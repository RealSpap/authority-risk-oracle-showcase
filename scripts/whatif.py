#!/usr/bin/env python3
"""What would a change do to a contract's score? From the files of the repository alone: no site, no network.

    python3 scripts/whatif.py base 0xbbbbbbbbbb9cc5e90e3b3af64bdaf62c37eeffcb --timelock 75
    python3 scripts/whatif.py robinhood 0x1195c074f898b7644ba732407619c9804dfe6dce --admin 60 --multisig 70 --timelock 60

Sets one or more of the five sub-scores to the values given (admin, multisig, timelock drive the composite; price feed and shared control only move the requirements) and prints the composite
before and after, the band, the requirements met before and after, and the smallest single-axis change that reaches the next band. The composite is the published formula,
floor(0.4 admin + 0.3 multisig + 0.3 timelock + 0.5) (written in integers below). It is the arithmetic of the score, NOT a prediction that a given change of the setup produces that sub-score:
which on-chain change earns which sub-score is the scorer's judgement (see METHODOLOGY.md). When the published composite is not what the formula gives for the sub-scores (a cap or a minimum
over several oracles is applied on top, as on some Solana programs), the tool says so and prints only the change, never an "after" it cannot stand behind. Exit code 2: the contract is not tracked
or a value is not an integer from 0 to 100.
"""
import argparse, glob, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from dossier import chain_key, load, utf8_stdout  # noqa: E402
from evaluate_rules import WATCH_SLUGS, LABEL, norm  # noqa: E402
from badges_req import requirements  # noqa: E402

AXES = (("timelock", "timelockScore", 3), ("multisig", "multisigScore", 3), ("admin key", "adminKeyScore", 4))   # (name, field, weight in tenths)
FIELDS = {"admin": "adminKeyScore", "multisig": "multisigScore", "timelock": "timelockScore", "price-feed": "oracleAuthorityScore", "shared": "crossExposureScore"}
BANDS = ("0-19", "20-39", "40-59", "60-79", "80-100")


def composite(s): return (4 * s["adminKeyScore"] + 3 * s["multisigScore"] + 3 * s["timelockScore"] + 5) // 10


def band(c): return BANDS[min(c // 20, 4)]


def cheapest_fix(s, c):
    """(next band floor, {axis: (points needed, from, to)}) by integer arithmetic, or None when the composite is already in the top band."""
    nxt = (c // 20) * 20 + 20
    if nxt > 100: return None
    e = 4 * s["adminKeyScore"] + 3 * s["multisigScore"] + 3 * s["timelockScore"]; out = {}
    for axis, k, w10 in AXES:
        need = -(-(10 * nxt - 5 - e) // w10)
        if need > 0 and s[k] + need <= 100: out[axis] = (need, s[k], s[k] + need)
    return nxt, out


def locate(W, chain, address):
    key = chain_key(chain); addr = norm(address)
    if not key: return None
    for f in sorted(glob.glob(os.path.join(W, "scores", "*.json"))):
        d = load(f) or {}
        if WATCH_SLUGS.get(os.path.basename(f)[:-5]) == key or (key == "solana" and d.get("kind") == "solana"):
            for t in d.get("targets", []):
                if norm(t.get("target")) == addr: return key, t
    return None


def scenario(target, changes):
    """The facts of a what-if as a dict (no printing): before/after sub-scores, composites, bands, requirements, and whether the formula reproduces the published composite."""
    before = {k: target.get(k) for k in FIELDS.values()}
    if any(v is None for v in before.values()): return {"error": "the sub-scores of this contract are not all in its record"}
    after = dict(before, **{FIELDS[n]: v for n, v in changes.items()}); pub = target.get("compositeScore"); model_ok = composite(before) == pub
    r0 = requirements(before); r1 = requirements(after)
    return {"before": before, "after": after, "published": pub, "model_matches": model_ok, "composite_before": composite(before), "composite_after": composite(after), "band_before": band(pub if pub is not None else composite(before)),
            "band_after": band(composite(after)) if model_ok else None, "met_before": sum(1 for x in r0 if x[1]), "met_after": sum(1 for x in r1 if x[1]),
            "newly_met": [a[0] for a, b in zip(r0, r1) if not a[1] and b[1]], "newly_failed": [a[0] for a, b in zip(r0, r1) if a[1] and not b[1]], "fix": cheapest_fix(before, pub) if model_ok else None}


def render(title, sc, changes):
    if "error" in sc: return [sc["error"]]
    out = ["What if, for %s" % title, "", "Change: " + ", ".join("%s %s -> %s" % (n, sc["before"][FIELDS[n]], v) for n, v in changes.items())]
    if not changes: out[-1] = "Change: none given (add --admin, --multisig, --timelock, --price-feed or --shared)"
    if sc["model_matches"]:
        out += ["Composite: %d -> %d (band %s -> %s)" % (sc["published"], sc["composite_after"], sc["band_before"], sc["band_after"])]
    else:
        out += ["Composite: published %s, but the formula gives %d for the unchanged sub-scores: a cap or a minimum over several oracles is applied on top, so no 'after' is stated here (the formula alone would move by %+d)." % (sc["published"], sc["composite_before"], sc["composite_after"] - sc["composite_before"])]
    out += ["Requirements met: %d of 6 -> %d of 6" % (sc["met_before"], sc["met_after"])]
    out += ["  now met: " + "; ".join(sc["newly_met"])] if sc["newly_met"] else []
    out += ["  no longer met: " + "; ".join(sc["newly_failed"])] if sc["newly_failed"] else []
    if sc["fix"]:
        nxt, moves = sc["fix"]; out += ["", "Smallest single-axis change to reach band %d+: " % nxt + ("; ".join("%s +%d (%d -> %d)" % (a, n, f, t) for a, (n, f, t) in sorted(moves.items(), key=lambda kv: kv[1][0])) or "none within 100")]
    out += ["", "This is the arithmetic of the published formula, not a prediction that a change of the setup earns that sub-score, and not advice."]
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0]); ap.add_argument("chain"); ap.add_argument("address"); ap.add_argument("--watch", default="watch")
    for n in FIELDS: ap.add_argument("--" + n, type=int, metavar="0-100")
    a = ap.parse_args(); utf8_stdout(); found = locate(a.watch, a.chain, a.address)
    if not found: print("not tracked: %s %s" % (a.chain, a.address)); sys.exit(2)
    key, t = found; changes = {n: getattr(a, n.replace("-", "_")) for n in FIELDS if getattr(a, n.replace("-", "_")) is not None}
    bad = {n: v for n, v in changes.items() if not 0 <= v <= 100}
    if bad: print("a sub-score is an integer from 0 to 100: %s" % ", ".join("%s=%s" % kv for kv in bad.items())); sys.exit(2)
    print("\n".join(render("%s on %s" % (norm(a.address)[:6] + "…" + norm(a.address)[-4:], LABEL.get(key, key)), scenario(t, changes), changes)))


if __name__ == "__main__":
    main()
