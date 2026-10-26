#!/usr/bin/env python3
"""Reads three numbers from a contract with eth_call and applies the written rule in rule.json. Python 3 standard library only.
  python3 -I reader.py --rpc http://127.0.0.1:18545 --target 0x... [--json reading.json]
Exit 0: ALLOWED BY THE RULE. Exit 1: REFUSED (with the reasons). Exit 2: CANNOT KNOW (a number could not be read: neither allowed nor refused, and it says what is missing).
Every answer prints the block it read and the exact calls, so anyone can read the same numbers again. This is a short independent reader: it is not the oracle's scorer, it does not run on a schedule and it blocks nothing by itself."""
import json, os, sys, urllib.request
H = os.path.dirname(os.path.abspath(__file__)); rule = json.load(open(os.path.join(H, "rule.json")))
SEL = {"threshold": ("0x42cde4e8", "threshold()"), "ownerCount": ("0x0db02622", "ownerCount()"), "minDelay": ("0xc63c4e9b", "minDelay()")}   # cast sig "threshold()" etc.
a = sys.argv[1:]; rpc = a[a.index("--rpc") + 1]; target = a[a.index("--target") + 1]; jout = a[a.index("--json") + 1] if "--json" in a else None
CHAIN = "anvil-local"


def call(method, params):
    q = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    r = json.load(urllib.request.urlopen(urllib.request.Request(rpc, q, {"content-type": "application/json"}), timeout=15))
    if "error" in r: raise RuntimeError(r["error"].get("message", "rpc error"))
    return r["result"]


try: block = int(call("eth_blockNumber", []), 16)
except Exception: block = None
vals, miss = {}, []
for k, (s, sig) in SEL.items():
    try:
        out = call("eth_call", [{"to": target, "data": s}, hex(block) if block is not None else "latest"])
        if not out or len(out) < 66: raise RuntimeError("empty answer")
        vals[k] = int(out, 16)
    except Exception as e: miss.append((sig, str(e)))
print("reader: target %s, read at block %s" % (target, block if block is not None else "NOT READ"))
print(("  to read the same numbers again: cast call %s \"threshold()(uint256)\" --block %s --rpc-url %s   (and ownerCount(), minDelay())" % (target, block, rpc)) if block is not None else "  no block read, nothing to replay")
rd = {"chain": CHAIN, "address": target}
if miss:
    rd["state"] = "not_read"
    print("CANNOT KNOW  (neither allowed nor refused: the rule cannot answer, and it says what is missing)")
    for sig, why in miss: print("  missing: %s (%s)" % (sig, why))
    print("  because R1 NOT READ: a missing reading is not a pass and not a refusal.")
    code = 2
else:
    rd.update(state="read", threshold=vals["threshold"], owners=vals["ownerCount"], delay_hours=vals["minDelay"] / 3600)
    print("  signers that must agree = %d, owners = %d, notice period = %d seconds (%.1f hours)" % (vals["threshold"], vals["ownerCount"], vals["minDelay"], vals["minDelay"] / 3600))
    why = []
    if vals["threshold"] < rule["min_threshold"] or vals["ownerCount"] < rule["min_owners"]:
        why.append("R2 SMALL MULTISIG: %d of %d is below %d of %d." % (vals["threshold"], vals["ownerCount"], rule["min_threshold"], rule["min_owners"]))
    if vals["minDelay"] < rule["min_delay_seconds"]:
        why.append("R3 NO NOTICE: %.1f hours is below %d hours." % (vals["minDelay"] / 3600, rule["min_delay_seconds"] // 3600))
    if why:
        print("REFUSED  (the rule refuses this)"); [print("  because " + w) for w in why]; code = 1
    else:
        print("ALLOWED BY THE RULE  (the rule allows this; it does not say the target is safe)"); code = 0
if jout: json.dump({"readings": [rd]}, open(jout, "w"))
sys.exit(code)
