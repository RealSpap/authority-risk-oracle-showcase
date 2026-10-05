"""
Unit tests that execute the REAL bodies of four functions in
chains/base-ecosystem/scorers.py which no other unit test reached (measured
with line coverage before this file existed; statements NOT run / total):

    score_moonwell_comptroller_base      25/26   (lines 690-746)
    _uniswap_direct_forwarder_score      23/24   (lines 615-658)
    score_aerodrome_slipstream_clfactory 20/21   (lines 565-612)
    _apply_intra_base_overlap             9/10   (lines 749-769)

Until now they were only checked by live runs against real chains. Here the
chain reads are patched (the four reader functions plus get_w3 that scorers.py
imports into its OWN namespace are replaced -- the imported names, never the
transport), so nothing touches the network, a key file or a transaction.

FIXTURE PROVENANCE. Every expected value below comes from one of:
  * a documented real observation / published score, cited next to the fixture
    with the file and section, or
  * an arithmetic derivation done by hand from the written formulas in
    METHODOLOGY.md ("Aggregation": composite = floor(0.4*adminKey +
    0.3*multisig + 0.3*timelock + 0.5); "multisigScore": min(100, threshold*15
    + max(0, owners-threshold)*5); "crossExposureScore": -20 per shared group).
No expected value was obtained by running the function under test.

Sources cited by short name in the comments:
  [MAINT]    chains/base-ecosystem/data/scored_targets_2026-09-19-maintenance.md
  [READBACK] chains/base-ecosystem/data/oracle_readback_2026-09-19.csv
             (getScore() read back on Base Sepolia after tx 0xc412f6dc...14fa1)
  [DEPLOY]   chains/base-ecosystem/deploy/README.md, "Maintenance run
             2026-09-19 -- 9 tracked targets" table
  [SCOUT]    chains/base-ecosystem/data/scouted_targets_2026-09-16.md
  [AERO]     chains/base-ecosystem/data/finding_2026-09-18-aerodrome-voter-governor-identity.md
  [MORPHO]   data/finding_2026-09-19-base-morpho-blue-robinhood-overlap.md
  [AAVE]     data/finding_2026-09-17-cross-ecosystem-aave-guardian-overlap.md
  [METH]     METHODOLOGY.md

WHAT IS, AND IS NOT, INDEPENDENTLY DOCUMENTED (checked by TestFixtureProvenance,
which reads the cited documents, so a citation below cannot silently rot):
  * Only the COUNTS (threshold, owner count) of the Aerodrome, Aerodrome-council
    and Moonwell-guardian Safes are documented observations; their individual
    owner addresses are not written down in the repo, so those owner lists are
    SYNTHETIC, distinct, valid addresses. Any "disjoint" / "shared" relation
    between synthetic lists holds BY CONSTRUCTION, not by observation.
  * The Morpho Blue owner list is the real 9-address list printed in full in
    [MORPHO]. The Aave guardian owners are documented only by their 8-hex
    prefixes in [AAVE]; the full addresses are the snapshot copied from
    score_aave_v3_base and are used only to reproduce Aave's published cross 80.
  * KNOWN LIMIT -- the Moonwell trusted sender. The docs print only
    0x8769b70a...5838. The full 20 bytes exist in the repo only in the scorer
    under test (and in its sibling test), so SENDER below is a COPY of the
    scorer's own comparison constant: prefix and suffix are tied to [MAINT] by
    TestFixtureProvenance, the middle 16 hex digits could only be checked against
    moonwell-fi's chains/1.json, which needs the network and is out of scope.
  * The prose of the notes is a GOLDEN MASTER of the scorers' current wording (a
    change detector for deletions / rewordings). The load-bearing facts inside it
    (addresses, Safe sizes, delays, roles) are the documented observations above;
    the sentences around them are not documented anywhere and cannot be wrong
    independently of the code.
  * Read ORDER is deliberately not pinned where no document fixes it: reads are
    compared as a multiset, plus the dependency order that is forced by the data
    (a Safe cannot be read before the address that owns it is known).

KNOWN-EQUIVALENT MUTATIONS (no input can make them change any output, so no test
can or should kill them): swapping the multisig/timelock arguments of _composite
(both weigh 0.3); dropping bool(admin) from Moonwell's chain_ok (admin falsy means
no sender read, so eth_senders == [] never equals [expected]); 'delay and delay > 0'
-> 'delay' (uint256); int() truncation in Moonwell's composite (its only reachable
raw composites 71.0 / 56.0 / 42.0 are integral); dropping 'slot1 and' from
Uniswap's l1_ok (slot1 falsy keeps l1_delay None); dropping .lower() on the
predeploy (0x4200...0007 has no hex letters); Slipstream '(50 if threshold == 2
else 10)' -> 'threshold >= 2' (the >= 3 branch already consumed the rest);
a min(90, ...) cap after the -20 deduction (the result is <= 80 already).

Run from the repo root:
    ARO_ZCASH_TESTNET_KEY_FILE=/nonexistent python3 -m unittest scripts.lib.tests.test_base_scorer_bodies -v
"""
import csv
import importlib.util
import os
import sys
import unittest

from web3 import Web3 as RealWeb3

REPO_ROOT = os.path.join(os.path.dirname(__file__), "..", "..", "..")


def _load_module(unique_name, relative_path):
    file_path = os.path.abspath(os.path.join(REPO_ROOT, relative_path))
    mod_dir = os.path.dirname(file_path)
    if mod_dir not in sys.path:
        sys.path.insert(0, mod_dir)
    spec = importlib.util.spec_from_file_location(unique_name, file_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[unique_name] = mod
    spec.loader.exec_module(mod)
    return mod


sys.path.insert(0, os.path.join(REPO_ROOT, "scripts", "lib"))
scorers = _load_module("aro_test_base_scorer_bodies_scorers", "chains/base-ecosystem/scorers.py")

# The price-authority walk (2026-10-04) reads many feeds on a real chain; it has its own offline test
# (scripts/lib/tests/test_price_authority.py), so the scorer bodies here see a fixed 100.
_PA_NAMES = ("for_aave", "for_aave_v2", "for_comet", "for_morpho_v1", "for_morpho_v2", "for_gmx_v2", "for_gmx_v1", "for_euler_factory", "for_euler_earn", "for_moonwell")
_PA_ORIG = {}


def setUpModule():
    for n in _PA_NAMES:
        _PA_ORIG[n] = getattr(scorers.price_authority, n)
        setattr(scorers.price_authority, n, lambda *a, **k: 100)


def tearDownModule():
    for n, f in _PA_ORIG.items():
        setattr(scorers.price_authority, n, f)


# ---------------------------------------------------------------------------
# Fakes: one dispatch table per read primitive, STRICT -- a read that a test did
# not explicitly wire is recorded and raises, so a scorer that starts reading
# something new (or reads on a None address) fails loudly instead of silently
# getting None (= "revert") back.
# ---------------------------------------------------------------------------
class FakeEth:
    def __init__(self, code_sizes):
        self._code_sizes = code_sizes

    def get_code(self, addr):
        return b"\x00" * self._code_sizes.get(addr, 1)


class FakeBaseW3:
    """The `w3` handed to a scorer as the Base connection. Only score_uniswap_v3_
    factory_base (used by the score_all test) touches .eth / .to_checksum_address
    directly; everything else goes through the patched readers."""

    def __init__(self, code_sizes=None):
        self.eth = FakeEth(code_sizes or {})

    @staticmethod
    def to_checksum_address(addr):
        return RealWeb3.to_checksum_address(addr)


BASE_W3 = FakeBaseW3()
L1_W3 = "ethereum-l1-w3-sentinel"  # what the patched get_w3() hands back for the L1 hop


class ReaderFake:
    NAMES = ("read_address_getter", "call_raw", "read_slot_as_address", "safe_owners_and_threshold", "get_w3")

    def __init__(self):
        self.getters = {}    # (address, function_name) -> address | None
        self.raw = {}        # (address, function_name, args-tuple) -> value | None
        self.slots = {}      # (address, slot) -> address | None
        self.safes = {}      # address -> (owners, threshold) | None
        self.abis = {}       # (address, function_name) -> abi fragment the scorer passed to call_raw
        self.log = []        # chronological (kind, w3, address, *rest)
        self.l1_urls = []    # every URL the scorer passed to get_w3
        self.unexpected = []

    def reads(self):
        """The read log without the w3 element: (kind, address, *rest)."""
        return [(e[0],) + tuple(e[2:]) for e in self.log]

    def _read(self, table, key, entry):
        self.log.append(entry)
        if key not in table:
            self.unexpected.append(entry)
            raise AssertionError("scorer issued a read this test did not wire: %r" % (entry,))
        return table[key]

    def read_address_getter(self, w3, address, function_name, retries=4):
        return self._read(self.getters, (address, function_name), ("getter", w3, address, function_name))

    def call_raw(self, w3, address, abi_fragment, function_name, *args, retries=4):
        self.abis[(address, function_name)] = abi_fragment
        return self._read(self.raw, (address, function_name, args), ("raw", w3, address, function_name, args))

    def read_slot_as_address(self, w3, address, slot, retries=4):
        return self._read(self.slots, (address, slot), ("slot", w3, address, slot))

    def safe_owners_and_threshold(self, w3, address, retries=4):
        return self._read(self.safes, address, ("safe", w3, address))

    def get_w3(self, rpc_url):
        self.l1_urls.append(rpc_url)
        return L1_W3


def install(test_case, fake):
    originals = {n: getattr(scorers, n) for n in ReaderFake.NAMES}
    for n in ReaderFake.NAMES:
        setattr(scorers, n, getattr(fake, n))

    def _restore():
        for n, fn in originals.items():
            setattr(scorers, n, fn)

    test_case.addCleanup(_restore)
    test_case.addCleanup(lambda: test_case.assertEqual(fake.unexpected, []))


def _assert_reads(test_case, fake, expected, must_precede=()):
    """The scorer issued exactly the reads in `expected` -- compared as a MULTISET, because
    no document fixes the order between independent reads -- and, for each
    (first, second) pair, `first` came before `second` because `second` needs the address
    that `first` returned (a Safe cannot be read before its owner is known)."""
    got = fake.reads()
    test_case.assertEqual(sorted(got, key=repr), sorted(expected, key=repr))
    for first, second in must_precede:
        test_case.assertLess(got.index(first), got.index(second), "%r must come before %r" % (first, second))


# ---------------------------------------------------------------------------
# Fixtures. REAL = documented on-chain observation; SYNTHETIC = placeholder.
# ---------------------------------------------------------------------------
def _cs(addr):
    return RealWeb3.to_checksum_address(addr.lower())


def _synthetic(n, start):
    """n distinct valid addresses 0x00..00<start>, ...  (SYNTHETIC)."""
    return [RealWeb3.to_checksum_address("0x" + hex(i)[2:].zfill(40)) for i in range(start, start + n)]


SAME = object()  # wire_* marker: "this role reads back the same address as owner()"

# --- Aerodrome Slipstream ---------------------------------------------------
# REAL: [MAINT] "Aerodrome Slipstream -- same key as Aerodrome V1": owner(),
# swapFeeManager(), unstakedFeeManager() all = 0xE6A41fE6...2075, a 3-of-7 Safe,
# no timelock; the same Safe as Aerodrome V1's pauser/feeManager/Voter.governor()
# ([AERO] table). Owner ADDRESSES are not documented -> SYNTHETIC (count 7 is real).
SLIPSTREAM = "0x5e7BB104d84c7CB9B682AaC2F3d509f5F406809A"          # [MAINT] table
AERO_SAFE = "0xE6A41fE61E7a1996B59d508661e3f524d6A32075"           # [MAINT], [AERO]
AERO_SAFE_OWNERS = _synthetic(7, 0x1000)
AERO_POOLFACTORY = "0x420DD381b31aEf6683db6B902084cB0FFECe40Da"    # [AERO]
AERO_VOTER = "0x16613524e02ad97eDfeF371bC883F2F5d6C480A5"          # [AERO]
AERO_COUNCIL = "0x99249b10593fCa1Ae9DAE6D4819F1A6dae5C013D"        # [AERO] emergencyCouncil, 3-of-5
AERO_COUNCIL_OWNERS = _synthetic(5, 0x2000)                        # SYNTHETIC; disjoint from AERO_SAFE_OWNERS by construction ([AERO]: "zero owner overlap")

# --- Uniswap V2 / V4 direct-forwarder targets --------------------------------
# REAL: [MAINT] "Uniswap V2 / V4 -- same DAO root as the tracked V3 Factory":
# feeToSetter() / owner() = 0x31FAfd48...72A9 (forwarder); slot 0 = the
# L2CrossDomainMessenger predeploy; slot 1 = L1 Timelock 0x1a9C8182...35BC with
# delay 172,800 s and admin GovernorBravo 0x408ED635...24C3 (re-read on Ethereum).
# Same forwarder / slots as [SCOUT] section 4 (V3 Factory's adapter.owner()).
UNI_V2_FACTORY = "0x8909Dc15e40173Ff4699343b6eB8132c65e18eC6"      # [MAINT] table
UNI_V4_POOLMANAGER = "0x498581fF718922c3f8e6A244956aF099B2652b2b"  # [MAINT] table
UNI_FORWARDER = _cs("0x31FAfd4889FA1269F7a13A66eE0fB458f27D72A9")
PREDEPLOY = "0x4200000000000000000000000000000000000007"           # OP-stack L2CrossDomainMessenger
UNI_L1_TIMELOCK = _cs("0x1a9C8182C09F50C8318d769245beA52c32BE35BC")
UNI_GOVERNOR_BRAVO = _cs("0x408ED6354d4973f66138C91495F2f2FCbd8724C3")
UNI_L1_DELAY = 172800                                              # 2 days
SLOT0 = "0x" + "00" * 32
SLOT1 = "0x" + "00" * 31 + "01"
L1_RPC = "https://ethereum-rpc.publicnode.com"                     # scorers.py docstring / [MAINT]
OTHER = _cs("0x" + "ee" * 20)                                      # SYNTHETIC "some other address"
OTHER_FORWARDER = _cs("0x" + "ef" * 20)                            # SYNTHETIC: a forwarder that is NOT the V3 one
OTHER_L1_TIMELOCK = _cs("0x" + "ab" * 20)                          # SYNTHETIC: an L1 timelock that is NOT Uniswap's

# --- Moonwell ---------------------------------------------------------------
# REAL: [MAINT] "Moonwell -- Wormhole-gated cross-chain governance": Unitroller
# .admin() = TemporalGovernor 0x8b621804...7d51, proposalDelay() = 86,400 s,
# allTrustedSenders(2) = [0x8769b70a...5838] (MULTICHAIN_GOVERNOR_V2_PROXY per
# moonwell-fi chains/1.json), guardian owner() = 3-of-5 Safe 0x446342AF...779E,
# guardianPauseAllowed = true. The doc abbreviates the sender; the full 20 bytes
# are taken from the scorer's own comparison constant (prefix 0x8769b70a and suffix
# 5838 match the doc, pinned by TestFixtureProvenance; the middle 16 hex digits are the
# KNOWN LIMIT in the module header). One guardian owner, 0xD791292655A1d382FcC1a6Cb9171476cf91F2caa,
# is named in full in [MAINT] ("Also disclosed"); the other four owner addresses are
# SYNTHETIC (count is real).
MOONWELL = "0xfBb21d0380beE3312B33c4353c8936a0F13EF26C"
TEMPORAL_GOVERNOR = _cs("0x8b621804a7637b781e2BbD58e256a591F2dF7d51")
MOONWELL_GUARDIAN = _cs("0x446342AF4F3bCD374276891C6bb3411bf2F8779E")
MOONWELL_GUARDIAN_OWNERS = [_cs("0xD791292655A1d382FcC1a6Cb9171476cf91F2caa")] + _synthetic(4, 0x3000)
SENDER_HEX = "8769b70ac7c93af0e75de0d69877709b66d75838"  # COPY of scorers.py's constant; see the KNOWN LIMIT in the header
SENDER = bytes(12) + bytes.fromhex(SENDER_HEX)           # bytes32, left-padded (what allTrustedSenders returns)
OTHER_SENDER = bytes(12) + bytes.fromhex("dd" * 20)      # SYNTHETIC

# --- Morpho Blue (only used by the overlap / score_all tests) -----------------
# REAL: [MAINT] audit rotation table: MorphoBlue.owner() = 0xcBa28b38...9AFa, 5-of-9;
# the 9 owners are the real list printed in [MORPHO].
MORPHO = "0xBBBBBbbBBb9cC5e90e3b3Af64bdAF62C37EEFFCb"
MORPHO_SAFE = "0xcBa28b38103307Ec8dA98377ffF9816C164f9AFa"
MORPHO_OWNERS = [_cs(a) for a in (
    "0x13cA8756E9470b71B8e998352c8741706217f963", "0x264c86DBbD2E4165FbBf0C35b0ddf0e00AEc6b31",
    "0x30E7c016fC702cDe9A50720a469d418490b7b652", "0x69FcEFDe2B48503d675181448B3D4272128bca9c",
    "0x84D3E4EE550DD5F99e76a548aC59a6BE1C8dCf79", "0x8f02b4a44Eacd9b8eE7739aa0BA58833DD45d002",
    "0xC100c251bdD297A66795112f04356E6BA5f89D80", "0xCF263cEe139763114fAaFC5F52865135412F50Ec",
    "0xe0aeb6811d33Df42A09066857CDaFca16b506086",
)]


# --- Morpho V1 vaults added 2026-09-25 (chains/base-ecosystem/scorers.py, commit 15543f2) -----
# REAL (live-read 2026-09-25, see data/finding_2026-09-25-controller-concentration.md): the
# threshold/owner-count of each Safe below and the KNOWN Steakhouse constants; individual owner
# addresses are not written down anywhere -> SYNTHETIC, same convention as every other block above.
GAUNTLET_VAULT = "0xeE8F4eC5672F09119b96Ab6fB59C27E1b7e44b61"
GAUNTLET_OWNER_SAFE = _cs("0x" + "70" * 20)
GAUNTLET_CURATOR_SAFE = _cs("0x" + "71" * 20)
GAUNTLET_GUARDIAN_SAFE = _cs("0x" + "72" * 20)
GAUNTLET_SHARED_OWNERS = _synthetic(7, 0x7200)  # REAL: all three roles share the SAME 7 signers

SPARK_VAULT = "0x7BfA7C4f149E7415b73bdeDfe609237e29CBF34A"
SPARK_OWNER_CONTRACT = _cs("0x" + "73" * 20)      # bespoke, not Ownable-shaped: owner()/owner() both unresolved
SPARK_CURATOR_SAFE = _cs("0x" + "74" * 20)
SPARK_GUARDIAN_SAFE = _cs("0x" + "75" * 20)
SPARK_CURATOR_OWNERS = _synthetic(5, 0x7300)      # REAL: 3-of-5
SPARK_GUARDIAN_OWNERS = _synthetic(5, 0x7400)     # REAL: disjoint from curator's, zero shared signers

STEAKHOUSE_USDC_BASE_VAULT = "0xbeeF010f9cb27031ad51e3333f9aF9C6B1228183"
GROVE_STEAKHOUSE_VAULT = "0xBeEf2d50B428675a1921bC6bBF4bfb9D8cF1461A"
STEAKHOUSE_GUARDIAN_PLACEHOLDER = _cs("0x" + "76" * 20)  # read and disclosed in notes, never Safe-resolved or scored
# REAL: the LITERAL constants chains/base-ecosystem/scorers.py compares owner()/curator() against
# (COPY of the scorer's own constants, same convention as Moonwell's SENDER above).
KNOWN_STEAKHOUSE_OWNER_SAFE = _cs("0x0A0e559bc3b0950a7e448F0d4894db195b9cf8DD")
KNOWN_STEAKHOUSE_CURATOR_SAFE = _cs("0x827e86072B06674a077f592A531dcE4590aDeCdB")
STEAKHOUSE_OWNER_OWNERS = _synthetic(9, 0x7500)   # REAL: 5-of-9 on Base
STEAKHOUSE_CURATOR_OWNERS = _synthetic(6, 0x7600)  # REAL: 2-of-6 on Base


def wire_morpho_vaults(fake):
    """The 4 Morpho V1 vaults added 2026-09-25. Not covered by the module docstring's four
    functions under test -- wired only so score_all() runs the full current target set without
    tripping ReaderFake's strict 'unexpected read' check, same reasoning
    wire_the_five_older_targets_that_are_not_under_test gives for the original five."""
    fake.getters[(GAUNTLET_VAULT, "owner")] = GAUNTLET_OWNER_SAFE
    fake.getters[(GAUNTLET_VAULT, "curator")] = GAUNTLET_CURATOR_SAFE
    fake.getters[(GAUNTLET_VAULT, "guardian")] = GAUNTLET_GUARDIAN_SAFE
    fake.safes[GAUNTLET_OWNER_SAFE] = (GAUNTLET_SHARED_OWNERS, 4)
    fake.safes[GAUNTLET_CURATOR_SAFE] = (GAUNTLET_SHARED_OWNERS, 3)
    fake.safes[GAUNTLET_GUARDIAN_SAFE] = (GAUNTLET_SHARED_OWNERS, 3)

    fake.getters[(SPARK_VAULT, "owner")] = SPARK_OWNER_CONTRACT
    fake.getters[(SPARK_OWNER_CONTRACT, "owner")] = None  # bespoke contract, not Ownable-shaped
    fake.getters[(SPARK_VAULT, "curator")] = SPARK_CURATOR_SAFE
    fake.getters[(SPARK_VAULT, "guardian")] = SPARK_GUARDIAN_SAFE
    fake.safes[SPARK_CURATOR_SAFE] = (SPARK_CURATOR_OWNERS, 3)
    fake.safes[SPARK_GUARDIAN_SAFE] = (SPARK_GUARDIAN_OWNERS, 3)

    for vault in (STEAKHOUSE_USDC_BASE_VAULT, GROVE_STEAKHOUSE_VAULT):
        fake.getters[(vault, "owner")] = KNOWN_STEAKHOUSE_OWNER_SAFE
        fake.getters[(vault, "curator")] = KNOWN_STEAKHOUSE_CURATOR_SAFE
        fake.getters[(vault, "guardian")] = STEAKHOUSE_GUARDIAN_PLACEHOLDER
    fake.safes[KNOWN_STEAKHOUSE_OWNER_SAFE] = (STEAKHOUSE_OWNER_OWNERS, 5)
    fake.safes[KNOWN_STEAKHOUSE_CURATOR_SAFE] = (STEAKHOUSE_CURATOR_OWNERS, 2)


def _vector(r):
    return (r["adminKeyScore"], r["multisigScore"], r["timelockScore"],
            r["oracleAuthorityScore"], r["crossExposureScore"], r["compositeScore"])


def _notes(r):
    return "\n".join(r["notes"])


# Independent pin of what scorers._CROSS_EXPOSURE_NOTE MEANS (its exact text is the scorer's
# own; the overlap pass keys on the constant itself, so the tests compare against it where they
# must). Meaning per the scorers.py comment above the constant and [METH] crossExposureScore:
# "100 = no overlap found, or not computed for that target".
PLACEHOLDER_FRAGMENTS = ("crossExposureScore = 100", "not computed")


# ---------------------------------------------------------------------------
# Wiring helpers (what each scorer reads, in the shape the real readers return)
# ---------------------------------------------------------------------------
def wire_slipstream(fake, owner=AERO_SAFE, swap=SAME, unstaked=SAME, safe=(AERO_SAFE_OWNERS, 3)):
    fake.getters[(SLIPSTREAM, "owner")] = owner
    fake.getters[(SLIPSTREAM, "swapFeeManager")] = owner if swap is SAME else swap
    fake.getters[(SLIPSTREAM, "unstakedFeeManager")] = owner if unstaked is SAME else unstaked
    if owner:  # the scorer only reads the Safe when owner() resolved
        fake.safes[owner] = safe


def wire_forwarder(fake, target, getter, forwarder=UNI_FORWARDER, slot0=PREDEPLOY, slot1=UNI_L1_TIMELOCK,
                   delay=UNI_L1_DELAY, admin=UNI_GOVERNOR_BRAVO):
    fake.getters[(target, getter)] = forwarder
    if forwarder:
        fake.slots[(forwarder, SLOT0)] = slot0
        fake.slots[(forwarder, SLOT1)] = slot1
        if slot1:
            fake.raw[(slot1, "delay", ())] = delay
            fake.raw[(slot1, "admin", ())] = admin


def wire_moonwell(fake, admin=TEMPORAL_GOVERNOR, delay=86400, senders=(SENDER,), guardian=MOONWELL_GUARDIAN,
                  guardian_safe=(MOONWELL_GUARDIAN_OWNERS, 3), pause_allowed=True):
    fake.getters[(MOONWELL, "admin")] = admin
    if admin:
        fake.raw[(admin, "proposalDelay", ())] = delay
        fake.raw[(admin, "allTrustedSenders", (2,))] = None if senders is None else list(senders)
        fake.getters[(admin, "owner")] = guardian
        fake.raw[(admin, "guardianPauseAllowed", ())] = pause_allowed
        if guardian:
            fake.safes[guardian] = guardian_safe


def _signature(fragment):
    (f,) = fragment
    return (f["name"] + "(" + ",".join(i["type"] for i in f["inputs"]) + ")", [o["type"] for o in f["outputs"]])


# ===========================================================================
# score_aerodrome_slipstream_clfactory
# ===========================================================================
class TestSlipstreamCLFactory(unittest.TestCase):
    def _score(self, **wire_kwargs):
        fake = ReaderFake()
        wire_slipstream(fake, **wire_kwargs)
        install(self, fake)
        return scorers.score_aerodrome_slipstream_clfactory(BASE_W3), fake

    # --- happy path: the PUBLISHED score --------------------------------------
    def test_one_3_of_7_safe_on_all_three_roles_reproduces_the_published_score(self):
        # [MAINT] table: Slipstream composite 46; [READBACK] row 5:
        # adminKey 65, multisig 65, timelock 0, oracle 100, composite 46.
        # Hand derivation: threshold 3 >= 3 -> adminKey 65; multisig
        # min(100, 3*15 + (7-3)*5) = 65; composite floor(26 + 19.5 + 0 + 0.5) = 46.
        # crossExposure is still 100 here: it becomes the published 80 only in the
        # score_all() post-pass (see TestScoreAllPublishedReadback).
        r, _ = self._score()
        self.assertEqual(_vector(r), (65, 65, 0, 100, 100, 46))
        self.assertEqual(r["target"], SLIPSTREAM)
        self.assertEqual(r["label"], "Aerodrome Slipstream CLFactory (Base)")

    def test_root_safe_owners_are_exposed_for_the_overlap_pass(self):
        r, _ = self._score()
        self.assertEqual(r["rootSafeOwners"], AERO_SAFE_OWNERS)
        self.assertIsInstance(r["rootSafeOwners"], list)

    def test_root_safe_owners_keep_the_order_getOwners_returned_them_in(self):
        # getOwners() returns the Safe's own linked-list order, which is not sorted; the
        # scorer copies it (`list(safe[0])`) and nothing sorts or reorders it. The fixture
        # above is monotonically ascending, which would hide a sorted() -- so use a shuffle.
        order = [AERO_SAFE_OWNERS[i] for i in (3, 0, 6, 1, 5, 2, 4)]
        self.assertNotEqual(order, sorted(order))
        r, _ = self._score(safe=(order, 3))
        self.assertEqual(r["rootSafeOwners"], order)

    def test_owners_returned_as_a_tuple_are_exposed_as_a_list(self):
        r, _ = self._score(safe=(tuple(AERO_SAFE_OWNERS), 3))
        self.assertEqual(r["rootSafeOwners"], AERO_SAFE_OWNERS)
        self.assertIsInstance(r["rootSafeOwners"], list)

    def test_notes_carry_the_three_roles_and_the_no_timelock_disclosure(self):
        # Wording per the scorer's own docstring: "No timelock anywhere."
        r, _ = self._score()
        self.assertEqual(r["notes"], [
            "CLFactory.owner() = %s, swapFeeManager() = %s, unstakedFeeManager() = %s" % (AERO_SAFE, AERO_SAFE, AERO_SAFE),
            "all three roles on one address: True",
            "owner Safe: 3-of-7, no timelock in the chain",
        ])

    def test_reads_the_three_roles_once_each_and_the_owner_safe_only_after_owner_resolved(self):
        # [MAINT]: owner(), swapFeeManager(), unstakedFeeManager() then the owner's Safe.
        # Only the dependency (the Safe is read at the address owner() returned) is ordered.
        _, fake = self._score()
        _assert_reads(self, fake, [
            ("getter", SLIPSTREAM, "owner"),
            ("getter", SLIPSTREAM, "swapFeeManager"),
            ("getter", SLIPSTREAM, "unstakedFeeManager"),
            ("safe", AERO_SAFE),
        ], must_precede=[(("getter", SLIPSTREAM, "owner"), ("safe", AERO_SAFE))])
        self.assertTrue(all(e[1] is BASE_W3 for e in fake.log))

    # --- Safe strength tiers: every value hand-derived from [METH] -------------
    def test_threshold_and_owner_count_tiers(self):
        # (threshold, owners, adminKey, multisig, composite); timelock is always 0.
        # adminKey: threshold>=3 -> 65, ==2 -> 50, else 10.
        # multisig: min(100, t*15 + max(0, n-t)*5).  composite: floor(0.4a + 0.3m + 0.5).
        rows = [
            (1, 1, 10, 15, 9),      # 4.0 + 4.5 + 0.5 = 9.0
            (1, 3, 10, 25, 12),     # 4.0 + 7.5 + 0.5 = 12.0
            (2, 2, 50, 30, 29),     # 20 + 9 + 0.5 = 29.5 -> 29
            (2, 3, 50, 35, 31),     # 20 + 10.5 + 0.5 = 31.0
            (3, 5, 65, 55, 43),     # 26 + 16.5 + 0.5 = 43.0
            (3, 7, 65, 65, 46),     # 26 + 19.5 + 0.5 = 46.0   (published Aerodrome shape)
            (4, 7, 65, 75, 49),     # 26 + 22.5 + 0.5 = 49.0
            (5, 9, 65, 95, 55),     # 26 + 28.5 + 0.5 = 55.0   (published Morpho Blue shape, [READBACK] row 0)
            (6, 6, 65, 90, 53),     # 26 + 27 + 0.5 = 53.5 -> 53   (uncapped, 6*15)
            (6, 8, 65, 100, 56),    # 90 + 2*5 = 100 exactly, 26 + 30 + 0.5 = 56.5 -> 56
        ]
        for threshold, n, admin, multisig, composite in rows:
            with self.subTest(threshold=threshold, owners=n):
                r, _ = self._score(safe=(_synthetic(n, 0x4000), threshold))
                self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["timelockScore"], r["compositeScore"]),
                                 (admin, multisig, 0, composite))
                self.assertIn("owner Safe: %d-of-%d, no timelock in the chain" % (threshold, n), r["notes"])

    def test_multisig_score_is_capped_at_100(self):
        # 7-of-9: 7*15 + 2*5 = 115 -> capped 100; 9-of-9: 135 -> 100.
        # composite floor(26 + 30 + 0.5) = 56 for both.
        for threshold, n in ((7, 9), (9, 9)):
            with self.subTest(threshold=threshold, owners=n):
                r, _ = self._score(safe=(_synthetic(n, 0x4000), threshold))
                self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["compositeScore"]), (65, 100, 56))

    def test_admin_key_tier_boundaries_move_only_with_the_threshold(self):
        # Dedicated guard for the boundaries (also spread over the table above): adminKey is
        # 65 for threshold >= 3, 50 for == 2, 10 below. Owner count fixed at 7 so only the
        # threshold moves; multisig = min(100, 15t + 5(7-t)) = 10t + 35.
        # (threshold, adminKey, multisig, composite = floor(0.4a + 0.3m + 0.5)):
        rows = [
            (1, 10, 45, 18),    # 4.0 + 13.5 + 0.5 = 18.0
            (2, 50, 55, 37),    # 20 + 16.5 + 0.5 = 37.0
            (3, 65, 65, 46),    # 26 + 19.5 + 0.5 = 46.0
            (4, 65, 75, 49),    # 26 + 22.5 + 0.5 = 49.0
        ]
        for threshold, admin, multisig, composite in rows:
            with self.subTest(threshold=threshold):
                r, _ = self._score(safe=(_synthetic(7, 0x4000), threshold))
                self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["timelockScore"], r["compositeScore"]),
                                 (admin, multisig, 0, composite))

    def test_composite_rounds_half_up_not_down_and_not_to_even(self):
        # [METH]: floor(x + 0.5). Raw values that land exactly on .5 (hand-computed):
        #   1-of-3: 0.4*10 + 0.3*25 = 11.5 -> 12  (truncation says 11)
        #   2-of-3: 0.4*50 + 0.3*35 = 30.5 -> 31  (banker's round() says 30)
        #   3-of-5: 0.4*65 + 0.3*55 = 42.5 -> 43  (truncation and banker's both say 42)
        #   3-of-7: 0.4*65 + 0.3*65 = 45.5 -> 46  (the published Aerodrome value; truncation says 45)
        for threshold, n, composite in ((1, 3, 12), (2, 3, 31), (3, 5, 43), (3, 7, 46)):
            with self.subTest(threshold=threshold, owners=n):
                r, _ = self._score(safe=(_synthetic(n, 0x4000), threshold))
                self.assertEqual(r["compositeScore"], composite)

    def test_threshold_above_owner_count_adds_no_negative_owner_term(self):
        # [METH]: min(100, threshold*15 + max(0, ownerCount - threshold)*5). A real Gnosis Safe
        # cannot have threshold > owners, but the written formula defines that corner: the
        # max(0, ...) term is 0, never negative.
        #   3-of-2: 45 (not 40); adminKey 65; composite floor(26 + 13.5 + 0.5) = 40
        #   2-of-1: 30 (not 25); adminKey 50; composite floor(20 + 9 + 0.5) = 29
        for threshold, n, admin, multisig, composite in ((3, 2, 65, 45, 40), (2, 1, 50, 30, 29)):
            with self.subTest(threshold=threshold, owners=n):
                r, _ = self._score(safe=(_synthetic(n, 0x4000), threshold))
                self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["compositeScore"]),
                                 (admin, multisig, composite))
                self.assertIn("owner Safe: %d-of-%d, no timelock in the chain" % (threshold, n), r["notes"])

    # --- degraded / disagreeing authority -> the documented conservative floor --
    def _assert_floor(self, r):
        # Unresolved authority floor: adminKey 20, multisig 0, timelock 0
        # ([METH] adminKeyScore: "an unresolved contract ... scores 20").
        # composite floor(0.4*20 + 0 + 0 + 0.5) = floor(8.5) = 8.
        self.assertEqual(_vector(r), (20, 0, 0, 100, 100, 8))
        self.assertEqual(r["rootSafeOwners"], [])
        self.assertIn("root authority not resolved as ONE Gnosis Safe this run -- conservative score", r["notes"])
        self.assertNotIn("owner Safe", _notes(r))

    def test_owner_unresolved_degrades_to_the_floor_and_never_reads_a_safe(self):
        r, fake = self._score(owner=None)
        self._assert_floor(r)
        self.assertIn("all three roles on one address: False", r["notes"])
        # No Safe read on a None owner; both fee managers are still read. This is NOT only fake
        # strictness: the real reader on a None address returns None only after
        # scripts/lib/web3_utils.py::_retrying has slept 0.4 + 0.8 + 1.2 = 2.4 s, so an
        # unguarded read costs real wall-clock time in the production run (score is unchanged).
        self.assertEqual([k for k, *_ in fake.reads()], ["getter", "getter", "getter"])

    def test_owner_unresolved_even_when_both_fee_managers_agree_on_a_real_safe(self):
        # owner() reverted, but the two fee managers point at the real Safe:
        # bool(owner) is False, so no role agreement is credited.
        r, _ = self._score(owner=None, swap=AERO_SAFE, unstaked=AERO_SAFE)
        self._assert_floor(r)
        self.assertIn("all three roles on one address: False", r["notes"])

    def test_swap_fee_manager_on_a_different_address_degrades(self):
        # Cross-check between three getters disagrees: owner is the real 3-of-7
        # Safe (and is read as one) but swapFeeManager is elsewhere.
        r, fake = self._score(swap=OTHER)
        self._assert_floor(r)
        self.assertIn("all three roles on one address: False", r["notes"])
        self.assertIn(("safe", AERO_SAFE), fake.reads())  # the owner Safe WAS resolved, the roles just disagree

    def test_unstaked_fee_manager_on_a_different_address_degrades(self):
        r, _ = self._score(unstaked=OTHER)
        self._assert_floor(r)

    def test_swap_fee_manager_read_failing_degrades(self):
        r, _ = self._score(swap=None)
        self._assert_floor(r)

    def test_unstaked_fee_manager_read_failing_degrades(self):
        r, _ = self._score(unstaked=None)
        self._assert_floor(r)

    def test_owner_that_is_not_a_gnosis_safe_degrades_whatever_it_is(self):
        # safe_owners_and_threshold() returns None for anything whose getOwners()/
        # getThreshold() revert: a bare EOA, a TimelockController, a bespoke
        # multisig exposing getSigners()/threshold(). The scorer cannot tell them
        # apart (it never reads bytecode), so all land on the same floor.
        kinds = {"bare EOA": _cs("0x" + "a1" * 20),
                 "TimelockController": _cs("0x" + "a2" * 20),
                 "custom getSigners()/threshold() multisig": _cs("0x" + "a3" * 20)}
        for kind, addr in kinds.items():
            with self.subTest(kind=kind):
                r, _ = self._score(owner=addr, safe=None)
                self._assert_floor(r)
                self.assertIn("all three roles on one address: True", r["notes"])


# ===========================================================================
# _uniswap_direct_forwarder_score  (+ its two thin wrappers)
# ===========================================================================
class TestUniswapDirectForwarder(unittest.TestCase):
    V2_SCOPE_FRAGMENT = "feeToSetter can only set feeTo / hand over feeToSetter"
    V4_SCOPE_FRAGMENTS = ("setProtocolFeeController", "transferOwnership")

    def _v2(self, **wire_kwargs):
        fake = ReaderFake()
        wire_forwarder(fake, UNI_V2_FACTORY, "feeToSetter", **wire_kwargs)
        install(self, fake)
        return scorers.score_uniswap_v2_factory_base(BASE_W3), fake

    def _v4(self, **wire_kwargs):
        fake = ReaderFake()
        wire_forwarder(fake, UNI_V4_POOLMANAGER, "owner", **wire_kwargs)
        install(self, fake)
        return scorers.score_uniswap_v4_poolmanager_base(BASE_W3), fake

    def _assert_degraded_admin(self, r, composite=38):
        # adminKey degrades to the unresolved floor 20, multisig stays "not
        # applicable" 100, timelock 0 -> floor(8 + 30 + 0 + 0.5) = floor(38.5) = 38.
        self.assertEqual(_vector(r), (20, 100, 0, 100, 100, composite))
        self.assertIn("L1 cross-domain re-confirmation did not fully resolve -- adminKeyScore degraded", r["notes"])

    # --- happy path: the PUBLISHED scores -------------------------------------
    def test_v2_factory_reproduces_the_published_score(self):
        # [MAINT] table + "Uniswap V2 / V4": "Scored exactly like V3 (80/100/75 -> 85)".
        # [READBACK] row 6: 80, 100, 75, 100, 100, 85; crossExposure 80 since 2026-09-20 (the shared
        # L1 Timelock root is folded, composite unchanged).
        # Hand derivation: floor(0.4*80 + 0.3*100 + 0.3*75 + 0.5) = floor(32 + 30 + 22.5 + 0.5) = 85.
        r, _ = self._v2()
        self.assertEqual(_vector(r), (80, 100, 75, 100, 80, 85))
        self.assertEqual(r["target"], UNI_V2_FACTORY)
        self.assertEqual(r["label"], "Uniswap V2 Factory (Base)")

    def test_v4_poolmanager_reproduces_the_published_score(self):
        # [READBACK] row 7: 80, 100, 75, 100, 100, 85; crossExposure 80 since 2026-09-20.
        r, _ = self._v4()
        self.assertEqual(_vector(r), (80, 100, 75, 100, 80, 85))
        self.assertEqual(r["target"], UNI_V4_POOLMANAGER)
        self.assertEqual(r["label"], "Uniswap V4 PoolManager (Base)")

    def test_v2_notes_carry_the_forwarder_slots_l1_reads_and_the_dao_scope(self):
        r, _ = self._v2()
        self.assertEqual(len(r["notes"]), 7)  # no degradation note on the happy path
        self.assertEqual(r["notes"][0], "feeToSetter() = %s" % UNI_FORWARDER)
        self.assertEqual(r["notes"][1], "forwarder slot 0 = %s, slot 1 (L1 Governance Timelock) = %s" % (PREDEPLOY, UNI_L1_TIMELOCK))
        self.assertEqual(r["notes"][2], "forwarder slot0 matches the L2CrossDomainMessenger predeploy: True")
        self.assertEqual(r["notes"][3], "L1 (own w3): %s.delay() = 172800s, .admin() = %s" % (UNI_L1_TIMELOCK, UNI_GOVERNOR_BRAVO))
        self.assertIn(self.V2_SCOPE_FRAGMENT, r["notes"][4])
        self.assertIn("one DAO root for V2/V3/V4 on Base", r["notes"][5])
        self.assertIn("crossExposureScore = 80", r["notes"][6])
        self.assertIn("Uniswap's Ethereum L1 Governance Timelock", r["notes"][6])
        self.assertNotIn("not counted in crossExposureScore", " ".join(r["notes"]))
        self.assertFalse(any("degraded" in n for n in r["notes"]))

    def test_wrappers_pass_their_own_getter_and_disclose_their_own_scope(self):
        # V2 reads feeToSetter(), V4 reads owner(); each carries its documented scope caveat
        # ([MAINT]: V2 feeToSetter = setFeeTo / setFeeToSetter only; V4 owner has exactly
        # setProtocolFeeController and transferOwnership).
        r2, f2 = self._v2()
        self.assertEqual(f2.reads()[0], ("getter", UNI_V2_FACTORY, "feeToSetter"))
        self.assertTrue(any(self.V2_SCOPE_FRAGMENT in n for n in r2["notes"]))
        r4, f4 = self._v4()
        self.assertEqual(f4.reads()[0], ("getter", UNI_V4_POOLMANAGER, "owner"))
        for fragment in self.V4_SCOPE_FRAGMENTS:
            self.assertTrue(any(fragment in n for n in r4["notes"]), fragment)

    def test_helper_arguments_flow_through_to_the_result_and_notes(self):
        target = _cs("0x" + "12" * 20)
        fake = ReaderFake()
        wire_forwarder(fake, target, "customGetter")
        install(self, fake)
        r = scorers._uniswap_direct_forwarder_score(BASE_W3, target, "customGetter", "Some Label", "some scope note")
        self.assertEqual((r["target"], r["label"]), (target, "Some Label"))
        self.assertEqual(r["notes"][0], "customGetter() = %s" % UNI_FORWARDER)
        self.assertIn("some scope note", r["notes"])
        self.assertEqual(_vector(r), (80, 100, 75, 100, 80, 85))

    def test_which_w3_each_read_uses_and_one_l1_connection_is_opened(self):
        # scorers.py docstring / [MAINT]: Base w3 for the getter and both storage slots; the
        # SEPARATE Ethereum w3 (opened from get_w3 at the public Ethereum RPC) for the L1
        # timelock's delay() and admin(). The order between independent reads is not pinned;
        # only the data dependencies are (the slots need the forwarder, the L1 reads need slot 1).
        _, fake = self._v2()
        expected = [
            ("getter", UNI_V2_FACTORY, "feeToSetter"),
            ("slot", UNI_FORWARDER, SLOT0),
            ("slot", UNI_FORWARDER, SLOT1),
            ("raw", UNI_L1_TIMELOCK, "delay", ()),
            ("raw", UNI_L1_TIMELOCK, "admin", ()),
        ]
        _assert_reads(self, fake, expected, must_precede=[
            (expected[0], expected[1]), (expected[0], expected[2]),
            (expected[2], expected[3]), (expected[2], expected[4]),
        ])
        w3_by_read = {(e[0],) + tuple(e[2:]): e[1] for e in fake.log}
        self.assertEqual(w3_by_read, {
            expected[0]: BASE_W3, expected[1]: BASE_W3, expected[2]: BASE_W3,
            expected[3]: L1_W3, expected[4]: L1_W3,
        })
        self.assertEqual(fake.l1_urls, [L1_RPC])

    def test_l1_call_shapes_are_delay_uint256_and_admin_address(self):
        _, fake = self._v2()
        self.assertEqual(_signature(fake.abis[(UNI_L1_TIMELOCK, "delay")]), ("delay()", ["uint256"]))
        self.assertEqual(_signature(fake.abis[(UNI_L1_TIMELOCK, "admin")]), ("admin()", ["address"]))

    def test_result_is_dao_rooted_so_it_has_no_root_safe_owners(self):
        # [MAINT]: "DAO-rooted, so not counted in crossExposureScore (no Safe signer set)".
        r, _ = self._v2()
        self.assertNotIn("rootSafeOwners", r)
        self.assertEqual(r["crossExposureScore"], 80)  # folded 2026-09-20: one L1 Timelock root, no Safe signer set
        self.assertEqual(r["oracleAuthorityScore"], 100)

    # --- unresolved / disagreeing reads -> admin floor ------------------------
    def test_forwarder_unresolved_degrades_and_opens_no_l1_connection(self):
        r, fake = self._v2(forwarder=None)
        self._assert_degraded_admin(r)
        # Nothing is read on a None forwarder. Not only fake strictness: the real readers on a
        # None address return None only after scripts/lib/web3_utils.py::_retrying sleeps
        # 0.4 + 0.8 + 1.2 = 2.4 s per read, so an unguarded read is real wall-clock cost.
        self.assertEqual(fake.reads(), [("getter", UNI_V2_FACTORY, "feeToSetter")])
        self.assertEqual(fake.l1_urls, [])
        self.assertIn("forwarder slot 0 = None, slot 1 (L1 Governance Timelock) = None", r["notes"])
        self.assertIn("forwarder slot0 matches the L2CrossDomainMessenger predeploy: False", r["notes"])

    def test_slot0_not_the_predeploy_degrades_even_though_the_l1_reads_resolve(self):
        # Cross-check between two sources disagrees: slot 0 says "not the canonical
        # OP-stack messenger" while slot 1 still points at the real Uniswap timelock
        # with a real delay. The gate must hold: admin 20 AND timelock 0
        # (timelock is gated on l1_ok, not only on the delay). Only the SCORE consequence is
        # asserted: whether the scorer still makes the L1 hop when slot 0 is already wrong is an
        # implementation detail no document fixes, so it is deliberately not pinned.
        r, _ = self._v2(slot0=OTHER)
        self._assert_degraded_admin(r)
        self.assertIn("forwarder slot0 matches the L2CrossDomainMessenger predeploy: False", r["notes"])

    def test_slot0_read_failing_degrades(self):
        r, _ = self._v2(slot0=None)
        self._assert_degraded_admin(r)

    def test_slot1_unresolved_degrades_and_skips_the_l1_hop(self):
        r, fake = self._v2(slot1=None)
        self._assert_degraded_admin(r)
        self.assertEqual(fake.l1_urls, [])
        self.assertEqual(sorted(k for k, *_ in fake.reads()), ["getter", "slot", "slot"])  # no L1 read without slot 1

    def test_l1_delay_read_failing_degrades_admin_and_timelock(self):
        r, _ = self._v2(delay=None)
        self._assert_degraded_admin(r)
        self.assertTrue(any(n.startswith("L1 (own w3): %s.delay() = None" % UNI_L1_TIMELOCK) for n in r["notes"]))

    def test_l1_admin_read_failing_degrades_admin_and_timelock(self):
        r, _ = self._v2(admin=None)
        self._assert_degraded_admin(r)

    # --- timelock rules ------------------------------------------------------
    def test_timelock_score_is_capped_at_75_for_any_positive_delay(self):
        # [METH] timelockScore: a confirmed delay is capped below 100 (no emergency-bypass
        # check done). Flat 75 for 1 s, 2 days and 30 days -> composite floor(84.5 + 0.5) = 85.
        for delay in (1, UNI_L1_DELAY, 30 * 86400):
            with self.subTest(delay=delay):
                r, _ = self._v2(delay=delay)
                self.assertEqual((r["adminKeyScore"], r["timelockScore"], r["compositeScore"]), (80, 75, 85))

    def test_zero_l1_delay_keeps_admin_80_but_scores_timelock_zero(self):
        # delay 0 is "resolved" (not None) so the admin gate passes, but a zero delay
        # earns no timelock credit: (80, 100, 0) -> floor(32 + 30 + 0 + 0.5) = floor(62.5) = 62.
        r, _ = self._v2(delay=0)
        self.assertEqual(_vector(r), (80, 100, 0, 100, 80, 62))
        self.assertFalse(any("degraded" in n for n in r["notes"]))

    # --- note integrity: a finding, kept asserting the desired behaviour -------
    def _different_dao_root(self):
        return self._v2(forwarder=OTHER_FORWARDER, slot1=OTHER_L1_TIMELOCK)

    def test_expected_failure_scenario_is_well_formed_so_an_unrelated_error_cannot_hide_in_it(self):
        # unittest.expectedFailure swallows ANY exception (a KeyError from a mis-wired fake, a
        # strict-fake AssertionError after a new read is added, ...). This companion runs the
        # SAME scenario without the decorator and pins everything that is NOT the finding, so
        # the expected failure below can only be "passing" for the reason it documents.
        # It asserts the gate semantics stated in _uniswap_direct_forwarder_score's docstring
        # (slot 0 == predeploy, slot 1 resolved, L1 delay and admin resolved) -- a
        # characterization: if a future change adds an identity gate (must equal the V3
        # forwarder), update this vector; the finding below is unaffected by that.
        r, fake = self._different_dao_root()
        self.assertEqual(fake.unexpected, [])
        self.assertEqual(_vector(r), (80, 100, 75, 100, 100, 85))
        self.assertEqual(r["notes"][0], "feeToSetter() = %s" % OTHER_FORWARDER)
        self.assertEqual(r["notes"][1], "forwarder slot 0 = %s, slot 1 (L1 Governance Timelock) = %s" % (PREDEPLOY, OTHER_L1_TIMELOCK))
        self.assertNotEqual(OTHER_FORWARDER, UNI_FORWARDER)        # documented V3 forwarder, [SCOUT] section 4
        self.assertNotEqual(OTHER_L1_TIMELOCK, UNI_L1_TIMELOCK)    # documented V3 L1 timelock, [SCOUT] section 4

    def test_same_forwarder_claim_is_only_made_when_it_really_is_the_v3_forwarder(self):
        # Fixed 2026-09-20: the note "Same forwarder and same L1 Governance Timelock as the
        # already-tracked Uniswap V3 Factory (Base)" used to be appended unconditionally. The documented V3 forwarder
        # is 0x31FAfd48...72A9 and its L1 timelock 0x1a9C8182...35BC ([SCOUT] section 4). With a DIFFERENT forwarder and
        # a DIFFERENT L1 timelock (the companion test above: every gate still passes) the sameness claim is not made,
        # and the score is unchanged. The same defect class was fixed for Aerodrome's "zero owner overlap" note on
        # 2026-09-18.
        r, _ = self._different_dao_root()
        self.assertFalse(any("Same forwarder and same L1 Governance Timelock" in n for n in r["notes"]))
        self.assertTrue(any("NOT asserted to be the same DAO root as V3" in n for n in r["notes"]))
        self.assertEqual(_vector(r), (80, 100, 75, 100, 100, 85))

    def test_the_sameness_claim_is_made_when_both_addresses_match_the_v3_ones(self):
        # the published rows (V2 Factory and V4 PoolManager on Base) do share the V3 forwarder and L1 timelock
        r, _ = self._v2()
        self.assertTrue(any("Same forwarder and same L1 Governance Timelock as the already-tracked Uniswap V3 Factory" in n
                            for n in r["notes"]))
        self.assertFalse(any("NOT asserted to be the same DAO root" in n for n in r["notes"]))


# ===========================================================================
# score_moonwell_comptroller_base
# ===========================================================================
class TestMoonwellComptroller(unittest.TestCase):
    def _score(self, **wire_kwargs):
        fake = ReaderFake()
        wire_moonwell(fake, **wire_kwargs)
        install(self, fake)
        return scorers.score_moonwell_comptroller_base(BASE_W3), fake

    def _assert_chain_not_ok(self, r):
        # chain_ok False: adminKey 30, timelock 0, multisig stays "not applicable" 100.
        # composite floor(0.4*30 + 0.3*100 + 0 + 0.5) = floor(12 + 30 + 0.5) = 42.
        self.assertEqual(_vector(r), (30, 100, 0, 100, 100, 42))
        self.assertIn("only trusted sender is Moonwell's MULTICHAIN_GOVERNOR_V2_PROXY (chains/1.json): False", r["notes"])

    # --- happy path: the PUBLISHED score --------------------------------------
    def test_expected_sender_and_one_day_delay_reproduce_the_published_score(self):
        # [MAINT] table: Moonwell composite 71, "Scored like Aave V3 Base (65/100/50 -> 71)".
        # [READBACK] row 8: 65, 100, 50, 100, 100, 71.
        # Hand derivation: floor(0.4*65 + 0.3*100 + 0.3*50 + 0.5) = floor(26 + 30 + 15 + 0.5) = 71.
        r, _ = self._score()
        self.assertEqual(_vector(r), (65, 100, 50, 100, 100, 71))
        self.assertEqual(r["target"], MOONWELL)
        self.assertEqual(r["label"], "Moonwell Comptroller (Unitroller, Base)")

    def test_notes_carry_the_governor_delay_sender_guardian_and_disclosed_limits(self):
        r, _ = self._score()
        n = r["notes"]
        self.assertEqual(len(n), 7)
        self.assertEqual(n[0], "Unitroller.admin() = %s (TemporalGovernor)" % TEMPORAL_GOVERNOR)
        self.assertEqual(n[1], "TemporalGovernor.proposalDelay() = 86400s, trusted senders on Wormhole chain 2 (Ethereum) = "
                               "['0x8769b70ac7c93af0e75de0d69877709b66d75838']")
        self.assertEqual(n[2], "TemporalGovernor.owner() (guardian) = %s, guardianPauseAllowed = True" % MOONWELL_GUARDIAN)
        self.assertEqual(n[3], "guardian is a real Gnosis Safe: 3-of-5 -- can pause once and fast-track a valid VAA past the delay")
        self.assertEqual(n[4], "only trusted sender is Moonwell's MULTICHAIN_GOVERNOR_V2_PROXY (chains/1.json): True")

    def test_open_threads_are_disclosed_and_the_cross_exposure_note_closes_the_list(self):
        # The docstring's disclosed limits: L1 governor + Wormhole guardian set not verified;
        # pauseGuardian / supply-borrow cap guardian are bounded roles, disclosed not folded in.
        r, _ = self._score()
        self.assertIn("Open thread, disclosed rather than guessed", r["notes"][5])
        self.assertIn("NOT re-verified this pass", r["notes"][5])
        self.assertIn("Wormhole's own guardian set", r["notes"][5])
        self.assertIn("disclosed not folded in", r["notes"][5])
        # The last note is the scorer's own not-computed placeholder. The overlap pass keys on
        # this exact constant, so the test compares against it, and ALSO pins its documented
        # meaning (scorers.py comment above it: 100 = "not computed" for this target).
        self.assertEqual(r["notes"][6], scorers._CROSS_EXPOSURE_NOTE)
        for fragment in PLACEHOLDER_FRAGMENTS:
            self.assertIn(fragment, r["notes"][6])

    def test_reads_the_documented_shapes_and_each_governor_read_only_after_admin_resolved(self):
        # Pins the read shapes that were confirmed live ([MAINT]: proposalDelay() = 86,400 s,
        # allTrustedSenders(2), guardianPauseAllowed = true) so a refactor cannot silently
        # change what is asked of the chain. Order between independent reads is not pinned; the
        # dependencies are (every governor read needs admin(); the guardian Safe needs owner()).
        _, fake = self._score()
        admin_read = ("getter", MOONWELL, "admin")
        guardian_read = ("getter", TEMPORAL_GOVERNOR, "owner")
        governor_reads = [
            ("raw", TEMPORAL_GOVERNOR, "proposalDelay", ()),
            ("raw", TEMPORAL_GOVERNOR, "allTrustedSenders", (2,)),
            guardian_read,
            ("raw", TEMPORAL_GOVERNOR, "guardianPauseAllowed", ()),
        ]
        _assert_reads(self, fake, [admin_read] + governor_reads + [("safe", MOONWELL_GUARDIAN)],
                      must_precede=[(admin_read, g) for g in governor_reads]
                      + [(guardian_read, ("safe", MOONWELL_GUARDIAN))])
        self.assertTrue(all(e[1] is BASE_W3 for e in fake.log))
        self.assertEqual(_signature(fake.abis[(TEMPORAL_GOVERNOR, "proposalDelay")]), ("proposalDelay()", ["uint256"]))
        self.assertEqual(_signature(fake.abis[(TEMPORAL_GOVERNOR, "allTrustedSenders")]), ("allTrustedSenders(uint16)", ["bytes32[]"]))
        self.assertEqual(_signature(fake.abis[(TEMPORAL_GOVERNOR, "guardianPauseAllowed")]), ("guardianPauseAllowed()", ["bool"]))

    def test_only_wormhole_chain_2_is_asked_for_trusted_senders(self):
        # Disclosed limit ([MAINT] "Open threads": "only Wormhole chain ids 2/16/23/24/30 were
        # checked for senders" -- by hand): the scorer itself queries chain 2 and nothing else.
        _, fake = self._score()
        sender_reads = [e for e in fake.reads() if len(e) > 2 and e[2] == "allTrustedSenders"]
        self.assertEqual(sender_reads, [("raw", TEMPORAL_GOVERNOR, "allTrustedSenders", (2,))])

    # --- sender cross-check (live read vs chains/1.json's documented address) --
    def test_any_sender_set_other_than_exactly_the_expected_one_degrades(self):
        cases = {
            "an extra trusted sender": [SENDER, OTHER_SENDER],
            "the extra sender listed first": [OTHER_SENDER, SENDER],
            "a different single sender": [OTHER_SENDER],
            "no trusted sender": [],
            "the read reverting": None,
        }
        for name, senders in cases.items():
            with self.subTest(case=name):
                r, _ = self._score(senders=senders)
                self._assert_chain_not_ok(r)

    def test_sender_differing_in_one_byte_degrades(self):
        near_miss = bytes(12) + bytes.fromhex("8769b70ac7c93af0e75de0d69877709b66d75839")
        r, _ = self._score(senders=[near_miss])
        self._assert_chain_not_ok(r)

    def test_a_single_bit_flipped_at_any_of_the_20_byte_positions_degrades(self):
        # The scorer must compare the WHOLE 20-byte address, not a prefix/suffix: flip one bit in
        # each byte in turn (positions 0..19, including the middle bytes the docs never print).
        # This also shows SENDER (the fixture) equals the scorer's constant on all 20 bytes.
        for i in range(20):
            with self.subTest(byte=i):
                raw = bytearray(bytes.fromhex(SENDER_HEX))
                raw[i] ^= 0x01
                r, _ = self._score(senders=[bytes(12) + bytes(raw)])
                self._assert_chain_not_ok(r)

    def test_sender_is_decoded_from_the_low_20_bytes_of_the_bytes32(self):
        # allTrustedSenders returns bytes32 values (left-padded addresses); the scorer keeps the
        # last 40 hex chars, lower-case, and compares to the documented lower-case address.
        r, _ = self._score(senders=[bytes(SENDER)])
        self.assertIn("['0x8769b70ac7c93af0e75de0d69877709b66d75838']", r["notes"][1])
        self.assertEqual(r["adminKeyScore"], 65)

    def test_degraded_sender_note_lists_what_was_actually_read(self):
        r, _ = self._score(senders=[SENDER, OTHER_SENDER])
        self.assertIn("['0x8769b70ac7c93af0e75de0d69877709b66d75838', '0x%s']" % ("dd" * 20), r["notes"][1])

    # --- admin unresolved -------------------------------------------------------
    def test_unitroller_admin_unresolved_degrades_and_reads_nothing_further(self):
        r, fake = self._score(admin=None)
        self._assert_chain_not_ok(r)
        # Nothing is read on a None admin. Not only fake strictness: on a None address the real
        # readers return None only after scripts/lib/web3_utils.py::_retrying has slept
        # 0.4 + 0.8 + 1.2 = 2.4 s, per read (four reads here), so an unguarded read is real
        # wall-clock cost in the production run even though the score would not change.
        self.assertEqual(fake.reads(), [("getter", MOONWELL, "admin")])
        self.assertEqual(r["notes"][0], "Unitroller.admin() = None (TemporalGovernor)")
        self.assertIn("proposalDelay() = None", r["notes"][1])
        self.assertIn("trusted senders on Wormhole chain 2 (Ethereum) = []", r["notes"][1])
        self.assertFalse(any("guardian is a real Gnosis Safe" in n for n in r["notes"]))

    # --- timelock rules ---------------------------------------------------------
    def test_timelock_score_is_a_flat_50_for_any_positive_delay(self):
        # Capped: the guardian fast-track path sits outside the delay ([MAINT], scorer comment).
        # 1 s, 1 day, 7 days -> (65, 100, 50) -> 71.
        for delay in (1, 86400, 7 * 86400):
            with self.subTest(delay=delay):
                r, _ = self._score(delay=delay)
                self.assertEqual((r["adminKeyScore"], r["timelockScore"], r["compositeScore"]), (65, 50, 71))

    def test_zero_or_unread_delay_scores_timelock_zero_but_keeps_admin_65(self):
        # (65, 100, 0) -> floor(26 + 30 + 0 + 0.5) = floor(56.5) = 56.
        for delay in (0, None):
            with self.subTest(delay=delay):
                r, _ = self._score(delay=delay)
                self.assertEqual(_vector(r), (65, 100, 0, 100, 100, 56))

    def test_timelock_needs_both_the_expected_sender_and_a_delay(self):
        # A real delay does not rescue a wrong sender set: timelock is gated on chain_ok.
        r, _ = self._score(senders=[OTHER_SENDER], delay=86400)
        self.assertEqual((r["adminKeyScore"], r["timelockScore"]), (30, 0))

    # --- guardian: disclosed, not scored -----------------------------------------
    def test_guardian_variants_never_change_the_score(self):
        # Documented design: the guardian path is capped-for in timelockScore (50) and
        # disclosed in notes, not folded into any sub-score ([MAINT]: "Scored like Aave V3 Base
        # (65/100/50 -> 71)"; scorer docstring: the guardian is disclosed, the L1 governor and
        # Wormhole set are "NOT verified ... same capped treatment"). So NO guardian property --
        # including its Safe's strength -- may move any of the six numbers.
        cases = {
            "a real 3-of-5 Safe (the observed one)": dict(),
            "a weaker 2-of-4 Safe": dict(guardian_safe=(_synthetic(4, 0x5000), 2)),
            "a 1-of-1 Safe": dict(guardian_safe=(_synthetic(1, 0x5000), 1)),
            "a stronger 5-of-5 Safe": dict(guardian_safe=(_synthetic(5, 0x5000), 5)),
            "not a Safe (bare EOA / other contract)": dict(guardian_safe=None),
            "guardian read reverting": dict(guardian=None),
            "pause not allowed": dict(pause_allowed=False),
            "pause flag unread": dict(pause_allowed=None),
        }
        for name, kwargs in cases.items():
            with self.subTest(case=name):
                r, _ = self._score(**kwargs)
                self.assertEqual(_vector(r), (65, 100, 50, 100, 100, 71))

    def test_guardian_safe_note_only_appears_when_the_guardian_resolves_as_a_safe(self):
        r, _ = self._score(guardian_safe=None)
        self.assertFalse(any("guardian is a real Gnosis Safe" in n for n in r["notes"]))
        self.assertEqual(len(r["notes"]), 6)
        r, _ = self._score(guardian=None)
        self.assertFalse(any("guardian is a real Gnosis Safe" in n for n in r["notes"]))
        self.assertIn("TemporalGovernor.owner() (guardian) = None, guardianPauseAllowed = True", r["notes"])

    def test_guardian_safe_size_is_reported_from_the_live_read(self):
        r, _ = self._score(guardian_safe=(_synthetic(4, 0x5000), 2))
        self.assertIn("guardian is a real Gnosis Safe: 2-of-4 -- can pause once and fast-track a valid VAA past the delay", r["notes"])

    def test_guardian_pause_flag_is_reported_in_the_notes(self):
        r, _ = self._score(pause_allowed=False)
        self.assertIn("guardianPauseAllowed = False", r["notes"][2])

    def test_no_guardian_safe_read_when_the_guardian_did_not_resolve(self):
        # Same reason as the None-admin test: an unguarded Safe read on a None guardian is a
        # 2.4 s _retrying sleep per unresolved run in production, with no score change.
        _, fake = self._score(guardian=None)
        self.assertEqual([k for k, *_ in fake.reads()].count("safe"), 0)


# ===========================================================================
# _apply_intra_base_overlap
# ===========================================================================
def _entry(label, owners, cross=100, notes=None):
    return {"label": label, "rootSafeOwners": owners, "crossExposureScore": cross,
            "notes": [scorers._CROSS_EXPOSURE_NOTE] if notes is None else list(notes)}


def _overlap_note(labels, score):
    # GOLDEN MASTER of the note's current format (see the header): re-states the scorer's
    # sentence so a deletion or rewording is caught; the facts inside it (which targets share a
    # signer, the resulting score) are the hand-derived / published values asserted around it.
    return ("intra-Base overlap (live, this run): root Safe signers shared with " + ", ".join(labels)
            + " -> crossExposureScore %d" % score)


NO_OVERLAP_NOTE = "intra-Base overlap (live, this run): no root signer shared with another tracked Base target"


class TestApplyIntraBaseOverlap(unittest.TestCase):
    def test_the_placeholder_note_the_pass_removes_is_the_documented_not_computed_disclosure(self):
        # Several tests below build entries whose default note IS scorers._CROSS_EXPOSURE_NOTE and
        # expect the pass to remove it (the pass keys on that constant, so they must import it).
        # Pin what the constant MEANS independently, so it cannot be blanked or repurposed while
        # those tests keep agreeing with themselves. Documented in the scorers.py comment above it
        # and in [METH] crossExposureScore: "100 = no overlap found, or not computed for that target".
        for fragment in PLACEHOLDER_FRAGMENTS:
            self.assertIn(fragment, scorers._CROSS_EXPOSURE_NOTE)
        self.assertNotEqual(scorers._CROSS_EXPOSURE_NOTE, NO_OVERLAP_NOTE)

    def test_two_targets_on_one_safe_lose_20_each_as_published_for_aerodrome(self):
        # [MAINT] "CORRECTION -- Aerodrome V1 PoolFactory crossExposureScore 100 -> 80":
        # "Adding Slipstream put two tracked targets on the same Safe, so Aerodrome V1
        # drops from 100 to 80"; [READBACK] rows 2 and 5 both read crossExposure 80.
        # Hand derivation: one OTHER target shares a signer -> 100 - 20*1 = 80.
        v1 = _entry("Aerodrome Finance PoolFactory (Base)", list(AERO_SAFE_OWNERS))
        cl = _entry("Aerodrome Slipstream CLFactory (Base)", list(AERO_SAFE_OWNERS))
        scorers._apply_intra_base_overlap([v1, cl])
        self.assertEqual((v1["crossExposureScore"], cl["crossExposureScore"]), (80, 80))
        self.assertEqual(v1["notes"], [_overlap_note(["Aerodrome Slipstream CLFactory (Base)"], 80)])
        self.assertEqual(cl["notes"], [_overlap_note(["Aerodrome Finance PoolFactory (Base)"], 80)])

    def test_returns_none_and_mutates_in_place(self):
        a, b = _entry("A", _synthetic(3, 1)), _entry("B", _synthetic(3, 1))
        results = [a, b]
        self.assertIsNone(scorers._apply_intra_base_overlap(results))
        self.assertEqual(results, [a, b])
        self.assertEqual(a["crossExposureScore"], 80)

    def test_empty_and_single_result_lists_are_fine(self):
        scorers._apply_intra_base_overlap([])
        solo = _entry("Solo", _synthetic(3, 1))
        scorers._apply_intra_base_overlap([solo])
        self.assertEqual(solo["crossExposureScore"], 100)
        self.assertIn(NO_OVERLAP_NOTE, solo["notes"])

    def test_disjoint_safes_keep_100_and_get_the_no_overlap_note(self):
        a, b = _entry("A", _synthetic(3, 1)), _entry("B", _synthetic(3, 100))
        scorers._apply_intra_base_overlap([a, b])
        for e in (a, b):
            self.assertEqual(e["crossExposureScore"], 100)
            self.assertIn(NO_OVERLAP_NOTE, e["notes"])

    def test_no_overlap_branch_keeps_the_scorers_own_cross_exposure_note(self):
        a, b = _entry("A", _synthetic(3, 1)), _entry("B", _synthetic(3, 100))
        scorers._apply_intra_base_overlap([a, b])
        self.assertEqual(a["notes"], [scorers._CROSS_EXPOSURE_NOTE, NO_OVERLAP_NOTE])

    def test_overlap_branch_drops_the_stale_not_computed_note_and_keeps_other_notes_in_order(self):
        a = _entry("A", _synthetic(3, 1), notes=["first", scorers._CROSS_EXPOSURE_NOTE, "second"])
        b = _entry("B", _synthetic(3, 1))
        scorers._apply_intra_base_overlap([a, b])
        self.assertEqual(a["notes"], ["first", "second", _overlap_note(["B"], 80)])
        self.assertNotIn(scorers._CROSS_EXPOSURE_NOTE, a["notes"])

    def test_a_single_shared_signer_is_enough(self):
        # [METH]/docstring: "at least one resolved root signer". A owns 1..3, B owns 3..5:
        # exactly one address in common.
        a, b = _entry("A", _synthetic(3, 1)), _entry("B", _synthetic(3, 3))
        scorers._apply_intra_base_overlap([a, b])
        self.assertEqual((a["crossExposureScore"], b["crossExposureScore"]), (80, 80))

    def test_many_shared_signers_with_the_same_target_count_once(self):
        # Deduction is per OTHER TARGET, not per shared signer: 3 shared signers -> still -20.
        a, b = _entry("A", _synthetic(5, 1)), _entry("B", _synthetic(5, 3))
        scorers._apply_intra_base_overlap([a, b])
        self.assertEqual((a["crossExposureScore"], b["crossExposureScore"]), (80, 80))

    def test_signer_match_ignores_address_case(self):
        addr = _synthetic(1, 0xABCDEF)[0]
        self.assertNotEqual(addr, addr.lower())  # the fixture really is mixed-case
        a, b = _entry("A", [addr]), _entry("B", [addr.lower()])
        scorers._apply_intra_base_overlap([a, b])
        self.assertEqual((a["crossExposureScore"], b["crossExposureScore"]), (80, 80))

    def test_signer_match_ignores_case_on_both_sides_of_the_comparison(self):
        # One address in three spellings (EIP-55 checksum, all lower, all upper hex). Every pair
        # must match whichever side carries which spelling, so BOTH the target's own set and the
        # other target's set are case-folded: each entry sees the other two -> 100 - 40 = 60.
        checksum = _synthetic(1, 0xABCDEF)[0]
        lower, upper = checksum.lower(), "0x" + checksum[2:].upper()
        self.assertEqual(len({checksum, lower, upper}), 3)
        entries = [_entry("A", [checksum]), _entry("B", [lower]), _entry("C", [upper])]
        scorers._apply_intra_base_overlap(entries)
        self.assertEqual([e["crossExposureScore"] for e in entries], [60, 60, 60])
        # And in the other orientation (lower-case target listed first, checksum last).
        entries = [_entry("A", [lower]), _entry("B", [upper]), _entry("C", [checksum])]
        scorers._apply_intra_base_overlap(entries)
        self.assertEqual([e["crossExposureScore"] for e in entries], [60, 60, 60])

    def test_chain_of_overlaps_is_counted_per_target_not_transitively(self):
        # A-B share a signer, B-C share a different one, A-C share none:
        # A: 1 other -> 80; B: 2 others -> 100 - 40 = 60; C: 1 other -> 80.
        a = _entry("A", _synthetic(2, 1))            # {1, 2}
        b = _entry("B", _synthetic(2, 2) + _synthetic(1, 50))   # {2, 3, 50}
        c = _entry("C", _synthetic(2, 50))           # {50, 51}
        scorers._apply_intra_base_overlap([a, b, c])
        self.assertEqual((a["crossExposureScore"], b["crossExposureScore"], c["crossExposureScore"]), (80, 60, 80))
        self.assertEqual(b["notes"], [_overlap_note(["A", "C"], 60)])  # others listed in results order

    def test_others_are_listed_in_results_order_not_alphabetical_order(self):
        # The note lists the OTHER targets in the order they appear in `results` (the oracle's
        # index order), not sorted: with results Z, A, M, target A sees [Z, M] (sorted: [M, Z]).
        z, a, m = (_entry(n, list(AERO_SAFE_OWNERS)) for n in ("Z", "A", "M"))
        scorers._apply_intra_base_overlap([z, a, m])
        self.assertEqual(a["notes"], [_overlap_note(["Z", "M"], 60)])
        self.assertEqual(z["notes"], [_overlap_note(["A", "M"], 60)])
        self.assertEqual(m["notes"], [_overlap_note(["Z", "A"], 60)])

    def test_a_target_is_told_apart_by_identity_not_by_equal_content(self):
        # [METH]: "-20 per OTHER tracked target". Two distinct tracked targets whose result dicts
        # happen to be equal in every field are still two targets: each is an "other" for the
        # other one. (Value equality would let each exclude its twin and leave both at 100.)
        x = _entry("Same", list(AERO_SAFE_OWNERS))
        y = _entry("Same", list(AERO_SAFE_OWNERS))
        self.assertEqual(x, y)
        self.assertIsNot(x, y)
        scorers._apply_intra_base_overlap([x, y])
        self.assertEqual((x["crossExposureScore"], y["crossExposureScore"]), (80, 80))
        self.assertEqual(x["notes"], [_overlap_note(["Same"], 80)])

    def test_three_targets_on_one_safe_lose_40_each(self):
        entries = [_entry(n, list(AERO_SAFE_OWNERS)) for n in ("A", "B", "C")]
        scorers._apply_intra_base_overlap(entries)
        self.assertEqual([e["crossExposureScore"] for e in entries], [60, 60, 60])
        self.assertEqual(entries[0]["notes"], [_overlap_note(["B", "C"], 60)])

    def test_deduction_stacks_on_a_cross_ecosystem_score_already_lowered_by_the_scorer(self):
        # docstring: "Deducts ON TOP of any cross-ecosystem deduction already applied by
        # the scorer itself (Morpho)": 80 - 20 = 60.
        morpho_like = _entry("M", _synthetic(3, 1), cross=80)
        other = _entry("O", _synthetic(3, 1))
        scorers._apply_intra_base_overlap([morpho_like, other])
        self.assertEqual((morpho_like["crossExposureScore"], other["crossExposureScore"]), (60, 80))

    def test_score_never_goes_below_zero(self):
        # 6 targets on one Safe: each has 5 others -> 100 - 100 = 0 exactly. 7 and 8 targets
        # would give -20 and -40 -> clamped to 0 (max(0, ...)).
        for group_size, expected in ((6, 0), (7, 0), (8, 0)):
            with self.subTest(targets=group_size):
                entries = [_entry("T%d" % i, list(AERO_SAFE_OWNERS)) for i in range(group_size)]
                scorers._apply_intra_base_overlap(entries)
                self.assertEqual([e["crossExposureScore"] for e in entries], [expected] * group_size)
        clamped = _entry("Low", list(AERO_SAFE_OWNERS), cross=30)
        scorers._apply_intra_base_overlap([clamped, _entry("X", list(AERO_SAFE_OWNERS)), _entry("Y", list(AERO_SAFE_OWNERS))])
        self.assertEqual(clamped["crossExposureScore"], 0)  # 30 - 40 -> 0, not -10

    def test_the_zero_floor_is_exact_and_the_note_reports_the_floored_score(self):
        # [METH]: crossExposureScore = max(0, 100 - 20 * sharedGroupCount). Hand-computed, with
        # every row sitting on or across the boundary (the deduction is 20 per OTHER target):
        #   start 100, 5 others -> 0 exactly        start 20, 1 other  -> 0 exactly
        #   start 10,  1 other  -> -10 -> 0         start 30, 2 others -> -10 -> 0
        #   start 100, 6 others -> -20 -> 0         start 40, 1 other  -> 20 (one step above the floor)
        rows = [(100, 5, 0), (20, 1, 0), (10, 1, 0), (30, 2, 0), (100, 6, 0), (40, 1, 20)]
        for start, others, expected in rows:
            with self.subTest(start=start, others=others):
                target = _entry("T", list(AERO_SAFE_OWNERS), cross=start)
                peers = [_entry("P%d" % i, list(AERO_SAFE_OWNERS)) for i in range(others)]
                scorers._apply_intra_base_overlap([target] + peers)
                self.assertEqual(target["crossExposureScore"], expected)
                self.assertEqual(target["notes"][-1], _overlap_note(["P%d" % i for i in range(others)], expected))

    def test_four_overlaps_leave_20(self):
        five = [_entry("T%d" % i, list(AERO_SAFE_OWNERS)) for i in range(5)]   # each has 4 others: 100 - 80
        scorers._apply_intra_base_overlap(five)
        self.assertEqual({e["crossExposureScore"] for e in five}, {20})

    def test_targets_without_a_root_safe_are_untouched_and_never_counted_as_others(self):
        # DAO/Timelock-rooted targets (Uniswap, Compound, Aave, Moonwell) either omit
        # rootSafeOwners or carry it empty; they get no note and no deduction, and they
        # do not count as an "other" for a rooted target.
        rooted = _entry("Rooted", list(AERO_SAFE_OWNERS))
        dao_missing_key = {"label": "DAO-missing-key", "crossExposureScore": 100, "notes": [scorers._CROSS_EXPOSURE_NOTE]}
        dao_empty = _entry("DAO-empty", [])
        scorers._apply_intra_base_overlap([rooted, dao_missing_key, dao_empty])
        self.assertEqual(rooted["crossExposureScore"], 100)
        self.assertIn(NO_OVERLAP_NOTE, rooted["notes"])
        for untouched in (dao_missing_key, dao_empty):
            self.assertEqual(untouched["crossExposureScore"], 100)
            self.assertEqual(untouched["notes"], [scorers._CROSS_EXPOSURE_NOTE])

    def test_result_does_not_depend_on_the_order_of_the_results_list(self):
        def build():
            return [_entry("A", _synthetic(2, 1)), _entry("B", _synthetic(2, 2) + _synthetic(1, 50)), _entry("C", _synthetic(2, 50))]
        forward, backward = build(), list(reversed(build()))
        scorers._apply_intra_base_overlap(forward)
        scorers._apply_intra_base_overlap(backward)
        by_label = lambda es: {e["label"]: e["crossExposureScore"] for e in es}
        self.assertEqual(by_label(forward), by_label(backward))
        self.assertEqual(by_label(forward), {"A": 80, "B": 60, "C": 80})

    def test_published_cross_exposure_column_for_all_nine_base_targets(self):
        # Full set as it stood on 2026-09-19. Inputs (what the scorers emit before the pass):
        #   Morpho Blue        cross 80 (its own live Robinhood-committee check), 9 real owners
        #   Aave V3 Base       cross 80 (Arbitrum guardian check), NO rootSafeOwners (DAO executor)
        #   Aerodrome V1       cross 100, the 3-of-7 Safe
        #   Uniswap V3/V2/V4, Compound V3, Moonwell   cross 100, no rootSafeOwners
        #   Slipstream         cross 100, the SAME 3-of-7 Safe as Aerodrome V1
        # Expected = the crossExposure column of [READBACK] (indices 0..8):
        #   80, 80, 80, 100, 100, 80, 100, 100, 100
        # Only Aerodrome V1 and Slipstream share a signer, so exactly those two drop by 20.
        # What is OBSERVED is the readback itself (Morpho's cross stayed at its own 80: the pass
        # deducted nothing from it); that Morpho's 9 real owners do not intersect the Aerodrome
        # owner list holds here BY CONSTRUCTION (the Aerodrome list is synthetic, see header).
        # Seven of the nine expected values equal their inputs (an untouched pass-through, which
        # is exactly the "no deduction for DAO-rooted / non-sharing targets" claim); the logic is
        # exercised by the Aerodrome pair, and end to end by TestScoreAllPublishedReadback.
        def dao(label, cross=100):
            return {"label": label, "crossExposureScore": cross, "notes": [scorers._CROSS_EXPOSURE_NOTE]}
        results = [
            _entry("Morpho Blue (singleton, Base)", list(MORPHO_OWNERS), cross=80, notes=[]),
            dao("Aave V3 Base (PoolAddressesProvider)", cross=80),
            _entry("Aerodrome Finance PoolFactory (Base)", list(AERO_SAFE_OWNERS)),
            dao("Uniswap V3 Factory (Base)"),
            dao("Compound V3 (Comet, USDC market, Base)"),
            _entry("Aerodrome Slipstream CLFactory (Base)", list(AERO_SAFE_OWNERS)),
            dao("Uniswap V2 Factory (Base)"),
            dao("Uniswap V4 PoolManager (Base)"),
            dao("Moonwell Comptroller (Unitroller, Base)"),
        ]
        scorers._apply_intra_base_overlap(results)
        self.assertEqual([r["crossExposureScore"] for r in results], [80, 80, 80, 100, 100, 80, 100, 100, 100])
        self.assertIn(NO_OVERLAP_NOTE, results[0]["notes"])  # Morpho: rooted, nobody shares its signers


# ===========================================================================
# score_all(): the four functions wired together against the published state
# ===========================================================================
# [READBACK] getScore() on Base Sepolia after tx 0xc412f6dc...14fa1, indices 0..8:
#   (target, adminKey, multisig, timelock, oracleAuthority, crossExposure, composite)
PUBLISHED_READBACK = [
    ("0xBBBBBbbBBb9cC5e90e3b3Af64bdAF62C37EEFFCb", 65, 95, 0, 100, 80, 55),    # 0 Morpho Blue
    ("0xe20fCBdBfFC4Dd138cE8b2E6FBb6CB49777ad64D", 65, 100, 50, 100, 80, 71),  # 1 Aave V3 Base
    ("0x420DD381b31aEf6683db6B902084cB0FFECe40Da", 65, 65, 0, 100, 80, 46),    # 2 Aerodrome V1
    ("0x33128a8fC17869897dcE68Ed026d694621f6FDfD", 80, 100, 75, 100, 100, 85),  # 3 Uniswap V3
    ("0xb125E6687d4313864e53df431d5425969c15Eb2F", 75, 100, 65, 100, 100, 80),  # 4 Compound V3
    ("0x5e7BB104d84c7CB9B682AaC2F3d509f5F406809A", 65, 65, 0, 100, 80, 46),    # 5 Slipstream
    ("0x8909Dc15e40173Ff4699343b6eB8132c65e18eC6", 80, 100, 75, 100, 100, 85),  # 6 Uniswap V2
    ("0x498581fF718922c3f8e6A244956aF099B2652b2b", 80, 100, 75, 100, 100, 85),  # 7 Uniswap V4
    ("0xfBb21d0380beE3312B33c4353c8936a0F13EF26C", 65, 100, 50, 100, 100, 71),  # 8 Moonwell
]
# PUBLISHED_READBACK above is pinned VERBATIM to the committed CSV (TestFixtureProvenance checks
# this byte for byte) -- never edit it to reflect a later drift or a newly added target. Both go
# in a SINCE_PUBLISHED-style override or, for genuinely new targets, a separate list instead; see
# TIMELOCK_COMPOSITE_SINCE_PUBLISHED and MORPHO_VAULTS_READBACK below.

# 2026-09-25: timelockScore capped at 60 for the pauseGuardian bypass (commit d6dca5e, same fix
# already applied to test_base_ecosystem_scorers.py and test_arbitrum_ecosystem_scorers.py -- this
# third fixture file was missed by that pass, found running the full suite before committing the
# controller-concentration work below, not by re-reading that earlier diff). Column indices match
# _vector()'s tuple: 2 = timelockScore, 5 = compositeScore.
TIMELOCK_COMPOSITE_SINCE_PUBLISHED = {4: (60, 78)}

# Added 2026-09-25 (commit 15543f2): the 4 new Morpho V1 vaults, appended at the end of
# SIMPLE_SCORERS so the original 9 above keep their published indices 0-8 and PUBLISHED_READBACK
# stays untouched. A SEPARATE list, not folded into PUBLISHED_READBACK, because these were never
# on the 2026-09-19 CSV -- there is no historical row to pin, only today's live read (verified
# directly against chains/base-ecosystem/scorers.py, 2026-09-25) reproduced by the SYNTHETIC wiring
# in wire_morpho_vaults(). crossExposure 60 (not the standalone 80) on the two Steakhouse-rooted
# vaults is _apply_intra_base_overlap() compounding their shared rootSafeOwners with EACH OTHER,
# exercised here for the first time by this fixture, not asserted before.
MORPHO_VAULTS_READBACK = [
    (GAUNTLET_VAULT, 60, 65, 55, 100, 100, 60),                # 9 Gauntlet USDC Prime
    (SPARK_VAULT, 60, 55, 75, 100, 100, 63),                   # 10 Spark USDC Vault
    (STEAKHOUSE_USDC_BASE_VAULT, 70, 50, 75, 100, 60, 66),     # 11 Steakhouse USDC
    (GROVE_STEAKHOUSE_VAULT, 70, 50, 75, 100, 60, 66),         # 12 Grove x Steakhouse USDC High Yield
]

# What the scorers return NOW where it differs from what was published on 2026-09-19 (PUBLISHED_READBACK stays
# pinned to the committed CSV). 2026-09-20: the three Uniswap targets share one L1 Timelock root with 8 more tracked
# targets on 4 other ecosystems, so crossExposure folds from 100 to 80 (composite is unchanged). Not on-chain until the
# next Base re-push.
CROSS_EXPOSURE_SINCE_PUBLISHED = {3: 80, 6: 80, 7: 80}

# The Arbitrum-shared Aave guardian owner set: [AAVE] documents them only by 8-hex prefixes
# (0xDA5Ae43e..., 0x1e380435..., ... -- tied to these values by TestFixtureProvenance); the full
# addresses are the dated snapshot copied from score_aave_v3_base in scorers.py, so they are NOT
# independently documented in full. Only needed to reproduce Aave's published cross 80.
ARB_AAVE_GUARDIAN_OWNERS = [_cs(a) for a in (
    "0xDA5Ae43e179987a66B9831F92223567e1F38BE7D", "0x1e3804357eD445251FfECbb6e40107bf03888885",
    "0x4f96743057482a2E10253AFDacDA3fd9CF2C1DC9", "0xebED04E9137AfeBFF6a1B97aC0adf61a544eFE29",
    "0xbd4DCfA978c6D0d342cE36809AfFFa49d4B7f1F7", "0xA3103D0ED00d24795Faa2d641ACf6A320EeD7396",
    "0x936CD9654271083cCF93A975919Da0aB3Bc99EF3", "0x0D2394C027602Dc4c3832Ffd849b5df45DBac0E9",
    "0x4C30E33758216aD0d676419c21CB8D014C68099f",
)]


def wire_aerodrome_v1(fake, voter_governor=AERO_SAFE):
    fake.raw[(AERO_POOLFACTORY, "owner", ())] = None            # [AERO]: owner() reverts by design
    fake.getters[(AERO_POOLFACTORY, "pauser")] = AERO_SAFE
    fake.getters[(AERO_POOLFACTORY, "feeManager")] = AERO_SAFE
    fake.getters[(AERO_POOLFACTORY, "voter")] = AERO_VOTER
    fake.getters[(AERO_VOTER, "governor")] = voter_governor
    fake.getters[(AERO_VOTER, "emergencyCouncil")] = AERO_COUNCIL
    fake.safes[AERO_SAFE] = (AERO_SAFE_OWNERS, 3)
    fake.safes[AERO_COUNCIL] = (AERO_COUNCIL_OWNERS, 3)


def wire_the_five_older_targets_that_are_not_under_test(fake):
    """Morpho, Aave, Uniswap V3, Compound at their published state. Their scorers are
    covered elsewhere; they are wired here only so score_all() runs the full 9.
    SYNTHETIC placeholders (author-chosen, NOT observations): Aave's executor and payloads
    controller, Compound's proxy admin and L1 governance timelock. The published vectors of
    those targets are therefore fixed by this wiring, and they are outside the four functions
    under test; what is asserted for them is only that score_all() places them at the right
    index and leaves them un-shared."""
    fake.getters[(MORPHO, "owner")] = MORPHO_SAFE
    fake.safes[MORPHO_SAFE] = (MORPHO_OWNERS, 5)                                   # [MAINT]: 5-of-9

    provider, guardian = "0xe20fCBdBfFC4Dd138cE8b2E6FBb6CB49777ad64D", _cs("0x360c0a69Ed2912351227a0b745f890CB2eBDbcFe")
    executor, payloads = _synthetic(1, 0x6001)[0], _synthetic(1, 0x6002)[0]
    fake.getters[(provider, "owner")] = executor
    fake.raw[(provider, "getACLAdmin", ())] = executor
    fake.getters[(executor, "owner")] = payloads
    fake.getters[(payloads, "owner")] = executor
    fake.raw[(payloads, "getExecutorSettingsByAccessControl", (1,))] = (executor, 86400)
    fake.raw[(payloads, "guardian", ())] = guardian
    fake.safes[guardian] = (ARB_AAVE_GUARDIAN_OWNERS, 5)

    wire_aerodrome_v1(fake)

    v3, adapter = "0x33128a8fC17869897dcE68Ed026d694621f6FDfD", _cs("0xaBEA76658b205696d49B5F91b2a03536cB8A3bE1")
    fake.getters[(v3, "owner")] = adapter                                          # [SCOUT] section 4
    fake.getters[(adapter, "owner")] = UNI_FORWARDER
    fake.slots[(UNI_FORWARDER, SLOT0)] = PREDEPLOY
    fake.slots[(UNI_FORWARDER, SLOT1)] = UNI_L1_TIMELOCK
    fake.raw[(UNI_L1_TIMELOCK, "delay", ())] = UNI_L1_DELAY
    fake.raw[(UNI_L1_TIMELOCK, "admin", ())] = UNI_GOVERNOR_BRAVO

    comet, local_timelock = "0xb125E6687d4313864e53df431d5425969c15Eb2F", _cs("0xCC3E7c85Bb0EE4f09380e041fee95a0caeDD4a02")
    bridge_receiver = _cs("0x18281dfC4d00905DA1aaA6731414EABa843c468A")            # [SCOUT] section 5
    proxy_admin, gov_timelock = _synthetic(1, 0x6003)[0], _synthetic(1, 0x6004)[0]
    fake.getters[(comet, "governor")] = local_timelock
    fake.slots[(comet, scorers.EIP1967_ADMIN_SLOT)] = proxy_admin
    fake.getters[(proxy_admin, "owner")] = local_timelock
    fake.raw[(local_timelock, "delay", ())] = 86400
    fake.getters[(local_timelock, "admin")] = bridge_receiver
    fake.getters[(bridge_receiver, "govTimelock")] = gov_timelock
    fake.getters[(bridge_receiver, "localTimelock")] = local_timelock
    # ADDED 2026-09-20: the Compound scorer now also reads pauseGuardian (its committee is folded into crossExposure when it
    # equals the L1/Arbitrum guardian's, see test_base_ecosystem_scorers.py). Wired here with an UNRELATED synthetic committee so
    # this fixture keeps reproducing the 2026-09-19 published readback (crossExposure 100).
    pause_guardian = _synthetic(1, 0x6005)[0]
    fake.getters[(comet, "pauseGuardian")] = pause_guardian
    fake.safes[pause_guardian] = (_synthetic(9, 0x6100), 5)


class TestScoreAllPublishedReadback(unittest.TestCase):
    def _run(self, fake):
        w3 = FakeBaseW3(code_sizes={_cs("0xaBEA76658b205696d49B5F91b2a03536cB8A3bE1"): 7266})  # [SCOUT]: 7,266-byte adapter
        install(self, fake)
        return scorers.score_all(w3)

    def _wire_everything(self):
        fake = ReaderFake()
        wire_the_five_older_targets_that_are_not_under_test(fake)
        wire_slipstream(fake)
        wire_forwarder(fake, UNI_V2_FACTORY, "feeToSetter")
        wire_forwarder(fake, UNI_V4_POOLMANAGER, "owner")
        wire_moonwell(fake)
        wire_morpho_vaults(fake)
        return fake

    def test_all_nine_targets_reproduce_the_published_readback_in_oracle_index_order(self):
        results = self._run(self._wire_everything())
        full_expected = PUBLISHED_READBACK + MORPHO_VAULTS_READBACK
        self.assertEqual([r["target"] for r in results], [row[0] for row in full_expected])
        for i, (row, r) in enumerate(zip(full_expected, results)):
            with self.subTest(index=i, label=r["label"]):
                expected = list(row[1:])
                if i in CROSS_EXPOSURE_SINCE_PUBLISHED:
                    expected[4] = CROSS_EXPOSURE_SINCE_PUBLISHED[i]  # crossExposure column
                if i in TIMELOCK_COMPOSITE_SINCE_PUBLISHED:
                    expected[2], expected[5] = TIMELOCK_COMPOSITE_SINCE_PUBLISHED[i]  # timelockScore, compositeScore columns
                self.assertEqual(_vector(r), tuple(expected))

    def test_slipstream_and_aerodrome_notes_name_each_other_after_the_overlap_pass(self):
        results = self._run(self._wire_everything())
        v1, cl = results[2], results[5]
        self.assertIn(_overlap_note(["Aerodrome Slipstream CLFactory (Base)"], 80), v1["notes"])
        self.assertIn(_overlap_note(["Aerodrome Finance PoolFactory (Base)"], 80), cl["notes"])
        self.assertNotIn(scorers._CROSS_EXPOSURE_NOTE, v1["notes"])

    def test_moonwell_and_the_uniswap_forwarders_are_not_part_of_the_signer_overlap(self):
        results = self._run(self._wire_everything())
        for i in (6, 7, 8):
            with self.subTest(index=i):
                self.assertNotIn("rootSafeOwners", results[i])
                self.assertFalse(any("intra-Base overlap" in n for n in results[i]["notes"]))

    def test_no_intra_base_overlap_is_reported_if_slipstream_moves_to_its_own_safe(self):
        # Counter-factual of the published correction: give Slipstream a Safe with disjoint
        # owners and Aerodrome V1 goes back to 100 (nothing shares a signer any more).
        fake = self._wire_everything()
        other_safe = _cs("0x" + "b7" * 20)
        wire_slipstream(fake, owner=other_safe, safe=(_synthetic(7, 0x7000), 3))
        results = self._run(fake)
        self.assertEqual((results[2]["crossExposureScore"], results[5]["crossExposureScore"]), (100, 100))
        self.assertEqual(results[5]["compositeScore"], 46)  # a different Safe of the same 3-of-7 shape scores the same

    def test_characterization_slipstream_role_divergence_hides_the_shared_safe_from_the_overlap_pass(self):
        # CHARACTERIZATION of current, arguably questionable behaviour (see findings), NOT a
        # documented requirement: a Slipstream whose fee managers moved off the owner degrades to
        # the floor AND stops being counted as sharing Aerodrome's Safe, although owner() is still
        # that very Safe. Aerodrome V1 therefore reads 100. What IS documented is only that the
        # pass counts targets with a RESOLVED root signer set ([METH]/docstring: "at least one
        # resolved root signer"), and that a degraded Slipstream exposes none (rootSafeOwners []).
        # If the scorer is changed to keep the owner Safe's signers on role divergence, this test
        # is expected to break and be rewritten, not "fixed" back.
        fake = self._wire_everything()
        wire_slipstream(fake, swap=OTHER)
        results = self._run(fake)
        self.assertEqual(_vector(results[5]), (20, 0, 0, 100, 100, 8))
        self.assertEqual(results[2]["crossExposureScore"], 100)


# ===========================================================================
# Fixture provenance: the citations in the comments above, checked against the
# cited documents themselves (offline, read-only, deterministic). If a document
# is edited so that a cited value is no longer there, these fail instead of the
# citation silently rotting.
# ===========================================================================
DOC_MAINT = "chains/base-ecosystem/data/scored_targets_2026-09-19-maintenance.md"
DOC_READBACK = "chains/base-ecosystem/data/oracle_readback_2026-09-19.csv"
DOC_AERO = "chains/base-ecosystem/data/finding_2026-09-18-aerodrome-voter-governor-identity.md"
DOC_SCOUT = "chains/base-ecosystem/data/scouted_targets_2026-09-16.md"
DOC_MORPHO = "data/finding_2026-09-19-base-morpho-blue-robinhood-overlap.md"
DOC_AAVE = "data/finding_2026-09-17-cross-ecosystem-aave-guardian-overlap.md"
DOC_METH = "METHODOLOGY.md"


def _doc_path(relative_path):
    return os.path.abspath(os.path.join(REPO_ROOT, relative_path))


def _doc_text(relative_path):
    """The document, lower-cased with all whitespace runs collapsed (so a line break inside a
    sentence does not matter)."""
    with open(_doc_path(relative_path), encoding="utf-8") as fh:
        return " ".join(fh.read().lower().split())


class TestFixtureProvenance(unittest.TestCase):
    def test_published_readback_table_equals_the_committed_csv_row_for_row(self):
        with open(_doc_path(DOC_READBACK), encoding="utf-8", newline="") as fh:
            rows = list(csv.DictReader(fh))
        from_csv = [(r["target"], int(r["adminKey"]), int(r["multisig"]), int(r["timelock"]),
                     int(r["oracleAuthority"]), int(r["crossExposure"]), int(r["composite"])) for r in rows]
        self.assertEqual([int(r["index"]) for r in rows], list(range(9)))
        self.assertEqual(from_csv, PUBLISHED_READBACK)

    def test_addresses_cited_as_real_appear_in_full_in_the_document_cited_for_them(self):
        cited = {
            DOC_MAINT: {
                "Slipstream CLFactory": SLIPSTREAM, "Aerodrome Safe": AERO_SAFE, "Uniswap V2 Factory": UNI_V2_FACTORY,
                "Uniswap V4 PoolManager": UNI_V4_POOLMANAGER, "Uniswap forwarder": UNI_FORWARDER,
                "Uniswap L1 timelock": UNI_L1_TIMELOCK, "Uniswap GovernorBravo": UNI_GOVERNOR_BRAVO,
                "Moonwell Unitroller": MOONWELL, "TemporalGovernor": TEMPORAL_GOVERNOR,
                "Moonwell guardian Safe": MOONWELL_GUARDIAN, "Moonwell guardian owner": MOONWELL_GUARDIAN_OWNERS[0],
                "Morpho Blue": MORPHO, "Morpho owner Safe": MORPHO_SAFE,
            },
            DOC_AERO: {"Aerodrome Safe": AERO_SAFE, "Aerodrome Voter": AERO_VOTER, "emergency council": AERO_COUNCIL},
            DOC_SCOUT: {"Aerodrome PoolFactory": AERO_POOLFACTORY, "Uniswap forwarder": UNI_FORWARDER,
                        "Uniswap L1 timelock": UNI_L1_TIMELOCK},
            DOC_MORPHO: {"Morpho owner %d" % i: a for i, a in enumerate(MORPHO_OWNERS)},
        }
        for doc, addresses in cited.items():
            text = _doc_text(doc)
            for name, address in addresses.items():
                with self.subTest(document=doc, address=name):
                    self.assertIn(address.lower(), text)

    def test_moonwell_sender_prefix_and_suffix_match_the_abbreviation_printed_in_the_maintenance_note(self):
        # The docs never print the full 20 bytes (KNOWN LIMIT in the header); pin what they do print.
        abbreviated = "0x%s...%s" % (SENDER_HEX[:8], SENDER_HEX[-4:])
        self.assertEqual(abbreviated, "0x8769b70a...5838")
        self.assertIn(abbreviated, _doc_text(DOC_MAINT))
        self.assertIn("multichain_governor_v2_proxy", _doc_text(DOC_MAINT))

    def test_aave_guardian_owner_snapshot_matches_the_prefixes_documented_in_the_finding(self):
        text = _doc_text(DOC_AAVE)
        for i, owner in enumerate(ARB_AAVE_GUARDIAN_OWNERS):
            with self.subTest(owner=i):
                self.assertIn(owner[:10].lower() + "...", text)
        self.assertIn("0x360c0a69ed2912351227a0b745f890cb2ebdbcfe", text)  # the Base-side Safe holding them
        self.assertIn("5-of-9", text)

    def test_fixture_sizes_match_the_documented_threshold_and_owner_counts(self):
        maint, aero, morpho = _doc_text(DOC_MAINT), _doc_text(DOC_AERO), _doc_text(DOC_MORPHO)
        self.assertEqual(len(AERO_SAFE_OWNERS), 7)
        self.assertIn("3-of-7 safe", maint)
        self.assertEqual(len(MOONWELL_GUARDIAN_OWNERS), 5)
        self.assertIn("3-of-5 safe `%s`" % MOONWELL_GUARDIAN.lower(), maint)
        self.assertEqual(len(AERO_COUNCIL_OWNERS), 5)
        self.assertIn("separate safe, 3-of-5, zero owner overlap", aero)
        self.assertEqual(len(MORPHO_OWNERS), 9)
        self.assertIn("5-of-9", morpho)
        self.assertFalse(set(AERO_COUNCIL_OWNERS) & set(AERO_SAFE_OWNERS))  # "zero owner overlap", by construction

    def test_the_formulas_used_for_every_hand_derivation_are_the_ones_in_the_methodology(self):
        text = _doc_text(DOC_METH)
        for formula in (
            "compositescore = floor(0.4 * adminkeyscore + 0.3 * multisigscore + 0.3 * timelockscore + 0.5)",
            "min(100, threshold * 15 + max(0, ownercount - threshold) * 5)",
            "crossexposurescore = max(0, 100 - 20 * sharedgroupcount)",
            "scores 20 as an explicit",  # the unresolved-authority floor used by the degraded paths
        ):
            with self.subTest(formula=formula):
                self.assertIn(formula, text)


if __name__ == "__main__":
    unittest.main()
