"""One identifier for one passage of the Watch, so that files can be shown to belong to the same run (30/10/2026).

A step of the Watch that fails does not stop the run: the file it should have rewritten stays as the run before left it, and is then committed with the files of the new run. The signed manifest
lists what is in the commit, not when each file was written. `run_id()` is the GitHub Actions run (`GITHUB_RUN_ID`) and its attempt (`GITHUB_RUN_ATTEMPT`), written as `<id>.<attempt>`; outside
GitHub Actions it is None and the writers add nothing, so a local run produces the files it always did. `scripts/check_run_id.py` compares the identifiers the files carry.
"""
import os


def current(env=None):
    """'<run id>.<attempt>' from the GitHub Actions environment, or None when this is not an Actions run (or the variables are not plain numbers)."""
    e = os.environ if env is None else env
    rid = str(e.get("GITHUB_RUN_ID") or "").strip()
    if not rid.isdigit(): return None
    att = str(e.get("GITHUB_RUN_ATTEMPT") or "1").strip()
    return "%s.%s" % (rid, att if att.isdigit() else "1")
