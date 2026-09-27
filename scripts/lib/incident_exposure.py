"""Pure logic for scripts/incident_exposure.py: what would a documented incident's authority configuration score here, and how many published targets sit at or below it?

The replay uses ONLY the shared Safe-rooted convention of scripts/lib/scorers.py (`_safe_rooted_scores`: threshold and owner count, no module, no guard, no timelock) and the standard
composite, so nothing here is a new formula. It answers "how exposed is what we track", not "would the score have predicted the incident":
data/research_2026-09-21-authority-incidents-evidence-table.md explains why the second question cannot be tested (no sample of protocols that were not hit).
"""
from lib.scorers import _composite, _safe_rooted_scores

# (label, threshold, owners): only incidents whose Safe threshold the source states (Bybit's owner count is an on-chain read); the timelock of 0 is this project's reading of a plain Safe, not a statement of the sources.
INCIDENTS = (
    ("Radiant Capital, 2024-10-16 ($53M): Safe 3-of-11", 3, 11),
    ("WazirX, 2024-07-18 ($235M): Safe 4-of-6", 4, 6),
    ("Bybit, 2025-02-21 ($1.46B): Safe 3-of-6", 3, 6),
    ("Humanity Protocol Ethereum, 2026-06 ($32M to $36M): Safe 3-of-6", 3, 6),
    ("Humanity Protocol BNB Chain, 2026-06: Safe 3-of-5", 3, 5),
)
LOWEST_BAND = 10  # composite 10 or less: mostly bare-key roots (METHODOLOGY.md: a bare EOA adminKeyScore is 2 to 10), plus a few placeholder or partial scores


def replay(threshold, owners):
    a, m, t = _safe_rooted_scores(threshold, owners)
    return {"adminKeyScore": a, "multisigScore": m, "timelockScore": t, "compositeScore": _composite(a, m, t)}


def at_or_below(rows, composite):
    """Number of published rows whose composite is <= `composite`."""
    return sum(1 for r in rows if r["compositeScore"] <= composite)


def summarize(rows):
    """Counts over published rows (dicts with the score dimensions)."""
    n = len(rows)
    comps = sorted(r["compositeScore"] for r in rows)
    return {"targets": n,
            "no_delay": sum(1 for r in rows if r["timelockScore"] == 0),
            "lowest_band": sum(1 for r in rows if r["compositeScore"] <= LOWEST_BAND),
            "median_composite": comps[n // 2] if n else None}
