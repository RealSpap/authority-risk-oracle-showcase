#!/usr/bin/env python3
"""Read-only: identity and rotation of the signers behind the Chainlink feed-owner Safes found by the ninth pass
(sweep_morpho_oracle_authority.py, 21 Sep): four Safes, one on each of Ethereum/Base/Robinhood Chain/Katana, all
4-of-9, owning the EACAggregatorProxy feeds that Morpho's ChainlinkOracleV2 markets read.
    python3 sweep_chainlink_feed_signers.py [--dump rows.json]
1. Re-derives the four Safe addresses from scratch (Morpho's public API lists markets and their oracle's feed
   addresses; owner() of each feed proxy is read on chain, not trusted from the API or from any prior note).
2. Reads getOwners()/getThreshold() of each of the four Safes and checks the signer sets are identical.
3. Identity, per signer: ENS reverse name (Ethereum mainnet), Blockscout public tags (Ethereum and Base), nonce.
4. Rotation: the AddedOwner/RemovedOwner/ChangedThreshold history of each Safe. Ethereum and Base are read through
   Blockscout's Etherscan-compatible log API, which serves the FULL history for free (their direct RPC refuses
   eth_getLogs beyond a short recent window on the free tier -- "Archive requests require a personal token" /
   "pruned history unavailable"; this is reported, not hidden). Robinhood Chain and Katana have no block explorer
   queried here, so their direct RPC's eth_getLogs is chunked from --since (default 2026-01-01) to latest, with the
   chunk width auto-discovered from the node's own "max allowed range" error instead of guessed, and the start
   block found by bisecting on block TIMESTAMP (eth_getCode looked cheaper but silently lies about history on a
   pruned node -- see find_deployment_block's docstring).
Nothing is sent, no key."""
import argparse, collections, datetime, json, re, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor
from web3 import Web3

RPC = {1: "https://ethereum-rpc.publicnode.com", 8453: "https://base-rpc.publicnode.com",
       4663: "https://rpc.mainnet.chain.robinhood.com", 747474: "https://rpc.katana.network"}
NAME = {1: "Ethereum", 8453: "Base", 4663: "Robinhood Chain", 747474: "Katana"}
BLOCKSCOUT = {1: "eth.blockscout.com", 8453: "base.blockscout.com"}  # no explorer queried for 4663 / 747474
ap = argparse.ArgumentParser()
ap.add_argument("--dump", default=None)
ap.add_argument("--since", default="2026-01-01", help="Robinhood Chain / Katana only (no explorer): scan their direct RPC from this date")
ARGS = ap.parse_args()


def curl(url, body=None, timeout=40):
    cmd = ["curl", "-s", "-m", str(timeout), "-A", "Mozilla/5.0"] + \
        (["-X", "POST", "-H", "content-type: application/json", "--data", json.dumps(body)] if body is not None else []) + [url]
    for _ in range(4):
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 5).stdout
            if out.strip():
                return json.loads(out)
        except Exception:
            pass
        time.sleep(1.5)
    return None


def gql(q):
    r = curl("https://blue-api.morpho.org/graphql", {"query": q}, timeout=60)
    if not r or not r.get("data"):
        sys.exit(f"Morpho API did not answer: {r}")
    return r["data"]


def rpc_err(ch, m, p, timeout=40):
    """Returns (result, error). Every other caller wants a plain result-or-None -- see rpc() below -- this is the
    one place that also needs the error body itself (to discover a node's real eth_getLogs range cap)."""
    for a in range(4):
        r = curl(RPC[ch], {"jsonrpc": "2.0", "id": 1, "method": m, "params": p}, timeout=timeout)
        if r and "error" not in r:
            return r.get("result"), None
        if r and "error" in r and "rate limit" not in json.dumps(r["error"]).lower():
            return None, r["error"]
        time.sleep(1.2 * (a + 1))
    return None, None


def rpc(ch, m, p, timeout=40):
    return rpc_err(ch, m, p, timeout)[0]


sel = lambda s: "0x" + bytes(Web3.keccak(text=s))[:4].hex()
call = lambda ch, to, sig, args="": rpc(ch, "eth_call", [{"to": to, "data": sel(sig) + args}, "latest"])

# ---------- 1. re-derive the four Safes from the feed proxies Morpho's ChainlinkOracleV2 markets actually read ----------
print("== step 1: re-deriving feed-owner Safes from Morpho markets (not trusted from any prior note) ==")
items, skip = [], 0
CH = list(RPC)
while True:
    q = ('{ markets(first: 500, skip: %d, where: { chainId_in: %s, supplyAssetsUsd_gte: 1000000 }) { items { '
         'listed chain { id } oracle { type data { ... on MorphoChainlinkOracleV2Data { baseFeedOne { address } '
         'baseFeedTwo { address } quoteFeedOne { address } quoteFeedTwo { address } } } } } pageInfo { countTotal } } }'
         % (skip, json.dumps(CH)))
    d = gql(q)["markets"]
    items += d["items"]
    skip += 500
    if skip >= d["pageInfo"]["countTotal"] or not d["items"]:
        break
L = [m for m in items if m["listed"] and (m["oracle"] or {}).get("type") == "ChainlinkOracleV2"]
print(f"{len(items)} markets fetched on the 4 chains ($1M+ supply), {len(L)} listed and on Morpho's Chainlink-based oracle")
feeds = set()
for m in L:
    dd = (m["oracle"] or {}).get("data") or {}
    ch = m["chain"]["id"]
    for f in (dd.get("baseFeedOne"), dd.get("baseFeedTwo"), dd.get("quoteFeedOne"), dd.get("quoteFeedTwo")):
        if f and f.get("address"):
            feeds.add((ch, f["address"].lower()))
print(f"{len(feeds)} distinct feed proxy contracts across the 4 chains")


def owner(k):
    ch, a = k
    r = call(ch, a, "owner()")
    r = r if isinstance(r, str) else None
    return k, (("0x" + r[-40:]) if r and len(r) >= 42 and int(r, 16) else None)


owners = {}
with ThreadPoolExecutor(10) as ex:
    for k, o in ex.map(owner, list(feeds)):
        owners[k] = o
grp = collections.defaultdict(int)
for (ch, a), o in owners.items():
    if o:
        grp[(ch, o)] += 1
print("\nfeed owners found, by chain, ranked by number of feeds owned:")
top_per_chain = {}
for ch in CH:
    chain_owners = sorted(((o, n) for (c, o), n in grp.items() if c == ch), key=lambda kv: -kv[1])
    for o, n in chain_owners[:5]:
        print(f"  {NAME[ch]:16s} {o} owns {n:3d} feeds")
    if chain_owners:
        top_per_chain[ch] = Web3.to_checksum_address(chain_owners[0][0])
print("\ntop owner per chain (candidate 'the Safe'):")
for ch, a in top_per_chain.items():
    print(f"  {NAME[ch]:16s} {a}")

# ---------- 2. signers of each of the four Safes ----------
print("\n== step 2: signers of each candidate Safe (getOwners/getThreshold read live, not from the ninth pass) ==")
safes = {}
for ch, a in top_per_chain.items():
    thr, own = call(ch, a, "getThreshold()"), call(ch, a, "getOwners()")
    ver = call(ch, a, "VERSION()")
    thr = thr if isinstance(thr, str) else None
    own = own if isinstance(own, str) else None
    ver = ver if isinstance(ver, str) else None
    if not (thr and own and len(own) > 130):
        print(f"  {NAME[ch]:16s} {a}: not a readable Safe (getOwners/getThreshold empty)")
        continue
    h = own[2:]
    n = int(h[64:128], 16)
    signer_set = {Web3.to_checksum_address("0x" + h[128 + 64 * i + 24:128 + 64 * (i + 1)]) for i in range(n)}
    version = bytes.fromhex(ver[130:130 + 2 * int(ver[66:130], 16)]).decode() if ver and len(ver) > 130 else "?"
    safes[ch] = dict(address=a, threshold=int(thr, 16), signers=signer_set, version=version)
    print(f"  {NAME[ch]:16s} {a}  Safe {int(thr, 16)}-of-{n} v{version}")
    for s in sorted(signer_set):
        print(f"      {s}")

sets = {ch: v["signers"] for ch, v in safes.items()}
if len(sets) > 1:
    inter = set.intersection(*sets.values())
    union = set.union(*sets.values())
    print(f"\nsigners common to all {len(sets)} readable Safes: {len(inter)} of {len(union)} distinct")
    print("-> the signer set is IDENTICAL across all readable chains, today." if inter == union else "-> signer sets DIFFER across chains, today.")

all_signers = sorted(set.union(*sets.values())) if sets else []

# ---------- 3. identity: ENS reverse name + Blockscout tags + nonce ----------
print("\n== step 3: identity of the signers (public sources only) ==")
w3 = Web3(Web3.HTTPProvider(RPC[1]))
identity = {}
for a in all_signers:
    rec = {"ens": None, "blockscout_eth_tags": None, "blockscout_base_tags": None, "nonce_eth": None}
    try:
        rec["ens"] = w3.ens.name(a)
    except Exception as e:
        rec["ens"] = f"(lookup failed: {e})"
    nonce = rpc(1, "eth_getTransactionCount", [a, "latest"])
    nonce = nonce if isinstance(nonce, str) else None
    rec["nonce_eth"] = int(nonce, 16) if nonce else None
    for chid, host in BLOCKSCOUT.items():
        d = curl(f"https://{host}/api/v2/addresses/{a}") or {}
        tags = []
        if d.get("ens_domain_name") and not rec["ens"]:
            rec["ens"] = d["ens_domain_name"] + " (from Blockscout, not the ENS reverse resolver)"
        meta = d.get("metadata")
        for t in (meta.get("tags", []) if isinstance(meta, dict) else []):
            tags.append(t.get("name") or t)
        if d.get("public_tags"):
            tags += d["public_tags"]
        if tags:
            rec[f"blockscout_{'eth' if chid == 1 else 'base'}_tags"] = tags
    identity[a] = rec
    ens = rec["ens"] or "no ENS name"
    tags = rec["blockscout_eth_tags"] or rec["blockscout_base_tags"]
    print(f"  {a}  nonce(eth)={rec['nonce_eth']}  ENS: {ens}" + (f"  tags: {tags}" if tags else ""))

n_identified = sum(1 for r in identity.values() if (r["ens"] and "lookup failed" not in str(r["ens"])) or r["blockscout_eth_tags"] or r["blockscout_base_tags"])
print(f"\n{n_identified} of {len(all_signers)} signers have a public ENS name or Blockscout tag.")

# ---------- 4. rotation: full AddedOwner / RemovedOwner / ChangedThreshold history ----------
print("\n== step 4: full owner-change history of each Safe (on-chain events, per chain) ==")
TOPIC = {"AddedOwner": "0x" + bytes(Web3.keccak(text="AddedOwner(address)")).hex(),
         "RemovedOwner": "0x" + bytes(Web3.keccak(text="RemovedOwner(address)")).hex(),
         "ChangedThreshold": "0x" + bytes(Web3.keccak(text="ChangedThreshold(uint256)")).hex()}


def decode_row(kind, data_hex):
    return ("0x" + data_hex[-40:]) if kind != "ChangedThreshold" else str(int(data_hex, 16))


def via_blockscout(host, addr):
    rows = []
    for kind, topic in TOPIC.items():
        url = f"https://{host}/api?module=logs&action=getLogs&address={addr}&topic0={topic}&fromBlock=1&toBlock=latest"
        backoff = 8
        got = None
        for _ in range(6):
            out = curl(url, timeout=40)
            if out and (out.get("status") == "1" or out.get("message") == "No logs found"):
                got = out.get("result") or []
                break
            time.sleep(backoff)
            backoff = min(backoff * 1.6, 40)
        if got is None:
            print(f"    [{kind}] gave up after retries (Blockscout rate limit) -- incomplete, not fabricated as empty")
            continue
        for it in got:
            rows.append(dict(block=int(it["blockNumber"], 16), ts=int(it["timeStamp"], 16), kind=kind,
                              value=decode_row(kind, it["data"]), tx=it["transactionHash"]))
    return rows


def find_deployment_block(ch, addr):
    """eth_getCode at an old block silently comes back '0x' on some pruned/state-limited nodes (Robinhood Chain's
    RPC does this) -- indistinguishable from genuine absence, so bisecting on it converges on the wrong end (looks
    'just deployed' at the current tip). eth_getBlockByNumber needs no state, only block headers, and was reliable
    at every height tried on every chain here, so bisect on the block TIMESTAMP against --since instead."""
    latest = int(rpc(ch, "eth_blockNumber", []), 16)
    since_ts = int(datetime.datetime.strptime(ARGS.since, "%Y-%m-%d").replace(tzinfo=datetime.timezone.utc).timestamp())
    lo, hi = 1, latest
    for _ in range(30):
        if hi - lo <= 1:
            break
        mid = (lo + hi) // 2
        blk = rpc(ch, "eth_getBlockByNumber", [hex(mid), False])
        ts = int(blk["timestamp"], 16) if isinstance(blk, dict) else None
        if ts is None:
            continue  # inconclusive read: resample, don't let it bias the search
        if ts < since_ts:
            lo = mid
        else:
            hi = mid
    return lo


def via_rpc(ch, addr):
    latest = int(rpc(ch, "eth_blockNumber", []), 16)
    start = find_deployment_block(ch, addr)
    print(f"    scanning from block {start} (~{ARGS.since}) to {latest} ({latest - start} blocks)")
    rows = []
    b = start
    chunk = 2_000_000
    calls = 0
    while b <= latest and calls < 400:
        top = min(b + chunk, latest)
        logs, err = rpc_err(ch, "eth_getLogs", [{"address": addr, "fromBlock": hex(b), "toBlock": hex(top), "topics": [list(TOPIC.values())]}], timeout=60)
        calls += 1
        if err is not None:  # discover the node's real max range from its own error message instead of guessing
            m = re.search(r'"maxAllowedRange"\s*:\s*(\d+)', json.dumps(err))
            if m and int(m.group(1)) < chunk:
                chunk = int(m.group(1))
                continue  # retry same window with the corrected width
            if top - b > 300:
                chunk = max(300, chunk // 2)
                continue
            print(f"    [skip] block {b}-{top}: {err}")
            b = top + 1
            continue
        for lg in (logs or []):
            kind = {v.lower(): k for k, v in TOPIC.items()}.get(lg["topics"][0].lower())
            if kind:
                rows.append(dict(block=int(lg["blockNumber"], 16), ts=None, kind=kind,
                                  value=decode_row(kind, lg["data"]), tx=lg["transactionHash"]))
        b = top + 1
    blocks = sorted({r["block"] for r in rows})
    ts_cache = {}
    for bn in blocks:
        blk = rpc(ch, "eth_getBlockByNumber", [hex(bn), False])
        blk = blk if isinstance(blk, dict) else None
        ts_cache[bn] = int(blk["timestamp"], 16) if blk else None
    for r in rows:
        r["ts"] = ts_cache.get(r["block"])
    if calls >= 400:
        print(f"    [stopped] hit the 400-call cap for this pass at block {b}; scan is INCOMPLETE past there")
    return rows


rotation_rows = []
for ch, info in safes.items():
    a = info["address"]
    print(f"\n  {NAME[ch]}: {a}")
    rows = via_blockscout(BLOCKSCOUT[ch], a) if ch in BLOCKSCOUT else via_rpc(ch, a)
    rows.sort(key=lambda r: (r["block"], r["tx"]))
    if not rows:
        print("    no AddedOwner/RemovedOwner/ChangedThreshold event ever found for this Safe.")
    for r in rows:
        dt = datetime.datetime.utcfromtimestamp(r["ts"]).strftime("%Y-%m-%d %H:%M:%S UTC") if r["ts"] else "unknown time"
        r["chain"] = NAME[ch]
        r["date_utc"] = dt
        print(f"    block {r['block']:>10}  {dt}  {r['kind']:16s} {r['value']}  tx {r['tx']}")
    rotation_rows += rows

# highlight the most recent swap (matching Added+Removed value in the same tx) per chain
print("\n== most recent owner swap per chain (same tx carrying both an AddedOwner and a RemovedOwner) ==")
by_tx = collections.defaultdict(list)
for r in rotation_rows:
    by_tx[(r["chain"], r["tx"])].append(r)
swaps = []
for (chain, tx), rs in by_tx.items():
    added = [r for r in rs if r["kind"] == "AddedOwner"]
    removed = [r for r in rs if r["kind"] == "RemovedOwner"]
    if added and removed:
        swaps.append((max(r["block"] for r in rs), chain, tx, removed[0]["value"], added[0]["value"], rs[0]["date_utc"]))
for block, chain, tx, out_addr, in_addr, dt in sorted(swaps, key=lambda s: -s[0])[:8]:
    print(f"  {chain:16s} {dt}  {out_addr} -> {in_addr}  tx {tx}")
if not swaps:
    print("  none found (no single tx carried both an AddedOwner and a RemovedOwner on any of the readable Safes)")

if ARGS.dump:
    json.dump(dict(safes={ch: dict(address=v["address"], threshold=v["threshold"], version=v["version"],
                                    signers=sorted(v["signers"])) for ch, v in safes.items()},
                    identity=identity, rotation=rotation_rows), open(ARGS.dump, "w"), indent=2)
    print(f"\nwrote {ARGS.dump}")
