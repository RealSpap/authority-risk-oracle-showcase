#!/usr/bin/env python3
"""Read-only: WHO MAY CALL the freeze, seize, pause and upgrade functions of the tokens already
tracked by this oracle's Arbitrum ecosystem, read from the verified source rather than from the
function names alone.

Port of chains/ethereum-l1/scripts/sweep_token_function_guards.py to Arbitrum (chain 42161), same
method exactly: fetch each token's verified Solidity source from Blockscout v2 (following an
EIP-1967 proxy to its implementation), find each freeze/seize/pause/upgrade function definition,
read its header modifiers (`onlyOwner`, `onlyRole(...)`, `onlyBlacklister`, ...), and when there is
none, look for an inline check in the first lines of the body. Nothing is sent, no key.

Token list (TOKENS below), not invented: the 77 real markets of Dolomite Margin
(0x6Bd780E7fDf01D77e4d475c821f1e7AE05409072, already tracked by
score_dolomite_margin_arbitrum() in chains/arbitrum-ecosystem/scorers.py), read live on 2026-09-25
via DolomiteMargin.getNumMarkets() + getMarketTokenAddress(i) against https://arb1.arbitrum.io/rpc
-- the exact on-chain analogue of "the tokens a lender holds" the L1 script sweeps for Aave/Compound
-- plus the USDai token (0x0A1a1A107E45b7Ced86833863f482BC5f4ed82EF, address confirmed from
DefiLlama-Adapters projects/usdai/index.js, USDAI_CONTRACT), the stablecoin already tracked via
score_usdai_bridge_adapter_arbitrum()'s mint/burn authority -- that scorer's own notes assert
"blacklist/pause roles" sit on a 3-of-3 Safe but say so was "disclosed context, not re-checked live"
(chains/arbitrum-ecosystem/data/scored_targets_2026-09-25-3-corrections.md, item 11). This sweep
closes exactly that gap by reading the token's own verified source.

Gains Network's gTrade Diamond (0xFF162c694eAA571f685030649814282eA457f169, already tracked via
score_gains_network_diamond_arbitrum()) is NOT a lender with a discrete token list the way Dolomite
or Aave are -- it is a perps engine, and its own GNS token's address was not independently confirmed
this pass (not in DefiLlama-Adapters under an obvious project key). Left out rather than guessed;
see the run's own text output below for the honest note.

A control runs first: Arbitrum-native USDC (Circle, 0xaf88d065e77c8cC2239327C5EDb3A432268e5831,
itself one of the 77 Dolomite market tokens) must read blacklist=onlyBlacklister,
pause=onlyPauser, or the run stops -- same control the L1 script runs against Ethereum-mainnet
USDC, confirming the reader is trustworthy on this chain's Blockscout instance too.
"""
import collections
import json
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

from web3 import Web3

BLOCKSCOUT = "arbitrum.blockscout.com"
RPC = "https://arb1.arbitrum.io/rpc"
EIP1967_IMPLEMENTATION_SLOT = int("0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc", 16)
_w3 = Web3(Web3.HTTPProvider(RPC, request_kwargs={"timeout": 20}))

# The 77 live Dolomite Margin market tokens (chain 42161), read 2026-09-25 via
# DolomiteMargin.getNumMarkets()/getMarketTokenAddress(i) against arb1.arbitrum.io/rpc.
DOLOMITE_MARKET_TOKENS = [
    "0x82aF49447D8a07e3bd95BD0d56f35241523fBab1", "0xDA10009cBd5D07dd0CeCc66161FC93D7c9000da1",
    "0xFF970A61A04b1cA14834A43f5dE4533eBDDB5CC8", "0xf97f4df75117a78c1A5a0DBb814Af92458539FB4",
    "0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f", "0xFd086bC7CD5C481DCC9C85ebE478A1C0b69FCbb9",
    "0x34DF4E8062A8C8Ae97E3382B452bd7BF60542698", "0x912CE59144191C1204E64559FE8253a0e49E6548",
    "0x85667409a723684Fe1e57Dd1ABDe8D88C2f54214", "0x5c80aC681B6b0E7EF6E0751211012601e6cFB043",
    "0x2aDba3f917bb0Af2530F8F295aD2a6fF1111Fc05", "0x7b07E78561a3C2C1Eade652A2a92Da150743F4D7",
    "0xFa7F8980b0f1E64A2062791cc3b0871572f1F7f0", "0xFEa7a6a0B346362BF88A9e4A88416B77a57D6c2A",
    "0x5979D7b546E38E414F7E9822514be443A4800529", "0xEC70Dcb4A1EFa46b8F2D97C310C9c4790ba5ffA8",
    "0x851729Df6C39BDB6E92721f2ADf750023D967eE8", "0xaf88d065e77c8cC2239327C5EDb3A432268e5831",
    "0x3d9907F9a368ad0a51Be60f7Da3b97cf940982D8", "0x539bdE0d7Dbd336b79148AA742883198BBF60342",
    "0x6C2C06790b3E3E3c38e12Ee22F8183b37a13EE55", "0x0c880f6761F1af8d9Aa9C466984b80DAb9a8c9e8",
    "0xC9375EF7635fe556F613AB528C9a2ed946BD075d", "0x1bE165864C918527F2e3e131c2ADc4da9B8c619B",
    "0xfeF14a3A1Ec46D4eB18c784BC1E61297FC68bbc8", "0x10393c20975cF177a3513071bC110f7962CD67da",
    "0x51fC0f6660482Ea73330E414eFd7808811a57Fa2", "0x3082CC23568eA640225c2467653dB90e9250AaA0",
    "0x1d9E10B161aE54FEAbe1E3F71f658cac3468e3C3", "0xfc5A1A6EB076a2C7aD06eD22C90d7E710E35ad0a",
    "0x790FF506ac24b03A21F3d0019227447AE2B55Ca5", "0x2c799166c9f0DbF9EFC5004cbCe4c5A37fA39329",
    "0x1E8e8B7a2F827b3bc12B00eE402145061b7050eF", "0x505582242757f16D72F8C4462A616E388Ca1b074",
    "0x18cB14564FBb015BD3439220D177799355abC0E0", "0x35751007a407ca6FEFfE80b3cB397736D2cf4dbe",
    "0xa2e14377fA6ce3556E2248559E85dc44260e362f", "0x2416092f143378750bb29b79eD961ab195CcEea5",
    "0x12A3bb4FDBC5C932438e067338767eE4A9165f1b", "0x4Cb9a7AE498CEDcBb5EAe9f25736aE7d428C9D66",
    "0x5402B5F40310bDED796c7D0F3FF6683f5C0cFfdf", "0x0C4D46076af67F8ba1cC3C01f7e873BD91EA41ab",
    "0x6Cc56e9cA71147D40b10a8cB8cBe911C1Faf4Cf8", "0x14c60cB8301E879dfb9eecbEbc013353b7e33012",
    "0xB15bbBfCff6c411410c66642306d1FfA7eCEc4D8", "0x2D165A76dd3e552DF3860789331Ab73c5a3d7F92",
    "0x894134a25a5faC1c2C26F1d8fBf05111a3CB9487", "0x20d51CB520C4622Dcc3d7E35003dBaB07d547E7E",
    "0x57F5E098CaD7A3D1Eed53991D4d66C45C9AF7812", "0x4186BFC76E2E237523CBC30FD220FE055156b41F",
    "0x4B82bd687042c4Ea68A2A45b8204dA74be0FB493", "0x9Fb5a64Ce2F659a6039aa57d45975fC097b3F373",
    "0xCeC868060a724199c0fbf62e61449175690a55bD", "0xD8724322f44E5c58D7A815F542036fb17DbbF839",
    "0x5d3a1Ff2b6BAb83b63cd9AD0787074081a52ef34", "0x24C9121C75c099b38D40020872B8A0d2C27c614D",
    "0x1BEEd3b7D1237B7773b5C4c249933E3Ca5e027c1", "0x5c99f6cf6069698D234D50Bf69EBd2f53e45ED1c",
    "0x1EBB1c7023aDdbb2B6e30e6F4C8D4A4440Bfd412", "0xc587646f67b38739006ED0200e2E0a26FDb01c9B",
    "0x24FE352a8303881dC8DeF80783682648623C57D2", "0x26AbfE435447b236b8A014B296E1A8FA2b912AeC",
    "0x6B2a01A5f79dEb4c2f3c0eDa7b01DF456FbD726a", "0xCF248BAF933C7b1B876B997246F25021A65383B3",
    "0xE5d6Fe410c69b44C357403A1936B3BFADDBe340B", "0x6586f1DB71513dAF94b0431156d225a46c00f20b",
    "0xF5063b40fa66aB2fbDa2E6807ac5759A41A1B0c3", "0x7E584529BB40220A2bD5d0c13E3d65aBd4A47F0E",
    "0x11F4532c05fb8eA6320B1DC155BFdC2498A5d8B4", "0x6c84a8f1c29108F47a79964b5Fe888D4f4D0dE40",
    "0x12275DCB9048680c4Be40942eA4D92c74C63b844", "0x18C14C2D707b2212e17d1579789Fc06010cfca23",
    "0xba5DdD1f9d7F570dc94a51479a000E3BCE967196", "0x6491c05A82219b8D1479057361ff1654749b876b",
    "0xdDb46999F8891663a8F2828d25298f70416d7610", "0x23E3df1196b3249c9b0A9476f990F105591872De",
    "0x51Bc8E41cBEc0AA97EC07C73597829c70b2eED46",
]
USDAI_TOKEN = "0x0A1a1A107E45b7Ced86833863f482BC5f4ed82EF"
ARBITRUM_USDC_CONTROL = "0xaf88d065e77c8cC2239327C5EDb3A432268e5831"

TOKENS = sorted(set(a.lower() for a in DOLOMITE_MARKET_TOKENS) | {USDAI_TOKEN.lower()})

FAM = {"freeze": re.compile(r"^(blacklist|unblacklist|addblacklist|removeblacklist|addtoblacklist|setblacklist|freeze|unfreeze|freezeaccount|banaddress|blockaccount|block|unblock|setblocklisted|blocklist|denylist|addtodenylist|updateblacklister)$", re.I),
       "seize": re.compile(r"^(wipe|wipefrozenaddress|destroyblackfunds|seize|clawback|forcetransfer|forcedtransfer|confiscate|forceburn)$", re.I),
       "pause": re.compile(r"^(pause|unpause|setpaused|updatepauser)$", re.I), "upgrade": re.compile(r"^(upgradeto|upgradetoandcall|_authorizeupgrade|changeadmin|upgrade|setimplementation)$", re.I)}
KEYWORDS = {"external", "public", "internal", "private", "view", "pure", "payable", "virtual", "override", "returns", "nonpayable", "returns"}


def curl(url):
    for a in range(5):
        try:
            out = subprocess.run(["curl", "-s", "-m", "60", "-A", "Mozilla/5.0", url], capture_output=True, text=True).stdout
            j = json.loads(out)
            if "Too many" in str(j.get("message", "")): time.sleep(2.0 * (a + 1)); continue
            return j
        except Exception: time.sleep(1.5 * (a + 1))
    return None


def eip1967_implementation(a):
    """Read the EIP-1967 implementation slot directly on-chain -- ADDED beyond the L1 script:
    Blockscout's own `implementations` link (what the L1 script relies on exclusively) is empty for
    at least one already-tracked Arbitrum target (USDai's TransparentUpgradeableProxy) even though
    the implementation IS separately verified under its own address; this falls back to the slot so
    a token is not silently read as "just proxy boilerplate" when that happens. Returns None if the
    slot is zero or the call fails."""
    try:
        raw = _w3.eth.get_storage_at(Web3.to_checksum_address(a), EIP1967_IMPLEMENTATION_SLOT)
        addr = "0x" + raw.hex()[-40:]
        return addr if int(addr, 16) != 0 else None
    except Exception:
        return None


def sources(a):
    """(list of source texts, language, name, note). Follows a proxy to its implementation --
    first via Blockscout's own `implementations` link (as the L1 script does), and if that is
    empty, via a direct EIP-1967 storage-slot read (see eip1967_implementation() above)."""
    d = curl(f"https://{BLOCKSCOUT}/api/v2/smart-contracts/{a}")
    if d is None: return [], None, None, "explorer did not answer"
    if not d.get("is_verified") and not d.get("source_code"): return [], None, d.get("name"), "not verified"
    texts, name = [], d.get("name")
    def take(x): return [x.get("source_code") or ""] + [s.get("source_code") or "" for s in (x.get("additional_sources") or [])]
    texts += take(d)
    impls = [(im.get("address") or im.get("address_hash")) for im in (d.get("implementations") or [])][:1]
    if not impls and "proxy" in (name or "").lower():
        slot_impl = eip1967_implementation(a)
        if slot_impl: impls = [slot_impl]
    for ia in impls:
        di = curl(f"https://{BLOCKSCOUT}/api/v2/smart-contracts/{ia}") if ia else None
        if di is None: return texts, d.get("language"), name, "implementation source not read"
        texts += take(di); name = f"{name} -> {di.get('name')}"
    return [t for t in texts if t], d.get("language"), name, None


DEF = re.compile(r"\bfunction\s+(\w+)\s*\(([^)]*)\)([^{;]*)([{;])", re.S)


def guards(text):
    out = {}
    for m in DEF.finditer(text):
        fn, hdr, end = m.group(1), m.group(3), m.group(4)
        fam = next((f for f, rx in FAM.items() if rx.match(fn)), None)
        if not fam or re.search(r"\b(view|pure)\b", hdr) or (end == ";" and "external" not in hdr and "public" not in hdr): continue
        h = re.sub(r"returns\s*\([^)]*\)", " ", hdr, flags=re.S); h = re.sub(r"override\s*\([^)]*\)", " ", h)
        mods = [(x.group(1) + (re.sub(r"\s+", "", x.group(2)) if x.group(2) else "")) for x in re.finditer(r"(\w+)(\s*\([^)]*\))?", h) if x.group(1) not in KEYWORDS]
        mods = [x for x in mods if not x.startswith(("whenNotPaused", "whenPaused", "nonReentrant", "notBlacklisted", "onlyProxy", "initializer", "reinitializer", "virtual"))]
        inline = None
        if not mods and end == "{":
            body = text[m.end(): m.end() + 500]
            im = re.search(r"(require\s*\([^;]*msg\.sender[^;]*;|_checkRole\s*\([^;]*;|_checkOwner\s*\(\s*\)\s*;|_authorizeUpgrade[^;]*;|if\s*\([^)]*msg\.sender[^)]*\)\s*(revert|\{))", body)
            inline = re.sub(r"\s+", " ", im.group(1))[:90] if im else None
        out.setdefault(fn, []).append(dict(fam=fam, mods=mods, inline=inline, abstract=(end == ";")))
    return out


def analyse(a):
    texts, lang, name, note = sources(a)
    r = dict(token=a, name=name, language=lang, note=note, funcs={})
    if note and not texts: return r
    if lang and lang.lower() != "solidity": r["note"] = f"language {lang}, not read"; return r
    for t in texts:
        for fn, lst in guards(t).items():
            for g in lst:
                if not g["abstract"] or fn not in r["funcs"]: r["funcs"].setdefault(fn, []).append(g)
    return r


def klass(g): return "modifier" if g["mods"] else ("inline" if g["inline"] else ("declared only" if g["abstract"] else "NO GUARD FOUND"))
RANK = {"modifier": 3, "inline": 2, "declared only": 1, "NO GUARD FOUND": 0}


def who(m):
    m = m.split("(")[0] if not m.startswith("onlyRole") else m
    if m == "onlyOwner": return "owner"
    if m.startswith("onlyRole") or m.startswith("onlyRoles"): return "role"
    if m in ("ifAdmin", "onlyAdmin", "proxyAdmin"): return "proxy admin"
    if m.startswith("only"): return "dedicated account (" + m + ")"
    return "other (" + m + ")"


# ---- control: Arbitrum-native USDC (Circle) must read blacklist=onlyBlacklister, pause=onlyPauser
ctl = analyse(ARBITRUM_USDC_CONTROL.lower())
cbl, cp = [g for g in ctl["funcs"].get("blacklist", []) if g["mods"]], [g for g in ctl["funcs"].get("pause", []) if g["mods"]]
if not (any("onlyBlacklister" in g["mods"] for g in cbl) and any("onlyPauser" in g["mods"] for g in cp)):
    sys.exit(f"CONTROL FAILED: Arbitrum USDC blacklist guards {[g['mods'] for g in ctl['funcs'].get('blacklist', [])]}, pause guards {[g['mods'] for g in ctl['funcs'].get('pause', [])]}, note {ctl['note']}; the reader is not trustworthy")
print("control ok: Arbitrum-native USDC blacklist is onlyBlacklister, pause is onlyPauser")

print(f"{len(TOKENS)} tokens (77 live Dolomite Margin markets + USDai, deduplicated)")
with ThreadPoolExecutor(4) as ex:
    rows = list(ex.map(analyse, TOKENS))
unread = [r for r in rows if r["note"] and not r["funcs"]]
print(f"read {len(rows) - len(unread)}, not read {len(unread)}: {collections.Counter(r['note'] for r in unread)}")

byfam = collections.defaultdict(collections.Counter)
for r in rows:
    if not r["funcs"]: continue
    print(f"\n== {r['token']} {r['name']}" + (f"  [{r['note']}]" if r["note"] else ""))
    for fn, lst in sorted(r["funcs"].items(), key=lambda kv: (kv[1][0]["fam"], kv[0])):
        cs = sorted({klass(g) + (": " + " ".join(g["mods"]) if g["mods"] else (": " + g["inline"] if g["inline"] else "")) for g in lst})
        print(f"   {lst[0]['fam']:8s} {fn:24s} " + " | ".join(cs))
        for g in lst: byfam[lst[0]["fam"]][klass(g)] += 1

print("\nfunctions by family and guard class:", {f: dict(c) for f, c in byfam.items()})

print("\nBest guard found per token and family; tokens a family was found on at all:")
for fam in ("freeze", "seize", "pause", "upgrade"):
    n = collections.Counter(); wc = collections.defaultdict(collections.Counter)
    for r in rows:
        gs = [g for lst in r["funcs"].values() for g in lst if g["fam"] == fam]
        if not gs: continue
        best = max((klass(g) for g in gs), key=lambda c: RANK[c])
        n[best] += 1
        if best == "modifier":
            for wm in {who(m) for g in gs if g["mods"] for m in g["mods"]}: wc[best][wm] += 1
    tot = sum(n.values())
    print(f"  {fam:8s} tokens with this function {tot:3d} | " + (", ".join(f"{k} {v} tokens" for k, v in sorted(n.items(), key=lambda kv: -RANK[kv[0]])) if tot else "none found"))
    if wc["modifier"]:
        print(f"           who the modifiers name (a token can have several): " + ", ".join(f"{k} {v}" for k, v in sorted(wc['modifier'].items(), key=lambda kv: -kv[1])))

if len(sys.argv) > 1 and sys.argv[1] == "--dump":
    json.dump(rows, open("arbitrum_token_guards_dump.json", "w"))
    print("wrote arbitrum_token_guards_dump.json")
