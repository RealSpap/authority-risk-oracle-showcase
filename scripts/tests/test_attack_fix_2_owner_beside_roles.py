"""A target read through owner() or admin() that is also an enumerable AccessControl: the holders of its DEFAULT_ADMIN_ROLE must be read too.

Weakness class: the independent reader followed the first getter that answered (owner(), admin()) and only asked for the admin-role holders of a target
with none of those. A contract that combines both kinds of control could then show a strong holder through owner() while the power sits with the
holders of the role, which were never read, and the trust rule had nothing to degrade.

The real second_opinion.main() runs here against an in-process fake node (only `_post` is replaced), then the trust rule reads the record it wrote.
No network.
"""
import contextlib, io, json, os, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.abspath(os.path.join(HERE, ".."))
for p in (SCRIPTS, os.path.join(SCRIPTS, "lib"), os.path.join(SCRIPTS, "lib", "tests")):
    if p not in sys.path:
        sys.path.insert(0, p)
import second_opinion as so  # noqa: E402
from trust_support import A, Watch, status, codes  # noqa: E402

T = "0x" + "aa" * 19 + "01"            # the target
S = "0x" + "5a" * 19 + "fe"            # a Safe 3-of-5, answered by owner()
OWNERS = ["0x%040x" % (0xb0 + i) for i in range(5)]
W = lambda v: "0x%064x" % v
WA = lambda a: "0x" + "00" * 12 + a[2:]
REVERT = {"code": 3, "message": "execution reverted"}
NO_ANSWER = {"code": -32603, "message": "internal error"}   # what a node says when it did not run the call: not a revert, not an answer
SI, COUNT, MEMBER = "0x01ffc9a7", "0xca15c873", "0x9010d07c"
AC_SELECTORS = ("0x01ffc9a7", "0xca15c873", "0x9010d07c")


def world(has_owner=True, access_control=True, count=25, members=None, calls=None, over=None, authority=None):
    """A fake node. `members(i)` is the address of role member i (default: 25 distinct plain keys). `over` maps a selector (on the target) to the answer
    to give instead: a word, REVERT, NO_ANSWER or a string of any shape. `authority` is the address the target's authority() answers."""
    over = over or {}
    members = members or (lambda i: "0x%040x" % (0xe100 + i))

    def answer(method, params):
        if method == "eth_blockNumber": return "0x100"
        if method == "eth_getLogs": return []
        if method == "eth_getTransactionCount": return "0x1"
        if method == "eth_getStorageAt": return W(0)
        if method == "eth_getCode": return "0x6080604052" if params[0].lower() in (T, S) else "0x"
        if method == "eth_call":
            to, data = params[0]["to"].lower(), params[0]["data"]
            sel = data[:10]
            if calls is not None and to == T: calls.append(sel)
            if to == T:
                if sel in over: return over[sel]
                if sel == so.SEL["authority"] and authority: return WA(authority)
                if sel == so.SEL["owner"] and has_owner: return WA(S)
                if access_control and sel == "0x01ffc9a7": return W(1)
                if access_control and sel == "0xca15c873": return W(count)
                if access_control and sel == "0x9010d07c":   # an enumerable set reverts past its length
                    i = int(data[-64:], 16)
                    return WA(members(i)) if i < count else REVERT
                return REVERT
            if to == S:
                if sel == so.SEL["getThreshold"]: return W(3)
                if sel == so.SEL["getOwners"]: return "0x" + "%064x" % 0x20 + "%064x" % 5 + "".join("%064x" % int(o, 16) for o in OWNERS)
                if sel == "0xcc2f8452": return "0x" + "%064x" % 0x40 + "%064x" % 1 + "%064x" % 0
                return REVERT
            return REVERT
        return None

    def fake_post(url, payload):
        one = isinstance(payload, dict)
        out = []
        for p in ([payload] if one else payload):
            r = answer(p["method"], p["params"])
            out.append({"jsonrpc": "2.0", "id": p["id"], **({"error": r} if isinstance(r, dict) and "code" in r else {"result": r})})
        return out[0] if one else out
    return fake_post


def read(score=50, **kw):
    with tempfile.TemporaryDirectory() as tmp:
        os.makedirs(os.path.join(tmp, "scores"))
        with open(os.path.join(tmp, "scores", "ethereum-l1-sepolia.json"), "w") as f:
            json.dump({"name": "Ethereum L1 (Sepolia)", "kind": "evm", "oracle": "0x" + "0f" * 20, "rpc": "https://x", "block": 1, "readAt": 1793000000,
                       "targets": [{"target": T, "adminKeyScore": score, "multisigScore": 60, "timelockScore": 0, "oracleAuthorityScore": 100, "crossExposureScore": 100,
                                    "compositeScore": 50, "lastUpdated": 1793000000, "stale": False}]}, f)
        none = os.path.join(tmp, "none.json")
        orig, argv = so._post, sys.argv
        so._post = world(**kw)
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


def trust_of(rec):
    r = dict(rec, chain="robinhood", target=A)
    w = Watch()
    try:
        w.edit("second_opinion.json", lambda d: d.update(results=[r if x["target"] == A else x for x in d["results"]]))
        d = w.trust()
        return status(d, A), codes(d, A)
    finally:
        w.close()


class TestRoleHoldersBesideAGetter(unittest.TestCase):
    def test_role_holders_of_a_target_read_through_owner_are_read(self):
        rec = read()
        self.assertEqual(rec.get("path"), "owner()")                     # the getter is still the holder that is followed
        self.assertEqual(rec.get("kind"), "safe")
        am = rec.get("admin_members")
        self.assertIsInstance(am, dict, rec)
        self.assertEqual(am.get("total"), 25)
        self.assertGreater(am.get("unread"), 0)
        self.assertGreater((rec.get("admin_members_gap") or {}).get("not_weighed", 0), 0)

    def test_the_trust_rule_no_longer_says_verified(self):
        st, cs = trust_of(read())
        self.assertNotEqual(st, "VERIFIED", cs)
        self.assertIn("admin_members_unread", cs)
        self.assertIn("admin_members_not_weighed", cs)

    def test_a_role_answered_with_the_same_member_at_every_index_is_not_complete(self):
        rec = read(count=10, members=lambda i: "0x%040x" % 0xe100)
        st, cs = trust_of(rec)
        self.assertNotEqual(st, "VERIFIED", cs)

    def test_the_getter_targets_get_the_probes_once_authority_included(self):
        calls = []
        read(access_control=False, calls=calls)
        self.assertEqual(calls.count(SI), 1)
        self.assertEqual(calls.count(so.SEL["authority"]), 1)   # second round: authority() beside owner() is a second controller

    # ---- second round: a probe that did not answer is not "no holder" ---------------------------------------------------------------------
    def assert_not_read(self, rec, what):
        st, cs = trust_of(rec)
        self.assertNotEqual(st, "VERIFIED", (what, cs))
        self.assertIn("admin_members_unread", cs, what)
        self.assertIsNone((rec.get("admin_members") or {}).get("total"), what)

    def test_a_count_the_node_did_not_answer_is_not_read(self):
        self.assert_not_read(read(over={COUNT: NO_ANSWER}), "getRoleMemberCount: no answer")

    def test_supports_interface_the_node_did_not_answer_is_not_read(self):
        self.assert_not_read(read(over={SI: NO_ANSWER}), "supportsInterface: no answer")

    def test_member_zero_the_node_did_not_answer_is_not_read(self):
        self.assert_not_read(read(over={MEMBER: NO_ANSWER}), "getRoleMember: no answer")

    def test_a_count_too_short_to_be_a_word_is_not_read(self):
        self.assert_not_read(read(over={COUNT: "0x19"}), "getRoleMemberCount: 1 byte")

    def test_a_count_above_zero_with_no_member_zero_is_not_read(self):
        self.assert_not_read(read(over={MEMBER: REVERT}), "count 25, member 0 reverts")

    # ---- second round: the set is judged by the count and member 0, not by supportsInterface --------------------------------------------------
    def test_supports_interface_answering_zero_beside_an_enumerable_role_is_not_verified(self):
        rec = read(over={SI: W(0)})
        st, cs = trust_of(rec)
        self.assertNotEqual(st, "VERIFIED", cs)
        self.assertEqual((rec.get("admin_members") or {}).get("total"), 25)

    def test_no_erc165_at_all_beside_an_enumerable_role_is_not_verified(self):
        rec = read(over={SI: REVERT})
        st, cs = trust_of(rec)
        self.assertNotEqual(st, "VERIFIED", cs)
        self.assertEqual((rec.get("admin_members") or {}).get("total"), 25)

    def test_a_count_of_zero_while_member_zero_answers_is_not_verified(self):
        rec = read(count=25, over={COUNT: W(0)})
        self.assert_not_read(rec, "count 0, members answer")

    # ---- second round: authority() beside owner() ------------------------------------------------------------------------------------------------
    def test_an_access_manager_named_by_authority_beside_owner_is_not_verified(self):
        manager = "0x" + "9c" * 20
        rec = read(access_control=False, authority=manager)
        st, cs = trust_of(rec)
        self.assertNotEqual(st, "VERIFIED", cs)
        self.assertIn("admin_members_not_weighed", cs)
        members = (rec.get("admin_members") or {}).get("members", [])
        self.assertEqual(len(members), 1, members)   # shortened like any key the reader found to be plain (the fake node has no code there)
        self.assertTrue(members[0].startswith(manager[:6]) and members[0].endswith(manager[-4:]), members)

    def test_beside_role_set_reads_each_answer_shape(self):
        w1 = lambda a: "0x" + "00" * 12 + a[2:]
        m = "0x" + "e1" * 20
        self.assertEqual(so.beside_role_set(W(1), W(2), w1(m), "", S), (m, 2, None, None))
        self.assertEqual(so.beside_role_set("", "", "", "", S), (None, None, None, None))                                    # a contract that reverts all of them: no role set
        self.assertEqual(so.beside_role_set("", W(0), "", "", S), (None, None, None, None))                                  # an empty enumerable set
        self.assertIsNotNone(so.beside_role_set(None, W(2), w1(m), "", S)[3])                                                  # no answer to a probe
        self.assertIsNotNone(so.beside_role_set(W(1), "0x02", w1(m), "", S)[3])                                                # too short
        self.assertIsNotNone(so.beside_role_set(W(1), W(0), w1(m), "", S)[3])                                                  # count 0, member 0 answers
        self.assertIsNotNone(so.beside_role_set(W(0), W(3), "", "", S)[3])                                                     # count 3, no member 0
        self.assertEqual(so.beside_role_set(W(0), W(3), w1(m), "", S)[:2], (m, 3))                                           # supportsInterface 0 changes nothing
        self.assertEqual(so.beside_role_set("", "", "", w1(S), S)[2], None)                                                    # authority() = the getter's holder adds nothing

    # controls
    def test_control_a_getter_target_that_is_not_access_control_stays_verified(self):
        rec = read(access_control=False)
        self.assertNotIn("admin_members", rec)
        st, cs = trust_of(rec)
        self.assertEqual(st, "VERIFIED", cs)

    def test_control_a_single_role_holder_that_is_the_getter_holder_stays_verified(self):
        rec = read(count=1, members=lambda i: S)
        self.assertFalse((rec.get("admin_members_gap") or {}).get("not_weighed"))
        st, cs = trust_of(rec)
        self.assertEqual(st, "VERIFIED", cs)

    def test_control_a_contract_that_reverts_every_probe_stays_verified(self):
        rec = read(access_control=False, over={SI: REVERT, COUNT: REVERT, MEMBER: REVERT, so.SEL["authority"]: REVERT})
        st, cs = trust_of(rec)
        self.assertEqual(st, "VERIFIED", cs)

    def test_control_an_empty_enumerable_role_set_stays_verified(self):
        rec = read(count=0)   # count 0 and member 0 reverts: nobody holds the role
        st, cs = trust_of(rec)
        self.assertEqual(st, "VERIFIED", cs)

    def test_control_authority_naming_the_getter_holder_adds_nothing(self):
        rec = read(access_control=False, authority=S)
        st, cs = trust_of(rec)
        self.assertEqual(st, "VERIFIED", cs)

    def test_control_a_roles_only_target_is_read_as_before(self):
        rec = read(has_owner=False)
        self.assertTrue(str(rec.get("path")).startswith("DEFAULT_ADMIN_ROLE member 1 of 25"), rec.get("path"))
        st, cs = trust_of(rec)
        self.assertIn("admin_members_unread", cs)


if __name__ == "__main__":
    unittest.main()
