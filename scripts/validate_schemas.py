#!/usr/bin/env python3
"""Validate the watch files against the schemas published next to them (watch/schema/*.schema.json), with the standard library
only: type, required, properties, additionalProperties, items, enum, anyOf/oneOf. A file that breaks its contract fails the
run loudly instead of breaking the dashboard quietly. Usage: python3 scripts/validate_schemas.py [--watch watch]"""
import argparse, glob, json, os, sys

TYPES = {"object": dict, "array": list, "string": str, "integer": int, "number": (int, float), "boolean": bool, "null": type(None)}


def check(d, s, path, errs):
    if "anyOf" in s or "oneOf" in s:
        ok = False
        for alt in s.get("anyOf") or s.get("oneOf"):
            n0 = len(errs); check(d, alt, path, errs)
            if len(errs) == n0: ok = True
            else: del errs[n0:]
        if not ok: errs.append(path + ": no alternative fits"); return
    t = s.get("type")
    if t:
        ts = t if isinstance(t, list) else [t]
        if not any(isinstance(d, TYPES[x]) and not (x in ("integer", "number") and isinstance(d, bool)) for x in ts):
            errs.append("%s: %s is not %s" % (path, type(d).__name__, ts)); return
    if "enum" in s and d not in s["enum"]: errs.append("%s: %r not in enum" % (path, d))
    if isinstance(d, dict):
        for r in s.get("required", []):
            if r not in d: errs.append("%s: required %s missing" % (path, r))
        props, ap = s.get("properties", {}), s.get("additionalProperties", True)
        for k, v in d.items():
            if k in props: check(v, props[k], path + "." + k, errs)
            elif ap is False: errs.append("%s: unexpected property %s" % (path, k))
            elif isinstance(ap, dict): check(v, ap, path + "." + k, errs)
    if isinstance(d, list) and "items" in s:
        for i, x in enumerate(d): check(x, s["items"], "%s[%d]" % (path, i), errs)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--watch", default="watch"); a = ap.parse_args()
    pairs = {"alerts": ["alerts.json"], "latest": ["latest.json"], "pending_ops": ["pending_ops.json"], "tvl": ["tvl.json"],
             "second_opinion": ["second_opinion.json"], "disputes": ["disputes.json"], "score_series": ["score_series.json"], "methodology": ["methodology.json"], "coverage": ["coverage.json"], "review_queue": ["review_queue.json"], "cross_chain": ["cross_chain.json"], "impl_sources": ["impl_sources.json"], "risk_by_cause": ["risk_by_cause.json"], "held_assets": ["held_assets.json"], "pause_state": ["pause_state.json"], "side_roles": ["side_roles.json"], "safe_activity": ["safe_activity.json"], "admin_probe": ["admin_probe.json"],   # since 2026-10-10
             "scores": [os.path.relpath(f, a.watch) for f in sorted(glob.glob(os.path.join(a.watch, "scores", "*.json")))]}
    errs, n, notes = [], 0, {}
    for name, files in pairs.items():
        sp = os.path.join(a.watch, "schema", name + ".schema.json")
        if not os.path.exists(sp): continue
        schema = json.load(open(sp))
        for f in files:
            p = os.path.join(a.watch, f)
            if not os.path.exists(p): continue   # a file the job did not write this run is the job's own warning, not a schema error
            n += 1
            try:
                data = json.load(open(p)); check(data, schema, f, errs)
                # a field a record carries and the schema does not declare is not an error (a consumer ignores it) but it is an undocumented part of the interface: 36 of the 56 fields of
                # second_opinion.json results were in that state on 2026-10-10. Said in the log, never a failure.
                for k, sub in (schema.get("properties") or {}).items():
                    if isinstance(sub, dict) and sub.get("type") == "array" and isinstance(data, dict) and isinstance(data.get(k), list) and isinstance((sub.get("items") or {}).get("properties"), dict):
                        und = sorted({x for rec in data[k] if isinstance(rec, dict) for x in rec} - set(sub["items"]["properties"]))
                        if und: notes.setdefault((name, k, tuple(und[:12]), len(und)), []).append(f)
            except ValueError as e: errs.append("%s: not JSON (%s)" % (f, e))
    for e in errs[:40]: print("  " + e)
    for (name, k, und, total), fs in list(notes.items())[:20]: print("  note: %s %s: %d field(s) not declared in the schema: %s%s" % (name, k, total, ", ".join(und), (" (%d files)" % len(fs)) if len(fs) > 1 else ""))
    print("schemas: %d file(s) checked, %d problem(s)" % (n, len(errs)))
    sys.exit(1 if errs else 0)


if __name__ == "__main__":
    main()
