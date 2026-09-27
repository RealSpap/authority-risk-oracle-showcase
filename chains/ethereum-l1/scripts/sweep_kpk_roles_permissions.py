#!/usr/bin/env python3
"""Read-only pass on the kpk Zodiac Roles modules on Ethereum L1: for every kpk-curated Morpho and Euler Earn vault,
find the curator Safe, its enabled Zodiac Roles v2 module, check whether the module answers to the very Safe it can
act for (owner()==avatar()==target()), decode every role's complete authorized-function set from the module's own
event history, and flag any TEST_-named role that still has an active member. Nothing is sent, no key.

    python3 sweep_kpk_roles_permissions.py

Sources, all public and read-only:
- Morpho's GraphQL API (blue-api.morpho.org) for the vault list (an indexer, not trusted for values).
- Euler's own registry (github.com/euler-xyz/euler-interfaces, addresses/1/CoreAddresses.json) for the Earn factory,
  then the factory's own vault list on-chain.
- eth_call (owner/curator/getModulesPaginated/getThreshold/getOwners/eth_getCode) on a public RPC for every vault,
  Safe and module found: this is the primary source for the owner()/avatar()/target() governance-loop check.
- Blockscout's decoded per-address event-log endpoint for each Roles module (public RPC eth_getLogs needs a known
  block range per address+topic and public nodes throttle broad ranges; Blockscout already decodes with the verified
  "Roles" ABI, which is Zodiac Roles v2 -- bytes32 roleKey, AllowFunction/ScopeFunction/RevokeFunction/AllowTarget/
  ScopeTarget/RevokeTarget/AssignRoles events -- confirmed by reading the ABI itself, not assumed from memory).
- 4byte.directory to resolve function selectors this repo's own ABI fetch could not name.

ADDED 2026-09-27: also matches each module's clone-of implementation (already computed by clone_impl()) against
scripts/lib/safe_modules.py's KNOWN_MODULE_IMPLEMENTATION_ADVISORIES, and, for a module cloning a vulnerable one,
checks whether any of its ACTIVE members (across every role, not just TEST_ ones) is a CONTRACT -- the only
condition under which the June 2026 Zodiac Roles ERC-1271 flaw is actually exploitable (see that registry's
docstring). A plain-EOA-only membership is unaffected regardless of which implementation it clones.
"""
import json, os, time, sys
import requests
from web3 import Web3

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "scripts", "lib"))
from safe_modules import module_implementation_advisory  # noqa: E402

H = {"user-agent": "Mozilla/5.0"}
RPCS = ["https://ethereum.publicnode.com", "https://ethereum-rpc.publicnode.com", "https://eth.drpc.org"]
sel = lambda s: "0x" + Web3.keccak(text=s)[:4].hex()


def rpc(m, p, tries=3):
    for _ in range(tries):
        for u in RPCS:
            try:
                r = requests.post(u, json={"jsonrpc": "2.0", "id": 1, "method": m, "params": p}, timeout=25, headers=H).json()
                if r.get("result") is not None:
                    return r["result"]
            except Exception:
                pass
        time.sleep(1)
    return None


def call(to, fn, args=""):
    return rpc("eth_call", [{"to": to, "data": sel(fn) + args}, "latest"])


def addr_call(to, fn):
    h = call(to, fn)
    return Web3.to_checksum_address("0x" + h[-40:]) if h and len(h) >= 66 else None


def gql(q):
    for _ in range(4):
        try:
            r = requests.post("https://blue-api.morpho.org/graphql", json={"query": q}, timeout=30, headers=H)
            d = r.json()
            if not d.get("errors"):
                return d["data"]
        except Exception:
            pass
        time.sleep(1)
    return None


def clone_impl(code):
    c = (code or "0x")[2:].lower()
    return Web3.to_checksum_address("0x" + c[20:60]) if c.startswith("363d3d373d3d3d363d73") and len(c) == 90 else None


def safe_owners(a):
    thr, own = call(a, "getThreshold()"), call(a, "getOwners()")
    if not thr or not own or len(own) < 130:
        return None, []
    h = own[2:]
    k = int(h[64:128], 16)
    return int(thr, 16), [Web3.to_checksum_address("0x" + h[128 + 64 * i + 24:128 + (i + 1) * 64]) for i in range(k)]


SENT = "0" * 24 + "0000000000000000000000000000000000000001"


def modules_of(a):
    h = call(a, "getModulesPaginated(address,uint256)", SENT + hex(20)[2:].zfill(64))
    if not h or len(h) < 2 + 64 * 3:
        return None
    h = h[2:]
    off = int(h[0:64], 16) * 2
    n = int(h[off:off + 64], 16)
    return [Web3.to_checksum_address("0x" + h[off + 64 + 64 * i + 24:off + 64 + (i + 1) * 64]) for i in range(n)]


# ---- 1. find every kpk-named vault on Ethereum mainnet (chain 1), Morpho V1 + V2 + Euler Earn ----
def find_kpk_vaults():
    v1 = (gql('{ vaults(first: 1000, where: { chainId_in: [1] }) { items { address name listed } } }') or {"vaults": {"items": []}})["vaults"]["items"]
    v2 = (gql('{ vaultV2s(first: 1000, where: { chainId_in: [1] }) { items { address name listed } } }') or {"vaultV2s": {"items": []}})["vaultV2s"]["items"]
    kpk_v1 = [v for v in v1 if "kpk" in (v["name"] or "").lower()]
    kpk_v2 = [v for v in v2 if "kpk" in (v["name"] or "").lower()]
    core = requests.get("https://raw.githubusercontent.com/euler-xyz/euler-interfaces/master/addresses/1/CoreAddresses.json", timeout=20, headers=H).json()
    fac = core["eulerEarnFactory"]
    n = int(call(fac, "getVaultListLength()"), 16)
    r = call(fac, "getVaultListSlice(uint256,uint256)", hex(0)[2:].zfill(64) + hex(n)[2:].zfill(64))
    h = r[2:]
    off = int(h[0:64], 16) * 2
    cnt = int(h[off:off + 64], 16)
    vaults = [Web3.to_checksum_address("0x" + h[off + 64 + 64 * i + 24:off + 64 + (i + 1) * 64]) for i in range(cnt)]

    def dec_str(hh):
        if not hh or len(hh) < 130:
            return None
        b = hh[2:]
        o = int(b[0:64], 16) * 2
        ln = int(b[o:o + 64], 16)
        return bytes.fromhex(b[o + 64:o + 64 + 2 * ln]).decode("utf-8", "replace")

    kpk_euler = []
    for v in vaults:
        nm = dec_str(call(v, "name()"))
        if nm and "kpk" in nm.lower():
            kpk_euler.append({"address": v, "name": nm})
    return kpk_v1, kpk_v2, kpk_euler


# ---- 2. resolve owner()/curator() for each vault, dedupe curator Safes ----
def resolve_curator_safes(kpk_v1, kpk_v2, kpk_euler):
    rows = []
    for v in kpk_v1:
        rows.append({"vault": v["address"], "name": v["name"], "family": "morpho-v1", "owner": addr_call(v["address"], "owner()"), "curator": addr_call(v["address"], "curator()")})
    for v in kpk_v2:
        rows.append({"vault": v["address"], "name": v["name"], "family": "morpho-v2", "owner": addr_call(v["address"], "owner()"), "curator": addr_call(v["address"], "curator()")})
    for v in kpk_euler:
        rows.append({"vault": v["address"], "name": v["name"], "family": "euler-earn", "owner": addr_call(v["address"], "owner()"), "curator": addr_call(v["address"], "curator()")})
    by_curator = {}
    for r in rows:
        c = r["curator"]
        if not c or int(c, 16) == 0:
            continue
        by_curator.setdefault(c, []).append(r)
    return rows, by_curator


# ---- 3. for each curator Safe: threshold/owners/modules, and for each module: owner/avatar/target loop check ----
def inspect_safes_and_modules(by_curator):
    out = {}
    for safe in sorted(by_curator):
        thr, owners = safe_owners(safe)
        mods = modules_of(safe)
        entry = {"threshold": thr, "n_owners": len(owners), "owners": owners, "vaults": [r["name"] for r in by_curator[safe]], "module": None}
        if mods:
            m = mods[0]  # every kpk curator Safe found here carries exactly one module
            code = rpc("eth_getCode", [m, "latest"])
            impl = clone_impl(code)
            mo, ma, mt = addr_call(m, "owner()"), addr_call(m, "avatar()"), addr_call(m, "target()")
            entry["module"] = {"address": m, "clone_of": impl, "owner": mo, "avatar": ma, "target": mt,
                                "governance_loop": (mo == safe and ma == safe and mt == safe)}
        out[safe] = entry
    return out


# ---- 4. decode each module's full event history into role -> {members, functions, targets} ----
def hex_to_ascii(h):
    b = bytes.fromhex(h[2:]).rstrip(b"\x00")
    try:
        s = b.decode("ascii")
        return s if s and all(32 <= ord(c) < 127 for c in s) else h
    except Exception:
        return h


def all_logs(addr):
    out, params = [], {}
    while True:
        d = None
        for _ in range(4):
            try:
                d = requests.get(f"https://eth.blockscout.com/api/v2/addresses/{addr}/logs", params=params, timeout=30, headers=H).json()
                break
            except Exception:
                time.sleep(1)
        if not d:
            break
        out += d.get("items", [])
        nxt = d.get("next_page_params")
        if not nxt:
            break
        params = nxt
    return out


def decode_module(module_addr):
    logs = sorted(all_logs(module_addr), key=lambda it: it.get("block_number", 0))
    roles = {}
    for it in logs:
        dec = it.get("decoded")
        if not dec:
            continue
        name = dec["method_call"].split("(")[0]
        p = {x["name"]: x["value"] for x in dec["parameters"]}
        if name == "AssignRoles":
            for rk, mo in zip(p["roleKeys"], p["memberOf"]):
                rk_a = hex_to_ascii(rk)
                roles.setdefault(rk_a, {"members": {}, "functions": {}, "targets": {}})
                roles[rk_a]["members"][p["module"]] = mo in (True, "true", "True")
        elif name in ("AllowFunction", "ScopeFunction", "RevokeFunction"):
            rk_a = hex_to_ascii(p["roleKey"])
            roles.setdefault(rk_a, {"members": {}, "functions": {}, "targets": {}})
            key = f"{p['targetAddress']}:{p['selector']}"
            if name == "AllowFunction":
                roles[rk_a]["functions"][key] = "allowed"
            elif name == "RevokeFunction":
                roles[rk_a]["functions"][key] = "revoked"
            else:
                roles[rk_a]["functions"][key] = f"scoped({len(p.get('conditions') or [])} conditions)"
        elif name in ("AllowTarget", "ScopeTarget", "RevokeTarget"):
            rk_a = hex_to_ascii(p["roleKey"])
            roles.setdefault(rk_a, {"members": {}, "functions": {}, "targets": {}})
            roles[rk_a]["targets"][p["targetAddress"]] = {"AllowTarget": "allowed (ANY function on this target)", "ScopeTarget": "scoped (per-function only)", "RevokeTarget": "revoked"}[name]
    return roles, len(logs)


abi_cache = {}


def selector_name(target, selector):
    if target not in abi_cache:
        m = {}
        try:
            d = requests.get(f"https://eth.blockscout.com/api/v2/smart-contracts/{target}", timeout=20, headers=H).json()
            for e in d.get("abi") or []:
                if e.get("type") == "function":
                    sig = e["name"] + "(" + ",".join(i["type"] for i in e.get("inputs", [])) + ")"
                    m[sel(sig)] = sig
        except Exception:
            pass
        abi_cache[target] = m
    if selector in abi_cache[target]:
        return abi_cache[target][selector]
    try:
        r = requests.get("https://www.4byte.directory/api/v1/signatures/", params={"hex_signature": selector}, timeout=15, headers=H).json()
        res = r.get("results") or []
        if res:
            return res[0]["text_signature"]
    except Exception:
        pass
    return selector


def main():
    print("=== 1. kpk vaults on Ethereum mainnet ===")
    kpk_v1, kpk_v2, kpk_euler = find_kpk_vaults()
    print(f"Morpho V1: {len(kpk_v1)}  Morpho V2: {len(kpk_v2)}  Euler Earn: {len(kpk_euler)}")

    print("\n=== 2. curator Safes ===")
    rows, by_curator = resolve_curator_safes(kpk_v1, kpk_v2, kpk_euler)
    print(f"{len(by_curator)} distinct curator addresses across {len(rows)} kpk vaults")

    print("\n=== 3. Safe config + module governance-loop check ===")
    safes = inspect_safes_and_modules(by_curator)
    with_module = {s: e for s, e in safes.items() if e["module"]}
    print(f"{len(with_module)} of {len(safes)} curator Safes carry a Zodiac Roles module")
    for s, e in with_module.items():
        loop = e["module"]["governance_loop"]
        print(f"  {s}  {e['threshold']}-of-{e['n_owners']}  module {e['module']['address']}  owner()==avatar()==target()==safe? {loop}")

    print("\n=== 4. full role/permission decode per module ===")
    report = []
    test_roles_active = []
    vuln_module_findings = []
    for safe, e in with_module.items():
        mod = e["module"]["address"]
        roles, n_logs = decode_module(mod)
        print(f"\n--- {e['vaults']}  safe {safe}  module {mod} ({n_logs} events) ---")
        role_report = {}
        module_active_members = set()
        for rk, info in roles.items():
            active = [a for a, m in info["members"].items() if m]
            removed = [a for a, m in info["members"].items() if not m]
            module_active_members.update(active)
            fn_named = {}
            for key, status in info["functions"].items():
                target, s = key.split(":")
                fn_named[f"{selector_name(target, s)} on {target}"] = status
            print(f"  ROLE {rk}: active members {active}" + (f" (removed: {removed})" if removed else ""))
            for fn, status in fn_named.items():
                print(f"      {fn:55s} -> {status}")
            for t, status in info["targets"].items():
                print(f"      [target] {t} -> {status}")
            role_report[rk] = {"active_members": active, "removed_members": removed, "functions": fn_named, "targets": info["targets"]}
            if rk.startswith("TEST_") and active:
                test_roles_active.append({"safe": safe, "vault_names": e["vaults"], "module": mod, "role": rk, "active_members": active, "functions": fn_named, "targets": info["targets"]})
        advisory = module_implementation_advisory(e["module"]["clone_of"])
        if advisory and advisory["status"] == "vulnerable":
            contract_members = [a for a in sorted(module_active_members) if (rpc("eth_getCode", [a, "latest"]) or "0x") != "0x"]
            vuln_module_findings.append({"safe": safe, "vault_names": e["vaults"], "module": mod, "clone_of": e["module"]["clone_of"],
                                          "advisory": advisory["name"], "active_members": sorted(module_active_members),
                                          "contract_members": contract_members, "exploitable_today": bool(contract_members)})
        report.append({"safe": safe, "vaults": e["vaults"], "module": mod, "threshold": e["threshold"], "governance_loop": e["module"]["governance_loop"], "roles": role_report})

    print("\n=== 5. TEST_-named roles with an active member ===")
    if test_roles_active:
        for t in test_roles_active:
            print(json.dumps(t, indent=2))
    else:
        print("none found")

    print("\n=== 6. modules cloning a known-vulnerable implementation (scripts/lib/safe_modules.py) ===")
    if vuln_module_findings:
        for v in vuln_module_findings:
            live = "EXPLOITABLE CONDITION HOLDS (a contract is an active member)" if v["exploitable_today"] else \
                "condition does not hold today: every active member is a plain EOA, unaffected regardless of the implementation"
            print(f"  {v['vault_names']}  safe {v['safe']}  module {v['module']}  clones {v['advisory']} ({v['clone_of']})")
            print(f"    {live}" + (f" -- contract member(s): {v['contract_members']}" if v["contract_members"] else ""))
    else:
        print("none found")

    json.dump({"safes": {s: {"threshold": e["threshold"], "owners": e["owners"], "vaults": e["vaults"], "module": e["module"]} for s, e in safes.items()},
               "report": report, "test_roles_active": test_roles_active, "vuln_module_findings": vuln_module_findings},
              open("kpk_roles_final_report.json", "w"), indent=2)
    print("\nwrote kpk_roles_final_report.json")


if __name__ == "__main__":
    main()
