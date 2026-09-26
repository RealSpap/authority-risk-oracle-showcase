"""
What changed on the Squads v4 multisigs the Solana scorers rely on? Pure diff logic for scripts/check_squads_changes.py (no RPC).

A Squads v4 multisig's authority is its member set (with permission masks), its threshold, its time lock and its config authority. Unlike an
EVM Safe there is no cheap per-address event feed, so this compares the CURRENT state with a saved snapshot (the same pattern as
scripts/lib/implementation_watch.py). First seen 2026-09-26: Jupiter Lend's program-upgrade multisig removed a member 82 minutes after a
re-push, which moved its published multisigScore from 83 to 87.
"""

import re

MS_CONSTANT = re.compile(r'\b([A-Z][A-Z0-9_]*MS)\s*=\s*"([1-9A-HJ-NP-Za-km-z]{32,44})"')


def multisig_constants(source: str) -> dict:
    """{address: [constant names]} for every `*_MS = "<base58>"` constant in a scorer's source text."""
    out = {}
    for name, addr in MS_CONSTANT.findall(source):
        out.setdefault(addr, []).append(name)
    return out


def shape(squads: dict) -> dict:
    """The comparable part of a sol_read.read_squads() result."""
    return {"threshold": squads["threshold"], "time_lock_s": squads["time_lock_s"], "config_authority": squads["config_authority"],
            "members": {m["key"]: m["mask"] for m in squads["member_list"]}}


def diff(old: dict, new: dict) -> list:
    """Human-readable changes between two `shape()` dicts; empty when identical."""
    out = []
    added = sorted(set(new["members"]) - set(old["members"]))
    removed = sorted(set(old["members"]) - set(new["members"]))
    out += [f"member added {k} (permissions {new['members'][k]})" for k in added]
    out += [f"member removed {k}" for k in removed]
    out += [f"member {k} permissions {old['members'][k]} -> {new['members'][k]}" for k in sorted(set(old["members"]) & set(new["members"])) if old["members"][k] != new["members"][k]]
    for field, label in (("threshold", "threshold"), ("time_lock_s", "time lock (s)"), ("config_authority", "config authority")):
        if old[field] != new[field]:
            out.append(f"{label} {old[field]} -> {new[field]}")
    return out
