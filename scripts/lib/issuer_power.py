"""What a token's ISSUER can do to the balances this oracle's own tracked vaults hold in it.

ADDED 2026-09-26 (backlog item 15, `data/finding_2026-09-20-competitor-gaps-and-morpho-vault-layer.md:499-
519,717-719`: "An issuer-power tag per vault asset (freeze, seize, pause, upgrade, and who holds the
roles)... Cheap, because verified ABIs are public"). That research was a market-wide sweep
(`chains/ethereum-l1/scripts/sweep_asset_authority.py`, 500+ assets) never scoped to what THIS oracle
actually tracks. This module holds the pure classification logic for that scoped version:
`scripts/check_issuer_power.py` reads the underlying asset of each of the 9 tracked Morpho V1 vaults
(only 4 distinct tokens: USDC on Base, USDT and USDC on Ethereum L1, AUSD on Monad/Ethereum L1) via
Blockscout's verified ABI, the same function-name families the source research already used.

Off-chain, disclosed only -- same precedent as every other extension built this week
(`l1CappedComposite`, controller-concentration, exit-capacity, the Vault V2 inventory): no
`AuthorityScore` field, no `adminKeyScore`/`multisigScore`/`timelockScore` computed. A vault's owner/
curator/guardian score says nothing about the token it holds -- this is a different, additive risk
surface, disclosed the same way as the others, not folded into any existing score.

Function names are a signal, not a proof (the source research's own limit, restated here): a function
named `pause` is reported present; whether it is gated `onlyOwner`, `onlyRole`, or open to anyone is
NOT read by this module (that needs `sweep_token_function_guards.py`'s deeper source-modifier read,
out of scope for this pass -- see the module docstring's own "what this is not" section).

EXTENDED same day: `data/finding_2026-09-26-issuer-power-tracked-assets.md` flagged AUSD as a real gap
in `KNOWN_CONTROLLER_GETTERS` -- it isn't OpenZeppelin AccessControl (no RoleGranted/RoleRevoked
events to replay), it's Agora's own bespoke role registry with direct `address[]` getters
(`getFreezerRoleMembers()` etc.) -- no event replay needed, a live call resolves the holder set
outright. `KNOWN_ROLE_MEMBER_GETTERS` below covers that family."""

FREEZE_PATTERN_WORDS = ("blacklist", "blocklist", "denylist", "freeze", "frozen", "banaddress", "blockaccount")
SEIZE_PATTERN_WORDS = ("wipe", "destroyblack", "seize", "clawback", "forcetransfer", "forcedtransfer", "confiscate", "forceburn")
PAUSE_PATTERN_WORDS = ("pause",)
UPGRADE_PATTERN_PREFIXES = ("upgradeto",)

# Zero-argument, address-returning controller getters this project already knows to check (same list
# sweep_asset_authority.py uses) -- a token exposing one of these names controllers of that name.
KNOWN_CONTROLLER_GETTERS = ("owner", "admin", "blacklister", "pauser", "masterMinter", "assetProtectionRole", "supplyController", "governance", "freezer", "guardian")

# Zero-argument, address[]-returning role-registry getters (Agora's AUSD naming convention -- see the
# module docstring's "EXTENDED" note). A token exposing one of these names has that role's FULL member
# list readable directly, no event-log replay needed.
KNOWN_ROLE_MEMBER_GETTERS = ("getFreezerRoleMembers", "getPauserRoleMembers", "getMinterRoleMembers", "getBurnerRoleMembers", "getBridgeMinterRoleMembers", "getBridgeBurnerRoleMembers", "getRateLimitManagerRoleMembers", "getAccessControlManagerRoleMembers")


def _matches_any(name, words):
    lname = name.lower()
    return any(w in lname for w in words)


def classify_functions(function_names):
    """{"freeze": [...], "seize": [...], "pause": [...], "upgrade": [...]} -- state-changing function
    names (not view/pure) matched by name against each family's known vocabulary, each list capped at
    4 (a signal that the family exists and a few examples, not an exhaustive audit)."""
    freeze = sorted(n for n in function_names if _matches_any(n, FREEZE_PATTERN_WORDS))
    seize = sorted(n for n in function_names if _matches_any(n, SEIZE_PATTERN_WORDS))
    pause = sorted(n for n in function_names if _matches_any(n, PAUSE_PATTERN_WORDS))
    upgrade = sorted(n for n in function_names if n.lower().startswith(UPGRADE_PATTERN_PREFIXES))
    return {"freeze": freeze[:4], "seize": seize[:4], "pause": pause[:4], "upgrade": upgrade[:4]}


def has_any_restrictive_power(families):
    """True if any of freeze/seize/pause was found (upgrade alone -- an implementation change, not a
    direct balance action -- is reported separately, not folded into this headline flag, matching the
    source research's own "freeze, seize or pause" summary line)."""
    return bool(families["freeze"] or families["seize"] or families["pause"])


def classify_controller(code_len, is_safe, safe_shape=None):
    """A short label for one controller address: "EOA", "Safe t-of-n", or "contract (N bytes)".
    Mirrors sweep_asset_authority.py's own kind() classifier so a result here is directly comparable
    to that research's published figures."""
    if code_len is None:
        return "unread"
    if code_len == 0:
        return "EOA"
    if is_safe and safe_shape:
        threshold, n = safe_shape
        return f"{threshold}-of-{n} Safe"
    return f"contract ({code_len}B)"
