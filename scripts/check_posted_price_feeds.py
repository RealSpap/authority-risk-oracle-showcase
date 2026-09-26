#!/usr/bin/env python3
"""Who POSTS the price of the Morpho markets whose feed is written by a role holder, and how far can they move it? (read-only)

check_morpho_market_oracles.py flags every listed market whose feed, or the feed it wraps through underlyingFeed(), exposes
setRoundData(int256): the price is posted, not observed. This opens each such price contract and reads, live:
  - the posting bounds (minAnswer, maxAnswer, maxAnswerDeviation) against the last answer, so the headroom is a number;
  - the access-control contract, the posting role (feedAdminRole) and its current holders (RoleGranted/RoleRevoked replay
    matched against live hasRole), and who holds DEFAULT_ADMIN_ROLE there (who can grant the posting role);
  - the ProxyAdmin owner of the price contract and its timelock delay, if any.

    python3 scripts/check_posted_price_feeds.py [--min-usd 1e6] [--out data/posted_price_feeds_2026-09-26.json]

Holders are replayed from logs on Ethereum (Tenderly's public gateway), Robinhood Chain (its RPC) and Base (Blockscout's logs API, which
rate-limits hard). Any other chain, or a log read that fails, is UNREAD for that field: never "no holder". Disclosed only; no score reads it.
"""
import argparse
import json
import os
import subprocess
import sys
import time

from web3 import Web3

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "lib"))
import check_morpho_market_oracles as census  # noqa: E402
from lib.market_oracles import market_feeds  # noqa: E402
from lib.web3_utils import EIP1967_ADMIN_SLOT, RpcUnavailable, call_raw, get_w3, read_address_getter, read_slot_as_address  # noqa: E402

TENDERLY = {1: "https://gateway.tenderly.co/public/mainnet"}
BLOCKSCOUT = {8453: "base.blockscout.com"}
FULL_RANGE_RPC = {4663: census.RPC[4663]}  # Robinhood Chain answers a full-history getLogs
GRANTED = "0x" + Web3.keccak(text="RoleGranted(bytes32,address,address)").hex().removeprefix("0x")
REVOKED = "0x" + Web3.keccak(text="RoleRevoked(bytes32,address,address)").hex().removeprefix("0x")
ZERO_ROLE = "0x" + "00" * 32
_INT = lambda name: [{"name": name, "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "int256"}]}]  # noqa: E731
_B32 = [{"name": "feedAdminRole", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "bytes32"}]}]
_HAS_ROLE = [{"name": "hasRole", "type": "function", "stateMutability": "view", "inputs": [{"type": "bytes32"}, {"type": "address"}], "outputs": [{"type": "bool"}]}]
_MIN_DELAY = [{"name": "getMinDelay", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "uint256"}]}]


def role_holders(w3, chain, access_control, role):
    """Current holders of `role` on `access_control`: replay of RoleGranted/RoleRevoked matched to live hasRole. Raises LookupError when the chain's
    logs cannot be read here."""
    events = []
    if chain in BLOCKSCOUT:
        for topic in (GRANTED, REVOKED):
            url = (f"https://{BLOCKSCOUT[chain]}/api?module=logs&action=getLogs&fromBlock=0&toBlock=latest&address={access_control}"
                   f"&topic0={topic}&topic1={role}&topic0_1_opr=and")
            d = json.loads(subprocess.run(["curl", "-s", "-m", "60", "-A", "Mozilla/5.0", url], capture_output=True, text=True).stdout or "{}")
            if not isinstance(d.get("result"), list):
                raise LookupError(f"Blockscout logs API: {d.get('message')}")
            events += [(int(l["blockNumber"], 16), int(l["logIndex"] or "0x0", 16), l["topics"][0] == topic and topic == GRANTED, "0x" + l["topics"][2][-40:]) for l in d["result"]]
    elif chain in TENDERLY or chain in FULL_RANGE_RPC:
        lw3 = get_w3(TENDERLY.get(chain) or FULL_RANGE_RPC[chain])
        for lg in lw3.eth.get_logs({"address": Web3.to_checksum_address(access_control), "topics": [[GRANTED, REVOKED], role], "fromBlock": 0, "toBlock": lw3.eth.block_number}):
            first = lg["topics"][0].hex().removeprefix("0x")
            events.append((lg["blockNumber"], lg["logIndex"], first == GRANTED.removeprefix("0x"), "0x" + lg["topics"][2].hex()[-40:]))
    else:
        raise LookupError("no full-history log source for this chain")
    state = {}
    for _, _, granted, acct in sorted(events):
        state[Web3.to_checksum_address(acct)] = granted
    out = []
    for acct in state:
        live = call_raw(w3, access_control, _HAS_ROLE, "hasRole", bytes.fromhex(role[2:]), acct)
        if live:
            out.append({"address": acct, "class": census.classify(w3, acct)[0]})
    return out


def inspect(chain, w3, target):
    r = {"chain": chain, "price_contract": target}
    for name in ("lastAnswer", "minAnswer", "maxAnswer", "maxAnswerDeviation", "lastTimestamp", "latestRound"):
        r[name] = call_raw(w3, target, _INT(name), name)
    if r["lastAnswer"]:
        r["headroom_up_pct"] = (r["maxAnswer"] / r["lastAnswer"] - 1) * 100 if r["maxAnswer"] is not None else None
        r["headroom_down_pct"] = (r["minAnswer"] / r["lastAnswer"] - 1) * 100 if r["minAnswer"] is not None else None
    ac = read_address_getter(w3, target, "accessControl")
    role = call_raw(w3, target, _B32, "feedAdminRole")
    r["access_control"] = ac
    r["role"] = "0x" + bytes(role).hex() if role else None
    admin = read_slot_as_address(w3, target, EIP1967_ADMIN_SLOT)
    if int(admin, 16):
        owner = read_address_getter(w3, admin, "owner")
        r["proxy_admin_owner"] = owner
        delay = call_raw(w3, owner, _MIN_DELAY, "getMinDelay") if owner else None
        r["proxy_admin_delay_s"] = delay
    for label, rl in (("posting_role_holders", r["role"]), ("default_admin_holders", ZERO_ROLE)):
        try:
            r[label] = role_holders(w3, chain, ac, rl) if ac and rl else None
        except (LookupError, RpcUnavailable) as e:
            r[label] = f"UNREAD ({e})"
    return r


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--min-usd", type=float, default=1e6)
    ap.add_argument("--out")
    args = ap.parse_args()

    markets = [m for m in census.fetch_markets(args.min_usd) if m["chain"]["id"] in census.RPC]
    w3 = {c: get_w3(u) for c, u in census.RPC.items()}
    targets = {}  # (chain, price contract) -> [(pair, supply)]
    for m in markets:
        chain = m["chain"]["id"]
        feeds = market_feeds(m) or [f for f, _ in census.expand_custom(w3[chain], m["oracle"]["address"])] if (m.get("oracle") or {}).get("address") else []
        for f in feeds:
            try:
                posted, tgt = census.admin_set_price(w3[chain], f)
            except RpcUnavailable:
                continue
            if posted:
                targets.setdefault((chain, tgt), []).append((f"{(m['collateralAsset'] or {}).get('symbol')}/{m['loanAsset']['symbol']}", m["state"]["supplyAssetsUsd"] or 0))
    results = []
    for (chain, tgt), mk in sorted(targets.items(), key=lambda kv: -sum(u for _, u in kv[1])):
        r = inspect(chain, w3[chain], tgt)
        r["markets"] = [{"pair": p, "supplyUsd": u} for p, u in mk]
        results.append(r)
        up, dn = r.get("headroom_up_pct"), r.get("headroom_down_pct")
        print(f"chain {chain} {tgt}: {', '.join(p for p, _ in mk)} (${sum(u for _, u in mk)/1e6:,.0f}M)")
        print(f"    last {r['lastAnswer']} at {time.strftime('%Y-%m-%d %H:%M', time.gmtime(r['lastTimestamp'])) + 'Z' if r['lastTimestamp'] else '?'}, bounds [{r['minAnswer']}, {r['maxAnswer']}]"
              + (f", headroom {dn:+.0f}% / {up:+.0f}%" if up is not None and dn is not None else "") + f", max deviation {r['maxAnswerDeviation']} (setRoundDataSafe only)")
        print(f"    posting role holders: {r['posting_role_holders']}")
        print(f"    DEFAULT_ADMIN holders: {r['default_admin_holders']}")
        print(f"    ProxyAdmin owner {r.get('proxy_admin_owner')}, timelock delay {r.get('proxy_admin_delay_s')}")
    if args.out:
        with open(args.out, "w") as f:
            json.dump(results, f, indent=1, default=str)


if __name__ == "__main__":
    main()
