"""scripts/check_structure.py : each rule must refuse its own planted fault (root entry, forbidden name, README ceiling, dash)."""
import importlib.util, shutil, tempfile, unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("check_structure", HERE.parent / "check_structure.py")
cs = importlib.util.module_from_spec(spec); spec.loader.exec_module(cs)
CFG = {"root_files": ["README.md"], "root_dirs": ["docs"], "max_root_entries": 2, "incident_parent": None, "incident_markers": [],
       "forbidden_names": ["draft*", "scratch*", "work"], "allowed_paths": [], "readme_max_lines": 10, "legacy_redirects": [], "max_legacy_redirects": 0}


class StructureRules(unittest.TestCase):
    def run_check(self, files):
        d = Path(tempfile.mkdtemp())
        try:
            for rel, text in files.items():
                p = d / rel; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(text, encoding="utf-8")
            return cs.check(d, CFG)
        finally:
            shutil.rmtree(d)

    def test_clean_tree_passes(self):
        self.assertEqual(self.run_check({"README.md": "# T\n", "docs/a.md": "x\n"}), [])

    def test_new_root_file_is_refused(self):
        self.assertTrue(any("unexpected" in e for e in self.run_check({"README.md": "# T\n", "NOTES.md": "x\n"})))

    def test_forbidden_name_is_refused(self):
        self.assertTrue(any("forbidden" in e for e in self.run_check({"README.md": "# T\n", "docs/draft.md": "x\n"})))

    def test_long_readme_is_refused(self):
        self.assertTrue(any("ceiling" in e for e in self.run_check({"README.md": "x\n" * 11})))

    def test_dash_is_refused(self):
        self.assertTrue(any("dash" in e for e in self.run_check({"README.md": "a " + chr(0x2014) + " b\n"})))

    def test_missing_readme_is_refused(self):
        self.assertTrue(any("missing" in e for e in self.run_check({"docs/a.md": "x\n"})))


if __name__ == "__main__":
    unittest.main()
