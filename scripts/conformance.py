#!/usr/bin/env python3
"""Does a label conform to Authority Facts v0.1? A checker anyone can run on ANY implementation's JSON twins (12/10/2026).

    python3 scripts/conformance.py path/to/twin.json                 # one label
    python3 scripts/conformance.py path/to/dir_of_twins/             # every *.json in it (index.json is skipped)
    python3 scripts/conformance.py --url https://realspap.github.io/oracle/p/index.json     # follows the `addresses` list of an index

What it checks (the specification, section 2 and 5): the fields of watch/schema/label.schema.json are present with the right types; the band matches the composite;
the composite is the published formula floor((4a + 3m + 3t + 5) / 10) of the three readings; a line that was not read is null and never 0 (zero keys, or a negative delay, is a failed read written as a number);
there are exactly the six requirement checks; the methodology hash and the licence are present. A composite that differs from the formula is reported as a DIFFERENCE, not a failure: section 5 allows a
documented difference (a cap or a minimum over several oracles), so the report lists them for the implementer to declare. Standard library only.
Exit 0: every label conforms (differences allowed). Exit 1: at least one label breaks the specification. Exit 2: nothing could be read.
"""
import http.client, json, os, re, sys, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from validate_schemas import check  # noqa: E402

SCHEMA = os.path.join(HERE, "..", "watch", "schema", "label.schema.json")
BANDS = (("critical", 0, 19), ("weak", 20, 39), ("moderate", 40, 59), ("decent", 60, 79), ("strong", 80, 100))


def judge(d, schema):
    """(violations, differences) for one parsed twin."""
    errs, diffs = [], []
    check(d, schema, "label", errs)
    if errs: return errs, diffs
    c = d["composite"]
    if not 0 <= c <= 100: errs.append("composite %d is outside 0..100" % c)
    band = next((b for b, lo, hi in BANDS if lo <= c <= hi), None)
    if band and d["band"] != band: errs.append("band %r does not match composite %d (expected %r)" % (d["band"], c, band))
    s = d["sub"]; f = (4 * s["adminKeyScore"] + 3 * s["multisigScore"] + 3 * s["timelockScore"] + 5) // 10
    if f != c: diffs.append("composite %d differs from the formula result %d: declare the cap or minimum that explains it" % (c, f))
    if d["keys_to_move"] is not None and d["keys_to_move"] < 1: errs.append("keys_to_move is %d: zero keys is a failed read, write null" % d["keys_to_move"])
    if d["react_hours"] is not None and d["react_hours"] < 0: errs.append("react_hours is negative")
    if d["money_per_key_usd"] is not None and d["money_per_key_usd"] <= 0: errs.append("money_per_key_usd is %s: an unknown amount is null, not zero" % d["money_per_key_usd"])
    if d["keys_to_move"] is None and d["money_per_key_usd"] is not None: errs.append("money_per_key_usd is given although keys_to_move was not read")
    if len(d["requirements"]) != 6: errs.append("%d requirement checks, the specification has six" % len(d["requirements"]))
    if not re.fullmatch(r"0x[0-9a-fA-F]{64}", d["methodology_hash"]): errs.append("methodology_hash is not a 32-byte hex hash")
    if not d["license"].strip(): errs.append("licence is empty")
    return errs, diffs


def load(src):
    if src.startswith("http"):                                     # a truncated answer raises http.client errors, which are neither OSError nor ValueError
        with urllib.request.urlopen(urllib.request.Request(src, headers={"User-Agent": "authority-facts-conformance/1"}), timeout=25) as r: return json.loads(r.read().decode("utf-8"))
    with open(src, encoding="utf-8") as f: return json.load(f)


def main(argv=None, out=print):
    argv = list(sys.argv[1:] if argv is None else argv); schema = json.load(open(SCHEMA, encoding="utf-8"))
    if not argv: out(__doc__.split("\n\n")[0]); return 2
    docs = []                                                      # (name, parsed or None)
    try:
        if argv[0] == "--url":
            if len(argv) < 2: out("conformance: --url needs the address of an index.json"); return 2
            idx = load(argv[1]); base = argv[1].rsplit("/", 1)[0]
            # the index maps an address to the pages that score it, one per chain: {"0x..": [{"chain": .., "key": "arbitrum", ..}]}; a twin is <key>-<address>.json next to it
            if not isinstance(idx.get("addresses"), dict): out("conformance: the index has no `addresses` map: nothing to follow"); return 2
            docs = [("%s-%s" % (pg["key"], a), load("%s/%s-%s.json" % (base, pg["key"], a))) for a, pgs in idx["addresses"].items() for pg in pgs if isinstance(pg, dict) and pg.get("key")]
        elif os.path.isdir(argv[0]):
            docs = [(n, load(os.path.join(argv[0], n))) for n in sorted(os.listdir(argv[0])) if n.endswith(".json") and n != "index.json"]
        else: docs = [(os.path.basename(argv[0]), load(argv[0]))]
    except (OSError, ValueError, http.client.HTTPException) as e:
        out("conformance: could not read the input (%s)" % type(e).__name__); return 2
    if not docs: out("conformance: no label found"); return 2
    bad = diff = 0
    for name, d in docs:
        errs, diffs = judge(d, schema)
        for e in errs: out("FAIL %s: %s" % (name, e))
        for e in diffs: out("DIFFERENCE %s: %s" % (name, e))
        bad += bool(errs); diff += bool(diffs)
    out("conformance: %d label(s), %d break the specification, %d with a difference to declare" % (len(docs), bad, diff))
    return 1 if bad else 0


def selftest():
    schema = json.load(open(SCHEMA, encoding="utf-8"))
    ok = {"chain": "Base", "address": "0xabc", "composite": 55, "band": "moderate", "keys_to_move": 2, "react_hours": 0, "money_per_key_usd": 10.5,
          "sub": {"adminKeyScore": 65, "multisigScore": 95, "timelockScore": 0}, "requirements": [{"label": "r", "met": True}] * 6, "independent_read": None,
          "last_pushed": 1, "stale": False, "methodology_hash": "0x" + "ab" * 32, "block": 5, "license": "CC BY 4.0"}
    assert judge(ok, schema) == ([], [])
    def bad(**kw): return judge({**ok, **kw}, schema)[0]
    assert bad(band="strong"); assert bad(keys_to_move=0); assert bad(money_per_key_usd=0); assert bad(requirements=[]); assert bad(methodology_hash="0x12"); assert bad(license=" ")
    assert bad(keys_to_move=None); assert not bad(keys_to_move=None, money_per_key_usd=None)       # money behind a key nobody counted is an invention
    assert bad(composite="55"); assert bad(react_hours=-1)
    assert bad(composite=150, band="strong")                       # outside 0..100 is a failure, not just a difference to the formula
    e, df = judge({**ok, "composite": 60, "band": "decent"}, schema); assert not e and df                # off the formula but consistent: a difference to declare
    missing = dict(ok); del missing["keys_to_move"]; assert judge(missing, schema)[0]
    print("selftest ok")


if __name__ == "__main__":
    if "--selftest" in sys.argv: selftest(); sys.exit(0)
    sys.exit(main())
