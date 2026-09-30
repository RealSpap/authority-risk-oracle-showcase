#!/usr/bin/env python3
"""
Independent read-back of solana_authority_oracle score accounts.

Does NOT reuse anything the push run returned (no signatures, no PDA list
from the push record): it re-derives every target's score LIVE from Solana
Mainnet Beta (read-only) via chains/solana/scorers.py::score_all(),
re-derives each target's `score` PDA from the program id, fetches the
account by a NEW getAccountInfo call on the oracle RPC, checks the account
owner and Anchor discriminator, decodes the Borsh layout of
`AuthorityScore` (see lib.rs), and asserts every on-chain field equals the
current scorer output. Also decodes the Registry PDA and checks every
target is tracked there.

Usage:
    python3 chains/solana/deploy/read_scores_solana.py \
        --oracle-rpc-url https://api.devnet.solana.com \
        --program-id <base58>

Exit code 0 only if every target matches.
"""
import argparse
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "chains", "solana"))
sys.path.insert(0, HERE)

import solana_tx as stx  # noqa: E402
from scorers import score_all  # noqa: E402

METHODOLOGY_VERSION = "authority-risk-oracle-solana-v1"

# Same methodologyHash rule as the push (scripts/lib/methodology.py), loaded by path so nothing on sys.path is shadowed.
import importlib.util as _ilu  # noqa: E402
_spec = _ilu.spec_from_file_location("aro_methodology", os.path.join(REPO_ROOT, "scripts", "lib", "methodology.py"))
methodology = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(methodology)
FIELDS = ("adminKeyScore", "multisigScore", "timelockScore", "oracleAuthorityScore",
          "crossExposureScore", "compositeScore")


def decode_score(data: bytes) -> dict:
    # discriminator(8) target(32) 6*u8 last_updated(i64) methodology_hash(32) bump(1)
    if len(data) != 8 + 32 + 6 + 8 + 32 + 1:
        raise ValueError(f"unexpected AuthorityScore length {len(data)}")
    if data[:8] != stx.anchor_discriminator("account", "AuthorityScore"):
        raise ValueError("account discriminator is not AuthorityScore")
    out = {"target": stx.b58encode(data[8:40])}
    for i, f in enumerate(FIELDS):
        out[f] = data[40 + i]
    out["lastUpdated"] = struct.unpack_from("<q", data, 46)[0]
    out["methodologyHash"] = data[54:86].hex()
    out["bump"] = data[86]
    return out


def decode_registry(data: bytes) -> dict:
    if data[:8] != stx.anchor_discriminator("account", "Registry"):
        raise ValueError("account discriminator is not Registry")
    admin = stx.b58encode(data[8:40])
    updater = stx.b58encode(data[40:72])
    max_stale = struct.unpack_from("<q", data, 72)[0]
    n = struct.unpack_from("<I", data, 80)[0]
    tracked = [stx.b58encode(data[84 + 32 * i: 116 + 32 * i]) for i in range(n)]
    return {"admin": admin, "updater": updater, "maxStalenessSeconds": max_stale, "tracked": tracked}


def main():
    import hashlib

    ap = argparse.ArgumentParser()
    ap.add_argument("--oracle-rpc-url", required=True)
    ap.add_argument("--program-id", required=True)
    ap.add_argument("--read-rpc-url", default="https://api.mainnet-beta.solana.com")
    args = ap.parse_args()

    program_id = stx.b58decode(args.program_id, 32)
    genesis = stx.rpc(args.oracle_rpc_url, "getGenesisHash")
    print(f"oracle RPC {args.oracle_rpc_url} genesis={genesis}")
    prog = stx.rpc(args.oracle_rpc_url, "getAccountInfo", [args.program_id, {"encoding": "base64"}])["value"]
    if prog is None or not prog["executable"]:
        sys.exit(f"program {args.program_id} not found / not executable on {args.oracle_rpc_url}")
    print(f"program {args.program_id} executable=True owner={prog['owner']}")

    registry, _ = stx.find_program_address([b"registry"], program_id)
    rdata, rowner = stx.get_account_data(args.oracle_rpc_url, stx.b58encode(registry))
    if rdata is None or rowner != args.program_id:
        sys.exit(f"registry PDA {stx.b58encode(registry)} missing or wrong owner ({rowner})")
    reg = decode_registry(rdata)
    print(f"registry PDA {stx.b58encode(registry)} admin={reg['admin']} updater={reg['updater']} "
          f"maxStaleness={reg['maxStalenessSeconds']}s tracked={len(reg['tracked'])}")

    expected_hash = methodology.solana_hash(METHODOLOGY_VERSION).hex()  # same rule as the push, scripts/lib/methodology.py
    live = score_all(args.read_rpc_url)
    print(f"{len(live)} targets re-derived live from {args.read_rpc_url} (read-only)")
    mismatches = 0
    for e in live:
        pda, _ = stx.find_program_address([b"score", stx.b58decode(e["target"], 32)], program_id)
        data, owner = stx.get_account_data(args.oracle_rpc_url, stx.b58encode(pda))
        if data is None or owner != args.program_id:
            print(f"MISSING {e['label']!r} pda={stx.b58encode(pda)} owner={owner}")
            mismatches += 1
            continue
        onchain = decode_score(data)
        diffs = [f for f in FIELDS if onchain[f] != e[f]]
        if onchain["target"] != e["target"]:
            diffs.append("target")
        if onchain["methodologyHash"] != expected_hash:
            diffs.append("methodologyHash")
        if e["target"] not in reg["tracked"]:
            diffs.append("not-in-registry")
        status = "OK" if not diffs else "MISMATCH " + ",".join(diffs)
        mismatches += bool(diffs)
        print(f"{status} {e['label']!r} pda={stx.b58encode(pda)} onchain composite={onchain['compositeScore']} "
              f"admin={onchain['adminKeyScore']} multisig={onchain['multisigScore']} timelock={onchain['timelockScore']} "
              f"oracle={onchain['oracleAuthorityScore']} cross={onchain['crossExposureScore']} "
              f"lastUpdated={onchain['lastUpdated']} | scorer composite={e['compositeScore']}")
    if mismatches:
        sys.exit(f"{mismatches} target(s) do not match")
    print(f"ALL {len(live)} ON-CHAIN SCORES == CURRENT SCORER OUTPUT")


if __name__ == "__main__":
    main()
