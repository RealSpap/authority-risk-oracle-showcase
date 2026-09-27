#!/usr/bin/env python3
"""Read-only look at WHO signs across the Squads/Realms multisigs and councils
already live-verified by chains/solana/scorers.py's own SIMPLE_SCORERS, for
every target already tracked by the oracle (Jupiter Aggregator/Perps/Lend,
Kamino Lend/Liquidity, Raydium, marginfi, PumpSwap, Meteora DAMM v2, Orca
Whirlpool, Marinade, Solend DAO governance, Drift, Save, SPL Stake Pool
program, JitoSOL, Sanctum Infinity, Sanctum validator LSTs) -- the Solana
port of chains/ethereum-l1/scripts/sweep_safe_signers.py's method.

    python3 sweep_squads_signers.py [rpc_url] [--dump signers.json]

What this adds beyond scorers.py's own `_apply_cross_exposure()` (which
already folds pairwise "target X shares >=1 signer with target Y" into
crossExposureScore, see that function's docstring): (1) it names the actual
shared PUBLIC KEYS, not just the fact of overlap; (2) it classifies each one
(plain on-curve wallet key vs an off-curve PDA/program/nested-multisig,
mirroring the EVM script's EOA/7702/Safe/contract split); (3) it computes
TRANSITIVE groups via union-find (same discipline as the EVM script's Safe
grouping) -- two protocols with no direct shared signer can still land in
one group through a third protocol, which a purely pairwise check (what
_apply_cross_exposure does today) cannot show.

Calls each SIMPLE_SCORERS function directly (not score_all(), which strips
`_signers` after folding it into crossExposureScore) -- so this reuses the
exact same live, offline-PDA-re-verified signer sets the oracle itself
already computed, not a second hand-copied list of multisig addresses.
Nothing is sent, no key.
"""
import collections
import json
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))              # this file lives in chains/solana/scripts/, next to sol_read.py
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))  # chains/solana/, where scorers.py lives
import scorers  # noqa: E402
import sol_read  # noqa: E402

RPC = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else "https://api.mainnet-beta.solana.com"
DUMP = sys.argv[sys.argv.index("--dump") + 1] if "--dump" in sys.argv else None


def classify(pk):
    """Plain on-curve wallet key vs off-curve PDA -- and for a PDA, which
    program owns it (a nested Squads vault, a Realms council PDA, or
    something else), the Solana analogue of the EVM script's eth_getCode
    classify()."""
    try:
        kt = sol_read.read_keytype(RPC, pk)
    except Exception as e:
        return {"kind": "unread", "owner": None, "error": str(e)}
    if kt["on_curve"]:
        return {"kind": "wallet (on-curve, a real keypair can sign for it)", "owner": kt["owner"]}
    if not kt["exists"]:
        return {"kind": "off-curve, no account (unfunded/unused PDA)", "owner": None}
    owner = kt["owner"]
    name = {
        scorers.SQUADS_V3_PROGRAM: "off-curve PDA owned by Squads v3 (nested multisig authority)",
        scorers.SQUADS_V4_PROGRAM: "off-curve PDA owned by Squads v4 (nested multisig authority)",
    }.get(owner, f"off-curve PDA owned by {owner}")
    if kt["executable"]:
        name = "off-curve, itself an executable program"
    return {"kind": name, "owner": owner}


def main():
    per_target = []  # (label, target, signers:set)
    for scorer in scorers.SIMPLE_SCORERS:
        name = scorer.__name__
        try:
            r = scorer(RPC)
        except Exception as e:
            print(f"SKIPPED {name} -- {type(e).__name__}: {e}")
            continue
        for r in (r if isinstance(r, list) else [r]):  # score_solgov_leads returns one result per lead
            sig = r.get("_signers") or set()
            per_target.append((r["label"], r["target"], sig))
            print(f"{r['label']:45s} {len(sig):3d} signers  compositeScore={r.get('compositeScore')}")

    print(f"\n{len(per_target)} targets read, {sum(1 for _, _, s in per_target if s)} with a resolved signer set")

    # signer -> {labels}
    by_signer = collections.defaultdict(set)
    for label, _target, sig in per_target:
        for k in sig:
            by_signer[k].add(label)

    shared = {k: labels for k, labels in by_signer.items() if len(labels) > 1}
    print(f"{len(by_signer)} distinct signer pubkeys across all resolved targets; {len(shared)} appear on more than one tracked protocol")

    if shared:
        print("\nkeys shared across protocols (classified live, one getAccountInfo each):")
        for k, labels in sorted(shared.items(), key=lambda kv: -len(kv[1])):
            c = classify(k)
            print(f"  {k}  on {len(labels)} protocols: {sorted(labels)}")
            print(f"      -> {c['kind']}")
    else:
        print("\nno signer pubkey is shared across two or more tracked protocols at the raw-key level.")

    # transitive groups (union-find), same discipline as sweep_safe_signers.py
    labels_all = [label for label, _, _ in per_target]
    parent = {l: l for l in labels_all}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    first_owner = {}
    for label, _target, sig in per_target:
        for k in sig:
            if k in first_owner:
                union(label, first_owner[k])
            else:
                first_owner[k] = label

    groups = collections.defaultdict(list)
    for label in labels_all:
        groups[find(label)].append(label)
    multi_groups = [g for g in groups.values() if len(g) > 1]
    print(f"\n{len(groups)} independent transitive signer-groups over {len(labels_all)} tracked protocols "
          f"({len(multi_groups)} group(s) span more than one protocol):")
    for g in sorted(multi_groups, key=lambda g: -len(g)):
        print(f"  {sorted(g)}")

    if DUMP:
        json.dump({
            "rpc": RPC,
            "targets": [{"label": l, "target": t, "signers": sorted(s)} for l, t, s in per_target],
            "shared_signers": {k: sorted(v) for k, v in shared.items()},
            "groups": [sorted(g) for g in groups.values()],
        }, open(DUMP, "w"), indent=2)
        print(f"\nwrote {DUMP}")


if __name__ == "__main__":
    main()
