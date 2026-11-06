"""Retired-on-purpose targets (data/retired_targets.json): listed apart, never hidden. Standard library only; no network.
A retired target is out of the stale count and the methodology hashes in use; a retired target written again is a normal target again with an alert; a file that cannot be read retires nothing."""
import contextlib, io, json, os, shutil, sys, tempfile, time, unittest

HERE = os.path.dirname(os.path.abspath(__file__)); SCRIPTS = os.path.join(HERE, ".."); sys.path.insert(0, SCRIPTS); sys.path.insert(0, os.path.join(SCRIPTS, "lib"))
import retired  # noqa: E402
import watch_run  # noqa: E402
import methodology_check  # noqa: E402
import oracle_freshness  # noqa: E402
import run_status  # noqa: E402
import push_guard  # noqa: E402

RET = "0x2cc440b721d2cafd6d64908d6d8c4acc57f8afc3"; LIVE = "0x1111111111111111111111111111111111111111"; PIN = 1790180194
OLD, NEW = "0x" + "ac" * 32, "0x" + "a3" * 32
ENTRY = {"note": "old minter, retired on purpose", "since": "2026-09-20", "last_update_at_retirement": PIN}
REG = {"ethereum-l1-sepolia:" + RET: ENTRY}


def row(target, last, stale, h=NEW, idx=0): return {"index": idx, "target": target, "adminKeyScore": 10, "multisigScore": 10, "timelockScore": 0, "oracleAuthorityScore": 10, "crossExposureScore": 10, "compositeScore": 10, "lastUpdated": last, "methodologyHash": h, "stale": stale}


class TestTheFile(unittest.TestCase):
    def write(self, tmp, obj):
        p = os.path.join(tmp, "r.json"); open(p, "w").write(obj if isinstance(obj, str) else json.dumps(obj)); return p

    def test_the_shipped_file_is_well_formed_and_pins_the_l1_minter(self):
        reg, err = retired.load(); self.assertIsNone(err); self.assertIn("ethereum-l1-sepolia:" + RET, reg)
        for k, v in reg.items(): self.assertTrue(v["note"] and v["since"] and isinstance(v["last_update_at_retirement"], int), k)

    def test_a_file_that_cannot_be_read_or_is_incomplete_retires_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            for bad in ("{not json", {"targets": []}, {"targets": {"a:0x1": {"note": "n", "since": "s"}}}, {"targets": {"a:0x1": {"note": "n", "since": "s", "last_update_at_retirement": 0}}},
                        {"targets": {"a:0x1": {"note": "n", "since": "s", "last_update_at_retirement": True}}}, {"targets": {"nocolon": {"note": "n", "since": "s", "last_update_at_retirement": 5}}}):
                reg, err = retired.load(self.write(tmp, bad)); self.assertEqual(reg, {}, bad); self.assertTrue(err, bad)
            reg, err = retired.load(os.path.join(tmp, "missing.json")); self.assertEqual(reg, {}); self.assertTrue(err)
            ok = {"note": "n", "since": "s", "last_update_at_retirement": 5}
            for bad in ({"a:0x1": dict(ok, last_update_at_retirement="5")}, {"a:0x1": dict(ok, last_update_at_retirement=int(time.time()) * 1000)}, {"a:0x1": dict(ok, last_update_at_retirement=int(time.time()) + 10 * 86400)},
                        {"a:0x1": dict(ok, note=["a list"])}, {"a:0x1": dict(ok, since=20260920)}, {"a:0x1": dict(ok, note="")}):
                reg, err = retired.load(self.write(tmp, {"targets": bad})); self.assertEqual(reg, {}, bad); self.assertTrue(err, bad)   # a date in milliseconds or in the future would never wake up
            reg, err = retired.load(self.write(tmp, {"targets": {"ETHEREUM-L1-Sepolia:0xABCdef": ok}})); self.assertIn("ethereum-l1-sepolia:0xabcdef", reg)   # keys are read in lower case


class TestApply(unittest.TestCase):
    def test_a_dormant_listed_target_is_retired_and_the_others_are_not(self):
        t = [row(RET, PIN, True, OLD), row(LIVE, 1793000000, False)]
        ret, woke = retired.apply("ethereum-l1-sepolia", t, REG)
        self.assertEqual(([x["target"] for x in ret], woke), ([RET], [])); self.assertTrue(t[0]["retired"]); self.assertNotIn("retired", t[1])

    def test_any_value_other_than_the_pin_is_a_write_even_an_earlier_one(self):
        for last in (PIN - 1, PIN + 1):
            t = [row(RET, last, True)]; ret, woke = retired.apply("ethereum-l1-sepolia", t, REG); self.assertEqual((ret, len(woke)), ([], 1), last); self.assertNotIn("retired", t[0])

    def test_the_address_is_matched_in_any_case(self):
        checksum = "0x2CC440b721d2CaFd6D64908d6d8c4aCC57F8Afc3"; t = [row(checksum, PIN, True, OLD)]
        ret, woke = retired.apply("ethereum-l1-sepolia", t, REG); self.assertEqual((len(ret), woke), (1, [])); self.assertEqual(len(retired.listing("ethereum-l1-sepolia", ret, REG)), 1)

    def test_the_same_address_on_another_oracle_is_not_retired(self):
        t = [row(RET, PIN, True, OLD)]; ret, woke = retired.apply("base-sepolia", t, REG); self.assertEqual((ret, woke), ([], [])); self.assertNotIn("retired", t[0])

    def test_a_retired_target_written_again_wakes_up_and_is_a_normal_target(self):
        t = [row(RET, PIN + 1, False)]; ret, woke = retired.apply("ethereum-l1-sepolia", t, REG)
        self.assertEqual((ret, [x["target"] for x in woke]), ([], [RET])); self.assertNotIn("retired", t[0])

    def test_a_stale_flag_from_an_earlier_run_does_not_keep_a_woken_target_retired(self):
        t = [dict(row(RET, PIN + 5, False), retired=True)]; retired.apply("ethereum-l1-sepolia", t, REG); self.assertNotIn("retired", t[0])

    def test_the_listing_carries_the_name_the_note_and_the_date(self):
        t = [row(RET, PIN, True, OLD)]; ret, _ = retired.apply("ethereum-l1-sepolia", t, REG)
        self.assertEqual(retired.listing("ethereum-l1-sepolia", ret, REG), [{"oracle": "ethereum-l1-sepolia", "target": RET, "note": ENTRY["note"], "since": "2026-09-20", "lastUpdated": PIN}])


class TestTheRun(unittest.TestCase):
    """watch_run.main() end to end on one fake oracle: the stale total, the badge, the published list, the alerts."""
    def run_main(self, targets, registry_obj, prev=None):
        tmp = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, tmp, True)
        os.makedirs(os.path.join(tmp, "scores")); rp = os.path.join(tmp, "retired.json")
        if prev is not None: json.dump({"name": "Ethereum L1 (Sepolia)", "oracle": "0x" + "09" * 20, "targets": prev}, open(os.path.join(tmp, "scores", "ethereum-l1-sepolia.json"), "w"))
        if registry_obj is not None: open(rp, "w").write(json.dumps(registry_obj))
        saved = (watch_run.WATCH, watch_run.ORACLES, watch_run.read_evm_any, watch_run.read_solana, watch_run.block_time_of, watch_run.scan_progress, retired.load)
        real_load = retired.load
        doc = {"name": "Ethereum L1 (Sepolia)", "kind": "evm", "oracle": "0x" + "09" * 20, "rpc": "http://x", "block": 5, "maxStaleness": 777600, "readAt": 1793800000, "targets": targets}
        watch_run.WATCH = tmp; watch_run.ORACLES = [("Ethereum L1 (Sepolia)", doc["oracle"], "http://x")]
        watch_run.read_evm_any = lambda name, oracle, url, since: json.loads(json.dumps(doc)); watch_run.read_solana = lambda since=None: (_ for _ in ()).throw(RuntimeError("no solana here"))
        watch_run.block_time_of = lambda rpc, block: 1793800000; watch_run.scan_progress = lambda prev, cur: (0, [])
        retired.load = lambda: real_load(rp)
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                try: watch_run.main()
                except SystemExit: pass
        finally:
            (watch_run.WATCH, watch_run.ORACLES, watch_run.read_evm_any, watch_run.read_solana, watch_run.block_time_of, watch_run.scan_progress, retired.load) = saved
        return tmp

    def read(self, tmp, name): return json.load(open(os.path.join(tmp, name)))

    def test_a_dormant_retired_target_is_listed_apart_and_not_counted_stale(self):
        tmp = self.run_main([row(LIVE, 1793790000, False, NEW, 0), row(RET, PIN, True, OLD, 1)], {"targets": REG})
        latest = self.read(tmp, "latest.json"); self.assertEqual((latest["total_targets"], latest["stale_total"], latest["retired_total"]), (2, 0, 1))
        self.assertEqual(latest["retired"][0]["target"], RET); self.assertIn("old minter", latest["retired"][0]["note"])   # the name and the note are published, not hidden
        self.assertEqual(self.read(tmp, "badge.json")["message"], "2 targets, 0 stale, 1 retired, 0 alarms")
        o = [x for x in latest["oracles"] if x.get("read_ok")][0]; self.assertEqual((o["targets"], o["stale"], o["retired"]), (2, 0, 1))
        hist = [json.loads(l) for l in open(os.path.join(tmp, "history.jsonl")) if l.strip()][-1]; self.assertEqual((hist["stale"], hist["retired"]), (0, 1))
        sc = {t["target"]: t for t in self.read(tmp, "scores/ethereum-l1-sepolia.json")["targets"]}; self.assertTrue(sc[RET]["retired"]); self.assertTrue(sc[RET]["stale"])   # still honest: it IS old
        self.assertEqual(self.read(tmp, "badge/ethereum-l1-sepolia/%s.json" % RET)["message"], "10/100 (retired)")

    def test_without_the_file_the_same_target_is_stale_again_and_the_badge_keeps_its_old_text(self):
        tmp = self.run_main([row(LIVE, 1793790000, False, NEW, 0), row(RET, PIN, True, OLD, 1)], None)
        latest = self.read(tmp, "latest.json"); self.assertEqual((latest["stale_total"], latest["retired_total"]), (1, 0))
        self.assertTrue(any("retired targets file not read" in a for a in latest["alerts"]))   # a missing file is an alarm, never a quiet fallback
        self.assertEqual(self.read(tmp, "badge.json")["message"], "2 targets, 1 stale, 1 alarm")

    def test_a_woken_retired_target_is_counted_and_raises_an_alert_on_every_run(self):
        tmp = self.run_main([row(LIVE, 1793790000, False, NEW, 0), row(RET, PIN + 100, True, OLD, 1)], {"targets": REG})
        latest = self.read(tmp, "latest.json"); self.assertEqual((latest["stale_total"], latest["retired_total"]), (1, 0))
        self.assertTrue(any("was written again" in a and "data/retired_targets.json" in a for a in latest["alerts"]), latest["alerts"])

    def test_a_target_that_is_not_listed_and_is_stale_is_still_counted(self):
        tmp = self.run_main([row(LIVE, PIN, True, NEW, 0), row(RET, PIN, True, OLD, 1)], {"targets": REG})
        latest = self.read(tmp, "latest.json"); self.assertEqual((latest["stale_total"], latest["retired_total"]), (1, 1))


    def test_a_retired_target_that_turns_stale_raises_no_turned_stale_alert_but_an_unlisted_one_does(self):
        before = [row(LIVE, 1793790000, False, NEW, 0), row(RET, PIN, False, OLD, 1)]   # the run before: both fresh
        latest = self.read(self.run_main([row(LIVE, 1793790000, False, NEW, 0), row(RET, PIN, True, OLD, 1)], {"targets": REG}, prev=before), "latest.json")
        self.assertFalse(any("turned stale" in a for a in latest["alerts"]), latest["alerts"])
        latest = self.read(self.run_main([row(LIVE, PIN, True, NEW, 0), row(RET, PIN, True, OLD, 1)], {"targets": REG}, prev=before + []), "latest.json")
        self.assertTrue(any("turned stale" in a for a in latest["alerts"]), latest["alerts"])   # the live one still alarms


class TestHashesAndFreshness(unittest.TestCase):
    def test_a_retired_target_is_not_a_second_method_in_use(self):
        seen, dom = methodology_check.dominant({"targets": [row(LIVE, 1, False, NEW), dict(row(RET, 1, True, OLD), retired=True)]}); self.assertEqual((seen, dom), ({NEW: 1}, NEW))
        seen, _ = methodology_check.dominant({"targets": [row(LIVE, 1, False, NEW), row(RET, 1, True, OLD)]}); self.assertEqual(len(seen), 2)   # not marked: a mix is still a mix

    def test_the_freshness_digest_leaves_a_dormant_retired_entry_out_and_keeps_a_woken_one(self):
        info = {"count": 2, "max_staleness": 777600, "updated": [(0, LIVE, 1793790000), (1, RET, PIN)]}
        s = oracle_freshness.summarize(info, 1793800000, 48 * 3600, "ethereum-l1-sepolia", REG)
        self.assertEqual(([r["address"] for r in s["stale"]], [r["address"] for r in s["retired"]]), ([], [RET]))
        info["updated"][1] = (1, RET, PIN + 1); s = oracle_freshness.summarize(info, 1793800000 + 9 * 86400, 48 * 3600, "ethereum-l1-sepolia", REG)
        self.assertIn(RET, [r["address"] for r in s["stale"]]); self.assertEqual(s["retired"], [])
        self.assertEqual([r["address"] for r in oracle_freshness.summarize(info, 1793800000, 48 * 3600)["rows"]], [LIVE, RET])   # no registry: nothing is left out


class TestTheOtherPlaces(unittest.TestCase):
    def test_the_freshness_digest_matches_the_address_in_checksum_case_as_web3_returns_it(self):
        info = {"count": 1, "max_staleness": 777600, "updated": [(0, "0x2CC440b721d2CaFd6D64908d6d8c4aCC57F8Afc3", PIN)]}
        s = oracle_freshness.summarize(info, PIN + 99 * 86400, 48 * 3600, "ethereum-l1-sepolia", REG); self.assertEqual((s["stale"], len(s["retired"])), ([], 1))
        self.assertEqual(len(oracle_freshness.summarize(dict(info, updated=[(0, RET, PIN - 1)]), PIN + 99 * 86400, 48 * 3600, "ethereum-l1-sepolia", REG)["stale"]), 1)   # an earlier value is a write too

    def freshness_main(self, registry_loader, updated):
        saved = (oracle_freshness.read_freshness, oracle_freshness.read_freshness_solana, oracle_freshness.retired_targets.load, oracle_freshness.time.time)
        oracle_freshness.read_freshness = lambda pause=0: [("Ethereum L1 (Sepolia)", {"count": len(updated), "max_staleness": 777600, "updated": updated}, None)]
        oracle_freshness.read_freshness_solana = lambda: []; oracle_freshness.retired_targets.load = registry_loader; oracle_freshness.time.time = lambda: PIN + 99 * 86400
        out = io.StringIO()
        try:
            with contextlib.redirect_stdout(out):
                with self.assertRaises(SystemExit) as cm: oracle_freshness.main([])
        finally: (oracle_freshness.read_freshness, oracle_freshness.read_freshness_solana, oracle_freshness.retired_targets.load, oracle_freshness.time.time) = saved
        return cm.exception.code, out.getvalue()

    def test_the_freshness_run_names_the_oracle_the_way_the_watch_does_and_says_what_it_left_out(self):
        code, out = self.freshness_main(lambda: (REG, None), [(0, LIVE, PIN + 98 * 86400), (1, RET, PIN)])
        self.assertEqual(code, 0); self.assertIn("retired, left to go stale on purpose", out); self.assertIn("except 1 retired", out); self.assertNotIn("already stale", out)

    def test_the_freshness_run_with_an_unreadable_file_counts_the_retired_entry_and_says_so(self):
        code, out = self.freshness_main(lambda: ({}, "retired_targets.json: boom"), [(0, LIVE, PIN + 98 * 86400), (1, RET, PIN)])
        self.assertEqual(code, 1); self.assertIn("retired targets file not read", out); self.assertIn("already stale", out)

    def test_methodology_json_lists_the_retired_targets_and_leaves_them_out_of_the_hashes(self):
        tmp = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, tmp, True); os.makedirs(os.path.join(tmp, "scores")); os.makedirs(os.path.join(tmp, "prev"))
        json.dump({"name": "x", "targets": [row(LIVE, 1, False, NEW), dict(row(RET, PIN, True, OLD), retired=True)]}, open(os.path.join(tmp, "scores", "ethereum-l1-sepolia.json"), "w"))
        old = sys.argv; sys.argv = ["methodology_check.py", "--registry", os.path.join(tmp, "none.json"), "--scores", os.path.join(tmp, "scores"), "--prev", os.path.join(tmp, "prev"), "--events", "", "--out", os.path.join(tmp, "m.json"), "--md", ""]
        try:
            with contextlib.redirect_stdout(io.StringIO()): methodology_check.main()
        finally: sys.argv = old
        m = json.load(open(os.path.join(tmp, "m.json"))); self.assertEqual(m["mixed"], []); self.assertEqual(list(m["hashes"]), [NEW]); self.assertEqual(m["retired"], [{"oracle": "ethereum-l1-sepolia", "target": RET, "hash": OLD}])

    def test_the_three_places_that_know_a_retired_target_agree(self):
        reg, _ = retired.load(); scope = json.load(open(os.path.join(SCRIPTS, "..", "data", "tvl_scope.json")))["targets"]; scoped = {k.split(":", 1)[1].lower() for k, v in scope.items() if v.get("scope") == "retired"}
        for k in reg:
            addr = k.split(":", 1)[1]; self.assertIn(addr, push_guard.RETIRED_ON_PURPOSE, k); self.assertIn(addr, scoped, k)   # push_guard stops asking for it, tvl_scope leaves its money out


class TestTheStatus(unittest.TestCase):
    def test_the_status_says_how_many_are_retired_without_changing_its_state(self):
        tmp = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, tmp, True)
        json.dump({"run_utc": "2026-11-05T00:00:00Z", "oracles": [], "total_targets": 2, "stale_total": 0, "retired_total": 1, "movers": [], "alerts": [], "unread": []}, open(os.path.join(tmp, "latest.json"), "w"))
        old = sys.argv; sys.argv = ["run_status.py", "--watch", tmp]
        try:
            with contextlib.redirect_stdout(io.StringIO()): run_status.main()
        finally: sys.argv = old
        rec = json.load(open(os.path.join(tmp, "status.json"))); self.assertEqual(rec["checks"]["retired"], 1); self.assertTrue(any("1 retired target" in r and "not counted stale" in r for r in rec["reasons"]))
        self.assertNotIn("stale", " ".join(r for r in rec["reasons"] if "retired" not in r))


if __name__ == "__main__":
    unittest.main()
