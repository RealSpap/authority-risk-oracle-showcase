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
     signature verifies (pynacl) against a key this script pins (PINNED_KEYS, or --pin KEY): a valid signature by any other key FAILS;
  3. the schemas: latest.json, scores/*.json, alerts.json, pending_ops.json, tvl.json against watch/schema/*.schema.json;
  4. the methodology registry: one methodologyHash per oracle;
  5. a random sample of scores re-read from the oracle contracts over public RPCs (getScore(target)): composite and push time must
     equal the published file, unless the oracle was pushed again since the run (then both are printed, as NOTE).
Exit 0 when everything passes, 1 on any FAIL, 3 when the audit could not be completed (a signature that could not be verified, signature.json
that could not be fetched). A NOTE is information, not a failure. A name in the manifest that is not a plain relative path (`..`, an absolute
path, an empty part, a backslash) is a FAIL and nothing is written or read for it (fetch_watch checks every name before it writes anything).
"""
import argparse, glob, hashlib, json, os, random, re, sys, tempfile, time, unicodedata, urllib.error, urllib.parse, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from watch_location import RAW  # noqa: E402  -- the root of the watch-data branch is the published watch/ folder
SEL_SCORE = "0xd47875d0"
PINNED_KEYS = ("11baca3ef6a69de4901c185f6cbbd3f93318fbb74f9961a8d39aead841adf409",)   # the signing key published in README.md and API.md; the MCP package pins the same one. A rotation is a commit that adds the new key here first.


class UnsafeManifest(RuntimeError):
    """The manifest names a path that is not a plain relative path inside the folder."""


NAME = re.compile(r"[A-Za-z0-9._@+=,~-]+(/[A-Za-z0-9._@+=,~-]+)*")   # every name the Watch publishes fits (1042 of 1042 on 22/10/2026)


def safe_name(n):
    """True for a plain relative path of ASCII letters, digits and . _ @ + = , ~ - only, split by single slashes: no `..`, no `.`, no part that ends with a dot (Windows drops it), no empty part (`a//b`), no space, newline, backslash, `?`, `%` or `#` (they would change the URL), no colon or drive, no full-width or other non-ASCII character, no NUL."""
    if not isinstance(n, str) or not NAME.fullmatch(n) or len(n) > 255: return False
    return all(part not in (".", "..") and not part.endswith(".") and not windows_special(part) for part in n.split("/"))


WIN_DEVICE = re.compile(r"(con|prn|aux|nul|com[0-9]|lpt[0-9])(\..*)?", re.I)   # Windows opens these as devices, with or without an extension (con.json)
WIN_SHORT = re.compile(r".*~[0-9]+(\..*)?", re.I)                                        # an 8.3 short name (BASE-S~1.JSO) can stand for another file


def windows_special(part):
    """True for a path part that Windows reads as a device (CON, NUL, COM1, LPT1 ..., also with an extension) or as a short 8.3 name."""
    return bool(WIN_DEVICE.fullmatch(part) or WIN_SHORT.fullmatch(part))


def unsafe_names(names):
    """The names that cannot be used as a path, plus names that collide with another one (the same file on a case-insensitive disk)."""
    names = list(names); bad = [n for n in names if not safe_name(n)]
    seen = {}
    for n in names:
        if safe_name(n): seen.setdefault(unicodedata.normalize("NFKC", n).casefold(), []).append(n)   # the same file once case or Unicode normalization is ignored (macOS)
    return bad + [x for v in seen.values() if len(v) > 1 for x in v]


def inside(base, n):
    """The path of name n under base, or None when it is unsafe or resolves (a symbolic link) outside base."""
    if not safe_name(n): return None
    root = os.path.realpath(base); p = os.path.realpath(os.path.join(base, n))
    return os.path.join(base, n) if p == root or p.startswith(root + os.sep) else None


MAX_NAMES = 5000        # a manifest with more names is refused: one request per name is the cost an outsider could impose
MAX_BYTES = 5_000_000   # a published file larger than this is not downloaded (the largest real one is about 0.2 MB)
MAX_TOTAL = 100_000_000   # the files of one audit together: 5000 names of 5 MB would be 25 GB; the whole real Watch is about 25 MB


class TooLarge(ValueError):
    """A published file is larger than MAX_BYTES."""


def get(url, binary=False):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (audit_public)"})
    with urllib.request.urlopen(req, timeout=30) as r:
        b = r.read(MAX_BYTES + 1)
    if len(b) > MAX_BYTES: raise TooLarge("answer larger than %d bytes" % MAX_BYTES)
    return b if binary else b.decode()


def fetch_watch(dest):
    """Download the published watch/ files named by the signed manifest into dest. Strict: a manifest that cannot be fetched (404 included) or read is
    an error, never a smaller audit; a name that is not a plain relative path stops everything before the first write."""
    sig = None
    for attempt in (1, 2):                                            # a transient failure is retried once; after that the audit stops rather than check less
        try: sig = json.loads(get(RAW + "signature.json")); break
        except urllib.error.HTTPError as e:
            if attempt == 2 or e.code == 404: raise RuntimeError("signature.json could not be fetched (HTTP %d): the audit would silently check less" % e.code)
        except (OSError, ValueError) as e:
            if attempt == 2: raise RuntimeError("signature.json could not be fetched (%s): the audit would silently check less" % type(e).__name__)
    files = (sig or {}).get("manifest", {}).get("files") if isinstance(sig, dict) and isinstance(sig.get("manifest"), dict) else None
    if not isinstance(files, dict) or not files: raise RuntimeError("signature.json has no manifest of files: the audit would silently check less")
    if len(files) > MAX_NAMES: raise UnsafeManifest("the manifest lists %d names, over the limit of %d: nothing was written" % (len(files), MAX_NAMES))
    bad = unsafe_names(files)
    if bad: raise UnsafeManifest("the manifest names %d path(s) that are not plain relative paths inside the folder (%s): nothing was written" % (len(bad), ", ".join(repr(b)[:50] for b in bad[:3])))
    os.makedirs(dest, exist_ok=True); open(os.path.join(dest, "signature.json"), "w").write(json.dumps(sig)); got = 0; failed = []; big = []; total = 0
    for n in files:
        if n.startswith("feed/") or n.startswith("badge/"): continue   # hundreds of small files: the manifest hashes cover them, the audit samples the rest
        p = inside(dest, n)
        if p is None: failed.append(n); continue
        try:
            b = get(RAW + urllib.parse.quote(n, safe="/"), binary=True); total += len(b)
            if total > MAX_TOTAL: raise RuntimeError("the files of the manifest are larger than %d bytes together (too large): the audit stopped" % MAX_TOTAL)
            os.makedirs(os.path.dirname(p), exist_ok=True); open(p, "wb").write(b); got += 1
        except RuntimeError: raise
        except TooLarge: big.append(n)
        except Exception: failed.append(n)   # a file the manifest lists that cannot be read or written is said, never swallowed
    if big: raise RuntimeError("%d file(s) listed in the manifest are too large (over %d bytes each): %s" % (len(big), MAX_BYTES, ", ".join(big[:3])))
    if failed: raise RuntimeError("%d file(s) listed in the manifest could not be fetched or written (%s)" % (len(failed), ", ".join(failed[:3])))
    return got


def rpc(url, method, params):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    req = urllib.request.Request(url, body, {"Content-Type": "application/json", "User-Agent": "Mozilla/5.0 (audit_public)"})
    with urllib.request.urlopen(req, timeout=30) as r: d = json.loads(r.read())
    if "error" in d: raise RuntimeError(str(d["error"])[:120])
    return d["result"]


def extract_ref(ref):
    """(folder, short sha): the state of the Watch at a git ref of this checkout, in a temporary folder. A commit of main from before the move holds it under watch/; a commit of the
    watch-data branch holds it at the root of the tree. After the move, main's watch/ holds only documents and notices: the audit says so rather than auditing them."""
    import subprocess
    root = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True).stdout.strip() or "."
    dest = tempfile.mkdtemp(prefix="aro-audit-ref-"); os.makedirs(os.path.join(dest, "watch"))
    tar = subprocess.run(["git", "-C", root, "archive", ref, "watch"], capture_output=True)   # a commit of main: the state is the watch/ folder
    if tar.returncode == 0 and tar.stdout:
        subprocess.run(["tar", "-x", "-C", dest], input=tar.stdout, check=True)
        if not os.path.exists(os.path.join(dest, "watch", "latest.json")) or "moved" in open(os.path.join(dest, "watch", "latest.json")).read(300):
            print("%s holds only documents and notices in watch/: the state moved to the watch-data branch, audit a commit of that branch" % ref); sys.exit(1)
    else:   # a commit of the watch-data branch (or the branch itself): the state is the root of the tree
        tar = subprocess.run(["git", "-C", root, "archive", ref], capture_output=True)
        if tar.returncode: print("cannot read %s from this checkout: %s" % (ref, tar.stderr.decode()[:120])); sys.exit(1)
        subprocess.run(["tar", "-x", "-C", os.path.join(dest, "watch")], input=tar.stdout, check=True)
    return os.path.join(dest, "watch"), subprocess.run(["git", "-C", root, "rev-parse", "--short", ref], capture_output=True, text=True).stdout.strip()


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--watch", default=None); ap.add_argument("--sample", type=int, default=8); ap.add_argument("--seed", type=int, default=None); ap.add_argument("--pin", action="append", default=[], help="a signing public key (64 hex characters) to trust in addition to the one pinned in this script")
    ap.add_argument("--ref", default=None, help="a git commit, tag or branch of this checkout: audit the state of the Watch as it was then, a commit of the watch-data branch (state at the root of the tree) or, before the move, of main (state in watch/); every run commits its signed manifest")
    a = ap.parse_args(); fails = 0; incomplete = []
    if a.ref:   # past run: extract the state of the Watch at that commit into a temporary folder and audit that
        a.watch, sha = extract_ref(a.ref); print("auditing the Watch state as committed at %s (%s)" % (a.ref, sha))
    def PASS(m): print("PASS  " + m)
    def FAIL(m):
        nonlocal fails; fails += 1; print("FAIL  " + m)
    def NOTE(m): print("NOTE  " + m)
    watch = a.watch
    if not watch:
        watch = os.path.join(tempfile.mkdtemp(prefix="aro-audit-"), "watch")
        try: n = fetch_watch(watch)
        except UnsafeManifest as e: print("FAIL  manifest: %s\n\nAUDIT FAILED: 1 failure(s)" % e); sys.exit(1)
        except RuntimeError as e: print("AUDIT INCOMPLETE: %s. Run it again." % e); sys.exit(3)
        print("fetched %d published file(s) from %s into %s" % (n, RAW, watch))
    if not os.path.exists(os.path.join(watch, "latest.json")) and not glob.glob(os.path.join(watch, "scores", "*.json")):
        FAIL("nothing to audit: no latest.json and no scores file under %s (an empty folder proves nothing)" % watch)   # 11/10 review: an empty folder used to end on AUDIT PASSED
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
    sp = os.path.join(watch, "signature.json"); stale_sig = False
    if os.path.exists(sp):
        s = json.load(open(sp)); changed, missing = [], []
        try:
            lrun = json.load(open(os.path.join(watch, "latest.json")))["run_utc"]
            if isinstance(s.get("run_utc"), str) and s["run_utc"] < lrun: stale_sig = True; FAIL("SIGNATURE STALE: signature.json is from %s, latest.json from %s: the last run could not be signed, and the files below are checked against the signature of an earlier run" % (s["run_utc"], lrun))   # N55bis
        except (OSError, ValueError, KeyError, TypeError): pass
        mf = s.get("manifest", {}).get("files") if isinstance(s.get("manifest"), dict) else None
        if not isinstance(mf, dict): FAIL("manifest: signature.json has no manifest of files"); mf = {}; s = {"manifest": {"files": {}}}
        bad = unsafe_names(mf)
        if len(mf) > MAX_NAMES: FAIL("manifest: %d names, over the limit of %d: not read" % (len(mf), MAX_NAMES)); mf = {}
        if bad: FAIL("manifest: %d name(s) are not plain relative paths inside the folder (%s): not read" % (len(bad), ", ".join(repr(b)[:50] for b in bad[:3])))
        for f, h in mf.items():
            if f in bad: continue
            p = inside(watch, f)
            if p is None: bad.append(f); FAIL("manifest: %r resolves outside the folder: not read" % f[:60]); continue
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
                if str(s["public_key"]).lower() in {k.lower() for k in PINNED_KEYS + tuple(a.pin)}: PASS("signature: valid Ed25519 signature by %s..., a key this audit pins (the key is read from the same file, so the pin is what makes it mean something)" % s["public_key"][:16])
                else: FAIL("signature: valid Ed25519 signature, but by a key this audit does not pin (%s...): it proves the files match what that key signed, not who holds it. Pass --pin KEY if you trust it" % s["public_key"][:16])
            except ImportError: NOTE("signature present (key %s…) but NOT VERIFIED: pynacl is not installed here (pip install pynacl, then run again); this audit is incomplete" % s["public_key"][:16]); incomplete.append("signature not verified")
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
        if unread == len(sample): NOTE("on-chain sample NOT RUN: no read answered, so this check proves nothing (it is not a pass)")
        (NOTE if unread == len(sample) else FAIL if agree + later + unread != len(sample) else NOTE if unread else PASS)("on-chain sample: %d of %d re-read scores equal the published file, %d pushed again since, %d not read (RPC)" % (agree, len(sample), later, unread))
    else: NOTE("on-chain sample skipped: the scores files carry no oracle address and RPC (a run before 2026-10-07), nothing to re-read")
    if incomplete and not fails: print("\nAUDIT INCOMPLETE: 0 failure(s), but %s (exit 3: not a pass)" % "; ".join(incomplete)); sys.exit(3)
    print("\n%s: %d failure(s)" % ("AUDIT PASSED" if not fails else "AUDIT FAILED", fails))
    if stale_sig: sys.exit(4)   # 4 = the signature is of an earlier run than latest.json (a distinct code, N55bis)
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
