"""Ed25519 signature verification (RFC 8032), standard library only. Verification only: this package never signs.

It is slow (a few milliseconds per point multiplication in pure Python, about 50 ms per check) and used once per refresh of the manifest. It is checked against the RFC 8032 test vectors
and against PyNaCl in the tests. Cofactorless verification, as libsodium does it: S must be below the group order, and the point R and the public key must decode.
"""
import hashlib

P = 2 ** 255 - 19
Q = 2 ** 252 + 27742317777372353535851937790883648493
D = (-121665 * pow(121666, P - 2, P)) % P
SQRT_M1 = pow(2, (P - 1) // 4, P)


def _recover_x(y, sign):
    if y >= P: return None
    x2 = (y * y - 1) * pow(D * y * y + 1, P - 2, P) % P
    if x2 == 0: return None if sign else 0
    x = pow(x2, (P + 3) // 8, P)
    if (x * x - x2) % P != 0: x = x * SQRT_M1 % P
    if (x * x - x2) % P != 0: return None
    if (x & 1) != sign: x = P - x
    return x


_BY = 4 * pow(5, P - 2, P) % P
_BX = _recover_x(_BY, 0)
G = (_BX, _BY, 1, _BX * _BY % P)
ZERO = (0, 1, 1, 0)


def point_add(p1, p2):
    a = (p1[1] - p1[0]) * (p2[1] - p2[0]) % P
    b = (p1[1] + p1[0]) * (p2[1] + p2[0]) % P
    c = 2 * p1[3] * p2[3] * D % P
    d = 2 * p1[2] * p2[2] % P
    e, f, g, h = b - a, d - c, d + c, b + a
    return (e * f % P, g * h % P, f * g % P, e * h % P)


def point_mul(s, pt):
    q = ZERO
    while s > 0:
        if s & 1: q = point_add(q, pt)
        pt = point_add(pt, pt)
        s >>= 1
    return q


def point_equal(p1, p2):
    return (p1[0] * p2[2] - p2[0] * p1[2]) % P == 0 and (p1[1] * p2[2] - p2[1] * p1[2]) % P == 0


def decompress(s):
    if len(s) != 32: return None
    y = int.from_bytes(s, "little"); sign = y >> 255; y &= (1 << 255) - 1
    x = _recover_x(y, sign)
    return None if x is None else (x, y, 1, x * y % P)


def verify(public_key, message, signature):
    """True only for a valid signature of `message` by `public_key` (32 bytes), `signature` being 64 bytes. Never raises on malformed input."""
    try:
        if len(public_key) != 32 or len(signature) != 64: return False
        a = decompress(public_key); r = decompress(signature[:32])
        if a is None or r is None: return False
        s = int.from_bytes(signature[32:], "little")
        if s >= Q: return False
        h = int.from_bytes(hashlib.sha512(signature[:32] + public_key + message).digest(), "little") % Q
        return point_equal(point_mul(s, G), point_add(r, point_mul(h, a)))
    except Exception:  # noqa: BLE001 -- anything malformed is simply not a valid signature
        return False


# --- used by the tests only: signing and key derivation, so that a test can build a signed manifest without a third-party library
def _clamp(h):
    a = int.from_bytes(h[:32], "little"); a &= (1 << 254) - 8; a |= 1 << 254
    return a


def public_from_seed(seed):
    h = hashlib.sha512(seed).digest(); a = _clamp(h)
    x, y, z, _t = point_mul(a, G); zi = pow(z, P - 2, P); x, y = x * zi % P, y * zi % P
    return (y | ((x & 1) << 255)).to_bytes(32, "little")


def sign(seed, message):
    h = hashlib.sha512(seed).digest(); a = _clamp(h); pk = public_from_seed(seed)
    r = int.from_bytes(hashlib.sha512(h[32:] + message).digest(), "little") % Q
    x, y, z, _t = point_mul(r, G); zi = pow(z, P - 2, P); x, y = x * zi % P, y * zi % P
    rs = (y | ((x & 1) << 255)).to_bytes(32, "little")
    k = int.from_bytes(hashlib.sha512(rs + pk + message).digest(), "little") % Q
    return rs + ((r + k * a) % Q).to_bytes(32, "little")
