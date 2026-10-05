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
The walk follows the getters it knows (FEED_GETTERS, RATE_GETTERS, and TEMPLATE_INPUT_GETTERS for one pinned build): an
input a wrapper reads through any other getter is not seen. An EIP-1167 clone of a pinned implementation (PASSTHROUGH_IMPLS)
is walked through to the oracles it switches between, and an input-less MorphoChainlinkOracleV2 (pinned template, six
inputs zero, price() = SCALE_FACTOR()) is disclosed as a constant.

Entry points: Aave V3, Aave V2 (Radiant), Compound V3, Moonwell (a Compound V2 fork), Morpho V1, Morpho Vault V2, GMX V2, GMX V1, an Euler V2 eVaultFactory
and an EulerEarn vault (a row's source may be a tuple: an EVK vault reads its router, adapters and ERC4626 rates, and its
value reaches every one of them). Rows that overlap (a
GMX market's pool on one row per token it prices, the GMX V1 VaultPriceFeed row over the whole pool) are weighed against
the priced supply the row builder returns (score(total=)), not against their own sum.
"""
from web3 import Web3
from web3.exceptions import ContractLogicError

import eth_abi
from eth_abi import encode as abi_encode

try:  # loaded as lib.price_authority (Robinhood scorers) or as a bare module (chain scorers put scripts/lib on sys.path)
    from . import morpho_v2
    from . import web3_utils as _wu
    from .web3_utils import call_raw, safe_owners_and_threshold
except ImportError:
    import morpho_v2
    import web3_utils as _wu
    from web3_utils import call_raw, safe_owners_and_threshold

MATERIALITY = 0.01
UNKNOWN_SCORE = 20
UNREAD_MARK = "material price path(s) UNREAD"  # push_guard holds an entry whose notes carry it and whose value moved
FAILED_MARK = "price walk failed"
FEED_GETTERS = ("BASE_TO_USD_AGGREGATOR", "ASSET_TO_USD_AGGREGATOR", "ASSET_TO_PEG", "PEG_TO_BASE",  # Aave adapters
                "assetToBaseAggregator", "underlyingPriceFeed", "WBTCToBTCPriceFeed", "BTCToUSDPriceFeed",  # Compound feeds
                "priceFeedA", "priceFeedB", "source",  # Compound/Monad wrappers
                "BASE_FEED_1", "BASE_FEED_2", "QUOTE_FEED_1", "QUOTE_FEED_2",  # MorphoChainlinkOracleV2
                "stETHtoETHPriceFeed",  # Compound WstETHPriceFeed, also a Morpho oracle input
                "underlyingFeed",  # Midas CustomAggregatorV3CompatibleFeedAdjusted
                "baseFeed", "quoteFeed",  # Robinhood Chain stock-token oracles (NetNet)
                "chainlinkFeed", "iassetUsdOracle", "exchangeRatioOracle",  # Radiant V2 adapters (immutable, verified source)
                "verifier",  # GMX ChainlinkDataStreamProvider: the Chainlink Data Streams VerifierProxy it reads
                "chronicle", "chainlink", "redstone",  # Chronicle OracleAggregator (Aggor): the median of three, each walked
                "priceFeed")  # Moonwell ChainlinkOEVWrapper
# Euler ChainlinkOracle / ChainlinkInfrequentOracle (feed) and CrossAdapter (its two legs) expose no other getter: tried only
# when none of FEED_GETTERS and RATE_GETTERS answered, so the walk of every other source makes three calls fewer.
EULER_FEED_GETTERS = ("feed", "oracleBaseCross", "oracleCrossQuote")
RATE_GETTERS = ("RATIO_PROVIDER", "ratioProvider", "BASE_VAULT", "QUOTE_VAULT",
                "wstETH", "WEETH")  # Compound WstETHPriceFeed, WeEthToEthExchangeRateAdapter: they reach the Lido and EtherFi specs
# Spark's *ExchangeRateOracle (immutable): ethSource() times one rate read through a getter named after its asset (oracle() is
# the rsETH LRTOracle). Followed only next to ethSource(): oracle() alone is far too generic (a GMX data-stream provider's
# oracle() is GMX's own Oracle).
ETH_RATE_GETTERS = ("steth", "weeth", "reth", "ezETH", "oracle")
# Moonwell's ChainlinkCompositeOracle (immutable): base() x multiplier() (x secondMultiplier() when set). Followed only when
# multiplier() answers and both are contracts: base() alone is an Euler adapter's base TOKEN (TelosC's fixed exUSD adapter).
COMPOSITE_GETTERS = ("base", "multiplier", "secondMultiplier")
IMPL_SLOT = 0x360894A13BA1A3210667C828492DB98DCA3E2076CC3735A920A3CA505D382BBC
ADMIN_SLOT = 0xB53127684A568B3173AE13B9F8A6016E243E63B6E8EE1178D6A717850B5D6103
BEACON_SLOT = 0xA3F0AD74E5423AEBFD80D3EF4346578335A9A72AEAEE59FF6CB3582B35133D50  # keccak("eip1967.proxy.beacon") - 1
ZEPPELIN_IMPL_SLOT = 0x7050C9E0F4CA769C69BD3A8EF740BC37934F8E2C036E5A723FD8EE048ED3F8C3  # keccak("org.zeppelinos.proxy.implementation")
ZEPPELIN_ADMIN_SLOT = 0x10D6A54A4754C8869D6886B5F5D7FBFA5B4522237EA5C60D11BC4E7A1FF9390B  # keccak("org.zeppelinos.proxy.admin"), FiatToken
PROXY_SLOTS = (IMPL_SLOT, ADMIN_SLOT, BEACON_SLOT, ZEPPELIN_IMPL_SLOT, ZEPPELIN_ADMIN_SLOT)
DELEGATION = b"\xef\x01\x00"  # EIP-7702: the account's code is this prefix and the delegate's address
EIP1167 = (bytes.fromhex("363d3d373d3d3d363d73"), bytes.fromhex("5af43d82803e903d91602b57fd5bf3"))  # minimal proxy around its 20-byte target
# EIP-1167 clones walked THROUGH to the oracles their implementation reads: {implementation: (runtime code hash, getters)}.
# MetaOracleDeviationTimelock (Steakhouse): price() is primaryOracle's or backupOracle's price, both fixed by initialize();
# challenge/acceptChallenge/heal are permissionless and only switch between the two; no owner, no setter (verified source,
# Ethereum solc 0.8.28; the Robinhood Chain build, Sourcify exact match solc 0.8.33, differs only in getDeviation and the
# initializer). Both hashes read live 2026-10-05; neither implementation has a proxy slot.
PASSTHROUGH_IMPLS = {
    "0x9b4655239e91dc9e1f7599bb88fba41b4542de5b": ("f4258224542b81cf805be3c37d08c2ee2d4f92a9a625deb6650d6e823650efa0", ("primaryOracle", "backupOracle")),
    "0x6a16d6fe1ba26e6ba52fda03972b1fe2e31ca729": ("df8ac65460bf9a997f353a153f8236d0dfa31d917d0cb894f74a4a2f8449ee14", ("primaryOracle", "backupOracle")),
}
# masked_template() of MorphoChainlinkOracleV2: equal for the verified Ethereum deployment 0xA6D6950c9F177F1De7f7757FB33539e3Ec60182a
# and the Robinhood Chain oracles 0x68B60430, 0xCb6EdD02 (read live 2026-10-05). With its six inputs zero, price() is the
# immutable SCALE_FACTOR (each feed and vault factor is 1 when its address is zero).
MORPHO_ORACLE_V2_TEMPLATE = "b8a82b17ed0f276b95b55a09897225a0aeff2b6310cb7d780233eaeff01a0d59"
MORPHO_ORACLE_V2_INPUTS = ("BASE_FEED_1", "BASE_FEED_2", "QUOTE_FEED_1", "QUOTE_FEED_2", "BASE_VAULT", "QUOTE_VAULT")
# PUSH32 layouts, position by position (masked_template pins the opcodes, a layout pins the 32-byte operands it zeroed): an
# int must be that exact value, a name the exact value its getter returns read as a uint (an address getter's word
# included). A set comparison is not enough: a hand-built copy could move a held address to another site, or put a dirty
# high bit on it (a CALL uses the low 160 bits). Read live on 2026-10-05.
_M4, _MFF, _ME0 = int("ff" * 31 + "fc", 16), int("ff" * 32, 16), int("ff" * 31 + "e0", 16)
_SEL = lambda h: int(h + "00" * 28, 16)  # noqa: E731  (a 4-byte selector left-aligned in a word)
# Input-less MorphoChainlinkOracleV2 (0x68B60430a1E2d663cCD975Be31d3d31EBa8Ee501, Robinhood Chain): its six feed and vault
# sites hold 0, its conversion samples 1, and SCALE_FACTOR sits only where the genuine code multiplies by it.
MORPHO_ORACLE_V2_INPUTLESS_LAYOUT = (
    _M4, 0, _M4, 0, _M4, 0, _M4, "SCALE_FACTOR", _M4, 0, _M4, 1, 0, 0, 0, 1, 0, 0, 0, "SCALE_FACTOR", _M4, 0, _M4, 1, _M4, 0,
    _M4, 1, _SEL("4e487b71"), _MFF, _SEL("227bc153"), _SEL("4e487b71"), _ME0, _SEL("4e487b71"), _SEL("feaf968c"),
    int("6e6567617469766520616e73776572" + "00" * 17, 16), _SEL("08c379a0"), _ME0, _SEL("07a2d13a"))
# Inputs a contract of one build reads through a getter too generic to follow everywhere: {masked_template: getters}. The
# Robinhood Chain stock-token oracle (NetNet markets, 2,563 bytes, unverified; same template for NVDA 0xED29D310, SPCX,
# GOOGL, AAPL, COIN, MSFT, read live 2026-10-05) prices SCALE_FACTOR * baseFeed / quoteFeed * token().uiMultiplier() / 1e18
# (checked numerically on NVDA to 16 digits): token() is an input.
# {masked_template: (input getters, PUSH32 layout)}; the build is followed only while its operands match the layout site by
# site (the same on the four NetNet oracles NVDA, SPCX, GOOGL and AAPL).
TEMPLATE_INPUT_GETTERS = {"8e9155a55e94d127e8d3e6f835cfeb402a232fac5a40508657520506cfd3cb7c": (("token",), (
    "loanToken", 8, "quoteFeed", 8, "SCALE_FACTOR", "token", "baseFeed", "baseFeed", "quoteFeed", "token", "token", 8, 8, "SCALE_FACTOR"))}
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


def delay_points(seconds):
    """timelockScore credited to an account that acts through a timelock shorter than the target's own delay (decided
    2026-10-05): the notice-period curve of chains/solana/METHODOLOGY.md 6.1 (50 x hours / 24 below a day, then +10 a day up
    to 80), capped
    at 60, the EVM level of a real delay whose bypass paths were not ruled out. 0 s gives 0."""
    if not seconds:
        return 0
    h = seconds / 3600
    return min(60, int((50 * h / 24 if h < 24 else 50 + min(30, 10 * (h / 24 - 1))) + 0.5))


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
    solc bzzr0 / bzzr1, solc version only (bytecodeHash none: the Robinhood Chain MorphoChainlinkOracleV2 builds), or old
    Vyper. Any other byte sequence is scanned as code."""
    ipfs = b"\x64ipfs\x58\x22"
    shapes = ((b"\xa2" + ipfs, 34, _SOLC, 3, b""), (b"\xa3" + ipfs, 34, b"\x6cexperimental", 1, _SOLC),
              (b"\xa1\x65bzzr0\x58\x20", 32, b"", 0, b""), (b"\xa2\x65bzzr1\x58\x20", 32, _SOLC, 3, b""),
              (b"\xa1" + _SOLC, 3, b"", 0, b""))
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


def _strip_metadata(code):
    """The runtime code without its compiler metadata trailer: exactly one of the maps _is_metadata knows, after a STOP or
    INVALID byte, that no PUSH constant of the code jumps into. Anything else is kept, so it is scanned or hashed as code."""
    n = int.from_bytes(code[-2:], "big") if len(code) >= 2 else 0
    start = len(code) - n - 2
    if 0 < n and start > 0 and code[start - 1] in (0x00, 0xFE) and _is_metadata(code[start:-2]) and not _jumped_into(code, start):
        return code[:start]
    return code


def _executable(code):
    """The bytes an opcode scan must read: the code before its metadata trailer (_strip_metadata); or, when solc put constant
    data (a long revert string, a description()) between the code and an exact trailer, the code before the first INVALID
    past which no valid JUMPDEST is the value of a PUSH placed before that INVALID. Execution cannot fall through INVALID
    and the JUMPDEST sweep is the EVM's own (from byte 0, PUSH data skipped), so nothing past that INVALID can run unless a
    jump target is computed at run time (a crafted contract, not a compiler's: the limit of _jumped_into). No exact trailer:
    the whole code."""
    n = int.from_bytes(code[-2:], "big") if len(code) >= 2 else 0
    start = len(code) - n - 2
    stripped = _strip_metadata(code)
    if len(stripped) < len(code) or not (0 < n and start > 0 and _is_metadata(code[start:-2])):
        return stripped
    i, pushes, dests, invalids = 0, [], [], []
    while i < len(code):
        op = code[i]
        if op == 0x5B:
            dests.append(i)
        elif op == 0xFE and i < start:
            invalids.append(i)
        if 0x60 <= op <= 0x7F:
            pushes.append((i, int.from_bytes(code[i + 1:i + op - 0x5E], "big")))
            i += op - 0x5F + 1
            continue
        i += 1
    for p in invalids:
        targets = {v for at, v in pushes if at < p}
        if not any(d > p and d in targets for d in dests):
            return code[:p]
    return code


def _no_opcode(code, banned):
    """True when no opcode in `banned` appears in the bytes the EVM can execute (_executable; PUSH data skipped): the
    compiler metadata trailer, and constant data placed before it, are not read as opcodes. Anything else is scanned, so a
    stray byte can only give a false 'not constant' (UNREAD)."""
    code = _executable(code)
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


def _push32_operands(code):
    """The PUSH32 operands of the runtime code (metadata trailer cut), as integers."""
    body, i, out = _strip_metadata(code), 0, []
    while i < len(body):
        op = body[i]
        if op == 0x7F:
            out.append(int.from_bytes(body[i + 1:i + 33], "big"))
        i += op - 0x5F + 1 if 0x60 <= op <= 0x7F else 1
    return out


def masked_template(code):
    """keccak of the runtime code without its metadata trailer (_strip_metadata) and with every PUSH32 operand zeroed: the
    hash of a contract's code with its 32-byte immutables (feed and vault addresses, scale factors) taken out, so every
    deployment of one build shares it. A truncated PUSH32 at the end is zeroed as far as it goes."""
    body = bytearray(_strip_metadata(code))
    i = 0
    while i < len(body):
        op = body[i]
        if op == 0x7F:
            body[i + 1:i + 33] = bytes(len(body[i + 1:i + 33]))
        i += op - 0x5F + 1 if 0x60 <= op <= 0x7F else 1
    return Web3.keccak(bytes(body)).hex().removeprefix("0x")


def _is_vault_v2(w3, address):
    """A Morpho Vault V2 of the pinned build (MORPHO_VAULT_V2_TEMPLATE) with no proxy slot."""
    code = _fixed_code(w3, address)
    return code is not None and masked_template(code) == MORPHO_VAULT_V2_TEMPLATE


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


def controller_path(w3, address, governance_delay, label, depth=0, delay=0):
    """Score the account that controls a contract: bare EOA (5, 0, t); Safe -> _safe_rooted with t; a timelock whose delay
    (plus `delay`) is at least the target's governance delay -> governance-grade; a shorter timelock -> the accounts that
    can schedule on it (_timelock_holders), each scored behind that delay, the worst one kept (decided 2026-10-05); a
    contract with owner()/admin() -> followed (2 hops); anything else UNREAD. `delay`: seconds of timelock already between
    this account and the price, credited as t = delay_points(delay)."""
    if address is None:
        return path(label, "UNREAD", note="controller unread")
    if delay and governance_delay and delay >= governance_delay:
        return path(label, "governance-grade", note=f"{address} acts behind {delay}s of timelock >= the target's governance delay {governance_delay}s", controller=address)
    code = _code(w3, address)
    t = delay_points(delay)
    above = f"behind {delay}s of timelock (timelockScore {t})" if delay else "no timelock above it"
    if not code:
        return path(label, "scored", composite(5, 0, t), f"{address}: bare EOA, {above}", address)
    if code[:3] == DELEGATION:
        return path(label, "scored", composite(5, 0, t), f"{address}: EOA with an EIP-7702 delegation, one key, {above}", address)
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
        owners, threshold = safe
        admin, multisig, _ = _safe_rooted(threshold, len(owners))
        return path(label, "scored", composite(admin, multisig, t), f"{address}: Safe {threshold}-of-{len(owners)}, {above}"
                    + (f"; Safe gate: {gate}" if gate else ""), address)
    if any(g.startswith("blocking") for g in gate):
        return path(label, "UNREAD", note=f"{address}: Safe with an unanalyzed module or singleton: {gate}", controller=address)
    for getter in ("getMinDelay", "delay"):
        d = call_raw(w3, address, _UINT(getter), getter, retries=2)
        if d is not None:
            total = d + delay
            seen = f"{address}: timelock {getter}() = {d}s" + (f" + {delay}s above it" if delay else "")
            if not _verified_timelock(w3, address):
                return path(label, "UNREAD", note=f"{seen}, but its code is not a verified timelock build (VERIFIED_TIMELOCKS, TIMELOCK_HOLDERS)", controller=address)
            if governance_delay and total >= governance_delay:  # a target with no delay of its own gives no governance-grade bar
                return path(label, "governance-grade", note=f"{seen} >= the target's governance delay {governance_delay}s", controller=address)
            holders, how = _timelock_holders(w3, address, getter)
            if not holders or depth >= 3:
                return path(label, "UNREAD", note=f"{seen}, below the target's governance delay ({governance_delay}); its proposers are not resolved: {how}", controller=address)
            subs = [controller_path(w3, h, governance_delay, f"{label} -> proposer {h}", depth + 1, total) for h in holders]
            return _worst(subs, f"{seen}, below the target's governance delay ({governance_delay}); who can schedule ({how}): "
                          + "; ".join(f"{s['controller'] or s['label']} {s['status']}" + (f" {s['composite']}" if s["composite"] is not None else "") for s in subs))
    if depth < 2:
        for getter in ("owner", "admin"):
            up = _addr(w3, address, getter)
            if up:
                return controller_path(w3, up, governance_delay, f"{label} -> {getter}()", depth + 1, delay)
    return path(label, "UNREAD", note=f"{address}: contract ({len(code)} bytes), neither EOA, resolvable Safe, timelock nor owned contract", controller=address)


def _worst(subs, why):
    """One path for several accounts that can each act alone: UNREAD if any is, else the lowest scored, else
    governance-grade (every one sits behind enough delay)."""
    pick = (next((s for s in subs if s["status"] == "UNREAD"), None)
            or min((s for s in subs if s["status"] == "scored"), key=lambda s: s["composite"], default=None) or subs[0])
    return dict(pick, note=f"{pick['note']} [{why}]")


# Who can schedule on an OpenZeppelin TimelockController: its PROPOSER_ROLE holders, and the holders of its admin role
# (TIMELOCK_ADMIN_ROLE before OpenZeppelin 5, DEFAULT_ADMIN_ROLE since; held by the timelock itself it acts only through a
# scheduled call), who can grant PROPOSER_ROLE. Not enumerable: each set comes from the timelock's whole RoleGranted /
# RoleRevoked history, replayed from block 0. Only a timelock whose runtime code is verified as a plain TimelockController
# (or byte-identical to one) is pinned, by code hash: an unverified build could let another role schedule. A run re-checks
# the code hash, each holder with hasRole, and that no grant or revoke of those roles happened after the proof block.
# {timelock lowercase: (chain id, proof block, ((role, holder), ...), runtime code hash)}
TIMELOCK_ROLES = {"PROPOSER_ROLE": Web3.keccak(text="PROPOSER_ROLE"), "TIMELOCK_ADMIN_ROLE": Web3.keccak(text="TIMELOCK_ADMIN_ROLE"),
                  "DEFAULT_ADMIN_ROLE": b"\x00" * 32}
TIMELOCK_HOLDERS = {
    # EtherFi OPERATION (2 d) and UPGRADE (10 d) timelocks: EtherFiTimelock, a plain OpenZeppelin 4 TimelockController
    # (Sourcify, Ethereum); 5 events each, admin role held only by itself (replayed 2026-10-05)
    "0xcd425f44758a08baab3c4908f3e3de5776e45d7a": (1, 26125251, (("PROPOSER_ROLE", "0x2aCA71020De61bb532008049e1Bd41E451aE8AdC"),),
                                                   "ade1557dee87af5dc1033d42e641b46176a2f9b8b9c341ad324837660b652778"),
    "0x9f26d4c958fd811a1f59b01b86be7dffc9d20761": (1, 26125266, (("PROPOSER_ROLE", "0xcdd57D11476c22d265722F68390b036f3DA48c21"),),
                                                   "bf21ebc11e4f971cbfdd8a64f63d34e737f63bc98303f223a03673bd141749f0"),
    # Chronicle on Monad: owner of the spellExecutor (7 d), byte-identical to ChronicleGovernance_CouncilTimelock 0xbA36311E on
    # Ethereum (Sourcify: OpenZeppelin 5.3 TimelockController + AccessControlEnumerable, uniform delay); 5 events, admin itself,
    # replayed on rpc1.monad.xyz 2026-10-05. Chronicle's ward timelock 0x2F8C9072 (7 d): code identical, metadata trailer
    # aside, to ChronicleTimelockController 0xcF03450A on Ethereum Sepolia (Blockscout-verified: OpenZeppelin TimelockController
    # plus a one-time initialize that grants the governors PROPOSER/CANCELLER and revokes the deployer's admin); 6 events,
    # the deployer's DEFAULT_ADMIN granted and revoked in the deployment block.
    "0x61ecb8efe66133368121872218c186244973e658": (143, 110715620, (("PROPOSER_ROLE", "0x82E6d70bcca6b0FedA9f00C9727Df4E03fAA0fB5"),),
                                                   "25811d5a1ce1d0f1da8f6ad0dbc551805b5f691b82945bb98ec2d0f44ea34711"),
    "0x2f8c90726bc6bec5d01313476f2e211a366a921a": (143, 110715623, (("PROPOSER_ROLE", "0x93Be96c028C6021de62A85021E41ceA63f42D516"),),
                                                   "3fb0f77e87760264dd1148469cd14185754a95af4387b78f2ce0b123fd374da4"),
    # GMX GovTimelockController 0x4bd1cdAa (1 d, a RoleStore ROLE_ADMIN): OpenZeppelin TimelockController plus name() (Sourcify
    # and Blockscout, Arbitrum); replayed 2026-10-05, 9 events, TIMELOCK_ADMIN_ROLE held only by itself. Proposers: the GMX
    # ProtocolGovernor and a bare EOA. The ConfigTimelockController 0x2Dd99f39 adds OracleModule and other functions to the
    # TimelockController: not a plain build, not pinned.
    "0x4bd1cdaab4254fc43ef6424653ca2375b4c94c0e": (42161, 511886266, (("PROPOSER_ROLE", "0x03e8f708e9C85EDCEaa6AD7Cd06824CeB82A7E68"),
                                                                     ("PROPOSER_ROLE", "0xE7BfFf2aB721264887230037940490351700a068")),
                                                   "d5f44930a71aedace378da4be055bbe314a746f7108033558c7a91ecfcc83ad7"),
}
# A timelock counts only when its code is a verified build: a contract answering getMinDelay() or delay() may let another
# role act at once (GMX's ConfigTimelockController adds functions; Dolomite's owner has a bypass role). Governance-grade, and
# a Compound Timelock's admin() as its only scheduler, need the runtime code hash listed here or pinned in TIMELOCK_HOLDERS
# (review of 2026-10-05). {runtime code hash: build, where verified}
VERIFIED_TIMELOCKS = {
    "d4723305a02271b663b1dd1845d20bb855804063fe498b5bd625cff34deb078f": "OpenZeppelin TimelockController (Sourcify exact match, Ethereum 0x49bd9989, the rsETH ProxyAdmin owner, 10 d)",
    "981458c817539dad7e7e91f8dfff45a41f03c734c15150a2053082cbc259cd4a": "ChronicleTimelockController_1: OpenZeppelin TimelockController + a one-time initialize (Sourcify exact match, Ethereum 0x40C33e79)",
    "25811d5a1ce1d0f1da8f6ad0dbc551805b5f691b82945bb98ec2d0f44ea34711": "ChronicleGovernance_CouncilTimelock: OpenZeppelin 5.3 TimelockController + AccessControlEnumerable, uniform delay (Sourcify, Ethereum 0xbA36311E; same code on Monad 0x61ecb8EF)",
    "6efba274b1952a7785a96abbeab284d059419fa812c47542e76123f1ea51c032": "OpenZeppelin TimelockController (Routescan-verified, Plasma 0x1415c23e, the Euler FactoryGovernor's admin, 4 d)",
    "5946724236054bf414ab56187235c379bf34cf64bfa7166fd26dae2050506c6d": "FluidTimelockController: a thin wrapper of OpenZeppelin TimelockController, no admin at deploy (Blockscout fully verified, Arbitrum and Plasma 0x4d6CE4F4, the Fluid Liquidity admin, 1 d)",
}


def _verified_timelock(w3, address):
    """True when the timelock's runtime code (no proxy slot) is a VERIFIED_TIMELOCKS build or its TIMELOCK_HOLDERS pin."""
    code = _fixed_code(w3, address)
    if code is None:
        return False
    h, pin = Web3.keccak(code).hex().removeprefix("0x"), TIMELOCK_HOLDERS.get(address.lower())
    return h in VERIFIED_TIMELOCKS or bool(pin and pin[3] == h)


# A chain whose scorer RPC cannot serve eth_getLogs over the replay window: {chain id: (log RPC, blocks per request)}.
LOG_SOURCES = {143: ("https://rpc1.monad.xyz", 10**9),  # rpc.monad.xyz caps eth_getLogs at 100 blocks
               9745: ("https://plasma.gateway.tenderly.co", 10**9)}  # rpc.plasma.to answers 429 to most calls (2026-10-05)
_ROLE_EVENTS = ["0x" + Web3.keccak(text=e).hex().removeprefix("0x") for e in ("RoleGranted(bytes32,address,address)", "RoleRevoked(bytes32,address,address)")]


def _log_reader(w3, chain):
    src = LOG_SOURCES.get(chain)
    return (_wu.get_w3(src[0]), src[1]) if src else (w3, 10_000)


def _timelock_holders(w3, timelock, getter):
    """(accounts that can schedule on `timelock`, how they were found), or (None, why) when they are not known.
    getMinDelay: the TIMELOCK_HOLDERS pin, re-checked live. delay(): a Compound Timelock (GRACE_PERIOD, MINIMUM_DELAY and
    MAXIMUM_DELAY readable), whose queueTransaction is onlyAdmin: admin(), and pendingAdmin() when set (it takes admin at
    once with acceptAdmin). controller_path reaches either branch only for a verified build (_verified_timelock), and
    VERIFIED_TIMELOCKS lists no Compound Timelock yet: in production a delay() contract is UNREAD until one is listed; the
    branch is kept, tested, for that day."""
    if getter == "delay":
        if any(call_raw(w3, timelock, _UINT(g), g, retries=2) is None for g in ("GRACE_PERIOD", "MINIMUM_DELAY", "MAXIMUM_DELAY")):
            return None, "delay() without the Compound Timelock getters"
        admin = _addr(w3, timelock, "admin")
        if not admin:
            return None, "Compound Timelock admin() unread"
        pending = _addr(w3, timelock, "pendingAdmin")
        return [admin] + ([pending] if pending else []), "Compound Timelock admin()" + (" and pendingAdmin()" if pending else "")
    pin = TIMELOCK_HOLDERS.get(timelock.lower())
    if not pin:
        return None, "holders not pinned in TIMELOCK_HOLDERS"
    chain, block, holders, code_hash = pin
    cid = _eth(lambda: w3.eth.chain_id, "chain id")
    if cid != chain:
        return None, f"pinned on chain {chain}, read on chain {cid}"
    if Web3.keccak(_code(w3, timelock)).hex().removeprefix("0x") != code_hash or any(_slot(w3, timelock, s) for s in PROXY_SLOTS):
        return None, "code changed since the pin, or a proxy slot is set"
    for role, h in holders:
        if call_raw(w3, timelock, _BOOL("hasRole", "bytes32", "address"), "hasRole", TIMELOCK_ROLES[role], _cs(h), retries=2) is not True:
            return None, f"{h} does not hold {role} any more (or the read failed)"
    lw3, chunk = _log_reader(w3, cid)
    topics = [_ROLE_EVENTS, ["0x" + bytes(r).hex() for r in TIMELOCK_ROLES.values()]]
    try:
        changes = logs_since(lw3, timelock, topics, block + 1, chunk)
    except Exception as e:  # noqa: BLE001 -- a failed log read is unknown, never "no change"
        return None, f"role replay after block {block} failed: {type(e).__name__}"
    if changes:
        return None, f"{changes} proposer/admin grant or revoke after the proof block {block}: re-derive the pin"
    return [_cs(h) for _, h in holders], f"pinned at block {block}, holders re-checked, no role change since"


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
    if len(code) == 45 and code.startswith(EIP1167[0]) and code.endswith(EIP1167[1]) and "0x" + code[10:30].hex() in PASSTHROUGH_IMPLS:
        return _walk_clone(w3, source, "0x" + code[10:30].hex(), specs, own, depth, memo)
    if _addr(w3, source, "aggregator"):
        return [("chainlink", source)]
    acl = _addr(w3, source, "ACL_MANAGER")
    if acl and acl.lower() not in own:  # an Aave-style adapter governed by another ACLManager than the target's
        return [("unread", source, f"adapter governed by a foreign ACLManager {acl}: its admins are not resolved")]
    manager = None if acl else _addr(w3, source, "manager")
    is_own = acl is not None or (manager is not None and manager.lower() in own) or (not manager and _owned_by(w3, source, own))
    # An Aave adapter only exposes the Aave getters: fewer calls, fewer rate-limit failures on public RPCs.
    feeds = [a for a in (_addr(w3, source, g) for g in (AAVE_FEED_GETTERS if acl else FEED_GETTERS)) if a and a.lower() != source.lower()]
    rates = [a for a in (_addr(w3, source, g) for g in (("RATIO_PROVIDER",) if acl else RATE_GETTERS)) if a]
    eth_source = None if acl else _addr(w3, source, "ethSource")
    if eth_source:
        legs = [a for a in (_addr(w3, source, g) for g in ETH_RATE_GETTERS) if a]
        if len(legs) != 1:  # the rate leg must be seen, and only one: anything else is not the analyzed shape
            return [("unread", source, f"ethSource() wrapper with {len(legs)} known rate legs, not exactly one")]
        feeds.append(eth_source)
        rates += legs
    if not acl:
        legs = [_addr(w3, source, g) for g in COMPOSITE_GETTERS]
        if legs[0] and legs[1]:
            if not all(_code(w3, a) for a in legs if a):  # a number read as an address (1e18), or a key: not the analyzed shape
                return [("unread", source, "composite oracle whose base(), multiplier() or secondMultiplier() answered an address with no code")]
            feeds += [a for a in legs if a and a.lower() != source.lower()]
    if not acl and not feeds and not rates:
        feeds = [a for a in (_addr(w3, source, g) for g in EULER_FEED_GETTERS) if a and a.lower() != source.lower()]
    template = masked_template(code)
    if not acl and template in TEMPLATE_INPUT_GETTERS:  # an input this build reads through a generic getter (token())
        walked, layout = TEMPLATE_INPUT_GETTERS[template]
        if not _layout_holds(w3, source, code, layout):
            return [("unread", source, "template-matched oracle whose 32-byte operands do not match its pinned layout, or a getter is unread")]
        ins = [_addr(w3, source, g) for g in walked]
        if None in ins:  # an input getter that reads zero or reverts: the input is not seen
            return [("unread", source, f"template-matched oracle whose input getter {walked} is unread or zero")]
        feeds += [a for a in ins if a.lower() != source.lower()]
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
        leaves.append(("spec", r) if r.lower() in specs else ("chainlink", r) if _addr(w3, r, "aggregator")
                      else ("vault-v2", r) if _is_vault_v2(w3, r) else ("rate", r))
    if not feeds and not rates:
        if is_own:  # an own adapter whose input this walk cannot see: unknown, unless a spec names it as own configuration
            return [("unread", source, "own adapter with no known upstream getter")]
        if not leaves:
            if is_provable_constant(w3, source):
                return [("constant", source)]
            if template == MORPHO_ORACLE_V2_TEMPLATE and _inputless_morpho_oracle(w3, source):
                return [("inputless", source)]
            return [("unread", source, "no aggregator(), no known upstream getter, no controller, not a provable constant")]
    return leaves


def _owned_by(w3, source, own):
    """True when the target's own governance holds `source` the way manager() does: its owner() is in `own` (a Moonwell
    ChainlinkOEVWrapper owned by the TemporalGovernor), or its DOLOMITE_MARGIN() is (a Dolomite oracle, onlyDolomiteMarginOwner:
    the Dolomite scorer puts DolomiteMargin in `own`); and no one else can swap its code: no beacon, and a proxy admin, if
    any, that is in `own` or whose owner() is."""
    holder = _addr(w3, source, "owner") or _addr(w3, source, "DOLOMITE_MARGIN")
    if not holder or holder.lower() not in own or _slot(w3, source, BEACON_SLOT):
        return False
    admin = _admin_slot(w3, source)
    return not admin or admin.lower() in own or (_addr(w3, admin, "owner") or "").lower() in own


def _inputless_morpho_oracle(w3, source):
    """True when all six inputs of a MorphoChainlinkOracleV2 (template already matched) read exactly zero and price() reads
    exactly SCALE_FACTOR(): with no feed and no vault the price is that immutable. An unread getter is not zero."""
    if any((v := call_raw(w3, source, _ADDR(g), g, retries=2)) is None or int(v, 16) for g in MORPHO_ORACLE_V2_INPUTS):
        return False
    price = call_raw(w3, source, _UINT("price"), "price", retries=2)
    scale = call_raw(w3, source, _UINT("SCALE_FACTOR"), "SCALE_FACTOR", retries=2)
    if price is None or price != scale:
        return False
    return _layout_holds(w3, source, _code(w3, source), MORPHO_ORACLE_V2_INPUTLESS_LAYOUT)


def _layout_holds(w3, source, code, layout):
    """True when the code's PUSH32 operands match `layout` site by site: an int exactly, a name exactly what its getter
    returns read as a uint (an unread getter fails)."""
    ops = _push32_operands(code)
    names = {x for x in layout if isinstance(x, str)}
    values = {g: call_raw(w3, source, _UINT(g), g, retries=2) for g in names}
    values = {g: int(v, 16) if isinstance(v, str) else v for g, v in values.items()}  # a hex word, as a decoder may hand it back
    if len(ops) != len(layout) or None in values.values():
        return False
    return all(op == (values[x] if isinstance(x, str) else x) for op, x in zip(ops, layout))


def _walk_clone(w3, source, impl, specs, own, depth, memo):
    """An EIP-1167 clone of a PASSTHROUGH_IMPLS implementation: walked through its listed getters while the implementation's
    code hash is the pinned one and it has no proxy slot. Any other answer is UNREAD."""
    code_hash, getters = PASSTHROUGH_IMPLS[impl]
    if Web3.keccak(_code(w3, impl)).hex().removeprefix("0x") != code_hash or any(_slot(w3, impl, s) for s in PROXY_SLOTS):
        return [("unread", source, f"EIP-1167 clone of {impl}: implementation code or proxy slots changed since its proof")]
    ups = [_addr(w3, source, g) for g in getters]
    if None in ups:
        return [("unread", source, f"EIP-1167 clone of {impl}: {dict(zip(getters, ups))} not all readable")]
    leaves = []
    for u in dict.fromkeys(ups):
        leaves += walk_source(w3, u, specs, own, depth + 1, memo)
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


def controller_of_path(w3, contract, governance_delay, specs=None):
    """A contract the target reads that someone other than the target controls: score its owner(), EIP-1967 admin and
    manager() (an upgradeable RedStone feed behind a ProxyAdmin, for instance), and its beacon's owner(), or the beacon's
    spec when one names who controls it (an AccessControl beacon has no owner())."""
    paths = []
    beacon = _slot(w3, contract, BEACON_SLOT)
    for label, ctrl in (("owner()", _addr(w3, contract, "owner")), ("proxy admin slot", _admin_slot(w3, contract)),
                        ("manager()", _addr(w3, contract, "manager"))):
        if ctrl:
            paths.append(controller_path(w3, ctrl, governance_delay, f"{contract} {label}"))
    if beacon and specs and beacon.lower() in specs:
        paths += specs[beacon.lower()](w3, governance_delay)
    elif beacon:  # whoever owns the beacon swaps the implementation
        paths.append(controller_path(w3, _addr(w3, beacon, "owner"), governance_delay, f"{contract} beacon {beacon} owner()"))
    return paths or [path(f"{contract}", "UNREAD", note="controller vanished between reads")]


def score(w3, rows, governance_delay, specs=None, own=(), notes=None, total=None):
    """rows: [(label, price source or None, value or None)]; a source may be a tuple of addresses (an Euler vault reads its
    router, the adapter for its asset and for each collateral, and the ERC4626 rates it converts through): each is walked
    and the row's value reaches every path any of them leads to; an element "unread: <why>" is an UNREAD part of it. specs: {address lowercase: fn(w3, governance_delay) ->
    [path]}. own: addresses of the target's own governance. total: the priced supply when rows overlap (a GMX market's pool
    on one row per token it prices), else the sum of the rows. Returns the score and appends one note per path."""
    specs = {k.lower(): v for k, v in (specs or {}).items()}
    own = {a.lower() for a in own}
    notes = [] if notes is None else notes
    total = sum(v for _, _, v in rows if v) if total is None else total
    by_key, reach, unknown_value, cache, memo = {}, {}, {}, {}, {}
    for label, source, value in rows:
        if source is None:
            leaves = [("unread", label, "price source unread")]
        else:
            leaves = []
            for s in (source if isinstance(source, tuple) else (source,)):
                if s.startswith("unread:"):  # a part of the row's price that could not be resolved: UNREAD, the rest still walked
                    leaves.append(("unread", label, s[7:].strip()))
                    continue
                if s.lower() not in cache:
                    cache[s.lower()] = walk_source(w3, s, specs, own, memo=memo)
                leaves += cache[s.lower()]
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
                    by_key[key] = controller_of_path(w3, addr, governance_delay, specs)
                elif kind == "constant":
                    by_key[key] = [path(f"{addr}", "constant", note="provable constant: no storage write, no call, no outside state read, no proxy slot")]
                elif kind == "inputless":
                    by_key[key] = [path(f"{addr}", "constant", note="input-less MorphoChainlinkOracleV2, template-pinned: six inputs zero, price() = SCALE_FACTOR()")]
                elif kind == "vault-v2":
                    by_key[key] = vault_v2_share_paths(w3, addr, governance_delay)
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


_POSITION = [{"name": "position", "type": "function", "stateMutability": "view", "inputs": [{"type": "bytes32"}, {"type": "address"}],
              "outputs": [{"type": "uint256"}, {"type": "uint128"}, {"type": "uint128"}]}]
_MARKET = [{"name": "market", "type": "function", "stateMutability": "view", "inputs": [{"type": "bytes32"}], "outputs": [{"type": "uint128"}] * 6}]
_PARAMS = [{"type": "address"}] * 4 + [{"type": "uint256"}]
_B32 = lambda name, *ins: [{"name": name, "type": "function", "stateMutability": "view", "inputs": [{"type": t} for t in ins], "outputs": [{"type": "bytes32"}]}]  # noqa: E731


def blue_rows(w3, morpho, holder, ids, tag="", idle=None):
    """[(market id, oracle, assets `holder` supplies there)] on a Morpho Blue singleton. Markets without an oracle (idle) are
    skipped; a market whose params, position or totals cannot be read is a row with no source and no value (UNREAD). The
    value is in loan-token units: only the shares matter."""
    par_abi = [{"name": "idToMarketParams", "type": "function", "stateMutability": "view", "inputs": [{"type": "bytes32"}], "outputs": _PARAMS}]
    rows = []
    for mid in ids:
        label = f"{tag}{bytes(mid).hex()}"
        params = call_raw(w3, morpho, par_abi, "idToMarketParams", mid)
        pos = call_raw(w3, morpho, _POSITION, "position", mid, Web3.to_checksum_address(holder))
        mkt = call_raw(w3, morpho, _MARKET, "market", mid)
        if params is None or pos is None or mkt is None:
            rows.append((label, None, None))
            continue
        if not int(params[2], 16):  # idle market: no collateral, no price
            if idle is not None:
                idle.append(pos[0] * mkt[0] // mkt[1] if mkt[1] else 0)
            continue
        rows.append((label, Web3.to_checksum_address(params[2]), pos[0] * mkt[0] // mkt[1] if mkt[1] else 0))
    return rows


def morpho_v1_rows(w3, vault):
    """[(market id, oracle, assets the vault supplies there)] for a Morpho V1 vault's withdraw queue, on the singleton the
    vault itself names (MORPHO(), an immutable: 0xBBBB...FFCb on Ethereum and Base, 0xD5D960E8 on Monad). None when MORPHO()
    or the queue length cannot be read."""
    morpho = _addr(w3, vault, "MORPHO")
    n = call_raw(w3, vault, _UINT("withdrawQueueLength"), "withdrawQueueLength")
    if morpho is None or n is None:
        return None
    q_abi = _B32("withdrawQueue", "uint256")
    ids = [call_raw(w3, vault, q_abi, "withdrawQueue", i) for i in range(n)]
    rows = [(f"market {i}", None, None) for i, mid in enumerate(ids) if mid is None]
    return rows + blue_rows(w3, morpho, vault, [m for m in ids if m is not None])


def _adapter_market_ids(w3, adapter):
    """Market ids a MorphoMarketV1Adapter holds: marketIds(i) (MorphoMarketV1AdapterV2) or marketParamsList(i) (the first
    version; id = keccak(abi.encode(params))). None when neither enumerates or one entry is unread."""
    n = call_raw(w3, adapter, _UINT("marketIdsLength"), "marketIdsLength", retries=2)
    if n is not None:
        ids = [call_raw(w3, adapter, _B32("marketIds", "uint256"), "marketIds", i) for i in range(n)]
        return None if None in ids else ids
    n = call_raw(w3, adapter, _UINT("marketParamsListLength"), "marketParamsListLength", retries=2)
    if n is None:
        return None
    mpl = [{"name": "marketParamsList", "type": "function", "stateMutability": "view", "inputs": [{"type": "uint256"}], "outputs": _PARAMS}]
    ids = []
    for i in range(n):
        p = call_raw(w3, adapter, mpl, "marketParamsList", i)
        if p is None:
            return None
        ids.append(Web3.keccak(abi_encode(["address", "address", "address", "address", "uint256"], list(p))))
    return ids


def morpho_v2_rows(w3, vault, notes=None):
    """[(market, oracle, assets)] for a Morpho Vault V2, one entry per adapter (adapters(i)):
    - a MorphoMarketV1Adapter(V2) (morpho() set): its Morpho Blue markets and its own position there, on that singleton;
    - a MorphoVaultV1Adapter (morphoVaultV1() set): the V1 vault's rows scaled by the adapter's share of it;
    - any other adapter: one row with no source and its realAssets() (UNREAD, material when large); skipped with a note when
      realAssets() is exactly 0.
    Idle assets (in the vault itself) are unpriced and left out, as Morpho V1's idle market; a note gives their share. None
    when the adapter list cannot be read."""
    notes = [] if notes is None else notes
    n = call_raw(w3, vault, _UINT("adaptersLength"), "adaptersLength")
    if n is None:
        return None
    rows, allocated = [], {}
    for i in range(n):
        a = _addr(w3, vault, "adapters", i, ins=("uint256",))
        if a is None:
            rows.append((f"adapter {i}", None, None))
            continue
        start = len(rows)
        morpho = _addr(w3, a, "morpho")
        v1 = None if morpho else _addr(w3, a, "morphoVaultV1")
        if morpho:
            ids = _adapter_market_ids(w3, a)
            real = call_raw(w3, a, _UINT("realAssets"), "realAssets")
            if ids is None:
                rows.append((f"adapter {a} (markets unread)", None, real))
            else:
                idle = []
                sub = blue_rows(w3, morpho, a, ids, f"{a[:10]} ", idle)
                rows += sub
                values = [v for _, _, v in sub]
                shown = sum(values + idle) if None not in values else None  # idle-market supply is held, just unpriced
                if real is None:  # what the adapter really holds is unknown: its rows cannot be checked
                    rows.append((f"adapter {a} (realAssets unread)", None, None))
                elif shown is not None and real - shown > real // 100:  # funds the market list does not show
                    rows.append((f"adapter {a} (realAssets {real} above its market rows {shown})", None, real - shown))
        elif v1:
            sub = morpho_v1_rows(w3, v1)
            bal = call_raw(w3, v1, _UINT("balanceOf", "address"), "balanceOf", a)
            supply = call_raw(w3, v1, _UINT("totalSupply"), "totalSupply")
            if sub is None or bal is None or not supply:
                rows.append((f"adapter {a} (V1 vault {v1} unread)", None, None))
            else:
                rows += [(f"{v1[:10]} {label}", src, None if value is None else value * bal // supply) for label, src, value in sub]
        else:
            real = call_raw(w3, a, _UINT("realAssets"), "realAssets")
            if real == 0:
                notes.append(f"adapter {a}: neither a Morpho market nor a Morpho V1 vault adapter, realAssets() = 0: no priced allocation, skipped")
            else:
                rows.append((f"adapter {a} (unknown kind)", None, real))
        values = [v for _, _, v in rows[start:]]
        allocated[a] = None if None in values else sum(values)  # unread rows: the allocation is unknown, not empty
    for a, held in allocated.items():  # nothing priced today but live caps: the allocator can fill it with no timelock
        cid = Web3.keccak(abi_encode(["string", "address"], ["this", a]))
        cap = call_raw(w3, vault, _UINT("absoluteCap", "bytes32"), "absoluteCap", cid)
        rel = call_raw(w3, vault, _UINT("relativeCap", "bytes32"), "relativeCap", cid) if cap else None
        if held == 0 and cap and rel:
            notes.append(f"adapter {a}: no priced allocation today but absoluteCap {cap}: allocators can allocate without a timelock, "
                         "so this field follows today's allocation")
    total = call_raw(w3, vault, _UINT("totalAssets"), "totalAssets")
    asset = _addr(w3, vault, "asset")
    idle = call_raw(w3, asset, _UINT("balanceOf", "address"), "balanceOf", Web3.to_checksum_address(vault)) if asset else None
    notes.append(f"idle assets {idle} of totalAssets {total}" + (f" ({idle / total:.2%})" if idle is not None and total else "")
                 + ": unpriced, left out of the shares")
    return rows


def morpho_v2_governance(w3, vault):
    """(governance delay, own addresses) of a Morpho Vault V2. Delay: the minimum live timelock over the fund-redirecting
    functions and the exit gates still callable (morpho_v2.timelock_and_gates); None when unread, and None when everything
    is abdicated (nothing left to bound, no bar either). Own: none. The owner and the curator act at once on any contract
    they control outside the vault, while the vault's composite credits its timelocks, so a price wrapper they own or manage
    is scored through them, never walked as the vault's own (review of 2026-10-05; Morpho V1 already passes no own set)."""
    delay, _ = morpho_v2.timelock_and_gates(w3, vault, call=call_raw)
    return (None if delay == float("inf") else delay), set()


# Moonwell (a Compound V2 fork) on Base. Read live 2026-10-05: Unitroller 0xfBb21d03, admin() = the TemporalGovernor
# 0x8b621804 (proposalDelay() 86400), oracle() = the ChainlinkOracle 0xEC942bE8 (Blockscout-verified, solc 0.8.19, 4,025
# bytes, no proxy slot): getUnderlyingPrice reads prices[underlying] when set (setUnderlyingPrice, setDirectPrice: onlyAdmin),
# else getFeed(underlying.symbol()); an mToken whose own symbol hashes to nativeToken() reads getFeed(its symbol) instead.
# setFeed and setAdmin are onlyAdmin; admin() = the TemporalGovernor. 21 markets, no override, every feed one of 14
# ChainlinkOEVWrappers (code a9268649..., owner() the TemporalGovernor, priceFeed set only in the constructor; the owner sets
# only fees, maxRoundDelay, maxDecrements and recoveries: own, walked by _owned_by) or 6 immutable ChainlinkCompositeOracles.
MOONWELL_TEMPORAL_GOVERNOR = "0x8b621804a7637b781e2BbD58e256a591F2dF7d51"
MOONWELL_ORACLE = ("0xEC942bE8A8114bFD0396A5052c36027f2cA6a9d0", "71bd27bf1769455c19a40556cd1d3bee966615d5c3c0b9c87f659e31179b57fe")  # address, runtime code hash
# LBTC/BTC ChainlinkBoundedCompositeOracle (the multiplier of the LBTC/USD composite 0xb9059D6A): proxy, implementation,
# ProxyAdmin, each with its runtime code hash (Blockscout-verified OpenZeppelin 4 TransparentUpgradeableProxy and ProxyAdmin,
# ChainlinkBoundedCompositeOracle, all solc 0.8.19), then its four settings, all read live 2026-10-05.
MOONWELL_LBTC_BOUNDED = {
    "proxy": ("0x31d099C106cd73E731972Fdf1390Cab77F59DaDe", "9d17500684ece8a63c40b6372139626a1e9c023a3ea1c758b47a5e5489cfebb0"),
    "implementation": ("0x497e43aF113e71929871C85C56022893B9Ac968C", "0ff74a4e94abb86f94f94ec9e6566c316c1793265fbe625efc1bcf86b8a1c88a"),
    "ProxyAdmin": ("0x8D7d2230A2d195F023588eDd13dBAd56dd69770F", "c66248bc564c89649da8dd5dca4a812d0c5644f4a1d0269490ec74a8dd35c007")}
MOONWELL_LBTC_SETTINGS = {"primaryLBTCOracle": "0x5C4c8d6f6Bf79B718F3e8399AaBdFEd01cB7e48f", "fallbackLBTCOracle": "0x1E6c22AAA11F507af12034A5Dc4126A6A25DC8d2",
                          "lowerBound": 98_000_000, "upperBound": 102_000_000}  # bounds: 8 decimals, 1e8 = one BTC
_STR = lambda name: [{"name": name, "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "string"}]}]  # noqa: E731
_INT = lambda name: [{"name": name, "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "int256"}]}]  # noqa: E731
_hash = lambda w3, a: Web3.keccak(_code(w3, a)).hex().removeprefix("0x")  # noqa: E731


def moonwell_rows(w3, comptroller):
    """[(market, price source, usd)] for every market of getAllMarkets(): value = (getCash + totalBorrows - totalReserves) x
    oracle.getUnderlyingPrice(mToken) / 1e36 (a V2 price carries 36 - decimals). Source: the oracle's own logic, read only
    while its code is the pinned ChainlinkOracle with no proxy slot: getFeed(mToken symbol) on the nativeToken branch, the
    oracle itself when assetPrices(underlying) != 0 (an admin override, judged by its spec), else getFeed(underlying
    symbol). Anything unread is a row with no source. None when the oracle or the market list cannot be read."""
    oracle = _addr(w3, comptroller, "oracle")
    markets = call_raw(w3, comptroller, [{"name": "getAllMarkets", "type": "function", "stateMutability": "view", "inputs": [],
                                          "outputs": [{"type": "address[]"}]}], "getAllMarkets")
    if not oracle or markets is None:
        return None
    pinned = (oracle.lower() == MOONWELL_ORACLE[0].lower() and _hash(w3, oracle) == MOONWELL_ORACLE[1]
              and not any(_slot(w3, oracle, s) for s in PROXY_SLOTS))
    native = call_raw(w3, oracle, _B32("nativeToken"), "nativeToken", retries=2) if pinned else None
    feed = lambda sym: _addr(w3, oracle, "getFeed", sym, ins=("string",))  # noqa: E731
    rows = []
    for m in markets:
        sym, und = call_raw(w3, m, _STR("symbol"), "symbol"), _addr(w3, m, "underlying")
        usym = call_raw(w3, und, _STR("symbol"), "symbol") if und else None
        direct = call_raw(w3, oracle, _UINT("assetPrices", "address"), "assetPrices", und) if und and pinned else None
        price = call_raw(w3, oracle, _UINT("getUnderlyingPrice", "address"), "getUnderlyingPrice", m)
        parts = [call_raw(w3, m, _UINT(g), g) for g in ("getCash", "totalBorrows", "totalReserves")]
        value = (parts[0] + parts[1] - parts[2]) * price / 1e36 if None not in parts and price is not None else None
        if native is None or sym is None:
            src = None
        elif Web3.keccak(text=sym) == bytes(native):
            src = feed(sym)
        else:
            src = oracle if direct else feed(usym) if direct == 0 and usym is not None else None
        rows.append((f"{sym or 'market'} {m}", src, value))
    return rows


def moonwell_governance(w3, comptroller):
    """(governance delay, own addresses): admin() of the Unitroller (the TemporalGovernor) and its proposalDelay(), the wait
    of every proposal it executes (its guardian's fast-track is in the composite). Own: Unitroller, its admin, and its oracle
    while the oracle's admin() is that same admin. Delay None when unread."""
    admin = _addr(w3, comptroller, "admin")
    if admin and admin.lower() != MOONWELL_TEMPORAL_GOVERNOR.lower():  # a moved admin is not the governor the specs and the composite describe
        return None, {comptroller}
    delay = call_raw(w3, admin, _UINT("proposalDelay"), "proposalDelay") if admin else None
    oracle = _addr(w3, comptroller, "oracle")
    own = {a for a in (comptroller, admin) if a}
    if oracle and admin and (_addr(w3, oracle, "admin") or "").lower() == admin.lower():
        own.add(oracle)
    return delay, own


def _moonwell_oracle_override(w3, gov):
    """A market whose price is the ChainlinkOracle's own override (prices[underlying], set by setUnderlyingPrice or
    setDirectPrice, onlyAdmin): own configuration while the oracle's code is the pinned one and its admin() is the
    TemporalGovernor, which the composite already scores. Any other answer is UNREAD."""
    oracle, label = MOONWELL_ORACLE[0], f"Moonwell ChainlinkOracle {MOONWELL_ORACLE[0]} admin price override"
    admin = _addr(w3, oracle, "admin")
    if _hash(w3, oracle) != MOONWELL_ORACLE[1] or (admin or "").lower() != MOONWELL_TEMPORAL_GOVERNOR.lower():
        return [path(label, "UNREAD", note=f"oracle code or admin() {admin} not the verified shape (admin: the TemporalGovernor)")]
    return [path(label, "own", note="setUnderlyingPrice / setDirectPrice onlyAdmin, admin() the TemporalGovernor: already in the composite")]


def _moonwell_lbtc_bounded(w3, gov):
    """LBTC/BTC ChainlinkBoundedCompositeOracle (verified source): latestRoundData() reads primaryLBTCOracle (RedStone
    LBTC_FUNDAMENTAL) and returns it only when its scaled answer lies in [lowerBound, upperBound]; otherwise it returns
    fallbackLBTCOracle (Chainlink LBTC/BTC). setPrimaryOracle, setFallbackOracle and setBounds are onlyOwner, initialize is
    spent (slot 0), and owner() and the ProxyAdmin's owner() are the TemporalGovernor. The primary's controller moves LBTC
    within the band only: bounded (decided 2026-10-05); the fallback is a Chainlink path. Each run: the three code hashes,
    the implementation and admin slots, no beacon, both owners, and the four settings exactly as read; else UNREAD."""
    (proxy, _), (impl, _), (admin, _) = MOONWELL_LBTC_BOUNDED.values()
    label = f"Moonwell LBTC/BTC bounded oracle {proxy}"
    tg = MOONWELL_TEMPORAL_GOVERNOR.lower()
    got = {g: (_addr(w3, proxy, g) if g.endswith("Oracle") else call_raw(w3, proxy, _INT(g), g, retries=2)) for g in MOONWELL_LBTC_SETTINGS}
    facts = {"code": {k: _hash(w3, a) == h for k, (a, h) in MOONWELL_LBTC_BOUNDED.items()},
             "implementation slot": _slot(w3, proxy, IMPL_SLOT), "admin slot": _slot(w3, proxy, ADMIN_SLOT), "beacon": _slot(w3, proxy, BEACON_SLOT),
             "owner": _addr(w3, proxy, "owner"), "ProxyAdmin owner": _addr(w3, admin, "owner"), **got}
    ok = (all(facts["code"].values()) and (facts["implementation slot"] or "").lower() == impl.lower() and (facts["admin slot"] or "").lower() == admin.lower()
          and not facts["beacon"] and not any(_slot(w3, admin, s) for s in PROXY_SLOTS)
          and (facts["owner"] or "").lower() == tg and (facts["ProxyAdmin owner"] or "").lower() == tg
          and all(str(got[k]).lower() == str(v).lower() for k, v in MOONWELL_LBTC_SETTINGS.items()))
    fallback = MOONWELL_LBTC_SETTINGS["fallbackLBTCOracle"]
    if not ok or not _addr(w3, fallback, "aggregator"):
        return [path(label, "UNREAD", note=f"not the verified shape: {facts}")]
    lo, hi = MOONWELL_LBTC_SETTINGS["lowerBound"], MOONWELL_LBTC_SETTINGS["upperBound"]
    return [path(f"{label}: primary {got['primaryLBTCOracle']} (RedStone)", "bounded",
                 note=f"used only inside [{lo}, {hi}] (1e8 = one BTC), band and feeds set by the TemporalGovernor; its controller can "
                      "hold LBTC anywhere in the band, or make it revert (every LBTC price read reverts: a freeze, not a price move)")] + chainlink_path(w3, fallback, gov)


# Their verdicts ("bounded", "own") hold only for a target whose own governance is the TemporalGovernor: for_moonwell adds them,
# no other Base target passes them (a Morpho vault reaching Moonwell's LBTC oracle sees the TemporalGovernor as a foreign controller).
MOONWELL_SPECS = {
    MOONWELL_LBTC_BOUNDED["proxy"][0]: _moonwell_lbtc_bounded,  # Moonwell LBTC/BTC (multiplier of the LBTC/USD composite 0xb9059D6A)
    MOONWELL_ORACLE[0]: _moonwell_oracle_override,               # Moonwell ChainlinkOracle: a row's source only for an admin override
}
BASE_SPECS = {}  # no Base spec applies to every consumer yet


def aave_v2_rows(w3, provider):
    """[(asset, source, value)] for every reserve of an Aave V2 LendingPool (Radiant V2 on Arbitrum). V2 ReserveData is
    (configuration, liquidityIndex, variableBorrowIndex, currentLiquidityRate, currentVariableBorrowRate,
    currentStableBorrowRate, lastUpdateTimestamp, aTokenAddress, stableDebtTokenAddress, variableDebtTokenAddress,
    interestRateStrategyAddress, id): aToken at index 7. Value = aToken totalSupply x getAssetPrice / 10**decimals (oracle
    units: only the shares matter). The AaveOracle reads its fallback oracle whenever a source answers <= 0: a fallback set
    is one more row, valued None (material, walked); an unread one is a row with no source (UNREAD)."""
    pool = _addr(w3, provider, "getLendingPool")
    oracle = _addr(w3, provider, "getPriceOracle")
    if not pool or not oracle:
        return None
    reserves = call_raw(w3, pool, [{"name": "getReservesList", "type": "function", "stateMutability": "view", "inputs": [],
                                    "outputs": [{"type": "address[]"}]}], "getReservesList")
    if reserves is None:
        return None
    data_abi = [{"name": "getReserveData", "type": "function", "stateMutability": "view", "inputs": [{"type": "address"}],
                 "outputs": [{"type": "tuple", "components": [{"type": t} for t in (
                     "uint256", "uint128", "uint128", "uint128", "uint128", "uint128", "uint40",
                     "address", "address", "address", "address", "uint8")]}]}]
    dec_abi = [{"name": "decimals", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "uint8"}]}]
    rows = []
    for asset in reserves:
        src = _addr(w3, oracle, "getSourceOfAsset", asset, ins=("address",))
        price = call_raw(w3, oracle, _UINT("getAssetPrice", "address"), "getAssetPrice", asset)
        data = call_raw(w3, pool, data_abi, "getReserveData", asset)
        dec = call_raw(w3, asset, dec_abi, "decimals")
        value = None
        if data and price is not None and dec is not None:
            ts = call_raw(w3, data[7], _UINT("totalSupply"), "totalSupply")
            value = ts * price / 10 ** dec if ts is not None else None
        rows.append((asset, src, value))
    fallback = call_raw(w3, oracle, _ADDR("getFallbackOracle"), "getFallbackOracle", retries=2)
    if fallback is None:
        rows.append(("fallback oracle (unread)", None, None))
    elif int(fallback, 16):
        rows.append(("fallback oracle (every reserve whose source answers <= 0)", Web3.to_checksum_address(fallback), None))
    return rows


def aave_v2_governance(w3, provider):
    """(governance delay, own addresses) of an Aave V2 market (Radiant): setAssetSources / setFallbackOracle are onlyOwner on
    the AaveOracle, so the delay is that owner's getMinDelay() when it is a timelock, else 0 (a Safe or a key re-points a
    source at once: no governance-grade bar); None when the owner is unread. Own: provider, oracle, provider.owner(),
    provider.getPoolAdmin(), and the oracle owner only when it is one of those two (the roots score_radiant_lendingpool
    scores); otherwise it is returned as `stray`: its instant setAssetSources lever is in no composite."""
    oracle = _addr(w3, provider, "getPriceOracle")
    raw = call_raw(w3, oracle, _ADDR("owner"), "owner", retries=2) if oracle else None
    if raw is None:  # owner() unread or not Ownable: who can re-point a source is unknown
        return None, {a for a in (provider, oracle) if a}, "unread"
    if not int(raw, 16):  # ownership renounced: nobody can re-point a source
        return None, {a for a in (provider, oracle) if a}, None
    owner = Web3.to_checksum_address(raw)
    d = call_raw(w3, owner, _UINT("getMinDelay"), "getMinDelay", retries=2) if _code(w3, owner) else None
    roots = {a for a in (_addr(w3, provider, "owner"), _addr(w3, provider, "getPoolAdmin")) if a}
    stray = None if owner.lower() in {r.lower() for r in roots} else owner
    own = {a for a in (provider, oracle, *roots) if a} | ({owner} if not stray else set())
    return (d if d is not None else 0), own, stray


# GMX V2 Synthetics (Arbitrum). Read live 2026-10-05 (study of that day, re-run by a second reader).
GMX_ROLESTORE = "0x3c3d99FD298f679DBC2CEcd132b4eC4d0F5e6e72"
GMX_DATASTORE = "0xFD70de6b91282D8017aA4E741e9Ae325CAb992d8"
GMX_READER = "0x470fbC46bcC0f16532691Df360A07d8Bf5ee0789"  # stateless Reader, gmx-synthetics deployments/arbitrum/Reader.json
GMX_CHAINLINK_PRICE_FEED_PROVIDER = "0x38B8dB61b724b51e42A88Cb8eC564CD685a0f53B"  # deployments/arbitrum/ChainlinkPriceFeedProvider.json
MULTICALL3 = "0xcA11bde05977b3631167028862bE2a173976CA11"
_gk = lambda s: Web3.keccak(abi_encode(["string"], [s]))  # noqa: E731  GMX Keys.X = keccak256(abi.encode("X"))
_gkey = lambda *tv: Web3.keccak(abi_encode([t for t, _ in tv], [v for _, v in tv]))  # noqa: E731  keccak256(abi.encode(...))
_GMX_MEMBERS = [{"name": "getRoleMembers", "type": "function", "stateMutability": "view", "inputs": [{"type": "bytes32"}, {"type": "uint256"}, {"type": "uint256"}],
                 "outputs": [{"type": "address[]"}]}]
_AGG3 = [{"name": "aggregate3", "type": "function", "stateMutability": "view",
          "inputs": [{"type": "tuple[]", "components": [{"type": "address"}, {"type": "bool"}, {"type": "bytes"}]}],
          "outputs": [{"type": "tuple[]", "components": [{"type": "bool"}, {"type": "bytes"}]}]}]
_fn = lambda name, ins=(), outs=("address",): {"name": name, "type": "function", "stateMutability": "view",  # noqa: E731
                                                "inputs": [{"type": t} for t in ins], "outputs": [{"type": t} for t in outs]}


def _batch(w3, calls, chunk=300, allow_failure=False):
    """[(target, fn abi dict, args)] -> decoded outputs (a scalar for one output, a tuple otherwise) through Multicall3
    aggregate3 (one sequential read per DataStore key hits public-RPC rate limits). allow_failure=False: one failed sub-call
    reverts the batch -> None, never a silent zero. allow_failure=True (getter probing only): a missing getter is None."""
    out = []
    for i in range(0, len(calls), chunk):
        part = calls[i:i + chunk]
        enc = [(Web3.to_checksum_address(t), allow_failure,
                Web3.keccak(text=f"{f['name']}({','.join(x['type'] for x in f['inputs'])})")[:4]
                + abi_encode([x["type"] for x in f["inputs"]], list(a))) for t, f, a in part]
        res = call_raw(w3, MULTICALL3, _AGG3, "aggregate3", enc)
        if res is None or len(res) != len(part):
            return None
        for (t, f, a), (ok, data) in zip(part, res):
            typ = [o["type"] for o in f["outputs"]]
            if not ok or (allow_failure and len(data) != 32 * len(typ)):
                if not allow_failure:
                    return None
                out.append(None)
                continue
            v = eth_abi.decode(typ, data)  # looked up at call time: abi_returndata_guard may patch it after import
            out.append(v[0] if len(v) == 1 else v)
    return out


def _gmx_ds(w3, getter, out, key):
    return call_raw(w3, GMX_DATASTORE, [_fn(getter, ("bytes32",), (out,))], getter, key, retries=2)


def gmx_v2_governance(w3, rolestore=GMX_ROLESTORE):
    """(delay, own, controller, oracle). The live ConfigTimelockController is the ROLE_ADMIN member that another ROLE_ADMIN
    member (TimelockConfig) names in timelockController(), as score_gmx_v2_rolestore resolves it; delay = its getMinDelay()
    (86400 on 2026-10-05); oracle = its oracle() (0x26C02F22, the Oracle every live handler reads; the repo's Oracle.json is
    stale). Nothing resolved: (None, own, None, None)."""
    admins = call_raw(w3, rolestore, _GMX_MEMBERS, "getRoleMembers", _gk("ROLE_ADMIN"), 0, 50) or []
    aset = {a.lower() for a in admins}
    own = {rolestore, GMX_DATASTORE, *admins}
    for m in admins:
        c = _addr(w3, m, "timelockController")
        if c and c.lower() in aset:
            return call_raw(w3, c, _UINT("getMinDelay"), "getMinDelay"), own, c, _addr(w3, c, "oracle")
    return None, own, None, None


def _gmx_atomic_withdrawal_on(w3, oracle, rolestore=GMX_ROLESTORE):
    """True when a CONTROLLER WithdrawalHandler (answers withdrawalVault()) reads `oracle` and its
    EXECUTE_ATOMIC_WITHDRAWAL_FEATURE_DISABLED flag is off (two handlers, both on, 2026-10-05). Raises on a failed read."""
    members = call_raw(w3, rolestore, _GMX_MEMBERS, "getRoleMembers", _gk("CONTROLLER"), 0, 500)
    if members is None:
        raise RuntimeError("CONTROLLER members unread")
    got = _batch(w3, [(a, _fn(g), ()) for a in members for g in ("withdrawalVault", "oracle")], allow_failure=True)
    if got is None:
        raise RuntimeError("CONTROLLER getters unread")
    for i, a in enumerate(members):
        vault, orc = got[2 * i], got[2 * i + 1]
        if vault and int(vault, 16) and orc and orc.lower() == oracle.lower():
            off = _gmx_ds(w3, "getBool", "bool", _gkey(("bytes32", _gk("EXECUTE_ATOMIC_WITHDRAWAL_FEATURE_DISABLED")), ("address", a)))
            if off is None:
                raise RuntimeError(f"atomic withdrawal flag of {a} unread")
            if off is False:
                return True
    return False


def gmx_v2_rows(w3, oracle):
    """(rows, priced supply) for GMX V2 Synthetics; None when a batch fails.
    Per token of any market (index, long, short): source = DataStore ORACLE_PROVIDER_FOR_TOKEN(oracle, token), the only
    provider Oracle._validatePrices accepts for a non-atomic action; value = its pool amounts over all markets (priced with
    the token's PRICE_FEED latestRoundData x PRICE_FEED_MULTIPLIER / 1e60 = USD per smallest unit; no PRICE_FEED and a
    non-zero pool -> None, material) + the OPEN_INTEREST (USD, 30 decimals) of the markets it indexes. A token with no
    provider is skipped: the Oracle accepts no price for it. These rows are the priced supply.
    Atomic actions (WithdrawalHandler.executeAtomicWithdrawal, relay fee swaps) take ANY enabled atomic provider: when the
    ChainlinkPriceFeedProvider is enabled and atomic and an atomic withdrawal is on for this oracle, every market whose
    tokens all have a PRICE_FEED adds one row per token (source = that Chainlink proxy, value = the market's pool). They
    overlap the provider rows, so the priced supply is returned for score(total=). IS_ATOMIC_ORACLE_PROVIDER is not
    enumerable: only the known ChainlinkPriceFeedProvider is checked (making another provider atomic is a 24 h TimelockConfig
    signal of the target's own governance)."""
    n = call_raw(w3, GMX_DATASTORE, _UINT("getAddressCount", "bytes32"), "getAddressCount", _gk("MARKET_LIST"))
    lst = call_raw(w3, GMX_DATASTORE, [_fn("getAddressValuesAt", ("bytes32", "uint256", "uint256"), ("address[]",))],
                   "getAddressValuesAt", _gk("MARKET_LIST"), 0, n) if n is not None else None
    if lst is None or len(lst) != n:
        return None
    get_market = {"name": "getMarket", "type": "function", "stateMutability": "view", "inputs": [{"type": "address"}, {"type": "address"}],
                  "outputs": [{"type": "(address,address,address,address)"}]}
    mk = _batch(w3, [(GMX_READER, get_market, (GMX_DATASTORE, m)) for m in lst])
    if mk is None:
        return None
    markets = [tuple(Web3.to_checksum_address(x) for x in r) for r in mk]  # (market token, index, long, short)
    get_uint, get_addr = _fn("getUint", ("bytes32",), ("uint256",)), _fn("getAddress", ("bytes32",))
    calls, keys = [], []
    for mt, index, long_, short in markets:
        legs = sorted({long_, short})
        for t in legs:
            keys.append(("pool", mt, t))
            calls.append((GMX_DATASTORE, get_uint, (_gkey(("bytes32", _gk("POOL_AMOUNT")), ("address", mt), ("address", t)),)))
        if int(index, 16):
            for c in legs:
                for is_long in (True, False):
                    keys.append(("oi", mt, index))
                    calls.append((GMX_DATASTORE, get_uint, (_gkey(("bytes32", _gk("OPEN_INTEREST")), ("address", mt), ("address", c), ("bool", is_long)),)))
    tokens = sorted({t for m in markets for t in m[1:] if int(t, 16)})
    for t in tokens:
        for kind, fn, key in (("feed", get_addr, _gkey(("bytes32", _gk("PRICE_FEED")), ("address", t))),
                              ("mult", get_uint, _gkey(("bytes32", _gk("PRICE_FEED_MULTIPLIER")), ("address", t))),
                              ("prov", get_addr, _gkey(("bytes32", _gk("ORACLE_PROVIDER_FOR_TOKEN")), ("address", oracle), ("address", t)))):
            keys.append((kind, t, None))
            calls.append((GMX_DATASTORE, fn, (key,)))
    vals = _batch(w3, calls)
    if vals is None:
        return None
    pool, oi, feed, mult, prov = {}, {}, {}, {}, {}
    for (kind, a, b), v in zip(keys, vals):
        if kind == "pool":
            pool[(a, b)] = v
        elif kind == "oi":
            oi[(a, b)] = oi.get((a, b), 0) + v
        else:
            {"feed": feed, "mult": mult, "prov": prov}[kind][a] = v if kind == "mult" else Web3.to_checksum_address(v)
    zero = lambda a: int(a, 16) == 0  # noqa: E731
    with_feed = [t for t in tokens if not zero(feed[t])]
    rd = _fn("latestRoundData", (), ("uint80", "int256", "uint256", "uint256", "uint80"))
    rounds = _batch(w3, [(feed[t], rd, ()) for t in with_feed], chunk=50)
    if rounds is None:
        return None
    price = {t: (r[1] * mult[t] / 1e60 if r[1] > 0 and mult[t] else None) for t, r in zip(with_feed, rounds)}
    value, unknown = {}, set()
    for (mt, t), amt in pool.items():
        if amt and price.get(t) is None:
            unknown.add(t)
        value[t] = value.get(t, 0) + (amt * price[t] if amt and price.get(t) is not None else 0)
    for (mt, idx), v in oi.items():
        value[idx] = value.get(idx, 0) + v / 1e30
    rows = [(f"{t} (Oracle provider)", prov[t], None if t in unknown else value.get(t, 0)) for t in tokens if not zero(prov[t])]
    if markets and not rows:  # markets but no token the resolved Oracle can price: a wrong or stale oracle, unknown
        return None
    total = sum(v for _, _, v in rows if v)
    pf = GMX_CHAINLINK_PRICE_FEED_PROVIDER
    enabled = _gmx_ds(w3, "getBool", "bool", _gkey(("bytes32", _gk("IS_ORACLE_PROVIDER_ENABLED")), ("address", pf)))
    atomic = _gmx_ds(w3, "getBool", "bool", _gkey(("bytes32", _gk("IS_ATOMIC_ORACLE_PROVIDER")), ("address", pf)))
    if enabled is None or atomic is None:
        return None
    if enabled and atomic and _gmx_atomic_withdrawal_on(w3, oracle):
        for mt, index, long_, short in markets:
            toks = sorted(t for t in {index, long_, short} if not zero(t))
            if toks and all(t in price for t in toks):
                legs = {long_, short}
                usd = None if any(pool[(mt, t)] and price[t] is None for t in legs) else sum(pool[(mt, t)] * price[t] for t in legs if pool[(mt, t)])
                rows += [(f"{mt} atomic withdrawal {t}", feed[t], usd) for t in toks]
    return rows, total


GMX_V1_VAULT = "0x489ee077994B6658eAfA855C308275EAd8097C4A"
GMX_V1_VAULT_PRICE_FEED = "0x2d68011bcA022ed0E474264145F46CC4de96a002"
GMX_V1_PRICE_FEED_TIMELOCK = "0x7b1FFdDEEc3C4797079C7ed91057e399e9D43a8B"  # VaultPriceFeed.gov() and FastPriceFeed.gov()


def gmx_v1_rows(w3, vault=GMX_V1_VAULT):
    """(rows, priced supply) for the GMX V1 Vault; None when priceFeed() or the token count is unread. Per WHITELISTED token
    (allWhitelistedTokens(i) with whitelistedTokens(t) true; a delisted token such as MIM is skipped: GlpManager.getAum and
    the Vault ignore it): source = VaultPriceFeed.priceFeeds(token) (the Chainlink proxy of the primary price), value =
    poolAmounts(t) x getMaxPrice(t) / 1e30 / 10^tokenDecimals(t). Plus one row for the VaultPriceFeed itself, valued at the
    whole pool (None when a token is unread): its governor can switch every token at once to the keeper-fed secondary
    price or re-peg the strict stablecoins. That row overlaps the token rows: the priced supply is their sum."""
    vpf = _addr(w3, vault, "priceFeed")
    n = call_raw(w3, vault, _UINT("allWhitelistedTokensLength"), "allWhitelistedTokensLength")
    if not vpf or n is None:
        return None
    rows, total = [], 0
    for i in range(n):
        t = _addr(w3, vault, "allWhitelistedTokens", i, ins=("uint256",))
        if t is None:
            rows.append((f"whitelisted token {i}", None, None))
            total = None
            continue
        listed = call_raw(w3, vault, _BOOL("whitelistedTokens", "address"), "whitelistedTokens", t)
        if listed is None:  # unknown whether the Vault still prices it: a row with no source, the total unknown
            rows.append((t, None, None))
            total = None
            continue
        if listed is not True:
            continue
        feed = _addr(w3, vpf, "priceFeeds", t, ins=("address",))
        pool = call_raw(w3, vault, _UINT("poolAmounts", "address"), "poolAmounts", t)
        price = call_raw(w3, vault, _UINT("getMaxPrice", "address"), "getMaxPrice", t)
        dec = call_raw(w3, vault, _UINT("tokenDecimals", "address"), "tokenDecimals", t)
        usd = pool * price / 1e30 / 10 ** dec if None not in (pool, price, dec) else None
        total = None if usd is None or total is None else total + usd
        rows.append((t, feed, usd))
    rows.append(("VaultPriceFeed configuration (all tokens)", vpf, total))
    return rows, sum(v for _, _, v in rows[:-1] if v)


# ------------------------------------------------------------------------------------------------- verified specs
# Each spec re-reads, every run, the facts that keep its classification (research of 2026-10-04, each fact re-checked by a
# second, independent pass); any other answer gives UNREAD.
_cs = lambda a: Web3.to_checksum_address(a.lower())  # noqa: E731


# ------------------------------------------------------------------------------------------------- Dolomite (Arbitrum)
# DolomiteMargin values every account with getMarketPrice(id) = getMarketPriceOracle(id).getPrice(token) and liquidates on it.
# Read live 2026-10-05 (77 markets): 76 read the OracleAggregatorV2 0xBfca44aB, whose getPrice sums each getOraclesByToken
# entry's price x weight / 100 with no cap (verified source), so ONE entry's oracle moves the whole market; market 41 reads
# an AdminPauseMarket. Dolomite's own oracles answer DOLOMITE_MARGIN() and their setters are onlyDolomiteMarginOwner (_owned_by).
DOLOMITE_MARGIN_ARB = "0x6Bd780E7fDf01D77e4d475c821f1e7AE05409072"
DOLOMITE_OWNER_V2_CODE_HASH = "818d423adf7eb351ffed39f4b8546c7a2138ee2162f6af7606e4c5e8bd7afe99"  # 0xC2B66E24, 13,011 bytes
# DolomiteOwnerV2 (Sourcify exact match) holds a queued call secondsTimeLocked() (300 s), but executeTransaction(id), open to any
# EXECUTOR_ROLE holder, skips that wait when the caller also holds BYPASS_TIMELOCK_ROLE, whoever queued the call. Plain
# AccessControl (getRoleAddresses returns a role's allowed DESTINATIONS, not its members): its RoleGranted / RoleRevoked history,
# replayed from block 0 to 511886172 on 2026-10-05 (13 grants and 2 revokes of the role), leaves these 11 holding both roles,
# the Safe 0x53D93b9C among them: it can execute any queued call, the DEFAULT_ADMIN's included, at once (governance delay 0).
DOLOMITE_BYPASS_EXECUTORS = (
    "0x53d93b9cd019311cabf031e52cdaeed795f9a825", "0x0a52bcb532f59f6a37a9d3b5bc9ffd47e461d995", "0x107cfc6ab0776d8c9d452f44a24853bec87ddbc5",
    "0x29cf6e8ecefb8d3c9dd2b727c1b7d1df1a754f6f", "0x444868b6e8079ac2c55eea115250f92c2b2c4d14", "0x47c8d387bc491da62053dff6acfbf225f0ee74bc",
    "0x6dbd962b4f62d18f756b5de57425574c4b8228d6", "0x73d25bf215a7487badc695d7ada30f1ad509d642", "0xf2d2d55daf93b0660297eaa10969ebe90ead5ce8",
    "0xf73632b4834be5b4aa1ab44c6398359fd482278e", "0xf7b5127b510e568fdc39e6bb54e2081bfad489af")
_DOLO_ENTRIES = [{"name": "getOraclesByToken", "type": "function", "stateMutability": "view", "inputs": [{"type": "address"}],
                  "outputs": [{"type": "tuple[]", "components": [{"type": "address"}, {"type": "address"}, {"type": "uint256"}]}]}]


def dolomite_governance(w3, margin):
    """(delay, own, why); own = {margin, owner()}. Delay 0 while one pinned bypass executor still holds BYPASS_TIMELOCK_ROLE
    and EXECUTOR_ROLE (hasRole, each run); None (no governance-grade bar) when owner() is not the pinned DolomiteOwnerV2 or no
    pinned holder still holds both (the set is to re-derive: with no bypass the delay would be secondsTimeLocked())."""
    owner = _addr(w3, margin, "owner")
    own = {a for a in (margin, owner) if a}
    if not owner or Web3.keccak(_code(w3, owner)).hex().removeprefix("0x") != DOLOMITE_OWNER_V2_CODE_HASH:
        return None, own, f"owner() {owner} is not the pinned DolomiteOwnerV2"
    secs = call_raw(w3, owner, _UINT("secondsTimeLocked"), "secondsTimeLocked", retries=2)
    has = lambda r, h: call_raw(w3, owner, _BOOL("hasRole", "bytes32", "address"), "hasRole", Web3.keccak(text=r), _cs(h), retries=2) is True  # noqa: E731
    by = next((h for h in DOLOMITE_BYPASS_EXECUTORS if has("BYPASS_TIMELOCK_ROLE", h) and has("EXECUTOR_ROLE", h)), None)
    if by:
        return 0, own, f"DolomiteOwnerV2 secondsTimeLocked() {secs}s, skipped by the BYPASS_TIMELOCK_ROLE executor {_cs(by)}"
    return None, own, f"DolomiteOwnerV2 secondsTimeLocked() {secs}s; no pinned bypass executor holds both roles any more: re-derive"


def dolomite_rows(w3, margin, own, notes):
    """(rows, priced supply) for DolomiteMargin; None when the market count or the market batch is unread. A market's value =
    supply par x supply index / 1e18 x getMarketPrice / 1e36 (USD); a getMarketPrice that reverts (a frozen market) or a failed
    read leaves it None: the market stays, counted material. Sources: an oracle answering getOraclesByToken (OracleAggregatorV2)
    gives one row per entry, each at the WHOLE market value, an entry's tokenPair expanded the same way; an own oracle
    (_owned_by) is read through to its getAggregatorByToken(token) feed when it has one; a GmxV2MarketTokenPriceOracle
    (marketTokens(token) true) is its own row (GMX Reader and DataStore, a spec) plus its LONG_TOKEN, SHORT_TOKEN and index
    token, expanded through the aggregator its REGISTRY's dolomiteRegistry() names (the one it reads); any other oracle is its
    own source. One row per (market, source); rows overlap, so the priced supply (each market once) goes to score(total=)."""
    n = call_raw(w3, margin, _UINT("getNumMarkets"), "getNumMarkets")
    fns = (_fn("getMarketTokenAddress", ("uint256",)), _fn("getMarketPriceOracle", ("uint256",)),
           _fn("getMarketTotalPar", ("uint256",), ("uint128", "uint128")), _fn("getMarketCurrentIndex", ("uint256",), ("uint96", "uint96", "uint32")),
           _fn("getMarketPrice", ("uint256",), ("uint256",)))
    got = _batch(w3, [(margin, f, (i,)) for i in range(n) for f in fns], allow_failure=True) if n is not None else None
    if got is None:
        return None
    owned, own = {}, {a.lower() for a in own}  # _owned_by compares lowercase

    def source(oracle, token, label, usd, out, depth):
        if call_raw(w3, oracle, _BOOL("marketTokens", "address"), "marketTokens", token, retries=2) is True:
            reg = _addr(w3, oracle, "REGISTRY")
            dreg = reg and _addr(w3, reg, "dolomiteRegistry")
            agg = dreg and _addr(w3, dreg, "oracleAggregator")
            und = _addr(w3, token, "UNDERLYING_TOKEN")
            legs = (_addr(w3, token, "LONG_TOKEN"), _addr(w3, token, "SHORT_TOKEN"), reg and und and _addr(w3, reg, "gmxMarketToIndexToken", und, ins=("address",)))
            out.append((f"{label} GM price (GMX Reader and DataStore)", oracle, usd))
            for leg, t in zip(("long", "short", "index"), legs):
                expand(agg, t, f"{label} {leg}", usd, out, depth + 1) if agg and t else out.append((f"{label} {leg} token or aggregator unread", None, usd))
            return
        if oracle.lower() not in owned:
            owned[oracle.lower()] = _owned_by(w3, oracle, own)
        feed = _addr(w3, oracle, "getAggregatorByToken", token, ins=("address",)) if owned[oracle.lower()] else None
        out.append((label, feed or oracle, usd))

    def expand(agg, token, label, usd, out, depth=0):
        entries = call_raw(w3, agg, _DOLO_ENTRIES, "getOraclesByToken", token, retries=2) if depth < 5 else None
        if entries is None and depth == 0:  # the market's oracle is not an aggregator: it is the source
            return source(agg, token, label, usd, out, depth)
        if not entries:
            return out.append((f"{label}: no oracle entry for {token} on {agg}", None, usd))
        for oracle, pair, _ in entries:
            source(_cs(oracle), token, label, usd, out, depth)
            if int(pair, 16):
                expand(agg, _cs(pair), f"{label} pair", usd, out, depth + 1)

    rows, total = [], 0
    for i in range(n):
        token, oracle, par, idx, price = got[5 * i:5 * i + 5]
        supply = par[1] * idx[1] // 10 ** 18 if par and idx else None
        if supply == 0:
            continue  # nothing deposited: nothing priced
        usd = supply * price / 1e36 if supply is not None and price else None
        if price is None:
            notes.append(f"market {i} {token}: getMarketPrice reverts (frozen market), supply par {par and par[1]}: value unknown, counted material")
        total += usd or 0
        label, out, seen = f"market {i} {token}", [], set()
        expand(_cs(oracle), _cs(token), label, usd, out) if token and oracle else out.append((label, None, usd))
        rows += [r for r in out if r[1] is None or not (r[1].lower() in seen or seen.add(r[1].lower()))]
    return rows, total


DOLOMITE_CONSTANT_PRICE_ORACLE = ("0xbd51A7Ec5ac75329FCC4E4e74894Ad3a39595614", "d57432f00b48e7478714d11ff8afe81d8f2f8ce62914aa0f938c6607f08006b5")


def _dolomite_constant_price(w3, gov):
    """Dolomite ConstantPriceOracle (verified source, 2,472 bytes): getPrice returns _tokenToPriceMap[token], written only by
    ownerSetTokenPrice, onlyDolomiteMarginOwner: the target's own configuration. Each run: code hash, no proxy slot,
    DOLOMITE_MARGIN() the Arbitrum DolomiteMargin; any other answer UNREAD."""
    a, h = DOLOMITE_CONSTANT_PRICE_ORACLE
    code, dm = _fixed_code(w3, a), _addr(w3, a, "DOLOMITE_MARGIN")
    if code is None or Web3.keccak(code).hex().removeprefix("0x") != h or not dm or dm.lower() != DOLOMITE_MARGIN_ARB.lower():
        return [path("Dolomite ConstantPriceOracle", "UNREAD", note=f"code, proxy slots or DOLOMITE_MARGIN() {dm}: not the 2026-10-05 shape")]
    return [path("Dolomite ConstantPriceOracle", "own", note="ownerSetTokenPrice is onlyDolomiteMarginOwner: already in the composite")]


# GmxV2MarketTokenPriceOracle 0xF6cB6348 (verified source, no proxy slot): GM price = REGISTRY.gmxReader().getMarketTokenPrice(
# gmxDataStore(), market, Dolomite's own index / long / short prices, MAX_PNL_FACTOR_FOR_DEPOSITS, false), cut by the DataStore
# SWAP_FEE_FACTOR(market, false). REGISTRY 0xaDC1A8AD is a RegistryProxy (verified, upgradeTo onlyDolomiteMarginOwner, no admin
# slot). Reader 0xfA26cBb4 (Blockscout-verified, solc 0.8.29) delegates to the MarketUtils library 0x0b34021E linked in its
# code (verified, the same 48 sources). Code hashes read live 2026-10-05.
DOLOMITE_GM_ORACLE = ("0xF6cB6348716e27e86189730B71F7DB27Fd1048Cc", "b03f563309717949126a7d0d2ada2182b17856444caf502b5677256a7ef1ca7b")
DOLOMITE_GMX_REGISTRY = ("0xaDC1A8AD79E55Ab9E8569e497775B63e737316A8", "09c2e34179e30cff7a7a0ae6a71c5f5d9fb527c0a90486236e2d77c7efd31a22")
DOLOMITE_GMX_READER = ("0xfA26cBb46e2614609406de08CA1Dc7f70a684184", "49ed1cb374dfbcea8c73fb50821b5e0bb3fbbe83f4324d954ef07c38758ac04a")
GMX_CONFIG = "0x233720Ccdec5514e2f5b68500C27A3e17571eF86"
# Key-by-key proof of 2026-10-05 (decision 7), over every DataStore key MarketUtils.getPoolValueInfo and the Dolomite oracle
# read. Not settable by a keeper: POOL_AMOUNT, OPEN_INTEREST(_IN_TOKENS), CUMULATIVE_BORROWING_FACTOR(_UPDATED_AT),
# TOTAL_BORROWING, POSITION_IMPACT_POOL_AMOUNT, LENT_POSITION_IMPACT_POOL_AMOUNT (handlers). Bounded by
# ConfigUtils.validateRange: BORROWING_FACTOR, BASE_BORROWING_FACTOR (5e-8 / s), ABOVE_OPTIMAL_USAGE_BORROWING_FACTOR (1e-7 / s).
# NOT bounded, each set at once by a CONFIG_KEEPER through Config (allowedBaseKeys): the keys below. No key of
# allowedLimitedBaseKeys (LIMITED_CONFIG_KEEPER) is read; RiskOracleConfig's RISK_ORACLE reaches OPTIMAL_USAGE_FACTOR too.
GMX_GM_UNBOUNDED_KEYS = {
    "OPEN_INTEREST_RESERVE_FACTOR": "no lower bound: 0 makes getMarketTokenPrice revert (a zero divisor in getUsageFactor), "
                                    "1 wei multiplies the kink model's usage factor up to 1e30-fold, so pending borrowing fees, added to the pool value, have no cap",
    "OPTIMAL_USAGE_FACTOR": "0 switches to the exponent model: rate = BORROWING_FACTOR x reservedUsd^BORROWING_EXPONENT_FACTOR / poolUsd",
    "BORROWING_EXPONENT_FACTOR": "up to 2: reserved USD squared, a per-second rate of several % on a market of a few million USD",
    "MAX_PNL_FACTOR": "0 to 100% (MAX_PNL_FACTOR_FOR_DEPOSITS): the traders' positive PnL is uncapped or capped at will",
    "BORROWING_FEE_RECEIVER_FACTOR": "0 to 100%: the pending borrowing fees credited to the pool",
    "SWAP_FEE_FACTOR": "up to 5%: the Dolomite oracle's own downward cut (a downward-only lever, scored: decision 4)",
}


def _dolomite_gm_price(w3, gov):
    """The GM price path: every run checks the pinned code of the Dolomite oracle, its RegistryProxy and the GMX Reader (no
    proxy slot on the oracle and the Reader), the registry's gmxReader() / gmxDataStore() and DOLOMITE_MARGIN(), and the
    DataStore's roleStore(); any other answer is one UNREAD path. Then each RoleStore ROLE_ADMIN member (it grants CONTROLLER:
    any DataStore write) is scored with controller_path, and the CONFIG_KEEPER surface is UNREAD: the key-by-key proof of
    2026-10-05 failed (GMX_GM_UNBOUNDED_KEYS), so it is neither bounded nor scored by its weakest keeper (decision 7)."""
    label = "Dolomite GM price (GMX Reader and DataStore)"
    (o, oh), (reg, rh), (rd, dh) = DOLOMITE_GM_ORACLE, DOLOMITE_GMX_REGISTRY, DOLOMITE_GMX_READER
    hashed = lambda a: Web3.keccak(_code(w3, a)).hex().removeprefix("0x")  # noqa: E731
    facts = {"oracle code": hashed(o) == oh and _fixed_code(w3, o) is not None, "registry code": hashed(reg) == rh,
             "reader code": hashed(rd) == dh and _fixed_code(w3, rd) is not None,
             "REGISTRY()": (_addr(w3, o, "REGISTRY") or "").lower() == reg.lower(),
             "DOLOMITE_MARGIN()": all((_addr(w3, a, "DOLOMITE_MARGIN") or "").lower() == DOLOMITE_MARGIN_ARB.lower() for a in (o, reg)),
             "gmxReader()": (_addr(w3, reg, "gmxReader") or "").lower() == rd.lower(),
             "gmxDataStore()": (_addr(w3, reg, "gmxDataStore") or "").lower() == GMX_DATASTORE.lower(),
             "roleStore()": (_addr(w3, GMX_DATASTORE, "roleStore") or "").lower() == GMX_ROLESTORE.lower()}
    if not all(facts.values()):
        return [path(label, "UNREAD", note=f"not the 2026-10-05 shape: {[k for k, ok in facts.items() if not ok]}")]
    admins = call_raw(w3, GMX_ROLESTORE, _GMX_MEMBERS, "getRoleMembers", _gk("ROLE_ADMIN"), 0, 50)
    keepers = call_raw(w3, GMX_ROLESTORE, _GMX_MEMBERS, "getRoleMembers", _gk("CONFIG_KEEPER"), 0, 100)
    paths = [controller_path(w3, a, gov, f"GMX RoleStore ROLE_ADMIN {a} (grants CONTROLLER: any DataStore write)") for a in admins or ()]
    if not admins:
        paths.append(path("GMX RoleStore ROLE_ADMIN", "UNREAD", note="members unread"))
    return paths + [path("GMX CONFIG_KEEPER keys of the GM price (Config, immediate)", "UNREAD",
                         note=f"{len(keepers) if keepers is not None else 'unread'} CONFIG_KEEPER member(s) set through Config {GMX_CONFIG}, at "
                              f"once, keys with no tight bound: {GMX_GM_UNBOUNDED_KEYS}")]


_R = lambda h: bytes.fromhex(h[2:] if h.startswith("0x") else h)  # noqa: E731


def _etherfi_weeth(w3, gov):
    """weETH's rate (LiquidityPool.amountForShare) moves only by an EtherFiAdmin rebase bounded by an APR cap whose maximum
    is immutable; the bound and every upgrade sit behind EtherFi's OPERATION (2 d) and UPGRADE (10 d) timelocks. OPERATION
    also holds two RoleRegistry roles not identified (0x684a419d..., 0x4d730356...), so each timelock is a controller path:
    governance-grade at or above the target's delay, else its pinned proposer scored behind its delay (controller_path)."""
    rr = _cs("0x62247D29B4B9BECf4BB73E0c722cf6445cfC7cE9")
    roles = {"UPGRADE_TIMELOCK_ROLE": ("0x5ba17a247620ef8426ae0fffc28eee4ee4b18eb3b8bcfa95664565c35371dfb5", _cs("0x9f26d4C958fD811A1F59B01B86Be7dFFc9d20761")),
             "OPERATION_TIMELOCK_ROLE": ("0xe6bda0fc5c63b525e475d178ed9c7fa9913b3429ade866197b11eb0f2c18c673", _cs("0xcD425f44758a08BaAB3C4908f3e3dE5776e45d7a"))}
    holders_abi = [{"name": "roleHolders", "type": "function", "stateMutability": "view", "inputs": [{"type": "bytes32"}], "outputs": [{"type": "address[]"}]}]
    rr_owner = _addr(w3, rr, "owner")  # the RoleRegistry owner can grant both roles: it must be the UPGRADE timelock
    if not rr_owner or rr_owner.lower() != roles["UPGRADE_TIMELOCK_ROLE"][1].lower():
        return [path("weETH rate (EtherFi)", "UNREAD", note=f"RoleRegistry owner {rr_owner}, expected the UPGRADE timelock")]
    for name, (role, tl) in roles.items():
        holders = call_raw(w3, rr, holders_abi, "roleHolders", _R(role))
        if holders is None or [h.lower() for h in holders] != [tl.lower()]:
            return [path("weETH rate (EtherFi)", "UNREAD", note=f"{name}: holders {holders} -- not the verified shape")]
    max_apr = call_raw(w3, _cs("0x0EF8fa4760Db8f5Cd4d993f3e3416f30f942D705"), [{"name": "maxAcceptableRebaseAprInBps", "type": "function",
                       "stateMutability": "view", "inputs": [], "outputs": [{"type": "int256"}]}], "maxAcceptableRebaseAprInBps")
    if max_apr != 1000:
        return [path("weETH rate (EtherFi)", "UNREAD", note=f"rebase APR cap maximum {max_apr}, expected the immutable 1000")]
    paths = [controller_path(w3, tl, gov, f"weETH rate (EtherFi) {name} timelock {tl}") for name, (_, tl) in roles.items()]
    for p in paths:
        p["note"] += "; rebase bounded (APR cap max 1000 bps, immutable)"
    return paths


LIDO_VOTING_IMPL = ("0xf165148978Fa3cE74d76043f833463c340CFB704", "c7fddc2dd2b87683ff73783d412a6815c4d779d7953d2d8b704778f219f197d1")  # read live 2026-10-05
_VOTE_TIME = [{"name": "voteTime", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "uint64"}]}]
_PROPOSERS = [{"name": "getProposers", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [
    {"type": "tuple[]", "components": [{"type": "address"}, {"type": "address"}]}]}]


def _lido_steth(w3, gov):
    """stETH's share rate moves by AccountingOracle reports (HashConsensus quorum) bounded by OracleReportSanityChecker; the
    limits, roles and upgrades belong to the Lido Agent, executable only by the Dual Governance executor behind the
    EmergencyProtectedTimelock. The delay counted is the whole window a DAO proposal must cross from its first public
    on-chain step (decided 2026-10-05): Aragon Voting voteTime() (the pinned Voting implementation cannot execute before
    the vote is closed: _canExecute requires VotePhase.Closed) + afterSubmit + afterSchedule, with Voting the only Dual
    Governance proposer; afterSchedule is left out while emergency protection is on (the committees' emergencyExecute
    skips it)."""
    tl, ex = _cs("0xCE0425301C85c5Ea2A0873A2dEe44d78E02D2316"), _cs("0x23E0B465633fF5178808F4A75186E2F2F9537021")
    acl, agent, voting = _cs("0x9895F0F17cc1d1891b6f18ee0b483B6f221b37Bb"), _cs("0x3e40D73EB977Dc6a537aF587D48316feE66E9C8c"), _cs("0x2e59A20f205bB85a89C53f1936454680651E618e")
    execute = Web3.keccak(text="EXECUTE_ROLE")
    perm = lambda who: call_raw(w3, acl, _BOOL("hasPermission", "address", "address", "bytes32"), "hasPermission", who, agent, execute)  # noqa: E731
    after = call_raw(w3, tl, _UINT("getAfterSubmitDelay"), "getAfterSubmitDelay")
    after_schedule = call_raw(w3, tl, _UINT("getAfterScheduleDelay"), "getAfterScheduleDelay")
    protection = call_raw(w3, tl, _BOOL("isEmergencyProtectionEnabled"), "isEmergencyProtectionEnabled")
    vote = call_raw(w3, voting, _VOTE_TIME, "voteTime")
    emergency = call_raw(w3, tl, _BOOL("isEmergencyModeActive"), "isEmergencyModeActive")
    ex_owner = _addr(w3, ex, "owner")
    dg = _addr(w3, tl, "getGovernance")
    proposers = call_raw(w3, dg, _PROPOSERS, "getProposers") if dg else None
    impl = _addr(w3, voting, "implementation")
    run_script = Web3.keccak(text="RUN_SCRIPT_ROLE")
    facts = {"afterSubmit": after, "afterSchedule": after_schedule, "voteTime": vote, "emergency": emergency, "protection": protection, "executor owner": ex_owner,
             "executor EXECUTE": perm(ex), "Voting EXECUTE": perm(voting), "DG proposers": proposers, "Voting implementation": impl,
             "Voting RUN_SCRIPT": call_raw(w3, acl, _BOOL("hasPermission", "address", "address", "bytes32"), "hasPermission", voting, agent, run_script)}
    # While emergency protection is on, the activation and execution committees can run a scheduled proposal at once
    # (emergencyExecute skips afterSchedule): the window then ends at afterSubmit.
    stages = (vote, after) if protection else (vote, after, after_schedule)
    window = sum(stages) if protection is not None and None not in stages else None
    impl_ok = impl and impl.lower() == LIDO_VOTING_IMPL[0].lower() and Web3.keccak(_code(w3, impl)).hex().removeprefix("0x") == LIDO_VOTING_IMPL[1]
    only_voting = proposers is not None and [(a.lower(), e.lower()) for a, e in proposers] == [(voting.lower(), ex.lower())]
    ok = (window and gov and window >= gov and emergency is False and ex_owner and ex_owner.lower() == tl.lower() and impl_ok and only_voting
          and facts["executor EXECUTE"] is True and facts["Voting EXECUTE"] is False and facts["Voting RUN_SCRIPT"] is False)
    if not ok:
        return [path("stETH share rate (Lido)", "UNREAD", note=f"not the verified shape, or a window below the target's delay {gov}s: {facts}")]
    return [path("stETH share rate (Lido)", "governance-grade", note=f"oracle reports bounded by the sanity checker; limits and upgrades through Dual Governance: "
                 f"voteTime {vote}s + afterSubmit {after}s" + ("" if protection else f" + afterSchedule {after_schedule}s")
                 + f" = {window}s >= {gov}s" + ("; afterSchedule not counted while emergency protection is on" if protection else ""))]


SKY_PAUSE_PROXY, SKY_PAUSE, SKY_CHIEF = "0xBE8E3e3618f7474F8cB1d074A26afFef007E98FB", "0xbE286431454714F511008713973d3B053A2d38f3", "0x929d9A1435662357F54AdcF64DcEE4d6b867a6f9"


def sky_governance_path(w3, gov, label):
    """Sky (MakerDAO) governance as a controller: MCD_PAUSE_PROXY, owned by MCD_PAUSE, whose authority is DSChief. A Sky
    vote has no minimum duration (continuous approval voting), so the window is the pause delay alone: governance-grade at
    or above the target's delay; otherwise scored with the convention of score_makerdao_sky_pause (decided 2026-10-05):
    adminKeyScore 75 while DSChief.hat().done() reads (20 otherwise), multisigScore 100 (not a Safe), timelockScore 70 for
    the 2-day delay (delay_points below it): composite 81 today."""
    owner, authority = _addr(w3, SKY_PAUSE_PROXY, "owner"), _addr(w3, SKY_PAUSE, "authority")
    pause_owner = _addr(w3, SKY_PAUSE, "owner")  # DSPause auth also passes for its owner: it must be zero, or it plots without DSChief
    delay = call_raw(w3, SKY_PAUSE, _UINT("delay"), "delay", retries=2)
    if (owner or "").lower() != SKY_PAUSE.lower() or (authority or "").lower() != SKY_CHIEF.lower() or delay is None or pause_owner is not None:
        return path(label, "UNREAD", note=f"pause proxy owner {owner}, pause authority {authority}, pause owner {pause_owner}, delay {delay}: not Sky's verified shape")
    if gov and delay >= gov:
        return path(label, "governance-grade", note=f"Sky pause delay {delay}s >= the target's governance delay {gov}s", controller=SKY_PAUSE_PROXY)
    hat = _addr(w3, SKY_CHIEF, "hat")
    done = call_raw(w3, hat, _BOOL("done"), "done", retries=2) if hat else None
    admin, timelock = (75 if done is not None else 20), (70 if delay >= 172800 else delay_points(delay))
    return path(label, "scored", composite(admin, 100, timelock), f"Sky governance: DSChief hat {hat} done() {done}, pause delay {delay}s below the "
                f"target's {gov}s; convention of score_makerdao_sky_pause ({admin}, 100, {timelock})", SKY_PAUSE_PROXY)


SKY_SUSDS, SKY_SPBEAM, SKY_SPBEAM_MOM = "0xa3931d71877C0E7a3148CB7Eb4463524FEc27fbD", "0x36B072ed8AFE665E3Aa6DaBa79Decbec63752b22", "0xf0C6e6Ec8B367cC483A411e595D3Ba0a816d37D0"
SKY_WARDS_PROOF_BLOCK = 26125269  # Rely/Deny of sUSDS and SP-BEAM replayed from block 0 on 2026-10-05: 4 events each
SKY_CODE = {SKY_SPBEAM: "e6f7193b228f5db44b75a8d6aae5eb9ef2bfa76f3043fa498f0f07e9e2607ee5",
            SKY_SPBEAM_MOM: "f2db8e14378dda9069c48d70f7851aaa4ef9317033d97eef87197e2cd2bbae87",  # SPBEAMMom: halt() only (file("bad", 1))
            "0x4e7991e5C547ce825BdEb665EE14a3274f9F61e0": "c80a36f3ada09727300a955ca9bbef907b2bc4b3438fc90b826f03bf9be40baa"}  # SUsds implementation
_CFGS = [{"name": "cfgs", "type": "function", "stateMutability": "view", "inputs": [{"type": "bytes32"}], "outputs": [{"type": "uint16"}] * 3}]
_WARD_EVENTS = ["0x" + Web3.keccak(text=e).hex().removeprefix("0x") for e in ("Rely(address)", "Deny(address)")]


def _sky_susds(w3, gov):
    """sUSDS (a Morpho BASE_VAULT, convertToAssets = chi): UUPS, upgrade and file('ssr') are `auth` (verified SUsds source:
    ssr >= RAY, so chi only rises). Wards replayed from block 0: MCD_PAUSE_PROXY and SP-BEAM; SP-BEAM's wards are
    MCD_PAUSE_PROXY and SPBEAMMom (halt() only, which freezes rate changes). SP-BEAM's buds set the rate within its SSR cfg
    (min, max, step bps, a cooldown): bounded. Upgrades and SP-BEAM's cfg: Sky governance (sky_governance_path)."""
    label = "sUSDS share rate (Sky)"
    impl = _slot(w3, SKY_SUSDS, IMPL_SLOT)
    wards = lambda c, a: call_raw(w3, c, _UINT("wards", "address"), "wards", _cs(a), retries=2)  # noqa: E731
    code_ok = all(Web3.keccak(_code(w3, a)).hex().removeprefix("0x") == h for a, h in SKY_CODE.items())
    facts = {"implementation": impl, "code pinned": code_ok, "sUSDS wards": (wards(SKY_SUSDS, SKY_PAUSE_PROXY), wards(SKY_SUSDS, SKY_SPBEAM)),
             "SP-BEAM wards": (wards(SKY_SPBEAM, SKY_PAUSE_PROXY), wards(SKY_SPBEAM, SKY_SPBEAM_MOM)),
             "SSR cfg": call_raw(w3, SKY_SPBEAM, _CFGS, "cfgs", b"SSR".ljust(32, b"\0"), retries=2)}
    if (not impl or impl.lower() != "0x4e7991e5c547ce825bdeb665ee14a3274f9f61e0" or not code_ok or facts["sUSDS wards"] != (1, 1)
            or facts["SP-BEAM wards"] != (1, 1) or not facts["SSR cfg"]):
        return [path(label, "UNREAD", note=f"not the verified shape: {facts}")]
    try:
        changes = sum(logs_since(w3, c, [_WARD_EVENTS], SKY_WARDS_PROOF_BLOCK + 1) for c in (SKY_SUSDS, SKY_SPBEAM))
    except Exception as e:  # noqa: BLE001 -- a failed log read is unknown, never "no change"
        return [path(label, "UNREAD", note=f"ward replay after block {SKY_WARDS_PROOF_BLOCK} failed: {type(e).__name__}")]
    if changes:
        return [path(label, "UNREAD", note=f"{changes} Rely/Deny since the proof block {SKY_WARDS_PROOF_BLOCK}: re-derive the wards")]
    return [sky_governance_path(w3, gov, f"{label}: upgrade and SP-BEAM configuration (MCD_PAUSE_PROXY ward)"),
            path(f"{label}: ssr by SP-BEAM's buds", "bounded", note=f"chi only rises (ssr >= RAY); SSR cfg (min, max, step) bps {facts['SSR cfg']}; SPBEAMMom can only halt")]


# masked_template of Morpho Vault V2 (Steakhouse Prime USDC 0xbeef0880 and Prime EURCV 0xbeef0C07, 21,808 bytes, read live
# 2026-10-05): a vault of this build read for its share price (a BASE_VAULT) is scored by vault_v2_share_paths.
MORPHO_VAULT_V2_TEMPLATE = "8d799902b0635b2aa79f2f0b05f64fa8c43e6c19ab91658e72c3d9a5b3ce2662"


def vault_v2_share_paths(w3, vault, gov):
    """A Morpho Vault V2 read for its share price: convertToAssets moves with what its adapters hold, with allocations
    inside caps, and with the curator's changes (adapters, caps, gates), each behind its own timelock; the accrual is
    capped by maxRate. The curator acts behind the vault's minimum live timelock (morpho_v2.timelock_and_gates):
    governance-grade at or above the target's delay, else scored behind it (controller_path); so does the owner, who can
    replace the curator at once. Its markets' own oracles are one hop further: disclosed, not scored."""
    label = f"Morpho Vault V2 {vault} share price"
    d, _ = morpho_v2.timelock_and_gates(w3, vault, call=call_raw)
    if d is None:
        return [path(label, "UNREAD", note="its timelocks are unread")]
    if d == float("inf"):
        return [path(label, "bounded", note="every fund-redirecting function and exit gate abdicated")]
    # setCurator is owner-only with no timelock (VaultV2.sol): the owner installs a curator at once, then acts behind d too
    p = _worst([controller_path(w3, _addr(w3, vault, g), gov, f"{label}: {g} behind its minimum timelock {d}s", delay=d) for g in ("curator", "owner")],
               "the curator, and the owner who replaces the curator at once")
    p["note"] += "; allocators act within the timelocked caps; its markets' oracles disclosed, not scored"
    return [p]


RSETH_PROOF_BLOCK = 26115261  # first Ethereum block of 2026-10-04 UTC; the DEFAULT_ADMIN replay of that day found one holder


def role_events_since(w3, contract, role, start, chunk=10_000):
    """Number of RoleGranted / RoleRevoked logs for `role` on `contract` from block `start` to the tip, in chunks a public
    RPC accepts (publicnode refuses 20,000 blocks; eth.drpc.org refuses even 1,000, so the Ethereum scorer's RPC must serve
    eth_getLogs). Raises on a failed read: never 'no event'."""
    topics = [["0x" + Web3.keccak(text=e).hex().removeprefix("0x") for e in ("RoleGranted(bytes32,address,address)", "RoleRevoked(bytes32,address,address)")],
              "0x" + role.hex()]
    return logs_since(w3, contract, topics, start, chunk)


def logs_since(w3, contract, topics, start, chunk=10_000):
    """Number of logs matching `topics` on `contract` from block `start` to the tip, read in chunks. Raises on a failed
    read: never 'no event'."""
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


VUSD_MONAD = ("0x8d3F9f9Eb2f5E8B48EFBB4074440D1E2A34Bc365", "f50a319e45275f9e49c1ba0a2c551d134040e280c9613df76d2863c65d4aebf1")  # vault, runtime code hash
VUSD_STRATEGY = ("0x8dCE15fc6a98484C995Fc702cBfBdA14A30454af", "0x62d83e8d579ec3b5911f29e02c70f4130092edd1",
                 "dbc4c1158581ab6fe41ef76149badc4950472779e946de4d2ad3da4d39b0730e")  # strategy, implementation, its code hash


def _accountable_vusd(w3, gov):
    """vUSD on Monad ('RWA Backed Lending by Valos', an AccountableAsyncRedeemVault, Sourcify chain 143): sharePrice() is
    strategy.sharePrice(vault), the strategy an AccountableOpenTerm UUPS proxy (implementation 0x62D83E8d, verified source:
    setTerms and defaultLoan onlyManager, _authorizeUpgrade onlyManagerOrSecurityAdmin, rollbackRate by the operationsAdmin
    when enabled, defaultLoan/coverDefault by a safetyModule when set). Read live 2026-10-05. Scored: investmentManager();
    globals().securityAdmin() while securityAdminEnabled(); globals().operationsAdmin() while operationsAdminEnabled();
    the globals proxy's controller. A safetyModule set is UNREAD (not analyzed). The rate publisher (publishRate) and the
    interest-rate proposers (proposeInterestRate) are disclosed, not scored."""
    vault, strategy = _cs(VUSD_MONAD[0]), _cs(VUSD_STRATEGY[0])
    label = f"vUSD (Monad) {vault} share price (Accountable strategy {strategy})"
    impl = _slot(w3, strategy, IMPL_SLOT)
    shape = (Web3.keccak(_code(w3, vault)).hex().removeprefix("0x") == VUSD_MONAD[1] and not any(_slot(w3, vault, s) for s in PROXY_SLOTS)
             and (_addr(w3, vault, "strategy") or "").lower() == strategy.lower() and impl and impl.lower() == VUSD_STRATEGY[1]
             and Web3.keccak(_code(w3, impl)).hex().removeprefix("0x") == VUSD_STRATEGY[2])
    if not shape:
        return [path(label, "UNREAD", note="vault code, strategy or strategy implementation changed since the 2026-10-05 read")]
    flags = {g: call_raw(w3, strategy, _BOOL(g), g, retries=2) for g in ("securityAdminEnabled", "operationsAdminEnabled")}
    safety = call_raw(w3, strategy, _ADDR("safetyModule"), "safetyModule", retries=2)
    globals_ = _addr(w3, strategy, "globals")
    paths = [controller_path(w3, _addr(w3, strategy, "investmentManager"), gov, f"{label}: investmentManager (setTerms, defaultLoan, upgrade)")]
    if None in flags.values() or safety is None or globals_ is None:
        return paths + [path(label, "UNREAD", note=f"admin switches {flags}, safetyModule {safety}, globals {globals_}: not all read")]
    for flag, getter in (("securityAdminEnabled", "securityAdmin"), ("operationsAdminEnabled", "operationsAdmin")):
        if flags[flag]:
            paths.append(controller_path(w3, _addr(w3, globals_, getter), gov, f"{label}: globals {globals_} {getter} ({flag})"))
    if int(safety, 16):
        paths.append(path(label, "UNREAD", note=f"safetyModule {safety} set: not analyzed"))
    paths += controller_of_path(w3, globals_, gov)
    for p in paths:
        p["note"] += "; publishRate and proposeInterestRate holders disclosed, not scored"
    return paths


def _code_is(w3, address, code_hash):
    """True when the runtime code of `address` hashes (keccak) to `code_hash`: its behaviour, immutables included, is the
    one analyzed (a pinned code with no DELEGATECALL of a stored address cannot be re-pointed by a proxy slot)."""
    return Web3.keccak(_code(w3, address)).hex().removeprefix("0x") == code_hash


def chronicle_scribe_spec(scribe, scribe_hash, wards, executor):
    """A Chronicle Scribe or ScribeOptimistic (chronicleprotocol/scribe, verified source): every price lever (lift / drop of
    a validator, setBar, rely / deny, setOpChallengePeriod) is `auth`, and its wards are enumerable (authed()). poke needs
    `bar` signatures of lifted validators (their keys, like a Chainlink DON, are disclosed, not scored). Kept only while
    authed() equals `wards` exactly and every code hash is the pinned one: {ward: (kind, code hash)} with kind
    "kiss" (Kisser or KissGovernanceOperator: its only call is IToll.kiss(who), read access, no price lever: bounded),
    "accessor" (a GovernanceAccessor: forwards rely/deny or lift/drop/setBar only when msg.sender is its immutable
    spellExecutor(), which must be `executor`) or "timelock" (scored by controller_path). executor = (SpellExecutor,
    code hash, owner, owner's code hash): exec() delegatecalls a spell only for its immutable owner, scored by
    controller_path. Any other answer is UNREAD."""
    se, se_hash, se_owner, owner_hash = executor

    def spec(w3, gov):
        label = f"Chronicle Scribe {scribe}"
        authed = call_raw(w3, scribe, _LIST("authed"), "authed", retries=2)
        pinned = {scribe: scribe_hash, se: se_hash, se_owner: owner_hash, **{w: h for w, (_, h) in wards.items()}}
        changed = [a for a, h in pinned.items() if not _code_is(w3, a, h)]
        if any(kind not in ("kiss", "timelock", "accessor") for kind, _ in wards.values()):  # a ward no branch below scores would vanish
            return [path(label, "UNREAD", note=f"a pinned ward of an unknown kind: {wards}")]
        accessors = [w for w, (kind, _) in wards.items() if kind == "accessor"]
        execs = {w: _addr(w3, w, "spellExecutor") for w in accessors}
        owner = _addr(w3, se, "owner")
        if (authed is None or sorted(a.lower() for a in authed) != sorted(w.lower() for w in wards) or changed
                or any((e or "").lower() != se.lower() for e in execs.values()) or (owner or "").lower() != se_owner.lower()):
            return [path(label, "UNREAD", note=f"authed() {authed}, code changed at {changed}, spellExecutor() {execs}, "
                                               f"SpellExecutor owner {owner}: not the verified shape")]
        paths = [path(f"{label} ward {w}", "bounded", note="can only kiss readers (IToll.kiss), code pinned")
                 for w, (kind, _) in wards.items() if kind == "kiss"]
        paths += [controller_path(w3, w, gov, f"{label} ward timelock {w} (lift, drop, setBar, rely)")
                  for w, (kind, _) in wards.items() if kind == "timelock"]
        if accessors:
            paths.append(controller_path(w3, se_owner, gov, f"{label} accessors {accessors} -> SpellExecutor {se} owner"))
        bar = call_raw(w3, scribe, _UINT("bar"), "bar", retries=2)
        op = call_raw(w3, scribe, _UINT("opChallengePeriod"), "opChallengePeriod", retries=2)
        for p in paths:
            p["note"] += f"; poke needs bar() = {bar} validator signatures (disclosed)" + (
                f"; opPoke by one validator stands after opChallengePeriod() = {op}s unless challenged (disclosed)" if op is not None else "")
        return paths
    return spec


# Chronicle on Monad (WBTC/USD 0xf8689D8A, MON/USD 0x936a444C, ETH/USD 0xa7f041Fb, WSTETH/USD 0x418541FF): bytecode not
# verified on Monad, each contract matched on 2026-10-05 against a verified build of Chronicle's published code, operand by
# operand (PUSH32 sites): the four Scribes share masked_template 3f2de248 with the verified Scribe 0x21D24b9f (Ethereum) and
# Chronicle_SOL_USD_1 0x2F8C9072 (Base Sepolia), solc 0.8.16, the only differing operand being the immutable wat();
# 0xB3bf22c6 = Kisser_1 (Ethereum 0x371A53bB, same operands); 0xAB783918 = ChronicleGovernance_Operator_Kiss_1 (Ethereum
# 0x579A8DA6, identical code: kiss(target, who) for its tolled callers only); 0x5B948495 = Accessor_Auth_1 (Ethereum
# 0xD4C5694c, only spellExecutor differs); 0x8A937Cd5 = ScribeGovernanceAccessor (lift / drop / setBar, `spell`-gated) of
# the verified Accessor_Scribe_1 (Arbitrum 0xFCa041df) with the AccessorExecuted event of the verified GovernanceAccessor
# (Ethereum 0xD4C5694c) emitted after each call: recompiled with solc 0.8.24 unoptimized, same masked template and
# operands but the immutable spellExecutor; SpellExecutor 0x9Fd43829 = CouncilSpellExecutor (Ethereum 0x3dF4F566, only the
# immutable owner differs); its owner 0x61ecb8EF = CouncilTimelock (code identical to Ethereum 0xbA36311E, 7 d);
# 0x2F8C9072 = ChronicleTimelockController (Ethereum Sepolia 0xcF03450A, identical operands, 7 d). Both timelocks are
# pinned in TIMELOCK_HOLDERS.
CHRONICLE_MONAD_WARDS = {
    "0xB3bf22c657a2d1EDEf447CA8D863C10989e047B0": ("kiss", "93edc7131be69cc1e56e5eba679653af536a98af14648688fd24470b38dfdede"),
    "0xAB7839187B3E82B48AdBA18c1b7Fa3f992c8B0db": ("kiss", "b03da6713dda25c2cd3de0bc1f0a0a2450b2291abda6b27813d54b14bb4cab75"),
    "0x5B948495Ca2347F0199aDCcfF09Fa6d2e660b291": ("accessor", "0a71794e7e2ea28561986a636de467c1f513566c881b633caea15297d969efcf"),
    "0x8A937Cd5983E2F2fD42863671467fD39B826AfEa": ("accessor", "9c85964c2b4fd7edbf2b124625d40e644b79d5a968e105401098e10aef1f07af"),
    "0x2F8C90726Bc6bEc5D01313476F2e211a366A921a": ("timelock", "3fb0f77e87760264dd1148469cd14185754a95af4387b78f2ce0b123fd374da4"),
}
CHRONICLE_MONAD_EXECUTOR = ("0x9Fd43829C79FbD556EE928Ebc82b5D9A710E8672", "99c73c382b0a3db7960441ec3635599fd08a20602a38a21c6108fb4729f62fb3",
                            "0x61ecb8EFe66133368121872218c186244973e658", "25811d5a1ce1d0f1da8f6ad0dbc551805b5f691b82945bb98ec2d0f44ea34711")
CHRONICLE_MONAD_SCRIBES = {  # {Scribe: runtime code hash}, 8,686 bytes each, read live 2026-10-05
    "0xf8689D8A90cDB562ea2B83cecE80c8a551a931C6": "15fa1089ec592f417f43fe90a949c450b8613c67b33aa0ce898142aecba25eee",
    "0x936a444C983347FFBfe3F26D1497CAbfA2BfE271": "210ace84627e0eebd6d8b226ab8eee9b56dc338fd9ee643aba4ab88a3ec39843",
    "0xa7f041Fb6AfFb962162Ff3f318cA184299e4eC58": "8133e335a456b328828959547c051e10f6b2bd3d218a06c9177166e76ce768c2",
    "0x418541FFD62bDB3078fb669cB9c18D45942d9C3d": "ab6cd28fbdb21032ba5c88137807b8ebb21970984a99e2b1acf9bf6057975b08",
}

MONAD_SPECS = {"0xbbb58AA3a251c9f19653771c44481c39500b71A3": _monad_fixed_musd,
               VUSD_MONAD[0]: _accountable_vusd,  # vUSD (an Euler router converts through it)
               **{s: chronicle_scribe_spec(s, h, CHRONICLE_MONAD_WARDS, CHRONICLE_MONAD_EXECUTOR)  # BASE_FEED_1 of the Morpho vault's oracles
                  for s, h in CHRONICLE_MONAD_SCRIBES.items()}}

ETHEREUM_SPECS = {
    "0xCd5fE23C85820F7B72D0926FC9b05b43E359b7ee": _etherfi_weeth,   # weETH (Aave RATIO_PROVIDER, Compound ratioProvider)
    "0xae7ab96520DE3A18E5e111B5EaAb095312D7fE84": _lido_steth,      # stETH (Aave wstETH adapter RATIO_PROVIDER)
    "0x7f39C581F595B53c5cb19bD0b3f8dA6c935E2Ca0": _lido_steth,      # wstETH (Compound CAPO ratioProvider: stEthPerToken)
    "0x349A73444b1a310BAe67ef67973022020d70020d": _kelp_rseth,      # rsETH LRTOracle
    "0x2A261e60FB14586B474C208b1B7AC6D0f5000306": _stakewise_oseth,  # osETH OsTokenVaultController
    "0x5C5b196aBE0d54485975D1Ec29617D42D9198326": _elixir_sdeusd,   # sdeUSD (Morpho BASE_VAULT)
    SKY_SUSDS: _sky_susds,                                           # sUSDS (Morpho BASE_VAULT)
}

# Chronicle on Ethereum, reached through the Aggor medians SparkLend reads (verified sources, read live 2026-10-05):
# Chronicle_ETH_USD_3 and Chronicle_BTC_USD_3 (ScribeOptimistic) have authed() = {ChronicleTimelockController_1 0x40C33e79
# (OpenZeppelin TimelockController, getMinDelay 604800), Kisser_1 0x371A53bB (kiss only), ChronicleGovernance_Accessor_Auth_1
# 0xD4C5694c (rely / deny for its immutable spellExecutor 0x3dF4F566 only)}; the CouncilSpellExecutor's immutable owner is the
# CouncilTimelock 0xbA36311E (getMinDelay 604800).
CHRONICLE_ETH_WARDS = {
    "0x40C33e796be78148CeC983C2202335A0962d172A": ("timelock", "981458c817539dad7e7e91f8dfff45a41f03c734c15150a2053082cbc259cd4a"),
    "0x371A53bB4203Ad5D7e60e220BaC1876FF3Ddda5B": ("kiss", "0bbccea9ef7abab13a788d531d2153ba70702a800a30be1395bf6e545f39d606"),
    "0xD4C5694cA1272a3d66236d45694f5777EcC94eF3": ("accessor", "fc28bc20d0e86dd3fc84861473767366feccff31e1702817b82faccbb7a47fae"),
}
CHRONICLE_ETH_EXECUTOR = ("0x3dF4F56693B9b6F0897636A10f76b88F49B4cf52", "c731adba72e4536747cbe167c252928ec36f79159a95843df35442dea3e35188",
                          "0xbA36311E48653fa4FF47bF7Fc301e15d27A7eD91", "25811d5a1ce1d0f1da8f6ad0dbc551805b5f691b82945bb98ec2d0f44ea34711")
CHRONICLE_ETH_SCRIBES = {"0x46ef0071b1E2fF6B42d36e5A177EA43Ae5917f4E": "9da7e1f90727f7f58203f9bb4dcad02f5f48329e03aa867883b6aed975f42a2f",  # ETH/USD
                         "0x24C392CDbF32Cf911B258981a66d5541d85269ce": "5b6ce9c48605c957e24c145816545dc7d19e41de92d4b688307872f3aaad22eb"}  # BTC/USD
ETHEREUM_SPECS.update({s: chronicle_scribe_spec(s, h, CHRONICLE_ETH_WARDS, CHRONICLE_ETH_EXECUTOR) for s, h in CHRONICLE_ETH_SCRIBES.items()})

# SparkLend (an Aave V3 fork without a PayloadsController). AaveOracle.setAssetSources / setFallbackOracle are
# onlyAssetListingOrPoolAdmins, PoolAddressesProvider.setPriceOracle is onlyOwner. Replayed from block 0 to
# SPARK_PROOF_BLOCK on 2026-10-05: ACLManager 0xdA135Cd7 (23 role events) has SparkProxy as sole DEFAULT_ADMIN and
# POOL_ADMIN and never granted ASSET_LISTING_ADMIN; SparkProxy (SubProxy: exec is auth, a delegatecall) has wards
# MCD_PAUSE_PROXY, the ESM (its code only calls deny(pause proxy) on a target, or vat.deny / end.cage) and StarGuard (plot is
# auth, exec runs the plotted spell for anyone), whose only ward is MCD_PAUSE_PROXY. Every price lever of the market thus
# waits MCD_PAUSE.delay() (a DSPause: every plot waits it, setDelay goes through it).
SPARK_PROXY, SPARK_ACL = "0x3300f198988e4C9C63F75dF86De36421f06af8c4", "0xdA135Cd78A086025BcdC87B038a1C462032b510C"
SPARK_ESM, SPARK_STAR_GUARD = "0x09e05fF6142F2f9de8B6B65855A1d56B6cfE4c58", "0x6605aa120fe8b656482903E7757BaBF56947E45E"
SPARK_PROOF_BLOCK = 26125383
SPARK_CODE = {SPARK_PROXY: "c873ecf914019a0ae597cd57a51b992a505d57197b1e6d5684d11cb257cbc024",  # SubProxy, 2,085 bytes
              SPARK_ESM: "63184871b9ab41e5a1c1c28d7f54be60ffa9e2466c227c5aecd3f075081e143f",  # ESM, 6,004 bytes
              SPARK_STAR_GUARD: "31ecbe6d44fdcba4d68f71425fd367da5e45b67c6bcd0b305dfe2880a3b9c4c6"}  # StarGuard, 6,435 bytes
_SPARK_ROLES = (b"\x00" * 32, Web3.keccak(text="POOL_ADMIN"), Web3.keccak(text="ASSET_LISTING_ADMIN"))


def spark_governance(w3, provider):
    """(governance delay, own addresses, how it was read) of SparkLend: MCD_PAUSE.delay() (the Sky pause, decided 2026-10-05:
    a Sky vote has no minimum duration) while every link above holds live: provider.owner() = getACLAdmin() = SparkProxy,
    getACLManager() = 0xdA135Cd7, SparkProxy holds DEFAULT_ADMIN and POOL_ADMIN, the three SparkProxy wards and StarGuard's
    ward read 1, StarGuard.subProxy() is SparkProxy, the code hashes are the pinned ones, MCD_PAUSE_PROXY.owner() is
    MCD_PAUSE, and no grant or revoke of those roles and no Rely / Deny on SparkProxy or StarGuard since SPARK_PROOF_BLOCK.
    Delay None otherwise (no governance-grade bar)."""
    own = {SPARK_PROXY, SPARK_ACL, SKY_PAUSE_PROXY, SKY_PAUSE}
    has = lambda role: call_raw(w3, SPARK_ACL, _BOOL("hasRole", "bytes32", "address"), "hasRole", role, _cs(SPARK_PROXY), retries=2)  # noqa: E731
    wards = lambda c, a: call_raw(w3, c, _UINT("wards", "address"), "wards", _cs(a), retries=2)  # noqa: E731
    facts = {"owner": _addr(w3, provider, "owner"), "ACL admin": _addr(w3, provider, "getACLAdmin"), "ACL manager": _addr(w3, provider, "getACLManager"),
             "roles": (has(_SPARK_ROLES[0]), has(_SPARK_ROLES[1])), "SparkProxy wards": tuple(wards(SPARK_PROXY, a) for a in (SKY_PAUSE_PROXY, SPARK_ESM, SPARK_STAR_GUARD)),
             "StarGuard ward": wards(SPARK_STAR_GUARD, SKY_PAUSE_PROXY), "StarGuard subProxy": _addr(w3, SPARK_STAR_GUARD, "subProxy"),
             "code pinned": all(_code_is(w3, a, h) for a, h in SPARK_CODE.items()), "pause proxy owner": _addr(w3, SKY_PAUSE_PROXY, "owner"),
             "pause owner": _addr(w3, SKY_PAUSE, "owner")}
    same = lambda k, a: (facts[k] or "").lower() == a.lower()  # noqa: E731
    if not (same("owner", SPARK_PROXY) and same("ACL admin", SPARK_PROXY) and same("ACL manager", SPARK_ACL) and same("StarGuard subProxy", SPARK_PROXY)
            and same("pause proxy owner", SKY_PAUSE) and facts["roles"] == (True, True) and facts["SparkProxy wards"] == (1, 1, 1)
            and facts["StarGuard ward"] == 1 and facts["code pinned"] and facts["pause owner"] is None):
        return None, own, f"not the verified shape: {facts}"
    try:
        changes = (logs_since(w3, SPARK_ACL, [_ROLE_EVENTS, ["0x" + bytes(r).hex() for r in _SPARK_ROLES]], SPARK_PROOF_BLOCK + 1)
                   + sum(logs_since(w3, c, [_WARD_EVENTS], SPARK_PROOF_BLOCK + 1) for c in (SPARK_PROXY, SPARK_STAR_GUARD)))
    except Exception as e:  # noqa: BLE001 -- a failed log read is unknown, never "no change"
        return None, own, f"role and ward replay after block {SPARK_PROOF_BLOCK} failed: {type(e).__name__}"
    if changes:
        return None, own, f"{changes} role grant / revoke or Rely / Deny since the proof block {SPARK_PROOF_BLOCK}: re-derive"
    delay = call_raw(w3, SKY_PAUSE, _UINT("delay"), "delay", retries=2)
    return delay, own, f"SparkProxy -> MCD_PAUSE_PROXY -> MCD_PAUSE checked, roles and wards pinned at block {SPARK_PROOF_BLOCK}, no change since"


def _bare_key_holder(w3, label, holder, has, facts):
    """A role whose holder is a bare EOA scores composite(5, 0, 0) = 2, the floor: holders not enumerated cannot lower it.
    Holding the role (True, read live) and having no code are both required; any other answer is UNREAD."""
    if has is not True or _code(w3, holder):
        return [path(label, "UNREAD", note=f"hasRole = {has}, holder {holder} code {len(_code(w3, holder))} bytes; {facts}")]
    return [path(label, "scored", composite(5, 0, 0), f"{holder}: bare EOA holding the role, no delay; 2 is the floor, other holders cannot lower it; {facts}", holder)]


MIDAS_MGLO_IMPL_HASH = "530f6535d038f5a9be4800d35b9495b01fc8d9d47e92570fa9f6483d670cfe75"  # implementation 0x1ae32bfE, read live 2026-10-05


def _midas_mglo_feed(w3, gov):
    """Midas MGloCustomAggregatorFeed 0x49D9Dd1F (TransparentUpgradeableProxy): setRoundData(int256) is onlyRole(feedAdminRole)
    on accessControl() and bounded only by [minAnswer, maxAnswer] (verified source, finding of 2026-09-26). Read live on
    2026-10-05: implementation 0x1ae32bfE (MIDAS_MGLO_IMPL_HASH), accessControl 0xe5F08720, feedAdminRole 0x5ad51e52...8a5f held
    by the bare EOA 0x83b573AA. Its ProxyAdmin (2-day timelock) cannot lower a path that already sits at the floor."""
    feed, ac_expected, holder = _cs("0x49D9Dd1Fa6EA3709aB8A5d5f16a1cf207eb91dd0"), "0xe5f087203f9e7a6104c821ec25b1f0a4505d3cb5", _cs("0x83b573AA8C4b567c0466c9d5e32D6513676d795b")
    label = f"Midas mGLO feed {feed} setRoundData (feedAdminRole)"
    impl, ac = _slot(w3, feed, IMPL_SLOT), _addr(w3, feed, "accessControl")
    role = call_raw(w3, feed, _B32("feedAdminRole"), "feedAdminRole")
    impl_ok = impl and Web3.keccak(_code(w3, impl)).hex().removeprefix("0x") == MIDAS_MGLO_IMPL_HASH
    if not impl_ok or not ac or ac.lower() != ac_expected or role is None:
        return [path(label, "UNREAD", note=f"implementation {impl} / accessControl {ac} / feedAdminRole {role}: not the analyzed shape")]
    has = call_raw(w3, ac, _BOOL("hasRole", "bytes32", "address"), "hasRole", role, holder)
    return _bare_key_holder(w3, label, holder, has, f"accessControl {ac}, feedAdminRole 0x{bytes(role).hex()}")


STOCK_BEACON_CODE_HASH = "8b465c0b53a2ba499566e9b4ca67d8c90ed6131743df806a570d156956a7e90e"  # 2,332 bytes, read live 2026-10-05; role tree: data/rotation_audit_2026-09-20-robinhood-chain-index15.md


def _robinhood_stock_beacon(w3, gov):
    """The AccessControl beacon 0xe10b6f6B behind every Robinhood Chain stock token (score_stock_token): its DEFAULT_ADMIN_ROLE
    is the admin of every role (upgrade, pause, mint, the uiMultiplier the stock oracles read) and is held by the bare EOA
    0xd6f8378f. The beacon has no owner() and no proxy slot; its code is pinned by hash (read live 2026-10-05)."""
    beacon, holder = _cs("0xe10b6f6B275de231345c20D14Ab812db62151b00"), _cs("0xd6f8378f8e440c65f8382f5f2728c78dfd55b66d")
    label = f"stock-token beacon {beacon} DEFAULT_ADMIN (every role, upgrade)"
    if Web3.keccak(_code(w3, beacon)).hex().removeprefix("0x") != STOCK_BEACON_CODE_HASH or any(_slot(w3, beacon, s) for s in PROXY_SLOTS):
        return [path(label, "UNREAD", note="beacon code or proxy slots changed since the 2026-10-05 read")]
    has = call_raw(w3, beacon, _BOOL("hasRole", "bytes32", "address"), "hasRole", b"\x00" * 32, holder)
    return _bare_key_holder(w3, label, holder, has, "DEFAULT_ADMIN_ROLE on the beacon")


# Spark Savings USDG on Robinhood Chain and the Sky governance above it, read live on 2026-10-05. Code pinned by keccak of the
# runtime code: the vault's plain ERC1967Proxy, its SparkVault implementation (Sourcify exact match, solc 0.8.29), the Spark
# Executor (8,113 bytes, byte-identical except its metadata hash to Spark's verified Executor 0x65d946e5 on Arbitrum), the
# ArbitrumReceiver (830 bytes, immutables l1Authority = the SubProxy and target = the Executor), and on Ethereum the Spark
# SubProxy, the ESM and the StarGuard (Sourcify exact match or match). Role and ward sets replayed from block 0 up to the proof
# blocks below.
SPUSDG = ("0xde770c84FE66E063336b31737cFE9790f18c4087", "e453bb57c26a2a65301162d021e6421e7c5bb7fb9649655c771e9283f5005260",
          "0x797c58c9779d46a437d8f57908d6d56371a55f02", "bbd8ef327a4e42afc493ac793bc3c0a273feb3f2d308b72835e822ef75837276")  # proxy, its hash, implementation, its hash
SPARK_RH_EXECUTOR = ("0x826AEaeee9233fA8Ba199518dd8621A5962b1D02", "3b03a709ec3dc582f3f23b8f68c36059ff2501a92dddd05a79c293e3cc0ca1c9")
SPARK_RH_RECEIVER = ("0xc12B1e59c5E337d5Acd2b4f0A9a27d9E5D7387E8", "036f5bb5bc4380e99a14d5d59902cff5046316b5cc2137bdf2573cc24adde79e")
SPARK_RH_PROOF_BLOCK = 80691480  # every log of the Executor replayed from block 0: 3 RoleGranted, 1 RoleRevoked (deployer), all by block 27859
SPARK_L1_RPC = "https://gateway.tenderly.co/public/mainnet"
SPARK_SUBPROXY = ("0x3300f198988e4C9C63F75dF86De36421f06af8c4", "c873ecf914019a0ae597cd57a51b992a505d57197b1e6d5684d11cb257cbc024")
SPARK_STARGUARD = ("0x6605aa120fe8b656482903E7757BaBF56947E45E", "31ecbe6d44fdcba4d68f71425fd367da5e45b67c6bcd0b305dfe2880a3b9c4c6")
SPARK_ESM_PIN = ("0x09e05fF6142F2f9de8B6B65855A1d56B6cfE4c58", "63184871b9ab41e5a1c1c28d7f54be60ffa9e2466c227c5aecd3f075081e143f")
SPARK_L1_PROOF_BLOCK = 26125374  # Rely/Deny of the SubProxy (5 events) and of the StarGuard (3) replayed from block 0
_SUBMISSION_ROLE = Web3.keccak(text="SUBMISSION_ROLE")


def _spark_savings_usdg(w3, gov):
    """spUSDG (a Morpho BASE_VAULT, convertToAssets = shares x nowChi()): chi only rises, at vsr, which SETTER_ROLE sets
    within [minVsr, maxVsr], and setVsrBounds (DEFAULT_ADMIN) keeps RAY <= minVsr <= maxVsr <= MAX_VSR, a constant of the
    code (100% APY): bounded (decided 2026-10-05). take() (TAKER_ROLE) moves liquidity, not convertToAssets. The upgrade
    (UUPS, _authorizeUpgrade) and every role belong to DEFAULT_ADMIN, enumerable, held only by the Spark Executor, whose
    queue() is SUBMISSION_ROLE, held only by the ArbitrumReceiver, which forwards a call only from the L1 alias of Spark's
    SubProxy. The SubProxy's wards are MCD_PAUSE_PROXY, the ESM (denyProxy: can only remove the pause proxy) and the
    StarGuard (plot() by its wards, MCD_PAUSE_PROXY only; exec permissionless): Sky governance, scored by
    sky_governance_path (decided 2026-10-05). The Executor's own delay() is not counted (conservative). Not checked: the
    Robinhood Chain bridge that applies the L1 alias, the chain's own trust."""
    label = "spUSDG share rate (Spark Savings USDG)"
    vault, proxy_hash, impl_pin, impl_hash = SPUSDG
    (ex, ex_hash), (rcv, rcv_hash), (sp, sp_hash), (sg, sg_hash), (esm, esm_hash) = SPARK_RH_EXECUTOR, SPARK_RH_RECEIVER, SPARK_SUBPROXY, SPARK_STARGUARD, SPARK_ESM_PIN
    h = lambda chain, a: Web3.keccak(_code(chain, a)).hex().removeprefix("0x")  # noqa: E731
    has = lambda c, role, who: call_raw(w3, c, _BOOL("hasRole", "bytes32", "address"), "hasRole", role, _cs(who), retries=2)  # noqa: E731
    impl = _slot(w3, vault, IMPL_SLOT)
    admins = call_raw(w3, vault, _UINT("getRoleMemberCount", "bytes32"), "getRoleMemberCount", b"\x00" * 32, retries=2)
    bounds = [call_raw(w3, vault, _UINT(g), g, retries=2) for g in ("minVsr", "maxVsr", "vsr")]
    facts = {"implementation": impl, "DEFAULT_ADMIN count": admins, "DEFAULT_ADMIN 0": _addr(w3, vault, "getRoleMember", b"\x00" * 32, 0, ins=("bytes32", "uint256")),
             "Executor self-admin": has(ex, b"\x00" * 32, ex), "receiver SUBMISSION": has(ex, _SUBMISSION_ROLE, rcv), "minVsr, maxVsr, vsr": bounds}
    ok = (h(w3, vault) == proxy_hash and impl and impl.lower() == impl_pin and h(w3, impl) == impl_hash and admins == 1
          and (facts["DEFAULT_ADMIN 0"] or "").lower() == ex.lower() and h(w3, ex) == ex_hash and h(w3, rcv) == rcv_hash
          and facts["Executor self-admin"] is True and facts["receiver SUBMISSION"] is True and None not in bounds and bounds[0] >= 10**27)
    if not ok:
        return [path(label, "UNREAD", note=f"not the verified Robinhood Chain shape: {facts}")]
    l1 = _wu.get_w3(SPARK_L1_RPC)
    wards = lambda c, a: call_raw(l1, c, _UINT("wards", "address"), "wards", _cs(a), retries=2)  # noqa: E731
    pp = _cs(SKY_PAUSE_PROXY)
    l1_facts = {"chain": _eth(lambda: l1.eth.chain_id, "L1 chain id"), "code": [h(l1, a) == x for a, x in ((sp, sp_hash), (sg, sg_hash), (esm, esm_hash))],
                "SubProxy wards": [wards(sp, a) for a in (pp, esm, sg)], "StarGuard ward": wards(sg, pp)}
    if l1_facts["chain"] != 1 or not all(l1_facts["code"]) or l1_facts["SubProxy wards"] != [1, 1, 1] or l1_facts["StarGuard ward"] != 1:
        return [path(label, "UNREAD", note=f"not the verified Ethereum shape: {l1_facts}")]
    try:
        changes = (logs_since(w3, ex, [_ROLE_EVENTS], SPARK_RH_PROOF_BLOCK + 1, 10**7)
                   + sum(logs_since(l1, c, [_WARD_EVENTS], SPARK_L1_PROOF_BLOCK + 1, 10**9) for c in (sp, sg)))
    except Exception as e:  # noqa: BLE001 -- a failed log read is unknown, never "no change"
        return [path(label, "UNREAD", note=f"role or ward replay after the proof blocks failed: {type(e).__name__}")]
    if changes:
        return [path(label, "UNREAD", note=f"{changes} role grant/revoke or Rely/Deny since the proof blocks: re-derive the sets")]
    d = call_raw(w3, ex, _UINT("delay"), "delay", retries=2)
    return [sky_governance_path(l1, gov, f"{label}: upgrade and roles (DEFAULT_ADMIN = Spark Executor {ex}, delay {d}s not counted, "
                                         f"queued only from Spark's SubProxy {sp} on Ethereum)"),
            path(f"{label}: vsr by SETTER_ROLE", "bounded", note=f"chi only rises; minVsr, maxVsr, vsr {bounds} ray, maxVsr <= MAX_VSR (100% APY) "
                 "by code; take() moves liquidity, not the rate")]


ROBINHOOD_SPECS = {
    "0x49D9Dd1Fa6EA3709aB8A5d5f16a1cf207eb91dd0": _midas_mglo_feed,        # mGLO (underlyingFeed of the Morpho wrapper 0xe90F5b4a)
    SPUSDG[0]: _spark_savings_usdg,                                        # spUSDG (a BASE_VAULT of a Morpho market Steakhouse Turbo lends in)
    "0xe10b6f6B275de231345c20D14Ab812db62151b00": _robinhood_stock_beacon,  # beacon of the stock tokens (token() of the NetNet oracles)
}


# Chainlink Data Streams on Arbitrum, read by every GMX data-stream provider through verifier(): VerifierProxy 2.0.0
# (verified source, solc 0.8.16). initializeVerifier / unsetVerifier are onlyOwner of the proxy, with no delay; setVerifier is
# onlyInitializedVerifier; each Verifier's setConfig (signers, f) is onlyOwner of that Verifier. The initialized Verifiers
# were replayed from the proxy's whole log history on 2026-10-05 (blocks 0 to CL_VERIFIER_PROOF_BLOCK, two
# VerifierInitialized events, no VerifierUnset): 0x534a7FF7 (Verifier 1.2.0) and 0x223752Eb (Verifier 2.0.0).
CL_VERIFIER_PROXY_ARB = "0x478Aa2aC9F6D65F84e09D9185d126c3a17c2a93C"
CL_VERIFIER_PROXY_ARB_CODE_HASH = "6a40f4a110509bd2933855d7994b8e1bdf1b1ce7b38c2f2657b7bb335283461a"  # 7,009 bytes, read live 2026-10-05
CL_VERIFIERS_ARB = ("0x534a7FF707Bc862cAB0Dda546F1B817Be5235b66", "0x223752Eb475098e79d10937480DF93864D7EfB83")
CL_VERIFIER_PROOF_BLOCK = 511816779
_VERIFIER_INITIALIZED = "0x" + Web3.keccak(text="VerifierInitialized(address)").hex().removeprefix("0x")


def _chainlink_data_streams_arb(w3, gov):
    """Scores the VerifierProxy owner (a new Verifier, instantly) and every initialized Verifier's owner that differs from it
    (setConfig, instantly). Each run: the proxy's code is the pinned one with no proxy slot, and no VerifierInitialized log
    since the replay (a failed log read is UNREAD, never 'no new verifier'). The scorer's RPC must serve eth_getLogs."""
    proxy, label = _cs(CL_VERIFIER_PROXY_ARB), "Chainlink Data Streams VerifierProxy"
    if Web3.keccak(_code(w3, proxy)).hex().removeprefix("0x") != CL_VERIFIER_PROXY_ARB_CODE_HASH or any(_slot(w3, proxy, s) for s in PROXY_SLOTS):
        return [path(label, "UNREAD", note="code or proxy slots changed since the 2026-10-05 read")]
    try:
        added = logs_since(w3, proxy, [_VERIFIER_INITIALIZED], CL_VERIFIER_PROOF_BLOCK + 1, chunk=1_000_000)
    except Exception as e:  # noqa: BLE001 -- a failed log read is unknown, never "no new verifier"
        return [path(label, "UNREAD", note=f"VerifierInitialized replay since block {CL_VERIFIER_PROOF_BLOCK} failed: {type(e).__name__}")]
    if added:
        return [path(label, "UNREAD", note=f"{added} VerifierInitialized event(s) since the 2026-10-05 replay: verifier set to re-derive")]
    owner = _addr(w3, proxy, "owner")
    paths = [controller_path(w3, owner, gov, f"Data Streams VerifierProxy {proxy} owner (initializeVerifier / unsetVerifier, instant)")]
    for v in CL_VERIFIERS_ARB:
        vo = _addr(w3, v, "owner")
        if vo is None or not owner or vo.lower() != owner.lower():
            paths.append(controller_path(w3, vo, gov, f"Data Streams Verifier {v} owner (setConfig: signers and f, instant)"))
    return paths


GMX_V1_VAULT_PRICE_FEED_CODE_HASH = "f8289d24d587e424387f13aec0ed6430d6c47a3eee47494af9a37ac657cac081"  # 8,457 bytes, read live 2026-10-05
GMX_V1_PRICE_FEED_TIMELOCK_CODE_HASH = "d9c25e8b1bb16bfc461287c450b6485ef03a1fd5eea39a1c0aada12a0dac08c0"  # 11,032 bytes, read live 2026-10-05


def _gmx_v1_vault_price_feed(w3, gov):
    """GMX V1 VaultPriceFeed: its gov() is the PriceFeedTimelock, NOT the Vault's own Timelock (0x718507c3), so this is not
    the target's own configuration. On it (gmx-contracts peripherals/PriceFeedTimelock.sol, verified source solc 0.6.12;
    eth_call 2026-10-05 succeeds from admin() and reverts 'Timelock: forbidden' from the tokenManager and a random address):
    admin() INSTANTLY calls setIsSecondaryPriceEnabled (the FastPriceFeed's keeper prices; with them stale it answers the
    Chainlink price widened by spreadBasisPointsIfChainError, 500 bps today, which the same admin sets instantly with no
    cap), setMaxStrictPriceDeviation (pins FRAX, USDC, USDC.e, DAI and USDT0 at 1 USD however far they depeg),
    setUseV2Pricing and setIsAmmEnabled, and can add PriceFeedTimelock keepers and handlers (isKeeper / isHandler, not
    enumerable): keepers INSTANTLY call setAdjustment and setSpreadBasisPoints (VaultPriceFeed caps of 20 and 50 bps);
    handlers also call setPriceSampleSpace (at most 5, a PriceFeedTimelock check pinned by its code hash) and the
    FastPriceFeed's setPriceDuration and setMaxPriceUpdateDelay; bounded, disclosed. tokenManager() INSTANTLY calls setAdmin; it is a
    GMX TokenManager (its admin plus minAuthorizations signers), so following its admin() alone overstates that path, which
    cannot lower a score the admin already holds at the floor. priceFeedSetTokenConfig (re-point a Chainlink feed), setGov
    and setPriceFeedUpdater are signalled with buffer(): governance-grade only while buffer() >= the Vault's own delay.
    A live secondary price adds the FastPriceFeed updaters (isUpdater, not enumerable): UNREAD; a live AMM price: UNREAD."""
    vpf, pft = _cs(GMX_V1_VAULT_PRICE_FEED), _cs(GMX_V1_PRICE_FEED_TIMELOCK)
    gov_now = _addr(w3, vpf, "gov")
    same = (Web3.keccak(_code(w3, vpf)).hex().removeprefix("0x") == GMX_V1_VAULT_PRICE_FEED_CODE_HASH
            and Web3.keccak(_code(w3, pft)).hex().removeprefix("0x") == GMX_V1_PRICE_FEED_TIMELOCK_CODE_HASH)
    if not gov_now or gov_now.lower() != pft.lower() or not same or any(_slot(w3, a, s) for a in (vpf, pft) for s in PROXY_SLOTS):
        return [path("GMX V1 VaultPriceFeed gov", "UNREAD", note=f"gov() {gov_now}, expected the PriceFeedTimelock {pft}; code or proxy slots of either changed")]
    paths = [controller_path(w3, _addr(w3, pft, "admin"), gov, "GMX V1 PriceFeedTimelock admin() (instant setIsSecondaryPriceEnabled / setMaxStrictPriceDeviation)"),
             controller_path(w3, _addr(w3, pft, "tokenManager"), gov, "GMX V1 PriceFeedTimelock tokenManager() (instant setAdmin; a TokenManager, its admin() followed)")]
    buffer = call_raw(w3, pft, _UINT("buffer"), "buffer")
    if buffer and gov and buffer >= gov:
        paths.append(path("GMX V1 PriceFeedTimelock signalled actions", "governance-grade",
                          note=f"priceFeedSetTokenConfig / setGov / setPriceFeedUpdater behind buffer() = {buffer}s >= the Vault's delay {gov}s"))
    else:
        paths.append(path("GMX V1 PriceFeedTimelock signalled actions", "UNREAD", note=f"buffer() = {buffer}s, below the Vault's delay {gov}s or unread"))
    for flag, what in (("isSecondaryPriceEnabled", "FastPriceFeed updaters (isUpdater) are not enumerable"), ("isAmmEnabled", "AMM pair reserves are not scored")):
        if call_raw(w3, vpf, _BOOL(flag), flag) is not False:
            paths.append(path(f"GMX V1 {flag}", "UNREAD", note=f"{flag} true or unread: {what}"))
    return paths


# reUSD NAV / USD on Arbitrum (Re Protocol, verified on Blockscout, solc 0.8.30): NAVFeedProxy -> aggregator() NAVFeed (a view
# over oracle()) -> NAVOracle, the last two AccessManaged by one OpenZeppelin AccessManager. {address: runtime code hash}, read
# live 2026-10-05; none has a proxy slot.
REUSD_NAV_PROXY, REUSD_NAV_FEED, REUSD_NAV_ORACLE, REUSD_ACCESS_MANAGER = (
    "0xC4d89EC77f1313FcE6720763D24042396d5b63C6", "0x5f4b05c71AFF91E149e40ea51b6dFf84cA4EFB8f",
    "0xD9e8Fe8C23480588F986b69dd5B5301c4235f8cf", "0xA3B25d04306f1552ed4b4e18a22197912FC07AEF")
REUSD_CODE = {REUSD_NAV_PROXY: "2dc1366c9e89bb5ffa2718221f61ccba1014212c8cd6da460af27e1a56581e5f",
              REUSD_NAV_FEED: "cecc850e637a54b31a88f1e4f1666cd69d90475caa0dfe3765dcbb68d6eb12dd",
              REUSD_NAV_ORACLE: "663caccce353fc961da2e31e5a0639fd5d91abd80eea46b7875d9a92431aa189",
              REUSD_ACCESS_MANAGER: "f20c84a5ce1496bc3226e56773a7b9cb2e850b44adc166631b36987497b887c8"}
REUSD_ADMIN = "0x8eec10616802Ef639CA55c98ac856553fAdEfBaD"  # the only ADMIN (role 0) holder, Safe 3-of-5
REUSD_ADMIN_PROOF_BLOCK = 511889458  # Arbitrum tip of the AccessManager's whole log replay (block 0 on), 2026-10-05
REUSD_SUBMITTER_ROLE = 4499270388501050984
# Every restricted lever of the proxy and the core, with the role the AccessManager must give it.
REUSD_LEVERS = {REUSD_NAV_PROXY: ("proposeAggregator(address)", "cancelAggregatorProposal()", "confirmAggregator(address)"),
                REUSD_NAV_ORACLE: ("forceNAVUpdate(uint256,string)", "applyMarkdown(uint256,uint256,string)", "setMaxNAV(uint256)",
                                   "setNormalBandBps(uint256)", "setForceBandBps(uint256)", "enterProtectionMode(string)",
                                   "exitProtectionMode()", "rearmProtectionEntry()", "syncSink(address)")}
_AM_ROLE_EVENTS = ["0x" + Web3.keccak(text=e).hex().removeprefix("0x") for e in ("RoleGranted(uint64,address,uint32,uint48,bool)", "RoleRevoked(uint64,address)")]


def _reusd_nav_arb(w3, gov):
    """reUSD NAV / USD (read by an own FluidChainlinkCappedRateL2). Verified source and live reads of 2026-10-05: the proxy
    swaps its aggregator only by proposeAggregator then confirmAggregator after the constant REVIEW_DELAY (48 h:
    governance-grade against Fluid's 24 h); applyMarkdown, the only decrease path, needs Protection Mode and the immutable
    markdownDelay (24 h) from its entry; submitReport (SUBMITTER role, 0x258feb10) is up-or-flat, bounded by the immutable
    velocity bucket (maxCumulativeBps per velocityWindow); forceNAVUpdate (up-or-flat, forceBandBps every 4 h) and the
    band and maxNAV setters are ADMIN (role 0) with no execution delay, so ADMIN can widen the band to 100%: scored. The
    ADMIN set, replayed from the AccessManager's first log (382960036: grant 0x51b61cb5; 457628923: grant 0x8eec1061;
    457673709: revoke 0x51b61cb5), is one Safe. Each run: code hashes, wiring, every lever's role, hasRole(0, Safe) =
    (true, 0) and no role-0 grant or revoke since the proof block."""
    label, am = "reUSD NAV feed", _cs(REUSD_ACCESS_MANAGER)
    same = all(Web3.keccak(_code(w3, a)).hex().removeprefix("0x") == h for a, h in REUSD_CODE.items())
    wiring = (_addr(w3, REUSD_NAV_PROXY, "aggregator"), _addr(w3, REUSD_NAV_FEED, "oracle"),
              _addr(w3, REUSD_NAV_PROXY, "authority"), _addr(w3, REUSD_NAV_ORACLE, "authority"))
    roles = {s: call_raw(w3, am, [_fn("getTargetFunctionRole", ("address", "bytes4"), ("uint64",))], "getTargetFunctionRole", _cs(t),
                         Web3.keccak(text=s)[:4], retries=2) for t, sigs in REUSD_LEVERS.items() for s in sigs}
    submit = call_raw(w3, am, [_fn("getTargetFunctionRole", ("address", "bytes4"), ("uint64",))], "getTargetFunctionRole", _cs(REUSD_NAV_ORACLE),
                      Web3.keccak(text="submitReport(uint256,uint256)")[:4], retries=2)
    has = call_raw(w3, am, [_fn("hasRole", ("uint64", "address"), ("bool", "uint32"))], "hasRole", 0, _cs(REUSD_ADMIN), retries=2)
    review = call_raw(w3, REUSD_NAV_PROXY, _UINT("REVIEW_DELAY"), "REVIEW_DELAY", retries=2)
    params = {g: call_raw(w3, REUSD_NAV_ORACLE, _UINT(g), g, retries=2) for g in ("markdownDelay", "maxCumulativeBps", "velocityWindow")}
    expected = (_cs(REUSD_NAV_FEED), _cs(REUSD_NAV_ORACLE), am, am)
    if (not same or any(_slot(w3, a, s) for a in REUSD_CODE for s in PROXY_SLOTS) or wiring != expected or any(r != 0 for r in roles.values())
            or submit != REUSD_SUBMITTER_ROLE or not has or list(has) != [True, 0] or None in (review, *params.values())):
        return [path(label, "UNREAD", note=f"code, wiring {wiring}, lever roles {roles}, submitReport role {submit}, hasRole(0, {REUSD_ADMIN}) {has}, "
                     f"REVIEW_DELAY {review}, {params}: not the analyzed shape")]
    try:
        lw3, chunk = _log_reader(w3, _eth(lambda: w3.eth.chain_id, "chain id"))
        changes = logs_since(lw3, am, [_AM_ROLE_EVENTS, "0x" + "00" * 32], REUSD_ADMIN_PROOF_BLOCK + 1, max(chunk, 1_000_000))
    except Exception as e:  # noqa: BLE001 -- a failed log read is unknown, never "no change"
        return [path(label, "UNREAD", note=f"ADMIN role replay since block {REUSD_ADMIN_PROOF_BLOCK} failed: {type(e).__name__}")]
    if changes:
        return [path(label, "UNREAD", note=f"{changes} ADMIN grant or revoke since block {REUSD_ADMIN_PROOF_BLOCK}: holder set to re-derive")]
    md = params["markdownDelay"]
    paths = [path(f"{label} aggregator swap", "governance-grade" if gov and review >= gov else "UNREAD",
                  note=f"proposeAggregator then confirmAggregator after REVIEW_DELAY {review}s; target delay {gov}s"),
             path(f"{label} applyMarkdown", "governance-grade" if gov and md >= gov else "UNREAD",
                  note=f"Protection Mode, then markdownDelay {md}s (immutable); target delay {gov}s"),
             path(f"{label} submitReport (role {REUSD_SUBMITTER_ROLE})", "bounded",
                  note=f"up or flat, velocity bucket {params['maxCumulativeBps']} bps per {params['velocityWindow']}s (immutables)")]
    return paths + [controller_path(w3, _cs(REUSD_ADMIN), gov, f"{label} NAVOracle ADMIN (forceNAVUpdate, band and maxNAV setters, no delay)")]


ARBITRUM_SPECS = {
    CL_VERIFIER_PROXY_ARB: _chainlink_data_streams_arb,  # verifier() of the GMX V2 ChainlinkDataStreamProvider
    GMX_V1_VAULT_PRICE_FEED: _gmx_v1_vault_price_feed,   # Vault.priceFeed() of GMX V1
    REUSD_NAV_PROXY: _reusd_nav_arb,                     # rate source of the Fluid reUSD CappedRate 0x5036F1a5
}


# ------------------------------------------------------------------------------------------------- Fluid
# Fluid Liquidity reads no price: its vault protocols (VaultT1 to T4) borrow from it, each through its own oracle (T1:
# vaultVariables2 >> 96; T2 to T4: VaultResolver.getContractForDeployerIndex(vault, (vaultVariables2 >> 92) & X30)), so a
# mispriced vault is bad debt on Liquidity's lenders. Fluid oracles expose no common getter list: each build below, pinned
# by masked template (verified source names, Blockscout on Arbitrum and Routescan on Plasma, 2026-10-05), keeps its inputs
# in immutables, so its inputs are the contracts its 5- to 32-byte PUSH operands name. The builds marked "slot0" keep one
# more input in storage slot 0, their only state variable (_SEQUENCER_ORACLE, verified source; none writes storage after
# deployment), which must read the chain's L2 sequencer uptime feed. A FluidCappedRate ("capped") is stateful: its caps
# are set by the guardians and governance of the Liquidity it names, which must be the target. An unknown build is UNREAD.
FLUID_LIQUIDITY = "0x52Aa899454998Be5b000Ad077a46Bbe360F4e497"  # same address on Arbitrum and Plasma
FLUID_VAULT_RESOLVER = "0xA5C3E16523eeeDDcC34706b0E6bE88b4c6EA95cC"
FLUID_VAULT_FACTORY = "0x324c5Dc1fC42c7a4D43d92df1eBA58a54d13Bf2d"
FLUID_DEX_FACTORY = "0x91716C4EDA1Fb55e84Bf8b4c7085f84285c19085"
FLUID_TEAM_MULTISIG = "0x4F6F977aCDD1177DCD81aB83074855EcB9C2D49e"  # Avocado 6-of-12: Liquidity guardian and timelock proposer
FLUID_BUILDS = {
    "6960472ef68c3036bb27bcbd2ddfc09d47cf0b2a1ecd11d5052c2a98923d320c": ("FluidGenericOracleL2", "oracle"),
    "6ba1aea01a7e2017ab5d94d8e8eea9aa32ffc26227ae9a774d936e7df7f74176": ("FluidGenericOracleL2", "slot0"),
    "1f94ff110a5debc8d57cc1b110c288c67e9211e8fb81ee36c836ec3505cf9441": ("FluidGenericOracleL2", "slot0"),
    "5e618ca74c886f088bf89d5e45a4345a65b48ff37424b51b58fc49c1f3cef158": ("FluidGenericOracle", "oracle"),
    "7d7a4bce14ac624f23e9f6826e9d8e1bf707b554a2c957c0b526138b500b21db": ("CLRS2UniV3CheckCLRSOracleL2", "slot0"),
    "b5e1b419a495330d7ca5b023d3e4e72a08c3891aceac03a7ddb32a4c41723d6c": ("UniV3CheckCLRSOracleL2", "slot0"),
    "10726c35f6bc87ca10640fb8d21f14445d6798752996811289304e01319dce02": ("FallbackCLRSOracleL2", "slot0"),
    "443043e5c2a3fd11af081f2652a2db21b4d646f087b7683f9f882279973b1162": ("Ratio2xFallbackCLRSOracleL2", "slot0"),
    "26dc34d3f489100fdeddaff6cec5f176f61338e1628c554b9503d5684b838ca5": ("ChainlinkCenterPriceL2", "slot0"),
    "6dec94ef4f977b5025e688dfdc2e79c3ab54c1708b30fb0d6a263ec8ad822c84": ("PegOracleL2", "oracle"),
    "eccab85315e82ac25d89f946629d1855feea9991196987db28d2065f9e066921": ("PegOracle", "oracle"),
    "928a0ece9d445b65ba4ff9c4f6ebce6bfc2905261f13fe5ad0992e1d0e24cc24": ("DexSmartColPegOracleL2", "oracle"),
    "b286d1885691c3de5041f576e8e67b6c1d308526c34d9b1eeac988bc803d40bd": ("DexSmartColPegOracleL2", "slot0"),
    "fea65222e74e9636ef6db382a5ef2cbe11112f8174011ac14516dde5eea77a45": ("DexSmartColPegOracle", "oracle"),
    "841f277c44d7afb14814d766037b692a73bae8a5080abdb6d7c1d45b0fe81b86": ("DexSmartDebtPegOracleL2", "oracle"),
    "475579eeb18099022a530df679e6c8729efc88ee38a283082544bb9f551de9be": ("DexSmartDebtPegOracleL2", "slot0"),
    "d2da83dbadeac6c98deaf44ac2f4dea6a046cd765481ea74cfedeed0d20683e7": ("DexSmartDebtPegOracle", "oracle"),
    "a064f97b051ccb13f95a0b10ab548ecf91c4ce7dde0b58688670667447bb48b3": ("DexSmartT4PegOracleL2", "oracle"),
    "16966956ba85bb59c15d85f837bc030918d19c271889889df6c3671d4bb961d5": ("DexSmartT4PegOracleL2", "slot0"),
    "9d046c404c35fa91f1f5acd20310f33707f7b51d099deceda037a331b48aebf4": ("DexSmartT4PegOracle", "oracle"),
    "189db339bf73ae44f60f156bdbdd0b49a128597b5c995f2878a70e31da744a1d": ("DexSmartT4CLOracleL2", "slot0"),
    "f7850e30e10e1dbcb8e1045158bf8dccb5f4bed92db3059e85626f0fd3c036ab": ("FluidERC4626CappedRate", "capped"),
    "535ad2a0939a4e032019a0c406260dc605b51dbfc298979a73e76bf9e049ad00": ("FluidChainlinkCappedRate", "capped"),
    "0f421bcef5ddb817e21d3fad9e17d36226104c76d12c0a11e00f064ce7938bf1": ("FluidChainlinkCappedRateL2", "capped"),
}
FLUID_DEX_TEMPLATE = "31bff70f2b84b4713d75c4421cde54a69e4e847d5531b1d0af6ee819c756503e"  # FluidDexT1, both chains
UNIV3_POOL_TEMPLATE = "85b4c129d36908937dd5627eb048b73ee4b1513b891637a8dd86a192178d6a39"  # UniswapV3Pool (Arbitrum)
UNIV3_FACTORIES = {"0x1f98431c8ad98523631ae4a59f267346ea31f984"}
FLUID_SEQUENCER_FEEDS = {"0xfdb631f5ee196f0ed6faa767959853a9f217697d"}  # Chainlink "L2 Sequencer Uptime Status Feed", Arbitrum
# Who can call VaultT*Admin.updateOracle (re-point a vault's price at once): VaultFactory.isGlobalAuth / isVaultAuth, owner
# included. Replayed from block 0 to the proof block on 2026-10-05 (LogSetGlobalAuth, LogSetVaultAuth, OwnershipTransferred):
# no vault auth ever; Plasma's 0x0Ed35B16 was granted at 746572 and revoked at 1815777. {chain id: (proof block, owner,
# {global auth: what it is})}. The owner is the VaultFactoryOwner (setGlobalAuth / setVaultAuth / spell onlyGovernance, the
# Liquidity timelock), code b649a768... on both chains; the fee auths call only rate setters (no updateOracle selector).
FLUID_VAULT_AUTHS = {
    42161: (511887408, "0xD7ae7c8848f7C550F10c40f5B39c596CEC75fe9c", {
        "0x3Bc96922e90f13B0Fa0c6a2db035D09681d966ea": ("VaultFeeRewardsAuth", "fe2f3c28cb93071822c776706d8777723cdd8855485e2e65410cfdb3fc93c273"),
        FLUID_TEAM_MULTISIG: ("team multisig", None)}),
    9745: (34252641, "0x90A55c584D174FD10F4f3d71B411882C0063746E", {
        "0xFF5121B9689B16e9558bEC16bca590f5d70E3ad4": ("VaultFeeRewardsAuth", "bf2041ed65bef4b8b05f2403fdbae63a1efe5c83d52f5e94a1fae594a8436c46"),
        FLUID_TEAM_MULTISIG: ("team multisig", None)}),
}
FLUID_CODE = {FLUID_VAULT_FACTORY: "867b772da380c40eb5d90b295246914abbd2031a5264d1ce3154c320de7ec699",
              "owner": "b649a76809c6decab54c1fb1b310710aa83c659b7ea9890c632630c5baa1e96b"}
_VAULT_AUTH_EVENTS = ["0x" + Web3.keccak(text=e).hex().removeprefix("0x") for e in (
    "LogSetGlobalAuth(address,bool)", "LogSetVaultAuth(address,bool,address)", "OwnershipTransferred(address,address)")]
FLUID_API = "https://api.fluid.instadapp.io/v2/{}/vaults"
_LATEST_ROUND = [_fn("latestRoundData", (), ("uint80", "int256", "uint256", "uint256", "uint80"))]


def _fluid_inputs(w3, code, seen):
    """The contracts named by the 5- to 32-byte PUSH operands of `code` (a value between 2**32 and 2**160 that has code), and
    the accounts without code that look like an address (a value of at least 2**152 and not all ones: a number, a multiplier or a
    decimals scale never gets that large): a price source that is a bare key scores 2, an unknown account is never skipped. A
    smaller operand without code is a number."""
    body, i, out = _strip_metadata(code), 0, []
    while i < len(body):
        op = body[i]
        n = op - 0x5F if 0x60 <= op <= 0x7F else 0
        v = int.from_bytes(body[i + 1:i + 1 + n], "big") if n >= 5 else 0
        if 2 ** 32 < v < 2 ** 160:
            a = Web3.to_checksum_address("0x%040x" % v)
            if a not in seen:
                seen[a] = _code(w3, a)
            if seen[a] or (v >= 2 ** 152 and v != 2 ** 160 - 1):
                out.append(a)
        i += n + 1
    return list(dict.fromkeys(out))


def _fluid_spec(status, label, note):
    return lambda w3, gov: [path(label, status, note=note)]


_REQUIRED_SIGNERS = _UINT("requiredSigners")
_SIGNERS = [{"name": "signers", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "address[]"}]}]


# The Avocado proxy (327 bytes, the same on Arbitrum and Plasma) keeps its implementation in storage slot 0, not an EIP-1967
# slot: both are pinned (the implementation's runtime hash differs between the two chains, its address does not), read 2026-10-05.
AVOCADO_PROXY_HASH = "20853b54882bb9e363b0a1a5576e30a150c3a57d1a2d330f5178fb7eb3733449"
AVOCADO_IMPL = ("0xEA4ebF3EC9f3bE577a04B02782D8683b2304B614", {"1674a52def6e5f765765a23e3fd8b2422a3083db41733fc130f80aa3967d5bda",
                                                            "c853f0021407d67227225842bccd4bfcc2d16228546a0ee249325b0cf61ac1a6"})


def _avocado_path(w3, label, multisig):
    """An Instadapp Avocado multisig acting with no delay: scored as t-of-n with _safe_rooted(t, n), t = requiredSigners() and
    n = len(signers()), while its proxy code and its implementation (slot 0) are the pinned ones. Not through controller_path:
    the Avocado answers owner() with its creator, which is not who signs. Anything else, or unread -> UNREAD."""
    proxy = _code(w3, multisig)
    impl = _slot(w3, multisig, 0)
    if (Web3.keccak(proxy).hex().removeprefix("0x") != AVOCADO_PROXY_HASH or (impl or "").lower() != AVOCADO_IMPL[0].lower()
            or Web3.keccak(_code(w3, impl)).hex().removeprefix("0x") not in AVOCADO_IMPL[1]):
        return path(label, "UNREAD", note=f"{multisig}: not the pinned Avocado proxy and implementation (slot 0 {impl})")
    t, signers = call_raw(w3, multisig, _REQUIRED_SIGNERS, "requiredSigners", retries=2), call_raw(w3, multisig, _SIGNERS, "signers", retries=2)
    if not t or not signers or t > len(signers):
        return path(label, "UNREAD", note=f"{multisig}: requiredSigners() {t}, signers() {signers}: not read as an Avocado multisig")
    return path(label, "scored", composite(*_safe_rooted(t, len(signers))), f"{multisig}: Avocado multisig {t}-of-{len(signers)}, no delay", multisig)


def _fluid_dex_spec(dex):
    """A FluidDexT1 (pinned build, no proxy slot) whose constantsView() names the target Liquidity and the DexFactory, owned
    by the team multisig: the target's own contract. Its pool price moves by trading; its configuration is the DexFactory
    owner's, the Liquidity guardian the composite scores."""
    def spec(w3, gov):
        code = _fixed_code(w3, dex)
        words = call_raw(w3, dex, [_fn("constantsView", (), ("uint256",) * 18)], "constantsView", retries=2)
        owner = _addr(w3, FLUID_DEX_FACTORY, "owner")
        ok = (code is not None and masked_template(code) == FLUID_DEX_TEMPLATE and words is not None and owner == _cs(FLUID_TEAM_MULTISIG)
              and words[1] == int(FLUID_LIQUIDITY, 16) and words[2] == int(FLUID_DEX_FACTORY, 16))
        if not ok:
            return [path(f"Fluid DEX {dex}", "UNREAD", note=f"not the pinned FluidDexT1 of the target, or DexFactory owner {owner}")]
        return [path(f"Fluid DEX {dex}", "own", note=f"FluidDexT1 on the target Liquidity, DexFactory owner {owner} (the team multisig, scored below)"),
                _avocado_path(w3, f"Fluid DEX {dex} configuration (DexFactory owner)", owner)]
    return spec


def _univ3_pool_spec(pool):
    """A Uniswap V3 pool (pinned build, canonical factory, no proxy slot) read as a TWAP or a check price: no one controls
    it, its price moves only by trading. Bounded, disclosed."""
    def spec(w3, gov):
        code = _fixed_code(w3, pool)
        f = _addr(w3, pool, "factory")
        if code is None or masked_template(code) != UNIV3_POOL_TEMPLATE or (f or "").lower() not in UNIV3_FACTORIES:
            return [path(f"pool {pool}", "UNREAD", note=f"factory {f}: not the pinned Uniswap V3 pool build")]
        return [path(f"Uniswap V3 pool {pool}", "bounded", note="canonical factory, not upgradeable: no controller (manipulation is economic)")]
    return spec


def fluid_oracle_sources(w3, oracle, specs, memo, depth=0):
    """Price sources one hop upstream of a Fluid oracle, for score(): the other Fluid builds it reads are walked through
    (Fluid's own immutable contracts and own CappedRates); the target Liquidity is skipped; a FluidDexT1, a Uniswap V3 pool
    and the L2 sequencer feed get a spec; a contract answering latestRoundData() is left to the generic walk; anything else
    is a rate source with no verified spec (UNREAD, unless a chain spec names it). A CappedRate bounds nothing here: its
    caps are classified per contract, not as a class (decided 2026-10-05), and none is proven bounded yet."""
    key = oracle.lower()
    if key in memo:
        return memo[key]
    memo[key] = [f"unread: Fluid oracle {oracle} reads itself through a cycle"]
    code = _fixed_code(w3, oracle)
    name, kind = FLUID_BUILDS.get(masked_template(code), (None, None)) if code else (None, None)
    if kind is None or depth > 4:
        out = [f"unread: {oracle} is not a pinned Fluid oracle build (an account, a proxy, an unknown template or deeper than 4)"]
    elif kind == "slot0" and (_slot(w3, oracle, 0) or "").lower() not in FLUID_SEQUENCER_FEEDS:
        out = [f"unread: {name} {oracle}: storage slot 0 is not the L2 sequencer feed"]
    else:
        ins = _fluid_inputs(w3, code, memo.setdefault(":code", {}))
        out = [] if kind != "capped" or _cs(FLUID_LIQUIDITY) in ins else [f"unread: {name} {oracle} answers to another Liquidity"]
        # A build that reads nothing it can name is not accounted for, except the plain PegOracle: its optional ERC4626 feed is an
        # immutable that is zero on most instances (a 1:1 peg, no call made); a set feed would be an operand with code.
        if kind in ("oracle", "slot0") and not ins and not name.startswith("PegOracle"):
            out = [f"unread: {name} {oracle} names no input contract"]
        for a in ins:
            low, sub = a.lower(), memo[":code"][a]
            if low == FLUID_LIQUIDITY.lower():
                continue
            if low in FLUID_SEQUENCER_FEEDS:
                specs.setdefault(low, _fluid_spec("bounded", f"L2 sequencer feed {a}", "uptime check: halts the oracle, moves no price"))
            elif not sub:
                pass  # an account with no code answering for a price: the generic walk scores its key
            elif low not in specs and masked_template(sub) in FLUID_BUILDS:
                out += fluid_oracle_sources(w3, a, specs, memo, depth + 1)
                continue
            elif low not in specs and masked_template(sub) == FLUID_DEX_TEMPLATE:
                specs[low] = _fluid_dex_spec(a)
            elif low not in specs and masked_template(sub) == UNIV3_POOL_TEMPLATE:
                specs[low] = _univ3_pool_spec(a)
            elif low not in specs and call_raw(w3, a, _LATEST_ROUND, "latestRoundData", retries=2) is None:
                specs[low] = _fluid_spec("UNREAD", f"rate source {a}", f"input of {name} {oracle} that is not a price feed and has no verified spec")
            out.append(a)
    memo[key] = list(dict.fromkeys(out))
    return memo[key]


def _fluid_vault_auths(w3, gov):
    """VaultT*Admin.updateOracle re-points a vault's price at once; it is open to VaultFactory.isGlobalAuth / isVaultAuth
    (owner included). Own configuration while the owner is the pinned VaultFactoryOwner (governed by the target's timelock),
    the pinned auths still hold their auth, the fee auths' code is the pinned one, and no auth or ownership log appeared
    since the proof block. The team multisig among them can re-point every vault's oracle with no delay: scored as an Avocado
    multisig (decided after the review of 2026-10-05; the composite's timelockScore note calls these instant powers
    bounded, which this one is not)."""
    label = f"Fluid VaultFactory {FLUID_VAULT_FACTORY} auths (updateOracle, instant)"
    cid = _eth(lambda: w3.eth.chain_id, "chain id")
    if cid not in FLUID_VAULT_AUTHS:
        return [path(label, "UNREAD", note=f"no auth replay pinned for chain {cid}")]
    block, owner, auths = FLUID_VAULT_AUTHS[cid]
    now = _addr(w3, FLUID_VAULT_FACTORY, "owner")
    held = {a: call_raw(w3, FLUID_VAULT_FACTORY, _BOOL("isGlobalAuth", "address"), "isGlobalAuth", _cs(a), retries=2) for a in auths}
    ok = (now == _cs(owner) and _hash(w3, FLUID_VAULT_FACTORY) == FLUID_CODE[FLUID_VAULT_FACTORY] and _hash(w3, owner) == FLUID_CODE["owner"]
          and _addr(w3, owner, "LIQUIDITY") == _cs(FLUID_LIQUIDITY) and _addr(w3, owner, "FACTORY") == _cs(FLUID_VAULT_FACTORY)
          and all(v is True for v in held.values()) and all(h is None or _hash(w3, a) == h for a, (_, h) in auths.items())
          and not any(_slot(w3, a, s) for a in (FLUID_VAULT_FACTORY, owner) for s in PROXY_SLOTS))
    if not ok:
        return [path(label, "UNREAD", note=f"owner {now} (pinned {owner}), isGlobalAuth {held}, or a code hash changed since the 2026-10-05 replay")]
    try:
        lw3, chunk = _log_reader(w3, cid)
        changes = logs_since(lw3, FLUID_VAULT_FACTORY, [_VAULT_AUTH_EVENTS], block + 1, max(chunk, 1_000_000))
    except Exception as e:  # noqa: BLE001 -- a failed log read is unknown, never "no change"
        return [path(label, "UNREAD", note=f"auth replay since block {block} failed: {type(e).__name__}")]
    if changes:
        return [path(label, "UNREAD", note=f"{changes} auth or ownership log(s) since block {block}: auth set to re-derive")]
    return [path(label, "own", note=f"owner {owner} (VaultFactoryOwner, the Liquidity timelock); global auths "
                 + ", ".join(f"{a} {what}" for a, (what, _) in auths.items()) + "; the fee auths only set rates")] + [
        _avocado_path(w3, f"Fluid VaultFactory auth {a} (updateOracle on any vault, no delay)", _cs(a))
        for a, (what, _) in auths.items() if what == "team multisig"]


def fluid_usd_weights(chain_id):
    """({token lowercase: (price, decimals)}, {dex lowercase: (token0, token1, token0PerShare, token1PerShare)}) from Fluid's
    public API, used ONLY as USD weights for materiality (decision 8 of 2026-10-05), never for a classification. Empty on
    any failure: every row is then unvalued, hence material."""
    import json
    import urllib.request
    try:
        req = urllib.request.Request(FLUID_API.format(chain_id), headers={"User-Agent": "authority-oracle"})
        vaults = json.loads(urllib.request.urlopen(req, timeout=30).read())
    except Exception:  # noqa: BLE001 -- no weight, never a classification
        return {}, {}
    prices, dexes = {}, {}
    for v in vaults if isinstance(vaults, list) else []:
        for side in ("supply", "borrow"):
            toks = v.get(f"{side}Token") or {}
            for t in toks.values():
                if t.get("price") and t.get("decimals") is not None:
                    prices[t["address"].lower()] = (float(t["price"]), int(t["decimals"]))
            dx = v.get(f"{side}DexData") or {}
            if int(dx.get("address") or "0x0", 16):
                dexes[dx["address"].lower()] = (toks["token0"]["address"].lower(), toks["token1"]["address"].lower(),
                                                int(dx["token0PerShare"]), int(dx["token1PerShare"]))
    return prices, dexes


_VAULT_STATE = [_fn("getVaultState", ("address",), ("uint256",) * 13)]
_T1_CONSTANTS = [_fn("constantsView", (), ("(address,address,address,address,address,address,uint8,uint8,uint256,bytes32,bytes32,bytes32,bytes32)",))]
_TN_CONSTANTS = [_fn("constantsView", (), ("(address,address,address,address,address,address,address,address,(address,address),(address,address),"
                                           "uint256,uint256,bytes32,bytes32,bytes32,bytes32)",))]


def _fluid_debt_usd(w3, vault, vtype, prices, dexes):
    """A vault's debt in USD: VaultResolver.getVaultState totalBorrow (token units, or DEX shares for smart debt), valued with
    the API prices (and the API per-share amounts of its borrow DEX). 0 when it owes nothing; None when unknown."""
    st = call_raw(w3, FLUID_VAULT_RESOLVER, _VAULT_STATE, "getVaultState", _cs(vault), retries=2)
    if st is None:
        return None
    if not st[4]:
        return 0
    cv = call_raw(w3, vault, _T1_CONSTANTS if vtype == 10000 else _TN_CONSTANTS, "constantsView", retries=2)
    if cv is None:
        return None
    if vtype in (10000, 20000):
        tok = (cv[5] if vtype == 10000 else cv[9][0]).lower()
        return st[4] * prices[tok][0] / 10 ** prices[tok][1] if tok in prices else None
    d = dexes.get(cv[7].lower())
    if not d or d[0] not in prices or d[1] not in prices:
        return None
    return st[4] / 1e18 * sum(per / 10 ** prices[t][1] * prices[t][0] for t, per in ((d[0], d[2]), (d[1], d[3])))


def fluid_rows(w3, specs, notes, weights=None):
    """[(vault, sources, debt in USD)] for every vault of the VaultResolver: its oracle's sources (fluid_oracle_sources), and
    the VaultFactory, whose auths can swap that oracle (_fluid_vault_auths). A vault with no oracle and no debt reads no
    price; with debt (or unread) it is a row with no source. None when the vault list is unread."""
    vaults = call_raw(w3, FLUID_VAULT_RESOLVER, _LIST("getAllVaultsAddresses"), "getAllVaultsAddresses")
    if vaults is None:
        return None
    cid = _eth(lambda: w3.eth.chain_id, "chain id")
    prices, dexes = weights if weights is not None else fluid_usd_weights(cid)
    specs[FLUID_VAULT_FACTORY.lower()] = _fluid_vault_auths
    rows, memo = [], {}
    for v in vaults:
        t = call_raw(w3, FLUID_VAULT_RESOLVER, _UINT("getVaultType", "address"), "getVaultType", _cs(v), retries=2)
        raw = call_raw(w3, FLUID_VAULT_RESOLVER, _UINT("getVaultVariables2Raw", "address"), "getVaultVariables2Raw", _cs(v), retries=2)
        usd = _fluid_debt_usd(w3, v, t, prices, dexes) if t in (10000, 20000, 30000, 40000) else None
        if t is None or raw is None:
            rows.append((v, None, usd))
            continue
        idx = (raw >> 92) & (2 ** 30 - 1)
        oracle = (_cs("0x%040x" % (raw >> 96)) if raw >> 96 else None) if t == 10000 else (
            _addr(w3, FLUID_VAULT_RESOLVER, "getContractForDeployerIndex", _cs(v), idx, ins=("address", "uint256")) if idx else None)
        if oracle is None:
            if usd != 0:
                rows.append((v, None, usd))
            continue
        rows.append((v, (FLUID_VAULT_FACTORY,) + tuple(fluid_oracle_sources(w3, oracle, specs, memo)), usd))
    unvalued = [r[0] for r in rows if r[2] is None]
    notes.append(f"{len(rows)} Fluid vaults, debt {sum(r[2] for r in rows if r[2]):,.0f} USD (API prices, weights only); {len(unvalued)} unvalued, counted material"
                 + (f": {unvalued}" if unvalued else ""))
    return rows



# ------------------------------------------------------------------------------------------------- Euler V2 (EVK)
# Study of 2026-10-05 (each recipe re-run by a second reader). An EVK vault prices its liabilities and collaterals through
# oracle(), fixed at creation: an EulerRouter for nearly every vault. EulerRouter (Routescan-verified source, 0xB9c2Cc54 on
# Plasma, solc 0.8.24): govSetConfig, govSetResolvedVault, govSetFallbackOracle and transferGovernance are onlyGovernor with
# no delay; resolveOracle takes the configured adapter, else converts through resolvedVaults (ERC4626 convertToAssets),
# else the fallback oracle, else reverts PriceOracle_NotSupported. The masked template below is the same for the 40
# routers each on Plasma and Monad read live 2026-10-05; any other oracle() is walked as a plain price source.
EULER_USD = "0x0000000000000000000000000000000000000348"  # ISO 4217 code 840: the EVK unit of account for USD
EULER_ROUTER_TEMPLATE = "01393e683f2f52e735f4594e3495e6c7692d12942673cdcb11f71d09242a83d1"
# PendleUniversalOracle (Routescan-verified 0xfa71c252 on Plasma, solc 0.8.24): immutable, rate from PendlePYOracleLib on
# its immutable pendleMarket (an AMM TWAP), scaled by the SY's exchangeRate unless quoted in SY.
PENDLE_UNIVERSAL_TEMPLATE = "6e6605223cd601c4403ad033d7703b7c63a008e46c9d71c47263d7aeb0218e78"
# SY implementations whose owner() can only pause (SYBase), checked against their verified source: {implementation:
# runtime code hash}. PendleDoubleMidasNoRedeemSY behind SY-splUSD 0xad96C88e on Plasma: exchangeRate is
# IMidasDataFeed(mTokenDataFeed).getDataInBase18() with mTokenDataFeed an immutable (2026-10-05). Any other implementation:
# its owner() is scored too.
PENDLE_SY_PAUSE_ONLY_IMPLS = {"0x1cfe03f16eed6b93922be7e415151674638be425": "cef07c2f834f881b366d4dd38f98bf46e03990ece935249463d40cd6a9141317"}
_LTV_FULL = [{"name": "LTVFull", "type": "function", "stateMutability": "view", "inputs": [{"type": "address"}],
              "outputs": [{"type": "uint16"}, {"type": "uint16"}, {"type": "uint16"}, {"type": "uint48"}, {"type": "uint32"}]}]
_RESOLVE = [{"name": "resolveOracle", "type": "function", "stateMutability": "view", "inputs": [{"type": "uint256"}, {"type": "address"}, {"type": "address"}],
             "outputs": [{"type": "uint256"}, {"type": "address"}, {"type": "address"}, {"type": "address"}]}]
_QUOTE = [{"name": "getQuote", "type": "function", "stateMutability": "view", "inputs": [{"type": "uint256"}, {"type": "address"}, {"type": "address"}],
           "outputs": [{"type": "uint256"}]}]
_LIST = lambda name: [{"name": name, "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "address[]"}]}]  # noqa: E731
_PROXY_CONFIG = [{"name": "getProxyConfig", "type": "function", "stateMutability": "view", "inputs": [{"type": "address"}],
                  "outputs": [{"type": "tuple", "components": [{"type": "bool"}, {"type": "address"}, {"type": "bytes"}]}]}]


EULER_NOT_SUPPORTED = bytes.fromhex("4ca22af0")  # PriceOracle_NotSupported(address,address)


def _revert_selector(w3, address, abi, name, *args):
    """The 4 bytes a call reverts with (b"" for a bare revert), None when it does not revert. Network failures retry, then
    raise: never read as a revert."""
    c = w3.eth.contract(address=Web3.to_checksum_address(address), abi=abi)

    def call():
        try:
            getattr(c.functions, name)(*args).call()
            return None
        except ContractLogicError as e:
            d = e.data
            if isinstance(d, str) and d.startswith("0x"):
                return bytes.fromhex(d[2:10])
            return bytes(d[:4]) if isinstance(d, (bytes, bytearray)) else b""
    return _eth(call, f"{name} revert data on {address}")


def _is_euler_router(w3, address):
    """True when `address` runs the pinned EulerRouter build: plain code, no proxy slot, masked template equal."""
    code = _fixed_code(w3, address)
    return code is not None and masked_template(code) == EULER_ROUTER_TEMPLATE


def euler_router_spec(router, own):
    """An EulerRouter's governor re-points any price at once: the target's own governance -> own; zero -> frozen; else
    controller_path. A router whose code is not the pinned build, or whose governor() is unread, is UNREAD."""
    own = {a.lower() for a in own}

    def spec(w3, gov):
        label = f"EulerRouter {router}"
        if not _is_euler_router(w3, router):
            return [path(label, "UNREAD", note="not the pinned EulerRouter build, or a proxy slot is set")]
        g = call_raw(w3, router, _ADDR("governor"), "governor", retries=2)
        if g is None:
            return [path(label, "UNREAD", note="governor() unread")]
        if not int(g, 16):
            return [path(label, "constant", note="governor() is zero: its configuration is frozen")]
        if g.lower() in own:
            return [path(label, "own", note=f"governor {g} is the target's own governance: already in the composite")]
        return [controller_path(w3, Web3.to_checksum_address(g), gov, f"{label} governor (govSetConfig: instant re-point of any price)")]
    return spec


# Euler's FactoryGovernor (6,374 bytes, Routescan-verified, solc 0.8.24; the same runtime on Plasma 0x939cA204 and Monad
# 0x515C9ff6): setImplementation only through adminCall (DEFAULT_ADMIN) or a pause / unpause that swaps in a read-only proxy.
EULER_FACTORY_GOVERNOR_HASH = "9bd008078058c7a0152c22f6dc1f5ebcaab8028bd674388a86fdb35b83ce3265"


def euler_factory_upgrade_path(w3, factory, gov, own):
    """The EVK factory's implementation upgrade: upgradeAdmin() (a FactoryGovernor) whose only DEFAULT_ADMIN
    (getRoleMemberCount = 1) is a TimelockController. Own -> own; that timelock >= the target's delay -> governance-grade;
    anything else UNREAD."""
    label = f"EVK factory {factory} implementation upgrade"
    ua = _addr(w3, factory, "upgradeAdmin")
    if ua is None:
        return path(label, "UNREAD", note="upgradeAdmin() unread")
    if ua.lower() in own:
        return path(label, "own", note=f"upgradeAdmin {ua} is the target's own governance")
    code = _fixed_code(w3, ua)  # only the verified build, with no proxy slot, routes setImplementation through its DEFAULT_ADMIN
    if code is None or Web3.keccak(code).hex().removeprefix("0x") != EULER_FACTORY_GOVERNOR_HASH:
        return path(label, "UNREAD", note=f"upgradeAdmin {ua} is not the verified FactoryGovernor build, or has a proxy slot")
    n = call_raw(w3, ua, _UINT("getRoleMemberCount", "bytes32"), "getRoleMemberCount", b"\x00" * 32, retries=2)
    tl = _addr(w3, ua, "getRoleMember", b"\x00" * 32, 0, ins=("bytes32", "uint256")) if n == 1 else None
    if tl and tl.lower() in own:
        return path(label, "own", note=f"FactoryGovernor {ua}'s sole DEFAULT_ADMIN {tl} is the target's own timelock")
    d = call_raw(w3, tl, _UINT("getMinDelay"), "getMinDelay", retries=2) if tl else None
    if d and gov and d >= gov and _verified_timelock(w3, tl):
        return path(label, "governance-grade", note=f"FactoryGovernor {ua}'s sole DEFAULT_ADMIN is timelock {tl}, getMinDelay {d}s >= {gov}s")
    return path(label, "UNREAD", note=f"FactoryGovernor {ua}: {n} DEFAULT_ADMIN(s), timelock {tl} delay {d}s, target delay {gov}s")


def evk_rate_spec(vault, factory, own):
    """An ERC4626 conversion a router makes through an EVK vault of `factory`: its share price moves only by its own
    interest accrual, capped by EVK's MAX_ALLOWED_INTEREST_RATE (bounded), and by an upgrade of the factory's
    implementation when the vault is upgradeable (an unread proxy config counts as upgradeable). A vault the factory does
    not list is UNREAD."""
    own = {a.lower() for a in own}

    def spec(w3, gov):
        if not factory or call_raw(w3, factory, _BOOL("isProxy", "address"), "isProxy", _cs(vault), retries=2) is not True:
            return [path(f"ERC4626 rate {vault}", "UNREAD", note=f"not an EVK vault of the factory {factory} and no verified spec: who sets its rate is not established")]
        cfg = call_raw(w3, factory, _PROXY_CONFIG, "getProxyConfig", _cs(vault), retries=2)
        out = [path(f"EVK vault rate {vault}", "bounded", note="share price from its own accounting; interest capped by MAX_ALLOWED_INTEREST_RATE")]
        if cfg is None or cfg[0]:
            out.append(euler_factory_upgrade_path(w3, factory, gov, own))
        return out
    return spec


def pendle_universal_spec(oracle):
    """A PendleUniversalOracle (pinned build) on an immutable Pendle market: the PT rate is an AMM TWAP with no controller,
    scaled by the SY's exchangeRate unless quoted in SY (then bounded). The first contract someone else controls is the SY:
    its upgrade (admin slot, followed to the ProxyAdmin's owner) is scored, and its owner() too unless its implementation
    is pinned as pause-only. The SY's own exchange-rate inputs are deeper and disclosed, not scored."""
    def spec(w3, gov):
        o = _cs(oracle)
        code = _fixed_code(w3, o)
        market = _addr(w3, o, "pendleMarket")
        toks = call_raw(w3, market, [_fn("readTokens", (), ("address", "address", "address"))], "readTokens", retries=2) if market else None
        if code is None or masked_template(code) != PENDLE_UNIVERSAL_TEMPLATE or not toks or any(_slot(w3, market, s) for s in PROXY_SLOTS):
            return [path(f"Pendle oracle {o}", "UNREAD", note=f"not the pinned PendleUniversalOracle build, market {market} tokens unread, or the market is a proxy")]
        sy, quote = _cs(toks[0]), _addr(w3, o, "quote")
        note = f"market {market} (immutable AMM TWAP), SY {sy}; the SY's own rate inputs are deeper, disclosed"
        if quote is None:
            return [path(f"Pendle oracle {o}", "UNREAD", note="quote() unread")]
        if quote.lower() == sy.lower():
            return [path(f"Pendle oracle {o}", "bounded", note=note + ": quoted in SY, the SY rate is not read")]
        admin, impl, beacon = _admin_slot(w3, sy), _slot(w3, sy, IMPL_SLOT), _slot(w3, sy, BEACON_SLOT)
        if not admin and impl:
            return [path(f"Pendle SY {sy}", "UNREAD", note="SY is a proxy without a readable admin slot")]
        paths = [controller_path(w3, admin, gov, f"Pendle SY {sy} upgrade (admin slot {admin}) behind oracle {o}")] if admin else []
        if beacon:  # a beacon proxy: whoever owns the beacon swaps the implementation
            impl = _addr(w3, beacon, "implementation")
            paths.append(controller_path(w3, _addr(w3, beacon, "owner"), gov, f"Pendle SY {sy} beacon {beacon} owner() (upgrade) behind oracle {o}"))
        pinned = PENDLE_SY_PAUSE_ONLY_IMPLS.get((impl or "").lower())
        if pinned and Web3.keccak(_code(w3, impl)).hex().removeprefix("0x") == pinned:
            note += f"; implementation {impl} pinned: owner() can only pause"
        else:
            paths.append(controller_path(w3, _addr(w3, sy, "owner"), gov, f"Pendle SY {sy} owner() (implementation {impl} not analyzed)"))
        for p in paths:
            p["note"] += "; " + note
        return paths or [path(f"Pendle oracle {o}", "bounded", note=note + ": SY not upgradeable, owner pause-only")]
    return spec


def _register_adapter_specs(w3, adapter, specs, depth=0):
    """A Pendle adapter (it answers pendleMarket()) gets pendle_universal_spec; a CrossAdapter's legs are visited too."""
    if depth > 3 or adapter.lower() in specs:
        return
    if _addr(w3, adapter, "pendleMarket"):
        specs[adapter.lower()] = pendle_universal_spec(adapter)
        return
    for g in ("oracleBaseCross", "oracleCrossQuote"):
        leg = _addr(w3, adapter, g)
        if leg:
            _register_adapter_specs(w3, leg, specs, depth + 1)


def euler_vault_sources(w3, vault, factory, own, specs, notes):
    """(sources, value) of one EVK vault, or (None, None) when it reads no price (oracle() zero) or lends against nothing
    (no collateral with a borrow or liquidation LTV). Sources: its oracle; through a pinned EulerRouter, the adapter it
    resolves for the vault's asset and for each live collateral and every vault it converts through on the way. A base the
    router does not price (resolveOracle reverts: PriceOracle_NotSupported) secures nothing and is noted. Value: totalAssets
    quoted in USD by the vault's oracle, ('non-USD', asset, totalAssets) for another unit of account, None when unread.
    Specs are added for the router, each conversion vault (a chain spec wins) and each Pendle adapter."""
    raw = call_raw(w3, vault, _ADDR("oracle"), "oracle", retries=2)
    if raw is None:
        return (), None  # unread: a row with no source
    if not int(raw, 16):
        return None, None
    oracle, uoa, asset = _cs(raw), _addr(w3, vault, "unitOfAccount"), _addr(w3, vault, "asset")
    cols = call_raw(w3, vault, _LIST("LTVList"), "LTVList", retries=2)
    if cols is None or uoa is None or asset is None:
        return (), None
    live, now = [], None
    for c in cols:  # an unread LTV counts as live; so does a liquidation LTV still ramping down to zero
        ltv = call_raw(w3, vault, _LTV_FULL, "LTVFull", _cs(c), retries=2)
        if ltv is not None and not ltv[0] and not ltv[1] and ltv[2]:
            now = now or _eth(lambda: w3.eth.get_block("latest")["timestamp"], "latest block time")
        if ltv is None or ltv[0] or ltv[1] or (ltv[2] and ltv[3] > now):
            live.append(c)
    if not live:
        return None, None
    srcs = [oracle]
    if _is_euler_router(w3, oracle):
        specs[oracle.lower()] = euler_router_spec(oracle, own)
        for base in [asset] + live:
            res = call_raw(w3, oracle, _RESOLVE, "resolveOracle", 10 ** 18, _cs(base), uoa, retries=2)
            if res is None:
                if _revert_selector(w3, oracle, _RESOLVE, "resolveOracle", 10 ** 18, _cs(base), uoa) != EULER_NOT_SUPPORTED:
                    # another revert (a stale rate, a broken input): the price exists, its path is unknown; the sources
                    # already resolved for this vault are still walked
                    srcs.append(f"unread: router {oracle} resolveOracle({base}) reverts, not with PriceOracle_NotSupported")
                    continue
                notes.append(f"{vault}: router {oracle} prices no {base} -> {uoa} (PriceOracle_NotSupported): unpriced, secures no borrow")
                continue
            b, hops = _cs(base), 0
            while b.lower() != res[1].lower():  # each ERC4626 the router converts through on its way to the priced base
                rv = _addr(w3, oracle, "resolvedVaults", b, ins=("address",))
                if rv is None or hops > 4:
                    srcs.append(f"unread: router {oracle} conversion chain of {base} unread or longer than 5 vaults")
                    break
                specs.setdefault(b.lower(), evk_rate_spec(b, factory, own))
                srcs.append(b)
                b, hops = rv, hops + 1
            else:
                if int(res[3], 16):
                    srcs.append(_cs(res[3]))
                    _register_adapter_specs(w3, _cs(res[3]), specs)
                continue
    ta = call_raw(w3, vault, _UINT("totalAssets"), "totalAssets", retries=2)
    if ta is None or not ta:
        value = ta
    elif uoa.lower() == EULER_USD:
        value = call_raw(w3, oracle, _QUOTE, "getQuote", ta, asset, uoa, retries=2)
    else:
        value = ("non-USD", asset, ta)
    return tuple(dict.fromkeys(srcs)), value


def euler_rows(w3, vaults, factory, own, specs, notes, weights=None):
    """[(vault, sources, value)] for the lending vaults among `vaults`. Value: the vault's totalAssets in USD, or
    weights[vault lowercase] (an Earn vault's allocation) when given. A non-USD unit of account is valued through the first
    USD-priced vault oracle that quotes the asset; none -> None (material). An unread vault is a row with no source."""
    rows = []
    for v in vaults:
        if not Web3.is_address(v):
            rows.append((v, None, None))
            continue
        srcs, value = euler_vault_sources(w3, v, factory, own, specs, notes)
        if srcs is None:
            continue
        rows.append([v, srcs or None, weights.get(v.lower()) if weights is not None else value])
    usd_oracles = [o for o in dict.fromkeys(_addr(w3, v, "oracle") for v in vaults if Web3.is_address(v)
                                            and (_addr(w3, v, "unitOfAccount") or "").lower() == EULER_USD) if o]
    for r in rows:
        if isinstance(r[2], tuple):
            _, asset, ta = r[2]
            r[2] = next((q for q in (call_raw(w3, o, _QUOTE, "getQuote", ta, asset, EULER_USD, retries=2) for o in usd_oracles) if q), None)
    return [tuple(r) for r in rows]


def euler_factory_governance(w3, factory):
    """(delay, own) of an EVK factory: the getMinDelay() of the sole DEFAULT_ADMIN timelock of its upgradeAdmin (None when
    unread or not exactly one), and {factory, upgradeAdmin, that timelock}."""
    ua = _addr(w3, factory, "upgradeAdmin")
    n = call_raw(w3, ua, _UINT("getRoleMemberCount", "bytes32"), "getRoleMemberCount", b"\x00" * 32) if ua else None
    tl = _addr(w3, ua, "getRoleMember", b"\x00" * 32, 0, ins=("bytes32", "uint256")) if n == 1 else None
    d = call_raw(w3, tl, _UINT("getMinDelay"), "getMinDelay") if tl else None
    return d, {a for a in (factory, ua, tl) if a}


def euler_earn_weights(w3, earn):
    """{strategy lowercase (or 'strategy i' when unread): assets the Earn vault holds there} from its withdraw queue:
    config(strategy).balance shares, previewRedeem'd by the strategy. None when the queue length is unread."""
    n = call_raw(w3, earn, _UINT("withdrawQueueLength"), "withdrawQueueLength")
    if n is None:
        return None
    cfg_abi = [_fn("config", ("address",), ("uint112", "uint136", "bool", "uint64"))]
    out = {}
    for i in range(n):
        s = _addr(w3, earn, "withdrawQueue", i, ins=("uint256",))
        cfg = call_raw(w3, earn, cfg_abi, "config", s) if s else None
        held = None if cfg is None else (call_raw(w3, s, _UINT("previewRedeem", "uint256"), "previewRedeem", cfg[0]) if cfg[0] else 0)
        out[s.lower() if s else f"strategy {i}"] = held
    return out


def _elixir_sdeusd_plasma(w3, gov):
    """sdeUSD on Plasma 0x7884A845 (an ERC4626 a router converts through): UUPS, _authorizeUpgrade is onlyRole(DEFAULT_ADMIN)
    and owner() returns the current default admin (verified implementation 0xb2F28684, Routescan). Scored: owner(), while
    the implementation is the pinned one and owner() holds DEFAULT_ADMIN. REWARDER_ROLE (transferInRewards, vested, can
    only raise the rate by the tokens it sends) is disclosed, not scored."""
    v, impl_expected = _cs("0x7884A8457f0E63e82C89A87fE48E8Ba8223DB069"), "0xb2f28684b04660a334ea27401e5468323213011b"
    label = f"sdeUSD (Plasma) {v} upgrade (owner = DEFAULT_ADMIN)"
    impl, owner = _slot(w3, v, IMPL_SLOT), _addr(w3, v, "owner")
    has = call_raw(w3, v, _BOOL("hasRole", "bytes32", "address"), "hasRole", b"\x00" * 32, owner) if owner else None
    same = impl and impl.lower() == impl_expected and Web3.keccak(_code(w3, impl)).hex().removeprefix("0x") == SDEUSD_PLASMA_IMPL_HASH
    if not same or has is not True:
        return [path(label, "UNREAD", note=f"implementation {impl}, owner {owner}, hasRole(DEFAULT_ADMIN, owner) {has}: not the analyzed shape")]
    p = controller_path(w3, owner, gov, label)
    p["note"] += "; REWARDER_ROLE transferInRewards raises the rate by what it sends (disclosed)"
    return [p]


SDEUSD_PLASMA_IMPL_HASH = "4598e29b64f98aa31cf70531bd992a7894f45d0431da1530601ec8369ef30857"  # 16,062 bytes, read live 2026-10-05

PLASMA_SPECS = {
    "0x7884A8457f0E63e82C89A87fE48E8Ba8223DB069": _elixir_sdeusd_plasma,  # sdeUSD (an Euler router converts esdeUSD-2 through it)
}


# ------------------------------------------------------------------------------------------------- entry points
def _fail_closed(fn):
    """A read that raises (RpcUnavailable after its retries, a malformed answer) gives UNKNOWN_SCORE and a note, never a
    crashed scorer: the walk is one field of the target, its other reads stand on their own."""
    def run(w3, target, specs=None, notes=None, **kw):
        notes = [] if notes is None else notes
        try:
            return fn(w3, target, specs, notes, **kw)
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
def for_sparklend(w3, provider, specs=None, notes=None):
    """oracleAuthorityScore of SparkLend (its PoolAddressesProvider): the Aave V3 rows, governance delay = MCD_PAUSE.delay()
    behind SparkProxy (spark_governance; None, no bar, when a link does not hold)."""
    notes = [] if notes is None else notes
    delay, own, how = spark_governance(w3, provider)
    rows = aave_rows(w3, provider)
    if rows is None:
        notes.append(f"oracleAuthorityScore {UNKNOWN_SCORE}: {UNREAD_MARK} ['reserve list or price oracle'] -- unknown, not 100")
        return UNKNOWN_SCORE
    notes.append(f"governance delay (MCD_PAUSE.delay() behind SparkProxy) = {delay}s: {how}")
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
def for_moonwell(w3, comptroller, specs=None, notes=None):
    """oracleAuthorityScore of Moonwell (its Unitroller): every market's supply at the oracle price, reaching the feed the
    ChainlinkOracle reads for it; governance delay = admin().proposalDelay() (the TemporalGovernor)."""
    notes = [] if notes is None else notes
    delay, own = moonwell_governance(w3, comptroller)
    if MOONWELL_TEMPORAL_GOVERNOR.lower() in {a.lower() for a in own}:  # the verdicts of these specs hold only under that governor
        specs = {**(specs or {}), **MOONWELL_SPECS}
    rows = moonwell_rows(w3, comptroller)
    if rows is None:
        notes.append(f"oracleAuthorityScore {UNKNOWN_SCORE}: {UNREAD_MARK} ['markets or oracle'] -- unknown, not 100")
        return UNKNOWN_SCORE
    notes.append(f"governance delay (TemporalGovernor proposalDelay()) = {delay}s; supply = cash + borrows - reserves")
    return score(w3, rows, delay, specs, own, notes)


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


@_fail_closed
def for_morpho_v2(w3, vault, specs=None, notes=None):
    """oracleAuthorityScore of a Morpho Vault V2: its adapters' markets' oracles weighted by the current allocation;
    governance delay = the minimum live fund-redirecting / exit-gate timelock (None: no governance-grade bar)."""
    notes = [] if notes is None else notes
    delay, own = morpho_v2_governance(w3, vault)
    rows = morpho_v2_rows(w3, vault, notes)
    if rows is None:
        notes.append(f"oracleAuthorityScore {UNKNOWN_SCORE}: {UNREAD_MARK} ['adapters'] -- unknown, not 100")
        return UNKNOWN_SCORE
    notes.append(f"governance delay (minimum fund-redirecting / exit-gate timelock) = {delay}s; shares = current allocation")
    return score(w3, rows, delay, specs, own, notes)


@_fail_closed
def for_aave_v2(w3, provider, specs=None, notes=None):
    """oracleAuthorityScore of an Aave V2 market (its LendingPoolAddressesProvider): governance delay = the AaveOracle
    owner's getMinDelay(), 0 when that owner is not a timelock."""
    notes = [] if notes is None else notes
    delay, own, stray = aave_v2_governance(w3, provider)
    rows = aave_v2_rows(w3, provider)
    if rows is not None and stray:
        rows.append((f"AaveOracle owner {stray}: instant setAssetSources, a root the composite does not score" if stray != "unread"
                     else "AaveOracle owner() unread: who can re-point a source is unknown", None, None))
    if rows is None:
        notes.append(f"oracleAuthorityScore {UNKNOWN_SCORE}: {UNREAD_MARK} ['reserve list or price oracle'] -- unknown, not 100")
        return UNKNOWN_SCORE
    notes.append(f"governance delay (AaveOracle owner getMinDelay(), 0 when not a timelock) = {delay}s")
    return score(w3, rows, delay, specs, own, notes)


@_fail_closed
def for_gmx_v2(w3, rolestore, specs=None, notes=None):
    """oracleAuthorityScore of GMX V2 Synthetics (tracked as its RoleStore): governance delay = the live
    ConfigTimelockController's getMinDelay(); priced supply = pools plus open interest of the provider rows."""
    notes = [] if notes is None else notes
    delay, own, controller, oracle = gmx_v2_governance(w3, rolestore)
    got = gmx_v2_rows(w3, oracle) if oracle else None
    if got is None:
        notes.append(f"oracleAuthorityScore {UNKNOWN_SCORE}: {UNREAD_MARK} ['GMX markets, pools or oracle providers'] -- unknown, not 100")
        return UNKNOWN_SCORE
    rows, total = got
    notes.append(f"governance delay (ConfigTimelockController {controller} getMinDelay()) = {delay}s; Oracle {oracle}; priced supply {total:,.0f} USD")
    return score(w3, rows, delay, specs, own, notes, total=total)


@_fail_closed
def for_gmx_v1(w3, vault, specs=None, notes=None):
    """oracleAuthorityScore of the GMX V1 Vault: governance delay = gov().buffer() (the Vault's own Timelock)."""
    notes = [] if notes is None else notes
    tl = _addr(w3, vault, "gov")
    delay = call_raw(w3, tl, _UINT("buffer"), "buffer") if tl else None
    got = gmx_v1_rows(w3, vault)
    if got is None:
        notes.append(f"oracleAuthorityScore {UNKNOWN_SCORE}: {UNREAD_MARK} ['GMX V1 whitelisted tokens'] -- unknown, not 100")
        return UNKNOWN_SCORE
    rows, total = got
    notes.append(f"governance delay (Vault.gov() {tl} buffer()) = {delay}s; priced supply {total:,.0f} USD")
    return score(w3, rows, delay, specs, {a for a in (vault, tl) if a}, notes, total=total)


@_fail_closed
def for_euler_factory(w3, factory, specs=None, notes=None):
    """oracleAuthorityScore of an EVK eVaultFactory (the registry and upgrade root of its vaults, as an Aave
    PoolAddressesProvider stands for its market): one row per lending vault, its totalAssets in USD reaching its router,
    its asset and collateral adapters and the vaults the router converts through. Governance delay = the factory's
    upgradeAdmin's sole DEFAULT_ADMIN timelock; own = {factory, upgradeAdmin, that timelock}."""
    notes = [] if notes is None else notes
    delay, own = euler_factory_governance(w3, factory)
    n = call_raw(w3, factory, _UINT("getProxyListLength"), "getProxyListLength")
    vaults = call_raw(w3, factory, [_fn("getProxyListSlice", ("uint256", "uint256"), ("address[]",))], "getProxyListSlice", 0, n) if n is not None else None
    if vaults is None:
        notes.append(f"oracleAuthorityScore {UNKNOWN_SCORE}: {UNREAD_MARK} ['factory vault list'] -- unknown, not 100")
        return UNKNOWN_SCORE
    specs = {k.lower(): v for k, v in (specs or {}).items()}
    rows = euler_rows(w3, vaults, factory, own, specs, notes)
    notes.append(f"governance delay (upgradeAdmin's sole DEFAULT_ADMIN timelock getMinDelay()) = {delay}s; {len(rows)} lending vaults of {len(vaults)}, "
                 "weighted by totalAssets in USD")
    return score(w3, rows, delay, specs, own, notes)


@_fail_closed
def for_euler_earn(w3, earn, specs=None, notes=None, factory=None):
    """oracleAuthorityScore of an EulerEarn vault (a Morpho V1 fork whose strategies are EVK vaults of `factory`): each
    strategy's price paths weighted by the Earn's allocation; governance delay = timelock(); own = {earn}: its owner and
    curator act at once on a router or vault they govern, which the Earn's timelock does not gate, so those are scored."""
    notes = [] if notes is None else notes
    earn = _cs(earn)
    delay = call_raw(w3, earn, _UINT("timelock"), "timelock")
    own = {earn}
    weights = euler_earn_weights(w3, earn)
    if weights is None:
        notes.append(f"oracleAuthorityScore {UNKNOWN_SCORE}: {UNREAD_MARK} ['withdraw queue'] -- unknown, not 100")
        return UNKNOWN_SCORE
    specs = {k.lower(): v for k, v in (specs or {}).items()}
    rows = euler_rows(w3, [k for k, held in weights.items() if held != 0], factory, own, specs, notes, weights)
    notes.append(f"governance delay (Earn timelock()) = {delay}s; strategies' factory {factory}; shares = current allocation")
    return score(w3, rows, delay, specs, own, notes)


@_fail_closed
def for_fluid(w3, liquidity, specs=None, notes=None, weights=None):
    """oracleAuthorityScore of a Fluid Liquidity layer: one row per vault of the VaultResolver, its debt in USD (API prices,
    weights only) reaching its oracle's sources and the VaultFactory auths. Governance delay = getMinDelay() of the
    Liquidity's getAdmin() (its TimelockController); own = {Liquidity, that timelock, the VaultFactory and its owner, the
    DexFactory}. `weights`: (prices, dexes) as fluid_usd_weights returns them, for tests."""
    notes = [] if notes is None else notes
    liquidity = _cs(liquidity)
    if liquidity != _cs(FLUID_LIQUIDITY):
        notes.append(f"oracleAuthorityScore {UNKNOWN_SCORE}: {UNREAD_MARK} ['not the Fluid Liquidity {FLUID_LIQUIDITY}'] -- unknown, not 100")
        return UNKNOWN_SCORE
    tl = _addr(w3, liquidity, "getAdmin")
    delay = call_raw(w3, tl, _UINT("getMinDelay"), "getMinDelay") if tl and _verified_timelock(w3, tl) else None  # an unverified build is no bar
    own = {a for a in (liquidity, tl, FLUID_VAULT_FACTORY, _addr(w3, FLUID_VAULT_FACTORY, "owner"), FLUID_DEX_FACTORY) if a}
    specs = {k.lower(): v for k, v in (specs or {}).items()}
    rows = fluid_rows(w3, specs, notes, weights)
    if rows is None:
        notes.append(f"oracleAuthorityScore {UNKNOWN_SCORE}: {UNREAD_MARK} ['VaultResolver vault list'] -- unknown, not 100")
        return UNKNOWN_SCORE
    notes.append(f"governance delay (Liquidity getAdmin() {tl} getMinDelay()) = {delay}s; rows = vaults, weighted by debt in USD")
    return score(w3, rows, delay, specs, own, notes)


# Dolomite's own-configuration verdicts hold only for a target governed by DolomiteMargin's owner: for_dolomite adds them, no
# other Arbitrum target passes them.
DOLOMITE_SPECS = {
    DOLOMITE_CONSTANT_PRICE_ORACLE[0]: _dolomite_constant_price,  # Dolomite ConstantPriceOracle (own configuration)
    DOLOMITE_GM_ORACLE[0]: _dolomite_gm_price,  # Dolomite GmxV2MarketTokenPriceOracle (GMX Reader and DataStore)
}


@_fail_closed
def for_dolomite(w3, margin, specs=None, notes=None):
    """oracleAuthorityScore of a DolomiteMargin: each market's oracle paths (dolomite_rows) weighed against the priced supply;
    governance delay and own = dolomite_governance (0 while a bypass executor of DolomiteOwnerV2 holds both roles)."""
    notes = [] if notes is None else notes
    specs = {**(specs or {}), **DOLOMITE_SPECS}
    delay, own, why = dolomite_governance(w3, margin)
    got = dolomite_rows(w3, margin, own, notes)
    if got is None:
        notes.append(f"oracleAuthorityScore {UNKNOWN_SCORE}: {UNREAD_MARK} ['Dolomite markets'] -- unknown, not 100")
        return UNKNOWN_SCORE
    rows, total = got
    notes.append(f"governance delay ({why}) = {delay}s; priced supply {total:,.0f} USD")
    return score(w3, rows, delay, specs, own, notes, total=total)
