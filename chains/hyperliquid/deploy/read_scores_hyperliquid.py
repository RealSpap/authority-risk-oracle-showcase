#!/usr/bin/env python3
"""Read-only read-back of the Hyperliquid oracle on HyperEVM Testnet against the live scorer.

No key, no signature, no transaction: only eth_call (plus the same live mainnet reads `push_scores.py --dry-run` does).

    python3 chains/hyperliquid/deploy/read_scores_hyperliquid.py <ORACLE_ADDRESS>

Recomputes the 15 scores with this repo's own scorer, rebuilds the same oracle keys push_scores.py uses (including the
derived keys for the two HIP-3 dexes that collide with a HyperEVM contract address), then reads getScore(key) on the
oracle and compares all 6 scores and the methodologyHash. Also checks trackedTargetsCount(), isStale() and that the
deployer holds UPDATER_ROLE. Exit code 0 only if everything matches. Counterpart of
`chains/solana/deploy/read_scores_solana.py`.
"""
import argparse
import os
import sys
import time

ap = argparse.ArgumentParser()
ap.add_argument("oracle")
ap.add_argument("--rpc", default="https://rpc.hyperliquid-testnet.xyz/evm")
ap.add_argument("--deployer", default="0x20630C6Ab4BA48a80edA46F77b9b6e987A8f32f5")
args = ap.parse_args()

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "chains", "hyperliquid", "deploy"))
sys.path.insert(0, os.path.join(REPO_ROOT, "chains", "hyperliquid"))
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts", "lib"))
import push_scores as ps  # noqa: E402
from web3 import Web3  # noqa: E402

w3 = Web3(Web3.HTTPProvider(args.rpc, request_kwargs={"timeout": 30}))
assert w3.eth.chain_id == 998, f"chain id {w3.eth.chain_id}, expected 998"
oracle = Web3.to_checksum_address(args.oracle)

ABI = [
    {"name": "getScore", "type": "function", "stateMutability": "view",
     "inputs": [{"name": "target", "type": "address"}],
     "outputs": [{"name": "", "type": "tuple", "components": [
         {"name": "adminKeyScore", "type": "uint8"}, {"name": "multisigScore", "type": "uint8"},
         {"name": "timelockScore", "type": "uint8"}, {"name": "oracleAuthorityScore", "type": "uint8"},
         {"name": "crossExposureScore", "type": "uint8"}, {"name": "compositeScore", "type": "uint8"},
         {"name": "lastUpdated", "type": "uint64"}, {"name": "methodologyHash", "type": "bytes32"}]}]},
    {"name": "trackedTargetsCount", "type": "function", "stateMutability": "view", "inputs": [],
     "outputs": [{"name": "", "type": "uint256"}]},
    {"name": "hasRole", "type": "function", "stateMutability": "view",
     "inputs": [{"name": "role", "type": "bytes32"}, {"name": "account", "type": "address"}],
     "outputs": [{"name": "", "type": "bool"}]},
    {"name": "isStale", "type": "function", "stateMutability": "view",
     "inputs": [{"name": "target", "type": "address"}], "outputs": [{"name": "", "type": "bool"}]},
]
c = w3.eth.contract(address=oracle, abi=ABI)

problems = []
code = w3.eth.get_code(oracle)
print(f"oracle {oracle}: {len(code)} bytes of code on chain {w3.eth.chain_id}")
if len(code) == 0:
    sys.exit("no code at that address")

role = Web3.keccak(text="UPDATER_ROLE")
has = c.functions.hasRole(role, Web3.to_checksum_address(args.deployer)).call()
print(f"deployer {args.deployer} holds UPDATER_ROLE: {has}")
if not has:
    problems.append("deployer lacks UPDATER_ROLE")

scored = ps.score_all()
meth = ps.methodology_hash()
targets, tuples = ps.build_targets_and_tuples(scored, int(time.time()), meth)
n = c.functions.trackedTargetsCount().call()
print(f"trackedTargetsCount = {n} (scorer produced {len(targets)})")
if n != len(targets):
    problems.append(f"trackedTargetsCount {n} != {len(targets)}")

fields = ["admin", "multisig", "timelock", "oracle", "crossExp", "composite"]
for entry, key, tup in zip(scored, targets, tuples):
    on = c.functions.getScore(key).call()
    exp = tup[:6]
    got = tuple(on[:6])
    ok = got == tuple(exp) and on[7] == meth
    stale = c.functions.isStale(key).call()
    flag = "OK " if ok and not stale else "DIFF"
    print(f"{flag} {entry['label'][:40]:40s} key={key[:10]}… composite chain={on[5]:3d} scorer={exp[5]:3d}"
          + ("" if ok else f"  chain={got} scorer={tuple(exp)} methOK={on[7] == meth}") + ("  STALE" if stale else ""))
    if got != tuple(exp):
        problems.append(f"{entry['label']}: chain {got} != scorer {tuple(exp)}")
    elif on[7] != meth:  # same scores, other code: pushed from another commit (see scripts/lib/methodology.py)
        problems.append(f"{entry['label']}: same scores, methodologyHash differs (pushed from other scoring code)")
    if stale:
        problems.append(f"{entry['label']}: stale")

print()
print("RESULT:", "ALL MATCH" if not problems else f"{len(problems)} PROBLEM(S)")
for p in problems:
    print(" -", p)
sys.exit(0 if not problems else 1)
