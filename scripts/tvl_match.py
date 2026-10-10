#!/usr/bin/env python3
"""Attach a DefiLlama TVL to every tracked target we can name with confidence.

The oracle scores *who can move the funds*; this script answers *how much sits behind that setup*, so the
dashboard can say "X USD in protocols scoring under 40". Read-only, no key. The match is an explicit table
(chain, address prefix) -> DefiLlama slug, written by hand: nothing is guessed from a name. A target not in
the table gets no TVL and the page says so. The TVL is the protocol's TVL on that chain when DefiLlama
breaks it down (scope "chain"), its total otherwise (scope "total"), or the whole chain's TVL for a target
that *is* the chain's authority (scope "chain-total": a rollup owner, a validator set, a native bridge).

    python3 scripts/tvl_match.py --out watch/tvl.json
"""
import argparse, glob, json, os, sys, time, urllib.request

def _dump_json(obj, path, indent=None):
    """Write the file only once the whole object is serialised: a crash half-way never leaves a truncated JSON behind
    (the previous run's file stays), and a reader never sees a half-written one."""
    import json as _j, os as _o
    tmp = path + ".tmp"
    with open(tmp, "w") as f: _j.dump(obj, f, indent=indent)
    _o.replace(tmp, path)


WATCH_SLUGS = {"robinhood-chain": "robinhood", "ethereum-l1-sepolia": "ethereum-l1", "arbitrum-sepolia": "arbitrum",
               "base-sepolia": "base", "plasma": "plasma", "tempo-moderato": "tempo", "monad": "monad", "hyperliquid-hyperevm": "hyperliquid", "solana-devnet": "solana"}
LLAMA_CHAIN = {"robinhood": "Robinhood Chain", "ethereum-l1": "Ethereum", "arbitrum": "Arbitrum", "base": "Base",
               "plasma": "Plasma", "tempo": "Tempo", "monad": "Monad", "hyperliquid": "Hyperliquid L1", "solana": "Solana"}
# (chain key, lowercase address prefix) -> slug, or "chain:<DefiLlama chain name>" for a chain's own authority.
# A third element overrides the chain whose TVL is read (a bridge that lives on another chain).
MAP = [
    ("robinhood", "0x8271e06e", "curve-dex"), ("robinhood", "0xd540f47f", "meridian-perps"), ("robinhood", "0x1195c074", "snuggle"),
    ("robinhood", "0x159a113e", "fables"), ("robinhood", "0x7f03effb", "noxa-fun"), ("robinhood", "0x02a84c1b", "pancakeswap-amm"),
    ("robinhood", "0x0bfbcf9f", "pancakeswap-amm-v3"), ("robinhood", "0xd5c6c796", "t3tris-finance"),
    ("robinhood", "0xe0c4ceb9", "ramses-cl-v2"), ("robinhood", "0x4b37359b", "ramses-cl-v2"), ("robinhood", "0x83341f89", "ramses-cl-v2"), ("robinhood", "0xa203a21d", "ramses-cl-v2"),
    ("robinhood", "0xbeeff033", "steakhouse-financial"), ("robinhood", "0xbeeff039", "steakhouse-financial"), ("robinhood", "0xbeefff13", "steakhouse-financial"), ("robinhood", "0xbeeff0fb", "steakhouse-financial"),
    ("robinhood", "0x0dc846db", "strato"), ("robinhood", "0x14b107cf", "arcus-perps"),
    ("robinhood", "0x9c3663fa", "arcus-ptokens"), ("robinhood", "0x925f92f0", "arcus-ptokens"), ("robinhood", "0x4472c69d", "arcus-ptokens"),
    ("robinhood", "0xe51960f1", "sushiswap-v3"), ("robinhood", "0xf28704c6", "uncx-network-v3"), ("robinhood", "0xfd2fd4b0", "spark-liquidity-layer"),
    ("robinhood", "0xde770c84", "spark-savings"), ("robinhood", "0x026df18f", "longbow"), ("robinhood", "0x65dc90cd", "longbow"), ("robinhood", "0xe129d4cb", "longbow"),
    ("robinhood", "0x544bf81c", "pendle-v2"), ("robinhood", "0x292fc50e", "symbiosis"), ("robinhood", "0x87673a61", "beefy"),
    ("robinhood", "0x94bab969", "lighter-robinhood-perps"), ("robinhood", "0x9d53d5e3", "morpho-blue"),
    ("robinhood", "0x6f475642", "layerzero-v2"), ("robinhood", "0xc39161c7", "layerzero-v2"), ("robinhood", "0xe1844c5d", "layerzero-v2"),
    ("robinhood", "0x1f7d7550", "uniswap-v3"), ("robinhood", "0x8366a39c", "uniswap-v3"), ("robinhood", "0x000000007a1c", "uniswap-v3"), ("robinhood", "0x8bceaa40", "uniswap-v3"),
    ("robinhood", "0x00000000000014aa", "ekubo"),
    ("robinhood", "0x23a19d23", "chain:Robinhood Chain"), ("robinhood", "0xbd0d173e", "chain:Robinhood Chain"), ("robinhood", "0x1232813b", "chain:Robinhood Chain"),
    ("robinhood", "0x1a07cc4b", "chain:Robinhood Chain"), ("robinhood", "0xdf875533", "chain:Robinhood Chain"), ("robinhood", "0xf0ce991e", "chain:Robinhood Chain"),
    ("ethereum-l1", "0xc139190f", "ethena-usdtb"), ("ethereum-l1", "0x73e35c5c", "ethena-usdtb"), ("ethereum-l1", "0x1d8f8f00", "rocket-pool"),
    ("ethereum-l1", "0xf403c135", "convex-finance"), ("ethereum-l1", "0x2cc440b7", "ethena-usde"), ("ethereum-l1", "0xe3490297", "ethena-usde"),
    ("ethereum-l1", "0x5d3a1ff2", "ethena-usde"), ("ethereum-l1", "0x211cc4dd", "ethena-usde"), ("ethereum-l1", "0x58538e6a", "ethena-usde"),
    ("ethereum-l1", "0x2260fac5", "wbtc"), ("ethereum-l1", "0xbbbbbbbb", "morpho-blue"), ("ethereum-l1", "0x85864637", "eigencloud"),
    ("ethereum-l1", "0x02c3ea4e", "sparklend"), ("ethereum-l1", "0x2f39d218", "aave-v3"), ("ethereum-l1", "0xc3d688b6", "compound-v3"),
    ("ethereum-l1", "0xae7ab965", "lido"), ("ethereum-l1", "0x6a8cbed7", "curve-dex"), ("ethereum-l1", "0xbe286431", "sky-lending"),
    ("ethereum-l1", "0x1f98431c", "uniswap-v3"), ("ethereum-l1", "0x000000000004444c", "uniswap-v4"),
    ("arbitrum", "0x3c3d99fd", "gmx-v2-perps"), ("arbitrum", "0x1a3c9b1d", "camelot-v3"), ("arbitrum", "0x88888888", "pendle-v2"),
    ("arbitrum", "0xe23b4ae3", "radiant-v2"), ("arbitrum", "0x52aa8994", "fluid-lending"), ("arbitrum", "0x489ee077", "gmx-v1-perps"),
    ("arbitrum", "0x423552c0", "chain:Arbitrum"), ("arbitrum", "0xa97684ea", "aave-v3"), ("arbitrum", "0x9c4ec768", "compound-v3"), ("arbitrum", "0x1f98431c", "uniswap-v3"),
    ("base", "0x420dd381", "aerodrome-v1"), ("base", "0x5e7bb104", "aerodrome-slipstream"), ("base", "0xbbbbbbbb", "morpho-blue"),
    ("base", "0xfbb21d03", "moonwell-lending"), ("base", "0xe20fcbdb", "aave-v3"), ("base", "0xb125e668", "compound-v3"),
    ("base", "0x8909dc15", "uniswap-v2"), ("base", "0x33128a8f", "uniswap-v3"), ("base", "0x498581ff", "uniswap-v4"),
    ("plasma", "0xa9c251f8", "telos-consilium"), ("plasma", "0x6c50b8ca", "chain:Plasma"), ("plasma", "0x88888888", "pendle-v2"),
    ("plasma", "0x6695c0f8", "yuzu-money"), ("plasma", "0x5d3a1ff2", "ethena-usde"), ("plasma", "0x52aa8994", "fluid-lending"),
    ("plasma", "0x42388213", "euler-v2"), ("plasma", "0x9b3ceb22", "euler-v2"), ("plasma", "0x061d8e13", "aave-v3"),
    ("monad", "0x8271e06e", "curve-dex"), ("monad", "0xd651346d", "kuru-clob"), ("monad", "0xad663ac8", "curvance"), ("monad", "0x34793fb9", "aave-v3"),
    ("monad", "0x36878c6f", "chain:Monad"), ("monad", "0x32841a85", "steakhouse-financial"), ("monad", "0xba4dd672", "euler-v2"), ("monad", "0x188d586d", "uniswap-v4"),
    ("tempo", "0x9a044ae0", "sentora-curator"), ("tempo", "0xc609656e", "gauntlet"), ("tempo", "0x10ee9aac", "morpho-blue"),
    ("tempo", "0xcccccccc", "chain:Tempo"), ("tempo", "0x20c00000000000000000000014f22ca9", "usdt0"),
    ("hyperliquid", "0xea394cd6", "hyperliquid-bridge"), ("hyperliquid", "0x2df1c51e", "hyperliquid-bridge", "Arbitrum"),
    ("hyperliquid", "0x393d0b87", "kinetiq-khype"), ("hyperliquid", "0x71f0019c", "kinetiq-kmhype"), ("hyperliquid", "0xdfc24b07", "hyperliquid-hlp"),
    ("hyperliquid", "0x574bafce", "unit"), ("hyperliquid", "0x8dafbe89", "unit"), ("hyperliquid", "0xa822a9ce", "unit"),
    ("hyperliquid", "0x72c98246", "hyperlend-pooled"), ("hyperliquid", "0x8888888192a4", "ventuals"),
    # Solana (program ids are base58; the prefix is matched lowercase)
    ("solana", "cpamdpzc", "meteora-damm-v2"), ("solana", "2lecshuw", "orca-dex"), ("solana", "so1enddq", "save"), ("solana", "7sf3tcwm", "save"),
    ("solana", "cammczo5", "raydium-amm"), ("solana", "4qp6fx6t", "marginfi-lending"), ("solana", "adya8hde", "pumpswap"), ("solana", "8szgkult", "marinade-liquid-staking"),
    ("solana", "h4nd9ayt", "jupiter-perpetual-exchange"), ("solana", "5ocnv1qi", "sanctum-infinity"), ("solana", "jup6lkbz", "jupiter-aggregator"), ("solana", "driftyha", "drift-trade"),
    ("solana", "jito4apy", "jito-liquid-staking"), ("solana", "gknhiwh3", "kamino-liquidity"), ("solana", "sp12twfx", "sanctum-validator-lsts"), ("solana", "7s1da8dd", "jupiter-lend"),
    ("solana", "7u3hehxy", "kamino-lend"),
]

def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers={"user-agent": "authority-risk-oracle watch"}), timeout=120) as r:
        return json.load(r)

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--out", default="watch/tvl.json"); ap.add_argument("--scores", default="watch/scores")
    a = ap.parse_args()
    protocols = {p["slug"]: p for p in get("https://api.llama.fi/protocols")}
    chains = {c["name"]: c["tvl"] for c in get("https://api.llama.fi/v2/chains")}
    out = {"generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "source": "DefiLlama (api.llama.fi/protocols, /v2/chains)",
           "matched": {}, "unmatched": [], "unknown_slugs": [], "no_figure": [], "chains": {k: chains.get(v) for k, v in LLAMA_CHAIN.items()}}
    for f in sorted(glob.glob(os.path.join(a.scores, "*.json"))):
        slug = os.path.basename(f)[:-5]; key = WATCH_SLUGS.get(slug)
        if not key: continue
        for t in json.load(open(f))["targets"]:
            addr = t["target"].lower(); hit = [m for m in MAP if m[0] == key and addr.startswith(m[1])]
            if not hit: out["unmatched"].append(key + ":" + addr); continue
            m = hit[0]; target = m[2]; chain = m[3] if len(m) > 3 else LLAMA_CHAIN[key]
            if target.startswith("chain:"):
                name = target[6:]; v = chains.get(name)
                if v is None: out["unknown_slugs"].append(target); continue
                out["matched"][key + ":" + addr] = {"slug": None, "name": name + " (whole chain)", "tvl": v, "scope": "chain-total", "chain": name}; continue
            p = protocols.get(target)
            if not p: out["unknown_slugs"].append(target); continue
            ct = (p.get("chainTvls") or {}).get(chain)
            if ct is not None: out["matched"][key + ":" + addr] = {"slug": target, "name": p["name"], "tvl": ct, "scope": "chain", "chain": chain, "category": p.get("category")}
            elif p.get("tvl") is None: out["unmatched"].append(key + ":" + addr); out["no_figure"].append(target); continue   # DefiLlama lists the protocol but publishes NO figure (1445 of 8691 on 10/10, a DEX aggregator among them): no figure is not a figure of zero, so the target gets none and the page says so
            else: out["matched"][key + ":" + addr] = {"slug": target, "name": p["name"], "tvl": p["tvl"], "scope": "total", "chain": None, "category": p.get("category")}
    out["unknown_slugs"] = sorted(set(out["unknown_slugs"])); out["no_figure"] = sorted(set(out["no_figure"]))
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    _dump_json(out, a.out, indent=1)
    total = sum(m["tvl"] for m in out["matched"].values())
    print(f"matched {len(out['matched'])} targets, {len(out['unmatched'])} without a TVL, {len(out['unknown_slugs'])} unknown slug(s) {out['unknown_slugs']}, sum {total/1e9:.1f}B USD (double counts shared slugs; the page dedupes)")
    if out["no_figure"]: print("note: DefiLlama publishes no TVL for %s: those targets carry no figure (not zero)" % ", ".join(out["no_figure"]))
    if out["unknown_slugs"]: print("warning: %d slug(s) unknown to DefiLlama (the hand-written map drifted): %s" % (len(out["unknown_slugs"]), ", ".join(map(str, out["unknown_slugs"][:10]))))
    return 0   # a drifted mapping is a warning in this log, not a failed job: the file above is complete for every other target

if __name__ == "__main__":
    sys.exit(main())
