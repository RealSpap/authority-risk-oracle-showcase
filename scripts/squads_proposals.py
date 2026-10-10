#!/usr/bin/env python3
"""The Solana counterpart of the timelock queues: the proposals of every Squads v4 multisig the independent reader resolved
(watch/second_opinion.json, kind "squads"). A proposal is a Proposal account of the multisig: active (awaiting votes), approved
(the time lock runs from the approval, then any executor can execute it, at any time, until the multisig's stale index passes it),
executed, rejected, cancelled. Approved-and-live proposals are the loaded guns; approved ones past the stale index are dead.
Merged into watch/pending_ops.json as records with family "squads" and "discovered": true, so the feeds, the rules, the calendar,
the calibration, the review queue and the coverage see them like a timelock queue. Two RPC calls per multisig.

    python3 scripts/squads_proposals.py --so watch/second_opinion.json --pending watch/pending_ops.json --recent-days 14
"""
import argparse, base64, hashlib, json, os, struct, sys, time

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from second_opinion import sol_rpc, b58encode, b58decode, on_curve_bytes, SQUADS_V4  # noqa: E402

PROPOSAL_DISC = b58encode(hashlib.sha256(b"account:Proposal").digest()[:8])
STATUS = {0: "draft", 1: "active", 2: "rejected", 3: "approved", 4: "executing", 5: "executed", 6: "cancelled"}
DISC = {hashlib.sha256(b"account:" + n).digest()[:8]: n.decode() for n in (b"VaultTransaction", b"ConfigTransaction", b"Batch")}
KNOWN = {"BPFLoaderUpgradeab1e11111111111111111111111": "BPF upgradeable loader", "11111111111111111111111111111111": "System", "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA": "Token", "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb": "Token-2022",
         "SQDS4ep65T869zMMBKyuUq6aD6EgTu8psMjkvj52pCf": "Squads v4", "ComputeBudget111111111111111111111111111111": "ComputeBudget", "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL": "Associated Token"}
LOADER_IX = {0: "InitializeBuffer", 1: "Write", 2: "DeployWithMaxDataLen", 3: "Upgrade", 4: "SetAuthority", 5: "Close", 6: "ExtendProgram", 7: "SetAuthorityChecked"}
CONFIG_ACTION = {0: "add member", 1: "remove member", 2: "change threshold", 3: "set time lock", 4: "add spending limit", 5: "remove spending limit", 6: "set rent collector"}
MAX_DECODE = 60   # transaction accounts fetched per run (pending first, then recent): one RPC call each


def tx_pda(ms, index):
    msb, prog = b58decode(ms), b58decode(SQUADS_V4)
    for bump in range(255, -1, -1):
        h = hashlib.sha256(b"multisig" + msb + b"transaction" + struct.pack("<Q", index) + bytes([bump]) + prog + b"ProgramDerivedAddress").digest()
        if not on_curve_bytes(h): return b58encode(h)


def decode_transaction(ms, index, governed, programdata_of):
    """What a proposal does, from its transaction account: a VaultTransaction (instructions: the programs called and, for the BPF
    loader, Upgrade / SetAuthority and the program concerned) or a ConfigTransaction (the multisig's own configuration). Returns
    {kind, text, target, touches_governed} or None when the account is absent or of an unknown kind."""
    pda = tx_pda(ms, index); r = sol_rpc("getAccountInfo", [pda, {"encoding": "base64"}])
    if not r or not r.get("value"): return None
    raw = base64.b64decode(r["value"]["data"][0]); what = DISC.get(raw[:8])
    try:
        if what == "ConfigTransaction":
            o = 8 + 32 + 32 + 8 + 1; n = struct.unpack_from("<I", raw, o)[0]; o += 4; acts = []
            for _ in range(min(n, 20)):
                tag = raw[o]; o += 1; name = CONFIG_ACTION.get(tag, "action %d" % tag)
                if tag in (0,): o += 32 + 1; acts.append(name)
                elif tag == 1: o += 32; acts.append(name)
                elif tag == 2: acts.append("%s to %d" % (name, struct.unpack_from("<H", raw, o)[0])); o += 2
                elif tag == 3: acts.append("%s to %d s" % (name, struct.unpack_from("<I", raw, o)[0])); o += 4
                else: acts.append(name); break   # spending limits and rent collector: variable layouts, named only
            return {"kind": "multisig config", "text": "multisig configuration: " + ", ".join(acts), "target": governed[0], "touches_governed": True}   # the multisig itself changes: every program it governs is concerned
        if what != "VaultTransaction": return None
        o = 8 + 32 + 32 + 8 + 1 + 1 + 1; n = struct.unpack_from("<I", raw, o)[0]; o += 4 + n
        o += 3; nk = struct.unpack_from("<I", raw, o)[0]; o += 4; keys = [b58encode(raw[o + 32 * i:o + 32 * i + 32]) for i in range(nk)]; o += 32 * nk
        ni = struct.unpack_from("<I", raw, o)[0]; o += 4; parts = []; target = None; touches = False; kind = "call"
        for _ in range(min(ni, 20)):
            pi = raw[o]; o += 1; na = struct.unpack_from("<I", raw, o)[0]; o += 4; accs = [keys[x] for x in raw[o:o + na] if x < len(keys)]; o += na; nd = struct.unpack_from("<I", raw, o)[0]; o += 4; data = raw[o:o + nd]; o += nd
            pid = keys[pi] if pi < len(keys) else "an address from a lookup table"; name = KNOWN.get(pid)
            if pid == "ComputeBudget111111111111111111111111111111": continue
            if name == "BPF upgradeable loader":
                ix = struct.unpack_from("<I", data, 0)[0] if len(data) >= 4 else -1; ixn = LOADER_IX.get(ix, "instruction %d" % ix)
                prog_acc = accs[1] if ix == 3 and len(accs) > 1 else next((p for p, pd in programdata_of.items() if pd in accs), None) or (accs[0] if accs else None)
                parts.append("%s of program %s" % (ixn, prog_acc)); kind = "program upgrade" if ix == 3 else "program authority change" if ix in (4, 7) else "loader " + ixn
                if prog_acc in governed or any(programdata_of.get(g) in accs for g in governed): touches = True; target = prog_acc if prog_acc in governed else next(g for g in governed if programdata_of.get(g) in accs)
                elif target is None: target = prog_acc
            elif name == "System": parts.append("System transfer" if (len(data) >= 4 and struct.unpack_from("<I", data, 0)[0] == 2) else "System call"); kind = kind if kind != "call" else "transfer"
            elif name in ("Token", "Token-2022"): parts.append("%s %s" % (name, {3: "transfer", 12: "transfer", 7: "mint", 6: "set authority"}.get(data[0] if data else -1, "instruction"))); kind = kind if kind != "call" else "transfer"
            elif pid in governed: parts.append("call to the governed program %s" % pid); touches = True; target = pid; kind = "call to the governed program"
            elif name == "Squads v4": parts.append("Squads v4 call")
            else: parts.append("call to %s" % pid); target = target or pid
            if not touches and any(a in governed for a in accs): touches = True; target = next(a for a in accs if a in governed)
        return {"kind": kind, "text": "; ".join(parts) or "no instruction", "target": target or governed[0], "touches_governed": touches}
    except (struct.error, IndexError): return None


def read_multisig_indexes(ms):
    r = sol_rpc("getAccountInfo", [ms, {"encoding": "base64"}])
    if not r or not r.get("value"): return None
    raw = base64.b64decode(r["value"]["data"][0]); o = 8 + 32 + 32; o += 2 + 4
    return {"transaction_index": struct.unpack_from("<Q", raw, o)[0], "stale_transaction_index": struct.unpack_from("<Q", raw, o + 8)[0]}


def read_proposals(ms):
    r = sol_rpc("getProgramAccounts", [SQUADS_V4, {"encoding": "base64", "filters": [{"memcmp": {"offset": 0, "bytes": PROPOSAL_DISC}}, {"memcmp": {"offset": 8, "bytes": ms}}]}])
    if r is None: return None
    out = []
    for a in r:
        raw = base64.b64decode(a["account"]["data"][0]); o = 8 + 32; idx = struct.unpack_from("<Q", raw, o)[0]; o += 8; st = raw[o]; o += 1; ts = None
        if st != 0 and len(raw) >= o + 8: ts = struct.unpack_from("<q", raw, o)[0]; o += 8   # every status but Draft carries a timestamp
        o += 1; na = struct.unpack_from("<I", raw, o)[0]; o += 4; o += 32 * na; nr = struct.unpack_from("<I", raw, o)[0] if len(raw) >= o + 4 else 0
        out.append({"index": idx, "status": STATUS.get(st, str(st)), "timestamp": ts if (ts and ts > 1e9) else None, "approvals": na, "rejections": nr, "account": a["pubkey"]})
    return sorted(out, key=lambda p: p["index"])


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--so", default="watch/second_opinion.json"); ap.add_argument("--pending", default="watch/pending_ops.json"); ap.add_argument("--recent-days", type=int, default=14); a = ap.parse_args()
    so = json.load(open(a.so)) if os.path.exists(a.so) else {"results": []}
    by_ms = {}; programdata_of = {}
    for r in so.get("results", []):
        if r.get("kind") == "squads" and r.get("multisig"):
            by_ms.setdefault(r["multisig"], {"targets": [], "delay": r.get("delay_seconds") or 0, "threshold": r.get("threshold"), "owners": r.get("owners")})["targets"].append(r["target"])
            if r.get("programdata"): programdata_of[r["target"]] = r["programdata"]
    decoded = 0
    pend = json.load(open(a.pending)) if os.path.exists(a.pending) else {"results": []}
    kept = [x for x in pend.get("results", []) if x.get("family") != "squads"]
    now = int(time.time()); recent_from = now - a.recent_days * 86400; new = []
    for ms, info in sorted(by_ms.items()):
        rec = {"name": "Squads v4 multisig %s…%s (%d-of-%d, time lock %d s), found by the independent reader (%d tracked program%s)" % (ms[:4], ms[-4:], info["threshold"] or 0, info["owners"] or 0, info["delay"], len(info["targets"]), "s" if len(info["targets"]) > 1 else ""),
               "chain": "solana", "address": ms, "family": "squads", "status": "ok", "discovered": True, "governs": info["targets"], "delay": info["delay"], "queued_events": None, "latest_queued": None, "pending": [], "recent": [], "active": [], "stale_approved": 0, "proposals": {}}
        idx = read_multisig_indexes(ms); time.sleep(0.3); props = read_proposals(ms); time.sleep(0.3)
        if idx is None or props is None: rec["status"] = "UNREAD (multisig account or proposals not answered)"; new.append(rec); continue
        stale = idx["stale_transaction_index"]; rec["queued_events"] = len(props); rec["stale_transaction_index"] = stale; rec["transaction_index"] = idx["transaction_index"]
        for p in props: rec["proposals"][p["status"]] = rec["proposals"].get(p["status"], 0) + 1
        for p in props:
            tgt = info["targets"][0]   # the operation hits the program the multisig governs (the vault transaction's own instructions are not decoded here)
            if p["status"] == "approved":
                if p["index"] <= stale: rec["stale_approved"] += 1; continue
                ready = (p["timestamp"] or now) + info["delay"]
                rec["pending"].append({"id": "squads:%s:%d" % (ms, p["index"]), "index": p["index"], "target": tgt, "value": 0, "selector": None, "signature": "Squads proposal #%d (%d approval%s)" % (p["index"], p["approvals"], "" if p["approvals"] == 1 else "s"), "ready_at": ready, "state": "ready" if now >= ready else "waiting", "approved_at": p["timestamp"], "account": p["account"], "undecoded": True})   # undecoded: the vault transaction's instructions are not read; it may be a treasury transfer, not an action on the program
            elif p["status"] == "active" and p["index"] > stale:
                rec["active"].append({"index": p["index"], "approvals": p["approvals"], "rejections": p["rejections"], "since": p["timestamp"], "account": p["account"]})
            elif p["status"] == "executed" and p["timestamp"] and p["timestamp"] >= recent_from:
                rec["recent"].append({"id": "squads:%s:%d" % (ms, p["index"]), "index": p["index"], "target": tgt, "value": 0, "selector": None, "signature": "Squads proposal #%d executed" % p["index"], "still_queued": False, "queued_at": p["timestamp"], "executed_at": p["timestamp"], "account": p["account"], "undecoded": True})
        for op in sorted(rec["pending"], key=lambda x: x["ready_at"]) + sorted(rec["recent"], key=lambda x: -(x["queued_at"] or 0)):   # what each live or recent proposal does: the transaction account, decoded
            if decoded >= MAX_DECODE: break
            d = decode_transaction(ms, op["index"], info["targets"], programdata_of); decoded += 1; time.sleep(0.2)
            if d:
                op.update({"undecoded": False, "decoded": d["kind"], "what": d["text"], "target": d["target"] or op["target"], "touches_governed": d["touches_governed"]})
                op["signature"] = "Squads proposal #%d: %s%s" % (op["index"], d["text"][:160], "" if d["touches_governed"] else " (not the tracked program)")
        if props: rec["latest_queued"] = max((p["timestamp"] or 0) for p in props) or None
        new.append(rec)
        print("%s: %d proposal(s) %s; %d approved and live (%d executable now), %d awaiting votes, %d approved but stale, %d executed in %d d" % (rec["name"][:46], len(props), rec["proposals"], len(rec["pending"]), sum(1 for p in rec["pending"] if p["state"] == "ready"), len(rec["active"]), rec["stale_approved"], len(rec["recent"]), a.recent_days))
    pend["results"] = kept + new; pend["squads_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    tmp = a.pending + ".tmp"; json.dump(pend, open(tmp, "w"), indent=1); os.replace(tmp, a.pending)
    print("squads proposals: %d multisig(s), %d approved-and-live proposal(s) in all (%d executable now), %d transaction(s) decoded" % (len(new), sum(len(r["pending"]) for r in new), sum(1 for r in new for p in r["pending"] if p["state"] == "ready"), decoded))
    for r in new:
        for op in r["pending"] + r["recent"]:
            if not op.get("undecoded", True): print("  %s #%d %s: %s%s" % (r["address"][:8], op["index"], "LIVE" if op in r["pending"] else "executed", op["what"][:120], "" if op.get("touches_governed") else " (not the tracked program)"))


if __name__ == "__main__":
    main()
