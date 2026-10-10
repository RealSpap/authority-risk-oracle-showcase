#!/usr/bin/env python3
"""What each queued or recent EVM timelock operation IS: watch/pending_ops.json gains, on every non-Squads operation, a `signature`
(the function name, from a table of authority selectors checked by keccak, else the public signature database, cached in
watch/selectors.json) and a `decoded` kind: upgrade, authority change, pause, nested timelock, cross-chain message, parameter
change, value transfer or empty call, unknown. The review queue, the feeds and the calibration read the kind.

    python3 scripts/classify_ops.py --pending watch/pending_ops.json --cache watch/selectors.json
"""
import argparse, json, os, re, time, urllib.request

KNOWN = {"0x2f2ff15d": "grantRole(bytes32,address)", "0xd547741f": "revokeRole(bytes32,address)", "0x36568abe": "renounceRole(bytes32,address)", "0xf2fde38b": "transferOwnership(address)", "0x3659cfe6": "upgradeTo(address)", "0x4f1ef286": "upgradeToAndCall(address,bytes)",
         "0x99a88ec4": "upgrade(address,address)", "0x9623609d": "upgradeAndCall(address,address,bytes)", "0x8f283970": "changeAdmin(address)", "0x7eff275e": "changeProxyAdmin(address,address)", "0x13af4035": "setOwner(address)", "0x704b6c02": "setAdmin(address)", "0x4dd18bf5": "setPendingAdmin(address)",
         "0x79ba5097": "acceptOwnership()", "0x8456cb59": "pause()", "0x3f4ba83a": "unpause()", "0x64d62353": "updateDelay(uint256)", "0x8a0dac4a": "setGuardian(address)", "0x0d582f13": "addOwnerWithThreshold(address,uint256)", "0xf8dc5dd9": "removeOwner(address,address,uint256)",
         "0x694e80c3": "changeThreshold(uint256)", "0x610b5925": "enableModule(address)", "0xe009cfde": "disableModule(address,address)", "0xe19a9dd9": "setGuard(address)", "0xd784d426": "setImplementation(address)", "0x01d5062a": "schedule(address,uint256,bytes,bytes32,bytes32,uint256)",
         "0x8f2a0bb0": "scheduleBatch(address[],uint256[],bytes[],bytes32,bytes32,uint256)", "0x134008d3": "execute(address,uint256,bytes,bytes32,bytes32)", "0xe177246e": "setDelay(uint256)", "0x75829def": "transferAdmin(address)", "0x2d88af4a": "setPauser(address)", "0xba29482f": "setMinDelay(uint256)"}   # each checked by keccak on 2026-10-10


def kind_of(name):
    n = (name or "").split("(")[0]
    if not n: return "value transfer or empty call"
    if re.search(r"upgrade|implementation|changeAdmin|changeProxyAdmin", n, re.I): return "upgrade"
    if re.search(r"role|owner|admin|guardian|threshold|module|guard|delay|pauser|authority|operator|minter|sentinel", n, re.I): return "authority change"
    if re.search(r"pause", n, re.I): return "pause"
    if re.search(r"^(schedule|execute|cancel)", n, re.I): return "nested timelock"
    if re.search(r"sendMessage|relay|bridge|peer", n, re.I): return "cross-chain message"
    return "parameter change"


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--pending", default="watch/pending_ops.json"); ap.add_argument("--cache", default="watch/selectors.json"); a = ap.parse_args()
    pend = json.load(open(a.pending)); cache = (json.load(open(a.cache)) if os.path.exists(a.cache) else {}).get("selectors", {})
    ops = [op for r in pend.get("results", []) if r.get("family") != "squads" for st in ("pending", "recent") for op in r.get(st, [])]
    unknown = sorted({op.get("selector") for op in ops if op.get("selector") and op["selector"] != "0x" and op["selector"] not in KNOWN and op["selector"] not in cache and not op.get("signature")})
    looked = 0
    if unknown:
        try:
            r = json.loads(urllib.request.urlopen(urllib.request.Request("https://api.openchain.xyz/signature-database/v1/lookup?function=%s&filter=true" % ",".join(unknown[:50]), headers={"User-Agent": "curl/8"}), timeout=20).read())
            for sel, names in (r.get("result", {}).get("function") or {}).items(): cache[sel] = (names or [{}])[0].get("name") if names else None; looked += 1
        except Exception: pass  # noqa: BLE001 -- the database not answering leaves the selector unknown, never a wrong name
        if looked: json.dump({"what": "selector -> function name, from the public signature database (openchain), cached; written by scripts/classify_ops.py", "selectors": cache}, open(a.cache + ".tmp", "w"), indent=1); os.replace(a.cache + ".tmp", a.cache)
    counts = {}
    for op in ops:
        sel = op.get("selector") or "0x"; name = op.get("signature") or KNOWN.get(sel) or cache.get(sel)
        if name: op["signature"] = name
        op["decoded"] = kind_of(name) if (name or sel == "0x") else "unknown"; counts[op["decoded"]] = counts.get(op["decoded"], 0) + 1
    tmp = a.pending + ".tmp"; json.dump(pend, open(tmp, "w"), indent=1); os.replace(tmp, a.pending)
    print("ops classified: %d EVM operation(s): %s; %d selector(s) looked up this run" % (len(ops), ", ".join("%s %d" % kv for kv in sorted(counts.items(), key=lambda kv: -kv[1])), looked))


if __name__ == "__main__":
    main()
