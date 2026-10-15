#!/usr/bin/env python3
"""One Atom feed per tracked contract, watch/feed/<oracle-slug>/<address>.xml: its score moves (events.jsonl), the alerts that
fired on it (alerts.json history) and the operations queued against it (pending_ops.json). A feed reader subscribed to one
contract sees only that contract. Written only when the content changes, so a run with nothing new commits nothing.

    python3 scripts/feeds_per_target.py --scores watch/scores --events watch/events.jsonl --alerts watch/alerts.json --pending watch/pending_ops.json --out watch/feed
"""
import argparse, glob, hashlib, html, json, os, re

from watch_location import RAW   # the feeds live on the watch-data branch
from evaluate_rules import detail_text, LABEL

SITE = "https://realspap.github.io/oracle/"   # the numbers of a balance alert, in words (same text as the notification and the alerts feed)


def norm(a): return (a or "").lower()


def entry(title, eid, updated, summary, link):
    return ('<entry><title>%s</title><id>urn:aro:%s</id><updated>%s</updated><summary>%s</summary><link href="%s"/></entry>'
            % (html.escape(title), eid, updated, html.escape(summary), html.escape(link)))


def protocol_feed(pslug, name, members, self_url):
    """One Atom feed for a whole protocol (since 2026-10-10): the entries of the feeds of all its tracked contracts, newest first, each titled with its chain and shortened address. members: [(chain key,
    address, entries [(when, entry xml)], lastUpdated, score, stale)]. Entry ids are prefixed with the contract so that two contracts can share an operation without the reader dropping one."""
    allx, seen = [], set()
    for ck, addr, es, _lu, _sc, _st in members:
        tag = "%s %s" % (LABEL.get(ck, ck), addr[:6] + "…" + addr[-4:])
        for when, x in es:
            x = x.replace("<title>", "<title>[%s] " % html.escape(tag), 1).replace("<id>urn:aro:", "<id>urn:aro:%s:%s:" % (ck, addr), 1)
            i = x.split("<id>")[1].split("</id>")[0]
            if i not in seen: seen.add(i); allx.append((when, x))
    allx.sort(key=lambda x: x[0] or "", reverse=True)
    lus = [m[3] for m in members if m[3]]; scores = [m[4] for m in members if isinstance(m[4], (int, float))]; chains = sorted({m[0] for m in members})
    updated = allx[0][0] if allx else (__import__("time").strftime("%Y-%m-%dT%H:%M:%SZ", __import__("time").gmtime(int(max(lus)))) if lus else "1970-01-01T00:00:00Z")
    feed = ['<?xml version="1.0" encoding="utf-8"?>', '<feed xmlns="http://www.w3.org/2005/Atom">',
            "<title>%s: authority risk, %d contract(s) on %d chain(s)</title>" % (html.escape(str(name)), len(members), len(chains)), "<author><name>Authority Risk Oracle</name></author>",
            '<link href="%s"/>' % html.escape(SITE + "#chain=all&q=" + str(pslug)), '<link rel="self" href="%s"/>' % html.escape(self_url), "<id>urn:aro:feed:protocol:%s</id>" % pslug, "<updated>%s</updated>" % updated,
            "<subtitle>scores %s to %s, %d stale; every move, alert and queued operation on its tracked contracts</subtitle>" % (min(scores) if scores else "?", max(scores) if scores else "?", sum(1 for m in members if m[5]))]
    return "\n".join(feed + [x for _w, x in allx[:50]] + ["</feed>"]) + "\n"


from lib.fresh_ops import fresh_enough, due_at  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scores", default="watch/scores"); ap.add_argument("--events", default="watch/events.jsonl")
    ap.add_argument("--alerts", default="watch/alerts.json"); ap.add_argument("--pending", default="watch/pending_ops.json")
    ap.add_argument("--out", default="watch/feed"); ap.add_argument("--tvl", default="watch/tvl.json", help="groups the contracts by DefiLlama protocol for the protocol feeds"); a = ap.parse_args()
    events = []
    if os.path.exists(a.events):
        for l in open(a.events):
            try: events.append(json.loads(l))
            except ValueError: continue
    alerts = json.load(open(a.alerts)).get("history", []) if os.path.exists(a.alerts) else []
    pend = json.load(open(a.pending)) if os.path.exists(a.pending) else {}
    # the same address can be tracked on two chains (6 today): every source is matched on chain AND address
    PENDING_CHAIN = {"ethereum": "ethereum-l1", "arbitrum": "arbitrum", "base": "base", "robinhood": "robinhood", "plasma": "plasma", "tempo": "tempo", "monad": "monad", "hyperliquid": "hyperliquid", "solana": "solana"}
    ops = []
    for r in (pend.get("results") or []):
        for op in r.get("pending", []) + r.get("recent", []):
            if (op.get("state") or op.get("still_queued")) and not fresh_enough(op.get("state"), due_at(op), __import__("time").time()): continue   # executable for more than 7 days: not listed (lib/fresh_ops.py)
            ops.append(dict(op, _chain=PENDING_CHAIN.get(r.get("chain"), r.get("chain"))))
    def chain_key(slug): return max([k for k in PENDING_CHAIN.values() if slug.startswith(k)], key=len, default=slug)   # "ethereum-l1-sepolia" -> "ethereum-l1"
    written = unchanged = 0
    matched = (json.load(open(a.tvl)).get("matched") if os.path.exists(a.tvl) else None) or {}; groups = {}   # protocol slug -> {name, members}
    for f in sorted(glob.glob(os.path.join(a.scores, "*.json"))):
        d = json.load(open(f)); slug = os.path.basename(f)[:-5]; name = d.get("name", slug); ck = chain_key(slug)
        def same_chain(label): return label == name or name.startswith(str(label) + " (")   # an alert says "Ethereum L1", the scores file "Ethereum L1 (Sepolia)"
        os.makedirs(os.path.join(a.out, slug), exist_ok=True)
        for t in d.get("targets", []):
            addr = t["target"]; n = norm(addr); link = SITE + "#chain=all&q=" + addr
            es = []
            for e in events:
                if norm(e.get("target")) == n and e.get("oracle") in (name, slug, ck):   # the watch names the oracle, the independent reader names the chain key
                    if e.get("kind") == "admin_change":
                        es.append((e["run_utc"], entry("admin changed (independent read)", "adminchange:" + hashlib.sha1(json.dumps(e, sort_keys=True).encode()).hexdigest()[:16], e["run_utc"], str(e.get("text"))[:400], link)))
                    elif e.get("kind") == "upgraded":
                        es.append((e["run_utc"], entry("UPGRADE EXECUTED (implementation changed)", "upgrade:" + hashlib.sha1(json.dumps(e, sort_keys=True).encode()).hexdigest()[:16], e["run_utc"], str(e.get("text"))[:400], link)))
                    elif str(e.get("kind", "")).startswith("dispute_"):
                        es.append((e["run_utc"], entry(str(e.get("text"))[:140], "dispute:" + hashlib.sha1(json.dumps(e, sort_keys=True).encode()).hexdigest()[:16], e["run_utc"], str(e.get("text"))[:400], link)))
                    elif e.get("kind") == "move":
                        es.append((e["run_utc"], entry(("%s added at %s" % (e.get("label") or addr[:10], e.get("after"))) if e.get("before") is None else ("%s moved: %s %s -> %s" % (e.get("label") or addr[:10], e.get("field"), e.get("before"), e.get("after"))),
                                                        "move:" + hashlib.sha1(json.dumps(e, sort_keys=True).encode()).hexdigest()[:16], e["run_utc"],
                                                        ("%s on %s was added to the watch at %s" % (e.get("label") or addr, name, e.get("after"))) if e.get("before") is None else ("%s on %s: %s went from %s to %s" % (e.get("label") or addr, name, e.get("field"), e.get("before"), e.get("after"))), link)))
                    else:
                        es.append((e["run_utc"], entry("alarm", "alarm:" + hashlib.sha1(json.dumps(e, sort_keys=True).encode()).hexdigest()[:16], e["run_utc"], str(e.get("text"))[:400], link)))
            for x in alerts:
                if norm(x.get("target")) == n and same_chain(x.get("chain")):
                    # dated at its first appearance, not at last_seen: an alert still active moved last_seen and its counter every run, so six feeds were rewritten every 6 hours with nothing new (seen 10/10)
                    es.append((x.get("first_seen") or x.get("last_seen"), entry("%s alert: %s" % (x.get("severity"), x.get("rule")), "alert:" + hashlib.sha1(str(x.get("key")).encode()).hexdigest()[:16],
                                                                               x.get("first_seen") or x.get("last_seen"), "%s%s, first seen %s" % (x.get("rule"), (" (" + detail_text(x) + ")") if detail_text(x) else "", x.get("first_seen")), link)))
            for op in ops:
                when = op.get("ready_at") or op.get("eta") or op.get("queued_at")   # OZ timelocks say ready_at + state, Compound-style ones eta + still_queued; a cleared one may only keep queued_at
                if norm(op.get("target")) == n and when and op.get("_chain") == ck:
                    ready = __import__("time").strftime("%Y-%m-%dT%H:%M:%SZ", __import__("time").gmtime(int(when))); state = op.get("state") or ("still queued" if op.get("still_queued") else "cleared")
                    fn = (op.get("signature") or "").split("(")[0] or op.get("selector") or "a call"
                    es.append((ready, entry("queued: %s (%s)" % (fn, state), "op:" + str(op.get("id") or "")[:18] + ":" + str(op.get("index", 0)),
                                            ready, "%s against this contract, executable from %s, %s" % (fn, ready, state), link)))
            es.sort(key=lambda x: x[0] or "", reverse=True)
            seen_ids, uniq = set(), []   # one entry per id (an operation seen as pending and as recent keeps its newest state only): a reader dedupes by id, a validator rejects duplicates
            for x in es:
                i = x[1].split("<id>")[1].split("</id>")[0]
                if i not in seen_ids: seen_ids.add(i); uniq.append(x)
            es = uniq
            m_ = matched.get(ck + ":" + addr.lower()) or {}
            if m_.get("slug"): groups.setdefault(m_["slug"], {"name": m_.get("name"), "members": []})["members"].append((ck, addr, es, t.get("lastUpdated"), t.get("compositeScore"), bool(t.get("stale"))))
            # a feed with nothing yet dates from the last push of the score, not from the read: readAt changes every run and would rewrite all 179 files each time
            updated = es[0][0] if es else (t.get("lastUpdated") and __import__("time").strftime("%Y-%m-%dT%H:%M:%SZ", __import__("time").gmtime(int(t["lastUpdated"]))))
            feed = ['<?xml version="1.0" encoding="utf-8"?>', '<feed xmlns="http://www.w3.org/2005/Atom">',
                    "<title>%s on %s: authority risk</title>" % (html.escape(addr), html.escape(name)), "<author><name>Authority Risk Oracle</name></author>",
                    '<link href="%s"/>' % html.escape(link), '<link rel="self" href="' + RAW + 'feed/%s/%s.xml"/>' % (slug, addr),
                    "<id>urn:aro:feed:%s:%s</id>" % (slug, n), "<updated>%s</updated>" % (updated or "1970-01-01T00:00:00Z"),
                    "<subtitle>score %s/100, stale %s; every move, alert and queued operation on this contract</subtitle>" % (t.get("compositeScore"), "yes" if t.get("stale") else "no")]
            feed += [e for _, e in es[:50]] + ["</feed>"]
            text = "\n".join(feed) + "\n"; path = os.path.join(a.out, slug, addr + ".xml")
            if os.path.exists(path) and open(path).read() == text: unchanged += 1; continue
            tmp = path + ".tmp"; open(tmp, "w").write(text); os.replace(tmp, path); written += 1
    pw = pu = 0; pdir = os.path.join(a.out, "protocol"); os.makedirs(pdir, exist_ok=True)
    for pslug, g in sorted(groups.items()):
        fname = re.sub(r"[^a-z0-9._-]", "-", str(pslug).lower()) + ".xml"; path = os.path.join(pdir, fname)
        text = protocol_feed(pslug, g["name"] or pslug, g["members"], RAW + "feed/protocol/" + fname)
        if os.path.exists(path) and open(path).read() == text: pu += 1; continue
        tmp = path + ".tmp"; open(tmp, "w").write(text); os.replace(tmp, path); pw += 1
    print("per-target feeds: %d written, %d unchanged; protocol feeds: %d written, %d unchanged" % (written, unchanged, pw, pu))


if __name__ == "__main__":
    main()
