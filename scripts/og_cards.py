#!/usr/bin/env python3
"""One share card (PNG, 1200x630) per tracked target, for link previews on X, Discord, Telegram, Farcaster.

Drawn with Pillow from the watch files, no browser: the score in its band colour, the five sub-scores as a rosette,
the protocol name (DefiLlama name when the target is matched in watch/tvl.json, else the short address) and the chain.
A card is rewritten only when its bytes change, so a run that moved nothing commits nothing.

    python3 scripts/og_cards.py --scores watch/scores --tvl watch/tvl.json --out watch/og
"""
import argparse, re, glob, io, json, math, os, sys
from PIL import Image, ImageDraw, ImageFont

def _dump_json(obj, path, indent=None):
    """Write the file only once the whole object is serialised: a crash half-way never leaves a truncated JSON behind
    (the previous run's file stays), and a reader never sees a half-written one."""
    import json as _j, os as _o
    tmp = path + ".tmp"
    with open(tmp, "w") as f: _j.dump(obj, f, indent=indent)
    _o.replace(tmp, path)


WATCH_SLUGS = {"robinhood-chain": "robinhood", "ethereum-l1-sepolia": "ethereum-l1", "arbitrum-sepolia": "arbitrum", "base-sepolia": "base",
               "plasma": "plasma", "tempo-moderato": "tempo", "monad": "monad", "hyperliquid-hyperevm": "hyperliquid", "solana-devnet": "solana"}
LABEL = {"robinhood": "Robinhood Chain", "ethereum-l1": "Ethereum L1", "arbitrum": "Arbitrum", "base": "Base", "plasma": "Plasma",
         "tempo": "Tempo", "monad": "Monad", "hyperliquid": "Hyperliquid", "solana": "Solana"}
BANDS = [(0, 19, "critical", (255, 77, 109)), (20, 39, "weak", (255, 146, 72)), (40, 59, "moderate", (255, 211, 77)), (60, 79, "decent", (123, 228, 149)), (80, 100, "strong", (46, 230, 197))]   # the dashboard's neon spectrum (module-all.css --band-*), so a link preview looks like the page it opens
BG, FG, DIM, FAINT = (5, 7, 11), (233, 242, 255), (163, 182, 204), (122, 142, 166)   # the dashboard's ground and ink (module-all.css --bg, --text, --text-dim, --text-faint)
AXES = ["Admin key", "Multisig", "Timelock", "Price feed", "Shared control"]


def norm(a):
    """An EVM address compares lowercase; a Solana program id is base58 and keeps its case."""
    a = str(a); return a.lower() if a.startswith("0x") else a

def band(s):
    for lo, hi, name, col in BANDS:
        if lo <= s <= hi: return name, col
    return BANDS[-1][2], BANDS[-1][3]

def font(size, bold=False):
    for p in (["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf", "/Library/Fonts/Arial Bold.ttf"] if bold else
              ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/System/Library/Fonts/Supplemental/Arial.ttf", "/Library/Fonts/Arial.ttf"]):
        if os.path.exists(p):
            try: return ImageFont.truetype(p, size)
            except Exception: pass
    return ImageFont.load_default()

def card(name, chain, score, sub, checked):
    im = Image.new("RGB", (1200, 630), BG); d = ImageDraw.Draw(im)
    bname, col = band(score)
    d.text((64, 52), "AUTHORITY RISK ORACLE  ·  read from the chain, published on-chain", font=font(22), fill=DIM)
    d.text((64, 118), str(score), font=font(170, True), fill=col)
    w = d.textlength(str(score), font=font(170, True))
    d.text((64 + w + 24, 236), bname.upper(), font=font(40, True), fill=col)
    d.text((64 + w + 24, 282), "out of 100", font=font(26), fill=DIM)
    if name.endswith(" (verified source)"): name = name[:-len(" (verified source)")]   # the Sourcify provenance stays in the page JSON; on a card it only eats the name
    nm = name if len(name) <= 34 else name[:32] + "…"
    # the name must stop before the radar's left label (about x = 520): shrink the font, then cut with an ellipsis
    fs = 52
    while fs > 30 and d.textlength(nm, font=font(fs, True)) > 456: fs -= 2
    while d.textlength(nm, font=font(fs, True)) > 456 and len(nm) > 4: nm = nm[:-2].rstrip() + "…"
    d.text((64, 372 + (52 - fs) // 2), nm, font=font(fs, True), fill=FG)
    d.text((64, 440), chain, font=font(30), fill=DIM)
    d.text((64, 548), "Can one person move this protocol's funds?   realspap.github.io/oracle" + ("   ·   checked " + checked if checked else ""), font=font(22), fill=FAINT)
    # rosette
    cx, cy, R = 890, 300, 140
    def pt(i, rr): a = -math.pi / 2 + i * 2 * math.pi / 5; return (cx + rr * math.cos(a), cy + rr * math.sin(a))
    for v in (25, 50, 75, 100): d.polygon([pt(i, R * v / 100) for i in range(5)], outline=(70, 66, 58))
    for i in range(5): d.line([(cx, cy), pt(i, R)], fill=(70, 66, 58), width=1)
    shape = [pt(i, 6 + (R - 6) * max(0, min(100, sub[i])) / 100) for i in range(5)]
    ov = Image.new("RGBA", im.size, (0, 0, 0, 0)); od = ImageDraw.Draw(ov); od.polygon(shape, fill=col + (80,), outline=col + (255,), width=4); im.paste(Image.alpha_composite(im.convert("RGBA"), ov).convert("RGB"))
    d = ImageDraw.Draw(im)
    for i in range(5):
        x, y = pt(i, R + 34); t = AXES[i] + " " + str(sub[i]); f = font(22, True); tw = d.textlength(t, font=f)
        tx = x - (tw if x < cx - 5 else 0 if x > cx + 5 else tw / 2); tx = max(560, min(tx, 1180 - tw))
        d.text((tx, y - 12), t, font=f, fill=DIM)
    return im

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--scores", default="watch/scores"); ap.add_argument("--names", default="watch/names.json"); ap.add_argument("--tvl", default="watch/tvl.json"); ap.add_argument("--out", default="watch/og"); ap.add_argument("--dashboard", default="dashboard/index.html"); ap.add_argument("--latest", default="watch/latest.json")
    a = ap.parse_args()
    names = json.load(open(a.names)) if a.names and os.path.exists(a.names) else {}   # on-chain name()/symbol() of the targets the dashboard has no title for, read at the site build (null = none)
    names = {k: v for k, v in names.items() if v}
    # the dashboard's own written titles, per (chain key, target index), when dashboard/index.html is next to the job
    titles = {}
    if os.path.exists(a.dashboard):
        dh = open(a.dashboard).read()
        for gm in re.finditer(r"CHAINS(?:\.(\w+)|\['([\w-]+)'\])\.groups = \[", dh):
            gk = gm.group(1) or gm.group(2); end = dh.find("\n  ];", gm.end()); body = dh[gm.end():end if end > 0 else gm.end() + 200000]
            for om in re.finditer(r"idx: \[([0-9, ]+)\],\s*title: '((?:[^'\\]|\\.)*)'|title: '((?:[^'\\]|\\.)*)',[^{}]*?idx: \[([0-9, ]+)\]", body):
                ix, ti = (om.group(1), om.group(2)) if om.group(1) else (om.group(4), om.group(3))
                for i in ix.split(","): titles[(gk, int(i))] = ti.replace("\\'", "'").split(" - ")[0]
    if os.path.exists(a.tvl):
        for k, m in json.load(open(a.tvl)).get("matched", {}).items():
            if m.get("scope") != "chain-total": names.setdefault(k, m["name"])   # after the on-chain name, before the short address; never a whole-chain figure as a name
    checked = ""
    if os.path.exists(a.latest): checked = json.load(open(a.latest)).get("run_utc", "")[:10]
    written = kept = 0; index = {}
    for f in sorted(glob.glob(os.path.join(a.scores, "*.json"))):
        slug = os.path.basename(f)[:-5]; key = WATCH_SLUGS.get(slug)
        if not key: continue
        d = json.load(open(f))
        for i, t in enumerate(d["targets"]):
            addr = t["target"]; k = key + ":" + norm(addr); name = titles.get((key, t.get("index", i))) or names.get(key + ":" + addr.lower()) or (addr[:6] + "…" + addr[-4:])
            sub = [t.get("adminKeyScore", 0), t.get("multisigScore", 0), t.get("timelockScore", 0), t.get("oracleAuthorityScore", 0), t.get("crossExposureScore", 0)]
            im = card(name, LABEL.get(key, key), int(t["compositeScore"]), sub, "")   # no date on a per-target card: it would change every day and rewrite 161 PNG
            buf = io.BytesIO(); im.save(buf, "PNG", optimize=True); data = buf.getvalue()
            path = os.path.join(a.out, slug, norm(addr) + ".png"); os.makedirs(os.path.dirname(path), exist_ok=True)
            if os.path.exists(path) and open(path, "rb").read() == data: kept += 1
            else: open(path, "wb").write(data); written += 1
            index[k] = {"png": os.path.relpath(path, a.out), "name": name, "score": int(t["compositeScore"])}
    # the page's own card: the headline numbers, so the dashboard link itself previews well
    allrows = []
    for f in sorted(glob.glob(os.path.join(a.scores, "*.json"))):
        key = WATCH_SLUGS.get(os.path.basename(f)[:-5])
        if key: allrows += [(key, norm(t["target"]), int(t["compositeScore"])) for t in json.load(open(f))["targets"]]
    n = len(allrows); n_chains = len(set(r[0] for r in allrows)); crit = sum(1 for r in allrows if r[2] <= 19); under = sum(1 for r in allrows if r[2] < 40)
    matched = json.load(open(a.tvl)).get("matched", {}) if os.path.exists(a.tvl) else {}
    wdir = os.path.dirname(a.tvl) or "."   # the page's rule in full (since 2026-10-10): a retired or peripheral contract carries nothing, a vault DefiLlama lists no protocol for carries what it holds (held_assets.json)
    try: scoped = set((json.load(open(os.path.join(wdir, "tvl_scope.json"))).get("targets") or {}).keys())
    except Exception: scoped = set()  # noqa: BLE001
    try: held = json.load(open(os.path.join(wdir, "held_assets.json"))).get("by_target") or {}
    except Exception: held = {}  # noqa: BLE001
    best = {}
    for key, addr, comp in allrows:
        ka = key + ":" + addr.lower(); m = matched.get(ka)   # tvl.json keys are lowercase even for Solana
        if ka in scoped: continue
        if not m and (held.get(ka) or {}).get("held_usd"): m = {"slug": "held:" + ka, "name": "held by the contract", "tvl": float(held[ka]["held_usd"]), "scope": "contract", "chain": key}
        if not m: continue
        slug = m.get("slug") or m["name"]; tot = m.get("scope") == "total"
        k = slug + "|" + ("*" if tot else str(m.get("chain")))
        if k not in best or comp < best[k][0]: best[k] = (comp, m["tvl"], slug, tot)
    # same rule as the page: a protocol matched on its all-chain total counts once, at the weakest of its setups
    totals = {v[2] for v in best.values() if v[3]}
    for k in [k for k, v in best.items() if v[2] in totals and not v[3]]:
        k2 = best[k][2] + "|*"; t = best[k2]; best[k2] = (min(t[0], best[k][0]), t[1], t[2], True); del best[k]
    at_risk = sum(v[1] for v in best.values() if v[0] < 40); total = sum(v[1] for v in best.values())
    def usd(v): return ("$%.1fB" % (v / 1e9)) if v >= 1e9 else ("$%.0fM" % (v / 1e6)) if v >= 1e6 else ("$%.0fk" % (v / 1e3))
    im = Image.new("RGB", (1200, 630), BG); d = ImageDraw.Draw(im)
    d.text((64, 52), "AUTHORITY RISK ORACLE  ·  read from the chain, published on-chain", font=font(22), fill=DIM)
    d.text((64, 110), "Can one person move", font=font(72, True), fill=FG); d.text((64, 190), "this protocol's funds?", font=font(72, True), fill=FG)
    d.text((64, 300), usd(at_risk), font=font(96, True), fill=BANDS[0][3])
    d.text((64, 410), "sits in DeFi deployments where one key or one thin multisig holds the power,", font=font(28), fill=DIM)
    d.text((64, 446), "out of %s tracked across %d contracts on %d chains." % (usd(total), n, n_chains), font=font(28), fill=DIM)
    d.text((64, 548), "%d critical  ·  %d under 40  ·  checked %s  ·  realspap.github.io/oracle" % (crit, under, checked), font=font(22), fill=FAINT)
    buf = io.BytesIO(); im.save(buf, "PNG", optimize=True); data = buf.getvalue(); sp = os.path.join(a.out, "summary.png")
    if not (os.path.exists(sp) and open(sp, "rb").read() == data): open(sp, "wb").write(data)
    _dump_json(index, os.path.join(a.out, "index.json"), indent=0)
    print(f"share cards: {written} written, {kept} unchanged, {len(index)} targets")

if __name__ == "__main__":
    sys.exit(main())
