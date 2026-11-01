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

--verify-signature (30/10/2026, off by default: without it nothing above changes) also reads signature.json (next to the score files, or --signature PATH_OR_URL), checks its Ed25519 signature with PyNaCl
against the published key (and any key given with --pin), and checks that each score file it read is byte for byte the file the manifest signed: a score file written by a later run than the signature
(signing was refused and the old signature.json was published again) fails with SIGNATURE FAIL, a missing or unreadable signature.json or a missing PyNaCl is SIGNATURE UNREAD / INCOMPLETE (exit 3, and --allow-unread does not turn it into a pass). A valid
signature shows that the files are what that key signed, not who holds the key; the age limit above is separate and still applies. The score-file rules and the age limit live in scripts/snapshot_rules.py (MAX_AGE_HOURS); agent_tools.py takes only its retired filter from it. `--pin` here adds keys to the published one (in sign_run.py `--pin` means only these keys).

Exit 0: every contract passes. Exit 1: at least one fails (below the minimum, falling, stale, not tracked). Exit 3: a score file could not be read
(network, 404): never a pass and never a score of 0; --allow-unread turns it into a warning for a workflow that must not depend on the network.
"""
import argparse, http.client, json, math, os, sys, time, urllib.request

from watch_location import RAW  # noqa: E402
import snapshot_rules as rules  # noqa: E402  -- what makes a score file usable, in one place; the age limit is rules.MAX_AGE_HOURS
BASE = RAW + "scores/"   # the published score files, on the watch-data branch
FILES = {"robinhood": "robinhood-chain", "ethereum-l1": "ethereum-l1-sepolia", "arbitrum": "arbitrum-sepolia", "base": "base-sepolia", "tempo": "tempo-moderato",
         "plasma": "plasma", "monad": "monad", "hyperliquid": "hyperliquid-hyperevm", "solana": "solana-devnet"}


def load_bytes(chain, source):
    """The bytes of the score file of a chain, or None when they cannot be read (an unread file is never an empty one)."""
    name = FILES.get(chain)
    if name is None: return None
    try:
        if source and not source.startswith("http"):
            with open(os.path.join(source, name + ".json"), "rb") as f: return f.read()
        with urllib.request.urlopen(urllib.request.Request((source or BASE).rstrip("/") + "/" + name + ".json", headers={"User-Agent": "authority-check/1"}), timeout=25) as r:
            return r.read()
    except (OSError, ValueError, http.client.HTTPException): return None      # a truncated answer (IncompleteRead) is an unread file, not a crash that exits 1 like a failed contract


def parse(raw):
    """The parsed score file, or None when the bytes are not JSON text."""
    try: return json.loads(raw.decode("utf-8")) if raw is not None else None
    except (ValueError, UnicodeDecodeError): return None


def load(chain, source):
    """The parsed score file of a chain, or None when it cannot be read (an unread file is never an empty one)."""
    return parse(load_bytes(chain, source))


def norm(chain):
    """base, Base or base-sepolia -> base (the names the other tools accept); anything else is returned lower-cased and judged unknown by check_one."""
    c = str(chain).strip().lower()
    return c if c in FILES else next((k for k, v in FILES.items() if v == c), c)


def check_one(chain, address, min_score, max_drop, doc, now=None, max_age_hours=rules.MAX_AGE_HOURS):
    """(verdict, text): verdict is 'ok', 'fail' or 'unread'."""
    chain = norm(chain); label = "%s:%s" % (chain, address)
    if chain not in FILES: return "fail", "FAIL %s: unknown chain (known: %s)" % (label, ", ".join(sorted(FILES)))
    why = rules.document_problem(doc, now, max_age_hours)   # unreadable, not a score file, no readAt, in the future, too old
    if why: return "unread", "UNREAD %s: %s" % (label, why)
    want = address if chain == "solana" else address.lower()   # a Solana address is case sensitive
    hits = [x for x in doc.get("targets", []) if isinstance(x, dict) and (str(x.get("target")) if chain == "solana" else str(x.get("target")).lower()) == want]
    if not hits: return "fail", "FAIL %s: not tracked by the oracle (no score to check; open an issue to ask for it)" % label
    if len(hits) > 1: return "unread", "UNREAD %s: listed %d times in the score file (which line is right is not known), no verdict" % (label, len(hits))
    t = hits[0]
    c = t.get("compositeScore")
    why = rules.composite_problem(t)
    if why: return "unread", "UNREAD %s: %s" % (label, why)
    parts = "admin %s, multisig %s, timelock %s" % (t.get("adminKeyScore"), t.get("multisigScore"), t.get("timelockScore"))
    if t.get("stale") is True: return "fail", "FAIL %s: the score is STALE (older than the oracle's staleness window), composite was %d (%s)" % (label, c, parts)
    why = rules.stale_problem(t)
    if why: return "unread", "UNREAD %s: %s" % (label, why)
    if c < min_score: return "fail", "FAIL %s: composite %d is under the minimum %d (%s)" % (label, c, min_score, parts)
    p = t.get("previousComposite")
    if max_drop is not None and isinstance(p, int) and not isinstance(p, bool) and p - c >= max_drop: return "fail", "FAIL %s: composite fell from %d to %d (%d points, limit %d) (%s)" % (label, p, c, p - c, max_drop, parts)
    return "ok", "OK   %s: composite %d (%s)" % (label, c, parts)


def signature_location(source, override=None):
    """Where signature.json is: --signature, else next to the `scores` folder or branch the score files come from (the Watch publishes scores/ and signature.json side by side)."""
    if override: return override
    if not source: return RAW + "signature.json"
    s = source.rstrip("/")
    return (s[:-len("scores")] if s.endswith("/scores") else s + "/") + "signature.json" if s.startswith("http") else os.path.join(os.path.dirname(os.path.abspath(s)) if os.path.basename(s) == "scores" else s, "signature.json")


def verify_signature(source, override, pins, raws):
    """(verdict, text) for --verify-signature. UNREAD when signature.json cannot be fetched or PyNaCl is missing (never a pass); FAIL when the signature is invalid, the key is not pinned, or a score
    file that was read is not the file the manifest signed. It proves the files are the ones THIS key signed in the run that signed them, not who holds the key: pin the key you trust."""
    loc = signature_location(source, override)
    try:
        if loc.startswith("http"):
            with urllib.request.urlopen(urllib.request.Request(loc, headers={"User-Agent": "authority-check/1"}), timeout=25) as r: sig = json.loads(r.read().decode("utf-8"))
        else:
            with open(loc, encoding="utf-8") as f: sig = json.load(f)
    except (OSError, ValueError, RecursionError, http.client.HTTPException): return "unread", "SIGNATURE UNREAD: signature.json could not be read at %s (no verdict, not a pass)" % loc
    import hashlib, audit_public
    kind, why = rules.signature_check(sig, tuple(audit_public.PINNED_KEYS) + tuple(pins or ()), {"scores/%s.json" % FILES[c]: hashlib.sha256(r).hexdigest() for c, r in raws.items()})
    return {"ok": "ok", "fail": "fail", "incomplete": "unread"}[kind], {"ok": "SIGNATURE ok: ", "fail": "SIGNATURE FAIL: ", "incomplete": "SIGNATURE INCOMPLETE: "}[kind] + why


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
    ap.add_argument("--min-score", type=int, default=0); ap.add_argument("--max-drop", type=int); ap.add_argument("--source"); ap.add_argument("--allow-unread", action="store_true"); ap.add_argument("--max-age-hours", type=positive_hours, default=rules.MAX_AGE_HOURS)
    ap.add_argument("--verify-signature", action="store_true", help="also verify signature.json (Ed25519, PyNaCl) and that each score file read is the one it signed")
    ap.add_argument("--signature", help="where signature.json is (path or https URL); default: next to the folder or branch the score files come from"); ap.add_argument("--pin", action="append", default=[], help="accept this signing key (hex) besides the published one; repeatable")
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
    docs, raws, fails, unread, sig_unread = {}, {}, 0, 0, False
    for chain, address, mn in targets:
        chain = norm(chain)
        if chain not in docs:
            raws[chain] = load_bytes(chain, a.source); docs[chain] = parse(raws[chain])   # one read: the bytes that are hashed are the bytes that are judged
        v, text = check_one(chain, address, mn, a.max_drop, docs[chain], max_age_hours=a.max_age_hours)
        out(text); fails += v == "fail"; unread += v == "unread"
    if a.verify_signature:
        v, text = verify_signature(a.source, a.signature, a.pin, {c: r for c, r in raws.items() if r is not None and c in FILES})
        out(text); fails += v == "fail"; sig_unread = v == "unread"   # --allow-unread covers a score file that could not be read, never a signature that was asked for and could not be checked
    if fails: return 1
    if (unread and not a.allow_unread) or sig_unread: return 3
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
