#!/usr/bin/env python3
"""Refuse to act on a contract unless its Authority Facts label is fresh, strong enough and has a delay that was read. Standard library only; works on the label of ANY v0.1 implementation."""
import json, sys, urllib.request

def gate(label, min_composite=60, min_react_hours=24, require_keys=False):
    """Return (ok, reason). A delay that was not read (null) is refused. A key count that was not read is accepted unless require_keys: it is null when the holder is a timelock, and the label says so in not_assessed."""
    if label["stale"]: return False, "stale: the score is out of date"
    if label["composite"] < min_composite: return False, "composite %d is under %d" % (label["composite"], min_composite)
    if label["react_hours"] is None: return False, "delay not read: unknown is not zero, and not safe"
    if label["react_hours"] < min_react_hours: return False, "only %d h to react, under %d" % (label["react_hours"], min_react_hours)
    if require_keys and label["keys_to_move"] is None: return False, "keys to move not read, and you asked for them"
    return True, "ok: %s %d (%s), %d h to react" % (label["chain"], label["composite"], label["band"], label["react_hours"])

if __name__ == "__main__":   # python3 authority_facts_gate.py https://realspap.github.io/oracle/p/robinhood-0x1f7d7550b1b028f7571e69a784071f0205fd2efa.json
    ok, why = gate(json.load(urllib.request.urlopen(sys.argv[1], timeout=25)))
    print(why); sys.exit(0 if ok else 1)
