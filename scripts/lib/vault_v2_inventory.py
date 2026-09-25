"""Disclosed-only inventory of Morpho Vault V2 targets on this oracle's own tracked ecosystems.

ADDED 2026-09-25 (roadmap item 10 continuation, "voit large" round 2 -- see
`data/finding_2026-09-25-vault-v2-scoring-scope.md` for why V2 is NOT scored: per-function timelocks,
permanently abdicated exit gates and a non-uniform curator model (Safe, bare EOA, or another contract,
confirmed to vary vault by vault) are a genuine new calibration decision, not a mechanical extension of
the V1 owner/curator/guardian formula already used elsewhere in this project). This module holds the
pure classification logic only -- no score is computed here or anywhere downstream of it.

Live discovery (2026-09-25) found the real gap is far larger than the $110M the 20/09 research quoted
for Monad alone: **$2.87B across 27 V2 vaults of $20M or more on 4 of this oracle's own tracked
ecosystems** (Ethereum L1, Robinhood Chain, Monad, Tempo -- Morpho's API does not index Plasma; Arbitrum
and Hyperliquid have no V2 vault above $20M today). Off-chain, disclosed only -- same precedent as
`l1CappedComposite`, the controller-concentration report and the exit-capacity check: no
`AuthorityScore` field, no score, no on-chain push.
"""


def classify_holder(code_len, is_safe):
    """"safe" (a real Gnosis Safe, is_safe True), "eoa" (code_len == 0), "contract" (code but not a
    Safe) or "unread" (code_len is None). Never a score input -- a fact about WHAT kind of authority
    holds the role, not how strong it is."""
    if code_len is None:
        return "unread"
    if is_safe:
        return "safe"
    if code_len == 0:
        return "eoa"
    return "contract"


def format_holder(kind, safe_shape=None):
    """A short label for one owner/curator holder, e.g. "3-of-5 Safe", "bare EOA", "contract (not a Safe)"."""
    if kind == "safe" and safe_shape:
        threshold, n = safe_shape
        return f"{threshold}-of-{n} Safe"
    return {"safe": "Safe (shape unread)", "eoa": "bare EOA", "contract": "contract (not a Safe)", "unread": "unread"}[kind]


# The 3 security-relevant V2 functions this project's own source research
# (data/finding_2026-09-20-competitor-gaps-and-morpho-vault-layer.md) identified as the ones that
# actually reach depositor principal: adding/removing an adapter (where funds can be allocated) and
# abdicating a gate (a one-way, permanent action). Reported, never scored.
DISCLOSED_TIMELOCK_FUNCTIONS = ("addAdapter", "removeAdapter", "abdicate")


def timelock_summary(timelocks_by_function):
    """{function_name: duration_seconds_or_None} restricted to DISCLOSED_TIMELOCK_FUNCTIONS, for the
    functions this vault's own API data actually reports (a function absent from the dict is not the
    same as a function at delay 0 -- not guessed, reported as 'unread')."""
    return {fn: timelocks_by_function.get(fn) for fn in DISCLOSED_TIMELOCK_FUNCTIONS}
