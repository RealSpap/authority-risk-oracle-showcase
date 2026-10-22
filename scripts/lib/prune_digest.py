"""Keeps the daily report in step with the queue: watch/digest.md is written once a day (the first run before 06:00 UTC) and published until the next one, so a queued operation
that becomes executable for more than FRESH_READY_DAYS days (lib/fresh_ops.py) between two reports would stay listed in it, and in the review queue it carries, for up to a day after every
other file dropped it. This removes, from the report, the lines that name such an operation, and recounts the titles. Standard library only. Prints file names only, never a target or a number
taken from the data.

A line of the report is dropped when it starts with "- **" and
  - it cites "proposal #N" under "queued operation executable" and no operation with that index is listed in pending_ops.json (a Squads proposal that is no longer published);
  - or it says "ready at <date>" and that date is more than 7 days in the past;
  - or it is a "queued ..." review item whose (chain, target) has no operation listed in pending_ops.json.
Called by review_queue.py at every run (a failure there never stops the run) and usable alone:  python3 scripts/lib/prune_digest.py --watch watch [--now <epoch>]
"""
import calendar, json, os, re, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from lib.fresh_ops import FRESH_READY_DAYS  # noqa: E402

WEEK = FRESH_READY_DAYS * 86400
CITED = re.compile(r"queued operation executable[^\n]{0,400}?proposal #(\d+)(?!\d)")
READY_AT = re.compile(r"ready at (\d{4}-\d\d-\d\d \d\d:\d\dZ)")
ORPHAN = re.compile(r"^- \*\*(queued [^*]+)\*\* (\S+) (\S+) \(")


def published(po):
    """(indexes of the operations listed in the 'pending' lists, {(chain, target)} of those operations)."""
    idx, pub = set(), set()
    for r in po.get("results", []):
        for p in r.get("pending", []):
            if p.get("index") is not None: idx.add(p.get("index"))
            pub.add((r.get("chain"), str(p.get("target")).lower()))
    return idx, pub


def stale_line(l, idx, pub, now):
    if not l.startswith("- **"): return False
    t = l.replace("\\u2026", "\u2026")
    if any(int(m) not in idx for m in CITED.findall(t)): return True
    if any(now - calendar.timegm(time.strptime(m, "%Y-%m-%d %H:%MZ")) > WEEK for m in READY_AT.findall(l)): return True
    m = ORPHAN.match(l)
    return bool(m) and m.group(1).startswith("queued ") and (m.group(2), m.group(3).lower()) not in pub


def prune_text(t, idx, pub, now):
    """(new text, number of lines dropped). The counts in the titles are recomputed from what is left."""
    out, removed = [], 0
    for l in t.split("\n"):
        if stale_line(l, idx, pub, now): removed += 1; continue
        out.append(l)
    if not removed: return t, 0
    sec, counts, head = None, {}, {}
    for n, l in enumerate(out):
        if l.startswith("### "): sec = n; counts[n] = 0; head[n] = l
        elif l.startswith("## "): sec = None
        elif sec is not None and l.startswith("- **"): counts[sec] += 1
    drop = set()
    for n, l in head.items():
        c = counts[n]
        if l.startswith("### Overdue:"):
            if c == 0:
                drop.add(n)
                if n + 1 < len(out) and out[n + 1] == "": drop.add(n + 1)
            else: out[n] = re.sub(r"Overdue: \d+", "Overdue: %d" % c, l)
        elif re.search(r"\(\d+\)$", l): out[n] = re.sub(r"\(\d+\)$", "(%d)" % c, l)
    byname = {re.sub(r" \(\d+\)$", "", l[4:]): counts[n] for n, l in head.items()}
    p1 = byname.get("Something happened: read before trusting the score", 0); p2 = byname.get("Decide", 0); p3 = byname.get("Coverage to extend", 0)
    ages = [float(m) for n, l in enumerate(out) if n not in drop and l.startswith("- **") for m in re.findall(r"\((\d+(?:\.\d+)?) d\)", l)[:1]]
    for n, l in enumerate(out):
        if l.startswith("## Needs a person"):
            out[n] = re.sub(r": \d+ item\(s\) \(priority 1: \d+, priority 2: \d+, priority 3: \d+\); oldest [\d.]+ d",
                            ": %d item(s) (priority 1: %d, priority 2: %d, priority 3: %d); oldest %s d" % (p1 + p2 + p3, p1, p2, p3, ("%.1f" % max(ages)) if ages else "0.0"), l)
    return "\n".join(l for n, l in enumerate(out) if n not in drop), removed


def prune_digest(watch, now=None):
    """Prunes watch/digest.md against watch/pending_ops.json. Returns the list of file names written (empty when nothing was dropped or a file is missing or unreadable: nothing is ever guessed)."""
    now = time.time() if now is None else now
    try:
        po = json.load(open(os.path.join(watch, "pending_ops.json"), encoding="utf-8"))
        text = open(os.path.join(watch, "digest.md"), encoding="utf-8").read()
    except (OSError, ValueError): return []
    idx, pub = published(po)
    new, n = prune_text(text, idx, pub, now)
    if not n: return []
    tmp = os.path.join(watch, "digest.md.tmp")
    with open(tmp, "w", encoding="utf-8") as fh: fh.write(new)
    os.replace(tmp, os.path.join(watch, "digest.md"))
    return ["digest.md"]


if __name__ == "__main__":
    w = sys.argv[sys.argv.index("--watch") + 1] if "--watch" in sys.argv else "watch"
    now = float(sys.argv[sys.argv.index("--now") + 1]) if "--now" in sys.argv else None
    done = prune_digest(w, now)
    print("  files rewritten: " + ", ".join(done) if done else "  nothing to drop")
