#!/usr/bin/env python3
"""Writes a small authority.lock/0.1-example file: what the owner of the lock expects for one contract. Python 3 standard library only.
  python3 -I make_lock.py --label NAME --address 0x... --threshold 3 --owners 5 --delay-hours 48 --out authority.lock"""
import json, sys
a = sys.argv[1:]; g = lambda k: a[a.index(k) + 1]
lock = {"format": "authority.lock/0.1-example", "note": "EXAMPLE for a local demo. It records what the lock's owner expects; it says nothing about whether any contract is safe.",
        "entries": [{"label": g("--label"), "chain": "anvil-local", "address": g("--address"), "expect": {"state": "read", "threshold": int(g("--threshold")), "owners": int(g("--owners")), "delay_hours": float(g("--delay-hours"))}}]}
json.dump(lock, open(g("--out"), "w"), indent=2)
