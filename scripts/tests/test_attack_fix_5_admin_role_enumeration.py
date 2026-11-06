"""The enumeration of an admin role is not taken at its word.

Weakness class: the holders of an enumerable DEFAULT_ADMIN_ROLE were whatever getRoleMemberCount and getRoleMember answered. The same member returned at
every index, or a count lower than the real number of holders, read as a complete list with nothing unread, so the trust rule had nothing to degrade.
Now the members are distinct, an implausible count is not a count, and the index just past the count is asked: it must not hold a member.

Checked on the assembly, on the trust rule fed by it, and on the real second_opinion.main() against an in-process fake node. No network.
"""
import contextlib, io, json, os, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.abspath(os.path.join(HERE, ".."))
for p in (SCRIPTS, os.path.join(SCRIPTS, "lib"), os.path.join(SCRIPTS, "lib", "tests")):
    if p not in sys.path:
        sys.path.insert(0, p)
import second_opinion as so  # noqa: E402
from lib import reader_audit as ra  # noqa: E402
from lib.reader_extras import admin_gap  # noqa: E402
from trust_support import B, Watch, status, codes, so_edit  # noqa: E402

WORD = lambda a: "0x" + "00" * 12 + a[2:].lower()
M = lambda i: "0x%040x" % (0xe100 + i)
PATH = "DEFAULT_ADMIN_ROLE member 1 of %s (AccessControl)"


def trust_of(am, total):
    gap = admin_gap(B, am, {m.lower(): "eoa" for m in am["members"]})
    w = Watch()
    try:
        w.edit("second_opinion.json", so_edit(B, path=PATH % total, admin_members=am, admin_members_gap=gap, adminKeyScore=80))
        d = w.trust()
        return status(d, B), codes(d, B)
    finally:
        w.close()


T = "0x" + "aa" * 19 + "01"
REVERT = {"code": 3, "message": "execution reverted"}


def reader_record(count, member, real=None):
    """A roles-only target: the role announces `count` holders; getRoleMember(i) answers member(i) for i < real (default: count), a revert beyond."""
    real = count if real is None else real

    def answer(method, params):
        if method == "eth_blockNumber": return "0x100"
        if method == "eth_getLogs": return []
        if method == "eth_getTransactionCount": return "0x1"
        if method == "eth_getStorageAt": return "0x" + "0" * 64
        if method == "eth_getCode": return "0x6080604052" if params[0].lower() == T else "0x"
        if method == "eth_call":
            to, data = params[0]["to"].lower(), params[0]["data"]
            if to == T:
                if data[:10] == "0x01ffc9a7": return "0x%064x" % 1
                if data[:10] == "0xca15c873": return "0x%064x" % count
                if data[:10] == "0x9010d07c":
                    i = int(data[-64:], 16)
                    return WORD(member(i)) if i < real else REVERT
            return REVERT
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
                       "targets": [{"target": T, "adminKeyScore": 10, "multisigScore": 0, "timelockScore": 0, "oracleAuthorityScore": 100, "crossExposureScore": 100,
                                    "compositeScore": 30, "lastUpdated": 1793000000, "stale": False}]}, f)
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


class TestTheAssembly(unittest.TestCase):
    def test_the_same_member_at_every_index_is_not_a_complete_list(self):
        am = ra.assemble_admin_members(B, 10, [WORD(B)] * 9)
        self.assertEqual(am["members"], [B])
        self.assertEqual(am["unread"], 9)
        st, cs = trust_of(am, 10)
        self.assertNotEqual(st, "VERIFIED")
        self.assertIn("admin_members_unread", cs)

    def test_a_member_written_in_another_case_is_the_same_member(self):
        am = ra.assemble_admin_members(B, 2, ["0x" + "00" * 12 + B[2:].upper()])
        self.assertEqual(am["unread"], 1)

    def test_an_implausible_count_is_not_a_count(self):
        am = ra.assemble_admin_members(B, 2 ** 255, [WORD(M(i)) for i in range(1, 10)])
        self.assertIsNone(am["total"])
        self.assertIsNone(am["unread"])
        self.assertIn("admin_members_unread", trust_of(am, "?")[1])

    def test_a_member_past_the_count_leaves_the_number_unknown(self):
        am = ra.assemble_admin_members(B, 1, [], beyond=WORD(M(1)))
        self.assertIsNone(am["unread"])
        self.assertNotEqual(trust_of(am, 1)[0], "VERIFIED")

    def test_no_answer_past_the_count_leaves_it_unconfirmed(self):
        self.assertIsNone(ra.assemble_admin_members(B, 1, [], beyond=None)["unread"])

    def test_the_probe_is_asked_only_within_the_bound(self):
        self.assertTrue(ra.admin_member_probe_call(T, 1)[1][0]["data"].endswith("%064x" % 1))
        self.assertIsNone(ra.admin_member_probe_call(T, 25))
        self.assertIsNone(ra.admin_member_probe_call(T, None))

    # controls
    def test_control_a_revert_past_the_count_confirms_it(self):
        am = ra.assemble_admin_members(B, 1, [], beyond="")
        self.assertEqual((am["total"], am["unread"]), (1, 0))
        self.assertEqual(trust_of(am, 1)[0], "VERIFIED")

    def test_control_the_kit_case_25_holders_bound_10_stays_partial(self):
        am = ra.assemble_admin_members(B, 25, ["0x" + "00" * 12 + "%040x" % i for i in range(2, 11)])
        self.assertEqual((am["read"], am["unread"]), (10, 15))
        w = Watch()
        try:
            w.edit("second_opinion.json", so_edit(B, admin_members=am))
            d = w.trust()
            self.assertEqual(status(d, B), "PARTIAL")
            self.assertIn("admin_members_unread", codes(d, B))
        finally:
            w.close()


class TestTheRealReader(unittest.TestCase):
    def test_a_count_lower_than_the_holders_is_caught(self):
        rec = reader_record(count=1, member=M, real=25)
        self.assertIsNone(rec["admin_members"]["unread"], rec["admin_members"])

    def test_the_same_member_at_every_index_is_caught(self):
        rec = reader_record(count=10, member=lambda i: M(0))
        self.assertEqual(rec["admin_members"]["unread"], 9, rec["admin_members"])

    def test_control_an_honest_single_holder_is_complete(self):
        rec = reader_record(count=1, member=M)
        self.assertEqual((rec["admin_members"]["total"], rec["admin_members"]["unread"]), (1, 0))


if __name__ == "__main__":
    unittest.main()
