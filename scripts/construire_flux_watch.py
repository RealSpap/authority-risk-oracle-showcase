#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""JSON Feed 1.1 of the AUTHORITY CHANGES the Watch saw: one entry per `admin_change` or `upgraded` event of the hash-chained journal `events.jsonl`.
Static, no network: reads one local file, writes one file. No score, no judgement: the text of the event as the Watch wrote it (root signers already shortened). The ids are stable (the `seq` line of the journal).
  python3 construire_flux_watch.py events.jsonl authority-changes.json [--scores DIR] [--limit 100]   # writes the feed; --scores gives the network and chain ID of each target
  python3 construire_flux_watch.py --check authority-changes.json                          # rereads a feed: shape, unique ids, order, kinds
  python3 construire_flux_watch.py --selftest
WIRING (done by whoever holds the Watch job, not by this script): after the line that writes `feed.xml`, run the first command on `events.jsonl` of the watch-data branch, to `authority-changes.json` at the root of that branch."""
import json, os, re, sys, tempfile
KINDS = {"admin_change": "Admin changed", "upgraded": "Implementation upgraded"}
SITE = "https://realspap.github.io/oracle/"
FEED = "https://raw.githubusercontent.com/RealSpap/authority-risk-oracle-showcase/watch-data/authority-changes.json"


def networks(scores_dir):
    """{(stem of the oracle file, target address): "Network name (chain ID N)" or "Network name"} from the per-oracle files the Watch writes (target_network, target_chain_id). The same address can be followed on several networks (one file each), so the oracle file is part of the key. A Solana address keeps its case, an EVM address is lower case."""
    out = {}
    for f in sorted(os.listdir(scores_dir)) if scores_dir and os.path.isdir(scores_dir) else []:
        if not f.endswith(".json"): continue
        try: d = json.load(open(os.path.join(scores_dir, f), encoding="utf-8"))
        except (OSError, ValueError): continue
        for t in (d.get("targets") or []) if isinstance(d, dict) else []:
            if isinstance(t, dict) and t.get("target") and t.get("target_network"):
                cid = t.get("target_chain_id"); a = str(t["target"]); a = a.lower() if a.startswith("0x") else a
                out[(f[:-5], a)] = "%s (chain ID %d)" % (t["target_network"], cid) if isinstance(cid, int) else str(t["target_network"])
    return out


def network_of(nets, oracle, target):
    """The network of the target of an event: the oracle of the event names the file (`base` -> `base-sepolia`), and only that file is looked in. With no file for that oracle, an address that all files agree on is used; an address that two networks share is NOT guessed: None."""
    a = str(target or ""); a = a.lower() if a.startswith("0x") else a
    stems = sorted({k[0] for k in nets})
    own = [s for s in stems if oracle and (s == oracle or s.startswith(oracle + "-"))]
    cand = {nets[(s, a)] for s in own if (s, a) in nets}
    if not cand and not own: cand = {v for (s, t), v in nets.items() if t == a}
    return next(iter(cand)) if len(cand) == 1 else None


def clean(text):
    """The Watch ends some texts with a clause about its score ("; the score reads who may upgrade, ..."): the feed carries facts only, so every clause that mentions a score is dropped."""
    parts = [x for x in re.split(r";\s+", text) if "score" not in x.lower()]
    return "; ".join(parts)


def build(lines, limit=100, nets=None):
    nets = nets or {}
    ev = [json.loads(l) for l in lines if l.strip()]
    ch = [e for e in ev if e.get("kind") in KINDS]
    ch.sort(key=lambda e: -e["seq"])
    items = []
    for e in ch[:limit]:
        who = e.get("label") or (e.get("target") or "")
        short = who if len(who) <= 24 else who[:10] + "\u2026" + who[-6:]
        net = network_of(nets, e.get("oracle"), e.get("target"))
        where = net or "network not determined from the target files of this run"
        body = clean(e.get("text") or KINDS[e["kind"]]) or KINDS[e["kind"]]
        items.append({"id": "tag:realspap.github.io,2026:watch:seq-%d" % e["seq"], "url": SITE + "#chain=all&q=" + (e.get("target") or ""), "title": "%s: %s on %s" % (KINDS[e["kind"]], short, net or "a network not determined from the target files of this run"),
                      "content_text": "Network: %s. %s" % (where, body), "date_published": e["run_utc"], "tags": [e["kind"], str(e.get("oracle", ""))], "_aro": {"seq": e["seq"], "kind": e["kind"], "network": net}})
    return {"version": "https://jsonfeed.org/version/1.1", "title": "Authority Risk Oracle: authority changes", "home_page_url": SITE, "feed_url": FEED,
            "description": "Each time the Watch reads a changed admin or a new implementation on a followed contract. Facts only, no score. Source: the hash-chained journal events.jsonl.", "language": "en", "items": items}


def check(feed):
    assert feed["version"] == "https://jsonfeed.org/version/1.1" and feed["title"] and isinstance(feed["items"], list)
    ids = [i["id"] for i in feed["items"]]; assert len(ids) == len(set(ids)), "ids en double"
    seqs = [i["_aro"]["seq"] for i in feed["items"]]; assert seqs == sorted(seqs, reverse=True), "ordre"
    for i in feed["items"]:
        assert i["_aro"]["kind"] in KINDS and re.match(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$", i["date_published"]) and i["content_text"].startswith("Network: ") and i["url"].startswith(SITE)
        assert "score" not in (i["title"] + i["content_text"]).lower(), "a score in an entry"
    return len(ids)


def selftest():
    lines = [json.dumps(x) for x in (
        {"seq": 1, "kind": "move", "run_utc": "2026-10-10T21:01:36Z", "oracle": "A", "target": "0x1", "field": "x", "before": 1, "after": 2},
        {"seq": 2, "kind": "admin_change", "run_utc": "2026-10-11T01:00:00Z", "oracle": "Base (Sepolia)", "target": "0x" + "ab" * 20, "label": None, "text": "admin read changed"},
        {"seq": 3, "kind": "alarm", "run_utc": "2026-10-11T02:00:00Z", "text": "scan gave up"},
        {"seq": 4, "kind": "upgraded", "run_utc": "2026-10-12T01:00:00Z", "oracle": "Plasma", "target": "0x" + "cd" * 20, "label": "Some vault", "text": "implementation changed"})]
    f = build(lines); n = check(f); assert n == 2 and [i["_aro"]["seq"] for i in f["items"]] == [4, 2] and all(i["_aro"]["kind"] != "move" for i in f["items"])
    assert build(lines, limit=1)["items"][0]["_aro"]["seq"] == 4
    d = tempfile.mkdtemp(); p = os.path.join(d, "f.json"); json.dump(f, open(p, "w")); check(json.load(open(p)))
    bad = json.loads(json.dumps(f)); bad["items"][1]["id"] = bad["items"][0]["id"]
    try: check(bad); raise AssertionError("ids en double acceptes")
    except AssertionError as e:
        if "acceptes" in str(e): raise
    print("selftest ok: 2 authority changes out of 4 events, order, unique ids, limit, reread")


if __name__ == "__main__":
    a = sys.argv[1:]
    if a == ["--selftest"]: selftest()
    elif a and a[0] == "--check": print("feed ok: %d entries" % check(json.load(open(a[1], encoding="utf-8"))))
    elif len(a) >= 2:
        lim = int(a[a.index("--limit") + 1]) if "--limit" in a else 100
        nets = networks(a[a.index("--scores") + 1]) if "--scores" in a else None
        f = build(open(a[0], encoding="utf-8").read().split("\n"), lim, nets); check(f); json.dump(f, open(a[1], "w", encoding="utf-8"), indent=1, ensure_ascii=False); print("written", a[1], len(f["items"]), "entries")
    else: print(__doc__)
