#!/usr/bin/env python3
"""
Recurring off-chain updater: re-derives every tracked target's authority-risk
score directly from the chain (never from a cached value or a UI claim) and
pushes the results on-chain in one updateScores() batch call.

Usage:
    READ_RPC_URL=https://rpc.mainnet.chain.robinhood.com \
    ORACLE_RPC_URL=https://rpc.testnet.chain.robinhood.com/rpc \
    ORACLE_ADDRESS=0x9BF45734D09bC7CA39238e767B2af9AAc62a7f52 \
    PRIVATE_KEY=0x... \
    python3 scripts/update_scores.py [--dry-run] [--skip-slow]

--skip-slow (only allowed together with --dry-run) omits the 4 scorers that
each do a full-chain-history eth_getLogs replay -- the entire reason a full
run has been clocked exceeding 50 minutes. Useful for a fast local
verification pass; never for anything that gets published, since it would
silently omit 4+ tracked targets from a result presented as complete.

READ_RPC_URL and ORACLE_RPC_URL are deliberately separate: every scored target
(the Morpho vault, Uniswap Factory, etc.) is a real contract that only exists
on Robinhood Chain MAINNET, while AuthorityRiskOracle itself is on TESTNET
during this validation phase (see README "Status"). Once the oracle moves to
mainnet, both variables should point at the same RPC -- but keeping them
separate now means this script can't silently read stale/wrong state by
accident if the two ever diverge again later.

Intended to run on a schedule (see .github/workflows/update_scores.yml) so
scores stay fresh instead of going stale between manual runs -- isStale()
on-chain is exactly the guard that makes a missed run visible to consumers
rather than silently serving old data as if it were current.
"""
import json
import os
import sys
import time

from web3 import Web3

sys.path.insert(0, os.path.dirname(__file__))
from lib.alerts import diff_alerts, format_summary, send_telegram_alert  # noqa: E402
from lib import methodology  # noqa: E402
from lib.oracle_keys import assert_unique_oracle_keys  # noqa: E402
from lib.scorers import score_all  # noqa: E402
from lib.web3_utils import get_w3  # noqa: E402

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API_SNAPSHOT_PATH = os.path.join(REPO_ROOT, "api", "scores.json")
# Not a live Pages URL (none is set up) -- the repo path is what's actually
# reachable by anyone with access today, dashboard included.
DASHBOARD_URL = "https://github.com/RealSpap/authority-risk-oracle/tree/main/dashboard"  # moved from RealSpap 2026-09-29

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

METHODOLOGY_VERSION = "authority-risk-oracle-v3"  # v3: PROPOSER_ROLE/CANCELLER_ROLE live re-derivation (fixes a stale batch-4 hardcoded finding), Chainlink oracle-admin Safe + LayerZero V2 infra tracked


def check_completeness(scored: list, previous_snapshot) -> None:
    """Raises SystemExit if this run's `scored` list is missing a target that was present in
    `previous_snapshot` (api/scores.json from the last publish) -- see the call site in _run() for
    why. No-op if there's no previous snapshot (first publish) or nothing is missing. Pure and
    RPC-free on purpose, unlike the rest of _run(), so this can be unit-tested directly."""
    if not previous_snapshot:
        return
    previous_targets = {e["target"].lower() for e in previous_snapshot.get("scores", [])}
    current_targets = {e["target"].lower() for e in scored}
    missing = sorted(previous_targets - current_targets)
    if missing:
        raise SystemExit(
            f"Refusing to proceed: {len(missing)} target(s) published last run are missing from "
            f"this run's scores -- {missing}. Likely SKIPPED over a persistent RPC failure (see "
            f"any 'score_all(): SKIPPED ...' line printed above), not a real removal. Re-run once "
            f"the RPC issue clears."
        )


def methodology_hash() -> bytes:
    # keccak256("<METHODOLOGY_VERSION>:<digest of every scoring file>") since 2026-09-30, see scripts/lib/methodology.py
    # (still keccak256, matching Solidity's keccak256(bytes), never sha256): a fix of the scorer now changes the
    # published hash, a change of the target's posture does not.
    return methodology.evm_hash("robinhood-chain", METHODOLOGY_VERSION)


def main():
    dry_run = "--dry-run" in sys.argv
    skip_slow = "--skip-slow" in sys.argv
    # ADDED 2026-09-18 (closes a tracked operational risk: a full run was
    # clocked exceeding 50 minutes -- "risque de timeout des routines").
    # --skip-slow omits the 4 scorers that do a full-chain-history log
    # replay (see scripts/lib/scorers.py's score_all()/_SLOW_SCORERS for
    # which ones and why), for a fast dev/verification pass. Never allowed
    # outside --dry-run: publishing a real updateScores() tx (or api/
    # scores.json) that's silently missing 4+ tracked targets, with nothing
    # in the published data itself saying so, is exactly the kind of
    # misleading-by-omission result this project's own discipline exists
    # to prevent -- fail loudly here instead.
    if skip_slow and not dry_run:
        raise SystemExit("--skip-slow is only allowed together with --dry-run -- a real publish must score every tracked target, never a silently incomplete subset.")
    try:
        _run(dry_run, skip_slow)
    except (Exception, SystemExit) as e:
        # SystemExit deliberately included: several failure paths in _run()
        # below (unreachable RPC, a reverted on-chain tx) raise SystemExit
        # directly as this script's own error-signaling convention, and
        # SystemExit does NOT inherit from Exception in Python -- an
        # `except Exception` here would silently miss exactly the cases
        # this fix exists for. KeyboardInterrupt is deliberately NOT caught
        # (also not an Exception subclass) -- an operator hitting Ctrl+C
        # should stop the script immediately, not trigger a failure alert.
        # FIXED 2026-09-17 (closed a disclosed gap): every alert this script
        # could send used to depend on the run reaching diff_alerts() at the
        # very end -- a crash anywhere before that (RPC unreachable, tx
        # rejected, receipt never confirms, PRIVATE_KEY malformed) exited
        # with a bare traceback and sent nothing, so a real signer rotation
        # or an outage on a tracked target's chain could go unnoticed
        # indefinitely if nobody happened to be watching the run's raw logs.
        # Never fires in --dry-run mode, matching that mode's existing
        # "not alerting" contract.
        if not dry_run:
            message = f"Authority Risk Oracle: update run FAILED -- {type(e).__name__}: {e}\n\n{DASHBOARD_URL}"
            sent = send_telegram_alert(message)
            print(f"Run failed ({type(e).__name__}: {e}) -- failure alert {'sent' if sent else 'NOT sent (Telegram not configured or send failed)'}.")
        raise


def _run(dry_run: bool, skip_slow: bool = False):
    methodology.code_digest("robinhood-chain")  # pin the code that runs now, before scoring
    if not dry_run:  # the published hash must match a commit
        methodology.require_committed("robinhood-chain")
    read_rpc_url = os.environ["READ_RPC_URL"]
    oracle_rpc_url = os.environ["ORACLE_RPC_URL"]
    oracle_address = os.environ["ORACLE_ADDRESS"]

    read_w3 = get_w3(read_rpc_url)
    if not read_w3.is_connected():
        raise SystemExit(f"Could not connect to read RPC: {read_rpc_url}")

    print(f"Reading target state from chain ID: {read_w3.eth.chain_id}")
    if skip_slow:
        print("--skip-slow set: omitting the 4 full-chain-history log-replay scorers (dev/verification pass only, not a complete run).")
    print("Re-deriving every tracked target's score from live chain state...\n")

    scored = score_all(read_w3, skip_slow=skip_slow)
    now = int(time.time())
    meth_hash = methodology_hash()
    print(methodology.describe("robinhood-chain", METHODOLOGY_VERSION))
    if not dry_run:  # right before sending: the files must still be the ones pinned before scoring
        methodology.assert_unchanged("robinhood-chain")

    # Load the previous published snapshot (if any) BEFORE anything downstream can overwrite it --
    # this is the only source both the completeness guard below and diff_alerts() (further down)
    # have for "what was published last time". Missing/corrupt file is treated as "first publish",
    # not an error. Moved earlier than the dry-run check on 2026-09-22 so the completeness guard
    # applies there too (a --dry-run operator relying on it to verify "does this currently work"
    # should see a silent gap just as loudly as a real push would refuse it).
    previous_snapshot = None
    if os.path.exists(API_SNAPSHOT_PATH):
        try:
            with open(API_SNAPSHOT_PATH) as f:
                previous_snapshot = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            print(f"Warning: could not read previous snapshot ({e}), treating as first publish.")

    # The oracle keeps one score per address: refuse the whole push if two entries share one
    # (scripts/lib/oracle_keys.py). Checked BEFORE completeness on purpose: a key collision is a
    # data-integrity bug in score_all() itself (two entries would silently overwrite each other
    # on-chain), a more fundamental problem than some targets being merely absent, and this project's
    # own test suite (scripts/lib/tests/test_oracle_keys.py) already locks in "refused before the
    # oracle RPC and the private key" for this specific guard -- keep it first in line.
    assert_unique_oracle_keys(scored, where="(robinhood push)")

    # ADDED 2026-09-22 (closes the tracked "web3_utils helpers rendent None pour un revert comme
    # [backlog note]" risk, see scripts/lib/web3_utils.RpcUnavailable): score_all() now
    # SKIPS a target instead of scoring it from an ambiguous None when a persistent RPC failure hits
    # it -- correct for that one target, but nothing used to check that score_all() still returned
    # everything it should have. Publishing api/scores.json (or updateScores()) with fewer targets
    # than the last snapshot, with nothing in the published data itself saying so, is exactly the
    # "misleading by omission" result --skip-slow's own guard above already exists to prevent, just
    # reached through an organic SKIP instead of that flag -- so it gets the same fail-loudly
    # treatment. Never checked under --skip-slow: that mode is DELIBERATELY missing 4 scorers by
    # design (see its own guard above), not a candidate for this check. diff_alerts()'s [MISSING]
    # branch is the second line of defense for whatever a future caller lets through anyway.
    if not skip_slow:
        check_completeness(scored, previous_snapshot)
    targets = []
    tuples = []
    for entry in scored:
        print(f"{entry['label']} ({entry['target']}): composite={entry['compositeScore']}/100, crossExposure={entry['crossExposureScore']}/100")
        for note in entry["notes"]:
            print(f"    {note}")
        targets.append(Web3.to_checksum_address(entry["target"]))
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
        print()

    if dry_run:
        print("--dry-run set: not sending a transaction, not writing api/scores.json, not alerting.")
        return

    # previous_snapshot was already loaded above (before this dry-run check), so the completeness
    # guard covers dry-run runs too; diff_alerts() below reuses that same snapshot rather than
    # reading it a second time.

    oracle_w3 = get_w3(oracle_rpc_url)
    if not oracle_w3.is_connected():
        raise SystemExit(f"Could not connect to oracle RPC: {oracle_rpc_url}")
    print(f"Pushing to oracle on chain ID: {oracle_w3.eth.chain_id}")

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

    # Publish the off-chain JSON snapshot (the "API": a documented, versioned
    # convenience cache of exactly what was just confirmed on-chain -- never
    # the source of truth, getScore() always is) and check it for anything
    # worth alerting on before this snapshot overwrites the one just diffed.
    api_scores = [
        {
            "target": entry["target"],
            "label": entry["label"],
            "adminKeyScore": entry["adminKeyScore"],
            "multisigScore": entry["multisigScore"],
            "timelockScore": entry["timelockScore"],
            "oracleAuthorityScore": entry["oracleAuthorityScore"],
            "crossExposureScore": entry["crossExposureScore"],
            "compositeScore": entry["compositeScore"],
            # ADDED 2026-09-17: off-chain ONLY -- the deployed oracle contract's
            # AuthorityScore struct has no field for this (a bigger, separate
            # migration decision), so it's published here in api/scores.json
            # rather than on-chain. See score_all()'s own docstring note for
            # what it means; None if score_rollup_l1_authority() itself failed
            # this run rather than a silently-wrong number.
            "l1CappedComposite": entry.get("l1CappedComposite"),
        }
        for entry in scored
    ]
    snapshot = {
        "oracle": Web3.to_checksum_address(oracle_address),
        "chainId": oracle_w3.eth.chain_id,
        "methodologyVersion": METHODOLOGY_VERSION,
        "methodologyHash": "0x" + meth_hash.hex(),
        "methodologyCommit": methodology.head_commit(),  # the commit whose scoring files the hash covers
        "generatedAt": now,
        "txHash": tx_hash.hex(),
        "blockNumber": receipt.blockNumber,
        "scores": api_scores,
    }
    os.makedirs(os.path.dirname(API_SNAPSHOT_PATH), exist_ok=True)
    with open(API_SNAPSHOT_PATH, "w") as f:
        json.dump(snapshot, f, indent=2)
        f.write("\n")
    print(f"Wrote {API_SNAPSHOT_PATH}")

    alerts = diff_alerts(previous_snapshot, api_scores)
    if alerts:
        print(f"{len(alerts)} alert(s) this run:")
        for line in alerts:
            print(f"  {line}")
        sent = send_telegram_alert(format_summary(alerts, DASHBOARD_URL))
        print("Telegram alert sent." if sent else "Telegram not configured (TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID unset) or send failed -- alerts printed above only.")
    else:
        print("No alerts this run (nothing dropped >= threshold, no new target below the alert ceiling).")


if __name__ == "__main__":
    main()
