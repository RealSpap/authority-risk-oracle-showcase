"""
Tests for the retirement of Zcash target 7 (the Zenrock zenZEC keyring), 2026-09-20:
`chains/zcash/scripts/zcash_retired_targets.py`, `attest_scores._live_results` / `verify --live`, `publish_batch.live_check`,
and the legacy snapshot file.

No network. What is pinned: that the anchored commitments (immutable, made before the retirement) still hold the retired target
and still verify offline; that a bundle holding it is re-derived WITH it and a bundle without it is not; that the legacy snapshot
says exactly what the anchors say; and that the two anchors' facts it cites are the ones in the files.
"""
import contextlib
import importlib.util
import io
import json
import os
import sys
import types
import unittest
from unittest import mock

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
SCRIPTS = os.path.join(REPO_ROOT, "chains/zcash/scripts")
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, os.path.join(REPO_ROOT, rel))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


rt = _load("aro_test_retired_targets", "chains/zcash/scripts/zcash_retired_targets.py")
at = _load("aro_test_attest_scores_retired", "chains/zcash/scripts/attest_scores.py")

ZENZEC = "keyring1k6vc6vhp6e6l3rxalue9v4ux"
FIRST_ANCHOR = "chains/zcash/data/testnet_attestation_v2_2026-09-19.json"
REANCHOR = "chains/zcash/data/testnet_attestation_v2_reanchor_2026-09-20.json"
SNAPSHOT = "chains/zcash/data/legacy_snapshot_zenzec_keyring_2026-09-20.json"


def _json(rel):
    with open(os.path.join(REPO_ROOT, rel)) as f:
        return json.load(f)


class TestTheAnchoredCommitmentsStillHoldTheRetiredTarget(unittest.TestCase):
    def test_both_aro2_anchors_contain_it_among_seven_targets(self):
        for rel in (FIRST_ANCHOR, REANCHOR):
            with self.subTest(file=rel):
                d = _json(rel)
                self.assertEqual(d["header"]["targetCount"], 7)
                self.assertIn(ZENZEC, [r["target"] for r in d["records"]])

    def test_both_anchors_still_re_derive_offline_and_are_recognised_as_holding_a_retired_target(self):
        for rel in (FIRST_ANCHOR, REANCHOR):
            with self.subTest(file=rel):
                d = _json(rel)
                self.assertEqual(at.rederive(d)["commitmentBlake2b256"], d["commitmentBlake2b256"])
                self.assertTrue(rt.bundle_includes_retired(d))

    def test_a_bundle_without_the_retired_target_is_not_treated_as_holding_one(self):
        d = _json(REANCHOR)
        six = {"records": [r for r in d["records"] if r["target"] != ZENZEC]}
        self.assertEqual(len(six["records"]), 6)
        self.assertFalse(rt.bundle_includes_retired(six))
        self.assertFalse(rt.bundle_includes_retired({}))
        self.assertFalse(rt.bundle_includes_retired({"records": []}))


class TestRetiredInBundle(unittest.TestCase):
    def test_it_is_the_set_of_retired_targets_the_bundle_actually_holds(self):
        for rel in (FIRST_ANCHOR, REANCHOR):
            with self.subTest(file=rel):
                self.assertEqual(rt.retired_in_bundle(_json(rel)), frozenset({ZENZEC}))

    def test_a_second_retired_target_the_bundle_does_not_hold_is_not_asked_for(self):
        # Rule 6 of METHODOLOGY 4.8.1 is general: another target may be retired later. A bundle made before that must
        # still be re-derived with the targets IT holds only, else it would be compared with a record it never had.
        with mock.patch.dict(rt.RETIRED_TARGETS, {"t1SomeOtherRetiredTarget": {"retired": "2026-10-01"}}):
            self.assertEqual(rt.retired_in_bundle(_json(REANCHOR)), frozenset({ZENZEC}))
            self.assertTrue(rt.bundle_includes_retired(_json(REANCHOR)))

    def test_once_a_target_is_removed_from_the_registry_the_bundles_that_contain_it_need_no_special_set(self):
        with mock.patch.dict(rt.RETIRED_TARGETS, clear=True):
            self.assertEqual(rt.retired_in_bundle(_json(REANCHOR)), frozenset())
            self.assertFalse(rt.bundle_includes_retired(_json(REANCHOR)))


class TestLiveRederivationIncludesTheRetiredTargetOnlyWhenTheBundleHoldsIt(unittest.TestCase):
    def _run_live_results(self, **kwargs):
        seen = {}

        def fake_score_all(*args, **kw):
            seen["args"], seen["kw"] = args, kw
            return ["sentinel"]
        fake = types.ModuleType("scorers")
        fake.score_all = fake_score_all
        with mock.patch.dict(sys.modules, {"scorers": fake}):
            out = at._live_results(**kwargs)
        return out, seen

    def test_live_results_defaults_to_the_live_set(self):
        out, seen = self._run_live_results()
        self.assertEqual(out, ["sentinel"])
        self.assertEqual(seen["kw"], {"include_retired": False})

    def test_live_results_can_ask_for_the_retired_targets_too(self):
        _, seen = self._run_live_results(include_retired=True)
        self.assertEqual(seen["kw"], {"include_retired": True})

    def test_publish_batch_live_check_uses_the_bundle_to_decide(self):
        pb = _load("aro_test_publish_batch_retired", "chains/zcash/scripts/publish_batch.py")
        calls = []

        def fake_live(include_retired=False):
            calls.append(include_retired)
            raise RuntimeError("stop after recording the flag")
        held = _json(REANCHOR)
        without = {"records": [r for r in held["records"] if r["target"] != ZENZEC], "header": held["header"]}
        with mock.patch.object(pb.at, "_live_results", fake_live):
            for bundle in (held, without):
                with self.assertRaises(RuntimeError):
                    pb.live_check(bundle)
        self.assertEqual(calls, [frozenset({ZENZEC}), frozenset()])


class TestVerifyLiveUsesTheRightSetForTheBundle(unittest.TestCase):
    """`attest_scores.py verify BUNDLE --live` re-derives the bundle from a live run. A live run that lacked a target the bundle
    contains would MISMATCH, so a bundle that holds a retired target must be re-derived WITH it, and a bundle without one must not
    be given it. `_live_results` is replaced by a fake that answers from the bundle's own records, so the outcome (PASS or FAIL)
    depends only on which set the main() path asked for."""

    def _verify(self, bundle):
        import tempfile
        flags = []

        def fake_live(include_retired=False):
            flags.append(include_retired)
            asked = set(include_retired) if include_retired not in (True, False) else (set(rt.RETIRED_TARGETS) if include_retired else set())
            return [r for r in bundle["records"] if r["target"] not in rt.RETIRED_TARGETS or r["target"] in asked]
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "bundle.json")
            with open(path, "w") as f:
                json.dump(bundle, f)
            with mock.patch.object(at, "_live_results", fake_live), contextlib.redirect_stdout(io.StringIO()):
                rc = at.main(["verify", path, "--live"])
        return rc, flags

    def test_a_bundle_holding_the_retired_target_passes_only_because_it_is_re_derived_with_it(self):
        for rel in (FIRST_ANCHOR, REANCHOR):
            with self.subTest(file=rel):
                rc, flags = self._verify(_json(rel))
                self.assertEqual((rc, flags), (0, [frozenset({ZENZEC})]))

    def test_a_six_target_bundle_is_re_derived_without_the_retired_target(self):
        held = _json(REANCHOR)
        six = at.build_bundle([r for r in held["records"] if r["target"] != ZENZEC], held["header"]["methodologyHashSha256"])
        self.assertEqual(six["header"]["targetCount"], 6)
        rc, flags = self._verify(six)
        self.assertEqual((rc, flags), (0, [frozenset()]))

    def test_the_wrong_set_fails_the_verification(self):
        # Sanity of the fake: if a bundle holding the retired target were re-derived WITHOUT it, verify --live must FAIL.
        held = _json(REANCHOR)
        with mock.patch.object(at, "_live_results", lambda include_retired=False: [r for r in held["records"] if r["target"] != ZENZEC]):
            import tempfile
            with tempfile.TemporaryDirectory() as d:
                path = os.path.join(d, "bundle.json")
                with open(path, "w") as f:
                    json.dump(held, f)
                with contextlib.redirect_stdout(io.StringIO()):
                    rc = at.main(["verify", path, "--live"])
        self.assertEqual(rc, 1)


class TestEveryPublishedBundleNamesTheCommitOfItsMethodologyPin(unittest.TestCase):
    """header.methodologyHashSha256 is the SHA-256 of METHODOLOGY.md at the commit `methodologyPinnedAt.gitCommit`. The publisher tool
    writes that commit by a hard-coded default, so a wrong one went unnoticed on the six-live-target anchor until it was hashed; this
    checks every published ARO2 record (every `testnet_attestation_v2_*.json` in data/, found by glob so that the next anchor is
    covered without editing this test). Skipped for a commit that this clone does not have (shallow clone)."""

    def test_the_pin_is_the_hash_of_the_methodology_at_the_named_commit(self):
        import glob
        import hashlib
        import subprocess
        files = sorted(os.path.relpath(p, REPO_ROOT) for p in glob.glob(os.path.join(REPO_ROOT, "chains/zcash/data/testnet_attestation_v2_*.json")))
        self.assertGreaterEqual(len(files), 3, files)   # the first anchor, the re-anchor, the six-live anchor: never an empty loop
        for rel in files:
            with self.subTest(file=rel):
                d = _json(rel)
                commit = d["methodologyPinnedAt"]["gitCommit"]
                r = subprocess.run(["git", "show", f"{commit}:chains/zcash/METHODOLOGY.md"], cwd=REPO_ROOT, capture_output=True)
                if r.returncode != 0:
                    self.skipTest(f"commit {commit[:7]} not available in this clone")
                self.assertEqual(hashlib.sha256(r.stdout).hexdigest(), d["header"]["methodologyHashSha256"])


class TestLegacySnapshot(unittest.TestCase):
    def test_the_file_is_exactly_what_the_two_anchored_files_say(self):
        built = rt.build_legacy_snapshot(ZENZEC, [(FIRST_ANCHOR, _json(FIRST_ANCHOR)), (REANCHOR, _json(REANCHOR))])
        self.assertEqual(_json(SNAPSHOT), built)

    def test_it_records_the_anchored_scores_and_names_both_transactions(self):
        s = _json(SNAPSHOT)
        self.assertEqual(s["target"], ZENZEC)
        self.assertEqual(s["retiredOn"], "2026-09-20")
        self.assertEqual((s["record"]["adminKeyScore"], s["record"]["multisigScore"], s["record"]["timelockScore"],
                          s["record"]["compositeScore"]), (65, 60, 0, 44))
        self.assertEqual([c["txid"] for c in s["committedIn"]],
                         ["18791a4cdaa00b5d0aefc1dcce5576c6e43ea9e203db03b0d973772dfe32cc37",
                          "eeaa894c3c46814f7228a7ecf2be84c0006c1154b5101688dd413d9a419689c0"])
        # both anchors carry the same commitment (the second republishes the first)
        self.assertEqual(len({c["commitmentBlake2b256"] for c in s["committedIn"]}), 1)

    def test_the_registry_points_at_the_files_that_exist(self):
        entry = rt.RETIRED_TARGETS[ZENZEC]
        for rel in (entry["status_note"], entry["legacy_snapshot"]):
            with self.subTest(file=rel):
                self.assertTrue(os.path.exists(os.path.join(REPO_ROOT, rel)), rel)

    def test_a_snapshot_is_refused_when_the_anchored_records_disagree(self):
        a, b = _json(FIRST_ANCHOR), _json(REANCHOR)
        for r in b["records"]:
            if r["target"] == ZENZEC:
                r["compositeScore"] = 45
        with self.assertRaises(ValueError):
            rt.build_legacy_snapshot(ZENZEC, [(FIRST_ANCHOR, a), (REANCHOR, b)])


if __name__ == "__main__":
    unittest.main()
