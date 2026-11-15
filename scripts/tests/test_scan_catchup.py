"""The scan of the oracle's own role events (watch_run.self_watch): it used to give up a window it could not read (Base Sepolia 98856 blocks, Monad 63609, 15 November) and jump the marker over it, so a RoleGranted inside
was never looked at. It now cuts the window into slices, hands a slice to the next node of the list when a node refuses it, and keeps what it read: a window that does not fit in one run is caught up over the next runs.
No network: the nodes are fakes that refuse a range wider than their own limit, like the public ones do."""
import contextlib, json, os, sys, unittest
import warnings

warnings.simplefilter("ignore", ResourceWarning)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import watch_run  # noqa: E402
from lib.reader_audit import scan_progress  # noqa: E402

ORACLE = "0x" + "ab" * 20
ACCT = "0x" + "00" * 12 + "cd" * 20


class Nodes:
    """Fake JSON-RPC nodes: `limits` url -> widest eth_getLogs range it answers; a url in `dead` raises on every call; `die_after` url -> number of getLogs it answers before it dies. Records every getLogs asked."""
    def __init__(self, limits, logs=(), dead=(), die_after=None, text="block range too large"):
        self.limits, self.logs, self.dead, self.die_after, self.text = limits, list(logs), set(dead), dict(die_after or {}), text
        self.asked = []      # (url, from, to, answered)
        self.answered = {}   # url -> answered getLogs

    def rpc(self, url, calls, tries=3):
        out = []
        for m, p in calls:
            if m == "eth_getCode": out.append("0x6001")
            elif m == "eth_call": out.append(hex(1 if p[0]["data"][10:74] == "0" * 64 else 0))
            elif m == "eth_getLogs":
                a, b = int(p[0]["fromBlock"], 16), int(p[0]["toBlock"], 16)
                if url in self.dead: self.asked.append((url, a, b, False)); raise RuntimeError("HTTP 500: boom")
                if url in self.die_after and self.answered.get(url, 0) >= self.die_after[url]: self.asked.append((url, a, b, False)); raise RuntimeError("HTTP 500: boom")
                if b - a + 1 > self.limits.get(url, 10 ** 9): self.asked.append((url, a, b, False)); raise RuntimeError(self.text)
                self.asked.append((url, a, b, True)); self.answered[url] = self.answered.get(url, 0) + 1
                out.append([l for l in self.logs if a <= int(l["blockNumber"], 16) <= b])
            else: raise AssertionError(m)
        return out

    def ok(self): return [(u, a, b) for u, a, b, k in self.asked if k]


def grant(block, tx="0xaa"): return {"topics": [watch_run.TOPIC_GRANTED, list(watch_run.ROLE_NAMES)[1], ACCT, "0x" + "00" * 12 + "ef" * 20], "blockNumber": hex(block), "transactionHash": tx}


class Base(unittest.TestCase):
    def setUp(self):
        self.saved = (watch_run.rpc, watch_run.time.sleep, dict(watch_run.LOG_NODES), watch_run.LOG_CALL_CAP); watch_run.time.sleep = lambda s: None
    def tearDown(self):
        watch_run.rpc, watch_run.time.sleep, watch_run.LOG_CALL_CAP = self.saved[0], self.saved[1], self.saved[3]; watch_run.LOG_NODES.clear(); watch_run.LOG_NODES.update(self.saved[2])

    def scan(self, nodes, url, since, block):
        watch_run.rpc = nodes.rpc; return watch_run.self_watch(ORACLE, url, since, block)

    def contiguous(self, calls, since, block):
        """every block from since+1 to block asked exactly once, in order: no hole, no overlap"""
        self.assertEqual(calls[0][1], since + 1); self.assertEqual(calls[-1][2], block)
        for x, y in zip(calls, calls[1:]): self.assertEqual(x[2] + 1, y[1])


class TestSliceAndHandOver(Base):
    def test_a_window_the_first_node_refuses_is_read_on_the_next_node_of_the_list(self):
        # the first node answers 100 blocks at most, the second 50000: the 98856 blocks of Base Sepolia on 15 November no longer need 989 calls on the narrow one
        watch_run.LOG_NODES["narrow"] = ["narrow", "wide"]
        n = Nodes({"narrow": 100, "wide": 50000}, logs=[grant(150000)]); w = self.scan(n, "narrow", 100000, 198856)
        self.assertTrue(w["read"], w.get("error")); self.assertNotIn("gap_blocks", w); self.assertEqual(w["scanned_upto"], 198856); self.assertEqual(w.get("unread_blocks", 0), 0)
        self.assertEqual([e["block"] for e in w["role_events"]], [150000])                      # the event inside the window is seen
        self.assertLessEqual(len(n.ok()), 20); self.assertTrue(all(u == "wide" for u, a, b in n.ok())); self.contiguous(n.ok(), 100000, 198856)

    def test_the_span_that_worked_is_remembered_a_refusal_is_not_asked_again_at_every_slice(self):
        watch_run.LOG_NODES["m"] = ["m"]
        n = Nodes({"m": 1000}); w = self.scan(n, "m", 0, 30000)
        self.assertTrue(w["read"]); failed = [(a, b) for u, a, b, k in n.asked if not k]
        self.assertLessEqual(len(failed), len(watch_run.LOG_SPANS)); self.assertEqual(len(n.ok()), 30); self.contiguous(n.ok(), 0, 30000)

    def test_a_node_that_dies_midway_hands_the_rest_to_the_next_without_losing_or_repeating_a_block(self):
        watch_run.LOG_NODES["a"] = ["a", "b"]
        n = Nodes({"a": 1000, "b": 1000}, logs=[grant(1500), grant(9500, "0xbb")], die_after={"a": 3}); w = self.scan(n, "a", 0, 12000)
        self.assertTrue(w["read"], w.get("error")); self.contiguous(n.ok(), 0, 12000)
        self.assertEqual([e["block"] for e in w["role_events"]], [1500, 9500]); self.assertEqual({u for u, a, b in n.ok()}, {"a", "b"})

    def test_every_node_dead_keeps_the_marker_and_says_the_window_was_not_read(self):
        watch_run.LOG_NODES["a"] = ["a", "b"]
        n = Nodes({}, dead={"a", "b"}); w = self.scan(n, "a", 1000, 5000)
        self.assertFalse(w["read"]); self.assertEqual(w["role_events"], []); self.assertEqual(w["scanned_upto"], 1000); self.assertEqual(w["unread_blocks"], 4000); self.assertIn("getLogs:", w["error"])
        self.assertEqual(watch_run.scanned_to(w, 1000, 5000), 1000)                              # the next run starts again from the same block: an unread window is never "no event"
        self.assertLessEqual(len(n.asked), 2 * len(watch_run.LOG_SPANS))                         # and a dead node is not hammered at every span and slice

    def test_a_node_that_fails_for_another_reason_than_the_size_is_left_for_the_rest_of_the_scan(self):
        watch_run.LOG_NODES["a"] = ["a", "b"]
        n = Nodes({"b": 1000}, dead={"a"}); w = self.scan(n, "a", 0, 8000)          # b refuses 5000 and takes 1000: the span goes down, the dead node must not be asked again at each span
        self.assertTrue(w["read"], w.get("error")); self.assertEqual([x for x in n.asked if x[0] == "a"], [("a", 1, 5000, False)]); self.contiguous(n.ok(), 0, 8000)

    def test_a_node_that_is_not_in_the_list_is_the_only_one(self):
        n = Nodes({"u": 10 ** 6}); w = self.scan(n, "u", 0, 700); self.assertTrue(w["read"]); self.assertEqual({u for u, a, b in n.ok()}, {"u"})


class TestCatchUp(Base):
    def test_a_window_that_does_not_fit_in_one_run_is_caught_up_over_the_next_runs_never_given_up(self):
        watch_run.LOG_NODES["m"] = ["m"]; watch_run.LOG_CALL_CAP = 5
        n = Nodes({"m": 100}, logs=[grant(150), grant(480, "0x2"), grant(520, "0x3"), grant(990, "0x4")]); since, block, seen, runs = 0, 1000, [], 0
        while True:
            runs += 1; w = self.scan(n, "m", since, block); seen += [e["block"] for e in w["role_events"]]
            self.assertNotIn("gap_blocks", w)                                                    # nothing is jumped over
            nxt = watch_run.scanned_to(w, since, block)
            if w["read"]: break
            self.assertEqual(nxt, since + 500); self.assertEqual(w["unread_blocks"], block - nxt); self.assertIn("getLogs:", w["error"]); since = nxt   # 5 calls of 100 blocks, then the marker moves on what was read
        self.assertEqual(runs, 2); self.assertEqual(seen, [150, 480, 520, 990])                  # every event once, in order, none lost, none twice
        self.assertEqual(watch_run.scanned_to(w, since, block), block)

    def test_a_partial_scan_moves_the_marker_so_the_stall_alarm_does_not_fire(self):
        prev = {"block": 900, "self_scanned_to": 400, "scan_stalled_runs": 0}
        cur = {"name": "Monad", "block": 1000, "self": {"read": False, "scanned_upto": 700, "unread_blocks": 300}, "self_scanned_to": 700}
        stalled, alerts = scan_progress(prev, cur)
        self.assertEqual((stalled, alerts), (0, []))                                             # the scan moved: catching up is not a hole and not a stall

    def test_what_is_still_unread_is_written_in_the_summary_line_of_the_run(self):
        src = open(os.path.join(os.path.dirname(watch_run.__file__), "watch_run.py"), encoding="utf-8").read()
        self.assertIn('"unread_blocks": sw.get("unread_blocks")', src)


class TestTheRealCaseOfThe15thOfNovember(Base):
    """The nodes the Watch really uses, with the ranges they were measured to accept on 15 November: Base Sepolia (sepolia.base.org 100, publicnode 50000, Tenderly 100000) and Monad (testnet-rpc.monad.xyz 100, Tenderly 1000)."""
    LIMITS = {"https://sepolia.base.org": 100, "https://base-sepolia-rpc.publicnode.com": 50000, "https://base-sepolia.gateway.tenderly.co": 100000,
              "https://testnet-rpc.monad.xyz/": 100, "https://monad-testnet.gateway.tenderly.co": 1000, "https://rpc-testnet.monadinfra.com": 100, "https://rpc.ankr.com/monad_testnet": 100}

    def test_base_sepolia_window_of_98856_blocks_is_read_whole_in_one_run(self):
        n = Nodes(self.LIMITS, logs=[grant(59_200_000)]); w = self.scan(n, "https://sepolia.base.org", 59_177_000, 59_177_000 + 98_856)
        self.assertTrue(w["read"], w.get("error")); self.assertNotIn("gap_blocks", w); self.assertEqual(w["unread_blocks"] if "unread_blocks" in w else 0, 0); self.assertEqual(len(w["role_events"]), 1)
        self.assertLessEqual(len(n.ok()), watch_run.LOG_CALL_CAP)

    def test_monad_window_of_63609_blocks_is_read_whole_in_one_run(self):
        n = Nodes(self.LIMITS, logs=[grant(79_990_000)]); w = self.scan(n, "https://testnet-rpc.monad.xyz/", 79_980_000, 79_980_000 + 63_609)
        self.assertTrue(w["read"], w.get("error")); self.assertNotIn("gap_blocks", w); self.assertEqual(len(w["role_events"]), 1); self.assertLessEqual(len(n.ok()), watch_run.LOG_CALL_CAP)

    def test_a_normal_six_hour_window_of_monad_fits_too(self):
        n = Nodes(self.LIMITS); w = self.scan(n, "https://testnet-rpc.monad.xyz/", 80_000_000, 80_000_000 + 54_000); self.assertTrue(w["read"], w.get("error"))

    def test_the_two_oracles_have_a_second_node_with_a_wider_range_in_the_list(self):
        for first in ("https://sepolia.base.org", "https://testnet-rpc.monad.xyz/"):
            lst = watch_run.LOG_NODES[first]; self.assertEqual(lst[0] in (first,) or first in lst, True); self.assertGreaterEqual(len(lst), 2)


if __name__ == "__main__":
    unittest.main()
