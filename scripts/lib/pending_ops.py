"""
What is queued right now behind the timelocks this oracle scores? Pure logic for scripts/check_pending_ops.py (no RPC).

A timelock's delay is a promise; the queue is the fact. Two families cover the tracked ones:
- OpenZeppelin TimelockController: `CallScheduled` / `CallExecuted` / `Cancelled`; whether an operation is still pending is
  answered by the contract (`isOperationPending(id)`), and when it becomes executable by `getTimestamp(id)`.
- Compound-style Timelock (Uniswap, Compound): `QueueTransaction` / `ExecuteTransaction` / `CancelTransaction`; still queued is
  `queuedTransactions(txHash)`, executable from `eta`, and expired after `eta + GRACE_PERIOD`.
Decoding and status classification only; the reads are in the script.
"""
from eth_abi import decode
from web3 import Web3


def _topic(sig):
    return "0x" + Web3.keccak(text=sig).hex().removeprefix("0x")


OZ_SCHEDULED = _topic("CallScheduled(bytes32,uint256,address,uint256,bytes,bytes32,uint256)")
COMPOUND_QUEUED = _topic("QueueTransaction(bytes32,address,uint256,string,bytes,uint256)")
QUEUE_TOPICS = {"oz": OZ_SCHEDULED, "compound": COMPOUND_QUEUED}


def _hex(v):
    v = v.hex() if isinstance(v, (bytes, bytearray)) else v
    return v.removeprefix("0x")


def _addr(topic):
    return Web3.to_checksum_address("0x" + _hex(topic)[-40:])


def decode_scheduled(kind, log):
    """One queued operation from a log. Returns {id, target, value, selector, block, tx, delay|eta, signature}, or None if the log is
    not a queue event of that family. `selector` is the 4-byte function selector of the queued call ('0x' if empty data)."""
    topics = [_hex(t) for t in log["topics"]]
    if "0x" + topics[0] != QUEUE_TOPICS[kind]:
        return None
    data = bytes.fromhex(_hex(log["data"]))
    block, tx = log["blockNumber"], log["transactionHash"]
    base = {"block": int(block, 16) if isinstance(block, str) else int(block), "tx": "0x" + _hex(tx)}
    if kind == "oz":
        target, value, calldata, _pred, delay = decode(["address", "uint256", "bytes", "bytes32", "uint256"], data)
        return {**base, "id": "0x" + topics[1], "index": int(topics[2], 16), "target": Web3.to_checksum_address(target), "value": value,
                "selector": "0x" + calldata[:4].hex() if calldata else "0x", "delay": delay, "signature": None}
    value, signature, calldata, eta = decode(["uint256", "string", "bytes", "uint256"], data)
    return {**base, "id": "0x" + topics[1], "index": 0, "target": _addr(topics[2]), "value": value, "eta": eta,
            "selector": "0x" + calldata[:4].hex() if calldata else "0x", "signature": signature}


def status(now: int, ready_at: int, grace: int = None):
    """'waiting' (before ready_at), 'ready' (executable now), or 'expired' (Compound-style only, past ready_at + grace)."""
    if now < ready_at:
        return "waiting"
    if grace is not None and now > ready_at + grace:
        return "expired"
    return "ready"


def dedupe_ops(ops):
    """A batch OZ operation emits one CallScheduled per index under one id: keep one row per id, with the count of calls."""
    seen = {}
    for o in ops:
        r = seen.setdefault(o["id"], {**o, "calls": 0})
        r["calls"] += 1
    return list(seen.values())
