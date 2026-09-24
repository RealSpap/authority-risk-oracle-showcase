"""
Minimal Solana write/read helpers for the deploy_testnet phase
(chains/solana/deploy/update_scores_solana.py and read_scores_solana.py).

Stdlib + PyNaCl only (PyNaCl is what generated the pipeline's throwaway
devnet key in the first place, see keys/authority-risk-oracle/solana-devnet/.env's
own "generated" note). No solana-py / anchorpy dependency, same discipline as
chains/solana/scripts/sol_read.py.

What is here, and nothing more:
  - base58 encode/decode of 32-byte pubkeys and 64-byte signatures
  - ed25519 "is this 32-byte string on the curve" check, needed for
    find_program_address (a PDA must be OFF the curve)
  - legacy (non-versioned) transaction message serialization + signing
  - JSON-RPC calls: getLatestBlockhash, sendTransaction, getSignatureStatuses,
    getAccountInfo, getGenesisHash, getSlot
  - wait_program_invocable(): program executable AND deployed before the
    current confirmed slot (avoids the deploy->initialize race)

SAFETY GUARD: `assert_not_mainnet(rpc_url)` refuses any RPC whose genesis
hash is Solana Mainnet Beta's. Every write path in this directory calls it
before signing anything. This pipeline may only ever write to Devnet or a
localhost solana-test-validator.
"""
import base64
import hashlib
import json
import struct
import time
import urllib.request

B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"

MAINNET_BETA_GENESIS = "5eykt4UsFv8P8NJdTREpY1vzqKqZKvdpKuc147dw2N9d"
DEVNET_GENESIS = "EtWTRABZaYq6iMfeYKouRu166VU2xqa1wcaWoxPkrZBG"
SYSTEM_PROGRAM_ID = "11111111111111111111111111111111"

# --- base58 -----------------------------------------------------------------


def b58encode(b: bytes) -> str:
    n = int.from_bytes(b, "big")
    s = ""
    while n:
        n, r = divmod(n, 58)
        s = B58[r] + s
    return "1" * (len(b) - len(b.lstrip(b"\0"))) + s


def b58decode(s: str, length: int) -> bytes:
    n = 0
    for ch in s:
        n = n * 58 + B58.index(ch)
    n_leading = len(s) - len(s.lstrip("1"))
    out = b"\x00" * n_leading + (n.to_bytes(length - n_leading, "big") if length > n_leading else b"")
    # to_bytes() silently left-pads a short value with zero bytes, which
    # would turn e.g. a 32-byte pubkey passed where 64 bytes are expected
    # into a different, wrong value -- re-encode and require an exact match
    # (caught by test_solana_deploy_tx.TestBase58.test_wrong_length_rejected).
    if len(out) != length or b58encode(out) != s:
        raise ValueError(f"base58 value {s!r} does not decode to exactly {length} bytes")
    return out


# --- ed25519 on-curve check (for PDA derivation) ----------------------------

_P = 2**255 - 19
_D = (-121665 * pow(121666, _P - 2, _P)) % _P


def is_on_curve(b: bytes) -> bool:
    """True iff `b` decompresses to an ed25519 point, matching
    curve25519-dalek's CompressedEdwardsY::decompress().is_some() (which
    Solana's `Pubkey::is_on_curve` / `find_program_address` use): the y
    coordinate is the low 255 bits (sign bit ignored, not reduced-checked),
    and the point exists iff (y^2 - 1) / (d*y^2 + 1) is a square mod p."""
    y = int.from_bytes(b, "little") & ((1 << 255) - 1)
    y %= _P
    u = (y * y - 1) % _P
    v = (_D * y * y + 1) % _P
    w = (u * pow(v, _P - 2, _P)) % _P
    return w == 0 or pow(w, (_P - 1) // 2, _P) == 1


def find_program_address(seeds, program_id: bytes):
    for bump in range(255, -1, -1):
        h = hashlib.sha256(b"".join(seeds) + bytes([bump]) + program_id + b"ProgramDerivedAddress").digest()
        if not is_on_curve(h):
            return h, bump
    raise RuntimeError("no valid PDA bump found")


# --- keypair loading (never prints the secret) ------------------------------


def load_keypair(path: str):
    """Accepts either a solana-keygen style JSON uint8[64] array, or this
    pipeline's keys/*.json dict format (`secret_key_uint8_array`). Returns
    (nacl SigningKey, 32-byte pubkey). Verifies the embedded pubkey matches
    the seed-derived one before returning."""
    import nacl.signing

    with open(path) as f:
        d = json.load(f)
    arr = d["secret_key_uint8_array"] if isinstance(d, dict) else d
    raw = bytes(arr)
    if len(raw) != 64:
        raise ValueError("keypair must be 64 bytes (seed + pubkey)")
    sk = nacl.signing.SigningKey(raw[:32])
    pub = bytes(sk.verify_key)
    if pub != raw[32:]:
        raise ValueError("keypair file is inconsistent: seed-derived pubkey != embedded pubkey")
    if isinstance(d, dict) and d.get("pubkey_base58") and d["pubkey_base58"] != b58encode(pub):
        raise ValueError("keypair file pubkey_base58 does not match its secret key")
    return sk, pub


# --- JSON-RPC ----------------------------------------------------------------


def rpc(url: str, method: str, params=None, retries: int = 4):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params or []}).encode()
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, data=body, headers={"content-type": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as r:
                resp = json.loads(r.read())
            if "error" in resp:
                raise RuntimeError(f"{method} RPC error: {resp['error']}")
            return resp["result"]
        except RuntimeError:
            raise
        except Exception as e:  # transient transport error
            last = e
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"{method} failed after {retries} attempts: {last}")


def assert_not_mainnet(url: str) -> str:
    g = rpc(url, "getGenesisHash")
    if g == MAINNET_BETA_GENESIS:
        raise SystemExit(
            f"REFUSING: {url} is Solana Mainnet Beta (genesis {g}). This pipeline never writes to mainnet."
        )
    return g


def get_account_data(url: str, pubkey_b58: str):
    res = rpc(url, "getAccountInfo", [pubkey_b58, {"encoding": "base64", "commitment": "confirmed"}])
    v = res["value"]
    if v is None:
        return None, None
    return base64.b64decode(v["data"][0]), v["owner"]


BPF_LOADER_UPGRADEABLE_ID = "BPFLoaderUpgradeab1e11111111111111111111111"


def parse_upgradeable_program(data: bytes) -> str:
    """Program account of the upgradeable loader: u32 LE enum tag (2 =
    Program) + 32-byte ProgramData address. Returns that address (base58)."""
    if len(data) < 36 or struct.unpack_from("<I", data, 0)[0] != 2:
        raise ValueError("not an upgradeable-loader Program account")
    return b58encode(data[4:36])


def parse_programdata_slot(data: bytes) -> int:
    """ProgramData account: u32 LE enum tag (3 = ProgramData) + u64 LE
    slot of the last deploy/upgrade + Option<Pubkey> authority + ELF."""
    if len(data) < 12 or struct.unpack_from("<I", data, 0)[0] != 3:
        raise ValueError("not an upgradeable-loader ProgramData account")
    return struct.unpack_from("<Q", data, 4)[0]


def wait_program_invocable(url: str, program_id_b58: str, timeout_s: int = 60, poll_s: float = 0.5) -> dict:
    """Block until `program_id_b58` can actually be invoked on `url`.

    A program deployed (or upgraded) in slot N is NOT invocable in slot N
    itself: the runtime answers 'Program is not deployed' /
    UnsupportedProgramId until the bank moves past N. Sending `initialize`
    right after `solana program deploy` therefore races (seen 2/2 times by
    the 2026-09-19 verifier on a local validator; the same deploy->initialize
    sequence is what deploy/README.md recommends on Devnet). So: require the
    program account to exist, be executable and owned by the upgradeable
    loader, read its ProgramData 'last deployed slot', and wait until the
    *confirmed* slot (the commitment sendTransaction preflights against) is
    strictly greater. Raises RuntimeError on timeout."""
    deadline = time.time() + timeout_s
    last_state = "program account not found"
    while time.time() < deadline:
        v = rpc(url, "getAccountInfo", [program_id_b58, {"encoding": "base64", "commitment": "confirmed"}])["value"]
        if v is not None and v.get("executable") and v.get("owner") == BPF_LOADER_UPGRADEABLE_ID:
            pdata_addr = parse_upgradeable_program(base64.b64decode(v["data"][0]))
            pd, _ = get_account_data(url, pdata_addr)
            if pd is not None:
                deployed_slot = parse_programdata_slot(pd)
                cur = rpc(url, "getSlot", [{"commitment": "confirmed"}])
                if cur > deployed_slot:
                    return {"program_id": program_id_b58, "programdata": pdata_addr,
                            "last_deployed_slot": deployed_slot, "confirmed_slot": cur}
                last_state = f"confirmed slot {cur} <= last deployed slot {deployed_slot}"
            else:
                last_state = f"ProgramData {pdata_addr} not found"
        elif v is not None:
            last_state = f"account exists but executable={v.get('executable')} owner={v.get('owner')}"
        time.sleep(poll_s)
    raise RuntimeError(f"program {program_id_b58} not invocable on {url} within {timeout_s}s ({last_state})")


# --- legacy transaction ------------------------------------------------------


def _compact_u16(n: int) -> bytes:
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


def build_signed_tx(signing_key, payer: bytes, program_id: bytes, accounts, data: bytes, blockhash_b58: str) -> bytes:
    """Single-instruction legacy transaction with one signer (the payer).
    `accounts` = list of (pubkey_bytes, is_signer, is_writable) in the
    instruction's own order. Account keys in the message are ordered as the
    runtime requires: writable signers, readonly signers, writable
    non-signers, readonly non-signers; the program id goes last
    (readonly non-signer)."""
    metas = {}
    order = []

    def add(pk, signer, writable):
        if pk in metas:
            s, w = metas[pk]
            metas[pk] = (s or signer, w or writable)
        else:
            metas[pk] = (signer, writable)
            order.append(pk)

    add(payer, True, True)
    for pk, s, w in accounts:
        add(pk, s, w)
    add(program_id, False, False)

    def rank(pk):
        s, w = metas[pk]
        return (0 if s and w else 1 if s else 2 if w else 3)

    keys = sorted(order, key=lambda pk: (rank(pk), order.index(pk)))
    # payer must be first
    assert keys[0] == payer
    n_sig = sum(1 for k in keys if metas[k][0])
    n_ro_signed = sum(1 for k in keys if metas[k][0] and not metas[k][1])
    n_ro_unsigned = sum(1 for k in keys if not metas[k][0] and not metas[k][1])
    if n_sig != 1:
        raise ValueError("this helper only supports a single signer (the payer)")

    idx = {k: i for i, k in enumerate(keys)}
    ix = bytes([idx[program_id]]) + _compact_u16(len(accounts)) + bytes(idx[pk] for pk, _, _ in accounts)
    ix += _compact_u16(len(data)) + data

    msg = bytes([n_sig, n_ro_signed, n_ro_unsigned]) + _compact_u16(len(keys)) + b"".join(keys)
    msg += b58decode(blockhash_b58, 32) + _compact_u16(1) + ix

    sig = signing_key.sign(msg).signature
    return _compact_u16(1) + sig + msg


def send_and_confirm(url: str, raw_tx: bytes, timeout_s: int = 60) -> str:
    sig = rpc(url, "sendTransaction", [base64.b64encode(raw_tx).decode(), {"encoding": "base64", "preflightCommitment": "confirmed"}])
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        st = rpc(url, "getSignatureStatuses", [[sig], {"searchTransactionHistory": True}])["value"][0]
        if st is not None:
            if st.get("err"):
                raise RuntimeError(f"transaction {sig} failed: {st['err']}")
            if st.get("confirmationStatus") in ("confirmed", "finalized"):
                return sig
        time.sleep(0.5)
    raise RuntimeError(f"transaction {sig} not confirmed within {timeout_s}s")


def anchor_discriminator(kind: str, name: str) -> bytes:
    """Anchor convention: instructions sha256("global:<ix>")[:8], accounts
    sha256("account:<StructName>")[:8]."""
    return hashlib.sha256(f"{kind}:{name}".encode()).digest()[:8]
