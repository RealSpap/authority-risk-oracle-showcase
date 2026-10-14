"""Tests of scripts/agent_tools.py, of the four MCP tools built on it and of the LangChain and AgentKit wrappers (skipped when those libraries are not installed)."""
import json, os, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.join(HERE, "..", "..")
sys.path.insert(0, os.path.join(HERE, "..")); sys.path.insert(0, os.path.join(ROOT, "integrations"))
import agent_tools  # noqa: E402
import mcp_server  # noqa: E402

ORACLE = "0x9BF45734D09bC7CA39238e767B2af9AAc62a7f52"
A = "0x1f7d7550b1b028f7571e69a784071f0205fd2efa"   # fresh, 85
B = "0xde770c84fe66e063336b31737cfe9790f18c4087"   # stale, 32
C = "0x159a113e012593d9b3cc63ad45e30f0467e13ef3"   # composite not read
D = "0x1a3c9b1d2f0529d97f2afc5136cc23e58f1fd35b"   # a Safe on Base, 40
E = "0x3c3d99fd298f679dbc2cecd132b4ec4d0f5e6e72"   # admin not classifiable on Base, 50


def tgt(addr, comp, stale=False, **over):
    t = {"target": addr, "adminKeyScore": 80, "multisigScore": 100, "timelockScore": 75, "oracleAuthorityScore": 100, "crossExposureScore": 80, "compositeScore": comp, "lastUpdated": 1791852875, "methodologyHash": "0x" + "ab" * 32, "stale": stale, "previousComposite": comp}
    t.update(over); return t


def build(w, with_second_opinion=True, with_state=True):
    os.makedirs(os.path.join(w, "scores"), exist_ok=True)
    if not with_state: return
    json.dump({"name": "Robinhood Chain", "kind": "evm", "oracle": ORACLE, "rpc": "https://rpc.testnet.chain.robinhood.com/rpc", "block": 134282761, "maxStaleness": 777600, "readAt": 1791895264,
               "targets": [tgt(A, 85), tgt(B, 32, True), tgt(C, None, adminKeyScore=None)]}, open(os.path.join(w, "scores", "robinhood-chain.json"), "w"))
    json.dump({"name": "Base (Sepolia)", "kind": "evm", "oracle": "0x50840a7667baEa9D05ad4ae3dCeb384724b58720", "rpc": "https://sepolia.base.org", "block": 40000000, "maxStaleness": 777600, "readAt": 1791895264,
               "targets": [tgt(D, 40), tgt(E, 50)]}, open(os.path.join(w, "scores", "base-sepolia.json"), "w"))
    json.dump({"name": "Solana (devnet)", "kind": "solana", "oracle": "5VhiTAGLEViGgajhxPbzdWz7WLUAiRy42DY6qi6tYh4W", "block": 1, "readAt": 1791895264, "targets": [tgt("JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4", 71)]},
              open(os.path.join(w, "scores", "solana-devnet.json"), "w"))
    json.dump({"matched": {"robinhood:" + A: {"name": "Alpha Swap V3", "slug": "alpha-swap-v3", "tvl": 1000000}, "base:" + D: {"name": "Alpha Swap V3", "slug": "alpha-swap-v3", "tvl": 500000}}}, open(os.path.join(w, "tvl.json"), "w"))
    if with_second_opinion:
        json.dump({"results": [
            {"chain": "base", "target": D, "kind": "safe", "posture": "admin: Safe 2-of-3 of 3 plain keys; delay: none", "holder": "0xba6a06f8517e271db44540e68ba46beb4bc6155d", "path": "owner()", "threshold": 2, "owners": 3, "keys_to_act": 2, "keys_lost_to_freeze": 2,
             "self_delay_seconds": None, "modules": [], "guard": None, "since": "2026-10-10T06:54:09Z", "exposure": {"keys_to_move": 2, "react_hours": 0, "tvl_usd": 500000, "money_source": "protocol_tvl"}},
            {"chain": "base", "target": E, "kind": "unreadable", "why": "no admin slot answered"}]}, open(os.path.join(w, "second_opinion.json"), "w"))


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.W = os.path.join(self.tmp.name, "w"); build(self.W)

    def tearDown(self): self.tmp.cleanup()


class TestGetScore(Base):
    def test_a_tracked_contract_gives_its_numbers_and_a_replay_that_names_the_oracle_and_the_block(self):
        r = agent_tools.get_score(self.W, "Robinhood", A.upper().replace("0X", "0x"))   # case does not matter
        self.assertEqual((r["status"], r["composite"], r["stale"]), ("ok", 85, False)); self.assertEqual(r["sub_scores"]["multisig"], 100); self.assertEqual(r["not_read"], [])
        self.assertIn(ORACLE, r["replay"]["command"]); self.assertIn("--block 134282761", r["replay"]["command"]); self.assertIn(A, r["replay"]["command"]); self.assertIn("archive", r["replay"]["how_to_read"])
        self.assertEqual(r["last_pushed_utc"], "2026-10-13T00:54:35Z"); self.assertIn("testnet", r["testnet_note"])

    def test_a_stale_score_is_reported_as_stale_not_hidden(self):
        r = agent_tools.get_score(self.W, "robinhood", B); self.assertEqual((r["status"], r["composite"], r["stale"]), ("ok", 32, True))

    def test_a_score_that_was_not_read_is_none_and_the_status_says_so(self):
        r = agent_tools.get_score(self.W, "robinhood", C)
        self.assertEqual(r["status"], "not_read"); self.assertIsNone(r["composite"]); self.assertIsNone(r["sub_scores"]["admin_key"]); self.assertIn("composite", r["not_read"]); self.assertIn("admin_key", r["not_read"])

    def test_an_untracked_contract_or_chain_is_not_a_score_of_zero(self):
        r = agent_tools.get_score(self.W, "robinhood", "0x0000000000000000000000000000000000000001")
        self.assertEqual(r["status"], "not_tracked"); self.assertIsNone(r["composite"]); self.assertIn("says nothing about its safety", r["reason"])
        r = agent_tools.get_score(self.W, "dogechain", A); self.assertEqual(r["status"], "not_tracked"); self.assertIn("unknown chain", r["reason"])

    def test_no_state_folder_says_where_the_state_lives(self):
        with tempfile.TemporaryDirectory() as t:
            build(os.path.join(t, "w"), with_state=False)
            for fn in (lambda: agent_tools.get_score(os.path.join(t, "w"), "base", D), lambda: agent_tools.list_targets(os.path.join(t, "w")), lambda: agent_tools.who_controls(os.path.join(t, "w"), "base", D), lambda: agent_tools.check_protocol(os.path.join(t, "w"), "alpha")):
                r = fn(); self.assertEqual(r["status"], "not_read"); self.assertIn("watch-data", r["reason"]); self.assertNotIn("composite", r)

    def test_solana_has_no_cast_command_and_says_why(self):
        r = agent_tools.get_score(self.W, "solana", "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4"); self.assertEqual((r["status"], r["composite"]), ("ok", 71)); self.assertIsNone(r["replay"]); self.assertIn("score account", r["replay_note"])


class TestListTargets(Base):
    def test_filter_sort_and_the_unread_rows_are_counted_not_zeroed(self):
        r = agent_tools.list_targets(self.W, max_score=50)
        self.assertEqual([x["composite"] for x in r["rows"]], [32, 40, 50]); self.assertEqual(r["score_not_read_so_not_filtered"], 1); self.assertEqual(r["of"], 6); self.assertEqual(r["matched"], 3)
        self.assertNotIn(C, [x["address"] for x in r["rows"]])   # a score not read is not a score under 50

    def test_chain_stale_and_limit_filters(self):
        self.assertEqual(sorted(x["chain"] for x in agent_tools.list_targets(self.W, chain="base")["rows"]), ["base", "base"])
        self.assertEqual([x["address"] for x in agent_tools.list_targets(self.W, stale=True)["rows"]], [B])
        self.assertEqual(agent_tools.list_targets(self.W, limit=2)["returned"], 2); self.assertEqual(agent_tools.list_targets(self.W, limit=10 ** 6)["returned"], 5)   # the sixth row has no score
        self.assertEqual(agent_tools.list_targets(self.W, chain="dogechain")["status"], "not_read")


class TestWhoControls(Base):
    def test_a_classified_admin(self):
        r = agent_tools.who_controls(self.W, "base", D)
        self.assertEqual((r["status"], r["admin_kind"], r["threshold"], r["owners"], r["keys_to_act"]), ("ok", "safe", 2, 3, 2)); self.assertEqual(r["delay_summary"], "none"); self.assertEqual(r["to_move_the_money"]["keys"], 2)
        self.assertEqual(r["not_read"], [])

    def test_an_admin_the_reader_could_not_classify_is_not_read_not_ok(self):
        r = agent_tools.who_controls(self.W, "base", E); self.assertEqual(r["status"], "not_read"); self.assertEqual(r["admin_kind"], "unreadable"); self.assertIsNone(r["threshold"]); self.assertIn("no admin slot", r["unreadable_reason"]); self.assertIn("threshold", r["not_read"])

    def test_missing_independent_reader_or_missing_record_or_untracked(self):
        with tempfile.TemporaryDirectory() as t:
            w = os.path.join(t, "w"); build(w, with_second_opinion=False)
            self.assertEqual(agent_tools.who_controls(w, "base", D)["status"], "not_read")
        self.assertEqual(agent_tools.who_controls(self.W, "robinhood", A)["status"], "not_read")   # tracked, but the reader has no record of it
        self.assertEqual(agent_tools.who_controls(self.W, "base", "0x0000000000000000000000000000000000000002")["status"], "not_tracked")


class TestCheckProtocol(Base):
    def test_verdicts(self):
        r = agent_tools.check_protocol(self.W, "alpha-swap-v3", 30)
        self.assertEqual(r["status"], "ok"); self.assertEqual(r["contracts"], 2); self.assertEqual(r["weakest_composite"], 40); self.assertEqual(r["verdict"], "ok")
        self.assertEqual(agent_tools.check_protocol(self.W, "alpha-swap-v3", 41)["verdict"], "fail")   # the weakest is under the minimum
        self.assertEqual(agent_tools.check_protocol(self.W, "nothing-like-this", 0)["status"], "not_tracked")

    def test_a_stale_contract_fails_even_when_the_numbers_are_high(self):
        json.dump({"matched": {"robinhood:" + A: {"name": "Alpha", "slug": "alpha", "tvl": 1}, "robinhood:" + B: {"name": "Alpha", "slug": "alpha", "tvl": 1}}}, open(os.path.join(self.W, "tvl.json"), "w"))
        r = agent_tools.check_protocol(self.W, "alpha", 0); self.assertEqual(r["verdict"], "fail"); self.assertEqual(r["stale_contracts"], 1)

    def test_a_contract_whose_score_was_not_read_is_not_a_pass(self):
        json.dump({"matched": {"robinhood:" + A: {"name": "Beta", "slug": "beta", "tvl": 1}, "robinhood:" + C: {"name": "Beta", "slug": "beta", "tvl": 1}}}, open(os.path.join(self.W, "tvl.json"), "w"))
        r = agent_tools.check_protocol(self.W, "beta", 10); self.assertEqual(r["verdict"], "unread_part"); self.assertEqual(r["composite_not_read_on"], 1)


class TestNothingIsZeroWhenNotRead(Base):
    def test_every_answer_has_null_where_the_file_has_nothing(self):
        r = agent_tools.get_score(self.W, "robinhood", C)
        self.assertEqual([k for k, v in r["sub_scores"].items() if v == 0], [])
        json.dump({"name": "Robinhood Chain", "kind": "evm", "targets": [{"target": A}]}, open(os.path.join(self.W, "scores", "robinhood-chain.json"), "w"))
        r = agent_tools.get_score(self.W, "robinhood", A); self.assertEqual(r["status"], "not_read"); self.assertIsNone(r["composite"]); self.assertIsNone(r["stale"]); self.assertIsNone(r["last_pushed_utc"]); self.assertIsNone(r["oracle"]["block"]); self.assertIsNone(r["replay"])


class TestMcpTools(Base):
    def call(self, name, args):
        out = mcp_server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": args}}, self.W); return out

    def test_the_four_tools_are_listed_read_only_and_answer_json(self):
        names = [t["name"] for t in mcp_server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, self.W)["result"]["tools"]]
        for n in ("getScore", "listTargets", "whoControls", "checkProtocol"): self.assertIn(n, names)
        for n, args in (("getScore", {"chain": "base", "address": D}), ("listTargets", {"max_score": 50}), ("whoControls", {"chain": "base", "address": D}), ("checkProtocol", {"protocol": "alpha-swap-v3", "min_score": 30})):
            res = self.call(n, args)["result"]; self.assertFalse(res["isError"]); self.assertIn("status", json.loads(res["content"][0]["text"])); self.assertIn("DATA", res["content"][1]["text"])   # the data notice travels with every answer

    def test_bad_arguments_are_refused_before_any_file_is_read(self):
        self.assertIn("error", self.call("getScore", {"chain": "base"})); self.assertIn("error", self.call("listTargets", {"max_score": 101})); self.assertIn("error", self.call("checkProtocol", {"protocol": "x", "path": "/etc/passwd"}))


try:
    import langchain_core  # noqa: F401
    HAS_LC = True
except ImportError:
    HAS_LC = False
try:
    import coinbase_agentkit  # noqa: F401
    HAS_AK = True
except ImportError:
    HAS_AK = False


@unittest.skipUnless(HAS_LC, "langchain-core is not installed")
class TestLangChain(Base):
    def test_four_tools_with_schemas_that_answer_json_strings(self):
        import langchain_authority_risk as L
        tools = {t.name: t for t in L.authority_risk_tools(self.W)}
        self.assertEqual(sorted(tools), ["check_protocol_authority", "get_authority_score", "list_authority_targets", "who_controls_contract"])
        self.assertEqual(json.loads(tools["get_authority_score"].invoke({"chain": "robinhood", "address": A}))["composite"], 85)
        self.assertEqual(json.loads(tools["list_authority_targets"].invoke({"max_score": 40}))["matched"], 2)
        self.assertEqual(json.loads(tools["who_controls_contract"].invoke({"chain": "base", "address": E}))["status"], "not_read")
        self.assertEqual(json.loads(tools["check_protocol_authority"].invoke({"protocol": "alpha-swap-v3"}))["verdict"], "ok")
        with self.assertRaises(Exception): tools["get_authority_score"].invoke({"chain": "base"})   # a missing argument is refused by the schema


@unittest.skipUnless(HAS_AK, "coinbase-agentkit is not installed")
class TestAgentKit(Base):
    def test_four_actions_that_need_no_wallet(self):
        import agentkit_authority_risk as K
        from unittest import mock
        posts = []   # AgentKit itself reports each action run to an analytics endpoint of its own; the test keeps that off the network and counts it
        patcher = mock.patch("coinbase_agentkit.analytics.send_analytics_event.requests.post", side_effect=lambda *a, **k: posts.append(a) or mock.Mock(raise_for_status=lambda: None)); patcher.start(); self.addCleanup(patcher.stop)
        p = K.authority_risk_action_provider(self.W); acts = {a.name.split("_", 1)[1]: a for a in p.get_actions(object())}
        self.assertEqual(sorted(acts), ["check_protocol_authority", "get_authority_score", "list_authority_targets", "who_controls_contract"])
        self.assertEqual(json.loads(acts["get_authority_score"].invoke({"chain": "robinhood", "address": A}))["composite"], 85)
        self.assertEqual(json.loads(acts["check_protocol_authority"].invoke({"protocol": "alpha-swap-v3", "min_score": 30}))["verdict"], "ok")
        self.assertTrue(p.supports_network(object()))


if __name__ == "__main__":
    unittest.main()
