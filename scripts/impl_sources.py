#!/usr/bin/env python3
"""Is the code behind each tracked proxy readable? For every implementation the independent reader found (watch/second_opinion.json,
`impl`), asks Sourcify (public, no key) whether a verified source exists for it on that chain: the match (exact_match, match, none),
the contract name, the compiler and the verification date. An upgrade to an unverified implementation is an upgrade nobody can read.
Written to watch/impl_sources.json, keyed <chain>:<target>; one request per implementation, so a few dozen per run.

    python3 scripts/impl_sources.py --so watch/second_opinion.json --out watch/impl_sources.json
"""
import argparse, hashlib, json, os, re, sys, time, urllib.error, urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.reader_audit import stamp_check  # noqa: E402  -- when it was checked, against which deployed code

CHAIN_ID = {"ethereum-l1": 1, "arbitrum": 42161, "base": 8453, "robinhood": 4663, "monad": 143, "hyperliquid": 999, "plasma": 9745}   # chains Sourcify knows; tempo is not listed there


def sourcify(cid, addr):
    try:
        r = urllib.request.urlopen(urllib.request.Request("https://sourcify.dev/server/v2/contract/%d/%s?fields=compilation" % (cid, addr), headers={"User-Agent": "curl/8"}), timeout=20)
        d = json.loads(r.read()); comp = d.get("compilation") or {}
        return {"verified": True, "match": d.get("match"), "name": re.sub(r"[^A-Za-z0-9_ .-]", "", str(comp.get("name") or ""))[:48] or None, "compiler": str(comp.get("compilerVersion") or "")[:24] or None, "verified_at": d.get("verifiedAt")}
    except urllib.error.HTTPError as e:
        if e.code == 404: return {"verified": False, "match": None, "name": None, "compiler": None, "verified_at": None}
        return None   # a transport failure is not an answer
    except Exception: return None  # noqa: BLE001


def osec(program):
    """OtterSec's verified-build registry (public, no key): whether a build reproduced from a repository and commit matches the
    program's deployed binary right now (is_verified), the repository, and when it last matched."""
    try:
        d = json.loads(urllib.request.urlopen(urllib.request.Request("https://verify.osec.io/status/%s" % program, headers={"User-Agent": "curl/8"}), timeout=20).read())
        h = str(d.get("on_chain_hash") or "").lower()   # the sha256 of the deployed binary as OtterSec read it; empty when it has no record of the program
        return {"verified": bool(d.get("is_verified")), "match": "verified build" if d.get("is_verified") else None, "name": None, "compiler": None, "verified_at": d.get("last_verified_at"),
                "on_chain_hash": h if re.fullmatch(r"[0-9a-f]{64}", h) else None,
                "repo_url": (d.get("repo_url") or None), "source": "osec", "note": None if d.get("is_verified") else ("a repository is registered but no build matches the deployed binary" if d.get("repo_url") else "no verified build registered")}
    except Exception: return None  # noqa: BLE001 -- a transport failure is not an answer


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--so", default="watch/second_opinion.json"); ap.add_argument("--out", default="watch/impl_sources.json"); a = ap.parse_args()
    so = json.load(open(a.so)) if os.path.exists(a.so) else {"results": []}
    prev = (json.load(open(a.out)) if os.path.exists(a.out) else {}).get("by_target", {})
    out, cache, code_of = {}, {}, {}; asked = 0
    now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    def deployed_sha256(chain, addr):   # the code at the implementation address when it was checked (None if it could not be read)
        k = chain + ":" + addr.lower()
        if k not in code_of:
            try:
                from second_opinion import MAINNET, rpc_batch
                c = rpc_batch(MAINNET[chain], [("eth_getCode", [addr, "latest"])])[0]
                code_of[k] = hashlib.sha256(bytes.fromhex(c[2:])).hexdigest() if isinstance(c, str) and len(c) > 2 else None
            except Exception: code_of[k] = None  # noqa: BLE001
        return code_of[k]
    for r in so.get("results", []):
        if not r.get("impl") or r.get("oracle_self") or r["chain"] not in CHAIN_ID: continue
        key = r["chain"] + ":" + str(r["target"]).lower(); ck = r["chain"] + ":" + r["impl"].lower()
        if ck not in cache:
            cache[ck] = sourcify(CHAIN_ID[r["chain"]], r["impl"]); asked += 1; time.sleep(0.25)
            if cache[ck] is None and prev.get(key, {}).get("impl", "").lower() == r["impl"].lower(): cache[ck] = dict(prev[key], stale=True)   # Sourcify not answering: keep the previous answer for the same implementation, marked
        if cache[ck] is None: out[key] = stamp_check({"impl": r["impl"], "via": r.get("impl_via"), "verified": None, "note": "Sourcify not answering this run"}, now_iso, None); continue
        out[key] = stamp_check(dict({"impl": r["impl"], "via": r.get("impl_via")}, **{k: v for k, v in cache[ck].items() if k != "impl"}), now_iso, deployed_sha256(r["chain"], r["impl"]), prev.get(key))
    for r in so.get("results", []):   # Solana: the program behind each tracked account, against OtterSec's verified builds (since 2026-10-10)
        if r.get("chain") != "solana" or r.get("oracle_self") or r.get("kind") in ("unreadable", "native"): continue
        program = r.get("via_program") or r["target"]; key = "solana:" + str(r["target"]).lower(); ck = "solana:" + program
        if ck not in cache:
            cache[ck] = osec(program); asked += 1; time.sleep(0.3)
            if cache[ck] is None and prev.get(key, {}).get("impl") == program: cache[ck] = dict(prev[key], stale=True)
        if cache[ck] is None: out[key] = stamp_check({"impl": program, "via": "program", "verified": None, "note": "OtterSec not answering this run"}, now_iso, None); continue
        osec_hash = cache[ck].get("on_chain_hash")   # the binary is not downloaded here: its hash is the one OtterSec reports (30/10/2026), None when it has no record
        out[key] = stamp_check(dict({"impl": program, "via": "program (verified build, OtterSec)"}, **{k: v for k, v in cache[ck].items() if k not in ("impl", "on_chain_hash")}, **({"code_hash_source": "OtterSec on_chain_hash"} if osec_hash else {})), now_iso, osec_hash, prev.get(key))
    chains_skipped = sorted({r["chain"] for r in so.get("results", []) if r.get("impl") and r["chain"] not in CHAIN_ID})
    rec = {"run_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "checked": len(out), "verified": sum(1 for v in out.values() if v.get("verified")), "unverified": sum(1 for v in out.values() if v.get("verified") is False), "not_answered": sum(1 for v in out.values() if v.get("verified") is None),
           "chains_not_on_sourcify": chains_skipped, "by_target": out, "what": "for every implementation behind a tracked proxy (second_opinion.json, impl): whether Sourcify holds a verified source on that chain, with match, name, compiler and date; for every Solana program behind a tracked account: whether OtterSec holds a verified build matching the deployed binary (source osec, repo_url); an upgrade to an unverified implementation is an upgrade nobody can read; written by scripts/impl_sources.py after every run"}
    tmp = a.out + ".tmp"; json.dump(rec, open(tmp, "w"), indent=1); os.replace(tmp, a.out)
    print("implementation sources: %d checked (%d request(s) to Sourcify and OtterSec), %d verified, %d unverified, %d not answered%s" % (rec["checked"], asked, rec["verified"], rec["unverified"], rec["not_answered"], (", chains not on Sourcify: " + ", ".join(chains_skipped)) if chains_skipped else ""))
    for k, v in sorted(out.items()):
        if v.get("verified") is False: print("  UNVERIFIED %s: implementation %s" % (k, v["impl"]))


if __name__ == "__main__":
    main()
