"""Tests of the second part of the readers: scripts/lib/reader_extras.py and its use by scripts/second_opinion.py.

No network, no key. The end-to-end tests run second_opinion.main() against an in-process FAKE NODE (a dict of contracts that answers eth_call, eth_getCode,
eth_getStorageAt, eth_getLogs, eth_blockNumber), so what the reader publishes is checked, not the lines that produce it.
"""
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, SCRIPTS)
sys.path.insert(0, os.path.join(SCRIPTS, "lib"))
from lib import reader_extras as rx  # noqa: E402

word = lambda n: "0x" + "%064x" % n
addr_word = lambda a: "0x" + "00" * 12 + a[2:].lower()


class TestConstants(unittest.TestCase):
    def test_topics_selectors_and_role_hashes_are_the_keccak_of_their_signatures(self):
        try:
            from web3 import Web3
        except ImportError:
            self.skipTest("web3 absent")
        k = lambda s: "0x" + Web3.keccak(text=s).hex().removeprefix("0x")
        self.assertEqual(rx.MIN_DELAY_CHANGE, k("MinDelayChange(uint256,uint256)"))
        self.assertEqual(rx.NEW_DELAY, k("NewDelay(uint256)"))
        self.assertEqual(rx.OWNERSHIP_TRANSFER_STARTED, k("OwnershipTransferStarted(address,address)"))
        self.assertEqual(rx.OWNERSHIP_TRANSFERRED, k("OwnershipTransferred(address,address)"))
        self.assertEqual(rx.DEFAULT_ADMIN_TRANSFER_SCHEDULED, k("DefaultAdminTransferScheduled(address,uint48)"))
        self.assertEqual(rx.DEFAULT_ADMIN_TRANSFER_CANCELED, k("DefaultAdminTransferCanceled()"))
        self.assertEqual(rx.DEFAULT_ADMIN_DELAY_CHANGE_SCHEDULED, k("DefaultAdminDelayChangeScheduled(uint48,uint48)"))
        self.assertEqual(rx.DEFAULT_ADMIN_DELAY_SEL, k("defaultAdminDelay()")[:10])
        self.assertEqual(rx.HAS_ROLE_SEL, k("hasRole(bytes32,address)")[:10])
        self.assertEqual("0x" + rx.EXECUTOR_ROLE, k("EXECUTOR_ROLE"))


class TestChunks(unittest.TestCase):
    def test_the_chunk_per_chain_is_the_one_measured_on_30_october_2026(self):
        self.assertEqual(rx.LOG_STEP_BY_CHAIN, {"monad": 100, "hyperliquid": 1000, "plasma": 10_000, "base": 10_000})      # lectures-getlogs.txt: widest range each RPC answered
        self.assertEqual(rx.LOG_STEP_BLOCKS, 100_000)


class TestWindow(unittest.TestCase):
    def test_a_window_runs_from_the_block_after_the_previous_record(self):
        self.assertEqual(rx.window_for(100, 150), {"from": 101, "to": 150, "cut": False})

    def test_no_window_without_a_previous_block_or_when_the_chain_did_not_advance(self):
        for prev, now in ((None, 150), (150, 150), (160, 150), ("x", 150), (True, 150), (100, None)):
            self.assertIn("reason", rx.window_for(prev, now), (prev, now))

    def test_a_window_above_the_bound_is_cut_to_its_last_blocks_and_says_so(self):
        w = rx.window_for(0, 1_000_000, max_blocks=1000)
        self.assertEqual((w["from"], w["to"], w["cut"]), (999_001, 1_000_000, True))

    def test_scan_logs_chunks_the_range_and_an_unanswered_chunk_is_an_incomplete_scan_not_an_empty_one(self):
        asked = []
        def getlogs(a, b):
            asked.append((a, b))
            return [{"blockNumber": hex(a)}] if (a, b) != (21, 30) else None
        logs, complete = rx.scan_logs(getlogs, 1, 45, step=10)
        self.assertEqual(asked, [(1, 10), (11, 20), (21, 30)])
        self.assertFalse(complete)
        self.assertEqual(len(logs), 2)
        logs, complete = rx.scan_logs(lambda a, b: [], 1, 45, step=10)
        self.assertEqual((logs, complete), ([], True))
        asked = []
        self.assertEqual(rx.scan_logs(lambda a, b: (asked.append(a), [])[1], 1, 1000, step=10, max_calls=3)[1], False)       # the rest is not read: said, not hidden
        self.assertEqual(len(asked), 3)                                                                                     # exactly the calls allowed, not one more
        self.assertEqual(rx.scan_logs(lambda a, b: [], 1, 30, step=10, max_calls=3), ([], True))                            # 3 chunks in 3 calls is complete


class TestDecode(unittest.TestCase):
    def test_each_event(self):
        a, b = "0x" + "aa" * 20, "0x" + "bb" * 20
        t = lambda x: "0x" + "00" * 12 + x[2:]
        ev = rx.decode_event({"topics": [rx.OWNERSHIP_TRANSFER_STARTED, t(a), t(b)], "data": "0x", "address": "0xCC", "blockNumber": "0x10", "transactionHash": "0x01"})
        self.assertEqual((ev["event"], ev["previous"], ev["new"], ev["block"], ev["address"]), ("OwnershipTransferStarted", a, b, 16, "0xcc"))
        ev = rx.decode_event({"topics": [rx.MIN_DELAY_CHANGE], "data": word(172800) + word(3600)[2:], "address": "0xcc", "blockNumber": "0x20"})
        self.assertEqual((ev["old"], ev["new"]), (172800, 3600))
        ev = rx.decode_event({"topics": [rx.NEW_DELAY, word(7200)], "data": "0x", "address": "0xcc", "blockNumber": "0x20"})
        self.assertEqual((ev["old"], ev["new"]), (None, 7200))
        ev = rx.decode_event({"topics": [rx.DEFAULT_ADMIN_TRANSFER_SCHEDULED, t(b)], "data": word(1790000000), "address": "0xcc", "blockNumber": "0x20"})
        self.assertEqual((ev["new"], ev["accept_schedule"]), (b, 1790000000))
        self.assertEqual(rx.decode_event({"topics": [rx.DEFAULT_ADMIN_TRANSFER_CANCELED], "data": "0x", "address": "0xcc", "blockNumber": "0x20"})["event"], "DefaultAdminTransferCanceled")
        ev = rx.decode_event({"topics": [rx.DEFAULT_ADMIN_DELAY_CHANGE_SCHEDULED], "data": word(0) + word(1790000000)[2:], "address": "0xcc", "blockNumber": "0x20"})
        self.assertEqual((ev["event"], ev["new_delay"], ev["effect_schedule"]), ("DefaultAdminDelayChangeScheduled", 0, 1790000000))      # a delay of 0 scheduled is a value
        self.assertIsNone(rx.decode_event({"topics": ["0x" + "11" * 32], "data": "0x"}))
        self.assertIsNone(rx.decode_event({"topics": [], "data": "0x"}))
        ev = rx.decode_event({"topics": [rx.MIN_DELAY_CHANGE], "data": "0x12", "address": "0xcc", "blockNumber": "0x20"})
        self.assertEqual((ev["old"], ev["new"]), (None, None))                 # unreadable is None, never 0

    def test_delay_change_direction_and_the_compound_case(self):
        evs = [{"event": "MinDelayChange", "old": 172800, "new": 3600, "block": 5}]
        self.assertEqual(rx.delay_change_of(evs), {"old": 172800, "new": 3600, "block": 5, "direction": "shorter"})
        self.assertEqual(rx.delay_change_of([{"event": "MinDelayChange", "old": 3600, "new": 7200, "block": 5}])["direction"], "longer")
        c = rx.delay_change_of([{"event": "NewDelay", "old": None, "new": 3600, "block": 6}], previous_delay=172800)
        self.assertEqual((c["old"], c["direction"]), (172800, "shorter"))
        c = rx.delay_change_of([{"event": "NewDelay", "old": None, "new": 3600, "block": 6}])
        self.assertEqual((c["old"], c["direction"]), (None, None))              # no previous delay known: the direction is not claimed
        self.assertIsNone(rx.delay_change_of([{"event": "OwnershipTransferStarted"}]))
        self.assertIsNone(rx.delay_change_of([]))

    def test_admin_events_keep_the_newest_ten_and_leave_delay_events_out(self):
        evs = [{"event": "OwnershipTransferStarted", "block": i} for i in range(15)] + [{"event": "MinDelayChange", "block": 99}]
        got, total = rx.admin_events_of(evs)
        self.assertEqual([e["block"] for e in got], list(range(5, 15)))
        self.assertEqual(total, 15)                                              # more than the ten kept: said, not hidden


class TestReads(unittest.TestCase):
    def test_default_admin_delay_and_executor_answers(self):
        self.assertEqual(rx.default_admin_delay_of(word(172800)), 172800)
        self.assertIsNone(rx.default_admin_delay_of("0x"))
        self.assertIsNone(rx.default_admin_delay_of(None))
        self.assertIsNone(rx.default_admin_delay_of(word(10 ** 12)))             # not a delay in seconds
        self.assertIs(rx.open_executor_of(word(1)), True)
        self.assertIs(rx.open_executor_of(word(0)), False)                       # the getter answered no: that is a value
        self.assertIsNone(rx.open_executor_of("0x"))                             # no getter (Compound), or no answer: nothing is claimed
        self.assertIsNone(rx.open_executor_of(None))
        self.assertIsNone(rx.open_executor_of("0x" + "zz" * 32))                 # 66 characters that are not a number: no claim, not False
        m, params = rx.open_executor_call("0xTL")
        self.assertEqual(m, "eth_call")
        self.assertEqual(params[0]["data"], rx.HAS_ROLE_SEL + rx.EXECUTOR_ROLE + "0" * 64)


class TestAdminGap(unittest.TestCase):
    H, M1, M2, M3 = "0x" + "11" * 20, "0x" + "22" * 20, "0x" + "33" * 20, "0x" + "44" * 20

    def members(self, **kw):
        base = {"members": [self.H, self.M1, self.M2], "total": 3, "read": 3, "unread": 0, "note": None}
        base.update(kw)
        return base

    def test_the_other_holders_are_counted_by_what_they_are(self):
        g = rx.admin_gap(self.H, self.members(), {self.M1: "eoa", self.M2: "contract"})
        self.assertEqual((g["not_weighed"], g["not_weighed_plain_keys"], g["not_weighed_contracts"], g["not_weighed_unclassified"]), (2, 1, 1, 0))
        self.assertIn("2 other holder(s)", g["text"])

    def test_a_member_whose_code_was_not_read_is_unclassified_not_a_contract(self):
        g = rx.admin_gap(self.H, self.members(), {self.M1: None, self.M2: "contract"})
        self.assertEqual((g["not_weighed_plain_keys"], g["not_weighed_contracts"], g["not_weighed_unclassified"]), (0, 1, 1))

    def test_unread_members_and_an_unknown_count_are_said(self):
        g = rx.admin_gap(self.H, self.members(total=25, unread=22, members=[self.H]), {})
        self.assertEqual(g["not_weighed"], 0)
        self.assertIn("22 more not read", g["text"])
        g = rx.admin_gap(self.H, {"members": [self.H], "total": None, "read": 1, "unread": None}, {})
        self.assertIn("number of holders was not read", g["text"])

    def test_a_sole_holder_leaves_nothing_to_say(self):
        g = rx.admin_gap(self.H, self.members(members=[self.H], total=1, read=1), {})
        self.assertIsNone(g["text"])
        self.assertIsNone(rx.admin_gap(self.H, None, {}))

    def test_the_comparison_with_the_score(self):
        g = rx.admin_gap(self.H, self.members(), {self.M1: "eoa", self.M2: "contract"})
        self.assertIn("plain keys and can act alone", rx.member_disagreement(60, g))
        self.assertIsNone(rx.member_disagreement(10, g))                         # the score already says a bare key: nothing to contradict
        self.assertIsNone(rx.member_disagreement(None, g))
        g2 = rx.admin_gap(self.H, self.members(), {self.M1: "contract", self.M2: "contract"})
        self.assertIsNone(rx.member_disagreement(60, g2))                        # contracts: no claim
        g3 = rx.admin_gap(self.H, self.members(), {self.M1: None, self.M2: None})
        self.assertIsNone(rx.member_disagreement(60, g3))                        # unread: no claim


class FakeNode:
    """An in-process node: contracts as dicts. An unknown call reverts ("0x"), like a contract without the getter; the answer "NOANSWER" is a node that did not answer."""
    def __init__(self, block=1000):
        self.block, self.code, self.calls, self.logs, self.getlogs_calls, self.fail_logs, self.log_urls = block, {}, {}, [], [], False, []
        self.offsets, self.url, self.no_block = {}, "", False      # a chain whose url contains a key of `offsets` is that many blocks ahead; no_block: the node does not answer eth_blockNumber

    def set(self, to, sig_or_sel, answer):
        self.calls[(to.lower(), sig_or_sel)] = answer

    def one(self, method, params):
        if method == "eth_blockNumber":
            if self.no_block:
                return None
            return hex(self.block + sum(v for k, v in self.offsets.items() if k in self.url))
        if method == "eth_getCode":
            return self.code.get(params[0].lower(), "0x")
        if method == "eth_getStorageAt":
            return word(0)
        if method == "eth_getTransactionCount":
            return "0x1"
        if method == "eth_call":
            got = self.calls.get((params[0]["to"].lower(), params[0]["data"][:10]), "0x")       # a revert (no such getter) comes back as "0x", like rpc_batch does for the real nodes
            return None if got == "NOANSWER" else got
        if method == "eth_getLogs":
            f = params[0]
            self.getlogs_calls.append((int(f["fromBlock"], 16), int(f["toBlock"], 16)))
            if self.fail_logs:
                return None
            addrs = {a.lower() for a in (f["address"] if isinstance(f["address"], list) else [f["address"]])}
            topics = set(f["topics"][0])
            return [l for l in self.logs if l["address"].lower() in addrs and l["topics"][0] in topics and int(f["fromBlock"], 16) <= int(l["blockNumber"], 16) <= int(f["toBlock"], 16)]
        return None

    def batch(self, url, calls):
        self.url = url
        if any(m == "eth_getLogs" for m, _ in calls):
            self.log_urls.append(url)
        return [self.one(m, p) for m, p in calls]


T_AC, T_OWN, T_DA, TL = "0x" + "a1" * 20, "0x" + "a2" * 20, "0x" + "a3" * 20, "0x" + "b1" * 20
T_C, TL2, T_ARB = "0x" + "a4" * 20, "0x" + "b2" * 20, "0x" + "a5" * 20
SAFE, KEY1, CON1 = "0x" + "c1" * 20, "0x" + "d1" * 20, "0x" + "e1" * 20
CONTRACT_CODE = "0x6080604052" + "00" * 40


class TestSecondOpinionAgainstAFakeNode(unittest.TestCase):
    def setUp(self):
        import second_opinion as so
        self.so = so
        self.tmp = tempfile.TemporaryDirectory()
        self.d = self.tmp.name
        os.makedirs(os.path.join(self.d, "scores"))
        self.node = n = FakeNode(1000)
        for a in (T_AC, T_OWN, T_DA, TL, SAFE, CON1, T_C, TL2, T_ARB):
            n.code[a.lower()] = CONTRACT_CODE
        # T_AC: AccessControlEnumerable, 3 members: a Safe 3-of-5 (the holder), a plain key, a contract
        n.set(T_AC, "0x01ffc9a7", word(1))
        n.set(T_AC, "0xca15c873", word(3))
        # T_OWN: Ownable, owner() = the timelock TL; TL answers getMinDelay; an open executor
        n.set(T_OWN, "0x8da5cb5b", addr_word(TL))
        n.set(TL, "0xf27a0c92", word(3600))
        n.set(TL, "0x91d14854", word(1))
        # T_DA: owner() = Safe; AccessControlDefaultAdminRules: pendingDefaultAdmin zero, defaultAdminDelay 2 days
        n.set(T_DA, "0x8da5cb5b", addr_word(SAFE))
        n.set(T_DA, "0xcf6eefb7", word(0) + word(0)[2:])
        n.set(T_DA, "0xcc8463c8", word(172800))
        # T_C: owner() = a Compound-style timelock (no getMinDelay, delay() answers)
        n.set(T_C, "0x8da5cb5b", addr_word(TL2))
        n.set(TL2, "0x6a42b8f8", word(3600))
        n.set(T_ARB, "0x8da5cb5b", addr_word(SAFE))
        n.set(SAFE, "0xe75235b8", word(3))
        n.set(SAFE, "0xa0e67e2b", word(0x20) + word(5)[2:] + "".join(("00" * 12 + ("%02x" % (0x70 + i)) * 20) for i in range(5)))
        json.dump({"kind": "evm", "name": "Fake", "readAt": 1790000000, "targets": [
            {"target": t, "adminKeyScore": 60, "multisigScore": 60, "timelockScore": 0, "lastUpdated": 1789999000} for t in (T_AC, T_OWN, T_DA, T_C)]},
            open(os.path.join(self.d, "scores", "ethereum-l1-sepolia.json"), "w"))
        self._orig = so.rpc_batch
        so.rpc_batch = n.batch
        # the members of T_AC are read through getRoleMember(bytes32,uint256) (0x9010d07c): answer by index through the data suffix
        orig_one = n.one
        members = [SAFE, KEY1, CON1]
        def one(method, params):
            if method == "eth_call" and params[0]["to"].lower() == T_AC.lower() and params[0]["data"].startswith("0x9010d07c"):
                return addr_word(members[int(params[0]["data"][-64:], 16)]) if int(params[0]["data"][-64:], 16) < 3 else None
            return orig_one(method, params)
        n.one = one

    def tearDown(self):
        self.so.rpc_batch = self._orig
        self.tmp.cleanup()

    def run_reader(self):
        out = os.path.join(self.d, "second_opinion.json")
        old = sys.argv
        sys.argv = ["second_opinion.py", "--scores", os.path.join(self.d, "scores"), "--out", out, "--md", os.path.join(self.d, "so.md"), "--ack", os.path.join(self.d, "ack.json"),
                    "--tvl", os.path.join(self.d, "tvl.json"), "--held", os.path.join(self.d, "held.json"), "--events", os.path.join(self.d, "events.jsonl")]
        cwd = os.getcwd()
        os.chdir(self.d)
        try:
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.so.main()
        finally:
            sys.argv = old
            os.chdir(cwd)
        return json.load(open(out))

    def rec(self, doc, target):
        return next(r for r in doc["results"] if str(r["target"]).lower() == target.lower())

    def test_the_first_run_has_no_window_and_says_why(self):
        doc = self.run_reader()
        w = doc["event_windows"]["ethereum-l1"]
        self.assertIsNone(w["from"])
        self.assertIn("first run", w["note"])
        self.assertIsNone(self.rec(doc, T_OWN)["admin_events"])
        self.assertEqual(self.node.getlogs_calls, [])

    def test_the_holders_the_score_does_not_weigh_are_compared_to_the_score(self):
        doc = self.run_reader()
        r = self.rec(doc, T_AC)
        self.assertEqual(r["admin_members"]["total"], 3)
        gap = r["admin_members_gap"]
        self.assertEqual((gap["not_weighed"], gap["not_weighed_plain_keys"], gap["not_weighed_contracts"]), (2, 1, 1))
        self.assertIn("plain keys and can act alone", r["disagree"])               # the score is 60, another holder of the role is a plain key
        self.assertIn(r, doc["disagreements"])

    def test_an_open_executor_and_the_delay_of_the_default_admin(self):
        doc = self.run_reader()
        self.assertIs(self.rec(doc, T_OWN)["open_executor"], True)
        self.assertEqual(self.rec(doc, T_DA)["default_admin_delay_seconds"], 172800)
        self.assertNotIn("default_admin_delay_seconds", self.rec(doc, T_OWN))        # no pendingDefaultAdmin() getter: no claim about a default admin delay

    def test_an_executor_that_answers_no_is_false_not_unknown(self):
        self.node.set(TL, "0x91d14854", word(0))
        self.assertIs(self.rec(self.run_reader(), T_OWN)["open_executor"], False)
        self.node.set(TL, "0x91d14854", "0x")                                       # a Compound-style timelock has no hasRole
        self.assertIsNone(self.rec(self.run_reader(), T_OWN)["open_executor"])

    def test_the_second_run_reads_the_events_of_the_window_and_sees_a_transfer_started_between_the_runs(self):
        self.run_reader()
        self.node.block = 1500
        self.node.logs = [
            {"address": T_OWN, "topics": [rx.OWNERSHIP_TRANSFER_STARTED, "0x" + "00" * 12 + "aa" * 20, "0x" + "00" * 12 + "bb" * 20], "data": "0x", "blockNumber": hex(1200), "transactionHash": "0x01"},
            {"address": TL, "topics": [rx.MIN_DELAY_CHANGE], "data": word(3600) + word(60)[2:], "blockNumber": hex(1300), "transactionHash": "0x02"},
            {"address": T_AC, "topics": [rx.OWNERSHIP_TRANSFER_STARTED, "0x" + "00" * 12 + "aa" * 20, "0x" + "00" * 12 + "bb" * 20], "data": "0x", "blockNumber": hex(900), "transactionHash": "0x03"},   # before the window
            {"address": T_OWN, "topics": [rx.OWNERSHIP_TRANSFERRED, "0x" + "00" * 12 + "bb" * 20, "0x" + "00" * 12 + "cc" * 20], "data": "0x", "blockNumber": hex(1001), "transactionHash": "0x04"},   # the first block of the window
            {"address": T_OWN, "topics": [rx.OWNERSHIP_TRANSFERRED, "0x" + "00" * 12 + "cc" * 20, "0x" + "00" * 12 + "dd" * 20], "data": "0x", "blockNumber": hex(1500), "transactionHash": "0x05"},   # the last block
            {"address": T_OWN, "topics": [rx.MIN_DELAY_CHANGE], "data": word(1) + word(2)[2:], "blockNumber": hex(1100), "transactionHash": "0x06"}]   # a delay event emitted by the target itself is not an admin event
        doc = self.run_reader()
        w = doc["event_windows"]["ethereum-l1"]
        self.assertEqual((w["from"], w["to"], w["complete"]), (1001, 1500, True))
        r = self.rec(doc, T_OWN)
        self.assertEqual([(e["event"], e["block"]) for e in r["admin_events"]], [("OwnershipTransferred", 1001), ("OwnershipTransferStarted", 1200), ("OwnershipTransferred", 1500)])
        self.assertTrue(r["admin_events"][1]["new"].startswith("0xbbbb"))
        self.assertIn("…", r["admin_events"][1]["new"])                             # a plain key does not leave in full
        self.assertEqual(r["delay_change"], {"old": 3600, "new": 60, "block": 1300, "direction": "shorter"})
        self.assertEqual(self.rec(doc, T_AC)["admin_events"], [])                  # the older event is outside the window

    def test_the_logs_are_asked_to_the_gateway_that_answers_them_not_to_publicnode(self):
        self.run_reader()
        self.node.block = 1500
        self.run_reader()
        self.assertEqual(self.node.log_urls[0], "https://gateway.tenderly.co/public/mainnet")      # publicnode answers 403 to eth_getLogs (read 30/10/2026)

    def test_a_compound_new_delay_is_compared_to_the_delay_the_previous_record_read(self):
        self.run_reader()
        self.node.block = 1500
        self.node.set(TL2, "0x6a42b8f8", word(60))
        self.node.logs = [{"address": TL2, "topics": [rx.NEW_DELAY, word(60)], "data": "0x", "blockNumber": hex(1300), "transactionHash": "0x07"}]
        doc = self.run_reader()
        r = self.rec(doc, T_C)
        self.assertEqual(r["timelock_family"], "compound")
        self.assertEqual(r["delay_change"], {"old": 3600, "new": 60, "block": 1300, "direction": "shorter"})
        self.assertNotIn("open_executor", r)                                         # a Compound timelock has no hasRole: no claim

    def test_the_window_of_a_chain_starts_after_the_previous_record_of_THAT_chain(self):
        json.dump({"kind": "evm", "name": "Fake2", "readAt": 1790000000, "targets": [{"target": T_ARB, "adminKeyScore": 60, "multisigScore": 60, "timelockScore": 0, "lastUpdated": 1789999000}]},
                  open(os.path.join(self.d, "scores", "arbitrum-sepolia.json"), "w"))
        self.node.offsets = {"arbitrum": 5000}                              # the other chain is far ahead
        self.run_reader()
        self.node.block = 1500
        doc = self.run_reader()
        self.assertEqual(doc["event_windows"]["ethereum-l1"]["from"], 1001)          # not 6001: the previous record of the other chain does not count
        self.assertEqual(doc["event_windows"]["arbitrum"]["from"], 6001)

    def test_an_unreadable_window_leaves_no_events_in_the_records_not_an_empty_list(self):
        self.run_reader()
        self.node.block = 1500
        self.node.fail_logs = True
        doc = self.run_reader()
        r = self.rec(doc, T_OWN)
        self.assertIsNone(r["admin_events"])                                         # [] would say "none happened"
        self.assertIsNone(r["admin_events_total"])
        self.assertIsNone(r["delay_change"])

    def test_a_window_the_node_refused_is_read_again_and_nothing_is_lost(self):
        doc = self.run_reader()
        self.assertEqual(doc["event_windows"]["ethereum-l1"]["scanned_to"], 1000)       # the first run only sets the marker
        self.node.block, self.node.fail_logs = 1500, True
        doc = self.run_reader()
        self.assertEqual(doc["event_windows"]["ethereum-l1"]["scanned_to"], 1000)       # nothing was read: the marker stays
        self.node.block, self.node.fail_logs = 2000, False
        self.node.logs = [{"address": T_OWN, "topics": [rx.OWNERSHIP_TRANSFER_STARTED, "0x" + "00" * 12 + "aa" * 20, "0x" + "00" * 12 + "bb" * 20], "data": "0x", "blockNumber": hex(1200), "transactionHash": "0x01"}]
        doc = self.run_reader()
        w = doc["event_windows"]["ethereum-l1"]
        self.assertEqual((w["from"], w["to"], w["complete"], w["scanned_to"]), (1001, 2000, True, 2000))      # the blocks the refused run missed are read now
        self.assertEqual(len(self.rec(doc, T_OWN)["admin_events"]), 1)

    def test_a_run_whose_block_was_not_read_does_not_lose_the_window_either(self):
        self.run_reader()
        self.node.block, self.node.no_block = 1500, True
        doc = self.run_reader()
        self.assertIsNone(doc["event_windows"]["ethereum-l1"]["from"])
        self.assertEqual(doc["event_windows"]["ethereum-l1"]["scanned_to"], 1000)
        self.node.no_block, self.node.block = False, 1800
        doc = self.run_reader()
        self.assertEqual(doc["event_windows"]["ethereum-l1"]["from"], 1001)

    def test_a_window_cut_at_the_bound_is_not_complete(self):
        self.run_reader()
        self.node.block = 1000 + rx.MAX_WINDOW_BLOCKS + 5000
        doc = self.run_reader()
        w = doc["event_windows"]["ethereum-l1"]
        self.assertEqual((w["cut"], w["complete"]), (True, False))
        self.assertIsNone(self.rec(doc, T_OWN)["admin_events"])
        self.assertEqual(w["scanned_to"], w["to"])                                    # the lost blocks are said once, then the marker moves on

    def test_the_first_run_of_the_lot_starts_from_the_previous_record_of_the_same_chain(self):
        json.dump({"kind": "evm", "name": "Fake2", "readAt": 1790000000, "targets": [{"target": T_ARB, "adminKeyScore": 60, "multisigScore": 60, "timelockScore": 0, "lastUpdated": 1789999000}]},
                  open(os.path.join(self.d, "scores", "arbitrum-sepolia.json"), "w"))
        self.node.offsets = {"arbitrum": 5000}
        self.run_reader()
        out = os.path.join(self.d, "second_opinion.json")
        old = json.load(open(out)); old.pop("event_windows")                          # a file written before the lot: no marker, only the records
        json.dump(old, open(out, "w"))
        self.node.block = 1500
        doc = self.run_reader()
        self.assertEqual(doc["event_windows"]["ethereum-l1"]["from"], 1001)          # the record of Ethereum, not the later one of Arbitrum
        self.assertEqual(doc["event_windows"]["arbitrum"]["from"], 6001)

    def test_the_window_never_ends_beyond_the_head_of_the_node_that_answers_the_logs(self):
        self.run_reader()
        self.node.block = 1500
        self.node.offsets = {"tenderly": -100}                                        # the logs gateway is 100 blocks behind
        doc = self.run_reader()
        w = doc["event_windows"]["ethereum-l1"]
        self.assertEqual((w["from"], w["to"], w["scanned_to"]), (1001, 1400, 1400))

    def test_the_chunk_is_the_one_measured_for_the_chain(self):
        self.run_reader()
        self.node.block = 1500
        self.so.LOG_STEP_BY_CHAIN = {"ethereum-l1": 100}
        try:
            self.run_reader()
        finally:
            self.so.LOG_STEP_BY_CHAIN = rx.LOG_STEP_BY_CHAIN
        self.assertEqual(self.node.getlogs_calls, [(1001, 1100), (1101, 1200), (1201, 1300), (1301, 1400), (1401, 1500)])

    def test_a_plain_key_among_the_members_never_leaves_in_full(self):
        self.node.code[SAFE.lower()] = "0x"                                           # the first member of T_AC is now a plain key: the holder is an EOA
        doc = self.run_reader()
        r = self.rec(doc, T_AC)
        self.assertIn("…", r["admin_members_gap"]["weighed_holder"])
        self.assertTrue(all(("…" in m) == (m.lower() != CON1.lower()) for m in r["admin_members"]["members"]), r["admin_members"]["members"])      # keys shortened, the contract whole

    def test_an_unreadable_holder_with_members_does_not_corrupt_the_counts(self):
        self.node.set(SAFE, "0xe75235b8", "NOANSWER")                                  # the first member's getThreshold() gets no answer: the record is unreadable
        doc = self.run_reader()
        r = self.rec(doc, T_AC)
        self.assertEqual(r["kind"], "unreadable")
        self.assertNotIn(r, doc["disagreements"])
        self.assertEqual(doc["agree"], sum(1 for x in doc["results"] if not x.get("disagree") and x.get("kind") not in ("unreadable", "native")))

    def test_a_shorter_default_admin_delay_is_a_change_of_the_admin_path(self):
        self.run_reader()
        self.node.block = 1500
        self.node.set(T_DA, "0xcc8463c8", word(0))                                     # 2 days -> 0
        doc = self.run_reader()
        r = self.rec(doc, T_DA)
        self.assertEqual(r["default_admin_delay_change"], {"previous": 172800, "now": 0, "direction": "shorter"})
        self.assertIn("shortened from 172800s to 0s", r["changed"])
        self.assertIn(r, doc["changed"])
        self.node.set(T_DA, "0xcc8463c8", word(259200))                               # longer: published, not alarmed
        doc = self.run_reader()
        r = self.rec(doc, T_DA)
        self.assertEqual(r["default_admin_delay_change"]["direction"], "longer")
        self.assertNotIn("shortened", r.get("changed") or "")

    def test_an_arbitrum_alias_holder_is_neither_a_plain_key_disagreement_nor_read_on_the_wrong_chain(self):
        l1 = "0x" + "f1" * 20
        alias = "0x%040x" % ((int(l1, 16) + self.so.ALIAS_OFFSET) % (1 << 160))
        self.node.code[l1.lower()] = CONTRACT_CODE
        self.node.set(l1, "0xf27a0c92", word(3600))                                      # the L1 holder is a timelock
        self.node.set(T_ARB, "0x8da5cb5b", "0x")                                         # no owner(): roles-based
        self.node.set(T_ARB, "0x01ffc9a7", word(1))
        self.node.set(T_ARB, "0xca15c873", word(1))
        orig_one = self.node.one
        self.node.one = lambda m, p: (addr_word(alias) if (m == "eth_call" and p[0]["to"].lower() == T_ARB.lower() and p[0]["data"].startswith("0x9010d07c")) else orig_one(m, p))
        json.dump({"kind": "evm", "name": "Fake2", "readAt": 1790000000, "targets": [{"target": T_ARB, "adminKeyScore": 60, "multisigScore": 60, "timelockScore": 0, "lastUpdated": 1789999000}]},
                  open(os.path.join(self.d, "scores", "arbitrum-sepolia.json"), "w"))
        doc = self.run_reader()
        r = self.rec(doc, T_ARB)
        self.assertEqual(r.get("alias_of"), l1)
        self.assertEqual(r["admin_members_gap"]["not_weighed"], 0)                       # the one member is the holder, before and after the alias hop
        self.assertNotIn("disagree", r)
        self.assertNotIn("open_executor", r)                                             # L1 reads are not asked to the Arbitrum RPC
        self.assertNotIn("delay_change", r)

    def test_a_window_the_node_refused_is_incomplete_not_empty(self):
        self.run_reader()
        self.node.block = 1500
        self.node.fail_logs = True
        doc = self.run_reader()
        self.assertIs(doc["event_windows"]["ethereum-l1"]["complete"], False)

    def test_the_delay_change_is_added_to_the_text_of_a_changed_admin(self):
        self.run_reader()
        self.node.block = 1500
        self.node.set(TL, "0xf27a0c92", word(60))                                   # the delay read now is not the one of the previous run
        self.node.logs = [{"address": TL, "topics": [rx.MIN_DELAY_CHANGE], "data": word(3600) + word(60)[2:], "blockNumber": hex(1300), "transactionHash": "0x02"}]
        doc = self.run_reader()
        r = self.rec(doc, T_OWN)
        self.assertIn("delay change to 60s at block 1300 (shorter)", r["changed"])


class TestEscalation(unittest.TestCase):
    NOW = 1_790_000_000
    iso = staticmethod(lambda s: __import__("time").strftime("%Y-%m-%dT%H:%M:%SZ", __import__("time").gmtime(s)))

    def state(self):
        return {"findings": ["disagree:base:0x" + "ab" * 20, "disagree:arbitrum:0x" + "cd" * 20, "overdue:review:x:0xaa:some text"],
                "first_seen": {"disagree:base:0x" + "ab" * 20: self.iso(self.NOW - 100 * 3600), "disagree:arbitrum:0x" + "cd" * 20: self.iso(self.NOW - 30 * 3600), "overdue:review:x:0xaa:some text": self.iso(self.NOW - 10 * 3600)},
                "first_notified_utc": self.iso(self.NOW - 30 * 3600)}

    def test_the_message_counts_from_the_oldest_finding_and_carries_no_address(self):
        import escalate
        m = escalate.message(self.state(), self.NOW)
        self.assertIn("ESCALATION", m)
        self.assertIn("stood for 100 hours", m)
        self.assertIn("3 finding(s) (2 disagree, 1 overdue)", m)
        self.assertNotIn("0xab", m)                                  # nothing private or specific leaves: counts and kinds only
        self.assertNotIn("some text", m)

    def test_no_finding_or_no_date_sends_nothing(self):
        import escalate
        self.assertIsNone(escalate.message({"findings": []}, self.NOW))
        self.assertIsNone(escalate.message({"findings": ["a"]}, self.NOW))
        self.assertIsNone(escalate.message(None, self.NOW))
        self.assertIsNone(escalate.message({"findings": ["a"], "first_notified_utc": "garbage"}, self.NOW))

    def test_each_configured_channel_gets_it_and_a_failure_does_not_stop_the_others(self):
        import escalate
        sent = []
        post_json = lambda url, p: (sent.append(("discord", p["content"])), True)[1]
        post_signed = lambda url, secret, p: (sent.append(("webhook", p["event"])), False)[1]
        telegram = lambda text: (sent.append(("telegram", text)), True)[1]
        env = {"DISCORD_WEBHOOK_URL": "http://d", "ALERT_WEBHOOK_URL": "https://w", "ALERT_WEBHOOK_SECRET": "s", "TELEGRAM_BOT_TOKEN": "t", "TELEGRAM_CHAT_ID": "c"}
        res = escalate.send("hello", env, post_json=post_json, post_signed=post_signed, telegram=telegram)
        self.assertEqual(res, {"discord": True, "webhook": False, "telegram": True})
        self.assertEqual(sorted(c for c, _ in sent), ["discord", "telegram", "webhook"])
        self.assertEqual(escalate.send("hello", {}, post_json=post_json, post_signed=post_signed, telegram=telegram), {})
        sent.clear()
        escalate.send("x" * 3000, {"DISCORD_WEBHOOK_URL": "http://d"}, post_json=post_json, post_signed=post_signed, telegram=telegram)
        self.assertEqual(len(sent[0][1]), 1900)                                              # Discord refuses a message above 2000 characters

    def test_the_command_exits_one_only_when_every_configured_channel_failed(self):
        import escalate
        with tempfile.TemporaryDirectory() as d:
            json.dump(self.state(), open(os.path.join(d, "alarm_state.json"), "w"))
            env = {"DISCORD_WEBHOOK_URL": "http://d"}
            import time
            real = time.time
            time.time = lambda: self.NOW
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(escalate.main(["--watch", d], env=env, post_json=lambda u, p: False, post_signed=lambda *a: False, telegram=lambda t: False), 1)
                    self.assertEqual(escalate.main(["--watch", d], env=env, post_json=lambda u, p: True, post_signed=lambda *a: False, telegram=lambda t: False), 0)
                    both = {"DISCORD_WEBHOOK_URL": "http://d", "ALERT_WEBHOOK_URL": "https://w", "ALERT_WEBHOOK_SECRET": "s"}
                    self.assertEqual(escalate.main(["--watch", d], env=both, post_json=lambda u, p: True, post_signed=lambda *a: False, telegram=lambda t: False), 0)      # one channel carried it: not a failure
                    self.assertEqual(escalate.main(["--watch", d], env={}, post_json=lambda u, p: False, post_signed=lambda *a: False, telegram=lambda t: False), 0)      # nobody configured: only the log
            finally:
                time.time = real

    def test_the_public_channels_hear_the_first_escalation_and_then_every_third_not_daily(self):
        import escalate, time
        real = time.time
        time.time = lambda: self.NOW
        try:
            with tempfile.TemporaryDirectory() as d:
                sent = []
                for n, expect in ((1, 1), (2, 0), (3, 1), (4, 0), (6, 1)):
                    st = dict(self.state(), escalations=n)
                    json.dump(st, open(os.path.join(d, "alarm_state.json"), "w"))
                    sent.clear()
                    with contextlib.redirect_stdout(io.StringIO()):
                        escalate.main(["--watch", d], env={"DISCORD_WEBHOOK_URL": "http://d"}, post_json=lambda u, p: (sent.append(1), True)[1], post_signed=lambda *a: True, telegram=lambda t: True)
                    self.assertEqual(len(sent), expect, "escalation %d" % n)
        finally:
            time.time = real

    def test_the_gate_counts_the_escalations_of_a_standing_state(self):
        import alarm_gate
        iso = lambda s: __import__("time").strftime("%Y-%m-%dT%H:%M:%SZ", __import__("time").gmtime(s))
        now = __import__("time").time()
        with tempfile.TemporaryDirectory() as d:
            log = os.path.join(d, "run.log")
            open(log, "w").write("quiet\n")
            for f in ("methodology.json", "review_queue.json", "alerts.json"):
                json.dump({}, open(os.path.join(d, f), "w"))
            json.dump({"disagreements": [{"chain": "base", "target": "0xaa"}]}, open(os.path.join(d, "second_opinion.json"), "w"))
            json.dump({"findings": ["disagree:base:0xaa"], "notified_utc": iso(now - 30 * 3600), "first_notified_utc": iso(now - 100 * 3600), "first_seen": {"disagree:base:0xaa": iso(now - 100 * 3600)}, "escalations": 2},
                      open(os.path.join(d, "alarm_state.json"), "w"))
            old = sys.argv
            os.environ["ALARM_CONDITION"] = "true"
            sys.argv = ["alarm_gate.py", "--watch", d, "--run-log", log, "--write"]
            try:
                with contextlib.redirect_stdout(io.StringIO()) as out, contextlib.redirect_stderr(io.StringIO()):
                    alarm_gate.main()
            finally:
                sys.argv = old
                os.environ.pop("ALARM_CONDITION", None)
            self.assertIn("mode=escalation", out.getvalue())
            self.assertEqual(json.load(open(os.path.join(d, "alarm_state.json")))["escalations"], 3)

    def test_the_workflow_labels_the_issue_and_runs_the_step_without_stopping_the_run(self):
        y = open(os.path.join(SCRIPTS, "..", ".github", "workflows", "watch.yml"), encoding="utf-8").read()
        self.assertIn("printf ',escalation'", y)
        i = y.index("Escalation: the same alarm state")
        block = y[i:i + 1400]
        self.assertIn("steps.gate.outputs.mode == 'escalation'", block)
        self.assertIn("continue-on-error: true", block)
        self.assertIn("python3 scripts/escalate.py --watch watch", block)
        self.assertLess(y.index("Record the run on the watch-data branch"), i)       # after the run is recorded: a failing channel cannot cost the record


if __name__ == "__main__":
    unittest.main()
