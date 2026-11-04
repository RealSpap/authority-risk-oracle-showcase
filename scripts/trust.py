#!/usr/bin/env python3
"""watch/trust.json: for every tracked target, how far what the watch publishes about it can be relied on (read-only, from the files of the run, no RPC).

A trust status is not a score and is never mixed with one: VERIFIED, PARTIAL, STALE, DISPUTED, UNVERIFIED or UNAVAILABLE, with the machine-readable reasons
and one state per dimension (reading, coverage, method, signature, journal, notification, financial_exposure, surveillance). The rule is written in
scripts/lib/trust_rules.py and in the file itself (`rule`). Written before the run is signed, so the manifest covers it.

    python3 scripts/trust.py --watch watch --data data --out watch/trust.json

An input file that cannot be read puts the dimension it feeds in "unverified" (never "ok"). The output is checked against watch/schema/trust.schema.json
before it is written. Fail closed: if the computation raises, or the file would break its own schema, the file written has every target UNAVAILABLE with the
reason `trust_not_computed` and `error` set (exit 1): the previous trust.json is never left in place to say VERIFIED for a run it knows nothing about.
"""
import argparse, glob, hashlib, json, os, sys, time

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
try:
    from evaluate_rules import LABEL, WATCH_SLUGS, lower_keys  # noqa: E402
    from lib import trust_rules as tr  # noqa: E402
    import validate_schemas  # noqa: E402
    IMPORT_ERROR = None
except Exception as _e:  # noqa: BLE001 -- fail closed even when this script cannot load its own helpers: main() then writes the minimal document below
    IMPORT_ERROR = "%s: %s" % (type(_e).__name__, str(_e)[:160])


def load(p):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def gather(watch, data):
    """The inputs of the rule: every file of the run it reads, parsed, or None when missing or unreadable."""
    inputs = {n: load(os.path.join(watch, n + ".json")) for n in ("latest", "second_opinion", "pause_state", "safe_activity", "side_roles", "held_assets", "tvl", "alerts",
                                                                   "methodology", "disputes", "signature", "chain", "coverage")}
    inputs["scores"] = {os.path.basename(f)[:-5]: load(f) for f in sorted(glob.glob(os.path.join(watch, "scores", "*.json")))}
    inputs["tvl_scope"] = lower_keys((load(os.path.join(data, "tvl_scope.json")) or {}).get("targets") or {})
    inputs["watch_slugs"] = WATCH_SLUGS
    return inputs


def pinned_keys():
    try:
        import audit_public
        return tuple(audit_public.PINNED_KEYS)
    except Exception:  # noqa: BLE001 -- no pin list: the key is then reported "unknown", never "pinned"
        return ()


def fixed_targets(data):
    pins = load(os.path.join(data, "scorer_pins.json")) or {}
    return {tr.norm_addr(a) for p in pins.get("pins", []) for a in p.get("targets", [])}


def build(watch, data, now=None, key_present=None):
    now = int(time.time()) if now is None else now
    key_present = (bool(os.environ.get("WATCH_SIGNING_KEY")) or os.environ.get("HAS_SIGNING_KEY") == "true") if key_present is None else key_present   # the workflow passes only whether a key exists
    inputs = gather(watch, data)
    inputs["pinned_keys"] = pinned_keys()
    inputs["chain_labels"] = {v: k for k, v in LABEL.items()}
    inputs["notify_min_severity"] = ((load(os.path.join(os.path.dirname(os.path.abspath(data)), "rules.json")) or {}).get("notify") or {}).get("min_severity")
    records = tr.derive_all(inputs, now, key_present, fixed_targets(data))
    counts, dims = tr.summary(records)
    pk = str((inputs.get("signature") or {}).get("public_key", "")).lower()
    run = {"signature": "expected_signed" if (inputs.get("signature") or {}).get("signed") and key_present else ("unsigned" if inputs.get("signature") else "unread"),   # a promise about the signature made after this file, not a verification
           "signature_key": "unknown" if not (pk and inputs["pinned_keys"]) else ("pinned" if pk in {k.lower() for k in inputs["pinned_keys"]} else "not_pinned"),
           "journal": "ok" if (inputs.get("chain") or {}).get("ok") is True else ("broken" if inputs.get("chain") else "unread"),
           "watch_run_utc": (inputs.get("latest") or {}).get("run_utc"), "inputs_unread": sorted(c.split(":", 1)[1] for c in tr.run_reasons(inputs, now, key_present) if c.startswith("input_missing:"))}
    return {"schemaVersion": 1, "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)), "rule_version": tr.RULE_VERSION, "rule": tr.__doc__.split("THE RULE")[1].split('"""')[0].strip(),
            "rule_sha256": hashlib.sha256(open(tr.__file__.replace(".pyc", ".py"), "rb").read()).hexdigest(), "error": None,
            "targets": len(records), "counts": counts, "dimension_counts": dims, "run": run, "by_target": records,
            "what": "A trust status per tracked target, distinct from its score: how much of what the watch publishes about it was checked, how old it is, whether anything contradicts it and whether the record that carries it is intact. Keyed <chain>:<address>. Reasons are machine-readable (`code`, `dimension`, `effect`); `effect` is decides, degrades or info (info never moves the status). Read it before relying on a score. It is rewritten only when the Watch runs: compare generated_utc with the present time, a file older than about 8 hours says nothing about now."}


def unavailable(watch, why, now=None):
    """The document written when the computation fails: every target UNAVAILABLE with the reason `trust_not_computed`, so that the previous file does not stay in
    place saying VERIFIED for a run it knows nothing about."""
    now = int(time.time()) if now is None else now
    keys = []
    for f in sorted(glob.glob(os.path.join(watch, "scores", "*.json"))):
        slug, doc = os.path.basename(f)[:-5], load(f)
        key = WATCH_SLUGS.get(slug) or ("solana" if (doc or {}).get("kind") == "solana" else None)
        keys += [key + ":" + tr.norm_addr(t.get("target")) for t in ((doc or {}).get("targets") or []) if key and isinstance(t, dict)]
    records = {k: tr._record({"trust_not_computed": why[:160]}) for k in keys}
    counts, dims = tr.summary(records)
    return {"schemaVersion": 1, "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)), "rule_version": tr.RULE_VERSION, "rule": tr.__doc__.split("THE RULE")[1].split('"""')[0].strip(),
            "rule_sha256": hashlib.sha256(open(tr.__file__.replace(".pyc", ".py"), "rb").read()).hexdigest(), "error": why[:300], "targets": len(records), "counts": counts, "dimension_counts": dims,
            "run": {"signature": "unread", "signature_key": "unknown", "journal": "unread", "watch_run_utc": None, "inputs_unread": []}, "by_target": records,
            "what": "The trust computation FAILED this run (see `error`): every target is UNAVAILABLE. This is not a statement about the targets."}


def minimal_failure_doc(why, now=None):
    """The document written when even the helpers could not be imported: no target can be listed, every count is zero and `error` says why. Standard library only."""
    now = int(time.time()) if now is None else now
    dims = ("reading", "coverage", "method", "signature", "journal", "notification", "financial_exposure", "surveillance")
    states = ("ok", "not_applicable", "partial", "unverified", "stale", "disputed", "unavailable")
    return {"schemaVersion": 1, "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)), "rule_version": "1", "rule": "not computed", "rule_sha256": "", "error": why[:300], "targets": 0,
            "counts": {s: 0 for s in ("VERIFIED", "PARTIAL", "STALE", "DISPUTED", "UNVERIFIED", "UNAVAILABLE")}, "dimension_counts": {d: {s: 0 for s in states} for d in dims},
            "run": {"signature": "unread", "signature_key": "unknown", "journal": "unread", "watch_run_utc": None, "inputs_unread": []}, "by_target": {},
            "what": "The trust computation could not run this run (see `error`): this file lists no target and says nothing about any of them. A target absent from by_target has NO trust status."}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0]); ap.add_argument("--watch", default="watch"); ap.add_argument("--data", default="data"); ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    out_path = a.out or os.path.join(a.watch, "trust.json")
    if IMPORT_ERROR:
        tmp = out_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f: json.dump(minimal_failure_doc(IMPORT_ERROR), f, indent=1)
        os.replace(tmp, out_path)
        print("trust.json NOT computed (import failed), a document with no target and the error written: " + IMPORT_ERROR); return 1
    schema = load(os.path.join(a.watch, "schema", "trust.schema.json")) or load(os.path.join(HERE, "..", "watch", "schema", "trust.schema.json"))
    failure = None
    try:
        doc = build(a.watch, a.data)
        errs = []
        if schema: validate_schemas.check(doc, schema, "trust.json", errs)
        else: errs.append("trust.schema.json is missing")
        if errs: failure = "trust.json breaks its own schema: " + "; ".join(errs[:3])
    except Exception as e:  # noqa: BLE001 -- fail closed: the failure is published, not hidden behind the previous file
        failure = "%s: %s" % (type(e).__name__, str(e)[:160])
    if failure:
        doc = unavailable(a.watch, failure)   # fail closed: an old trust.json must not keep saying VERIFIED for a run it knows nothing about
    tmp = out_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f: json.dump(doc, f, indent=1)
    os.replace(tmp, out_path)
    if failure:
        print("trust.json NOT computed, every target written UNAVAILABLE: " + failure); return 1
    print("trust: %d target(s), %s" % (doc["targets"], ", ".join("%d %s" % (v, k) for k, v in doc["counts"].items() if v)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
