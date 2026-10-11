#!/usr/bin/env python3
"""
Solana score-push script, parameterized on the model of
`chains/ethereum-l1/deploy/update_scores_ethereum_l1.py` for this
ecosystem's own read/write split:

  READ  -- Solana Mainnet Beta: where the 13 scored targets (Jupiter
           Aggregator v6, Kamino Lend, Solend DAO governance, Drift
           Protocol, Raydium, marginfi, Kamino Liquidity, Jupiter Perps,
           Jupiter Lend, PumpSwap, Meteora DAMM v2, Orca Whirlpool,
           Marinade Liquid Staking) actually live and are re-derived live
           from, via chains/solana/scorers.py::score_all().
  WRITE -- Solana Devnet: where solana_authority_oracle (chains/solana/
           program/programs/solana-authority-oracle) will be deployed in
           the next phase (deploy_testnet). No program exists on devnet
           yet this phase (scoring_build) -- this script's normal,
           non-dry-run path is intentionally not runnable until
           ORACLE_PROGRAM_ID exists (mirrors the Ethereum L1 script's own
           "ORACLE_ADDRESS doesn't exist yet" convention exactly).

--dry-run is the only mode this phase actually exercises: it re-derives
every score from live mainnet state and builds the exact Anchor
`update_score` instruction DATA bytes (8-byte discriminator +
Borsh-serialized args) that would be sent for each target, WITHOUT opening
a connection to any write RPC, without needing a devnet keypair, and
without sending anything -- proving the encoding path works before a real
program ID exists to send it to. This intentionally does not depend on
solana-py/anchorpy (not installed, no network access assumed at
push-script-write time) -- the discriminator and Borsh layout are computed
by hand from Anchor's own well-documented convention
(sha256("global:<ix_name>")[0:8], little-endian ints, fixed-size arrays
verbatim), same "no external deps beyond stdlib" discipline already used by
chains/solana/scripts/sol_read.py, which this script re-uses to compute
`methodology_hash` bytes identically to how the EVM script computes its
Solidity-side keccak of METHODOLOGY_VERSION.

Usage:
    python3 chains/solana/deploy/update_scores_solana.py --dry-run

Non-dry-run (deploy_testnet phase; implemented 2026-09-19, rehearsed on a
localhost solana-test-validator -- see deploy/README.md; deployed and pushed
for real on Devnet 2026-09-20, see deploy_record_solana.txt):
    READ_RPC_URL=https://api.mainnet-beta.solana.com \
    ORACLE_RPC_URL=https://api.devnet.solana.com \
    ORACLE_PROGRAM_ID=<base58, from an actual devnet deploy> \
    KEYPAIR_FILE=<path to keys/authority-risk-oracle/solana-devnet/.env, a raw
    solana-keygen-style JSON uint8[64] array despite the .env name, never
    printed/committed -- confirmed live 2026-09-24, see
    scripts/repush_all_oracles.sh and chains/solana/deploy/check_keypair_matches.py> \
    python3 chains/solana/deploy/update_scores_solana.py --out pushed.json

The write path lives in push_live() + deploy/solana_tx.py (stdlib +
PyNaCl, hand-built legacy transactions). It refuses any oracle RPC whose
genesis hash is Mainnet Beta's.
"""
import argparse
import hashlib
import json
import os
import struct
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "chains", "solana"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# appended, not inserted first: scripts/lib has its own scorers.py, which must not shadow chains/solana/scorers.py
sys.path.append(os.path.join(REPO_ROOT, "scripts", "lib"))

from scorers import score_all  # noqa: E402
from oracle_keys import assert_unique_oracle_keys  # noqa: E402
import push_guard  # noqa: E402  (scripts/lib; held scores and a lost target are refused as on the EVM oracles)

DEFAULT_READ_RPC_URL = "https://api.mainnet-beta.solana.com"  # Solana Mainnet Beta, READ ONLY
DEFAULT_ORACLE_RPC_URL = "https://api.devnet.solana.com"  # Solana Devnet, the only network this pipeline may write to
METHODOLOGY_VERSION = "authority-risk-oracle-solana-v1"

# methodologyHash tied to the scoring code since 2026-09-30 (scripts/lib/methodology.py). Loaded by path, not by
# putting scripts/lib on sys.path, so no chain-local module (e.g. a chain's own `scorers`) can be shadowed.
import importlib.util as _ilu  # noqa: E402
_spec = _ilu.spec_from_file_location("aro_methodology", os.path.join(REPO_ROOT, "scripts", "lib", "methodology.py"))
methodology = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(methodology)

B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def b58decode_pubkey(s: str) -> bytes:
    """Decode a base58 Solana pubkey to its 32 raw bytes. Exact inverse of
    `sol_read.py`'s own `b58()` encoder: each leading '1' char is one
    leading 0x00 byte (standard base58, same convention Bitcoin addresses
    use), the remaining bytes are the big-endian base-58 value, and a
    Solana pubkey is always exactly 32 bytes -- so the non-leading-zero
    portion is padded to `32 - n_leading` rather than guessed."""
    n = 0
    for ch in s:
        n = n * 58 + B58.index(ch)
    n_leading = len(s) - len(s.lstrip("1"))
    return b"\x00" * n_leading + n.to_bytes(32 - n_leading, "big")


def methodology_hash() -> bytes:
    # sha256("<METHODOLOGY_VERSION>:<digest of every scoring file>") since 2026-09-30, see scripts/lib/methodology.py.
    # sha256, not keccak, as this project's Solana-side tooling already standardizes on. A fix of the scorer now
    # changes the published hash, a change of the target's posture does not.
    return methodology.solana_hash(METHODOLOGY_VERSION)


def anchor_discriminator(ix_name: str) -> bytes:
    """Anchor's own documented convention: sha256("global:<instruction
    name>")[0:8]. Verified against this program's own instruction name
    (`update_score`, chains/solana/program/programs/solana-authority-oracle/
    src/lib.rs) -- not guessed."""
    return hashlib.sha256(f"global:{ix_name}".encode()).digest()[:8]


def encode_update_score_ix_data(target_pubkey_b58: str, scored: dict) -> bytes:
    """Borsh-encode `update_score`'s args exactly as the program's `#[program]`
    entrypoint expects them (see lib.rs): target: Pubkey (32 bytes, raw,
    not base58), then 6x u8, then methodology_hash: [u8; 32]. Borsh has no
    length prefix for a fixed-size array or a Pubkey newtype -- both are
    written verbatim, same as every other fixed-size Anchor arg."""
    target_bytes = b58decode_pubkey(target_pubkey_b58)
    assert len(target_bytes) == 32, f"expected 32-byte pubkey, got {len(target_bytes)} for {target_pubkey_b58}"
    payload = struct.pack(
        "<6B",
        scored["adminKeyScore"],
        scored["multisigScore"],
        scored["timelockScore"],
        scored["oracleAuthorityScore"],
        scored["crossExposureScore"],
        scored["compositeScore"],
    )
    return anchor_discriminator("update_score") + target_bytes + payload + methodology_hash()


def review_before_push(scored, tracked_and_published, accepted=(), accepted_missing=(), skip_published_check=False):
    """Refuse a push that would lose a target or move a score without a person looking, as the EVM push scripts do.

    tracked_and_published: (tracked, published) where tracked is the list of base58 targets in the oracle's Registry and
    published is {target: decoded AuthorityScore} for the ones already written, or None when the read failed.
    Raises SystemExit on: a tracked target the scorer did not return (its on-chain score would silently go stale),
    an unreadable published state (unless skip_published_check), or any entry push_guard.review holds."""
    tracked, published = tracked_and_published
    accepted_missing = {a.lower() for a in accepted_missing}
    scored_keys = {e["target"].lower() for e in scored}
    missing = [x for x in tracked if x.lower() not in scored_keys and x.lower() not in accepted_missing]
    if missing:
        raise SystemExit("Push guard: the Registry tracks target(s) the scorer did not return, so their on-chain score would go stale: "
                         + ", ".join(missing) + ". Fix the read, or pass --accept-missing=" + ",".join(missing) + " if they were retired on purpose.")
    if published is None:
        if not skip_published_check:
            raise SystemExit("Push guard: published scores UNREAD; refusing to push. Re-run, or pass --skip-published-check after checking by hand.")
        print("Push guard: published scores UNREAD, --skip-published-check given: the drop check and the lost-target check were not run")
        pub = pub_o = pub_c = None
    else:
        pub = {k.lower(): v["compositeScore"] for k, v in published.items()}
        pub_o = {k.lower(): v["oracleAuthorityScore"] for k, v in published.items()}
        pub_c = {k.lower(): v["crossExposureScore"] for k, v in published.items()}
    held, lines = push_guard.review(scored, pub, accepted, pub_o, pub_c)
    print(f"[push] push guard: {len(held)} entr{'y' if len(held) == 1 else 'ies'} held")
    for l in lines:
        print(l)
    if held:
        raise SystemExit("Push guard: refusing to push. Look at each HELD entry, then re-run with --accept-held="
                         + ",".join(e["target"] for e in held) + " if it is right.")


def read_registry_and_published(oracle_rpc_url, program_id_b58, scored):
    """(tracked, published): the Registry's tracked targets and the decoded score of each scored target already written.
    (tracked, None) when a read failed: the caller must not treat that as 'nothing published'. ([], {}) on a first publish."""
    import solana_tx as stx
    import read_scores_solana as rs
    program_id = stx.b58decode(program_id_b58, 32)
    registry, _ = stx.find_program_address([b"registry"], program_id)
    try:
        rdata, rowner = stx.get_account_data(oracle_rpc_url, stx.b58encode(registry))
        if rdata is None:
            return [], {}
        if rowner != program_id_b58:
            return [], None
        tracked = rs.decode_registry(rdata)["tracked"]
        published = {}
        for e in scored:
            pda, _ = stx.find_program_address([b"score", stx.b58decode(e["target"], 32)], program_id)
            data, owner = stx.get_account_data(oracle_rpc_url, stx.b58encode(pda))
            if data is not None and owner == program_id_b58:
                published[e["target"]] = rs.decode_score(data)
        return tracked, published
    except Exception as ex:  # noqa: BLE001 -- a failed read is never 'nothing published'
        print(f"[push] published scores UNREAD ({type(ex).__name__}: {ex})")
        return [], None


def push_live(args):
    """Real write path (deploy_testnet phase): re-derive every score live
    from Mainnet Beta (READ ONLY), then send `initialize` (only if the
    Registry PDA does not exist yet) and one `update_score` per target to
    the oracle RPC -- Solana Devnet, or a localhost solana-test-validator
    for a rehearsal. Refuses a mainnet oracle RPC outright (genesis-hash
    check, not a URL string match). Never prints the secret key."""
    import solana_tx as stx

    methodology.code_digest("solana")  # pin the code that runs now, before scoring
    methodology.require_committed("solana")  # the published hash must match a commit
    print(methodology.describe("solana", METHODOLOGY_VERSION))
    if not args.program_id or not args.keypair_file:
        print("Non-dry-run needs --program-id/ORACLE_PROGRAM_ID and --keypair-file/KEYPAIR_FILE.", file=sys.stderr)
        sys.exit(1)
    genesis = stx.assert_not_mainnet(args.oracle_rpc_url)
    net = "Solana Devnet" if genesis == stx.DEVNET_GENESIS else f"non-mainnet cluster (genesis {genesis})"
    print(f"[push] oracle RPC {args.oracle_rpc_url} = {net}")

    # Scores are read (Mainnet Beta, read only) and checked for key collisions BEFORE the payer key is read and before any
    # transaction (initialize included) is built.
    print(f"[push] reading live scores from {args.read_rpc_url} (Solana Mainnet Beta, read-only)")
    scored = score_all(args.read_rpc_url)
    print(f"[push] {len(scored)} targets scored live")
    # The oracle keeps one score per address: refuse the whole push if two entries share one (scripts/lib/oracle_keys.py).
    assert_unique_oracle_keys(scored, exact=True, where="(solana push)")
    methodology.assert_unchanged("solana")  # the files must still be the ones pinned before scoring

    sk, payer = stx.load_keypair(args.keypair_file)
    program_id = stx.b58decode(args.program_id, 32)
    system_program = stx.b58decode(stx.SYSTEM_PROGRAM_ID, 32)
    print(f"[push] payer/updater = {stx.b58encode(payer)} (secret key not printed)")

    # Deploy->first-tx race guard: a program is only invocable once the
    # confirmed slot is past its ProgramData 'last deployed slot'.
    ready = stx.wait_program_invocable(args.oracle_rpc_url, args.program_id)
    print(f"[push] program executable, last deployed slot {ready['last_deployed_slot']} "
          f"< confirmed slot {ready['confirmed_slot']} -- invocable")

    review_before_push(scored, read_registry_and_published(args.oracle_rpc_url, args.program_id, scored),
                       accepted=[x for x in (args.accept_held or "").split(",") if x.strip()],
                       accepted_missing=[x for x in (args.accept_missing or "").split(",") if x.strip()],
                       skip_published_check=args.skip_published_check)

    registry, _ = stx.find_program_address([b"registry"], program_id)
    record = {"oracle_rpc_url": args.oracle_rpc_url, "genesis": genesis, "program_id": args.program_id,
              "payer": stx.b58encode(payer), "registry_pda": stx.b58encode(registry), "initialize_tx": None, "scores": [],
              "methodologyHash": methodology_hash().hex(), "methodologyCommit": methodology.head_commit()}

    data, owner = stx.get_account_data(args.oracle_rpc_url, stx.b58encode(registry))
    if data is None:
        ix_data = stx.anchor_discriminator("global", "initialize") + payer + payer
        bh = stx.rpc(args.oracle_rpc_url, "getLatestBlockhash", [{"commitment": "confirmed"}])["value"]["blockhash"]
        raw = stx.build_signed_tx(sk, payer, program_id,
                                  [(registry, False, True), (payer, True, True), (system_program, False, False)],
                                  ix_data, bh)
        record["initialize_tx"] = stx.send_and_confirm(args.oracle_rpc_url, raw)
        print(f"[push] initialize tx = {record['initialize_tx']}  registry PDA = {stx.b58encode(registry)}")
    else:
        if owner != args.program_id:
            sys.exit(f"registry PDA exists but is owned by {owner}, not {args.program_id} -- refusing")
        print(f"[push] registry PDA {stx.b58encode(registry)} already initialized, skipping initialize")

    for entry in scored:
        target = stx.b58decode(entry["target"], 32)
        score_pda, _ = stx.find_program_address([b"score", target], program_id)
        ix_data = encode_update_score_ix_data(entry["target"], entry)
        bh = stx.rpc(args.oracle_rpc_url, "getLatestBlockhash", [{"commitment": "confirmed"}])["value"]["blockhash"]
        raw = stx.build_signed_tx(sk, payer, program_id,
                                  [(registry, False, True), (score_pda, False, True), (payer, True, True),
                                   (system_program, False, False)],
                                  ix_data, bh)
        sig = stx.send_and_confirm(args.oracle_rpc_url, raw)
        rec = {k: entry[k] for k in ("target", "label", "adminKeyScore", "multisigScore", "timelockScore",
                                      "oracleAuthorityScore", "crossExposureScore", "compositeScore")}
        rec.update({"score_pda": stx.b58encode(score_pda), "tx": sig})
        record["scores"].append(rec)
        print(f"[push] {entry['label']!r} composite={entry['compositeScore']} pda={rec['score_pda']} tx={sig}")
    if args.out:
        with open(args.out, "w") as f:
            json.dump(record, f, indent=1)
        print(f"[push] record written to {args.out}")
    print(f"[push] {len(record['scores'])}/{len(scored)} update_score transactions confirmed")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--read-rpc-url", default=os.environ.get("READ_RPC_URL", DEFAULT_READ_RPC_URL))
    ap.add_argument("--oracle-rpc-url", default=os.environ.get("ORACLE_RPC_URL", DEFAULT_ORACLE_RPC_URL))
    ap.add_argument("--program-id", default=os.environ.get("ORACLE_PROGRAM_ID"))
    ap.add_argument("--keypair-file", default=os.environ.get("KEYPAIR_FILE"))
    ap.add_argument("--accept-held", default="", help="comma-separated base58 targets the push guard holds that a person accepted")
    ap.add_argument("--accept-missing", default="", help="comma-separated base58 targets the Registry tracks that were retired on purpose")
    ap.add_argument("--skip-published-check", action="store_true", help="push although the published scores could not be read (after checking by hand)")
    ap.add_argument("--out", help="write a JSON record of every pushed score + tx signature here")
    args = ap.parse_args()

    if not args.dry_run:
        push_live(args)
        return

    print(f"[dry-run] reading live scores from {args.read_rpc_url} (Solana Mainnet Beta, read-only)")
    scored = score_all(args.read_rpc_url)
    print(f"[dry-run] {len(scored)} targets scored live, encoding update_score instruction data for each\n")
    # The oracle keeps one score per address: refuse the whole push if two entries share one (scripts/lib/oracle_keys.py).
    assert_unique_oracle_keys(scored, exact=True, where="(solana dry-run)")

    meth_hash = methodology_hash()
    print(f"methodology_hash = {meth_hash.hex()} (sha256(\"{METHODOLOGY_VERSION}:<code digest>\"))")
    print(methodology.describe("solana", METHODOLOGY_VERSION) + "\n")

    for entry in scored:
        data = encode_update_score_ix_data(entry["target"], entry)
        print(f"target={entry['target']}  label={entry['label']!r}")
        print(
            f"  composite={entry['compositeScore']} adminKey={entry['adminKeyScore']} "
            f"multisig={entry['multisigScore']} timelock={entry['timelockScore']} "
            f"oracleAuthority={entry['oracleAuthorityScore']} crossExposure={entry['crossExposureScore']}"
        )
        print(f"  update_score ix data ({len(data)} bytes) = {data.hex()}")
        assert len(data) == 8 + 32 + 6 + 32, f"unexpected ix data length {len(data)}"
    print(f"\n[dry-run] {len(scored)}/{len(scored)} instructions encoded, 0 bytes sent, no RPC write connection opened, no keypair read.")


if __name__ == "__main__":
    main()
