"""Gnosis Safe modules and guard: read them, and say whether each one has been analyzed.

ADDED 2026-09-21. A Safe's owner set and threshold only describe who can act if no module and no
guard changes that: a module can execute transactions as the Safe without the owners' signatures,
and a guard can block them. Until today only some scorers read either (Robinhood Chain's
`_safe_rooted_entry`, Ethereum L1's Ethena and Horizon scorers, Tempo, Hyperliquid); the shared
`safe_owners_and_threshold` helper never did. `scripts/check_safe_modules_guards.py` sweeps every
registered root Safe with this module and reports anything not in KNOWN_ANALYSES, so a module added
later shows up as UNANALYZED instead of silently.

Reads are retried and a failed read is `None`, never an empty list: "no module" and "could not read"
are different results and only the first one is a clean bill.

The same sweep also reads the Safe's singleton (its masterCopy, storage slot 0) and fallback handler, and
says whether each is one of the published Safe builds. A proxy whose singleton is not a published build
is not necessarily wrong, but it must be looked at once: the singleton IS the Safe's logic.
"""
import os
import sys

from web3 import Web3

sys.path.insert(0, os.path.dirname(__file__))
from web3_utils import RpcUnavailable, _read, call_raw, read_slot_as_address  # noqa: E402

SENTINEL = "0x0000000000000000000000000000000000000001"
ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"
GUARD_SLOT = "0x" + bytes(Web3.keccak(text="guard_manager.guard.address")).hex()
FALLBACK_HANDLER_SLOT = "0x" + bytes(Web3.keccak(text="fallback_manager.handler.address")).hex()
_MODULES_ABI = [{"name": "getModulesPaginated", "type": "function", "stateMutability": "view",
                 "inputs": [{"type": "address"}, {"type": "uint256"}],
                 "outputs": [{"type": "address[]"}, {"type": "address"}]}]
_LEGACY_MODULES_ABI = [{"name": "getModules", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "address[]"}]}]
_PAGE = 10
_MAX_PAGES = 5

# ADDED 2026-09-26: the same Confirmed Transaction Module 0.1.0 (5,451 bytes, code hash 0x31eca2a56e5118d7...) is enabled on the
# Chainlink feed-owner Safes of Ethereum, Base, Arbitrum and Monad (the 4-of-9 group with the same 9 signers as Robinhood's), byte-identical
# to the one analyzed on Robinhood Chain below, so the analysis of its LOGIC carries over. Its STATE was read per chain: manager() is the
# Safe itself on all five chains; on Ethereum, Base and Arbitrum it is in active use (Ethereum: 280 Confirmed, 90 Executed, 185 Revoked
# events; Base: 9 ExecutorUpdated; Arbitrum: 8 Confirmed, 8 Executed), unlike Robinhood's unused one. The executor set was replayed from
# the ExecutorUpdated events (Blockscout, all pages) and matched against live isExecutor() for every address ever touched: 8 allowed
# executors on Ethereum, 7 on Base and 8 on Arbitrum, almost the same addresses on each (Base lacks 0x480496c0...), 2 of them
# (0x7052cB84..., 0x480496c0...) also signers of the Safe. An executor runs only what the Safe confirmed (its threshold still decides), it does not lower the threshold.
# Monad's copy has no explorer and was not replayed (manager() only).
# ADDED 2026-10-04: Plasma's Chainlink feed-owner Safe 0x73877Fe3... (4-of-9, same 9 signers) carries a sixth copy, 0xd73014ee...:
# 5,451 bytes, byte-identical to Ethereum's (same code hash 0x31eca2a56e5118d7...), manager() = that Safe. Not replayed (manager() only),
# like Monad's. Without this entry the Safe read as UNRESOLVED, which would floor any Plasma price path through it.
_CHAINLINK_MODULE_SUMMARY = (
    "Confirmed Transaction Module 0.1.0 on a Chainlink feed-owner Safe (4-of-9, same 9 signers as Robinhood's). Byte-identical to the "
    "module analyzed on Robinhood Chain (5,451 bytes), so it does not bypass the threshold: it separates approving from executing. "
    "manager() is the Safe itself. State differs from Robinhood: see the 2026-09-26 note above this table for the per-chain activity "
    "and the replayed executor set."
)

# Every module or guard found on a registered root Safe, with what was established about it and when.
# Keys are lowercase addresses. A module or guard NOT in here is reported as UNANALYZED.
KNOWN_ANALYSES = {
    "0xe5fb4576bbed29ac3846ccde81e2201e72cc5316": {
        "analyzed": "2026-09-21",
        "kind": "module",
        "name": "Confirmed Transaction Module 0.1.0",
        "summary": (
            "Enabled on Robinhood Chain's Chainlink Price Feed Admin Safe (4-of-9). eth_call simulation, no transaction: "
            "confirmTransaction, setExecutor and revokeTransaction revert 'Method can only be called from manager' from a "
            "random address and succeed from the Safe (its own manager), and executeTransaction reverts 'only executor can "
            "call' from both, so the Safe's threshold still decides what runs and a separate executor only runs what the "
            "Safe confirmed. None of the 9 owners is an executor, the module has emitted no log and the Safe no "
            "ExecutionFromModuleSuccess event. It does not bypass the threshold; it separates approving from executing. Unused today."
        ),
    },
    "0x2e1b5a40edc922bce489668b11749b8eabd67f6b": {
        "analyzed": "2026-09-26",
        "kind": "module",
        "name": "Confirmed Transaction Module 0.1.0 (Ethereum)",
        "summary": _CHAINLINK_MODULE_SUMMARY,
    },
    "0xf3c72d97a5dcf0449e89bbce1a0581d8d15c0237": {
        "analyzed": "2026-09-26",
        "kind": "module",
        "name": "Confirmed Transaction Module 0.1.0 (Base)",
        "summary": _CHAINLINK_MODULE_SUMMARY,
    },
    "0x7f9971226aead3013a5db7767e59dac48d01c4f6": {
        "analyzed": "2026-09-26",
        "kind": "module",
        "name": "Confirmed Transaction Module 0.1.0 (Arbitrum)",
        "summary": _CHAINLINK_MODULE_SUMMARY,
    },
    "0x412fc13437e86889b6c4c010236da46642d138fc": {
        "analyzed": "2026-09-26",
        "kind": "module",
        "name": "Confirmed Transaction Module 0.1.0 (Monad)",
        "summary": _CHAINLINK_MODULE_SUMMARY,
    },
    "0xd73014ee51fb33915578b24a70133b0ba734f35f": {
        "analyzed": "2026-10-04",
        "kind": "module",
        "name": "Confirmed Transaction Module 0.1.0 (Plasma)",
        "summary": _CHAINLINK_MODULE_SUMMARY,
    },
    "0xcf57572261c7c2bcf21ffd220ea7d1a27d40a827": {
        "analyzed": "2026-09-21",
        "kind": "module",
        "name": "Arbitrum L2 UpgradeExecutor",
        "summary": (
            "Enabled on the Arbitrum Security Council Emergency Safe (9-of-12). It is the same address as the L2 "
            "UpgradeExecutor whose EXECUTOR_ROLE this Safe holds (already read by score_arbitrum_security_council_safe), "
            "so the DAO's executor path can act as the Safe without the Council's signatures, in addition to the Council "
            "acting through the executor. Consistent with Arbitrum's documented design (DAO-approved actions rotate Council "
            "members), not checked against its documentation in this pass. The Safe's threshold is not the only authority "
            "over it."
        ),
    },
    "0x4405f3b660eb53c4d1ac04546ef30a7a6bf91036": {
        "analyzed": "2026-09-21",
        "kind": "module",
        "name": "HypernativeModule (pause), protects 0xc0E823Ef...4078",
        "summary": (
            "Enabled on Radiant's emergency-admin Safe (1-of-5). Its revert strings read 'HypernativeModule'. eth_call "
            "simulation, no transaction: pause() succeeds from the module's owner (a bare EOA, 9 transactions, ~0.04 ETH) and "
            "reverts OwnableUnauthorizedAccount from the Safe and from a random address; changeUpdater succeeds from the "
            "owner or the updater (the Safe) only; replaceProtectedContract from the updater only. Powers: pause-class, by "
            "one extra key beside the Safe's five. No fund-moving call was found among its functions."
        ),
    },
    "0x28e24b1d5fefc0e9c0f354e9d7411f5f44827eab": {
        "analyzed": "2026-09-21",
        "kind": "module",
        "name": "HypernativeModule (pause, setPoolPause), protects 0x73Eb9AaE...d559",
        "summary": (
            "Second pause module on Radiant's emergency-admin Safe, same owner EOA and same updater (the Safe) as the first. "
            "pause() succeeds from the owner and reverts from the Safe and from a random address; setPoolPause(bool) reverts "
            "for all three callers in the simulation. Pause-class powers only."
        ),
    },
    "0x74abe7805541c28f31953b3cda9711dc96278d29": {
        "analyzed": "2026-09-21",
        "kind": "guard",
        "name": "EthenaSafeGuard",
        "summary": (
            "Set as the guard of Ethena's 5-of-10 Safe on Ethereum L1 and of the same committee's Safe on Plasma (same guard "
            "address). On L1 it is a positive control already recorded by score_ethena_minting: only whitelisted executors "
            "can submit the Safe's transactions, and removing the guard takes 48 hours in public (installed 2026-07-06). Its "
            "selectors (checkTransaction, scheduleTimelockedOperation, enableModule, setGuard, setFallbackHandler, "
            "timelockDelay, allowedSafes, executorWhitelist) are consistent with that. Not scored. The Plasma deployment's "
            "own configuration was not read."
        ),
    },
}


# ADDED 2026-09-27 (backlog item "known-vulnerable module code registry", data/finding_2026-09-20-
# competitor-gaps-and-morpho-vault-layer.md, eighth pass): a module found on a tracked Safe is often a
# minimal-proxy CLONE of one shared implementation (EIP-1167, see clone_impl() below), so a disclosed
# flaw is a property of the IMPLEMENTATION address, not of each clone individually -- one entry here
# covers every Safe that clones it, present or future. Keys are lowercase IMPLEMENTATION addresses (the
# clone's own address is never a key here). Re-derived from verified source on 2026-09-27, not copied
# from the 21/09 finding's prose: both addresses' SignatureChecker.sol were fetched from Blockscout and
# diffed directly. The June 2026 Zodiac Roles/Delay ERC-1271 flaw: `SignatureChecker.isValidSignature`
# read `(, bytes memory returnData) = signer.staticcall(...)` and returned `bytes4(returnData) ==
# EIP1271_MAGIC_VALUE` without checking the staticcall's own success flag, so a signer whose call
# reverts with return data happening to start with the right 4 bytes still passes. It needs the role
# MEMBER to be a CONTRACT (extcodesize > 0) whose isValidSignature reverts that way -- the checker
# already returns false before the call for a plain EOA member (extcodesize == 0), never reaching the
# vulnerable line, so an all-EOA membership is unaffected regardless of which implementation it clones.
KNOWN_MODULE_IMPLEMENTATION_ADVISORIES = {
    "0x9646fdad06d3e24444381f44362a3b0eb343d337": {
        "name": "Zodiac Roles v2, pre-fix",
        "verified_source_as_of": "2026-03-19",
        "status": "vulnerable",
        "advisory": (
            "ERC-1271 signature check (SignatureChecker.sol) does not verify the staticcall itself "
            "succeeded before reading its return data -- disclosed by the Zodiac team June 2026, "
            "exploited against Gnosis Pay accounts 1 June 2026, fixed 5 June 2026."
        ),
        "condition": "exploitable only if a role MEMBER is a contract (not a plain EOA) whose isValidSignature can revert with crafted return data",
    },
    "0xf2964ce6161ce0e75964fe7927ce114cb0b283d5": {
        "name": "Zodiac Roles v2, patched",
        "verified_source_as_of": "2026-06-27",
        "status": "patched",
        "advisory": "SignatureChecker.sol checks the staticcall's success flag before reading return data -- not affected by the June 2026 disclosure.",
        "condition": None,
    },
}


def module_implementation_advisory(implementation_address):
    """The KNOWN_MODULE_IMPLEMENTATION_ADVISORIES entry for a module's clone-of implementation address
    (case-insensitive), or None if `implementation_address` is None or matches nothing here -- absence
    is not a clean bill, it means no advisory is on file for that implementation, not that none exists."""
    if not implementation_address:
        return None
    return KNOWN_MODULE_IMPLEMENTATION_ADVISORIES.get(implementation_address.lower())


# Published Safe singleton and fallback-handler builds, each checked against Sourcify on Ethereum mainnet on
# 2026-09-21 (exact match, contract name as labelled; the v1.1.1 singleton is a partial match). Lowercase keys.
CANONICAL_SINGLETONS = {
    "0xd9db270c1b5e3bd161e8c8503c55ceabee709552": "v1.3.0 GnosisSafe",
    "0x3e5c63644e683549055b9be8653de26e0b4cd36e": "v1.3.0 GnosisSafeL2",
    "0xfb1bffc9d739b8d520daf37df666da4c687191ea": "v1.3.0 GnosisSafeL2 (eip155 deployment)",
    "0x69f4d1788e39c87893c980c06edf4b7f686e2938": "v1.3.0 GnosisSafe (eip155 deployment)",
    "0x41675c099f32341bf84bfc5382af534df5c7461a": "v1.4.1 Safe",
    "0x29fcb43b46531bca003ddc8fcb67ffe91900c762": "v1.4.1 SafeL2",
    "0x34cfac646f301356faa8b21e94227e3583fe3f5f": "v1.1.1 GnosisSafe",
    # ADDED 2026-09-26: v1.5.0 SafeL2, seen on a tracked Robinhood Chain Safe (ramses) after its ChangedMasterCopy of 2026-09-25. Checked
    # against safe-global/safe-deployments v1.5.0 (canonical address on chains 1 and 4663, code hash 0x180193227186ccb8...), the live code hash
    # on Robinhood Chain matches it, and Sourcify has an exact match named SafeL2 on Ethereum.
    "0xedd160febbd92e350d4d398fb636302fccd67c7e": "v1.5.0 SafeL2",
}
CANONICAL_FALLBACK_HANDLERS = {
    "0xf48f2b2d2a534e402487b3ee7c18c33aec0fe5e4": "v1.3.0 CompatibilityFallbackHandler",
    "0x017062a1de2fe6b99be3d9d37841fed19f573804": "v1.3.0 CompatibilityFallbackHandler (eip155 deployment)",
    "0xfd0732dc9e303f09fcef3a7388ad10a83459ec99": "v1.4.1 CompatibilityFallbackHandler",
    "0xd5d82b6addc9027b22dca772aa68d5d74cdbdf44": "v1.1.1 DefaultCallbackHandler",
    # ADDED 2026-09-26: v1.5.0 CompatibilityFallbackHandler, same source and live code-hash check as the v1.5.0 SafeL2 above (0x3c6a85bc...).
    "0x3efcbb83a4a7afcb4f68d501e2c2203a38be77f4": "v1.5.0 CompatibilityFallbackHandler",
}
# A singleton that is not a published build but has been read and understood.
KNOWN_SINGLETON_ANALYSES = {
    "0x113779daf982b09f7a9db64af132aa97496b3999": {
        "analyzed": "2026-09-21",
        "name": "GnosisSafe 1.3.0 rebuilt with the ERC-165 guard check, Robinhood Chain",
        "summary": (
            "The singleton behind Robinhood Chain's Chainlink Price Feed Admin Safe, at an address the Safe deployment "
            "lists do not publish (23,328 bytes, solc 0.7.6). Sourcify exact match on Robinhood Chain (chain 4663) for "
            "contracts/GnosisSafe.sol. Its verified sources were diffed against safe-global/safe-contracts at tag v1.3.0: "
            "every core file is identical (GnosisSafe, Executor, OwnerManager, ModuleManager, FallbackManager, "
            "SelfAuthorized, SignatureDecoder, StorageAccessible and the rest) except contracts/base/GuardManager.sol, "
            "where setGuard additionally requires the new guard to support the Guard interface (ERC-165, error GS300). "
            "That is a later upstream hardening, more restrictive than the published build, not a behaviour change to "
            "owners, threshold, modules or execution."
        ),
    },
}
# A Safe deployed WITHOUT a proxy runs its own code: its slot 0 (the singleton) is zero and the code itself is the logic, so
# it is keyed by keccak of its runtime code (lowercase hex, no 0x), accepted only after that code's verified sources were
# compared line by line with the official Safe release it vendors (decided by Spap on 2026-10-05).
KNOWN_PROXYLESS_SAFES = {
    "8d0ac2ac4115860f948942d0a29e00aac085b33547ec5850d03189aaff5bbd2f": {
        "analyzed": "2026-10-05",
        "name": "API3 GnosisSafeWithoutProxy (safe-contracts 1.3.0, no proxy), Robinhood Chain 0xbAC8d514",
        "summary": (
            "The 8-owner, threshold-4 Safe that owns API3's OwnableCallForwarder 0x0F52eE9C on Robinhood Chain, 12,330 bytes of "
            "runtime code, no immutables. Sourcify exact match on chain 4663 (creation and runtime) for "
            "contracts/access/GnosisSafeWithoutProxy.sol, solc 0.8.12, optimizer 200 runs, EVM london. Its 15 vendored files "
            "under contracts/vendor/@gnosis.pm/safe-contracts@1.3.0 (GnosisSafe, Executor, FallbackManager, GuardManager, "
            "ModuleManager, OwnerManager, Enum, EtherPaymentFallback, SecuredTokenTransfer, SelfAuthorized, SignatureDecoder, "
            "Singleton, StorageAccessible, GnosisSafeMath, ISignatureValidator) are byte-identical to tag v1.3.0 of "
            "safe-global/safe-smart-account (formerly safe-contracts): no difference at all. The only added code is the "
            "wrapper's constructor (threshold reset to 0, setupOwners, setupModules(0, empty), no fallback handler, no payment, "
            "a SafeSetup event), which is not in the runtime code; setup() cannot run again since setupOwners requires a zero "
            "threshold. Compiled with solc 0.8 instead of 0.7.6: checked arithmetic only adds reverts, it cannot widen who can "
            "act. Owners, threshold, modules, guard, fallback handler, execTransaction and the signature checks are those of "
            "Safe 1.3.0. Read live: no module, guard 0, fallback handler 0, VERSION 1.3.0. Contracts/test/MockSafeTarget.sol "
            "is in the same compilation but not inherited."
        ),
    },
}


def read_code_hash(w3, safe, retries=4):
    """keccak of the account's runtime code (lowercase hex, no 0x), or None if the read failed."""
    try:
        code = _read(lambda: w3.eth.get_code(Web3.to_checksum_address(safe)), retries, what=f"code of {safe}", classify=lambda _: False)
    except RpcUnavailable:
        return None
    return Web3.keccak(bytes(code)).hex().removeprefix("0x")


def _slot_or_none(w3, safe, slot, retries):
    """read_slot_as_address() now RAISES RpcUnavailable instead of returning None on a persistent
    RPC failure (added 2026-09-22: eth_getStorageAt can't revert, so a failure there is never a
    legitimate 'no answer' -- see web3_utils.RpcUnavailable). This module's own read_singleton/
    read_guard/read_fallback_handler document 'None if the read failed' as their contract, and
    gate_findings() below depends on that -- a flaky RPC must stay 'info, never blocking' (a
    deliberate choice, see gate_findings' own docstring), so the conversion happens here, once."""
    try:
        return read_slot_as_address(w3, safe, slot, retries=retries)
    except RpcUnavailable:
        return None


def read_singleton(w3, safe, retries=4):
    """The proxy's singleton (masterCopy, storage slot 0) as a checksum address, or None if the read failed."""
    return _slot_or_none(w3, safe, "0x0", retries)


def read_fallback_handler(w3, safe, retries=4):
    """The Safe's fallback handler as a checksum address, ZERO_ADDRESS if none is set, None if the read failed."""
    return _slot_or_none(w3, safe, FALLBACK_HANDLER_SLOT, retries)


def classify_singleton(singleton, canonical=None, known=None):
    """"unread", "canonical" (a published build), "analyzed" (read and understood) or "unanalyzed"."""
    canonical = CANONICAL_SINGLETONS if canonical is None else canonical
    known = KNOWN_SINGLETON_ANALYSES if known is None else known
    if singleton is None:
        return "unread"
    if singleton.lower() in canonical:
        return "canonical"
    return "analyzed" if singleton.lower() in known else "unanalyzed"


def classify_fallback_handler(handler, canonical=None):
    """"unread", "none", "canonical" or "unanalyzed" (a handler that is not a published build)."""
    canonical = CANONICAL_FALLBACK_HANDLERS if canonical is None else canonical
    if handler is None:
        return "unread"
    if handler.lower() == ZERO_ADDRESS:
        return "none"
    return "canonical" if handler.lower() in canonical else "unanalyzed"


def read_modules(w3, safe, retries=4):
    """Enabled modules of a Safe as a list of checksum addresses (possibly empty), or None if the read
    failed. Follows the pagination cursor for up to _MAX_PAGES pages.

    call_raw() RAISES RpcUnavailable on a persistent RPC failure now (2026-09-22) instead of
    returning the same None a confirmed revert would -- caught here and turned back into this
    function's own documented None-on-failure contract, same as _slot_or_none() above. This also
    makes the "no getModulesPaginated() -- fall back to the legacy getModules()" branch below more
    correct than before: `page is None` after this change means a CONFIRMED revert (RpcUnavailable
    already left through the except), so falling back to the legacy ABI only happens when
    getModulesPaginated() genuinely isn't implemented, never on a network blip that happened to hit
    the first page."""
    modules = []
    start = SENTINEL
    for _ in range(_MAX_PAGES):
        try:
            page = call_raw(w3, safe, _MODULES_ABI, "getModulesPaginated", start, _PAGE, retries=retries)
        except RpcUnavailable:
            return None
        if page is None:
            if start == SENTINEL:
                # Safe v1.0.0 has getModules() and no getModulesPaginated(); a real read failure fails this one too.
                try:
                    legacy = call_raw(w3, safe, _LEGACY_MODULES_ABI, "getModules", retries=1)
                except RpcUnavailable:
                    return None
                if legacy is not None:
                    return [Web3.to_checksum_address(m) for m in legacy]
            return None
        found, nxt = page
        modules.extend(Web3.to_checksum_address(m) for m in found)
        if not nxt or nxt.lower() in (SENTINEL.lower(), ZERO_ADDRESS):
            return modules
        start = nxt
    return modules


def gate_findings(w3, safe, retries=4):
    """(blocking, info) text lists for the authority gate in web3_utils.safe_owners_and_threshold.

    blocking: an unanalyzed module (it can execute as the Safe without the owners) or a singleton that is neither a published
    Safe build nor analyzed (the Safe's logic is unknown); a zero singleton passes only when the Safe's own code hash is in
    KNOWN_PROXYLESS_SAFES (a Safe deployed without a proxy). Either one means the owner set and threshold are not the authority.
    info: a read that failed. Never blocking, so a flaky RPC cannot collapse a score. Guards and fallback handlers are not
    checked here: they can block or answer calls, not act as the Safe."""
    blocking, info = [], []
    modules = read_modules(w3, safe, retries)
    if modules is None:
        info.append("modules that could not be read")
    else:
        unknown = [m for m in modules if m.lower() not in KNOWN_ANALYSES]
        if unknown:
            blocking.append("module(s) not analyzed: " + ", ".join(unknown))
    singleton = read_singleton(w3, safe, retries)
    status = classify_singleton(singleton)
    if status == "unanalyzed" and singleton.lower() == ZERO_ADDRESS and read_code_hash(w3, safe, retries) in KNOWN_PROXYLESS_SAFES:
        status = "analyzed"  # no proxy: its own code is the logic, pinned by hash (an unread code stays blocking)
    if status == "unread":
        info.append("a singleton that could not be read")
    elif status == "unanalyzed":
        blocking.append(f"singleton {singleton} that is not a published Safe build and not analyzed")
    return blocking, info


def read_guard(w3, safe, retries=4):
    """The Safe's transaction guard as a checksum address, ZERO_ADDRESS if none is set, None if the read failed."""
    return _slot_or_none(w3, safe, GUARD_SLOT, retries)


def classify(modules, guard, known=None):
    """Status of one Safe from its `modules` (list or None) and `guard` (address, ZERO_ADDRESS or None).

    - "unread":     a read failed; nothing is claimed either way.
    - "clean":      no module and no guard.
    - "analyzed":   at least one module or guard, every one of them in `known`.
    - "unanalyzed": at least one module or guard that is not in `known` (needs a human).
    """
    known = KNOWN_ANALYSES if known is None else known
    if modules is None or guard is None:
        return {"status": "unread", "modules": modules, "guard": guard, "unanalyzed": []}
    has_guard = guard.lower() != ZERO_ADDRESS
    present = [m for m in modules] + ([guard] if has_guard else [])
    if not present:
        return {"status": "clean", "modules": modules, "guard": guard, "unanalyzed": []}
    unanalyzed = [a for a in present if a.lower() not in known]
    return {"status": "unanalyzed" if unanalyzed else "analyzed", "modules": modules, "guard": guard, "unanalyzed": unanalyzed}


def singleton_note(safe, singleton, canonical=None, known=None):
    """One note line for a scorer about the Safe's singleton. Never a score input."""
    canonical = CANONICAL_SINGLETONS if canonical is None else canonical
    known = KNOWN_SINGLETON_ANALYSES if known is None else known
    status = classify_singleton(singleton, canonical, known)
    if status == "unread":
        return f"Safe {safe}: singleton could not be read this run"
    if status == "canonical":
        return f"Safe {safe}: singleton {singleton} is a published Safe build ({canonical[singleton.lower()]})"
    if status == "analyzed":
        info = known[singleton.lower()]
        return f"Safe {safe}: singleton {singleton} is not a published Safe build, analyzed {info['analyzed']}: {info['summary']}"
    return f"WARNING (unanalyzed singleton, re-check by hand): Safe {safe}: singleton {singleton} is not a published Safe build and has not been analyzed"


def note_for(safe, modules, guard, known=None):
    """One note line for a scorer: what this Safe has enabled and, for known ones, what was found. Never a score input."""
    known = KNOWN_ANALYSES if known is None else known
    verdict = classify(modules, guard, known)
    if verdict["status"] == "unread":
        return f"Safe {safe}: modules or guard could not be read this run, so the threshold is not confirmed to be the only authority"
    if verdict["status"] == "clean":
        return f"Safe {safe}: no module and no guard enabled (read this run), so the owner set and threshold are the whole authority"
    parts = []
    for addr in verdict["modules"] + ([guard] if guard.lower() != ZERO_ADDRESS else []):
        info = known.get(addr.lower())
        label = "guard" if addr == guard else "module"
        parts.append(f"{label} {addr} = {info['name']}: {info['summary']}" if info else f"{label} {addr} = NOT ANALYZED")
    prefix = "WARNING (unanalyzed module or guard, re-check by hand): " if verdict["status"] == "unanalyzed" else ""
    return f"{prefix}Safe {safe} has " + "; ".join(parts)
