"""
Unit tests for the 3 verified Ethereum L1 changes made on 2026-09-25:

1. TVL refresh for score_lido_steth / score_eigenlayer_strategy_manager -- documentation-only
   (prose in the docstring), no computed value depends on it, so it is not separately tested here.
2. score_eigenlayer_strategy_manager's new Pauser disclosure: StrategyManager.pauserRegistry() ->
   a 1-of-7 Gnosis Safe that can pause() the whole contract instantly. Disclosed in the notes only
   -- must NOT move the 3 existing sub-scores (see this function's own docstring for why no
   convention in this file supports stacking a second bypass discount on the one already scored).
3. score_convex_finance_booster, a brand-new target: a 3-hop chain (Booster -> BoosterOwner
   (sealed, 30-day FORCE_DELAY) -> BoosterOwnerSecondary (unsealed) -> a Gnosis Safe), scored with
   the same Ethereum L1 Safe rule as score_morpho_blue_l1() / score_aave_v3_horizon_pool().

Same FakeHelpers monkeypatch approach as the other files in this directory (e.g.
test_new_targets_2026_09_20.py): no network, no RPC.

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


scorers = _load("aro_eth_l1_targets_2026_09_25", "chains/ethereum-l1/scorers.py")
cs = RealWeb3.to_checksum_address

# EigenLayer addresses, as already used by test_new_targets_2026_09_20.py.
EIGEN_SM = cs("0x858646372CC42E1A627fcE94aa7A7033e7CF075A")
EIGEN_PROXY_ADMIN = cs("0x8b9566AdA63B64d1E1dcF1418b43fd1433b72444")
EIGEN_EXECUTOR = cs("0x369e6F597e22EaB55fFb173C6d9cD234BD699111")
EIGEN_TIMELOCK = cs("0xC06Fd4F821eaC1fF1ae8067b36342899b57BAa2d")
EIGEN_COMMUNITY = cs("0xFEA47018D632A77bA579846c840d5706705Dc598")
EIGEN_PAUSER_REGISTRY = cs("0xb8765ED72235D279C3fB53936e4606DB0EF12806")
EIGEN_PAUSER_SAFE = cs("0x5050389572f2D220aD927CCbeA0D406831012390")

# Convex Finance addresses (see score_convex_finance_booster's docstring).
CONVEX_BOOSTER = cs("0xF403C135812408BFbE8713b5A23a04b3D48AAE31")
CONVEX_BOOSTER_OWNER = cs("0x3cE6408F923326f81A7D7929952947748180f1E6")
CONVEX_BOOSTER_OWNER_SECONDARY = cs("0x256e1bba846611c37cf89844a02435e6c098b86d")
CONVEX_SAFE = cs("0xa3C5A1e09150B75ff251c1a7815A07182c3de2FB")


class FakeHelpers:
    def __init__(self):
        self.calls = {}
        self.safes = {}
        self.slots = {}
        self.eoas = set()

    def call_raw(self, w3, address, abi_fragment, function_name, *args, retries=4):
        key = (cs(address) if address else address, function_name, args)
        return self.calls.get(key)

    def safe_owners_and_threshold(self, w3, address, retries=4):
        return self.safes.get(cs(address))

    def read_slot_as_address(self, w3, address, slot, retries=4):
        return self.slots.get((cs(address), slot))

    def is_eoa(self, w3, address):
        return cs(address) in self.eoas

    def cross_checked(self, rpc_urls, fn, *args):
        return fn(FakeW3(), *args)


class FakeW3:
    @staticmethod
    def to_checksum_address(addr):
        return cs(addr)


def _patch(tc, fake):
    names = ["call_raw", "safe_owners_and_threshold", "cross_checked", "read_slot_as_address", "is_eoa"]
    orig = {n: getattr(scorers, n) for n in names}
    for n in names:
        setattr(scorers, n, getattr(fake, n))
    tc.addCleanup(lambda: [setattr(scorers, n, orig[n]) for n in names])


def _owners(n, start=1):
    return [cs("0x" + hex(i)[2:].zfill(40)) for i in range(start, start + n)]


# --------------------------------------------------------------------- EigenLayer Pauser disclosure


def _eigen_fake(exec_threshold=1, community=(9, 13), min_delay=864000,
                 pauser_ok=True, pauser_shape=(1, 7), unpauser=EIGEN_EXECUTOR):
    f = FakeHelpers()
    f.slots[(EIGEN_SM, scorers._EIP1967_ADMIN_SLOT)] = EIGEN_PROXY_ADMIN
    f.calls[(EIGEN_PROXY_ADMIN, "owner", ())] = EIGEN_EXECUTOR
    f.safes[EIGEN_EXECUTOR] = ([EIGEN_TIMELOCK, EIGEN_COMMUNITY], exec_threshold)
    f.calls[(EIGEN_TIMELOCK, "getMinDelay", ())] = min_delay
    f.safes[EIGEN_COMMUNITY] = (_owners(community[1], start=100), community[0])
    if pauser_ok:
        p_threshold, p_owner_count = pauser_shape
        f.calls[(EIGEN_SM, "pauserRegistry", ())] = EIGEN_PAUSER_REGISTRY
        f.calls[(EIGEN_PAUSER_REGISTRY, "isPauser", (EIGEN_PAUSER_SAFE,))] = True
        f.calls[(EIGEN_PAUSER_REGISTRY, "unpauser", ())] = unpauser
        f.safes[EIGEN_PAUSER_SAFE] = (_owners(p_owner_count, start=200), p_threshold)
    return f


class TestEigenLayerPauserDisclosure(unittest.TestCase):
    def test_pauser_disclosed_without_moving_the_existing_sub_scores(self):
        _patch(self, _eigen_fake())
        r = scorers.score_eigenlayer_strategy_manager(FakeW3())
        # Unaffected: same values as the 2026-09-20 resolved case (test_new_targets_2026_09_20.py).
        self.assertEqual(
            (r["adminKeyScore"], r["multisigScore"], r["timelockScore"], r["compositeScore"]),
            (60, 100, 20, 60),
        )
        joined = " ".join(r["notes"])
        self.assertIn(f"isPauser({EIGEN_PAUSER_SAFE}) = True", joined)
        self.assertIn("1-of-7", joined)
        self.assertIn("the SAME executor Safe already scored above", joined)
        self.assertIn("Disclosed, not scored", joined)

    def test_pauser_unresolved_does_not_crash_or_move_scores(self):
        _patch(self, _eigen_fake(pauser_ok=False))
        r = scorers.score_eigenlayer_strategy_manager(FakeW3())
        self.assertEqual(
            (r["adminKeyScore"], r["multisigScore"], r["timelockScore"], r["compositeScore"]),
            (60, 100, 20, 60),
        )
        self.assertIn("disclosed pause-authority check is skipped", " ".join(r["notes"]))

    def test_unpauser_mismatch_is_noted_not_hidden(self):
        _patch(self, _eigen_fake(unpauser=cs("0x" + "ab" * 20)))
        r = scorers.score_eigenlayer_strategy_manager(FakeW3())
        self.assertIn("did not match this run", " ".join(r["notes"]))

    def test_pauser_disclosure_also_applies_on_the_owner_set_drift_branch(self):
        # Even when the owner/upgrade path itself degrades, the (independent) pause-authority
        # path is still read and disclosed -- the two are separate authority paths.
        f = _eigen_fake()
        f.safes[EIGEN_EXECUTOR] = ([EIGEN_TIMELOCK, cs("0x" + "cd" * 20)], 1)
        _patch(self, f)
        r = scorers.score_eigenlayer_strategy_manager(FakeW3())
        self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["timelockScore"]), (20, 0, 0))
        self.assertIn(f"isPauser({EIGEN_PAUSER_SAFE}) = True", " ".join(r["notes"]))


# --------------------------------------------------------------------- Convex Finance Booster


def _convex_fake(threshold=3, n_owners=5, owner1=CONVEX_BOOSTER_OWNER, owner2=CONVEX_BOOSTER_OWNER_SECONDARY,
                  safe_addr=CONVEX_SAFE, sealed1=True, sealed2=False, force_delay=2592000):
    f = FakeHelpers()
    f.calls[(CONVEX_BOOSTER, "owner", ())] = owner1
    f.calls[(CONVEX_BOOSTER_OWNER, "isSealed", ())] = sealed1
    f.calls[(CONVEX_BOOSTER_OWNER, "FORCE_DELAY", ())] = force_delay
    f.calls[(CONVEX_BOOSTER_OWNER, "owner", ())] = owner2
    f.calls[(CONVEX_BOOSTER_OWNER_SECONDARY, "isSealed", ())] = sealed2
    f.calls[(CONVEX_BOOSTER_OWNER_SECONDARY, "owner", ())] = safe_addr
    if safe_addr:
        f.safes[cs(safe_addr)] = (_owners(n_owners, start=1), threshold)
    return f


class TestConvexFinanceBooster(unittest.TestCase):
    def test_resolved_3_of_5_safe(self):
        _patch(self, _convex_fake())
        r = scorers.score_convex_finance_booster(FakeW3())
        self.assertEqual(r["target"], CONVEX_BOOSTER)
        self.assertEqual(
            (r["adminKeyScore"], r["multisigScore"], r["timelockScore"],
             r["oracleAuthorityScore"], r["compositeScore"]),
            (65, 55, 0, 100, 43),
        )
        self.assertEqual(r["_rootGroup"], "convex-finance-booster-owner-safe-0xa3c5a1e0")

    def test_sealed_state_and_force_delay_are_disclosed(self):
        _patch(self, _convex_fake())
        r = scorers.score_convex_finance_booster(FakeW3())
        joined = " ".join(r["notes"])
        self.assertIn("isSealed() = True", joined)
        self.assertIn("FORCE_DELAY() = 2592000s", joined)
        self.assertIn("BoosterOwnerSecondary.isSealed() = False", joined)
        self.assertIn("not folded into timelockScore", joined)

    def test_hop_mismatch_degrades_rather_than_guesses(self):
        _patch(self, _convex_fake(owner1=cs("0x" + "cd" * 20)))
        r = scorers.score_convex_finance_booster(FakeW3())
        self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["timelockScore"]), (20, 0, 0))
        self.assertIn("did not fully resolve", " ".join(r["notes"]))

    def test_unresolved_safe_degrades(self):
        _patch(self, _convex_fake(safe_addr=None))
        r = scorers.score_convex_finance_booster(FakeW3())
        self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["timelockScore"]), (20, 0, 0))

    def test_threshold_two_uses_the_50_admin_key_band(self):
        _patch(self, _convex_fake(threshold=2, n_owners=4))
        r = scorers.score_convex_finance_booster(FakeW3())
        self.assertEqual(r["adminKeyScore"], 50)
        self.assertEqual(r["multisigScore"], min(100, 2 * 15 + 2 * 5))

    def test_threshold_one_uses_the_10_admin_key_band(self):
        _patch(self, _convex_fake(threshold=1, n_owners=3))
        r = scorers.score_convex_finance_booster(FakeW3())
        self.assertEqual(r["adminKeyScore"], 10)


class TestRegistryAndCrossExposure(unittest.TestCase):
    def test_convex_scorer_registered_exactly_once(self):
        names = [f.__name__ for f in scorers.SIMPLE_SCORERS]
        self.assertEqual(names.count("score_convex_finance_booster"), 1)

    def test_convex_root_group_is_distinct_and_leaves_existing_targets_untouched(self):
        existing = [
            ("Morpho Blue", "morpho-association-safe", True),
            ("EigenLayer", "eigenlayer-executor-multisig-0x369e6f59", False),
        ]
        new = [("Convex", "convex-finance-booster-owner-safe-0xa3c5a1e0", False)]

        def run(rows):
            res = [{"label": a, "notes": [], "_rootGroup": b, "_crossEcosystem": c} for a, b, c in rows]
            scorers._apply_cross_exposure(res)
            return {r["label"]: r["crossExposureScore"] for r in res}

        before = run(existing)
        after = run(existing + new)
        for label, value in before.items():
            self.assertEqual(after[label], value, f"{label} moved: {value} -> {after[label]}")
        self.assertEqual(after["Convex"], 100)


if __name__ == "__main__":
    unittest.main()
