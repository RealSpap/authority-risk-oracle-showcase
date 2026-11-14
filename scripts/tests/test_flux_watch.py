"""scripts/construire_flux_watch.py: the JSON Feed of authority changes. Offline, with made-up events.

What this guards: only `admin_change` and `upgraded` events enter the feed, newest first, with stable ids (the seq of the event); no score is read or written; the file the job writes goes through the same
withhold step as every published file (an entry that names a queue left out is cleaned); the script touches no network and no file other than its output."""
import json, os, subprocess, sys, tempfile, unittest, warnings

warnings.simplefilter("ignore", ResourceWarning)
HERE = os.path.dirname(os.path.abspath(__file__)); SCRIPTS = os.path.join(HERE, ".."); SCRIPT = os.path.join(SCRIPTS, "construire_flux_watch.py")
sys.path.insert(0, SCRIPTS); sys.path.insert(0, HERE)
import construire_flux_watch as F  # noqa: E402
import test_withhold as TW  # noqa: E402

EVENTS = [json.dumps(e) for e in (
    {"seq": 1, "kind": "move", "run_utc": "2026-11-01T01:00:00Z", "oracle": "A", "target": "0x1", "field": "x", "before": 1, "after": 2},
    {"seq": 2, "kind": "admin_change", "run_utc": "2026-11-02T01:00:00Z", "oracle": "Base (Sepolia)", "target": "0x" + "ab" * 20, "label": None, "text": "admin read changed"},
    {"seq": 3, "kind": "alarm", "run_utc": "2026-11-03T01:00:00Z", "text": "scan gave up"},
    {"seq": 4, "kind": "upgraded", "run_utc": "2026-11-04T01:00:00Z", "oracle": "Plasma", "target": "0x" + "cd" * 20, "label": "Some vault", "text": "implementation changed"})]


class TestBuild(unittest.TestCase):
    def test_only_authority_changes_enter_newest_first_with_stable_ids(self):
        f = F.build(EVENTS); self.assertEqual([i["_aro"]["seq"] for i in f["items"]], [4, 2])
        self.assertEqual([i["id"] for i in f["items"]], ["tag:realspap.github.io,2026:watch:seq-4", "tag:realspap.github.io,2026:watch:seq-2"])
        self.assertEqual(F.check(f), 2)
    def test_no_score_field_is_read_or_written(self):
        t = json.dumps(F.build(EVENTS)).lower(); self.assertNotIn("score", t.replace("no score", ""))
    def test_the_score_clause_the_watch_writes_in_its_texts_is_dropped(self):
        # the shape of a real `upgraded` event of the journal: its text ends with a clause about the score
        e = json.dumps({"seq": 9, "kind": "upgraded", "run_utc": "2026-11-05T01:00:00Z", "oracle": "base", "target": "0x" + "ab" * 20, "label": None,
                        "text": "upgrade executed on base 0xabababab: implementation changed since the previous run: 0xc145 -> 0xb6ef (EIP-1967 implementation slot); the score reads who may upgrade, this is an upgrade that happened"})
        f = F.build([e]); t = f["items"][0]["content_text"]; self.assertNotIn("score", t.lower()); self.assertIn("EIP-1967 implementation slot", t); F.check(f)
    def test_each_entry_names_its_network_and_chain_id_from_the_oracle_file_of_the_event(self):
        d = tempfile.mkdtemp(); A = "0x" + "ab" * 20
        for stem, net, cid in (("base-sepolia", "Base mainnet", 8453), ("arbitrum-sepolia", "Arbitrum One mainnet", 42161), ("plasma", "Plasma mainnet", 9745)):
            json.dump({"targets": [{"target": A, "target_network": net, "target_chain_id": cid}, {"target": "SoLaNaPrOgRaM", "target_network": "Solana mainnet-beta", "target_chain_id": None}] if stem == "base-sepolia" else [{"target": A, "target_network": net, "target_chain_id": cid}]}, open(os.path.join(d, stem + ".json"), "w"))
        nets = F.networks(d)
        def ev(seq, oracle, kind="upgraded", target=A): return json.dumps({"seq": seq, "kind": kind, "run_utc": "2026-11-05T01:00:00Z", "oracle": oracle, "target": target.upper().replace("0X", "0x") if target.startswith("0x") else target, "label": None, "text": "implementation changed"})
        by = {i["_aro"]["seq"]: i for i in F.build([ev(1, "base"), ev(2, "arbitrum"), ev(3, "plasma")], nets=nets)["items"]}
        self.assertTrue(by[1]["content_text"].startswith("Network: Base mainnet (chain ID 8453). ")); self.assertTrue(by[2]["content_text"].startswith("Network: Arbitrum One mainnet (chain ID 42161). ")); self.assertTrue(by[3]["content_text"].startswith("Network: Plasma mainnet (chain ID 9745). "))
        self.assertIn("Arbitrum One mainnet (chain ID 42161)", by[2]["title"])
        self.assertEqual(F.network_of(nets, "solana", "SoLaNaPrOgRaM"), "Solana mainnet-beta"); self.assertIsNone(F.network_of(nets, "solana", "solanaprogram"))
        self.assertIsNone(F.network_of(nets, "ethereum-l1", A), "an address that three networks share is never guessed when the oracle has no file")
        it = F.build([ev(4, "hyperliquid")], nets=nets)["items"][0]; self.assertTrue(it["content_text"].startswith("Network: network not determined from the target files of this run. ")); self.assertNotIn("hyperliquid", it["title"]); self.assertIn("on a network not determined", it["title"])
        e2 = json.dumps({"seq": 10, "kind": "admin_change", "run_utc": "2026-11-05T02:00:00Z", "oracle": "x", "target": "0x" + "12" * 20, "label": None, "text": "admin read changed"})
        self.assertTrue(F.build([e2], nets=nets)["items"][0]["content_text"].startswith("Network: network not determined"))
    def test_the_id_does_not_change_when_older_events_leave_the_window(self):
        a = {i["id"] for i in F.build(EVENTS)["items"]}; b = {i["id"] for i in F.build(EVENTS, limit=1)["items"]}; self.assertTrue(b <= a)
    def test_the_command_writes_one_file_and_selftest_passes(self):
        d = tempfile.mkdtemp(); ev = os.path.join(d, "events.jsonl"); out = os.path.join(d, "authority-changes.json"); open(ev, "w").write("\n".join(EVENTS) + "\n")
        r = subprocess.run([sys.executable, "-I", SCRIPT, ev, out], capture_output=True, text=True); self.assertEqual(r.returncode, 0, r.stderr); self.assertEqual(sorted(os.listdir(d)), ["authority-changes.json", "events.jsonl"])
        r = subprocess.run([sys.executable, "-I", SCRIPT, "--check", out], capture_output=True, text=True); self.assertEqual(r.returncode, 0, r.stderr)
        r = subprocess.run([sys.executable, "-I", SCRIPT, "--selftest"], capture_output=True, text=True); self.assertEqual(r.returncode, 0, r.stderr)
    def test_it_imports_no_network_module(self):
        src = open(SCRIPT, encoding="utf-8").read(); self.assertNotRegex(src, r"(?m)^\s*(import|from)\s+(urllib|requests|socket|http)")


class TestThroughTheWithholdStep(TW.Base):
    def test_an_entry_that_names_a_held_queue_is_cleaned_like_any_published_json(self):
        evs = [json.dumps({"seq": 7, "kind": "admin_change", "run_utc": "2026-11-05T01:00:00Z", "oracle": "O", "target": "0x" + "ee" * 20, "label": None, "text": "admin is now %s" % TW.HELD_MS}),
               json.dumps({"seq": 8, "kind": "upgraded", "run_utc": "2026-11-06T01:00:00Z", "oracle": "O", "target": "0x" + "ff" * 20, "label": None, "text": "implementation changed"})]
        self.put("authority-changes.json", F.build(evs)); self.run_cli(); r0, _ = self.run_cli("check"); self.assertEqual(r0.returncode, 1, "the leak must be seen before the views step"); self.run_cli("views")
        t = self.text("authority-changes.json"); self.assertNotIn(TW.HELD_MS, t); self.assertIn("implementation changed", t)
        r, _ = self.run_cli("check"); self.assertEqual(r.returncode, 0, r.stderr)


if __name__ == "__main__":
    unittest.main()
