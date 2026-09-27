"""
How much of a chain's value do the tracked targets cover, and what is the biggest untracked protocol? Pure logic for scripts/check_tvl_coverage.py.

Matching is by NAME, on purpose crude: a DefiLlama protocol counts as tracked when its first significant name token appears in a tracked target's label.
It errs both ways (a renamed protocol is missed; "Aave V2" is counted with "Aave V3"), which is why the tool prints the largest UNMATCHED protocols for a human
to read, instead of trusting the percentage. Same method and same limits as data/coverage_2026-09-21-tvl-by-ecosystem.md, now reproducible.
"""
import re

STOP = {"v1", "v2", "v3", "v4", "v5", "v6", "protocol", "finance", "network", "labs", "dao", "swap", "exchange", "dex", "the", "money", "fi", "capital",
        "lend", "lending", "vault", "vaults", "pool", "pools", "chain", "bridge", "and", "of", "usd", "app", "x", "liquid", "staking"}
# DefiLlama renames that the name match cannot see: DefiLlama token -> the token this project's label uses (each verified against the live label list).
ALIASES = {"eigencloud": "eigenlayer"}
# Renames keyed by the FULL DefiLlama name, where the first token is shared with another protocol ("GMX Solana" was GMTrade; "GMX V2" on Arbitrum is a different, tracked target).
NAME_ALIASES = {
    "gmx solana": "gmtrade",
    # "USD AI" tokenizes to ["usd", "ai"]: "usd" is a stopword and "ai" is under the 3-character floor `significant()`
    # uses everywhere else, so this DefiLlama name has NO significant token at all and could never match by name --
    # not a rename, a real tracked target (chains/arbitrum-ecosystem/scorers.py::score_usd_ai_mintburn, DefiLlama slug
    # usd-ai) whose own label contains "ai" as a plain (unfiltered) token.
    "usd ai": "ai",
}
EXCLUDED_CATEGORIES = {"CEX"}  # proof-of-reserves figures: no contract whose authority this oracle would score


def tokens(text: str) -> list:
    return [t for t in re.split(r"[^a-z0-9]+", text.lower()) if t]


def significant(name: str) -> list:
    return [t for t in tokens(name) if t not in STOP and len(t) >= 3]


def label_tokens(labels: list) -> set:
    out = set()
    for l in labels:
        out.update(tokens(l))
    return out


def is_tracked(protocol_name: str, labels_tokens: set) -> bool:
    sig = significant(protocol_name)
    first = NAME_ALIASES.get(protocol_name.strip().lower()) or (ALIASES.get(sig[0], sig[0]) if sig else None)
    return bool(first) and first in labels_tokens


def chain_rows(protocols: list, chain: str) -> list:
    """[(name, category, tvl_usd)] for every protocol with a positive TVL on `chain`, CEX excluded, largest first."""
    rows = []
    for p in protocols:
        tvl = (p.get("chainTvls") or {}).get(chain)
        if tvl and tvl > 0 and p.get("category") not in EXCLUDED_CATEGORIES:
            rows.append((p["name"], p.get("category") or "?", float(tvl)))
    return sorted(rows, key=lambda r: -r[2])


def coverage(protocols: list, chain: str, labels: list, top: int = 12) -> dict:
    rows = chain_rows(protocols, chain)
    lt = label_tokens(labels)
    total = sum(r[2] for r in rows)
    matched = sum(r[2] for r in rows if is_tracked(r[0], lt))
    unmatched = [r for r in rows if not is_tracked(r[0], lt)]
    return {"chain": chain, "protocols": len(rows), "total_usd": total, "matched_usd": matched, "share": matched / total if total else 0.0,
            "matched_count": len(rows) - len(unmatched), "largest_unmatched": unmatched[:top]}
