#!/usr/bin/env python3
"""Money at risk, by cause: watch/risk_by_cause.json. The dashboard says how much tracked money sits under low scores; this says
why, from the independent reads of the run: behind a plain-key admin, behind a multisig made of plain keys only, with no delay on
the admin path, behind an implementation with no verified source, frozen if one key is lost, with an upgrade approved and
executable, with an admin transfer in flight. A contract can sit under several causes; money is counted once per protocol and
chain inside a cause (DefiLlama figures, the 08/10 rule). No RPC.

    python3 scripts/risk_by_cause.py --watch watch --out watch/risk_by_cause.json
"""
import argparse, glob, json, os, sys, time

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from evaluate_rules import lower_keys, WATCH_SLUGS, norm, PENDING_CHAIN  # noqa: E402


def load(p):
    try: return json.load(open(p))
    except Exception: return None  # noqa: BLE001


CAUSES = [("side_role_plain_key", "a secondary role (curator, guardian, pauser) is held by a plain key"), ("plain_key_admin", "the admin is a plain key"), ("keys_only_multisig", "the admin multisig is made of plain keys only"), ("no_delay", "no delay on the admin path (no timelock, no Zodiac delay, no Squads time lock)"),
          ("unverified_code", "the code behind the proxy has no verified source (Sourcify) or build (OtterSec)"), ("one_key_freezes", "one lost key freezes the admin multisig"), ("upgrade_executable", "an upgrade is approved and executable now"), ("transfer_in_flight", "an admin transfer is designated and not yet accepted"), ("module_on_safe", "a module is enabled on the admin Safe (executes without the signatures)")]


def money_once(kas, tvl, scope, held):
    """The dashboard's own count (moneyBehind in module-all.js): one figure per protocol and DefiLlama chain, a protocol matched on its
    all-chain total counts once and swallows its per-chain figures, a whole-chain figure counts once per chain, a retired or peripheral
    contract carries nothing, a vault with no match carries what it holds. Before 10/10 this file keyed on the oracle's chain and on the
    slug alone: Ethena counted twice (chain + total), the Hyperliquid bridge's Arbitrum side was lost, five whole-chain figures collapsed into one.
    kas: the <chain>:<address> keys to count; tvl: tvl.json `matched`; scope: data/tvl_scope.json `targets` with lower-case keys; held: held_assets.json `by_target`.
    Module level (it was a closure of main) so that every product that adds money up, the protocol brief included, uses this one rule."""
    seen, totals = {}, set()
    for ka in kas:
        if (scope.get(ka) or {}).get("scope") in ("retired", "peripheral"): continue
        m = tvl.get(ka)
        if not m:
            if (held.get(ka) or {}).get("held_usd"): seen["held:" + ka] = (None, False, float(held[ka]["held_usd"]))
            continue
        s_ = m.get("slug") or m.get("name"); tot = m.get("scope") == "total"; k_ = str(s_) + "|" + ("*" if tot else str(m.get("chain") or ""))
        if tot: totals.add(s_)
        if k_ not in seen: seen[k_] = (s_, tot, float(m.get("tvl") or 0))
    return sum(v for s_, tot, v in seen.values() if tot or s_ not in totals)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--watch", default="watch"); ap.add_argument("--data", default="data"); ap.add_argument("--out", default="watch/risk_by_cause.json"); a = ap.parse_args(); W = a.watch
    scope = lower_keys((load(os.path.join(a.data, "tvl_scope.json")) or {}).get("targets"))   # retired or peripheral contracts: counted as contracts, never as money
    pub = os.path.join(W, "tvl_scope.json"); json.dump({"what": "copy of data/tvl_scope.json for the dashboard and the pages: a retired or peripheral contract carries none of its protocol's TVL; keyed <chain>:<address>", "targets": scope}, open(pub + ".tmp", "w"), indent=1); os.replace(pub + ".tmp", pub)
    so = {r["chain"] + ":" + norm(r["target"]).lower(): r for r in (load(os.path.join(W, "second_opinion.json")) or {}).get("results", []) if not r.get("oracle_self")}
    tvl = (load(os.path.join(W, "tvl.json")) or {}).get("matched", {}); isrc = (load(os.path.join(W, "impl_sources.json")) or {}).get("by_target", {})
    plain_side = set((load(os.path.join(W, "side_roles.json")) or {}).get("plain_key_roles") or [])   # since 2026-10-10: roles the admin handed out (side_roles.py)
    pend = load(os.path.join(W, "pending_ops.json")) or {}; upg_live = set()
    for tl in pend.get("results", []):
        ck = PENDING_CHAIN.get(tl.get("chain"), tl.get("chain"))
        for op in tl.get("pending", []):
            if op.get("state") == "ready" and (op.get("decoded") == "program upgrade" or "upgrade" in str(op.get("signature") or "").lower()): upg_live.add(ck + ":" + norm(op.get("target")).lower())
    targets = {}
    for f in sorted(glob.glob(os.path.join(W, "scores", "*.json"))):
        d = load(f) or {}; key = WATCH_SLUGS.get(os.path.basename(f)[:-5]) or ("solana" if d.get("kind") == "solana" else None)
        if key:
            for t in d.get("targets", []): targets[key + ":" + norm(t["target"]).lower()] = t
    held = (load(os.path.join(W, "held_assets.json")) or {}).get("by_target", {})   # a vault with no DefiLlama match still holds money by its own account (totalAssets, since 2026-10-10): counted as its own protocol
    total_money = money_once(targets, tvl, scope, held)
    out = {}
    for cid, label in CAUSES:
        hits = []
        for ka in targets:
            r = so.get(ka) or {}; k = r.get("kind"); src = isrc.get(ka) or {}
            b = r.get("behind") or {}   # a bare contract holder with an owner() of its own: that owner is the effective hand (since 2026-10-10)
            if k == "contract" and b.get("kind"): k = b["kind"]; r = dict(r, delay_seconds=b.get("delay_seconds"), threshold=b.get("threshold"), owners=b.get("owners"), owners_kinds=None, modules_detail=None)
            if cid == "plain_key_admin": hit = k == "eoa"
            elif cid == "keys_only_multisig": hit = k in ("safe", "squads") and {kk for kk, v in (r.get("owners_kinds") or {}).items() if v} == {"eoa"}
            elif cid == "no_delay": hit = k in ("eoa", "safe", "squads") and not (r.get("delay_seconds") or 0) and not (r.get("self_delay_seconds") or 0) and not (r.get("owners_kinds") or {}).get("timelock") and not any(m.get("kind") == "zodiac-delay" and m.get("cooldown_seconds") for m in (r.get("modules_detail") or []))   # a holder read as a bare "contract" may hide a delay the reader cannot see: not claimed
            elif cid == "unverified_code": hit = src.get("verified") is False
            elif cid == "one_key_freezes": hit = r.get("keys_lost_to_freeze") == 1
            elif cid == "upgrade_executable": hit = ka in upg_live
            elif cid == "transfer_in_flight": hit = bool(r.get("pending_admin"))
            elif cid == "side_role_plain_key": hit = ka in plain_side
            else: hit = bool(r.get("modules"))
            if hit: hits.append(ka)
        money = money_once(hits, tvl, scope, held)
        out[cid] = {"label": label, "contracts": len(hits), "with_tvl": sum(1 for ka in hits if (ka in tvl or (held.get(ka) or {}).get("held_usd")) and (scope.get(ka) or {}).get("scope") not in ("retired", "peripheral")), "out_of_scope": sum(1 for ka in hits if (scope.get(ka) or {}).get("scope") in ("retired", "peripheral")), "tvl_usd": round(money), "share_of_tracked": (round(money / total_money, 3) if total_money else None), "targets": sorted(hits)}
    rec = {"generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "tracked_tvl_usd": round(total_money), "contracts": len(targets), "causes": out,
           "what": "money at risk by cause, from the independent reads of the run (second_opinion.json, impl_sources.json, pending_ops.json) and DefiLlama (tvl.json, one figure per protocol and chain; a contract with no protocol match counts what it holds by its own account, held_assets.json); a contract can sit under several causes; read a cause as the money a single failure of that kind would expose, not as a sum across causes; written by scripts/risk_by_cause.py after every run"}
    tmp = a.out + ".tmp"; json.dump(rec, open(tmp, "w"), indent=1); os.replace(tmp, a.out)
    print("risk by cause: $%.0fM tracked on %d contracts; " % (total_money / 1e6, len(targets)) + "; ".join("%s: %d contract(s), $%.0fM" % (cid, v["contracts"], v["tvl_usd"] / 1e6) for cid, v in out.items()))


if __name__ == "__main__":
    main()
