#!/usr/bin/env python3
"""Live check for new Tempo scoring targets. No hardcoded conclusion.

Replaces the pattern refused on 2026-09-20 and again on 2026-09-21, where
"0 new targets" was printed by a script that read nothing.  This one reads,
every time it runs:

  1. the official Tempo token registry `https://tokenlist.tempo.xyz/list/4217`
     (version, timestamp, token count);
  2. the oracle's own `trackedTargets` array on Moderato, so the covered set
     comes from the chain rather than from a file in this repo;
  3. `totalSupply()` / `decimals()` of every registry token that is NOT
     already tracked, on two independent mainnet providers.

Then it applies the re-scout trigger exactly as written in
`chains/tempo/data/scouted_bridged_tokens_2026-09-19.md` section 5:

  * the registry's `version.patch` rising past 34, or the token count
    changing;
  * an untracked token moving "roughly two orders of magnitude past where
    it sits today", i.e. x100 against that document's own dated snapshot
    of every untracked token's supply -- which is why the snapshot is
    carried here, per token, instead of a single global bar.

For context it also prints which untracked tokens sit above the weakest
already-covered independent token by value (cUSD, about 50,337 units on
2026-09-19), and -- for each of those -- resolves its root role holders
live and compares its authority closure with the closures of the tracked
targets, instead of repeating the 2026-09-19 note's structural argument on
trust.

Exit code 0 means "no new target"; exit code 2 means the trigger fired and
a human re-scout is owed.  Usage:

    python3 chains/tempo/scripts/check_new_targets_live.py
"""

import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

TOKENLIST_URL = "https://tokenlist.tempo.xyz/list/4217"
MAINNET_RPCS = ["https://rpc.tempo.xyz", "https://tempo.drpc.org"]
MODERATO_RPC = "https://rpc.moderato.tempo.xyz"
ORACLE = "0x50840a7667baEa9D05ad4ae3dCeb384724b58720"

# Trigger constants from data/scouted_bridged_tokens_2026-09-19.md section 5.
BASELINE_TOKEN_COUNT = 34
BASELINE_VERSION = (1, 0, 34)
# Weakest already-covered independent token by supply on 2026-09-19 (cUSD,
# 50,337.23 units) -- printed as context, not used as the trigger.
WEAKEST_COVERED_SUPPLY = 50_337.23
# x100 = the "roughly two orders of magnitude" of the documented trigger.
TRIGGER_FACTOR = 100
# Dated per-token snapshot from that same document's section 3 (2026-09-19),
# the baseline the "two orders of magnitude" is measured against.
SNAPSHOT_2026_09_19 = {
    "senpathUSDE": 116_422.5, "BRLA": 50_100.0, "GBPA": 50_001.0, "stcUSD": 23_869.6,
    "USD1": 1_119.9, "goUSD": 1_117.0, "syrupUSDC": 886.1, "USDY": 468.9, "reUSD": 233.7,
    "MACH": 156.2, "CADD": 99.0, "SBC": 96.3, "frxUSD": 44.5, "EURAU": 41.0, "USDe": 22.3,
    "sUSDe": 5.6, "YLDS": 5.5, "wYLDS": 5.1, "siUSD": 4.0, "wsrUSD": 3.9, "rUSD": 0.00001,
    "iUSD": 0.0, "CHFAU": 0.0, "SEKAU": 0.0, "GUSD": 0.0,
}

SEL_TOTAL_SUPPLY = "0x18160ddd"   # totalSupply()
SEL_DECIMALS = "0x313ce567"       # decimals()
SEL_COUNT = "0x835e2172"          # trackedTargetsCount()
SEL_TRACKED = "0x9481e5e0"        # trackedTargets(uint256)


def _load_audit_module():
    """Load the sibling non-circular audit module for its live authority
    readers (keccak, RPC, R1/R2 resolution). This is NOT the published
    scorer -- `methodology_test.py`/`scorers.py` are never imported here."""
    import importlib.util
    import os
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "audit_rotation_index.py")
    spec = importlib.util.spec_from_file_location("aro_audit", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def http_json(url):
    r = subprocess.run(["curl", "-s", "-m", "40", url], capture_output=True, text=True)
    return json.loads(r.stdout)


def rpc(url, method, params):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
    for _ in range(4):
        r = subprocess.run(["curl", "-s", "-m", "60", "-X", "POST",
                            "-H", "Content-Type: application/json", "-d", body, url],
                           capture_output=True, text=True)
        try:
            out = json.loads(r.stdout)
        except json.JSONDecodeError:
            continue
        if "error" in out:
            if out["error"].get("code") == 3:
                return None
            continue
        return out["result"]
    raise RuntimeError(f"{url} {method} failed")


def call(url, to, data):
    return rpc(url, "eth_call", [{"to": to, "data": data}, "latest"])


def main():
    print("== 1. official Tempo token registry, read live ==")
    tl = http_json(TOKENLIST_URL)
    v = tl["version"]
    ver = (v["major"], v["minor"], v["patch"])
    print(f"   {TOKENLIST_URL}")
    print(f"   name={tl['name']!r} version={ver[0]}.{ver[1]}.{ver[2]} timestamp={tl['timestamp']}")
    print(f"   tokens listed: {len(tl['tokens'])}")

    print("\n== 2. covered set, read from the oracle on Moderato (not from this repo) ==")
    cnt = int(call(MODERATO_RPC, ORACLE, SEL_COUNT), 16)
    tracked = []
    for i in range(cnt):
        w = call(MODERATO_RPC, ORACLE, SEL_TRACKED + hex(i)[2:].rjust(64, "0"))
        tracked.append("0x" + w[-40:])
    tracked_set = {a.lower() for a in tracked}
    print(f"   oracle {ORACLE} trackedTargetsCount() = {cnt}")
    print(f"   tracked TIP-20 addresses among them: "
          f"{len([a for a in tracked_set if a.startswith('0x20c0')])}")

    untracked = [t for t in tl["tokens"] if t["address"].lower() not in tracked_set]
    print(f"   registry tokens NOT tracked by the oracle: {len(untracked)}")

    print("\n== 3. live totalSupply() of every untracked token, on two providers ==")

    def supply(tok):
        a = tok["address"]
        outs = [call(u, a, SEL_TOTAL_SUPPLY) for u in MAINNET_RPCS]
        decs = [call(u, a, SEL_DECIMALS) for u in MAINNET_RPCS]
        vals = [int(o, 16) for o in outs if o]
        dec = int([d for d in decs if d][0], 16)
        agree = len(set(vals)) == 1
        return tok["symbol"], a, vals[0] / 10 ** dec, agree, [x / 10 ** dec for x in vals]

    rows = []
    with ThreadPoolExecutor(6) as ex:
        for r in ex.map(supply, untracked):
            rows.append(r)
    rows.sort(key=lambda r: -r[2])
    over_bar, moved = [], []
    for sym, addr, val, agree, vals in rows:
        flag = "" if agree else f"  (providers differ: {vals} -- live supply, re-read)"
        base = SNAPSHOT_2026_09_19.get(sym)
        if base is None:
            ratio_txt = "  [NOT IN THE 2026-09-19 SNAPSHOT]"
            moved.append((sym, addr, val, None))
        else:
            ratio = (val / base) if base > 0 else (float("inf") if val > 0 else 1.0)
            ratio_txt = f"  (2026-09-19: {base:,.4f}, x{ratio:,.2f})"
            if ratio >= TRIGGER_FACTOR:
                moved.append((sym, addr, val, ratio))
        mark = "  <== above the weakest covered token" if val > WEAKEST_COVERED_SUPPLY else ""
        print(f"   {sym:<12} {addr}  totalSupply={val:>18,.4f}{mark}{ratio_txt}{flag}")
        if val > WEAKEST_COVERED_SUPPLY:
            over_bar.append((sym, addr, val))

    print("\n== 3b. live authority read on every untracked token above that bar ==")
    audit = _load_audit_module()
    tracked_closures = {}
    for sym, addr, val in over_bar:
        head = int(audit.rpc(audit.LOG_RPC, "eth_blockNumber", []), 16)
        _, lg = audit.scan_role_logs([addr], head)
        cands = sorted({audit.as_addr(l["topics"][2]) for l in lg})
        holders = audit.role_holders(addr, cands, audit.ROOT_ROLE_NAMES)
        root = sorted({a for r in audit.ROOT_ROLE_NAMES for a in holders[r]})
        print(f"   {sym} {addr}")
        print(f"     role holders now: {holders}")
        print(f"     root-control set (R1): {root or '(empty)'}")
        clo = set()
        for a in root:
            k = audit.resolve_key(a)
            print(f"     {a} -> {k['kind']} k={k['k']} n={k['n']}")
            clo |= audit.authority_closure(a)
        overlaps = []
        for t in tracked:
            if t.lower() not in tracked_closures:
                tracked_closures[t.lower()] = audit.authority_closure(t)
            if clo & tracked_closures[t.lower()]:
                overlaps.append(t)
        print(f"     authority closure shares an address with tracked target(s): {overlaps or 'NONE'}")

    print("\n== 4. re-scout trigger (data/scouted_bridged_tokens_2026-09-19.md section 5) ==")
    fired = []
    print(f"   registry version {ver} vs baseline {BASELINE_VERSION}: "
          f"{'CHANGED' if ver != BASELINE_VERSION else 'unchanged'}")
    if ver != BASELINE_VERSION:
        fired.append(f"registry version moved {BASELINE_VERSION} -> {ver}")
    print(f"   token count {len(tl['tokens'])} vs baseline {BASELINE_TOKEN_COUNT}: "
          f"{'CHANGED' if len(tl['tokens']) != BASELINE_TOKEN_COUNT else 'unchanged'}")
    if len(tl["tokens"]) != BASELINE_TOKEN_COUNT:
        fired.append(f"token count moved {BASELINE_TOKEN_COUNT} -> {len(tl['tokens'])}")
    print(f"   untracked tokens up x{TRIGGER_FACTOR} or more since the 2026-09-19 snapshot: "
          f"{[m[0] for m in moved] or 'none'}")
    for sym, addr, val, ratio in moved:
        fired.append(f"{sym} ({addr}) at {val:,.4f}: " +
                     (f"x{ratio:,.2f} since 2026-09-19" if ratio else "absent from the 2026-09-19 snapshot"))
    print(f"   (context, not a trigger) untracked tokens above the weakest covered token "
          f"({WEAKEST_COVERED_SUPPLY:,.2f}): {[s for s, _, _ in over_bar] or 'none'}")

    print("\n== VERDICT ==")
    if fired:
        print("   RE-SCOUT OWED:")
        for f in fired:
            print(f"     - {f}")
        sys.exit(2)
    print(f"   0 new targets. Registry unchanged at {ver[0]}.{ver[1]}.{ver[2]} / {len(tl['tokens'])} tokens,")
    print(f"   and none of the {len(untracked)} untracked tokens moved x{TRIGGER_FACTOR} since 2026-09-19.")
    print("   See section 3b above for what the live authority read says about the tokens that")
    print("   merely sit above the weakest covered token -- that is context for a future scouting")
    print("   pass, not a target this maintenance run may add on its own.")
    sys.exit(0)


if __name__ == "__main__":
    main()
