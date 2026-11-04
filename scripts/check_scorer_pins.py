#!/usr/bin/env python3
"""Do the configurations that some scorers read and then publish constants for still match what the scorer's documentation says? (read-only)

The balayage of the scorers (2026-10-30, class 1) found targets whose scorer reads owners, thresholds or delays into its notes but sets the three
admin sub-scores to constants (Ramses CL V2, the Longbow vaults, the Spark executor): if the configuration changes, the notes change and the score does
not. This script reads each of those configurations live (data/scorer_pins.json) and compares it to the value the scorer's docstring gives. It never
changes a score and the scorers are not touched (they are covered by the methodology hash; this file is not).

    python3 scripts/check_scorer_pins.py            # compare; exit 1 on a difference or a read that could not be made
    python3 scripts/check_scorer_pins.py --update   # write what was read as the new expected values, after a person has looked; refused while anything is unread

A read that failed is UNREAD, never "unchanged". A transport failure is not a revert: a call that reverts is an answer ("not a Safe"), a call that gets no
answer is not. No key, nothing sent. Called by scripts/daily_digest.py.
"""
import argparse
import json
import os
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from lib.reader_audit import evaluate_pin  # noqa: E402

PINS = os.path.join(HERE, "..", "data", "scorer_pins.json")


def selector(sig):
    from web3 import Web3
    return "0x" + Web3.keccak(text=sig)[:4].hex()


def _rpc(url, method, params, tries=3):
    """The JSON-RPC result, "" when the node answers with an execution error (a revert), None when no answer could be had."""
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    for i in range(tries):
        try:
            req = urllib.request.Request(url, data=body, headers={"content-type": "application/json", "user-agent": "check_scorer_pins/1"})
            out = json.loads(urllib.request.urlopen(req, timeout=30).read().decode())
            if isinstance(out, dict) and "result" in out:
                return out["result"]
            if isinstance(out, dict) and isinstance(out.get("error"), dict) and "revert" in str(out["error"].get("message", "")).lower():
                return ""
        except Exception:  # noqa: BLE001 -- retried, then reported as unread
            pass
        time.sleep(2 * (i + 1))
    return None


def caller(url):
    return (lambda to, data: _rpc(url, "eth_call", [{"to": to, "data": data}, "latest"]),
            lambda to: _rpc(url, "eth_getCode", [to, "latest"]))


def expand(pin):
    """The concrete reads of a pin: its `reads`, plus its `reads_per_target` once per target (the name carries the short target)."""
    out = list(pin.get("reads", []))
    for t in pin.get("targets", []):
        for r in pin.get("reads_per_target", []):
            nm = r["name"] + "@" + t[:8]; spec = dict(r, name=nm, to=t if r["to"] == "$target" else r["to"])
            if nm in (pin.get("observed") or {}): spec["expect"] = pin["observed"][nm]   # after --update: the value a person accepted
            out.append(spec)
    return out


def _address(word):
    if not isinstance(word, str) or len(word) != 66:
        return None
    a = int(word, 16)
    return "0x%040x" % a if a else None


def observe(spec, call, code, sel=selector):
    """The value of one read: an int, a bool, or None when it could not be read. `call(to, data)` / `code(to)` answer as `_rpc` does."""
    to = spec["to"]
    if spec.get("via"):
        to = _address(call(to, sel(spec["via"])))
        if to is None:
            return None
    kind = spec["kind"]
    if kind == "owners_equal":   # the SAME set of owners behind two getters (owner() and curator()): two Safes with three owners each are not the same Safe signers unless the sets are equal
        sets = []
        for via in spec["vias"]:
            s = _address(call(spec["to"], sel(via)))
            w = call(s, sel(spec["call"])) if s else None
            if not isinstance(w, str) or len(w) < 2 + 128:
                return None
            n = int(w[2 + 64:2 + 128], 16)
            if len(w) < 2 + 128 + 64 * n:
                return None
            sets.append(sorted("0x" + w[2 + 128 + 64 * k + 24: 2 + 128 + 64 * (k + 1)] for k in range(n)))
        return sets[0] == sets[1]
    if kind == "code_len":
        c = code(to)
        return (len(c) - 2) // 2 if isinstance(c, str) and c.startswith("0x") else None
    w = call(to, sel(spec["call"])) if kind != "is_safe" else call(to, sel("getThreshold()"))
    if kind == "is_safe":
        if w is None:
            return None
        return bool(w not in ("", "0x") and len(w) >= 66 and int(w, 16) > 0)
    if not isinstance(w, str) or w in ("", "0x"):
        return None
    try:
        if kind == "uint":
            return int(w, 16) if len(w) >= 66 else None
        if kind == "owners_len":
            if len(w) < 2 + 128:
                return None
            n = int(w[2 + 64:2 + 128], 16)
            return n if len(w) >= 2 + 128 + 64 * n else None
    except ValueError:
        return None
    return None


def run(doc, make_caller=caller, sel=selector):
    """[(pin result, concrete reads)] for every pin of the document."""
    out = []
    for pin in doc["pins"]:
        url = doc["rpc"][pin["chain"]]
        call, code = make_caller(url)
        reads = expand(pin)
        observed = {r["name"]: observe(r, call, code, sel) for r in reads}
        out.append((evaluate_pin(dict(pin, reads=reads), observed), reads, observed))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0]); ap.add_argument("--update", action="store_true"); ap.add_argument("--pins", default=PINS)
    a = ap.parse_args(argv)
    doc = json.load(open(a.pins))
    results = run(doc)
    bad = 0
    for res, reads, observed in results:
        tag = {"ok": "OK", "changed": "CHANGED", "unread": "UNREAD"}[res["status"]]
        print(f"[{tag}] {res['id']}: {len(reads)} read(s)")
        for d in res["differences"]:
            print(f"   {d['read']}: expected {d['expected']}, read {d['observed']} ({d.get('source')})")
        for u in res["unread"]:
            print(f"   {u}: not read")
        bad += res["status"] != "ok"
    if a.update:
        if any(r["status"] == "unread" for r, _, _ in results):
            print("refused: something is unread; nothing written"); return 1
        for pin, (res, reads, observed) in zip(doc["pins"], results):
            for spec in pin.get("reads", []):
                spec.setdefault("expect_documented", spec["expect"]); spec["expect"] = observed[spec["name"]]
            for spec in pin.get("reads_per_target", []):
                spec.setdefault("expect_documented", spec["expect"])
            pin["observed"] = {k: v for k, v in observed.items() if "@" in k}
        blocks = {}
        for ch, url in doc["rpc"].items():
            b = _rpc(url, "eth_blockNumber", [])
            if not (isinstance(b, str) and b.startswith("0x")):
                print(f"refused: the head block of {ch} was not read; nothing written"); return 1
            blocks[ch] = int(b, 16)
        doc["snapshot_blocks"] = blocks
        doc["snapshot_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        tmp = a.pins + ".tmp"; json.dump(doc, open(tmp, "w"), indent=1); os.replace(tmp, a.pins); print("snapshot written"); return 0
    print(f"{len(results)} pin(s), {bad} not ok")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
