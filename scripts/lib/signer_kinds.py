"""What kind of account is each root signer of a tracked group, and has that changed? Pure logic for scripts/check_signer_kinds.py (no RPC).

A Safe picks how to check an owner's signature from the signature's own `v` byte: `v` = 0 makes it call `isValidSignature` (ERC-1271) on the owner ADDRESS, anything else is ECDSA recovery.
Since EIP-7702 an EOA can give itself code by signing an authorization, and that call then reaches the delegate's code: a validation path is added beyond the owner's key, whose rules are the
delegate's. So a signer that flips from EOA to delegated (or changes delegate) changes how a threshold can be met with no Safe transaction and no event on the Safe, and nothing else in this
repository would show it (first scan 2026-09-26: 3 of 582 pairs already delegated).
"""


def key(ecosystem: str, address: str) -> str:
    return f"{ecosystem}:{address.lower()}"


def snapshot(classified: dict) -> dict:
    """{key: {"kind": ..., "delegate": ...}} from who_controls.code_scan()'s {(ecosystem, address): (kind, delegate)}; unread pairs are left out (they are reported, never stored as a kind)."""
    return {key(eco, addr): {"kind": kind, "delegate": (delegate.lower() if kind == "eip7702" else None)}
            for (eco, addr), (kind, delegate) in classified.items() if kind != "unread"}


def diff(old: dict, new: dict, unread=frozenset()) -> dict:
    """{"changed": [(severity, key, text)], "new": [key], "gone": [key]}. HIGH = a signer that was a plain EOA now has code or a delegate, its delegate changed, or a NEW signer is already delegated;
    INFO = a delegation was removed (7702 -> EOA), or a NEW signer is a contract. `unread` keys (read failed this time) are never reported as gone: an outage is not a removal."""
    changed = []
    for k in sorted(set(old) & set(new)):
        o, n = old[k], new[k]
        if o == n:
            continue
        if o["kind"] == "eip7702" and n["kind"] == "eoa":
            changed.append(("INFO", k, f"delegation removed (was {o['delegate']})"))
        elif n["kind"] == "eip7702" and o["kind"] == "eip7702":
            changed.append(("HIGH", k, f"delegate changed {o['delegate']} -> {n['delegate']}"))
        elif n["kind"] == "eip7702":
            changed.append(("HIGH", k, f"{o['kind']} -> EIP-7702 delegated to {n['delegate']}"))
        else:
            changed.append(("HIGH", k, f"{o['kind']} -> {n['kind']}"))
    added = sorted(set(new) - set(old))
    for k in added:
        if new[k]["kind"] == "eip7702":
            changed.append(("HIGH", k, f"new signer already EIP-7702 delegated to {new[k]['delegate']}"))
        elif new[k]["kind"] == "contract":
            changed.append(("INFO", k, "new signer that is a contract"))
    return {"changed": changed, "new": added, "gone": sorted(set(old) - set(new) - set(unread))}
