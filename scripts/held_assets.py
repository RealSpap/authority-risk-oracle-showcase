#!/usr/bin/env python3
"""What the contract itself holds, read from the contract: watch/held_assets.json. A protocol's TVL (DefiLlama) is attached to every
tracked contract of that protocol, so the money "behind" an admin was the protocol's, not the contract's. An ERC-4626 vault says what it
holds: totalAssets() in asset(), priced by DefiLlama's coin API without a key. 29 of the 179 tracked contracts answer (10/10): for those the
attacker's question (second_opinion.py, exposure) uses the contract's own balance, the others keep the protocol figure and say so.

    python3 scripts/held_assets.py --scores watch/scores --out watch/held_assets.json

Not read: a contract without totalAssets()/asset() (a router, a pool, a token: their balance is not one number), a Solana program. A price
DefiLlama does not know leaves the record unpriced (held_usd null), never a zero.
"""
import argparse, glob, json, os, sys, time, urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from second_opinion import MAINNET, rpc_batch, addr_of  # noqa: E402
from evaluate_rules import WATCH_SLUGS  # noqa: E402

SEL = {"totalAssets": "0x01e1d114", "asset": "0x38d52e0f", "decimals": "0x313ce567", "symbol": "0x95d89b41"}   # keccak checked 10/10
LLAMA = {"ethereum-l1": "ethereum"}   # the other chain keys are DefiLlama's own names (robinhood, plasma, tempo, monad, base, arbitrum, hyperliquid)


def word_int(h):
    return int(h, 16) if (h and h != "0x" and len(h) == 66) else None


def word_str(h):
    try:
        b = bytes.fromhex(h[2:]); n = int.from_bytes(b[32:64], "big"); return b[64:64 + min(n, 64)].decode("utf-8", "replace") if len(b) >= 96 else b[:32].rstrip(b"\0").decode("utf-8", "replace")   # a symbol is a few characters: a token that returns a page of text (a stranger can deploy one) is cut at 64 bytes before it reaches the public file
    except Exception: return None  # noqa: BLE001


def prices(chain, assets):
    if not assets: return {}
    out = {}
    for i in range(0, len(assets), 40):
        q = ",".join(LLAMA.get(chain, chain) + ":" + x for x in assets[i:i + 40])
        try:
            r = json.loads(urllib.request.urlopen(urllib.request.Request("https://coins.llama.fi/prices/current/" + q, headers={"User-Agent": "authority-risk-oracle watch"}), timeout=30).read())
            for k, v in (r.get("coins") or {}).items(): out[k.split(":", 1)[1].lower()] = v
        except Exception as e: print("prices %s: %s" % (chain, str(e)[:80]))  # noqa: BLE001 -- unpriced, not zero
    return out


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--scores", default="watch/scores"); ap.add_argument("--out", default="watch/held_assets.json"); a = ap.parse_args()
    try: prev = json.load(open(a.out)); prev_by = prev.get("by_target") or {}
    except Exception: prev, prev_by = {}, {}  # noqa: BLE001
    by_target, unpriced, asked, unread_chains, carried, vanished = {}, [], 0, [], 0, []
    out_now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    for f in sorted(glob.glob(os.path.join(a.scores, "*.json"))):
        key = WATCH_SLUGS.get(os.path.basename(f)[:-5]); url = MAINNET.get(key)
        if not url: continue
        ts = [t["target"] for t in json.load(open(f)).get("targets", [])]; asked += len(ts)
        r = rpc_batch(url, [c for t in ts for c in (("eth_call", [{"to": t, "data": SEL["totalAssets"]}, "latest"]), ("eth_call", [{"to": t, "data": SEL["asset"]}, "latest"]))])
        # rpc_batch answers "" for a revert (no such getter) and None for a call nobody answered: an RPC down is not 25 contracts without a vault.
        # A target not answered keeps its previous record, marked stale, so the money behind it and the alerts on it do not vanish for one bad run (seen 10/10: a dead Ethereum RPC emptied the file of its 4 vaults)
        dead = [t for i, t in enumerate(ts) if r[2 * i] is None or r[2 * i + 1] is None]   # one of the two calls unanswered is as good as both: the record is kept, not dropped
        if ts and sum(1 for i in range(len(ts)) if r[2 * i] is None and r[2 * i + 1] is None) == len(ts): unread_chains.append(key)
        for t in dead:
            pv = prev_by.get(key + ":" + t.lower())
            if pv: by_target[key + ":" + t.lower()] = dict(pv, stale=True, stale_since=pv.get("stale_since") or prev.get("generated_utc")); carried += 1
        found = {t: (word_int(r[2 * i]), addr_of(r[2 * i + 1])) for i, t in enumerate(ts) if word_int(r[2 * i]) is not None and addr_of(r[2 * i + 1])}
        # a contract that reported its balance last run and now ANSWERS without one (totalAssets() reverts or asset() is empty: an upgrade, a pause, a replaced implementation) is not a contract without a vault: its previous record is kept,
        # marked, and the rules say so (second review of the balance move, 10/10: it used to vanish from the file without a trace)
        for t in ts:
            ka_ = key + ":" + t.lower()
            if t not in found and t not in dead and prev_by.get(ka_):
                pv = prev_by[ka_]; by_target[ka_] = dict(pv, stale=True, stale_since=pv.get("stale_since") or prev.get("generated_utc"), vanished=True, vanished_since=pv.get("vanished_since") or out_now); carried += 1; vanished.append(ka_)
        assets = sorted({v[1].lower() for v in found.values()})
        meta = rpc_batch(url, [c for x in assets for c in (("eth_call", [{"to": x, "data": SEL["decimals"]}, "latest"]), ("eth_call", [{"to": x, "data": SEL["symbol"]}, "latest"]))])
        dec = {x: (word_int(meta[2 * i]), word_str(meta[2 * i + 1])) for i, x in enumerate(assets)}
        px = prices(key, assets)
        for t, (ta, x) in found.items():
            x = x.lower(); d, sym = dec.get(x, (None, None)); p = (px.get(x) or {}); d = d if d is not None else p.get("decimals")
            amount = ta / 10 ** d if d is not None else None; held = amount * p["price"] if (amount is not None and p.get("price") is not None) else None
            rec = {"asset": x, "symbol": p.get("symbol") or sym, "decimals": d, "total_assets": str(ta), "amount": amount, "price_usd": p.get("price"), "price_at": p.get("timestamp"), "held_usd": held}
            pv = prev_by.get(key + ":" + t.lower()) or {}
            # the move of the balance since the previous run, in token units so that a price move does not count (since 2026-10-10): a vault that loses most of its assets between two runs is the most direct sign of a drain
            if pv.get("amount") and pv.get("asset") == x and amount is not None:
                rec["prev_amount"] = pv["amount"]; rec["prev_at"] = pv.get("stale_since") or prev.get("generated_utc"); rec["amount_change_pct"] = round((amount - pv["amount"]) / pv["amount"] * 100, 2)
            if held is None and amount is not None and pv.get("price_usd") is not None and pv.get("asset") == x:   # the price API did not answer: the last known price, said so, rather than no money
                rec.update(price_usd=pv["price_usd"], price_at=pv.get("price_at"), held_usd=amount * pv["price_usd"], price_stale=True); held = rec["held_usd"]
            by_target[key + ":" + t.lower()] = rec
            if held is None: unpriced.append(key + ":" + t.lower())
        print("%s: %d of %d answer totalAssets()/asset(), %d asset(s), %d priced%s" % (key, len(found), len(ts), len(assets), sum(1 for x in assets if x in px), (", %d not answered by the RPC (previous record kept, stale)" % len(dead)) if dead else ""))
    drops = sorted(({"target": k, "symbol": v.get("symbol"), "from": v["prev_amount"], "to": v["amount"], "change_pct": v["amount_change_pct"], "since": v.get("prev_at")} for k, v in by_target.items() if (v.get("amount_change_pct") or 0) <= -30 and not v.get("stale")), key=lambda x: x["change_pct"])
    out = {"generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "asked": asked, "count": len(by_target), "unpriced": unpriced, "drops": drops, "vanished": vanished, "unread_chains": unread_chains, "stale": carried, "by_target": by_target,
           "what": "what each tracked contract holds by its own account: ERC-4626 totalAssets() in asset(), priced by coins.llama.fi; contracts without the getters are absent, not zero; read by scripts/held_assets.py before the second opinion"}
    json.dump(out, open(a.out + ".tmp", "w"), indent=1); os.replace(a.out + ".tmp", a.out)
    for v_ in vanished: print("VANISHED %s: reported its balance last run, no longer answers totalAssets()/asset()" % v_[:44])
    for d_ in drops: print("DROP %s: %.1f%% since %s (%s -> %s %s)" % (d_["target"][:40], d_["change_pct"], d_["since"], round(d_["from"]), round(d_["to"]), d_["symbol"]))
    print("held_assets.json: %d contract(s) priced, %d unpriced, %d asked%s%s" % (len(by_target) - len(unpriced), len(unpriced), asked, (", %d kept from the previous run (RPC not answering, or the getter answers nothing)" % carried) if carried else "", (", chain(s) not read: " + ", ".join(unread_chains)) if unread_chains else ""))


if __name__ == "__main__":
    main()
