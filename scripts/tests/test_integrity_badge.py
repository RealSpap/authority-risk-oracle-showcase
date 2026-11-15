"""The badge "watch integrity" says whether the WATCH is healthy, not whether the Watch found something. It used to turn red for a target alarm (an executed upgrade, a high alert, a role change on a watched contract),
which mixes "the Watch is broken" with "the Watch is doing its job". Health (valid signature, intact chain, every oracle read, role scan without a hole) colours the badge; what the Watch found goes to `findings`
in status.json, to alerts.json and to the badge of the alarms. `state` of status.json stays the worse of the two, as it was, for the monitors that read it."""
import contextlib, io, json, os, sys, tempfile, unittest
import warnings

warnings.simplefilter("ignore", ResourceWarning)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import audit_public  # noqa: E402
import run_status  # noqa: E402

RUN = "2026-11-15T18:30:00Z"


def oracle(slug, read_ok=True, self_watch="complete"):
    sw = {"complete": {"read": True, "role_events": 0, "error": None, "unread_blocks": None},
          "baseline": {"read": False, "role_events": 0, "error": None, "unread_blocks": None},       # the first read of an oracle: no earlier block to scan from
          "behind": {"read": False, "role_events": 0, "error": "getLogs: 300 blocks left after 120 calls, read by the next run", "unread_blocks": 300},
          "failed": {"read": False, "role_events": 0, "error": "getLogs: HTTP 500", "unread_blocks": 4000}}[self_watch]
    return {"name": slug, "slug": slug, "kind": "evm", "read_ok": read_ok, "self_watch": sw}


class Case(unittest.TestCase):
    def watch(self, tmp, oracles=None, alerts=(), unread=(), chain=True, sig="fresh", so=None, rules_high=0, prev_status=None, extra_latest=None):
        w = os.path.join(tmp, "watch"); os.makedirs(os.path.join(w, "scores"))
        oracles = oracles if oracles is not None else [oracle("base"), oracle("monad")]
        lat = {"run_utc": RUN, "oracles": oracles, "unread": list(unread), "alerts": list(alerts), "total_targets": 4, "stale_total": 0}; lat.update(extra_latest or {})
        json.dump(lat, open(os.path.join(w, "latest.json"), "w"))
        json.dump({"ok": True, "lines": 3} if chain is True else chain, open(os.path.join(w, "chain.json"), "w"))
        if sig == "fresh": json.dump({"run_utc": RUN, "manifest": {"files": {}}, "signed": True, "public_key": sorted(audit_public.PINNED_KEYS)[0]}, open(os.path.join(w, "signature.json"), "w"))
        elif sig == "stale": json.dump({"run_utc": "2026-11-15T12:30:00Z", "manifest": {"files": {}}, "signed": True, "public_key": sorted(audit_public.PINNED_KEYS)[0]}, open(os.path.join(w, "signature.json"), "w"))
        if so is not None: json.dump(so, open(os.path.join(w, "second_opinion.json"), "w"))
        if rules_high: json.dump({"active": [{"severity": "high", "rule": "a change is ready to execute"}] * rules_high}, open(os.path.join(w, "alerts.json"), "w"))
        if prev_status is not None: json.dump(prev_status, open(os.path.join(w, "status.json"), "w"))
        return w

    def exec_status(self, w):
        old, sys.argv = sys.argv, ["run_status.py", "--watch", w]
        try:
            with contextlib.redirect_stdout(io.StringIO()): run_status.main()
        finally: sys.argv = old
        return json.load(open(os.path.join(w, "status.json"))), json.load(open(os.path.join(w, "badge", "integrity.json")))

    def go(self, **kw):
        with tempfile.TemporaryDirectory() as tmp: return self.exec_status(self.watch(tmp, **kw))


class TestHealthAloneColoursTheBadge(Case):
    def test_a_healthy_watch_is_green_and_says_the_role_scan_is_complete(self):
        st, bd = self.go()
        self.assertEqual((st["health"]["state"], st["findings"]["state"], st["state"]), ("ok", "ok", "ok"), st["reasons"]); self.assertEqual(bd["color"], "brightgreen")
        self.assertIn("role scan complete", bd["message"])

    def test_target_alarms_do_not_turn_the_integrity_badge_red(self):
        # the state of 15 November: an executed upgrade, a queued operation ready to execute, role-event alerts: findings of the Watch, not a fault of the Watch
        st, bd = self.go(alerts=["Solana: upgrade executed", "Ethena: a queued operation is ready to execute"], so={"agree": 3, "disagree": 0, "upgrades": [{"program": "x"}]}, rules_high=2)
        self.assertEqual(st["health"]["state"], "ok", st["health"]); self.assertEqual(bd["color"], "brightgreen", bd)
        self.assertEqual(st["findings"]["state"], "alarm"); self.assertEqual(st["state"], "alarm")        # the monitors that read `state` still see the alarm
        self.assertTrue(any("alarm(s) raised by the watch" in r for r in st["findings"]["reasons"])); self.assertTrue(any("upgrade(s) executed" in r for r in st["findings"]["reasons"]))
        self.assertFalse(any("alarm(s) raised" in r or "upgrade" in r for r in st["health"]["reasons"]))   # and the reasons are kept apart
        self.assertTrue(all(r in st["reasons"] for r in st["findings"]["reasons"] + st["health"]["reasons"]))   # `reasons` still lists everything

    def test_a_hole_in_the_role_scan_is_orange_never_red_and_never_green(self):
        st, bd = self.go(oracles=[oracle("base", self_watch="behind"), oracle("monad")])
        self.assertEqual(st["health"]["state"], "degraded"); self.assertEqual(bd["color"], "orange"); self.assertIn("role scan behind", bd["message"]); self.assertIn("300 blocks", bd["message"])
        self.assertTrue(any("role scan" in r for r in st["health"]["reasons"])); self.assertEqual(st["findings"]["state"], "ok")
        st, bd = self.go(oracles=[oracle("base", self_watch="failed"), oracle("monad", self_watch="behind")]); self.assertIn("4300 blocks", bd["message"]); self.assertIn("2 oracle", bd["message"])

    def test_the_gap_alarm_of_an_older_run_is_a_health_matter_too(self):
        st, bd = self.go(alerts=["Monad: the scan of the oracle's own role events gave up a window of 63609 blocks; a RoleGranted or RoleRevoked inside it was not seen"])
        self.assertEqual((st["health"]["state"], st["findings"]["state"], bd["color"]), ("degraded", "ok", "orange"), st)

    def test_the_first_read_of_an_oracle_is_a_baseline_not_a_hole(self):
        st, bd = self.go(oracles=[oracle("base", self_watch="baseline"), oracle("monad")]); self.assertEqual((st["health"]["state"], bd["color"]), ("ok", "brightgreen"))

    def test_an_oracle_not_read_is_orange_the_first_time_and_red_when_it_stays_mute(self):
        st, bd = self.go(oracles=[oracle("base", read_ok=False), oracle("monad")], unread=["base"])
        self.assertEqual((st["health"]["state"], bd["color"]), ("degraded", "orange")); self.assertEqual(st["checks"]["unread"], ["base"])
        prev = {"run_utc": "2026-11-15T12:30:00Z", "state": "degraded", "checks": {"unread": ["base"]}}
        st, bd = self.go(oracles=[oracle("base", read_ok=False), oracle("monad")], unread=["base"], prev_status=prev)
        self.assertEqual((st["health"]["state"], bd["color"]), ("alarm", "red")); self.assertTrue(any("mute" in r for r in st["health"]["reasons"]))
        st, bd = self.go(oracles=[oracle("base"), oracle("monad", read_ok=False)], unread=["monad"], prev_status=prev); self.assertEqual(st["health"]["state"], "degraded")    # another oracle: first time
        st, bd = self.go(oracles=[oracle("base"), oracle("monad")], prev_status=prev); self.assertEqual(st["health"]["state"], "ok")                                          # read again: green

    def test_no_oracle_read_at_all_is_red(self):
        st, bd = self.go(oracles=[oracle("base", read_ok=False), oracle("monad", read_ok=False)], unread=["base", "monad"])
        self.assertEqual((st["health"]["state"], bd["color"]), ("alarm", "red"))

    def test_a_broken_chain_a_stale_signature_and_a_missing_latest_stay_red(self):
        st, bd = self.go(chain={"ok": False, "reason": "line 3 does not link"}); self.assertEqual((st["health"]["state"], bd["color"]), ("alarm", "red"))
        st, bd = self.go(sig="stale"); self.assertEqual((st["health"]["state"], bd["color"]), ("alarm", "red")); self.assertIn("signature stale", bd["message"])
        with tempfile.TemporaryDirectory() as tmp:
            w = self.watch(tmp); os.remove(os.path.join(w, "latest.json")); st, bd = self.exec_status(w)
        self.assertEqual((st["health"]["state"], bd["color"]), ("alarm", "red"))

    def test_an_unsigned_run_or_an_unpinned_key_stays_orange(self):
        st, bd = self.go(sig="none"); self.assertEqual((st["health"]["state"], bd["color"]), ("degraded", "orange"))

    def test_what_the_watch_found_is_not_in_the_words_of_the_badge(self):
        st, bd = self.go(alerts=["a score dropped"], rules_high=1); self.assertNotIn("alarm", bd["message"].lower()); self.assertNotIn("alert", bd["message"].lower())

    def test_findings_that_are_only_to_review_are_degraded_for_the_state_and_green_for_the_badge(self):
        st, bd = self.go(so={"agree": 2, "disagree": 1}); self.assertEqual((st["findings"]["state"], st["state"], bd["color"]), ("degraded", "degraded", "brightgreen"))


if __name__ == "__main__":
    unittest.main()
