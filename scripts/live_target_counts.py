#!/usr/bin/env python3
"""Read `trackedTargetsCount()` live from every deployed testnet oracle and
print the per-oracle numbers, their sum, and the "a+b+c" breakdown string the
docs use.

The Solana oracle (a native Anchor program, not an EVM contract) is read separately, by
`scripts/solana_oracle_reader.py`, and added as the last row of the output.

Why this exists: SUBMISSION.md/README.md quote a per-oracle target count and a
grand total, and the pipeline adds targets all day, so those figures went stale
several times within one day (54 -> 57 for Robinhood Chain, 100 -> 121 overall)
even after each was corrected by hand. Run this and paste its output instead of
recomputing from prose. Strictly read-only: plain eth_call, no key, no
transaction.

    python3 scripts/live_target_counts.py
"""
import sys

from web3 import Web3

sys.path.insert(0, __file__.rsplit("/", 1)[0])
import solana_oracle_reader  # noqa: E402

COUNT_ABI = [{"name": "trackedTargetsCount", "type": "function", "stateMutability": "view",
              "inputs": [], "outputs": [{"type": "uint256"}]}]

# (name, oracle address, testnet RPC). Addresses/RPCs are the ones documented in
# each ecosystem's own deploy README; several ecosystems share the identical
# oracle address because the same deployer key was at the same nonce on each.
ORACLES = [
    ("Robinhood Chain", "0x9BF45734D09bC7CA39238e767B2af9AAc62a7f52", "https://rpc.testnet.chain.robinhood.com/rpc"),
    ("Ethereum L1 (Sepolia)", "0xB6F8474ccC71AF477c31c2DF663B3942ddfbf906", "https://ethereum-sepolia-rpc.publicnode.com"),
    ("Arbitrum (Sepolia)", "0x50840a7667baEa9D05ad4ae3dCeb384724b58720", "https://sepolia-rollup.arbitrum.io/rpc"),
    ("Base (Sepolia)", "0x50840a7667baEa9D05ad4ae3dCeb384724b58720", "https://sepolia.base.org"),
    ("Tempo (Moderato)", "0x50840a7667baEa9D05ad4ae3dCeb384724b58720", "https://rpc.moderato.tempo.xyz"),
    ("Plasma", "0x50840a7667baEa9D05ad4ae3dCeb384724b58720", "https://testnet-rpc.plasma.to"),
    ("Monad", "0x50840a7667baEa9D05ad4ae3dCeb384724b58720", "https://testnet-rpc.monad.xyz/"),
    ("Hyperliquid (HyperEVM)", "0x50840a7667baEa9D05ad4ae3dCeb384724b58720", "https://rpc.hyperliquid-testnet.xyz/evm"),
]


def read_counts(oracles=ORACLES, web3_cls=Web3):
    """Returns [(name, count_or_None, error_or_None)] -- a failing oracle is
    reported, never silently dropped from the total."""
    out = []
    for name, address, rpc in oracles:
        try:
            w3 = web3_cls(web3_cls.HTTPProvider(rpc, request_kwargs={"timeout": 20}))
            code = w3.eth.get_code(web3_cls.to_checksum_address(address))
            if not code or len(code) == 0:
                out.append((name, None, "no bytecode at oracle address"))
                continue
            c = w3.eth.contract(address=web3_cls.to_checksum_address(address), abi=COUNT_ABI)
            out.append((name, int(c.functions.trackedTargetsCount().call()), None))
        except Exception as e:  # noqa: BLE001 -- report per-oracle, keep going
            out.append((name, None, f"{type(e).__name__}: {e}"))
    return out


def read_solana_count(reader=solana_oracle_reader.read_oracle):
    """Same contract as `read_counts()` for the one non-EVM oracle: (name, count_or_None, error_or_None)."""
    try:
        return ("Solana (Devnet)", len(reader()["tracked"]), None)
    except Exception as e:  # noqa: BLE001 -- reported, never dropped from the total
        return ("Solana (Devnet)", None, f"{type(e).__name__}: {e}")


def main():
    rows = read_counts() + [read_solana_count()]
    for name, count, err in rows:
        print(f"  {name:<24} {count if err is None else 'UNREADABLE -- ' + err}")
    ok = [c for _, c, e in rows if e is None]
    failed = [n for n, _, e in rows if e is not None]
    print(f"\n{sum(ok)} scored targets across {len(ok)} of {len(rows)} oracles: " + "+".join(str(c) for c in ok))
    if failed:
        print(f"INCOMPLETE -- could not read: {', '.join(failed)} (do not quote the total above)")
        sys.exit(1)


if __name__ == "__main__":
    main()
