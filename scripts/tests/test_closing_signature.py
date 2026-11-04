"""Closing additions of 30/10/2026 (audit of the published checks): the GitHub Action can verify the signature, the signature is compared with the passage (run_id) it belongs to, and the Watch workflow runs the run_id check. Standard library only; no network."""
import contextlib, io, json, os, re, subprocess, sys, tempfile, unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import audit_public  # noqa: E402
A = "0xaaa0000000000000000000000000000000000001"


def run_main(mod, argv):
    old, buf = sys.argv, io.StringIO(); sys.argv = [mod.__name__ + ".py", *argv]
    try:
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            try: r = mod.main(); code = r if isinstance(r, int) else 0
            except SystemExit as e: code = e.code
    finally: sys.argv = old
    return code, buf.getvalue()


class TestActionVerifySignature(unittest.TestCase):
    """action.yml: the input exists, is off by default, and only the value "true" adds --verify-signature to the command."""
    def setUp(self): self.text = open(os.path.join(ROOT, "action.yml"), encoding="utf-8").read()

    def test_the_input_is_declared_and_off_by_default(self):
        m = re.search(r"(?ms)^  verify-signature:\n(.*?)(?=^  \S|^runs:)", self.text); self.assertTrue(m, "input verify-signature")
        self.assertIn('default: "false"', m.group(1)); self.assertIn("required: false", m.group(1))

    def args_for(self, value):
        run = re.search(r"(?ms)^      run: \|\n(.*)\Z", self.text).group(1)
        script = "\n".join(l[8:] if l.startswith("        ") else l for l in run.splitlines())
        script = script.replace('python3 "$GITHUB_ACTION_PATH/scripts/authority_check.py" "${args[@]}"', 'printf "%s\\n" "${args[@]}"')
        env = dict(os.environ, IN_CHAIN="base", IN_ADDRESS=A, IN_TARGETS="", IN_MIN="50", IN_DROP="", IN_UNREAD="false", IN_VERIFY=value, RUNNER_TEMP=tempfile.gettempdir(), GITHUB_ACTION_PATH=ROOT)
        r = subprocess.run(["bash", "-c", script], capture_output=True, text=True, env=env); self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.split()

    def test_only_true_adds_the_flag(self):
        self.assertIn("--verify-signature", self.args_for("true"))
        for v in ("false", "", "yes", "TRUE", "1"): self.assertNotIn("--verify-signature", self.args_for(v), v)

    def test_the_other_arguments_are_unchanged(self):
        self.assertEqual(self.args_for("false"), ["--min-score", "50", "--chain", "base", "--address", A])


class TestSignatureBelongsToThePassage(unittest.TestCase):
    def watch(self, tmp, lid, sid, sig_run="2026-10-22T12:00:00Z"):
        w = os.path.join(tmp, "watch"); os.makedirs(os.path.join(w, "scores"))
        json.dump(dict({"run_utc": "2026-10-22T12:00:00Z", "oracles": [], "unread": [], "alerts": [], "total_targets": 1, "stale_total": 0}, **({"run_id": lid} if lid else {})), open(os.path.join(w, "latest.json"), "w"))
        json.dump({"ok": True, "lines": 0}, open(os.path.join(w, "chain.json"), "w")); json.dump({"a": 1}, open(os.path.join(w, "scores", "x.json"), "w"))
        json.dump(dict({"run_utc": sig_run, "manifest": {"files": {}, "events_chain_head": None}, "signed": True, "public_key": "ab" * 32}, **({"run_id": sid} if sid else {})), open(os.path.join(w, "signature.json"), "w"))
        return w

    def audit(self, w): return run_main(audit_public, ["--watch", w, "--sample", "0"])

    def test_a_signature_of_another_passage_has_exit_code_4(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, out = self.audit(self.watch(tmp, "200.1", "199.1"))
        self.assertEqual(code, 4, out); self.assertIn("SIGNATURE FROM ANOTHER PASSAGE", out); self.assertIn("199.1", out)

    def test_a_signature_of_a_later_passage_is_also_refused_and_does_not_claim_more_than_it_knows(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, out = self.audit(self.watch(tmp, "199.1", "200.1", sig_run="2026-10-22T18:00:00Z"))
        self.assertEqual(code, 4, out); self.assertIn("not shown to cover this latest.json", out); self.assertNotIn("does not belong", out)

    def test_the_same_passage_is_not_stale(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, out = self.audit(self.watch(tmp, "200.1", "200.1"))
        self.assertNotIn("SIGNATURE FROM ANOTHER PASSAGE", out); self.assertNotIn("SIGNATURE STALE", out); self.assertNotEqual(code, 4, out)

    def test_a_run_before_the_identifier_is_not_called_stale_for_lacking_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, out = self.audit(self.watch(tmp, None, None))
        self.assertNotIn("ANOTHER PASSAGE", out); self.assertNotEqual(code, 4, out)

    def test_one_file_without_the_identifier_is_not_compared(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, out = self.audit(self.watch(tmp, "200.1", None))
        self.assertNotIn("ANOTHER PASSAGE", out); self.assertNotEqual(code, 4, out)

    def test_the_older_time_still_gives_the_old_message(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, out = self.audit(self.watch(tmp, "200.1", "200.1", sig_run="2026-10-22T06:00:00Z"))
        self.assertEqual(code, 4, out); self.assertIn("SIGNATURE STALE", out)


class TestWatchWorkflow(unittest.TestCase):
    def test_the_run_id_check_runs_after_the_signing_and_the_status_and_before_the_red_step(self):
        t = open(os.path.join(ROOT, ".github", "workflows", "watch.yml"), encoding="utf-8").read()
        sign = t.index("scripts/sign_run.py --watch watch > watch/signature.txt"); status = t.index("scripts/run_status.py --watch watch"); chk = t.index("scripts/check_run_id.py --watch watch")
        red = t.index('name: "Red if any step failed')
        self.assertTrue(sign < status < chk < red)
        line = [l for l in t.splitlines() if "check_run_id.py" in l][0]
        self.assertIn('|| echo "exit code $?" >> watch/run_id.txt', line)   # a failure is written where the last step turns it into a red run, like the other steps


if __name__ == "__main__":
    unittest.main()
