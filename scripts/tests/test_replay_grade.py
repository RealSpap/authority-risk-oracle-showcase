"""scripts/replay_grade.py: the Replay Grade registry made executable. No network: the reader is replaced by a function.
Each case is a way the script could say OK without having read, or turn a failed read into a zero."""
import json, os, sys, unittest, warnings

warnings.simplefilter("ignore", ResourceWarning)
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
import replay_grade as rg  # noqa: E402

ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
OUT_OF_WINDOW = "2026-11-14T07:00:00Z"
IN_WINDOW = "2026-11-14T12:20:00Z"


def ctx(fetch=None, now=OUT_OF_WINDOW, offline=False, clock=None):
    """now = the stamp ; clock = the real clock that judges the Watch window (the same as the stamp unless given)"""
    return rg.Context(repo=ROOT, fetch=fetch or (lambda url, limit=None: (_ for _ in ()).throw(AssertionError("no network expected"))), now=rg.parse_now(now), offline=offline, clock=clock or (lambda: rg.parse_now(now)))


def served(doc, clock=None):
    body = doc if isinstance(doc, bytes) else json.dumps(doc).encode()
    return ctx(fetch=lambda url, limit=None: body, clock=clock)


class T(unittest.TestCase):
    def test_grades_follow_the_four_elements(self):
        g = rg.grade
        self.assertEqual(g(dict(cmd=1, pt=1, ex=1, net=1, src=1)), "A")
        self.assertEqual(g(dict(cmd=1, pt=1, ex=1, net=None, src=0)), "A", "a claim about no chain: the network element is not applicable")
        self.assertEqual(g(dict(cmd=1, pt=1, ex=1, net=0, src=1)), "B", "a chain read with no chain id written is not an A")
        self.assertEqual(g(dict(cmd=0, pt=1, ex=0, net=0, src=0)), "C", "a named point with no command is a C (Q307 P1-2)")
        self.assertEqual(g(dict(cmd=1, pt=0, ex=0, net=0, src=0)), "B")
        self.assertEqual(g(dict(cmd=0, pt=0, ex=0, net=0, src=1)), "C")
        self.assertEqual(g(dict(cmd=0, pt=0, ex=0, net=0, src=0)), "D")

    def test_the_registry_gives_the_published_counts(self):
        reg = rg.load_registry(os.path.join(ROOT, "scripts", "replay_grade_claims.json"))
        ids = [c["id"] for c in reg]; self.assertEqual(len(ids), len(set(ids)), "an id is used twice")
        count = lambda pred: {k: sum(1 for c in reg if pred(c) and rg.grade(c["elements"]) == k) for k in "ABCD"}
        self.assertEqual(count(lambda c: c["page"] == "README.md"), {"A": 1, "B": 15, "C": 18, "D": 13})
        self.assertEqual(count(lambda c: c["page"] != "README.md"), {"A": 1, "B": 11, "C": 20, "D": 42})

    def test_keccak_has_its_known_answers(self):
        self.assertEqual(rg.keccak256(b"").hex(), "c5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470")
        self.assertEqual(rg.selector("transfer(address,uint256)"), "0xa9059cbb")
        self.assertEqual(rg.selector("getScore(address)"), "0xd47875d0")

    def test_a_planted_false_value_is_a_difference(self):
        good = {"kind": "selectors", "items": [["owner()", "0x8da5cb5b"]]}
        bad = {"kind": "selectors", "items": [["owner()", "0x8da5cb5c"]]}
        self.assertEqual(rg.run_check(good, ctx())[0], "OK")
        v, why = rg.run_check(bad, ctx()); self.assertEqual(v, "DIFFERENCE"); self.assertIn("0x8da5cb5b", why)

    def test_a_failed_read_is_unread_never_ok_never_a_zero(self):
        def down(url, limit=None): raise OSError("refused")
        chk = {"kind": "json", "url": "https://realspap.github.io/oracle/p/index.json", "path": "count", "op": "eq", "expected": 202}
        v, why = rg.run_check(chk, ctx(fetch=down)); self.assertEqual(v, "UNREAD"); self.assertIn("refused", why)
        v, _ = rg.run_check(chk, ctx(fetch=lambda u, limit=None: b"not json")); self.assertEqual(v, "UNREAD", "an unreadable answer is not a value")
        v, _ = rg.run_check(chk, ctx(fetch=lambda u, limit=None: json.dumps({"other": 202}).encode())); self.assertEqual(v, "UNREAD", "a missing field is not a zero")
        v, _ = rg.run_check(chk, ctx(fetch=lambda u, limit=None: json.dumps({"count": 0}).encode())); self.assertEqual(v, "DIFFERENCE", "a zero that was read is a difference, not unread")

    def test_json_checks_compare_what_was_read(self):
        ok = lambda body: ctx(fetch=lambda u, limit=None: json.dumps(body).encode())
        c1 = {"kind": "json", "url": "https://realspap.github.io/oracle/p/index.json", "path": "count", "op": "eq", "expected": 202}
        self.assertEqual(rg.run_check(c1, ok({"count": 202}))[0], "OK"); self.assertEqual(rg.run_check(c1, ok({"count": 203}))[0], "DIFFERENCE")
        c2 = {"kind": "json", "url": "https://raw.githubusercontent.com/x/y/watch-data/alerts.json", "path": "active", "op": "len_eq", "expected": 8}
        self.assertEqual(rg.run_check(c2, ok({"active": [1] * 8}))[0], "OK"); self.assertEqual(rg.run_check(c2, ok({"active": [1] * 5}))[0], "DIFFERENCE")
        c3 = {"kind": "group_count", "url": "https://raw.githubusercontent.com/x/y/watch-data/second_opinion.json", "list_path": "results", "by": "kind", "expected": {"safe": 2, "eoa": 1}}
        self.assertEqual(rg.run_check(c3, ok({"results": [{"kind": "safe"}, {"kind": "safe"}, {"kind": "eoa"}]}))[0], "OK")
        self.assertEqual(rg.run_check(c3, ok({"results": [{"kind": "safe"}, {"kind": "eoa"}, {"kind": "eoa"}]}))[0], "DIFFERENCE")

    def test_the_watch_window_and_the_offline_flag_forbid_every_network_read(self):
        chk = {"kind": "json", "url": "https://realspap.github.io/oracle/p/index.json", "path": "count", "op": "eq", "expected": 202}
        v, why = rg.run_check(chk, ctx(now=IN_WINDOW)); self.assertEqual((v, "window" in why), ("UNREAD", True))
        v, why = rg.run_check(chk, ctx(offline=True)); self.assertEqual((v, "offline" in why), ("UNREAD", True))
        for hh, ok in (("2026-11-14T06:09:59Z", False), ("2026-11-14T06:10:00Z", True), ("2026-11-14T06:55:59Z", True), ("2026-11-14T06:56:00Z", False), ("2026-11-14T07:30:00Z", False), ("2026-11-14T00:30:00Z", True), ("2026-11-14T18:55:00Z", True), ("2026-11-14T18:56:00Z", False)):
            self.assertEqual(rg.in_watch_window(rg.parse_now(hh)), ok, hh)

    def test_the_stamp_cannot_hide_the_real_clock_and_the_offset_is_converted(self):
        chk = {"kind": "json", "url": "https://realspap.github.io/oracle/p/index.json", "path": "count", "op": "eq", "expected": 202}
        v, why = rg.run_check(chk, ctx(fetch=lambda u, limit=None: b'{"count": 202}', now=OUT_OF_WINDOW, clock=lambda: rg.parse_now(IN_WINDOW)))
        self.assertEqual((v, "window" in why), ("UNREAD", True), "--now 07:00 with a real clock at 12:20 sends no request")
        self.assertTrue(rg.in_watch_window(rg.parse_now("2026-11-14T08:20:00+02:00")), "08:20+02:00 is 06:20Z")
        self.assertFalse(rg.in_watch_window(rg.parse_now("2026-11-14T08:05:00+02:00")), "08:05+02:00 is 06:05Z, before the window")
        self.assertEqual(rg.parse_now("2026-11-14T08:20:00+02:00").hour, 6)

    def test_the_window_is_judged_before_every_request_not_once(self):
        chk = {"kind": "json", "url": "https://realspap.github.io/oracle/p/index.json", "path": "count", "op": "eq", "expected": 202}
        ticks = iter(["2026-11-14T06:09:50Z", "2026-11-14T06:10:05Z"]); n = []
        def fetch(u, limit=None): n.append(u); return b'{"count": 202}'
        c = ctx(fetch=fetch, clock=lambda: rg.parse_now(next(ticks)))
        v, _ = rg.run_check({"kind": "all", "checks": [chk, chk]}, c)
        self.assertEqual((v, len(n)), ("UNREAD", 1), "the second request is not sent")

    def test_a_failed_read_of_the_watch_files_is_unread_not_a_value(self):
        self.assertEqual(rg.run_check(rg.CHECKS["W04"], served({"active": [], "errors": ["rpc refused"]}))[0], "UNREAD", "errors filled: not 'read 0'")
        self.assertEqual(rg.run_check(rg.CHECKS["P05"], served(b'{"run_utc": "2026-10-10T21:01:36Z"}\n'))[0], "UNREAD", "no seq: not 'seq is None'")
        self.assertEqual(rg.run_check(rg.CHECKS["V11"], served({"results": []}))[0], "UNREAD", "an empty list is not zero counts")
        self.assertEqual(rg.run_check(rg.CHECKS["W04"], served({"active": [1] * 5}))[0], "DIFFERENCE", "a real zero or a real 5 is read")

    def test_a_dated_claim_whose_value_moved_is_stale_a_present_claim_is_a_difference(self):
        self.assertEqual(rg.run_check(rg.CHECKS["H05"], served({"active": [1] * 8}))[0], "OK")
        v, why = rg.run_check(rg.CHECKS["H05"], served({"active": [1] * 5})); self.assertEqual(v, "UNREAD"); self.assertIn("stale", why); self.assertIn("5", why)
        self.assertEqual(rg.run_check(rg.CHECKS["W04"], served({"active": [1] * 5}))[0], "DIFFERENCE")

    def test_a_two_part_claim_is_ok_only_when_both_parts_hold(self):
        mk = lambda n_chains: {"count": 202, "addresses": {"a": [{"key": "k%d" % i} for i in range(n_chains)]}}
        self.assertEqual(rg.run_check(rg.CHECKS["H01"], served(mk(9)))[0], "OK")
        v, why = rg.run_check(rg.CHECKS["H01"], served(mk(8))); self.assertEqual(v, "DIFFERENCE"); self.assertIn("8", why)
        self.assertEqual(rg.run_check(rg.CHECKS["H01"], served({"count": 203, "addresses": mk(9)["addresses"]}))[0], "DIFFERENCE")

    def test_the_home_page_links_are_counted_exactly_without_the_script_template(self):
        cards = "".join('<a href="p/robinhood-0x%040x.html">c</a>' % i for i in range(15)); js = "<script>var u = 'p/' + esc(r.key) + '.html'; a = '<a href=\"p/' + esc(r.key) + '-' + esc(addrKey(r)) + '.html\">'</script>"
        self.assertEqual(rg.run_check(rg.CHECKS["H04"], served((cards + js).encode()))[0], "OK", "15 cards and one template: OK")
        self.assertEqual(rg.run_check(rg.CHECKS["H04"], served((cards + '<a href="p/solana-abc.html">x</a>').encode()))[0], "DIFFERENCE", "a sixteenth card is a difference, not 'at least 15'")

    def test_only_the_two_public_hosts_are_opened(self):
        chk = {"kind": "json", "url": "https://example.org/x.json", "path": "a", "op": "eq", "expected": 1}
        v, why = rg.run_check(chk, ctx()); self.assertEqual(v, "UNREAD"); self.assertIn("host", why)

    def test_the_line_counts_of_the_readme_are_read_in_the_repository(self):
        chk = {"kind": "lines", "items": [["integrations/authority_facts_gate_strict.py", 49], ["integrations/authority_facts_gate.py", 18]]}
        self.assertEqual(rg.run_check(chk, ctx())[0], "OK")
        chk["items"][0][1] = 50; v, why = rg.run_check(chk, ctx()); self.assertEqual(v, "DIFFERENCE"); self.assertIn("49", why)
        chk["items"] = [["integrations/does_not_exist.py", 1]]; self.assertEqual(rg.run_check(chk, ctx())[0], "UNREAD", "a missing file is unread, not zero lines")

    def test_a_claim_with_no_command_is_unread_with_its_cause_and_keeps_its_grade(self):
        rows = rg.evaluate([{"id": "X1", "page": "p", "where": "w", "claim": "c", "command": "none", "elements": dict(cmd=0, pt=0, ex=0, net=None, src=0)}], {}, ctx())
        self.assertEqual((rows[0]["grade"], rows[0]["verdict"]), ("D", "UNREAD")); self.assertIn("nothing to replay", rows[0]["why"])

    def test_the_summary_never_counts_unread_as_ok_and_the_exit_code_follows(self):
        rows = [dict(id="a", grade="A", verdict="OK", why=""), dict(id="b", grade="D", verdict="UNREAD", why="x"), dict(id="c", grade="B", verdict="DIFFERENCE", why="y")]
        s = rg.summary(rows); self.assertEqual((s["OK"], s["UNREAD"], s["DIFFERENCE"]), (1, 1, 1))
        self.assertEqual(rg.exit_code(rows), 1)
        self.assertEqual(rg.exit_code(rows[:2]), 0, "unread alone does not fail the run")
        self.assertEqual(rg.exit_code(rows[:2], strict=True), 3, "strict: an unread read is not a pass")
        self.assertEqual(rg.exit_code([]), 3, "nothing read at all is not a pass")

    def test_the_selftest_plants_a_false_value_and_passes(self):
        self.assertEqual(rg.selftest(), 0)

    def test_a_check_whose_claim_is_not_in_the_registry_is_an_error(self):
        with self.assertRaises(KeyError): rg.evaluate([{"id": "X1", "page": "p", "where": "w", "claim": "c", "command": "none", "elements": dict(cmd=0, pt=0, ex=0, net=None, src=0)}], {"NOPE": {"kind": "lines", "items": []}}, ctx())

    def test_the_script_is_in_none_of_the_nine_methodology_hashes(self):
        sys.path.insert(0, os.path.join(ROOT, "scripts", "lib"))
        from lib import methodology
        seen = 0
        for eco in methodology.ENTRY:
            files = methodology.scoring_files(eco, root=ROOT); seen += 1
            self.assertNotIn("scripts/replay_grade.py", files, eco); self.assertNotIn("scripts/replay_grade_claims.json", files, eco)
        self.assertEqual(seen, 9)

    def test_the_default_checks_are_all_attached_to_claims_of_the_registry(self):
        reg = {c["id"] for c in rg.load_registry(os.path.join(ROOT, "scripts", "replay_grade_claims.json"))}
        self.assertTrue(set(rg.CHECKS) <= reg, sorted(set(rg.CHECKS) - reg))


if __name__ == "__main__":
    unittest.main()
