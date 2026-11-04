"""Closing addition of 30/10/2026: the page docs/MULTISIG-SHAPES.md is generated from the scorers by scripts/multisig_shapes.py, and a test regenerates it and compares. Standard library only; no network."""
import ast, glob, os, sys, tempfile, textwrap, unittest

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import multisig_shapes as ms  # noqa: E402


def analyse_source(src):
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "scorers.py"); open(p, "w", encoding="utf-8").write(textwrap.dedent(src)); return {name: sorted({c for c, _ in items}) for name, _, items in ms.analyse(p)}


class TestThePageMatchesTheCode(unittest.TestCase):
    def test_the_page_is_what_the_scorers_say(self):
        self.assertEqual(open(ms.PAGE, encoding="utf-8").read(), ms.build(), "run python3 scripts/multisig_shapes.py --write")

    def test_check_mode_passes_and_fails(self):
        self.assertEqual(ms.main(["--check"]), 0)
        real = ms.PAGE
        with tempfile.TemporaryDirectory() as d:
            ms.PAGE = os.path.join(d, "x.md"); open(ms.PAGE, "w").write("stale\n")
            try: self.assertEqual(ms.main(["--check"]), 1)
            finally: ms.PAGE = real

    def test_every_function_that_builds_a_multisig_score_is_in_the_page(self):
        page = open(ms.PAGE, encoding="utf-8").read()
        for rel in ["scripts/lib/scorers.py"] + sorted(os.path.relpath(p, ROOT) for p in glob.glob(os.path.join(ROOT, "chains", "*", "scorers.py"))):
            tree = ast.parse(open(os.path.join(ROOT, rel), encoding="utf-8").read()); wanted = set()
            for fn in ast.walk(tree):
                if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)): continue
                if any(isinstance(k, ast.Constant) and k.value == "multisigScore" for d in ast.walk(fn) if isinstance(d, ast.Dict) for k in d.keys): wanted.add(fn.name)
                if any(isinstance(a, ast.Assign) and any(isinstance(t, ast.Subscript) and isinstance(t.slice, ast.Constant) and t.slice.value == "multisigScore" for t in a.targets) for a in ast.walk(fn)): wanted.add(fn.name)
            for name in wanted: self.assertIn("| `%s` |" % name, page, rel)

    def test_what_the_parser_could_not_follow_is_listed_apart(self):
        page = open(ms.PAGE, encoding="utf-8").read(); self.assertIn("## Left to be read by hand", page)
        tail = page.split("## Left to be read by hand")[1]
        rows = [l for l in page.splitlines() if l.startswith("| `") and "other" in l.split("|")[3]]
        for l in rows: self.assertIn(l.split("|")[2].strip(), tail, l)   # a function classed "other" is named in the closing section

    def test_the_limits_page_points_to_it(self):
        self.assertIn("docs/MULTISIG-SHAPES.md", open(os.path.join(ROOT, "docs", "LIMITS.md"), encoding="utf-8").read())


class TestTheClassification(unittest.TestCase):
    def test_the_standard_formula_in_any_order_and_with_any_names(self):
        for expr in ("min(100, t * 15 + max(0, n - t) * 5)", "min(max(0, n - t) * 5 + t * 15, 100)", "min(t * 15 + max(0, len(o) - t) * 5, 100)"):
            t = ast.parse(expr.replace("t ", "t ")).body[0].value; self.assertTrue(ms.is_standard(t), expr)

    def test_a_near_miss_is_not_the_standard_formula(self):
        for expr in ("min(100, t * 14 + max(0, n - t) * 5)", "min(100, t * 15 + max(0, n - t) * 6)", "min(99, t * 15 + max(0, n - t) * 5)", "min(100, t * 15 + max(1, n - t) * 5)", "min(100, t * 15 + max(0, n - k) * 5)", "min(100, t * 15 + (n - t) * 5)", "min(100, t * 15)"):
            self.assertFalse(ms.is_standard(ast.parse(expr).body[0].value), expr)

    def test_classes_of_synthetic_scorers(self):
        got = analyse_source('''
            def a(t, o):
                m = min(100, t * 15 + max(0, len(o) - t) * 5)
                return {"multisigScore": m}
            def b():
                m = 0
                return {"multisigScore": m}
            def c(x, y):
                m = min(x, y)
                return {"multisigScore": m}
            def d(root):
                m = root[1] * 10 if root else 0
                return {"multisigScore": m}
            def e():
                admin, m, tl = (40, 0, 0)
                return {"multisigScore": m}
            def h(t, n): return min(100, t * 15 + max(0, n - t) * 5)
            def f(t, n):
                m = h(t, n)
                return {"multisigScore": m}
            def g(m):
                return {"multisigScore": m}
            def r():
                m = 5 if cond() else 20
                return {"multisigScore": m}
            ''')
        self.assertEqual(got, {"a": ["standard"], "b": ["fixed"], "c": ["weakest"], "d": ["weights"], "e": ["fixed"], "f": ["helper"], "g": ["other"], "r": ["rule"]})

    def test_an_assignment_to_the_key_is_a_site_too(self):
        got = analyse_source('''
            def fix(entries, k, n):
                for e in entries:
                    e["multisigScore"] = min(100, k * 15 + max(0, n - k) * 5)
            ''')
        self.assertEqual(got, {"fix": ["standard"]})

    def test_a_tuple_returned_by_a_helper_is_followed(self):
        got = analyse_source('''
            def helper(t, n): return (20, min(100, t * 15 + max(0, n - t) * 5), 0)
            def s(t, n):
                a, m, tl = helper(t, n)
                return {"multisigScore": m}
            ''')
        self.assertEqual(got, {"s": ["standard"]})

    def test_branches_with_two_classes_show_both(self):
        got = analyse_source('''
            def s(t, n, ok):
                m = 0
                if ok: m = min(100, t * 15 + max(0, n - t) * 5)
                return {"multisigScore": m}
            ''')
        self.assertEqual(got, {"s": ["fixed", "standard"]})


if __name__ == "__main__":
    unittest.main()
