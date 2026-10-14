#!/usr/bin/env python3
"""A thirty-second tour of what the watch knows, from the repository alone: no site, no network, no key. The first command to run after cloning.

    python3 scripts/tour.py
    python3 scripts/tour.py --watch watch --top 5

It prints: how many contracts on how many chains and protocols, the protocols whose WEAKEST tracked deployment scores under 40 with the most money attached (the dashboard's rule), how many
contracts are behind a plain key and how many of them carry more than $100M, how much of the picture is unread (said first, not last), whether the published files agree with each other, and
four commands with real arguments taken from this data, to go further (a dossier, a comparison, a brief, a question). Every figure comes from the files under watch/; a value the watch did not
read is counted as unread, never as zero. It is a reading of who can act and how fast on the contracts the watch tracks, not an audit and not investment advice.
"""
import argparse, os, sys
from watch_location import NO_STATE_HINT  # the state is on the watch-data branch

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from dossier import load, utf8_stdout, clean_lines  # noqa: E402
from evaluate_rules import LABEL  # noqa: E402
from find import table  # noqa: E402
from brief import protocols, money, usd, short  # noqa: E402
import consistency  # noqa: E402

BIG = 1e8   # "carries more than": the line the page draws for a plain key behind a lot of money


def weakest_with_money(W, rows, top=5, below=40):
    """[(protocol dict, weakest score, money, contracts)] for protocols whose weakest deployment scores under `below`, most money first (a protocol with no figure goes last, said so by None)."""
    out = []
    for slug, p in protocols(rows).items():
        scored = [r for r in p["rows"] if r.get("score") is not None]
        if not scored: continue
        w = min(r["score"] for r in scored)
        if w < below: out.append((slug, p["name"], w, money(W, p["rows"]), len(p["rows"])))
    out.sort(key=lambda x: (x[3] is None, -(x[3] or 0), x[2], x[0])); return out[:top]


def build(W, top=5):
    """(lines, error)."""
    rows = table(W)
    if not rows: return None, "no tracked contract in %s/scores" % W + NO_STATE_HINT
    ps = protocols(rows); chains = sorted({r["chain"] for r in rows}); run = (load(os.path.join(W, "latest.json")) or {}).get("run_utc")
    out = ["What the watch knows (run of %s)" % (run or "an unknown run"), "", "%d tracked contracts on %d chains, %d of them attached to %d protocols (DefiLlama)." % (len(rows), len(chains), sum(len(p["rows"]) for p in ps.values()), len(ps)), ""]
    unread_admin = sum(1 for r in rows if r.get("kind") in (None, "unreadable", "native")); unread_keys = sum(1 for r in rows if r.get("keys_to_move") is None); unread_pause = sum(1 for r in rows if r.get("paused") is None)
    out += ["Unread first (a value not read is never counted as zero):", "  admin not read on %d of %d, keys to move the money not read on %d of %d, pause state not read on %d of %d." % (unread_admin, len(rows), unread_keys, len(rows), unread_pause, len(rows)), ""]
    wm = weakest_with_money(W, rows, top)
    out += ["Protocols whose weakest deployment scores under 40, most money attached first:"]
    out += ["  %-28s weakest %3d/100   %9s   %d contract%s" % (name[:28], w, usd(m), n, "" if n == 1 else "s") for _slug, name, w, m, n in wm] or ["  none"]
    plain = [r for r in rows if r.get("kind") == "eoa"]; big = [r for r in plain if (r.get("money_usd") or 0) >= BIG]
    out += ["", "A plain key as admin: %d contract%s read as one; %d of them with $100M or more attached%s." % (len(plain), "" if len(plain) == 1 else "s", len(big), (": " + ", ".join("%s on %s" % (r["title"], LABEL.get(r["chain"], r["chain"])) for r in sorted(big, key=lambda r: -r["money_usd"])[:3])) if big else "")]
    f, skipped, ran = consistency.check(W)
    out += ["", "The files agree with each other: " + ("yes (%d checks)" % ran if not f else "NO, %d disagreement(s), first: %s: %s" % (len(f), f[0]["file"], f[0]["what"])) + (" ; not checked (file missing): " + ", ".join(skipped) if skipped else "")]
    first = rows and sorted(rows, key=lambda r: (r.get("score") is None, r.get("score") or 0, -(r.get("money_usd") or 0)))[0]
    cmds = []
    if first: cmds.append(("one contract, in words", "python3 scripts/dossier.py %s %s" % (first["chain"], first["target"])))
    big_ps = [x[0] for x in sorted(((s, money(W, p["rows"])) for s, p in ps.items()), key=lambda x: -(x[1] or 0))[:2]]
    if len(big_ps) == 2: cmds.append(("two protocols side by side", "python3 scripts/compare.py %s %s" % tuple(big_ps)))
    if big_ps: cmds.append(("a protocol on every chain", "python3 scripts/brief.py %s" % big_ps[0]))
    cmds.append(("a question over all contracts", "python3 scripts/find.py --kind eoa --min-money 1e8"))
    out += ["", "Go further:"] + ["  %-32s %s" % (what + ":", cmd) for what, cmd in cmds]
    out += ["", "This is a reading of who can act and how fast on the tracked contracts, from public data: not an audit and not investment advice. Every line comes from a file under watch/ (watch/API.md describes each)."]
    return clean_lines(out), None


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0]); ap.add_argument("--watch", default="watch"); ap.add_argument("--top", type=int, default=5); a = ap.parse_args(); utf8_stdout()
    lines, err = build(a.watch, a.top)
    if err: print(err); sys.exit(2)
    print("\n".join(lines))


if __name__ == "__main__":
    main()
