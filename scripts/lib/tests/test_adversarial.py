"""Tests for the trust status: scripts/lib/trust_rules.py, scripts/trust.py, the adversarial kit (scripts/adversarial/) and the delivery harness.

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
for p in (SCRIPTS, os.path.join(SCRIPTS, "lib"), os.path.join(SCRIPTS, "adversarial")):
    if p not in sys.path:
        sys.path.insert(0, p)
import trust  # noqa: E402
from lib import trust_rules as tr  # noqa: E402
import run as kit  # noqa: E402
import harness  # noqa: E402
try:
    import nacl.signing  # noqa: F401
    HAVE_NACL = True
except ImportError:
    HAVE_NACL = False
def reasons_of(doc, addr):
    return [r["code"] for r in doc["by_target"]["robinhood:" + addr]["reasons"]]


class TestKit(unittest.TestCase):
    def test_every_case_gives_its_expected_result(self):
        for name, fn in kit.CASES.items():
            if name.startswith(("05", "06")) and not HAVE_NACL:
                continue
            exp = kit.jload(kit.EXPECTED)["cases"][name]
            self.assertEqual(kit.compare(exp, fn()), [], name)

    def test_the_command_exits_zero(self):
        import contextlib, io
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(kit.main(["--allow-skip"]), 0)

    def test_a_wrong_expectation_is_reported(self):
        self.assertTrue(kit.compare({"status_of_B": "VERIFIED"}, {"status_of_B": "PARTIAL"}))
        self.assertTrue(kit.compare({"x": 1}, {}))
        self.assertEqual(kit.compare({"attack": "text", "x": 1}, {"x": 1}), [])

    def test_the_expected_file_names_every_case_and_says_it_was_written_first(self):
        exp = kit.jload(kit.EXPECTED)
        self.assertTrue(exp["written_before_first_run"])
        self.assertEqual(sorted(exp["cases"]), sorted(kit.CASES))
        self.assertGreaterEqual(len(exp["CHANGES"]), 1)     # a change to an expectation needs a line saying why
        self.assertIn("case 11", exp["CHANGES"][0])
        self.assertIn("BEFORE it was first run", exp["CHANGES"][0])
        for line in exp["CHANGES"]:
            self.assertNotIn("/" + "Users/", line)
            self.assertNotIn("work/", line)                     # a published file does not name a private folder

    def test_the_first_expectation_is_kept_and_every_difference_since_is_said(self):
        import hashlib
        first_path = os.path.join(kit.HERE, "EXPECTED-first.json")
        raw = open(first_path, "rb").read()
        self.assertIn(hashlib.sha256(raw).hexdigest(), kit.jload(kit.EXPECTED)["CHANGES"][0])      # the file the first change line points at is the one shipped
        first, now = json.loads(raw)["cases"], kit.jload(kit.EXPECTED)["cases"]
        changed = sorted(k for k in first if {x: y for x, y in first[k].items() if x not in ("exercises", "limits")} != {x: y for x, y in now[k].items() if x not in ("exercises", "limits")})
        said = " ".join(kit.jload(kit.EXPECTED)["CHANGES"][1:])
        for name in changed:
            self.assertIn("case " + name[:2], said, "case %s differs from the first expectation and no change line names it" % name)
        self.assertNotIn("11-alert-proof-replayable", first)


class TestDeliveryEndToEnd(unittest.TestCase):
    def test_fifteen_alerts_one_channel_down_nothing_lost_nothing_doubled(self):
        with harness.Delivery(15) as d:
            d.webhook.up = False
            d.run()
            self.assertEqual(len(d.discord.counts()), 10)
            self.assertEqual(len(d.webhook.counts()), 0)
            d.webhook.up = True
            runs, out = d.run_until_delivered()
            self.assertEqual(runs, 2)
            self.assertEqual(len(d.discord.counts()), 15)
            self.assertEqual(len(d.webhook.counts()), 15)
            self.assertEqual((d.discord.duplicates(), d.webhook.duplicates()), (0, 0))
            self.assertTrue(all(x["notified"] for x in out["active"]))

    def test_a_lost_answer_means_a_second_copy_never_a_lost_alert(self):
        with harness.Delivery(4, channels=("webhook",)) as d:
            d.webhook.lose_ack = True
            out = d.run()
            self.assertTrue(all(not x["notified"] for x in out["active"]))
            d.webhook.lose_ack = False
            d.run_until_delivered()
            self.assertEqual(sorted(d.webhook.counts()), sorted(d.targets))
            self.assertEqual(d.webhook.duplicates(), 4)             # at least once, said so in watch/API.md

    def test_the_receiver_checks_the_signature_so_a_wrong_secret_delivers_nothing(self):
        with harness.Delivery(2, channels=("webhook",)) as d:
            os.environ["ALERT_WEBHOOK_SECRET"] = "not-the-receivers-secret"
            out = d.run()
            self.assertEqual(d.webhook.received, [])
            self.assertTrue(all(not x["notified"] for x in out["active"]))

    def test_a_quiet_run_after_delivery_sends_nothing(self):
        with harness.Delivery(3) as d:
            d.run_until_delivered()
            n = (len(d.discord.received), len(d.webhook.received))
            d.run()
            self.assertEqual((len(d.discord.received), len(d.webhook.received)), n)


class TestNullIsNotZero(unittest.TestCase):
    """An unknown is null, never 0, from the reading to the rule that fires on it. Each assertion would fail if a stage turned None into 0."""

    def rule(self, expr, env):
        import evaluate_rules
        return evaluate_rules.ev(ast.parse(expr, mode="eval"), env)

    def test_a_null_compares_false_in_rules_and_zero_does_not(self):
        for expr in ("delta < 0", "delta <= 0", "delta > -5", "delta >= 0", "delta == 0", "tvl_usd >= 0", "ready_in_hours < 1", "age_days < 1"):
            self.assertFalse(self.rule(expr, {"delta": None, "tvl_usd": None, "ready_in_hours": None, "age_days": None}), expr)
        self.assertTrue(self.rule("delta == 0", {"delta": 0}))
        self.assertTrue(self.rule("delta <= 0", {"delta": 0}))
        self.assertTrue(self.rule("delta != 0", {"delta": None}))      # unknown is not zero

    def test_the_label_schema_keeps_null_and_zero_apart(self):
        import validate_schemas
        schema = json.load(open(os.path.join(ROOT, "watch", "schema", "label.schema.json")))
        props = schema["properties"]
        for k in ("keys_to_move", "react_hours", "money_per_key_usd"):
            for v in (0, None):
                errs = []
                validate_schemas.check(v, props[k], k, errs)
                self.assertEqual(errs, [], (k, v))
            errs = []
            validate_schemas.check("0", props[k], k, errs)
            self.assertTrue(errs, k)                                # the string "0" and the word "not read" are not a way to write unknown

    def test_the_new_readers_say_none_for_unknown(self):
        from lib import reader_audit as ra
        self.assertIsNone(ra.read_gap_seconds(None, 5))
        self.assertEqual(ra.read_gap_seconds(5, 5), 0)
        self.assertIsNone(ra.evaluation_of(None, 5, False))
        self.assertIsNone(ra.freshness_record(None, None, None, [])["oldest_push"])
        self.assertIsNone(ra.assemble_admin_members(None, None, [])["unread"])
        self.assertEqual(ra.assemble_admin_members(None, 3, [])["unread"], 3)
        self.assertEqual(ra.last_updated_alerts("x", [{"target": "0x1", "lastUpdated": 5}], {}, 0)[1], None)       # a block time of 0 is a value; None is the unknown
        self.assertIsNotNone(ra.last_updated_alerts("x", [{"target": "0x1", "lastUpdated": 5}], {}, None)[1])
        self.assertIsNone(tr.stale_days({"stale": True}, "2026-10-30T00:00:00Z"))
        self.assertEqual(tr.stale_days({"stale": True, "stale_since": "2026-10-30T00:00:00Z"}, "2026-10-30T00:00:00Z"), 0.0)

    def test_a_missing_file_is_not_a_zero_in_the_trust_document(self):
        w = kit.Watch()
        try:
            os.remove(os.path.join(w.dir, "second_opinion.json"))
            d = w.trust()
            self.assertEqual(d["counts"]["VERIFIED"], 0)            # no input, no verified
            self.assertNotIn("independent_read_missing", reasons_of(d, kit.A))
            self.assertIn("input_missing:second_opinion", reasons_of(d, kit.A))
        finally:
            w.close()


if __name__ == "__main__":
    unittest.main()
