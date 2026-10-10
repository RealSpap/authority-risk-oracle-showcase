#!/usr/bin/env python3
"""Two or more protocols side by side, from the files of the repository alone: no site, no network.

    python3 scripts/compare.py morpho-blue aave-v3
    python3 scripts/compare.py morpho aave compound --json
    python3 scripts/compare.py --chains                    # the same table with one column per CHAIN instead (all chains), or --chains base arbitrum for some

For each protocol (a DefiLlama slug or any part of its name, as in scripts/brief.py): how many tracked contracts and chains, the weakest score, the fewest keys to move the money, the shortest time to
react, how many contracts have a plain key as admin, the money attached (the dashboard's rule), and what is paused, alerting or stale. A value the watch did not read is `?` (None in the JSON) and a
count says how many contracts it was read on, so a protocol with half of its contracts unread never looks safer than one fully read. A reading of who can act and how fast, not an audit and not advice.
Exit code 2 when a name matches no protocol or several (the candidates are listed).
"""
import argparse, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from dossier import utf8_stdout, chain_key  # noqa: E402
from evaluate_rules import LABEL  # noqa: E402
from find import table  # noqa: E402
from brief import match, money, usd  # noqa: E402


def summary(W, query, rows=None):
    """(summary dict, error): the metrics of the one protocol `query` names."""
    rows = table(W) if rows is None else rows; hits = match(rows, query)
    if not hits: return None, "no protocol matches %r" % query
    if len(hits) > 1: return None, "%r matches several protocols: %s" % (query, ", ".join(sorted(hits)))
    slug, p = next(iter(hits.items())); return stats(W, rs=p["rows"], key=slug, name=p["name"]), None


def stats(W, rs, key, name):
    """The metrics of one group of tracked contracts (a protocol, or a chain)."""
    def low(field):   # (smallest known value, number of contracts where it was read)
        vals = [r[field] for r in rs if r.get(field) is not None]; return (min(vals) if vals else None), len(vals)
    score, n_score = low("score"); keys, n_keys = low("keys_to_move"); react, n_react = low("react_hours")
    read = [r for r in rs if r.get("kind") not in (None, "unreadable", "native")]
    return {"protocol": key, "name": name, "contracts": len(rs), "chains": len({r["chain"] for r in rs}), "weakest_score": score, "weakest_score_read_on": n_score,
            "fewest_keys": keys, "fewest_keys_read_on": n_keys, "shortest_react_hours": react, "shortest_react_read_on": n_react,
            "plain_key_admins": sum(1 for r in read if r.get("kind") == "eoa"), "admin_read_on": len(read), "money_usd": money(W, rs),
            "paused": sum(1 for r in rs if r.get("paused")), "alerting": sum(1 for r in rs if r.get("alert")), "stale": sum(1 for r in rs if r.get("stale"))}


def by_chain(W, rows, wanted=()):
    """(summaries, error): one summary per chain, in the order asked (all the chains that have a tracked contract when none is asked)."""
    keys = [chain_key(w) for w in wanted]
    if wanted and not all(keys): return None, "unknown chain %r (chains: %s)" % (wanted[keys.index(None)], ", ".join(sorted(LABEL)))
    keys = keys or sorted({r["chain"] for r in rows}); out = []
    for k in dict.fromkeys(keys):   # a chain named twice once
        rs = [r for r in rows if r["chain"] == k]
        if not rs: return None, "no tracked contract on %s" % LABEL.get(k, k)
        out.append(stats(W, rs, k, LABEL.get(k, k)))
    return out, None


def render(sums):
    cell = lambda v: "?" if v is None else str(v)
    of = lambda v, n, total: "%s (read on %d of %d)" % (cell(v), n, total)
    lines = [("", [s["name"] for s in sums]), ("contracts / chains", ["%d / %d" % (s["contracts"], s["chains"]) for s in sums]),
             ("weakest score", [of(s["weakest_score"], s["weakest_score_read_on"], s["contracts"]) for s in sums]),
             ("fewest keys to move the money", [of(s["fewest_keys"], s["fewest_keys_read_on"], s["contracts"]) for s in sums]),
             ("shortest time to react", [of(None if s["shortest_react_hours"] is None else "%s h" % s["shortest_react_hours"], s["shortest_react_read_on"], s["contracts"]) for s in sums]),
             ("plain key as admin", ["%d of %d read" % (s["plain_key_admins"], s["admin_read_on"]) for s in sums]), ("money attached", [usd(s["money_usd"]) for s in sums]),
             ("paused / alerting / stale", ["%d / %d / %d" % (s["paused"], s["alerting"], s["stale"]) for s in sums])]
    w0 = max(len(l) for l, _ in lines); ws = [max(len(v[i]) for _, v in lines) for i in range(len(sums))]
    return "\n".join("  ".join([l.ljust(w0)] + [v[i].ljust(ws[i]) for i in range(len(sums))]).rstrip() for l, v in lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0]); ap.add_argument("protocols", nargs="*", help="protocol slugs or names; with --chains, chain names"); ap.add_argument("--watch", default="watch"); ap.add_argument("--json", action="store_true")
    ap.add_argument("--chains", action="store_true", help="one column per chain instead of per protocol")
    a = ap.parse_args(); utf8_stdout(); rows = table(a.watch)
    if not rows: print("no tracked contract in %s/scores" % a.watch); sys.exit(2)
    if not a.chains and not a.protocols: ap.error("name at least one protocol, or use --chains")
    sums, seen = [], set()
    if a.chains:
        sums, err = by_chain(a.watch, rows, a.protocols)
        if err: print(err); sys.exit(2)
        a.protocols = []
    for q in a.protocols:
        s, err = summary(a.watch, q, rows)
        if err: print(err); sys.exit(2)
        if s["protocol"] in seen: continue   # the same protocol named twice is compared with itself once
        seen.add(s["protocol"]); sums.append(s)
    if a.json: print(json.dumps({"protocols": sums}, indent=1)); return
    print(render(sums))
    if a.chains: print("\nThe money of two chains is not additive: a protocol matched on its all-chain total is counted in full on every chain it is matched on.")
    print("\nRead from the watch files only. Scores are the oracle's reading of who can act and how fast; not an audit, not investment advice.")


if __name__ == "__main__":
    main()
