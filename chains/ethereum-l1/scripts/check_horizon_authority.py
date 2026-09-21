#!/usr/bin/env python3
"""
Read-only re-derivation of every on-chain fact behind score_aave_v3_horizon_pool() (Aave V3 Horizon on
Ethereum). Prints one line per check, `OK ...` or `FAIL ...`, and exits 1 if any check fails. It sends no
transaction and needs no key. Reads go to two public RPCs; the role history and the verified source come from
the Blockscout API (the public RPCs refuse eth_getLogs).

    python3 chains/ethereum-l1/scripts/check_horizon_authority.py

Checks: (1) root, (2) role holders by hasRole on both RPCs, (3) role admins, (4) the two Safes,
(5) the role history replayed from the 16 events equals the hasRole reading, (6) no signer overlap with the two
Aave committees this repo already tracks, (7) what POOL_ADMIN can do, from the verified PoolConfigurator source,
(8) the same access rule confirmed by eth_call simulations from each holder (nothing is sent).
"""
import importlib.util
import json
import os
import re
import subprocess
import sys
import time
import urllib.request

from web3 import Web3

RPCS = ["https://ethereum-rpc.publicnode.com", "https://eth.drpc.org"]
BLOCKSCOUT = "https://eth.blockscout.com/api/v2"
PROVIDER = "0x5D39E06b825C1F2B80bf2756a73e28eFAA128ba0"
ACL = "0xEFD5df7b87d2dCe6DD454b4240b3e0A4db562321"
CONFIGURATOR_IMPL = "0x898E245D83Ad255Dc57b04978D0b4A12b94a557F"
EXECUTOR = "0x5300A1a15135EA4dc7aD5a167152C01EFc9b192A"
ADMIN_SAFE = "0x13B57382c36BAB566E75C72303622AF29E27e1d3"
RISK_SAFE = "0xE6ec1f0Ae6Cd023bd0a9B4d0253BDC755103253c"
RISK_LISTING_CONTRACT = "0x09e8E1408a68778CEDdC1938729Ea126710E7Dda"
GHO_DIRECT_MINTER = "0xe10C78A3AC7f016eD2DE1A89c5479b1039EAB9eA"
RWA_ATOKEN_MANAGER = "0x803e5Db3E26e88AD0a682A46c3E04cdd053D0EB9"
DEPLOYER = "0x3eAF4e16Fa85F6ba6F7795390e191E7365C1d51e"
RWA_ROLE = "0x1bcbc82ace14413a2df9613295a6bb0971037c9194435dfa4ffdd82ff5736c43"  # name not identified

ROLE = {n: "0x" + bytes(Web3.keccak(text=n)).hex() for n in ("POOL_ADMIN", "EMERGENCY_ADMIN", "RISK_ADMIN", "ASSET_LISTING_ADMIN")}
ROLE["DEFAULT_ADMIN"] = "0x" + "00" * 32
NAME = {v: k for k, v in ROLE.items()}
NAME[RWA_ROLE] = "RWA_ROLE"
failures = []


def report(ok, text):
    print(("OK   " if ok else "FAIL ") + text)
    if not ok:
        failures.append(text)


def _post(url, method, params):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, data=body, headers={"content-type": "application/json", "user-agent": "Mozilla/5.0"})
            return json.load(urllib.request.urlopen(req, timeout=40))
        except Exception:
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"{url} unreachable for {method}")


def call(url, to, data):
    r = _post(url, "eth_call", [{"to": to, "data": data}, "latest"])
    return r.get("result") if "result" in r else None


def both(to, data):
    return [call(u, to, data) for u in RPCS]


def word(addr):
    return "0" * 24 + addr[2:].lower()


def addr_of(h):
    return Web3.to_checksum_address("0x" + h[-40:])


def has_role(role, holder):
    vals = both(ACL, "0x91d14854" + role[2:] + word(holder))
    return None if None in vals else (int(vals[0], 16) if vals[0] == vals[1] else None)


def get_json(url):
    """Blockscout, first with urllib, then with curl (urllib alone was seen to drop a chunked reply mid-body)."""
    for attempt in range(3):
        try:
            return json.load(urllib.request.urlopen(urllib.request.Request(url, headers={"user-agent": "Mozilla/5.0"}), timeout=60))
        except Exception:
            pass
        try:
            out = subprocess.run(["curl", "-s", "-m", "60", "-A", "Mozilla/5.0", url], capture_output=True, text=True, timeout=90)
            if out.returncode == 0 and out.stdout.strip():
                return json.loads(out.stdout)
        except Exception:
            pass
        time.sleep(2 * (attempt + 1))
    return None


def safe_config(addr):
    thr = both(addr, "0xe75235b8")
    own = both(addr, "0xa0e67e2b")
    mods = both(addr, "0xcc2f8452" + "0" * 63 + "1" + "0" * 62 + "0a")
    ver = both(addr, "0xffa1ad74")
    if None in thr + own + mods + ver or thr[0] != thr[1] or own[0] != own[1] or mods[0] != mods[1]:
        return None
    h = own[0][2:]
    n = int(h[64:128], 16)
    owners = ["0x" + h[128 + 64 * i + 24: 128 + 64 * (i + 1)] for i in range(n)]
    n_mods = int(mods[0][2:][128:192], 16)
    version = bytes.fromhex(ver[0][2:])[64:].rstrip(b"\0").decode(errors="ignore")
    return int(thr[0], 16), owners, n_mods, version


# 1. root
for fn, sel in (("owner()", "0x8da5cb5b"), ("getACLAdmin()", "0x0e67178c")):
    vals = both(PROVIDER, sel)
    report(None not in vals and vals[0] == vals[1] and addr_of(vals[0]) == EXECUTOR, f"provider {fn} = governance Executor {EXECUTOR} on both RPCs ({vals[0] and addr_of(vals[0])})")

# 2. role holders (hasRole, both RPCs)
expected = {
    "DEFAULT_ADMIN": {EXECUTOR: 1, ADMIN_SAFE: 0, RISK_SAFE: 0, DEPLOYER: 0},
    "POOL_ADMIN": {EXECUTOR: 1, ADMIN_SAFE: 1, RISK_SAFE: 0, RISK_LISTING_CONTRACT: 0, DEPLOYER: 0},
    "EMERGENCY_ADMIN": {EXECUTOR: 1, ADMIN_SAFE: 1, RISK_SAFE: 0, RISK_LISTING_CONTRACT: 0},
    "RISK_ADMIN": {RISK_SAFE: 1, RISK_LISTING_CONTRACT: 1, GHO_DIRECT_MINTER: 1, ADMIN_SAFE: 0, EXECUTOR: 0},
    "ASSET_LISTING_ADMIN": {RISK_LISTING_CONTRACT: 1, ADMIN_SAFE: 0},
}
for role, holders in expected.items():
    bad = [(h, want, has_role(ROLE[role], h)) for h, want in holders.items() if has_role(ROLE[role], h) != want]
    report(not bad, f"hasRole({role}) matches the expected holder table on both RPCs ({len(holders)} addresses checked)" + (f" MISMATCH {bad}" if bad else ""))
report(has_role(RWA_ROLE, RWA_ATOKEN_MANAGER) == 1, f"role {RWA_ROLE[:12]}... is held by the RWA aToken manager {RWA_ATOKEN_MANAGER}")

# 3. role admins: every role is administered by DEFAULT_ADMIN, so only the Executor can change a holder
for role in ("POOL_ADMIN", "EMERGENCY_ADMIN", "RISK_ADMIN", "ASSET_LISTING_ADMIN"):
    vals = both(ACL, "0x248a9ca3" + ROLE[role][2:])
    report(None not in vals and vals[0] == vals[1] and int(vals[0], 16) == 0, f"getRoleAdmin({role}) = DEFAULT_ADMIN on both RPCs")

# 4. the two Safes
admin = safe_config(ADMIN_SAFE)
risk = safe_config(RISK_SAFE)
report(bool(admin) and admin[0] == 4 and len(admin[1]) == 6, f"admin Safe {ADMIN_SAFE} is 4-of-6" + (f" (read {admin[0]}-of-{len(admin[1])})" if admin else " (unread)"))
report(bool(risk) and risk[0] == 3 and len(risk[1]) == 4, f"risk Safe {RISK_SAFE} is 3-of-4" + (f" (read {risk[0]}-of-{len(risk[1])})" if risk else " (unread)"))
report(bool(admin) and bool(risk) and admin[2] == 0 and risk[2] == 0, "neither Safe has a module enabled (no delay module)")
report(bool(admin) and bool(risk) and admin[3] == "1.4.1" and risk[3] == "1.4.1", "both Safes are Safe v1.4.1")
shared = sorted({o.lower() for o in admin[1]} & {o.lower() for o in risk[1]}) if admin and risk else []
report(len(shared) == 3, f"the two Safes share 3 signers: {shared}")
code = [_post(RPCS[0], "eth_getCode", [a, "latest"])["result"] for a in (RISK_LISTING_CONTRACT,)]
report(len(code[0]) > 4 and safe_config(RISK_LISTING_CONTRACT) is None, f"{RISK_LISTING_CONTRACT} is a contract and not a Safe ({(len(code[0]) - 2) // 2} bytes)")

# 5. the role history replayed from the events equals the hasRole reading (independent of the eth_call path)
events, page = [], ""
while True:
    d = get_json(f"{BLOCKSCOUT}/addresses/{ACL}/logs{page}")
    if d is None:
        report(False, "Blockscout role history unreachable after retries (run again; not a finding about Horizon)")
        break
    events += d.get("items", [])
    nxt = d.get("next_page_params")
    if not nxt:
        break
    page = "?" + "&".join(f"{k}={v}" for k, v in nxt.items())
held = {}
for ev in sorted(events, key=lambda e: (e["block_number"], e["index"])):
    dec = ev.get("decoded") or {}
    p = {x["name"]: x["value"] for x in dec.get("parameters", [])}
    if not p:
        continue
    key = (p["role"], Web3.to_checksum_address(p["account"]))
    if dec["method_call"].startswith("RoleGranted"):
        held[key] = True
    elif dec["method_call"].startswith("RoleRevoked"):
        held.pop(key, None)
by_role = {}
for (role, acct) in held:
    by_role.setdefault(NAME.get(role, role[:12]), set()).add(acct)
want = {"DEFAULT_ADMIN": {EXECUTOR}, "POOL_ADMIN": {EXECUTOR, ADMIN_SAFE}, "EMERGENCY_ADMIN": {EXECUTOR, ADMIN_SAFE},
        "RISK_ADMIN": {RISK_SAFE, RISK_LISTING_CONTRACT, GHO_DIRECT_MINTER}, "ASSET_LISTING_ADMIN": {RISK_LISTING_CONTRACT}, "RWA_ROLE": {RWA_ATOKEN_MANAGER}}
report(len(events) == 16, f"the ACLManager emitted 16 role events (read {len(events)})")
report(by_role == want, f"replaying RoleGranted/RoleRevoked gives exactly the holder table above ({ {k: len(v) for k, v in sorted(by_role.items())} })")

# 6. no overlap with the two Aave committees already tracked in this repo
here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(here, "..", "..", "..", "scripts", "lib"))
spec = importlib.util.spec_from_file_location("l1_scorers", os.path.join(here, "..", "scorers.py"))
l1 = importlib.util.module_from_spec(spec)
sys.modules["l1_scorers"] = l1
spec.loader.exec_module(l1)
known = set(l1._KNOWN_AAVE_GUARDIAN_OWNERS_2026_09_17) | set(l1._KNOWN_AAVE_PROTOCOL_GUARDIAN_OWNERS_2026_09_20)
horizon_signers = {o.lower() for o in (admin[1] if admin else [])} | {o.lower() for o in (risk[1] if risk else [])}
report(len(known) == 16 and len(horizon_signers) == 7 and not (horizon_signers & known), f"none of the 7 Horizon signers is in the 9-signer or the 7-signer Aave committee tracked here ({len(known)} known addresses)")

# 7. what POOL_ADMIN can do, from the verified PoolConfigurator source
src_json = get_json(f"{BLOCKSCOUT}/smart-contracts/{CONFIGURATOR_IMPL}") or {}
if not src_json:
    report(False, "Blockscout verified source unreachable after retries (run again; not a finding about Horizon)")
src = (src_json.get("source_code") or "") + "".join("\n" + f.get("source_code", "") for f in src_json.get("additional_sources", []))
pool_admin_fns = sorted({name for name, _, tail in re.findall(r"function\s+(\w+)\s*\(([^)]*)\)\s*(?:external|public)([^{;]*)\{", src) if re.search(r"\bonlyPoolAdmin\b", tail)})
report({"updateAToken", "updateVariableDebtToken", "dropReserve", "setReserveActive"} <= set(pool_admin_fns), f"onlyPoolAdmin functions in the verified PoolConfigurator source: {pool_admin_fns}")
struct = re.search(r"struct UpdateATokenInput \{([^}]*)\}", src)
report(bool(struct) and "address implementation;" in struct.group(1), "UpdateATokenInput carries a caller-supplied `address implementation`")

# 8. simulated calls (eth_call with a `from`, never sent): the access modifier, on both RPCs. Aave error '1' is
# CALLER_NOT_POOL_ADMIN and '4' is CALLER_NOT_RISK_OR_POOL_ADMIN; anything else means the call got past the modifier
# (a later revert on a dummy reserve is expected and is not an access refusal).
from eth_abi import encode  # noqa: E402

CONFIGURATOR = "0x83Cb1B4af26EEf6463aC20AFbAC9c0e2E017202F"  # the PoolConfigurator proxy (AaveV3EthereumHorizon.POOL_CONFIGURATOR)
STRANGER = "0x000000000000000000000000000000000000dEaD"
one = "0x0000000000000000000000000000000000000001"


def selector(sig):
    return bytes(Web3.keccak(text=sig))[:4]


CALLS = {
    "dropReserve (onlyPoolAdmin)": "0x" + (selector("dropReserve(address)") + encode(["address"], [one])).hex(),
    "updateAToken (onlyPoolAdmin)": "0x" + (selector("updateAToken((address,address,address,string,string,address,bytes))") + encode(
        ["(address,address,address,string,string,address,bytes)"], [(one, one, one, "a", "b", one, b"")])).hex(),
    "setSupplyCap (onlyRiskOrPoolAdmins)": "0x" + (selector("setSupplyCap(address,uint256)") + encode(["address", "uint256"], [one, 1])).hex(),
}


def refusal(rpc, frm, data):
    r = _post(rpc, "eth_call", [{"from": frm, "to": CONFIGURATOR, "data": data}, "latest"])
    if "result" in r:
        return None
    d = (r.get("error") or {}).get("data") or ""
    if isinstance(d, str) and d.startswith("0x08c379a0"):
        h = d[10:]
        return bytes.fromhex(h[128:128 + 2 * int(h[64:128], 16)]).decode(errors="replace")
    return ""  # reverted without a reason: past the modifier


for name, data in CALLS.items():
    want = {"4-of-6 Safe": (ADMIN_SAFE, False), "3-of-4 risk Safe": (RISK_SAFE, name.startswith("setSupplyCap")), "stranger": (STRANGER, None)}
    got = {who: [refusal(u, frm, data) for u in RPCS] for who, (frm, _) in want.items()}
    denied = lambda vals, code: all(v == code for v in vals)  # noqa: E731
    passed = lambda vals: all(v != "1" and v != "4" for v in vals)  # noqa: E731
    if name.startswith("setSupplyCap"):
        ok = passed(got["4-of-6 Safe"]) and passed(got["3-of-4 risk Safe"]) and denied(got["stranger"], "4")
        detail = "both Safes pass the modifier, a stranger gets error 4"
    else:
        ok = passed(got["4-of-6 Safe"]) and denied(got["3-of-4 risk Safe"], "1") and denied(got["stranger"], "1")
        detail = "the 4-of-6 passes the modifier, the 3-of-4 risk Safe and a stranger get error 1"
    report(ok, f"simulated {name}: {detail} (both RPCs; read {got})")

print(f"\n{len(failures)} check(s) failed" if failures else "\nALL CHECKS OK")
sys.exit(1 if failures else 0)
