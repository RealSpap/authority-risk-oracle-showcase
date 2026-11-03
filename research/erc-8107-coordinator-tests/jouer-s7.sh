#!/bin/bash
# Replays S7 (test/Wrapped2LDGrace.t.sol) on a fork of Ethereum mainnet at block 26192453 (read only: no transaction is sent; the node is only queried).
# Real run, then one run with each coordinator step left out. Needs `forge install` and `bash fetch.sh` first (see README).
#   NODE=<archive node URL> OUT=<output folder> bash jouer-s7.sh
set -u
cd "$(dirname "$0")"; export PATH="$PATH:$HOME/.foundry/bin"
BLK=26192453; NODE="${NODE:-https://gateway.tenderly.co/public/mainnet}"; OUT="${OUT:-sorties}"; mkdir -p "$OUT"
run() { # $1 output name, $2 mutant ("none" for the real run)
  MUTANT="$2" forge test --root . --fork-url "$NODE" --fork-block-number $BLK --no-storage-caching --match-contract Wrapped2LDGraceTest --match-test testS7 -vv -j 1 --fork-retries 30 --fork-retry-backoff 400 > "$OUT/$1.txt" 2>&1
  echo "== $1 (MUTANT=$2): $(grep -E 'Suite result' "$OUT/$1.txt" | sed 's/ finished.*//')"
  grep -E '^\[(PASS|FAIL)' "$OUT/$1.txt" | sed 's/ (gas.*//; s/ (block.*//' | sort -u
  grep -h 'OBS|' "$OUT/$1.txt" | sed 's/^ *//' | sort -u > "$OUT/lignes-OBS-$1.txt"
}
date -u +%FT%TZ | tee "$OUT"/start-time-s7.txt
run wrapped2ld-real none
for m in verify continuity liveness-decision deadline liveness-execution; do run wrapped2ld-mutant-$m $m; done
date -u +%FT%TZ | tee "$OUT"/end-time-s7.txt
