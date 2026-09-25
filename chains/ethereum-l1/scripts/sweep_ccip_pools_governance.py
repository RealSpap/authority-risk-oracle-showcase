#!/usr/bin/env python3
"""Read-only, independent re-derivation: Chainlink CCIP on Ethereum mainnet -- (a) every token pool
registered in the on-chain TokenAdminRegistry (owner, rate-limit admin, pool type, reserves held) and
(b) CCIP on-chain governance (the RBACTimelock found as owner() of the core CCIP contracts, its
AccessControl roles, and the ManyChainMultiSig / Gnosis Safe contracts holding those roles, decoded
for their signers and quorum).

    python3 sweep_ccip_pools_governance.py [--max-tokens N] [--dump rows.json] [--cross-check]

Addresses come from the official CCIP Directory (docs.chain.link/ccip/directory/mainnet: an Astro
page whose JSON props are HTML-entity-escaped in the raw HTML -- html.unescape() then a plain
json.loads() recovers them, no RSC framework knowledge needed) and are independently confirmed
on-chain via typeAndVersion(). Function signatures and struct layouts (TokenConfig, RBACTimelock role
constants, ManyChainMultiSig Config/Signer) come from docs.chain.link/ccip/api-reference and
github.com/smartcontractkit/ccip-owner-contracts (RBACTimelock.sol, ManyChainMultiSig.sol), fetched
and read directly rather than assumed. Primary RPC: ethereum.publicnode.com. --cross-check repeats
the handful of numbers that matter most (core addresses' typeAndVersion, token count, timelock role
member counts) against a second, differently-operated RPC (eth.drpc.org) to catch a single-provider
fluke. Nothing is sent, no key used.
"""
import argparse
import html
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import requests
from web3 import Web3

ap = argparse.ArgumentParser()
ap.add_argument("--max-tokens", type=int, default=2000, help="cap on tokens paged out of TokenAdminRegistry")
ap.add_argument("--dump", default=None)
ap.add_argument("--cross-check", action="store_true", help="also verify the key numbers against a second RPC")
ARGS = ap.parse_args()

PRIMARY_RPC = "https://ethereum.publicnode.com"
SECONDARY_RPC = "https://eth.drpc.org"  # different operator, used only for --cross-check
w3 = Web3(Web3.HTTPProvider(PRIMARY_RPC, request_kwargs={"timeout": 30}))
cs = Web3.to_checksum_address

# ---- minimal ABI fragments, each taken from an official source read in this run (see header) ----
ABI = {
    "typeAndVersion": [{"name": "typeAndVersion", "type": "function", "stateMutability": "view",
                         "inputs": [], "outputs": [{"type": "string"}]}],
    "owner": [{"name": "owner", "type": "function", "stateMutability": "view",
               "inputs": [], "outputs": [{"type": "address"}]}],
    "tar": [
        {"name": "getAllConfiguredTokens", "type": "function", "stateMutability": "view",
         "inputs": [{"type": "uint64", "name": "startIndex"}, {"type": "uint64", "name": "maxCount"}],
         "outputs": [{"type": "address[]", "name": "tokens"}]},
        {"name": "getTokenConfig", "type": "function", "stateMutability": "view",
         "inputs": [{"type": "address", "name": "token"}],
         "outputs": [{"type": "tuple", "name": "config", "components": [
             {"type": "address", "name": "administrator"},
             {"type": "address", "name": "pendingAdministrator"},
             {"type": "address", "name": "tokenPool"}]}]},
    ],
    "pool": [
        {"name": "getRateLimitAdmin", "type": "function", "stateMutability": "view",
         "inputs": [], "outputs": [{"type": "address"}]},
        {"name": "getToken", "type": "function", "stateMutability": "view",
         "inputs": [], "outputs": [{"type": "address"}]},
    ],
    "erc20": [
        {"name": "symbol", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "string"}]},
        {"name": "decimals", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "uint8"}]},
        {"name": "balanceOf", "type": "function", "stateMutability": "view",
         "inputs": [{"type": "address"}], "outputs": [{"type": "uint256"}]},
    ],
    "timelock": [
        {"name": "getMinDelay", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "uint256"}]},
        {"name": "getRoleMemberCount", "type": "function", "stateMutability": "view",
         "inputs": [{"type": "bytes32"}], "outputs": [{"type": "uint256"}]},
        {"name": "getRoleMember", "type": "function", "stateMutability": "view",
         "inputs": [{"type": "bytes32"}, {"type": "uint256"}], "outputs": [{"type": "address"}]},
    ] + [{"name": r, "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "bytes32"}]}
         for r in ("ADMIN_ROLE", "PROPOSER_ROLE", "EXECUTOR_ROLE", "CANCELLER_ROLE", "BYPASSER_ROLE")],
    "mcms": [
        {"name": "getConfig", "type": "function", "stateMutability": "view",
         "inputs": [], "outputs": [{"type": "tuple", "name": "config", "components": [
             {"type": "tuple[]", "name": "signers", "components": [
                 {"type": "address", "name": "addr"}, {"type": "uint8", "name": "index"}, {"type": "uint8", "name": "group"}]},
             {"type": "uint8[32]", "name": "groupQuorums"},
             {"type": "uint8[32]", "name": "groupParents"}]}]},
    ],
    "safe": [
        {"name": "getOwners", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "address[]"}]},
        {"name": "getThreshold", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "uint256"}]},
        {"name": "VERSION", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "string"}]},
    ],
}
ALL_ABI = [f for group in ABI.values() for f in group]


def contract(w3_inst, addr):
    return w3_inst.eth.contract(address=cs(addr), abi=ALL_ABI)


def safe_call(fn, default=None, retries=3):
    # ponytail: public RPC under concurrent load drops/times out a real share of calls (measured:
    # distinct-pool count swung 504->476 across two runs 7 minutes apart on the same 563 tokens) --
    # a bare try/except would silently read those as "this pool doesn't exist" rather than "the RPC
    # dropped this one call". A few retries with backoff is the honest floor, not full robustness;
    # bump retries or add jitter/backoff tuning if counts still don't stabilize.
    for attempt in range(retries):
        try:
            return fn()
        except Exception:
            if attempt == retries - 1:
                return default
            time.sleep(0.4 * (attempt + 1))
    return default


def get_directory_addresses():
    """The CCIP Directory page (Astro/React) ships its data as an HTML-entity-escaped JSON blob
    inside a `props="..."` attribute. html.unescape() turns &quot; back into ", after which the
    chain block for "mainnet" is a normal (if verbose, Astro-serialized) JSON object."""
    r = requests.get("https://docs.chain.link/ccip/directory/mainnet",
                      headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
    r.raise_for_status()
    page = html.unescape(r.text)
    i = page.find('"tokenAdminRegistry"')
    if i < 0:
        raise RuntimeError("CCIP Directory page layout changed: 'tokenAdminRegistry' not found")
    # totalLanes/totalTokens sit ~230 chars BEFORE tokenAdminRegistry in the same chain object
    # (order is name, logo, totalLanes, totalTokens, chain, key, explorer, ..., tokenAdminRegistry,
    # ..., router, ..., armProxy), so the window must extend backward, not just forward.
    chunk = page[max(0, i - 500):i + 1500]

    def addr_after(key):
        m = re.search(re.escape(key) + r'"\s*:\s*\[0,\s*"?(0x[0-9a-fA-F]{40})?', chunk)
        return cs(m.group(1)) if m and m.group(1) else None

    router_m = re.search(r'"router"\s*:\s*\[0,\{"address"\s*:\s*\[0,\s*"(0x[0-9a-fA-F]{40})"', chunk)
    armproxy_m = re.search(r'"armProxy"\s*:\s*\[0,\{"address"\s*:\s*\[0,\s*"(0x[0-9a-fA-F]{40})"', chunk)
    total_tokens_m = re.search(r'"totalTokens"\s*:\s*\[0,\s*(\d+)\]', chunk)
    return {
        "token_admin_registry": addr_after("tokenAdminRegistry"),
        "ccip_home": addr_after("ccipHome"),
        "router": cs(router_m.group(1)) if router_m else None,
        "rmn_proxy": cs(armproxy_m.group(1)) if armproxy_m else None,
        "directory_total_tokens": int(total_tokens_m.group(1)) if total_tokens_m else None,
    }


print("=" * 78)
print("Fetching CCIP Directory (docs.chain.link/ccip/directory/mainnet)")
print("=" * 78)
directory = get_directory_addresses()
for k, v in directory.items():
    print(f"  {k}: {v}")
for k in ("token_admin_registry", "ccip_home", "router", "rmn_proxy"):
    if not directory[k]:
        print(f"FATAL: could not extract {k} from the CCIP Directory page", file=sys.stderr)
        sys.exit(1)

TOKEN_ADMIN_REGISTRY = directory["token_admin_registry"]
ROUTER = directory["router"]
RMN_PROXY = directory["rmn_proxy"]
CCIP_HOME = directory["ccip_home"]

# ============================================================
# PART A -- CCIP token pools via the on-chain TokenAdminRegistry
# ============================================================
print()
print("=" * 78)
print("PART A: CCIP token pools registered on-chain")
print("=" * 78)

core = {"TokenAdminRegistry": TOKEN_ADMIN_REGISTRY, "Router": ROUTER, "RMN proxy (armProxy)": RMN_PROXY, "CCIPHome": CCIP_HOME}
core_tv, core_owner = {}, {}
for name, addr in core.items():
    c = contract(w3, addr)
    tv = safe_call(lambda c=c: c.functions.typeAndVersion().call())
    ow = safe_call(lambda c=c: c.functions.owner().call())
    core_tv[name], core_owner[name] = tv, ow
    print(f"  {name:24s} {addr}  typeAndVersion={tv!r}  owner={ow}")

tar = contract(w3, TOKEN_ADMIN_REGISTRY)
tokens = safe_call(lambda: tar.functions.getAllConfiguredTokens(0, ARGS.max_tokens).call(), [])
print(f"\ngetAllConfiguredTokens(0,{ARGS.max_tokens}) -> {len(tokens)} tokens on-chain "
      f"(CCIP Directory UI 'totalTokens' field says {directory['directory_total_tokens']})")
if len(tokens) >= ARGS.max_tokens:
    print(f"  WARNING: hit the --max-tokens cap ({ARGS.max_tokens}); there may be more tokens than read here.")


def read_token_config(token):
    cfg = safe_call(lambda: tar.functions.getTokenConfig(token).call())
    return token, cfg  # cfg = (administrator, pendingAdministrator, tokenPool) or None


with ThreadPoolExecutor(8) as ex:
    token_configs = dict(ex.map(read_token_config, tokens))

pools = sorted({cfg[2] for cfg in token_configs.values() if cfg and int(cfg[2], 16) != 0})
print(f"{len(pools)} distinct non-zero token pool address(es) among those {len(tokens)} tokens")


def read_pool(pool):
    c = contract(w3, pool)
    row = {"pool": pool}
    row["typeAndVersion"] = safe_call(lambda: c.functions.typeAndVersion().call())
    row["owner"] = safe_call(lambda: c.functions.owner().call())
    row["rate_limit_admin"] = safe_call(lambda: c.functions.getRateLimitAdmin().call())
    tok = safe_call(lambda: c.functions.getToken().call())
    row["underlying_token"] = tok
    if tok:
        tc = contract(w3, tok)
        row["symbol"] = safe_call(lambda: tc.functions.symbol().call())
        row["decimals"] = safe_call(lambda: tc.functions.decimals().call())
        raw = safe_call(lambda: tc.functions.balanceOf(cs(pool)).call())
        row["reserves_raw"] = raw
        row["reserves"] = raw / (10 ** row["decimals"]) if raw is not None and row.get("decimals") is not None else None
    else:
        row["symbol"] = row["decimals"] = row["reserves_raw"] = row["reserves"] = None
    return row


with ThreadPoolExecutor(8) as ex:
    pool_rows = list(ex.map(read_pool, pools))

n_owner_ok = sum(1 for r in pool_rows if r["owner"])
n_rla = sum(1 for r in pool_rows if r["rate_limit_admin"] and int(r["rate_limit_admin"], 16) != 0)
by_type = {}
for r in pool_rows:
    by_type[r["typeAndVersion"] or "?"] = by_type.get(r["typeAndVersion"] or "?", 0) + 1

print(f"  owner() answered: {n_owner_ok}/{len(pool_rows)}")
print(f"  non-zero getRateLimitAdmin(): {n_rla}/{len(pool_rows)}")
print("  pool typeAndVersion breakdown:")
for t, n in sorted(by_type.items(), key=lambda kv: -kv[1]):
    print(f"    {n:4d}  {t}")

# governance cross-owned-but-not-owner example: any pool whose owner != its rate_limit_admin, both non-zero
interesting = [r for r in pool_rows if r["owner"] and r["rate_limit_admin"]
               and int(r["rate_limit_admin"], 16) != 0 and r["owner"] != r["rate_limit_admin"]]
print(f"\n  pools where owner() != getRateLimitAdmin() (both non-zero): {len(interesting)}")
for r in interesting[:10]:
    print(f"    pool {r['pool']}  symbol={r['symbol']}  owner={r['owner']}  rateLimitAdmin={r['rate_limit_admin']}")

for r in sorted(pool_rows, key=lambda r: -(r["reserves"] or 0))[:8]:
    sym = r["symbol"] or "?"
    print(f"    top-reserve pool {r['pool']}  {sym:8s}  reserves~={r['reserves']:.2f}" if r["reserves"] else
          f"    top-reserve pool {r['pool']}  {sym}  reserves=?")

# ============================================================
# PART B -- CCIP on-chain governance (RBACTimelock + MCMS/Safe)
# ============================================================
print()
print("=" * 78)
print("PART B: CCIP on-chain governance")
print("=" * 78)

owner_candidates = sorted({a for a in core_owner.values() if a})
print(f"Distinct owner() address(es) across the 4 core contracts: {owner_candidates}")
if len(owner_candidates) != 1:
    print("  NOTE: core contracts do NOT all share a single owner (or one owner() call failed) -- see values above.")

timelock_addr = None
role_hash = {}
ROLES = ["ADMIN_ROLE", "PROPOSER_ROLE", "EXECUTOR_ROLE", "CANCELLER_ROLE", "BYPASSER_ROLE"]
for cand in owner_candidates:
    c = contract(w3, cand)
    h = safe_call(lambda c=c: c.functions.PROPOSER_ROLE().call())
    if h is not None:
        timelock_addr = cand
        break

if not timelock_addr:
    print("Could not confirm an RBACTimelock among the owner() candidates.")
else:
    tl = contract(w3, timelock_addr)
    tl_tv = safe_call(lambda: tl.functions.typeAndVersion().call())
    min_delay = safe_call(lambda: tl.functions.getMinDelay().call())
    print(f"\nRBACTimelock confirmed by AccessControl selector PROPOSER_ROLE(): {timelock_addr}")
    print(f"  typeAndVersion() = {tl_tv!r}")
    print(f"  getMinDelay() = {min_delay} seconds (~{min_delay / 3600:.2f}h)" if min_delay is not None else "  getMinDelay() failed")

    for role_name in ROLES:
        role_hash[role_name] = safe_call(lambda role_name=role_name: getattr(tl.functions, role_name)().call())

    role_members = {}
    for role_name, h in role_hash.items():
        if h is None:
            role_members[role_name] = []
            continue
        cnt = safe_call(lambda h=h: tl.functions.getRoleMemberCount(h).call(), 0)
        members = [safe_call(lambda h=h, i=i: tl.functions.getRoleMember(h, i).call()) for i in range(cnt)]
        role_members[role_name] = [m for m in members if m]
        print(f"  {role_name}: {cnt} member(s): {role_members[role_name]}")

    all_members = sorted({m for members in role_members.values() for m in members})
    print(f"\n{len(all_members)} distinct address(es) hold at least one role")
    role_owners = {}
    for m in all_members:
        roles_here = [rn for rn, ms in role_members.items() if m in ms]
        role_owners[m] = roles_here
        code = w3.eth.get_code(cs(m))
        is_contract = len(code) > 0
        print(f"  {m}  roles={roles_here}  {'contract, ' + str(len(code)) + ' bytes' if is_contract else 'EOA'}")

    print("\n  decoding each contract role member as ManyChainMultiSig, else Gnosis Safe:")
    for m in all_members:
        code = w3.eth.get_code(cs(m))
        if len(code) == 0:
            print(f"    {m}: EOA, not a multisig contract")
            continue
        c = contract(w3, m)
        m_tv = safe_call(lambda c=c: c.functions.typeAndVersion().call())
        m_owner = safe_call(lambda c=c: c.functions.owner().call())
        cfg = safe_call(lambda c=c: c.functions.getConfig().call())
        if cfg is not None:
            signers, group_quorums, group_parents = cfg
            print(f"    {m}  ManyChainMultiSig  typeAndVersion={m_tv!r}  owner()={m_owner}  {len(signers)} signer(s)")
            for addr, idx, group in signers:
                print(f"      signer {addr}  index={idx}  group={group}")
            continue
        owners = safe_call(lambda c=c: c.functions.getOwners().call())
        threshold = safe_call(lambda c=c: c.functions.getThreshold().call())
        if owners is not None and threshold is not None:
            ver = safe_call(lambda c=c: c.functions.VERSION().call())
            print(f"    {m}  Gnosis Safe {threshold}-of-{len(owners)}  VERSION={ver}  owners={owners}")
        else:
            print(f"    {m}  NOT decodable as ManyChainMultiSig nor Gnosis Safe (typeAndVersion={m_tv!r}, owner()={m_owner}) "
                  f"-- reported unidentified, not guessed.")

# ============================================================
# Cross-check against a second, independently-operated RPC
# ============================================================
if ARGS.cross_check:
    print()
    print("=" * 78)
    print(f"CROSS-CHECK against {SECONDARY_RPC}")
    print("=" * 78)
    w3b = Web3(Web3.HTTPProvider(SECONDARY_RPC, request_kwargs={"timeout": 30}))
    ok = safe_call(lambda: w3b.eth.block_number)
    print(f"  secondary RPC reachable, block {ok}" if ok else "  secondary RPC UNREACHABLE, skipping cross-check")
    if ok:
        for name, addr in core.items():
            cb = contract(w3b, addr)
            tv_b = safe_call(lambda cb=cb: cb.functions.typeAndVersion().call())
            match = "match" if tv_b == core_tv[name] else "MISMATCH"
            print(f"  {name:24s} typeAndVersion via secondary RPC = {tv_b!r}  ({match} vs primary)")
        tar_b = contract(w3b, TOKEN_ADMIN_REGISTRY)
        tokens_b = safe_call(lambda: tar_b.functions.getAllConfiguredTokens(0, ARGS.max_tokens).call(), [])
        print(f"  getAllConfiguredTokens count via secondary RPC: {len(tokens_b)} "
              f"({'match' if len(tokens_b) == len(tokens) else 'MISMATCH'} vs primary's {len(tokens)})")
        if timelock_addr:
            tl_b = contract(w3b, timelock_addr)
            for role_name, h in role_hash.items():
                if h is None:
                    continue
                cnt_b = safe_call(lambda h=h: tl_b.functions.getRoleMemberCount(h).call())
                cnt_a = safe_call(lambda h=h: tl.functions.getRoleMemberCount(h).call())
                print(f"  {role_name} member count: primary={cnt_a} secondary={cnt_b} "
                      f"({'match' if cnt_a == cnt_b else 'MISMATCH'})")

# ============================================================
result = {
    "directory": directory,
    "core_typeAndVersion": core_tv,
    "core_owner": core_owner,
    "n_tokens_onchain": len(tokens),
    "n_pools": len(pools),
    "pools": pool_rows,
    "timelock": timelock_addr,
    "role_members": role_members if timelock_addr else None,
}
if ARGS.dump:
    json.dump(result, open(ARGS.dump, "w"), indent=2, default=str)
    print(f"\nwrote {ARGS.dump}")
