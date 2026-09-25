#!/usr/bin/env python3
"""Read-only: who the Aave Governance Guardian is on every chain where Aave V3 runs, and how many chains share the same signers.
    python3 chains/ethereum-l1/scripts/sweep_aave_guardians.py [--dump rows.json]
Aave's official address book (github.com/bgd-labs/aave-address-book, `src/GovernanceV3<Chain>.sol`) names, per chain, the GOVERNANCE_GUARDIAN and the
GRANULAR_GUARDIAN. For each, this reads the account on chain (plain EOA, Safe t-of-n with version and guard, or another contract), then compares the signer
sets of the Safes across chains: the same signers behind different Safe addresses is one group of people on many chains. It also weighs each chain by Aave V3's
TVL on DefiLlama. It does not read what the guardian can do on each chain, only who it is. Nothing is sent, no key."""
import argparse, collections, json, re, subprocess, time
from concurrent.futures import ThreadPoolExecutor
from web3 import Web3
ap = argparse.ArgumentParser(); ap.add_argument("--dump", default=None); ARGS = ap.parse_args()
RPC = {"Ethereum": "https://ethereum-rpc.publicnode.com", "Base": "https://base-rpc.publicnode.com", "Arbitrum": "https://arbitrum-one-rpc.publicnode.com", "Optimism": "https://optimism-rpc.publicnode.com",
       "Polygon": "https://polygon-bor-rpc.publicnode.com", "BNB": "https://bsc-rpc.publicnode.com", "Avalanche": "https://avalanche-c-chain-rpc.publicnode.com", "Gnosis": "https://rpc.gnosischain.com",
       "Scroll": "https://rpc.scroll.io", "Linea": "https://rpc.linea.build", "Mantle": "https://rpc.mantle.xyz", "Sonic": "https://rpc.soniclabs.com", "Celo": "https://forno.celo.org",
       "Metis": "https://andromeda.metis.io/?owner=1088", "ZkSync": "https://mainnet.era.zksync.io", "Ink": "https://rpc-gel.inkonchain.com", "Soneium": "https://rpc.soneium.org", "Plasma": "https://rpc.plasma.to",
       "Monad": "https://rpc.monad.xyz", "XLayer": "https://rpc.xlayer.tech", "Bob": "https://rpc.gobob.xyz", "MegaEth": "https://mainnet.megaeth.com/rpc"}
# PolygonZkEvm and InkWhitelabel have a GovernanceV3*.sol file in the address book but no GOVERNANCE_GUARDIAN/GRANULAR_GUARDIAN constant (checked 2026-09-25): left out on purpose, not missed.
# MegaEth: use mainnet.megaeth.com/rpc, NOT carrot.megaeth.com/rpc (that one is a different network, the "Carrot" testnet, and silently returns EOA for a guardian that is a Safe on mainnet).
LLAMA_NAME = {"BNB": "Binance", "Gnosis": "xDai", "ZkSync": "zkSync Era", "XLayer": "X Layer", "MegaEth": "MegaETH"}
def curl(url, body=None):
    cmd = ["curl", "-s", "-m", "40", "-A", "Mozilla/5.0"] + (["-X", "POST", "-H", "content-type: application/json", "--data", json.dumps(body)] if body else []) + [url]
    for _ in range(3):
        try: return subprocess.run(cmd, capture_output=True, text=True).stdout
        except Exception: pass
sel = lambda s: "0x" + bytes(Web3.keccak(text=s))[:4].hex()
def rpc(ch, m, p):
    # A JSON-RPC error (e.g. publicnode rate-limit -32005) must NOT be read as "no result" -- that silently turns
    # a rate-limited Safe into a fake EOA downstream. Retry with backoff, and return a distinct sentinel on
    # exhaustion so callers can tell "confirmed empty" from "read failed" instead of treating both as falsy.
    for attempt in range(4):
        try: resp = json.loads(curl(RPC[ch], {"jsonrpc": "2.0", "id": 1, "method": m, "params": p}) or "{}")
        except Exception: resp = {}
        if "result" in resp: return resp["result"]
        if attempt < 3: time.sleep(1.5 * (attempt + 1))
    return "RPC_FAILED"
call = lambda ch, to, sig: rpc(ch, "eth_call", [{"to": to, "data": sel(sig)}, "latest"])
def gov(ch):
    src = curl(f"https://raw.githubusercontent.com/bgd-labs/aave-address-book/main/src/GovernanceV3{ch}.sol") or ""
    if src.startswith("404") or "constant" not in src: return ch, None
    g = lambda n: (re.search(n + r"\s*=\s*(0x[0-9a-fA-F]{40})", src) or [None, None])[1]
    return ch, dict(governance=g("GOVERNANCE_GUARDIAN"), granular=g("GRANULAR_GUARDIAN"))
with ThreadPoolExecutor(8) as ex: G = dict(ex.map(gov, RPC))
GUARD = "0x4a204f620c8c5ccdca3fd54d003badd85ba500436a431f0cbda4f558c93c34c8"
def account(ch, a):
    code = rpc(ch, "eth_getCode", [a, "latest"])
    if code == "RPC_FAILED": return dict(kind="read failed (RPC error after retries, not a confirmed EOA)")
    code = code or "0x"
    if code == "0x": return dict(kind="EOA")
    t, o = call(ch, a, "getThreshold()"), call(ch, a, "getOwners()")
    if not (t and t != "0x" and o and len(o) > 130): return dict(kind=f"contract ({(len(code) - 2) // 2} B)")
    h = o[2:]; n = int(h[64:128], 16); v = call(ch, a, "VERSION()"); g = rpc(ch, "eth_getStorageAt", [a, GUARD, "latest"])
    return dict(kind="Safe", thr=int(t, 16), n=n, owners=sorted("0x" + h[128 + 64 * i + 24: 128 + 64 * (i + 1)] for i in range(n)),
                ver=bytes.fromhex(v[130:130 + 2 * int(v[66:130], 16)]).decode() if v and len(v) > 130 else "?", guard=bool(g and int(g, 16)))
rows = [(ch, role, a, account(ch, a)) for ch, d in G.items() if d for role, a in d.items() if a]
tvl = {}
try:
    ct = json.loads(curl("https://api.llama.fi/protocol/aave-v3") or "{}").get("currentChainTvls", {})
    tvl = {k: v for k, v in ct.items() if "-" not in k and k not in ("borrowed", "staking", "pool2")}
except Exception: pass
print(f"chains with a governance file: {sum(1 for d in G.values() if d)} of {len(RPC)}")
groups = collections.defaultdict(list)
for ch, role, a, s in rows:
    if role == "governance" and s["kind"] == "Safe": groups[tuple(s["owners"])].append(ch)
    print(f"  {ch:10s} {role:10s} {a[:10]}.. " + (f"Safe {s['thr']}-of-{s['n']} v{s['ver']} guard {'yes' if s['guard'] else 'no'}" if s["kind"] == "Safe" else s["kind"]))
for owners, chs in sorted(groups.items(), key=lambda kv: -len(kv[1])):
    w = sum(tvl.get(LLAMA_NAME.get(c, c), 0) for c in chs)
    print(f"\nthe Governance Guardian Safes with the same {len(owners)} signers: {len(chs)} chains {chs}; Aave V3 TVL on them ${w/1e9:.2f}B of ${sum(tvl.values())/1e9:.2f}B")
print("Safe addresses used for the Governance Guardian:", len({a for ch, role, a, s in rows if role == 'governance'}), "on", sum(1 for ch, role, a, s in rows if role == "governance"), "chains")
if ARGS.dump: json.dump(rows, open(ARGS.dump, "w")); print(f"\nwrote {ARGS.dump}")
