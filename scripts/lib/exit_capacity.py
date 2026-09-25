"""A timelock protects depositors only if they can leave before a queued change takes effect.

ADDED 2026-09-25 (backlog item 10, `data/finding_2026-09-20-competitor-gaps-and-morpho-vault-layer.md:370-397`
"eighth pass": "no product was found that puts a DeFi vault's timelock next to its exit capacity"). The
research and methodology already existed (`chains/ethereum-l1/scripts/sweep_exit_capacity.py`, a 167-vault
market-wide sweep against Morpho's public API) but were never scoped to this oracle's own tracked targets or
turned into a disclosed field. This module holds the pure classification logic; `scripts/check_exit_capacity.py`
does the live API read for the 9 Morpho vaults `scripts/lib/controller_concentration.py` already tracks.

Off-chain, disclosed only -- same precedent as `l1CappedComposite` and the controller-concentration report:
no `AuthorityScore` field added, `timelockScore` unchanged. This measures a DIFFERENT thing than
`timelockScore` (which asks "is there a real delay before an authority-changing action executes") --
exit capacity asks "if that delay's queued change turns out to be malicious, how much of a depositor's
money can actually leave before it takes effect". A long timelock with thin exit liquidity is a shorter
real protection window than its own duration suggests.
"""
DAY = 86400


def exit_share(tvl_usd, instant_liquidity_usd, in_kind_liquidity_usd=0.0):
    """Fraction of a vault's deposits that could leave before a queued timelocked change takes effect.
    `in_kind_liquidity_usd` (Morpho V2's forceDeallocatableLiquidityUsd) adds to the instant share; 0.0
    for V1 vaults, which have no in-kind exit. Returns None if tvl_usd is not positive (nothing to divide
    by, not a 0% finding)."""
    if not tvl_usd or tvl_usd <= 0:
        return None
    return min(1.0, (instant_liquidity_usd + in_kind_liquidity_usd) / tvl_usd)


def exit_band(share):
    """"<5%", "5-20%", "20-50%" or ">=50%" -- the same bands `sweep_exit_capacity.py`'s own market-wide
    sweep used, so a result here is directly comparable to that research's published figures."""
    if share is None:
        return "unknown"
    if share < 0.05:
        return "<5%"
    if share < 0.20:
        return "5-20%"
    if share < 0.50:
        return "20-50%"
    return ">=50%"


def timelock_bucket(seconds):
    """A short label for a timelock duration in seconds, matching sweep_exit_capacity.py's own buckets."""
    if seconds is None:
        return "unknown"
    if seconds == 0:
        return "0 (no delay)"
    if seconds < 3 * DAY:
        return "under 3d"
    if seconds <= 3 * DAY + 300:
        return "3d"
    if seconds < 7 * DAY:
        return "3d to 7d"
    if seconds == 7 * DAY:
        return "7d"
    return "over 7d"


def is_thin_behind_a_short_delay(seconds, share):
    """True when a timelock of about 3 days or less (Morpho's own most common listing tier) sits in
    front of a vault whose exit capacity is under 20% of deposits -- the specific combination the
    research's eighth pass flagged as a real, sizeable protection-window gap (44 of 167 vaults
    market-wide, $1,910M, 32% of the researched sample's deposits). Not a claim that any change is
    queued or pending -- a sizing at one instant, same limit the source research states."""
    if seconds is None or share is None:
        return False
    return seconds <= 3 * DAY + 300 and share < 0.20
