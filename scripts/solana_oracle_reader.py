#!/usr/bin/env python3
"""Read the native Solana authority-oracle program on Devnet without any key, transaction or third-party library.

The Solana counterpart of the `eth_call` reads every EVM oracle gets in `oracle_freshness.py` and
`live_target_counts.py`. Deployed 2026-09-20, see `chains/solana/deploy/README.md`.

Two account types, both Anchor accounts (8-byte discriminator first), layouts from
`chains/solana/program/programs/solana-authority-oracle/src/lib.rs`:

    Registry        disc(8) admin(32) updater(32) max_staleness_seconds(i64) tracked(u32 length + 32 * n) bump
    AuthorityScore  disc(8) target(32) admin multisig timelock oracle cross composite (6 x u8)
                    last_updated(i64) methodology_hash(32) bump                                = 87 bytes

The Registry lists the tracked targets in push order, which is the index order the dashboard uses. Every
score account is found with one `getProgramAccounts` filtered on its exact size, so a target pushed later
shows up here without editing this file.
"""
import base64
import hashlib
import json
import struct
import time
import urllib.request

DEVNET_RPC = "https://api.devnet.solana.com"
PROGRAM_ID = "5VhiTAGLEViGgajhxPbzdWz7WLUAiRy42DY6qi6tYh4W"
# PDA of seeds [b"registry"] under PROGRAM_ID (checked against `solana_tx.find_program_address` in the tests).
REGISTRY_PDA = "CDHtBTibohaCRLtNavArsXfthK9gbwkbmvnujncZBEib"
SCORE_ACCOUNT_SIZE = 87
_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def b58encode(raw: bytes) -> str:
    n = int.from_bytes(raw, "big")
    out = ""
    while n:
        n, r = divmod(n, 58)
        out = _ALPHABET[r] + out
    return "1" * (len(raw) - len(raw.lstrip(b"\x00"))) + out


def anchor_discriminator(name: str) -> bytes:
    return hashlib.sha256(f"account:{name}".encode()).digest()[:8]


def decode_registry(data: bytes) -> dict:
    """Pure. Raises ValueError on anything that is not a Registry account."""
    if len(data) < 8 + 32 + 32 + 8 + 4 or data[:8] != anchor_discriminator("Registry"):
        raise ValueError("not a Registry account")
    (max_staleness,) = struct.unpack_from("<q", data, 72)
    (n,) = struct.unpack_from("<I", data, 80)
    if 84 + 32 * n > len(data):
        raise ValueError(f"Registry claims {n} tracked targets but holds only {len(data)} bytes")
    return {
        "admin": b58encode(data[8:40]),
        "updater": b58encode(data[40:72]),
        "max_staleness": max_staleness,
        "tracked": [b58encode(data[84 + 32 * i: 116 + 32 * i]) for i in range(n)],
    }


def decode_score(data: bytes) -> dict:
    """Pure. Raises ValueError on anything that is not an AuthorityScore account."""
    if len(data) != SCORE_ACCOUNT_SIZE or data[:8] != anchor_discriminator("AuthorityScore"):
        raise ValueError("not an AuthorityScore account")
    admin, multisig, timelock, oracle, cross, composite = data[40:46]
    (last_updated,) = struct.unpack_from("<q", data, 46)
    return {
        "target": b58encode(data[8:40]),
        "adminKeyScore": admin, "multisigScore": multisig, "timelockScore": timelock,
        "oracleAuthorityScore": oracle, "crossExposureScore": cross, "compositeScore": composite,
        "lastUpdated": last_updated, "methodologyHash": "0x" + data[54:86].hex(),
    }


def rpc(url: str, method: str, params: list, tries: int = 4):
    """Plain JSON-RPC over urllib. Public RPCs cut a response now and then, so retry a few times."""
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, body, {"content-type": "application/json"})
            resp = json.load(urllib.request.urlopen(req, timeout=40))
            break
        except Exception:  # noqa: BLE001 -- retried, then re-raised
            if attempt == tries - 1:
                raise
            time.sleep(2 * (attempt + 1))
    if "error" in resp:
        raise RuntimeError(f"{method} RPC error: {resp['error']}")
    return resp["result"]


def read_oracle(rpc_url=DEVNET_RPC, program_id=PROGRAM_ID, registry_pda=REGISTRY_PDA, rpc_fn=rpc):
    """Returns {"admin", "updater", "max_staleness", "tracked": [target...], "scores": [score dict, tracked order]}.
    A tracked target with no score account, or a score account nobody tracks, is an error, never a silent gap."""
    reg = rpc_fn(rpc_url, "getAccountInfo", [registry_pda, {"encoding": "base64"}])["value"]
    if reg is None:
        raise RuntimeError(f"no Registry account at {registry_pda} (program not initialized on this cluster?)")
    if reg["owner"] != program_id:
        raise RuntimeError(f"Registry {registry_pda} is owned by {reg['owner']}, not by {program_id}")
    registry = decode_registry(base64.b64decode(reg["data"][0]))
    accounts = rpc_fn(rpc_url, "getProgramAccounts", [program_id, {"encoding": "base64", "filters": [{"dataSize": SCORE_ACCOUNT_SIZE}]}])
    by_target = {}
    for a in accounts:
        s = decode_score(base64.b64decode(a["account"]["data"][0]))
        by_target[s["target"]] = s
    missing = [t for t in registry["tracked"] if t not in by_target]
    untracked = [t for t in by_target if t not in registry["tracked"]]
    if missing or untracked:
        raise RuntimeError(f"Registry and score accounts disagree: {len(missing)} tracked without a score, {len(untracked)} scored but not tracked")
    registry["scores"] = [by_target[t] for t in registry["tracked"]]
    return registry
