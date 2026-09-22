"""Loads the Zcash Testnet publisher key from a file OUTSIDE this repository.

CORRECTION 2026-09-19: the publisher private key used to be hardcoded in
`publish_attestation.py` (PRIVKEY_HEX), in `scripts/lib/tests/test_zcash_tx.py`
and in `chains/zcash/data/testnet_oracle_poc_2026-09-19.md`. It was removed
from every tracked file and now lives only in the pipeline's `keys/` folder
(same model as `keys/solana-devnet.json`), never in this repo.

It is still readable in git history (commit 40ca1a4). Because ARO1/ARO2
authentication rests only on "the anchoring tx was spent from the publisher
address", that key must be treated as COMPROMISED: a key file carrying
`"exposed_in_git_history": true` makes `publish_attestation.py send` and
`publish_batch.py send` refuse to broadcast.

ROTATED 2026-09-19 (UTC evening, i.e. 2026-09-20 in Europe/Paris): the current publisher key (PUBKEY_HEX / ADDRESS below) is a
fresh os.urandom key that was never written to any tracked file. Its funds are the
remaining ARO2 change of the exposed key, swept to it in one Testnet transaction
(no faucet). The exposed key's public values stay below as LEGACY_EXPOSED_* only
so the historic ARO1 / first-ARO2 transactions remain identifiable.

Key file format (JSON, chmod 600):
  {"network": "zcash-testnet", "address": "tm...", "pubkey_compressed_hex": "...",
   "privkey_hex": "<64 hex, never printed>", "exposed_in_git_history": bool, ...}

Location: $ARO_ZCASH_TESTNET_KEY_FILE, else DEFAULT_KEY_FILE below.
"""
import json
import os

import secp256k1 as ec
import zcash_read as zr

ENV_VAR = "ARO_ZCASH_TESTNET_KEY_FILE"
DEFAULT_KEY_FILE = os.path.expanduser(
    "~/Desktop/workspace/authority-risk-oracle-multichain-pipeline/keys/zcash-testnet.json")

# Public values only (safe to commit): the CURRENT publisher, rotated 2026-09-19 (UTC).
PUBKEY_HEX = "02e6a829db766cdf6488cfae3cd9588b1871317b625becdd5381c356923004a8cd"
ADDRESS = "tmCj66nwJY8xgNj3jwEyUMhLGmZzbHYiHY8"

# The previous publisher, whose private half was committed in clear (40ca1a4):
# it anchored ARO1 (f0780a09...) and the first ARO2 (18791a4c...). Kept as public
# values only, to identify those two historic transactions. load() REFUSES a key file
# holding this key by identity, whatever its exposed_in_git_history flag says or omits,
# unless the caller passes allow_legacy_exposed=True (only the tests that rebuild that
# key's historic transactions do).
LEGACY_EXPOSED_PUBKEY_HEX = "0388e6af60fe4d0fe63248e3953165f6f13dd57f733ed7283d68f12f2acfb3b41f"
LEGACY_EXPOSED_ADDRESS = "tmDvDRYD7meGJXFoeTqtjFcrNF5378ZzaBo"


class PublisherKeyMissing(FileNotFoundError):
    pass


class PublisherKeyInvalid(ValueError):
    pass


class PublisherKeyExposed(ValueError):
    """The key file holds the legacy key whose private half is public in git history."""


def key_file_path() -> str:
    return os.environ.get(ENV_VAR) or DEFAULT_KEY_FILE


def key_available() -> bool:
    return os.path.isfile(key_file_path())


def load(allow_legacy_exposed=False):
    """Returns (priv_int, pubkey_compressed_bytes, address, exposed_bool).

    Raises PublisherKeyMissing with an explicit message if the file is absent,
    PublisherKeyInvalid if it is malformed or does not match its own address,
    PublisherKeyExposed if it holds the legacy exposed key (by identity, not by the
    file's flag) and allow_legacy_exposed is not True.
    Never includes the private key in any message.
    """
    path = key_file_path()
    if not os.path.isfile(path):
        raise PublisherKeyMissing(
            f"Zcash Testnet publisher key file not found: {path}. The key is kept OUT of "
            f"the repository on purpose. Point {ENV_VAR} at a JSON key file "
            "(fields: privkey_hex, pubkey_compressed_hex, address) or create "
            "keys/zcash-testnet.json in the pipeline folder (chmod 600).")
    with open(path) as f:
        d = json.load(f)
    try:
        priv = int(d["privkey_hex"], 16)
        pub_hex = d["pubkey_compressed_hex"]
        address = d["address"]
    except (KeyError, ValueError, TypeError) as e:
        # `from None`: the original ValueError's message quotes the offending value, which could be a
        # (malformed) private key; it must not survive in the chained traceback.
        raise PublisherKeyInvalid(f"malformed key file {path}: missing/invalid field ({type(e).__name__})") from None
    pub = ec.privkey_to_pubkey(priv)
    if pub.hex() != pub_hex:
        raise PublisherKeyInvalid(f"key file {path}: privkey does not match pubkey_compressed_hex")
    if zr.transparent_output_script(address) != "76a914" + ec.hash160(pub).hex() + "88ac":
        raise PublisherKeyInvalid(f"key file {path}: address does not match the public key")
    if pub.hex() == LEGACY_EXPOSED_PUBKEY_HEX and not allow_legacy_exposed:
        raise PublisherKeyExposed(
            f"key file {path} holds the legacy key whose private half is public in git history "
            "(commit 40ca1a4): refused by identity, whatever its exposed_in_git_history flag says")
    return priv, pub, address, bool(d.get("exposed_in_git_history", False))
