"""
Cross-ECOSYSTEM signer-overlap detection -- the project-wide gap this
project's own audit named: scripts/lib/signer_overlap.py computes overlap only
WITHIN Robinhood Chain's own tracked targets (since 2026-09-20 it also applies a
hand-set, dated "cross_ecosystem" flag to a group, but it never compares against
another chain). This module checks
whether a root signer (or an entire Safe, via identical address) tracked on
ONE ecosystem also appears on ANOTHER -- e.g. the same person sitting on
both a Robinhood Chain Safe and an Ethereum L1 Safe this project separately
tracks, or literally the same Safe address redeployed via CREATE2 on more
than one chain (a real, documented risk pattern -- this project's sister
research, multisig-overlap, found exactly this for ether.fi,
Curve, Aave V3 and others: a "diversified" multi-chain deployment sharing
one key set is not diversified against key compromise at all).

Still deliberately NOT called from any live score_all() pipeline: coupling one
chain's own live, weekly-cron score_all() to another chain's RPC would let a
flaky RPC degrade an unrelated push. Runnable standalone instead
(scripts/check_cross_ecosystem_overlap.py) so this can be re-checked as
more targets/ecosystems get added, without becoming a dependency of the
live push. (An earlier version of this docstring also said Ethereum L1 and
Base were not deployed, so no live crossExposureScore existed there to feed;
that reason is obsolete, Ethereum L1, Arbitrum, Base, Tempo, Plasma and Monad
are all deployed oracles now.)

How this relates to the published scores (CORRECTED 2026-09-20, the
crossExposureScore convention decision in METHODOLOGY.md): a cross-ecosystem
overlap IS folded into crossExposureScore on every EVM ecosystem, as a flat 80,
without any scorer calling a second chain. Each ecosystem's scorer compares the
owner set it just read on its own chain against a hardcoded, dated snapshot of
the other chain's committee; Robinhood Chain instead carries a hand-set,
dated "cross_ecosystem" flag on the group in scripts/lib/signer_overlap.py.
The registries below are the inputs to the sweep that FINDS those overlaps,
they are not what the scorers read, so adding or removing a group here changes
no score by itself, and a snapshot or flag in a scorer goes stale until someone
re-runs the sweep and updates it. Not covered: Solana, Hyperliquid and Zcash
(signer formats not bridged, or not added to a registry yet).
"""
import os
import sys

from web3 import Web3

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from web3_utils import RpcUnavailable  # noqa: E402


def group_root_signers(w3, group: dict, safe_owners_fn, incomplete_out: list = None) -> set:
    """Resolve one group's root signer set. Reuses the exact GROUPS shape
    already used by scripts/lib/signer_overlap.py (targets/known_eoa/safes),
    so a group dict written for either module works in both -- pass in
    `safe_owners_fn` (e.g. web3_utils.safe_owners_and_threshold, or
    signer_overlap._safe_owners for its Safe-or-bespoke-multisig fallback)
    rather than importing one here, so this module has no hard dependency
    on either caller's specific owner-resolution strategy.

    ADDED 2026-09-22: `safe_owners_fn` can now RAISE instead of returning None on a persistent RPC
    failure (web3_utils.safe_owners_and_threshold does, since a bare None there would be
    indistinguishable from a confirmed 'not a Safe'). This module deliberately stays agnostic about
    which exception type that is for MOST failures -- isolating a per-safe failure like
    `safe_score()` does for a per-target one elsewhere in this project, printed and skipped rather
    than crashing the rest of this group (never mind the caller's whole multi-group, multi-ecosystem
    sweep) over one bad read. The one exception it DOES recognize by name is RpcUnavailable
    (web3_utils's own network-failure signal, which every real safe_owners_fn passed to this
    function in practice already raises): unlike this sweep's unconditional, no-consequence output
    (never feeds a live score, see this module's own header), silently returning a SMALLER signer
    set here means a real cross-ecosystem overlap can be missed and never manually flagged --
    caught here specifically so a caller can pass `incomplete_out` (a list this function appends
    `(safe_addr, exception)` to) and print an honest summary of which groups' results might be
    incomplete, instead of relying on a human noticing one SKIPPED line among many."""
    signers = set(Web3.to_checksum_address(a) for a in group.get("known_eoa", []))
    for safe_addr in group.get("safes", []):
        try:
            owners = safe_owners_fn(w3, safe_addr)
        except RpcUnavailable as e:
            print(f"group_root_signers(): NETWORK FAILURE on {safe_addr} -- {e} -- this group's signer set may be INCOMPLETE")
            if incomplete_out is not None:
                incomplete_out.append((safe_addr, e))
            continue
        except Exception as e:
            print(f"group_root_signers(): SKIPPED {safe_addr} -- {type(e).__name__}: {e}")
            continue
        if owners:
            if isinstance(owners, tuple):  # (owners, threshold) shape
                owners = owners[0]
            signers.update(Web3.to_checksum_address(o) for o in owners)
    return signers


def find_cross_ecosystem_overlaps(ecosystem_groups: dict) -> dict:
    """`ecosystem_groups`: {(ecosystem, group_key): signer_set}.
    Returns {signer: {(ecosystem, group_key), ...}} for every signer that
    appears in groups from MORE THAN ONE ecosystem. Pure set logic, no RPC --
    testable without a live chain (see scripts/lib/tests/test_cross_ecosystem_overlap.py)."""
    registry = {}
    for (ecosystem, key), signers in ecosystem_groups.items():
        for s in signers:
            registry.setdefault(s, set()).add((ecosystem, key))
    return {signer: groups for signer, groups in registry.items() if len({eco for eco, _ in groups}) > 1}


def find_identical_safe_addresses(ecosystem_safes: dict) -> dict:
    """`ecosystem_safes`: {(ecosystem, group_key): safe_address}.
    Returns every Safe address tracked, under that SAME address, on more
    than one ecosystem -- the ether.fi/Curve/Aave-style "same Safe
    redeployed via CREATE2 on N chains" pattern, distinct from (and
    stronger than) a mere shared-signer overlap: one compromised key set
    controls every chain's deployment simultaneously, not just one.

    Despite the name, this is pure address-identity logic with no
    Safe-specific behavior -- ADDED 2026-09-19: `scripts/check_
    cross_ecosystem_overlap.py` now also calls this on `known_eoa`
    addresses (the Curve/Monad-Robinhood finding: the identical bare EOA,
    not a Safe at all, reused across two chains) under a separate report
    section, rather than adding a redundant second function."""
    registry = {}
    for (ecosystem, key), addr in ecosystem_safes.items():
        registry.setdefault(Web3.to_checksum_address(addr), set()).add((ecosystem, key))
    return {addr: groups for addr, groups in registry.items() if len({eco for eco, _ in groups}) > 1}


def find_subset_committees(ecosystem_groups: dict, min_size: int = 2) -> list:
    """`ecosystem_groups`: {(ecosystem, group_key): signer_set}, the same
    input `find_cross_ecosystem_overlaps` takes.

    ADDED 2026-09-19, closing a real gap `find_cross_ecosystem_overlaps`
    left open: that function flags any INDIVIDUAL signer appearing in 2+
    ecosystems, which is enough to notice "these overlap" but not to
    characterize HOW MUCH -- the Monad/Robinhood Morpho vault finding (a
    full 6-of-6 curator committee entirely contained in a 7-signer
    Robinhood committee) had to be reasoned about by hand from that
    function's per-signer output. This does the containment check
    directly: for every pair of groups from DIFFERENT ecosystems, checks
    whether one's signer set is a subset of the other's (including the
    equal-sets case, already caught differently by an exact-signer-overlap
    reading of `find_cross_ecosystem_overlaps` but surfaced here in the
    same "containment" framing for consistency).

    Returns a list of dicts, each `{"smaller": (ecosystem, key), "larger":
    (ecosystem, key), "shared": signer_set}`, sorted with the most
    complete containments (smallest smaller-group, i.e. the strongest
    "your ENTIRE committee is inside theirs" cases) first. `min_size`
    excludes trivial 0-1-signer groups (an empty or single-EOA group is
    "contained in" almost anything, not a meaningful finding) -- default 2,
    matching this project's own judgment call in the Monad finding pass
    (a 1-signer bare-EOA group correctly gets its own dedicated identical-
    EOA check above instead)."""
    results = []
    items = [(k, v) for k, v in ecosystem_groups.items() if len(v) >= min_size]
    for i, (key_a, signers_a) in enumerate(items):
        eco_a = key_a[0]
        for key_b, signers_b in items[i + 1:]:
            eco_b = key_b[0]
            if eco_a == eco_b:
                continue
            if signers_a <= signers_b:
                results.append({"smaller": key_a, "larger": key_b, "shared": signers_a})
            elif signers_b <= signers_a:
                results.append({"smaller": key_b, "larger": key_a, "shared": signers_b})
    results.sort(key=lambda r: len(r["shared"]))
    return results


# Ethereum L1, Arbitrum and Base don't have their own signer_overlap.py-style
# GROUPS registry yet (each is a handful of targets in one scorers.py file,
# not Robinhood Chain's ~20-group structure) -- declared here in the same
# shape instead, so this module can check them against Robinhood Chain's
# existing GROUPS (scripts/lib/signer_overlap.py) without duplicating that
# structure.
#
# UPDATED 2026-09-17 (this project's own second bug-hunt-adjacent pass, same
# day): Ethereum L1's own "ethena" group only listed 1 of the 5 targets this
# project now tracks under the SAME Safe (0x3b0aaf6e...) -- expanded to all
# 5 (see chains/ethereum-l1/scorers.py's own `_apply_cross_exposure`
# `_rootGroup` = "ethena-safe-0x3b0aaf6e" grouping, added earlier the same
# day, for the WITHIN-ecosystem version of this same finding). Arbitrum
# added for the first time -- it didn't exist as a scored ecosystem when this
# module was first written. Base's Aave guardian Safe added after a live
# check found it is the EXACT SAME 9-owner, 5-of-9 committee as Arbitrum's
# own Aave guardian Safe (different Safe address per chain, IDENTICAL owner
# set -- confirmed live, the same "CREATE2-redeployed shared committee"
# pattern this module's own docstring describes as this project's sister
# research's finding for ether.fi/Curve/other Aave deployments, now found
# live in THIS project's own tracked targets for the first time). Ethereum
# L1's own Aave PROTOCOL_GUARDIAN (4-of-7) was checked against this set too
# and confirmed to share ZERO signers -- a genuinely separate, older,
# mainnet-only governance body, not the same committee.
# CORRECTED 2026-09-19: "mainnet-only" was wrong. That 4-of-7 committee is also the
# Aave EMERGENCY_ADMIN on Arbitrum, Base, Plasma and Monad (a different Safe address per
# chain, the SAME 7 owners, verified by hand on all five chains) -- a second cross-chain
# committee, still with zero overlap with the 9-signer GOVERNANCE_GUARDIAN set above.
# See the `aave_protocol_guardian` groups below.
# NOTE 2026-09-20 (crossExposureScore convention decision, METHODOLOGY.md): the
# "WITHIN-ecosystem version" wording above (about chains/ethereum-l1/scorers.py's
# `_apply_cross_exposure` grouping) is stale. That function is no longer purely
# within-Ethereum-L1: besides the `_rootGroup` count it now folds a cross-ecosystem
# committee match into crossExposureScore as min(within-L1 score, 80), through the
# `_crossEcosystem` flag its scorers set (the 9-signer PayloadsController.guardian()
# committee, the 7-signer PROTOCOL_GUARDIAN committee, the Morpho Association committee).
ETHEREUM_L1_GROUPS = {
    # ADDED 2026-09-20: WBTC's legacy MultiSigWallet (0x972Eed35..., 6-of-10, reached WBTC token -> Controller
    # 0xCA06411b... -> this wallet). Its owners are frozen here as a dated snapshot (a legacy wallet is not a Safe, so
    # safe_owners_and_threshold cannot resolve it): 7 bare EOAs and 3 contracts, read live 2026-09-20, no overlap with any
    # other registered committee on 6 ecosystems. Re-read getOwners() by hand if BitGo rotates them.
    "wbtc_multisigwallet": {
        "targets": ["0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599"],
        "known_eoa": [
            "0x512fce9B07Ce64590849115EE6B32fd40eC0f5F3", "0x157b1E5ba2302308461f64a8606F2d5970DF129E",
            "0xcBf19D8F01146e3Ec89Aed604485FAbEfA66B268", "0x65CE9DC44591d3B35c6c47b0a42bAeB7191A9d11",
            "0xa9e777D56C0Ad861f6a03967E080e767ad8D39b6", "0xD00e0079B8CAB524F3fa20EA879a7736E512a5Fc",
            "0x0940c5bcAAe6e9Fbd22e869c2a3cD7A21604ED8D", "0xD3A12aBeE178795b9ef94791168826933d9f08D4",
            "0xA2F5E57800DA954BE440FCAfCb02BF2b3fB5AdB7", "0x7E25156DF6CFC563b5811Ef7214D092E660483C8",
        ],
        "safes": [],
    },
    # ADDED 2026-09-20 (registry coverage pass): one contract, Uniswap's Ethereum L1 Governance Timelock, is the root of 11
    # tracked targets on 5 ecosystems (Ethereum L1 2, Arbitrum 1, Base 3, Robinhood Chain 4, Monad 1). It is a token-vote DAO
    # contract, not a signer committee, but it is one root identity, so it is registered like a known EOA and the sweep reports it.
    "uniswap_dao_timelock": {
        "targets": ["0x1F98431c8aD98523631AE4a59f267346ea31F984", "0x000000000004444c5dc75cB358380D2e3dE08A90"],  # V3 Factory, V4 PoolManager
        "known_eoa": ["0x1a9C8182C09F50c8318d769245bEA52c32BE35BC"],
        "safes": [],
    },
    # ADDED 2026-09-20 (registry coverage pass): the sweep covered 7 of the 20 Ethereum L1 targets, 6 of 10 Arbitrum, 3 of 9 Base, 7 of 9 Plasma
    # and 2 of 14 Tempo; the groups below add the real Safes and bare EOAs each unregistered target"s scorer names, so the live sweep can
    # find overlaps the scorers do not hardcode.
    "morpho_blue": {
        "targets": ["0xBBBBBbbBBb9cC5e90e3b3Af64bdAF62C37EEFFCb"],
        "known_eoa": [],
        "safes": ["0xcBa28b38103307Ec8dA98377ffF9816C164f9AFa"],
    },
    "compound_v3_pause_guardian": {
        "targets": ["0xc3d688B66703497DAA19211EEdff47f25384cdc3"],
        "known_eoa": ["0x6d903f6003cca6255D85CcA4D3B5E5146dC33925"],  # + Compound's L1 Governance Timelock, the DAO root of all three Comets (added 2026-09-20)
        "safes": ["0xbbf3f1421D886E9b2c5D716B5192aC998af2012c"],
    },
    "eigenlayer": {
        "targets": ["0x858646372CC42E1A627fcE94aa7A7033e7CF075A"],
        "known_eoa": [],
        # ADDED 2026-09-25: StrategyManager.pauserRegistry() -> isPauser() resolves a THIRD root, a
        # 1-of-7 Safe (`0x5050389572f2d220ad927CcbeA0D406831012390`) never previously registered --
        # a single signature on this Safe can pause the whole contract, disclosed the same day in
        # chains/ethereum-l1/scorers.py's score_eigenlayer_strategy_manager(). Added here so the
        # sweep can find any of its 7 signers sitting on another tracked Safe.
        "safes": ["0x369e6F597e22EaB55fFb173C6d9cD234BD699111", "0xFEA47018D632A77bA579846c840d5706705Dc598", "0x5050389572f2d220ad927CcbeA0D406831012390"],
    },
    # ADDED 2026-09-25: Convex Finance Booster, new Ethereum L1 target (chains/ethereum-l1/scorers.py::
    # score_convex_finance_booster). Two intermediate owner contracts (BoosterOwner, sealed, 30-day
    # forced delay; BoosterOwnerSecondary, unsealed) sit above the Safe -- only the Safe itself is a
    # signer committee the sweep can compare, so only it is registered here.
    "convex_finance": {
        "targets": ["0xF403C135812408BFbE8713b5A23a04b3D48AAE31"],
        "known_eoa": [],
        "safes": ["0xa3C5A1e09150B75ff251c1a7815A07182c3de2FB"],
    },
    "rocket_pool": {
        "targets": ["0x1d8f8f00cfa6758d7bE78336684788Fb0ee0Fa46"],
        "known_eoa": ["0x0cCF14983364A7735d369879603930Afe10df21e"],
        "safes": [],
    },
    "aave_horizon": {
        "targets": ["0x5D39E06b825C1F2B80bf2756a73e28eFAA128ba0"],
        "known_eoa": [],
        "safes": ["0x13B57382c36BAB566E75C72303622AF29E27e1d3", "0xE6ec1f0Ae6Cd023bd0a9B4d0253BDC755103253c"],
    },
    "aave_guardian": {
        "targets": ["0xc2aaCf6553D20d1e9d78E365AAba8032af9c85b0"],  # ACLManager
        "known_eoa": [],
        "safes": ["0x2CFe3ec4d5a6811f4B8067F0DE7e47DfA938Aa30"],  # PROTOCOL_GUARDIAN, 4-of-7
    },
    # ADDED 2026-09-19: the OTHER Aave emergency seat on L1. The group above covers
    # ACLManager's PROTOCOL_GUARDIAN (4-of-7); PayloadsController.guardian() is a
    # different Safe, 5-of-9, whose 9 owners are byte-identical to
    # `aave_guardian` on Arbitrum, Base, Plasma and Monad. This chain was the one
    # never compared, so the cross-ecosystem sweep reported that committee on 4
    # chains when it is on 5. Live-confirmed on 2 RPCs (publicnode + drpc).
    "aave_payloads_guardian": {
        "targets": ["0x2f39d218133AFaB8F2B819B1066c7E434Ad94E9e"],  # Aave V3 PoolAddressesProvider
        "known_eoa": [],
        "safes": ["0xCe52ab41C40575B072A18C9700091Ccbe4A06710"],  # PayloadsController.guardian(), 5-of-9
    },
    "ethena": {
        "targets": [
            "0xe3490297a08d6fC8Da46Edb7B6142E4F461b62D3",  # EthenaMinting (USDe live minter; replaced retired 0x2CC440b7... 2026-09-20)
            "0x73E35C5c35A274E34AdE6EB13cC7f62aEE323728",  # USDtb PSM (via EthenaTimelockController)
            "0x5d3a1ff2B6BAB83b63cd9AD0787074081a52eF34",  # USDe OFTAdapter (LayerZero)
            "0x211Cc4DD073734dA055fbF44a2b4667d5e5fE5D2",  # sUSDe OFTAdapter (LayerZero)
            "0x58538E6A46E07434d7E7375BC268D3cB839C0133",  # ENA OFTAdapter (LayerZero)
        ],
        "known_eoa": [],
        "safes": ["0x3b0aaf6e6fcd4a7ceef8c92c32dfea9e64dc1862"],  # 5-of-10
    },
    "usdtb_bare_eoa": {
        # NOT the Ethena Safe -- USDtb's own admin is a genuinely separate,
        # unrotated bare EOA (see chains/ethereum-l1/scorers.py's score_usdtb()
        # docstring for the disclosed inconsistency this represents within
        # Ethena's own infrastructure). Included here for completeness, not
        # because it's expected to overlap with anything.
        "targets": ["0xC139190F447e929f090Edeb554D95AbB8b18aC1c"],  # USDtb token
        "known_eoa": ["0xd93826BB299765c87D13AeBa2A7E5d9B27A03956"],
        "safes": [],
    },
}

ARBITRUM_GROUPS = {
    # ADDED 2026-09-20 (registry coverage pass): one contract, Uniswap's Ethereum L1 Governance Timelock, is the root of 11
    # tracked targets on 5 ecosystems (Ethereum L1 2, Arbitrum 1, Base 3, Robinhood Chain 4, Monad 1). It is a token-vote DAO
    # contract, not a signer committee, but it is one root identity, so it is registered like a known EOA and the sweep reports it.
    "uniswap_dao_timelock": {
        "targets": ["0x1F98431c8aD98523631AE4a59f267346ea31F984"],  # V3 Factory, owned through the Arbitrum alias of the L1 Timelock
        "known_eoa": ["0x1a9C8182C09F50c8318d769245bEA52c32BE35BC", "0x2BAD8182C09F50c8318d769245beA52C32Be46CD"],  # the L1 Timelock and its Arbitrum alias
        "safes": [],
    },
    # ADDED 2026-09-20 (registry coverage pass): the sweep covered 7 of the 20 Ethereum L1 targets, 6 of 10 Arbitrum, 3 of 9 Base, 7 of 9 Plasma
    # and 2 of 14 Tempo; the groups below add the real Safes and bare EOAs each unregistered target"s scorer names, so the live sweep can
    # find overlaps the scorers do not hardcode.
    "compound_v3": {
        "targets": ["0x9c4ec768c28520B50860ea7a15bd7213a9fF58bf"],
        "known_eoa": ["0x6d903f6003cca6255D85CcA4D3B5E5146dC33925"],  # + Compound's L1 Governance Timelock, the DAO root of all three Comets (added 2026-09-20)
        "safes": ["0x78E6317DD6D43DdbDa00Dce32C2CbaFc99361a9d"],
    },
    "pendle": {
        "targets": ["0x888888888889758F76e7103c6CbF23ABbF58F946"],
        "known_eoa": [],
        "safes": ["0x7877AdFaDEd756f3248a0EBfe8Ac2E2eF87b75Ac"],
    },
    "fluid": {
        "targets": ["0x52Aa899454998Be5b000Ad077a46Bbe360F4e497"],
        "known_eoa": [],
        "safes": ["0x196Ed45eC4ACA949E7AA921ceC81e219e682775e"],
    },
    "gmx_timelock_multisig": {
        "targets": ["0x3c3d99FD298f679DBC2CEcd132b4eC4d0F5e6e72"],  # RoleStore
        "known_eoa": [],
        "safes": ["0x8D1d2e24eC641eDC6a1ebe0F3aE7af0EBC573e0D"],  # TIMELOCK_MULTISIG holder, 5-of-8
    },
    # ADDED 2026-09-25: gTrade's Diamond's real binding constraint, found the same day -- a 10-hour
    # OZ TimelockController (0x893FCf48...) whose PROPOSER/CANCELLER set includes a bare EOA plus two
    # Safes, not the 3-day/14-day timelocks the target's docstring names up front. See
    # chains/arbitrum-ecosystem/scorers.py's gTrade entry for the full derivation.
    "gtrade_emergency_timelock": {
        "targets": ["0xFF162c694eAA571f685030649814282eA457f169"],  # Diamond
        "known_eoa": ["0x80Fd0AcCc8dA81b0852d2dCA17B5DdaB68f22253"],  # bare EOA, PROPOSER+CANCELLER
        "safes": ["0xc07EEd650aB255190CA9766162CfB47cFDf72f3a", "0xe8997C502fCD0729B462FCA19A50cF0DAEA0cAB5"],
    },
    # ADDED 2026-09-20 (maintenance run) with score_gmx_v1_vault(). The second
    # Safe is deliberately the SAME address as gmx_timelock_multisig's: on GMX V1
    # it is the Timelock's tokenManager, which can call setAdmin() with no delay,
    # and on GMX V2 it holds PROPOSER/EXECUTOR/CANCELLER on the timelock that is a
    # ROLE_ADMIN of the RoleStore. Registering it here is what makes the sweep
    # report that overlap instead of leaving it to a scorer-local note.
    "gmx_v1_vault": {
        "targets": ["0x489ee077994B6658eAfA855C308275EAd8097C4A"],  # GMX V1 Vault
        "known_eoa": [],
        "safes": [
            "0x58F582455b54d7c83d03BCeed95FAf72B37fdDD7",  # Timelock.admin(), 4-of-6
            "0x8D1d2e24eC641eDC6a1ebe0F3aE7af0EBC573e0D",  # Timelock.tokenManager(), 5-of-8
        ],
    },
    "camelot": {
        "targets": ["0x1a3c9B1d2F0529D97f2afC5136Cc23e58f1FD35B"],  # AMMv3 Factory
        "known_eoa": [],
        "safes": ["0xbA6A06f8517e271DB44540e68BA46BEB4Bc6155d"],  # factory owner, 2-of-3
    },
    "arbitrum_security_council": {
        "targets": ["0x423552c0F05baCCac5Bfa91C6dCF1dc53a0A1641"],  # the Safe itself, also the target
        "known_eoa": [],
        "safes": ["0x423552c0F05baCCac5Bfa91C6dCF1dc53a0A1641"],  # 9-of-12, Arbitrum's own emergency root
    },
    "aave_guardian": {
        "targets": ["0xa97684ead0e402dC232d5A977953DF7ECBaB3CDb"],  # PoolAddressesProvider
        "known_eoa": [],
        "safes": ["0x1A0581dd5C7C3DA4Ba1CDa7e0BcA7286afc4973b"],  # PayloadsController guardian, 5-of-9
    },
    # Radiant (CORRECTED 2026-09-20, data/finding_2026-09-20-unscored-role-sweep.md
    # section 3): this comment used to say Radiant's admin is a TimelockController
    # with no Safe layer, so there was nothing to resolve. That was wrong.
    # provider.owner() is a 72h TimelockController, but getPoolAdmin()
    # (0x111CEEee040739fD91D29C34C33E6B3E112F2177) is a separate 4-of-11 Safe and
    # getEmergencyAdmin() (0xDdF609735785bF8c7648FFfd12bE543cE6740928) a 1-of-5 Safe
    # whose 5 owners are all among the 11. Neither is in this registry yet (a group
    # is data, and this pass only touched comments), so this sweep did not re-check
    # them. Their owners were compared by hand on 2026-09-20 against the 70 groups of
    # the 7 ecosystems and none matched (see _RADIANT_CROSS_EXPOSURE_NOTE in
    # chains/arbitrum-ecosystem/scorers.py). Done later the same day: see "radiant_pool_admin" below.
    # ADDED 2026-09-20: the Radiant group named in the comment above, so this sweep now checks the
    # two Safes itself instead of relying on the by-hand comparison. Both are read live by the scorer
    # (`score_radiant_lendingpool`): getPoolAdmin() is the 4-of-11 Safe that gates the configurator's
    # onlyPoolAdmin functions, getEmergencyAdmin() a 1-of-5 Safe whose owners are all among the 11.
    "radiant_pool_admin": {
        "targets": ["0xE23B4AE3624fB6f7cDEF29bC8EAD912f1Ede6886"],  # Radiant V2 LendingPool
        "known_eoa": [],
        "safes": [
            "0x111CEEee040739fD91D29C34C33E6B3E112F2177",  # getPoolAdmin(), 4-of-11
            "0xDdF609735785bF8c7648FFfd12bE543cE6740928",  # getEmergencyAdmin(), 1-of-5
        ],
    },
    # ADDED 2026-09-19 (unscored-role sweep): Aave's PROTOCOL_GUARDIAN / EMERGENCY_ADMIN seat on Arbitrum.
    # 4-of-7 Safe with the SAME 7 owners as Ethereum L1's PROTOCOL_GUARDIAN (0x2CFe3ec4...), a different
    # Safe address per chain; zero overlap with the 9-signer GOVERNANCE_GUARDIAN committee.
    "aave_protocol_guardian": {
        "targets": [],
        "known_eoa": [],
        "safes": ["0xCb45E82419baeBCC9bA8b1e5c7858e48A3B26Ea6"],
    },
}

BASE_GROUPS = {
    # ADDED 2026-09-20 (registry coverage pass): one contract, Uniswap's Ethereum L1 Governance Timelock, is the root of 11
    # tracked targets on 5 ecosystems (Ethereum L1 2, Arbitrum 1, Base 3, Robinhood Chain 4, Monad 1). It is a token-vote DAO
    # contract, not a signer committee, but it is one root identity, so it is registered like a known EOA and the sweep reports it.
    "uniswap_dao_timelock": {
        "targets": ["0x33128a8fC17869897dcE68Ed026d694621f6FDfD", "0x8909Dc15e40173Ff4699343b6eB8132c65e18eC6", "0x498581fF718922c3f8e6A244956aF099B2652b2b"],  # V3, V2, V4
        "known_eoa": ["0x1a9C8182C09F50c8318d769245bEA52c32BE35BC"],
        "safes": [],
    },
    # ADDED 2026-09-20 (registry coverage pass): the sweep covered 7 of the 20 Ethereum L1 targets, 6 of 10 Arbitrum, 3 of 9 Base, 7 of 9 Plasma
    # and 2 of 14 Tempo; the groups below add the real Safes and bare EOAs each unregistered target"s scorer names, so the live sweep can
    # find overlaps the scorers do not hardcode.
    "compound_v3": {
        "targets": ["0xb125E6687d4313864e53df431d5425969c15Eb2F"],  # Comet USDC
        "known_eoa": ["0x6d903f6003cca6255D85CcA4D3B5E5146dC33925"],  # + Compound's L1 Governance Timelock, the DAO root of all three Comets (added 2026-09-20)
        "safes": ["0x3cb4653F3B45F448D9100b118B75a1503281d2ee"],  # pauseGuardian, 5-of-9 (same 9 owners as L1 and Arbitrum)
    },
    "aerodrome_slipstream": {
        "targets": ["0x5e7BB104d84c7CB9B682AaC2F3d509f5F406809A"],
        "known_eoa": [],
        "safes": ["0xE6A41fE61E7a1996B59d508661e3f524d6A32075"],
    },
    "moonwell": {
        "targets": ["0xfBb21d0380beE3312B33c4353c8936a0F13EF26C"],
        "known_eoa": ["0x8769B70ac7c93AF0e75de0D69877709B66d75838"],
        "safes": [],
    },
    "morpho_blue": {
        "targets": ["0xBBBBBbbBBb9cC5e90e3b3Af64bdAF62C37EEFFCb"],
        "known_eoa": [],
        "safes": ["0xcBa28b38103307Ec8dA98377ffF9816C164f9AFa"],  # 5-of-9
    },
    "aerodrome": {
        "targets": ["0x420DD381b31aEf6683db6B902084cB0FFECe40Da"],
        "known_eoa": [],
        "safes": ["0xE6A41fE61E7a1996B59d508661e3f524d6A32075"],  # pauser/feeManager, 3-of-7 -- also confirmed live 2026-09-18 to be Voter.governor() itself, same key, not a second entry here
    },
    # ADDED 2026-09-18: closed the same day chains/base-ecosystem/data/
    # finding_2026-09-18-aerodrome-voter-governor-identity.md traced
    # Voter's authority -- emergencyCouncil is a GENUINELY SEPARATE Safe
    # from the "aerodrome" group above (zero owner overlap, confirmed live
    # and by that finding's own adversarial review), bounded to
    # killGauge/reviveGauge and not folded into Aerodrome's own composite,
    # but its 5 real signers are still worth checking against every other
    # tracked ecosystem here.
    "aerodrome_emergency_council": {
        "targets": ["0x16613524e02ad97eDfeF371bC883F2F5d6C480A5"],  # Voter
        "known_eoa": [],
        "safes": ["0x99249b10593fCa1Ae9DAE6D4819F1A6dae5C013D"],  # emergencyCouncil, 3-of-5
    },
    "aave_guardian": {
        # FIXED 2026-09-17 (closed a coverage gap this module's own stale
        # comment claimed didn't exist): Base's Aave V3 DOES have a local
        # guardian Safe (PayloadsController.guardian()), read live by
        # chains/base-ecosystem/scorers.py's score_aave_v3_base() but never
        # previously added here. Live-confirmed: this Safe has the EXACT
        # SAME 9 owners and 5-of-9 threshold as Arbitrum's own Aave guardian
        # Safe above, at a different address -- the CREATE2-redeployed
        # shared-committee pattern, found live for the first time in this
        # project's own tracked targets.
        "targets": ["0xe20fCBdBfFC4Dd138cE8b2E6FBb6CB49777ad64D"],  # PoolAddressesProvider
        "known_eoa": [],
        "safes": ["0x360c0a69Ed2912351227a0b745f890CB2eBDbcFe"],  # PayloadsController guardian, 5-of-9
    },
    # Uniswap on Base is DAO/Timelock-rooted with no local Safe layer: registered above as the
    # "uniswap_dao_timelock" group (the L1 Timelock as a single root identity).
    # ADDED 2026-09-19 (unscored-role sweep): Aave's PROTOCOL_GUARDIAN / EMERGENCY_ADMIN seat on Base.
    # 4-of-7 Safe with the SAME 7 owners as Ethereum L1's PROTOCOL_GUARDIAN (0x2CFe3ec4...), a different
    # Safe address per chain; zero overlap with the 9-signer GOVERNANCE_GUARDIAN committee.
    "aave_protocol_guardian": {
        "targets": [],
        "known_eoa": [],
        "safes": ["0x56C1a4b54921DEA9A344967a8693C7E661D72968"],
    },
}

# ADDED 2026-09-18: Tempo didn't exist as a scored ecosystem when this
# module was first written; its own controller-resolution work (closing
# METHODOLOGY.md's 4-controller-type gap the same day, see chains/tempo/
# data/scored_targets_2026-09-18-controller-types.md) live-resolved two
# GENUINE Gnosis Safes this pass -- both included here. Deliberately NOT
# included: Tempo's LayerZero OneSig (USDC.e/EURC.e's shared admin,
# 0x09c865FA...3A1f) and its 3 Chainlink MCMS instances (cbBTC/PRIME's
# proposer/bypasser/canceller) -- neither shape is a Gnosis Safe, so
# `safe_owners_and_threshold` cannot resolve them, and this module has no
# `known_eoa`-style LIVE resolution path for them yet (putting a hand-
# copied signer list in `known_eoa` would go stale silently, exactly what
# this project's own discipline elsewhere avoids) -- a disclosed gap for
# a future pass, not a silent omission.
TEMPO_GROUPS = {
    "cap_safe": {
        # Controls cUSD's TimelockController (proposer/executor/canceller)
        # AND is the same OFT's LayerZero EndpointV2 delegate -- see
        # chains/tempo/data/scouted_targets_2026-09-17-run2.md T11.
        "targets": ["0x20c0000000000000000000000520792dcccccccc"],  # cUSD
        "known_eoa": [],
        "safes": ["0xb8fc49402df3ee4f8587268fb89fda4d621a8793"],  # Cap Safe, 3-of-5
    },
    "usdt0_safe": {
        # TIP-403 policy 3 (blacklist) admin AND USDT0's own
        # DEFAULT_ADMIN_ROLE holder.
        "targets": ["0x20c00000000000000000000014f22ca97301eb73"],  # USDT0
        "known_eoa": [],
        "safes": ["0x4DFF9b5b0143E642a3F63a5bcf2d1C328e600bf8"],  # 3-of-5
    },
}

# ADDED 2026-09-18: Plasma didn't exist as a scored ecosystem when this
# module was first written -- added the same day it was scored (see
# chains/plasma-ecosystem/scorers.py). Two of its own scorers already
# compute a real cross-chain overlap directly (score_aave_v3_pool_plasma
# against Arbitrum/Base's shared Aave guardian committee,
# score_ethena_usde_oft_plasma against Ethereum L1's own tracked Ethena
# Safe) -- both findings independently re-derivable via THIS module's own
# generic set-overlap check too, included here for that reason, not to
# duplicate the individual scorers' own hardcoded comparisons.
PLASMA_GROUPS = {
    # ADDED 2026-09-20 (registry coverage pass): the sweep covered 7 of the 20 Ethereum L1 targets, 6 of 10 Arbitrum, 3 of 9 Base, 7 of 9 Plasma
    # and 2 of 14 Tempo; the groups below add the real Safes and bare EOAs each unregistered target"s scorer names, so the live sweep can
    # find overlaps the scorers do not hardcode.
    "fluid": {
        "targets": ["0x52Aa899454998Be5b000Ad077a46Bbe360F4e497"],
        "known_eoa": [],
        "safes": ["0x196Ed45eC4ACA949E7AA921ceC81e219e682775e"],
    },
    "telos_consilium": {
        "targets": ["0xa9C251F8304b1B3Fc2b9e8fcae78D94Eff82Ac66"],
        "known_eoa": [],
        "safes": ["0x7d07BFdd01422D7b655B333157eB551B9712dCd8"],
    },
    "aave_guardian": {
        "targets": ["0x061D8e131F26512348ee5FA42e2DF1bA9d6505E9"],  # PoolAddressesProvider
        "known_eoa": [],
        "safes": ["0x19CE4363FEA478Aa04B9EA2937cc5A2cbcD44be6"],  # PayloadsController guardian, 5-of-9
    },
    "ethena": {
        "targets": ["0x5d3a1Ff2b6BAb83b63cd9AD0787074081a52ef34"],  # USDe OFT
        "known_eoa": [],
        "safes": ["0x2C57434603F21f580c91A3Bdc0CC5F3F20278632"],  # 5-of-10
    },
    "pendle": {
        "targets": ["0x888888888889758F76e7103c6CbF23ABbF58F946", "0x84A240Fa784E7F03CB99BA3716065961c5d0D531"],
        "known_eoa": [],
        "safes": ["0x7877AdFaDEd756f3248a0EBfe8Ac2E2eF87b75Ac"],  # 3-of-5
    },
    "validator_set": {
        "targets": ["0x6c50b8ca8EeAa1c75dEe5b5EA79772AcAbc92F48"],  # Aquila
        "known_eoa": [],
        "safes": ["0xCA6fE51bEd6269e3A325d85131Df9B475ecf8F53"],  # 3-of-4
    },
    "euler": {
        "targets": ["0x42388213C6F56D7E1477632b58Ae6Bba9adeEeA3", "0x9b3CeB22Cab2F1b9Ace4CD3132C8a123552eDa2c"],
        "known_eoa": [],
        "safes": ["0xfD30738fcB5eb5Ba418a84e672007912F991E539"],  # DAO Safe, 4-of-8 (proposer on both Timelocks)
    },
    # ADDED 2026-09-19: PAUSE_GUARDIAN_ROLE on the eVaultFactory Governor
    # (0x939cA204...). Found by an independent verification pass while drafting
    # the Monad Euler dashboard card; nothing in the repo (no scorer, no group,
    # no doc) named this role or these addresses before. Holders (live,
    # getRoleMember): the Labs Safe below plus two bare EOAs, and the SAME two
    # EOAs hold the same role on Monad's Governor (MONAD_GROUPS below). Either
    # EOA alone can call pause(eVaultFactory) -- eth_call simulation, no
    # transaction, a random address reverts.
    "euler_pause_guardian": {
        "targets": ["0x42388213C6F56D7E1477632b58Ae6Bba9adeEeA3"],  # eVaultFactory
        "known_eoa": [
            "0xff217004BdD3A6A592162380dc0E6BbF143291eB",
            "0xcC6451385685721778E7Bd80B54F8c92b484F601",
        ],
        "safes": ["0xbe7623D35700700DdC7A92fEe1fe7B0E9E6f1013"],  # Labs Safe
    },
    # ADDED 2026-09-20 (Yuzu authority trace): Yuzu Money's two proposer Safes, registered as ONE group
    # because they have the IDENTICAL five bare-EOA owners (S1 3-of-5 proposes on the 12h timelock that
    # holds ADMIN_ROLE and holds POOL_MANAGER on yzPP directly, S2 4-of-5 proposes on the 2-day timelock
    # that owns every ProxyAdmin). Two separate groups would make the target overlap itself.
    "yuzu": {
        "targets": ["0x6695c0f8706C5ACe3Bdf8995073179cCA47926dc"],  # yzUSD
        "known_eoa": [],
        "safes": [
            "0xe61ad2De346db42879B6ee3c7cF0C6a2cDC0530d",  # S1, 3-of-5
            "0xa2a9700407934e913C840556B3D29F19cf6f203d",  # S2, 4-of-5
        ],
    },
    # ADDED 2026-09-19 (unscored-role sweep): Aave's PROTOCOL_GUARDIAN / EMERGENCY_ADMIN seat on Plasma.
    # 4-of-7 Safe with the SAME 7 owners as Ethereum L1's PROTOCOL_GUARDIAN (0x2CFe3ec4...), a different
    # Safe address per chain; zero overlap with the 9-signer GOVERNANCE_GUARDIAN committee.
    "aave_protocol_guardian": {
        "targets": [],
        "known_eoa": [],
        "safes": ["0xEf323B194caD8e02D9E5D8F07B34f625f1c088f1"],
    },
}

# ADDED 2026-09-19: Monad didn't exist as a scored ecosystem when this
# module was first written -- added the same day it was scored/deployed
# (see chains/monad/scorers.py). Every one of its 7 scorers' own docstrings
# disclosed crossExposureScore as "not computed this pass" -- this closes
# that gap for the 5 of 7 targets whose authority actually resolves to a
# real Gnosis Safe or a known bare EOA. Uniswap v4's PoolManager (owner is a Wormhole
# message relay -> Ethereum's UNI Timelock) was added 2026-09-20 as the "uniswap_dao_timelock"
# group. Still NOT included: the Monad Native Bridge (owner is a Wormhole
# GeneralPurposeGovernance relay gated by a 13-of-19 Guardian quorum, also
# not a Safe) -- neither shape is resolvable via `safe_owners_and_threshold`,
# same "no live resolution path yet" disclosed gap this file already
# documents for Tempo's LayerZero OneSig/Chainlink MCMS shapes above.
MONAD_GROUPS = {
    # ADDED 2026-09-20 (registry coverage pass): one contract, Uniswap's Ethereum L1 Governance Timelock, is the root of 11
    # tracked targets on 5 ecosystems (Ethereum L1 2, Arbitrum 1, Base 3, Robinhood Chain 4, Monad 1). It is a token-vote DAO
    # contract, not a signer committee, but it is one root identity, so it is registered like a known EOA and the sweep reports it.
    "uniswap_dao_timelock": {
        "targets": ["0x188d586Ddcf52439676Ca21A244753fA19F9Ea8e"],  # V4 PoolManager, owned by a Wormhole receiver relaying the L1 Timelock
        "known_eoa": ["0x1a9C8182C09F50c8318d769245bEA52c32BE35BC"],
        "safes": [],
    },
    "echo_ebtc_admin": {
        # Real, dated 2026-05 admin-key exploit, since remediated -- see
        # chains/monad/scorers.py::score_echo_ebtc_monad() for the full
        # incident. This is the CURRENT admin Safe, not the compromised
        # pre-incident bare EOA.
        "targets": ["0xd691b0aFed67F96CEC28Ab6308Cbe5b2C103b7e9"],  # eBTC token proxy
        "known_eoa": [],
        "safes": ["0x401a33127e4946a82709b5edc60c636581cab1c5"],  # 3-of-4
    },
    "kuru": {
        "targets": ["0xd651346d7c789536ebf06dc72aE3C8502cd695CC", "0x2A68ba1833cDf93fa9Da1EEbd7F46242aD8E90c5"],  # Router, MarginAccount
        "known_eoa": [],
        "safes": ["0x8b736dCE2071783fD9Db0a423dad17cc8ed5788b"],  # 3-of-5, no timelock
    },
    "morpho_vault_owner": {
        "targets": ["0x32841A8511D5c2c5b253f45668780B99139e476D"],  # Grove x Steakhouse High Yield AUSD vault
        "known_eoa": [],
        "safes": ["0x0A0e559bc3b0950a7e448F0d4894db195b9cf8DD"],  # owner, 5-of-8
    },
    "morpho_vault_curator": {
        # Same vault as above -- its curator (which also doubles as
        # guardian, see the scorer's own docstring) is a SEPARATE Safe from
        # the owner, checked as its own group so an overlap with either
        # role is caught independently.
        "targets": ["0x32841A8511D5c2c5b253f45668780B99139e476D"],
        "known_eoa": [],
        "safes": ["0x827e86072B06674a077f592A531dcE4590aDeCdB"],  # curator = guardian, 2-of-6
    },
    "curve_admin": {
        # NOT a Safe -- a single bare EOA, confirmed live (zero contract
        # bytecode) and confirmed actively exercised (Set_new_fee/Ramp_A
        # calls). Included as `known_eoa`, same convention already used for
        # Ethereum L1's own `usdtb_bare_eoa` group above -- if this
        # ownership ever transfers to Curve DAO's usual multisig, this
        # entry goes stale and should be updated then, not treated as
        # permanent.
        "targets": ["0x8271e06E5887FE5ba05234f5315c19f3Ec90E8aD"],  # StableSwap Factory
        "known_eoa": ["0xabc336d4C71ad275695744d32DdB1d8266Db1cbF"],
        "safes": [],
    },
    "curvance_emergency_council": {
        "targets": ["0xaD663aC84052b52BE4ed1b27BA416505e84a00Bf"],  # LendingOptimizer vault
        "known_eoa": [],
        "safes": ["0x379D4a8FBc23A8Fd8c2b3738Dbf1fEBe9a64399c"],  # Emergency Council, 4-of-5, proven zero-delay path
    },
    # ADDED 2026-09-19 (second pass, same day): Aave V3 and Euler V2 --
    # see chains/monad/scorers.py's own score_aave_v3_monad()/
    # score_euler_v2_monad() for the full authority-chain derivation.
    "aave_guardian": {
        "targets": ["0x34793Fb9935F7bB5E5aE920fb963F39063E7A615"],  # PoolAddressesProvider
        "known_eoa": [],
        # PayloadsController guardian, 5-of-9 -- CONFIRMED live this pass to be
        # the exact same 9 signers as PLASMA_GROUPS["aave_guardian"] above (and,
        # per that group's own docstring reference, Arbitrum's and Base's too) --
        # a FOURTH chain sharing this one committee, not a fresh coincidence.
        # (CORRECTED 2026-09-19: Ethereum L1's PayloadsController.guardian() is the same
        # committee, see ETHEREUM_L1_GROUPS["aave_payloads_guardian"] -- five chains in total.)
        "safes": ["0x056E4C4E80D1D14a637ccbD0412CDAAEc5B51F4E"],
    },
    "euler_dao": {
        "targets": ["0xba4Dd672062dE8FeeDb665DD4410658864483f1E"],  # eVaultFactory
        "known_eoa": [],
        "safes": ["0xdA3da5c8f93c0B7630412B8cd7dE571011Df8963"],  # DAO Safe, 4-of-8, proposer on both TimelockControllers -- checked, distinct from PLASMA_GROUPS["euler"]'s own DAO Safe (Euler uses a different Safe per chain)
    },
    "euler_security_council": {
        "targets": ["0xba4Dd672062dE8FeeDb665DD4410658864483f1E"],
        "known_eoa": [],
        "safes": ["0x6d2d19a06A49e87bedC653CEd58c17C3B40502F9"],  # Security Council, 2-of-3 -- no DEFAULT_ADMIN_ROLE/PROPOSER_ROLE/EXECUTOR_ROLE found on either Euler governor this pass, checked anyway per this module's own "no unchecked defaults" convention
    },
    # ADDED 2026-09-19: PAUSE_GUARDIAN_ROLE on Monad's eVaultFactory Governor
    # (0x515C9ff6...). chains/monad/scorers.py looked for GUARDIAN_ROLE /
    # PAUSER_ROLE / EMERGENCY_ROLE / WILD_CARD, none of which the deployed
    # contracts use, so this seat was never seen. Holders (live, getRoleMember):
    # the Labs Safe below plus the SAME two bare EOAs that hold it on Plasma.
    "euler_pause_guardian": {
        "targets": ["0xba4Dd672062dE8FeeDb665DD4410658864483f1E"],  # eVaultFactory
        "known_eoa": [
            "0xff217004BdD3A6A592162380dc0E6BbF143291eB",
            "0xcC6451385685721778E7Bd80B54F8c92b484F601",
        ],
        "safes": ["0x9cC876dCb0e99cC040cf5F92880d0Ee9e320CA61"],  # Labs Safe
    },
    # ADDED 2026-09-19 (unscored-role sweep): Aave's PROTOCOL_GUARDIAN / EMERGENCY_ADMIN seat on Monad (which ALSO holds POOL_ADMIN there).
    # 4-of-7 Safe with the SAME 7 owners as Ethereum L1's PROTOCOL_GUARDIAN (0x2CFe3ec4...), a different
    # Safe address per chain; zero overlap with the 9-signer GOVERNANCE_GUARDIAN committee.
    "aave_protocol_guardian": {
        "targets": [],
        "known_eoa": [],
        "safes": ["0xc887455536CBD4e615B745e70CaCde15B3117e74"],
    },
}
