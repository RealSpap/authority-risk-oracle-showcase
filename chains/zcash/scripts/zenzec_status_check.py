#!/usr/bin/env python3
"""Read-only status check for Zenrock zenZEC (Zcash target 7). Public data only: no key, no write.

Prints the facts recorded in chains/zcash/data/zenzec_status_2026-09-20.md (the Solana authority chain of
the zenZEC mint, the program's deployment slot, the mint's latest non-price activity, the ZEC backing
address balance, the zrchain tip) and reports every TRIGGER that differs from that baseline: each one is a
reason to re-read the status note and, if warranted, revisit whether the flag on target 7 still holds.

Usage (from chains/zcash/scripts):  python3 zenzec_status_check.py
Exit 0 = no trigger fired, 1 = at least one trigger fired, 2 = a read failed (inconclusive).
"""
import datetime
import json
import os
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

SOLANA_RPCS = ("https://api.mainnet-beta.solana.com", "https://solana-rpc.publicnode.com")
ZRCHAIN_RPC = "https://rpc.diamond.zenrocklabs.io"
ZEC_HOSTS = ("zec.rocks:443", "eu.zec.rocks:443")

MINT = "JDt9rRGaieF6aN1cJkXFeUmsy7ZE4yY3CZb8tVMXVroS"
BASELINE = {
    "supply_raw": "49451437135",                                            # 494.51437135, 8 decimals
    "mint_authority": "6kgpWRR277ZeibFzgEVVXaYz2AztVTD5bCbVEiFq13Mk",
    "freeze_authority": None,
    "multisig": (1, 1),                                                     # (required, valid signers)
    "signer": "8y1Zmkj4uJhU9ykuK7hXgTar1YeoDASX2CnhpD8EsJ7s",
    "program": "BTzxmuLgNUfBeNCFxsoSVpEKjRTma75eWcaPjyDCUF88",
    "upgrade_authority": "2RoRSPwFmMcFDd3DLgoomMRFkhUSaVNSDo7XyH2tw6de",
    "deploy_slot": 383091028,                                               # 2025-11-28 12:53 UTC
    # The look-alike test program of 2026-08-05/06 referenced the mint authority account; nothing later should.
    "quiet_after_utc": "2026-08-06T15:00:00Z",
    "backing_address": "t1g7BWsvsqfiYb2j1ManbK6gKhmYjXLAFn4",
    "backing_zat": 49873980102,
    "zrchain_height": 9534552,
}


def solana_rpc(method, params, rpcs=SOLANA_RPCS, tries=5):
    last = None
    for base in rpcs:
        for i in range(tries):
            try:
                req = urllib.request.Request(
                    base, data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode(),
                    headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"})
                d = json.load(urllib.request.urlopen(req, timeout=40))
                if "error" in d:
                    raise RuntimeError(str(d["error"])[:120])
                return d["result"]
            except Exception as e:
                last = e
                time.sleep(4 + 4 * i if "429" in str(e) else 1)
    raise RuntimeError(f"{method} failed on every provider: {last}")


def utc(ts):
    return datetime.datetime.fromtimestamp(ts, datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_solana(rpc=solana_rpc):
    out = {}
    mint = rpc("getAccountInfo", [MINT, {"encoding": "jsonParsed"}])["value"]["data"]["parsed"]["info"]
    out["supply_raw"], out["mint_authority"], out["freeze_authority"] = mint["supply"], mint.get("mintAuthority"), mint.get("freezeAuthority")
    ms = rpc("getAccountInfo", [out["mint_authority"], {"encoding": "jsonParsed"}])["value"]["data"]["parsed"]
    if ms.get("type") == "multisig":
        info = ms["info"]
        out["multisig"] = (info["numRequiredSigners"], info["numValidSigners"])
        out["signer"] = (info.get("signers") or [None])[0]
    else:
        out["multisig"], out["signer"] = None, None
    if out["signer"]:
        out["program"] = rpc("getAccountInfo", [out["signer"], {"encoding": "base64"}])["value"]["owner"]
        pa = rpc("getAccountInfo", [out["program"], {"encoding": "jsonParsed"}])["value"]
        pdata = pa["data"]["parsed"]["info"].get("programData") if pa["data"].get("parsed") else None
        if pdata:
            pd = rpc("getAccountInfo", [pdata, {"encoding": "jsonParsed"}])["value"]["data"]["parsed"]["info"]
            out["upgrade_authority"], out["deploy_slot"] = pd.get("authority"), pd["slot"]
    sigs = rpc("getSignaturesForAddress", [out["mint_authority"], {"limit": 1}])
    out["last_multisig_activity"] = utc(sigs[0]["blockTime"]) if sigs and sigs[0].get("blockTime") else None
    if out.get("upgrade_authority"):
        s2 = rpc("getSignaturesForAddress", [out["upgrade_authority"], {"limit": 1}])
        out["upgrade_key_latest_tx"] = utc(s2[0]["blockTime"]) if s2 and s2[0].get("blockTime") else None
    return out


def read_backing(hosts=ZEC_HOSTS):
    import zcash_read as zr
    vals = []
    for h in hosts:
        try:
            vals.append(zr.taddr_balance(h, BASELINE["backing_address"]))
        except Exception:
            pass
    return vals


def read_zrchain(url=ZRCHAIN_RPC):
    try:
        d = json.load(urllib.request.urlopen(urllib.request.Request(url + "/status", headers={"User-Agent": "Mozilla/5.0"}), timeout=20))
        si = d.get("result", d)["sync_info"]
        return int(si["latest_block_height"]), si["latest_block_time"]
    except Exception:
        return None, None


def triggers(sol, backing, zr_height, baseline=BASELINE):
    fired = []
    for k in ("supply_raw", "mint_authority", "freeze_authority", "multisig", "signer", "program", "upgrade_authority", "deploy_slot"):
        if sol.get(k) != baseline[k]:
            fired.append(f"{k} changed: baseline {baseline[k]!r}, now {sol.get(k)!r}")
    last = sol.get("last_multisig_activity")
    if last and last > baseline["quiet_after_utc"]:
        fired.append(f"the mint authority account appears in a transaction at {last}, after {baseline['quiet_after_utc']}")
    if len(set(backing)) > 1:
        fired.append(f"the ZEC hosts disagree on the backing balance: {backing}")
    elif backing and backing[0] != baseline["backing_zat"]:
        fired.append(f"backing address balance changed: baseline {baseline['backing_zat']} zat, now {backing[0]} zat")
    if zr_height is not None and zr_height > baseline["zrchain_height"]:
        fired.append(f"zrchain tip advanced: baseline {baseline['zrchain_height']}, now {zr_height}")
    return fired


def main():
    try:
        sol = read_solana()
    except Exception as e:
        print("INCONCLUSIVE: Solana reads failed:", e)
        return 2
    backing = read_backing()
    height, btime = read_zrchain()
    print(f"zenZEC supply (raw, 8 decimals): {sol['supply_raw']}  freeze authority: {sol['freeze_authority']}")
    print(f"mint authority {sol['mint_authority']}  multisig (required, valid): {sol['multisig']}  signer: {sol['signer']}")
    print(f"signer owned by program {sol.get('program')}  upgrade authority {sol.get('upgrade_authority')}  deployment slot {sol.get('deploy_slot')}")
    print(f"upgrade key latest transaction: {sol.get('upgrade_key_latest_tx')}  |  mint authority account latest transaction: {sol.get('last_multisig_activity')}")
    print(f"backing address {BASELINE['backing_address']} balance (zat) per host {ZEC_HOSTS}: {backing}")
    print(f"zrchain tip at {ZRCHAIN_RPC}: height {height}, block time {btime}")
    fired = triggers(sol, backing, height)
    if not backing:
        print("INCONCLUSIVE: no ZEC host answered")
        return 2
    for f in fired:
        print("TRIGGER FIRED:", f)
    print("RESULT", "triggers fired: re-read chains/zcash/data/zenzec_status_2026-09-20.md" if fired else "no trigger fired: baseline of 2026-09-20 still holds")
    return 1 if fired else 0


if __name__ == "__main__":
    sys.exit(main())
