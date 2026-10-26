#!/usr/bin/env python3
# A lock checker used by this demo; adapted from an earlier internal version, with one message changed ("no reading ... could be made", because here the reading comes from a local chain).
"""Compares an authority.lock file (what its owner expects) with a READING (a json file of readings). Python 3 standard library only, no network.
  python3 -I authority_lock_check.py authority.lock reading.json
Exit 0: every entry of the lock matches the reading. Exit 1: at least one entry CHANGED, is NOT READ or is NOT FOUND (plain-language message). Exit 2: unreadable file or unknown format.
The lock does not show that a contract is safe: it only says whether the reading is still the one its owner wrote down."""
import json, sys
FIELDS = {"state": "state", "kind": "kind of authority", "threshold": "number of signers needed", "owners": "number of signers", "delay_hours": "notice period (hours)", "self_delay_hours": "delay set in the contract itself (hours)"}
def load(p):
    try: return json.load(open(p, encoding="utf-8"))
    except (OSError, ValueError) as e: print("ERROR: cannot read %s (%s)" % (p, e.__class__.__name__)); sys.exit(2)
def main(lock_path, reading_path):
    lock, rd = load(lock_path), load(reading_path)
    if not str(lock.get("format", "")).startswith("authority.lock/0.1") or not isinstance(lock.get("entries"), list): print("ERROR: %s is not an authority.lock/0.1 file" % lock_path); sys.exit(2)
    if not isinstance(rd.get("readings"), list): print("ERROR: %s has no list of readings" % reading_path); sys.exit(2)
    by = {(r["chain"], r["address"].lower()): r for r in rd["readings"]}; bad = 0
    for e in lock["entries"]:
        name = "%s (%s, %s...)" % (e["label"], e["chain"], e["address"][:10]); r = by.get((e["chain"], e["address"].lower()))
        if r is None: bad += 1; print("RED   NOT FOUND  %s: this contract is not in the reading. The lock cannot confirm anything about it." % name); continue
        if r["state"] != "read" and e["expect"].get("state") == "read": bad += 1; print("RED   NOT READ   %s: no reading of who can change this contract could be made. That is no information about its safety, and it is not a pass." % name); continue
        diffs = [(FIELDS[k], v, r.get(k)) for k, v in e["expect"].items() if k in FIELDS and r.get(k) != v]
        if diffs: bad += 1; print("RED   CHANGED    %s: " % name + "; ".join("%s was %s when the lock was written, now %s" % (f, "not set" if a is None else a, "not set" if b is None else b) for f, a, b in diffs) + ". Read why before you sign.")
        else: print("GREEN MATCHES    %s: the reading is the one the lock expects." % name)
    print("\n%s: %d of %d entries do not match. A green line does not say the contract is safe." % ("RED" if bad else "GREEN", bad, len(lock["entries"])) if bad else "\nGREEN: all %d entries match the reading. This does not say any contract is safe." % len(lock["entries"]))
    return 1 if bad else 0
if __name__ == "__main__":
    if len(sys.argv) != 3: print(__doc__); sys.exit(2)
    sys.exit(main(sys.argv[1], sys.argv[2]))
