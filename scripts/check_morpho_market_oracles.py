#!/usr/bin/env python3
"""Who can move the price each Morpho market trusts? (read-only, public RPC + Morpho's public API, no key)

The vault layer already has curator/owner scoring; the price a market lends against comes from its oracle's feeds,
and a feed behind an EIP-1967 proxy or a Chainlink proxy has an admin that can repoint it. For every listed Morpho
market above a supply floor on the ecosystems this oracle tracks, this reads each feed's proxy admin (EIP-1967 slot),
that admin's owner(), and the feed's own owner(), classifies the controlling address (EOA / Safe k-of-n / contract,
timelock delay when it is a plain timelock) and groups markets by controller.

    python3 scripts/check_morpho_market_oracles.py                 # markets >= $5M supply
    python3 scripts/check_morpho_market_oracles.py --min-usd 1e6 --out data/morpho_market_oracles_2026-09-26.json

Complements chains/ethereum-l1/scripts/sweep_morpho_oracle_authority.py (21/09), which reads owner() of Chainlink feed proxies:
this adds the EIP-1967 proxy-admin path, classifies every controller (EOA / Safe k-of-n / timelock, weak quorums flagged), and
unwraps a MetaOracleDeviationTimelock (no admin of its own) into its primary and backup oracles' feeds.

Disclosed only: no score reads this. "No admin found" means neither an EIP-1967 admin nor owner() was readable on the
feed, NOT that the feed is proven immutable. A read that failed on the network is counted as UNREAD, never as "no admin".
"""
import argparse
import json
import subprocess
import sys
import os
from concurrent.futures import ThreadPoolExecutor

from web3 import Web3

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "lib"))
from lib import code_review  # noqa: E402
from lib.issuer_power import classify_controller  # noqa: E402
from lib.market_oracles import concentration, controller_of, group_by_signers, market_feeds, path_split, weak_controller  # noqa: E402
from lib.web3_utils import EIP1967_ADMIN_SLOT, EIP1967_IMPLEMENTATION_SLOT, RpcUnavailable, call_raw, get_w3, read_address_getter, read_slot_as_address, safe_owners_and_threshold  # noqa: E402

MORPHO_API = "https://blue-api.morpho.org/graphql"
# Morpho API chain id -> public RPC, only the ecosystems this oracle tracks.
RPC = {1: "https://ethereum-rpc.publicnode.com", 8453: "https://base-rpc.publicnode.com", 42161: "https://arbitrum-one-rpc.publicnode.com",
       143: "https://rpc.monad.xyz", 999: "https://rpc.hyperliquid.xyz/evm", 4663: "https://rpc.mainnet.chain.robinhood.com"}
ZERO = "0x0000000000000000000000000000000000000000"
_MIN_DELAY_ABI = [{"name": "getMinDelay", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "uint256"}]}]

QUERY = """query($min: Float!) { markets(first: 500, orderBy: SupplyAssetsUsd, orderDirection: Desc,
  where: {supplyAssetsUsd_gte: $min, listed: true}) { items { marketId chain{id} loanAsset{symbol} collateralAsset{symbol}
  state{supplyAssetsUsd} oracle{ address type data { __typename
  ... on MorphoChainlinkOracleV2Data { baseFeedOne{address} baseFeedTwo{address} quoteFeedOne{address} quoteFeedTwo{address} }
  ... on MorphoChainlinkOracleData { baseFeedOne{address} baseFeedTwo{address} quoteFeedOne{address} quoteFeedTwo{address} } } } } } }"""


def fetch_markets(min_usd):
    """curl, not urllib: same chunked-read quirk as scripts/check_vault_v2_inventory.py (see its fetch_vaults)."""
    cmd = ["curl", "-s", "-m", "60", "-A", "Mozilla/5.0", "-X", "POST", MORPHO_API, "-H", "content-type: application/json",
           "--data", json.dumps({"query": QUERY, "variables": {"min": float(min_usd)}})]
    out = json.loads(subprocess.run(cmd, capture_output=True, text=True, check=True).stdout)
    if "errors" in out:
        raise SystemExit(f"Morpho API error: {out['errors'][:2]}")
    return out["data"]["markets"]["items"]


def _nz(a):
    return None if not a or a == ZERO else a


def read_feed(w3, feed):
    r = {"feed": feed}
    try:
        r["admin"] = _nz(read_slot_as_address(w3, feed, EIP1967_ADMIN_SLOT))
        owner = read_address_getter(w3, feed, "owner")
        r["feed_owner"] = _nz(owner)
        r["renounced"] = owner == ZERO
        r["admin_owner"] = _nz(read_address_getter(w3, r["admin"], "owner")) if r["admin"] else None
    except RpcUnavailable as e:
        r["unread"] = str(e)
    return r


SET_ROUND_DATA = "0x" + bytes(Web3.keccak(text="setRoundData(int256)"))[:4].hex()


def admin_set_price(w3, feed):
    """(True, target) if the feed, or the feed it wraps through underlyingFeed(), exposes setRoundData(int256): its price is POSTED by a role
    holder, not observed. Looks at the dispatcher selectors of the target's implementation (EIP-1967) or its own code, so it works on a chain
    with no explorer. A read failure raises RpcUnavailable: never reported as False."""
    target = feed
    for _ in range(2):
        under = _nz(read_address_getter(w3, target, "underlyingFeed"))
        if not under:
            break
        target = under
    impl = _nz(read_slot_as_address(w3, target, EIP1967_IMPLEMENTATION_SLOT))
    code = bytes(w3.eth.get_code(w3.to_checksum_address(impl or target)))
    return SET_ROUND_DATA in code_review.selectors(code), target


_FEED_GETTERS = ("BASE_FEED_1", "BASE_FEED_2", "QUOTE_FEED_1", "QUOTE_FEED_2")


def expand_custom(w3, oracle):
    """A MetaOracleDeviationTimelock has no admin and no setter, but reads a primary and a backup oracle: the price authority
    is theirs. Returns [(feed, kind)] for the feeds of those underlying Morpho oracles (their BASE_/QUOTE_FEED getters), or
    the underlying oracle itself when it is not that shape, or the oracle itself when it has no primary/backup at all."""
    out = []
    try:
        for role in ("primaryOracle", "backupOracle"):
            under = _nz(read_address_getter(w3, oracle, role))
            if not under:
                continue
            feeds = [f for f in (_nz(read_address_getter(w3, under, g)) for g in _FEED_GETTERS) if f]
            out += [(f, f"{role}-feed") for f in feeds] or [(under, f"{role}-oracle")]
    except RpcUnavailable:
        return [(oracle, "custom-oracle")]
    return out or [(oracle, "custom-oracle")]


def classify(w3, addr):
    """(label, safe_shape) for one controller: label is EOA / Safe k-of-n / contract; safe_shape is (threshold, frozenset of
    lowercase owners) for a Safe, else None. Safe shape is read WITHOUT the module gate (this asks who signs, and the gate
    would hide a Safe carrying an unanalyzed module as a plain "contract"); a Safe the gate would reject is flagged."""
    try:
        code_len = len(w3.eth.get_code(w3.to_checksum_address(addr)))
        safe = safe_owners_and_threshold(w3, addr, check_modules=False) if code_len else None
        gated = safe_owners_and_threshold(w3, addr) if safe else None
    except RpcUnavailable:
        return "unread", None
    label = classify_controller(code_len, safe is not None, (safe[1], len(safe[0])) if safe else None)
    if safe and gated is None:
        label += " (unanalyzed module or singleton)"
    if label.startswith("contract"):
        try:
            d = call_raw(w3, addr, _MIN_DELAY_ABI, "getMinDelay")
        except RpcUnavailable:
            d = None
        if d is not None:
            label += f", timelock {d}s"
    return label, ((safe[1], frozenset(o.lower() for o in safe[0])) if safe else None)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--min-usd", type=float, default=5e6)
    ap.add_argument("--out")
    args = ap.parse_args()

    markets = [m for m in fetch_markets(args.min_usd) if m["chain"]["id"] in RPC]
    w3 = {c: get_w3(u) for c, u in RPC.items()}
    for c, w in w3.items():  # a wrong RPC for a chain id would silently read the wrong chain
        assert w.eth.chain_id == c, f"RPC for chain {c} answers chain id {w.eth.chain_id}"

    with ThreadPoolExecutor(6) as ex:
        market_targets = dict(zip((m["marketId"] for m in markets), ex.map(
            lambda m: [(f, "feed") for f in market_feeds(m)] or (expand_custom(w3[m["chain"]["id"]], m["oracle"]["address"]) if (m.get("oracle") or {}).get("address") else []),
            markets)))
    targets = {(m["chain"]["id"], f): k for m in markets for f, k in market_targets[m["marketId"]]}  # (chain, address) -> kind

    with ThreadPoolExecutor(6) as ex:
        reads = dict(zip(targets, ex.map(lambda k: read_feed(w3[k[0]], k[1]), targets)))

    def flag(k):
        try:
            return admin_set_price(w3[k[0]], k[1])
        except RpcUnavailable:
            return None, None
    # Every read feed, not only the ones with no admin: a proxied feed with a timelocked ProxyAdmin can STILL be posted by a role holder.
    readable = [k for k, r in reads.items() if "unread" not in r]
    with ThreadPoolExecutor(6) as ex:
        set_price = dict(zip(readable, ex.map(flag, readable)))

    ctrl_keys = sorted({(c, controller_of(r)) for (c, _), r in reads.items() if controller_of(r) and "unread" not in r})
    with ThreadPoolExecutor(6) as ex:
        classified = dict(zip(ctrl_keys, ex.map(lambda k: classify(w3[k[0]], k[1]), ctrl_keys)))
    classes = {k: v[0] for k, v in classified.items()}
    safe_sets = {k: v[1] for k, v in classified.items() if v[1]}

    rows = []
    for m in markets:
        chain = m["chain"]["id"]
        for f, kind in market_targets[m["marketId"]]:
            r = reads[(chain, f)]
            c = controller_of(r) if "unread" not in r else None
            rows.append({"chain": chain, "market": m["marketId"], "pair": f"{(m['collateralAsset'] or {}).get('symbol')}/{m['loanAsset']['symbol']}",
                         "supplyUsd": m["state"]["supplyAssetsUsd"], "oracleType": (m.get("oracle") or {}).get("type"), "feed": f,
                         "kind": kind, "admin": r.get("admin"), "admin_owner": r.get("admin_owner"), "feed_owner": r.get("feed_owner"),
                         "controller": c, "controller_class": classes.get((chain, c)), "unread": r.get("unread"),
                         "admin_set_price": (set_price.get((chain, f)) or (False, None))[0], "price_target": (set_price.get((chain, f)) or (False, None))[1]})

    total = sum(m["state"]["supplyAssetsUsd"] or 0 for m in markets)
    unread = [r for r in rows if r["unread"]]
    print(f"{len(markets)} listed markets >= ${args.min_usd:,.0f} on {len(RPC)} tracked chains, ${total/1e6:,.0f}M supplied; "
          f"{len(targets)} distinct feeds/oracles read, {len({r['feed'] for r in unread})} UNREAD\n")

    by_class = {}
    per_market = {}  # a market is counted once, under its weakest controller
    for r in rows:
        k = r["market"]
        cur = per_market.get(k)
        rank = 0 if r["unread"] else 3 if not r["controller"] else 2 if not weak_controller(r["controller_class"]) else 1
        if cur is None or rank < cur[0]:
            per_market[k] = (rank, r)
    label = {0: "UNREAD", 1: "weakest controller = EOA or Safe threshold<=2", 2: "weakest controller = larger Safe/contract/timelock", 3: "no admin found (not proven immutable)"}
    for rank, r in per_market.values():
        b = by_class.setdefault(rank, [0, 0.0])
        b[0] += 1
        b[1] += r["supplyUsd"] or 0
    print("=== Markets by weakest feed controller ===")
    for rank in sorted(by_class):
        n, s = by_class[rank]
        print(f"  {label[rank]}: {n} markets, ${s/1e6:,.0f}M")

    print("\n=== Top controllers by supplied value (each market counted once per controller) ===")
    for g in concentration(rows)[:15]:
        print(f"  chain {g['chain']} {g['controller']}  [{g['class']}]  {g['markets']} market(s), ${g['supplyUsd']/1e6:,.0f}M" + ("  <-- weak" if weak_controller(g["class"]) else ""))

    total_mk = {r["market"]: r["supplyUsd"] or 0.0 for r in rows}
    print("\n=== Safe committees that control feeds (same threshold and signers, any chain) ===")
    for (k, owners), members in sorted(group_by_signers(safe_sets).items(), key=lambda kv: -path_split(rows, set(kv[1]), 1.0)["all"][1]):
        sp = path_split(rows, set(members), sum(total_mk.values()))
        if sp["all"][0] and (len(members) > 1 or sp["all"][1] >= 1e7):
            print(f"  {k}-of-{len(owners)} Safe on {len(members)} chain(s) {sorted({c for c, _ in members})}: live price path {sp['live'][0]} markets "
                  f"${sp['live'][1]/1e6:,.0f}M ({100*sp['live_share']:.1f}%), backup-only {sp['backup_only'][0]} markets ${sp['backup_only'][1]/1e6:,.0f}M, "
                  f"all {sp['all'][0]} markets ${sp['all'][1]/1e6:,.0f}M ({100*sp['all_share']:.1f}% of ${sum(total_mk.values())/1e6:,.0f}M)")

    posted = {}
    for r in rows:
        if r["admin_set_price"]:
            posted[r["market"]] = r
    print("\n=== Markets whose price is POSTED by a role holder (feed or wrapped feed exposes setRoundData) ===")
    for r in sorted(posted.values(), key=lambda r: -(r["supplyUsd"] or 0)):
        print(f"  chain {r['chain']} {r['pair']}  ${(r['supplyUsd'] or 0)/1e6:,.0f}M  feed {r['feed']} -> price contract {r['price_target']}")
    print(f"  {len(posted)} market(s), ${sum(r['supplyUsd'] or 0 for r in posted.values())/1e6:,.0f}M. Who holds the posting role is NOT read here (a role, not an owner()): see the dated finding.")
    for r in unread[:10]:
        print(f"UNREAD chain {r['chain']} {r['feed']}: {r['unread']}")
    if args.out:
        with open(args.out, "w") as f:
            json.dump({"minUsd": args.min_usd, "rows": rows}, f, indent=1, default=str)
        print(f"rows written to {args.out}")


if __name__ == "__main__":
    main()
