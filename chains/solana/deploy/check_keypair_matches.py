#!/usr/bin/env python3
"""Read-only diagnostic: does this keypair file parse, and does its derived
pubkey match the expected updater address? Never prints private key bytes,
only the (public) derived pubkey. Reuses solana_tx.py's own b58encode
(no external base58 dependency).

Added 2026-09-24: the solana-devnet keypair file was found to be genuinely
missing from BOTH the pre- and post-migration keys/ locations (not just a
wrong path this time) -- see REPRISE.md, 2026-09-24. Once a keypair file
exists, run this BEFORE a real push:

    python3 chains/solana/deploy/check_keypair_matches.py <path> BcwteMtYL5wL8dvMYWedPT2V6oh1hTgd8vgKEkQyy9yx

(BcwteMtYL5wL8dvMYWedPT2V6oh1hTgd8vgKEkQyy9yx is the expected updater pubkey,
confirmed in chains/solana/deploy/README.md.)

Accepts either shape push_solana_devnet.sh accepts: a raw 64-byte JSON array
(standard solana-keygen format), or a dict with a "secret_key_uint8_array"
field wrapping that array."""
import json
import os
import sys

import nacl.signing

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from solana_tx import b58encode  # noqa: E402

path = sys.argv[1]
expected = sys.argv[2] if len(sys.argv) > 2 else None

with open(path) as f:
    parsed = json.load(f)
arr = parsed["secret_key_uint8_array"] if isinstance(parsed, dict) else parsed
raw = bytes(arr)
if len(raw) != 64:
    sys.exit(f"expected a 64-byte keypair, got {len(raw)} bytes from {path}")
sk = nacl.signing.SigningKey(raw[:32])
derived_pub = b58encode(bytes(sk.verify_key))
embedded_pub = b58encode(raw[32:64])

print(f"file: {path}")
print(f"derived pubkey from bytes[0:32]:  {derived_pub}")
print(f"embedded pubkey in bytes[32:64]:  {embedded_pub}")
print(f"internal match: {'OK' if derived_pub == embedded_pub else 'MISMATCH -- not a valid keypair file'}")
if expected:
    print(f"expected updater pubkey:          {expected}")
    print(f"matches expected: {'YES' if derived_pub == expected else 'NO'}")
