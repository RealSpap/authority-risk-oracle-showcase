#!/usr/bin/env python3
"""Has the code behind any tracked target changed since the last reviewed snapshot?

ADDED 2026-09-21 (scripts/lib/implementation_watch.py explains why). Reads every target tracked by the deployed testnet oracles
(the mainnet addresses they score), fingerprints its code (proxy implementation, beacon implementation, clone implementation, or its
own code hash), and diffs against data/implementation_snapshot.json.

    python3 scripts/check_implementation_changes.py            # compare; exit 1 if a target changed or could not be read
    python3 scripts/check_implementation_changes.py --update   # after reviewing the changes, write the new snapshot
    python3 scripts/check_implementation_changes.py --verify   # also report where each proxy implementation's source is verified

A CHANGED target keeps its authority score but its code moved: read what the new implementation does before trusting the score, then
--update. NEW targets are added by --update; a target that could not be read is never written over a good fingerprint.
For every changed implementation the report says what the new one adds or drops (function selectors, named through the public signature
database), whether the compiler changed, and where its source is verified (Sourcify, Routescan, and Etherscan V2 only if you set
ETHERSCAN_API_KEY yourself). Explorers that sit behind a bot check are never queried; a chain that has one is reported "unknown", not
"unverified" (scripts/lib/code_review.py). Strictly read-only against the chains.
"""
import datetime
import os
import sys

from web3 import Web3

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "lib"))
from lib import code_review  # noqa: E402
from lib.implementation_watch import diff, fingerprint, load_snapshot, save_snapshot  # noqa: E402
from live_target_counts import ORACLES  # noqa: E402

SNAPSHOT = os.path.join(HERE, "..", "data", "implementation_snapshot.json")
# oracle name (live_target_counts.ORACLES) -> the MAINNET RPC its targets live on
MAINNET_RPC = {
    "Robinhood Chain": "https://rpc.mainnet.chain.robinhood.com",
    "Ethereum L1 (Sepolia)": "https://ethereum-rpc.publicnode.com",
    "Arbitrum (Sepolia)": "https://arb1.arbitrum.io/rpc",
    "Base (Sepolia)": "https://mainnet.base.org",
    "Tempo (Moderato)": "https://rpc.tempo.xyz",
    "Plasma": "https://rpc.plasma.to",
    "Monad": "https://rpc.monad.xyz",
    "Hyperliquid (HyperEVM)": "https://rpc.hyperliquid.xyz/evm",
}
CHAIN_ID = {
    "Robinhood Chain": 4663, "Ethereum L1 (Sepolia)": 1, "Arbitrum (Sepolia)": 42161, "Base (Sepolia)": 8453,
    "Tempo (Moderato)": 4217, "Plasma": 9745, "Monad": 143, "Hyperliquid (HyperEVM)": 999,
}
_TRACKED_ABI = [
    {"name": "trackedTargetsCount", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "uint256"}]},
    {"name": "trackedTargets", "type": "function", "stateMutability": "view", "inputs": [{"type": "uint256"}], "outputs": [{"type": "address"}]},
]
_IMPLEMENTATION_ABI = [{"name": "implementation", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "address"}]}]


def _retry(fn, attempts=4):
    import time
    for i in range(attempts):
        try:
            return fn()
        except Exception:
            time.sleep(0.6 * (i + 1))
    return None


def tracked_targets(name, address, rpc):
    """The mainnet addresses one testnet oracle tracks, or None if the oracle could not be read."""
    w3 = Web3(Web3.HTTPProvider(rpc, request_kwargs={"timeout": 30}))
    contract = w3.eth.contract(address=Web3.to_checksum_address(address), abi=_TRACKED_ABI)
    count = _retry(lambda: contract.functions.trackedTargetsCount().call())
    if count is None:
        return None
    out = []
    for i in range(count):
        t = _retry(lambda: contract.functions.trackedTargets(i).call())
        if t is None:
            return None
        out.append(t)
    return out


def live_fingerprints():
    live = {}
    for name, oracle, testnet_rpc in ORACLES:
        rpc = MAINNET_RPC.get(name)
        if rpc is None:
            continue
        targets = tracked_targets(name, oracle, testnet_rpc)
        w3 = Web3(Web3.HTTPProvider(rpc, request_kwargs={"timeout": 30}))
        if targets is None:
            print(f"  [UNREAD oracle] {name}: its tracked targets could not be read")
            live[f"{name}:__oracle__"] = {"kind": "unread"}
            continue

        def get_code(a, w3=w3):
            r = _retry(lambda: bytes(w3.eth.get_code(Web3.to_checksum_address(a))))
            return r

        def get_storage(a, slot, w3=w3):
            return _retry(lambda: bytes(w3.eth.get_storage_at(Web3.to_checksum_address(a), int(slot, 16))))

        def beacon_impl(b, w3=w3):
            c = w3.eth.contract(address=Web3.to_checksum_address(b), abi=_IMPLEMENTATION_ABI)
            r = _retry(lambda: c.functions.implementation().call())
            return r.lower() if r else None

        for t in targets:
            live[f"{name}:{t.lower()}"] = fingerprint(
                t.lower(), get_code, get_storage, beacon_impl, lambda b: "0x" + bytes(Web3.keccak(b)).hex())
    return live


def review_lines(fields, get_code, chain_id, resolve=code_review.resolve_names, verify=code_review.verification):
    """Plain-text lines that say what a changed implementation is: what it adds or drops, and where its source is verified.

    `fields` is one entry of diff()["changed"] ({field: (old, new)}); get_code(address) -> bytes or None."""
    if "implementation" not in fields:
        return []
    old, new = fields["implementation"]
    lines = []
    new_code = get_code(new) if new else None
    old_code = get_code(old) if old else None
    if new_code is None:
        return ["the new implementation's code could not be read"]
    if old_code is None:
        lines.append("the previous implementation had no readable code (the proxy is new, or the old implementation was removed)")
        sel = code_review.selectors(new_code)
        names = resolve(sel)
        lines.append(f"new implementation: {len(new_code)} bytes, {len(sel)} selectors: "
                     + ", ".join((names.get(x) or [x])[0] for x in sorted(sel))[:700])
    else:
        review = code_review.compare(old_code, new_code)
        names = resolve(set(review["added"]) | set(review["removed"]))
        lines.extend(code_review.summarize(review, names))
    results = verify(chain_id, new)
    verdict = code_review.verified_anywhere(results)
    verdict_text = {True: "verified", False: "NOT verified anywhere it can be asked", None: "unknown"}[verdict]
    lines.append(f"source of the new implementation: {verdict_text} ("
                 + "; ".join(f"{r['source']}: {r['status']}" + (f" as {r['name']}" if r.get("name") else "") for r in results) + ")")
    return lines


def _w3_for(name):
    return Web3(Web3.HTTPProvider(MAINNET_RPC[name], request_kwargs={"timeout": 30}))


def main(argv):
    update = "--update" in argv
    snapshot = load_snapshot(SNAPSHOT)
    live = live_fingerprints()
    result = diff(snapshot["targets"], live)
    kinds = {}
    for fp in live.values():
        kinds[fp.get("kind")] = kinds.get(fp.get("kind"), 0) + 1
    print(f"{len(live)} targets fingerprinted ({', '.join(f'{v} {k}' for k, v in sorted(kinds.items()))}); "
          f"snapshot of {snapshot['takenAt'] or 'nothing'}")
    for key, fields in result["changed"].items():
        print(f"  [CHANGED] {key}")
        for field, (old, new) in fields.items():
            print(f"      {field}: {old} -> {new}")
        name = key.rsplit(":", 1)[0]
        w3 = _w3_for(name)
        for line in review_lines(fields, lambda a, w3=w3: _retry(lambda: bytes(w3.eth.get_code(Web3.to_checksum_address(a)))), CHAIN_ID[name]):
            print(f"      {line}")
    if snapshot["takenAt"] is None:
        print(f"  no snapshot yet: {len(result['new'])} targets are new (--update writes the baseline)")
    else:
        for key in result["new"]:
            print(f"  [NEW] {key} ({live[key]['kind']})")
    for key in result["removed"]:
        print(f"  [REMOVED from the oracles] {key}")
    for key in result["unread"]:
        print(f"  [UNREAD] {key}")
    if "--verify" in argv:
        print("source verification of every proxy implementation:")
        tally = {}
        for key, fp in sorted(live.items()):
            impl = fp.get("implementation")
            if not impl:
                continue
            name = key.rsplit(":", 1)[0]
            results = code_review.verification(CHAIN_ID[name], Web3.to_checksum_address(impl))
            verdict = {True: "verified", False: "NOT verified", None: "unknown"}[code_review.verified_anywhere(results)]
            tally[verdict] = tally.get(verdict, 0) + 1
            if verdict != "verified":
                print(f"  [{verdict}] {key} -> {impl}: " + "; ".join(f"{r['source']}: {r['status']}" for r in results))
        print("  " + ", ".join(f"{v} {k}" for k, v in sorted(tally.items())))
    if update:
        merged = dict(snapshot["targets"])
        for key, fp in live.items():
            if fp.get("kind") != "unread":
                merged[key] = fp
        for key in result["removed"]:
            merged.pop(key, None)
        save_snapshot(SNAPSHOT, datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%MZ"), merged)
        print(f"snapshot written: {len(merged)} targets")
        return 1 if result["unread"] else 0
    return 1 if (result["changed"] or result["unread"]) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
