#!/usr/bin/env python3
"""The same gate as authority_facts_gate.py with its lines as options, and a strict mode (30/10/2026). Standard library only; works on the label of ANY v0.1 implementation.

    python3 integrations/authority_facts_gate_strict.py LABEL.json_or_https_address                   # the defaults of authority_facts_gate.py: composite 60, 24 hours, keys not required
    python3 integrations/authority_facts_gate_strict.py LABEL --min-composite 80 --min-react-hours 72   # your own lines
    python3 integrations/authority_facts_gate_strict.py LABEL --strict                                  # --require-keys, and a label that lists anything it did not read (`not_assessed`) is refused

authority_facts_gate.py is unchanged: its defaults are an example chosen for the demonstration, not a policy, and this file does not change them; it only lets you choose. The decision itself is the
`gate` function of that file, called with your lines. Exit 0 = the label passes, 1 = it is refused. A refusal is a message, never a score; the label is trusted as given (no signature is checked).
"""
import argparse, json, os, sys, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from authority_facts_gate import gate  # noqa: E402


def strict_gate(label, min_composite=60, min_react_hours=24, require_keys=False, strict=False):
    """(ok, reason): gate() with your lines. strict = require_keys, and a non-empty `not_assessed` (what the label says it did not read) is refused."""
    ok, why = gate(label, min_composite, min_react_hours, require_keys or strict)
    na = label.get("not_assessed")
    if ok and strict and na: return False, "strict: the label lists what it did not read (%s)" % "; ".join(str(x) for x in (na[:3] if isinstance(na, list) else [na]))
    return ok, why


def main(argv=None):
    ap = argparse.ArgumentParser(description="Gate on one Authority Facts label, with your own lines.")
    ap.add_argument("label", help="address (https://...) or path of the JSON twin of one label")
    ap.add_argument("--min-composite", type=int, default=60); ap.add_argument("--min-react-hours", type=int, default=24)
    ap.add_argument("--require-keys", action="store_true", help="refuse a label whose number of keys was not read"); ap.add_argument("--strict", action="store_true", help="--require-keys, and refuse a label that lists anything it did not read")
    a = ap.parse_args(argv)
    if os.path.isfile(a.label):
        with open(a.label, encoding="utf-8") as f: label = json.load(f)
    else: label = json.load(urllib.request.urlopen(a.label, timeout=25))
    ok, why = strict_gate(label, a.min_composite, a.min_react_hours, a.require_keys, a.strict)
    print(why); return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
