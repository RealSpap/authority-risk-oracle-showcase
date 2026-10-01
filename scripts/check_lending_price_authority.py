#!/usr/bin/env python3
"""Who can move the PRICE a tracked lender uses, without a timelock? Read-only, disclosed only, never scored.

Why (2026-10-01, roadmap item R8): the oracle's oracleAuthorityScore says nothing about the lenders it tracks, and on
10 Mar 2026 an automated agent of Aave V3 Ethereum updated the wstETH CAPO adapter with no multisig and no timelock; the
snapshot ratio and timestamp ended up misaligned, the cap fell 2.85% under the live rate and about 27 M$ (some 10,938
wstETH, 34 accounts) were liquidated (governance.aave.com/t/post-mortem-exchange-rate-misallignment-on-wsteth-core-and-
prime-instances/24269). This lists, live, for Aave V3 Ethereum Core (the tracked `score_aave_v3_pool` target):

- every reserve, its price source (AaveOracle.getSourceOfAsset) and the value supplied (aToken supply x oracle price).
  A source that answers ACL_MANAGER() is an Aave adapter: its parameters are set by RISK_ADMIN or POOL_ADMIN holders of
  THAT ACLManager (not always the pool's own). Its kind comes from probes (LST CAPO: getSnapshotRatio; stable CAPO:
  getPriceCap; Pendle PT: discountRatePerYear; else its description()), and its setters from its code. A source that
  reverts on ACL_MANAGER() is an external feed (Chainlink and the like), out of scope here.
- for each gating ACLManager, the RISK_ADMIN and POOL_ADMIN holders (RoleGranted/RoleRevoked replayed from deployment,
  each confirmed by hasRole on two RPCs), what controls each one (Safe and owners, steward and its RISK_COUNCIL), and
  whether its code (behind one EIP-1967 hop) carries a call path to an adapter setter or a steward entry point.
- for a steward with a path and a council, its own limits (getRiskConfig) and, on the largest adapter of each kind it
  reaches, a harmful update SIMULATED by eth_call from the council's address, next to a harmless control update that
  must pass for the result to mean anything.

The path search is a heuristic: found = a code path exists, not found = no direct path seen (an executor of arbitrary
calls would be missed). A read that fails is printed UNREAD and never counted as zero. Nothing is sent, no key.

    python3 scripts/check_lending_price_authority.py
"""
import importlib.util
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor

from eth_abi import encode
from web3 import Web3

sys.path.insert(0, os.path.dirname(__file__))
from lib.scorers import _replay_role_holders  # noqa: E402
from lib.web3_utils import _is_revert, get_w3  # noqa: E402

RPCS = ["https://ethereum-rpc.publicnode.com", "https://eth.drpc.org"]
LOGS_RPC = "https://gateway.tenderly.co/public/mainnet"
PROVIDER = "0x2f39d218133AFaB8F2B819B1066c7E434Ad94E9e"  # Aave V3 Ethereum Core PoolAddressesProvider
ACL_START_BLOCK = 16_291_117  # ACLManager creation block (chains/ethereum-l1/scorers.py::_MAIN_POOL_ACL_START_BLOCK)
ADAPTER_SETTERS = ["setCapParameters((uint104,uint48,uint16))", "setPriceCap(int256)", "setDiscountRatePerYear(uint64)", "setPrice(int256)",
                   "setPriceCapRatio(int256)"]  # a closed list: no match means "no KNOWN setter", never "no setter"
STEWARD_ENTRIES = ["updateLstPriceCaps((address,(uint104,uint48,uint16))[])", "updateStablePriceCaps((address,uint256)[])",
                   "updatePendleDiscountRates((address,uint256)[])"]
IMPL_SLOT = 0x360894A13BA1A3210667C828492DB98DCA3E2076CC3735A920A3CA505D382BBC
ADMIN_SLOT = 0xB53127684A568B3173AE13B9F8A6016E243E63B6E8EE1178D6A717850B5D6103
BEACON_SLOT = 0xA3F0AD74E5423AEBFD80D3EF4346578335A9A72AEAEE59FF6CB3582CFB8BC3D0
LST, STABLE, PENDLE, RATIO = "LST CAPO", "stable CAPO", "Pendle PT discount", "ratio-capped adapter"


def selector(sig):
    return bytes(Web3.keccak(text=sig)[:4])


def _push(n):
    b = n.to_bytes(32, "big").lstrip(b"\0") or b"\0"
    return bytes([0x5F + len(b)]) + b


def push_bytes(sig):
    """The PUSHn instruction that puts this selector on the stack (a leading zero byte shortens it: PUSH3, not PUSH4)."""
    return _push(int.from_bytes(selector(sig), "big"))


def push_patterns(sig):
    """The ways solc puts a selector on the stack that this search knows: PUSHn sel; PUSH32 (sel << 224) (high optimizer
    runs); and, when the selector ends in k zero bits, PUSHn (sel >> k) PUSH1 (224 + k) SHL (via-IR constant optimizer).
    Added 2026-10-01 after a second review: the PendleDiscountRateAgent builds setDiscountRatePerYear calldata as
    PUSH4 20730b65 PUSH1 e2 SHL, and the first version, matching only the plain form, printed 'none seen' for it."""
    sel = int.from_bytes(selector(sig), "big")
    pats, k = [_push(sel), bytes([0x7F]) + selector(sig) + bytes(28)], 1
    while k <= 31 and (sel >> k) << k == sel:
        pats.append(_push(sel >> k) + bytes([0x60, 0xE0 + k, 0x1B]))
        k += 1
    return pats


def code_paths(code: bytes, sigs=ADAPTER_SETTERS + STEWARD_ENTRIES):
    """Names of the setters / steward entry points whose selector is put on the stack somewhere in this code."""
    return [s.split("(")[0] for s in sigs if any(p in code for p in push_patterns(s))]


def known_names():
    """The holder names the Ethereum scorer already keeps (one list, not a copy)."""
    path = os.path.join(os.path.dirname(__file__), "..", "chains", "ethereum-l1", "scorers.py")
    spec = importlib.util.spec_from_file_location("eth_l1_scorers_for_names", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod._MAIN_POOL_KNOWN_RISK_ADMIN


def fn(name, inputs=(), out="address"):
    return [{"name": name, "type": "function", "stateMutability": "view", "inputs": [{"type": t} for t in inputs],
             "outputs": [{"type": out}] if isinstance(out, str) else [{"type": t} for t in out]}]


def rpc(call, tries=3):
    """A raw RPC call (get_code, get_block, get_storage_at) with retries; raises after the last one (caller prints UNREAD)."""
    for attempt in range(tries):
        try:
            return call()
        except Exception:  # noqa: BLE001
            if attempt == tries - 1:
                raise
            time.sleep(1 + attempt)


def read(w3, address, name, *args, inputs=(), out="address"):
    """(value, ok): ok True on success, False when the contract itself says no (revert, no such function), None when
    the read failed (transport, rate limit) after 3 tries. Fixed 2026-10-01: a first version folded both into False, and
    one rate-limited probe on syrupUSDT ($114M) made a CAPO adapter look like a plain feed."""
    c = w3.eth.contract(address=Web3.to_checksum_address(address), abi=fn(name, inputs, out))
    for attempt in range(3):
        try:
            return getattr(c.functions, name)(*args).call(), True
        except Exception as e:  # noqa: BLE001
            if _is_revert(e):
                return None, False
            time.sleep(1 + attempt)
    return None, None


def two_rpcs(name, address, *args, inputs=(), out="address"):
    """(value, status): "ok" when both RPCs answer the same value, "absent" when both confirm a revert, "unread"
    otherwise (a failed read, a revert on one side only, or two different values). Fixed 2026-10-01 after review: a
    single None for all three let a failed RISK_COUNCIL read pass as 'no council' and skip the simulations silently."""
    vals = [read(get_w3(u), address, name, *args, inputs=inputs, out=out) for u in RPCS]
    if all(ok for _, ok in vals) and vals[0][0] == vals[1][0]:
        return vals[0][0], "ok"
    if all(ok is False for _, ok in vals):
        return None, "absent"
    return None, "unread"


def classify_source(acl, probes):
    """Kind of a price source from its probe results ({name: (value, ok)}). acl is the ACL_MANAGER() result."""
    if acl[1] is None:
        return "UNREAD"
    if acl[1] is False:
        return "external feed"
    for name, kind in (("getSnapshotRatio", LST), ("getPriceCap", STABLE), ("discountRatePerYear", PENDLE), ("getPriceCapRatio", RATIO)):
        if probes[name][1]:
            return kind
    if any(ok is None for _, ok in probes.values()):
        return "UNREAD"
    return f"other Aave adapter ({probes['description'][0] or 'no description'})"


def slot_address(w3, address, slot):
    raw = rpc(lambda: w3.eth.get_storage_at(Web3.to_checksum_address(address), slot))
    a = "0x" + bytes(raw)[-20:].hex()
    return Web3.to_checksum_address(a) if int(a, 16) else None


def logic_code(w3, address):
    """(code to search, note): the address's own runtime code, or its implementation's behind one EIP-1967 hop
    (implementation slot, else beacon). Fixed 2026-10-01 after review: two holders are proxies, and the stub alone was
    searched, so 'none seen' said nothing about them."""
    code = bytes(rpc(lambda: w3.eth.get_code(Web3.to_checksum_address(address))))
    impl = slot_address(w3, address, IMPL_SLOT)
    if impl is None:
        beacon = slot_address(w3, address, BEACON_SLOT)
        if beacon:
            impl, ok = read(w3, beacon, "implementation")
            if not ok:
                return code, f"beacon {beacon} implementation() UNREAD, proxy stub searched only"
    if impl is None:
        return code, ""
    admin = slot_address(w3, address, ADMIN_SLOT)
    impl_code = bytes(rpc(lambda: w3.eth.get_code(Web3.to_checksum_address(impl))))
    return impl_code, f"proxy -> implementation {impl} ({len(impl_code)} bytes), proxy admin {admin or 'none in slot'}"


def deploy_block(w3, address):
    """First block with code at `address`: binary search on an archive endpoint, so the role replay starts there, not at 0."""
    lo, hi = 0, rpc(lambda: w3.eth.block_number)
    while lo < hi:
        mid = (lo + hi) // 2
        if rpc(lambda: w3.eth.get_code(Web3.to_checksum_address(address), block_identifier=mid)):
            hi = mid
        else:
            lo = mid + 1
    return lo


def kind(w3, address, depth=1):
    """EOA / 7702 / Safe (owners' kinds `depth` levels down, and its modules) / other contract."""
    code = rpc(lambda: w3.eth.get_code(Web3.to_checksum_address(address)))
    if not code:
        return "bare EOA"
    if bytes(code[:3]) == b"\xef\x01\x00":
        return "EOA with an EIP-7702 delegation"
    owners, ok = read(w3, address, "getOwners", out="address[]")
    threshold, ok2 = read(w3, address, "getThreshold", out="uint256")
    if ok and ok2:
        inner = [f"{o} [{kind(w3, o, depth - 1)}]" if depth > 0 else o for o in owners]
        mods, ok3 = read(w3, address, "getModulesPaginated", "0x" + "00" * 19 + "01", 10, inputs=("address", "uint256"),
                         out=("address[]", "address"))
        modules = (f"modules {list(mods[0])}, authority not resolved past them" if ok3 and mods[0] else "no module" if ok3
                   else "modules UNREAD")  # a revert (an older Safe without getModulesPaginated) is not "no module"
        return f"Safe {threshold}-of-{len(owners)}, {modules}: owners {', '.join(inner)}"
    if None in (ok, ok2):
        return f"contract ({len(code)} bytes), Safe reads UNREAD"
    return f"contract ({len(code)} bytes)"


def steward_bounds(w3, steward):
    """The steward's own limits. getRiskConfig() of aave-dao/aave-v3-risk-stewards (src/interfaces/IRiskSteward.sol on main,
    read 2026-10-01) returns 15 static (minDelay, maxPercentChange) pairs in this order: collateral 3, eMode 3, rates 4,
    caps 2, then priceCapLst, priceCapStable, discountRatePendle. Any other length is a layout we do not know: UNREAD."""
    try:
        raw = rpc(lambda: w3.eth.call({"to": Web3.to_checksum_address(steward), "data": "0x" + selector("getRiskConfig()").hex()}))
    except Exception as e:  # noqa: BLE001
        return f"UNREAD (getRiskConfig: {'revert' if _is_revert(e) else type(e).__name__})"
    words = [int.from_bytes(raw[i:i + 32], "big") for i in range(0, len(raw), 32)]
    if len(words) != 30:
        return f"UNREAD (getRiskConfig returned {len(words)} words, layout unknown)"
    (d_lst, p_lst), (d_st, p_st), (d_pe, p_pe) = (words[24], words[25]), (words[26], words[27]), (words[28], words[29])
    return (f"LST: maxYearlyGrowth may move {p_lst / 100:g}% (relative) per update, one update per {d_lst / 86400:g} d per adapter, "
            f"snapshotRatio never above the live ratio, and no update may leave the price capped; stable: cap may move "
            f"{p_st / 100:g}% per update, one per {d_st / 86400:g} d; Pendle: discount rate may move {p_pe / 1e16:g} points "
            f"(absolute) per update, one per {d_pe / 86400:g} d")


def _sim(w3, steward, council, data):
    """True accepted, False the update path refused (revert), None the call itself failed."""
    try:
        rpc(lambda: w3.eth.call({"from": Web3.to_checksum_address(council), "to": Web3.to_checksum_address(steward), "data": "0x" + data.hex()}), tries=2)
        return True
    except Exception as e:  # noqa: BLE001
        return False if _is_revert(e) else None


def _verdict(control, attack, what):
    if control is None or attack is None:
        return "simulation UNREAD (call failed)"
    if not control:
        return "simulation INCONCLUSIVE: the control update was refused too (debounce, restriction or another rule)"
    return f"REFUSES {what} (simulated)" if not attack else f"ACCEPTS {what} (simulated)"


def simulate_lst(w3, steward, council, adapter):
    """Can the council, through this steward, set an LST cap that prices the asset at half its live rate right away?
    Control: a snapshot 0.01% under the live ratio, dated just past the adapter's minimum snapshot delay, must pass."""
    ratio, ok1 = read(w3, adapter, "getRatio", out="int256")
    delay, ok2 = read(w3, adapter, "MINIMUM_SNAPSHOT_DELAY", out="uint256")
    growth, ok3 = read(w3, adapter, "getMaxYearlyGrowthRatePercent", out="uint256")
    if not (ok1 and ok2 and ok3):
        return "simulation UNREAD (adapter reads failed)"
    try:
        ts = rpc(lambda: w3.eth.get_block("latest"))["timestamp"] - delay - 3600
    except Exception:  # noqa: BLE001
        return "simulation UNREAD (block read failed)"
    sel = selector(STEWARD_ENTRIES[0])

    def data(frac):
        return sel + encode(["(address,(uint104,uint48,uint16))[]"], [[(Web3.to_checksum_address(adapter), (int(ratio * frac), ts, growth))]])
    return _verdict(_sim(w3, steward, council, data(0.9999)), _sim(w3, steward, council, data(0.5)), "a cap at half the live rate")


def simulate_stable(w3, steward, council, adapter):
    """Can the council set a stable cap 10% under the current one in one update? Control: 0.1% under."""
    cap, ok = read(w3, adapter, "getPriceCap", out="int256")
    if not ok:
        return "simulation UNREAD (adapter read failed)"
    sel = selector(STEWARD_ENTRIES[1])

    def data(frac):
        return sel + encode(["(address,uint256)[]"], [[(Web3.to_checksum_address(adapter), int(cap * frac))]])
    return _verdict(_sim(w3, steward, council, data(0.999)), _sim(w3, steward, council, data(0.9)), "a cap 10% lower in one update")


def simulate_pendle(w3, steward, council, adapter):
    """Can the council raise a PT discount rate by 50 points in one update (a much lower PT price)? Control: +0.1 point."""
    rate, ok = read(w3, adapter, "discountRatePerYear", out="uint256")
    if not ok:
        return "simulation UNREAD (adapter read failed)"
    sel = selector(STEWARD_ENTRIES[2])

    def data(delta):
        return sel + encode(["(address,uint256)[]"], [[(Web3.to_checksum_address(adapter), rate + delta)]])
    return _verdict(_sim(w3, steward, council, data(10 ** 15)), _sim(w3, steward, council, data(5 * 10 ** 17)), "a discount 50 points higher in one update")


def replay_senders(logs):
    """Current authorized senders of a RiskOracle from AuthorizedSenderAdded/Removed logs, in chain order."""
    added, cur = bytes(Web3.keccak(text="AuthorizedSenderAdded(address)")), {}
    for lg in sorted(logs, key=lambda x: (x["blockNumber"], x["logIndex"])):
        word = bytes(lg["topics"][1]) if len(lg["topics"]) > 1 else bytes(lg["data"])[:32]
        cur[Web3.to_checksum_address(word[-20:])] = bytes(lg["topics"][0]) == added
    return sorted(a for a, on in cur.items() if on)


def describe_agent(w3, logs_w3, holder):
    """For a holder exposing AGENT_HUB() (an automated agent, the path of the March 2026 incident): its registration on the
    hub, the RiskOracle it executes and who may publish there, its range limits, and its last injected update per market.
    Added 2026-10-01 after the second review. Returns printable lines; any failed read is printed UNREAD."""
    hub, ok = read(w3, holder, "AGENT_HUB")
    if ok is not True:
        return [] if ok is False else ["AGENT_HUB() UNREAD"]
    n, ok = read(w3, hub, "getAgentCount", out="uint256")
    if not ok:
        return [f"agent of AgentHub {hub}: getAgentCount() UNREAD"]
    owner, ok_o = read(w3, hub, "owner")
    lines = [f"agent of AgentHub {hub} (owner {owner if ok_o else 'UNREAD'}, {n} agents registered)"]
    rm, _ = read(w3, holder, "RANGE_VALIDATION_MODULE")
    for i in range(n):
        addr, ok = read(w3, hub, "getAgentAddress", i, inputs=("uint256",))
        if ok is None:
            lines.append(f"agent id {i}: getAgentAddress UNREAD, registration not known")
            continue
        if not ok or addr.lower() != holder.lower():
            continue
        q = {k: read(w3, hub, k, i, inputs=("uint256",), out=o) for k, o in (
            ("isAgentEnabled", "bool"), ("isAgentPermissioned", "bool"), ("getRiskOracle", "address"), ("getUpdateType", "string"),
            ("getMinimumDelay", "uint256"), ("getAllowedMarkets", "address[]"), ("isMarketsFromAgentEnabled", "bool"))}
        if any(ok is not True for _, ok in q.values()):
            lines.append(f"agent id {i}: hub reads UNREAD ({[k for k, (_, ok) in q.items() if ok is not True]})")
            continue
        v = {k: val for k, (val, _) in q.items()}
        admin, ok_a = read(w3, hub, "getAgentAdmin", i, inputs=("uint256",))
        try:
            admin_kind = kind(w3, admin, 0) if ok_a else "UNREAD"
        except Exception as e:  # noqa: BLE001
            admin_kind = f"UNREAD ({type(e).__name__})"
        lines.append(f"agent id {i}: admin {admin if ok_a else 'UNREAD'} [{admin_kind}] (may change its markets, delay, range and "
                     "enabled flag, no timelock)")
        lines.append(f"agent id {i}: enabled={v['isAgentEnabled']}, " + ("only permissioned senders may trigger it" if v["isAgentPermissioned"]
                     else "ANYONE may trigger it") + f", update type '{v['getUpdateType']}', min delay {v['getMinimumDelay'] / 86400:g} d, "
                     + ("markets taken from the agent" if v["isMarketsFromAgentEnabled"] else f"{len(v['getAllowedMarkets'])} allowed market(s)"))
        oracle = v["getRiskOracle"]
        desc, ok_d = read(w3, oracle, "description", out="string")
        desc = desc if ok_d else "description UNREAD"
        ro_owner, _ = read(w3, oracle, "owner")
        try:
            senders = replay_senders(logs_w3.eth.get_logs({"address": Web3.to_checksum_address(oracle), "fromBlock": 0, "toBlock": "latest", "topics": [[
                Web3.keccak(text="AuthorizedSenderAdded(address)"), Web3.keccak(text="AuthorizedSenderRemoved(address)")]]}))
            confirmed = [s for s in senders if read(w3, oracle, "isAuthorized", s, inputs=("address",), out="bool")[0] is True]
            who = "NONE replayed: an anomaly, not 'nobody'" if not senders else ", ".join(
                f"{s} [{kind(w3, s, 0)}]" + ("" if s in confirmed else " (isAuthorized not confirmed)") for s in senders)
        except Exception as e:  # noqa: BLE001
            who = f"UNREAD ({type(e).__name__})"
        try:
            owner_kind = kind(w3, ro_owner, 0) if ro_owner else "UNREAD"
        except Exception as e:  # noqa: BLE001
            owner_kind = f"UNREAD ({type(e).__name__})"
        lines.append(f"   executes RiskOracle {oracle} '{desc}', owner {ro_owner or 'UNREAD'} [{owner_kind}], authorized senders: {who} "
                     "(replayed from events: a sender set in the constructor emits none and is not covered)")
        for m in v["getAllowedMarkets"]:
            sym, _ = read(w3, m, "symbol", out="string")
            last, ok_last = read(w3, hub, "getLastInjectedUpdate", i, m, inputs=("uint256", "address"), out=("uint256", "uint256"))
            rc, ok_rc = (read(w3, rm, "getRangeConfigByMarket", hub, i, m, v["getUpdateType"], inputs=("address", "uint256", "address", "string"),
                              out=("uint120", "uint120", "bool", "bool")) if rm else (None, None))
            dc, ok_dc = (read(w3, rm, "getDefaultRangeConfig", hub, i, v["getUpdateType"], inputs=("address", "uint256", "string"),
                              out=("uint120", "uint120", "bool", "bool")) if rm else (None, None))
            inj = "UNREAD" if not ok_last else "never" if last[0] == 0 else f"update #{last[1]} at {last[0]}"
            rng = "UNREAD" if not (ok_rc and ok_dc) else (f"market {rc}, default {dc}" + "  (maxIncrease, maxDecrease, increase relative?, decrease relative?)")
            lines.append(f"   market {m} {sym or ''}: last injected {inj}; range {rng}")
    return lines


SIMULATIONS = {LST: ("updateLstPriceCaps", simulate_lst), STABLE: ("updateStablePriceCaps", simulate_stable),
               PENDLE: ("updatePendleDiscountRates", simulate_pendle)}


def main():
    w3 = get_w3(RPCS[0])
    (pool, s1), (oracle, s2), (acl, s3) = (two_rpcs(n, PROVIDER) for n in ("getPool", "getPriceOracle", "getACLManager"))
    if (s1, s2, s3) != ("ok", "ok", "ok"):
        raise SystemExit("PoolAddressesProvider reads UNREAD on two RPCs: no conclusion")
    reserves, ok = read(w3, pool, "getReservesList", out="address[]")
    if not ok:
        raise SystemExit("getReservesList UNREAD: no conclusion")

    def reserve(asset):
        src, ok_src = read(w3, oracle, "getSourceOfAsset", asset, inputs=("address",))
        price, _ = read(w3, oracle, "getAssetPrice", asset, inputs=("address",), out="uint256")
        data, _ = read(w3, pool, "getReserveData", asset, inputs=("address",),
                       out=("uint256", "uint128", "uint128", "uint128", "uint128", "uint128", "uint40", "uint16", "address", "address",
                            "address", "address", "uint128", "uint128", "uint128"))
        sym, _ = read(w3, asset, "symbol", out="string")
        dec, _ = read(w3, asset, "decimals", out="uint8")
        supply = None
        if data and price is not None and dec is not None:
            ts, ok_ts = read(w3, data[8], "totalSupply", out="uint256")
            supply = ts * price / 1e8 / 10 ** dec if ok_ts else None
        row = {"asset": asset, "symbol": sym or asset[:10], "source": src, "kind": "UNREAD", "acl": None, "setters": [], "supplyUsd": supply}
        if not ok_src:
            return row
        acl_r = read(w3, src, "ACL_MANAGER")
        probes = {n: read(w3, src, n, out=o) for n, o in (("getSnapshotRatio", "uint256"), ("getPriceCap", "int256"),
                                                          ("discountRatePerYear", "uint256"), ("getPriceCapRatio", "int256"),
                                                          ("description", "string"))}
        row["kind"], row["acl"] = classify_source(acl_r, probes), acl_r[0]
        if row["acl"]:
            try:
                row["setters"] = code_paths(bytes(rpc(lambda: w3.eth.get_code(Web3.to_checksum_address(src)))), ADAPTER_SETTERS)
            except Exception:  # noqa: BLE001
                row["setters"] = ["UNREAD"]
        return row

    with ThreadPoolExecutor(6) as ex:
        rows = sorted(ex.map(reserve, reserves), key=lambda r: -(r["supplyUsd"] or 0))
    adapters = [r for r in rows if r["acl"]]
    total = sum(r["supplyUsd"] or 0 for r in rows)
    print(f"Aave V3 Ethereum Core: {len(rows)} reserves, ${total / 1e9:.2f}B supplied")
    for k in sorted({r["kind"] for r in rows}):
        group = [r for r in rows if r["kind"] == k]
        srcs = len({r["source"] for r in group})
        print(f"   {k}: {len(group)} reserves on {srcs} sources, ${sum(r['supplyUsd'] or 0 for r in group) / 1e9:.3f}B")
    unread_value = [r["symbol"] for r in rows if r["supplyUsd"] is None]
    if unread_value:
        print(f"   value UNREAD (counted as 0 in the sums above, listed here): {unread_value}")
    print("\nReserves priced by an Aave adapter (parameters set by the gating ACLManager's RISK_ADMIN or POOL_ADMIN):")
    for r in adapters:
        gate = "" if r["acl"].lower() == acl.lower() else f"  gated by ACLManager {r['acl']}"
        print(f"   {r['symbol']:<20} {r['kind'][:40]:<40} ${(r['supplyUsd'] or 0) / 1e6:9,.1f}M  setters {r['setters'] or 'no known setter selector'}"
              f"  source {r['source']}{gate}")

    names, logs_w3 = known_names(), get_w3(LOGS_RPC)
    for gate in sorted({r["acl"] for r in adapters}, key=lambda a: a.lower() != acl.lower()):
        gated = [r for r in adapters if r["acl"] == gate]
        print(f"\nACLManager {gate}: gates {len(gated)} Core reserves on {len({r['source'] for r in gated})} adapters, "
              f"${sum(r['supplyUsd'] or 0 for r in gated) / 1e6:,.0f}M supplied")
        try:
            start = ACL_START_BLOCK if gate.lower() == acl.lower() else deploy_block(logs_w3, gate)
            roles = _replay_role_holders(logs_w3, gate, ["RISK_ADMIN", "POOL_ADMIN"], start_block=start)
        except Exception as e:  # noqa: BLE001
            print(f"   role replay UNREAD ({type(e).__name__}): who can move these prices is not known")
            continue
        if not roles["POOL_ADMIN"]:
            print(f"   no POOL_ADMIN grant replayed from block {start}: an ANOMALY (a live pool has one), the list below is not trusted")
        for role in ("RISK_ADMIN", "POOL_ADMIN"):
            for h in sorted(roles[role]):
                live, st = two_rpcs("hasRole", gate, Web3.keccak(text=role), h, inputs=("bytes32", "address"), out="bool")
                if live is not True:
                    print(f"   {role} {h}: " + ("replay says holder, hasRole false on both RPCs: ANOMALY, this list is not trusted"
                                                   if st == "ok" else "hasRole UNREAD"))
                    continue
                name = names.get(h.lower(), "(unnamed)") if gate.lower() == acl.lower() and role == "RISK_ADMIN" else "(unnamed)"
                try:
                    code, proxy = logic_code(w3, h)
                    paths, what = code_paths(code), kind(w3, h)
                except Exception as e:  # noqa: BLE001
                    print(f"   {role} {h} {name}: code UNREAD ({type(e).__name__})")
                    continue
                council, cst = two_rpcs("RISK_COUNCIL", h)
                line = f"   {role} {h} {name}: {what}" + (f"; {proxy}" if proxy else "")
                if cst == "ok":
                    try:
                        line += f"; RISK_COUNCIL {council} ({kind(w3, council)})"
                    except Exception as e:  # noqa: BLE001
                        line += f"; RISK_COUNCIL {council} (kind UNREAD: {type(e).__name__})"
                elif cst == "unread" and paths:
                    line += "; RISK_COUNCIL UNREAD (bounds and simulations not run)"
                print(line + f"; setter path in code: {', '.join(paths) if paths else 'none seen'}")
                for agent_line in describe_agent(w3, logs_w3, h):
                    print(f"      {agent_line}")
                if cst != "ok" or not paths:
                    continue
                print(f"      bounds {steward_bounds(w3, h)}")
                for k, (entry, sim) in SIMULATIONS.items():
                    target = next((r for r in gated if r["kind"] == k), None)
                    if target and entry in paths:
                        print(f"      {target['symbol']}: {sim(w3, h, council, target['source'])}")
    print("\nDisclosed only: no score reads this. The simulations are eth_call from the council's address: nothing is sent.")


if __name__ == "__main__":
    main()
