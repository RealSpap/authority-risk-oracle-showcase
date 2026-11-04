"""Tests for the trust status: scripts/lib/trust_rules.py, scripts/trust.py, and the fixture it runs on.

No network. The kit's signing cases generate throw-away keys in a temporary folder (they are skipped when PyNaCl is not installed).
"""
import ast
import calendar
import copy
import json
import os
import shutil
import sys
import tempfile
import time
import unittest
HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.abspath(os.path.join(HERE, "..", ".."))
ROOT = os.path.abspath(os.path.join(SCRIPTS, ".."))
for p in (SCRIPTS, os.path.join(SCRIPTS, "lib"), HERE):
    if p not in sys.path:
        sys.path.insert(0, p)
import trust  # noqa: E402
from lib import trust_rules as tr  # noqa: E402
import trust_support as kit  # noqa: E402  -- the fixture and the helpers (Watch, so_edit, status, KEY ...) are shared with the adversarial kit
try:
    import nacl.signing  # noqa: F401
    HAVE_NACL = True
except ImportError:
    HAVE_NACL = False
def reasons_of(doc, addr):
    return [r["code"] for r in doc["by_target"]["robinhood:" + addr]["reasons"]]


class TestVocabulary(unittest.TestCase):
    def test_every_reason_is_declared_with_a_known_dimension_state_and_effect(self):
        for code, (dim, state, effect) in tr.REASONS.items():
            self.assertIn(dim, tr.DIMENSIONS, code)
            self.assertIn(state, tr.DIM_STATES, code)
            self.assertIn(effect, ("decides", "degrades", "info"), code)

    def test_the_rule_text_names_every_status(self):
        for s in tr.STATUSES:
            self.assertIn(s, tr.__doc__)
        self.assertIn("not that the contract is safe", tr.__doc__)


class TestPrecedence(unittest.TestCase):
    """The first matching line of the rule, from the top: UNAVAILABLE, DISPUTED, STALE, UNVERIFIED, PARTIAL, VERIFIED."""

    def status(self, *codes):
        return tr._record({c: "x" for c in codes})["status"]

    def test_each_line(self):
        self.assertEqual(self.status(), "VERIFIED")
        self.assertEqual(self.status("modules_truncated"), "PARTIAL")
        self.assertEqual(self.status("independent_read_unreadable"), "UNVERIFIED")
        self.assertEqual(self.status("score_stale"), "STALE")
        self.assertEqual(self.status("dispute_open"), "DISPUTED")
        self.assertEqual(self.status("oracle_not_read"), "UNAVAILABLE")

    def test_the_worse_wins_over_the_milder(self):
        self.assertEqual(self.status("modules_truncated", "independent_read_unreadable"), "UNVERIFIED")
        self.assertEqual(self.status("independent_read_unreadable", "score_stale"), "STALE")
        self.assertEqual(self.status("score_stale", "reader_disagrees"), "DISPUTED")
        self.assertEqual(self.status("reader_disagrees", "oracle_not_read", "modules_truncated"), "UNAVAILABLE")

    def test_info_reasons_never_move_the_status_but_are_listed(self):
        r = tr._record({"pause_no_getter": "x", "money_unknown": "x", "money_stale": "x", "oracle_method_mixed": "x", "method_version_unregistered": "x", "side_roles_not_covered": "x"})
        self.assertEqual(r["status"], "VERIFIED")
        self.assertEqual(len(r["reasons"]), 6)
        self.assertEqual(r["dimensions"]["financial_exposure"], "stale")        # shown on its dimension
        self.assertEqual(r["dimensions"]["coverage"], "ok")

    def test_an_unverified_dimension_other_than_the_reading_is_partial(self):
        self.assertEqual(self.status("input_missing:pause_state"), "PARTIAL")
        self.assertEqual(self.status("signature_unread"), "PARTIAL")
        self.assertEqual(self.status("input_missing:second_opinion"), "UNVERIFIED")

    def test_dimension_state_is_the_worst_of_its_reasons(self):
        r = tr._record({"reader_disagreement_acknowledged": "x", "modules_truncated": "x"})
        self.assertEqual(r["dimensions"]["reading"], "partial")
        r = tr._record({"reader_disagreement_acknowledged": "x", "score_stale": "x"})
        self.assertEqual(r["dimensions"]["reading"], "stale")


class TestOnTheFixture(unittest.TestCase):
    def setUp(self):
        self.w = kit.Watch()

    def tearDown(self):
        self.w.close()

    def test_baseline_is_verified_and_the_document_validates(self):
        d = self.w.trust()
        self.assertEqual(d["counts"]["VERIFIED"], 3)
        self.assertEqual(d["targets"], 3)
        self.assertEqual(d["run"], {"signature": "expected_signed", "signature_key": "pinned", "journal": "ok", "watch_run_utc": "2026-10-30T06:20:00Z", "inputs_unread": []})
        self.assertIsNone(d["error"])
        import hashlib
        self.assertEqual(d["rule_sha256"], hashlib.sha256(open(tr.__file__.replace(".pyc", ".py"), "rb").read()).hexdigest())
        errs = []
        import validate_schemas
        validate_schemas.check(d, json.load(open(os.path.join(ROOT, "watch", "schema", "trust.schema.json"))), "trust", errs)
        self.assertEqual(errs, [])

    def test_a_missing_input_is_never_ok(self):
        for name, expected_status in (("second_opinion", "UNVERIFIED"), ("pause_state", "PARTIAL"), ("safe_activity", "PARTIAL"), ("side_roles", "PARTIAL"), ("alerts", "PARTIAL"),
                                      ("methodology", "PARTIAL"), ("disputes", "PARTIAL"), ("signature", "PARTIAL"), ("chain", "PARTIAL")):
            w = kit.Watch()
            try:
                os.remove(os.path.join(w.dir, name + ".json"))
                d = w.trust()
                self.assertEqual(d["by_target"]["robinhood:" + kit.A]["status"], expected_status, name)
            finally:
                w.close()

    def test_a_missing_tvl_is_listed_but_does_not_degrade(self):
        os.remove(os.path.join(self.w.dir, "tvl.json"))
        d = self.w.trust()
        self.assertEqual(kit.status(d, kit.A), "VERIFIED")
        self.assertIn("input_missing:tvl", reasons_of(d, kit.A))
        self.assertEqual(d["run"]["inputs_unread"], ["tvl"])

    def test_the_score_does_not_change_the_status(self):
        base = self.w.trust()
        def lower(d):
            for t in d["targets"]: t.update({"compositeScore": 1, "adminKeyScore": 1})
        self.w.edit("scores/robinhood-chain.json", lower)
        low = self.w.trust()
        self.assertEqual({k: v["status"] for k, v in base["by_target"].items()}, {k: v["status"] for k, v in low["by_target"].items()})

    def test_signature_and_journal_are_run_wide(self):
        self.w.edit("chain.json", lambda d: d.update({"ok": False}))
        d = self.w.trust()
        self.assertTrue(all(v["status"] == "PARTIAL" and "journal_broken" in [r["code"] for r in v["reasons"]] for v in d["by_target"].values()))
        w2 = kit.Watch()
        try:
            w2.edit("signature.json", lambda d: d.update({"signed": False}))
            d = w2.trust()
            self.assertTrue(all("run_unsigned" in [r["code"] for r in v["reasons"]] for v in d["by_target"].values()))
            d = w2.trust(key_present=False)
            self.assertEqual(d["run"]["signature"], "unsigned")
        finally:
            w2.close()
        w2 = kit.Watch()
        try:
            d = w2.trust(key_present=False)                              # the previous manifest says signed, but this run has no key
            self.assertTrue(all("run_unsigned" in [r["code"] for r in v["reasons"]] for v in d["by_target"].values()))
            self.assertTrue(all(v["status"] == "PARTIAL" for v in d["by_target"].values()))
        finally:
            w2.close()
        w3 = kit.Watch()
        try:
            self.assertEqual(w3.trust(key_present=False)["run"]["signature"], "unsigned")      # signed before, but no key in this run: not claimed
        finally:
            w3.close()

    def test_each_decisive_reason_on_the_fixture(self):
        cases = [("dispute", lambda w: w.edit("disputes.json", lambda d: d["by_target"].update({kit.KEY[kit.A]: [{"id": 1, "status": "open"}]})), "DISPUTED", "dispute_open"),
                 ("resolved dispute is nothing", lambda w: w.edit("disputes.json", lambda d: d["by_target"].update({kit.KEY[kit.A]: [{"id": 1, "status": "resolved"}]})), "VERIFIED", None),
                 ("reader disagrees", lambda w: w.edit("second_opinion.json", kit.so_edit(kit.C, disagree="the score says x")), "DISPUTED", "reader_disagrees"),
                 ("reader disagreement reviewed", lambda w: w.edit("second_opinion.json", kit.so_edit(kit.C, disagree="x", acknowledged=True)), "PARTIAL", "reader_disagreement_acknowledged"),
                 ("score stale", lambda w: w.edit("scores/robinhood-chain.json", lambda d: d["targets"][0].update({"stale": True})), "STALE", "score_stale"),
                 ("native", lambda w: w.edit("second_opinion.json", kit.so_edit(kit.C, kind="native")), "UNVERIFIED", "native_entity"),
                 ("no record", lambda w: w.edit("second_opinion.json", lambda d: d.update({"results": [r for r in d["results"] if r["target"] != kit.C]})), "UNVERIFIED", "independent_read_missing"),
                 ("pause state unread for 5 days", lambda w: w.edit("pause_state.json", lambda d: d["by_target"].update({kit.KEY[kit.C]: {"paused": False, "stale": True, "stale_since": "2026-10-24T00:00:00Z"}})), "STALE", "state_unverified_pause"),
                 ("pause state unread for 1 day", lambda w: w.edit("pause_state.json", lambda d: d["by_target"].update({kit.KEY[kit.C]: {"paused": False, "stale": True, "stale_since": "2026-10-29T12:00:00Z"}})), "PARTIAL", "state_stale_pause"),
                 ("pause state stale with no date: the age is not known, not zero", lambda w: w.edit("pause_state.json", lambda d: d["by_target"].update({kit.KEY[kit.C]: {"paused": False, "stale": True}})), "STALE", "state_unverified_pause"),
                 ("safe activity unread for 1 day", lambda w: w.edit("safe_activity.json", lambda d: d["by_safe"]["h1"].update({"stale": True, "stale_since": "2026-10-29T12:00:00Z"})), "PARTIAL", "state_stale_safe_activity"),
                 ("safe activity stale with no date", lambda w: w.edit("safe_activity.json", lambda d: d["by_safe"]["h1"].update({"stale": True})), "STALE", "state_unverified_safe_activity"),
                 ("pause reads of the chain got no answer", lambda w: w.edit("pause_state.json", lambda d: (d.update({"unread_chains": ["robinhood"]}), d["by_target"].pop(kit.KEY[kit.C], None), None)[-1]), "PARTIAL", "pause_unread"),
                 ("Safe whose module list was not said to be complete", lambda w: w.edit("second_opinion.json", kit.so_edit(kit.A, modules_truncated=None)), "PARTIAL", "modules_unread"),
                 ("Safe whose modules were not read", lambda w: w.edit("second_opinion.json", kit.so_edit(kit.A, modules=None)), "PARTIAL", "modules_unread"),
                 ("admin role members path without a count", lambda w: w.edit("second_opinion.json", kit.so_edit(kit.B, path="DEFAULT_ADMIN_ROLE member 0")), "PARTIAL", "admin_members_unread"),
                 ("an input file kept from an earlier run: the independent reader", lambda w: w.edit("second_opinion.json", lambda d: d.update({"generated_utc": "2026-10-29T06:00:00Z"})), "STALE", "input_stale:second_opinion"),
                 ("an input file kept from an earlier run: the pause state", lambda w: w.edit("pause_state.json", lambda d: d.update({"generated_utc": "2026-10-29T06:00:00Z"})), "PARTIAL", "input_stale:pause_state"),
                 ("an input file with no date", lambda w: w.edit("alerts.json", lambda d: (d.pop("evaluated_utc", None), None)[-1]), "PARTIAL", "input_stale:alerts"),
                 ("the previous manifest is signed by another key", lambda w: w.edit("signature.json", lambda d: d.update({"public_key": "ab" * 32})), "PARTIAL", "signature_key_not_pinned"),
                 ("safe activity unread for 5 days", lambda w: w.edit("safe_activity.json", lambda d: d["by_safe"]["h1"].update({"stale": True, "stale_since": "2026-10-24T00:00:00Z"})), "STALE", "state_unverified_safe_activity"),
                 ("scan gap", lambda w: w.edit("scores/robinhood-chain.json", lambda d: d["self"].update({"gap_blocks": 5000})), "PARTIAL", "scan_gap"),
                 ("scan stalled two runs", lambda w: w.edit("scores/robinhood-chain.json", lambda d: d.update({"scan_stalled_runs": 2})), "PARTIAL", "scan_gap"),
                 ("scan stalled one run is nothing", lambda w: w.edit("scores/robinhood-chain.json", lambda d: d.update({"scan_stalled_runs": 1})), "VERIFIED", None),
                 ("admin members all read", lambda w: w.edit("second_opinion.json", kit.so_edit(kit.B, admin_members={"members": ["0x1"], "total": 1, "read": 1, "unread": 0, "note": None})), "VERIFIED", None),
                 ("admin members unread", lambda w: w.edit("second_opinion.json", kit.so_edit(kit.B, admin_members={"members": ["0x1"], "total": 4, "read": 1, "unread": 3, "note": "3 of 4"})), "PARTIAL", "admin_members_unread"),
                 ("other hash", lambda w: w.edit("scores/robinhood-chain.json", lambda d: d["targets"][2].update({"methodologyHash": "0x" + "88" * 32})), "PARTIAL", "method_hash_differs"),
                 ("fixed by decision", lambda w: w.edit("scores/robinhood-chain.json", lambda d: d["targets"][1].update({"evaluation": "fixed_by_decision"})), "PARTIAL", "score_fixed_by_decision"),
                 ("undelivered alert (alerts.json carries the DISPLAY name of the chain)", lambda w: w.edit("alerts.json", lambda d: d["active"].append({"chain": "Robinhood Chain", "target": kit.B, "rule": "r", "severity": "high", "notified": False})), "PARTIAL", "alert_undelivered"),
                 ("delivered alert is nothing", lambda w: w.edit("alerts.json", lambda d: d["active"].append({"chain": "Robinhood Chain", "target": kit.B, "rule": "r", "severity": "high", "notified": True})), "VERIFIED", None),
                 ("an alert under the severity that is sent stays notified: false by design", lambda w: w.edit("alerts.json", lambda d: d["active"].append({"chain": "Robinhood Chain", "target": kit.B, "rule": "r", "severity": "info", "notified": False})), "VERIFIED", None),
                 ("contract admin the reader did not resolve", lambda w: w.edit("second_opinion.json", kit.so_edit(kit.B, kind="contract", behind=None)), "PARTIAL", "reader_cannot_contradict"),
                 ("contract admin resolved one hop", lambda w: w.edit("second_opinion.json", kit.so_edit(kit.B, kind="contract", behind={"address": "0x1", "kind": "timelock"})), "VERIFIED", None),
                 ("program-derived address admin", lambda w: w.edit("second_opinion.json", kit.so_edit(kit.B, kind="pda")), "PARTIAL", "reader_cannot_contradict"),
                 ("Safe whose signers were not all classified", lambda w: w.edit("second_opinion.json", kit.so_edit(kit.A, owners_kinds={"eoa": 2, "unread": 1})), "PARTIAL", "safe_signers_unclassified"),
                 ("admin members: the count itself was not read", lambda w: w.edit("second_opinion.json", kit.so_edit(kit.B, admin_members={"members": ["0x1"], "total": None, "read": 1, "unread": None, "note": "the number of members was not read"})), "PARTIAL", "admin_members_unread"),
                 ("the independent reader's file is 5 h 45 older than the run (one failed step, below the old 8 hour limit)", lambda w: w.edit("second_opinion.json", lambda d: d.update({"generated_utc": "2026-10-30T00:35:00Z"})), "STALE", "input_stale:second_opinion"),
                 ("held assets file missing", lambda w: w.rm("held_assets.json"), "VERIFIED", "input_missing:held_assets"),
                 ("other holders of the admin role that the score does not weigh", lambda w: w.edit("second_opinion.json", kit.so_edit(kit.B, admin_members_gap={"not_weighed": 2, "text": "2 other holder(s) of DEFAULT_ADMIN_ROLE read"})), "PARTIAL", "admin_members_not_weighed"),
                 ("no other holder", lambda w: w.edit("second_opinion.json", kit.so_edit(kit.B, admin_members_gap={"not_weighed": 0, "text": None})), "VERIFIED", None),
                 ("admin events window not read completely", lambda w: w.edit("second_opinion.json", lambda d: d.update({"event_windows": {"robinhood": {"complete": False}}})), "PARTIAL", "admin_events_unread"),
                 ("admin events window read completely", lambda w: w.edit("second_opinion.json", lambda d: d.update({"event_windows": {"robinhood": {"complete": True}}})), "VERIFIED", None),
                 ("first run: no window, nothing unread", lambda w: w.edit("second_opinion.json", lambda d: d.update({"event_windows": {"robinhood": {"complete": None}}})), "VERIFIED", None),
                 ("open executor is information, not a downgrade", lambda w: w.edit("second_opinion.json", kit.so_edit(kit.B, open_executor=True)), "VERIFIED", "executor_open"),
                 ("side role kept stale", lambda w: w.edit("side_roles.json", lambda d: d["by_target"].update({kit.KEY[kit.B]: {"roles": {"pauser()": {"kind": "eoa", "stale": True}}}})), "PARTIAL", "side_roles_stale"),
                 ("oracle self watch unread", lambda w: w.edit("latest.json", lambda d: d["oracles"][0].update({"self_watch": {"read": False}})), "PARTIAL", "oracle_self_watch_unread"),
                 ("oracle not read", lambda w: w.edit("latest.json", lambda d: d["oracles"][0].update({"read_ok": False})), "UNAVAILABLE", "oracle_not_read")]
        run_wide = ("oracle_", "scan_gap", "input_stale", "input_missing", "signature_key", "watch_old", "pause_unread", "admin_events_unread")      # reasons that hold for every target of the run or of the oracle
        for label, edit, want, code in cases:
            w = kit.Watch()
            try:
                edit(w)
                d = w.trust()
                got = {a: kit.status(d, a) for a in (kit.A, kit.B, kit.C)}
                hit = [a for a, s in got.items() if s == want]
                self.assertTrue(hit if want != "VERIFIED" else all(s == "VERIFIED" for s in got.values()), "%s: %s" % (label, got))
                if code:
                    carriers = [a for a in (kit.A, kit.B, kit.C) if code in reasons_of(d, a)]
                    self.assertTrue(carriers, label)
                    if code.startswith(run_wide):
                        self.assertEqual(sorted(carriers), sorted(hit), label)
                    else:
                        self.assertEqual(len(carriers), 1, "%s: a reason about one target landed on %s" % (label, carriers))
                        if want != "VERIFIED":
                            self.assertEqual(carriers, hit, "%s: the status landed on another target than the reason" % label)
            finally:
                w.close()

    def test_a_held_amount_of_zero_is_a_known_zero_not_an_unknown(self):
        def drop(d):
            for a in (kit.A, kit.C): d["matched"].pop(kit.KEY[a], None)
        self.w.edit("tvl.json", drop)
        self.w.edit("held_assets.json", lambda d: d["by_target"].update({kit.KEY[kit.A]: {"held_usd": 0.0, "price_at": kit.NOW}}))
        d = self.w.trust()
        self.assertNotIn("money_unknown", reasons_of(d, kit.A))      # held 0.0: known
        self.assertIn("money_unknown", reasons_of(d, kit.C))         # no source at all: unknown

    def test_info_reasons_are_listed_where_they_hold(self):
        H2 = "0x" + "99" * 32
        self.w.edit("methodology.json", lambda d: d.update({"mixed": [{"oracle": "robinhood-chain", "hashes": {kit.A: 2, H2: 1}}], "hashes": {"0x" + "77" * 32: {"method_version": None}}}))
        d = self.w.trust()
        for addr in (kit.A, kit.B, kit.C):
            self.assertIn("oracle_method_mixed", reasons_of(d, addr))
            self.assertIn("method_version_unregistered", reasons_of(d, addr))
            self.assertIn("pause_no_getter", reasons_of(d, addr)) if addr != kit.C else self.assertNotIn("pause_no_getter", reasons_of(d, addr))
            self.assertEqual(kit.status(d, addr), "VERIFIED")

    def test_the_scorer_pins_file_marks_its_targets_fixed_by_decision(self):
        json.dump({"pins": [{"id": "x", "targets": [kit.B.upper().replace("0X", "0x")]}]}, open(os.path.join(self.w.data, "scorer_pins.json"), "w"))
        d = self.w.trust()
        self.assertEqual(kit.status(d, kit.B), "PARTIAL")
        self.assertIn("score_fixed_by_decision", reasons_of(d, kit.B))
        self.assertEqual(kit.status(d, kit.A), "VERIFIED")

    def test_the_workflow_only_says_whether_a_key_exists(self):
        old = {k: os.environ.pop(k, None) for k in ("WATCH_SIGNING_KEY", "HAS_SIGNING_KEY")}
        try:
            self.assertEqual(trust.build(self.w.dir, self.w.data, now=kit.NOW)["run"]["signature"], "unsigned")
            os.environ["HAS_SIGNING_KEY"] = "true"
            self.assertEqual(trust.build(self.w.dir, self.w.data, now=kit.NOW)["run"]["signature"], "expected_signed")
            os.environ["HAS_SIGNING_KEY"] = "false"
            self.assertEqual(trust.build(self.w.dir, self.w.data, now=kit.NOW)["run"]["signature"], "unsigned")
        finally:
            for k, v in old.items():
                os.environ.pop(k, None)
                if v is not None: os.environ[k] = v

    def test_the_run_is_deterministic(self):
        a, b = self.w.trust(), self.w.trust()
        self.assertEqual(a["by_target"], b["by_target"])
        self.assertEqual(a["counts"], b["counts"])


class TestDriver(unittest.TestCase):
    def test_main_writes_the_file_and_stops_on_a_schema_break(self):
        w = kit.Watch()
        try:
            out = os.path.join(w.dir, "trust.json")
            self.assertEqual(trust.main(["--watch", w.dir, "--data", w.data, "--out", out]), 0)
            self.assertEqual(json.load(open(out))["rule_version"], tr.RULE_VERSION)
            os.remove(out)
            os.makedirs(os.path.join(w.dir, "schema"))
            json.dump({"type": "object", "required": ["nothing_like_this"]}, open(os.path.join(w.dir, "schema", "trust.schema.json"), "w"))
            self.assertEqual(trust.main(["--watch", w.dir, "--data", w.data, "--out", out]), 1)
            doc = json.load(open(out))                                 # fail closed: not the old file, not nothing: every target UNAVAILABLE and the reason said
            self.assertEqual(doc["counts"]["UNAVAILABLE"], doc["targets"])
            self.assertGreater(doc["targets"], 0)
            self.assertIn("schema", doc["error"])
            self.assertTrue(all([r["code"] for r in v["reasons"]] == ["trust_not_computed"] for v in doc["by_target"].values()))
        finally:
            w.close()

    def test_an_exception_overwrites_the_previous_file_with_unavailable(self):
        w = kit.Watch()
        orig = tr.derive_all
        try:
            out = os.path.join(w.dir, "trust.json")
            self.assertEqual(trust.main(["--watch", w.dir, "--data", w.data, "--out", out]), 0)
            self.assertEqual(json.load(open(out))["counts"]["UNAVAILABLE"], 0)
            tr.derive_all = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
            self.assertEqual(trust.main(["--watch", w.dir, "--data", w.data, "--out", out]), 1)
            doc = json.load(open(out))
            self.assertEqual(doc["counts"]["UNAVAILABLE"], doc["targets"])
            self.assertIn("boom", doc["error"])
        finally:
            tr.derive_all = orig
            w.close()

    def test_the_signing_key_is_unknown_when_nothing_can_be_compared(self):
        w = kit.Watch()
        orig = trust.pinned_keys
        try:
            trust.pinned_keys = lambda: ()                                   # no pin list: never "pinned", and no signature dimension at "ok"
            d0 = trust.build(w.dir, w.data, now=kit.NOW, key_present=True)
            self.assertEqual(d0["run"]["signature_key"], "unknown")
            self.assertTrue(all("signature_key_unverifiable" in reasons_of(d0, a) and d0["by_target"]["robinhood:" + a]["dimensions"]["signature"] == "unverified" for a in (kit.A, kit.B, kit.C)))
            trust.pinned_keys = orig
            w.edit("signature.json", lambda d: d.pop("public_key", None) and None)       # no key in the manifest: unknown too
            self.assertEqual(trust.build(w.dir, w.data, now=kit.NOW, key_present=True)["run"]["signature_key"], "unknown")
            w.edit("signature.json", lambda d: d.update({"public_key": "ab" * 32}))
            self.assertEqual(trust.build(w.dir, w.data, now=kit.NOW, key_present=True)["run"]["signature_key"], "not_pinned")
        finally:
            trust.pinned_keys = orig
            w.close()

    def test_the_open_executor_reason_lands_on_the_timelock_target_only(self):
        w = kit.Watch()
        try:
            w.edit("second_opinion.json", kit.so_edit(kit.B, open_executor=True))
            d = w.trust(key_present=True)
            self.assertEqual([a for a in (kit.A, kit.B, kit.C) if "executor_open" in reasons_of(d, a)], [kit.B])
            self.assertEqual(d["by_target"]["robinhood:" + kit.B]["status"], "VERIFIED")          # information, not a downgrade
        finally:
            w.close()

    def test_an_import_failure_still_overwrites_the_previous_file(self):
        w = kit.Watch()
        orig = trust.IMPORT_ERROR
        try:
            out = os.path.join(w.dir, "trust.json")
            self.assertEqual(trust.main(["--watch", w.dir, "--data", w.data, "--out", out]), 0)
            trust.IMPORT_ERROR = "ImportError: no module named x"
            self.assertEqual(trust.main(["--watch", w.dir, "--data", w.data, "--out", out]), 1)
            doc = json.load(open(out))
            self.assertIn("ImportError", doc["error"])
            self.assertEqual((doc["targets"], doc["by_target"]), (0, {}))
            errs = []
            schema = json.load(open(os.path.join(kit.ROOT, "watch", "schema", "trust.schema.json")))
            trust.validate_schemas.check(doc, schema, "trust.json", errs)
            self.assertEqual(errs, [])                                  # the fallback document still honours the schema
        finally:
            trust.IMPORT_ERROR = orig
            w.close()

    def test_a_solana_address_keeps_its_case_and_an_evm_one_loses_it(self):
        self.assertEqual(tr.norm_addr("0xAbC"), "0xabc")
        self.assertEqual(tr.norm_addr("9xQeWvG816bUx9EPjHmaT23yvVM2ZWbrrpZb9PusVFin"), "9xQeWvG816bUx9EPjHmaT23yvVM2ZWbrrpZb9PusVFin")

    def test_the_file_enters_the_signed_manifest(self):
        if not HAVE_NACL:
            self.skipTest("PyNaCl absent")
        import sign_run
        w = kit.Watch()
        try:
            self.assertEqual(trust.main(["--watch", w.dir, "--data", w.data]), 0)
            self.assertIn("trust.json", sign_run.manifest(w.dir)["files"])
        finally:
            w.close()

    def test_the_workflow_runs_it_before_the_signature(self):
        y = open(os.path.join(ROOT, ".github", "workflows", "watch.yml"), encoding="utf-8").read()
        self.assertIn("python3 scripts/trust.py --watch watch", y)
        self.assertLess(y.index("scripts/trust.py"), y.index("scripts/sign_run.py --watch watch > watch/signature.txt"))
        self.assertGreater(y.index("scripts/trust.py"), y.index("Shorten every root-signer address"))      # after the shortening: it copies sentences of the reader, which must not carry a signer address
        self.assertGreater(y.index("scripts/trust.py"), y.index("scripts/redact_signers.py --index"))

    def test_real_shape_of_the_watch_data_is_read(self):
        # the sample is a compact copy of the shapes of a real run (coverage of every file the rule reads)
        d = trust.gather(kit.BASE, tempfile.gettempdir())
        for name in ("latest", "second_opinion", "pause_state", "safe_activity", "side_roles", "held_assets", "tvl", "alerts", "methodology", "disputes", "signature", "chain"):
            self.assertIsInstance(d[name], dict, name)


if __name__ == "__main__":
    unittest.main()
