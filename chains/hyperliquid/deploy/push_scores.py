#!/usr/bin/env python3
"""
Hyperliquid (HyperEVM sub-layer) score pusher -- modeled directly on
`chains/arbitrum-ecosystem/deploy/push_scores.py` and
`chains/base-ecosystem/deploy/push_scores.py` (same shape: re-derive every
tracked target's score live, then push via `AuthorityRiskOracle.
updateScores()`), adapted for Hyperliquid's own read pattern.

One real difference from the Arbitrum/Base siblings: `chains/hyperliquid/
scorers.py::score_all()` takes NO RPC argument (`score_all(_url_unused=
None)`) -- Hyperliquid's reads are fixed official endpoints (the HyperCore
info API, the HyperEVM RPC, the public Arbitrum One RPC for the legacy
bridge, HyperLend's own archive RPC), not one caller-supplied chain, so
there is no single "READ_RPC_URL chain-id guard" to apply the way the
EVM-only siblings do. This script's own dry-run reconfirms `eth_chainId`
on the HyperEVM RPC directly instead (see `main()` below).

**Scope note, HyperCore vs HyperEVM**: per `../METHODOLOGY.md` section 1,
"smart contract admin key" only exists on HyperEVM -- HyperCore (the
native exchange/validator engine) has NO smart-contract deployment concept
at all, so there is no separate "native HyperCore program" this script (or
any Solidity contract) could ever target the way an Anchor program targets
Solana. What CAN be deployed, and is what this deploy/ folder targets, is
`src/AuthorityRiskOracle.sol` reused unmodified on HyperEVM -- the SAME
contract every other EVM ecosystem in this repo already deploys per-chain,
storing scores for HyperCore-native targets (HIP-3 dexes, the L1, Unit
treasuries, HLP) exactly as it already stores scores for Arbitrum/Base
mainnet targets today: the oracle contract's chain and the scored targets'
chain are independent by design throughout this whole repo, not a new
pattern invented here.

Usage (--dry-run, this phase -- read-only, no transaction, no PRIVATE_KEY
needed):
    python3 chains/hyperliquid/deploy/push_scores.py --dry-run

Usage (real send, future deploy_testnet phase, once the oracle is deployed
and the key is funded):
    ORACLE_RPC_URL=https://rpc.hyperliquid-testnet.xyz/evm \
    ORACLE_ADDRESS=0x... \
    PRIVATE_KEY=0x... \
    python3 chains/hyperliquid/deploy/push_scores.py

PRIVATE_KEY is the raw hex value, not a file path. The actual value lives in a JSON file named by
work/ecosystems.json's own "key_file" field (a "private_key" field inside it, despite the file itself
being named ".env" -- confirmed live 2026-09-24, see scripts/repush_all_oracles.sh::read_key for the
exact extraction pattern):
    PRIVATE_KEY=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["private_key"])' <key_file>) \
    ...rest of the command above...

--dry-run ALSO differs from the root script's --dry-run in one respect: it
goes one step further and actually ABI-ENCODES the updateScores() calldata
(using the real ORACLE_ABI below) and prints its hex, so a re-run of this
exact script is enough to prove the encoding step works end to end -- not
just that the Python-side scoring dicts look right. No transaction is
built, signed, or sent; ORACLE_RPC_URL/ORACLE_ADDRESS/PRIVATE_KEY are not
read at all in --dry-run mode.

ADDED 2026-09-22 (backlog item, "aucune correction ciblee n'est possible,
c'est tout ou rien"): --targets/--oracle, so a correction to a handful of
entries doesn't have to resend all 15 (or however many are tracked) --
every unrelated target keeps whatever lastUpdated/score it already has
on-chain, rather than being needlessly re-stamped with "now" alongside the
targets actually being corrected.

    # push ONLY these two oracle keys (addresses AFTER HIP-3-dex-derived-key
    # resolution -- what's actually stored on-chain, see resolve_oracle_keys()
    # below), everything else on the oracle is left untouched:
    ORACLE_RPC_URL=... ORACLE_ADDRESS=0x... PRIVATE_KEY=0x... \
    python3 chains/hyperliquid/deploy/push_scores.py \
        --targets 0xKinetiqAddr,0xOtherAddr

    # --oracle overrides ORACLE_ADDRESS from the CLI instead of the env var
    # (ORACLE_RPC_URL/PRIVATE_KEY are still read from the environment,
    # matching every other ecosystem's push script -- only the address,
    # the part that actually varies between a targeted correction and a
    # fresh full push, gets a CLI shortcut):
    ORACLE_RPC_URL=... PRIVATE_KEY=0x... \
    python3 chains/hyperliquid/deploy/push_scores.py --oracle 0x...

Omitting --targets keeps the exact original all-or-nothing behaviour: every
tracked target is re-scored and pushed, as before this flag existed. Every
OTHER shape of --targets refuses loudly (SystemExit), immediately after
argument parsing and well under a second, before any live network/scoring
work: given but empty ("", ",", " "), malformed (bad length/hex/checksum),
or well-formed but matching no currently-scored oracle key -- same "never a
silent overwrite" convention resolve_oracle_keys() already uses for key
collisions. --oracle refuses the same way, on the same schedule.
"""
import argparse
import os
import sys
import time

from web3 import Web3

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts", "lib"))
sys.path.insert(0, os.path.join(REPO_ROOT, "chains", "hyperliquid"))

from web3_utils import get_w3  # noqa: E402
from scorers import score_all  # noqa: E402

HYPEREVM_MAINNET_CHAIN_ID = 999   # 0x3e7, re-confirmed live this pass via eth_chainId (see README.md)
HYPEREVM_TESTNET_CHAIN_ID = 998   # 0x3e6, re-confirmed live this pass via eth_chainId (see README.md) -- NOT guessed

ORACLE_ABI = [
    {
        "name": "updateScores",
        "type": "function",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "targets", "type": "address[]"},
            {
                "name": "scores",
                "type": "tuple[]",
                "components": [
                    {"name": "adminKeyScore", "type": "uint8"},
                    {"name": "multisigScore", "type": "uint8"},
                    {"name": "timelockScore", "type": "uint8"},
                    {"name": "oracleAuthorityScore", "type": "uint8"},
                    {"name": "crossExposureScore", "type": "uint8"},
                    {"name": "compositeScore", "type": "uint8"},
                    {"name": "lastUpdated", "type": "uint64"},
                    {"name": "methodologyHash", "type": "bytes32"},
                ],
            },
        ],
        "outputs": [],
    }
]

METHODOLOGY_VERSION = "authority-risk-oracle-hyperliquid-v1"


def methodology_hash() -> bytes:
    # keccak256, matching Solidity's keccak256(bytes) -- same convention as
    # every other ecosystem's push_scores.py, not sha256.
    return Web3.keccak(text=METHODOLOGY_VERSION)


HIP3_DEX_LABEL_PREFIX = "HIP-3 dex "


def hip3_dex_derived_key(dex_name: str) -> str:
    """METHODOLOGY.md 4.7 amendment (2026-09-19): same construction as the L1's
    own key (last 20 bytes of a keccak256 of a namespaced string, which no key
    controls), applied to a HIP-3 dex whose deployer address collides with a
    separately-scored HyperEVM contract at the SAME address."""
    return Web3.to_checksum_address(Web3.keccak(text=f"hyperliquid:hip3-dex:{dex_name}")[-20:])


def resolve_oracle_keys(scored):
    """Assign each scored entry the address it is stored under in the oracle.

    FOUND 2026-09-19 (deploy_testnet rehearsal): the oracle is keyed by
    `address` only (`_scores[target] = score`), and two pairs of tracked
    targets share one address -- HIP-3 dex `mkts` (HyperCore-native deployer)
    and Kinetiq's HIP3StakingManager (HyperEVM proxy) both at 0x71f0...29ec,
    HIP-3 dex `para` and para's StakingVault both at 0x8888...6ed3. Pushed
    as-is, `updateScores()` silently overwrites the first entry of each pair
    with the second: 15 scores in, 13 slots on-chain, mkts' 9 and para's 5
    unreadable. Resolution: the HyperEVM contract keeps its real address (an
    EVM consumer calling getScore(contract) gets the contract's own score);
    the colliding HIP-3 dex moves to a derived key (`hip3_dex_derived_key`).
    Any collision this rule cannot resolve is a hard failure, never a silent
    overwrite. Scores themselves are not touched."""
    by_addr = {}
    for entry in scored:
        by_addr.setdefault(entry["target"].lower(), []).append(entry)
    for group in by_addr.values():
        if len(group) < 2:
            continue
        for entry in group:
            label = entry.get("label", "")
            if label.startswith(HIP3_DEX_LABEL_PREFIX):
                name = label[len(HIP3_DEX_LABEL_PREFIX):].strip()
                entry["oracleKey"] = hip3_dex_derived_key(name)
                entry.setdefault("notes", []).append(
                    f"oracle key = {entry['oracleKey']} (derived, METHODOLOGY.md 4.7 amendment 2026-09-19) because deployer "
                    f"{entry['target']} is also the address of a separately-scored HyperEVM contract"
                )
    keys = [Web3.to_checksum_address(e.get("oracleKey", e["target"])) for e in scored]
    dupes = sorted({k for k in keys if keys.count(k) > 1})
    if dupes:
        raise SystemExit(f"REFUSING: oracle key collision(s) left unresolved, a push would silently overwrite scores: {dupes}")
    return keys


def build_targets_and_tuples(scored, now, meth_hash):
    keys = resolve_oracle_keys(scored)
    targets = []
    tuples = []
    for key, entry in zip(keys, scored):
        targets.append(key)
        tuples.append(
            (
                entry["adminKeyScore"],
                entry["multisigScore"],
                entry["timelockScore"],
                entry["oracleAuthorityScore"],
                entry["crossExposureScore"],
                entry["compositeScore"],
                now,
                meth_hash,
            )
        )
    return targets, tuples


def parse_targets_csv(targets_csv):
    """None -> None (--targets omitted: the original all-or-nothing push, unchanged). Otherwise the
    deduplicated, checksummed, REQUEST-ORDER-preserved address list (never an alphabetical re-sort,
    so the printed review lines before signing follow what the operator typed, not a re-shuffled
    one). Pure syntax validation -- no dependency on what's actually tracked/scored, so it can run
    (and does, see main()) BEFORE any live work, unlike the "does this match a real oracle key"
    check in filter_by_targets() below, which genuinely needs the live scored set.

    FIXED 2026-09-22 (review of commit 210aed6, BLOCKING, then review of the fix commit 838f5c2,
    reservation "ASYMMETRIC VALIDATION"): the original check was `if not targets_csv`, which treated
    `--targets ""` (or "," / " " / ",,") the SAME as --targets being omitted entirely -- silently
    pushed ALL 15 targets with no disclosure, exactly the failure mode --targets exists to prevent
    (a wrapper interpolating an empty/unset variable). First fix moved the check into
    filter_by_targets(), which is only called AFTER score_all()'s ~100s live re-derivation -- so
    `--targets ""` refused, but only after paying the full live cost, and the fix's own commit
    message wrongly claimed (copy-pasted from --oracle's genuinely-fast refusal) that it was fast.
    This split closes both: the syntax-only part (this function) now runs immediately after argument
    parsing, symmetric with validate_oracle_override(), so a typo/empty value is caught before any
    network call, and the commit message's claim is actually true this time."""
    if targets_csv is None:
        return None
    raw = [a.strip() for a in targets_csv.split(",") if a.strip()]
    if not raw:
        raise SystemExit(
            f"REFUSING --targets: given but empty ({targets_csv!r}) -- omit --targets entirely for "
            f"the original all-or-nothing push, or provide at least one address"
        )
    try:
        seen, wanted = set(), []
        for a in raw:
            w = Web3.to_checksum_address(a)
            if w not in seen:
                seen.add(w)
                wanted.append(w)
    except ValueError as e:
        raise SystemExit(f"REFUSING --targets: {targets_csv!r} contains a malformed address ({e})")
    return wanted


def filter_by_targets(targets, tuples, scored, wanted):
    """None -> unchanged (default: every tracked target). `wanted` is the ALREADY-VALIDATED address
    list from parse_targets_csv() above (or None), matched here against the oracle keys ACTUALLY
    being pushed (post HIP-3-dex-derived-key rewrite, resolved by build_targets_and_tuples()/
    resolve_oracle_keys() just before this is called) -- what --targets means is "these on-chain
    slots", not necessarily the raw scorer target address. Any requested address matching nothing in
    `targets` REFUSES (SystemExit, naming every known key) rather than silently pushing an empty or
    wrong set.

    KNOWN GAP, NOT FIXED (review of commit 210aed6, reservation): requesting the RAW address of a
    HIP-3 dex that collided with another entry and moved to a derived key does NOT error -- it
    silently matches whichever OTHER entry (never a dex) still holds that raw address, with no
    signal that a dex also lives there under a different key. Both of this repo's two known
    collisions (mkts, para) are exactly this shape. An informational hint on the SUCCESSFUL-match
    path (not the refusal path -- a first attempt at this put it in the wrong branch and was
    reverted, see commit history) would close it; deferred rather than rushed."""
    if wanted is None:
        return targets, tuples, scored
    index = {t: i for i, t in enumerate(targets)}
    missing = [w for w in wanted if w not in index]
    if missing:
        raise SystemExit(
            f"REFUSING --targets: {missing} match no currently tracked/scored oracle key "
            f"(known keys: {sorted(targets)}) -- typo, or not tracked right now"
        )
    keep = [index[w] for w in wanted]
    return [targets[i] for i in keep], [tuples[i] for i in keep], [scored[i] for i in keep]


def parse_args(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true",
                    help="encode calldata only, never read ORACLE_RPC_URL/ORACLE_ADDRESS/PRIVATE_KEY, never send")
    p.add_argument("--targets", default=None,
                    help="comma-separated oracle-key addresses to push (targeted correction); "
                         "default: every tracked target (original all-or-nothing behaviour)")
    p.add_argument("--oracle", default=None,
                    help="override ORACLE_ADDRESS from the CLI instead of the environment "
                         "(ORACLE_RPC_URL/PRIVATE_KEY are still read from the environment)")
    return p.parse_args(argv)


def validate_oracle_override(raw):
    """None -> None (no override: oracle_address falls back to ORACLE_ADDRESS from the environment,
    unchanged from before --oracle existed). FIXED 2026-09-22 (review of commit 210aed6,
    reservation): checksum-validated HERE, immediately after argument parsing and before any live
    scoring/network work, instead of only failing (with a raw, unrelated-looking web3 ValueError)
    at the point the transaction is built -- several minutes and a full live re-derivation later.
    Also closes the same "given but empty must not silently behave like absent" gap --targets was
    fixed for: `--oracle ""` used to fall straight through to the environment fallback."""
    if raw is None:
        return None
    if not raw.strip():
        raise SystemExit("REFUSING --oracle: given but empty -- omit --oracle entirely to use ORACLE_ADDRESS from the environment")
    try:
        return Web3.to_checksum_address(raw.strip())
    except ValueError as e:
        raise SystemExit(f"REFUSING --oracle: {raw!r} is not a valid address ({e})")


def main(argv=None):
    args = parse_args(argv)
    dry_run = args.dry_run
    # Both --oracle and --targets are syntax-validated HERE, immediately after argument parsing and
    # before any live network/scoring work -- an empty/malformed value refuses in well under a
    # second, not after paying for a ~100s live re-derivation across 4 external APIs first (review
    # of commit 838f5c2, reservation "ASYMMETRIC VALIDATION").
    oracle_override = validate_oracle_override(args.oracle)
    wanted_targets = parse_targets_csv(args.targets)

    evm_rpc = "https://rpc.hyperliquid.xyz/evm"
    evm_w3 = get_w3(evm_rpc)
    if not evm_w3.is_connected():
        raise SystemExit(f"Could not connect to HyperEVM mainnet RPC: {evm_rpc}")
    if evm_w3.eth.chain_id != HYPEREVM_MAINNET_CHAIN_ID:
        raise SystemExit(
            f"HyperEVM RPC resolved to chain ID {evm_w3.eth.chain_id}, expected "
            f"{HYPEREVM_MAINNET_CHAIN_ID} (HyperEVM mainnet) -- refusing to score against the wrong chain."
        )
    print(f"HyperEVM mainnet confirmed live: chain ID {evm_w3.eth.chain_id}, block {evm_w3.eth.block_number}")
    print("Re-deriving every tracked target's score from live chain/API state "
          "(HyperCore info API + HyperEVM RPC + Arbitrum One RPC for the legacy bridge + HyperLend archive RPC)...\n")

    scored = score_all()  # no RPC argument -- see this module's own docstring
    now = int(time.time())
    meth_hash = methodology_hash()

    targets, tuples = build_targets_and_tuples(scored, now, meth_hash)
    # --targets is applied AFTER the full resolve_oracle_keys()/dupe-check above, on purpose: a real
    # collision among the FULL tracked set must still be caught even when this run only intends to
    # push a subset -- narrowing the push must never narrow the safety check.
    targets, tuples, scored = filter_by_targets(targets, tuples, scored, wanted_targets)
    if wanted_targets is not None:
        print(f"--targets set: pushing only {len(targets)} of the currently tracked oracle keys "
              f"(every other entry on the oracle is left untouched).\n")

    for key, entry in zip(targets, scored):
        print(f"{entry['label']} ({entry['target']}, oracle key {key}): composite={entry['compositeScore']}/100, "
              f"l1Capped={entry.get('l1CappedComposite')}, oracle={entry['oracleAuthorityScore']}/100, "
              f"crossExposure={entry['crossExposureScore']}/100")

    oracle_iface = Web3().eth.contract(abi=ORACLE_ABI)
    calldata = oracle_iface.encode_abi("updateScores", args=[targets, tuples])

    print(f"\nEncoded updateScores() calldata ({len(calldata) // 2 - 1} bytes) for {len(targets)} targets: {calldata[:66]}...")
    print(f"methodologyHash = 0x{meth_hash.hex()}")
    print(f"Target chain for this calldata: HyperEVM Testnet, chain ID {HYPEREVM_TESTNET_CHAIN_ID}")

    if dry_run:
        print("\n--dry-run set: calldata encoded above, but NOT sending a transaction, NOT reading ORACLE_RPC_URL/ORACLE_ADDRESS/PRIVATE_KEY.")
        return

    oracle_rpc_url = os.environ["ORACLE_RPC_URL"]
    oracle_address = oracle_override or os.environ["ORACLE_ADDRESS"]
    oracle_w3 = get_w3(oracle_rpc_url)
    if not oracle_w3.is_connected():
        raise SystemExit(f"Could not connect to oracle RPC: {oracle_rpc_url}")
    if oracle_w3.eth.chain_id != HYPEREVM_TESTNET_CHAIN_ID:
        raise SystemExit(
            f"ORACLE_RPC_URL resolved to chain ID {oracle_w3.eth.chain_id}, expected "
            f"{HYPEREVM_TESTNET_CHAIN_ID} (HyperEVM Testnet) -- refusing to send to the wrong chain, "
            f"and NEVER to HyperEVM mainnet (999) regardless of what this env var is set to."
        )
    if oracle_w3.eth.chain_id == HYPEREVM_MAINNET_CHAIN_ID:
        raise SystemExit("REFUSING: ORACLE_RPC_URL resolved to HyperEVM MAINNET (999). This pipeline never writes to mainnet, for any ecosystem.")
    print(f"\nPushing to oracle on chain ID: {oracle_w3.eth.chain_id} (HyperEVM Testnet)")

    private_key = os.environ["PRIVATE_KEY"]
    account = oracle_w3.eth.account.from_key(private_key)
    oracle = oracle_w3.eth.contract(address=Web3.to_checksum_address(oracle_address), abi=ORACLE_ABI)

    tx = oracle.functions.updateScores(targets, tuples).build_transaction(
        {
            "from": account.address,
            "nonce": oracle_w3.eth.get_transaction_count(account.address),
            "gasPrice": oracle_w3.eth.gas_price,
        }
    )
    signed = account.sign_transaction(tx)
    tx_hash = oracle_w3.eth.send_raw_transaction(signed.raw_transaction)
    print(f"Sent updateScores() tx: {tx_hash.hex()}")

    receipt = oracle_w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
    status = "success" if receipt.status == 1 else "FAILED"
    print(f"Confirmed in block {receipt.blockNumber}: {status}")
    if receipt.status != 1:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
