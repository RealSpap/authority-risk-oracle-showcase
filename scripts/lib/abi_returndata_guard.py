"""ABI return-data size guard: a getter that returns more (or less) than its declared ABI says must not be read silently.

THE TRAP. `eth_abi.decode(["uint256"], data)` returns the FIRST 32-byte word of `data` and ignores whatever follows, and web3.py's
`contract.functions.f().call()` goes through the same decoder. A getter that returns a struct or several values, read with a
single-value ABI, therefore does not revert and does not raise: it hands back the first word as if it were the answer. It happened
for real on 2026-09-20 (`getScore(address)` returns the `AuthorityScore` struct, read as `uint256` it gave `adminKeyScore = 3` in
place of `compositeScore`, and a verification "agreed" on the wrong number, see data/rotation_audit_2026-09-20-robinhood-chain-index16.md).
The same decoder is behind every scorer read in this repository.

WHAT THIS DOES. `classify(types, data)` compares the return data with what the declared output types require:
  * all-static outputs (uint/int/bool/address/bytesN, static arrays and tuples of those): the length must be exactly the sum of the
    static sizes. Longer means a struct or extra outputs were read with a shorter ABI (the trap), shorter means the data is not
    what the ABI says.
  * outputs that include a dynamic type (string, bytes, T[]): the length must cover the head (one 32-byte word per dynamic output
    plus the static ones), and what was decoded must re-encode to exactly the length that came back. A getter that returns several
    values, read with one dynamic output (`address[]` where the contract returns `(address[], uint256)`), decodes without error and
    drops the rest; its canonical encoding is shorter than the data, which is how it is caught. Solidity and Vyper emit canonical
    encodings; an answer whose canonical re-encoding has a different length than the one returned is refused, which degrades the
    target instead of trusting an unusual layout. Only the LENGTH is compared: a non-canonical layout of the same total length is not
    seen, and neither is the one case that is a valid canonical encoding of the narrower type itself, `(uint256 = 32, T)` read as `[T]`
    (the first word then reads as a valid offset and the rest re-encodes to the same bytes: no check on the bytes can tell them apart).
  * empty data for a function that declares outputs is its own kind (an address without code answers an `eth_call` with empty data
    instead of reverting) and is left to the original decoder, which raises by itself.
`install()` patches `eth_abi.codec.ABICodec.decode` (web3's contract calls) and the module-level `eth_abi.decode` (scripts that decode by
hand, such as Tempo's own call primitive, when they import it after `install()`), either to RECORD every mismatch with the file and
line of the caller (audit mode, nothing changes for the caller) or to RAISE `ReturnDataSizeMismatch` (a DecodingError, so web3 turns it
into its usual BadFunctionCallOutput and the helpers that already treat a failed decode as "not this interface" degrade the way they
do for a revert). The helpers swallow that exception, so a refusal is logged once to stderr with its caller; it is otherwise seen as
an unresolved read, never as a confident wrong number. scripts/audit_abi_returndata.py runs every ecosystem's score_all() with
`install("record", ...)`.
"""
import atexit
import json
import os
import sys
import threading

import eth_abi
import eth_abi.abi
from eth_abi.codec import ABICodec
from eth_abi.exceptions import DecodingError
from eth_abi.grammar import TupleType, parse

MODES = ("record", "raise")

# what the codec is BEFORE any patch (this module is the only patcher): the layout check decodes with it, and uninstall restores it.
# If another module object of this file already installed the guard (it was imported under a second name), the true original is kept on
# its wrapper: this object then neither stacks a second patch nor mistakes the first wrapper for the original.
_ORIGINAL_DECODE = getattr(ABICodec.decode, "__aro_original__", ABICodec.decode)
_HAD_OWN_DECODE = "decode" in ABICodec.__dict__ and not hasattr(ABICodec.decode, "__aro_original__")


class ReturnDataSizeMismatch(DecodingError, ValueError):
    """The return data does not have the size the declared ABI outputs require. A DecodingError, so web3 turns it into its usual
    BadFunctionCallOutput exactly like any other undecodable answer, and a ValueError for callers that catch that."""


def _size(node):
    """Byte size of a static ABI type, None if it is dynamic."""
    if node.is_dynamic:
        return None
    base = sum(_size(c) for c in node.components) if isinstance(node, TupleType) else 32
    for dim in (node.arrlist or ()):
        base *= dim[0]
    return base


def expected_size(types):
    """(bytes, exact): the size the outputs require, and whether the data must have exactly that size (all static)
    or at least that size (a dynamic output: the head only)."""
    total, exact = 0, True
    for t in types:
        node = parse(t)
        s = _size(node)
        if s is None:
            total += 32
            exact = False
        else:
            total += s
    return total, exact


def _canonical_length(types, data):
    """The length of the canonical encoding of what `data` decodes to under `types`, None when it cannot be decoded and re-encoded
    (the original decoder then raises by itself, or the value has no encoding to compare)."""
    try:
        decoded = _ORIGINAL_DECODE(eth_abi.abi.default_codec, types, data)
        return len(eth_abi.encode(types, decoded))
    except Exception:  # noqa: BLE001
        return None


def classify(types, data):
    """None when `data` has the size `types` require, else (kind, message). kind is "empty" (no data at all), "more" or "fewer"
    (an all-static output list with more or fewer bytes than it takes), "head" (a dynamic output list shorter than its head) or
    "layout" (a dynamic output list whose decoded values do not re-encode to the length that came back)."""
    types = list(types)
    if not types:
        return None
    n = len(data)
    need, exact = expected_size(types)
    if n == 0:
        return ("empty", f"empty return data for outputs {types} (an address without code answers an eth_call this way)")
    if exact and n != need:
        kind = "more" if n > need else "fewer"
        return (kind, f"{n} bytes returned for outputs {types} which take exactly {need}: {kind} than declared"
                      f"{', a struct or extra outputs read with a shorter ABI silently give their first words' if kind == 'more' else ''}")
    if not exact:
        if n < need:
            return ("head", f"{n} bytes returned for outputs {types} whose head alone takes {need}")
        canonical = _canonical_length(types, data)
        if canonical is not None and canonical != n:
            return ("layout", f"{n} bytes returned for outputs {types} whose canonical encoding takes {canonical}: "
                              f"{'more' if n > canonical else 'fewer'} than declared"
                              f"{', extra returned values read with a shorter ABI are silently dropped' if n > canonical else ''}")
    return None


def check_return(types, data):
    """The message of `classify`, or None when the size is right."""
    c = classify(types, data)
    return c[1] if c else None


_THIS_FILE = os.path.realpath(__file__)
_state = {"mode": None, "sink": None, "records": {}, "original": None, "module_originals": None, "checked": 0,
          "atexit": False, "logged": set()}
_lock = threading.Lock()


def _caller():
    f = sys._getframe(2)
    # skip frames inside eth_abi / web3 / this module to name the scorer line that asked for the decode
    while f is not None and (os.path.realpath(f.f_code.co_filename) == _THIS_FILE
                             or any(p in f.f_code.co_filename for p in ("/eth_abi/", "/web3/", "/site-packages/"))):
        f = f.f_back
    return f"{os.path.relpath(f.f_code.co_filename) if f else '?'}:{f.f_lineno if f else '?'}"


def _guarded_decode(self, types, data, strict=True):
    with _lock:
        _state["checked"] += 1
    found = classify(types, data)
    if found:
        kind, problem = found
        key = (tuple(types), len(data), _caller())
        log_key = (key[0], key[2])           # one stderr line per call site and output types, whatever the answer sizes
        # empty data is left to the original decoder, which raises InsufficientDataBytes (a DecodingError) by itself
        if _state["mode"] == "raise" and kind != "empty":
            with _lock:
                first = log_key not in _state["logged"]
                _state["logged"].add(log_key)
            if first:
                sys.stderr.write(f"ABI return-data guard: REFUSED at {key[2]}: {problem}\n")
            raise ReturnDataSizeMismatch(problem)
        with _lock:
            rec = _state["records"].setdefault(key, {"kind": kind, "types": list(types), "bytes": len(data), "caller": key[2],
                                                     "problem": problem, "count": 0})
            rec["count"] += 1
    return _state["original"](self, types, data, strict)


def _module_decode(types, data, strict=True):
    return _guarded_decode(eth_abi.abi.default_codec, types, data, strict)


def install(mode="raise", sink=None):
    """Patch the decoder process-wide. mode "record" keeps decoding exactly as before and writes the mismatches to `sink`
    (a JSON file) at exit, mode "raise" makes a mismatch raise ReturnDataSizeMismatch. Idempotent."""
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}")
    if _state["original"] is None:
        if hasattr(ABICodec.decode, "__aro_original__"):
            return                            # another module object of this file already installed the guard: one patch, its state
        _guarded_decode.__aro_original__ = ABICodec.decode
        _state["original"] = ABICodec.decode
        ABICodec.decode = _guarded_decode
        _state["module_originals"] = (eth_abi.decode, eth_abi.abi.decode)
        eth_abi.decode = eth_abi.abi.decode = _module_decode
    _state["mode"], _state["sink"] = mode, sink
    if mode == "record" and sink and not _state["atexit"]:
        atexit.register(dump)
        _state["atexit"] = True


def ensure_installed(mode="raise"):
    """Install the guard in `mode` unless it is already installed (an earlier install keeps its mode, so the audit tool's "record"
    is never switched to "raise" by a library that imports this module afterwards)."""
    if _state["original"] is None:
        install(mode)


def uninstall():
    if _state["original"] is not None:
        if _HAD_OWN_DECODE:
            ABICodec.decode = _state["original"]
        else:
            del ABICodec.decode          # it was inherited: leave the class as it was found
        eth_abi.decode, eth_abi.abi.decode = _state["module_originals"]
        _state["original"] = _state["module_originals"] = None
    with _lock:
        _state["records"].clear()
        _state["logged"].clear()
        _state["checked"] = 0
    _state["mode"] = None
    _state["sink"] = None


def records():
    with _lock:
        return sorted(_state["records"].values(), key=lambda r: (r["caller"], r["bytes"]))


def dump():
    if _state["sink"]:
        with open(_state["sink"], "w", encoding="utf-8") as f:
            json.dump({"checked": _state["checked"], "mismatches": records()}, f)
