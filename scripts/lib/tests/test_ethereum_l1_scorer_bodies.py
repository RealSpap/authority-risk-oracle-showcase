"""
Unit tests that execute the REAL BODIES of four chains/ethereum-l1/scorers.py
functions that no other unit test ran (coverage: every statement but the `def`
line unexecuted in each), with the chain reads patched:

    score_compound_v3_cusdc          (Compound V3 cUSDCv3, Comet USDC)
    score_sparklend_pool             (SparkLend PoolAddressesProvider)
    score_uniswap_v4_pool_manager    (Uniswap V4 PoolManager)
    score_wbtc                       (WBTC token, Controller + legacy MultiSigWallet)

Until now they were only checked by live runs against Ethereum mainnet and by
the smaller resolved-plus-one-degraded suite in
chains/ethereum-l1/tests/test_new_targets_2026_09_19.py. This file covers every
branch: the happy path that reproduces the PUBLISHED row (all five sub-scores
plus the composite plus the notes that carry the disclosed limits), each
unresolved or off-target read degrading to the documented floor, an EOA versus a
Safe versus a timelock versus a multisig as the authority, cross-checks between
two sources that disagree, and the boundary of every cap or threshold rule.

FIXTURE PROVENANCE
------------------
Every expected score below is one of these, never the function's own output
copied back. Each fixture and each test says which one it is:

  PUBLISHED  a value from chains/ethereum-l1/deploy/README.md, table "Current
             on-chain scores (re-push, 2026-09-20)", rows 9, 10, 11, 13
               9  Compound V3 cUSDCv3   78 / 100 / 60 / 100 / cross 100 / composite 79
               10 SparkLend             75 / 100 / 60 / 100 / cross  80 / composite 78
               11 Uniswap V4 PoolMgr    80 / 100 / 75 / 100 / cross  80 / composite 85
               13 WBTC                  55 / 100 /  0 / 100 / cross 100 / composite 52
             (same rows in chains/ethereum-l1/data/maintenance_2026-09-19.md
             section (b), and on dashboard/index.html, CHAINS.ethereum-l1 idx 9-13).
             HONEST LIMIT: those published numbers are the on-chain output of
             these same scorers (read back equal to the scorer output on
             2026-09-20), so a PUBLISHED row is a REGRESSION ANCHOR, not an
             independent oracle. What makes the file more than a mirror is
             (1) TestCitationsHold, which re-reads the README table and checks the
             cited rows still say what the fixtures say, and that the composite of
             EVERY published row (15, eight of them on a .5 rounding boundary) is
             the exact formula applied to that row's own published sub-scores;
             (2) the raw reads feeding each fixture come from the scorers'
             docstrings and maintenance_2026-09-19.md (delay 172,800s, MINIMUM_DELAY
             172,800s, 608 proposals, pauseGuardian Safe 5-of-9, FreezerMom Safe
             3-of-5, quorum 40M UNI, WBTC required() = 6 / getOwners() = 10), and
             TestCitationsHold checks the docstrings and the note still contain
             the principal figures (not every one: MINIMUM_DELAY and
             transactionCount are cited but not machine-checked);
  HAND       an arithmetic derivation done by hand from the written formula, with
             the working next to it: METHODOLOGY.md "Aggregation",
             compositeScore = floor(0.4*admin + 0.3*multisig + 0.3*timelock + 0.5),
             and for WBTC the multisig formula METHODOLOGY.md "What each dimension
             actually reads" gives, min(100, threshold*15 + max(0, owners-threshold)*5).
             Every hand composite is also re-checked against exact rational
             arithmetic (fractions.Fraction), independent of scorers._composite
             (the same formula, so independent of float rounding, not of the
             formula; the formula itself is anchored to the 15 published rows);
  PROBE      an invented boundary or degraded state (delay 172799 / 0 / 3600,
             proposalCount 0 / 1, wards 2, a 1-of-9 guardian, a lower-case address,
             a 6-required / 5-owner "misread"), NOT a documented real state. The
             expected value is hand arithmetic from the formula, and the test says
             PROBE;
  CHARACTERISATION  a probe whose expected value is what the scorer does today
             where no written policy decides it. These are named
             test_..._current_behaviour or say CHARACTERISATION, and they are the
             tests a deliberate scorer change must edit (and say so in its commit).
             Where METHODOLOGY.md DOES decide the case and the scorer disagrees, the
             test asserts the documented value under unittest.expectedFailure
             instead (see TestUniswapV4PoolManagerDelay).

Addresses. A full address is taken from the scorer body, a data note or the
README where one carries it (cited next to the constant). Five fixture addresses
are documented in the repo only as an 8-hex prefix in a scorer docstring, and
their full value appears only in the earlier chains/ethereum-l1/tests/
test_new_targets_2026_09_19.py: COMP_GOVERNOR, COMP_PAUSE_GUARDIAN,
V4_FEE_ADAPTER, WBTC_CONTROLLER, WBTC_MULTISIG. They are IDENTIFIER-ONLY: no score
depends on their value, and a test per scorer proves it by moving each of them
to an unrelated address and getting the same score. TestCitationsHold checks
every fixture address that has a docstring prefix against that prefix. Multisig
owner lists (`_owners`) are placeholders: only their COUNT feeds a score (also
proven by a test), and the real signer sets are not part of any documented fixture.

Everything is offline. The scorer imported `call_raw` and
`safe_owners_and_threshold` into its own namespace, so those two names are
patched (the imported name, not the transport); `cross_checked` and
`safe_score` are patched to fail loudly if any of these four functions ever
started to use them. The fake checks every ABI fragment the scorer builds
(function name, argument count, argument and return types), refuses a `None`
address (which the real call_raw would spend ~2.4s of retry sleeps on), and, like
web3 7.x, refuses an address ARGUMENT that is not EIP-55: it runs the real ABI
encoder and, as the real call_raw does, returns None when the encoder raises
(recorded in `FakeChain.rejected`).

Notes. The notes are the channel that carries each scorer's disclosed limits, so
their wording is asserted deliberately, and every disclosure is asserted both
present where it applies and absent where it does not (never only absent). They
mirror the scorers' f-strings by nature, so they are presence checks, not an
independent oracle for a score.

Whitebox wiring tests (the composite helper's argument order, the w3 checksum
normaliser) exist only because the mutations they catch are invisible in every
output a scorer can produce; each says so.
"""
import importlib.util
import inspect
import os
import re
import sys
import unittest
from fractions import Fraction

from web3 import Web3 as RealWeb3

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
scorers = _load_module("aro_test_eth_l1_scorer_bodies_scorers", "chains/ethereum-l1/scorers.py")


# --------------------------------------------------------------------------- fakes
_ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")
# encode_abi is pure: nothing is ever sent, and the provider points at the discard port on this machine anyway.
_ENCODER_W3 = RealWeb3(RealWeb3.HTTPProvider("http://127.0.0.1:9"))


def _norm(value):
    """Lower-case anything that looks like an address, so a lookup does not
    depend on checksum case (the scorers call w3.to_checksum_address on some
    arguments and not on others)."""
    if isinstance(value, str) and value.startswith("0x"):
        return value.lower()
    return value


def _type_ok(solidity_type, value):
    if solidity_type == "address":
        return isinstance(value, str) and bool(_ADDRESS_RE.match(value))
    if solidity_type in ("uint8", "uint40", "uint256"):
        return isinstance(value, int) and not isinstance(value, bool)
    if solidity_type == "bool":
        return isinstance(value, bool)
    if solidity_type == "bytes32":
        return isinstance(value, bytes) and len(value) == 32
    if solidity_type == "address[]":
        return isinstance(value, list) and all(_type_ok("address", v) for v in value)
    return True


class FakeChain:
    """The two chain-read primitives the four scorers import, backed by dicts.
    A key that was never set reads as None, exactly like a real call_raw whose
    eth_call reverted or failed every retry."""

    def __init__(self):
        self.reads = {}        # (address.lower(), function_name, normalised args) -> value
        self.safes = {}        # address.lower() -> (owners, threshold)
        self.calls = []        # every (address, function_name, args) call_raw received
        self.rejected = []     # calls the real web3 ABI encoder refused (the real call_raw would return None)
        self.safe_calls = []   # every address safe_owners_and_threshold received

    @staticmethod
    def _key(address, function_name, args):
        return (_norm(address), function_name, tuple(_norm(a) for a in args))

    def set(self, address, function_name, value, *args):
        self.reads[self._key(address, function_name, args)] = value

    def unset(self, address, function_name, *args):
        # KeyError on a typo, so a "degrade" test can never silently remove nothing.
        del self.reads[self._key(address, function_name, args)]

    def set_safe(self, address, owners, threshold):
        self.safes[_norm(address)] = (list(owners), threshold)

    def unset_safe(self, address):
        del self.safes[_norm(address)]

    def merged_with(self, *others):
        merged = FakeChain()
        for chain in (self,) + others:
            merged.reads.update(chain.reads)
            merged.safes.update(chain.safes)
        return merged

    def call_raw(self, w3, address, abi_fragment, function_name, *args, retries=4):
        self.calls.append((address, function_name, args))
        if address is None:
            raise AssertionError(
                f"scorer called call_raw({function_name!r}) with a None address; the real call_raw would burn "
                "its retry sleeps on it, the scorer must short-circuit"
            )
        assert len(abi_fragment) == 1, abi_fragment
        fragment = abi_fragment[0]
        assert fragment["name"] == function_name, (fragment["name"], function_name)
        assert len(fragment["inputs"]) == len(args), (function_name, fragment["inputs"], args)
        for declared, arg in zip(fragment["inputs"], args):
            assert _type_ok(declared["type"], arg), (function_name, declared, arg)
        try:
            # Same encoder, same refusal as the real call_raw: web3 7.x raises InvalidAddress for an address
            # argument that is not EIP-55, and call_raw swallows it and returns None (degrading the score).
            _ENCODER_W3.eth.contract(
                address=RealWeb3.to_checksum_address(address), abi=abi_fragment
            ).encode_abi(function_name, args=list(args))
        except Exception as exc:
            self.rejected.append((address, function_name, args, type(exc).__name__))
            return None
        value = self.reads.get(self._key(address, function_name, args))
        if value is not None and len(fragment["outputs"]) == 1:
            assert _type_ok(fragment["outputs"][0]["type"], value), (function_name, fragment["outputs"], value)
        return value

    def safe_owners_and_threshold(self, w3, address, retries=4):
        self.safe_calls.append(address)
        if address is None:
            raise AssertionError("scorer called safe_owners_and_threshold(None); it must short-circuit")
        return self.safes.get(_norm(address))

    def cross_checked(self, rpc_urls, fn, *args):
        raise AssertionError("none of these four scorers is supposed to use cross_checked")

    def safe_score(self, label, fn, *args):
        raise AssertionError("none of these four scorers is supposed to use safe_score")


class FakeW3:
    """to_checksum_address is the real implementation (Spark passes checksummed
    addresses as call arguments); get_code exists only because the real
    score_uniswap_v3_factory, run as V4's sibling in the cross-exposure test,
    asks for the fee adapter's code size (7266 bytes, maintenance_2026-09-19.md
    section (a))."""

    class eth:
        @staticmethod
        def get_code(addr):
            return b"\x60" * 7266

    @staticmethod
    def to_checksum_address(addr):
        return RealWeb3.to_checksum_address(addr)


class RecordingW3(FakeW3):
    """FakeW3 that remembers every address handed to to_checksum_address (used by the white-box wiring
    test that proves SparkLend normalises each address argument through the injected `w3`)."""

    def __init__(self):
        self.checksummed = []

    def to_checksum_address(self, addr):
        self.checksummed.append(addr)
        return RealWeb3.to_checksum_address(addr)


def _spy_on_composite(test_case):
    """Wrap scorers._composite so a test can see exactly which (admin, multisig, timelock) a scorer handed to
    the ONE shared implementation of METHODOLOGY.md's formula. The wrapper delegates to the real function; the
    expected values in the tests using it are hand-derived, never read from here. Returns the list of
    (admin, multisig, timelock) triples seen. White-box on purpose: multisig and timelock both weigh 0.3, so
    swapping them, or re-implementing the formula inline with a different rounding, is invisible in the output
    on every input a scorer can reach."""
    real = scorers._composite
    seen = []

    def spy(*args, **kwargs):
        bound = inspect.signature(real).bind(*args, **kwargs)
        seen.append((bound.arguments["admin_key"], bound.arguments["multisig"], bound.arguments["timelock"]))
        return real(*args, **kwargs)

    scorers._composite = spy
    test_case.addCleanup(setattr, scorers, "_composite", real)
    return seen


def _patch_helpers(test_case, chain):
    names = {
        "call_raw": chain.call_raw,
        "safe_owners_and_threshold": chain.safe_owners_and_threshold,
        "cross_checked": chain.cross_checked,
        "safe_score": chain.safe_score,
    }
    originals = {n: getattr(scorers, n) for n in names}
    for n, fake in names.items():
        setattr(scorers, n, fake)
    test_case.addCleanup(lambda: [setattr(scorers, n, originals[n]) for n in names])


def _owners(n, start=1):
    """n distinct placeholder owner addresses; only the count matters to a score."""
    return [RealWeb3.to_checksum_address("0x" + hex(i)[2:].zfill(40)) for i in range(start, start + n)]


def _some_address(tag):
    """A distinct, valid, otherwise meaningless address (an 'other' authority)."""
    return RealWeb3.to_checksum_address("0x" + tag.encode().hex().zfill(40)[-40:])


class _ScorerCase(unittest.TestCase):
    """setUp builds the documented fixture; a test then breaks one thing."""

    def build_chain(self):
        raise NotImplementedError

    def run_scorer(self):
        raise NotImplementedError

    def setUp(self):
        self.chain = self.build_chain()
        _patch_helpers(self, self.chain)

    def assertScores(self, result, admin, multisig, timelock, composite):
        self.assertEqual(
            (result["adminKeyScore"], result["multisigScore"], result["timelockScore"],
             result["oracleAuthorityScore"], result["compositeScore"]),
            (admin, multisig, timelock, 100, composite),
        )

    def assertNote(self, result, fragment):
        self.assertTrue(
            any(fragment in n for n in result["notes"]),
            f"no note contains {fragment!r}; notes were:\n" + "\n".join(result["notes"]),
        )

    def assertNoNote(self, result, fragment):
        self.assertFalse(
            any(fragment in n for n in result["notes"]),
            f"a note unexpectedly contains {fragment!r}; notes were:\n" + "\n".join(result["notes"]),
        )

    def calls_named(self, function_name):
        return [c for c in self.chain.calls if c[1] == function_name]


# --------------------------------------------------------------------------- composite arithmetic
# (admin, multisig, timelock, composite): composite = floor(0.4*a + 0.3*m + 0.3*t + 0.5) = (4a+3m+3t+5)//10,
# METHODOLOGY.md "Aggregation". Working shown per row; every row below is a triple one of
# the four scorers can produce.
HAND_DERIVED_COMPOSITES = [
    (78, 100, 60, 79),   # 31.2 + 30 + 18   = 79.2 -> +0.5 = 79.7 -> 79    (Compound, published 79)
    (20, 20, 60, 32),    # 8 + 6 + 18       = 32   -> 32.5        -> 32    (Compound, root not confirmed)
    (78, 100, 0, 61),    # 31.2 + 30 + 0    = 61.2 -> 61.7        -> 61
    (20, 20, 0, 14),     # 8 + 6 + 0        = 14   -> 14.5        -> 14    (every read failed: the documented floor)
    (75, 100, 60, 78),   # 30 + 30 + 18     = 78   -> 78.5        -> 78    (SparkLend, published 78)
    (75, 100, 0, 60),    # 30 + 30 + 0      = 60   -> 60.5        -> 60
    (80, 100, 75, 85),   # 32 + 30 + 22.5   = 84.5 -> 85.0        -> 85    (Uniswap V4, published 85)
    (60, 100, 75, 77),   # 24 + 30 + 22.5   = 76.5 -> 77.0        -> 77
    (20, 20, 75, 37),    # 8 + 6 + 22.5     = 36.5 -> 37.0        -> 37    (Uniswap V4, root not confirmed)
    (80, 100, 0, 62),    # 32 + 30 + 0      = 62   -> 62.5        -> 62
    (55, 100, 0, 52),    # 22 + 30 + 0      = 52   -> 52.5        -> 52    (WBTC, published 52)
    (55, 95, 0, 51),     # 22 + 28.5 + 0    = 50.5 -> 51.0        -> 51    (WBTC 5-of-9: a .5 boundary; truncating gives 50)
    (55, 90, 0, 49),     # 22 + 27 + 0      = 49   -> 49.5        -> 49
    (55, 80, 0, 46),     # 22 + 24 + 0      = 46   -> 46.5        -> 46
    (20, 70, 0, 29),     # 8 + 21 + 0       = 29   -> 29.5        -> 29
    (20, 60, 0, 26),     # 8 + 18 + 0       = 26   -> 26.5        -> 26
    (20, 50, 0, 23),     # 8 + 15 + 0       = 23   -> 23.5        -> 23    (WBTC required() = 0 probe)
    (10, 20, 0, 10),     # 4 + 6 + 0        = 10   -> 10.5        -> 10
]


def _exact_composite(admin, multisig, timelock):
    value = Fraction(4, 10) * admin + Fraction(3, 10) * multisig + Fraction(3, 10) * timelock + Fraction(1, 2)
    return value.numerator // value.denominator


class TestCompositeArithmeticBehindTheExpectedValues(unittest.TestCase):
    def test_hand_derived_table_equals_exact_rational_arithmetic(self):
        for admin, multisig, timelock, composite in HAND_DERIVED_COMPOSITES:
            self.assertEqual(_exact_composite(admin, multisig, timelock), composite, (admin, multisig, timelock))

    def test_float_composite_helper_agrees_with_exact_arithmetic_on_every_row(self):
        for admin, multisig, timelock, composite in HAND_DERIVED_COMPOSITES:
            self.assertEqual(scorers._composite(admin, multisig, timelock), composite, (admin, multisig, timelock))


# =========================================================================== Compound V3 cUSDCv3
# Addresses.
#   COMET: deploy/README.md row 9 (and the scorer body).
#   COMP_TIMELOCK: the "Compound Timelock" the docstring calls 0x6d903f60..., full address in
#     chains/base-ecosystem/data/scouted_targets_2026-09-16.md (BaseBridgeReceiver.govTimelock()) and
#     chains/arbitrum-ecosystem/scorers.py (_COMPOUND_L1_GOVERNANCE_TIMELOCK).
#   COMP_PROXY_ADMIN, COMP_CONFIGURATOR: the "CometProxyAdmin 0x1EC63B58..." of the docstring and the
#     Configurator, full values in the scorer body (they are the two contracts the scorer reads).
#   COMP_PAUSE_GUARDIAN ("pauseGuardian 0xbbf3f142..." in the docstring) and COMP_GOVERNOR (the docstring names
#     no address for it): IDENTIFIER-ONLY. Their full values are documented in the repo only in
#     chains/ethereum-l1/tests/test_new_targets_2026_09_19.py, neither is in the scorer body (which reads
#     them from the chain), and no score depends on their value:
#     TestCompoundV3CusdcIdentifiersAreOnlyIdentifiers proves it.
COMET = "0xc3d688B66703497DAA19211EEdff47f25384cdc3"
COMP_TIMELOCK = "0x6d903f6003cca6255D85CcA4D3B5E5146dC33925"
COMP_GOVERNOR = "0x309a862bbC1A00e45506cB8A802D1ff10004c8C0"
COMP_PROXY_ADMIN = "0x1EC63B5883C3481134FD50D5DAebc83Ecd2E8779"
COMP_CONFIGURATOR = "0x316f9708bB98af7dA9c68C1C3b5e79039cD336E3"
COMP_PAUSE_GUARDIAN = "0xbbf3f1421D886E9b2c5D716B5192aC998af2012c"


def _compound_chain():
    """The reads the scorer's docstring documents (observed live 2026-09-19): delay() = MINIMUM_DELAY =
    172,800s, Timelock.admin() = the Compound Governor with 608 proposals, CometProxyAdmin.owner() and
    Configurator.governor() both the same Timelock, pauseGuardian = a 5-of-9 Safe."""
    chain = FakeChain()
    chain.set(COMET, "governor", COMP_TIMELOCK)
    chain.set(COMP_TIMELOCK, "delay", 172800)
    chain.set(COMP_TIMELOCK, "MINIMUM_DELAY", 172800)
    chain.set(COMP_TIMELOCK, "admin", COMP_GOVERNOR)
    chain.set(COMP_GOVERNOR, "proposalCount", 608)
    chain.set(COMP_PROXY_ADMIN, "owner", COMP_TIMELOCK)
    chain.set(COMP_CONFIGURATOR, "governor", COMP_TIMELOCK)
    chain.set(COMET, "pauseGuardian", COMP_PAUSE_GUARDIAN)
    chain.set_safe(COMP_PAUSE_GUARDIAN, _owners(9), 5)
    return chain


class TestCompoundV3CusdcPublishedRow(_ScorerCase):
    def build_chain(self):
        return _compound_chain()

    def run_scorer(self):
        return scorers.score_compound_v3_cusdc(FakeW3())

    def test_reproduces_the_published_sub_scores_and_composite(self):
        # PUBLISHED deploy/README.md row 9: 78 / 100 / 60 / oracle 100 / composite 79 (HAND: 31.2+30+18 = 79.2 -> 79)
        self.assertScores(self.run_scorer(), 78, 100, 60, 79)
        self.assertEqual(self.chain.rejected, [])  # every argument was one the real web3 encoder accepts

    def test_the_composite_comes_from_the_shared_helper_fed_admin_multisig_timelock_in_that_order(self):
        # White-box, see _spy_on_composite: (78, 100, 60) HAND-derived above; 100 and 60 differ, so a swapped
        # order shows. An inline formula would never call the helper at all.
        seen = _spy_on_composite(self)
        result = self.run_scorer()
        self.assertEqual(seen, [(78, 100, 60)])
        self.assertEqual(result["compositeScore"], 79)

    def test_target_label_and_root_group(self):
        result = self.run_scorer()
        self.assertEqual(result["target"], COMET)  # deploy/README.md row 9 address
        self.assertEqual(result["label"], "Compound V3 cUSDCv3 (Comet USDC)")
        self.assertEqual(result["_rootGroup"], "compound-l1-governance")

    def test_published_cross_exposure_is_100_because_no_other_target_shares_the_root(self):
        result = self.run_scorer()
        scorers._apply_cross_exposure([result])
        self.assertEqual(result["crossExposureScore"], 100)  # deploy/README.md row 9, cross column
        self.assertNotIn("_rootGroup", result)
        self.assertNotIn("_crossEcosystem", result)
        self.assertNoNote(result, "shares its root authority")

    def test_notes_record_the_delay_the_floor_the_governor_and_the_proposal_count(self):
        result = self.run_scorer()
        self.assertNote(result, f"Comet.governor() = {COMP_TIMELOCK} (Compound Timelock)")
        self.assertNote(
            result, f"Timelock.delay() = 172800s ; MINIMUM_DELAY = 172800s ; Timelock.admin() = {COMP_GOVERNOR}")
        self.assertNote(result, "CompoundGovernor.proposalCount() = 608")

    def test_notes_record_that_the_upgrade_and_config_paths_converge_on_the_timelock(self):
        result = self.run_scorer()
        self.assertNote(
            result,
            f"CometProxyAdmin.owner() = {COMP_TIMELOCK} ; Configurator.governor() = {COMP_TIMELOCK} "
            "(both expected = the Timelock)",
        )

    def test_notes_carry_the_disclosed_instant_pause_bypass_of_the_5_of_9_safe(self):
        result = self.run_scorer()
        self.assertNote(result, f"Comet.pauseGuardian() = {COMP_PAUSE_GUARDIAN}: real Gnosis Safe 5-of-9")
        self.assertNote(result, "can pause supply/transfer/withdraw/absorb/buy instantly (freeze, not redirect)")
        self.assertNoNote(result, "degraded")
        self.assertNoNote(result, "NOT resolved as a Safe")

    def test_reads_the_contracts_the_docstring_names(self):
        self.run_scorer()
        touched = {c[0].lower() for c in self.chain.calls}
        self.assertIn("0xc3d688b66703497daa19211eedff47f25384cdc3", touched)  # Comet, deploy/README.md row 9
        self.assertTrue(any(a.startswith("0x1ec63b58") for a in touched))     # CometProxyAdmin, docstring prefix
        self.assertEqual(self.chain.safe_calls, [COMP_PAUSE_GUARDIAN])        # the Safe check goes to pauseGuardian()


class TestCompoundV3CusdcRootUnread(_ScorerCase):
    def build_chain(self):
        return _compound_chain()

    def run_scorer(self):
        return scorers.score_compound_v3_cusdc(FakeW3())

    def test_comet_governor_unread_degrades_to_the_documented_floor(self):
        self.chain.unset(COMET, "governor")
        result = self.run_scorer()
        self.assertScores(result, 20, 20, 0, 14)  # governor unread => Timelock unread (delay 0 credit), root unconfirmed: 8 + 6 + 0 = 14 -> 14.5 -> 14
        self.assertNote(result, "Comet.governor() = None (Compound Timelock)")
        self.assertNote(result, "did not fully resolve or converge this run -- adminKeyScore degraded")
        self.assertNote(result, "Timelock.delay() unread or below 2 days this run -- timelockScore degraded")

    def test_comet_governor_unread_makes_no_read_on_a_none_address(self):
        self.chain.unset(COMET, "governor")
        self.run_scorer()  # the fake raises on any call_raw(None, ...)
        for downstream in ("delay", "MINIMUM_DELAY", "admin", "proposalCount"):
            self.assertEqual(self.calls_named(downstream), [], downstream)

    def test_nothing_resolving_at_all_including_the_upgrade_path_gives_the_floor(self):
        # PROBE: timelock None, ProxyAdmin.owner() None, Configurator.governor() None. HAND: 8 + 6 + 0 = 14.
        # This does NOT test that None == None is refused: with the Timelock unread the governor and
        # proposalCount are unread too, so adminKeyScore is 20 whatever `_same` says. The None == None guard
        # cannot be observed through any of the four scorers (every other _same operand is a non-None
        # constant), so it is pinned directly on the helper in TestSameHelper. Fixed 2026-09-20
        self.chain.unset(COMET, "governor")
        self.chain.unset(COMP_PROXY_ADMIN, "owner")
        self.chain.unset(COMP_CONFIGURATOR, "governor")
        self.assertScores(self.run_scorer(), 20, 20, 0, 14)

    def test_comet_governor_is_a_bare_eoa_gets_the_floor_even_when_the_upgrade_path_points_at_it(self):
        # An EOA has no delay()/admin(), so those reads revert (unset -> None). ProxyAdmin and Configurator
        # agree with it, so the convergence check passes, but the governor chain cannot be traced. This scorer reads no
        # bytecode: an EOA governor is indistinguishable from any other unresolved governor and takes the unconfirmed-root
        # floor (20/20). METHODOLOGY.md gives multisig 0 for a root KNOWN to be a bare EOA; this scorer does not tell them apart.
        eoa = _some_address("eoa-governor")
        self.chain.set(COMET, "governor", eoa)
        self.chain.set(COMP_PROXY_ADMIN, "owner", eoa)
        self.chain.set(COMP_CONFIGURATOR, "governor", eoa)
        self.assertScores(self.run_scorer(), 20, 20, 0, 14)  # Fixed 2026-09-20

    def test_comet_governor_is_a_safe_is_not_credited_as_the_delayed_dao_root(self):
        # A Safe root would answer getOwners()/getThreshold(), but has no delay()/admin()/proposalCount().
        safe = _some_address("safe-governor")
        self.chain.set(COMET, "governor", safe)
        self.chain.set(COMP_PROXY_ADMIN, "owner", safe)
        self.chain.set(COMP_CONFIGURATOR, "governor", safe)
        self.chain.set_safe(safe, _owners(9), 5)
        self.assertScores(self.run_scorer(), 20, 20, 0, 14)  # Fixed 2026-09-20


class TestCompoundV3CusdcGovernorTracing(_ScorerCase):
    def build_chain(self):
        return _compound_chain()

    def run_scorer(self):
        return scorers.score_compound_v3_cusdc(FakeW3())

    def test_timelock_admin_unread_degrades_admin_key_and_multisig(self):
        self.chain.unset(COMP_TIMELOCK, "admin")
        result = self.run_scorer()
        self.assertScores(result, 20, 20, 60, 32)  # root not confirmed (multisig 20): 8 + 6 + 18 = 32 -> 32.5 -> 32
        self.assertNote(result, "CompoundGovernor.proposalCount() = None")
        self.assertEqual(self.calls_named("proposalCount"), [])

    def test_proposal_count_unread_degrades_admin_key_and_multisig(self):
        self.chain.unset(COMP_GOVERNOR, "proposalCount")
        self.assertScores(self.run_scorer(), 20, 20, 60, 32)  # root not confirmed (multisig 20): 8 + 6 + 18 = 32 -> 32.5 -> 32

    def test_proposal_count_zero_is_a_dormant_governor_and_degrades_admin_key_and_multisig(self):
        # PROBE proposalCount 0. 0 is falsy: a governor that never ran a proposal is not "real, active DAO
        # (600+ proposals)". HAND (root not confirmed, multisig 20): 8 + 6 + 18 = 32 -> 32.5 -> 32.
        self.chain.set(COMP_GOVERNOR, "proposalCount", 0)
        result = self.run_scorer()
        self.assertScores(result, 20, 20, 60, 32)  # root not confirmed (multisig 20): 8 + 6 + 18 = 32 -> 32.5 -> 32
        self.assertNote(result, "CompoundGovernor.proposalCount() = 0")

    def test_a_single_proposal_is_enough_for_the_admin_key_credit(self):
        # CHARACTERISATION (PROBE proposalCount = 1): the gate is truthiness, not a threshold; the docstring's
        # "600+" is a description of the observed 608, not a rule.
        self.chain.set(COMP_GOVERNOR, "proposalCount", 1)
        self.assertScores(self.run_scorer(), 78, 100, 60, 79)


class TestCompoundV3CusdcUpgradePathCrossChecks(_ScorerCase):
    """Three sources must agree on one root: Comet.governor(), CometProxyAdmin.owner() and
    Configurator.governor()."""

    def build_chain(self):
        return _compound_chain()

    def run_scorer(self):
        return scorers.score_compound_v3_cusdc(FakeW3())

    def test_proxy_admin_owned_by_another_address_degrades_admin_key_and_multisig(self):
        other = _some_address("other-proxy-owner")
        self.chain.set(COMP_PROXY_ADMIN, "owner", other)
        result = self.run_scorer()
        self.assertScores(result, 20, 20, 60, 32)  # root not confirmed (multisig 20): 8 + 6 + 18 = 32 -> 32.5 -> 32
        self.assertNote(result, f"CometProxyAdmin.owner() = {other}")

    def test_proxy_admin_owner_unread_degrades_admin_key_and_multisig(self):
        self.chain.unset(COMP_PROXY_ADMIN, "owner")
        result = self.run_scorer()
        self.assertScores(result, 20, 20, 60, 32)  # root not confirmed (multisig 20): 8 + 6 + 18 = 32 -> 32.5 -> 32
        self.assertNote(result, "CometProxyAdmin.owner() = None")

    def test_configurator_governed_by_another_address_degrades_admin_key_and_multisig(self):
        other = _some_address("other-configurator-governor")
        self.chain.set(COMP_CONFIGURATOR, "governor", other)
        result = self.run_scorer()
        self.assertScores(result, 20, 20, 60, 32)  # root not confirmed (multisig 20): 8 + 6 + 18 = 32 -> 32.5 -> 32
        self.assertNote(result, f"Configurator.governor() = {other}")

    def test_configurator_governor_unread_degrades_admin_key_and_multisig(self):
        self.chain.unset(COMP_CONFIGURATOR, "governor")
        self.assertScores(self.run_scorer(), 20, 20, 60, 32)  # root not confirmed (multisig 20): 8 + 6 + 18 = 32 -> 32.5 -> 32

    def test_both_paths_off_the_timelock_is_still_a_single_degradation_to_20(self):
        self.chain.set(COMP_PROXY_ADMIN, "owner", _some_address("a"))
        self.chain.set(COMP_CONFIGURATOR, "governor", _some_address("b"))
        self.assertScores(self.run_scorer(), 20, 20, 60, 32)  # root not confirmed (multisig 20): 8 + 6 + 18 = 32 -> 32.5 -> 32

    def test_case_differences_between_the_three_sources_still_agree(self):
        # RPCs return checksummed addresses, other sources lower-case them; _same() compares lower-cased.
        self.chain.set(COMP_PROXY_ADMIN, "owner", COMP_TIMELOCK.lower())
        self.chain.set(COMP_CONFIGURATOR, "governor", COMP_TIMELOCK.upper().replace("0X", "0x"))
        self.assertScores(self.run_scorer(), 78, 100, 60, 79)


class TestCompoundV3CusdcPauseGuardian(_ScorerCase):
    def build_chain(self):
        return _compound_chain()

    def run_scorer(self):
        return scorers.score_compound_v3_cusdc(FakeW3())

    def test_pause_guardian_unread_degrades_admin_key_and_multisig_and_says_so(self):
        self.chain.unset(COMET, "pauseGuardian")
        result = self.run_scorer()
        self.assertScores(result, 20, 20, 60, 32)  # root not confirmed (multisig 20): 8 + 6 + 18 = 32 -> 32.5 -> 32
        self.assertNote(result, "Comet.pauseGuardian() = None: NOT resolved as a Safe this run")
        self.assertEqual(self.chain.safe_calls, [])  # a None guardian is never handed to the Safe helper

    def test_pause_guardian_that_is_a_bare_eoa_is_not_an_identified_safe(self):
        eoa = _some_address("eoa-guardian")
        self.chain.set(COMET, "pauseGuardian", eoa)  # no Safe entry: getOwners()/getThreshold() revert
        result = self.run_scorer()
        self.assertScores(result, 20, 20, 60, 32)  # root not confirmed (multisig 20): 8 + 6 + 18 = 32 -> 32.5 -> 32
        self.assertNote(result, f"Comet.pauseGuardian() = {eoa}: NOT resolved as a Safe this run")

    def test_pause_guardian_safe_read_fails_after_retries_degrades_admin_key_and_multisig(self):
        self.chain.unset_safe(COMP_PAUSE_GUARDIAN)  # a transient failure surviving every retry reads as None
        self.assertScores(self.run_scorer(), 20, 20, 60, 32)  # root not confirmed (multisig 20): 8 + 6 + 18 = 32 -> 32.5 -> 32

    def test_guardian_safe_shape_appears_in_the_note_as_threshold_of_owners(self):
        self.chain.set_safe(COMP_PAUSE_GUARDIAN, _owners(7), 4)
        self.assertNote(self.run_scorer(), "real Gnosis Safe 4-of-7")

    def test_guardian_safe_threshold_is_disclosed_in_the_note_but_not_scored(self):
        # CHARACTERISATION (PROBE 1-of-9): a Safe that can pause withdrawals instantly earns the same 78 as the
        # observed 5-of-9. Not a scorer defect against a written rule: the scorer's own comment says "same
        # convention as Aave's 78", and score_aave_v3_pool reads the guardian Safe's threshold only for
        # `is not None`, so the two scorers agree. The docstring calls the seat "an identified Safe"; only the
        # fact that it resolves as a Safe is read into the score. Worth a rubric decision, see findings.
        self.chain.set_safe(COMP_PAUSE_GUARDIAN, _owners(9), 1)
        result = self.run_scorer()
        self.assertScores(result, 78, 100, 60, 79)
        self.assertNote(result, "real Gnosis Safe 1-of-9")


class TestCompoundV3CusdcTimelockDelay(_ScorerCase):
    def build_chain(self):
        return _compound_chain()

    def run_scorer(self):
        return scorers.score_compound_v3_cusdc(FakeW3())

    def test_delay_unread_degrades_timelock_score_only(self):
        self.chain.unset(COMP_TIMELOCK, "delay")
        result = self.run_scorer()
        self.assertScores(result, 78, 100, 0, 61)  # 31.2 + 30 + 0 = 61.2 -> 61.7 -> 61
        self.assertNote(result, "Timelock.delay() = unread")  # Fixed 2026-09-20
        self.assertNote(result, "Timelock.delay() unread or below 2 days this run -- timelockScore degraded")
        self.assertNoNote(result, "adminKeyScore degraded")

    def test_delay_one_second_below_two_days_gets_no_credit(self):
        # PROBE delay 172799s (code rule `delay >= 172800`). HAND: 31.2 + 30 + 0 = 61.2 -> 61.7 -> 61.
        self.chain.set(COMP_TIMELOCK, "delay", 172799)
        self.assertScores(self.run_scorer(), 78, 100, 0, 61)

    def test_delay_of_zero_is_read_as_a_real_value_and_gets_no_credit(self):
        # PROBE delay 0: 0 is not None, so this is "no delay", not "unread"
        self.chain.set(COMP_TIMELOCK, "delay", 0)
        result = self.run_scorer()
        self.assertScores(result, 78, 100, 0, 61)
        self.assertNote(result, "Timelock.delay() = 0s")

    def test_delay_of_exactly_two_days_is_the_published_60(self):
        self.chain.set(COMP_TIMELOCK, "delay", 172800)
        self.assertScores(self.run_scorer(), 78, 100, 60, 79)

    def test_a_delay_longer_than_two_days_keeps_the_same_capped_60(self):
        # PROBE delay 7 days (code rule "delay >= 172800 -> 60"): the cap is below Uniswap's 75 because a Safe can
        # freeze withdrawals instantly (docstring, "Bypass found and disclosed"), whatever the delay length.
        self.chain.set(COMP_TIMELOCK, "delay", 7 * 86400)
        self.assertScores(self.run_scorer(), 78, 100, 60, 79)

    def test_admin_and_timelock_degrade_independently_to_the_floor(self):
        self.chain.unset(COMP_TIMELOCK, "delay")
        self.chain.unset(COMP_PROXY_ADMIN, "owner")
        self.assertScores(self.run_scorer(), 20, 20, 0, 14)  # Fixed 2026-09-20

    def test_minimum_delay_is_disclosed_in_the_notes_but_not_scored(self):
        # CHARACTERISATION (PROBE MINIMUM_DELAY unread): the docstring says MINIMUM_DELAY = 172,800s "so the delay
        # cannot be lowered below 2 days" and the timelock comment says "a 2-day floor", but only delay() feeds
        # the score. No written rule in METHODOLOGY.md requires the floor to be read, so this is pinned, not
        # marked expectedFailure; see findings.
        self.chain.unset(COMP_TIMELOCK, "MINIMUM_DELAY")
        result = self.run_scorer()
        self.assertScores(result, 78, 100, 60, 79)
        self.assertNote(result, "MINIMUM_DELAY = unread")

    def test_a_low_minimum_delay_is_also_not_scored(self):
        # CHARACTERISATION (PROBE MINIMUM_DELAY = 1s), same as above.
        self.chain.set(COMP_TIMELOCK, "MINIMUM_DELAY", 1)
        self.assertScores(self.run_scorer(), 78, 100, 60, 79)


class TestCompoundV3CusdcTotalOutage(_ScorerCase):
    def build_chain(self):
        return FakeChain()  # every read reverts

    def test_nothing_readable_returns_the_documented_floor_without_raising(self):
        result = scorers.score_compound_v3_cusdc(FakeW3())
        # multisigScore is the unconfirmed-root floor 20 here: 100 ("not applicable") is reserved for a confirmed DAO+Timelock root.
        self.assertScores(result, 20, 20, 0, 14)  # Fixed 2026-09-20
        self.assertNote(result, "Comet.pauseGuardian() = None: NOT resolved as a Safe this run")
        self.assertNote(result, "adminKeyScore degraded")
        self.assertNote(result, "timelockScore degraded")
        self.assertEqual(result["_rootGroup"], "compound-l1-governance")


class TestCompoundV3CusdcIdentifiersAreOnlyIdentifiers(_ScorerCase):
    """COMP_GOVERNOR and COMP_PAUSE_GUARDIAN are IDENTIFIER-ONLY fixtures (documented in the repo only as a
    prefix / not at all, see the header): the score depends on what they resolve to, never on their value.
    Likewise the owner addresses of the guardian Safe (`_owners`) are placeholders: only their count is read."""

    def build_chain(self):
        return _compound_chain()

    def run_scorer(self):
        return scorers.score_compound_v3_cusdc(FakeW3())

    def test_the_governor_can_be_any_address_that_reads_as_an_active_dao(self):
        other = _some_address("compound-governor-b")
        self.chain.set(COMP_TIMELOCK, "admin", other)
        self.chain.set(other, "proposalCount", 608)
        result = self.run_scorer()
        self.assertScores(result, 78, 100, 60, 79)
        self.assertNote(result, f"Timelock.admin() = {other}")

    def test_the_pause_guardian_can_be_any_address_that_reads_as_a_safe(self):
        other = _some_address("compound-guardian-b")
        self.chain.set(COMET, "pauseGuardian", other)
        self.chain.set_safe(other, _owners(9), 5)
        self.assertScores(self.run_scorer(), 78, 100, 60, 79)

    def test_the_guardian_safe_signers_are_only_counted(self):
        self.chain.set_safe(COMP_PAUSE_GUARDIAN, _owners(9, start=500), 5)
        result = self.run_scorer()
        self.assertScores(result, 78, 100, 60, 79)
        self.assertNote(result, "real Gnosis Safe 5-of-9")


class TestSameHelper(unittest.TestCase):
    """scorers._same(a, b): 'both resolved and equal, ignoring case'. Its truthiness guard cannot be observed
    through score_compound_v3_cusdc, score_sparklend_pool, score_uniswap_v4_pool_manager or score_wbtc (every
    second operand there is a non-None constant, and an unread first hop already forces the degraded score), so
    it is pinned here directly. None == None reading as equal would let two unread reads pass for 'the upgrade
    path converges on the Timelock'."""

    def test_two_unread_values_are_not_the_same(self):
        self.assertFalse(scorers._same(None, None))

    def test_two_empty_strings_are_not_the_same(self):
        self.assertFalse(scorers._same("", ""))

    def test_an_unread_value_is_not_the_same_as_a_real_address_in_either_order(self):
        self.assertFalse(scorers._same(None, COMP_TIMELOCK))
        self.assertFalse(scorers._same(COMP_TIMELOCK, None))
        self.assertFalse(scorers._same("", COMP_TIMELOCK))
        self.assertFalse(scorers._same(COMP_TIMELOCK, ""))

    def test_one_address_in_two_spellings_is_the_same(self):
        self.assertTrue(scorers._same(COMP_TIMELOCK, COMP_TIMELOCK.lower()))
        self.assertTrue(scorers._same(COMP_TIMELOCK.lower(), COMP_TIMELOCK))

    def test_two_different_addresses_are_not_the_same(self):
        self.assertFalse(scorers._same(COMP_TIMELOCK, COMP_GOVERNOR))


# =========================================================================== SparkLend
# Addresses. SPARK_PROVIDER: deploy/README.md row 10. SPARK_PROXY: docstring "SPARK_PROXY 0x3300f198...",
# full address and its real 2,085-byte SubProxy bytecode in data/scored_targets_2026-09-15-batch6.md.
# ACL/PAUSE_PROXY/FREEZER_*: docstring prefixes 0xdA135Cd7 / 0xBE8E3e36 / 0x237e3985 / 0x44efFc47, full
# values from the scorer body. MCD_PAUSE: deploy/README.md row 2 (the Maker target this one shares a root
# with).
SPARK_PROVIDER = "0x02C3eA4e34C0cBd694D2adFa2c690EECbC1793eE"
SPARK_ACL = "0xdA135Cd78A086025BcdC87B038a1C462032b510C"
SPARK_PROXY = "0x3300f198988e4C9C63F75dF86De36421f06af8c4"
MCD_PAUSE_PROXY = "0xBE8E3e3618f7474F8cB1d074A26afFef007E98FB"
MCD_PAUSE = "0xbE286431454714F511008713973d3B053A2d38f3"
FREEZER_MOM = "0x237e3985dD7E373F2ec878EC1Ac48A228Cf2e7a3"
FREEZER_MULTISIG = "0x44efFc473e81632B12486866AA1678edbb7BEeC3"
DEFAULT_ADMIN_ROLE = b"\x00" * 32  # OpenZeppelin AccessControl's DEFAULT_ADMIN_ROLE


def _checksum(address):
    return RealWeb3.to_checksum_address(address)


def _spark_chain():
    """Reads documented in the scorer docstring and maintenance_2026-09-19.md section (b): SparkProxy holds
    DEFAULT_ADMIN on the ACLManager, wards(MCD_PAUSE_PROXY) = 1, MCD_PAUSE_PROXY.owner() = MCD_PAUSE with
    delay() 2 days, FreezerMom wards the SPARKLEND_FREEZER_MULTISIG, a 3-of-5 Safe."""
    chain = FakeChain()
    chain.set(SPARK_PROVIDER, "owner", SPARK_PROXY)
    chain.set(SPARK_ACL, "hasRole", True, DEFAULT_ADMIN_ROLE, _checksum(SPARK_PROXY))
    chain.set(SPARK_PROXY, "wards", 1, _checksum(MCD_PAUSE_PROXY))
    chain.set(MCD_PAUSE_PROXY, "owner", MCD_PAUSE)
    chain.set(MCD_PAUSE, "delay", 172800)
    chain.set(FREEZER_MOM, "wards", 1, _checksum(FREEZER_MULTISIG))
    chain.set_safe(FREEZER_MULTISIG, _owners(5), 3)
    return chain


class TestSparkLendPublishedRow(_ScorerCase):
    def build_chain(self):
        return _spark_chain()

    def run_scorer(self):
        return scorers.score_sparklend_pool(FakeW3())

    def test_reproduces_the_published_sub_scores_and_composite(self):
        # PUBLISHED deploy/README.md row 10: 75 / 100 / 60 / oracle 100 / composite 78 (HAND: 30+30+18 = 78 -> 78)
        self.assertScores(self.run_scorer(), 75, 100, 60, 78)
        self.assertEqual(self.chain.rejected, [])  # every argument was one the real web3 encoder accepts

    def test_the_composite_comes_from_the_shared_helper_fed_admin_multisig_timelock_in_that_order(self):
        # White-box, see _spy_on_composite: (75, 100, 60) HAND-derived above; 100 and 60 differ, so a swapped
        # order shows. Every reachable SparkLend composite is an exact integer (78, 60, 56, 38), so an inline
        # truncating formula would give the same numbers: only the helper call itself can be pinned.
        seen = _spy_on_composite(self)
        result = self.run_scorer()
        self.assertEqual(seen, [(75, 100, 60)])
        self.assertEqual(result["compositeScore"], 78)

    def test_target_label_and_root_group(self):
        result = self.run_scorer()
        self.assertEqual(result["target"], SPARK_PROVIDER)  # deploy/README.md row 10 address
        self.assertEqual(result["label"], "SparkLend (PoolAddressesProvider)")
        self.assertEqual(result["_rootGroup"], "makerdao-sky-governance")

    def test_notes_walk_the_authority_chain(self):
        result = self.run_scorer()
        self.assertNote(result, f"PoolAddressesProvider.owner() = {SPARK_PROXY} (SparkProxy)")
        self.assertNote(result, "ACLManager.hasRole(DEFAULT_ADMIN_ROLE, SparkProxy) = True")
        self.assertNote(result, "SparkProxy.wards(MCD_PAUSE_PROXY) = 1")
        self.assertNote(result, f"MCD_PAUSE_PROXY.owner() = {MCD_PAUSE} (expected MCD_PAUSE {MCD_PAUSE})")
        self.assertNote(result, "MCD_PAUSE.delay() = 172800s")

    def test_notes_carry_the_disclosed_instant_freeze_seat(self):
        result = self.run_scorer()
        self.assertNote(
            result,
            "FreezerMom.wards(SPARKLEND_FREEZER_MULTISIG) = 1 ; freezer multisig = 3-of-5 "
            "-- instant freeze/pause seat (no delay)",
        )
        self.assertNoNote(result, "degraded")

    def test_asks_the_acl_manager_about_default_admin_role_for_the_checksummed_spark_proxy(self):
        # On its own this cannot see the scorer's w3.to_checksum_address (the fixture's owner() is already
        # EIP-55); test_a_lower_case_owner_is_checksummed_before_it_becomes_a_call_argument is the one that can.
        self.run_scorer()
        (call,) = self.calls_named("hasRole")
        self.assertEqual(call[0].lower(), SPARK_ACL.lower())
        self.assertEqual(call[2], (DEFAULT_ADMIN_ROLE, _checksum(SPARK_PROXY)))

    def test_a_lower_case_owner_is_checksummed_before_it_becomes_a_call_argument(self):
        # PROBE: web3 decodes owner() as EIP-55, so a lower-case owner never reaches the scorer on mainnet; this
        # pins the scorer's own defensive w3.to_checksum_address. FakeChain runs the real web3 7.x encoder, which
        # refuses a non-EIP-55 address argument (InvalidAddress) exactly as it does in production, where the real
        # call_raw swallows that and returns None, degrading adminKeyScore 75 -> 20 without any error.
        self.chain.set(SPARK_PROVIDER, "owner", SPARK_PROXY.lower())
        result = self.run_scorer()
        self.assertScores(result, 75, 100, 60, 78)  # PUBLISHED row 10, unchanged
        self.assertEqual(self.chain.rejected, [])
        (call,) = self.calls_named("hasRole")
        self.assertEqual(call[2], (DEFAULT_ADMIN_ROLE, _checksum(SPARK_PROXY)))

    def test_every_address_argument_goes_through_the_injected_w3_normaliser(self):
        # WHITE-BOX wiring test. The constants MCD_PAUSE_PROXY and SPARKLEND_FREEZER_MULTISIG are already EIP-55
        # in the scorer, so dropping the w3.to_checksum_address around them changes no output and no fake can
        # tell; the only observable is that the injected `w3` was asked to normalise them. The point is that a
        # future edit of either constant to a non-EIP-55 spelling keeps working instead of degrading silently.
        w3 = RecordingW3()
        scorers.score_sparklend_pool(w3)
        self.assertLessEqual(
            {SPARK_PROXY.lower(), MCD_PAUSE_PROXY.lower(), FREEZER_MULTISIG.lower()},
            {a.lower() for a in w3.checksummed},
        )

    def test_asks_spark_proxy_about_the_mcd_pause_proxy_and_freezer_mom_about_the_multisig(self):
        self.run_scorer()
        ward_calls = {(c[0].lower(), c[2]) for c in self.calls_named("wards")}
        self.assertEqual(ward_calls, {
            (SPARK_PROXY.lower(), (_checksum(MCD_PAUSE_PROXY),)),
            (FREEZER_MOM.lower(), (_checksum(FREEZER_MULTISIG),)),
        })

    def test_constants_match_the_prefixes_the_docstring_documents(self):
        self.run_scorer()
        touched = {c[0].lower() for c in self.chain.calls}
        for prefix in ("0x02c3ea4e", "0xda135cd7", "0xbe8e3e36", "0x237e3985"):
            self.assertTrue(any(a.startswith(prefix) for a in touched), prefix)
        self.assertEqual([a.lower()[:10] for a in self.chain.safe_calls], ["0x44effc47"])

    def test_the_mcd_pause_read_is_the_contract_the_maker_scorer_scores(self):
        # The docstring: "MCD_PAUSE ... the 2-day-delay target already scored in score_makerdao_sky_pause()".
        # Both sides are pinned to the literal address of deploy/README.md row 2 (MakerDAO / Sky MCD_PAUSE), not
        # compared with each other's output. The Maker fixture's DSChief and spell are placeholder identifiers:
        # score_makerdao_sky_pause only tests `hat is not None and done is not None` (its docstring documents
        # hat() = an executed spell, done() = true; the real addresses are not in the repo).
        readme_row_2_address = "0xbe286431454714f511008713973d3b053a2d38f3"
        self.run_scorer()
        (delay_call,) = self.calls_named("delay")
        self.assertEqual(delay_call[0].lower(), readme_row_2_address)
        dschief, spell = _some_address("dschief"), _some_address("hat-spell")
        self.chain.set(MCD_PAUSE, "authority", dschief)
        self.chain.set(dschief, "hat", spell)
        self.chain.set(spell, "done", True)
        maker = scorers.score_makerdao_sky_pause(FakeW3())
        self.assertEqual(maker["target"].lower(), readme_row_2_address)


class TestSparkLendRootChain(_ScorerCase):
    def build_chain(self):
        return _spark_chain()

    def run_scorer(self):
        return scorers.score_sparklend_pool(FakeW3())

    def test_provider_owner_unread_scores_the_unresolved_floor_and_skips_the_dependent_reads(self):
        self.chain.unset(SPARK_PROVIDER, "owner")
        result = self.run_scorer()
        # Fixed 2026-09-20: timelock credit now requires root_resolved, not just readable delay
        # HAND: 8 + 6 + 0 = 14 -> 14.5 -> 14
        self.assertScores(result, 20, 20, 0, 14)
        self.assertNote(result, "PoolAddressesProvider.owner() = None (SparkProxy)")
        self.assertNote(result, "ACLManager.hasRole(DEFAULT_ADMIN_ROLE, SparkProxy) = None")
        self.assertNote(result, "SparkProxy.wards(MCD_PAUSE_PROXY) = None")
        self.assertNote(result, "did not fully resolve this run -- adminKeyScore degraded")
        self.assertEqual(self.calls_named("hasRole"), [])

    def test_owner_replaced_by_a_bare_eoa_is_not_a_root_the_scorer_can_trace(self):
        eoa = _some_address("eoa-owner")
        self.chain.set(SPARK_PROVIDER, "owner", eoa)  # no hasRole/wards entries: an EOA answers neither
        self.assertEqual(self.run_scorer()["adminKeyScore"], 20)

    def test_owner_replaced_by_a_safe_is_not_a_root_the_scorer_can_trace(self):
        safe = _some_address("safe-owner")
        self.chain.set(SPARK_PROVIDER, "owner", safe)
        self.chain.set_safe(safe, _owners(5), 3)
        self.assertEqual(self.run_scorer()["adminKeyScore"], 20)

    def test_new_owner_that_does_not_hold_default_admin_role_degrades(self):
        other = _some_address("new-owner")
        self.chain.set(SPARK_PROVIDER, "owner", other)
        self.chain.set(SPARK_ACL, "hasRole", False, DEFAULT_ADMIN_ROLE, _checksum(other))
        self.chain.set(other, "wards", 1, _checksum(MCD_PAUSE_PROXY))  # even with the ward, the role is missing
        result = self.run_scorer()
        self.assertEqual(result["adminKeyScore"], 20)
        self.assertNote(result, "ACLManager.hasRole(DEFAULT_ADMIN_ROLE, SparkProxy) = False")

    def test_default_admin_role_read_false_degrades_admin_key_multisig_and_timelock(self):
        self.chain.set(SPARK_ACL, "hasRole", False, DEFAULT_ADMIN_ROLE, _checksum(SPARK_PROXY))
        self.assertScores(self.run_scorer(), 20, 20, 0, 14)  # Fixed 2026-09-20

    def test_default_admin_role_read_unread_degrades_admin_key_multisig_and_timelock(self):
        self.chain.unset(SPARK_ACL, "hasRole", DEFAULT_ADMIN_ROLE, _checksum(SPARK_PROXY))
        result = self.run_scorer()
        self.assertScores(result, 20, 20, 0, 14)  # Fixed 2026-09-20
        self.assertNote(result, "ACLManager.hasRole(DEFAULT_ADMIN_ROLE, SparkProxy) = None")

    def test_mcd_pause_proxy_not_a_ward_of_spark_proxy_degrades_admin_key_multisig_and_timelock(self):
        self.chain.set(SPARK_PROXY, "wards", 0, _checksum(MCD_PAUSE_PROXY))
        result = self.run_scorer()
        self.assertScores(result, 20, 20, 0, 14)  # Fixed 2026-09-20
        self.assertNote(result, "SparkProxy.wards(MCD_PAUSE_PROXY) = 0")

    def test_ward_unread_degrades_admin_key_multisig_and_timelock(self):
        self.chain.unset(SPARK_PROXY, "wards", _checksum(MCD_PAUSE_PROXY))
        self.assertScores(self.run_scorer(), 20, 20, 0, 14)  # Fixed 2026-09-20

    def test_a_wards_value_other_than_one_is_not_a_ward(self):
        # PROBE: Sky's auth `wards` mapping holds 0 or 1 (rely/deny), and the scorer requires exactly 1; any other
        # value is read as "not a ward". HAND: 8 + 6 + 0 = 14 -> 14.5 -> 14. CHARACTERISATION of a strict
        # equality the docstring does not spell out ("wards ... rely/deny replay"). Fixed 2026-09-20
        self.chain.set(SPARK_PROXY, "wards", 2, _checksum(MCD_PAUSE_PROXY))
        result = self.run_scorer()
        self.assertScores(result, 20, 20, 0, 14)
        self.assertNote(result, "SparkProxy.wards(MCD_PAUSE_PROXY) = 2")
        self.assertNote(result, "did not fully resolve this run -- adminKeyScore degraded")


class TestSparkLendPauseProxyCrossCheck(_ScorerCase):
    """MCD_PAUSE_PROXY.owner() is a second source for 'this root is Sky governance': it has to name MCD_PAUSE,
    the contract whose delay() is then read."""

    def build_chain(self):
        return _spark_chain()

    def run_scorer(self):
        return scorers.score_sparklend_pool(FakeW3())

    def test_pause_proxy_owned_by_another_contract_degrades_admin_key_multisig_and_timelock(self):
        other = _some_address("not-mcd-pause")
        self.chain.set(MCD_PAUSE_PROXY, "owner", other)
        result = self.run_scorer()
        self.assertScores(result, 20, 20, 0, 14)  # Fixed 2026-09-20
        self.assertNote(result, f"MCD_PAUSE_PROXY.owner() = {other}")

    def test_pause_proxy_owner_unread_degrades_admin_key_multisig_and_timelock(self):
        self.chain.unset(MCD_PAUSE_PROXY, "owner")
        self.assertScores(self.run_scorer(), 20, 20, 0, 14)  # Fixed 2026-09-20

    def test_pause_proxy_owner_in_another_case_still_matches(self):
        self.chain.set(MCD_PAUSE_PROXY, "owner", MCD_PAUSE.lower())
        self.assertScores(self.run_scorer(), 75, 100, 60, 78)


class TestSparkLendDelayAndFreezeSeat(_ScorerCase):
    def build_chain(self):
        return _spark_chain()

    def run_scorer(self):
        return scorers.score_sparklend_pool(FakeW3())

    def test_delay_unread_degrades_timelock_score_only(self):
        self.chain.unset(MCD_PAUSE, "delay")
        result = self.run_scorer()
        self.assertScores(result, 75, 100, 0, 60)  # 30 + 30 + 0 = 60 -> 60.5 -> 60
        self.assertNote(result, "MCD_PAUSE.delay() = unread")
        self.assertNote(result, "MCD_PAUSE.delay() unread or below 2 days this run -- timelockScore degraded")
        self.assertNoNote(result, "adminKeyScore degraded")

    def test_delay_one_second_below_two_days_gets_no_credit(self):
        # PROBE delay 172799s (code rule `delay >= 172800`). HAND: 30 + 30 + 0 = 60 -> 60.5 -> 60.
        self.chain.set(MCD_PAUSE, "delay", 172799)
        self.assertScores(self.run_scorer(), 75, 100, 0, 60)

    def test_delay_of_zero_is_no_delay_not_unread(self):
        # PROBE delay 0: 0 is not None, so this is "no delay", not "unread".
        self.chain.set(MCD_PAUSE, "delay", 0)
        result = self.run_scorer()
        self.assertScores(result, 75, 100, 0, 60)
        self.assertNote(result, "MCD_PAUSE.delay() = 0s")

    def test_a_longer_delay_keeps_the_same_capped_60(self):
        # PROBE delay 3 days: the 60 is a cap for the identified instant freeze seat, not a function of length.
        self.chain.set(MCD_PAUSE, "delay", 259200)
        self.assertScores(self.run_scorer(), 75, 100, 60, 78)

    def test_freezer_ward_unread_degrades_timelock_score_only(self):
        self.chain.unset(FREEZER_MOM, "wards", _checksum(FREEZER_MULTISIG))
        result = self.run_scorer()
        self.assertScores(result, 75, 100, 0, 60)
        self.assertNote(result, "FreezerMom.wards(SPARKLEND_FREEZER_MULTISIG) = None")
        self.assertNote(result, "FreezerMom ward unread this run -- timelockScore degraded")

    def test_freezer_ward_read_as_zero_still_counts_as_read(self):
        # CHARACTERISATION (PROBE wards = 0): only "was the ward read" gates the 60, the value is not looked at.
        # The instant seat also includes the Sky Chief's hat (docstring), which this scorer never reads either.
        # No written rule decides it (the scorer comment only says "capped ... for the identified instant
        # freeze/pause seat"), so it is pinned, not marked expectedFailure; see findings.
        self.chain.set(FREEZER_MOM, "wards", 0, _checksum(FREEZER_MULTISIG))
        result = self.run_scorer()
        self.assertScores(result, 75, 100, 60, 78)
        self.assertNote(result, "FreezerMom.wards(SPARKLEND_FREEZER_MULTISIG) = 0")

    def test_freezer_safe_unresolved_is_only_a_note(self):
        # CHARACTERISATION (PROBE freezer Safe unresolved): the 3-of-5 shape is disclosed, not scored.
        self.chain.unset_safe(FREEZER_MULTISIG)
        result = self.run_scorer()
        self.assertScores(result, 75, 100, 60, 78)
        self.assertNote(result, "freezer multisig = unresolved -- instant freeze/pause seat (no delay)")

    def test_freezer_safe_shape_is_rendered_as_threshold_of_owners(self):
        self.chain.set_safe(FREEZER_MULTISIG, _owners(7), 4)
        self.assertNote(self.run_scorer(), "freezer multisig = 4-of-7 -- instant freeze/pause seat")

    def test_freezer_safe_signers_are_only_counted(self):
        # `_owners` are placeholders (the real signer set is not a documented fixture): the shape in the note is
        # the threshold and the number of owners, whoever they are.
        self.chain.set_safe(FREEZER_MULTISIG, _owners(5, start=700), 3)
        result = self.run_scorer()
        self.assertScores(result, 75, 100, 60, 78)
        self.assertNote(result, "freezer multisig = 3-of-5 -- instant freeze/pause seat")

    def test_admin_and_timelock_degrade_independently_to_the_floor(self):
        self.chain.unset(MCD_PAUSE, "delay")
        self.chain.set(SPARK_PROXY, "wards", 0, _checksum(MCD_PAUSE_PROXY))
        self.assertScores(self.run_scorer(), 20, 20, 0, 14)  # Fixed 2026-09-20


class TestSparkLendTotalOutage(_ScorerCase):
    def build_chain(self):
        return FakeChain()

    def test_nothing_readable_returns_the_documented_floor_without_raising(self):
        result = scorers.score_sparklend_pool(FakeW3())
        # multisigScore is the unconfirmed-root floor 20 here: 100 ("not applicable") is reserved for a confirmed DAO+Timelock root.
        self.assertScores(result, 20, 20, 0, 14)  # Fixed 2026-09-20
        self.assertNote(result, "freezer multisig = unresolved")
        self.assertNote(result, "adminKeyScore degraded")
        self.assertNote(result, "timelockScore degraded")
        self.assertEqual(result["_rootGroup"], "makerdao-sky-governance")


# =========================================================================== Uniswap V4 PoolManager
# POOL_MANAGER: deploy/README.md row 11 (and the docstring). UNI_TIMELOCK: maintenance_2026-09-19.md section (a)
# table (`adapter.owner()` / `adapter.feeSetter()` = 0x1a9C8182C09F50C8318d769245beA52c32BE35BC, EIP-55 form).
# UNI_GOVERNOR: same table (GovernorBravo 0x408ED635...24C3), full value in
# data/rotation_audit_2026-09-19-robinhood-chain-index9.md and
# data/correction_2026-09-17-uniswap-testnet-oracle-sync.md. UNI_QUORUM: same table, quorumVotes() = 40M UNI
# (18 decimals). V4_FEE_ADAPTER is IDENTIFIER-ONLY: the docstring says "a V4FeeAdapter (Sourcify exact match)" and
# gives no address, the full value appears in the repo only in
# chains/ethereum-l1/tests/test_new_targets_2026_09_19.py, and no score depends on it
# (TestUniswapV4PoolManagerIdentifiersAreOnlyIdentifiers proves it). UNI_TIMELOCK is deliberately NOT taken from
# scorers.UNISWAP_TIMELOCK, so a typo in that constant fails the happy path instead of being mirrored.
POOL_MANAGER = "0x000000000004444c5dc75cB358380D2e3dE08A90"
UNI_TIMELOCK = "0x1a9C8182C09F50C8318d769245beA52c32BE35BC"
UNI_GOVERNOR = "0x408ED6354d4973f66138C91495F2f2FCbd8724C3"
V4_FEE_ADAPTER = "0x89A5D5bF00a27D55c02951E49078a5C5771051dB"
UNI_QUORUM = 40_000_000 * 10**18  # maintenance_2026-09-19.md section (a): quorumVotes() = 40M UNI
# The disclosed limit of the fee path (score_uniswap_v4_pool_manager, "a second, undelayed fee authority"), as
# the note says it. Asserted positively in every test where the fee path lowers adminKeyScore.
FEE_PATH_DISCLOSURE = "a second, undelayed fee authority; adminKeyScore lowered"


def _v4_chain():
    """Reads documented in the docstring (live 2026-09-19): PoolManager.owner() = the Uniswap Governance
    Timelock directly, its protocolFeeController = a V4FeeAdapter whose owner() and feeSetter() are that same
    Timelock; Timelock delay() = 172,800s (2 days), admin() = GovernorBravo, quorumVotes() = 40M UNI."""
    chain = FakeChain()
    chain.set(POOL_MANAGER, "owner", UNI_TIMELOCK)
    chain.set(POOL_MANAGER, "protocolFeeController", V4_FEE_ADAPTER)
    chain.set(V4_FEE_ADAPTER, "owner", UNI_TIMELOCK)
    chain.set(V4_FEE_ADAPTER, "feeSetter", UNI_TIMELOCK)
    chain.set(UNI_TIMELOCK, "delay", 172800)
    chain.set(UNI_TIMELOCK, "admin", UNI_GOVERNOR)
    chain.set(UNI_GOVERNOR, "quorumVotes", UNI_QUORUM)
    return chain


class TestUniswapV4PoolManagerPublishedRow(_ScorerCase):
    def build_chain(self):
        return _v4_chain()

    def run_scorer(self):
        return scorers.score_uniswap_v4_pool_manager(FakeW3())

    def test_reproduces_the_published_sub_scores_and_composite(self):
        # PUBLISHED deploy/README.md row 11: 80 / 100 / 75 / oracle 100 / composite 85 (HAND: 32+30+22.5 = 84.5 -> 85)
        self.assertScores(self.run_scorer(), 80, 100, 75, 85)
        self.assertEqual(self.chain.rejected, [])  # every argument was one the real web3 encoder accepts

    def test_the_composite_comes_from_the_shared_helper_fed_admin_multisig_timelock_in_that_order(self):
        # White-box, see _spy_on_composite: (80, 100, 75) HAND-derived above; 100 and 75 differ, so a swapped
        # order shows. (The 84.5 boundary already distinguishes this scorer from an inline truncating formula.)
        seen = _spy_on_composite(self)
        result = self.run_scorer()
        self.assertEqual(seen, [(80, 100, 75)])
        self.assertEqual(result["compositeScore"], 85)

    def test_target_label_and_root_group(self):
        result = self.run_scorer()
        self.assertEqual(result["target"], POOL_MANAGER)  # deploy/README.md row 11 address
        self.assertEqual(result["label"], "Uniswap V4 PoolManager")
        self.assertEqual(result["_rootGroup"], "uniswap-l1-governance")

    def test_confirmed_root_claims_the_cross_ecosystem_shared_root_and_names_it(self):
        # 2026-09-20: the same L1 Timelock roots tracked Uniswap targets on Arbitrum, Base, Robinhood Chain and Monad.
        result = self.run_scorer()
        self.assertIs(result["_crossEcosystem"], True)
        self.assertIn(scorers._UNISWAP_SHARED_ROOT_NOTE, result["notes"])

    def test_notes_walk_owner_fee_controller_delay_governor_and_quorum(self):
        result = self.run_scorer()
        self.assertNote(
            result,
            f"PoolManager.owner() = {UNI_TIMELOCK} (expected Uniswap Governance Timelock {UNI_TIMELOCK})")
        self.assertNote(
            result,
            f"protocolFeeController = {V4_FEE_ADAPTER} ; owner() = {UNI_TIMELOCK} ; feeSetter() = {UNI_TIMELOCK}")
        self.assertNote(
            result,
            f"Timelock.delay() = 172800s ; admin() = {UNI_GOVERNOR} ; GovernorBravo.quorumVotes() = {UNI_QUORUM}")
        self.assertNoNote(result, "degraded")
        self.assertNoNote(result, "lowered")

    def test_reads_the_canonical_pool_manager_and_the_documented_timelock_constant(self):
        self.run_scorer()
        self.assertEqual(self.chain.calls[0][0].lower(), "0x000000000004444c5dc75cb358380d2e3de08a90")  # README row 11
        self.assertEqual(scorers.UNISWAP_TIMELOCK.lower(), UNI_TIMELOCK.lower())  # maintenance_2026-09-19.md (a)

    def test_the_timelock_is_the_same_root_the_v3_scorer_reads(self):
        # docstring: "the exact root already scored for V3 in score_uniswap_v3_factory()" and "Same scoring as
        # V3; shares its root group with V3". Each side is pinned to its own PUBLISHED row (deploy/README.md rows
        # 0 and 11: 80 / 100 / 75 for both), not only compared with the other's output, so the two cannot regress
        # together unnoticed. V3's Factory.owner() = V3OpenFeeAdapter and adapter.owner() = the Timelock are from
        # maintenance_2026-09-19.md section (a).
        self.chain.set("0x1F98431c8aD98523631AE4a59f267346ea31F984", "owner", "0xf2371551Fe3937Db7c750f4DfABe5c2fFFdcBf5A")
        self.chain.set("0xf2371551Fe3937Db7c750f4DfABe5c2fFFdcBf5A", "owner", UNI_TIMELOCK)
        v3 = scorers.score_uniswap_v3_factory(FakeW3())
        v4 = self.run_scorer()
        self.assertEqual((v3["adminKeyScore"], v3["multisigScore"], v3["timelockScore"]), (80, 100, 75))
        self.assertEqual((v4["adminKeyScore"], v4["multisigScore"], v4["timelockScore"]), (80, 100, 75))
        self.assertEqual(v3["_rootGroup"], v4["_rootGroup"])
        self.assertEqual(v4["_rootGroup"], "uniswap-l1-governance")


class TestUniswapV4PoolManagerOwner(_ScorerCase):
    def build_chain(self):
        return _v4_chain()

    def run_scorer(self):
        return scorers.score_uniswap_v4_pool_manager(FakeW3())

    def test_owner_unread_degrades_to_the_floor_and_skips_the_dependent_reads(self):
        self.chain.unset(POOL_MANAGER, "owner")
        result = self.run_scorer()
        self.assertScores(result, 20, 20, 0, 14)  # 8 + 6 + 0 = 14 -> 14.5 -> 14  # Fixed 2026-09-20
        self.assertNote(result, "PoolManager.owner() = None")
        self.assertNote(result, "PoolManager.owner() is not the known Timelock or quorumVotes() unread")
        self.assertNote(result, "Timelock.delay() unread -- timelockScore degraded")
        for downstream in ("delay", "admin", "quorumVotes"):
            self.assertEqual(self.calls_named(downstream), [], downstream)

    def test_owner_is_a_bare_eoa_degrades_admin_key(self):
        eoa = _some_address("eoa-owner")
        self.chain.set(POOL_MANAGER, "owner", eoa)  # an EOA has no delay()/admin()
        result = self.run_scorer()
        self.assertScores(result, 20, 20, 0, 14)  # Fixed 2026-09-20
        self.assertNote(result, f"PoolManager.owner() = {eoa}")
        self.assertIs(result["_crossEcosystem"], False)  # an unconfirmed root never claims the shared root
        self.assertNotIn(scorers._UNISWAP_SHARED_ROOT_NOTE, result["notes"])

    def test_owner_is_a_safe_degrades_admin_key(self):
        safe = _some_address("safe-owner")
        self.chain.set(POOL_MANAGER, "owner", safe)
        self.chain.set_safe(safe, _owners(5), 3)
        self.assertEqual(self.run_scorer()["adminKeyScore"], 20)

    def test_owner_that_is_not_the_known_timelock_degrades_admin_key_even_with_a_healthy_fee_path(self):
        self.chain.set(POOL_MANAGER, "owner", _some_address("other-timelock"))
        result = self.run_scorer()
        self.assertEqual(result["adminKeyScore"], 20)  # not 60: the fee-path branch only runs under an 80
        self.assertNoNote(result, "second, undelayed fee authority")

    def test_owner_that_is_a_different_fully_readable_governor_is_still_not_the_known_timelock(self):
        # Fixed 2026-09-20: timelockScore now also requires owner to be the known Timelock,
        # not just a readable Timelock with delay >= 172800.
        # HAND: 8 + 6 + 0 = 14 -> 14.5 -> 14.
        other_timelock, other_governor = _some_address("look-alike-tl"), _some_address("look-alike-gov")
        self.chain.set(POOL_MANAGER, "owner", other_timelock)
        self.chain.set(other_timelock, "delay", 172800)
        self.chain.set(other_timelock, "admin", other_governor)
        self.chain.set(other_governor, "quorumVotes", UNI_QUORUM)
        result = self.run_scorer()
        self.assertScores(result, 20, 20, 0, 14)
        self.assertNote(result, "PoolManager.owner() is not the known Timelock")
        self.assertNote(result, "timelockScore degraded")

    def test_owner_in_another_case_still_matches_the_known_timelock(self):
        self.chain.set(POOL_MANAGER, "owner", UNI_TIMELOCK.lower())
        self.chain.set(UNI_TIMELOCK.lower(), "delay", 172800)
        self.chain.set(UNI_TIMELOCK.lower(), "admin", UNI_GOVERNOR)
        self.assertScores(self.run_scorer(), 80, 100, 75, 85)


class TestUniswapV4PoolManagerGovernor(_ScorerCase):
    def build_chain(self):
        return _v4_chain()

    def run_scorer(self):
        return scorers.score_uniswap_v4_pool_manager(FakeW3())

    def test_quorum_unread_degrades_admin_key_and_multisig(self):
        self.chain.unset(UNI_GOVERNOR, "quorumVotes")
        result = self.run_scorer()
        self.assertScores(result, 20, 20, 75, 37)  # root not confirmed (multisig 20): 8 + 6 + 22.5 = 36.5 -> 37.0 -> 37
        self.assertNote(result, "GovernorBravo.quorumVotes() = None")
        self.assertNote(result, "adminKeyScore degraded")

    def test_governor_unread_leaves_the_quorum_unread_and_degrades_admin_key_and_multisig(self):
        self.chain.unset(UNI_TIMELOCK, "admin")
        result = self.run_scorer()
        self.assertScores(result, 20, 20, 75, 37)  # root not confirmed (multisig 20): 8 + 6 + 22.5 = 36.5 -> 37.0 -> 37
        self.assertNote(result, "admin() = None ; GovernorBravo.quorumVotes() = None")
        self.assertEqual(self.calls_named("quorumVotes"), [])

    def test_a_quorum_of_zero_is_read_not_unread(self):
        # 0 is not None: the credit gate is "was quorumVotes() read", so this still earns the 80.
        self.chain.set(UNI_GOVERNOR, "quorumVotes", 0)
        self.assertScores(self.run_scorer(), 80, 100, 75, 85)


class TestUniswapV4PoolManagerFeePath(_ScorerCase):
    """protocolFeeController's owner() and feeSetter() are two more sources that must name the same Timelock."""

    def build_chain(self):
        return _v4_chain()

    def run_scorer(self):
        return scorers.score_uniswap_v4_pool_manager(FakeW3())

    def test_fee_setter_off_the_timelock_lowers_admin_key_to_60(self):
        other = _some_address("fee-setter-eoa")
        self.chain.set(V4_FEE_ADAPTER, "feeSetter", other)
        result = self.run_scorer()
        self.assertScores(result, 60, 100, 75, 77)  # 24 + 30 + 22.5 = 76.5 -> 77.0 -> 77
        self.assertNote(result, "protocolFeeController owner/feeSetter NOT the Timelock this run")
        self.assertNote(result, f"feeSetter() = {other}")
        # the disclosed limit itself, asserted positively (it was only ever asserted absent elsewhere):
        self.assertNote(result, FEE_PATH_DISCLOSURE)
        self.assertNoNote(result, "adminKeyScore degraded")  # lowered to 60, not degraded to 20

    def test_fee_controller_owner_off_the_timelock_lowers_admin_key_to_60(self):
        self.chain.set(V4_FEE_ADAPTER, "owner", _some_address("fee-owner-safe"))
        result = self.run_scorer()
        self.assertScores(result, 60, 100, 75, 77)
        self.assertNote(result, FEE_PATH_DISCLOSURE)

    def test_both_off_the_timelock_is_a_single_lowering_to_60(self):
        self.chain.set(V4_FEE_ADAPTER, "owner", _some_address("a"))
        self.chain.set(V4_FEE_ADAPTER, "feeSetter", _some_address("b"))
        result = self.run_scorer()
        self.assertScores(result, 60, 100, 75, 77)
        self.assertEqual(sum(FEE_PATH_DISCLOSURE in n for n in result["notes"]), 1)

    def test_fee_controller_unread_lowers_admin_key_to_60_and_skips_its_reads(self):
        self.chain.unset(POOL_MANAGER, "protocolFeeController")
        result = self.run_scorer()
        self.assertScores(result, 60, 100, 75, 77)
        self.assertNote(result, "protocolFeeController = None ; owner() = None ; feeSetter() = None")
        self.assertNote(result, FEE_PATH_DISCLOSURE)
        self.assertEqual(self.calls_named("feeSetter"), [])

    def test_fee_controller_owner_unread_lowers_admin_key_to_60(self):
        self.chain.unset(V4_FEE_ADAPTER, "owner")
        result = self.run_scorer()
        self.assertScores(result, 60, 100, 75, 77)
        self.assertNote(result, FEE_PATH_DISCLOSURE)

    def test_fee_controller_that_is_the_timelock_in_another_case_does_not_lower(self):
        self.chain.set(V4_FEE_ADAPTER, "owner", UNI_TIMELOCK.lower())
        self.chain.set(V4_FEE_ADAPTER, "feeSetter", UNI_TIMELOCK.lower())
        self.assertScores(self.run_scorer(), 80, 100, 75, 85)

    def test_fee_path_off_the_timelock_and_quorum_unread_is_the_lower_of_the_two_outcomes(self):
        self.chain.set(V4_FEE_ADAPTER, "feeSetter", _some_address("x"))
        self.chain.unset(UNI_GOVERNOR, "quorumVotes")
        result = self.run_scorer()
        self.assertEqual(result["adminKeyScore"], 20)  # not 60
        self.assertNoNote(result, FEE_PATH_DISCLOSURE)  # the fee-path branch only runs under an 80


class TestUniswapV4PoolManagerDelay(_ScorerCase):
    def build_chain(self):
        return _v4_chain()

    def run_scorer(self):
        return scorers.score_uniswap_v4_pool_manager(FakeW3())

    def test_delay_unread_degrades_timelock_score_only(self):
        self.chain.unset(UNI_TIMELOCK, "delay")
        result = self.run_scorer()
        self.assertScores(result, 80, 100, 0, 62)  # 32 + 30 + 0 = 62 -> 62.5 -> 62
        self.assertNote(result, "Timelock.delay() = unread")  # Fixed 2026-09-20
        self.assertNote(result, "Timelock.delay() unread -- timelockScore degraded")

    def test_a_delay_below_two_days_gets_no_timelock_credit(self):
        # CHARACTERISATION (PROBE delay = 3600s): the scorer now requires delay >= 172800 for timelock credit,
        # matching Compound and SparkLend. A delay below the floor gets no credit. HAND: 32 + 30 + 0 = 62.
        self.chain.set(UNI_TIMELOCK, "delay", 3600)
        result = self.run_scorer()
        self.assertScores(result, 80, 100, 0, 62)
        self.assertNote(result, "Timelock.delay() = 3600s is below 172800s floor")

    def test_a_delay_of_zero_is_read_as_a_real_value_and_gets_no_credit(self):
        # Fixed 2026-09-20
        self.chain.set(UNI_TIMELOCK, "delay", 0)
        result = self.run_scorer()
        self.assertScores(result, 80, 100, 0, 62)
        self.assertNote(result, "Timelock.delay() = 0s is below 172800s floor")

    def test_a_delay_below_floor_gets_no_credit_regardless_of_known_timelock(self):
        # Fixed 2026-09-20: confirmed real delay below 172800s gets no timelock credit
        # HAND: 8 + 6 + 0 = 14 -> 14.5 -> 14.
        other_timelock, other_governor = _some_address("look-alike-tl"), _some_address("look-alike-gov")
        self.chain.set(POOL_MANAGER, "owner", other_timelock)
        self.chain.set(other_timelock, "delay", 3600)
        self.chain.set(other_timelock, "admin", other_governor)
        self.chain.set(other_governor, "quorumVotes", UNI_QUORUM)
        result = self.run_scorer()
        self.assertScores(result, 20, 20, 0, 14)
        self.assertNote(result, "below 172800s floor")

    def test_admin_and_timelock_degrade_independently_to_the_floor(self):
        self.chain.unset(UNI_TIMELOCK, "delay")
        self.chain.unset(UNI_GOVERNOR, "quorumVotes")
        self.assertScores(self.run_scorer(), 20, 20, 0, 14)  # 8 + 6 + 0 = 14 -> 14.5 -> 14


class TestUniswapV4PoolManagerIdentifiersAreOnlyIdentifiers(_ScorerCase):
    """V4_FEE_ADAPTER is an IDENTIFIER-ONLY fixture (no address in the docstring, see the header): what the
    scorer reads is the adapter's owner() and feeSetter(), never its own address."""

    def build_chain(self):
        return _v4_chain()

    def run_scorer(self):
        return scorers.score_uniswap_v4_pool_manager(FakeW3())

    def test_the_fee_adapter_can_be_any_address_whose_owner_and_setter_are_the_timelock(self):
        other = _some_address("v4-fee-adapter-b")
        self.chain.set(POOL_MANAGER, "protocolFeeController", other)
        self.chain.set(other, "owner", UNI_TIMELOCK)
        self.chain.set(other, "feeSetter", UNI_TIMELOCK)
        result = self.run_scorer()
        self.assertScores(result, 80, 100, 75, 85)
        self.assertNote(result, f"protocolFeeController = {other} ;")


class TestUniswapV4PoolManagerTotalOutage(_ScorerCase):
    def build_chain(self):
        return FakeChain()

    def test_nothing_readable_returns_the_documented_floor_without_raising(self):
        result = scorers.score_uniswap_v4_pool_manager(FakeW3())
        # multisigScore is the unconfirmed-root floor 20 here: 100 ("not applicable") is reserved for a confirmed DAO+Timelock root.
        self.assertScores(result, 20, 20, 0, 14)  # Fixed 2026-09-20
        self.assertEqual(result["_rootGroup"], "uniswap-l1-governance")


# =========================================================================== WBTC
# WBTC: deploy/README.md row 13 (and the scorer body). WBTC_CONTROLLER / WBTC_MULTISIG: docstring "Controller
# (0xCA06411b...)" and "MultiSigWallet at 0x972Eed35..." (also maintenance_2026-09-19.md section (b), same
# prefixes). IDENTIFIER-ONLY: the full values appear in the repo only in
# chains/ethereum-l1/tests/test_new_targets_2026_09_19.py, the scorer reads them from the chain, and no score
# depends on their value (TestWbtcIdentifiersAreOnlyIdentifiers proves it; the only place the multisig prefix
# is code is the _rootGroup string "wbtc-multisigwallet-0x972eed35"). The docstring observations (OBSERVED
# 2026-09-19): Controller.token() points back at WBTC, MultiSigWallet.required() = 6, getOwners() = 10,
# getThreshold() reverts (a legacy Gnosis MultiSigWallet, not a Safe), dailyLimit() = 0, no timelock.
WBTC = "0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599"
WBTC_CONTROLLER = "0xCA06411bd7a7296d7dbdd0050DFc846E95fEBEB7"
WBTC_MULTISIG = "0x972Eed35781f09987a5c40F761f6A24623C570DE"


def _wbtc_chain(required=6, owner_count=10):
    chain = FakeChain()
    chain.set(WBTC, "owner", WBTC_CONTROLLER)
    chain.set(WBTC_CONTROLLER, "token", WBTC)
    chain.set(WBTC_CONTROLLER, "owner", WBTC_MULTISIG)
    chain.set(WBTC_MULTISIG, "required", required)
    chain.set(WBTC_MULTISIG, "getOwners", _owners(owner_count))
    return chain


class TestWbtcPublishedRow(_ScorerCase):
    def build_chain(self):
        return _wbtc_chain()

    def run_scorer(self):
        return scorers.score_wbtc(FakeW3())

    def test_reproduces_the_published_sub_scores_and_composite(self):
        # PUBLISHED deploy/README.md row 13: 55 / 100 / 0 / oracle 100 / composite 52 (HAND: 22+30+0 = 52 -> 52)
        self.assertScores(self.run_scorer(), 55, 100, 0, 52)
        self.assertEqual(self.chain.rejected, [])  # every argument was one the real web3 encoder accepts

    def test_the_composite_comes_from_the_shared_helper_fed_admin_multisig_timelock_in_that_order(self):
        # White-box, see _spy_on_composite: (55, 100, 0) HAND-derived above; 100 and 0 differ, so a swapped order
        # shows. The published row is not on a .5 boundary; the truncation case is TestWbtcThresholdRule's 5-of-9.
        seen = _spy_on_composite(self)
        result = self.run_scorer()
        self.assertEqual(seen, [(55, 100, 0)])
        self.assertEqual(result["compositeScore"], 52)

    def test_target_label_and_root_group(self):
        result = self.run_scorer()
        self.assertEqual(result["target"], WBTC)  # deploy/README.md row 13 address
        self.assertEqual(result["label"], "WBTC (Wrapped BTC)")
        self.assertEqual(result["_rootGroup"], "wbtc-multisigwallet-0x972eed35")

    def test_published_cross_exposure_is_100_because_no_other_target_shares_the_root(self):
        result = self.run_scorer()
        scorers._apply_cross_exposure([result])
        self.assertEqual(result["crossExposureScore"], 100)  # deploy/README.md row 13, cross column
        self.assertNotIn("_rootGroup", result)

    def test_published_multisig_100_is_the_cap_not_the_raw_sum(self):
        # 6-of-10: 6*15 + (10-6)*5 = 90 + 20 = 110, capped at 100. Six-of-six shows the uncapped side: 90.
        self.assertEqual(self.run_scorer()["multisigScore"], 100)
        self.chain.set(WBTC_MULTISIG, "getOwners", _owners(6))
        self.assertEqual(self.run_scorer()["multisigScore"], 90)

    def test_notes_record_the_controller_the_token_pointer_the_required_count_and_the_owner_count(self):
        result = self.run_scorer()
        self.assertNote(result, f"WBTC.owner() = {WBTC_CONTROLLER} (Controller) ; Controller.token() = {WBTC}")
        self.assertNote(result, f"Controller.owner() = {WBTC_MULTISIG} ; MultiSigWallet.required() = 6 ; owners = 10")
        self.assertNoNote(result, "degraded")

    def test_reads_the_legacy_multisig_interface_and_never_the_safe_helper(self):
        # docstring: "a legacy Gnosis MultiSigWallet (NOT a Gnosis Safe: getThreshold() reverts, required() = 6,
        # getOwners() = 10)"
        self.run_scorer()
        self.assertEqual(self.chain.safe_calls, [])
        self.assertEqual(self.calls_named("getThreshold"), [])
        self.assertEqual(len(self.calls_named("required")), 1)
        self.assertEqual(len(self.calls_named("getOwners")), 1)

    def test_reads_start_at_the_wbtc_token_address_published_in_the_readme(self):
        self.run_scorer()
        self.assertEqual(self.chain.calls[0][0].lower(), "0x2260fac5e5542a773aa44fbcfedf7c193bc2c599")
        self.assertEqual(self.chain.calls[0][1], "owner")

    def test_timelock_score_is_zero_because_no_delay_exists_anywhere_in_the_chain(self):
        self.assertEqual(self.run_scorer()["timelockScore"], 0)


class TestWbtcThresholdRule(_ScorerCase):
    """admin 55 when required() >= 3 else 20; multisig = min(100, required*15 + max(0, owners-required)*5)
    (METHODOLOGY.md 'What each dimension actually reads'). Every case except the observed 6-of-10 is a PROBE
    (an invented threshold and owner count); the expected values are HAND arithmetic, shown in each test."""

    def build_chain(self):
        return _wbtc_chain()

    def run_scorer(self):
        return scorers.score_wbtc(FakeW3())

    def _score_with(self, required, owner_count):
        self.chain.set(WBTC_MULTISIG, "required", required)
        self.chain.set(WBTC_MULTISIG, "getOwners", _owners(owner_count))
        return self.run_scorer()

    def test_three_of_ten_is_the_lowest_threshold_with_the_55(self):
        # multisig 3*15 + 7*5 = 45 + 35 = 80 ; 22 + 24 = 46 -> 46.5 -> 46
        self.assertScores(self._score_with(3, 10), 55, 80, 0, 46)

    def test_two_of_ten_falls_below_the_threshold_and_scores_20(self):
        # multisig 2*15 + 8*5 = 30 + 40 = 70 ; 8 + 21 = 29 -> 29.5 -> 29
        self.assertScores(self._score_with(2, 10), 20, 70, 0, 29)

    def test_one_of_ten_scores_20(self):
        # multisig 1*15 + 9*5 = 15 + 45 = 60 ; 8 + 18 = 26 -> 26.5 -> 26
        self.assertScores(self._score_with(1, 10), 20, 60, 0, 26)

    def test_six_of_six_is_the_uncapped_90(self):
        # multisig 6*15 + 0 = 90 ; 22 + 27 = 49 -> 49.5 -> 49
        self.assertScores(self._score_with(6, 6), 55, 90, 0, 49)

    def test_ten_of_ten_hits_the_100_cap(self):
        # multisig 10*15 = 150 -> min(100, 150) = 100
        self.assertScores(self._score_with(10, 10), 55, 100, 0, 52)

    def test_five_of_nine_lands_on_a_half_point_and_rounds_up(self):
        # PROBE 5-of-9 (a plausible multisig shape, not the observed 6-of-10): multisig
        # 5*15 + 4*5 = 75 + 20 = 95; HAND: 22 + 28.5 + 0 = 50.5 -> +0.5 = 51.0 -> 51. A truncating composite
        # gives 50; every other WBTC case here has a multisig score that is a multiple of 10, so 0.3*m is
        # integral and never reaches a .5. Anchored to the published rounding of the same multisig 95:
        # deploy/README.md row 12 (Morpho Blue Safe 5-of-9, 65 / 95 / 0: 26 + 28.5 = 54.5 -> 55).
        self.assertScores(self._score_with(5, 9), 55, 95, 0, 51)

    def test_more_required_than_owners_does_not_go_negative_on_the_owner_surplus(self):
        # PROBE, a misread that cannot occur on a real MultiSigWallet (6 required, only 5 owners):
        # max(0, 5-6) = 0, so multisig = 6*15 = 90, not 90-5
        self.assertScores(self._score_with(6, 5), 55, 90, 0, 49)

    def test_a_required_of_zero_is_read_not_unread(self):
        # PROBE: required() = 0 is a value, not None; the gate is `required is not None`. Unreachable on the real
        # wallet (the legacy Gnosis MultiSigWallet's validRequirement forbids 0), so this only pins the
        # None-versus-falsy distinction. HAND: admin 20 (0 < 3), multisig min(100, 0*15 + 10*5) = 50,
        # composite 8 + 15 + 0 = 23 -> 23.5 -> 23. A falsy gate would degrade it to 10 / 20 / 0 / 10 instead.
        result = self._score_with(0, 10)
        self.assertScores(result, 20, 50, 0, 23)
        self.assertNoNote(result, "degraded")

    def test_threshold_does_not_change_the_zero_timelock(self):
        for required in (1, 3, 6):
            self.assertEqual(self._score_with(required, 10)["timelockScore"], 0, required)


class TestWbtcUnresolved(_ScorerCase):
    """Anything in the WBTC -> Controller -> MultiSigWallet chain not resolving degrades to admin 10 /
    multisig 20 / timelock 0: 4 + 6 + 0 = 10 -> 10.5 -> 10."""

    def build_chain(self):
        return _wbtc_chain()

    def run_scorer(self):
        return scorers.score_wbtc(FakeW3())

    def assertDegraded(self, result):
        self.assertScores(result, 10, 20, 0, 10)
        self.assertNote(result, "Controller/multisig chain did not resolve this run -- scores degraded")

    def test_token_owner_unread_degrades_and_skips_every_dependent_read(self):
        self.chain.unset(WBTC, "owner")
        result = self.run_scorer()
        self.assertDegraded(result)
        self.assertNote(result, "WBTC.owner() = None (Controller) ; Controller.token() = None")
        self.assertNote(result, "Controller.owner() = None ; MultiSigWallet.required() = None ; owners = None")
        self.assertEqual(len(self.chain.calls), 1)  # only WBTC.owner() was attempted

    def test_controller_token_pointer_unread_degrades(self):
        self.chain.unset(WBTC_CONTROLLER, "token")
        self.assertDegraded(self.run_scorer())

    def test_controller_token_pointing_at_another_token_degrades(self):
        # cross-check of two sources: WBTC.owner() must be a Controller that points BACK at WBTC
        other_token = _some_address("another-token")
        self.chain.set(WBTC_CONTROLLER, "token", other_token)
        result = self.run_scorer()
        self.assertDegraded(result)
        self.assertNote(result, f"Controller.token() = {other_token}")

    def test_controller_token_pointer_in_another_case_still_matches(self):
        self.chain.set(WBTC_CONTROLLER, "token", WBTC.lower())
        self.assertScores(self.run_scorer(), 55, 100, 0, 52)

    def test_controller_owner_unread_degrades(self):
        self.chain.unset(WBTC_CONTROLLER, "owner")
        self.assertDegraded(self.run_scorer())

    def test_required_unread_degrades(self):
        self.chain.unset(WBTC_MULTISIG, "required")
        result = self.run_scorer()
        self.assertDegraded(result)
        self.assertNote(result, "MultiSigWallet.required() = None ; owners = 10")

    def test_owners_unread_degrades(self):
        self.chain.unset(WBTC_MULTISIG, "getOwners")
        result = self.run_scorer()
        self.assertDegraded(result)
        self.assertNote(result, "MultiSigWallet.required() = 6 ; owners = None")

    def test_an_empty_owner_list_degrades(self):
        self.chain.set(WBTC_MULTISIG, "getOwners", [])
        self.assertDegraded(self.run_scorer())

    def test_controller_owner_that_is_a_bare_eoa_degrades(self):
        # an EOA answers neither required() nor getOwners()
        eoa = _some_address("eoa-controller-owner")
        self.chain.set(WBTC_CONTROLLER, "owner", eoa)
        self.assertDegraded(self.run_scorer())

    def test_controller_owner_that_is_a_gnosis_safe_degrades_because_the_scorer_only_knows_the_legacy_wallet(self):
        # A Safe answers getOwners() (same selector) but has no required(): it reverts, so the read is None.
        safe = _some_address("safe-controller-owner")
        self.chain.set(WBTC_CONTROLLER, "owner", safe)
        self.chain.set(safe, "getOwners", _owners(9))
        self.chain.set_safe(safe, _owners(9), 5)
        self.assertDegraded(self.run_scorer())
        self.assertEqual(self.chain.safe_calls, [])  # the Safe helper is not consulted as a fallback

    def test_controller_owner_that_is_a_timelock_degrades(self):
        # a timelock-shaped owner answers delay(), not required()/getOwners()
        timelock = _some_address("timelock-controller-owner")
        self.chain.set(WBTC_CONTROLLER, "owner", timelock)
        self.chain.set(timelock, "delay", 172800)
        self.assertDegraded(self.run_scorer())

    def test_degraded_scores_do_not_depend_on_which_link_failed(self):
        for setup in (
            lambda c: c.unset(WBTC, "owner"),
            lambda c: c.unset(WBTC_CONTROLLER, "token"),
            lambda c: c.unset(WBTC_CONTROLLER, "owner"),
            lambda c: c.unset(WBTC_MULTISIG, "required"),
            lambda c: c.unset(WBTC_MULTISIG, "getOwners"),
        ):
            chain = _wbtc_chain()
            setup(chain)
            _patch_helpers(self, chain)
            result = scorers.score_wbtc(FakeW3())
            self.assertEqual(
                (result["adminKeyScore"], result["multisigScore"], result["timelockScore"], result["compositeScore"]),
                (10, 20, 0, 10),
            )


class TestWbtcIdentifiersAreOnlyIdentifiers(_ScorerCase):
    """WBTC_CONTROLLER and WBTC_MULTISIG are IDENTIFIER-ONLY fixtures (documented only as a prefix, see the
    header): the score comes from what the chain says the Controller and the wallet are, never from their
    address. The wallet's owner addresses (`_owners`) are placeholders: only their count is read."""

    def build_chain(self):
        return _wbtc_chain()

    def run_scorer(self):
        return scorers.score_wbtc(FakeW3())

    def test_controller_and_wallet_can_be_any_addresses_with_the_same_shape(self):
        controller, wallet = _some_address("wbtc-controller-b"), _some_address("wbtc-multisig-b")
        self.chain.set(WBTC, "owner", controller)
        self.chain.set(controller, "token", WBTC)
        self.chain.set(controller, "owner", wallet)
        self.chain.set(wallet, "required", 6)
        self.chain.set(wallet, "getOwners", _owners(10))
        result = self.run_scorer()
        self.assertScores(result, 55, 100, 0, 52)
        self.assertNote(result, f"WBTC.owner() = {controller} (Controller) ; Controller.token() = {WBTC}")

    def test_the_wallet_owners_are_only_counted(self):
        self.chain.set(WBTC_MULTISIG, "getOwners", _owners(10, start=900))
        result = self.run_scorer()
        self.assertScores(result, 55, 100, 0, 52)
        self.assertNote(result, "owners = 10")


class TestWbtcTotalOutage(_ScorerCase):
    def build_chain(self):
        return FakeChain()

    def test_nothing_readable_returns_the_documented_floor_without_raising(self):
        result = scorers.score_wbtc(FakeW3())
        self.assertScores(result, 10, 20, 0, 10)
        self.assertEqual(result["_rootGroup"], "wbtc-multisigwallet-0x972eed35")


# =========================================================================== cross-exposure of the four
class TestPublishedCrossExposureOfTheFour(unittest.TestCase):
    """deploy/README.md, "Current on-chain scores (re-push, 2026-09-20)": the cross column is 100 for Compound
    (row 9) and WBTC (row 13) and 80 for SparkLend (row 10) and Uniswap V4 (row 11); the two 80s come from sharing
    a root group with MakerDAO/Sky MCD_PAUSE (row 2, 80) and the Uniswap V3 Factory (row 0, 80) respectively.
    Here the real scorers of all six run together on one fake chain."""

    def setUp(self):
        # Maker fixture. OBSERVED (score_makerdao_sky_pause docstring): MCD_PAUSE.delay() = 172,800s, DSChief.hat()
        # = an executed spell, hat().done() = true. The DSChief and spell addresses are PLACEHOLDER identifiers:
        # the real ones are not in the repo, and the scorer only tests `hat is not None and done is not None`,
        # so the Maker row reproduces PUBLISHED row 2 (75 / 100 / 70 / composite 81; HAND 30 + 30 + 21 = 81 ->
        # 81.5 -> 81) from those documented reads alone, not from values tuned to the output.
        maker = FakeChain()
        maker.set(MCD_PAUSE, "delay", 172800)
        maker.set(MCD_PAUSE, "authority", _some_address("dschief"))
        maker.set(_some_address("dschief"), "hat", _some_address("hat-spell"))
        maker.set(_some_address("hat-spell"), "done", True)
        v3 = FakeChain()
        v3.set("0x1F98431c8aD98523631AE4a59f267346ea31F984", "owner", "0xf2371551Fe3937Db7c750f4DfABe5c2fFFdcBf5A")
        v3.set("0xf2371551Fe3937Db7c750f4DfABe5c2fFFdcBf5A", "owner", UNI_TIMELOCK)
        chain = _compound_chain().merged_with(_spark_chain(), maker, _v4_chain(), v3, _wbtc_chain())
        _patch_helpers(self, chain)
        w3 = FakeW3()
        self.results = [
            scorers.score_compound_v3_cusdc(w3),
            scorers.score_sparklend_pool(w3),
            scorers.score_makerdao_sky_pause(w3),
            scorers.score_uniswap_v3_factory(w3),
            scorers.score_uniswap_v4_pool_manager(w3),
            scorers.score_wbtc(w3),
        ]
        scorers._apply_cross_exposure(self.results)
        self.by_label = {r["label"]: r for r in self.results}

    def test_compound_and_wbtc_stand_alone_at_100(self):
        self.assertEqual(self.by_label["Compound V3 cUSDCv3 (Comet USDC)"]["crossExposureScore"], 100)
        self.assertEqual(self.by_label["WBTC (Wrapped BTC)"]["crossExposureScore"], 100)

    def test_sparklend_and_maker_share_the_sky_root_at_80(self):
        spark = self.by_label["SparkLend (PoolAddressesProvider)"]
        maker = self.by_label["MakerDAO / Sky governance (MCD_PAUSE)"]
        self.assertEqual(spark["crossExposureScore"], 80)
        self.assertEqual(maker["crossExposureScore"], 80)
        self.assertEqual((maker["adminKeyScore"], maker["multisigScore"], maker["timelockScore"], maker["compositeScore"]),
                         (75, 100, 70, 81))  # deploy/README.md row 2
        self.assertTrue(any("shares its root authority (makerdao-sky-governance) with 1 other" in n for n in spark["notes"]))

    def test_uniswap_v4_and_v3_share_the_timelock_root_at_80(self):
        v4 = self.by_label["Uniswap V4 PoolManager"]
        v3 = self.by_label["Uniswap V3 Factory"]
        self.assertEqual(v4["crossExposureScore"], 80)
        self.assertEqual(v3["crossExposureScore"], 80)
        self.assertEqual((v3["adminKeyScore"], v3["multisigScore"], v3["timelockScore"], v3["compositeScore"]),
                         (80, 100, 75, 85))  # deploy/README.md row 0
        self.assertTrue(any("shares its root authority (uniswap-l1-governance) with 1 other" in n for n in v4["notes"]))

    def test_none_of_the_four_folds_a_cross_ecosystem_overlap(self):
        # The cross-ecosystem fold (flat 80 via _crossEcosystem) belongs to Aave and Morpho; these four are
        # within-L1 only, and the internal keys never leak into the published dict.
        for label in ("Compound V3 cUSDCv3 (Comet USDC)", "SparkLend (PoolAddressesProvider)",
                      "Uniswap V4 PoolManager", "WBTC (Wrapped BTC)"):
            self.assertNotIn("_crossEcosystem", self.by_label[label], label)
            self.assertNotIn("_rootGroup", self.by_label[label], label)

    def test_published_composites_are_untouched_by_the_cross_exposure_pass(self):
        self.assertEqual(self.by_label["Compound V3 cUSDCv3 (Comet USDC)"]["compositeScore"], 79)
        self.assertEqual(self.by_label["SparkLend (PoolAddressesProvider)"]["compositeScore"], 78)
        self.assertEqual(self.by_label["Uniswap V4 PoolManager"]["compositeScore"], 85)
        self.assertEqual(self.by_label["WBTC (Wrapped BTC)"]["compositeScore"], 52)


# =========================================================================== citations
README_PATH = os.path.join(REPO_ROOT, "chains", "ethereum-l1", "deploy", "README.md")
MAINTENANCE_NOTE_PATH = os.path.join(REPO_ROOT, "chains", "ethereum-l1", "data", "maintenance_2026-09-19.md")
_README_ROW_RE = re.compile(r"^\|\s*(\d+)\s*\|\s*(.+?)\s*\|\s*`(0x[0-9a-fA-F]{40})`\s*\|((?:\s*\**\d+\**\s*\|){6})\s*$")

# PUBLISHED, deploy/README.md "Current on-chain scores (re-push, 2026-09-20)":
# scorer target address -> (row, admin, multisig, timelock, oracle, cross, composite). These are the values the
# tests above hard-code; TestCitationsHold checks the README still says so.
PUBLISHED_ROWS = {
    COMET: (9, 78, 100, 60, 100, 100, 79),
    SPARK_PROVIDER: (10, 75, 100, 60, 100, 80, 78),
    POOL_MANAGER: (11, 80, 100, 75, 100, 80, 85),
    WBTC: (13, 55, 100, 0, 100, 100, 52),
}


def _squash(text):
    return " ".join(text.split())


def _published_table():
    """address.lower() -> (row, name, admin, multisig, timelock, oracle, cross, composite), every row of the
    README table that follows the heading 'Current on-chain scores'."""
    with open(README_PATH, encoding="utf-8") as fh:
        text = fh.read()
    rows = {}
    for line in text[text.index("## Current on-chain scores"):].splitlines()[1:]:
        if line.startswith("## "):
            break
        m = _README_ROW_RE.match(line)
        if m:
            numbers = [int(c.strip().strip("*").strip()) for c in m.group(4).split("|") if c.strip()]
            rows[m.group(3).lower()] = (int(m.group(1)), m.group(2)) + tuple(numbers)
    return rows


class TestCitationsHold(unittest.TestCase):
    """The provenance the tests above cite, checked mechanically: if the README table, a scorer docstring or the
    maintenance note drifts away from a fixture, this fails and says which citation to re-verify. This is what
    keeps a PUBLISHED regression anchor honest, and it is the only independent anchor the file has for the
    composite formula itself (15 published rows, 8 of them exactly on a .5 boundary)."""

    def test_the_readme_table_was_found_and_is_complete(self):
        self.assertGreaterEqual(len(_published_table()), 15)

    def test_the_four_cited_rows_say_what_the_fixtures_say(self):
        table = _published_table()
        for address, expected in PUBLISHED_ROWS.items():
            row = table[address.lower()]
            self.assertEqual((row[0],) + row[2:], expected, address)

    def test_every_published_composite_is_the_exact_formula_of_its_own_published_sub_scores(self):
        # Independent of the scorers: only the README's numbers and METHODOLOGY.md's formula, in exact rationals.
        table = _published_table()
        boundary = 0
        for address, (row, name, admin, multisig, timelock, oracle, cross, composite) in table.items():
            self.assertEqual(_exact_composite(admin, multisig, timelock), composite, (row, name))
            if (Fraction(4, 10) * admin + Fraction(3, 10) * multisig + Fraction(3, 10) * timelock) % 1 == Fraction(1, 2):
                boundary += 1
        self.assertGreaterEqual(boundary, 5)  # the round-half-up rule is exercised, not just the easy rows

    def test_the_shared_composite_helper_reproduces_every_published_composite(self):
        for address, (row, name, admin, multisig, timelock, oracle, cross, composite) in _published_table().items():
            self.assertEqual(scorers._composite(admin, multisig, timelock), composite, (row, name))

    def test_every_fixture_address_documented_by_a_docstring_prefix_matches_that_prefix(self):
        documented = {
            scorers.score_compound_v3_cusdc: [COMET, COMP_TIMELOCK, COMP_PROXY_ADMIN, COMP_PAUSE_GUARDIAN],
            scorers.score_sparklend_pool: [
                SPARK_PROVIDER, SPARK_ACL, SPARK_PROXY, MCD_PAUSE_PROXY, FREEZER_MOM, FREEZER_MULTISIG],
            scorers.score_uniswap_v4_pool_manager: [POOL_MANAGER, UNI_TIMELOCK],
            scorers.score_wbtc: [WBTC_CONTROLLER, WBTC_MULTISIG],
        }
        for function, addresses in documented.items():
            doc = _squash(function.__doc__).lower()
            for address in addresses:
                self.assertIn(address[:10].lower(), doc, f"{function.__name__}: {address}")

    def test_the_raw_reads_behind_the_fixtures_are_still_in_the_scorer_docstrings(self):
        figures = {
            scorers.score_compound_v3_cusdc: ["172,800s", "608 proposals", "5-of-9"],
            scorers.score_sparklend_pool: ["3-of-5", "2-day-delay"],
            scorers.score_uniswap_v4_pool_manager: ["MINIMUM_DELAY = 2 days"],
            scorers.score_wbtc: ["getThreshold() reverts", "required() = 6", "getOwners() = 10"],
        }
        for function, fragments in figures.items():
            doc = _squash(function.__doc__)
            for fragment in fragments:
                self.assertIn(fragment, doc, f"{function.__name__}: {fragment}")

    def test_the_raw_reads_behind_the_fixtures_are_still_in_the_maintenance_note(self):
        with open(MAINTENANCE_NOTE_PATH, encoding="utf-8") as fh:
            note = _squash(fh.read())
        for fragment in (
            UNI_TIMELOCK, "172800 / 172800", "40M UNI", "608 proposals", "pauseGuardian = Safe 5-of-9",
            "Safe 3-of-5", "6-of-10",
        ):
            self.assertIn(fragment, note, fragment)


if __name__ == "__main__":
    unittest.main()
