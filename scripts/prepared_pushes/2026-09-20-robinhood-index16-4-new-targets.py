#!/usr/bin/env python3
"""
ARCHIVED, DO NOT RERUN OR COPY AS A TEMPLATE (2026-09-30): it publishes the old hand-typed methodologyHash
(keccak of a label) without the commit check. Pushes since 2026-09-30 tie the hash to the code: see scripts/lib/methodology.py.

PREPARED PUSH -- Robinhood Chain rotation audit, index 16 (2026-09-20).
Four NEW targets. Run by SPAP, never by an agent (rule of 2026-09-20: the
agent prepares the exact command, the user broadcasts it, the agent re-reads
the chain read-only afterwards).

What it pushes
--------------
  UNCX Network V4 Liquidity Locker  0x128A800cBc615cc110Bff16E475865c67631603A  50/35/0/100/100 -> 31
  Orvex V2 PairFactoryUpgradeable   0x5c98b2d892b37c9a1D3b69472bdDc172A64CdC09   5/ 0/0/100/100 ->  2
  Orvex V4 CL PoolManager           0xd01C774d4A66408326Bc65728Ac5Ae5aAf004032  65/65/0/100/100 -> 46
  Orvex V4 Vault                    0xFe7E25dE55e5cBbEcCcb661F3679F873f72B9b0D   2/ 0/0/100/100 ->  1

NOT in this batch, on purpose: tracked target index 16 (NFLX,
0xE0444EF8...91E8). Its score was fully re-derived this run and matches what
is already published (3/0/0/100/100, composite 1), so there is nothing to
correct on chain. See data/rotation_audit_2026-09-20-robinhood-chain-index16.md.

Safety
------
Nothing is broadcast unless --broadcast is passed AND every precondition
below holds. Default is a dry run.
  1. ORACLE_RPC_URL must report chain id 46630 (Robinhood Chain TESTNET).
     A mainnet chain id aborts. This project never writes to a mainnet.
  2. The signer must already hold UPDATER_ROLE (checked read-only).
  3. Each of the 4 scores is RE-DERIVED live, on BOTH mainnet read RPCs,
     immediately before sending, and must agree with the table above and
     with each other. Any mismatch aborts.
  4. Each of the 4 targets must NOT already be tracked (this is an add, not
     a correction). Any already-tracked target aborts.
  5. After the receipt, every pushed score is read back with getScore() and
     the CORRECT struct ABI and compared field by field.

Usage
-----
  # dry run (this is what the agent ran; it sends nothing)
  ORACLE_RPC_URL=https://rpc.testnet.chain.robinhood.com/rpc \
  python3 scripts/prepared_pushes/2026-09-20-robinhood-index16-4-new-targets.py

  # real push -- Spap only
  ORACLE_RPC_URL=https://rpc.testnet.chain.robinhood.com/rpc \
  PRIVATE_KEY=0x... \
  python3 scripts/prepared_pushes/2026-09-20-robinhood-index16-4-new-targets.py --broadcast
"""
import os
import sys

from web3 import Web3

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))
from lib.scorers import (  # noqa: E402
    score_uncx_v4_locker,
    score_orvex_v2_pair_factory,
    score_orvex_v4_pool_manager,
    score_orvex_v4_vault,
)
from lib.signer_overlap import compute_cross_exposure  # noqa: E402

TESTNET_CHAIN_ID = 46630
ORACLE = "0x9BF45734D09bC7CA39238e767B2af9AAc62a7f52"
READ_RPCS = [
    "https://rpc.mainnet.chain.robinhood.com",
    "https://robinhood.drpc.org",
]
# keccak256("authority-risk-oracle-v3") -- recomputed below, not trusted as a literal.
METHODOLOGY_STRING = "authority-risk-oracle-v3"

SCORERS = [
    ("UNCX Network V4 Liquidity Locker", score_uncx_v4_locker),
    ("Orvex V2 PairFactoryUpgradeable", score_orvex_v2_pair_factory),
    ("Orvex V4 CL PoolManager", score_orvex_v4_pool_manager),
    ("Orvex V4 Vault", score_orvex_v4_vault),
]

# The hand-derived table from data/rotation_audit_2026-09-20-robinhood-chain-index16.md.
# The live re-derivation must reproduce it exactly, or this script aborts.
EXPECTED = {
    "0x128A800cBc615cc110Bff16E475865c67631603A": (50, 35, 0, 100, 100, 31),
    "0x5c98b2d892b37c9a1D3b69472bdDc172A64CdC09": (5, 0, 0, 100, 100, 2),
    "0xd01C774d4A66408326Bc65728Ac5Ae5aAf004032": (65, 65, 0, 100, 100, 46),
    "0xFe7E25dE55e5cBbEcCcb661F3679F873f72B9b0D": (2, 0, 0, 100, 100, 1),
}

SCORE_TUPLE = {
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
    "type": "tuple",
}
ORACLE_ABI = [
    {"name": "updateScores", "type": "function", "stateMutability": "nonpayable",
     "inputs": [{"name": "targets", "type": "address[]"},
                {"name": "scores", "type": "tuple[]", **{k: v for k, v in SCORE_TUPLE.items() if k == "components"}}],
     "outputs": []},
    {"name": "getScore", "type": "function", "stateMutability": "view",
     "inputs": [{"name": "target", "type": "address"}],
     "outputs": [{"name": "", **SCORE_TUPLE}]},
    {"name": "trackedTargetsCount", "type": "function", "stateMutability": "view",
     "inputs": [], "outputs": [{"type": "uint256"}]},
    {"name": "hasRole", "type": "function", "stateMutability": "view",
     "inputs": [{"type": "bytes32"}, {"type": "address"}], "outputs": [{"type": "bool"}]},
    {"name": "UPDATER_ROLE", "type": "function", "stateMutability": "view",
     "inputs": [], "outputs": [{"type": "bytes32"}]},
]


def fail(msg):
    print(f"ABORT: {msg}")
    sys.exit(1)


def rederive():
    """Re-derive all 4 entries on BOTH read RPCs. Returns the agreed dict."""
    per_rpc = []
    for url in READ_RPCS:
        w3 = Web3(Web3.HTTPProvider(url, request_kwargs={"timeout": 90}))
        if not w3.is_connected():
            fail(f"read RPC unreachable: {url}")
        cross = compute_cross_exposure(w3)
        out = {}
        for label, fn in SCORERS:
            e = fn(w3)
            target = Web3.to_checksum_address(e["target"])
            out[target] = (
                e["adminKeyScore"], e["multisigScore"], e["timelockScore"],
                e["oracleAuthorityScore"], cross.get(target, 100), e["compositeScore"],
            )
            print(f"  [{url}] {label:<36} {out[target]}")
        per_rpc.append(out)
    if per_rpc[0] != per_rpc[1]:
        fail(f"the two read RPCs disagree:\n  A={per_rpc[0]}\n  B={per_rpc[1]}")
    for addr, expected in EXPECTED.items():
        got = per_rpc[0].get(Web3.to_checksum_address(addr))
        if got != expected:
            fail(f"{addr}: live re-derivation {got} != audited table {expected} -- "
                 "the chain moved since the audit; re-run the audit, do not push")
    return per_rpc[0]


def main():
    broadcast = "--broadcast" in sys.argv
    oracle_rpc = os.environ.get("ORACLE_RPC_URL")
    if not oracle_rpc:
        fail("ORACLE_RPC_URL not set")

    w3 = Web3(Web3.HTTPProvider(oracle_rpc, request_kwargs={"timeout": 90}))
    if not w3.is_connected():
        fail(f"oracle RPC unreachable: {oracle_rpc}")
    chain_id = w3.eth.chain_id
    print(f"oracle RPC chain id = {chain_id}")
    if chain_id != TESTNET_CHAIN_ID:
        fail(f"chain id {chain_id} is not the Robinhood Chain TESTNET ({TESTNET_CHAIN_ID}). "
             "This project never writes to a mainnet.")

    oracle = w3.eth.contract(address=Web3.to_checksum_address(ORACLE), abi=ORACLE_ABI)
    before_count = oracle.functions.trackedTargetsCount().call()
    print(f"trackedTargetsCount() before = {before_count}")

    print("\nre-deriving all 4 scores live on both mainnet read RPCs:")
    derived = rederive()

    already = []
    for addr in derived:
        published = oracle.functions.getScore(addr).call()
        if published[6] != 0:  # lastUpdated
            already.append((addr, published))
    if already:
        fail(f"these targets are ALREADY tracked, so this is not an add: {already}. "
             "Use a correction script instead, and document the divergence.")
    print("none of the 4 targets is already tracked -- this is an add, as intended")

    methodology_hash = Web3.keccak(text=METHODOLOGY_STRING)
    print(f"methodologyHash = 0x{methodology_hash.hex()}")

    targets = [Web3.to_checksum_address(a) for a in EXPECTED]
    now = w3.eth.get_block("latest")["timestamp"]
    scores = [(*derived[t], now, methodology_hash) for t in targets]

    calldata = oracle.encode_abi("updateScores", args=[targets, scores])
    print("\n--- exact calldata for updateScores(address[],AuthorityScore[]) ---")
    print(calldata)
    print("--- end calldata ---")

    if not broadcast:
        print("\nDRY RUN -- nothing sent. Re-run with --broadcast and PRIVATE_KEY set to push.")
        return

    key = os.environ.get("PRIVATE_KEY")
    if not key:
        fail("--broadcast given but PRIVATE_KEY is not set")
    account = w3.eth.account.from_key(key)
    updater_role = oracle.functions.UPDATER_ROLE().call()
    if not oracle.functions.hasRole(updater_role, account.address).call():
        fail(f"{account.address} does not hold UPDATER_ROLE on {ORACLE}")
    print(f"signer {account.address} holds UPDATER_ROLE, balance "
          f"{w3.from_wei(w3.eth.get_balance(account.address), 'ether')} ETH")

    tx = oracle.functions.updateScores(targets, scores).build_transaction({
        "from": account.address,
        "nonce": w3.eth.get_transaction_count(account.address),
        "chainId": chain_id,
    })
    signed = w3.eth.account.sign_transaction(tx, key)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    print(f"sent {tx_hash.hex()} -- waiting for the receipt")
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=300)
    print(f"status={receipt['status']} block={receipt['blockNumber']}")
    if receipt["status"] != 1:
        fail("transaction reverted")

    print(f"trackedTargetsCount() after = {oracle.functions.trackedTargetsCount().call()} "
          f"(was {before_count}, expected {before_count + 4})")
    for t in targets:
        got = oracle.functions.getScore(t).call()
        want = derived[t]
        ok = tuple(got[:6]) == want and got[7] == methodology_hash
        print(f"  read back {t}: {tuple(got[:6])} composite={got[5]} match={ok}")
        if not ok:
            fail(f"read-back mismatch on {t}: on chain {got} vs pushed {want}")
    print("\nall 4 read back identical to what was pushed.")


if __name__ == "__main__":
    main()
