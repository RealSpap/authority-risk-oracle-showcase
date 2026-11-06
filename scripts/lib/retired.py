"""Targets an oracle still tracks on purpose although they are no longer scored (data/retired_targets.json, kept by hand).

The contract cannot remove a target, so such a target turns stale for ever. It is not hidden: the Watch publishes it in its own list ("retired", with the note and the date),
counts it apart, and leaves it out of the two counts that mean "something to do": the stale total and the methodology hashes in use.
A retired target does not stay out of sight if it is written again: when its lastUpdated is anything other than the value the file pins (the exact value read on chain when it was retired), the Watch counts it as a normal target
again and raises an alert on every run until a person edits the file.
Read errors never retire anything: a missing or broken file means the old behaviour (everything counted), and the reason is printed."""
import json, os, time

PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data", "retired_targets.json")


def load(path=PATH):
    """({"<oracle-slug>:<target lowercase>": entry}, None) or ({}, reason). An entry needs a note, a date and the lastUpdated it was retired at (an integer above zero)."""
    try:
        raw = json.load(open(path, encoding="utf-8")).get("targets")
    except (OSError, ValueError, AttributeError) as e:
        return {}, "%s: %s" % (os.path.basename(path), str(e)[:100])
    if not isinstance(raw, dict): return {}, "%s: no `targets` object" % os.path.basename(path)
    out = {}
    for k, v in raw.items():
        pin = v.get("last_update_at_retirement") if isinstance(v, dict) else None
        if not (isinstance(k, str) and ":" in k and isinstance(pin, int) and not isinstance(pin, bool) and 0 < pin <= time.time() + 86400 and isinstance(v.get("note"), str) and v["note"] and isinstance(v.get("since"), str) and v["since"]):
            return {}, "%s: entry %r is incomplete or its pin is not a plausible date in seconds (note, since, last_update_at_retirement)" % (os.path.basename(path), k)
        out[k.lower()] = v
    return out, None


def apply(slug, targets, registry):
    """Marks in place the targets of one oracle that are retired (t["retired"] = True) and returns (retired, woken), two lists of the target rows.
    retired: listed in the registry and not written since it was retired (lastUpdated equal to the pinned value). woken: listed, but written again (any other lastUpdated): counted as a normal target."""
    retired, woken = [], []
    for t in targets:
        t.pop("retired", None)
        e = registry.get("%s:%s" % (slug, str(t.get("target")).lower()))
        if not e: continue
        if t.get("lastUpdated") != e["last_update_at_retirement"]: woken.append(t)   # any other value, earlier or later, is a write (the updater supplies the date itself)
        else: t["retired"] = True; retired.append(t)
    return retired, woken


def listing(slug, retired, registry):
    """The published line of each retired target: where, which, the note, since when, the last update."""
    return [{"oracle": slug, "target": t["target"], "note": registry["%s:%s" % (slug, str(t["target"]).lower())]["note"], "since": registry["%s:%s" % (slug, str(t["target"]).lower())]["since"], "lastUpdated": t.get("lastUpdated")} for t in retired]
