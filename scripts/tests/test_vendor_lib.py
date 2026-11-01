"""The installable package carries the scripts/lib/ modules that its vendored modules import (30/10/2026: risk_by_cause.py began to import lib.reader_audit and the package failed at import)."""
import os, re, sys, tempfile, unittest
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "packages", "authority-risk-mcp"))
import vendor_tools  # noqa: E402


class TestVendoredLib(unittest.TestCase):
    def test_every_lib_import_of_a_vendored_module_is_carried(self):
        want = vendor_tools.expected()
        for m in vendor_tools.MODULES:
            for x in re.findall(r"^\s*(?:from lib\.(\w+) import|import lib\.(\w+))", open(os.path.join(ROOT, "scripts", m + ".py"), encoding="utf-8").read(), re.M):
                n = x[0] or x[1]
                self.assertIn("lib/%s.py" % n, want, "%s imports lib.%s, which the package does not carry" % (m, n))
        if any(k.startswith("lib/") for k in want): self.assertIn("lib/__init__.py", want)

    def test_the_dependencies_of_a_lib_module_are_followed_and_a_missing_one_stops_the_build(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "lib"))
            open(os.path.join(d, "a.py"), "w").write("from lib.b import x\n"); open(os.path.join(d, "lib", "b.py"), "w").write("import lib.c\n"); open(os.path.join(d, "lib", "c.py"), "w").write("y = 1\n")
            old = vendor_tools.SCRIPTS; vendor_tools.SCRIPTS = d
            try:
                self.assertEqual(vendor_tools.lib_modules(["a"]), ["b", "c"])
                open(os.path.join(d, "lib", "b.py"), "w").write("import lib.zzz\n")
                with self.assertRaises(SystemExit): vendor_tools.lib_modules(["a"])
                open(os.path.join(d, "a.py"), "w").write("import os\n"); self.assertEqual(vendor_tools.lib_modules(["a"]), [])
            finally: vendor_tools.SCRIPTS = old


if __name__ == "__main__":
    unittest.main()
