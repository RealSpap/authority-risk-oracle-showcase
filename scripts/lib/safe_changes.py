"""
What changed on the Safes this oracle tracks, recently. Pure logic for scripts/check_safe_changes.py (no RPC).

A Safe's authority is its signer set, its threshold, its modules, its guard and its singleton. Each change emits one
event, so "what moved this month" is readable straight from the logs, before any score is recomputed. Safe v1.3.0
emits the changed address in `data`, v1.4.1 as `topics[1]`; both are decoded.
"""
from web3 import Web3

# event name -> (signature, kind of value). Signature hashes are identical whether or not the parameter is indexed.
SAFE_EVENTS = {
    "AddedOwner": ("AddedOwner(address)", "address"),
    "RemovedOwner": ("RemovedOwner(address)", "address"),
    "ChangedThreshold": ("ChangedThreshold(uint256)", "uint"),
    "EnabledModule": ("EnabledModule(address)", "address"),
    "DisabledModule": ("DisabledModule(address)", "address"),
    "ChangedGuard": ("ChangedGuard(address)", "address"),
    "ChangedMasterCopy": ("ChangedMasterCopy(address)", "address"),  # v1.1.1 singleton change
}
TOPIC_TO_NAME = {"0x" + Web3.keccak(text=sig).hex().removeprefix("0x"): name for name, (sig, _) in SAFE_EVENTS.items()}

# Higher = more worth reading first. A module or a lowered threshold can change who acts; a guard can only block.
_WEIGHT = {"EnabledModule": 5, "ChangedMasterCopy": 5, "ChangedThreshold": 4, "RemovedOwner": 3, "AddedOwner": 3,
           "ChangedGuard": 2, "DisabledModule": 1}


def _word(log, index=1):
    """32-byte value of an event: topics[1] (indexed, v1.4.1) if present, else the first data word (v1.3.0)."""
    topics = log["topics"]
    raw = topics[index] if len(topics) > index else log["data"]
    raw = raw.hex() if isinstance(raw, (bytes, bytearray)) else raw
    return raw.removeprefix("0x")[:64]


def decode_event(log):
    """{name, value, block, tx} for a Safe management event log, or None for any other topic. `value` is a checksum
    address for owner/module/guard/singleton events and an int for a threshold."""
    topic0 = log["topics"][0]
    topic0 = topic0.hex() if isinstance(topic0, (bytes, bytearray)) else topic0
    name = TOPIC_TO_NAME.get("0x" + topic0.removeprefix("0x"))
    if not name:
        return None
    word = _word(log)
    value = int(word, 16) if SAFE_EVENTS[name][1] == "uint" else Web3.to_checksum_address("0x" + word[-40:])
    block = log["blockNumber"]
    tx = log["transactionHash"]
    return {"name": name, "value": value, "block": int(block, 16) if isinstance(block, str) else int(block),
            "tx": tx.hex() if isinstance(tx, (bytes, bytearray)) else tx}


def rank(events):
    """Most structural first, then most recent."""
    return sorted(events, key=lambda e: (-_WEIGHT.get(e["name"], 0), -e["block"]))


def summarize_by_safe(events_by_safe: dict) -> dict:
    """{safe: {"count": n, "names": sorted distinct event names}} for Safes with at least one event."""
    return {s: {"count": len(ev), "names": sorted({e["name"] for e in ev})} for s, ev in events_by_safe.items() if ev}
