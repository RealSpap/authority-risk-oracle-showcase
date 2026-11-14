#!/usr/bin/env python3
"""Replay Grade v0.1 made executable: reads again each claim of the public pages (README and the pages under /oracle/), gives its grade A to D, and says what a replay gave.

    - python3 scripts/replay_grade.py                 # every claim: grade, verdict, cause
    - python3 scripts/replay_grade.py --offline       # no network read at all (the checks that need one are UNREAD, with that cause)
    - python3 scripts/replay_grade.py --json          # the same, machine readable
    - python3 scripts/replay_grade.py --only H01,V05  # a few claims
    - python3 scripts/replay_grade.py --now STAMP  # the stamp of the report only: the Watch window is always judged on the real clock, before every request
    - python3 scripts/replay_grade.py --strict        # an UNREAD claim makes the exit code 3
    - python3 scripts/replay_grade.py --selftest      # plants false values and false failures; exit 0 only if every one is caught

Two different things are given for each claim and never mixed:
  GRADE   A to D: what the PAGE lets a reader replay, from four elements (command, named point of reading, expected result, network) and a source. It is computed from
          scripts/replay_grade_claims.json, never written by hand. It does not say whether the claim is true.
  VERDICT what THIS script got when it replayed the claim: OK (the replay gives what the page says), DIFFERENCE (it ran and gave something else; the cause says what),
          UNREAD (the replay did not run or its read failed: no command to run yet, refused or dead link, a field that is not there, a file that reports errors of its own, an empty list, a dated claim whose value moved, the Watch window, --offline).
          UNREAD is never OK and never zero: it is counted apart and never turned into a value.

Reads only: the public repository copy, https://realspap.github.io and https://raw.githubusercontent.com (nothing else is opened), never during a Watch window
(minutes 10 to 55 of the UTC hours 0, 6, 12 and 18). No key, no transaction, standard library only. Exit code: 1 if any claim is a DIFFERENCE, 3 if nothing was read at all
(or, with --strict, if any claim is UNREAD), else 0. No scorer imports this file, so the methodology hash does not change (scripts/lib/methodology.py, scoring_files)."""
import argparse, collections, datetime as dt, json, os, re, sys, urllib.error, urllib.parse, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
HOSTS = {"realspap.github.io", "raw.githubusercontent.com"}
SITE = "https://realspap.github.io/oracle/"
WATCH = "https://raw.githubusercontent.com/RealSpap/authority-risk-oracle-showcase/watch-data/"


def grade(e):
    """Replay Grade v0.1: A = command, named point, expected result and network (n/a when the claim is about no chain); B = not A and a command; C = not B and a source or a named point; D = nothing"""
    if e["cmd"] and e["pt"] and e["ex"] and (e["net"] is None or e["net"]): return "A"
    if e["cmd"]: return "B"
    return "C" if (e["src"] or e["pt"]) else "D"


# ---------------------------------------------------------------- keccak-256 (the Ethereum one, not the NIST SHA-3), for the selectors and slots written on the pages
_RC = [0x0000000000000001, 0x0000000000008082, 0x800000000000808A, 0x8000000080008000, 0x000000000000808B, 0x0000000080000001, 0x8000000080008081, 0x8000000000008009,
       0x000000000000008A, 0x0000000000000088, 0x0000000080008009, 0x000000008000000A, 0x000000008000808B, 0x800000000000008B, 0x8000000000008089, 0x8000000000008003,
       0x8000000000008002, 0x8000000000000080, 0x000000000000800A, 0x800000008000000A, 0x8000000080008081, 0x8000000000008080, 0x0000000080000001, 0x8000000080008008]
_ROT = [[0, 36, 3, 41, 18], [1, 44, 10, 45, 2], [62, 6, 43, 15, 61], [28, 55, 25, 21, 56], [27, 20, 39, 8, 14]]
_M = (1 << 64) - 1


def _rol(x, n): return ((x << n) | (x >> (64 - n))) & _M if n else x


def _f(s):
    for rc in _RC:
        c = [s[x][0] ^ s[x][1] ^ s[x][2] ^ s[x][3] ^ s[x][4] for x in range(5)]
        d = [c[(x - 1) % 5] ^ _rol(c[(x + 1) % 5], 1) for x in range(5)]
        s = [[s[x][y] ^ d[x] for y in range(5)] for x in range(5)]
        b = [[0] * 5 for _ in range(5)]
        for x in range(5):
            for y in range(5): b[y][(2 * x + 3 * y) % 5] = _rol(s[x][y], _ROT[x][y])
        s = [[b[x][y] ^ ((~b[(x + 1) % 5][y]) & b[(x + 2) % 5][y]) for y in range(5)] for x in range(5)]
        s[0][0] ^= rc
    return s


def keccak256(data):
    rate = 136; p = bytearray(data) + b"\x01"
    while len(p) % rate: p += b"\x00"
    p[-1] |= 0x80
    s = [[0] * 5 for _ in range(5)]
    for off in range(0, len(p), rate):
        for i in range(rate // 8): s[i % 5][i // 5] ^= int.from_bytes(p[off + 8 * i: off + 8 * i + 8], "little")
        s = _f(s)
    return b"".join(s[i % 5][i // 5].to_bytes(8, "little") for i in range(4))


def selector(signature): return "0x" + keccak256(signature.encode()).hex()[:8]


def slot(name, minus_one): return "0x%064x" % (int.from_bytes(keccak256(name.encode()), "big") - (1 if minus_one else 0))


# ---------------------------------------------------------------- context, window, reading
def utc_now(): return dt.datetime.now(dt.timezone.utc)


class Context:
    """now = the stamp written on the report (it may be given with --now); clock = the REAL clock, read before every request, which alone decides the Watch window"""
    def __init__(self, repo, fetch, now, offline=False, clock=None): self.repo, self.fetch, self.now, self.offline, self.clock = repo, fetch, now, offline, clock or utc_now


def parse_now(s):
    if not s: return utc_now()
    t = dt.datetime.fromisoformat(s.replace("Z", "+00:00")); return t.astimezone(dt.timezone.utc) if t.tzinfo else t.replace(tzinfo=dt.timezone.utc)


def in_watch_window(t):
    t = t.astimezone(dt.timezone.utc) if t.tzinfo else t.replace(tzinfo=dt.timezone.utc)
    return t.hour % 6 == 0 and 10 <= t.minute <= 55


def default_fetch(url, limit=None):
    h = {"User-Agent": "read-only-replay-grade"}
    if limit: h["Range"] = "bytes=0-%d" % (limit - 1)
    with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=30) as r: return r.read(limit) if limit else r.read()


def _read(chk, ctx):
    """the bytes of chk["url"], or raises _Unread with the cause"""
    host = urllib.parse.urlparse(chk["url"]).hostname
    if host not in HOSTS: raise _Unread("host %s is not one of the two public hosts this script opens" % host)
    if ctx.offline: raise _Unread("offline: --offline forbids every network read")
    if in_watch_window(ctx.clock()): raise _Unread("Watch window (minutes 10 to 55 of UTC hours 0, 6, 12, 18): no request")
    try: return ctx.fetch(chk["url"], chk.get("limit"))
    except (OSError, urllib.error.URLError, ValueError) as e: raise _Unread("%s: %s" % (chk["url"], str(e)[:80]))


class _Unread(Exception): pass


def _dig(o, path):
    for k in path.split("."):
        if not isinstance(o, dict) or k not in o: raise _Unread("field %s is not in the answer" % path)
        o = o[k]
    return o


def _json(chk, ctx):
    try: doc = json.loads(_read(chk, ctx))
    except ValueError as e: raise _Unread("the answer is not JSON: %s" % str(e)[:60])
    if isinstance(doc, dict) and doc.get("errors"): raise _Unread("the file reports errors of its own read, so its values are not a reading: %s" % str(doc["errors"])[:80])
    return doc


# ---------------------------------------------------------------- the checks: kind -> function(chk, ctx) -> (verdict, cause)
def _selectors(chk, ctx):
    bad = [(sig, want, selector(sig)) for sig, want in chk["items"] if selector(sig) != want]
    return ("DIFFERENCE", "; ".join("%s: page %s, keccak %s" % b for b in bad)) if bad else ("OK", "%d selector(s) equal keccak of their signature" % len(chk["items"]))


def _slots(chk, ctx):
    bad = [(n, want, slot(n, m)) for n, m, want in chk["items"] if slot(n, m) != want]
    return ("DIFFERENCE", "; ".join("%s: page %s, keccak %s" % b for b in bad)) if bad else ("OK", "%d slot(s) equal keccak of their name" % len(chk["items"]))


def _lines(chk, ctx):
    got = []
    for rel, want in chk["items"]:
        p = os.path.join(ctx.repo, rel)
        if not os.path.isfile(p): raise _Unread("file %s is not in the repository copy" % rel)
        with open(p, "rb") as f: got.append((rel, want, f.read().count(b"\n")))
    bad = [g for g in got if g[1] != g[2]]
    return ("DIFFERENCE", "; ".join("%s: page %d lines, file %d" % (r, w, n) for r, w, n in bad)) if bad else ("OK", "line counts equal: " + ", ".join("%s %d" % (r, n) for r, _, n in got))


def _json_check(chk, ctx):
    v = _dig(_json(chk, ctx), chk["path"])
    if chk["op"] == "len_eq":
        if not isinstance(v, list): raise _Unread("field %s is not a list" % chk["path"])
        v = len(v)
    if v == chk["expected"]: return "OK", "read %s, the page says %s" % (v, chk["expected"])
    if chk.get("dated"): return "UNREAD", "the page dates this value (it says %s at build time) and the value moved to %s: a stale expected result, not a difference" % (chk["expected"], v)
    return "DIFFERENCE", "read %s, the page says %s" % (v, chk["expected"])


def _group_count(chk, ctx):
    rows = _dig(_json(chk, ctx), chk["list_path"])
    if isinstance(rows, list) and not rows: raise _Unread("the list %s is empty: nothing was read, and an empty list is not zero counts" % chk["list_path"])
    if not isinstance(rows, list) or not all(isinstance(r, dict) and chk["by"] in r for r in rows): raise _Unread("the list %s has no field %s on every row" % (chk["list_path"], chk["by"]))
    got = dict(collections.Counter(r[chk["by"]] for r in rows))
    return ("OK", "counts equal %s" % got) if got == chk["expected"] else ("DIFFERENCE", "read %s, the page says %s" % (dict(sorted(got.items())), dict(sorted(chk["expected"].items()))))


def _first_line(chk, ctx):
    try: line = json.loads(_read(chk, ctx).decode("utf-8", "replace").split("\n")[0])
    except ValueError as e: raise _Unread("the first line is not JSON: %s" % str(e)[:60])
    if not isinstance(line, dict): raise _Unread("the first line is not an object")
    for k in list(chk.get("expect", {})) + list(chk.get("startswith", {})):
        if k not in line: raise _Unread("field %s is not in the first line" % k)
    bad = [(k, line.get(k), v) for k, v in chk.get("expect", {}).items() if line.get(k) != v] + [(k, line.get(k), v + "...") for k, v in chk.get("startswith", {}).items() if not str(line.get(k, "")).startswith(v)]
    return ("DIFFERENCE", "; ".join("%s is %r, the page implies %r" % b for b in bad)) if bad else ("OK", "first line: " + ", ".join("%s = %s" % (k, line.get(k)) for k in list(chk.get("expect", {})) + list(chk.get("startswith", {}))))


def _json_distinct(chk, ctx):
    box = _dig(_json(chk, ctx), chk["container"])
    if not isinstance(box, dict) or not box: raise _Unread("%s is empty or not a mapping: nothing was read" % chk["container"])
    vals = set()
    for items in box.values():
        if not isinstance(items, list) or not all(isinstance(i, dict) and chk["item_field"] in i for i in items): raise _Unread("an entry of %s has no field %s" % (chk["container"], chk["item_field"]))
        vals |= {i[chk["item_field"]] for i in items}
    n = len(vals)
    return ("OK", "%d distinct %s, the page says %d" % (n, chk["item_field"], chk["expected"])) if n == chk["expected"] else ("DIFFERENCE", "%d distinct %s read, the page says %d" % (n, chk["item_field"], chk["expected"]))


def _html_count(chk, ctx):
    n = len(re.findall(chk["pattern"], _read(chk, ctx).decode("utf-8", "replace")))
    ok = n >= chk["expected"] if chk["op"] == "ge" else n == chk["expected"]
    return ("OK" if ok else "DIFFERENCE", "found %d, the page says %s%d" % (n, "at least " if chk["op"] == "ge" else "", chk["expected"]))


def _all(chk, ctx):
    res = [run_check(c, ctx) for c in chk["checks"]]
    if any(v == "DIFFERENCE" for v, _ in res): return "DIFFERENCE", "; ".join(w for v, w in res if v == "DIFFERENCE")
    if any(v == "UNREAD" for v, _ in res): return "UNREAD", "; ".join(w for v, w in res if v == "UNREAD")
    return "OK", "; ".join(w for _, w in res)


KINDS = {"selectors": _selectors, "slots": _slots, "lines": _lines, "json": _json_check, "group_count": _group_count, "first_line_json": _first_line, "html_count": _html_count, "json_distinct": _json_distinct, "all": _all}


def run_check(chk, ctx):
    try: return KINDS[chk["kind"]](chk, ctx)
    except _Unread as e: return "UNREAD", str(e)


# the claims this script knows how to replay, with the value the PAGE says (read from the page, never from today's answer). Every other claim is UNREAD with its cause.
_V = [["getThreshold()", "0xe75235b8"], ["getOwners()", "0xa0e67e2b"], ["getMinDelay()", "0xf27a0c92"], ["delay()", "0x6a42b8f8"], ["getModulesPaginated(address,uint256)", "0xcc2f8452"], ["owner()", "0x8da5cb5b"], ["admin()", "0xf851a440"], ["hasRole(bytes32,address)", "0x91d14854"]]
_S = [["eip1967.proxy.admin", True, "0xb53127684a568b3173ae13b9f8a6016e243e63b6e8ee1178d6a717850b5d6103"], ["eip1967.proxy.beacon", True, "0xa3f0ad74e5423aebfd80d3ef4346578335a9a72aeaee59ff6cb3582b35133d50"], ["guard_manager.guard.address", False, "0x4a204f620c8c5ccdca3fd54d003badd85ba500436a431f0cbda4f558c93c34c8"]]
_ALERTS = {"kind": "json", "url": WATCH + "alerts.json", "path": "active", "op": "len_eq", "expected": 8}
_HOME = {"kind": "html_count", "url": SITE, "pattern": r'href="p/[A-Za-z0-9-]+\.html"', "op": "eq", "expected": 15}   # the card links only: the one link built by the page's script holds quotes and plus signs
CHECKS = {
    "R15": {"kind": "lines", "items": [["integrations/authority_facts_gate_strict.py", 46], ["integrations/authority_facts_gate.py", 18]]},
    "H01": {"kind": "all", "checks": [{"kind": "json", "url": SITE + "p/index.json", "path": "count", "op": "eq", "expected": 202}, {"kind": "json_distinct", "url": SITE + "p/index.json", "container": "addresses", "item_field": "key", "expected": 9}]},
    "H04": _HOME, "H29": _HOME,
    "H05": dict(_ALERTS, dated=True), "W04": _ALERTS,   # H05 is dated ("at build time"): a moved value is a stale expected result ; W04 is in the present tense: a moved value is a difference
    "H18": {"kind": "selectors", "items": [["getScore(address)", "0xd47875d0"], ["trackedTargets(uint256)", "0x9481e5e0"], ["trackedTargetsCount()", "0x835e2172"]]},
    "V05": {"kind": "all", "checks": [{"kind": "selectors", "items": _V}, {"kind": "slots", "items": _S}]},
    "V11": {"kind": "group_count", "url": WATCH + "second_opinion.json", "list_path": "results", "by": "kind", "expected": {"safe": 48, "unreadable": 39, "contract": 36, "timelock": 24, "squads": 17, "eoa": 16, "native": 16, "pda": 7}},
    "P05": {"kind": "first_line_json", "url": WATCH + "events.jsonl", "limit": 4000, "expect": {"seq": 1}, "startswith": {"run_utc": "2026-10-10"}},
}


# ---------------------------------------------------------------- registry, evaluation, report
def load_registry(path):
    with open(path, encoding="utf-8") as f: reg = json.load(f)["claims"]
    for c in reg:
        for k in ("id", "page", "where", "claim", "command", "elements"):
            if k not in c: raise ValueError("claim %s has no field %s" % (c.get("id"), k))
        if set(c["elements"]) != {"cmd", "pt", "ex", "net", "src"}: raise ValueError("claim %s: the five elements are cmd, pt, ex, net, src" % c["id"])
    return reg


def evaluate(registry, checks, ctx):
    ids = {c["id"] for c in registry}
    for k in checks:
        if k not in ids: raise KeyError("a check is attached to %s, which is not a claim of the registry" % k)
    rows = []
    for c in registry:
        g = grade(c["elements"])
        if c["id"] in checks: v, why = run_check(checks[c["id"]], ctx)
        else: v, why = "UNREAD", ("nothing to replay: the page holds no command for this claim" if g in "CD" else "a command or a named point is written on the page; this script has no replay for it yet")
        rows.append({"id": c["id"], "page": c["page"], "where": c["where"], "claim": c["claim"], "grade": g, "verdict": v, "why": why})
    return rows


def summary(rows):
    s = {"claims": len(rows), "OK": 0, "DIFFERENCE": 0, "UNREAD": 0}
    for r in rows: s[r["verdict"]] += 1
    s["grades"] = dict(sorted(collections.Counter(r["grade"] for r in rows).items()))
    return s


def exit_code(rows, strict=False):
    if any(r["verdict"] == "DIFFERENCE" for r in rows): return 1
    if not any(r["verdict"] == "OK" for r in rows): return 3
    if strict and any(r["verdict"] == "UNREAD" for r in rows): return 3
    return 0


def selftest():
    """plants false values and false failures; every one must be caught. Prints what it did; 0 only if all pass."""
    bad = []
    def expect(name, got, want):
        print("%-62s %s" % (name, "ok" if got == want else "FAILED: got %r, expected %r" % (got, want)))
        if got != want: bad.append(name)
    ctx = Context(repo=HERE + "/..", fetch=lambda u, limit=None: json.dumps({"count": 202, "active": [1] * 8}).encode(), now=parse_now("2026-11-14T07:00:00Z"), clock=lambda: parse_now("2026-11-14T07:00:00Z"))
    expect("keccak256 of the empty string", keccak256(b"").hex(), "c5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470")
    expect("true selector is OK", run_check({"kind": "selectors", "items": [["owner()", "0x8da5cb5b"]]}, ctx)[0], "OK")
    expect("PLANTED false selector is a DIFFERENCE", run_check({"kind": "selectors", "items": [["owner()", "0xdeadbeef"]]}, ctx)[0], "DIFFERENCE")
    expect("PLANTED false slot is a DIFFERENCE", run_check({"kind": "slots", "items": [["eip1967.proxy.admin", True, "0x" + "00" * 32]]}, ctx)[0], "DIFFERENCE")
    expect("PLANTED false line count is a DIFFERENCE", run_check({"kind": "lines", "items": [["scripts/replay_grade.py", 1]]}, ctx)[0], "DIFFERENCE")
    expect("PLANTED false count (page says 203, answer 202)", run_check({"kind": "json", "url": SITE + "p/index.json", "path": "count", "op": "eq", "expected": 203}, ctx)[0], "DIFFERENCE")
    expect("true count is OK", run_check({"kind": "json", "url": SITE + "p/index.json", "path": "count", "op": "eq", "expected": 202}, ctx)[0], "OK")
    def down(u, limit=None): raise OSError("refused")
    down_ctx = Context(repo=ctx.repo, fetch=down, now=ctx.now)
    expect("PLANTED refusal is UNREAD, not OK", run_check({"kind": "json", "url": SITE + "p/index.json", "path": "count", "op": "eq", "expected": 202}, down_ctx)[0], "UNREAD")
    expect("PLANTED missing field is UNREAD, not zero", run_check({"kind": "json", "url": SITE + "p/index.json", "path": "nope", "op": "eq", "expected": 0}, ctx)[0], "UNREAD")
    one = {"kind": "json", "url": SITE + "p/index.json", "path": "count", "op": "eq", "expected": 202}
    expect("a Watch window on the real clock forbids the read", run_check(one, Context(ctx.repo, ctx.fetch, ctx.now, clock=lambda: parse_now("2026-11-14T12:20:00Z")))[0], "UNREAD")
    expect("PLANTED --now 07:00 cannot hide the real window (12:20)", run_check(one, Context(ctx.repo, ctx.fetch, parse_now("2026-11-14T07:00:00Z"), clock=lambda: parse_now("2026-11-14T12:20:00Z")))[0], "UNREAD")
    expect("PLANTED +02:00 offset: 08:20+02:00 is 06:20Z, inside the window", in_watch_window(parse_now("2026-11-14T08:20:00+02:00")), True)
    ticks = iter(["2026-11-14T06:09:50Z", "2026-11-14T06:10:05Z"])
    expect("PLANTED clock enters the window between two requests: UNREAD", run_check({"kind": "all", "checks": [one, one]}, Context(ctx.repo, ctx.fetch, ctx.now, clock=lambda: parse_now(next(ticks))))[0], "UNREAD")
    served = lambda doc: Context(ctx.repo, lambda u, limit=None: (doc if isinstance(doc, bytes) else json.dumps(doc).encode()), ctx.now, clock=ctx.clock)
    al = dict(_ALERTS)
    expect("PLANTED errors field filled with no alert is UNREAD, not zero", run_check(al, served({"active": [], "errors": ["rpc refused"]}))[0], "UNREAD")
    expect("PLANTED first line with no seq is UNREAD", run_check(CHECKS["P05"], served(b'{"run_utc": "2026-10-10T21:01:36Z"}\n'))[0], "UNREAD")
    expect("PLANTED empty results list is UNREAD, not zero counts", run_check(CHECKS["V11"], served({"results": []}))[0], "UNREAD")
    expect("PLANTED dated claim whose value moved is UNREAD (stale), not a difference", run_check(CHECKS["H05"], served({"active": [1] * 5}))[0], "UNREAD")
    expect("a claim in the present tense whose value moved is a DIFFERENCE", run_check(CHECKS["W04"], served({"active": [1] * 5}))[0], "DIFFERENCE")
    expect("PLANTED two-part claim: 202 read but 8 chains is a DIFFERENCE", run_check(CHECKS["H01"], served({"count": 202, "addresses": {"a": [{"key": str(i)} for i in range(8)]}}))[0], "DIFFERENCE")
    expect("two-part claim: 202 and 9 chains is OK", run_check(CHECKS["H01"], served({"count": 202, "addresses": {"a": [{"key": str(i)} for i in range(9)]}}))[0], "OK")
    rows = evaluate([{"id": "X", "page": "p", "where": "w", "claim": "c", "command": "x", "elements": dict(cmd=0, pt=0, ex=0, net=None, src=0)}], {"X": {"kind": "selectors", "items": [["owner()", "0x0"]]}}, ctx)
    expect("PLANTED false value gives exit code 1", exit_code(rows), 1)
    expect("no claim read at all gives exit code 3", exit_code([{"verdict": "UNREAD"}]), 3)
    return 1 if bad else 0


def render(rows, now):
    out = ["Replay Grade v0.1, read at %s" % now.strftime("%Y-%m-%dT%H:%MZ"), "id    grade verdict     page                 claim / cause"]
    for r in rows:
        out.append("%-5s %-5s %-11s %-20s %s" % (r["id"], r["grade"], r["verdict"], r["page"], r["claim"][:70]))
        if r["verdict"] != "OK": out.append("%s %s" % (" " * 44, r["why"][:150]))
    s = summary(rows)
    out.append("claims %d: OK %d, DIFFERENCE %d, UNREAD %d (unread is not ok, and it is not zero) ; grades %s" % (s["claims"], s["OK"], s["DIFFERENCE"], s["UNREAD"], s["grades"]))
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--repo", default=os.path.abspath(os.path.join(HERE, ".."))); ap.add_argument("--claims", default=os.path.join(HERE, "replay_grade_claims.json"))
    ap.add_argument("--now"); ap.add_argument("--offline", action="store_true"); ap.add_argument("--json", action="store_true"); ap.add_argument("--strict", action="store_true")
    ap.add_argument("--only"); ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest: return selftest()
    ctx = Context(a.repo, default_fetch, parse_now(a.now), a.offline)
    reg = load_registry(a.claims)
    if a.only: keep = set(a.only.split(",")); reg = [c for c in reg if c["id"] in keep]
    rows = evaluate(reg, {k: v for k, v in CHECKS.items() if k in {c["id"] for c in reg}}, ctx)
    print(json.dumps({"read_at": ctx.now.strftime("%Y-%m-%dT%H:%M:%SZ"), "summary": summary(rows), "claims": rows}, ensure_ascii=False, indent=1) if a.json else render(rows, ctx.now))
    return exit_code(rows, a.strict)


if __name__ == "__main__":
    sys.exit(main())
