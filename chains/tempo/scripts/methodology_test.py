"""Methodology test (started 2026-09-16, extended 2026-09-17 and 2026-09-18
-- see chains/tempo/METHODOLOGY.md's own changelog for the exact history,
this docstring intentionally points there instead of repeating a target
list that has already gone stale once): apply chains/tempo/METHODOLOGY.md
section 4 (including the 4.1 numeric mapping added by this test) to Tempo
mainnet. Current target set: `TOKENS` below (9 TIP-20s) plus the chain
baseline (`score_chain_baseline`) plus `VAULT_V2_TARGETS` (3 Morpho Vault
V2 instances, `score_vault_v2`), 13 targets total -- see `TOKENS` and
`VAULT_V2_TARGETS` themselves, not this docstring, for the authoritative
live list.

Read-only JSON-RPC (eth_call, eth_getCode, eth_getLogs, eth_getStorageAt)
against the official endpoint https://rpc.tempo.xyz, every eth_call fact
re-read against the independent endpoint https://tempo-rpc.publicnode.com.
Role holders are enumerated either via real on-chain AccessControlEnumerable
getters where available, or from event logs over the full chain history on
the official endpoint (100,000-block windows, the endpoint's limit; two
different event schemes depending on the contract -- TIP-20's own
`RoleMembershipUpdated` via `scan_role_logs`, or OpenZeppelin's standard
`RoleGranted`/`RoleRevoked` via `_role_members_via_logs` for a generic
AccessControl contract), then confirmed one by one with hasRole on both
endpoints. No transaction, no key.

Usage:
    python3 chains/tempo/scripts/methodology_test.py          # full JSON (reads + scores)
    python3 chains/tempo/scripts/methodology_test.py scores   # scores only
"""
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

from eth_abi import decode, encode
from eth_utils import keccak, to_checksum_address

RPCS = ["https://rpc.tempo.xyz", "https://tempo-rpc.publicnode.com"]
LOG_RPC = RPCS[0]
LOG_WINDOW = 100_000

VALIDATOR_CONFIG_V2 = "0xCCCCCCCC00000000000000000000000000000001"
TIP403_REGISTRY = "0x403c000000000000000000000000000000000000"
LZ_ENDPOINT_V2 = "0x20Bb7C2E2f4e5ca2B4c57060d1aE2615245dCc9C"
ETHEREUM_EID = 30101
EIP1967_IMPL = "0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc"
EIP1967_ADMIN = "0xb53127684a568b3173ae13b9f8a6016e243e63b6e8ee1178d6a717850b5d6103"
SAFE_GUARD_SLOT = "0x4a204f620c8c5ccdca3fd54d003badd85ba500436a431f0cbda4f558c93c34c8"
SAFE_SENTINEL = "0x0000000000000000000000000000000000000001"

TOKENS = {
    "USDC.e": {"address": "0x20C000000000000000000000b9537d11c60E8b50", "lz_oapp": "0x19Ff94Fe4C93D546e4DB3E1FB124D45366B0b9F5"},
    "USDT0": {"address": "0x20c00000000000000000000014f22ca97301eb73", "lz_oapp": "0xaf37E8B6C9ED7f6318979f56Fc287d76c30847ff"},
    # ADDED 2026-09-17: pathUSD, Tempo's own native/first-party stablecoin
    # (the fee-fallback token, METHODOLOGY.md section 5) -- NOT bridged via
    # LayerZero (not listed among section 3.7's bridged assets), lz_oapp is
    # None on purpose, not an oversight (see score_token()'s own comment).
    # Second-largest stablecoin on Tempo by supply (~$39.3M live, bigger
    # than USDT0's ~$9.7M), a real flagship target by usage.
    "pathUSD": {"address": "0x20c0000000000000000000000000000000000000", "lz_oapp": None},
    # ADDED 2026-09-18: closing scouted_targets_2026-09-17-run2.md's own
    # funnel -- 6 new tokens fully resolved that run, plus the R2 gap
    # (section 8, open point 1) that had kept them "unresolved" (composite
    # 8) is closed the same day (see classify()'s new branches below).
    "USDB": {"address": "0x20c0000000000000000000003158081efd85bfc2", "lz_oapp": None},  # Bridge controller, same pattern as pathUSD
    "cbBTC": {"address": "0x20c000000000000000000000c412ec89d0c08be5", "lz_oapp": None},  # CCIP-bridged, not LayerZero
    "PRIME": {"address": "0x20c00000000000000000000058d0b8b2cfdb358c", "lz_oapp": None},  # CCIP-bridged, not LayerZero
    "DLUSD": {"address": "0x20c0000000000000000000006fd9a167923ba194", "lz_oapp": None},  # Bridge controller, same pattern as pathUSD/USDB
    "EURC.e": {"address": "0x20c0000000000000000000001621e21F71CF12fb", "lz_oapp": "0x7753Dc8d4bd48Db599Da21E08b1Ab1D6FDFfdC71"},
    "cUSD": {"address": "0x20c0000000000000000000000520792dcccccccc", "lz_oapp": "0xbD12E50Bfaa25735D074DBfDCF73208b9ccD2e43"},
}
ROLES = {r: ("0x" + keccak(text=r).hex().removeprefix("0x")) for r in ["ISSUER_ROLE", "PAUSE_ROLE", "UNPAUSE_ROLE", "BURN_BLOCKED_ROLE"]}
ROLES["DEFAULT_ADMIN_ROLE"] = "0x" + "00" * 32
ROLE_BY_HASH = {v: k for k, v in ROLES.items()}
# Section 4.1, rule R1: roles whose holders belong to the root-control set of a TIP-20.
# UNPAUSE_ROLE is excluded: it can only restore transfers.
ROOT_ROLES = ("DEFAULT_ADMIN_ROLE", "ISSUER_ROLE", "PAUSE_ROLE", "BURN_BLOCKED_ROLE")

# ADDED 2026-09-18: role constants for the generic OpenZeppelin AccessControl
# / TimelockController shapes classify() can now resolve (METHODOLOGY.md
# section 8, open point 1). These are DIFFERENT hashes from TIP-20's own
# ROLES above (TIP-20 is a precompile with its own role scheme; these are
# ordinary Solidity contracts using OZ's standard names) -- kept in a
# separate dict on purpose, not merged, to avoid a same-named-but-
# different-hash collision (TIP-20 has no PROPOSER/EXECUTOR/CANCELLER/
# BYPASSER/ADMIN_ROLE concept at all; conversely a TimelockController has
# no ISSUER_ROLE/PAUSE_ROLE concept).
TIMELOCK_ROLES = {r: ("0x" + keccak(text=r).hex()) for r in
                  ["PROPOSER_ROLE", "EXECUTOR_ROLE", "CANCELLER_ROLE", "BYPASSER_ROLE", "ADMIN_ROLE"]}
# EXECUTOR_ROLE and CANCELLER_ROLE are deliberately never resolved to
# holders anywhere in this file (see `_classify_timelock`'s own docstring)
# -- both are purely defensive/non-originating (EXECUTOR can only execute
# an already-scheduled, already-delayed action; CANCELLER can only cancel
# one), the same convention that already excludes TIP-20's UNPAUSE_ROLE.
# Their hashes stay in this dict anyway (computed the same self-verifying
# way as every other role hash in this file, never hardcoded) so a future
# reviewer who wants to add them back has the exact value ready, not a
# silent omission to rediscover.
DEFAULT_ADMIN_ROLE = "0x" + "00" * 32
# MCMS (Chainlink's ManyChainMultiSig, smartcontractkit/ccip-owner-contracts
# src/ManyChainMultiSig.sol) config shape: Config{ Signer[] signers,
# uint8[32] groupQuorums, uint8[32] groupParents }, Signer{ address addr,
# uint8 index, uint8 group }. getConfig() returns this as one struct.
MCMS_CONFIG_ABI = "((address,uint8,uint8)[],uint8[32],uint8[32])"
MCMS_NUM_GROUPS = 32

# ADDED 2026-09-18 -- closes scouted_targets_2026-09-17-run2.md section 8,
# open point 4 ("Morpho Vault V2 and market oracles need a written target
# type"). The 3 Morpho Vault V2 instances that section 3 fully resolved on
# Tempo mainnet (T1-T3; T4 Morpho Blue core and T5 the cbBTC/pathUSD market
# oracle are a DIFFERENT target shape -- no curator/adapter timelock concept
# -- left for a future pass, not silently folded in here). The selector
# dict itself (VAULT_V2_FUND_DESTINATION_SELECTORS) is defined further down,
# right after `selector()` exists to compute it from real signatures.
VAULT_V2_TARGETS = {
    "Sentora pathUSD (Morpho Vault V2)": "0x9a044AE05E5e6290DcF56afd69548565e957a626",
    "Unnamed pathUSD Vault V2 feeding Sentora": "0x83a1491f3e7f8dAAB8F787a631334b9ca7a87023",
    "Tempo Earn (Morpho Vault V2, Gauntlet-curated)": "0xC609656Ed9ef219c98C8e549bF729144F211f06E",
}

# ADDED 2026-09-19 (maintenance run, rule R9 in METHODOLOGY.md 4.1): Morpho
# Blue core, scouted as T4 in data/scouted_targets_2026-09-17-run2.md and
# left unwired until now. Address from 2 primary sources, re-checked this
# run: docs.morpho.org/get-started/resources/addresses (Tempo tab) and
# DefiLlama-Adapters projects/morpho-blue/config.js (`tempo.morphoBlue`,
# the adapter behind DefiLlama's "Morpho Blue" Tempo TVL, $42.6M read
# 2026-09-19 from api.llama.fi/protocols).
MORPHO_BLUE_TARGETS = {
    "Morpho Blue core": "0x10EE9AAC980A180dd4DcFc96C746d60B0EA88f97",
}

# ADDED 2026-09-20 (crossExposureScore convention decision, see
# cross_exposure()): the 9 owners of Morpho Association's global governance
# Safe, hardcoded as a dated, lowercased snapshot and compared against the
# FRESHLY read signer set of this file's own Morpho Blue core owner Safe.
# Never opens a second RPC connection to another chain from inside the
# scorer. Read live 2026-09-20 from Tempo (this core's owner Safe
# 0x645890a0...0fbbc, both RPCS, 5-of-9, 9 EOA signers) and diffed against
# the Morpho Blue owner Safe on Ethereum L1 (0xcBa28b38...9AFa, publicnode
# and 1rpc), on Base (same address as L1) and on Robinhood Chain
# (0x0605956...9728): all four are 5-of-9 with this exact 9-signer set,
# independently re-confirmed, not assumed from the shared protocol name.
# Same committee as chains/base-ecosystem/scorers.py
# `_KNOWN_ROBINHOOD_MORPHO_BLUE_OWNERS_2026_09_19`, kept as a separate copy
# because this file cannot import across ecosystems.
_KNOWN_MORPHO_BLUE_OWNERS_2026_09_20 = frozenset({
    "0x13ca8756e9470b71b8e998352c8741706217f963", "0x264c86dbbd2e4165fbbf0c35b0ddf0e00aec6b31",
    "0x30e7c016fc702cde9a50720a469d418490b7b652", "0x69fcefde2b48503d675181448b3d4272128bca9c",
    "0x84d3e4ee550dd5f99e76a548ac59a6be1c8dcf79", "0x8f02b4a44eacd9b8ee7739aa0ba58833dd45d002",
    "0xc100c251bdd297a66795112f04356e6ba5f89d80", "0xcf263cee139763114faafc5f52865135412f50ec",
    "0xe0aeb6811d33df42a09066857cdafca16b506086",
})
_MORPHO_BLUE_OVERLAP_NOTE = (
    "Real cross-chain finding, independently re-confirmed live 2026-09-20 on Tempo and on Ethereum L1: "
    "this target's root signer set is IDENTICAL (exact set, 9 signers) to the Morpho Blue owner Safe "
    "on Ethereum L1, Base and Robinhood Chain (Safe addresses differ, 5-of-9 at the 2026-09-20 "
    "snapshot everywhere) -- Morpho Association's own global governance committee, not assumed "
    "from the shared protocol name. crossExposureScore is capped at 80."
)


# ----------------------------------------------------------------------------- JSON-RPC
def rpc(url, method, params):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
    last = None
    for _ in range(4):
        r = subprocess.run(
            ["curl", "-s", "-m", "60", "-X", "POST", "-H", "Content-Type: application/json", "-d", body, url],
            capture_output=True, text=True,
        )
        try:
            out = json.loads(r.stdout)
        except json.JSONDecodeError:
            last = r.stdout[:200]
            continue
        if "error" in out:
            last = out["error"]
            if out["error"].get("code") == 3:  # execution reverted: deterministic
                return None
            continue
        return out["result"]
    raise RuntimeError(f"{url} {method}: {last}")


def selector(sig):
    return keccak(text=sig)[:4]


# ADDED 2026-09-18 -- see VAULT_V2_TARGETS above for why. Computed from the
# REAL function signatures in morpho-org/vault-v2 `src/VaultV2.sol` (fetched
# and read directly, not cited from memory) -- never hardcoded, the same
# self-verifying discipline ROLES/TIMELOCK_ROLES use. Cross-checked live:
# `selector("addAdapter(address)")` reproduces `0x60d54d41`, the exact value
# scouted_targets_2026-09-17-run2.md's own verification command already used
# against T1 (`timelock(bytes4)(uint256) 0x60d54d41`, "# addAdapter: 259200").
#
# This is the "fund-destination" path open point 4 asks for: the five
# curator selectors that can send vault funds somewhere NEW (a fresh
# adapter, a bigger cap) or remove an existing guardrail, as opposed to
# `setPerformanceFee`/`setIsSentinel`/etc., which cannot redirect funds.
# `setAdapterRegistry` is included because it can swap which registry of
# pre-approved adapters `addAdapter` is allowed to pull from.
VAULT_V2_FUND_DESTINATION_SELECTORS = {
    name: selector(sig) for name, sig in {
        "addAdapter": "addAdapter(address)",
        "removeAdapter": "removeAdapter(address)",
        "setAdapterRegistry": "setAdapterRegistry(address)",
        "increaseAbsoluteCap": "increaseAbsoluteCap(bytes,uint256)",
        "increaseRelativeCap": "increaseRelativeCap(bytes,uint256)",
    }.items()
}


def call(to, sig, arg_types=(), args=(), out_types=(), url=RPCS[0]):
    data = selector(sig) + (encode(list(arg_types), list(args)) if arg_types else b"")
    res = rpc(url, "eth_call", [{"to": to, "data": "0x" + data.hex()}, "latest"])
    if res is None or res == "0x":
        return None
    try:
        return decode(list(out_types), bytes.fromhex(res[2:]))
    except Exception:  # noqa: BLE001
        return None


def call2(*a, **kw):
    """Same eth_call on both endpoints. Raises if they disagree (a fact needs 2 sources)."""
    vals = [call(*a, url=u, **kw) for u in RPCS]
    norm = [json.dumps(_norm(v), sort_keys=True) for v in vals]
    if norm[0] != norm[1]:
        raise RuntimeError(f"RPC disagreement on {a}: {norm}")
    return vals[0]


def _norm(v):
    if isinstance(v, (list, tuple)):
        items = [_norm(x) for x in v]
        return sorted(items, key=str) if all(isinstance(x, str) for x in items) else items
    if isinstance(v, bytes):
        return v.hex()
    return v.lower() if isinstance(v, str) else v


def code(addr, url=RPCS[0]):
    return rpc(url, "eth_getCode", [addr, "latest"])


def storage_addr(addr, slot):
    vals = {rpc(u, "eth_getStorageAt", [addr, slot, "latest"]) for u in RPCS}
    if len(vals) != 1:
        raise RuntimeError(f"RPC disagreement on storage {addr} {slot}")
    v = int(vals.pop(), 16)
    return to_checksum_address("0x%040x" % v) if v else None


def _weakest_sort_key(r):
    """Section 4.1, rule R3's ordering (lower k weaker, equal k larger n
    weaker, unresolved -- k is None -- weakest of all), factored into one
    place. FIXES a real bug (scouted_targets_2026-09-17-run2.md section 8,
    open point 3): `classify()`'s own internal weakest-controller line used
    to call `min(resolved, key=lambda r: (r["k"], -r["n"]))` directly,
    which raises TypeError the moment ANY controller is unresolved (k is
    None, and None can't compare with an int) -- exactly the case that
    matters most (a controller that fails to resolve should score as the
    WORST case, not crash the whole scorer). The top-level `weakest()`
    function below already had the correct None-safe form; this reuses it
    instead of leaving two copies to drift apart again."""
    return (-1, 0) if r["k"] is None else (r["k"], -r["n"])


def _role_members_enumerable(addr, role_hash):
    """AccessControlEnumerable's real getters (getRoleMemberCount +
    getRoleMember), confirmed live against both RBACTimelock (CCIP) and the
    Bridge issuance controller (pathUSD/USDB/DLUSD) during 2026-09-18
    research -- both are genuinely enumerable, unlike a stock OpenZeppelin
    TimelockController (see `_role_members_via_logs` below). Returns None
    (not an empty list) if the contract doesn't support enumeration at all,
    so the caller can tell "no holders" apart from "can't enumerate"."""
    role_bytes = bytes.fromhex(role_hash[2:])
    cnt = call2(addr, "getRoleMemberCount(bytes32)", ("bytes32",), (role_bytes,), ("uint256",))
    if cnt is None:
        return None
    n = cnt[0]
    members = []
    for i in range(n):
        m = call2(addr, "getRoleMember(bytes32,uint256)", ("bytes32", "uint256"), (role_bytes, i), ("address",))
        if m:
            members.append(to_checksum_address(m[0]))
    return members


def _role_members_via_logs(addr, role_hash):
    """Fallback for a plain OpenZeppelin AccessControl contract (NOT
    AccessControlEnumerable -- confirmed for Cap's cUSD TimelockController
    during 2026-09-18 research, which reverts on getRoleMemberCount):
    scan the standard `RoleGranted`/`RoleRevoked` events (OZ's
    IAccessControl.sol, NOT the TIP-20-specific `RoleMembershipUpdated`
    `scan_role_logs` above reads -- a different event scheme entirely,
    kept separate on purpose) over the full chain history in LOG_WINDOW
    chunks, exactly the pagination discipline `scan_role_logs` already
    uses for TIP-20 tokens, then confirms each candidate live with
    `hasRole` (a revoked-then-regranted-elsewhere candidate must not be
    trusted from the log alone)."""
    role_topic = "0x" + keccak(text="RoleGranted(bytes32,address,address)").hex()
    role_bytes = bytes.fromhex(role_hash[2:])
    head = int(rpc(LOG_RPC, "eth_blockNumber", []), 16)

    def window(start):
        return rpc(LOG_RPC, "eth_getLogs", [{"fromBlock": hex(start), "toBlock": hex(min(start + LOG_WINDOW - 1, head)),
                                             "address": addr, "topics": [role_topic, "0x" + role_hash[2:]]}])
    logs = []
    with ThreadPoolExecutor(12) as ex:
        for res in ex.map(window, range(0, head + 1, LOG_WINDOW)):
            logs.extend(res)
    candidates = sorted({to_checksum_address("0x" + lg["topics"][2][-40:]) for lg in logs})
    return [a for a in candidates if call2(addr, "hasRole(bytes32,address)", ("bytes32", "address"), (role_bytes, a), ("bool",))[0]]


def _role_holders(addr, role_hash):
    """Dispatcher: try real on-chain enumeration first, fall back to a full
    historical log scan only when the contract doesn't support it."""
    members = _role_members_enumerable(addr, role_hash)
    if members is not None:
        return members
    return _role_members_via_logs(addr, role_hash)


def _classify_timelock(addr, min_delay, depth):
    """A TimelockController-shape contract (METHODOLOGY.md section 8, open
    point 1: 'OpenZeppelin TimelockController (Cap)' and 'Chainlink
    RBACTimelock + hierarchical MCMS (CCIP)' -- the SAME resolution path,
    since RBACTimelock is a modified TimelockController v4.7.0 with one
    extra role, confirmed against real source 2026-09-18). PROPOSER (can
    schedule a new action), BYPASSER (skips the delay entirely,
    RBACTimelock-only) and ADMIN_ROLE/DEFAULT_ADMIN_ROLE (added by
    adversarial review, 2026-09-18 -- see below) are treated as
    controlling roles. EXECUTOR and CANCELLER are NOT: EXECUTOR can only
    execute an already-scheduled, already-delayed action and CANCELLER can
    only cancel one, both purely defensive/non-originating, the same
    convention ROOT_ROLES already applies by excluding TIP-20's
    UNPAUSE_ROLE.

    FIXED 2026-09-18 (adversarial review, confirmed independently 3
    separate ways): this function used to omit ADMIN_ROLE/DEFAULT_ADMIN_ROLE
    entirely, even though it strictly dominates BYPASSER_ROLE in privilege
    -- on RBACTimelock, `onlyRoleOrAdminRole` lets an ADMIN_ROLE holder call
    `bypasserExecuteBatch` directly (real source confirmed:
    smartcontractkit/ccip-owner-contracts, no schedule/delay check at all,
    same as BYPASSER) AND grant/revoke ANY role including itself; on a
    plain TimelockController, DEFAULT_ADMIN_ROLE controls PROPOSER/
    EXECUTOR/CANCELLER membership, though it must still go through a fresh
    schedule (it cannot itself skip the delay the way RBACTimelock's
    ADMIN_ROLE can). Both live targets scored this pass (Cap's
    TimelockController and CCIP's RBACTimelock) happen to be
    self-administered (ADMIN_ROLE/DEFAULT_ADMIN_ROLE held only by the
    timelock's own address, confirmed live both ways), so this gap did not
    change any published number -- but a future target with an externally-
    or weakly-held admin role would have silently scored safer than it
    really is, with no signal that a role was skipped."""
    proposer_hash = TIMELOCK_ROLES["PROPOSER_ROLE"]
    bypasser_probe = call2(addr, "BYPASSER_ROLE()", out_types=("bytes32",))
    has_bypasser = bypasser_probe is not None
    admin_role_probe = call2(addr, "ADMIN_ROLE()", out_types=("bytes32",))
    paths = [("PROPOSER_ROLE", proposer_hash, min_delay)]
    if has_bypasser:
        paths.append(("BYPASSER_ROLE", TIMELOCK_ROLES["BYPASSER_ROLE"], 0))
    if admin_role_probe is not None:
        # RBACTimelock: ADMIN_ROLE can call bypasserExecuteBatch directly, delay=0.
        paths.append(("ADMIN_ROLE", TIMELOCK_ROLES["ADMIN_ROLE"], 0))
    else:
        # Plain OpenZeppelin TimelockController: DEFAULT_ADMIN_ROLE controls
        # role membership but must still go through a fresh schedule+delay
        # to actually execute anything -- credited with the real min_delay,
        # not 0.
        paths.append(("DEFAULT_ADMIN_ROLE", DEFAULT_ADMIN_ROLE, min_delay))
    candidates, delays = [], []
    for label, role_hash, delay in paths:
        holders = _role_holders(addr, role_hash)
        # Self-administration guard (found live, 2026-09-18: both real
        # targets this pass self-administer their own ADMIN_ROLE/
        # DEFAULT_ADMIN_ROLE, i.e. `addr` holds a role on itself). Recursing
        # classify() on `addr` again would re-enter this SAME function,
        # re-derive the SAME self-held ADMIN_ROLE again, and so on until
        # the depth>3 cutoff returns "unresolved" (k=None) -- which
        # `_weakest_sort_key` then treats as the weakest possible entry,
        # WRONGLY dragging the whole result to k=None even though PROPOSER/
        # BYPASSER resolved perfectly well. Self-administration is not a
        # genuinely separate weakest-key candidate anyway: reaching a
        # self-held admin role still requires going through PROPOSER
        # (schedule) or BYPASSER (immediate) to grant it to yourself, both
        # already tracked as their own paths -- so a self-held holder
        # contributes nothing new and is filtered out rather than chased.
        holders = [h for h in holders if to_checksum_address(h) != addr]
        if not holders:
            continue
        delays.append(delay)
        for h in holders:
            candidates.append(dict(via=label, delaySeconds=delay, **classify(h, depth + 1)))
    if not candidates:
        return {"address": addr, "kind": "unresolved contract (TimelockController, no resolvable proposer/bypasser)",
                "k": None, "n": None, "signers": [], "minDelaySeconds": 0}
    weakest_c = min(candidates, key=_weakest_sort_key)
    return {"address": addr, "kind": "TimelockController", "getMinDelaySeconds": min_delay, "hasBypasser": has_bypasser,
            "controllers": candidates, "k": weakest_c["k"], "n": weakest_c["n"],
            "signers": sorted({s for c in candidates for s in c["signers"]}),
            # R5b's own text: "shortest enforced delay over every path in the
            # root-control set" -- a BYPASSER path, when present, always
            # wins this min() since it is defined as delay=0, which is
            # exactly the finding this branch exists to surface (cbBTC/PRIME:
            # a 3h timelock that a SEPARATE, no-delay path can skip entirely).
            "minDelaySeconds": min(delays)}


def _classify_access_control_enumerable(addr, depth):
    """A plain AccessControlEnumerable contract with no TimelockController
    shape (no getMinDelay/PROPOSER_ROLE) -- METHODOLOGY.md section 8, open
    point 1's 'UUPS + AccessControlEnumerable (Bridge controller)' case
    (pathUSD/USDB/DLUSD's issuance controller). Resolves DEFAULT_ADMIN_ROLE
    holders (OZ's bytes32(0) convention), no delay concept at all."""
    holders = _role_members_enumerable(addr, DEFAULT_ADMIN_ROLE) or []
    if not holders:
        return {"address": addr, "kind": "unresolved contract (AccessControlEnumerable, no DEFAULT_ADMIN_ROLE holder)",
                "k": None, "n": None, "signers": [], "minDelaySeconds": 0}
    candidates = [classify(h, depth + 1) for h in holders]
    weakest_c = min(candidates, key=_weakest_sort_key)
    return {"address": addr, "kind": "AccessControlEnumerable", "controllers": candidates,
            "k": weakest_c["k"], "n": weakest_c["n"],
            "signers": sorted({s for c in candidates for s in c["signers"]}), "minDelaySeconds": 0}


def _mcms_flatten_quorum(signers, group_quorums, group_parents):
    """Chainlink ManyChainMultiSig's real on-chain shape
    (smartcontractkit/ccip-owner-contracts, ManyChainMultiSig.sol),
    confirmed 2026-09-18 against live getConfig() data on all 3 MCMS
    instances controlling cbBTC/PRIME (proposer/bypasser/canceller),
    independently re-derived from the raw struct (not trusted from a
    citation) and cross-checked to reproduce the exact numbers
    scouted_targets_2026-09-17-run2.md already published by hand
    (4-of-42, 8-of-47, 2-of-47): each Signer belongs to exactly one of 32
    groups; a group's own children are (a) every signer directly in it and
    (b) every OTHER group whose parent is it; a group is satisfied once
    `groupQuorums[g]` of its children are satisfied, and (since the tree is
    strict -- a signer belongs to exactly one leaf group) the cheapest way
    to satisfy a k-of-n group is always its k cheapest children. Root is
    group 0. Bottom-up dynamic programming, not a guess at a flat t-of-n."""
    from collections import defaultdict
    children_signers, children_groups = defaultdict(list), defaultdict(list)
    for s_addr, s_index, s_group in signers:
        children_signers[s_group].append(s_addr)
    for g in range(MCMS_NUM_GROUPS):
        if g != 0 and group_quorums[g] > 0:
            children_groups[group_parents[g]].append(g)

    def cost(g):
        if group_quorums[g] == 0:
            return None  # disabled group, contributes nothing
        options = [1 for _ in children_signers[g]]
        for sub in children_groups[g]:
            c = cost(sub)
            if c is not None:
                options.append(c)
        options.sort()
        q = group_quorums[g]
        if len(options) < q:
            return None  # cannot be satisfied at all -- misconfigured, treat as unresolved by the caller
        return sum(options[:q])

    return cost(0)


def _classify_mcms(addr, config):
    """Section 8, open point 1's 'hierarchical MCMS' case. Resolves to the
    SAME (k, n, signers) shape as Safe/LayerZero OneSig so admin_key_score/
    multisig_score/weakest() all work unchanged -- signers are taken
    directly from Config.signers, NOT recursively classify()'d (matching
    this file's own existing precedent: Safe/OneSig owners are recorded as
    the terminal signer set too, never chased further)."""
    signers, group_quorums, group_parents = config
    k = _mcms_flatten_quorum(signers, group_quorums, group_parents)
    signer_addrs = sorted({to_checksum_address(s[0]) for s in signers})
    if k is None:
        return {"address": addr, "kind": "unresolved contract (MCMS, root quorum unsatisfiable)",
                "k": None, "n": None, "signers": [], "minDelaySeconds": 0}
    return {"address": addr, "kind": "MCMS", "k": k, "n": len(signer_addrs), "signers": signer_addrs,
            "groupQuorums": [q for q in group_quorums if q > 0], "minDelaySeconds": 0}


# ------------------------------------------------------------------ authority resolution
def classify(addr, depth=0):
    """Section 4.1, rule R2: resolve an authority address to a key (k, n) description."""
    addr = to_checksum_address(addr)
    if depth > 3:
        # Defensive-only hard stop: none of the branches below are known to
        # cycle (MCMS terminates without recursing; the generic owner()/
        # EIP-1967/delegate branch already caps recursion at depth < 2), but
        # a misconfigured contract naming another as its own controller in a
        # loop should degrade to unresolved rather than recurse forever.
        return {"address": addr, "kind": "unresolved contract (max resolution depth)", "k": None, "n": None,
                "signers": [], "minDelaySeconds": 0}
    c = code(addr)
    if c == "0x":
        return {"address": addr, "kind": "EOA", "k": 1, "n": 1, "signers": [addr]}
    if c.startswith("0xef0100"):
        return {"address": addr, "kind": "EOA (EIP-7702 delegated)", "k": 1, "n": 1, "signers": [addr],
                "delegate": to_checksum_address("0x" + c[8:48])}
    safe_thr = call2(addr, "getThreshold()", out_types=("uint256",))
    safe_owners = call2(addr, "getOwners()", out_types=("address[]",))
    if safe_thr and safe_owners:
        mods = call2(addr, "getModulesPaginated(address,uint256)", ("address", "uint256"), (SAFE_SENTINEL, 20),
                     ("address[]", "address"))
        owners = [to_checksum_address(o) for o in safe_owners[0]]
        return {"address": addr, "kind": "Safe", "version": (call2(addr, "VERSION()", out_types=("string",)) or [None])[0],
                "singleton": storage_addr(addr, "0x0"), "k": safe_thr[0], "n": len(owners), "signers": owners,
                "signerKinds": sorted({("EOA" if code(o) == "0x" else "contract") for o in owners}),
                "modules": list(mods[0]) if mods else None, "guard": storage_addr(addr, SAFE_GUARD_SLOT),
                "nonce": (call2(addr, "nonce()", out_types=("uint256",)) or [None])[0]}
    os_thr = call2(addr, "threshold()", out_types=("uint256",))
    os_signers = call2(addr, "getSigners()", out_types=("address[]",))
    if os_thr and os_signers:
        signers = [to_checksum_address(o) for o in os_signers[0]]
        return {"address": addr, "kind": "LayerZero OneSig", "version": call2(addr, "VERSION()", out_types=("string",))[0],
                "k": os_thr[0], "n": len(signers), "signers": signers,
                "signerKinds": sorted({("EOA" if code(o) == "0x" else "contract") for o in signers}),
                "executorRequired": call2(addr, "executorRequired()", out_types=("bool",))[0],
                "executors": list(call2(addr, "getExecutors()", out_types=("address[]",))[0]),
                "nonce": call2(addr, "nonce()", out_types=("uint256",))[0]}
    # ADDED 2026-09-18 -- MUST come before the generic owner()/EIP-1967
    # fallback below: a TimelockController has no owner() at all (it's
    # role-based), and an MCMS's OWN owner() is the timelock that names it
    # as PROPOSER/BYPASSER -- resolving MCMS generically via owner() would
    # chase that circular reference instead of reading its real signer set.
    min_delay = call2(addr, "getMinDelay()", out_types=("uint256",))
    proposer_role = call2(addr, "PROPOSER_ROLE()", out_types=("bytes32",))
    if min_delay is not None and proposer_role is not None:
        return _classify_timelock(addr, min_delay[0], depth)
    mcms_config = call2(addr, "getConfig()", out_types=(MCMS_CONFIG_ABI,))
    if mcms_config is not None:
        return _classify_mcms(addr, mcms_config[0])
    admin_enumerable = call2(addr, "getRoleMemberCount(bytes32)", ("bytes32",), (bytes.fromhex(DEFAULT_ADMIN_ROLE[2:]),), ("uint256",))
    if admin_enumerable is not None:
        return _classify_access_control_enumerable(addr, depth)
    owner = call2(addr, "owner()", out_types=("address",))
    impl, padmin = storage_addr(addr, EIP1967_IMPL), storage_addr(addr, EIP1967_ADMIN)
    controllers = []
    if owner and int(owner[0], 16):
        controllers.append(("owner()", owner[0]))
    if padmin:
        pa_owner = call2(padmin, "owner()", out_types=("address",))
        controllers.append(("EIP-1967 admin -> owner()", pa_owner[0] if pa_owner else padmin))
    # ADDED 2026-09-18 -- METHODOLOGY.md section 8, open point 1's 4th
    # controller type: "the LayerZero endpoint delegate as a zero-delay path
    # next to an owner timelock". A registered OApp's delegate can
    # reconfigure its inbound message verification (receive library, DVN
    # set) in ONE transaction with NO owner-timelock gating at all
    # (LayerZero-Labs/LayerZero-v2 EndpointV2.sol's `_assertAuthorized`
    # treats `msg.sender == delegates[oapp]` as fully equivalent to
    # `msg.sender == oapp` itself -- confirmed against real source
    # 2026-09-18). Folded in as a THIRD parallel controller candidate,
    # exactly like owner() and the EIP-1967 admin already are, rather than
    # left in `notes` only (R6b) where it can't affect adminKeyScore/
    # multisigScore/timelockScore at all -- this is a no-op for a contract
    # that isn't a registered OApp (delegates() returns the zero address).
    delegate = call2(LZ_ENDPOINT_V2, "delegates(address)", ("address",), (addr,), ("address",))
    if delegate and int(delegate[0], 16):
        controllers.append(("LayerZero EndpointV2 delegate", delegate[0]))
    if depth < 2 and controllers:
        resolved = [dict(via=v, **classify(a, depth + 1)) for v, a in controllers]
        # FIXED 2026-09-18 (scouted_targets_2026-09-17-run2.md section 8,
        # open point 3): this used to be `min(resolved, key=lambda r: (r["k"],
        # -r["n"]))`, which raised TypeError the moment ANY controller
        # resolved to "unresolved" (k=None) -- happened on cbBTC, PRIME and
        # cUSD in that scouting run. Now shares `_weakest_sort_key` with the
        # top-level `weakest()` below instead of a second, divergent copy.
        weakest_c = min(resolved, key=_weakest_sort_key)
        return {"address": addr, "kind": "contract", "proxyImplementation": impl, "proxyAdmin": padmin,
                "controllers": resolved, "k": weakest_c["k"], "n": weakest_c["n"],
                "signers": sorted({s for r in resolved for s in r["signers"]}),
                "minDelaySeconds": min((r.get("minDelaySeconds", 0) for r in resolved), default=0)}
    return {"address": addr, "kind": "unresolved contract", "k": None, "n": None, "signers": [], "minDelaySeconds": 0}


def weakest(keys):
    """Section 4.1, rule R3 (same ordering as chains/hyperliquid rule 4.2): lower k is weaker,
    on equal k larger n is weaker. Unresolved keys are the weakest of all."""
    return min(keys, key=_weakest_sort_key)


# ----------------------------------------------------------------------- numeric mapping
def admin_key_score(key):
    if key is None:
        return 100  # empty root-control set: every root role renounced, no policy admin
    if key["k"] is None:
        return 20  # unresolved contract (repo convention, scripts/lib/scorers.py)
    k, n = key["k"], key["n"]
    if k >= 3:
        return 65
    if k == 2:
        return 50
    return 10 if n == 1 else 5


def multisig_score(key):
    if key is None:
        return 100
    if key["k"] is None:
        return 0
    k, n = key["k"], key["n"]
    if k == 1:
        return 15 if n == 1 else max(0, 14 - 2 * (n - 1))
    return max(16, min(100, 20 * k - (n - k)))


def timelock_score(min_delay_seconds):
    if not min_delay_seconds:
        return 0
    h = min_delay_seconds / 3600
    return 20 if h < 24 else 35 if h < 48 else 60 if h < 168 else 80


def composite(a, m, t):
    # Exact-integer form, not math.floor(0.4*a+0.3*m+0.3*t+0.5) -- that float form reads one LOWER
    # than exact on 2054/1,030,301 (a,m,t) triples (scripts/lib/scorers.py, scripts/
    # validate_all_scorers.py; same defect found and fixed in the audit_rotation_index* family,
    # commit e8ad7d5 -- this is the same bug in a sibling live re-derivation script).
    return (4 * a + 3 * m + 3 * t + 5) // 10


# --------------------------------------------------------------------------------- reads
def scan_role_logs(addresses):
    topics = [("0x" + keccak(text=s).hex().removeprefix("0x")) for s in (
        "RoleMembershipUpdated(bytes32,address,address,bool)", "RoleAdminUpdated(bytes32,bytes32,address)",
        "TransferPolicyUpdate(address,uint64)")]
    head = int(rpc(LOG_RPC, "eth_blockNumber", []), 16)

    def window(start):
        return rpc(LOG_RPC, "eth_getLogs", [{"fromBlock": hex(start), "toBlock": hex(min(start + LOG_WINDOW - 1, head)),
                                             "address": addresses, "topics": [topics]}])
    logs = []
    with ThreadPoolExecutor(12) as ex:
        for res in ex.map(window, range(0, head + 1, LOG_WINDOW)):
            logs.extend(res)
    logs.sort(key=lambda l: (int(l["blockNumber"], 16), int(l["logIndex"], 16)))
    out = {to_checksum_address(a): [] for a in addresses}
    for lg in logs:
        t = lg["topics"]
        ev = {"block": int(lg["blockNumber"], 16), "tx": lg["transactionHash"]}
        if t[0] == topics[0]:
            ev.update(event="RoleMembershipUpdated", role=ROLE_BY_HASH.get(t[1], t[1]),
                      account=to_checksum_address("0x" + t[2][-40:]), granted=int(lg["data"], 16) == 1)
        elif t[0] == topics[1]:
            ev.update(event="RoleAdminUpdated", role=ROLE_BY_HASH.get(t[1], t[1]), newAdminRole=ROLE_BY_HASH.get(t[2], t[2]))
        else:
            ev.update(event="TransferPolicyUpdate", newPolicyId=int(t[2], 16))
        out[to_checksum_address(lg["address"])].append(ev)
    return head, out


def lz_inbound(oapp):
    delegate = call2(LZ_ENDPOINT_V2, "delegates(address)", ("address",), (oapp,), ("address",))[0]
    lib = call2(LZ_ENDPOINT_V2, "getReceiveLibrary(address,uint32)", ("address", "uint32"), (oapp, ETHEREUM_EID), ("address", "bool"))[0]
    raw = call2(LZ_ENDPOINT_V2, "getConfig(address,address,uint32,uint32)", ("address", "address", "uint32", "uint32"),
                (oapp, lib, ETHEREUM_EID, 2), ("bytes",))[0]
    conf, req_count, opt_count, opt_thr, req, opt = decode(["(uint64,uint8,uint8,uint8,address[],address[])"], raw)[0]
    return {"srcEid": ETHEREUM_EID, "endpointDelegate": delegate, "receiveLibrary": lib, "confirmations": conf,
            "requiredDVNs": list(req), "optionalDVNs": list(opt), "optionalDVNThreshold": opt_thr}


def score_chain_baseline():
    owner = call2(VALIDATOR_CONFIG_V2, "owner()", out_types=("address",))[0]
    key = classify(owner)
    vals = call2(VALIDATOR_CONFIG_V2, "getActiveValidators()",
                 out_types=("(bytes32,address,string,string,address,uint64,uint64,uint64)[]",))[0]
    a, m, t = admin_key_score(key), multisig_score(key), timelock_score(key.get("minDelaySeconds", 0))
    return {
        "target": "Tempo L1 validator registry (ValidatorConfigV2)", "address": VALIDATOR_CONFIG_V2,
        "reads": {"owner": key, "activeValidatorEntries": len(vals), "precompileCode": code(VALIDATOR_CONFIG_V2)},
        "rootControlSet": [key], "weakestKey": {"k": key["k"], "n": key["n"], "address": key["address"]},
        "adminKeyScore": a, "multisigScore": m, "timelockScore": t, "oracleAuthorityScore": 100,
        "compositeScore": composite(a, m, t),
    }


def score_token(label, token, lz_oapp, events):
    token = to_checksum_address(token)
    reads = {
        "name": call2(token, "name()", out_types=("string",))[0],
        "totalSupply": call2(token, "totalSupply()", out_types=("uint256",))[0],
        "decimals": call2(token, "decimals()", out_types=("uint8",))[0],
        "transferPolicyId": call2(token, "transferPolicyId()", out_types=("uint64",))[0],
        "paused": call2(token, "paused()", out_types=("bool",))[0],
        "supplyCap": call2(token, "supplyCap()", out_types=("uint256",))[0],
        "codeIsPrecompileMarker": code(token) == "0xef",
    }
    candidates = sorted({e["account"] for e in events if e["event"] == "RoleMembershipUpdated"})
    holders = {r: [] for r in ROLES}
    for acct in candidates:
        for r, h in ROLES.items():
            if call2(token, "hasRole(address,bytes32)", ("address", "bytes32"), (acct, bytes.fromhex(h[2:])), ("bool",))[0]:
                holders[r].append(acct)
    reads["roleHoldersNow"] = holders
    reads["roleAdminChanges"] = [e for e in events if e["event"] == "RoleAdminUpdated"]
    root = []
    for r in ROOT_ROLES:
        for acct in holders[r]:
            root.append(dict(role=r, **classify(acct)))
    pid = reads["transferPolicyId"]
    if pid >= 2:
        ptype, padmin = call2(TIP403_REGISTRY, "policyData(uint64)", ("uint64",), (pid,), ("uint8", "address"))
        reads["policy"] = {"id": pid, "type": ["WHITELIST", "BLACKLIST"][ptype], "admin": padmin}
        root.append(dict(role=f"TIP-403 policy {pid} admin", **classify(padmin)))
    else:
        reads["policy"] = {"id": pid, "type": "always-reject" if pid == 0 else "always-allow", "admin": None}
    # FIXED 2026-09-17 (extending coverage to pathUSD): lz_oapp used to be
    # required and unconditionally read here -- fine for every token scored
    # so far (USDC.e, USDT0), which are all bridged via a LayerZero OFT, but
    # pathUSD is Tempo's own native/first-party stablecoin (the fee-fallback
    # token cited in METHODOLOGY.md section 5, not listed among the bridged
    # assets in section 3.7) with no LayerZero OApp to read at all. None
    # here means "not a bridged asset", recorded as a fact, not skipped
    # silently.
    reads["layerZeroInbound"] = lz_inbound(lz_oapp) if lz_oapp else None
    key = weakest(root) if root else None
    # FIXED 2026-09-18 (closes METHODOLOGY.md section 8, open point 1):
    # timelockScore used to be hardcoded to timelock_score(0) -- correct for
    # every target scored before this pass (Safe/OneSig/EOA/unresolved all
    # have delay=0 by construction), but wrong now that classify() can
    # resolve a real TimelockController. Per R5b's own text ("shortest
    # enforced delay over EVERY PATH in the root-control set"), this is the
    # minimum over ALL of root, not just the single k/n-weakest entry --
    # `key` above answers "who is the weakest key", this answers "what is
    # the shortest delay ACROSS all of them", two different questions R5b
    # deliberately keeps separate.
    delay = min((r.get("minDelaySeconds", 0) for r in root), default=0)
    a, m, t = admin_key_score(key), multisig_score(key), timelock_score(delay)
    return {
        "target": label, "address": token, "reads": reads, "rootControlSet": root,
        "weakestKey": None if key is None else {"k": key["k"], "n": key["n"], "address": key["address"], "role": key["role"]},
        "adminKeyScore": a, "multisigScore": m, "timelockScore": t, "oracleAuthorityScore": 100,
        "compositeScore": composite(a, m, t),
    }


def _vault_v2_timelock(vault):
    """ADDED 2026-09-18 (open point 4). Reads `abdicated(bytes4)`/
    `timelock(bytes4)` for every selector in
    VAULT_V2_FUND_DESTINATION_SELECTORS and returns the minimum enforced
    delay in seconds over every NON-abdicated one.

    A selector Morpho VaultV2 reports as abdicated can never be un-abdicated
    (confirmed against real source, morpho-org/vault-v2 `src/VaultV2.sol`
    `abdicate()`: sets `abdicated[selector] = true` permanently, no reverse
    function exists anywhere in the contract) -- that specific fund-
    destination path is not merely delayed, it is permanently closed, which
    is a STRONGER guarantee than any finite delay. Rather than invent a new
    score band for "permanently closed", this reuses timelock_score()'s own
    existing top band (delay >= 7 days -> 80) by returning a delay of
    exactly 7 days when every tracked selector is abdicated -- the same
    scale every other Tempo target's timelockScore already reads through,
    not a special case bolted on.

    Live-verified 2026-09-18 against all 3 VAULT_V2_TARGETS: T1 (Sentora
    pathUSD) -- setAdapterRegistry abdicated, the other 4 not, minimum
    259200s (addAdapter/increaseAbsoluteCap/increaseRelativeCap all 3 days,
    removeAdapter 7 days) -- matches
    scouted_targets_2026-09-17-run2.md section 5's own live table exactly.
    T2 -- addAdapter/removeAdapter abdicated, the other 3 (setAdapterRegistry,
    both cap increases) not abdicated with delay 0 each -- minimum 0s,
    also an exact match. T3 (Tempo Earn) -- setAdapterRegistry abdicated,
    minimum 259200s (both cap increases; add/removeAdapter are 7 days) --
    exact match again."""
    delays = []
    for sel in VAULT_V2_FUND_DESTINATION_SELECTORS.values():
        abd = call2(vault, "abdicated(bytes4)", ("bytes4",), (sel,), ("bool",))
        if abd is not None and abd[0]:
            continue  # permanently renounced -- no path, excluded from the minimum
        tl = call2(vault, "timelock(bytes4)", ("bytes4",), (sel,), ("uint256",))
        delays.append(tl[0] if tl else 0)
    if not delays:
        return 7 * 86400  # every fund-destination path permanently closed: top band of timelock_score()
    return min(delays)


def score_vault_v2(label, vault):
    """ADDED 2026-09-18: closes scouted_targets_2026-09-17-run2.md section 8,
    open point 4 ("Morpho Vault V2 and market oracles need a written target
    type"). A NEW Tempo target shape, not an R2 hop: `owner`/`curator` are
    plain public state vars on morpho-org/vault-v2 `src/VaultV2.sol`
    (confirmed against real source), each resolved through the SAME
    classify()/weakest() rules R2/R3 every other Tempo target already uses
    -- no new address-resolution logic needed, since owner/curator on the 3
    live targets are themselves a Safe or a plain EOA, shapes classify()
    already handles. What IS new is the timelock dimension: instead of one
    `getMinDelay()`, R5b here reads the per-selector fund-destination delay
    (`_vault_v2_timelock` above).

    Root-control set is deliberately {owner, curator} only -- allocators and
    sentinels are excluded from the NUMERIC set, the same convention already
    applied to TIP-20's UNPAUSE_ROLE (R1) and TimelockController's EXECUTOR/
    CANCELLER (`_classify_timelock`): all are real but bounded, non-
    originating powers, confirmed against real source (VaultV2.sol's
    `allocate`/`deallocate` can only move funds among adapters the curator
    has ALREADY approved, within caps the curator has ALREADY set;
    `setIsSentinel`'s own holder can only revoke/decrease/deallocate, never
    add a destination or raise a cap) -- real operational risk, but not a
    NEW fund destination, so left out of the set the admin/multisig/timelock
    scores are built on rather than silently inflating it.

    Cross-checked 2026-09-18 against scouted_targets_2026-09-17-run2.md
    section 4's own "resolved reading (proposal)" column, independently
    re-derived here (not copied): T1 (owner Safe 1-of-1, curator Safe 1-of-1,
    weakest key (1,1), delay 259200s) scores 10/15/60/27, an EXACT match to
    that row's "T1 curator 1-of-1 + 3 days = 10 / 15 / 60 / 27". T3 (owner
    Safe 4-of-7, curator Safe 3-of-7, weakest key the curator's (3,7), delay
    259200s) scores 65/56/60/61, an EXACT match to "T3 curator 3-of-7 + 3
    days = 65 / 56 / 60 / 61". T2 (owner = curator = one plain EOA, delay
    0s -- addAdapter/removeAdapter abdicated but the 3 cap/registry selectors
    are not) scores 10/15/0/9; that row's proposal column has no T2 example
    to compare against, so this is this pass's own first reading, not a
    reproduction."""
    owner = call2(vault, "owner()", out_types=("address",))
    curator = call2(vault, "curator()", out_types=("address",))
    root = []
    if owner and int(owner[0], 16):
        root.append(dict(role="owner", **classify(owner[0])))
    if curator and int(curator[0], 16):
        root.append(dict(role="curator", **classify(curator[0])))
    key = weakest(root) if root else None
    delay = _vault_v2_timelock(vault)
    a, m, t = admin_key_score(key), multisig_score(key), timelock_score(delay)
    return {
        "target": label, "address": vault, "kind": "Morpho Vault V2",
        "reads": {"owner": owner[0] if owner else None, "curator": curator[0] if curator else None,
                  "fundDestinationDelaySeconds": delay},
        "rootControlSet": root,
        "weakestKey": None if key is None else {"k": key["k"], "n": key["n"], "address": key["address"], "role": key["role"]},
        "adminKeyScore": a, "multisigScore": m, "timelockScore": t, "oracleAuthorityScore": 100,
        "compositeScore": composite(a, m, t),
    }


def score_morpho_blue(label, core):
    """ADDED 2026-09-19 (rule R9). Morpho Blue core (morpho-org/morpho-blue
    `src/Morpho.sol`, read directly): the ONLY privileged address is
    `owner`, and its `onlyOwner` functions are exactly `setOwner`,
    `enableIrm`, `enableLltv`, `setFee` (capped at MAX_FEE = 25% of
    interest, ConstantsLib.sol) and `setFeeRecipient`. No proxy (immutable
    contract, both EIP-1967 slots read empty live), no pause, no role to
    move funds, and market parameters (including each market's oracle) are
    fixed at `createMarket`, which is permissionless. Root-control set =
    {owner}, resolved through R2/R3 unchanged. No timelock exists on any
    owner function, so R5b gives 0. oracleAuthorityScore stays 100 (R5c):
    the core's owner has no power over any market's price source -- the
    per-market oracle authority is a different target shape (T5 in
    scouted_targets_2026-09-17-run2.md), still open, not folded in here.

    Live-verified 2026-09-19 on both RPCS: owner = Safe 1.4.1 5-of-9
    `0x645890a0...0fbbc`, no module, no guard, 9 EOA signers, the same 9
    signers and threshold as Morpho's Ethereum owner `0xcBa28b38...9AFa`,
    feeRecipient = zero address. Scores 65/96/0/55 (composite; crossExposureScore is
    not a composite input).

    CORRECTED 2026-09-20: that shared 9-signer committee used to be kept out
    of the score (R6b context only, crossExposureScore 100). It is now folded
    into crossExposureScore = 80 by cross_exposure() below, which compares
    this target's freshly read signer set to
    `_KNOWN_MORPHO_BLUE_OWNERS_2026_09_20`. Nothing changes in the five
    score fields this function itself returns (crossExposureScore is set
    afterwards by cross_exposure())."""
    core = to_checksum_address(core)
    owner = call2(core, "owner()", out_types=("address",))
    root = []
    if owner and int(owner[0], 16):
        root.append(dict(role="owner", **classify(owner[0])))
    key = weakest(root) if root else None
    delay = min((r.get("minDelaySeconds", 0) for r in root), default=0)
    a, m, t = admin_key_score(key), multisig_score(key), timelock_score(delay)
    fee_recipient = call2(core, "feeRecipient()", out_types=("address",))
    return {
        "target": label, "address": core, "kind": "Morpho Blue core",
        "reads": {"owner": owner[0] if owner else None, "feeRecipient": fee_recipient[0] if fee_recipient else None,
                  "proxyImplementation": storage_addr(core, EIP1967_IMPL)},
        "rootControlSet": root,
        "weakestKey": None if key is None else {"k": key["k"], "n": key["n"], "address": key["address"], "role": key["role"]},
        "adminKeyScore": a, "multisigScore": m, "timelockScore": t, "oracleAuthorityScore": 100,
        "compositeScore": composite(a, m, t),
    }


def cross_exposure(results):
    """Section 4.1, rule R6: contract semantics. 100 - 20 per OTHER tracked Tempo target
    sharing at least one root signer, floored at 0.

    CORRECTED 2026-09-20 (crossExposureScore convention: the field means "does the same
    root signer also control ANOTHER tracked target", cross-ecosystem overlaps included):
    a target whose root signer set is exactly `_KNOWN_MORPHO_BLUE_OWNERS_2026_09_20`
    (Morpho Association's committee, also the owner of the tracked Morpho Blue cores on
    Ethereum L1, Base and Robinhood Chain) is capped at 80, the flat value the other
    ecosystems use for a cross-chain committee match. min(), so this never raises a value
    the within-Tempo rule already lowered, and a mismatch (or an unresolved, empty signer
    set) leaves the within-Tempo value untouched. The finding goes to that target's
    `notes`, not to any new result key."""
    signer_sets = [{s.lower() for k in r["rootControlSet"] for s in k["signers"]} for r in results]
    for i, r in enumerate(results):
        shared = [results[j]["target"] for j in range(len(results)) if j != i and signer_sets[i] & signer_sets[j]]
        within_tempo = max(0, 100 - 20 * len(shared))
        r["crossExposureScore"] = within_tempo
        r["sharedRootSignersWith"] = shared
        if signer_sets[i] == _KNOWN_MORPHO_BLUE_OWNERS_2026_09_20:
            r["crossExposureScore"] = min(within_tempo, 80)
            r.setdefault("notes", {})["crossChainSignerOverlap"] = _MORPHO_BLUE_OVERLAP_NOTE


def main():
    head, events = scan_role_logs([t["address"] for t in TOKENS.values()])
    results = [score_chain_baseline()]
    for label, t in TOKENS.items():
        results.append(score_token(label, t["address"], t["lz_oapp"], events[to_checksum_address(t["address"])]))
    for label, addr in VAULT_V2_TARGETS.items():
        results.append(score_vault_v2(label, addr))
    for label, addr in MORPHO_BLUE_TARGETS.items():
        results.append(score_morpho_blue(label, addr))
    cross_exposure(results)
    base = results[0]["compositeScore"]
    for r in results[1:]:
        # CORRECTED 2026-09-20: used to overwrite `notes`, which would now drop the
        # cross-chain finding cross_exposure() may have put there.
        r["notes"] = {"chainCappedComposite": min(r["compositeScore"], base), **r.get("notes", {})}
    if sys.argv[1:] == ["scores"]:
        cols = ["adminKeyScore", "multisigScore", "timelockScore", "oracleAuthorityScore", "crossExposureScore", "compositeScore"]
        print(json.dumps([{"target": r["target"], **{c: r[c] for c in cols}, **r.get("notes", {})} for r in results], indent=1))
    else:
        print(json.dumps({"logScanHead": head, "roleEvents": events, "results": results}, indent=1, default=str))


if __name__ == "__main__":
    main()
