"""Has the code behind a tracked target changed? A fingerprint per target, and a diff against the last reviewed one.

ADDED 2026-09-21. The oracle scores WHO controls a target. It says nothing about the code they control changing, and on 2026-09-21
a first archive read found three of the 13 proxies it could read (Compound V3 on Ethereum, Yuzu yzUSD and one more on Plasma) had a
different implementation than 30 days earlier. A target's score can be right about the authority and stale about the code.

This module fingerprints every tracked target (EIP-1967 proxy: its implementation; beacon proxy: the beacon's implementation;
ERC-1167 clone: its implementation; anything else: the hash of its own code) and diffs a live fingerprint against a stored one, so a
change is caught between runs without archive access, which most public RPCs do not offer. scripts/check_implementation_changes.py
wires the real chain and the stored snapshot (data/implementation_snapshot.json); the readers here are injected.
"""
import json

IMPL_SLOT = "0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc"
BEACON_SLOT = "0xa3f0ad74e5423aebfd80d3ef4346578335a9a72aeaee59ff6cb3582b35133d50"
_CLONE_PREFIX = bytes.fromhex("363d3d373d3d3d363d73")
ZERO = "0x" + "0" * 40


def _addr_from_word(word):
    """The last 20 bytes of a 32-byte storage word as a lowercase 0x address, or None if the word is empty or unreadable."""
    if word is None:
        return None
    raw = bytes(word)
    if int.from_bytes(raw, "big") == 0:
        return None
    return "0x" + raw[-20:].hex()


def fingerprint(target, get_code, get_storage, beacon_implementation, keccak):
    """Fingerprint of one target.

    get_code(addr) -> bytes or None; get_storage(addr, slot_hex) -> 32 bytes or None; beacon_implementation(beacon) -> address or None;
    keccak(bytes) -> hex string. Returns {"kind", "implementation", "implementationCodeHash", "codeHash"} where fields that do not
    apply are None, or {"kind": "unread"} if the target's own code could not be read."""
    code = get_code(target)
    if code is None:
        return {"kind": "unread"}
    if len(code) == 0:
        return {"kind": "no code", "implementation": None, "implementationCodeHash": None, "codeHash": None}
    implementation, kind = None, "plain"
    if len(code) == 45 and bytes(code[:10]) == _CLONE_PREFIX:
        implementation, kind = "0x" + bytes(code[10:30]).hex(), "erc1167 clone"
    else:
        impl = _addr_from_word(get_storage(target, IMPL_SLOT))
        if impl:
            implementation, kind = impl, "eip1967 proxy"
        else:
            beacon = _addr_from_word(get_storage(target, BEACON_SLOT))
            if beacon:
                implementation, kind = beacon_implementation(beacon), "beacon proxy"
    impl_hash = None
    if implementation:
        impl_code = get_code(implementation)
        impl_hash = keccak(impl_code) if impl_code else None
    return {"kind": kind, "implementation": implementation, "implementationCodeHash": impl_hash, "codeHash": keccak(code)}


def changed_fields(old, new):
    """The fingerprint fields that differ, as {field: (old, new)}. A target that could not be read is never reported as changed."""
    if old.get("kind") == "unread" or new.get("kind") == "unread":
        return {}
    return {f: (old.get(f), new.get(f)) for f in ("kind", "implementation", "implementationCodeHash", "codeHash") if old.get(f) != new.get(f)}


def diff(snapshot, live):
    """Compare {key: fingerprint} maps. Returns {"changed": {key: fields}, "new": [key], "removed": [key], "unread": [key]}."""
    changed, unread = {}, []
    for key, fp in live.items():
        if fp.get("kind") == "unread":
            unread.append(key)
            continue
        if key in snapshot:
            fields = changed_fields(snapshot[key], fp)
            if fields:
                changed[key] = fields
    return {
        "changed": changed,
        "new": sorted(k for k, fp in live.items() if k not in snapshot and fp.get("kind") != "unread"),
        "removed": sorted(k for k in snapshot if k not in live),
        "unread": sorted(unread),
    }


def load_snapshot(path):
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        return {"takenAt": None, "targets": {}}


def save_snapshot(path, taken_at, targets):
    with open(path, "w") as f:
        json.dump({"takenAt": taken_at, "targets": dict(sorted(targets.items()))}, f, indent=1, sort_keys=True)
        f.write("\n")
