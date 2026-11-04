#!/usr/bin/env python3
"""Four questions an AI agent asks before it depends on a contract, answered from the files of the Watch (a clone of the watch-data branch, or any folder with the same files). Read-only, no network, no key,
standard library only. The same four functions serve the MCP server (scripts/mcp_server.py) and the LangChain and AgentKit wrappers (integrations/).

    get_score(W, chain, address)            the score of one contract, where it was read, and a call to replay the reading yourself
    list_targets(W, chain=None, ...)        the tracked contracts that match a filter, with how many rows could not be filtered because a value was not read
    who_controls(W, chain, address)         who can change the contract and how fast, as the independent reader found it
    check_protocol(W, protocol, min_score)  a protocol on every chain it is tracked on: its weakest contract, what was not read, a verdict

Rules for every answer: a value the Watch did not read is `None` and is named in `not_read`; it is never 0, never "ok". `status` says which of three things happened: the answer is read (`ok`), the contract is not
tracked (`not_tracked`), or the file needed for the answer is missing or unreadable (`not_read`). A fourth, `retired` (30/10/2026): the contract is marked retired in tvl_scope.json (the protocol's money does not sit behind it); it answers with no score, and is left out of list_targets (counted in `retired_not_listed`, a key that is 0 when nothing is retired) and check_protocol (a protocol whose every contract is retired answers `retired`). The scores are published on TESTNET oracles for contracts of the networks named in each answer: say so to your user.
"""
import glob, json, os, re, sys, time

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import compare, dossier, find, snapshot_rules  # noqa: E402

NOTE = "A reading of who can act on a contract and how fast, from public data, taken at the time shown: not an audit, not investment advice, and it cannot see a change made after that time."
TESTNET = "The scores are pushed to testnet oracles for contracts of the networks named here; the contract itself runs on that network, not on the testnet that stores the score."
GETSCORE_ABI = "getScore(address)((uint8,uint8,uint8,uint8,uint8,uint8,uint64,bytes32))"   # AuthorityRiskOracle (v1), the oracle running today
SUBS = (("admin_key", "adminKeyScore"), ("multisig", "multisigScore"), ("timelock", "timelockScore"), ("price_feed", "oracleAuthorityScore"), ("shared_control", "crossExposureScore"))


def _iso(ts):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts)) if isinstance(ts, (int, float)) and not isinstance(ts, bool) and ts > 0 else None


def _matches(W, chain, address):
    """Every (chain key, score-file document, target row) that names this contract, in file order. The chain may be written as the Watch writes it (robinhood, base, ethereum-l1...) or as its score file."""
    key = dossier.chain_key(chain)
    if not key: return []
    addr = dossier.norm(address); out = []
    for f in sorted(glob.glob(os.path.join(W, "scores", "*.json"))):
        d = dossier.load(f) or {}
        if dossier.WATCH_SLUGS.get(os.path.basename(f)[:-5]) == key or (key == "solana" and d.get("kind") == "solana"):
            out += [(key, d, t) for t in d.get("targets", []) if dossier.norm(t.get("target")) == addr]
    return out


def _find_target(W, chain, address):
    """(chain key, score-file document, target row) of the first row, or None."""
    m = _matches(W, chain, address)
    return m[0] if m else None


def _duplicate_answer(W, chain, address, hit):
    """A contract that a score file lists more than once (30/10/2026): the rows are compared. Equal rows are harmless and the answer carries `duplicate_rows`; rows that differ make the answer `not_read`,
    because the first line is not known to be the current one. Returns (answer to give instead, or None; number of rows)."""
    rows = _matches(W, chain, address)
    if len(rows) < 2: return None, 1
    fields = ("compositeScore", "previousComposite", "stale", "lastUpdated", "methodologyHash") + tuple(f for _, f in SUBS)
    if all(all(r[2].get(f) == hit[2].get(f) for f in fields) for r in rows[1:]): return None, len(rows)
    return {"status": "not_read", "chain": hit[0], "address": hit[2].get("target"), "composite": None, "duplicate": True, "duplicate_rows": len(rows),
            "reason": "the score file lists this contract %d times with different values, so the Watch does not know which row is current" % len(rows), "note": NOTE}, len(rows)


def _retired(W, key, address):
    """The tvl_scope.json record when the contract is marked retired there, else None (no tvl_scope.json = nothing is retired)."""
    return snapshot_rules.retired(snapshot_rules.scope_of(W), key, address)


def _retired_answer(rec, key, address):
    return {"status": "retired", "chain": key, "address": address, "composite": None, "reason": "this contract is marked retired in tvl_scope.json: %s" % (rec.get("note") or "the protocol's money does not sit behind it"),
            "retired_since": rec.get("since"), "note": NOTE}


def _no_state(W):
    return not glob.glob(os.path.join(W, "scores", "*.json"))


def _missing(what, W):
    return {"status": "not_read", "reason": "%s: no score file under %s/scores. The state of the Watch lives on the watch-data branch (https://github.com/RealSpap/authority-risk-oracle-showcase/tree/watch-data), clone it as the folder." % (what, W), "note": NOTE}


_ADDR = re.compile(r"0x[0-9a-fA-F]{40}")
_RPC = re.compile(r"https://[A-Za-z0-9.-]+(:[0-9]{1,5})?(/[A-Za-z0-9._~/%-]*)?")


def _replay_safe(d, t):
    """The `cast call` line is meant to be pasted into a shell: it is built only from an oracle and a target that are addresses, a block that is a whole number and an RPC that is a plain https address with no space,
    quote, `;`, `|`, `&`, `$`, backtick or `#`. A score file is not a trusted input (the local helper and the integrations do not check its signature)."""
    ok_block = isinstance(d.get("block"), int) and not isinstance(d.get("block"), bool) and d["block"] > 0
    return bool(isinstance(d.get("oracle"), str) and _ADDR.fullmatch(d["oracle"]) and isinstance(t.get("target"), str) and _ADDR.fullmatch(t["target"]) and ok_block
                and isinstance(d.get("rpc"), str) and _RPC.fullmatch(d["rpc"]))


def get_score(W, chain, address):
    if _no_state(W): return _missing("get_score", W)
    hit = _find_target(W, chain, address)
    if not hit:
        known = dossier.chain_key(chain)
        return {"status": "not_tracked", "chain": chain, "address": address, "composite": None, "reason": ("unknown chain %r (chains: %s)" % (chain, ", ".join(sorted(dossier.LABEL)))) if not known else "the Watch does not track this contract on %s: that says nothing about its safety" % dossier.LABEL.get(known, known), "note": NOTE}
    key, d, t = hit
    gone = _retired(W, key, t.get("target"))
    if gone: return _retired_answer(gone, key, t.get("target"))
    ambiguous, n_rows = _duplicate_answer(W, chain, address, hit)
    if ambiguous: return ambiguous
    comp = t.get("compositeScore"); subs = {n: t.get(f) for n, f in SUBS}
    not_read = [n for n, v in list(subs.items()) + [("composite", comp)] if v is None]
    # the same three rules as the CI gate and `check` (snapshot_rules): a file of unknown or old age, a composite that is not a whole number from 0 to 100 and a stale flag that is not true/false are NOT an answer
    problem = snapshot_rules.document_problem(d) or snapshot_rules.composite_problem(t) or snapshot_rules.stale_problem(t)
    if snapshot_rules.stale_problem(t): not_read.append("stale")
    if not isinstance(d.get("readAt"), (int, float)) or isinstance(d.get("readAt"), bool): not_read.append("watch_read_utc")
    rec = {"status": "ok" if problem is None else "not_read", "reason": problem, "chain": key, "network": dossier.LABEL.get(key, key), "address": t.get("target"), "composite": comp, "sub_scores": subs, "stale": t.get("stale"),
           "previous_composite": t.get("previousComposite"), "last_pushed_utc": _iso(t.get("lastUpdated")), "watch_read_utc": _iso(d.get("readAt")), "methodology_hash": t.get("methodologyHash"), "not_read": not_read,
           "oracle": {"name": d.get("name"), "kind": d.get("kind"), "address": d.get("oracle"), "rpc": d.get("rpc"), "block": d.get("block"), "max_staleness_seconds": d.get("maxStaleness")}, "testnet_note": TESTNET, "note": NOTE}
    if d.get("kind") == "evm" and _replay_safe(d, t):
        rec["replay"] = {"command": "cast call %s '%s' %s --rpc-url %s --block %s" % (d["oracle"], GETSCORE_ABI, t["target"], d["rpc"], d["block"]),
                         "how_to_read": "the tuple is (adminKey, multisig, timelock, priceFeed, sharedControl, composite, lastUpdated, methodologyHash); --block needs an archive node: without it you read the latest value, which may be newer than this answer"}
    else:
        rec["replay"] = None
        rec["replay_note"] = "no ready command for this network: read the score account of the oracle program (seeds 'score' + the target) on the cluster named in `oracle`" if d.get("kind") == "solana" else "no replay data in the file"
    if n_rows > 1: rec["duplicate_rows"] = n_rows
    return rec


def list_targets(W, chain=None, max_score=None, min_score=None, stale=None, limit=25):
    if _no_state(W): return _missing("list_targets", W)
    if chain and not find.chain_key(chain): return {"status": "not_read", "reason": "unknown chain %r (chains: %s)" % (chain, ", ".join(sorted(find.LABEL))), "note": NOTE}
    scope = snapshot_rules.scope_of(W)
    rows = [r for r in find.table(W) if not chain or r["chain"] == find.chain_key(chain)]
    n_retired = sum(1 for r in rows if snapshot_rules.retired(scope, r["chain"], r["target"])); rows = [r for r in rows if not snapshot_rules.retired(scope, r["chain"], r["target"])]
    pairs = {}   # the contracts that are listed (not the retired ones) which a score file names more than once; the target is already normalised by find.table, which keeps the case of a Solana address
    for r in rows: pairs[(r["chain"], r["target"])] = pairs.get((r["chain"], r["target"]), 0) + 1
    n_duplicate = sum(1 for n in pairs.values() if n > 1)
    unread = [r for r in rows if r["score"] is None]
    sel = [r for r in rows if r["score"] is not None and (max_score is None or r["score"] <= max_score) and (min_score is None or r["score"] >= min_score) and (stale is None or r["stale"] is stale)]
    sel.sort(key=lambda r: (r["score"], r["title"] or ""))
    limit = max(1, min(int(limit), 200))
    return {"status": "ok", "matched": len(sel), "of": len(rows), "returned": min(limit, len(sel)), "score_not_read_so_not_filtered": len(unread), "retired_not_listed": n_retired, "contracts_listed_twice": n_duplicate,
            "rows": [{"chain": r["chain"], "address": r["target"], "title": r["title"], "protocol": r["protocol"], "composite": r["score"], "stale": r["stale"], "money_usd": r["money_usd"], "kind": r["kind"]} for r in sel[:limit]],
            "sorted_by": "composite, weakest first", "testnet_note": TESTNET, "note": NOTE}


def who_controls(W, chain, address):
    if _no_state(W): return _missing("who_controls", W)
    hit = _find_target(W, chain, address)
    if not hit: return {"status": "not_tracked", "chain": chain, "address": address, "reason": "the Watch does not track this contract: that says nothing about who controls it", "note": NOTE}
    key, d, t = hit; addr = dossier.norm(address)
    gone = _retired(W, key, t.get("target"))
    if gone: return _retired_answer(gone, key, t.get("target"))
    ambiguous, n_rows = _duplicate_answer(W, chain, address, hit)
    if ambiguous: return ambiguous
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
    if n_rows > 1: out["duplicate_rows"] = n_rows
    return out


def check_protocol(W, protocol, min_score=0):
    if _no_state(W): return _missing("check_protocol", W)
    scope = snapshot_rules.scope_of(W); all_rows = find.table(W)
    s, err = compare.summary(W, protocol, all_rows)   # the protocol is named on ALL rows: dropping the retired ones first could make the query match another protocol
    if not err:
        hits = compare.match(all_rows, protocol); slug, p = next(iter(hits.items())); live = [r for r in p["rows"] if not snapshot_rules.retired(scope, r["chain"], r["target"])]
        if not live: return {"status": "retired", "protocol": protocol, "reason": "every tracked contract of this protocol is marked retired in tvl_scope.json: the Watch tracks it, and no score of it is a live one", "note": NOTE}
        s = compare.stats(W, rs=live, key=slug, name=p["name"])
    if err: return {"status": "not_tracked", "protocol": protocol, "reason": err, "note": NOTE}
    chains = {r["chain"] for r in live}; slug_of = lambda f, d: dossier.WATCH_SLUGS.get(os.path.basename(f)[:-5]) or ("solana" if (d or {}).get("kind") == "solana" else None)
    file_problems = [p for f in sorted(glob.glob(os.path.join(W, "scores", "*.json"))) for d in [dossier.load(f)] if slug_of(f, d) in chains for p in [snapshot_rules.document_problem(d)] if p]
    if file_problems: return {"status": "not_read", "protocol": protocol, "reason": file_problems[0], "note": NOTE}   # the same age rule as `check`: no verdict on a score file of unknown or old age
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
    # the exit code says what the answer is, so that `agent_tools.py ... && deploy` does not deploy on "not read": 0 read (and a protocol verdict ok), 1 not tracked or a protocol verdict fail, 3 not read (or a protocol verdict unread / unread_part)
    sys.exit(3 if out.get("status") == "not_read" or out.get("verdict") in ("unread", "unread_part") else 1 if out.get("status") == "not_tracked" or out.get("verdict") == "fail" else 0)


if __name__ == "__main__":
    main()
