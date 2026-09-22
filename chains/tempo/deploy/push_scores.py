#!/usr/bin/env python3
"""
Tempo score pusher -- modeled directly on `chains/hyperliquid/deploy/
push_scores.py` (the closest sibling: `chains/tempo/scorers.py::score_all()`
also takes NO RPC argument, `score_all(_url_unused=None)`, since Tempo's
reads are fixed official endpoints -- `RPCS = ["https://rpc.tempo.xyz",
"https://tempo-rpc.publicnode.com"]` inside `scripts/methodology_test.py`,
cross-checked against each other on every eth_call -- not one
caller-supplied chain the way the Arbitrum/Base/Ethereum-L1 siblings take
`READ_RPC_URL`).

Same shape as every other ecosystem's pusher: re-derive every tracked
target's score live, then push via `AuthorityRiskOracle.updateScores()`
(the SAME unmodified contract, `src/AuthorityRiskOracle.sol`, every other
EVM ecosystem in this repo deploys per-chain).

One Tempo-specific difference from every EVM sibling, load-bearing for the
real-send path below (not the --dry-run path, which never reaches it):
Tempo has **no native gas token** (METHODOLOGY.md section 1 and section 5)
-- `BALANCE`/`SELFBALANCE`/`CALLVALUE` are always 0, and transaction fees
are paid in a USD TIP-20 stablecoin (pathUSD from the testnet faucet, as
the fallback fee token), not in wei. `eth_getBalance` on both Tempo Mainnet
and Tempo Testnet (Moderato) was independently confirmed THIS pass (see
../deploy/README.md) to return a FIXED, address-independent sentinel value
(0x9612...c9b2, decimal 42424242...4242) on 3 separate RPC endpoints and 2
different addresses -- not a real, spendable native balance, and NOT
evidence the shared throwaway deployer key is funded. `build_transaction()`
below still uses the standard web3.py `gasPrice`/legacy-tx shape (matching
every EVM sibling's own real-send path) since Tempo is fully EVM/JSON-RPC
compatible for transaction *submission* -- but a real send will need the
deployer's TIP-20 fee-token balance to actually be nonzero, which
`eth_getBalance` cannot tell us; disclosed as an open thread in
../deploy/README.md, not resolved by this script.

Usage (--dry-run, this phase -- read-only, no transaction, no PRIVATE_KEY
needed):
    python3 chains/tempo/deploy/push_scores.py --dry-run

Usage (real send, future phase, once the oracle is deployed on Moderato and
the key holds a nonzero TIP-20 fee-token balance there):
    ORACLE_RPC_URL=https://rpc.moderato.tempo.xyz \
    ORACLE_ADDRESS=0x... \
    PRIVATE_KEY=0x... \
    python3 chains/tempo/deploy/push_scores.py

--dry-run ALSO differs from the root script's --dry-run in one respect: it
goes one step further and actually ABI-ENCODES the updateScores() calldata
(using the real ORACLE_ABI below) and prints its hex, so a re-run of this
exact script is enough to prove the encoding step works end to end -- not
just that the Python-side scoring dicts look right. No transaction is
built, signed, or sent; ORACLE_RPC_URL/ORACLE_ADDRESS/PRIVATE_KEY are not
read at all in --dry-run mode.
"""
import os
import sys
import time

from web3 import Web3

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "chains", "tempo"))
sys.path.insert(0, os.path.join(REPO_ROOT, "chains", "tempo", "scripts"))
# appended, not inserted first: scripts/lib has its own scorers.py, which must not shadow chains/tempo/scorers.py
sys.path.append(os.path.join(REPO_ROOT, "scripts", "lib"))

from scorers import score_all  # noqa: E402
from oracle_keys import assert_unique_oracle_keys  # noqa: E402

TEMPO_MAINNET_CHAIN_ID = 4217   # re-confirmed live this pass via `cast chain-id --rpc-url https://rpc.tempo.xyz`
TEMPO_TESTNET_CHAIN_ID = 42431  # Moderato, re-confirmed live this pass via `cast chain-id --rpc-url https://rpc.moderato.tempo.xyz`

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

METHODOLOGY_VERSION = "authority-risk-oracle-tempo-v1"


def methodology_hash() -> bytes:
    # keccak256, matching Solidity's keccak256(bytes) -- same convention as
    # every other ecosystem's push_scores.py, not sha256.
    return Web3.keccak(text=METHODOLOGY_VERSION)


def build_targets_and_tuples(scored, now, meth_hash):
    # The oracle keeps one score per address: refuse the whole push if two entries share one (scripts/lib/oracle_keys.py).
    assert_unique_oracle_keys(scored, where="(tempo push)")
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

    print("Re-deriving every tracked Tempo target's score from live Tempo Mainnet state "
          "(fixed RPCS inside scripts/methodology_test.py, dual-RPC cross-checked per read)...\n")

    scored = score_all()  # no RPC argument -- see this module's own docstring
    if not scored:
        raise SystemExit("score_all() returned no results (see its own printed SKIPPED reason above) -- refusing to encode an empty push.")
    now = int(time.time())
    meth_hash = methodology_hash()

    for entry in scored:
        print(f"{entry['label']} ({entry['target']}): composite={entry['compositeScore']}/100, "
              f"crossExposure={entry.get('crossExposureScore')}/100")

    targets, tuples = build_targets_and_tuples(scored, now, meth_hash)

    oracle_iface = Web3().eth.contract(abi=ORACLE_ABI)
    calldata = oracle_iface.encode_abi("updateScores", args=[targets, tuples])

    print(f"\nEncoded updateScores() calldata ({len(calldata) // 2 - 1} bytes) for {len(targets)} targets: {calldata[:66]}...")
    print(f"methodologyHash = 0x{meth_hash.hex()}")
    print(f"Target chain for this calldata: Tempo Testnet (Moderato), chain ID {TEMPO_TESTNET_CHAIN_ID}")

    if dry_run:
        print("\n--dry-run set: calldata encoded above, but NOT sending a transaction, NOT reading ORACLE_RPC_URL/ORACLE_ADDRESS/PRIVATE_KEY.")
        return

    oracle_rpc_url = os.environ["ORACLE_RPC_URL"]
    oracle_address = os.environ["ORACLE_ADDRESS"]
    oracle_w3 = Web3(Web3.HTTPProvider(oracle_rpc_url, request_kwargs={"timeout": 20}))
    if not oracle_w3.is_connected():
        raise SystemExit(f"Could not connect to oracle RPC: {oracle_rpc_url}")
    if oracle_w3.eth.chain_id == TEMPO_MAINNET_CHAIN_ID:
        raise SystemExit("REFUSING: ORACLE_RPC_URL resolved to Tempo MAINNET (4217). This pipeline never writes to mainnet, for any ecosystem.")
    if oracle_w3.eth.chain_id != TEMPO_TESTNET_CHAIN_ID:
        raise SystemExit(
            f"ORACLE_RPC_URL resolved to chain ID {oracle_w3.eth.chain_id}, expected "
            f"{TEMPO_TESTNET_CHAIN_ID} (Tempo Testnet / Moderato) -- refusing to send to an unexpected chain."
        )
    print(f"\nPushing to oracle on chain ID: {oracle_w3.eth.chain_id} (Tempo Testnet / Moderato)")

    private_key = os.environ["PRIVATE_KEY"]
    account = oracle_w3.eth.account.from_key(private_key)
    oracle = oracle_w3.eth.contract(address=Web3.to_checksum_address(oracle_address), abi=ORACLE_ABI)

    tx = oracle.functions.updateScores(targets, tuples).build_transaction(
        {
            "from": account.address,
            "nonce": oracle_w3.eth.get_transaction_count(account.address),
            "gasPrice": oracle_w3.eth.gas_price,
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
