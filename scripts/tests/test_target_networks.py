"""The network of the oracle (test) and of each target (mainnet) is READ and written in the Watch record. No network: the RPC is replaced.
Each case is a way the file could say "mainnet" without having read it: a mainnet RPC that answers a test chain, a node that fails, an address without code,
the one testnet target, a rollup contract that lives on the parent chain, a native of HyperCore."""
import json, os, re, sys, unittest, warnings

warnings.simplefilter("ignore", ResourceWarning)
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
import target_networks as tn  # noqa: E402
import validate_schemas  # noqa: E402

ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
A1, A2, A3 = "0x" + "11" * 20, "0x" + "22" * 20, "0x" + "33" * 20
BASE_ORACLE = "https://sepolia.base.org"
MAIN_BASE = {"https://base-rpc.publicnode.com": 8453, "https://gateway.tenderly.co/public/base": 8453, BASE_ORACLE: 84532}


def fake(chains, codes=None, fail=(), heads=None, log=None):
    """chains: url -> chain id ; codes: (host or '*', lower case address) -> '0x...' ; fail: urls that raise ; heads: url -> block number ; log: list that receives (url, method, params)"""
    def rpc(url, calls, tries=1):
        if url in fail: raise RuntimeError("down")
        out = []
        for m, p in calls:
            if log is not None: log.append((url, m, p))
            if m == "eth_chainId": out.append(hex(chains[url]))
            elif m == "eth_blockNumber": out.append(hex((heads or {}).get(url, 26400691)))
            elif m == "eth_getBlockByNumber": out.append({"hash": "0x" + "ab" * 32, "timestamp": hex(1762970000)})
            elif m == "eth_getCode": out.append((codes or {}).get((url.split("/")[2], p[0].lower())) or (codes or {}).get(("*", p[0].lower())) or "0x6001")
            else: raise AssertionError(m)
        return out
    return rpc


class T(unittest.TestCase):
    def test_a_clean_read_says_both_networks_and_names_the_block(self):
        mod, per = tn.evm_fields("Base (Sepolia)", BASE_ORACLE, [{"target": A1}, {"target": A2}], fake(MAIN_BASE))
        self.assertEqual((mod["oracle_network"], mod["oracle_chain_id"]), ("Base Sepolia (testnet)", 84532))
        self.assertEqual((mod["target_network"], mod["target_chain_id"], mod["target_block"], mod["target_rpc"]), ("Base mainnet", 8453, 26400691, "base-rpc.publicnode.com"))
        self.assertEqual(mod["target_block_hash"], "0x" + "ab" * 32); self.assertEqual(mod["target_block_time"], 1762970000)
        self.assertIn("not the block the scorer read", mod["target_block_kind"])
        self.assertEqual(per[A1], {"target_network": "Base mainnet", "target_chain_id": 8453, "target_network_read": "code at block 26400691 on base-rpc.publicnode.com", "target_read_block": 26400691, "code_on_target_network": True})

    def test_the_code_and_the_block_hash_are_read_at_the_block_that_is_named(self):
        log = []
        mod, per = tn.evm_fields("Base (Sepolia)", BASE_ORACLE, [{"target": A1}, {"target": A2}], fake(MAIN_BASE, heads={"https://base-rpc.publicnode.com": 4242}, log=log))
        self.assertEqual(mod["target_block"], 4242)
        blocks = [p for u, m, p in log if m == "eth_getBlockByNumber"]; codes = [p for u, m, p in log if m == "eth_getCode"]
        self.assertEqual(blocks, [[hex(4242), False]], "the hash and the time are those of the block number named, not of `latest`")
        self.assertEqual(sorted(c[1] for c in codes), [hex(4242)] * 2, "every code is read at the named block, never at `latest`")

    def test_a_mainnet_rpc_that_answers_a_test_chain_is_refused(self):
        chains = dict(MAIN_BASE); chains["https://base-rpc.publicnode.com"] = 84532; chains["https://gateway.tenderly.co/public/base"] = 84532
        mod, per = tn.evm_fields("Base (Sepolia)", BASE_ORACLE, [{"target": A1}], fake(chains))
        self.assertIsNone(mod["target_chain_id"]); self.assertIsNone(mod["target_block"]); self.assertIn("expected 8453", mod["target_read_error"])
        self.assertTrue(per[A1]["target_network"].startswith("unplaced")); self.assertIsNone(per[A1]["target_chain_id"])

    def test_the_second_node_serves_when_the_first_fails(self):
        mod, per = tn.evm_fields("Base (Sepolia)", BASE_ORACLE, [{"target": A1}], fake(MAIN_BASE, fail=("https://base-rpc.publicnode.com",)))
        self.assertEqual(mod["target_rpc"], "gateway.tenderly.co"); self.assertEqual(per[A1]["target_network"], "Base mainnet")

    def test_every_node_down_is_a_cause_never_a_zero_or_a_mainnet(self):
        mod, per = tn.evm_fields("Base (Sepolia)", BASE_ORACLE, [{"target": A1}], fake(MAIN_BASE, fail=tuple(MAIN_BASE)))
        self.assertIsNone(mod["target_block"]); self.assertIsNone(mod["target_chain_id"]); self.assertTrue(mod["target_read_error"]); self.assertIsNone(mod["oracle_chain_id"]); self.assertTrue(mod["oracle_chain_read_error"])
        self.assertEqual((mod["oracle_network"], mod["target_network"]), ("unplaced (read impossible)", "unplaced (read impossible)"), "no chain id read, no network name")
        self.assertEqual(per[A1]["target_network"], "unplaced (read impossible)"); self.assertIsNone(per[A1]["code_on_target_network"])

    def test_an_address_without_code_on_the_target_network_is_not_established(self):
        mod, per = tn.evm_fields("Base (Sepolia)", BASE_ORACLE, [{"target": A1}, {"target": A2}], fake(MAIN_BASE, codes={("*", A2): "0x"}))
        self.assertEqual(per[A1]["target_network"], "Base mainnet"); self.assertFalse(per[A2]["code_on_target_network"]); self.assertIsNone(per[A2]["target_chain_id"])
        self.assertTrue(per[A2]["target_network"].startswith("unplaced (no code"))

    def test_an_oracle_rpc_on_another_chain_is_said(self):
        chains = dict(MAIN_BASE); chains[BASE_ORACLE] = 8453   # the oracle RPC would be MAINNET: the record says so
        mod, _ = tn.evm_fields("Base (Sepolia)", BASE_ORACLE, [{"target": A1}], fake(chains))
        self.assertIn("expected 84532", mod["oracle_chain_read_error"]); self.assertEqual(mod["oracle_network"], "unplaced (read impossible)", "the oracle RPC is not the test network: no name")

    def test_the_only_testnet_target_has_its_code_read_on_the_test_network(self):
        chains = {"https://rpc.moderato.tempo.xyz": 42431, "https://rpc.tempo.xyz": 4217, "https://tempo-rpc.publicnode.com": 4217}
        mod, per = tn.evm_fields("Tempo (Moderato)", "https://rpc.moderato.tempo.xyz", [{"target": tn.HELD}, {"target": A1}], fake(chains, heads={"https://rpc.moderato.tempo.xyz": 777}))
        h = per[tn.HELD]
        self.assertEqual((h["target_network"], h["target_chain_id"], h["code_on_target_network"], h["target_read_block"]), ("Tempo Moderato (testnet)", 42431, True, 777))
        self.assertIn("rpc.moderato.tempo.xyz (chain 42431)", h["target_network_read"])
        self.assertEqual(per[A1]["target_network"], "Tempo mainnet")
        chains2 = dict(chains)
        chains3 = dict(chains); chains3["https://rpc.moderato.tempo.xyz"] = 4217   # the "testnet" RPC answers mainnet: Held is not placed on a test network by a constant
        _, per3h = tn.evm_fields("Tempo (Moderato)", "https://rpc.moderato.tempo.xyz", [{"target": tn.HELD}], fake(chains3))
        self.assertTrue(per3h[tn.HELD]["target_network"].startswith("unplaced")); self.assertIsNone(per3h[tn.HELD]["target_chain_id"])
        _, per2 = tn.evm_fields("Tempo (Moderato)", "https://rpc.moderato.tempo.xyz", [{"target": tn.HELD}], fake(chains2, codes={("rpc.moderato.tempo.xyz", tn.HELD): "0x"}))
        self.assertTrue(per2[tn.HELD]["target_network"].startswith("unplaced")); self.assertIsNone(per2[tn.HELD]["target_chain_id"])

    def test_a_rollup_contract_without_code_on_the_rollup_is_looked_up_on_the_parent_chain(self):
        chains = {"https://rpc.testnet.chain.robinhood.com/rpc": 46630, "https://rpc.mainnet.chain.robinhood.com": 4663, "https://ethereum-rpc.publicnode.com": 1, "https://gateway.tenderly.co/public/mainnet": 1}
        codes = {("rpc.mainnet.chain.robinhood.com", A2): "0x"}
        mod, per = tn.evm_fields("Robinhood Chain", "https://rpc.testnet.chain.robinhood.com/rpc", [{"target": A1}, {"target": A2}], fake(chains, codes=codes, heads={"https://ethereum-rpc.publicnode.com": 555}))
        self.assertEqual(per[A1]["target_network"], "Robinhood Chain mainnet")
        self.assertEqual((per[A2]["target_network"], per[A2]["target_chain_id"], per[A2]["target_read_block"]), ("Ethereum mainnet", 1, 555))
        self.assertTrue(per[A2]["code_on_target_network"], "the code exists on the network the target was placed on (Ethereum)")
        codes3 = {("*", A2): "0x"}
        _, per3 = tn.evm_fields("Robinhood Chain", "https://rpc.testnet.chain.robinhood.com/rpc", [{"target": A2}], fake(chains, codes=codes3))
        self.assertTrue(per3[A2]["target_network"].startswith("unplaced"), "no code on either network: unplaced")

    def test_a_hyperliquid_native_is_placed_by_the_info_api_and_has_no_chain_id(self):
        chains = {"https://rpc.hyperliquid-testnet.xyz/evm": 998, "https://rpc.hyperliquid.xyz/evm": 999, "https://arb1.arbitrum.io/rpc": 42161, "https://arbitrum-one-rpc.publicnode.com": 42161}
        codes = {("rpc.hyperliquid.xyz", A2): "0x", ("rpc.hyperliquid.xyz", A3): "0x", ("arb1.arbitrum.io", A2): "0x", ("arb1.arbitrum.io", A3): "0x"}
        def post(url, body): return {"role": "vault"} if body["user"] == A2 else {"role": "missing"}
        mod, per = tn.evm_fields("Hyperliquid (HyperEVM)", "https://rpc.hyperliquid-testnet.xyz/evm", [{"target": A1}, {"target": A2}, {"target": A3}], fake(chains, codes=codes), post_json=post)
        self.assertEqual(per[A1]["target_network"], "HyperEVM mainnet")
        self.assertEqual((per[A2]["target_network"], per[A2]["target_chain_id"]), ("Hyperliquid mainnet (HyperCore)", None)); self.assertIn("role=vault", per[A2]["target_network_read"])
        self.assertIsNone(per[A2]["target_read_block"], "a HyperCore object is not read at a block"); self.assertIsNone(per[A2]["code_on_target_network"])
        self.assertTrue(per[A3]["target_network"].startswith("unplaced"), "role missing: not on HyperCore")
        _, per4 = tn.evm_fields("Hyperliquid (HyperEVM)", "https://rpc.hyperliquid-testnet.xyz/evm", [{"target": A2}], fake(chains, codes=codes))
        self.assertTrue(per4[A2]["target_network"].startswith("unplaced"), "without the API client nothing is guessed")
        def broken(url, body): raise RuntimeError("429")
        _, per5 = tn.evm_fields("Hyperliquid (HyperEVM)", "https://rpc.hyperliquid-testnet.xyz/evm", [{"target": A2}], fake(chains, codes=codes), post_json=broken)
        self.assertTrue(per5[A2]["target_network"].startswith("unplaced")); self.assertIn("failed", per5[A2]["target_network_read"])

    def test_the_derived_keys_are_recomputed_and_placed_by_the_object_they_stand_for(self):
        from web3 import Web3
        for addr, (string, kind, dex) in tn.DERIVED_KEYS.items():
            self.assertEqual("0x" + Web3.keccak(text=string).hex()[-40:], addr, string)
        L1, PARA, MKTS = list(tn.DERIVED_KEYS)
        chains = {"https://rpc.hyperliquid-testnet.xyz/evm": 998, "https://rpc.hyperliquid.xyz/evm": 999, "https://arb1.arbitrum.io/rpc": 42161, "https://arbitrum-one-rpc.publicnode.com": 42161}
        codes = {("*", L1): "0x", ("*", PARA): "0x", ("*", MKTS): "0x"}
        def post(url, body):
            return [{"name": "xyz"}, {"name": "para"}] if body["type"] == "perpDexs" else [{"validator": "v"}] if body["type"] == "validatorSummaries" else {"role": "missing"}
        mod, per = tn.evm_fields("Hyperliquid (HyperEVM)", "https://rpc.hyperliquid-testnet.xyz/evm", [{"target": L1}, {"target": PARA}, {"target": MKTS}], fake(chains, codes=codes), post_json=post)
        self.assertEqual(per[L1]["target_network"], "Hyperliquid mainnet (HyperCore)"); self.assertIn("not an account", per[L1]["target_network_read"]); self.assertIn("validatorSummaries", per[L1]["target_network_read"])
        self.assertEqual(per[PARA]["target_network"], "Hyperliquid mainnet (HyperCore)"); self.assertIn("dex para is listed by perpDexs", per[PARA]["target_network_read"])
        self.assertTrue(per[MKTS]["target_network"].startswith("unplaced"), "dex mkts is not in the list: unplaced")
        self.assertIsNone(per[L1]["target_chain_id"]); self.assertIsNone(per[L1]["target_read_block"])
        def post_empty(url, body): return [] if body["type"] == "validatorSummaries" else [{"name": "para"}]
        _, per2 = tn.evm_fields("Hyperliquid (HyperEVM)", "https://rpc.hyperliquid-testnet.xyz/evm", [{"target": L1}], fake(chains, codes=codes), post_json=post_empty)
        self.assertTrue(per2[L1]["target_network"].startswith("unplaced"), "an empty validator list proves nothing")
        def post_junk(url, body): return [{"x": 1}] if body["type"] == "validatorSummaries" else []
        _, per3 = tn.evm_fields("Hyperliquid (HyperEVM)", "https://rpc.hyperliquid-testnet.xyz/evm", [{"target": L1}], fake(chains, codes=codes), post_json=post_junk)
        self.assertTrue(per3[L1]["target_network"].startswith("unplaced"), "an answer without validators proves nothing")

    def test_an_oracle_without_a_table_entry_is_an_error_not_a_default(self):
        with self.assertRaises(KeyError): tn.evm_fields("A new oracle", BASE_ORACLE, [], fake(MAIN_BASE))

    def test_apply_gives_every_target_a_network(self):
        doc = {"targets": [{"target": A1}, {"target": A3}]}
        tn.apply(doc, {"target_network": "Base mainnet"}, {A1: {"target_network": "Base mainnet", "target_chain_id": 8453}})
        self.assertEqual(doc["targets"][0]["target_network"], "Base mainnet"); self.assertTrue(doc["targets"][1]["target_network"].startswith("unplaced (target not read"))

    def test_solana_the_genesis_names_the_network(self):
        G = tn.GENESIS
        def sol(url, m, p):
            if m == "getGenesisHash": return G["Solana mainnet-beta"]
            if m == "getSlot": return 4242
            if m == "getMultipleAccounts": return {"value": [{"lamports": 1}, None]}
        mod, per = tn.solana_fields(["Prog1", "Prog2"], sol)
        self.assertEqual((mod["target_network"], mod["target_block"], mod["target_genesis"]), ("Solana mainnet-beta", 4242, G["Solana mainnet-beta"]))
        self.assertEqual(per["Prog1"]["target_network"], "Solana mainnet-beta"); self.assertIn("genesis 5eykt4Us", per["Prog1"]["target_network_read"])
        self.assertTrue(per["Prog2"]["target_network"].startswith("unplaced (no account"))
        dev = lambda url, m, p: G["Solana devnet"] if m == "getGenesisHash" else None   # the "mainnet" RPC answers devnet
        mod, per = tn.solana_fields(["Prog1"], dev)
        self.assertIsNone(mod["target_block"]); self.assertIn("expected mainnet-beta", mod["target_read_error"]); self.assertEqual(per["Prog1"]["target_network"], "unplaced (read impossible)")

    def test_every_oracle_of_the_watch_has_a_network_and_the_chain_ids_are_the_ones_of_the_push_scripts(self):
        sys.path.insert(0, os.path.join(ROOT, "scripts"))
        from live_target_counts import ORACLES
        self.assertEqual(sorted(n for n, _, _ in ORACLES), sorted(tn.TABLE), "a published oracle without a network, or a network without an oracle")
        scripts = {"Robinhood Chain": "scripts/update_scores.py", "Ethereum L1 (Sepolia)": "chains/ethereum-l1/deploy/update_scores_ethereum_l1.py", "Arbitrum (Sepolia)": "chains/arbitrum-ecosystem/deploy/push_scores.py",
                   "Base (Sepolia)": "chains/base-ecosystem/deploy/push_scores.py", "Tempo (Moderato)": "chains/tempo/deploy/push_scores.py", "Plasma": "chains/plasma-ecosystem/deploy/push_scores.py",
                   "Monad": "chains/monad/deploy/push_scores.py", "Hyperliquid (HyperEVM)": "chains/hyperliquid/deploy/push_scores.py"}
        for name, path in scripts.items():
            with open(os.path.join(ROOT, path), encoding="utf-8") as fh: text = fh.read()
            _, o_id, _, t_id, _ = tn.TABLE[name]
            self.assertTrue(re.search(r"\b%d\b" % o_id, text), "%s: the oracle chain id %d is not in %s" % (name, o_id, path))
            self.assertTrue(re.search(r"\b%d\b" % t_id, text), "%s: the target chain id %d is not in %s" % (name, t_id, path))


def record(**kw):
    r = {"name": "x", "oracle": A1, "readAt": 1794700000, "targets": [{"target": A2, "compositeScore": 50}, {"target": A3, "compositeScore": 40}], "networks_version": 1, "oracle_network": "Base Sepolia (testnet)", "target_network": "Base mainnet"}
    for t in r["targets"]: t["target_network"] = "Base mainnet"
    r.update(kw); return r


class WatchStep(unittest.TestCase):
    def test_a_failed_network_read_never_stops_the_run_and_still_names_the_networks(self):
        import watch_run
        old = tn.evm_fields
        def boom(*a, **k): raise RuntimeError("down")
        tn.evm_fields = boom
        try:
            doc = watch_run.add_networks("Base (Sepolia)", {"kind": "evm", "rpc": BASE_ORACLE, "targets": [{"target": A1}]})
        finally:
            tn.evm_fields = old
        self.assertIn("could not be obtained", doc["target_read_error"])
        self.assertEqual((doc["oracle_network"], doc["target_network"]), ("unplaced (read impossible)", "unplaced (read impossible)"), "nothing was read: no network name")
        self.assertNotIn("target_chain_id", doc, "no chain id was read: none is written")
        self.assertTrue(doc["targets"][0]["target_network"].startswith("unplaced"))
        e = []; validate_schemas.check(dict(doc, name="x", oracle=A1, readAt=1794700000, targets=[dict(doc["targets"][0], compositeScore=1)]), Schema.schema, "x", e)
        self.assertEqual(e, [], "the record still validates")

    @staticmethod
    def clock(watch_run):
        """a fake clock for watch_run.time: returns (state, restore)"""
        class T:
            now = 1_000_000.0
            def time(self): return T.now
            def sleep(self, s): T.now += s
        real = watch_run.time; watch_run.time = T()
        return T, lambda: setattr(watch_run, "time", real)

    def run_pass(self, durations_between, inside, n=9):
        """the shape of a Watch pass: for each oracle, `durations_between` seconds pass reading it, then add_networks runs and takes `inside` seconds"""
        import watch_run
        T, restore = self.clock(watch_run); old = tn.evm_fields
        def slow(name, oracle_url, targets, rpc, batched=None, post_json=None):
            T.now += inside
            return {"oracle_network": "x", "target_network": "y"}, {a["target"].lower(): {"target_network": "y"} for a in targets}
        tn.evm_fields = slow
        try:
            watch_run.begin_networks_pass()
            docs = []
            for i in range(n):
                T.now += durations_between
                docs.append(watch_run.add_networks("Base (Sepolia)", {"kind": "evm", "rpc": BASE_ORACLE, "targets": [{"target": A1}]}))
        finally:
            tn.evm_fields = old; restore()
        return docs

    def test_a_slow_first_oracle_and_slow_oracle_reads_do_not_empty_the_next_networks(self):
        # the real pass of the Watch: the last oracles are read 400 to 470 seconds after the first one; the networks of each take a few seconds
        docs = self.run_pass(durations_between=60, inside=5, n=9)
        self.assertEqual([("target_read_error" in d) for d in docs], [False] * 9, "every oracle gets its networks read")
        docs = self.run_pass(durations_between=450, inside=5, n=3)
        self.assertEqual([("target_read_error" in d) for d in docs], [False] * 3, "the time spent reading the oracles themselves is not counted")

    def test_the_budget_counts_only_the_time_spent_reading_networks(self):
        docs = self.run_pass(durations_between=1, inside=100, n=5)   # 100 s each: 3 calls spend the 300 s, the next ones are skipped
        self.assertEqual([("target_read_error" in d) for d in docs], [False, False, False, True, True])
        self.assertIn("time budget", docs[3]["target_read_error"]); self.assertTrue(docs[3]["targets"][0]["target_network"].startswith("unplaced"))
        self.assertEqual(docs[3]["oracle_network"], "unplaced (read impossible)")

    def test_a_slow_call_that_fails_counts_in_the_budget_too(self):
        import watch_run
        T, restore = self.clock(watch_run); old = tn.evm_fields
        def slow_fail(*a, **k):
            T.now += 200
            raise RuntimeError("the RPC answered after 200 s with an error")
        tn.evm_fields = slow_fail
        try:
            watch_run.begin_networks_pass()
            docs = [watch_run.add_networks("Base (Sepolia)", {"kind": "evm", "rpc": BASE_ORACLE, "targets": [{"target": A1}]}) for _ in range(3)]
        finally:
            tn.evm_fields = old; restore()
        self.assertIn("answered after 200 s", docs[0]["target_read_error"]); self.assertIn("answered after 200 s", docs[1]["target_read_error"])
        self.assertIn("time budget", docs[2]["target_read_error"], "400 s spent on two failing calls: the third is not tried")

    def test_the_budget_starts_again_at_the_next_pass(self):
        import watch_run
        calls = []; old = tn.evm_fields
        tn.evm_fields = lambda *a, **k: calls.append(1) or ({"oracle_network": "x", "target_network": "y"}, {})
        try:
            watch_run._NETWORKS_SPENT[0] = watch_run.NETWORKS_BUDGET_S + 1
            skipped = watch_run.add_networks("Base (Sepolia)", {"kind": "evm", "rpc": BASE_ORACLE, "targets": [{"target": A1}]})
            watch_run.begin_networks_pass()
            read = watch_run.add_networks("Base (Sepolia)", {"kind": "evm", "rpc": BASE_ORACLE, "targets": [{"target": A1}]})
        finally:
            tn.evm_fields = old; watch_run.begin_networks_pass()
        self.assertIn("time budget", skipped["target_read_error"]); self.assertNotIn("target_read_error", read); self.assertEqual(len(calls), 1)

    def test_no_rpc_is_called_once_the_budget_is_spent(self):
        import watch_run
        calls = []; old = tn.evm_fields
        tn.evm_fields = lambda *a, **k: calls.append(1) or ({}, {})
        watch_run._NETWORKS_SPENT[0] = watch_run.NETWORKS_BUDGET_S + 1
        try:
            doc = watch_run.add_networks("Base (Sepolia)", {"kind": "evm", "rpc": BASE_ORACLE, "targets": [{"target": A1}]})
        finally:
            tn.evm_fields = old; watch_run.begin_networks_pass()
        self.assertEqual(calls, []); self.assertIn("time budget", doc["target_read_error"])

    def test_every_path_marks_the_record_as_carrying_the_networks(self):
        import watch_run
        old = tn.evm_fields
        try:
            tn.evm_fields = lambda *a, **k: ({"oracle_network": "x", "target_network": "y"}, {})
            ok = watch_run.add_networks("Base (Sepolia)", {"kind": "evm", "rpc": BASE_ORACLE, "targets": [{"target": A1}]})
            def boom(*a, **k): raise RuntimeError("down")
            tn.evm_fields = boom
            bad = watch_run.add_networks("Base (Sepolia)", {"kind": "evm", "rpc": BASE_ORACLE, "targets": [{"target": A1}]})
            watch_run._NETWORKS_SPENT[0] = watch_run.NETWORKS_BUDGET_S + 1
            late = watch_run.add_networks("Base (Sepolia)", {"kind": "evm", "rpc": BASE_ORACLE, "targets": [{"target": A1}]})
        finally:
            tn.evm_fields = old; watch_run.begin_networks_pass()
        for d in (ok, bad, late):
            self.assertEqual(d["networks_version"], 1); self.assertIn("oracle_network", d); self.assertIn("target_network", d)
            self.assertTrue(all("target_network" in t for t in d["targets"]))

    def test_a_solana_oracle_rpc_that_answers_another_genesis_is_not_named_devnet(self):
        import watch_run
        old_f, old_r = tn.solana_fields, watch_run._sol_rpc
        tn.solana_fields = lambda targets, rpc_json: ({"oracle_network": tn.UNREAD, "target_network": "Solana mainnet-beta"}, {})
        try:
            watch_run._sol_rpc = lambda url, m, p: tn.GENESIS["Solana devnet"]
            ok = watch_run.add_networks("Solana (Devnet)", {"kind": "solana", "rpc": "https://api.devnet.solana.com", "targets": []})
            watch_run._sol_rpc = lambda url, m, p: tn.GENESIS["Solana mainnet-beta"]
            bad = watch_run.add_networks("Solana (Devnet)", {"kind": "solana", "rpc": "https://api.devnet.solana.com", "targets": []})
        finally:
            tn.solana_fields, watch_run._sol_rpc = old_f, old_r
        self.assertEqual(ok["oracle_network"], "Solana devnet")
        self.assertEqual(bad["oracle_network"], "unplaced (read impossible)"); self.assertIn("expected devnet", bad["oracle_chain_read_error"])


class Schema(unittest.TestCase):
    with open(os.path.join(ROOT, "watch", "schema", "scores.schema.json"), encoding="utf-8") as fh: schema = json.load(fh)

    def errs(self, rec):
        e = []; validate_schemas.check(rec, self.schema, "scores/x.json", e); return e

    def test_a_complete_record_is_valid(self):
        self.assertEqual(self.errs(record()), [])

    def test_no_target_without_a_network(self):
        for i in (0, 1):   # whichever target lacks it, the record is refused
            r = record(); del r["targets"][i]["target_network"]
            self.assertTrue(any("targets[%d]: required target_network" % i in x for x in self.errs(r)), i)

    def test_a_record_that_carries_the_marker_must_name_both_networks_and_every_target(self):
        r = record(); del r["oracle_network"]; del r["target_network"]
        e = self.errs(r); self.assertTrue(any("required oracle_network" in x for x in e) and any("required target_network" in x for x in e))
        r = record(); del r["targets"][1]["target_network"]
        self.assertTrue(any("targets[1]: required target_network" in x for x in self.errs(r)))

    def test_an_old_format_record_stays_valid_whatever_the_date(self):
        # the record an unreadable oracle keeps from an earlier pass: written by the code before this change, without any network field
        import calendar
        start = calendar.timegm((2026, 11, 14, 0, 0, 1))   # 2026-11-14T00:00:01Z, then 30 days later, then a year later
        for read_at in (start, start + 30 * 86400, start + 365 * 86400):
            r = record(readAt=read_at)
            for k in ("networks_version", "oracle_network", "target_network"): del r[k]
            for t in r["targets"]: del t["target_network"]
            self.assertEqual(self.errs(r), [], "readAt %d" % read_at)

    def test_the_watch_validation_step_passes_on_an_old_file_after_the_start_date(self):
        import calendar, tempfile, shutil
        d = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(d, "scores"))
            r = record(readAt=calendar.timegm((2026, 11, 14, 0, 0, 1)) + 30 * 86400)
            for k in ("networks_version", "oracle_network", "target_network"): del r[k]
            for t in r["targets"]: del t["target_network"]
            with open(os.path.join(d, "scores", "x.json"), "w", encoding="utf-8") as fh: json.dump(r, fh)
            shutil.copytree(os.path.join(ROOT, "watch", "schema"), os.path.join(d, "schema"))
            old = sys.argv; sys.argv = ["validate_schemas.py", "--watch", d]
            try:
                try: validate_schemas.main(); code = 0
                except SystemExit as e: code = e.code or 0
            finally: sys.argv = old
        finally: shutil.rmtree(d, ignore_errors=True)
        self.assertEqual(code, 0, "an old file kept by an unreadable oracle never fails the Watch")

    def test_types_of_the_new_fields(self):
        self.assertTrue(self.errs(record(target_chain_id="8453")))
        self.assertEqual(self.errs(record(target_chain_id=None, target_block=None, target_read_error="down")), [])


if __name__ == "__main__":
    unittest.main()
