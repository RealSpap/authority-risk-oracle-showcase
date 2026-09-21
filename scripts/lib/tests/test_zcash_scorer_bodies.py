"""
Unit tests for the BODIES of five `chains/zcash/scorers.py` functions that no
other unit test executed (measured with coverage: `score_all` 42/43 statements
not run, `score_ext_zec_omft` 39/40, `score_maya_asgard_vault` 25/26,
`score_l1` 23/24, `cross_exposure` 12/13). Until now they were checked only by
live runs against the real chains.

Everything is OFFLINE. Every reader the scorers import into their own
namespace is patched (`grpc`, `compute_concentration`, `find_multisig_spends`,
`taddr_balance`, `nr.*`, `mr.active_zec_vaults`, `zr.get_keyring`,
`zr.get_key_by_id`), the "patch the imported name, not the transport"
convention the other Zcash scorer tests use. On top of that every test also
blocks `subprocess.run` (every real reader shells out to `curl`), so a reader
that was missed fails loudly instead of touching the network. No key file is
needed.

FIXTURE PROVENANCE. No expected value here was obtained by running the
function under test. Each one comes from either

  * a documented real observation / published score, cited next to the fixture:
      - `chains/zcash/data/scored_targets_2026-09-19.md` (the 7-row table, the
        L1 concentration window 3,486,232-3,488,231, the zenZEC keyring facts)
      - `chains/zcash/data/scored_targets_2026-09-17.md` / `..-09-18.md`
        (`zec.omft.near` derivation, Maya vault table)
      - `chains/zcash/METHODOLOGY.md` sections 3.1 (12 `GetLightdInfo` reads
        of eu.zec.rocks: `/Zakura:1.3.1/` x6, `/Zebra:6.3.0/` x6, branch id
        37a5165b), 3.2 (fund spends, pubkey prefixes), 3.4/4.2 (k50=3, k25=1),
        3.6 (Maya vaults), 3.7 (zenZEC keyring), 4.6-4.8 (formulas)
      - `chains/zcash/data/scouting_candidates_2026-09-18.md` (the two full
        Maya vault `pub_key`s), `chains/zcash/data/zenzec_mpc_keyring_2026-09-19.md`
        (the keyring read and keys 387/388)
      - `data/finding_2026-09-18-cross-ecosystem-unresolved-floor-inversion.md`
  * or a hand derivation from the written scoring formula (METHODOLOGY.md 4.6-4.8:
    `admin_key_score_kn` ladder, `multisig_score_kn` = max(16, min(100, 20k-(n-k))),
    L1 multisig = min(100, 15*k50 + 5*k25), composite = floor(0.4a + 0.3m + 0.3t + 0.5),
    cross exposure = max(0, 100 - 20 * <other funds/vaults sharing >= 1 pubkey>)), with
    the arithmetic written in a comment beside it.

Where a fixture has to be synthetic (the observation exists but its exact
bytes were never published) the comment says which part is real and which part
is filler.

Identities that are DOCUMENTED FACTS (the lightwalletd operators, the two NEAR
RPCs) are hard-coded below and pinned against the scorer's constants in
`TestDocumentedConstants`, they are NOT read back from the code under test: a
renamed or wrong hostname in the scorer fails a test.

CONTRACT PINS. A few assertions pin behaviour that no real reader can produce
(a 2,001-block window, a k25-only-None concentration, a duplicated membership
entry, a non-zero timelock on a fund record). They are marked "contract pin" in
their comments: they hold the documented FORMULA to its stated rule at a corner
the live data never reaches, they are not observations. Tests that pin CURRENT
behaviour where the documentation is silent or where a finding says the current
behaviour is wrong are marked "characterization" and say what must be edited
together if the scorer is changed.
"""
import contextlib
import importlib.util
import io
import os
import subprocess
import sys
import unittest

REPO_ROOT = os.path.join(os.path.dirname(__file__), "..", "..", "..")


def _load_module(unique_name, relative_path):
    file_path = os.path.abspath(os.path.join(REPO_ROOT, relative_path))
    ecosystem_dir = os.path.dirname(file_path)
    if ecosystem_dir not in sys.path:
        sys.path.insert(0, ecosystem_dir)
    spec = importlib.util.spec_from_file_location(unique_name, file_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[unique_name] = mod
    spec.loader.exec_module(mod)
    return mod


scorers = _load_module("aro_test_zcash_scorer_bodies", "chains/zcash/scorers.py")

# Documented facts, hard-coded (NOT read from the scorer). METHODOLOGY.md section 2, Mainnet row
# (chains/zcash/METHODOLOGY.md line 94): "zec.rocks:443, zcash.mysideoftheweb.com:9067 (two distinct
# domains), eu.zec.rocks:443"; 3.1 (line 128): the 12 GetLightdInfo reads were taken on eu.zec.rocks:443;
# 3.5 (line 202) and scored_targets_2026-09-17.md: NEAR reads on rpc.mainnet.near.org cross-checked on
# free.rpc.fastnear.com (the https:// scheme is the scorer's own; the documents give the hostnames).
PRIMARY = "zec.rocks:443"
SECOND = "zcash.mysideoftheweb.com:9067"
LINEAGE_HOST = "eu.zec.rocks:443"
NEAR_PRIMARY = "https://rpc.mainnet.near.org"
NEAR_SECOND = "https://free.rpc.fastnear.com"


def _patch(test, obj, name, value):
    orig = getattr(obj, name)
    setattr(obj, name, value)
    test.addCleanup(lambda: setattr(obj, name, orig))


def _capture(fn, *args):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        out = fn(*args)
    return out, buf.getvalue()


class OfflineCase(unittest.TestCase):
    """Every real reader shells out to curl through subprocess.run: make any
    reader that a test forgot to patch fail loudly instead of going online."""

    def setUp(self):
        def _no_subprocess(*args, **kwargs):
            raise AssertionError(f"offline test attempted a subprocess/network call: {args!r}")
        _patch(self, subprocess, "run", _no_subprocess)


# ------------------------------------------------------------------ wire helpers
def _varint(n):
    out = b""
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            out += bytes([b | 0x80])
        else:
            return out + bytes([b])


def _field_varint(num, v):
    return _varint(num << 3) + _varint(v)


def _field_bytes(num, data):
    return _varint((num << 3) | 2) + _varint(len(data)) + data


def _lightd_info(tip, version):
    """GetLightdInfo wire message: consensusBranchId=6, blockHeight=7, nodeSubversion=14
    (field names per zcash_read.py's own `info` subcommand, lines 172-173, the same code family
    the scorer decodes with). PROVENANCE LIMIT: the lightwalletd LightdInfo .proto is not
    vendored in this repository and cannot be read offline, so these three field numbers are
    evidenced only by the project's own decoder. The round trip goes through the REAL decode(),
    so it proves the scorer and zcash_read.py agree with each other, not that they agree with
    lightwalletd. Branch id 37a5165b is the one METHODOLOGY.md 3.1 recorded on all 12 reads.
    `tip=None` omits blockHeight."""
    msg = _field_bytes(6, b"37a5165b")
    if tip is not None:
        msg += _field_varint(7, tip)
    return msg + _field_bytes(14, version.encode())


# ------------------------------------------------------------- published facts
# scored_targets_2026-09-19.md, "Summary table (live run, 2026-09-19)":
#   (target, adminKey, multisig, timelock, oracle, crossExposure, composite, l1CappedComposite)
L1_KEY = "0xB8e62E6AeB4C400b6F3e66cAb69ACe55439035c3"
ZIP271_ADDR = "t3ev37Q2uL1sfTsiJQJiWJoFzQpDhmnUwYo"
ZCG_ADDR = "t3cFfPt1Bcvgez9ZbMBFWeZsskxTkPzGCow"
VAULT_A_ADDR = "t1RBiXrLRdrHgsuSGQEusG2wCzPFczEVMfT"
VAULT_B_ADDR = "t1VtnnhTYhmADh7L2uKU3Sev7GscBHT6HfE"
ZENZEC_KEYRING = "keyring1k6vc6vhp6e6l3rxalue9v4ux"
PUBLISHED_2026_09_19 = [
    (L1_KEY, 20, 50, 35, 100, 100, 34, None),
    (ZIP271_ADDR, 50, 39, 0, 100, 100, 32, 32),
    (ZCG_ADDR, 50, 39, 0, 100, 100, 32, 32),
    ("zec.omft.near", 5, 18, 0, 100, 100, 7, None),
    (VAULT_A_ADDR, 65, 100, 0, 100, 100, 56, None),
    (VAULT_B_ADDR, 65, 100, 0, 100, 100, 56, None),
    (ZENZEC_KEYRING, 65, 60, 0, 100, 100, 44, None),
]

# L1 concentration window. scored_targets_2026-09-19.md publishes "3,486,232-3,488,231
# today" and METHODOLOGY.md 4.2 the rule "2,000 blocks ending 10 blocks below the lower tip":
# so the lower operator tip was 3,488,231 + 10 = 3,488,241 (derived by that rule; the tips
# themselves were never published, so BOTH tips are inferred/synthetic, only the window is real).
# The other operator's tip is synthetic: any value >= the lower one.
PUBLISHED_WINDOW = (3486232, 3488231)
LOWER_TIP = 3488241
HIGHER_TIP = 3488243
# METHODOLOGY.md 3.1: 12 successive GetLightdInfo reads of eu.zec.rocks:443 returned
# /Zakura:1.3.1/ 6 times and /Zebra:6.3.0/ 6 times (the interleaving is synthetic).
OBSERVED_VERSIONS = ["/Zakura:1.3.1/", "/Zebra:6.3.0/"] * 6


def _conc(blocks=2000, k50=3, k25=1):
    # METHODOLOGY.md 3.4/4.2 and scored_targets_2026-09-19.md: k50=3, k25=1 on both operators
    # over a 2,000-block window. Only these three keys are read by score_l1().
    return {"blocks": blocks, "addressesToExceed50Pct": k50, "addressesToExceed25Pct": k25}


class FakeLightd:
    """`grpc(host, "GetLightdInfo", b"")` -> [wire message]."""

    def __init__(self, versions, tips):
        self.versions = list(versions)
        self.tips = dict(tips)
        self.omit_tip_for = set()
        self.fail_hosts = {}
        self.calls = []
        self._lineage_reads = 0

    def __call__(self, host, method, msg):
        self.calls.append((host, method, msg))
        if host in self.fail_hosts:
            raise self.fail_hosts[host]
        if method != "GetLightdInfo":
            raise AssertionError(f"unexpected gRPC method in test: {method}")
        if host == LINEAGE_HOST:
            version = self.versions[self._lineage_reads % len(self.versions)]
            self._lineage_reads += 1
            tip = self.tips.get(host, LOWER_TIP)
        else:
            version = "/Zebra:6.3.0/"
            tip = self.tips[host]
        return [_lightd_info(None if host in self.omit_tip_for else tip, version)]

    def hosts_called(self):
        return [c[0] for c in self.calls]


class FakeConcentration:
    """`compute_concentration(host, start, end, step)`. `step` deliberately has NO default here
    (the real function defaults to 200, so a scorer that forgot to pass it would still behave the
    same live): a call that omits it raises TypeError, so the scorer's explicit `step=200` is a
    pinned part of its call contract (scorers.py score_l1, "step=200")."""

    def __init__(self, by_host):
        self.by_host = dict(by_host)
        self.calls = []

    def __call__(self, host, start, end, step):
        self.calls.append((host, start, end, step))
        return dict(self.by_host[host])


# ---- fund spends (find_multisig_spends fixtures)
def _pk(prefix_hex):
    # 33-byte compressed key. The 5-byte prefix is the REAL observed one (METHODOLOGY.md 3.2);
    # the remaining 28 bytes are synthetic filler (the full keys were never published,
    # only disjointness between the two sets matters here).
    return prefix_hex + "ab" * ((66 - len(prefix_hex)) // 2)


ZIP271_KEYS = [_pk("0248ca6a21"), _pk("027f05a867"), _pk("030b7820b7")]   # METHODOLOGY.md 3.2
ZCG_KEYS = [_pk("0352d50656"), _pk("02f39d0b69"), _pk("027072ba23")]      # METHODOLOGY.md 3.2


def _spend(m, n, keys, op, suffix, height, vin, vout):
    return {"height": height, "m": m, "n": n, "op": op, "pubkeys": list(keys), "suffix": suffix,
            "vin": vin, "transparentVout": vout}


# METHODOLOGY.md 3.2: t3ev37... spends at 3,227,947 (one 7,875 ZEC chunk, no transparent
# output) and 3,308,125 (spent that output, paid 7,308.4093 ZEC back), both
# `OP_2 <3 pubkeys> OP_3 OP_CHECKMULTISIG`, 4 transactions scanned in total.
ZIP271_SPENDS = [
    _spend(2, 3, ZIP271_KEYS, "CHECKMULTISIG", None, 3227947, 1, 0),
    _spend(2, 3, ZIP271_KEYS, "CHECKMULTISIG", None, 3308125, 1, 1),
]
# METHODOLOGY.md 3.2: t3cFfPt1... 8 sweep transactions at heights 3,478,969 and 3,478,971
# (1,001 inputs each, no transparent output) out of 10,009 scanned; redeem script
# `OP_2 <3 pubkeys> OP_3 OP_CHECKMULTISIGVERIFY <4-byte nonce> OP_DROP OP_DEPTH OP_0 OP_EQUAL`.
# METHODOLOGY.md 7.3 records the real suffix `04f3bc7045 75 74 00 87` (4-byte nonce, OP_DROP,
# OP_DEPTH OP_0 OP_EQUAL). Only the 4/4 split of the 8 spends between the two heights is synthetic.
ZCG_SUFFIX = "04" + "f3bc7045" + "75" + "740087"
ZCG_SPENDS = [_spend(2, 3, ZCG_KEYS, "CHECKMULTISIGVERIFY", ZCG_SUFFIX, h, 1001, 0)
              for h in [3478969] * 4 + [3478971] * 4]


def _scan(addr, spends, scanned):
    return {"address": addr, "scannedTxs": scanned, "spendsFound": len(spends), "range": [0, 0], "spends": spends}


class FakeFundScanner:
    """`find_multisig_spends(host, addr, start, end, window)`."""

    def __init__(self):
        self.results = {}
        self.calls = []

    def __call__(self, host, addr, start, end, window):
        self.calls.append((host, addr, start, end, window))
        r = self.results[(host, addr)]
        if isinstance(r, Exception):
            raise r
        return r


# ---- NEAR fixtures (scored_targets_2026-09-17.md, scorers.py score_ext_zec_omft docstring)
FACTORY = "omft.near"
BARE = "bridge-mng.near"                    # one full-access key, confirmed live
DAO = "int-mnt-dao.sputnik-dao.near"        # Requestor role: 3 members, call {quorum 0, threshold 1}
# The count (3) is the real observation; the member account names are synthetic.
REQUESTORS = ["synthetic-requestor-1.near", "synthetic-requestor-2.near", "synthetic-requestor-3.near"]


def _acl(grantees):
    # Only the subset of near_plugins' acl_get_permissioned_accounts() the scorer reads
    # (`roles.TokenDepositer.grantees`). near_read.permissioned_accounts() returns the contract
    # view's JSON unchanged (near_read.py, call_view). SHAPE PROVENANCE LIMIT: this repository
    # documents the payload only through the scorer's own field accesses and the role holders in
    # scored_targets_2026-09-17.md; the near_plugins JSON schema itself is not vendored here.
    # Role::DAO is held solely by intents.sputnik-dao.near (docstring, 09-17 doc).
    return {"roles": {"TokenDepositer": {"grantees": list(grantees)},
                      "DAO": {"grantees": ["intents.sputnik-dao.near"]}}}


def _key(i):
    return {"public_key": f"ed25519:synthetic-key-{i}", "access_key": {"nonce": 0, "permission": "FullAccess"}}


def _policy(members, call_vote_policy=None, vote_policy=None, role_name="Requestor"):
    # Sputnik DAO v2 get_policy() subset: roles[].name, roles[].kind.Group, roles[].vote_policy
    # keyed by proposal kind with {weight_kind, quorum, threshold}. Real observations behind it
    # (scorers.py score_ext_zec_omft docstring, scored_targets_2026-09-17.md): int-mnt-dao's
    # Requestor role = 3 members, call {quorum 0, threshold 1}; intents.sputnik-dao.near's council =
    # 5 members, threshold [79, 100]. SHAPE PROVENANCE LIMIT: the surrounding JSON layout is
    # reconstructed from the scorer's own field accesses (near_read.dao_policy returns the raw view).
    vp = vote_policy if vote_policy is not None else {"call": call_vote_policy}
    return {"roles": [
        # synthetic decoy: proves the scorer picks the role NAMED Requestor, not the first/largest
        {"name": "synthetic-decoy", "kind": {"Group": ["decoy-1.near", "decoy-2.near", "decoy-3.near", "decoy-4.near", "decoy-5.near"]},
         "vote_policy": {"call": {"weight_kind": "RoleWeight", "quorum": "0", "threshold": [79, 100]}}},
        {"name": role_name, "kind": {"Group": list(members)}, "vote_policy": vp},
    ]}


ONE_VOTE = {"weight_kind": "RoleWeight", "quorum": "0", "threshold": "1"}  # "threshold=1, quorum=0" (09-17 doc)


class FakeNear:
    """Per-endpoint fakes of near_read.permissioned_accounts / access_key_count / dao_policy.
    `second[name]` is a value served ONLY by NEAR_SECOND_RPC (an operator that disagrees)."""

    def __init__(self):
        self.acl = _acl([BARE, DAO])
        self.keys = {BARE: [_key(1)]}                       # "exactly ONE full-access key"
        self.policy = {DAO: _policy(REQUESTORS, ONE_VOTE)}
        self.second = {}
        self.calls = []

    def _serve(self, name, url, account, value):
        self.calls.append((name, url, account))
        if url == NEAR_SECOND and name in self.second:
            return self.second[name]
        return value

    def permissioned_accounts(self, url, account):
        return self._serve("permissioned_accounts", url, account, self.acl)

    def access_key_count(self, url, account):
        return self._serve("access_key_count", url, account, self.keys[account])

    def dao_policy(self, url, account):
        return self._serve("dao_policy", url, account, self.policy[account])

    def urls_for(self, name):
        return sorted(c[1] for c in self.calls if c[0] == name)


# ---- Maya fixtures (METHODOLOGY.md 3.6, scored_targets_2026-09-18.md, scouting_candidates_2026-09-18.md)
VAULT_A_PUB = "mayapub1addwnpepqdgafgd6gv8x09m9vu6fvqzkj0e0v2wj64ezs7vm5p2w5tmf0t0hvpljmch"
VAULT_B_PUB = "mayapub1addwnpepq24t2hk53nz9k5rkcs0vaqn5crc08rmznlpmgvsx670wxdd7htw8225yt4w"
VAULT_A_LEDGER = 220970943152     # exact match to live balance
VAULT_A_LIVE = 220970943152
VAULT_B_LEDGER = 129157478056     # Mayanode ledger
VAULT_B_LIVE = 126951364578       # live on-chain, both operators; gap = 2,206,113,478 zat


def _members(tag, n=20):
    # n=20 per vault and the two sets being completely disjoint are the real observations
    # (METHODOLOGY.md 3.6); the member strings themselves are synthetic.
    return [f"synthetic-tss-member-{tag}-{i:02d}" for i in range(n)]


def _vault_a():
    # Dict layout = maya_read.active_zec_vaults() (maya_read.py lines 87-106): pub_key,
    # ledger_amount_zat (int of the ZEC.ZEC coin amount), zec_address, membership.
    return {"pub_key": VAULT_A_PUB, "ledger_amount_zat": VAULT_A_LEDGER, "zec_address": VAULT_A_ADDR,
            "membership": _members("a")}


def _vault_b():
    return {"pub_key": VAULT_B_PUB, "ledger_amount_zat": VAULT_B_LEDGER, "zec_address": VAULT_B_ADDR,
            "membership": _members("b")}


class FakeBalances:
    """`taddr_balance(host, addr)` -> zat (a table keyed by (host, addr))."""

    def __init__(self):
        self.table = {}
        self.calls = []

    def set_both(self, addr, zat):
        self.table[(PRIMARY, addr)] = zat
        self.table[(SECOND, addr)] = zat

    def __call__(self, host, *addrs):
        assert len(addrs) == 1, addrs
        self.calls.append((host, addrs[0]))
        value = self.table[(host, addrs[0])]
        if isinstance(value, Exception):
            raise value
        return value


# ---- zenZEC fixtures (zenzec_mpc_keyring_2026-09-19.md, "2. The keyring's live party-threshold",
# lines 80-95, and "3. The two Zcash-mainnet addresses", lines 110-120). The dict layout is
# zenrock_read.get_keyring() / get_key_by_id() (zenrock_read.py docstrings: address, creator,
# description, admins, parties, party_threshold, key_req_fee, sig_req_fee, is_active, height;
# and id, keyring_addr, wallets{type: address}, zcash_mainnet_address_rederived, height); the
# keyring JSON in the data note matches field for field.
KEY_387_ADDR = "t1WrUBdocqpubAHoRrpihYBoDFjPg7utLka"
KEY_388_ADDR = "t1S9DvnjtxgP4HMo1W6sTxVh95f6cmZ9dcw"
KEYRING_READ = {
    "height": 9534552,   # the frozen height, METHODOLOGY.md 4.8.1
    "address": ZENZEC_KEYRING, "creator": "zen1wa2l79s9v9fxl0ergelvv55nmfdh6ms052c9rq",
    "description": "Zenrock MPC", "party_threshold": 3, "key_req_fee": 75000000, "sig_req_fee": 50000000,
    "is_active": True, "admins": ["zen1wa2l79s9v9fxl0ergelvv55nmfdh6ms052c9rq"],
    "parties": ["zen1vxl32yly7zgrssnxnhlk4dcryylmz6zvkszclh", "zen1dy5mleccrc0sq3gflxklc3v32269c5704jrz8z",
                "zen12ppadg7mwmtf9e4mm8wvk2hkvduqh43vhn0zjr"],
}


def _zr_key(key_id, addr):
    return {"height": 9534552, "id": key_id, "keyring_addr": ZENZEC_KEYRING,
            "wallets": {"WALLET_TYPE_ZCASH_MAINNET": addr}, "zcash_mainnet_address_rederived": addr}


class World:
    """Reader fakes reproducing the 2026-09-19 state the published table was scored from."""

    def __init__(self):
        self.lightd = FakeLightd(OBSERVED_VERSIONS, {PRIMARY: HIGHER_TIP, SECOND: LOWER_TIP})
        self.conc = FakeConcentration({PRIMARY: _conc(), SECOND: _conc()})
        self.scan = FakeFundScanner()
        for host in (PRIMARY, SECOND):  # "identical on both operators where cross-checked" (3.2)
            self.scan.results[(host, ZIP271_ADDR)] = _scan(ZIP271_ADDR, ZIP271_SPENDS, 4)
            self.scan.results[(host, ZCG_ADDR)] = _scan(ZCG_ADDR, ZCG_SPENDS, 10009)
        self.near = FakeNear()
        self.vaults = [_vault_a(), _vault_b()]
        self.maya_error = None
        self.balances = FakeBalances()
        self.balances.set_both(VAULT_A_ADDR, VAULT_A_LIVE)
        self.balances.set_both(VAULT_B_ADDR, VAULT_B_LIVE)
        self.balances.set_both(KEY_387_ADDR, 0)   # "both hold 0 ZEC" on both operators
        self.balances.set_both(KEY_388_ADDR, 0)
        self.keyring = dict(KEYRING_READ)
        self.keys = {387: _zr_key(387, KEY_387_ADDR), 388: _zr_key(388, KEY_388_ADDR)}
        self.zr_error = None

    def install_l1(self, test):
        _patch(test, scorers, "grpc", self.lightd)
        _patch(test, scorers, "compute_concentration", self.conc)

    def install_funds(self, test):
        _patch(test, scorers, "find_multisig_spends", self.scan)

    def install_ext(self, test):
        _patch(test, scorers.nr, "permissioned_accounts", self.near.permissioned_accounts)
        _patch(test, scorers.nr, "access_key_count", self.near.access_key_count)
        _patch(test, scorers.nr, "dao_policy", self.near.dao_policy)

    def install_maya(self, test):
        def fake_active_zec_vaults():
            if self.maya_error:
                raise self.maya_error
            return [dict(v) for v in self.vaults]
        _patch(test, scorers.mr, "active_zec_vaults", fake_active_zec_vaults)
        # METHODOLOGY.md 3.6 (2026-09-19): chain ZEC reads "halted": true, "chain_trading_paused": true
        _patch(test, scorers.mr, "inbound_addresses",
               lambda: [{"chain": "BTC", "halted": False}, {"chain": "ZEC", "halted": True, "chain_trading_paused": True}])
        _patch(test, scorers, "taddr_balance", self.balances)

    def install_zenzec(self, test):
        def fake_get_keyring(addr, host=None):
            assert addr == ZENZEC_KEYRING, addr
            if self.zr_error:
                raise self.zr_error
            return dict(self.keyring)

        def fake_get_key_by_id(key_id, host=None):
            return dict(self.keys[key_id])
        _patch(test, scorers.zr, "get_keyring", fake_get_keyring)
        _patch(test, scorers.zr, "get_key_by_id", fake_get_key_by_id)
        _patch(test, scorers, "taddr_balance", self.balances)

    def install_all(self, test):
        self.install_l1(test)
        self.install_funds(test)
        self.install_ext(test)
        self.install_maya(test)
        self.install_zenzec(test)


# ================================================================ documented constants
class TestDocumentedConstants(OfflineCase):
    """The hosts and dated constants the tests above hard-code are DOCUMENTED FACTS, and the
    scorer's own constants are compared to them here, so a wrong or renamed one fails."""

    def test_lightwalletd_and_near_operators_are_the_documented_ones(self):
        # METHODOLOGY.md 2 (line 94), 3.1 (line 128), 3.5 (line 202)
        self.assertEqual(scorers.PRIMARY_HOST, PRIMARY)
        self.assertEqual(scorers.SECOND_HOST, SECOND)
        self.assertNotEqual(PRIMARY, SECOND)
        self.assertEqual(scorers.LINEAGE_SAMPLE_HOST, LINEAGE_HOST)
        self.assertEqual(scorers.NEAR_PRIMARY_RPC, NEAR_PRIMARY)
        self.assertEqual(scorers.NEAR_SECOND_RPC, NEAR_SECOND)
        self.assertEqual(scorers.ZEC_OMFT_TOKEN, "zec.omft.near")
        self.assertEqual(scorers.ZEC_OMFT_FACTORY, "omft.near")   # 09-17 doc: factory `omft.near`

    def test_l1_window_and_dated_constants_are_the_documented_ones(self):
        # METHODOLOGY.md 4.2/4.6: 2,000 blocks ending 10 blocks below the lower tip
        self.assertEqual((scorers.CONC_WINDOW, scorers.CONC_CONFIRMATIONS), (2000, 10))
        # METHODOLOGY.md 4.3 (median 23.8 days) and 4.6 (timelock cap 35)
        self.assertEqual(scorers._MEDIAN_SCHEDULED_NOTICE_DAYS, 23.8)
        self.assertEqual(scorers._EMERGENCY_BYPASS_TIMELOCK_CAP, 35)
        # METHODOLOGY.md 4.2: unresolved-P2SH floor adminKey 5 / multisig 16
        self.assertEqual((scorers._UNRESOLVED_P2SH_ADMIN_KEY, scorers._UNRESOLVED_P2SH_MULTISIG), (5, 16))
        # METHODOLOGY.md 7.3: keccak256("zcash:mainnet:l1") last 20 bytes (`cast keccak`)
        self.assertEqual(scorers.L1_TARGET_ID, L1_KEY)

    def test_zenzec_identity_and_frozen_snapshot_constants_are_the_documented_ones(self):
        # zenzec_mpc_keyring_2026-09-19.md lines 51-53 (keyring, key ids); METHODOLOGY.md 4.8.1 (frozen height/time)
        self.assertEqual(scorers.ZENZEC_KEYRING_ADDR, ZENZEC_KEYRING)
        self.assertEqual(scorers.ZENZEC_INFRA_KEY_IDS, {"rewards_deposit": 387, "change_address": 388})
        self.assertEqual(scorers.ZENZEC_FROZEN_HEIGHT, 9534552)
        self.assertEqual(scorers.ZENZEC_FROZEN_AS_OF, "2026-08-10T23:19:52Z")


# =========================================================================== score_l1
class _ReverseIterationSet(set):
    """A real set whose ITERATION ORDER is forced to be reverse-sorted. Python randomises str
    hashing per process, so the natural order of a two-string set is sorted about half the time:
    a scorer that prints list(observed) instead of sorted(observed) would pass by luck on some
    hash seeds. With this subclass an unsorted print can never coincide with the sorted one."""

    def __iter__(self):
        return iter(sorted(set.__iter__(self), reverse=True))


class TestScoreL1(OfflineCase):
    def setUp(self):
        super().setUp()
        self.w = World()
        self.w.install_l1(self)

    def test_published_run_reproduces_all_five_scores_and_composite(self):
        # scored_targets_2026-09-19.md row 1: 20 / 50 / 35 / 100 / 100 -> composite 34.
        # Hand derivation: admin 20 (1 independent lineage), multisig min(100, 15*3 + 5*1) = 50,
        # timelock cap 35, composite floor(0.4*20 + 0.3*50 + 0.3*35 + 0.5) = floor(8+15+10.5+0.5) = 34.
        r = scorers.score_l1()
        self.assertEqual(r["target"], L1_KEY)
        self.assertEqual(r["label"], "Zcash L1 (consensus-rule-change authority)")
        self.assertEqual(r["adminKeyScore"], 20)
        self.assertEqual(r["multisigScore"], 50)
        self.assertEqual(r["timelockScore"], 35)
        self.assertEqual(r["oracleAuthorityScore"], 100)
        self.assertEqual(r["crossExposureScore"], 100)
        self.assertEqual(r["compositeScore"], 34)

    def test_l1_is_the_baseline_and_carries_no_l1_cap_key(self):
        # scored_targets_2026-09-19.md: l1CappedComposite column is "n/a (baseline)" for L1.
        self.assertNotIn("l1CappedComposite", scorers.score_l1())

    def test_published_run_notes_carry_the_disclosed_limits(self):
        notes = scorers.score_l1()["notes"]
        self.assertEqual(len(notes), 3)
        # METHODOLOGY.md 3.1: 2 distinct strings observed, Zakura excluded as a fork -> 1 independent.
        # 4.6 says the fork judgment is "a dated interpretive finding, not something a live read alone
        # determines": that DATED caveat is part of the disclosure and is pinned, not just the count.
        self.assertIn(f"{LINEAGE_HOST}: 2 distinct nodeSubversion string(s) observed over 12 samples", notes[0])
        self.assertIn("['/Zakura:1.3.1/', '/Zebra:6.3.0/']", notes[0])
        self.assertIn("1 counted as independent", notes[0])
        self.assertIn("Zakura excluded as a declared fork of Zebra", notes[0])
        self.assertIn("DATED finding", notes[0])
        # METHODOLOGY.md 4.2: payout addresses are an UPPER bound, so multisigScore is an upper bound
        self.assertIn("blocks 3486232-3488231 (2000 blocks", notes[1])
        self.assertIn(f"identical k50/k25 on {PRIMARY} and {SECOND}", notes[1])
        self.assertIn("3 payout addresses exceed 50%, 1 exceed 25%", notes[1])
        self.assertIn("UPPER bound", notes[1])
        # METHODOLOGY.md 4.3/4.6: 23.8-day median notice, capped at 35 by the 2026-06 zero-notice
        # emergency Orchard-disabling fork. 4.3 and 4.6 both state the 23.8 is measured once (by
        # notice_period.py on 2026-09-17), not re-derived on every run: that is the "DATED fact" caveat.
        self.assertIn("timelockScore capped at 35", notes[2])
        self.assertIn("23.8-day median", notes[2])
        self.assertIn("DATED fact", notes[2])
        self.assertIn("2026-06 emergency Orchard-disabling", notes[2])
        self.assertIn("zero public notice", notes[2])
        self.assertFalse(any("FAILED" in n or "did not fully resolve" in n for n in notes))

    def test_lineage_versions_are_listed_sorted_whatever_the_set_iteration_order(self):
        # The note lists the distinct strings SORTED (scorers.py prints `sorted(observed)`; METHODOLOGY.md
        # 3.1 gives them in the same Zakura-then-Zebra order). A listing that changed order between
        # processes would make the published note, and anything hashed from it, non-reproducible. Str-set
        # iteration order depends on PYTHONHASHSEED, so the real _observed_lineages() result is wrapped in
        # a set that iterates in REVERSE-sorted order: the note can only come out sorted if the scorer
        # sorts it. Everything else the scorer does with the set (len, the fork-prefix scan) is unaffected.
        real = scorers._observed_lineages
        _patch(self, scorers, "_observed_lineages", lambda *a, **k: _ReverseIterationSet(real(*a, **k)))
        note = scorers.score_l1()["notes"][0]
        self.assertIn("observed over 12 samples: ['/Zakura:1.3.1/', '/Zebra:6.3.0/'] -- ", note)
        self.assertNotIn("['/Zebra:6.3.0/', '/Zakura:1.3.1/']", note)

    def test_lineage_sample_is_twelve_reads_of_the_load_balanced_domain(self):
        # scored_targets_2026-09-17.md: "a 12-sample lineage check"; note text says "over 12 samples"
        scorers.score_l1()
        hosts = self.w.lightd.hosts_called()
        self.assertEqual(hosts.count(LINEAGE_HOST), 12)
        self.assertEqual(hosts.count(PRIMARY), 1)
        self.assertEqual(hosts.count(SECOND), 1)
        self.assertEqual({c[1] for c in self.w.lightd.calls}, {"GetLightdInfo"})

    def test_window_is_2000_blocks_ending_10_below_the_lower_tip(self):
        # scored_targets_2026-09-19.md: window 3,486,232-3,488,231 (see LOWER_TIP derivation above)
        scorers.score_l1()
        self.assertEqual([(c[1], c[2]) for c in self.w.conc.calls], [PUBLISHED_WINDOW, PUBLISHED_WINDOW])
        self.assertEqual(PUBLISHED_WINDOW[1] - PUBLISHED_WINDOW[0] + 1, 2000)

    def test_concentration_is_computed_on_both_operators_with_step_200(self):
        # Contract pin: scorers.py passes step=200 explicitly on BOTH calls. FakeConcentration has no
        # default for `step`, so a call that omits it raises TypeError instead of silently taking the
        # real function's own default of 200.
        scorers.score_l1()
        self.assertEqual([c[0] for c in self.w.conc.calls], [PRIMARY, SECOND])
        self.assertEqual({c[3] for c in self.w.conc.calls}, {200})

    def test_lower_tip_wins_whichever_operator_is_behind(self):
        # METHODOLOGY.md 4.2: "below the lower tip of two lightwalletd operators"
        self.w.lightd.tips = {PRIMARY: LOWER_TIP, SECOND: HIGHER_TIP}
        scorers.score_l1()
        self.assertEqual([(c[1], c[2]) for c in self.w.conc.calls], [PUBLISHED_WINDOW, PUBLISHED_WINDOW])

    def test_lineage_ladder_drives_admin_key_and_composite(self):
        # 4.6 ladder: 1 independent lineage -> 20, 2 -> 45, 3+ -> 65 (higher bands are
        # untested against real Zcash state, hand-derived here). multisig 50 + timelock 35 fixed,
        # so composite = floor(0.4*A + 15 + 10.5 + 0.5) = floor(0.4*A + 26): A=20 -> 34, 45 -> 44, 65 -> 52.
        cases = [
            # METHODOLOGY.md 7.3 (2026-09-17 second run): 12 reads = 5 /Zakura:1.3.1/ + 7 /Zebra:6.3.0/,
            # still 1 independent lineage, adminKey 20 ("yes" agree)
            ("09-17 second-run observation, 5 Zakura + 7 Zebra",
             ["/Zakura:1.3.1/"] * 5 + ["/Zebra:6.3.0/"] * 7, 1, 20, 34),
            ("only Zebra", ["/Zebra:6.3.0/"], 1, 20, 34),
            ("only the Zakura fork: never counted as 0 independent lineages", ["/Zakura:1.3.1/"], 1, 20, 34),
            ("Zebra + one hypothetical independent implementation", ["/Zebra:6.3.0/", "/Hypothetical:1.0.0/"], 2, 45, 44),
            ("Zebra + two hypothetical independent implementations",
             ["/Zebra:6.3.0/", "/Hypothetical:1.0.0/", "/Other:2.0.0/"], 3, 65, 52),
            # 5 distinct strings (an unsorted listing then matches the sorted one only 1 time in 120),
            # one of them the Zakura fork: 4 independent, still the 3+ band -> admin 65,
            # composite floor(0.4*65 + 0.3*50 + 0.3*35 + 0.5) = floor(26 + 15 + 10.5 + 0.5) = 52.
            ("Zakura + Zebra + three hypothetical implementations",
             ["/Zebra:6.3.0/", "/Zakura:1.3.1/", "/Gamma:3.0.0/", "/Alpha:1.0.0/", "/Beta:2.0.0/"], 4, 65, 52),
        ]
        for name, versions, independent, admin, composite in cases:
            with self.subTest(name):
                self.w.lightd.versions = versions
                self.w.lightd._lineage_reads = 0
                r = scorers.score_l1()
                self.assertIn(f"{independent} counted as independent", r["notes"][0])
                # the listed strings are the distinct ones in sorted order (built from the FIXTURE list)
                self.assertIn(f"{len(set(versions))} distinct nodeSubversion string(s) observed over 12 samples: "
                              f"{sorted(set(versions))} -- ", r["notes"][0])
                self.assertEqual(r["adminKeyScore"], admin)
                self.assertEqual(r["multisigScore"], 50)
                self.assertEqual(r["compositeScore"], composite)

    def test_operators_disagreeing_on_any_concentration_field_degrade_multisig_to_20(self):
        # METHODOLOGY.md 4.6: "identical on both or degraded to 20". Composite of the degraded
        # result: floor(0.4*20 + 0.3*20 + 0.3*35 + 0.5) = floor(8 + 6 + 10.5 + 0.5) = 25.
        cases = [
            ("k50 differs", _conc(k50=3), _conc(k50=4)),
            ("k25 differs", _conc(k25=1), _conc(k25=2)),
            ("blocks differ", _conc(blocks=2000), _conc(blocks=1999)),
        ]
        for name, primary, second in cases:
            with self.subTest(name):
                self.w.conc.by_host = {PRIMARY: primary, SECOND: second}
                r = scorers.score_l1()
                self.assertEqual(r["multisigScore"], 20)
                self.assertEqual(r["compositeScore"], 25)
                self.assertEqual(r["adminKeyScore"], 20)      # only multisig degrades
                self.assertEqual(r["timelockScore"], 35)
                self.assertTrue(any("concentration cross-check FAILED on 3486232-3488231" in n for n in r["notes"]))
                self.assertTrue(any("did not fully resolve this run -- multisigScore degraded, treat as unverified" in n
                                    for n in r["notes"]))
                self.assertFalse(any("identical k50/k25" in n for n in r["notes"]))

    def test_failed_cross_check_note_shows_both_operators_values(self):
        self.w.conc.by_host = {PRIMARY: _conc(k50=3, k25=1), SECOND: _conc(k50=4, k25=1)}
        note = next(n for n in scorers.score_l1()["notes"] if "FAILED" in n)
        self.assertIn(f"{PRIMARY} blocks=2000 k50=3 k25=1", note)
        self.assertIn(f"{SECOND} blocks=2000 k50=4 k25=1", note)

    def test_window_that_is_not_exactly_2000_blocks_fails_even_when_both_operators_agree(self):
        # METHODOLOGY.md 4.2/4.6: the sample is "the 2,000 blocks ending 10 below the lower tip". A count
        # that is not exactly 2,000 is not that sample even when both operators agree with each other.
        # 1999 is a plausible short read (a range served short). Contract pin: 2001 cannot come out of a
        # 2,000-block range with a real reader, it holds the rule to "exactly 2,000" in BOTH directions.
        for name, blocks in [("short by one", 1999), ("long by one", 2001)]:
            with self.subTest(name):
                self.w.conc.by_host = {PRIMARY: _conc(blocks=blocks), SECOND: _conc(blocks=blocks)}
                r = scorers.score_l1()
                self.assertEqual(r["multisigScore"], 20)
                self.assertEqual(r["compositeScore"], 25)
                self.assertTrue(any("FAILED" in n for n in r["notes"]))
                self.assertFalse(any("identical k50/k25" in n for n in r["notes"]))

    def test_unresolvable_k_on_both_operators_degrades_multisig_to_20(self):
        # compute_concentration() returns None when the attributed addresses never exceed the
        # threshold (miner_concentration.py addresses_to_exceed). Identical on both operators, so no
        # FAILED note, but `(k50 and k25)` is falsy -> the documented floor of 20 (METHODOLOGY.md 4.6:
        # "degraded to 20"). Hand derivation of the composite: floor(8 + 6 + 10.5 + 0.5) = 25.
        # The real reader cannot give k25 None with k50 set (addresses_to_exceed(25) crosses its
        # threshold no later than addresses_to_exceed(50)), so the third case is a contract pin: the
        # documented rule is "degrade unless BOTH k50 and k25 resolved", and it must not depend on which
        # of the two is missing.
        for name, k50, k25 in [("both None", None, None), ("only k50 None", None, 1),
                               ("only k25 None (contract pin)", 3, None)]:
            with self.subTest(name):
                self.w.conc.by_host = {PRIMARY: _conc(k50=k50, k25=k25), SECOND: _conc(k50=k50, k25=k25)}
                r = scorers.score_l1()
                self.assertEqual(r["multisigScore"], 20)
                self.assertEqual(r["compositeScore"], 25)
                self.assertFalse(any("FAILED" in n for n in r["notes"]))
                self.assertTrue(any("multisigScore degraded" in n for n in r["notes"]))

    def test_documented_sensitivity_if_the_top_and_fifth_payers_were_one_entity(self):
        # METHODOLOGY.md 7.3 "Sensitivity of the address-versus-entity bound (not scored)": if the two
        # untagged payers were one entity, k50 would be 2 -> multisigScore min(100, 15*2 + 5*1) = 35
        # instead of 50, and the L1 composite floor(8 + 10.5 + 10.5 + 0.5) = 29 instead of 34.
        self.w.conc.by_host = {PRIMARY: _conc(k50=2, k25=1), SECOND: _conc(k50=2, k25=1)}
        r = scorers.score_l1()
        self.assertEqual(r["multisigScore"], 35)
        self.assertEqual(r["compositeScore"], 29)

    def test_multisig_is_capped_at_100_for_a_very_dispersed_hash_rate(self):
        # 4.6: min(100, 15*k50 + 5*k25). k50=8, k25=4 -> 120 + 20 = 140 -> 100.
        # composite floor(8 + 30 + 10.5 + 0.5) = 49.
        self.w.conc.by_host = {PRIMARY: _conc(k50=8, k25=4), SECOND: _conc(k50=8, k25=4)}
        r = scorers.score_l1()
        self.assertEqual(r["multisigScore"], 100)
        self.assertEqual(r["compositeScore"], 49)

    def test_unreadable_tip_raises_instead_of_scoring(self):
        # A missing blockHeight is not a disagreement to degrade on: score_all() catches the
        # exception and skips L1 (see TestScoreAll). Characterization of the CURRENT failure mode: the
        # scorer's `next(...)` over the decoded fields raises StopIteration (no explicit message). The
        # exact type is pinned, and so is that it failed BEFORE any concentration read, so that an
        # unrelated crash later in score_l1() cannot satisfy this test. If the scorer is changed to raise
        # a clearer error, edit the expected type here.
        self.w.lightd.omit_tip_for = {SECOND}
        with self.assertRaises(StopIteration):
            scorers.score_l1()
        self.assertEqual(self.w.conc.calls, [])
        self.assertEqual(self.w.lightd.hosts_called().count(SECOND), 1)      # the failure is on the second tip read

    def test_lightwalletd_failure_during_lineage_sampling_raises(self):
        self.w.lightd.fail_hosts = {LINEAGE_HOST: RuntimeError("lightwalletd unreachable")}
        with self.assertRaises(RuntimeError):
            scorers.score_l1()


# ===================================================================== cross_exposure
def _fund(label, keys, degraded=False, cross=None, composite=0, admin=50, multisig=39, timelock=0):
    # admin 50 / multisig 39 = the published 2-of-3 ladder values (scored_targets_2026-09-19.md).
    # timelock 0 is the documented FUND value (METHODOLOGY.md 4.3, 4.6); the parameter exists only
    # for the contract pin that the re-derived composite uses the record's own timelockScore.
    return {"target": label + "-addr", "label": label, "adminKeyScore": admin, "multisigScore": multisig,
            "timelockScore": timelock, "oracleAuthorityScore": 100, "crossExposureScore": cross,
            "compositeScore": composite, "notes": ["n0"], "_pubkeys": set(keys), "_degraded": degraded}


class TestCrossExposure(OfflineCase):
    def test_disjoint_real_key_sets_score_100_and_recompute_the_published_composite(self):
        # METHODOLOGY.md 3.2: the two funds use disjoint pubkeys (real prefixes).
        # Published: crossExposure 100, composite 32 = floor(0.4*50 + 0.3*39 + 0 + 0.5) = floor(32.2).
        # The stale composite (0) is overwritten with the re-derived one.
        a = _fund("ZIP 271", ZIP271_KEYS, composite=0)
        b = _fund("ZCG", ZCG_KEYS, composite=0)
        scorers.cross_exposure([a, b])
        for r in (a, b):
            self.assertEqual(r["crossExposureScore"], 100)
            self.assertEqual(r["compositeScore"], 32)
            self.assertEqual(r["notes"][-1], "signer pubkeys confirmed disjoint from every other tracked Zcash fund this run")

    def test_shared_pubkey_costs_20_per_other_fund_and_names_it(self):
        # 4.6: max(0, 100 - 20 * count of other tracked Zcash funds sharing >= 1 pubkey)
        shared = ZIP271_KEYS[0]
        a = _fund("ZIP 271", ZIP271_KEYS)
        b = _fund("ZCG", [shared, ZCG_KEYS[1], ZCG_KEYS[2]])
        scorers.cross_exposure([a, b])
        self.assertEqual(a["crossExposureScore"], 80)
        self.assertEqual(b["crossExposureScore"], 80)
        self.assertEqual(a["notes"][-1], "shares at least one signer pubkey with: ['ZCG']")
        self.assertEqual(b["notes"][-1], "shares at least one signer pubkey with: ['ZIP 271']")
        self.assertEqual(a["compositeScore"], 32)      # crossExposure is not a composite input

    def test_penalty_counts_other_funds_not_shared_pubkeys(self):
        # METHODOLOGY.md 4.6: "max(0, 100 - 20 * count of other tracked Zcash funds sharing >=1 pubkey)".
        # Two funds that share TWO pubkeys are still ONE other fund: 100 - 20*1 = 80 each (a per-pubkey
        # count would give 100 - 20*2 = 60). Hypothetical key sets, no real fund shares any key.
        a = _fund("A", ["k1", "k2", "k3"])
        b = _fund("B", ["k1", "k2", "k9"])
        scorers.cross_exposure([a, b])
        self.assertEqual(a["crossExposureScore"], 80)
        self.assertEqual(b["crossExposureScore"], 80)
        self.assertEqual(a["notes"][-1], "shares at least one signer pubkey with: ['B']")
        # and the fully shared script (3 of 3 keys) is still just one other fund
        c = _fund("C", ["k1", "k2", "k3"])
        d = _fund("D", ["k1", "k2", "k3"])
        scorers.cross_exposure([c, d])
        self.assertEqual((c["crossExposureScore"], d["crossExposureScore"]), (80, 80))

    def test_composite_is_rederived_from_the_records_own_three_scores_including_timelock(self):
        # Contract pin (no real fund has timelock != 0, METHODOLOGY.md 4.3): the composite that
        # cross_exposure() rewrites is the repo-wide formula over the record's OWN adminKey/multisig/
        # timelock, not a hard-wired timelock of 0. admin 50, multisig 39, timelock 35:
        # floor(0.4*50 + 0.3*39 + 0.3*35 + 0.5) = floor(20 + 11.7 + 10.5 + 0.5) = floor(42.7) = 42
        # (with the timelock term dropped it would be 32).
        a = _fund("A", ZIP271_KEYS, composite=0, timelock=35)
        scorers.cross_exposure([a])
        self.assertEqual(a["compositeScore"], 42)

    def test_partial_overlap_among_three_funds_counts_per_fund(self):
        # A shares with B and with C, B and C share nothing: A 100-40=60, B 80, C 80.
        ka, kb, kc = ["k1", "k2"], ["k1", "k3"], ["k2", "k4"]
        a, b, c = _fund("A", ka), _fund("B", kb), _fund("C", kc)
        scorers.cross_exposure([a, b, c])
        self.assertEqual(a["crossExposureScore"], 60)
        self.assertEqual(b["crossExposureScore"], 80)
        self.assertEqual(c["crossExposureScore"], 80)
        self.assertEqual(a["notes"][-1], "shares at least one signer pubkey with: ['B', 'C']")

    def test_score_floors_at_zero_when_six_or_more_others_share(self):
        # 100 - 20*6 = -20 -> 0
        funds = [_fund(f"F{i}", ["shared-key"]) for i in range(7)]
        scorers.cross_exposure(funds)
        self.assertEqual({f["crossExposureScore"] for f in funds}, {0})

    def test_single_fund_has_nothing_to_share_with(self):
        a = _fund("ZIP 271", ZIP271_KEYS)
        scorers.cross_exposure([a])
        self.assertEqual(a["crossExposureScore"], 100)
        self.assertIn("confirmed disjoint", a["notes"][-1])

    def test_degraded_result_is_left_exactly_as_score_fund_set_it(self):
        # docstring: a degraded result keeps crossExposureScore None, its notes and its composite
        # (the 4.2 unresolved-P2SH floor composite 7 = floor(0.4*5 + 0.3*16 + 0.5) = floor(7.3)).
        degraded = _fund("unresolved", ZIP271_KEYS, degraded=True, cross=None, composite=7, admin=5, multisig=16)
        scorers.cross_exposure([degraded])
        self.assertIsNone(degraded["crossExposureScore"])
        self.assertEqual(degraded["compositeScore"], 7)
        self.assertEqual(degraded["notes"], ["n0"])

    def test_degraded_neighbour_is_not_compared_even_if_it_shares_keys(self):
        # An unresolved fund's pubkeys are not a measured signer set: the healthy fund must not be
        # penalised for overlapping with it.
        healthy = _fund("healthy", ZIP271_KEYS)
        degraded = _fund("degraded", ZIP271_KEYS, degraded=True, composite=7)
        scorers.cross_exposure([healthy, degraded])
        self.assertEqual(healthy["crossExposureScore"], 100)
        self.assertIn("confirmed disjoint", healthy["notes"][-1])

    def test_neighbour_with_no_recovered_pubkeys_is_not_compared(self):
        healthy = _fund("healthy", ZIP271_KEYS)
        empty = _fund("empty", [])
        scorers.cross_exposure([healthy, empty])
        self.assertEqual(healthy["crossExposureScore"], 100)

    def test_bookkeeping_keys_are_removed_from_every_result_and_nothing_is_returned(self):
        results = [_fund("ok", ZIP271_KEYS), _fund("bad", ZCG_KEYS, degraded=True)]
        self.assertIsNone(scorers.cross_exposure(results))
        for r in results:
            self.assertNotIn("_pubkeys", r)
            self.assertNotIn("_degraded", r)

    def test_empty_list_is_a_no_op(self):
        results = []
        self.assertIsNone(scorers.cross_exposure(results))
        self.assertEqual(results, [])


class TestCrossExposureOnRealScoreFundOutput(OfflineCase):
    """Feed cross_exposure() what score_fund()'s real body produces from the published spends."""

    def setUp(self):
        super().setUp()
        self.w = World()
        self.w.install_funds(self)

    def _score_both(self):
        out = []
        for label, cfg in scorers.FUNDS.items():
            out.append(scorers.score_fund(label, cfg["address"], cfg["scanStart"], cfg["scanEnd"], cfg["window"]))
        return out

    def test_published_funds_come_out_disjoint_with_composite_32(self):
        results = self._score_both()
        scorers.cross_exposure(results)
        self.assertEqual([r["target"] for r in results], [ZIP271_ADDR, ZCG_ADDR])
        for r in results:
            self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["timelockScore"]), (50, 39, 0))
            self.assertEqual(r["crossExposureScore"], 100)
            self.assertEqual(r["compositeScore"], 32)

    def test_fund_whose_two_operators_disagree_stays_unresolved_and_is_not_compared(self):
        # ZIP 271 second operator reveals a different threshold -> score_fund degrades to the 5/16
        # floor (composite 7, crossExposure null). Its primary-host pubkeys are kept in `_pubkeys`
        # but must not be counted against the healthy fund, even if they overlap.
        self.w.scan.results[(SECOND, ZIP271_ADDR)] = _scan(
            ZIP271_ADDR, [_spend(3, 3, ZIP271_KEYS, "CHECKMULTISIG", None, 3308125, 1, 1)], 4)
        self.w.scan.results[(PRIMARY, ZCG_ADDR)] = _scan(
            ZCG_ADDR, [_spend(2, 3, ZIP271_KEYS, "CHECKMULTISIGVERIFY", ZCG_SUFFIX, 3478971, 1001, 0)], 10009)
        self.w.scan.results[(SECOND, ZCG_ADDR)] = self.w.scan.results[(PRIMARY, ZCG_ADDR)]
        results = self._score_both()
        scorers.cross_exposure(results)
        zip271, zcg = results
        self.assertEqual((zip271["adminKeyScore"], zip271["multisigScore"], zip271["compositeScore"]), (5, 16, 7))
        self.assertIsNone(zip271["crossExposureScore"])
        self.assertTrue(any("MISMATCH" in n for n in zip271["notes"]))
        self.assertFalse(any("confirmed disjoint" in n for n in zip271["notes"]))
        self.assertEqual(zcg["crossExposureScore"], 100)


# ============================================================== score_ext_zec_omft
class TestScoreExtZecOmft(OfflineCase):
    def setUp(self):
        super().setUp()
        self.w = World()
        self.w.install_ext(self)
        self.near = self.w.near

    def test_published_run_reproduces_5_18_0_and_composite_7(self):
        # scored_targets_2026-09-17.md / 09-19.md: zec.omft.near 5 / 18 / 0 / 100 / 100 -> 7.
        # Hand derivation: weakest key is the DAO Requestor group (k=1, n=3), equal k as the bare key
        # (1,1) but larger n is weaker; admin_key_score_kn(1,3) = 5, multisig max(16, min(100, 20-2)) = 18,
        # composite floor(0.4*5 + 0.3*18 + 0 + 0.5) = floor(7.9) = 7.
        r = scorers.score_ext_zec_omft()
        self.assertEqual(r["target"], "zec.omft.near")
        self.assertEqual(r["label"], "zec.omft.near (NEAR PoA bridge, ZEC)")
        self.assertEqual(r["adminKeyScore"], 5)
        self.assertEqual(r["multisigScore"], 18)
        self.assertEqual(r["timelockScore"], 0)
        self.assertEqual(r["oracleAuthorityScore"], 100)
        self.assertEqual(r["crossExposureScore"], 100)
        self.assertEqual(r["compositeScore"], 7)

    def test_off_zcash_authority_has_no_l1_cap_key(self):
        # 09-17 doc: l1CappedComposite "deliberately NOT computed" for this target.
        self.assertNotIn("l1CappedComposite", scorers.score_ext_zec_omft())

    def test_published_run_notes_show_both_paths_and_the_binding_one(self):
        notes = scorers.score_ext_zec_omft()["notes"]
        self.assertEqual(len(notes), 4)
        self.assertIn(f"omft.near acl_get_permissioned_accounts(): Role::TokenDepositer grantees = ['{BARE}', '{DAO}']", notes[0])
        self.assertIn(f"{BARE}: 1 full-access key(s) -- single-signer path, (k=1, n=1)", notes[1])
        self.assertIn(f"{DAO}: Requestor group n=3, call vote_policy threshold=1 quorum=0 -> (k=1, n=3)", notes[2])
        self.assertIn(f"weakest key by (k, -n) ordering: {DAO} at (k=1, n=3)", notes[3])

    def test_every_read_is_taken_on_both_rpc_operators(self):
        # 09-17 doc: "cross-checked against a second NEAR RPC (free.rpc.fastnear.com alongside rpc.mainnet.near.org)"
        scorers.score_ext_zec_omft()
        both = sorted([NEAR_PRIMARY, NEAR_SECOND])
        self.assertEqual(self.near.urls_for("permissioned_accounts"), both)
        self.assertEqual(self.near.urls_for("access_key_count"), both)
        self.assertEqual(self.near.urls_for("dao_policy"), both)
        self.assertEqual({c[2] for c in self.near.calls if c[0] == "permissioned_accounts"}, {"omft.near"})

    def test_operators_disagreeing_on_any_read_raises_rather_than_trusting_one(self):
        # docstring: "disagreement raises rather than trusting one source"
        cases = [
            ("permissioned_accounts", _acl([BARE])),
            ("access_key_count", [_key(1), _key(2)]),
            ("dao_policy", _policy(REQUESTORS, {"quorum": "0", "threshold": "2"})),
        ]
        for name, other in cases:
            with self.subTest(name):
                near = FakeNear()
                near.second[name] = other
                _patch(self, scorers.nr, "permissioned_accounts", near.permissioned_accounts)
                _patch(self, scorers.nr, "access_key_count", near.access_key_count)
                _patch(self, scorers.nr, "dao_policy", near.dao_policy)
                with self.assertRaises(RuntimeError) as cm:
                    scorers.score_ext_zec_omft()
                self.assertIn(f"NEAR RPC disagreement on {name}", str(cm.exception))

    def test_single_key_is_the_weakest_when_the_dao_needs_two_of_three(self):
        # DAO threshold "2" of 3 -> (2,3): admin 50, multisig max(16, 40-1) = 39. The bare key (1,1) is
        # weaker (k=1 < 2): admin 10 (single key), multisig max(16, min(100, 20-0)) = 20,
        # composite floor(0.4*10 + 0.3*20 + 0 + 0.5) = floor(10.5) = 10.
        self.near.policy[DAO] = _policy(REQUESTORS, {"quorum": "0", "threshold": "2"})
        r = scorers.score_ext_zec_omft()
        self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["compositeScore"]), (10, 20, 10))
        self.assertIn(f"weakest key by (k, -n) ordering: {BARE} at (k=1, n=1)", r["notes"][-1])

    def test_bare_account_with_two_keys_is_a_one_of_two(self):
        # Two access keys, either of which signs alone: (k=1, n=2), weaker than the DAO's (2,3) and than
        # a single key: admin 5 (k=1, n>1), multisig max(16, 20 - (2-1)) = 19, composite
        # floor(0.4*5 + 0.3*19 + 0 + 0.5) = floor(8.2) = 8.
        self.near.keys[BARE] = [_key(1), _key(2)]
        self.near.policy[DAO] = _policy(REQUESTORS, {"quorum": "0", "threshold": "2"})
        r = scorers.score_ext_zec_omft()
        self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["compositeScore"]), (5, 19, 8))
        self.assertIn("2 full-access key(s) -- single-signer path, (k=1, n=2)", r["notes"][1])

    # ---- Ratio thresholds. PROVENANCE OF THE ROUNDING RULE (read this before editing): the only
    # written statement of how a Sputnik "Ratio" [numerator, denominator] becomes a vote count k is the
    # scorer's own "FIXED 2026-09-17" comment and docstring: k = ceil(numerator * n / denominator).
    # Neither METHODOLOGY.md nor any file in chains/zcash/data states Sputnik's own rule, and the
    # Sputnik contract source (policy.rs `to_weight`) cannot be read offline in this run. The tests
    # below therefore pin THE SCORER'S OWN STATED RULE by hand arithmetic; they do not prove it is what
    # the Sputnik contract enforces. OPEN QUESTION for a reviewer with network access: if `to_weight`
    # is floor(num*n/denom)+1 ("strictly more than the ratio"), the two rules differ exactly when
    # num*n is divisible by denom (see the [1,2]-over-4 case), and the scorer would understate k by one
    # there (the conservative direction). The real observed shapes ([79,100] over 5 = 3.95) agree under
    # both rules, so no published score depends on it.
    def test_ratio_shaped_threshold_is_read_as_ceil_of_numerator_times_n_over_denominator(self):
        # Sputnik "Ratio" threshold (FIXED 2026-09-17 in scorers.py): [79,100] over a 5-member group
        # is the live shape of intents.sputnik-dao.near's council (a REAL shape). The pairing with the
        # `Requestor` role and 5 synthetic member names is INVENTED (the scorer only reads the role named
        # Requestor; the observed Requestor role has 3 members and Weight "1"). k = ceil(79*5/100) =
        # ceil(3.95) = 4. DAO-only grantees so the ratio path is the binding one: admin 65 (k>=3),
        # multisig max(16, min(100, 80-1)) = 79, composite floor(26 + 23.7 + 0 + 0.5) = 50.
        self.near.acl = _acl([DAO])
        five = [f"synthetic-member-{i}.near" for i in range(5)]
        self.near.policy[DAO] = _policy(five, {"quorum": "0", "threshold": [79, 100]})
        r = scorers.score_ext_zec_omft()
        self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["compositeScore"]), (65, 79, 50))
        self.assertIn("Requestor group n=5", r["notes"][1])
        self.assertIn("(k=4, n=5)", r["notes"][1])

    def test_ratio_rounds_up_not_down(self):
        # [1,2] over 3 members: ceil(1.5) = 2 (a strict half of 3 is not enough). (2,3): 50 / 39 -> 32.
        self.near.acl = _acl([DAO])
        self.near.policy[DAO] = _policy(REQUESTORS, {"quorum": "0", "threshold": [1, 2]})
        r = scorers.score_ext_zec_omft()
        self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["compositeScore"]), (50, 39, 32))

    def test_ratio_with_a_fraction_below_one_half_still_rounds_up_not_to_nearest(self):
        # [1,4] over 5 members: 5/4 = 1.25 -> ceil = 2 (round-to-nearest would give 1). Hypothetical
        # shape, hand derivation: (k=2, n=5): admin 50, multisig max(16, min(100, 40 - 3)) = 37,
        # composite floor(0.4*50 + 0.3*37 + 0 + 0.5) = floor(20 + 11.1 + 0.5) = floor(31.6) = 31.
        self.near.acl = _acl([DAO])
        five = [f"synthetic-member-{i}.near" for i in range(5)]
        self.near.policy[DAO] = _policy(five, {"quorum": "0", "threshold": [1, 4]})
        r = scorers.score_ext_zec_omft()
        self.assertIn("(k=2, n=5)", r["notes"][1])
        self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["compositeScore"]), (50, 37, 31))

    def test_ratio_that_divides_exactly_is_taken_at_the_quotient_per_the_scorers_stated_rule(self):
        # CHARACTERIZATION of the scorer's stated rule at an exact division (see the provenance
        # block above: NOT verified against Sputnik's contract). [1,2] over 4 members: 4/2 = 2.0 exactly,
        # ceil = 2 (a floor+1 rule would say 3). (k=2, n=4): admin 50, multisig max(16, min(100, 40 - 2))
        # = 38, composite floor(0.4*50 + 0.3*38 + 0 + 0.5) = floor(20 + 11.4 + 0.5) = floor(31.9) = 31.
        # If the rounding rule is changed after checking the contract, edit this test with the scorer.
        self.near.acl = _acl([DAO])
        four = [f"synthetic-member-{i}.near" for i in range(4)]
        self.near.policy[DAO] = _policy(four, {"quorum": "0", "threshold": [1, 2]})
        r = scorers.score_ext_zec_omft()
        self.assertIn("(k=2, n=4)", r["notes"][1])
        self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["compositeScore"]), (50, 38, 31))

    def test_unanimous_ratio_resolves_to_all_members_not_all_but_one(self):
        # [1,1] over 3 members: ceil(3*1/1) = 3 = n, a unanimous group (k may equal n, it is not
        # capped to n-1). Both the ceil rule and a floor+1-capped-at-n rule give 3, so this case does not
        # depend on the open question above. (k=3, n=3): admin 65, multisig max(16, min(100, 60 - 0)) = 60,
        # composite floor(0.4*65 + 0.3*60 + 0 + 0.5) = floor(26 + 18 + 0.5) = 44 (the published 3-of-3
        # zenZEC values, METHODOLOGY.md 4.8).
        self.near.acl = _acl([DAO])
        self.near.policy[DAO] = _policy(REQUESTORS, {"quorum": "0", "threshold": [1, 1]})
        r = scorers.score_ext_zec_omft()
        self.assertIn("(k=3, n=3)", r["notes"][1])
        self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["compositeScore"]), (65, 60, 44))

    def test_weight_string_threshold_of_zero_is_kept_as_zero_not_raised_to_one(self):
        # Sputnik Weight thresholds are decimal strings; "0" parses to k=0. Hand derivation from the 4.6
        # ladder at (k=0, n=3): admin 5 (k<2, n!=1), multisig max(16, min(100, 0 - 3)) = 16, composite
        # floor(0.4*5 + 0.3*16 + 0 + 0.5) = floor(2 + 4.8 + 0.5) = 7. (k=1 would give multisig 18.)
        # Characterization of a shape nobody observed: the scorer takes the string at face value.
        self.near.acl = _acl([DAO])
        self.near.policy[DAO] = _policy(REQUESTORS, {"quorum": "0", "threshold": "0"})
        r = scorers.score_ext_zec_omft()
        self.assertIn("threshold=0 quorum=0 -> (k=0, n=3)", r["notes"][1])
        self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["compositeScore"]), (5, 16, 7))

    def test_non_numeric_weight_string_fails_loudly_instead_of_dropping_the_path(self):
        # Characterization: a Weight threshold that is a string but not a decimal integer makes int()
        # raise ValueError, rather than resolving k=None and silently dropping the DAO path from the
        # weakest-key comparison (compare test_malformed_threshold_drops_the_dao_path... for the
        # non-string shapes, which DO drop it). score_all() turns the exception into a SKIPPED target.
        self.near.policy[DAO] = _policy(REQUESTORS, {"quorum": "0", "threshold": "abc"})
        with self.assertRaises(ValueError):
            scorers.score_ext_zec_omft()

    def test_equal_k_and_n_on_both_paths_is_a_tie_won_by_the_bare_account_listed_first(self):
        # Tie-break of the (k, -n) ordering: the bare account has 3 access keys, (k=1, n=3), the same
        # (k, n) as the DAO's 1-of-3 Requestor group. The weakest-key note attributes the tie to the FIRST
        # candidate, the bare account (its path is evaluated first, and min() keeps the first minimum).
        # Scores are identical either way (5 / 18 / 7), only the attribution differs.
        self.near.keys[BARE] = [_key(1), _key(2), _key(3)]
        r = scorers.score_ext_zec_omft()
        self.assertEqual(r["notes"][-1], f"weakest key by (k, -n) ordering: {BARE} at (k=1, n=3)")
        self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["compositeScore"]), (5, 18, 7))

    def test_only_the_first_bare_grantee_is_read_a_second_one_is_ignored(self):
        # CHARACTERIZATION of a limitation the documentation is silent about (the docstring and the 09-17
        # note describe exactly one bare grantee, bridge-mng.near): the scorer reads the access keys of
        # the FIRST non-Sputnik grantee only and never looks at a second one, and no note says so. Were
        # a second bare account to hold fewer keys or more authority it would not move the score. Pinned
        # here so a change to "consider every bare grantee" is a deliberate edit of this test.
        second = "synthetic-second-bare.near"
        self.near.acl = _acl([BARE, second, DAO])
        self.near.keys[second] = [_key(7), _key(8)]
        r = scorers.score_ext_zec_omft()
        self.assertEqual({c[2] for c in self.near.calls if c[0] == "access_key_count"}, {BARE})
        self.assertIn(f"grantees = ['{BARE}', '{second}', '{DAO}']", r["notes"][0])
        self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["compositeScore"]), (5, 18, 7))

    def test_malformed_threshold_drops_the_dao_path_and_the_bare_key_binds(self):
        # k is None -> the candidate is not appended: only the bare key (1,1) remains -> 10 / 20 / 10.
        shapes = [
            ("ratio with zero denominator", [1, 0]),
            ("three-element list", [1, 2, 3]),
            ("dict-shaped weight", {"Weight": "1"}),
            ("missing threshold", None),
        ]
        for name, threshold in shapes:
            with self.subTest(name):
                vp = {"quorum": "0"} if threshold is None else {"quorum": "0", "threshold": threshold}
                self.near.policy[DAO] = _policy(REQUESTORS, vp)
                r = scorers.score_ext_zec_omft()
                self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["compositeScore"]), (10, 20, 10))
                self.assertIn("(k=None, n=3)", r["notes"][2])
                self.assertIn(f"weakest key by (k, -n) ordering: {BARE} at (k=1, n=1)", r["notes"][-1])

    def test_wildcard_vote_policy_is_used_when_there_is_no_call_entry(self):
        # scorers.py: `vote_policy.get("call", vote_policy.get("*", {}))`
        self.near.policy[DAO] = _policy(REQUESTORS, vote_policy={"*": ONE_VOTE})
        r = scorers.score_ext_zec_omft()
        self.assertIn("(k=1, n=3)", r["notes"][2])
        self.assertEqual((r["adminKeyScore"], r["multisigScore"]), (5, 18))

    def test_no_vote_policy_at_all_leaves_threshold_unresolved(self):
        self.near.policy[DAO] = _policy(REQUESTORS, vote_policy={})
        r = scorers.score_ext_zec_omft()
        self.assertIn("threshold=None quorum=None -> (k=None, n=3)", r["notes"][2])
        self.assertEqual((r["adminKeyScore"], r["multisigScore"]), (10, 20))   # bare key binds

    def test_dao_without_a_requestor_role_is_reported_and_the_bare_key_binds(self):
        self.near.policy[DAO] = _policy(REQUESTORS, ONE_VOTE, role_name="not-requestor")
        r = scorers.score_ext_zec_omft()
        self.assertIn(f"{DAO}: no 'Requestor' role found in get_policy() this run -- could not resolve a (k,n) for this path",
                      r["notes"])
        self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["compositeScore"]), (10, 20, 10))

    def test_bare_key_only_grantee_list_scores_a_single_signer(self):
        self.near.acl = _acl([BARE])
        r = scorers.score_ext_zec_omft()
        self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["compositeScore"]), (10, 20, 10))
        self.assertEqual(self.near.urls_for("dao_policy"), [])      # no DAO grantee -> no policy read

    def test_dao_only_grantee_list_scores_the_requestor_group(self):
        self.near.acl = _acl([DAO])
        r = scorers.score_ext_zec_omft()
        self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["compositeScore"]), (5, 18, 7))
        self.assertEqual(self.near.urls_for("access_key_count"), [])   # no bare grantee -> no key read

    def test_no_resolvable_path_degrades_to_the_unresolved_floor_5_16(self):
        # Fixed 2026-09-20: the unresolved fallback used to be 20/20 (composite 14), above the
        # live-confirmed weakest real key (Requestor group 1-of-3 = 5/18, composite 7): a documented dormant
        # inversion (data/finding_2026-09-18-cross-ecosystem-unresolved-floor-inversion.md). METHODOLOGY.md 4.2
        # sets the unresolved floor of every other Zcash target at 5/16. Composite by hand from 4.6:
        # floor(0.4*5 + 0.3*16 + 0 + 0.5) = floor(7.3) = 7.
        for name, acl, policy in [
            ("empty grantee list", _acl([]), None),
            ("DAO with no Requestor role and no bare grantee", _acl([DAO]),
             _policy(REQUESTORS, ONE_VOTE, role_name="not-requestor")),
            ("DAO with malformed threshold and no bare grantee", _acl([DAO]),
             _policy(REQUESTORS, {"quorum": "0", "threshold": [1, 0]})),
        ]:
            with self.subTest(name):
                self.near.acl = acl
                if policy is not None:
                    self.near.policy[DAO] = policy
                r = scorers.score_ext_zec_omft()
                self.assertEqual((r["adminKeyScore"], r["multisigScore"]), (5, 16))
                self.assertEqual(r["compositeScore"], 7)
                self.assertIn("no TokenDepositer path resolved to a (k,n) this run -- degraded rather than guessing", r["notes"])
                self.assertFalse(any("weakest key by" in n for n in r["notes"]))

    def test_unresolved_fallback_must_not_outrank_the_confirmed_weakest_key(self):
        # The invariant behind the fix above: an unresolved read never scores above the live-confirmed weakest
        # real key (5/18, data/finding_2026-09-18-cross-ecosystem-unresolved-floor-inversion.md).
        self.near.acl = _acl([])
        r = scorers.score_ext_zec_omft()
        self.assertLessEqual(r["adminKeyScore"], 5)
        self.assertLessEqual(r["multisigScore"], 18)


# ======================================================== score_maya_asgard_vault
class TestScoreMayaAsgardVault(OfflineCase):
    def setUp(self):
        super().setUp()
        self.w = World()
        self.w.install_maya(self)

    def _score(self, vault=None, others=None):
        vault = vault or self.w.vaults[0]
        if others is None:
            others = [v for v in self.w.vaults if v["zec_address"] != vault["zec_address"]]
        return scorers.score_maya_asgard_vault(vault, others)

    def test_vault_a_reproduces_the_published_row(self):
        # scored_targets_2026-09-18.md / 09-19.md: 65 / 100 / 0 / 100 / 100 -> 56.
        # n=20 -> k=ceil(40/3)=14 (METHODOLOGY.md 3.6); admin 65 (k>=3); multisig
        # min(100, 20*14-(20-14)) = 274 -> 100; composite floor(26 + 30 + 0 + 0.5) = 56.
        r = self._score(self.w.vaults[0])
        self.assertEqual(r["target"], VAULT_A_ADDR)
        self.assertEqual(r["adminKeyScore"], 65)
        self.assertEqual(r["multisigScore"], 100)
        self.assertEqual(r["timelockScore"], 0)
        self.assertEqual(r["oracleAuthorityScore"], 100)
        self.assertEqual(r["crossExposureScore"], 100)
        self.assertEqual(r["compositeScore"], 56)
        self.assertNotIn("l1CappedComposite", r)       # "n/a (off-Zcash authority, METHODOLOGY.md 4.7)"

    def test_vault_b_reproduces_the_published_row(self):
        r = self._score(self.w.vaults[1])
        self.assertEqual(r["target"], VAULT_B_ADDR)
        self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["timelockScore"]), (65, 100, 0))
        self.assertEqual((r["oracleAuthorityScore"], r["crossExposureScore"], r["compositeScore"]), (100, 100, 56))

    def test_label_is_the_first_24_chars_of_the_real_pub_key(self):
        # 'mayapub1' (8) + 'addwnpep' (8) + 'qdgafgd6' (8) = 24 chars for vault A; '...q24t2hk5' for vault B.
        self.assertEqual(self._score(self.w.vaults[0])["label"],
                         "Maya Protocol Asgard vault mayapub1addwnpepqdgafgd6... (native ZEC custody, TSS)")
        self.assertEqual(self._score(self.w.vaults[1])["label"],
                         "Maya Protocol Asgard vault mayapub1addwnpepq24t2hk5... (native ZEC custody, TSS)")

    def test_vault_a_notes_carry_single_source_threshold_and_matching_balance(self):
        notes = self._score(self.w.vaults[0])["notes"]
        self.assertEqual(len(notes), 5)   # the 5th is the ZEC chain status note added 2026-09-20 (METHODOLOGY 4.7)
        # METHODOLOGY.md 3.6: single Mayachain source disclosed; 14-of-20 from Mayanode's own go-tss formula
        self.assertIn("SINGLE SOURCE", notes[0])
        self.assertIn("membership n=20 TSS signer pubkeys", notes[0])
        self.assertIn("required co-signers k=ceil(2n/3)=14 of n=20", notes[1])
        # METHODOLOGY.md 3.6 "Disclosed limitation": the threshold is INFERRED from Mayanode's own
        # go-tss `GetThreshold` at commit ad1072c33ca2091fe12917de2321578474e3e3eb, not read from an API
        # field. That provenance is what makes the 14-of-20 checkable, so it is part of the pinned note.
        self.assertIn("conversion.GetThreshold()", notes[1])
        self.assertIn("commit ad1072c3", notes[1])
        self.assertIn("tss_required_signers() docstring", notes[1])
        # vault A: live on-chain balance == Mayanode ledger (exact match) -> no ledger note
        self.assertEqual(notes[2], f"live on-chain balance {VAULT_A_LIVE} zat, identical on {PRIMARY} and {SECOND}")
        self.assertFalse(any("Mayanode-internal ledger" in n for n in notes))
        self.assertIn("halted=True, chain_trading_paused=True", notes[3])     # METHODOLOGY 4.7 status disclosure
        self.assertIn("confirmed DISJOINT (0 shared signer nodes)", notes[4])
        self.assertIn("(1 other(s) checked)", notes[4])

    def test_vault_b_ledger_gap_is_disclosed_as_unresolved(self):
        # METHODOLOGY.md 3.6: ledger 129,157,478,056 vs live 126,951,364,578 -> gap 2,206,113,478 zat
        # (129157478056 - 126951364578 = 2206113478), "genuinely unresolved".
        notes = self._score(self.w.vaults[1])["notes"]
        self.assertEqual(notes[2], f"live on-chain balance {VAULT_B_LIVE} zat, identical on {PRIMARY} and {SECOND}")
        ledger_note = notes[3]
        self.assertIn(f"Mayanode-internal ledger for this vault says {VAULT_B_LEDGER} zat", ledger_note)
        self.assertIn("differs from the live on-chain balance by 2206113478 zat", ledger_note)
        self.assertIn("Disclosed as genuinely unresolved, not smoothed over", ledger_note)
        self.assertIn("NOT reconciled this pass", ledger_note)
        # METHODOLOGY.md 3.6: WHY the gap is unresolved. An earlier draft attributed it to a queued outbound
        # entry (~2,206,088,478 zat); independent re-reads matched that amount to different vault keys, so
        # "the queue is live and mutates ... amount-matching against it cannot attribute a specific entry".
        # That withdrawn attribution is part of the disclosure and is pinned, not just the headline.
        self.assertIn("~2,206,088,478 zat", ledger_note)
        self.assertIn("DIFFERENT vault_pub_key values", ledger_note)
        self.assertIn("queue is live and mutates", ledger_note)
        self.assertIn("amount-matching against it is NOT a reliable way to attribute", ledger_note)
        self.assertIn("no confirmed explanation for the gap exists", ledger_note)

    def test_a_ledger_gap_is_disclosed_whatever_its_size_and_sign(self):
        # The ledger note is the disclosure of ANY disagreement between Mayanode's internal ledger and the
        # live on-chain balance; it has no magnitude threshold and no direction. The gap is printed as
        # (ledger - live), the direction of the documented observation (METHODOLOGY.md 3.6: vault B ledger
        # 129,157,478,056 minus live 126,951,364,578 = +2,206,113,478). Hand arithmetic on vault A
        # (ledger 220,970,943,152): live = ledger - 1 -> gap +1 zat; live = ledger + 1 -> gap -1 zat.
        # Hypothetical one-zat gaps (no such gap was observed on vault A, whose ledger matched exactly).
        cases = [("live one zat below the ledger", VAULT_A_LEDGER - 1, "by 1 zat"),
                 ("live one zat above the ledger", VAULT_A_LEDGER + 1, "by -1 zat")]
        for name, live, gap_text in cases:
            with self.subTest(name):
                self.w.balances.set_both(VAULT_A_ADDR, live)
                notes = self._score(self.w.vaults[0])["notes"]
                self.assertEqual(notes[2], f"live on-chain balance {live} zat, identical on {PRIMARY} and {SECOND}")
                ledger_notes = [n for n in notes if "Mayanode-internal ledger" in n]
                self.assertEqual(len(ledger_notes), 1)
                self.assertIn(f"ledger for this vault says {VAULT_A_LEDGER} zat", ledger_notes[0])
                self.assertIn(f"differs from the live on-chain balance {gap_text}", ledger_notes[0])

    def test_both_operators_are_asked_for_this_vaults_balance(self):
        self._score(self.w.vaults[0])
        self.assertEqual(self.w.balances.calls, [(PRIMARY, VAULT_A_ADDR), (SECOND, VAULT_A_ADDR)])

    def test_halted_status_is_disclosed_in_the_notes_without_changing_any_score(self):
        # Fixed 2026-09-20. METHODOLOGY.md 4.7, last row: "Halted/paused status | Disclosed in the
        # scorer's notes (via `/mayachain/inbound_addresses`), not folded into any of the five dimensions".
        # METHODOLOGY.md 3.6: chain ZEC reads `"halted": true, "chain_trading_paused": true`. The inbound_addresses
        # shape (a list of per-chain dicts with `chain`/`halted`/`chain_trading_paused`) follows the fields 3.6 quotes.
        _patch(self, scorers.mr, "inbound_addresses",
               lambda: [{"chain": "ZEC", "halted": True, "chain_trading_paused": True}])
        r = self._score(self.w.vaults[0])
        self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["crossExposureScore"], r["compositeScore"]),
                         (65, 100, 100, 56))                      # never folded into a dimension
        self.assertTrue(any("halted=True" in n and "chain_trading_paused=True" in n for n in r["notes"]))

    def test_a_running_zec_chain_is_reported_as_running_not_as_halted(self):
        _patch(self, scorers.mr, "inbound_addresses",
               lambda: [{"chain": "ZEC", "halted": False, "chain_trading_paused": False}])
        r = self._score(self.w.vaults[0])
        self.assertTrue(any("halted=False" in n and "chain_trading_paused=False" in n for n in r["notes"]))
        self.assertFalse(any("halted=True" in n for n in r["notes"]))
        self.assertEqual(r["compositeScore"], 56)

    def test_an_unreadable_or_missing_chain_status_is_disclosed_and_never_fatal(self):
        def boom():
            raise RuntimeError("mayanode down")
        for name, fn in [("read fails", boom), ("ZEC not listed", lambda: [{"chain": "BTC", "halted": False}]),
                         ("empty answer", lambda: None)]:
            with self.subTest(name):
                _patch(self, scorers.mr, "inbound_addresses", fn)
                r = self._score(self.w.vaults[0])
                self.assertTrue(any("unread" in n for n in r["notes"]))
                self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["compositeScore"]), (65, 100, 56))

    def test_balance_mismatch_between_operators_is_disclosed_and_changes_no_score(self):
        # 4.7: the balance is "not itself a scoring dimension". Balance figures below are synthetic
        # (a one-zat disagreement); the scores must stay the published 65/100/0/100/100/56.
        self.w.balances.table[(SECOND, VAULT_A_ADDR)] = VAULT_A_LIVE - 1
        r = self._score(self.w.vaults[0])
        notes = r["notes"]
        self.assertTrue(any(f"BALANCE MISMATCH between {PRIMARY} ({VAULT_A_LIVE} zat) and {SECOND} ({VAULT_A_LIVE - 1} zat)" in n
                            for n in notes))
        self.assertFalse(any(n.startswith("live on-chain balance") for n in notes))
        self.assertFalse(any("Mayanode-internal ledger" in n for n in notes))
        self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["crossExposureScore"], r["compositeScore"]),
                         (65, 100, 100, 56))

    def test_zero_live_balance_is_a_real_balance_not_a_missing_read(self):
        # scored_targets_2026-09-19.md "Bug fixed this pass": lightwalletd omits valueZat when it is exactly 0,
        # a legitimate zero. Both operators say 0 while the ledger still says 129157478056 zat.
        self.w.balances.set_both(VAULT_B_ADDR, 0)
        notes = self._score(self.w.vaults[1])["notes"]
        self.assertTrue(any(n.startswith(f"live on-chain balance 0 zat, identical on {PRIMARY} and {SECOND}") for n in notes))
        self.assertTrue(any(f"differs from the live on-chain balance by {VAULT_B_LEDGER} zat" in n for n in notes))
        self.assertFalse(any("BALANCE MISMATCH" in n for n in notes))

    def test_shared_signer_costs_20_per_vault_and_names_the_other_vault(self):
        # 4.7: max(0, 100 - 20 * count of other active XVAULT targets sharing >= 1 TSS member pubkey)
        a, b = self.w.vaults
        b["membership"][3] = a["membership"][7]
        r = self._score(a, [b])
        self.assertEqual(r["crossExposureScore"], 80)
        self.assertIn(f"shares at least one TSS signer node with: ['{VAULT_B_ADDR}']", r["notes"][-1])
        self.assertEqual(r["compositeScore"], 56)      # crossExposure is not a composite input

    def test_penalty_counts_other_vaults_not_shared_members(self):
        # METHODOLOGY.md 4.7: "max(0, 100 - 20 * count of other tracked active XVAULT targets sharing >= 1
        # TSS member pubkey)". Two shared members with the SAME other vault are still ONE other vault:
        # 100 - 20*1 = 80 (a per-member count would give 100 - 20*2 = 60). Hypothetical overlap: the two
        # real vaults share no member (METHODOLOGY.md 3.6).
        a, b = self.w.vaults
        b["membership"][3] = a["membership"][7]
        b["membership"][4] = a["membership"][8]
        r = self._score(a, [b])
        self.assertEqual(r["crossExposureScore"], 80)
        self.assertEqual(r["notes"][-1], f"shares at least one TSS signer node with: ['{VAULT_B_ADDR}']")

    def test_membership_count_is_the_length_of_the_membership_list(self):
        # METHODOLOGY.md 4.7: "n = the vault's own live `membership` count"; 3.6: the go-tss call site uses
        # `len(localStateItem.ParticipantKeys)`, a plain length. Contract pin: a membership list that repeats
        # one entry (never observed: the 20 real members are distinct, 3.6) still counts its 20 entries,
        # so n=20 and k=ceil(40/3)=14, not the 19 distinct entries (k=ceil(38/3)=13).
        members = _members("dup", 19)
        vault = dict(self.w.vaults[0], membership=members + [members[0]])
        r = self._score(vault, [])
        self.assertIn("membership n=20 TSS signer pubkeys", r["notes"][0])
        self.assertIn("required co-signers k=ceil(2n/3)=14 of n=20", r["notes"][1])

    def test_sharing_with_six_or_more_vaults_floors_at_zero(self):
        # 100 - 20*6 = -20 -> 0
        a = self.w.vaults[0]
        others = []
        for i in range(6):
            o = {"pub_key": f"synthetic-pub-{i}", "ledger_amount_zat": 1, "zec_address": f"t1synthetic{i}",
                 "membership": [a["membership"][i]]}
            others.append(o)
        r = self._score(a, others)
        self.assertEqual(r["crossExposureScore"], 0)
        self.assertEqual(r["notes"][-1], f"shares at least one TSS signer node with: {[o['zec_address'] for o in others]}")

    def test_the_vault_itself_in_other_vaults_is_not_counted_as_sharing(self):
        # `ov["zec_address"] != addr` guard: a vault trivially shares every member with itself.
        a = self.w.vaults[0]
        r = self._score(a, [a])
        self.assertEqual(r["crossExposureScore"], 100)
        self.assertIn("confirmed DISJOINT (0 shared signer nodes)", r["notes"][-1])
        self.assertIn("(1 other(s) checked)", r["notes"][-1])      # len(other_vaults) is reported as passed in

    def test_no_other_vaults_is_trivially_disjoint(self):
        r = self._score(self.w.vaults[0], [])
        self.assertEqual(r["crossExposureScore"], 100)
        self.assertIn("(0 other(s) checked)", r["notes"][-1])

    def test_membership_size_drives_the_threshold_ladder(self):
        # k = ceil(2n/3) (METHODOLOGY.md 3.6), then the shared bare-(k,n) ladder:
        #   n=3  -> k=2: admin 50, multisig max(16, 40-1) = 39, composite floor(20 + 11.7 + 0.5) = 32
        #           (the same as the published 2-of-3 funds)
        #   n=4  -> k=3: admin 65, multisig max(16, 60-1) = 59, composite floor(26 + 17.7 + 0.5) = 44
        #   n=1  -> k=1: admin 10 (single key), multisig 20, composite floor(4 + 6 + 0.5) = 10
        cases = [(3, 2, 50, 39, 32), (4, 3, 65, 59, 44), (1, 1, 10, 20, 10)]
        for n, k, admin, multisig, composite in cases:
            with self.subTest(n=n):
                vault = dict(self.w.vaults[0], membership=_members("n", n))
                r = self._score(vault, [])
                self.assertIn(f"required co-signers k=ceil(2n/3)={k} of n={n}", r["notes"][1])
                self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["compositeScore"]), (admin, multisig, composite))

    def test_empty_membership_lands_on_the_bottom_of_the_ladder_by_the_written_formula(self):
        # HAND DERIVATION AT A FORMULA BOUNDARY, not an observation (no empty membership was ever read;
        # METHODOLOGY.md 3.6 observed n=20 on both vaults). n=0 -> k=ceil(0)=0 -> admin 5 (k<2, n!=1),
        # multisig max(16, min(100, 0 - 0)) = 16 (4.6 ladder and its floor): the same 5/16 pair 4.2 gives an
        # unresolved P2SH; composite floor(0.4*5 + 0.3*16 + 0 + 0.5) = floor(2 + 4.8 + 0.5) = 7.
        # Only the arithmetic is pinned. The documentation does not say whether an empty membership should
        # ALSO be flagged as unresolved the way 4.2 flags an unresolved P2SH (the notes today only report
        # "membership n=0"): that is raised as a finding, not asserted here.
        vault = dict(self.w.vaults[0], membership=[])
        r = self._score(vault, [])
        self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["compositeScore"]), (5, 16, 7))
        self.assertIn("membership n=0", r["notes"][0])


# ==================================================================== score_all

def _by_target(results):
    return {r["target"]: r for r in results}


def _score_all_including_retired(*args):
    """score_all() over the FULL set the 2026-09-19 anchors contain: the six live targets plus the retired one."""
    return scorers.score_all(*args, include_retired=True)


class TestScoreAllPublishedRun(OfflineCase):
    """score_all() with every real scorer body running over the 2026-09-19 reader fakes."""

    def setUp(self):
        super().setUp()
        self.w = World()
        self.w.install_all(self)

    def test_reproduces_the_seven_published_rows(self):
        results, out = _capture(_score_all_including_retired)
        self.assertEqual(out, "")                                     # nothing skipped
        self.assertEqual(len(results), 7)
        for r, (target, admin, multisig, timelock, oracle, cross, composite, capped) in zip(results, PUBLISHED_2026_09_19):
            with self.subTest(target):
                self.assertEqual(r["target"], target)
                self.assertEqual(
                    (r["adminKeyScore"], r["multisigScore"], r["timelockScore"], r["oracleAuthorityScore"],
                     r["crossExposureScore"], r["compositeScore"]),
                    (admin, multisig, timelock, oracle, cross, composite))
                if capped is None:
                    self.assertNotIn("l1CappedComposite", r)
                else:
                    self.assertEqual(r["l1CappedComposite"], capped)

    def test_result_order_is_l1_funds_ext_maya_vaults_zenzec(self):
        results, _ = _capture(_score_all_including_retired)
        self.assertEqual([r["target"] for r in results],
                         [row[0] for row in PUBLISHED_2026_09_19])

    def test_fund_labels_are_the_published_names(self):
        results, _ = _capture(_score_all_including_retired)
        by = _by_target(results)
        self.assertEqual(by[ZIP271_ADDR]["label"], "ZIP 271 one-time lockbox disbursement")
        self.assertEqual(by[ZCG_ADDR]["label"], "ZCG funding stream (FS_FPF_ZCG_H3)")

    def test_no_internal_bookkeeping_key_leaks_into_the_published_results(self):
        results, _ = _capture(_score_all_including_retired)
        for r in results:
            self.assertNotIn("_pubkeys", r)
            self.assertNotIn("_degraded", r)

    def test_funds_are_scanned_with_their_configured_windows_on_both_operators(self):
        # METHODOLOGY.md 3.2 gives the START of the ZIP 271 range (3,146,400, "since") and the ZCG range
        # 3,475,800 to 3,485,800. The ZIP 271 END (3,486,400) and the two chunk windows (50000 and 1000)
        # appear only in the reproduction commands, METHODOLOGY.md section 6 lines 609
        # (`p2sh_spends.py zec.rocks:443 t3ev37... 3146400 3486400 50000`) and 612
        # (`p2sh_spends.py zec.rocks:443 t3cFfPt1... 3475800 3485800 1000`). Note METHODOLOGY.md 7.3's ZCG
        # "control" row quotes a DIFFERENT window (3,476,771-3,486,770) from a separate independent
        # re-derivation; the scorer's configured window is the one in 3.2 and section 6.
        _capture(_score_all_including_retired)
        calls = self.w.scan.calls
        self.assertEqual(len(calls), 4)
        self.assertEqual({(c[1], c[2], c[3], c[4]) for c in calls if c[1] == ZIP271_ADDR}, {(ZIP271_ADDR, 3146400, 3486400, 50000)})
        self.assertEqual({(c[1], c[2], c[3], c[4]) for c in calls if c[1] == ZCG_ADDR}, {(ZCG_ADDR, 3475800, 3485800, 1000)})
        self.assertEqual({c[0] for c in calls}, {PRIMARY, SECOND})

    def test_each_fund_gets_only_its_own_static_note_appended(self):
        # METHODOLOGY.md 8 (the two "Resolved 2026-09-19" bullets, lines 684-722): the FPF / ZIP 1015 /
        # "key holders NOT named" facts belong to the ZCG fund t3cFfPt1..., the ZIP 1016 coinholder-vote
        # facts to t3ev37...; conflating the two funds' key holders was a caught research error. The
        # expected content is pinned from the DOCUMENT (fragments below), not rebuilt from the scorer's own
        # FUND_STATIC_NOTES constant, so a wrong or swapped note fails.
        by = _by_target(_capture(_score_all_including_retired)[0])
        zcg_notes, zip271_notes = by[ZCG_ADDR]["notes"], by[ZIP271_ADDR]["notes"]
        # ZCG: administering entity named (ZIP 1015 / ZIP 1016 / FPF's Q2 2026 report, section 8 lines 684-695) ...
        zcg_facts = ["Financial Privacy Foundation", "Cayman Islands", "Administering entity per ZIP 1015",
                     "ZIP 1016 line 130", "fpf-q2-2026-report, released 2026-07-08",
                     # ... and the honest gap: the individual key holders are not named anywhere (lines 695-704),
                     # with the explicit warning not to conflate them with ZIP 271's named organisations
                     "NOT named in any primary source",
                     "Zcash Foundation, Electric Coin Company, Shielded Labs"]
        # ZIP 271: real coinholder votes HAVE occurred (section 8 lines 705-722)
        zip271_facts = ["ZIP-1016-governed coinholder votes", "inaugural vote closed 2025-11-26",
                        "9 proposals, 5 approved", "more than 1,000,000 ZEC voted", "420,000 ZEC threshold",
                        "postponed to Q3 2026", "Ironwood upgrade"]
        for fact in zcg_facts:
            with self.subTest(fund="ZCG", fact=fact):
                self.assertEqual(sum(fact in n for n in zcg_notes), 1)
                self.assertFalse(any(fact in n for n in zip271_notes))
        for fact in zip271_facts:
            with self.subTest(fund="ZIP 271", fact=fact):
                self.assertEqual(sum(fact in n for n in zip271_notes), 1)
                self.assertFalse(any(fact in n for n in zcg_notes))
        # exactly two static notes on ZCG (entity named / holders not named), one on ZIP 271 (votes occurred)
        self.assertEqual(len(scorers.FUND_STATIC_NOTES[ZCG_ADDR]), 2)
        self.assertEqual(len(scorers.FUND_STATIC_NOTES[ZIP271_ADDR]), 1)
        self.assertEqual(sorted(scorers.FUND_STATIC_NOTES), sorted([ZCG_ADDR, ZIP271_ADDR]))
        for target in (L1_KEY, "zec.omft.near", VAULT_A_ADDR, VAULT_B_ADDR, ZENZEC_KEYRING):
            self.assertFalse(any("ZIP-1016-governed" in n or "Administering entity" in n for n in by[target]["notes"]))

    def test_zenzec_target_is_the_frozen_snapshot_of_the_published_keyring(self):
        # METHODOLOGY.md 4.8.1: "It is `frozen` while its source tip equals the recorded frozen height"
        # (9,534,552, block time 2026-08-10T23:19:52Z) and "the scorer returns `status` and `asOf`". The
        # documentation pins the word "frozen" and the asOf timestamp; the EXACT status spelling
        # "frozen_snapshot" is code-defined (only its sibling `status_review_needed` is spelled out in
        # 4.8.1), so it is asserted as the current spelling and the documented word is asserted beside it.
        by = _by_target(_capture(_score_all_including_retired)[0])
        z = by[ZENZEC_KEYRING]
        self.assertIn("frozen", z["status"])
        self.assertEqual(z["status"], "frozen_snapshot")
        self.assertEqual(z["asOf"], "2026-08-10T23:19:52Z")
        self.assertIn("FROZEN SNAPSHOT", z["notes"][0])

    def test_argument_is_ignored_and_the_result_is_unchanged(self):
        # signature matches every other ecosystem's score_all(url) for the update_scores.py harness
        without, _ = _capture(_score_all_including_retired)
        with_arg, _ = _capture(_score_all_including_retired, "https://not-used.invalid")
        self.assertEqual([(r["target"], r["compositeScore"]) for r in with_arg],
                         [(r["target"], r["compositeScore"]) for r in without])


class TestScoreAllRetiredTarget(OfflineCase):
    """Zcash target 7, the Zenrock zenZEC keyring, was retired from the live set on 2026-09-20
    (chains/zcash/scripts/zcash_retired_targets.py). The default run no longer returns it and no longer reads
    zrchain for it; a run with include_retired=True still does, because the anchors made before the retirement
    contain it."""

    def setUp(self):
        super().setUp()
        self.w = World()
        self.w.install_all(self)

    def test_the_default_run_is_the_six_live_rows_without_the_retired_target(self):
        results, out = _capture(scorers.score_all)
        self.assertEqual(out, "")
        self.assertEqual([r["target"] for r in results], [row[0] for row in PUBLISHED_2026_09_19 if row[0] != ZENZEC_KEYRING])
        self.assertEqual(len(results), 6)

    def test_the_default_run_does_not_touch_zrchain_at_all(self):
        # Even a failing zrchain read must not show up: the retired target is not attempted, so no SKIPPED line.
        self.w.zr_error = RuntimeError("zrchain node unreachable")
        results, out = _capture(scorers.score_all)
        self.assertEqual(len(results), 6)
        self.assertNotIn("zenZEC", out)
        self.assertNotIn("SKIPPED", out)

    def test_include_retired_returns_the_seven_rows_the_anchors_contain_with_the_retired_one_last(self):
        results, out = _capture(_score_all_including_retired)
        self.assertEqual(out, "")
        self.assertEqual([r["target"] for r in results], [row[0] for row in PUBLISHED_2026_09_19])
        self.assertEqual(results[-1]["target"], ZENZEC_KEYRING)

    def test_the_six_live_rows_are_identical_with_and_without_the_retired_target(self):
        live, _ = _capture(scorers.score_all)
        full, _ = _capture(_score_all_including_retired)
        strip = lambda rs: [(r["target"], r["adminKeyScore"], r["multisigScore"], r["timelockScore"], r["oracleAuthorityScore"],
                             r["crossExposureScore"], r["compositeScore"]) for r in rs]
        self.assertEqual(strip(live), strip(full[:6]))

    def test_include_retired_accepts_a_set_of_ids_and_ignores_ids_that_are_not_retired(self):
        results, _ = _capture(lambda: scorers.score_all(include_retired={ZENZEC_KEYRING}))
        self.assertEqual(len(results), 7)
        results, _ = _capture(lambda: scorers.score_all(include_retired={"t1NotARetiredTarget"}))
        self.assertEqual(len(results), 6)
        self.assertNotIn(ZENZEC_KEYRING, [r["target"] for r in results])
        results, _ = _capture(lambda: scorers.score_all(include_retired=set()))
        self.assertEqual(len(results), 6)

    def test_the_registry_is_the_single_switch_a_target_removed_from_it_is_live_again(self):
        from unittest import mock as _mock
        with _mock.patch.dict(scorers.RETIRED_TARGETS, clear=True):
            results, out = _capture(scorers.score_all)
        self.assertEqual(out, "")
        self.assertEqual([r["target"] for r in results], [row[0] for row in PUBLISHED_2026_09_19])
        self.assertEqual(len(results), 7)

    def test_the_registry_of_retired_targets_names_the_zenzec_keyring_with_its_documents(self):
        from zcash_retired_targets import RETIRED_TARGETS
        self.assertEqual(sorted(RETIRED_TARGETS), [ZENZEC_KEYRING])
        entry = RETIRED_TARGETS[ZENZEC_KEYRING]
        self.assertEqual(entry["retired"], "2026-09-20")
        self.assertTrue(entry["status_note"].endswith("zenzec_status_2026-09-20.md"))
        self.assertTrue(entry["legacy_snapshot"].endswith("legacy_snapshot_zenzec_keyring_2026-09-20.json"))
        self.assertIs(scorers.RETIRED_TARGETS, RETIRED_TARGETS)


class TestScoreAllFailureIsolation(OfflineCase):
    """One target failing must skip only that target (the project's "SKIPPED <target>" convention)."""

    def setUp(self):
        super().setUp()
        self.w = World()
        self.w.install_all(self)

    def _run(self):
        return _capture(_score_all_including_retired)

    def test_l1_failure_skips_l1_and_nulls_every_funds_l1_cap(self):
        self.w.lightd.fail_hosts = {LINEAGE_HOST: RuntimeError("lightwalletd unreachable")}
        results, out = self._run()
        by = _by_target(results)
        self.assertNotIn(L1_KEY, by)
        self.assertEqual(len(results), 6)
        self.assertIn("score_all(): SKIPPED Zcash L1 this run -- RuntimeError: lightwalletd unreachable", out)
        for addr in (ZIP271_ADDR, ZCG_ADDR):
            self.assertIsNone(by[addr]["l1CappedComposite"])
            self.assertEqual(by[addr]["notes"][-1], "l1CappedComposite not computed this run -- Zcash L1 score unavailable")
            self.assertEqual(by[addr]["compositeScore"], 32)         # the fund's own score is unaffected

    def test_unreadable_l1_tip_is_skipped_not_raised(self):
        self.w.lightd.omit_tip_for = {PRIMARY}
        results, out = self._run()
        self.assertNotIn(L1_KEY, _by_target(results))
        self.assertIn("score_all(): SKIPPED Zcash L1 this run", out)

    def test_a_failing_fund_is_skipped_and_the_other_is_still_cross_checked_and_capped(self):
        self.w.scan.results[(PRIMARY, ZCG_ADDR)] = RuntimeError("lightwalletd down")
        results, out = self._run()
        by = _by_target(results)
        self.assertNotIn(ZCG_ADDR, by)
        self.assertEqual(len(results), 6)
        self.assertIn("score_all(): SKIPPED ZCG funding stream (FS_FPF_ZCG_H3) this run -- RuntimeError: lightwalletd down", out)
        z = by[ZIP271_ADDR]
        self.assertEqual((z["crossExposureScore"], z["compositeScore"], z["l1CappedComposite"]), (100, 32, 32))
        self.assertTrue(any("confirmed disjoint" in n for n in z["notes"]))

    def test_both_funds_failing_still_returns_the_other_targets(self):
        for addr in (ZIP271_ADDR, ZCG_ADDR):
            self.w.scan.results[(PRIMARY, addr)] = RuntimeError("lightwalletd down")
        results, out = self._run()
        self.assertEqual([r["target"] for r in results],
                         [L1_KEY, "zec.omft.near", VAULT_A_ADDR, VAULT_B_ADDR, ZENZEC_KEYRING])
        self.assertEqual(out.count("SKIPPED"), 2)

    def test_degraded_fund_keeps_its_unresolved_floor_and_is_capped_at_it(self):
        # The primary operator finds no recognised spend for ZIP 271 -> METHODOLOGY.md 4.2 unresolved
        # floor 5/16, composite 7 (floor(0.4*5 + 0.3*16 + 0.5) = floor(7.3)), crossExposure null,
        # l1CappedComposite = min(7, L1's 34) = 7.
        self.w.scan.results[(PRIMARY, ZIP271_ADDR)] = _scan(ZIP271_ADDR, [], 0)
        results, _ = self._run()
        z = _by_target(results)[ZIP271_ADDR]
        self.assertEqual((z["adminKeyScore"], z["multisigScore"], z["compositeScore"]), (5, 16, 7))
        self.assertIsNone(z["crossExposureScore"])
        self.assertEqual(z["l1CappedComposite"], 7)
        self.assertTrue(any("threshold UNRESOLVED" in n for n in z["notes"]))

    def test_fund_stronger_than_the_l1_is_capped_to_the_l1_composite(self):
        # 4.6: l1CappedComposite = min(compositeScore, L1 compositeScore). A hypothetical 3-of-3 ZCG
        # script: admin 65, multisig max(16, 60-0) = 60, composite floor(26 + 18 + 0.5) = 44 > L1's 34.
        spends = [_spend(3, 3, ZCG_KEYS, "CHECKMULTISIGVERIFY", ZCG_SUFFIX, 3478971, 1001, 0)]
        for host in (PRIMARY, SECOND):
            self.w.scan.results[(host, ZCG_ADDR)] = _scan(ZCG_ADDR, spends, 10009)
        z = _by_target(self._run()[0])[ZCG_ADDR]
        self.assertEqual((z["adminKeyScore"], z["multisigScore"], z["compositeScore"]), (65, 60, 44))
        self.assertEqual(z["l1CappedComposite"], 34)

    def test_ext_failure_from_operator_disagreement_skips_only_ext(self):
        self.w.near.second["dao_policy"] = _policy(REQUESTORS, {"quorum": "0", "threshold": "2"})
        results, out = self._run()
        self.assertNotIn("zec.omft.near", _by_target(results))
        self.assertEqual(len(results), 6)
        self.assertIn("score_all(): SKIPPED zec.omft.near this run -- RuntimeError: NEAR RPC disagreement on dao_policy", out)

    def test_maya_read_failure_skips_every_vault_but_nothing_else(self):
        self.w.maya_error = RuntimeError("Mayanode REST call failed after retries")
        results, out = self._run()
        self.assertEqual([r["target"] for r in results],
                         [L1_KEY, ZIP271_ADDR, ZCG_ADDR, "zec.omft.near", ZENZEC_KEYRING])
        self.assertIn("score_all(): SKIPPED Maya Protocol Asgard vaults this run -- RuntimeError: Mayanode REST call failed", out)

    def test_one_vault_failing_skips_only_that_vault(self):
        self.w.balances.table[(PRIMARY, VAULT_A_ADDR)] = RuntimeError("lightwalletd down")
        results, out = self._run()
        by = _by_target(results)
        self.assertNotIn(VAULT_A_ADDR, by)
        self.assertIn(VAULT_B_ADDR, by)
        self.assertEqual(len(results), 6)
        self.assertIn(f"score_all(): SKIPPED Maya vault {VAULT_A_ADDR} this run -- RuntimeError: lightwalletd down", out)
        # vault B is still compared against the OTHER active vault (the list comes from the vault
        # read, not from which scorings succeeded)
        self.assertIn("(1 other(s) checked)", by[VAULT_B_ADDR]["notes"][-1])

    def test_each_vault_is_scored_against_the_other_vaults_only(self):
        seen = []
        orig = scorers.score_maya_asgard_vault

        def spy(vault, other_vaults):
            seen.append((vault["zec_address"], [o["zec_address"] for o in other_vaults]))
            return orig(vault, other_vaults)
        _patch(self, scorers, "score_maya_asgard_vault", spy)
        c = {"pub_key": "synthetic-pub-c", "ledger_amount_zat": 5, "zec_address": "t1syntheticVaultC", "membership": _members("c")}
        self.w.vaults.append(c)
        self.w.balances.set_both("t1syntheticVaultC", 5)
        self._run()
        self.assertEqual(seen, [
            (VAULT_A_ADDR, [VAULT_B_ADDR, "t1syntheticVaultC"]),
            (VAULT_B_ADDR, [VAULT_A_ADDR, "t1syntheticVaultC"]),
            ("t1syntheticVaultC", [VAULT_A_ADDR, VAULT_B_ADDR]),
        ])

    def test_zenzec_failure_skips_only_zenzec(self):
        self.w.zr_error = RuntimeError("zrchain node unreachable")
        results, out = self._run()
        self.assertEqual(len(results), 6)
        self.assertNotIn(ZENZEC_KEYRING, _by_target(results))
        self.assertIn("score_all(): SKIPPED Zenrock zenZEC MPC keyring this run -- RuntimeError: zrchain node unreachable", out)

    def test_every_target_failing_returns_an_empty_list_instead_of_raising(self):
        self.w.lightd.fail_hosts = {LINEAGE_HOST: RuntimeError("down")}
        for addr in (ZIP271_ADDR, ZCG_ADDR):
            self.w.scan.results[(PRIMARY, addr)] = RuntimeError("down")
        self.w.near.second["permissioned_accounts"] = _acl([])
        self.w.maya_error = RuntimeError("down")
        self.w.zr_error = RuntimeError("down")
        results, out = self._run()
        self.assertEqual(results, [])
        self.assertEqual(out.count("SKIPPED"), 6)      # L1, 2 funds, EXT, Maya vaults, zenZEC


if __name__ == "__main__":
    unittest.main()
