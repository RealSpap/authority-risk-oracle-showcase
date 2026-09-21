#!/usr/bin/env python3
"""
Hyperliquid deploy_testnet rehearsal WITHOUT anvil and WITHOUT a funded key.

Why this exists (2026-09-19): the deployer key has 0 wei on HyperEVM Testnet
(Hyperliquid's faucet requires a prior mainnet deposit -- out of scope), and
Foundry (anvil/forge/cast) is no longer installed on the host that runs this
pipeline, so the other ecosystems' "anvil fork" rehearsal cannot be replayed
here. Instead this script runs the whole deploy -> updateScores -> getScore
sequence INSIDE ONE `eth_call` on the REAL HyperEVM Testnet (chain 998):
the init code of `EthCallRehearsal.sol` (a contract creation with no `to`)
deploys the unmodified `src/AuthorityRiskOracle.sol` + `src/ExampleConsumer.sol`,
pushes the scores through the real `updateScores()`, reads each one back
through separate external `getScore()` calls, and returns the result.

`eth_call` is a read: nothing is broadcast, nothing is signed, no private key
is read, nothing persists on-chain, and gasPrice 0 means no balance is
needed. It executes against live testnet state and the testnet's own EVM
implementation (arguably closer to a real deploy than a local anvil fork,
which runs Foundry's EVM, not HyperEVM's).

Hard guards: the target RPC must report chain id 998; 999 (HyperEVM
mainnet) is refused even though an eth_call could not write anyway.

Usage (from the repo root):
    python3 chains/hyperliquid/deploy/rehearsal/rehearse_ethcall.py [--evm-version cancun] [--out result.json]

Scores are re-derived live via `chains/hyperliquid/scorers.py::score_all()`
and mapped to oracle keys by the SAME `push_scores.build_targets_and_tuples`
a real push would use, so this rehearses the real push path, not a copy.
"""
import argparse
import json
import os
import sys
import time

import solcx
from eth_abi import decode as abi_decode
from eth_abi import encode as abi_encode
from web3 import Web3

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts", "lib"))
sys.path.insert(0, os.path.join(REPO_ROOT, "chains", "hyperliquid"))
sys.path.insert(0, os.path.dirname(HERE))

from push_scores import build_targets_and_tuples, methodology_hash  # noqa: E402

TESTNET_RPCS = [
    "https://rpc.hyperliquid-testnet.xyz/evm",   # official
    "https://hyperliquid-testnet.drpc.org",      # independent provider
]
TESTNET_CHAIN_ID = 998
MAINNET_CHAIN_ID = 999
SOLC_VERSION = "0.8.36"  # same compiler the 2026-09-18 forge build used
DEPLOYER = "0x20630C6Ab4BA48a80edA46F77b9b6e987A8f32f5"  # public address only, used as eth_call `from`
SCORE_TUPLE = "(uint8,uint8,uint8,uint8,uint8,uint8,uint64,bytes32)"


def compile_harness(evm_version):
    solcx.set_solc_version(SOLC_VERSION)
    src = os.path.join(HERE, "EthCallRehearsal.sol")
    out = solcx.compile_files(
        [src],
        output_values=["bin", "bin-runtime"],
        optimize=True,
        optimize_runs=200,
        evm_version=evm_version,
        base_path=REPO_ROOT,
        allow_paths=[REPO_ROOT],
        import_remappings=["@openzeppelin/contracts/=lib/openzeppelin-contracts/contracts/"],
    )
    harness = next(v for k, v in out.items() if k.endswith(":EthCallRehearsal"))
    oracle = next(v for k, v in out.items() if k.endswith(":AuthorityRiskOracle"))
    return harness["bin"], oracle["bin-runtime"]


def rpc(url, method, params):
    w3 = Web3(Web3.HTTPProvider(url, request_kwargs={"timeout": 60}))
    resp = w3.provider.make_request(method, params)
    if "error" in resp:
        raise RuntimeError(f"{url} {method}: {resp['error']}")
    return resp["result"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--evm-version", default="cancun")
    ap.add_argument("--out", default=None)
    ap.add_argument("--legacy-keys", action="store_true",
                    help="key every entry by its raw scored address (the pre-2026-09-19 push behaviour) "
                         "to reproduce the silent-overwrite collision; expected to FAIL")
    args = ap.parse_args()

    from scorers import score_all  # noqa: E402  (live reads, HyperCore + HyperEVM mainnet, read-only)

    scored = score_all()
    now = int(time.time())
    meth = methodology_hash()
    targets, tuples = build_targets_and_tuples(scored, now, meth)
    if args.legacy_keys:
        targets = [Web3.to_checksum_address(e["target"]) for e in scored]
    print(f"{len(scored)} targets scored live, {len(set(targets))} distinct oracle keys")

    harness_bin, oracle_runtime = compile_harness(args.evm_version)
    expected_codehash = "0x" + Web3.keccak(hexstr=oracle_runtime).hex().removeprefix("0x")
    init = "0x" + harness_bin + abi_encode(["address[]", f"{SCORE_TUPLE}[]"], [targets, tuples]).hex()
    print(f"solc {SOLC_VERSION}, evm_version={args.evm_version}, init code {len(init) // 2 - 1} bytes")

    results = {"evm_version": args.evm_version, "solc": SOLC_VERSION, "scored_at": now,
               "methodologyHash": "0x" + meth.hex(), "rpcs": {}, "targets": []}
    all_ok = True
    for url in TESTNET_RPCS:
        chain_id = int(rpc(url, "eth_chainId", []), 16)
        if chain_id == MAINNET_CHAIN_ID or chain_id != TESTNET_CHAIN_ID:
            raise SystemExit(f"REFUSING: {url} reports chain id {chain_id}, expected {TESTNET_CHAIN_ID}")
        block = int(rpc(url, "eth_blockNumber", []), 16) - 20  # a little behind head: lagging providers still serve it
        call = {"from": DEPLOYER, "data": init, "gas": hex(30_000_000), "gasPrice": "0x0"}
        try:
            ret = rpc(url, "eth_call", [call, hex(block)])
        except RuntimeError as e:
            print(f"[{url}] eth_call FAILED at block {block}: {e}")
            results["rpcs"][url] = {"chainId": chain_id, "block": block, "error": str(e)}
            all_ok = False
            continue
        try:  # informational only: some providers cap eth_estimateGas at the 3M small-block limit
            gas = int(rpc(url, "eth_estimateGas", [call, hex(block)]), 16)
        except RuntimeError as e:
            gas = f"unavailable ({e})"
        (oracle_addr, consumer_addr, consumer_oracle, updater_before, tracked, codehash, back, stale, step_gas) = abi_decode(
            ["address", "address", "address", "bool", "uint256", "bytes32", f"{SCORE_TUPLE}[]", "bool[]", "uint256[3]"],
            bytes.fromhex(ret[2:]),
        )
        codehash_hex = "0x" + codehash.hex()
        mismatches = []
        for key, sent, got, st, entry in zip(targets, tuples, back, stale, scored):
            ok = tuple(sent) == tuple(got) and not st
            if not ok:
                mismatches.append(entry["label"])
            if url == TESTNET_RPCS[0]:
                results["targets"].append({"label": entry["label"], "scoredAddress": entry["target"], "oracleKey": key,
                                           "composite_sent": sent[5], "composite_readback": got[5], "match": ok})
            print(f"[{url}] {entry['label']} key={key}: sent composite={sent[5]} readback={got[5]} "
                  f"stale={st} -> {'MATCH' if ok else 'MISMATCH'}")
        codehash_ok = codehash_hex.lower().removeprefix("0x") == expected_codehash.lower().removeprefix("0x")
        rpc_ok = (not mismatches and tracked == len(targets) and updater_before
                  and consumer_oracle.lower() == oracle_addr.lower() and codehash_ok)
        all_ok &= rpc_ok
        results["rpcs"][url] = {"chainId": chain_id, "block": block, "estimateGas": gas,
                                "simulatedOracle": oracle_addr, "simulatedConsumer": consumer_addr,
                                "consumerOracleWired": consumer_oracle.lower() == oracle_addr.lower(),
                                "updaterRoleOnDeployer": updater_before, "trackedTargetsCount": tracked,
                                "oracleCodehash": codehash_hex, "expectedCodehash": expected_codehash,
                                "stepExecutionGas": {"oracleDeploy": step_gas[0], "consumerDeploy": step_gas[1],
                                                     "updateScores": step_gas[2]},
                                "mismatches": mismatches, "ok": rpc_ok}
        print(f"[{url}] execution gas per step (excl. 21k intrinsic + calldata): oracle deploy={step_gas[0]}, "
              f"consumer deploy={step_gas[1]}, updateScores({len(targets)})={step_gas[2]}")
        print(f"[{url}] chain {chain_id} block {block}: trackedTargetsCount={tracked}/{len(targets)}, "
              f"UPDATER_ROLE={updater_before}, consumer wired={consumer_oracle.lower() == oracle_addr.lower()}, "
              f"codehash={codehash_hex} (expected {expected_codehash}), estimateGas={gas}, "
              f"mismatches={mismatches or 'none'} -> {'REHEARSAL OK' if rpc_ok else 'REHEARSAL FAILED'}")

    results["all_ok"] = all_ok
    if args.out:
        with open(args.out, "w") as f:
            json.dump(results, f, indent=2)
    print("ALL RPCS REHEARSAL OK" if all_ok else "REHEARSAL FAILED ON AT LEAST ONE RPC")
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
