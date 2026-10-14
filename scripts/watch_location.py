"""Where the state of the Watch is published: the root of the `watch-data` branch of this repository (since 2026-10; before that, `watch/` on main).

`main` holds the code and the human-written documents; every run of the Watch commits what it read to `watch-data`, so that the history of `main` is the history of the work.
In the Action's job the branch is cloned INTO `watch/`, so the scripts keep their `watch/...` paths; only the public URLs change. A link written before the move,
https://github.com/RealSpap/authority-risk-oracle-showcase/blob/main/watch/status.json, still answers on main with a small notice that says where the live file is.
"""
REPO = "RealSpap/authority-risk-oracle-showcase"
DATA_BRANCH = "watch-data"
RAW = "https://raw.githubusercontent.com/%s/%s/" % (REPO, DATA_BRANCH)   # the root of the branch is the old watch/ folder: RAW + "status.json", RAW + "scores/base-sepolia.json"
BROWSE = "https://github.com/%s/tree/%s/" % (REPO, DATA_BRANCH)
NO_STATE_HINT = " (the state of the Watch is committed to the watch-data branch, not to main: run `bash scripts/watch_branch.sh prepare` to clone it into watch/)"
