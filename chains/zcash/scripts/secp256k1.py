"""Minimal pure-Python secp256k1: keygen, transparent-address encoding, RFC6979
deterministic ECDSA signing. No third-party deps -- matches this folder's existing
zero-dependency style (zcash_read.py's own docstring: "no deps, uses curl").

Written 2026-09-19 to publish a real testnet proof-of-concept attestation for
METHODOLOGY.md section 8's open "native oracle form" question -- see
`publish_attestation.py` and `zcash_tx.py` in this same folder. TESTNET USE ONLY:
every key this module generates or that `publish_attestation.py` uses is a
throwaway Zcash Testnet key with no mainnet value, generated fresh with
`os.urandom`, never imported from or used for any real-value wallet.
"""
import hashlib, hmac, os, struct

P  = 2**256 - 2**32 - 977
N  = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
Gx = 0x79BE667EF9DCBBAC55A06295CE870B07029BFCDB2DCE28D959F2815B16F81798
Gy = 0x483ADA7726A3C4655DA4FBFC0E1108A8FD17B448A68554199C47D08FFB10D4B8
G  = (Gx, Gy)

def inv(a, m=P):
    return pow(a, m - 2, m)

def point_add(p1, p2):
    if p1 is None: return p2
    if p2 is None: return p1
    x1, y1 = p1; x2, y2 = p2
    if x1 == x2 and (y1 + y2) % P == 0:
        return None
    if p1 == p2:
        lam = (3 * x1 * x1) * inv(2 * y1) % P
    else:
        lam = (y2 - y1) * inv(x2 - x1) % P
    x3 = (lam * lam - x1 - x2) % P
    y3 = (lam * (x1 - x3) - y1) % P
    return (x3, y3)

def scalar_mult(k, point=G):
    result = None
    addend = point
    while k:
        if k & 1:
            result = point_add(result, addend)
        addend = point_add(addend, addend)
        k >>= 1
    return result

def privkey_to_pubkey(priv_int, compressed=True):
    x, y = scalar_mult(priv_int)
    if compressed:
        prefix = b'\x02' if y % 2 == 0 else b'\x03'
        return prefix + x.to_bytes(32, 'big')
    return b'\x04' + x.to_bytes(32, 'big') + y.to_bytes(32, 'big')

def b58encode(b: bytes) -> str:
    ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
    n = int.from_bytes(b, 'big')
    out = ''
    while n:
        n, r = divmod(n, 58)
        out = ALPHABET[r] + out
    pad = 0
    for c in b:
        if c == 0: pad += 1
        else: break
    return '1' * pad + out

def base58check(prefix: bytes, payload: bytes) -> str:
    data = prefix + payload
    chk = hashlib.sha256(hashlib.sha256(data).digest()).digest()[:4]
    return b58encode(data + chk)

def hash160(b: bytes) -> bytes:
    return hashlib.new('ripemd160', hashlib.sha256(b).digest()).digest()

# RFC6979 deterministic k for ECDSA over secp256k1 (SHA-256 as the hash fn)
def rfc6979_k(privkey_int, msg_hash: bytes):
    x = privkey_int.to_bytes(32, 'big')
    h1 = msg_hash
    v = b'\x01' * 32
    k = b'\x00' * 32
    k = hmac.new(k, v + b'\x00' + x + h1, hashlib.sha256).digest()
    v = hmac.new(k, v, hashlib.sha256).digest()
    k = hmac.new(k, v + b'\x01' + x + h1, hashlib.sha256).digest()
    v = hmac.new(k, v, hashlib.sha256).digest()
    while True:
        v = hmac.new(k, v, hashlib.sha256).digest()
        cand = int.from_bytes(v, 'big')
        if 1 <= cand < N:
            return cand
        k = hmac.new(k, v + b'\x00', hashlib.sha256).digest()
        v = hmac.new(k, v, hashlib.sha256).digest()

def ecdsa_sign(privkey_int, msg_hash: bytes) -> bytes:
    """Returns low-S DER-encoded ECDSA signature over a 32-byte digest (the
    digest IS the message, no additional hashing -- matches ZIP-244 sighash
    and Bitcoin-style transaction signing)."""
    z = int.from_bytes(msg_hash, 'big')
    while True:
        k = rfc6979_k(privkey_int, msg_hash)
        x1, y1 = scalar_mult(k)
        r = x1 % N
        if r == 0:
            continue
        s = (inv(k, N) * (z + r * privkey_int)) % N
        if s == 0:
            continue
        if s > N // 2:
            s = N - s
        break
    def der_int(v):
        b = v.to_bytes(32, 'big').lstrip(b'\x00')
        if b[0] & 0x80:
            b = b'\x00' + b
        return b'\x02' + bytes([len(b)]) + b
    rb, sb = der_int(r), der_int(s)
    body = rb + sb
    return b'\x30' + bytes([len(body)]) + body

def der_decode_sig(sig: bytes):
    assert sig[0] == 0x30
    i = 2
    assert sig[i] == 0x02
    ln = sig[i + 1]
    r = int.from_bytes(sig[i + 2:i + 2 + ln], 'big'); i += 2 + ln
    assert sig[i] == 0x02
    ln = sig[i + 1]
    s = int.from_bytes(sig[i + 2:i + 2 + ln], 'big')
    return r, s

def ecdsa_verify(pubkey_bytes: bytes, msg_hash: bytes, sig: bytes) -> bool:
    """Self-check only (this project never trusts a signature it cannot
    independently re-derive verification for -- METHODOLOGY.md's own
    data-collection discipline). Decodes a compressed pubkey and a DER sig."""
    if pubkey_bytes[0] not in (2, 3):
        raise ValueError('expected compressed pubkey')
    x = int.from_bytes(pubkey_bytes[1:], 'big')
    y_sq = (pow(x, 3, P) + 7) % P
    y = pow(y_sq, (P + 1) // 4, P)
    if (y % 2 == 0) != (pubkey_bytes[0] == 2):
        y = P - y
    pub = (x, y)
    r, s = der_decode_sig(sig)
    if not (1 <= r < N and 1 <= s < N):
        return False
    z = int.from_bytes(msg_hash, 'big')
    w = inv(s, N)
    u1, u2 = (z * w) % N, (r * w) % N
    x1, y1 = point_add(scalar_mult(u1, G), scalar_mult(u2, pub))
    return (x1 % N) == r

if __name__ == '__main__':
    priv = int.from_bytes(os.urandom(32), 'big') % N
    pub = privkey_to_pubkey(priv)
    h160 = hash160(pub)
    # Zcash Testnet P2PKH (tm...), lead bytes 1D 25 -- METHODOLOGY.md section 2
    addr = base58check(bytes.fromhex('1d25'), h160)
    print('privkey_hex', priv.to_bytes(32, 'big').hex())
    print('pubkey_hex', pub.hex())
    print('address', addr)
