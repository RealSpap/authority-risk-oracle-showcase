#!/bin/bash
# Replays the tests on a fork of Ethereum mainnet at block 26192453 (read only: no transaction is sent; the node is only queried).
#   bash fetch.sh        once: downloads the reference contracts of ethereum/ERCs at the pinned commit and checks their sha256
#   NODE=<archive node URL> bash jouer.sh      NODE: an archive node of Ethereum mainnet that can read block 26192453; if unset, a public gateway is used, which can limit old state or the request rate (then use your own node)
set -u
cd "$(dirname "$0")"; export PATH="$PATH:$HOME/.foundry/bin"
BLK=26192453; NODE="${NODE:-https://gateway.tenderly.co/public/mainnet}"; OUT="${OUT:-sorties}"; mkdir -p "$OUT"
run() { # $1 output name, $2 contract, $3 mutant ("none" for the real run)
  MUTANT="$3" forge test --root . --fork-url "$NODE" --fork-block-number $BLK --no-storage-caching --match-contract "$2" -vv -j 1 --fork-retries 30 --fork-retry-backoff 400 > "$OUT/$1.txt" 2>&1
  echo "== $1 (MUTANT=$3): $(grep -E 'Suite result' "$OUT/$1.txt" | sed 's/ finished.*//')"
  grep -E '^\[(PASS|FAIL)' "$OUT/$1.txt" | sed 's/ (gas.*//; s/ (block.*//' | sort -u
  grep -h 'OBS|' "$OUT/$1.txt" | sed 's/^ *//' | sort -u > "$OUT/lignes-OBS-$1.txt"
}
date -u +%FT%TZ | tee "$OUT"/start-time.txt
run aliases-real TwoAliasesTest none
run aliases-mutant-skipsecond TwoAliasesTest skipsecond
run coordinator-real CompleteCoordinatorTest none
for m in verify continuity liveness-decision deadline liveness-execution; do run coordinator-mutant-$m CompleteCoordinatorTest $m; done
date -u +%FT%TZ | tee "$OUT"/end-time.txt
