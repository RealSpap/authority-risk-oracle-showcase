#!/usr/bin/env python3
"""
Ethereum L1 score-push script, parameterized on the model of the repo's
`scripts/update_scores.py` (Robinhood Chain) for this ecosystem's own
read/write split:

  READ  -- Ethereum L1 mainnet (chain 1): where the scored targets (9 as of
           2026-09-17: Uniswap V3 Factory, Aave V3 Pool, MakerDAO/Sky
           MCD_PAUSE, Ethena EthenaMinting, USDtb, USDtb PSM, and the 3
           Ethena LayerZero OFTAdapters) actually live and are re-derived
           live from, via chains/ethereum-l1/scorers.py.
  WRITE -- Ethereum Sepolia testnet (chain 11155111): where
           AuthorityRiskOracle.sol (src/AuthorityRiskOracle.sol, reused
           unmodified -- see chains/ethereum-l1/deploy/README.md) will be
           deployed in the next phase (deploy_testnet). No oracle exists yet
           this phase (scoring_build) -- this script's normal, non-dry-run
           path is intentionally not runnable until ORACLE_ADDRESS exists.

--dry-run is the only mode this phase actually exercises: it re-derives all
4 scores from live mainnet state and ABI-encodes the exact `updateScores(
address[], AuthorityScore[])` calldata that would be sent, WITHOUT opening a
connection to any write RPC, without needing PRIVATE_KEY, and without
sending anything -- proving the encoding path works before a real oracle
address exists to send it to.

Usage:
    python3 chains/ethereum-l1/deploy/update_scores_ethereum_l1.py --dry-run
    python3 chains/ethereum-l1/deploy/update_scores_ethereum_l1.py --dry-run --read-rpc-url <url>

Non-dry-run (deploy_testnet phase only, not usable yet):
    READ_RPC_URL=https://ethereum-rpc.publicnode.com \
    ORACLE_RPC_URL=https://ethereum-sepolia-rpc.publicnode.com \
    ORACLE_ADDRESS=0x... \
    PRIVATE_KEY=0x... \
    python3 chains/ethereum-l1/deploy/update_scores_ethereum_l1.py

PRIVATE_KEY is the raw hex value, not a file path. The actual value lives in a JSON file named by
work/ecosystems.json's own "key_file" field (a "private_key" field inside it, despite the file itself
being named ".env" -- confirmed live 2026-09-24, see scripts/repush_all_oracles.sh::read_key for the
exact extraction pattern):
    PRIVATE_KEY=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["private_key"])' <key_file>) \
    ...rest of the command above...
"""
import argparse
import os
import sys
import time

from web3 import Web3

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts", "lib"))
sys.path.insert(0, os.path.join(REPO_ROOT, "chains", "ethereum-l1"))

from web3_utils import get_w3  # noqa: E402
from scorers import score_all  # noqa: E402
from oracle_keys import assert_unique_oracle_keys  # noqa: E402

DEFAULT_READ_RPC_URL = "https://ethereum-rpc.publicnode.com"  # Ethereum L1 mainnet, chain 1
DEFAULT_ORACLE_RPC_URL = "https://ethereum-sepolia-rpc.publicnode.com"  # Sepolia, chain 11155111
DEFAULT_READ_CHAIN_ID = 1
DEFAULT_ORACLE_CHAIN_ID = 11155111
METHODOLOGY_VERSION = "authority-risk-oracle-ethereum-l1-v1"

# methodologyHash tied to the scoring code since 2026-09-30 (scripts/lib/methodology.py). Loaded by path, not by
# putting scripts/lib on sys.path, so no chain-local module (e.g. a chain's own `scorers`) can be shadowed.
import importlib.util as _ilu  # noqa: E402
_spec = _ilu.spec_from_file_location("aro_methodology", os.path.join(REPO_ROOT, "scripts", "lib", "methodology.py"))
methodology = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(methodology)

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

def methodology_hash() -> bytes:
    # keccak256("<METHODOLOGY_VERSION>:<digest of every scoring file>") since 2026-09-30, see scripts/lib/methodology.py:
    # a fix of the scorer now changes the published hash, a change of the target's posture does not.
    return methodology.evm_hash("ethereum-l1", METHODOLOGY_VERSION)


def build_calldata(w3_for_encoding, scored, now, meth_hash):
    # FIXED 2026-09-17 (closed a real bug, see data/correction_2026-09-17-
    # missing-crossexposure-field.md): this used to hardcode every target's
    # on-chain crossExposureScore to 100 regardless of what scorers.py
    # actually computed, because scorers.py didn't compute the field at all
    # when this constant was first written. scorers.py now computes a real
    # per-target value (5 of the 9 tracked targets share one root Safe and
    # read 20, not 100) -- silently overwriting that with a flat 100 here
    # would have discarded the finding at the exact moment it was pushed
    # on-chain, the one place this project's own methodology says the
    # number has to be trustworthy. Reads the real value from each entry now.
    oracle = w3_for_encoding.eth.contract(abi=ORACLE_ABI)
    # The oracle keeps one score per address: refuse the whole push if two entries share one (scripts/lib/oracle_keys.py).
    assert_unique_oracle_keys(scored, where="(ethereum-l1 push)")
    targets = [Web3.to_checksum_address(e["target"]) for e in scored]
    tuples = [
        (
            e["adminKeyScore"],
            e["multisigScore"],
            e["timelockScore"],
            e["oracleAuthorityScore"],
            e["crossExposureScore"],
            e["compositeScore"],
            now,
            meth_hash,
        )
        for e in scored
    ]
    calldata = oracle.encode_abi("updateScores", args=[targets, tuples])
    return calldata, targets, tuples


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Encode calldata only, send nothing, no PRIVATE_KEY needed.")
    parser.add_argument("--read-rpc-url", default=os.environ.get("READ_RPC_URL", DEFAULT_READ_RPC_URL))
    parser.add_argument("--oracle-rpc-url", default=os.environ.get("ORACLE_RPC_URL", DEFAULT_ORACLE_RPC_URL))
    parser.add_argument("--oracle-address", default=os.environ.get("ORACLE_ADDRESS"))
    args = parser.parse_args()
    methodology.code_digest("ethereum-l1")  # pin the code that runs now, before scoring
    if not args.dry_run:  # the published hash must match a commit
        methodology.require_committed("ethereum-l1")

    read_w3 = get_w3(args.read_rpc_url)
    if not read_w3.is_connected():
        raise SystemExit(f"Could not connect to read RPC: {args.read_rpc_url}")
    read_chain_id = read_w3.eth.chain_id
    print(f"Read RPC chain ID: {read_chain_id} (expect {DEFAULT_READ_CHAIN_ID} for Ethereum L1 mainnet)")
    if read_chain_id != DEFAULT_READ_CHAIN_ID:
        raise SystemExit(f"Refusing: read RPC is not Ethereum L1 mainnet (got chain {read_chain_id}).")

    scored = score_all(read_w3)
    now = int(time.time())
    meth_hash = methodology_hash()
    print(methodology.describe("ethereum-l1", METHODOLOGY_VERSION))
    if not args.dry_run:  # right before sending: the files must still be the ones pinned before scoring
        methodology.assert_unchanged("ethereum-l1")

    calldata, targets, tuples = build_calldata(read_w3, scored, now, meth_hash)

    print(f"\nEncoded updateScores() calldata for {len(targets)} targets:")
    for entry in scored:
        print(f"  {entry['label']}: composite={entry['compositeScore']}/100 -> {entry['target']}")
    print(f"\ncalldata ({len(calldata)} bytes incl. 0x, selector {calldata[:10]}):")
    print(calldata)

    if not args.dry_run:
        print("\n--dry-run not set: this phase (scoring_build) does not send. "
              "The non-dry-run path (build_transaction/sign/send below) is wired for "
              "deploy_testnet once ORACLE_ADDRESS/PRIVATE_KEY exist -- not exercised here.")
        if not args.oracle_address:
            raise SystemExit("ORACLE_ADDRESS not set -- no oracle deployed yet this phase. Use --dry-run.")
        oracle_w3 = get_w3(args.oracle_rpc_url)
        if not oracle_w3.is_connected():
            raise SystemExit(f"Could not connect to oracle RPC: {args.oracle_rpc_url}")
        oracle_chain_id = oracle_w3.eth.chain_id
        print(f"Oracle RPC chain ID: {oracle_chain_id} (expect {DEFAULT_ORACLE_CHAIN_ID} for Sepolia)")
        if oracle_chain_id != DEFAULT_ORACLE_CHAIN_ID:
            raise SystemExit(f"Refusing: oracle RPC is not Sepolia (got chain {oracle_chain_id}).")
        private_key = os.environ["PRIVATE_KEY"]
        account = oracle_w3.eth.account.from_key(private_key)
        oracle = oracle_w3.eth.contract(address=Web3.to_checksum_address(args.oracle_address), abi=ORACLE_ABI)
        tx = oracle.functions.updateScores(targets, tuples).build_transaction(
            {
                "from": account.address,
                "nonce": oracle_w3.eth.get_transaction_count(account.address),
                # FIXED 2026-09-19: was the bare eth_gasPrice quote with no
                # headroom -- the 2026-09-19 push (tx 0x3278...2694, 0.93 gwei)
                # sat pending >7 min after Sepolia's base fee rose to 1.03 gwei
                # and had to be replaced (same nonce, same calldata) by
                # 0xef18...f0d8. 2x headroom, still negligible on a testnet.
                "gasPrice": 2 * oracle_w3.eth.gas_price,
                "chainId": oracle_chain_id,
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
    else:
        print("\n--dry-run: no RPC connection opened to the oracle chain, no PRIVATE_KEY read, nothing sent.")


if __name__ == "__main__":
    main()
