"""
Tempo authority scorers -- 13 flagship targets (2026-09-17: chain baseline,
USDC.e, USDT0, pathUSD; 6 more added 2026-09-18: USDB, cbBTC, PRIME, DLUSD,
EURC.e, cUSD; 3 Morpho Vault V2 instances added the same day, see below).

Promotes `METHODOLOGY.md` section 4.1 (rules R1-R7, the numeric mapping
added by the methodology test) into the same `scorers.py` / `score_all()`
shape every other ecosystem in this project uses. Every read-and-score
primitive already existed, fully working and already live-tested, in
`scripts/methodology_test.py` (`score_chain_baseline()`, `score_token()`,
`cross_exposure()`, role-log scanning, key classification) -- this file
imports those directly rather than duplicating them (the same "one
canonical copy" discipline already applied this pass to Solana's
`sol_read.py` decoders and Hyperliquid's `methodology_test.py` functions),
and adds only the top-level `score_all()` sequencing that
`methodology_test.py`'s own `main()` previously did inline and unexported.

Every number is derived live from Tempo Mainnet on each run, with every
`eth_call` fact independently cross-checked against a second RPC inside
`methodology_test.py`'s own `call2()` (raises on disagreement -- not an
optional cross-check, a hard requirement baked into the read primitive
itself). See `data/scored_targets_2026-09-17.md` for the first 4 targets'
live-verified numbers (`chain baseline`/USDC.e/USDT0 match `data/
methodology_test_2026-09-16.md`'s hand-derived reference values exactly,
31/55/43 composite) and `data/scored_targets_2026-09-18-controller-types.md`
for the 6 new targets added 2026-09-18, which closed `classify()`'s
previous inability to resolve 4 real controller shapes (a plain
OpenZeppelin TimelockController, Chainlink RBACTimelock + hierarchical
MCMS, a UUPS AccessControlEnumerable "bridge controller", and a LayerZero
endpoint delegate as a parallel zero-delay path) -- every one of these
used to collapse to "unresolved contract" (composite 8), including
`pathUSD` itself (now correctly 9, not 8: it shares the Bridge controller
with USDB and DLUSD). `score_vault_v2()`, also added 2026-09-18, closes a
separate open point (a written target type for Morpho Vault V2, not an R2
controller hop) -- see its own docstring and `VAULT_V2_TARGETS` in
`scripts/methodology_test.py`."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "scripts"))
# scripts/lib is appended (never first: it has its own scorers.py); the guard must be installed BEFORE methodology_test imports eth_abi.decode
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "..", "scripts", "lib"))
import abi_returndata_guard  # noqa: E402
abi_returndata_guard.ensure_installed("raise")
import methodology_test as mt  # noqa: E402


def _normalize_field_names(results: list):
    # FIXED 2026-09-17 (caught by scripts/validate_all_scorers.py's first
    # real run, not by inspection): methodology_test.py's own return shape
    # uses "target" for the human-readable name and "address" for the
    # on-chain address -- the OPPOSITE of every other ecosystem in this
    # project ("target" = address, "label" = name). Left as-is inside
    # methodology_test.py (its own docstrings and
    # data/methodology_test_2026-09-16.md already document and reproduce
    # that exact shape), but normalized here so this file's own score_all()
    # output matches the project-wide convention every downstream consumer
    # (an on-chain tuple, api/scores.json, this project's own
    # cross-ecosystem tooling) already assumes -- a real schema mismatch
    # that would have pushed a label string where an address was expected.
    # FIXED 2026-09-17 (closed a bug hunt finding): the pop()-based swap
    # above is not idempotent -- calling this twice on the same dict (e.g.
    # a future caller re-running it, or a REPL/debug session inspecting
    # `results` after a partial run) would pop the now-relocated "target"
    # (holding the address) into "label", clobbering the correct
    # human-readable name, then crash with KeyError on the missing
    # "address" key. Guarded to be a safe no-op on a second call.
    for r in results:
        if "address" not in r:
            continue  # already normalized (or never had the legacy shape) -- no-op
        r["label"] = r.pop("target")
        r["target"] = r.pop("address")


def score_all(_url_unused=None) -> list:
    # Signature matches every other ecosystem's score_all(url) for the
    # update_scores.py harness's sake, even though Tempo's reads are fixed
    # official endpoints (see methodology_test.py's RPCS constant), not a
    # caller-supplied RPC URL -- accepted and ignored rather than
    # special-cased by the caller.
    try:
        head, events = mt.scan_role_logs([t["address"] for t in mt.TOKENS.values()])
        results = [mt.score_chain_baseline()]
        for label, t in mt.TOKENS.items():
            token = mt.to_checksum_address(t["address"])
            results.append(mt.score_token(label, t["address"], t["lz_oapp"], events[token]))
        # ADDED 2026-09-18: Morpho Vault V2 target type (mt.score_vault_v2,
        # closes scouted_targets_2026-09-17-run2.md section 8 open point 4)
        # -- same "target"/"address" legacy naming as score_token/
        # score_chain_baseline above, swapped to this project's convention
        # by _normalize_field_names() below like every other Tempo result.
        for label, addr in mt.VAULT_V2_TARGETS.items():
            results.append(mt.score_vault_v2(label, addr))
        # ADDED 2026-09-19: Morpho Blue core (rule R9, mt.score_morpho_blue).
        for label, addr in mt.MORPHO_BLUE_TARGETS.items():
            results.append(mt.score_morpho_blue(label, addr))
        mt.cross_exposure(results)
        base = results[0]["compositeScore"]
        for r in results[1:]:
            # CORRECTED 2026-09-20: used to overwrite `notes`, which would now drop the
            # cross-chain committee finding mt.cross_exposure() puts on the Morpho Blue core.
            r["notes"] = {"chainCappedComposite": min(r["compositeScore"], base), **r.get("notes", {})}
        _normalize_field_names(results)
        return results
    except Exception as e:
        # Per-run isolation at the batch level (not per-target like every other
        # ecosystem's score_all()): the role-log scan and chain-baseline read
        # are shared setup every token score below depends on, so a failure
        # here can't isolate to "one target" the way an independent EVM
        # eth_call chain can -- printed and skipped rather than silently
        # returning a stale/partial result.
        print(f"score_all(): SKIPPED this run -- {type(e).__name__}: {e}")
        return []
