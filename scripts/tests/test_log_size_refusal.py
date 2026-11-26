"""Tests of the log scan of the oracle's own role events when a node refuses a block range with the code -32005. Fake node, no network, no waiting.
Run:  python3 -B test_log_size_refusal.py [path/to/watch_run.py]   (default: ../watch_run.py)
Case behind it: from 17 to 26 November 2026 the role scan of the HyperEVM testnet oracle did not move for 9 runs (785 537 blocks unread). The node that serves the read
(998.rpc.thirdweb.com) answers a range above 1000 blocks with the code -32005 and the words "Log response size exceeded. Maximum allowed number of requested blocks is 1000".
-32005 is also the code of "rate limited", so the call was read as a rate limit: the node was dropped for the whole scan and the narrower spans (1000, 200, 100) were never tried.
Then mutants of the new code: each must make at least one test fail."""
import importlib.util, json, os, sys, types, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PATH = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("-") else os.path.join(HERE, "..", "watch_run.py")
sys.path.insert(0, os.path.join(HERE, ".."))
TEXT = [None]   # the source under test (a mutant replaces it)
NODE = "https://998.rpc.thirdweb.com"
ORACLE = "0x" + "ab" * 20
SIZE = {"code": -32005, "message": "Log response size exceeded. Maximum allowed number of requested blocks is 1000"}
RATE = {"code": -32005, "message": "rate limited"}


def load():
    src = TEXT[0] if TEXT[0] is not None else open(PATH, encoding="utf-8").read()
    mod = types.ModuleType("watch_run_under_test"); mod.__file__ = PATH; exec(compile(src, PATH, "exec"), mod.__dict__); return mod


class FakeNode:
    """urlopen of a node that answers eth_getLogs for at most `limit` blocks (error `refusal` above it), or always `always` when given."""
    def __init__(s, limit=1000, refusal=SIZE, always=None): s.limit, s.refusal, s.always, s.asked = limit, refusal, always, []
    def urlopen(s, req, timeout=0):
        body = json.loads(req.data.decode()); batch = body if isinstance(body, list) else [body]; out = []
        for c in batch:
            if c["method"] != "eth_getLogs": out.append({"jsonrpc": "2.0", "id": c["id"], "result": "0x6001" if c["method"] == "eth_getCode" else "0x" + "00" * 31 + "01"}); continue
            a, b = int(c["params"][0]["fromBlock"], 16), int(c["params"][0]["toBlock"], 16); s.asked.append((a, b))
            err = s.always if s.always else (s.refusal if b - a + 1 > s.limit else None)
            out.append({"jsonrpc": "2.0", "id": c["id"], **({"error": err} if err else {"result": []})})
        data = json.dumps(out if isinstance(body, list) else out[0]).encode()
        class R:
            def read(self): return data
            def __enter__(self): return self
            def __exit__(self, *a): return False
        return R()


class LogSizeRefusal(unittest.TestCase):
    def setUp(self):
        self.w = load(); self.sleeps = []
        self.saved = (self.w.time.sleep, self.w.urllib.request.urlopen); self.w.time.sleep = lambda s: self.sleeps.append(s)
        self.w._single_only.clear(); self.w._rate_spent.clear(); self.w._rate_seen.clear(); self.w._rate_cap.clear()
    def tearDown(self): self.w.time.sleep, self.w.urllib.request.urlopen = self.saved

    def scan(self, node, since=0, block=3500):
        self.w.urllib.request.urlopen = node.urlopen
        return self.w.scan_logs(ORACLE, [NODE], since, block)

    def test_a_size_refusal_coded_32005_is_not_a_rate_limit(self):
        self.assertFalse(self.w._rate_limited({"error": SIZE}))
        self.assertFalse(self.w._rate_limited({"error": {"code": -32005, "message": "Log response size exceeded. Maximum allowed number of requested blocks"}}))   # as cut by the Watch at 100 characters
        self.assertTrue(self.w._rate_limited({"error": RATE})); self.assertTrue(self.w._rate_limited({"error": {"code": -32005, "message": "request rate limit exceeded"}}))
        self.assertTrue(self.w._rate_limited({"error": {"code": -32005, "message": "Too many requests, rate limited"}}))
        for msg in ("rate_limited: log response size exceeded", "Too many request: log range too large", "throttled: maximum allowed number of requested blocks is 1000", "Rate-Limit reached, block range exceeds max"):
            self.assertTrue(self.w._rate_limited({"error": {"code": -32005, "message": msg}}), msg)   # a word of pace and a word of size: a limit, as before the change
        self.assertTrue(self.w._rate_limited({"error": {"code": -32005, "message": "project ID request rate exceeded"}}))   # limits worded with "exceeded", no word of size
        self.assertTrue(self.w._rate_limited({"error": {"code": -32005, "message": "limit exceeded"}}))
        self.assertTrue(self.w._rate_limited({"error": {"code": -32005, "message": "rate limited: log response size exceeded"}}))   # a message that says both is a limit: it is waited out, as before

    def test_the_scan_moves_on_to_a_narrower_span_instead_of_dropping_the_node(self):
        node = FakeNode(limit=1000); found, upto, last = self.scan(node)
        self.assertEqual((found, upto), ([], 3500)); self.assertNotIsInstance(last, self.w.RateLimited)   # every block read, no rate limit raised
        asked = node.asked; self.assertEqual(asked[0], (1, 3500))   # the widest span is asked first, once, and refused
        self.assertTrue(any(b - a + 1 == 1000 for a, b in asked))
        ok = [x for x in asked if x[1] - x[0] + 1 <= 1000]   # the calls the node answered
        self.assertEqual(ok[0][0], 1); self.assertTrue(all(ok[i][1] + 1 == ok[i + 1][0] for i in range(len(ok) - 1))); self.assertEqual(ok[-1][1], 3500)   # no hole, no overlap

    def test_a_size_refusal_does_not_spend_the_rate_limit_pauses(self):
        self.scan(FakeNode(limit=1000), 0, 6500)
        self.assertFalse(set(self.sleeps) & set(self.w.RATE_WAITS)); self.assertLess(sum(self.sleeps), 10)   # a wide first call is refused once; no pause of a rate limit is spent on a limit that is not one

    def test_a_node_that_takes_only_100_blocks_is_still_read_to_the_end(self):
        node = FakeNode(limit=100); found, upto, last = self.scan(node, 0, 450)
        self.assertEqual(upto, 450); self.assertTrue(all(b - a + 1 <= 100 for a, b in node.asked[-5:]))

    def test_a_real_rate_limit_still_drops_the_node_and_the_window_is_unread(self):
        node = FakeNode(always=RATE); found, upto, last = self.scan(node, 100, 3500)
        self.assertEqual((found, upto), ([], 100)); self.assertIsInstance(last, self.w.RateLimited)   # nothing read: the marker stays, the next run starts again
        self.assertEqual(len(set(node.asked)), 1)   # the node is left: the same first range only (waited out), no narrower span is tried on a limited node

    def test_self_watch_reads_the_window_across_runs_and_never_calls_a_refused_range_read(self):
        self.w.urllib.request.urlopen = FakeNode(limit=1000).urlopen
        # the part of the case: a window far beyond one span and beyond the call cap is read in part, the marker moves, the rest is the next run's
        big = self.w.LOG_CALL_CAP * 1000 + 777; w = self.w.self_watch(ORACLE, NODE, 0, big)
        self.assertFalse(w["read"]); self.assertEqual(w["scanned_upto"], self.w.LOG_CALL_CAP * 1000)   # 120 answered calls of 1000 blocks
        self.assertIn("blocks left after", w["error"]); self.assertNotIn("size exceeded", w["error"])   # the cap is the reason it is unread, not the wide span that was refused first
        self.assertGreater(w["scanned_upto"], 0); self.assertEqual(w["unread_blocks"], big - w["scanned_upto"]); self.assertEqual(w["role_events"], [])
        self.assertEqual(self.w.scanned_to(w, 0, big), w["scanned_upto"])   # the marker follows what was read: a run later the same window is shorter

    def test_the_unread_window_is_never_counted_as_read_or_as_no_event(self):
        self.w.urllib.request.urlopen = FakeNode(always=RATE).urlopen
        w = self.w.self_watch(ORACLE, NODE, 100, 3500); self.assertFalse(w["read"]); self.assertEqual(w["unread_blocks"], 3400); self.assertIn("getLogs", w["error"])
        self.assertEqual(self.w.scanned_to(w, 100, 3500), 100)


def mutants(src):
    """(name, source) pairs: each breaks one rule of the change."""
    out = []
    def mut(name, old, new, count=1):
        if src.count(old) < 1: raise SystemExit("mutant %s: text not found: %r" % (name, old[:60]))
        out.append((name, src.replace(old, new, count)))
    mut("M1 a size refusal is a rate limit again", "if _size_refused(e): return False", "if False: return False")
    mut("M2 any -32005 is a size refusal", "return e.get(\"code\") == -32005 or \"rate\" in str(e.get(\"message\", \"\")).lower()", "return False")
    mut("M3 the size words are not looked for", "return bool(SIZE_REFUSED.search(msg)) and", "return bool(SIZE_REFUSED.search('x')) and")
    mut("M4 a real limit that says exceeded counts as size", "and not RATE_WORDS.search(msg)", "")
    mut("M8 the underscore is no longer a separator of rate limit", "rate[-_ ]?limit", "rate[- ]?limit")
    mut("M9 throttled is no longer a word of pace", "|throttl|", "|")
    mut("M7 every message is a size refusal", "return bool(SIZE_REFUSED.search(msg)) and not RATE_WORDS.search(msg)", "return True")
    mut("M6 an answer no longer clears the refused-span error", "pos, answered, done, last = b + 1, answered + 1, True, None", "pos, answered, done = b + 1, answered + 1, True")
    mut("M5 a rate limit no longer drops the node", "if isinstance(e, RateLimited) or not RANGE_REFUSED.search(str(e)): dead.add(u)", "if not RANGE_REFUSED.search(str(e)): dead.add(u)")
    return out


class MutantsAreCaught(unittest.TestCase):
    def test_every_mutant_makes_at_least_one_test_fail(self):
        base = open(PATH, encoding="utf-8").read(); survivors = []
        for name, src in mutants(base):
            TEXT[0] = src
            try:
                res = unittest.TextTestRunner(stream=open(os.devnull, "w"), verbosity=0).run(unittest.defaultTestLoader.loadTestsFromTestCase(LogSizeRefusal))
                if res.wasSuccessful(): survivors.append(name)
            except Exception: pass   # a mutant that does not even load is caught
            finally: TEXT[0] = None
        self.assertEqual(survivors, [], "mutants not caught: %s" % survivors)


if __name__ == "__main__":
    sys.argv = [a for a in sys.argv if a == sys.argv[0] or a.startswith("-")]
    unittest.main(verbosity=1)
