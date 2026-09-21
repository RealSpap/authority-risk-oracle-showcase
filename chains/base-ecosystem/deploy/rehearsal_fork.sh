#!/usr/bin/env bash
# Base Ecosystem -- deploy_testnet full dress rehearsal on a local Base
# Sepolia fork.
#
# Why this script exists: the shared throwaway deployer
# (0xA08a76457b758aFF9702dBf5b870679E1232B715, keys/evm-testnet-shared.json)
# has 0 ETH on real Base Sepolia as of 2026-09-17 evening (confirmed live on
# 2 independent RPCs -- see chains/base-ecosystem/deploy/README.md and
# runs/2026-09-17-run2/base-ecosystem/claims_attempt1.txt), and no faucet
# with a captcha/login is allowed. Rather than doing nothing this phase,
# this script proves out the ENTIRE deploy_testnet pipeline end to end
# against a local anvil fork of real Base Sepolia state, using anvil's own
# well-known default dev account (NOT the throwaway key -- no real or
# testnet-funded private key is used here, nothing here ever touches a real
# network). Modeled directly on chains/ethereum-l1/deploy/rehearsal_fork.sh,
# parameterized for Base instead of Ethereum L1.
#
# Re-run any time with: bash chains/base-ecosystem/deploy/rehearsal_fork.sh
# Requires: anvil/forge/cast (foundry), python3 with web3 installed, repo
# root as the working directory.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$REPO_ROOT"

FORK_RPC_URL="${FORK_RPC_URL:-https://sepolia.base.org}"
READ_RPC_URL="${READ_RPC_URL:-https://mainnet.base.org}"
ANVIL_PORT="${ANVIL_PORT:-8547}"
ANVIL_HOST_URL="http://127.0.0.1:${ANVIL_PORT}"
# anvil's well-known default account #0 (public knowledge, printed by every
# anvil startup, never funded with anything real) -- explicitly NOT
# keys/evm-testnet-shared.json.
ANVIL_DEV_KEY="0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
ANVIL_DEV_ADDR="0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"

RUN_LOG_DIR="${RUN_LOG_DIR:-${TMPDIR:-/tmp}/rehearsal-base-ecosystem}"
mkdir -p "$RUN_LOG_DIR"
ANVIL_LOG="$RUN_LOG_DIR/anvil_fork.log"
BROADCAST_LOG="$RUN_LOG_DIR/deploy_broadcast.log"
PUSH_LOG="$RUN_LOG_DIR/push_scores.log"

echo "== 1/6: chain-id sanity check on the fork source (must be Base Sepolia, 84532) =="
SRC_CHAIN_ID=$(~/.foundry/bin/cast chain-id --rpc-url "$FORK_RPC_URL")
echo "source RPC chain id: $SRC_CHAIN_ID"
if [ "$SRC_CHAIN_ID" != "84532" ]; then
  echo "REFUSING: fork source is not Base Sepolia (got $SRC_CHAIN_ID)." >&2
  exit 1
fi

echo "== 2/6: starting anvil fork of Base Sepolia on port $ANVIL_PORT =="
~/.foundry/bin/anvil --fork-url "$FORK_RPC_URL" --port "$ANVIL_PORT" --chain-id 84532 > "$ANVIL_LOG" 2>&1 &
ANVIL_PID=$!
echo "anvil pid: $ANVIL_PID (log: $ANVIL_LOG)"

cleanup() {
  echo "== 6/6: stopping anvil (pid $ANVIL_PID) =="
  kill "$ANVIL_PID" 2>/dev/null || true
  wait "$ANVIL_PID" 2>/dev/null || true
}
trap cleanup EXIT

echo "waiting for anvil to accept connections..."
for i in $(seq 1 30); do
  if ~/.foundry/bin/cast chain-id --rpc-url "$ANVIL_HOST_URL" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
FORK_CHAIN_ID=$(~/.foundry/bin/cast chain-id --rpc-url "$ANVIL_HOST_URL")
echo "fork chain id: $FORK_CHAIN_ID"
if [ "$FORK_CHAIN_ID" != "84532" ]; then
  echo "REFUSING: local fork is not reporting chain 84532 (got $FORK_CHAIN_ID)." >&2
  exit 1
fi

echo "== 3/6: deploying AuthorityRiskOracle + ExampleConsumer to the fork (anvil dev key, not the real testnet key) =="
PRIVATE_KEY="$ANVIL_DEV_KEY" ~/.foundry/bin/forge script script/Deploy.s.sol \
  --rpc-url "$ANVIL_HOST_URL" \
  --broadcast \
  --private-key "$ANVIL_DEV_KEY" \
  --out /tmp/rehearsal-out-base --cache-path /tmp/rehearsal-cache-base \
  | tee "$BROADCAST_LOG"

ORACLE_ADDRESS=$(grep -A1 "AuthorityRiskOracle deployed at:" "$BROADCAST_LOG" | head -1 | awk '{print $NF}')
echo "Parsed ORACLE_ADDRESS: $ORACLE_ADDRESS"
if [ -z "$ORACLE_ADDRESS" ]; then
  echo "REFUSING: could not parse deployed oracle address from broadcast log." >&2
  exit 1
fi

echo "== 4/6: confirming deployer holds UPDATER_ROLE on the deployed oracle =="
UPDATER_ROLE=$(~/.foundry/bin/cast call "$ORACLE_ADDRESS" "UPDATER_ROLE()(bytes32)" --rpc-url "$ANVIL_HOST_URL")
echo "UPDATER_ROLE = $UPDATER_ROLE"
HAS_ROLE=$(~/.foundry/bin/cast call "$ORACLE_ADDRESS" "hasRole(bytes32,address)(bool)" "$UPDATER_ROLE" "$ANVIL_DEV_ADDR" --rpc-url "$ANVIL_HOST_URL")
echo "hasRole(UPDATER_ROLE, deployer) = $HAS_ROLE"
if [ "$HAS_ROLE" != "true" ]; then
  echo "REFUSING: deployer does not hold UPDATER_ROLE, cannot push scores." >&2
  exit 1
fi

echo "== 5/6: pushing live-rederived Base mainnet scores to the fork oracle =="
READ_RPC_URL="$READ_RPC_URL" \
ORACLE_RPC_URL="$ANVIL_HOST_URL" \
ORACLE_ADDRESS="$ORACLE_ADDRESS" \
PRIVATE_KEY="$ANVIL_DEV_KEY" \
python3 chains/base-ecosystem/deploy/push_scores.py \
  | tee "$PUSH_LOG"

echo "== reading back getScore() for each target from the fork oracle, and comparing to a freshly re-derived score =="
python3 - "$ORACLE_ADDRESS" "$ANVIL_HOST_URL" "$READ_RPC_URL" <<'PYEOF'
import sys, os
sys.path.insert(0, "scripts/lib")
sys.path.insert(0, "chains/base-ecosystem")
from web3_utils import get_w3
from scorers import score_all
from web3 import Web3

oracle_address, anvil_url, read_rpc = sys.argv[1], sys.argv[2], sys.argv[3]

ORACLE_ABI = [{
    "name": "getScore", "type": "function", "stateMutability": "view",
    "inputs": [{"type": "address"}],
    "outputs": [{"type": "tuple", "components": [
        {"name": "adminKeyScore", "type": "uint8"},
        {"name": "multisigScore", "type": "uint8"},
        {"name": "timelockScore", "type": "uint8"},
        {"name": "oracleAuthorityScore", "type": "uint8"},
        {"name": "crossExposureScore", "type": "uint8"},
        {"name": "compositeScore", "type": "uint8"},
        {"name": "lastUpdated", "type": "uint64"},
        {"name": "methodologyHash", "type": "bytes32"},
    ]}],
}]

anvil_w3 = get_w3(anvil_url)
oracle = anvil_w3.eth.contract(address=Web3.to_checksum_address(oracle_address), abi=ORACLE_ABI)

read_w3 = get_w3(read_rpc)
fresh = score_all(read_w3)

all_match = True
for entry in fresh:
    onchain = oracle.functions.getScore(Web3.to_checksum_address(entry["target"])).call()
    onchain_composite = onchain[5]
    fresh_composite = entry["compositeScore"]
    match = onchain_composite == fresh_composite
    all_match = all_match and match
    print(f"{entry['label']}: on-chain composite={onchain_composite} vs freshly-computed={fresh_composite} -> {'MATCH' if match else 'MISMATCH'}")

if all_match:
    print("All 5 on-chain scores match freshly-computed scores exactly.")
else:
    print("MISMATCH DETECTED -- see above.")
    sys.exit(1)
PYEOF

echo "Rehearsal complete. Oracle address on fork (ephemeral, NOT a real deployment): $ORACLE_ADDRESS"
