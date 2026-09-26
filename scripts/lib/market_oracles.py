"""
Who can move the price a Morpho market trusts? Pure logic for scripts/check_morpho_market_oracles.py.

A Morpho market's oracle is immutable, but the FEEDS it reads are often proxies (EIP-1967 or a Chainlink
EACAggregatorProxy) whose admin can swap the implementation, or the aggregator, in one transaction. That
admin, not the vault curator and not Morpho Blue, is the party that can misprice a market's collateral.
No RPC here so it is testable without a chain.
"""

FEED_FIELDS = ("baseFeedOne", "baseFeedTwo", "quoteFeedOne", "quoteFeedTwo")


def market_feeds(market: dict) -> list:
    """Distinct non-null feed addresses of a market's Morpho Chainlink-style oracle (V1 and V2 share the
    field names). Empty for a custom oracle, whose own address is then the thing to inspect."""
    data = (market.get("oracle") or {}).get("data") or {}
    out = []
    for f in FEED_FIELDS:
        a = (data.get(f) or {}).get("address")
        if a and a.lower() not in {x.lower() for x in out}:
            out.append(a)
    return out


def controller_of(read: dict):
    """The address that ultimately holds upgrade or repoint authority over one feed read: the ProxyAdmin's
    owner when the admin is a ProxyAdmin, else the admin itself (an EOA or Safe used directly), else the
    feed's own owner() (Chainlink's proxy pattern), else None (no admin found, NOT proven immutable)."""
    return read.get("admin_owner") or read.get("admin") or read.get("feed_owner")


def concentration(rows: list) -> list:
    """`rows`: one dict per (market, feed) with chain, market, supplyUsd, controller, controller_class.
    Groups by (chain, controller) and counts each market once per controller, so a market with two
    feeds behind the same admin is not double-counted. Sorted by supply descending."""
    groups = {}
    for r in rows:
        c = r.get("controller")
        if not c:
            continue
        g = groups.setdefault((r["chain"], c), {"chain": r["chain"], "controller": c, "class": r.get("controller_class"), "markets": {}})
        g["markets"][r["market"]] = r["supplyUsd"] or 0.0
    out = [{"chain": g["chain"], "controller": g["controller"], "class": g["class"], "markets": len(g["markets"]),
            "supplyUsd": sum(g["markets"].values())} for g in groups.values()]
    return sorted(out, key=lambda x: -x["supplyUsd"])


def weak_controller(controller_class: str) -> bool:
    """True for a controller that is one key or a small quorum: a bare EOA, or a Safe with threshold <= 2.
    A contract of unknown shape is NOT called weak here (it is unclassified, not proven strong)."""
    if not controller_class:
        return False
    if controller_class == "EOA":
        return True
    if controller_class.endswith("Safe"):
        try:
            return int(controller_class.split("-of-")[0]) <= 2
        except ValueError:
            return False
    return False


def group_by_signers(safe_sets: dict) -> dict:
    """`safe_sets`: {(chain, address): (threshold, frozenset(lowercase owners))} for every Safe controller read.
    Groups Safes on any chain that share the SAME threshold and SAME signer set: one committee, many chains.
    Returns {(threshold, owners): [(chain, address), ...]}."""
    out = {}
    for key, shape in safe_sets.items():
        out.setdefault(shape, []).append(key)
    return out


def path_split(rows: list, members: set, total_usd: float) -> dict:
    """How markets depend on a controller group (`members` = set of (chain, controller address)). A market's LIVE price
    path is its direct feeds or, for a MetaOracleDeviationTimelock, its primary oracle; the backup oracle only takes over
    after a deviation, a challenge and a timelock. A market counts once: 'live' if any live-path feed is in the group,
    else 'backup_only'. Returns market counts and supply for live, backup_only, and all, plus the share of `total_usd`."""
    live, backup = {}, {}
    for r in rows:
        if (r["chain"], r.get("controller")) not in members:
            continue
        (backup if r["kind"].startswith("backupOracle") else live)[r["market"]] = r["supplyUsd"] or 0.0
    only_backup = {m: u for m, u in backup.items() if m not in live}
    allm = {**live, **only_backup}
    usd = lambda d: sum(d.values())  # noqa: E731
    return {"live": (len(live), usd(live)), "backup_only": (len(only_backup), usd(only_backup)),
            "all": (len(allm), usd(allm)), "live_share": usd(live) / total_usd if total_usd else 0.0,
            "all_share": usd(allm) / total_usd if total_usd else 0.0}
