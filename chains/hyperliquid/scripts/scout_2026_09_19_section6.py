"""Scouting run 2026-09-19: closing METHODOLOGY.md section 6's first and
third open questions (the second -- L1 upgrade notice lead time -- has no
live read attached to it; that search trail is documented directly in
METHODOLOGY.md/data/finding_2026-09-19-section6-open-questions.md since
there is nothing to script against a source that does not exist).

Reuses `scout_2026_09_17_run2.py`'s own HTTP/RPC/decoding helpers (`info`,
`rpc`, `one`, `cs`, `ARB`, `EVM`, `BRIDGE2`, `EPOCH7_TX`) rather than
duplicating them -- same "one canonical copy" discipline this project
already applies elsewhere (see that module's own docstring, and
METHODOLOGY.md 3.7's CoreWriter/Kinetiq lesson).

Every read goes to a public endpoint: the official HyperCore info API, the
official HyperEVM RPC (chain 999), and the public Arbitrum One RPC. No
transaction, no key, no write.

Usage (each subcommand prints one JSON object):
    python3 chains/hyperliquid/scripts/scout_2026_09_19_section6.py bridge-vs-l1
    python3 chains/hyperliquid/scripts/scout_2026_09_19_section6.py hip4-deployers
"""
import json
import os
import sys

from eth_abi import decode as abi_decode
from web3 import Web3

sys.path.insert(0, os.path.dirname(__file__))
from scout_2026_09_17_run2 import info, rpc, one, cs, ARB, EVM, BRIDGE2, EPOCH7_TX  # noqa: E402

SIG_EMERGENCY_UNLOCK = "emergencyUnlock((uint64,address[],address[],uint64[]),(uint64,address[],uint64[]),(uint256,uint256,uint8)[],uint64)"
SIG_UPDATE_VALIDATOR_SET = "updateValidatorSet((uint64,address[],address[],uint64[]),(uint64,address[],uint64[]),(uint256,uint256,uint8)[])"


def _kn(addr):
    m = info({"type": "userToMultiSigSigners", "user": addr})
    return (1, 1) if m is None else (m["threshold"], len(m["authorizedUsers"]))


def bridge_vs_l1():
    """Question 1: decode the last validator-set-changing calldata on
    Bridge2 (epoch 7) and compare its hot/cold signer set against the
    current 27 active Hyperliquid L1 validators (and, for completeness,
    all 35 registered ones -- both the `validator` identity address and
    the `signer` hot-key address of each)."""
    tx = rpc(ARB, "eth_getTransactionByHash", [EPOCH7_TX])
    selector = tx["input"][:10]
    sel_emergency = "0x" + Web3.keccak(text=SIG_EMERGENCY_UNLOCK)[:4].hex()
    sel_update = "0x" + Web3.keccak(text=SIG_UPDATE_VALIDATOR_SET)[:4].hex()
    fn_called = {sel_emergency: "emergencyUnlock", sel_update: "updateValidatorSet"}.get(selector, "UNKNOWN")

    new_set, active_cold_at_call_time, sigs, nonce = abi_decode(
        ["(uint64,address[],address[],uint64[])", "(uint64,address[],uint64[])", "(uint256,uint256,uint8)[]", "uint64"],
        bytes.fromhex(tx["input"][10:]))
    epoch, hot, cold, powers = new_set

    live_epoch = one(ARB, BRIDGE2, "epoch()", "uint64")
    live_hot_hash = one(ARB, BRIDGE2, "hotValidatorSetHash()", "bytes32").hex()
    live_cold_hash = one(ARB, BRIDGE2, "coldValidatorSetHash()", "bytes32").hex()
    pending_raw = rpc(ARB, "eth_call", [{"to": cs(BRIDGE2), "data": "0x" + Web3.keccak(text="pendingValidatorSetUpdate()")[:4].hex()}, "latest"])
    pend_epoch, pend_power, pend_update_time, pend_block, pend_n, pend_hot_hash, pend_cold_hash = abi_decode(
        ["uint64", "uint64", "uint64", "uint64", "uint64", "bytes32", "bytes32"], bytes.fromhex(pending_raw[2:]))

    # Hash-matching (decoded hot/cold set -> keccak -> compare against the
    # live on-chain hotValidatorSetHash/coldValidatorSetHash) is already
    # independently done in scout_2026_09_17_run2.py::bridge2() and confirmed
    # there -- not repeated here to avoid a second, divergent implementation
    # of the same check; this function instead cross-checks the CURRENT
    # `epoch()` and `pendingValidatorSetUpdate()` reads below, which that
    # earlier script does not.

    vals = info({"type": "validatorSummaries"})
    active = [v for v in vals if v["isActive"]]
    l1_all = {v["validator"].lower() for v in vals} | {v["signer"].lower() for v in vals}
    l1_active = {v["validator"].lower() for v in active} | {v["signer"].lower() for v in active}
    bridge_keys = {a.lower() for a in list(hot) + list(cold)}

    return {
        "epoch7TxHash": EPOCH7_TX,
        "epoch7TxFunctionCalled": fn_called,
        "epoch7TxSelector": selector,
        "note": "the LAST validator-set change on Bridge2 was via emergencyUnlock (cold-quorum path), not the plain updateValidatorSet (hot-quorum) path -- both write the same ValidatorSetUpdateRequest shape and both are decoded the same way",
        "liveEpoch": live_epoch,
        "liveHotValidatorSetHash": "0x" + live_hot_hash,
        "liveColdValidatorSetHash": "0x" + live_cold_hash,
        "decodedTxEpoch": epoch,
        "pendingValidatorSetUpdate_updateTime": pend_update_time,
        "pendingValidatorSetUpdate_updateBlockNumber": pend_block,
        "pendingUpdateAlreadyFinalized": pend_update_time == 0,
        "hotAddresses": [cs(a) for a in hot],
        "coldAddresses": [cs(a) for a in cold],
        "powers": list(powers),
        "l1RegisteredValidatorCount": len(vals),
        "l1ActiveValidatorCount": len(active),
        "overlapWithAnyRegisteredL1ValidatorOrSigner": sorted(bridge_keys & l1_all),
        "overlapWithActiveL1ValidatorOrSigner": sorted(bridge_keys & l1_active),
    }


def hip4_deployers():
    """Question 3 (HIP-4 half): live outcome-market deployer/sub-deployer
    inventory from the MAINNET info API (`outcomeMeta`), with each
    address's (k, n) multisig shape and HyperEVM bytecode length (per
    METHODOLOGY.md 3.7's caution: a HyperCore-native address that also
    carries HyperEVM bytecode needs its logic checked, not assumed)."""
    meta = info({"type": "outcomeMeta"})
    deployers_out = []
    for d in meta["deployers"]:
        all_addrs = [d["deployer"]] + [a for _variant, addrs in d["subDeployers"] for a in addrs]
        code_len = {a: (len(rpc(EVM, "eth_getCode", [cs(a), "latest"])) - 2) // 2 for a in all_addrs}
        deployers_out.append({
            "venue": d["venue"],
            "deployer": cs(d["deployer"]),
            "deployerKN": _kn(d["deployer"]),
            "subDeployers": {
                variant: {cs(a): _kn(a) for a in addrs}
                for variant, addrs in d["subDeployers"]
            },
            "hyperEvmCodeLenByAddress": code_len,
        })
    from collections import Counter
    outcome_count_by_venue = dict(Counter(o.get("venue") for o in meta["outcomes"]))
    return {
        "totalOutcomes": len(meta["outcomes"]),
        "totalQuestions": len(meta.get("questions", [])),
        "outcomeCountByVenue": outcome_count_by_venue,
        "deployers": deployers_out,
    }


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else None
    fns = {"bridge-vs-l1": bridge_vs_l1, "hip4-deployers": hip4_deployers}
    if cmd not in fns:
        raise SystemExit(f"usage: {sys.argv[0]} [{'|'.join(fns)}]")
    print(json.dumps(fns[cmd](), indent=2, default=str))
