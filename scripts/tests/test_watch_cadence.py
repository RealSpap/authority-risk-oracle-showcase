"""The cadence fields of status.json, the daily report condition, the bootstrap switch, the opening guard and the once-a-week Telegram summary. No network: the shells of the workflow are run for real with stand-ins for `gh`, `python3` and `sleep`; the YAML is read, not trusted."""
import contextlib, datetime, io, json, os, re, shutil, stat, subprocess, sys, tempfile, unittest
import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.abspath(os.path.join(HERE, ".."))
ROOT = os.path.abspath(os.path.join(SCRIPTS, ".."))
sys.path.insert(0, SCRIPTS); sys.path.insert(0, os.path.join(SCRIPTS, "lib"))
WFDIR = os.path.join(ROOT, ".github", "workflows")


def load_wf(name):
    d = yaml.safe_load(open(os.path.join(WFDIR, name), encoding="utf-8"))
    d["on"] = d.pop(True, d.get("on"))   # YAML 1.1 reads the key `on` as True
    return d


def daily_step():
    return next(s for s in load_wf("watch.yml")["jobs"]["watch"]["steps"] if s.get("name", "").startswith("Daily report (first run of the day"))


class TestWatchYml(unittest.TestCase):
    def setUp(self): self.d = load_wf("watch.yml"); self.text = open(os.path.join(WFDIR, "watch.yml"), encoding="utf-8").read()

    def test_the_schedule_is_the_first_slot_plus_a_second_one_30_minutes_later_and_the_manual_start_knows_the_relay_flag(self):
        self.assertEqual([x["cron"] for x in self.d["on"]["schedule"]], ["17 */6 * * *", "47 */6 * * *"])
        inp = self.d["on"]["workflow_dispatch"]["inputs"]["relay"]; self.assertEqual((inp["type"], inp["default"]), ("string", "false"))

    def test_the_header_no_longer_promises_four_a_day(self):
        self.assertNotIn("four times a day", self.text)

    def test_the_header_writes_no_cadence_by_hand_and_there_is_no_scheduled_relay(self):
        header = " ".join(l for l in self.text.split("\non:")[0].splitlines() if l.lstrip().startswith("#"))
        self.assertIn("scheduled every 6 hours", header)                                   # the schedule is the one stable fact written down
        self.assertIsNone(re.search(r"(\d+|one|two|three|four|several)\s+(to\s+\d+\s+)?(times|runs|passes)|\ba day\b|\bper day\b|\beach day\b|\bdaily\b", header, re.I), header)
        self.assertFalse(os.path.exists(os.path.join(WFDIR, "watch-relay.yml")))           # no second scheduled workflow: it would meet the same limit and add runs

    def test_no_shell_of_the_watch_has_a_workflow_input_written_into_it(self):
        # `${{ inputs.relay }}` inside `run:` is text pasted into the shell before it runs: it goes through `env:` and the shell reads a variable
        for s in self.d["jobs"]["watch"]["steps"]:
            self.assertNotIn("inputs.", s.get("run", ""), s.get("name"))
        self.assertNotIn("inputs.", daily_step()["run"])
        env = daily_step()["env"]; self.assertEqual(env["RELAY"], "${{ inputs.relay }}"); self.assertEqual(env["EVENT_NAME"], "${{ github.event_name }}")
        self.assertNotIn("github.event_name", daily_step()["run"])

    def test_the_state_check_is_told_whether_the_run_comes_from_a_script(self):
        step = next(s for s in self.d["jobs"]["watch"]["steps"] if s.get("id") == "run")
        self.assertEqual(step["env"]["WATCH_RELAY"], "${{ inputs.relay }}")

    def test_the_daily_report_is_the_first_run_of_the_utc_day_not_a_run_before_06_00(self):
        run = daily_step()["run"]
        self.assertNotIn("-lt 6", run.split("daily_digest.py")[0])
        self.assertIn("watch/digest.md", run); self.assertIn("date -u +%F", run); self.assertIn("watch/.digest_attempt", run)
        self.assertIn('[ -z "$RELAY" ] || [ "$RELAY" = false ]', run)                   # a person is a run whose relay input is empty or exactly false: a script does not force the report
        self.assertNotIn('"$RELAY" != true', run)                                        # the old test let a script that sends True or 1 force the report
        self.assertEqual(self.text.count("-lt 6"), 1)                                  # only the inactive daily-mode summary still depends on the hour (not changed here): the weekly one now follows the day's report

    def test_the_mark_of_the_attempt_is_written_before_the_attempt(self):
        run = daily_step()["run"]
        self.assertLess(run.index("> watch/.digest_attempt"), run.index("daily_digest.py"))

    def run_daily(self, cwd, event="schedule", relay="", digest_rc=1, record_fails=False, sign_rc=0, redact_rc=0, record_fails_at=0, pub=None):
        """The whole shell of the step, with stand-ins for python3, timeout and the branch script: returns the number of times the report was attempted."""
        run = daily_step()["run"]
        os.makedirs(os.path.join(cwd, "bin"), exist_ok=True); os.makedirs(os.path.join(cwd, "scripts"), exist_ok=True); os.makedirs(os.path.join(cwd, "watch"), exist_ok=True)
        open(os.path.join(cwd, "bin", "python3"), "w").write('#!/bin/bash\necho "$@" >> "$CALLS"\ncase "$*" in *daily_digest.py*) if [ "$DIGEST_RC" = 0 ]; then printf "# Authority risk digest, %s 01:20 UTC\\n" "$(date -u +%F)" > watch/digest.md; fi; exit "$DIGEST_RC" ;; *redact_signers.py*) exit "${REDACT_RC:-0}" ;; *sign_run.py*) exit "${SIGN_RC:-0}" ;; esac\nexit 0\n')
        open(os.path.join(cwd, "bin", "timeout"), "w").write('#!/bin/bash\nshift\nexec "$@"\n')
        open(os.path.join(cwd, "scripts", "watch_branch.sh"), "w").write('echo "record $*" >> "$CALLS"\nn=$(grep -c "^record " "$CALLS")\n[ "${RECORD_FAILS:-}" != 1 ] || exit 1\n[ -z "${RECORD_FAILS_AT:-}" ] || [ "$n" != "$RECORD_FAILS_AT" ] || exit 1\n[ -z "${PUB:-}" ] || { rm -rf "$PUB"; cp -R watch "$PUB"; }   # what is recorded on the branch: a whole copy of watch/, the next run starts from it\n')
        for n in ("python3", "timeout"): p = os.path.join(cwd, "bin", n); os.chmod(p, os.stat(p).st_mode | stat.S_IEXEC)
        calls = os.path.join(cwd, "calls.log")
        if os.path.exists(calls): os.remove(calls)   # one count per run of the step
        out = os.path.join(cwd, "github_output.txt")
        if os.path.exists(out): os.remove(out)   # one output file per run of the step, like GitHub
        env = dict(os.environ, PATH=os.path.join(cwd, "bin") + os.pathsep + os.environ["PATH"], CALLS=calls, DIGEST_RC=str(digest_rc), EVENT_NAME=event, RELAY=relay, RUNNER_TEMP=cwd, GITHUB_TOKEN="", WATCH_REMOTE="", WATCH_SIGNING_KEY="", GITHUB_OUTPUT=out, RECORD_FAILS="1" if record_fails else "", SIGN_RC=str(sign_rc), REDACT_RC=str(redact_rc), RECORD_FAILS_AT=str(record_fails_at or ""), PUB=pub or "")
        r = subprocess.run(["bash", "-e", "-c", run], cwd=cwd, env=env, capture_output=True, text=True)
        if not (record_fails or sign_rc or redact_rc or record_fails_at): self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.rc = r.returncode
        text = open(calls).read() if os.path.exists(calls) else ""
        self.output = open(out).read() if os.path.exists(out) else ""   # what the step wrote to $GITHUB_OUTPUT
        return text.count("daily_digest.py"), text

    @staticmethod
    def today(): return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")

    def test_the_condition_runs_the_report_for_the_cases_that_matter(self):
        def attempts(digest_day, event, relay, mark=None):
            with tempfile.TemporaryDirectory() as t:
                os.mkdir(os.path.join(t, "watch"))
                if digest_day: open(os.path.join(t, "watch", "digest.md"), "w").write("# Authority risk digest, %s 01:20 UTC\n" % digest_day)
                if mark: open(os.path.join(t, "watch", ".digest_attempt"), "w").write(mark + "\n")
                return self.run_daily(t, event, relay, digest_rc=0)[0]
        today = self.today()
        self.assertEqual(attempts("2000-01-01", "schedule", ""), 1)         # no report today yet: the first run of the day makes it, at any hour
        self.assertEqual(attempts(today, "schedule", ""), 0)                # already made today: a later run does not make it again
        self.assertEqual(attempts(None, "schedule", ""), 1)                 # no report at all
        self.assertEqual(attempts(today, "workflow_dispatch", "false"), 1)  # started by hand: forced, as before
        self.assertEqual(attempts(today, "workflow_dispatch", "true"), 0)   # started with relay=true: not forced
        for v in ("True", "TRUE", "1", "yes", " true", "false ", "0", "relay"):       # a script that writes the value another way is still a script
            self.assertEqual(attempts(today, "workflow_dispatch", v), 0, repr(v))
        self.assertEqual(attempts(today, "workflow_dispatch", ""), 1)         # an empty input (nobody typed it) is a person
        self.assertEqual(attempts("2000-01-01", "workflow_dispatch", "true"), 1)   # a run with relay=true on a day without a report makes it
        self.assertEqual(attempts("2000-01-01", "schedule", "", mark="2000-01-01"), 1)   # a mark of an earlier day does not block today

    def test_a_report_that_fails_is_attempted_once_a_day_not_by_every_later_run(self):
        with tempfile.TemporaryDirectory() as t:
            n1, _ = self.run_daily(t, "schedule", "", digest_rc=1)         # the report crashes: the step goes on (a warning), the mark stays
            self.assertEqual(n1, 1)
            self.assertEqual(open(os.path.join(t, "watch", ".digest_attempt")).read().strip(), self.today())
            n2, text = self.run_daily(t, "schedule", "", digest_rc=1)      # the next run of the same UTC day: no second attempt
            self.assertEqual(n2, 0, text)
            n3, _ = self.run_daily(t, "schedule", "", digest_rc=1)
            self.assertEqual(n3, 0)
            n4, _ = self.run_daily(t, "workflow_dispatch", "false", digest_rc=1)   # a person who starts it by hand still gets the attempt
            self.assertEqual(n4, 1)

    def test_a_timeout_of_the_report_also_leaves_the_mark(self):
        with tempfile.TemporaryDirectory() as t:
            n1, _ = self.run_daily(t, "schedule", "", digest_rc=124); self.assertEqual(n1, 1)
            n2, _ = self.run_daily(t, "schedule", "", digest_rc=124); self.assertEqual(n2, 0)

    # ---- revision 3 (d): the Monday summary goes out once, with the first run of the UTC day that made the day's report
    def test_the_weekly_summary_follows_the_days_report_not_the_hour(self):
        steps = self.d["jobs"]["watch"]["steps"]
        self.assertEqual(daily_step().get("id"), "digest")
        weekly = next(s for s in steps if s.get("name", "").startswith("Weekly summary on Telegram"))
        self.assertIn("steps.digest.outputs.first == '1'", weekly["if"]); self.assertIn("vars.TELEGRAM_MODE != 'daily'", weekly["if"]); self.assertTrue(weekly["if"].startswith("always()"))
        self.assertNotIn("-lt 6", weekly["run"]); self.assertIn('date -u +%u)" = 1', weekly["run"])       # still only on Monday
        self.assertLess(steps.index(daily_step()), steps.index(weekly))                                    # the output exists before the step reads it

    def test_the_first_output_is_written_after_the_record_and_only_for_the_first_run_of_the_day(self):
        run = daily_step()["run"]
        self.assertLess(run.index("watch_branch.sh record"), run.index('echo "first=1"'))
        with tempfile.TemporaryDirectory() as t:
            n1, _ = self.run_daily(t, "schedule", "", digest_rc=0); self.assertEqual(n1, 1); self.assertIn("first=1", self.output)
            n2, _ = self.run_daily(t, "schedule", "", digest_rc=0); self.assertEqual(n2, 0); self.assertEqual(self.output, "")   # the second run of the day: no report, no output: no second summary
            n3, _ = self.run_daily(t, "schedule", "", digest_rc=0); self.assertEqual(self.output, "")
            n4, _ = self.run_daily(t, "workflow_dispatch", "false", digest_rc=0); self.assertEqual(n4, 1); self.assertEqual(self.output, "")   # forced by a person: a report, but not the first of the day
            n5, _ = self.run_daily(t, "workflow_dispatch", "True", digest_rc=0); self.assertEqual((n5, self.output), (0, ""))

    def test_a_report_that_fails_still_counts_as_the_days_first_run_and_the_summary_goes_once(self):
        with tempfile.TemporaryDirectory() as t:
            n1, _ = self.run_daily(t, "schedule", "", digest_rc=1); self.assertEqual(n1, 1); self.assertIn("first=1", self.output)
            n2, _ = self.run_daily(t, "schedule", "", digest_rc=1); self.assertEqual((n2, self.output), (0, ""))

    def test_a_step_that_stops_before_the_record_leaves_no_output(self):
        with tempfile.TemporaryDirectory() as t:
            n1, _ = self.run_daily(t, "schedule", "", digest_rc=0, record_fails=True)                  # even the mark cannot be recorded: nothing is attempted
            self.assertNotEqual(self.rc, 0); self.assertNotIn("first=1", self.output); self.assertEqual(n1, 0)
        with tempfile.TemporaryDirectory() as t, tempfile.TemporaryDirectory() as pub:
            n2, _ = self.run_daily(t, "schedule", "", digest_rc=0, record_fails_at=2, pub=os.path.join(pub, "p"))   # the report was made, its record fails
            self.assertNotEqual(self.rc, 0); self.assertNotIn("first=1", self.output); self.assertEqual(n2, 1)

    # ---- revision 4 (P2-b): the mark of the attempt is published ALONE, before the attempt, so that a failed re-signature (or a failed record) leaves one attempt a UTC day, never one per run
    def started_from(self, pub, t):
        """a new run: a clean workspace holding what the previous run recorded on the branch"""
        shutil.copytree(pub, os.path.join(t, "watch"))

    def test_the_mark_is_recorded_alone_before_the_attempt_and_the_report_after_the_signature(self):
        run = daily_step()["run"]
        self.assertEqual(run.count("watch_branch.sh record"), 2)
        self.assertLess(run.index("> watch/.digest_attempt"), run.index("watch_branch.sh record"))
        self.assertLess(run.index("watch_branch.sh record"), run.index("daily_digest.py"))                # the mark first
        self.assertLess(run.index("sign_run.py"), run.rindex("watch_branch.sh record"))                   # the report after the signature
        with tempfile.TemporaryDirectory() as t, tempfile.TemporaryDirectory() as pub:
            n, text = self.run_daily(t, "schedule", "", digest_rc=0, pub=os.path.join(pub, "p"))
            recs = [l for l in text.splitlines() if l.startswith("record ") or "daily_digest" in l or "sign_run" in l]
            self.assertEqual(n, 1)
            self.assertTrue(recs[0].startswith("record record Daily report attempt "), recs); self.assertIn("daily_digest.py", recs[1]); self.assertIn("sign_run.py", recs[2]); self.assertTrue(recs[3].startswith("record record Daily report "), recs)
            self.assertNotIn("attempt", recs[3])

    def test_a_failed_resignature_leaves_the_mark_published_and_never_the_unsigned_report(self):
        with tempfile.TemporaryDirectory() as t, tempfile.TemporaryDirectory() as pub:
            p = os.path.join(pub, "p")
            n1, text = self.run_daily(t, "schedule", "", digest_rc=0, sign_rc=1, pub=p, record_fails=False)
            self.assertEqual(self.rc, 1, text); self.assertEqual(n1, 1); self.assertNotIn("first=1", self.output)
            recs = [l for l in text.splitlines() if l.startswith("record ")]
            self.assertEqual(len(recs), 1, recs); self.assertIn("attempt", recs[0])                       # only the mark was recorded: the digest, changed and not signed, never left the runner
            self.assertEqual(open(os.path.join(p, ".digest_attempt")).read().strip(), self.today())     # the mark is on the branch
            self.assertFalse(os.path.exists(os.path.join(p, "digest.md")))                                # and what is on the branch holds no report of the failed run
            with tempfile.TemporaryDirectory() as t2:
                self.started_from(p, t2)
                n2, text2 = self.run_daily(t2, "schedule", "", digest_rc=0, sign_rc=1, pub=p); self.assertEqual(n2, 0, text2)       # the next run of the day: no new attempt
                self.assertEqual(self.output, "")
            with tempfile.TemporaryDirectory() as t3:
                self.started_from(p, t3)
                n3, _ = self.run_daily(t3, "workflow_dispatch", "false", digest_rc=0, sign_rc=1, pub=p); self.assertEqual(n3, 1)   # a person who starts it by hand still gets one

    def test_a_refused_redaction_or_a_failed_check_is_bounded_the_same_way(self):
        for kw in (dict(redact_rc=1),):
            with tempfile.TemporaryDirectory() as t, tempfile.TemporaryDirectory() as pub:
                p = os.path.join(pub, "p")
                n1, text = self.run_daily(t, "schedule", "", digest_rc=0, pub=p, record_fails=False, **kw); self.assertNotEqual(self.rc, 0); self.assertEqual(n1, 1)
                self.assertEqual(open(os.path.join(p, ".digest_attempt")).read().strip(), self.today())
                with tempfile.TemporaryDirectory() as t2:
                    self.started_from(p, t2); n2, _ = self.run_daily(t2, "schedule", "", digest_rc=0, pub=p, **kw); self.assertEqual(n2, 0)

    def test_a_failed_record_of_the_report_leaves_the_mark_published_and_the_day_bounded(self):
        with tempfile.TemporaryDirectory() as t, tempfile.TemporaryDirectory() as pub:
            p = os.path.join(pub, "p")
            n1, text = self.run_daily(t, "schedule", "", digest_rc=0, record_fails_at=2, pub=p); self.assertEqual((n1, self.rc), (1, 1)); self.assertNotIn("first=1", self.output)
            self.assertEqual(open(os.path.join(p, ".digest_attempt")).read().strip(), self.today())
            with tempfile.TemporaryDirectory() as t2:
                self.started_from(p, t2); n2, _ = self.run_daily(t2, "schedule", "", digest_rc=0, pub=p); self.assertEqual(n2, 0)

    def test_when_the_mark_cannot_be_published_nothing_is_attempted_and_the_step_says_so(self):
        with tempfile.TemporaryDirectory() as t:
            n, text = self.run_daily(t, "schedule", "", digest_rc=0, record_fails_at=1)
            self.assertEqual((n, self.rc), (0, 1)); self.assertNotIn("first=1", self.output)
            self.assertNotIn("sign_run.py", text)

    def test_a_healthy_day_is_unchanged_one_report_one_first_output_and_two_commits(self):
        with tempfile.TemporaryDirectory() as t, tempfile.TemporaryDirectory() as pub:
            n1, text = self.run_daily(t, "schedule", "", digest_rc=0, pub=os.path.join(pub, "p"))
            self.assertEqual((n1, self.rc), (1, 0)); self.assertIn("first=1", self.output)
            self.assertEqual(len([l for l in text.splitlines() if l.startswith("record ")]), 2)

    def test_every_action_the_watch_uses_is_still_pinned_to_a_commit(self):
        uses = re.findall(r"uses: (\S+)", self.text); self.assertTrue(uses)
        for u in uses: self.assertRegex(u, r"^actions/[a-z-]+@[0-9a-f]{40}$")


class TestBootstrapSwitchAndTheRelay(unittest.TestCase):
    """WATCH_BOOTSTRAP means 'a person started this run': a run started by the relay is never one."""
    PIN = "ab" * 32

    def check(self, **kw):
        import check_previous_state as cps
        with tempfile.TemporaryDirectory() as t:
            return cps.check(t, pins=(self.PIN,), require_signature=True, **kw)

    def test_a_run_started_by_hand_still_takes_the_switch(self):
        code, lines = self.check(bootstrap_env=True, event="workflow_dispatch", relay=False)
        self.assertEqual(code, 0, lines); self.assertTrue([l for l in lines if l.startswith("ALARM WATCH_BOOTSTRAP accepted")])

    def test_a_run_started_with_relay_true_never_takes_the_switch_and_says_so(self):
        code, lines = self.check(bootstrap_env=True, event="workflow_dispatch", relay=True)
        self.assertEqual(code, 1, lines)
        self.assertTrue([l for l in lines if l.startswith("ALARM WATCH_BOOTSTRAP is set but this run was not started by hand") and "relay=true" in l], lines)

    def test_relay_false_does_not_change_a_scheduled_run(self):
        code, lines = self.check(bootstrap_env=True, event="schedule", relay=False)
        self.assertEqual(code, 1); self.assertTrue([l for l in lines if "event 'schedule'" in l], lines)

    def test_the_command_line_switch_is_a_person_at_a_prompt_and_is_not_touched(self):
        code, lines = self.check(bootstrap=True, event="", relay=True)
        self.assertEqual(code, 0, lines)

    def run_script(self, relay):
        with tempfile.TemporaryDirectory() as t:
            w = os.path.join(t, "watch"); os.mkdir(w)
            env = {k: v for k, v in os.environ.items() if k not in ("WATCH_SIGNING_KEY", "WATCH_PIN", "WATCH_BOOTSTRAP", "WATCH_RELAY", "HAS_SIGNING_KEY", "GITHUB_REPOSITORY", "GITHUB_EVENT_NAME", "WATCH_LAST_SUCCESS_UTC")}
            env.update(HAS_SIGNING_KEY="true", WATCH_PIN=self.PIN, WATCH_BOOTSTRAP="1", GITHUB_EVENT_NAME="workflow_dispatch", WATCH_RELAY=relay)
            r = subprocess.run([sys.executable, os.path.join(SCRIPTS, "check_previous_state.py"), "--watch", w], env=env, capture_output=True, text=True)
        return r.returncode, r.stdout + r.stderr

    def test_the_script_reads_the_relay_variable_the_workflow_hands_it(self):
        rc, text = self.run_script("true"); self.assertEqual(rc, 1, text)
        rc, text = self.run_script("false"); self.assertEqual(rc, 0, text)
        rc, text = self.run_script(""); self.assertEqual(rc, 0, text)        # a scheduled run has no input; a dispatch started by hand has "false"

    def test_any_other_value_than_false_or_empty_is_a_script_and_never_takes_the_switch(self):
        # a script that sends True, 1, TRUE, yes or " true" is a script all the same: the switch is refused, the alarm says so
        for v in ("true", "True", "TRUE", "1", "yes", " true", "true ", "0", "false ", "False", "relay"):
            rc, text = self.run_script(v)
            self.assertEqual(rc, 1, (v, text)); self.assertIn("started with relay=true by a script", text, v)
        for v in ("false", ""):
            rc, text = self.run_script(v); self.assertEqual(rc, 0, (v, text))


class TestStatusCadence(unittest.TestCase):
    def watch(self, tmp, lines, run_utc="2026-11-08T13:22:25Z", latest=True, mode="degraded"):
        """mode ok: signed by a pinned key, chain intact, nothing fired; degraded: no signature.json; alarm: the watch raised an alarm."""
        import audit_public
        w = os.path.join(tmp, "watch"); os.makedirs(os.path.join(w, "scores"))
        if latest: json.dump({"run_utc": run_utc, "oracles": [], "unread": [], "alerts": (["a score dropped"] if mode == "alarm" else []), "total_targets": 1, "stale_total": 0}, open(os.path.join(w, "latest.json"), "w"))
        if mode == "ok": json.dump({"signed": True, "public_key": sorted(audit_public.PINNED_KEYS)[0], "run_utc": run_utc}, open(os.path.join(w, "signature.json"), "w"))
        json.dump({"ok": True, "lines": 0}, open(os.path.join(w, "chain.json"), "w"))
        if lines is not None: open(os.path.join(w, "trend.jsonl"), "w").write("\n".join(lines) + "\n")
        return w

    @staticmethod
    def tl(*times): return [json.dumps({"run_utc": t}) for t in times]

    def status(self, w):
        import run_status
        argv, sys.argv = sys.argv, ["run_status.py", "--watch", w]
        try:
            with contextlib.redirect_stdout(io.StringIO()): run_status.main()
        finally: sys.argv = argv
        return json.load(open(os.path.join(w, "status.json")))

    def test_counts_the_runs_of_the_last_seven_days_up_to_and_including_this_one(self):
        import run_status
        W = tempfile.mkdtemp()
        try:
            open(os.path.join(W, "trend.jsonl"), "w").write("\n".join(self.tl("2026-11-01T13:22:25Z", "2026-11-01T13:22:26Z", "2026-11-02T00:00:00Z", "2026-11-08T05:58:38Z", "2026-11-08T05:58:38Z")) + "\n")
            n, prev, gap = run_status.cadence(W, "2026-11-08T13:22:25Z")
            self.assertEqual(n, 4)                    # 11-01 13:22:25 is exactly 7 days before: out; 11-01 13:22:26, 11-02 and 11-08 05:58:38 in (a duplicate counts once); this run counts
            self.assertEqual(prev.strftime("%Y-%m-%dT%H:%M:%SZ"), "2026-11-08T05:58:38Z"); self.assertAlmostEqual(gap, 7.4, 1)
        finally: shutil.rmtree(W)

    def test_this_run_is_counted_even_if_the_trend_line_is_missing_and_a_future_line_is_ignored(self):
        import run_status
        W = tempfile.mkdtemp()
        try:
            open(os.path.join(W, "trend.jsonl"), "w").write("\n".join(self.tl("2026-11-09T00:00:00Z", "not a date") + ["not json", "[]"]) + "\n")
            self.assertEqual(run_status.cadence(W, "2026-11-08T13:22:25Z"), (1, None, None))
        finally: shutil.rmtree(W)

    def test_an_unreadable_record_is_none_never_zero(self):
        import run_status
        W = tempfile.mkdtemp()
        try:
            self.assertEqual(run_status.cadence(W, "2026-11-08T13:22:25Z"), (None, None, None))      # no trend.jsonl
            self.assertEqual(run_status.cadence(W, "garbage"), (None, None, None))
        finally: shutil.rmtree(W)

    def test_status_json_carries_the_three_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = self.status(self.watch(tmp, self.tl("2026-11-08T05:58:38Z", "2026-11-07T21:48:00Z")))
            self.assertEqual((s["runs_7d"], s["previous_run_utc"], s["hours_since_previous_run"]), (3, "2026-11-08T05:58:38Z", 7.4))
            self.assertFalse([r for r in s["reasons"] if "silent" in r])
        with tempfile.TemporaryDirectory() as tmp:
            s = self.status(self.watch(tmp, self.tl("2026-11-07T21:48:00Z")))
            self.assertEqual(s["hours_since_previous_run"], 15.6); self.assertTrue([r for r in s["reasons"] if "silent for 15.6 hours" in r])
        with tempfile.TemporaryDirectory() as tmp:
            s = self.status(self.watch(tmp, None)); self.assertEqual((s["runs_7d"], s["previous_run_utc"], s["hours_since_previous_run"]), (None, None, None))

    def test_a_long_silence_is_a_reason_and_changes_no_state_from_ok_degraded_or_alarm(self):
        # revision 3: the baseline is each of the three states in turn, read from a real status.json: a mutant that forces degraded (or alarm, or ok) now fails on one of them
        for mode, expected in (("ok", "ok"), ("degraded", "degraded"), ("alarm", "alarm")):
            states = {}
            for gap_h, last in ((7, "2026-11-08T06:22:25Z"), (15.6, "2026-11-07T21:48:00Z")):
                with tempfile.TemporaryDirectory() as tmp:
                    s = self.status(self.watch(tmp, self.tl(last), mode=mode)); states[gap_h] = s
            self.assertEqual(states[7]["state"], expected, (mode, states[7]["reasons"]))      # the fixture is what it says it is
            self.assertEqual(states[15.6]["state"], expected, (mode, states[15.6]["reasons"]))    # the silence changes nothing
            self.assertFalse([r for r in states[7]["reasons"] if "silent" in r], mode)
            self.assertEqual(len([r for r in states[15.6]["reasons"] if "silent for 15.6 hours" in r]), 1, mode)
            self.assertEqual(sorted(set(states[15.6]["reasons"]) - set(states[7]["reasons"])), sorted(r for r in states[15.6]["reasons"] if "silent" in r), mode)   # and adds that reason only
        with tempfile.TemporaryDirectory() as tmp:
            s = self.status(self.watch(tmp, self.tl("2026-11-07T21:48:00Z"), mode="ok"))
            self.assertEqual(s["reasons"], [r for r in s["reasons"] if "silent" in r])     # an ok run with a long silence has that one reason and nothing else
            self.assertEqual(s["state"], "ok")

    def test_without_latest_json_the_run_is_counted_once_not_twice(self):
        # trend.py wrote this run's line with the clock of its own step, a few seconds before run_status.py reads the clock again: those two times are one run
        now = datetime.datetime.now(datetime.timezone.utc); f = lambda d: d.strftime("%Y-%m-%dT%H:%M:%SZ")
        with tempfile.TemporaryDirectory() as tmp:
            w = self.watch(tmp, self.tl(f(now - datetime.timedelta(hours=7)), f(now - datetime.timedelta(seconds=40))), latest=False)
            s = self.status(w)
            self.assertEqual(s["runs_7d"], 2)                                            # the earlier run and this one
            self.assertEqual(s["previous_run_utc"], f(now - datetime.timedelta(hours=7))); self.assertAlmostEqual(s["hours_since_previous_run"], 7.0, 1)
            self.assertIn("latest.json missing", s["reasons"])                           # the state is already an alarm, the count is still honest

    def test_without_latest_json_a_run_that_is_not_this_one_is_still_a_run(self):
        now = datetime.datetime.now(datetime.timezone.utc); f = lambda d: d.strftime("%Y-%m-%dT%H:%M:%SZ")
        with tempfile.TemporaryDirectory() as tmp:
            s = self.status(self.watch(tmp, self.tl(f(now - datetime.timedelta(minutes=30))), latest=False))     # 30 minutes before: another run
            self.assertEqual(s["runs_7d"], 2)

    def test_with_latest_json_only_the_same_second_is_the_same_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = self.status(self.watch(tmp, self.tl("2026-11-08T13:22:25Z", "2026-11-08T13:22:00Z")))     # 25 seconds earlier but a different run: both count
            self.assertEqual(s["runs_7d"], 2)

    def test_the_api_page_describes_the_three_fields(self):
        row = next(l for l in open(os.path.join(ROOT, "watch", "API.md"), encoding="utf-8").read().splitlines() if l.startswith("| `status.json` |"))
        for k in ("runs_7d", "previous_run_utc", "hours_since_previous_run", "NOT in the signed manifest"): self.assertIn(k, row)


class TestOpeningGuard(unittest.TestCase):
    """The first job: a scheduled run whose slot was served (another run of watch.yml created in the 45 minutes before it) is cancelled, never recorded as a success; any doubt lets it go on."""
    ME = 5000
    T0 = datetime.datetime(2026, 11, 10, 12, 50, 0, tzinfo=datetime.timezone.utc)

    @staticmethod
    def guard_step():
        wf = load_wf("watch.yml"); return wf["jobs"]["guard"]["steps"][0]

    def rid(self, rid, seconds_before, conclusion="success", status="completed", ran=25 * 60, **kw):
        c = self.T0 - datetime.timedelta(seconds=seconds_before); f = "%Y-%m-%dT%H:%M:%SZ"
        d = {"id": rid, "status": status, "conclusion": conclusion, "created_at": c.strftime(f), "run_started_at": c.strftime(f), "updated_at": (c + datetime.timedelta(seconds=ran)).strftime(f), "event": "workflow_dispatch"}   # ran: seconds between the start and the last update
        d.update(kw); return d

    def me(self): return self.rid(self.ME, 0, None, "in_progress", event="schedule")

    def run_guard(self, runs, event="schedule", raw=None, list_fails=False, cancel_fails=False, me_in_list=True, schedule="17 */6 * * *", guard_slot=""):
        step = self.guard_step()
        with tempfile.TemporaryDirectory() as cwd:
            os.makedirs(os.path.join(cwd, "bin"))
            open(os.path.join(cwd, "bin", "gh"), "w").write('#!/bin/bash\necho "gh $*" >> "$CALLS"\ncase "$*" in\n *"-X POST"*) [ "${CANCEL_FAILS:-}" != 1 ] || { echo "HTTP 403: Resource not accessible by integration" >&2; exit 1; }; exit 0 ;;\n *"/runs?per_page=30"*) [ "${LIST_FAILS:-}" != 1 ] || { echo "HTTP 502: bad gateway" >&2; exit 1; }; cat "$RUNS_FILE"; exit 0 ;;\nesac\nexit 9\n')
            open(os.path.join(cwd, "bin", "sleep"), "w").write('#!/bin/bash\necho "sleep $*" >> "$CALLS"\necho "output-at-sleep: $(tr \'\\n\' , < "$GITHUB_OUTPUT")" >> "$CALLS"\nexit 0\n')
            for n in ("gh", "sleep"): q = os.path.join(cwd, "bin", n); os.chmod(q, os.stat(q).st_mode | stat.S_IEXEC)
            body = raw if raw is not None else json.dumps({"total_count": len(runs) + 1, "workflow_runs": ([self.me()] if me_in_list else []) + runs})
            open(os.path.join(cwd, "runs.json"), "w").write(body)
            calls = os.path.join(cwd, "calls.log")
            out = os.path.join(cwd, "github_output.txt"); open(out, "w").close()
            env = dict(os.environ, PATH=os.path.join(cwd, "bin") + os.pathsep + os.environ["PATH"], CALLS=calls, RUNS_FILE=os.path.join(cwd, "runs.json"), RUNNER_TEMP=cwd, GH_TOKEN="x", EVENT_NAME=event, SCHEDULE=schedule, RUN_ID=str(self.ME), REPO="RealSpap/authority-risk-oracle-showcase",
                       GITHUB_OUTPUT=out, GUARD_SLOT=guard_slot, LIST_FAILS="1" if list_fails else "", CANCEL_FAILS="1" if cancel_fails else "")
            r = subprocess.run(["bash", "-e", "-c", step["run"]], cwd=cwd, env=env, capture_output=True, text=True)
            c = open(calls).read().splitlines() if os.path.exists(calls) else []
            self.gh_output = open(out).read()   # what the step wrote to $GITHUB_OUTPUT
        return r.returncode, r.stdout + r.stderr, c

    CANCEL = "gh api -X POST repos/RealSpap/authority-risk-oracle-showcase/actions/runs/5000/cancel"

    def test_a_scheduled_run_whose_slot_was_served_20_minutes_ago_is_cancelled_with_a_notice(self):
        rc, out, calls = self.run_guard([self.rid(4000, 20 * 60)])
        self.assertEqual([c for c in calls if "POST" in c], [self.CANCEL])
        self.assertIn("::notice title=Slot already served::run 4000", out); self.assertIn("20 minutes", out); self.assertIn("(slot rule)", out)
        self.assertEqual([c for c in calls if c.startswith("sleep")], ["sleep 120"])             # it waits for the cancel to land
        # the fake cancel does not stop the shell: the fallback is the end of the job in RED, never "this run goes on" (the watch job is skipped through the output)
        self.assertEqual(rc, 1, out); self.assertIn("::error title=Opening guard::the cancel was accepted but had not been applied after 2 minutes", out); self.assertNotIn("this run goes on", out)
        self.assertEqual(self.gh_output, "served=true\n")

    def test_the_window_is_45_minutes_included_and_a_second_more_is_a_run(self):
        for sec, cancelled in ((44 * 60 + 59, True), (45 * 60, True), (45 * 60 + 1, False), (3 * 3600, False), (13 * 3600, False)):
            rc, out, calls = self.run_guard([self.rid(4000, sec)])
            self.assertEqual(rc, 1 if cancelled else 0, (sec, out)); self.assertEqual(bool([c for c in calls if "POST" in c]), cancelled, sec)

    def test_a_run_that_served_nothing_does_not_count_and_any_other_run_does(self):
        for concl, status, cancelled in (("cancelled", "completed", False), ("skipped", "completed", False), ("success", "completed", True), ("failure", "completed", True), ("timed_out", "completed", True),
                                         (None, "in_progress", True), (None, "queued", True), (None, "pending", True), (None, "waiting", True)):
            rc, out, calls = self.run_guard([self.rid(4000, 600, concl, status)])
            self.assertEqual(bool([c for c in calls if "POST" in c]), cancelled, (concl, status))

    def test_two_runs_never_cancel_each_other_only_an_earlier_one_counts(self):
        rc, out, calls = self.run_guard([self.rid(6000, -300)])          # created 5 minutes AFTER this run: it is the other's business
        self.assertEqual([c for c in calls if "POST" in c], []); self.assertIn("no other run", out)
        rc, out, calls = self.run_guard([self.rid(6000, 0)])             # same second, a later id: not earlier
        self.assertEqual([c for c in calls if "POST" in c], [])
        rc, out, calls = self.run_guard([self.rid(4000, 0)])             # same second, an earlier id: earlier
        self.assertEqual([c for c in calls if "POST" in c], [self.CANCEL])

    def test_a_run_started_by_hand_or_a_push_is_never_checked(self):
        for ev in ("workflow_dispatch", "push", "workflow_run", ""):
            rc, out, calls = self.run_guard([self.rid(4000, 60)], event=ev)
            self.assertEqual((rc, calls), (0, []), ev)                    # not even a read

    def test_any_doubt_lets_the_run_go_on_never_a_silent_stop(self):
        cases = {"gh fails": dict(runs=[], list_fails=True), "html": dict(runs=[], raw="<html>Bad gateway</html>"), "empty": dict(runs=[], raw=""), "no list": dict(runs=[], raw='{"message": "Not Found"}'),
                 "this run missing": dict(runs=[self.rid(4000, 60)], me_in_list=False), "date unreadable": dict(runs=[self.rid(4000, 60, created_at="hier")]),
                 "no date": dict(runs=[{"id": 4000, "status": "completed", "conclusion": "success"}]), "no id": dict(runs=[{"status": "completed", "conclusion": "success", "created_at": "2026-11-10T12:40:00Z"}])}
        for name, kw in cases.items():
            rc, out, calls = self.run_guard(**kw)
            self.assertEqual(rc, 0, (name, out)); self.assertEqual([c for c in calls if "POST" in c], [], name); self.assertIn("::warning title=Opening guard::", out, name); self.assertIn("this run goes on", out, name)

    def test_a_refused_cancel_lets_the_run_go_on_and_says_so(self):
        rc, out, calls = self.run_guard([self.rid(4000, 600)], cancel_fails=True)
        self.assertEqual(rc, 0, out); self.assertIn("the cancel request was refused", out); self.assertIn("this run goes on", out); self.assertEqual([c for c in calls if c.startswith("sleep")], [])

    def test_the_guard_job_is_first_alone_in_having_actions_write_and_cannot_write_anything_else(self):
        wf = load_wf("watch.yml"); jobs = wf["jobs"]
        self.assertEqual(list(jobs), ["guard", "watch"])
        self.assertEqual(jobs["guard"]["permissions"], {"actions": "write"})                           # no contents: it could not push to watch-data or main
        self.assertNotIn("permissions", jobs["watch"])                                                 # the watch job keeps the workflow's: contents write, actions read
        self.assertEqual(wf["permissions"], {"contents": "write", "actions": "read"})
        self.assertEqual(jobs["watch"]["needs"], "guard"); self.assertEqual(jobs["watch"]["if"], "${{ !cancelled() && needs.guard.outputs.served != 'true' }}")
        self.assertEqual(jobs["guard"]["outputs"], {"served": "${{ steps.guard.outputs.served }}"})
        self.assertEqual(len(jobs["guard"]["steps"]), 1)
        g = jobs["guard"]["steps"][0]; text = g["run"]
        self.assertEqual(g["id"], "guard")
        self.assertNotIn("uses", g); self.assertNotIn("git ", text); self.assertNotIn("watch-data", text); self.assertNotIn("checkout", text)    # no code is run from the repository, nothing is recorded
        self.assertEqual(g["env"]["EVENT_NAME"], "${{ github.event_name }}"); self.assertEqual(g["env"]["SCHEDULE"], "${{ github.event.schedule }}"); self.assertEqual(g["env"]["GUARD_SLOT"], "${{ vars.WATCH_GUARD_SLOT }}"); self.assertNotIn("${{", text)   # every context value goes through env
        self.assertLessEqual(jobs["guard"]["timeout-minutes"], 5)

    def test_the_cancelled_run_is_never_the_anchor_of_the_rollback_check(self):
        # the anchor step takes the newest run with status=success: a run the guard cancelled is `cancelled`, so the anchor is still the last run that really published
        wf = load_wf("watch.yml"); step = next(s for s in wf["jobs"]["watch"]["steps"] if s.get("id") == "anchor")
        self.assertIn("status=success", step["run"])
        runs = [self.rid(5000, 0, "cancelled"), self.rid(4000, 30 * 60, "success"), self.rid(3000, 6 * 3600, "success")]     # newest first, like the API
        with tempfile.TemporaryDirectory() as cwd:
            os.makedirs(os.path.join(cwd, "bin"))
            # a `gh` that applies the filter of the URL like GitHub does, then the --jq of the step: first run's created_at
            open(os.path.join(cwd, "bin", "gh"), "w").write('#!/bin/bash\npython3 - "$2" <<\'PY\'\nimport json, os, sys\nruns = json.load(open(os.environ["RUNS_FILE"]))\nif "status=success" in sys.argv[1]: runs = [r for r in runs if r["conclusion"] == "success"]\nprint(runs[0]["created_at"] if runs else "")\nPY\n')
            q = os.path.join(cwd, "bin", "gh"); os.chmod(q, os.stat(q).st_mode | stat.S_IEXEC)
            open(os.path.join(cwd, "runs.json"), "w").write(json.dumps(runs)); out = os.path.join(cwd, "out.txt"); open(out, "w").close()
            env = dict(os.environ, PATH=os.path.join(cwd, "bin") + os.pathsep + os.environ["PATH"], RUNS_FILE=os.path.join(cwd, "runs.json"), GITHUB_OUTPUT=out, GITHUB_REPOSITORY="x/y", GH_TOKEN="x")
            r = subprocess.run(["bash", "-e", "-c", step["run"]], cwd=cwd, env=env, capture_output=True, text=True); self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(open(out).read().strip(), "utc=" + runs[1]["created_at"])                 # the run at -30 min, not the cancelled one at 0


    # ---- revision 4: the rule per slot, the early failure, the cancel accepted but late, the calculator written out by the job

    @staticmethod
    def utc(*a): return datetime.datetime(*a, tzinfo=datetime.timezone.utc)

    def ago(self, when): return (self.T0 - when).total_seconds()

    def decide(self, runs, **kw):
        """-> (cancelled: bool, output of the step)"""
        rc, out, calls = self.run_guard(runs, **kw)
        return bool([c for c in calls if "POST" in c]), out

    def test_the_slot_rule_catches_a_run_created_hours_before_which_the_45_minutes_never_saw(self):
        # the real case of 8 Nov 2026: the late copy of the 00:17 slot is created at 05:58:22; a script run created at 00:43 served that slot 5 hours earlier
        self.T0 = self.utc(2026, 11, 8, 5, 58, 22)
        cancelled, out = self.decide([self.rid(4000, self.ago(self.utc(2026, 11, 8, 0, 43, 22)))])
        self.assertTrue(cancelled, out); self.assertIn("(slot rule)", out); self.assertIn("315 minutes", out)
        # the same run 5 hours later than the script's run (nobody served the slot): it goes on, it is the only copy
        cancelled, out = self.decide([self.rid(4000, self.ago(self.utc(2026, 11, 7, 18, 43, 22)))])        # the script run of the PREVIOUS slot (18:17)
        self.assertFalse(cancelled, out); self.assertIn("no other run", out)

    def test_the_slot_starts_5_minutes_before_it_to_the_second(self):
        self.T0 = self.utc(2026, 11, 10, 13, 30, 0)       # 73 minutes after the 12:17 slot: the 45 minutes cannot see the runs below
        for when, cancelled in (((12, 12, 0), True), ((12, 11, 59), False), ((12, 17, 0), True), ((13, 29, 59), True), ((6, 20, 0), False)):
            got, out = self.decide([self.rid(4000, self.ago(self.utc(2026, 11, 10, *when)))])
            self.assertEqual(got, cancelled, (when, out))

    def test_the_slot_is_the_one_before_this_runs_own_creation_across_midnight_and_the_6_hour_edges(self):
        for t0, when, cancelled in ((self.utc(2026, 11, 10, 0, 10, 0), self.utc(2026, 11, 9, 18, 12, 0), True),       # slot 18:17 of the day before, 5 minutes earlier
                                    (self.utc(2026, 11, 10, 0, 10, 0), self.utc(2026, 11, 9, 18, 11, 59), False),
                                    (self.utc(2026, 11, 10, 12, 10, 0), self.utc(2026, 11, 10, 6, 12, 0), True),      # before the slot of 12:17: the slot is 06:17
                                    (self.utc(2026, 11, 10, 12, 10, 0), self.utc(2026, 11, 10, 6, 11, 59), False),
                                    (self.utc(2026, 11, 10, 12, 18, 0), self.utc(2026, 11, 10, 6, 40, 0), False),     # one minute after the slot: it is 12:17 now, the 06:40 run is the previous slot's
                                    (self.utc(2026, 11, 10, 12, 18, 0), self.utc(2026, 11, 10, 12, 12, 0), True),
                                    (self.utc(2026, 12, 1, 0, 10, 0), self.utc(2026, 11, 30, 18, 12, 0), True)):      # change of month
            self.T0 = t0
            got, out = self.decide([self.rid(4000, self.ago(when))])
            self.assertEqual(got, cancelled, (str(t0), str(when), out))

    def test_the_second_slot_goes_on_when_the_first_was_skipped_and_is_cancelled_when_the_first_ran(self):
        # GitHub skipped the 12:17 run; the 12:47 run must be the one that serves the slot
        self.T0 = self.utc(2026, 11, 10, 12, 49, 0)
        self.assertFalse(self.decide([self.rid(4000, self.ago(self.utc(2026, 11, 10, 6, 20, 0)))], schedule="47 */6 * * *")[0])        # the last run is the 06:17 one: nothing served this slot
        got, out = self.decide([self.rid(4000, self.ago(self.utc(2026, 11, 10, 12, 20, 0)))], schedule="47 */6 * * *")                 # the 12:17 run was created at 12:20: 29 minutes before
        self.assertTrue(got, out)
        self.assertFalse(self.decide([self.rid(4000, self.ago(self.utc(2026, 11, 10, 12, 20, 0)), conclusion="failure", ran=120)], schedule="47 */6 * * *")[0])   # a first run that failed in 2 minutes served nothing: the second one goes on

    def test_a_late_copy_of_the_first_slot_is_cancelled_by_the_run_of_the_second_slot(self):
        self.T0 = self.utc(2026, 11, 10, 12, 58, 0)       # the 12:17 copy arrives late, after the 12:47 run was created
        got, out = self.decide([self.rid(4000, self.ago(self.utc(2026, 11, 10, 12, 49, 0)))], schedule="17 */6 * * *")
        self.assertTrue(got, out); self.assertIn("slot", out)
        self.assertEqual(self.guard_step().get("name", "")[:13], "Opening guard")

    def test_the_cron_of_the_event_decides_the_slot_not_a_constant(self):
        self.T0 = self.utc(2026, 11, 8, 14, 22, 56)       # the real daily run of 8 Nov (cron 23 7 * * *)
        x = self.rid(4000, self.ago(self.utc(2026, 11, 8, 7, 18, 0)))
        self.assertTrue(self.decide([x], schedule="23 7 * * *")[0])                       # slot 07:23, minus 5 minutes = 07:18
        self.assertFalse(self.decide([self.rid(4000, self.ago(self.utc(2026, 11, 8, 7, 17, 59)))], schedule="23 7 * * *")[0])
        self.assertFalse(self.decide([x], schedule="17 */6 * * *")[0])                     # with the 6-hour cron the slot is 12:17: a 07:18 run served nothing
        self.assertTrue(self.decide([x], schedule="30 14 * * *")[0])                       # a cron whose last slot is yesterday's 14:30 (14:22 is before it): the 07:18 run was created since
        self.assertFalse(self.decide([x], schedule="30 7 * * *")[0])                       # slot 07:30 today: the 07:18 run is older than the slot minus 5 minutes, 7 hours before this one

    def test_only_an_earlier_run_counts_under_the_slot_rule_too_and_the_same_second_goes_by_id(self):
        self.T0 = self.utc(2026, 11, 10, 13, 30, 0)
        self.assertFalse(self.decide([self.rid(6000, -60)])[0])                           # created a minute AFTER this run
        self.assertTrue(self.decide([self.rid(4000, 3000)])[0])                           # 50 minutes before: slot rule only
        self.assertTrue(self.decide([self.rid(4000, 0)])[0]); self.assertFalse(self.decide([self.rid(6000, 0)])[0])
        # another scheduled run counts like any other (a second late copy of the same slot is cancelled, the first one went on)
        self.assertTrue(self.decide([self.rid(4000, 3000, event="schedule")])[0])
        # the first of two late copies is not cancelled by the one that comes after it
        self.assertFalse(self.decide([self.rid(6000, -3000, event="schedule")])[0])

    def test_a_run_that_failed_early_did_not_serve_the_slot_the_eight_cases(self):
        self.T0 = self.utc(2026, 11, 10, 13, 30, 0)
        cases = (("success", "success", "completed", 25 * 60, True),
                 ("failure after 2 minutes", "failure", "completed", 120, False),
                 ("failure after 25 minutes", "failure", "completed", 25 * 60, True),
                 ("in progress", None, "in_progress", 25 * 60, True),
                 ("queued", None, "queued", 0, True),
                 ("cancelled", "cancelled", "completed", 60, False),
                 ("skipped", "skipped", "completed", 0, False),
                 ("timed_out", "timed_out", "completed", 150 * 60, True))
        for name, conclusion, status, ran, cancelled in cases:
            for created in (self.utc(2026, 11, 10, 12, 20, 0), self.utc(2026, 11, 10, 13, 0, 0)):                 # the slot rule (73 min) and the 45-minute window (30 min)
                got, out = self.decide([self.rid(4000, self.ago(created), conclusion, status, ran=ran)])
                self.assertEqual(got, cancelled, (name, str(created), out))

    def test_ten_minutes_exactly_counts_and_a_failure_that_cannot_be_timed_does_not(self):
        self.T0 = self.utc(2026, 11, 10, 13, 30, 0); at = self.ago(self.utc(2026, 11, 10, 12, 20, 0))
        for ran, cancelled in ((0, False), (1, False), (599, False), (600, True), (601, True)):
            self.assertEqual(self.decide([self.rid(4000, at, "failure", ran=ran)])[0], cancelled, ran)
        self.assertFalse(self.decide([self.rid(4000, at, "startup_failure", ran=0)])[0])         # a workflow that never started
        self.assertTrue(self.decide([self.rid(4000, at, "startup_failure", ran=700)])[0])
        for broken in ({"updated_at": None}, {"run_started_at": None}, {"updated_at": "yesterday"}, {"run_started_at": "yesterday"}):
            rc, out, calls = self.run_guard([self.rid(4000, at, "failure", **broken)])
            self.assertEqual(rc, 0, out); self.assertEqual([c for c in calls if "POST" in c], [], broken)    # not counted: this run goes on
        r = self.rid(4000, at, "failure"); del r["updated_at"]
        self.assertFalse(self.decide([r])[0])

    def test_the_duration_of_a_failure_is_counted_from_its_start_not_from_its_creation(self):
        self.T0 = self.utc(2026, 11, 10, 13, 30, 0); f = "%Y-%m-%dT%H:%M:%SZ"
        created = self.utc(2026, 11, 10, 12, 20, 0)
        queued_long = self.rid(4000, self.ago(created), "failure", created_at=created.strftime(f), run_started_at=(created + datetime.timedelta(minutes=30)).strftime(f), updated_at=(created + datetime.timedelta(minutes=32)).strftime(f))
        self.assertFalse(self.decide([queued_long])[0])         # 30 minutes in the queue, 2 minutes of work: an early failure
        queued_long["updated_at"] = (created + datetime.timedelta(minutes=41)).strftime(f)
        self.assertTrue(self.decide([queued_long])[0])          # 11 minutes of work

    def test_two_early_failures_in_a_row_let_the_next_run_go_on_and_a_success_before_them_still_serves(self):
        self.T0 = self.utc(2026, 11, 10, 13, 30, 0)
        a = self.rid(4000, self.ago(self.utc(2026, 11, 10, 12, 29, 0)), "failure", ran=90)
        b = self.rid(4100, self.ago(self.utc(2026, 11, 10, 12, 52, 0)), "failure", ran=150)
        self.assertFalse(self.decide([a, b])[0])
        ok = self.rid(3900, self.ago(self.utc(2026, 11, 10, 12, 20, 0)), "success")
        self.assertTrue(self.decide([a, b, ok])[0])                                       # a run that really ran before them served the slot
        self.assertFalse(self.decide([a, b, self.rid(3900, self.ago(self.utc(2026, 11, 10, 12, 20, 0)), "cancelled")])[0])
        # and under the 45-minute window as well: the old test of the first revision (a failure after 2 minutes served the slot) no longer holds
        self.T0 = self.utc(2026, 11, 10, 12, 50, 0)
        self.assertFalse(self.decide([self.rid(4000, 600, "failure", ran=120)])[0])
        self.assertTrue(self.decide([self.rid(4000, 600, "failure", ran=1500)])[0])

    def test_an_unreadable_cron_lets_the_run_go_on_with_a_warning_even_when_the_window_would_cancel(self):
        for bad in ("", "@hourly", "61 * * * *", "17 */6 * *", "MON * * * *"):
            rc, out, calls = self.run_guard([self.rid(4000, 600)], schedule=bad)
            self.assertEqual(rc, 0, (bad, out)); self.assertEqual([c for c in calls if "POST" in c], [], bad)
            self.assertIn("::warning title=Opening guard::the check could not be completed", out); self.assertIn("this run goes on", out); self.assertEqual(self.gh_output, "")

    def test_the_output_served_is_written_only_when_the_cancel_was_accepted_and_before_the_wait(self):
        rc, out, calls = self.run_guard([self.rid(4000, 600)])
        self.assertEqual(self.gh_output, "served=true\n")
        at_sleep = [c for c in calls if c.startswith("output-at-sleep:")]
        self.assertEqual(at_sleep, ["output-at-sleep: served=true,"])                      # already there when the wait begins: a cancel that lands during it still leaves the watch job skipped
        rc, out, calls = self.run_guard([self.rid(4000, 600)], cancel_fails=True); self.assertEqual(self.gh_output, "")        # a refused cancel: the run goes on, the watch job starts
        rc, out, calls = self.run_guard([]); self.assertEqual((rc, self.gh_output), (0, ""))                                    # nothing served
        rc, out, calls = self.run_guard([self.rid(4000, 600)], event="workflow_dispatch"); self.assertEqual((rc, self.gh_output), (0, ""))

    def test_the_watch_job_does_not_start_after_an_accepted_cancel_or_a_cancelled_run_but_does_after_a_crashed_guard(self):
        expr = load_wf("watch.yml")["jobs"]["watch"]["if"]
        inner = re.fullmatch(r"\$\{\{ (.*) \}\}", expr).group(1)
        py = inner.replace("!cancelled()", "(not cancelled)").replace("&&", " and ").replace("needs.guard.outputs.served", "served")
        self.assertIsNone(re.search(r"[A-Za-z_]+(?<!not)(?<!and)(?<!cancelled)(?<!served)\b", re.sub(r"'true'", "", py)), py)     # nothing left that the table below does not define
        for cancelled, served, starts in ((False, "", True), (False, "true", False), (True, "", False), (True, "true", False)):
            self.assertEqual(eval(py, {"cancelled": cancelled, "served": served}), starts, (cancelled, served))
        # "(False, '', True)" is also the guard that crashed: no output, not cancelled: the Watch starts

    def test_the_slot_calculator_the_job_writes_out_is_the_very_text_of_scripts_cron_slot_py(self):
        text = self.guard_step()["run"]
        m = re.search(r"cat > \"\$T/cron_slot\.py\" <<'PY1'\n(.*?)\nPY1\n", text, re.S)
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1) + "\n", open(os.path.join(SCRIPTS, "cron_slot.py"), encoding="utf-8").read())
        self.assertIn("import cron_slot", text)

    def test_the_repository_variable_turns_the_slot_rule_off_and_keeps_the_45_minute_window(self):
        self.T0 = self.utc(2026, 11, 10, 13, 30, 0)
        slot_only = self.rid(4000, self.ago(self.utc(2026, 11, 10, 12, 20, 0)))                   # 70 minutes before: the slot rule alone sees it
        window = self.rid(4100, self.ago(self.utc(2026, 11, 10, 13, 0, 0)))                      # 30 minutes before: the window sees it
        for value, want_slot, want_window in (("", True, True), ("on", True, True), ("OFF", True, True), ("off", False, True), ("1", True, True)):      # exactly "off" and nothing else
            self.assertEqual(self.decide([slot_only], guard_slot=value)[0], want_slot, value)
            self.assertEqual(self.decide([window], guard_slot=value)[0], want_window, value)
        rc, out, calls = self.run_guard([self.rid(4100, self.ago(self.utc(2026, 11, 10, 13, 0, 0)))], guard_slot="off", schedule="not a cron")      # off: the cron is not even read
        self.assertEqual([c for c in calls if "POST" in c], [self.CANCEL])

    def test_the_real_runs_of_7_and_8_november_with_a_script_run_at_slot_plus_26_minutes(self):
        # the script ("net") serves each slot at about +26 minutes; the real late copies arrive later: all of them are duplicates, none is the only run of its slot
        script = {(2026, 11, 8, 0): (0, 43, 22), (2026, 11, 8, 6): (6, 43, 22), (2026, 11, 8, 12): (12, 43, 22), (2026, 11, 7, 18): (18, 43, 22), (2026, 11, 7, 12): (12, 43, 22)}
        real = ((2026, 11, 8, 5, 58, 22, (2026, 11, 8, 0)), (2026, 11, 8, 13, 22, 9, (2026, 11, 8, 12)), (2026, 11, 7, 21, 48, 29, (2026, 11, 7, 18)), (2026, 11, 7, 12, 58, 11, (2026, 11, 7, 12)))
        for y, mo, d, h, mi, se, slot in real:
            self.T0 = self.utc(y, mo, d, h, mi, se)
            hh, mm, ss = script[slot]
            got, out = self.decide([self.rid(4000, self.ago(self.utc(slot[0], slot[1], slot[2], hh, mm, ss)))])
            self.assertTrue(got, (y, mo, d, h, mi, out))
        # with no script run for the slot (the Mac was off) the real run is the only one: it goes on
        self.T0 = self.utc(2026, 11, 8, 5, 58, 22)
        self.assertFalse(self.decide([self.rid(4000, self.ago(self.utc(2026, 11, 7, 21, 48, 29)))])[0])


if __name__ == "__main__":
    unittest.main()
