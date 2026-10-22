#!/usr/bin/env python3
"""Everything a person must look at, in one ordered list: watch/review_queue.json (and .md). The run produces findings in seven
files (disagreements, admin changes, upgrades, transfers in flight, Safe modules and guards to classify, open disputes, unread
timelock queues, Safe signer events, methodology changes); this gathers them, ranks them, says what to do with each, and drops the
ones a person already reviewed (data/second_opinion_acknowledged.json, data/digest_acknowledged.json, disputes resolved). Read-only
over watch/ and data/, no RPC.

    python3 scripts/review_queue.py --watch watch --data data --out watch/review_queue.json --md watch/review_queue.md

Priorities: 1 = something happened (upgrade, admin change, transfer in flight, signer or threshold or module change, methodology
change): read it before trusting the score; 2 = the reader disagrees with the score or cannot classify something (disagreement,
module or guard to identify, open dispute, timelock queue unread, a delay or a guardian announced, an admin Safe that woke up): decide; 3 = coverage you may want to extend.\nSince 2026-10-10 the queue also reads the state files: a paused contract and a secondary role that changed hands are priority 1 (something happened).
"""
import argparse, json, os, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.fresh_ops import fresh_enough  # noqa: E402


def load(p):
    try: return json.load(open(p))
    except Exception: return None  # noqa: BLE001 -- a missing file contributes nothing


def state_items(W, add):
    """The state mechanisms of 2026-10-10 into the queue. A stale record (the call went unanswered) says nothing and adds nothing; a text never carries a value that changes from run
    to run, so an item keeps its age and a priority-1 one that nobody answers re-enters the alarm."""
    def split(k): c, _, t = str(k).partition(":"); return c, t
    for k, v in ((load(os.path.join(W, "pause_state.json")) or {}).get("by_target") or {}).items():
        if v.get("paused") and not v.get("stale"):
            c, t = split(k); add(1, "contract paused", c, t, "%s answers true" % v.get("via"), "find out why: an incident being contained, or the admin holding users' funds; do not rely on an exit until it is running again", "pause_state.json")
    for k, v in ((load(os.path.join(W, "side_roles.json")) or {}).get("by_target") or {}).items():
        c, t = split(k)
        for name, x in (v.get("pending") or {}).items():
            if x.get("stale"): continue
            if name == "timelock": add(1 if x.get("shorter") else 2, "delay change announced", c, t, "the contract's own delay is announced to go to %s h%s" % (int(x.get("seconds") or 0) // 3600, " (shorter)" if x.get("shorter") else ""), "a shorter delay leaves less time to react: decide whether to warn users before it applies", "side_roles.json")
            else: add(2, "guardian change announced", c, t, "a new guardian is announced (%s)" % (x.get("kind") or "unread"), "identify the designated guardian; a plain key is a weaker brake than a Safe", "side_roles.json")
    for ch in (load(os.path.join(W, "side_roles.json")) or {}).get("changes") or []:
        if ch.get("change") == "announced": continue   # the announcements are items above
        c, t = split(ch.get("target")); add(1, "secondary role changed hands", c, t, "%s: %s" % (ch.get("role"), ch.get("change")), "read who holds it now; in a vault a guardian can revoke a pending change, a curator allocates funds", "side_roles.json changes")
    for k, v in ((load(os.path.join(W, "held_assets.json")) or {}).get("by_target") or {}).items():
        c, t = split(k)
        if v.get("vanished") and not v.get("stale"): add(2, "balance no longer reported", c, t, "totalAssets() answered at an earlier run and no longer does", "an upgrade, a pause or a replaced implementation can do this: read the contract", "held_assets.json")
    sa = load(os.path.join(W, "safe_activity.json")) or {}
    for ch in sa.get("changes") or []:
        if ch.get("woke"):
            for tk in ch.get("governs") or []:
                c, t = split(tk); add(2, "admin Safe woke up", c, t, "%s executed after a long idle stretch" % ch.get("safe"), "find what it executed; an upgrade or a parameter change often follows", "safe_activity.json")
    for lab in sa.get("never_executed") or []:
        gov = sorted({tk for v in (sa.get("by_safe") or {}).values() if v.get("safe") == lab and not v.get("stale") for tk in v.get("governs") or []})
        for tk in gov:
            c, t = split(tk); add(3, "admin Safe never used", c, t, "%s has executed no transaction (nonce 0)" % lab, "an admin path nobody has exercised: confirm the signers can still act", "safe_activity.json")
    for k, v in ((load(os.path.join(W, "admin_probe.json")) or {}).get("by_target") or {}).items():
        if v.get("holders"):
            c, t = split(k); add(3, "admin role holder seen", c, t, "%d known contract(s) hold DEFAULT_ADMIN_ROLE; the list is not complete" % len(v["holders"]), "compare with the published admin-key score; holders cannot be listed on this contract", "admin_probe.json")


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--watch", default="watch"); ap.add_argument("--data", default="data"); ap.add_argument("--out", default="watch/review_queue.json"); ap.add_argument("--md", default="watch/review_queue.md")
    ap.add_argument("--overdue-days", type=float, default=2.0, help="a priority-1 item still here after this many days re-enters the alarm")
    a = ap.parse_args(); W, D = a.watch, a.data; items = []
    prev = {}   # since 2026-10-10 the queue remembers: an item keeps its first_seen from run to run, so its age is public and a stale one escalates
    try:
        for x in json.load(open(a.out)).get("items", []): prev[(x["kind"], x.get("chain"), str(x.get("target")).lower(), str(x["text"])[:120])] = x.get("first_seen")
    except Exception: pass  # noqa: BLE001 -- no previous queue: everything is new
    import re as _re
    def scrub(t): return _re.sub(r"0x[0-9a-fA-F]{40}", lambda m: m.group(0)[:6] + "\u2026" + m.group(0)[-4:], str(t))   # a signer named in a Safe event is a key: never whole in a public file
    seen = set()
    def add(prio, kind, chain, target, text, todo, source):
        k = (kind, chain, str(target).lower(), str(text)[:120])
        if k in seen: return   # the same operation can sit in two timelock records (watchlist and discovered, or an alias): once
        seen.add(k); items.append({"priority": prio, "kind": kind, "chain": chain, "target": target, "text": str(text)[:300], "todo": todo, "source": source})
    so = load(os.path.join(W, "second_opinion.json")) or {}; isrc = (load(os.path.join(W, "impl_sources.json")) or {}).get("by_target", {})
    for r in so.get("upgrades", []):
        src = isrc.get(r["chain"] + ":" + str(r["target"]).lower()) or {}
        add(1, "upgrade executed", r["chain"], r["target"], r.get("upgraded"), ("read what the new implementation does before trusting the score (the private pipeline's implementation check names selectors added and dropped)" + ("; its source is verified on Sourcify (%s)" % (src.get("name") or "unnamed") if src.get("verified") else "; NO verified source on Sourcify for the new implementation: read the bytecode, or find a verified source on the chain's explorer" if src.get("verified") is False else "")), "second_opinion.json upgrades")
    for r in so.get("changed", []): add(1, "admin read changed", r["chain"], r["target"], r.get("changed"), "confirm the new admin path and whether the score should move before the weekly push", "second_opinion.json changed")
    for r in so.get("results", []):
        if r.get("oracle_self"): continue
        if r.get("pending_admin"): add(1, "admin transfer in flight", r["chain"], r["target"], "%s designated (%s)" % (r["pending_admin"], r.get("pending_via")), "identify the designated admin; when it accepts, the admin read changes", "second_opinion.json pending_admin")
        for m in r.get("modules_detail") or []:
            if m.get("kind") == "eoa": add(1, "plain key as Safe module", r["chain"], r["target"], "module %s executes through the admin Safe alone" % m.get("address"), "this contradicts the multisig score outright: review the score", "second_opinion.json modules_detail")
            elif not (m.get("kind") == "zodiac-delay" and m.get("owner_is_the_safe")): add(2, "Safe module to identify", r["chain"], r["target"], "%s: %s, owned by %s" % (m.get("address"), m.get("kind"), "the Safe itself" if m.get("owner_is_the_safe") else (m.get("owner") or "unknown")), "say what this module does and who controls it; a module executes without the t-of-n", "second_opinion.json modules_detail")
        if r.get("guard_detail"): add(2, "Safe guard to identify", r["chain"], r["target"], "%s: %s, owned by %s" % (r["guard_detail"].get("address"), r["guard_detail"].get("kind"), r["guard_detail"].get("owner") or "unknown"), "say what this guard checks and who can change it", "second_opinion.json guard_detail")
        if r.get("disagree") and not r.get("acknowledged"): add(2, "second opinion disagrees", r["chain"], r["target"], r["disagree"], "review which role the scorer weighs; then either fix the score or write the note in data/second_opinion_acknowledged.json", "second_opinion.json disagreements")
        if r.get("modules") is None and r.get("kind") == "safe": add(3, "Safe modules not read this run", r["chain"], r["target"], "RPC did not answer getModulesPaginated", "nothing to do unless it repeats", "second_opinion.json")
    state_items(W, add)   # pause, other hands, balances, admin Safes, admin roles seen (mechanisms 80 to 91): alerts and pages had them, the queue that escalates an unanswered item did not
    for c in (load(os.path.join(W, "methodology.json")) or {}).get("changes", []): add(1, "methodology changed", c.get("chain"), None, "%s: %s -> %s on %d target(s)" % (c.get("name"), str(c.get("from"))[:12], str(c.get("to"))[:12], c.get("targets") or 0), "expected after a release of the scorer; otherwise a push by a key that should not hold the updater role", "methodology.json")
    for d in (load(os.path.join(W, "disputes.json")) or {}).get("disputes", []):
        if d.get("status") == "open": add(2, "dispute open", d.get("chain"), d.get("target"), "%s: %s" % (d.get("id"), d.get("claim")), "read the evidence in the issue, then set upheld / revised / withdrawn with the resolution in data/disputes.json", "disputes.json")
    for inv in (load(os.path.join(W, "disputes.json")) or {}).get("invalid", []): add(3, "dispute entry invalid", None, None, "%s: %s" % (inv.get("id"), inv.get("why")), "fix the entry in data/disputes.json", "disputes.json invalid")
    po = load(os.path.join(W, "pending_ops.json")) or {}; now = time.time()
    for tl in po.get("results", []):
        if str(tl.get("status", "ok")) != "ok": add(2 if tl.get("discovered") else 1, "timelock queue unread", tl.get("chain"), tl.get("address"), "%s: %s" % (tl.get("name"), str(tl.get("status"))[:120]), "find why the queue cannot be read (family getter, RPC range); until then queued operations there are not seen", "pending_ops.json")
        for op in tl.get("pending", []):
            if not fresh_enough(op.get("state"), op.get("ready_at"), now): continue   # executable for more than 7 days: not listed here either (lib/fresh_ops.py), whatever wrote the file
            kind_ = op.get("decoded") or ""; what_ = ((kind_ + ": ") if kind_ and kind_ not in ("unknown",) else "") + (op.get("signature") or op.get("selector") or "a call")
            if op.get("state") == "ready" or (op.get("ready_at") and op["ready_at"] - now < 48 * 3600 and op["ready_at"] > now): add(1, "queued operation executable" + ("" if op.get("state") == "ready" else " within 48 h"), tl.get("chain"), op.get("target"), "%s via %s" % (what_, tl.get("name")), "read the call before it lands", "pending_ops.json")
            elif kind_ in ("upgrade", "authority change", "pause"): add(2, "queued %s waiting" % kind_, tl.get("chain"), op.get("target"), "%s via %s, executable %s" % (what_, tl.get("name"), time.strftime("%Y-%m-%d", time.gmtime(op["ready_at"])) if op.get("ready_at") else "later"), "an authority change sits in the queue: read it before its day", "pending_ops.json")
    ack = (load(os.path.join(D, "digest_acknowledged.json")) or {}).get("safe_changes", {})
    for eco in (load(os.path.join(W, "safe_changes.json")) or {}).get("results", []):
        for e in eco.get("events", []):
            tx = str(e.get("tx") or ""); noted = next((v for k, v in ack.items() if tx.startswith(k) or k.startswith(tx[:10])), None) if tx else None
            if not noted: add(1, "Safe %s" % e.get("name"), eco.get("ecosystem"), e.get("safe"), "%s %s (%s)" % (e.get("name"), scrub(e.get("value")) if str(e.get("name")) in ("AddedOwner", "RemovedOwner") else e.get("value"), ", ".join(e.get("groups") or [])), "who is the new signer / what changed; then note it in data/digest_acknowledged.json", "safe_changes.json")
    cov = load(os.path.join(W, "coverage.json")) or {}
    for key, c in (cov.get("chains") or {}).items():
        for b in c.get("blind_spots", []):
            if "timelock" in b and "not watched" in b: add(3, "timelock queues not watched", key, None, b, "scripts/pending_ops_discovered.py covers them from the next run if their family getter answers", "coverage.json")
    now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()); now_s = time.time()
    import calendar
    for x in items:
        x["first_seen"] = prev.get((x["kind"], x.get("chain"), str(x.get("target")).lower(), str(x["text"])[:120])) or now_iso
        try: x["age_days"] = round((now_s - calendar.timegm(time.strptime(x["first_seen"], "%Y-%m-%dT%H:%M:%SZ"))) / 86400, 1)
        except ValueError: x["age_days"] = 0.0
        x["overdue"] = bool(x["priority"] == 1 and x["age_days"] > a.overdue_days)
    items.sort(key=lambda x: (x["priority"], -x["age_days"], x["kind"], str(x["chain"]), str(x["target"])))
    counts = {str(p): sum(1 for x in items if x["priority"] == p) for p in (1, 2, 3)}
    overdue = [x for x in items if x["overdue"]]; oldest = max((x["age_days"] for x in items), default=0.0)
    out = {"generated_utc": now_iso, "total": len(items), "by_priority": counts, "overdue": len(overdue), "overdue_days": a.overdue_days, "oldest_days": oldest, "items": items,
           "what": "what a person must look at, from the files of this run, ranked: 1 something happened (read before trusting the score), 2 decide (disagreement, module or guard to identify, open dispute, unread queue), 3 coverage to extend; items a person already reviewed (acknowledged files, resolved disputes) are left out; written by scripts/review_queue.py after every run"}
    tmp = a.out + ".tmp"; json.dump(out, open(tmp, "w"), indent=1); os.replace(tmp, a.out)
    if a.md:
        md = ["## Needs a person, %s: %d item(s) (%s)%s" % (out["generated_utc"], len(items), ", ".join("priority %s: %s" % kv for kv in counts.items()), ("; oldest %.1f d" % oldest) if items else ""), ""]
        if overdue: md += ["### Overdue: %d priority-1 item(s) waiting for more than %g day(s), back in the alarm" % (len(overdue), a.overdue_days)] + ["- **%s** %s %s (%.1f d): %s" % (x["kind"], x["chain"] or "", x["target"] or "", x["age_days"], x["text"]) for x in overdue] + [""]
        for p, title in ((1, "Something happened: read before trusting the score"), (2, "Decide"), (3, "Coverage to extend")):
            sel = [x for x in items if x["priority"] == p]
            if sel: md += ["### %s (%d)" % (title, len(sel))] + ["- **%s** %s %s (%.1f d): %s. To do: %s. (%s)" % (x["kind"], x["chain"] or "", x["target"] or "", x["age_days"], x["text"], x["todo"], x["source"]) for x in sel] + [""]
        open(a.md, "w").write("\n".join(md))
    try:   # the daily report is written once a day: drop from it, at every run, the lines of operations the queue no longer lists (lib/prune_digest.py); a failure here never stops the run
        from lib.prune_digest import prune_digest
        done = prune_digest(W)
        if done: print("daily report: lines of operations no longer listed dropped from " + ", ".join(done))
    except Exception as e:  # noqa: BLE001
        print("daily report not pruned (%s)" % type(e).__name__)
    print("review queue: %d item(s): %s; oldest %.1f d; %d overdue (priority 1 for more than %g d)" % (len(items), ", ".join("priority %s: %s" % kv for kv in counts.items()), oldest, len(overdue), a.overdue_days))
    for x in items[:12]: print("  [%d] %s %s %s: %s" % (x["priority"], x["kind"], x["chain"] or "", (x["target"] or "")[:10], x["text"][:90]))


if __name__ == "__main__":
    main()
