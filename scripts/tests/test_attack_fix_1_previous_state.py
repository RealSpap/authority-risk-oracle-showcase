"""The state a Watch run starts from must be the one the previous run signed.

Weakness class: a file kept from one run to the next (the event log, the score history) changed between two runs by someone who can push to the
watch-data branch but does not hold the signing key. If the run only reads the previous chain head from signature.json without checking that
signature, or continues when signature.json is gone, it extends the changed files and signs them with the real key: the change becomes signed.

These tests run the part of the workflow step "Read every EVM oracle" that comes before the reading itself (taken from .github/workflows/watch.yml),
on a signed fixture, then on changed copies of it. No network; the signing keys are throwaway keys made here.

Second round (31/10/2026, after the review of the code): a state with no signature.json is never "no state" in a repository that signs (the log gone,
empty or unreadable included); an older signed state put back is told from the list of runs; the refusal and the bootstrap switch always reach the alarm;
a failed signature is not recorded; the bootstrap switch is for a run started by hand only.
"""
import hashlib, json, os, shutil, subprocess, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.abspath(os.path.join(HERE, ".."))
ROOT = os.path.abspath(os.path.join(SCRIPTS, ".."))
BASE = os.path.join(SCRIPTS, "lib", "tests", "fixtures", "trust-base-watch")
WF = os.path.join(ROOT, ".github", "workflows", "watch.yml")
sys.path.insert(0, SCRIPTS)

try:
    import nacl.signing as _ns
except ImportError:  # pragma: no cover
    _ns = None


def gate_script():
    """The shell of the run step up to the reading (watch_run.py), as the workflow has it, then a marker that says the run would continue."""
    lines = open(WF, encoding="utf-8").read().splitlines()
    end = next(i for i, l in enumerate(lines) if "python3 scripts/watch_run.py 2>&1 | tee watch/run.log" in l)
    start = max(i for i in range(end) if lines[i].strip() == "run: |")
    body = "\n".join(l.strip() for l in lines[start + 1:end])
    return body.replace("python3 ", sys.executable + " -B ") + "\necho CONTINUES\n"


def events(path, n):
    prev, out = "", []
    for i in range(n):
        line = json.dumps({"run_utc": "2026-10-29T00:%02d:00Z" % i, "kind": "move", "text": "e%d" % i, "seq": i + 1, "prev": prev}, sort_keys=True)
        out.append(line); prev = hashlib.sha256(line.encode()).hexdigest()
    with open(path, "w") as f:
        f.write("\n".join(out) + "\n")


def sign(watch, seed):
    env = dict(os.environ, WATCH_SIGNING_KEY=seed)
    r = subprocess.run([sys.executable, "-B", "-E", os.path.join(SCRIPTS, "sign_run.py"), "--watch", watch], env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def public_key(seed):
    return _ns.SigningKey(bytes.fromhex(seed)).verify_key.encode().hex()


def step_if(name_start):
    """The `if:` expression of the workflow step whose name starts with name_start, without its trailing comment."""
    lines = open(WF, encoding="utf-8").read().splitlines()
    i = next(k for k, l in enumerate(lines) if l.strip().startswith("- name: ") and name_start in l)
    j = next(k for k in range(i + 1, len(lines)) if lines[k].startswith("        if: ") or lines[k].startswith("      - name: "))
    assert lines[j].startswith("        if: "), "step %r has no if" % name_start
    return lines[j][len("        if: "):].split("   #")[0]


def evaluate(expr, outputs):
    """Evaluate a GitHub Actions `if` expression made of ==, !=, && and || over steps.<id>.outputs.<name> and always()."""
    import re
    py = re.sub(r"steps\.(\w+)\.outputs\.(\w+)", lambda m: "O(%r, %r)" % (m.group(1), m.group(2)), expr)
    py = py.replace("always()", "True").replace("&&", " and ").replace("||", " or ")
    return bool(eval(py, {"O": lambda step, name: (outputs.get(step) or {}).get(name, "")}))   # noqa: S307 -- the text is the workflow of this repository


@unittest.skipIf(_ns is None, "PyNaCl is not installed")
class TestThePreviousStateIsCheckedBeforeTheRunExtendsIt(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = os.path.join(self.tmp.name, "repo")
        os.makedirs(self.root)
        os.symlink(SCRIPTS, os.path.join(self.root, "scripts"))
        self.watch = os.path.join(self.root, "watch")
        shutil.copytree(BASE, self.watch)
        os.remove(os.path.join(self.watch, "signature.json"))
        events(os.path.join(self.watch, "events.jsonl"), 8)
        with open(os.path.join(self.watch, "history.jsonl"), "w") as f:
            f.write("".join(json.dumps({"run_utc": "2026-10-29T0%d:00:00Z" % i, "composite": 40 + i}) + "\n" for i in range(4)))
        open(os.path.join(self.watch, "API.md"), "w").write("# API\n")
        os.makedirs(os.path.join(self.watch, "schema"))
        open(os.path.join(self.watch, "schema", "x.schema.json"), "w").write("{}\n")
        self.seed = os.urandom(32).hex()
        sign(self.watch, self.seed)

    def tearDown(self):
        self.tmp.cleanup()

    def gate(self, **env):
        out = os.path.join(self.tmp.name, "github_output")
        e = {k: v for k, v in os.environ.items() if k not in ("WATCH_SIGNING_KEY", "WATCH_PIN", "WATCH_BOOTSTRAP", "HAS_SIGNING_KEY", "GITHUB_REPOSITORY", "GITHUB_EVENT_NAME", "WATCH_LAST_SUCCESS_UTC")}
        e.update({"GITHUB_OUTPUT": out, "HAS_SIGNING_KEY": "true", "WATCH_PIN": public_key(self.seed)}); e.update(env)
        r = subprocess.run(["bash", "-c", gate_script()], cwd=self.root, env=e, capture_output=True, text=True)
        text = r.stdout + r.stderr
        return r.returncode == 0 and "CONTINUES" in text, text

    def cut_log(self, n=3):
        p = os.path.join(self.watch, "events.jsonl")
        lines = open(p).read().splitlines()
        open(p, "w").write("\n".join(lines[:-n]) + "\n")
        return hashlib.sha256(lines[-n - 1].encode()).hexdigest()

    def sig(self):
        return json.load(open(os.path.join(self.watch, "signature.json")))

    def put_sig(self, s):
        json.dump(s, open(os.path.join(self.watch, "signature.json"), "w"), indent=1)

    # the weakness, as it was found: the log cut and the new head written into signature.json without signing again
    def test_a_cut_log_with_a_rewritten_unsigned_head_does_not_continue(self):
        head = self.cut_log(3)
        s = self.sig(); s["manifest"]["events_chain_head"] = head
        s["manifest"]["files"]["events.jsonl"] = hashlib.sha256(open(os.path.join(self.watch, "events.jsonl"), "rb").read()).hexdigest()
        self.put_sig(s)
        ok, text = self.gate()
        self.assertFalse(ok, text)

    # its simpler variant: signature.json removed while an event log exists
    def test_a_cut_log_with_signature_json_removed_does_not_continue(self):
        self.cut_log(3)
        os.remove(os.path.join(self.watch, "signature.json"))
        ok, text = self.gate()
        self.assertFalse(ok, text)

    def test_a_kept_file_without_a_chain_changed_between_two_runs_does_not_continue(self):
        p = os.path.join(self.watch, "history.jsonl")
        open(p, "w").write("".join(open(p).readlines()[:2]))
        ok, text = self.gate()
        self.assertFalse(ok, text)

    def test_a_file_added_between_two_runs_does_not_continue(self):
        open(os.path.join(self.watch, "scores", "extra.json"), "w").write("{}\n")
        ok, text = self.gate()
        self.assertFalse(ok, text)

    def test_a_state_signed_again_by_another_key_does_not_continue(self):
        self.cut_log(2)
        sign(self.watch, os.urandom(32).hex())
        ok, text = self.gate()
        self.assertFalse(ok, text)

    def test_the_bootstrap_switch_never_accepts_a_signature_that_does_not_verify(self):
        head = self.cut_log(3)
        s = self.sig(); s["manifest"]["events_chain_head"] = head; self.put_sig(s)
        ok, text = self.gate(WATCH_BOOTSTRAP="1", GITHUB_EVENT_NAME="workflow_dispatch")
        self.assertFalse(ok, text)

    # controls: what must keep working
    def test_control_the_state_as_signed_continues(self):
        ok, text = self.gate()
        self.assertTrue(ok, text)

    def test_control_documents_copied_from_main_do_not_stop_the_run(self):
        open(os.path.join(self.watch, "API.md"), "w").write("# API, edited on main\n")
        open(os.path.join(self.watch, "schema", "y.schema.json"), "w").write("{}\n")
        ok, text = self.gate()
        self.assertTrue(ok, text)

    def empty_the_state(self):
        for n in os.listdir(self.watch):
            p = os.path.join(self.watch, n)
            shutil.rmtree(p) if os.path.isdir(p) else os.remove(p)

    def test_control_a_first_run_of_a_repository_with_no_key_continues(self):
        self.empty_the_state()
        ok, text = self.gate(HAS_SIGNING_KEY="false", WATCH_PIN="")
        self.assertTrue(ok, text)

    def test_control_the_first_signed_run_continues_only_with_the_bootstrap_switch(self):
        os.remove(os.path.join(self.watch, "signature.json"))
        self.assertFalse(self.gate()[0])
        self.assertFalse(self.gate(WATCH_BOOTSTRAP="1")[0])   # no event named: not a run started by hand, the variable is ignored
        ok, text = self.gate(WATCH_BOOTSTRAP="1", GITHUB_EVENT_NAME="workflow_dispatch")
        self.assertTrue(ok, text)
        self.assertIn("WATCH_BOOTSTRAP", text)

    def test_the_canonical_repository_pins_the_published_key_by_default(self):
        import watch_location
        ok, text = self.gate(WATCH_PIN="", GITHUB_REPOSITORY=watch_location.REPO)   # signed by a throwaway key, which is not the published one
        self.assertFalse(ok, text)
        self.assertIn("not a pinned key", text)

    # ---- second round: a missing state is not an empty state --------------------------------------------------------------------------------
    def github_output(self):
        p = os.path.join(self.tmp.name, "github_output")
        return open(p).read() if os.path.exists(p) else ""

    def test_signature_and_log_both_removed_is_not_a_first_run(self):
        os.remove(os.path.join(self.watch, "signature.json"))
        os.remove(os.path.join(self.watch, "events.jsonl"))
        open(os.path.join(self.watch, "history.jsonl"), "w").write("")   # the rest of the state rewritten
        ok, text = self.gate()
        self.assertFalse(ok, text)
        self.assertIn("REFUSED", text)

    def test_signature_removed_and_the_log_made_of_blank_lines_is_not_a_first_run(self):
        os.remove(os.path.join(self.watch, "signature.json"))
        open(os.path.join(self.watch, "events.jsonl"), "w").write("\n  \n\n")
        ok, text = self.gate()
        self.assertFalse(ok, text)

    def test_signature_removed_and_an_empty_log_is_not_a_first_run(self):
        os.remove(os.path.join(self.watch, "signature.json"))
        open(os.path.join(self.watch, "events.jsonl"), "w").write("")
        self.assertFalse(self.gate()[0])

    def test_signature_removed_and_a_log_that_cannot_be_read_is_not_a_first_run(self):
        os.remove(os.path.join(self.watch, "signature.json"))
        p = os.path.join(self.watch, "events.jsonl")
        os.remove(p)
        os.mkdir(p)   # a folder where the log was: opening it fails
        ok, text = self.gate()
        self.assertFalse(ok, text)
        self.assertIn("cannot be read", text)

    def test_a_repository_with_no_key_takes_an_absent_log_as_a_first_run_but_not_a_blank_or_unreadable_one(self):
        nokey = dict(HAS_SIGNING_KEY="false", WATCH_PIN="")
        os.remove(os.path.join(self.watch, "signature.json"))
        p = os.path.join(self.watch, "events.jsonl")
        os.remove(p)
        self.assertTrue(self.gate(**nokey)[0])   # absent: nothing was ever there to sign
        open(p, "w").write("\n \n")
        ok, text = self.gate(**nokey)
        self.assertFalse(ok, text)               # blank: something was emptied
        os.remove(p)
        os.mkdir(p)
        ok, text = self.gate(**nokey)
        self.assertFalse(ok, text)               # unreadable

    def test_with_the_bootstrap_switch_the_emptied_state_is_taken_only_by_a_run_started_by_hand(self):
        for gone in ("events.jsonl",):
            os.remove(os.path.join(self.watch, gone))
        os.remove(os.path.join(self.watch, "signature.json"))
        ok, text = self.gate(WATCH_BOOTSTRAP="1", GITHUB_EVENT_NAME="schedule")
        self.assertFalse(ok, text)
        self.assertIn("not started by hand", text)
        ok, text = self.gate(WATCH_BOOTSTRAP="1", GITHUB_EVENT_NAME="workflow_dispatch")
        self.assertTrue(ok, text)
        self.assertIn("ALARM WATCH_BOOTSTRAP accepted", text)

    def test_the_bootstrap_switch_left_on_after_the_first_signed_run_is_an_alarm_every_time(self):
        ok, text = self.gate(WATCH_BOOTSTRAP="1", GITHUB_EVENT_NAME="workflow_dispatch")   # the state is signed: the switch is not needed
        self.assertTrue(ok, text)
        self.assertIn("ALARM WATCH_BOOTSTRAP is still set", text)
        self.assertIn("prev_alarm=1", self.github_output())
        ok, text = self.gate(WATCH_BOOTSTRAP="1", GITHUB_EVENT_NAME="schedule")
        self.assertTrue(ok, text)
        self.assertIn("ALARM WATCH_BOOTSTRAP is set but this run was not started by hand", text)
        with open(os.path.join(self.root, "watch", "run.log")) as f:
            self.assertIn("ALARM", f.read())

    def test_control_a_run_without_the_switch_raises_no_alarm_line(self):
        ok, text = self.gate()
        self.assertTrue(ok, text)
        self.assertNotIn("ALARM", text)
        self.assertNotIn("prev_alarm", self.github_output())

    # ---- going back: an older signed state put back on the branch ---------------------------------------------------------------------------
    def run_utc_of_the_state(self):
        return json.load(open(os.path.join(self.watch, "latest.json")))["run_utc"]

    def test_an_older_signed_state_put_back_is_refused_when_a_later_run_succeeded(self):
        later = "2026-10-30T12:17:00Z"   # the last successful run started six hours after the run this state comes from
        self.assertEqual(self.run_utc_of_the_state(), "2026-10-30T06:20:00Z")
        ok, text = self.gate(WATCH_LAST_SUCCESS_UTC=later)
        self.assertFalse(ok, text)
        self.assertIn("older than the last successful run", text)

    def test_the_date_next_to_the_manifest_cannot_hide_a_state_put_back(self):
        s = self.sig(); s["run_utc"] = "2026-10-31T00:00:00Z"; self.put_sig(s)   # run_utc of signature.json is outside the signature: it proves nothing
        ok, text = self.gate(WATCH_LAST_SUCCESS_UTC="2026-10-30T12:17:00Z")
        self.assertFalse(ok, text)

    def test_a_date_written_into_latest_json_to_hide_a_state_put_back_is_a_changed_file(self):
        p = os.path.join(self.watch, "latest.json")
        d = json.load(open(p)); d["run_utc"] = "2026-10-30T12:20:00Z"; json.dump(d, open(p, "w"))
        ok, text = self.gate(WATCH_LAST_SUCCESS_UTC="2026-10-30T12:17:00Z")
        self.assertFalse(ok, text)
        self.assertIn("latest.json differs", text)

    def test_a_last_success_date_that_is_not_a_date_does_not_pass(self):
        self.assertFalse(self.gate(WATCH_LAST_SUCCESS_UTC="soon")[0])

    def test_control_the_state_written_by_the_last_successful_run_continues(self):
        for last in ("2026-10-30T06:17:00Z", "2026-10-30T06:20:00Z", "2026-10-30T06:24:00Z"):   # created a little before, at, or within the slack after the stamp
            ok, text = self.gate(WATCH_LAST_SUCCESS_UTC=last)
            self.assertTrue(ok, last + text)
        ok, text = self.gate()   # the list of runs could not be read: the check is skipped, and says so
        self.assertTrue(ok, text)
        self.assertIn("no start time of a last successful run", text)

    # ---- the refusal reaches the alarm whatever the gate remembers --------------------------------------------------------------------------
    def test_a_refusal_writes_an_alarm_line_an_output_and_the_issue_text(self):
        self.cut_log(3)
        ok, text = self.gate()
        self.assertFalse(ok, text)
        out = self.github_output()
        self.assertIn("code=2", out)
        self.assertIn("prev_alarm=1", out)
        run_log = open(os.path.join(self.root, "watch", "run.log")).read()
        self.assertIn("ALARM previous state refused", run_log)
        alarm = open(os.path.join(self.root, "watch", "alarm.md")).read()
        self.assertIn("REFUSED", alarm)

    def test_the_alarm_gate_does_not_hold_back_a_refusal_when_findings_were_already_notified(self):
        import alarm_gate, time
        self.cut_log(3)
        self.gate()
        found = alarm_gate.findings(os.path.join(self.root, "watch"), os.path.join(self.root, "watch", "run.log"))
        self.assertTrue(any(f.startswith("alarm:ALARM previous state refused") for f in found), found)
        seen = ["disagree:c:0x%02d" % i for i in range(13)]
        now = time.time()
        state = {"findings": seen, "notified_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now))}
        self.assertEqual(alarm_gate.decide(set(seen) | found, state, now), "new")

    def test_the_alarm_step_opens_an_issue_for_a_refusal_even_when_the_gate_says_quiet(self):
        expr = step_if("Alarm (an issue in the private repository")
        quiet = {"gate": {"mode": "quiet"}, "so": {"disagree": "13", "upgraded": "0"}, "meth": {"changed": "0"}, "rq": {"overdue": "0"}, "rules": {"hi_new": "0"}}
        self.assertTrue(evaluate(expr, dict(quiet, run={"code": "2", "prev_alarm": "1"})))
        self.assertTrue(evaluate(expr, dict(quiet, run={"code": "0", "prev_alarm": "1"})))   # the switch left on
        self.assertTrue(evaluate(expr, dict(quiet, run={"code": "0"}, sign={"failed": "1"})))
        # the gate still keeps quiet what it was made for
        self.assertFalse(evaluate(expr, dict(quiet, run={"code": "2"})))
        self.assertFalse(evaluate(expr, dict(quiet, run={"code": "0"}, so={"disagree": "0", "upgraded": "0"})))

    def test_the_alarm_lines_of_the_check_are_put_back_in_run_log_after_the_run_has_rewritten_it(self):
        text = open(WF, encoding="utf-8").read()
        self.assertLess(text.index("python3 scripts/watch_run.py 2>&1 | tee watch/run.log"), text.index("grep '^ALARM' watch/previous_state.txt >> watch/run.log"))   # tee starts run.log again

    def test_the_gate_condition_knows_a_refusal(self):
        lines = open(WF, encoding="utf-8").read().splitlines()
        cond = next(l for l in lines if l.strip().startswith("ALARM_CONDITION:"))
        self.assertIn("steps.run.outputs.prev_alarm", cond)
        self.assertIn("steps.sign.outputs.failed", cond)

    # ---- PyNaCl missing is not an alteration ------------------------------------------------------------------------------------------------
    def test_pynacl_missing_says_not_checked_and_does_not_call_it_an_alteration(self):
        stub = os.path.join(self.tmp.name, "stub")
        os.makedirs(os.path.join(stub, "nacl"))
        open(os.path.join(stub, "nacl", "__init__.py"), "w").write("raise ImportError('no PyNaCl here')\n")
        ok, text = self.gate(PYTHONPATH=stub)
        self.assertFalse(ok, text)
        self.assertIn("not checked", text)
        self.assertNotIn("is not the one the previous run signed", text)
        self.assertIn("code=2", self.github_output())

    # ---- the date of the last successful run comes from GitHub's list of runs: the step that reads it, with a stand-in for `gh` ----------------
    def anchor_step(self, gh_body):
        lines = open(WF, encoding="utf-8").read().splitlines()
        i = next(k for k, l in enumerate(lines) if l.strip().startswith("- name:") and "The last successful run of this workflow" in l)
        j = next(k for k in range(i, len(lines)) if lines[k].strip() == "run: |")
        k = next(k for k in range(j + 1, len(lines)) if lines[k].startswith("      - name:"))
        script = "\n".join(l.strip() for l in lines[j + 1:k])
        bindir = os.path.join(self.tmp.name, "bin")
        os.makedirs(bindir, exist_ok=True)
        with open(os.path.join(bindir, "gh"), "w") as f:
            f.write("#!/bin/bash\n" + gh_body + "\n")
        os.chmod(os.path.join(bindir, "gh"), 0o755)
        out = os.path.join(self.tmp.name, "anchor_output")
        open(out, "w").close()
        r = subprocess.run(["bash", "-ec", script], cwd=self.root, env=dict(os.environ, PATH=bindir + os.pathsep + os.environ["PATH"], GITHUB_OUTPUT=out, GITHUB_REPOSITORY="o/r", GH_TOKEN="x"), capture_output=True, text=True)
        return r.returncode, open(out).read(), r.stdout + r.stderr

    def test_the_anchor_step_passes_on_the_date_of_the_last_successful_run(self):
        rc, out, text = self.anchor_step("echo 2026-10-30T12:17:03Z")
        self.assertEqual(rc, 0, text)
        self.assertEqual(out.strip(), "utc=2026-10-30T12:17:03Z")

    def test_the_anchor_step_says_so_when_the_list_cannot_be_read_and_never_stops_the_run(self):
        for body in ("exit 1", "echo null", "echo", "echo 'rate limit exceeded'"):
            rc, out, text = self.anchor_step(body)
            self.assertEqual(rc, 0, (body, text))
            self.assertEqual(out.strip(), "", (body, out))   # no date: the check is skipped, it does not invent one
            self.assertIn("::warning title=Rollback check", text, body)

    def test_the_run_step_receives_the_date_and_the_scripts_never_see_a_token(self):
        text = open(WF, encoding="utf-8").read()
        self.assertIn("WATCH_LAST_SUCCESS_UTC: ${{ steps.anchor.outputs.utc }}", text)
        i = text.index("- name: Read every EVM oracle and diff against the previous run")
        self.assertNotIn("GH_TOKEN", text[i:text.index("      - name:", i + 10)])
        self.assertIn("actions: read", text[:text.index("jobs:")])

    # ---- a failed signature is not recorded ------------------------------------------------------------------------------------------------
    def sign_step_command(self):
        lines = open(WF, encoding="utf-8").read().splitlines()
        i = next(k for k, l in enumerate(lines) if l.strip().startswith("- name:") and "Sign the run" in l)
        j = next(k for k in range(i, len(lines)) if lines[k].strip() == "run: |")
        k = next(k for k in range(j + 1, len(lines)) if lines[k].startswith("      - name:"))
        return "\n".join(l.strip() for l in lines[j + 1:k])

    def test_a_run_that_cannot_be_signed_stops_the_job_before_it_is_recorded(self):
        cmd = self.sign_step_command().replace("python3 ", sys.executable + " -B ")
        out = os.path.join(self.tmp.name, "sign_output")
        e = dict(os.environ, GITHUB_OUTPUT=out, WATCH_SIGNING_KEY="not-a-hex-seed")
        r = subprocess.run(["bash", "-ec", cmd], cwd=self.root, env=e, capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)   # a step that exits 0 lets the next step, the record, run
        self.assertIn("failed=1", open(out).read())
        r = subprocess.run(["bash", "-ec", cmd], cwd=self.root, env=dict(os.environ, GITHUB_OUTPUT=out, WATCH_SIGNING_KEY=self.seed), capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)   # control: a signature that works goes on

    def test_the_daily_report_that_cannot_be_signed_again_ends_before_the_record(self):
        text = open(WF, encoding="utf-8").read()
        i = text.index('Daily report (first run of the day')
        step = text[i:text.index("      - name:", i + 10)]
        resign = next(l for l in step.splitlines() if "Re-signing failed" in l)
        self.assertIn("exit 1", resign)
        self.assertLess(step.index("Re-signing failed"), step.index("watch_branch.sh record"))
        ids = [l for l in text.splitlines() if "      - name: Record the run on the watch-data branch" in l]
        self.assertEqual(len(ids), 1)
        rec_i = text.index("      - name: Record the run on the watch-data branch")
        self.assertNotIn("always()", text[rec_i:text.index("        run:", rec_i)])   # the main record only follows steps that succeeded

    def test_the_documents_from_main_are_the_ones_the_branch_script_copies(self):
        import check_previous_state as cps
        line = next(l for l in open(os.path.join(SCRIPTS, "watch_branch.sh")) if l.startswith("DOCS="))
        docs = set(line.split('"')[1].split()) - {".gitignore"}
        self.assertEqual(docs, set(cps.MAIN_DOCS) | {d.rstrip("/") for d in cps.MAIN_DOC_DIRS})


if __name__ == "__main__":
    unittest.main()
