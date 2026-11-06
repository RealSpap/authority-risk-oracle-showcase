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


    def doc(self, block, scanned, gap=None, read_ok=True):
        return {"name": "Base", "block": block, "self_scanned_to": scanned, "self": {"read": read_ok, **({"gap_blocks": gap} if gap else {})}}

    def test_a_gap_is_an_alert(self):
        _, alerts = ra.scan_progress(self.doc(100, 100), self.doc(5000, 5000, gap=4900))
        self.assertEqual(len(alerts), 1)
        self.assertIn("4900 blocks", alerts[0])

    def test_no_gap_no_alert_and_no_stall_when_the_marker_advances(self):
        stalled, alerts = ra.scan_progress(self.doc(100, 100), self.doc(200, 200))
        self.assertEqual((stalled, alerts), (0, []))

    def test_a_marker_that_does_not_move_while_the_chain_does_counts_runs_and_alerts_at_two(self):
        s1, a1 = ra.scan_progress(self.doc(100, 100), self.doc(200, 100))
        self.assertEqual((s1, a1), (1, []))
        prev = dict(self.doc(200, 100), scan_stalled_runs=1)
        s2, a2 = ra.scan_progress(prev, self.doc(300, 100))
        self.assertEqual(s2, 2)
        self.assertEqual(len(a2), 1)
        self.assertIn("2 runs", a2[0])

    def test_the_count_resets_when_the_marker_moves_again(self):
        prev = dict(self.doc(300, 100), scan_stalled_runs=3)
        self.assertEqual(ra.scan_progress(prev, self.doc(400, 400)), (0, []))

    def test_a_first_run_or_a_missing_marker_is_not_a_stall(self):
        self.assertEqual(ra.scan_progress({}, self.doc(100, 100)), (0, []))
        self.assertEqual(ra.scan_progress(self.doc(100, None), self.doc(200, None)), (0, []))


class TestLastUpdated(unittest.TestCase):
    T = lambda self, a, lu: {"target": a, "lastUpdated": lu}
    A = "0x" + "11" * 20

    def test_future_date_beyond_the_tolerance_is_f1(self):
        alerts, skip = ra.last_updated_alerts("Base", [self.T(self.A, 1000 + 301)], {}, 1000)
        self.assertEqual(len(alerts), 1)
        self.assertIn("after the block time", alerts[0])
        self.assertIsNone(skip)

    def test_a_date_inside_the_tolerance_is_fine(self):
        self.assertEqual(ra.last_updated_alerts("Base", [self.T(self.A, 1300)], {}, 1000)[0], [])

    def test_a_date_that_goes_back_is_f2_without_any_block_time(self):
        alerts, skip = ra.last_updated_alerts("Base", [self.T(self.A, 500)], {self.A: {"lastUpdated": 900}}, None)
        self.assertEqual(len(alerts), 1)
        self.assertIn("went back", alerts[0])
        self.assertIn("F1", skip)

    def test_an_unread_block_time_skips_f1_and_says_so(self):
        alerts, skip = ra.last_updated_alerts("Base", [self.T(self.A, 10 ** 12)], {}, None)
        self.assertEqual(alerts, [])
        self.assertIsNotNone(skip)

    def test_a_date_that_did_not_change_is_quiet(self):
        self.assertEqual(ra.last_updated_alerts("Base", [self.T(self.A, 900)], {self.A: {"lastUpdated": 900}}, 1000)[0], [])

    def test_no_block_time_is_never_read_as_zero(self):
        # with block_time 0 every date would be 'in the future'; None must skip, 0 must not be invented
        alerts, _ = ra.last_updated_alerts("Base", [self.T(self.A, 10)], {}, None)
        self.assertEqual(alerts, [])


class TestFreshness(unittest.TestCase):


    def test_four_ages_and_unknown_is_none(self):
        r = ra.freshness_record(1790000000, 100, 1789999990, [{"lastUpdated": 10}, {"lastUpdated": 30}, {"lastUpdated": None}])
        self.assertEqual(r, {"watch_read_at": 1790000000, "block": 100, "block_time": 1789999990, "newest_push": 30, "oldest_push": 10})
        r = ra.freshness_record(None, None, None, [])
        self.assertIsNone(r["newest_push"])
        self.assertIsNone(r["oldest_push"])


class TestEvaluation(unittest.TestCase):


    def test_three_values(self):
        self.assertEqual(ra.evaluation_of(1000, 1000, False), "recomputed")
        self.assertEqual(ra.evaluation_of(1000 - 7 * 3600, 1000, False), "kept")
        self.assertEqual(ra.evaluation_of(1000 - 6 * 3600, 1000, False), "recomputed")      # exactly six hours: still the same pass
        self.assertEqual(ra.evaluation_of(1000 - 6 * 3600 - 1, 1000, False), "kept")
        self.assertEqual(ra.evaluation_of(1, 1000, True), "fixed_by_decision")
        self.assertIsNone(ra.evaluation_of(None, 1000, False))


class TestDeliveryUnits(unittest.TestCase):


    def test_configured_channels_need_both_halves(self):
        self.assertEqual(ra.configured_channels({"ALERT_WEBHOOK_URL": "https://x"}), [])
        self.assertEqual(ra.configured_channels({"ALERT_WEBHOOK_URL": "https://x", "ALERT_WEBHOOK_SECRET": "s", "DISCORD_WEBHOOK_URL": "d", "TELEGRAM_BOT_TOKEN": "t"}), ["discord", "webhook"])

    def test_owed_channels(self):
        c = ["discord", "webhook"]
        self.assertEqual(ra.channels_still_owed(None, c), c)
        self.assertEqual(ra.channels_still_owed({"delivered": ["discord"]}, c), ["webhook"])
        self.assertEqual(ra.channels_still_owed({"notified": True}, c), [])           # written before this change, notified: delivered everywhere
        self.assertEqual(ra.channels_still_owed({"notified": False}, c), c)
        self.assertEqual(ra.channels_still_owed({"rule": "x"}, c), [])                 # an old entry with no field at all counts as notified (the file default)

    def test_batches_are_cut_at_the_cap_per_channel(self):
        keys = ["k%d" % i for i in range(12)]
        owed = {k: ["discord"] for k in keys}
        owed["k11"] = ["discord", "webhook"]
        b = ra.batches_for(keys, owed, ["discord", "webhook"])
        self.assertEqual(len(b["discord"]), 10)
        self.assertEqual(b["webhook"], ["k11"])

    def test_delivered_only_where_the_send_worked(self):
        b = {"discord": ["a"], "webhook": ["a"]}
        self.assertEqual(ra.delivered_after(None, "a", b, {"discord": True, "webhook": False}), ["discord"])
        self.assertEqual(ra.delivered_after(["discord"], "a", b, {"webhook": True}), ["discord", "webhook"])
        self.assertEqual(ra.delivered_after(None, "z", b, {"discord": True}), [])         # not in the batch: not delivered
        self.assertTrue(ra.is_notified(["discord"], []))
        self.assertFalse(ra.is_notified(["discord"], ["discord", "webhook"]))


class TestStateUnverifiedPure(unittest.TestCase):


    def test_units(self):
        gen = "2026-10-30T00:00:00Z"
        self.assertEqual(ra.unverified_days({"stale": True, "stale_since": "2026-10-26T00:00:00Z"}, gen), 4.0)
        self.assertIsNone(ra.unverified_days({"stale": False, "stale_since": "2026-10-01T00:00:00Z"}, gen))
        self.assertIsNone(ra.unverified_days({"stale": True}, gen))
        self.assertTrue(ra.state_unverified({"stale": True, "stale_since": "2026-10-27T00:00:00Z"}, gen))
        self.assertFalse(ra.state_unverified({"stale": True, "stale_since": "2026-10-29T00:00:00Z"}, gen))


class TestAlarmGate(unittest.TestCase):
    NOW = 1_790_000_000
    iso = staticmethod(lambda t: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t)))

    def st(self, hours_since_first, hours_since_last, findings=("a",)):
        return {"findings": list(findings), "notified_utc": self.iso(self.NOW - hours_since_last * 3600), "first_notified_utc": self.iso(self.NOW - hours_since_first * 3600)}

    def test_modes(self):
        d = ra.decide_gate
        self.assertEqual(d({"a"}, None, self.NOW), "new")
        self.assertEqual(d({"a", "b"}, self.st(5, 5), self.NOW), "new")
        self.assertEqual(d({"a"}, self.st(5, 5), self.NOW), "quiet")
        self.assertEqual(d({"a"}, self.st(30, 25), self.NOW), "reminder")
        self.assertEqual(d({"a"}, self.st(80, 25), self.NOW), "escalation")
        self.assertEqual(d(set(), self.st(30, 25), self.NOW, condition_holds=False), "recovered")
        self.assertEqual(d(set(), self.st(30, 25), self.NOW, condition_holds=True), "unrecognised")      # a cause the gate does not read is not the end of the alarm
        self.assertEqual(d(set(), self.st(30, 25), self.NOW), "unrecognised")                            # the caller did not say: never silence it
        self.assertEqual(d(set(), None, self.NOW), "unrecognised")
        self.assertEqual(d(set(), {"findings": [], "notified_utc": None}, self.NOW), "unrecognised")

    def test_a_new_finding_does_not_restart_the_clock_of_an_old_one(self):
        iso = lambda s: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(s))
        now = 1_790_000_000
        st = {"findings": ["a", "b"], "notified_utc": iso(now - 30 * 3600), "first_notified_utc": iso(now - 30 * 3600),
              "first_seen": {"a": iso(now - 100 * 3600), "b": iso(now - 30 * 3600)}}
        self.assertEqual(ra.decide_gate({"a", "b"}, st, now), "escalation")          # `a` has stood for 100 hours
        self.assertEqual(ra.decide_gate({"b"}, st, now), "reminder")                # only the newer one is left: 30 hours


class TestAdminMembers(unittest.TestCase):
    A = lambda self, n: "0x" + "00" * 12 + ("%040x" % n)

    def test_calls_cover_members_1_to_the_bound(self):
        calls = ra.admin_member_calls("0xabc", 4)
        self.assertEqual(len(calls), 3)
        self.assertTrue(calls[0][1][0]["data"].endswith("%064x" % 1))
        self.assertTrue(calls[2][1][0]["data"].endswith("%064x" % 3))
        self.assertEqual(len(ra.admin_member_calls("0xabc", 500)), ra.ADMIN_MEMBERS_CAP - 1)
        self.assertEqual(ra.admin_member_calls("0xabc", 1), [])
        self.assertEqual(ra.admin_member_calls("0xabc", None), [])

    def test_all_members_read(self):
        r = ra.assemble_admin_members("0x" + "0" * 39 + "1", 3, [self.A(2), self.A(3)])
        self.assertEqual((r["read"], r["unread"], r["note"]), (3, 0, None))

    def test_the_bound_says_how_many_were_not_read(self):
        r = ra.assemble_admin_members("0x" + "0" * 39 + "1", 25, [self.A(i) for i in range(2, 11)])
        self.assertEqual((r["read"], r["unread"]), (10, 15))
        self.assertIn("15 of 25", r["note"])
        self.assertIn("bound of 10", r["note"])

    def test_an_unanswered_member_is_unread_not_absent(self):
        r = ra.assemble_admin_members("0x" + "0" * 39 + "1", 3, [self.A(2), None])
        self.assertEqual((r["read"], r["unread"]), (2, 1))
        self.assertIn("missing", r["note"])

    def test_an_unknown_count_is_not_a_number(self):
        r = ra.assemble_admin_members("0x" + "0" * 39 + "1", None, [])
        self.assertIsNone(r["total"])
        self.assertIsNone(r["unread"])


class TestModulesPage(unittest.TestCase):


    def test_the_sentinel_means_complete(self):
        mods, trunc = ra.parse_modules_page(modules_word([5, 6], 1))
        self.assertEqual(len(mods), 2)
        self.assertFalse(trunc)

    def test_another_next_means_truncated(self):
        mods, trunc = ra.parse_modules_page(modules_word(list(range(10, 60)), 0x1234))
        self.assertEqual(len(mods), 50)
        self.assertTrue(trunc)

    def test_a_zero_next_is_not_an_end_of_list(self):
        self.assertEqual(ra.parse_modules_page(modules_word([5], 0)), (None, None))   # 31/10/2026: a Safe ends its list with the sentinel 1; zero is unread

    def test_a_malformed_answer_is_unread(self):
        self.assertEqual(ra.parse_modules_page(None), (None, None))
        self.assertEqual(ra.parse_modules_page("0x" + "00" * 10), (None, None))
        short = modules_word([5, 6, 7], 1)[:-64]                              # the length claims 3, the answer holds 2
        self.assertEqual(ra.parse_modules_page(short), (None, None))

    def test_the_flag_is_null_for_a_page_that_cannot_be_read(self):
        ok = "0x" + "%064x" % 0x40 + "%064x" % 1 + "%064x" % 1 + "%064x" % 7
        self.assertIs(ra.modules_truncated_of(ok), False)
        self.assertIs(ra.modules_truncated_of("0x" + "%064x" % 0x40 + "%064x" % 0xABC + "%064x" % 1 + "%064x" % 7), True)
        self.assertIsNone(ra.modules_truncated_of("0x" + "%064x" % 0x40 + "%064x" % 1 + "%064x" % 3 + "%064x" % 7))      # claims 3 modules and holds one: unreadable, not complete
        self.assertIsNone(ra.modules_truncated_of(None))
        self.assertIsNone(ra.modules_truncated_of("0x"))


class TestPendingDefaultAdmin(unittest.TestCase):


    def test_parse(self):
        w = "0x" + "%064x" % 0xABCDEF + "%064x" % 1795000000
        self.assertEqual(ra.parse_pending_default_admin(w), ("0x%040x" % 0xABCDEF, 1795000000))
        self.assertEqual(ra.parse_pending_default_admin("0x" + "0" * 128), (None, None))
        self.assertEqual(ra.parse_pending_default_admin("0x"), (None, None))
        self.assertEqual(ra.parse_pending_default_admin(None), (None, None))
        self.assertEqual(ra.PENDING_DEFAULT_ADMIN_SEL, "0xcf6eefb7")


class TestTransferOutcome(unittest.TestCase):


    def test_outcomes(self):
        o = ra.transfer_outcome
        self.assertIsNone(o(None, "0xa", None))
        self.assertEqual(o("0xB", "0xb", None), "accepted")
        self.assertEqual(o("0xb", "0xa", None, prev_via="pendingOwner() on the contract (Ownable2Step)", clean_families={"contract_owner"}), "cleared")
        self.assertEqual(o("0xb", "0xa", None), "unread")          # which getter showed it is not known: nothing is told
        self.assertEqual(o("0xb", "0xa", "0xc"), "replaced")
        self.assertIsNone(o("0xb", "0xa", "0xB"))                  # still pending, nothing to tell
        short = lambda a: str(a).lower()[:6]
        self.assertEqual(o("0xabcdef…1234", "0xabcdef9999", None, short), "accepted")        # a plain key is compared in its short form


class TestBlockHonoured(unittest.TestCase):
    A = "0x" + "%064x" % 5

    def test_truth_table(self):
        h = ra.block_honoured
        self.assertTrue(h(self.A, old_answer="0x"))                     # empty at block 1: the node looked at the old state
        self.assertTrue(h(self.A, old_answer="0x" + "%064x" % 2))
        self.assertFalse(h(self.A, old_answer=self.A))                  # the same answer: the tag is ignored
        self.assertIsNone(h(self.A, old_error="historical state 0xab is not available"))
        self.assertIsNone(h(self.A, old_error="missing trie node"))
        self.assertTrue(h(self.A, old_error="execution reverted"))
        self.assertIsNone(h(self.A, old_error="ConnectionError: refused"))
        self.assertIsNone(h(None, old_answer="0x"))                     # nothing to compare to at the head
        self.assertIsNone(h("0x", old_answer="0x"))
        self.assertIsNone(h(self.A))


class TestEvidenceMatches(unittest.TestCase):


    def doc(self):
        return {"oracle": "0xor", "rpc": "https://rpc", "block": 77, "readAt": 5, "targets": [{"target": "0xAB", "compositeScore": 10}]}

    def reading(self):
        return {"oracle": "0xor", "oracle_block": 77, "oracle_read_at": 5, "composite": 10, "reproduce": "cast call 0xor 'getScore(address)' 0xAB --rpc-url https://rpc --block 77"}

    def test_a_faithful_proof_matches(self):
        self.assertEqual(ra.evidence_matches(self.reading(), self.doc(), "0xab"), (True, []))

    def test_each_alteration_is_caught(self):
        for k, v in (("oracle_block", 78), ("oracle", "0xother"), ("composite", 11), ("oracle_read_at", 6), ("reproduce", "cast call 0xor 'getScore(address)' 0xAB --rpc-url https://rpc --block 78"),
                     ("reproduce", None)):
            r = dict(self.reading(), **{k: v})
            self.assertFalse(ra.evidence_matches(r, self.doc(), "0xab")[0], k)
        self.assertFalse(ra.evidence_matches(self.reading(), self.doc(), "0xzz")[0])
        self.assertFalse(ra.evidence_matches({}, self.doc(), "0xab")[0])


class TestReadGap(unittest.TestCase):


    def test_seconds_not_blocks(self):
        self.assertEqual(ra.read_gap_seconds(100, 160), 60)
        self.assertEqual(ra.read_gap_seconds(200, 160), 0)
        self.assertIsNone(ra.read_gap_seconds(None, 160))
        self.assertIsNone(ra.read_gap_seconds(True, 160))


class TestDepthLimit(unittest.TestCase):


    def test_a_safe_below_the_bound_is_a_hit_and_a_plain_contract_is_not(self):
        from lib.nested_signers import MAX_DEPTH, build_tree
        # a chain of Safes, each owned by the next one, deeper than the bound
        names = ["0x" + "%040x" % i for i in range(1, MAX_DEPTH + 4)]
        safes = {names[i]: ([names[i + 1]], 1) for i in range(len(names) - 1)}
        get_code = lambda a: bytes([1, 2, 3]) if a in names else None
        get_safe = lambda a: safes.get(a)
        tree = build_tree(names[0], get_code, get_safe)
        hits = ra.depth_limit_hits(tree, get_safe, MAX_DEPTH)
        self.assertEqual(hits, [names[MAX_DEPTH]])
        # the same shape where the node at the bound is not a Safe: no hit
        no_safe = lambda a: safes.get(a) if a != names[MAX_DEPTH] else None
        tree2 = build_tree(names[0], get_code, no_safe)
        self.assertEqual(ra.depth_limit_hits(tree2, no_safe, MAX_DEPTH), [])

    def test_a_probe_that_fails_is_not_a_hit(self):
        node = {"kind": "contract", "addr": "0x1", "kids": []}
        def boom(a): raise RuntimeError("rpc")
        self.assertEqual(ra.depth_limit_hits(node, boom, 0), [])

    def test_the_checker_uses_it(self):
        self.assertIn("depth_limit_hits(tree, get_safe, MAX_DEPTH)", read("check_nested_signers.py"))


class TestFinalState(unittest.TestCase):


    def test_oz(self):
        self.assertIsNone(ra.final_state("oz", True))
        self.assertEqual(ra.final_state("oz", False, done=True), "executed")
        self.assertEqual(ra.final_state("oz", False, done=False), "cancelled")
        self.assertEqual(ra.final_state("oz", False, done=None), "unknown")

    def test_compound(self):
        self.assertEqual(ra.final_state("compound", False, executed_events=1, cancelled_events=0), "executed")
        self.assertEqual(ra.final_state("compound", False, executed_events=0, cancelled_events=2), "cancelled")
        self.assertEqual(ra.final_state("compound", False, executed_events=0, cancelled_events=0), "unknown")      # left the queue, no event found: the event read missed it, it did NOT expire
        self.assertEqual(ra.final_state("compound", False, expired=True), "unknown")        # events not looked for or unread

    def test_the_ledger_keeps_it(self):
        import warning_ledger as wl
        T0 = 1_790_000_000
        po = lambda recent=(), pending=(): {"results": [{"chain": "ethereum", "address": "0xAA", "name": "TL", "status": "ok", "pending": list(pending), "recent": list(recent), "delay": 7200}]}
        op = lambda i, queued, **kw: {"id": i, "queued_at": T0 - 100, "still_queued": queued, "decoded": "authority change", **kw}
        l1 = wl.update(None, po(pending=[op("b", True, eta=T0 + 30 * 3600)]), T0)
        l2 = wl.update(l1, po(recent=[op("b", False, final_state="cancelled")]), T0 + 6 * 3600)
        self.assertEqual(l2["entries"]["ethereum:0xaa:b"]["final_state"], "cancelled")
        l3 = wl.update(l2, po(recent=[op("c", False, queued_at=T0 + 7 * 3600)]), T0 + 12 * 3600)
        self.assertEqual(l3["entries"]["ethereum:0xaa:c"]["final_state"], "unknown")        # no state given: unknown, never guessed
        l4 = wl.update(wl.update(None, po(pending=[op("d", True, eta=T0 + 9 * 3600)]), T0), po(), T0 + 6 * 3600)
        self.assertEqual(l4["entries"]["ethereum:0xaa:d"]["final_state"], "unknown")        # it left the files

    def test_check_pending_ops_records_it_and_the_window(self):
        src = read("check_pending_ops.py")
        self.assertIn("\"final_state\": fin", src)
        self.assertIn("out.update(window_fields(head, start, block_time))", src)

    def test_window_fields(self):
        self.assertEqual(ra.window_fields(1000, 0, 12)["window_blocks"], 1000)
        self.assertEqual(ra.window_fields(7200, 0, 12)["window_days_est"], 1.0)
        self.assertEqual(ra.window_fields(5, 10, 12)["window_blocks"], 0)


class TestMethodBreak(unittest.TestCase):


    def test_points_after_a_change_on_their_chain_are_marked(self):
        series = {"robinhood:0xa": [{"t": "2026-10-01T00:00:00Z", "composite": 50, "from": "push"}, {"t": "2026-10-10T00:00:00Z", "composite": 52, "from": "watch"}, {"t": "2026-10-20T00:00:00Z", "composite": 52, "from": "watch"}],
                  "base:0xb": [{"t": "2026-10-01T00:00:00Z", "composite": 50, "from": "push"}, {"t": "2026-10-20T00:00:00Z", "composite": 50, "from": "watch"}]}
        meth = {"robinhood": [{"t": "2026-10-05T00:00:00Z", "from": "0xold", "to": "0xnew"}]}
        ra.mark_method_breaks(series, meth)
        self.assertEqual([p["method_break"] for p in series["robinhood:0xa"]], [False, True, False])
        self.assertEqual(series["robinhood:0xa"][1]["method_change"], {"from": "0xold", "to": "0xnew"})
        self.assertEqual([p["method_break"] for p in series["base:0xb"]], [False, False])

    def test_a_change_exactly_at_the_previous_point_belongs_to_that_point_not_the_next(self):
        series = {"base:0xb": [{"t": "2026-10-05T00:00:00Z", "composite": 1, "from": "push"}, {"t": "2026-10-10T00:00:00Z", "composite": 1, "from": "watch"}]}
        ra.mark_method_breaks(series, {"base": [{"t": "2026-10-05T00:00:00Z"}]})
        self.assertEqual([p["method_break"] for p in series["base:0xb"]], [False, False])

    def test_a_change_exactly_at_the_point_time_counts_and_the_first_point_never(self):
        series = {"base:0xb": [{"t": "2026-10-05T00:00:00Z", "composite": 1, "from": "push"}, {"t": "2026-10-10T00:00:00Z", "composite": 1, "from": "watch"}]}
        ra.mark_method_breaks(series, {"base": [{"t": "2026-10-10T00:00:00Z"}, {"t": "2026-10-05T00:00:00Z"}]})
        self.assertEqual([p["method_break"] for p in series["base:0xb"]], [False, True])

    def test_score_series_end_to_end(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "scores"))
            addr = "0x" + "11" * 20
            json.dump({"kind": "evm", "targets": [{"target": addr, "compositeScore": 40, "lastUpdated": 1790000000}]}, open(os.path.join(d, "scores", "robinhood-chain.json"), "w"))
            ev = [{"run_utc": "2026-10-10T00:00:00Z", "kind": "move", "oracle": "Robinhood Chain", "target": addr, "field": "compositeScore", "before": 30, "after": 35},
                  {"run_utc": "2026-10-09T00:00:00Z", "kind": "methodology_changed", "chain": "robinhood", "from": "0xa", "to": "0xb"}]
            open(os.path.join(d, "events.jsonl"), "w").write("\n".join(json.dumps(e) for e in ev) + "\n")
            json.dump({"results": [
                {"chain": "robinhood", "address": "0xTL", "name": "T", "status": "ok", "pending": [], "recent": [
                    {"target": addr, "queued_at": int(time.time()) - 86400, "undecoded": True},
                    {"target": addr, "queued_at": int(time.time()) - 86400, "touches_governed": False},
                    {"target": addr, "queued_at": int(time.time()) - 86400, "undecoded": True}]}]}, open(os.path.join(d, "pending.json"), "w"))
            r = subprocess.run([sys.executable, "-B", "-E", os.path.join(SCRIPTS, "score_series.py"), "--scores", os.path.join(d, "scores"), "--events", os.path.join(d, "events.jsonl"),
                                "--pending", os.path.join(d, "pending.json"), "--out", os.path.join(d, "out.json")], capture_output=True, text=True, cwd=SCRIPTS)
            self.assertEqual(r.returncode, 0, r.stderr)
            out = json.load(open(os.path.join(d, "out.json")))
            pts = out["series"]["robinhood:" + addr]
            self.assertTrue(any(p.get("method_break") for p in pts))
            self.assertEqual(out["calibration"]["excluded_undecoded"], 2)
            self.assertEqual(out["calibration"]["excluded_other_target"], 1)


class TestSnapshotMoneyOverlapsStamp(unittest.TestCase):


    def test_snapshot_status(self):
        now = 1_793_000_000       # 2026-10-26
        s = ra.snapshot_status("2026-10-21", 30, now)
        self.assertEqual((s["swept_utc"], s["valid_until_utc"], s["expired"]), ("2026-10-21", "2026-11-20", False))
        self.assertTrue(ra.snapshot_status("2026-10-21", 30, 1_800_000_000)["expired"])
        self.assertEqual(ra.snapshot_status(None, 30, now), {"swept_utc": None, "valid_until_utc": None, "expired": None})
        self.assertEqual(ra.snapshot_status("oops", 30, now)["expired"], None)

    def test_cross_chain_carries_the_snapshot(self):
        src = read("cross_chain.py")
        self.assertIn("exposure_snapshot_utc", src)
        d = json.load(open(os.path.join(SCRIPTS, "..", "data", "cross_snapshot.json")))
        self.assertEqual(d["swept_utc"], "2026-10-21")

    def test_money_source(self):
        scope = {"c:a": {"scope": "retired"}}
        tvl = {"c:b": {"scope": "total"}, "c:c": {"scope": "chain"}, "c:d": {"scope": "contract"}}
        held = {"c:e": {"held_usd": 5}}
        f = lambda k: ra.money_source(k, tvl, scope, held)
        self.assertEqual([f(k) for k in ("c:a", "c:b", "c:c", "c:d", "c:e", "c:z")], ["out_of_scope", "protocol_total", "chain_figure", "contract_figure", "held_by_contract", "none"])

    def test_overlaps_count_the_shared_money_once(self):
        money = lambda ks: 10.0 * len(ks)
        r = ra.cause_overlaps({"a": {"1", "2"}, "b": {"2", "3"}, "c": {"9"}}, money)
        self.assertEqual(r["pairs"], {"a + b": {"contracts": 1, "tvl_usd": 10}})
        self.assertEqual(r["any_cause"], {"contracts": 4, "tvl_usd": 40})
        self.assertEqual(ra.cause_overlaps({}, money)["any_cause"]["contracts"], 0)

    def test_risk_by_cause_publishes_both(self):
        src = read("risk_by_cause.py")
        self.assertIn("cause_overlaps(hit_sets", src)
        self.assertIn("out[cid][\"money_source\"]", src)

    def test_stamp_check(self):
        e = ra.stamp_check({"impl": "0x1", "verified": True}, "NOW", "abc", {"checked_at": "OLD"})
        self.assertEqual((e["checked_at"], e["deployed_code_sha256"]), ("NOW", "abc"))
        e = ra.stamp_check({"impl": "0x1", "verified": True, "stale": True}, "NOW", "abc", {"checked_at": "OLD", "deployed_code_sha256": "oldhash"})
        self.assertEqual((e["checked_at"], e["deployed_code_sha256"]), ("OLD", "oldhash"))
        e = ra.stamp_check({"impl": "0x1", "verified": None}, "NOW", None)
        self.assertEqual((e["checked_at"], e["deployed_code_sha256"]), (None, None))
        e = ra.stamp_check({"impl": "0x1", "verified": False}, "NOW", None)
        self.assertEqual(e["checked_at"], "NOW")                  # Sourcify answered "not verified": that answer has a time

    def test_impl_sources_stamps_every_entry(self):
        src = read("impl_sources.py")
        self.assertEqual(src.count("stamp_check("), 4)

    def test_no_getter(self):
        self.assertTrue(ra.no_getter_recognised(["0x", "0x", "0x"]))
        self.assertFalse(ra.no_getter_recognised(["0x", None, "0x"]))
        self.assertFalse(ra.no_getter_recognised(["0x", "0x" + "00" * 31 + "01", "0x"]))
        self.assertFalse(ra.no_getter_recognised([]))
        self.assertIn("\"no_getter_recognised\": sorted(no_getter)", read("side_roles.py"))
        self.assertIn("no_getter_recognised(r[len(names) * i:len(names) * (i + 1)])", read("side_roles.py"))


class TestCrossChainAndRiskByCause(unittest.TestCase):


    def fixture(self, d):
        a1, a2 = "0x" + "a1" * 20, "0x" + "b2" * 20
        os.makedirs(os.path.join(d, "watch", "scores")); os.makedirs(os.path.join(d, "data"))
        for slug, addr in (("robinhood-chain", a1), ("base-sepolia", a2)):
            json.dump({"kind": "evm", "targets": [{"target": addr, "compositeScore": 40, "lastUpdated": 1790000000}]}, open(os.path.join(d, "watch", "scores", slug + ".json"), "w"))
        json.dump({"matched": {"robinhood:" + a1: {"slug": "p", "name": "P", "tvl": 1e6, "scope": "chain", "chain": "Robinhood Chain"},
                               "base:" + a2: {"slug": "p", "name": "P", "tvl": 2e6, "scope": "chain", "chain": "Base"}}}, open(os.path.join(d, "watch", "tvl.json"), "w"))
        json.dump({"results": [{"chain": "robinhood", "target": a1, "kind": "eoa"}, {"chain": "base", "target": a2, "kind": "eoa", "pending_admin": "0xabc"}]}, open(os.path.join(d, "watch", "second_opinion.json"), "w"))
        json.dump({"swept_utc": "2026-10-21", "valid_days": 30}, open(os.path.join(d, "data", "cross_snapshot.json"), "w"))
        return a1, a2

    def run_script(self, name, d, *extra):
        r = subprocess.run([sys.executable, "-B", "-E", os.path.join(SCRIPTS, name), "--watch", os.path.join(d, "watch"), "--out", os.path.join(d, "watch", name[:-3] + ".json"), "--data", os.path.join(d, "data")] + list(extra),
                           capture_output=True, text=True, cwd=SCRIPTS)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.load(open(os.path.join(d, "watch", name[:-3] + ".json")))

    def test_cross_chain_says_which_sweep_each_chain_rests_on(self):
        with tempfile.TemporaryDirectory() as d:
            self.fixture(d)
            out = self.run_script("cross_chain.py", d)
            self.assertEqual(out["exposure_snapshot"]["swept_utc"], "2026-10-21")
            self.assertEqual(out["exposure_snapshot"]["valid_until_utc"], "2026-11-20")
            chains = out["items"][0]["chains"]
            self.assertEqual({c["exposure_snapshot_utc"] for c in chains.values()}, {"2026-10-21"})
            os.remove(os.path.join(d, "data", "cross_snapshot.json"))
            out = self.run_script("cross_chain.py", d)
            self.assertIsNone(out["items"][0]["chains"]["robinhood"]["exposure_snapshot_utc"])      # no date recorded: null, not a made-up one

    def test_the_sweep_date_is_per_target_then_per_chain_then_the_files(self):
        now = 1_793_000_000
        snap = {"swept_utc": "2026-10-21", "valid_days": 30, "chains": {"base": {"swept_utc": "2026-10-10"}}, "targets": {"robinhood:0xaa": {"swept_utc": "2026-08-01", "valid_days": 30}}}
        f = lambda ka: ra.snapshot_for(snap, ka, now)
        self.assertEqual((f("robinhood:0xAA")["swept_utc"], f("robinhood:0xAA")["from"], f("robinhood:0xAA")["expired"]), ("2026-08-01", "target", True))     # the key is lower-cased
        self.assertEqual((f("base:0xbb")["swept_utc"], f("base:0xbb")["from"]), ("2026-10-10", "chain"))
        self.assertEqual((f("tempo:0xcc")["swept_utc"], f("tempo:0xcc")["from"]), ("2026-10-21", "global"))
        none = ra.snapshot_for({}, "tempo:0xcc", now)
        self.assertEqual((none["swept_utc"], none["expired"], none["from"]), (None, None, "none"))                    # no date: unknown, never made up
        self.assertEqual(ra.snapshot_for({"swept_utc": "not a date"}, "tempo:0xcc", now)["from"], "none")
        bad = ra.snapshot_for({"swept_utc": "2026-10-21", "targets": {"tempo:0xcc": {"swept_utc": "garbage"}}}, "tempo:0xcc", now)
        self.assertEqual(bad["from"], "global")                                                                       # an unreadable target date falls back, it does not erase the file's

    def test_cross_chain_publishes_the_sweep_of_each_target_and_the_oldest_per_chain(self):
        with tempfile.TemporaryDirectory() as d:
            a1, a2 = self.fixture(d)
            json.dump({"swept_utc": "2026-10-21", "valid_days": 30, "targets": {"robinhood:" + a1: {"swept_utc": "2026-08-01"}}}, open(os.path.join(d, "data", "cross_snapshot.json"), "w"))
            out = self.run_script("cross_chain.py", d)
            chains = out["items"][0]["chains"]
            self.assertEqual(chains["robinhood"]["exposure_snapshot_utc"], "2026-08-01")
            self.assertEqual(chains["robinhood"]["targets"][0]["from"], "target")
            self.assertEqual(chains["robinhood"]["exposure_snapshot_expired_targets"], 1)
            self.assertEqual(chains["base"]["exposure_snapshot_utc"], "2026-10-21")
            self.assertEqual(chains["base"]["exposure_snapshot_expired_targets"], 0)

    def test_a_target_with_no_date_at_all_is_unknown_not_expired(self):
        with tempfile.TemporaryDirectory() as d:
            a1, a2 = self.fixture(d)
            json.dump({"valid_days": 30, "targets": {"robinhood:" + a1: {"swept_utc": "2026-10-20"}}}, open(os.path.join(d, "data", "cross_snapshot.json"), "w"))     # no date for the file, none for base
            out = self.run_script("cross_chain.py", d)["items"][0]["chains"]
            self.assertEqual((out["robinhood"]["exposure_snapshot_unknown_targets"], out["robinhood"]["exposure_snapshot_expired_targets"]), (0, 0))
            self.assertEqual((out["base"]["exposure_snapshot_utc"], out["base"]["exposure_snapshot_unknown_targets"], out["base"]["exposure_snapshot_expired_targets"]), (None, 1, 0))

    def test_the_oldest_sweep_of_a_chain_and_the_order_target_chain_file(self):
        with tempfile.TemporaryDirectory() as d:
            a1, a2 = self.fixture(d)
            a3 = "0x" + "a3" * 20
            sp = os.path.join(d, "watch", "scores", "robinhood-chain.json")
            doc = json.load(open(sp)); doc["targets"].append({"target": a3, "compositeScore": 40, "lastUpdated": 1790000000}); json.dump(doc, open(sp, "w"))
            tp = os.path.join(d, "watch", "tvl.json")
            tv = json.load(open(tp)); tv["matched"]["robinhood:" + a3] = {"slug": "p", "name": "P", "tvl": 1e6, "scope": "chain", "chain": "Robinhood Chain"}; json.dump(tv, open(tp, "w"))
            json.dump({"swept_utc": "2026-10-21", "valid_days": 30, "chains": {"robinhood": {"swept_utc": "2026-09-15"}}, "targets": {"robinhood:" + a1: {"swept_utc": "2026-08-01"}}},
                      open(os.path.join(d, "data", "cross_snapshot.json"), "w"))
            ch = self.run_script("cross_chain.py", d)["items"][0]["chains"]["robinhood"]
            by = {x["target"]: x for x in ch["targets"]}
            self.assertEqual((by[a1]["swept_utc"], by[a1]["from"]), ("2026-08-01", "target"))      # the target's own date wins over its chain's
            self.assertEqual((by[a3]["swept_utc"], by[a3]["from"]), ("2026-09-15", "chain"))
            self.assertEqual(ch["exposure_snapshot_utc"], "2026-08-01")                          # the OLDEST of the two
            self.assertEqual(ch["exposure_snapshot_expired_targets"], 2)                         # 2026-08-01 and 2026-09-15 are both past 30 days

    def test_risk_by_cause_says_where_each_figure_comes_from_and_what_overlaps(self):
        with tempfile.TemporaryDirectory() as d:
            a1, a2 = self.fixture(d)
            out = self.run_script("risk_by_cause.py", d)
            causes = out["causes"]
            self.assertEqual(causes["plain_key_admin"]["money_source"], {"robinhood:" + a1: "chain_figure", "base:" + a2: "chain_figure"})
            self.assertIn("overlaps", out)
            self.assertEqual(out["overlaps"]["any_cause"]["contracts"], 2)
            self.assertTrue(any("plain_key_admin" in k for k in out["overlaps"]["pairs"]))


class TestScorerPins(unittest.TestCase):


    def test_evaluate_pin(self):
        pin = {"id": "p", "reads": [{"name": "a", "expect": 1}, {"name": "b", "expect": 2}]}
        self.assertEqual(ra.evaluate_pin(pin, {"a": 1, "b": 2})["status"], "ok")
        r = ra.evaluate_pin(pin, {"a": 1, "b": 3})
        self.assertEqual((r["status"], r["differences"][0]["read"]), ("changed", "b"))
        self.assertEqual(ra.evaluate_pin(pin, {"a": 1, "b": None})["status"], "unread")
        self.assertEqual(ra.evaluate_pin(pin, {"a": 9, "b": None})["status"], "changed")        # a difference wins over an unread
        self.assertEqual(ra.evaluate_pin({"id": "p"}, {})["status"], "unread")                   # no reads is not ok

    def test_zero_is_a_value_not_unread(self):
        pin = {"id": "p", "reads": [{"name": "delay", "expect": 0}]}
        self.assertEqual(ra.evaluate_pin(pin, {"delay": 0})["status"], "ok")
        self.assertEqual(ra.evaluate_pin(pin, {"delay": 3600})["status"], "changed")

    def test_the_shipped_pins_file_is_well_formed(self):
        import check_scorer_pins as cp
        doc = json.load(open(cp.PINS))
        self.assertEqual([p["id"] for p in doc["pins"]], ["ramses-clv2", "longbow-vaults", "spark-executor"])
        reads = [r for p in doc["pins"] for r in cp.expand(p)]
        self.assertEqual(len(reads), 3 + 3 * 5 + 4)
        self.assertEqual(len({r["name"] for r in reads}), len(reads))

    def test_observe_and_run_with_a_fake_chain(self):
        import check_scorer_pins as cp
        sel = lambda s: "sel:" + s
        word = lambda n: "0x" + "%064x" % n
        state = {}
        def make(url):
            def call(to, data):
                v = state.get((to, data))
                return v
            return call, (lambda to: state.get(("code", to)))
        multisig, timelock = "0x20D630cF1f5628285BfB91DfaC8C89eB9087BE1A", "0xE41c07CcD69A0f19A2186f3Ad30409BD585436CE"
        state[(multisig, "sel:getThreshold()")] = word(1)
        state[(multisig, "sel:getOwners()")] = "0x" + "%064x" % 0x20 + "%064x" % 1 + "%064x" % 5
        state[(timelock, "sel:getMinDelay()")] = word(0)
        doc = {"rpc": {"robinhood": "u"}, "pins": [json.load(open(cp.PINS))["pins"][0]]}
        res = cp.run(doc, make_caller=make, sel=sel)
        self.assertEqual(res[0][0]["status"], "ok")
        state[(multisig, "sel:getThreshold()")] = word(2)
        self.assertEqual(cp.run(doc, make_caller=make, sel=sel)[0][0]["status"], "changed")
        state[(multisig, "sel:getThreshold()")] = None                     # no answer: unread, never unchanged
        self.assertEqual(cp.run(doc, make_caller=make, sel=sel)[0][0]["status"], "unread")

    def test_observe_kinds(self):
        import check_scorer_pins as cp
        sel = lambda s: s
        owner = "0x" + "00" * 12 + "ab" * 20
        calls = {("0xv", "owner()"): owner, (owner[:2] + owner[26:], "getThreshold()"): "0x" + "%064x" % 2}
        call = lambda to, data: calls.get((to, data))
        spec = {"kind": "uint", "to": "0xv", "via": "owner()", "call": "getThreshold()"}
        self.assertEqual(cp.observe(spec, call, lambda t: None, sel), 2)
        self.assertIsNone(cp.observe(dict(spec, via="curator()"), call, lambda t: None, sel))        # the via read got no answer
        self.assertEqual(cp.observe({"kind": "code_len", "to": "0xc"}, call, lambda t: "0x" + "00" * 8113, sel), 8113)
        self.assertIsNone(cp.observe({"kind": "code_len", "to": "0xc"}, call, lambda t: None, sel))
        short_owners = "0x" + "%064x" % 0x20 + "%064x" % 5 + "%064x" % 1          # the answer claims five owners and holds one
        self.assertIsNone(cp.observe({"kind": "owners_len", "to": "0xo", "call": "getOwners()"}, lambda to, d: short_owners, lambda t: None, sel))
        self.assertFalse(cp.observe({"kind": "is_safe", "to": "0xr"}, lambda to, d: "", lambda t: None, sel))     # a revert is an answer
        self.assertIsNone(cp.observe({"kind": "is_safe", "to": "0xr"}, lambda to, d: None, lambda t: None, sel))  # no answer is not

    def test_the_digest_runs_it(self):
        self.assertIn("run(\"check_scorer_pins.py\"", read("daily_digest.py"))


class TestSecondReviewReservesPure(unittest.TestCase):


    def test_a_never_pushed_score_is_not_a_push_of_1970(self):
        f = ra.freshness_record(1790000000, 5, 1789999990, [{"lastUpdated": 0}, {"lastUpdated": 1789000000}, {"lastUpdated": True}])
        self.assertEqual((f["newest_push"], f["oldest_push"]), (1789000000, 1789000000))
        f = ra.freshness_record(1790000000, 5, 1789999990, [{"lastUpdated": 0}])
        self.assertEqual((f["newest_push"], f["oldest_push"]), (None, None))

    def test_a_sweep_date_written_with_capitals_still_matches(self):
        snap = {"swept_utc": "2026-10-21", "valid_days": 30, "targets": {"Robinhood:0xAABB": {"swept_utc": "2026-08-01"}}}
        self.assertEqual(ra.snapshot_for(snap, "robinhood:0xaabb", 1_793_000_000)["from"], "target")

    def test_a_standing_stall_is_said_when_it_starts_and_then_once_a_day_not_at_every_run(self):
        said = []
        for stalled_before in range(1, 10):
            s, out = ra.scan_progress({"block": 100, "self_scanned_to": 90, "scan_stalled_runs": stalled_before}, {"name": "Base", "block": 200, "self_scanned_to": 90})
            said.append((s, bool(out)))
        self.assertEqual([s for s, o in said if o], [2, 6, 10])

    def test_a_future_dated_target_is_said_once_not_at_every_run(self):
        tg = [{"target": "0x" + "ab" * 20, "lastUpdated": 1_000_000}]
        first, _ = ra.last_updated_alerts("Base", tg, {}, 1_000_000 - 4000)
        again, _ = ra.last_updated_alerts("Base", tg, {}, 1_000_000 - 4000 - 21600, already_future=ra.future_dated(tg, 1_000_000 - 4000))
        self.assertEqual((len(first), len(again)), (1, 0))
        self.assertEqual(ra.future_dated(tg, 1_000_000 - 4000), [tg[0]["target"]])
        self.assertEqual(ra.future_dated(tg, None), [])

    def test_a_change_of_method_minutes_after_the_move_of_the_same_pass_marks_that_point(self):
        series = {"base:0xb": [{"t": "2026-10-30T00:17:05Z", "composite": 1, "from": "first"}, {"t": "2026-10-30T00:17:05Z", "composite": 2, "from": "push"}]}
        ra.mark_method_breaks(series, {"base": [{"t": "2026-10-30T00:41:00Z", "from": "0xa", "to": "0xb"}]})
        self.assertEqual([p["method_break"] for p in series["base:0xb"]], [False, True])
        series = {"base:0xb": [{"t": "2026-10-30T00:17:05Z", "composite": 1}, {"t": "2026-10-30T00:17:05Z", "composite": 2}]}
        ra.mark_method_breaks(series, {"base": [{"t": "2026-10-30T09:00:00Z", "from": "0xa", "to": "0xb"}]})      # hours later: another pass
        self.assertEqual([p["method_break"] for p in series["base:0xb"]], [False, False])

    def test_transfer_outcome_is_cleared_only_when_the_getter_that_showed_it_answered(self):
        o = ra.transfer_outcome
        via_c = "pendingOwner() on the contract (Ownable2Step)"
        self.assertEqual(o("0xa", "0xb", None, prev_via=via_c, clean_families={"contract_owner"}), "cleared")
        self.assertEqual(o("0xa", "0xb", None, prev_via=via_c, clean_families=set()), "unread")                       # that read got no answer this run
        self.assertEqual(o("0xa", "0xb", None, prev_via=via_c, clean_families={"proxy_admin"}), "unread")            # another getter answered, not this one
        self.assertEqual(o("0xa", "0xb", None), "unread")                                                             # an old record that does not say which getter
        self.assertEqual(o("0xa", "0xa", None, prev_via=via_c), "accepted")
        self.assertEqual(o("0xa", "0xb", "0xc", prev_via=via_c), "replaced")
        self.assertEqual(ra.pending_family("pendingDefaultAdmin() (AccessControlDefaultAdminRules)"), "default_admin")
        self.assertEqual(ra.pending_family("pendingOwner() on the ProxyAdmin (Ownable2Step)"), "proxy_admin")

    def test_a_transfer_first_seen_through_a_getter_the_lot_began_to_read_is_not_a_change(self):
        via = "pendingDefaultAdmin() (AccessControlDefaultAdminRules)"
        f = ra.first_read_through_new_getter
        self.assertTrue(f({"kind": "eoa"}, "0xabc", via))                                          # the previous record never read that getter
        self.assertFalse(f({"kind": "eoa", "pending_getters": ["default_admin"]}, "0xabc", via))    # it did: a transfer that appears is a change
        self.assertFalse(f({"kind": "eoa"}, "0xabc", "pendingOwner() on the contract (Ownable2Step)"))
        self.assertFalse(f(None, "0xabc", via))
        self.assertFalse(f({"kind": "eoa"}, None, via))

    def test_the_gap_to_the_push_is_measured_from_the_push(self):
        self.assertEqual(ra.since_score_push_seconds(1000, 1500), 500)
        self.assertEqual(ra.since_score_push_seconds(2000, 1500), 0)            # a push dated in the future has no age (F1 is the alarm for it), never a negative one
        self.assertIsNone(ra.since_score_push_seconds(None, 1500))
        self.assertIsNone(ra.since_score_push_seconds(True, 1500))

    def test_a_pinned_read_is_replayed_exactly_and_a_latest_read_is_not(self):
        meta = {"oracle": "0xor", "rpc": "https://rpc", "block": 77, "readAt": 5, "read_tag": "pinned"}
        self.assertTrue(ra.reading_evidence(meta, None, {"target": "0xab"}, "k")["reproduce_exact"])
        self.assertFalse(ra.reading_evidence(dict(meta, read_tag="latest"), None, {"target": "0xab"}, "k")["reproduce_exact"])

    def test_a_response_that_is_not_hexadecimal_is_an_unread_member_not_a_crash(self):
        r = ra.assemble_admin_members("0x" + "11" * 20, 3, ["0x" + "zz" * 32, "0x" + "00" * 12 + "22" * 20])
        self.assertEqual((r["read"], r["unread"]), (2, 1))


class TestPinsOwnersEqual(unittest.TestCase):


    def test_two_safes_with_the_same_count_but_other_owners_are_not_the_same(self):
        import check_scorer_pins as cp
        sel = lambda s: s
        def owners(*a):
            return "0x" + "%064x" % 0x20 + "%064x" % len(a) + "".join("00" * 12 + x * 20 for x in a)
        calls = {("0xv", "owner()"): "0x" + "00" * 12 + "a1" * 20, ("0xv", "curator()"): "0x" + "00" * 12 + "a2" * 20,
                 ("0x" + "a1" * 20, "getOwners()"): owners("01", "02", "03"), ("0x" + "a2" * 20, "getOwners()"): owners("03", "02", "01")}
        spec = {"kind": "owners_equal", "to": "0xv", "vias": ["owner()", "curator()"], "call": "getOwners()"}
        self.assertTrue(cp.observe(spec, lambda to, d: calls.get((to, d)), lambda t: None, sel))
        calls[("0x" + "a2" * 20, "getOwners()")] = owners("03", "02", "09")
        self.assertFalse(cp.observe(spec, lambda to, d: calls.get((to, d)), lambda t: None, sel))
        calls[("0x" + "a2" * 20, "getOwners()")] = None
        self.assertIsNone(cp.observe(spec, lambda to, d: calls.get((to, d)), lambda t: None, sel))      # no answer is unread


class TestExpiredAndExclusions(unittest.TestCase):


    def test_a_compound_operation_still_queued_past_eta_plus_grace_is_told_expired(self):
        try:
            import importlib
            from lib import abi_returndata_guard, pending_ops
            abi_returndata_guard.uninstall()      # other suites install the ABI guard and leave modules holding its wrapper (the same cause as test_pending_ops failing when run after them): start from the real decoder
            importlib.reload(pending_ops)
            import check_pending_ops as cpo
            importlib.reload(cpo)
            from eth_abi import encode
            from web3 import Web3
        except ImportError:
            self.skipTest("web3 / eth_abi absent")
        head, now = 25_000_000, int(time.time())
        eta = now - 3 * 86400                                           # became executable 3 days ago; the grace is 2 days: expired, and still published (< 7 days)
        block = head - int(3.5 * 86400 / 12)
        data = encode(["uint256", "string", "bytes", "uint256"], [0, "setX(uint256)", b"\x00" * 32, eta])
        log = {"topics": [cpo.QUEUE_TOPICS["compound"], "0x" + "%064x" % 7, "0x" + "00" * 12 + "dd" * 20], "data": "0x" + data.hex(), "blockNumber": block, "transactionHash": "0x" + "%064x" % 7}
        sel = lambda sig: Web3.keccak(text=sig)[:4].hex()
        answers = {sel("delay()"): lambda a: (172800).to_bytes(32, "big"), sel("GRACE_PERIOD()"): lambda a: (2 * 86400).to_bytes(32, "big"), sel("queuedTransactions(bytes32)"): lambda a: (1).to_bytes(32, "big")}
        class Eth:
            block_number = head
            def get_logs(self, flt): return [log] if flt["topics"][0] == log["topics"][0] else []
            def get_block(self, n): return {"timestamp": now - (head - n) * 12}
            def call(self, tx):
                fn = answers.get(bytes(tx["data"])[:4].hex())
                if fn is None: raise RuntimeError("no answer")
                return fn(bytes(tx["data"])[4:])
        class W3:
            eth = Eth()
        orig = cpo.get_w3
        cpo.get_w3 = lambda url: W3()
        try:
            out = cpo.check_timelock("Fake", "ethereum", "0x" + "ee" * 20, "compound", 30)
        finally:
            cpo.get_w3 = orig
        self.assertEqual(out["status"], "ok", out.get("status"))
        self.assertEqual([p_["state"] for p_ in out["pending"]], ["expired"])
        self.assertEqual([r_["final_state"] for r_ in out["recent"]], ["expired"])

    def test_an_operation_in_both_lists_is_excluded_once(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "scores"))
            addr = "0x" + "11" * 20
            json.dump({"kind": "evm", "targets": [{"target": addr, "compositeScore": 40, "lastUpdated": 1790000000}]}, open(os.path.join(d, "scores", "robinhood-chain.json"), "w"))
            open(os.path.join(d, "events.jsonl"), "w").write("")
            op = {"id": "0x01", "target": addr, "queued_at": int(time.time()) - 86400, "undecoded": True}
            json.dump({"results": [{"chain": "robinhood", "address": "0xTL", "name": "T", "status": "ok", "pending": [op], "recent": [op, dict(op, id="0x02")]}]}, open(os.path.join(d, "pending.json"), "w"))
            r = subprocess.run([sys.executable, "-B", "-E", os.path.join(SCRIPTS, "score_series.py"), "--scores", os.path.join(d, "scores"), "--events", os.path.join(d, "events.jsonl"),
                                "--pending", os.path.join(d, "pending.json"), "--out", os.path.join(d, "out.json")], capture_output=True, text=True, cwd=SCRIPTS)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(json.load(open(os.path.join(d, "out.json")))["calibration"]["excluded_undecoded"], 2)      # ids 0x01 (in both lists) and 0x02: two operations, not three


if __name__ == "__main__":
    unittest.main()
