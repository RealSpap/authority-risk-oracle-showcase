#!/usr/bin/env python3
"""Check the state a Watch run starts from, BEFORE the run extends it and signs it again.

The Watch keeps its state on the watch-data branch, and every run appends to some of its files (events.jsonl, history.jsonl, the history of alerts.json)
before signing the whole folder with the real key. A change pushed to that branch between two runs by someone who does not hold the key (a push by hand,
a leaked token) is unsigned at the moment of the push; if the next run did not look, it would continue the changed files and sign them, and the change
would then carry a valid signature. This script refuses that: the previous signature.json must verify (against a pinned key when one is given), every file
its manifest lists must still have the hash it had when it was signed, no file the manifest does not list may have appeared, and the event log must still
end at the head the manifest records.

A missing state is not an empty state. In a repository that signs (a key exists, or a key is pinned), a previous run with no signature.json is refused
whatever the event log looks like (absent, blank, unreadable or cut): deleting the signature and the log together must not read as "a first run", because
the run that follows would sign the emptied state with the real key. The first signed run of such a repository is started by hand with the bootstrap switch.
A repository with no key has nothing signed to protect: an absent log and no signature is its first run.

Going back: an older signed state put back on the branch is consistent and carries a good signature, so nothing inside the state tells it from the latest one.
The one thing that remembers what was already seen is the list of runs GitHub keeps for the workflow. The workflow passes the start time of the last
SUCCESSFUL run (--last-success-utc); the previous state must have been written by that run or a later one, judged by the run_utc of latest.json, which is a file
of the signed manifest (the run_utc written next to the manifest in signature.json is not signed and is never used for this). Without that date the check is
skipped and says so.

What is not compared: the documents that scripts/watch_branch.sh copies from main into watch/ at every prepare (DOCS there: API.md, README.md, schema/,
names.json; they come from main, not from the branch), and the `code` part of the manifest (main may have moved since the previous run).

    python3 scripts/check_previous_state.py --watch watch [--pin KEY | --pin published] [--require-signature] [--bootstrap] [--last-success-utc 2026-10-30T12:17:00Z]

  --pin KEY            the previous signature must be by this public key (hex; repeatable; `published` = audit_public.PINNED_KEYS). Also read from the
                       environment variable WATCH_PIN when no --pin is given; in the canonical repository (GITHUB_REPOSITORY equal to
                       watch_location.REPO) the default is `published`, so a state signed again by any other key is refused.
  --require-signature  an unsigned previous run is refused (the repository signs every run). Default: on when HAS_SIGNING_KEY is "true".
  --bootstrap          the single documented exception: accept a previous state that carries no signature at all (no signature.json, whatever the log, or a
                       manifest with "signed": false) for ONE run, the first signed one. The same switch is the environment variable WATCH_BOOTSTRAP=1 (the
                       repository variable only the owner can set), but that one counts ONLY when GITHUB_EVENT_NAME is workflow_dispatch, a run started by hand:
                       a scheduled run, or an environment that does not say, ignores it, so a variable left at 1 cannot let an attacker's emptied state through at 06:00. Every run that sees the switch
                       prints an ALARM line (used, ignored, or still set although the state is signed) so that it is never silent. It never accepts a signature
                       that does not verify, a key that is not pinned, or a file that differs from the manifest.
  --last-success-utc   (also WATCH_LAST_SUCCESS_UTC) the start time of the last successful run of this workflow, from GitHub's list of runs.

Exit 0: the previous state is the one that was signed (or, with no key anywhere, there is none: a first run). Exit 1: refused, with the reasons; the last line
starting with ALARM is the one the alarm gate reads. Exit 3: PyNaCl is not installed, so the signature could not be checked: INCOMPLETE, never a pass, and not
a finding about the state.
"""
import argparse, calendar, json, os, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import audit_public  # noqa: E402
import sign_run  # noqa: E402
import watch_location  # noqa: E402

MAIN_DOCS = ("API.md", "README.md", "names.json")   # as DOCS in scripts/watch_branch.sh (.gitignore is a hidden name, never in the manifest)
MAIN_DOC_DIRS = ("schema/",)


def from_main(rel):
    rel = rel.replace(os.sep, "/")
    return rel in MAIN_DOCS or rel.startswith(MAIN_DOC_DIRS)


def journal_state(watch):
    """'absent' (no such file), 'unreadable' (it exists and cannot be read), 'blank' (no line with a character in it) or 'lines'. Only 'absent' can be a first run, and only with no key."""
    p = os.path.join(watch, "events.jsonl")
    if not os.path.lexists(p):
        return "absent"
    try:
        with open(p, encoding="utf-8", errors="replace") as f:
            return "lines" if any(l.strip() for l in f) else "blank"
    except OSError:
        return "unreadable"


def utc(text):
    """Seconds since the epoch of a 2026-10-30T12:17:00Z date, or None when it is not one."""
    try:
        return calendar.timegm(time.strptime(str(text), "%Y-%m-%dT%H:%M:%SZ"))
    except (ValueError, TypeError, OverflowError):
        return None


ROLLBACK_SLACK_SECONDS = 300   # latest.json is stamped a few minutes after its run was created; the list of runs gives the creation time


def check(watch, pins=(), require_signature=False, bootstrap=False, last_success=None, event="", bootstrap_env=False):
    """(code, lines): code 0 accepted, 1 refused, 3 incomplete; lines say why. A line starting with ALARM must reach the alarm even when the run goes on.

    bootstrap: the switch was given on the command line (a person at a prompt). bootstrap_env: WATCH_BOOTSTRAP=1 in the environment (the repository variable): it counts
    only when `event` is workflow_dispatch, a run started by hand; any other event, or none, ignores it and says so."""
    out = []
    keyed = bool(pins) or require_signature   # this repository signs: a missing state is then a deleted one, not a new one
    sw = bool(bootstrap) or (bool(bootstrap_env) and event == "workflow_dispatch")
    if bootstrap_env and not sw:
        out.append("ALARM WATCH_BOOTSTRAP is set but this run was not started by hand (event %r): the switch is ignored. Remove the repository variable WATCH_BOOTSTRAP" % (event or "none"))
    sp = os.path.join(watch, "signature.json")
    if not os.path.exists(sp):
        js = journal_state(watch)
        if js == "absent" and not keyed:
            return 0, out + ["no signature.json and no event log, and this repository has no signing key: a first run, there is no previous state to check"]
        what = {"absent": "the event log is gone too", "blank": "the event log is empty", "unreadable": "the event log cannot be read", "lines": "an event log exists"}[js]
        if sw:
            return 0, out + ["ALARM WATCH_BOOTSTRAP accepted a previous state with no signature.json (%s): this run signs it with the real key. Remove the repository variable WATCH_BOOTSTRAP now" % what]
        return 1, out + ["REFUSED: signature.json is gone and %s: the previous state cannot be shown to be the one the Watch signed, and an empty or missing state is not a first run in a repository that signs (the first signed run is started by hand with WATCH_BOOTSTRAP=1)" % what]
    try:
        with open(sp, encoding="utf-8") as f:
            s = json.load(f)
        signed_m = s["manifest"]
        signed_files = signed_m["files"]
        if not isinstance(signed_files, dict):
            raise TypeError("manifest.files is not an object")
    except (OSError, ValueError, KeyError, TypeError) as e:
        return 1, out + ["REFUSED: the previous signature.json cannot be read (%s)" % str(e)[:120]]
    bad, notes = [], []
    unsigned_ok = False
    if s.get("signed") is True:
        pk = str(s.get("public_key", "")).lower()
        if pins and pk not in pins:
            bad.append("the previous run is signed by %s..., which is not a pinned key" % pk[:12])
        try:
            import nacl.signing as ns
        except ImportError:
            return 3, out + ["INCOMPLETE: PyNaCl is not installed, the signature of the previous run cannot be checked (pip install pynacl); this is not a pass and says nothing about the state"]
        try:
            ns.VerifyKey(bytes.fromhex(s["public_key"])).verify(sign_run.canonical(signed_m), bytes.fromhex(s["signature"]))
        except Exception as e:  # noqa: BLE001 -- any failure to verify is a refusal, never a pass
            bad.append("the signature of the previous manifest does not verify (%s)" % (str(e)[:80] or type(e).__name__))
    elif keyed:
        if sw:
            unsigned_ok = True
            notes.append("ALARM WATCH_BOOTSTRAP accepted a previous run that is unsigned: this run signs it with the real key. Remove the repository variable WATCH_BOOTSTRAP now")
        else:
            bad.append("the previous run is unsigned while this repository signs every run")
    else:
        notes.append("NOTE the previous run is unsigned: its files are compared with its manifest, which proves nothing about who wrote them")
    if sw and not unsigned_ok:
        notes.append("ALARM WATCH_BOOTSTRAP is still set although the previous run is signed (it is not needed): an attacker who empties the state would be let through by it. Remove the repository variable WATCH_BOOTSTRAP")
    try:
        now = sign_run.manifest(watch)
    except sign_run.Unsignable as e:
        return 1, out + ["REFUSED: the previous state holds a file the audit would refuse (%s)" % e]
    for f, h in sorted(signed_files.items()):
        if from_main(f):
            continue
        if f not in now["files"]:
            bad.append("%s is listed in the previous manifest and is gone" % f)
        elif now["files"][f] != h:
            bad.append("%s differs from the previous manifest" % f)
    for f in sorted(now["files"]):
        if f not in signed_files and not from_main(f):
            bad.append("%s is not in the previous manifest (added after signing)" % f)
    if signed_m.get("events_chain_head") != now["events_chain_head"]:
        bad.append("events.jsonl no longer ends at the head the previous manifest records")
    if last_success:
        # going back: an older state, signed by the real key, is whole and valid. Its date is read from latest.json, a file of the signed manifest (the run_utc next to the manifest is not signed).
        ref = utc(last_success)
        try:
            with open(os.path.join(watch, "latest.json"), encoding="utf-8") as f:
                ran = utc(json.load(f).get("run_utc"))
        except (OSError, ValueError, AttributeError):
            ran = None
        if ref is None:
            bad.append("the start time of the last successful run (%r) is not a date: the state cannot be placed in time" % str(last_success)[:40])
        elif ran is None:
            bad.append("latest.json carries no readable run_utc: the state cannot be placed in time, and a last successful run exists")
        elif ran < ref - ROLLBACK_SLACK_SECONDS:
            bad.append("the previous state is older than the last successful run (latest.json run_utc %s, that run started %s): an older state was put back on the branch" % (time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ran)), time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ref))))
    else:
        notes.append("NOTE no start time of a last successful run was given: an older signed state put back on the branch would not be noticed this run")
    if bad:
        return 1, out + notes + ["REFUSED: " + b for b in bad]
    return 0, out + notes + ["previous state: %d file(s) as signed, event log ends at the signed head" % sum(1 for f in signed_files if not from_main(f))]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--watch", default="watch")
    ap.add_argument("--pin", action="append", default=[])
    ap.add_argument("--require-signature", action="store_true", default=os.environ.get("HAS_SIGNING_KEY") == "true")
    ap.add_argument("--bootstrap", action="store_true")
    ap.add_argument("--last-success-utc", default=os.environ.get("WATCH_LAST_SUCCESS_UTC", "").strip())
    a = ap.parse_args(argv)
    raw = a.pin or [p for p in os.environ.get("WATCH_PIN", "").split(",") if p.strip()]
    if not raw and os.environ.get("GITHUB_REPOSITORY") == watch_location.REPO:
        raw = ["published"]   # the canonical repository: the previous run must be signed by the published key, whoever wrote signature.json
    pins = {k.lower() for p in raw for k in (audit_public.PINNED_KEYS if p.strip() == "published" else (p.strip(),))}
    code, lines = check(a.watch, pins, a.require_signature, a.bootstrap, a.last_success_utc or None, os.environ.get("GITHUB_EVENT_NAME", ""), os.environ.get("WATCH_BOOTSTRAP") == "1")
    for l in lines:
        print(l)
    if code == 1:
        why = next((l for l in lines if l.startswith("REFUSED")), "see the lines above")
        print("ALARM previous state refused: " + why.replace("REFUSED: ", "", 1)[:120])   # the alarm gate identifies a finding by this line; the Alarm step also opens an issue for a refusal whatever the gate says
    elif code == 3:
        print("ALARM previous state not checked: PyNaCl is not installed (not a finding about the state)")
    return code


if __name__ == "__main__":
    sys.exit(main())
