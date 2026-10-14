#!/usr/bin/env python3
"""An authority-risk brief for ONE protocol, on every chain it is tracked on, in Markdown: what a DAO or a reviewer would want on one page.

    python3 scripts/brief.py morpho-blue
    python3 scripts/brief.py ethena-usde > ethena-brief.md     # a DefiLlama slug, or any part of a name that matches ONE protocol ("ethena" matches two: the candidates are listed)

The dossier (scripts/dossier.py) is one contract; this is the protocol: its tracked contracts on all chains, the weakest deployment, the fewest keys and the shortest reaction time, the money
attached (by the dashboard's own rule), what needs a person, and what the watch could NOT read about it. Built from the files of the repository alone: no site, no network. Public data only,
and a reading of who can act and how fast, not an audit and not investment advice. A value the watch did not read is said so; a headline never rests on a value that is unknown.
Exit code 2 when no protocol matches or the name is ambiguous (the candidates are listed).
"""
import argparse, os, sys
from watch_location import NO_STATE_HINT  # the state is on the watch-data branch

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from evaluate_rules import LABEL, lower_keys  # noqa: E402
from risk_by_cause import money_once  # noqa: E402
from dossier import load, utf8_stdout, clean_lines  # noqa: E402
from find import table  # noqa: E402


def protocols(rows):
    """{slug: {"name", "rows"}} over the contracts the watch could attach to a DefiLlama protocol."""
    out = {}
    for r in rows:
        if r.get("slug"): out.setdefault(r["slug"], {"name": r.get("protocol") or r["slug"], "rows": []})["rows"].append(r)
    return out


def match(rows, query):
    """The protocols whose slug or name contains the query (case-insensitive); an exact slug wins over longer matches."""
    q = str(query).strip().lower(); ps = protocols(rows)
    if q in ps: return {q: ps[q]}
    return {s: p for s, p in ps.items() if q and (q in s.lower() or q in str(p["name"]).lower())}


def money(W, rows):
    """Money attached to these contracts, by the rule of the dashboard and of risk_by_cause.py (`money_once`): one figure per protocol and DefiLlama chain, a protocol matched on its
    all-chain total counts once and swallows its per-chain figures, a retired or peripheral contract carries nothing, a vault with no match carries what it holds. Using the same function
    keeps the brief, the dashboard and the risk-by-cause total from giving three figures for one protocol (this file counted per-chain figures first until 10/10). None when no contract
    has a figure."""
    tvl = (load(os.path.join(W, "tvl.json")) or {}).get("matched") or {}; held = (load(os.path.join(W, "held_assets.json")) or {}).get("by_target") or {}
    scope = lower_keys((load(os.path.join(W, "tvl_scope.json")) or {}).get("targets"))
    kas = [(r["chain"] + ":" + r["target"]).lower() for r in rows]   # the files key their records in lower case, a Solana (base58) address included
    if not any((tvl.get(k) or {}).get("tvl") is not None or (held.get(k) or {}).get("held_usd") for k in kas): return None
    return money_once(kas, tvl, scope, held)


def usd(v): return "?" if v is None else ("$%.1fB" % (v / 1e9) if v >= 1e9 else "$%.0fM" % (v / 1e6) if v >= 1e6 else "$%s" % "{:,.0f}".format(v))


def short(a): return a[:6] + "…" + a[-4:]


def build(W, query):
    """(lines, error): the brief as lines, or (None, message) when nothing or several protocols match."""
    rows = table(W); hits = match(rows, query)
    if not rows: return None, "no tracked contract in %s/scores" % W + NO_STATE_HINT
    if not hits:
        top = sorted(protocols(rows).items(), key=lambda kv: -len(kv[1]["rows"]))[:8]
        return None, "no protocol matches %r. Most tracked: %s" % (query, ", ".join("%s (%d)" % (s, len(p["rows"])) for s, p in top))
    if len(hits) > 1: return None, "%r matches several protocols: %s" % (query, ", ".join(sorted(hits)))
    slug, p = next(iter(hits.items())); rs = sorted(p["rows"], key=lambda r: (r["score"] if r["score"] is not None else 999, r["chain"]))
    chains = sorted({r["chain"] for r in rs}); total = money(W, rs); run = (load(os.path.join(W, "latest.json")) or {}).get("run_utc")
    out = ["# Authority risk brief: %s" % p["name"], "",
           "%d tracked contract(s) on %d chain(s): %s. About %s attached (DefiLlama, by the dashboard's rule: one figure per chain, an all-chain total counted once, a retired contract nothing). Read from the watch run of %s." % (len(rs), len(chains), ", ".join(LABEL.get(c, c) for c in chains), usd(total), run or "an unknown run"), ""]
    known = lambda f: [r for r in rs if r.get(f) is not None]
    out += ["## In short"]
    w = rs[0]; tied = [r for r in rs[1:] if r["score"] == w["score"]]
    out += ["- weakest deployment: **%s** on %s, score %s/100%s%s" % (short(w["target"]), LABEL.get(w["chain"], w["chain"]), w["score"], (": " + w["posture"]) if w.get("posture") else "", (" (%d other deployment(s) share this score: %s)" % (len(tied), ", ".join("%s %s" % (LABEL.get(r["chain"], r["chain"]), short(r["target"])) for r in tied))) if tied else "")]
    k = known("keys_to_move"); r_ = known("react_hours")
    if k: m_ = min(k, key=lambda r: r["keys_to_move"]); out += ["- fewest keys to move the money: **%s** on %s (%s)" % (m_["keys_to_move"], LABEL.get(m_["chain"], m_["chain"]), short(m_["target"]))]
    if r_: m_ = min(r_, key=lambda r: r["react_hours"]); out += ["- shortest time to react: **%s h** on %s (%s)" % (m_["react_hours"], LABEL.get(m_["chain"], m_["chain"]), short(m_["target"]))]
    read = [r for r in rs if r.get("kind") not in (None, "unreadable", "native")]; plain = [r for r in read if r.get("kind") == "eoa"]
    out += ["- a plain key as admin on %d of the %d contract(s) whose admin was read (%d not read)" % (len(plain), len(read), len(rs) - len(read))]
    out += ["- %d of %d contract(s) have a stale score (the oracle has not pushed it within its maxStaleness)" % (sum(1 for r in rs if r["stale"]), len(rs)), ""]
    out += ["## Contracts", "", "| Chain | Contract | Score | Admin | Keys | React | Money |", "|---|---|---|---|---|---|---|"]
    for r in rs: out += ["| %s | `%s` | %s | %s | %s | %s | %s |" % (LABEL.get(r["chain"], r["chain"]), short(r["target"]), r["score"], r.get("posture") or r.get("kind") or "not read", "?" if r["keys_to_move"] is None else r["keys_to_move"], "?" if r["react_hours"] is None else "%s h" % r["react_hours"], usd(r["money_usd"]))]
    flags = []
    for r in rs:
        where = "%s %s" % (LABEL.get(r["chain"], r["chain"]), short(r["target"]))
        if r.get("paused"): flags += ["**paused**: %s answers `paused()` true" % where]
        if r.get("disagree_text"): flags += ["the independent reader disagrees with the score on %s: %s" % (where, r["disagree_text"])]
        if r.get("admin_safe_woke"): flags += ["the admin Safe of %s, idle for a long stretch, executed again" % where]
        if r.get("alert"): flags += ["a rule is firing on %s" % where]
        if r.get("admin_safe_never_used"): flags += ["the admin Safe of %s has never executed a transaction (nonce 0)" % where]
    out += ["", "## What needs a person"] + (["- " + f for f in flags] or ["- nothing flagged in the sources read"])
    unread = {"admin read": sum(1 for r in rs if r.get("kind") in (None, "unreadable", "native")), "keys and reaction time": sum(1 for r in rs if r.get("keys_to_move") is None), "money": sum(1 for r in rs if r.get("money_usd") is None),
              "pause state": sum(1 for r in rs if r.get("paused") is None)}
    out += ["", "## What the watch did not read about this protocol"] + ["- %s: %d of %d contract(s)" % (k_, n, len(rs)) for k_, n in unread.items() if n] + ([] if any(unread.values()) else ["- everything asked was read"])
    out += ["", "A contract whose pause state is not read may still be paused: the watch only sees `paused()` and `isPaused()`. Scores are the oracle's reading of who can act and how fast; this is not an audit and not investment advice.", "Source: `watch/` of the repository (`watch/API.md` describes each file)."]
    return clean_lines(out), None


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0]); ap.add_argument("protocol"); ap.add_argument("--watch", default="watch"); a = ap.parse_args(); utf8_stdout()
    lines, err = build(a.watch, a.protocol)
    if err: print(err); sys.exit(2)
    print("\n".join(lines))


if __name__ == "__main__":
    main()
