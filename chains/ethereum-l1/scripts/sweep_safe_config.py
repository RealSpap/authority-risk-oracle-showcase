#!/usr/bin/env python3
"""Read-only look at what a Safe's "t-of-n" does not say, for every listed owner or curator Safe found by the vault sweeps.
    python3 chains/ethereum-l1/scripts/sweep_safe_config.py morpho_rows.json euler_rows.json [--dump safes.json]
For each distinct (chain, Safe): version, enabled modules (a module can move funds or change owners without the threshold),
the guard (a contract that can veto or force a check on every transaction), the fallback handler and the nonce (how many
transactions the Safe has ever executed: 0 means never used). A module that is an EIP-1167 clone is resolved to its
implementation so the same module code can be counted across Safes. Nothing is sent, no key. Inputs are the row dumps of
sweep_morpho_vault_owners.py --dump and sweep_euler_earn.py --dump; deposits are counted once per Safe address whatever the role."""
import argparse, collections, json, subprocess, sys, time, urllib.request
from concurrent.futures import ThreadPoolExecutor
from web3 import Web3
RPC = {1: ["https://ethereum-rpc.publicnode.com", "https://eth.drpc.org"], 8453: ["https://base-rpc.publicnode.com", "https://base.drpc.org"],
       4663: ["https://rpc.mainnet.chain.robinhood.com"], 143: ["https://rpc.monad.xyz"], 42161: ["https://arb1.arbitrum.io/rpc", "https://arbitrum-one-rpc.publicnode.com"],
       999: ["https://rpc.hyperliquid.xyz/evm"], 4217: ["https://rpc.tempo.xyz"], 988: ["https://rpc.stable.xyz"], 10: ["https://mainnet.optimism.io", "https://optimism-rpc.publicnode.com"],
       137: ["https://polygon-bor-rpc.publicnode.com"], 130: ["https://mainnet.unichain.org"], 747474: ["https://rpc.katana.network"],
       9745: ["https://rpc.plasma.to"], 56: ["https://bsc-rpc.publicnode.com"], 43114: ["https://api.avax.network/ext/bc/C/rpc"]}
ap = argparse.ArgumentParser(); ap.add_argument("rows", nargs="+"); ap.add_argument("--dump", default=None); ARGS = ap.parse_args()
def post(url, body):
    try:
        req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"content-type": "application/json", "user-agent": "Mozilla/5.0"})
        return json.load(urllib.request.urlopen(req, timeout=40))
    except Exception:
        try:   # this Python's TLS library cannot reach some hosts (rpc.katana.network): curl can
            o = subprocess.run(["curl", "-s", "-m", "40", "-X", "POST", "-H", "content-type: application/json", "-A", "Mozilla/5.0", "--data", json.dumps(body), url], capture_output=True, text=True, timeout=60)
            return json.loads(o.stdout) if o.returncode == 0 and o.stdout.strip() else None
        except Exception:
            return None
def rpc(ch, m, p):
    for a in range(3):
        for url in RPC[ch]:
            r = post(url, {"jsonrpc": "2.0", "id": 1, "method": m, "params": p})
            if r and r.get("result") is not None: return r["result"]
        time.sleep(0.8 * (a + 1))
sel = lambda s: "0x" + bytes(Web3.keccak(text=s))[:4].hex()
slot = lambda s: "0x" + bytes(Web3.keccak(text=s)).hex()
GUARD, FALLBACK = slot("guard_manager.guard.address"), slot("fallback_manager.handler.address")
ZERO = "0x" + "0" * 40; SENT = "0" * 24 + "0000000000000000000000000000000000000001"
call = lambda ch, to, data: rpc(ch, "eth_call", [{"to": to, "data": data}, "latest"])
addr = lambda h: Web3.to_checksum_address("0x" + h[-40:])
def decode_string(h):
    if not h or len(h) < 130: return None
    n = int(h[66:130], 16); return bytes.fromhex(h[130:130 + 2 * n]).decode("utf-8", "replace")
def modules(ch, a):
    h = call(ch, a, sel("getModulesPaginated(address,uint256)") + SENT + hex(20)[2:].zfill(64))
    if not h or len(h) < 2 + 64 * 3: return None
    h = h[2:]; off = int(h[0:64], 16) * 2; n = int(h[off:off + 64], 16)
    return [addr(h[off + 64 + 64 * i: off + 64 + 64 * (i + 1)]) for i in range(n)]
def clone_impl(code):   # EIP-1167 minimal proxy: 363d3d373d3d3d363d73 <20 bytes> 5af43d82803e903d91602b57fd5bf3
    c = code[2:].lower()
    return addr(c[20:60]) if c.startswith("363d3d373d3d3d363d73") and len(c) == 90 else None
def module_info(ch, m):
    code = rpc(ch, "eth_getCode", [m, "latest"]) or "0x"
    cd = call(ch, m, sel("txCooldown()"))   # Zodiac Delay module answers this
    return {"module": m, "code_bytes": (len(code) - 2) // 2, "clone_of": clone_impl(code), "delay_cooldown_s": int(cd, 16) if cd and cd != "0x" else None}
def read(key):
    ch, a = key
    ver = decode_string(call(ch, a, sel("VERSION()")))
    mods = modules(ch, a)
    g = rpc(ch, "eth_getStorageAt", [a, GUARD, "latest"]); f = rpc(ch, "eth_getStorageAt", [a, FALLBACK, "latest"])
    nonce = call(ch, a, sel("nonce()"))
    guard = addr(g) if g and int(g, 16) else None; fb = addr(f) if f and int(f, 16) else None
    return {"chain": ch, "safe": a, "version": ver, "modules": None if mods is None else [module_info(ch, m) for m in mods],
            "guard": guard, "fallback": fb, "nonce": int(nonce, 16) if nonce and nonce != "0x" else None}
rows = []
for f in ARGS.rows: rows += json.load(open(f))
safes = {}
for r in rows:
    if r.get("listed") is False: continue
    for role in ("owner", "curator"):
        a, k = r.get(role), (r.get(role + "_kind") or "")
        if a and (k.startswith("Safe") or k.startswith("1-of-1 Safe")) and r["chain"] in RPC:
            s = safes.setdefault((r["chain"], Web3.to_checksum_address(a)), {"usd": 0.0, "roles": set(), "kind": k, "names": set()})
            s["usd"] += r["usd"]; s["roles"].add(role)
            if r.get("name"): s["names"].add(r["name"].split(" ")[0])
with ThreadPoolExecutor(6) as ex: res = list(ex.map(read, safes))
for r in res: r.update(usd=safes[(r["chain"], r["safe"])]["usd"], roles=sorted(safes[(r["chain"], r["safe"])]["roles"]), kind=safes[(r["chain"], r["safe"])]["kind"], names=sorted(safes[(r["chain"], r["safe"])]["names"])[:3])
tot = sum(r["usd"] for r in res)
unread = [r for r in res if r["modules"] is None]
mod = [r for r in res if r["modules"]]; grd = [r for r in res if r["guard"]]; fbh = collections.Counter(r["fallback"] for r in res)
usd = lambda rs: sum(r["usd"] for r in rs)
print(f"{len(res)} distinct listed owner/curator Safes on {len({r['chain'] for r in res})} chains, ${tot/1e9:.2f}B of deposits (a vault counts once per Safe address)")
print(f"module list unread: {len(unread)} | with at least one module: {len(mod)} (${usd(mod)/1e6:.0f}M) | with a guard: {len(grd)} (${usd(grd)/1e6:.0f}M) | nonce 0 (never used): {sum(1 for r in res if r['nonce'] == 0)}")
print("versions:", dict(collections.Counter(r["version"] for r in res).most_common(8)))
print("fallback handlers:", dict(collections.Counter(r["fallback"] for r in res).most_common(4)))
nz = sorted(r["nonce"] for r in res if r["nonce"] is not None)
if nz: print(f"nonce (transactions ever executed): min {nz[0]}, median {nz[len(nz)//2]}, max {nz[-1]}; under 20: {sum(1 for n in nz if n < 20)} Safes")
impls = collections.Counter(); delays = []
for r in mod:
    for m in r["modules"]:
        impls[m["clone_of"] or m["module"]] += 1
        if m["delay_cooldown_s"] is not None: delays.append((r, m))
print("\nmodules by implementation (or address when not a clone):", dict(impls.most_common(8)))
print(f"modules that answer txCooldown() (Zodiac Delay style): {len(delays)}")
print("\nSafes with a module or a guard, by deposits:")
for r in sorted(mod + [g for g in grd if g not in mod], key=lambda r: -r["usd"])[:14]:
    ms = ", ".join((m["clone_of"] or m["module"])[:10] + ("+delay %ds" % m["delay_cooldown_s"] if m["delay_cooldown_s"] is not None else "") for m in (r["modules"] or []))
    print(f"  {r['chain']:>6} ${r['usd']/1e6:7.1f}M {r['safe'][:10]}.. {r['kind']:26s} {'/'.join(r['roles']):13s} modules [{ms}] guard {r['guard'][:10] + '..' if r['guard'] else '-'} {r['names']}")
if ARGS.dump: json.dump(res, open(ARGS.dump, "w")); print(f"\nwrote {len(res)} Safes to {ARGS.dump}")
