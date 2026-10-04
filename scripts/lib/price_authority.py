"""oracleAuthorityScore for a price CONSUMER (METHODOLOGY.md, "oracleAuthorityScore for price consumers", decided by Spap on
2026-10-04 after data/finding_2026-10-01-aave-capo-price-authority.md and its 2026-10-04 addendum).

    oracleAuthorityScore = min, over the MATERIAL price paths ONE HOP upstream, of each path's own composite

- MATERIAL: the path reaches at least MATERIALITY (1%) of the target's priced supply. A row whose value is UNREAD counts as
  material (fail-closed).
- ONE HOP: the walk goes THROUGH the target's own price contracts (an Aave adapter whose ACL_MANAGER() is the target's
  ACLManager; a wrapper whose manager() is the target's governor) and through PROVABLY IMMUTABLE wrappers (no proxy slot,
  no storage write, no DELEGATECALL), and stops at the first contract someone else controls: a Chainlink proxy, a rate
  provider, an upgradeable feed. A wrapper that is neither is UNREAD. An own adapter with no known upstream getter is UNREAD
  unless a spec names it as own configuration. That contract is scored by who can change what IT
  reports. Its own inputs (Stader behind rsETH, L1 cbETH behind a Base exchange-rate feed) are disclosed, not scored
  (decided 2026-10-04).
- The target's own config path is already in compositeScore and is not scored again.
- A path is DISCLOSED, not scored, when it is provably bounded (a verified spec, re-checked live), when it sits behind a
  timelock at least as long as the target's own governance delay ("governance-grade"), or when the contract is a provable
  constant (no SSTORE, CALL, STATICCALL, DELEGATECALL, CALLCODE or SELFDESTRUCT, no proxy slot).
- A Safe with no timelock scores _safe_rooted_scores(threshold, n); a bare EOA scores (5, 0, 0).
- A material path that cannot be read is UNREAD and the target scores at most UNKNOWN_SCORE (20), never 100. No material
  path: 100 (not applicable).

Every read is live. A spec names what to check and which answer keeps the classification; any other answer is UNREAD.
The walk follows the getters it knows (FEED_GETTERS, RATE_GETTERS): an input a wrapper reads through any other getter is
not seen.
"""
from web3 import Web3

try:  # loaded as lib.price_authority (Robinhood scorers) or as a bare module (chain scorers put scripts/lib on sys.path)
    from . import web3_utils as _wu
    from .web3_utils import call_raw, safe_owners_and_threshold
except ImportError:
    import web3_utils as _wu
    from web3_utils import call_raw, safe_owners_and_threshold

MATERIALITY = 0.01
UNKNOWN_SCORE = 20
UNREAD_MARK = "material price path(s) UNREAD"  # push_guard holds an entry whose notes carry it and whose value moved
FAILED_MARK = "price walk failed"
FEED_GETTERS = ("BASE_TO_USD_AGGREGATOR", "ASSET_TO_USD_AGGREGATOR", "ASSET_TO_PEG", "PEG_TO_BASE",  # Aave adapters
                "assetToBaseAggregator", "underlyingPriceFeed", "WBTCToBTCPriceFeed", "BTCToUSDPriceFeed",  # Compound feeds
                "priceFeedA", "priceFeedB", "source",  # Compound/Monad wrappers
                "BASE_FEED_1", "BASE_FEED_2", "QUOTE_FEED_1", "QUOTE_FEED_2")  # MorphoChainlinkOracleV2
RATE_GETTERS = ("RATIO_PROVIDER", "ratioProvider", "BASE_VAULT", "QUOTE_VAULT")
IMPL_SLOT = 0x360894A13BA1A3210667C828492DB98DCA3E2076CC3735A920A3CA505D382BBC
ADMIN_SLOT = 0xB53127684A568B3173AE13B9F8A6016E243E63B6E8EE1178D6A717850B5D6103
BEACON_SLOT = 0xA3F0AD74E5423AEBFD80D3EF4346578335A9A72AEAEE59FF6CB3582B35133D50  # keccak("eip1967.proxy.beacon") - 1
ZEPPELIN_IMPL_SLOT = 0x7050C9E0F4CA769C69BD3A8EF740BC37934F8E2C036E5A723FD8EE048ED3F8C3  # keccak("org.zeppelinos.proxy.implementation")
ZEPPELIN_ADMIN_SLOT = 0x10D6A54A4754C8869D6886B5F5D7FBFA5B4522237EA5C60D11BC4E7A1FF9390B  # keccak("org.zeppelinos.proxy.admin"), FiatToken
PROXY_SLOTS = (IMPL_SLOT, ADMIN_SLOT, BEACON_SLOT, ZEPPELIN_IMPL_SLOT, ZEPPELIN_ADMIN_SLOT)
DELEGATION = b"\xef\x01\x00"  # EIP-7702: the account's code is this prefix and the delegate's address
_ADDR = lambda name, *ins: [{"name": name, "type": "function", "stateMutability": "view", "inputs": [{"type": t} for t in ins], "outputs": [{"type": "address"}]}]  # noqa: E731
_UINT = lambda name, *ins: [{"name": name, "type": "function", "stateMutability": "view", "inputs": [{"type": t} for t in ins], "outputs": [{"type": "uint256"}]}]  # noqa: E731
_BOOL = lambda name, *ins: [{"name": name, "type": "function", "stateMutability": "view", "inputs": [{"type": t} for t in ins], "outputs": [{"type": "bool"}]}]  # noqa: E731


def composite(admin, multisig, timelock):
    return (4 * admin + 3 * multisig + 3 * timelock + 5) // 10


def _safe_rooted(threshold, n):
    """Same convention as scripts/lib/scorers.py::_safe_rooted_scores (Safe at the root, no timelock above it); a unit test
    pins the two together."""
    admin = 65 if threshold >= 3 else (50 if threshold == 2 else 10)
    return admin, min(100, threshold * 15 + max(0, n - threshold) * 5), 0


def _addr(w3, address, name, *args, ins=()):
    v = call_raw(w3, address, _ADDR(name, *ins), name, *args, retries=2)
    return Web3.to_checksum_address(v) if v and int(v, 16) else None


def _eth(fn, what):
    """A direct node read (code, storage, logs, block number) with the same retries as call_raw; these cannot revert, so
    any failure retries and then raises (RpcUnavailable), never becomes an empty value."""
    return _wu._read(fn, 4, what=what, classify=lambda _: False)


def _slot(w3, address, slot):
    a = Web3.to_checksum_address(address)
    raw = bytes(_eth(lambda: w3.eth.get_storage_at(a, slot), f"storage {hex(slot)} of {a}"))[-20:]
    return Web3.to_checksum_address("0x" + raw.hex()) if int.from_bytes(raw, "big") else None


def path(label, status, composite_=None, note="", controller=None):
    return {"label": label, "status": status, "composite": composite_, "note": note, "controller": controller}


def _code(w3, address):
    a = Web3.to_checksum_address(address)
    return bytes(_eth(lambda: w3.eth.get_code(a), f"code of {a}"))


def _admin_slot(w3, address):
    return _slot(w3, address, ADMIN_SLOT) or _slot(w3, address, ZEPPELIN_ADMIN_SLOT)


_SOLC = b"\x64solc\x43"  # "solc": 3-byte version


def _is_metadata(t):
    """True when `t` is exactly one of the compiler metadata maps: solc ipfs (with or without the experimental flag),
    solc bzzr0 / bzzr1, or old Vyper. Any other byte sequence is scanned as code."""
    ipfs = b"\x64ipfs\x58\x22"
    shapes = ((b"\xa2" + ipfs, 34, _SOLC, 3, b""), (b"\xa3" + ipfs, 34, b"\x6cexperimental", 1, _SOLC),
              (b"\xa1\x65bzzr0\x58\x20", 32, b"", 0, b""), (b"\xa2\x65bzzr1\x58\x20", 32, _SOLC, 3, b""))
    for head, h, mid, m, tail in shapes:
        size = len(head) + h + len(mid) + m + (len(tail) + 3 if tail else 0)
        if len(t) == size and t.startswith(head) and t[len(head) + h:].startswith(mid) and t[len(t) - (len(tail) + 3):].startswith(tail):
            return True
    return len(t) == 11 and t.startswith(b"\xa1\x65vyper\x83")


def _jumped_into(code, start):
    """True when a JUMPDEST lies inside the trailer and some PUSH constant of the code before it equals its offset: code
    that jumps into its own 'metadata'. A target computed at run time is not seen (a crafted contract, not a compiler's)."""
    i, dests, pushed = 0, set(), set()
    while i < len(code):
        op = code[i]
        if op == 0x5B and i >= start:
            dests.add(i)
        if 0x60 <= op <= 0x7F:
            if i < start:
                pushed.add(int.from_bytes(code[i + 1:i + op - 0x5E], "big"))
            i += op - 0x5F + 1
            continue
        i += 1
    return bool(dests & pushed)


def _no_opcode(code, banned):
    """True when no opcode in `banned` appears in the runtime code (PUSH data skipped). A compiler metadata trailer (exactly
    a solc ipfs / bzzr or old Vyper map, after a STOP or INVALID byte, that no PUSH constant of the code jumps into) is cut
    off so its hash bytes are not read as opcodes; anything else is scanned, so a stray byte can only give a false 'not
    constant' (UNREAD)."""
    n = int.from_bytes(code[-2:], "big") if len(code) >= 2 else 0
    start = len(code) - n - 2
    if 0 < n and start > 0 and code[start - 1] in (0x00, 0xFE) and _is_metadata(code[start:-2]) and not _jumped_into(code, start):
        code = code[:start]
    i = 0
    while i < len(code):
        op = code[i]
        if 0x60 <= op <= 0x7F:
            i += op - 0x5F + 1
            continue
        if op in banned:
            return False
        i += 1
    return True


def _fixed_code(w3, address):
    """The runtime code when it is plain contract code with no proxy slot set, else None (an EOA, an EIP-7702 account or a
    proxy: what it runs can change)."""
    code = _code(w3, address)
    if not code or code[:3] == DELEGATION or any(_slot(w3, address, s) for s in PROXY_SLOTS):
        return None
    return code


# State a key holder or any caller can move without a storage write of the contract itself: balances (anyone can donate),
# other accounts' code (an EIP-7702 account re-delegates), transient storage (set earlier in the same transaction).
# EXTCODESIZE is left out here: Solidity before 0.8.10 checks it before every external call; a constant bans it below.
# So are TIMESTAMP and NUMBER: fixed-price feeds report updatedAt = block.timestamp, which nobody chooses.
_OUTSIDE_STATE = (0x31, 0x47, 0x3C, 0x3F, 0x5C, 0x5D,  # BALANCE, SELFBALANCE, EXTCODECOPY, EXTCODEHASH, TLOAD, TSTORE
                  0x3A, 0x40, 0x41, 0x44, 0x45, 0x48, 0x4A)  # GASPRICE, BLOCKHASH, COINBASE, PREVRANDAO, GASLIMIT, BASEFEE, BLOBBASEFEE
_WRITES = (0x55, 0xF2, 0xF4, 0xFF)  # SSTORE, CALLCODE, DELEGATECALL, SELFDESTRUCT


def is_provable_constant(w3, address):
    """True when the runtime code holds no storage write, no call of any kind, no read of state outside its own code
    (balances, other code, transient storage, ORIGIN, CALLER, gas or block-builder values) and no proxy slot is set:
    whatever it reports, nobody can change it."""
    code = _fixed_code(w3, address)
    return code is not None and _no_opcode(code, _WRITES + _OUTSIDE_STATE + (0xF1, 0xFA, 0x3B, 0x32, 0x33, 0x5A))  # + calls, EXTCODESIZE, ORIGIN, CALLER, GAS


def is_immutable_wrapper(w3, address):
    """True when the code can read other contracts (CALL, STATICCALL) but writes no storage, makes no DELEGATECALL or
    CALLCODE, cannot SELFDESTRUCT, reads no balance, foreign code or transient storage, and no proxy slot is set: nobody
    can change which contracts it reads or how it combines them."""
    code = _fixed_code(w3, address)
    return code is not None and _no_opcode(code, _WRITES + _OUTSIDE_STATE)


def controller_path(w3, address, governance_delay, label, depth=0):
    """Score the account that controls a contract: bare EOA (5, 0, 0); Safe -> _safe_rooted; a timelock whose delay is at
    least the target's governance delay -> governance-grade; a contract with owner()/admin() -> followed (2 hops);
    anything else UNREAD."""
    if address is None:
        return path(label, "UNREAD", note="controller unread")
    code = _code(w3, address)
    if not code:
        return path(label, "scored", composite(5, 0, 0), f"{address}: bare EOA, no delay", address)
    if code[:3] == DELEGATION:
        return path(label, "scored", composite(5, 0, 0), f"{address}: EOA with an EIP-7702 delegation, one key", address)
    # The Safe authority gate logs its module/singleton findings for the entry being scored; these belong to this price
    # path, not to the consumer's own Safe, so they are taken out of the shared log and kept in this path's note.
    log = _wu._AUTHORITY_GATE_LOG
    mark = len(log)
    try:
        safe = safe_owners_and_threshold(w3, address)
    finally:  # also when the read raises: the events never reach the consumer's notes
        gate = [f"{kind}: {text}" for _, kind, text in log[mark:]]
        del log[mark:]
    if safe:
        owners, t = safe
        return path(label, "scored", composite(*_safe_rooted(t, len(owners))), f"{address}: Safe {t}-of-{len(owners)}, no timelock above it"
                    + (f"; Safe gate: {gate}" if gate else ""), address)
    if any(g.startswith("blocking") for g in gate):
        return path(label, "UNREAD", note=f"{address}: Safe with an unanalyzed module or singleton: {gate}", controller=address)
    for getter in ("getMinDelay", "delay"):
        d = call_raw(w3, address, _UINT(getter), getter, retries=2)
        if d is not None:
            if governance_delay and d >= governance_delay:  # a target with no delay of its own gives no governance-grade bar
                return path(label, "governance-grade", note=f"{address}: timelock {getter}() = {d}s >= the target's governance delay {governance_delay}s", controller=address)
            return path(label, "UNREAD", note=f"{address}: timelock {getter}() = {d}s, below the target's governance delay ({governance_delay}); its proposers are not resolved", controller=address)
    if depth < 2:
        for getter in ("owner", "admin"):
            up = _addr(w3, address, getter)
            if up:
                return controller_path(w3, up, governance_delay, f"{label} -> {getter}()", depth + 1)
    return path(label, "UNREAD", note=f"{address}: contract ({len(code)} bytes), neither EOA, resolvable Safe, timelock nor owned contract", controller=address)


AAVE_FEED_GETTERS = FEED_GETTERS[:4]


def walk_source(w3, source, specs, own, depth=0, memo=None):
    """Leaves one hop upstream of a price source: ('chainlink', proxy), ('spec', addr), ('controller-of', addr),
    ('rate', addr) or ('unread', addr, why). `own`: lowercase addresses of the target's own governance (a wrapper whose
    manager() is one of them is the target's own contract)."""
    memo = {} if memo is None else memo
    if source.lower() in memo:
        return memo[source.lower()]
    if depth > 5:
        return [("unread", source, "walk deeper than 5 hops")]
    memo[source.lower()] = leaves = _walk(w3, source, specs, own, depth, memo)
    return leaves


def _walk(w3, source, specs, own, depth, memo):
    if source.lower() in specs:
        return [("spec", source)]
    code = _code(w3, source)
    if not code or code[:3] == DELEGATION:
        return [("key", source)]  # an EOA or an EIP-7702 account answering for a price: whoever holds the key sets it
    if _addr(w3, source, "aggregator"):
        return [("chainlink", source)]
    acl = _addr(w3, source, "ACL_MANAGER")
    if acl and acl.lower() not in own:  # an Aave-style adapter governed by another ACLManager than the target's
        return [("unread", source, f"adapter governed by a foreign ACLManager {acl}: its admins are not resolved")]
    manager = None if acl else _addr(w3, source, "manager")
    is_own = acl is not None or (manager is not None and manager.lower() in own)
    # An Aave adapter only exposes the Aave getters: fewer calls, fewer rate-limit failures on public RPCs.
    feeds = [a for a in (_addr(w3, source, g) for g in (AAVE_FEED_GETTERS if acl else FEED_GETTERS)) if a and a.lower() != source.lower()]
    rates = [a for a in (_addr(w3, source, g) for g in (("RATIO_PROVIDER",) if acl else RATE_GETTERS)) if a]
    leaves = []
    if not is_own:
        if _addr(w3, source, "owner") or _admin_slot(w3, source) or _slot(w3, source, BEACON_SLOT) or manager:
            leaves.append(("controller-of", source))
        elif (feeds or rates) and not is_immutable_wrapper(w3, source):
            leaves.append(("unread", source, "wrapper with no owner(), admin slot or manager() that is not provably immutable "
                                             "(a proxy slot, a storage write or a DELEGATECALL): who can change it is not resolved"))
    for f in dict.fromkeys(feeds):
        leaves += walk_source(w3, f, specs, own, depth + 1, memo)
    for r in dict.fromkeys(rates):  # a rate provider that is itself a Chainlink proxy (L2 exchange-rate feeds) is one
        leaves.append(("spec", r) if r.lower() in specs else ("chainlink", r) if _addr(w3, r, "aggregator") else ("rate", r))
    if not feeds and not rates:
        if is_own:  # an own adapter whose input this walk cannot see: unknown, unless a spec names it as own configuration
            return [("unread", source, "own adapter with no known upstream getter")]
        if not leaves:
            if is_provable_constant(w3, source):
                return [("constant", source)]
            return [("unread", source, "no aggregator(), no known upstream getter, no controller, not a provable constant")]
    return leaves


def chainlink_path(w3, proxy, governance_delay):
    """proposeAggregator/confirmAggregator are onlyOwner with no delay (EACAggregatorProxy source, read 2026-10-04), and the
    aggregator's owner can setConfig: owner() of both."""
    owner = _addr(w3, proxy, "owner")
    agg = _addr(w3, proxy, "aggregator")
    agg_owner = _addr(w3, agg, "owner") if agg else None
    paths = [controller_path(w3, owner, governance_delay, f"Chainlink proxy {proxy} owner (instant aggregator swap)")]
    admin = _admin_slot(w3, proxy)  # an EACAggregatorProxy has none; anything answering aggregator() that is a proxy does
    if admin:
        paths.append(controller_path(w3, admin, governance_delay, f"{proxy} proxy admin slot (upgrade)"))
    beacon = _slot(w3, proxy, BEACON_SLOT)
    if beacon:
        paths.append(controller_path(w3, _addr(w3, beacon, "owner"), governance_delay, f"{proxy} beacon {beacon} owner()"))
    if agg_owner and (not owner or agg_owner.lower() != owner.lower()):
        paths.append(controller_path(w3, agg_owner, governance_delay, f"aggregator {agg} owner (setConfig)"))
    elif agg and not agg_owner and not is_provable_constant(w3, agg):
        paths.append(path(f"aggregator {agg}", "UNREAD", note="aggregator without a readable owner(): who can change its answer is not resolved"))
    return paths


def controller_of_path(w3, contract, governance_delay):
    """A contract the target reads that someone other than the target controls: score its owner(), EIP-1967 admin and
    manager() (an upgradeable RedStone feed behind a ProxyAdmin, for instance)."""
    paths = []
    beacon = _slot(w3, contract, BEACON_SLOT)
    for label, ctrl in (("owner()", _addr(w3, contract, "owner")), ("proxy admin slot", _admin_slot(w3, contract)),
                        ("manager()", _addr(w3, contract, "manager"))):
        if ctrl:
            paths.append(controller_path(w3, ctrl, governance_delay, f"{contract} {label}"))
    if beacon:  # whoever owns the beacon swaps the implementation
        paths.append(controller_path(w3, _addr(w3, beacon, "owner"), governance_delay, f"{contract} beacon {beacon} owner()"))
    return paths or [path(f"{contract}", "UNREAD", note="controller vanished between reads")]


def score(w3, rows, governance_delay, specs=None, own=(), notes=None):
    """rows: [(label, price source or None, value or None)]. specs: {address lowercase: fn(w3, governance_delay) -> [path]}.
    own: addresses of the target's own governance. Returns the score and appends one note per path."""
    specs = {k.lower(): v for k, v in (specs or {}).items()}
    own = {a.lower() for a in own}
    notes = [] if notes is None else notes
    total = sum(v for _, _, v in rows if v)
    by_key, reach, unknown_value, cache, memo = {}, {}, {}, {}, {}
    for label, source, value in rows:
        if source is None:
            leaves = [("unread", label, "price source unread")]
        else:
            if source.lower() not in cache:
                cache[source.lower()] = walk_source(w3, source, specs, own, memo=memo)
            leaves = cache[source.lower()]
        for leaf in dict.fromkeys(tuple(x) for x in leaves):
            key = leaf[:2]
            if key not in by_key:
                kind, addr = leaf[0], leaf[1]
                if kind == "chainlink":
                    by_key[key] = chainlink_path(w3, addr, governance_delay)
                elif kind == "key":
                    by_key[key] = [controller_path(w3, addr, governance_delay, f"price source {addr} is an account, not a contract")]
                elif kind == "spec":
                    by_key[key] = specs[addr.lower()](w3, governance_delay)
                elif kind == "controller-of":
                    by_key[key] = controller_of_path(w3, addr, governance_delay)
                elif kind == "constant":
                    by_key[key] = [path(f"{addr}", "constant", note="provable constant: no storage write, no call, no outside state read, no proxy slot")]
                elif kind == "rate":
                    by_key[key] = [path(f"rate provider {addr}", "UNREAD", note="no verified spec: who sets its rate is not established")]
                else:
                    by_key[key] = [path(f"source {addr}", "UNREAD", note=leaf[2])]
            reach[key] = reach.get(key, 0) + (value or 0)
            unknown_value[key] = unknown_value.get(key, False) or value is None
    scored, unread = [], []
    for key, paths in by_key.items():
        share = reach[key] / total if total else 0
        material = share >= MATERIALITY or unknown_value[key]
        for p in paths:
            notes.append(f"price path {p['label']}: {p['status']}" + (f", composite {p['composite']}" if p["composite"] is not None else "")
                         + f", reach {share:.2%}{'' if material else ' (immaterial)'}" + (f" -- {p['note']}" if p["note"] else ""))
            if material and p["status"] == "scored":
                scored.append(p["composite"])
            elif material and p["status"] == "UNREAD":
                unread.append(p["label"])
    if unread:
        result = min([UNKNOWN_SCORE] + scored)
        notes.append(f"oracleAuthorityScore {result}: {UNREAD_MARK} {unread} -- unknown, not 100")
        return result
    if not scored:
        notes.append("oracleAuthorityScore 100: no material price path one hop upstream that can move a price without a proven bound")
        return 100
    result = min(scored)
    notes.append(f"oracleAuthorityScore {result} = min over material price paths one hop upstream (METHODOLOGY, rule of 2026-10-04)")
    return result


# ------------------------------------------------------------------------------------------------- row builders
def aave_rows(w3, provider):
    """[(asset, source, usd)] for every reserve of an Aave V3 instance (AaveOracle.getSourceOfAsset, aToken supply x price)."""
    pool = _addr(w3, provider, "getPool")
    oracle = _addr(w3, provider, "getPriceOracle")
    if not pool or not oracle:
        return None
    reserves = call_raw(w3, pool, [{"name": "getReservesList", "type": "function", "stateMutability": "view", "inputs": [],
                                    "outputs": [{"type": "address[]"}]}], "getReservesList")
    if reserves is None:
        return None
    unit = call_raw(w3, oracle, _UINT("BASE_CURRENCY_UNIT"), "BASE_CURRENCY_UNIT") or 10 ** 8
    data_abi = [{"name": "getReserveData", "type": "function", "stateMutability": "view", "inputs": [{"type": "address"}],
                 "outputs": [{"type": t} for t in ("uint256", "uint128", "uint128", "uint128", "uint128", "uint128", "uint40",
                                                    "uint16", "address", "address", "address", "address", "uint128", "uint128", "uint128")]}]
    rows = []
    for asset in reserves:
        src = _addr(w3, oracle, "getSourceOfAsset", asset, ins=("address",))
        price = call_raw(w3, oracle, _UINT("getAssetPrice", "address"), "getAssetPrice", asset)
        data = call_raw(w3, pool, data_abi, "getReserveData", asset)
        dec = call_raw(w3, asset, [{"name": "decimals", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "uint8"}]}], "decimals")
        usd = None
        if data and price is not None and dec is not None:
            ts = call_raw(w3, data[8], _UINT("totalSupply"), "totalSupply")
            usd = ts * price / unit / 10 ** dec if ts is not None else None
        rows.append((asset, src, usd))
    return rows


def aave_governance(w3, provider):
    """(governance delay, own addresses) of an Aave V3 instance: the ACL admin executor's PayloadsController delay for
    access level 1 (getExecutorSettingsByAccessControl(1)), read live, and {executor, PayloadsController, ACLManager}.
    Delay None when unread."""
    executor = _addr(w3, provider, "getACLAdmin")
    acl_manager = _addr(w3, provider, "getACLManager")  # an adapter is the market's own only when it answers to this one
    pc = _addr(w3, executor, "owner") if executor else None
    settings = call_raw(w3, pc, [{"name": "getExecutorSettingsByAccessControl", "type": "function", "stateMutability": "view",
                                  "inputs": [{"type": "uint8"}], "outputs": [{"type": "tuple", "components": [{"type": "address"}, {"type": "uint40"}]}]}],
                        "getExecutorSettingsByAccessControl", 1) if pc else None
    delay = settings[1] if settings and settings[0] and executor and settings[0].lower() == executor.lower() else None
    return delay, {a for a in (executor, pc, acl_manager) if a}


def comet_rows(w3, comet):
    """[(asset, price feed, usd)] for a Compound V3 Comet: the base asset (totalSupply) and every collateral
    (totalsCollateral), valued with Comet.getPrice(feed). Priced supply = what the Comet lends plus what secures it."""
    info_abi = [{"name": "getAssetInfo", "type": "function", "stateMutability": "view", "inputs": [{"type": "uint8"}],
                 "outputs": [{"type": "tuple", "components": [{"type": "uint8"}, {"type": "address"}, {"type": "address"}, {"type": "uint64"},
                                                              {"type": "uint64"}, {"type": "uint64"}, {"type": "uint64"}, {"type": "uint128"}]}]}]
    tot_abi = [{"name": "totalsCollateral", "type": "function", "stateMutability": "view", "inputs": [{"type": "address"}],
                "outputs": [{"type": "uint128"}, {"type": "uint128"}]}]
    n = call_raw(w3, comet, [{"name": "numAssets", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "uint8"}]}], "numAssets")
    base_feed = _addr(w3, comet, "baseTokenPriceFeed")
    if n is None or base_feed is None:
        return None
    price = lambda feed: call_raw(w3, comet, _UINT("getPrice", "address"), "getPrice", feed)  # noqa: E731
    base_supply = call_raw(w3, comet, _UINT("totalSupply"), "totalSupply")
    base_scale = call_raw(w3, comet, _UINT("baseScale"), "baseScale")
    p = price(base_feed)
    rows = [(_addr(w3, comet, "baseToken"), base_feed, base_supply * p / 1e8 / base_scale if None not in (base_supply, base_scale, p) else None)]
    for i in range(n):
        info = call_raw(w3, comet, info_abi, "getAssetInfo", i)
        if info is None:
            rows.append((f"asset {i}", None, None))
            continue
        asset, feed, scale = info[1], info[2], info[3]
        tot = call_raw(w3, comet, tot_abi, "totalsCollateral", asset)
        p = price(feed)
        rows.append((asset, feed, tot[0] * p / 1e8 / scale if tot is not None and p is not None and scale else None))
    return rows


def morpho_v1_rows(w3, vault, morpho="0xBBBBBbbBBb9cC5e90e3b3Af64bdAF62C37EEFFCb"):
    """[(market id, oracle, assets the vault supplies there)] for a Morpho V1 vault's withdraw queue. Markets without an
    oracle (idle) are skipped. The value is in loan-token units: only the shares matter."""
    n = call_raw(w3, vault, _UINT("withdrawQueueLength"), "withdrawQueueLength")
    if n is None:
        return None
    q_abi = [{"name": "withdrawQueue", "type": "function", "stateMutability": "view", "inputs": [{"type": "uint256"}], "outputs": [{"type": "bytes32"}]}]
    pos_abi = [{"name": "position", "type": "function", "stateMutability": "view", "inputs": [{"type": "bytes32"}, {"type": "address"}],
                "outputs": [{"type": "uint256"}, {"type": "uint128"}, {"type": "uint128"}]}]
    mkt_abi = [{"name": "market", "type": "function", "stateMutability": "view", "inputs": [{"type": "bytes32"}],
                "outputs": [{"type": "uint128"}] * 6}]
    par_abi = [{"name": "idToMarketParams", "type": "function", "stateMutability": "view", "inputs": [{"type": "bytes32"}],
                "outputs": [{"type": "address"}, {"type": "address"}, {"type": "address"}, {"type": "address"}, {"type": "uint256"}]}]
    rows = []
    for i in range(n):
        mid = call_raw(w3, vault, q_abi, "withdrawQueue", i)
        if mid is None:
            rows.append((f"market {i}", None, None))
            continue
        params = call_raw(w3, morpho, par_abi, "idToMarketParams", mid)
        pos = call_raw(w3, morpho, pos_abi, "position", mid, Web3.to_checksum_address(vault))
        mkt = call_raw(w3, morpho, mkt_abi, "market", mid)
        if params is None or pos is None or mkt is None:
            rows.append((mid.hex(), None, None))
            continue
        if not int(params[2], 16):
            continue  # idle market: no collateral, no price
        assets = pos[0] * mkt[0] // mkt[1] if mkt[1] else 0
        rows.append((mid.hex(), Web3.to_checksum_address(params[2]), assets))
    return rows


# ------------------------------------------------------------------------------------------------- verified specs
# Each spec re-reads, every run, the facts that keep its classification (research of 2026-10-04, each fact re-checked by a
# second, independent pass); any other answer gives UNREAD.
_cs = lambda a: Web3.to_checksum_address(a.lower())  # noqa: E731
_R = lambda h: bytes.fromhex(h[2:] if h.startswith("0x") else h)  # noqa: E731


def _etherfi_weeth(w3, gov):
    """weETH's rate (LiquidityPool.amountForShare) moves only by an EtherFiAdmin rebase bounded by an APR cap whose maximum
    is immutable; the bound and every upgrade sit behind EtherFi's OPERATION (2 d) and UPGRADE (10 d) timelocks."""
    rr = _cs("0x62247D29B4B9BECf4BB73E0c722cf6445cfC7cE9")
    roles = {"UPGRADE_TIMELOCK_ROLE": ("0x5ba17a247620ef8426ae0fffc28eee4ee4b18eb3b8bcfa95664565c35371dfb5", _cs("0x9f26d4C958fD811A1F59B01B86Be7dFFc9d20761")),
             "OPERATION_TIMELOCK_ROLE": ("0xe6bda0fc5c63b525e475d178ed9c7fa9913b3429ade866197b11eb0f2c18c673", _cs("0xcD425f44758a08BaAB3C4908f3e3dE5776e45d7a"))}
    holders_abi = [{"name": "roleHolders", "type": "function", "stateMutability": "view", "inputs": [{"type": "bytes32"}], "outputs": [{"type": "address[]"}]}]
    rr_owner = _addr(w3, rr, "owner")  # the RoleRegistry owner can grant both roles: it must be the UPGRADE timelock
    if not rr_owner or rr_owner.lower() != roles["UPGRADE_TIMELOCK_ROLE"][1].lower():
        return [path("weETH rate (EtherFi)", "UNREAD", note=f"RoleRegistry owner {rr_owner}, expected the UPGRADE timelock")]
    notes = []
    for name, (role, tl) in roles.items():
        holders = call_raw(w3, rr, holders_abi, "roleHolders", _R(role))
        d = call_raw(w3, tl, _UINT("getMinDelay"), "getMinDelay")
        if holders is None or [h.lower() for h in holders] != [tl.lower()] or not d or not gov or d < gov:
            return [path("weETH rate (EtherFi)", "UNREAD", note=f"{name}: holders {holders}, delay {d} -- not the verified shape")]
        notes.append(f"{name} = timelock {tl} ({d}s)")
    max_apr = call_raw(w3, _cs("0x0EF8fa4760Db8f5Cd4d993f3e3416f30f942D705"), [{"name": "maxAcceptableRebaseAprInBps", "type": "function",
                       "stateMutability": "view", "inputs": [], "outputs": [{"type": "int256"}]}], "maxAcceptableRebaseAprInBps")
    if max_apr != 1000:
        return [path("weETH rate (EtherFi)", "UNREAD", note=f"rebase APR cap maximum {max_apr}, expected the immutable 1000")]
    return [path("weETH rate (EtherFi)", "governance-grade", note="rebase bounded (APR cap max 1000 bps, immutable); " + "; ".join(notes))]


def _lido_steth(w3, gov):
    """stETH's share rate moves by AccountingOracle reports (HashConsensus quorum) bounded by OracleReportSanityChecker; the
    limits, roles and upgrades belong to the Lido Agent, executable only by the Dual Governance executor behind the
    EmergencyProtectedTimelock (afterSubmit 3 d)."""
    tl, ex = _cs("0xCE0425301C85c5Ea2A0873A2dEe44d78E02D2316"), _cs("0x23E0B465633fF5178808F4A75186E2F2F9537021")
    acl, agent, voting = _cs("0x9895F0F17cc1d1891b6f18ee0b483B6f221b37Bb"), _cs("0x3e40D73EB977Dc6a537aF587D48316feE66E9C8c"), _cs("0x2e59A20f205bB85a89C53f1936454680651E618e")
    execute = Web3.keccak(text="EXECUTE_ROLE")
    perm = lambda who: call_raw(w3, acl, _BOOL("hasPermission", "address", "address", "bytes32"), "hasPermission", who, agent, execute)  # noqa: E731
    after = call_raw(w3, tl, _UINT("getAfterSubmitDelay"), "getAfterSubmitDelay")
    emergency = call_raw(w3, tl, _BOOL("isEmergencyModeActive"), "isEmergencyModeActive")
    ex_owner = _addr(w3, ex, "owner")
    run_script = Web3.keccak(text="RUN_SCRIPT_ROLE")
    facts = {"afterSubmit": after, "emergency": emergency, "executor owner": ex_owner, "executor EXECUTE": perm(ex), "Voting EXECUTE": perm(voting),
             "Voting RUN_SCRIPT": call_raw(w3, acl, _BOOL("hasPermission", "address", "address", "bytes32"), "hasPermission", voting, agent, run_script)}
    ok = (after and gov and after >= gov and emergency is False and ex_owner and ex_owner.lower() == tl.lower()
          and facts["executor EXECUTE"] is True and facts["Voting EXECUTE"] is False and facts["Voting RUN_SCRIPT"] is False)
    if not ok:
        return [path("stETH share rate (Lido)", "UNREAD", note=f"not the verified shape: {facts}")]
    return [path("stETH share rate (Lido)", "governance-grade", note=f"oracle reports bounded by the sanity checker; limits and upgrades through Dual Governance, afterSubmit {after}s")]


RSETH_PROOF_BLOCK = 26115261  # first Ethereum block of 2026-10-04 UTC; the DEFAULT_ADMIN replay of that day found one holder


def role_events_since(w3, contract, role, start, chunk=10_000):
    """Number of RoleGranted / RoleRevoked logs for `role` on `contract` from block `start` to the tip, in chunks a public
    RPC accepts (publicnode refuses 20,000 blocks; eth.drpc.org refuses even 1,000, so the Ethereum scorer's RPC must serve
    eth_getLogs). Raises on a failed read: never 'no event'."""
    topics = [["0x" + Web3.keccak(text=e).hex().removeprefix("0x") for e in ("RoleGranted(bytes32,address,address)", "RoleRevoked(bytes32,address,address)")],
              "0x" + role.hex()]
    tip, n, a = _eth(lambda: w3.eth.block_number, "block number"), 0, Web3.to_checksum_address(contract)
    while start <= tip:
        end = min(start + chunk - 1, tip)
        flt = {"fromBlock": start, "toBlock": end, "address": a, "topics": topics}
        n += len(_eth(lambda: w3.eth.get_logs(flt), f"logs {start}-{end} of {a}"))
        start = end + 1
    return n


def _kelp_rseth(w3, gov):
    """rsETH's LRTOracle: the LRTConfig DEFAULT_ADMIN can switch off pricePercentageLimit and re-point an asset oracle with
    no timelock (both simulated by eth_call 2026-10-04). Scored. Upgrades go through a ProxyAdmin behind a 10-day timelock.
    LRTConfig is not enumerable: the admin set was replayed on 2026-10-04 (28 grants, 12 revokes, one live holder); each run
    re-reads that holder with hasRole and checks that no DEFAULT_ADMIN grant or revoke happened since that day."""
    oracle, config, admin = _cs("0x349A73444b1a310BAe67ef67973022020d70020d"), _cs("0x947Cb49334e6571ccBFEF1f1f1178d8469D65ec7"), _cs("0xb3696a817D01C8623E66D156B6798291fa10a46d")
    cfg = _addr(w3, oracle, "lrtConfig")
    has = call_raw(w3, config, _BOOL("hasRole", "bytes32", "address"), "hasRole", b"\x00" * 32, Web3.to_checksum_address(admin))
    if not cfg or cfg.lower() != config.lower() or has is not True:
        return [path("rsETH LRTOracle admin", "UNREAD", note=f"lrtConfig {cfg}, hasRole(DEFAULT_ADMIN, {admin}) {has}")]
    try:
        changes = role_events_since(w3, config, b"\x00" * 32, RSETH_PROOF_BLOCK)
    except Exception as e:  # noqa: BLE001 -- a failed log read is unknown, never "no change"
        return [path("rsETH LRTOracle admin", "UNREAD", note=f"DEFAULT_ADMIN log replay since block {RSETH_PROOF_BLOCK} failed: {type(e).__name__}")]
    if changes:
        return [path("rsETH LRTOracle admin", "UNREAD", note=f"{changes} DEFAULT_ADMIN grant/revoke event(s) since the 2026-10-04 proof: holder set to re-derive")]
    admin_path = controller_path(w3, admin, gov, "rsETH LRTOracle admin (LRTConfig DEFAULT_ADMIN: limit off, oracle re-point, no timelock)")
    upgrade = controller_path(w3, _slot(w3, oracle, ADMIN_SLOT), gov, "rsETH LRTOracle upgrade (ProxyAdmin)")
    return [admin_path, upgrade]


def _stakewise_oseth(w3, gov):
    """osETH's OsTokenVaultController is not upgradeable and its rate can only rise (avgRewardPerSecond is unsigned and
    capped by an immutable maximum; verified source 2026-10-04); Aave's CAPO clips the upside. Disclosed as bounded while
    the code is the same and no proxy slot appears."""
    c = _cs("0x2A261e60FB14586B474C208b1B7AC6D0f5000306")
    code = _code(w3, c)
    same = Web3.keccak(code).hex().removeprefix("0x") == "ebd2fe45e59cf42767707b0fcce7f540ff08d122c7c7087b422c8b80fbd9afe8"
    if not same or any(_slot(w3, c, s) for s in (IMPL_SLOT, ADMIN_SLOT, BEACON_SLOT)):
        return [path("osETH rate (StakeWise)", "UNREAD", note="code or proxy slots changed since the 2026-10-04 proof")]
    return [path("osETH rate (StakeWise)", "bounded", note="non-upgradeable, rate can only rise; upside clipped by the target's CAPO")]


def _elixir_sdeusd(w3, gov):
    """sdeUSD (Morpho BASE_VAULT, convertToAssets): UUPS, upgrade gated by DEFAULT_ADMIN = owner(). Deeper input disclosed,
    not scored (one hop): deUSD can be minted without backing through a CCIP pool whose owner is an EIP-7702 EOA, which
    raises sdeUSD's rate (research 2026-10-04)."""
    owner = _addr(w3, _cs("0x5C5b196aBE0d54485975D1Ec29617D42D9198326"), "owner")
    return [controller_path(w3, owner, gov, "sdeUSD upgrade (owner, DEFAULT_ADMIN)")]


def _monad_fixed_musd(w3, gov):
    """Aave V3 Monad's 'Fixed mUSD/USD' adapter: setPrice by a POOL_ADMIN of the target's own ACLManager (the executor behind
    the PayloadsController and the PROTOCOL_GUARDIAN Safe 4-of-7), a seat the market's own composite already scores. Own
    configuration while the adapter answers to that ACLManager (read 2026-10-04)."""
    acl = _addr(w3, _cs("0xbbb58AA3a251c9f19653771c44481c39500b71A3"), "ACL_MANAGER")
    if not acl or acl.lower() != "0xa9fee192a76b8f5e5f3d310ab6c526cb11f3d95b":
        return [path("Monad Fixed mUSD/USD adapter", "UNREAD", note=f"ACL_MANAGER {acl}, expected the market's own 0xa9fEe192")]
    return [path("Monad Fixed mUSD/USD adapter", "own", note="setPrice by the market's own POOL_ADMIN holders: already in the composite")]


MONAD_SPECS = {"0xbbb58AA3a251c9f19653771c44481c39500b71A3": _monad_fixed_musd}

ETHEREUM_SPECS = {
    "0xCd5fE23C85820F7B72D0926FC9b05b43E359b7ee": _etherfi_weeth,   # weETH (Aave RATIO_PROVIDER, Compound ratioProvider)
    "0xae7ab96520DE3A18E5e111B5EaAb095312D7fE84": _lido_steth,      # stETH (Aave wstETH adapter RATIO_PROVIDER)
    "0x7f39C581F595B53c5cb19bD0b3f8dA6c935E2Ca0": _lido_steth,      # wstETH (Compound CAPO ratioProvider: stEthPerToken)
    "0x349A73444b1a310BAe67ef67973022020d70020d": _kelp_rseth,      # rsETH LRTOracle
    "0x2A261e60FB14586B474C208b1B7AC6D0f5000306": _stakewise_oseth,  # osETH OsTokenVaultController
    "0x5C5b196aBE0d54485975D1Ec29617D42D9198326": _elixir_sdeusd,   # sdeUSD (Morpho BASE_VAULT)
}


# ------------------------------------------------------------------------------------------------- entry points
def _fail_closed(fn):
    """A read that raises (RpcUnavailable after its retries, a malformed answer) gives UNKNOWN_SCORE and a note, never a
    crashed scorer: the walk is one field of the target, its other reads stand on their own."""
    def run(w3, target, specs=None, notes=None):
        notes = [] if notes is None else notes
        try:
            return fn(w3, target, specs, notes)
        except Exception as e:  # noqa: BLE001 -- a failed read is unknown, never 100
            notes.append(f"oracleAuthorityScore {UNKNOWN_SCORE}: {FAILED_MARK} ({type(e).__name__}: {e}) -- unknown, not 100")
            return UNKNOWN_SCORE
    run.__name__, run.__doc__ = fn.__name__, fn.__doc__
    return run


@_fail_closed
def for_aave(w3, provider, specs=None, notes=None):
    """oracleAuthorityScore of an Aave V3 instance (its PoolAddressesProvider). A reserve list that cannot be read is
    UNREAD: UNKNOWN_SCORE."""
    notes = [] if notes is None else notes
    delay, own = aave_governance(w3, provider)
    rows = aave_rows(w3, provider)
    if rows is None:
        notes.append(f"oracleAuthorityScore {UNKNOWN_SCORE}: {UNREAD_MARK} ['reserve list or price oracle'] -- unknown, not 100")
        return UNKNOWN_SCORE
    notes.append(f"governance delay (PayloadsController level 1) = {delay}s")
    return score(w3, rows, delay, specs, own, notes)


@_fail_closed
def for_comet(w3, comet, specs=None, notes=None):
    """oracleAuthorityScore of a Compound V3 Comet: governance delay = governor().delay() (the local timelock on an L2)."""
    notes = [] if notes is None else notes
    governor = _addr(w3, comet, "governor")
    delay = call_raw(w3, governor, _UINT("delay"), "delay") if governor else None
    rows = comet_rows(w3, comet)
    if rows is None:
        notes.append(f"oracleAuthorityScore {UNKNOWN_SCORE}: {UNREAD_MARK} ['Comet assets'] -- unknown, not 100")
        return UNKNOWN_SCORE
    notes.append(f"governance delay (governor {governor} delay()) = {delay}s")
    return score(w3, rows, delay, specs, {governor} if governor else set(), notes)


@_fail_closed
def for_morpho_v1(w3, vault, specs=None, notes=None):
    """oracleAuthorityScore of a Morpho V1 vault: its markets' oracles weighted by the vault's current allocation;
    governance delay = vault.timelock()."""
    notes = [] if notes is None else notes
    delay = call_raw(w3, vault, _UINT("timelock"), "timelock")
    rows = morpho_v1_rows(w3, vault)
    if rows is None:
        notes.append(f"oracleAuthorityScore {UNKNOWN_SCORE}: {UNREAD_MARK} ['withdraw queue'] -- unknown, not 100")
        return UNKNOWN_SCORE
    notes.append(f"governance delay (vault timelock()) = {delay}s; shares = current allocation")
    return score(w3, rows, delay, specs, set(), notes)
