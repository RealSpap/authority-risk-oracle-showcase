"""
Unit tests for the Morpho Vault V2 scoring added 2026-09-26 (Spap's go-ahead, see METHODOLOGY.md's
"Morpho Vault V2 scoring" section for the 3 methodology decisions this code applies).

Same FakeHelpers monkeypatch approach as test_new_targets_2026_09_25.py -- no network, no RPC. This
file additionally patches `read_address_getter` (not needed by that sibling file's targets, which all
used `call_raw` directly for their owner-hop reads) since `_score_steakhouse_v2_vault` reads
owner()/curator() through it, matching the same convention `_score_steakhouse_l1_vault` (untested by
mock, live-dry-run-only) already established -- covered here instead because the V2 path adds real
new logic (the timelock-banding thresholds, the per-gate abdication read) that V1's sibling doesn't
have.

Run:  PYTHONPATH=. python3 -m unittest discover -s chains/ethereum-l1/tests -v
"""
import importlib.util
import os
import sys
import unittest

from web3 import Web3 as RealWeb3

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts", "lib"))


def _load(name, rel):
    path = os.path.join(REPO_ROOT, rel)
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


scorers = _load("aro_eth_l1_vault_v2_2026_09_26", "chains/ethereum-l1/scorers.py")
cs = RealWeb3.to_checksum_address

VAULT = cs("0xbeef088055857739C12CD3765F20b7679Def0f51")
SUPERVISOR = cs("0x4D7bd498Bb24098Ca281C05519629c605407f71d")
OWNER_SAFE = cs(scorers._KNOWN_STEAKHOUSE_OWNER_SAFE_2026_09_25)
CURATOR_SAFE = cs(scorers._KNOWN_STEAKHOUSE_CURATOR_SAFE_2026_09_25)
DAY = 86400


class FakeHelpers:
    def __init__(self):
        self.addrs = {}
        self.calls = {}
        self.safes = {}

    def read_address_getter(self, w3, address, name, retries=4):
        return self.addrs.get((cs(address), name))

    def call_raw(self, w3, address, abi_fragment, function_name, *args, retries=4):
        return self.calls.get((cs(address), function_name, args))

    def safe_owners_and_threshold(self, w3, address, retries=4):
        return self.safes.get(cs(address))


class FakeW3:
    @staticmethod
    def to_checksum_address(addr):
        return cs(addr)


def _patch(tc, fake):
    names = ["read_address_getter", "call_raw", "safe_owners_and_threshold"]
    orig = {n: getattr(scorers, n) for n in names}
    for n in names:
        setattr(scorers, n, getattr(fake, n))
    tc.addCleanup(lambda: [setattr(scorers, n, orig[n]) for n in names])


def _owners(n, start=1):
    return [cs("0x" + hex(i)[2:].zfill(40)) for i in range(start, start + n)]


def _selector(sig):
    return RealWeb3.keccak(text=sig)[:4]


def _base_fake(owner_threshold=5, owner_n=10, curator_threshold=2, curator_n=7,
               fund_delay_days=7, abdicated=(True, True, True, False), gate_delay_days=7):
    """All four `_FUND_REDIRECTING_FUNCTION_SIGS` at `fund_delay_days`; the four exit gates
    abdicated per the `abdicated` tuple (receive-shares, send-shares, receive-assets, send-assets),
    a NOT-abdicated gate reading `gate_delay_days`."""
    f = FakeHelpers()
    f.addrs[(VAULT, "owner")] = SUPERVISOR
    f.addrs[(VAULT, "curator")] = CURATOR_SAFE
    f.addrs[(SUPERVISOR, "owner")] = OWNER_SAFE
    f.safes[OWNER_SAFE] = (_owners(owner_n, start=1), owner_threshold)
    f.safes[CURATOR_SAFE] = (_owners(curator_n, start=100), curator_threshold)
    for sig in scorers._FUND_REDIRECTING_FUNCTION_SIGS:
        f.calls[(VAULT, "timelock", (_selector(sig),))] = fund_delay_days * DAY
    gate_sigs = list(scorers._EXIT_GATE_FUNCTION_SIGS.values())
    for sig, is_abdicated in zip(gate_sigs, abdicated):
        f.calls[(VAULT, "abdicated", (_selector(sig),))] = is_abdicated
        if not is_abdicated:
            f.calls[(VAULT, "timelock", (_selector(sig),))] = gate_delay_days * DAY
    return f


class TestScoreSteakhousePrimeUsdcV2(unittest.TestCase):
    def test_resolved_matches_known_steakhouse_safes(self):
        _patch(self, _base_fake())
        r = scorers.score_morpho_steakhouse_prime_usdc_v2(FakeW3())
        self.assertEqual(r["target"], VAULT)
        self.assertEqual(
            (r["adminKeyScore"], r["multisigScore"], r["timelockScore"], r["oracleAuthorityScore"], r["compositeScore"]),
            (70, 55, 75, 100, 67),
        )
        self.assertEqual(r["_rootGroup"], "steakhouse-owner-safe-0x0a0e559b")

    def test_abdicated_gates_disclosed_individually_not_as_one_flag(self):
        _patch(self, _base_fake())
        r = scorers.score_morpho_steakhouse_prime_usdc_v2(FakeW3())
        joined = " ".join(r["notes"])
        self.assertIn("receive shares gate: permanently abdicated", joined)
        self.assertIn("send shares gate: permanently abdicated", joined)
        self.assertIn("receive assets gate: permanently abdicated", joined)
        self.assertIn("send assets gate: NOT abdicated", joined)
        self.assertIn("7-day timelock", joined)

    def test_timelock_score_bands_on_the_minimum_delay_not_the_maximum(self):
        # One fund-redirecting function at 3 days should cap timelockScore at the 3-day band (60)
        # even though every other function (and every live gate) is at 7 days -- the worst realistic
        # path, not the best one, matching this project's established convention.
        f = _base_fake()
        f.calls[(VAULT, "timelock", (_selector("removeAdapter(address)"),))] = 3 * DAY
        _patch(self, f)
        r = scorers.score_morpho_steakhouse_prime_usdc_v2(FakeW3())
        self.assertEqual(r["timelockScore"], 60)

    def test_zero_delay_fund_redirecting_function_zeroes_timelock_score(self):
        f = _base_fake()
        f.calls[(VAULT, "timelock", (_selector("addAdapter(address)"),))] = 0
        _patch(self, f)
        r = scorers.score_morpho_steakhouse_prime_usdc_v2(FakeW3())
        self.assertEqual(r["timelockScore"], 0)

    def test_all_gates_abdicated_does_not_crash_or_misclassify(self):
        _patch(self, _base_fake(abdicated=(True, True, True, True)))
        r = scorers.score_morpho_steakhouse_prime_usdc_v2(FakeW3())
        # Still 75: the fund-redirecting functions (not gates) set the 7-day floor here.
        self.assertEqual(r["timelockScore"], 75)
        self.assertNotIn("NOT abdicated", " ".join(r["notes"]))

    def test_owner_mismatch_degrades_rather_than_guesses(self):
        f = _base_fake()
        f.addrs[(SUPERVISOR, "owner")] = cs("0x" + "cd" * 20)
        _patch(self, f)
        r = scorers.score_morpho_steakhouse_prime_usdc_v2(FakeW3())
        self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["timelockScore"]), (20, 20, 0))
        self.assertIn("did NOT match the known Steakhouse Safes", " ".join(r["notes"]))

    def test_curator_mismatch_degrades_rather_than_guesses(self):
        f = _base_fake()
        f.addrs[(VAULT, "curator")] = cs("0x" + "ef" * 20)
        _patch(self, f)
        r = scorers.score_morpho_steakhouse_prime_usdc_v2(FakeW3())
        self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["timelockScore"]), (20, 20, 0))


class TestScoreSteakhousePrimeEurcvV2(unittest.TestCase):
    def test_different_vault_address_same_shared_safes(self):
        vault2 = cs("0xbeef0C075Da5D01112AE5cF34d257074fB5DDB2f")
        f = FakeHelpers()
        f.addrs[(vault2, "owner")] = SUPERVISOR
        f.addrs[(vault2, "curator")] = CURATOR_SAFE
        f.addrs[(SUPERVISOR, "owner")] = OWNER_SAFE
        f.safes[OWNER_SAFE] = (_owners(10, start=1), 5)
        f.safes[CURATOR_SAFE] = (_owners(7, start=100), 2)
        for sig in scorers._FUND_REDIRECTING_FUNCTION_SIGS:
            f.calls[(vault2, "timelock", (_selector(sig),))] = 7 * DAY
        for sig in scorers._EXIT_GATE_FUNCTION_SIGS.values():
            f.calls[(vault2, "abdicated", (_selector(sig),))] = True
        _patch(self, f)
        r = scorers.score_morpho_steakhouse_prime_eurcv_v2(FakeW3())
        self.assertEqual(r["target"], vault2)
        self.assertEqual(r["_rootGroup"], "steakhouse-owner-safe-0x0a0e559b")


if __name__ == "__main__":
    unittest.main()
