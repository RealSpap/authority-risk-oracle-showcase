"""Tests for the readers added on 30 October 2026: scripts/lib/reader_audit.py and the scripts that call it.

No network, no key. The integration tests run `evaluate_rules.main()` and `score_series` on fixtures in a temporary directory, with the senders replaced by
local fakes that can fail on demand, so a delivery that is lost, doubled or caught up is a thing a test can state.
Each test was written to fail on the code of commit f73927b and to pass on the patched code.
"""
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, SCRIPTS)
sys.path.insert(0, os.path.join(SCRIPTS, "lib"))
from lib import reader_audit as ra  # noqa: E402
def read(path):
    with open(os.path.join(SCRIPTS, path), encoding="utf-8") as f:
        return f.read()
def modules_word(mods, nxt):
    """getModulesPaginated answer: offset, next, length, addresses."""
    w = "%064x" % 0x40 + "%064x" % nxt + "%064x" % len(mods)
    for m in mods:
        w += "%064x" % m
    return "0x" + w


class TestScanProgress(unittest.TestCase):


    def test_watch_run_calls_it(self):
        src = read("watch_run.py")
        self.assertIn("cur[\"scan_stalled_runs\"], extra = scan_progress(prev_doc, cur); alerts.extend(extra)", src)
        self.assertIn("cur[\"block_time\"] = block_time_of(cur[\"rpc\"], cur[\"block\"])", src)
        self.assertIn("alerts.extend(lu_alerts)", src)


class TestLastUpdated(unittest.TestCase):
    T = lambda self, a, lu: {"target": a, "lastUpdated": lu}
    A = "0x" + "11" * 20

    def test_watch_run_reads_the_block_time_and_wires_f1_f2(self):
        src = read("watch_run.py")
        self.assertIn("def block_time_of(", src)
        self.assertIn("last_updated_alerts(name, cur[\"targets\"], prev, cur.get(\"block_time\")", src)

    def test_block_time_of_reads_the_timestamp_and_fails_to_none(self):
        import watch_run
        orig = watch_run.rpc
        try:
            watch_run.rpc = lambda url, calls, tries=3: [{"timestamp": hex(1234)}]
            self.assertEqual(watch_run.block_time_of("u", 5), 1234)
            def boom(*a, **k): raise RuntimeError("down")
            watch_run.rpc = boom
            self.assertIsNone(watch_run.block_time_of("u", 5))
            watch_run.rpc = lambda url, calls, tries=3: [None]
            self.assertIsNone(watch_run.block_time_of("u", 5))
        finally:
            watch_run.rpc = orig


class TestFreshness(unittest.TestCase):


    def test_latest_json_carries_it(self):
        self.assertIn("freshness_record(cur.get(\"readAt\")", read("watch_run.py"))

    def test_the_evaluation_is_assigned_to_every_target(self):
        self.assertIn("t[\"evaluation\"] = evaluation_of(t.get(\"lastUpdated\"), newest_push, str(t[\"target\"]).lower() in fixed_set)", read("watch_run.py"))


class TestEvaluation(unittest.TestCase):


    def test_the_fixed_targets_come_from_the_pins_file(self):
        import watch_run
        fx = watch_run.fixed_scorer_targets()
        self.assertIn("0x026df18fbd2a7639089d0a16293383ec687a5ca1", fx)   # a Longbow vault
        self.assertEqual(len(fx), 9)


class DeliveryHarness(unittest.TestCase):
    """evaluate_rules.main() on a fixture directory, senders replaced by fakes that can fail."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cwd = os.getcwd()
        os.chdir(self.tmp.name)
        os.makedirs("watch/scores")
        json.dump({"version": 1, "about": "x", "rules": [{"name": "low score", "when": "score < 50", "severity": "high"}], "notify": {"min_severity": "medium"}}, open("rules.json", "w"))
        json.dump({"run_utc": "2026-10-30T00:00:00Z"}, open("watch/latest.json", "w"))
        json.dump({"matched": {}}, open("watch/tvl.json", "w"))
        self.sent = []
        self.ok = {"discord": True, "webhook": True}
        import evaluate_rules as ev
        self.ev = ev
        self._orig = (ev.post_json, ev.post_signed)
        ev.post_json = lambda url, p: (self.sent.append(("discord", [l for l in p["content"].split("\n") if l.startswith("[")])), self.ok["discord"])[1]
        ev.post_signed = lambda url, secret, p: (self.sent.append(("webhook", [a["target"] for a in p["alerts"]])), self.ok["webhook"])[1]
        self._env = {k: os.environ.get(k) for k in ("DISCORD_WEBHOOK_URL", "ALERT_WEBHOOK_URL", "ALERT_WEBHOOK_SECRET", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "TELEGRAM_MODE")}
        for k in self._env:
            os.environ.pop(k, None)

    def tearDown(self):
        self.ev.post_json, self.ev.post_signed = self._orig
        for k, v in self._env.items():
            os.environ.pop(k, None)
            if v is not None:
                os.environ[k] = v
        os.chdir(self.cwd)
        self.tmp.cleanup()

    def scores(self, n, composite=10):
        tg = ["0x" + "%040x" % i for i in range(1, n + 1)]
        json.dump({"kind": "evm", "name": "Robinhood", "oracle": "0x" + "ab" * 20, "rpc": "https://x", "block": 100, "readAt": 1790000000,
                   "targets": [{"target": t, "compositeScore": composite, "adminKeyScore": 10, "multisigScore": 10, "timelockScore": 10, "oracleAuthorityScore": 100,
                                "crossExposureScore": 100, "lastUpdated": 1789999000, "stale": False} for t in tg]}, open("watch/scores/robinhood-chain.json", "w"))
        return tg

    def run_rules(self):
        sys.argv = ["evaluate_rules.py", "--rules", "rules.json", "--scores", "watch/scores", "--latest", "watch/latest.json", "--out", "watch/alerts.json"]
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            try:
                self.ev.main()
            except SystemExit:
                pass
        return json.load(open("watch/alerts.json"))


class TestDeliveryIntegration(DeliveryHarness):


    def configure(self, discord=True, webhook=True):
        if discord:
            os.environ["DISCORD_WEBHOOK_URL"] = "http://discord.local/x"
        if webhook:
            os.environ["ALERT_WEBHOOK_URL"] = "https://hook.local/x"
            os.environ["ALERT_WEBHOOK_SECRET"] = "s"

    def test_a_channel_that_works_does_not_mark_the_alert_delivered_for_the_one_that_failed(self):
        self.configure()
        self.scores(3)
        self.ok["webhook"] = False
        out = self.run_rules()
        self.assertTrue(all(x["delivered"] == ["discord"] and x["notified"] is False for x in out["active"]))
        # the webhook comes back: only IT is sent the alerts, Discord is not told twice
        self.ok["webhook"] = True
        self.sent.clear()
        out = self.run_rules()
        self.assertEqual([c for c, _ in self.sent], ["webhook"])
        self.assertTrue(all(x["delivered"] == ["discord", "webhook"] and x["notified"] is True for x in out["active"]))
        # a third run sends nothing at all
        self.sent.clear()
        self.run_rules()
        self.assertEqual(self.sent, [])

    def test_a_lost_delivery_is_retried_and_a_double_one_is_not_sent(self):
        self.configure(webhook=False)
        self.scores(2)
        self.ok["discord"] = False
        out = self.run_rules()
        self.assertTrue(all(x["notified"] is False for x in out["active"]))
        self.ok["discord"] = True
        self.sent.clear()
        out = self.run_rules()
        self.assertEqual(len(self.sent), 1)
        self.assertTrue(all(x["notified"] for x in out["active"]))
        self.sent.clear()
        self.run_rules()
        self.assertEqual(self.sent, [])

    def test_the_cap_of_ten_leaves_the_rest_for_the_next_run(self):
        self.configure(webhook=False)
        self.scores(12)
        out = self.run_rules()
        self.assertEqual(sum(1 for x in out["active"] if x["notified"]), 10)
        self.sent.clear()
        out = self.run_rules()
        self.assertEqual(len(self.sent[0][1]), 2)
        self.assertTrue(all(x["notified"] for x in out["active"]))

    def test_with_no_channel_nothing_is_owed(self):
        self.scores(2)
        out = self.run_rules()
        self.assertTrue(all(x["notified"] for x in out["active"]))
        self.assertEqual(self.sent, [])


class TestStateUnverified(DeliveryHarness):


    def test_a_pause_state_unread_for_days_fires_a_rule_and_a_fresh_one_does_not(self):
        tg = self.scores(2, composite=90)
        mk = lambda t, since: {"paused": False, "via": "paused", "stale": True, "stale_since": since}
        json.dump({"generated_utc": "2026-10-30T00:00:00Z", "by_target": {
            "robinhood:" + tg[0]: mk(tg[0], "2026-10-20T00:00:00Z"), "robinhood:" + tg[1]: mk(tg[1], "2026-10-29T12:00:00Z")}}, open("watch/pause_state.json", "w"))
        rules = json.load(open("rules.json"))
        rules["rules"] = [{"name": "unverified", "when": "state_unverified", "severity": "info"}]
        json.dump(rules, open("rules.json", "w"))
        out = self.run_rules()
        self.assertEqual([x["target"] for x in out["active"]], [tg[0]])

    def test_a_safe_activity_unread_for_days_reaches_the_contracts_it_governs(self):
        tg = self.scores(1, composite=90)
        json.dump({"generated_utc": "2026-10-30T00:00:00Z", "by_safe": {"h": {"stale": True, "stale_since": "2026-10-10T00:00:00Z", "governs": ["robinhood:" + tg[0]]}}}, open("watch/safe_activity.json", "w"))
        rules = json.load(open("rules.json"))
        rules["rules"] = [{"name": "unverified", "when": "state_unverified", "severity": "info"}]
        json.dump(rules, open("rules.json", "w"))
        self.assertEqual(len(self.run_rules()["active"]), 1)

    def test_an_alert_that_is_not_about_a_queue_keeps_its_evidence_empty_and_carries_a_reading(self):
        tg = self.scores(1, composite=10)
        json.dump({"results": [{"chain": "robinhood", "address": "0xTL", "name": "TL", "status": "ok", "pending": [
            {"target": tg[0], "id": "0x1", "state": "waiting", "ready_at": int(time.time()) + 7200, "signature": "setOwner(address)", "timelock": "TL"}], "recent": []}]}, open("watch/pending_ops.json", "w"))
        out = self.run_rules()
        a = out["active"][0]
        self.assertEqual(a["evidence"], [])                       # `evidence` is the queued operations of a queue alert and nothing else (consumers read each item as one)
        self.assertEqual(a["reading"]["oracle_block"], 100)

    def test_the_shipped_rules_have_the_two_new_rules(self):
        rules = json.load(open(os.path.join(SCRIPTS, "..", "rules.json")))["rules"]
        self.assertEqual(sum(1 for r in rules if "state_unverified" in r["when"]), 2)


class TestAlarmGate(unittest.TestCase):
    NOW = 1_790_000_000
    iso = staticmethod(lambda t: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t)))

    def run_gate(self, d, log, cond="false"):
        import alarm_gate
        os.environ["ALARM_CONDITION"] = cond
        old = sys.argv
        sys.argv = ["alarm_gate.py", "--watch", d, "--run-log", log, "--write"]
        out = io.StringIO()
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
                alarm_gate.main()
        finally:
            sys.argv = old
            os.environ.pop("ALARM_CONDITION", None)
        return out.getvalue(), json.load(open(os.path.join(d, "alarm_state.json")))

    def files(self, d, disagree=()):
        json.dump({"disagreements": [{"chain": "base", "target": t_} for t_ in disagree]}, open(os.path.join(d, "second_opinion.json"), "w"))
        for f in ("methodology.json", "review_queue.json", "alerts.json"):
            json.dump({}, open(os.path.join(d, f), "w"))

    def test_the_gate_script_writes_the_state_that_makes_recovery_and_escalation_possible(self):
        with tempfile.TemporaryDirectory() as d:
            log = os.path.join(d, "run.log")
            open(log, "w").write("all quiet\n")
            self.files(d, disagree=("0xaa",))
            out, st = self.run_gate(d, log, "true")
            self.assertIn("mode=new", out)
            self.assertTrue(st["first_notified_utc"])
            self.assertEqual(list(st["first_seen"]), ["disagree:base:0xaa"])
            self.files(d)                                           # the disagreement is gone, the condition says the run is quiet
            out2, st2 = self.run_gate(d, log, "false")
            self.assertIn("mode=recovered", out2)
            self.assertEqual(st2["findings"], [])
            out3, _ = self.run_gate(d, log, "false")
            self.assertIn("mode=unrecognised", out3)                # the end of an alarm is told once

    def test_a_one_pass_alarm_event_is_not_an_alarm_to_clear(self):
        with tempfile.TemporaryDirectory() as d:
            log = os.path.join(d, "run.log")
            open(log, "w").write("ALARM a score fell\n")
            self.files(d)
            out, _ = self.run_gate(d, log, "true")
            self.assertIn("mode=new", out)
            open(log, "w").write("all quiet\n")
            out2, _ = self.run_gate(d, log, "false")
            self.assertIn("mode=unrecognised", out2)               # a score that fell once is not a state that ended: no "Alarm cleared" issue six hours later

    def test_a_file_the_gate_cannot_read_is_not_the_end_of_an_alarm(self):
        with tempfile.TemporaryDirectory() as d:
            log = os.path.join(d, "run.log")
            open(log, "w").write("all quiet\n")
            self.files(d, disagree=("0xaa",))
            self.run_gate(d, log, "true")
            os.remove(os.path.join(d, "second_opinion.json"))       # the reader crashed: the counters of the workflow would read zero
            out, _ = self.run_gate(d, log, "false")
            self.assertIn("mode=unrecognised", out)

    def test_the_workflow_has_the_cleared_step_and_the_escalation_title(self):
        y = open(os.path.join(SCRIPTS, "..", ".github", "workflows", "watch.yml"), encoding="utf-8").read()
        self.assertIn("steps.gate.outputs.mode == 'recovered'", y)
        self.assertIn("ESCALATION", y)
        i = y.index("Alarm cleared: the findings")
        self.assertIn("continue-on-error: true", y[i:i + 900])                   # a failed notice must not stop the run from being recorded
        j = y.index("ALARM_CONDITION:")
        self.assertIn("steps.run.outputs.code != '0'", y[j:j + 120])             # a crashed run (code 1) is not a quiet one


class TestAdminMembers(unittest.TestCase):
    A = lambda self, n: "0x" + "00" * 12 + ("%040x" % n)

    def test_second_opinion_wires_it(self):
        src = read("second_opinion.py")
        self.assertIn("admin_member_calls(targets[i][\"target\"], n_)", src)
        self.assertIn("rec[\"admin_members\"] = assemble_admin_members(", src)


class TestModulesPage(unittest.TestCase):


    def test_second_opinion_publishes_the_flag(self):     # wiring check (source)
        self.assertIn("rec[\"modules_truncated\"] = modules_truncated_of(mods, 50)", read("second_opinion.py"))
        self.assertIn("return parse_modules_page(word, 50)[0]", read("second_opinion.py"))


class TestPendingDefaultAdmin(unittest.TestCase):


    def test_second_opinion_reads_it(self):
        self.assertIn("pendingDefaultAdmin() (AccessControlDefaultAdminRules)", read("second_opinion.py"))


class TestTransferOutcome(unittest.TestCase):


    def test_second_opinion_publishes_the_outcome_and_the_way_a_transfer_is_followed(self):   # wiring check (source), the behaviour is in the tests above
        src = read("second_opinion.py")
        self.assertIn("rec[\"pending_outcome\"] = transfer_outcome(pr.get(\"pending_admin\"), rec.get(\"holder\"), rec.get(\"pending_admin\"), short, prev_via=pr.get(\"pending_via\"), clean_families=pend_clean.get(i))", src)
        self.assertIn("\"pending_follow\": PENDING_FOLLOW_NOTE", src)
        self.assertIn("since the last block read", ra.PENDING_FOLLOW_NOTE)
        self.assertIn("Not read as events", ra.PENDING_FOLLOW_NOTE)               # what the events do NOT cover is said next to what they do


class TestBlockHonoured(unittest.TestCase):
    A = "0x" + "%064x" % 5

    def test_probe_asks_block_one_and_never_raises(self):
        import watch_run
        orig = watch_run.rpc
        asked = []
        try:
            def honest(url, calls, tries=3):
                asked.append(calls[0][1][1]); return ["0x"]
            watch_run.rpc = honest
            self.assertTrue(watch_run.probe_block("u", "0xo", self.A)["honoured"])
            self.assertEqual(asked, ["0x1"])
            watch_run.rpc = lambda url, calls, tries=3: [self.A]
            self.assertFalse(watch_run.probe_block("u", "0xo", self.A)["honoured"])
            def boom(url, calls, tries=3): raise ValueError("[{'code': -32000, 'message': 'historical state abc is not available'}]")
            watch_run.rpc = boom
            self.assertIsNone(watch_run.probe_block("u", "0xo", self.A)["honoured"])
        finally:
            watch_run.rpc = orig

    def test_read_evm_publishes_the_pin_and_pins_only_when_asked(self):
        import watch_run
        orig = (watch_run.rpc, watch_run.batched, watch_run.self_watch)
        tags = {"n": []}
        def fake_rpc(url, calls, tries=3):
            m = calls[0][0]
            if m == "eth_blockNumber": return ["0x64"]
            tags["n"].append(calls[0][1][1])
            return ["0x1", "0x" + "%064x" % 777600] if len(calls) == 2 else ["0x"]
        def fake_batched(url, calls):
            tags["n"] += [c[1][1] for c in calls]
            if len(calls) == 1: return ["0x" + "00" * 12 + "ab" * 20]
            return ["0x" + "%064x" % i for i in range(8)] + ["0x" + "%064x" % 0] if False else ["0x" + "".join("%064x" % (i + 1) for i in range(8)), "0x" + "%064x" % 0]
        watch_run.rpc, watch_run.batched, watch_run.self_watch = fake_rpc, fake_batched, (lambda *a, **k: {"read": True})
        old = os.environ.pop("WATCH_PIN_BLOCK", None)
        try:
            doc = watch_run.read_evm("X", "0x" + "cd" * 20, "http://x")
            self.assertEqual((doc["pinned_block"], doc["reference_block"], doc["read_tag"]), (None, 100, "latest"))
            self.assertIn("block_probe", doc)
            self.assertTrue(all(t == "latest" for t in tags["n"] if t != "0x1"))
            tags["n"].clear()
            os.environ["WATCH_PIN_BLOCK"] = "1"
            doc = watch_run.read_evm("X", "0x" + "cd" * 20, "http://x")
            self.assertEqual((doc["pinned_block"], doc["read_tag"]), (100, "pinned"))
            self.assertTrue(all(t == "0x64" for t in tags["n"] if t != "0x1"), tags["n"])
            self.assertIn("0x1", tags["n"])                                     # the probe asks block 1 either way
        finally:
            watch_run.rpc, watch_run.batched, watch_run.self_watch = orig
            os.environ.pop("WATCH_PIN_BLOCK", None)
            if old is not None: os.environ["WATCH_PIN_BLOCK"] = old


class TestSnapshotMoneyOverlapsStamp(unittest.TestCase):


    def test_reading_evidence(self):
        meta = {"oracle": "0xor", "rpc": "https://rpc", "block": 77, "readAt": 5}
        ev = ra.reading_evidence(meta, {"kind": "eoa", "path": "owner()", "block_start": 1, "block_end": 2, "read_gap_seconds": 9}, {"target": "0xab", "compositeScore": 10, "lastUpdated": 3}, "k")
        self.assertEqual(ev["oracle_block"], 77)
        self.assertEqual(ev["second_opinion"]["block_end"], 2)
        self.assertIn("--block 77", ev["reproduce"])
        ev = ra.reading_evidence({}, None, {"target": "0xab"}, "k")
        self.assertIsNone(ev["reproduce"])
        self.assertIsNone(ev["second_opinion"])

    def test_alerts_carry_the_reading(self):
        class Harness(DeliveryHarness):
            def runTest(self): pass
        h = Harness()
        h.setUp()
        try:
            h.scores(1)
            out = h.run_rules()
            self.assertEqual(out["active"][0]["reading"]["oracle_block"], 100)
            self.assertIn("--block 100", out["active"][0]["reading"]["reproduce"])
        finally:
            h.tearDown()


class TestSecondReviewReserves(DeliveryHarness):


    def test_every_alert_carries_previous_run_and_a_reading(self):
        self.scores(2)
        out = self.run_rules()
        for x in out["active"]:
            self.assertIn("previous_run", x)                  # declared in watch/schema/alerts.schema.json
            self.assertIn("reading", x)
            self.assertIs(x["reading"]["reproduce_exact"], False)       # a read at `latest` is replayed at the head block of then, not identically

    def test_the_f1_and_scan_stall_alarm_lines_make_the_same_finding_at_every_run(self):
        import alarm_gate
        a1, _ = ra.last_updated_alerts("Base", [{"target": "0x" + "ab" * 20, "lastUpdated": 1_000_000}], {}, 1_000_000 - 4000)
        a2, _ = ra.last_updated_alerts("Base", [{"target": "0x" + "ab" * 20, "lastUpdated": 1_000_000}], {}, 1_000_000 - 4000 - 21600)
        prev = {"block": 100, "self_scanned_to": 90, "scan_stalled_runs": 1}
        s1 = ra.scan_progress(prev, {"name": "Base", "block": 200, "self_scanned_to": 90})[1]
        s2 = ra.scan_progress(dict(prev, block=200, scan_stalled_runs=5), {"name": "Base", "block": 300, "self_scanned_to": 90})[1]      # six runs now, not two: said again after a day
        self.assertTrue(a1 and a2 and s1 and s2)
        self.assertNotEqual(a1, a2)                            # the numbers do change
        def found(lines):
            with tempfile.TemporaryDirectory() as d:
                log = os.path.join(d, "run.log")
                open(log, "w").write("".join("ALARM " + l + "\n" for l in lines))
                return alarm_gate.findings(d, log)
        self.assertEqual(found(a1 + s1), found(a2 + s2))       # one finding for the whole standing state: the gate stays quiet instead of opening an issue every six hours

    def test_a_state_written_before_the_lot_still_escalates(self):
        old = {"findings": ["a"], "notified_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(1_790_000_000 - 80 * 3600))}      # no first_notified_utc
        self.assertEqual(ra.decide_gate({"a"}, old, 1_790_000_000), "escalation")

    def test_the_gate_script_writes_first_notified_from_an_old_state(self):
        import alarm_gate
        iso = lambda s: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(s))
        with tempfile.TemporaryDirectory() as d:
            log = os.path.join(d, "run.log")
            open(log, "w").write("ALARM x\n")
            st = {"findings": ["alarm:ALARM x"], "notified_utc": iso(time.time() - 30 * 3600)}
            json.dump(st, open(os.path.join(d, "alarm_state.json"), "w"))
            old = sys.argv
            sys.argv = ["alarm_gate.py", "--watch", d, "--run-log", log, "--write"]
            try:
                with contextlib.redirect_stdout(io.StringIO()) as out, contextlib.redirect_stderr(io.StringIO()):
                    alarm_gate.main()
            finally:
                sys.argv = old
            self.assertIn("mode=reminder", out.getvalue())
            self.assertEqual(json.load(open(os.path.join(d, "alarm_state.json")))["first_notified_utc"], st["notified_utc"])

    def test_the_title_says_how_many_alerts_the_channel_is_owed_while_the_text_lists_ten(self):
        os.environ["DISCORD_WEBHOOK_URL"] = "http://discord.local/x"
        self.scores(15)
        texts = []
        orig = self.ev.post_json
        self.ev.post_json = lambda url, p: (texts.append(p["content"]), True)[1]
        try:
            self.run_rules()
        finally:
            self.ev.post_json = orig
        self.assertIn("15 new alert(s)", texts[0])
        self.assertIn("10 listed", texts[0])
        self.assertEqual(sum(1 for l in texts[0].split("\n") if l.startswith("[high]")), 10)

    def test_in_daily_mode_telegram_is_owed_the_critical_alerts_before_the_cap_of_ten(self):
        import alerts
        os.environ["TELEGRAM_BOT_TOKEN"] = "t"; os.environ["TELEGRAM_CHAT_ID"] = "c"; os.environ["TELEGRAM_MODE"] = "daily"
        rules = {"version": 1, "about": "x", "notify": {"min_severity": "medium"}, "rules": [
            {"name": "low score", "when": "score < 50", "severity": "high"},
            {"name": "the contract has been paused since the previous run", "when": "score < 5", "severity": "high"}]}
        json.dump(rules, open("rules.json", "w"))
        tg = ["0x" + "%040x" % i for i in range(1, 14)]
        json.dump({"kind": "evm", "name": "Robinhood", "oracle": "0x" + "ab" * 20, "rpc": "https://x", "block": 100, "readAt": 1790000000,
                   "targets": [{"target": t_, "compositeScore": 2 if i == 12 else 10, "adminKeyScore": 10, "multisigScore": 10, "timelockScore": 10, "oracleAuthorityScore": 100,
                                "crossExposureScore": 100, "lastUpdated": 1789999000, "stale": False} for i, t_ in enumerate(tg)]}, open("watch/scores/robinhood-chain.json", "w"))
        carried = []
        orig = alerts.send_telegram_alert
        alerts.send_telegram_alert = lambda text: (carried.append(text), True)[1]
        try:
            out = self.run_rules()
        finally:
            alerts.send_telegram_alert = orig
        self.assertEqual(len(carried), 1)
        self.assertIn("1 critical alert", carried[0])             # the 12 ordinary ones did not fill the message
        live = [x for x in out["active"] if x["rule"].startswith("the contract has been paused")]
        self.assertTrue(live and all("telegram" in x["delivered"] for x in live))
        ordinary = [x for x in out["active"] if x["rule"] == "low score"]
        self.assertTrue(all(x["notified"] for x in ordinary))      # nobody owes them to Telegram in the daily mode


class TestNotHashed(unittest.TestCase):


    def test_no_scorer_set_covers_the_new_files(self):
        import methodology
        new = {"scripts/lib/reader_audit.py", "scripts/check_scorer_pins.py", "scripts/lib/reader_extras.py", "scripts/escalate.py"}
        for eco in ("robinhood-chain", "ethereum-l1", "arbitrum-ecosystem", "base-ecosystem", "tempo", "plasma-ecosystem", "monad", "hyperliquid", "solana"):
            files = set(methodology.scoring_files(eco, os.path.join(SCRIPTS, "..")))
            self.assertFalse(files & new, eco)
            for touched in ("scripts/watch_run.py", "scripts/evaluate_rules.py", "scripts/second_opinion.py", "scripts/alarm_gate.py"):
                self.assertNotIn(touched, files)


if __name__ == "__main__":
    unittest.main()
