#!/usr/bin/env python3
"""Who controls what, the other way round: what can ONE address touch across every tracked ecosystem?

check_cross_ecosystem_overlap.py answers "which protocols share signers". This inverts the same live
resolution (every registry group's root signers, 8 EVM ecosystems) into an address -> tracked groups
index, so a security team, a Safe signer or a protocol can ask "if this key is compromised, which
tracked protocols are affected?" and see the most-connected keys in the whole set.

    python3 scripts/who_controls.py 0xADDRESS [0xADDRESS ...]   # blast radius of each address
    python3 scripts/who_controls.py --top 15                    # most-connected signers
    python3 scripts/who_controls.py --families                  # protocol families whose signer set repeats across ecosystems
    python3 scripts/who_controls.py --code-scan                 # EOA / EIP-7702-delegated / contract, per signer per chain
    python3 scripts/who_controls.py --write-index PATH          # dump the full index as JSON

Read-only (public RPC only, no key, no transaction), disclosure only: no score reads any of this.
Solana and Zcash are out of scope (their key formats are not bridged); Hyperliquid covers only its
4 HyperEVM Safe-rooted targets. A group whose Safe failed to resolve is listed under INCOMPLETE.
"""
import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from check_cross_ecosystem_overlap import REGISTRIES, resolve_all  # noqa: E402
from lib.authority_index import blast_radius, build_index, classify_code, family_reach, hygiene_summary, top_signers  # noqa: E402
from web3 import Web3  # noqa: E402


def code_scan(ecosystem_groups, w3s):
    """{(ecosystem, signer): (kind, delegate)} for every resolved root signer, read on that signer's own chain."""
    pairs = sorted({(eco, s) for (eco, _), signers in ecosystem_groups.items() for s in signers})

    def read(pair):
        eco, addr = pair
        try:
            return pair, classify_code(bytes(w3s[eco].eth.get_code(Web3.to_checksum_address(addr))))
        except Exception as e:  # a failed read is reported, never treated as "eoa"
            return pair, ("unread", f"{type(e).__name__}: {e}")

    with ThreadPoolExecutor(8) as ex:
        return dict(ex.map(read, pairs))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("addresses", nargs="*")
    ap.add_argument("--top", type=int)
    ap.add_argument("--families", action="store_true")
    ap.add_argument("--code-scan", action="store_true")
    ap.add_argument("--write-index")
    args = ap.parse_args()
    if not (args.addresses or args.top or args.families or args.code_scan or args.write_index):
        ap.error("give an address, --top N, --families, --code-scan or --write-index PATH")

    ecosystem_groups, _, _, incomplete, w3s = resolve_all()
    registries = {eco: groups for eco, (_, groups, _) in REGISTRIES.items()}
    index = build_index(registries, ecosystem_groups)
    print(f"{len(ecosystem_groups)} groups, {len(index)} distinct addresses indexed, "
          f"{len(incomplete)} group(s) INCOMPLETE" + (f": {sorted({(e, k) for e, k, _, _ in incomplete})}" if incomplete else "") + "\n")

    for a in args.addresses:
        r = blast_radius(index, a)
        print(f"{r['address']}: {len(r['groups'])} group(s) across {len(r['ecosystems'])} ecosystem(s)"
              + (f" (includes L1/L2 alias {', '.join(r['via_alias'])})" if r["via_alias"] else ""))
        for eco, key, role in r["entries"]:
            print(f"    {eco}:{key}  [{role}]")
        if not r["entries"]:
            print("    not in any tracked group (absence here is not proof of safety: unresolved groups and Solana/Zcash are out of scope)")

    if args.top:
        print(f"=== Top {args.top} most-connected signers ===")
        for t in top_signers(index, args.top):
            fam = f", {t['family_count']} distinct famil{'y' if t['family_count'] == 1 else 'ies'}" if t["family_count"] != t["groups"] else ""
            print(f"  {t['address']}  {t['ecosystems']} ecosystem(s), {t['groups']} group(s){fam}: " + ", ".join(f"{e}:{k}" for e, k in t["where"][:6]))

    if args.families:
        fr = family_reach(index)
        print(f"=== {len(fr)} protocol famil{'y' if len(fr) == 1 else 'ies'} whose registry group key repeats across ecosystems ===")
        for key, r in sorted(fr.items(), key=lambda kv: (-len(kv[1]["ecosystems"]), kv[0])):
            same = " -- IDENTICAL signer set on every ecosystem below (one committee, one point of failure)" if r["identical_across_ecosystems"] else ""
            print(f"  {key}: {len(r['ecosystems'])} ecosystems ({', '.join(r['ecosystems'])}), {len(r['signers'])} distinct signer(s) across them{same}")

    if args.code_scan:
        classified = code_scan(ecosystem_groups, w3s)
        unread = {k: v for k, v in classified.items() if v[0] == "unread"}
        s = hygiene_summary({k: v for k, v in classified.items() if v[0] != "unread"})
        print(f"=== Signer code scan: {len(classified)} (chain, signer) pairs, {len(unread)} unread ===")
        print(f"  {s['counts']}")
        for delegate, who in s["delegates"].items():
            print(f"  EIP-7702 delegate {delegate}: {len(who)} signer(s): " + ", ".join(who[:8]))
        for (eco, addr), v in unread.items():
            print(f"  UNREAD {eco}:{addr} -- {v[1]}")

    if args.write_index:
        with open(args.write_index, "w") as f:
            json.dump({a: [list(e) for e in v] for a, v in sorted(index.items())}, f, indent=1)
        print(f"index written to {args.write_index}")


if __name__ == "__main__":
    main()
