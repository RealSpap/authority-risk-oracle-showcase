"""Morpho Vault V2 per-function timelocks, read live (METHODOLOGY.md, "Morpho Vault V2 scoring", decision 1).

MOVED 2026-10-04 from chains/ethereum-l1/scorers.py (`_vault_v2_timelock_and_gates`) so the 6 Robinhood Chain V2 vaults
use the same reader as Ethereum L1's; until then they read setOwner/setCurator/setIsSentinel, which a V2 vault never
timelocks, so their timelockScore was a constant (15 or 10) whatever the real delays (7 days on 4 vaults, 3 on 2).
Two fixes on the way, both found by the 2026-10-04 depth review:
- a function that is permanently abdicated can never be called again, so its timelock protects nothing and is left out
  of the minimum (Purinta abdicated setAdapterRegistry, whose own timelock is 0: counting it gave a false 0-day minimum);
- a timelock() or abdicated() read that reverts is UNREAD, and makes the minimum UNREAD (None). It used to become 0.
"""
from web3 import Web3

try:  # loaded as lib.morpho_v2 (Robinhood scorers) or as a bare module (chain scorers put scripts/lib on sys.path)
    from .web3_utils import call_raw
except ImportError:
    from web3_utils import call_raw

FUND_REDIRECTING_FUNCTION_SIGS = [
    "addAdapter(address)", "removeAdapter(address)", "setAdapterRegistry(address)",
    "increaseAbsoluteCap(bytes,uint256)", "increaseRelativeCap(bytes,uint256)",
]
EXIT_GATE_FUNCTION_SIGS = {
    "receive shares": "setReceiveSharesGate(address)", "send shares": "setSendSharesGate(address)",
    "receive assets": "setReceiveAssetsGate(address)", "send assets": "setSendAssetsGate(address)",
}
_TIMELOCK = [{"name": "timelock", "type": "function", "stateMutability": "view", "inputs": [{"type": "bytes4"}], "outputs": [{"type": "uint256"}]}]
_ABDICATED = [{"name": "abdicated", "type": "function", "stateMutability": "view", "inputs": [{"type": "bytes4"}], "outputs": [{"type": "bool"}]}]


def timelock_and_gates(w3, vault, call=call_raw):
    """(min delay in seconds over every fund-redirecting function and exit gate still callable, or None when any needed
    read failed; notes). `call` is the caller's own call_raw (so a scorer's tests can patch it where they patch the rest).
    A revert (call_raw returns None) makes the minimum UNREAD (None), never 0. A network failure raises RpcUnavailable,
    which propagates: the scorer's safe_score skips the whole target rather than scoring it. A minimum of float('inf')
    means everything is abdicated."""
    delays, notes, unread = [], [], []
    for sig in FUND_REDIRECTING_FUNCTION_SIGS:
        selector = Web3.keccak(text=sig)[:4]
        abdicated = call(w3, vault, _ABDICATED, "abdicated", selector)
        if abdicated is True:
            notes.append(f"{sig}: permanently abdicated (can never be called again), not counted")
            continue
        d = call(w3, vault, _TIMELOCK, "timelock", selector)
        if abdicated is None or d is None:
            unread.append(sig)
        else:
            delays.append((sig, d))
    fund = list(delays)
    for gate_label, sig in EXIT_GATE_FUNCTION_SIGS.items():
        selector = Web3.keccak(text=sig)[:4]
        abdicated = call(w3, vault, _ABDICATED, "abdicated", selector)
        if abdicated is True:
            notes.append(f"{gate_label} gate: permanently abdicated (curator can never set this again)")
            continue
        d = call(w3, vault, _TIMELOCK, "timelock", selector)
        if abdicated is None or d is None:
            unread.append(sig)
            continue
        delays.append((sig, d))
        notes.append(f"{gate_label} gate: NOT abdicated, still curator-controlled behind a {d // 86400}-day timelock")
    notes.insert(0, "fund-redirecting timelocks (seconds): " + ", ".join(f"{sig}={d}" for sig, d in fund))
    if unread:
        notes.append(f"timelock()/abdicated() UNREAD for {unread}: minimum delay unread, not taken as 0")
        return None, notes
    if not delays:
        notes.append("every fund-redirecting function and exit gate is abdicated: nothing left to redirect funds")
        return float("inf"), notes
    return min(d for _, d in delays), notes


def timelock_band(min_delay):
    """Ethereum L1 V2 bands (same as its V1 Steakhouse vaults): 7 d -> 75, 3 d -> 60, any delay -> 40, none -> 0.
    UNREAD (None) -> 0, the conservative floor, with the caller's note saying so."""
    if min_delay is None:
        return 0
    if min_delay >= 7 * 86400:
        return 75
    if min_delay >= 3 * 86400:
        return 60
    return 40 if min_delay > 0 else 0
