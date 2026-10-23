#!/usr/bin/env python3
"""One command that replays what this project publishes. No key, no account, public RPCs and public files only, standard library only, under two minutes.

    python3 scripts/prove.py                # from a clone of the repository
    python3 scripts/prove.py --selftest     # offline: plants a falsified value and checks that it comes out as a DIFFERENCE

Every line says OK, DIFFERENCE or UNREAD. An RPC error or a missing file is UNREAD, never a zero and never a pass. Exit 0: everything read and equal. Exit 1: at least one DIFFERENCE. Exit 2: nothing differs but something was UNREAD.

What it replays (the block at the top of the README shows its expected output):
  1. the Watch's published numbers against the chain: targets per oracle, methodology hash, push date, every sub-score of every target (eight EVM oracles and the Solana program, read with eth_call and getProgramAccounts);
  2. the same chain reads against CHANGELOG.md (hash, push date, target count per oracle) and against the README's example and api/scores.json;
  3. the published back-test (backtest/incidents.json on the site): its counts, its loss sums, its rate;
  4. Authority Facts v0.1 conformance (scripts/conformance.py) of every JSON twin published on the site.

What it does NOT prove: that a score is *right* (it proves the chain, the Watch and the changelog agree, not that the scorer read the real world correctly); that the score predicts an incident (the back-test reads write-ups, not the chain before the attack);
that the administrator keys of the oracle contracts are safe; anything about a chain whose public RPC did not answer (those lines say UNREAD).
"""
import calendar, concurrent.futures as cf, json, os, re, sys, time, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.join(HERE, "..")
sys.path.insert(0, HERE)
RAW = "https://raw.githubusercontent.com/RealSpap/authority-risk-oracle-showcase"
SITE = "https://realspap.github.io/oracle"
OK, DIFF, UNREAD = "OK", "DIFFERENCE", "UNREAD"
SEL_COUNT, SEL_TARGET, SEL_SCORE = "0x835e2172", "0x9481e5e0", "0xd47875d0"   # trackedTargetsCount(), trackedTargets(uint256), getScore(address)
# (Watch file, CHANGELOG name, oracle, public RPC). Same list as scripts/live_target_counts.py (several ecosystems share one oracle address: the same deployer key was at the same nonce).
O2 = "0x50840a7667baEa9D05ad4ae3dCeb384724b58720"
ORACLES = [
    ("robinhood-chain", "Robinhood Chain", "0x9BF45734D09bC7CA39238e767B2af9AAc62a7f52", "https://rpc.testnet.chain.robinhood.com/rpc"),
    ("ethereum-l1-sepolia", "Ethereum L1", "0xB6F8474ccC71AF477c31c2DF663B3942ddfbf906", "https://ethereum-sepolia-rpc.publicnode.com"),
    ("arbitrum-sepolia", "Arbitrum", O2, "https://sepolia-rollup.arbitrum.io/rpc"),
    ("base-sepolia", "Base", O2, "https://sepolia.base.org"),
    ("tempo-moderato", "Tempo", O2, "https://rpc.moderato.tempo.xyz"),
    ("plasma", "Plasma", O2, "https://testnet-rpc.plasma.to"),
    ("monad", "Monad", O2, "https://testnet-rpc.monad.xyz/"),
    ("hyperliquid-hyperevm", "Hyperliquid", O2, "https://rpc.hyperliquid-testnet.xyz/evm|https://998.rpc.thirdweb.com"),   # the first endpoint rate-limits (429): the second is tried when it does not answer
]
SUBS = ("adminKeyScore", "multisigScore", "timelockScore", "oracleAuthorityScore", "crossExposureScore", "compositeScore")
PUSH_TOLERANCE = 45 * 60   # the changelog gives the minute of the push; the oracle stores the push second of each target
DEADLINE = time.time() + 105


# ---------------------------------------------------------------- reads (the only part that touches the network)
def http_text(url, tries=3, timeout=25):
    for i in range(tries):
        try: return urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "authority-risk-oracle-prove/1"}), timeout=timeout).read().decode("utf-8", "replace")
        except Exception: time.sleep(1 + i)
    return None


def http_json(url):
    t = http_text(url)
    try: return json.loads(t) if t is not None else None
    except ValueError: return None


def rpc_batch(url, calls, tries=3):
    """calls = [(to, data)]; one JSON-RPC batch; returns the list of hex results, or None if the endpoint did not answer every call (never a partial list)."""
    body = json.dumps([{"jsonrpc": "2.0", "id": i, "method": "eth_call", "params": [{"to": to, "data": data}, "latest"]} for i, (to, data) in enumerate(calls)]).encode()
    for i in range(tries):
        try:
            resp = json.load(urllib.request.urlopen(urllib.request.Request(url, body, {"content-type": "application/json", "User-Agent": "authority-risk-oracle-prove/1"}), timeout=30))
            if isinstance(resp, dict): resp = [resp]
            by_id = {r.get("id"): r for r in resp if isinstance(r, dict)}
            if len(by_id) == len(calls) and all("result" in by_id[k] and isinstance(by_id[k]["result"], str) for k in range(len(calls))): return [by_id[k]["result"] for k in range(len(calls))]
        except Exception: pass
        time.sleep(1 + i)
    return None


def decode_score(h):
    b = bytes.fromhex(h[2:])
    if len(b) != 256: return None
    w = [int.from_bytes(b[i:i + 32], "big") for i in range(0, 256, 32)]
    return dict(zip(SUBS, w[:6]), lastUpdated=w[6], methodologyHash="0x" + b[224:256].hex())


def read_evm(rpc_urls, oracle):
    """Tries each public endpoint (separated by |) in turn. -> {"count": n, "targets": {address: score dict}} or None when none answered every call."""
    for u in rpc_urls.split("|"):
        r = read_evm_one(u, oracle)
        if r is not None: return r
    return None


def read_evm_one(rpc_url, oracle):
    r = rpc_batch(rpc_url, [(oracle, SEL_COUNT)])
    if not r: return None
    n = int(r[0], 16)
    addrs = []
    for lo in range(0, n, 40):
        part = rpc_batch(rpc_url, [(oracle, SEL_TARGET + "%064x" % i) for i in range(lo, min(n, lo + 40))])
        if part is None: return None
        addrs += ["0x" + h[-40:] for h in part]
    targets = {}
    for lo in range(0, len(addrs), 40):
        part = rpc_batch(rpc_url, [(oracle, SEL_SCORE + "0" * 24 + a[2:]) for a in addrs[lo:lo + 40]])
        if part is None: return None
        for a, h in zip(addrs[lo:lo + 40], part):
            s = decode_score(h)
            if s is None: return None
            targets[a] = s
    return {"count": n, "targets": targets}


def read_solana():
    import solana_oracle_reader as sr
    try: o = sr.read_oracle()
    except Exception: return None
    return {"count": len(o["tracked"]), "targets": {s["target"]: s for s in o["scores"]}}


# ---------------------------------------------------------------- pure comparisons (tested offline, with a planted falsified value)
def parse_changelog(text):
    """-> {oracle name: {"hash", "targets", "pushed"}} from the newest section whose table has a Pushed column."""
    for sec in re.split(r"\n### ", text):
        rows = re.findall(r"^\| ([^|]+?) \| `(0x[0-9a-f]{64})`(?: \((\d+) targets\))? \| (\d{4}-\d\d-\d\d \d\d:\d\dZ) \|$", sec, re.M)
        if rows:
            return {n: {"hash": h, "targets": int(c) if c else None, "pushed": float(calendar.timegm(time.strptime(p, "%Y-%m-%d %H:%MZ")))} for n, h, c, p in rows}
    return {}


def cmp_counts(chain, watch):
    """chain/watch: slug -> {"count"} / published file. -> (status, detail)."""
    bad, unread = [], []
    for slug, c in chain.items():
        w = watch.get(slug)
        if c is None or w is None: unread.append(slug); continue
        wn = len(w.get("targets", []))
        if c["count"] != wn or len(c["targets"]) != c["count"]: bad.append("%s chain %d / Watch %d" % (slug, c["count"], wn))
    if bad: return DIFF, "; ".join(bad)
    if unread: return UNREAD, "unread: " + ", ".join(unread)
    return OK, "%d oracles: targets per oracle on the chain = Watch (%s)" % (len(chain), " + ".join(str(c["count"]) for c in chain.values()))


def cmp_scores(chain, watch):
    """every sub-score, hash and push time of every target, chain against the Watch's published file."""
    n = bad = 0; unread = []
    for slug, c in chain.items():
        w = watch.get(slug)
        if c is None or w is None: unread.append(slug); continue
        wt = {t["target"].lower(): t for t in w.get("targets", [])}
        for a, s in c["targets"].items():
            t = wt.get(a.lower() if a.startswith("0x") else a)
            n += 1
            if t is None or any(t.get(k) != s[k] for k in SUBS + ("lastUpdated", "methodologyHash")): bad += 1
    if bad: return DIFF, "%d of %d targets differ between the chain and the Watch (a push since its last read, or an error)" % (bad, n)
    if unread: return UNREAD, "unread: " + ", ".join(unread)
    return OK, "%d targets: six sub-scores, push date and methodology hash identical on the chain and in the Watch" % n


def cmp_changelog(chain, names, cl):
    """hash, target count at that hash and push date per oracle against CHANGELOG.md; a target still under an older hash is counted and said."""
    bad, unread, older, n = [], [], 0, 0
    for slug, name in names.items():
        c, e = chain.get(slug), cl.get(name)
        if c is None or e is None: unread.append(name); continue
        at = [s for s in c["targets"].values() if s["methodologyHash"] == e["hash"]]
        older += len(c["targets"]) - len(at); n += 1
        last = max((s["lastUpdated"] for s in at), default=0)
        if e["targets"] is not None and len(at) != e["targets"]: bad.append("%s: %d targets at the CHANGELOG hash, it announces %d" % (name, len(at), e["targets"]))
        if not at or abs(last - e["pushed"]) > PUSH_TOLERANCE: bad.append("%s: last push %s, CHANGELOG %s" % (name, time.strftime("%d/%m %H:%MZ", time.gmtime(last)), time.strftime("%d/%m %H:%MZ", time.gmtime(e["pushed"]))))
    if bad: return DIFF, "; ".join(bad)
    if unread: return UNREAD, "unread: " + ", ".join(unread)
    return OK, "%d EVM oracles: methodology hash, target count and push date = CHANGELOG%s" % (n, " (%d target(s) keep an older hash, which the CHANGELOG says)" % older if older else "")


README_EXAMPLE_RE = re.compile(r"cast call (0x[0-9a-fA-F]{40}) \\\n\s+\"getScore[^\"]*\" \\\n\s+(0x[0-9a-fA-F]{40}) \\\n[^\n]*\n#[^\n]*\n# (\d+), (\d+), (\d+), (\d+), (\d+), (\d+),")


def parse_readme_example(text):
    """The example of the README (a `cast call` and the line of values under it) -> (oracle, target, six sub-scores) or None. The last two values (push time, hash) change at every push and are not compared."""
    m = README_EXAMPLE_RE.search(text or "")
    return (m.group(1).lower(), m.group(2).lower(), tuple(int(x) for x in m.groups()[2:8])) if m else None


def cmp_readme(chain, readme):
    """The example written in README.md against the chain: the named oracle, a tracked target, and the six values it prints."""
    ex = parse_readme_example(readme)
    if readme is None: return UNREAD, "README.md unread (run from a clone)"
    if ex is None: return UNREAD, "the README no longer has the example this script reads"
    oracle, addr, want = ex
    slug = next((s for s, _n, o, _r in ORACLES if o.lower() == oracle), None)
    if slug is None: return DIFF, "the README example names an oracle (%s…) that is not one of the nine" % oracle[:8]
    c = chain.get(slug)
    if c is None: return UNREAD, "the oracle of the README example was unread"
    s = c["targets"].get(addr)
    if s is None: return DIFF, "the README example target is not tracked by that oracle"
    got = tuple(s[k] for k in SUBS)
    return (OK, "README example: getScore(%s…%s) = %s" % (addr[:6], addr[-4:], ", ".join(map(str, got)))) if got == want else (DIFF, "README example: read %s, written %s" % (got, want))


def cmp_api(chain, api):
    """api/scores.json is the Robinhood table as of ONE push: same targets and scores as the chain, or a dated difference."""
    c = chain.get("robinhood-chain")
    if c is None or api is None: return UNREAD, "api/scores.json or the Robinhood oracle unread"
    rows = {r["target"].lower(): r for r in api["scores"]}
    diff = [a for a, s in c["targets"].items() if a not in rows or any(rows[a].get(k) != s[k] for k in SUBS)]
    pushed = max((s["lastUpdated"] for s in c["targets"].values()), default=0)
    hashes = {s["methodologyHash"] for s in c["targets"].values()}
    if api.get("methodologyHash") not in hashes:
        return DIFF, "api/scores.json carries the hash of %s (%s…), the chain was pushed on %s with another hash: the sub-scores are %s, the hash and the date are out of date" % (time.strftime("%d/%m", time.gmtime(api.get("generatedAt", 0))), str(api.get("methodologyHash"))[:10], time.strftime("%d/%m", time.gmtime(pushed)), "identical" if not diff else "different for %d target(s)" % len(diff))
    if diff or len(rows) != len(c["targets"]):
        return DIFF, "api/scores.json is from %s (%d targets), the chain was pushed on %s (%d targets): %d target(s) differ" % (time.strftime("%d/%m", time.gmtime(api.get("generatedAt", 0))), len(rows), time.strftime("%d/%m", time.gmtime(pushed)), len(c["targets"]), len(diff))
    return OK, "api/scores.json = the chain (%d Robinhood targets)" % len(rows)


def cmp_solana(sol, watch):
    w = watch.get("solana-devnet")
    if sol is None or w is None: return UNREAD, "Solana program or Watch file unread"
    wt = {t["target"]: t for t in w.get("targets", [])}
    bad = sum(1 for a, s in sol["targets"].items() if a not in wt or any(wt[a].get(k) != s[k] for k in SUBS + ("lastUpdated", "methodologyHash"))) + abs(len(wt) - len(sol["targets"]))
    return (DIFF, "Solana: %d difference(s) between the program and the Watch" % bad) if bad else (OK, "Solana (devnet): %d accounts read, scores and hash identical to the Watch's" % len(sol["targets"]))


def cmp_backtest(inc, page):
    """the published back-test: counts, loss sums and rate recomputed from incidents.json, against the headline numbers of the page."""
    if inc is None or page is None: return UNREAD, "backtest/incidents.json or the back-test page unread"
    sc = inc["in_scope"]; n = {k: sum(1 for x in sc if x["flagged"] == k) for k in ("yes", "no", "not measurable")}
    total, scope_loss, flagged_loss = sum(x["loss_usd"] for x in inc["incidents"]), sum(x["loss_usd"] for x in sc), sum(x["loss_usd"] for x in sc if x["flagged"] == "yes")
    txt = re.sub(r"<[^>]+>", " ", page)
    m = re.search(r"flagged (\d+), missed (\d+), and could not be applied to (\d+)", txt)
    if not m: return UNREAD, "the back-test page no longer has the expected sentence"
    want = (n["yes"], n["no"], n["not measurable"])
    if tuple(map(int, m.groups())) != want: return DIFF, "page: %s flagged/missed/not measurable, file: %s" % (m.groups(), want)
    sums = ("$%.1fB" % (total / 1e9), "$%.1fM" % (scope_loss / 1e6), "$%.1fM of the $" % (flagged_loss / 1e6))
    if not all(s in txt for s in sums): return DIFF, "loss sums: the file gives %s, the page does not carry them all" % (sums,)
    return OK, "back-test: %d incidents read, %d are about who controls a contract: %d flagged, %d missed, %d not measurable; rate %d/%d flagged (%d/%d of the measurable cases)" % (len(inc["incidents"]), len(sc), n["yes"], n["no"], n["not measurable"], n["yes"], len(sc), n["yes"], n["yes"] + n["no"])


def cmp_twins(results):
    """results: [(name, errs, diffs)] or None for a twin not read."""
    if not results: return UNREAD, "no JSON twin read"
    unread = sum(1 for r in results if r is None); rs = [r for r in results if r is not None]
    bad = sum(1 for r in rs if r[1]); diffs = sum(1 for r in rs if r[2])
    if bad: return DIFF, "Authority Facts v0.1: %d of %d twins break the specification" % (bad, len(rs))
    if unread: return UNREAD, "Authority Facts v0.1: %d of %d twins unread" % (unread, len(results))
    return OK, "Authority Facts v0.1: %d JSON twins of the site conform (conformance.py)%s" % (len(rs), ", %d with a declared difference" % diffs if diffs else "")


# ---------------------------------------------------------------- orchestration
def gather(log=lambda *_: None):
    names = {slug: name for slug, name, _o, _r in ORACLES}
    with cf.ThreadPoolExecutor(12) as ex:
        f_chain = {slug: ex.submit(read_evm, rpc, o) for slug, _n, o, rpc in ORACLES}
        f_sol = ex.submit(read_solana)
        f_watch = {slug: ex.submit(http_json, "%s/watch-data/scores/%s.json" % (RAW, slug)) for slug in list(names) + ["solana-devnet"]}
        f_inc = ex.submit(http_json, SITE + "/backtest/incidents.json"); f_page = ex.submit(http_text, SITE + "/backtest/"); f_idx = ex.submit(http_json, SITE + "/p/index.json")
        local = lambda f: open(os.path.join(ROOT, f), encoding="utf-8").read() if os.path.exists(os.path.join(ROOT, f)) else None
        cl_text, api_text, readme_text = local("CHANGELOG.md"), local("api/scores.json"), local("README.md")
        chain = {s: f.result() for s, f in f_chain.items()}; sol = f_sol.result(); watch = {s: f.result() for s, f in f_watch.items()}
        idx = f_idx.result()
        urls = []
        if isinstance(idx, dict) and isinstance(idx.get("addresses"), dict):
            urls = ["%s/p/%s-%s.json" % (SITE, pg["key"], a) for a, pgs in idx["addresses"].items() for pg in pgs if isinstance(pg, dict) and pg.get("key")]
        twins = list(ex.map(http_json, urls)) if urls else []
    schema = json.load(open(os.path.join(ROOT, "watch", "schema", "label.schema.json"), encoding="utf-8")) if os.path.exists(os.path.join(ROOT, "watch", "schema", "label.schema.json")) else None
    return {"readme": readme_text, "names": names, "chain": chain, "sol": sol, "watch": watch, "cl": parse_changelog(cl_text) if cl_text else None, "api": json.loads(api_text) if api_text else None,
            "inc": f_inc.result(), "page": f_page.result(), "twins": twins, "twin_urls": urls, "schema": schema}


def judge_twins(data):
    import conformance
    out = []
    for d in data["twins"]:
        if d is None or data["schema"] is None: out.append(None); continue
        errs, diffs = conformance.judge(d, data["schema"]); out.append(("", errs, diffs))
    return out


def lines(data):
    """-> [(status, text)] : the ten to fifteen lines of the report."""
    chain, watch = data["chain"], data["watch"]
    out = [cmp_counts(chain, watch), cmp_scores(chain, watch), cmp_solana(data["sol"], watch)]
    out.append(cmp_changelog(chain, data["names"], data["cl"]) if data["cl"] else (UNREAD, "CHANGELOG.md unread (run from a clone)"))
    out += [cmp_readme(chain, data.get("readme")), cmp_api(chain, data["api"]), cmp_backtest(data["inc"], data["page"]), cmp_twins(judge_twins(data))]
    return out


def render(res, secs):
    w = {OK: "OK        ", DIFF: "DIFFERENCE", UNREAD: "UNREAD    "}
    rows = ["%s %s" % (w[s], t) for s, t in res]
    n = {k: sum(1 for s, _t in res if s == k) for k in (OK, DIFF, UNREAD)}
    rows.append("%d OK, %d DIFFERENCE, %d UNREAD in %.0f s. Does not prove: that the scores are right, that they predict an incident, that the oracles' administrator keys are safe." % (n[OK], n[DIFF], n[UNREAD], secs))
    return rows, (1 if n[DIFF] else (2 if n[UNREAD] else 0))


def selftest():
    """Offline: a consistent world gives all OK; one falsified sub-score gives a DIFFERENCE; an unread oracle is UNREAD, never OK."""
    def score(i, h="0x" + "11" * 32): return dict(adminKeyScore=10 + i, multisigScore=20, timelockScore=30, oracleAuthorityScore=40, crossExposureScore=50, compositeScore=25, lastUpdated=1_790_000_000, methodologyHash=h)
    a1, a2 = "0x" + "aa" * 20, "0x" + "bb" * 20
    chain = {"robinhood-chain": {"count": 2, "targets": {a1: score(0), a2: score(1)}}}
    watch = {"robinhood-chain": {"targets": [dict(score(0), target=a1), dict(score(1), target=a2)]}}
    assert cmp_counts(chain, watch)[0] == OK and cmp_scores(chain, watch)[0] == OK
    bad = json.loads(json.dumps(watch)); bad["robinhood-chain"]["targets"][1]["timelockScore"] = 31          # the falsified value
    assert cmp_scores(chain, bad)[0] == DIFF, "a falsified value must come out as DIFFERENCE"
    assert cmp_counts(chain, {"robinhood-chain": {"targets": [dict(score(0), target=a1)]}})[0] == DIFF
    assert cmp_scores({"robinhood-chain": None}, watch)[0] == UNREAD and cmp_counts({"robinhood-chain": None}, watch)[0] == UNREAD
    cl = {"X": {"hash": "0x" + "11" * 32, "targets": 2, "pushed": 1_790_000_000.0}}
    assert cmp_changelog(chain, {"robinhood-chain": "X"}, cl)[0] == OK
    assert cmp_api(chain, {"scores": [dict(target=a1, **{k: score(0)[k] for k in SUBS}), dict(target=a2, **{k: score(1)[k] for k in SUBS})], "generatedAt": 1, "methodologyHash": "0x" + "11" * 32})[0] == OK
    assert cmp_api(chain, {"scores": [], "generatedAt": 1, "methodologyHash": "0x" + "99" * 32})[0] == DIFF   # a stale hash is a DIFFERENCE even when the sub-scores agree
    assert cmp_changelog(chain, {"robinhood-chain": "X"}, {"X": dict(cl["X"], targets=3)})[0] == DIFF
    assert cmp_changelog(chain, {"robinhood-chain": "X"}, {"X": dict(cl["X"], pushed=1_790_000_000.0 + 7200)})[0] == DIFF
    assert cmp_changelog(chain, {"robinhood-chain": "X"}, {"X": dict(cl["X"], hash="0x" + "22" * 32)})[0] == DIFF
    inc = {"incidents": [{"loss_usd": 1e9}, {"loss_usd": 2e8}], "in_scope": [{"loss_usd": 2e8, "flagged": "yes"}]}
    page = "flagged 1, missed 0, and could not be applied to 0 $1.2B $200.0M $200.0M of the $"
    assert cmp_backtest(inc, page)[0] == OK and cmp_backtest(inc, page.replace("flagged 1", "flagged 2"))[0] == DIFF and cmp_backtest(None, page)[0] == UNREAD
    assert render([(OK, "a"), (UNREAD, "b")], 1)[1] == 2 and render([(OK, "a"), (DIFF, "b"), (UNREAD, "c")], 1)[1] == 1 and render([(OK, "a")], 1)[1] == 0
    print("selftest ok")


def main():
    if "--selftest" in sys.argv: selftest(); return 0
    t0 = time.time(); data = gather(); res = lines(data); rows, code = render(res, time.time() - t0)
    print("\n".join(rows)); return code


if __name__ == "__main__":
    sys.exit(main())
