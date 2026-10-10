#!/usr/bin/env python3
"""Everything the watch knows about one contract, in words, from the repository alone: no site, no network, no key.

    python3 scripts/dossier.py base 0xbbbbbbbbbb9cc5e90e3b3af64bdaf62c37eeffcb
    python3 scripts/dossier.py base-sepolia 0xbbbb... --watch watch

The site joins a dozen watch files into one page per contract; this joins the same files for someone who has cloned the repository (a reviewer, a script, an agent). Same rule
as every page: what the watch could not read is said to be unread, never shown as nothing. A source file that is missing gives a line "not read", and a record marked stale is
said to be stale. Exit code 2 when the contract is not tracked.
"""
import argparse, glob, json, os, sys, time

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from evaluate_rules import WATCH_SLUGS, LABEL, PENDING_CHAIN, norm  # noqa: E402
from badges_req import requirements  # noqa: E402

NAMES = {"adminKeyScore": "admin key", "multisigScore": "multisig", "timelockScore": "timelock", "oracleAuthorityScore": "price feed", "crossExposureScore": "shared control"}


def clean_name(value, limit=80):
    """A name that comes from a third party (a DefiLlama protocol name) made safe to print into a line of text that an agent or a person reads: control characters, line breaks and invisible formatting
    characters (zero-width, right-to-left overrides) removed, runs of spaces collapsed, cut at `limit` characters. A hostile name cannot add a line, move the text or pose as an instruction."""
    import unicodedata
    t = "".join(" " if (unicodedata.category(c) in ("Cc", "Zl", "Zp") or c in "\t\r\n") else ("" if unicodedata.category(c) == "Cf" else c) for c in str(value if value is not None else ""))
    t = " ".join(t.split())
    return t if len(t) <= limit else t[:limit - 1] + "…"


def clean_lines(lines, limit=600):
    """The last pass over text that is about to be printed. Text read from the files includes strings that strangers control: an ERC-20 symbol() on chain, the text of a public dispute, a revert
    message. Each line loses its control characters and invisible formatting characters, a line break inside an element becomes a space, and a line is cut at `limit` characters. Spaces are
    kept (the tour aligns columns). Cleaning each line here, not each field where it is printed, covers a field added later, and a terminal never receives an escape sequence from a contract."""
    import unicodedata
    def one(l):
        t = "".join(" " if c in "\n\r\t" or unicodedata.category(c) in ("Zl", "Zp") else ("" if unicodedata.category(c) in ("Cc", "Cf") else c) for c in l)
        return t if len(t) <= limit else t[:limit - 1] + "…"
    return [one(l) if l else l for l in lines]


def load(p):
    try: return json.load(open(p))
    except Exception: return None  # noqa: BLE001 -- a missing or unreadable file is reported as "not read" below


def utf8_stdout():
    """These commands print '…' (a shortened address) and '**'. A terminal or a pipe with a legacy encoding (a Windows code page, an ASCII locale in a minimal container) would stop them with a
    UnicodeEncodeError: ask for UTF-8 and replace what cannot be shown. A stream that cannot be reconfigured (a test's StringIO) is left alone."""
    try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError, OSError): pass


def day(ts):
    try: return time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(int(ts)))
    except (TypeError, ValueError): return "an unknown time"


def chain_key(name):
    """'base', 'base-sepolia' or 'Base' -> 'base'."""
    n = str(name).strip().lower()
    if n in WATCH_SLUGS: return WATCH_SLUGS[n]
    if n in LABEL: return n
    for k, v in LABEL.items():
        if v.lower() == n: return k
    return None


def build(W, chain, address):
    """The dossier as a list of lines, or None when the contract is not tracked."""
    key = chain_key(chain)
    if not key: return None
    addr = norm(address); ka = key + ":" + addr; target = None; slug = None; oname = None
    for f in sorted(glob.glob(os.path.join(W, "scores", "*.json"))):
        s = os.path.basename(f)[:-5]; d = load(f) or {}
        if WATCH_SLUGS.get(s) == key or (key == "solana" and d.get("kind") == "solana"):
            for t in d.get("targets", []):
                if norm(t.get("target")) == addr: target, slug, oname = t, s, d.get("name")
    if not target: return None
    so, tvl, held, pz, sr, sa, ap, po, al, dp = (load(os.path.join(W, n)) for n in ("second_opinion.json", "tvl.json", "held_assets.json", "pause_state.json", "side_roles.json", "safe_activity.json", "admin_probe.json", "pending_ops.json", "alerts.json", "disputes.json"))
    m = ((tvl or {}).get("matched") or {}).get(ka.lower()) or {}; out = []   # lower-case keys, a Solana (base58) address included
    out += ["# %s on %s" % (clean_name(m.get("name")) or (addr[:6] + "…" + addr[-4:]), LABEL.get(key, key)), "", "Contract `%s`. Read from the files of the watch run of %s." % (addr, (load(os.path.join(W, "latest.json")) or {}).get("run_utc") or "an unknown run"), ""]
    sc = target
    out += ["## Score", "- composite **%s/100**%s%s" % (sc.get("compositeScore"), (" (was %s)" % sc["previousComposite"]) if sc.get("previousComposite") not in (None, "") and sc.get("previousComposite") != sc.get("compositeScore") else "", ", **stale**: the oracle has not pushed it within its maxStaleness" if sc.get("stale") else ""),
            "- admin key %s, multisig %s, timelock %s, price feed %s, shared control %s" % tuple(sc.get(k, "?") for k in ("adminKeyScore", "multisigScore", "timelockScore", "oracleAuthorityScore", "crossExposureScore")),
            "- last pushed on-chain %s" % day(sc.get("lastUpdated")), ""]
    reqs = requirements(sc); out += ["## What the score asks for", "- %d of %d requirements met" % (sum(1 for _l, ok, _f, _v, _t in reqs if ok), len(reqs))]
    for label, ok, field, value, need in reqs:
        out += ["- %s: %s (%s %s, %s or more needed)" % ("not read" if ok is None else "met" if ok else "**not met**", label, NAMES.get(field, field), "?" if value is None else value, need)]
    out += [""]
    out += ["## Who controls it"]
    r = next((x for x in (so or {}).get("results", []) if x.get("chain") == key and norm(x.get("target")) == addr), None) if so else None
    if so is None: out += ["- not read: second_opinion.json is missing"]
    elif not r: out += ["- the independent reader has no record for this contract"]
    else:
        out += ["- %s" % (r.get("posture") or "kind: %s" % r.get("kind"))]
        if r.get("kind") in ("unreadable", "native"): out += ["- the independent reader cannot classify the admin here: %s" % (r.get("why") or r.get("kind"))]
        if r.get("keys_to_act") is not None: out += ["- %s key(s) to act; %s lost keys would freeze it" % (r.get("keys_to_act"), r.get("keys_lost_to_freeze"))]
        if r.get("disagree"): out += ["- **the independent reader disagrees with the score%s**: %s" % (" (reviewed: %s)" % r["acknowledged"] if r.get("acknowledged") else "", r["disagree"])]
        elif r.get("kind") not in ("unreadable", "native"): out += ["- consistent with the published admin-key score"]
        ex = r.get("exposure") if isinstance(r.get("exposure"), dict) else next((e for e in (so or {}).get("exposure", []) if e.get("chain") == key and norm(e.get("target")) == addr), None)
        if ex: out += ["- to move the money: %s key(s)%s; money behind one key about $%s (%s)" % (ex.get("keys_to_move"), (", %s h to react" % ex["react_hours"]) if ex.get("react_hours") is not None else "", "{:,.0f}".format(ex["money_per_key_usd"]) if ex.get("money_per_key_usd") is not None else "?", ex.get("money_source"))]
        if r.get("pending_admin"): out += ["- **an admin transfer is in flight**: %s designated" % r["pending_admin"]]
    ob = [v for v in ((sa or {}).get("by_safe") or {}).values() if ka in (v.get("governs") or []) and not v.get("stale")]
    if sa is None: out += ["- admin Safe activity not read: safe_activity.json is missing"]
    for v in sorted(ob, key=lambda v: str(v.get("safe"))):
        out += ["- the Safe %s has %s" % (str(v.get("safe")).split(":", 1)[-1], "never executed a transaction (nonce 0)" if v.get("never_executed") else "executed %s transaction(s); this watch has read that number since %s" % (v.get("nonce"), str(v.get("idle_since"))[:10]))]
    pr = ((ap or {}).get("by_target") or {}).get(ka)
    if pr and pr.get("holders"): out += ["- the admin role is held by %s (asked %d known holders; this is proof of those, not a complete list)" % (", ".join("%s `%s`" % (h.get("kind"), h.get("holder")) for h in pr["holders"]), pr.get("probed") or 0)]
    out += [""]
    out += ["## Money"]
    h = ((held or {}).get("by_target") or {}).get(ka.lower())
    if m.get("tvl") is not None: out += ["- $%s of %s TVL attached (DefiLlama)%s" % ("{:,.0f}".format(m["tvl"]), clean_name(m.get("name")), "" if m.get("scope") != "chain" else ", this chain only")]
    if h and h.get("held_usd") is not None: out += ["- the contract holds about $%s of %s by its own account%s" % ("{:,.0f}".format(h["held_usd"]), h.get("symbol"), " (stale)" if h.get("stale") else "")]
    if h and h.get("vanished"): out += ["- **it reported its balance at an earlier run and no longer does**"]
    if m.get("tvl") is None and not (h and h.get("held_usd") is not None): out += ["- no money figure: no DefiLlama protocol and no totalAssets() answer"]
    out += [""]
    out += ["## State"]
    z = ((pz or {}).get("by_target") or {}).get(ka)
    if pz is None: out += ["- pause: not read (pause_state.json is missing)"]
    elif not z: out += ["- pause: this contract answers neither paused() nor isPaused(), so a pause is not seen"]
    elif z.get("stale"): out += ["- pause: the last answer is stale"]
    else: out += ["- %s" % ("**paused** (%s answers true)" % z.get("via") if z.get("paused") else "not paused (%s answers false)" % z.get("via"))]
    s = ((sr or {}).get("by_target") or {}).get(ka)
    if sr is None: out += ["- other hands: not read (side_roles.json is missing)"]
    elif not s: out += ["- other hands: no pauser, guardian or curator getter answers on this contract"]
    else:
        for n, x in (s.get("roles") or {}).items(): out += ["- %s is %s `%s`%s" % (n, {"safe": "a Safe %s-of-%s" % (x.get("threshold"), x.get("owners")), "eoa": "a plain key", "timelock": "a timelock", "contract": "a contract"}.get(x.get("kind"), str(x.get("kind"))), x.get("holder"), " (stale)" if x.get("stale") else "")]
        for n, x in (s.get("pending") or {}).items(): out += ["- **announced**: %s" % ("a new guardian (%s)" % x.get("kind") if n == "guardian" else "the delay goes to %s h%s" % (int(x.get("seconds") or 0) // 3600, " (shorter)" if x.get("shorter") else "")) + (" from %s" % day(x["valid_at"]) if x.get("valid_at") else "")]
    out += [""]
    out += ["## Queue and alerts"]
    ops = []
    for res in (po or {}).get("results", []):
        if PENDING_CHAIN.get(res.get("chain"), res.get("chain")) != key: continue
        for op in (res.get("pending") or []) + (res.get("recent") or []):
            if norm(op.get("target")) == addr: ops.append((op, res.get("name")))
    if po is None: out += ["- queue: not read (pending_ops.json is missing)"]
    elif not ops: out += ["- nothing queued against this contract in the timelocks the watch reads"]
    for op, name in sorted(ops, key=lambda x: x[0].get("ready_at") or x[0].get("eta") or 0):
        out += ["- queued in %s: %s, executable from %s (%s)" % (name, (op.get("signature") or "").split("(")[0] or op.get("selector") or "a call", day(op.get("ready_at") or op.get("eta")), op.get("state") or ("still queued" if op.get("still_queued") else "cleared"))]
    mine = [x for x in (al or {}).get("active", []) if norm(x.get("target")) == addr and (x.get("chain") == oname or str(oname).startswith(str(x.get("chain")) + " ("))]   # an alert names the chain as the oracle does, with or without its network in brackets
    if al is None: out += ["- alerts: not read (alerts.json is missing)"]
    elif not mine: out += ["- no rule is firing on this contract"]
    for x in mine: out += ["- **%s alert**: %s (since %s)" % (x.get("severity"), x.get("rule"), x.get("first_seen"))]
    dd = [x for x in (dp or {}).get("disputes", []) if x.get("chain") == key and norm(x.get("target")) == addr]
    for x in dd: out += ["- dispute %s: %s" % (x.get("id"), x.get("status"))]
    out += ["", "## History"]
    ss = load(os.path.join(W, "score_series.json"))
    pts = (((ss or {}).get("series") or {}).get(ka)) or []
    if ss is None: out += ["- score over time: not read (score_series.json is missing)"]
    elif not pts: out += ["- score over time: no point recorded yet"]
    else: out += ["- score over time (last %d of %d points): %s" % (min(8, len(pts)), len(pts), ", ".join("%s %s (%s)" % (str(p.get("t"))[:10], p.get("composite"), p.get("from")) for p in pts[-8:]))]
    evs, ev_ok = [], os.path.exists(os.path.join(W, "events.jsonl"))
    if ev_ok:
        for l in open(os.path.join(W, "events.jsonl"), encoding="utf-8", errors="replace"):
            try: e = json.loads(l)
            except ValueError: continue
            if norm(e.get("target")) == addr and e.get("oracle") in (oname, slug, key): evs.append(e)
    if not ev_ok: out += ["- events: not read (events.jsonl is missing)"]
    elif not evs: out += ["- events: none recorded for this contract"]
    for e in sorted(evs, key=lambda e: str(e.get("run_utc")))[-8:]:
        k = e.get("kind"); what = ("admin changed (independent read): %s" % str(e.get("text"))[:160]) if k == "admin_change" else ("**upgrade executed**: %s" % str(e.get("text"))[:160]) if k == "upgraded" else str(e.get("text"))[:160] if str(k).startswith("dispute_") else ("%s moved: %s %s to %s" % (e.get("label") or "score", e.get("field"), e.get("before"), e.get("after"))) if k == "move" else "alarm: %s" % str(e.get("text"))[:160]
        out += ["- %s %s" % (str(e.get("run_utc"))[:10], what)]
    past = [x for x in (al or {}).get("history", []) if norm(x.get("target")) == addr and (x.get("chain") == oname or str(oname).startswith(str(x.get("chain")) + " ("))]
    for x in sorted(past, key=lambda x: str(x.get("last_seen")))[-5:]: out += ["- alert %s (%s): first seen %s, last seen %s, %s run(s)" % (x.get("rule"), x.get("severity"), str(x.get("first_seen"))[:10], str(x.get("last_seen"))[:10], x.get("times"))]
    out += ["", "Every line comes from a file under `watch/`; `watch/API.md` says what each one is."]
    return clean_lines(out)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("chain"); ap.add_argument("address"); ap.add_argument("--watch", default="watch"); a = ap.parse_args(); utf8_stdout()
    lines = build(a.watch, a.chain, a.address)
    if lines is None:
        print("not tracked: %s %s (chains: %s)" % (a.chain, a.address, ", ".join(sorted(LABEL)))); sys.exit(2)
    print("\n".join(lines))


if __name__ == "__main__":
    main()
