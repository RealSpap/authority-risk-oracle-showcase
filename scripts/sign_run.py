#!/usr/bin/env python3
"""Sign what the watch publishes, so that the files served from GitHub can be checked against a key GitHub does not hold.

watch/signature.json = a manifest (sha256 of every published watch file, the head of the hash-chained event log, the hashes of the code that produced
the run) and its Ed25519 signature. The run time (`run_utc`) is written NEXT TO the manifest, not inside it: the signature does not cover it, so a
reader who needs the age of a reading uses the signed per-file readAt, not run_utc (a known limit, written down on 22/10/2026). The seed comes from the WATCH_SIGNING_KEY secret (64 hex characters), set by the maintainer; without
it the manifest is still written, with "signed": false, and the dashboard says so. What it proves: a file changed or added by a
commit made outside the Watch workflow (a push by hand, a compromised token) carries no valid signature. What it does not prove: the
workflow runs with the secret, so a change to the workflow itself could sign anything; that change is visible in the git history of
.github/workflows/watch.yml, which is why the workflow file is part of the review, not of the manifest.

    python3 scripts/sign_run.py --watch watch                 # write watch/signature.json (signed if WATCH_SIGNING_KEY is set)
    python3 scripts/sign_run.py --watch watch --verify        # recompute every hash and check the signature; exit 1 on any mismatch or on a published file the manifest does not list
    python3 scripts/sign_run.py --new-key                     # print a fresh seed and its public key, for the maintainer only

Published files are every *.json, *.jsonl, *.xml, *.md, *.ics, *.csv under watch/ (recursively, feed/ and badge/ included), except
this manifest, the job logs (*.txt, *.log), alarm.md, any who_controls.json, and the two summaries written after the signature from signed
sources (status.json, badge/integrity.json); catalog.json and metrics.prom are derived the same way and its extension is not one the manifest lists. The manifest also records the sha256 of the code that
produced the run (scripts/*.py, rules.json, .github/workflows/watch.yml) and the commit it ran from, so a published run names its
exact producer. The signature covers the canonical JSON of the manifest.
"""
import argparse, glob, hashlib, json, os, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # python3 -I does not put the script folder on the path
import audit_public   # the one rule for a published name and the caps: what the audit refuses is not signed

SKIP = {"signature.json", "alarm.md", "alerts_high.md", "alarm_state.json", "methodology.md", "who_controls.json", "status.json", "integrity.json", "catalog.json"}   # status.json and badge/integrity.json are written after the signature, from signed sources: summaries, not evidence
EXT = (".json", ".jsonl", ".xml", ".md", ".ics", ".csv")


def through_link(watch, rel):
    """True when a folder on the way to rel (below watch) is a symbolic link: its content is not inside the folder, so it does not enter the manifest."""
    parts = rel.split(os.sep)[:-1]
    return any(os.path.islink(os.path.join(watch, *parts[:i + 1])) for i in range(len(parts)))


class Unsignable(RuntimeError):
    """A published file the audit would refuse: the run stops here, before anything is signed or published."""


def walk(watch):
    """Every path below watch, without following a symbolic link to a folder (two links that point at each other would never end) and without hidden names (as the earlier glob did)."""
    for d, dirs, names in os.walk(watch, followlinks=False):
        dirs[:] = sorted(x for x in dirs if not x.startswith("."))
        for n in sorted(names):
            if not n.startswith("."): yield os.path.join(d, n)


def manifest(watch):
    files = {}
    for path in walk(watch):
        rel = os.path.relpath(path, watch)
        if not os.path.isfile(path) or os.path.islink(path) or through_link(watch, rel) or os.path.basename(path) in SKIP or not path.endswith(EXT) or "/og/" in path.replace(os.sep, "/") + "/" or "private" in rel.split(os.sep)[:-1]: continue
        if os.path.getsize(path) > audit_public.MAX_BYTES: raise Unsignable("%s is larger than %d bytes: the audit would refuse to download it" % (rel, audit_public.MAX_BYTES))
        files[rel] = hashlib.sha256(open(path, "rb").read()).hexdigest()
    bad = audit_public.unsafe_names(k.replace(os.sep, "/") for k in files)
    if bad: raise Unsignable("%d published name(s) the audit would refuse (not plain relative names, or the same file once case is ignored): %s" % (len(bad), ", ".join(repr(b)[:50] for b in bad[:3])))
    if len(files) > audit_public.MAX_NAMES: raise Unsignable("%d published files, over the limit of %d that the audit reads" % (len(files), audit_public.MAX_NAMES))
    if sum(os.path.getsize(os.path.join(watch, k)) for k in files) > audit_public.MAX_TOTAL: raise Unsignable("the published files are larger than %d bytes together: the audit would stop" % audit_public.MAX_TOTAL)
    ev = os.path.join(watch, "events.jsonl"); head = None
    if os.path.exists(ev):
        lines = [l.rstrip("\n") for l in open(ev) if l.strip()]
        if lines: head = hashlib.sha256(lines[-1].encode()).hexdigest()
    # provenance: the code that produced the run (scripts, rules, the workflow itself) and the commit it ran from
    root = os.path.dirname(os.path.abspath(watch)); code = {}
    for rel in sorted(glob.glob(os.path.join(root, "scripts", "*.py"))) + [os.path.join(root, "rules.json"), os.path.join(root, ".github", "workflows", "watch.yml")]:
        if os.path.isfile(rel): code[os.path.relpath(rel, root)] = hashlib.sha256(open(rel, "rb").read()).hexdigest()
    return {"files": files, "events_chain_head": head, "count": len(files), "code": code, "commit": os.environ.get("GITHUB_SHA") or None}


def signable(watch):
    """The manifest, or a clean stop: a published file the audit would refuse is a failure here, before anything is signed, not an audit that fails for everyone later."""
    try: return manifest(watch)
    except Unsignable as e: print("REFUSED TO SIGN: %s" % e); sys.exit(1)


def canonical(m):
    return json.dumps(m, sort_keys=True, separators=(",", ":")).encode()


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--watch", default="watch"); ap.add_argument("--verify", action="store_true"); ap.add_argument("--new-key", action="store_true")
    a = ap.parse_args()
    if a.new_key:
        from nacl.signing import SigningKey
        k = SigningKey.generate()
        print("WATCH_SIGNING_KEY (the secret, repository settings, never in a file):", k.encode().hex())
        print("public key (publish it in README.md and API.md):", k.verify_key.encode().hex()); return
    out = os.path.join(a.watch, "signature.json")
    if a.verify:
        if not os.path.exists(out): print("no signature.json"); sys.exit(1)
        s = json.load(open(out)); m = signable(a.watch); bad = []
        for f, h in s["manifest"]["files"].items():
            if m["files"].get(f) != h: bad.append(f)
        extra = [f for f in m["files"] if f not in s["manifest"]["files"]]
        bad += [f + " (added after signing: the signature does not cover it)" for f in extra]   # a file nobody signed is a change outside the Watch, not a detail (22/10/2026)
        if s["manifest"].get("events_chain_head") != m["events_chain_head"]: bad.append("events.jsonl (chain head)")
        for f, h in (s["manifest"].get("code") or {}).items():
            if m["code"].get(f) != h: bad.append(f + " (code that produced the run differs from this checkout)")
        if s.get("signed"):
            from nacl.signing import VerifyKey
            try: VerifyKey(bytes.fromhex(s["public_key"])).verify(canonical(s["manifest"]), bytes.fromhex(s["signature"])); sig = "valid"
            except Exception as e: sig = "INVALID (%s)" % e; bad.append("signature")
        else: sig = "none (unsigned run)"
        print("manifest: %d file(s), %d changed since signing%s; signature %s" % (len(s["manifest"]["files"]), len(bad), (", %d file(s) not covered: %s" % (len(extra), ", ".join(extra[:5]))) if extra else "", sig))
        for b in bad: print("  CHANGED  " + b)
        sys.exit(1 if bad else 0)
    m = signable(a.watch); seed = os.environ.get("WATCH_SIGNING_KEY", "").strip()
    rec = {"run_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "manifest": m, "signed": False,
           "what": "sha256 of every published watch file and the head of the event-log chain; Ed25519 over the canonical JSON of `manifest` (sort_keys, no spaces). Verify: python3 scripts/sign_run.py --watch watch --verify"}
    if seed:
        from nacl.signing import SigningKey
        k = SigningKey(bytes.fromhex(seed)); rec["signed"] = True
        rec["public_key"] = k.verify_key.encode().hex(); rec["signature"] = k.sign(canonical(m)).signature.hex()
    else:
        rec["note"] = "no WATCH_SIGNING_KEY secret: manifest written, not signed"
    tmp = out + ".tmp"; json.dump(rec, open(tmp, "w"), indent=1); os.replace(tmp, out)
    print("signature.json: %d file(s) in the manifest, %s" % (m["count"], ("signed by " + rec["public_key"][:16] + "…") if rec["signed"] else "unsigned (no key set)"))


if __name__ == "__main__":
    main()
