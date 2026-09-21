#!/usr/bin/env python3
"""Read-only reads of Zenrock's own `zrchain` Mainnet (`diamond-1`) -- the
custody chain behind `zenZEC` (native ZEC, wrapped on Solana via a
distributed-MPC/dMPC signer network). Added 2026-09-19, resuming the lead
`data/scouting_candidates_2026-09-18.md` deferred the day before: Zenrock's
hosted docs (`docs.zenrocklabs.io`) and REST/LCD gateway
(`api.diamond.zenrocklabs.io`) both still returned `Payment Required` (HTTP
402) / HTTP 503 on RE-CHECK, 2026-09-19 -- same failure as the day before, not
a stale check. The two community REST mirrors the Cosmos chain-registry
lists (`api.zenrock.nodestake.org`, `zenrock.api.m.stavr.tech`) are
unreachable / 502, also unchanged from 2026-09-18.

**What actually worked this pass, and why it is a primary source, not a
workaround that manufactures data:** Zenrock's own Tendermint/CometBFT RPC
(`rpc.diamond.zenrocklabs.io`, confirmed live to be `diamond-1` = "Zenrock
Mainnet" by Zenrock's own validator-setup README, `zenrocklabs/
zenrock-validators`, and by the Cosmos chain-registry's `zenrock/chain.json`)
DOES answer. CometBFT's `/abci_query` endpoint routes to the exact same
gRPC-gateway Query services the REST/LCD gateway would otherwise translate
HTTP paths into -- this is how the REST gateway works internally, not a
side channel. The request/response message shapes below are read directly
from `github.com/Zenrock-Foundation/zrchain`'s own published `.pb.go`
source (`x/identity/types/keyring.pb.go`, `x/identity/types/query.pb.go`,
`x/treasury/types/query.pb.go`), never guessed, and every field extracted
below was independently cross-checked at least once this pass (see
`data/zenzec_mpc_keyring_2026-09-19.md`): the Solana mint address read from
zrchain's own `x/dct` module params matched, byte for byte, the mint
address this project already independently verified live on Solana Mainnet
RPC on 2026-09-18; the two Zcash-mainnet addresses read from `x/treasury`
Key objects were independently re-derived from their raw public keys using
the exact P2PKH algorithm published in zrchain's own
`x/treasury/types/wallet_zcash.go`, both matching the chain's own reported
address exactly.

**DISCLOSED LIMITATIONS (not smoothed over):**
- SINGLE SOURCE. `rpc.zenrock.nodestake.org` (the chain-registry's second
  listed RPC operator) refused every connection this pass
  (`curl: (7) Failed to connect`). No independent second zrchain full node
  could be reached -- unlike every other read in this project (Zcash's own
  two lightwalletd operators, NEAR's two RPCs), this module's reads rely on
  one node, disclosed rather than presented as having the same guarantee.
- DATED, not live-current. This one reachable node's own `/status` reports
  ITS OWN last ingested block at height 9,534,552 / `2026-08-10T23:19:52Z`,
  with `n_peers: 0` (isolated from the rest of the network -- not proof the
  whole `diamond-1` Mainnet is halted; the Cosmos chain-registry still lists
  it `"status": "live"` -- but no fresher zrchain endpoint could be found to
  confirm today's real chain tip). Every read through this module reflects
  that ~40-day-old snapshot, not "today", until a fresher endpoint is found.
- MUTABLE, unlike a Zcash P2SH script. A `Keyring`'s `parties`/
  `party_threshold` can change (`x/identity`'s own
  `message_add_keyring_party.go` / `message_remove_keyring_party.go` /
  `message_update_keyring.go` exist) -- this is not a cryptographic
  commitment fixed forever the way a P2SH redeem script's `HASH160` is.
- Hand-rolled protobuf reader (varint + length-delimited only), written for
  exactly the message shapes this project needs -- not a full protobuf
  runtime. A future zrchain proto change would need this file re-checked
  against the new `.pb.go` source, the same "dated interpretive fact"
  caveat already applied elsewhere in this project (Zakura's fork status,
  Mayanode's TSS threshold formula).

Usage:
  zenrock_read.py keyring <keyring_addr>          -> x/identity KeyringByAddress
  zenrock_read.py key <key_id>                    -> x/treasury KeyByID (raw pubkey + derived wallets)
  zenrock_read.py dct_asset_params <asset_enum>   -> x/dct QueryParams, one AssetParams entry
"""
import base64
import hashlib
import json
import subprocess
import sys

RPC_HOST = "https://rpc.diamond.zenrocklabs.io"

# Zcash transparent P2PKH version bytes (METHODOLOGY.md section 2 / this
# repo's own zcash_read.py) -- reproduced here (not imported) because this
# is zrchain's own key-to-address algorithm, read from
# `x/treasury/types/wallet_zcash.go` (`zcashMainnetP2PKHVersionBytes`), a
# DIFFERENT source of truth than Zcash's own protocol spec, even though the
# two bytes are identical. Kept as its own citation, not silently merged.
_ZCASH_MAINNET_P2PKH_VERSION = bytes([0x1C, 0xB8])


# --- generic transport / protobuf plumbing ---------------------------------

def _varint(n: int) -> bytes:
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


def _read_varint(b: bytes, i: int):
    shift = v = 0
    while True:
        c = b[i]
        i += 1
        v |= (c & 0x7F) << shift
        shift += 7
        if not c & 0x80:
            return v, i


def _decode_tlv(b: bytes):
    """Generic top-level (field_no, value) walk -- same class of manual
    protobuf decoder as `scripts/zcash_read.py`'s `decode()`, applied to
    zrchain's ABCI query response bytes instead of lightwalletd's gRPC
    framing. wire type 0 (varint) yields an int, wire type 2
    (length-delimited) yields raw bytes for the caller to decode further
    (a nested message, a string, or packed varints) -- every field this
    project actually reads from zrchain is one of these two."""
    i, res = 0, []
    while i < len(b):
        key, i = _read_varint(b, i)
        num, wt = key >> 3, key & 7
        if wt == 0:
            v, i = _read_varint(b, i)
        elif wt == 2:
            ln, i = _read_varint(b, i)
            v = b[i:i + ln]
            i += ln
        else:
            raise ValueError(f"unhandled wire type {wt} at field {num}, byte offset {i}")
        res.append((num, v))
    return res


def _field_bytes(num: int, data: bytes) -> bytes:
    return _varint((num << 3) | 2) + _varint(len(data)) + data


def _field_varint(num: int, val: int) -> bytes:
    return _varint(num << 3) + _varint(val)


def abci_query(path: str, data: bytes = b"", host: str = RPC_HOST, tries: int = 3):
    """One CometBFT `/abci_query` call. `path` must be JSON-double-quoted in
    the query string -- Tendermint's own GET-argument parser treats bare
    punctuation like `/` in an unquoted value as invalid JSON (confirmed
    live 2026-09-19: `error converting http params to arguments: invalid
    character '/' looking for beginning of value` without the quotes).
    Raises on a non-zero ABCI response code or an empty value rather than
    returning something a caller could mistake for a real, present answer
    (this project's "raise rather than silently trust" convention, same as
    `scorers.py`'s NEAR cross-RPC check)."""
    last_err = None
    for _ in range(tries):
        try:
            out = subprocess.run(
                ["curl", "-sk", "--max-time", "20", "-G", f"{host}/abci_query",
                 "--data-urlencode", f'path="{path}"',
                 "--data-urlencode", f"data=0x{data.hex()}"],
                capture_output=True, text=True, check=True,
            ).stdout
            resp = json.loads(out)["result"]["response"]
            break
        except (subprocess.CalledProcessError, json.JSONDecodeError, KeyError) as e:
            last_err = e
    else:
        raise RuntimeError(f"ABCI query {path} failed after {tries} tries: {last_err}")
    if resp.get("code"):
        raise RuntimeError(f"ABCI query {path} returned ABCI code {resp['code']}: {resp.get('log')}")
    if not resp.get("value"):
        raise RuntimeError(f"ABCI query {path} returned an empty value at height {resp.get('height')} "
                            f"-- not found, not a real (possibly zero) answer")
    return base64.b64decode(resp["value"]), int(resp["height"])


# --- x/identity: Keyring (the on-chain dMPC party-threshold object) -------

def get_keyring(keyring_addr: str, host: str = RPC_HOST) -> dict:
    """`zrchain.identity.Query/KeyringByAddress`. Field numbers from
    `x/identity/types/keyring.pb.go`'s `Keyring` struct, read 2026-09-19:
    address=1, creator=2, description=3, admins=4 (repeated), parties=5
    (repeated), party_threshold=6, key_req_fee=7, sig_req_fee=8,
    is_active=9. `QueryKeyringByAddressResponse` wraps it in field 1
    (`x/identity/types/query.pb.go`)."""
    req = _field_bytes(1, keyring_addr.encode())
    raw, height = abci_query("/zrchain.identity.Query/KeyringByAddress", req, host)
    wrapper = dict(_decode_tlv(raw))
    if 1 not in wrapper:
        raise RuntimeError(f"KeyringByAddress({keyring_addr}): response missing field 1 (keyring)")
    admins, parties, out = [], [], {"height": height}
    for num, v in _decode_tlv(wrapper[1]):
        if num == 1:
            out["address"] = v.decode()
        elif num == 2:
            out["creator"] = v.decode()
        elif num == 3:
            out["description"] = v.decode()
        elif num == 4:
            admins.append(v.decode())
        elif num == 5:
            parties.append(v.decode())
        elif num == 6:
            out["party_threshold"] = v
        elif num == 7:
            out["key_req_fee"] = v
        elif num == 8:
            out["sig_req_fee"] = v
        elif num == 9:
            out["is_active"] = bool(v)
    out["admins"], out["parties"] = admins, parties
    # Zero-value proto3 fields (e.g. an inactive `is_active=false`, or a
    # threshold that somehow reads back 0) are omitted on the wire, not sent
    # as an explicit 0/false -- default them rather than leave a KeyError,
    # matching the DCT AssetParams reads below hitting the same convention.
    out.setdefault("party_threshold", 0)
    out.setdefault("is_active", False)
    return out


# --- x/treasury: Key (one dMPC-generated key + its derived wallet addresses) --

def _hash160(b: bytes) -> bytes:
    h = hashlib.new("ripemd160")
    h.update(hashlib.sha256(b).digest())
    return h.digest()


def _b58encode(b: bytes) -> str:
    alphabet = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
    n = int.from_bytes(b, "big")
    res = ""
    while n > 0:
        n, r = divmod(n, 58)
        res = alphabet[r] + res
    n_zeros = len(b) - len(b.lstrip(b"\x00"))
    return alphabet[0] * n_zeros + res


def zcash_mainnet_p2pkh_address(pubkey: bytes) -> str:
    """Independent re-derivation of zrchain's own `ZCashWallet.Address()`
    (`x/treasury/types/wallet_zcash.go`): HASH160 of the compressed secp256k1
    pubkey, Zcash's 2-byte mainnet P2PKH version prefix (`0x1C 0xB8`, unlike
    Bitcoin's 1-byte prefix), Base58Check. Used to CROSS-CHECK the address
    the chain itself reports for a `Key` (see `get_key_by_id` below) rather
    than trusting that reported string outright -- both matched exactly for
    both zenZEC infra keys checked 2026-09-19 (key IDs 387, 388)."""
    payload = _ZCASH_MAINNET_P2PKH_VERSION + _hash160(pubkey)
    checksum = hashlib.sha256(hashlib.sha256(payload).digest()).digest()[:4]
    return _b58encode(payload + checksum)


def get_key_by_id(key_id: int, host: str = RPC_HOST) -> dict:
    """`zrchain.treasury.Query/KeyByID`. Response is `QueryKeyByIDResponse{
    KeyResponse key = 1; repeated WalletResponse wallets = 2 }`
    (`x/treasury/types/query.pb.go` and `key.pb.go`'s `KeyResponse`/
    `WalletResponse` structs -- NOT the same field layout as the internal
    `Key` struct in the same file: this query-response view stringifies
    `type` (field 4) instead of leaving it a raw varint enum). `KeyResponse`
    is id=1, workspace_addr=2, keyring_addr=3, type=4 (string), public_key=5.
    `WalletResponse` is address=1, type=2 (both strings). Read 2026-09-19,
    confirmed against the live wire bytes (field 4 of `key` decodes as a
    length-delimited UTF-8 enum NAME, not a varint, matching `KeyResponse`
    and not `Key`).

    `wallets` is a REPEATED top-level field (2), never collapsed through a
    plain `dict()` of the outer message -- doing that would keep only the
    LAST wallet entry (Zcash Regtest, alphabetically/positionally last) and
    silently discard Mainnet, exactly the kind of quiet wrong-answer this
    project's own discipline exists to avoid. `QueryKeyByIDRequest` is
    `{id=1, wallet_type=2, prefixes=3}` -- only `id` is set here, matching
    the CLI's own default (no wallet-type filter)."""
    req = _field_varint(1, key_id)
    raw, height = abci_query("/zrchain.treasury.Query/KeyByID", req, host)
    top = _decode_tlv(raw)  # LIST, not dict: field 2 (wallets) repeats
    out = {"height": height, "wallets": {}}
    pubkey = None
    key_type = None
    for num, v in top:
        if num == 1:  # KeyResponse
            for knum, kv in _decode_tlv(v):
                if knum == 1:
                    out["id"] = kv
                elif knum == 2:
                    out["workspace_addr"] = kv.decode()
                elif knum == 3:
                    out["keyring_addr"] = kv.decode()
                elif knum == 4:
                    key_type = kv.decode()
                    out["key_type"] = key_type
                elif knum == 5:
                    pubkey = kv
                    out["public_key_hex"] = kv.hex()
        elif num == 2:  # repeated WalletResponse{ address=1, type=2 }
            wf = dict(_decode_tlv(v))
            addr = wf.get(1, b"").decode()
            wtype = wf.get(2, b"").decode()
            out["wallets"][wtype] = addr
    if pubkey is not None and key_type == "KEY_TYPE_BITCOIN_SECP256K1":
        out["zcash_mainnet_address_rederived"] = zcash_mainnet_p2pkh_address(pubkey)
    return out


# --- x/dct: AssetParams (which keyring/keys a wrapped asset actually uses) --

def get_dct_asset_params(asset_enum: int, host: str = RPC_HOST) -> dict:
    """`zrchain.dct.Query/QueryParams` (request is empty), then picks out the
    one `AssetParams` entry matching `asset_enum` (`ASSET_ZENZEC` = 2, per
    `x/dct/types/dct.pb.go`'s `Asset` enum, confirmed live by the entry's own
    own field-1 value). Field numbers from `x/dct/types/params.pb.go`'s
    `AssetParams`/`Solana` structs, read 2026-09-19. Only the fields this
    project's scorer actually uses are decoded; StakerKeyId/EthMinterKeyId/
    UnstakerKeyId/CompleterKeyId are proto3-omitted (unset, i.e. 0) for
    `ASSET_ZENZEC` today -- absence is itself a live-read fact, not a
    parsing gap, and is left absent here too rather than defaulted to a
    misleadingly-specific 0."""
    raw, height = abci_query("/zrchain.dct.Query/QueryParams", b"", host)
    # QueryParamsResponse{ Params params = 1 }; Params{ repeated AssetParams assets = 1 }
    top = dict(_decode_tlv(raw))  # single `params` field, dict() is safe here
    for _, asset_bytes in [(n, v) for n, v in _decode_tlv(top[1]) if n == 1]:
        fields = _decode_tlv(asset_bytes)
        fmap = {}
        for num, v in fields:
            fmap.setdefault(num, []).append(v)
        if 1 not in fmap or fmap[1][0] != asset_enum:
            continue
        out = {"height": height, "asset": fmap[1][0]}
        if 2 in fmap:
            out["deposit_keyring_addr"] = fmap[2][0].decode()
        if 7 in fmap:
            out["rewards_deposit_key_id"] = fmap[7][0]
        if 8 in fmap:  # packed repeated varint (change_address_key_ids)
            blob = fmap[8][0]
            ids, i = [], 0
            while i < len(blob):
                val, i = _read_varint(blob, i)
                ids.append(val)
            out["change_address_key_ids"] = ids
        if 9 in fmap:
            out["proxy_address"] = fmap[9][0].decode()
        if 12 in fmap:
            sol = dict(_decode_tlv(fmap[12][0]))
            if 1 in sol:
                out["solana_signer_key_id"] = sol[1]
            if 5 in sol:
                out["solana_mint_address"] = sol[5].decode()
        return out
    raise RuntimeError(f"asset enum {asset_enum} not found in live x/dct params (height {height})")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "keyring":
        print(json.dumps(get_keyring(sys.argv[2]), indent=2))
    elif cmd == "key":
        print(json.dumps(get_key_by_id(int(sys.argv[2])), indent=2))
    elif cmd == "dct_asset_params":
        print(json.dumps(get_dct_asset_params(int(sys.argv[2])), indent=2))
    else:
        raise SystemExit(__doc__)
