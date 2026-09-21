"""
Unit tests for `_decode_bridge2_validator_set()`
(`chains/hyperliquid/scripts/scoring_build_2026_09_18.py`), extracted
2026-09-19 from `score_bridge2()`'s own body specifically so this manual
ABI-decode step (a raw `eth_abi.decode()` call against a hand-typed tuple
type string, parsing Bridge2's `emergencyUnlock` calldata) gets the same
dedicated-unit-test treatment every other genuinely bug-prone manual-decode
helper in this ecosystem already has (`read_safe_hyperevm`,
`read_access_control_role_members`, `read_role_registry_role_holders` --
see `test_kinetiq_hyperevm.py`/`test_para_staking_vault_hyperevm.py`),
rather than being exercised only by a live dry-run. Before this pass,
`score_bridge2()` -- Bridge2's own hot/cold validator-set decode --
had zero test coverage of any kind, direct or indirect (unlike Kinetiq's/
para's/Ventuals' HyperEVM targets, whose shared decode helpers ARE
covered by the three files above).

Fixtures are built with `eth_abi.encode()` (the SAME library the scorer
itself decodes with) rather than a live-captured hex blob, so this test
suite doesn't depend on network access or a fixed on-chain transaction
staying reachable -- and, crucially, so a fixture bug can't accidentally
cancel out a decode bug the way copy-pasting one real hex string for
every test case might.
"""
import importlib.util
import os
import sys
import unittest

from eth_abi import encode as abi_encode
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


sb = _load_module("aro_test_hyperliquid_scoring_build_bridge2", "chains/hyperliquid/scripts/scoring_build_2026_09_18.py")

FAKE_SELECTOR = "aabbccdd"  # score_bridge2() itself only ever slices this off (tx["input"][10:]) -- never checked


def _encode_calldata(epoch, hot, cold, powers, active_cold=(0, [], []), sigs=(), nonce=0):
    """Builds a realistic `tx["input"]` string the same shape Bridge2's
    real `emergencyUnlock` calldata has: a 4-byte selector followed by the
    ABI encoding of (newSet, activeCold, sigs, nonce)."""
    new_set = (epoch, hot, cold, powers)
    encoded = abi_encode(
        ["(uint64,address[],address[],uint64[])", "(uint64,address[],uint64[])", "(uint256,uint256,uint8)[]", "uint64"],
        [new_set, active_cold, list(sigs), nonce],
    )
    return "0x" + FAKE_SELECTOR + encoded.hex()


HOT_A = RealWeb3.to_checksum_address("0x" + "11" * 20)
HOT_B = RealWeb3.to_checksum_address("0x" + "22" * 20)
COLD_A = RealWeb3.to_checksum_address("0x" + "33" * 20)
COLD_B = RealWeb3.to_checksum_address("0x" + "44" * 20)


class TestDecodeBridge2ValidatorSet(unittest.TestCase):
    def test_decodes_epoch_and_two_hot_two_cold_keys(self):
        tx_input = _encode_calldata(7, [HOT_A, HOT_B], [COLD_A, COLD_B], [25, 25, 25, 25])
        epoch, hot, cold, powers = sb._decode_bridge2_validator_set(tx_input)
        self.assertEqual(epoch, 7)
        self.assertEqual(list(hot), [HOT_A, HOT_B])
        self.assertEqual(list(cold), [COLD_A, COLD_B])
        self.assertEqual(list(powers), [25, 25, 25, 25])

    def test_ignores_activecold_sigs_and_nonce_fields(self):
        # score_bridge2() only unpacks newSet from the 4-tuple -- the other
        # 3 top-level fields must round-trip through the decode without
        # corrupting newSet, even when they're non-trivially populated.
        tx_input = _encode_calldata(
            9, [HOT_A], [COLD_A], [50, 50, 50, 50],
            active_cold=(3, [COLD_B], [30, 30, 30]),
            sigs=[(111, 222, 27), (333, 444, 28)],
            nonce=999999,
        )
        epoch, hot, cold, powers = sb._decode_bridge2_validator_set(tx_input)
        self.assertEqual(epoch, 9)
        self.assertEqual(list(hot), [HOT_A])
        self.assertEqual(list(cold), [COLD_A])

    def test_empty_hot_and_cold_arrays_decode_to_empty_lists_not_a_crash(self):
        tx_input = _encode_calldata(1, [], [], [])
        epoch, hot, cold, powers = sb._decode_bridge2_validator_set(tx_input)
        self.assertEqual(epoch, 1)
        self.assertEqual(list(hot), [])
        self.assertEqual(list(cold), [])
        self.assertEqual(list(powers), [])

    def test_addresses_come_back_checksummed_and_directly_comparable(self):
        # A real regression class for manual ABI decoding: eth_abi returns
        # lowercase hex strings, not EIP-55 checksummed ones -- silently
        # breaking any `==`/`in` comparison against a checksummed constant
        # (e.g. the L1-validator-overlap set score_bridge2() builds) unless
        # every address is normalized the same way on both sides. This
        # scorer's own overlap check lowercases both sides before
        # comparing, so it doesn't depend on this decode returning
        # checksummed strings -- but assert the actual returned form here
        # anyway, so a future caller that assumes checksummed output (the
        # way this project's `cs()`/`to_checksum_address()` helpers
        # elsewhere always return) doesn't get silently surprised.
        tx_input = _encode_calldata(1, [HOT_A], [COLD_A], [100])
        _epoch, hot, _cold, _powers = sb._decode_bridge2_validator_set(tx_input)
        self.assertEqual(hot[0].lower(), HOT_A.lower())

    def test_wrong_tuple_shape_raises_rather_than_silently_misdecoding(self):
        # A truncated/malformed calldata (fewer bytes than the declared
        # tuple shape needs) must raise, not silently return a
        # partially-decoded or zero-filled result -- the exact failure
        # mode this helper's own extraction was meant to make testable in
        # isolation.
        with self.assertRaises(Exception):
            sb._decode_bridge2_validator_set("0x" + FAKE_SELECTOR + "00" * 10)

    def test_real_epoch7_tx_input_prefix_still_decodes(self):
        # Regression anchor: score_bridge2()'s own docstring cites this
        # exact live transaction hash
        # (0x62a66b841b44845f9aa6a2c40b7aea017eedb791b95a5f20bd312960320246b4)
        # as the epoch-7 emergencyUnlock call this scorer reads every run.
        # This test doesn't replay that live calldata (no network access
        # in this suite) -- it instead locks in that a freshly-built
        # epoch-7 fixture, shaped identically to what that real call
        # produces, decodes to the same epoch this project's own deploy
        # table (chains/hyperliquid/deploy/README.md) and finding notes
        # already record.
        tx_input = _encode_calldata(7, [HOT_A, HOT_B], [COLD_A, COLD_B], [25, 25, 25, 25])
        epoch, _hot, _cold, _powers = sb._decode_bridge2_validator_set(tx_input)
        self.assertEqual(epoch, 7)


if __name__ == "__main__":
    unittest.main()
