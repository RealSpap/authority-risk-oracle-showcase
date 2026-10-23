#!/usr/bin/env python3
"""A CI gate for authority risk: fail a build when a contract you depend on has a weak, falling or stale authority score (12/10/2026).

    python3 scripts/authority_check.py --chain base --address 0x... --min-score 60
    python3 scripts/authority_check.py --target base:0x...:60 --target solana:JUP6Lk...:40 --max-drop 10
    python3 scripts/authority_check.py --file authority-check.txt          # one `chain:address[:min-score]` per line, # comments allowed

As a GitHub Action (the same script, no install): see action.yml at the root of this repository.

Reads the published score files of the watch (watch/scores/<chain>.json, from raw.githubusercontent.com or from --source DIR). Standard library only.
A contract passes only if the oracle tracks it, its score was read and is not stale, the composite is at least --min-score (default 0 = presence and
freshness only), and it did not fall by --max-drop points or more since the previous run (the file carries previousComposite).
What counts as "read" (22/10/2026, after an adversarial pass): the file carries a numeric readAt that is not in the future and not older than --max-age-hours
(a finite number above 0: 0 or nan would switch the check off); the contract is listed once; `stale` is the boolean false (true fails; absent, null or
any other value is unread); the composite is a whole number from 0 to 100 (not a boolean, not 150). Anything else is UNREAD (exit 3), never a pass.
What it does not do: it does not verify signature.json, so it trusts the transport (https to raw.githubusercontent.com) and the folder you give it with --source;
`python3 scripts/audit_public.py` checks the signed manifest. The default age limit here is 48 hours: pass --max-age-hours to choose another. (The published MCP package 0.1.0 flags a snapshot older than 72 hours.)

Exit 0: every contract passes. Exit 1: at least one fails (below the minimum, falling, stale, not tracked). Exit 3: a score file could not be read
(network, 404): never a pass and never a score of 0; --allow-unread turns it into a warning for a workflow that must not depend on the network.
"""
import argparse, http.client, json, math, os, sys, time, urllib.request

from watch_location import RAW  # noqa: E402
BASE = RAW + "scores/"   # the published score files, on the watch-data branch
FILES = {"robinhood": "robinhood-chain", "ethereum-l1": "ethereum-l1-sepolia", "arbitrum": "arbitrum-sepolia", "base": "base-sepolia", "tempo": "tempo-moderato",
         "plasma": "plasma", "monad": "monad", "hyperliquid": "hyperliquid-hyperevm", "solana": "solana-devnet"}


def load(chain, source):
    """The parsed score file of a chain, or None when it cannot be read (an unread file is never an empty one)."""
    name = FILES.get(chain)
    if name is None: return None
    try:
        if source and not source.startswith("http"):
            with open(os.path.join(source, name + ".json"), encoding="utf-8") as f: return json.load(f)
        with urllib.request.urlopen(urllib.request.Request((source or BASE).rstrip("/") + "/" + name + ".json", headers={"User-Agent": "authority-check/1"}), timeout=25) as r:
            return json.loads(r.read().decode("utf-8"))
    except (OSError, ValueError, http.client.HTTPException): return None      # a truncated answer (IncompleteRead) is an unread file, not a crash that exits 1 like a failed contract


def norm(chain):
    """base, Base or base-sepolia -> base (the names the other tools accept); anything else is returned lower-cased and judged unknown by check_one."""
    c = str(chain).strip().lower()
    return c if c in FILES else next((k for k, v in FILES.items() if v == c), c)


def check_one(chain, address, min_score, max_drop, doc, now=None, max_age_hours=48):
    """(verdict, text): verdict is 'ok', 'fail' or 'unread'."""
    chain = norm(chain); label = "%s:%s" % (chain, address)
    if chain not in FILES: return "fail", "FAIL %s: unknown chain (known: %s)" % (label, ", ".join(sorted(FILES)))
    if doc is None: return "unread", "UNREAD %s: the score file could not be read (no verdict, not a pass)" % label
    if not isinstance(doc, dict) or not isinstance(doc.get("targets", []), list): return "unread", "UNREAD %s: the score file is not a score file (no verdict, not a pass)" % label
    if not isinstance(max_age_hours, (int, float)) or isinstance(max_age_hours, bool) or not math.isfinite(max_age_hours) or max_age_hours <= 0: max_age_hours = 48   # a limit of 0 or nan must not switch the check off
    ra = doc.get("readAt")
    if not isinstance(ra, (int, float)) or isinstance(ra, bool) or not math.isfinite(ra): return "unread", "UNREAD %s: the score file carries no readAt, so its age is unknown (no verdict on data of unknown age)" % label
    age = (time.time() if now is None else now) - ra
    if age < -600: return "unread", "UNREAD %s: the score file is dated in the future (readAt): the clock or the file is wrong, no verdict" % label
    if age > max_age_hours * 3600: return "unread", "UNREAD %s: the score file was written %d hours ago (limit %d): the watch may have stopped, no verdict on stale data" % (label, age // 3600, max_age_hours)
    want = address if chain == "solana" else address.lower()   # a Solana address is case sensitive
    hits = [x for x in doc.get("targets", []) if isinstance(x, dict) and (str(x.get("target")) if chain == "solana" else str(x.get("target")).lower()) == want]
    if not hits: return "fail", "FAIL %s: not tracked by the oracle (no score to check; open an issue to ask for it)" % label
    if len(hits) > 1: return "unread", "UNREAD %s: listed %d times in the score file (which line is right is not known), no verdict" % (label, len(hits))
    t = hits[0]
    c = t.get("compositeScore")
    if not isinstance(c, int) or isinstance(c, bool) or not 0 <= c <= 100: return "unread", "UNREAD %s: the composite score was not read (a whole number from 0 to 100 is expected)" % label
    parts = "admin %s, multisig %s, timelock %s" % (t.get("adminKeyScore"), t.get("multisigScore"), t.get("timelockScore"))
    if t.get("stale") is True: return "fail", "FAIL %s: the score is STALE (older than the oracle's staleness window), composite was %d (%s)" % (label, c, parts)
    if t.get("stale") is not False: return "unread", "UNREAD %s: the stale flag is missing or not true/false: freshness is unknown (no verdict, not a pass)" % label
    if c < min_score: return "fail", "FAIL %s: composite %d is under the minimum %d (%s)" % (label, c, min_score, parts)
    p = t.get("previousComposite")
    if max_drop is not None and isinstance(p, int) and not isinstance(p, bool) and p - c >= max_drop: return "fail", "FAIL %s: composite fell from %d to %d (%d points, limit %d) (%s)" % (label, p, c, p - c, max_drop, parts)
    return "ok", "OK   %s: composite %d (%s)" % (label, c, parts)


def parse_target(s, default_min):
    bits = s.strip().split(":")
    if len(bits) < 2 or not bits[0] or not bits[1]: raise ValueError("expected chain:address[:min-score], got %r" % s)
    return bits[0].strip().lower(), bits[1].strip(), (int(bits[2]) if len(bits) > 2 and bits[2].strip() else default_min)


def positive_hours(v):
    """A whole number of hours above 0. 0, nan, inf and text are refused: they would turn the age check into no check."""
    try: n = int(v)
    except (TypeError, ValueError): raise argparse.ArgumentTypeError("%r is not a whole number of hours above 0" % v)
    if n <= 0: raise argparse.ArgumentTypeError("%d is not above 0: a limit of 0 would switch the age check off" % n)
    return n


def main(argv=None, out=print):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--chain"); ap.add_argument("--address"); ap.add_argument("--target", action="append", default=[]); ap.add_argument("--file")
    ap.add_argument("--min-score", type=int, default=0); ap.add_argument("--max-drop", type=int); ap.add_argument("--source"); ap.add_argument("--allow-unread", action="store_true"); ap.add_argument("--max-age-hours", type=positive_hours, default=48)
    a = ap.parse_args(argv)
    targets = []
    try:
        if a.chain or a.address:
            if not (a.chain and a.address): ap.error("--chain and --address go together")
            targets.append((a.chain.strip().lower(), a.address.strip(), a.min_score))
        targets += [parse_target(t, a.min_score) for t in a.target]
        if a.file:
            with open(a.file, encoding="utf-8") as f: targets += [parse_target(l.split("#")[0], a.min_score) for l in f if l.split("#")[0].strip()]
    except (ValueError, OSError) as e:
        out("ERROR: %s" % e); return 2
    if not targets: out("ERROR: nothing to check (give --chain/--address, --target or --file)"); return 2
    docs, fails, unread = {}, 0, 0
    for chain, address, mn in targets:
        chain = norm(chain)
        if chain not in docs: docs[chain] = load(chain, a.source)
        v, text = check_one(chain, address, mn, a.max_drop, docs[chain], max_age_hours=a.max_age_hours)
        out(text); fails += v == "fail"; unread += v == "unread"
    if fails: return 1
    if unread and not a.allow_unread: return 3
    return 0


def selftest():
    import tempfile
    def doc(*ts): return {"targets": list(ts), "readAt": time.time()}
    ok = {"target": "0xAAA0000000000000000000000000000000000001", "compositeScore": 65, "adminKeyScore": 70, "multisigScore": 80, "timelockScore": 20, "stale": False, "previousComposite": 66}
    cases = [(ok, 60, None, "ok"), (ok, 70, None, "fail"), ({**ok, "stale": True}, 0, None, "fail"), ({**ok, "previousComposite": 80}, 0, 10, "fail"), ({**ok, "previousComposite": 80}, 0, None, "ok"),
             ({**ok, "compositeScore": None}, 0, None, "unread")]
    for t, mn, md, want in cases: assert check_one("base", "0xaaa0000000000000000000000000000000000001", mn, md, doc(t))[0] == want, (t, mn, md, want)   # also: EVM addresses compare lower-cased
    assert check_one("base", "0xdead", 0, None, doc(ok))[0] == "fail"                       # not tracked is a failure, not a pass and not a zero
    assert check_one("base", "0xaaa", 0, None, None)[0] == "unread"                          # an unreadable file is neither
    assert check_one("solana", "AbC", 0, None, doc({"target": "abc", "compositeScore": 50, "stale": False}))[0] == "fail"   # Solana is case sensitive
    assert check_one("solana", "AbC", 0, None, doc({"target": "AbC", "compositeScore": 50, "stale": False}))[0] == "ok"
    assert check_one("mars", "0x1", 0, None, doc())[0] == "fail"
    A = "0xaaa0000000000000000000000000000000000001"   # the cases an adversarial pass found to pass (22/10/2026): each is unread, never ok
    assert check_one("base", A, 0, None, {"targets": [ok]})[0] == "unread"                                      # no readAt: the age is unknown
    assert check_one("base", A, 0, None, {**doc(ok), "readAt": time.time() + 7200})[0] == "unread"            # dated in the future
    assert check_one("base", A, 0, None, {**doc(ok), "readAt": 1_000_000}, now=1_000_000 + 99 * 3600, max_age_hours=0)[0] == "unread"   # a limit of 0 does not switch the check off
    for bad in ({k: v for k, v in ok.items() if k != "stale"}, {**ok, "stale": None}, {**ok, "stale": "False"}): assert check_one("base", A, 0, None, doc(bad))[0] == "unread", bad
    for bad in (True, 150, -5, 2 ** 63, 100.0, "65"): assert check_one("base", A, -10, None, doc({**ok, "compositeScore": bad}))[0] == "unread", bad
    assert check_one("base", A, 0, None, doc(ok, {**ok, "compositeScore": 5}))[0] == "unread"                  # the same contract twice: no line wins
    assert check_one("base", A, 0, None, [1, 2])[0] == "unread"                                                 # not a score file
    old = {**doc(ok), "readAt": 1_000_000}; assert check_one("base", "0xaaa0000000000000000000000000000000000001", 0, None, old, now=1_000_000 + 49 * 3600)[0] == "unread"          # a file older than 48 hours is no basis for a verdict
    assert check_one("base", "0xaaa0000000000000000000000000000000000001", 0, None, old, now=1_000_000 + 47 * 3600)[0] == "ok"
    assert check_one("base-sepolia", "0xaaa0000000000000000000000000000000000001", 0, None, doc(ok))[0] == "ok"                                                             # the slug works as well as the key
    with tempfile.TemporaryDirectory() as d:
        json.dump(doc(ok), open(os.path.join(d, "base-sepolia.json"), "w")); log = []
        assert main(["--source", d, "--target", "base:0xAAA0000000000000000000000000000000000001:60"], out=log.append) == 0, log
        assert main(["--source", d, "--target", "base:0xAAA0000000000000000000000000000000000001:99"], out=log.append) == 1
        assert main(["--source", d, "--target", "arbitrum:0x1"], out=log.append) == 3                       # arbitrum-sepolia.json is absent: unread
        assert main(["--source", d, "--target", "arbitrum:0x1", "--allow-unread"], out=log.append) == 0
        assert main(["--source", d, "--target", "base:0xdead", "--target", "arbitrum:0x1"], out=log.append) == 1   # a failure outranks an unread
        assert main(["--source", d], out=log.append) == 2
    print("selftest ok")


if __name__ == "__main__":
    if "--selftest" in sys.argv: selftest(); sys.exit(0)
    sys.exit(main())
