#!/usr/bin/env python3
"""What each tracked Morpho vault's underlying token issuer can do to the balances it holds.
See scripts/lib/issuer_power.py's own docstring for why this is disclosed, not scored, and its
precedent (the source research, `sweep_asset_authority.py`, scoped down to just the 4 distinct assets
this oracle's 9 tracked Morpho V1 vaults actually hold). Live read: Blockscout's verified-contract API
for each token's ABI and controller getters, each chain's own RPC for eth_getCode/Safe resolution.
Nothing is sent, no key.

    python3 scripts/check_issuer_power.py

Exit status 1 if any asset's ABI could not be read this run, 0 otherwise.
"""
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "lib"))
sys.path.insert(0, os.path.dirname(__file__))
from lib.issuer_power import KNOWN_CONTROLLER_GETTERS, KNOWN_ROLE_MEMBER_GETTERS, classify_controller, classify_functions, has_any_restrictive_power  # noqa: E402
from lib.web3_utils import _read, call_raw, get_w3, read_address_array_getter, read_address_getter, safe_owners_and_threshold  # noqa: E402
from web3 import Web3  # noqa: E402

# ADDED 2026-09-26 (chain 42161, Arbitrum): extended for scripts/check_compound_v3_comet_issuer_power.py,
# which reuses read_abi()/read_controllers()/read_role_members() across all 3 tracked Comet markets'
# chains -- purely additive, read_abi() takes chain_id as a parameter so this never affects the
# Morpho-vault-scoped main() below.
BLOCKSCOUT = {1: "eth.blockscout.com", 8453: "base.blockscout.com", 42161: "arbitrum.blockscout.com"}
RPC = {1: "https://ethereum-rpc.publicnode.com", 8453: "https://mainnet.base.org", 42161: "https://arb1.arbitrum.io/rpc"}

# The 4 distinct underlying assets of this oracle's 9 tracked Morpho V1 vaults (Morpho's public API,
# read 2026-09-26): USDC/USDT are read on their real issuing chain (Ethereum L1 / Base) even where a
# tracked vault holds a bridged copy elsewhere -- the issuer's own controllers live where the token is
# actually deployed, not on every chain it circulates on. AUSD is verified on Ethereum L1
# (AgoraDollarErc1967Proxy) even though the vault holding it is on Monad, for the same reason.
TRACKED_ASSETS = [
    # (chain_id, address, symbol, vaults that hold it)
    (8453, "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913", "USDC", ["Gauntlet USDC Prime", "Grove x Steakhouse USDC High Yield", "Steakhouse USDC (Base)", "Spark USDC Vault"]),
    (1, "0xdAC17F958D2ee523a2206206994597C13D831ec7", "USDT", ["Steakhouse USDT (Ethereum L1)"]),
    (1, "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48", "USDC", ["Steakhouse USDC (Ethereum L1)", "1337 USDC", "Adpend USDC"]),
    (1, "0x00000000eFE302BEAA2b3e6e1b18d08D69a9012a", "AUSD", ["Grove x Steakhouse High Yield AUSD (Monad)"]),
]


def fetch_json(url, tries=3):
    """Shells out to curl with a browser User-Agent -- Blockscout 403s bare urllib.request calls
    (no UA header); same fix `sweep_asset_authority.py`'s own curl() helper already uses."""
    cmd = ["curl", "-s", "-m", "30", "-A", "Mozilla/5.0", url]
    for _ in range(tries):
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=35).stdout
            return json.loads(out)
        except Exception:
            continue
    return None


def read_abi(chain_id, address):
    """(function_names, address_getter_names, array_getter_names, contract_name) or
    (None, None, None, None) if unread. Follows ONE implementation hop for a proxy (same limit
    sweep_asset_authority.py's own analyse() has)."""
    d = fetch_json(f"https://{BLOCKSCOUT[chain_id]}/api/v2/smart-contracts/{address}")
    if not d or d.get("message") or (not d.get("is_verified") and not d.get("abi") and not d.get("implementations")):
        return None, None, None, None
    abis = [d.get("abi") or []]
    for impl in (d.get("implementations") or [])[:1]:
        impl_addr = impl.get("address") or impl.get("address_hash")
        if impl_addr:
            di = fetch_json(f"https://{BLOCKSCOUT[chain_id]}/api/v2/smart-contracts/{impl_addr}")
            if di:
                abis.append(di.get("abi") or [])
    fns = {x["name"] for ab in abis for x in ab if x.get("type") == "function" and x.get("stateMutability") not in ("view", "pure")}

    def _zero_arg_getters(output_type):
        return {x["name"] for ab in abis for x in ab if x.get("type") == "function" and x.get("stateMutability") in ("view", "pure")
                and not x.get("inputs") and x.get("outputs") and x["outputs"][0].get("type") == output_type}

    return fns, _zero_arg_getters("address"), _zero_arg_getters("address[]"), d.get("name")


def read_controllers(w3, chain_id, address, getter_names):
    """{getter_name: (address, classified_label)} for every KNOWN_CONTROLLER_GETTERS name the ABI
    actually exposes and that resolves to a non-zero address."""
    out = {}
    for getter in KNOWN_CONTROLLER_GETTERS:
        if getter not in getter_names:
            continue
        try:
            holder = read_address_getter(w3, address, getter)
        except Exception:
            continue
        if not holder or int(holder, 16) == 0:
            continue
        out[getter] = (holder, _classify_address(w3, holder))
    return out


def _classify_address(w3, addr):
    try:
        code_len = len(w3.eth.get_code(w3.to_checksum_address(addr)))
    except Exception:
        return classify_controller(None, False)
    safe = None
    if code_len:
        try:
            safe = safe_owners_and_threshold(w3, addr)
        except Exception:
            safe = None
    shape = (safe[1], len(safe[0])) if safe else None
    return classify_controller(code_len, safe is not None, shape)


def read_role_members(w3, address, array_getter_names):
    """{getter_name: [(member address, classified label), ...]} for every KNOWN_ROLE_MEMBER_GETTERS
    name the ABI actually exposes and that returns at least one member -- Agora's AUSD-style bespoke
    role registry (see scripts/lib/issuer_power.py's "EXTENDED" docstring note), no event-log replay
    needed. Each member classified EOA/Safe/contract exactly like read_controllers() does."""
    out = {}
    for getter in KNOWN_ROLE_MEMBER_GETTERS:
        if getter not in array_getter_names:
            continue
        try:
            members = read_address_array_getter(w3, address, getter)
        except Exception:
            continue
        if members:
            out[getter] = [(m, _classify_address(w3, m)) for m in members]
    return out


# ADDED 2026-10-01 (roadmap R10): how much can be minted RIGHT NOW without a further admin act. Disclosed, never scored.
# Full-range eth_getLogs verified that day on Tenderly's mainnet gateway (3,811 USDC MinterConfigured/MinterRemoved logs in
# one call). Base has no such source: Tenderly's Base gateway caps at 1,000 blocks and Blockscout stops at 10,000 results,
# so the Base USDC minter set is printed UNREAD rather than built from a partial history.
LOGS_RPC = {1: "https://gateway.tenderly.co/public/mainnet"}
MINTER_CONFIGURED = bytes(Web3.keccak(text="MinterConfigured(address,uint256)"))
MINTER_REMOVED = bytes(Web3.keccak(text="MinterRemoved(address)"))


def _fn(name, inputs=("address",), out="uint256"):
    outs = [{"type": t} for t in out] if isinstance(out, tuple) else [{"type": out}]
    return [{"name": name, "type": "function", "stateMutability": "view", "inputs": [{"type": t} for t in inputs], "outputs": outs}]


# Agora AUSD: getAmountCanBeMinted(minter) returns (currentAmountInFlight, amountCanBeMinted) (verified ABI, read 2026-10-01).
AGORA_CAN_MINT = _fn("getAmountCanBeMinted", out=("uint256", "uint256"))


def replay_minters(logs):
    """Current FiatToken minter set from MinterConfigured / MinterRemoved logs, replayed in chain order (block, logIndex)."""
    cur = set()
    for lg in sorted(logs, key=lambda x: (x["blockNumber"], x["logIndex"])):
        who = Web3.to_checksum_address(bytes(lg["topics"][1])[-20:])
        if bytes(lg["topics"][0]) == MINTER_CONFIGURED:
            cur.add(who)
        elif bytes(lg["topics"][0]) == MINTER_REMOVED:
            cur.discard(who)
    return cur


def read_mint_bound(w3, chain_id, address, fns):
    """One printable line: what can be minted without a further admin act, or why it is UNREAD. A revert means "not this
    interface"; a network failure raises RpcUnavailable out of call_raw and is reported UNREAD, never as zero."""
    try:
        dec = call_raw(w3, address, _fn("decimals", (), "uint8"), "decimals")
        if dec is None:
            return "UNREAD (decimals() reverted)"
        unit = 10 ** dec
        if call_raw(w3, address, _fn("minterAllowance"), "minterAllowance", "0x" + "00" * 20) is not None:
            if chain_id not in LOGS_RPC:
                return f"per-minter allowances (FiatToken); minter set UNREAD: no full-range log source for chain {chain_id}"
            # Logs and reads pinned to ONE block both sources have reached: a minter configured in a block the log source had
            # not seen yet would otherwise be missing from the total without a trace.
            logs_w3 = get_w3(LOGS_RPC[chain_id])
            head = min(w3.eth.block_number, logs_w3.eth.block_number)
            logs = logs_w3.eth.get_logs({"address": Web3.to_checksum_address(address), "fromBlock": 0, "toBlock": head,
                                         "topics": [["0x" + MINTER_CONFIGURED.hex(), "0x" + MINTER_REMOVED.hex()]]})
            if not logs:
                return "per-minter allowances (FiatToken); minter replay came back EMPTY: an anomaly, UNREAD, not 'no minter'"
            token = w3.eth.contract(address=Web3.to_checksum_address(address), abi=_fn("isMinter", out="bool") + _fn("minterAllowance"))

            def at_head(name, m):
                return _read(lambda: getattr(token.functions, name)(m).call(block_identifier=head), what=f"{name}({m}) at block {head}")
            rows = []
            for m in sorted(replay_minters(logs)):
                if at_head("isMinter", m) is not True:
                    return f"per-minter allowances (FiatToken); replay says {m} is a minter at block {head}, isMinter() disagrees: UNREAD"
                rows.append((m, at_head("minterAllowance", m)))
            if any(a is None for _, a in rows):
                return "per-minter allowances (FiatToken); a minterAllowance() reverted: UNREAD"
            total = sum(a for _, a in rows) / unit
            detail = ", ".join(f"{m} {a / unit:,.0f}" for m, a in sorted(rows, key=lambda r: -r[1]))
            return f"{len(rows)} minters (FiatToken, replayed from {len(logs)} logs to block {head}, each confirmed by isMinter there): {total:,.0f} mintable [{detail}]"
        if call_raw(w3, address, AGORA_CAN_MINT, "getAmountCanBeMinted", "0x" + "00" * 20) is not None:
            paused = call_raw(w3, address, _fn("isMintPaused", (), "bool"), "isMintPaused")
            roles = {}
            for getter in ("getMinterRoleMembers", "getBridgeMinterRoleMembers"):
                members = read_address_array_getter(w3, address, getter)
                if members is None:
                    return f"rate-limited minters (Agora); {getter}() reverted: UNREAD"
                for m in members:
                    roles.setdefault(Web3.to_checksum_address(m), []).append(getter[3:-11])
            parts, total = [], 0
            for m, held in sorted(roles.items()):  # one member holding both roles is counted once
                res = call_raw(w3, address, AGORA_CAN_MINT, "getAmountCanBeMinted", m)
                if res is None:
                    return f"rate-limited minters (Agora); getAmountCanBeMinted({m}) reverted: UNREAD"
                total += res[1]
                parts.append(f"{'+'.join(held)} {m} {res[1] / unit:,.0f}")
            return (f"rate-limited minters (Agora), minting paused={paused}: {total / unit:,.0f} mintable now in the current windows "
                    f"[{'; '.join(parts) or 'no member'}]")
        if "issue" in fns:
            return "no on-chain bound: issue(uint256) mints any amount, there is no allowance or rate limit to read"
        return "no known mint-bound interface: UNREAD"
    except Exception as e:  # noqa: BLE001 -- RpcUnavailable or a log-source failure: reported, never a zero
        return f"UNREAD ({type(e).__name__}: {str(e)[:100]})"


def main():
    w3_by_chain = {}
    unread = mint_unread = 0
    for chain_id, addr, symbol, vaults in TRACKED_ASSETS:
        if chain_id not in w3_by_chain:
            w3_by_chain[chain_id] = get_w3(RPC[chain_id])
        w3 = w3_by_chain[chain_id]

        fns, getters, array_getters, name = read_abi(chain_id, addr)
        if fns is None:
            print(f"  [UNREAD] chain {chain_id} {symbol} ({addr}): not verified or ABI unreadable this run")
            unread += 1
            continue

        families = classify_functions(fns)
        flag = " <-- freeze, seize or pause capable" if has_any_restrictive_power(families) else ""
        print(f"\n{symbol} (chain {chain_id}, {name}) -- held by {len(vaults)} tracked vault(s): {', '.join(vaults)}")
        print(f"  functions found: freeze={families['freeze']} seize={families['seize']} pause={families['pause']} upgrade={families['upgrade']}{flag}")

        controllers = read_controllers(w3, chain_id, addr, getters)
        for getter, (holder, label) in controllers.items():
            print(f"    {getter}() = {holder} [{label}]")

        role_members = read_role_members(w3, addr, array_getters)
        for getter, members in role_members.items():
            rendered = ", ".join(f"{m} [{label}]" for m, label in members)
            print(f"    {getter}() = [{rendered}]")

        if not controllers and not role_members:
            print("    no controller getter from the known list resolved on this token")
        bound = read_mint_bound(w3, chain_id, addr, fns)
        mint_unread += "UNREAD" in bound
        print(f"  mint bound: {bound}")

    print(f"\n{len(TRACKED_ASSETS)} distinct assets checked, {unread} unread; {mint_unread} mint bound(s) UNREAD (reported, not in the exit code).")
    return 1 if unread else 0


if __name__ == "__main__":
    sys.exit(main())
