#!/usr/bin/env python3
"""
Monad score pusher -- modeled directly on the repo root's
`scripts/update_scores.py` and the Plasma/Tempo siblings
(`chains/plasma-ecosystem/deploy/push_scores.py`,
`chains/tempo/deploy/update_scores_solana.py`'s EVM cousins): re-derive
every tracked target's score live, then push via
`AuthorityRiskOracle.updateScores()`.

Usage (--dry-run -- read-only, no transaction, no PRIVATE_KEY needed):
    READ_RPC_URL=https://rpc.monad.xyz \
    python3 chains/monad/deploy/push_scores.py --dry-run

Usage (real send, once the oracle is deployed on Monad testnet and the key
is funded):
    READ_RPC_URL=https://rpc.monad.xyz \
    ORACLE_RPC_URL=https://testnet-rpc.monad.xyz/ \
    ORACLE_ADDRESS=0x... \
    PRIVATE_KEY=0x... \
    python3 chains/monad/deploy/push_scores.py

PRIVATE_KEY is the raw hex value, not a file path. The actual value lives in a JSON file named by
work/ecosystems.json's own "key_file" field (a "private_key" field inside it, despite the file itself
being named ".env" -- confirmed live 2026-09-24, see scripts/repush_all_oracles.sh::read_key for the
exact extraction pattern):
    PRIVATE_KEY=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["private_key"])' <key_file>) \
    ...rest of the command above...

READ_RPC_URL and ORACLE_RPC_URL are deliberately separate: every scored
target (Echo Protocol/eBTC, the Monad Native Bridge, Curvance, Kuru,
Uniswap v4, Morpho, Curve) is a real contract that only exists on Monad
MAINNET (chain 143), while AuthorityRiskOracle itself lives on Monad
TESTNET (chain 10143) -- keeping the two apart means this script can't
silently read stale/wrong state if they ever diverge, same reasoning as
every other ecosystem file in this project.
"""
import os
import sys
import time

from web3 import Web3

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts", "lib"))
sys.path.insert(0, os.path.join(REPO_ROOT, "chains", "monad"))

from web3_utils import get_w3  # noqa: E402
from scorers import score_all  # noqa: E402
from oracle_keys import assert_unique_oracle_keys  # noqa: E402

MONAD_MAINNET_CHAIN_ID = 143
MONAD_TESTNET_CHAIN_ID = 10143

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

METHODOLOGY_VERSION = "authority-risk-oracle-monad-v1"

# methodologyHash tied to the scoring code since 2026-09-30 (scripts/lib/methodology.py). Loaded by path, not by
# putting scripts/lib on sys.path, so no chain-local module (e.g. a chain's own `scorers`) can be shadowed.
import importlib.util as _ilu  # noqa: E402
_spec = _ilu.spec_from_file_location("aro_methodology", os.path.join(REPO_ROOT, "scripts", "lib", "methodology.py"))
methodology = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(methodology)


def methodology_hash() -> bytes:
    # keccak256("<METHODOLOGY_VERSION>:<digest of every scoring file>") since 2026-09-30, see scripts/lib/methodology.py:
    # a fix of the scorer now changes the published hash, a change of the target's posture does not.
    return methodology.evm_hash("monad", METHODOLOGY_VERSION)


def build_targets_and_tuples(scored, now, meth_hash):
    # The oracle keeps one score per address: refuse the whole push if two entries share one (scripts/lib/oracle_keys.py).
    assert_unique_oracle_keys(scored, where="(monad push)")
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
    methodology.code_digest("monad")  # pin the code that runs now, before scoring
    if not dry_run:  # the published hash must match a commit
        methodology.require_committed("monad")

    read_rpc_url = os.environ.get("READ_RPC_URL", "https://rpc.monad.xyz")
    read_w3 = get_w3(read_rpc_url)
    if not read_w3.is_connected():
        raise SystemExit(f"Could not connect to read RPC: {read_rpc_url}")
    if read_w3.eth.chain_id != MONAD_MAINNET_CHAIN_ID:
        raise SystemExit(
            f"READ_RPC_URL resolved to chain ID {read_w3.eth.chain_id}, expected "
            f"{MONAD_MAINNET_CHAIN_ID} (Monad mainnet) -- these scorers target real "
            f"Monad mainnet contracts, refusing to score against the wrong chain."
        )

    print(f"Reading target state from chain ID: {read_w3.eth.chain_id} (Monad mainnet), block {read_w3.eth.block_number}")
    print("Re-deriving every tracked target's score from live chain state...\n")

    scored = score_all(read_w3)
    now = int(time.time())
    meth_hash = methodology_hash()
    print(methodology.describe("monad", METHODOLOGY_VERSION))
    if not dry_run:  # right before sending: the files must still be the ones pinned before scoring
        methodology.assert_unchanged("monad")

    for entry in scored:
        print(f"{entry['label']} ({entry['target']}): composite={entry['compositeScore']}/100, crossExposure={entry['crossExposureScore']}/100")

    targets, tuples = build_targets_and_tuples(scored, now, meth_hash)

    oracle_iface = Web3().eth.contract(abi=ORACLE_ABI)
    calldata = oracle_iface.encode_abi("updateScores", args=[targets, tuples])

    print(f"\nEncoded updateScores() calldata ({len(calldata) // 2 - 1} bytes): {calldata}")
    print(f"methodologyHash = 0x{meth_hash.hex()}")
    print(f"Target chain for this calldata: Monad testnet, chain ID {MONAD_TESTNET_CHAIN_ID}")

    if dry_run:
        print("\n--dry-run set: calldata encoded above, but NOT sending a transaction, NOT reading ORACLE_RPC_URL/ORACLE_ADDRESS/PRIVATE_KEY.")
        return

    oracle_rpc_url = os.environ["ORACLE_RPC_URL"]
    oracle_address = os.environ["ORACLE_ADDRESS"]
    oracle_w3 = get_w3(oracle_rpc_url)
    if not oracle_w3.is_connected():
        raise SystemExit(f"Could not connect to oracle RPC: {oracle_rpc_url}")
    if oracle_w3.eth.chain_id != MONAD_TESTNET_CHAIN_ID:
        raise SystemExit(
            f"ORACLE_RPC_URL resolved to chain ID {oracle_w3.eth.chain_id}, expected "
            f"{MONAD_TESTNET_CHAIN_ID} (Monad testnet) -- refusing to send to the wrong chain."
        )
    print(f"\nPushing to oracle on chain ID: {oracle_w3.eth.chain_id} (Monad testnet)")

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
