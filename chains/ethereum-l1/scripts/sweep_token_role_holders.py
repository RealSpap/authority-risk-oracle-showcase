#!/usr/bin/env python3
"""Read-only: who actually holds the AccessControl roles of the tokens a lender takes as collateral or deposit.
    python3 chains/ethereum-l1/scripts/sweep_token_role_holders.py [--from-dump asset_auth.json] [--token 1:0x...] [--dump rows.json]
sweep_asset_authority.py finds, by function name, which tokens can freeze, seize, pause or be upgraded, and reads the plain getters (owner(), blacklister(), ...).
A token built on OpenZeppelin AccessControl has no such getter: its holders are only in the RoleGranted and RoleRevoked events. This replays those events
(one eth_getLogs call to a public gateway), names each role from the bytes32 constants of the verified ABI (PAUSER_ROLE, ...), then CHECKS every replayed holder on chain with
hasRole(role, account), so a truncated or misordered replay shows up as a mismatch instead of a wrong answer. Each holder is classed as a plain account, a
Safe (t-of-n with its signers), a legacy multisig, a timelock, or another contract (with its owner() when it has one). RoleAdminChanged is not replayed: a role
whose admin was changed keeps its holders here. Roles held by a contract that is not a Safe are named, not resolved. It reads capability and holders, not use.
Nothing is sent, no key. Without --token it takes the tokens of a sweep_asset_authority.py dump that use AccessControl or whose controllers were not read."""
import argparse, collections, functools, json, re, subprocess, sys, threading, time
from concurrent.futures import ThreadPoolExecutor
from web3 import Web3
ap = argparse.ArgumentParser(); ap.add_argument("--from-dump", default=None); ap.add_argument("--token", action="append", default=[]); ap.add_argument("--dump", default=None); ARGS = ap.parse_args()
RPC = {1: "https://ethereum-rpc.publicnode.com", 8453: "https://base-rpc.publicnode.com", 42161: "https://arbitrum-one-rpc.publicnode.com", 10: "https://optimism-rpc.publicnode.com", 137: "https://polygon-bor-rpc.publicnode.com"}
BLOCKSCOUT = {1: "eth.blockscout.com", 8453: "base.blockscout.com", 42161: "arbitrum.blockscout.com", 10: "optimism.blockscout.com", 137: "polygon.blockscout.com"}
LOGS_RPC = {1: "https://gateway.tenderly.co/public/mainnet", 8453: "https://gateway.tenderly.co/public/base", 42161: "https://gateway.tenderly.co/public/arbitrum", 10: "https://gateway.tenderly.co/public/optimism", 137: "https://gateway.tenderly.co/public/polygon"}
SLOTS = {"EIP-1967 admin": "0xb53127684a568b3173ae13b9f8a6016e243e63b6e8ee1178d6a717850b5d6103", "ZeppelinOS admin": "0x10d6a54a4754c8869d6886b5f5d7fbfa5b4522237ea5c60d11bc4e7a1ff9390b"}
GRANTED = "0x2f8788117e7eff1d82e926ec794901d17c78024a50270940304540a733656f0d"; REVOKED = "0xf6391f5c32d9c69d2a47ea670b442974b53935d1edc7fd64eb21e047a839171b"
FAILS = collections.Counter()
COMMON_ROLES = ["MINTER_ROLE", "BURNER_ROLE", "PAUSER_ROLE", "UNPAUSER_ROLE", "UPGRADER_ROLE", "BLACKLISTER_ROLE", "BLACKLIST_ROLE", "BLACKLIST_MANAGER_ROLE", "FREEZER_ROLE", "FREEZE_ROLE",
                "FREEZE_ADMIN_ROLE", "WIPER_ROLE", "SEIZER_ROLE", "COMPLIANCE_ROLE", "COMPLIANCE_OFFICER_ROLE", "KYC_ROLE", "WHITELIST_ROLE", "WHITELISTER_ROLE", "ALLOWLIST_ROLE", "TRANSFER_AGENT_ROLE",
                "AGENT_ROLE", "OPERATOR_ROLE", "MANAGER_ROLE", "ADMIN_ROLE", "GOVERNANCE_ROLE", "GUARDIAN_ROLE", "ORACLE_ROLE", "PRICE_UPDATER_ROLE", "REWARDS_ADMIN_ROLE", "MINTER_ADMIN_ROLE", "PROPOSER_ROLE",
                "EXECUTOR_ROLE", "CANCELLER_ROLE", "TIMELOCK_ADMIN_ROLE", "SUPPLY_CONTROLLER_ROLE", "ASSET_PROTECTION_ROLE", "RESCUER_ROLE", "CONTROLLER_ROLE", "ISSUER_ROLE", "BRIDGE_ROLE", "CCIP_ADMIN_ROLE"]
def curl(url, body=None):
    cmd = ["curl", "-s", "-m", "45", "-A", "Mozilla/5.0"] + (["-X", "POST", "-H", "content-type: application/json", "--data", json.dumps(body)] if body else []) + [url]
    for a in range(4):
        try:
            out = subprocess.run(cmd, capture_output=True, text=True).stdout
            if out.strip(): return out
        except Exception: pass
        time.sleep(1.5 * (a + 1))
    return None
GATE = threading.Semaphore(6)   # at most 6 node calls at once: the public nodes answer a burst with a rate-limit error
RATE = re.compile(r"rate|limit|too many|429|capacity|timeout|timed out|busy|try again|unavailable|overload", re.I)
def rpc(ch, m, p):
    """Result of a node call, or None. None means either a genuine revert (the function does not exist) or a failure that survived 6 tries; the second case is
    counted in FAILS and printed at the end, because a failed read must never be taken for an absent function or a zero."""
    for att in range(6):
        with GATE: out = curl(RPC[ch], {"jsonrpc": "2.0", "id": 1, "method": m, "params": p})
        try: j = json.loads(out)
        except Exception: j = {}
        if j.get("result") is not None: return j["result"]
        err = j.get("error")
        if err and not RATE.search(json.dumps(err)): return None   # a genuine answer: revert or unknown method
        time.sleep(1.5 * (att + 1))
    FAILS[ch] += 1; return None
sel = lambda s: "0x" + bytes(Web3.keccak(text=s))[:4].hex()
def call(ch, to, sig, arg=""): return rpc(ch, "eth_call", [{"to": to, "data": sel(sig) + arg}, "latest"])
def addr(h): return Web3.to_checksum_address("0x" + h[-40:]) if h and len(h) >= 42 and int(h, 16) else None
def ok(h): return bool(h) and h != "0x"
def code_class(ch, x):
    c = rpc(ch, "eth_getCode", [x, "latest"])
    return "unread" if c is None else ("plain account" if c == "0x" else "contract")
@functools.lru_cache(maxsize=None)
def cname(ch, a):
    """Verified contract name (and implementation name) from Blockscout's v2 API, which has a far larger quota than its logs API."""
    for att in range(3):
        try:
            d = json.loads(curl(f"https://{BLOCKSCOUT[ch]}/api/v2/smart-contracts/{a}") or "{}")
            if "is_verified" in d or d.get("message") == "Not found":
                im = (d.get("implementations") or [{}])[0].get("name")
                return (d.get("name") or "unverified") + (f" -> {im}" if im else "")
        except Exception: pass
        time.sleep(2.0 * (att + 1))
    return "name not read"
@functools.lru_cache(maxsize=None)
def kind(ch, a, depth=0):
    code = rpc(ch, "eth_getCode", [a, "latest"])
    if code is None: return "unread (node did not answer)"
    if code == "0x": return "plain account"
    t, o = call(ch, a, "getThreshold()"), call(ch, a, "getOwners()")
    if ok(t) and ok(o) and len(o) > 130:
        h = o[2:]; n = int(h[64:128], 16); return f"Safe {int(t, 16)}-of-{n} signers {sorted('0x' + h[128 + 64 * i + 24: 128 + 64 * (i + 1)] for i in range(n))}"
    r = call(ch, a, "required()")
    if ok(r) and ok(o) and len(o) > 130:
        h = o[2:]; n = int(h[64:128], 16); ks = collections.Counter(code_class(ch, "0x" + h[128 + 64 * i + 24: 128 + 64 * (i + 1)]) for i in range(n))
        return f"legacy multisig {int(r, 16)}-of-{n} owners ({dict(ks)})"
    q, sg = call(ch, a, "quorum()"), call(ch, a, "signers()")
    if ok(q) and ok(sg) and len(sg) > 130:   # weighted multisig (Ripple's "MultiSign"): each signer has a weight, the quorum is a sum of weights
        h = sg[2:]; n = int(h[64:128], 16); sigs = ["0x" + h[128 + 64 * i + 24: 128 + 64 * (i + 1)] for i in range(n)]
        wr = [call(ch, a, "signerWeight(address)", x[2:].rjust(64, "0")) for x in sigs]
        if any(not ok(x) for x in wr): return f"weighted multisig quorum {int(q, 16)}, {n} signers, WEIGHTS NOT READ (a node call failed)"
        w = [int(x, 16) for x in wr]; need, tot = 0, 0
        for x in sorted(w, reverse=True):
            if tot >= int(q, 16): break
            tot += x; need += 1
        ks = collections.Counter(code_class(ch, x) for x in sigs)
        return f"weighted multisig quorum {int(q, 16)} of total weight {sum(w)}, {n} signers ({dict(ks)}), {need} signers are enough, signers {sorted(sigs)}"
    d = call(ch, a, "getMinDelay()")
    if ok(d): return f"timelock (min delay {int(d, 16)} s)"
    ow = addr(call(ch, a, "owner()")) if depth < 2 else None
    return f"contract {cname(ch, a)} ({(len(code) - 2) // 2} B)" + (f", owner() = {ow}: {kind(ch, ow, depth + 1)}" if ow else "")
def abi_of(ch, a):
    d = curl(f"https://{BLOCKSCOUT[ch]}/api/v2/smart-contracts/{a}")
    try: d = json.loads(d)
    except Exception: return []
    abis = [d.get("abi") or []]
    for im in (d.get("implementations") or [])[:1]:
        ia = im.get("address") or im.get("address_hash")
        if ia:
            try: abis.append(json.loads(curl(f"https://{BLOCKSCOUT[ch]}/api/v2/smart-contracts/{ia}") or "{}").get("abi") or [])
            except Exception: pass
    return [x for ab in abis for x in ab]
def logs(ch, a):
    """Returns (events, complete) for RoleGranted and RoleRevoked over the whole history, in one eth_getLogs call to a public gateway that allows the full range
    (most free nodes refuse it: publicnode wants a key, drpc caps at 10 000 blocks, Blockscout's logs API allows 10 calls per ~40 minutes). An error is retried, then
    reported as not read; it is never taken for an empty history. A result of 10 000 or more is flagged as possibly cut."""
    for att in range(5):
        out = curl(LOGS_RPC[ch], {"jsonrpc": "2.0", "id": 1, "method": "eth_getLogs", "params": [{"address": a, "fromBlock": "0x0", "toBlock": "latest", "topics": [[GRANTED, REVOKED]]}]})
        try: j = json.loads(out)
        except Exception: j = {}
        if isinstance(j.get("result"), list): return j["result"], len(j["result"]) < 10000
        time.sleep(2.0 * (att + 1))
    return [], False
def analyse(ch, a):
    a = Web3.to_checksum_address(a); abi = abi_of(ch, a)
    names = {"0x" + "00" * 32: "DEFAULT_ADMIN_ROLE"}
    names.update({"0x" + bytes(Web3.keccak(text=n)).hex(): n + "*" for n in COMMON_ROLES})   # * = named by hashing a common role name, not read from the ABI
    for x in abi:
        if x.get("type") == "function" and not x.get("inputs") and x.get("outputs") and x["outputs"][0].get("type") == "bytes32" and x["name"].upper().endswith("ROLE"):
            v = call(ch, a, x["name"] + "()")
            if ok(v): names[v] = x["name"]
    ev, complete = logs(ch, a)
    ev = sorted([dict(l, _rev=l["topics"][0].lower() == REVOKED) for l in ev], key=lambda l: (int(l["blockNumber"], 16), int(l["logIndex"], 16)))
    held = set()
    for l in ev:
        role, acct = l["topics"][1], "0x" + l["topics"][2][-40:]
        (held.discard if l.get("_rev") else held.add)((role, acct))
    holders, mismatches, unverified = collections.defaultdict(list), 0, 0
    for role, acct in sorted(held):
        v = call(ch, a, "hasRole(bytes32,address)", role[2:] + acct[2:].rjust(64, "0"))
        if not ok(v): unverified += 1; holders[role].append(Web3.to_checksum_address(acct)); continue
        if int(v, 16): holders[role].append(Web3.to_checksum_address(acct))
        else: mismatches += 1
    fn = sorted({x["name"] for x in abi if x.get("type") == "function" and x.get("stateMutability") not in ("view", "pure")})
    up = {}
    for sn, slot in SLOTS.items():
        v = rpc(ch, "eth_getStorageAt", [a, slot, "latest"])
        if ok(v) and int(v, 16): x = Web3.to_checksum_address("0x" + v[-40:]); up[sn] = (x, kind(ch, x))
    ow = addr(call(ch, a, "owner()")); own = (ow, kind(ch, ow)) if ow else None
    sy = call(ch, a, "symbol()")
    try: sym = bytes.fromhex(sy[130:130 + 2 * int(sy[66:130], 16)]).decode() if ok(sy) and len(sy) > 130 else (bytes.fromhex(sy[2:66]).rstrip(b"\0").decode() if ok(sy) else "?")
    except Exception: sym = "?"
    with ThreadPoolExecutor(4) as ex: kinds = dict(zip([h for hs in holders.values() for h in hs], ex.map(lambda h: kind(ch, h), [h for hs in holders.values() for h in hs])))
    print(f"  read {sym} on chain {ch}: {len(ev)} events, {sum(len(v) for v in holders.values())} holders", file=sys.stderr, flush=True)
    return dict(chain=ch, token=a, symbol=sym, events=len(ev), events_complete=complete, roles={names.get(r, r[:10] + ".."): [(h, kinds[h]) for h in hs] for r, hs in holders.items()},
                replay_mismatches=mismatches, unverified=unverified, proxy_admin=up, owner=own, enumerable=any(x.get("name") == "getRoleMemberCount" for x in abi), has_hasRole=any(x.get("name") == "hasRole" for x in abi), abi_read=bool(abi), n_functions=len(fn))
tokens = []
for t in ARGS.token: c, a = t.split(":"); tokens.append((int(c), a))
if ARGS.from_dump:
    for x in json.load(open(ARGS.from_dump)):
        cap = any(x["fam"].get(k) for k in ("freeze", "seize", "pause", "upgrade"))
        if x["chain"] in BLOCKSCOUT and cap and (x.get("roles") or not x["controllers"]): tokens.append((x["chain"], x["token"]))
tokens = sorted(set(tokens))
if not tokens: sys.exit("no token: pass --token CHAIN_ID:0xADDRESS or --from-dump")
print(f"{len(tokens)} tokens")
with ThreadPoolExecutor(3) as ex: rows = list(ex.map(lambda t: analyse(*t), tokens))
EXPO = {}
if ARGS.from_dump:
    for x in json.load(open(ARGS.from_dump)): EXPO[(x["chain"], Web3.to_checksum_address(x["token"]))] = (x["deposits"] + x["collateral"]) / 1e9
for r in sorted(rows, key=lambda r: -EXPO.get((r["chain"], r["token"]), 0)):
    e = EXPO.get((r["chain"], r["token"]))
    print(f"\n== {r['symbol']} chain {r['chain']} {r['token']}" + (f"  exposure ${e:.2f}B" if e is not None else "") + f"  events {r['events']}{'' if r['events_complete'] else ' (NOT ALL READ: the node did not answer or the answer may be cut)'}, hasRole in ABI {r['has_hasRole']}, replay mismatches vs hasRole: {r['replay_mismatches']}, holders whose hasRole could not be read: {r['unverified']}")
    for sn, (x, k) in r["proxy_admin"].items(): print(f"   {sn:24s} {x}  {k}")
    if r["owner"]: print(f"   {'owner()':24s} {r['owner'][0]}  {r['owner'][1]}")
    if not r["events_complete"]: print("   logs not fully read: nothing can be concluded about the holders of this token")
    elif not r["roles"]: print("   0 RoleGranted events" + ("" if r["has_hasRole"] else " and no hasRole in the ABI: this token does not use AccessControl") + ("" if not r["has_hasRole"] else " (roles may have been set in the constructor without an event, or moved to another mechanism)"))
    for role, hs in sorted(r["roles"].items()):
        if len(hs) > 8:
            c = collections.Counter(k.split(" signers")[0].split(",")[0].split(" (")[0] for _, k in hs)
            print(f"   {role:24s} {len(hs)} holders: {dict(c)}; first {[h for h, _ in hs[:2]]}")
        else:
            for h, k in hs: print(f"   {role:24s} {h}  {k}")
print("\nnode calls that still failed after 6 tries, by chain:", dict(FAILS) or "none")
unread = sum(1 for r in rows for hs in r["roles"].values() for _, k in hs if "unread" in k or "NOT READ" in k)
print("holders shown as unread or with weights not read:", unread)
if ARGS.dump: json.dump(rows, open(ARGS.dump, "w")); print(f"\nwrote {ARGS.dump}")
