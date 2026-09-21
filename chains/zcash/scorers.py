"""
Zcash authority scorers -- 4 flagship targets (2026-09-17, EXT added same
day as a follow-up).

Unlike `chains/solana`, `chains/hyperliquid` and `chains/tempo` (each
promoted the same day from an already-tested 0-100 numeric mapping), this
file is the FIRST numeric mapping for Zcash: `METHODOLOGY.md` section 4
gives measurable inputs and qualitative rules per dimension, but no
methodology-test pass had yet turned them into deterministic formulas (no
"4.6"/"4.1 numeric mapping" section exists there the way it does for the
other three ecosystems). The formulas below are that missing step, written
directly against this file rather than a separate methodology-test
document, and are disclosed as first-pass judgment calls where the
underlying methodology doc itself says the input is not yet solid (see
each function's docstring). Two of Zcash's own methodology drafts were
already rejected twice for overstating confidence (METHODOLOGY.md section
7) -- the discipline here is the same: score what is live-verified and
defensible, leave the rest as a disclosed open item rather than a
plausible-looking number.

Reuses the read-only primitives already built and live-tested in
`scripts/zcash_read.py`, `scripts/p2sh_spends.py` and
`scripts/miner_concentration.py` (the latter two refactored 2026-09-17 into
importable functions -- both used to run entirely at module import time
with no callable entry point, verified behavior-identical against
METHODOLOGY.md section 3.2/3.4's already-documented live values before and
after: same (m,n)/pubkeys for both funds, same 3/1 addresses-to-exceed
50%/25%, same 93 unattributed blocks).

Targets scored: the two protocol-defined fund multisigs (ZIP 271 one-time
lockbox `t3ev37...`, the ZCG funding stream `t3cFfPt1...`), the L1
baseline (consensus-rule-change authority, keyed per METHODOLOGY.md section 4's target-type table and its
proposed `address(uint160(uint256(keccak256("zcash:mainnet:<id>"))))`
scheme), and (added 2026-09-17, same day, as a follow-up once resolved)
`EXT`: the NEAR PoA bridge representation `zec.omft.near`. METHODOLOGY.md
section 8 had this open ("Identify the NEAR contract that controls
zec.omft.near minting and its signer set") -- resolved by fetching
`github.com/near/intents`'s `contracts/poa/factory/src/contract.rs` source
(a `near_plugins` access-control-gated factory, `omft.near`) and reading
its live role holders. `POOL` (Sapling/Orchard/Ironwood shielded value
pools) is deliberately and PERMANENTLY not given a 0-100 score, not a
placeholder gap -- see
`data/pool_trusted_setup_disclosure_2026-09-17.md`: the only candidate
input (whether at least one Groth16 trusted-setup ceremony participant was
honest) is an unfalsifiable historical-trust question no live read can
ever confirm, unlike every other score in this project.

Added 2026-09-18: `score_maya_asgard_vault()`, the new `XVAULT` target type
(METHODOLOGY.md section 4's target-type table and new section 4.7) --
Maya Protocol's Asgard TSS vaults, which hold real native ZEC.ZEC on Zcash
Mainnet itself (not a Zcash protocol-defined `FUND`, not an off-Zcash
`EXT` representation: the mirror image of `zec.omft.near`, identified but
deliberately left unscored by `data/scouting_candidates_2026-09-18.md`
pending exactly this methodology decision). See METHODOLOGY.md section 3.6
for the live-verified vault facts and the TSS required-signers formula's
primary-source citation (Mayanode's own bifrost go-tss code, not assumed
from the THORChain-fork convention).
"""
import math
import os
import sys

from eth_utils import keccak, to_checksum_address

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "scripts"))
from p2sh_spends import find_multisig_spends  # noqa: E402
from miner_concentration import compute_concentration  # noqa: E402
from zcash_read import grpc, decode, taddr_balance  # noqa: E402
import near_read as nr  # noqa: E402
import maya_read as mr  # noqa: E402
import zenrock_read as zr  # noqa: E402
from zcash_retired_targets import RETIRED_TARGETS  # noqa: E402

# METHODOLOGY.md section 4 (target types): "the methodology phase must fix a deterministic mapping
# such as address(uint160(uint256(keccak256("zcash:mainnet:<id>"))))" -- this
# is that fix, same last-20-bytes-of-keccak256 scheme already used for
# Hyperliquid's own address-less L1 target.
L1_TARGET_ID = to_checksum_address(keccak(text="zcash:mainnet:l1")[-20:])

PRIMARY_HOST = "zec.rocks:443"
SECOND_HOST = "zcash.mysideoftheweb.com:9067"          # independent second operator (METHODOLOGY.md section 2)
CONC_WINDOW = 2000          # METHODOLOGY.md 4.2 / 4.6: blocks in the concentration sample
CONC_CONFIRMATIONS = 10     # stay below both operators' tips so both serve the same blocks
LINEAGE_SAMPLE_HOST = "eu.zec.rocks:443"                 # load-balanced domain observed serving both Zebra and Zakura backends

FUNDS = {
    "ZIP 271 one-time lockbox disbursement": {
        "address": "t3ev37Q2uL1sfTsiJQJiWJoFzQpDhmnUwYo",
        "scanStart": 3146400, "scanEnd": 3486400, "window": 50000,
    },
    "ZCG funding stream (FS_FPF_ZCG_H3)": {
        "address": "t3cFfPt1Bcvgez9ZbMBFWeZsskxTkPzGCow",
        "scanStart": 3475800, "scanEnd": 3485800, "window": 1000,
    },
}

# Dated, citation-only research findings (not live-derived, so kept separate from
# score_fund()'s own live-read notes) -- appended to the matching fund's `notes`
# by score_all() below. See METHODOLOGY.md section 8 for the full sourcing and
# section 3.2 for the resulting update to the "key holders not named" line.
FUND_STATIC_NOTES = {
    # Resolved 2026-09-19 (partial): the ADMINISTERING ENTITY is named and
    # documented in primary sources; the specific on-chain key holders are not.
    "t3cFfPt1Bcvgez9ZbMBFWeZsskxTkPzGCow": [
        "Administering entity per ZIP 1015 (§'Financial Privacy Foundation') and "
        "ZIP 1016 line 130 (github.com/zcash/zips zip-1016.md, read 2026-09-19): the "
        "Financial Privacy Foundation (FPF), a Cayman Islands-incorporated nonprofit "
        "-- confirmed operating and reporting publicly via its own quarterly reports "
        "(financialprivacyfoundation.org/post/fpf-q2-2026-report, released 2026-07-08).",
        "The specific individual or sub-entity holders of this address's 2-of-3 "
        "on-chain keys are NOT named in any primary source found this pass (ZIP "
        "1015, ZIP 1016, zcashcommunitygrants.org, FPF's own Q2/Q1 2026 and Q4 2025 "
        "reports, forum.zcashcommunity.com search) -- this is a real gap, not "
        "carried over unchecked from the prior pass. Do NOT conflate with ZIP 271's "
        "explicitly named Key-Holder Organizations (Zcash Foundation, Electric Coin "
        "Company, Shielded Labs) for the OTHER fund (t3ev37...): ZIP 271's own text "
        "scopes that naming to its own one-time lockbox disbursement only, and at "
        "least one secondary/AI-generated search summary conflated the two funds "
        "during this research pass, caught and rejected by checking ZIP 271's raw "
        "source directly rather than trusting the summary.",
    ],
    # Resolved 2026-09-19: real coinholder votes under ZIP 1016 have occurred.
    "t3ev37Q2uL1sfTsiJQJiWJoFzQpDhmnUwYo": [
        "ZIP-1016-governed coinholder votes on this fund's Coinholder-Controlled Fund "
        "HAVE occurred, contrary to treating the low transparent outflow above as "
        "evidence the mechanism is untested or unused: the 'Coinholder-Directed "
        "Retroactive Grants Program' (forum.zcashcommunity.com/t/nu6-1-coinholder-"
        "directed-retroactive-grants-program/51713, dated July 2025) explicitly "
        "operationalizes ZIP 1016 ('Under this model, ZIP 1016 states: 12% of block "
        "rewards will flow to the Coinholder Grants Program from November 2025 until "
        "Zcash's third halving'). An inaugural vote closed 2025-11-26 (9 proposals, "
        "5 approved, more than 1,000,000 ZEC voted on most questions -- comfortably "
        "over ZIP 1016's 420,000 ZEC threshold), a Q1 2026 round and a Q4 2025 "
        "disbursement round also completed; a Q2 2026 round was explicitly "
        "postponed to Q3 2026 'due to ongoing work on the Ironwood upgrade' (FPF Q2 "
        "2026 report, financialprivacyfoundation.org, released 2026-07-08). The low "
        "transparent outflow from this address is therefore better read as "
        "consistent with ZIP 271's own shielded-disbursement design (3.2) than as a "
        "sign the governance process itself is dormant.",
    ],
}

NEAR_PRIMARY_RPC = "https://rpc.mainnet.near.org"
NEAR_SECOND_RPC = "https://free.rpc.fastnear.com"  # independent second operator, matches METHODOLOGY.md 3.5's own supply cross-check
ZEC_OMFT_TOKEN = "zec.omft.near"
ZEC_OMFT_FACTORY = "omft.near"

# zenZEC's dMPC keyring on Zenrock's own zrchain Mainnet (`diamond-1`) -- discovered
# 2026-09-19 (data/zenzec_mpc_keyring_2026-09-19.md) by a live `zrchain.dct.Query/
# QueryParams` read (the address is `x/dct`'s live `DepositKeyringAddr` for
# `ASSET_ZENZEC`, NOT the placeholder in zrchain's own `keeper/params.go`
# `DefaultParams()`, which a live `KeyringByAddress` query against this exact RPC
# resolves to "not found" -- a dev/test fixture, not the deployed value). Same
# "hardcode the discovered address, live-read what can change" convention as
# `FUNDS` above: the keyring's identity is fixed here, but its `parties`/
# `party_threshold` are read fresh from chain on every run, because x/identity's
# own `message_add_keyring_party.go`/`message_remove_keyring_party.go` mean they
# are NOT a cryptographic commitment the way a P2SH `HASH160` is.
ZENZEC_KEYRING_ADDR = "keyring1k6vc6vhp6e6l3rxalue9v4ux"
# The two Zcash-side infrastructure Key IDs this same live QueryParams read
# resolved for ASSET_ZENZEC (`rewards_deposit_key_id`, `change_address_key_ids[0]`).
# NOT the bulk deposit-custody address(es): Zenrock's own `docs/README.md` deposit
# sequence (`data/scouting_candidates_2026-09-18.md`) generates a FRESH Zcash key
# per user deposit, so no small fixed set of "vault" addresses exists the way Maya
# Protocol's two Asgard vaults do -- these two are the only ZEC-side addresses
# nameable from public on-chain config at all, checked here for exactly that reason.
ZENZEC_INFRA_KEY_IDS = {"rewards_deposit": 387, "change_address": 388}
# STATUS FLAG (2026-09-20, see data/zenzec_status_2026-09-20.md). The only zrchain node that answers reports
# this height and no newer block; the product behind the keyring (zenZEC) shows every sign of a wind-down.
# The composite of this target is therefore a dated reading of the keyring's structure, never a live one.
# The flag drops itself the moment the node moves, and asks for a human re-read instead of staying silent.
ZENZEC_FROZEN_HEIGHT = 9_534_552
ZENZEC_FROZEN_AS_OF = "2026-08-10T23:19:52Z"

def _composite(admin_key, multisig, timelock):
    # Exact integer arithmetic: floor(0.4a + 0.3m + 0.3t + 0.5) in binary floating point comes out one LOWER than
    # the exact value for 2054 of the 1,030,301 possible (a, m, t), for example (0, 1, 24) -> 7 instead of 8. No
    # published score is affected (checked over every live oracle entry); this removes the latent bias.
    return (4 * admin_key + 3 * multisig + 3 * timelock + 5) // 10


def admin_key_score_kn(k, n):
    # Same ladder already established for a raw k-of-n signature threshold
    # in chains/hyperliquid/scripts/methodology_test.py (admin_key_score)
    # and chains/tempo/scripts/methodology_test.py (admin_key_score, rule
    # R4) -- Zcash's P2SH m-of-n redeem script is the same primitive class
    # (a bare signature threshold, no vote-permission bitmask or role
    # system layered on top), so this reuses that exact ladder rather than
    # inventing a new one for a structurally identical mechanism.
    if k >= 3:
        return 65
    if k == 2:
        return 50
    return 10 if n == 1 else 5


def multisig_score_kn(k, n):
    # Same formula already established for a raw k-of-n threshold in the
    # Hyperliquid/Tempo methodology tests (Tempo's floored version, R5):
    # max(16, min(100, 20k - (n-k))). Reused for the same reason as
    # admin_key_score_kn above.
    return max(16, min(100, 20 * k - (n - k)))


# METHODOLOGY.md 4.2 "Unresolved P2SH" rule (fixed 2026-09-17 run2, methodology test):
# a P2SH address commits only to HASH160(redeem script). Until a spend reveals the
# script (or when the revealed script is not a recognised constraint-only m-of-n,
# or the two lightwalletd operators disagree), its threshold is UNRESOLVED. The
# score is the lowest value the 4.6 k-of-n ladder can give ANY real P2SH m-of-n
# script (1-of-N: adminKey 5, multisig 16), flagged as unresolved -- never the
# out-of-ladder 0 the discovery draft proposed, and never the previous 20/20
# placeholder, which scored an unknown script ABOVE a known 1-of-3 (5/18).
_UNRESOLVED_P2SH_ADMIN_KEY = 5
_UNRESOLVED_P2SH_MULTISIG = 16


def _suffix_is_constraint_only(op: str, suffix_hex) -> bool:
    """METHODOLOGY.md 4.2: bytes after OP_CHECKMULTISIG(VERIFY) can change what the
    script means (e.g. `OP_CHECKMULTISIG OP_DROP OP_1` is anyone-can-spend). Accept
    only: no suffix after OP_CHECKMULTISIG; after OP_CHECKMULTISIGVERIFY, zero or
    more `<push 1..75 bytes> OP_DROP` pairs followed by `OP_DEPTH OP_0 OP_EQUAL`
    (the ZCG address's observed nonce + clean-stack pattern) or by `OP_1`.
    Anything else is treated as unresolved, not guessed."""
    suffix = bytes.fromhex(suffix_hex) if suffix_hex else b""
    if op == "CHECKMULTISIG":
        return suffix == b""
    if op != "CHECKMULTISIGVERIFY":
        return False
    i = 0
    while i < len(suffix) and 1 <= suffix[i] <= 75:
        ln = suffix[i]
        if i + 1 + ln >= len(suffix) or suffix[i + 1 + ln] != 0x75:  # OP_DROP
            return False
        i += 2 + ln
    return suffix[i:] in (bytes.fromhex("740087"), bytes.fromhex("51"))


def _observed_lineages(host=LINEAGE_SAMPLE_HOST, samples=12):
    """Live count of distinct `nodeSubversion` strings observed on a
    load-balanced domain known to route to multiple backend operators
    (METHODOLOGY.md 3.1). This is a genuinely different, more solid
    measurement than "lineage SHARE of nodes/hashrate", which
    METHODOLOGY.md section 8 explicitly flags as unmeasured ("a one-off
    handshake survey gave unstable results and is not used") -- counting
    distinct version strings from repeated samples of one load-balanced
    endpoint is a much weaker claim (it says nothing about the two
    lineages' relative share of the network) but is itself reproducible
    and live-checkable, unlike a P2P crawl this project cannot run.

    Returns the RAW set of observed version strings -- whether each one is
    an INDEPENDENT lineage or a fork is a separate, non-live judgment, see
    `_KNOWN_FORK_PREFIXES` and `_independent_lineage_count` below. Do not
    feed this set's length directly into a score."""
    seen = set()
    for _ in range(samples):
        for num, v in decode(grpc(host, "GetLightdInfo", b"")[0]):
            if num == 14:
                seen.add(v.decode())
    return seen


# DATED interpretive fact, NOT re-derivable from a live version string alone
# (same "dated, not re-checked every run" convention as
# _MEDIAN_SCHEDULED_NOTICE_DAYS above): METHODOLOGY.md section 3.1 read
# Zakura's own README ("forked from Zebra") and Cargo.toml (renamed forks of
# Zebra's own proving crates, still depending on upstream zcash_protocol/
# zcash_script) and concluded Zakura is a declared fork, not an independent
# implementation -- a bug or change in the shared upstream code reaches
# both. A live GetLightdInfo read can confirm Zakura is STILL RUNNING (the
# _observed_lineages() call above), but not whether it remains a fork -- if
# Zakura ever diverges from Zebra's crates, this needs a manual update
# backed by the same kind of primary-source read, not a bigger sample size.
_KNOWN_FORK_PREFIXES = ("/Zakura:",)


def _independent_lineage_count(observed_versions):
    independent = {v for v in observed_versions if not v.startswith(_KNOWN_FORK_PREFIXES)}
    return len(independent) if independent else 1  # never 0: at least Zebra itself must be running for Mainnet to exist


def _admin_key_score_l1(independent_count):
    """Ladder written for this pass (no prior methodology-test number to
    reuse, unlike the other three ecosystems' L1 targets). Judgment call,
    disclosed rather than presented as mechanically derived:

    - 1 independent lineage (today's live state: Zebra, with Zakura a
      declared fork sharing upstream proving-system crates, METHODOLOGY.md
      3.1) scores ABOVE Hyperliquid's equivalent L1 admin score of 15
      ("single closed-source signing key, auto-pulled, no public source to
      audit") because Zebra's source IS public and auditable -- but still
      low, and specifically NOT scored as if that mitigant were reliable:
      METHODOLOGY.md 3.1 and 4.3 already document one real precedent where a
      Mainnet rule change (the 2026-06 emergency Orchard-disabling soft
      fork, zcashd v6.12.4) shipped via a release with NO public tag in the
      official repository -- a "public source" claim that did not hold for
      at least one real, disclosed incident.
    - Higher bands (2, 3+ genuinely independent lineages) are written for
      forward-compatibility and transparency, matching this project's
      convention of publishing a full ladder even when only its lowest rung
      is reachable today (same pattern as Hyperliquid/Tempo's L1 formulas)
      -- untested against any real multi-lineage Zcash state, since none
      exists yet."""
    if independent_count <= 1:
        return 20
    if independent_count == 2:
        return 45
    return 65


# DATED historical fact, NOT re-derived live every run (same convention as
# scripts/lib/scorers.py's EthenaTimelockController "zero CallScheduled
# history" note): recomputing this would mean re-scanning GitHub release
# timestamps and historical block headers across every past upgrade tag on
# every scorer run, for a fact about upgrades that already activated and
# will not change. Source: METHODOLOGY.md section 4.3's table, itself
# produced by scripts/notice_period.py against live lightwalletd reads on
# 2026-09-17. Median of the three SCHEDULED Zebra-lineage upgrades this
# project measured (NU6 23.8 days, NU6.1 39.2 days, NU6.3 17.7 days) =
# 23.8 days -- update this constant (and re-run notice_period.py) the next
# time a new network upgrade activates, not on every score_l1() call.
_MEDIAN_SCHEDULED_NOTICE_DAYS = 23.8
# One real precedent (METHODOLOGY.md 3.1/4.3): the 2026-06 emergency
# Orchard-disabling soft fork shipped via a release with literally ZERO
# public notice (no tag in the public repository before activation) --
# this caps timelockScore well below what 23.8 days alone would suggest,
# the same "instant-bypass exists, cap below the clean value" convention
# already used for USDtb PSM's freeze bypass and the Ethena LayerZero
# OFTAdapters' setPeer bypass on the Ethereum L1 side of this project.
_EMERGENCY_BYPASS_TIMELOCK_CAP = 35


def _timelock_score_l1():
    return _EMERGENCY_BYPASS_TIMELOCK_CAP


def score_l1() -> dict:
    """Zcash L1 (consensus-rule-change authority). See METHODOLOGY.md
    section 4's `L1` row across 4.1-4.5 for the qualitative rules this
    function turns into numbers, and the docstrings of
    `_admin_key_score_l1`/`_timelock_score_l1` above for the specific
    judgment calls made where the methodology doc itself flags an input as
    not yet solid (section 8's open questions)."""
    notes = []

    observed = _observed_lineages()
    independent = _independent_lineage_count(observed)
    notes.append(
        f"{LINEAGE_SAMPLE_HOST}: {len(observed)} distinct nodeSubversion string(s) observed over 12 samples: {sorted(observed)} "
        f"-- {independent} counted as independent (Zakura excluded as a declared fork of Zebra, DATED finding, see this module's docstring)"
    )

    # FIXED 2026-09-17 run2 (methodology test): the window used to be the frozen range
    # 3,483,700-3,485,699, so "recent blocks" (METHODOLOGY.md 4.2) silently aged on every
    # run. It is now the 2,000 blocks ending CONC_CONFIRMATIONS below the lower of the two
    # operators' tips, computed on both operators; any disagreement degrades.
    tips = []
    for host in (PRIMARY_HOST, SECOND_HOST):
        tips.append(next(v for num, v in decode(grpc(host, "GetLightdInfo", b"")[0]) if num == 7))
    end = min(tips) - CONC_CONFIRMATIONS
    start = end - CONC_WINDOW + 1
    conc = compute_concentration(PRIMARY_HOST, start, end, step=200)
    conc2 = compute_concentration(SECOND_HOST, start, end, step=200)
    k50, k25 = conc["addressesToExceed50Pct"], conc["addressesToExceed25Pct"]
    if (conc2["blocks"], conc2["addressesToExceed50Pct"], conc2["addressesToExceed25Pct"]) != (conc["blocks"], k50, k25) or conc["blocks"] != CONC_WINDOW:
        notes.append(f"concentration cross-check FAILED on {start}-{end}: {PRIMARY_HOST} blocks={conc['blocks']} k50={k50} k25={k25} vs "
                     f"{SECOND_HOST} blocks={conc2['blocks']} k50={conc2['addressesToExceed50Pct']} k25={conc2['addressesToExceed25Pct']}")
        k50 = k25 = None
    else:
        notes.append(f"coinbase payout concentration, blocks {start}-{end} ({conc['blocks']} blocks, identical k50/k25 on {PRIMARY_HOST} and {SECOND_HOST}): "
                     f"{k50} payout addresses exceed 50%, {k25} exceed 25% -- payout addresses are an UPPER bound on independent "
                     f"entities (one operator can use several addresses), so this multisigScore is an upper bound (METHODOLOGY.md 4.2)")

    admin_key = _admin_key_score_l1(independent)
    multisig = min(100, 15 * k50 + 5 * k25) if (k50 and k25) else 20
    if not (k50 and k25):
        notes.append("miner-concentration read did not fully resolve this run -- multisigScore degraded, treat as unverified")
    timelock = _timelock_score_l1()
    notes.append(
        f"timelockScore capped at {_EMERGENCY_BYPASS_TIMELOCK_CAP} despite a {_MEDIAN_SCHEDULED_NOTICE_DAYS}-day median "
        f"notice for scheduled upgrades (DATED fact, see this module's docstring) -- the 2026-06 emergency Orchard-disabling "
        f"soft fork shipped with zero public notice, a proven bypass of the scheduled-upgrade norm"
    )

    return {
        "target": L1_TARGET_ID, "label": "Zcash L1 (consensus-rule-change authority)",
        "adminKeyScore": admin_key, "multisigScore": multisig, "timelockScore": timelock,
        "oracleAuthorityScore": 100, "crossExposureScore": 100,
        "compositeScore": _composite(admin_key, multisig, timelock),
        "notes": notes,
    }


def score_fund(label: str, address: str, scan_start: int, scan_end: int, window: int) -> dict:
    """One protocol-defined fund multisig. See METHODOLOGY.md section 3.2
    for the ZIP 271 / ZCG background and section 4.1-4.5 `FUND` rows.

    Root key = the (m, n) revealed by the most recent real spend's redeem
    script (`OP_CHECKMULTISIG`/`OP_CHECKMULTISIGVERIFY`), cross-checked
    live against a second, independent lightwalletd operator -- never
    silently trusting one source: if the two disagree on the revealed
    (m, n) or pubkey set, the target degrades to the METHODOLOGY.md 4.2
    unresolved-P2SH floor (5/16, composite 7) with a note saying so,
    matching the hard cross-RPC requirement already established in
    `chains/tempo/scripts/methodology_test.py`'s `call2()`. (Until
    2026-09-20 this docstring said it "raises"; the code has always
    degraded instead.)

    timelockScore is 0 by METHODOLOGY.md's own explicit ruling (4.3): "No
    delay: a 2-of-3 spend settles after normal confirmations. ZIP 1016
    quarterly votes and 30-day review are off-chain context, not a
    timelock" -- not re-derived here, just applied."""
    notes = []
    primary = find_multisig_spends(PRIMARY_HOST, address, scan_start, scan_end, window)
    second = find_multisig_spends(SECOND_HOST, address, scan_start, scan_end, window)
    real_spends_p = [s for s in primary["spends"] if "m" in s]
    real_spends_s = [s for s in second["spends"] if "m" in s]
    notes.append(f"{PRIMARY_HOST}: {primary['spendsFound']} spend(s) found scanning {primary['scannedTxs']} txs")

    def _unresolved(reason, pubkeys=frozenset()):
        notes.append(f"threshold UNRESOLVED ({reason}) -- METHODOLOGY.md 4.2 unresolved-P2SH floor "
                     f"(adminKey {_UNRESOLVED_P2SH_ADMIN_KEY}, multisig {_UNRESOLVED_P2SH_MULTISIG}), not a measured threshold")
        return {
            "target": address, "label": label,
            "adminKeyScore": _UNRESOLVED_P2SH_ADMIN_KEY, "multisigScore": _UNRESOLVED_P2SH_MULTISIG, "timelockScore": 0,
            "oracleAuthorityScore": 100, "crossExposureScore": None,
            "compositeScore": _composite(_UNRESOLVED_P2SH_ADMIN_KEY, _UNRESOLVED_P2SH_MULTISIG, 0),
            "notes": notes, "_pubkeys": set(pubkeys), "_degraded": True,
        }

    if not real_spends_p:
        return _unresolved("no spend revealing a recognised m-of-n redeem script in the scanned range on the primary host")

    latest = real_spends_p[-1]
    m, n, pubkeys = latest["m"], latest["n"], set(latest["pubkeys"])
    if n != len(latest["pubkeys"]) or not 1 <= m <= n:
        return _unresolved(f"revealed script is malformed: m={m} n={n} with {len(latest['pubkeys'])} pubkeys")
    if not _suffix_is_constraint_only(latest["op"], latest.get("suffix")):
        return _unresolved(f"revealed script has an unrecognised suffix after {latest['op']}: {latest.get('suffix')}")
    # A P2SH address commits to exactly one redeem script (its HASH160), so every spend
    # reveals the same script: the threshold cannot change without moving funds to a
    # new address. "Most recent" is therefore any valid spend, not a moving value.

    if real_spends_s:
        latest_s = real_spends_s[-1]
        cross_matched = (latest_s["m"], latest_s["n"], set(latest_s["pubkeys"])) == (m, n, pubkeys)
        notes.append(f"{SECOND_HOST}: cross-checked latest spend's (m,n,pubkeys) -- {'MATCH' if cross_matched else 'MISMATCH, degrading'}")
        if not cross_matched:
            return _unresolved("the two lightwalletd operators disagree on the revealed script", pubkeys)
    else:
        notes.append(f"{SECOND_HOST}: no multisig spend found to cross-check against this run -- proceeding on the primary host alone, not the usual two-source guarantee")

    admin_key = admin_key_score_kn(m, n)
    multisig = multisig_score_kn(m, n)
    timelock = 0  # METHODOLOGY.md 4.3: no on-chain delay on a fund spend; off-chain votes are not a timelock
    notes.append(f"threshold {m}-of-{n} (revealed on chain by the spend at height {latest['height']}; fixed for this address by its HASH160 commitment)")

    return {
        "target": address, "label": label,
        "adminKeyScore": admin_key, "multisigScore": multisig, "timelockScore": timelock,
        "oracleAuthorityScore": 100, "crossExposureScore": None,  # filled in by cross_exposure()
        "compositeScore": _composite(admin_key, multisig, timelock),
        "notes": notes, "_pubkeys": pubkeys, "_degraded": False,
    }


def cross_exposure(fund_results: list):
    """METHODOLOGY.md 4.5: 'The two on-chain funds use disjoint public keys
    ... re-check at every spend.' Live pubkey-set comparison, not a
    snapshot trusted from the methodology doc's own prior finding.

    FIXED 2026-09-17 (closed a bug hunt finding): this used to unconditionally
    overwrite crossExposureScore (and append a confident "confirmed disjoint"
    note) for EVERY result, including ones score_fund() had already degraded
    to crossExposureScore=None because no spend was found this run, or the
    two hosts disagreed -- clobbering an honest "unresolved" state with a
    false "confirmed disjoint" claim built from incomplete or mismatched
    pubkey data. A degraded result's `_degraded` flag is now checked first;
    its crossExposureScore/notes/compositeScore are left exactly as
    score_fund() set them."""
    for i, r in enumerate(fund_results):
        if r["_degraded"]:
            continue
        others_sharing = [
            o["label"] for j, o in enumerate(fund_results)
            if j != i and not o["_degraded"] and o["_pubkeys"] and r["_pubkeys"] & o["_pubkeys"]
        ]
        r["crossExposureScore"] = max(0, 100 - 20 * len(others_sharing))
        if others_sharing:
            r["notes"].append(f"shares at least one signer pubkey with: {others_sharing}")
        else:
            r["notes"].append("signer pubkeys confirmed disjoint from every other tracked Zcash fund this run")
        r["compositeScore"] = _composite(r["adminKeyScore"], r["multisigScore"], r["timelockScore"])
    for r in fund_results:
        del r["_pubkeys"]
        del r["_degraded"]


def _near_read_cross_checked(fn, *args):
    """Every NEAR read below is taken on NEAR_PRIMARY_RPC and re-checked
    against NEAR_SECOND_RPC -- raises rather than trusting one source on
    disagreement, the same hard cross-RPC requirement Tempo's call2()
    already established for this project (stronger than an optional
    separate pass)."""
    primary = fn(NEAR_PRIMARY_RPC, *args)
    second = fn(NEAR_SECOND_RPC, *args)
    if primary != second:
        raise RuntimeError(f"NEAR RPC disagreement on {fn.__name__}{args}: {primary!r} vs {second!r}")
    return primary


def score_ext_zec_omft() -> dict:
    """zec.omft.near -- the NEAR-side PoA (Proof of Authority) bridge
    representation of ZEC (METHODOLOGY.md 3.5, target type `EXT`). Scored
    with the "host-chain method" METHODOLOGY.md 4.4 already specifies for
    EXT targets: the authority that matters is whoever can mint new
    zec.omft.near tokens, read from the NEAR contract that actually
    controls that, not from a Zcash-side read (nothing on Zcash constrains
    this bridge's own mint authority).

    Contract source: `github.com/near/intents`,
    `contracts/poa/factory/src/contract.rs`. `zec.omft.near` is deployed
    and administered by a factory contract, `omft.near`, which gates
    `ft_deposit` (the function that actually mints/credits new
    zec.omft.near balance -- METHODOLOGY.md's own "the oracle for 'ZEC was
    deposited'") behind a `near_plugins` access-control role check:
    `Role::DAO` OR `Role::TokenDepositer`. Live-read root-control set
    (`acl_get_permissioned_accounts()`, cross-checked against a second NEAR
    RPC, disagreement raises rather than trusting one source):

    - `Role::TokenDepositer` grantees: `bridge-mng.near` (a bare NEAR
      account, confirmed live via `view_access_key_list` to hold exactly
      ONE full-access key -- functionally a single-key EOA equivalent, not
      a multisig of any kind) and `int-mnt-dao.sputnik-dao.near` (a Sputnik
      DAO v2 instance). Either alone can mint -- this is an OR grant, not
      an AND.
    - The DAO's own `get_policy()` (also cross-checked) shows its
      "Requestor" role (the group whose members can both propose AND vote
      to execute a "call"-type action, which is what a mint call is) has
      only 3 members, with `vote_policy.call = {quorum: 0, threshold: 1}`
      -- a single vote from ANY ONE of those 3 members passes the
      proposal outright, no minimum participation required. Structurally
      a 1-of-3 signature threshold, not a real majority-vote DAO for this
      specific action class.
    - `Role::DAO` (also mint-capable, and the only role that can add/
      remove other roles or full-access keys on the factory itself) is
      held solely by a DIFFERENT Sputnik DAO, `intents.sputnik-dao.near`,
      whose "council" role has 5 members and a genuinely strong
      `threshold: [79, 100]` (79%) for the same "call" action class --
      this path is NOT the weakest and does not drive the score below, but
      is disclosed for the contrast: the headline governance DAO is real
      and strong, but day-to-day minting does not have to go through it.

    Weakest key by this project's established (k, -n) ordering (lower k
    weaker, then larger n weaker): comparing bridge-mng.near (k=1, n=1)
    against the Requestor group (k=1, n=3) -- equal k, larger n is weaker,
    so the Requestor group's 1-of-3 is the binding constraint, not the
    single bare key. Scored with the SAME `admin_key_score_kn`/
    `multisig_score_kn` ladder already used for Zcash's own P2SH funds
    above (a bare signature/vote threshold is the same primitive class
    regardless of which chain enforces it).

    No delay of any kind exists on this path (`quorum=0` means a single
    vote can also execute immediately, not just approve) --
    timelockScore=0. No price read -- oracleAuthorityScore=100.
    `crossExposureScore`=100: NEAR account IDs and Zcash P2SH pubkeys are
    different key spaces entirely, so a comparison against the tracked
    Zcash funds above is not meaningful (not run through the same check as
    a result, disclosed rather than silently 'checked and found clean').
    `l1CappedComposite` is deliberately NOT computed for this target: the
    cap models "could a Zcash rule change override this," which does not
    apply here -- this bridge's mint authority is entirely off-Zcash and
    would be unaffected by any Zcash consensus rule change."""
    notes = []

    acl = _near_read_cross_checked(nr.permissioned_accounts, ZEC_OMFT_FACTORY)
    depositer_grantees = acl["roles"]["TokenDepositer"]["grantees"]
    notes.append(f"omft.near acl_get_permissioned_accounts(): Role::TokenDepositer grantees = {depositer_grantees}")

    bare_account = next((a for a in depositer_grantees if "sputnik-dao" not in a), None)
    dao_account = next((a for a in depositer_grantees if "sputnik-dao" in a), None)

    candidates = []
    if bare_account:
        keys = _near_read_cross_checked(nr.access_key_count, bare_account)
        k, n = 1, len(keys)
        notes.append(f"{bare_account}: {n} full-access key(s) -- single-signer path, (k={k}, n={n})")
        candidates.append((k, n, bare_account))
    if dao_account:
        policy = _near_read_cross_checked(nr.dao_policy, dao_account)
        requestor = next((r for r in policy["roles"] if r["name"] == "Requestor"), None)
        if requestor:
            group = requestor["kind"]["Group"]
            vp = requestor["vote_policy"].get("call", requestor.get("vote_policy", {}).get("*", {}))
            threshold = vp.get("threshold")
            n = len(group)
            # FIXED 2026-09-17 (closed a bug hunt finding): Sputnik DAO v2's
            # vote_policy.threshold can be either a "Weight" (plain string
            # vote count, e.g. "1") or a "Ratio" ([numerator, denominator],
            # e.g. [79, 100] -- confirmed live in THIS SAME deployment
            # family, intents.sputnik-dao.near's council role uses exactly
            # this shape). Only the string form was parsed; a Ratio-shaped
            # threshold silently resolved k=None and dropped this candidate
            # from the weakest-key comparison instead of being read.
            if isinstance(threshold, str):
                k = int(threshold)
            elif isinstance(threshold, (list, tuple)) and len(threshold) == 2 and threshold[1]:
                num, denom = threshold
                k = math.ceil(num * n / denom)
            else:
                k = None
            notes.append(f"{dao_account}: Requestor group n={n}, call vote_policy threshold={threshold} quorum={vp.get('quorum')} -> (k={k}, n={n})")
            if k is not None:
                candidates.append((k, n, dao_account))
        else:
            notes.append(f"{dao_account}: no 'Requestor' role found in get_policy() this run -- could not resolve a (k,n) for this path")

    if candidates:
        k, n, weakest_via = min(candidates, key=lambda c: (c[0], -c[1]))
        notes.append(f"weakest key by (k, -n) ordering: {weakest_via} at (k={k}, n={n})")
        admin_key = admin_key_score_kn(k, n)
        multisig = multisig_score_kn(k, n)
    else:
        # The unresolved floor of every other Zcash target (METHODOLOGY.md 4.2, the floor of the 4.6 ladder: 5/16), never above a confirmed
        # real path: the live-confirmed weakest key here (the Requestor group, 1-of-3) scores 5/18. The old 20/20 ranked
        # an unknown above a known 1-of-3 (data/finding_2026-09-18-cross-ecosystem-unresolved-floor-inversion.md).
        admin_key, multisig = 5, 16
        notes.append("no TokenDepositer path resolved to a (k,n) this run -- degraded rather than guessing")

    timelock = 0  # quorum=0 on the DAO path means even the strongest available path here has no enforced delay; the weaker path (single key / 1-of-3) certainly doesn't either

    return {
        "target": ZEC_OMFT_TOKEN, "label": "zec.omft.near (NEAR PoA bridge, ZEC)",
        "adminKeyScore": admin_key, "multisigScore": multisig, "timelockScore": timelock,
        "oracleAuthorityScore": 100, "crossExposureScore": 100,
        "compositeScore": _composite(admin_key, multisig, timelock),
        "notes": notes,
    }


def tss_required_signers(n: int) -> int:
    """Minimum number of a Maya Protocol Asgard vault's `n` TSS members that
    must co-sign to move funds -- METHODOLOGY.md section 3.6/4.7.

    NOT assumed from the generic "THORChain-fork uses a 2/3 majority"
    convention `data/scouting_candidates_2026-09-18.md` flagged as an open
    item ("the actual signing threshold ... was NOT confirmed from a
    primary source this pass"). Instead read from Mayanode's own source
    (`gitlab.com/mayachain/mayanode`, commit `ad1072c33ca2091fe12917de2321578474e3e3eb`,
    2026-09-17, the `develop` HEAD at read time):

    - `bifrost/tss/go-tss/conversion/conversion.go` `func GetThreshold(value int)`:
      `threshold := int(math.Ceil(float64(value)*2.0/3.0)) - 1`
    - This exact `threshold` is the value every keygen/keysign call site in
      `bifrost/` passes straight into the underlying tss-lib ceremony as
      `btss.NewParameters(curve, ctx, partyID, len(partiesID), threshold)`
      (`bifrost/tss/go-tss/keygen/ecdsa/tss_keygen.go` line 84,
      `tss_keysign.go` line 106, and 6 more call sites, `grep -rn
      "conversion.GetThreshold(" bifrost/` in the cloned repo) -- called
      with `len(localStateItem.ParticipantKeys)`, i.e. THIS vault's own
      live `membership` count, not a network-wide constant.
    - tss-lib's own (t, n) convention: a degree-`t` Feldman/Shamir
      polynomial needs `t + 1` shares to reconstruct or co-sign. So the
      real minimum co-signer count is `threshold + 1 = ceil(n * 2/3)`,
      which is what this function returns -- not the raw `GetThreshold()`
      return value itself (that is the polynomial DEGREE, one less).

    Disclosed limitation: this is inferred from the generic keygen/keysign
    code path that every TSS ceremony on Mayanode uses, not from a field
    the REST API labels "signing threshold" for a specific vault -- no
    such field was found on `/mayachain/vaults/asgard`. If a future
    Mayanode release changes this formula, this constant must be
    re-derived from the source at that time, the same "dated interpretive
    fact" caveat already applied to Zakura's fork status in `score_l1()`.
    """
    return math.ceil(n * 2 / 3)


def score_maya_asgard_vault(vault: dict, other_vaults: list) -> dict:
    """One Maya Protocol Asgard vault (target type `XVAULT`, METHODOLOGY.md
    section 4.7) holding native ZEC.ZEC on Zcash Mainnet, controlled by an
    external network's own TSS validator set rather than a Zcash P2SH
    script or a Zcash protocol-defined fund. `vault` is one entry from
    `maya_read.active_zec_vaults()`: `{pub_key, ledger_amount_zat,
    zec_address, membership}`.

    adminKeyScore/multisigScore reuse the SAME bare-(k,n)-threshold ladder
    already applied to Zcash's own P2SH funds above and to
    `zec.omft.near`'s DAO Requestor group -- a TSS threshold signature is
    the same primitive class (a bare signer-count threshold, no role
    system or vote-permission bitmask layered on top), so this is the same
    reuse this module's docstrings already establish as precedent, not a
    new judgment call.

    timelockScore = 0: no on-chain delay of any kind gates a completed TSS
    signature from broadcasting, the same "FUND multisig: no delay" ruling
    METHODOLOGY.md 4.3 already makes for a Zcash P2SH spend.

    `l1CappedComposite` is deliberately NOT computed, same reasoning as
    `score_ext_zec_omft()`: this target's controlling authority (Mayachain's
    own TSS validator set) is entirely off-Zcash and would be unaffected by
    any Zcash consensus rule change. Unlike `EXT`, the ZEC itself sits ON
    Zcash Mainnet in an ordinary-looking P2PKH address -- but Zcash L1
    governance has no NAMED, targeted power over this specific address the
    way it does over a `FUND` (a protocol-defined recipient enforced by
    consensus itself); every other ZEC holder is equally subject to the
    same generic consensus rules, so that is not a targeted authority
    relationship worth capping against.
    """
    notes = []
    addr = vault["zec_address"]
    n = len(vault["membership"])
    k = tss_required_signers(n)
    notes.append(
        f"mayanode.mayachain.info /mayachain/vaults/asgard (SINGLE SOURCE -- no second independent "
        f"Mayachain full-node API could be found/verified reachable this pass, see maya_read.py's "
        f"module docstring for the hostnames probed): membership n={n} TSS signer pubkeys for this vault"
    )
    notes.append(
        f"required co-signers k=ceil(2n/3)={k} of n={n} -- Mayanode's own bifrost go-tss "
        f"conversion.GetThreshold() formula (commit ad1072c3, 2026-09-17), see tss_required_signers() docstring"
    )

    bal_primary = taddr_balance(PRIMARY_HOST, addr)
    bal_second = taddr_balance(SECOND_HOST, addr)
    ledger = vault["ledger_amount_zat"]
    if bal_primary != bal_second:
        notes.append(f"BALANCE MISMATCH between {PRIMARY_HOST} ({bal_primary} zat) and {SECOND_HOST} "
                      f"({bal_second} zat) -- degrading, live balance figure below unverified this run")
        balance = None
    else:
        balance = bal_primary
        notes.append(f"live on-chain balance {balance} zat, identical on {PRIMARY_HOST} and {SECOND_HOST}")
        if balance != ledger:
            notes.append(
                f"Mayanode-internal ledger for this vault says {ledger} zat -- differs from the live "
                f"on-chain balance by {ledger - balance} zat. NOT reconciled this pass: an earlier draft "
                f"of this note pointed to a specific /mayachain/queue/outbound entry (~2,206,088,478 zat) "
                f"as a plausible cause, but independent re-checks of that same endpoint within the same "
                f"day attributed that amount to DIFFERENT vault_pub_key values on different reads -- the "
                f"queue is live and mutates (entries get processed/resubmitted) faster than it can be "
                f"cross-checked, so amount-matching against it is NOT a reliable way to attribute a "
                f"specific entry to this vault, and no confirmed explanation for the gap exists. "
                f"Disclosed as genuinely unresolved, not smoothed over -- see METHODOLOGY.md section 3.6"
            )

    # METHODOLOGY.md 4.7 (last row): the halted/paused status of the ZEC chain is disclosed in the notes, from
    # /mayachain/inbound_addresses, and never folded into a dimension: it is a fact about current flow, not about
    # who controls the vault. A failed or empty read is disclosed as unread, never guessed and never fatal.
    try:
        zec_status = next((c for c in (mr.inbound_addresses() or []) if c.get("chain") == "ZEC"), None)
        if zec_status is None:
            notes.append("ZEC chain status on Mayachain: not listed in /mayachain/inbound_addresses this run "
                         "(halted/paused status unread; not a scoring input)")
        else:
            notes.append(
                f"ZEC chain status on Mayachain (/mayachain/inbound_addresses, single source): "
                f"halted={zec_status.get('halted')}, chain_trading_paused={zec_status.get('chain_trading_paused')} "
                f"-- a fact about current flow, not about who controls the vault, so not folded into any score")
    except Exception as e:
        notes.append(f"ZEC chain halted/paused status unread this run ({type(e).__name__}) -- disclosed, "
                     f"not a scoring input")

    admin_key = admin_key_score_kn(k, n)
    multisig = multisig_score_kn(k, n)
    timelock = 0

    others_sharing = [
        ov["zec_address"] for ov in other_vaults
        if ov["zec_address"] != addr and set(ov["membership"]) & set(vault["membership"])
    ]
    cross_exposure = max(0, 100 - 20 * len(others_sharing))
    if others_sharing:
        notes.append(f"shares at least one TSS signer node with: {others_sharing}")
    else:
        notes.append(f"TSS membership set confirmed DISJOINT (0 shared signer nodes) from every other "
                      f"active Maya Asgard vault holding ZEC this run ({len(other_vaults)} other(s) checked)")

    return {
        "target": addr, "label": f"Maya Protocol Asgard vault {vault['pub_key'][:24]}... (native ZEC custody, TSS)",
        "adminKeyScore": admin_key, "multisigScore": multisig, "timelockScore": timelock,
        "oracleAuthorityScore": 100,  # no price/data feed read gates this target
        "crossExposureScore": cross_exposure,
        "compositeScore": _composite(admin_key, multisig, timelock),
        "notes": notes,
    }


def score_zenzec_mpc_keyring() -> dict:
    """RETIRED from the live set on 2026-09-20 (METHODOLOGY.md 4.8.1, `zcash_retired_targets.RETIRED_TARGETS`):
    `score_all()` no longer calls this; it is reachable only through `score_all(include_retired=True)`, which
    re-derives a commitment made BEFORE the retirement. Its record as anchored is in
    `data/legacy_snapshot_zenzec_keyring_2026-09-20.json`.

    Zenrock's `zenZEC` custody keyring (target type `MPCKEYRING`,
    METHODOLOGY.md section 4.8) -- resumes the lead
    `data/scouting_candidates_2026-09-18.md` deferred, unscored, the day
    before: real, non-trivial ZEC value (494.51 zenZEC, live Solana mainnet
    read, independently corroborated by CoinDesk/Bitget) custodied by an
    off-Zcash dMPC signer network, but with a per-deposit FRESHLY GENERATED
    Zcash key model that does not fit `XVAULT` (Maya's 2 fixed, enumerable
    Asgard vaults) as written. Zenrock's own hosted docs and REST/LCD
    gateway were still down on RE-CHECK 2026-09-19 (`docs.zenrocklabs.io`
    HTTP 402, `api.diamond.zenrocklabs.io` HTTP 503, same failure as
    2026-09-18, not a stale check) -- resolved instead via hand-built ABCI
    queries against zrchain's own Tendermint RPC, see
    `scripts/zenrock_read.py`'s module docstring for the full method, and
    `data/zenzec_mpc_keyring_2026-09-19.md` for every cross-check performed.

    Target type decision (closes scouting's open item 1): the authority
    scored here is the KEYRING (`x/identity`'s `Parties`/`PartyThreshold` --
    "the number of parties required to submit signed txs" for every key that
    keyring ever generates, including a brand-new per-deposit one), not any
    single Zcash address -- matching scouting's own framing, "whoever can
    request/sign a new key," not "whoever holds vault address X." A bare
    `(k, n)` party threshold is the same primitive class already scored for
    Zcash's own P2SH `FUND`s and Maya's `XVAULT` TSS vaults, so
    `admin_key_score_kn`/`multisig_score_kn` are reused unchanged, the same
    precedent this file's docstrings already establish for every other
    bare-threshold target.

    `ZENZEC_KEYRING_ADDR` was discovered, not guessed: a live
    `zrchain.dct.Query/QueryParams` read resolved `ASSET_ZENZEC`'s live
    `DepositKeyringAddr` to this value -- NOT the placeholder hardcoded in
    zrchain's own `x/dct/keeper/params.go` `DefaultParams()`
    (`keyring1pfnq7r04rept47gaf5cpdew2`), which a live `KeyringByAddress`
    query against this exact RPC resolves to "not found: unknown request" (a
    dev/test fixture never deployed, confirmed by trying it, not assumed).
    That same live `QueryParams` read's `Solana.MintAddress` field
    (`JDt9rRGaieF6aN1cJkXFeUmsy7ZE4yY3CZb8tVMXVroS`) matches, byte for byte,
    the mint this project already independently verified live on Solana
    Mainnet RPC -- strong cross-source evidence this is the real deployed
    configuration, not a wrong or stale one, despite the reading node itself
    being stale (see below).

    Disclosed rather than smoothed over:
    - SINGLE SOURCE, DATED. Only `rpc.diamond.zenrocklabs.io` answered this
      pass; the chain-registry's second RPC operator
      (`rpc.zenrock.nodestake.org`) refused every connection. That one node
      reports its OWN sync state stuck at height 9,534,552 /
      2026-08-10T23:19:52Z with 0 p2p peers -- isolated, not proof the whole
      `diamond-1` Mainnet (which the chain-registry still lists "live") is
      halted, but no fresher zrchain endpoint could be found to confirm
      today's real tip. Every fact below is that ~40-day-old snapshot, not
      "today" -- and unlike a P2SH script's `HASH160` commitment, a
      Keyring's `parties`/`party_threshold` CAN change on-chain
      (`x/identity`'s own add/remove-party and update-keyring messages
      exist), so this reading could already be stale in a way a Zcash
      `FUND`'s threshold never can be.
    - Bulk custody address(es) still NOT determined -- CONFIRMS, not
      overturns, `data/scouting_candidates_2026-09-18.md`'s finding. The two
      Zcash-mainnet addresses this project COULD name from public on-chain
      config (`ZENZEC_INFRA_KEY_IDS`: the rewards-deposit and
      change-address keys) both independently re-derive correctly from
      their live on-chain pubkeys (this project's own P2PKH math matches
      zrchain's own reported address exactly, both keys) but hold 0 ZEC on
      BOTH of this project's own already-established lightwalletd operators
      today -- consistent with per-deposit ephemeral keys holding the real
      balance, not these two named infrastructure roles. No address holding
      the real ~494.51 zenZEC-equivalent of native ZEC was found or
      enumerated this pass (would need either the still-down indexer/REST
      API, or brute-forcing thousands of sequential Key IDs, not attempted).
    - Party identities are zrchain accounts, not named operators. Whether
      the 3 `Parties` map to 3 distinct physical institutions (Zenrock's own
      marketing claims "eight institutional operators", unverified secondary
      claim, see `data/scouting_candidates_2026-09-18.md`) was not checked
      this pass -- same class of disclosed gap as Maya's TSS "20 signers,
      not confirmed as 20 distinct companies."
    - Shared root with zenBTC. The SAME live `QueryParams` method against
      `zrchain.zenbtc.Query` resolves zenBTC's `DepositKeyringAddr` to this
      IDENTICAL keyring address -- this 3-of-3 signer set is Zenrock's
      shared core dMPC custody keyring across at least two wrapped assets,
      not something zenZEC-specific. Disclosed under crossExposureScore,
      not scored against it: zenBTC is not itself a target this Zcash
      scorer tracks (different chain/key space), the same "counted once,
      disclosed not scored twice" discipline METHODOLOGY.md 4.4 already
      applies to backend-lineage counting.
    - `x/policy` ("Approval policies and governance", per zrchain's own
      README module table) may impose additional signing constraints on top
      of the raw keyring threshold -- not checked this pass, an open item,
      not assumed irrelevant.

    `timelockScore` = 0: no on-chain delay of any kind gates a completed
    dMPC signature from broadcasting once the party threshold is met, the
    same "no delay" ruling already applied to a Zcash `FUND` P2SH spend
    (4.3) and to Maya's `XVAULT` TSS spends (4.7) -- `x/policy` aside (see
    above). `l1CappedComposite` deliberately NOT computed, same reasoning as
    `score_ext_zec_omft()`/`score_maya_asgard_vault()`: this target's
    controlling authority is entirely off-Zcash."""
    notes = []
    kr = zr.get_keyring(ZENZEC_KEYRING_ADDR)
    k, n = kr["party_threshold"], len(kr["parties"])
    frozen = int(kr["height"]) == ZENZEC_FROZEN_HEIGHT
    notes.append(
        f"STATUS: FROZEN SNAPSHOT, single source -- read at zrchain height {ZENZEC_FROZEN_HEIGHT} "
        f"(block time {ZENZEC_FROZEN_AS_OF}); the operating company behind zenZEC is in UK administration "
        "since 2026-04-08 and its ZEC backing sits at an address that is not derived from this keyring. "
        "Not a live risk reading; do not average or rank it with live targets. See "
        "data/zenzec_status_2026-09-20.md" if frozen else
        f"STATUS FLAG NEEDS REVIEW: the zrchain node's height is now {kr['height']}, no longer the frozen "
        f"{ZENZEC_FROZEN_HEIGHT}. Run scripts/zenzec_status_check.py and re-read data/zenzec_status_2026-09-20.md "
        "before presenting this score as live or as frozen."
    )
    notes.append(
        f"{zr.RPC_HOST}, height {kr['height']} (SINGLE SOURCE, DATED -- see this "
        f"function's docstring): keyring {ZENZEC_KEYRING_ADDR!r} ({kr['description']!r}) "
        f"is_active={kr['is_active']}, {len(kr['admins'])} admin(s), party_threshold={k} "
        f"of {n} parties -> (k={k}, n={n})"
    )
    if not (n and 1 <= k <= n):
        notes.append(f"malformed threshold read (k={k}, n={n}) -- degrading to the unresolved floor, not guessing")
        admin_key, multisig = 5, 16
    else:
        admin_key = admin_key_score_kn(k, n)
        multisig = multisig_score_kn(k, n)

    try:
        for role, key_id in ZENZEC_INFRA_KEY_IDS.items():
            key = zr.get_key_by_id(key_id)
            if key.get("keyring_addr") != ZENZEC_KEYRING_ADDR:
                notes.append(f"key {key_id} ({role}): keyring_addr {key.get('keyring_addr')!r} != expected {ZENZEC_KEYRING_ADDR!r} -- SKIPPED, not trusted")
                continue
            addr = key["wallets"].get("WALLET_TYPE_ZCASH_MAINNET")
            rederived = key.get("zcash_mainnet_address_rederived")
            if not addr or addr != rederived:
                notes.append(f"key {key_id} ({role}): chain-reported Zcash Mainnet address {addr!r} != independently re-derived {rederived!r} -- SKIPPED, not trusted")
                continue
            bal_p = taddr_balance(PRIMARY_HOST, addr)
            bal_s = taddr_balance(SECOND_HOST, addr)
            if bal_p != bal_s:
                notes.append(f"key {key_id} ({role}) {addr}: BALANCE MISMATCH {PRIMARY_HOST}={bal_p} vs {SECOND_HOST}={bal_s} zat -- unresolved this run")
            else:
                notes.append(f"key {key_id} ({role}) {addr}: {bal_p} zat on both {PRIMARY_HOST} and {SECOND_HOST} (address independently re-derived from the live on-chain pubkey, matches chain-reported)")
    except Exception as e:
        notes.append(f"infra-key balance cross-check did not complete this run -- {type(e).__name__}: {e} (does not affect the keyring threshold score above)")

    notes.append(
        "bulk per-deposit custody address(es) NOT enumerated this pass (no small fixed "
        "vault set exists, unlike Maya's XVAULT) -- value-at-risk is read from the "
        "wrapped-supply proxy on Solana instead, see data/zenzec_mpc_keyring_2026-09-19.md"
    )
    notes.append(
        "same keyring is live-confirmed as zenBTC's own DepositKeyringAddr too (zrchain.zenbtc.Query/QueryParams) "
        "-- a shared dMPC signer root across wrapped assets, disclosed here, not scored against crossExposureScore "
        "(zenBTC is not a target this Zcash scorer tracks, different key space)"
    )

    timelock = 0
    return {
        "target": ZENZEC_KEYRING_ADDR, "label": "Zenrock zenZEC dMPC custody keyring (\"Zenrock MPC\")",
        "adminKeyScore": admin_key, "multisigScore": multisig, "timelockScore": timelock,
        "oracleAuthorityScore": 100, "crossExposureScore": 100,
        "compositeScore": _composite(admin_key, multisig, timelock),
        "status": "frozen_snapshot" if frozen else "status_review_needed",
        "asOf": ZENZEC_FROZEN_AS_OF if frozen else None,
        "notes": notes,
    }


def score_all(_unused=None, include_retired=False) -> list:
    # Signature matches every other ecosystem's score_all(url) for the
    # update_scores.py harness's sake, even though Zcash's reads are fixed
    # lightwalletd endpoints (PRIMARY_HOST/SECOND_HOST above), not a
    # caller-supplied RPC URL.
    results = []
    try:
        l1 = score_l1()
        results.append(l1)
    except Exception as e:
        print(f"score_all(): SKIPPED Zcash L1 this run -- {type(e).__name__}: {e}")
        l1 = None

    fund_results = []
    for label, cfg in FUNDS.items():
        try:
            r = score_fund(label, cfg["address"], cfg["scanStart"], cfg["scanEnd"], cfg["window"])
            r["notes"].extend(FUND_STATIC_NOTES.get(cfg["address"], []))
            fund_results.append(r)
        except Exception as e:
            print(f"score_all(): SKIPPED {label} this run -- {type(e).__name__}: {e}")
    cross_exposure(fund_results)

    l1_composite = l1["compositeScore"] if l1 else None
    for r in fund_results:
        if l1_composite is None:
            r["l1CappedComposite"] = None
            r["notes"].append("l1CappedComposite not computed this run -- Zcash L1 score unavailable")
        else:
            r["l1CappedComposite"] = min(r["compositeScore"], l1_composite)
    results.extend(fund_results)

    try:
        results.append(score_ext_zec_omft())
    except Exception as e:
        print(f"score_all(): SKIPPED zec.omft.near this run -- {type(e).__name__}: {e}")

    try:
        active_vaults = mr.active_zec_vaults()
        for v in active_vaults:
            try:
                other = [ov for ov in active_vaults if ov["zec_address"] != v["zec_address"]]
                results.append(score_maya_asgard_vault(v, other))
            except Exception as e:
                print(f"score_all(): SKIPPED Maya vault {v.get('zec_address')} this run -- {type(e).__name__}: {e}")
    except Exception as e:
        print(f"score_all(): SKIPPED Maya Protocol Asgard vaults this run -- {type(e).__name__}: {e}")

    # RETIRED 2026-09-20 (zcash_retired_targets.RETIRED_TARGETS, the single switch): the Zenrock zenZEC keyring is a frozen
    # single-source snapshot of a product in wind-down, so while it is in that registry it is not part of the live set and of
    # no commitment built from a fresh run. It stays scorable, for one reason only: a commitment made BEFORE the retirement
    # contains it, and `attest_scores.py verify --live` re-derives such a bundle with include_retired=<the retired ids it
    # holds>. Removing it from the registry makes it live again (default run includes it).
    if include_retired is True:
        asked = set(RETIRED_TARGETS)
    else:
        asked = set(include_retired or ()) & set(RETIRED_TARGETS)
    if ZENZEC_KEYRING_ADDR not in RETIRED_TARGETS or ZENZEC_KEYRING_ADDR in asked:
        try:
            results.append(score_zenzec_mpc_keyring())
        except Exception as e:
            print(f"score_all(): SKIPPED Zenrock zenZEC MPC keyring this run -- {type(e).__name__}: {e}")

    return results
