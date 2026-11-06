"""A run dated in the future is refused by the trust rule and by the public audit.

Weakness class: the age of a run is the present time minus its date. With a date in the future the age is negative, and every check of the form
"older than N hours" passes: the trust status never turned STALE while the present time was before that date, and the public audit printed the
negative age as a note. A runner clock that runs ahead, or a date written by hand, kept a stopped Watch looking alive.

No network; the signing keys are throwaway keys made here.
"""
import calendar, json, os, shutil, subprocess, sys, tempfile, time, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.abspath(os.path.join(HERE, ".."))
for p in (SCRIPTS, os.path.join(SCRIPTS, "lib"), os.path.join(SCRIPTS, "lib", "tests")):
    if p not in sys.path:
        sys.path.insert(0, p)
from trust_support import A, BASE, Watch, status, codes  # noqa: E402
from lib import trust_rules as tr  # noqa: E402

try:
    import nacl.signing as _ns
except ImportError:  # pragma: no cover
    _ns = None

ISO = lambda t: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t))
T_RUN = calendar.timegm(time.strptime("2026-10-30T06:20:00Z", "%Y-%m-%dT%H:%M:%SZ"))
INPUTS = [(n + ".json", f) for n, f in sorted(tr.INPUT_DATE_FIELD.items())]


def dated(shift, now, inputs=True, signature=False):
    """The base run with run_utc (and the input dates, the manifest date) moved by `shift` seconds, its trust computed at `now`."""
    w = Watch()
    try:
        w.edit("latest.json", lambda d: d.update(run_utc=ISO(T_RUN + shift)))
        if inputs:
            for name, field in INPUTS:
                w.edit(name, (lambda f: lambda d: d.update({f: ISO(T_RUN + shift + 600)}))(field))
        if signature:
            w.edit("signature.json", lambda d: d.update(run_utc=ISO(T_RUN + shift)))
        d = w.trust(now=now)
        return status(d, A), codes(d, A)
    finally:
        w.close()


class TestTheTrustRule(unittest.TestCase):
    def test_a_run_and_its_inputs_dated_a_month_ahead_are_not_verified_three_days_later(self):
        st, cs = dated(30 * 86400, T_RUN + 73 * 3600)
        self.assertNotEqual(st, "VERIFIED", cs)
        self.assertIn("run_future_dated", cs)

    def test_the_same_twenty_days_later(self):
        st, cs = dated(30 * 86400, T_RUN + 20 * 86400)
        self.assertEqual(st, "STALE", cs)
        self.assertIn("run_future_dated", cs)

    def test_a_manifest_dated_in_the_future_is_caught(self):
        st, cs = dated(0, T_RUN + 3600, inputs=False, signature=False)
        self.assertNotIn("run_future_dated", cs)
        w = Watch()
        try:
            w.edit("signature.json", lambda d: d.update(run_utc=ISO(T_RUN + 5 * 86400)))
            self.assertIn("run_future_dated", codes(w.trust(now=T_RUN + 3600), A))
        finally:
            w.close()

    def test_the_reason_is_in_the_vocabulary(self):
        self.assertEqual(tr.REASONS["run_future_dated"], ("surveillance", "stale", "decides"))
        self.assertIn("run_future_dated", tr.TRANSIENT)
        self.assertEqual(tr.FUTURE_TOLERANCE_SECONDS, 600)

    # controls
    def test_control_the_base_run_an_hour_later_stays_verified(self):
        st, cs = dated(0, T_RUN + 3600)
        self.assertEqual(st, "VERIFIED", cs)

    def test_control_dates_a_few_minutes_ahead_are_within_the_tolerance(self):
        st, cs = dated(0, T_RUN + 1)   # the inputs are 600 s after run_utc: 599 s ahead of the present time, inside the tolerance of 600 s
        self.assertNotIn("run_future_dated", cs)

    def test_control_an_old_run_is_still_stale_for_its_age_not_for_the_future(self):
        st, cs = dated(0, T_RUN + 20 * 3600)
        self.assertEqual(st, "STALE")
        self.assertIn("watch_old", cs)
        self.assertNotIn("run_future_dated", cs)


@unittest.skipIf(_ns is None, "PyNaCl is not installed")
class TestThePublicAudit(unittest.TestCase):
    def signed(self, tmp, run_t, trust=None, latest_text=None):
        d = os.path.join(tmp, "watch")
        shutil.copytree(BASE, d)
        os.remove(os.path.join(d, "signature.json"))
        with open(os.path.join(d, "latest.json")) as f:
            lj = json.load(f)
        lj["run_utc"] = run_t if isinstance(run_t, str) else ISO(run_t)   # a string is written as it is: the formats the audit does not read
        with open(os.path.join(d, "latest.json"), "w") as f:
            json.dump(lj, f)
        if latest_text is not None:   # latest.json as given, before signing: the manifest then matches it
            with open(os.path.join(d, "latest.json"), "w") as f:
                f.write(latest_text)
        if trust is not None:   # a trust.json whose generated_utc is the given text (before signing, so that it is in the manifest)
            with open(os.path.join(d, "trust.json"), "w") as f:
                json.dump({"generated_utc": trust, "by_target": {}}, f)
        seed = os.urandom(32).hex()
        r = subprocess.run([sys.executable, "-B", "-E", os.path.join(SCRIPTS, "sign_run.py"), "--watch", d], env=dict(os.environ, WATCH_SIGNING_KEY=seed), capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return d, _ns.SigningKey(bytes.fromhex(seed)).verify_key.encode().hex()

    def audit(self, d, pin):
        env = {k: v for k, v in os.environ.items() if k != "WATCH_SIGNING_KEY"}
        r = subprocess.run([sys.executable, "-B", "-E", os.path.join(SCRIPTS, "audit_public.py"), "--watch", d, "--sample", "0", "--pin", pin], env=env, capture_output=True, text=True)
        return r.returncode, r.stdout + r.stderr

    def test_a_signed_run_dated_a_month_ahead_with_the_manifest_ahead_too_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            d, pub = self.signed(tmp, time.time() + 30 * 86400)
            sp = os.path.join(d, "signature.json")
            with open(sp) as f:
                sg = json.load(f)
            with open(os.path.join(d, "latest.json")) as f:
                sg["run_utc"] = json.load(f)["run_utc"]       # the runner clock ahead: the date beside the manifest is ahead too
            with open(sp, "w") as f:
                json.dump(sg, f)
            code, out = self.audit(d, pub)
            self.assertNotEqual(code, 0, out)
            self.assertIn("dated in the future", out)
            self.assertIn("AUDIT FAILED", out)

    # ---- second round: the dates of the other files, and a date that cannot be read ----------------------------------------------------------
    def edit_json(self, d, name, fn):
        p = os.path.join(d, name)
        with open(p) as f:
            doc = json.load(f)
        fn(doc)
        with open(p, "w") as f:
            json.dump(doc, f)

    def test_a_manifest_date_in_the_future_fails_even_when_latest_json_is_on_time(self):
        with tempfile.TemporaryDirectory() as tmp:
            d, pub = self.signed(tmp, time.time())
            self.edit_json(d, "signature.json", lambda sg: sg.update(run_utc=ISO(time.time() + 5 * 86400)))
            code, out = self.audit(d, pub)
            self.assertNotEqual(code, 0, out)
            self.assertIn("signature.json run_utc", out)
            self.assertIn("a date in the future", out)

    def test_a_trust_file_dated_in_the_future_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            d, pub = self.signed(tmp, time.time(), trust=ISO(time.time() + 5 * 86400))
            code, out = self.audit(d, pub)
            self.assertNotEqual(code, 0, out)
            self.assertIn("trust.json generated_utc", out)
            self.assertIn("a date in the future", out)

    def test_a_manifest_date_that_cannot_be_read_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            d, pub = self.signed(tmp, time.time())
            self.edit_json(d, "signature.json", lambda sg: sg.update(run_utc="2026-11-30T00:00:00+00:00"))
            code, out = self.audit(d, pub)
            self.assertNotEqual(code, 0, out)
            self.assertIn("signature.json: run_utc is not a readable date", out)

    def test_a_trust_file_without_a_readable_date_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            d, pub = self.signed(tmp, time.time(), trust="soon")
            code, out = self.audit(d, pub)
            self.assertNotEqual(code, 0, out)
            self.assertIn("trust.json: generated_utc is not a readable date", out)

    def test_a_run_date_in_the_plus_zero_zero_format_fails_whether_it_is_ahead_or_old(self):
        for when in (time.time() + 30 * 86400, time.time() - 40 * 86400):   # the two forms the review found: a month ahead and forty days old
            with tempfile.TemporaryDirectory() as tmp:
                d, pub = self.signed(tmp, time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime(when)))
                self.edit_json(d, "signature.json", lambda sg: sg.update(run_utc=time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime(when))))
                code, out = self.audit(d, pub)
                self.assertNotEqual(code, 0, out)
                self.assertIn("no readable run_utc", out)
                self.assertIn("AUDIT FAILED", out)

    def test_a_latest_json_date_in_the_plus_zero_zero_format_fails_on_its_own(self):
        with tempfile.TemporaryDirectory() as tmp:
            d, pub = self.signed(tmp, time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()))   # signature.json keeps a date in the format the audit reads
            code, out = self.audit(d, pub)
            self.assertNotEqual(code, 0, out)
            self.assertIn("FAIL  watch age: latest.json carries no readable run_utc", out)

    def test_a_latest_json_that_is_not_json_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            d, pub = self.signed(tmp, time.time(), latest_text="{not json")
            code, out = self.audit(d, pub)
            self.assertNotEqual(code, 0, out)
            self.assertIn("latest.json cannot be read", out)

    def test_control_a_trust_file_dated_now_and_a_run_without_one_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            d, pub = self.signed(tmp, time.time(), trust=ISO(time.time()))
            code, out = self.audit(d, pub)
            self.assertEqual(code, 0, out)
        with tempfile.TemporaryDirectory() as tmp:
            d, pub = self.signed(tmp, time.time())   # no trust.json: a run from before that file existed
            self.assertEqual(self.audit(d, pub)[0], 0)

    def test_control_a_signed_run_dated_now_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            d, pub = self.signed(tmp, time.time())
            code, out = self.audit(d, pub)
            self.assertEqual(code, 0, out)
            self.assertIn("AUDIT PASSED", out)

    def test_control_a_run_a_few_minutes_ahead_is_within_the_tolerance(self):
        with tempfile.TemporaryDirectory() as tmp:
            d, pub = self.signed(tmp, time.time() + 120)
            sp = os.path.join(d, "signature.json")
            with open(sp) as f:
                sg = json.load(f)
            sg["run_utc"] = ISO(time.time() + 120)      # beside the manifest, not covered by the signature: the same clock as latest.json
            with open(sp, "w") as f:
                json.dump(sg, f)
            code, out = self.audit(d, pub)
            self.assertEqual(code, 0, out)


if __name__ == "__main__":
    unittest.main()
