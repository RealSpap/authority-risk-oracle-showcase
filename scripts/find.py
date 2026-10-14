#!/usr/bin/env python3
"""Ask the watch a question about ALL the tracked contracts, from the repository alone: no site, no network, no jq.

    python3 scripts/find.py --kind eoa --min-money 1e8                 # a plain key behind $100M or more
    python3 scripts/find.py --paused                                   # contracts that answer paused() true now
    python3 scripts/find.py --unreadable --chain robinhood              # where the independent reader cannot classify the admin
    python3 scripts/find.py --max-keys 2 --max-react-hours 24 --sort money_per_key --limit 10
    python3 scripts/find.py --alert --json                              # the contracts a rule is firing on, as JSON
    python3 scripts/find.py --watchlist mine.txt --alert --fail-if-any    # a gate for a cron job: exit code 3 when a rule is firing on one of MY contracts
    python3 scripts/find.py --min-money 1e8 --csv > exposed.csv         # the same rows for a spreadsheet (an unread value is an empty cell)

One row per tracked contract, joined from the score files, the independent read, the money figures, the pause state, the admin Safe activity and the alerts (the same joins as
scripts/dossier.py, for one contract). A value the watch did not read is None in the JSON and "?" in the table, and a filter on it EXCLUDES the row: `--max-keys 2` never returns a
contract whose keys are unknown. The footer says how many rows had the filtered field unread, so the absence of a match is never read as the absence of the thing.
"""
import argparse, csv, glob, io, json, os, sys
from watch_location import NO_STATE_HINT  # the state is on the watch-data branch

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from evaluate_rules import WATCH_SLUGS, LABEL, norm  # noqa: E402
from dossier import load, chain_key, utf8_stdout, clean_name  # noqa: E402

SORTS = {"money": ("money_usd", True), "score": ("score", False), "money_per_key": ("money_per_key_usd", True), "keys": ("keys_to_move", False), "react": ("react_hours", False)}


cn = lambda v: None if v is None else clean_name(v)   # noqa: E731 -- names and slugs come from DefiLlama: printed safely, None stays None


def table(W):
    """One dict per tracked contract (a list), joined from the watch files. Every joined field is None when its source is missing or has no record for the contract."""
    so, tvl, held, pz, sa, al = (load(os.path.join(W, n)) for n in ("second_opinion.json", "tvl.json", "held_assets.json", "pause_state.json", "safe_activity.json", "alerts.json"))
    read = {(r.get("chain"), norm(r.get("target"))): r for r in (so or {}).get("results", [])}
    woke, never = set(), set()
    for v in ((sa or {}).get("by_safe") or {}).values():
        if v.get("stale"): continue
        for t in v.get("governs") or []:
            if v.get("never_executed"): never.add(t)
    for c in (sa or {}).get("changes") or []:
        if c.get("woke"): woke.update(c.get("governs") or [])
    rows = []
    for f in sorted(glob.glob(os.path.join(W, "scores", "*.json"))):
        d = load(f) or {}; slug = os.path.basename(f)[:-5]; key = WATCH_SLUGS.get(slug) or ("solana" if d.get("kind") == "solana" else None)
        if not key: continue
        for t in d.get("targets", []):
            addr = norm(t["target"]); ka = key + ":" + addr; r = read.get((key, addr)); ex = (r or {}).get("exposure") if isinstance((r or {}).get("exposure"), dict) else None
            m = ((tvl or {}).get("matched") or {}).get(ka.lower()) or {}; h = ((held or {}).get("by_target") or {}).get(ka.lower()) or {}   # tvl_match.py and held_assets.py key their records in lower case, a Solana (base58) address included
            money = ex.get("tvl_usd") if ex and ex.get("tvl_usd") is not None else (m.get("tvl") if m.get("tvl") is not None else (h.get("held_usd") if not h.get("stale") else None))
            z = ((pz or {}).get("by_target") or {}).get(ka)
            rows.append({"chain": key, "target": addr, "slug": cn(m.get("slug")), "protocol": cn(m.get("name")), "posture": (r or {}).get("posture"), "disagree_text": ((r or {}).get("disagree") if not (r or {}).get("acknowledged") else None), "title": cn(m.get("name")) or (addr[:6] + "…" + addr[-4:]), "score": t.get("compositeScore"), "stale": bool(t.get("stale")),
                         "kind": (r or {}).get("kind"), "keys_to_move": ex.get("keys_to_move") if ex else None, "react_hours": ex.get("react_hours") if ex else None,
                         "money_usd": money, "money_per_key_usd": ex.get("money_per_key_usd") if ex else None,
                         "paused": None if (pz is None or not z or z.get("stale")) else bool(z.get("paused")), "disagree": None if r is None else bool(r.get("disagree") and not r.get("acknowledged")),
                         "admin_safe_woke": ka in woke if sa is not None else None, "admin_safe_never_used": ka in never if sa is not None else None,
                         "alert": None if al is None else any(norm(x.get("target")) == addr and (x.get("chain") == d.get("name") or str(d.get("name")).startswith(str(x.get("chain")) + " (")) for x in al.get("active", []))})
    return rows


def watchlist(rows, lines):
    """(rows kept, entries that matched no tracked contract). An entry is an address, `chain:address` or a DefiLlama protocol slug; a blank line or a `#` comment is skipped. Addresses compare
    in lower case (a Solana one included); a shortened `0x1234…abcd` is not an entry. An entry nothing matches is RETURNED, so a typo or an untracked contract is never read as "nothing wrong"."""
    want = [l.split("#")[0].strip().lower() for l in lines]; want = [w for w in want if w]; hit, kept = set(), []
    for r in rows:
        keys = {r["target"].lower(), (r["chain"] + ":" + r["target"]).lower(), str(r.get("slug") or "").lower()} - {""}
        m = [w for w in want if w in keys]
        if m: hit.update(m); kept.append(r)
    return kept, [w for w in want if w not in hit]


def select(rows, a):
    """(selected rows, {filtered field: number of rows where it was unread}) for the namespace a."""
    unread = {}
    def need(row, field, test):
        v = row.get(field)
        if v is None: unread[field] = unread.get(field, 0) + 1; return False
        return bool(test(v))
    out = []
    for r in rows:
        if a.chain and r["chain"] != chain_key(a.chain): continue
        if a.kind and not need(r, "kind", lambda v: v == a.kind): continue
        if a.min_money is not None and not need(r, "money_usd", lambda v: v >= a.min_money): continue
        if a.max_score is not None and not need(r, "score", lambda v: v <= a.max_score): continue
        if a.max_keys is not None and not need(r, "keys_to_move", lambda v: v <= a.max_keys): continue
        if a.max_react_hours is not None and not need(r, "react_hours", lambda v: v <= a.max_react_hours): continue
        if a.paused and not need(r, "paused", lambda v: v): continue
        if a.disagree and not need(r, "disagree", lambda v: v): continue
        if a.unreadable and r.get("kind") not in ("unreadable", "native"):
            if r.get("kind") is None: unread["kind"] = unread.get("kind", 0) + 1
            continue
        if a.safe_woke and not need(r, "admin_safe_woke", lambda v: v): continue
        if a.safe_never_used and not need(r, "admin_safe_never_used", lambda v: v): continue
        if a.alert and not need(r, "alert", lambda v: v): continue
        if a.not_stale and r["stale"]: continue
        out.append(r)
    field, rev = SORTS[a.sort]
    out.sort(key=lambda r: (r.get(field) is None, -(r.get(field) or 0) if rev else (r.get(field) or 0)))
    return (out[:a.limit] if a.limit else out), unread


COLUMNS = ("chain", "target", "title", "protocol", "slug", "score", "stale", "kind", "posture", "keys_to_move", "react_hours", "money_usd", "money_per_key_usd", "paused", "disagree", "admin_safe_woke", "admin_safe_never_used", "alert")


def cell(v):
    """One CSV cell. A value the watch did not read is an EMPTY cell, never 0 or "no". A text starting with = + - @ (or a tab or return) would be run as a formula by a spreadsheet: it gets a leading
    apostrophe, because the protocol names come from a third party (DefiLlama)."""
    if v is None: return ""
    if isinstance(v, bool): return "true" if v else "false"
    v = str(v) if not isinstance(v, (int, float)) else v
    return "'" + v if isinstance(v, str) and v[:1] in ("=", "+", "-", "@", "\t", "\r") else v


def to_csv(rows):
    """The rows as CSV text (header first, one line per contract, the columns of COLUMNS), for a spreadsheet."""
    out = io.StringIO(); w = csv.writer(out, lineterminator="\n"); w.writerow(COLUMNS)
    for r in rows: w.writerow([cell(r.get(c)) for c in COLUMNS])
    return out.getvalue()


def fmt(v):
    if v is None: return "?"
    if isinstance(v, bool): return "yes" if v else "no"
    if isinstance(v, float) and abs(v) >= 1000: return "{:,.0f}".format(v)
    return str(v)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0]); ap.add_argument("--watch", default="watch")
    ap.add_argument("--chain"); ap.add_argument("--kind", help="eoa, safe, timelock, contract, squads, pda, unreadable, native")
    ap.add_argument("--min-money", type=float); ap.add_argument("--max-score", type=int); ap.add_argument("--max-keys", type=int); ap.add_argument("--max-react-hours", type=float)
    for f in ("paused", "disagree", "unreadable", "safe-woke", "safe-never-used", "alert", "not-stale"): ap.add_argument("--" + f, action="store_true")
    ap.add_argument("--sort", choices=sorted(SORTS), default="money"); ap.add_argument("--limit", type=int, default=0); ap.add_argument("--json", action="store_true"); ap.add_argument("--watchlist", help="a file: one address, chain:address or protocol slug per line (# comments); only those contracts are looked at, and an entry that matches nothing is said on stderr")
    ap.add_argument("--fail-if-any", action="store_true", help="exit code 3 when at least one row is selected (for a cron job or a CI step); 2 stays for usage errors"); ap.add_argument("--csv", action="store_true", help="CSV on the standard output, an empty cell where the watch did not read the value")
    a = ap.parse_args(); utf8_stdout()
    rows = table(a.watch)
    if not rows: print("no tracked contract in %s/scores" % a.watch + NO_STATE_HINT); sys.exit(2)
    if a.chain and not chain_key(a.chain): print("unknown chain %r (chains: %s)" % (a.chain, ", ".join(sorted(LABEL)))); sys.exit(2)
    if a.watchlist:
        try: rows, lost = watchlist(rows, open(a.watchlist, encoding="utf-8").read().split("\n"))
        except OSError as e: print("cannot read the watchlist: %s" % e); sys.exit(2)
        for w in lost: print("watchlist: %r matches no tracked contract (a typo, or not tracked: that says nothing about its risk)" % w, file=sys.stderr)
    sel, unread = select(rows, a)
    output(a, rows, sel, unread)
    if a.fail_if_any:
        if sel: sys.exit(3)
        if unread: print("gate: exit 0, but not every row could be judged: %s" % ("; ".join("%d row(s) with %s not read" % (n, f) for f, n in sorted(unread.items()))), file=sys.stderr)   # a gate that cannot see is not a gate that is green


def output(a, rows, sel, unread):
    if a.csv:
        sys.stdout.write(to_csv(sel))
        if unread: print("".join("%d row(s) excluded because %s was not read.\n" % (n, f) for f, n in sorted(unread.items())), end="", file=sys.stderr)   # on stderr: the CSV on stdout stays a CSV
        return
    if a.json: print(json.dumps({"count": len(sel), "of": len(rows), "unread_on_filtered_field": unread, "rows": sel}, indent=1)); return
    cols = ("chain", "score", "money_usd", "keys_to_move", "react_hours", "kind", "title")
    print("  ".join(c.ljust(12) if c != "title" else c for c in cols))
    for r in sel:
        flags = [n for n, v in (("PAUSED", r["paused"]), ("DISAGREES", r["disagree"]), ("SAFE WOKE", r["admin_safe_woke"]), ("ALERT", r["alert"]), ("STALE", r["stale"])) if v]
        print("  ".join(fmt(r[c]).ljust(12) if c != "title" else fmt(r[c]) for c in cols) + ("   [" + ", ".join(flags) + "]" if flags else ""))
    print("\n%d of %d tracked contract(s)." % (len(sel), len(rows)) + ("".join("\n%d row(s) excluded because %s was not read." % (n, f) for f, n in sorted(unread.items())) if unread else ""))


if __name__ == "__main__":
    main()
