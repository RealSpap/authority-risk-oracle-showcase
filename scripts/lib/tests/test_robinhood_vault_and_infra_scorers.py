"""
Unit tests for "batch B" of the 2026-09-18 test-coverage audit on
`scripts/lib/scorers.py` (Robinhood Chain) -- the parametrized-template
vault scorers (Arcus pToken family, Robinhood stock-token beacon family,
the generic Morpho Vault V2 template, the Longbow vault template) plus a
handful of normal-primitive standalone/list-returning scorers (Spark
Savings USDG, Pendle V2, LayerZero V2 infra, Snuggle MaxFi vault). This is
a sibling pass to test_robinhood_uniswap_family_scorers.py (batch "first"),
covering a disjoint set of `score_*` functions in the same file --
test_scorers.py's `_composite`/`_apply_l1_cap` coverage is not repeated
here, and the Uniswap-bridge-alias family is not repeated here either.

Same FakeHelpers/FakeW3 approach and the same package-relative-import
workaround as test_scorers.py and test_robinhood_uniswap_family_scorers.py
(see the sys.path comment below -- copied verbatim, this is the single
easiest way to waste time on this file).

Two wrinkles new to this file:

1. score_layerzero_infra() is the first scorer in this project's test
   history to call `custom_multisig_owners_and_threshold()` (a bespoke
   non-Safe on-chain multisig primitive, distinct from
   `safe_owners_and_threshold()`) -- FakeHelpers below adds a separate
   `custom_multisig_results` dispatch table and fake method for it,
   patched alongside the others.

2. score_snuggle_maxfi_vault() calls `w3.eth.get_code(...)` DIRECTLY (not
   through `is_eoa()`) and inspects the raw bytes for the EIP-7702
   delegation designator prefix `b"\\xef\\x01\\x00"` -- a bare
   `code_sizes -> zero-filled bytes` FakeEth (as used in
   test_base_ecosystem_scorers.py and test_robinhood_uniswap_family_scorers.py)
   cannot express that specific byte pattern, so FakeEth here also accepts
   a `codes` dict of address -> raw bytes, checked first.

Two behavioral oddities were noticed while reading this batch's functions
and are exercised (not "fixed") below; both are called out again in the
test-writing pass's final report as candidate live bugs:
  - score_longbow_vault(): adminKeyScore/multisigScore/timelockScore are a
    flat `40, 40, 15` literal assignment, NOT conditioned on whether
    owner()/curator() or either Gnosis Safe actually resolved.
  - score_spark_savings_usdg(): `timelockScore = 10 if delay == 0 else 60`
    means an UNRESOLVED delay() read (None) lands in the same branch as a
    confirmed nonzero delay (60, the better score) rather than failing
    closed.
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
    """`codes` (address -> raw bytes) takes priority when present, so a test
    can pin an exact byte pattern (e.g. the EIP-7702 designator prefix);
    `code_sizes` (address -> length) is the lighter-weight zero-filled-bytes
    form used elsewhere in this project's test suite. An address in neither
    dict defaults to 100 zero bytes -- "has ordinary contract code" -- the
    same default test_robinhood_uniswap_family_scorers.py's FakeEth uses."""

    def __init__(self, codes=None, code_sizes=None):
        self._codes = codes or {}
        self._code_sizes = code_sizes or {}

    def get_code(self, addr):
        if addr in self._codes:
            return self._codes[addr]
        return b"\x00" * self._code_sizes.get(addr, 100)


class FakeW3:
    def __init__(self, codes=None, code_sizes=None):
        self.eth = FakeEth(codes, code_sizes)

    @staticmethod
    def to_checksum_address(addr):
        return RealWeb3.to_checksum_address(addr)


class FakeHelpers:
    def __init__(self):
        self.address_getters = {}        # (address, function_name) -> address-or-None
        self.call_raw_results = {}       # (address, function_name, args-tuple) -> value-or-None
        self.slot_results = {}           # (address, slot) -> address-or-None
        self.safe_results = {}           # address -> (owners, threshold) or None
        self.custom_multisig_results = {}  # address -> (signers, threshold) or None -- bespoke non-Safe multisig
        self.eoa_results = {}            # address -> bool, default True

    def read_address_getter(self, w3, address, function_name, retries=4):
        return self.address_getters.get((address, function_name))

    def call_raw(self, w3, address, abi_fragment, function_name, *args, retries=4):
        return self.call_raw_results.get((address, function_name, args))

    def read_slot_as_address(self, w3, address, slot, retries=4):
        return self.slot_results.get((address, slot))

    def safe_owners_and_threshold(self, w3, address, retries=4):
        return self.safe_results.get(address)

    def custom_multisig_owners_and_threshold(self, w3, address, retries=4):
        return self.custom_multisig_results.get(address)

    def is_eoa(self, w3, address):
        return self.eoa_results.get(address, True)


def _patch_helpers(test_case, fake):
    names = [
        "read_address_getter", "call_raw", "read_slot_as_address",
        "safe_owners_and_threshold", "custom_multisig_owners_and_threshold", "is_eoa",
    ]
    originals = {n: getattr(scorers, n) for n in names}
    for n in names:
        setattr(scorers, n, getattr(fake, n))
    test_case.addCleanup(lambda: [setattr(scorers, n, originals[n]) for n in names])


def _owners(n, start=1):
    return [RealWeb3.to_checksum_address("0x" + hex(i)[2:].zfill(40)) for i in range(start, start + n)]


ADDR_A = RealWeb3.to_checksum_address("0x" + "aa" * 20)
ADDR_B = RealWeb3.to_checksum_address("0x" + "bb" * 20)


# --------------------------------------------------------------------- Arcus pToken family (Robinhood Chain)
class TestScoreArcusPtoken(unittest.TestCase):
    BEACON = "0x33846348210A0Cc0345F354d9DE52b89AD473A76"

    def test_beacon_safe_confirmed_scores_65_55_across_all_targets(self):
        fake = FakeHelpers()
        fake.address_getters[(self.BEACON, "owner")] = ADDR_A
        fake.safe_results[ADDR_A] = (_owners(3), 2)  # 2-of-3
        _patch_helpers(self, fake)

        for target_address, label in scorers.ARCUS_TARGETS:
            with self.subTest(label=label):
                result = scorers.score_arcus_ptoken(FakeW3(), target_address, label)
                self.assertEqual(result["target"], target_address)
                self.assertEqual(result["label"], label)
                self.assertEqual(
                    (result["adminKeyScore"], result["multisigScore"], result["timelockScore"]),
                    (65, 55, 0),
                )
                self.assertEqual(result["compositeScore"], scorers._composite(65, 55, 0))

    def test_beacon_owner_unresolved_degrades_to_10_0(self):
        fake = FakeHelpers()
        # (BEACON, "owner") deliberately absent -> None
        _patch_helpers(self, fake)

        target_address, label = scorers.ARCUS_TARGETS[1]
        result = scorers.score_arcus_ptoken(FakeW3(), target_address, label)
        self.assertEqual(
            (result["adminKeyScore"], result["multisigScore"], result["timelockScore"]),
            (10, 0, 0),
        )

    def test_beacon_owner_resolves_but_is_not_a_safe_degrades_to_10_0(self):
        fake = FakeHelpers()
        fake.address_getters[(self.BEACON, "owner")] = ADDR_A
        # ADDR_A deliberately absent from safe_results -> not a Safe
        _patch_helpers(self, fake)

        target_address, label = scorers.ARCUS_TARGETS[0]
        result = scorers.score_arcus_ptoken(FakeW3(), target_address, label)
        self.assertEqual(
            (result["adminKeyScore"], result["multisigScore"], result["timelockScore"]),
            (10, 0, 0),
        )


# --------------------------------------------------------------------- Robinhood stock-token beacon family
class TestScoreStockToken(unittest.TestCase):
    BEACON = "0xe10b6f6b275de231345c20d14ab812db62151b00"
    KNOWN_ADMIN = "0xd6f8378f8e440c65f8382f5f2728c78dfd55b66d"
    DEFAULT_ADMIN_ROLE = b"\x00" * 32  # OZ's DEFAULT_ADMIN_ROLE constant, not a keccak-derived value

    def _has_role_key(self):
        return (self.BEACON, "hasRole", (self.DEFAULT_ADMIN_ROLE, RealWeb3.to_checksum_address(self.KNOWN_ADMIN)))

    def test_admin_still_holds_role_and_is_bare_eoa_scores_3_across_all_targets(self):
        fake = FakeHelpers()
        fake.call_raw_results[self._has_role_key()] = True
        # is_eoa() is called with the RAW (non-checksummed) known_admin string --
        # the source never checksums it before this specific call, unlike the
        # hasRole() arg a few lines above, which it does checksum.
        fake.eoa_results[self.KNOWN_ADMIN] = True
        _patch_helpers(self, fake)

        for target_address, label in scorers.STOCK_TOKEN_TARGETS:
            with self.subTest(label=label):
                result = scorers.score_stock_token(FakeW3(), target_address, label)
                self.assertEqual(result["target"], target_address)
                self.assertEqual(
                    (result["adminKeyScore"], result["multisigScore"], result["timelockScore"]),
                    (3, 0, 0),
                )

    def test_role_check_unresolved_fails_closed_to_40(self):
        fake = FakeHelpers()
        # hasRole(...) key deliberately absent -> None -> is_eoa() never even called
        _patch_helpers(self, fake)

        target_address, label = scorers.STOCK_TOKEN_TARGETS[0]
        result = scorers.score_stock_token(FakeW3(), target_address, label)
        self.assertEqual(result["adminKeyScore"], 40)

    def test_admin_role_revoked_scores_40(self):
        fake = FakeHelpers()
        fake.call_raw_results[self._has_role_key()] = False
        _patch_helpers(self, fake)

        target_address, label = scorers.STOCK_TOKEN_TARGETS[0]
        result = scorers.score_stock_token(FakeW3(), target_address, label)
        self.assertEqual(result["adminKeyScore"], 40)

    def test_admin_holds_role_but_is_not_a_bare_eoa_scores_40(self):
        fake = FakeHelpers()
        fake.call_raw_results[self._has_role_key()] = True
        fake.eoa_results[self.KNOWN_ADMIN] = False
        _patch_helpers(self, fake)

        target_address, label = scorers.STOCK_TOKEN_TARGETS[0]
        result = scorers.score_stock_token(FakeW3(), target_address, label)
        self.assertEqual(result["adminKeyScore"], 40)


# --------------------------------------------------------------------- Generic Morpho Vault V2 template
class TestScoreMorphoVaultGeneric(unittest.TestCase):
    SELECTORS = ("0x13af4035", "0xe90956cf", "0x920ed706")  # setOwner/setCurator/setIsSentinel

    def _delay_key(self, vault, sel):
        return (vault, "timelock", (bytes.fromhex(sel[2:]),))

    def test_bare_eoa_owner_and_curator_safe_known_delays_across_all_vaults(self):
        for vault, label in scorers.MORE_MORPHO_VAULTS:
            with self.subTest(label=label):
                fake = FakeHelpers()
                fake.address_getters[(vault, "owner")] = ADDR_A
                fake.eoa_results[ADDR_A] = True
                fake.address_getters[(vault, "curator")] = ADDR_B
                fake.safe_results[ADDR_B] = (_owners(3), 2)
                for i, sel in enumerate(self.SELECTORS):
                    fake.call_raw_results[self._delay_key(vault, sel)] = 86400 if i < 2 else 172800
                _patch_helpers(self, fake)

                result = scorers.score_morpho_vault_generic(FakeW3(), vault, label)
                self.assertEqual(result["target"], vault)
                self.assertEqual(result["label"], label)
                self.assertEqual(result["adminKeyScore"], 10)      # owner_is_eoa
                self.assertEqual(result["multisigScore"], 16)      # curator Safe 2-of-3 -> 2*8
                self.assertEqual(result["timelockScore"], 60)      # known delays, min > 0

    def test_owner_resolves_directly_to_a_real_safe_no_two_hop_trace(self):
        vault, label = scorers.MORE_MORPHO_VAULTS[0]
        fake = FakeHelpers()
        fake.address_getters[(vault, "owner")] = ADDR_A
        fake.eoa_results[ADDR_A] = False
        fake.safe_results[ADDR_A] = (_owners(5), 3)
        # no curator resolved, no delays resolved
        _patch_helpers(self, fake)

        result = scorers.score_morpho_vault_generic(FakeW3(), vault, label)
        self.assertEqual(result["adminKeyScore"], 48)   # 30 + 3*6
        self.assertEqual(result["multisigScore"], 24)   # owner Safe only: 3*8
        self.assertEqual(result["timelockScore"], 0)    # no delay reads resolved at all

    def test_owner_two_hop_trace_resolves_a_bare_eoa(self):
        vault, label = scorers.MORE_MORPHO_VAULTS[1]
        fake = FakeHelpers()
        fake.address_getters[(vault, "owner")] = ADDR_A
        fake.eoa_results[ADDR_A] = False  # not a bare EOA itself -> traced one hop further
        fake.address_getters[(ADDR_A, "owner")] = ADDR_B
        fake.eoa_results[ADDR_B] = True
        _patch_helpers(self, fake)

        result = scorers.score_morpho_vault_generic(FakeW3(), vault, label)
        self.assertEqual(result["adminKeyScore"], 10)   # second-hop root IS a bare EOA
        self.assertEqual(result["multisigScore"], 0)
        self.assertTrue(any("owner().owner()" in n and "traced one hop further" in n for n in result["notes"]))

    def test_owner_two_hop_trace_resolves_a_safe(self):
        vault, label = scorers.MORE_MORPHO_VAULTS[2]
        fake = FakeHelpers()
        fake.address_getters[(vault, "owner")] = ADDR_A
        fake.eoa_results[ADDR_A] = False
        fake.address_getters[(ADDR_A, "owner")] = ADDR_B
        fake.eoa_results[ADDR_B] = False
        fake.safe_results[ADDR_B] = (_owners(3, start=50), 2)
        _patch_helpers(self, fake)

        result = scorers.score_morpho_vault_generic(FakeW3(), vault, label)
        self.assertEqual(result["adminKeyScore"], 42)   # 30 + 2*6
        self.assertEqual(result["multisigScore"], 16)   # owner Safe only: 2*8

    def test_owner_two_hop_trace_fails_to_resolve_falls_back_to_20(self):
        vault, label = scorers.MORE_MORPHO_VAULTS[0]
        fake = FakeHelpers()
        fake.address_getters[(vault, "owner")] = ADDR_A
        fake.eoa_results[ADDR_A] = False
        # (ADDR_A, "owner") deliberately absent -> nested lookup returns None -> trace abandoned
        _patch_helpers(self, fake)

        result = scorers.score_morpho_vault_generic(FakeW3(), vault, label)
        self.assertEqual(result["adminKeyScore"], 20)   # neither a bare EOA nor a resolvable Safe
        self.assertEqual(result["multisigScore"], 0)
        self.assertEqual(result["timelockScore"], 0)

    def test_owner_entirely_unresolved_curator_safe_and_one_zero_delay_scores_10_timelock(self):
        vault, label = scorers.MORE_MORPHO_VAULTS[1]
        fake = FakeHelpers()
        # (vault, "owner") deliberately absent -> owner is None entirely
        fake.address_getters[(vault, "curator")] = ADDR_B
        fake.safe_results[ADDR_B] = (_owners(3), 2)
        fake.call_raw_results[self._delay_key(vault, self.SELECTORS[0])] = 0
        fake.call_raw_results[self._delay_key(vault, self.SELECTORS[1])] = 86400
        # third selector's delay unresolved -> filtered out of `delays`
        _patch_helpers(self, fake)

        result = scorers.score_morpho_vault_generic(FakeW3(), vault, label)
        self.assertEqual(result["adminKeyScore"], 20)   # owner unresolved -> neither eoa nor safe branch
        self.assertEqual(result["multisigScore"], 16)   # curator Safe only: 2*8
        self.assertEqual(result["timelockScore"], 10)   # min(delays) == 0


# --------------------------------------------------------------------- Longbow vault template
class TestScoreLongbowVault(unittest.TestCase):
    def test_owner_and_curator_share_identical_safe_fixed_scores_across_all_vaults(self):
        shared_owners = _owners(3)
        for vault, label in scorers.LONGBOW_TARGETS:
            with self.subTest(label=label):
                fake = FakeHelpers()
                fake.address_getters[(vault, "owner")] = ADDR_A
                fake.address_getters[(vault, "curator")] = ADDR_B
                fake.safe_results[ADDR_A] = (shared_owners, 2)
                fake.safe_results[ADDR_B] = (shared_owners, 2)  # identical owner set
                _patch_helpers(self, fake)

                result = scorers.score_longbow_vault(FakeW3(), vault, label)
                self.assertEqual(result["target"], vault)
                self.assertEqual(result["label"], label)
                self.assertEqual(
                    (result["adminKeyScore"], result["multisigScore"], result["timelockScore"]),
                    (40, 40, 15),
                )
                self.assertTrue(any("share the IDENTICAL owner set" in n for n in result["notes"]))

    def test_owner_and_curator_safes_differ_still_fixed_scores_no_identical_note(self):
        vault, label = scorers.LONGBOW_TARGETS[0]
        fake = FakeHelpers()
        fake.address_getters[(vault, "owner")] = ADDR_A
        fake.address_getters[(vault, "curator")] = ADDR_B
        fake.safe_results[ADDR_A] = (_owners(3, start=1), 2)
        fake.safe_results[ADDR_B] = (_owners(3, start=90), 2)  # different owner set
        _patch_helpers(self, fake)

        result = scorers.score_longbow_vault(FakeW3(), vault, label)
        self.assertEqual(
            (result["adminKeyScore"], result["multisigScore"], result["timelockScore"]),
            (40, 40, 15),
        )
        self.assertFalse(any("IDENTICAL" in n for n in result["notes"]))

    def test_owner_and_curator_entirely_unresolved_scores_unchanged_regression(self):
        # NOTE: this documents a real oddity found while reading the source,
        # not a bug this test file fixes: adminKeyScore/multisigScore/
        # timelockScore are a flat `40, 40, 15` literal assignment at the end
        # of score_longbow_vault(), never actually conditioned on whether
        # owner()/curator() or either Gnosis Safe resolved. Even a total
        # read failure below still reports the same "confirmed" scores.
        # Flagged in the batch's final report as a candidate live bug --
        # out of scope to fix here.
        vault, label = scorers.LONGBOW_TARGETS[2]
        fake = FakeHelpers()
        # owner()/curator() both deliberately absent -> None
        _patch_helpers(self, fake)

        result = scorers.score_longbow_vault(FakeW3(), vault, label)
        self.assertEqual(
            (result["adminKeyScore"], result["multisigScore"], result["timelockScore"]),
            (40, 40, 15),
        )
        self.assertEqual(len(result["notes"]), 1)  # only the unconditional owner()/curator() line


# --------------------------------------------------------------------- Spark Savings USDG (spUSDG)
class TestScoreSparkSavingsUsdg(unittest.TestCase):
    EXECUTOR = "0x826aeaeee9233fa8ba199518dd8621a5962b1d02"
    RECEIVER = "0xc12B1e59c5E337d5Acd2b4f0A9a27d9E5D7387E8"

    def test_confirmed_full_chain_delay_zero_matches_documented_live_state(self):
        fake = FakeHelpers()
        fake.eoa_results[self.EXECUTOR] = False
        fake.call_raw_results[(self.EXECUTOR, "delay", ())] = 0
        fake.call_raw_results[(self.EXECUTOR, "gracePeriod", ())] = 172800
        fake.address_getters[(self.RECEIVER, "l1Authority")] = ADDR_A
        # RECEIVER deliberately absent from safe_results -- expected False, ArbitrumReceiver pattern
        _patch_helpers(self, fake)

        result = scorers.score_spark_savings_usdg(FakeW3())
        self.assertEqual(
            (result["adminKeyScore"], result["multisigScore"], result["timelockScore"]),
            (50, 30, 10),
        )

    def test_delay_nonzero_scores_timelock_60(self):
        fake = FakeHelpers()
        fake.call_raw_results[(self.EXECUTOR, "delay", ())] = 3600
        _patch_helpers(self, fake)

        result = scorers.score_spark_savings_usdg(FakeW3())
        self.assertEqual(result["timelockScore"], 60)

    def test_delay_unresolved_falls_into_same_branch_as_confirmed_nonzero_regression(self):
        # NOTE: `timelockScore = 10 if delay == 0 else 60` means an
        # UNRESOLVED delay() read (None, e.g. every retry hit a transient RPC
        # failure) is indistinguishable from a confirmed nonzero delay -- it
        # lands on the BETTER score (60), not a fail-closed default. This
        # looks like a real scoring bug (inconsistent with the rest of this
        # file's "unresolved read -> conservative score" discipline);
        # flagged in the final report, not fixed here.
        fake = FakeHelpers()
        # (EXECUTOR, "delay", ()) deliberately absent -> None
        _patch_helpers(self, fake)

        result = scorers.score_spark_savings_usdg(FakeW3())
        self.assertEqual(result["timelockScore"], 60)

    def test_admin_key_and_multisig_constant_regardless_of_reads(self):
        # Even a materially WORSE live state (the executor is now a bare EOA,
        # contradicting the docstring's self-administering-AccessControl
        # story) does not move adminKeyScore/multisigScore -- both are flat
        # literals (50, 30) in this scorer, not derived from the reads above
        # them. Documented here, flagged in the final report.
        fake = FakeHelpers()
        fake.eoa_results[self.EXECUTOR] = True
        # l1Authority / receiver Safe check left entirely unresolved
        _patch_helpers(self, fake)

        result = scorers.score_spark_savings_usdg(FakeW3())
        self.assertEqual(result["adminKeyScore"], 50)
        self.assertEqual(result["multisigScore"], 30)


# --------------------------------------------------------------------- Spark Liquidity Layer (ALMProxy) -- previously ZERO test coverage
# Found 2026-09-19 while sweeping every ecosystem's scorers.py for function
# names missing from every test file: unlike its sibling
# score_spark_savings_usdg() above (same executor contract, added the same
# batch 13), this function's own admin-confirmation gate is a real
# hasRole(DEFAULT_ADMIN_ROLE, executor) check on the TARGET, not an is_eoa()
# check on the executor itself -- a materially different fixture shape
# despite the near-identical resulting scores (50, 30, 10-or-60).
# RESTORED 2026-09-19: this class was accidentally dropped by a later,
# unrelated commit (0ee6001, rotation audit index 12) that edited this same
# file and silently lost it -- caught by a fresh test-coverage sweep, not
# re-derived from memory (verified byte-identical to the original via git
# history, and the scorer function itself is unchanged since).
class TestScoreSparkLiquidityLayerAlmproxy(unittest.TestCase):
    TARGET = "0xfD2fD4B046136B540A56C11c75ac679AE7d1dB24"
    EXECUTOR = "0x826aeaeee9233fa8ba199518dd8621a5962b1d02"
    RECEIVER = "0xc12B1e59c5E337d5Acd2b4f0A9a27d9E5D7387E8"
    DEFAULT_ADMIN_ROLE = b"\x00" * 32

    def _wire(self, executor_holds_admin=True, delay=0):
        fake = FakeHelpers()
        fake.call_raw_results[(self.TARGET, "hasRole", (self.DEFAULT_ADMIN_ROLE, RealWeb3.to_checksum_address(self.EXECUTOR)))] = executor_holds_admin
        fake.call_raw_results[(self.EXECUTOR, "delay", ())] = delay
        fake.call_raw_results[(self.EXECUTOR, "gracePeriod", ())] = 604800
        fake.address_getters[(self.RECEIVER, "l1Authority")] = ADDR_A
        _patch_helpers(self, fake)
        return fake

    def test_confirmed_full_chain_delay_zero_matches_documented_live_state(self):
        self._wire(executor_holds_admin=True, delay=0)
        result = scorers.score_spark_liquidity_layer_almproxy(FakeW3())
        self.assertEqual(
            (result["adminKeyScore"], result["multisigScore"], result["timelockScore"]),
            (50, 30, 10),
        )
        self.assertTrue(any("8113" in n or "8,113" in n for n in result["notes"]))

    def test_delay_nonzero_scores_timelock_60(self):
        self._wire(executor_holds_admin=True, delay=3600)
        result = scorers.score_spark_liquidity_layer_almproxy(FakeW3())
        self.assertEqual(result["timelockScore"], 60)

    def test_delay_unresolved_lands_in_the_same_branch_as_nonzero_regression(self):
        # Same disclosed oddity as score_spark_savings_usdg() above:
        # `timelock_score = 10 if delay == 0 else 60` treats an UNRESOLVED
        # delay() read (None, e.g. every retry hit a transient RPC failure)
        # identically to a confirmed nonzero delay -- the better score (60),
        # not a fail-closed default. Exercised here, not fixed.
        self._wire(executor_holds_admin=True, delay=None)
        result = scorers.score_spark_liquidity_layer_almproxy(FakeW3())
        self.assertEqual(result["timelockScore"], 60)

    def test_executor_does_not_hold_admin_role_fails_closed(self):
        # Unlike score_spark_savings_usdg()'s flat-literal admin/multisig
        # scores, THIS scorer's own docstring explicitly commits to failing
        # loud on divergence ("Fail loud rather than silently scoring
        # against a stale assumption") -- confirmed here as real behavior,
        # not just a docstring claim: a False hasRole read degrades ALL
        # three sub-scores, not just one.
        self._wire(executor_holds_admin=False)
        result = scorers.score_spark_liquidity_layer_almproxy(FakeW3())
        self.assertEqual(
            (result["adminKeyScore"], result["multisigScore"], result["timelockScore"]),
            (20, 0, 0),
        )
        self.assertTrue(any("DIVERGENCE" in n for n in result["notes"]))

    def test_admin_key_and_multisig_constant_once_role_confirmed(self):
        # Same flat-literal-once-gated pattern as the Spark Savings sibling:
        # adminKeyScore/multisigScore don't vary with delay/gracePeriod/
        # l1Authority once executor_holds_admin is True.
        self._wire(executor_holds_admin=True, delay=999999)
        result = scorers.score_spark_liquidity_layer_almproxy(FakeW3())
        self.assertEqual(result["adminKeyScore"], 50)
        self.assertEqual(result["multisigScore"], 30)


# --------------------------------------------------------------------- Pendle V2 (ProxyAdmin + devProxyAdmin + MarketFactoryV6)
class TestScorePendleV2(unittest.TestCase):
    PROXY_ADMIN = "0xA28c08f165116587D4F3E708743B4dEe155c5E64"
    DEV_PROXY_ADMIN = "0xD37eB2E6DE40a33ba68BaD94427723b66c954EA9"
    MARKET_FACTORY = "0x544BF81c855AE84c1e8b65d5E38770898D01EeE2"

    def test_both_proxyadmins_are_safes_scores_70_weakest_threshold_sets_multisig(self):
        fake = FakeHelpers()
        fake.address_getters[(self.PROXY_ADMIN, "owner")] = ADDR_A
        fake.safe_results[ADDR_A] = (_owners(5), 3)
        fake.address_getters[(self.DEV_PROXY_ADMIN, "owner")] = ADDR_B
        fake.safe_results[ADDR_B] = (_owners(3, start=50), 2)
        fake.address_getters[(self.MARKET_FACTORY, "owner")] = ADDR_A  # unused in the score, only in notes
        fake.eoa_results[ADDR_A] = False
        _patch_helpers(self, fake)

        result = scorers.score_pendle_v2(FakeW3())
        self.assertEqual(result["adminKeyScore"], 70)
        self.assertEqual(result["multisigScore"], 30)  # weakest of the two: threshold 2 * 15
        self.assertEqual(result["timelockScore"], 0)
        self.assertTrue(any("MarketFactoryV6.owner()" in n for n in result["notes"]))

    def test_one_proxyadmin_safe_other_unresolved_scores_45(self):
        fake = FakeHelpers()
        fake.address_getters[(self.PROXY_ADMIN, "owner")] = ADDR_A
        fake.safe_results[ADDR_A] = (_owners(5), 4)
        # devProxyAdmin.owner() deliberately absent -> dpa_owner None -> dpa_safe None
        _patch_helpers(self, fake)

        result = scorers.score_pendle_v2(FakeW3())
        self.assertEqual(result["adminKeyScore"], 45)
        self.assertEqual(result["multisigScore"], 60)  # only Safe found: threshold 4 * 15

    def test_neither_proxyadmin_resolves_a_safe_scores_10_degraded(self):
        fake = FakeHelpers()
        fake.address_getters[(self.PROXY_ADMIN, "owner")] = ADDR_A
        # ADDR_A resolves but is not registered as a Safe -> not a Safe
        # devProxyAdmin.owner() also entirely unresolved
        _patch_helpers(self, fake)

        result = scorers.score_pendle_v2(FakeW3())
        self.assertEqual(result["adminKeyScore"], 10)
        self.assertEqual(result["multisigScore"], 0)


# --------------------------------------------------------------------- LayerZero V2 messaging infra (Robinhood Chain)
class TestScoreLayerzeroInfra(unittest.TestCase):
    ENDPOINT = "0x6F475642a6e85809B1c36Fa62763669b1b48DD5B"
    SEND_ULN = "0xC39161c743D0307EB9BCc9FEF03eeb9Dc4802de7"
    RECEIVE_ULN = "0xe1844c5D63a9543023008D332Bd3d2e6f1FE1043"

    def test_all_three_agree_and_confirmed_as_bespoke_multisig(self):
        fake = FakeHelpers()
        for addr in (self.ENDPOINT, self.SEND_ULN, self.RECEIVE_ULN):
            fake.address_getters[(addr, "owner")] = ADDR_A
        fake.custom_multisig_results[ADDR_A] = (_owners(7), 5)  # 5-of-7
        _patch_helpers(self, fake)

        results = scorers.score_layerzero_infra(FakeW3())
        self.assertEqual(len(results), 3)
        self.assertEqual({r["target"] for r in results}, {self.ENDPOINT, self.SEND_ULN, self.RECEIVE_ULN})
        for r in results:
            # CORRECTED 2026-09-21: multisig was `threshold * 8` = 40; it is now 5*15 + 2*5 = 85, composite 48 (was 34).
            self.assertEqual(
                (r["adminKeyScore"], r["multisigScore"], r["timelockScore"]),
                (55, 85, 0),
            )
            self.assertEqual(r["compositeScore"], 48)
            self.assertFalse(any("WARNING" in n for n in r["notes"]))
        # notes (and therefore compositeScore) are the SAME shared list/value across all 3 entries
        self.assertEqual(results[0]["compositeScore"], results[1]["compositeScore"])

    def test_owner_neither_safe_nor_bespoke_multisig_degrades_to_20_0(self):
        fake = FakeHelpers()
        for addr in (self.ENDPOINT, self.SEND_ULN, self.RECEIVE_ULN):
            fake.address_getters[(addr, "owner")] = ADDR_A
        # ADDR_A deliberately absent from custom_multisig_results -> None
        _patch_helpers(self, fake)

        results = scorers.score_layerzero_infra(FakeW3())
        for r in results:
            self.assertEqual(
                (r["adminKeyScore"], r["multisigScore"], r["timelockScore"]),
                (20, 0, 0),
            )

    def test_multisig_score_is_capped_at_100(self):
        fake = FakeHelpers()
        for addr in (self.ENDPOINT, self.SEND_ULN, self.RECEIVE_ULN):
            fake.address_getters[(addr, "owner")] = ADDR_A
        fake.custom_multisig_results[ADDR_A] = (_owners(20), 15)  # 15*15 + 5*5 = 250 -> capped
        _patch_helpers(self, fake)

        results = scorers.score_layerzero_infra(FakeW3())
        self.assertEqual(results[0]["multisigScore"], 100)

    def test_owner_disagreement_across_targets_adds_dedicated_warning_note(self):
        fake = FakeHelpers()
        fake.address_getters[(self.ENDPOINT, "owner")] = ADDR_A
        fake.address_getters[(self.SEND_ULN, "owner")] = ADDR_B  # disagrees with EndpointV2
        fake.address_getters[(self.RECEIVE_ULN, "owner")] = ADDR_A
        fake.custom_multisig_results[ADDR_A] = (_owners(7), 5)
        _patch_helpers(self, fake)

        results = scorers.score_layerzero_infra(FakeW3())
        self.assertTrue(any("WARNING" in n and "SendUln302" in n for n in results[0]["notes"]))
        # resolution still proceeds using EndpointV2's (targets[0]'s) owner
        self.assertEqual(results[0]["adminKeyScore"], 55)
        self.assertEqual(results[0]["multisigScore"], 85)


# --------------------------------------------------------------------- Snuggle: MaxFi Robinhood vault
class TestScoreSnuggleMaxfiVault(unittest.TestCase):
    VAULT = "0x1195C074F898b7644bA732407619c9804dFE6DCE"
    PROXY_ADMIN = ADDR_A
    SATELLITE = RealWeb3.to_checksum_address("0x" + "33" * 20)
    EOA1 = RealWeb3.to_checksum_address("0x" + "11" * 20)
    EOA2 = RealWeb3.to_checksum_address("0x" + "22" * 20)

    def _confirmed_satellite(self, fake):
        fake.address_getters[(self.VAULT, "adminSatellite")] = self.SATELLITE
        fake.call_raw_results[(self.SATELLITE, "TIMELOCK_DELAY", ())] = 86400

    def test_confirmed_bare_eoa_same_key_scores_2(self):
        fake = FakeHelpers()
        fake.slot_results[(self.VAULT, scorers.EIP1967_ADMIN_SLOT)] = self.PROXY_ADMIN
        fake.address_getters[(self.PROXY_ADMIN, "owner")] = self.EOA1
        fake.address_getters[(self.VAULT, "owner")] = self.EOA1  # same key both sides
        self._confirmed_satellite(fake)
        _patch_helpers(self, fake)

        fake_w3 = FakeW3(codes={self.EOA1: b""})  # bare EOA: zero-length code
        result = scorers.score_snuggle_maxfi_vault(fake_w3)
        self.assertEqual(
            (result["adminKeyScore"], result["multisigScore"], result["timelockScore"]),
            (2, 0, 0),
        )

    def test_confirmed_bare_eoa_different_keys_scores_5(self):
        fake = FakeHelpers()
        fake.slot_results[(self.VAULT, scorers.EIP1967_ADMIN_SLOT)] = self.PROXY_ADMIN
        fake.address_getters[(self.PROXY_ADMIN, "owner")] = self.EOA1
        fake.address_getters[(self.VAULT, "owner")] = self.EOA2  # different EOA -> same_key False
        _patch_helpers(self, fake)

        # controller = pa_owner or vault_owner -> pa_owner (EOA1) wins
        fake_w3 = FakeW3(codes={self.EOA1: b""})
        result = scorers.score_snuggle_maxfi_vault(fake_w3)
        self.assertEqual(result["adminKeyScore"], 5)

    def test_eip7702_delegated_controller_treated_as_eoa_equivalent(self):
        # Dedicated test for the EIP-7702 designator-prefix detection
        # (`is_7702`) -- a real, specific code path, not just "has code or
        # not": 23 bytes total, 0xef0100 followed by the 20-byte delegate
        # address, exactly the shape EIP-7702 wallets leave on-chain.
        delegated_code = b"\xef\x01\x00" + b"\x11" * 20
        fake = FakeHelpers()
        fake.slot_results[(self.VAULT, scorers.EIP1967_ADMIN_SLOT)] = self.PROXY_ADMIN
        fake.address_getters[(self.PROXY_ADMIN, "owner")] = self.EOA1
        fake.address_getters[(self.VAULT, "owner")] = self.EOA1  # same key
        _patch_helpers(self, fake)

        fake_w3 = FakeW3(codes={self.EOA1: delegated_code})
        result = scorers.score_snuggle_maxfi_vault(fake_w3)
        self.assertEqual(result["adminKeyScore"], 2)  # same as a bare EOA, same_key True
        self.assertTrue(any("EIP-7702 delegated = True" in n for n in result["notes"]))
        self.assertTrue(any("bare EOA = False" in n for n in result["notes"]))  # NOT the plain-EOA path

    def test_proxy_admin_owner_unresolved_falls_back_to_vault_owner(self):
        fake = FakeHelpers()
        # EIP-1967 admin slot deliberately absent -> proxy_admin None -> pa_owner None
        fake.address_getters[(self.VAULT, "owner")] = self.EOA1
        _patch_helpers(self, fake)

        fake_w3 = FakeW3(codes={self.EOA1: b""})
        result = scorers.score_snuggle_maxfi_vault(fake_w3)
        # controller = None or vault_owner = EOA1; same_key is False whenever pa_owner is None
        self.assertEqual(result["adminKeyScore"], 5)

    def test_controller_entirely_unresolved_fails_closed_to_5(self):
        fake = FakeHelpers()
        # neither the EIP-1967 admin slot nor vault.owner() resolve -> controller is None
        _patch_helpers(self, fake)

        result = scorers.score_snuggle_maxfi_vault(FakeW3())
        self.assertEqual(result["adminKeyScore"], 5)
        self.assertTrue(any("Controller did not resolve this run" in n for n in result["notes"]))

    def test_controller_is_now_a_real_safe_scores_40_with_warning(self):
        fake = FakeHelpers()
        fake.address_getters[(self.VAULT, "owner")] = self.EOA1
        fake.safe_results[self.EOA1] = (_owners(3), 2)
        _patch_helpers(self, fake)

        # EOA1 not in `codes` -> default 100 zero bytes: ordinary contract code, not a bare EOA
        result = scorers.score_snuggle_maxfi_vault(FakeW3())
        self.assertEqual(result["adminKeyScore"], 40)
        self.assertTrue(any("WARNING" in n and "now a Safe" in n for n in result["notes"]))

    def test_controller_has_code_but_is_not_a_resolvable_safe_scores_5_with_warning(self):
        fake = FakeHelpers()
        fake.address_getters[(self.VAULT, "owner")] = self.EOA1
        # EOA1 deliberately absent from safe_results -> not resolvable as a Safe
        _patch_helpers(self, fake)

        result = scorers.score_snuggle_maxfi_vault(FakeW3())
        self.assertEqual(result["adminKeyScore"], 5)
        self.assertTrue(any("WARNING" in n and "not a resolvable Safe" in n for n in result["notes"]))


# --------------------------------------------------------------------- Morpho Blue (singleton, Robinhood Chain)
class TestScoreMorphoBlueSingleton(unittest.TestCase):
    TARGET = "0x9D53d5E3bd5E8d4Cbfa6DB1ca238AEA02E651010"

    def test_five_of_nine_safe_matches_base_ecosystem_sibling_formula(self):
        # Mirrors chains/base-ecosystem/scorers.py::score_morpho_blue's own
        # formula for the identical protocol -- 5-of-9 -> admin_key=65,
        # multisig=min(100, 5*15 + 4*5)=95, timelock=0 (no TimelockController
        # anywhere in this chain, same as every other Safe-rooted target here).
        fake = FakeHelpers()
        fake.address_getters[(self.TARGET, "owner")] = ADDR_A
        fake.address_getters[(self.TARGET, "feeRecipient")] = None
        fake.safe_results[ADDR_A] = (_owners(9), 5)
        _patch_helpers(self, fake)

        result = scorers.score_morpho_blue_singleton(FakeW3())
        self.assertEqual(result["target"], self.TARGET)
        self.assertEqual(result["label"], "Morpho Blue (singleton, Robinhood Chain)")
        self.assertEqual(
            (result["adminKeyScore"], result["multisigScore"], result["timelockScore"]),
            (65, 95, 0),
        )
        self.assertEqual(result["compositeScore"], scorers._composite(65, 95, 0))
        self.assertTrue(any("real Gnosis Safe: 5-of-9" in n for n in result["notes"]))

    def test_two_of_three_safe_scores_50_and_multisig_capped_formula(self):
        fake = FakeHelpers()
        fake.address_getters[(self.TARGET, "owner")] = ADDR_A
        fake.address_getters[(self.TARGET, "feeRecipient")] = None
        fake.safe_results[ADDR_A] = (_owners(3), 2)
        _patch_helpers(self, fake)

        result = scorers.score_morpho_blue_singleton(FakeW3())
        self.assertEqual(
            (result["adminKeyScore"], result["multisigScore"], result["timelockScore"]),
            (50, 35, 0),
        )

    def test_owner_unresolved_as_safe_degrades_to_conservative_20_0_0(self):
        fake = FakeHelpers()
        fake.address_getters[(self.TARGET, "owner")] = ADDR_A
        fake.address_getters[(self.TARGET, "feeRecipient")] = None
        # ADDR_A deliberately absent from safe_results -> not resolvable as a Safe
        _patch_helpers(self, fake)

        result = scorers.score_morpho_blue_singleton(FakeW3())
        self.assertEqual(
            (result["adminKeyScore"], result["multisigScore"], result["timelockScore"]),
            (20, 0, 0),
        )
        self.assertTrue(any("NOT resolvable as a Gnosis Safe" in n for n in result["notes"]))

    def test_multisig_score_never_exceeds_100_cap(self):
        # threshold*15 + extra*5 could exceed 100 for a large enough Safe --
        # confirms the min(100, ...) cap actually holds, not just for 5-of-9.
        fake = FakeHelpers()
        fake.address_getters[(self.TARGET, "owner")] = ADDR_A
        fake.address_getters[(self.TARGET, "feeRecipient")] = None
        fake.safe_results[ADDR_A] = (_owners(20), 10)  # 10*15 + 10*5 = 200, uncapped
        _patch_helpers(self, fake)

        result = scorers.score_morpho_blue_singleton(FakeW3())
        self.assertEqual(result["multisigScore"], 100)


# --------------------------------------------------------------------- NOXA Fun Launch Locker
class TestScoreNoxaFunLaunchLocker(unittest.TestCase):
    LOCKER = "0x7F03effbd7ceB22A3f80Dd468f67eF27826acD85"
    POSITION_MANAGER = "0x73991a25C818Bf1f1128dEAaB1492D45638DE0D3"

    def _balance_key(self, addr):
        return (self.POSITION_MANAGER, "balanceOf", (RealWeb3.to_checksum_address(addr),))

    def test_bare_eoa_owner_scores_5_0_0(self):
        fake = FakeHelpers()
        fake.address_getters[(self.LOCKER, "owner")] = ADDR_A
        fake.eoa_results[ADDR_A] = True
        fake.call_raw_results[self._balance_key(self.LOCKER)] = 60142
        _patch_helpers(self, fake)

        result = scorers.score_noxa_fun_launch_locker(FakeW3())
        self.assertEqual(result["target"], self.LOCKER)
        self.assertEqual(result["label"], "NOXA Fun Launch Locker")
        self.assertEqual(
            (result["adminKeyScore"], result["multisigScore"], result["timelockScore"]),
            (5, 0, 0),
        )
        self.assertEqual(result["compositeScore"], scorers._composite(5, 0, 0))
        self.assertTrue(any("bare EOA = True" in n for n in result["notes"]))
        self.assertTrue(any("60142 live Uniswap V3 LP NFTs" in n for n in result["notes"]))

    def test_owner_resolves_to_a_real_contract_scores_40(self):
        fake = FakeHelpers()
        fake.address_getters[(self.LOCKER, "owner")] = ADDR_A
        fake.eoa_results[ADDR_A] = False
        fake.call_raw_results[self._balance_key(self.LOCKER)] = 60142
        _patch_helpers(self, fake)

        result = scorers.score_noxa_fun_launch_locker(FakeW3())
        self.assertEqual(
            (result["adminKeyScore"], result["multisigScore"], result["timelockScore"]),
            (40, 0, 0),
        )

    def test_owner_unresolved_degrades_to_conservative_40(self):
        fake = FakeHelpers()
        # LOCKER deliberately absent from address_getters -> owner() unresolved
        _patch_helpers(self, fake)

        result = scorers.score_noxa_fun_launch_locker(FakeW3())  # must not raise
        self.assertEqual(result["adminKeyScore"], 40)
        self.assertTrue(any("owner() unresolved this run" in n for n in result["notes"]))


# --------------------------------------------------------------------- UNCX Network V3 Locker
class TestScoreUncxV3Locker(unittest.TestCase):
    LOCKER = "0xF28704c691290547924e2129D407dA36bda8ce0f"

    def test_two_of_three_safe_scores_50_35_0(self):
        # Rotation audit index 10 (2026-09-19): real owner() is a confirmed
        # 2-of-3 Safe -- same threshold-aware formula as
        # score_morpho_blue_singleton()'s own 2-of-3 case (50, 35, 0).
        fake = FakeHelpers()
        fake.address_getters[(self.LOCKER, "owner")] = ADDR_A
        fake.safe_results[ADDR_A] = (_owners(3), 2)
        _patch_helpers(self, fake)

        result = scorers.score_uncx_v3_locker(FakeW3())
        self.assertEqual(result["target"], self.LOCKER)
        self.assertEqual(result["label"], "UNCX Network V3 Locker (Robinhood Chain)")
        self.assertEqual(
            (result["adminKeyScore"], result["multisigScore"], result["timelockScore"]),
            (50, 35, 0),
        )
        self.assertEqual(result["compositeScore"], scorers._composite(50, 35, 0))
        self.assertTrue(any("real Gnosis Safe: 2-of-3" in n for n in result["notes"]))

    def test_larger_safe_uses_threshold_and_extra_owner_terms(self):
        fake = FakeHelpers()
        fake.address_getters[(self.LOCKER, "owner")] = ADDR_A
        fake.safe_results[ADDR_A] = (_owners(9), 5)
        _patch_helpers(self, fake)

        result = scorers.score_uncx_v3_locker(FakeW3())
        self.assertEqual(
            (result["adminKeyScore"], result["multisigScore"], result["timelockScore"]),
            (65, 95, 0),
        )

    def test_owner_unresolved_as_safe_degrades_to_conservative_20_0_0(self):
        fake = FakeHelpers()
        fake.address_getters[(self.LOCKER, "owner")] = ADDR_A
        # ADDR_A deliberately absent from safe_results -> not resolvable as a Safe
        _patch_helpers(self, fake)

        result = scorers.score_uncx_v3_locker(FakeW3())
        self.assertEqual(
            (result["adminKeyScore"], result["multisigScore"], result["timelockScore"]),
            (20, 0, 0),
        )
        self.assertTrue(any("NOT resolvable as a Gnosis Safe" in n for n in result["notes"]))


class TestScoreArcusPerpsBridgevault(unittest.TestCase):
    """score_arcus_perps_bridgevault() -- rotation audit batch, 2026-09-19
    (new-target search while auditing index 11). Root mechanism is a
    2-of-3 bare-EOA `ValidatorConsensus` threshold, not a Gnosis Safe --
    exercised here via the enumerable-role fake dispatch (getRoleMemberCount/
    getRoleMember), same FakeHelpers.call_raw_results table
    score_layerzero_infra()'s custom-multisig test already uses, just with a
    bytes32 role argument instead of that scorer's own ABI shape."""

    BRIDGE_VAULT = "0x14b107cf534239c59571b066cb6497a321da897c"
    VALIDATOR_CONSENSUS = "0x9d032106aE6e41F36132Fff1e7b0d973B4e55Da8"
    TIMELOCK = "0x0dA180B14721CE46A83669b4816cb652caa1001D"
    CHECKPOINT_MANAGER = "0xA3D46D248224070f58C5F750E1f2fcA2123DF487"
    DEFAULT_ADMIN_ROLE = bytes(32)
    VALIDATOR_ROLE = RealWeb3.keccak(text="VALIDATOR_ROLE")

    def _wire_admin_holders(self, fake, holders):
        fake.call_raw_results[(self.BRIDGE_VAULT, "getRoleMemberCount", (self.DEFAULT_ADMIN_ROLE,))] = len(holders)
        for i, h in enumerate(holders):
            fake.call_raw_results[(self.BRIDGE_VAULT, "getRoleMember", (self.DEFAULT_ADMIN_ROLE, i))] = h

    def _wire_validators(self, fake, threshold, validators):
        fake.call_raw_results[(self.VALIDATOR_CONSENSUS, "threshold", ())] = threshold
        fake.call_raw_results[(self.VALIDATOR_CONSENSUS, "getRoleMemberCount", (self.VALIDATOR_ROLE,))] = len(validators)
        for i, v in enumerate(validators):
            fake.call_raw_results[(self.VALIDATOR_CONSENSUS, "getRoleMember", (self.VALIDATOR_ROLE, i))] = v

    def _wire_default_admin_trio(self, fake):
        self._wire_admin_holders(fake, [self.TIMELOCK, self.VALIDATOR_CONSENSUS, self.CHECKPOINT_MANAGER])

    def _wire_timelock(self, fake, min_delay=86400):
        fake.call_raw_results[(self.TIMELOCK, "getMinDelay", ())] = min_delay

    def test_two_of_three_validator_quorum_scores_50_35_0(self):
        fake = FakeHelpers()
        validators = _owners(3)
        self._wire_default_admin_trio(fake)
        self._wire_validators(fake, 2, validators)
        for v in validators:
            fake.eoa_results[v] = True
        self._wire_timelock(fake)
        _patch_helpers(self, fake)

        result = scorers.score_arcus_perps_bridgevault(FakeW3())
        self.assertEqual(result["target"], self.BRIDGE_VAULT)
        self.assertEqual(result["label"], "Arcus Perps BridgeVault (Robinhood Chain)")
        self.assertEqual(
            (result["adminKeyScore"], result["multisigScore"], result["timelockScore"]),
            (50, 35, 0),
        )
        self.assertEqual(result["compositeScore"], scorers._composite(50, 35, 0))
        self.assertTrue(any("does NOT gate the operative path" in n for n in result["notes"]))

    def test_three_of_n_validator_threshold_scores_65(self):
        fake = FakeHelpers()
        validators = _owners(5)
        self._wire_default_admin_trio(fake)
        self._wire_validators(fake, 3, validators)
        for v in validators:
            fake.eoa_results[v] = True
        self._wire_timelock(fake)
        _patch_helpers(self, fake)

        result = scorers.score_arcus_perps_bridgevault(FakeW3())
        self.assertEqual(
            (result["adminKeyScore"], result["multisigScore"], result["timelockScore"]),
            (65, min(100, 3 * 15 + 2 * 5), 0),
        )

    def test_admin_role_holders_no_longer_match_expected_trio_degrades_conservatively(self):
        fake = FakeHelpers()
        # Only 1 holder now instead of the expected {Timelock, ValidatorConsensus,
        # CheckpointManager} -- the authority chain changed since this scorer was
        # written; must not silently keep scoring the old shape.
        self._wire_admin_holders(fake, [ADDR_A])
        _patch_helpers(self, fake)

        result = scorers.score_arcus_perps_bridgevault(FakeW3())
        self.assertEqual(
            (result["adminKeyScore"], result["multisigScore"], result["timelockScore"]),
            (10, 0, 0),
        )
        self.assertTrue(any("DIVERGENCE" in n for n in result["notes"]))

    def test_non_eoa_validator_degrades_to_conservative_10_0_0(self):
        fake = FakeHelpers()
        validators = _owners(3)
        self._wire_default_admin_trio(fake)
        self._wire_validators(fake, 2, validators)
        fake.eoa_results[validators[0]] = False  # one validator seat is itself a contract, not a bare key
        self._wire_timelock(fake)
        _patch_helpers(self, fake)

        result = scorers.score_arcus_perps_bridgevault(FakeW3())
        self.assertEqual(
            (result["adminKeyScore"], result["multisigScore"], result["timelockScore"]),
            (10, 0, 0),
        )


class TestScoreT3trisVault(unittest.TestCase):
    """score_t3tris_vault() -- rotation audit, new-target search while
    auditing index 12 (2026-09-19). AccessControl `hasRole(DEFAULT_ADMIN_ROLE,
    knownAdmin)` live-checked every run (the same `known_admin` + `call_raw`
    pattern score_stock_token() already uses for its beacon's
    DEFAULT_ADMIN_ROLE), not a full RoleGranted/RoleRevoked replay every run
    -- the replay was one-time discovery work, documented in the scorer's own
    docstring, not something this scorer repeats live."""

    VAULT = "0xd5c6c79692715145098a65d1eb1f2a10c524f8e8"
    KNOWN_ADMIN = RealWeb3.to_checksum_address("0x65D02Bb13f515DD105Fb733E9E31f11A2F65e57f")
    DEFAULT_ADMIN_ROLE = bytes(32)

    def _has_role_key(self):
        return (self.VAULT, "hasRole", (self.DEFAULT_ADMIN_ROLE, self.KNOWN_ADMIN))

    def _gross_tvl_key(self):
        return (self.VAULT, "getGrossTVL", ())

    def test_bare_eoa_still_holds_default_admin_role_scores_5_0_0(self):
        fake = FakeHelpers()
        fake.call_raw_results[self._has_role_key()] = True
        fake.eoa_results[self.KNOWN_ADMIN] = True
        fake.call_raw_results[self._gross_tvl_key()] = (734701760, 100753, 14238936, 749041449)
        _patch_helpers(self, fake)

        result = scorers.score_t3tris_vault(FakeW3())
        self.assertEqual(result["target"], self.VAULT)
        self.assertEqual(result["label"], "T3tris Finance WBTC vault (Robinhood Chain)")
        self.assertEqual(
            (result["adminKeyScore"], result["multisigScore"], result["timelockScore"]),
            (5, 0, 0),
        )
        self.assertEqual(result["compositeScore"], scorers._composite(5, 0, 0))
        self.assertTrue(any("bare EOA = True" in n for n in result["notes"]))

    def test_admin_role_now_held_by_a_contract_scores_40(self):
        fake = FakeHelpers()
        fake.call_raw_results[self._has_role_key()] = True
        fake.eoa_results[self.KNOWN_ADMIN] = False
        fake.call_raw_results[self._gross_tvl_key()] = (734701760, 0, 0, 734701760)
        _patch_helpers(self, fake)

        result = scorers.score_t3tris_vault(FakeW3())
        self.assertEqual(
            (result["adminKeyScore"], result["multisigScore"], result["timelockScore"]),
            (40, 0, 0),
        )
        self.assertTrue(any("WARNING: DEFAULT_ADMIN_ROLE holder is now a contract" in n for n in result["notes"]))

    def test_role_rotated_away_from_known_admin_degrades_conservatively(self):
        fake = FakeHelpers()
        fake.call_raw_results[self._has_role_key()] = False
        _patch_helpers(self, fake)

        result = scorers.score_t3tris_vault(FakeW3())  # must not raise
        self.assertEqual(
            (result["adminKeyScore"], result["multisigScore"], result["timelockScore"]),
            (40, 0, 0),
        )
        self.assertTrue(any("role rotated" in n for n in result["notes"]))


if __name__ == "__main__":
    unittest.main()
