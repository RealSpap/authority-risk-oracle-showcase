#!/usr/bin/env python3
"""Read-only: do tokenized stocks (Backed Finance "xStocks", Dinari dShares, Swarm, etc. -- an on-chain token that tracks a real
listed equity or an equity index like the S&P 500) appear TODAY as an actual deposit/collateral asset in the lending markets this
project already tracks on Ethereum L1 (Aave, Morpho, Compound, Spark, Euler, Dolomite, Maple)?
    python3 chains/ethereum-l1/scripts/sweep_tokenized_equity_collateral.py [--dump rows.json]
Pools come from DefiLlama's public yields API (yields.llama.fi/pools, an indexer), scanned for the tracked projects' pools whose
symbol/pool name matches an equity-ticker-like pattern (stock, SPY, AAPL, TSLA, NVDA, ... or "xstock"/"dshares"). DefiLlama's
generic pools endpoint does not say loan vs collateral for a Morpho market, so every Morpho hit is cross-checked against Morpho's
own GraphQL API (blue-api.morpho.org) for the real per-market split (collateralAsset vs loanAsset, with live USD amounts and LLTV).
A symbol match is not proof of a real tokenized stock: some hits are vault/strategy tokens whose NAME happens to contain "stock"
(e.g. a basis-trade vault). Each hit's underlying token name/symbol is read from Blockscout and printed so this can be judged by a
human, not assumed. For every hit confirmed as a real tokenized-equity collateral asset, this then reads its on-chain authority
the same way sweep_asset_authority.py does: the verified ABI (Blockscout) for freeze/pause/mint/burn-family functions, the
zero-arg address-returning getters (owner, pauser, ...), and classifies each controller account (EOA, Safe t-of-n, other
contract). If the wrapper's own asset() points at an unwrapped underlying token, that underlying is resolved too. Nothing is
sent, no key."""
import argparse, json, re, subprocess, sys, time
from web3 import Web3

ap = argparse.ArgumentParser()
ap.add_argument("--dump", default=None)
ARGS = ap.parse_args()

RPC = "https://ethereum.publicnode.com"
BLOCKSCOUT = "eth.blockscout.com"
# the lending projects this repo already tracks on Ethereum L1 (DefiLlama yields "project" slugs, verified live 2026-09-25)
TARGET_PROJECTS = ["aave-v3", "aave-v4", "compound-v2", "compound-v3", "morpho-blue", "sparklend", "spark-savings", "euler-v2", "dolomite", "maple"]
STOCK_RE = re.compile(r"\bstock\b|xstock|dshares|\bspy\b|spyx|wspyx|\baapl\b|\btsla\b|\bnvda\b|\bmsft\b|googl?x?\b|\bamzn\b|\bmeta\b|\bmstr\b|\bhood\b|\bcoin\b", re.I)
FAM = {"freeze": re.compile(r"blacklist|blocklist|denylist|freeze|frozen|banaddress|blockaccount|sanctionslist", re.I),
       "seize": re.compile(r"wipe|destroyblack|seize(?!cooldown)|clawback|forcetransfer|forcedtransfer|confiscate|forceburn", re.I),
       "pause": re.compile(r"pause", re.I), "mint": re.compile(r"^mint", re.I), "burn": re.compile(r"^burn|^redeem", re.I)}
GETTERS = ("owner", "admin", "pauser", "sanctionsList", "blacklister", "freezer", "guardian", "asset")


def curl(url, body=None, tries=3):
    cmd = ["curl", "-s", "-m", "60", "-A", "Mozilla/5.0"] + (["-X", "POST", "-H", "content-type: application/json", "--data", json.dumps(body)] if body is not None else []) + [url]
    for a in range(tries):
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=70)
            if r.stdout:
                return json.loads(r.stdout)
        except Exception:
            time.sleep(1.0 * (a + 1))
    return None


def rpc(m, p):
    d = curl(RPC, {"jsonrpc": "2.0", "id": 1, "method": m, "params": p})
    return (d or {}).get("result")


sel = lambda s: "0x" + bytes(Web3.keccak(text=s))[:4].hex()
call = lambda to, sig: rpc("eth_call", [{"to": to, "data": sel(sig)}, "latest"])


def kind(a):
    if not a or int(a, 16) == 0:
        return "none"
    code = rpc("eth_getCode", [a, "latest"]) or "0x"
    if code == "0x":
        return "EOA"
    t, o = call(a, "getThreshold()"), call(a, "getOwners()")
    if t and t != "0x" and o and len(o) > 130:
        n = int(o[2 + 64:2 + 128], 16)
        owners = sorted("0x" + o[2 + 128 + 64 * i + 24:2 + 128 + 64 * (i + 1)] for i in range(n))
        return f"Safe {int(t, 16)}-of-{n} {owners}"
    return f"contract ({(len(code) - 2) // 2} B)"


def morpho_gql(q):
    d = curl("https://blue-api.morpho.org/graphql", {"query": q})
    if not d or not d.get("data"):
        return None
    return d["data"]


def morpho_role_of_token(addr):
    """Scan every listed Morpho Blue market on Ethereum for one where `addr` is the collateral or the loan asset."""
    target = addr.lower()
    found, skip = [], 0
    while True:
        d = morpho_gql('{ markets(first: 500, skip: %d) { items { listed chain { id } loanAsset { address symbol } '
                        'collateralAsset { address symbol } state { supplyAssetsUsd collateralAssetsUsd borrowAssetsUsd } lltv } '
                        'pageInfo { countTotal } } }' % skip)
        if not d:
            return None  # API unreachable -- caller must say so, not assume "not found"
        items = d["markets"]["items"]
        for m in items:
            if m["chain"]["id"] != 1 or not m["listed"]:
                continue
            ca = (m.get("collateralAsset") or {}).get("address") or ""
            la = (m.get("loanAsset") or {}).get("address") or ""
            if ca.lower() == target:
                found.append(("collateral", m))
            if la.lower() == target:
                found.append(("loan", m))
        skip += 500
        if skip >= d["markets"]["pageInfo"]["countTotal"] or not items:
            break
    return found


def token_meta(addr):
    d = curl(f"https://{BLOCKSCOUT}/api/v2/tokens/{addr}")
    return d if d and not d.get("message") else None


def authority(addr):
    """Verified ABI (own contract, or the EIP-1967 implementation behind a proxy) -> capability families + controller accounts."""
    out = dict(name=None, proxy=False, fam={f: [] for f in FAM}, controllers={}, kinds={}, note=None)
    d = curl(f"https://{BLOCKSCOUT}/api/v2/smart-contracts/{addr}")
    if not d or d.get("message") or (not d.get("is_verified") and not d.get("abi") and not d.get("implementations")):
        out["note"] = "not verified or unread on Blockscout"
        return out
    abis = [d.get("abi") or []]
    for im in (d.get("implementations") or [])[:1]:
        ia = im.get("address") or im.get("address_hash")
        di = curl(f"https://{BLOCKSCOUT}/api/v2/smart-contracts/{ia}") if ia else None
        if di:
            abis.append(di.get("abi") or [])
    fns = {x["name"] for ab in abis for x in ab if x.get("type") == "function" and x.get("stateMutability") not in ("view", "pure")}
    views = {x["name"] for ab in abis for x in ab if x.get("type") == "function" and x.get("stateMutability") in ("view", "pure")
             and not x.get("inputs") and x.get("outputs") and x["outputs"][0].get("type") == "address"}
    out["name"] = d.get("name"); out["proxy"] = bool(d.get("proxy_type") or d.get("implementations"))
    out["fam"] = {f: sorted(n for n in fns if rx.search(n))[:5] for f, rx in FAM.items()}
    for g in GETTERS:
        if g in views:
            r = call(addr, f"{g}()")
            if r and len(r) >= 42 and int(r, 16):
                out["controllers"][g] = "0x" + r[-40:]
    out["kinds"] = {g: kind(v) for g, v in out["controllers"].items() if g != "asset"}
    return out


# ---- 1. tracked-project pools whose symbol/name looks like a tokenized stock ----
pools = curl("https://yields.llama.fi/pools")
if not pools or not pools.get("data"):
    sys.exit("DefiLlama yields API did not answer -- cannot proceed (not a negative result, an unreachable source)")
data = pools["data"]
candidates = [p for p in data if p.get("project") in TARGET_PROJECTS and p.get("chain") == "Ethereum"
              and (STOCK_RE.search(p.get("symbol") or "") or STOCK_RE.search(p.get("pool") or "")) and p.get("underlyingTokens")]
print(f"{len(data)} DefiLlama pools scanned; {len(candidates)} candidate pool(s) on Ethereum in the {len(TARGET_PROJECTS)} tracked "
      f"lending projects ({', '.join(TARGET_PROJECTS)}) whose symbol matches a tokenized-equity-like pattern")

seen_tokens, rows = set(), []
for p in candidates:
    tok = (p["underlyingTokens"][0] or "").lower()
    if not tok or int(tok, 16) == 0 or tok in seen_tokens:
        continue
    seen_tokens.add(tok)
    meta = token_meta(tok)
    real_name = (meta or {}).get("name") or "?"
    real_symbol = (meta or {}).get("symbol") or "?"
    print(f"\n== candidate: DefiLlama {p['project']} pool '{p['symbol']}' -> token {tok}")
    print(f"   on-chain token name/symbol (Blockscout): \"{real_name}\" / \"{real_symbol}\"")
    row = dict(project=p["project"], defillama_symbol=p["symbol"], token=tok, name=real_name, symbol=real_symbol, role=None, market=None)
    if p["project"] == "morpho-blue":
        roles = morpho_role_of_token(tok)
        if roles is None:
            print("   Morpho GraphQL API unreachable -- role (collateral vs loan) could not be confirmed, skipping this candidate honestly")
            row["note"] = "morpho api unreachable, role unconfirmed"
            rows.append(row); continue
        if not roles:
            print("   listed on DefiLlama as a Morpho pool but NOT found as collateral or loan asset in any currently LISTED Morpho market -- likely delisted/stale pool")
            row["note"] = "not in any listed morpho market"
            rows.append(row); continue
        for role, m in roles:
            st = m["state"]
            print(f"   Morpho market: role={role} chain=Ethereum loanAsset={m['loanAsset']['symbol']} collateralAsset={m['collateralAsset']['symbol']} "
                  f"lltv={int(m['lltv'])/1e18:.2%} supplyUSD=${st['supplyAssetsUsd']:,.0f} collateralUSD=${st['collateralAssetsUsd']:,.0f} borrowUSD=${st['borrowAssetsUsd']:,.0f}")
            r2 = dict(row); r2["role"] = role; r2["market"] = m; rows.append(r2)
    else:
        print(f"   note: not a Morpho pool -- DefiLlama's generic yields endpoint does not distinguish collateral vs pure supply for {p['project']}; reported as present, role unconfirmed")
        row["note"] = "role unconfirmed (non-morpho pool)"; rows.append(row)

# ---- 2. manual read of each hit's real identity, to separate true tokenized-equity collateral from name-only false positives ----
confirmed = [r for r in rows if r.get("role") == "collateral"]
print(f"\n{'='*90}\nCONFIRMED as collateral in a currently listed market of a tracked lender: {len(confirmed)} token(s)")
if not confirmed:
    print("No tokenized stock was found as REAL collateral in the tracked lending markets today -- negative result.")
for r in confirmed:
    m = r["market"]
    print(f"\n--- {r['name']} ({r['symbol']}) -- {r['token']}")
    print(f"    Morpho Blue market on Ethereum: collateral, loan asset {m['loanAsset']['symbol']}, LLTV {int(m['lltv'])/1e18:.0%}, "
          f"collateral posted ${m['state']['collateralAssetsUsd']:,.0f}, currently borrowed ${m['state']['borrowAssetsUsd']:,.0f}")
    auth = authority(r["token"])
    if auth["note"]:
        print(f"    authority: {auth['note']}")
    else:
        print(f"    contract: {auth['name']}" + (" (behind an EIP-1967 proxy)" if auth["proxy"] else ""))
        for fam, fns in auth["fam"].items():
            if fns:
                print(f"      {fam}-family function(s): {fns}")
        for g, addr in auth["controllers"].items():
            if g == "asset":
                m2 = token_meta(addr)
                print(f"      asset() -> unwraps to {addr} = \"{(m2 or {}).get('name') or '?'}\" ({(m2 or {}).get('symbol') or '?'})")
            else:
                print(f"      {g} = {addr} -> {auth['kinds'].get(g)}")

if ARGS.dump:
    json.dump(rows, open(ARGS.dump, "w"), default=str)
    print(f"\nwrote {len(rows)} rows to {ARGS.dump}")
