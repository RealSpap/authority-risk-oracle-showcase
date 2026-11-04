#!/usr/bin/env python3
"""Refuse to act on a contract unless its Authority Facts label says it is not stale, is strong enough and has a delay that was read. Standard library only; works on the label of ANY v0.1 implementation."""
import json, math, sys, urllib.request

def gate(label, min_composite=60, min_react_hours=24, require_keys=False):
    """Return (ok, reason). Unknown is refused: `stale` must be the boolean false, the composite a whole number from 0 to 100, the delay a finite number (null = not read). A key count that was not read is accepted unless require_keys: it is null when the holder is a timelock, and the label says so in not_assessed. The flag `stale` is the one the label was built with: how old the label itself is, is not checked here (see authority_facts_gate_strict.py --max-age-hours)."""
    if not isinstance(label, dict) or label.get("stale") is not False: return False, "stale: the score is out of date, or the label does not say (stale must be false)"
    c, rh = label.get("composite"), label.get("react_hours")
    if not isinstance(c, int) or isinstance(c, bool) or not 0 <= c <= 100: return False, "composite not read: a whole number from 0 to 100 is expected"
    if c < min_composite: return False, "composite %d is under %d" % (c, min_composite)
    if rh is None or isinstance(rh, bool) or not isinstance(rh, (int, float)) or not math.isfinite(rh): return False, "delay not read: unknown is not zero, and not safe"
    if rh < min_react_hours: return False, "only %d h to react, under %d" % (rh, min_react_hours)
    if require_keys and label.get("keys_to_move") is None: return False, "keys to move not read, and you asked for them"
    return True, "ok: %s %d (%s), %d h to react" % (label.get("chain"), c, label.get("band"), rh)

if __name__ == "__main__":   # python3 authority_facts_gate.py https://realspap.github.io/oracle/p/robinhood-0x1f7d7550b1b028f7571e69a784071f0205fd2efa.json
    ok, why = gate(json.load(urllib.request.urlopen(sys.argv[1], timeout=25)))
    print(why); sys.exit(0 if ok else 1)
