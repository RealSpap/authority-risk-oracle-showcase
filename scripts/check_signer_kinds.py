#!/usr/bin/env python3
"""Has any root signer of a tracked group turned from a plain EOA into an account with code (EIP-7702), or changed delegate? (read-only)

Resolves every registry group's root signers live (the same resolution as who_controls.py), reads each signer's code on its own chain, and diffs the kind
(EOA / EIP-7702 delegated / contract) and the delegate against data/signer_kinds_snapshot.json. A signer whose code could not be read is UNREAD, never "still an EOA".

    python3 scripts/check_signer_kinds.py            # compare; exit 1 on a HIGH change, a signer that left every group, or an unread signer or group
    python3 scripts/check_signer_kinds.py --update   # write the current state as the new snapshot after reviewing; refused while anything is unread

Why it exists: see scripts/lib/signer_kinds.py. Takes a few minutes (it resolves every group). No key, nothing sent.
"""
import argparse
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "lib"))
from check_cross_ecosystem_overlap import resolve_all  # noqa: E402
from lib.signer_kinds import diff, key, snapshot  # noqa: E402
from who_controls import code_scan  # noqa: E402

SNAPSHOT = os.path.join(HERE, "..", "data", "signer_kinds_snapshot.json")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--update", action="store_true")
    args = ap.parse_args()
    groups, _, _, incomplete, w3s = resolve_all()
    classified = code_scan(groups, w3s)
    unread = {k: v for k, v in classified.items() if v[0] == "unread"}
    now = snapshot(classified)
    old_doc = json.load(open(SNAPSHOT)) if os.path.exists(SNAPSHOT) else {}
    old = old_doc.get("signers", {})
    unread_keys = {key(eco, addr) for eco, addr in unread}
    d = diff(old, now, unread_keys) if old else {"changed": [], "new": sorted(now), "gone": []}
    for sev, k, text in d["changed"]:
        print(f"  [{'CHANGED' if sev == 'HIGH' else 'INFO'}] {k}: {text}")
    if incomplete:  # the signers of an unresolved group are missing from this run: a count, not one alarm per owner
        if d["gone"]:
            print(f"  [GONE?] {len(d['gone'])} signer(s) missing from this run, unconfirmed: {len({(e, k) for e, k, _, _ in incomplete})} group(s) could not be resolved")
    else:
        for k in d["gone"]:
            print(f"  [GONE] {k}: no longer a root signer of any tracked group (a signer removed, or a Safe whose owners could no longer be resolved): review, then --update")
    for (eco, addr), v in sorted(unread.items()):
        print(f"  [UNREAD] {eco}:{addr}: {v[1]}")
    if incomplete:
        print(f"  [UNREAD] {len({(e, k) for e, k, _, _ in incomplete})} group(s) whose signer set could not be fully resolved: their signers are absent from this check")
    counts = {}
    for v in now.values():
        counts[v["kind"]] = counts.get(v["kind"], 0) + 1
    high = sum(1 for s, _, _ in d["changed"] if s == "HIGH")
    print(f"{len(classified)} (chain, signer) pairs, {len(classified) - len(unread)} read, {len(unread)} unread, {counts}, {high} changed, {len(d['new'])} new, {len(d['gone'])} gone"
          + (f", snapshot of {old_doc.get('read')}" if old else ", no snapshot yet"))
    if args.update and (unread or incomplete):
        print("snapshot NOT written: it would silently drop the unread signers and unresolved groups; rerun when everything can be read")
        sys.exit(1)
    if args.update:
        with open(SNAPSHOT, "w") as f:
            json.dump({"read": time.strftime("%Y-%m-%dT%H:%MZ", time.gmtime()), "signers": now}, f, indent=1, sort_keys=True)
        print(f"snapshot written: {len(now)} signers")
    sys.exit(1 if high or d['gone'] or unread or incomplete else 0)


if __name__ == "__main__":
    main()
