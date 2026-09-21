#!/usr/bin/env python3
"""Cross-ecosystem oracle key SET audit (read-only: public RPC reads, no key, no transaction).

Extends check_oracle_key_collisions.py's own count-only predecessor
(data/audit_oracle_key_collisions_2026-09-20.md): that audit compared on-chain COUNT against scored
COUNT per oracle and found one documented gap (Ethereum L1, 20 on-chain vs 19 scored -- a retired
Ethena minter the oracle contract has no removal function for, see
chains/ethereum-l1/deploy/README.md rows 3/14). A count match can hide a SWAP: an orphan on-chain
key that happens to cancel out against a missing scored key, leaving the totals equal while the
actual sets differ. This compares the SETS themselves, not just their size, for each of the 9
deployed oracles (Robinhood Chain, Ethereum L1, Arbitrum, Base, Tempo, Plasma, Monad, Hyperliquid,
Solana; Zcash has no on-chain oracle contract at all -- see SUBMISSION.md -- and is out of scope).

For each oracle:
- ON-CHAIN side: every key in trackedTargets(0..trackedTargetsCount()-1) (EVM, same ABI
  oracle_freshness.py already reads), or the Solana Registry's own `tracked` list
  (solana_oracle_reader.read_oracle(), which already cross-checks it against score accounts
  internally and raises on any disagreement -- never a silent partial read).
- SCORED side: score_all()'s current live output for that ecosystem, in its own subprocess (same
  isolation as validate_all_scorers.py / check_oracle_key_collisions.py, whose fetch_entries() and
  Hyperliquid resolver this file reuses rather than re-implementing), with Hyperliquid's own
  derived-key resolution applied first -- its push script pushes `oracleKey`, every other ecosystem
  pushes `target` (see scripts/lib/oracle_keys.py's own docstring).

Reports, per oracle: ORPHAN keys (on-chain, no scored entry currently produces them -- a stale or
never-removed row, like the Ethereum L1 case above) and GAP keys (scored, but not found on-chain --
never pushed, or pushed under a different key than the one compared here). An oracle that cannot be
fully read on EITHER side is reported FAILED, never silently treated as matching.

    python3 scripts/check_oracle_key_sets.py                          # every oracle
    python3 scripts/check_oracle_key_sets.py --ecosystem solana,base
    python3 scripts/check_oracle_key_sets.py --skip robinhood-chain   # the slow one (about 25 minutes)

A --skip/--ecosystem run audits fewer than all 9 oracles ON PURPOSE -- the final summary always
states how many of the 9 were actually audited this run, and prints INCOMPLETE (never just "EVERY...
MATCHES") whenever that is fewer than 9, so a partial run's output can't be mistaken for full
coverage if quoted on its own. Exit code 0 only if every AUDITED oracle was fully read on both sides
and no orphan or gap was found among them -- narrowing the scope on purpose is not itself a failure,
matching check_oracle_key_collisions.py's and live_target_counts.py's own behavior; only a FAILED or
MISMATCH oracle (never an oracle you deliberately excluded) drives the non-zero exit.
"""
import argparse
import os
import sys
from concurrent.futures import ThreadPoolExecutor

from web3 import Web3

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "lib"))
import check_oracle_key_collisions as ckc  # noqa: E402
import oracle_keys  # noqa: E402
import solana_oracle_reader  # noqa: E402
import validate_all_scorers as v  # noqa: E402

TRACKED_ABI = [
    {"name": "trackedTargetsCount", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "uint256"}]},
    {"name": "trackedTargets", "type": "function", "stateMutability": "view", "inputs": [{"type": "uint256"}], "outputs": [{"type": "address"}]},
]

# (ecosystem key in validate_all_scorers.ECOSYSTEMS, display name, oracle address, testnet RPC) for
# the 8 EVM oracles -- same addresses/RPCs scripts/live_target_counts.py already documents (several
# ecosystems share one address: same deployer key at the same nonce on each chain), in the same order.
EVM_ORACLES = [
    ("robinhood-chain", "Robinhood Chain", "0x9BF45734D09bC7CA39238e767B2af9AAc62a7f52", "https://rpc.testnet.chain.robinhood.com/rpc"),
    ("ethereum-l1", "Ethereum L1 (Sepolia)", "0xB6F8474ccC71AF477c31c2DF663B3942ddfbf906", "https://ethereum-sepolia-rpc.publicnode.com"),
    ("arbitrum", "Arbitrum (Sepolia)", "0x50840a7667baEa9D05ad4ae3dCeb384724b58720", "https://sepolia-rollup.arbitrum.io/rpc"),
    ("base", "Base (Sepolia)", "0x50840a7667baEa9D05ad4ae3dCeb384724b58720", "https://sepolia.base.org"),
    ("tempo", "Tempo (Moderato)", "0x50840a7667baEa9D05ad4ae3dCeb384724b58720", "https://rpc.moderato.tempo.xyz"),
    ("plasma", "Plasma", "0x50840a7667baEa9D05ad4ae3dCeb384724b58720", "https://testnet-rpc.plasma.to"),
    ("monad", "Monad", "0x50840a7667baEa9D05ad4ae3dCeb384724b58720", "https://testnet-rpc.monad.xyz/"),
    ("hyperliquid", "Hyperliquid (HyperEVM)", "0x50840a7667baEa9D05ad4ae3dCeb384724b58720", "https://rpc.hyperliquid-testnet.xyz/evm"),
]
ALL_ECOSYSTEMS = [eco for eco, *_ in EVM_ORACLES] + ["solana"]


def read_onchain_keys_evm(address, rpc, web3_cls=Web3):
    """The full, normalized set of trackedTargets(i) on one EVM oracle. Raises on any read failure --
    never returns a partial set silently (an incomplete on-chain read must not be mistaken for a
    small, clean one)."""
    w3 = web3_cls(web3_cls.HTTPProvider(rpc, request_kwargs={"timeout": 20}))
    addr = web3_cls.to_checksum_address(address)
    code = w3.eth.get_code(addr)
    if not code or len(code) == 0:
        raise RuntimeError("no bytecode at oracle address")
    c = w3.eth.contract(address=addr, abi=TRACKED_ABI)
    count = int(c.functions.trackedTargetsCount().call())
    return {oracle_keys._evm_normalize(c.functions.trackedTargets(i).call()) for i in range(count)}


def read_onchain_keys_solana():
    """base58, compared exact -- same convention scripts/lib/oracle_keys.py already uses for Solana.
    Looks up solana_oracle_reader.read_oracle fresh on every call (not as a bound default argument --
    the same trap scored_keys() below was just fixed for in this file; patch.object(k,
    "solana_oracle_reader") on the module works here for the same reason it works there)."""
    return set(solana_oracle_reader.read_oracle()["tracked"])


def scored_keys(name, timeout):
    """(keys, error) -- the normalized set of keys score_all() currently produces for one ecosystem,
    honouring Hyperliquid's own derived-oracleKey resolution (see this file's own module docstring).
    Looks up ckc.fetch_entries/ckc._hyperliquid_resolver fresh on every call (not as bound default
    arguments) so tests can patch them on the ckc module, same as this repo's other test doubles."""
    entries, err = ckc.fetch_entries(name, timeout)
    if err:
        return None, err
    if not entries:
        return None, "score_all() returned zero entries"
    exact = name in ckc.EXACT_KEY_ECOSYSTEMS  # reuse the one existing table rather than a second copy
    if name == "hyperliquid":
        try:
            ckc._hyperliquid_resolver()(entries)
        except SystemExit as e:
            return None, f"the push script's own resolution refuses: {e}"
        return {oracle_keys.entry_key(e, exact, honour_oracle_key=True) for e in entries}, None
    return {oracle_keys.entry_key(e, exact) for e in entries}, None


def audit_one(ecosystem, display_name, onchain_fn, timeout):
    """Never lets one oracle's failure -- on either side -- propagate past this function: a
    ThreadPoolExecutor.map() caller (see main()) has no per-item try/except of its own, so an
    uncaught exception here would abort the WHOLE audit and lose every other oracle's report, not
    just fail this one. scored_keys()'s own (None, err) contract is only ONE of its failure modes --
    it can also raise directly (ckc.fetch_entries spawning a subprocess, ckc._hyperliquid_resolver
    importing push_scores.py live) -- so this wraps the call itself, not just its return value."""
    try:
        onchain = onchain_fn()
    except Exception as e:  # noqa: BLE001 -- reported per-oracle, never silently treated as empty
        return {"ecosystem": ecosystem, "display": display_name, "error": f"on-chain read failed: {type(e).__name__}: {e}"}
    try:
        scored, err = scored_keys(ecosystem, timeout)
    except Exception as e:  # noqa: BLE001 -- reported per-oracle, never crashes the other oracles' jobs
        return {"ecosystem": ecosystem, "display": display_name, "error": f"scored read failed (unexpected exception): {type(e).__name__}: {e}"}
    if err:
        return {"ecosystem": ecosystem, "display": display_name, "error": f"scored read failed: {err}"}
    orphans = onchain - scored
    gaps = scored - onchain
    return {"ecosystem": ecosystem, "display": display_name, "error": None,
            "onchain_count": len(onchain), "scored_count": len(scored), "orphans": orphans, "gaps": gaps}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ecosystem", help="only these ecosystems (comma-separated)")
    ap.add_argument("--skip", help="skip these ecosystems (comma-separated)")
    ap.add_argument("--timeout", type=int, default=None, help="per-ecosystem timeout in seconds (default: validate_all_scorers' own)")
    args = ap.parse_args()

    names = list(ALL_ECOSYSTEMS)
    if args.ecosystem:
        wanted = set(args.ecosystem.split(","))
        unknown = wanted - set(ALL_ECOSYSTEMS)
        if unknown:
            raise SystemExit(f"Unknown ecosystem(s): {sorted(unknown)}. Known: {sorted(ALL_ECOSYSTEMS)}")
        names = [n for n in names if n in wanted]
    if args.skip:
        skipped = set(args.skip.split(","))
        unknown = skipped - set(ALL_ECOSYSTEMS)
        if unknown:
            raise SystemExit(f"Unknown ecosystem(s) in --skip: {sorted(unknown)}. Known: {sorted(ALL_ECOSYSTEMS)}")
        names = [n for n in names if n not in skipped]
    if not names:
        raise SystemExit("no ecosystem selected: refusing to report a clean result for an empty audit")

    jobs = []
    for eco, display, addr, rpc in EVM_ORACLES:
        if eco in names:
            jobs.append((eco, display, lambda addr=addr, rpc=rpc: read_onchain_keys_evm(addr, rpc)))
    if "solana" in names:
        jobs.append(("solana", "Solana (Devnet)", read_onchain_keys_solana))

    def one(job):
        eco, display, onchain_fn = job
        timeout = args.timeout if args.timeout is not None else v._ECOSYSTEM_TIMEOUT_DEFAULTS.get(eco, v._FALLBACK_TIMEOUT)
        return audit_one(eco, display, onchain_fn, timeout)

    # Capped, not len(jobs): up to 9 parallel live score_all() subprocesses (each itself hitting
    # public mainnet RPCs) plus up to 8 parallel EVM on-chain reads would exceed this project's own
    # documented limit (see the ABI-returndata-guard project note: at most 2-3 live calculations in
    # parallel against public RPCs) and risks 429s producing phantom ORPHAN/GAP noise, not a silent
    # false-clean (only keys are compared here, not scores) but still incredible output.
    with ThreadPoolExecutor(max_workers=min(len(jobs), 3)) as pool:  # jobs is non-empty: the "no ecosystem selected" guard above already refused an empty run
        reports = list(pool.map(one, jobs))

    ok = True
    for r in reports:
        if r["error"]:
            ok = False
            print(f"{r['display']:24} FAILED  {r['error']}")
            continue
        if r["orphans"] or r["gaps"]:
            ok = False
            print(f"{r['display']:24} MISMATCH  {r['onchain_count']} on-chain keys, {r['scored_count']} distinct scored keys")
            for k in sorted(r["orphans"]):
                print(f"    ORPHAN (on-chain, no scored entry currently produces it): {k}")
            for k in sorted(r["gaps"]):
                print(f"    GAP (scored, not found on-chain): {k}")
            continue
        print(f"{r['display']:24} ok  {r['onchain_count']} on-chain keys, {r['scored_count']} distinct scored keys, sets match")

    # Scope disclosure: a --skip/--ecosystem run audits fewer than all 9 oracles ON PURPOSE (the
    # module docstring's own example, `--skip robinhood-chain`, does this -- and Robinhood Chain
    # alone was over a third of all tracked keys as of 2026-09-20). Printing an unqualified "EVERY...
    # MATCHES" for a partial run would overclaim coverage exactly the way the sibling tools in this
    # repo (check_oracle_key_collisions.py's "{total} entries across {len(reports)} ecosystem(s)",
    # live_target_counts.py's "INCOMPLETE -- do not quote the total above") both refuse to.
    audited, total = len(reports), len(ALL_ECOSYSTEMS)
    scope_line = f"\n{audited} of {total} oracle(s) audited"
    if audited < total:
        not_audited = ", ".join(n for n in ALL_ECOSYSTEMS if n not in names)
        scope_line += f" -- INCOMPLETE, not audited this run: {not_audited} (do not quote the result below as covering every oracle)"
    print(scope_line)
    if ok:
        print("RESULT: EVERY AUDITED ON-CHAIN KEY SET MATCHES ITS SCORED SET" if audited == total
              else "RESULT: EVERY AUDITED KEY SET MATCHES (SCOPE INCOMPLETE, SEE ABOVE)")
    else:
        print("RESULT: FAIL (orphan, gap, or an oracle could not be fully read)")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
