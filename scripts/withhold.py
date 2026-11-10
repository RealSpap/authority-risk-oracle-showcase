#!/usr/bin/env python3
"""Some entries can be left out of the public view.

The list of what is left out is NOT in this repository: it is read at run time from the environment variable WATCH_WITHHOLD (an Actions secret), JSON:

    {"addresses": ["<address>", ...], "categories": ["<category>"], "level": "hide"}

  categories  queue families (the `family` field of pending_ops.json) that are not part of the public view: their queues are not listed,
              no total counts them, and the files whose totals leave them out say `not_shown` (a total stays a number, counted without them)
  addresses   an address of a private list (a queue's own address, a program it governs, a buffer, a vault, an account of one of its operations): a queue that names
              one of them anywhere is left out, and so are the lines of the event log that name it
  level       "hide" (default): a queue left out is not listed at all; "count": it stays listed with its identity and only the number of operations (pending_count, detail_withheld: true)
  `{}` is a valid list that leaves nothing out: it is how a list is lifted without deleting the secret.

    python3 scripts/withhold.py retain --watch watch [--private FILE]   # after the queue steps, before anything that reads pending_ops.json
    python3 scripts/withhold.py views  --watch watch [--private FILE]   # after the feeds and the totals are written: what they would still show
    python3 scripts/withhold.py check  --watch watch [--private FILE] [--strict]   # before the run is signed and before every record: exit 1 if a string left out is still in a published file

retain, in this order: (1) takes the queues out of watch/pending_ops.json, so every file written from it afterwards (alerts, feeds, review queue, score series, ledger, coverage)
is computed without them; (2) takes out of watch/events.jsonl the lines THIS run appended that name a queue left out or announce an upgrade of a program it governs, and links the
lines that stay again (the lines of earlier runs are never touched: they are what the signature of the previous run pins); (3) removes from watch/second_opinion.json and
second_opinion.md the per-run lines `upgraded` and `changed` of those programs; (4) removes from the files that carry state from run to run (alerts.json history, warning_ledger.json,
digest.md) what earlier runs wrote about the queues. The full records, lines and fields go to FILE (a runner file, never under watch/) for the private watch. Nothing is printed.
views: drops from the Atom feeds and paper_trail.json what names a string left out, and says `not_shown` in the files whose counts would otherwise read 0. It then reads every published file the way `check` does
and cleans what `check` would refuse: in a JSON file an entry (of a list) that names an operation of a queue left out is dropped, and any other string that names one of the strings left out (an address in a
sentence, in a path, in a key, in its shortened form, in any case) is written without it; in a text file the line is dropped (a bullet that names an operation) or written without it. An alert that quotes the path of control of a program
(`reading.second_opinion.path`) and names a string left out loses that one field, with no mark in its place.
Fails closed: with a list present, a crash, an unreadable queue file or an unknown head of the event log stops the job and writes one ALARM line to watch/run.log (the private alarm).
With the list absent or unreadable the Watch publishes as before and the same alarm says so; it names nobody.
A configured address that is a scored target (a program the oracle tracks) stays a scored target. An address that is a controller (a multisig, a vault) stays in the files that state who
controls a program (second_opinion.json, second_opinion.md, *_vaults.json): the next run compares its reads with them. `check --strict` lists every file that still names one.
Not changed: lines of events.jsonl written by earlier runs, and what earlier commits of watch-data already show.
"""
import argparse, fnmatch, hashlib, json, os, re, sys

KEEP = ("name", "chain", "address", "family", "status", "discovered", "governs", "delay")   # what a "count" record keeps: an allowlist, so a field added later is left out by default
QUEUE_RULES = ("a queued change against this contract", "an upgrade was executed")   # alert rules about a queue or about an upgrade (rules.json) begin with these
STRUCTURE = ("second_opinion.json", "second_opinion.md")   # these, and the files named *_vaults.json, name a multisig or a vault as the control of a program, not its queue
QUEUE_FILES = ("pending_ops.json", "pending_ops.ics", "alerts.json", "alerts.xml", "digest.md", "review_queue.json", "review_queue.md", "score_series.json", "warning_ledger.json", "risk_by_cause.json", "feed.xml", "paper_trail.json")
QUEUE_DIRS = ("feed",)
UNPUBLISHED = ("alarm.md", "alerts_high.md", "alarm_state.json", "who_controls.json")
EXT = (".json", ".jsonl", ".xml", ".md", ".ics", ".csv", ".prom")
MAX_SECRET = 48000   # bytes: GitHub refuses a secret over 48 KB
MASK = "(not shown)"   # what stands where a string left out was written in a published file
ABSENT = "ALARM withhold list not read (WATCH_WITHHOLD is absent): the public view is written as before"
INVALID = "ALARM withhold list not read (WATCH_WITHHOLD is not a valid list): the public view is written as before"
NOHEAD = "ALARM withhold stopped the run (the head of the previous event log is unknown, so the event log cannot be written without the lines left out)"
BADQUEUE = "ALARM withhold stopped the run (the queue file could not be read, so nothing could be left out of it)"
CRASH = "ALARM withhold stopped the run (a step failed with a list present)"
CHECK = "ALARM withhold stopped the run (a published file still names something left out of the public view: nothing was recorded)"


def parse(raw):
    """(config, None) or (None, 'absent' | 'invalid'). Nothing of `raw` is ever put in a message."""
    if raw is None or not str(raw).strip(): return None, "absent"
    try:
        d = json.loads(raw)
        if not isinstance(d, dict) or not set(d) <= {"categories", "addresses", "level"}: return None, "invalid"
        cats, adr, level = d.get("categories", []), d.get("addresses", []), d.get("level", "hide")
        if not (isinstance(cats, list) and isinstance(adr, list) and all(isinstance(x, str) and x.strip() for x in cats + adr)) or level not in ("hide", "count"): return None, "invalid"
    except Exception: return None, "invalid"   # noqa: BLE001 -- not even the parser's message: it can quote the text
    return {"categories": {x.strip().lower() for x in cats}, "addresses": {x.strip().lower() for x in adr}, "level": level}, None


def by_term(rec, cfg):
    """A record names one of the configured addresses: as its own address, or anywhere in it (governs, target, account, signature, what, a buffer, a vault)."""
    if str(rec.get("address") or "").lower() in cfg["addresses"]: return True
    text = json.dumps(rec).lower()
    return any(len(t) >= 8 and t in text for t in cfg["addresses"])


def holds(rec, cfg):
    return str(rec.get("family") or "").lower() in cfg["categories"] or by_term(rec, cfg)


def shorts(a):
    """The shortened forms the Watch writes for an address (four and four, six and four characters around an ellipsis)."""
    return [a[:4] + "…" + a[-4:], a[:6] + "…" + a[-4:]] if isinstance(a, str) and len(a) >= 12 else []


def short(a):
    """The form the queue names carry: four characters, an ellipsis, four characters."""
    return shorts(a)[0] if shorts(a) else None


def plain(text):
    """A JSON file written with the default settings carries the ellipsis as \\u2026: read it as the character the shortened names are made with."""
    return text.replace("\\u2026", "…").lower()


def is_structure(rel):
    return rel in STRUCTURE or fnmatch.fnmatch(rel, "*_vaults.json")


def tokens(recs):
    """(identity strings, operation strings) of the records: the operation strings of every record left out, the identity (address, name, short forms) of those that name a configured
    address (`_targeted`): a queue left out only because of its family is one of many and its address is no secret."""
    ident, ops = set(), set()
    for r in recs:
        a = r.get("address")
        if r.get("_targeted"):
            for v in [a, r.get("name")] + shorts(a):
                if isinstance(v, str) and len(v) >= 8: ident.add(v)
        for k in ("pending", "recent", "active"):
            for o in r.get(k) or []:
                for f in ("id", "account", "tx", "signature"):
                    if isinstance(o, dict) and isinstance(o.get(f), str) and len(o[f]) >= 8: ops.add(o[f])
    return ident, ops


def retain_doc(doc, cfg):
    """Records left out are removed from doc["results"] (level hide) or reduced to identity and a count. Returns the full records."""
    out, held = [], []
    for r in doc.get("results") or []:
        if not (isinstance(r, dict) and holds(r, cfg)): out.append(r); continue
        if r.get("detail_withheld"): out.append({k: r[k] for k in KEEP + ("pending_count", "detail_withheld", "pending") if k in r}); continue   # already reduced by an earlier pass: keep its count
        held.append(r)
        if cfg["level"] == "count":
            n = len(r.get("pending") or []) if str(r.get("status", "ok")) == "ok" else None
            out.append({**{k: r[k] for k in KEEP if k in r}, "pending": [], "pending_count": n, "detail_withheld": True})
    doc["results"] = out
    return held


def _load(p):
    try: return json.load(open(p))
    except Exception: return None  # noqa: BLE001


def _save(p, obj):
    tmp = p + ".tmp"; json.dump(obj, open(tmp, "w"), indent=1); os.replace(tmp, p)


def targets(watch):
    """The addresses the oracle scores (watch/scores/*.json, `target`), lowercased: a configured address among them is a tracked program, not a secret to remove everywhere."""
    out, d = set(), os.path.join(watch, "scores")
    for n in (os.listdir(d) if os.path.isdir(d) else []):
        doc = _load(os.path.join(d, n))
        for t in (doc.get("targets") if isinstance(doc, dict) else None) or []:
            if isinstance(t, dict) and isinstance(t.get("target"), str): out.add(t["target"].lower())
    return out


def governed(watch, addrs):
    """Programs whose control (the multisig or the holder the independent reader found) is one of `addrs`: read from this run's second_opinion.json, so a queue that was not read this run still has its programs."""
    out = set(); d = _load(os.path.join(watch, "second_opinion.json"))
    for r in (d.get("results") if isinstance(d, dict) else None) or []:
        if isinstance(r, dict) and any(str(r.get(k) or "").lower() in addrs for k in ("multisig", "holder")) and isinstance(r.get("target"), str): out.add(r["target"].lower())
    return out


def _head(watch):
    return ((_load(os.path.join(watch, "signature.json")) or {}).get("manifest") or {}).get("events_chain_head")


def drop_events(watch, every, gov):
    """Take out of events.jsonl the lines this run appended that name something left out, or announce an upgrade of a governed program; link the lines that stay again.
    The lines of earlier runs end at the head the previous signature pins: they are never read for this, never rewritten. Returns the lines dropped, or None when that head is unknown."""
    p = os.path.join(watch, "events.jsonl")
    if not os.path.exists(p): return []
    lines = [l for l in open(p, encoding="utf-8").read().split("\n") if l.strip()]; head = _head(watch)
    idx = next((i for i, l in enumerate(lines) if head and hashlib.sha256(l.encode()).hexdigest() == head), None)
    if idx is None: return None
    new = lines[idx + 1:]

    def named(l):
        if any(t in plain(l) for t in every): return True
        try: e = json.loads(l)
        except ValueError: return False
        return e.get("kind") == "upgraded" and str(e.get("target") or "").lower() in gov
    dropped = [l for l in new if named(l)]
    if not dropped: return []
    last = lines[idx]; prev = hashlib.sha256(last.encode()).hexdigest()
    try: seq = int(json.loads(last).get("seq"))
    except Exception: seq = 0   # noqa: BLE001
    out = lines[:idx + 1]
    for l in new:
        if l in dropped: continue
        seq += 1; line = json.dumps({**json.loads(l), "seq": seq, "prev": prev}); out.append(line); prev = hashlib.sha256(line.encode()).hexdigest()   # the same link rule as the writers
    tmp = p + ".tmp"; open(tmp, "w", encoding="utf-8").write("\n".join(out) + "\n"); os.replace(tmp, p)
    return dropped


def scrub_reads(watch, gov):
    """The per-run fields `upgraded` and `changed` of the governed programs in second_opinion.json (recomputed from the previous run at every run, never carried), and their rows in the lists
    `upgrades` and `changed`. Returns (what was removed, the texts removed)."""
    p = os.path.join(watch, "second_opinion.json"); d = _load(p); out, texts = [], []
    if not isinstance(d, dict) or not gov: return out, texts
    for r in d.get("results") or []:
        if isinstance(r, dict) and str(r.get("target") or "").lower() in gov and (r.get("upgraded") or r.get("changed")):
            out.append({"chain": r.get("chain"), "target": r.get("target"), "upgraded": r.pop("upgraded", None), "changed": r.pop("changed", None)})
            texts += [x for x in (out[-1]["upgraded"], out[-1]["changed"]) if isinstance(x, str) and x]
    for k in ("upgrades", "changed"):
        if isinstance(d.get(k), list): d[k] = [x for x in d[k] if not (isinstance(x, dict) and str(x.get("target") or "").lower() in gov)]
    if out: _save(p, d)
    return out, texts


def scrub_md(watch, texts, every):
    """second_opinion.md is written from the same lists: its bullets that carry a text removed above, or a string left out, go; a section left with no bullet goes with its title and its closing
    sentence, a section that keeps some is counted again; no section left, no file (as the writer does)."""
    p = os.path.join(watch, "second_opinion.md")
    if not os.path.exists(p) or not (texts or every): return 0
    src = open(p, encoding="utf-8").read(); head, *secs = re.split(r"(?m)^(?=### )", src); out, n = [head], 0
    for s in secs:
        lines = s.split("\n"); items = [l for l in lines if l.startswith("- ")]
        keep = [l for l in items if not (any(t in l for t in texts) or any(w in plain(l) for w in every))]
        if len(keep) == len(items): out.append(s); continue
        n += len(items) - len(keep)
        if not keep: continue
        body = [l for l in lines if not l.startswith("- ")]; first = re.sub(r"^(### )\d+", lambda m: m.group(1) + str(len(keep)), body[0], count=1)
        out.append("\n".join([first, ""] + keep + body[1:]))
    if not n: return 0
    if len(out) == 1: os.remove(p)
    else: open(p, "w", encoding="utf-8").write("".join(out))
    return n


def scrub_carried(watch, recs, extra=(), gov_extra=()):
    """What earlier runs wrote about the queues in the three files that carry state: alerts.json history, warning_ledger.json, digest.md."""
    if not recs and not gov_extra: return
    ident, ops = tokens(recs); every = [t.lower() for t in ident | ops | set(extra)]
    gov = {str(g).lower() for r in recs if r.get("_targeted") for g in (r.get("governs") or [])} | set(gov_extra)
    p = os.path.join(watch, "alerts.json"); d = _load(p)
    if isinstance(d, dict) and isinstance(d.get("history"), list):
        d["history"] = [h for h in d["history"] if not (isinstance(h, dict) and str(h.get("rule", "")).startswith(QUEUE_RULES) and str(h.get("target", "")).lower() in gov)]; _save(p, d)
    p = os.path.join(watch, "warning_ledger.json"); d = _load(p)
    if isinstance(d, dict) and isinstance(d.get("entries"), dict):
        d["entries"] = {k: v for k, v in d["entries"].items() if not any(t in k.lower() for t in every)}; _save(p, d)
    p = os.path.join(watch, "digest.md")
    if os.path.exists(p):
        lines = open(p, encoding="utf-8").read().split("\n")
        open(p, "w", encoding="utf-8").write("\n".join(l for l in lines if not any(t in l.lower() for t in every)))


def alarm(watch, text):
    try:
        with open(os.path.join(watch, "run.log"), "a") as f: f.write(text + "\n")
    except OSError: pass
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a") as f: f.write("alarm=1\n")


def _private_load(private):
    d = _load(private) if private else None
    d = d if isinstance(d, dict) else {"queues": d if isinstance(d, list) else []}
    return {"queues": d.get("queues") or [], "events": d.get("events") or [], "reads": d.get("reads") or [], "config": d.get("config")}


def retain(watch, private):
    cfg, why = parse(os.environ.get("WATCH_WITHHOLD"))
    if cfg is None:
        if why == "invalid": alarm(watch, INVALID)
        elif os.environ.get("WATCH_WITHHOLD_REQUIRED") == "1": alarm(watch, ABSENT)
        return 0
    if not cfg["categories"] and not cfg["addresses"]: return 0   # `{}`: a list that leaves nothing out (how a list is lifted)
    try:
        p = os.path.join(watch, "pending_ops.json"); doc = _load(p)
        if not isinstance(doc, dict): alarm(watch, BADQUEUE); return 2   # the queue file cannot be read: the lines about it would enter the chain, so the run stops
        held = retain_doc(doc, cfg); tgt = [r for r in held if by_term(r, cfg)]; tg = targets(watch)
        marked = [dict(r, _targeted=True) if any(r is t for t in tgt) else r for r in held]
        secret = {t for t in cfg["addresses"] if len(t) >= 8} - tg   # a scored program is not a secret to remove everywhere
        ident, ops = tokens(marked); every = [w.lower() for w in ident | ops | secret] + [s.lower() for t in secret | {r.get("address") for r in tgt} for s in shorts(t)]
        gov = {str(g).lower() for r in tgt for g in (r.get("governs") or [])} | {t for t in cfg["addresses"] if t in tg} | governed(watch, {a.lower() for a in secret | {r.get("address") for r in tgt} if a})
        dropped = drop_events(watch, every, gov)
        if dropped is None: alarm(watch, NOHEAD); return 2   # the log cannot be told from this run's lines: nothing was changed, and nothing is signed
        reads, texts = scrub_reads(watch, gov); scrub_md(watch, texts, every)
        if private:
            old = _private_load(private); key = lambda r: (r.get("chain"), str(r.get("address")).lower())
            q = {key(r): r for r in old["queues"] if isinstance(r, dict)}; q.update({key(r): r for r in marked})
            ev = list(old["events"]) + [l for l in dropped if l not in old["events"]]
            rd = list(old["reads"]) + [r for r in reads if r not in old["reads"]]
            fd = os.open(private, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w") as f: json.dump({"queues": list(q.values()), "events": ev, "reads": rd, "config": {"addresses": sorted(cfg["addresses"]), "categories": sorted(cfg["categories"]), "level": cfg["level"]}}, f, indent=1)
        if cfg["categories"]: doc["not_shown"] = sorted(cfg["categories"])
        _save(p, doc); scrub_carried(watch, marked, {r.get("address") for r in held if r.get("address")} | {r.get("name") for r in held if r.get("name")} | secret | {s for t in secret for s in shorts(t)}, gov)
    except Exception: alarm(watch, CRASH); return 2   # noqa: BLE001 -- with a list present, a crash must stop the job: publishing what was to be left out is the one failure that cannot be undone
    return 0


def published(watch):
    for d, dirs, names in os.walk(watch):
        dirs[:] = [x for x in dirs if not x.startswith(".")]
        for n in names:
            if n.endswith(EXT) and n not in UNPUBLISHED and not n.startswith("."): yield os.path.join(d, n)


def _config_of(cfg, priv):
    if cfg: return cfg
    c = (priv or {}).get("config") or {}
    return parse(json.dumps(c))[0] if c else None


def views(watch, private, cfg):
    """The Atom feeds and paper_trail.json are written from the whole event log and the documents of the repository: what names a string left out leaves them (the event log itself is immutable and
    stays as it is). Where a count would read 0 only because a family is not shown, the file says `not_shown` and the count is null."""
    priv = _private_load(private) if private else {"queues": []}; cfg = _config_of(cfg, priv); ident, ops = tokens(priv["queues"])
    secret = {t for t in (cfg or {}).get("addresses", ()) if len(t) >= 8} - targets(watch)
    every = [w.lower() for w in ident | ops | secret] + [s.lower() for t in secret | {r.get("address") for r in priv["queues"] if r.get("_targeted")} for s in shorts(t)]
    for p in published(watch):
        rel = os.path.relpath(p, watch).replace(os.sep, "/")
        if every and p.endswith(".xml") and (rel in ("feed.xml", "alerts.xml") or rel.split("/")[0] in QUEUE_DIRS):
            text = open(p, encoding="utf-8").read(); parts = re.split(r"(<entry>.*?</entry>)", text, flags=re.S)
            kept = [x for x in parts if not (x.startswith("<entry>") and any(w in plain(x) for w in every))]
            if len(kept) != len(parts): open(p, "w", encoding="utf-8").write("".join(kept))
        if every and rel == "paper_trail.json":
            d = _load(p)
            if isinstance(d, dict) and isinstance(d.get("index"), dict) and any(k.lower() in set(every) for k in d["index"]):
                d["index"] = {k: v for k, v in d["index"].items() if k.lower() not in set(every)}; _save(p, d)
    scrub(watch, priv, cfg)
    fams = sorted((cfg or {}).get("categories") or ())
    if not fams: return 0
    chains = {str(r.get("chain")) for r in priv["queues"] if str(r.get("family")) in fams and r.get("chain")}
    note = "queues of the %s family are not shown in the public view: the counts and the alerts of this file do not include them" % ", ".join(fams)
    p = os.path.join(watch, "coverage.json"); d = _load(p)
    if isinstance(d, dict):
        d["not_shown"] = fams; ch = d.get("chains", d)
        for k, v in (ch.items() if isinstance(ch, dict) else ()):
            if isinstance(v, dict) and any(c in k for c in chains) and "timelock_queues_watched" in v:
                v["blind_spots"] = list(v.get("blind_spots") or []) + [note]
        _save(p, d)
    p = os.path.join(watch, "risk_by_cause.json"); d = _load(p)
    if isinstance(d, dict):
        d["not_shown"] = fams
        if isinstance(d.get("causes"), dict) and isinstance(d["causes"].get("upgrade_executable"), dict): d["causes"]["upgrade_executable"]["not_counted"] = fams
        _save(p, d)
    p = os.path.join(watch, "alerts.json"); d = _load(p)
    if isinstance(d, dict): d["not_shown"] = fams; _save(p, d)
    p = os.path.join(watch, "trend.jsonl")
    if os.path.exists(p):
        ls = open(p, encoding="utf-8").read().split("\n"); idx = max((i for i, l in enumerate(ls) if l.strip()), default=None); run = (_load(os.path.join(watch, "latest.json")) or {}).get("run_utc")
        try: last = json.loads(ls[idx]) if idx is not None else None
        except ValueError: last = None
        if isinstance(last, dict) and run and last.get("run_utc") == run:
            last["not_shown"] = fams; ls[idx] = json.dumps(last); open(p, "w", encoding="utf-8").write("\n".join(ls))
    return 0


def new_event_lines(watch):
    """The lines of events.jsonl this run appended (after the head the previous signature pins), or None when that head is unknown."""
    p = os.path.join(watch, "events.jsonl")
    if not os.path.exists(p): return []
    head = _head(watch); lines = [l for l in open(p, encoding="utf-8", errors="ignore").read().split("\n") if l.strip()]
    idx = next((i for i, l in enumerate(lines) if head and hashlib.sha256(l.encode()).hexdigest() == head), None)
    return None if idx is None else lines[idx + 1:]


def _sets(watch, priv, cfg):
    """(operation strings, identity strings, other strings left out), lowercased: the three kinds of string `check` looks for and `scrub` removes. The other strings are the configured addresses that are not
    scored targets, with their shortened forms."""
    ident, ops = tokens(priv["queues"])
    terms = [t for t in ((cfg or {}).get("addresses") or ()) if len(t) >= 8 and t not in targets(watch)]
    return [t.lower() for t in ops], [t.lower() for t in ident], [x.lower() for t in terms for x in [t] + shorts(t)]


def _looked_for(rel, ops, ident, terms, level, strict):
    """The strings a published file must not name, by its place: (operation strings, strings that name a queue or an address)."""
    if level == "count" and rel == "pending_ops.json": return ops, []   # the queue is listed there on purpose, with its identity and a number
    queue_class = rel in QUEUE_FILES or rel.split("/")[0] in QUEUE_DIRS or rel == "events.jsonl"
    names = ([] if is_structure(rel) and not strict else list(ident)) + (list(terms) if strict or queue_class else [])
    return ops, names


def _plain_of(p):
    try: return plain(open(p, encoding="utf-8", errors="ignore").read())
    except OSError: return None


def _text_of(p, rel, new):
    t = _plain_of(p)
    return plain("\n".join(new)) if rel == "events.jsonl" and t is not None else t


def check(watch, private, cfg=None, strict=False):
    """Published files that still name a string left out. Operation strings of a queue left out: nowhere. The identity of a queue that names a configured address: nowhere but the structure files
    (and, at level count, its own record). A configured address that is not a scored target: in the queue files and the new event lines; with strict, in every file."""
    priv = _private_load(private) if private else {"queues": []}; cfg = _config_of(cfg, priv); recs = priv["queues"]
    if not recs and not cfg: return []
    ops, ident, terms = _sets(watch, priv, cfg); level = cfg["level"] if cfg else "hide"
    new = new_event_lines(watch); bad = []
    for p in published(watch):
        rel = os.path.relpath(p, watch).replace(os.sep, "/")
        if rel == "events.jsonl" and new is None: continue   # the head is unknown: the lines of earlier runs cannot be told from this run's
        t = _text_of(p, rel, new)
        if t is None: continue
        o, n = _looked_for(rel, ops, ident, terms, level, strict)
        if any(x in t for x in o + n): bad.append(rel)
    return sorted(bad)


def _mask(text, words):
    """`text` without any of `words` (any case, longest first)."""
    return re.sub("|".join(re.escape(w) for w in sorted(words, key=len, reverse=True)), MASK, text, flags=re.I) if words else text


def _naming(v, words):
    return any(w in plain(json.dumps(v, ensure_ascii=False)) for w in words)


def _clean_json(v, ops, names, in_list=False):
    """A copy of `v` without what names a string left out. The first list met on the way down is a list of entries (alerts, items, actions, points): an entry that names an operation is dropped, and the
    number that counted the list (`total`, `count`, `actions`) is counted again; everywhere else a string is written without the words, and so is a key."""
    words = ops + names
    if isinstance(v, str): return _mask(v, [w for w in words if w in plain(v)])
    if isinstance(v, list): return [_clean_json(x, ops, names, True) for x in v if in_list or not _naming(x, ops)]
    if not isinstance(v, dict): return v
    out, shrunk = {}, []   # ponytail: only `total`, `count` and `actions` are counted again; a file with other counts (by_priority, by_band) is written again by its own step after `retain`, this is the net under it
    for k, x in v.items():
        hit = [w for w in words if w in plain(str(k))]
        if hit and not in_list: continue   # an entry keyed by a string left out
        if k == "second_opinion" and isinstance(x, dict) and isinstance(x.get("path"), str) and any(w in plain(x["path"]) for w in words):
            x = {kk: vv for kk, vv in x.items() if kk != "path"}   # taken out, not written with a mark: a mark would show where the string was
        y = _clean_json(x, ops, names, in_list); out[_mask(str(k), hit) if hit else k] = y
        if isinstance(x, list) and len(y) != len(x): shrunk.append((len(x), len(y)))
    for c in ("total", "count", "actions"):
        for was, now in shrunk:
            if v.get(c) == was and c in out: out[c] = now
    return out


def _clean_text(text, ops, names, drop):
    """A text file without what names a string left out: a bullet about an operation goes (not in a file of one line per record), any other line is written without the words."""
    out = []
    for l in text.split("\n"):
        low = plain(l)
        if drop and l.lstrip().startswith(("- ", "* ")) and any(o in low for o in ops): continue
        if any(w in low for w in ops + names): l = _mask(l.replace("\\u2026", "…"), ops + names)
        out.append(l)
    return "\n".join(out)


def scrub(watch, priv, cfg):
    """What `check` would refuse, cleaned: see `views`. Only the files `check` refuses are read again and written again."""
    if not priv["queues"] and not cfg: return
    ops, ident, terms = _sets(watch, priv, cfg); level = cfg["level"] if cfg else "hide"
    for p in published(watch):
        rel = os.path.relpath(p, watch).replace(os.sep, "/")
        if rel in ("events.jsonl", "pending_ops.json", "pending_ops.ics"): continue   # the log is never rewritten here, the queue file is cleaned by `retain`
        o, n = _looked_for(rel, ops, ident, terms, level, False)
        if not (o or n) or not any(x in (_plain_of(p) or "") for x in o + n): continue
        if p.endswith(".json"):
            d = _load(p)
            if d is None: raise ValueError("a published JSON file could not be read")
            _save(p, _clean_json(d, o, n))
        else:
            text = _clean_text(open(p, encoding="utf-8", errors="ignore").read(), o, n, not p.endswith(".jsonl"))   # read before the file is opened for writing
            open(p, "w", encoding="utf-8").write(text)


def main(argv=None):
    ap = argparse.ArgumentParser(); ap.add_argument("cmd", choices=("retain", "views", "check")); ap.add_argument("--watch", default="watch"); ap.add_argument("--private", default=os.environ.get("WATCH_WITHHOLD_PRIVATE")); ap.add_argument("--strict", action="store_true")
    a = ap.parse_args(argv)
    if not a.private and os.environ.get("RUNNER_TEMP") and os.path.exists(os.path.join(os.environ["RUNNER_TEMP"], "held_queue.json")): a.private = os.path.join(os.environ["RUNNER_TEMP"], "held_queue.json")   # the later steps and the record read the file the first step wrote
    if a.cmd == "retain": return retain(a.watch, a.private)
    cfg, _ = parse(os.environ.get("WATCH_WITHHOLD"))
    if a.cmd == "views":
        try: return views(a.watch, a.private, cfg)
        except Exception: alarm(a.watch, CRASH); return 2   # noqa: BLE001 -- as retain: with a list present, stop rather than publish
    bad = check(a.watch, a.private, cfg, a.strict)
    if bad:
        top = sorted({b.split("/")[0] for b in bad})   # the top folder or file only: a per-program file is named by the program
        print("withhold check: a string left out is still in %d published file(s), under: %s" % (len(bad), ", ".join(top[:6])), file=sys.stderr)
        alarm(a.watch, CHECK)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
