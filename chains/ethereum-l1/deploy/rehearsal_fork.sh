#!/usr/bin/env bash
# Ethereum L1 -- deploy_testnet full dress rehearsal on a local Sepolia fork.
#
# Why this script exists: the shared throwaway deployer
# (0xA08a76457b758aFF9702dBf5b870679E1232B715, keys/evm-testnet-shared.json)
# has 0 ETH on real Sepolia as of 2026-09-17 (confirmed live on 2 independent
# RPCs, see chains/ethereum-l1/data/deploy_rehearsal_2026-09-17.md) and an
# open "A faire" card already asks Spap to fund it via a faucet -- an agent
# cannot use a faucet. Rather than doing nothing this phase, this script
# proves out the ENTIRE deploy_testnet pipeline end to end against a local
# anvil fork of real Sepolia state, using anvil's own well-known default
# dev account (NOT the throwaway key -- no real or testnet-funded private
# key is used here, nothing here ever touches a real network).
#
# Re-run any time with: bash chains/ethereum-l1/deploy/rehearsal_fork.sh
# Requires: anvil/forge/cast (foundry), python3 with web3 installed, repo
# root as the working directory.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$REPO_ROOT"

FORK_RPC_URL="${FORK_RPC_URL:-https://ethereum-sepolia-rpc.publicnode.com}"
READ_RPC_URL="${READ_RPC_URL:-https://ethereum-rpc.publicnode.com}"
ANVIL_PORT="${ANVIL_PORT:-8546}"
ANVIL_HOST_URL="http://127.0.0.1:${ANVIL_PORT}"
# anvil's well-known default account #0 (public knowledge, printed by every
# anvil startup, never funded with anything real) -- explicitly NOT
# keys/evm-testnet-shared.json.
ANVIL_DEV_KEY="0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
ANVIL_DEV_ADDR="0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"

RUN_LOG_DIR="${RUN_LOG_DIR:-${TMPDIR:-/tmp}/rehearsal-ethereum-l1}"
mkdir -p "$RUN_LOG_DIR"
ANVIL_LOG="$RUN_LOG_DIR/anvil_fork.log"
BROADCAST_LOG="$RUN_LOG_DIR/deploy_broadcast.log"
PUSH_LOG="$RUN_LOG_DIR/push_scores.log"

echo "== 1/6: chain-id sanity check on the fork source (must be Sepolia, 11155111) =="
SRC_CHAIN_ID=$(~/.foundry/bin/cast chain-id --rpc-url "$FORK_RPC_URL")
echo "source RPC chain id: $SRC_CHAIN_ID"
if [ "$SRC_CHAIN_ID" != "11155111" ]; then
  echo "REFUSING: fork source is not Sepolia (got $SRC_CHAIN_ID)." >&2
  exit 1
fi

echo "== 2/6: starting anvil fork of Sepolia on port $ANVIL_PORT =="
~/.foundry/bin/anvil --fork-url "$FORK_RPC_URL" --port "$ANVIL_PORT" --chain-id 11155111 > "$ANVIL_LOG" 2>&1 &
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
if [ "$FORK_CHAIN_ID" != "11155111" ]; then
  echo "REFUSING: local fork is not reporting chain 11155111 (got $FORK_CHAIN_ID)." >&2
  exit 1
fi

echo "== 3/6: deploying AuthorityRiskOracle + ExampleConsumer to the fork (anvil dev key, not the real testnet key) =="
PRIVATE_KEY="$ANVIL_DEV_KEY" ~/.foundry/bin/forge script script/Deploy.s.sol \
  --rpc-url "$ANVIL_HOST_URL" \
  --broadcast \
  --private-key "$ANVIL_DEV_KEY" \
  --out /tmp/rehearsal-out --cache-path /tmp/rehearsal-cache \
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

echo "== 5/6: pushing live-rederived mainnet scores to the fork oracle =="
READ_RPC_URL="$READ_RPC_URL" \
ORACLE_RPC_URL="$ANVIL_HOST_URL" \
ORACLE_ADDRESS="$ORACLE_ADDRESS" \
PRIVATE_KEY="$ANVIL_DEV_KEY" \
python3 chains/ethereum-l1/deploy/update_scores_ethereum_l1.py \
  --read-rpc-url "$READ_RPC_URL" \
  --oracle-rpc-url "$ANVIL_HOST_URL" \
  --oracle-address "$ORACLE_ADDRESS" \
  | tee "$PUSH_LOG"

echo "== reading back getScore() for each target from the fork oracle =="
# Updated 2026-09-17 evening: this list now covers all 9 targets scorers.py
# tracks as of this run (was hardcoded to the original 4 -- USDtb, USDtb PSM
# and the 3 Ethena LayerZero OFTAdapters were promoted to real scorers this
# afternoon by an interactive session and this readback loop had gone stale).
for TARGET in \
  0x1F98431c8aD98523631AE4a59f267346ea31F984 \
  0x2f39d218133AFaB8F2B819B1066c7E434Ad94E9e \
  0xbE286431454714F511008713973d3B053A2d38f3 \
  0x2CC440b721d2CaFd6D64908D6d8C4aCC57F8Afc3 \
  0xC139190F447e929f090Edeb554D95AbB8b18aC1c \
  0x73E35C5c35A274E34AdE6EB13cC7f62aEE323728 \
  0x5d3a1ff2B6BAB83b63cd9AD0787074081a52eF34 \
  0x211Cc4DD073734dA055fbF44a2b4667d5e5fE5D2 \
  0x58538E6A46E07434d7E7375BC268D3cB839C0133 ; do
  echo "-- $TARGET --"
  ~/.foundry/bin/cast call "$ORACLE_ADDRESS" \
    "getScore(address)((uint8,uint8,uint8,uint8,uint8,uint8,uint64,bytes32))" \
    "$TARGET" --rpc-url "$ANVIL_HOST_URL"
done

echo "Rehearsal complete. Oracle address on fork (ephemeral, NOT a real deployment): $ORACLE_ADDRESS"
