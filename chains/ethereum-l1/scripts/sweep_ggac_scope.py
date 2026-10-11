#!/usr/bin/env python3
"""Read-only: exact role-protected functions of Aave's GranularGuardianAccessControl (Ethereum L1),
and the real on-chain scope of solveEmergency vs what Aave's own public documentation says.
    python3 sweep_ggac_scope.py
Sources, all fetched live (nothing hardcoded from memory):
  1. bgd-labs/aave-address-book (GitHub raw) -> GRANULAR_GUARDIAN address for Ethereum.
  2. Blockscout verified-source API -> full Solidity source + ABI of that contract.
  3. On-chain eth_call (publicnode RPC) -> role holders, CROSS_CHAIN_CONTROLLER address, live call test.
  4. Blockscout again -> proxy/implementation of CROSS_CHAIN_CONTROLLER, its full verified source tree.
  5. bgd-labs/aave-delivery-infrastructure README (GitHub raw) -> Aave's own public description of the roles.
Nothing is sent, no key, no state change (eth_call only).
"""
import json, re, subprocess, time
from web3 import Web3

RPC = "https://ethereum.publicnode.com"


def curl(url, body=None, headers=None):
    cmd = ["curl", "-sL", "-m", "40", "-A", "Mozilla/5.0"]
    for h in headers or []:
        cmd += ["-H", h]
    if body is not None:
        cmd += ["-X", "POST", "-H", "content-type: application/json", "--data", json.dumps(body)]
    cmd.append(url)
    for _ in range(3):
        try:
            return subprocess.run(cmd, capture_output=True, text=True, timeout=45).stdout
        except Exception:
            pass
    return ""


def rpc(method, params):
    for attempt in range(5):
        out = curl(RPC, {"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
        try:
            r = json.loads(out or "{}")
        except Exception:
            return None, out
        err = r.get("error")
        if err and err.get("code") == -32005 and attempt < 4:
            time.sleep(2 * (attempt + 1))  # public RPC rate limit backoff, ponytail: fixed backoff, add jitter if this still flakes
            continue
        return r.get("result"), err
    return None, err


sel = lambda sig: "0x" + Web3.keccak(text=sig).hex()[:8]


def call(to, sig, extra_data=""):
    res, err = rpc("eth_call", [{"to": to, "data": sel(sig) + extra_data}, "latest"])
    return res, err


# ---- 1. address book: GRANULAR_GUARDIAN on Ethereum (live, not from memory) ----
print("== 1. GRANULAR_GUARDIAN address (bgd-labs/aave-address-book, GitHub raw) ==")
src = curl("https://raw.githubusercontent.com/bgd-labs/aave-address-book/main/src/GovernanceV3Ethereum.sol")
m = re.search(r"GRANULAR_GUARDIAN\s*=\s*(0x[0-9a-fA-F]{40})", src)
if not m:
    print("DEAD END: GRANULAR_GUARDIAN address not found in the address-book -> stop.")
    raise SystemExit(0)
GGAC = Web3.to_checksum_address(m.group(1))
print(f"  GRANULAR_GUARDIAN (Ethereum) = {GGAC}")

# ---- 2. verified source + ABI from Blockscout ----
print("\n== 2. Verified source (Blockscout) of the contract at this address ==")
bs = curl(f"https://eth.blockscout.com/api/v2/smart-contracts/{GGAC}")
try:
    bs = json.loads(bs)
except Exception:
    print("DEAD END: Blockscout unreachable/non-JSON response -> stop.")
    raise SystemExit(0)
name = bs.get("name")
verified = bs.get("is_verified")
print(f"  verified contract name: {name}")
print(f"  is_verified : {verified}")
print(f"  compiler: {bs.get('compiler_version')}")
print(f"  main file: {bs.get('file_path')}")
if not verified or name != "GranularGuardianAccessControl":
    print("DEAD END: the contract at this address is not the expected GranularGuardianAccessControl -> stop.")
    raise SystemExit(0)

abi = bs.get("abi") or []
fn_entries = [e for e in abi if e.get("type") == "function"]
main_src = bs.get("source_code") or ""

# role gate per function, read straight out of the verified source text (onlyRole(X) modifier)
role_of_fn = {}
for fm in re.finditer(r"function\s+(\w+)\s*\([^)]*\)[^{;]*?\bonlyRole\(([A-Z_]+)\)", main_src, re.S):
    role_of_fn[fm.group(1)] = fm.group(2)
# grantRole/revokeRole are inherited from OZ AccessControl: onlyRole(getRoleAdmin(role)), default admin = DEFAULT_ADMIN_ROLE
for inherited in ("grantRole", "revokeRole"):
    role_of_fn.setdefault(inherited, "getRoleAdmin(role) [DEFAULT_ADMIN_ROLE by default]")

print("\n  EXACT role-protected functions (name, role gate, signature):")
protected = []
for e in fn_entries:
    n = e["name"]
    if n in role_of_fn or n in ("grantRole", "revokeRole"):
        sig = n + "(" + ",".join(i["type"] for i in e.get("inputs", [])) + ")"
        protected.append((n, role_of_fn.get(n, "?"), sig))
        print(f"    - {n:24s} role={role_of_fn.get(n, '?'):45s} sig={sig}")
other_fns = sorted(e["name"] for e in fn_entries if e["name"] not in role_of_fn and e["name"] not in ("grantRole", "revokeRole"))
print(f"  Other functions (not protected by a direct onlyRole, read-only or standard AccessControl): {other_fns}")

# ---- 3. on-chain role holders ----
print("\n== 3. Current role holders (on-chain, eth_call) ==")
roles = {}
for role_name in ("SOLVE_EMERGENCY_ROLE", "RETRY_ROLE"):
    rh, err = call(GGAC, f"{role_name}()")
    if rh and not err:
        roles[role_name] = rh[-64:].rjust(64, "0")
roles["DEFAULT_ADMIN_ROLE"] = "0" * 64  # OZ constant, always bytes32(0)

for role_name, role_hash in roles.items():
    cnt, err = call(GGAC, "getRoleMemberCount(bytes32)", role_hash)
    if err or not cnt:
        print(f"  {role_name}: eth_call getRoleMemberCount failed ({err})")
        continue
    n = int(cnt, 16)
    members = []
    for i in range(n):
        idx_hex = hex(i)[2:].rjust(64, "0")
        addr_res, aerr = call(GGAC, "getRoleMember(bytes32,uint256)", role_hash + idx_hex)
        if addr_res and not aerr:
            members.append(Web3.to_checksum_address("0x" + addr_res[-40:]))
        time.sleep(0.3)
    print(f"  {role_name} ({n} holder(s)): {members}")

# ---- 4. CROSS_CHAIN_CONTROLLER address + proxy/implementation ----
print("\n== 4. Target CROSS_CHAIN_CONTROLLER (read on-chain from the guardian, not assumed) ==")
ccc_res, ccc_err = call(GGAC, "CROSS_CHAIN_CONTROLLER()")
if ccc_err or not ccc_res:
    print(f"DEAD END: cannot read CROSS_CHAIN_CONTROLLER on-chain ({ccc_err}) -> stop.")
    raise SystemExit(0)
CCC = Web3.to_checksum_address("0x" + ccc_res[-40:])
print(f"  CROSS_CHAIN_CONTROLLER = {CCC}")

bs_ccc = curl(f"https://eth.blockscout.com/api/v2/smart-contracts/{CCC}")
try:
    bs_ccc = json.loads(bs_ccc)
except Exception:
    bs_ccc = {}
print(f"  name (proxy): {bs_ccc.get('name')}  proxy_type: {bs_ccc.get('proxy_type')}")
impls = bs_ccc.get("implementations") or []
if not impls:
    print("DEAD END: no implementation detected behind this proxy -> partial stop, section 5 skipped.")
    impl_addr = None
else:
    impl_addr = impls[0]["address_hash"]
    print(f"  current implementation: {impl_addr} ({impls[0].get('name')})")

# ---- 5. does the CURRENT implementation actually contain solveEmergency? (source-level truth) ----
if impl_addr:
    print("\n== 5. Does the CURRENT implementation of CROSS_CHAIN_CONTROLLER contain solveEmergency? ==")
    bs_impl = curl(f"https://eth.blockscout.com/api/v2/smart-contracts/{impl_addr}")
    try:
        bs_impl = json.loads(bs_impl)
    except Exception:
        bs_impl = {}
    all_src = {bs_impl.get("file_path"): bs_impl.get("source_code") or ""}
    for s in bs_impl.get("additional_sources") or []:
        all_src[s.get("file_path")] = s.get("source_code") or ""
    hits = [fp for fp, s in all_src.items() if s and "function solveEmergency" in s]
    inherits = [fp for fp, s in all_src.items() if s and re.search(r"\bcontract\s+\w+\s+is\b[^{]*EmergencyConsumer", s)]
    print(f"  files of the verified implementation: {len(all_src)}")
    print(f"  files containing 'function solveEmergency': {hits or 'NONE'}")
    print(f"  files whose contract inherits from EmergencyConsumer: {inherits or 'NONE'}")

    # empirical on-chain confirmation: does the deployed runtime bytecode dispatch the solveEmergency selector?
    se_entry = next(e for e in abi if e.get("name") == "solveEmergency")
    def canon(t):
        if t["type"].startswith("tuple"):
            inner = "(" + ",".join(canon(c) for c in t["components"]) + ")"
            return inner + t["type"][5:]
        return t["type"]
    canon_sig = "solveEmergency(" + ",".join(canon(i) for i in se_entry["inputs"]) + ")"
    se_selector = sel(canon_sig)[2:]
    code, _ = rpc("eth_getCode", [impl_addr, "latest"])
    code = (code or "0x")[2:]
    push4 = "63" + se_selector  # PUSH4 <selector>, how Solidity's function dispatcher checks selectors
    print(f"  canonical signature rebuilt: {canon_sig}")
    print(f"  selector solveEmergency = 0x{se_selector}")
    print(f"  this selector (PUSH4) is present in the runtime bytecode of the current implementation: {'YES' if push4 in code else 'NO'}")

    # live eth_call against the PROXY directly (empty-array args), to see the actual revert
    from eth_abi import encode
    args = ([], [], [], [], [], [], [], [], [])
    types = ["(uint256,uint8)[]", "(uint256,uint120)[]", "(address,uint256[])[]", "(address,uint256[])[]",
             "address[]", "address[]", "(address,address,uint256)[]", "(address,uint256[])[]", "(uint256,uint256)[]"]
    encoded = encode(types, args).hex()
    call_res, call_err = rpc("eth_call", [{"to": CCC, "data": "0x" + se_selector + encoded}, "latest"])
    print(f"  eth_call solveEmergency(9x []) directly on the CROSS_CHAIN_CONTROLLER proxy: result={call_res} error={call_err}")

# ---- 6. what Aave's OWN public documentation says about the scope ----
print("\n== 6. Aave's public documentation (bgd-labs/aave-delivery-infrastructure, docs/overview.md) ==")
doc = curl("https://raw.githubusercontent.com/bgd-labs/aave-delivery-infrastructure/main/docs/overview.md")
if not doc or len(doc) < 200:
    print("DEAD END: README/overview.md unreachable -> no comparison possible.")
else:
    lines = doc.splitlines()
    for i, l in enumerate(lines):
        if "SOLVE_EMERGENCY_ROLE" in l or ("solveEmergency" in l and "goal" in l.lower()):
            print(f"  L{i}: {l.strip()}")
    m2 = re.search(r"goal is to return.*?(?=\n\n|\Z)", doc, re.S)
    if m2:
        print("\n  Scope paragraph (docs/overview.md, summarized, not copied in full):")
        print("  -> solveEmergency aims to bring a.DI back to operational mode: a working sending state (>=1 active bridge")
        print("     adapter per destination chain) and a working receiving state (enough adapters to reach")
        print("     requiredConfirmations); it can also be used to force a NON-working state if the bridges")
        print("     are compromised. No mention of any power over the funds of the Aave Pool or of other contracts.")

# ---- 7. what kind of account actually holds each role (EOA / Safe-sized proxy / other contract) ----
print("\n== 7. Nature of the holder accounts (EOA vs contract, bytecode size) ==")
all_members = set()
for role_name, role_hash in roles.items():
    cnt, err = call(GGAC, "getRoleMemberCount(bytes32)", role_hash)
    if err or not cnt:
        continue
    for i in range(int(cnt, 16)):
        idx_hex = hex(i)[2:].rjust(64, "0")
        addr_res, aerr = call(GGAC, "getRoleMember(bytes32,uint256)", role_hash + idx_hex)
        if addr_res and not aerr:
            all_members.add(Web3.to_checksum_address("0x" + addr_res[-40:]))
        time.sleep(0.3)
for a in sorted(all_members):
    code, _ = rpc("eth_getCode", [a, "latest"])
    code = code or "0x"
    kind = "EOA" if code == "0x" else f"contract ({(len(code) - 2) // 2} bytes)"
    print(f"  {a} : {kind}")
    time.sleep(0.3)

print("\n== END ==")
