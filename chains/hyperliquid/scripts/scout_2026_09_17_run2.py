"""Scouting run 2026-09-17 (run 2): live, read-only authority reads for the
Hyperliquid targets written up in data/scouted_targets_2026-09-17-run2.md.

Every read goes to a public endpoint: the official HyperCore info API, the
official HyperEVM RPC (chain 999), the public Arbitrum One RPC, and, for the
one historical log scan (hyperlend-acl-logs), HyperLend's own public archive
RPC listed in its docs. No transaction, no key.

Usage (each subcommand prints one JSON object):
    python3 chains/hyperliquid/scripts/scout_2026_09_17_run2.py para
    python3 chains/hyperliquid/scripts/scout_2026_09_17_run2.py mkts
    python3 chains/hyperliquid/scripts/scout_2026_09_17_run2.py kinetiq
    python3 chains/hyperliquid/scripts/scout_2026_09_17_run2.py unit
    python3 chains/hyperliquid/scripts/scout_2026_09_17_run2.py hlp
    python3 chains/hyperliquid/scripts/scout_2026_09_17_run2.py bridge2
    python3 chains/hyperliquid/scripts/scout_2026_09_17_run2.py hyperlend
    python3 chains/hyperliquid/scripts/scout_2026_09_17_run2.py hyperlend-acl-logs   # slow, ~460 log queries
"""
import concurrent.futures as cf
import json
import subprocess
import sys
import time

from eth_abi import decode, encode
from web3 import Web3

API = "https://api.hyperliquid.xyz/info"
EVM = "https://rpc.hyperliquid.xyz/evm"
ARB = "https://arb1.arbitrum.io/rpc"
HYPERLEND_ARCHIVE = "https://rpc.hyperlend.finance/archive"
IMPL_SLOT = "0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc"
ADMIN_SLOT = "0xb53127684a568b3173ae13b9f8a6016e243e63b6e8ee1178d6a717850b5d6103"
GUARD_SLOT = "0x4a204f620c8c5ccdca3fd54d003badd85ba500436a431f0cbda4f558c93c34c8"
ZERO32 = b"\x00" * 32


def _post(url, body, timeout=60, attempts=5):
    """POST JSON with curl. Retries empty or non-JSON answers (public endpoints
    rate-limit bursts) with a short backoff, then raises."""
    last = None
    for i in range(attempts):
        r = subprocess.run(
            ["curl", "-s", "-m", str(timeout), "-X", "POST", "-H", "Content-Type: application/json", "-d", json.dumps(body), url],
            capture_output=True, text=True,
        )
        try:
            return json.loads(r.stdout)
        except ValueError as e:
            last = f"{e}: {r.stdout[:120]!r}"
            time.sleep(1 + 2 * i)
    raise ConnectionError(f"{url} gave no JSON after {attempts} attempts ({last})")


def info(body):
    return _post(API, body)


def rpc(url, method, params):
    out = _post(url, {"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
    if "error" in out:
        raise RuntimeError(f"{method}: {out['error']}")
    return out["result"]


def cs(a):
    return Web3.to_checksum_address(a)


def call(url, to, sig, types_in=(), args=(), types_out=None):
    """eth_call `sig` (e.g. 'owner()') on `to`; returns decoded tuple, or None on revert."""
    data = Web3.keccak(text=sig)[:4] + (encode(list(types_in), list(args)) if types_in else b"")
    try:
        raw = rpc(url, "eth_call", [{"to": cs(to), "data": "0x" + data.hex()}, "latest"])
    except RuntimeError:
        return None
    b = bytes.fromhex(raw[2:])
    if types_out is None:
        return b
    if not b:
        return None
    return decode(list(types_out), b)


def one(url, to, sig, out_type, types_in=(), args=()):
    r = call(url, to, sig, types_in, args, (out_type,))
    if r is None:
        return None
    v = r[0]
    if out_type == "address":
        return cs(v)
    if out_type == "address[]":
        return [cs(x) for x in v]
    return v


def slot_addr(url, a, slot):
    raw = rpc(url, "eth_getStorageAt", [cs(a), slot, "latest"])
    return cs("0x" + raw[-40:])


def code_len(url, a):
    return (len(rpc(url, "eth_getCode", [cs(a), "latest"])) - 2) // 2


def safe(url, a):
    owners = one(url, a, "getOwners()", "address[]")
    thr = one(url, a, "getThreshold()", "uint256")
    if owners is None or thr is None:
        return None
    mods = call(url, a, "getModulesPaginated(address,uint256)", ("address", "uint256"),
                ("0x0000000000000000000000000000000000000001", 10), ("address[]", "address"))
    return {"threshold": thr, "owners": owners, "n": len(owners),
            "modules": [cs(x) for x in mods[0]] if mods else None,
            "guard": slot_addr(url, a, GUARD_SLOT)}


def role_hash(name):
    return ZERO32 if name == "DEFAULT_ADMIN_ROLE" else Web3.keccak(text=name)


def has_role(url, contract, role, account):
    return one(url, contract, "hasRole(bytes32,address)", "bool", ("bytes32", "address"), (role_hash(role), cs(account)))


def enum_role(url, contract, role):
    n = one(url, contract, "getRoleMemberCount(bytes32)", "uint256", ("bytes32",), (role_hash(role),))
    if n is None:
        return None
    return [one(url, contract, "getRoleMember(bytes32,uint256)", "address", ("bytes32", "uint256"), (role_hash(role), i)) for i in range(n)]


def multisig_kn(user):
    m = info({"type": "userToMultiSigSigners", "user": user})
    return None if m is None else {"threshold": m["threshold"], "authorizedUsers": m["authorizedUsers"]}


def dex(name):
    d = next(x for x in info({"type": "perpDexs"}) if x and x["name"] == name)
    m, ctxs = info({"type": "metaAndAssetCtxs", "dex": name})
    oi = sum(float(c["openInterest"]) * float(c["markPx"]) for c in ctxs if c.get("markPx"))
    net = float(info({"type": "perpDexStatus", "dex": name})["totalNetDeposit"])
    return d, round(oi), round(net)


# ---------------------------------------------------------------- HIP-3 dexes

def para():
    d, oi, net = dex("para")
    dep = cs(d["deployer"])
    vault_impl = slot_addr(EVM, dep, IMPL_SLOT)
    rr = one(EVM, dep, "roleRegistry()", "address")
    rr_owner = one(EVM, rr, "owner()", "address")
    managers = one(EVM, rr, "roleHolders(bytes32)", "address[]", ("bytes32",), (Web3.keccak(text="MANAGER_ROLE"),))
    operators = one(EVM, rr, "roleHolders(bytes32)", "address[]", ("bytes32",), (Web3.keccak(text="OPERATOR_ROLE"),))
    op_safes = {o: safe(EVM, o) for o in operators}
    leaf_keys = {}
    for o, s in op_safes.items():
        for k in (s["owners"] if s else [o]):
            leaf_keys[k] = {"evmCodeBytes": code_len(EVM, k), "safe": safe(EVM, k)}
    return {
        "dex": "para", "deployer": dep, "oracleUpdater": d.get("oracleUpdater"),
        "subDeployers": dict(d.get("subDeployers") or []),
        "hypercoreMultisig": {a: multisig_kn(a) for a in [dep] + [x for v in dict(d.get("subDeployers") or []).values() for x in v]},
        "openInterestUsd": oi, "totalNetDepositUsd": net,
        "deployerDelegatedHype": float(info({"type": "delegatorSummary", "user": dep})["delegated"]),
        "deployerEvmCodeBytes": code_len(EVM, dep),
        "deployerIsUupsProxyImpl": vault_impl,
        "roleRegistry": rr, "roleRegistryOwner": rr_owner, "roleRegistryOwnerSafe": safe(EVM, rr_owner),
        "MANAGER_ROLE": managers, "OPERATOR_ROLE": operators, "operatorSafes": op_safes,
        "operatorSafeLeafKeys": leaf_keys,
        "vaultPaused": one(EVM, rr, "isPaused(address)", "bool", ("address",), (dep,)),
        "namedApiWallets": info({"type": "extraAgents", "user": dep}),
        "oracleUpdaterEvmCodeBytes": code_len(EVM, "0x764ed9d59c91a2c653fd50c43585917366244335"),
    }


def mkts():
    d, oi, net = dex("mkts")
    dep = cs(d["deployer"])
    subs = dict(d.get("subDeployers") or [])
    ex_manager = one(EVM, dep, "exManager()", "address")
    gc = one(EVM, ex_manager, "globalConfig()", "address")
    wallet_admin = one(EVM, gc, "exWalletAdmin()", "address")
    sm_proxy_admin = slot_addr(EVM, dep, ADMIN_SLOT)
    em_proxy_admin = slot_addr(EVM, ex_manager, ADMIN_SLOT)
    root_safe = "0x18A82c968b992D28D4D812920eB7b4305306f8F1"
    return {
        "dex": "mkts", "deployer": dep, "oracleUpdater": d.get("oracleUpdater"), "subDeployers": subs,
        "subDeployerHypercoreMultisig": {a: multisig_kn(a) for v in subs.values() for a in v},
        "subDeployerEvmCodeBytes": {a: code_len(EVM, a) for v in subs.values() for a in v},
        "openInterestUsd": oi, "totalNetDepositUsd": net,
        "deployerHypercoreMultisig": multisig_kn(dep),
        "deployerEvmCodeBytes": code_len(EVM, dep),
        "HIP3StakingManagerImpl": slot_addr(EVM, dep, IMPL_SLOT),
        "exManager": ex_manager, "exManagerImpl": slot_addr(EVM, ex_manager, IMPL_SLOT),
        "exPhase(3=LIVE)": one(EVM, ex_manager, "exPhase()", "uint8"),
        "walletNonce": one(EVM, ex_manager, "walletNonce()", "uint256"),
        "globalConfig": gc, "exWalletAdmin": wallet_admin, "exWalletAdminEvmCodeBytes": code_len(EVM, wallet_admin),
        "globalConfig_CONFIG_ADMIN_ROLE": enum_role(EVM, gc, "CONFIG_ADMIN_ROLE"),
        "globalConfig_DEFAULT_ADMIN_ROLE": enum_role(EVM, gc, "DEFAULT_ADMIN_ROLE"),
        "exManager_DEFAULT_ADMIN_ROLE": enum_role(EVM, ex_manager, "DEFAULT_ADMIN_ROLE"),
        "exManager_MANAGER_ROLE": enum_role(EVM, ex_manager, "MANAGER_ROLE"),
        "exManager_OPERATOR_ROLE": enum_role(EVM, ex_manager, "OPERATOR_ROLE"),
        "stakingManagerProxyAdminOwner": one(EVM, sm_proxy_admin, "owner()", "address"),
        "exManagerProxyAdminOwner": one(EVM, em_proxy_admin, "owner()", "address"),
        "rootSafe": safe(EVM, root_safe),
        "namedApiWallets": info({"type": "extraAgents", "user": dep}),
    }


# ---------------------------------------------------------------- Kinetiq

KINETIQ = {
    "kHYPE": {"stakingManager": "0x393D0B87Ed38fc779FD9611144aE649BA6082109",
              "oracleManager": "0x192826e470bd65FDC2CB472eDd834D096233049b",
              "defaultOracle": "0xefbcCc6E33DA1C1ef638cBc0F044968D0f590fED"},
    "kmHYPE": {"stakingManager": "0x71F0019cC7fa79E4f42587FB7b9a817D8d2429EC",
               "oracleManager": "0x673C57b16F3855CB08030290654bb5E26Ac8E273",
               "defaultOracle": "0x9c2Fc9AE6261d08EA8f1dBe53F58C99F7eF9FCA2"},
}


def kinetiq():
    out = {}
    for k, c in KINETIQ.items():
        sm, om, do = c["stakingManager"], c["oracleManager"], c["defaultOracle"]
        pa = slot_addr(EVM, sm, ADMIN_SLOT)
        checker = one(EVM, om, "sanityChecker()", "address")
        entry = {
            "stakingManager": sm,
            "stakingManager_DEFAULT_ADMIN_ROLE": enum_role(EVM, sm, "DEFAULT_ADMIN_ROLE"),
            "stakingManagerProxyAdminOwner": one(EVM, pa, "owner()", "address"),
            "oracleManager_DEFAULT_ADMIN_ROLE": enum_role(EVM, om, "DEFAULT_ADMIN_ROLE"),
            "oracleManager_MANAGER_ROLE": enum_role(EVM, om, "MANAGER_ROLE"),
            "oracleManager_OPERATOR_ROLE": enum_role(EVM, om, "OPERATOR_ROLE"),
            "oracleManager_MIN_UPDATE_INTERVAL_s": one(EVM, om, "MIN_UPDATE_INTERVAL()", "uint256"),
            "oracleManager_MIN_VALID_ORACLES": one(EVM, om, "MIN_VALID_ORACLES()", "uint256"),
            "oracleManager_maxPerformanceBound_bps": one(EVM, om, "maxPerformanceBound()", "uint256"),
            "sanityChecker": checker,
            "defaultOracle_MIN_UPDATE_INTERVAL_s": one(EVM, do, "MIN_UPDATE_INTERVAL()", "uint256"),
        }
        vm = one(EVM, om, "validatorManager()", "address")
        entry["validatorManager"] = vm
        entry["validatorManager_ORACLE_MANAGER_ROLE"] = enum_role(EVM, vm, "ORACLE_MANAGER_ROLE")
        ops = entry["oracleManager_OPERATOR_ROLE"] or []
        entry["operatorEvmCodeBytes"] = {o: code_len(EVM, o) for o in ops}
        entry["defaultOracle_operatorHasRole"] = {o: has_role(EVM, do, "OPERATOR_ROLE", o) for o in ops}
        if checker and int(checker, 16) != 0:
            entry["sanityCheckerParams"] = {
                "owner": one(EVM, checker, "owner()", "address"),
                "stakingManager": one(EVM, checker, "stakingManager()", "address"),
                "rewardsTolerance_bps": one(EVM, checker, "rewardsTolerance()", "uint256"),
                "slashingTolerance_bps": one(EVM, checker, "slashingTolerance()", "uint256"),
                "balanceDriftTolerance_bps": one(EVM, checker, "balanceDriftTolerance()", "uint256"),
                "maxScoreBound_bps": one(EVM, checker, "maxScoreBound()", "uint256"),
            }
        out[k] = entry
    out["rootSafe"] = safe(EVM, "0x18A82c968b992D28D4D812920eB7b4305306f8F1")
    out["kHYPE_exchangeRate_1e18"] = one(EVM, "0x9209648Ec9D448EF57116B73A2f081835643dc7A", "kHYPEToHYPE(uint256)", "uint256", ("uint256",), (10**18,))
    return out


# ---------------------------------------------------------------- Unit

UNIT_DEPLOYER = "0xF036a5261406a394bd63Eb4dF49C464634a66155"
UNIT_TREASURIES = {  # docs.hyperunit.xyz "Key Addresses > Mainnet"
    "UBTC": ("0x8f254b963e8468305d409b33aa137c67", "0x574bAFCe69d9411f662a433896e74e4F153096FA", "BTC"),
    "UETH": ("0xe1edd30daaf5caac3fe63569e24748da", "0x8DAfBe89302656a7Df43c470e9EbCB4c540835c0", "ETH"),
    "USOL": ("0x49b67c39f5566535de22b29b0e51e685", "0xA822a9cEB6D6CB5b565bD10098AbCFA9Cf18D748", "SOL"),
}


def unit():
    mids = info({"type": "allMids"})
    out = {"deployer": UNIT_DEPLOYER, "deployerMultisig": multisig_kn(UNIT_DEPLOYER),
           "deployerNamedApiWallets": info({"type": "extraAgents", "user": UNIT_DEPLOYER}),
           "deployerEvmCodeBytes": code_len(EVM, UNIT_DEPLOYER), "tokens": {}}
    for sym, (tid, treasury, px_coin) in UNIT_TREASURIES.items():
        td = info({"type": "tokenDetails", "tokenId": tid})
        bals = {b["coin"]: float(b["total"]) for b in info({"type": "spotClearinghouseState", "user": treasury})["balances"]}
        max_supply = float(td["maxSupply"])
        treasury_bal = bals.get(sym, 0.0)
        outstanding = max_supply - treasury_bal
        out["tokens"][sym] = {
            "tokenId": tid, "tokenDeployer": td.get("deployer"), "maxSupply": max_supply,
            "genesisHolder": (td.get("genesis") or {}).get("userBalances"),
            "treasury": treasury, "treasuryMultisig": multisig_kn(treasury),
            "treasuryNamedApiWallets": info({"type": "extraAgents", "user": treasury}),
            "treasuryBalance": treasury_bal, "treasuryShareOfMaxSupply": treasury_bal / max_supply,
            "outstandingOutsideTreasury": outstanding,
            "outstandingUsd": round(outstanding * float(mids[px_coin])),
        }
    return out


# ---------------------------------------------------------------- HLP

HLP = "0xdfc24b077bc1425ad1dea75bcb6f8158e10df303"


def hlp():
    v = info({"type": "vaultDetails", "vaultAddress": HLP})
    leader = v["leader"]
    portfolio = dict(v["portfolio"])
    children = v["relationship"]["data"]["childAddresses"]
    return {
        "vault": HLP, "name": v["name"], "leader": leader,
        "leaderMultisig": multisig_kn(leader), "leaderEvmCodeBytes": code_len(EVM, leader),
        "leaderNamedApiWallets": info({"type": "extraAgents", "user": leader}),
        "leaderCommission": v["leaderCommission"], "leaderFraction": v["leaderFraction"],
        "accountValueUsd_latest": round(float(portfolio["day"]["accountValueHistory"][-1][1])),
        "children": {c: info({"type": "vaultDetails", "vaultAddress": c})["leader"] for c in children},
        "allowDeposits": v["allowDeposits"], "isClosed": v["isClosed"],
    }


# ---------------------------------------------------------------- Bridge2 (Arbitrum)

BRIDGE2 = "0x2df1c51e09aecf9cacb7bc98cb1742757f163df7"
EPOCH7_TX = "0x62a66b841b44845f9aa6a2c40b7aea017eedb791b95a5f20bd312960320246b4"
USDC_ARB = "0xaf88d065e77c8cC2239327C5EDb3A432268e5831"
EXTRA_LOCKER = "0xf9d2282a4a4c216f624717c0747d23146fc048c5"


def bridge2():
    tx = rpc(ARB, "eth_getTransactionByHash", [EPOCH7_TX])
    sig = "emergencyUnlock((uint64,address[],address[],uint64[]),(uint64,address[],uint64[]),(uint256,uint256,uint8)[],uint64)"
    selector_ok = tx["input"][:10] == "0x" + Web3.keccak(text=sig)[:4].hex().removeprefix("0x")
    new_set, active_cold, _sigs, _nonce = decode(
        ["(uint64,address[],address[],uint64[])", "(uint64,address[],uint64[])", "(uint256,uint256,uint8)[]", "uint64"],
        bytes.fromhex(tx["input"][10:]))
    epoch, hot, cold, powers = new_set
    hot_hash = Web3.keccak(encode(["address[]", "uint64[]", "uint64"], [list(hot), list(powers), epoch])).hex()
    cold_hash = Web3.keccak(encode(["address[]", "uint64[]", "uint64"], [list(cold), list(powers), epoch])).hex()
    onchain_hot = one(ARB, BRIDGE2, "hotValidatorSetHash()", "bytes32").hex()
    onchain_cold = one(ARB, BRIDGE2, "coldValidatorSetHash()", "bytes32").hex()
    vals = info({"type": "validatorSummaries"})
    l1_keys = {x["validator"].lower() for x in vals} | {x["signer"].lower() for x in vals}
    bridge_keys = [a.lower() for a in list(hot) + list(cold)]
    norm = lambda h: h.removeprefix("0x")
    return {
        "bridge": BRIDGE2, "usdcBalance": one(ARB, USDC_ARB, "balanceOf(address)", "uint256", ("address",), (BRIDGE2,)) / 1e6,
        "epoch": one(ARB, BRIDGE2, "epoch()", "uint64"),
        "lockerThreshold": one(ARB, BRIDGE2, "lockerThreshold()", "uint64"),
        "disputePeriodSeconds": one(ARB, BRIDGE2, "disputePeriodSeconds()", "uint64"),
        "paused": one(ARB, BRIDGE2, "paused()", "bool"),
        "implementationSlot": slot_addr(ARB, BRIDGE2, IMPL_SLOT),
        "epoch7TxSelectorIsEmergencyUnlock": selector_ok,
        "decodedEpoch": epoch, "hotAddresses": [cs(a) for a in hot], "coldAddresses": [cs(a) for a in cold],
        "powers": list(powers),
        "hotHashMatchesOnchain": norm(hot_hash) == norm(onchain_hot),
        "coldHashMatchesOnchain": norm(cold_hash) == norm(onchain_cold),
        # hot set plus the one extra address seen in ModifiedLocker/ModifiedFinalizer events;
        # constructor-set lockers emit no event and cannot be enumerated this way.
        "lockers": {cs(a): one(ARB, BRIDGE2, "lockers(address)", "bool", ("address",), (cs(a),)) for a in list(hot) + [EXTRA_LOCKER]},
        "finalizers": {cs(a): one(ARB, BRIDGE2, "finalizers(address)", "bool", ("address",), (cs(a),)) for a in list(hot) + [EXTRA_LOCKER]},
        "lockersVotingLock": one(ARB, BRIDGE2, "getLockersVotingLock()", "address[]"),
        "l1ValidatorCount": len(vals), "l1ActiveValidatorCount": sum(1 for x in vals if x["isActive"]),
        "bridgeKeysMatchingAnyL1ValidatorOrSignerAddress": sorted(set(bridge_keys) & l1_keys),
    }


# ---------------------------------------------------------------- HyperLend Pooled

HL = {  # docs.hyperlend.finance/developer-documentation/contract-addresses
    "PoolAddressesProvider": "0x72c98246a98bFe64022a3190e7710E157497170C",
    "ACLManager": "0x10914Ee2C2dd3F3dEF9EFFB75906CA067700a04A",
    "ProxyAdmin": "0xdb3Bf3e22380780F75D7F57C772e71fCa7EBA027",
    "GovernanceMultisig": "0x2110E7B8e925C387A88259CEac9bd82c47868E9C",
    "TimelockA": "0xaAaaaAAAa810beD1EDA93A18FEC940857ED17879",
    "TimelockB": "0xbbBBbbBB81e9B92918AA51e0CDfB3B53f7D72432",
    "ExecutorDocs": "0x1a54A8C3C49127FcF17F45B842d760f877746B22",
    "TreasuryMultisig": "0xCBF400610DBF462fE316D8A7db6Ba78d57E43d7b",
    "EmergencyAdminMultisig": "0xC2A0F2c78dd7E37C82aA3A8e37fc712a3ddb7cAc",
}
HL_EXTRA = {"ExecutorLive": "0x0a0d1d19107d2658b127C872fBEB97F5F9BD5d42",
            "EmergencyAdminSafe2": "0xb6c27b7293ca9612b9641c93203b42bf67c18616",
            "CapAutomator": "0x01f550365b99ae5b76533241c5ba8255441ba312"}


def hyperlend():
    p = HL["PoolAddressesProvider"]
    out = {
        "providerOwner": one(EVM, p, "owner()", "address"),
        "aclAdmin": one(EVM, p, "getACLAdmin()", "address"),
        "proxyAdminOwner": one(EVM, HL["ProxyAdmin"], "owner()", "address"),
        "executorLiveOwner": one(EVM, HL_EXTRA["ExecutorLive"], "owner()", "address"),
        "executorDocsOwner": one(EVM, HL["ExecutorDocs"], "owner()", "address"),
        "timelockA_minDelay_s": one(EVM, HL["TimelockA"], "getMinDelay()", "uint256"),
        "timelockB_minDelay_s": one(EVM, HL["TimelockB"], "getMinDelay()", "uint256"),
        "safes": {n: safe(EVM, HL.get(n) or HL_EXTRA.get(n)) for n in
                  ("GovernanceMultisig", "TreasuryMultisig", "EmergencyAdminMultisig", "EmergencyAdminSafe2")},
        "capAutomatorAdminIsTimelockB": has_role(EVM, HL_EXTRA["CapAutomator"], "DEFAULT_ADMIN_ROLE", HL["TimelockB"]),
        "timelockRoles": {},
        "aclHasRole": {},
    }
    cands = {**HL, **HL_EXTRA}
    for tl in ("TimelockA", "TimelockB"):
        out["timelockRoles"][tl] = {r: [n for n, a in cands.items() if has_role(EVM, HL[tl], r, a)]
                                    for r in ("PROPOSER_ROLE", "EXECUTOR_ROLE", "CANCELLER_ROLE", "DEFAULT_ADMIN_ROLE")}
        out["timelockRoles"][tl]["openExecutor(address0)"] = has_role(EVM, HL[tl], "EXECUTOR_ROLE", "0x0000000000000000000000000000000000000000")
    for r in ("DEFAULT_ADMIN_ROLE", "POOL_ADMIN", "EMERGENCY_ADMIN", "RISK_ADMIN", "ASSET_LISTING_ADMIN"):
        out["aclHasRole"][r] = [n for n, a in cands.items() if has_role(EVM, HL["ACLManager"], r, a)]
    return out


def hyperlend_acl_logs():
    """Full RoleGranted/RoleRevoked history of the ACLManager, 100k-block chunks
    (the official RPC serves at most 50 blocks of logs)."""
    acl = HL["ACLManager"]
    granted = "0x" + Web3.keccak(text="RoleGranted(bytes32,address,address)").hex().removeprefix("0x")
    revoked = "0x" + Web3.keccak(text="RoleRevoked(bytes32,address,address)").hex().removeprefix("0x")
    latest = int(rpc(HYPERLEND_ARCHIVE, "eth_blockNumber", []), 16)
    lo, hi = 0, latest
    while lo < hi:
        mid = (lo + hi) // 2
        if rpc(HYPERLEND_ARCHIVE, "eth_getCode", [acl, hex(mid)]) not in ("0x", ""):
            hi = mid
        else:
            lo = mid + 1
    ranges = [(b, min(b + 99_999, latest)) for b in range(lo, latest + 1, 100_000)]

    def q(r):
        last = None
        for _ in range(4):
            try:
                return rpc(HYPERLEND_ARCHIVE, "eth_getLogs", [{"address": acl, "fromBlock": hex(r[0]), "toBlock": hex(r[1]), "topics": [[granted, revoked]]}])
            except Exception as e:  # retry transient failures
                last = e
        raise RuntimeError(f"range {r}: {last}")

    logs = []
    with cf.ThreadPoolExecutor(8) as ex:
        for res in ex.map(q, ranges):
            logs += res
    names = {"0x" + role_hash(n).hex().removeprefix("0x"): n for n in
             ("DEFAULT_ADMIN_ROLE", "POOL_ADMIN", "EMERGENCY_ADMIN", "RISK_ADMIN", "ASSET_LISTING_ADMIN", "FLASH_BORROWER", "BRIDGE")}
    state = {}
    for l in sorted(logs, key=lambda l: (int(l["blockNumber"], 16), int(l["logIndex"], 16))):
        key = (names.get(l["topics"][1], l["topics"][1]), cs("0x" + l["topics"][2][-40:]))
        state[key] = l["topics"][0] == granted
    holders = {}
    for (role, acct), live in sorted(state.items()):
        if live:
            holders.setdefault(role, []).append(acct)
    return {"deployBlock": lo, "latestBlock": latest, "events": len(logs), "currentHolders": holders}


if __name__ == "__main__":
    fn = {"para": para, "mkts": mkts, "kinetiq": kinetiq, "unit": unit, "hlp": hlp, "bridge2": bridge2,
          "hyperlend": hyperlend, "hyperlend-acl-logs": hyperlend_acl_logs}[sys.argv[1]]
    print(json.dumps(fn(), indent=1, default=str))
