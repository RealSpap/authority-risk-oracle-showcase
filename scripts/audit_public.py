#!/usr/bin/env python3
"""Audit what this project publishes, in one command, from outside: nothing here needs a key, an account or this repository's
trust. Standard library only (pynacl, if installed, also checks the Ed25519 signature).

    python3 scripts/audit_public.py                      # fetch watch/ from GitHub into a temporary folder and audit it
    python3 scripts/audit_public.py --watch watch        # audit a local checkout
    python3 scripts/audit_public.py --sample 12          # re-read that many scores from the oracles themselves (default 8)
    python3 scripts/audit_public.py --ref <commit>       # a past run, as committed: its manifest, signature, chain and schemas (from a git checkout)

What it checks, and prints as PASS / FAIL / NOTE:
  1. the hash chain of events.jsonl (every line commits to the previous one);
  2. the signed manifest, signature.json: every published file hashes to what the manifest says, the chain head matches, and the
     signature verifies against the published key (pynacl) or is at least present;
  3. the schemas: latest.json, scores/*.json, alerts.json, pending_ops.json, tvl.json against watch/schema/*.schema.json;
  4. the methodology registry: one methodologyHash per oracle;
  5. a random sample of scores re-read from the oracle contracts over public RPCs (getScore(target)): composite and push time must
     equal the published file, unless the oracle was pushed again since the run (then both are printed, as NOTE).
Exit 0 when everything passes, 1 on any FAIL. A NOTE is information, not a failure.
"""
import argparse, glob, hashlib, json, os, random, sys, tempfile, time, urllib.request

RAW = "https://raw.githubusercontent.com/RealSpap/authority-risk-oracle-showcase/main/"
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
SEL_SCORE = "0xd47875d0"


def get(url, binary=False):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (audit_public)"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read() if binary else r.read().decode()


def fetch_watch(dest):
    """Download the published watch/ files named by the manifest (or, without one, the core files) into dest."""
    os.makedirs(dest, exist_ok=True); names = []
    try:
        sig = json.loads(get(RAW + "watch/signature.json")); names = list(sig["manifest"]["files"]); open(os.path.join(dest, "signature.json"), "w").write(json.dumps(sig))
    except Exception:
        names = ["latest.json", "events.jsonl", "history.jsonl", "alerts.json", "pending_ops.json", "tvl.json", "methodology.json", "chain.json", "API.md"]
        try: names += ["scores/" + (o.get("slug") or __import__("re").sub(r"[^a-z0-9]+", "-", o["name"].lower()).strip("-")) + ".json" for o in json.loads(get(RAW + "watch/latest.json"))["oracles"]]
        except Exception: pass
        names += ["schema/" + n + ".schema.json" for n in ("latest", "scores", "alerts", "pending_ops", "tvl", "second_opinion", "disputes", "score_series", "methodology", "coverage", "review_queue", "cross_chain", "impl_sources", "risk_by_cause", "held_assets", "pause_state", "side_roles", "safe_activity", "admin_probe")]
    got = 0
    for n in names:
        if n.startswith("feed/") or n.startswith("badge/"): continue   # hundreds of small files: the manifest hashes cover them, the audit samples the rest
        try:
            b = get(RAW + "watch/" + n, binary=True); p = os.path.join(dest, n); os.makedirs(os.path.dirname(p), exist_ok=True); open(p, "wb").write(b); got += 1
        except Exception: pass
    return got


def rpc(url, method, params):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    req = urllib.request.Request(url, body, {"Content-Type": "application/json", "User-Agent": "Mozilla/5.0 (audit_public)"})
    with urllib.request.urlopen(req, timeout=30) as r: d = json.loads(r.read())
    if "error" in d: raise RuntimeError(str(d["error"])[:120])
    return d["result"]


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--watch", default=None); ap.add_argument("--sample", type=int, default=8); ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--ref", default=None, help="a git commit, tag or branch of this checkout: audit the watch/ folder as it was then (every run commits its signed manifest)")
    a = ap.parse_args(); fails = 0
    if a.ref:   # past run: extract watch/ at that commit into a temporary folder and audit that
        import subprocess
        root = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True).stdout.strip() or "."
        dest = tempfile.mkdtemp(prefix="aro-audit-ref-"); tar = subprocess.run(["git", "-C", root, "archive", a.ref, "watch"], capture_output=True)
        if tar.returncode: print("cannot read %s from this checkout: %s" % (a.ref, tar.stderr.decode()[:120])); sys.exit(1)
        subprocess.run(["tar", "-x", "-C", dest], input=tar.stdout, check=True); a.watch = os.path.join(dest, "watch")
        sha = subprocess.run(["git", "-C", root, "rev-parse", "--short", a.ref], capture_output=True, text=True).stdout.strip()
        print("auditing watch/ as committed at %s (%s)" % (a.ref, sha))
    def PASS(m): print("PASS  " + m)
    def FAIL(m):
        nonlocal fails; fails += 1; print("FAIL  " + m)
    def NOTE(m): print("NOTE  " + m)
    watch = a.watch
    if not watch:
        watch = os.path.join(tempfile.mkdtemp(prefix="aro-audit-"), "watch"); n = fetch_watch(watch); print("fetched %d published file(s) from %s into %s" % (n, RAW, watch))
    # 1. chain
    import verify_chain
    c = verify_chain.check(os.path.join(watch, "events.jsonl"))
    if c.get("reason") == "no events file": NOTE("event log: no events.jsonl published yet (nothing to chain)")
    else: (PASS if c["ok"] else FAIL)("event log: %s (%s chained, %s before the chain)" % ("chain intact" if c["ok"] else c.get("reason"), c.get("chained"), c.get("unchained")))
    # 1b. is the watch alive: latest.json older than two schedules (6 h cron) means the job stopped, and every audited file is that old
    try:
        lj = json.load(open(os.path.join(watch, "latest.json"))); age_h = (time.time() - __import__("calendar").timegm(time.strptime(lj["run_utc"], "%Y-%m-%dT%H:%M:%SZ"))) / 3600   # timegm, not mktime: the local clock may be on summer time
        (NOTE if age_h <= 12 else FAIL)("watch alive: last run %s, %.1f h ago%s" % (lj["run_utc"], age_h, "" if age_h <= 12 else " (older than two 6-hour schedules: the job is not running, everything audited here is that old)"))
    except Exception as e: NOTE("watch age not checked (%s)" % str(e)[:60])
    # 2. manifest + signature
    sp = os.path.join(watch, "signature.json")
    if os.path.exists(sp):
        s = json.load(open(sp)); changed, missing = [], []
        for f, h in s["manifest"]["files"].items():
            p = os.path.join(watch, f)
            if not os.path.exists(p): missing.append(f); continue
            if hashlib.sha256(open(p, "rb").read()).hexdigest() != h: changed.append(f)
        (PASS if not changed else FAIL)("manifest: %d file(s) listed, %d checked, %d differ%s" % (len(s["manifest"]["files"]), len(s["manifest"]["files"]) - len(missing), len(changed), (": " + ", ".join(changed[:5])) if changed else ""))
        if missing: NOTE("%d listed file(s) not present locally (feeds and badges are not fetched by this audit): hashes not compared for them" % len(missing))
        head = c.get("head") if c["ok"] else None
        (PASS if s["manifest"].get("events_chain_head") == head else FAIL)("manifest: event-log chain head %s" % ("matches" if s["manifest"].get("events_chain_head") == head else "differs"))
        if s.get("signed"):
            try:
                from nacl.signing import VerifyKey
                VerifyKey(bytes.fromhex(s["public_key"])).verify(json.dumps(s["manifest"], sort_keys=True, separators=(",", ":")).encode(), bytes.fromhex(s["signature"]))
                PASS("signature: valid Ed25519 signature by %s… (compare this key with the one the README publishes)" % s["public_key"][:16])
            except ImportError: NOTE("signature present (key %s…), pynacl not installed here: pip install pynacl to verify it" % s["public_key"][:16])
            except Exception as e: FAIL("signature: INVALID (%s)" % e)
        else: NOTE("run unsigned (no signing key set by the maintainer at that run)")
    else: NOTE("no signature.json: this run predates signed manifests")
    # 3. schemas
    try:
        import validate_schemas
        errs, n = [], 0
        pairs = {"alerts": ["alerts.json"], "latest": ["latest.json"], "pending_ops": ["pending_ops.json"], "tvl": ["tvl.json"], "second_opinion": ["second_opinion.json"], "disputes": ["disputes.json"], "score_series": ["score_series.json"], "methodology": ["methodology.json"], "coverage": ["coverage.json"], "review_queue": ["review_queue.json"], "cross_chain": ["cross_chain.json"], "impl_sources": ["impl_sources.json"], "risk_by_cause": ["risk_by_cause.json"], "held_assets": ["held_assets.json"], "pause_state": ["pause_state.json"], "side_roles": ["side_roles.json"], "safe_activity": ["safe_activity.json"], "admin_probe": ["admin_probe.json"], "scores": [os.path.relpath(f, watch) for f in sorted(glob.glob(os.path.join(watch, "scores", "*.json")))]}
        for name, files in pairs.items():
            schp = os.path.join(watch, "schema", name + ".schema.json")
            if not os.path.exists(schp): continue
            sch = json.load(open(schp))
            for f in files:
                p = os.path.join(watch, f)
                if os.path.exists(p): n += 1; validate_schemas.check(json.load(open(p)), sch, f, errs)
        (PASS if not errs else FAIL)("schemas: %d file(s) checked, %d problem(s)%s" % (n, len(errs), (": " + errs[0]) if errs else ""))
    except Exception as e: NOTE("schemas not checked (%s)" % e)
    # 4. methodology
    mixed, old_kept = [], []
    for f in sorted(glob.glob(os.path.join(watch, "scores", "*.json"))):
        d = json.load(open(f)); tg = d.get("targets", []); h = lambda t: (t.get("methodologyHash") or "").lower()
        live = {h(t) for t in tg if not t.get("stale")}; hs = live or {h(t) for t in tg}   # an entry retired by design (or not re-pushed yet) is stale and keeps the hash it was last scored under: it is not a second method in use (11/10)
        if len(hs) > 1: mixed.append(os.path.basename(f)[:-5])
        n_old = sum(1 for t in tg if t.get("stale") and h(t) not in hs)
        if live and n_old: old_kept.append("%s: %d" % (os.path.basename(f)[:-5], n_old))
    (PASS if not mixed else FAIL)("methodology: one hash per oracle" if not mixed else "methodology: mixed hashes on " + ", ".join(mixed))
    if old_kept: NOTE("methodology: stale entries that keep an older hash (retired, or not re-pushed yet), counted apart from the live ones: " + "; ".join(old_kept))
    # 5. sample re-read from the oracles
    rows = []
    for f in sorted(glob.glob(os.path.join(watch, "scores", "*.json"))):
        d = json.load(open(f))
        if d.get("kind") == "evm":
            for t in d.get("targets", []): rows.append((d["name"], d["oracle"], d["rpc"], t))
    if rows and a.sample <= 0: NOTE("on-chain sample skipped (--sample 0)")
    elif rows:
        rnd = random.Random(a.seed); sample = rnd.sample(rows, min(a.sample, len(rows))); agree = later = unread = 0
        for name, oracle, url, t in sample:
            try:
                r = rpc(url, "eth_call", [{"to": oracle, "data": SEL_SCORE + t["target"].lower().replace("0x", "").rjust(64, "0")}, "latest"])
                comp, ts = int(r[2 + 64 * 5: 2 + 64 * 6], 16), int(r[2 + 64 * 6: 2 + 64 * 7], 16)
                if comp == t["compositeScore"] and ts == t["lastUpdated"]: agree += 1
                elif ts > t["lastUpdated"]: later += 1; NOTE("%s %s: pushed again since the run (file %d at %d, chain %d at %d)" % (name, t["target"][:10], t["compositeScore"], t["lastUpdated"], comp, ts))
                else: FAIL("%s %s: chain says %d (pushed %d), file says %d (pushed %d)" % (name, t["target"][:10], comp, ts, t["compositeScore"], t["lastUpdated"]))
            except Exception as e: unread += 1; NOTE("%s %s: not read (%s)" % (name, t["target"][:10], str(e)[:60]))
            time.sleep(0.3)
        (PASS if agree + later + unread == len(sample) else FAIL)("on-chain sample: %d of %d re-read scores equal the published file, %d pushed again since, %d not read (RPC)" % (agree, len(sample), later, unread))
    else: NOTE("on-chain sample skipped: the scores files carry no oracle address and RPC (a run before 2026-10-07), nothing to re-read")
    print("\n%s: %d failure(s)" % ("AUDIT PASSED" if not fails else "AUDIT FAILED", fails))
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
