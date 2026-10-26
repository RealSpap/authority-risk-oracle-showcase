"""The weaknesses an adversarial pass found in four scripts that read what the Watch publishes (22/10/2026): each test is one false pass or one write outside a folder.
    python3 -m unittest scripts.tests.test_scripts_hardening
The paths below come from a manifest, a score file or a command line; none is a secret and none reaches the network (the fetch function is replaced)."""
import contextlib, io, json, math, os, sys, tempfile, time, unittest, urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
import audit_public, authority_check, sign_run, watch_age  # noqa: E402
import run_status  # noqa: E402,F401

ROOT = os.path.join(HERE, "..", "..")
ADDR = "0x" + "aa" * 20


def run_main(mod, argv):
    old, buf = sys.argv, io.StringIO(); sys.argv = [mod.__name__ + ".py", *argv]
    try:
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            try: r = mod.main(); code = r if isinstance(r, int) else 0
            except SystemExit as e: code = e.code
    finally: sys.argv = old
    return code, buf.getvalue()


class TestManifestPaths(unittest.TestCase):
    """A name that comes from signature.json is a path only if it is a plain relative path inside the folder. The live fetch reads it before any signature check."""
    HOSTILE = ["../fuite-1.json", "scores/../../fuite-2.json", "/tmp/fuite-absolu.json", "scores//dup.json", "a\\b.json", "./x.json", "C:evil.json", ""]

    def serve(self, files):
        sig = {"run_utc": "2026-10-22T00:00:00Z", "manifest": {"files": files, "events_chain_head": None}, "signed": False}
        def get(url, binary=False):
            if url.endswith("signature.json"): return json.dumps(sig)
            return b"{}" if binary else "{}"
        return get

    def test_safe_name_accepts_plain_relative_paths_only(self):
        for n in ("latest.json", "scores/base-sepolia.json", "schema/latest.schema.json", "feed/a/b.xml", "ok/..hidden"): self.assertTrue(audit_public.safe_name(n), n)
        for n in self.HOSTILE + ["scores/..", "..", "a/../b", None, 5, ["a"], "x\x00y"]: self.assertFalse(audit_public.safe_name(n), repr(n))

    def test_two_names_for_one_file_on_a_case_insensitive_disk_are_refused(self):
        self.assertEqual(sorted(audit_public.unsafe_names(["scores/A.json", "scores/a.json", "b.json"])), ["scores/A.json", "scores/a.json"])

    def test_the_live_fetch_writes_nothing_when_a_name_is_hostile(self):
        old = audit_public.get
        try:
            for bad in self.HOSTILE[:-1]:
                with tempfile.TemporaryDirectory() as tmp:
                    dest = os.path.join(tmp, "a", "b", "dest"); audit_public.get = self.serve({"latest.json": "0" * 64, bad: "1" * 64})
                    with self.assertRaises(audit_public.UnsafeManifest, msg=bad): audit_public.fetch_watch(dest)
                    self.assertEqual([], [os.path.join(r, f) for r, _d, fs in os.walk(tmp) for f in fs], "something was written for %r" % bad)   # not even signature.json or latest.json
        finally: audit_public.get = old

    def test_the_audit_exits_1_with_a_FAIL_on_a_hostile_manifest(self):
        old = audit_public.get
        try:
            audit_public.get = self.serve({"latest.json": "0" * 64, "../x.json": "1" * 64}); code, out = run_main(audit_public, ["--sample", "0"])
        finally: audit_public.get = old
        self.assertEqual(code, 1, out); self.assertIn("FAIL  manifest:", out); self.assertIn("AUDIT FAILED", out)

    def test_a_missing_or_empty_signature_is_incomplete_never_a_smaller_audit(self):
        old = audit_public.get
        try:
            def nf(url, binary=False): raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)
            audit_public.get = nf; code, out = run_main(audit_public, ["--sample", "0"]); self.assertEqual(code, 3, out); self.assertIn("AUDIT INCOMPLETE", out)   # a server that answers 404 does not turn the audit into a note
            for body in ('{"manifest": {}}', '{"manifest": {"files": {}}}', '{"manifest": {"files": ["a"]}}', "[]", "{}"):
                audit_public.get = lambda url, binary=False, body=body: body; code, out = run_main(audit_public, ["--sample", "0"]); self.assertEqual(code, 3, (body, out))
        finally: audit_public.get = old

    def test_a_local_manifest_with_hostile_names_is_failed_and_the_outside_file_is_not_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            w = os.path.join(tmp, "watch"); os.makedirs(os.path.join(w, "scores")); json.dump({"run_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}, open(os.path.join(w, "latest.json"), "w")); json.dump({"a": 1}, open(os.path.join(w, "scores", "x.json"), "w"))
            open(os.path.join(tmp, "secret.json"), "w").write("{}")
            json.dump({"run_utc": "x", "manifest": {"files": {"../secret.json": "0" * 64}, "events_chain_head": None}, "signed": False}, open(os.path.join(w, "signature.json"), "w"))
            code, out = run_main(audit_public, ["--watch", w, "--sample", "0"])
        self.assertEqual(code, 1, out); self.assertIn("FAIL  manifest: 1 name(s) are not plain relative paths", out)

    def test_a_symbolic_link_that_leaves_the_folder_is_not_followed(self):
        with tempfile.TemporaryDirectory() as tmp:
            w = os.path.join(tmp, "w"); os.makedirs(w); open(os.path.join(tmp, "outside.json"), "w").write("{}"); os.symlink(os.path.join(tmp, "outside.json"), os.path.join(w, "link.json"))
            self.assertIsNone(audit_public.inside(w, "link.json")); self.assertIsNone(audit_public.inside(w, "../outside.json")); self.assertEqual(audit_public.inside(w, "a/b.json"), os.path.join(w, "a/b.json"))


class TestManifestPathsSecondPass(unittest.TestCase):
    """The second reader (22/10/2026) found five more ways around the first fix: Unicode, the URL, no cap, silent failures, folder links, and a lost exclusion."""
    def serve(self, files, fail=()):
        sig = {"run_utc": "2026-10-22T00:00:00Z", "manifest": {"files": files, "events_chain_head": None}, "signed": False}
        def get(url, binary=False):
            if url.endswith("signature.json"): return json.dumps(sig)
            if any(url.endswith(f) for f in fail): raise OSError("refused")
            return b"{}" if binary else "{}"
        return get

    def test_names_that_change_the_file_or_the_url_are_refused(self):
        for n in ("e\u0301.json", "\u00e9.json", "\uff41.json", "x.json\n", "x.json.", "x.json ", "dir./x.json", "x.json?z=1", "%2e%2e/x.json", "a#b.json", "a b.json", "a:b.json", "x" * 300):
            self.assertFalse(audit_public.safe_name(n), repr(n))
        self.assertTrue(audit_public.safe_name("scores/base-sepolia.json")); self.assertTrue(audit_public.safe_name("feed/0xabc.xml"))

    def test_two_names_the_same_file_once_case_or_unicode_is_ignored_are_refused(self):
        self.assertEqual(sorted(audit_public.unsafe_names(["scores/A.json", "scores/a.json"])), ["scores/A.json", "scores/a.json"])
        self.assertEqual(sorted(audit_public.unsafe_names(["e\u0301.json", "\u00e9.json"])), ["e\u0301.json", "\u00e9.json"])   # both non-ASCII: refused as unsafe names

    def test_the_url_of_a_file_is_quoted_and_hostile_names_never_reach_it(self):
        urls = []; base = self.serve({"latest.json": "0" * 64, "scores/a-b.json": "1" * 64})
        def get(url, binary=False): urls.append(url); return base(url, binary)
        old = audit_public.get
        try:
            audit_public.get = get
            with tempfile.TemporaryDirectory() as tmp: self.assertEqual(audit_public.fetch_watch(os.path.join(tmp, "d")), 2)
        finally: audit_public.get = old
        self.assertEqual(sorted(u.split("watch-data/")[-1] for u in urls), ["latest.json", "scores/a-b.json", "signature.json"])

    def test_more_names_than_the_cap_are_refused_before_any_request_for_a_file(self):
        files = {"f%05d.json" % i: "0" * 64 for i in range(audit_public.MAX_NAMES + 1)}; old = audit_public.get; urls = []
        try:
            base = self.serve(files); audit_public.get = lambda url, binary=False: (urls.append(url), base(url, binary))[1]
            with tempfile.TemporaryDirectory() as tmp:
                with self.assertRaises(audit_public.UnsafeManifest): audit_public.fetch_watch(os.path.join(tmp, "d"))
                self.assertFalse(os.path.exists(os.path.join(tmp, "d")))
        finally: audit_public.get = old
        self.assertEqual(len(urls), 1)   # only signature.json

    def test_a_file_that_cannot_be_fetched_stops_the_audit_as_incomplete_never_a_smaller_one(self):
        old = audit_public.get
        try:
            audit_public.get = self.serve({"latest.json": "0" * 64, "scores/x.json": "1" * 64}, fail=("scores/x.json",))
            with tempfile.TemporaryDirectory() as tmp:
                with self.assertRaises(RuntimeError) as c: audit_public.fetch_watch(os.path.join(tmp, "d"))
            self.assertIn("could not be fetched or written", str(c.exception))
            code, out = run_main(audit_public, ["--sample", "0"]); self.assertEqual(code, 3, out); self.assertIn("AUDIT INCOMPLETE", out)
        finally: audit_public.get = old

    def test_a_file_that_cannot_be_written_stops_the_audit_too(self):
        old = audit_public.get
        try:
            audit_public.get = self.serve({"latest.json": "0" * 64})
            with tempfile.TemporaryDirectory() as tmp:
                dest = os.path.join(tmp, "d"); os.makedirs(dest); os.makedirs(os.path.join(dest, "latest.json"))   # a folder where the file should go: the write fails
                with self.assertRaises(RuntimeError): audit_public.fetch_watch(dest)
        finally: audit_public.get = old

    def test_an_answer_over_the_size_cap_is_an_error(self):
        class R:
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def read(self, n=-1): return b"x" * (n if n >= 0 else audit_public.MAX_BYTES + 5)
        old = audit_public.urllib.request.urlopen
        try:
            audit_public.urllib.request.urlopen = lambda *a, **k: R()
            with self.assertRaises(ValueError): audit_public.get("https://example.invalid/x", binary=True)
        finally: audit_public.urllib.request.urlopen = old


class TestSignRunSecondPass(unittest.TestCase):
    def watch(self, tmp):
        w = os.path.join(tmp, "repo", "watch"); os.makedirs(w); os.makedirs(os.path.join(tmp, "repo", "scripts")); json.dump({"a": 1}, open(os.path.join(w, "a.json"), "w")); return w

    def test_a_private_folder_never_enters_the_signed_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            w = self.watch(tmp)
            for rel in ("private/x.json", "scores/private/y.json", "private/deep/z.md"):
                p = os.path.join(w, rel); os.makedirs(os.path.dirname(p), exist_ok=True); open(p, "w").write("{}")
            self.assertEqual(sorted(sign_run.manifest(w)["files"]), ["a.json"])

    def test_a_folder_that_is_a_link_to_a_folder_outside_does_not_enter_the_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            w = self.watch(tmp); out = os.path.join(tmp, "outside"); os.makedirs(os.path.join(out, "sub")); json.dump({"o": 1}, open(os.path.join(out, "sub", "o.json"), "w")); os.symlink(out, os.path.join(w, "lien"))
            self.assertEqual(sorted(sign_run.manifest(w)["files"]), ["a.json"])


class TestSignatureKey(unittest.TestCase):
    """A valid signature by a key nobody pinned is not a pass: the key is read from the same file as the signature."""
    KEY = "44" * 32

    def have_nacl(self):
        try: import nacl.signing  # noqa: F401
        except ImportError: self.skipTest("pynacl is not installed")

    def signed_watch(self, tmp):
        w = os.path.join(tmp, "repo", "watch"); os.makedirs(os.path.join(w, "scores")); os.makedirs(os.path.join(tmp, "repo", "scripts"))
        json.dump({"run_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}, open(os.path.join(w, "latest.json"), "w")); json.dump({"kind": "solana", "name": "S", "targets": [{"target": "T", "methodologyHash": "0xaa"}]}, open(os.path.join(w, "scores", "solana-devnet.json"), "w"))
        old = os.environ.get("WATCH_SIGNING_KEY"); os.environ["WATCH_SIGNING_KEY"] = self.KEY
        try: run_main(sign_run, ["--watch", w])
        finally:
            if old is None: os.environ.pop("WATCH_SIGNING_KEY", None)
            else: os.environ["WATCH_SIGNING_KEY"] = old
        return w

    def test_a_valid_signature_by_an_unpinned_key_fails_and_the_pin_option_accepts_it(self):
        self.have_nacl()
        from nacl.signing import SigningKey
        pub = SigningKey(bytes.fromhex(self.KEY)).verify_key.encode().hex()
        with tempfile.TemporaryDirectory() as tmp:
            w = self.signed_watch(tmp)
            code, out = run_main(audit_public, ["--watch", w, "--sample", "0"]); self.assertEqual(code, 1, out); self.assertIn("FAIL  signature: valid Ed25519 signature, but by a key this audit does not pin", out)
            code, out = run_main(audit_public, ["--watch", w, "--sample", "0", "--pin", pub]); self.assertEqual(code, 0, out); self.assertIn("PASS  signature: valid Ed25519 signature", out)
            code, out = run_main(audit_public, ["--watch", w, "--sample", "0", "--pin", "00" * 32]); self.assertEqual(code, 1, out)   # another pinned key does not help

    def test_the_pinned_key_is_the_one_published_in_the_api_notes(self):
        api = os.path.join(ROOT, "watch", "API.md")
        if not os.path.exists(api): self.skipTest("watch/API.md is not in this checkout")
        self.assertEqual(len(audit_public.PINNED_KEYS), 1); self.assertIn("`" + audit_public.PINNED_KEYS[0] + "`", open(api, encoding="utf-8").read())


class TestSignRun(unittest.TestCase):
    def watch(self, tmp):
        w = os.path.join(tmp, "repo", "watch"); os.makedirs(w); os.makedirs(os.path.join(tmp, "repo", "scripts")); json.dump({"a": 1}, open(os.path.join(w, "a.json"), "w")); return w

    def test_a_file_added_after_signing_fails_the_verification(self):
        with tempfile.TemporaryDirectory() as tmp:
            w = self.watch(tmp); run_main(sign_run, ["--watch", w]); self.assertEqual(run_main(sign_run, ["--watch", w, "--verify"])[0], 0)
            json.dump({"b": 2}, open(os.path.join(w, "ajoute.json"), "w")); code, out = run_main(sign_run, ["--watch", w, "--verify"])
        self.assertEqual(code, 1, out); self.assertIn("ajoute.json", out); self.assertIn("not covered", out)

    def test_a_symbolic_link_to_a_file_outside_the_folder_is_not_in_the_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            w = self.watch(tmp); open(os.path.join(tmp, "outside.json"), "w").write('{"o": 1}'); os.symlink(os.path.join(tmp, "outside.json"), os.path.join(w, "lien.json"))
            self.assertEqual(sorted(sign_run.manifest(w)["files"]), ["a.json"])

    def test_the_docstring_says_where_the_run_time_is(self):
        self.assertIn("NEXT TO the manifest", sign_run.__doc__); self.assertNotIn("the head of the hash-chained event log, the run time)", sign_run.__doc__)


class TestAuthorityCheck(unittest.TestCase):
    """Every row of the adversarial pass: the gate says UNREAD (exit 3), never ok."""
    NOW = 2_000_000_000

    def ok(self, **kw): return dict({"target": ADDR, "compositeScore": 65, "stale": False, "adminKeyScore": 70, "multisigScore": 80, "timelockScore": 20}, **kw)

    def one(self, targets, read_at=NOW - 3600, mn=0, max_age=48, **doc):
        d = dict({"targets": targets}, **doc)
        if read_at is not None: d["readAt"] = read_at
        return authority_check.check_one("base", ADDR, mn, None, d, now=self.NOW, max_age_hours=max_age)

    def test_the_reference_case_is_ok(self): self.assertEqual(self.one([self.ok()])[0], "ok")

    def test_a_file_without_readAt_is_unread(self): self.assertEqual(self.one([self.ok()], read_at=None)[0], "unread")

    def test_a_readAt_that_is_not_a_number_or_is_in_the_future_is_unread(self):
        for ra in ("2026", True, None, float("nan"), self.NOW + 7200): self.assertEqual(self.one([self.ok()], read_at=ra)[0], "unread", ra)

    def test_a_limit_of_zero_does_not_switch_the_age_check_off(self):
        self.assertEqual(self.one([self.ok()], read_at=self.NOW - 40 * 86400, max_age=0)[0], "unread"); self.assertEqual(self.one([self.ok()], read_at=self.NOW - 40 * 86400, max_age=float("nan"))[0], "unread")
        code, out = run_main(authority_check, ["--max-age-hours", "0", "--chain", "base", "--address", ADDR]); self.assertEqual(code, 2, out)   # refused at the command line

    def test_a_missing_or_null_or_text_stale_flag_is_unread_and_true_fails(self):
        no = {k: v for k, v in self.ok().items() if k != "stale"}
        for t in (no, self.ok(stale=None), self.ok(stale="False"), self.ok(stale=0)): self.assertEqual(self.one([t])[0], "unread", t)
        self.assertEqual(self.one([self.ok(stale=True)])[0], "fail")

    def test_a_composite_that_is_not_a_whole_number_from_0_to_100_is_unread(self):
        for c in (True, False, 150, 101, -5, 2 ** 63, 65.0, "65", None): self.assertEqual(self.one([self.ok(compositeScore=c)], mn=-10)[0], "unread", c)
        for c in (0, 100): self.assertEqual(self.one([self.ok(compositeScore=c)])[0], "ok", c)

    def test_a_contract_listed_twice_is_unread_whatever_the_lines_say(self):
        self.assertEqual(self.one([self.ok(compositeScore=65), self.ok(compositeScore=5)])[0], "unread"); self.assertEqual(self.one([self.ok(compositeScore=5), self.ok(compositeScore=65)])[0], "unread")

    def test_the_other_failures_are_unchanged(self):
        self.assertEqual(authority_check.check_one("base", "0xdead", 0, None, {"targets": [self.ok()], "readAt": self.NOW}, now=self.NOW)[0], "fail")   # not tracked
        self.assertEqual(self.one([self.ok()], mn=70)[0], "fail"); self.assertEqual(authority_check.check_one("base", ADDR, 0, None, None)[0], "unread")
        self.assertEqual(authority_check.check_one("base", ADDR, 0, None, [1, 2])[0], "unread")


class TestWatchAge(unittest.TestCase):
    NOW = watch_age.parse_utc("2026-10-10T12:00:00Z")

    def test_a_limit_that_is_not_a_finite_number_above_zero_is_unknown_never_fresh(self):
        old = {"run_utc": "2026-08-20T12:00:00Z"}   # 51 days before NOW
        for lim in (float("nan"), float("inf"), 0, -1, "14", None, True): self.assertEqual(watch_age.judge(old, self.NOW, lim)[0], 2, lim)
        self.assertEqual(watch_age.judge(old, self.NOW, 14)[0], 1)

    def test_the_command_line_refuses_nan_inf_zero_and_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = os.path.join(tmp, "latest.json"); json.dump({"run_utc": "2026-08-20T12:00:00Z"}, open(f, "w"))
            for lim in ("nan", "inf", "0", "-3", "abc"): self.assertEqual(run_main(watch_age, ["--file", f, "--max-hours", lim])[0], 2, lim)
            self.assertEqual(run_main(watch_age, ["--file", f, "--max-hours", "14"])[0], 1)


class TestThirdPass(unittest.TestCase):
    """The third reader (22/10/2026, N55): the signer must refuse what the audit refuses, a folder link loop must end, Windows names, a cap on the total."""
    def watch(self, tmp):
        w = os.path.join(tmp, "repo", "watch"); os.makedirs(w); os.makedirs(os.path.join(tmp, "repo", "scripts")); json.dump({"a": 1}, open(os.path.join(w, "a.json"), "w")); return w

    def test_a_published_name_the_audit_refuses_is_not_signed(self):
        for name in ("a b.json", "x\ny.json", "caf\u00e9.json", "con.json", "a:b.json"):
            with tempfile.TemporaryDirectory() as tmp:
                w = self.watch(tmp); open(os.path.join(w, name), "w").write("{}")
                with self.assertRaises(sign_run.Unsignable): sign_run.manifest(w)
                code, out = run_main(sign_run, ["--watch", w]); self.assertEqual(code, 1, name); self.assertIn("REFUSED TO SIGN", out)
                self.assertFalse(os.path.exists(os.path.join(w, "signature.json")), name)

    def test_two_names_the_same_file_once_case_is_ignored_are_not_signed(self):
        with tempfile.TemporaryDirectory() as tmp:
            w = self.watch(tmp)
            if os.path.exists(os.path.join(w, "A.json")): self.skipTest("this disk ignores case")
            open(os.path.join(w, "A.json"), "w").write("{}")
            with self.assertRaises(sign_run.Unsignable): sign_run.manifest(w)

    def test_two_folder_links_that_point_at_each_other_end(self):
        import signal
        with tempfile.TemporaryDirectory() as tmp:
            w = self.watch(tmp); os.symlink(os.path.join(w, "l2"), os.path.join(w, "l1")); os.symlink(os.path.join(w, "l1"), os.path.join(w, "l2"))
            os.makedirs(os.path.join(w, "d")); os.symlink(w, os.path.join(w, "d", "back"))
            signal.signal(signal.SIGALRM, lambda *a: (_ for _ in ()).throw(TimeoutError("manifest did not end"))); signal.alarm(20)
            try: files = sorted(sign_run.manifest(w)["files"])
            finally: signal.alarm(0)
            self.assertEqual(files, ["a.json"])

    def test_the_same_files_as_the_earlier_listing_hidden_names_stay_out(self):
        with tempfile.TemporaryDirectory() as tmp:
            w = self.watch(tmp); open(os.path.join(w, ".hidden.json"), "w").write("{}"); os.makedirs(os.path.join(w, ".git")); open(os.path.join(w, ".git", "x.json"), "w").write("{}")
            self.assertEqual(sorted(sign_run.manifest(w)["files"]), ["a.json"])

    def test_windows_device_and_short_names_are_refused_ordinary_ones_are_not(self):
        for bad in ("con.json", "CON", "nul.md", "a/NUL.json", "COM1.csv", "lpt9", "aux.x.json", "BASE-S~1.JSO", "x~12.md", "a~1"):
            self.assertFalse(audit_public.safe_name(bad), bad)
        for ok in ("contract.json", "console.md", "scores/base.json", "a~b.json", "com10.json", "lpt.json", "a~1b.json"):
            self.assertTrue(audit_public.safe_name(ok), ok)

    def test_a_manifest_with_a_windows_device_name_writes_nothing(self):
        old = audit_public.get; sig = {"run_utc": "x", "manifest": {"files": {"con.json": "0" * 64}, "events_chain_head": None}, "signed": False}
        try:
            audit_public.get = lambda url, binary=False: json.dumps(sig)
            with tempfile.TemporaryDirectory() as tmp:
                with self.assertRaises(audit_public.UnsafeManifest): audit_public.fetch_watch(os.path.join(tmp, "d"))
                self.assertFalse(os.path.exists(os.path.join(tmp, "d")))
        finally: audit_public.get = old

    def test_the_total_of_the_files_has_a_cap_and_says_too_large(self):
        old, cap = audit_public.get, audit_public.MAX_TOTAL
        sig = {"run_utc": "x", "manifest": {"files": {"f%d.json" % i: "0" * 64 for i in range(5)}, "events_chain_head": None}, "signed": False}
        def get(url, binary=False): return json.dumps(sig) if url.endswith("signature.json") else (b"x" * 400 if binary else "x" * 400)
        try:
            audit_public.get = get; audit_public.MAX_TOTAL = 1000
            with tempfile.TemporaryDirectory() as tmp:
                with self.assertRaises(RuntimeError) as c: audit_public.fetch_watch(os.path.join(tmp, "d"))
                self.assertIn("too large", str(c.exception))
        finally: audit_public.get = old; audit_public.MAX_TOTAL = cap

    def test_one_file_over_the_cap_says_too_large_and_the_audit_exits_3(self):
        old = audit_public.get; sig = {"run_utc": "x", "manifest": {"files": {"big.json": "0" * 64}, "events_chain_head": None}, "signed": False}
        def get(url, binary=False):
            if url.endswith("signature.json"): return json.dumps(sig)
            raise audit_public.TooLarge("answer larger than %d bytes" % audit_public.MAX_BYTES)
        try:
            audit_public.get = get
            code, out = run_main(audit_public, ["--sample", "0"]); self.assertEqual(code, 3, out); self.assertIn("too large", out); self.assertIn("big.json", out)
        finally: audit_public.get = old

    def test_the_signer_refuses_a_total_over_the_cap(self):
        cap = audit_public.MAX_TOTAL
        try:
            audit_public.MAX_TOTAL = 10
            with tempfile.TemporaryDirectory() as tmp:
                w = self.watch(tmp); json.dump({"b": "x" * 50}, open(os.path.join(w, "b.json"), "w"))
                with self.assertRaises(sign_run.Unsignable): sign_run.manifest(w)
        finally: audit_public.MAX_TOTAL = cap

    def test_a_slug_with_a_trailing_newline_is_not_a_badge_name(self):
        import badges_protocol
        self.assertIsNone(badges_protocol.SLUG.fullmatch("foo\n")); self.assertTrue(badges_protocol.SLUG.fullmatch("foo-bar.1"))
        rows = [{"score": 40, "chain": "base", "target": "0x1", "stale": False}]; old = (badges_protocol.table, badges_protocol.protocols)
        try:
            badges_protocol.table = lambda w: []; badges_protocol.protocols = lambda t: {"foo\n": {"rows": rows}, "ok": {"rows": rows}}
            with tempfile.TemporaryDirectory() as tmp:
                code, out = run_main(badges_protocol, ["--watch", tmp, "--out", os.path.join(tmp, "o")])
                self.assertEqual(sorted(os.listdir(os.path.join(tmp, "o"))), ["ok.json"], out)
        finally: badges_protocol.table, badges_protocol.protocols = old

    def test_the_slug_check_holds_on_its_own_not_only_through_safe_name(self):
        """Since the safe_name guard was added (N55bis) "foo\\n" is refused twice, so removing or loosening SLUG no longer failed any test (a local replay of
        scripts/mutate.py found two mutants that survive for this reason). These slugs pass safe_name and only SLUG refuses them: a slash, a capital, an at sign, an empty slug, a leading dot, two dots, a leading dash, 81 characters."""
        import badges_protocol
        BAD = ("foo/bar", "Foo", "foo@bar", "", ".hidden", "..", "-x", "a" * 81)   # a slash, a capital, an at sign, empty, a leading dot, two dots, a leading dash, 81 characters (the limit is 80)
        for bad in BAD:
            self.assertTrue(audit_public.safe_name(bad + ".json"), bad)   # the second guard would let it through
            self.assertIsNone(badges_protocol.SLUG.fullmatch(bad), bad)
        rows = [{"score": 40, "chain": "base", "target": "0x1", "stale": False}]; old = (badges_protocol.table, badges_protocol.protocols)
        try:
            badges_protocol.table = lambda w: []; badges_protocol.protocols = lambda t: dict([(x, {"rows": rows}) for x in BAD] + [("ok", {"rows": rows})])
            with tempfile.TemporaryDirectory() as tmp:
                code, out = run_main(badges_protocol, ["--watch", tmp, "--out", os.path.join(tmp, "o")])
                self.assertEqual(sorted(os.listdir(os.path.join(tmp, "o"))), ["ok.json"], out)
        finally: badges_protocol.table, badges_protocol.protocols = old


class TestFourthPass(unittest.TestCase):
    """N55bis (priv): a refused signing must not look like a signed run; slugs that are device names; the signer under python3 -I."""
    def watch(self, tmp, sig_run, signed=True, txt=None):
        w = os.path.join(tmp, "watch"); os.makedirs(os.path.join(w, "scores")); json.dump({"run_utc": "2026-10-22T12:00:00Z", "oracles": [], "unread": [], "alerts": [], "total_targets": 1, "stale_total": 0}, open(os.path.join(w, "latest.json"), "w"))
        json.dump({"ok": True, "lines": 0}, open(os.path.join(w, "chain.json"), "w")); json.dump({"a": 1}, open(os.path.join(w, "scores", "x.json"), "w"))
        json.dump({"run_utc": sig_run, "manifest": {"files": {}, "events_chain_head": None}, "signed": signed, "public_key": "ab" * 32}, open(os.path.join(w, "signature.json"), "w"))
        if txt: open(os.path.join(w, "signature.txt"), "w").write(txt)
        return w

    def status(self, w):
        import run_status
        code, out = run_main(run_status, ["--watch", w]); return json.load(open(os.path.join(w, "status.json"))), json.load(open(os.path.join(w, "badge", "integrity.json")))

    def test_a_signature_of_an_earlier_run_is_stale_never_signed(self):
        with tempfile.TemporaryDirectory() as tmp:
            st, bd = self.status(self.watch(tmp, "2026-10-22T06:00:00Z"))
        self.assertEqual(st["checks"]["signature_status"], "stale"); self.assertFalse(st["checks"]["signed"]); self.assertEqual(st["state"], "alarm"); self.assertIn("signature STALE", " ".join(st["reasons"]))
        self.assertIn("signature stale", bd["message"]); self.assertNotIn("signed", bd["message"].replace("signature stale", ""))

    def test_a_refused_signing_in_the_log_is_stale_even_if_the_times_agree(self):
        with tempfile.TemporaryDirectory() as tmp:
            st, bd = self.status(self.watch(tmp, "2026-10-22T12:05:00Z", txt="REFUSED TO SIGN: 1 published name(s)\nexit code 1\n"))
        self.assertEqual(st["checks"]["signature_status"], "stale"); self.assertIn("signature stale", bd["message"])

    def test_a_fresh_signed_run_is_still_signed(self):
        with tempfile.TemporaryDirectory() as tmp:
            st, bd = self.status(self.watch(tmp, "2026-10-22T12:05:00Z"))
        self.assertEqual(st["checks"]["signature_status"], "signed"); self.assertTrue(st["checks"]["signed"]); self.assertTrue(bd["message"].startswith("signed")); self.assertEqual(st["state"], "ok", st["reasons"])

    def test_the_audit_of_a_stale_signature_has_its_own_exit_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            w = self.watch(tmp, "2026-10-22T06:00:00Z"); code, out = run_main(audit_public, ["--watch", w, "--sample", "0"])
        self.assertEqual(code, 4, out); self.assertIn("SIGNATURE STALE", out)

    def test_a_slug_that_is_a_device_name_gets_a_suffix_and_the_audit_accepts_the_file(self):
        import badges_protocol
        rows = [{"score": 40, "chain": "base", "target": "0x1", "stale": False}]; old = (badges_protocol.table, badges_protocol.protocols)
        try:
            badges_protocol.table = lambda w: []; badges_protocol.protocols = lambda t: {"con": {"rows": rows}, "com1": {"rows": rows}, "ok": {"rows": rows}}
            with tempfile.TemporaryDirectory() as tmp:
                run_main(badges_protocol, ["--watch", tmp, "--out", os.path.join(tmp, "o")]); names = sorted(os.listdir(os.path.join(tmp, "o")))
        finally: badges_protocol.table, badges_protocol.protocols = old
        self.assertEqual(names, ["com1-card.json", "con-card.json", "ok.json"]); self.assertTrue(all(audit_public.safe_name(n) for n in names))

    def test_the_signer_runs_under_python3_dash_I(self):
        import subprocess
        with tempfile.TemporaryDirectory() as tmp:
            w = os.path.join(tmp, "repo", "watch"); os.makedirs(w); os.makedirs(os.path.join(tmp, "repo", "scripts")); json.dump({"a": 1}, open(os.path.join(w, "a.json"), "w"))
            r = subprocess.run([sys.executable, "-I", os.path.join(HERE, "..", "sign_run.py"), "--watch", w], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


class TestFifthPass(unittest.TestCase):
    """23/10, second reader N71: three sentences of SECURITY.md described the 0.2.0 work, not the package that is published, or were wrong about `mcp_server.py check`."""
    def sec(self): return open(os.path.join(ROOT, "SECURITY.md"), encoding="utf-8").read()
    def check_src(self): return open(os.path.join(HERE, "..", "authority_check.py"), encoding="utf-8").read()

    def test_the_published_package_is_not_said_to_have_a_12_hour_preflight(self):
        s = self.sec(); self.assertNotIn("uses 12 for its", s); self.assertNotIn("--max-age-hours 12", s)
        self.assertIn("(version 0.1.0) uses 72 hours and flags an older snapshot", s); self.assertIn("the published package has no `preflight` answer; one with a 12-hour limit is being tested and may come in a later version", s)
        c = self.check_src(); self.assertNotIn("MCP preflight uses 12", c); self.assertNotIn("pass --max-age-hours 12 to match", c); self.assertNotIn("preflight is in the next version", c); self.assertIn("flags a snapshot older than 72 hours", c)

    def test_the_local_helper_check_tool_has_a_48_hour_limit(self):
        s = self.sec(); self.assertNotIn("does not verify `signature.json` or the age of the files", s)
        self.assertIn("Its `check` tool applies the 48-hour age limit", s)

    def test_the_live_addresses_are_in_the_reference_not_the_readme(self):
        s = self.sec(); self.assertNotIn("The live addresses are in the README.", s); self.assertIn("The live addresses are in `docs/REFERENCE.md`.", s)


    def test_the_hyperliquid_deploy_readme_lists_no_explorer_link_that_does_not_answer(self):
        # 23/10: https://testnet.purrsec.com returns 404 (HEAD and GET): the host answers, the page is not found; the line is a sentence, not a link
        t = open(os.path.join(ROOT, "chains", "hyperliquid", "deploy", "README.md"), encoding="utf-8").read()
        self.assertNotIn("purrsec", t); self.assertIn("returned 404 (not found) on 23 October 2026", t)

if __name__ == "__main__": unittest.main()
