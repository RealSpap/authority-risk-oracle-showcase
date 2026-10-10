#!/usr/bin/env python3
"""The paper trail of every tracked target: which dated documents in data/ and docs/ mention its address.

Findings, corrections, backtests, audits and reviews are written as Markdown files with the date in their name. This index
lets the dashboard show, under a protocol, "3 documents: correction 2026-09-16 …, finding 2026-09-17 …" with a link to each,
so a reader can see the work behind a score instead of taking it on faith. Read-only; no network.

    python3 scripts/paper_trail.py --out watch/paper_trail.json
"""
import argparse, glob, json, os, re, sys

def _dump_json(obj, path, indent=None):
    """Write the file only once the whole object is serialised: a crash half-way never leaves a truncated JSON behind
    (the previous run's file stays), and a reader never sees a half-written one."""
    import json as _j, os as _o
    tmp = path + ".tmp"
    with open(tmp, "w") as f: _j.dump(obj, f, indent=indent)
    _o.replace(tmp, path)


ADDR = re.compile(r"0x[0-9a-fA-F]{40}")
SOL = re.compile(r"\b[1-9A-HJ-NP-Za-km-z]{32,44}\b")

def title_of(path):
    for line in open(path, encoding="utf-8", errors="replace"):
        if line.startswith("# "): return line[2:].strip()[:140]
    return os.path.basename(path)

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--out", default="watch/paper_trail.json"); ap.add_argument("--dirs", nargs="*", default=["data", "docs"])
    a = ap.parse_args()
    index, docs = {}, 0
    for d in a.dirs:
        for path in sorted(glob.glob(os.path.join(d, "**", "*.md"), recursive=True)):
            text = open(path, encoding="utf-8", errors="replace").read(); docs += 1
            name = os.path.basename(path); m = re.search(r"(\d{4}-\d\d-\d\d)", name); date = m.group(1) if m else ""
            kind = name.split("_")[0] if "_" in name else ""
            rec = {"file": path.replace(os.sep, "/"), "title": title_of(path), "date": date, "kind": kind}
            seen = set()
            for x in sorted(set(ADDR.findall(text)) | {s for s in SOL.findall(text) if not re.fullmatch(r"[0-9a-fA-F]{32,44}", s)}):
                k = x.lower() if x.startswith("0x") else x
                if k in seen: continue
                seen.add(k); index.setdefault(k, []).append(rec)
    for k in index: index[k].sort(key=lambda r: r["date"], reverse=True)
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    _dump_json({"docs": docs, "index": dict(sorted(index.items()))}, a.out, indent=0)
    print(f"paper trail: {docs} documents, {len(index)} addresses mentioned")

if __name__ == "__main__":
    sys.exit(main())
