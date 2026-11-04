#!/usr/bin/env python3
"""Which formula gives the multisig sub-score, scorer by scorer. Reads the scorers of the repository with the Python parser (read only, no network, nothing is imported or run) and writes docs/MULTISIG-SHAPES.md.

    python3 scripts/multisig_shapes.py            # print the page
    python3 scripts/multisig_shapes.py --write    # write docs/MULTISIG-SHAPES.md
    python3 scripts/multisig_shapes.py --check    # exit 1 when docs/MULTISIG-SHAPES.md is not what the code says

For every function that builds a dict with the key `multisigScore`, or assigns `entry["multisigScore"] = ...`, the value is followed back to its assignments in the same function and each one is put in a class:
  standard     min(100, t * 15 + max(0, n - t) * 5), the formula of METHODOLOGY.md (threshold t, owner count n), in any order of the terms
  helper       a call to a helper function of the same file, classed by what the helper returns
  weakest      the minimum of several other values (the weakest set decides)
  weights      a formula with other weights, or a rule on a list of Safes (the Zcash formula on the concentration of miners is one of them)
  rule         a value chosen by a condition between constants
  fixed        a constant written in the code (the notes may follow the configuration read; the number does not)
  other        anything else: named in the page so that it is read by hand
It reports the shape of the CODE per scorer. It does not say which scorer serves which target, and it does not run any scorer, so it cannot say which branch a given target takes. Standard library only."""
import ast, glob, os, sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
PAGE = os.path.join(ROOT, "docs", "MULTISIG-SHAPES.md")
FILES = ["scripts/lib/scorers.py"]   # then chains/*/scorers.py, sorted


def _num(n, v=None):
    return isinstance(n, ast.Constant) and isinstance(n.value, (int, float)) and not isinstance(n.value, bool) and (v is None or n.value == v)


def _terms(n):
    return [n.left, n.right] if isinstance(n, ast.BinOp) and isinstance(n.op, ast.Add) else None


def is_standard(node):
    """min(100, t * 15 + max(0, n - t) * 5), the arguments of min and the two terms in any order, t the same expression in both terms."""
    if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "min" and len(node.args) == 2): return False
    for cap, body in (node.args, node.args[::-1]):
        if not _num(cap, 100): continue
        ts = _terms(body)
        if not ts: continue
        for a, b in (ts, ts[::-1]):
            if not (isinstance(a, ast.BinOp) and isinstance(a.op, ast.Mult) and _num(a.right, 15)): continue
            if not (isinstance(b, ast.BinOp) and isinstance(b.op, ast.Mult) and _num(b.right, 5) and isinstance(b.left, ast.Call) and isinstance(b.left.func, ast.Name) and b.left.func.id == "max" and len(b.left.args) == 2 and _num(b.left.args[0], 0)): continue
            diff = b.left.args[1]
            if isinstance(diff, ast.BinOp) and isinstance(diff.op, ast.Sub) and ast.dump(diff.right) == ast.dump(a.left): return True
    return False


class Ctx:
    """The function being read and the constants of the module, to follow a name one step back."""
    def __init__(self, fn=None, consts=None): self.fn, self.consts, self.busy = fn, consts or {}, set()


def _assigned(ctx, name):
    """Expressions assigned to `name` in the function (other than `name` itself), as (value, tuple index or None)."""
    out = []
    for st in ast.walk(ctx.fn) if ctx.fn is not None else []:
        if isinstance(st, ast.Assign):
            for t in st.targets:
                if isinstance(t, ast.Name) and t.id == name and not (isinstance(st.value, ast.Name) and st.value.id == name): out.append((st.value, None))
                elif isinstance(t, (ast.Tuple, ast.List)) and any(isinstance(e, ast.Name) and e.id == name for e in t.elts): out.append((st.value, [k for k, e in enumerate(t.elts) if isinstance(e, ast.Name) and e.id == name][0]))
    return out


def classify(node, helpers, depth=0, ctx=None):
    """(class, short text) of one expression."""
    text = ast.unparse(node)
    if _num(node): return "fixed", text
    if is_standard(node): return "standard", ""
    if ctx is not None and depth < 4:
        if isinstance(node, ast.Name) and node.id not in ctx.busy:
            ctx.busy.add(node.id)
            try:
                got = [classify(v, helpers, depth + 1, ctx) if i is None else element(v, i, helpers, 0, ctx)[0] for v, i in _assigned(ctx, node.id)]
                if not got and node.id in ctx.consts: got = [classify(ctx.consts[node.id], helpers, depth + 1, ctx)]
            finally: ctx.busy.discard(node.id)
            kinds = {c for c, _ in got}
            if got and len(kinds) == 1: return got[0][0], got[0][1]
            if got: return "mixed", "/".join(sorted(kinds))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "min" and len(node.args) == 2 and _num(node.args[1], 100) and not isinstance(node.args[0], (ast.GeneratorExp,)): return classify(node.args[0], helpers, depth + 1, ctx)
        if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Call) and isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, int):
            return element(node.value, node.slice.value, helpers, 0, ctx)[0]
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "min" and node.args:
        # min(x, 100) around a name is a cap, not a shape of its own
        if len(node.args) == 2 and _num(node.args[1], 100) and isinstance(node.args[0], ast.Name): return "other", text
        if all(isinstance(a, (ast.Name, ast.Subscript)) or isinstance(a, ast.GeneratorExp) for a in node.args): return "weakest", text
        if len(node.args) == 1 and isinstance(node.args[0], ast.GeneratorExp) and is_standard_gen(node.args[0]): return "weakest", text
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in helpers and depth < 2:
        hf, inner = helpers[node.func.id]
        kinds = {classify(r, helpers, depth + 1, Ctx(hf, (ctx.consts if ctx else {})))[0] for r in inner}
        return ("helper", "%s -> %s" % (node.func.id, "/".join(sorted(kinds)))) if kinds else ("other", text)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in ("max", "min") and any(isinstance(a, ast.BinOp) for a in ast.walk(node)): return "weights", text
    if isinstance(node, ast.IfExp):
        if _num(node.body) and _num(node.orelse): return "rule", text
        return "weights", text
    if isinstance(node, ast.BinOp) and any(_num(x) for x in (node.left, node.right)): return "weights", text
    if isinstance(node, ast.BinOp): return "weights", text
    return "other", text


def element(value, i, helpers, depth=0, ctx=None):
    """Classes of the element i of a tuple that is unpacked: a tuple of the same length, or the returns of a helper of the same file (a returned tuple, or a call to another helper)."""
    if isinstance(value, (ast.Tuple, ast.List)) and i < len(value.elts) and not any(isinstance(e, ast.Starred) for e in value.elts): return [classify(value.elts[i], helpers, 0, ctx)]
    if isinstance(value, ast.Call) and isinstance(value.func, ast.Name) and value.func.id in helpers and depth < 3:
        out = []; hf, rets = helpers[value.func.id]; hctx = Ctx(hf, ctx.consts if ctx else {})
        for r in rets:
            if isinstance(r, (ast.Tuple, ast.List)): out += element(r, i, helpers, depth + 1, hctx)
            elif isinstance(r, ast.Call): out += element(r, i, helpers, depth + 1, hctx)
            else: out.append(("other", "returned by %s: %s" % (value.func.id, ast.unparse(r)[:60])))
        return out or [("other", ast.unparse(value)[:80])]
    return [("other", "unpacked from " + ast.unparse(value)[:80])]


def is_standard_gen(g):
    return isinstance(g.elt, ast.Call) and is_standard(g.elt)


def _returns(fn):
    return [r.value for r in ast.walk(fn) if isinstance(r, ast.Return) and r.value is not None]


def analyse(path):
    """[(function, line, [(class, text)...])] for the functions of one file that build a `multisigScore` key."""
    tree = ast.parse(open(path, encoding="utf-8").read())
    funcs = [f for f in ast.walk(tree) if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef))]
    helpers = {f.name: (f, _returns(f)) for f in funcs}
    consts = {t.id: st.value for st in tree.body if isinstance(st, ast.Assign) for t in st.targets if isinstance(t, ast.Name)}
    rows = []
    for fn in funcs:
        sites = [(v, k.lineno) for d in ast.walk(fn) if isinstance(d, ast.Dict) for k, v in zip(d.keys, d.values) if isinstance(k, ast.Constant) and k.value == "multisigScore"]
        sites += [(a.value, a.lineno) for a in ast.walk(fn) if isinstance(a, ast.Assign) and any(isinstance(t, ast.Subscript) and isinstance(t.slice, ast.Constant) and t.slice.value == "multisigScore" for t in a.targets)]   # entry["multisigScore"] = ...
        if not sites: continue
        items = []
        for v, line in sites:
            if isinstance(v, ast.Name):
                got = False
                for st in ast.walk(fn):
                    if isinstance(st, ast.Assign) and any(isinstance(t, ast.Name) and t.id == v.id for t in st.targets):
                        items.append((st.lineno,) + classify(st.value, helpers, 0, Ctx(fn, consts))); got = True
                    elif isinstance(st, ast.Assign) and any(isinstance(t, (ast.Tuple, ast.List)) and any(isinstance(e, ast.Name) and e.id == v.id for e in t.elts) for t in st.targets):
                        for t in st.targets:
                            if isinstance(t, (ast.Tuple, ast.List)) and any(isinstance(e, ast.Name) and e.id == v.id for e in t.elts):
                                i = [k for k, e in enumerate(t.elts) if isinstance(e, ast.Name) and e.id == v.id][0]
                                items += [(st.lineno,) + c for c in element(st.value, i, helpers, 0, Ctx(fn, consts))]; got = True
                    elif isinstance(st, ast.For) and any(isinstance(e, ast.Name) and e.id == v.id for e in ast.walk(st.target)):
                        items.append((st.lineno, "other", "loop variable over " + ast.unparse(st.iter)[:60])); got = True
                    elif isinstance(st, ast.AugAssign) and isinstance(st.target, ast.Name) and st.target.id == v.id:
                        items.append((st.lineno, "other", ast.unparse(st))); got = True
                if not got: items.append((line, "other", "%s (a parameter or an unresolved name)" % v.id))
            else: items.append((line,) + classify(v, helpers, 0, Ctx(fn, consts)))
        flat = []
        for it in items:   # a name that several branches assign to different classes is shown as those classes
            if it[1] == "mixed": flat += [(it[0], k, "" if k in ("standard", "fixed") else "branches of the function") for k in it[2].split("/")]
            else: flat.append(it)
        items = flat
        seen, uniq = set(), []
        for it in sorted(items):
            if (it[1], it[2]) not in seen: seen.add((it[1], it[2])); uniq.append(it)
        rows.append((fn.name, min(i[0] for i in uniq), [(c, t) for _, c, t in uniq]))
    return sorted(rows, key=lambda r: r[1])


def build(root=ROOT):
    files = [FILES[0]] + sorted(os.path.relpath(p, root).replace(os.sep, "/") for p in glob.glob(os.path.join(root, "chains", "*", "scorers.py")))
    out = ["# The multisig sub-score, scorer by scorer", "",
           "Generated by `python3 scripts/multisig_shapes.py --write` from the scorers of this repository with the Python parser; `python3 scripts/multisig_shapes.py --check` fails when this page is not what the code says. It describes the shape of the CODE, one row per scorer function that sets a `multisigScore` (in a dict, or by assigning a key of that name): it does not say which scorer serves which target, and it does not run any scorer, so it cannot say which branch a given target takes. To know what a target's score used, read the notes of that target. The general formula is in METHODOLOGY.md (`multisigScore`); see also docs/LIMITS.md, \"The multisig score is not one formula\".", "",
           "Classes: **standard** `min(100, t * 15 + max(0, n - t) * 5)`; **helper** a call to a helper of the same file, classed by what it returns; **weakest** the minimum of several other values; **weights** a formula with other weights or a rule on a list of Safes (the Zcash formula on the concentration of miners is one of them); **rule** a value picked by a condition between constants; **fixed** a constant written in the code; **other** read by hand. A scorer can use several classes (the branches of one function).", ""]
    total = {}
    body = []
    for rel in files:
        rows = analyse(os.path.join(root, rel))
        if not rows: continue
        body += ["## `%s`" % rel, "", "| Function | Line | Classes | Expressions that are not the standard formula |", "|---|---|---|---|"]
        for name, line, items in rows:
            classes = sorted({c for c, _ in items}); [total.__setitem__(c, total.get(c, 0) + 1) for c in classes]
            fixed = sorted({t for c, t in items if c == "fixed" and t}, key=lambda x: float(x)); exprs = [("`%s`" % t.replace("|", "/")[:90]) for c, t in items if c not in ("standard", "fixed") and t]
            if fixed: exprs.insert(0, "fixed: " + ", ".join(fixed))
            body.append("| `%s` | %d | %s | %s |" % (name, line, ", ".join(classes), "; ".join(exprs)))
        body.append("")
    manual = [(rel, name, line, "; ".join(t for c, t in items if c == "other")) for rel in files for name, line, items in analyse(os.path.join(root, rel)) if any(c == "other" for c, _ in items)]
    out += ["Functions by class (a function with several classes is counted in each): " + ", ".join("%s %d" % (c, n) for c, n in sorted(total.items())) + ".", ""]
    body += ["## Left to be read by hand", "", "The parser could not follow the multisig value of these functions to a formula (it is a parameter, a value taken from another scorer, or built in a way the tool does not follow). They are listed so that they are not mistaken for covered: %d function(s)." % len(manual), "",
             "| File | Function | Line | What was found |", "|---|---|---|---|"] + ["| `%s` | `%s` | %d | `%s` |" % (r, n, l, t.replace("|", "/")[:110]) for r, n, l, t in manual] + [""]
    return "\n".join(out + body).rstrip("\n") + "\n"


def main(argv=None):
    a = sys.argv[1:] if argv is None else argv
    text = build()
    if "--write" in a: open(PAGE, "w", encoding="utf-8").write(text); print("wrote", os.path.relpath(PAGE, ROOT)); return 0
    if "--check" in a:
        have = open(PAGE, encoding="utf-8").read() if os.path.exists(PAGE) else None
        if have != text: print("docs/MULTISIG-SHAPES.md is not what the scorers say: run python3 scripts/multisig_shapes.py --write"); return 1
        print("docs/MULTISIG-SHAPES.md matches the scorers"); return 0
    print(text, end=""); return 0


if __name__ == "__main__":
    sys.exit(main())
