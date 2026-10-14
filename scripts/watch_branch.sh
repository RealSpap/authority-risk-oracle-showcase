#!/usr/bin/env bash
# Where the Watch keeps its state: the `watch-data` branch, cloned into ./watch for the length of a run (see scripts/watch_location.py).
#
#   bash scripts/watch_branch.sh prepare              before the first step that reads or writes watch/
#   bash scripts/watch_branch.sh record "<message>"   after a step that changed watch/: commit it to the branch and push the branch
#
# main is never written here. The documents written by hand (API.md, README.md, .gitignore, schema/) stay canonical on main and are copied into watch/ at every prepare, so that the
# scripts and the signed manifest see them; the state files of main's watch/ folder after the move are only small notices and are never copied.
#
# Environment: WATCH_REMOTE (default: the origin remote of this checkout); GITHUB_TOKEN (sent as an HTTP header for fetch and push, never written to disk or to the URL);
# WATCH_DATA_BRANCH (default watch-data); WATCH_REQUIRE_SEED=1 (the canonical repository: a missing branch is an error, because starting from nothing would break the chain of events;
# a fork leaves it unset and the branch is created empty).
set -euo pipefail
BRANCH="${WATCH_DATA_BRANCH:-watch-data}"
REMOTE="${WATCH_REMOTE:-$(git remote get-url origin 2>/dev/null || true)}"
DOCS="API.md README.md .gitignore schema names.json"   # names.json: the on-chain names of the untitled targets, maintained by hand and read by the cards
IDENT=(-c user.name=Spap -c user.email=335248717+RealSpap@users.noreply.github.com)
AUTH=()   # (bash 3.2 on a Mac: an empty array under set -u needs the +"" form below)
if [ -n "${GITHUB_TOKEN:-}" ]; then AUTH=(-c "http.https://github.com/.extraheader=AUTHORIZATION: basic $(printf x-access-token:%s "$GITHUB_TOKEN" | base64 | tr -d '\n')"); fi
[ -n "$REMOTE" ] || { echo "watch_branch: no remote to read the $BRANCH branch from (set WATCH_REMOTE)" >&2; exit 2; }

has_branch() { git ${AUTH[@]+"${AUTH[@]}"} ls-remote --exit-code --heads "$REMOTE" "$BRANCH" >/dev/null 2>&1; }

prepare() {
  local docs; docs="$(mktemp -d)"
  for d in $DOCS; do [ -e "watch/$d" ] && cp -R "watch/$d" "$docs/"; done   # the documents of main, before the folder is replaced
  rm -rf watch
  if has_branch; then
    git ${AUTH[@]+"${AUTH[@]}"} clone -q --depth 1 --branch "$BRANCH" "$REMOTE" watch
    echo "watch/: the $BRANCH branch at $(git -C watch rev-parse --short HEAD)"
  elif [ "${WATCH_REQUIRE_SEED:-}" = 1 ]; then
    echo "watch_branch: the $BRANCH branch does not exist on $REMOTE. Starting from nothing would break the chain of events: run the one-time migration (migrer-watch-vers-branche.sh) first." >&2
    exit 3
  else
    mkdir watch; git -C watch init -q -b "$BRANCH"
    echo "watch/: no $BRANCH branch yet, starting a new one (a first run: there is no previous state to compare with)"
  fi
  for d in $DOCS; do [ -e "$docs/$d" ] && { rm -rf "watch/$d"; cp -R "$docs/$d" "watch/$d"; }; done
  rm -rf "$docs"
}

record() {
  local msg="${1:?a commit message}"
  git -C watch add -A
  if git -C watch diff --cached --quiet; then echo "watch/: nothing to record"; return 0; fi
  git -C watch "${IDENT[@]}" commit -qm "$msg"
  local try
  for try in 1 2 3; do
    if git -C watch ${AUTH[@]+"${AUTH[@]}"} push -q "$REMOTE" "HEAD:refs/heads/$BRANCH"; then echo "watch/: recorded on $BRANCH at $(git -C watch rev-parse --short HEAD)"; return 0; fi
    echo "watch/: push refused (try $try), rebasing on the branch" >&2
    git -C watch ${AUTH[@]+"${AUTH[@]}"} fetch -q --depth 50 "$REMOTE" "$BRANCH" && git -C watch "${IDENT[@]}" rebase -q FETCH_HEAD || { git -C watch rebase --abort 2>/dev/null || true; echo "watch_branch: cannot rebase on $BRANCH" >&2; return 1; }
  done
  echo "watch_branch: the push to $BRANCH failed three times" >&2; return 1
}

case "${1:-}" in
  prepare) prepare ;;
  record) shift; record "$@" ;;
  *) echo "usage: watch_branch.sh prepare | record \"<message>\"" >&2; exit 2 ;;
esac
