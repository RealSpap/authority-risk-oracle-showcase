"""Slow tests: the package as a user gets it. Builds the wheel and the npm tarball into throwaway folders, installs them in a throwaway virtual environment and a throwaway npm project, starts the server from
the installed command and calls the four tools against a signed fixture, then against an altered one. Needs network access for pip (setuptools) only.

    AUTHORITY_RISK_SLOW=1 python3 -m unittest tests.test_install -v
    AUTHORITY_RISK_LIVE=1 AUTHORITY_RISK_SLOW=1 ...      # also calls the installed server against the real watch-data branch
"""
import glob, json, os, shutil, subprocess, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__)); PKG = os.path.normpath(os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
import test_package as tp  # noqa: E402

SLOW = os.environ.get("AUTHORITY_RISK_SLOW") == "1"


def rpc_lines(msgs): return "\n".join(json.dumps(m) for m in msgs) + "\n"


CALLS = [("getScore", {"chain": "robinhood", "address": tp.A}), ("listTargets", {"max_score": 50}), ("whoControls", {"chain": "base", "address": "0x1a3c9b1d2f0529d97f2afc5136cc23e58f1fd35b"}), ("checkProtocol", {"protocol": "alpha-swap-v3"})]


def session(cmd, data_dir, extra=(), env=None):
    msgs = [{"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {}}] + [{"jsonrpc": "2.0", "id": i + 1, "method": "tools/call", "params": {"name": n, "arguments": a}} for i, (n, a) in enumerate(CALLS)]
    r = subprocess.run(cmd + ["--data-dir", data_dir, "--trust-key", tp.PUB] + list(extra), input=rpc_lines(msgs), capture_output=True, text=True, timeout=120, env=env)
    out = [json.loads(l) for l in r.stdout.splitlines()]
    return r, out[0], [json.loads(o["result"]["content"][0]["text"]) for o in out[1:]]


@unittest.skipUnless(SLOW, "set AUTHORITY_RISK_SLOW=1")
class TestInstalled(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not os.path.exists(tp.FIXTURE): raise unittest.SkipTest("the repository's scripts/tests are not beside the package")
        cls.tmp = tempfile.TemporaryDirectory(); t = cls.tmp.name
        subprocess.run([sys.executable, os.path.join(PKG, "vendor_tools.py"), "--npm"], check=True, capture_output=True)
        cls.src = os.path.join(t, "pkg"); shutil.copytree(PKG, cls.src, ignore=shutil.ignore_patterns("tests", "__pycache__", "dist", "build", "*.egg-info", "node_modules", "*.tgz"))
        cls.fx = tp.load_fixture(); cls.data = os.path.join(t, "data"); cls.fx.build(cls.data); tp.sign_dir(cls.data)
        # Python: a wheel built from the copy, installed into a fresh virtual environment
        cls.venv = os.path.join(t, "venv"); subprocess.run([sys.executable, "-m", "venv", cls.venv], check=True)
        pip = os.path.join(cls.venv, "bin", "pip")
        # The files that will be published, when build_packages.sh has run (the workflows run it first); otherwise a wheel and a tarball built from the copy.
        built_wheels = glob.glob(os.path.join(PKG, "dist", "*.whl")); built_tgz = glob.glob(os.path.join(PKG, "dist-npm", "*.tgz"))
        if built_wheels and built_tgz: cls.wheel, cls.tgz, cls.used_built = built_wheels[0], built_tgz[0], True
        else:
            subprocess.run([pip, "wheel", "--no-deps", "-q", "-w", os.path.join(t, "dist"), cls.src], check=True, capture_output=True)
            cls.wheel = glob.glob(os.path.join(t, "dist", "*.whl"))[0]
            r = subprocess.run(["npm", "pack", "--silent"], cwd=os.path.join(cls.src, "npm"), capture_output=True, text=True, check=True); cls.tgz = os.path.join(cls.src, "npm", r.stdout.strip().splitlines()[-1]); cls.used_built = False
        subprocess.run([pip, "install", "-q", cls.wheel], check=True, capture_output=True)
        cls.proj = os.path.join(t, "proj"); os.makedirs(cls.proj); subprocess.run(["npm", "init", "-y", "--silent"], cwd=cls.proj, capture_output=True, check=True)
        subprocess.run(["npm", "install", "--silent", "--no-audit", "--no-fund", cls.tgz], cwd=cls.proj, check=True, capture_output=True)

    @classmethod
    def tearDownClass(cls): cls.tmp.cleanup()

    def check_session(self, cmd, env=None):
        r, init, res = session(cmd, self.data, env=env)
        self.assertEqual(r.returncode, 0, r.stderr); self.assertEqual(init["result"]["serverInfo"]["name"], "authority-risk-mcp")
        self.assertEqual([x["status"] for x in res], ["ok"] * 4); self.assertEqual(res[0]["composite"], 85); self.assertTrue(all(x["integrity"]["verified"] for x in res)); self.assertEqual(res[3]["verdict"], "ok")
        # the same folder with one file changed after it was signed
        bad = self.data + "-altered"; shutil.copytree(self.data, bad); p = os.path.join(bad, "scores", "robinhood-chain.json"); d = json.load(open(p)); d["targets"][0]["compositeScore"] = 99; json.dump(d, open(p, "w"))
        r, _i, res = session(cmd, bad, env=env); self.assertTrue(res[0]["integrity_failed"]); self.assertNotIn("composite", res[0])
        shutil.rmtree(bad)

    def test_the_installed_python_command_answers_the_four_tools_and_refuses_an_altered_folder(self):
        cmd = [os.path.join(self.venv, "bin", "authority-risk-mcp")]
        v = subprocess.run(cmd + ["--version"], capture_output=True, text=True); self.assertEqual(v.stdout.strip(), "authority-risk-mcp 0.1.0")
        self.check_session(cmd)

    def test_the_installed_npm_command_does_the_same_through_the_launcher(self):
        cmd = [os.path.join(self.proj, "node_modules", ".bin", "authority-risk-mcp")]
        v = subprocess.run(cmd + ["--version"], capture_output=True, text=True); self.assertEqual(v.stdout.strip(), "authority-risk-mcp 0.1.0")
        self.check_session(cmd)

    def test_the_npm_launcher_says_what_is_missing_when_there_is_no_python(self):
        empty = os.path.join(self.tmp.name, "empty"); os.makedirs(empty)
        node = shutil.which("node"); r = subprocess.run([node, os.path.join(self.proj, "node_modules", "authority-risk-mcp", "bin", "authority-risk-mcp.js"), "--version"], capture_output=True, text=True, env={"PATH": empty})
        self.assertEqual(r.returncode, 1); self.assertIn("Python 3.9 or newer was not found", r.stderr); self.assertIn("uvx", r.stderr)

    def test_both_packages_carry_the_same_name_version_licence_and_registry_name_and_no_private_detail(self):
        py = open(os.path.join(self.src, "pyproject.toml"), encoding="utf-8").read(); pj = json.load(open(os.path.join(self.src, "npm", "package.json")))
        self.assertIn('name = "authority-risk-mcp"', py); self.assertIn('version = "0.1.0"', py); self.assertEqual((pj["name"], pj["version"], pj["license"], pj["author"]), ("authority-risk-mcp", "0.1.0", "MIT", "RealSpap"))
        self.assertEqual(pj["mcpName"], "io.github.RealSpap/authority-risk-mcp"); self.assertIn("mcp-name: io.github.RealSpap/authority-risk-mcp", open(os.path.join(self.src, "README.md"), encoding="utf-8").read())
        self.assertEqual(pj["repository"]["url"], "git+https://github.com/RealSpap/authority-risk-oracle-showcase.git")
        sj = json.load(open(os.path.join(self.src, "server.json"))); self.assertEqual(sj["name"], pj["mcpName"]); self.assertEqual({p["registryType"] for p in sj["packages"]}, {"pypi", "npm"}); self.assertTrue(all(p["version"] == "0.1.0" and p["identifier"] == "authority-risk-mcp" for p in sj["packages"]))
        import re
        blob = "".join(open(f, encoding="utf-8", errors="ignore").read() for f in glob.glob(os.path.join(self.src, "**", "*"), recursive=True) if os.path.isfile(f) and not f.endswith((".tgz", ".pyc")) and "/_vendor/" not in f and "/npm/python/" not in f)
        for needle in (r"@[A-Za-z0-9.-]+\.(com|org|net|io|ch|fr)\b", "/" + "Users/", "cer" + "veau|anthro" + "pic|Claude Code|Co-Authored|Generated with", r"\b(Spap)\b(?!\w)"):
            for m in re.finditer(needle, blob, re.I):
                s = blob[max(0, m.start() - 30):m.end() + 30].replace("\n", " ")
                self.assertTrue("github.com" in s or "RealSpap" in s or "example." in s or "noreply" in s or "mcp.so" in s, "private detail? %r" % s)
        self.assertEqual(glob.glob(os.path.join(self.src, "**", "*.pem"), recursive=True) + glob.glob(os.path.join(self.src, "**", ".env*"), recursive=True), [])

    @unittest.skipUnless(os.environ.get("AUTHORITY_RISK_LIVE") == "1", "set AUTHORITY_RISK_LIVE=1 to call the installed server against the real watch-data branch")
    def test_live_against_the_real_branch(self):
        for cmd in ([os.path.join(self.venv, "bin", "authority-risk-mcp")], [os.path.join(self.proj, "node_modules", ".bin", "authority-risk-mcp")]):
            msgs = [{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "getScore", "arguments": {"chain": "robinhood", "address": "0x1f7d7550B1b028f7571E69A784071F0205FD2EfA"}}}]
            r = subprocess.run(cmd, input=rpc_lines(msgs), capture_output=True, text=True, timeout=180); res = json.loads(json.loads(r.stdout.splitlines()[0])["result"]["content"][0]["text"])
            self.assertEqual(res["status"], "ok", res); self.assertTrue(res["integrity"]["verified"] and res["integrity"]["pinned"], res["integrity"]); self.assertEqual(res["integrity"]["chain_head"], "verified")


if __name__ == "__main__":
    unittest.main()
