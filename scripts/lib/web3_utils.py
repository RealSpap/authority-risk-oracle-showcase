"""
Small, dependency-light helpers for tracing on-chain authority.

The rule this whole project runs on: never trust a block explorer's "verified
contract name" or a project's own docs as the final answer about who controls
what. Every helper here does a real eth_call (or two, against independent
RPCs) and returns what the chain actually says.
"""
import os
import sys
import time
from eth_abi.exceptions import DecodingError
from web3 import Web3
from web3.exceptions import (
    BadFunctionCallOutput,
    ContractLogicError,
    Web3RPCError,
)

# One canonical module object for the guard whatever the way this file was imported (`web3_utils` or `lib.web3_utils`); appended, never
# inserted first, so it cannot shadow a chain's own module of the same name (scripts/lib/scorers.py exists).
_LIB_DIR = os.path.dirname(os.path.abspath(__file__))
if _LIB_DIR not in sys.path:
    sys.path.append(_LIB_DIR)
import abi_returndata_guard  # noqa: E402

# Same canonicalization, same reason, for RpcUnavailable (see rpc_unavailable.py's own docstring):
# ADDED 2026-09-22 after action was rejected for the bug this exists to prevent -- a caller
# that reached this class via `lib.web3_utils` raised a DIFFERENT class object than one that reached
# it via bare `web3_utils`, so its `except RpcUnavailable` silently missed. Defining the class here
# directly, however this file itself was imported, could never have closed that: this bare import is
# what pins every importer to the one class in sys.modules['rpc_unavailable'].
import rpc_unavailable  # noqa: E402

# A getter that returns a struct or several values, read with a single-value ABI, does not revert: the decoder hands back the first
# 32-byte word as if it were the answer. With the guard a return of the wrong size raises instead, which the helpers below already
# treat as "not this interface" (see scripts/lib/abi_returndata_guard.py, scripts/audit_abi_returndata.py).
abi_returndata_guard.ensure_installed("raise")

# Canonical EIP-1967 storage slots (bytes32(uint256(keccak256(<name>)) - 1)).
EIP1967_IMPLEMENTATION_SLOT = "0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc"
EIP1967_ADMIN_SLOT = "0xb53127684a568b3173ae13b9f8a6016e243e63b6e8ee1178d6a717850b5d6103"

_SAFE_ABI = [
    {"name": "getOwners", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "address[]"}]},
    {"name": "getThreshold", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "uint256"}]},
]

_ADDRESS_GETTER_ABI = lambda name: [  # noqa: E731
    {"name": name, "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "address"}]}
]

_ADDRESS_ARRAY_GETTER_ABI = lambda name: [  # noqa: E731
    {"name": name, "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "address[]"}]}
]


def get_w3(rpc_url: str) -> Web3:
    return Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 20}))


def is_eoa(w3: Web3, address: str) -> bool:
    """True if `address` has no deployed bytecode -- a real, bare externally-owned account."""
    return w3.eth.get_code(Web3.to_checksum_address(address)) == b""


# Alias, not a redefinition -- see rpc_unavailable.py and the import above. `web3_utils.RpcUnavailable`
# and `lib.web3_utils.RpcUnavailable` (and every other importer, whatever path it uses) are now
# guaranteed to be the exact same class object, `is`-identical, not just equal by name.
RpcUnavailable = rpc_unavailable.RpcUnavailable


def _is_revert(exc: Exception) -> bool:
    """True only for a confirmed EVM revert or a structurally-impossible decode -- the contract (or
    the decoder) itself answering "not this interface", a real fact worth keeping as `None`. False
    for everything else, INCLUDING every exception type this function doesn't recognize: the
    classification deliberately defaults to "network failure", because skipping a target via
    `RpcUnavailable` is always safer than silently scoring it from an ambiguous `None`.

    - ContractLogicError / BadFunctionCallOutput: web3.py's own revert signals.
    - DecodingError: raised by eth_abi (and by this module's own abi_returndata_guard, installed at
      import time above) when a call returns data of the wrong size/shape for the ABI asked for --
      exactly the "single-value ABI reading a struct" trap that guard exists to catch, which is a
      real "not this interface" fact, not a network problem.
    - Web3RPCError whose JSON-RPC error carries code 3 (the code chains/tempo/scripts/methodology_test.py
      already keys on for the same distinction) or a message containing "execution reverted": some
      providers surface a revert as a JSON-RPC error object rather than raising ContractLogicError.
    """
    if isinstance(exc, (ContractLogicError, BadFunctionCallOutput, DecodingError)):
        return True
    if isinstance(exc, Web3RPCError):
        err = (getattr(exc, "rpc_response", None) or {}).get("error") or {}
        if err.get("code") == 3:
            return True
        return "execution reverted" in str(err.get("message", "")).lower()
    return False


def _read(fn, retries: int = 4, what: str = "a read", classify=_is_revert):
    """Replaces a bare `except Exception: return None` at each helper's call site below. Same
    backoff schedule as `_retrying()` (0.4, 0.8, 1.2s between up to `retries` attempts), but the two
    outcomes of a failure are no longer the same value:

    - a confirmed revert (`classify(exc)` is True -- `_is_revert` by default) returns None
      IMMEDIATELY -- no point retrying a deterministic answer, and it stops costing up to
      `0.4*(retries-1)` seconds of sleep on every legitimate "this isn't the right interface" read
      (a real, measured slowdown: this project has already logged full runs exceeding 50 minutes).
    - anything else retries with backoff, then raises RpcUnavailable once every attempt is spent,
      instead of quietly returning the same None a revert would have produced.

    `classify` is a parameter, not always `_is_revert`, because `read_slot_as_address` below passes
    `lambda _: False`: eth_getStorageAt cannot revert, so treating ANY exception there as "maybe a
    revert" would be wrong even in the (currently theoretical) case of some future exception type
    `_is_revert` happens to also recognize -- that helper's whole contract is "never return None",
    and it must hold by construction, not by coincidence of what `_is_revert` currently matches.

    `retries=1` (the override several ecosystems already pass at call sites EXPECTED to revert, e.g.
    Aerodrome PoolFactory.owner() in chains/base-ecosystem/scorers.py) keeps its meaning -- a single
    attempt -- but now a network failure on that one attempt raises instead of being silently taken
    for the expected revert."""
    last = None
    for attempt in range(1, retries + 1):
        try:
            return fn()
        except Exception as e:
            if classify(e):
                return None
            last = e
            if attempt < retries:
                time.sleep(0.4 * attempt)
    raise RpcUnavailable(f"{what}: unreadable after {retries} attempt(s) -- {type(last).__name__}: {last}")


def _retrying(fn, retries=4):
    """Retry with light backoff before giving up on a transient RPC failure (a
    None result from one of this module's own exception-swallowing calls
    below). Added 2026-09-17: this module's own eth_call helpers -- the ones
    the real weekly production cron (`scripts/update_scores.py` -> `score_all()`)
    actually runs against live RPCs -- had NO retry at all, unlike
    `chains/ethereum-l1/scorers.py` and `chains/base-ecosystem/scorers.py`,
    which had each independently copied an identical local `_retrying()` to
    work around this same gap (see those files' own FIXED 2026-09-17 notes).
    Centralized here once, before a third ecosystem (Arbitrum) copies it
    again -- both of those files now import the retrying versions below
    directly instead of keeping their own copies."""
    result = fn()
    attempt = 1
    while result is None and attempt < retries:
        time.sleep(0.4 * attempt)
        result = fn()
        attempt += 1
    return result


ARBITRUM_L1_L2_ALIAS_OFFSET = 0x1111000000000000000000000000000000001111


def arbitrum_l1_l2_alias(l1_address: str) -> str:
    """Deterministic Arbitrum L1->L2 address alias (the `msg.sender` identity an
    L1 contract's canonical-bridge-relayed call arrives as on L2). An alias is
    never itself the target of a contract deployment -- no bytecode, no private
    key -- so it reads exactly like a bare EOA to a mechanical `is_eoa()` check,
    which is the correct, expected result for a legitimate cross-domain
    governance call, not evidence of a vanity-mined or compromised key. See
    data/correction_2026-09-16-uniswap-bridge-alias.md for the incident this
    formula corrects (Uniswap's real L1 Governance Timelock was misread as a
    "vanity-ground bare EOA" on Robinhood Chain before this was traced)."""
    l1_int = int(Web3.to_checksum_address(l1_address), 16)
    aliased = (l1_int + ARBITRUM_L1_L2_ALIAS_OFFSET) % (2**160)
    return Web3.to_checksum_address(f"0x{aliased:040x}")


def read_address_getter(w3: Web3, address: str, function_name: str, retries: int = 4):
    """Call a no-arg, address-returning view function. Returns None on a confirmed revert (the
    caller should treat that as 'this isn't the right interface', not as 'no authority exists
    here'). Raises RpcUnavailable if every retry attempt hits a persistent RPC failure instead --
    unlike a revert, that's not information about the chain, and a caller that only checks
    `is not None` before scoring a dimension must not see the two conflated (see RpcUnavailable)."""
    def _call():
        contract = w3.eth.contract(address=Web3.to_checksum_address(address), abi=_ADDRESS_GETTER_ABI(function_name))
        return getattr(contract.functions, function_name)().call()
    return _read(_call, retries, what=f"{function_name}() on {address}")


def read_address_array_getter(w3: Web3, address: str, function_name: str, retries: int = 4):
    """Same contract as read_address_getter(), for a no-arg getter that returns `address[]` instead
    of a single `address` -- e.g. a bespoke role-registry's getFreezerRoleMembers()-style accessor
    (Agora's AUSD; see scripts/check_issuer_power.py). Returns None on a confirmed revert, raises
    RpcUnavailable on a persistent network failure -- never conflate the two (see read_address_getter's
    own docstring for why)."""
    def _call():
        contract = w3.eth.contract(address=Web3.to_checksum_address(address), abi=_ADDRESS_ARRAY_GETTER_ABI(function_name))
        return getattr(contract.functions, function_name)().call()
    return _read(_call, retries, what=f"{function_name}() on {address}")


def read_slot_as_address(w3: Web3, address: str, slot: str, retries: int = 4):
    """Returns the checksum address stored at `slot`. `eth_getStorageAt` cannot revert -- a slot on
    an address with no code, or one that was never written, simply reads back as 32 zero bytes --
    so unlike the other helpers in this module, a failure here is NEVER a legitimate "no answer":
    it always means the read didn't happen (network, timeout, rate limit). Raises RpcUnavailable
    once every retry attempt is spent, rather than returning None, which a caller could otherwise
    mistake for "this slot is genuinely unset" instead of "this RPC call never completed". Passes
    `classify=lambda _: False` -- never treat ANY exception here as a revert, by construction, not
    by coincidence of what _is_revert() happens to currently recognize (see _read()'s docstring)."""
    def _call():
        raw = w3.eth.get_storage_at(Web3.to_checksum_address(address), int(slot, 16))
        return Web3.to_checksum_address("0x" + raw.hex()[-40:])
    return _read(_call, retries, what=f"storage slot {slot} on {address}", classify=lambda _: False)


# ADDED 2026-09-21 -- the Safe authority gate. A Safe's owners and threshold are only "who can act" if no module can
# execute as the Safe and its logic is a known Safe build. Every scorer that resolves a Safe through
# safe_owners_and_threshold() therefore treats a Safe with an UNANALYZED module, or a singleton that is neither a published
# Safe build nor analyzed, as UNRESOLVED authority (this function returns None, exactly like "not a Safe"), so the existing
# conservative-score path applies without touching each scorer. What counts as analyzed lives in scripts/lib/safe_modules.py
# (KNOWN_ANALYSES, KNOWN_SINGLETON_ANALYSES). A module list that cannot be READ is NOT treated as a finding: the score is left
# as it was and a note says so. Guards and fallback handlers never degrade (they cannot act as the Safe, only block).
# `check_modules=False` is for callers that want only the owner set (cross-ecosystem sweeps, signer overlap), where dropping a
# gated Safe's signers would hide a real overlap.
_AUTHORITY_GATE_LOG = []        # (safe, "blocking" | "info", text): drained by safe_score() into the result's notes
_AUTHORITY_GATE_CACHE = {}      # (endpoint, safe) -> (monotonic time, blocking, info)
_AUTHORITY_GATE_TTL_SECONDS = 300


def _safe_modules_lib():
    try:
        from . import safe_modules  # imported as scripts.lib.web3_utils / lib.web3_utils
    except ImportError:
        import safe_modules  # imported as a bare module with scripts/lib on sys.path
    return safe_modules


def _authority_gate(w3: Web3, address: str, retries: int):
    """(blocking, info): lists of strings about `address`'s modules and singleton. Cached briefly, a run reads the
    same Safe from several scorers."""
    endpoint = getattr(getattr(w3, "provider", None), "endpoint_uri", None) or id(w3)
    key = (endpoint, address.lower())
    hit = _AUTHORITY_GATE_CACHE.get(key)
    if hit and time.monotonic() - hit[0] < _AUTHORITY_GATE_TTL_SECONDS:
        return hit[1], hit[2]
    blocking, info = _safe_modules_lib().gate_findings(w3, address, retries)
    _AUTHORITY_GATE_CACHE[key] = (time.monotonic(), blocking, info)
    return blocking, info


def safe_owners_and_threshold(w3: Web3, address: str, retries: int = 4, check_modules: bool = True):
    """Returns (owners: list[str], threshold: int) if `address` is a real Gnosis Safe, or None if
    the getOwners()/getThreshold() calls revert (not a Safe) -- or, since 2026-09-21, if the Safe
    carries an unanalyzed module or an unanalyzed non-published singleton (see the authority gate
    above; pass check_modules=False to skip it). Raises RpcUnavailable if every retry attempt hits
    a persistent RPC failure instead of revert -- see RpcUnavailable's docstring for why that must
    not come back as the same None a real "not a Safe" answer would."""
    def _call():
        contract = w3.eth.contract(address=Web3.to_checksum_address(address), abi=_SAFE_ABI)
        owners = contract.functions.getOwners().call()
        threshold = contract.functions.getThreshold().call()
        return owners, threshold
    resolved = _read(_call, retries, what=f"getOwners()/getThreshold() on {address}")
    if resolved is None or not check_modules:
        return resolved
    blocking, info = _authority_gate(w3, address, retries)
    for text in blocking:
        _AUTHORITY_GATE_LOG.append((Web3.to_checksum_address(address), "blocking", text))
    for text in info:
        _AUTHORITY_GATE_LOG.append((Web3.to_checksum_address(address), "info", text))
    return None if blocking else resolved


_CUSTOM_MULTISIG_ABI = [
    {"name": "getSigners", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "address[]"}]},
    {"name": "threshold", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "uint256"}]},
]


def custom_multisig_owners_and_threshold(w3: Web3, address: str, retries: int = 4):
    """Returns (signers: list[str], threshold: int) for a bespoke on-chain
    multisig that is NOT a Gnosis Safe -- i.e. exposes getSigners()/threshold()
    instead of getOwners()/getThreshold(). Discovered on LayerZero's own
    Robinhood Chain infra ownership contract (batch 8): a real 5-of-7 custom
    multisig, invisible to safe_owners_and_threshold() since getOwners() and
    getThreshold() both revert on it. Returns None if this pattern doesn't
    match either (confirmed revert). Raises RpcUnavailable if every retry
    attempt hits a persistent RPC failure instead -- the caller should treat
    that as 'unresolved, try again later', not silently as an EOA or a Safe,
    which a bare None indistinguishable from a real revert used to invite."""
    def _call():
        contract = w3.eth.contract(address=Web3.to_checksum_address(address), abi=_CUSTOM_MULTISIG_ABI)
        signers = contract.functions.getSigners().call()
        threshold = contract.functions.threshold().call()
        return signers, threshold
    return _read(_call, retries, what=f"getSigners()/threshold() on {address}")


def call_raw(w3: Web3, address: str, abi_fragment: list, function_name: str, *args, retries: int = 4):
    """Escape hatch for one-off, non-address-returning getters (uint256, bool, bytes32...).
    Returns None on a confirmed revert. Raises RpcUnavailable if every retry attempt hits a
    persistent RPC failure instead of revert -- see RpcUnavailable's docstring."""
    def _call():
        contract = w3.eth.contract(address=Web3.to_checksum_address(address), abi=abi_fragment)
        return getattr(contract.functions, function_name)(*args).call()
    return _read(_call, retries, what=f"{function_name}({', '.join(map(str, args))}) on {address}")


def cross_checked(rpc_urls: list, fn, *args):
    """Run `fn(w3, *args)` against every RPC in rpc_urls and raise if they disagree.
    This is the automated form of the '2+ independent RPCs' rule used throughout
    this project's manual research passes."""
    results = []
    for url in rpc_urls:
        w3 = get_w3(url)
        results.append(fn(w3, *args))
    first = results[0]
    if any(r != first for r in results[1:]):
        raise RuntimeError(f"RPC disagreement for {fn.__name__}{args}: {results} across {rpc_urls}")
    return first


def safe_score(label: str, fn, *args) -> list:
    """Per-target failure isolation for a score_all()-style batch. This is where RpcUnavailable
    (see above) actually lands: a helper's `except Exception` here already catches it like any
    other failure, so a scorer that checks `is not None` on its read results -- instead of wrapping
    them in its own try/except -- now SKIPS the target on a persistent RPC failure rather than
    scoring it from an ambiguous None. Moved here
    2026-09-17 (was scripts/lib/scorers.py's own `_safe_score`, added the same
    day) so every ecosystem's score_all() can import ONE canonical copy
    instead of each re-implementing it -- the exact duplication pattern this
    project already caught once for `_retrying()` and centralized here too,
    closing it before a third or fourth ecosystem's file copies it again.

    A single target's scorer raising (a transient RPC failure surviving every
    retry inside this module's own helpers, or a deliberate loud RuntimeError
    like score_rollup_l1_authority()'s own scan-bug guard) used to crash an
    unguarded score_all() entirely -- failing to push EVERY other target's
    score too, not just the flaky one. This isolates each call: a failure is
    printed (still visible, not silently swallowed) and that target is
    skipped for this run rather than taking the whole batch down. Returns a
    list so callers can .extend() uniformly regardless of whether `fn` itself
    returns one dict or several."""
    start = len(_AUTHORITY_GATE_LOG)
    try:
        result = fn(*args)
        results = result if isinstance(result, list) else [result]
        events = list(_AUTHORITY_GATE_LOG[start:])
        del _AUTHORITY_GATE_LOG[start:]
        # ADDED 2026-09-21: say WHY a Safe was treated as unresolved (the scorer's own note only says "not resolvable").
        seen = set()
        for safe, kind, text in events:
            line = (
                f"SAFE AUTHORITY GATE: Safe {safe} has {text}; its owner set and threshold are not the whole authority, so it was treated as "
                f"unresolved and the conservative score applies (scripts/lib/safe_modules.py, analyze it there to lift this)"
                if kind == "blocking" else
                f"Safe {safe}: {text}, so the score was left as computed, not confirmed"
            )
            if line in seen:
                continue
            seen.add(line)
            for r in results:
                if isinstance(r, dict) and isinstance(r.get("notes"), list):
                    r["notes"].append(line)
        return results
    except Exception as e:
        del _AUTHORITY_GATE_LOG[start:]
        print(f"score_all(): SKIPPED {label} this run -- {type(e).__name__}: {e}")
        return []
