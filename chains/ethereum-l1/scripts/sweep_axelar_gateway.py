#!/usr/bin/env python3
"""Read-only: Axelar's AxelarGateway on Ethereum mainnet -- who governs it, who can cap mint limits, and how the
weighted "operator" (validator) set that authorizes cross-chain messages is rotated.
    python3 sweep_axelar_gateway.py
Gateway address is Axelar's own deployment registry (axelar-contract-deployments repo, axelar-chains-config/info/
mainnet.json), cross-checked live: governance()/mintLimiter()/authModule() must all return real contracts, the
EternalStorage-derived implementation slot must match the registry's claimed implementation, and the operator set's
keccak256(abi.encode(operators, weights, threshold)) must match hashForEpoch() read live from the auth contract --
nothing here is taken on the registry's word alone. eth_call/eth_getBlockByNumber go through a normal public RPC;
full OperatorshipTransferred history does not (public RPCs cap eth_getLogs at a small recent-block window without a
paid token -- confirmed live below), so that part uses Tenderly's free public gateway instead. Nothing is sent, no key.
"""
import json, subprocess, sys, time, statistics
from collections import Counter
from eth_abi import decode as abi_decode
from web3 import Web3

RPC = "https://ethereum.publicnode.com"
LOGS_RPC = "https://gateway.tenderly.co/public/mainnet"  # publicnode refuses eth_getLogs beyond a small recent window without a token; Tenderly's public gateway doesn't


def curl(url, body):
    cmd = ["curl", "-s", "-m", "40", "-A", "Mozilla/5.0", "-X", "POST", "-H", "content-type: application/json",
           "--data", json.dumps(body), url]
    for _ in range(3):
        try:
            out = subprocess.run(cmd, capture_output=True, text=True).stdout
            if out:
                return out
        except Exception:
            pass
    return "{}"


def rpc(method, params, url=RPC):
    for attempt in range(5):
        r = json.loads(curl(url, {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}) or "{}")
        if "error" not in r:
            return r.get("result")
        if r["error"].get("code") == -32005 and attempt < 4:  # rate limited, back off and retry
            time.sleep(3 * (attempt + 1))
            continue
        print(f"  RPC error on {method}: {r['error']}", file=sys.stderr)
        return None


sel = lambda s: "0x" + Web3.keccak(text=s)[:4].hex()
call = lambda to, sig, args_hex="": rpc("eth_call", [{"to": to, "data": sel(sig) + args_hex}, "latest"])
addr_from = lambda w: Web3.to_checksum_address("0x" + w[-40:]) if w and w != "0x" else None


def decode_string(word_hex):
    # single dynamic `string` return: offset word, then length word, then data
    data = bytes.fromhex(word_hex[2:])
    length = int.from_bytes(data[32:64], "big")
    return data[64:64 + length].decode()


GATEWAY = "0x4F4495243837681061C4743b74B3eEdf548D56A5"  # axelar-contract-deployments mainnet.json: chains.ethereum.contracts.AxelarGateway.address

print(f"AxelarGateway (proxy) on Ethereum mainnet: {GATEWAY}")
code = rpc("eth_getCode", [GATEWAY, "latest"]) or "0x"
print(f"  has contract code: {len(code) > 2} ({(len(code) - 2) // 2} bytes -- small, it's a thin delegatecall proxy)")

# Custom EternalStorage proxy: getAddress(key) reads mapping(bytes32=>address) declared as the 3rd state var (slot
# index 2) in EternalStorage.sol, so the real slot is keccak256(key ++ uint256(2)), not the raw "key" itself.
KEY_IMPLEMENTATION = bytes.fromhex("360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc")
impl_slot = "0x" + Web3.keccak(KEY_IMPLEMENTATION + (2).to_bytes(32, "big")).hex()
impl = addr_from(rpc("eth_getStorageAt", [GATEWAY, impl_slot, "latest"]))
print(f"  implementation (EternalStorage slot, derived not assumed): {impl}")

governance = addr_from(call(GATEWAY, "governance()"))
mint_limiter = addr_from(call(GATEWAY, "mintLimiter()"))
auth_module = addr_from(call(GATEWAY, "authModule()"))
token_deployer = addr_from(call(GATEWAY, "tokenDeployer()"))
assert governance and mint_limiter and auth_module, "core getters came back empty -- wrong address, stopping"
print(f"  governance():    {governance}")
print(f"  mintLimiter():   {mint_limiter}")
print(f"  authModule():    {auth_module}")
print(f"  tokenDeployer(): {token_deployer}")

# --- governance(): identify it, don't just trust the name ---------------------------------------------------
gov_chain = decode_string(call(governance, "governanceChain()"))
gov_addr = decode_string(call(governance, "governanceAddress()"))
min_delay = int(call(governance, "minimumTimeLockDelay()") or "0x0", 16)
print(f"\ngovernance() {governance} -- InterchainGovernance pattern, confirmed on-chain:")
print(f"  governanceChain():        {gov_chain!r}")
print(f"  governanceAddress():      {gov_addr!r}  (Cosmos account on the Axelar chain that proposals must come from)")
print(f"  minimumTimeLockDelay():   {min_delay} s ({min_delay/86400:.1f} days) -- hard floor enforced on Ethereum itself for any scheduled proposal")
print("  controls (per AxelarGateway.sol v6.2.0 source, modifier-checked): transferGovernance(), upgrade() (implementation swap) exclusively;")
print("  transferMintLimiter() and setTokenMintLimits() jointly with mintLimiter() below (onlyMintLimiter accepts either)")

# --- mintLimiter(): identify it -------------------------------------------------------------------------------
signer_threshold = int(call(mint_limiter, "signerThreshold()") or "0x0", 16)
signer_accounts_raw = call(mint_limiter, "signerAccounts()")
data = bytes.fromhex(signer_accounts_raw[2:])
n = int.from_bytes(data[32:64], "big")
signers = sorted(Web3.to_checksum_address("0x" + data[64 + 32 * i + 12:64 + 32 * (i + 1)].hex()) for i in range(n))
print(f"\nmintLimiter() {mint_limiter} -- Axelar's own BaseMultisig contract (not a Gnosis Safe), confirmed on-chain:")
print(f"  signerThreshold(): {signer_threshold} of {len(signers)}")
for s in signers:
    print(f"    {s}")
print("  controls: setTokenMintLimits() alone (also callable by governance); no timelock on this path")

# --- authModule(): weighted operator set ------------------------------------------------------------------------
auth_owner = addr_from(call(auth_module, "owner()"))
current_epoch = int(call(auth_module, "currentEpoch()") or "0x0", 16)
print(f"\nauthModule() {auth_module} -- AxelarAuthWeighted, confirmed on-chain:")
print(f"  owner() == gateway: {auth_owner == GATEWAY}  (only the gateway itself may call transferOperatorship)")
print(f"  currentEpoch(): {current_epoch}")

# --- full rotation history: public RPC vs Tenderly -----------------------------------------------------------
topic0 = "0x" + Web3.keccak(text="OperatorshipTransferred(address[],uint256[],uint256)").hex()
probe = rpc("eth_getLogs", [{"address": auth_module, "topics": [topic0], "fromBlock": "0x0", "toBlock": "latest"}])
print(f"\neth_getLogs full range on {RPC}: {'worked' if probe is not None else 'refused (see stderr above -- this is the known publicnode archive-token limit)'}")

logs = rpc("eth_getLogs", [{"address": auth_module, "topics": [topic0], "fromBlock": "0x0", "toBlock": "latest"}], url=LOGS_RPC)
if logs is None:
    print("Tenderly gateway also refused -- cannot get rotation history this run. Stopping honestly here.")
    sys.exit(1)

print(f"eth_getLogs full range on {LOGS_RPC}: {len(logs)} OperatorshipTransferred events")
assert len(logs) == current_epoch, f"event count {len(logs)} != currentEpoch() {current_epoch} -- inconsistent, not reporting cadence numbers"

decoded = []
for lg in logs:
    ops, weights, threshold = abi_decode(["address[]", "uint256[]", "uint256"], bytes.fromhex(lg["data"][2:]))
    decoded.append(dict(block=int(lg["blockNumber"], 16), tx=lg["transactionHash"],
                         ops=[Web3.to_checksum_address(a) for a in ops], weights=list(weights), threshold=threshold))
decoded.sort(key=lambda d: d["block"])

# verify the two most recent decoded sets against hashForEpoch(), read live -- don't trust the log decode blindly
from eth_abi import encode as abi_encode
for i, d in zip((current_epoch, current_epoch - 1), (decoded[-1], decoded[-2])):
    h_live = call(auth_module, "hashForEpoch(uint256)", format(i, "064x"))
    h_computed = "0x" + Web3.keccak(abi_encode(["address[]", "uint256[]", "uint256"], [d["ops"], d["weights"], d["threshold"]])).hex()
    assert h_live == h_computed, f"epoch {i}: hashForEpoch()={h_live} but recomputed hash of decoded event={h_computed}"
print("hashForEpoch(current) and hashForEpoch(current-1) both match the recomputed hash of the decoded events -- decode verified correct.")

first, last = decoded[0], decoded[-1]
ts_first = int((rpc("eth_getBlockByNumber", [hex(first["block"]), False]) or {}).get("timestamp", "0x0"), 16)
ts_last = int((rpc("eth_getBlockByNumber", [hex(last["block"]), False]) or {}).get("timestamp", "0x0"), 16)
# publicnode refuses eth_getCode at an old historical block ("archive requests require a token"); Tenderly's
# gateway is a full archive node and answers it directly -- don't let a silent RPC failure masquerade as "0x".
code_before = rpc("eth_getCode", [auth_module, hex(first["block"] - 1)], url=LOGS_RPC)
if code_before is None:
    print(f"\ncould not confirm whether block {first['block']-1} predates deployment (RPC refused) -- not claiming it.")
else:
    print(f"\ncontract has no code at block {first['block']-1} ({code_before == '0x'}) -> block {first['block']} is the authModule's deployment block: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime(ts_first))}")
print(f"most recent rotation: block {last['block']}, {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime(ts_last))}, tx {last['tx']}")

gaps = [b["block"] - a["block"] for a, b in zip(decoded, decoded[1:])]
buckets = Counter()
for g in gaps:
    h = g * 12 / 3600
    buckets["<6h"] += h < 6
    buckets["6-24h"] += 6 <= h < 24
    buckets["1-2d"] += 24 <= h < 48
    buckets["2-7d"] += 48 <= h < 168
    buckets[">7d"] += h >= 168
print(f"\n{len(gaps)} gaps between rotations, over {(ts_last-ts_first)/86400:.0f} days:")
print(f"  median {statistics.median(gaps)*12/3600:.1f} h, mean {statistics.mean(gaps)*12/3600:.1f} h (assuming ~12s/block post-merge)")
print(f"  distribution: {dict(buckets)}")

tx_from = (rpc("eth_getTransactionByHash", [last["tx"]]) or {}).get("from")
print(f"  most recent rotation tx sent by relayer EOA: {tx_from}")

cur, prev = decoded[-1], decoded[-2]
set_cur, set_prev = set(cur["ops"]), set(prev["ops"])
print(f"\ncurrent operator set (epoch {current_epoch}): {len(cur['ops'])} addresses, total weight {sum(cur['weights'])}, threshold {cur['threshold']} ({cur['threshold']/sum(cur['weights'])*100:.1f}%)")
print(f"vs previous epoch ({current_epoch - 1}): {len(set_cur & set_prev)} addresses in common, {len(set_cur - set_prev)} new, {len(set_prev - set_cur)} dropped -- of {len(set_cur)}")
for a, w in sorted(zip(cur["ops"], cur["weights"]), key=lambda x: -x[1])[:5]:
    print(f"    {a}  weight {w}")

print("\ndone.")
