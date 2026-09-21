"""
Body-level unit tests for `chains/plasma-ecosystem/scorers.py::
score_fluid_liquidity_plasma()`.

Until now this function's body (51 statements) was executed by NO unit test:
it was only ever checked by live runs against `https://rpc.plasma.to`. These
tests run the REAL body with the chain reads patched, so the published score
and every branch are pinned offline.

Same approach as `test_plasma_ecosystem_scorers.py` (the sibling file for the
other Plasma scorers): monkeypatch the read-primitive names the scorer
imported into its own namespace (`read_address_getter`, `call_raw`,
`safe_owners_and_threshold`, `read_slot_as_address`), never the transport,
and fake the two direct `w3.eth.get_code` calls with a small `FakeW3`. The
scorer's own private helper `_has_role` is NOT patched: it runs for real on
top of the faked `call_raw`, so the hasRole call shape (ABI, role hash,
checksummed account) is exercised too.

One class (`TestFluidReplayOfDocumentedRawPayloads`) goes one level lower and
patches NOTHING in the scorer: it feeds the raw JSON-RPC answers that
`chains/plasma-ecosystem/data/fluid_liquidity_plasma_2026-09-18.md` documents
verbatim to a real `Web3` through an offline provider, so the real
`call_raw` / `read_address_getter` / `safe_owners_and_threshold` / `_has_role`
run end to end. That is the evidence that the hand-built `FakePlasma` model
below (a missing entry means "reverted") agrees with recorded chain answers.

FIXTURE PROVENANCE. No expected value here was obtained by running the
function and copying its output. Each one is one of:

  * a documented real observation, cited next to the fixture:
      - `chains/plasma-ecosystem/data/fluid_liquidity_plasma_2026-09-18.md`
        ("FLUID NOTE" below, section numbers are that file's),
      - the score row in
        `chains/plasma-ecosystem/data/scored_targets_2026-09-18.md` (row 6)
        and the on-chain read-back table in
        `chains/plasma-ecosystem/deploy/README.md` ("Current on-chain scores
        (re-push, 2026-09-20)", row 6): admin 40, multisig 100, timelock 70,
        oracle 100, cross 100, composite 67. That is what the oracle holds until the
        next re-push; since 2026-09-20 the scorer gives 65 / 55 / 55 / 100 / 80 / 59
        (the SCORED constant below, from the signer reads of
        `chains/plasma-ecosystem/data/fluid_liquidity_plasma_2026-09-20_signers.md`);
      - the scorer's own docstring for `score_fluid_liquidity_plasma`;
  * an arithmetic derivation done by hand from METHODOLOGY.md's written
    formula, `compositeScore = floor(0.4*admin + 0.3*multisig + 0.3*timelock
    + 0.5)`, written here as the exact-integer identity
    `(4*a + 3*m + 3*t + 5) // 10` (`_hand_composite`) and, in the branch
    table, as a hand-computed LITERAL next to its arithmetic. Never via
    `scorers._composite` (that helper is only ever the SUBJECT of
    `TestCompositeHelperRoundsHalfUp`, compared against hand values), and
    never from sub-scores the function itself returned;
  * a value re-derived independently from its definition (OpenZeppelin role
    hashes, function selectors and the EIP-1967 admin slot via keccak256);
  * a SYNTHETIC fixture, i.e. an invented state used to reach a branch that
    the live chain does not exhibit. Every synthetic value is defined once in
    the "SYNTHETIC FIXTURES" block below, named `SYNTH_*`, and is NOT a
    documented observation: the bare-EOA address, the plain-contract address
    and its code size, the Safe address / its code size / its owners, the
    role-holder stand-ins, and the hypothetical delays.

Three kinds of deliberate "the code and the documentation disagree" markers:

  * `unittest.expectedFailure` tests keep asserting what the documentation says
    and the function currently does not do. Each has a comment naming the
    documented source and the disagreement; the same items are listed as
    findings in the report that accompanied this file. If production code is
    fixed the test flips to "unexpected success" and the marker must be removed.
  * CHARACTERIZATION tests pin what the function returns TODAY for a branch
    whose value one of those expectedFailure tests says is wrong. They exist so
    that a silent change of the wrong value is noticed (an expectedFailure test
    alone cannot: any other wrong value keeps it failing as expected). They are
    labelled `CHARACTERIZATION`, and must be deleted together with their paired
    expectedFailure marker when the production code is fixed.
  * Note-WORDING tests (`TestFluidPublishedNoteWording`) pin the disclosure
    clauses of the published notes. The wording is the scorer's own; they are
    change detectors that stop a disclosure being deleted silently, not
    independent evidence. The value-bearing facts are in
    `TestFluidPublishedNoteFacts`.
"""
import importlib.util
import os
import sys
import unittest
from unittest import mock

from eth_abi import encode as encode_abi
from eth_utils import function_abi_to_4byte_selector
from web3 import Web3 as RealWeb3
from web3.providers import BaseProvider

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


sys.path.insert(0, os.path.join(REPO_ROOT, "scripts", "lib"))
scorers = _load_module("aro_test_plasma_scorer_bodies", "chains/plasma-ecosystem/scorers.py")
import web3_utils  # noqa: E402  (on sys.path just above; used to check one selector and to silence retry sleeps)


# --- Documented real observations (FLUID NOTE = data/fluid_liquidity_plasma_2026-09-18.md) ---

# FLUID NOTE sec.2 (deployments.md `plasma` row) and sec.3.
LIQUIDITY = "0x52Aa899454998Be5b000Ad077a46Bbe360F4e497"
LIQUIDITY_CODE_BYTES = 4462  # FLUID NOTE sec.3: "4,462 bytes of real, live bytecode"

# FLUID NOTE sec.4: getAdmin() -> 0x...4d6ce4f4498d59eed397bcbc687805a07f9b2346.
TIMELOCK = "0x4d6CE4F4498d59Eed397bCbC687805a07f9b2346"
TIMELOCK_CODE_BYTES = 9741  # FLUID NOTE sec.5: "9,741 bytes ... re-measured precisely via web3.py"
MIN_DELAY = 86400  # FLUID NOTE sec.5: getMinDelay() = 0x15180 = 86400 s = 24 h

# FLUID NOTE sec.5 (constructor args (86400, [proposer], [executor], 0x0)) and sec.6 (hasRole reads).
PROPOSER = "0x4F6F977aCDD1177DCD81aB83074855EcB9C2D49e"
EXECUTOR = "0x196Ed45eC4ACA949E7AA921ceC81e219e682775e"
ZERO = "0x0000000000000000000000000000000000000000"

# FLUID NOTE sec.7: "eth_getCode(proposer) = 327 bytes (re-measured via web3.py)", executor 171 bytes.
# (The scorer's own docstring says "~190 and ~150 bytes"; that disagrees with this later, precise
# re-measurement. Reported as a stale-doc finding, not used here.)
PROPOSER_CODE_BYTES = 327
EXECUTOR_CODE_BYTES = 171

# Read live on Plasma AND on Arbitrum One on 2026-09-20 (data/fluid_liquidity_plasma_2026-09-20_signers.md): the proposer is an
# Avocado multisig (DOMAIN_SEPARATOR_NAME() = "Avocado-Multisig"), requiredSigners() = 6 and signers() = these 12, identical on both
# chains; the executor is a Safe v1.4.1 with threshold 3 and these 5 owners, identical on both chains. Four of the five owners are
# also among the 12 signers (a disclosed concentration, not scored).
PROPOSER_REQUIRED_SIGNERS = 6
PROPOSER_SIGNERS = [
    "0x1d895e5cf6e5288c9a56face942e016696fb0c90",
    "0x2f1584337426e699f449fe4e582816f610a3249f",
    "0x33581f263ddd51035ab61da3b9fbc9563d5f839a",
    "0x5612c18e33ff219f29d463d39bb7e68731638fac",
    "0x7284a8451d9a0e7dc62b3a71c0593ea2ec5c5638",
    "0x88bb9b99084dcf809c4e423b90b2dd402f04c826",
    "0x97399c934d1a8b36ff6bde553bc8ed769ce730bd",
    "0xa32e5237e32b17e6a374dbc4c062eeeb21d69506",
    "0xa7615cd307f323172331865181dc8b80a2834324",
    "0xc0c72156c4007b727d1ca4a583d06a2ff9e554f3",
    "0xc7810aa3b0c6a2778eecc114b93d59b2e9da9e05",
    "0xd33d3fce969f0470c723e45a3e5b34ce2ed78db7",
]
EXECUTOR_OWNERS = [
    "0x599cC75CbC26d6EB20FaF70B9e68a939171fA94d",
    "0x1d895E5CF6E5288C9A56fACE942E016696Fb0C90",
    "0xa7615CD307F323172331865181DC8b80a2834324",
    "0xC0c72156C4007B727d1CA4A583d06A2fF9E554F3",
    "0xD33D3fcE969F0470c723e45A3e5b34cE2eD78db7",
]
EXECUTOR_THRESHOLD = 3

# FLUID NOTE sec.4: EIP-1967 admin slot, "independently recomputed in Python".
EIP1967_ADMIN_SLOT = "0xb53127684a568b3173ae13b9f8a6016e243e63b6e8ee1178d6a717850b5d6103"

# FLUID NOTE sec.4-5: the raw eth_call requests and answers, verbatim (JSON-RPC against rpc.plasma.to).
SEL_OWNER = "0x8da5cb5b"                                     # sec.4  data of the owner() request
SEL_GETADMIN = "0x6e9960c3"                                  # sec.4  data of the getAdmin() request
SEL_GETOWNERS = "0xa0e67e2b"                                 # sec.5  "# getOwners()"
SEL_GETTHRESHOLD = "0xe75235b8"                              # sec.5  "# getThreshold()"
SEL_GETMINDELAY = "0xf27a0c92"                               # sec.5  "# getMinDelay()"
SEL_REQUIRED_SIGNERS = "0x" + RealWeb3.keccak(text="requiredSigners()")[:4].hex()  # 2026-09-20 note: Avocado ABI
SEL_SIGNERS = "0x" + RealWeb3.keccak(text="signers()")[:4].hex()
RAW_OWNER_REVERT_DATA = "0xc44f8d3b000000000000000000000000000000000000000000000000000000000000c351"  # sec.4 error.data
RAW_GETADMIN_RESULT = "0x0000000000000000000000004d6ce4f4498d59eed397bcbc687805a07f9b2346"  # sec.4 result
RAW_GETMINDELAY_RESULT = "0x0000000000000000000000000000000000000000000000000000000000015180"  # sec.5 result
# 2026-09-20 note: the raw answers of the five signer reads, ABI-encoded here from the documented values (the encoding is the standard one).
RAW_REQUIRED_SIGNERS_RESULT = "0x" + encode_abi(["uint8"], [PROPOSER_REQUIRED_SIGNERS]).hex()
RAW_SIGNERS_RESULT = "0x" + encode_abi(["address[]"], [PROPOSER_SIGNERS]).hex()
RAW_EXECUTOR_OWNERS_RESULT = "0x" + encode_abi(["address[]"], [EXECUTOR_OWNERS]).hex()
RAW_EXECUTOR_THRESHOLD_RESULT = "0x" + encode_abi(["uint256"], [EXECUTOR_THRESHOLD]).hex()
# sec.6 documents the hasRole answers only as true/false; their ABI bool encoding is the standard one.
RAW_TRUE = "0x" + "00" * 31 + "01"
RAW_FALSE = "0x" + "00" * 32

# OpenZeppelin TimelockController role ids are keccak256 of the role name (OZ source); derived here
# independently of the hex constants hard-coded inside the scorer.
TIMELOCK_ADMIN_ROLE = bytes(RealWeb3.keccak(text="TIMELOCK_ADMIN_ROLE"))
PROPOSER_ROLE = bytes(RealWeb3.keccak(text="PROPOSER_ROLE"))
EXECUTOR_ROLE = bytes(RealWeb3.keccak(text="EXECUTOR_ROLE"))
CANCELLER_ROLE = bytes(RealWeb3.keccak(text="CANCELLER_ROLE"))
HASROLE_SELECTOR = "0x" + RealWeb3.keccak(text="hasRole(bytes32,address)")[:4].hex()

# The score of the observed state since 2026-09-20 (signer sets resolved, see the constants above): the same value the Arbitrum
# Fluid scorer gives the identical structure, plus the cross-ecosystem fold. Until the next re-push the on-chain oracle still holds
# the earlier 40 / 100 / 70 / 100 / 67 (scored_targets_2026-09-18.md row 6, deploy/README.md read-back row 6).
SCORED = {
    "adminKeyScore": 65,
    "multisigScore": 55,
    "timelockScore": 55,
    "oracleAuthorityScore": 100,
    "crossExposureScore": 80,
    "compositeScore": 59,
}

# The notes are one entry per documented trace step, in the order FLUID NOTE walks them
# (sec.3 code, sec.4 owner then getAdmin, sec.5 admin code then shape, sec.6 roles, sec.7 code sizes),
# closed by the crossExposure note. Ten entries in the observed (timelock) state.
OBSERVED_NOTE_PREFIXES = [
    "eth_getCode(Liquidity, ",                                     # sec.3
    "Liquidity.owner() = ",                                        # sec.4
    "Liquidity.getAdmin() = ",                                     # sec.4
    "getAdmin() target code size = ",                              # sec.5
    "getAdmin() target is NOT a Gnosis Safe",                      # sec.5
    "hasRole(TIMELOCK_ADMIN_ROLE, Timelock itself) = ",            # sec.6
    "hasRole(PROPOSER_ROLE, ",                                     # sec.6
    "hasRole(CANCELLER_ROLE, proposer) = ",                        # sec.6
    "proposer code size = ",                                       # sec.7
    "crossExposureScore = 80: the freshly read proposer signer set",  # cross-ecosystem fold
]


def _addr(n):
    return RealWeb3.to_checksum_address("0x" + hex(n)[2:].zfill(40))


# --- SYNTHETIC FIXTURES: invented states, NOT documented observations -----------------------------
# Used only to reach branches the live chain does not exhibit. Nothing about them is sourced.
SYNTH_EOA = _addr(0xE0A)                 # a getAdmin() result with no bytecode
SYNTH_PLAIN_CONTRACT = _addr(0xC0DE)     # a getAdmin() result with code that is neither a Safe nor a Timelock
SYNTH_PLAIN_CONTRACT_CODE_BYTES = 1234
SYNTH_SAFE = _addr(0x5AFE)               # a getAdmin() result that answers getOwners()/getThreshold()
SYNTH_SAFE_CODE_BYTES = 999              # (deliberately NOT 171, which is the documented executor size)
SYNTH_SAFE_OWNERS = [_addr(i) for i in range(0x100, 0x105)]
SYNTH_SAFE_THRESHOLD = 3                 # 3-of-5: only the SHAPE is cited (Arbitrum note sec.7, see the Safe class)
SYNTH_PROPOSER_SAFE_OWNERS = [_addr(i) for i in range(0x200, 0x205)]
SYNTH_ADMIN_STAND_IN = _addr(0xAD)       # an external holder of TIMELOCK_ADMIN_ROLE
SYNTH_PROPOSER_STAND_IN = _addr(0xBB)    # a holder of PROPOSER_ROLE that is not the docs-cited proposer
SYNTH_EXECUTOR_STAND_IN = _addr(0xCC)    # a holder of EXECUTOR_ROLE that is not the docs-cited executor
SYNTH_OWNER = _addr(0x0A)                # a value owner() never returned live (it reverts, FLUID NOTE sec.4)
SYNTH_DELAY_TWO_DAYS = 2 * 86400         # a hypothetical live delay (documented one is 86400)
SYNTH_DELAYS_BELOW_A_DAY = (1, 3600, 86399)  # boundary probes around 0 and around the documented 86400


def _hand_composite(admin_key, multisig, timelock):
    """METHODOLOGY.md: floor(0.4a + 0.3m + 0.3t + 0.5), as an exact integer identity
    ((4a + 3m + 3t + 5) / 10, floored) so no float rounding is involved."""
    return (4 * admin_key + 3 * multisig + 3 * timelock + 5) // 10


class FakePlasma:
    """In-memory model of the chain state around Fluid's Liquidity. Every method
    below stands in for a name the scorer imported (or for `w3.eth.get_code`), and
    every read is appended to `calls` so tests can assert which reads were made."""

    def __init__(self):
        self.code_sizes = {}         # lowercased address -> bytes of deployed code
        self.address_getters = {}    # (lowercased address, function name) -> address
        self.owner_results = {}      # lowercased address -> value of Liquidity.owner()
        self.safes = {}              # lowercased address -> (owners, threshold)
        self.min_delays = {}         # lowercased address -> getMinDelay()
        self.avocados = {}           # lowercased address -> (requiredSigners(), signers()) of an Avocado multisig
        self.timelocks = set()       # lowercased addresses that answer hasRole()
        self.role_holders = {}       # (lowercased contract, role bytes) -> {lowercased accounts}
        self.forced_role_result = {}  # (lowercased contract) -> value returned for EVERY hasRole (e.g. None)
        self.forced_reads = {}       # (lowercased contract, role bytes, lowercased account) -> value for THAT ONE hasRole read
        self.slot_values = {}        # (lowercased address, slot) -> address
        self.abis = {}               # function name -> first ABI fragment (a one-entry list) the scorer passed
        self.calls = []              # ordered log of reads

    # -- names patched into the scorer's namespace ------------------------------------------------
    def read_address_getter(self, w3, address, function_name, retries=4):
        self.calls.append(("read_address_getter", address.lower(), function_name))
        return self.address_getters.get((address.lower(), function_name))

    def call_raw(self, w3, address, abi_fragment, function_name, *args, retries=4):
        a = address.lower()
        self.abis.setdefault(function_name, abi_fragment)
        if function_name == "owner":
            self.calls.append(("call_raw", a, "owner", retries))
            return self.owner_results.get(a)
        if function_name == "getMinDelay":
            self.calls.append(("call_raw", a, "getMinDelay", retries))
            return self.min_delays.get(a)
        if function_name == "requiredSigners":
            self.calls.append(("call_raw", a, "requiredSigners", retries))
            entry = self.avocados.get(a)
            return entry[0] if entry else None
        if function_name == "signers":
            self.calls.append(("call_raw", a, "signers", retries))
            entry = self.avocados.get(a)
            return list(entry[1]) if entry else None
        if function_name == "hasRole":
            role, account = args
            self.calls.append(("hasRole", a, bytes(role), account.lower()))
            single = (a, bytes(role), account.lower())
            if single in self.forced_reads:
                return self.forced_reads[single]
            if a in self.forced_role_result:
                return self.forced_role_result[a]
            if a not in self.timelocks:
                return None
            return account.lower() in self.role_holders.get((a, bytes(role)), set())
        raise AssertionError(f"unexpected call_raw({function_name!r}) from score_fluid_liquidity_plasma")

    def safe_owners_and_threshold(self, w3, address, retries=4):
        self.calls.append(("safe_owners_and_threshold", address.lower()))
        return self.safes.get(address.lower())

    def read_slot_as_address(self, w3, address, slot, retries=4):
        self.calls.append(("read_slot_as_address", address.lower(), slot))
        return self.slot_values.get((address.lower(), slot))

    # -- helpers ----------------------------------------------------------------------------------
    def calls_of(self, kind):
        return [c for c in self.calls if c[0] == kind]

    def has_role_queries(self):
        """{(contract, role, account)} of every hasRole read made."""
        return {(c[1], c[2], c[3]) for c in self.calls_of("hasRole")}


class FakeEth:
    def __init__(self, fake):
        self.fake = fake

    def get_code(self, address):
        self.fake.calls.append(("get_code", address.lower()))
        return b"\x00" * self.fake.code_sizes.get(address.lower(), 0)


class FakeW3:
    def __init__(self, fake):
        self.eth = FakeEth(fake)

    @staticmethod
    def to_checksum_address(addr):
        return RealWeb3.to_checksum_address(addr)


def _patch_helpers(test_case, fake):
    names = ["read_address_getter", "call_raw", "safe_owners_and_threshold", "read_slot_as_address"]
    originals = {n: getattr(scorers, n) for n in names}
    for n in names:
        setattr(scorers, n, getattr(fake, n))
    test_case.addCleanup(lambda: [setattr(scorers, n, originals[n]) for n in names])


def _wire_observed_state(fake):
    """The live state documented on 2026-09-18 (FLUID NOTE sec.3-7): Liquidity.owner() reverts,
    getAdmin() is a self-administered 24 h TimelockController, proposer and executor hold
    their roles, the canceller sits on the proposer only, neither role holder is Safe-shaped."""
    fake.code_sizes[LIQUIDITY.lower()] = LIQUIDITY_CODE_BYTES
    fake.code_sizes[TIMELOCK.lower()] = TIMELOCK_CODE_BYTES
    fake.code_sizes[PROPOSER.lower()] = PROPOSER_CODE_BYTES
    fake.code_sizes[EXECUTOR.lower()] = EXECUTOR_CODE_BYTES
    fake.address_getters[(LIQUIDITY.lower(), "getAdmin")] = TIMELOCK  # sec.4
    # sec.4: owner() reverts -> nothing registered in owner_results (call_raw yields None).
    # sec.5: getOwners()/getThreshold() revert on the Timelock; sec.7: on the proposer -> no safes entry.
    fake.min_delays[TIMELOCK.lower()] = MIN_DELAY  # sec.5
    fake.timelocks.add(TIMELOCK.lower())
    t = TIMELOCK.lower()
    fake.role_holders[(t, TIMELOCK_ADMIN_ROLE)] = {t}      # sec.6: held by the Timelock itself, not by 0x0
    fake.role_holders[(t, PROPOSER_ROLE)] = {PROPOSER.lower()}
    fake.role_holders[(t, EXECUTOR_ROLE)] = {EXECUTOR.lower()}
    fake.role_holders[(t, CANCELLER_ROLE)] = {PROPOSER.lower()}  # sec.6: canceller on proposer only
    # 2026-09-20 reads (data/fluid_liquidity_plasma_2026-09-20_signers.md): proposer = Avocado 6-of-12, executor = Safe 3-of-5.
    fake.avocados[PROPOSER.lower()] = (PROPOSER_REQUIRED_SIGNERS, list(PROPOSER_SIGNERS))
    fake.safes[EXECUTOR.lower()] = (list(EXECUTOR_OWNERS), EXECUTOR_THRESHOLD)
    # sec.4: the raw EIP-1967 admin slot reads the same address as getAdmin(); the scorer requires it to confirm the chain.
    fake.slot_values[(LIQUIDITY.lower(), EIP1967_ADMIN_SLOT)] = TIMELOCK


def _set_admin(fake, address):
    fake.address_getters[(LIQUIDITY.lower(), "getAdmin")] = address


class _FluidCase(unittest.TestCase):
    """Base: a fresh FakePlasma wired to the documented observed state, patched into the scorer."""

    def setUp(self):
        self.fake = FakePlasma()
        _wire_observed_state(self.fake)
        _patch_helpers(self, self.fake)
        self.w3 = FakeW3(self.fake)

    def score(self):
        return scorers.score_fluid_liquidity_plasma(self.w3)

    def notes_text(self, result):
        return "\n".join(result["notes"])

    def score_with(self, mutate):
        """Score a FRESH copy of the observed state after `mutate(fake)` changed it. Returns the result."""
        fake = FakePlasma()
        _wire_observed_state(fake)
        mutate(fake)
        _patch_helpers(self, fake)
        return scorers.score_fluid_liquidity_plasma(FakeW3(fake))


# ======================================================================================
# Happy path: the PUBLISHED score
# ======================================================================================
class TestFluidPublishedScore(_FluidCase):
    def test_reproduces_all_five_sub_scores_and_the_composite(self):
        result = self.score()
        for field, expected in SCORED.items():
            with self.subTest(field=field):
                self.assertEqual(result[field], expected)

    def test_composite_is_the_hand_derived_weighted_sum(self):
        # By hand: 0.4*65 + 0.3*55 + 0.3*55 = 26 + 16.5 + 16.5 = 59.0, +0.5 -> 59.5, floored 59 (oracle and cross excluded by
        # METHODOLOGY). Exact integer form: (4*65 + 3*55 + 3*55 + 5) // 10 = 595 // 10 = 59.
        self.assertEqual(_hand_composite(65, 55, 55), 59)
        self.assertEqual(self.score()["compositeScore"], 59)

    def test_target_is_the_address_the_deployments_md_row_documents(self):
        self.assertEqual(self.score()["target"], LIQUIDITY)  # FLUID NOTE sec.2

    def test_label_names_fluid_liquidity_on_plasma(self):
        self.assertEqual(self.score()["label"], "Fluid (Instadapp) Liquidity (Plasma)")

    def test_result_has_exactly_the_authority_score_fields_plus_notes(self):
        result = self.score()
        self.assertEqual(
            set(result),
            {"target", "label", "adminKeyScore", "multisigScore", "timelockScore",
             "oracleAuthorityScore", "crossExposureScore", "compositeScore", "notes"},
        )
        self.assertIsInstance(result["notes"], list)

    def test_notes_are_one_entry_per_documented_trace_step_in_the_documented_order(self):
        notes = self.score()["notes"]
        self.assertEqual(len(notes), len(OBSERVED_NOTE_PREFIXES))
        for index, prefix in enumerate(OBSERVED_NOTE_PREFIXES):
            with self.subTest(index=index):
                self.assertTrue(notes[index].startswith(prefix), notes[index][:80])

    def test_a_second_run_gets_its_own_notes_list_and_does_not_accumulate(self):
        # Replaces a former `assertEqual(score(), score())`, which passes for any deterministic
        # implementation. What a rerun can really break is shared state: a notes list reused across calls.
        first = self.score()["notes"]
        second = self.score()["notes"]
        self.assertIsNot(first, second)
        self.assertEqual(len(first), len(OBSERVED_NOTE_PREFIXES))
        self.assertEqual(len(second), len(OBSERVED_NOTE_PREFIXES))


class TestFluidPublishedNoteFacts(_FluidCase):
    """The value-bearing content of the notes: each asserted number or address is a documented
    observation (cited), independent of the scorer's connective wording."""

    def setUp(self):
        super().setUp()
        self.notes = self.notes_text(self.score())

    def test_records_the_observed_liquidity_bytecode_size(self):
        self.assertIn(f"eth_getCode(Liquidity, {LIQUIDITY}) = 4462 bytes", self.notes)  # FLUID NOTE sec.3

    def test_records_the_chain_id_as_9745_which_is_0x2611(self):
        # FLUID NOTE sec.1: eth_chainId -> 0x2611 (= 9745), Plasma mainnet. hex() is independent arithmetic.
        self.assertEqual(hex(9745), "0x2611")
        self.assertEqual(scorers.PLASMA_CHAIN_ID, 9745)
        self.assertIn("chain 9745, eth_chainId=0x2611", self.notes)

    def test_records_owner_reverting_as_none(self):
        # FLUID NOTE sec.4: owner() reverts (custom infinite proxy, not Ownable).
        self.assertIn("Liquidity.owner() = None", self.notes)

    def test_records_the_getadmin_address(self):
        self.assertIn(f"Liquidity.getAdmin() = {TIMELOCK}", self.notes)  # FLUID NOTE sec.4

    def test_records_the_timelock_as_a_real_contract_of_9741_bytes(self):
        self.assertIn("getAdmin() target code size = 9741 bytes (a real contract, not a bare EOA)", self.notes)  # sec.5

    def test_records_not_a_safe_but_a_timelock_with_the_24h_delay(self):
        self.assertIn("is NOT a Gnosis Safe", self.notes)  # sec.5: getOwners()/getThreshold() revert
        self.assertIn("getMinDelay() = 86400s (24h)", self.notes)  # sec.5: 0x15180

    def test_records_the_self_administered_role_reads(self):
        # FLUID NOTE sec.6.
        self.assertIn("hasRole(TIMELOCK_ADMIN_ROLE, Timelock itself) = True, hasRole(TIMELOCK_ADMIN_ROLE, 0x0) = False", self.notes)

    def test_records_the_docs_cited_proposer_and_executor_as_confirmed_live(self):
        self.assertIn(f"hasRole(PROPOSER_ROLE, {PROPOSER}) = True, hasRole(EXECUTOR_ROLE, {EXECUTOR}) = True", self.notes)

    def test_records_canceller_on_proposer_only(self):
        self.assertIn("hasRole(CANCELLER_ROLE, proposer) = True, hasRole(CANCELLER_ROLE, executor) = False", self.notes)

    def test_records_the_resolved_proposer_and_executor_signer_sets(self):
        self.assertIn("proposer code size = 327 bytes, executor code size = 171 bytes", self.notes)  # sec.7
        self.assertIn("proposer getOwners()/getThreshold() = NOT Safe-shaped (both revert)", self.notes)
        self.assertIn("proposer is an Avocado multisig: requiredSigners() = 6, signers() = 12; executor is a 3-of-5 Safe", self.notes)
        self.assertNotIn("NOT resolved this run", self.notes)

    def test_records_the_cross_ecosystem_fold(self):
        self.assertIn("crossExposureScore = 80: the freshly read proposer signer set is identical, as a set, to the committee", self.notes)
        self.assertNotIn("not computed", self.notes)


class TestFluidPublishedNoteWording(_FluidCase):
    """CHANGE DETECTORS for the disclosure clauses at the end of each published note. The wording is the
    scorer's own (not independent evidence); each clause states a provenance or a limit that the
    FLUID NOTE section named in the test backs, and the tests stop one from being deleted silently."""

    def setUp(self):
        super().setUp()
        self.notes = self.notes_text(self.score())

    def test_first_note_says_this_is_a_genuine_separate_plasma_deployment(self):
        # FLUID NOTE sec.2-3: "confirmed below to be a real, separately-deployed contract on Plasma".
        self.assertIn("genuine separate Plasma deployment, not a docs artifact", self.notes)

    def test_getadmin_note_claims_the_storage_slot_cross_check(self):
        # FLUID NOTE sec.4 documents that cross-check as done by hand. The function itself never performs it
        # (see the expectedFailure in TestFluidCrossChecks), so this pins the claimed wording only.
        self.assertIn("cross-checked live via a raw eth_getStorageAt read at that slot", self.notes)

    def test_role_note_states_the_self_administered_conclusion(self):
        # FLUID NOTE sec.6: "Self-administered (no external super-admin escape hatch)".
        self.assertIn("self-administered, no separate external super-admin escape hatch found", self.notes)

    def test_proposer_executor_note_discloses_the_docs_provenance_of_the_addresses(self):
        # FLUID NOTE sec.7, last paragraph: sourced from deployments.md, then confirmed live via hasRole().
        self.assertIn("(docs-cited addresses, independently confirmed live)", self.notes)

    def test_code_size_note_says_both_are_real_contracts(self):
        # FLUID NOTE sec.7: "Both are contracts, not bare EOAs."
        self.assertIn("(both real contracts, not bare EOAs)", self.notes)


# ======================================================================================
# The read plan: which reads the scorer makes, and with which constants
# ======================================================================================
class TestFluidReadPlan(_FluidCase):
    """These pin the exact reads the current implementation makes. That mirrors its structure (a harmless
    refactor of the order would need the tests updated), but every selector and every address checked
    here is independent: keccak256 or a documented constant, not read back from the scorer."""

    def test_owner_is_read_once_on_liquidity_with_a_single_attempt(self):
        # An expected revert is not retried (each retry sleeps in the real call_raw).
        self.score()
        owner_calls = [c for c in self.fake.calls_of("call_raw") if c[2] == "owner"]
        self.assertEqual(owner_calls, [("call_raw", LIQUIDITY.lower(), "owner", 1)])

    def test_admin_is_read_through_getadmin_not_owner(self):
        self.score()
        self.assertEqual(self.fake.calls_of("read_address_getter"), [("read_address_getter", LIQUIDITY.lower(), "getAdmin")])

    def test_timelock_role_reads_cover_the_four_oz_roles_with_docs_addresses(self):
        self.score()
        t = TIMELOCK.lower()
        self.assertEqual(
            self.fake.has_role_queries(),
            {
                (t, TIMELOCK_ADMIN_ROLE, t),                 # self-administered?
                (t, TIMELOCK_ADMIN_ROLE, ZERO.lower()),      # no zero-address super-admin?
                (t, PROPOSER_ROLE, PROPOSER.lower()),        # docs-cited proposer
                (t, EXECUTOR_ROLE, EXECUTOR.lower()),        # docs-cited executor
                (t, CANCELLER_ROLE, PROPOSER.lower()),       # emergency-bypass check
                (t, CANCELLER_ROLE, EXECUTOR.lower()),
            },
        )

    def test_admin_then_proposer_are_probed_for_safe_shape(self):
        # Docstring: getOwners()/getThreshold() "both revert on it" (the admin) and "revert on the
        # proposer" (FLUID NOTE sec.5 and sec.7).
        self.score()
        safe_probes = [c[1] for c in self.fake.calls_of("safe_owners_and_threshold")]
        self.assertEqual(safe_probes[:2], [TIMELOCK.lower(), PROPOSER.lower()])

    # Was an expectedFailure until 2026-09-20 (finding, now fixed). FLUID NOTE sec.7 (and the scorer's docstring) say "Neither [proposer nor
    # executor] is Safe-shaped", but the only evidence given is that getOwners()/getThreshold() "revert on the
    # proposer": the executor is never probed (the function calls safe_owners_and_threshold for the admin and
    # the proposer only). And chains/arbitrum-ecosystem/data/scored_targets_2026-09-19-maintenance.md sec.7
    # documents that the SAME address, 0x196Ed45e..., "is a Safe v1.4.1 (3-of-5)" on Arbitrum (the Timelock's
    # constructor args are identical on every chain, FLUID NOTE sec.5). So the executor's Safe shape on Plasma
    # is an unprobed, documented-plausible fact behind the "signer strength UNRESOLVED" disclosure.
    # Fixed 2026-09-20.
    def test_the_executor_is_probed_for_safe_shape_too(self):
        self.score()
        safe_probes = [c[1] for c in self.fake.calls_of("safe_owners_and_threshold")]
        self.assertIn(EXECUTOR.lower(), safe_probes)

    def test_an_executor_that_answers_as_a_safe_is_reported_as_one_while_the_proposer_is_not(self):
        self.fake.safes[EXECUTOR.lower()] = (SYNTH_SAFE_OWNERS, SYNTH_SAFE_THRESHOLD)
        text = self.notes_text(self.score())
        self.assertIn(
            "proposer getOwners()/getThreshold() = NOT Safe-shaped (both revert), "
            "executor getOwners()/getThreshold() = a real Gnosis Safe -- ", text)

    def test_an_executor_that_does_not_answer_as_a_safe_is_reported_as_not_safe_shaped(self):
        del self.fake.safes[EXECUTOR.lower()]
        text = self.notes_text(self.score())
        self.assertIn("executor getOwners()/getThreshold() = NOT Safe-shaped (both revert) -- ", text)

    def test_bytecode_is_fetched_for_liquidity_timelock_proposer_and_executor(self):
        self.score()
        fetched = [c[1] for c in self.fake.calls_of("get_code")]
        self.assertEqual(fetched, [LIQUIDITY.lower(), TIMELOCK.lower(), PROPOSER.lower(), EXECUTOR.lower()])

    def test_getmindelay_abi_resolves_to_the_documented_selector(self):
        self.score()
        selector = function_abi_to_4byte_selector(self.fake.abis["getMinDelay"][0]).hex()
        self.assertEqual(selector, SEL_GETMINDELAY[2:])  # FLUID NOTE sec.5 (# getMinDelay())

    def test_owner_abi_resolves_to_the_documented_selector(self):
        self.score()
        self.assertEqual(function_abi_to_4byte_selector(self.fake.abis["owner"][0]).hex(), SEL_OWNER[2:])  # FLUID NOTE sec.4

    def test_hasrole_abi_resolves_to_the_oz_accesscontrol_selector(self):
        self.score()
        expected = RealWeb3.keccak(text="hasRole(bytes32,address)")[:4].hex()
        self.assertEqual(function_abi_to_4byte_selector(self.fake.abis["hasRole"][0]).hex(), expected)

    def test_the_getter_name_the_scorer_passes_encodes_to_the_documented_getadmin_selector(self):
        # Docstring: getAdmin() is selector 0x6e9960c3, "independently re-derived via keccak256". The scorer
        # never builds that ABI itself (the read helper does), so take the function NAME the scorer really
        # passed and encode it with the helper's own ABI builder; the replay class below also runs the
        # helper for real end to end.
        self.score()
        (call,) = self.fake.calls_of("read_address_getter")
        name = call[2]
        abi = web3_utils._ADDRESS_GETTER_ABI(name)
        self.assertEqual(function_abi_to_4byte_selector(abi[0]).hex(), SEL_GETADMIN[2:])
        self.assertEqual(RealWeb3.keccak(text=f"{name}()")[:4].hex(), SEL_GETADMIN[2:])


class TestFixtureConstantsAreSound(unittest.TestCase):
    """Guards the FIXTURE, not the scorer: these never call `score_fluid_liquidity_plasma`. The constants
    the other tests are built on (documented raw payloads, selectors, delay, slot) are re-derived here from
    their definitions, so a typo in a fixture cannot silently turn a test into a tautology."""

    def test_documented_addresses_are_valid_checksums(self):
        for a in (LIQUIDITY, TIMELOCK, PROPOSER, EXECUTOR):
            with self.subTest(address=a):
                self.assertTrue(RealWeb3.is_checksum_address(a))

    def test_min_delay_0x15180_is_exactly_24_hours(self):
        self.assertEqual(0x15180, MIN_DELAY)
        self.assertEqual(MIN_DELAY, 24 * 3600)

    def test_custom_error_payload_0xc351_is_50001(self):
        self.assertEqual(0xC351, 50001)  # docstring: "payload 0xc351 (50001)"
        self.assertEqual(RAW_OWNER_REVERT_DATA[:10], "0xc44f8d3b")
        self.assertEqual(int(RAW_OWNER_REVERT_DATA[10:], 16), 50001)

    def test_eip1967_admin_slot_is_keccak_eip1967_proxy_admin_minus_one(self):
        derived = "0x" + format(int.from_bytes(RealWeb3.keccak(text="eip1967.proxy.admin"), "big") - 1, "064x")
        self.assertEqual(derived, EIP1967_ADMIN_SLOT)  # FLUID NOTE sec.4

    def test_documented_raw_answers_decode_to_the_fixture_values(self):
        self.assertEqual(RealWeb3.to_checksum_address("0x" + RAW_GETADMIN_RESULT[-40:]), TIMELOCK)
        self.assertEqual(int(RAW_GETMINDELAY_RESULT, 16), MIN_DELAY)

    def test_documented_selectors_are_the_keccak_of_their_signatures(self):
        for signature, documented in (
            ("owner()", SEL_OWNER),
            ("getAdmin()", SEL_GETADMIN),
            ("getOwners()", SEL_GETOWNERS),
            ("getThreshold()", SEL_GETTHRESHOLD),
            ("getMinDelay()", SEL_GETMINDELAY),
        ):
            with self.subTest(signature=signature):
                self.assertEqual("0x" + RealWeb3.keccak(text=signature)[:4].hex(), documented)


# ======================================================================================
# Below the fakes: the documented raw JSON-RPC payloads through the REAL read helpers
# ======================================================================================
class RawReplayProvider(BaseProvider):
    """An offline JSON-RPC provider that answers ONLY from raw payloads FLUID NOTE documents. Anything
    else is answered with a revert and recorded in `unexpected`, so a test can prove the scorer asked
    for nothing undocumented."""

    def __init__(self):
        super().__init__()
        self.codes = {}          # lowercased address -> number of code bytes (FLUID NOTE sec.3, 5, 7)
        self.eth_calls = {}      # (lowercased to, lowercased data) -> ("result", hex) | ("revert", error data or None)
        self.slots = {}          # (lowercased address, slot) -> hex value
        self.requests = []       # ("eth_call", to, data) | ("eth_getCode", address, None), every request, retries included
        self.unexpected = []

    @staticmethod
    def _ok(result):
        return {"jsonrpc": "2.0", "id": 1, "result": result}

    @staticmethod
    def _revert(data=None):
        error = {"code": 3, "message": "execution reverted"}
        if data is not None:
            error["data"] = data
        return {"jsonrpc": "2.0", "id": 1, "error": error}

    def make_request(self, method, params):
        if method == "eth_chainId":
            return self._ok(hex(9745))  # FLUID NOTE sec.1: 0x2611
        if method == "eth_getCode":
            address = params[0].lower()
            self.requests.append(("eth_getCode", address, None))
            if address not in self.codes:
                self.unexpected.append((method, address))
                return self._ok("0x")
            return self._ok("0x" + "60" * self.codes[address])
        if method == "eth_getStorageAt":
            address = params[0].lower()
            slot = params[1].lower()
            self.requests.append(("eth_getStorageAt", address, slot))
            value = self.slots.get((address, slot))
            if value is None:
                self.unexpected.append((method, address, slot))
                return self._ok("0x" + "00" * 32)
            return self._ok(value)
        if method == "eth_call":
            to, data = params[0]["to"].lower(), params[0]["data"].lower()
            self.requests.append(("eth_call", to, data))
            answer = self.eth_calls.get((to, data))
            if answer is None:
                self.unexpected.append((method, to, data))
                return self._revert()
            kind, payload = answer
            return self._ok(payload) if kind == "result" else self._revert(payload)
        self.unexpected.append((method, params))
        return self._revert()


def _has_role_call(role, account):
    """The calldata a correct hasRole(bytes32,address) request carries: selector, role, address padded to 32."""
    return HASROLE_SELECTOR + role.hex() + "00" * 12 + account[2:].lower()


def _documented_observation():
    """FLUID NOTE sec.3-7 as raw answers. hasRole answers are documented as true/false only (sec.6)."""
    p = RawReplayProvider()
    lq, tl, pr, ex = LIQUIDITY.lower(), TIMELOCK.lower(), PROPOSER.lower(), EXECUTOR.lower()
    p.codes = {lq: LIQUIDITY_CODE_BYTES, tl: TIMELOCK_CODE_BYTES, pr: PROPOSER_CODE_BYTES, ex: EXECUTOR_CODE_BYTES}
    p.eth_calls = {
        (lq, SEL_OWNER): ("revert", RAW_OWNER_REVERT_DATA),                # sec.4
        (lq, SEL_GETADMIN): ("result", RAW_GETADMIN_RESULT),               # sec.4
        (tl, SEL_GETOWNERS): ("revert", None),                             # sec.5 "execution reverted"
        (tl, SEL_GETTHRESHOLD): ("revert", None),                          # sec.5
        (tl, SEL_GETMINDELAY): ("result", RAW_GETMINDELAY_RESULT),         # sec.5
        (pr, SEL_GETOWNERS): ("revert", None),                             # sec.7 "revert on the proposer"
        (pr, SEL_GETTHRESHOLD): ("revert", None),                          # sec.7
        # 2026-09-20 note: the proposer is an Avocado multisig, the executor a Safe 3-of-5
        (pr, SEL_REQUIRED_SIGNERS): ("result", RAW_REQUIRED_SIGNERS_RESULT),
        (pr, SEL_SIGNERS): ("result", RAW_SIGNERS_RESULT),
        (ex, SEL_GETOWNERS): ("result", RAW_EXECUTOR_OWNERS_RESULT),
        (ex, SEL_GETTHRESHOLD): ("result", RAW_EXECUTOR_THRESHOLD_RESULT),
        (tl, _has_role_call(TIMELOCK_ADMIN_ROLE, TIMELOCK)): ("result", RAW_TRUE),    # sec.6
        (tl, _has_role_call(TIMELOCK_ADMIN_ROLE, ZERO)): ("result", RAW_FALSE),       # sec.6
        (tl, _has_role_call(PROPOSER_ROLE, PROPOSER)): ("result", RAW_TRUE),          # sec.6
        (tl, _has_role_call(EXECUTOR_ROLE, EXECUTOR)): ("result", RAW_TRUE),          # sec.6
        (tl, _has_role_call(CANCELLER_ROLE, PROPOSER)): ("result", RAW_TRUE),         # sec.6
        (tl, _has_role_call(CANCELLER_ROLE, EXECUTOR)): ("result", RAW_FALSE),        # sec.6
    }
    # EIP-1967 admin slot cross-check (sec.4)
    p.slots[(lq, EIP1967_ADMIN_SLOT.lower())] = RAW_GETADMIN_RESULT
    return p


class TestFluidReplayOfDocumentedRawPayloads(unittest.TestCase):
    """No scorer name is patched here: the real `call_raw`, `read_address_getter`, `safe_owners_and_threshold`
    and `_has_role` encode real requests and decode real answers through a real `Web3`, fed only the raw
    payloads FLUID NOTE records. Reproducing the published score from them is independent of `FakePlasma`."""

    def setUp(self):
        self.provider = _documented_observation()
        # The real helpers sleep between retries of an expected revert; that would only slow the test down.
        sleeper = mock.patch.object(web3_utils.time, "sleep")
        sleeper.start()
        self.addCleanup(sleeper.stop)
        # The Safe authority gate (2026-09-21) adds module and singleton reads that FLUID NOTE never recorded; this replay is about the
        # score's own reads, so the gate is stubbed to "clean" here and tested on its own in test_web3_utils.py.
        gate = mock.patch.object(web3_utils, "_authority_gate", return_value=([], []))
        gate.start()
        self.addCleanup(gate.stop)
        self.result = scorers.score_fluid_liquidity_plasma(RealWeb3(self.provider))

    def test_reproduces_the_score_from_the_raw_answers(self):
        for field, expected in SCORED.items():
            with self.subTest(field=field):
                self.assertEqual(self.result[field], expected)

    def test_asked_for_nothing_undocumented(self):
        self.assertEqual(self.provider.unexpected, [])

    def test_made_every_documented_read_with_the_documented_calldata(self):
        made = {(r[0], r[1], r[2]) for r in self.provider.requests}
        lq, tl, pr, ex = LIQUIDITY.lower(), TIMELOCK.lower(), PROPOSER.lower(), EXECUTOR.lower()
        required = {
            ("eth_call", lq, SEL_OWNER),
            ("eth_call", lq, SEL_GETADMIN),
            ("eth_call", tl, SEL_GETOWNERS),
            ("eth_call", tl, SEL_GETMINDELAY),
            ("eth_call", pr, SEL_GETOWNERS),
            ("eth_call", pr, SEL_REQUIRED_SIGNERS),
            ("eth_call", pr, SEL_SIGNERS),
            ("eth_call", ex, SEL_GETOWNERS),
            ("eth_call", ex, SEL_GETTHRESHOLD),
        } | {("eth_call", tl, data) for (to, data) in self.provider.eth_calls if to == tl and data.startswith(HASROLE_SELECTOR)}
        self.assertEqual(len(required), 9 + 6)
        self.assertLessEqual(required, made)
        for address in (LIQUIDITY, TIMELOCK, PROPOSER, EXECUTOR):
            self.assertIn(("eth_getCode", address.lower(), None), made)

    def test_owner_is_asked_once_because_its_revert_is_expected(self):
        owner_requests = [r for r in self.provider.requests if r[:3] == ("eth_call", LIQUIDITY.lower(), SEL_OWNER)]
        self.assertEqual(len(owner_requests), 1)

    def test_decodes_the_documented_answers_into_the_notes(self):
        text = "\n".join(self.result["notes"])
        self.assertIn(f"Liquidity.getAdmin() = {TIMELOCK}", text)
        self.assertIn("getMinDelay() = 86400s (24h)", text)
        self.assertIn("Liquidity.owner() = None", text)
        self.assertIn("hasRole(CANCELLER_ROLE, proposer) = True, hasRole(CANCELLER_ROLE, executor) = False", text)


# ======================================================================================
# Branches on what getAdmin() resolves to
# ======================================================================================
class TestFluidAdminIsUnresolved(_FluidCase):
    """getAdmin() reverted or every retry hit a transient RPC failure -> read_address_getter is None."""

    def setUp(self):
        super().setUp()
        del self.fake.address_getters[(LIQUIDITY.lower(), "getAdmin")]
        self.result = self.score()

    def test_admin_key_and_timelock_degrade_to_the_unresolved_placeholder(self):
        # METHODOLOGY: an unresolved contract scores 20 "unknown, not assumed safe"; no delay found -> 0.
        self.assertEqual(self.result["adminKeyScore"], 20)
        self.assertEqual(self.result["timelockScore"], 0)

    def test_the_slot_cross_check_is_reported_as_not_attempted_when_getadmin_is_unread(self):
        text = self.notes_text(self.result)
        self.assertIn("which was not attempted because getAdmin() itself was unread (cross-check NOT completed)", text)
        self.assertNotIn("could not be read this run", text)
        self.assertNotIn("identical address", text)
        self.assertEqual(self.fake.calls_of("read_slot_as_address"), [])

    def test_notes_say_unresolved_contract_shape(self):
        self.assertIn("neither a Gnosis Safe nor a TimelockController this run -- unresolved contract shape", self.notes_text(self.result))

    def test_no_further_read_is_attempted_on_a_none_admin(self):
        # Only Liquidity's own bytecode is fetched; no Safe probe, no getMinDelay, no hasRole.
        self.assertEqual([c[1] for c in self.fake.calls_of("get_code")], [LIQUIDITY.lower()])
        self.assertEqual(self.fake.calls_of("safe_owners_and_threshold"), [])
        self.assertEqual(self.fake.calls_of("hasRole"), [])
        self.assertEqual([c for c in self.fake.calls_of("call_raw") if c[2] == "getMinDelay"], [])

    def test_no_timelock_role_notes_are_emitted(self):
        self.assertNotIn("hasRole(", self.notes_text(self.result))

    def test_the_reported_code_size_is_zero_because_no_admin_address_was_read(self):
        # No address came back from getAdmin(), so nothing is fetched for it and the size reads 0 bytes.
        self.assertIn("getAdmin() target code size = 0 bytes", self.notes_text(self.result))

    # DELIBERATE expectedFailure (note only, no score effect). The note printed for an admin that could NOT
    # be read ("Liquidity.getAdmin() = None") is "getAdmin() target code size = 0 bytes (NO CODE -- a bare
    # EOA)": with no address there is no target to call an EOA, and the very next shape note says "unresolved
    # contract shape". METHODOLOGY.md, adminKeyScore: an unresolved authority is "an explicit 'unknown, not
    # assumed safe' placeholder, never silently treated as either extreme" (a bare EOA being the near-worst
    # extreme, and confusing the two being the class of bug data/correction_2026-09-16-uniswap-bridge-alias.md
    # describes).
    # Fixed 2026-09-20.
    def test_an_unread_admin_is_not_described_as_a_bare_eoa(self):
        self.assertNotIn("a bare EOA", self.notes_text(self.result))

    def test_composite_of_the_unresolved_20_0_0_is_8_by_hand(self):
        # Fixed 2026-09-20 - multisig now 0 for unresolved admin
        # By hand: 0.4*20 + 0.3*0 + 0.3*0 = 8 + 0 + 0 = 8 (exact-integer form (80+0+0+5)//10 = 8).
        # The sub-scores are the LITERALS below, not the function's own return values.
        self.assertEqual(_hand_composite(20, 0, 0), 8)
        self.assertEqual(self.result["compositeScore"], 8)

    # Fixed 2026-09-20 - multisig now 0 for unresolved admin
    def test_unresolved_admin_multisig_score_is_0(self):
        self.assertEqual(self.result["multisigScore"], 0)

    # Was an expectedFailure until 2026-09-20 (finding, now fixed). Documented floor for an unresolved authority in this same file:
    # Aquila (line ~281), Telos and Yuzu's not-a-timelock branch all return (admin, multisig, timelock)
    # = (20, 0, 0), and test_plasma_ecosystem_scorers.py asserts exactly (20, 0, 0) for them; METHODOLOGY:
    # multisig is "0 if no Safe/multisig layer exists"; `100` means "not applicable (root is a real,
    # active DAO)". Before this fix score_fluid_liquidity_plasma set `multisig = 100` unconditionally (its own
    # comment: "the root is a TimelockController"), so an unread getAdmin() scored (20, 100, 0), composite 38
    # (by hand: (4*20 + 3*100 + 5)//10 = 38) instead of the floor's 8 -- a transient RPC failure inflated
    # the score instead of degrading it. It now scores (20, 0, 0), composite 8.
    # Fixed 2026-09-20.
    def test_unresolved_admin_scores_the_documented_floor_20_0_0_composite_8(self):
        r = self.result
        self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["timelockScore"]), (20, 0, 0))
        self.assertEqual(r["compositeScore"], _hand_composite(20, 0, 0))
        self.assertEqual(_hand_composite(20, 0, 0), 8)


class TestFluidAdminIsABareEoa(_FluidCase):
    """getAdmin() resolves to an address that has no bytecode (SYNTHETIC: SYNTH_EOA, the live admin is a
    contract)."""

    def setUp(self):
        super().setUp()
        self.eoa = SYNTH_EOA
        _set_admin(self.fake, self.eoa)
        self.result = self.score()

    def test_notes_call_it_a_bare_eoa(self):
        self.assertIn("getAdmin() target code size = 0 bytes (NO CODE -- a bare EOA)", self.notes_text(self.result))

    def test_no_delay_found_scores_timelock_zero(self):
        self.assertEqual(self.result["timelockScore"], 0)

    def test_timelock_role_reads_are_skipped_for_a_non_timelock_admin(self):
        self.assertEqual(self.fake.calls_of("hasRole"), [])
        self.assertNotIn("hasRole(", self.notes_text(self.result))

    def test_the_eoa_is_probed_for_safe_shape_and_for_a_delay_before_giving_up(self):
        self.assertEqual([c[1] for c in self.fake.calls_of("safe_owners_and_threshold")], [self.eoa.lower()])
        self.assertIn(("call_raw", self.eoa.lower(), "getMinDelay", 4), self.fake.calls)

    # Fixed 2026-09-20 - bare EOA now properly classified with adminKey 5 and multisig 0
    def test_bare_eoa_sub_scores_are_5_0_0_composite_2(self):
        r = self.result
        self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["timelockScore"]), (5, 0, 0))
        self.assertEqual(r["compositeScore"], 2)

    # Was an expectedFailure until 2026-09-20 (finding, now fixed). METHODOLOGY.md ("What each dimension actually reads", adminKeyScore):
    # "a bare EOA scores 2-10", 20 being reserved for an unresolved CONTRACT. The scorer's own note
    # above says "NO CODE -- a bare EOA" yet scores adminKey 20.
    # Fixed 2026-09-20.
    def test_bare_eoa_admin_key_is_in_the_documented_2_to_10_band(self):
        self.assertTrue(2 <= self.result["adminKeyScore"] <= 10, self.result["adminKeyScore"])

    # Was an expectedFailure until 2026-09-20 (finding, now fixed). METHODOLOGY.md, multisigScore: "Score is 0 if no Safe/multisig layer
    # exists (the root is a bare EOA or a plain contract)". The scorer returns 100 here.
    # Fixed 2026-09-20.
    def test_bare_eoa_admin_has_multisig_score_zero(self):
        self.assertEqual(self.result["multisigScore"], 0)


class TestFluidAdminIsAPlainContract(_FluidCase):
    """getAdmin() resolves to a contract that is neither a Safe nor a TimelockController (SYNTHETIC:
    SYNTH_PLAIN_CONTRACT and its 1234-byte code size are invented)."""

    def setUp(self):
        super().setUp()
        self.plain = SYNTH_PLAIN_CONTRACT
        _set_admin(self.fake, self.plain)
        self.fake.code_sizes[self.plain.lower()] = SYNTH_PLAIN_CONTRACT_CODE_BYTES
        self.result = self.score()

    def test_notes_say_a_real_contract_of_unresolved_shape(self):
        text = self.notes_text(self.result)
        self.assertIn(f"getAdmin() target code size = {SYNTH_PLAIN_CONTRACT_CODE_BYTES} bytes (a real contract, not a bare EOA)", text)
        self.assertIn("neither a Gnosis Safe nor a TimelockController this run", text)

    def test_admin_key_is_the_unresolved_contract_placeholder_20(self):
        self.assertEqual(self.result["adminKeyScore"], 20)  # METHODOLOGY: unresolved contract = 20

    def test_no_delay_found_scores_timelock_zero(self):
        self.assertEqual(self.result["timelockScore"], 0)

    def test_role_reads_and_proposer_bytecode_are_skipped(self):
        self.assertEqual(self.fake.calls_of("hasRole"), [])
        self.assertNotIn(PROPOSER.lower(), [c[1] for c in self.fake.calls_of("get_code")])

    # Fixed 2026-09-20 - plain contract now properly classified with multisig 0
    def test_plain_contract_multisig_score_is_0_composite_8(self):
        self.assertEqual(self.result["multisigScore"], 0)
        self.assertEqual(self.result["compositeScore"], 8)

    # Was an expectedFailure until 2026-09-20 (finding, now fixed). METHODOLOGY.md, multisigScore: 0 when "the root is a bare EOA or a
    # plain contract"; Yuzu's own not-a-timelock branch returns (20, 0, 0). Fluid returns multisig 100.
    # Fixed 2026-09-20.
    def test_plain_contract_admin_has_multisig_score_zero(self):
        self.assertEqual(self.result["multisigScore"], 0)


class TestFluidAdminIsAGnosisSafe(_FluidCase):
    """getAdmin() resolves to a Safe (SYNTHETIC: not the observed state; SYNTH_SAFE and its owners are
    invented). 3-of-5 is the real shape of the Fluid executor Safe seen on Arbitrum (chains/
    arbitrum-ecosystem/data/scored_targets_2026-09-19-maintenance.md sec.7: "0x196Ed45e... is a Safe v1.4.1
    (3-of-5)"), used here only as a realistic shape, not as a claim about Plasma."""

    def setUp(self):
        super().setUp()
        self.safe_addr = SYNTH_SAFE
        self.owners = SYNTH_SAFE_OWNERS
        _set_admin(self.fake, self.safe_addr)
        self.fake.code_sizes[self.safe_addr.lower()] = SYNTH_SAFE_CODE_BYTES
        self.fake.safes[self.safe_addr.lower()] = (self.owners, SYNTH_SAFE_THRESHOLD)
        self.result = self.score()

    def test_notes_report_the_safe_threshold_and_owner_count(self):
        self.assertIn("getAdmin() target resolves as a Gnosis Safe: 3-of-5", self.notes_text(self.result))

    def test_a_safe_admin_that_has_no_delay_is_not_described_as_a_timelock(self):
        # (Was `test_safe_takes_priority_over_the_timelock_note`, which overclaimed: this fixture has no
        # getMinDelay, so it cannot tell which branch has priority. The precedence is tested in
        # TestFluidAdminAnswersAsBothSafeAndTimelock.)
        self.assertNotIn("live OpenZeppelin TimelockController", self.notes_text(self.result))

    def test_no_delay_found_scores_timelock_zero(self):
        self.assertEqual(self.result["timelockScore"], 0)

    def test_timelock_role_reads_are_skipped_for_a_safe_admin(self):
        self.assertEqual(self.fake.calls_of("hasRole"), [])
        self.assertNotIn("hasRole(", self.notes_text(self.result))

    # Fixed 2026-09-20: a resolved Safe root is classified, not assumed. adminKey is the table of the
    # sibling scorer in this file (score_validator_set_authority: 3-of-N -> 50), multisig is METHODOLOGY's
    # min(100, 3*15 + 2*5) = 55 for 3-of-5, timelock 0 (no delay found). Composite by hand: 0.4*50 + 0.3*55 + 0.3*0 + 0.5
    # = 20 + 16.5 + 0 + 0.5 = 37.
    def test_a_resolved_3_of_5_safe_admin_scores_50_55_0_composite_37(self):
        r = self.result
        self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["timelockScore"]), (50, 55, 0))
        self.assertEqual(r["compositeScore"], 37)

    # Was an expectedFailure until 2026-09-20 (finding, now fixed). METHODOLOGY.md, adminKeyScore: a resolved root is "a Gnosis Safe or bespoke
    # multisig (scored better...)" than the 20 that is "an explicit 'unknown, not assumed safe' placeholder"
    # for a contract whose controller wasn't traced. The sibling scorer in this same file scores a 3-of-N Safe
    # root at adminKey 50 (Aquila, `admin_key = 50 if threshold == 3`; test_plasma_ecosystem_scorers.py line
    # ~139 pins 50 for 3-of-4). Fluid gives a resolved 3-of-5 Safe the same 20 as an unresolved contract.
    # Fixed 2026-09-20.
    def test_a_resolved_safe_admin_scores_better_than_the_unresolved_placeholder(self):
        self.assertGreater(self.result["adminKeyScore"], 20)

    # Was an expectedFailure until 2026-09-20 (finding, now fixed). METHODOLOGY.md, multisigScore: "The general shape used across most
    # targets: min(100, threshold*15 + max(0, ownerCount - threshold)*5)". By hand for 3-of-5:
    # 3*15 + 2*5 = 55 (the Arbitrum note above quotes the same "3-of-5 -> 55"). Aquila's Safe branch in
    # this same file uses that formula (3-of-4 -> 50). Fluid returns 100 whatever the Safe looks like.
    # Fixed 2026-09-20.
    def test_safe_admin_multisig_score_follows_the_threshold_formula(self):
        self.assertEqual(self.result["multisigScore"], min(100, 3 * 15 + max(0, 5 - 3) * 5))
        self.assertEqual(self.result["multisigScore"], 55)


class TestFluidAdminAnswersAsBothSafeAndTimelock(_FluidCase):
    """HYPOTHETICAL and SYNTHETIC: the documented Timelock address (which really answers getMinDelay() and
    the hasRole reads) is made to ALSO answer getOwners()/getThreshold() as a 3-of-5 Safe. No such contract
    was observed; it is the only way to tell which of the two shape notes has priority."""

    def setUp(self):
        super().setUp()
        self.fake.safes[TIMELOCK.lower()] = (SYNTH_SAFE_OWNERS, SYNTH_SAFE_THRESHOLD)
        self.result = self.score()
        self.text = self.notes_text(self.result)

    def test_the_safe_note_takes_priority_over_the_timelock_note(self):
        # Characterization of the current if-Safe / elif-Timelock order (the scorer's own structure; the
        # documentation only ever describes each shape separately).
        self.assertIn("getAdmin() target resolves as a Gnosis Safe: 3-of-5", self.text)
        self.assertNotIn("live OpenZeppelin TimelockController", self.text)
        self.assertNotIn("is NOT a Gnosis Safe", self.text)

    def test_the_score_follows_the_safe_reading_like_the_notes_and_no_timelock_role_is_read(self):
        # Fixed 2026-09-20: the notes and the score used to disagree here (Safe in the notes, Timelock 70 in the
        # score). By hand: adminKey 50 (threshold 3), multisig min(100, 3*15 + (5-3)*5) = 55, timelock 0,
        # composite (4*50 + 3*55 + 0 + 5)//10 = 370//10 = 37.
        r = self.result
        self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["timelockScore"], r["compositeScore"]), (50, 55, 0, 37))
        self.assertEqual(self.fake.calls_of("hasRole"), [])


# ======================================================================================
# Full sub-score tuples and composites, per branch, by hand
# ======================================================================================
def _as_observed(fake):
    pass


def _as_bare_eoa(fake):
    _set_admin(fake, SYNTH_EOA)


def _as_plain_contract(fake):
    _set_admin(fake, SYNTH_PLAIN_CONTRACT)
    fake.code_sizes[SYNTH_PLAIN_CONTRACT.lower()] = SYNTH_PLAIN_CONTRACT_CODE_BYTES


def _as_safe(fake):
    _set_admin(fake, SYNTH_SAFE)
    fake.code_sizes[SYNTH_SAFE.lower()] = SYNTH_SAFE_CODE_BYTES
    fake.safes[SYNTH_SAFE.lower()] = (SYNTH_SAFE_OWNERS, SYNTH_SAFE_THRESHOLD)


def _as_unresolved(fake):
    del fake.address_getters[(LIQUIDITY.lower(), "getAdmin")]


def _as_timelock_with_a_role_gap(fake):
    fake.role_holders[(TIMELOCK.lower(), PROPOSER_ROLE)] = {SYNTH_PROPOSER_STAND_IN.lower()}


def _as_timelock_with_an_unresolved_proposer_signer_set(fake):
    del fake.avocados[PROPOSER.lower()]


def _as_timelock_with_an_executor_that_is_not_a_safe(fake):
    del fake.safes[EXECUTOR.lower()]


def _as_timelock_with_a_zero_delay(fake):
    fake.min_delays[TIMELOCK.lower()] = 0


def _as_timelock_with_an_unreadable_admin_slot(fake):
    del fake.slot_values[(LIQUIDITY.lower(), EIP1967_ADMIN_SLOT)]


def _as_timelock_with_a_disagreeing_admin_slot(fake):
    fake.slot_values[(LIQUIDITY.lower(), EIP1967_ADMIN_SLOT)] = SYNTH_ADMIN_STAND_IN


class TestFluidBranchScoresByHand(_FluidCase):
    """(adminKey, multisig, timelock) -> composite for each branch, every composite a hand-computed LITERAL
    (arithmetic in the comment), so neither the sub-scores nor the weights come from the function under
    test. The weighted sum is METHODOLOGY's: 0.4*admin + 0.3*multisig + 0.3*timelock + 0.5, floored.

    Rows marked CHARACTERIZATION pin today's value for a branch whose documented value differs (see the
    expectedFailure tests in the branch classes above): they keep the wrong number from changing silently.
    """

    BRANCHES = [
        # label, mutation of the observed state, (admin, multisig, timelock), composite
        # observed (signers resolved): 0.4*65 + 0.3*55 + 0.3*55 = 26 + 16.5 + 16.5 = 59 (SCORED)
        ("observed timelock", _as_observed, (65, 55, 55), 59),
        # not confirmed this run, all four land on the floor 0.4*20 + 0.3*0 + 0.3*0 = 8 (never above the confirmed 59):
        # role gap (docs-cited proposer no longer holds the role)
        ("timelock with a role gap", _as_timelock_with_a_role_gap, (20, 0, 0), 8),
        ("timelock with an unresolved proposer signer set", _as_timelock_with_an_unresolved_proposer_signer_set, (20, 0, 0), 8),
        ("timelock whose executor is not a Safe", _as_timelock_with_an_executor_that_is_not_a_safe, (20, 0, 0), 8),
        ("timelock with a zero delay", _as_timelock_with_a_zero_delay, (20, 0, 0), 8),
        ("timelock whose admin slot cross-check is unreadable", _as_timelock_with_an_unreadable_admin_slot, (20, 0, 0), 8),
        ("timelock whose admin slot disagrees with getAdmin()", _as_timelock_with_a_disagreeing_admin_slot, (20, 0, 0), 8),
        # fixed: bare EOA, plain contract, Safe now classified
        # bare EOA: 0.4*5 + 0.3*0 + 0.3*0 = 2 (adminKey 2-10)
        ("bare EOA", _as_bare_eoa, (5, 0, 0), 2),
        # plain contract: 0.4*20 + 0.3*0 + 0.3*0 = 8 (unresolved contract, multisig 0)
        ("plain contract", _as_plain_contract, (20, 0, 0), 8),
        # Gnosis Safe (3-of-5): admin 50 (Aquila's table, 3-of-N), multisig min(100, 3*15 + 2*5) = 55;
        # 0.4*50 + 0.3*55 + 0.3*0 + 0.5 = 20 + 16.5 + 0 + 0.5 = 37
        ("Gnosis Safe", _as_safe, (50, 55, 0), 37),
        # unresolved: 0.4*20 + 0.3*0 + 0.3*0 = 8 (floor 20,0,0, previously 20,100,0)
        ("unresolved", _as_unresolved, (20, 0, 0), 8),
    ]

    def test_every_branch(self):
        for label, mutate, (admin, multisig, timelock), composite in self.BRANCHES:
            with self.subTest(branch=label):
                # the literal composite is checked against the independent hand formula first
                self.assertEqual(_hand_composite(admin, multisig, timelock), composite)
                r = self.score_with(mutate)
                self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["timelockScore"]), (admin, multisig, timelock))
                self.assertEqual(r["compositeScore"], composite)
                # oracle and cross are published but never folded into the composite
                self.assertEqual(r["oracleAuthorityScore"], 100)
                # the cross-ecosystem fold applies only when the proposer signer set was read and matched (observed row)
                self.assertEqual(r["crossExposureScore"], 80 if label == "observed timelock" else 100)


class TestCompositeHelperRoundsHalfUp(unittest.TestCase):
    """`scorers._composite` is the weighted sum the function under test ends with. Inside
    `score_fluid_liquidity_plasma` every reachable weighted sum is an exact integer (admin in {20, 40},
    multisig 100, timelock in {0, 70}: 8/16 + 30 + 0/21), so round-half-up and truncation cannot be told
    apart through the function. The helper's documented rounding (`floor(x + 0.5)`, "standard round-half-up
    ... not Python's builtin round()") is therefore pinned here directly, with hand-derived expectations."""

    def test_half_values_round_up_not_down_and_not_to_even(self):
        # (45, 55, 0): 0.4*45 = 18, 0.3*55 = 16.5, sum 34.5 -> round-half-up 35 (truncation and banker's
        # rounding both give 34). Exact-integer form: (4*45 + 3*55 + 3*0 + 5)//10 = 350//10 = 35.
        self.assertEqual(_hand_composite(45, 55, 0), 35)
        self.assertEqual(scorers._composite(45, 55, 0), 35)

    def test_below_half_rounds_down(self):
        # (44, 55, 0): 17.6 + 16.5 = 34.1 -> 34. Exact-integer form: (176 + 165 + 0 + 5)//10 = 346//10 = 34.
        self.assertEqual(_hand_composite(44, 55, 0), 34)
        self.assertEqual(scorers._composite(44, 55, 0), 34)

    def test_the_published_fluid_triple_and_the_bounds(self):
        self.assertEqual(scorers._composite(40, 100, 70), 67)   # 16 + 30 + 21
        self.assertEqual(scorers._composite(20, 100, 0), 38)    # 8 + 30 + 0
        self.assertEqual(scorers._composite(0, 0, 0), 0)
        self.assertEqual(scorers._composite(100, 100, 100), 100)  # 40 + 30 + 30

    def test_the_weights_are_040_030_030_in_that_order(self):
        # One-hot inputs isolate each weight: 100*0.4 = 40, 100*0.3 = 30, 100*0.3 = 30.
        self.assertEqual(scorers._composite(100, 0, 0), 40)
        self.assertEqual(scorers._composite(0, 100, 0), 30)
        self.assertEqual(scorers._composite(0, 0, 100), 30)


# ======================================================================================
# The TimelockController branch: delay and role checks
# ======================================================================================
class TestFluidTimelockDelay(_FluidCase):
    def test_zero_delay_timelock_scores_timelock_zero(self):
        # METHODOLOGY: timelock 0 "if no delay mechanism is found"; a 0 s minDelay enforces no delay.
        self.fake.min_delays[TIMELOCK.lower()] = 0
        r = self.score()
        self.assertEqual(r["timelockScore"], 0)
        self.assertIn("getMinDelay() = 0s (0h)", self.notes_text(r))

    def test_a_longer_delay_does_not_lift_the_cap_for_the_bounded_path_outside_it(self):
        # timelockScore is capped at 55 because the auths and the guardian (the same team multisig) act without the delay
        # (docstring, data note 2026-09-20), so a 48 h delay scores the same 55 as 24 h, the same rule as the Arbitrum scorer.
        self.fake.min_delays[TIMELOCK.lower()] = SYNTH_DELAY_TWO_DAYS
        r = self.score()
        self.assertEqual(r["timelockScore"], 55)
        self.assertIn("getMinDelay() = 172800s (48h)", self.notes_text(r))

    def test_every_positive_delay_scores_55_including_the_boundaries_around_zero_and_24h(self):
        # CHARACTERIZATION. Only 86400 is a documented observation (score 55, SCORED); 1, 3600, 86399 and
        # 172800 are SYNTHETIC boundary probes. They pin the lower bound of "a real delay" at exactly `> 0`:
        # one second above zero and one second below the documented 24 h all score the same 55 as 24 h itself
        # (see the expectedFailure below for why that flat value is itself questionable).
        for delay in SYNTH_DELAYS_BELOW_A_DAY + (MIN_DELAY, SYNTH_DELAY_TWO_DAYS):
            with self.subTest(delay=delay):
                self.fake.min_delays[TIMELOCK.lower()] = delay
                self.assertEqual(self.score()["timelockScore"], 55)

    def test_a_zero_delay_is_not_a_confirmed_timelock_and_scores_the_floor(self):
        # Fixed 2026-09-20: `chain_closed` did not require a delay above zero, so a 0 s timelock reached adminKey 40.
        self.fake.min_delays[TIMELOCK.lower()] = 0
        r = self.score()
        self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["timelockScore"], r["compositeScore"]), (20, 0, 0, 8))

    # Was an expectedFailure until 2026-09-20 (finding, now fixed). METHODOLOGY.md, timelockScore: "A confirmed real delay scores 60-75
    # DEPENDING ON LENGTH and whether an emergency-bypass path was checked for and ruled out". The scorer
    # returns the same flat 55 (70 before 2026-09-20) for a 1-second minDelay as for the documented 24 h one, so the score does not
    # depend on length at all.
    @unittest.expectedFailure
    def test_a_one_second_delay_scores_lower_than_the_documented_24h_delay(self):
        self.fake.min_delays[TIMELOCK.lower()] = 1
        one_second = self.score()["timelockScore"]
        self.fake.min_delays[TIMELOCK.lower()] = MIN_DELAY
        self.assertLess(one_second, self.score()["timelockScore"])

    def test_unreadable_delay_means_not_a_timelock(self):
        # getMinDelay() reverts / RPC failure -> None -> the admin is treated as not a timelock at all.
        del self.fake.min_delays[TIMELOCK.lower()]
        r = self.score()
        self.assertEqual(r["timelockScore"], 0)
        self.assertEqual(r["adminKeyScore"], 20)
        self.assertEqual(self.fake.calls_of("hasRole"), [])
        self.assertIn("neither a Gnosis Safe nor a TimelockController", self.notes_text(r))


class TestFluidTimelockRoleChecks(_FluidCase):
    """`confirmed` needs: a timelock with a delay above zero AND getAdmin() equal to the raw EIP-1967 admin slot AND self-administered
    AND no zero-address admin AND the docs-cited proposer AND executor both hold their roles AND both signer sets resolved. Failing
    any -> the floor (20, 0, 0), and no delay credit either."""

    def _assert_degraded_to_the_floor(self, r):
        # An unconfirmed chain scores the conservative floor, never above the confirmed 59 (same rule as the Arbitrum Fluid scorer;
        # before 2026-09-20 it kept multisig 100 and timelock 70, composite 59).
        self.assertEqual(r["adminKeyScore"], 20)
        self.assertEqual(r["timelockScore"], 0)
        self.assertEqual(r["multisigScore"], 0)
        # By hand: 0.4*20 + 0.3*0 + 0.3*0 = 8 (a literal, not the returned sub-scores).
        self.assertEqual(r["compositeScore"], 8)
        self.assertEqual(r["crossExposureScore"], 100)  # not compared, disclosed as not computed

    def test_external_super_admin_instead_of_self_administration_opens_the_chain(self):
        t = TIMELOCK.lower()
        self.fake.role_holders[(t, TIMELOCK_ADMIN_ROLE)] = {SYNTH_ADMIN_STAND_IN.lower()}  # someone else, not the timelock
        r = self.score()
        self._assert_degraded_to_the_floor(r)
        self.assertIn("hasRole(TIMELOCK_ADMIN_ROLE, Timelock itself) = False", self.notes_text(r))

    def test_zero_address_holding_the_admin_role_opens_the_chain(self):
        t = TIMELOCK.lower()
        self.fake.role_holders[(t, TIMELOCK_ADMIN_ROLE)] = {t, ZERO.lower()}
        r = self.score()
        self._assert_degraded_to_the_floor(r)
        self.assertIn("hasRole(TIMELOCK_ADMIN_ROLE, 0x0) = True", self.notes_text(r))

    def test_docs_cited_proposer_no_longer_holding_the_role_opens_the_chain(self):
        # Docs (constructor args) and chain disagree: the docs-cited proposer does not hold PROPOSER_ROLE live.
        t = TIMELOCK.lower()
        self.fake.role_holders[(t, PROPOSER_ROLE)] = {SYNTH_PROPOSER_STAND_IN.lower()}
        r = self.score()
        self._assert_degraded_to_the_floor(r)
        self.assertIn(f"hasRole(PROPOSER_ROLE, {PROPOSER}) = False", self.notes_text(r))

    def test_docs_cited_executor_no_longer_holding_the_role_opens_the_chain(self):
        t = TIMELOCK.lower()
        self.fake.role_holders[(t, EXECUTOR_ROLE)] = {SYNTH_EXECUTOR_STAND_IN.lower()}
        r = self.score()
        self._assert_degraded_to_the_floor(r)
        self.assertIn(f"hasRole(EXECUTOR_ROLE, {EXECUTOR}) = False", self.notes_text(r))

    def test_when_every_role_read_is_unreadable_the_result_is_the_unresolved_placeholder(self):
        # Every hasRole read returns None (transient RPC failure): nothing can be confirmed -> 20,
        # never the fully-closed 40. NOTE this forces None on ALL reads, so it cannot show that any ONE
        # read fails closed on its own: the single-read tests below do that.
        self.fake.forced_role_result[TIMELOCK.lower()] = None
        r = self.score()
        self._assert_degraded_to_the_floor(r)
        self.assertIn("hasRole(PROPOSER_ROLE", self.notes_text(r))

    def _only_this_read_is_unreadable(self, role, account):
        self.fake.forced_reads[(TIMELOCK.lower(), role, account.lower())] = None
        return self.score()

    def test_an_unreadable_proposer_read_alone_fails_closed(self):
        # Everything else is the observed state: only hasRole(PROPOSER_ROLE, proposer) returns None.
        r = self._only_this_read_is_unreadable(PROPOSER_ROLE, PROPOSER)
        self._assert_degraded_to_the_floor(r)
        self.assertIn(f"hasRole(PROPOSER_ROLE, {PROPOSER}) = False", self.notes_text(r))

    def test_an_unreadable_executor_read_alone_fails_closed(self):
        r = self._only_this_read_is_unreadable(EXECUTOR_ROLE, EXECUTOR)
        self._assert_degraded_to_the_floor(r)
        self.assertIn(f"hasRole(EXECUTOR_ROLE, {EXECUTOR}) = False", self.notes_text(r))

    def test_an_unreadable_self_administration_read_alone_fails_closed(self):
        r = self._only_this_read_is_unreadable(TIMELOCK_ADMIN_ROLE, TIMELOCK)
        self._assert_degraded_to_the_floor(r)
        self.assertIn("hasRole(TIMELOCK_ADMIN_ROLE, Timelock itself) = None", self.notes_text(r))

    # Was an expectedFailure until 2026-09-20 (finding, now fixed). This is a FAIL-OPEN in the current code: with ONLY the zero-address read
    # unreadable (None) and every other read as observed, `role_admin_found = bool(admin_self) and not
    # bool(admin_zero)` treats "could not read" as "the zero address does not hold the role", and the score
    # reaches the fully-closed 40. The scorer's docstring says the zero address is "confirmed FALSE" and
    # METHODOLOGY.md calls 20 the explicit "unknown, not assumed safe" placeholder: an unread absence is not
    # a confirmed absence, so 20 is the documented fail-closed value (as for the three single reads above).
    # Fixed 2026-09-20.
    def test_an_unreadable_zero_address_read_alone_fails_closed(self):
        r = self._only_this_read_is_unreadable(TIMELOCK_ADMIN_ROLE, ZERO)
        self.assertEqual(r["adminKeyScore"], 20)

    def test_the_unreadable_zero_address_read_is_shown_as_none_in_the_notes_not_coerced_to_false(self):
        r = self._only_this_read_is_unreadable(TIMELOCK_ADMIN_ROLE, ZERO)
        self.assertIn("hasRole(TIMELOCK_ADMIN_ROLE, 0x0) = None", self.notes_text(r))

    def test_only_the_observed_state_reaches_admin_key_65(self):
        t = TIMELOCK.lower()
        observed = self.score_with(lambda fake: None)
        self.assertEqual(observed["adminKeyScore"], 65)  # SCORED

        def role_holders(role, holders):
            return lambda fake: fake.role_holders.__setitem__((t, role), holders)

        def unreadable(role, account):
            return lambda fake: fake.forced_reads.__setitem__((t, role, account.lower()), None)

        def no_delay(fake):
            del fake.min_delays[t]

        one_deviation_each = {
            "not self-administered": (role_holders(TIMELOCK_ADMIN_ROLE, set()), 20),
            "external super-admin": (role_holders(TIMELOCK_ADMIN_ROLE, {SYNTH_ADMIN_STAND_IN.lower()}), 20),
            "zero-address admin": (role_holders(TIMELOCK_ADMIN_ROLE, {t, ZERO.lower()}), 20),
            "no proposer": (role_holders(PROPOSER_ROLE, set()), 20),
            "other proposer": (role_holders(PROPOSER_ROLE, {SYNTH_PROPOSER_STAND_IN.lower()}), 20),
            "no executor": (role_holders(EXECUTOR_ROLE, set()), 20),
            "other executor": (role_holders(EXECUTOR_ROLE, {SYNTH_EXECUTOR_STAND_IN.lower()}), 20),
            "unreadable self-administration": (unreadable(TIMELOCK_ADMIN_ROLE, TIMELOCK), 20),
            "unreadable proposer": (unreadable(PROPOSER_ROLE, PROPOSER), 20),
            "unreadable executor": (unreadable(EXECUTOR_ROLE, EXECUTOR), 20),
            "unreadable delay": (no_delay, 20),
            "admin is a bare EOA": (_as_bare_eoa, 5),  # bare EOA scores 5 (project convention)
            "admin is a plain contract": (_as_plain_contract, 20),  # unresolved contract
            "admin is a Safe": (_as_safe, 50),  # a resolved 3-of-5 Safe: Aquila's table gives 50
            "admin unresolved": (_as_unresolved, 20),  # unresolved admin
        }
        for label, (mutate, expected_admin_key) in one_deviation_each.items():
            with self.subTest(deviation=label):
                self.assertEqual(self.score_with(mutate)["adminKeyScore"], expected_admin_key)

    def test_a_different_canceller_layout_does_not_change_any_score(self):
        # CHARACTERIZATION: the canceller reads are disclosed in a note but feed no score.
        t = TIMELOCK.lower()
        r = self.score_with(lambda fake: fake.role_holders.__setitem__((t, CANCELLER_ROLE), {PROPOSER.lower(), EXECUTOR.lower()}))
        for field, expected in SCORED.items():
            with self.subTest(field=field):
                self.assertEqual(r[field], expected)

    def test_proposer_that_is_a_safe_switches_the_safe_shape_note(self):
        self.fake.safes[PROPOSER.lower()] = (SYNTH_PROPOSER_SAFE_OWNERS, 3)
        text = self.notes_text(self.score())
        self.assertIn("a real Gnosis Safe", text)
        self.assertIn("proposer getOwners()/getThreshold() = a real Gnosis Safe", text)
        self.assertNotIn("proposer getOwners()/getThreshold() = NOT Safe-shaped", text)


# ======================================================================================
# The proposer and executor signer sets (resolved 2026-09-20) and the cross-ecosystem fold
# ======================================================================================
def _committee(prefix, n):
    """n SYNTHETIC signer addresses (not observed), distinct from every documented address."""
    return [_addr(prefix + i) for i in range(n)]


class TestFluidSignerSets(_FluidCase):
    def test_the_avocado_signer_reads_are_made_on_the_proposer(self):
        self.score()
        made = {(c[1], c[2]) for c in self.fake.calls if c[0] == "call_raw"}
        self.assertIn((PROPOSER.lower(), "requiredSigners"), made)
        self.assertIn((PROPOSER.lower(), "signers"), made)

    def test_the_avocado_abis_resolve_to_the_selectors_of_the_documented_functions(self):
        self.score()
        for name, selector in (("requiredSigners", SEL_REQUIRED_SIGNERS), ("signers", SEL_SIGNERS)):
            with self.subTest(function=name):
                self.assertEqual("0x" + function_abi_to_4byte_selector(self.fake.abis[name][0]).hex(), selector)

    def test_an_unresolved_proposer_signer_set_scores_the_floor_and_says_so(self):
        for label, entry in (("no answer", None), ("zero required signers", (0, list(PROPOSER_SIGNERS))), ("no signers", (6, []))):
            with self.subTest(case=label):
                def mutate(fake, entry=entry):
                    if entry is None:
                        del fake.avocados[PROPOSER.lower()]
                    else:
                        fake.avocados[PROPOSER.lower()] = entry
                r = self.score_with(mutate)
                self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["timelockScore"], r["compositeScore"]), (20, 0, 0, 8))
                self.assertEqual(r["crossExposureScore"], 100)
                text = self.notes_text(r)
                self.assertIn("signer strength NOT resolved this run", text)
                self.assertIn("crossExposureScore = 100 (not computed this run", text)
                self.assertNotIn("proposer is an Avocado multisig", text)

    def test_the_score_follows_the_weaker_of_the_two_signer_sets_by_hand(self):
        # (proposer k of n, executor k of n) -> (adminKey, multisig, timelock, composite). adminKey 65 when the weaker set needs at
        # least 3 signatures, 50 at 2, 10 at 1; multisig = the weaker of min(100, k*15 + max(0, n-k)*5); timelock 55.
        cases = [
            # 2-of-3 proposer: 2*15 + 1*5 = 35; executor 3-of-5 = 55 -> multisig 35, adminKey 50. (200 + 105 + 165 + 5)//10 = 47
            ((2, 3), (3, 5), (50, 35, 55, 47)),
            # 1-of-1 proposer: 15; -> adminKey 10, multisig 15. (40 + 45 + 165 + 5)//10 = 25
            ((1, 1), (3, 5), (10, 15, 55, 25)),
            # 6-of-12 proposer: 90 + 30 = 120 -> 100; executor 5-of-9: 75 + 20 = 95 -> multisig 95, adminKey 65. (260 + 285 + 165 + 5)//10 = 71
            ((6, 12), (5, 9), (65, 95, 55, 71)),
            # 3-of-3 proposer: 45, executor 55 -> 45, adminKey 65. (260 + 135 + 165 + 5)//10 = 56
            ((3, 3), (3, 5), (65, 45, 55, 56)),
        ]
        for (pk, pn), (ek, en), expected in cases:
            with self.subTest(proposer=f"{pk}-of-{pn}", executor=f"{ek}-of-{en}"):
                def mutate(fake, pk=pk, pn=pn, ek=ek, en=en):
                    fake.avocados[PROPOSER.lower()] = (pk, _committee(0x5000, pn))
                    fake.safes[EXECUTOR.lower()] = (_committee(0x6000, en), ek)
                r = self.score_with(mutate)
                self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["timelockScore"], r["compositeScore"]), expected)
                self.assertEqual(_hand_composite(*expected[:3]), expected[3])


class TestFluidCrossExposureFold(_FluidCase):
    """METHODOLOGY.md "Convention (decided 2026-09-20)": a root committee identical, as a set, to the committee of a tracked
    target on another ecosystem scores crossExposure 80, else 100. Here: the Avocado multisig that is also the proposer of the
    tracked Fluid Liquidity on Arbitrum One."""

    def test_the_snapshot_is_the_committee_read_on_arbitrum_and_equals_the_one_read_on_plasma(self):
        self.assertEqual(scorers._FLUID_TEAM_SIGNERS_ARBITRUM_2026_09_20, frozenset(a.lower() for a in PROPOSER_SIGNERS))
        self.assertEqual(len(scorers._FLUID_TEAM_SIGNERS_ARBITRUM_2026_09_20), 12)

    def test_an_identical_set_scores_80_whatever_the_order_or_the_address_case(self):
        for label, signers in (("reversed", list(reversed(PROPOSER_SIGNERS))),
                               ("checksummed", [RealWeb3.to_checksum_address(a) for a in PROPOSER_SIGNERS])):
            with self.subTest(read=label):
                r = self.score_with(lambda fake, signers=signers: fake.avocados.__setitem__(PROPOSER.lower(), (6, signers)))
                self.assertEqual(r["crossExposureScore"], 80)
                self.assertIn("crossExposureScore = 80: the freshly read proposer signer set is identical", self.notes_text(r))

    def test_a_set_that_differs_by_one_signer_or_by_an_extra_one_scores_100_with_the_reason(self):
        swapped = list(PROPOSER_SIGNERS[:-1]) + [SYNTH_ADMIN_STAND_IN]
        extra = list(PROPOSER_SIGNERS) + [SYNTH_ADMIN_STAND_IN]
        for label, signers in (("one signer swapped", swapped), ("one extra signer", extra)):
            with self.subTest(read=label):
                r = self.score_with(lambda fake, signers=signers: fake.avocados.__setitem__(PROPOSER.lower(), (6, signers)))
                self.assertEqual(r["crossExposureScore"], 100)
                self.assertIn("does NOT match exactly", self.notes_text(r))
                self.assertEqual(r["compositeScore"], 59)  # the fold never enters the composite

    def test_the_fold_does_not_lower_the_three_sub_scores(self):
        r = self.score()
        self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["timelockScore"]), (65, 55, 55))


# ======================================================================================
# Cross-checks between two sources
# ======================================================================================
class TestFluidCrossChecks(_FluidCase):
    # Was an expectedFailure until 2026-09-20 (finding, now fixed). The docstring and the emitted note both state that getAdmin() was
    # "cross-checked live via a raw eth_getStorageAt read at that slot" (the EIP-1967 admin slot
    # 0xb531...6103, FLUID NOTE sec.4). The scorer imports read_slot_as_address but never calls it in
    # this function, so that cross-check is a hard-coded sentence, not something a run performs.
    # Fixed 2026-09-20.
    def test_getadmin_is_cross_checked_against_the_eip1967_admin_slot_at_run_time(self):
        self.fake.slot_values[(LIQUIDITY.lower(), EIP1967_ADMIN_SLOT)] = TIMELOCK
        self.score()
        slot_reads = [c for c in self.fake.calls_of("read_slot_as_address") if c[1] == LIQUIDITY.lower()]
        self.assertGreaterEqual(len(slot_reads), 1)

    def test_a_slot_read_equal_to_getadmin_is_reported_as_the_identical_address(self):
        self.fake.slot_values[(LIQUIDITY.lower(), EIP1967_ADMIN_SLOT)] = TIMELOCK
        text = self.notes_text(self.score())
        self.assertIn("eth_getStorageAt read at that slot, which returned the identical address", text)
        self.assertNotIn("DIFFERENT address", text)
        self.assertNotIn("cross-check NOT completed", text)

    def test_a_slot_read_that_differs_from_getadmin_is_reported_as_different(self):
        self.fake.slot_values[(LIQUIDITY.lower(), EIP1967_ADMIN_SLOT)] = SYNTH_ADMIN_STAND_IN
        text = self.notes_text(self.score())
        self.assertIn("which returned a DIFFERENT address", text)
        self.assertIn("the two views of the admin do not agree", text)
        self.assertNotIn("identical address", text)
        r = self.score()
        self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["timelockScore"], r["compositeScore"]), (20, 0, 0, 8))

    def test_an_unreadable_slot_is_reported_as_the_cross_check_not_completed_and_scores_the_floor(self):
        self.fake.slot_values.clear()  # the raw read returns nothing
        r = self.score()
        text = self.notes_text(r)
        self.assertIn("which could not be read this run (cross-check NOT completed)", text)
        self.assertNotIn("identical address", text)
        # An unconfirmed chain scores the floor, as the Arbitrum Fluid scorer does when its slot cross-check fails.
        self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["timelockScore"], r["compositeScore"]), (20, 0, 0, 8))
        self.assertEqual(r["crossExposureScore"], 100)

    # Was an expectedFailure until 2026-09-20 (finding, now fixed). The timelock note says the live delay "matches deployments.md's
    # documented constructor arg (86400) ... exactly" (FLUID NOTE sec.5 docs-vs-chain cross-check). The
    # sentence is emitted unconditionally, so a live delay of 48 h (docs and chain now DISAGREE) still
    # reports a match.
    # Fixed 2026-09-20.
    def test_a_live_delay_that_differs_from_the_docs_86400_is_not_reported_as_a_match(self):
        self.fake.min_delays[TIMELOCK.lower()] = SYNTH_DELAY_TWO_DAYS
        text = self.notes_text(self.score())
        self.assertNotIn("matches deployments.md", text)

    # Was an expectedFailure until 2026-09-20 (finding, now fixed). The emergency-bypass note claims "canceller power sits on the same
    # address as PROPOSER_ROLE only ... no separate zero-delay cancel path found" (FLUID NOTE sec.6:
    # canceller on proposer, NOT on executor). The sentence is emitted unconditionally, so it is printed
    # right after a read showing the executor DOES hold CANCELLER_ROLE.
    # Fixed 2026-09-20.
    def test_canceller_also_on_the_executor_is_not_reported_as_proposer_only(self):
        t = TIMELOCK.lower()
        self.fake.role_holders[(t, CANCELLER_ROLE)] = {PROPOSER.lower(), EXECUTOR.lower()}
        text = self.notes_text(self.score())
        self.assertIn("hasRole(CANCELLER_ROLE, proposer) = True, hasRole(CANCELLER_ROLE, executor) = True", text)
        self.assertNotIn("sits on the same address as PROPOSER_ROLE only", text)

    # Was an expectedFailure until 2026-09-20 (finding, now fixed). The role note ends "-- self-administered, no separate external super-admin
    # escape hatch found" (FLUID NOTE sec.6 draws that conclusion from the reads true/false). The sentence is
    # emitted unconditionally, so it is printed right after a read showing the Timelock is NOT
    # self-administered (an external address holds TIMELOCK_ADMIN_ROLE) or that the zero address holds it.
    # Fixed 2026-09-20.
    def test_an_external_super_admin_is_not_reported_as_self_administered(self):
        t = TIMELOCK.lower()
        self.fake.role_holders[(t, TIMELOCK_ADMIN_ROLE)] = {SYNTH_ADMIN_STAND_IN.lower()}
        text = self.notes_text(self.score())
        self.assertIn("hasRole(TIMELOCK_ADMIN_ROLE, Timelock itself) = False", text)
        self.assertNotIn("no separate external super-admin escape hatch found", text)

    def test_canceller_reads_are_reported_verbatim_even_when_they_differ_from_the_observed_state(self):
        t = TIMELOCK.lower()
        self.fake.role_holders[(t, CANCELLER_ROLE)] = {EXECUTOR.lower()}
        text = self.notes_text(self.score())
        self.assertIn("hasRole(CANCELLER_ROLE, proposer) = False, hasRole(CANCELLER_ROLE, executor) = True", text)

    def test_owner_reading_something_is_recorded_but_does_not_change_the_score(self):
        # FLUID NOTE sec.4 says owner() reverts. If it ever answered (SYNTH_OWNER, invented), the note must
        # show the value and the score still comes from the getAdmin() chain.
        self.fake.owner_results[LIQUIDITY.lower()] = SYNTH_OWNER
        r = self.score()
        self.assertIn(f"Liquidity.owner() = {SYNTH_OWNER}", self.notes_text(r))
        for field, expected in SCORED.items():
            with self.subTest(field=field):
                self.assertEqual(r[field], expected)


if __name__ == "__main__":
    unittest.main()
