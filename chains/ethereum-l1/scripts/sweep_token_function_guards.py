#!/usr/bin/env python3
"""Read-only: WHO MAY CALL the freeze, seize, pause and upgrade functions of the tokens a lender holds, read from the verified source rather than from the function names alone.
    python3 chains/ethereum-l1/scripts/sweep_token_function_guards.py --from-dump asset_auth.json [--token 1:0x...] [--dump rows.json]
sweep_asset_authority.py flags a token as freezable, seizable, pausable or upgradeable from the NAMES of its functions; that says the capability exists, not who may use it (a
function named `pause` guarded by `onlyOwner` and one guarded by nothing look the same). This fetches the verified Solidity source (Blockscout v2 API, the implementation
behind a proxy), finds each such function definition and reads its header modifiers (`onlyOwner`, `onlyRole(PAUSER_ROLE)`, `onlyBlacklister`, ...), and, when there is none, looks
for an inline check in the first lines of the body (`require(msg.sender == ...)`, `_checkRole`, `_authorizeUpgrade` for UUPS). Each function is classed:
guarded by a modifier, guarded inline, or NO GUARD FOUND (which means this reading found none, not that there is none: the guard may be in a parent function or an internal call).
With --role-holders (a sweep_token_role_holders.py dump) and --from-dump it also joins each guard to the accounts that satisfy it (getters `blacklister()`, `pauser()`, `owner()` from the asset dump, roles from the role dump) and sizes what ONE account without code can trigger alone. Source that is not Solidity, not verified, or has no such function is reported as such.
A control runs first: USDC's `blacklist` must read `onlyBlacklister` and `pause` must read `onlyPauser`, or the run stops. Nothing is sent, no key."""
import argparse, collections, json, re, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor
ap = argparse.ArgumentParser(); ap.add_argument("--from-dump", default=None); ap.add_argument("--token", action="append", default=[]); ap.add_argument("--role-holders", default=None); ap.add_argument("--dump", default=None); ARGS = ap.parse_args()
BLOCKSCOUT = {1: "eth.blockscout.com", 8453: "base.blockscout.com", 42161: "arbitrum.blockscout.com", 10: "optimism.blockscout.com", 137: "polygon.blockscout.com"}
FAM = {"freeze": re.compile(r"^(blacklist|unblacklist|addblacklist|removeblacklist|addtoblacklist|freeze|unfreeze|freezeaccount|banaddress|blockaccount|block|unblock|setblocklisted|blocklist|denylist|addtodenylist|updateblacklister)$", re.I),
       "seize": re.compile(r"^(wipe|wipefrozenaddress|destroyblackfunds|seize|clawback|forcetransfer|forcedtransfer|confiscate|forceburn)$", re.I),
       "pause": re.compile(r"^(pause|unpause|setpaused|updatepauser)$", re.I), "upgrade": re.compile(r"^(upgradeto|upgradetoandcall|_authorizeupgrade|changeadmin|upgrade|setimplementation)$", re.I)}
KEYWORDS = {"external", "public", "internal", "private", "view", "pure", "payable", "virtual", "override", "returns", "nonpayable", "returns"}
def curl(url):
    for a in range(5):
        try:
            out = subprocess.run(["curl", "-s", "-m", "60", "-A", "Mozilla/5.0", url], capture_output=True, text=True).stdout
            j = json.loads(out)
            if "Too many" in str(j.get("message", "")): time.sleep(2.0 * (a + 1)); continue
            return j
        except Exception: time.sleep(1.5 * (a + 1))
    return None
def sources(ch, a):
    """(list of source texts, language, name, note). Follows a proxy to its implementation."""
    d = curl(f"https://{BLOCKSCOUT[ch]}/api/v2/smart-contracts/{a}")
    if d is None: return [], None, None, "explorer did not answer"
    if not d.get("is_verified") and not d.get("source_code"): return [], None, d.get("name"), "not verified"
    texts, name = [], d.get("name")
    def take(x): return [x.get("source_code") or ""] + [s.get("source_code") or "" for s in (x.get("additional_sources") or [])]
    texts += take(d)
    for im in (d.get("implementations") or [])[:1]:
        ia = im.get("address") or im.get("address_hash"); di = curl(f"https://{BLOCKSCOUT[ch]}/api/v2/smart-contracts/{ia}") if ia else None
        if di is None: return texts, d.get("language"), name, "implementation source not read"
        texts += take(di); name = f"{name} -> {di.get('name')}"
    return [t for t in texts if t], d.get("language"), name, None
DEF = re.compile(r"\bfunction\s+(\w+)\s*\(([^)]*)\)([^{;]*)([{;])", re.S)
def guards(text):
    out = {}
    for m in DEF.finditer(text):
        fn, hdr, end = m.group(1), m.group(3), m.group(4)
        fam = next((f for f, rx in FAM.items() if rx.match(fn)), None)
        if not fam or re.search(r"\b(view|pure)\b", hdr) or (end == ";" and "external" not in hdr and "public" not in hdr): continue
        h = re.sub(r"returns\s*\([^)]*\)", " ", hdr, flags=re.S); h = re.sub(r"override\s*\([^)]*\)", " ", h)
        mods = [(x.group(1) + (re.sub(r"\s+", "", x.group(2)) if x.group(2) else "")) for x in re.finditer(r"(\w+)(\s*\([^)]*\))?", h) if x.group(1) not in KEYWORDS]
        mods = [x for x in mods if not x.startswith(("whenNotPaused", "whenPaused", "nonReentrant", "notBlacklisted", "onlyProxy", "initializer", "reinitializer", "virtual"))]
        inline = None
        if not mods and end == "{":
            body = text[m.end(): m.end() + 500]
            im = re.search(r"(require\s*\([^;]*msg\.sender[^;]*;|_checkRole\s*\([^;]*;|_checkOwner\s*\(\s*\)\s*;|_authorizeUpgrade[^;]*;|if\s*\([^)]*msg\.sender[^)]*\)\s*(revert|\{))", body)
            inline = re.sub(r"\s+", " ", im.group(1))[:90] if im else None
        out.setdefault(fn, []).append(dict(fam=fam, mods=mods, inline=inline, abstract=(end == ";")))
    return out
def analyse(k):
    ch, a = k; texts, lang, name, note = sources(ch, a)
    r = dict(chain=ch, token=a, name=name, language=lang, note=note, funcs={})
    if note and not texts: return r
    if lang and lang.lower() != "solidity": r["note"] = f"language {lang}, not read"; return r
    for t in texts:
        for fn, lst in guards(t).items():
            for g in lst:
                if not g["abstract"] or fn not in r["funcs"]: r["funcs"].setdefault(fn, []).append(g)
    return r
def klass(g): return "modifier" if g["mods"] else ("inline" if g["inline"] else ("declared only" if g["abstract"] else "NO GUARD FOUND"))
RANK = {"modifier": 3, "inline": 2, "declared only": 1, "NO GUARD FOUND": 0}
def who(m):   # the kind of caller a modifier names, by its text only
    m = m.split("(")[0] if not m.startswith("onlyRole") else m
    if m == "onlyOwner": return "owner"
    if m.startswith("onlyRole") or m.startswith("onlyRoles"): return "role"
    if m in ("ifAdmin", "onlyAdmin", "proxyAdmin"): return "proxy admin"
    if m.startswith("only"): return "dedicated account (" + m + ")"
    return "other (" + m + ")"
# ---- control
ctl = analyse((1, "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"))
cbl, cp = [g for g in ctl["funcs"].get("blacklist", []) if g["mods"]], [g for g in ctl["funcs"].get("pause", []) if g["mods"]]
if not (any("onlyBlacklister" in g["mods"] for g in cbl) and any("onlyPauser" in g["mods"] for g in cp)):
    sys.exit(f"CONTROL FAILED: USDC blacklist guards {[g['mods'] for g in ctl['funcs'].get('blacklist', [])]}, pause guards {[g['mods'] for g in ctl['funcs'].get('pause', [])]}, note {ctl['note']}; the reader is not trustworthy")
print("control ok: USDC blacklist is onlyBlacklister, pause is onlyPauser")
toks, expo = [], {}
for t in ARGS.token: c, a = t.split(":"); toks.append((int(c), a.lower()))
if ARGS.from_dump:
    for x in json.load(open(ARGS.from_dump)):
        if x["chain"] in BLOCKSCOUT and any(x["fam"].get(f) for f in ("freeze", "seize", "pause", "upgrade")): toks.append((x["chain"], x["token"].lower())); expo[(x["chain"], x["token"].lower())] = (x["symbol"], (x["deposits"] + x["collateral"]) / 1e9)
toks = sorted(set(toks)); print(f"{len(toks)} tokens")
with ThreadPoolExecutor(4) as ex: rows = list(ex.map(analyse, toks))
unread = [r for r in rows if r["note"] and not r["funcs"]]
print(f"read {len(rows) - len(unread)}, not read {len(unread)}: {collections.Counter(r['note'] for r in unread)}")
tally = collections.Counter(); byfam = collections.defaultdict(collections.Counter)
for r in sorted(rows, key=lambda r: -expo.get((r["chain"], r["token"].lower()), (0, 0))[1]):
    e = expo.get((r["chain"], r["token"].lower())); print(f"\n== {e[0] if e else '?'} chain {r['chain']} {r['token']} {r['name']}" + (f"  exposure ${e[1]:.2f}B" if e else "") + (f"  [{r['note']}]" if r["note"] else ""))
    for fn, lst in sorted(r["funcs"].items(), key=lambda kv: (kv[1][0]["fam"], kv[0])):
        cs = sorted({klass(g) + (": " + " ".join(g["mods"]) if g["mods"] else (": " + g["inline"] if g["inline"] else "")) for g in lst})
        print(f"   {lst[0]['fam']:8s} {fn:24s} " + " | ".join(cs))
        for g in lst: byfam[lst[0]["fam"]][klass(g)] += 1
print("\nfunctions by family and guard class:", {f: dict(c) for f, c in byfam.items()})
print("\nBest guard found per token and family, weighted by exposure (deposits + collateral in the dump); families a token has at all:")
for fam in ("freeze", "seize", "pause", "upgrade"):
    w = collections.defaultdict(float); n = collections.Counter(); wc = collections.defaultdict(lambda: collections.defaultdict(float))
    for r in rows:
        gs = [g for lst in r["funcs"].values() for g in lst if g["fam"] == fam]
        if not gs: continue
        best = max((klass(g) for g in gs), key=lambda c: RANK[c]); e = expo.get((r["chain"], r["token"].lower()), (0, 0))[1]
        w[best] += e; n[best] += 1
        if best == "modifier":
            for wm in {who(m) for g in gs if g["mods"] for m in g["mods"]}: wc[best][wm] += e
    tot = sum(w.values())
    print(f"  {fam:8s} tokens {sum(n.values()):3d} exposure ${tot:5.2f}B | " + ", ".join(f"{k} {n[k]} tokens ${v:.2f}B" for k, v in sorted(w.items(), key=lambda kv: -RANK[kv[0]])))
    print(f"           who the modifiers name (a token can have several; exposure counted once per kind): " + ", ".join(f"{k} ${v:.2f}B" for k, v in sorted(wc['modifier'].items(), key=lambda kv: -kv[1])))

if ARGS.role_holders and ARGS.from_dump:
    ad = {(x["chain"], x["token"].lower()): x for x in json.load(open(ARGS.from_dump))}
    rh = {(r["chain"], r["token"].lower()): r for r in json.load(open(ARGS.role_holders)) if r["events_complete"]}
    TOT = sum(x["deposits"] + x["collateral"] for x in ad.values()) / 1e9; GET = {"onlyBlacklister": "blacklister", "onlyPauser": "pauser"}
    def holders(key, m):
        """kinds of the accounts that satisfy modifier m, or None when what was read cannot say"""
        b = m.split("(")[0]; a = ad.get(key); r = rh.get(key)
        if m.startswith("onlyRole(") and r:
            hs = r["roles"].get(m[9:-1]) or r["roles"].get(m[9:-1] + "*")
            return [k.split(" signers")[0].split(" (")[0].split(",")[0] for _, k in hs] if hs else None
        if b in GET and a and GET[b] in a["controllers"]: return ["plain account" if a["kinds"].get(GET[b]) == "EOA" else "contract"]
        if b == "onlyOwner":
            if r and r["owner"]: return ["plain account" if r["owner"][1] == "plain account" else r["owner"][1].split(" (")[0].split(",")[0]]
            if a and "owner" in a["controllers"]: return ["plain account" if a["kinds"].get("owner") == "EOA" else "contract"]
        return None
    print(f"\nWho can trigger it (guards joined to holders; direct functions only, update* excluded; exposure ${TOT:.2f}B):")
    for fam in ("freeze", "seize", "pause"):
        d = collections.defaultdict(float); single = []
        for r in rows:
            key = (r["chain"], r["token"].lower()); a = ad.get(key)
            if not a: continue
            e = (a["deposits"] + a["collateral"]) / 1e9
            ms = [m for fn, lst in r["funcs"].items() if not fn.lower().startswith("update") for gg in lst if gg["fam"] == fam for m in gg["mods"] if not m.startswith(("onlyWhen", "notOwner"))]
            if not ms: continue
            hs = [holders(key, m) for m in ms]; kinds = [k for h in hs if h for k in h]
            cls = "one account without code" if "plain account" in kinds else ("multisig, timelock or contract only" if kinds and all(h is not None for h in hs) else "guard found, holder not resolved")
            d[cls] += e
            if cls.startswith("one"): single.append((a["symbol"], a["chain"], round(e, 2)))
        print(f"  {fam:6s} " + " | ".join(f"{k} ${v:.2f}B ({100 * v / TOT:.0f}%)" for k, v in sorted(d.items(), key=lambda kv: kv[0])) + f"\n         one-account tokens: {sorted(single, key=lambda t: -t[2])[:10]}")
if ARGS.dump: json.dump(rows, open(ARGS.dump, "w")); print(f"wrote {ARGS.dump}")
