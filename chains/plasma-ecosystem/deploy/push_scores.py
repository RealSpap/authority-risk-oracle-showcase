#!/usr/bin/env python3
"""
Plasma Ecosystem score pusher -- modeled directly on the repo root's
`scripts/update_scores.py` and the Arbitrum/Base siblings
(`chains/arbitrum-ecosystem/deploy/push_scores.py`,
`chains/base-ecosystem/deploy/push_scores.py`): re-derive every tracked
target's score live, then push via `AuthorityRiskOracle.updateScores()`.

Usage (--dry-run, this phase -- read-only, no transaction, no PRIVATE_KEY
needed):
    READ_RPC_URL=https://rpc.plasma.to \
    python3 chains/plasma-ecosystem/deploy/push_scores.py --dry-run

Usage (real send, future deploy_testnet phase, once the oracle is deployed
on Plasma testnet and the key is funded -- NOT done by this script alone,
needs Foundry's `forge script script/Deploy.s.sol --broadcast` first, same
sequence every other ecosystem in this project followed):
    READ_RPC_URL=https://rpc.plasma.to \
    ORACLE_RPC_URL=https://testnet-rpc.plasma.to \
    ORACLE_ADDRESS=0x... \
    PRIVATE_KEY=0x... \
    python3 chains/plasma-ecosystem/deploy/push_scores.py

READ_RPC_URL and ORACLE_RPC_URL are deliberately separate: every scored
target (Aquila, Aave V3, Pendle, Ethena, Euler V2, Fluid) is a real contract
that only exists on Plasma MAINNET (chain 9745), while AuthorityRiskOracle
itself would live on Plasma TESTNET (chain 9746) during a validation phase --
keeping the two apart means this script can't silently read stale/wrong
state if they ever diverge, same reasoning as every other ecosystem file in
this project.

--dry-run ALSO differs from the root script's --dry-run in one respect: it
goes one step further and actually ABI-ENCODES the updateScores() calldata
(using the real ORACLE_ABI below) and prints its hex, so a re-run of this
exact script is enough to prove the encoding step works end to end -- not
just that the Python-side scoring dicts look right. No transaction is built,
signed, or sent; ORACLE_RPC_URL/ORACLE_ADDRESS/PRIVATE_KEY are not read at
all in --dry-run mode.
"""
import os
import sys
import time

from web3 import Web3

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts", "lib"))
sys.path.insert(0, os.path.join(REPO_ROOT, "chains", "plasma-ecosystem"))

from web3_utils import get_w3  # noqa: E402
from scorers import score_all  # noqa: E402
from oracle_keys import assert_unique_oracle_keys  # noqa: E402

PLASMA_MAINNET_CHAIN_ID = 9745
PLASMA_TESTNET_CHAIN_ID = 9746

ORACLE_ABI = [
    {
        "name": "updateScores",
        "type": "function",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "targets", "type": "address[]"},
            {
                "name": "scores",
                "type": "tuple[]",
                "components": [
                    {"name": "adminKeyScore", "type": "uint8"},
                    {"name": "multisigScore", "type": "uint8"},
                    {"name": "timelockScore", "type": "uint8"},
                    {"name": "oracleAuthorityScore", "type": "uint8"},
                    {"name": "crossExposureScore", "type": "uint8"},
                    {"name": "compositeScore", "type": "uint8"},
                    {"name": "lastUpdated", "type": "uint64"},
                    {"name": "methodologyHash", "type": "bytes32"},
                ],
            },
        ],
        "outputs": [],
    }
]

METHODOLOGY_VERSION = "authority-risk-oracle-plasma-ecosystem-v1"


def methodology_hash() -> bytes:
    # keccak256, matching Solidity's keccak256(bytes) -- NOT sha256, same
    # discipline as the root script and every ecosystem sibling.
    return Web3.keccak(text=METHODOLOGY_VERSION)


def build_targets_and_tuples(scored, now, meth_hash):
    # The oracle keeps one score per address: refuse the whole push if two entries share one (scripts/lib/oracle_keys.py).
    assert_unique_oracle_keys(scored, where="(plasma push)")
    targets = []
    tuples = []
    for entry in scored:
        targets.append(Web3.to_checksum_address(entry["target"]))
        tuples.append(
            (
                entry["adminKeyScore"],
                entry["multisigScore"],
                entry["timelockScore"],
                entry["oracleAuthorityScore"],
                entry["crossExposureScore"],
                entry["compositeScore"],
                now,
                meth_hash,
            )
        )
    return targets, tuples


def main():
    dry_run = "--dry-run" in sys.argv

    read_rpc_url = os.environ.get("READ_RPC_URL", "https://rpc.plasma.to")
    read_w3 = get_w3(read_rpc_url)
    if not read_w3.is_connected():
        raise SystemExit(f"Could not connect to read RPC: {read_rpc_url}")
    if read_w3.eth.chain_id != PLASMA_MAINNET_CHAIN_ID:
        raise SystemExit(
            f"READ_RPC_URL resolved to chain ID {read_w3.eth.chain_id}, expected "
            f"{PLASMA_MAINNET_CHAIN_ID} (Plasma mainnet) -- these scorers target real "
            f"Plasma mainnet contracts, refusing to score against the wrong chain."
        )

    print(f"Reading target state from chain ID: {read_w3.eth.chain_id} (Plasma mainnet), block {read_w3.eth.block_number}")
    print("Re-deriving every tracked target's score from live chain state...\n")

    scored = score_all(read_w3)
    now = int(time.time())
    meth_hash = methodology_hash()

    for entry in scored:
        print(f"{entry['label']} ({entry['target']}): composite={entry['compositeScore']}/100, crossExposure={entry['crossExposureScore']}/100")

    targets, tuples = build_targets_and_tuples(scored, now, meth_hash)

    # Build the ABI-encoded updateScores() calldata regardless of dry-run or
    # not -- this is the one step this script exists to prove works, whether
    # or not it ever gets sent.
    oracle_iface = Web3().eth.contract(abi=ORACLE_ABI)
    calldata = oracle_iface.encode_abi("updateScores", args=[targets, tuples])

    print(f"\nEncoded updateScores() calldata ({len(calldata) // 2 - 1} bytes): {calldata}")
    print(f"methodologyHash = 0x{meth_hash.hex()}")
    print(f"Target chain for this calldata: Plasma testnet, chain ID {PLASMA_TESTNET_CHAIN_ID}")

    if dry_run:
        print("\n--dry-run set: calldata encoded above, but NOT sending a transaction, NOT reading ORACLE_RPC_URL/ORACLE_ADDRESS/PRIVATE_KEY.")
        return

    oracle_rpc_url = os.environ["ORACLE_RPC_URL"]
    oracle_address = os.environ["ORACLE_ADDRESS"]
    oracle_w3 = get_w3(oracle_rpc_url)
    if not oracle_w3.is_connected():
        raise SystemExit(f"Could not connect to oracle RPC: {oracle_rpc_url}")
    if oracle_w3.eth.chain_id != PLASMA_TESTNET_CHAIN_ID:
        raise SystemExit(
            f"ORACLE_RPC_URL resolved to chain ID {oracle_w3.eth.chain_id}, expected "
            f"{PLASMA_TESTNET_CHAIN_ID} (Plasma testnet) -- refusing to send to the wrong chain."
        )
    print(f"\nPushing to oracle on chain ID: {oracle_w3.eth.chain_id} (Plasma testnet)")

    private_key = os.environ["PRIVATE_KEY"]
    account = oracle_w3.eth.account.from_key(private_key)
    oracle = oracle_w3.eth.contract(address=Web3.to_checksum_address(oracle_address), abi=ORACLE_ABI)

    gas_price = int(oracle_w3.eth.gas_price * 1.25)
    tx = oracle.functions.updateScores(targets, tuples).build_transaction(
        {
            "from": account.address,
            "nonce": oracle_w3.eth.get_transaction_count(account.address),
            "gasPrice": gas_price,
        }
    )
    signed = account.sign_transaction(tx)
    tx_hash = oracle_w3.eth.send_raw_transaction(signed.raw_transaction)
    print(f"Sent updateScores() tx: {tx_hash.hex()}")

    receipt = oracle_w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
    status = "success" if receipt.status == 1 else "FAILED"
    print(f"Confirmed in block {receipt.blockNumber}: {status}")
    if receipt.status != 1:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
