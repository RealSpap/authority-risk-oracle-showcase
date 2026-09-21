"""
Unit tests that execute the REAL bodies of five `chains/solana/scorers.py`
functions which, before this file, were only ever checked by live runs
against Solana Mainnet Beta (coverage measured 2026-09-20: statements NOT
run / total): `score_marinade` (48/49), `score_solend_dao_governance`
(40/41), `score_meteora_damm_v2` (21/22), `score_all` (9/10) and
`_resolve_legacy_serum_multisig` (8/9).

Everything here is OFFLINE. The scorers import `sol_read` as a module
(`import sol_read`), so the reader functions they call are PATCHED BY NAME
on that module object (`read_program`, `read_keytype`, `read_realm`,
`read_governance`, `read_governance_v2`, `read_squadsv3`,
`read_marinade_state`, `read_legacy_serum_multisig`,
`list_token_owner_records`, `read_mint`) -- the project's usual "patch the
imported name, not the transport" convention. `sol_read.rpc` and
`sol_read.acct` are ALSO patched, to raise, so a reader this file forgot to
patch fails loudly instead of touching the network. The pure offline
primitives (`find_program_address`, `on_curve`, `b58`, `b58dec`) are NOT
patched: the scorers derive real PDAs with them, and the fixtures below are
real accounts whose PDA relationships are documented, so the real derivation
is part of what is being checked.

FIXTURE PROVENANCE. Every expected number is either (a) a published value
copied from a data note / the deploy README, with the file cited next to
it, or (b) hand-derived from the written formula in METHODOLOGY.md 6.1
(`_composite = floor(0.4 a + 0.3 m + 0.3 t + 0.5)`; Squads-v3-shaped
multisig `admin = 40 + min(20, 5(t-1))`, `multisig = min(100, round(15 t + 40
t/n))`, `timelock = 0`; Realms countable council `admin = 60 + min(30,
5(t-1))`, same multisig formula; on-curve `5/0/0`; off-curve unresolved
`20/0/0`; `None` `100/100/100`; delay curve `0 -> 0`, `d < 24h -> round(50
d/24)`, `d >= 24h -> min(80, 50 + min(30, round(10 (d/24 - 1))))`), with the
arithmetic written in a comment. NOTHING was obtained by running the
function under test and copying its output. Real inputs used:

  * Marinade legacy 6-of-13 multisig `magrsHF...`: the EXACT account bytes
    fetched live on 2026-09-18 (`test_marinade_liquid_staking.py`,
    `data/scored_targets_2026-09-18-marinade-liquid-staking.md`), decoded
    with the real reader; its signer PDA `551FBX...` (bump 253) and the
    `State.admin_authority` native-treasury PDA `42VJbD...` are checked
    against the documented addresses in `TestFixtureProvenance`.
  * Solend DAO realm / governance / governance-program values:
    `data/methodology_test_2026-09-17-solend-governance.md` (live reads).
  * Meteora DAMM v2 upgrade path (Squads v3 `CoEsyk...`, authority index 1
    `JADaUV...`, 4-of-7): `data/scouted_targets_2026-09-17-run2.md` row 7
    (which also publishes the 55 / 83 / 0, composite 47 upper bound the
    "ADMINS floor removed" tests below reproduce) and
    `data/scored_targets_2026-09-18-defi-config-admins.md` (published
    5 / 0 / 0, composite 2).
  * PROVENANCE LIMIT, Meteora `ADMINS[]`: the two full keys are recorded
    in exactly one place in the repository, `scorers.py`
    `METEORA_DAMM_V2_ADMINS` (and the regression tests that copy it). The
    data note above names the upstream file (`MeteoraAg/damm-v2`
    `programs/cp-amm/src/instructions/admin/auth.rs`) and the regression
    test, but does NOT print the addresses; the upstream source is not
    vendored or hash-pinned here. So `METEORA_ADMINS` below is a change
    detector against `scorers.py`, not an independent confirmation of
    the addresses. What IS independent: the on-curve check (the real
    `sol_read.on_curve`), and the key prefixes `5unTfT2...` / `DHLXnJd...`
    which `score_meteora_damm_v2`'s docstring records.
  * The individual member keys of Meteora's 7-key Squads multisig and the
    four non-`8HVYKg...` Marinade council seats are NOT recorded in the
    repository (only prefixes / counts are), so those are SYNTHETIC keys
    (`_key(n)`); no expected score depends on which keys they are. The
    signer-set and cross-exposure assertions are therefore only about set
    arithmetic over those inventions, not about real members.
  * Marinade governance `M5Fg6G...`'s `voting_base_time`/`cooloff`/
    `hold-up` are NOT recorded in any data file (only "community Disabled,
    council YesVotePercentage(50%)" is). The fixture assumes voting 3 days,
    cool-off 0, hold-up 0, back-solved from the 2026-09-18 note's Path B
    timelock of 70 under the additive formula that existed that day
    (72 h -> 50 + round(10 * (3 - 1)) = 70). The back-solve is not unique
    (voting 2 d + hold-up 1 d also gives 72 h); the published 45 is
    insensitive to it (Path A's timelock of 0 dominates).
  * PROVENANCE LIMIT, Path B timelock: no real published number exists
    under the current formula. The 2026-09-18 Marinade note lists Path B
    as 70 / 69 / 70, but its timelock element came from the additive
    voting + cool-off + hold-up curve that METHODOLOGY.md section 7's
    2026-09-19 changelog row replaced by "hold-up alone" in the same
    change as the code. Every Path B timelock asserted below is therefore
    hand-derived from that reconciled written curve; spec and code were
    changed together, so agreement between them is not independent
    evidence for the timelock element specifically. Only the admin and
    multisig elements (70 / 69) are reproduced from a published value.
  * Cross-exposure: the README publishes Meteora 60, Jupiter v6 40,
    Jupiter Perps 40. `scouted_targets_2026-09-17-run2.md` documents only a
    GROUP-level overlap (meteora <-> jupiter, one shared key `CHRDWW...`
    inside the Jupiter Perps 4-of-8, group score 80). Which two scored
    targets Meteora overlaps with at target level is not recorded, so the
    stand-in targets in `test_two_targets_sharing_a_signer_...` are
    invented; that test validates the `max(0, 100 - 20 n)` arithmetic
    (METHODOLOGY.md section 4), not a reproduction of the published 60.

One test is `unittest.expectedFailure` on purpose (the council weight vs signers finding): it asserts the
DOCUMENTED value and the code currently computes something else. It is
reported as a finding, not bent to pass (see the test's comment).

"ADMINS floor removed" tests: the hardcoded `ADMINS[]` path always scores
(5, 0, 0) and `min()` makes that floor invisible to everything Path A does
(any Path A value >= (5, 0, 0) yields the same combined score). To exercise
the composition logic itself, some Meteora tests replace ONLY the
`on_curve` result with a neutral (100, 100, 100) test double. The expected
numbers in those tests are the documented upper bound (55 / 83 / 0 -> 47)
or hand arithmetic, never the function's output.
"""
import contextlib
import copy
import importlib.util
import io
import os
import sys
import unittest
from unittest import mock

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


solana = _load_module("aro_test_solana_scorer_bodies", "chains/solana/scorers.py")
# The module object scorers.py's own `import sol_read` resolved to -- the one
# whose reader functions the scorers actually call.
sol_read = solana.sol_read

SYSTEM_PROGRAM = "11111111111111111111111111111111"
BPF_LOADER_V3 = "BPFLoaderUpgradeab1e11111111111111111111111"


def _key(n):
    """A validly-shaped SYNTHETIC 32-byte pubkey (base58 of 32 copies of byte
    `n`). Used only where the repository records no real key (see module
    docstring); no expected score depends on which key it is."""
    return sol_read.b58(bytes([n]) * 32)


# ---------------------------------------------------------------------------
# Real Marinade inputs (data/scored_targets_2026-09-18-marinade-liquid-staking.md)
# ---------------------------------------------------------------------------
MARINADE_PROGRAM = "MarBmsSgKXdrN1egZf5sqe1TMai9K1rChYNDJgjq7aD"
MARINADE_STATE = "8szGkuLTAux9XMgZ2vtY39jVSowEcpBfFfD8hXSEqdGC"
MARINADE_MSOL_MINT = "mSoLzYCxHdYgdzU16g5QSh3i5K3z3KZK7ytfqcJm7So"
MARINADE_MULTISIG_PROGRAM = "msigmtwzgXJHj2ext4XJjCDmpbcMuufFb5cHuwg6Xdt"
MARINADE_UPGRADE_MS = "magrsHFQxkkioAy45VWnZnFBBdKVdy2ZiRoRGYT9Wed"
# Live program-upgrade authority = the multisig's signer PDA, seeds
# [multisig_pubkey], bump = stored nonce 253 (same file, "Path A").
MARINADE_UPGRADE_AUTHORITY = "551FBXSXdhcRDDkdcb3ThDRg84Mwe5Zs6YjJ1EEoyzBp"
MARINADE_GOV_PROGRAM = "GovMaiHfpVPw8BAM1mbdzgmSZYDw2tdP32J2fapoQoYs"
MARINADE_REALM = "899YG3yk4F66ZgbNWLHriZHTXSKk9e1kvsKEquW7L6Mo"
MARINADE_GOVERNANCE = "M5Fg6GipNvPzWgXNr5wj1EDcp8GB9J53cgyE7YGYLbL"
MARINADE_COUNCIL_MINT = "6MGwpuJ5YE1c8jJaF8FKurQdDJeYRf1adX76dovkXxRs"
# State.admin_authority = native-treasury PDA of MARINADE_GOVERNANCE (same file, "Path B").
MARINADE_ADMIN_AUTHORITY = "42VJbDihcS81YJPbuhHnHgvo1ehu42j8VK9sNwrnAarR"
# The one council seat whose owner is documented: it is ALSO owner #6 of the
# 6-of-13 upgrade multisig (same file, "Cross-exposure, live-detected").
MARINADE_COUNCIL_REAL_OWNER = "8HVYKgq2PA4SCDuPZSfHBH1aupTBJYPVru6kq3UfuSX9"

# Exact base64 bytes of the real Marinade legacy multisig account, fetched
# live from Solana Mainnet Beta on 2026-09-18 (identical to the constant in
# test_marinade_liquid_staking.py).
LEGACY_MULTISIG_B64 = (
    "4HR5ukShT+wNAAAAa1Y09sy89Lzydy8G0GXp4AkLfSuiY13iv8oiI7rXT5Uk1dz1+v/NoHUMouHBpE6dSWLHj82IN/aJD1R1uRZoLq94Erew5MPzyQFt"
    "S2yJqnCc4CgTbscdZSTrmdbfyBhwq6WhhsMStmP68sR+I38GLzJZplQyYahnZ/3xsmcR/AlQDfg0K+06fV/ahebbPXm4G9kYs25KbWFQPqXYy36/RZKl"
    "kx87Gw/N9KG3SXmuDcDkwB4509kFm9/IspE3egNebDtfKzaM4fZjPRe2nhdYdyZcw65rI9Y5iANP3epL4TjGMiVc5PXc8cIb9UeM1dOsa59aFI3p1Eyt"
    "C/qdgJjG3ZZcACCTi+yToGlT38pqPih6qA+KtszslhjUUl0oaRQH4iSH27V1qLfA7OMudff8gd1dfyO4fmQHNP9VI+m1IkZY8CaCN9kiKOLGb2H0cyBm"
    "e8GoEJ8gRMVwSPM2Qn5U1SKvETqmpyblytCLcltKe1Vuuuh0DMPTnN1H3z3QKqYESfOv6E8sbK3nigXtYf7FSABixk/m2c5R+5SzEU2nolwGAAAAAAAA"
    "AP0BAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
)


def _decode_real_legacy_multisig():
    def fake_acct(url, pk, enc="base64", length=None):
        assert pk == MARINADE_UPGRADE_MS, pk
        return {"data": [LEGACY_MULTISIG_B64]}

    with mock.patch.object(sol_read, "acct", fake_acct):
        return sol_read.read_legacy_serum_multisig("unused-url", MARINADE_UPGRADE_MS)


_REAL_LEGACY_MULTISIG = _decode_real_legacy_multisig()

# ---------------------------------------------------------------------------
# Real Solend inputs (data/methodology_test_2026-09-17-solend-governance.md)
# ---------------------------------------------------------------------------
SLND_MINT = "SLNDpmoWTVADgEdndyvWzroNL7zSi1dF9PC3xHGtPwp"
SOLEND_REALM = "7sf3tcWm58vhtkJMwuw2P3T6UBX7UE5VKxPMnXJUZ1Hn"
SOLEND_GOVERNANCE = "4AxRDMShhYgoP7vVsZ1oDzQQaVw3WBPUoFvonYxJXTpc"
SOLEND_GOV_PROGRAM = "A7kmu2kUcnQwAVn8B4znQmGJeUrsJ1WEhYVMtmiBLkEr"
SOLEND_REALM_AUTHORITY = "EsLAEeKA1dUJRiPpbTAm7r94KqGDAKe1ivH8PLAAuSxV"  # bare on-curve EOA
SOLEND_PROGRAM_UPGRADE_AUTHORITY = "6EpduYmguTXpJMtEKjYXvrmuusBFrTy2stPNzbDZrqUT"  # bare on-curve EOA

# ---------------------------------------------------------------------------
# Real Meteora DAMM v2 inputs (data/scouted_targets_2026-09-17-run2.md row 7,
# data/scored_targets_2026-09-18-defi-config-admins.md)
# ---------------------------------------------------------------------------
METEORA_PROGRAM = "cpamdpZCGKUy5JxQXB4dcpGPiikHawvSWAd6mEn1sGG"
METEORA_UPGRADE_MS = "CoEsykatDegLB7pcMJia79JSriDdi71nPnjgeSfw623k"
# Documented as "authority index 1 (`JADaUV...`)"; full string is the offline
# Squads v3 PDA, checked in TestFixtureProvenance.
METEORA_UPGRADE_AUTHORITY = "JADaUV8kvDpDbJr55wxXJHVaBS3VCj8thZZHjfeuCVLd"
# Rust compile-time ADMINS[] (MeteoraAg/damm-v2 auth.rs). Literal copies of
# scorers.METEORA_DAMM_V2_ADMINS: a CHANGE DETECTOR only (see the module
# docstring's provenance limit -- no data note prints these addresses and the
# upstream source is not vendored).
METEORA_ADMINS = (
    "5unTfT2kssBuNvHPY6LbJfJpLqEcdMxGYLWHwShaeTLi",
    "DHLXnJdACTY83yKwnUkeoDjqi4QBbsYGa1v8tJL76ViX",
)
# SYNTHETIC 7 member keys (the real list is not recorded in the repository).
METEORA_MEMBER_KEYS = tuple(_key(0x40 + i) for i in range(7))


# ---------------------------------------------------------------------------
# Fake read layer
# ---------------------------------------------------------------------------
def _keytype(pk, on_curve, exists=True, owner=SYSTEM_PROGRAM):
    return {"key": pk, "on_curve": on_curve, "exists": exists,
            "owner": owner if exists else None, "executable": False if exists else None}


def _tor(owner, amount=1):
    return {"tor": "tor-of-" + owner[:8], "governing_token_owner": owner,
            "governing_token_deposit_amount": amount}


class _Chain:
    """Fixture tables keyed by address plus the fake readers patched into
    `sol_read`. Every read is recorded in `calls`; a read of an address with
    no fixture raises AssertionError (which `score_all` would swallow as a
    skipped target -- tests that go through it also check the result count)."""

    def __init__(self):
        self.programs = {}
        self.keytypes = {}
        self.realms = {}
        self.governances = {}
        self.governances_v2 = {}
        self.squads_v3 = {}
        self.marinade_states = {}
        self.legacy_multisigs = {}
        self.owner_records = {}
        self.mints = {}
        self.calls = []

    def _lookup(self, table, name, key):
        if key not in table:
            raise AssertionError(f"unexpected {name} read of {key!r}")
        return copy.deepcopy(table[key])

    def read_program(self, url, pk):
        self.calls.append(("read_program", pk))
        return self._lookup(self.programs, "read_program", pk)

    def read_keytype(self, url, pk):
        self.calls.append(("read_keytype", pk))
        return self._lookup(self.keytypes, "read_keytype", pk)

    def read_realm(self, url, pk):
        self.calls.append(("read_realm", pk))
        return self._lookup(self.realms, "read_realm", pk)

    def read_governance(self, url, pk):
        self.calls.append(("read_governance", pk))
        return self._lookup(self.governances, "read_governance", pk)

    def read_governance_v2(self, url, pk):
        self.calls.append(("read_governance_v2", pk))
        return self._lookup(self.governances_v2, "read_governance_v2", pk)

    def read_squadsv3(self, url, pk, authority_index=None):
        self.calls.append(("read_squadsv3", (pk, authority_index)))
        fx = self._lookup(self.squads_v3, "read_squadsv3", pk)
        out = {k: v for k, v in fx.items() if not k.startswith("authority_")}
        if authority_index is not None and ("authority_%d" % authority_index) in fx:
            out["authority_%d" % authority_index] = fx["authority_%d" % authority_index]
        return out

    def read_marinade_state(self, url, pk):
        self.calls.append(("read_marinade_state", pk))
        return self._lookup(self.marinade_states, "read_marinade_state", pk)

    def read_legacy_serum_multisig(self, url, pk):
        self.calls.append(("read_legacy_serum_multisig", pk))
        return self._lookup(self.legacy_multisigs, "read_legacy_serum_multisig", pk)

    def list_token_owner_records(self, url, governance_program, realm, mint, account_type=17):
        key = (governance_program, realm, mint)
        self.calls.append(("list_token_owner_records", key))
        return self._lookup(self.owner_records, "list_token_owner_records", key)

    def read_mint(self, url, pk):
        self.calls.append(("read_mint", pk))
        return self._lookup(self.mints, "read_mint", pk)

    @staticmethod
    def _no_network(*args, **kwargs):
        raise AssertionError("a test reached sol_read's network transport")

    def calls_to(self, name):
        return [key for n, key in self.calls if n == name]

    def install(self, testcase):
        def patch(name, fn):
            p = mock.patch.object(sol_read, name, fn)
            p.start()
            testcase.addCleanup(p.stop)

        patch("rpc", self._no_network)
        patch("acct", self._no_network)
        for name in ("read_program", "read_keytype", "read_realm", "read_governance",
                     "read_governance_v2", "read_squadsv3", "read_marinade_state",
                     "read_legacy_serum_multisig", "list_token_owner_records", "read_mint"):
            patch(name, getattr(self, name))


def _add_solend(chain):
    chain.realms[SOLEND_REALM] = {
        "realm": SOLEND_REALM, "account_type": 16, "community_mint": SLND_MINT,
        "council_mint": None, "authority": SOLEND_REALM_AUTHORITY, "name": "Solend DAO"}
    chain.governances[SOLEND_GOVERNANCE] = {
        "governance": SOLEND_GOVERNANCE, "account_type": 20, "realm": SOLEND_REALM,
        "governed_account": SLND_MINT, "proposals_count": 15,
        "community_vote_threshold": {"kind": "YesVotePercentage", "value": 1},
        "min_community_weight_to_create_proposal": 250000000000,
        "transactions_hold_up_time_s": 0, "voting_base_time_s": 259200}
    chain.programs[SOLEND_GOV_PROGRAM] = {
        "program": SOLEND_GOV_PROGRAM, "owner": BPF_LOADER_V3, "executable": True,
        "programdata": "DBvb9pnKMCjfQsCzhExQwKUCRAVRxNAyiHFyFKbaPJrC", "last_deploy_slot": 138109469,
        "upgrade_authority": SOLEND_PROGRAM_UPGRADE_AUTHORITY}
    chain.keytypes[SOLEND_REALM_AUTHORITY] = _keytype(SOLEND_REALM_AUTHORITY, True)
    chain.keytypes[SOLEND_PROGRAM_UPGRADE_AUTHORITY] = _keytype(SOLEND_PROGRAM_UPGRADE_AUTHORITY, True)


def _add_meteora(chain):
    chain.programs[METEORA_PROGRAM] = {
        "program": METEORA_PROGRAM, "owner": BPF_LOADER_V3, "executable": True,
        "upgrade_authority": METEORA_UPGRADE_AUTHORITY}
    chain.squads_v3[METEORA_UPGRADE_MS] = {
        "ms": METEORA_UPGRADE_MS, "threshold": 4, "n_keys": 7,
        "keys": list(METEORA_MEMBER_KEYS), "authority_1": METEORA_UPGRADE_AUTHORITY}


def _add_marinade(chain, council=None, supply=None, pct=50, voting_s=259200, cooloff_s=0, holdup_s=0):
    """Real Marinade fixture; `council` is a list of (owner, deposit) pairs
    (default: 5 seats of 1 token, the documented census) and `supply` the
    council mint supply (default: the deposit sum, the documented state)."""
    if council is None:
        council = [(MARINADE_COUNCIL_REAL_OWNER, 1)] + [(_key(0x60 + i), 1) for i in range(4)]
    if supply is None:
        supply = sum(amount for _, amount in council)
    chain.programs[MARINADE_PROGRAM] = {
        "program": MARINADE_PROGRAM, "owner": BPF_LOADER_V3, "executable": True,
        "upgrade_authority": MARINADE_UPGRADE_AUTHORITY}
    chain.legacy_multisigs[MARINADE_UPGRADE_MS] = copy.deepcopy(_REAL_LEGACY_MULTISIG)
    chain.marinade_states[MARINADE_STATE] = {
        "state": MARINADE_STATE, "msol_mint": MARINADE_MSOL_MINT,
        "admin_authority": MARINADE_ADMIN_AUTHORITY, "paused": False}
    chain.governances_v2[MARINADE_GOVERNANCE] = {
        "governance": MARINADE_GOVERNANCE, "realm": MARINADE_REALM,
        "community_vote_threshold": {"tag": 2, "kind": "Disabled", "pct": None},
        "council_vote_threshold": {"tag": 0, "kind": "YesVotePercentage", "pct": pct},
        "transactions_hold_up_time_s": holdup_s, "voting_base_time_s": voting_s,
        "voting_cool_off_time_s": cooloff_s}
    chain.owner_records[(MARINADE_GOV_PROGRAM, MARINADE_REALM, MARINADE_COUNCIL_MINT)] = [
        _tor(owner, amount) for owner, amount in council]
    chain.mints[MARINADE_COUNCIL_MINT] = {
        "mint": MARINADE_COUNCIL_MINT, "supply": supply, "decimals": 0}


class _PathSpy:
    """Calls straight through to the real `_score_full_power_path` and
    records (args, kwargs, result), so a test can check both what the scorer
    fed the formula and what the formula returned."""

    def __init__(self):
        self._orig = solana._score_full_power_path
        self.calls = []

    def __call__(self, *args, **kwargs):
        result = self._orig(*args, **kwargs)
        self.calls.append((args, kwargs, result))
        return result

    def by_kind(self, kind):
        return [(kw, res) for args, kw, res in self.calls if args and args[0] == kind]

    def install(self, testcase):
        p = mock.patch.object(solana, "_score_full_power_path", self)
        p.start()
        testcase.addCleanup(p.stop)


class _ChainCase(unittest.TestCase):
    """setUp builds the fixture chain, patches the readers, installs the spy."""

    def build_chain(self):
        raise NotImplementedError

    def setUp(self):
        self.chain = self.build_chain()
        self.chain.install(self)
        self.spy = _PathSpy()
        self.spy.install(self)

    def has_note(self, result, fragment):
        return any(fragment in n for n in result["notes"])

    def notes_starting(self, result, prefix):
        """The notes that BEGIN with `prefix`. Unlike `has_note` (which matches
        any note containing the fragment, so one note's text can satisfy an
        assertion meant for another) this pins a fragment to one note."""
        return [n for n in result["notes"] if n.startswith(prefix)]

    def scores(self, result):
        return (result["adminKeyScore"], result["multisigScore"], result["timelockScore"])


# ---------------------------------------------------------------------------
# Fixtures really are what the documentation says they are
# ---------------------------------------------------------------------------
class TestFixtureProvenance(unittest.TestCase):
    """Cross-checks the real fixtures against the documented facts with the
    pure offline primitives only, independently of any scorer."""

    def test_marinade_legacy_multisig_real_bytes_decode_to_the_documented_6_of_13(self):
        ms = _REAL_LEGACY_MULTISIG
        self.assertEqual(ms["threshold"], 6)
        self.assertEqual(ms["nonce"], 253)
        self.assertEqual(len(ms["owners"]), 13)
        self.assertEqual(len(set(ms["owners"])), 13)
        # Documented cross-exposure: "owner #6" also holds a council seat. The
        # index base is 0: test_marinade_liquid_staking.py's live-confirmed
        # constants are named LEGACY_MULTISIG_OWNER_0 .. OWNER_12 for the 13
        # owners (OWNER_12 is the last one), and use owners[6] for OWNER_6.
        self.assertEqual(ms["owners"][6], MARINADE_COUNCIL_REAL_OWNER)
        # Two more live-confirmed anchors from the same file (first / last owner).
        self.assertEqual(ms["owners"][0], "8DzsCSvbvBDYxGB4ytNF698zi6Dyo9dUBVRNjZQFHSUt")
        self.assertEqual(ms["owners"][12], "5ygHFBRddFh7v4PpqquQu2yeRdxWvN1PhyjyzfENdUVh")

    def test_marinade_upgrade_authority_is_the_documented_signer_pda_with_bump_253(self):
        derived, bump = sol_read.find_program_address(
            [sol_read.b58dec(MARINADE_UPGRADE_MS)], MARINADE_MULTISIG_PROGRAM)
        self.assertEqual(derived, MARINADE_UPGRADE_AUTHORITY)
        self.assertEqual(bump, 253)
        self.assertFalse(sol_read.on_curve(MARINADE_UPGRADE_AUTHORITY))

    def test_marinade_admin_authority_is_the_native_treasury_pda_of_the_governance(self):
        derived, _ = sol_read.find_program_address(
            [b"native-treasury", sol_read.b58dec(MARINADE_GOVERNANCE)], MARINADE_GOV_PROGRAM)
        self.assertEqual(derived, MARINADE_ADMIN_AUTHORITY)

    def test_meteora_upgrade_authority_is_squads_v3_authority_index_1_with_documented_prefix(self):
        derived, _ = sol_read.find_program_address(
            [b"squad", sol_read.b58dec(METEORA_UPGRADE_MS), (1).to_bytes(4, "little"), b"authority"],
            "SMPLecH534NA9acpos4G6x7uf3LWbCAwZQE9e8ZekMu")
        self.assertEqual(derived, METEORA_UPGRADE_AUTHORITY)
        self.assertTrue(derived.startswith("JADaUV"))

    def test_documented_on_curve_and_off_curve_classification(self):
        # Solend: both authorities documented "on_curve true"; Meteora ADMINS[]: "two bare on-curve EOAs".
        for pk in (SOLEND_REALM_AUTHORITY, SOLEND_PROGRAM_UPGRADE_AUTHORITY) + METEORA_ADMINS:
            self.assertTrue(sol_read.on_curve(pk), pk)

    def test_module_constants_match_the_documented_addresses(self):
        self.assertEqual(solana.MARINADE_PROGRAM, MARINADE_PROGRAM)
        self.assertEqual(solana.MARINADE_MULTISIG_PROGRAM, MARINADE_MULTISIG_PROGRAM)
        # Change detector against this file's copy (see the module docstring's
        # provenance limit); the documented prefixes are the only record that
        # does not live in the constant itself.
        self.assertEqual(tuple(solana.METEORA_DAMM_V2_ADMINS), METEORA_ADMINS)
        self.assertEqual([k[:7] for k in METEORA_ADMINS], ["5unTfT2", "DHLXnJd"])


# ---------------------------------------------------------------------------
# _resolve_legacy_serum_multisig
# ---------------------------------------------------------------------------
class TestResolveLegacySerumMultisig(_ChainCase):
    def build_chain(self):
        chain = _Chain()
        chain.legacy_multisigs[MARINADE_UPGRADE_MS] = copy.deepcopy(_REAL_LEGACY_MULTISIG)
        return chain

    def _resolve(self, authority, candidate=MARINADE_UPGRADE_MS, label="program upgrade"):
        notes = []
        ms = solana._resolve_legacy_serum_multisig("unused-url", label, authority, candidate, notes)
        return ms, notes

    def test_live_authority_equal_to_the_derived_signer_pda_returns_the_decoded_multisig(self):
        ms, notes = self._resolve(MARINADE_UPGRADE_AUTHORITY)
        self.assertIsNotNone(ms)
        self.assertEqual(ms["threshold"], 6)
        self.assertEqual(len(ms["owners"]), 13)

    def test_match_note_records_bump_nonce_and_the_derived_address(self):
        _, notes = self._resolve(MARINADE_UPGRADE_AUTHORITY)
        self.assertEqual(len(notes), 1)
        self.assertIn("canonical bump=253, stored nonce=253", notes[0])
        self.assertIn(f"= {MARINADE_UPGRADE_AUTHORITY} (expected live authority {MARINADE_UPGRADE_AUTHORITY})", notes[0])
        self.assertTrue(notes[0].endswith("-- MATCH"))

    def test_note_carries_the_caller_label_and_the_candidate_address(self):
        _, notes = self._resolve(MARINADE_UPGRADE_AUTHORITY, label="some other label")
        self.assertTrue(notes[0].startswith("some other label: "))
        self.assertIn(MARINADE_UPGRADE_MS, notes[0])

    def test_authority_that_differs_from_the_derived_pda_degrades_to_none(self):
        ms, notes = self._resolve(_key(0x30))
        self.assertIsNone(ms)
        self.assertTrue(notes[0].endswith("-- MISMATCH, degrading"))

    def test_none_authority_never_matches_even_though_a_pda_can_be_derived(self):
        ms, notes = self._resolve(None)
        self.assertIsNone(ms)
        self.assertIn("(expected live authority None)", notes[0])
        self.assertTrue(notes[0].endswith("-- MISMATCH, degrading"))

    def test_stored_nonce_that_is_not_the_canonical_bump_degrades_even_when_the_pda_matches(self):
        # Tamper: same real account but nonce 252. The derived PDA still
        # equals the live authority (bump 253), yet the stored nonce !=
        # canonical bump, so the multisig must not be trusted.
        self.chain.legacy_multisigs[MARINADE_UPGRADE_MS]["nonce"] = 252
        ms, notes = self._resolve(MARINADE_UPGRADE_AUTHORITY)
        self.assertIsNone(ms)
        self.assertIn("canonical bump=253, stored nonce=252", notes[0])
        self.assertTrue(notes[0].endswith("-- MISMATCH, degrading"))

    def test_stored_nonce_above_the_canonical_bump_degrades_too(self):
        # The rule is bump == nonce (marinade-finance/multisig re-derives the
        # signer PDA with the stored nonce AS the bump), so a nonce ABOVE the
        # canonical bump 253 is as wrong as one below it. 254 and 255 are the
        # values a one-sided `bump <= nonce` comparison would wrongly accept.
        for nonce in (254, 255):
            with self.subTest(nonce=nonce):
                self.chain.legacy_multisigs[MARINADE_UPGRADE_MS]["nonce"] = nonce
                ms, notes = self._resolve(MARINADE_UPGRADE_AUTHORITY)
                self.assertIsNone(ms)
                self.assertIn(f"canonical bump=253, stored nonce={nonce}", notes[0])
                self.assertTrue(notes[0].endswith("-- MISMATCH, degrading"))

    def test_stored_nonce_of_zero_degrades_too(self):
        # 0 is falsy: it must be compared, not treated as "absent".
        self.chain.legacy_multisigs[MARINADE_UPGRADE_MS]["nonce"] = 0
        ms, notes = self._resolve(MARINADE_UPGRADE_AUTHORITY)
        self.assertIsNone(ms)
        self.assertIn("canonical bump=253, stored nonce=0", notes[0])

    def test_wrong_candidate_multisig_for_a_live_authority_degrades(self):
        other = _key(0x71)
        self.chain.legacy_multisigs[other] = copy.deepcopy(_REAL_LEGACY_MULTISIG)
        ms, notes = self._resolve(MARINADE_UPGRADE_AUTHORITY, candidate=other)
        self.assertIsNone(ms)
        self.assertTrue(notes[0].endswith("-- MISMATCH, degrading"))

    def test_reads_only_the_candidate_account_once(self):
        self._resolve(MARINADE_UPGRADE_AUTHORITY)
        self.assertEqual(self.chain.calls, [("read_legacy_serum_multisig", MARINADE_UPGRADE_MS)])


# ---------------------------------------------------------------------------
# score_solend_dao_governance
# ---------------------------------------------------------------------------
class TestScoreSolendDaoGovernance(_ChainCase):
    def build_chain(self):
        chain = _Chain()
        _add_solend(chain)
        return chain

    def _score(self):
        return solana.score_solend_dao_governance("unused-url")

    def _renounce_both_eoas(self):
        self.chain.realms[SOLEND_REALM]["authority"] = None
        self.chain.programs[SOLEND_GOV_PROGRAM]["upgrade_authority"] = None

    # -- happy path: the published score ----------------------------------
    def test_reproduces_the_published_sub_scores_and_composite(self):
        # PUBLISHED (methodology_test_2026-09-17-solend-governance.md
        # "Combined score"; chains/solana/deploy/README.md row "Solend DAO"):
        # adminKey 5, multisig 0, timelock 0, oracle 100, composite 2.
        result = self._score()
        self.assertEqual(self.scores(result), (5, 0, 0))
        self.assertEqual(result["oracleAuthorityScore"], 100)
        self.assertEqual(result["compositeScore"], 2)
        # hand check: floor(0.4*5 + 0.3*0 + 0.3*0 + 0.5) = floor(2.5) = 2
        self.assertEqual(result["target"], SOLEND_REALM)
        self.assertEqual(result["label"], "Solend DAO (governance realm)")

    def test_signers_are_the_two_bare_eoas(self):
        self.assertEqual(self._score()["_signers"], {SOLEND_REALM_AUTHORITY, SOLEND_PROGRAM_UPGRADE_AUTHORITY})

    def test_notes_name_both_bare_eoa_authorities_and_that_no_vote_is_required(self):
        result = self._score()
        self.assertTrue(self.has_note(result, f"Realm.authority = {SOLEND_REALM_AUTHORITY}"))
        self.assertTrue(self.has_note(
            result, f"Realm.authority {SOLEND_REALM_AUTHORITY} is a bare on-curve key (owner={SYSTEM_PROGRAM}) -- no vote required"))
        self.assertTrue(self.has_note(result, f"governance program.upgrade_authority = {SOLEND_PROGRAM_UPGRADE_AUTHORITY}"))
        self.assertTrue(self.has_note(
            result, f"governance program.upgrade_authority {SOLEND_PROGRAM_UPGRADE_AUTHORITY} is a bare on-curve key "
                    f"(owner={SYSTEM_PROGRAM}) -- no vote required"))

    def test_notes_disclose_that_the_raw_one_percent_threshold_is_not_a_score_input(self):
        # Disclosed limit (methodology_test file, "Caveat"): the YesVotePercentage(1)
        # value is not independently re-confirmed and feeds no score.
        result = self._score()
        self.assertTrue(self.has_note(result, "proposals_count=15"))
        self.assertTrue(self.has_note(result, "transactions_hold_up_time_s=0 voting_base_time_s=259200"))
        self.assertTrue(self.has_note(result, "'kind': 'YesVotePercentage', 'value': 1"))
        self.assertTrue(self.has_note(result, "raw value not independently re-confirmed, not used as a score input"))

    def test_token_vote_path_is_flat_70_70_with_timelock_from_holdup_alone(self):
        # Path B (METHODOLOGY.md 6.1, no countable t): admin 70, multisig 70
        # flat. Timelock RECONCILED 2026-09-19 to the hold-up time alone:
        # hold-up 0 -> 0 (voting 3 days no longer feeds it). Hours: 259200/3600 = 72.0.
        result = self._score()
        self.assertTrue(self.has_note(
            result, "community token-vote path (no council mint): adminKey=70 multisig=70 timelock=0 "
                    "(voting=72.0h hold-up=0.0h)"))
        (kw, res), = self.spy.by_kind("realms_governance")
        self.assertEqual(res, (70, 70, 0))
        self.assertEqual(kw, {"voting_s": 259200, "holdup_s": 0})

    def test_combined_note_states_the_min_over_all_three_paths(self):
        self.assertTrue(self.has_note(
            self._score(), "combined (min over all three full-power paths, METHODOLOGY.md 6.2): "
                           "adminKey=5 multisig=0 timelock=0"))

    def _dominated_by_note(self, result):
        (note,) = self.notes_starting(result, "combined (min over all three full-power paths")
        return note

    def test_dominated_by_note_lists_both_bare_eoa_paths(self):
        # Docstring claim ("two of the three paths ... dominate the
        # composite"): the two bare-EOA paths are named.
        note = self._dominated_by_note(self._score())
        self.assertIn("'Realm.authority'", note)
        self.assertIn("'governance program.upgrade_authority'", note)

    # -- which LABEL is attached to which path ---------------------------------
    # In each scenario exactly ONE path is strictly the lowest on every
    # dimension, so which name the "dominated by" note must carry is
    # unambiguous under any reasonable reading (no reliance on the code's own
    # tie rule). Hold-up 86400 s puts the token-vote path at (70, 70, 50):
    # delay curve d = 24 h -> 50 + min(30, round(10 * (24/24 - 1))) = 50.
    # Bare on-curve EOA = (5, 0, 0) and renounced (None) = (100, 100, 100)
    # (METHODOLOGY.md 6.1).
    def test_dominated_by_names_the_program_upgrade_path_when_only_it_is_the_bare_eoa(self):
        self.chain.realms[SOLEND_REALM]["authority"] = None                      # A = (100, 100, 100)
        self.chain.governances[SOLEND_GOVERNANCE]["transactions_hold_up_time_s"] = 86400  # B = (70, 70, 50)
        result = self._score()                                                   # C = (5, 0, 0)
        self.assertEqual(self.scores(result), (5, 0, 0))
        self.assertTrue(self._dominated_by_note(result).endswith(
            "-- dominated by: ['governance program.upgrade_authority']"))

    def test_dominated_by_names_the_realm_authority_when_only_it_is_the_bare_eoa(self):
        self.chain.programs[SOLEND_GOV_PROGRAM]["upgrade_authority"] = None      # C = (100, 100, 100)
        self.chain.governances[SOLEND_GOVERNANCE]["transactions_hold_up_time_s"] = 86400  # B = (70, 70, 50)
        result = self._score()                                                   # A = (5, 0, 0)
        self.assertEqual(self.scores(result), (5, 0, 0))
        self.assertTrue(self._dominated_by_note(result).endswith(
            "-- dominated by: ['Realm.authority']"))

    def test_dominated_by_names_the_token_vote_path_when_both_eoas_are_renounced(self):
        self._renounce_both_eoas()                                               # A = C = (100, 100, 100)
        result = self._score()                                                   # B = (70, 70, 0)
        self.assertEqual(self.scores(result), (70, 70, 0))
        self.assertTrue(self._dominated_by_note(result).endswith(
            "-- dominated by: ['community token-vote']"))

    def test_dominated_by_with_a_renounced_realm_authority_and_zero_holdup(self):
        # A = (100, 100, 100), B = (70, 70, 0), C = (5, 0, 0): C is the minimum
        # on admin and multisig; B only ties it on timelock (0 == 0). The label
        # of the renounced path (Realm.authority) must never appear.
        self.chain.realms[SOLEND_REALM]["authority"] = None
        note = self._dominated_by_note(self._score())
        self.assertIn("'governance program.upgrade_authority'", note)
        self.assertNotIn("'Realm.authority'", note)

    def test_token_vote_path_is_also_listed_as_dominant_only_through_a_timelock_tie(self):
        # CHARACTERIZATION of the code's own tie rule, NOT a documented value:
        # no document specifies the wording of this note. The rule: a path is
        # "dominant" if it equals the combined min on ANY dimension. Paths
        # (5,0,0), (70,70,0), (5,0,0): the token-vote path ties the min on
        # timelock (0 == 0), so all three names are listed. Pinned so a change
        # to that rule is a deliberate one. FINDING (cosmetic, not a scoring
        # bug): with the published inputs the note names the 70/70 token-vote
        # path as "dominating" although only the two EOA paths bind admin and
        # multisig; the scenarios above are the unambiguous ones.
        note = self._dominated_by_note(self._score())
        self.assertTrue(note.endswith(
            "-- dominated by: ['Realm.authority', 'community token-vote', 'governance program.upgrade_authority']"))

    def test_reads_exactly_the_documented_accounts(self):
        # The set of accounts the docstring says are read (realm, its authority,
        # the governance over the SLND mint, the governance program and its
        # upgrade authority). Order is NOT asserted: nothing documents it and a
        # harmless refactor may reorder it.
        self._score()
        self.assertEqual(set(self.chain.calls), {
            ("read_realm", SOLEND_REALM),
            ("read_keytype", SOLEND_REALM_AUTHORITY),
            ("read_governance", SOLEND_GOVERNANCE),
            ("read_program", SOLEND_GOV_PROGRAM),
            ("read_keytype", SOLEND_PROGRAM_UPGRADE_AUTHORITY),
        })

    # -- authority classification ladder (both EOA slots) -------------------
    def test_renounced_realm_authority_scores_100_and_is_not_a_signer(self):
        self.chain.realms[SOLEND_REALM]["authority"] = None
        result = self._score()
        self.assertTrue(self.has_note(result, "Realm.authority = None"))
        self.assertTrue(self.has_note(result, "Realm.authority is None -- renounced, the safest band, not a failed read"))
        self.assertNotIn(SOLEND_REALM_AUTHORITY, result["_signers"])
        self.assertNotIn(("read_keytype", SOLEND_REALM_AUTHORITY), self.chain.calls)
        # program authority still a bare EOA -> the combined score is unchanged
        self.assertEqual(self.scores(result), (5, 0, 0))

    def test_renounced_program_upgrade_authority_scores_100_and_is_not_a_signer(self):
        self.chain.programs[SOLEND_GOV_PROGRAM]["upgrade_authority"] = None
        result = self._score()
        self.assertTrue(self.has_note(result, "governance program.upgrade_authority is None -- renounced, the safest band, not a failed read"))
        self.assertEqual(result["_signers"], {SOLEND_REALM_AUTHORITY})
        self.assertEqual(self.scores(result), (5, 0, 0))

    def test_off_curve_realm_authority_degrades_to_20_0_0_and_is_not_a_signer(self):
        pda = MARINADE_UPGRADE_AUTHORITY  # a real off-curve PDA (checked in TestFixtureProvenance)
        self.chain.realms[SOLEND_REALM]["authority"] = pda
        self.chain.keytypes[pda] = _keytype(pda, False, exists=False)
        result = self._score()
        self.assertTrue(self.has_note(
            result, f"Realm.authority {pda} is off-curve (a PDA) -- controller not resolved this pass, "
                    "degraded rather than assumed self-governed"))
        self.assertEqual(result["_signers"], {SOLEND_PROGRAM_UPGRADE_AUTHORITY})
        # Path A = (20,0,0) but Path C is still a bare EOA (5,0,0): min is (5,0,0).
        self.assertEqual(self.scores(result), (5, 0, 0))

    def test_both_authorities_off_curve_gives_20_0_0_and_composite_8(self):
        for pk in (MARINADE_UPGRADE_AUTHORITY, MARINADE_ADMIN_AUTHORITY):
            self.chain.keytypes[pk] = _keytype(pk, False, exists=False)
        self.chain.realms[SOLEND_REALM]["authority"] = MARINADE_UPGRADE_AUTHORITY
        self.chain.programs[SOLEND_GOV_PROGRAM]["upgrade_authority"] = MARINADE_ADMIN_AUTHORITY
        result = self._score()
        # A=(20,0,0) C=(20,0,0) B=(70,70,0) -> min = (20,0,0)
        self.assertEqual(self.scores(result), (20, 0, 0))
        # composite: floor(0.4*20 + 0 + 0 + 0.5) = floor(8.5) = 8
        self.assertEqual(result["compositeScore"], 8)
        self.assertEqual(result["_signers"], set())

    def test_mixed_renounced_and_off_curve_takes_the_min_per_dimension(self):
        self.chain.realms[SOLEND_REALM]["authority"] = None
        pda = MARINADE_UPGRADE_AUTHORITY
        self.chain.keytypes[pda] = _keytype(pda, False, exists=False)
        self.chain.programs[SOLEND_GOV_PROGRAM]["upgrade_authority"] = pda
        # A=(100,100,100) B=(70,70,0) C=(20,0,0) -> admin min 20, multisig min 0, timelock min 0
        self.assertEqual(self.scores(self._score()), (20, 0, 0))

    # -- token-vote path becomes the binding constraint --------------------
    def test_with_both_eoas_renounced_the_token_vote_path_alone_sets_the_score(self):
        self._renounce_both_eoas()
        result = self._score()
        # Combined = path B = (70, 70, 0).
        self.assertEqual(self.scores(result), (70, 70, 0))
        # hand check: floor(0.4*70 + 0.3*70 + 0 + 0.5) = floor(49.5) = 49
        self.assertEqual(result["compositeScore"], 49)
        self.assertEqual(result["_signers"], set())

    def test_holdup_time_drives_the_token_vote_timelock_through_the_delay_curve(self):
        self._renounce_both_eoas()
        # (hold-up seconds, timelock, composite) -- each hand-derived:
        #   0      -> 0                                   floor(28 + 21 + 0    + 0.5) = 49
        #   3600   -> d=1h  <24h: round(50*1/24)=round(2.08)=2      floor(28+21+0.6+0.5)=50
        #   82800  -> d=23h <24h: round(50*23/24)=round(47.9)=48    floor(28+21+14.4+0.5)=63
        #   86400  -> d=24h: 50+min(30,round(10*(1-1)))=50           floor(28+21+15+0.5)=64
        #   172800 -> d=48h: 50+min(30,round(10*(2-1)))=60           floor(28+21+18+0.5)=67
        #   2592000-> d=720h: 50+min(30,round(10*29))=80 (cap)       floor(28+21+24+0.5)=73
        for holdup_s, timelock, composite in (
                (0, 0, 49), (3600, 2, 50), (82800, 48, 63), (86400, 50, 64), (172800, 60, 67), (2592000, 80, 73)):
            with self.subTest(holdup_s=holdup_s):
                self.chain.governances[SOLEND_GOVERNANCE]["transactions_hold_up_time_s"] = holdup_s
                result = self._score()
                self.assertEqual(self.scores(result), (70, 70, timelock))
                self.assertEqual(result["compositeScore"], composite)

    def test_voting_time_is_disclosed_but_does_not_move_the_timelock(self):
        self._renounce_both_eoas()
        self.chain.governances[SOLEND_GOVERNANCE]["voting_base_time_s"] = 30 * 86400
        result = self._score()
        self.assertEqual(result["timelockScore"], 0)
        self.assertTrue(self.has_note(result, "voting=720.0h hold-up=0.0h"))

    def test_council_mint_present_scores_the_placeholder_threshold_1_path(self):
        # The "council mint" branch is dead for the real Solend realm (documented
        # in the source: it passes the placeholder threshold=1). threshold 1 ->
        # (5, 0) per METHODOLOGY.md 6.1; timelock 0 for hold-up 0.
        self.chain.realms[SOLEND_REALM]["council_mint"] = _key(0x21)
        self._renounce_both_eoas()
        result = self._score()
        (kw, res), = self.spy.by_kind("realms_governance")
        self.assertEqual(kw["threshold"], 1)
        self.assertEqual(res, (5, 0, 0))
        self.assertEqual(self.scores(result), (5, 0, 0))
        self.assertEqual(result["compositeScore"], 2)

    # -- wrong-account guards ------------------------------------------------
    def test_wrong_community_mint_aborts_before_reading_the_governance(self):
        self.chain.realms[SOLEND_REALM]["community_mint"] = _key(0x22)
        with self.assertRaisesRegex(ValueError, "wrong account, aborting rather than scoring the wrong DAO"):
            self._score()
        self.assertNotIn("read_governance", [n for n, _ in self.chain.calls])

    def test_governance_of_a_different_realm_aborts(self):
        self.chain.governances[SOLEND_GOVERNANCE]["realm"] = _key(0x23)
        with self.assertRaisesRegex(ValueError, "realm/governed_account mismatch"):
            self._score()
        self.assertNotIn("read_program", [n for n, _ in self.chain.calls])

    def test_governance_over_a_different_governed_account_aborts(self):
        self.chain.governances[SOLEND_GOVERNANCE]["governed_account"] = _key(0x24)
        with self.assertRaisesRegex(ValueError, "realm/governed_account mismatch"):
            self._score()


# ---------------------------------------------------------------------------
# score_meteora_damm_v2
# ---------------------------------------------------------------------------
class TestScoreMeteoraDammV2(_ChainCase):
    def build_chain(self):
        chain = _Chain()
        _add_meteora(chain)
        return chain

    def _score(self):
        return solana.score_meteora_damm_v2("unused-url")

    def _neutralise_admins_path(self):
        """Replace ONLY the `on_curve` result (the hardcoded ADMINS[] path)
        with (100, 100, 100); every other kind still goes through the real
        formula (via the spy installed in setUp). The ADMINS floor otherwise
        masks everything Path A does (see the module docstring)."""
        inner = solana._score_full_power_path

        def neutral(kind, *args, **kwargs):
            if kind == "on_curve":
                return (100, 100, 100)
            return inner(kind, *args, **kwargs)

        p = mock.patch.object(solana, "_score_full_power_path", neutral)
        p.start()
        self.addCleanup(p.stop)

    # -- happy path: the published score ----------------------------------
    def test_reproduces_the_published_sub_scores_and_composite(self):
        # PUBLISHED (data/scored_targets_2026-09-18-defi-config-admins.md
        # summary table; chains/solana/deploy/README.md row "Meteora DAMM v2"):
        # adminKey 5, multisig 0, timelock 0, oracle 100, composite 2.
        result = self._score()
        self.assertEqual(self.scores(result), (5, 0, 0))
        self.assertEqual(result["oracleAuthorityScore"], 100)
        self.assertEqual(result["compositeScore"], 2)
        # hand check: floor(0.4*5 + 0 + 0 + 0.5) = floor(2.5) = 2
        self.assertEqual(result["target"], METEORA_PROGRAM)
        self.assertEqual(result["label"], "Meteora DAMM v2")

    def test_program_upgrade_path_alone_is_the_published_upper_bound_55_83_0(self):
        # scouted_targets_2026-09-17-run2.md row 7: Squads v3 4-of-7 -> 55 / 83 / 0,
        # composite 47 (upper bound). Hand: admin 40+min(20,5*3)=55;
        # multisig min(100, round(15*4 + 40*4/7)) = round(60+22.86) = 83; timelock 0.
        self._score()
        (kw, res), = self.spy.by_kind("squads_v3")
        self.assertEqual(kw, {"threshold": 4, "voters": 7})
        self.assertEqual(res, (55, 83, 0))
        self.assertEqual(solana._composite(*res), 47)

    def test_with_the_admins_floor_removed_the_upgrade_path_reproduces_the_scouted_upper_bound_47(self):
        # scouted_targets_2026-09-17-run2.md row 7: "55 / 83 / 0", composite
        # 47 (upper bound). Hand: admin 40 + min(20, 5*3) = 55; multisig
        # min(100, round(15*4 + 40*4/7)) = round(60 + 22.857) = 83; timelock 0
        # (Squads v3 has no delay). Composite floor(0.4*55 + 0.3*83 + 0.3*0 +
        # 0.5) = floor(22 + 24.9 + 0 + 0.5) = floor(47.4) = 47 (without the
        # +0.5 it would be 46; with admin/multisig swapped 50; with a 0.6
        # multisig weight 72). Path B is (100, 100, 100), so the combined
        # min is Path A alone; a max() over timelocks would give 100.
        self._neutralise_admins_path()
        result = self._score()
        self.assertEqual(self.scores(result), (55, 83, 0))
        self.assertEqual(result["compositeScore"], 47)
        (adm_note,) = self.notes_starting(result, "ADMINS[]")
        (cmb_note,) = self.notes_starting(result, "combined")
        # each note reports ITS OWN path: ADMINS -> the (neutral) path B, combined -> the min.
        self.assertTrue(adm_note.endswith("adminKey=100 multisig=100 timelock=100"), adm_note)
        self.assertTrue(cmb_note.endswith("adminKey=55 multisig=83 timelock=0"), cmb_note)
        self.assertEqual(result["_signers"], set(METEORA_MEMBER_KEYS) | set(METEORA_ADMINS))

    def test_with_the_admins_floor_removed_an_unresolved_upgrade_path_scores_exactly_20_20_0(self):
        # The degrade band for an unmatched authority is (20, 20, 0) (the value
        # the sibling scorers use for the same situation). Hand: composite
        # floor(0.4*20 + 0.3*20 + 0.3*0 + 0.5) = floor(8 + 6 + 0 + 0.5) = 14.
        # With the ADMINS floor in place any Path A value >= (5, 0, 0) would
        # give the same combined score, so it must be neutralised to see this.
        self._neutralise_admins_path()
        self.chain.programs[METEORA_PROGRAM]["upgrade_authority"] = _key(0x50)
        result = self._score()
        self.assertEqual(self.scores(result), (20, 20, 0))
        self.assertEqual(result["compositeScore"], 14)
        self.assertEqual(result["_signers"], set(METEORA_ADMINS))
        self.assertFalse(self.has_note(result, "program upgrade Squads v3:"))

    def test_admins_path_is_scored_as_a_bare_on_curve_key(self):
        self._score()
        self.assertEqual([res for _, res in self.spy.by_kind("on_curve")], [(5, 0, 0)])

    def test_signers_are_the_seven_multisig_members_plus_the_two_hardcoded_admins(self):
        signers = self._score()["_signers"]
        self.assertEqual(signers, set(METEORA_MEMBER_KEYS) | set(METEORA_ADMINS))
        self.assertEqual(len(signers), 9)

    def test_notes_carry_the_disclosed_hardcoded_admins_limit(self):
        # Disclosed limit (METHODOLOGY.md 6.2 / docstring): ADMINS[] is a
        # compile-time constant, invisible to any live account read, OR-gated.
        result = self._score()
        self.assertTrue(self.has_note(result, "hardcoded compile-time constant"))
        self.assertTrue(self.has_note(result, "NOT derivable from any live account read"))
        self.assertTrue(self.has_note(result, "OR-gated, either key alone gates create_operator_account/close_operator_account"))
        for admin in METEORA_ADMINS:
            self.assertTrue(self.has_note(result, admin))

    def test_admins_note_carries_the_admins_path_own_scores(self):
        # `has_note` would be satisfied by the separate "combined" note, which
        # ends with the same digits. The ADMINS[] note itself must end with
        # the on-curve band (METHODOLOGY.md 6.1: bare key = 5 / 0 / 0).
        (note,) = self.notes_starting(self._score(), "ADMINS[]")
        self.assertTrue(note.endswith("adminKey=5 multisig=0 timelock=0"), note)
        for admin in METEORA_ADMINS:
            self.assertIn(admin, note)

    def test_notes_report_the_matched_upgrade_multisig_and_that_squads_v3_has_no_timelock(self):
        result = self._score()
        self.assertTrue(self.has_note(result, f"program.upgrade_authority = {METEORA_UPGRADE_AUTHORITY}"))
        self.assertTrue(self.has_note(result, "-- MATCH"))
        self.assertFalse(self.has_note(result, "MISMATCH"))
        self.assertTrue(self.has_note(result, "program upgrade Squads v3: 4-of-7, no time-lock field"))
        self.assertTrue(self.has_note(
            result, "combined (min over both full-power paths, METHODOLOGY.md 6.2): adminKey=5 multisig=0 timelock=0"))

    def test_reads_the_program_and_only_the_documented_multisig_at_authority_index_1(self):
        # Documented: program `cpamdp...`, Squads v3 `CoEsyk...`, authority
        # index 1 (`JADaUV...`). Neither the read ORDER nor the number of times
        # the multisig is fetched is asserted: both are implementation detail of
        # `_resolve_squads_v3` that a caching refactor may change.
        self._score()
        self.assertEqual(set(self.chain.calls), {
            ("read_program", METEORA_PROGRAM),
            ("read_squadsv3", (METEORA_UPGRADE_MS, 1)),
        })

    # -- cap / override rule ------------------------------------------------
    def test_hardcoded_admins_floor_overrides_even_a_unanimous_7_of_7_upgrade_multisig(self):
        # Path A 7-of-7: admin 40+min(20,30)=60; multisig min(100, round(105+40))=100; timelock 0.
        self.chain.squads_v3[METEORA_UPGRADE_MS]["threshold"] = 7
        result = self._score()
        (kw, res), = self.spy.by_kind("squads_v3")
        self.assertEqual(res, (60, 100, 0))
        # ...yet the ADMINS[] path (5,0,0) still sets the combined score.
        self.assertEqual(self.scores(result), (5, 0, 0))
        self.assertEqual(result["compositeScore"], 2)

    # -- unresolved / malformed reads --------------------------------------
    def test_derived_authority_mismatch_drops_path_a_and_its_signers_and_the_admins_floor_still_binds(self):
        # NOTE: the exact Path A band (20/20/0) is pinned by
        # test_with_the_admins_floor_removed_an_unresolved_upgrade_path_...;
        # here the combined score is (5,0,0) whatever Path A degrades to.
        self.chain.programs[METEORA_PROGRAM]["upgrade_authority"] = _key(0x50)
        result = self._score()
        self.assertTrue(self.has_note(result, "MISMATCH, degrading"))
        self.assertEqual(self.spy.by_kind("squads_v3"), [])
        self.assertFalse(self.has_note(result, "program upgrade Squads v3:"))
        self.assertEqual(result["_signers"], set(METEORA_ADMINS))
        self.assertEqual(self.scores(result), (5, 0, 0))
        self.assertEqual(result["compositeScore"], 2)

    def test_mismatch_does_not_read_the_multisig_a_second_time(self):
        self.chain.programs[METEORA_PROGRAM]["upgrade_authority"] = _key(0x50)
        self._score()
        self.assertEqual(self.chain.calls_to("read_squadsv3"), [(METEORA_UPGRADE_MS, 1)])

    def test_none_upgrade_authority_is_a_renounced_program_not_a_failed_read(self):
        # Fixed 2026-09-20: `_resolve_squads_v3` now has the "renounced" branch the v4 helper got on
        # 2026-09-17. A loader-v3 authority of None is the safest state (METHODOLOGY.md 6.1), not a mismatch. The
        # composite is unaffected because the hardcoded ADMINS[] path (5/0/0) dominates either way.
        self.chain.programs[METEORA_PROGRAM]["upgrade_authority"] = None
        result = self._score()
        self.assertTrue(self.has_note(result, "program.upgrade_authority = None"))
        self.assertTrue(self.has_note(result, "upgrade authority is None -- renounced/immutable, the safest band per METHODOLOGY.md 6.1"))
        self.assertFalse(self.has_note(result, "MISMATCH, degrading"))
        self.assertEqual(self.scores(result), (5, 0, 0))
        # a renounced program has no upgrade multisig to read, and its members are not signers
        self.assertEqual(self.chain.calls_to("read_squadsv3"), [])
        self.assertEqual(result["_signers"], set(METEORA_ADMINS))

    def test_missing_derived_authority_key_with_a_live_authority_degrades(self):
        del self.chain.squads_v3[METEORA_UPGRADE_MS]["authority_1"]
        result = self._score()
        self.assertTrue(self.has_note(result, "MISMATCH, degrading"))
        self.assertEqual(self.scores(result), (5, 0, 0))


# ---------------------------------------------------------------------------
# score_marinade
# ---------------------------------------------------------------------------
class TestScoreMarinade(_ChainCase):
    def build_chain(self):
        chain = _Chain()
        _add_marinade(chain)
        return chain

    def _score(self):
        return solana.score_marinade("unused-url")

    # -- happy path: the published score ----------------------------------
    def test_reproduces_the_published_sub_scores_and_composite(self):
        # PUBLISHED (data/scored_targets_2026-09-18-marinade-liquid-staking.md
        # "Result"; chains/solana/deploy/README.md row "Marinade"): combined
        # adminKey 60, multisig 69, timelock 0, oracle 100, composite 45.
        # Hand: Path A 6-of-13 -> admin 40+min(20,25)=60, multisig
        # min(100, round(90+18.46))=100, timelock 0. Path B council
        # ceil(0.50*5)=3-of-5 -> admin 60+min(30,10)=70, multisig round(45+24)=69.
        # min per dimension = (60, 69, 0); floor(24 + 20.7 + 0 + 0.5) = 45.
        result = self._score()
        self.assertEqual(self.scores(result), (60, 69, 0))
        self.assertEqual(result["oracleAuthorityScore"], 100)
        self.assertEqual(result["compositeScore"], 45)

    def test_target_and_label(self):
        result = self._score()
        self.assertEqual(result["target"], MARINADE_STATE)
        self.assertEqual(result["label"], "Marinade Liquid Staking")

    def test_path_a_and_path_b_match_the_published_per_path_table(self):
        # Same note file's per-path table: Path A 60/100/0, Path B 70/69/70.
        # The admin and multisig elements (70 / 69) are reproduced from the
        # published table. The published Path B TIMELOCK (70) is NOT: it came
        # from the additive curve that METHODOLOGY.md section 7's 2026-09-19
        # changelog row replaced by hold-up-only, and the fixture's hold-up (0)
        # is itself unrecorded, so the reconciled-curve value asserted here
        # (hold-up 0 s -> delay curve 0 -> 0) is hand-derived, and is not
        # independent of the code change that introduced that curve.
        self._score()
        (kw_a, res_a), = self.spy.by_kind("squads_v3")
        self.assertEqual(kw_a, {"threshold": 6, "voters": 13})
        self.assertEqual(res_a, (60, 100, 0))
        (kw_b, res_b), = self.spy.by_kind("realms_governance")
        self.assertEqual((kw_b["threshold"], kw_b["voters"]), (3, 5))
        self.assertEqual(res_b[:2], (70, 69))
        self.assertEqual(res_b[2], 0)

    def test_path_b_is_fed_the_governance_timing_fields_unchanged(self):
        # Three DISTINCT values so a swap of any two shows: voting 4 d, cool-off
        # 2 d, hold-up 1 d.
        self.chain.governances_v2[MARINADE_GOVERNANCE].update(
            {"voting_base_time_s": 345600, "voting_cool_off_time_s": 172800, "transactions_hold_up_time_s": 86400})
        result = self._score()
        (kw_b, _), = self.spy.by_kind("realms_governance")
        self.assertEqual((kw_b["voting_s"], kw_b["cooloff_s"], kw_b["holdup_s"]), (345600, 172800, 86400))
        # ...and the disclosure note reports each value under ITS OWN name.
        self.assertTrue(self.has_note(result, "holdup=86400s voting_base=345600s cooloff=172800s"))

    def test_path_a_zero_delay_binds_the_combined_timelock_when_path_b_has_a_holdup(self):
        # Hold-up 86400 s -> delay curve d = 24 h -> 50 + min(30, round(10*(1-1)))
        # = 50 for Path B (hand-derived; see the module docstring for the
        # provenance limit of the timelock curve). Path A (Squads-v3-shaped) has
        # no delay -> 0. Combined timelock = min(0, 50) = 0 (a max would give 50),
        # admin min(60, 70) = 60, multisig min(100, 69) = 69,
        # composite floor(24 + 20.7 + 0 + 0.5) = 45.
        _add_marinade(self.chain, holdup_s=86400)
        result = self._score()
        (_, res_b), = self.spy.by_kind("realms_governance")
        self.assertEqual(res_b, (70, 69, 50))
        self.assertEqual(self.scores(result), (60, 69, 0))
        self.assertEqual(result["compositeScore"], 45)

    def test_an_unresolved_path_a_still_binds_the_timelock_at_zero_when_path_b_has_a_holdup(self):
        # Path A degraded (20,20,0) vs Path B (70,69,50): min timelock 0.
        # composite floor(8 + 6 + 0 + 0.5) = 14.
        _add_marinade(self.chain, holdup_s=86400)
        self.chain.programs[MARINADE_PROGRAM]["upgrade_authority"] = _key(0x31)
        result = self._score()
        self.assertEqual(self.scores(result), (20, 20, 0))
        self.assertEqual(result["compositeScore"], 14)

    def test_signers_are_the_union_of_multisig_owners_and_council_owners(self):
        result = self._score()
        council = {MARINADE_COUNCIL_REAL_OWNER} | {_key(0x60 + i) for i in range(4)}
        self.assertEqual(result["_signers"], set(_REAL_LEGACY_MULTISIG["owners"]) | council)
        # documented cross-exposure: the real council owner is on both paths,
        # so 13 owners + 4 other council seats = 17 distinct keys.
        self.assertEqual(len(result["_signers"]), 17)
        self.assertIn(MARINADE_COUNCIL_REAL_OWNER, result["_signers"])

    def test_notes_carry_the_disclosed_legacy_multisig_limits(self):
        result = self._score()
        self.assertTrue(self.has_note(result, f"program.upgrade_authority = {MARINADE_UPGRADE_AUTHORITY}"))
        self.assertTrue(self.has_note(result, "canonical bump=253, stored nonce=253"))
        self.assertTrue(self.has_note(result, "-- MATCH"))
        self.assertTrue(self.has_note(
            result, "program upgrade legacy multisig: 6-of-13 delay=0s (no timelock field exists on this account type)"))

    def test_notes_carry_the_council_census_and_threshold_derivation(self):
        result = self._score()
        self.assertTrue(self.has_note(result, f"State.admin_authority = {MARINADE_ADMIN_AUTHORITY}"))
        self.assertTrue(self.has_note(result, "5 TokenOwnerRecords with nonzero deposit"))
        self.assertTrue(self.has_note(result, "council mint supply=5 (matches deposit sum, live-checked)"))
        self.assertTrue(self.has_note(result, "council_vote_threshold=50% -> ceil(50%*5)=3-of-5"))
        self.assertTrue(self.has_note(result, "community voting confirmed Disabled on this record"))
        self.assertTrue(self.has_note(result, "holdup=0s voting_base=259200s cooloff=0s"))
        self.assertTrue(self.has_note(
            result, "combined (min over both full-power paths, METHODOLOGY.md 6.2): adminKey=60 multisig=69 timelock=0"))

    def test_reads_exactly_the_documented_accounts(self):
        # The accounts the docstring says are read: the program, the legacy
        # multisig, State, the council Governance, its TokenOwnerRecords and the
        # council mint. Order is NOT asserted (nothing documents it).
        self._score()
        self.assertEqual(set(self.chain.calls), {
            ("read_program", MARINADE_PROGRAM),
            ("read_legacy_serum_multisig", MARINADE_UPGRADE_MS),
            ("read_marinade_state", MARINADE_STATE),
            ("read_governance_v2", MARINADE_GOVERNANCE),
            ("list_token_owner_records", (MARINADE_GOV_PROGRAM, MARINADE_REALM, MARINADE_COUNCIL_MINT)),
            ("read_mint", MARINADE_COUNCIL_MINT),
        })

    # -- path A unresolved ---------------------------------------------------
    def test_upgrade_authority_mismatch_degrades_path_a_to_20_20_0(self):
        self.chain.programs[MARINADE_PROGRAM]["upgrade_authority"] = _key(0x31)
        result = self._score()
        self.assertTrue(self.has_note(result, "MISMATCH, degrading"))
        self.assertFalse(self.has_note(result, "program upgrade legacy multisig:"))
        self.assertEqual(self.spy.by_kind("squads_v3"), [])
        # Path A (20,20,0) vs Path B (70,69,.) -> (20,20,0); floor(8 + 6 + 0 + 0.5) = 14
        self.assertEqual(self.scores(result), (20, 20, 0))
        self.assertEqual(result["compositeScore"], 14)
        # the multisig owners are not counted as signers; only the council is
        self.assertEqual(result["_signers"], {MARINADE_COUNCIL_REAL_OWNER} | {_key(0x60 + i) for i in range(4)})

    def test_stored_nonce_not_the_canonical_bump_degrades_path_a(self):
        self.chain.legacy_multisigs[MARINADE_UPGRADE_MS]["nonce"] = 252
        result = self._score()
        self.assertTrue(self.has_note(result, "canonical bump=253, stored nonce=252"))
        self.assertEqual(self.scores(result), (20, 20, 0))

    def test_none_upgrade_authority_is_reported_as_renounced_not_a_failed_read(self):
        self.chain.programs[MARINADE_PROGRAM]["upgrade_authority"] = None
        result = self._score()
        self.assertTrue(self.has_note(result, "program.upgrade_authority = None"))
        self.assertTrue(self.has_note(result, "upgrade authority is None -- renounced/immutable, the safest band per METHODOLOGY.md 6.1"))
        self.assertFalse(self.has_note(result, "MISMATCH, degrading"))
        # a renounced program has no upgrade multisig: its owners are not counted as signers, only the council is
        # (same census as the degraded-path-A test above)
        self.assertEqual(result["_signers"], {MARINADE_COUNCIL_REAL_OWNER} | {_key(0x60 + i) for i in range(4)})

    # Fixed 2026-09-20. METHODOLOGY.md 6.1 scores an upgrade authority of None (renounced/immutable)
    # 100/100/100, and the 2026-09-17 fixes wired that up for Jupiter v6 and the Squads v4 helper;
    # `_resolve_legacy_serum_multisig` lacked the branch, so a renounced Marinade program was scored as a failed read
    # (20/20/0). Documented value: Path A = (100,100,100), Path B = (70,69,0) (fixture hold-up 0), combined
    # (70,69,0), composite floor(28+20.7+0+0.5) = 49.
    def test_renounced_upgrade_authority_should_score_the_safest_band_per_methodology_6_1(self):
        self.chain.programs[MARINADE_PROGRAM]["upgrade_authority"] = None
        result = self._score()
        self.assertEqual(self.scores(result), (70, 69, 0))
        self.assertEqual(result["compositeScore"], 49)

    # -- path B unresolved ---------------------------------------------------
    def test_admin_authority_that_is_not_the_native_treasury_degrades_path_b_and_skips_the_governance_reads(self):
        self.chain.marinade_states[MARINADE_STATE]["admin_authority"] = _key(0x32)
        result = self._score()
        self.assertTrue(self.has_note(
            result, "admin_authority does NOT match the offline-derived native-treasury PDA of "
                    f"{MARINADE_GOVERNANCE} ({MARINADE_ADMIN_AUTHORITY}) -- degrading"))
        for name in ("read_governance_v2", "list_token_owner_records", "read_mint"):
            self.assertEqual(self.chain.calls_to(name), [], name)
        self.assertEqual(self.spy.by_kind("realms_governance"), [])
        # Path A (60,100,0) vs Path B (20,20,0) -> (20,20,0), composite 14
        self.assertEqual(self.scores(result), (20, 20, 0))
        self.assertEqual(result["compositeScore"], 14)
        # only the 13 multisig owners are signers (no council census was read)
        self.assertEqual(result["_signers"], set(_REAL_LEGACY_MULTISIG["owners"]))

    def test_both_paths_unresolved_gives_20_20_0_and_no_signers(self):
        self.chain.programs[MARINADE_PROGRAM]["upgrade_authority"] = _key(0x31)
        self.chain.marinade_states[MARINADE_STATE]["admin_authority"] = _key(0x32)
        result = self._score()
        self.assertEqual(self.scores(result), (20, 20, 0))
        self.assertEqual(result["compositeScore"], 14)
        self.assertEqual(result["_signers"], set())

    # -- stale-assumption aborts (the function raises rather than mis-scoring)
    def test_wrong_msol_mint_aborts_before_reading_the_governance(self):
        self.chain.marinade_states[MARINADE_STATE]["msol_mint"] = _key(0x33)
        with self.assertRaisesRegex(ValueError, "!= expected mSOL mint -- wrong account, aborting"):
            self._score()
        self.assertEqual(self.chain.calls_to("read_governance_v2"), [])

    def test_governance_of_a_different_realm_aborts(self):
        self.chain.governances_v2[MARINADE_GOVERNANCE]["realm"] = _key(0x34)
        with self.assertRaisesRegex(ValueError, f"!= expected {MARINADE_REALM} -- wrong account, aborting"):
            self._score()
        self.assertEqual(self.chain.calls_to("list_token_owner_records"), [])

    def test_community_voting_no_longer_disabled_aborts(self):
        self.chain.governances_v2[MARINADE_GOVERNANCE]["community_vote_threshold"] = {
            "tag": 0, "kind": "YesVotePercentage", "pct": 1}
        with self.assertRaisesRegex(ValueError, "community voting is no longer Disabled"):
            self._score()

    def test_council_threshold_of_another_kind_aborts(self):
        for kind in ("QuorumPercentage", "Disabled"):
            with self.subTest(kind=kind):
                self.chain.governances_v2[MARINADE_GOVERNANCE]["council_vote_threshold"] = {
                    "tag": 1, "kind": kind, "pct": None if kind == "Disabled" else 50}
                with self.assertRaisesRegex(ValueError, "council_vote_threshold is no longer YesVotePercentage"):
                    self._score()

    def test_council_mint_supply_diverging_from_the_deposit_sum_aborts(self):
        # deposits sum to 5; supply 6 (a mint) and 4 (a partial withdrawal) both abort.
        for supply in (6, 4):
            with self.subTest(supply=supply):
                self.chain.mints[MARINADE_COUNCIL_MINT]["supply"] = supply
                with self.assertRaisesRegex(
                        ValueError, r"the deposit-sum/mint-supply assumption this scorer relies on is stale"):
                    self._score()

    # -- council census / threshold derivation -------------------------------
    def test_zero_deposit_records_are_not_voters_and_not_signers(self):
        ghost = _key(0x66)
        council = [(MARINADE_COUNCIL_REAL_OWNER, 1)] + [(_key(0x60 + i), 1) for i in range(4)] + [(ghost, 0)]
        _add_marinade(self.chain, council=council)
        result = self._score()
        self.assertNotIn(ghost, result["_signers"])
        self.assertTrue(self.has_note(result, "5 TokenOwnerRecords with nonzero deposit"))
        self.assertEqual(self.scores(result), (60, 69, 0))

    def test_single_seat_council_scores_like_a_bare_key(self):
        # supply 1, 50% -> ceil(0.5) = 1-of-1 -> (5,0) per METHODOLOGY.md 6.1.
        _add_marinade(self.chain, council=[(MARINADE_COUNCIL_REAL_OWNER, 1)])
        result = self._score()
        self.assertTrue(self.has_note(result, "ceil(50%*1)=1-of-1"))
        # Path A (60,100,0), Path B (5,0,0): floor(0.4*5 + 0 + 0 + 0.5) = 2
        self.assertEqual(self.scores(result), (5, 0, 0))
        self.assertEqual(result["compositeScore"], 2)

    def test_two_of_four_council_lowers_only_the_multisig_dimension(self):
        # supply 4, 50% -> 2-of-4: admin 60+min(30,5)=65, multisig round(30+20)=50.
        # combined: admin min(60,65)=60, multisig min(100,50)=50, timelock 0.
        _add_marinade(self.chain, council=[(_key(0x60 + i), 1) for i in range(4)])
        result = self._score()
        self.assertTrue(self.has_note(result, "ceil(50%*4)=2-of-4"))
        self.assertEqual(self.scores(result), (60, 50, 0))
        # floor(24 + 15 + 0 + 0.5) = 39
        self.assertEqual(result["compositeScore"], 39)

    def test_percentage_that_divides_evenly_gives_the_exact_countable_threshold(self):
        # 60% of 5 = 3 exactly (same 3-of-5 as the published case).
        _add_marinade(self.chain, pct=60)
        result = self._score()
        self.assertTrue(self.has_note(result, "council_vote_threshold=60% -> ceil(60%*5)=3-of-5"))
        self.assertEqual(self.scores(result), (60, 69, 0))

    def test_non_unit_weight_council_is_thresholded_on_total_weight_not_seat_count(self):
        # 5 seats holding 2 tokens each: mint supply 10, 50% -> ceil(0.5*10) = 5
        # -> 5-of-10 BY WEIGHT (the seat count, 5, must not be used as the
        # denominator: that would read 5-of-5). Hand: admin 60 + min(30, 5*4) = 80;
        # multisig min(100, round(15*5 + 40*5/10)) = round(75 + 20) = 95;
        # timelock 0. Combined with Path A (60,100,0): (60, 95, 0);
        # composite floor(0.4*60 + 0.3*95 + 0 + 0.5) = floor(24 + 28.5 + 0.5) = 53.
        seats = [(_key(0x60 + i), 2) for i in range(5)]
        _add_marinade(self.chain, council=seats)
        result = self._score()
        (kw_b, res_b), = self.spy.by_kind("realms_governance")
        self.assertEqual((kw_b["threshold"], kw_b["voters"]), (5, 10))
        self.assertEqual(res_b, (80, 95, 0))
        self.assertEqual(self.scores(result), (60, 95, 0))
        self.assertEqual(result["compositeScore"], 53)
        self.assertTrue(self.has_note(result, "5 TokenOwnerRecords with nonzero deposit"))
        self.assertTrue(self.has_note(result, "council mint supply=10 (matches deposit sum, live-checked)"))
        self.assertTrue(self.has_note(result, "council_vote_threshold=50% -> ceil(50%*10)=5-of-10"))
        self.assertEqual(result["_signers"], set(_REAL_LEGACY_MULTISIG["owners"]) | {s for s, _ in seats})

    def test_sixty_percent_of_seven_equal_seats_is_the_documented_five_of_seven(self):
        # data/finding_2026-09-17-spl-governance-shared-instance-controller.md:
        # a 60% threshold over 7 one-token seats is ceil(0.6*7) = ceil(4.2) = 5,
        # "an effective 5-of-7 council" (a real, non-integer ceiling). Seat keys
        # are synthetic (that DAO's members are not used). Path B 5-of-7: admin
        # 60 + min(30, 5*4) = 80; multisig min(100, round(75 + 28.57)) = 100
        # (cap). Combined with Path A (60,100,0): (60, 100, 0);
        # composite floor(24 + 30 + 0 + 0.5) = 54.
        _add_marinade(self.chain, council=[(_key(0x60 + i), 1) for i in range(7)], pct=60)
        result = self._score()
        (kw_b, res_b), = self.spy.by_kind("realms_governance")
        self.assertEqual((kw_b["threshold"], kw_b["voters"]), (5, 7))
        self.assertEqual(res_b[:2], (80, 100))
        self.assertTrue(self.has_note(result, "council_vote_threshold=60% -> ceil(60%*7)=5-of-7"))
        self.assertEqual(self.scores(result), (60, 100, 0))
        self.assertEqual(result["compositeScore"], 54)

    def test_unanimous_council_hits_the_multisig_cap_of_100(self):
        # 100% of 5 -> 5-of-5: admin 60+min(30,20)=80; multisig min(100, round(75+40))=100
        # (cap). Combined: admin min(60,80)=60, multisig 100, timelock 0;
        # floor(24 + 30 + 0 + 0.5) = 54.
        _add_marinade(self.chain, pct=100)
        result = self._score()
        (_, res_b), = self.spy.by_kind("realms_governance")
        self.assertEqual(res_b[:2], (80, 100))
        self.assertEqual(self.scores(result), (60, 100, 0))
        self.assertEqual(result["compositeScore"], 54)

    def test_empty_council_census_never_silently_returns_a_score(self):
        # No voters and supply 0: deposit sum == supply == 0, threshold
        # ceil(0.5*0) = 0, and the shared formula divides 40*0/0. Today that is a
        # ZeroDivisionError (an accidental guard); an explicit ValueError guard
        # would be a better one and also passes. Any OTHER exception (the
        # harness's AssertionError for a missing fixture, a TypeError, ...) or a
        # returned score fails. The census reads must have happened, so the
        # failure comes from the arithmetic and not from a missing fixture.
        _add_marinade(self.chain, council=[], supply=0)
        with self.assertRaises((ZeroDivisionError, ValueError)):
            self._score()
        self.assertEqual(
            self.chain.calls_to("list_token_owner_records"),
            [(MARINADE_GOV_PROGRAM, MARINADE_REALM, MARINADE_COUNCIL_MINT)])
        self.assertEqual(self.chain.calls_to("read_mint"), [MARINADE_COUNCIL_MINT])

    # Regression test: math.ceil(pct / 100 * weight) was off by one for 28% of 25 (fixed 2026-09-20).
    def test_threshold_is_the_exact_ceiling_not_a_float_artifact(self):
        owners = [_key(0x80 + i) for i in range(5)]
        _add_marinade(self.chain, council=[(o, 5) for o in owners], pct=28)
        result = self._score()
        self.assertTrue(self.has_note(result, "ceil(28%*25)=7-of-25"))

    # FINDING (oddity, latent): METHODOLOGY.md 6.1 defines `t` as the threshold
    # "in signers when countable" and scores any t = 1 as a bare key (5/0/0).
    # The scorer divides by council WEIGHT, not by distinct signers, so one
    # member holding >= the threshold weight would still be scored as a
    # 3-of-5 multisig. Live weights are 1 each, so today's 45 is unaffected.
    # Documented value asserted: owner A holds 3 of 5 tokens (threshold weight
    # 3), so a single key passes proposals -> t = 1 -> Path B (5,0,0) ->
    # combined (5,0,0).
    @unittest.expectedFailure
    def test_a_member_holding_the_whole_threshold_weight_should_score_as_a_single_key(self):
        big, small1, small2 = _key(0x90), _key(0x91), _key(0x92)
        _add_marinade(self.chain, council=[(big, 3), (small1, 1), (small2, 1)])
        result = self._score()
        self.assertEqual(self.scores(result), (5, 0, 0))


# ---------------------------------------------------------------------------
# score_all
# ---------------------------------------------------------------------------
def _stub_result(label, signers, composite=50):
    return {"target": "target-of-" + label, "label": label,
            "adminKeyScore": 50, "multisigScore": 50, "timelockScore": 50,
            "oracleAuthorityScore": 100, "compositeScore": composite,
            "notes": [], "_signers": set(signers)}


def _stub_scorer(name, result):
    def scorer(url):
        scorer.seen_urls.append(url)
        return result

    scorer.seen_urls = []
    scorer.__name__ = name
    return scorer


class TestScoreAll(_ChainCase):
    def build_chain(self):
        chain = _Chain()
        _add_solend(chain)
        _add_meteora(chain)
        _add_marinade(chain)
        return chain

    def _patch_scorers(self, scorers):
        p = mock.patch.object(solana, "SIMPLE_SCORERS", scorers)
        p.start()
        self.addCleanup(p.stop)

    def _run(self, url="unused-url"):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            results = solana.score_all(url)
        return results, buf.getvalue()

    # -- the real registry -------------------------------------------------
    def test_registry_lists_the_thirteen_published_scorers_then_the_five_added_on_2026_09_20(self):
        # chains/solana/deploy/README.md: the oracle holds 13 targets (the first 13 scorers, in push order); five more
        # were added on 2026-09-20 (test_solana_staking_and_save_scorers.py pins their order) and are not on-chain yet.
        self.assertEqual(len(solana.SIMPLE_SCORERS), 18)
        self.assertEqual(solana.SIMPLE_SCORERS[12], solana.score_marinade)  # the 13th published scorer is unchanged
        for fn in (solana.score_solend_dao_governance, solana.score_meteora_damm_v2, solana.score_marinade):
            self.assertIn(fn, solana.SIMPLE_SCORERS)

    # -- real scorer bodies, end to end -------------------------------------
    def _real_three(self):
        self._patch_scorers([solana.score_solend_dao_governance, solana.score_meteora_damm_v2, solana.score_marinade])

    def test_real_scorers_publish_their_documented_scores_through_score_all(self):
        self._real_three()
        results, out = self._run()
        self.assertEqual(out, "")
        by_label = {r["label"]: r for r in results}
        self.assertEqual(len(results), 3)
        # (composite, admin, multisig, timelock, oracle) from chains/solana/deploy/README.md
        self.assertEqual(
            {label: (r["compositeScore"], r["adminKeyScore"], r["multisigScore"], r["timelockScore"], r["oracleAuthorityScore"])
             for label, r in by_label.items()},
            {"Solend DAO (governance realm)": (2, 5, 0, 0, 100),
             "Meteora DAMM v2": (2, 5, 0, 0, 100),
             "Marinade Liquid Staking": (45, 60, 69, 0, 100)})

    def test_real_scorers_with_disjoint_signers_publish_cross_exposure_100(self):
        # README: Solend 100, Marinade 100 (Meteora's published 60 needs the Jupiter
        # signers, see the stub-based test below). No signer is shared among these three.
        self._real_three()
        results, _ = self._run()
        self.assertEqual([r["crossExposureScore"] for r in results], [100, 100, 100])
        for r in results:
            self.assertFalse(any("shares at least one signer" in n for n in r["notes"]), r["label"])

    def test_private_signer_sets_are_removed_from_every_published_result(self):
        self._real_three()
        results, _ = self._run()
        for r in results:
            self.assertNotIn("_signers", r)

    def test_scorers_run_in_registry_order_and_receive_the_url(self):
        first = _stub_scorer("first", _stub_result("A", []))
        second = _stub_scorer("second", _stub_result("B", []))
        self._patch_scorers([first, second])
        results, _ = self._run("https://rpc.example.invalid")
        self.assertEqual([r["label"] for r in results], ["A", "B"])
        self.assertEqual(first.seen_urls, ["https://rpc.example.invalid"])
        self.assertEqual(second.seen_urls, ["https://rpc.example.invalid"])

    def test_two_targets_sharing_a_signer_with_meteora_cost_it_40_the_arithmetic_behind_60(self):
        # ARITHMETIC test, not a reproduction of the published number. The
        # README publishes Meteora crossExposure = 60 = 100 - 20 * 2 (formula:
        # METHODOLOGY.md section 4, `max(0, 100 - 20 n)`). Which two scored
        # targets Meteora overlaps with is NOT recorded (the scouting note gives
        # only the group-level meteora <-> jupiter overlap, one key inside the
        # Jupiter Perps 4-of-8), so the two "Jupiter" targets here are INVENTED
        # stand-ins: both share one key with Meteora's multisig and one with
        # each other.
        #   Meteora shares with v6 and Perps -> 100 - 20*2 = 60
        #   v6 shares with Meteora and Perps -> 60;  Perps likewise -> 60
        v6 = _stub_result("Jupiter Aggregator v6", [METEORA_MEMBER_KEYS[0], _key(0xA0)])
        perps = _stub_result("Jupiter Perpetual Exchange", [METEORA_MEMBER_KEYS[1], _key(0xA0)])
        self._patch_scorers([
            _stub_scorer("score_jupiter_aggregator_v6", v6),
            solana.score_solend_dao_governance,
            _stub_scorer("score_jupiter_perps", perps),
            solana.score_meteora_damm_v2,
            solana.score_marinade,
        ])
        results, out = self._run()
        self.assertEqual(out, "")
        by_label = {r["label"]: r for r in results}
        self.assertEqual(by_label["Meteora DAMM v2"]["crossExposureScore"], 60)
        self.assertEqual(by_label["Jupiter Aggregator v6"]["crossExposureScore"], 60)
        self.assertEqual(by_label["Jupiter Perpetual Exchange"]["crossExposureScore"], 60)
        self.assertEqual(by_label["Solend DAO (governance realm)"]["crossExposureScore"], 100)
        self.assertEqual(by_label["Marinade Liquid Staking"]["crossExposureScore"], 100)
        self.assertIn(
            "shares at least one signer with: ['Jupiter Aggregator v6', 'Jupiter Perpetual Exchange']",
            by_label["Meteora DAMM v2"]["notes"])

    # -- failure isolation ---------------------------------------------------
    def test_one_failing_scorer_is_skipped_and_reported_and_the_others_still_score(self):
        def boom(url):
            raise ValueError("boom")

        ok = _stub_scorer("ok_scorer", _stub_result("Only", []))
        self._patch_scorers([boom, ok])
        results, out = self._run()
        self.assertEqual([r["label"] for r in results], ["Only"])
        self.assertEqual(out, "score_all(): SKIPPED boom this run -- ValueError: boom\n")

    def test_a_real_scorer_that_aborts_on_a_stale_assumption_is_skipped_not_fatal(self):
        self.chain.marinade_states[MARINADE_STATE]["msol_mint"] = _key(0x33)
        self._real_three()
        results, out = self._run()
        self.assertEqual([r["label"] for r in results], ["Solend DAO (governance realm)", "Meteora DAMM v2"])
        self.assertTrue(out.startswith("score_all(): SKIPPED score_marinade this run -- ValueError: State msol_mint"))

    def test_every_scorer_failing_returns_an_empty_list(self):
        def boom(url):
            raise RuntimeError("down")

        self._patch_scorers([boom])
        results, out = self._run()
        self.assertEqual(results, [])
        self.assertIn("SKIPPED boom this run -- RuntimeError: down", out)

    def test_no_scorers_returns_an_empty_list(self):
        self._patch_scorers([])
        results, out = self._run()
        self.assertEqual((results, out), ([], ""))

    # -- list results and cross-exposure arithmetic --------------------------
    def test_only_a_list_is_flattened_a_tuple_is_one_malformed_result(self):
        # CHARACTERIZATION of the contract boundary: score_all() flattens a
        # `list`; anything else is taken to be ONE result dict. A tuple of
        # result dicts is out of contract, so it is not flattened and the
        # cross-exposure pass (which needs a dict) rejects it with a TypeError
        # -- outside the per-scorer try/except, so it is not swallowed as a
        # "SKIPPED" line.
        a, b = _stub_result("A", []), _stub_result("B", [])
        self._patch_scorers([_stub_scorer("tuple_scorer", (a, b))])
        with self.assertRaises(TypeError):
            self._run()

    def test_a_scorer_returning_a_list_is_flattened_into_the_results(self):
        a, b = _stub_result("A", []), _stub_result("B", [])
        c = _stub_result("C", [])
        self._patch_scorers([_stub_scorer("many", [a, b]), _stub_scorer("one", c)])
        results, _ = self._run()
        self.assertEqual([r["label"] for r in results], ["A", "B", "C"])

    def test_a_single_shared_signer_costs_20_for_each_of_the_two_targets(self):
        a = _stub_result("A", ["k1", "k2"])
        b = _stub_result("B", ["k2", "k3"])
        self._patch_scorers([_stub_scorer("a", a), _stub_scorer("b", b)])
        results, _ = self._run()
        self.assertEqual([r["crossExposureScore"] for r in results], [80, 80])
        self.assertIn("shares at least one signer with: ['B']", results[0]["notes"])
        self.assertIn("shares at least one signer with: ['A']", results[1]["notes"])

    def test_sharing_many_signers_with_the_same_target_is_still_one_overlap(self):
        a = _stub_result("A", ["k1", "k2", "k3"])
        b = _stub_result("B", ["k1", "k2", "k3"])
        self._patch_scorers([_stub_scorer("a", a), _stub_scorer("b", b)])
        results, _ = self._run()
        self.assertEqual([r["crossExposureScore"] for r in results], [80, 80])

    def test_cross_exposure_score_never_goes_below_zero(self):
        # 7 targets all sharing "k": each has 6 others -> 100 - 120 -> floored at 0.
        stubs = [_stub_scorer(f"s{i}", _stub_result(f"T{i}", ["k"])) for i in range(7)]
        self._patch_scorers(stubs)
        results, _ = self._run()
        self.assertEqual([r["crossExposureScore"] for r in results], [0] * 7)

    def test_five_overlapping_targets_score_exactly_zero(self):
        stubs = [_stub_scorer(f"s{i}", _stub_result(f"T{i}", ["k"])) for i in range(6)]
        self._patch_scorers(stubs)
        results, _ = self._run()
        # 5 others -> 100 - 100 = 0
        self.assertEqual([r["crossExposureScore"] for r in results], [0] * 6)

    def test_a_target_with_no_signers_is_neither_penalised_nor_listed_as_sharing(self):
        renounced = _stub_result("Renounced", [])
        other = _stub_result("Other", ["k1"])
        self._patch_scorers([_stub_scorer("r", renounced), _stub_scorer("o", other)])
        results, _ = self._run()
        self.assertEqual([r["crossExposureScore"] for r in results], [100, 100])
        self.assertEqual(results[0]["notes"], [])
        self.assertEqual(results[1]["notes"], [])

    def test_disjoint_signers_publish_100_and_add_no_note(self):
        a = _stub_result("A", ["k1"])
        b = _stub_result("B", ["k2"])
        self._patch_scorers([_stub_scorer("a", a), _stub_scorer("b", b)])
        results, _ = self._run()
        self.assertEqual([r["crossExposureScore"] for r in results], [100, 100])
        self.assertEqual([r["notes"] for r in results], [[], []])


# ---------------------------------------------------------------------------
# _composite: the shared arithmetic every scorer above ends with
# ---------------------------------------------------------------------------
class TestCompositeArithmetic(unittest.TestCase):
    def test_the_published_half_boundary_composites_round_up(self):
        # (5, 0, 0): floor(2.0 + 0 + 0 + 0.5) = 2 (published for Solend, Meteora
        # and Orca); (60, 69, 0): floor(24 + 20.7 + 0 + 0.5) = 45 (Marinade).
        self.assertEqual(solana._composite(5, 0, 0), 2)
        self.assertEqual(solana._composite(60, 69, 0), 45)

    # Regression test: the float form of _composite was one low for 2054 triples (fixed 2026-09-20).
    def test_composite_at_an_exact_half_boundary_rounds_up_per_the_written_formula(self):
        self.assertEqual(solana._composite(40, 57, 48), 48)


if __name__ == "__main__":
    unittest.main()
