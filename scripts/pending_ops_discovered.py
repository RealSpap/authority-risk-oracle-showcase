#!/usr/bin/env python3
"""The timelock queues the hand-written watchlist does not cover: every timelock the independent reader found in an admin path
(watch/second_opinion.json, kind "timelock", on a chain the watchlist does not scan) gets its queue read here, with the same
decoding and the same questions as scripts/check_pending_ops.py (what is queued, is it still pending, when is it executable, what
went through lately), then merged into watch/pending_ops.json with "discovered": true, so the feeds, the rules, the calendar,
the calibration and the coverage see them without knowing the difference. Public RPCs refuse wide log ranges on these chains, so
the queue is read in chunks over a bounded window, and each record says how many blocks and about how many days it covers:
a queue event older than that window is not seen (an OpenZeppelin operation never expires), which the record states.

    python3 scripts/pending_ops_discovered.py --so watch/second_opinion.json --pending watch/pending_ops.json --days 14
"""
import argparse, json, os, sys, time

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "lib"))
from web3 import Web3  # noqa: E402
from lib.pending_ops import QUEUE_TOPICS, decode_scheduled, dedupe_ops, status  # noqa: E402
from lib.web3_utils import get_w3  # noqa: E402
from second_opinion import MAINNET, short  # noqa: E402  -- the call RPC per chain key, the one the reader used; short(): a watchlist address may already be shortened by the redaction (a timelock that is also a root signer)
from evaluate_rules import PENDING_CHAIN  # noqa: E402

LOG_RPC = {"ethereum-l1": "https://gateway.tenderly.co/public/mainnet", "arbitrum": "https://gateway.tenderly.co/public/arbitrum", "base": "https://base.rpc.sentio.xyz", "plasma": "https://rpc.plasma.to", "robinhood": "https://rpc.mainnet.chain.robinhood.com", "hyperliquid": "https://rpc.hyperliquid.xyz/evm", "monad": "https://rpc.monad.xyz", "tempo": None}
CHUNK = {"ethereum-l1": 10000000, "arbitrum": 10000000, "base": 10000, "plasma": 10000, "robinhood": 20000, "hyperliquid": 1000, "monad": 100, "tempo": 10000}   # the widest eth_getLogs range each public RPC accepted (probed 2026-10-10; Tenderly reads the whole range)
MAX_CHUNKS = 60   # per timelock and run: bounds the job's RPC budget; the record says how far back it reached
MAX_CHUNKS_BY = {"robinhood": 150}   # a 0.1 s block time: 150 x 20 000 blocks is still only about 3.5 days, said in the record
KEY_OF = {v: k for k, v in PENDING_CHAIN.items()}   # chain key -> the chain name pending_ops.json uses


def _call(w3, to, sig, arg=b""): return w3.eth.call({"to": Web3.to_checksum_address(to), "data": Web3.keccak(text=sig)[:4] + arg})
def _b32(h): return bytes.fromhex(h[2:] if h.startswith("0x") else h).rjust(32, b"\0")


def read_queue(name, key, address, family, days, recent_days):
    out = {"name": name, "chain": KEY_OF.get(key, key), "address": address, "family": family, "status": "ok", "queued_events": None, "latest_queued": None, "pending": [], "recent": [], "discovered": True, "log_rpc": LOG_RPC.get(key)}
    if not LOG_RPC.get(key): out["status"] = "UNREAD (no log source known for this chain)"; return out
    try:
        logs_w3, calls_w3 = get_w3(LOG_RPC[key]), get_w3(MAINNET[key] if key in MAINNET else LOG_RPC[key])
        if calls_w3.eth.get_code(Web3.to_checksum_address(address)) == b"": out["status"] = "UNREAD (no code at this address on this chain: an alias of a contract on another chain)"; return out
        try: out["delay"] = int.from_bytes(_call(calls_w3, address, "getMinDelay()" if family == "oz" else "delay()"), "big")
        except Exception:  # noqa: BLE001 -- the reader's family guess can be wrong: the other family's getter decides
            family = "compound" if family == "oz" else "oz"; out["family"] = family; out["delay"] = int.from_bytes(_call(calls_w3, address, "getMinDelay()" if family == "oz" else "delay()"), "big")
        if family != "oz": out["grace"] = int.from_bytes(_call(calls_w3, address, "GRACE_PERIOD()"), "big")
        head = logs_w3.eth.block_number; b0, b1 = logs_w3.eth.get_block(head - 1000), logs_w3.eth.get_block(head)
        bt = max(0.05, (b1["timestamp"] - b0["timestamp"]) / 1000.0)   # measured block time, not assumed
        want = int(days * 86400 / bt); span = min(want, CHUNK[key] * MAX_CHUNKS_BY.get(key, MAX_CHUNKS)); start = max(0, head - span)
        raw = []; frm = start
        while frm <= head:
            to = min(head, frm + CHUNK[key] - 1)
            raw += logs_w3.eth.get_logs({"address": Web3.to_checksum_address(address), "topics": [QUEUE_TOPICS[family]], "fromBlock": frm, "toBlock": to}); frm = to + 1; time.sleep(0.05)
        ops = [o for o in (decode_scheduled(family, lg) for lg in raw) if o]
        out.update({"queued_events": len(ops), "window_blocks": head - start, "window_days_est": round((head - start) * bt / 86400, 1), "window_note": ("the whole %d-day window" % days) if span >= want else "bounded by the RPC budget: a queue event older than this window is not seen; an OpenZeppelin operation never expires"})
        now = int(time.time())
        if ops: out["latest_queued"] = max(logs_w3.eth.get_block(o["block"])["timestamp"] for o in ops[-3:])
        recent_from = head - int(recent_days * 86400 / bt)
        for op in dedupe_ops(ops):
            if family == "oz":
                still = bool(int.from_bytes(_call(calls_w3, address, "isOperationPending(bytes32)", _b32(op["id"])), "big"))
                ready = int.from_bytes(_call(calls_w3, address, "getTimestamp(bytes32)", _b32(op["id"])), "big") if still else None; grace = None
            else:
                still = bool(int.from_bytes(_call(calls_w3, address, "queuedTransactions(bytes32)", _b32(op["id"])), "big")); ready, grace = op["eta"], out["grace"]
            if still: out["pending"].append({**op, "ready_at": ready, "state": status(now, ready, grace)})
            if op["block"] >= recent_from: out["recent"].append({**op, "still_queued": still, "queued_at": logs_w3.eth.get_block(op["block"])["timestamp"]})
    except Exception as e:  # noqa: BLE001 -- any unread part makes the whole timelock UNREAD, never "nothing pending"
        out["status"] = "UNREAD (%s: %s)" % (type(e).__name__, str(e)[:120])
    return out


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--so", default="watch/second_opinion.json"); ap.add_argument("--pending", default="watch/pending_ops.json")
    ap.add_argument("--days", type=int, default=14); ap.add_argument("--recent-days", type=int, default=14); a = ap.parse_args()
    so = json.load(open(a.so)) if os.path.exists(a.so) else {"results": []}
    pend = json.load(open(a.pending)) if os.path.exists(a.pending) else {"results": []}
    kept = [r for r in pend.get("results", []) if not r.get("discovered")]
    watched = {(r.get("chain"), short(str(r.get("address", "")).lower())) for r in kept}   # compared on short forms: the published file may carry a shortened address
    found = {}
    for r in so.get("results", []):
        if r.get("kind") != "timelock" or not r.get("holder") or r.get("alias_of") or r.get("oracle_self"): continue
        key = r["chain"]; addr = str(r["holder"]).lower()
        if key not in KEY_OF or (KEY_OF[key], short(addr)) in watched or "…" in addr: continue
        found.setdefault((key, addr), {"family": "compound" if r.get("timelock_family") == "compound" else "oz", "targets": []})["targets"].append(r["target"])
    new = []
    for (key, addr), info in sorted(found.items()):
        name = "%s timelock %s…%s, found by the independent reader (%d tracked contract%s)" % (key, addr[:6], addr[-4:], len(info["targets"]), "s" if len(info["targets"]) > 1 else "")
        rec = read_queue(name, key, addr, info["family"], a.days, a.recent_days); rec["governs"] = info["targets"]; new.append(rec)
        print("%s: %s; %s queue event(s) over %s block(s) (about %s d), %d pending, %d recent" % (name, rec["status"][:60], rec.get("queued_events"), rec.get("window_blocks"), rec.get("window_days_est"), len(rec["pending"]), len(rec["recent"])))
    pend["results"] = kept + new; pend["discovered_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()); pend["discovered"] = len(new)
    tmp = a.pending + ".tmp"; json.dump(pend, open(tmp, "w"), indent=1); os.replace(tmp, a.pending)
    print("pending ops: %d timelock(s) from the watchlist + %d discovered by the independent reader (%d unread)" % (len(kept), len(new), sum(1 for r in new if r["status"] != "ok")))


if __name__ == "__main__":
    main()
