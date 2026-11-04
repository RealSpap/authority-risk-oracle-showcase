"""What makes a published score file usable, in one place (30/10/2026).

`scripts/authority_check.py` (the CI gate, the GitHub Action and, through it, the local helper `scripts/mcp_server.py`) takes from this module what makes a score file usable: is it a score file, how old is it,
is the flag `stale` a boolean, is the composite a whole number from 0 to 100. `scripts/agent_tools.py` (which the installable package `authority-risk-mcp` carries byte for byte, see
packages/authority-risk-mcp/vendor_tools.py) takes from it whether a contract is retired in tvl_scope.json, and (since the second round of review) the same file, composite and stale-flag rules for `get_score` and `check_protocol`: a score file of unknown or old age, a composite that is not a whole number from 0 to 100 and a stale flag that is not true/false give `status: not_read` with the reason. This module is the one
copy of those rules.
Standard library only; nothing here reads the network or a key.

THE AGE LIMIT. `MAX_AGE_HOURS` is the one documented age limit of this repository's own checks: a score file older than this is UNREAD, never a pass. It is 48 hours, the limit the CI gate
and the local helper have always used. The installable package 0.1.0 still flags a snapshot older than 72 hours (`snapshot_stale`, without refusing it): that is a separate default of a
published version, left as it is; moving it to this constant is a decision for the next package release, not made here.
"""
import json, math, os, time

MAX_AGE_HOURS = 48
CLOCK_SKEW_SECONDS = 600   # a readAt this far in the future is a wrong clock or a wrong file, not a fresh one


def age_limit(v):
    """The age limit actually applied: v when it is a finite number above 0, else MAX_AGE_HOURS. A limit of 0 or nan must not switch the age check off."""
    if not isinstance(v, (int, float)) or isinstance(v, bool) or not math.isfinite(v) or v <= 0: return MAX_AGE_HOURS
    return v


def document_problem(doc, now=None, max_age_hours=MAX_AGE_HOURS):
    """Why a whole score file cannot be the basis of a verdict (a sentence), or None. Never raises."""
    if doc is None: return "the score file could not be read (no verdict, not a pass)"
    if not isinstance(doc, dict) or not isinstance(doc.get("targets", []), list): return "the score file is not a score file (no verdict, not a pass)"
    limit = age_limit(max_age_hours)
    ra = doc.get("readAt")
    if not isinstance(ra, (int, float)) or isinstance(ra, bool) or not math.isfinite(ra): return "the score file carries no readAt, so its age is unknown (no verdict on data of unknown age)"
    age = (time.time() if now is None else now) - ra
    if age < -CLOCK_SKEW_SECONDS: return "the score file is dated in the future (readAt): the clock or the file is wrong, no verdict"
    if age > limit * 3600: return "the score file was written %d hours ago (limit %d): the watch may have stopped, no verdict on stale data" % (age // 3600, limit)
    return None


def composite_problem(t):
    """Why a target's composite is not a number to decide on, or None: a whole number from 0 to 100 is expected (not a boolean, not 150)."""
    c = t.get("compositeScore")
    if not isinstance(c, int) or isinstance(c, bool) or not 0 <= c <= 100: return "the composite score was not read (a whole number from 0 to 100 is expected)"
    return None


def stale_problem(t):
    """Why the stale flag cannot be used, or None. `stale` must be the boolean true or false; absent, null or any other value is unknown."""
    if t.get("stale") is not True and t.get("stale") is not False: return "the stale flag is missing or not true/false: freshness is unknown (no verdict, not a pass)"
    return None


def scope_of(W, filename="tvl_scope.json"):
    """{'<chain>:<address>' in lower case: record} from the Watch's copy of data/tvl_scope.json. An absent or unreadable file is an empty scope: nothing is retired that nobody said was."""
    try:
        with open(os.path.join(W, filename), encoding="utf-8") as f: d = json.load(f)
    except (OSError, ValueError): return {}
    t = d.get("targets") if isinstance(d, dict) else None
    return {str(k).lower(): v for k, v in t.items() if isinstance(v, dict)} if isinstance(t, dict) else {}


def retired(scope, chain, address):
    """The scope record when the contract is marked retired there (the protocol's money does not sit behind it), else None. `chain` is the Watch's key (robinhood, base, ethereum-l1 ...)."""
    r = scope.get(("%s:%s" % (chain, address)).lower())
    return r if isinstance(r, dict) and r.get("scope") == "retired" else None


def canonical(manifest):
    """The bytes the Watch signs: the canonical JSON of the manifest (keys sorted, no spaces)."""
    return json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()


def signature_check(sig, pins=(), files=None):
    """(kind, sentence) for a parsed signature.json; kind is 'ok', 'fail' or 'incomplete' (the signature could not be checked at all: PyNaCl missing).

    pins    the public keys (hex) that are accepted; empty = any key (the signature then proves the files match what THAT key signed, not who holds it).
    files   {name in the manifest: sha256 hex of the bytes you actually read}: each must be the hash the manifest lists. A name the manifest does not list is a failure: a signature from an
            earlier run (signing was refused and the old signature.json was published again) does not cover a file written by a later one.
    """
    m = sig.get("manifest") if isinstance(sig, dict) else None
    if not isinstance(m, dict) or not isinstance(m.get("files"), dict): return "fail", "signature.json has no manifest"
    if sig.get("signed") is not True: return "fail", "the run is unsigned (no signing key was set): nobody vouches for the manifest"
    pk = str(sig.get("public_key", "")).lower()
    if pins and pk not in {str(p).lower() for p in pins}: return "fail", "signed by a key that is not pinned (%s...)" % pk[:12]
    try: from nacl.signing import VerifyKey
    except ImportError: return "incomplete", "PyNaCl is not installed, so the signature was not checked (pip install pynacl)"
    try: VerifyKey(bytes.fromhex(pk)).verify(canonical(m), bytes.fromhex(str(sig.get("signature", ""))))
    except Exception as e: return "fail", "the signature is not valid (%s)" % type(e).__name__   # noqa: BLE001 -- any failure to verify is a failure
    for name, sha in sorted((files or {}).items()):
        if m["files"].get(name) != sha: return "fail", "%s is not the file the manifest signed (the signature may belong to an earlier run, or the file was changed)" % name
    return "ok", "signed by %s...%s, manifest of run %s (run time not signed)%s" % (pk[:12], " (pinned)" if pins else " (not pinned)", sig.get("run_utc"), (", covers " + ", ".join(sorted(files))) if files else ", but covers no score file that was read")
