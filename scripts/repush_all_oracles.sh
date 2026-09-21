#!/usr/bin/env bash
# Re-push every deployed testnet oracle so no tracked entry turns stale.
#
# Why: AuthorityRiskOracle has no removal function and `isStale()` is true for an entry nine days after its
# last update (maxStaleness), so an oracle nobody re-pushes silently goes stale for every target. Run
# `python3 scripts/oracle_freshness.py` to see when each one expires; push before that date.
#
# Run this yourself, from a clone of the repo. It is meant for the maintainer, never for an assistant or CI:
# a real run reads the two updater key files and sends one updateScores() transaction per oracle.
#
#   bash scripts/repush_all_oracles.sh                     # every oracle, real send
#   DRY=1 bash scripts/repush_all_oracles.sh               # recompute + encode only: no key read, nothing sent
#   ONLY="base plasma" bash scripts/repush_all_oracles.sh  # a subset (names: base plasma monad arbitrum l1 tempo hyperliquid solana robinhood)
#
# Keys (never printed, never written anywhere): KEYS_DIR/evm-testnet-shared/.env for base, plasma, monad,
# arbitrum, l1, tempo and hyperliquid; KEYS_DIR/robinhood-chain-testnet/.env for robinhood (its own updater
# key) -- confirmed live 2026-09-24 against work/ecosystems.json's own key_file field, the authoritative
# source if this ever drifts again. Both are JSON files (despite the .env name) with a "private_key" field.
# Solana takes a keypair FILE path (KEYS_DIR/solana-devnet/.env -- a raw solana-keygen-style JSON
# uint8[64] array despite the .env name, confirmed live 2026-09-24, matches work/ecosystems.json's
# own key_file field), not a key value. Override KEYS_DIR if your keys live elsewhere.
#
# Time: each step recomputes every target live before it sends. base/plasma/monad/arbitrum/l1 take about a
# minute each, tempo about 9 minutes, robinhood about 25 (run it alone in a second terminal:
# ONLY=robinhood bash scripts/repush_all_oracles.sh). A failing step does not stop the others; the exit
# code is non-zero if any step failed.
set -uo pipefail

cd "$(dirname "$0")/.."
KEYS_DIR="${KEYS_DIR:-$HOME/keys/authority-risk-oracle}"
SHARED_ORACLE=0x50840a7667baEa9D05ad4ae3dCeb384724b58720
ROBINHOOD_ORACLE=0x9BF45734D09bC7CA39238e767B2af9AAc62a7f52
L1_ORACLE=0xB6F8474ccC71AF477c31c2DF663B3942ddfbf906
DRYFLAG=""
if [ "${DRY:-}" = "1" ]; then DRYFLAG="--dry-run"; echo "DRY RUN: nothing will be sent and no key file is read"; fi
ONLY="${ONLY:-base plasma monad arbitrum l1 tempo hyperliquid solana robinhood}"
SOLANA_PROGRAM_ID=5VhiTAGLEViGgajhxPbzdWz7WLUAiRy42DY6qi6tYh4W

# Preflight, read-only and never blocking: has the code behind any tracked target changed since the last reviewed snapshot?
# A CHANGED target keeps its authority score but its code moved; read the new implementation before trusting the score, then
# `python3 scripts/check_implementation_changes.py --update`. See scripts/lib/implementation_watch.py.
echo "--- implementation watch (read-only) ---"
python3 scripts/check_implementation_changes.py || echo "^ REVIEW the CHANGED or UNREAD targets above (this does not stop the re-push)"
echo "-----------------------------------------"

read_key() {  # $1 = key file; prints the private key, only when actually sending
  python3 - "$1" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
k = d.get("private_key") or d.get("privateKey") or d.get("PRIVATE_KEY")
if not k:
    sys.exit("no private_key field in " + sys.argv[1] + "; its keys are: " + ", ".join(d.keys()))
print(k)
PY
}

wanted() { case " $ONLY " in *" $1 "*) return 0 ;; *) return 1 ;; esac; }
FAILED=""

step() {  # $1 = name, $2 = key file (shared or robinhood), rest = env assignments then command via eval
  local name="$1" keyfile="$2"; shift 2
  wanted "$name" || return 0
  echo
  echo "=== $name"
  if [ -z "$DRYFLAG" ]; then
    local key
    key="$(read_key "$KEYS_DIR/$keyfile")" || { echo "cannot read the key for $name"; FAILED="$FAILED $name"; return 0; }
    export PRIVATE_KEY="$key"
  fi
  if ! eval "$@ $DRYFLAG"; then FAILED="$FAILED $name"; fi
  unset PRIVATE_KEY
}

echo "--- freshness before"
python3 scripts/oracle_freshness.py || true

step base evm-testnet-shared/.env "READ_RPC_URL=https://mainnet.base.org ORACLE_RPC_URL=https://sepolia.base.org ORACLE_ADDRESS=$SHARED_ORACLE python3 chains/base-ecosystem/deploy/push_scores.py"
step plasma evm-testnet-shared/.env "READ_RPC_URL=https://rpc.plasma.to ORACLE_RPC_URL=https://testnet-rpc.plasma.to ORACLE_ADDRESS=$SHARED_ORACLE python3 chains/plasma-ecosystem/deploy/push_scores.py"
step monad evm-testnet-shared/.env "READ_RPC_URL=https://rpc.monad.xyz ORACLE_RPC_URL=https://testnet-rpc.monad.xyz/ ORACLE_ADDRESS=$SHARED_ORACLE python3 chains/monad/deploy/push_scores.py"
step arbitrum evm-testnet-shared/.env "READ_RPC_URL=https://arb1.arbitrum.io/rpc ORACLE_RPC_URL=https://sepolia-rollup.arbitrum.io/rpc ORACLE_ADDRESS=$SHARED_ORACLE python3 chains/arbitrum-ecosystem/deploy/push_scores.py"
step l1 evm-testnet-shared/.env "READ_RPC_URL=https://ethereum-rpc.publicnode.com ORACLE_RPC_URL=https://ethereum-sepolia-rpc.publicnode.com ORACLE_ADDRESS=$L1_ORACLE python3 chains/ethereum-l1/deploy/update_scores_ethereum_l1.py"
step tempo evm-testnet-shared/.env "ORACLE_RPC_URL=https://rpc.moderato.tempo.xyz ORACLE_ADDRESS=$SHARED_ORACLE python3 chains/tempo/deploy/push_scores.py"
step hyperliquid evm-testnet-shared/.env "ORACLE_RPC_URL=https://rpc.hyperliquid-testnet.xyz/evm ORACLE_ADDRESS=$SHARED_ORACLE python3 chains/hyperliquid/deploy/push_scores.py"

# Solana (Devnet, native program): a keypair file, no PRIVATE_KEY value is read by this script.
if wanted solana; then
  echo
  echo "=== solana"
  if ! eval "READ_RPC_URL=https://api.mainnet-beta.solana.com ORACLE_RPC_URL=https://api.devnet.solana.com ORACLE_PROGRAM_ID=$SOLANA_PROGRAM_ID KEYPAIR_FILE=$KEYS_DIR/solana-devnet/.env python3 chains/solana/deploy/update_scores_solana.py $DRYFLAG"; then FAILED="$FAILED solana"; fi
fi

step robinhood robinhood-chain-testnet/.env "READ_RPC_URL=https://rpc.mainnet.chain.robinhood.com ORACLE_RPC_URL=https://rpc.testnet.chain.robinhood.com/rpc ORACLE_ADDRESS=$ROBINHOOD_ORACLE python3 scripts/update_scores.py"

echo
echo "--- freshness after"
python3 scripts/oracle_freshness.py || true

if [ -n "$FAILED" ]; then echo "FAILED steps:$FAILED"; exit 1; fi
echo "All requested steps completed."
