"""scoring_build 2026-09-19: HIP-4 outcome-market deployers.

`data/finding_2026-09-19-section6-open-questions.md` section 3 found three
live mainnet HIP-4 outcome-deployer venues (`out` 3-of-4, `txyz` 2-of-3, `skew`
3-of-5) whose sub-deployers are all bare single keys, and left them at
scouting phase for two reasons: their economic weight had never been sized,
and a new controller shape needs a real scorer with tests. This module is that
scoring_build pass (adversarial review applied the same day, see
`data/scored_targets_2026-09-19-hip4-outcome-deployers.md` section 10). What it adds:

  * `score_hip4_outcome_deployer(venue)`: the scorer, parameterized by venue
    name exactly like `methodology_test.score_hip3_dex(name)` is by dex name.
    It is a generic function: any live venue can be scored with it, but only
    the venues that cleared the real-usage bar are wired into
    `scorers.py::SIMPLE_SCORERS` (none today: see `data/scored_targets_2026-09-19-
    hip4-outcome-deployers.md` for the sizing and the promote/hold decision).
  * `outcome_market_economics(venue, meta, ctx_by_coin)`: the economic-weight
    sizing, a pure function over two live payloads so it can be unit-tested
    without network access.

No new formula and no new constant. Every number is produced by functions
that already exist and were already adversarially reviewed
(`methodology_test.py`): `weakest`, `kn`, `admin_key_score`, `key_score`,
`composite`. The only judgment call is the ANALOGY that maps HIP-4's
settlement authority onto HIP-3's root-control machinery, made explicit here:

  HIP-3 dex                                   HIP-4 outcome venue
  ---------------------------------------     --------------------------------------
  root set = deployer + `haltTrading`         root set = deployer + `settleOutcome`
             sub-deployers (rule 4.2.3)                  and `settleQuestion` sub-deployers
  `setSubDeployers` is deployer-only          `setSubDeployers` is deployer-only
                                              (not in the sub-deployer variant list of
                                              the official HIP-4 deployer-actions page)
  oracle authority = weakest `setOracle` key  oracle authority = the same weakest key: the settle
                                              key supplies the result (`settleFraction`) itself;
                                              PARTIAL analogy, see "What the docs say" below
  no delay documented -> timelock 0           no delay documented for `settleOutcome`,
                                              `settleQuestion2` or `setSubDeployers`
                                              -> timelock 0 (METHODOLOGY.md 4.3)

Why settlement (and not registration) is the root-control action: an outcome
is fully collateralized (1 Yes + 1 No = 1 USDC, official HIP-4 overview), and
`settleOutcome`/`settleQuestion2` decide how that locked collateral is split
between holders. A sub-deployer holding either grant can therefore redirect
the venue's locked collateral without the deployer multisig, the same
"sub-deployers bypass a strong deployer multisig" shape as METHODOLOGY.md
4.2 rule 3.

The three registration variants are excluded from the root set. That is a
choice by analogy, NOT a finding that they are harmless. What the official
page says they can do: create markets and set `deployerFeeScale` in [0, 10] on
the new market (users then pay the base fee times `scale + max(scale, 1)`, up
to 20x, of which up to 10x goes to the deployer; the scale is visible per
market in `outcomeMeta`), and `registerAndAssociateNamedOutcomeFromTemplate`
adds an outcome to a LIVE question, crediting the holders of the question's
fallback-YES token with an equal balance of the new outcome's YES ("so existing
'other' positions keep their meaning"; designed to be neutral for existing
positions, not verified beyond that). None of them is documented to decide who
receives already-locked collateral, and HIP-3's `score_hip3_dex` likewise leaves
its non-halt sub-deployer variants (`registerAsset`, `setDeployerFees`, ...)
out of its root set. On all three live venues every sub-deployer holds ALL FIVE
variants, so the exclusion changes no live number; a venue with split grants
gets an `ifRegistrationOnlyKeysWereCounted` block in `reads` and a note, so the
reader sees how much the choice matters instead of trusting it.

What the docs say about settlement, and what they do not (official
deployer-actions page, read 2026-09-19). Documented: `settleFraction` is a
decimal in [0, 1]; a standalone outcome may settle to any fraction, an outcome
of a question only to exactly 0 or 1 with exactly one winner (sequentially, or
all at once with `settleQuestion2`); `nameAndDescription` and `sideNames` must
match the outcome exactly and `details` must be empty; a sub-deployer can only
settle the deployer's own outcomes and questions, so a compromised settle key
reaches that venue's book and no other. NOT documented: any delay, any check of
the value against the market's underlying, any bound on WHEN a settle may
happen, any dispute step. The `setOracle` analogy is therefore partial:
`setOracle` is a continuous push that the protocol clamps (1% per update, 2.5 s
apart, 10x from the day open, METHODOLOGY.md 4.4), while a settlement is a
one-shot, unclamped decision inside the [0, 1] / exactly-{0, 1} bounds. On-chain
history read the same day (data doc section 8) shows those two absences are
real, not just undocumented: settles executed before the market's stated time,
and 15 `binaryPrice` markets (template text: "resolves to Yes ... otherwise
resolves to No") were settled at 0.5. `oracleAuthorityScore` does not enter
`composite`, so this cannot move a headline number.

The only enforcement the page documents is that a market contradicting its
template's `semanticRestriction` is "malformed and slashable by validators". It
does not say that a wrong or early settlement is slashable, and it gives no
HIP-4 stake amount (each deployer delegates about 500K HYPE, a `delegatorSummary`
read, not a documented HIP-4 requirement). The scorer therefore records that as
context and does not credit it as a deterrent.

Grants the scorer does not know. The page lists exactly five `variant` names
and says the `settleQuestion` grant authorizes the `settleQuestion2` action,
i.e. the naming has already drifted once. A venue whose `subDeployers` holds a
non-empty grant outside those five makes `score_hip4_outcome_deployer` RAISE
(`Hip4ReadError`) instead of silently leaving that holder out of the root set:
classifying a new grant is a human decision, never a default.

Economic weight (how "real usage" is measured for this family). Open interest
has no direct analog because an outcome is not leveraged; the analog of "money
that a compromised root key could redirect" is the collateral locked behind
live outcomes. The API exposes it only indirectly, as per-side
`circulatingSupply` in `spotMetaAndAssetCtxs` (coins `#<10*outcome+side>`,
official asset-ids page); `totalSupply` on those coins is a protocol constant
(uint64 max scaled) and is not used. Full collateralization gives an exact
identity that this module CHECKS on every read instead of assuming:

  * standalone outcome:  Yes supply == No supply, collateral = Yes supply;
  * question with outcomes i = 0..N (fallback included): exactly one outcome
    settles Yes, so for every possible winner w
        Yes_w + sum(No_j for j != w) = collateral,
    which is equivalent to (Yes_i - No_i) being the SAME number D for every
    member i, with collateral = sum(No_i) + D. (`negate` and `merge` move
    supply between sides without changing this identity.)

A group whose supplies violate the identity, whose supplies are negative, or
whose market data is missing, is reported as UNVERIFIED and excluded from the
total; a missing value is never counted as zero. (With non-negative supplies the
identity cannot give a negative collateral: if D < 0 then every No_i >= -D, so
collateral >= (n - 1) * (-D) >= 0. That is why there is no separate negative-
collateral guard.) The two sides of a merged book report the same trades, so
24h volume is taken from ONE side (`dayBaseVlm` of the Yes coin, in shares); a
share pays at most 1 USDC, so shares are also the face-value volume in USDC.
`dayNtlVlm` is not used because the Yes and No coins report the same trade at
complementary prices.

Reproduction:
    python3 chains/hyperliquid/scripts/scoring_build_2026_09_19_hip4.py size            # all venues + the protocol-run recurring outcomes
    python3 chains/hyperliquid/scripts/scoring_build_2026_09_19_hip4.py size --history  # + 7 UTC days of face volume (slow, ~1 call per outcome)
    python3 chains/hyperliquid/scripts/scoring_build_2026_09_19_hip4.py venue out       # one venue's full scorer JSON
    python3 chains/hyperliquid/scripts/scoring_build_2026_09_19_hip4.py venue txyz
    python3 chains/hyperliquid/scripts/scoring_build_2026_09_19_hip4.py venue skew
    python3 chains/hyperliquid/scripts/scoring_build_2026_09_19_hip4.py history [venue]  # what the venue's keys did with settleOutcome (explorer, 300 latest txs per address)
    python3 chains/hyperliquid/scripts/scoring_build_2026_09_19_hip4.py cross-check     # one-off: every address in the tracked targets vs each venue's keys (slow, runs score_all())

Read-only: official HyperCore info API and HyperEVM RPC (chain 999). No
transaction, no key. HyperCore reads rest on a single operator's API (gap G9,
METHODOLOGY.md section 2), the same limitation every other HyperCore target
in this ecosystem carries.
"""
import calendar
import json
import os
import re
import statistics
import sys
import time
from decimal import Decimal, InvalidOperation

sys.path.insert(0, os.path.dirname(__file__))
import methodology_test as mt  # noqa: E402  (module attribute access on purpose: tests patch `mt.info` / `mt.evm`)

# Actions that decide who receives an outcome's locked collateral. `settleQuestion`
# is the grant name; per the official page it authorizes the `settleQuestion2` action.
HIP4_ROOT_CONTROL_VARIANTS = ("settleOutcome", "settleQuestion")
# Registration actions (create markets, set the fee scale, add an outcome to a live question). Left out of the root
# set BY ANALOGY with HIP-3, not because they are known to be harmless: see the module docstring.
HIP4_REGISTRATION_VARIANTS = (
    "registerStandaloneOutcomeFromTemplate",
    "registerQuestionFromTemplate",
    "registerAndAssociateNamedOutcomeFromTemplate",
)
# Read-only block-explorer endpoint (same operator as the info API): `userDetails` returns a user's 300 LATEST
# transactions, so every count derived from it is a lower bound over a window, never a total.
EXPLORER_URL = "https://rpc.hyperliquid.xyz/explorer"


class Hip4ReadError(Exception):
    """A HIP-4 API payload that is missing or does not have the documented
    shape. Raised (never swallowed) on the authority path so `score_all()`'s
    per-scorer isolation reports the target as SKIPPED instead of emitting a
    score computed from a guess."""


def _dec(value):
    """Decimal from an API string, or None when absent/unparseable. Callers
    treat None as 'unknown', never as zero."""
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _f(d):
    return float(d)


# ---------------------------------------------------------------- economic weight


def outcome_market_economics(venue, meta, ctx_by_coin):
    """Locked collateral and 24h volume of one venue's live outcomes.

    `venue` is the deployer's venue name; pass None for the protocol-run
    recurring outcomes (they carry no `venue` field). `meta` is the
    `outcomeMeta` payload, `ctx_by_coin` maps `#<encoding>` to its
    `spotMetaAndAssetCtxs` context. Pure: no I/O."""
    live = {o["outcome"]: o for o in meta.get("outcomes") or []}
    mine = {oid for oid, o in live.items() if o.get("venue") == venue}

    groups = []  # (kind, id, [live outcome ids])
    grouped = set()
    for q in meta.get("questions") or []:
        members = [m for m in [q.get("fallbackOutcome"), *(q.get("namedOutcomes") or [])] if m in live]
        if members and any(m in mine for m in members):
            groups.append(("question", q["question"], members))
            grouped.update(members)
    for oid in sorted(mine - grouped):
        groups.append(("standalone", oid, [oid]))

    total = Decimal(0)
    unverified = []
    for kind, gid, members in groups:
        if {live[m].get("venue") for m in members} != {venue}:
            unverified.append({"kind": kind, "id": gid, "why": "members span more than one venue"})
            continue
        rows, missing, negative = [], [], []
        for m in members:
            y, n = ctx_by_coin.get(f"#{10 * m}"), ctx_by_coin.get(f"#{10 * m + 1}")
            ys = _dec(y.get("circulatingSupply")) if y else None
            ns = _dec(n.get("circulatingSupply")) if n else None
            if ys is None or ns is None:
                missing.append(m)
            elif ys < 0 or ns < 0:
                negative.append(m)
            else:
                rows.append((ys, ns))
        if missing:
            unverified.append({"kind": kind, "id": gid, "why": f"no readable supply for outcome(s) {missing}"})
            continue
        if negative:
            unverified.append({"kind": kind, "id": gid, "why": f"negative supply for outcome(s) {negative}"})
            continue
        if kind == "standalone":
            (ys, ns), = rows
            if ys != ns:
                unverified.append({"kind": kind, "id": gid, "why": f"Yes supply {ys} != No supply {ns}"})
                continue
            total += ys
        else:
            diffs = {ys - ns for ys, ns in rows}
            if len(diffs) != 1:
                unverified.append({"kind": kind, "id": gid, "why": f"(Yes - No) differs across members: {sorted(str(d) for d in diffs)}"})
                continue
            # non-negative supplies (checked above) make a negative result impossible: see the module docstring
            total += sum((ns for _, ns in rows), Decimal(0)) + next(iter(diffs))

    shares24h = Decimal(0)
    both_sides = Decimal(0)
    traded = with_supply = sides_disagree = 0
    without_data = []
    for oid in sorted(mine):
        y, n = ctx_by_coin.get(f"#{10 * oid}"), ctx_by_coin.get(f"#{10 * oid + 1}")
        b0 = _dec(y.get("dayBaseVlm")) if y else None
        b1 = _dec(n.get("dayBaseVlm")) if n else None
        s0 = _dec(y.get("circulatingSupply")) if y else None
        s1 = _dec(n.get("circulatingSupply")) if n else None
        if b0 is None or b1 is None:
            without_data.append(oid)
            continue
        shares24h += b0
        traded += 1 if b0 > 0 else 0
        sides_disagree += 1 if b0 != b1 else 0
        with_supply += 1 if any(s is not None and s > 0 for s in (s0, s1)) else 0
        both_sides += sum((s for s in (s0, s1) if s is not None and s >= 0), Decimal(0))

    return {
        "venue": venue,
        "outcomesLive": len(mine),
        "questionsLive": sum(1 for g in groups if g[0] == "question"),
        "outcomesWithOutstandingSupply": with_supply,
        "outcomesTraded24h": traded,
        "lockedCollateralUsd": _f(total),
        "lockedCollateralFullyVerified": not unverified and not without_data,
        # Deliberately generous face-value reading (every outstanding Yes AND No share counted as 1 USDC,
        # ignoring the collateral identity): an upper bound used only to test that a decision does not
        # hinge on how conservatively collateral is measured.
        "sharesOutstandingBothSides": _f(both_sides),
        "unverifiedGroups": unverified,
        "outcomesWithoutMarketData": without_data,
        "shares24h": _f(shares24h),
        "face24hVolumeUsd": _f(shares24h),  # a share pays at most 1 USDC
        "volumeSidesDisagree": sides_disagree,
    }


def fetch_outcome_ctxs():
    """`#<encoding>` -> context, from the spot asset contexts (one call)."""
    resp = mt.info({"type": "spotMetaAndAssetCtxs"})
    return {c["coin"]: c for c in resp[1] if str(c.get("coin", "")).startswith("#")}


def venue_daily_face_volume(venue, meta, days=7, now_ms=None):
    """Face volume (shares, one side) per UTC day over the last `days` days
    for the venue's CURRENTLY LIVE outcomes. A lower bound on venue activity:
    outcomes that already settled are no longer listed, so their history
    cannot be summed. One `candleSnapshot` call per live outcome."""
    now_ms = now_ms or int(time.time() * 1000)
    start = now_ms - days * 86_400_000
    per_day = {}
    for o in meta["outcomes"]:
        if o.get("venue") != venue:
            continue
        candles = None
        for attempt in range(3):
            try:
                candles = mt.info({"type": "candleSnapshot", "req": {"coin": f"#{10 * o['outcome']}", "interval": "1d", "startTime": start, "endTime": now_ms}})
                break
            except Exception:
                time.sleep(1 + attempt)
        if candles is None:
            raise Hip4ReadError(f"candleSnapshot failed 3 times for outcome {o['outcome']}")
        for c in candles:
            day = time.strftime("%Y-%m-%d", time.gmtime(c["t"] / 1000))
            per_day[day] = per_day.get(day, 0.0) + float(c["v"])
    return dict(sorted(per_day.items()))


def _stated_time_ms(description):
    """The market's own stated time (`time` or `expiry` keyword, UTC `%Y%m%d-%H%M`) from an on-chain
    description `key:value|key:value`, in ms; None when absent or not in that format."""
    try:
        kv = dict(part.split(":", 1) for part in description.split("|"))
        stated = kv.get("time") or kv.get("expiry")
        return calendar.timegm(time.strptime(stated, "%Y%m%d-%H%M")) * 1000 if stated else None
    except (ValueError, TypeError, AttributeError):
        return None


def settlement_history(txs_by_addr, early_threshold_ms=3_600_000):
    """What the venue's own keys actually did with `settleOutcome`, from explorer
    transactions ({address: [tx]}, the shape of `userDetails`). Pure: no I/O.

    An outcome settled MORE than `early_threshold_ms` before the stated time of its own
    description is reported in `early` (with its settle fraction), and a settle within that
    margin of the stated time in `onTimeDelaySeconds` (per address: n / median / min / max of
    seconds after the stated time). Only successful actions (`error` null) are counted as
    settled; failed ones are counted apart. Counts are over the 300 latest transactions of
    each address: lower bounds."""
    total = errors = no_stated_time = 0
    by_template_fraction, early, delays, window = {}, [], {}, {}
    for addr, txs in sorted(txs_by_addr.items()):
        if txs:
            window[addr] = {"firstMs": min(t["time"] for t in txs), "lastMs": max(t["time"] for t in txs), "txs": len(txs)}
        for t in txs:
            op = (t.get("action") or {}).get("operation")
            body = op.get("settleOutcome") if isinstance(op, dict) else None
            if body is None:
                continue
            if t.get("error") is not None:
                errors += 1
                continue
            total += 1
            name, desc = body["nameAndDescription"]
            key = f"{name}|{body['settleFraction']}"
            by_template_fraction[key] = by_template_fraction.get(key, 0) + 1
            stated = _stated_time_ms(desc)
            if stated is None:
                no_stated_time += 1
            elif stated - t["time"] > early_threshold_ms:
                early.append({"address": addr, "outcome": body["outcome"], "template": name, "settleFraction": body["settleFraction"],
                              "settledAtMs": t["time"], "statedTime": desc, "hoursBeforeStatedTime": round((stated - t["time"]) / 3_600_000, 1), "hash": t["hash"]})
            elif abs(t["time"] - stated) <= early_threshold_ms:
                delays.setdefault(addr, []).append((t["time"] - stated) / 1000)
    return {
        "settleOutcomeSucceeded": total,
        "settleOutcomeFailed": errors,
        "settleOutcomeWithoutStatedTime": no_stated_time,
        "byTemplateAndFraction": dict(sorted(by_template_fraction.items())),
        "early": sorted(early, key=lambda e: e["settledAtMs"]),
        "onTimeDelaySeconds": {a: {"n": len(v), "median": round(statistics.median(v), 1), "min": round(min(v), 1), "max": round(max(v), 1)} for a, v in sorted(delays.items())},
        "windowByAddress": window,
        "limit": "explorer userDetails returns the 300 latest transactions per address: every count is a lower bound over that window",
    }


def fetch_settlement_history(venue=None):
    """`settlement_history` over the deployer and every sub-deployer of `venue`
    (all venues when None), read live from the explorer. Read-only."""
    meta = mt.info({"type": "outcomeMeta"})
    addrs = set()
    for d in meta["deployers"]:
        if venue is None or d.get("venue") == venue:
            addrs |= _venue_authority_addrs(d)
    if not addrs:
        raise Hip4ReadError(f"no active outcome deployer for venue {venue!r}")
    txs = {}
    for a in sorted(addrs):
        details = mt._post(EXPLORER_URL, {"type": "userDetails", "user": a})
        if not isinstance(details, dict) or not isinstance(details.get("txs"), list):
            raise Hip4ReadError(f"explorer userDetails({a}) has no 'txs' list")
        txs[a] = details["txs"]
    return settlement_history(txs)


# ---------------------------------------------------------------- scorer


def _lower_all(addrs):
    return [a.lower() for a in addrs]


def _venue_authority_addrs(d):
    """Every address holding ANY grant on this venue (used for cross-exposure
    and bytecode checks, like `score_hip3_dex`'s `root_keys`)."""
    addrs = {d["deployer"].lower()}
    for _variant, lst in d.get("subDeployers") or []:
        addrs |= set(_lower_all(lst))
    return addrs


def _hip3_dex_authority_addrs(x):
    addrs = {x["deployer"].lower()}
    if x.get("oracleUpdater"):
        addrs.add(x["oracleUpdater"].lower())
    for _variant, lst in x.get("subDeployers") or []:
        addrs |= set(_lower_all(lst))
    return addrs


def _root_keys(addrs):
    """The authority addresses plus the authorized users of each one that is a
    HyperCore multisig (METHODOLOGY.md 4.5)."""
    out = set()
    for a in addrs:
        out |= {u.lower() for u in mt.kn(a)[1]} | {a.lower()}
    return out


def _multisig_tree(addrs, max_depth=4):
    """Every HyperCore multisig reachable from `addrs` by following authorized
    users, nested multisigs included (cycles cut, depth capped). Returns
    ({address: (threshold, [authorized users])}, truncated). METHODOLOGY.md 4.2
    rule 2 does not expand nested multisigs into a score; this only DISCLOSES them.
    `truncated` is True when the depth cap left an address unexamined."""
    seen, tree = set(), {}
    frontier = sorted({a.lower() for a in addrs})
    for _ in range(max_depth + 1):
        nxt = []
        for a in frontier:
            if a in seen:
                continue
            seen.add(a)
            (k, _n), users = mt.kn(a)
            users = [u.lower() for u in users]
            if users != [a]:  # a bare key comes back as ((1, 1), [itself])
                tree[a] = (k, users)
                nxt += users
        frontier = nxt
    return tree, any(a not in seen for a in frontier)


def score_hip4_outcome_deployer(venue):
    meta = mt.info({"type": "outcomeMeta"})
    deployers = meta.get("deployers") if isinstance(meta, dict) else None
    if not isinstance(deployers, list):
        raise Hip4ReadError(f"outcomeMeta has no 'deployers' list (got {type(meta).__name__})")
    d = next((x for x in deployers if x.get("venue") == venue), None)
    if d is None:
        raise Hip4ReadError(f"no active outcome deployer for venue {venue!r} (live venues: {sorted(x.get('venue') for x in deployers)})")

    dep = d["deployer"].lower()
    sub = {variant: _lower_all(lst) for variant, lst in (d.get("subDeployers") or [])}
    unclassified = {v: lst for v, lst in sub.items() if lst and v not in HIP4_ROOT_CONTROL_VARIANTS and v not in HIP4_REGISTRATION_VARIANTS}
    if unclassified:
        # never guess: a grant this scorer has not classified could be a settle power under a new name
        raise Hip4ReadError(f"venue {venue!r} has sub-deployer grants this scorer does not classify: {unclassified}; "
                            f"a human must decide whether each is root control (see the module docstring) before a score is emitted")
    root_set = {dep} | {a for v in HIP4_ROOT_CONTROL_VARIANTS for a in sub.get(v, [])}
    registration_only = sorted({a for v in HIP4_REGISTRATION_VARIANTS for a in sub.get(v, [])} - root_set)
    # sorted() so a tie between equally weak keys resolves to the same address every run
    weakest = mt.weakest(sorted(root_set))
    (rk, rn) = mt.kn(weakest)[0]

    admin = mt.admin_key_score(rk, rn)
    ms = mt.key_score(rk, rn)
    timelock = 0
    oracle = mt.key_score(rk, rn)  # the settle key supplies settleFraction itself: same weakest key as the root set

    # 4.5 cross exposure: other tracked HyperCore targets sharing any root key
    mine_keys = _root_keys(_venue_authority_addrs(d))
    dexes = [x for x in mt.info({"type": "perpDexs"}) if x]
    sharing_dexes = sorted(x["name"] for x in dexes if _root_keys(_hip3_dex_authority_addrs(x)) & mine_keys)
    sharing_venues = sorted(x["venue"] for x in deployers if x.get("venue") != venue and _root_keys(_venue_authority_addrs(x)) & mine_keys)
    cross = max(0, 100 - 20 * (len(sharing_dexes) + len(sharing_venues)))

    # METHODOLOGY.md 3.7: an authority address that carries HyperEVM bytecode needs its logic read
    all_addrs = sorted(_venue_authority_addrs(d))
    code_bytes = {}
    for a in all_addrs:
        code = mt.evm("eth_getCode", [a, "latest"])
        if not isinstance(code, str) or not code.startswith("0x"):
            raise Hip4ReadError(f"eth_getCode({a}) returned {code!r}")
        code_bytes[a] = (len(code) - 2) // 2
    with_code = sorted(a for a, n in code_bytes.items() if n > 0)

    authority = _venue_authority_addrs(d)
    tree, tree_truncated = _multisig_tree(authority)
    nested = {a: v for a, v in tree.items() if a not in authority}

    sensitivity = None
    if registration_only:
        alt_weakest = mt.weakest(sorted(root_set | set(registration_only)))
        (ak, an) = mt.kn(alt_weakest)[0]
        sensitivity = {
            "weakestKey": [alt_weakest, mt.fmt((ak, an))],
            "adminKeyScore": mt.admin_key_score(ak, an),
            "multisigScore": mt.key_score(ak, an),
            "compositeScore": mt.composite(mt.admin_key_score(ak, an), mt.key_score(ak, an), timelock),
        }

    weakest_label = "the deployer itself" if weakest == dep else "a sub-deployer"
    deployer_kn = mt.kn(dep)[0]
    notes = [
        f"weakest settlement key: {weakest} ({mt.fmt((rk, rn))}), {weakest_label}; deployer is {mt.fmt(deployer_kn)}. "
        f"Root set = deployer + {'/'.join(HIP4_ROOT_CONTROL_VARIANTS)} sub-deployers (METHODOLOGY.md 4.1 HIP-4 row): they decide who receives an outcome's locked collateral",
        "the deployer stays in the set even when it is stronger than every sub-deployer: `setSubDeployers` is deployer-only, so it can always grant itself the settle variants (same reasoning as METHODOLOGY.md 4.2 rule 3)",
        "sub-deployers holding only registration variants are left out of the set BY ANALOGY with HIP-3 (`registerAsset`, `setDeployerFees`), not because they are known to be harmless: "
        "per the official page they create markets, set `deployerFeeScale` in [0, 10] on new markets (user fee up to 20x the base rate) and can add outcomes to a live question; "
        "none is documented to decide who receives already-locked collateral. Holders: "
        + (", ".join(registration_only) if registration_only else "none on this venue"),
        "timelockScore 0: the official HIP-4 deployer-actions page (read 2026-09-19) documents no delay on settleOutcome, settleQuestion2 or setSubDeployers. "
        "The only enforcement it documents is validator slashing of markets that contradict their template's semantic restriction ('malformed'); it does not say a wrong or early settlement is slashable, "
        "so nothing is credited as a deterrent",
        "oracleAuthorityScore = the same weakest key: the settle key supplies `settleFraction` itself, unlike a `setOracle` push (continuous, clamped by the protocol). Documented bounds only: a decimal in [0, 1], "
        "exactly 0 or 1 with one winner for outcomes of a question, exact metadata match, the deployer's own book only. NOT documented: any delay, any check against the market's underlying, any bound on when a settle may happen. "
        "Observed on chain 2026-09-19 (data/scored_targets_2026-09-19-hip4-outcome-deployers.md section 8; re-run the `history` subcommand): early settles and 0.5 settles of Yes/No markets were accepted. No on-chain check is credited",
    ]
    if registration_only:
        notes.append(f"SENSITIVITY: this venue has registration-only keys. If they were counted as root control the weakest key would be {sensitivity['weakestKey'][0]} ({sensitivity['weakestKey'][1]}) "
                     f"and the composite {sensitivity['compositeScore']} instead of {mt.composite(admin, ms, timelock)}; the score above uses the analogy, see reads.ifRegistrationOnlyKeysWereCounted")
    if nested:
        notes.append(f"NESTED MULTISIGS: {len(nested)} signer(s) of this venue's authority addresses are themselves HyperCore multisigs ({', '.join(sorted(nested))}). METHODOLOGY.md 4.2 rule 2 does not expand them, "
                     f"so the scores use each authority address's own (k, n); the effective threshold of the nested structure is not evaluated here" + (" (depth cap reached, list incomplete)" if tree_truncated else ""))
    if with_code:
        notes.append(f"WARNING: {with_code} carry HyperEVM bytecode -- METHODOLOGY.md 3.7 applies (CoreWriter attributes an action to the calling contract's own address); "
                     f"a `null` userToMultiSigSigners does not mean 'single key' for them. Score below is the generic reading; re-check by hand")

    reads = {
        "venue": venue,
        "deployer": [dep, mt.fmt(deployer_kn)],
        "subDeployers": {v: [[a, mt.fmt(mt.kn(a)[0])] for a in lst] for v, lst in sub.items()},
        "rootControlVariants": list(HIP4_ROOT_CONTROL_VARIANTS),
        "rootControlSet": sorted(root_set),
        "registrationOnlySubDeployers": registration_only,
        "hyperEvmCodeBytes": code_bytes,
        "venuesSharingARootKey": sharing_venues,
        "dexesSharingARootKey": sharing_dexes,
        "nestedMultisigSigners": {a: {"threshold": k, "authorizedUsers": users, "includesAnAuthorityAddress": bool(set(users) & authority)} for a, (k, users) in sorted(nested.items())},
    }
    if tree_truncated:
        reads["nestedMultisigSignersTruncated"] = True
    if sensitivity:
        reads["ifRegistrationOnlyKeysWereCounted"] = sensitivity

    # Informational block: economic weight, limits and slashable stake. Feeds no score, so a failed
    # read degrades to a flagged, empty block instead of discarding a valid authority score.
    try:
        econ = outcome_market_economics(venue, meta, fetch_outcome_ctxs())
        limits = mt.info({"type": "outcomeDeployerLimits", "venue": venue})
        stake = float(mt.info({"type": "delegatorSummary", "user": dep})["delegated"])
        reads["economicWeight"] = econ
        reads["outcomeDeployerLimits"] = limits
        reads["deployerDelegatedHype"] = stake
        notes.append(
            f"economic weight at read time: ${econ['lockedCollateralUsd']:,.0f} collateral locked behind {econ['outcomesLive']} live outcomes "
            f"(fully verified: {econ['lockedCollateralFullyVerified']}), ${econ['face24hVolumeUsd']:,.0f} face volume in the last 24h, deployer delegates {stake:,.0f} HYPE (`delegatorSummary`; slashing is documented only for malformed markets, so context, not credited)"
        )
    except Exception as e:  # noqa: BLE001 -- deliberate: informational only, disclosed below
        reads["economicWeight"] = {"error": f"{type(e).__name__}: {e}"}
        notes.append(f"economic weight NOT read this run ({type(e).__name__}: {e}); the authority scores above do not depend on it")
    notes.append(
        f"cross-exposure checked against {len(dexes)} HIP-3 dexes and {len(deployers) - 1} sibling outcome venues (root keys = authority addresses + multisig signers): "
        f"overlap {sharing_dexes + sharing_venues or 'none'}. Nested multisig signers, the HLP leader, Unit treasuries and HyperEVM role holders are not re-checked at runtime; see data/scored_targets_2026-09-19-hip4-outcome-deployers.md for the one-off check"
    )

    return {
        "target": dep,
        "label": f"HIP-4 outcome deployer {venue}",
        "reads": reads,
        "adminKeyScore": admin,
        "multisigScore": ms,
        "timelockScore": timelock,
        "oracleAuthorityScore": oracle,
        "crossExposureScore": cross,
        "compositeScore": mt.composite(admin, ms, timelock),
        "weakestRootKey": [weakest, mt.fmt((rk, rn))],
        "weakestOracleKey": [weakest, mt.fmt((rk, rn))],
        "notes": notes,
    }


_ADDRESS = re.compile(r"0x[0-9a-fA-F]{40}")


def _addresses_by_target(entries):
    """address (lowercase) -> set of tracked-target labels whose reads or notes mention it."""
    out = {}
    for entry in entries:
        for a in {x.lower() for x in _ADDRESS.findall(json.dumps(entry, default=str))}:
            out.setdefault(a, set()).add(entry["label"])
    return out


def _keys_overlapping_universe(keys, universe):
    """{address: sorted labels} for every key that is also in `universe`."""
    return {a: sorted(universe[a]) for a in sorted(set(keys) & set(universe))}


def _signer_closure(addr, expand_one, max_depth=4):
    """Every address reachable from `addr` by repeatedly applying `expand_one`
    (address -> its direct signers/owners), cycles cut, at most `max_depth`
    levels. `addr` itself is not in the result. Pure given `expand_one`."""
    addr = addr.lower()
    seen, frontier = {addr}, {addr}
    for _ in range(max_depth):
        nxt = set()
        for a in frontier:
            nxt |= {c.lower() for c in expand_one(a)} - seen
        seen |= nxt
        frontier = nxt
        if not frontier:
            break
    return seen - {addr}


def cross_check_tracked_targets(workers=6, max_depth=4):
    """One-off, CLI-only check that goes further than the runtime cross-exposure
    in `score_hip4_outcome_deployer`: harvest EVERY address that appears in the
    currently tracked Hyperliquid targets' reads and notes (a live `score_all()`
    run), expand each one RECURSIVELY (HyperCore multisig signers via
    `userToMultiSigSigners`, Gnosis Safe owners via `getOwners()` on HyperEVM, up
    to `max_depth` levels, cycles cut: `out`'s deployer sits in a nested-multisig
    cycle, so a one-level expansion under-reports), and intersect that set with
    each outcome venue's authority addresses and their signers expanded the same
    way. Over-inclusive on purpose (a regex over the JSON): any hit is meant to
    be read by a human, a miss is meaningful. Returns {venue: {address: [where]}}
    plus counts. Callers must check `trackedTargets` against the expected number
    of tracked targets: a scorer that fails in `score_all()` is skipped, which
    shrinks the universe silently."""
    import concurrent.futures as cf
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    import scorers  # noqa: E402  (imported lazily: pulls in every tracked target's scorer)
    import scout_2026_09_17_run2 as scout  # noqa: E402

    # a venue must not be reported as overlapping itself if one is wired into score_all() later
    tracked = [e for e in scorers.score_all() if not e["label"].startswith("HIP-4 outcome deployer")]
    harvested = _addresses_by_target(tracked)

    def expand_one(a):
        found = set()
        m = scout.multisig_kn(a)
        if m:
            found |= {u.lower() for u in m["authorizedUsers"]}
        sf = scout.safe(scout.EVM, a)
        if sf:
            found |= {o.lower() for o in sf["owners"]}
        return found

    with cf.ThreadPoolExecutor(max_workers=workers) as ex:
        expanded = dict(ex.map(lambda a: (a, _signer_closure(a, expand_one, max_depth)), sorted(harvested)))
    universe = {}  # address -> labels (direct or via a tracked address it signs for)
    for a, labels in harvested.items():
        universe.setdefault(a, set()).update(labels)
        for child in expanded[a]:
            universe.setdefault(child, set()).update(f"{l} (signer/owner of {a})" for l in labels)

    meta = mt.info({"type": "outcomeMeta"})
    result, venue_key_counts = {}, {}
    for d in meta["deployers"]:
        keys = set()
        for a in _venue_authority_addrs(d):
            keys |= {a} | _signer_closure(a, expand_one, max_depth)
        venue_key_counts[d["venue"]] = len(keys)
        result[d["venue"]] = _keys_overlapping_universe(keys, universe)
    return {"trackedTargets": len(tracked), "harvestedAddresses": len(harvested), "expandedUniverse": len(universe),
            "venueKeysAllLevels": venue_key_counts, "maxDepth": max_depth, "overlapByVenue": result}


def _size_all(with_history=False):
    meta = mt.info({"type": "outcomeMeta"})
    ctxs = fetch_outcome_ctxs()
    out = {"readAtUnix": int(time.time()), "outcomesTotal": len(meta["outcomes"]), "questionsTotal": len(meta.get("questions") or []), "venues": {}}
    for venue in [x["venue"] for x in meta["deployers"]] + [None]:
        row = outcome_market_economics(venue, meta, ctxs)
        if with_history and venue is not None:
            row["dailyFaceVolumeLiveOutcomes"] = venue_daily_face_volume(venue, meta)
        out["venues"]["PROTOCOL_RECURRING" if venue is None else venue] = row
    return out


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else None
    if cmd == "size":
        print(json.dumps(_size_all("--history" in sys.argv), indent=1, default=str))
    elif cmd == "venue" and len(sys.argv) > 2:
        print(json.dumps(score_hip4_outcome_deployer(sys.argv[2]), indent=1, default=str))
    elif cmd == "history":
        print(json.dumps(fetch_settlement_history(sys.argv[2] if len(sys.argv) > 2 else None), indent=1, default=str))
    elif cmd == "cross-check":
        print(json.dumps(cross_check_tracked_targets(), indent=1, default=str))
    else:
        raise SystemExit(f"usage: {sys.argv[0]} size [--history] | venue <name> | history [<venue>] | cross-check")
