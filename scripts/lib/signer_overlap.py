"""
Cross-protocol signer-overlap detection for authority-risk-oracle.

Adds a 5th dimension to every score, crossExposureScore, answering a question
none of the other four sub-scores can: does the same real person (the same
root EOA, whether holding a target directly or sitting as a Gnosis Safe owner)
also control ANOTHER tracked target? A single compromised key becoming a
systemic risk across multiple "independent" protocols is exactly the failure
mode this project's sister research program, multisig-overlap, was built to
catch (343 protocols, 570 confirmed Safes) -- this module reuses that same
discipline (re-derive live, look for legitimate context before flagging an
overlap as notable) scoped to this oracle's own tracked targets.

Deliberately NOT folded into compositeScore: compositeScore stays exactly
what it always meant (this target's own authority setup, in isolation).
crossExposureScore is a property of the SET of tracked targets, not of any
one target alone, and is published as its own field for exactly that reason.

Convention (matches the rest of this project: 100 = safest):
    crossExposureScore = max(0, 100 - 20 * sharedGroupCount)
where sharedGroupCount is how many OTHER tracked-target groups share at
least one root signer with this one. 0 shared -> 100 (fully independent
authority). Each additional shared group costs 20 points, floored at 0.

CORRECTED 2026-09-20: the formula above only sees overlap WITHIN Robinhood
Chain, so a group whose root committee is identical to a tracked target's
committee on ANOTHER ecosystem (Pendle, Morpho Blue, Curve, all confirmed by
scripts/check_cross_ecosystem_overlap.py) still read 100 on-chain. Such a group
now carries the optional key "cross_ecosystem" (a short dated reason string)
and scores min(within-Robinhood score, 80): 80 is the same flat value
Arbitrum/Base/Plasma/Monad already use for a committee shared with another
chain's tracked target, and min() means the cross-ecosystem rule never RAISES a
score the within-Robinhood rule already lowered (Steakhouse/Morpho vaults stay
40). The flag is a static, dated claim: this module deliberately opens no second
RPC connection to another chain, so a flag whose overlap has ended (committee
rotated) must be removed by hand after re-running the sweep script.
"""
import os
import sys

from web3 import Web3

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from web3_utils import RpcUnavailable, _is_revert  # noqa: E402

_SAFE_ABI = [
    {"name": "getOwners", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "address[]"}]},
    {"name": "getThreshold", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "uint256"}]},
]

_CUSTOM_MULTISIG_ABI = [
    {"name": "getSigners", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "address[]"}]},
    {"name": "threshold", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "uint256"}]},
]


def _safe_owners(w3, addr):
    """Resolves a group entry's signer set. Tries the standard Gnosis Safe ABI
    first; if that reverts, falls back to the bespoke getSigners()/threshold()
    pattern found on LayerZero's own Robinhood Chain infra-ownership contract
    (batch 8, see web3_utils.custom_multisig_owners_and_threshold) rather than
    silently skipping any non-Safe multisig as if it had no signers at all.

    ADDED 2026-09-22: raises RpcUnavailable (does NOT return None) if a persistent RPC failure --
    not a confirmed revert -- prevents resolving either interface. This function's ONE live caller,
    compute_cross_exposure_with_notes(), used to treat that same None as "not a Safe, no signers" --
    silently narrowing a group's signer set, which RAISES crossExposureScore (fewer counted as
    shared), publishing an UNDER-estimated risk under network load. Worse than the plain floor
    score web3_utils's own fix was written for, and this function is reached from score_all() on
    the real Robinhood push (scripts/lib/scorers.py -> compute_cross_exposure_with_notes()), not
    only from the standalone sweep (scripts/check_cross_ecosystem_overlap.py). No retry loop here
    (this function never had one before this fix either) -- a single failed attempt is enough to
    mark the whole group unresolved, see below."""
    try:
        c = w3.eth.contract(address=Web3.to_checksum_address(addr), abi=_SAFE_ABI)
        return [Web3.to_checksum_address(o) for o in c.functions.getOwners().call()]
    except Exception as e:
        if not _is_revert(e):
            raise RpcUnavailable(f"getOwners() on {addr}: {type(e).__name__}: {e}") from e
    try:
        c = w3.eth.contract(address=Web3.to_checksum_address(addr), abi=_CUSTOM_MULTISIG_ABI)
        return [Web3.to_checksum_address(o) for o in c.functions.getSigners().call()]
    except Exception as e:
        if not _is_revert(e):
            raise RpcUnavailable(f"getSigners() on {addr}: {type(e).__name__}: {e}") from e
        return None


# One entry per tracked-target GROUP (matching the same grouping used in
# data/scored_targets_*.md and dashboard/index.html): the addresses in that
# group, and how to resolve its root signer set.
#   - "known_eoa": bare EOAs directly confirmed this pass as the root
#     controlling authority (or, for rollup_l1, individually-resolved Safe
#     owners from a chain this module's caller-supplied w3 can't reach --
#     see the note on that entry).
#   - "safes": Safe addresses on the SAME chain as the group's own targets
#     (Robinhood Chain mainnet), whose owners are re-derived live every run.
#   - "cross_ecosystem" (optional, ADDED 2026-09-20): a short dated reason string
#     saying this group's root committee is identical to a tracked target's on
#     another ecosystem. Caps the group's crossExposureScore at 80 (see the module
#     docstring); ignored by cross_ecosystem_overlap.group_root_signers(), which
#     only reads known_eoa/safes.
GROUPS = {
    # ADDED 2026-09-25: Flock Credit Vault, new target -- governance() is a bare, active EOA
    # (no multisig, no timelock on the 2-step transfer itself). Registered so the sweep can
    # find this EOA sitting on another tracked ecosystem's committee.
    "flock_credit": {
        "targets": ["0xd42174d3Db28B0fA2BD25381c3521b18AE9dB490"],
        "known_eoa": ["0x097bA31b7ACffD75b909Fc7Bef2e55424D2Dacdc"],
        "safes": [],
    },
    "steakhouse": {
        "targets": ["0xBeEff033F34C046626B8D0A041844C5d1A5409dd"],
        "known_eoa": ["0x337feFE49514fb901eB455A501b8Be76CDeF7660"],
        "safes": ["0x9023FBD6A08C666491A2d1648737E400cF42D2Fb"],
    },
    "uniswap_stack": {
        # CORRECTED 2026-09-16 (previously mislabeled "known_eoa"/vanity-ground key):
        # 0x2BAD8182... is the legitimate Arbitrum L1->L2 alias of Uniswap's real
        # Ethereum-mainnet Governance Timelock (0x1a9C8182C09F50c8318d769245bEA52c32BE35BC),
        # re-derived by exact arithmetic (L1 + 0x1111...1111 mod 2^160, deterministic,
        # not a coincidental lookalike) and re-confirmed live today: the L1 address has
        # real deployed bytecode, the L2 alias has none -- expected for a bridge alias
        # (a sender identity materialized via the canonical bridge, not a deployed
        # contract), not evidence of a bare/compromised key. Left in `known_eoa` here
        # (the cross-exposure signer-overlap check still needs to treat it as a single
        # root identity, not a Safe) but it is NOT actually a private-key-controlled EOA
        # -- see scorers.py for the same correction and the open re-scoring question.
        "targets": [
            "0x1f7d7550B1b028f7571E69A784071F0205FD2EfA",
            "0x8366a39CC670B4001A1121B8F6A443A643e40951",
            "0x000000007A1C8e570011EeDF86A2A35593013cBA",
            "0x8bcEaA40B9AcdfAedF85AdF4FF01F5Ad6517937f",
        ],
        "known_eoa": ["0x2BAD8182C09F50c8318d769245beA52C32Be46CD", "0x1a9C8182C09F50c8318d769245bEA52c32BE35BC"],
        "safes": [],
        # ADDED 2026-09-20: this alias is the Arbitrum-family form of Uniswap's Ethereum L1 Governance Timelock, which is
        # also the root of tracked Uniswap targets on Ethereum L1, Arbitrum, Base and Monad (each scorer re-confirms it
        # live). Hand-set and dated, like every cross_ecosystem flag: remove it by hand if Uniswap re-roots.
        "cross_ecosystem": "2026-09-20: this alias is the Arbitrum form of the Uniswap L1 Governance Timelock 0x1a9C8182...35BC, which also roots tracked Uniswap targets on Ethereum L1, Arbitrum, Base and Monad",
    },
    "lighter": {
        "targets": ["0x94bAB9693Ba2f6358507eFfcbd372b0660AFfF9d"],
        "known_eoa": ["0x4972E0CaCb2AC45644BA054838e96fF4f6f7eFDb"],
        "safes": ["0x8Caf9FF9392F39E87cBC65A130c026caaCD321ef"],
    },
    "arcus": {
        "targets": [
            "0x9c3663FA9ab976E67B42939486EC4966Cb41a0BB",
            "0x925F92F055EDB79C42B5d45E64A1b74143b90eA0",
            "0x4472C69d299382F8847ebCE4FC6Ed8e295510E3e",
        ],
        "known_eoa": [],
        "safes": ["0x81B80499C396a9931b9e44953425a82C1b2541bd"],
    },
    # ADDED rotation audit 2026-09-19 (new-target search while auditing index
    # 11): Arcus's OTHER product (Perps, not pTokens) -- a genuinely
    # different on-chain authority chain from the `arcus` group above (see
    # score_arcus_perps_bridgevault()'s own docstring), but its
    # TimelockController's PROPOSER_ROLE/EXECUTOR_ROLE/CANCELLER_ROLE
    # includes one address (0x4f1d777b... -- CORRECTED 2026-09-19: a 2-of-4
    # Gnosis Safe with 171 bytes of code, NOT an EOA as first written; it is
    # listed under `known_eoa` below because the overlap this group records is
    # the same ADDRESS appearing in both groups, and its 4 owners are bare EOAs
    # in no other tracked group) that is ALSO one of the 3 owners of
    # the `arcus` group's own Safe -- a real, live-confirmed cross-protocol
    # signer overlap between two different Arcus products, not a duplicate
    # of the same authority chain. Grepped this file for all 4 addresses
    # below before wiring this group in -- none appeared anywhere else.
    "arcus_perps_bridgevault": {
        "targets": ["0x14b107cf534239c59571b066cb6497a321da897c"],
        "known_eoa": [
            "0xfd2b8e0529CCCBA28Faa0946318322F1CA9bee51",
            "0x19f45260a20F38181A87a8da866DccfF7F6D009b",
            "0x0f517FD397c7DD6BAA968bbEaEF5622A52717FF7",
            "0x4f1d777bf36E259F3cB66f2cE969f4c5De05ebe2",
        ],
        "safes": [],
    },
    # ADDED rotation audit 2026-09-19 (new-target search while auditing index
    # 12): T3tris Finance's WBTC vault on Robinhood Chain. Grepped this file
    # for the vault address AND the admin EOA before wiring this group in --
    # neither appears anywhere else (the 3 sibling vaults in T3tris's own
    # registry are each keyed by a genuinely different EOA, not this one, so
    # they are not a duplicate of this group -- see score_t3tris_vault()'s
    # own docstring).
    "t3tris_wbtc_vault": {
        "targets": ["0xd5c6c79692715145098a65d1eb1f2a10c524f8e8"],
        "known_eoa": ["0x65D02Bb13f515DD105Fb733E9E31f11A2F65e57f"],
        "safes": [],
    },
    # ADDED rotation audit 2026-09-19 (new-target search while auditing index
    # 13): up v3 (up33.xyz), the ~$8.6M TVL lead carried over open since
    # index 8. Grepped this file for the factory address AND the owner
    # Safe/its 4 owners before wiring this group in -- none appear anywhere
    # else (a genuinely new authority root, not the same Arbitrum L1->L2
    # alias every other tracked Uniswap-family target shares). See
    # score_up_v3_factory()'s own docstring in scripts/lib/scorers.py.
    #
    # NOTE (rotation audit index 14, 2026-09-19): up's own ve(3,3) V2 stack
    # (up v2, ~$1.16M TVL, DefiLlama slug `up-v2`) is governed by this SAME
    # Safe end to end -- confirmed on 2 RPCs: the V2 PoolFactory's `pauser()`
    # and `feeManager()`, the Voter's `governor()`/`emergencyCouncil()`/
    # `epochGovernor()`, the VotingEscrow's `team()`, the Minter's `team()`
    # and the FactoryRegistry's `owner()` all return
    # 0x0eEA30aBa3f07abFA20E4b544F55e0f917d9DFd8. It is not a separate
    # authority root, so it was NOT added as its own target this pass; if it
    # is ever tracked, add its addresses to THIS group's `targets` rather than
    # a new group (the same handling already noted for UNCX's second locker).
    "up_v3": {
        "targets": ["0x1ac9dB4a2608ba45D6127B1737949b51Bb54B7F3"],
        "known_eoa": [],
        "safes": ["0x0eEA30aBa3f07abFA20E4b544F55e0f917d9DFd8"],
    },
    # ADDED rotation audit 2026-09-19 (new-target search while auditing index
    # 14): Alandale V3, a ve(3,3) Algebra-Integral-v1.0-based CL DEX on
    # Robinhood Chain (~$1.14M TVL recomputed on-chain and confirmed by
    # DexScreener; DefiLlama lists ~$1.99M, inflated by one wrong USAR price --
    # see the scorer's docstring). The factory's owner(), its ProxyAdmin's
    # owner() and its sole DEFAULT_ADMIN_ROLE holder are all one plain 3-of-5
    # Gnosis Safe. Grepped this whole repo for the factory, the ProxyAdmin,
    # the Safe and all 5 of its owners before wiring this group in -- zero
    # matches anywhere; compute_cross_exposure() below (which re-reads every
    # OTHER tracked Safe's owners on-chain, not just the hardcoded ones) is
    # the authoritative check, and returned 100. See
    # score_alandale_v3_factory()'s own docstring in scripts/lib/scorers.py.
    "alandale_v3": {
        "targets": ["0x16494A80E08Bcb9285D87b67149d7b01774D82F8"],
        "known_eoa": [],
        "safes": ["0x2a04c1D26767dD30f62712DCFCF1222f733A2B0E"],
    },
    "stock_tokens": {
        "targets": [
            "0x322F0929c4625eD5bAd873c95208D54E1c003b2d",
            "0x12f190a9F9d7D37a250758b26824B97CE941bF54",
            "0x894E1EC2D74FFE5AEF8Dc8A9e84686acCB964F2A",
            "0xE0444EF8BF4eD74f74FD73686e2ddF4C1c5591E8",
            "0x86923f96303D656E4aa86D9d42D1e57ad2023fdC",
        ],
        # 2026-09-19 (rotation audit index 15): the DEFAULT_ADMIN_ROLE holder
        # (first entry) roots the whole role tree -- `getRoleAdmin()` is 0x00 for
        # all 13 role ids the beacon has ever granted, no `RoleAdminChanged` in
        # its full history -- but it holds NO operational role itself: the 12
        # other bare EOAs below hold the live per-function roles on the SAME
        # beacon (BEACON_UPGRADER 0xCd8C..., PAUSER 0xe7BC..., BLOCKER 0x913c...,
        # MINTER 0x2b94..., BURNER 0x6E40..., TOKEN_PAUSER 0xFCcF... and 6
        # roles whose names are not known, listed by holder only). Replayed
        # from genesis (full-history address-only eth_getLogs on one RPC, the
        # block-0..9000 window re-replayed identically on a second; later
        # grants are bounded by the admin EOA's nonce = 2 = its two known txs)
        # and confirmed live with hasRole() on 2 RPCs. None of the 12 appears
        # in any other group; they are listed so a future overlap is caught,
        # not because today's crossExposureScore (100) changes.
        "known_eoa": [
            "0xD6f8378F8e440c65F8382F5f2728c78DfD55B66d",
            "0xCd8C6182e7C6Ca3B5156D6a90a67719d7e2Be094",
            "0x2b94105fFf37630f98e1f24811daD588FC5C3A87",
            "0x6E40B50A40C1db42A85a0E8fe8FF7d9CbFc2D8C1",
            "0x957B6de6525C63349f7619743Ef1E0ad93cd74D4",
            "0xe7BCB188254Bc6eBBfF63014DfED4cD4A024F22A",
            "0xFCcF56B674113d9C4eb0F9B3370930ceD9E6Ab23",
            "0x7369d100c00F28E45D779ac9d4b1c7afa61e4aBC",
            "0x5516B3451d4d6C9f63353Fe7Bc9537477ECCE000",
            "0x697e774d60c1a3769f2eD0b919AAcf17be0ae553",
            "0x92905e8d0e2301BA143215B8D86D63fFD4188143",
            "0xcba16C2b9048AF033c5b34E43dd1D47D1358524A",
            "0x913cA87347391218e5De2C17c5A0AEba8B0b28fD",
        ],
        "safes": [],
    },
    # New 2026-09-19 (rotation audit index 15): Saffron Vaults factory. Its
    # Ownable2Step owner is an EIP-7702-delegated EOA (MetaMask
    # EIP7702StatelessDeleGator), functionally one key, same address as
    # feeReceiver() and as creatorAddress of all 111 vaults. Grepped
    # scripts/, chains/, data/ and README.md for the owner and factory
    # addresses: no other tracked group contains either.
    # compute_cross_exposure() is the authoritative check and returned 100.
    "saffron_vault_factory": {
        "targets": ["0xb24b143ad6bB5bE9559CcC75f34A2261b7456904"],
        "known_eoa": ["0x58CA1eaED80896400122164Abe16d77B2b4ff7c9"],
        "safes": [],
    },
    "netnet_credit": {
        "targets": ["0x99347d5F70D3838763f6Bddcf80304C8aa953B57"],
        "known_eoa": [],
        "safes": ["0x3Bb7A23316f82C0e984fA2E784846d8928a35f42"],
    },
    "purinta": {
        "targets": ["0x37788ff0c1d4e45A7FE06BC7e71e0cc00121d0A8"],
        "known_eoa": [],
        "safes": [
            "0x370EC5d1809B27F1fB18e002cf79837c46F5134c",
            "0x82B4a86c796d9508350D129BA150B5D625ec98A4",
        ],
    },
    "ethena_steakhouse": {
        "targets": ["0xbEeFF0fb1Dc19344A87b8479dAb60A2e16160737"],
        "known_eoa": [],
        "safes": [
            "0x9023FBD6A08C666491A2d1648737E400cF42D2Fb",  # SAME curator Safe as steakhouse
            "0xD062020d07FACF39b5a06C34B07d81c43F615ef4",
        ],
    },
    "steakhouse_turbo": {
        # ADDED batch 13 (2026-09-18): found via DefiLlama-Adapters'
        # registries/curators.js (the file the TVL page actually reads, not the
        # 404ing projects/steakhouse/index.js flagged open in batch 12). Same
        # curator Safe as "steakhouse"/"ethena_steakhouse" above, and the SAME
        # owner()-chain Safe as "ethena_steakhouse" (owner() -> 0x261a3b7A...
        # -> 0xD062020d..., confirmed live, identical hop shape to Ethena x
        # Steakhouse) -- a distinct tracked target, not a duplicate group.
        "targets": ["0xbeEfFF136E3684273e6aA75A1669B784B373A4FD"],
        "known_eoa": [],
        "safes": [
            "0x9023FBD6A08C666491A2d1648737E400cF42D2Fb",
            "0xD062020d07FACF39b5a06C34B07d81c43F615ef4",
        ],
    },
    "grove_steakhouse": {
        # ADDED batch 13 (2026-09-18): same discovery as steakhouse_turbo above.
        # Curator is a DIFFERENT, not-previously-tracked 2-of-2 Safe ("Grove"),
        # but owner() resolves through the same 0x261a3b7A... contract to the
        # SAME 0xD062020d... Safe already shared by steakhouse/ethena_steakhouse/
        # steakhouse_turbo -- confirmed live, not assumed from the naming.
        "targets": ["0xBEEff039907422219Fb367e525954DDC092854d9"],
        "known_eoa": [],
        "safes": [
            "0x622E19d6903BD4507cfc70b31d5B99535114C0FC",
            "0xD062020d07FACF39b5a06C34B07d81c43F615ef4",
        ],
    },
    "spark_savings": {
        # UPDATED batch 13 (2026-09-18): Spark Liquidity Layer's ALMProxy
        # (0xfD2fD4B0...) added to this SAME group, not a new one -- its
        # DEFAULT_ADMIN_ROLE holder is confirmed (live hasRole + matching
        # 8,113-byte bytecode) to be the literal same executor contract as
        # spUSDG below, i.e. one root authority, two tracked targets. See
        # score_spark_liquidity_layer_almproxy().
        "targets": [
            "0xde770c84FE66E063336b31737cFE9790f18c4087",
            "0xfD2fD4B046136B540A56C11c75ac679AE7d1dB24",
        ],
        "known_eoa": [],
        "safes": [],
        "unresolved_note": "Executor is a self-administering contract, not a Safe; its L1 controller (Sky's SubProxy) was not fully traced -- no EOA signer set to cross-reference this pass. (This means crossExposureScore=100 for both targets in this group is the project's existing 'not applicable' convention, NOT a confirmed no-overlap result -- the two targets are known to share this one root contract, which the Safe-owner-based formula below has no way to score as an overlap; disclosed in data/ rather than silently defaulted.)",
    },
    "rollup_l1": {
        "targets": [
            "0x23A19d23e89166adedbDcB432518AB01e4272D94",
            "0xBd0D173EEb87D57A09521c24388a12789F33ba96",
            "0x1232813BDd40aa9d53066A880dE78a4Be70B90FD",
            "0x1A07cc4BD17E0118BdB54D70990D2158AbAD7a2D",
            "0xDf8755334ce7A73cCF6b581C02eA649AE3E864b3",
            "0xf0ce991ea4A0d2400A4AB49b20ae333f6Dce3DE9",
        ],
        # Re-derived live 2026-09-16 via EXECUTOR_ROLE RoleGranted/RoleRevoked replay
        # on ETHEREUM MAINNET (this group's authority lives on L1, not Robinhood
        # Chain -- see data/scored_targets_2026-09-15-batch4.md). The 7-of-8 Safe
        # 0x7Ae50886c7EA0394613aa7Dcc287a5c9650784b6 has 8 owners; one seat
        # (0x0fc5c64074641e677Fb86bCE80303a2eE64344Ac) is itself a nested 3-of-7
        # Safe, whose 7 owners are the real root signers for that seat. The caller's
        # w3 here only reaches Robinhood Chain, so these are listed as pre-resolved
        # rather than re-queried on the wrong chain by this module.
        "known_eoa": [
            "0x640BF0B6b8706f35195d6491cbE347c01b967393",
            "0x7957e74a59Af4404f64B454cDfaF08F7047021DD",
            "0x54Fafc2728569b9F6099613482bBc8E47B61E477",
            "0xb89C85BE593e6A8f7e35AC481b5F75Fc4036f31c",
            "0x29631c2da9Ab1C0Ca1935A463842a9484E34Fa17",
            "0x2584fd737d35bE395aa979b18602d0dE65f38b2c",
            "0xe94aCAa305ce4DF3862585AD0B8Ed05C8C808d6A",
            "0xBa86e3b54E3Ee00185EccB41ff40FC3d5Ee79ecA",
            "0x582B0cCE0bA332D151998A7cA62Cf12d308b050F",
            "0xFA677559d43856af84E9ceA929E36BF126da4562",
            "0x499b56449Fe624Cc984Ec92F64Be01F9619441B4",
            "0x90a0eb0337224f74D694c04648f0Ab8a80E37029",
            "0x026F0df4b04a258207337fBB05790F0E1283e526",
            "0x9b6488FBa4ed8fD4840F37345311eCCA1B09740C",
        ],
        "safes": [],
    },
    "ramses": {
        "targets": [
            "0xE0c4ceb92d08CA985bB70fe0a22fEb121A9854A8",
            "0x4b37359BF291AbE8453692DB58d515a8b013Dca9",
            "0x83341F891f898cb5E0cacC8a70501BBa83d9CecF",
            "0xA203A21dCCB461E415DaA342E8e635B6CeE0cCb3",
        ],
        "known_eoa": [],
        "safes": ["0x20D630cF1f5628285BfB91DfaC8C89eB9087BE1A"],
    },
    "ekubo": {
        "targets": ["0x00000000000014aA86C5d3c41765bb24e11bd701"],
        "known_eoa": [],
        "safes": [],
        "unresolved_note": "Verified ownerless by design -- no authority surface exists to cross-reference.",
    },
    "pendle": {
        "targets": ["0x544BF81c855AE84c1e8b65d5E38770898D01EeE2"],
        "known_eoa": [],
        "safes": [
            "0x7877AdFaDEd756f3248a0EBfe8Ac2E2eF87b75Ac",
            "0xE6F0489ED91dc27f40f9dbe8f81fccbFC16b9cb1",
        ],
        # ADDED 2026-09-20: the first Safe above is the identical address (not just
        # the same signers) that owns Pendle's Router on Plasma.
        "cross_ecosystem": "2026-09-20: identical Safe address 0x7877AdFa...75Ac also owns Pendle's Router on Plasma",
    },
    "curve": {
        "targets": ["0x8271e06E5887FE5ba05234f5315c19f3Ec90E8aD"],
        "known_eoa": ["0xabc336d4C71ad275695744d32DdB1d8266Db1cbF"],
        "safes": [],
        # ADDED 2026-09-20: a bare EOA, so the identical address is the identical key.
        "cross_ecosystem": "2026-09-20: identical admin bare EOA 0xabc336d4...1cbF is also the StableSwap factory admin on Monad",
    },
    "meridian_perps": {
        "targets": ["0xD540F47F214dC7D6D244E62A6aE7e06B586Ef44A"],
        "known_eoa": ["0x39C647fdd8524c69be3E05A754bD63E02b019D75"],
        "safes": [],
    },
    "longbow": {
        "targets": [
            "0x026df18fbd2A7639089D0a16293383ec687A5Ca1",
            "0x65dC90cd3a0BCDE967c8AE6019d6790b616E78F7",
            "0xe129D4Cb2d454C4ACFAc909d1576453A9b835f61",
        ],
        "known_eoa": [],
        "safes": [
            "0x396ae0BD5623c3750e15fd222770F1e972153ED4",
            "0xe600452658762042749eb8e11955542B7EBeA4Bb",
        ],
    },
    "chainlink_admin": {
        # New in batch 8: owner() on 7 independently-sampled Chainlink feeds
        # (including the stock_tokens group's own price feeds) all resolve to
        # this one Safe -- added here specifically to check whether it shares
        # any signer with any other tracked group.
        "targets": ["0xEE27D5aE494300902D90454E8630a3f1c68C9c52"],
        "known_eoa": [],
        "safes": ["0xEE27D5aE494300902D90454E8630a3f1c68C9c52"],
    },
    "layerzero_infra": {
        # New in batch 8: EndpointV2/SendUln302/ReceiveUln302 share one owner,
        # a bespoke (non-Safe) 5-of-7 multisig -- resolved via the
        # getSigners()/threshold() fallback added to _safe_owners() this batch.
        "targets": [
            "0x6F475642a6e85809B1c36Fa62763669b1b48DD5B",
            "0xC39161c743D0307EB9BCc9FEF03eeb9Dc4802de7",
            "0xe1844c5D63a9543023008D332Bd3d2e6f1FE1043",
        ],
        "known_eoa": [],
        "safes": ["0xE590a6730D7a8790E99ce3db11466Acb644c3942"],
    },
    # Batch 9: four Safe-rooted targets. Each Safe's owners were compared live
    # against every group above (and against each other) before being added --
    # verified zero overlap, not a silent default 100.
    "pancakeswap_v3": {
        "targets": ["0x0BFbCF9fa4f9C56B0F40a671Ad40E0805A091865"],
        "known_eoa": [],
        "safes": ["0xfa206DAB60c014bEb6833004D8848910165e6047"],
    },
    "sushiswap_v3": {
        "targets": ["0xE51960f1B45f1C9FB6D166E6a884F866fC70433B"],
        "known_eoa": [],
        "safes": ["0x6fA4080b70eed82Cf48570DDE705026905a64657"],
    },
    "symbiosis": {
        "targets": ["0x292fC50e4eB66C3f6514b9E402dBc25961824D62"],
        "known_eoa": [],
        "safes": ["0x0605963420C4e8566fCEf2CF65Dcd575662bF53d"],
    },
    "strato_bridge": {
        "targets": ["0x0dc846db6a4eC7b5a3e542F7db88049E9ADd2541"],
        "known_eoa": [],
        "safes": ["0x8c458F866e603335ef179A63a2528F357732f5d5"],
    },
    "fables": {
        # batch 10 (2026-09-17): sole ADMIN_ROLE holder on the FablesPoolRegistry's
        # AccessManager, an EIP-7702-delegated EOA (real activity, 470 txs -- not a
        # bridge alias like uniswap_stack's entry, a genuinely private-key-controlled
        # address). Listed in known_eoa for the same reason: the overlap check needs
        # one root identity to compare against every other group's signers.
        "targets": ["0x159a113E012593d9B3Cc63aD45e30F0467e13ef3"],
        "known_eoa": ["0x359856655934338D798f9CCE1f181486301D36a5"],
        "safes": [],
    },
    "beefy": {
        # batch 10 (2026-09-17): representative vault only (SPY-WETH). Real 3-of-6
        # Safe holds PROPOSER_ROLE/CANCELLER_ROLE on both the vault- and
        # strategy-level TimelockControllers.
        "targets": ["0x87673A619Fc4F3Fc08068A0BB04f60aA2D04ca62"],
        "known_eoa": [],
        "safes": ["0x000000a151650b85742d8c286E09ABa7bE9BDB82"],
    },
    "morpho_blue": {
        "targets": ["0x9D53d5E3bd5E8d4Cbfa6DB1ca238AEA02E651010"],
        "known_eoa": [],
        "safes": ["0x060595638692de6CCd47ca04094F1772D3D39728"],
        # ADDED 2026-09-20: different Safe address per chain (CREATE2-per-chain),
        # identical owner set; see data/finding_2026-09-19-base-morpho-blue-robinhood-overlap.md.
        "cross_ecosystem": "2026-09-20: same 9-signer 5-of-9 Safe committee as the Morpho Blue owner Safes on Base, Ethereum L1 and Tempo",
    },
    "noxa_fun": {
        # Rotation audit index 9 (2026-09-19): NOXA Fun Launch Locker, bare EOA
        # owner confirmed live on 2 RPCs (nonce 45, active key). Own standalone
        # group -- not yet found to share a root signer with any other tracked
        # target's group.
        "targets": ["0x7F03effbd7ceB22A3f80Dd468f67eF27826acD85"],
        "known_eoa": ["0x7E035Fb048a31e0481b88074557415b1C187242B"],
        "safes": [],
    },
    "uncx_v3_locker": {
        # Rotation audit index 10 (2026-09-19): UNCX Network's V3 Liquidity
        # Locker, a lead left open across index 8 and index 9's own audits,
        # resolved this pass once the real uncx-network GitHub org's source
        # was found and cross-checked against the deployed bytecode (see
        # score_uncx_v3_locker()'s docstring). owner() confirmed the same
        # real 2-of-3 Safe on 2 RPCs. UNCX's second locker (unicrypt-v4)
        # shares this exact Safe but is not yet a tracked target (its own
        # contract source not located this pass) -- if/when it is scored,
        # add its address to this SAME group rather than a new one.
        #
        # 2026-09-20 (rotation audit index 16): DONE, exactly as that note
        # asked. The V4 locker 0x128A800c...603A is now scored
        # (score_uncx_v4_locker()) and joins this group rather than getting
        # one of its own, because owner() on BOTH lockers re-reads live to
        # the SAME Safe 0x31c44A17...9693 on both mainnet RPCs. Consequence
        # worth stating: adding it does NOT change any crossExposureScore --
        # the penalty counts OTHER groups sharing a signer, and this adds a
        # target to an existing group, not a group.
        "targets": [
            "0xF28704c691290547924e2129D407dA36bda8ce0f",
            "0x128A800cBc615cc110Bff16E475865c67631603A",
        ],
        "known_eoa": [],
        "safes": ["0x31c44A17aa2E639B40f33DA805CB1DB55d969693"],
    },
    "orvex": {
        # Rotation audit index 16 (2026-09-20). ONE group for all three Orvex
        # targets, not three: they share their roots. The bare EOA
        # 0x3b2b572C...2F14 is owner() of BOTH the V2 PairFactory and the V4
        # Vault; the Safe 0x9DB42D3B...1A53 (3-of-7, v1.3.0, no module, guard
        # slot zero) is owner() of the V4 PoolManager AND of the V2
        # ProxyAdmin AND is the V4 Vault's pendingOwner (offered, not
        # accepted, as of 2026-09-20). All re-read live on both mainnet RPCs.
        # The 7 Safe owners are re-derived live by compute_cross_exposure()
        # itself, not hardcoded here.
        "targets": [
            "0x5c98b2d892b37c9a1D3b69472bdDc172A64CdC09",
            "0xd01C774d4A66408326Bc65728Ac5Ae5aAf004032",
            "0xFe7E25dE55e5cBbEcCcb661F3679F873f72B9b0D",
        ],
        "known_eoa": ["0x3b2b572C56dD96B351ceB95c53e7EdB97BF42F14"],
        "safes": ["0x9DB42D3BDA1525963db3B2372C4DAABaf0491A53"],
    },
    "snuggle": {
        # batch 11 (2026-09-17): MaxFi Robinhood vault (Snuggle white-label). One
        # plain bare EOA (no code, 759 txs on this chain) is both ProxyAdmin.owner()
        # and vault.owner() -- listed in known_eoa as the group's root identity.
        "targets": ["0x1195C074F898b7644bA732407619c9804dFE6DCE"],
        "known_eoa": ["0x6aC51A706539D4F5A326dA2892520180858e25FF"],
        "safes": [],
    },
    "pancakeswap_v2": {
        # rotation-audit batch (2026-09-18): PancakeSwap AMM (V2-style) Factory.
        # feeToSetter is a bare EOA, real activity (nonce 20) on this chain --
        # grepped across the whole repo before wiring this in, no textual match
        # against any other tracked group's known_eoa/safes; this module's own
        # live Safe-owner re-derivation is the authoritative check.
        "targets": ["0x02a84c1b3BBD7401a5f7fa98a384EBC70bB5749E"],
        "known_eoa": ["0xD09971D8ed6C6a5e57581e90d593ee5B94e348D4"],
        "safes": [],
    },
}


# ADDED 2026-09-20: flat score for a group flagged "cross_ecosystem" (same value the
# Arbitrum/Base/Plasma/Monad scorers hardcode for a committee shared with another chain).
_CROSS_ECOSYSTEM_SCORE = 80


def compute_cross_exposure(w3) -> dict:
    """Returns {target_address: crossExposureScore} for every address across all
    groups. Re-derives every Safe's owner set live (never trusts this module's own
    hardcoded lists as ground truth for the OWNERS -- only the Safe/EOA addresses
    themselves are fixed inputs, discovered and documented in prior batches).

    Return shape is unchanged (scores only) so score_all() and every caller keep
    working; the per-target explanation of a cross-ecosystem cap comes from
    compute_cross_exposure_with_notes()."""
    return compute_cross_exposure_with_notes(w3)[0]


def compute_cross_exposure_with_notes(w3) -> tuple:
    """Returns (scores, notes): `scores` is exactly what compute_cross_exposure()
    returns; `notes` is {target_address: [str, ...]} for every target whose group
    carries the optional "cross_ecosystem" key (targets of unflagged groups get no
    entry). ADDED 2026-09-20: the plain score alone would read 80 with no visible
    reason for a group that has no within-Robinhood overlap at all.

    A flagged group scores min(within-Robinhood score, 80): never raises a score the
    within-Robinhood rule already lowered (a group at 40 stays 40).

    ADDED 2026-09-22, REVISED same day after adversarial review found the first version incomplete:
    `_safe_owners` now raises RpcUnavailable (not the same bare None a confirmed revert produces) on
    a persistent network failure -- see its own docstring. This function does NOT catch it. A first
    version tried to: mark just the OWNING group unresolved and force its own score to 100. That
    looked "surgical" but was wrong -- `registry` is GLOBAL and shared (built once, across every
    group, before any group is scored), so the missing Safe's owners silently vanish from every
    OTHER group's overlap count too, not just the owning group's. A group with NO Safe of its own
    (all known_eoa) can never be marked unresolved yet still gets its score silently pulled up by
    the same missing signer set -- proven on the REAL registry (arcus/arcus_perps_bridgevault,
    pancakeswap_v2/v3, the steakhouse family): rate-limiting arcus's one Safe fixed arcus's own
    score (100, with a note) but left arcus_perps_bridgevault silently wrong (100, no note),
    reproducing exactly the direction this whole fix exists to close. This module already documents
    the same registry-vs-scoring-loop separation for a DIFFERENT case (a statically `unresolved_note`
    group's signers still leaking into the shared registry, see
    data/finding_2026-09-18-signer-overlap-unresolved-note-registry-leak.md) -- there the leak
    happens to penalize the wrong group (safe direction), here it would have favored it (dangerous
    direction), which is why this needed its own fix rather than reusing that one's shape.
    A per-group fix can't be made sound without knowing what the unresolved Safe's real owners
    were, which is exactly the one thing a failed read can't tell you. Letting RpcUnavailable
    propagate out of this whole function is smaller AND correct: score_all() (scripts/lib/scorers.py)
    already wraps its ONE call to this function in a try/except that sets every target's
    crossExposureScore to 100 with an explicit "NOT a confirmed no-overlap result" note -- the exact
    fallback this needed, already built and already load-bearing for any other failure in this
    function, not a new convention."""
    registry = {}  # signer -> set of group keys
    group_all_signers = {}

    for key, g in GROUPS.items():
        signers = set(Web3.to_checksum_address(a) for a in g.get("known_eoa", []))
        for safe_addr in g.get("safes", []):
            owners = _safe_owners(w3, safe_addr)  # raises RpcUnavailable on a persistent network
            # failure -- deliberately NOT caught here, see the docstring above.
            if owners is None:
                continue
            signers.update(owners)
        group_all_signers[key] = signers
        for s in signers:
            registry.setdefault(s, set()).add(key)

    result = {}
    notes = {}
    for key, g in GROUPS.items():
        if g.get("unresolved_note"):
            score = 100  # not-applicable, matches this project's existing convention
        else:
            shared_groups = set()
            for s in group_all_signers[key]:
                shared_groups.update(registry[s] - {key})
            score = max(0, 100 - 20 * len(shared_groups))
        cross_ecosystem = g.get("cross_ecosystem")
        note = None
        if cross_ecosystem:
            within = score
            score = min(within, _CROSS_ECOSYSTEM_SCORE)
            if within < _CROSS_ECOSYSTEM_SCORE:
                note = (
                    f"crossExposureScore = {score}: within-Robinhood signer sharing already scores below "
                    f"the cross-ecosystem cap of {_CROSS_ECOSYSTEM_SCORE}, so the lower value is kept; "
                    f"this committee is ALSO shared with a tracked target on another ecosystem "
                    f"({cross_ecosystem})"
                )
            else:
                note = (
                    f"crossExposureScore = {score} (would be {within} on within-Robinhood sharing alone): "
                    f"this target's root committee is identical to a tracked target's on another ecosystem "
                    f"({cross_ecosystem}); real finding, verified by scripts/check_cross_ecosystem_overlap.py"
                )
        for target in g["targets"]:
            addr = Web3.to_checksum_address(target)
            result[addr] = score
            # last group wins for a target listed twice, same as `result` itself
            if note:
                notes[addr] = [note]
            else:
                notes.pop(addr, None)
    return result, notes
