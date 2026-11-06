"""A Safe's module page is read only when it has the shape of a real answer.

Weakness class: the decoder of getModulesPaginated took any answer long enough to hold three words as a page. A contract that answers every call with
zeros (or a node that lies) was read as "no module, complete list"; a full page with a zero cursor, or a length above the page size, were read as
complete too. A module executes without the owners' signatures, so a list taken as complete when it was not read hides that power.

Checked on the decoder, on the trust rule fed by it, and on the real second_opinion.main() against an in-process fake node. No network.
"""
import contextlib, io, json, os, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.abspath(os.path.join(HERE, ".."))
for p in (SCRIPTS, os.path.join(SCRIPTS, "lib"), os.path.join(SCRIPTS, "lib", "tests")):
    if p not in sys.path:
        sys.path.insert(0, p)
import second_opinion as so  # noqa: E402
from lib import reader_audit as ra  # noqa: E402
from trust_support import A, Watch, status, codes, so_edit  # noqa: E402

SENTINEL = 1


def page(mods, nxt, offset=0x40, length=None):
    n = len(mods) if length is None else length
    return "0x" + "%064x" % offset + "%064x" % nxt + "%064x" % n + "".join("%064x" % m for m in mods)


ZEROS = "0x" + "0" * 192


def trust_of(mods, trunc):
    w = Watch()
    try:
        w.edit("second_opinion.json", so_edit(A, modules=mods, modules_truncated=trunc))
        d = w.trust()
        return status(d, A), codes(d, A)
    finally:
        w.close()


T = "0x" + "aa" * 19 + "01"
S = "0x" + "5a" * 19 + "fe"
OWNERS = ["0x%040x" % (0xb0 + i) for i in range(5)]


def reader_record(modules_answer):
    def answer(method, params):
        if method == "eth_blockNumber": return "0x100"
        if method == "eth_getLogs": return []
        if method == "eth_getTransactionCount": return "0x1"
        if method == "eth_getStorageAt": return "0x" + "0" * 64
        if method == "eth_getCode": return "0x6080604052" if params[0].lower() in (T, S) else "0x"
        if method == "eth_call":
            to, sel = params[0]["to"].lower(), params[0]["data"][:10]
            if to == T and sel == so.SEL["owner"]: return "0x" + "00" * 12 + S[2:]
            if to == S:
                if sel == so.SEL["getThreshold"]: return "0x%064x" % 3
                if sel == so.SEL["getOwners"]: return "0x" + "%064x" % 0x20 + "%064x" % 5 + "".join("%064x" % int(o, 16) for o in OWNERS)
                if sel == "0xcc2f8452": return modules_answer
            return {"code": 3, "message": "execution reverted"}
        return None

    def fake_post(url, payload):
        one = isinstance(payload, dict)
        out = []
        for p in ([payload] if one else payload):
            r = answer(p["method"], p["params"])
            out.append({"jsonrpc": "2.0", "id": p["id"], **({"error": r} if isinstance(r, dict) and "code" in r else {"result": r})})
        return out[0] if one else out

    with tempfile.TemporaryDirectory() as tmp:
        os.makedirs(os.path.join(tmp, "scores"))
        with open(os.path.join(tmp, "scores", "ethereum-l1-sepolia.json"), "w") as f:
            json.dump({"name": "Ethereum L1 (Sepolia)", "kind": "evm", "oracle": "0x" + "0f" * 20, "rpc": "https://x", "block": 1, "readAt": 1793000000,
                       "targets": [{"target": T, "adminKeyScore": 50, "multisigScore": 60, "timelockScore": 0, "oracleAuthorityScore": 100, "crossExposureScore": 100,
                                    "compositeScore": 50, "lastUpdated": 1793000000, "stale": False}]}, f)
        none = os.path.join(tmp, "none.json")
        orig, argv = so._post, sys.argv
        so._post = fake_post
        sys.argv = ["second_opinion.py", "--scores", os.path.join(tmp, "scores"), "--out", os.path.join(tmp, "so.json"), "--md", os.path.join(tmp, "so.md"),
                    "--ack", none, "--tvl", none, "--held", none, "--events", os.path.join(tmp, "events.jsonl")]
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                try:
                    so.main()
                except SystemExit:
                    pass
        finally:
            so._post, sys.argv = orig, argv
        with open(os.path.join(tmp, "so.json")) as f:
            return [r for r in json.load(f)["results"] if r["target"].lower() == T][0]


class TestTheDecoderIsStrict(unittest.TestCase):
    def test_an_answer_of_zeros_is_unread(self):
        self.assertEqual(ra.parse_modules_page(ZEROS), (None, None))
        self.assertIsNone(ra.modules_truncated_of(ZEROS))

    def test_a_full_page_with_a_zero_cursor_is_unread(self):
        self.assertEqual(ra.parse_modules_page(page(range(100, 150), 0)), (None, None))

    def test_a_length_above_the_page_is_unread(self):
        self.assertEqual(ra.parse_modules_page(page(range(100, 150), SENTINEL, length=60)), (None, None))
        self.assertEqual(ra.parse_modules_page(page(range(100, 160), SENTINEL)), (None, None))

    def test_a_wrong_offset_extra_words_or_a_non_address_word_are_unread(self):
        self.assertEqual(ra.parse_modules_page(page([5], SENTINEL, offset=0x20)), (None, None))
        self.assertEqual(ra.parse_modules_page(page([5], SENTINEL) + "0" * 64), (None, None))
        self.assertEqual(ra.parse_modules_page(page([(1 << 200) + 5], SENTINEL)), (None, None))
        self.assertEqual(ra.parse_modules_page(page([0], SENTINEL)), (None, None))

    # second round: the end of a list is the sentinel 1, never zero (a Safe from 1.1.1 to 1.4.1 ends getModulesPaginated with it)
    def test_a_cursor_of_zero_is_not_an_end_of_list_whatever_the_length_of_the_page(self):
        for mods in ([], [5], list(range(100, 149)), list(range(100, 150))):
            self.assertEqual(ra.parse_modules_page(page(mods, 0)), (None, None), len(mods))
            self.assertIsNone(ra.modules_truncated_of(page(mods, 0)), len(mods))

    def test_the_trust_rule_does_not_say_complete_for_a_cursor_of_zero(self):
        for mods in ([], list(range(100, 149))):
            m, t = ra.parse_modules_page(page(mods, 0))
            st, cs = trust_of(m, ra.modules_truncated_of(page(mods, 0)))
            self.assertNotEqual(st, "VERIFIED", len(mods))
            self.assertIn("modules_unread", cs)

    def test_the_trust_rule_says_unread_for_such_an_answer(self):
        mods, trunc = ra.parse_modules_page(ZEROS)
        st, cs = trust_of(mods, ra.modules_truncated_of(ZEROS))
        self.assertNotEqual(st, "VERIFIED")
        self.assertIn("modules_unread", cs)

    # controls: real answers keep their reading
    def test_control_an_empty_list_with_the_sentinel_is_complete(self):
        self.assertEqual(ra.parse_modules_page(page([], SENTINEL)), ([], False))
        self.assertEqual(trust_of([], False)[0], "VERIFIED")

    def test_control_a_full_page_with_the_sentinel_is_complete_and_one_with_a_cursor_is_cut(self):
        mods, trunc = ra.parse_modules_page(page(range(100, 150), SENTINEL))
        self.assertEqual((len(mods), trunc), (50, False))
        mods, trunc = ra.parse_modules_page(page(range(100, 150), 149))
        self.assertEqual((len(mods), trunc), (50, True))


class TestTheRealReader(unittest.TestCase):
    def test_a_safe_whose_module_page_is_an_empty_list_with_a_zero_cursor_is_not_read_as_complete(self):
        rec = reader_record(page([], 0))
        self.assertEqual(rec.get("kind"), "safe")
        self.assertIsNone(rec.get("modules"))
        self.assertIsNone(rec.get("modules_truncated"))

    def test_a_safe_whose_page_of_49_has_a_zero_cursor_is_not_read_as_complete(self):
        rec = reader_record(page(range(100, 149), 0))
        self.assertIsNone(rec.get("modules_truncated"))

    def test_a_safe_whose_module_page_is_zeros_is_not_read_as_complete(self):
        rec = reader_record(ZEROS)
        self.assertEqual(rec.get("kind"), "safe")
        self.assertIsNone(rec.get("modules"))
        self.assertIsNone(rec.get("modules_truncated"))

    def test_control_a_safe_with_no_module_is_read_as_complete(self):
        rec = reader_record(page([], SENTINEL))
        self.assertEqual((rec.get("modules"), rec.get("modules_truncated")), ([], False))


if __name__ == "__main__":
    unittest.main()
