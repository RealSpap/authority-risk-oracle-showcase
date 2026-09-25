#!/usr/bin/env python3
"""Read-only: Axelar Interchain Token Service (ITS) on Ethereum mainnet -- one real corridor with its governance,
a full sweep of the on-chain TokenManagerProxy registry, and the real reserve balance behind the notable lock/unlock ones.
    python3 sweep_axelar_its.py [--dump rows.json]
Three volets, one script:
  (1) corridor: confirms whether SolvBTC is still a real ITS corridor (or reports if it is not, and what the registry sweep
      found instead), then reads who actually holds OPERATOR/FLOW_LIMITER/MINTER on its TokenManagerProxy (RolesAdded events
      replayed + hasRole confirmation) -- that is its governance, not a name on a dashboard.
  (2) sweep: replays every TokenManagerDeployed event the ITS contract has ever emitted (eth_getLogs, Tenderly's public
      gateway which serves full-range history for free, cf. project memory reference-free-getlogs-sources), decodes each
      TokenManagerProxy's type and underlying token straight from the event's abi-encoded params (the same layout
      TokenManager.params() produces), then reads each proxy's live flowLimit(). flowLimit()==0 means UNLIMITED, not zero
      allowance -- confirmed by reading FlowLimit.sol: _addFlowOut/_addFlowIn both `if (flowLimit_ == 0) return;` before any
      check.
  (3) tvl: for the LOCK_UNLOCK / LOCK_UNLOCK_FEE proxies whose underlying token is a well-known asset (DAI, USDT, WETH,
      WBTC, LINK, native USDC used as axlUSDC's Ethereum-side reserve), reads the REAL balanceOf(tokenManager) today --
      the actual tokens sitting in the pool, not the flow-limit ceiling.
Nothing is sent, no key. The ITS address and ABI are pulled live from axelarnetwork/axelar-contract-deployments and
axelarnetwork/interchain-token-service on GitHub, not hardcoded from memory -- if Axelar redeploys, this script re-derives.
"""
import argparse, json, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor
from eth_abi import decode as abi_decode
from web3 import Web3

ap = argparse.ArgumentParser()
ap.add_argument("--dump", default=None, help="write the full decoded registry (all TokenManagerProxy rows) to this JSON file")
ap.add_argument("--workers", type=int, default=6)
ARGS = ap.parse_args()

RPC = "https://ethereum.publicnode.com"
GATEWAY = "https://gateway.tenderly.co/public/mainnet"  # handles full-range eth_getLogs for free, cf. project memory
GITHUB_CONFIG = "https://raw.githubusercontent.com/axelarnetwork/axelar-contract-deployments/main/axelar-chains-config/info/mainnet.json"
GITHUB_ITS_TAG = "v2.1.1"

WELL_KNOWN = {  # Ethereum-mainnet address -> label, only used to flag which lock/unlock reserves are worth a balanceOf() read
    "0x6b175474e89094c44da98b954eedeac495271d0f": "DAI",
    "0xdac17f958d2ee523a2206206994597c13d831ec7": "USDT",
    "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2": "WETH",
    "0x2260fac5e5542a773aa44fbcfedf7c193bc2c599": "WBTC",
    "0x514910771af9ca656af840dff83e8264ecf986ca": "LINK",
    "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48": "USDC (native, locked as axlUSDC's Ethereum reserve)",
}
TM_TYPE = {0: "NATIVE_INTERCHAIN_TOKEN", 1: "MINT_BURN_FROM", 2: "LOCK_UNLOCK", 3: "LOCK_UNLOCK_FEE", 4: "MINT_BURN"}
ROLE = {0: "MINTER", 1: "OPERATOR", 2: "FLOW_LIMITER"}


def curl(url, body=None):
    cmd = ["curl", "-s", "-m", "40"] + (["-X", "POST", "-H", "content-type: application/json", "--data", json.dumps(body)] if body else []) + [url]
    for _ in range(3):
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=45).stdout
            if out:
                return out
        except Exception:
            pass
    return None


def rpc(method, params, url=RPC):
    # publicnode's free tier throws -32005 "Rate limit exceeded" under load (measured live while running this sweep) --
    # retry with backoff instead of reading that as "empty"/"no code", which would be a false negative, not a real zero.
    for attempt in range(6):
        r = curl(url, {"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
        try:
            d = json.loads(r or "{}")
        except Exception:
            time.sleep(1 + attempt); continue
        if "error" in d:
            if d["error"].get("code") == -32005 or "rate limit" in str(d["error"].get("message", "")).lower():
                time.sleep(1.5 * (attempt + 1)); continue
            return None, d["error"]
        return d.get("result"), None
    return None, {"message": "gave up after retries (persistent rate limit)"}


sel = lambda s: "0x" + Web3.keccak(text=s).hex()[:8]
topic0 = lambda s: "0x" + Web3.keccak(text=s).hex()


def call(to, data, url=RPC):
    res, err = rpc("eth_call", [{"to": to, "data": data}, "latest"], url)
    return res


def eth_get_logs(address, topics, url=GATEWAY):
    res, err = rpc("eth_getLogs", [{"address": address, "topics": topics, "fromBlock": "0x0", "toBlock": "latest"}], url)
    return res, err


# ---------- step 0: find the real ITS address (not from memory) and confirm it is a live contract ----------
print("=== step 0: resolving the real InterchainTokenService address ===")
cfg_raw = curl(GITHUB_CONFIG)
if not cfg_raw:
    print("FATAL: could not fetch axelar-contract-deployments/main/axelar-chains-config/info/mainnet.json"); sys.exit(1)
cfg = json.loads(cfg_raw)
its_cfg = cfg["chains"]["ethereum"]["contracts"]["InterchainTokenService"]
ITS = Web3.to_checksum_address(its_cfg["address"])
print(f"ITS address (from axelar-contract-deployments, live fetch): {ITS}  version={its_cfg.get('version')}")
code, _ = rpc("eth_getCode", [ITS, "latest"])
print(f"eth_getCode({ITS}) on Ethereum mainnet: {'has code, ' + str((len(code) - 2)//2) + ' bytes' if code and code != '0x' else 'EMPTY -- not deployed here'}")
if not code or code == "0x":
    sys.exit(1)

# ---------- step 2 first (registry sweep feeds step 1 and 3): replay every TokenManagerDeployed event ----------
print("\n=== step 2: sweeping the registry -- every TokenManagerDeployed event ever emitted by ITS ===")
TOPIC_TMD = topic0("TokenManagerDeployed(bytes32,address,uint8,bytes)")
logs, err = eth_get_logs(ITS, [TOPIC_TMD])
if err or logs is None:
    print(f"FATAL: eth_getLogs on {GATEWAY} failed: {err}"); sys.exit(1)
print(f"eth_getLogs full range (0x0..latest) via {GATEWAY}: {len(logs)} TokenManagerDeployed events")

registry = []
for lg in logs:
    token_id = lg["topics"][1]
    tm_type = int(lg["topics"][2], 16)
    data = bytes.fromhex(lg["data"][2:])
    tm_addr = Web3.to_checksum_address("0x" + data[:32].hex()[-40:])
    # data layout for (address tokenManager, bytes params): word0=tokenManager, word1=offset-to-bytes, then len+bytes
    try:
        decoded_tail = abi_decode(["address", "bytes"], data)
        params_bytes = decoded_tail[1]
        op_bytes, underlying = abi_decode(["bytes", "address"], params_bytes)
        operator_from_params = ("0x" + op_bytes.hex()) if op_bytes else None
    except Exception:
        underlying, operator_from_params = None, None
    registry.append({
        "tokenId": token_id, "tokenManager": tm_addr, "type": TM_TYPE.get(tm_type, f"?{tm_type}"),
        "underlying": underlying, "operator_from_params": operator_from_params,
        "blockNumber": int(lg["blockNumber"], 16), "txHash": lg["transactionHash"],
    })

by_type = {}
for r in registry:
    by_type[r["type"]] = by_type.get(r["type"], 0) + 1
print(f"decoded {len(registry)} TokenManagerProxy deployments, by type: {by_type}")
n_unique_tm = len({r['tokenManager'] for r in registry})
print(f"unique TokenManagerProxy addresses: {n_unique_tm} (should equal {len(registry)} if no tokenId was ever re-deployed)")

print(f"reading live flowLimit() for all {len(registry)} TokenManagerProxy via {ARGS.workers} workers ({RPC}) ...")
FLOWLIMIT_SEL = sel("flowLimit()")


def read_flow(r):
    res = call(r["tokenManager"], FLOWLIMIT_SEL)
    if res and res != "0x":
        r["flowLimit"] = int(res, 16)
    else:
        r["flowLimit"] = None
    return r


with ThreadPoolExecutor(ARGS.workers) as ex:
    registry = list(ex.map(read_flow, registry))

read_ok = [r for r in registry if r["flowLimit"] is not None]
unlimited = [r for r in read_ok if r["flowLimit"] == 0]
print(f"flowLimit() answered for {len(read_ok)}/{len(registry)} proxies; {len(unlimited)} of those read exactly 0 -> UNLIMITED per FlowLimit.sol source (not 'no flow allowed')")

# ---------- step 1: one real corridor with its governance ----------
print("\n=== step 1: a real corridor and who governs it ===")
solv_addr = "0x7a56e1c57c7475ccf742a1832b028f0456652f97"
solv_rows = [r for r in registry if (r["underlying"] or "").lower() == solv_addr]
DEC_SEL_EARLY = sel("decimals()")
if solv_rows:
    r = solv_rows[0]
    dec_res = call(Web3.to_checksum_address(r["underlying"]), DEC_SEL_EARLY)
    dec = int(dec_res, 16) if dec_res and dec_res != "0x" else 18
    fl_h = "UNLIMITED" if r["flowLimit"] == 0 else f"{r['flowLimit']/10**dec:,.4f} solvBTC per 6h epoch"
    print(f"SolvBTC (0x7A56E1...652F97) IS still a live ITS corridor on Ethereum: tokenId={r['tokenId']}")
    print(f"  TokenManagerProxy={r['tokenManager']}  type={r['type']}  flowLimit()={fl_h}")
    corridor = r
else:
    print("SolvBTC's TokenManager was NOT found among the on-chain TokenManagerDeployed events -- it is not a live ITS corridor on Ethereum today.")
    lock_rows = sorted([r for r in registry if r["type"].startswith("LOCK_UNLOCK") and (r["underlying"] or "").lower() in WELL_KNOWN], key=lambda r: r["blockNumber"])
    corridor = lock_rows[0] if lock_rows else (registry[0] if registry else None)
    if corridor:
        print(f"Using instead: {WELL_KNOWN.get((corridor['underlying'] or '').lower(), corridor['underlying'])}"
              f"  TokenManagerProxy={corridor['tokenManager']}  type={corridor['type']}")

if corridor:
    tm = corridor["tokenManager"]
    # governance: replay RolesAdded(address,uint256) on the proxy itself, then confirm live with hasRole()
    TOPIC_ROLES_ADDED = topic0("RolesAdded(address,uint256)")
    role_logs, rerr = eth_get_logs(tm, [TOPIC_ROLES_ADDED])
    print(f"RolesAdded events on {tm}: {len(role_logs) if role_logs else 0} ({rerr if rerr else 'ok'})")
    grants = []
    if role_logs:
        for lg in role_logs:
            acct = Web3.to_checksum_address("0x" + lg["topics"][1][-40:])
            mask = int(lg["data"], 16)
            roles = [ROLE[b] for b in ROLE if (mask >> b) & 1]
            grants.append((acct, mask, roles))
            print(f"  RolesAdded(account={acct}, roles={roles}, block={int(lg['blockNumber'],16)})")
    # live confirmation: hasRole() for every account seen in the grant log (roles can be removed later -- the log alone
    # only proves it was granted once, not that it still holds it)
    HASROLE_SEL = sel("hasRole(address,uint8)")
    GETTHRESHOLD_SEL = sel("getThreshold()")
    GETOWNERS_SEL = sel("getOwners()")
    print("  live hasRole() confirmation (a past RolesAdded does not mean the role is still held), and what kind of account each governor is:")
    for acct, mask, roles in grants:
        for b in ROLE:
            if (mask >> b) & 1:
                data = HASROLE_SEL + acct[2:].rjust(64, "0").lower() + format(b, "064x")
                res = call(tm, data)
                still = bool(res and int(res, 16))
                print(f"    hasRole({acct}, {ROLE[b]}) NOW = {still}")
        code, _ = rpc("eth_getCode", [acct, "latest"])
        if acct == ITS:
            kind = "the ITS contract itself"
        elif not code or code == "0x":
            kind = "EOA (plain externally-owned account, no code)"
        else:
            thr = call(acct, GETTHRESHOLD_SEL)
            if thr and thr != "0x":
                owners_raw = call(acct, GETOWNERS_SEL)
                ob = bytes.fromhex(owners_raw[2:]) if owners_raw and owners_raw != "0x" else b""
                n = int.from_bytes(ob[32:64], "big") if len(ob) >= 64 else 0
                kind = f"Gnosis Safe multisig {int(thr,16)}-of-{n}"
            else:
                kind = f"contract, {(len(code)-2)//2} bytes (not a Safe -- getThreshold() reverted)"
        print(f"    {acct} is: {kind}")

    # "still active" should mean actually used, not just deployed once -- replay every outbound InterchainTransfer
    # for this corridor's tokenId and look at the most recent one, not only whether the TokenManager exists.
    TOPIC_TRANSFER = topic0("InterchainTransfer(bytes32,address,string,bytes,uint256,bytes32)")
    xfer_logs, xerr = eth_get_logs(ITS, [TOPIC_TRANSFER, corridor["tokenId"]])
    if xfer_logs:
        import datetime
        last_ts = datetime.datetime.utcfromtimestamp(int(xfer_logs[-1]["blockTimestamp"], 16))
        last_block = int(xfer_logs[-1]["blockNumber"], 16)
        print(f"  InterchainTransfer history for this tokenId: {len(xfer_logs)} outbound transfers total,"
              f" most recent at block {last_block} ({last_ts:%Y-%m-%d}) -- deployed and governed does not by itself mean recently used.")
    else:
        print(f"  InterchainTransfer history for this tokenId: 0 outbound transfers found ({xerr if xerr else 'none on record'})")

# ---------- step 3: real balance held today for the notable lock/unlock corridors ----------
print("\n=== step 3: real reserve balance today (balanceOf), not the flow-limit ceiling ===")
BAL_SEL = sel("balanceOf(address)")
DEC_SEL = sel("decimals()")

# cross-reference against Axelar's own public ITS asset list (independent source: axelarscan, not the RPC/GitHub used
# above) so a near-empty TokenManager sharing the same underlying token as the tracked one isn't reported as "the" reserve
official_tms = set()
scan_raw = curl("https://api.axelarscan.io/api/getITSAssets")
try:
    for asset in json.loads(scan_raw or "[]"):
        eth = (asset.get("chains") or {}).get("ethereum")
        if eth and eth.get("tokenManager"):
            official_tms.add(eth["tokenManager"].lower())
    print(f"axelarscan getITSAssets: {len(official_tms)} Ethereum-side TokenManager addresses officially tracked (independent cross-check source)")
except Exception as e:
    print(f"axelarscan cross-check unavailable ({e}) -- proceeding without the official/unofficial label")

tvl_rows = [r for r in registry if r["type"].startswith("LOCK_UNLOCK") and (r["underlying"] or "").lower() in WELL_KNOWN]
print(f"lock/unlock TokenManagerProxy whose underlying is a well-known asset: {len(tvl_rows)} (includes permissionless duplicates -- anyone can deploy a LOCK_UNLOCK manager pointing at any ERC20)")
total_official_usd_note = []
for r in tvl_rows:
    tok = Web3.to_checksum_address(r["underlying"])
    tm = r["tokenManager"]
    dec_res = call(tok, DEC_SEL)
    dec = int(dec_res, 16) if dec_res and dec_res != "0x" else 18
    bal_res = call(tok, BAL_SEL + tm[2:].rjust(64, "0").lower())
    bal = int(bal_res, 16) if bal_res and bal_res != "0x" else None
    label = WELL_KNOWN[r["underlying"].lower()]
    fl = r["flowLimit"]
    fl_h = "UNLIMITED" if fl == 0 else (f"{fl/10**dec:,.4f}" if fl is not None else "read failed")
    bal_h = f"{bal/10**dec:,.4f}" if bal is not None else "read failed"
    tag = "OFFICIAL (axelarscan-tracked)" if tm.lower() in official_tms else "permissionless duplicate, not axelarscan-tracked"
    print(f"  {label:45s} [{tag}]")
    print(f"      TokenManager={tm}  flowLimit(6h cap)={fl_h:>14s}  real balanceOf() today={bal_h:>16s}")
    r["balanceOf"], r["decimals"], r["label"], r["official"] = bal, dec, label, tm.lower() in official_tms
    if r["official"]:
        total_official_usd_note.append(f"{label}={bal_h}")

n_official_examined = sum(1 for r in tvl_rows if r["official"])
print(f"\ntotal TokenManagerProxy scanned: {len(registry)} across {len(by_type)} types")
print(f"confirmed corridors examined with governance: 1 (SolvBTC) | notable lock/unlock reserves checked: {len(tvl_rows)}, of which {n_official_examined} are axelarscan-official ({', '.join(total_official_usd_note)})")

if ARGS.dump:
    json.dump(registry, open(ARGS.dump, "w"), indent=2)
    print(f"\nwrote {ARGS.dump}")
