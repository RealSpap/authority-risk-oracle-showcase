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

--strict (30/10/2026, off by default: without it nothing above changes) also reads the label against watch/schema/label.strict.schema.json, the plain schema plus the bounds it does not state
(composite 0..100, keys at least 1, delay at least 0, money above 0, a 32-byte hash, six requirements, the five sub-scores each 0..100), and reports a difference from the published formula as a failure.
"""
import http.client, json, math, os, re, sys, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from validate_schemas import check  # noqa: E402

SCHEMA = os.path.join(HERE, "..", "watch", "schema", "label.schema.json")
STRICT_SCHEMA = os.path.join(HERE, "..", "watch", "schema", "label.strict.schema.json")
BANDS = (("critical", 0, 19), ("weak", 20, 39), ("moderate", 40, 59), ("decent", 60, 79), ("strong", 80, 100))


def check_bounds(d, s, path, errs):
    """The bounds of the strict schema that validate_schemas.check does not know (minimum, maximum, exclusiveMinimum, minLength, pattern, minItems, maxItems), over the shape `check` already accepted."""
    if isinstance(d, bool): return
    if isinstance(d, float) and not math.isfinite(d): errs.append("%s: %s is not a finite number" % (path, d)); return
    if isinstance(d, (int, float)):
        if "minimum" in s and d < s["minimum"]: errs.append("%s: %s is under the minimum %s" % (path, d, s["minimum"]))
        if "maximum" in s and d > s["maximum"]: errs.append("%s: %s is over the maximum %s" % (path, d, s["maximum"]))
        if "exclusiveMinimum" in s and d <= s["exclusiveMinimum"]: errs.append("%s: %s is not above %s" % (path, d, s["exclusiveMinimum"]))
    if isinstance(d, str):
        if "minLength" in s and len(d) < s["minLength"]: errs.append("%s: shorter than %d" % (path, s["minLength"]))
        if "pattern" in s and not re.search(s["pattern"], d): errs.append("%s: does not match %s" % (path, s["pattern"]))
    if isinstance(d, list):
        if "minItems" in s and len(d) < s["minItems"]: errs.append("%s: %d item(s), at least %d expected" % (path, len(d), s["minItems"]))
        if "maxItems" in s and len(d) > s["maxItems"]: errs.append("%s: %d item(s), at most %d expected" % (path, len(d), s["maxItems"]))
        for i, x in enumerate(d):
            if isinstance(s.get("items"), dict): check_bounds(x, s["items"], "%s[%d]" % (path, i), errs)
    if isinstance(d, dict):
        for k, sub in (s.get("properties") or {}).items():
            if k in d: check_bounds(d[k], sub, path + "." + k, errs)


def judge(d, schema, strict=None):
    """(violations, differences) for one parsed twin. strict: the parsed label.strict.schema.json to read it against as well (None = the plain reading, unchanged)."""
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
    if strict is not None:
        check(d, strict, "label", errs); check_bounds(d, strict, "label", errs)
        errs += ["strict: " + x for x in diffs]; diffs = []   # a difference from the published formula is a failure in strict mode
        errs[:] = list(dict.fromkeys(errs))
    return errs, diffs


def load(src):
    if src.startswith("http"):                                     # a truncated answer raises http.client errors, which are neither OSError nor ValueError
        with urllib.request.urlopen(urllib.request.Request(src, headers={"User-Agent": "authority-facts-conformance/1"}), timeout=25) as r: return json.loads(r.read().decode("utf-8"))
    with open(src, encoding="utf-8") as f: return json.load(f)


def main(argv=None, out=print):
    argv = list(sys.argv[1:] if argv is None else argv); schema = json.load(open(SCHEMA, encoding="utf-8"))
    strict = None
    if "--strict" in argv: argv.remove("--strict"); strict = json.load(open(STRICT_SCHEMA, encoding="utf-8"))
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
        errs, diffs = judge(d, schema, strict)
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
