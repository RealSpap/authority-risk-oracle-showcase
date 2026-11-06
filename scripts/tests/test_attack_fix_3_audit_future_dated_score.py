"""The public audit refuses a signed run that carries a score dated in the future.

Weakness class: `lastUpdated` is supplied by whoever pushes the score, and the contract measures staleness from it, so a score dated a year ahead never turns
stale. The trust rule says so (reason score_future_dated), but the public audit, which is what a reader runs against a signed run, passed such a run: the
signature, the hashes and the schemas are all fine, since the Watch signs what it wrote. The audit now fails it with the same rule and the same tolerance.

No network; the signing keys are throwaway keys made here.
"""
import json, os, shutil, subprocess, sys, tempfile, time, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.abspath(os.path.join(HERE, ".."))
for p in (SCRIPTS, os.path.join(SCRIPTS, "lib"), os.path.join(SCRIPTS, "lib", "tests")):
    if p not in sys.path:
        sys.path.insert(0, p)
from trust_support import BASE  # noqa: E402
import audit_public  # noqa: E402
from lib import trust_rules  # noqa: E402

try:
    import nacl.signing as _ns
except ImportError:  # pragma: no cover
    _ns = None

ISO = lambda t: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t))


class TestTheRule(unittest.TestCase):
    D = {"readAt": 1000, "targets": [{"target": "0xAb", "lastUpdated": 1000}, {"target": "0xcd", "lastUpdated": 1000 + 301}, {"target": "0xef", "lastUpdated": 1000 + 300}]}

    def test_the_same_tolerance_as_the_trust_rule(self):
        self.assertEqual(audit_public.SCORE_FUTURE_TOLERANCE_SECONDS, trust_rules.SCORE_FUTURE_TOLERANCE_SECONDS)

    def test_a_date_beyond_the_tolerance_after_the_read_time_is_late(self):
        self.assertEqual(audit_public.future_dated_scores(self.D), ["0xcd"])

    def test_the_block_time_is_the_reference_when_it_was_read(self):
        d = dict(self.D, block_time=500)
        self.assertEqual(audit_public.future_dated_scores(d), ["0xAb", "0xcd", "0xef"])

    def test_a_target_the_watch_listed_is_late_whatever_its_date_and_in_any_case(self):
        d = dict(self.D, future_dated=["0xAB"])
        self.assertEqual(audit_public.future_dated_scores(d), ["0xAb", "0xcd"])

    def test_control_a_date_that_is_not_an_integer_is_not_compared(self):
        d = {"readAt": 1000, "targets": [{"target": "0x01", "lastUpdated": "2000"}, {"target": "0x02", "lastUpdated": True}]}
        self.assertEqual(audit_public.future_dated_scores(d), [])


@unittest.skipIf(_ns is None, "PyNaCl is not installed")
class TestThePublicAudit(unittest.TestCase):
    def signed(self, tmp, edit=None):
        d = os.path.join(tmp, "watch")
        shutil.copytree(BASE, d)
        os.remove(os.path.join(d, "signature.json"))
        with open(os.path.join(d, "latest.json")) as f:
            lj = json.load(f)
        lj["run_utc"] = ISO(time.time())   # a run of now, so that the age of the run says nothing here
        with open(os.path.join(d, "latest.json"), "w") as f:
            json.dump(lj, f)
        if edit:
            sp = os.path.join(d, "scores", "robinhood-chain.json")
            with open(sp) as f:
                s = json.load(f)
            edit(s)
            with open(sp, "w") as f:
                json.dump(s, f)
        seed = os.urandom(32).hex()
        r = subprocess.run([sys.executable, "-B", "-E", os.path.join(SCRIPTS, "sign_run.py"), "--watch", d], env=dict(os.environ, WATCH_SIGNING_KEY=seed), capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return d, _ns.SigningKey(bytes.fromhex(seed)).verify_key.encode().hex()

    def audit(self, d, pin):
        env = {k: v for k, v in os.environ.items() if k != "WATCH_SIGNING_KEY"}
        r = subprocess.run([sys.executable, "-B", "-E", os.path.join(SCRIPTS, "audit_public.py"), "--watch", d, "--sample", "0", "--pin", pin], env=env, capture_output=True, text=True)
        return r.returncode, r.stdout + r.stderr

    def test_a_signed_run_with_a_score_dated_a_year_ahead_fails(self):
        def f(s):   # the variant as found: lastUpdated a year ahead, the target in future_dated, the block time read
            s["targets"][0]["lastUpdated"] = int(time.time()) + 365 * 86400; s["future_dated"] = [s["targets"][0]["target"]]; s["block_time"] = int(time.time()) - 60
        with tempfile.TemporaryDirectory() as tmp:
            d, pub = self.signed(tmp, f)
            code, out = self.audit(d, pub)
            self.assertNotEqual(code, 0, out)
            self.assertIn("score dates", out)
            self.assertIn("AUDIT FAILED", out)

    def test_the_same_without_the_list_the_date_against_the_block_time_is_enough(self):
        def f(s):
            s["targets"][0]["lastUpdated"] = int(time.time()) + 3600; s["future_dated"] = []; s["block_time"] = int(time.time()) - 60
        with tempfile.TemporaryDirectory() as tmp:
            d, pub = self.signed(tmp, f)
            code, out = self.audit(d, pub)
            self.assertNotEqual(code, 0, out)
            self.assertIn("score dates", out)

    def test_without_a_block_time_the_read_time_is_the_reference(self):
        def f(s):
            s.pop("block_time", None); s["future_dated"] = []; s["targets"][0]["lastUpdated"] = s["readAt"] + 86400
        with tempfile.TemporaryDirectory() as tmp:
            d, pub = self.signed(tmp, f)
            code, out = self.audit(d, pub)
            self.assertNotEqual(code, 0, out)

    def test_control_the_base_run_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            d, pub = self.signed(tmp)
            code, out = self.audit(d, pub)
            self.assertEqual(code, 0, out)
            self.assertIn("AUDIT PASSED", out)

    def test_the_audit_says_it_checked_the_dates(self):
        with tempfile.TemporaryDirectory() as tmp:
            d, pub = self.signed(tmp)
            self.assertIn("PASS  score dates", self.audit(d, pub)[1])

    def test_control_a_date_within_the_tolerance_passes(self):
        def f(s):
            s["block_time"] = int(time.time()) - 3600; s["future_dated"] = []; s["targets"][0]["lastUpdated"] = s["block_time"] + 200
        with tempfile.TemporaryDirectory() as tmp:
            d, pub = self.signed(tmp, f)
            code, out = self.audit(d, pub)
            self.assertEqual(code, 0, out)


if __name__ == "__main__":
    unittest.main()
