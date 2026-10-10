#!/usr/bin/env python3
"""The same protocol on several chains, hand by hand: watch/cross_chain.json. A user who moves from one deployment to another
assumes the same risk; the scores and the independent reads say otherwise (Ethena: a 5-of-10 Safe on Ethereum, a 24-hour timelock
on Plasma). Groups the tracked contracts by DefiLlama protocol (watch/tvl.json), keeps the protocols present on two chains or more,
and for each chain gives the composite range, the admin kinds the independent reader found and a one-line posture; names the
weakest chain and whether the postures differ. From the files of the run, no RPC.

    python3 scripts/cross_chain.py --watch watch --out watch/cross_chain.json
"""
import argparse, glob, json, os, sys, time

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from evaluate_rules import lower_keys, WATCH_SLUGS, norm, LABEL  # noqa: E402


def load(p):
    try: return json.load(open(p))
    except Exception: return None  # noqa: BLE001


def posture(r):
    """One line for a holder, from the independent read: 'Safe 5-of-10 (10 plain keys)', 'timelock 24 h', 'plain key', 'contract'."""
    k = r.get("kind")
    selfd = (" + contract timelock %d h" % (r["self_delay_seconds"] // 3600)) if r.get("self_delay_seconds") else ""
    if k == "safe":
        ok = r.get("owners_kinds") or {}; comp = ", ".join("%d %s" % (v, {"eoa": "plain keys" if v > 1 else "plain key", "safe": "Safes" if v > 1 else "Safe", "timelock": "timelocks" if v > 1 else "timelock", "contract": "contracts" if v > 1 else "contract", "unread": "not read"}.get(kk, kk)) for kk, v in sorted(ok.items(), key=lambda kv: -kv[1]) if v > 0)
        return "Safe %s-of-%s" % (r.get("threshold"), r.get("owners")) + (" (%s)" % comp if comp else "") + (" +%d module(s)" % len(r["modules"]) if r.get("modules") else "") + selfd
    if k == "timelock": return "timelock %d h" % ((r.get("delay_seconds") or 0) // 3600) + selfd
    if k == "eoa": return "plain key" + selfd
    if k == "squads" and r.get("threshold"): return "Squads %s-of-%s" % (r["threshold"], r["owners"]) + ((" + time lock %d h" % (r["delay_seconds"] // 3600)) if r.get("delay_seconds") else "")
    if k in ("pda", "squads", "immutable", "program"): return k
    if k == "contract":
        b = r.get("behind") or {}
        return "contract" + ((" owned by a timelock %d h" % ((b.get("delay_seconds") or 0) // 3600)) if b.get("kind") == "timelock" else (" owned by a Safe %s-of-%s" % (b.get("threshold"), b.get("owners"))) if b.get("kind") == "safe" else " owned by a plain key" if b.get("kind") == "eoa" else "") + selfd
    return "not read"


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--watch", default="watch"); ap.add_argument("--data", default="data"); ap.add_argument("--out", default="watch/cross_chain.json"); a = ap.parse_args(); W = a.watch
    scope = lower_keys((load(os.path.join(a.data, "tvl_scope.json")) or {}).get("targets"))
    tvl = (load(os.path.join(W, "tvl.json")) or {}).get("matched", {}); so = {r["chain"] + ":" + norm(r["target"]).lower(): r for r in (load(os.path.join(W, "second_opinion.json")) or {}).get("results", []) if not r.get("oracle_self")}
    scores = {}
    for f in sorted(glob.glob(os.path.join(W, "scores", "*.json"))):
        d = load(f) or {}; key = WATCH_SLUGS.get(os.path.basename(f)[:-5]) or ("solana" if d.get("kind") == "solana" else None)
        if key:
            for t in d.get("targets", []): scores[key + ":" + norm(t["target"]).lower()] = t
    groups = {}
    for ka, m in tvl.items():
        if not m.get("slug") or ka not in scores: continue
        key = ka.split(":", 1)[0]; g = groups.setdefault(m["slug"], {"protocol": m.get("name") or m["slug"], "chains": {}})
        c = g["chains"].setdefault(key, {"chain": LABEL.get(key, key), "contracts": 0, "composite_min": 100, "composite_max": 0, "admin_kinds": {}, "postures": [], "tvl_usd": 0.0})
        t = scores[ka]; comp = int(t.get("compositeScore") or 0); c["contracts"] += 1; c["composite_min"] = min(c["composite_min"], comp); c["composite_max"] = max(c["composite_max"], comp)
        if m.get("scope") == "chain" and (scope.get(ka) or {}).get("scope") not in ("retired", "peripheral"): c["tvl_usd"] = max(c["tvl_usd"], float(m.get("tvl") or 0))   # one chain figure per protocol and chain, not summed over its contracts; a retired contract carries none
        r = so.get(ka)
        if r:
            k = r.get("kind") or "unreadable"; c["admin_kinds"][k] = c["admin_kinds"].get(k, 0) + 1
            p = posture(r)
            if p not in c["postures"]: c["postures"].append(p)
    out_protos = []
    for slug, g in groups.items():
        if len(g["chains"]) < 2: continue
        chains = g["chains"]; kinds_sets = [frozenset(k for k in c["admin_kinds"] if k not in ("unreadable", "native")) for c in chains.values()]
        weakest = min(chains.items(), key=lambda kv: kv[1]["composite_min"]); strongest = max(chains.items(), key=lambda kv: kv[1]["composite_min"])
        differs = len(set(s for s in kinds_sets if s)) > 1 or (strongest[1]["composite_min"] - weakest[1]["composite_min"]) >= 15
        out_protos.append({"slug": slug, "protocol": g["protocol"], "chains": chains, "weakest_chain": weakest[0], "weakest_composite": weakest[1]["composite_min"], "strongest_chain": strongest[0], "strongest_composite": strongest[1]["composite_min"],
                           "spread": strongest[1]["composite_min"] - weakest[1]["composite_min"], "postures_differ": differs,
                           "text": "%s: %s" % (g["protocol"], "; ".join("%s %s (composite %s)" % (c["chain"], " / ".join(c["postures"]) or "admin not read", c["composite_min"] if c["composite_min"] == c["composite_max"] else "%d to %d" % (c["composite_min"], c["composite_max"])) for c in sorted(chains.values(), key=lambda c: c["composite_min"])))})
    out_protos.sort(key=lambda p: (-p["postures_differ"], -p["spread"], p["protocol"]))
    out = {"generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "protocols": len(out_protos), "differing": sum(1 for p in out_protos if p["postures_differ"]), "items": out_protos,
           "what": "protocols tracked on two chains or more (grouped by DefiLlama slug, watch/tvl.json): per chain the composite range, the admin kinds the independent reader found and the postures in one line; weakest_chain is the deployment with the lowest composite, postures_differ when the admin kinds differ between chains or the composites are 15 points apart; written by scripts/cross_chain.py after every run"}
    tmp = a.out + ".tmp"; json.dump(out, open(tmp, "w"), indent=1); os.replace(tmp, a.out)
    print("cross-chain: %d protocol(s) on 2+ chains, %d with differing postures" % (len(out_protos), out["differing"]))
    for p in out_protos: print("  %s%s" % ("DIFFERS " if p["postures_differ"] else "", p["text"][:220]))


if __name__ == "__main__":
    main()
