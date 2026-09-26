#!/usr/bin/env python3
"""One dated report for whoever watches this oracle: deadlines, authority changes, queued operations, code changes, and what could not be read.

It assembles five existing read-only checks, adding no reading logic of its own:
  1. oracle_freshness.py         -> which deployed oracle turns stale, and when (act-now list)
  2. check_safe_changes.py       -> Safe signer / threshold / module / guard / singleton changes over --days (default 7)
  3. check_pending_ops.py        -> what is queued behind the watched timelocks, and what cleared recently
  4. check_implementation_changes.py -> has the code behind a tracked target changed since the reviewed snapshot
  5. check_squads_changes.py     -> did a Squads v4 multisig behind a Solana target change members, threshold or time lock since its snapshot

    python3 scripts/daily_digest.py                        # Markdown to stdout, about 10 to 25 minutes
    python3 scripts/daily_digest.py --days 7 --out data/digest_2026-09-26.md

A source that could not be read is listed under "Not read" and is never reported as quiet. The closing line says "nothing moved" ONLY when every source
was read and none had a finding; otherwise it says which sources are missing. Ecosystems whose public RPC cannot serve the Safe-events query
(Tempo, Monad, Hyperliquid; see data/finding_2026-09-26-safe-changes-30d-and-v150-singleton.md) are listed as not attempted, not skipped silently.
Posture drift (published score vs live scorer, check_posture_drift.py) takes up to 50 minutes and is not included: run it separately.
Disclosed only. Nothing is sent anywhere; alerting is a separate, opt-in step (scripts/lib/alerts.py).
"""
import argparse
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "lib"))
import check_pending_ops  # noqa: E402
import check_safe_changes  # noqa: E402
from check_cross_ecosystem_overlap import REGISTRIES  # noqa: E402
from lib import code_review  # noqa: E402
from lib.safe_changes import rank  # noqa: E402

SAFE_ECOSYSTEMS = ["ethereum-l1", "arbitrum", "base", "plasma", "robinhood"]
NOT_ATTEMPTED = {"tempo": "public RPC returned no control events", "monad": "public RPC caps eth_getLogs near 100 blocks",
                 "hyperliquid": "public RPC rate-limits the query"}
FRESH_LINE = re.compile(r"^\s+(?P<name>.+?)\s+(?P<n>\d+) targets, oldest update (?P<oldest>.+?), first entry turns stale in (?P<hours>[\d.]+) h \((?P<when>.+?)\)")
ACT_NOW_HOURS = 96


def run(script, *args, timeout=3000):
    r = subprocess.run([sys.executable, os.path.join(HERE, script), *args], capture_output=True, text=True, timeout=timeout)
    return r.returncode, [l for l in (r.stdout + r.stderr).splitlines() if "warn" not in l.lower()]


def freshness():
    code, lines = run("oracle_freshness.py", "--warn-hours", str(ACT_NOW_HOURS))
    rows = [m.groupdict() for m in map(FRESH_LINE.match, lines) if m]
    if len(rows) < 9:  # 8 EVM oracles + Solana: fewer rows than that means an oracle line is missing
        return None, [f"oracle_freshness.py returned {len(rows)} of 9 oracle lines (exit {code})"]
    return rows, []


def safe_changes(days):
    findings, unread = [], []
    for eco in SAFE_ECOSYSTEMS:
        r = check_safe_changes.check_ecosystem(eco, REGISTRIES[eco][1], days, 1200)
        if r["status"].startswith("UNREAD"):
            unread.append(f"Safe changes, {eco}: {r['status']}")
            continue
        findings += [(eco, e) for e in rank(r["events"])]
    return findings, unread


def pending(recent_days):
    act, recent, unread = [], [], []
    for w in check_pending_ops.WATCHLIST:
        r = check_pending_ops.check_timelock(*w, 365, recent_days)
        if r["status"].startswith("UNREAD"):
            unread.append(f"Timelock queue, {r['name']}: {r['status']}")
            continue
        act += [(r["name"], p) for p in r["pending"] if p["state"] != "expired"]
        recent += [(r["name"], p) for p in r["recent"]]
    return act, recent, unread


def code_changes():
    """(exit code, lines about a CHANGED or UNREAD target, count of NEW targets not yet in the snapshot, snapshot date)."""
    code, lines = run("check_implementation_changes.py", timeout=3000)
    bad = [l.strip() for l in lines if re.search(r"\[(CHANGED|UNREAD)", l)]
    new = sum(1 for l in lines if "[NEW]" in l)
    m = next((re.search(r"snapshot of (\S+)", l) for l in lines if "snapshot of" in l), None)
    return code, bad, new, (m.group(1) if m else "unknown")


def squads_changes():
    """(exit code, CHANGED/UNREAD lines, headline)"""
    code, lines = run("check_squads_changes.py", timeout=900)
    bad = [l.strip() for l in lines if re.search(r"\[(CHANGED|UNREAD)\]", l)]
    head = next((l.strip() for l in lines if "multisigs read" in l), "")
    return code, bad, head


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--out")
    args = ap.parse_args()
    now = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())
    out = [f"# Authority risk digest, {now}", ""]
    unread, findings = [], 0

    rows, u = freshness()
    unread += u
    out.append("## Act now: oracles turning stale")
    if rows:
        soon = sorted((r for r in rows if float(r["hours"]) <= ACT_NOW_HOURS * 2.5), key=lambda r: float(r["hours"]))
        for r in soon:
            urgent = float(r["hours"]) <= ACT_NOW_HOURS
            findings += urgent
            out.append(f"- {'**ACT NOW** ' if urgent else ''}{r['name']}: {r['n']} targets, first entry turns stale in {float(r['hours']):.0f} h ({r['when']}); oldest update {r['oldest']}")
        if not soon:
            out.append("- none within 10 days")
    else:
        out.append("- not read")

    sc, u = safe_changes(args.days)
    unread += u
    out += ["", f"## Safe authority changes, last {args.days} days"]
    findings += len(sc)
    out += [f"- {eco}: {e['name']} {e['value']} on {e['safe']} ({', '.join(e['groups'])}), tx {e['tx']}" for eco, e in sc] or ["- none in the ecosystems read"]
    out.append("- not attempted: " + "; ".join(f"{k} ({v})" for k, v in NOT_ATTEMPTED.items()))

    act, recent, u = pending(args.days)
    unread += u
    names = code_review.resolve_names({p["selector"] for _, p in act + recent if p["selector"] != "0x"}) if act + recent else {}

    def fn(p):
        return (names.get(p["selector"]) or [p["selector"]])[0]

    out += ["", "## Timelock queue"]
    findings += len(act)
    out += [f"- **executable or waiting** {n}: {p['target']} {fn(p)} ready at {time.strftime('%Y-%m-%d %H:%M', time.gmtime(p['ready_at']))}Z ({p['state']})" for n, p in act] or ["- nothing pending on the 6 watched timelocks"]
    out += [f"- cleared, queued {time.strftime('%Y-%m-%d', time.gmtime(p['queued_at']))}: {n} -> {p['target']} {fn(p)}" for n, p in recent if not p["still_queued"]]

    code, bad, new_targets, snap = code_changes()
    out += ["", "## Code behind tracked targets"]
    if code == 0 and not bad:
        out.append(f"- no tracked target's implementation changed since the reviewed snapshot ({snap})")
    else:
        findings += 1
        out += [f"- {h}" for h in bad] or ["- check_implementation_changes.py exited non-zero without a CHANGED or UNREAD line: read it directly"]
        if any("UNREAD" in h for h in bad) or not bad:
            unread.append("Implementation watch: a target or oracle could not be read, or the script failed")
    if new_targets:
        out.append(f"- {new_targets} target(s) added since that snapshot are not fingerprinted yet (informational: run check_implementation_changes.py --update after a look)")

    code, bad, head = squads_changes()
    out += ["", "## Solana Squads v4 multisigs (members, threshold, time lock)"]
    if code == 0 and head:
        out.append(f"- no change since the snapshot ({head})")
    else:
        findings += 1
        out += [f"- {h}" for h in bad] or ["- check_squads_changes.py failed without a recognizable line: read it directly"]
        if any("[UNREAD]" in h for h in bad) or not head:
            unread.append("Squads watch: a multisig could not be read, or the script failed")

    out += ["", "## Not read (no conclusion drawn for these)"]
    out += [f"- {u}" for u in unread] or ["- every attempted source was read"]
    out += ["", "Posture drift (published score vs live scorer) is not part of this digest: run scripts/check_posture_drift.py."]
    out.append("")
    caveat = f" Safe events are not covered for: {', '.join(NOT_ATTEMPTED)}."
    out.append(f"**Nothing moved in the sources read.**{caveat}" if not findings and not unread else f"**{findings} item(s) above; {len(unread)} source(s) not read.**{caveat}")
    text = "\n".join(out)
    print(text)
    if args.out:
        with open(args.out, "w") as f:
            f.write(text + "\n")


if __name__ == "__main__":
    main()
