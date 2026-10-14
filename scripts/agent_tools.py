#!/usr/bin/env python3
"""Four questions an AI agent asks before it depends on a contract, answered from the files of the Watch (a clone of the watch-data branch, or any folder with the same files). Read-only, no network, no key,
standard library only. The same four functions serve the MCP server (scripts/mcp_server.py) and the LangChain and AgentKit wrappers (integrations/).

    get_score(W, chain, address)            the score of one contract, where it was read, and a call to replay the reading yourself
    list_targets(W, chain=None, ...)        the tracked contracts that match a filter, with how many rows could not be filtered because a value was not read
    who_controls(W, chain, address)         who can change the contract and how fast, as the independent reader found it
    check_protocol(W, protocol, min_score)  a protocol on every chain it is tracked on: its weakest contract, what was not read, a verdict

Rules for every answer: a value the Watch did not read is `None` and is named in `not_read`; it is never 0, never "ok". `status` says which of three things happened: the answer is read (`ok`), the contract is not
tracked (`not_tracked`), or the file needed for the answer is missing or unreadable (`not_read`). The scores are published on TESTNET oracles for contracts of the networks named in each answer: say so to your user.
"""
import glob, json, os, sys, time

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import compare, dossier, find  # noqa: E402

NOTE = "A reading of who can act on a contract and how fast, from public data, taken at the time shown: not an audit, not investment advice, and it cannot see a change made after that time."
TESTNET = "The scores are pushed to testnet oracles for contracts of the networks named here; the contract itself runs on that network, not on the testnet that stores the score."
GETSCORE_ABI = "getScore(address)((uint8,uint8,uint8,uint8,uint8,uint8,uint64,bytes32))"   # AuthorityRiskOracle (v1), the oracle running today
SUBS = (("admin_key", "adminKeyScore"), ("multisig", "multisigScore"), ("timelock", "timelockScore"), ("price_feed", "oracleAuthorityScore"), ("shared_control", "crossExposureScore"))


def _iso(ts):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts)) if isinstance(ts, (int, float)) and not isinstance(ts, bool) and ts > 0 else None


def _find_target(W, chain, address):
    """(score-file document, target row) or None. The chain may be written as the Watch writes it (robinhood, base, ethereum-l1...) or as its score file."""
    key = dossier.chain_key(chain)
    if not key: return None
    addr = dossier.norm(address)
    for f in sorted(glob.glob(os.path.join(W, "scores", "*.json"))):
        d = dossier.load(f) or {}
        if dossier.WATCH_SLUGS.get(os.path.basename(f)[:-5]) == key or (key == "solana" and d.get("kind") == "solana"):
            for t in d.get("targets", []):
                if dossier.norm(t.get("target")) == addr: return key, d, t
    return None


def _no_state(W):
    return not glob.glob(os.path.join(W, "scores", "*.json"))


def _missing(what, W):
    return {"status": "not_read", "reason": "%s: no score file under %s/scores. The state of the Watch lives on the watch-data branch (https://github.com/RealSpap/authority-risk-oracle-showcase/tree/watch-data), clone it as the folder." % (what, W), "note": NOTE}


def get_score(W, chain, address):
    if _no_state(W): return _missing("get_score", W)
    hit = _find_target(W, chain, address)
    if not hit:
        known = dossier.chain_key(chain)
        return {"status": "not_tracked", "chain": chain, "address": address, "composite": None, "reason": ("unknown chain %r (chains: %s)" % (chain, ", ".join(sorted(dossier.LABEL)))) if not known else "the Watch does not track this contract on %s: that says nothing about its safety" % dossier.LABEL.get(known, known), "note": NOTE}
    key, d, t = hit
    comp = t.get("compositeScore"); subs = {n: t.get(f) for n, f in SUBS}
    not_read = [n for n, v in list(subs.items()) + [("composite", comp)] if v is None]
    rec = {"status": "ok" if comp is not None else "not_read", "chain": key, "network": dossier.LABEL.get(key, key), "address": t.get("target"), "composite": comp, "sub_scores": subs, "stale": t.get("stale"),
           "previous_composite": t.get("previousComposite"), "last_pushed_utc": _iso(t.get("lastUpdated")), "watch_read_utc": _iso(d.get("readAt")), "methodology_hash": t.get("methodologyHash"), "not_read": not_read,
           "oracle": {"name": d.get("name"), "kind": d.get("kind"), "address": d.get("oracle"), "rpc": d.get("rpc"), "block": d.get("block"), "max_staleness_seconds": d.get("maxStaleness")}, "testnet_note": TESTNET, "note": NOTE}
    if d.get("kind") == "evm" and d.get("oracle") and d.get("block") and d.get("rpc") and t.get("target"):
        rec["replay"] = {"command": "cast call %s '%s' %s --rpc-url %s --block %s" % (d["oracle"], GETSCORE_ABI, t["target"], d["rpc"], d["block"]),
                         "how_to_read": "the tuple is (adminKey, multisig, timelock, priceFeed, sharedControl, composite, lastUpdated, methodologyHash); --block needs an archive node: without it you read the latest value, which may be newer than this answer"}
    else:
        rec["replay"] = None
        rec["replay_note"] = "no ready command for this network: read the score account of the oracle program (seeds 'score' + the target) on the cluster named in `oracle`" if d.get("kind") == "solana" else "no replay data in the file"
    return rec


def list_targets(W, chain=None, max_score=None, min_score=None, stale=None, limit=25):
    if _no_state(W): return _missing("list_targets", W)
    if chain and not find.chain_key(chain): return {"status": "not_read", "reason": "unknown chain %r (chains: %s)" % (chain, ", ".join(sorted(find.LABEL))), "note": NOTE}
    rows = [r for r in find.table(W) if not chain or r["chain"] == find.chain_key(chain)]
    unread = [r for r in rows if r["score"] is None]
    sel = [r for r in rows if r["score"] is not None and (max_score is None or r["score"] <= max_score) and (min_score is None or r["score"] >= min_score) and (stale is None or r["stale"] is stale)]
    sel.sort(key=lambda r: (r["score"], r["title"] or ""))
    limit = max(1, min(int(limit), 200))
    return {"status": "ok", "matched": len(sel), "of": len(rows), "returned": min(limit, len(sel)), "score_not_read_so_not_filtered": len(unread),
            "rows": [{"chain": r["chain"], "address": r["target"], "title": r["title"], "protocol": r["protocol"], "composite": r["score"], "stale": r["stale"], "money_usd": r["money_usd"], "kind": r["kind"]} for r in sel[:limit]],
            "sorted_by": "composite, weakest first", "testnet_note": TESTNET, "note": NOTE}


def who_controls(W, chain, address):
    if _no_state(W): return _missing("who_controls", W)
    hit = _find_target(W, chain, address)
    if not hit: return {"status": "not_tracked", "chain": chain, "address": address, "reason": "the Watch does not track this contract: that says nothing about who controls it", "note": NOTE}
    key, d, t = hit; addr = dossier.norm(address)
    so = dossier.load(os.path.join(W, "second_opinion.json"))
    if so is None: return {"status": "not_read", "chain": key, "address": t.get("target"), "reason": "second_opinion.json (the independent reader) is missing or unreadable", "note": NOTE}
    r = next((x for x in so.get("results", []) if x.get("chain") == key and dossier.norm(x.get("target")) == addr), None)
    if r is None: return {"status": "not_read", "chain": key, "address": t.get("target"), "reason": "the independent reader has no record of this contract", "note": NOTE}
    ex = r.get("exposure") if isinstance(r.get("exposure"), dict) else {}
    out = {"status": "not_read" if r.get("kind") in ("unreadable", "native") else "ok", "chain": key, "address": t.get("target"), "admin_kind": r.get("kind"), "posture": r.get("posture"), "admin_holder": r.get("holder"), "path_read": r.get("path"),
           "threshold": r.get("threshold"), "owners": r.get("owners"), "keys_to_act": r.get("keys_to_act"), "keys_lost_to_freeze": r.get("keys_lost_to_freeze"), "delay_summary": (r.get("posture") or "").partition("delay:")[2].strip() or None, "delay_seconds_of_the_admin_timelock": r.get("self_delay_seconds"),
           "modules": r.get("modules"), "guard": r.get("guard"), "pending_admin_change": r.get("pending_admin"), "reader_read_since_utc": r.get("since"), "reader_disagrees_with_score": bool(r.get("disagree")), "disagreement": r.get("disagree") or None,
           "to_move_the_money": {"keys": ex.get("keys_to_move"), "react_hours": ex.get("react_hours"), "money_usd": ex.get("tvl_usd"), "money_source": ex.get("money_source")}, "unreadable_reason": r.get("why") if r.get("kind") in ("unreadable", "native") else None}
    out["not_read"] = sorted(k for k in ("threshold", "keys_to_act", "delay_summary", "admin_holder") if out[k] is None) + (["admin (kind: %s)" % r.get("kind")] if r.get("kind") in ("unreadable", "native") else [])
    out["note"] = NOTE; out["testnet_note"] = TESTNET
    return out


def check_protocol(W, protocol, min_score=0):
    if _no_state(W): return _missing("check_protocol", W)
    rows = find.table(W)
    s, err = compare.summary(W, protocol, rows)
    if err: return {"status": "not_tracked", "protocol": protocol, "reason": err, "note": NOTE}
    weakest = s.get("weakest_score"); read_on = s.get("weakest_score_read_on"); n = s.get("contracts")
    unread = n - read_on if isinstance(n, int) and isinstance(read_on, int) else None
    if weakest is None: verdict = "unread"
    elif weakest < min_score or s.get("stale") or s.get("alerting"): verdict = "fail"
    elif unread: verdict = "unread_part"   # the contracts that were read pass; some were not read, and that is not a pass
    else: verdict = "ok"
    return {"status": "ok", "protocol": s["protocol"], "name": s.get("name"), "verdict": verdict, "min_score": min_score, "contracts": n, "chains": s.get("chains"), "weakest_composite": weakest, "weakest_read_on_contracts": read_on,
            "composite_not_read_on": unread, "stale_contracts": s.get("stale"), "alerting_contracts": s.get("alerting"), "plain_key_admins": s.get("plain_key_admins"), "admin_read_on_contracts": s.get("admin_read_on"),
            "fewest_keys_to_act": s.get("fewest_keys"), "fewest_keys_read_on_contracts": s.get("fewest_keys_read_on"), "shortest_react_hours": s.get("shortest_react_hours"), "shortest_react_read_on_contracts": s.get("shortest_react_read_on"),
            "money_usd": s.get("money_usd"), "meaning": {"ok": "every contract was read, none is stale or alerting, the weakest meets the minimum", "fail": "the weakest is under the minimum, or a contract is stale or alerting",
            "unread_part": "what was read passes but some contracts were not read: not a pass", "unread": "no score was read for this protocol"}[verdict], "testnet_note": TESTNET, "note": NOTE}


def main():
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0]); ap.add_argument("tool", choices=["get_score", "list_targets", "who_controls", "check_protocol"]); ap.add_argument("--watch", default="watch")
    ap.add_argument("--chain"); ap.add_argument("--address"); ap.add_argument("--protocol"); ap.add_argument("--min-score", type=int, default=0); ap.add_argument("--max-score", type=int); ap.add_argument("--limit", type=int, default=25); a = ap.parse_args()
    out = {"get_score": lambda: get_score(a.watch, a.chain, a.address), "who_controls": lambda: who_controls(a.watch, a.chain, a.address), "list_targets": lambda: list_targets(a.watch, a.chain, a.max_score, None, None, a.limit),
           "check_protocol": lambda: check_protocol(a.watch, a.protocol, a.min_score)}[a.tool]()
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
