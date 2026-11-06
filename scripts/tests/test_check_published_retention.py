#!/usr/bin/env python3
"""scripts/check_published_retention.py on files in the shape the writers really produce (offline, planted): a listed operation past the limit fails wherever it is listed, a date that is not a usable number fails too, an unreadable file is never a pass.
Shapes: pending_ops.json results[].pending / results[].recent (check_pending_ops.py), alerts.json active[].evidence[] (evaluate_rules.py: the operation sits in `evidence`, never at the root of the alert)."""
import json, os, subprocess, sys, tempfile, time, unittest

HERE = os.path.dirname(os.path.abspath(__file__)); SCRIPT = os.path.join(HERE, "..", "check_published_retention.py"); sys.path.insert(0, os.path.join(HERE, ".."))
import check_published_retention as C  # noqa: E402

NOW = 1_790_000_000; DAY = 86400
NO_ALERTS = {"active": []}


def rec(pending=(), recent=()): return {"results": [{"address": "A1", "name": "tl", "pending": list(pending), "recent": list(recent)}], "discovered": 15}
def op(ready_at, **k): return dict({"id": "x:%s" % ready_at, "ready_at": ready_at, "eta": ready_at, "state": "pending"}, **k)
def alert(*evidence): return {"active": [{"rule": "r", "severity": "high", "chain": "c", "target": "T", "title": "t", "score": 3, "evidence": list(evidence), "reading": {}}]}   # the producer's shape
def evid(ready_at): return {"timelock": "tl", "timelock_address": "A1", "family": "squads", "id": "x", "chain": "solana", "tx": None, "selector": None, "signature": "s", "ready_at": ready_at, "state": "pending"}


class T(unittest.TestCase):
    def test_a_pending_operation_executable_for_more_than_seven_days_is_reported(self):
        bad = C.listed_too_long(rec([op(NOW - 8 * DAY), op(NOW - 6 * DAY), op(NOW + DAY)]), NO_ALERTS, NOW); self.assertEqual(len(bad), 1)
        self.assertEqual(C.listed_too_long(rec([op(NOW - 7 * DAY)]), NO_ALERTS, NOW), [])   # exactly seven days: still published, as lib/fresh_ops.py says

    def test_a_recent_row_still_queued_is_read_too_and_an_executed_one_is_not(self):
        old = {"id": "r1", "still_queued": True, "queued_at": NOW - 40 * DAY, "delay": 86400}
        self.assertEqual(len(C.listed_too_long(rec(recent=[old]), NO_ALERTS, NOW)), 1)
        self.assertEqual(C.listed_too_long(rec(recent=[dict(old, still_queued=False)]), NO_ALERTS, NOW), [])

    def test_an_alert_carries_its_operation_in_evidence_in_the_producers_shape(self):
        self.assertEqual(len(C.listed_too_long(rec(), alert(evid(NOW - 30 * DAY), evid(NOW + DAY)), NOW)), 1)
        self.assertEqual(C.listed_too_long(rec(), alert(evid(None)), NOW), [])   # a queue alert whose operation has no ready time yet: nothing to compare
        self.assertEqual(C.listed_too_long(rec(), {"active": [{"target": "T", "ready_at": NOW - 30 * DAY}]}, NOW), [])   # a root-level date is not a shape the producer writes: not read

    def test_a_date_that_is_not_a_usable_number_is_unreadable_never_a_pass(self):
        for bad_value in (0, -5, "1790000000", True):
            self.assertEqual(len(C.listed_too_long(rec([op(bad_value)]), NO_ALERTS, NOW)), 1, bad_value)
            self.assertEqual(len(C.listed_too_long(rec(), alert(evid(bad_value)), NOW)), 1, bad_value)

    REAL_EVIDENCE_KEYS = {"timelock", "timelock_address", "family", "id", "chain", "tx", "selector", "signature", "ready_at", "state"}   # copied once from a live alerts.json (watch-data, 05/11/2026): the keys of an evidence item

    def test_the_planted_evidence_has_exactly_the_keys_of_a_live_one(self):
        self.assertEqual(set(evid(1)), self.REAL_EVIDENCE_KEYS)

    def test_eta_is_checked_like_ready_at_even_beside_a_valid_ready_at(self):
        for bad_value in (0, "1790000000", True): self.assertEqual(len(C.listed_too_long(rec([op(NOW + DAY, eta=bad_value)]), NO_ALERTS, NOW)), 1, bad_value)

    def test_the_counts_say_what_was_read(self):
        self.assertEqual(C.counts(rec([op(NOW)], [{"still_queued": True}, {"still_queued": False}]), alert(evid(NOW), evid(NOW))), (1, 1, 2))
        self.assertEqual(C.counts(rec(), NO_ALERTS), (0, 0, 0))

    def test_the_writers_still_have_the_shape_this_check_reads(self):
        er = open(os.path.join(HERE, "..", "evaluate_rules.py"), encoding="utf-8").read(); cp = open(os.path.join(HERE, "..", "check_pending_ops.py"), encoding="utf-8").read()
        for needle in ('"ready_at": op.get("ready_at"), "state": op.get("state")})', '"evidence": evidence if '): self.assertIn(needle, er)
        for needle in ('out["pending"].append({**op, "ready_at": ready, "state": st})', 'out["recent"].append({**op, "still_queued": still', '"queued_at": logs_w3.eth.get_block'): self.assertIn(needle, cp)

    def test_the_command_exit_codes(self):
        with tempfile.TemporaryDirectory() as d:
            def put(po, al):
                json.dump(po, open(os.path.join(d, "pending_ops.json"), "w")); json.dump(al, open(os.path.join(d, "alerts.json"), "w"))
            def run(): return subprocess.run([sys.executable, "-B", SCRIPT, "--dir", d], capture_output=True, text=True).returncode
            self.assertEqual(run(), 2)                                       # files missing: unread, not a pass
            put(rec([op(time.time() - 30 * DAY)]), NO_ALERTS); self.assertEqual(run(), 1)
            put(rec([op(time.time() + DAY)]), NO_ALERTS); self.assertEqual(run(), 0)
            put(rec(), alert(evid(time.time() - 30 * DAY))); self.assertEqual(run(), 1)
            put(rec([op(0)]), NO_ALERTS); self.assertEqual(run(), 1)
            open(os.path.join(d, "alerts.json"), "w").write("not json"); self.assertEqual(run(), 2)


if __name__ == "__main__": unittest.main(verbosity=1)
