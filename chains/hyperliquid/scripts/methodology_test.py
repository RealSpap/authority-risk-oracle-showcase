"""Methodology test (2026-09-16): apply chains/hyperliquid/METHODOLOGY.md section 4
(including the 4.6 numeric mapping added by this test) to two live HyperCore targets:

  1. the `xyz` HIP-3 perp dex (trade[XYZ]), keyed by its deployer address
  2. the Hyperliquid L1 itself (validator set, validator-operated perps), keyed by the
     synthetic identifier of section 4.7

Read-only: official info API https://api.hyperliquid.xyz/info and the official
HyperEVM RPC. No transaction, no key.

Usage:
    python3 chains/hyperliquid/scripts/methodology_test.py          # full JSON
    python3 chains/hyperliquid/scripts/methodology_test.py scores   # scores only
"""
import json
import subprocess
import sys

API = "https://api.hyperliquid.xyz/info"
EVM_RPC = "https://rpc.hyperliquid.xyz/evm"

# Section 4.1: actions that can directly move positions or re-grant authority.
ROOT_CONTROL_VARIANTS = ("haltTrading",)  # setSubDeployers is deployer-only (not delegable)
ORACLE_VARIANTS = ("setOracle",)


def _post(url, body):
    r = subprocess.run(
        ["curl", "-s", "-m", "30", "-X", "POST", "-H", "Content-Type: application/json", "-d", json.dumps(body), url],
        capture_output=True, text=True, check=True,
    )
    return json.loads(r.stdout)


def info(body):
    return _post(API, body)


class HyperEvmRpcError(Exception):
    """Raised when the RPC returns a JSON-RPC error object that is NOT a confirmed revert (rate
    limit, an internal node error, any error code other than 3) instead of a `result`.

    NARROWED 2026-09-22: until this date, `evm()` raised this same exception for BOTH a genuine
    revert (the common, expected case -- e.g. calling getOwners() on a contract that isn't a Safe
    at all) AND a real RPC-level problem, and the 4 call sites in this file that catch it degraded
    both the same way (conservative unresolved, (20, 0, 0)). That conflated exactly the case this
    project's own web3_utils.RpcUnavailable exists to separate elsewhere: a transient RPC failure
    silently retiring a scoring dimension to its floor under load, indistinguishable in the output
    from a confirmed "this isn't the right interface." `evm()` now inspects the JSON-RPC error code
    -- 3 means "execution reverted" (the same convention chains/tempo/scripts/methodology_test.py's
    `rpc()` already keys on) and is raised as HyperEvmReadError instead, this file's existing bucket
    for "not this interface, degrade gracefully." Every OTHER error code lands here, and the 4 call
    sites that used to catch this too now let it propagate to score_all()'s per-scorer SKIPPED
    isolation instead of degrading a target from an ambiguous failure. This class's original
    surfacing case (HIP-3 dex `para`'s own StakingVault infrastructure, 2026-09-17, whose
    MANAGER_ROLE holder is itself an EIP-1967 proxy that reverts on getOwners()) is unaffected: that
    revert still comes back as HyperEvmReadError and read_safe_hyperevm still treats it as "not a
    Safe," not a crash -- only a NON-revert RPC error changed which way it degrades."""


def evm(method, params):
    resp = _post(EVM_RPC, {"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
    if "result" not in resp:
        error = resp.get("error") or {}
        if error.get("code") == 3:  # execution reverted, deterministic -- see HyperEvmReadError below
            raise HyperEvmReadError(f"{method}({params}): execution reverted -- {error}")
        raise HyperEvmRpcError(f"{method}({params}): RPC returned no result -- {error}")
    return resp["result"]


def _selector(sig):
    # HexBytes.hex() in this project's web3.py version does NOT include a
    # "0x" prefix -- a first attempt sliced [2:10] assuming it did, silently
    # producing the wrong 4 bytes (shifted by one byte) for every selector.
    # Caught by comparing against the already-known-correct selectors used
    # by hand during this same investigation (e.g. getOwners() = 0xa0e67e2b)
    # before this function was written into scorer code, not after.
    from web3 import Web3
    return "0x" + Web3.keccak(text=sig).hex()[0:8]


def _eth_call(to, data):
    return evm("eth_call", [{"to": to, "data": data}, "latest"])


GUARD_STORAGE_SLOT = "0x4a204f620c8c5ccdca3fd54d003badd85ba500436a431f0cbda4f558c93c34c8"
EIP1967_IMPLEMENTATION_SLOT = "0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc"


class HyperEvmReadError(Exception):
    """Raised when a HyperEVM read doesn't decode as the shape it was
    expected to be (e.g. a target address that isn't actually a Gnosis
    Safe), OR -- since 2026-09-22 -- when evm() itself gets a confirmed
    "execution reverted" (JSON-RPC error code 3) response: the contract
    answering "not this interface" belongs in this bucket, not
    HyperEvmRpcError (a real RPC-level problem), so the callers that catch
    this exception to degrade gracefully keep doing exactly that for a
    revert, while a genuine RPC failure now propagates instead -- see
    HyperEvmRpcError's own docstring. FIXED 2026-09-17 (closed an adversarial-review finding): the
    original version of read_safe_hyperevm had no such check, so a target
    that returned a single, unrelated 32-byte word instead of a real
    ABI-encoded (address[], uint256) response would silently decode to an
    empty owners list and a nonsensical threshold (e.g. "5-of-0") with no
    error and no warning, rather than failing loudly the way
    scripts/lib/web3_utils.py::safe_owners_and_threshold's try/except ->
    None -> caller's conservative-fallback convention already does for the
    identical pattern on the Robinhood Chain side of this project."""


def _address_from_hex(raw, context):
    # FIXED 2026-09-17 (closed an adversarial-review finding): a short or
    # empty `raw` (e.g. "0x", the real eth_call return value for a no-code
    # address) used to silently slice into a malformed "0x0x" string via
    # `"0x" + raw[-40:]` -- Python's negative-index slicing does not raise
    # on a too-short string, it just returns the string unchanged. That
    # value would then propagate two or three calls further before
    # finally failing with a generic, confusing `ValueError` deep inside
    # an unrelated decode step. Fail immediately, at the actual point of
    # the bad read, with a message that names what was being resolved.
    if len(raw) < 42:
        raise HyperEvmReadError(f"{context}: expected a 32-byte word encoding an address, got {raw!r} (likely a no-code/empty eth_call result)")
    return "0x" + raw[-40:]


def _bytes_from_hex(raw, context):
    # FIXED 2026-09-17 (closed an adversarial-review finding, confirmed by
    # independent re-verification): `bytes.fromhex(raw[2:])` raises a bare
    # built-in `ValueError` on malformed hex (odd length, non-hex chars --
    # plausible from a glitching/non-compliant RPC provider, not just a
    # contract-level issue). That ValueError is NOT a HyperEvmReadError or
    # HyperEvmRpcError, so it silently slipped past every `except
    # (HyperEvmReadError, HyperEvmRpcError)` clause in this file, including
    # `_classify_authority_holder`'s -- the exact "uncategorized crash"
    # class this file's other helpers were already hardened against.
    # `read_safe_hyperevm` had this same gap in its two `bytes.fromhex`
    # calls even after its FIRST hardening pass (that pass added shape
    # validation AFTER the conversion, not around the conversion itself).
    try:
        return bytes.fromhex(raw[2:])
    except ValueError as e:
        raise HyperEvmReadError(f"{context}: result is not well-formed hex: {raw!r} ({e})")


def read_safe_hyperevm(address):
    """Gnosis Safe owners/threshold/modules/guard on HyperEVM -- the same
    facts and the same slot constant `scripts/lib/scorers.py::
    _safe_guard_and_modules` already uses on the Robinhood Chain side of
    this project (re-derived independently here rather than imported,
    since no ecosystem's scorers.py imports another's -- confirmed by
    checking every chains/*/scorers.py has zero cross-ecosystem imports).

    FIXED 2026-09-17 (closed an adversarial-review finding): raises
    HyperEvmReadError if the decoded shape is not a structurally possible
    Safe (threshold > owner count, or a response too short to have
    contained a real ABI-encoded dynamic array) instead of silently
    returning a fabricated, self-contradictory result like "5-of-0" with
    no warning. Callers must catch this and degrade, the same convention
    `_safe_rooted_entry` already follows for the EVM-side helper this
    function deliberately does not import."""
    owners_raw = _eth_call(address, _selector("getOwners()"))
    threshold_raw = _eth_call(address, _selector("getThreshold()"))
    threshold = int(threshold_raw, 16)
    data = _bytes_from_hex(owners_raw, f"{address} getOwners()")
    if len(data) < 64:
        raise HyperEvmReadError(f"{address}: getOwners() response too short to be a real (address[]) ABI encoding ({len(data)} bytes)")
    n = int.from_bytes(data[32:64], "big")
    if len(data) < 64 + 32 * n:
        raise HyperEvmReadError(f"{address}: getOwners() claims {n} owners but the response is too short to contain them")
    owners = ["0x" + data[64 + 32 * i + 12:64 + 32 * (i + 1)].hex() for i in range(n)]
    modules_raw = _eth_call(address, _selector("getModulesPaginated(address,uint256)") + "0" * 63 + "1" + ("%064x" % 10))
    mdata = _bytes_from_hex(modules_raw, f"{address} getModulesPaginated()")
    if len(mdata) < 96:
        raise HyperEvmReadError(f"{address}: getModulesPaginated() response too short to be a real (address[], address) ABI encoding ({len(mdata)} bytes)")
    mn = int.from_bytes(mdata[64:96], "big")
    if len(mdata) < 96 + 32 * mn:
        raise HyperEvmReadError(f"{address}: getModulesPaginated() claims {mn} modules but the response is too short to contain them")
    if mn >= 10:
        # Same hardcoded pageSize=10 this project's own
        # scripts/lib/scorers.py::_safe_guard_and_modules already uses and
        # never paginates past -- flagged here rather than silently
        # truncated, since a full page means there MAY be more.
        pass  # noted in the caller via the returned "modules" list length, not raised: a full page is not itself invalid
    modules = ["0x" + mdata[96 + 32 * i + 12:96 + 32 * (i + 1)].hex() for i in range(mn)]
    guard_raw = evm("eth_getStorageAt", [address, GUARD_STORAGE_SLOT, "latest"])
    guard = _address_from_hex(guard_raw, f"{address} guard slot")
    if threshold == 0 or threshold > len(owners):
        raise HyperEvmReadError(f"{address}: decoded as threshold={threshold} over {len(owners)} owners -- not a structurally possible Safe, degrading rather than trusting it")
    return {"safe": address, "owners": owners, "threshold": threshold, "modules": modules, "guard": guard,
            "modulesPageMayBeTruncated": mn >= 10}


def read_access_control_role_members(contract, role_hash):
    """OpenZeppelin AccessControlEnumerable: every current holder of one
    role. `role_hash` is the 32-byte role identifier (e.g. the return
    value of calling `DEFAULT_ADMIN_ROLE()`, which is always `bytes32(0)`
    by OpenZeppelin's own convention, or `keccak256("SOME_ROLE")` for a
    custom role)."""
    role_padded = role_hash[2:].rjust(64, "0")
    count = int(_eth_call(contract, _selector("getRoleMemberCount(bytes32)") + role_padded), 16)
    members = []
    for i in range(count):
        raw = _eth_call(contract, _selector("getRoleMember(bytes32,uint256)") + role_padded + ("%064x" % i))
        members.append("0x" + raw[-40:])
    return members


def _safe_rooted_scores_hyperevm(threshold, n_owners):
    # Reuses scripts/lib/scorers.py::_safe_rooted_scores's already-
    # calibrated convention verbatim (a plain Gnosis Safe, no module, no
    # guard, no timelock above it) rather than inventing a new formula for
    # the first HyperEVM-side target -- see that function's own docstring
    # for the calibration rationale (batch 9, landed against Arcus/
    # Longbow/Chainlink/LayerZero precedents).
    if threshold >= 3:
        admin_key = 65
    elif threshold == 2:
        admin_key = 50
    else:
        admin_key = 10
    multisig = min(100, threshold * 15 + max(0, n_owners - threshold) * 5)
    return admin_key, multisig, 0


ROLE_NAMES = ("DEFAULT_ADMIN_ROLE", "MANAGER_ROLE", "OPERATOR_ROLE", "SENTINEL_ROLE", "TREASURY_ROLE")


def _role_hash(contract, role_name):
    if role_name == "DEFAULT_ADMIN_ROLE":
        return "0x" + "0" * 64  # OpenZeppelin's own fixed convention, never a live getter call
    return _eth_call(contract, _selector(role_name + "()"))


def _has_role(contract, role_hash, account):
    """hasRole(bytes32,address) -- the only live check available for a plain
    (non-Enumerable) OpenZeppelin AccessControl role: no getRoleMemberCount/
    getRoleMember (Kinetiq's shape) and no roleHolders(bytes32) either (para's/
    Ventuals' shape) -- both confirmed to revert against stHYPE (added
    2026-09-25). Used to confirm a candidate holder address live before
    scoring it, rather than trusting a name as static text."""
    data = _selector("hasRole(bytes32,address)") + role_hash[2:].rjust(64, "0") + account[2:].rjust(64, "0")
    return int(_eth_call(contract, data), 16) != 0


ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"


def _classify_authority_holder(address, none_means_renounced=False):
    """One holder of one role/authority slot -> (adminKey, multisig,
    timelock), reusing this project's existing conventions rather than
    inventing new ones: a real Gnosis Safe scores via
    `_safe_rooted_scores_hyperevm`; anything else with no code is a bare
    EOA, scored the same as a 1-of-1 Safe (`_safe_rooted_scores_hyperevm`'s
    own `threshold=1` branch, admin_key=10) -- the same floor this
    project's Solana side uses for a bare on-curve key. A contract that
    isn't a resolvable Safe (HyperEvmReadError, e.g. a malformed response)
    OR that reverts entirely on the Safe-shaped calls (HyperEvmRpcError --
    e.g. a plain EIP-1967 proxy delegating to a non-Safe implementation,
    which simply doesn't implement getOwners()) is treated the same as an
    unresolved authority: degraded to a conservative 20/0/0, matching
    `scripts/lib/scorers.py::_safe_rooted_entry`'s own fallback for the
    identical situation, rather than silently trusted or crashed on.

    `none_means_renounced`: pass True ONLY for an address read from an
    `owner()`-style single-authority slot (e.g. `Ownable`/
    `Ownable2Step`'s own `owner()`), where the zero address has a special,
    deliberate meaning -- renounced, no one can ever act again -- the
    SAFEST possible state, not a weak bare key. Matches this project's own
    `none_means_renounced` convention on the Solana side
    (`_resolve_squads_v4`, fixed the same day this pass after a real
    scorer treated a renounced authority as a false MISMATCH instead of
    the safest band). Do NOT pass True for an enumerated role-holder
    address (AccessControlEnumerable/EnumerableRoles) -- roles don't have
    an idiomatic "renounce to zero, forever" meaning the way an owner()
    slot does, so a zero address there would be corrupt data, not a
    deliberate safety signal."""
    if none_means_renounced and address.lower() == ZERO_ADDRESS:
        return (100, 100, 100), {"kind": "renounced (owner() == address(0), no one can ever act)"}
    code = evm("eth_getCode", [address, "latest"])
    if code == "0x":
        return (10, 0, 0), {"kind": "bare EOA"}
    try:
        safe = read_safe_hyperevm(address)
    except HyperEvmReadError as e:  # HyperEvmRpcError deliberately NOT caught here since 2026-09-22, see its docstring
        return (20, 0, 0), {"kind": "unresolved (not a decodable Safe)", "error": str(e)}
    admin_key, multisig, timelock = _safe_rooted_scores_hyperevm(safe["threshold"], len(safe["owners"]))
    # FIXED 2026-09-17 (closed an adversarial-review finding): this used to
    # return only `len(safe["owners"])` (a count), so a caller building a
    # cross-exposure address set from these `info_` dicts had no way to
    # see the Safe's ACTUAL owner addresses -- only the Safe's own address
    # was ever checkable, silently missing any owner nested one level
    # deeper (a real case here: one of para StakingVault's OPERATOR_ROLE
    # Safe's 3 owners is the SAME address as the separate RoleRegistry.
    # owner() Safe's own sole owner -- invisible to a check that only
    # looks at role_paths' top-level keys). `ownerAddresses` is added
    # alongside the existing `owners` count for exactly this purpose.
    return (admin_key, multisig, timelock), {"kind": "Gnosis Safe", "threshold": safe["threshold"], "owners": len(safe["owners"]),
                                              "ownerAddresses": safe["owners"], "modules": safe["modules"], "guard": safe["guard"]}


def score_kinetiq_staking_manager():
    """Kinetiq's `HIP3StakingManager` (kmHYPE liquid staking -- CORRECTED
    2026-09-19, this docstring's own parenthetical was a mislabel; see
    METHODOLOGY.md's 2026-09-18 changelog entry and the live on-chain
    confirmation in `data/finding_2026-09-19-hyperliquid-khype-kmhype-
    identity.md`) -- the FIRST
    HyperEVM-native target this project scores, every other Hyperliquid
    target so far being HyperCore-native. Surfaced while investigating a
    genuinely different question (does the HIP-3 dex `mkts`/`km`'s deployer
    address, which also carries live HyperEVM bytecode, expose a second
    root-control path over those perp markets?) -- the answer to THAT
    question turned out to be no (see `data/finding_2026-09-17-
    hyperliquid-hip3-evm-proxy-authority.md`'s correction: the contract is
    Kinetiq's own staking manager, unrelated to HIP-3 dex admin actions),
    but the investigation surfaced a real, fully independently verified
    authority chain worth scoring in its own right, for a DIFFERENT
    protocol (Kinetiq) than the one that led to finding it.

    FIXED 2026-09-17 (closed an adversarial-review finding on this same-
    day addition): a first version of this function scored ONLY the
    `DEFAULT_ADMIN_ROLE` path (the 4-of-8 Safe) and its docstring flatly
    asserted every other operational role "has zero current holders" --
    false for 3 of 4: `MANAGER_ROLE` is held by the same Safe (benign),
    but `OPERATOR_ROLE` is held by a BARE EOA
    (`0x4459872f33d7e3b61238a6edc7611463c25d82fa`, confirmed via
    `eth_getCode` = `0x`) that can call `withdrawFromSpot`/
    `processL1Operations`, and `TREASURY_ROLE` is held by a SEPARATE
    4-of-7 Gnosis Safe sharing only 1 of 7 owners with the "root" Safe.
    The bare EOA is now the binding constraint (see the composite
    computation below) -- this was found only because the claim in the
    original docstring was independently re-verified rather than trusted,
    exactly the discipline this project applies to every other cited
    number.

    Every operational role this contract defines
    (`DEFAULT_ADMIN_ROLE`/`MANAGER_ROLE`/`OPERATOR_ROLE`/`SENTINEL_ROLE`/
    `TREASURY_ROLE`) is read and every current holder classified (Gnosis
    Safe, bare EOA, or an unresolved contract) via the SAME, already-
    calibrated conventions this project uses everywhere else -- no new
    formula invented for the first HyperEVM target. `adminKeyScore`/
    `multisigScore`/`timelockScore` take the MINIMUM across every
    currently-held role, per METHODOLOGY.md 6.2's "several authorities per
    target" convention (already used this same day on the Solana side for
    Solend/Drift): the weakest path decides the target's real risk.

    The EIP-1967 proxy-admin chain (proxy -> an Ownable admin contract ->
    that contract's `owner()`) independently confirms the SAME Safe holds
    `DEFAULT_ADMIN_ROLE`, kept as a cross-check note, not a separate score
    input (it resolves to the identical Safe already covered by the role
    read).

    Not scored (informational): the intermediate Ownable admin contract
    (`0x6181cb542015490dd2985043f9ff119896ca92d0`) that sits between the
    proxy and the Safe -- itself a real contract, but only a pass-through;
    the Safe is the actual root. Also not scored: whether any of these
    authority holders controls any OTHER Kinetiq contract beyond this one
    proxy -- not checked this pass."""
    proxy = "0x71f0019cc7fa79e4f42587fb7b9a817d8d2429ec"  # SAME address as HIP-3 dexes mkts/km's HyperCore-native deployer
    # Read the EIP-1967 admin slot directly rather than calling a
    # transparent-proxy admin()/eth_call-style getter -- those typically
    # revert or return the wrong value unless called BY the current admin
    # itself, per EIP-1967's own transparent-proxy convention.
    admin_slot = "0xb53127684a568b3173ae13b9f8a6016e243e63b6e8ee1178d6a717850b5d6103"
    admin_raw = evm("eth_getStorageAt", [proxy, admin_slot, "latest"])
    admin = _address_from_hex(admin_raw, f"{proxy} EIP-1967 admin slot")
    owner_raw = _eth_call(admin, _selector("owner()"))
    safe_addr = _address_from_hex(owner_raw, f"{admin} owner()")

    notes = [
        f"proxy {proxy} (same address as HIP-3 dexes mkts/km's HyperCore-native deployer) EIP-1967 admin = {admin}",
        f"admin contract {admin}.owner() = {safe_addr} (cross-check only; the real score comes from the role reads below)",
    ]

    # Every role this contract defines, every current holder, classified.
    role_paths = {}
    nested_owner_addrs = set()  # FIXED 2026-09-17: see the cross-exposure note below
    for role_name in ROLE_NAMES:
        role_hash = _role_hash(proxy, role_name)
        members = read_access_control_role_members(proxy, role_hash)
        if not members:
            notes.append(f"{role_name}: 0 holders")
            continue
        for member in members:
            scores, info_ = _classify_authority_holder(member)
            role_paths[f"{role_name}:{member}"] = scores
            notes.append(f"{role_name}: holder {member} ({info_['kind']}) -> adminKey={scores[0]} multisig={scores[1]} timelock={scores[2]}")
            if info_.get("kind") == "Gnosis Safe" and (info_["modules"] or int(info_["guard"], 16) != 0):
                notes.append(f"WARNING: {member} (holds {role_name}) has a module or guard -- threshold alone no longer describes who can act; re-check by hand")
            nested_owner_addrs |= {a.lower() for a in info_.get("ownerAddresses", [])}

    admin_key = min(p[0] for p in role_paths.values())
    multisig = min(p[1] for p in role_paths.values())
    timelock = min(p[2] for p in role_paths.values())
    # Reported per-dimension, not as one combined "dominant path" list --
    # every path here happens to carry timelock=0 (no Safe in this set has
    # a timelock above it), so a single combined list would show all 4
    # paths as "tied" on that dimension and obscure the one path that
    # actually drives adminKey/multisig down.
    dominant_admin_key = sorted(k for k, p in role_paths.items() if p[0] == admin_key)
    dominant_multisig = sorted(k for k, p in role_paths.items() if p[1] == multisig)
    notes.append(
        f"combined (min over every currently-held role, METHODOLOGY.md 6.2): "
        f"adminKey={admin_key} (weakest: {dominant_admin_key}) "
        f"multisig={multisig} (weakest: {dominant_multisig}) "
        f"timelock={timelock} (every path here is 0 -- no Safe in this set has a timelock)"
    )
    dominant = dominant_admin_key

    # Real cross-exposure check against every HIP-3 dex's own root/oracle
    # signer set (same signer-overlap convention score_hip3_dex already
    # uses for dex-to-dex comparisons) -- not assumed clean, checked.
    # Checks every address that holds ANY role above, AND every owner
    # address nested one level deeper inside any of those that resolved to
    # a Gnosis Safe -- FIXED 2026-09-17 (closed an adversarial-review
    # finding): this used to check only the top-level role_paths keys
    # (a Safe's own address), never the individual owners inside it, so a
    # dex signer that happened to BE one of those owners (rather than the
    # Safe itself) would have been silently missed.
    all_holder_addrs_lower = {key.split(":", 1)[1].lower() for key in role_paths} | nested_owner_addrs
    dexes = [d for d in info({"type": "perpDexs"}) if d]
    sharing_dexes = []
    for d in dexes:
        addrs = {d["deployer"]} | ({d["oracleUpdater"]} if d.get("oracleUpdater") else set())
        for _, lst in d.get("subDeployers") or []:
            addrs |= set(lst)
        signers = set()
        for a in addrs:
            signers |= set(kn(a)[1]) | {a}
        if all_holder_addrs_lower & {s.lower() for s in signers}:
            sharing_dexes.append(d["name"])
    cross_exposure = max(0, 100 - 20 * len(sharing_dexes))
    notes.append(f"cross-checked all {len(dexes)} HIP-3 dexes' own signer sets against every role-holder address above -- overlap: {sharing_dexes or 'none'}")

    return {
        "target": proxy,
        "label": "Kinetiq HIP3StakingManager (HyperEVM)",
        "reads": {
            "proxyEip1967Admin": admin,
            "adminContractOwnerCrossCheck": safe_addr,
            "roleHolders": {k: {"adminKey": p[0], "multisig": p[1], "timelock": p[2]} for k, p in role_paths.items()},
            "dominantPaths": dominant,
            "dexesSharingASignerWithAnyRoleHolder": sharing_dexes,
        },
        "adminKeyScore": admin_key,
        "multisigScore": multisig,
        "timelockScore": timelock,
        "oracleAuthorityScore": 100,
        "crossExposureScore": cross_exposure,
        "compositeScore": composite(admin_key, multisig, timelock),
        "notes": notes,
    }


def read_role_registry_role_holders(contract, role_hash):
    """Solady `EnumerableRoles`-style role read (as wrapped by a project's
    own `RoleRegistry.roleHolders(bytes32)`) -- a DIFFERENT interface than
    OpenZeppelin's `AccessControlEnumerable` (`read_access_control_role_
    members` above): one call returns the full holder array directly,
    there is no separate count-then-index-loop. Found and read live
    2026-09-17 while investigating HIP-3 dex `para`'s own EVM-side
    infrastructure (a DIFFERENT product than Kinetiq's, reusing a similar
    but not identical role-registry pattern -- proof that this general
    "check every role a HyperEVM contract's access-control system
    defines" methodology generalizes across at least two independently-
    written implementations, not just Kinetiq's one).

    FIXED 2026-09-17 (closed two adversarial-review findings): (a)
    `role_hash` used to be spliced with `role_hash[2:].rjust(64, "0")` with
    no minimum-length check -- a short or empty `role_hash` (e.g. if a
    future RoleRegistry upgrade ever made `MANAGER_ROLE()`/`OPERATOR_ROLE()`
    return no data instead of reverting for an unrecognized selector)
    would silently zero-pad into `bytes32(0)` -- this project's own
    `DEFAULT_ADMIN_ROLE` sentinel value elsewhere -- and query a
    completely different, unintended role with no error, no warning, a
    silently WRONG result rather than a crash or a clear failure; (b) the
    `bytes.fromhex` conversion now goes through the shared
    `_bytes_from_hex` helper, closing the same bare-`ValueError`-escapes-
    every-except-clause gap `read_safe_hyperevm` also had."""
    if len(role_hash) < 66:
        raise HyperEvmReadError(f"{contract}: role hash {role_hash!r} is not a well-formed 32-byte value (likely a reverted or malformed role getter)")
    raw = _eth_call(contract, _selector("roleHolders(bytes32)") + role_hash[2:].rjust(64, "0"))
    data = _bytes_from_hex(raw, f"{contract} roleHolders({role_hash})")
    if len(data) < 64:
        raise HyperEvmReadError(f"{contract}: roleHolders() response too short to be a real (address[]) ABI encoding ({len(data)} bytes)")
    n = int.from_bytes(data[32:64], "big")
    if len(data) < 64 + 32 * n:
        raise HyperEvmReadError(f"{contract}: roleHolders() claims {n} holders but the response is too short to contain them")
    return ["0x" + data[64 + 32 * i + 12:64 + 32 * (i + 1)].hex() for i in range(n)]


def score_para_staking_vault():
    """A SEPARATE, previously-undisclosed HyperEVM authority chain found
    while closing this project's own open question about HIP-3 dex
    `para`'s EVM-side proxy (`data/finding_2026-09-17-hyperliquid-hip3-
    evm-proxy-authority.md` had explicitly left `para`'s own implementation
    source unread, "an open, symmetrical gap" to Kinetiq's). Reading it
    corrects that file's own earlier claim about `para`'s proxy: it is NOT
    an immutable proxy with "no standard-pattern admin" -- that framing
    conflated proxy patterns. This is a UUPS proxy (OpenZeppelin
    `UUPSUpgradeable`), which never uses the EIP-1967 ADMIN slot at all
    (only a TRANSPARENT proxy does) -- the admin slot reading zero was
    never evidence of "no admin," only of "not a transparent proxy." The
    real authority lives in the implementation's own `_authorizeUpgrade`,
    gated by an external `RoleRegistry` contract's `owner()`.

    Contract name (verified source, `hyperevmscan.io`): `StakingVault`. It
    manages real value: `delegatorSummary()` reads 500,801.29 HYPE
    currently delegated to validators (~$41.7M at the live $83.32/HYPE
    mid price, 2026-09-17) -- larger than several already-promoted HIP-3
    dexes' own open interest. No spot token was found linking to this
    vault as an `evmContract` (checked all 501 live spot tokens) -- this
    is a custody/treasury vault, not a wrapped liquid-staking token.

    Three independent authority paths, each fully resolved, not assumed:
      1. `RoleRegistry.owner()` (`Ownable2StepUpgradeable`; gates
         `_authorizeUpgrade` on BOTH the vault and the RoleRegistry
         itself, plus `grantRole`/`revokeRole`/`pause`/`unpause`) --
         resolves to a 1-of-1 Gnosis Safe.
      2. `MANAGER_ROLE` (gates `deposit`/`stake`/`unstake`/
         `tokenRedelegate`/`spotSend`/`transferHypeToCore` -- i.e. every
         function that can actually move the vault's funds) -- resolves
         to a SEPARATE EIP-1967 proxy whose implementation is NOT
         verified on `hyperevmscan.io` ("Are you the contract creator?
         Verify and Publish..."). `_classify_authority_holder` correctly
         degrades this to the conservative unresolved-contract fallback
         (20/0/0) rather than guessing at unverified bytecode's
         semantics -- the exact discipline this project's own earlier
         CoreWriter/Kinetiq overclaim (since corrected) should have
         applied from the start.
      3. `OPERATOR_ROLE` (gates `addValidator`/`removeValidator`/
         `addApiWallet`) -- resolves to a DIFFERENT Gnosis Safe, 1-of-3
         (one of its 3 owners is the same address as the 1-of-1 Safe from
         path 1, but the threshold is 1 regardless -- any ONE of the 3
         owners can already act alone).

    Every CoreWriter call this vault makes (`CoreWriterLibrary.
    stakingDeposit/stakingWithdraw/tokenDelegate/spotSend/addApiWallet`,
    confirmed by reading `StakingVault.sol` line by line, not just its
    ABI) is a staking/delegation/API-wallet helper -- none reaches
    `haltTrading`/`setOracle`/`setSubDeployers`. This closes the specific
    open question about `para` cleanly: no dex-admin-equivalent path
    found here either, matching the Kinetiq precedent.

    Per METHODOLOGY.md 6.2, the three paths' scores are combined by
    MINIMUM per dimension, not by picking the best-looking one: path 2's
    unresolved contract has `multisigScore=0`, which dominates regardless
    of the two real Safes' own (better) numbers -- an unverified contract
    holding fund-moving power is treated as, and disclosed as, the
    binding constraint, not softened by the other two paths' cleaner
    reads."""
    # These four setup reads are deliberately left unwrapped, unlike the
    # per-role loop below: if the RoleRegistry itself can't even be found
    # or its basic getters revert, there is genuinely nothing to score for
    # this target this run -- score_all()'s own per-scorer try/except
    # (chains/hyperliquid/scorers.py) already isolates that failure to a
    # single "SKIPPED" line rather than losing every OTHER target's
    # results, the same convention every other scorer's own top-level
    # setup already relies on (e.g. score_kinetiq_staking_manager's
    # equivalent proxy/admin/safe reads). The per-ROLE loop below is a
    # different case: losing ONE role's read should not cost the other
    # two, which is why that failure degrades in place instead.
    proxy = "0x8888888c43cbb7e1c4132542e46831bffd866ed3"  # SAME address as HIP-3 dex para's HyperCore-native deployer
    role_registry = _address_from_hex(_eth_call(proxy, _selector("roleRegistry()")), f"{proxy} roleRegistry()")

    manager_role = _eth_call(role_registry, _selector("MANAGER_ROLE()"))
    operator_role = _eth_call(role_registry, _selector("OPERATOR_ROLE()"))
    owner = _address_from_hex(_eth_call(role_registry, _selector("owner()")), f"{role_registry} owner()")
    # FIXED 2026-09-17 (closed an adversarial-review finding): a role
    # constant reads with no length check used to be spliced straight into
    # `.rjust(64, "0")` -- a short/empty response (a future RoleRegistry
    # upgrade returning no data instead of reverting for a since-renamed
    # getter, say) would silently zero-pad into `bytes32(0)`, which this
    # project's own DEFAULT_ADMIN_ROLE convention elsewhere treats as a
    # MEANINGFUL value -- not a crash, not a warning, just a silently
    # WRONG role queried instead of the intended one. Validate immediately
    # rather than let a malformed constant masquerade as a real one.
    for name, val in (("MANAGER_ROLE()", manager_role), ("OPERATOR_ROLE()", operator_role)):
        if len(val) < 66:
            raise HyperEvmReadError(f"{role_registry} {name}: expected a 32-byte role hash, got {val!r}")

    role_paths = {}
    nested_owner_addrs = set()  # FIXED 2026-09-17: see the cross-exposure note below
    notes = [
        f"proxy {proxy} (same address as HIP-3 dex para's HyperCore-native deployer) roleRegistry() = {role_registry}",
    ]
    for role_label, role_hash in [("RoleRegistry.owner()", None), ("MANAGER_ROLE", manager_role), ("OPERATOR_ROLE", operator_role)]:
        if role_hash is None:
            members = [owner]
        else:
            # FIXED 2026-09-17 (closed an adversarial-review finding): this
            # call used to be unwrapped, so ANY failure reading ONE role
            # (a revert, a malformed response) crashed the entire scorer --
            # unlike a single unresolvable HOLDER, which _classify_
            # authority_holder already degrades gracefully. A whole ROLE
            # failing to read is degraded the same way: a conservative
            # unresolved path (20/0/0), not a crash, so the other roles
            # still contribute to the minimum-over-paths computation.
            try:
                members = read_role_registry_role_holders(role_registry, role_hash)
            except HyperEvmReadError as e:  # HyperEvmRpcError deliberately NOT caught here since 2026-09-22, see its docstring
                role_paths[f"{role_label}:UNRESOLVED"] = (20, 0, 0)
                notes.append(f"{role_label}: FAILED to read holders ({e}) -- degraded to conservative unresolved (20/0/0) rather than crashing this target's score")
                continue
        if not members:
            notes.append(f"{role_label}: 0 holders")
            continue
        for member in members:
            scores, info_ = _classify_authority_holder(member, none_means_renounced=(role_label == "RoleRegistry.owner()"))
            role_paths[f"{role_label}:{member}"] = scores
            notes.append(f"{role_label}: holder {member} ({info_['kind']}) -> adminKey={scores[0]} multisig={scores[1]} timelock={scores[2]}")
            if info_.get("kind") == "Gnosis Safe" and (info_["modules"] or int(info_["guard"], 16) != 0):
                notes.append(f"WARNING: {member} (holds {role_label}) has a module or guard -- threshold alone no longer describes who can act; re-check by hand")
            nested_owner_addrs |= {a.lower() for a in info_.get("ownerAddresses", [])}

    admin_key = min(p[0] for p in role_paths.values())
    multisig = min(p[1] for p in role_paths.values())
    timelock = min(p[2] for p in role_paths.values())
    dominant_admin_key = sorted(k for k, p in role_paths.items() if p[0] == admin_key)
    dominant_multisig = sorted(k for k, p in role_paths.items() if p[1] == multisig)
    notes.append(
        f"combined (min over every currently-held role, METHODOLOGY.md 6.2): "
        f"adminKey={admin_key} (weakest: {dominant_admin_key}) "
        f"multisig={multisig} (weakest: {dominant_multisig}) "
        f"timelock={timelock} (every path here is 0 -- no Safe or registry in this set has a timelock)"
    )

    delegator_summary_raw = _eth_call(proxy, _selector("delegatorSummary()"))
    delegated_wei = int.from_bytes(_bytes_from_hex(delegator_summary_raw, f"{proxy} delegatorSummary()")[0:32], "big")
    notes.append(f"delegatorSummary().delegated = {delegated_wei} (raw, 8 decimals) = {delegated_wei / 1e8:,.2f} HYPE currently delegated to validators")

    # Checks every role-holder address AND every owner address nested one
    # level deeper inside any that resolved to a Gnosis Safe -- FIXED
    # 2026-09-17 (closed an adversarial-review finding): this used to
    # check only the top-level role_paths keys, never the individual
    # owners inside a resolved Safe. Concretely matters here: one of the
    # OPERATOR_ROLE Safe's 3 owners is the SAME address as the SEPARATE
    # RoleRegistry.owner() Safe's own sole owner -- invisible to a check
    # that only looked at role_paths' top-level keys.
    # FIXED 2026-09-18 (closed an adversarial-review finding): a role_paths
    # key ending in ":UNRESOLVED" (an unread role, degraded rather than
    # crashed) used to split into the literal string "unresolved" here,
    # which can never match a real dex signer address but had no place in
    # a set that's supposed to contain only addresses -- excluded now.
    all_holder_addrs_lower = {key.split(":", 1)[1].lower() for key in role_paths if not key.endswith(":UNRESOLVED")} | nested_owner_addrs
    dexes = [d for d in info({"type": "perpDexs"}) if d]
    sharing_dexes = []
    for d in dexes:
        addrs = {d["deployer"]} | ({d["oracleUpdater"]} if d.get("oracleUpdater") else set())
        for _, lst in d.get("subDeployers") or []:
            addrs |= set(lst)
        signers = set()
        for a in addrs:
            signers |= set(kn(a)[1]) | {a}
        if all_holder_addrs_lower & {s.lower() for s in signers}:
            sharing_dexes.append(d["name"])
    cross_exposure = max(0, 100 - 20 * len(sharing_dexes))
    notes.append(f"cross-checked all {len(dexes)} HIP-3 dexes' own signer sets against every role-holder address above -- overlap: {sharing_dexes or 'none'}")

    return {
        "target": proxy,
        "label": "para StakingVault (HyperEVM)",
        "reads": {
            "roleRegistry": role_registry,
            "roleHolders": {k: {"adminKey": p[0], "multisig": p[1], "timelock": p[2]} for k, p in role_paths.items()},
            "dominantPaths": dominant_admin_key,
            "delegatedHype": delegated_wei / 1e8,
            "dexesSharingASignerWithAnyRoleHolder": sharing_dexes,
        },
        "adminKeyScore": admin_key,
        "multisigScore": multisig,
        "timelockScore": timelock,
        "oracleAuthorityScore": 100,
        "crossExposureScore": cross_exposure,
        "compositeScore": composite(admin_key, multisig, timelock),
        "notes": notes,
    }


def score_ventuals_vhype_staking():
    """A THIRD HyperEVM-native target, found 2026-09-18 while chasing a
    "Similar Match" contract `hyperevmscan.io` flagged next to `para`
    StakingVault's own implementation. That specific similar-bytecode
    contract turned out to be a dead end for attribution purposes (its
    own EIP-1967 slot doesn't match any of the 10 tracked HIP-3 dexes'
    deployer addresses) -- but sweeping every dex's deployer for its OWN
    EIP-1967 implementation slot (not just `eth_getCode`, which the
    2026-09-17 promotion already checked) found something real instead:
    HIP-3 dex `vntl` -- STILL genuinely dormant, $0 open interest, same as
    every re-sweep this project has run -- ALSO carries live HyperEVM
    infrastructure, exactly like `mkts`/`km` (Kinetiq) and `para` before
    it. Unlike either of those, this one has a real, named product behind
    it: **Ventuals vHYPE**, a liquid-staking token (`hyperevmscan.io`
    contract-creator tag "Ventuals vHYPE: Deployer"; a HyperCore spot
    token `VNTLS`, `fullName: "Ventuals"`, confirms the same product
    name independently). `vntl`'s own deployer/proxy IS the underlying
    custody `StakingVault` (verified source, same contract type as
    Kinetiq's and `para`'s) -- `delegatorSummary()` reads 7,328.99 HYPE
    currently delegated (~$610K at the live $83.32/HYPE mid price),
    cross-checked against a second, independent read
    (`StakingVaultManager.totalBalance()` -- see below -- returns the
    identical figure).

    TWO layers, not one: unlike `para`'s simple StakingVault, this
    product has a second contract in front of it, `StakingVaultManager`
    (verified source, contract name confirmed on `hyperevmscan.io`),
    which mints/burns the `vHYPE` liquid-staking token, manages a
    withdrawal queue (`queueWithdraw`/`claimWithdraw`/`batchClaimWithdraws`
    /`processBatch`/`finalizeBatch` -- all permissionlessly callable by
    ANYONE, a standard keeper-processed queue design, not a privileged
    action) and itself HOLDS `MANAGER_ROLE` on the same `RoleRegistry`
    that roots the underlying `StakingVault` -- i.e. it is the mechanism
    by which the withdrawal queue actually triggers `stake`/`unstake` on
    the custody vault, not an independent authority.

    Three paths, all fully resolved -- unlike `para`, where the
    `MANAGER_ROLE` holder's implementation is unverified and its
    practical authority was deliberately left conservative:
      1. `RoleRegistry.owner()` -- resolves to a 2-of-3 Gnosis Safe.
      2. `OPERATOR_ROLE` -- resolves to the SAME 2-of-3 Safe directly
         (not nested inside a different Safe, unlike `para`'s case).
      3. `MANAGER_ROLE` -- resolves to the `StakingVaultManager` PROXY.
         Unlike `para`'s analogous proxy, this implementation IS
         verified, so its practical authority was resolved by actually
         READING the source (`hyperevmscan.io`), not by trusting a bare
         `roleRegistry()` getter call (which proves nothing about actual
         gating on its own -- a malicious implementation could expose
         that getter without using it for access control; this is
         exactly the "bytecode presence isn't sufficient evidence"
         discipline this project's own earlier CoreWriter/Kinetiq
         overclaim, since corrected, should have applied from the
         start). Confirmed by reading `Base.sol` (identical to
         Kinetiq's/`para`'s own base contract) that `_authorizeUpgrade`
         is gated `onlyOwner` -> `roleRegistry.owner()`, and by reading
         EVERY externally-callable function in `StakingVaultManager.sol`
         that every DISCRETIONARY, parameter-changing, or emergency
         action (`setMinimumStakeBalance`, `switchValidator`,
         `setMinimumDepositAmount`/`WithdrawAmount`/`MaximumWithdrawAmount`,
         `setClaimWindowBuffer`, `setBatchProcessingPaused`, `resetBatch`,
         `finalizeResetBatch`, `applySlash`, `emergencyStakingWithdraw`,
         `emergencyStakingDeposit`, `windDown`) is gated `onlyOwner` --
         the SAME `roleRegistry.owner()` as paths 1 and 2. CORRECTED
         2026-09-18 (an adversarial review caught this): NOT literally
         "every privileged, fund-affecting action" -- `finalizeBatch`/
         `processBatch` are themselves `whenNotPaused`-only, callable by
         ANYONE, and DO directly call the underlying vault's
         `stake`/`unstake`/`transferHypeToCore` (the exact functions
         `MANAGER_ROLE` gates on that vault). What actually preserves the
         score: every amount and destination those two functions move is
         computed purely from internal accounting and the `onlyOwner`-set
         `validator` -- zero caller-supplied amount or destination -- so
         a non-owner caller has no discretion over where funds go; this
         is a keeper-style settlement step, not a privilege-escalation
         path. This distinction (discretionary actions onlyOwner-gated;
         the permissionless entry point non-discretionary), not a
         blanket "onlyOwner everywhere," is what the identical-to-Safe
         score for this path actually rests on. This contract does NOT
         import `CoreWriterLibrary`/`ICoreWriter` at all (only the
         underlying `StakingVault` it calls into does) -- confirmed from
         its own file list on `hyperevmscan.io`, not assumed.

    All three paths resolve to the IDENTICAL 2-of-3 Safe -- a materially
    different, more reassuring picture than `para`'s (where the analogous
    path was conservatively scored as unresolved because its
    implementation isn't verified). `compositeScore=31`, `l1Capped
    Composite=min(31, 26)=26` -- the L1 cap actually binds here, unlike
    `para`'s and Kinetiq's own (already below the L1's 26)."""
    # FIXED 2026-09-18 (closed an adversarial-review finding): the one
    # address this function trusts as "manually verified" is checked
    # against its OWN EIP-1967 implementation slot at runtime, every run
    # -- not just once, by hand, at derivation time. A UUPS proxy's own
    # address never changes across an upgrade; only its backing
    # implementation moves, and the SAME Safe this function already
    # trusts is the sole entity that can push that upgrade (Base.sol's
    # `_authorizeUpgrade` -> `onlyOwner`). Without this check, a routine,
    # legitimate Safe-authorized upgrade could silently swap this
    # contract's real logic while the code kept applying a manual
    # verification that no longer describes its behavior. If the
    # implementation ever changes, this degrades to the normal
    # conservative path instead of continuing to trust a stale reading.
    VENTUALS_MANAGER_ROLE_VERIFIED_HOLDER = "0x88888880793f89ce85777ff2e0e2d366bf05b20c"
    VENTUALS_MANAGER_ROLE_VERIFIED_IMPLEMENTATION = "0x0000000c21e635b59edff54e70fe21315fa9b245"

    proxy = "0x8888888192a4a0593c13532ba48449fc24c3beda"  # SAME address as HIP-3 dex vntl's HyperCore-native deployer
    role_registry = _address_from_hex(_eth_call(proxy, _selector("roleRegistry()")), f"{proxy} roleRegistry()")
    owner = _address_from_hex(_eth_call(role_registry, _selector("owner()")), f"{role_registry} owner()")
    operator_role = _eth_call(role_registry, _selector("OPERATOR_ROLE()"))
    manager_role = _eth_call(role_registry, _selector("MANAGER_ROLE()"))

    role_paths = {}
    nested_owner_addrs = set()
    notes = [f"proxy {proxy} (same address as HIP-3 dex vntl's HyperCore-native deployer) roleRegistry() = {role_registry}"]

    scores, info_ = _classify_authority_holder(owner, none_means_renounced=True)
    role_paths[f"RoleRegistry.owner():{owner}"] = scores
    notes.append(f"RoleRegistry.owner(): holder {owner} ({info_['kind']}) -> adminKey={scores[0]} multisig={scores[1]} timelock={scores[2]}")
    nested_owner_addrs |= {a.lower() for a in info_.get("ownerAddresses", [])}

    # FIXED 2026-09-18 (closed an adversarial-review finding): the
    # role-hash length check used to run BEFORE these try/except blocks,
    # unguarded -- a malformed OPERATOR_ROLE()/MANAGER_ROLE() response
    # (e.g. a future RoleRegistry upgrade that renames or removes a role)
    # crashed the entire target's score instead of degrading just that
    # one role, breaking the exact graceful-degradation convention this
    # function otherwise follows. The length check now happens per-role,
    # inside the same try/except that already handles read_role_registry_
    # role_holders' own failures.
    try:
        if len(operator_role) < 66:
            raise HyperEvmReadError(f"{role_registry} OPERATOR_ROLE(): expected a 32-byte role hash, got {operator_role!r}")
        operator_members = read_role_registry_role_holders(role_registry, operator_role)
    except HyperEvmReadError as e:  # HyperEvmRpcError deliberately NOT caught here since 2026-09-22, see its docstring
        role_paths["OPERATOR_ROLE:UNRESOLVED"] = (20, 0, 0)
        notes.append(f"OPERATOR_ROLE: FAILED to read holders ({e}) -- degraded to conservative unresolved (20/0/0)")
        operator_members = []
    if operator_role and len(operator_role) >= 66 and not operator_members and "OPERATOR_ROLE:UNRESOLVED" not in role_paths:
        notes.append("OPERATOR_ROLE: 0 holders")
    for member in operator_members:
        # FIXED 2026-09-18 (closed an adversarial-review finding): live
        # state has OPERATOR_ROLE held by the SAME address as RoleRegistry
        # .owner() -- reuse that already-computed classification instead
        # of re-running the full Safe-decode RPC sequence a second time
        # (redundant work, and a narrow theoretical inconsistency risk if
        # a Safe reconfiguration landed between the two independent
        # "latest"-block reads).
        if member.lower() == owner.lower():
            scores = role_paths[f"RoleRegistry.owner():{owner}"]
            role_paths[f"OPERATOR_ROLE:{member}"] = scores
            notes.append(f"OPERATOR_ROLE: holder {member} (SAME address as RoleRegistry.owner(), reusing that classification) -> adminKey={scores[0]} multisig={scores[1]} timelock={scores[2]}")
            continue
        scores, info_ = _classify_authority_holder(member)
        role_paths[f"OPERATOR_ROLE:{member}"] = scores
        notes.append(f"OPERATOR_ROLE: holder {member} ({info_['kind']}) -> adminKey={scores[0]} multisig={scores[1]} timelock={scores[2]}")
        nested_owner_addrs |= {a.lower() for a in info_.get("ownerAddresses", [])}

    try:
        if len(manager_role) < 66:
            raise HyperEvmReadError(f"{role_registry} MANAGER_ROLE(): expected a 32-byte role hash, got {manager_role!r}")
        manager_members = read_role_registry_role_holders(role_registry, manager_role)
    except HyperEvmReadError as e:  # HyperEvmRpcError deliberately NOT caught here since 2026-09-22, see its docstring
        role_paths["MANAGER_ROLE:UNRESOLVED"] = (20, 0, 0)
        notes.append(f"MANAGER_ROLE: FAILED to read holders ({e}) -- degraded to conservative unresolved (20/0/0)")
        manager_members = []
    if manager_role and len(manager_role) >= 66 and not manager_members and "MANAGER_ROLE:UNRESOLVED" not in role_paths:
        notes.append("MANAGER_ROLE: 0 holders")
    for member in manager_members:
        # NOT run through _classify_authority_holder's mechanical Safe
        # decode (getOwners() would simply revert on this contract, like
        # para's analogous proxy, defaulting to a conservative
        # unresolved score). This ONE address's classification is instead
        # a MANUALLY-verified result: `hyperevmscan.io`'s verified source
        # for this exact address was read directly (see this function's
        # own docstring) and confirmed to gate every privileged action,
        # including its own upgrade, via `onlyOwner` -> the SAME
        # `roleRegistry.owner()` already resolved above -- so its
        # practical authority is that SAME Gnosis Safe, not "unknown."
        # This is deliberately NOT automated into a general rule (e.g.
        # "trust any contract whose roleRegistry() call succeeds") --
        # that would repeat this project's own earlier CoreWriter/Kinetiq
        # overclaim, since corrected, of trusting bytecode/interface
        # presence without reading verified source to confirm the actual
        # gating. `para`'s own analogous MANAGER_ROLE holder is NOT
        # verified and correctly remains conservatively scored.
        is_manually_verified = member.lower() == VENTUALS_MANAGER_ROLE_VERIFIED_HOLDER
        if is_manually_verified:
            # Re-derived every run, not trusted once and forgotten: if a
            # Safe-authorized upgrade ever swaps this proxy's backing
            # implementation, the manual verification no longer applies,
            # and this falls through to the normal conservative path.
            try:
                current_impl = _address_from_hex(
                    evm("eth_getStorageAt", [member, EIP1967_IMPLEMENTATION_SLOT, "latest"]),
                    f"{member} EIP-1967 implementation slot",
                )
            except HyperEvmReadError:
                current_impl = None
            is_manually_verified = current_impl is not None and current_impl.lower() == VENTUALS_MANAGER_ROLE_VERIFIED_IMPLEMENTATION
        if is_manually_verified:
            scores = role_paths[f"RoleRegistry.owner():{owner}"]
            role_paths[f"MANAGER_ROLE:{member}"] = scores
            notes.append(f"MANAGER_ROLE: holder {member} (verified StakingVaultManager, implementation re-confirmed live == {VENTUALS_MANAGER_ROLE_VERIFIED_IMPLEMENTATION}, manually confirmed onlyOwner-gated -> SAME Safe as RoleRegistry.owner()) -> adminKey={scores[0]} multisig={scores[1]} timelock={scores[2]}")
        else:
            scores, info_ = _classify_authority_holder(member)
            role_paths[f"MANAGER_ROLE:{member}"] = scores
            notes.append(f"MANAGER_ROLE: holder {member} ({info_['kind']}, NOT manually verified -- either an unexpected holder or its implementation has changed since the manual review) -> adminKey={scores[0]} multisig={scores[1]} timelock={scores[2]} -- re-check by hand")
            nested_owner_addrs |= {a.lower() for a in info_.get("ownerAddresses", [])}

    admin_key = min(p[0] for p in role_paths.values())
    multisig = min(p[1] for p in role_paths.values())
    timelock = min(p[2] for p in role_paths.values())
    dominant_admin_key = sorted(k for k, p in role_paths.items() if p[0] == admin_key)
    dominant_multisig = sorted(k for k, p in role_paths.items() if p[1] == multisig)
    notes.append(
        f"combined (min over every currently-held role, METHODOLOGY.md 6.2): "
        f"adminKey={admin_key} (weakest: {dominant_admin_key}) "
        f"multisig={multisig} (weakest: {dominant_multisig}) "
        f"timelock={timelock}"
    )

    delegator_summary_raw = _eth_call(proxy, _selector("delegatorSummary()"))
    delegated_wei = int.from_bytes(_bytes_from_hex(delegator_summary_raw, f"{proxy} delegatorSummary()")[0:32], "big")
    notes.append(f"delegatorSummary().delegated = {delegated_wei} (raw, 8 decimals) = {delegated_wei / 1e8:,.2f} HYPE currently delegated to validators")

    # FIXED 2026-09-18 (closed an adversarial-review finding): a
    # role_paths key ending in ":UNRESOLVED" used to split into the
    # literal string "unresolved" here, which can never match a real dex
    # signer address but had no place in a set meant to contain only
    # addresses -- excluded now.
    all_holder_addrs_lower = {key.split(":", 1)[1].lower() for key in role_paths if not key.endswith(":UNRESOLVED")} | nested_owner_addrs
    dexes = [d for d in info({"type": "perpDexs"}) if d]
    sharing_dexes = []
    for d in dexes:
        addrs = {d["deployer"]} | ({d["oracleUpdater"]} if d.get("oracleUpdater") else set())
        for _, lst in d.get("subDeployers") or []:
            addrs |= set(lst)
        signers = set()
        for a in addrs:
            signers |= set(kn(a)[1]) | {a}
        if all_holder_addrs_lower & {s.lower() for s in signers}:
            sharing_dexes.append(d["name"])
    cross_exposure = max(0, 100 - 20 * len(sharing_dexes))
    notes.append(f"cross-checked all {len(dexes)} HIP-3 dexes' own signer sets against every role-holder address above -- overlap: {sharing_dexes or 'none'}")

    return {
        "target": proxy,
        "label": "Ventuals vHYPE staking (HyperEVM)",
        "reads": {
            "roleRegistry": role_registry,
            "roleHolders": {k: {"adminKey": p[0], "multisig": p[1], "timelock": p[2]} for k, p in role_paths.items()},
            "dominantPaths": dominant_admin_key,
            "delegatedHype": delegated_wei / 1e8,
            "dexesSharingASignerWithAnyRoleHolder": sharing_dexes,
        },
        "adminKeyScore": admin_key,
        "multisigScore": multisig,
        "timelockScore": timelock,
        "oracleAuthorityScore": 100,
        "crossExposureScore": cross_exposure,
        "compositeScore": composite(admin_key, multisig, timelock),
        "notes": notes,
    }


def score_sthype_liquid_staking():
    """stHYPE (`0xffaa4a3d97fe9107cef8a3f48c069f577ff76cc1`) -- a liquid-staking token for
    HYPE, the FOURTH HyperEVM-native target this project scores (added 2026-09-25).
    Verified independently today: an earlier candidate address for this same target,
    `0x94e8396e0869c9f2200760af0621afd240e1cf38`, is actually `wstHYPE`, an ERC-4626-style
    WRAPPER around stHYPE (identical 2,232-byte code length to stHYPE itself, which is what
    made the two easy to conflate) -- corrected before this scorer was ever written, not
    after finding a bug in a committed one.

    Plain OpenZeppelin `AccessControl` (confirmed live: both `getRoleMemberCount(bytes32)`,
    Kinetiq's enumeration shape, and `roleHolders(bytes32)`, para's/Ventuals' RoleRegistry
    shape, revert against this contract) plus `AccessControlDefaultAdminRules`'s own
    `defaultAdmin()` getter, which names the current `DEFAULT_ADMIN_ROLE` holder directly,
    no enumeration needed:

      1. `defaultAdmin()` = a 4-of-6 Gnosis Safe (`0x97dee0ea4ca10560f260a0f6f45bdc128a1
         d51f9`) -- `hasRole(DEFAULT_ADMIN_ROLE, that Safe)` independently confirmed True.
      2. `REBASER_ROLE` (the role that actually pushes stHYPE's rebase, i.e. its exchange
         rate) is held by "Overseer V1" (`0xb96f07367e69e86d6e9c3f29215885104813eeae`,
         `hasRole` confirmed True) -- NOT the Safe directly (`hasRole(REBASER_ROLE, Safe)`
         confirmed False). Overseer V1 carries HyperEVM bytecode but is NOT itself
         Safe-shaped (its own `getOwners()` would revert) -- a thin controller contract that
         `_classify_authority_holder` would wrongly degrade to the conservative unresolved
         fallback (20/0/0) if called on it directly. Its OWN `owner()` -- checked live, every
         run, the same discipline `para` StakingVault's and Ventuals' own manually-resolved
         proxy paths already use rather than trusting a one-time manual read -- resolves to
         the IDENTICAL Safe as path 1.

    Both currently-held root paths land on the SAME single Safe, so the minimum-over-paths
    convention (METHODOLOGY.md 6.2) is trivial here: one distinct authority, not two
    competing ones.

    CORRECTED before this ever reached scorers.py: today's independent research proposed
    adminKeyScore=65, multisigScore=78, compositeScore=49 for this Safe's (k=4, n=6),
    reading `key_score(4, 6)` straight off METHODOLOGY.md 4.6's own example column ("4-of-6
    = 78") -- the HyperCore-native up-to-10-signer ladder. That table is for a HIP-3
    dex/HyperCore `userToMultiSigSigners` construct, a different primitive than a real
    on-chain Gnosis Safe contract (confirmed live here: `getOwners()`/`getThreshold()` both
    resolve normally, the same structural check Kinetiq's and HyperLend's own root Safes
    pass). This project's OWN established convention for that latter case is different:
    `_classify_authority_holder` -- the exact function `score_kinetiq_staking_manager`/
    `score_para_staking_vault`/`score_ventuals_vhype_staking` already call on every one of
    THEIR OWN Safe-shaped role holders -- routes a real Safe through `_safe_rooted_scores_
    hyperevm` instead, and `score_hyperlend_pooled`'s own docstring
    (`scripts/scoring_build_2026_09_18.py`) names exactly why: `key_score` is "calibrated
    for HyperCore's up-to-10-signer multisig primitive, a different scale" than a plain
    Gnosis Safe. The already-committed, test-locked Kinetiq precedent confirms this in
    practice: `_safe_rooted_scores_hyperevm(4, 8) == (65, 80, 0)`
    (`scripts/lib/tests/test_kinetiq_hyperevm.py::
    test_four_of_eight_matches_kinetiq_live_result`), NOT `key_score(4, 8) == 76`. Applying
    the SAME, already-established Safe formula here gives adminKeyScore=65 (unchanged --
    both ladders agree at k>=3), multisigScore=70 (`min(100, 4*15 + 2*5)`, NOT 78),
    compositeScore=47 (NOT 49). Disclosed here rather than silently reproduced: this is a
    live-verified correction of the day's own research, not a second-guess of an
    already-settled repo convention.

    Cross-exposure, live-checked 2026-09-25 against every OTHER Hyperliquid target this
    project tracks that is ALSO rooted in a HyperEVM Gnosis Safe:
      - Kinetiq HIP3StakingManager and Kinetiq kHYPE StakingManager (both rooted in the
        SAME 4-of-8 Safe, `KINETIQ_ROOT_SAFE` in `scripts/scoring_build_2026_09_18.py`):
        covered automatically, every run, by `chains/hyperliquid/scorers.py`'s own
        `_apply_hyperevm_shared_root_exposure` pass (METHODOLOGY.md 4.5) -- this target's
        `reads.roleHolders` exposes its `DEFAULT_ADMIN_ROLE:<Safe>` key in the SAME shape
        Kinetiq's own entries already do, so that generic pass compares them with no new
        code here. Zero shared owners found (manually re-confirmed live via `getOwners()`
        on both Safes before writing this function, not just assumed from the generic pass
        finding nothing).
      - HIP-3 dex `para` (its own root, after `_apply_hyperevm_identity_overrides` in
        `scorers.py`, is a 1-of-3 Safe gating `OPERATOR_ROLE` on its `roleRegistry()`,
        resolved live: `0x5a24d40ef0b6856aefeefe65c332ce7cc7d9ba04`) and HyperLend Pooled
        (Governance Safe `0x2110E7B8e925C387A88259CEac9bd82c47868E9C`, 4-of-8, AND Treasury
        Safe `0xCBF400610DBF462fE316D8A7db6Ba78d57E43d7b`, 5-of-9) do NOT expose a
        comparable `reads.roleHolders` shape, so the generic pass does not compare against
        them -- checked by hand instead (`getOwners()` on all three), zero shared owners
        found with any of them. Not automated into a live per-run check here:
        `scoring_build_2026_09_18.py` (HyperLend Pooled) and `scout_2026_09_17_run2.py`
        (its Safe reader) already import FROM this module, so importing back would be
        circular.

    `oracleAuthorityScore=100`: NOT investigated this pass whether `REBASER_ROLE`'s push is
    bounded the way Kinetiq's kHYPE/kmHYPE `OracleManager` sanityChecker is (METHODOLOGY.md
    4.4) -- disclosed as an open item, not assumed benign, matching this project's own
    "a dimension that genuinely does not apply scores 100" default for a dimension not yet
    investigated, rather than silently reusing Kinetiq's specific bounded/unbounded rule for
    a structurally different contract with no sanityChecker checked here."""
    proxy = "0xffaa4a3d97fe9107cef8a3f48c069f577ff76cc1"  # stHYPE -- NOT 0x94e8396e0869c9f2200760af0621afd240e1cf38 (wstHYPE, the wrapper)
    overseer_v1 = "0xb96f07367e69e86d6e9c3f29215885104813eeae"
    default_admin_role_hash = "0x" + "0" * 64

    default_admin = _address_from_hex(_eth_call(proxy, _selector("defaultAdmin()")), f"{proxy} defaultAdmin()")
    if not _has_role(proxy, default_admin_role_hash, default_admin):
        raise HyperEvmReadError(f"{proxy}: defaultAdmin() {default_admin} does not currently hold DEFAULT_ADMIN_ROLE -- stale or mid-transfer, degrading rather than trusting defaultAdmin() alone")
    admin_scores, admin_info = _classify_authority_holder(default_admin)
    notes = [
        f"defaultAdmin() = {default_admin} ({admin_info['kind']}, {admin_info.get('threshold')}-of-{admin_info.get('owners')}) -> adminKey={admin_scores[0]} multisig={admin_scores[1]} timelock={admin_scores[2]}",
    ]
    if admin_info.get("kind") == "Gnosis Safe" and (admin_info["modules"] or int(admin_info["guard"], 16) != 0):
        notes.append(f"WARNING: {default_admin} (defaultAdmin) has a module or guard -- threshold alone no longer describes who can act; re-check by hand")

    rebaser_role_hash = _role_hash(proxy, "REBASER_ROLE")
    if not _has_role(proxy, rebaser_role_hash, overseer_v1):
        raise HyperEvmReadError(f"{proxy}: {overseer_v1} (expected Overseer V1) does not currently hold REBASER_ROLE -- degrading rather than trusting a stale address")
    overseer_owner = _address_from_hex(_eth_call(overseer_v1, _selector("owner()")), f"{overseer_v1} owner()")
    if overseer_owner.lower() == default_admin.lower():
        # Same discipline as score_ventuals_vhype_staking's OPERATOR_ROLE-same-as-owner
        # reuse: avoid re-running the full Safe-decode RPC sequence for an address already
        # classified above.
        rebaser_scores = admin_scores
        notes.append(f"REBASER_ROLE: holder {overseer_v1} (Overseer V1, a controller contract, not itself Safe-shaped -- getOwners() would revert on it) -> owner() = {overseer_owner}, the SAME Safe as defaultAdmin() -- reusing that classification rather than re-running the RPC sequence")
    else:
        rebaser_scores, rebaser_info = _classify_authority_holder(overseer_owner)
        notes.append(f"REBASER_ROLE: holder {overseer_v1} (Overseer V1) -> owner() = {overseer_owner} (DIFFERENT from defaultAdmin() -- scored independently, {rebaser_info['kind']}) -> adminKey={rebaser_scores[0]} multisig={rebaser_scores[1]} timelock={rebaser_scores[2]}")

    admin_key = min(admin_scores[0], rebaser_scores[0])
    multisig = min(admin_scores[1], rebaser_scores[1])
    timelock = min(admin_scores[2], rebaser_scores[2])
    notes.append(
        f"combined (min over every currently-held root role, METHODOLOGY.md 6.2): adminKey={admin_key} multisig={multisig} timelock={timelock} "
        f"-- CORRECTED from today's own research proposal (adminKeyScore=65, multisigScore=78, compositeScore=49, derived via key_score(4,6), "
        f"the HyperCore-native ladder, METHODOLOGY.md 4.6's own '4-of-6 = 78' example): a real Gnosis Safe on HyperEVM (getOwners()/getThreshold() "
        f"both resolved live) uses this project's OWN already-established _safe_rooted_scores_hyperevm formula instead -- the same one Kinetiq's/"
        f"Ventuals'/para StakingVault's own Safe-shaped role holders already go through via _classify_authority_holder, and the one score_hyperlend_"
        f"pooled's own docstring names explicitly for exactly this case ('the Standard Gnosis Safe formula ... not key_score, that one is calibrated "
        f"for HyperCore's up-to-10-signer multisig primitive, a different scale')."
    )
    notes.append(
        "cross-checked against every OTHER Hyperliquid target rooted in a HyperEVM Gnosis Safe this project tracks, live, 2026-09-25: Kinetiq "
        "HIP3StakingManager/kHYPE StakingManager (shared 4-of-8 root Safe) -- zero overlap, also covered every run by scorers.py's own generic "
        "HyperEVM shared-root pass since this entry exposes DEFAULT_ADMIN_ROLE:<Safe> the same way those two do; HIP-3 dex para's own 1-of-3 "
        "OPERATOR_ROLE Safe -- zero overlap; HyperLend Pooled's Governance (4-of-8) and Treasury (5-of-9) Safes -- zero overlap with either. Not "
        "automated (only checked by hand this pass): comparing against para/HyperLend would need importing scoring_build_2026_09_18.py/"
        "scout_2026_09_17_run2.py back into this module, which already imports FROM this one -- a circular import."
    )

    return {
        "target": proxy,
        "label": "stHYPE liquid staking (HyperEVM)",
        "reads": {
            "defaultAdmin": default_admin,
            "roleHolders": {
                f"DEFAULT_ADMIN_ROLE:{default_admin}": {"adminKey": admin_scores[0], "multisig": admin_scores[1], "timelock": admin_scores[2]},
                f"REBASER_ROLE:{overseer_v1}": {"adminKey": rebaser_scores[0], "multisig": rebaser_scores[1], "timelock": rebaser_scores[2]},
            },
            "rebaserRoleHolder": overseer_v1,
            "rebaserRoleHolderOwner": overseer_owner,
        },
        "adminKeyScore": admin_key,
        "multisigScore": multisig,
        "timelockScore": timelock,
        "oracleAuthorityScore": 100,
        "crossExposureScore": 100,
        "compositeScore": composite(admin_key, multisig, timelock),
        "notes": notes,
    }


_kn_cache = {}


def kn(addr):
    """(threshold, authorized users) of a HyperCore user; null -> single key (1, 1)."""
    if addr not in _kn_cache:
        m = info({"type": "userToMultiSigSigners", "user": addr})
        _kn_cache[addr] = ((1, 1), [addr]) if m is None else ((m["threshold"], len(m["authorizedUsers"])), m["authorizedUsers"])
    return _kn_cache[addr]


def key_score(k, n):
    """Section 4.6 k-of-n mapping, non-decreasing along the rule 4.2 ordering
    (lower k weaker, then larger n weaker), strict except at the 0 floor and 100 cap.
    HyperCore multisigs have n <= 10."""
    if k == 1:
        return 15 if n == 1 else max(0, 14 - 2 * (n - 1))
    return min(100, 20 * k - (n - k))


def admin_key_score(k, n):
    """Section 4.6 ladder, same thresholds as scripts/lib/scorers.py _safe_rooted_scores."""
    if k >= 3:
        return 65
    if k == 2:
        return 50
    return 10 if n == 1 else 5


def composite(admin_key, multisig, timelock):
    # Exact-integer form, not math.floor(0.4*a+0.3*m+0.3*t+0.5) -- that float form reads one LOWER
    # than exact on 2054/1,030,301 (a,m,t) triples (scripts/lib/scorers.py, scripts/
    # validate_all_scorers.py; same defect found and fixed in the audit_rotation_index* family,
    # commit e8ad7d5 -- this is the same bug in a sibling live re-derivation script).
    return (4 * admin_key + 3 * multisig + 3 * timelock + 5) // 10


def fmt(t):
    return "single key" if t == (1, 1) else f"{t[0]}-of-{t[1]}"


def weakest(addrs):
    return min(addrs, key=lambda a: (kn(a)[0][0], -kn(a)[0][1]))


def score_hip3_dex(name):
    dexes = [d for d in info({"type": "perpDexs"}) if d]
    d = next(x for x in dexes if x["name"] == name)
    sub = {k: v for k, v in (d.get("subDeployers") or [])}
    dep = d["deployer"]
    root_set = {dep, *[a for v in ROOT_CONTROL_VARIANTS for a in sub.get(v, [])]}
    oracle_set = {dep, d.get("oracleUpdater") or dep, *[a for v in ORACLE_VARIANTS for a in sub.get(v, [])]}
    root_w, oracle_w = weakest(root_set), weakest(oracle_set)
    (rk, rn), (ok, on) = kn(root_w)[0], kn(oracle_w)[0]

    # 4.5 cross exposure: other HIP-3 dexes sharing any root key (authority address or its signer)
    def root_keys(x):
        addrs = {x["deployer"]} | ({x["oracleUpdater"]} if x.get("oracleUpdater") else set())
        for _, lst in x.get("subDeployers") or []:
            addrs |= set(lst)
        out = set()
        for a in addrs:
            out |= set(kn(a)[1]) | {a}
        return out

    mine = root_keys(d)
    sharing = sorted(x["name"] for x in dexes if x["name"] != name and root_keys(x) & mine)
    evm_side = {a: {"code": evm("eth_getCode", [a, "latest"]), "nonce": int(evm("eth_getTransactionCount", [a, "latest"]), 16)}
                for a in sorted(root_set | oracle_set)}

    m, ctxs = info({"type": "metaAndAssetCtxs", "dex": name})
    oi = sum(float(c["openInterest"]) * float(c["markPx"]) for c in ctxs if c.get("markPx"))
    stake = info({"type": "delegatorSummary", "user": dep})

    admin = admin_key_score(rk, rn)
    ms = key_score(rk, rn)
    tl = 0
    return {
        "target": dep,
        "label": f"HIP-3 dex {name}",
        "reads": {
            "deployer": [dep, fmt(kn(dep)[0])],
            "oracleUpdaterField": d.get("oracleUpdater"),
            "subDeployers": {k: [[a, fmt(kn(a)[0])] for a in v] for k, v in sub.items()},
            "rootControlSet": sorted(root_set),
            "oracleSet": sorted(oracle_set),
            "evmSide": evm_side,
            "assets": len(m["universe"]),
            "openInterestUsd": round(oi),
            "totalNetDepositUsd": round(float(info({"type": "perpDexStatus", "dex": name})["totalNetDeposit"])),
            "deployerDelegatedHype": float(stake["delegated"]),
            "dexesSharingARootKey": sharing,
        },
        "adminKeyScore": admin,
        "multisigScore": ms,
        "timelockScore": tl,
        "oracleAuthorityScore": key_score(ok, on),
        "crossExposureScore": max(0, 100 - 20 * len(sharing)),
        "compositeScore": composite(admin, ms, tl),
        "weakestRootKey": [root_w, fmt((rk, rn))],
        "weakestOracleKey": [oracle_w, fmt((ok, on))],
    }


def _coeff(weights, total, num, den):
    c = 0
    for i, w in enumerate(sorted(weights, reverse=True)):
        c += w
        if c * den > num * total:
            return i + 1, c / total
    return None, None


def score_l1():
    from web3 import Web3

    target = Web3.to_checksum_address(Web3.keccak(text="hyperliquid:hypercore-l1")[-20:])
    v = [x for x in info({"type": "validatorSummaries"}) if x["isActive"]]
    total = sum(x["stake"] for x in v)
    ent = {}
    for x in v:
        key = "Hyper Foundation" if x["name"].startswith("Hyper Foundation") else x["validator"]
        ent[key] = ent.get(key, 0) + x["stake"]
    val_w, ent_w = [x["stake"] for x in v], list(ent.values())
    k_l, share_l = _coeff(ent_w, total, 1, 3)
    k_h, share_h = _coeff(ent_w, total, 1, 2)
    k_f, share_f = _coeff(ent_w, total, 2, 3)
    m, ctxs = info({"type": "metaAndAssetCtxs"})
    oi = sum(float(c["openInterest"]) * float(c["oraclePx"]) for c in ctxs)
    admin, ms, tl = 15, min(100, 15 * k_f + 5 * k_l), 0
    return {
        "target": target,
        "label": "Hyperliquid L1 (HyperCore validator set)",
        "reads": {
            "activeValidators": len(v),
            "activeEntities": len(ent),
            "foundationLabeledShare": ent["Hyper Foundation"] / total,
            "validatorCoefficients": {"gt1_3": _coeff(val_w, total, 1, 3), "gt1_2": _coeff(val_w, total, 1, 2), "gt2_3": _coeff(val_w, total, 2, 3)},
            "entityCoefficients": {"gt1_3": [k_l, share_l], "gt1_2": [k_h, share_h], "gt2_3": [k_f, share_f]},
            "mainDexAssets": len(m["universe"]),
            "mainDexOpenInterestUsd": round(oi),
        },
        "adminKeyScore": admin,
        "multisigScore": ms,
        "timelockScore": tl,
        "oracleAuthorityScore": min(100, 20 * k_h),
        "crossExposureScore": 100,
        "compositeScore": composite(admin, ms, tl),
    }


if __name__ == "__main__":
    res = [score_hip3_dex("xyz"), score_l1()]
    if len(sys.argv) > 1 and sys.argv[1] == "scores":
        keys = ("adminKeyScore", "multisigScore", "timelockScore", "oracleAuthorityScore", "crossExposureScore", "compositeScore")
        print(json.dumps({r["label"]: [r[k] for k in keys] for r in res}))
    else:
        print(json.dumps(res, indent=1))
