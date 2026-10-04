"""
Unit tests for a first batch of scoring-decision logic in the root
`scripts/lib/scorers.py` (Robinhood Chain) -- the 2026-09-18 test-coverage
audit's next-ranked gap after Zcash, Base-ecosystem, Arbitrum-ecosystem, and
Ethereum L1. This file was already flagged as too broad for one pass (25
`score_*` functions across ~1583 lines, several with shared parametrized
templates feeding ~44 tracked targets) -- this is a deliberately scoped
first batch, not the whole file: the closed family of scorers sharing the
`_score_uniswap_bridge_alias_root()` helper (score_uniswap_v3_factory,
score_uniswap_v4_poolmanager, score_uniswapx_reactor,
score_uniswap_v2_factory_feetosetter -- all four resolve to the same real
Uniswap L1 Governance Timelock via its deterministic Arbitrum bridge alias),
plus two self-contained scorers already fully read while surveying this
file (score_morpho_steakhouse_usdg, score_lighter_escrow). test_scorers.py
already covers this file's pure `_composite`/`_apply_l1_cap` logic; that is
NOT repeated here.

Same FakeHelpers/FakeW3 approach as the four prior ecosystem test files.
New wrinkle specific to this file: `_score_uniswap_bridge_alias_root()`
opens a SECOND, independent w3 instance via `get_w3()` and calls
`.eth.get_code(...)` directly on it (not through a helper) -- Base's
existing L1 cross-check never did that (it only ever fed the second w3
into `call_raw()`, already faked), so this file's FakeW3 needs a real
`.eth.get_code()` with per-test-controllable results, not the bare-string
sentinel Base's fake `get_w3()` could get away with returning. The
deterministic `arbitrum_l1_l2_alias()` formula itself is NOT faked --
called for real in every fixture below, matching this project's own
"never trust a hand-typed value" discipline applied to the alias address
these fixtures need.
"""
import os
import sys
import unittest

from web3 import Web3 as RealWeb3

REPO_ROOT = os.path.join(os.path.dirname(__file__), "..", "..", "..")

# scripts/lib/scorers.py uses a package-relative import (`from .web3_utils
# import ...`), unlike the per-ecosystem chains/*/scorers.py files -- it
# can't be loaded standalone via importlib.util.spec_from_file_location the
# way those are. Match test_scorers.py's own already-working approach
# instead: put `scripts` on sys.path so `lib` resolves as a real package.
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))
from lib import scorers  # noqa: E402


class FakeEth:
    def __init__(self, code_sizes=None):
        self._code_sizes = code_sizes or {}

    def get_code(self, addr):
        return b"\x00" * self._code_sizes.get(addr, 100)


class FakeW3:
    def __init__(self, code_sizes=None):
        self.eth = FakeEth(code_sizes)

    @staticmethod
    def to_checksum_address(addr):
        return RealWeb3.to_checksum_address(addr)


class FakeHelpers:
    def __init__(self):
        self.address_getters = {}    # (address, function_name) -> address-or-None
        self.call_raw_results = {}   # (address, function_name, args-tuple) -> value-or-None
        self.slot_results = {}       # (address, slot) -> address-or-None
        self.safe_results = {}       # address -> (owners, threshold) or None
        self.eoa_results = {}        # address -> bool, default True
        self.l1_w3 = FakeW3()        # get_w3()'s return value -- default: every address "has code"

    def read_address_getter(self, w3, address, function_name, retries=4):
        return self.address_getters.get((address, function_name))

    def call_raw(self, w3, address, abi_fragment, function_name, *args, retries=4):
        return self.call_raw_results.get((address, function_name, args))

    def read_slot_as_address(self, w3, address, slot, retries=4):
        return self.slot_results.get((address, slot))

    def safe_owners_and_threshold(self, w3, address, retries=4):
        return self.safe_results.get(address)

    def is_eoa(self, w3, address):
        return self.eoa_results.get(address, True)

    def get_w3(self, rpc_url):
        return self.l1_w3


def _patch_helpers(test_case, fake):
    names = ["read_address_getter", "call_raw", "read_slot_as_address", "safe_owners_and_threshold", "is_eoa", "get_w3"]
    originals = {n: getattr(scorers, n) for n in names}
    for n in names:
        setattr(scorers, n, getattr(fake, n))
    test_case.addCleanup(lambda: [setattr(scorers, n, originals[n]) for n in names])


def _owners(n, start=1):
    return [RealWeb3.to_checksum_address("0x" + hex(i)[2:].zfill(40)) for i in range(start, start + n)]


ADDR_A = RealWeb3.to_checksum_address("0x" + "aa" * 20)
ADDR_B = RealWeb3.to_checksum_address("0x" + "bb" * 20)


# ADDED 2026-10-04: a Vault V2's live per-function timelocks, as scripts/lib/morpho_v2.py reads them (abdicated() then
# timelock() for the 5 fund-redirecting functions and the 4 exit gates). Synthetic values, named where used.
_V2_FUND = ["addAdapter(address)", "removeAdapter(address)", "setAdapterRegistry(address)",
            "increaseAbsoluteCap(bytes,uint256)", "increaseRelativeCap(bytes,uint256)"]
_V2_GATES = ["setReceiveSharesGate(address)", "setSendSharesGate(address)", "setReceiveAssetsGate(address)", "setSendAssetsGate(address)"]
DAY = 86400


def _v2_delays(fake, vault, fund=7 * DAY, gate_abdicated=(True, True, True, False), gate_delay=7 * DAY, overrides=None):
    for sig in _V2_FUND:
        sel = RealWeb3.keccak(text=sig)[:4]
        fake.call_raw_results[(vault, "abdicated", (sel,))] = False
        fake.call_raw_results[(vault, "timelock", (sel,))] = fund
    for sig, ab in zip(_V2_GATES, gate_abdicated):
        sel = RealWeb3.keccak(text=sig)[:4]
        fake.call_raw_results[(vault, "abdicated", (sel,))] = ab
        if not ab:
            fake.call_raw_results[(vault, "timelock", (sel,))] = gate_delay
    for sig, (ab, d) in (overrides or {}).items():
        sel = RealWeb3.keccak(text=sig)[:4]
        fake.call_raw_results[(vault, "abdicated", (sel,))] = ab
        fake.call_raw_results[(vault, "timelock", (sel,))] = d

UNI_L1_TIMELOCK = scorers._UNISWAP_L1_GOVERNANCE_TIMELOCK
UNI_L1_TIMELOCK_CHECKSUM = RealWeb3.to_checksum_address(UNI_L1_TIMELOCK)
# Computed live via the module's own real (unfaked) deterministic formula --
# not hand-typed or copy-pasted from a docstring's stated value.
UNI_BRIDGE_ALIAS = scorers.arbitrum_l1_l2_alias(UNI_L1_TIMELOCK)
GOVERNOR_BRAVO = RealWeb3.to_checksum_address("0x" + "60" * 20)


def _confirmed_l1_recheck(fake):
    """Shared 'the L1 re-verification itself succeeds' fixture -- every one
    of the 4 alias-root callers reuses this exact same L1 read sequence."""
    fake.l1_w3 = FakeW3(code_sizes={UNI_L1_TIMELOCK_CHECKSUM: 100})
    fake.call_raw_results[(UNI_L1_TIMELOCK, "delay", ())] = 172800
    fake.call_raw_results[(UNI_L1_TIMELOCK, "admin", ())] = GOVERNOR_BRAVO
    fake.call_raw_results[(GOVERNOR_BRAVO, "quorumVotes", ())] = 40_000_000 * 10**18


# --------------------------------------------------------------------- _score_uniswap_bridge_alias_root (shared helper, tested directly)
class TestScoreUniswapBridgeAliasRoot(unittest.TestCase):
    def test_alias_confirmed_and_l1_reconfirmed_scores_80_100_75(self):
        fake = FakeHelpers()
        _confirmed_l1_recheck(fake)
        _patch_helpers(self, fake)

        notes = []
        result = scorers._score_uniswap_bridge_alias_root(UNI_BRIDGE_ALIAS, notes)
        self.assertEqual(result, (80, 100, 75))
        self.assertTrue(any("match = True" in n for n in notes))

    def test_alias_not_confirmed_degrades_to_bare_eoa_equivalent(self):
        fake = FakeHelpers()
        _confirmed_l1_recheck(fake)  # even with a healthy L1, a wrong root must still degrade
        _patch_helpers(self, fake)

        notes = []
        result = scorers._score_uniswap_bridge_alias_root(ADDR_A, notes)  # NOT the real alias
        self.assertEqual(result, (5, 0, 0))
        self.assertTrue(any("Alias check failed" in n for n in notes))

    def test_resolved_root_none_short_circuits_without_crashing(self):
        fake = FakeHelpers()
        _patch_helpers(self, fake)

        notes = []
        result = scorers._score_uniswap_bridge_alias_root(None, notes)
        self.assertEqual(result, (5, 0, 0))

    def test_alias_confirmed_but_l1_code_empty_fails_closed(self):
        # The alias matches, but the L1 Timelock's own bytecode read comes
        # back empty this run (RPC returned nothing, or the address somehow
        # isn't a real contract) -- must NOT silently keep the higher score.
        fake = FakeHelpers()
        _confirmed_l1_recheck(fake)
        fake.l1_w3 = FakeW3(code_sizes={UNI_L1_TIMELOCK_CHECKSUM: 0})
        _patch_helpers(self, fake)

        notes = []
        result = scorers._score_uniswap_bridge_alias_root(UNI_BRIDGE_ALIAS, notes)
        self.assertEqual(result, (5, 0, 0))
        self.assertTrue(any("L1 re-confirmation incomplete" in n for n in notes))

    def test_alias_confirmed_but_delay_unresolved_fails_closed(self):
        fake = FakeHelpers()
        _confirmed_l1_recheck(fake)
        del fake.call_raw_results[(UNI_L1_TIMELOCK, "delay", ())]
        _patch_helpers(self, fake)

        notes = []
        result = scorers._score_uniswap_bridge_alias_root(UNI_BRIDGE_ALIAS, notes)
        self.assertEqual(result, (5, 0, 0))

    def test_alias_confirmed_but_quorum_unresolved_fails_closed(self):
        fake = FakeHelpers()
        _confirmed_l1_recheck(fake)
        del fake.call_raw_results[(GOVERNOR_BRAVO, "quorumVotes", ())]
        _patch_helpers(self, fake)

        notes = []
        result = scorers._score_uniswap_bridge_alias_root(UNI_BRIDGE_ALIAS, notes)
        self.assertEqual(result, (5, 0, 0))


# --------------------------------------------------------------------- Uniswap V3 Factory (Robinhood Chain)
class TestScoreUniswapV3Factory(unittest.TestCase):
    FACTORY = "0x1f7d7550B1b028f7571E69A784071F0205FD2EfA"

    def test_single_hop_alias_confirmed(self):
        fake = FakeHelpers()
        fake.address_getters[(self.FACTORY, "owner")] = UNI_BRIDGE_ALIAS
        # eoa_results defaults to True -- the alias itself has no bytecode, matching is_eoa's real behavior
        _confirmed_l1_recheck(fake)
        _patch_helpers(self, fake)

        result = scorers.score_uniswap_v3_factory(FakeW3())
        self.assertEqual((result["adminKeyScore"], result["multisigScore"], result["timelockScore"]), (80, 100, 75))
        self.assertEqual(result["compositeScore"], scorers._composite(80, 100, 75))

    def test_two_hop_trace_through_a_contract_adapter(self):
        # factory.owner() resolves to a real contract (not the alias directly) --
        # the second hop (adapter.owner()) must be the one actually checked
        # against the alias.
        fake = FakeHelpers()
        fake.address_getters[(self.FACTORY, "owner")] = ADDR_A
        fake.eoa_results[ADDR_A] = False
        fake.address_getters[(ADDR_A, "owner")] = UNI_BRIDGE_ALIAS
        _confirmed_l1_recheck(fake)
        _patch_helpers(self, fake)

        result = scorers.score_uniswap_v3_factory(FakeW3())
        self.assertEqual((result["adminKeyScore"], result["multisigScore"], result["timelockScore"]), (80, 100, 75))

    def test_root_is_a_real_safe_not_the_alias_uses_safe_branch(self):
        # Neither hop resolves to a bare EOA -- root_authority stays a
        # contract, so the alias-root helper is never even called; the
        # Safe-based branch applies instead.
        fake = FakeHelpers()
        fake.address_getters[(self.FACTORY, "owner")] = ADDR_A
        fake.eoa_results[ADDR_A] = False
        fake.address_getters[(ADDR_A, "owner")] = ADDR_B
        fake.eoa_results[ADDR_B] = False
        fake.safe_results[ADDR_B] = (_owners(3), 2)
        _patch_helpers(self, fake)

        result = scorers.score_uniswap_v3_factory(FakeW3())
        self.assertEqual(result["adminKeyScore"], 40)
        self.assertEqual(result["multisigScore"], 20)  # threshold 2 * 10
        self.assertEqual(result["timelockScore"], 0)


# --------------------------------------------------------------------- Uniswap V4 PoolManager (Robinhood Chain)
class TestScoreUniswapV4PoolManager(unittest.TestCase):
    POOL_MANAGER = "0x8366a39CC670B4001A1121B8F6A443A643e40951"

    def test_owner_is_alias_confirmed(self):
        fake = FakeHelpers()
        fake.address_getters[(self.POOL_MANAGER, "owner")] = UNI_BRIDGE_ALIAS
        _confirmed_l1_recheck(fake)
        _patch_helpers(self, fake)

        result = scorers.score_uniswap_v4_poolmanager(FakeW3())
        self.assertEqual((result["adminKeyScore"], result["multisigScore"], result["timelockScore"]), (80, 100, 75))

    def test_owner_is_a_real_contract_uses_flat_fallback(self):
        # Unlike V3 Factory, this scorer has no second-hop trace or Safe
        # branch for a non-EOA owner -- a flat 40/0/0 fallback.
        fake = FakeHelpers()
        fake.address_getters[(self.POOL_MANAGER, "owner")] = ADDR_A
        fake.eoa_results[ADDR_A] = False
        _patch_helpers(self, fake)

        result = scorers.score_uniswap_v4_poolmanager(FakeW3())
        self.assertEqual((result["adminKeyScore"], result["multisigScore"], result["timelockScore"]), (40, 0, 0))


# --------------------------------------------------------------------- UniswapX V3DutchOrderReactor (Robinhood Chain)
class TestScoreUniswapxReactor(unittest.TestCase):
    REACTOR = "0x000000007A1C8e570011EeDF86A2A35593013cBA"

    def test_owner_is_alias_confirmed(self):
        fake = FakeHelpers()
        fake.address_getters[(self.REACTOR, "owner")] = UNI_BRIDGE_ALIAS
        _confirmed_l1_recheck(fake)
        _patch_helpers(self, fake)

        result = scorers.score_uniswapx_reactor(FakeW3())
        self.assertEqual((result["adminKeyScore"], result["multisigScore"], result["timelockScore"]), (80, 100, 75))

    def test_owner_unresolved_does_not_crash_the_is_eoa_call(self):
        # owner() came back None -- `is_eoa(w3, owner) if owner else None`
        # must short-circuit rather than calling is_eoa(w3, None).
        fake = FakeHelpers()
        # (self.REACTOR, "owner") deliberately absent -> None
        _patch_helpers(self, fake)

        result = scorers.score_uniswapx_reactor(FakeW3())
        self.assertEqual((result["adminKeyScore"], result["multisigScore"], result["timelockScore"]), (40, 0, 0))


# --------------------------------------------------------------------- Uniswap V2 Factory feeToSetter (Robinhood Chain)
class TestScoreUniswapV2FactoryFeeToSetter(unittest.TestCase):
    TARGET = "0x8bcEaA40B9AcdfAedF85AdF4FF01F5Ad6517937f"

    def test_fee_to_setter_via_call_raw_alias_confirmed(self):
        # This caller reaches its root through call_raw(), not
        # read_address_getter() -- the one scorer in this family that does.
        fake = FakeHelpers()
        fake.call_raw_results[(self.TARGET, "feeToSetter", ())] = UNI_BRIDGE_ALIAS
        _confirmed_l1_recheck(fake)
        _patch_helpers(self, fake)

        result = scorers.score_uniswap_v2_factory_feetosetter(FakeW3())
        self.assertEqual((result["adminKeyScore"], result["multisigScore"], result["timelockScore"]), (80, 100, 75))

    def test_fee_to_setter_is_a_contract_uses_flat_fallback(self):
        fake = FakeHelpers()
        fake.call_raw_results[(self.TARGET, "feeToSetter", ())] = ADDR_A
        fake.eoa_results[ADDR_A] = False
        _patch_helpers(self, fake)

        result = scorers.score_uniswap_v2_factory_feetosetter(FakeW3())
        self.assertEqual((result["adminKeyScore"], result["multisigScore"], result["timelockScore"]), (40, 0, 0))


# --------------------------------------------------------------------- Morpho Steakhouse USDG vault (Robinhood Chain)
class TestScoreMorphoSteakhouseUsdg(unittest.TestCase):
    VAULT = "0xBeEff033F34C046626B8D0A041844C5d1A5409dd"
    GUARDIAN_CANDIDATE = "0x5642BCd50fC751fF2d04f155423e4D0E25C2a744"
    SELECTORS = ("0x13af4035", "0xe90956cf", "0x920ed706")

    def _sel_key(self, sel):
        return (self.VAULT, "timelock", (bytes.fromhex(sel[2:]),))

    # CHANGED 2026-10-04: V2 decisions 1 and 3 (METHODOLOGY.md, "Morpho Vault V2 scoring"); expected values by hand.
    def test_all_resolve_root_eoa_curator_safe_one_fund_function_at_zero_delay(self):
        fake = FakeHelpers()
        fake.address_getters[(self.VAULT, "owner")] = ADDR_A
        fake.eoa_results[ADDR_A] = True
        fake.address_getters[(self.VAULT, "curator")] = ADDR_B
        fake.safe_results[ADDR_B] = (_owners(3), 2)
        candidate_checksum = RealWeb3.to_checksum_address(self.GUARDIAN_CANDIDATE)
        fake.call_raw_results[(self.VAULT, "isSentinel", (candidate_checksum,))] = True
        fake.safe_results[self.GUARDIAN_CANDIDATE] = (_owners(5, start=10), 3)
        _v2_delays(fake, self.VAULT, overrides={"addAdapter(address)": (False, 0)})
        _patch_helpers(self, fake)

        result = scorers.score_morpho_steakhouse_usdg(FakeW3())
        self.assertEqual(result["adminKeyScore"], 5)      # root is a bare EOA: decision 3 floor (aligned 2026-10-04, was 10)
        self.assertEqual(result["multisigScore"], 35)     # curator Safe 2-of-3: 2*15 + 1*5
        self.assertEqual(result["timelockScore"], 0)      # addAdapter at 0 days -> minimum 0

    def test_abdicated_zero_delay_function_does_not_count(self):
        fake = FakeHelpers()
        fake.address_getters[(self.VAULT, "owner")] = ADDR_A
        fake.eoa_results[ADDR_A] = True
        _v2_delays(fake, self.VAULT, overrides={"setAdapterRegistry(address)": (True, 0)})  # the live shape on 5 of 6 vaults
        _patch_helpers(self, fake)
        self.assertEqual(scorers.score_morpho_steakhouse_usdg(FakeW3())["timelockScore"], 75)  # minimum 7 days

    def test_root_not_eoa_traces_one_more_hop(self):
        fake = FakeHelpers()
        fake.address_getters[(self.VAULT, "owner")] = ADDR_A
        fake.eoa_results[ADDR_A] = False
        fake.address_getters[(ADDR_A, "owner")] = ADDR_B
        fake.eoa_results[ADDR_B] = True
        _v2_delays(fake, self.VAULT, fund=DAY, gate_delay=DAY)
        _patch_helpers(self, fake)

        result = scorers.score_morpho_steakhouse_usdg(FakeW3())
        self.assertEqual(result["adminKeyScore"], 5)   # second-hop root IS a bare EOA: decision 3 floor
        self.assertEqual(result["multisigScore"], 5)   # no curator resolved
        self.assertEqual(result["timelockScore"], 40)  # 1-day minimum: band "any delay"

    def test_all_timelock_reads_none_degrades_without_crashing_regression(self):
        fake = FakeHelpers()
        fake.address_getters[(self.VAULT, "owner")] = ADDR_A
        fake.eoa_results[ADDR_A] = True
        # no abdicated()/timelock() answer registered -> every read None -> UNREAD, never 0 days
        _patch_helpers(self, fake)

        result = scorers.score_morpho_steakhouse_usdg(FakeW3())  # must not raise
        self.assertEqual(result["timelockScore"], 0)
        self.assertTrue(any("minimum delay UNREAD" in n for n in result["notes"]))


# --------------------------------------------------------------------- Lighter (zkLighter) Escrow proxy (Robinhood Chain)
class TestScoreLighterEscrow(unittest.TestCase):
    PROXY = "0x94bAB9693Ba2f6358507eFfcbd372b0660AFfF9d"

    def _slot_key(self):
        return (self.PROXY, scorers.EIP1967_ADMIN_SLOT)

    def test_confirmed_bare_eoa_council_with_real_delay_caps_at_15(self):
        fake = FakeHelpers()
        fake.slot_results[self._slot_key()] = ADDR_A  # gatekeeper
        fake.call_raw_results[(ADDR_A, "getMaster", ())] = ADDR_B
        fake.safe_results[ADDR_B] = (_owners(5, start=20), 3)
        fake.call_raw_results[(ADDR_A, "approvedUpgradeNoticePeriod", ())] = 604800
        council = RealWeb3.to_checksum_address("0x" + "cc" * 20)
        fake.call_raw_results[(ADDR_A, "securityCouncilAddress", ())] = council
        fake.eoa_results[council] = True
        _patch_helpers(self, fake)

        result = scorers.score_lighter_escrow(FakeW3())
        self.assertEqual(result["adminKeyScore"], 75)
        self.assertEqual(result["multisigScore"], 65)  # 3*20+5
        self.assertEqual(result["timelockScore"], 15)  # real delay, but a bare EOA can zero it unilaterally

    def test_council_not_a_bare_eoa_awards_full_timelock_credit(self):
        fake = FakeHelpers()
        fake.slot_results[self._slot_key()] = ADDR_A
        fake.call_raw_results[(ADDR_A, "approvedUpgradeNoticePeriod", ())] = 604800
        council = RealWeb3.to_checksum_address("0x" + "cc" * 20)
        fake.call_raw_results[(ADDR_A, "securityCouncilAddress", ())] = council
        fake.eoa_results[council] = False  # a real contract/module, not a bypassable bare key
        _patch_helpers(self, fake)

        result = scorers.score_lighter_escrow(FakeW3())
        self.assertEqual(result["timelockScore"], 60)

    def test_council_unresolved_degrades_regression(self):
        # Regression test for the FIXED 2026-09-17 bug this scorer's own
        # comment documents: council_is_eoa=None (securityCouncilAddress()
        # itself never resolved) used to fall through Python truthiness into
        # the SAME 60-point branch as a council confirmed NOT to be a bare
        # EOA -- silently awarding the best score for a bypass check that
        # was never actually performed.
        fake = FakeHelpers()
        fake.slot_results[self._slot_key()] = ADDR_A
        fake.call_raw_results[(ADDR_A, "approvedUpgradeNoticePeriod", ())] = 604800
        # (ADDR_A, "securityCouncilAddress", ()) deliberately absent -> None
        _patch_helpers(self, fake)

        result = scorers.score_lighter_escrow(FakeW3())
        self.assertEqual(result["timelockScore"], 0)
        self.assertTrue(any("bare-EOA bypass check was never performed" in n for n in result["notes"]))

    def test_zero_notice_period_scores_zero_timelock(self):
        fake = FakeHelpers()
        fake.slot_results[self._slot_key()] = ADDR_A
        fake.call_raw_results[(ADDR_A, "approvedUpgradeNoticePeriod", ())] = 0
        council = RealWeb3.to_checksum_address("0x" + "cc" * 20)
        fake.call_raw_results[(ADDR_A, "securityCouncilAddress", ())] = council
        fake.eoa_results[council] = True
        _patch_helpers(self, fake)

        result = scorers.score_lighter_escrow(FakeW3())
        self.assertEqual(result["timelockScore"], 0)

    def test_no_master_safe_degrades_admin_key_and_multisig(self):
        fake = FakeHelpers()
        fake.slot_results[self._slot_key()] = ADDR_A
        # getMaster() absent -> None -> no safe lookup attempted
        fake.call_raw_results[(ADDR_A, "approvedUpgradeNoticePeriod", ())] = 604800
        council = RealWeb3.to_checksum_address("0x" + "cc" * 20)
        fake.call_raw_results[(ADDR_A, "securityCouncilAddress", ())] = council
        fake.eoa_results[council] = True
        _patch_helpers(self, fake)

        result = scorers.score_lighter_escrow(FakeW3())
        self.assertEqual(result["adminKeyScore"], 10)
        self.assertEqual(result["multisigScore"], 0)


if __name__ == "__main__":
    unittest.main()
