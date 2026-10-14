"""Tests of authority-risk-mcp: the signature check, the integrity of what is read (a local HTTP server stands for the network), the protocol, and parity with the repository's own tools.

    python3 -m unittest discover -s tests            # fast, no network (needs the repository around it, and `python3 vendor_tools.py` run once)
    AUTHORITY_RISK_SLOW=1 python3 -m unittest tests.test_install      # builds the wheel and the npm tarball in throwaway environments
"""
import hashlib, http.server, importlib.util, io, json, os, socket, subprocess, sys, tempfile, threading, unittest

HERE = os.path.dirname(os.path.abspath(__file__)); PKG = os.path.join(HERE, "..")
sys.path.insert(0, os.path.join(PKG, "src"))
from authority_risk_mcp import ed25519, server  # noqa: E402
from authority_risk_mcp.store import IntegrityFailed, NotRead, Store  # noqa: E402

FIXTURE = os.path.join(PKG, "..", "..", "scripts", "tests", "test_agent_tools.py")
SEED = bytes(range(32)); PUB = ed25519.public_from_seed(SEED).hex(); OTHER_SEED = bytes(range(1, 33)); OTHER_PUB = ed25519.public_from_seed(OTHER_SEED).hex()
A = "0x1f7d7550b1b028f7571e69a784071f0205fd2efa"


def load_fixture():
    spec = importlib.util.spec_from_file_location("agent_tools_fixture", FIXTURE); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m


def sign_dir(w, seed=SEED, signed=True, tamper_manifest=False, wrong_head=False):
    """Write events.jsonl and signature.json for the fixture folder `w`, the way scripts/sign_run.py does."""
    open(os.path.join(w, "events.jsonl"), "w").write('{"n":1}\n{"n":2}\n')
    files = {}
    for base, _d, names in os.walk(w):
        for n in names:
            rel = os.path.relpath(os.path.join(base, n), w)
            if rel != "signature.json": files[rel] = hashlib.sha256(open(os.path.join(base, n), "rb").read()).hexdigest()
    head = hashlib.sha256(b'{"n":2}').hexdigest() if not wrong_head else "0" * 64
    manifest = {"files": files, "events_chain_head": head, "count": len(files), "code": {}, "commit": None}
    body = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    rec = {"run_utc": "2026-10-14T09:55:22Z", "manifest": manifest, "signed": signed, "what": "test"}
    if signed:
        rec["public_key"] = ed25519.public_from_seed(seed).hex(); rec["signature"] = ed25519.sign(seed, body).hex()
    if tamper_manifest: rec["manifest"]["count"] += 1
    json.dump(rec, open(os.path.join(w, "signature.json"), "w"))


class Serve:
    """A local HTTP server over a folder, with an optional per-file replacement (to serve a tampered copy)."""
    def __init__(self, root, replace=None):
        outer = self; self.replace = replace or {}
        class H(http.server.SimpleHTTPRequestHandler):
            def __init__(s, *a, **k): super().__init__(*a, directory=root, **k)
            def log_message(s, *a): pass
            def do_GET(s):
                rel = s.path.lstrip("/").split("?")[0]
                if rel in outer.replace:
                    data = outer.replace[rel]; s.send_response(200); s.send_header("Content-Length", str(len(data))); s.end_headers(); s.wfile.write(data); return
                if rel == "redirect-away": s.send_response(302); s.send_header("Location", "https://evil.example/x"); s.end_headers(); return
                super().do_GET()
        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H); self.url = "http://127.0.0.1:%d/" % self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
    def stop(self): self.httpd.shutdown(); self.httpd.server_close()


class Base(unittest.TestCase):
    def setUp(self):
        if not os.path.exists(FIXTURE): self.skipTest("the repository's scripts/tests are not beside the package")
        self.fx = load_fixture(); self.tmp = tempfile.TemporaryDirectory(); self.W = os.path.join(self.tmp.name, "w"); self.fx.build(self.W)
        self.servers = []
    def tearDown(self):
        for s in self.servers: s.stop()
        self.tmp.cleanup()
    def serve(self, **k): s = Serve(self.W, **k); self.servers.append(s); return s
    def store(self, urls=None, **k):
        k.setdefault("trusted_keys", [PUB]); k.setdefault("retry_wait", 0)
        return Store(bases=urls, **k)
    def call(self, st, name, args): return server.answer(st, name, args)


class TestEd25519(unittest.TestCase):
    def test_rfc8032_vectors_and_tampering(self):
        for seed, pk, msg, sig in (("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60", "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a", "",
                                    "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b"),
                                   ("4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb", "3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c", "72",
                                    "92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da085ac1e43e15996e458f3613d0f11d8c387b2eaeb4302aeeb00d291612bb0c00")):
            seed, pk, msg, sig = map(bytes.fromhex, (seed, pk, msg, sig))
            self.assertEqual(ed25519.public_from_seed(seed), pk); self.assertEqual(ed25519.sign(seed, msg), sig); self.assertTrue(ed25519.verify(pk, msg, sig))
            self.assertFalse(ed25519.verify(pk, msg + b"x", sig)); bad = bytearray(sig); bad[40] ^= 1; self.assertFalse(ed25519.verify(pk, msg, bytes(bad)))
            self.assertFalse(ed25519.verify(bytes(32), msg, sig))

    def test_malformed_inputs_are_false_not_errors(self):
        pk = ed25519.public_from_seed(SEED); sig = ed25519.sign(SEED, b"m")
        for a in ((pk[:31], b"m", sig), (pk, b"m", sig[:63]), (b"", b"", b""), (pk, b"m", b"\xff" * 64), (b"\xff" * 32, b"m", sig)): self.assertFalse(ed25519.verify(*a))

    def test_a_malleated_signature_is_refused(self):
        """The same signature with S replaced by S + the group order satisfies the verification equation; it must be refused."""
        pk = ed25519.public_from_seed(SEED); sig = ed25519.sign(SEED, b"m"); s = int.from_bytes(sig[32:], "little")
        self.assertTrue(ed25519.verify(pk, b"m", sig)); self.assertFalse(ed25519.verify(pk, b"m", sig[:32] + (s + ed25519.Q).to_bytes(32, "little")))

    def test_it_agrees_with_pynacl_when_pynacl_is_installed(self):
        try: from nacl.signing import SigningKey
        except ImportError: self.skipTest("PyNaCl is not installed")
        for i in range(5):
            sk = SigningKey(bytes([i + 1]) * 32); msg = b"manifest %d" % i; signed = sk.sign(msg)
            self.assertTrue(ed25519.verify(bytes(sk.verify_key), msg, signed.signature)); self.assertEqual(ed25519.sign(bytes([i + 1]) * 32, msg), signed.signature)

    def test_the_live_signature_of_the_watch_verifies_when_a_copy_is_at_hand(self):
        p = os.environ.get("WATCH_SIGNATURE_JSON")
        if not p or not os.path.exists(p): self.skipTest("set WATCH_SIGNATURE_JSON to a copy of watch-data/signature.json")
        s = json.load(open(p)); self.assertTrue(ed25519.verify(bytes.fromhex(s["public_key"]), json.dumps(s["manifest"], sort_keys=True, separators=(",", ":")).encode(), bytes.fromhex(s["signature"])))


class TestIntegrityOverHttp(Base):
    def test_a_signed_pinned_snapshot_is_read_and_says_so(self):
        import calendar, time
        t0 = calendar.timegm(time.strptime("2026-10-14T09:55:22Z", "%Y-%m-%dT%H:%M:%SZ"))
        sign_dir(self.W); s = self.serve(); st = self.store([s.url], now=lambda: t0 + 3600)
        r = self.call(st, "getScore", {"chain": "robinhood", "address": A})
        self.assertEqual((r["status"], r["composite"]), ("ok", 85)); i = r["integrity"]
        self.assertTrue(i["verified"]); self.assertEqual((i["signed_by"], i["pinned"], i["chain_head"]), (PUB, True, "verified")); self.assertEqual(i["manifest_run_utc"], "2026-10-14T09:55:22Z")
        self.assertEqual((i["snapshot_age_hours"], i["snapshot_stale"]), (1.0, False))
        st.close()
        st = self.store([s.url], now=lambda: t0 + 5 * 86400); i = self.call(st, "getScore", {"chain": "robinhood", "address": A})["integrity"]; self.assertEqual((i["snapshot_age_hours"], i["snapshot_stale"]), (120.0, True)); st.close()

    def test_a_tampered_file_is_never_a_value(self):
        sign_dir(self.W); good = json.load(open(os.path.join(self.W, "scores", "robinhood-chain.json"))); good["targets"][0]["compositeScore"] = 99
        s = self.serve(replace={"scores/robinhood-chain.json": json.dumps(good).encode()}); st = self.store([s.url])
        r = self.call(st, "getScore", {"chain": "robinhood", "address": A})
        self.assertEqual(r["status"], "not_read"); self.assertTrue(r["integrity_failed"]); self.assertNotIn("composite", r); self.assertIn("scores/robinhood-chain.json", r["reason"])

    def test_the_second_source_is_used_when_the_first_serves_a_different_copy_and_a_mismatch_everywhere_is_refused(self):
        sign_dir(self.W); bad = self.serve(replace={"tvl.json": b'{"matched": {}}'}); good = self.serve()
        st = self.store([bad.url, good.url]); self.assertEqual(self.call(st, "getScore", {"chain": "robinhood", "address": A})["status"], "ok")
        st2 = self.store([bad.url]); self.assertTrue(self.call(st2, "getScore", {"chain": "robinhood", "address": A})["integrity_failed"])

    def test_a_signature_problem_is_refused(self):
        for label, kw, store_kw in (("unsigned", dict(signed=False), {}), ("unpinned key", dict(seed=OTHER_SEED), {}), ("manifest altered after signing", dict(tamper_manifest=True), {}), ("event log head differs", dict(wrong_head=True), {})):
            sign_dir(self.W, **kw); s = self.serve(); st = self.store([s.url], **store_kw)
            r = self.call(st, "getScore", {"chain": "robinhood", "address": A})
            self.assertEqual((r["status"], r["integrity_failed"]), ("not_read", True), label); self.assertNotIn("composite", r, label)

    def test_the_explicit_overrides_read_but_say_not_verified_or_not_pinned(self):
        sign_dir(self.W, signed=False); s = self.serve(); st = self.store([s.url], allow_unsigned=True)
        i = self.call(st, "getScore", {"chain": "robinhood", "address": A})["integrity"]; self.assertFalse(i["verified"]); self.assertEqual(i["signature"], "unsigned")
        sign_dir(self.W, seed=OTHER_SEED); st = self.store([s.url], allow_unpinned=True)
        i = self.call(st, "getScore", {"chain": "robinhood", "address": A})["integrity"]; self.assertTrue(i["verified"]); self.assertFalse(i["pinned"])
        st = self.store([s.url], trusted_keys=[PUB, OTHER_PUB]); self.assertTrue(self.call(st, "getScore", {"chain": "robinhood", "address": A})["integrity"]["pinned"])

    def test_no_network_is_not_read_and_not_tampered(self):
        sign_dir(self.W); s = self.serve(); url = s.url; s.stop(); self.servers.remove(s)
        r = self.call(self.store([url], timeout=2), "getScore", {"chain": "robinhood", "address": A}); self.assertEqual((r["status"], r["integrity_failed"]), ("not_read", False)); self.assertNotIn("composite", r)

    def test_a_redirect_to_another_host_is_refused(self):
        sign_dir(self.W); s = self.serve(); st = self.store([s.url])
        with self.assertRaises(NotRead): st._fetch(s.url, "redirect-away")

    def test_the_default_sources_are_https_and_http_is_for_loopback_only(self):
        from authority_risk_mcp.store import DEFAULT_BASES
        self.assertTrue(all(b.startswith("https://") for b in DEFAULT_BASES))
        with self.assertRaises(ValueError): Store(bases=["http://example.com/"])
        with self.assertRaises(ValueError): Store(bases=["ftp://example.com/"])

    def test_a_new_run_landing_between_two_reads_gets_one_retry(self):
        sign_dir(self.W); s = self.serve(); st = self.store([s.url], retry_wait=0); calls = []
        original = st._sync_once
        def flaky():
            calls.append(1)
            if len(calls) == 1: raise IntegrityFailed("a run landed between the manifest and a file")
            return original()
        st._sync_once = flaky; r = self.call(st, "getScore", {"chain": "robinhood", "address": A}); self.assertEqual(r["status"], "ok"); self.assertEqual(len(calls), 2)


class TestLocalFolder(Base):
    def test_a_signed_folder_is_checked_and_a_changed_file_is_refused(self):
        sign_dir(self.W); st = self.store(data_dir=self.W); self.assertTrue(self.call(st, "getScore", {"chain": "base", "address": "0x1a3c9b1d2f0529d97f2afc5136cc23e58f1fd35b"})["integrity"]["verified"])
        open(os.path.join(self.W, "second_opinion.json"), "w").write('{"results": []}')
        r = self.call(self.store(data_dir=self.W), "whoControls", {"chain": "base", "address": "0x1a3c9b1d2f0529d97f2afc5136cc23e58f1fd35b"}); self.assertTrue(r["integrity_failed"]); self.assertNotIn("admin_kind", r)

    def test_a_folder_without_a_signature_reads_but_says_it_is_not_checked(self):
        r = self.call(self.store(data_dir=self.W), "getScore", {"chain": "robinhood", "address": A}); self.assertEqual(r["status"], "ok"); self.assertFalse(r["integrity"]["verified"]); self.assertIn("NOT checked", r["integrity"]["note"])

    def test_the_offline_mode_touches_no_network(self):
        sign_dir(self.W); real = socket.socket.connect
        def no(*a, **k): raise AssertionError("a network connection was attempted")
        socket.socket.connect = no
        try:
            st = self.store(data_dir=self.W)
            for name, args in (("getScore", {"chain": "robinhood", "address": A}), ("listTargets", {"max_score": 50}), ("whoControls", {"chain": "base", "address": "0x1a3c9b1d2f0529d97f2afc5136cc23e58f1fd35b"}), ("checkProtocol", {"protocol": "alpha-swap-v3"})):
                self.assertEqual(self.call(st, name, args)["status"], "ok", name)
        finally: socket.socket.connect = real


class TestServerAndParity(Base):
    def test_the_four_tools_are_listed_read_only_and_arguments_are_checked(self):
        sign_dir(self.W); st = self.store(data_dir=self.W)
        tl = server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, st)["result"]["tools"]
        self.assertEqual([t["name"] for t in tl], ["getScore", "listTargets", "whoControls", "checkProtocol"]); self.assertTrue(all(t["annotations"]["readOnlyHint"] for t in tl))
        for bad in ({"name": "getScore", "arguments": {"chain": "base"}}, {"name": "listTargets", "arguments": {"max_score": 101}}, {"name": "checkProtocol", "arguments": {"protocol": "x", "path": "/etc/passwd"}}, {"name": "tour", "arguments": {}}):
            self.assertIn("error", server.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": bad}, st))
        init = server.handle({"jsonrpc": "2.0", "id": 3, "method": "initialize", "params": {}}, st)["result"]; self.assertEqual(init["serverInfo"]["name"], "authority-risk-mcp")
        self.assertIsNone(server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}, st))

    def test_the_answers_equal_the_repositorys_own_tools_apart_from_the_integrity_block(self):
        sign_dir(self.W); st = self.store(data_dir=self.W)
        sys.path.insert(0, os.path.join(PKG, "..", "..", "scripts")); import agent_tools as repo  # noqa: E402
        for name, args, fn in (("getScore", {"chain": "robinhood", "address": A}, lambda: repo.get_score(self.W, "robinhood", A)), ("listTargets", {"max_score": 50}, lambda: repo.list_targets(self.W, None, 50, None, None, 25)),
                               ("whoControls", {"chain": "base", "address": "0x1a3c9b1d2f0529d97f2afc5136cc23e58f1fd35b"}, lambda: repo.who_controls(self.W, "base", "0x1a3c9b1d2f0529d97f2afc5136cc23e58f1fd35b")), ("checkProtocol", {"protocol": "alpha-swap-v3", "min_score": 30}, lambda: repo.check_protocol(self.W, "alpha-swap-v3", 30))):
            got = self.call(st, name, args); got.pop("integrity"); self.assertEqual(json.loads(json.dumps(got)), json.loads(json.dumps(fn())), name)

    def test_over_standard_input_and_output_like_a_client_does(self):
        sign_dir(self.W)
        msgs = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}, {"jsonrpc": "2.0", "method": "notifications/initialized"}, {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "getScore", "arguments": {"chain": "robinhood", "address": A}}}]
        r = subprocess.run([sys.executable, "-W", "ignore", "-m", "authority_risk_mcp", "--data-dir", self.W, "--trust-key", PUB], input="\n".join(json.dumps(m) for m in msgs) + "\nnot json\n", capture_output=True, text=True, env=dict(os.environ, PYTHONPATH=os.path.join(PKG, "src")), timeout=60)
        out = [json.loads(l) for l in r.stdout.splitlines()]; self.assertEqual(len(out), 3); self.assertEqual(json.loads(out[1]["result"]["content"][0]["text"])["composite"], 85); self.assertEqual(out[2]["error"]["code"], -32700); self.assertEqual(r.stderr, "")


class TestBuild(unittest.TestCase):
    def test_no_file_in_the_package_root_hides_a_module_that_the_build_tools_run(self):
        """`python -m build` run in this folder once ran a file called build.py found here instead of the PyPA module, and the first release failed. No top-level .py file may carry the name of a module the build chain runs or imports."""
        hidden = {"build", "pip", "twine", "setuptools", "wheel", "venv", "ensurepip", "unittest", "json", "os", "sys", "re", "test", "site", "pkg_resources", "distutils", "packaging", "importlib"}
        mine = {os.path.splitext(n)[0] for n in os.listdir(PKG) if n.endswith(".py")}
        self.assertEqual(sorted(mine & hidden), [])

    def test_the_publish_workflow_and_the_build_check_run_the_same_build_file(self):
        wf = os.path.join(PKG, "..", "..", ".github", "workflows")
        for name in ("publish-mcp.yml", "package-build.yml"):
            p = os.path.join(wf, name)
            if not os.path.exists(p): self.skipTest(name + " is not beside the package")
            text = open(p, encoding="utf-8").read(); self.assertIn("bash build_packages.sh", text, name); self.assertNotIn("python3 -m build", text, name)   # the commands live in one file
        self.assertTrue(os.path.exists(os.path.join(PKG, "build_packages.sh")))

    def test_the_vendored_modules_are_the_repositorys_scripts_byte_for_byte(self):
        if not os.path.exists(FIXTURE): self.skipTest("the repository's scripts are not beside the package")
        r = subprocess.run([sys.executable, os.path.join(PKG, "vendor_tools.py"), "--check"], capture_output=True, text=True); self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_no_vendored_module_that_can_send_anything_is_in_the_package(self):
        v = os.path.join(PKG, "src", "authority_risk_mcp", "_vendor")
        if not os.path.isdir(v): self.skipTest("run vendor_tools.py first")
        src = "".join(open(os.path.join(v, n), encoding="utf-8").read() for n in os.listdir(v) if n.endswith(".py"))
        for word in ("urlopen", "send_telegram", "send_discord", "smtplib", "socket.", "subprocess", "requests."): self.assertNotIn(word, src, word)
        store_src = open(os.path.join(PKG, "src", "authority_risk_mcp", "store.py"), encoding="utf-8").read(); self.assertEqual(store_src.count("urlopen") + store_src.count("self._opener.open"), 1)   # the one place that reads the network


if __name__ == "__main__":
    unittest.main()
