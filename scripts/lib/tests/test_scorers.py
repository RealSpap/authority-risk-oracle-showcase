"""
Unit tests for scripts/lib/scorers.py's pure logic -- no live RPC.
Covers the functions every one of the ~50 individual scorers depends on
(_composite's rounding, _safe_score's per-target isolation, _apply_l1_cap's
l1CappedComposite derivation) rather than the ~50 scorers themselves, which
need a live chain to mean anything and are exercised by the project's
existing --dry-run scripts instead.
"""
import os
import sys
import unittest

from web3 import Web3

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from lib import scorers  # noqa: E402
from lib.scorers import _apply_l1_cap, _composite  # noqa: E402
from lib.web3_utils import RpcUnavailable  # noqa: E402


class TestComposite(unittest.TestCase):
    def test_all_zero(self):
        self.assertEqual(_composite(0, 0, 0), 0)

    def test_all_hundred(self):
        self.assertEqual(_composite(100, 100, 100), 100)

    def test_weighting_matches_documented_formula(self):
        # 0.4*admin + 0.3*multisig + 0.3*timelock, floor(... + 0.5)
        # admin=80, multisig=100, timelock=75 -> 32 + 30 + 22.5 = 84.5 -> 85
        self.assertEqual(_composite(80, 100, 75), 85)

    def test_round_half_up_not_bankers_rounding(self):
        # The exact regression _composite()'s own docstring documents: Python's
        # builtin round() uses round-half-to-even and silently produced 42 for
        # a raw value of exactly 42.5, where the already-published score
        # (computed by hand, same convention) was 43. admin=50, multisig=40,
        # timelock=35 -> 20 + 12 + 10.5 = 42.5 exactly.
        raw = 0.4 * 50 + 0.3 * 40 + 0.3 * 35
        self.assertEqual(raw, 42.5)
        self.assertEqual(round(raw), 42)  # banker's rounding: the wrong answer
        self.assertEqual(_composite(50, 40, 35), 43)  # round-half-up: the right one

    def test_oracle_authority_param_accepted_but_not_weighted(self):
        # oracleAuthorityScore is published separately, never folded into
        # compositeScore -- passing a low value must not change the result.
        self.assertEqual(_composite(80, 100, 75, oracle_authority=0), _composite(80, 100, 75, oracle_authority=100))



class TestApplyL1Cap(unittest.TestCase):
    def test_caps_a_high_score_down(self):
        entry = {"compositeScore": 100, "notes": []}
        _apply_l1_cap(entry, l1_authority_composite=60)
        self.assertEqual(entry["l1CappedComposite"], 60)

    def test_does_not_raise_a_low_score(self):
        # min() never increases a score -- a target already below the L1
        # ceiling keeps its own (lower) number, it isn't pulled UP to 60.
        entry = {"compositeScore": 30, "notes": []}
        _apply_l1_cap(entry, l1_authority_composite=60)
        self.assertEqual(entry["l1CappedComposite"], 30)

    def test_equal_scores_are_unaffected(self):
        entry = {"compositeScore": 60, "notes": []}
        _apply_l1_cap(entry, l1_authority_composite=60)
        self.assertEqual(entry["l1CappedComposite"], 60)

    def test_never_overwrites_compositeScore_itself(self):
        entry = {"compositeScore": 100, "notes": []}
        _apply_l1_cap(entry, l1_authority_composite=60)
        self.assertEqual(entry["compositeScore"], 100)  # untouched

    def test_none_authority_composite_sets_none_and_notes_why(self):
        # score_rollup_l1_authority() itself failed/was skipped this run --
        # must not silently compute a wrong cap from missing data.
        entry = {"compositeScore": 100, "notes": []}
        _apply_l1_cap(entry, l1_authority_composite=None)
        self.assertIsNone(entry["l1CappedComposite"])
        self.assertTrue(any("l1CappedComposite not computed" in n for n in entry["notes"]))


class TestScoreAllSkipSlow(unittest.TestCase):
    """ADDED 2026-09-18: closes a tracked operational risk (a full score_all()
    run clocked exceeding 50 minutes -- "risque de timeout des routines",
    caused entirely by 4 scorers that each replay full chain history via
    eth_getLogs). score_all(w3, skip_slow=True) omits exactly those 4;
    default skip_slow=False must reproduce today's exact call set.

    Fully isolated from the ~26 real scorer functions: SIMPLE_SCORERS,
    _SLOW_SCORERS, the 4 parametrized target lists, and the 3 scorers
    called directly by name (score_rollup_l1_authority, score_ramses_clv2,
    score_layerzero_infra) are all monkeypatched to small tracking stand-ins
    that just record their own name -- this tests score_all()'s own
    orchestration/filtering logic, not any individual scorer's real
    behavior (already covered elsewhere)."""

    def _tracker(self, name):
        def fn(w3):
            self.calls.append(name)
            return {
                "target": "0x" + str(len(self.calls)).zfill(40), "label": name,
                "adminKeyScore": 50, "multisigScore": 50, "timelockScore": 50,
                "oracleAuthorityScore": 100, "compositeScore": 50, "notes": [],
            }
        fn.__name__ = name
        return fn

    def _patch_all(self):
        self.calls = []
        fast = self._tracker("fast")
        slow = self._tracker("slow")
        rollup = self._tracker("rollup")
        ramses = self._tracker("ramses")
        layerzero = self._tracker("layerzero")
        patched = {
            "SIMPLE_SCORERS": [fast, slow],
            "_SLOW_SCORERS": frozenset({slow}),
            "ARCUS_TARGETS": [], "STOCK_TOKEN_TARGETS": [], "MORE_MORPHO_VAULTS": [], "LONGBOW_TARGETS": [],
            "score_rollup_l1_authority": rollup, "score_ramses_clv2": ramses, "score_layerzero_infra": layerzero,
        }
        originals = {n: getattr(scorers, n) for n in patched}
        for n, v in patched.items():
            setattr(scorers, n, v)
        self.addCleanup(lambda: [setattr(scorers, n, v) for n, v in originals.items()])

    def test_default_skip_slow_false_calls_every_scorer_matching_todays_behavior(self):
        self._patch_all()
        scorers.score_all(w3=None)
        self.assertEqual(set(self.calls), {"fast", "slow", "rollup", "ramses", "layerzero"})

    def test_skip_slow_true_omits_exactly_the_four_slow_scorers(self):
        self._patch_all()
        scorers.score_all(w3=None, skip_slow=True)
        self.assertEqual(set(self.calls), {"fast", "layerzero"})

    def test_skip_slow_true_still_produces_valid_l1_capped_composite_none(self):
        # rollup_entries is empty under skip_slow -> l1_authority_composite
        # is None -> every surviving entry's l1CappedComposite is None too,
        # reusing the SAME degradation path _apply_l1_cap already has for
        # "score_rollup_l1_authority failed this run" (not a new branch).
        self._patch_all()
        results = scorers.score_all(w3=None, skip_slow=True)
        self.assertTrue(results)
        for entry in results:
            self.assertIsNone(entry["l1CappedComposite"])

    def test_cross_ecosystem_note_reaches_the_entry_next_to_its_score(self):
        # ADDED 2026-09-20: compute_cross_exposure_with_notes() explains a flat-80
        # cross-ecosystem cap; score_all() must carry that note onto the entry.
        self._patch_all()
        target = scorers.Web3.to_checksum_address("0x" + "1".zfill(40))
        other = scorers.Web3.to_checksum_address("0x" + "2".zfill(40))
        original = scorers.compute_cross_exposure_with_notes
        scorers.compute_cross_exposure_with_notes = lambda w3: ({target: 80, other: 100}, {target: ["cap note"]})
        self.addCleanup(lambda: setattr(scorers, "compute_cross_exposure_with_notes", original))
        results = scorers.score_all(w3=None, skip_slow=True)
        by_target = {scorers.Web3.to_checksum_address(r["target"]): r for r in results}
        self.assertEqual(by_target[target]["crossExposureScore"], 80)
        self.assertIn("cap note", by_target[target]["notes"])

    def test_compute_cross_exposure_failing_defaults_every_entry_to_100_with_a_not_confirmed_note(self):
        # ADDED 2026-09-22: this is the fallback the signer_overlap.py fix from the same day relies
        # on -- compute_cross_exposure_with_notes() now lets RpcUnavailable (a persistent RPC
        # failure resolving a Safe, see web3_utils.RpcUnavailable) propagate rather than trying to
        # contain it to just the directly-affected group (an earlier version of that fix tried
        # exactly that and was found unsound: the shared signer registry means a failure anywhere
        # can silently affect ANY other group's score, not just the one that owns the failing Safe).
        # This existing try/except (present well before this date, FIXED 2026-09-17 per its own
        # comment) is what actually closes the gap -- and had NO test coverage before this one,
        # despite now being load-bearing for that fix. Uses RpcUnavailable specifically (not a bare
        # Exception) to prove this real exception type is caught here like any other, since it's a
        # RuntimeError subclass and nothing about `except Exception` is RpcUnavailable-specific.
        self._patch_all()
        original = scorers.compute_cross_exposure_with_notes

        def boom(w3):
            raise RpcUnavailable("getOwners() on 0xSafe: ConnectionError: boom")
        scorers.compute_cross_exposure_with_notes = boom
        self.addCleanup(lambda: setattr(scorers, "compute_cross_exposure_with_notes", original))
        results = scorers.score_all(w3=None, skip_slow=True)
        self.assertTrue(results)
        for entry in results:
            self.assertEqual(entry["crossExposureScore"], 100)
            self.assertTrue(
                any("NOT a confirmed no-overlap result" in n for n in entry["notes"]),
                entry["notes"],
            )

    def test_slow_scorers_set_contains_exactly_the_two_expected_real_functions(self):
        # Locks in which real functions _SLOW_SCORERS names, independent of
        # the monkeypatching above (reads the real, unpatched module attrs).
        self.assertEqual(
            scorers._SLOW_SCORERS,
            frozenset({scorers.score_fables_pool_registry, scorers.score_beefy_spy_weth_vault}),
        )


class TestScorePendleV2GovernanceProxyNote(unittest.TestCase):
    """ADDED 2026-09-20: MarketFactoryV6.owner() (the Pendle governance proxy) used to be a disclosed open
    sub-thread; it now resolves, by hasRole(DEFAULT_ADMIN_ROLE), to the SAME Safe that owns ProxyAdmin. The score
    does not move (that Safe already sets the ceiling); only the note and its honesty when the read fails."""

    PA_OWNER = Web3.to_checksum_address("0x" + "aa" * 20)
    DPA_OWNER = Web3.to_checksum_address("0x" + "bb" * 20)
    MF_OWNER = Web3.to_checksum_address("0x" + "cc" * 20)

    def _run(self, admin_read):
        names = ["read_address_getter", "safe_owners_and_threshold", "is_eoa", "call_raw"]
        originals = {n: getattr(scorers, n) for n in names}
        owners = {"0xA28c08f165116587D4F3E708743B4dEe155c5E64": self.PA_OWNER,
                  "0xD37eB2E6DE40a33ba68BaD94427723b66c954EA9": self.DPA_OWNER,
                  "0x544BF81c855AE84c1e8b65d5E38770898D01EeE2": self.MF_OWNER}
        scorers.read_address_getter = lambda w3, a, fn, retries=4: owners.get(a)
        scorers.safe_owners_and_threshold = lambda w3, a, retries=4: ([Web3.to_checksum_address("0x" + "%040x" % i) for i in range(1, 6 if a == self.PA_OWNER else 7)], 3) if a in (self.PA_OWNER, self.DPA_OWNER) else None
        scorers.is_eoa = lambda w3, a: False
        seen = []

        def fake_call_raw(w3, address, abi, fn, *args, retries=4):
            seen.append((address, fn, args))
            return admin_read
        scorers.call_raw = fake_call_raw
        try:
            return scorers.score_pendle_v2(None), seen
        finally:
            for n, v in originals.items():
                setattr(scorers, n, v)

    def test_default_admin_held_by_the_proxyadmin_safe_is_noted_and_the_score_is_unchanged(self):
        r, seen = self._run(True)
        self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["timelockScore"], r["compositeScore"]), (70, 45, 0, 42))
        text = " ".join(r["notes"])
        self.assertIn("SAME Safe", text)
        self.assertNotIn("not resolved this pass", text)
        self.assertEqual(seen[0], (self.MF_OWNER, "hasRole", (b"\x00" * 32, self.PA_OWNER)))

    def test_a_failed_or_negative_read_keeps_the_open_wording(self):
        for value in (False, None):
            with self.subTest(value=value):
                r, _ = self._run(value)
                text = " ".join(r["notes"])
                self.assertIn("not confirmed to be that Safe", text)
                self.assertEqual(r["compositeScore"], 42)


if __name__ == "__main__":
    unittest.main()
