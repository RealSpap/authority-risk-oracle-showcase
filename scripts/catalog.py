#!/usr/bin/env python3
"""A catalogue of what the Watch publishes, for a program or an AI agent that has to find the right file before it reads one: watch/catalog.json.

    python3 scripts/catalog.py --watch watch --api watch/API.md

For every file under watch/ (one line per top-level file, one per folder of files such as scores/ or feed/): where to fetch it, what it is (the first
words of its row in watch/API.md, so the description is written once), its JSON Schema when there is one, its size. Then the questions people actually ask, each with
the file and the field that answers it. The same questions are the ones the site's llms.txt lists. Read-only; written near the end of the run, so
like status.json it is derived, not in the signed manifest (signature.json is the integrity record, and it is listed here too).

A file with no row in API.md is listed with an empty description and named under `undocumented`: the gap is visible, never papered over.
"""
import argparse, glob, json, os, re, time

from watch_location import RAW  # noqa: E402  -- the root of the watch-data branch (the old watch/ folder)
PAGES = "https://realspap.github.io/oracle/"
EXT = (".json", ".jsonl", ".xml", ".md", ".ics", ".csv", ".prom")
SKIP = {"who_controls.json", "alarm.md", "alerts_high.md", "catalog.json"}   # the signer index is never published; the alarm text is a transient; the catalogue does not list itself
# What people ask, and where the answer is. `file` must be a row of API.md (a test checks it); `field` says how to read the answer.
QUESTIONS = [
    {"ask": "Who controls this contract, and how many keys does it take to act?", "file": "second_opinion.json", "field": "results[] where chain and target match: kind, holder, threshold, keys_to_act, delay_seconds"},
    {"ask": "Which contracts put the most money behind the fewest keys?", "file": "second_opinion.json", "field": "exposure[]: keys_to_move, react_hours, money_per_key_usd"},
    {"ask": "Which contracts share an admin, and how much money is behind it?", "file": "second_opinion.json", "field": "clusters[]"},
    {"ask": "What is firing right now?", "file": "alerts.json", "field": "active[]: rule, severity, chain, target, first_seen"},
    {"ask": "Is anything paused?", "file": "pause_state.json", "field": "paused[] (chain:target keys); changes[] for a flip since the previous run"},
    {"ask": "What is queued against a contract, and when does it execute?", "file": "pending_ops.json", "field": "results[].pending[]: ready_at (or eta on a Compound-style timelock), signature, state (or still_queued)"},
    {"ask": "Did an admin Safe that was idle just execute?", "file": "safe_activity.json", "field": "woke[]; changes[] with delta and idle_days"},
    {"ask": "Is the Watch running and healthy?", "file": "status.json", "field": "state (ok / degraded / alarm) and reasons[]; metrics.prom: aro_run_timestamp_seconds"},
    {"ask": "Has any published file been altered after the run?", "file": "signature.json", "field": "manifest.files{path: sha256} and manifest.events_chain_head; at the top level signed, public_key, signature; verify: python3 scripts/sign_run.py --watch watch --verify"},
    {"ask": "What moved since the previous run?", "file": "latest.json", "field": "movers[], alerts[], unread[]"},
]


def api_rows(path):
    """{file name: (first words of the description, schema path or None)} from the markdown table of API.md; a row can name several files."""
    out = {}
    try: lines = open(path, encoding="utf-8").read().split("\n")
    except OSError: return out
    for l in lines:
        if not l.startswith("| `"): continue
        parts = l.split(" | ")
        if len(parts) < 2: continue
        desc = re.sub(r"\s+", " ", parts[1]).strip(); desc = desc if len(desc) <= 220 else desc[:220].rsplit(" ", 1)[0] + "…"
        last = parts[-1].strip().strip("|").strip().strip("`")
        schema = last if re.fullmatch(r"schema/[a-z_]+\.schema\.json", last) else None
        for n in re.findall(r"`([^`]+)`", parts[0]): out.setdefault(n, (desc, schema))
    return out


def build(W, api_path, now=None):
    rows = api_rows(api_path); files, undocumented = [], []
    for p in sorted(glob.glob(os.path.join(W, "*"))):
        n = os.path.basename(p)
        if os.path.isdir(p):
            kids = [k for k in glob.glob(os.path.join(p, "**", "*"), recursive=True) if os.path.isfile(k) and k.endswith(EXT)]
            if kids and n not in ("schema", "prev"):
                d, s = next((v for k, v in rows.items() if k.startswith(n + "/")), ("", None))   # the API.md row is named after a file inside, `scores/<oracle-slug>.json`
                files.append({"path": n + "/", "url": RAW + n + "/", "count": len(kids), "description": d, "schema": s})
            continue
        if n in SKIP or not n.endswith(EXT): continue
        d, s = rows.get(n, ("", None))
        if not d and n not in ("API.md", "README.md"): undocumented.append(n)
        files.append({"path": n, "url": RAW + n, "bytes": os.path.getsize(p), "description": d, "schema": s, "schema_url": (RAW + s) if s else None})
    twin = {"url": PAGES + "p/{chain}-{address}.json", "what": "the page of one contract as JSON: score, sub-scores, independent read, held assets, pause, roles, Safe activity; every key is described in API.md"}
    return {"generated_utc": now or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "repo": "RealSpap/authority-risk-oracle-showcase", "raw_base": RAW, "pages": PAGES, "reference": RAW + "API.md",
            "files": files, "contract_page": twin, "questions": [dict(q, url=RAW + q["file"]) for q in QUESTIONS], "undocumented": undocumented,
            "what": "where each published file is, what it holds and which one answers which question; descriptions come from watch/API.md, so a file without a row there is listed under `undocumented`"}


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--watch", default="watch"); ap.add_argument("--api", default="watch/API.md"); a = ap.parse_args()
    c = build(a.watch, a.api); p = os.path.join(a.watch, "catalog.json")
    open(p + ".tmp", "w").write(json.dumps(c, indent=1) + "\n"); os.replace(p + ".tmp", p)
    print("catalog.json: %d entries, %d question(s), %d undocumented%s" % (len(c["files"]), len(c["questions"]), len(c["undocumented"]), (": " + ", ".join(c["undocumented"])) if c["undocumented"] else ""))


if __name__ == "__main__":
    main()
