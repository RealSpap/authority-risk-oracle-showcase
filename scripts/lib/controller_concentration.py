"""Controller-level concentration over this oracle's own tracked Morpho V1 vaults.

ADDED 2026-09-25 (backlog item 2, `data/finding_2026-09-20-competitor-gaps-and-morpho-vault-layer.md:689-691`:
"A signal per controller (threshold, signer overlap between its roles, number of vaults and chains it
governs) would follow the same convention as the cross-exposure score"). GitHub tracker cards #9/#10 (`Spap
- research & outreach tracker`) list this as "retained" and note the concrete number that motivated it: two
curator Safes were found (2026-09-20, over the WIDER Morpho ecosystem, via
`chains/ethereum-l1/scripts/analyze_controllers.py`) to govern 46% of curated deposits. That script is prior
art -- a one-off offline analysis of a JSON dump from `sweep_morpho_vault_owners.py`, grouping raw owner/
curator addresses over vaults the oracle does NOT track. This module answers a narrower, oracle-scoped
question instead: of the vaults THIS oracle actually tracks and publishes scores for, who really controls
them, and does any one controller hold more than one role (owner/curator/guardian) on the SAME vault with the
SAME signers -- the concrete pattern already found and scored per-vault (Gauntlet USDC Prime: all three roles,
same 7 signers) but never rolled up across the tracked set as its own signal.

Off-chain only, same precedent as `l1CappedComposite` (METHODOLOGY.md): the deployed `AuthorityScore` struct
has no field for this, and adding one is a contract migration, a separate, bigger decision. This is a
read-only report over already-tracked, already-scored targets -- it changes no published score.

Strictly re-reads owner()/curator()/guardian() live on every call (no caching of role addresses across runs);
Safe resolution goes through safe_owners_and_threshold(..., check_modules=False) since this asks "who signs",
same reasoning check_cross_ecosystem_overlap.py's own module docstring gives for the same choice.
"""
import collections

TRACKED_MORPHO_VAULTS = [
    # (ecosystem, rpc, label, vault address, roles to read)
    ("ethereum-l1", "https://ethereum-rpc.publicnode.com", "Morpho V1: Adpend USDC", "0x55555815a5595991C3A0Ff119B59AEF6C8B55555", ("owner", "curator")),
    ("ethereum-l1", "https://ethereum-rpc.publicnode.com", "Morpho V1: 1337 USDC", "0x94643e86aa5E38DDAc6c7791C1297f4E40cD96c1", ("owner",)),
    ("ethereum-l1", "https://ethereum-rpc.publicnode.com", "Morpho V1: Steakhouse USDT (Ethereum L1)", "0xbEef047a543E45807105E51A8BBEFCc5950fcfBa", ("owner", "curator", "guardian")),
    ("ethereum-l1", "https://ethereum-rpc.publicnode.com", "Morpho V1: Steakhouse USDC (Ethereum L1)", "0xBEEF01735c132Ada46AA9aA4c54623cAA92A64CB", ("owner", "curator", "guardian")),
    ("base", "https://mainnet.base.org", "Morpho V1: Gauntlet USDC Prime (Base)", "0xeE8F4eC5672F09119b96Ab6fB59C27E1b7e44b61", ("owner", "curator", "guardian")),
    ("base", "https://mainnet.base.org", "Morpho V1: Spark USDC Vault (Base)", "0x7BfA7C4f149E7415b73bdeDfe609237e29CBF34A", ("curator", "guardian")),  # owner: unresolved bespoke contract, see chains/base-ecosystem/scorers.py
    ("base", "https://mainnet.base.org", "Morpho V1: Steakhouse USDC (Base)", "0xbeeF010f9cb27031ad51e3333f9aF9C6B1228183", ("owner", "curator", "guardian")),
    ("base", "https://mainnet.base.org", "Morpho V1: Grove x Steakhouse USDC High Yield (Base)", "0xBeEf2d50B428675a1921bC6bBF4bfb9D8cF1461A", ("owner", "curator", "guardian")),
    ("monad", "https://rpc.monad.xyz", "Morpho V1: Grove x Steakhouse High Yield AUSD (Monad)", "0x32841A8511D5c2c5b253f45668780B99139e476D", ("owner", "curator", "guardian")),
]

MORPHO_API = "https://blue-api.morpho.org/graphql"


def read_vault_roles(w3, vault, roles, read_address_getter):
    """{role: address_or_None} for the roles this vault is known to expose. A revert (None from
    read_address_getter) means that role getter doesn't apply here -- already known per-vault
    (e.g. Spark's owner() is a bespoke contract, not read as a role at all), not re-guessed."""
    return {role: read_address_getter(w3, vault, role) for role in roles}


def build_controller_registry(vault_rows, safe_owners_and_threshold_fn, w3_by_ecosystem):
    """vault_rows: [(ecosystem, label, vault, {role: address})]. Returns {controller_addr_lower:
    {"roles_by_vault": {(ecosystem, label): {role: bool}}, "safe_by_ecosystem": {ecosystem:
    (owners, threshold) or False}, "vaults": set(), "ecosystems": set()}} -- keyed by the RAW
    controller address only, so a literal same-address controller reused across chains
    (Steakhouse's owner and curator Safes, confirmed 2026-09-25 to be the SAME addresses on
    Ethereum L1, Base AND Monad) merges into one controller entry automatically.

    IMPORTANT, found live 2026-09-25 while building this: the SAME Safe address does NOT
    necessarily carry the SAME owner set or threshold on every chain it is deployed to --
    Steakhouse's owner Safe reads 5-of-10 on Ethereum L1, 5-of-9 on Base and 5-of-8 on Monad; its
    curator Safe reads 2-of-7 on Ethereum L1 and Monad but 2-of-6 on Base. A Safe's address is
    deterministic (CREATE2) but its owners can be changed per-chain after deployment via
    addOwner/removeOwner/swapOwner independently on each chain -- there is no cross-chain sync.
    Reading a controller's Safe config ONCE and applying it to every chain it appears on (the
    first version of this function did exactly that) would silently misreport its true signer
    count and threshold on every chain but the one read first. Resolved per (ecosystem, address)
    instead, never assumed shared."""
    registry = collections.defaultdict(lambda: {"roles_by_vault": {}, "safe_by_ecosystem": {}, "vaults": set(), "ecosystems": set()})
    for ecosystem, label, vault, roles in vault_rows:
        for role, addr in roles.items():
            if not addr or int(addr, 16) == 0:
                continue
            key = addr.lower()
            c = registry[key]
            c["roles_by_vault"].setdefault((ecosystem, label), {})[role] = True
            c["vaults"].add((ecosystem, label))
            c["ecosystems"].add(ecosystem)
            if ecosystem not in c["safe_by_ecosystem"]:
                w3 = w3_by_ecosystem[ecosystem]
                c["safe_by_ecosystem"][ecosystem] = safe_owners_and_threshold_fn(w3, addr) or False  # False = confirmed not a Safe on THIS chain (bare EOA or unresolved)
    return dict(registry)


def same_signers_across_roles(roles_present):
    """True only when a controller holds 2+ roles that were independently CONFIRMED to share the
    identical owner set -- the caller passes that confirmation in per vault (this module doesn't
    re-derive it; each scorer already does, per-vault, and this rolls that finding up rather than
    recomputing it a second way)."""
    return len(roles_present) >= 2


def config_varies_across_chains(safe_by_ecosystem):
    """True if this controller's Safe threshold/owner-count is not identical on every chain it
    was resolved on -- same address, independently reconfigured per chain (see
    build_controller_registry's docstring). None entries (unresolved this run) are ignored, not
    treated as a mismatch."""
    shapes = {(s[1], len(s[0])) for s in safe_by_ecosystem.values() if s}
    return len(shapes) > 1


def fold_in_vault_v2_reach(registry, v2_rows):
    """ADDED 2026-09-26, closes the gap `data/finding_2026-09-25-vault-v2-inventory.md` flagged as
    "not yet folded into the controller-concentration tool itself": 6 Steakhouse-family Vault V2
    targets resolve, via `check_vault_v2_inventory.read_holder()`'s one-hop VaultV2Supervisor chase,
    to the exact same Steakhouse Safe already tracked here as owner of 4 V1 vaults -- so that
    controller's TRUE reach ($818.9M) was invisible in a report scoped only to V1.

    `v2_rows`: [(controller_addr_lower, extra_tvl_usd, vault_label)], computed by the caller from
    Vault V2's own live owner-resolution (this module never re-derives that itself). Adds a purely
    informational `"v2_reach"` annotation to any controller ALREADY present in the V1 registry --
    never merged into `vault_count`/`tvl`/`ecosystems`, which stay scoped to the oracle's actually
    tracked/scored V1 vaults (Vault V2 remains disclosed-only, no score, per
    `data/finding_2026-09-25-vault-v2-scoring-scope.md`). A controller that reaches ONLY V2 vaults,
    with no V1 role at all, is out of scope for this report -- that's the V2 inventory's own job."""
    for addr_lower, extra_tvl, vault_label in v2_rows:
        if addr_lower not in registry:
            continue
        entry = registry[addr_lower].setdefault("v2_reach", {"tvl": 0.0, "vaults": []})
        entry["tvl"] += extra_tvl
        entry["vaults"].append(vault_label)
    return registry


def rank_controllers(registry, tvl_by_vault):
    """[(controller_addr, info, vault_count, chain_count, roles_on_any_single_vault, tvl_governed)],
    sorted by vault_count desc then tvl_governed desc. `roles_on_any_single_vault` is the largest
    number of distinct roles this controller holds on any ONE of its vaults (2 or 3 = same entity
    wears multiple hats on that vault, the pattern this module exists to surface)."""
    out = []
    for addr, info in registry.items():
        vault_count = len(info["vaults"])
        chain_count = len(info["ecosystems"])
        max_roles_one_vault = max((len(roles) for roles in info["roles_by_vault"].values()), default=0)
        tvl = sum(tvl_by_vault.get(v, 0.0) for v in info["vaults"])
        out.append((addr, info, vault_count, chain_count, max_roles_one_vault, tvl))
    out.sort(key=lambda row: (-row[2], -row[5]))
    return out
