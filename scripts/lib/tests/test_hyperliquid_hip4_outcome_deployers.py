"""
Unit tests for `chains/hyperliquid/scripts/scoring_build_2026_09_19_hip4.py`:
the HIP-4 outcome-deployer scorer `score_hip4_outcome_deployer(venue)` and the
economic-weight sizing `outcome_market_economics()` that decided which venues
clear this ecosystem's real-usage bar (see `chains/hyperliquid/data/
scored_targets_2026-09-19-hip4-outcome-deployers.md`).

No network access: `methodology_test.info` and `.evm` (the only two doors the
scorer reads through) are patched with a small fake HyperCore API. Address and
supply fixtures are FROZEN COPIES of live mainnet reads taken 2026-09-19:

  * venue `out`: deployer 3-of-4, two bare-key sub-deployers holding all five
    grants; venue `txyz`: deployer 2-of-3 with the SAME three signers as HIP-3
    dex `xyz`'s deployer (the cross-exposure finding of that pass);
  * question 198 (English Premier League winner, 7 outcomes): its real
    per-outcome Yes/No supplies, which satisfy the full-collateralization
    identity the sizing relies on.

What is locked in here, by group:
  1. sizing: the collateral identity (standalone and question), that anything
     unverifiable (missing, negative, identity-breaking) is EXCLUDED and flagged
     instead of counted as zero, that one side's volume is used (both sides of a
     merged book report the same trade);
  2. scoring: nominal live shape, multisig deployer (1-of-1, 1-of-N, k-of-n) +
     bare-key sub-deployer (the weakness that motivated the whole pass), a venue
     with no sub-deployer, the deployer staying in the set, registration-only
     sub-deployers being excluded WITH a visible sensitivity block, a grant the
     scorer does not classify raising, nested multisigs disclosed, wording that
     must not overclaim (slashing, oracle), deterministic tie-breaking;
  3. failures: an authority read that fails must raise (never emit a score
     computed from a guess); a failed informational read must degrade to a
     flagged empty block without touching the authority scores; the history
     read's window and UTC bucketing;
  4. wiring: no HIP-4 venue is in `score_all()`'s registry (the recorded
     decision), and a promoted venue would integrate with `score_all()`'s
     isolation and L1-cap post-processing, including a case where the cap binds.
"""
import calendar
import contextlib
import importlib.util
import io
import os
import sys
import time
import unittest
from unittest import mock

REPO_ROOT = os.path.join(os.path.dirname(__file__), "..", "..", "..")
HL_METHODOLOGY = os.path.abspath(os.path.join(REPO_ROOT, "chains/hyperliquid/scripts/methodology_test.py"))


def _load_module(unique_name, relative_path):
    file_path = os.path.abspath(os.path.join(REPO_ROOT, relative_path))
    ecosystem_dir = os.path.dirname(file_path)
    if ecosystem_dir not in sys.path:
        sys.path.insert(0, ecosystem_dir)
    spec = importlib.util.spec_from_file_location(unique_name, file_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[unique_name] = mod
    spec.loader.exec_module(mod)
    return mod


@contextlib.contextmanager
def _hyperliquid_methodology_test_as_bare_name():
    """The scorer modules do `import methodology_test` (a bare name that
    Tempo's ecosystem also uses for a DIFFERENT file). In one `unittest
    discover` process the bare name may already point at either. Make sure it
    is the Hyperliquid one while the modules under test are loaded, and put
    back whatever was there before."""
    prev = sys.modules.get("methodology_test")
    if prev is not None and os.path.abspath(getattr(prev, "__file__", "") or "") == HL_METHODOLOGY:
        yield
        return
    spec = importlib.util.spec_from_file_location("methodology_test", HL_METHODOLOGY)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["methodology_test"] = mod
    try:
        spec.loader.exec_module(mod)
        yield
    finally:
        if prev is None:
            sys.modules.pop("methodology_test", None)
        else:
            sys.modules["methodology_test"] = prev


with _hyperliquid_methodology_test_as_bare_name():
    sut = _load_module("aro_test_hyperliquid_hip4", "chains/hyperliquid/scripts/scoring_build_2026_09_19_hip4.py")
    hl_scorers = _load_module("aro_test_hyperliquid_scorers_for_hip4", "chains/hyperliquid/scorers.py")
validate_all = _load_module("aro_test_hip4_validate_all_scorers", "scripts/validate_all_scorers.py")

# ---- frozen live addresses (2026-09-19)
OUT_DEP = "0x0c46eb73fae2816f219fcf11f50d6d3c59b5819e"
OUT_SIGNERS = ["0x000af4332f3823b73f2ee3ee71d36e97d819fb07", "0x3d014abc10d9316bd20dc7a03b1c2935c3d7a1bd",
               "0x588deb78d26289ea796165d452d2e85f81dfc0e1", "0xcb3efe8962989c3f8247348ecf8139b026b43329"]
OUT_SUB_A = "0x6947a610ef50f8b5d4b59abcd94dd75aaaa645b9"
OUT_SUB_B = "0xf1923927d7d2847191fb7ef8b1a16028aa5ae754"
TXYZ_DEP = "0x7aca09667816a4817b8bc697fb239ad42ff9f553"
TXYZ_SUBS = ["0x77ef1bbc0467f0ddde42e5a0e9ccd80369c55cc8", "0x786864b48a102a047b9796c2541256e5f08bbe70"]
XYZ_SIGNERS = ["0x04777feeff2d63be8d2f1c00f19ad40d6934c977", "0xdad9fea2ed085e857dc372e5715fa6df10e941db",
               "0xf35dde413c076116ef0c0c608f59ebb998fb701f"]  # SAME three signers back both xyz's and txyz's deployer
XYZ_DEP = "0x88806a71d74ad0a510b350545c9ae490912f0888"
SKEW_DEP = "0x08e9c89f46dccee91bdb85c6532eb93a4c335efe"
SKEW_SUB = "0x1c867861e0cffb0eba07d9d94f716189c130dac6"
SKEW_SIGNERS = ["0x0feed220190e3147b8427e88833b8d0395b5f093", "0x12c13eeaf480be0d18dc4a9a63be001f470125ce",
                "0x28e88fc65a910c4beb7aa85fa74284c288a78782", "0x47663bf757d8657c741d9eb03c71a882b64ad8a3",
                "0x4d4509d7f3d6d6b8506dc4b9444942d00ee36941"]

ALL_VARIANTS = ["registerAndAssociateNamedOutcomeFromTemplate", "registerQuestionFromTemplate",
                "registerStandaloneOutcomeFromTemplate", "settleOutcome", "settleQuestion"]

# question 198, real per-outcome supplies (fallback 1472 first, then 6 named outcomes)
Q198_IDS = [1472, 1473, 1474, 1475, 1476, 1477, 1478]
Q198_YES = [30941, 39152, 35534, 34389, 37784, 31166, 31369]
Q198_NO = [0, 8211, 4593, 3448, 6843, 225, 428]
Q198_COLLATERAL = 54689


def _venue(venue, dep, subs_by_variant):
    return {"deployer": dep, "venue": venue, "subDeployers": [[v, list(a)] for v, a in sorted(subs_by_variant.items())]}


def _all_variants(addrs):
    return {v: addrs for v in ALL_VARIANTS}


def _outcome(oid, venue):
    return {"outcome": oid, "name": "template:binaryPrice", "description": f"d{oid}", "sideSpecs": [{"name": "template:Yes"}, {"name": "template:No"}],
            "quoteToken": "USDC", "venue": venue, "deployerFeeScale": "1.0"}


def _ctx(oid, yes, no, yes_vol=0, no_vol=None):
    no_vol = yes_vol if no_vol is None else no_vol
    base = {"prevDayPx": "0.0", "markPx": "0.5", "midPx": "0.5", "totalSupply": "184467440737095.53125"}
    return [dict(base, coin=f"#{10 * oid}", circulatingSupply=str(yes), dayBaseVlm=str(yes_vol), dayNtlVlm="1.0"),
            dict(base, coin=f"#{10 * oid + 1}", circulatingSupply=str(no), dayBaseVlm=str(no_vol), dayNtlVlm="2.0")]


def _ctx_map(*pairs):
    return {c["coin"]: c for p in pairs for c in p}


def _q198_meta_and_ctx(venue="out", volumes=None):
    volumes = volumes or [0] * 7
    outcomes = [_outcome(i, venue) for i in Q198_IDS]
    question = {"question": 198, "name": "template:sportsTournamentWinner", "description": "EPL", "fallbackOutcome": 1472,
                "namedOutcomes": Q198_IDS[1:], "settledNamedOutcomes": []}
    ctxs = [_ctx(i, y, n, v) for i, y, n, v in zip(Q198_IDS, Q198_YES, Q198_NO, volumes)]
    return outcomes, question, ctxs


class FakeApi:
    """A tiny HyperCore info API + HyperEVM `eth_getCode`."""

    def __init__(self, deployers, outcomes=(), questions=(), ctxs=(), dexes=(), multisigs=None, code=None):
        self.meta = {"outcomes": list(outcomes), "questions": list(questions), "deployers": list(deployers), "feeScale": "1.0"}
        self.ctxs = [c for pair in ctxs for c in pair]
        self.dexes = [None] + list(dexes)  # the real payload starts with a null entry
        self.multisigs = {k.lower(): v for k, v in (multisigs or {}).items()}
        self.code = {k.lower(): v for k, v in (code or {}).items()}
        self.fail = {}
        self.stake = {"delegated": "500000.0"}
        self.limits = {"nDailyOutcomesRemaining": 400, "nActiveOutcomesRemaining": 1}
        self.calls = []
        self.bodies = []

    def info(self, body):
        t = body["type"]
        self.calls.append(t)
        self.bodies.append(body)
        if t in self.fail:
            raise self.fail[t]
        if t == "outcomeMeta":
            return self.meta
        if t == "spotMetaAndAssetCtxs":
            return [{"universe": [], "tokens": []}, self.ctxs]
        if t == "perpDexs":
            return self.dexes
        if t == "userToMultiSigSigners":
            return self.multisigs.get(body["user"].lower())
        if t == "delegatorSummary":
            return self.stake
        if t == "outcomeDeployerLimits":
            return self.limits
        raise AssertionError(f"unexpected info request: {body}")

    def evm(self, method, params):
        assert method == "eth_getCode", method
        return self.code.get(params[0].lower(), "0x")


def multisig(threshold, users):
    return {"threshold": threshold, "authorizedUsers": list(users)}


@contextlib.contextmanager
def patched(api):
    with mock.patch.object(sut.mt, "info", api.info), mock.patch.object(sut.mt, "evm", api.evm), \
            mock.patch.dict(sut.mt._kn_cache, {}, clear=True):
        yield


def out_api(**overrides):
    """Live-shaped venue `out`: 3-of-4 deployer, two bare-key sub-deployers holding all five grants,
    question 198 plus one standalone outcome, and HIP-3 dex `xyz` present but unrelated."""
    q_outcomes, question, q_ctxs = _q198_meta_and_ctx("out", volumes=[100, 0, 0, 0, 0, 0, 0])
    standalone = _outcome(1209, "out")
    kwargs = dict(
        deployers=[_venue("out", OUT_DEP, _all_variants([OUT_SUB_A, OUT_SUB_B]))],
        outcomes=[standalone] + q_outcomes, questions=[question],
        ctxs=[_ctx(1209, 162765, 162765, 56934)] + q_ctxs,
        dexes=[{"name": "xyz", "deployer": XYZ_DEP, "oracleUpdater": None, "subDeployers": []}],
        multisigs={OUT_DEP: multisig(3, OUT_SIGNERS), XYZ_DEP: multisig(2, XYZ_SIGNERS)},
    )
    kwargs.update(overrides)
    return FakeApi(**kwargs)


def score(api, venue="out"):
    with patched(api):
        return sut.score_hip4_outcome_deployer(venue)


def scores_of(entry):
    return tuple(entry[k] for k in ("adminKeyScore", "multisigScore", "timelockScore", "oracleAuthorityScore", "crossExposureScore", "compositeScore"))


# =============================================================== 1. sizing


class TestOutcomeMarketEconomics(unittest.TestCase):
    def _econ(self, venue, outcomes, ctxs, questions=()):
        meta = {"outcomes": list(outcomes), "questions": list(questions)}
        return sut.outcome_market_economics(venue, meta, _ctx_map(*ctxs))

    def test_standalone_collateral_is_the_yes_supply(self):
        e = self._econ("out", [_outcome(1, "out")], [_ctx(1, 333, 333, 369)])
        self.assertEqual(e["lockedCollateralUsd"], 333.0)
        self.assertTrue(e["lockedCollateralFullyVerified"])
        self.assertEqual(e["outcomesLive"], 1)
        self.assertEqual(e["outcomesWithOutstandingSupply"], 1)

    def test_question_198_real_supplies_give_the_exact_collateral(self):
        outcomes, question, ctxs = _q198_meta_and_ctx()
        e = self._econ("out", outcomes, ctxs, [question])
        self.assertEqual(e["lockedCollateralUsd"], float(Q198_COLLATERAL))
        self.assertTrue(e["lockedCollateralFullyVerified"])
        self.assertEqual(e["questionsLive"], 1)

    def test_identity_matches_an_independent_payout_computation(self):
        # Independent of the implementation: for EVERY possible winner w the payout is
        # Yes_w + sum(No_j, j != w); full collateralization means all seven equal the locked amount.
        payouts = {w: Q198_YES[w] + sum(n for j, n in enumerate(Q198_NO) if j != w) for w in range(7)}
        self.assertEqual(set(payouts.values()), {Q198_COLLATERAL})
        outcomes, question, ctxs = _q198_meta_and_ctx()
        self.assertEqual(self._econ("out", outcomes, ctxs, [question])["lockedCollateralUsd"], float(payouts[0]))

    def test_naive_yes_supply_sum_would_overstate_a_question(self):
        # Guards the reason the identity exists: summing Yes supplies (or max side) is NOT the collateral.
        outcomes, question, ctxs = _q198_meta_and_ctx()
        e = self._econ("out", outcomes, ctxs, [question])
        self.assertGreater(sum(Q198_YES), e["lockedCollateralUsd"])
        self.assertEqual(e["sharesOutstandingBothSides"], float(sum(Q198_YES) + sum(Q198_NO)))

    def test_other_venues_and_protocol_outcomes_are_not_counted(self):
        outcomes = [_outcome(1, "out"), _outcome(2, "txyz"), _outcome(3, None)]
        ctxs = [_ctx(1, 100, 100), _ctx(2, 7000, 7000), _ctx(3, 50, 50)]
        self.assertEqual(self._econ("out", outcomes, ctxs)["lockedCollateralUsd"], 100.0)
        self.assertEqual(self._econ("txyz", outcomes, ctxs)["lockedCollateralUsd"], 7000.0)
        self.assertEqual(self._econ(None, outcomes, ctxs)["lockedCollateralUsd"], 50.0)

    def test_standalone_with_unequal_sides_is_unverified_and_excluded(self):
        e = self._econ("out", [_outcome(1, "out"), _outcome(2, "out")], [_ctx(1, 100, 100), _ctx(2, 900, 5)])
        self.assertEqual(e["lockedCollateralUsd"], 100.0)  # the broken one is NOT counted
        self.assertFalse(e["lockedCollateralFullyVerified"])
        self.assertEqual([g["id"] for g in e["unverifiedGroups"]], [2])
        self.assertIn("!=", e["unverifiedGroups"][0]["why"])

    def test_question_breaking_the_identity_is_unverified_and_excluded(self):
        outcomes, question, ctxs = _q198_meta_and_ctx()
        ctxs[3] = _ctx(1475, Q198_YES[3] + 999, Q198_NO[3])  # one member no longer matches the shared (Yes - No)
        e = self._econ("out", outcomes, ctxs, [question])
        self.assertEqual(e["lockedCollateralUsd"], 0.0)
        self.assertFalse(e["lockedCollateralFullyVerified"])
        self.assertEqual(e["unverifiedGroups"][0]["kind"], "question")
        self.assertIn("differs across members", e["unverifiedGroups"][0]["why"])

    def test_missing_market_data_is_flagged_not_counted_as_zero(self):
        outcomes = [_outcome(1, "out"), _outcome(2, "out")]
        e = self._econ("out", outcomes, [_ctx(1, 100, 100, 10)])  # outcome 2 has no context at all
        self.assertEqual(e["lockedCollateralUsd"], 100.0)
        self.assertEqual(e["outcomesWithoutMarketData"], [2])
        self.assertFalse(e["lockedCollateralFullyVerified"])
        self.assertEqual(e["outcomesLive"], 2)  # still counted as live: absence of data is not absence of the market

    def test_missing_volume_field_alone_makes_the_result_not_fully_verified(self):
        # supplies are readable and consistent, only `dayBaseVlm` is absent: nothing is "unverified" by the identity,
        # yet the market data is incomplete, so the flag must still drop (a missing value is never read as zero)
        pair = _ctx(1, 100, 100, 10)
        pair[0].pop("dayBaseVlm")
        e = self._econ("out", [_outcome(1, "out")], [pair])
        self.assertEqual(e["lockedCollateralUsd"], 100.0)
        self.assertEqual(e["unverifiedGroups"], [])
        self.assertEqual(e["outcomesWithoutMarketData"], [1])
        self.assertFalse(e["lockedCollateralFullyVerified"])
        self.assertEqual(e["shares24h"], 0.0)  # not counted as zero volume either: the outcome is listed as without data

    def test_negative_supply_is_unverified_and_excluded(self):
        # a negative circulating supply is a malformed payload, never collateral (equal negative sides would pass the standalone check)
        e = self._econ("out", [_outcome(1, "out")], [_ctx(1, -5, -5)])
        self.assertEqual(e["lockedCollateralUsd"], 0.0)
        self.assertFalse(e["lockedCollateralFullyVerified"])
        self.assertIn("negative supply", e["unverifiedGroups"][0]["why"])
        self.assertEqual(e["sharesOutstandingBothSides"], 0.0)  # the generous upper bound ignores it too
        outcomes, question, ctxs = _q198_meta_and_ctx()
        ctxs[2] = _ctx(1474, -1, Q198_NO[2])
        e = self._econ("out", outcomes, ctxs, [question])
        self.assertEqual(e["lockedCollateralUsd"], 0.0)
        self.assertIn("negative supply for outcome(s) [1474]", e["unverifiedGroups"][0]["why"])

    def test_unparseable_supply_is_treated_as_missing(self):
        pair = _ctx(1, 100, 100)
        pair[0]["circulatingSupply"] = "not-a-number"
        e = self._econ("out", [_outcome(1, "out")], [pair])
        self.assertEqual(e["lockedCollateralUsd"], 0.0)
        self.assertFalse(e["lockedCollateralFullyVerified"])

    def test_question_members_spanning_two_venues_are_unverified(self):
        outcomes, question, ctxs = _q198_meta_and_ctx()
        outcomes[2]["venue"] = "txyz"
        e = self._econ("out", outcomes, ctxs, [question])
        self.assertEqual(e["lockedCollateralUsd"], 0.0)
        self.assertIn("span more than one venue", e["unverifiedGroups"][0]["why"])

    def test_volume_counts_one_side_only(self):
        # Yes and No coins report the same trades: summing both would double the venue's volume.
        e = self._econ("out", [_outcome(1, "out"), _outcome(2, "out")], [_ctx(1, 10, 10, 369), _ctx(2, 5, 5, 0)])
        self.assertEqual(e["shares24h"], 369.0)
        self.assertEqual(e["face24hVolumeUsd"], 369.0)
        self.assertEqual(e["outcomesTraded24h"], 1)
        self.assertEqual(e["volumeSidesDisagree"], 0)

    def test_sides_reporting_different_volume_are_counted(self):
        e = self._econ("out", [_outcome(1, "out")], [_ctx(1, 10, 10, yes_vol=369, no_vol=400)])
        self.assertEqual(e["volumeSidesDisagree"], 1)
        self.assertEqual(e["shares24h"], 369.0)  # still the Yes side, the disagreement is surfaced not averaged

    def test_venue_with_no_live_outcomes_is_all_zero(self):
        e = self._econ("out", [_outcome(9, "txyz")], [_ctx(9, 5, 5)])
        self.assertEqual((e["outcomesLive"], e["lockedCollateralUsd"], e["shares24h"]), (0, 0.0, 0.0))

    def test_fractional_supplies_do_not_lose_precision(self):
        e = self._econ("out", [_outcome(1, "out"), _outcome(2, "out"), _outcome(3, "out")], [_ctx(1, "0.1", "0.1"), _ctx(2, "0.2", "0.2"), _ctx(3, "0.3", "0.3")])
        self.assertEqual(e["lockedCollateralUsd"], 0.6)  # float 0.1 + 0.2 + 0.3 would give 0.6000000000000001


# =============================================================== 2. scoring


class TestScoreHip4OutcomeDeployer(unittest.TestCase):
    def test_nominal_live_shape_multisig_deployer_with_bare_key_sub_deployers(self):
        entry = score(out_api())
        # deployer 3-of-4 is stronger than the bare-key sub-deployers, which hold the settle grants and bypass it
        self.assertEqual(scores_of(entry), (10, 15, 0, 15, 100, 9))
        self.assertEqual(entry["label"], "HIP-4 outcome deployer out")
        self.assertEqual(entry["target"], OUT_DEP)
        self.assertEqual(entry["weakestRootKey"], [OUT_SUB_A, "single key"])  # tie of two bare keys -> lowest address, every run
        self.assertEqual(entry["reads"]["deployer"], [OUT_DEP, "3-of-4"])
        self.assertEqual(entry["reads"]["rootControlSet"], sorted([OUT_DEP, OUT_SUB_A, OUT_SUB_B]))
        self.assertEqual(entry["reads"]["venuesSharingARootKey"], [])
        self.assertEqual(entry["reads"]["dexesSharingARootKey"], [])
        self.assertEqual(entry["reads"]["hyperEvmCodeBytes"], {OUT_DEP: 0, OUT_SUB_A: 0, OUT_SUB_B: 0})
        self.assertIn("a sub-deployer", entry["notes"][0])
        self.assertIn("deployer is 3-of-4", entry["notes"][0])

    def test_nominal_live_shape_has_no_registration_only_key_no_nested_multisig_and_no_sensitivity_block(self):
        entry = score(out_api())
        self.assertEqual(entry["reads"]["registrationOnlySubDeployers"], [])
        self.assertNotIn("ifRegistrationOnlyKeysWereCounted", entry["reads"])
        self.assertEqual(entry["reads"]["nestedMultisigSigners"], {})
        self.assertFalse([n for n in entry["notes"] if n.startswith(("SENSITIVITY", "NESTED"))])

    def test_nominal_economics_use_the_collateral_identity(self):
        econ = score(out_api())["reads"]["economicWeight"]
        self.assertEqual(econ["lockedCollateralUsd"], float(162765 + Q198_COLLATERAL))
        self.assertTrue(econ["lockedCollateralFullyVerified"])
        self.assertEqual(econ["face24hVolumeUsd"], float(56934 + 100))
        self.assertEqual(econ["outcomesLive"], 8)

    def test_result_passes_the_cross_ecosystem_schema_sensor(self):
        for api in (out_api(), out_api(deployers=[_venue("out", OUT_DEP, {})])):
            self.assertEqual(validate_all.validate_entry(score(api)), [])

    def test_stronger_sub_deployer_does_not_lift_a_weaker_deployer(self):
        subs = ["0x1111111111111111111111111111111111111111"]
        api = out_api(deployers=[_venue("out", OUT_DEP, _all_variants(subs))],
                      multisigs={OUT_DEP: multisig(2, OUT_SIGNERS[:3]), subs[0]: multisig(4, [f"0x{i:040x}" for i in range(1, 7)])})
        entry = score(api)
        self.assertEqual(entry["weakestRootKey"], [OUT_DEP, "2-of-3"])  # the deployer stays in the set (setSubDeployers is deployer-only)
        self.assertEqual(scores_of(entry), (50, 39, 0, 39, 100, 32))
        self.assertIn("the deployer itself", entry["notes"][0])

    def test_venue_without_any_sub_deployer_scores_on_the_deployer_alone(self):
        for sub_list in ([], None):
            venue = {"deployer": OUT_DEP, "venue": "out", "subDeployers": sub_list}
            entry = score(out_api(deployers=[venue], multisigs={OUT_DEP: multisig(3, OUT_SIGNERS + ["0x" + "5" * 40])}))
            self.assertEqual(entry["reads"]["rootControlSet"], [OUT_DEP])
            self.assertEqual(entry["reads"]["subDeployers"], {})
            self.assertEqual(scores_of(entry), (65, 58, 0, 58, 100, 43))  # 3-of-5
            self.assertIn("none on this venue", " ".join(entry["notes"]))

    def test_venue_without_sub_deployer_and_a_bare_key_deployer(self):
        entry = score(out_api(deployers=[_venue("out", OUT_DEP, {})], multisigs={}))
        self.assertEqual(scores_of(entry), (10, 15, 0, 15, 100, 9))
        self.assertEqual(entry["weakestRootKey"], [OUT_DEP, "single key"])

    def test_sub_deployer_with_only_registration_grants_is_excluded_but_the_choice_is_shown(self):
        # a registrar is left out of the root set BY ANALOGY with HIP-3 (it is not documented to redirect locked collateral),
        # and the output says how much that choice matters instead of asking the reader to trust it
        registrar = "0x2222222222222222222222222222222222222222"
        subs = {"registerStandaloneOutcomeFromTemplate": [registrar], "registerQuestionFromTemplate": [registrar]}
        entry = score(out_api(deployers=[_venue("out", OUT_DEP, subs)]))
        self.assertEqual(scores_of(entry), (65, 59, 0, 59, 100, 44))  # 3-of-4 deployer alone
        self.assertEqual(entry["reads"]["registrationOnlySubDeployers"], [registrar])
        self.assertEqual(entry["reads"]["rootControlSet"], [OUT_DEP])
        alt = entry["reads"]["ifRegistrationOnlyKeysWereCounted"]
        self.assertEqual(alt["weakestKey"], [registrar, "single key"])
        self.assertEqual((alt["adminKeyScore"], alt["multisigScore"], alt["compositeScore"]), (10, 15, 9))
        note = next(n for n in entry["notes"] if n.startswith("SENSITIVITY"))
        self.assertIn(registrar, note)
        self.assertIn("composite 9 instead of 44", note)
        self.assertIn("BY ANALOGY", " ".join(entry["notes"]))  # the exclusion is never presented as a finding of harmlessness

    def test_a_sub_deployer_holding_a_settle_grant_and_a_registration_grant_is_not_registration_only(self):
        both = "0x4444444444444444444444444444444444444444"
        subs = {"settleOutcome": [both], "registerQuestionFromTemplate": [both]}
        entry = score(out_api(deployers=[_venue("out", OUT_DEP, subs)]))
        self.assertEqual(entry["reads"]["registrationOnlySubDeployers"], [])
        self.assertEqual(entry["reads"]["rootControlSet"], sorted([OUT_DEP, both]))
        self.assertNotIn("ifRegistrationOnlyKeysWereCounted", entry["reads"])

    def test_a_grant_the_scorer_does_not_classify_raises_instead_of_being_ignored(self):
        holder = "0x3333333333333333333333333333333333333333"
        for variant in ("settleQuestion2", "setDeployerFees", "someFutureSettleVariant"):
            subs = _all_variants([OUT_SUB_A])
            subs[variant] = [holder]
            with self.assertRaises(sut.Hip4ReadError) as cm:
                score(out_api(deployers=[_venue("out", OUT_DEP, subs)]))
            self.assertIn(variant, str(cm.exception))
            self.assertIn(holder, str(cm.exception))
        # a listed grant with no holder carries nothing to classify
        subs = _all_variants([OUT_SUB_A])
        subs["settleQuestion2"] = []
        self.assertEqual(scores_of(score(out_api(deployers=[_venue("out", OUT_DEP, subs)]))), (10, 15, 0, 15, 100, 9))

    def test_multisig_deployers_with_threshold_one_and_no_sub_deployer(self):
        one_of_one = out_api(deployers=[_venue("out", OUT_DEP, {})], multisigs={OUT_DEP: multisig(1, [OUT_SIGNERS[0]])})
        entry = score(one_of_one)
        self.assertEqual(entry["weakestRootKey"], [OUT_DEP, "single key"])  # a 1-of-1 multisig is one key (METHODOLOGY.md 4.2 rule 1)
        self.assertEqual(scores_of(entry), (10, 15, 0, 15, 100, 9))
        one_of_three = out_api(deployers=[_venue("out", OUT_DEP, {})], multisigs={OUT_DEP: multisig(1, OUT_SIGNERS[:3])})
        entry = score(one_of_three)
        self.assertEqual(entry["weakestRootKey"], [OUT_DEP, "1-of-3"])  # strictly weaker than one key
        self.assertEqual(scores_of(entry), (5, 10, 0, 10, 100, 5))

    def test_a_sub_deployer_holding_only_settle_question_is_in_the_set(self):
        settler = "0x3333333333333333333333333333333333333333"
        entry = score(out_api(deployers=[_venue("out", OUT_DEP, {"settleQuestion": [settler]})]))
        self.assertEqual(entry["weakestRootKey"], [settler, "single key"])
        self.assertEqual(scores_of(entry), (10, 15, 0, 15, 100, 9))

    def test_a_sub_deployer_holding_only_settle_outcome_is_in_the_set(self):
        settler = "0x3333333333333333333333333333333333333333"
        entry = score(out_api(deployers=[_venue("out", OUT_DEP, {"settleOutcome": [settler]})]))
        self.assertEqual(entry["weakestRootKey"], [settler, "single key"])

    def test_one_of_n_sub_deployer_is_weaker_than_a_bare_key(self):
        one_of_three = "0x" + "f" * 40  # sorts AFTER the bare key, so only a correct (k, -n) ordering picks it
        api = out_api(deployers=[_venue("out", OUT_DEP, _all_variants([one_of_three, OUT_SUB_A]))],
                      multisigs={OUT_DEP: multisig(3, OUT_SIGNERS), one_of_three: multisig(1, [f"0x{i:040x}" for i in range(10, 13)])})
        entry = score(api)
        self.assertEqual(entry["weakestRootKey"], [one_of_three, "1-of-3"])
        self.assertEqual(scores_of(entry), (5, 10, 0, 10, 100, 5))  # admin 5, key_score(1,3) = 14 - 2*2

    def test_a_tie_between_equally_weak_keys_is_resolved_from_a_sorted_input(self):
        # `min` returns the first minimal element, so the winner of a tie is decided by the order of the input:
        # a set's order is not stable across runs, hence the input must be sorted (lowest address wins)
        real, seen = sut.mt.weakest, []

        def spy(addrs):
            seen.append(list(addrs))
            return real(addrs)

        with mock.patch.object(sut.mt, "weakest", spy):
            entry = score(out_api())
        self.assertEqual(len(seen), 1)
        self.assertEqual(seen[0], sorted([OUT_DEP, OUT_SUB_A, OUT_SUB_B]))
        self.assertEqual(entry["weakestRootKey"][0], OUT_SUB_A)

    def test_mixed_case_addresses_from_the_api_are_normalized(self):
        venue = _venue("out", OUT_DEP.replace("0c46", "0C46").replace("5819e", "5819E"), _all_variants([OUT_SUB_A.upper().replace("0X", "0x")]))
        entry = score(out_api(deployers=[venue]))
        self.assertEqual(entry["target"], OUT_DEP)
        self.assertEqual(entry["weakestRootKey"][0], OUT_SUB_A)

    def test_root_control_variants_cover_the_documented_grants_exactly_once(self):
        self.assertEqual(sut.HIP4_ROOT_CONTROL_VARIANTS, ("settleOutcome", "settleQuestion"))
        self.assertEqual(set(sut.HIP4_ROOT_CONTROL_VARIANTS) | set(sut.HIP4_REGISTRATION_VARIANTS), set(ALL_VARIANTS))
        self.assertFalse(set(sut.HIP4_ROOT_CONTROL_VARIANTS) & set(sut.HIP4_REGISTRATION_VARIANTS))

    def test_the_scored_venue_is_the_requested_one_among_several(self):
        deployers = [_venue("skew", SKEW_DEP, _all_variants([SKEW_SUB])), _venue("out", OUT_DEP, _all_variants([OUT_SUB_A, OUT_SUB_B]))]
        api = out_api(deployers=deployers, multisigs={OUT_DEP: multisig(3, OUT_SIGNERS), SKEW_DEP: multisig(3, SKEW_SIGNERS)})
        self.assertEqual(score(api, "skew")["target"], SKEW_DEP)
        self.assertEqual(score(api, "skew")["reads"]["deployer"], [SKEW_DEP, "3-of-5"])
        self.assertEqual(score(api, "out")["target"], OUT_DEP)


class TestNestedMultisigsAndWording(unittest.TestCase):
    NESTED = "0x" + "5" * 40

    def _nested_api(self, **kw):
        signers = [OUT_SIGNERS[0], OUT_SIGNERS[1], OUT_SIGNERS[3], self.NESTED]
        # live 2026-09-19: one of `out`'s deployer signers is itself a 3-of-4 multisig that lists the deployer among its signers
        multisigs = {OUT_DEP: multisig(3, signers), self.NESTED: multisig(3, [OUT_DEP, "0x" + "6" * 40, "0x" + "7" * 40, "0x" + "8" * 40])}
        return out_api(multisigs=multisigs, **kw)

    def test_a_signer_that_is_itself_a_multisig_is_disclosed_and_changes_no_score(self):
        entry = score(self._nested_api())
        self.assertEqual(scores_of(entry), scores_of(score(out_api())))  # rule 4.2.2: nested multisigs are not expanded into the score
        nested = entry["reads"]["nestedMultisigSigners"]
        self.assertEqual(list(nested), [self.NESTED])
        self.assertEqual(nested[self.NESTED]["threshold"], 3)
        self.assertTrue(nested[self.NESTED]["includesAnAuthorityAddress"])  # the cycle back to the deployer
        note = next(n for n in entry["notes"] if n.startswith("NESTED MULTISIGS"))
        self.assertIn(self.NESTED, note)
        self.assertIn("not evaluated", note)
        self.assertEqual(validate_all.validate_entry(entry), [])

    def test_nesting_two_levels_deep_with_a_cycle_terminates_and_lists_every_multisig(self):
        second = "0x" + "9" * 40
        api = self._nested_api()
        api.multisigs[self.NESTED] = multisig(3, [OUT_DEP, second, "0x" + "6" * 40, "0x" + "7" * 40])
        api.multisigs[second] = multisig(2, [OUT_DEP, self.NESTED, "0x" + "a" * 40])  # points back at both
        nested = score(api)["reads"]["nestedMultisigSigners"]
        self.assertEqual(sorted(nested), sorted([self.NESTED, second]))

    def test_multisig_tree_depth_cap_is_reported_not_silent(self):
        chain = [f"0x{0xc0de00 + i:040x}" for i in range(8)]
        bare = [f"0x{0xb0b000 + i:040x}" for i in range(8)]
        api = FakeApi(deployers=[], multisigs={chain[i]: multisig(2, [chain[i + 1], bare[i]]) for i in range(7)})
        with patched(api):
            tree, truncated = sut._multisig_tree([chain[0]])
            self.assertTrue(truncated)
            self.assertEqual(sorted(tree), sorted(chain[:5]))  # 5 levels examined, the 6th left unexamined
            tree, truncated = sut._multisig_tree([chain[6]])  # chain[6] -> chain[7], chain[7] is a bare key here
            self.assertFalse(truncated)
            self.assertEqual(sorted(tree), [chain[6]])

    def test_slashing_is_not_credited_as_a_deterrent_for_settlement(self):
        text = " ".join(score(out_api())["notes"])
        self.assertNotIn("only deterrent", text)
        self.assertIn("does not say a wrong or early settlement is slashable", text)
        self.assertIn("nothing is credited as a deterrent", text)

    def test_oracle_note_states_documented_bounds_and_what_is_not_documented(self):
        note = next(n for n in score(out_api())["notes"] if n.startswith("oracleAuthorityScore"))
        self.assertIn("[0, 1]", note)
        self.assertIn("exactly 0 or 1", note)
        self.assertIn("NOT documented", note)
        self.assertIn("unlike a `setOracle` push", note)

    def test_limits_and_stake_are_requested_for_the_scored_venue_not_a_hardcoded_one(self):
        deployers = [_venue("skew", SKEW_DEP, _all_variants([SKEW_SUB])), _venue("out", OUT_DEP, _all_variants([OUT_SUB_A, OUT_SUB_B]))]
        api = out_api(deployers=deployers, multisigs={OUT_DEP: multisig(3, OUT_SIGNERS), SKEW_DEP: multisig(3, SKEW_SIGNERS)})
        score(api, "skew")
        self.assertIn({"type": "outcomeDeployerLimits", "venue": "skew"}, api.bodies)
        self.assertIn({"type": "delegatorSummary", "user": SKEW_DEP}, api.bodies)
        self.assertNotIn({"type": "outcomeDeployerLimits", "venue": "out"}, api.bodies)


class TestCrossExposure(unittest.TestCase):
    def _txyz_api(self, dexes=(), extra_deployers=(), **kw):
        deployers = [_venue("txyz", TXYZ_DEP, _all_variants(TXYZ_SUBS)), *extra_deployers]
        return FakeApi(deployers=deployers, dexes=list(dexes), multisigs={TXYZ_DEP: multisig(2, XYZ_SIGNERS), XYZ_DEP: multisig(2, XYZ_SIGNERS)}, **kw)

    def test_shared_signers_with_a_hip3_dex_are_detected(self):
        # live 2026-09-19: txyz's deployer and HIP-3 dex xyz's deployer are different addresses backed by the SAME three signers
        api = self._txyz_api(dexes=[{"name": "xyz", "deployer": XYZ_DEP, "oracleUpdater": None, "subDeployers": []}])
        entry = score(api, "txyz")
        self.assertEqual(entry["reads"]["dexesSharingARootKey"], ["xyz"])
        self.assertEqual(entry["crossExposureScore"], 80)
        self.assertEqual(entry["compositeScore"], 9)  # cross exposure is not a composite input

    def test_a_dex_matching_only_on_a_sub_deployer_or_oracle_updater_counts(self):
        dex = {"name": "dx", "deployer": "0x" + "9" * 40, "oracleUpdater": TXYZ_SUBS[0], "subDeployers": []}
        self.assertEqual(score(self._txyz_api(dexes=[dex]), "txyz")["reads"]["dexesSharingARootKey"], ["dx"])
        dex = {"name": "dy", "deployer": "0x" + "9" * 40, "oracleUpdater": None, "subDeployers": [["haltTrading", [TXYZ_SUBS[1].upper().replace("0X", "0x")]]]}
        self.assertEqual(score(self._txyz_api(dexes=[dex]), "txyz")["reads"]["dexesSharingARootKey"], ["dy"])

    def test_a_sibling_outcome_venue_sharing_a_signer_is_detected(self):
        sibling = _venue("sib", "0x" + "8" * 40, _all_variants(["0x" + "7" * 40]))
        api = self._txyz_api(extra_deployers=[sibling])
        api.multisigs["0x" + "8" * 40] = multisig(2, [XYZ_SIGNERS[0], "0x" + "6" * 40])
        entry = score(api, "txyz")
        self.assertEqual(entry["reads"]["venuesSharingARootKey"], ["sib"])
        self.assertEqual(entry["crossExposureScore"], 80)

    def test_a_sibling_outcome_venue_sharing_only_a_sub_deployer_is_detected(self):
        # no multisig, no shared signer: the ONLY link is the sibling's sub-deployer being one of this venue's sub-deployers
        sibling = _venue("sib", "0x" + "8" * 40, _all_variants([TXYZ_SUBS[0].upper().replace("0X", "0x")]))
        entry = score(self._txyz_api(extra_deployers=[sibling]), "txyz")
        self.assertEqual(entry["reads"]["venuesSharingARootKey"], ["sib"])
        self.assertEqual(entry["crossExposureScore"], 80)

    def test_a_dex_and_a_venue_together_cost_twenty_each(self):
        sibling = _venue("sib", "0x" + "8" * 40, {})
        api = self._txyz_api(dexes=[{"name": "xyz", "deployer": XYZ_DEP, "oracleUpdater": None, "subDeployers": []}], extra_deployers=[sibling])
        api.multisigs["0x" + "8" * 40] = multisig(2, [XYZ_SIGNERS[1], "0x" + "6" * 40])
        self.assertEqual(score(api, "txyz")["crossExposureScore"], 60)

    def test_cross_exposure_floors_at_zero(self):
        siblings = [_venue(f"s{i}", f"0x{i + 1:040x}", {}) for i in range(6)]
        api = self._txyz_api(extra_deployers=siblings)
        for s in siblings:
            api.multisigs[s["deployer"]] = multisig(1, [XYZ_SIGNERS[2], f"0x{0xabc0 + int(s['venue'][1:]):040x}"])
        self.assertEqual(score(api, "txyz")["crossExposureScore"], 0)

    def test_independent_dexes_and_venues_leave_it_at_100(self):
        dex = {"name": "other", "deployer": "0x" + "9" * 40, "oracleUpdater": None, "subDeployers": [["setOracle", ["0x" + "a" * 40]]]}
        self.assertEqual(score(out_api(dexes=[dex]))["crossExposureScore"], 100)


class TestHyperEvmBytecodeCheck(unittest.TestCase):
    def test_bytecode_on_an_authority_address_is_disclosed_and_scores_do_not_change(self):
        baseline = scores_of(score(out_api()))
        entry = score(out_api(code={OUT_SUB_B: "0x6080604052"}))
        self.assertEqual(scores_of(entry), baseline)  # generic reading kept; the warning tells a human to re-check by hand
        self.assertEqual(entry["reads"]["hyperEvmCodeBytes"][OUT_SUB_B], 5)
        warnings = [n for n in entry["notes"] if n.startswith("WARNING")]
        self.assertEqual(len(warnings), 1)
        self.assertIn(OUT_SUB_B, warnings[0])
        self.assertIn("3.7", warnings[0])

    def test_no_bytecode_means_no_warning(self):
        self.assertFalse([n for n in score(out_api())["notes"] if n.startswith("WARNING")])

    def test_malformed_code_response_raises_instead_of_assuming_an_eoa(self):
        for bad in (None, 5, "6080", ""):
            with self.assertRaises(sut.Hip4ReadError):
                score(out_api(code={OUT_SUB_A: bad}))


# =============================================================== 3. failures


class TestFailureHandling(unittest.TestCase):
    def test_unknown_venue_raises_with_the_live_venue_list(self):
        with self.assertRaises(sut.Hip4ReadError) as cm:
            score(out_api(), "nope")
        self.assertIn("nope", str(cm.exception))
        self.assertIn("out", str(cm.exception))

    def test_outcome_meta_read_failure_propagates_and_emits_nothing(self):
        api = out_api()
        api.fail["outcomeMeta"] = ConnectionError("api down")
        with self.assertRaises(ConnectionError):
            score(api)

    def test_outcome_meta_without_deployers_is_a_read_error(self):
        for payload in ({"outcomes": []}, {"deployers": None}, [], None, "oops"):
            api = out_api()
            api.meta = payload
            with self.assertRaises(sut.Hip4ReadError):
                score(api)

    def test_multisig_read_failure_propagates_rather_than_guessing_a_key(self):
        api = out_api()
        api.fail["userToMultiSigSigners"] = RuntimeError("rate limited")
        with self.assertRaises(RuntimeError):
            score(api)

    def test_perp_dexs_failure_propagates(self):
        api = out_api()
        api.fail["perpDexs"] = ConnectionError("api down")
        with self.assertRaises(ConnectionError):
            score(api)

    def test_evm_rpc_failure_propagates(self):
        api = out_api()
        api.evm = mock.Mock(side_effect=ConnectionError("rpc down"))
        with self.assertRaises(ConnectionError):
            score(api)

    def _assert_economics_degraded(self, entry, expected_error_prefix):
        self.assertEqual(scores_of(entry), scores_of(score(out_api())))  # authority scores untouched
        self.assertEqual(set(entry["reads"]["economicWeight"]), {"error"})  # no partial or invented numbers
        self.assertTrue(entry["reads"]["economicWeight"]["error"].startswith(expected_error_prefix))
        self.assertNotIn("outcomeDeployerLimits", entry["reads"])
        self.assertTrue(any("economic weight NOT read this run" in n for n in entry["notes"]))

    def test_asset_context_failure_degrades_the_informational_block_only(self):
        api = out_api()
        api.fail["spotMetaAndAssetCtxs"] = ValueError("bad json")
        self._assert_economics_degraded(score(api), "ValueError")

    def test_malformed_asset_context_payload_degrades_too(self):
        api = out_api()
        api.ctxs = None  # -> `resp[1]` is None -> TypeError while iterating
        self._assert_economics_degraded(score(api), "TypeError")

    def test_stake_read_failure_degrades_without_partial_economics(self):
        api = out_api()
        api.stake = {}
        self._assert_economics_degraded(score(api), "KeyError")

    def test_deployer_limits_failure_degrades(self):
        api = out_api()
        api.fail["outcomeDeployerLimits"] = ConnectionError("api down")
        self._assert_economics_degraded(score(api), "ConnectionError")

    def test_daily_volume_history_retries_then_raises(self):
        meta = {"outcomes": [_outcome(1, "out")]}
        calls = []

        def flaky(body):
            calls.append(body["type"])
            raise ConnectionError("down")

        with mock.patch.object(sut.mt, "info", flaky), mock.patch.object(sut.time, "sleep"):
            with self.assertRaises(sut.Hip4ReadError):
                sut.venue_daily_face_volume("out", meta)
        self.assertEqual(calls, ["candleSnapshot"] * 3)

    def test_daily_volume_history_sums_per_utc_day_across_outcomes(self):
        meta = {"outcomes": [_outcome(1, "out"), _outcome(2, "out"), _outcome(3, "txyz")]}
        day = 1_789_000_000_000 - (1_789_000_000_000 % 86_400_000)  # a UTC midnight, ms
        by_coin = {"#10": [{"t": day, "v": "5"}, {"t": day + 86_400_000, "v": "7"}], "#20": [{"t": day, "v": "1"}]}
        with mock.patch.object(sut.mt, "info", lambda body: by_coin[body["req"]["coin"]]):
            out = sut.venue_daily_face_volume("out", meta)  # outcome 3 belongs to another venue: never queried
        self.assertEqual(sorted(out.values()), [6.0, 7.0])


@contextlib.contextmanager
def _local_timezone(name):
    """A non-UTC local zone, so that a `localtime` bucketing bug cannot hide on a machine that happens to run in UTC."""
    old = os.environ.get("TZ")
    os.environ["TZ"] = name
    time.tzset()
    try:
        yield
    finally:
        if old is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = old
        time.tzset()


class TestDailyVolumeHistory(unittest.TestCase):
    def test_requests_a_seven_day_window_of_daily_candles_for_the_yes_coin(self):
        now_ms = 1_789_000_123_456
        seen = []

        def fake(body):
            seen.append(body)
            return []

        with mock.patch.object(sut.mt, "info", fake):
            sut.venue_daily_face_volume("out", {"outcomes": [_outcome(3, "out")]}, now_ms=now_ms)
        self.assertEqual(seen, [{"type": "candleSnapshot", "req": {"coin": "#30", "interval": "1d", "startTime": now_ms - 7 * 86_400_000, "endTime": now_ms}}])

    def test_days_are_bucketed_by_utc_not_by_the_local_timezone(self):
        now_ms = 1_789_000_123_456
        just_after_utc_midnight = (now_ms // 86_400_000) * 86_400_000 + 1000
        expected_day = time.strftime("%Y-%m-%d", time.gmtime(just_after_utc_midnight / 1000))
        with mock.patch.object(sut.mt, "info", lambda body: [{"t": just_after_utc_midnight, "v": "5"}]), _local_timezone("America/Los_Angeles"):
            out = sut.venue_daily_face_volume("out", {"outcomes": [_outcome(3, "out")]}, now_ms=now_ms)
        self.assertEqual(out, {expected_day: 5.0})  # in Los Angeles that instant is still the PREVIOUS calendar day


def _settle_tx(outcome, fraction, description, at_ms, error=None, template="template:binaryPrice", h=None):
    return {"time": at_ms, "user": "0xsub", "block": 1, "hash": h or f"0x{outcome:064x}", "error": error,
            "action": {"type": "outcomeDeploy", "venue": "skew", "operation": {"settleOutcome": {
                "outcome": outcome, "settleFraction": fraction, "details": "", "nameAndDescription": [template, description], "sideNames": ["template:Yes", "template:No"]}}}}


def _utc_ms(y, mo, d, h=0, mi=0, sec=0):
    return calendar.timegm((y, mo, d, h, mi, sec)) * 1000


class TestSettlementHistory(unittest.TestCase):
    """The on-chain evidence behind data doc section 8 (early settles, 0.5 settles, key cadence), as a pure function
    over explorer transactions so a reader can re-derive it and the parsing is locked in."""
    SUB = "0x1c867861e0cffb0eba07d9d94f716189c130dac6"
    DESC = "perp:BTC|priceDescription:the Pyth BTC/USD price|seconds:90|threshold:75200|time:20260921-0600"

    def test_a_settle_more_than_an_hour_before_the_stated_time_is_reported_with_its_fraction(self):
        stated = _utc_ms(2026, 9, 21, 6, 0)
        at = stated - int(62.8 * 3_600_000)
        h = sut.settlement_history({self.SUB: [_settle_tx(3069, "0.5", self.DESC, at)]})
        self.assertEqual(h["settleOutcomeSucceeded"], 1)
        self.assertEqual(h["byTemplateAndFraction"], {"template:binaryPrice|0.5": 1})
        self.assertEqual(len(h["early"]), 1)
        e = h["early"][0]
        self.assertEqual((e["outcome"], e["settleFraction"], e["hoursBeforeStatedTime"], e["address"]), (3069, "0.5", 62.8, self.SUB))
        self.assertEqual(h["onTimeDelaySeconds"], {})

    def test_on_time_settles_give_the_delay_after_the_stated_time_per_address(self):
        stated = _utc_ms(2026, 9, 21, 6, 0)
        txs = [_settle_tx(i, "1", self.DESC, stated + d * 1000) for i, d in enumerate((5.5, 8.25, 13.75), start=1)]
        h = sut.settlement_history({self.SUB: txs})
        self.assertEqual(h["early"], [])
        self.assertEqual(h["onTimeDelaySeconds"], {self.SUB: {"n": 3, "median": 8.2, "min": 5.5, "max": 13.8}})

    def test_the_one_hour_margin_is_strict_and_decides_early_versus_on_time(self):
        stated = _utc_ms(2026, 9, 21, 6, 0)
        exactly_one_hour = sut.settlement_history({self.SUB: [_settle_tx(1, "1", self.DESC, stated - 3_600_000)]})
        self.assertEqual(exactly_one_hour["early"], [])
        self.assertEqual(exactly_one_hour["onTimeDelaySeconds"][self.SUB]["median"], -3600.0)  # settled early by exactly the margin: still "on time"
        just_over = sut.settlement_history({self.SUB: [_settle_tx(1, "1", self.DESC, stated - 3_600_001)]})
        self.assertEqual(len(just_over["early"]), 1)
        long_after = sut.settlement_history({self.SUB: [_settle_tx(1, "1", self.DESC, stated + 3_600_001)]})
        self.assertEqual((long_after["early"], long_after["onTimeDelaySeconds"]), ([], {}))  # late by more than the margin: neither bucket

    def test_failed_settles_are_counted_apart_and_never_as_settled(self):
        stated = _utc_ms(2026, 9, 21, 6, 0)
        h = sut.settlement_history({self.SUB: [_settle_tx(1, "0.5", self.DESC, stated - 10 * 3_600_000, error="Outcome already settled")]})
        self.assertEqual((h["settleOutcomeSucceeded"], h["settleOutcomeFailed"], h["early"], h["byTemplateAndFraction"]), (0, 1, [], {}))

    def test_missing_or_malformed_stated_time_is_counted_not_guessed(self):
        at = _utc_ms(2026, 9, 18)
        txs = [_settle_tx(1, "1", "choice:A", at), _settle_tx(2, "1", "time:not-a-date|x:y", at), _settle_tx(3, "1", "garbage without colon", at),
               _settle_tx(4, "1", "expiry:20260921-0600|choice:A", at)]
        h = sut.settlement_history({self.SUB: txs})
        self.assertEqual(h["settleOutcomeSucceeded"], 4)
        self.assertEqual(h["settleOutcomeWithoutStatedTime"], 3)
        self.assertEqual(len(h["early"]), 1)  # the `expiry` keyword is the stated time of question outcomes and sports markets
        self.assertEqual(h["early"][0]["outcome"], 4)

    def test_stated_times_are_read_as_utc_whatever_the_local_timezone(self):
        stated = _utc_ms(2026, 9, 21, 6, 0)
        with _local_timezone("America/Los_Angeles"):
            self.assertEqual(sut._stated_time_ms(self.DESC), stated)

    def test_other_actions_are_not_settlements(self):
        register = {"time": 1, "user": "0x", "block": 1, "hash": "0x1", "error": None,
                    "action": {"type": "outcomeDeploy", "venue": "skew", "operation": {"registerStandaloneOutcomeFromTemplate": {"id": "binaryPrice", "keywordToValue": []}}}}
        question = {"time": 2, "user": "0x", "block": 1, "hash": "0x2", "error": None,
                    "action": {"type": "outcomeDeploy", "venue": "out", "operation": {"settleQuestion2": {"question": 3, "outcomeSettlements": []}}}}
        spot = {"time": 3, "user": "0x", "block": 1, "hash": "0x3", "error": None, "action": {"type": "spotSend"}}
        h = sut.settlement_history({self.SUB: [register, question, spot]})
        self.assertEqual(h["settleOutcomeSucceeded"], 0)
        self.assertEqual(h["windowByAddress"][self.SUB]["txs"], 3)
        self.assertIn("lower bound", h["limit"])

    def test_fetch_reads_the_deployer_and_every_sub_deployer_of_the_requested_venue_only(self):
        api = out_api()
        requested = []

        def fake_post(url, body):
            requested.append((url, body))
            return {"txs": []}

        with patched(api), mock.patch.object(sut.mt, "_post", fake_post):
            h = sut.fetch_settlement_history("out")
        self.assertEqual({u for _, u in ((b["type"], b["user"]) for _, b in requested)}, {OUT_DEP, OUT_SUB_A, OUT_SUB_B})
        self.assertEqual({url for url, _ in requested}, {sut.EXPLORER_URL})
        self.assertEqual({b["type"] for _, b in requested}, {"userDetails"})
        self.assertEqual(h["settleOutcomeSucceeded"], 0)
        with patched(api), mock.patch.object(sut.mt, "_post", fake_post):
            with self.assertRaises(sut.Hip4ReadError):
                sut.fetch_settlement_history("nope")

    def test_fetch_raises_on_a_payload_without_a_tx_list(self):
        for bad in ({}, {"txs": None}, [], None):
            with patched(out_api()), mock.patch.object(sut.mt, "_post", lambda url, body, bad=bad: bad):
                with self.assertRaises(sut.Hip4ReadError):
                    sut.fetch_settlement_history("out")


class TestCrossCheckHelpers(unittest.TestCase):
    def test_signer_closure_follows_nesting_cuts_cycles_and_excludes_the_start(self):
        graph = {"0xa": {"0xb", "0xc"}, "0xb": {"0xa", "0xd"}, "0xd": {"0xe"}}  # 0xb points back at 0xa
        self.assertEqual(sut._signer_closure("0xA", lambda a: graph.get(a, set())), {"0xb", "0xc", "0xd", "0xe"})
        self.assertEqual(sut._signer_closure("0xe", lambda a: graph.get(a, set())), set())

    def test_signer_closure_never_expands_the_same_address_twice(self):
        # the cycle cut is what keeps the one-off tool's network calls bounded: with it each address is expanded once
        graph = {"0xa": {"0xb", "0xc"}, "0xb": {"0xa", "0xc"}, "0xc": {"0xa", "0xb"}}
        calls = []

        def expand(a):
            calls.append(a)
            return graph.get(a, set())

        self.assertEqual(sut._signer_closure("0xa", expand), {"0xb", "0xc"})
        self.assertEqual(sorted(calls), ["0xa", "0xb", "0xc"])

    def test_signer_closure_depth_cap(self):
        graph = {f"0x{i}": {f"0x{i + 1}"} for i in range(10)}
        self.assertEqual(sut._signer_closure("0x0", lambda a: graph.get(a, set()), max_depth=3), {"0x1", "0x2", "0x3"})

    def test_addresses_are_harvested_from_reads_and_notes_case_insensitively(self):
        entries = [{"label": "A", "reads": {"k": "0x" + "AB" * 20}, "notes": [f"holder {OUT_SUB_A} and short 0xabc"]},
                   {"label": "B", "reads": [OUT_SUB_A.upper().replace("0X", "0x")]}]
        found = sut._addresses_by_target(entries)
        self.assertEqual(found["0x" + "ab" * 20], {"A"})
        self.assertEqual(found[OUT_SUB_A], {"A", "B"})
        self.assertEqual(len(found), 2)  # the truncated 0xabc is not an address

    def test_overlap_lists_only_keys_present_in_the_universe(self):
        universe = {"0xaa": {"L1"}, "0xbb": {"L2", "L3"}}
        self.assertEqual(sut._keys_overlapping_universe({"0xbb", "0xcc"}, universe), {"0xbb": ["L2", "L3"]})
        self.assertEqual(sut._keys_overlapping_universe({"0xcc"}, universe), {})


# =============================================================== 4. wiring


def _hip4_wrapper(venue):
    def wrapper(_unused_arg=None):
        return sut.score_hip4_outcome_deployer(venue)
    wrapper.__name__ = f"score_hip4_{venue}"
    return wrapper


class TestScoreAllWiring(unittest.TestCase):
    def test_no_hip4_venue_is_registered_in_score_all_yet(self):
        # RECORDED DECISION (data/scored_targets_2026-09-19-hip4-outcome-deployers.md): all three live venues
        # (out, txyz, skew) were sized and none demonstrably clears the real-usage bar the HIP-3 dexes were
        # promoted under, so none is wired in. A future promotion must change this test together with the
        # registry, in the same commit, with the sizing evidence in the data file.
        names = [s.__name__ for s in hl_scorers.SIMPLE_SCORERS]
        self.assertEqual([n for n in names if "hip4" in n.lower()], [])

    def test_a_failing_hip4_scorer_is_skipped_without_losing_the_others(self):
        api = out_api()
        api.fail["outcomeMeta"] = ConnectionError("api down")
        good = lambda _u=None: {"label": "good", "target": "0x1", "compositeScore": 50}  # noqa: E731
        good.__name__ = "score_good"
        buf = io.StringIO()
        with patched(api), mock.patch.object(hl_scorers, "SIMPLE_SCORERS", [_hip4_wrapper("out"), good]), contextlib.redirect_stdout(buf):
            results = hl_scorers.score_all()
        self.assertEqual([r["label"] for r in results], ["good"])
        self.assertIn("SKIPPED score_hip4_out", buf.getvalue())
        self.assertIn("ConnectionError", buf.getvalue())

    def test_a_promoted_venue_gets_the_l1_cap_and_keeps_its_scores(self):
        l1 = lambda _u=None: {"label": "Hyperliquid L1 (test double)", "target": "0x2", "compositeScore": 26}  # noqa: E731
        l1.__name__ = "score_l1_double"
        with patched(out_api()), mock.patch.object(hl_scorers, "SIMPLE_SCORERS", [l1, _hip4_wrapper("out")]), contextlib.redirect_stdout(io.StringIO()):
            results = hl_scorers.score_all()
        entry = next(r for r in results if r["label"] == "HIP-4 outcome deployer out")
        self.assertEqual(entry["compositeScore"], 9)
        self.assertEqual(entry["l1CappedComposite"], 9)  # min(9, 26): the cap has no effect on an already-weak target
        self.assertEqual(validate_all.validate_entry(entry), [])
        # the identity override that targets HIP-3 dex `para` must not touch a HIP-4 entry
        self.assertFalse(any(n.startswith("CORRECTED") for n in entry["notes"]))

    def test_the_l1_cap_actually_binds_on_a_strong_promoted_venue(self):
        # a 3-of-4 deployer with no sub-deployer scores 44; against an L1 composite of 26 the cap must lower it
        # (the previous test only showed min(9, 26) = 9, which would also pass if the cap were not applied at all)
        l1 = lambda _u=None: {"label": "Hyperliquid L1 (test double)", "target": "0x2", "compositeScore": 26}  # noqa: E731
        l1.__name__ = "score_l1_double"
        api = out_api(deployers=[_venue("out", OUT_DEP, {})])
        with patched(api), mock.patch.object(hl_scorers, "SIMPLE_SCORERS", [l1, _hip4_wrapper("out")]), contextlib.redirect_stdout(io.StringIO()):
            results = hl_scorers.score_all()
        entry = next(r for r in results if r["label"] == "HIP-4 outcome deployer out")
        self.assertEqual(entry["compositeScore"], 44)  # the target's own score is never overwritten
        self.assertEqual(entry["l1CappedComposite"], 26)



# ======================================================================================
# ADDED 2026-09-21: HyperEVM targets sharing a root holder (METHODOLOGY.md 4.5, extended)
# ======================================================================================
def _evm_entry(label, roles, cross=100):
    return {"label": label, "crossExposureScore": cross, "compositeScore": 4, "notes": [],
            "reads": {"roleHolders": {f"{role}:{holder}": {"adminKey": 65} for role, holder in roles}}}


SAFE_S = "0x18A82c968B992D28D4D812920eB7b4305306f8F1"


class TestHyperEvmSharedRootExposure(unittest.TestCase):
    def test_two_targets_with_the_same_default_admin_holder_each_read_80_and_keep_their_composite(self):
        a = _evm_entry("Kinetiq A", [("DEFAULT_ADMIN_ROLE", SAFE_S), ("OPERATOR_ROLE", "0x" + "11" * 20)])
        b = _evm_entry("Kinetiq B", [("DEFAULT_ADMIN_ROLE", SAFE_S.lower()), ("OPERATOR_ROLE", "0x" + "22" * 20)])
        hl_scorers._apply_hyperevm_shared_root_exposure([a, b])
        self.assertEqual((a["crossExposureScore"], b["crossExposureScore"]), (80, 80))
        self.assertEqual((a["compositeScore"], b["compositeScore"]), (4, 4))
        self.assertTrue(any("was 100" in n and "Kinetiq B" in n for n in a["notes"]))

    def test_three_targets_sharing_a_root_read_60(self):
        entries = [_evm_entry(f"T{i}", [("DEFAULT_ADMIN_ROLE", SAFE_S)]) for i in range(3)]
        hl_scorers._apply_hyperevm_shared_root_exposure(entries)
        self.assertEqual([e["crossExposureScore"] for e in entries], [60, 60, 60])

    def test_an_operational_role_shared_alone_is_not_a_shared_root(self):
        a = _evm_entry("A", [("DEFAULT_ADMIN_ROLE", "0x" + "aa" * 20), ("OPERATOR_ROLE", SAFE_S)])
        b = _evm_entry("B", [("DEFAULT_ADMIN_ROLE", "0x" + "bb" * 20), ("OPERATOR_ROLE", SAFE_S)])
        hl_scorers._apply_hyperevm_shared_root_exposure([a, b])
        self.assertEqual((a["crossExposureScore"], b["crossExposureScore"]), (100, 100))
        self.assertEqual((a["notes"], b["notes"]), ([], []))

    def test_a_role_registry_owner_counts_as_a_root(self):
        a = _evm_entry("Vault A", [("RoleRegistry.owner()", SAFE_S)])
        b = _evm_entry("Vault B", [("RoleRegistry.owner()", SAFE_S)])
        hl_scorers._apply_hyperevm_shared_root_exposure([a, b])
        self.assertEqual((a["crossExposureScore"], b["crossExposureScore"]), (80, 80))

    def test_it_never_raises_a_value_a_scorer_already_lowered(self):
        a = _evm_entry("A", [("DEFAULT_ADMIN_ROLE", SAFE_S)], cross=40)
        b = _evm_entry("B", [("DEFAULT_ADMIN_ROLE", SAFE_S)])
        hl_scorers._apply_hyperevm_shared_root_exposure([a, b])
        self.assertEqual((a["crossExposureScore"], b["crossExposureScore"]), (40, 80))

    def test_targets_without_role_holders_are_left_alone(self):
        dex = {"label": "HIP-3 dex xyz", "crossExposureScore": 100, "compositeScore": 9, "reads": {"deployer": SAFE_S}}
        evm = _evm_entry("A", [("DEFAULT_ADMIN_ROLE", SAFE_S)])
        hl_scorers._apply_hyperevm_shared_root_exposure([dex, evm])
        self.assertEqual((dex["crossExposureScore"], evm["crossExposureScore"]), (100, 100))
        self.assertNotIn("notes", dex)

    def test_a_single_holder_of_a_root_shared_with_nobody_is_unchanged(self):
        a = _evm_entry("A", [("DEFAULT_ADMIN_ROLE", "0x" + "aa" * 20)])
        b = _evm_entry("B", [("DEFAULT_ADMIN_ROLE", "0x" + "bb" * 20)])
        hl_scorers._apply_hyperevm_shared_root_exposure([a, b])
        self.assertEqual((a["crossExposureScore"], b["crossExposureScore"]), (100, 100))

    def test_score_all_runs_the_pass_and_a_failure_in_it_does_not_discard_results(self):
        a = _evm_entry("Kinetiq A", [("DEFAULT_ADMIN_ROLE", SAFE_S)])
        b = _evm_entry("Kinetiq B", [("DEFAULT_ADMIN_ROLE", SAFE_S)])
        l1 = {"label": "Hyperliquid L1 (HyperCore validator set)", "crossExposureScore": 100, "compositeScore": 26}
        with mock.patch.object(hl_scorers, "SIMPLE_SCORERS", [lambda: l1, lambda: a, lambda: b]), \
                mock.patch.object(hl_scorers, "_apply_hyperevm_identity_overrides"), \
                mock.patch.object(hl_scorers, "_apply_kinetiq_oracle_authority_fix"), \
                contextlib.redirect_stdout(io.StringIO()):
            results = hl_scorers.score_all()
        self.assertEqual([r["crossExposureScore"] for r in results if r["label"].startswith("Kinetiq")], [80, 80])
        with mock.patch.object(hl_scorers, "SIMPLE_SCORERS", [lambda: l1, lambda: a]), \
                mock.patch.object(hl_scorers, "_apply_hyperevm_identity_overrides"), \
                mock.patch.object(hl_scorers, "_apply_kinetiq_oracle_authority_fix"), \
                mock.patch.object(hl_scorers, "_apply_hyperevm_shared_root_exposure", side_effect=RuntimeError("boom")), \
                contextlib.redirect_stdout(io.StringIO()) as out:
            results = hl_scorers.score_all()
        self.assertEqual(len(results), 2)  # nothing discarded
        self.assertIn("HyperEVM shared-root exposure FAILED", out.getvalue())


if __name__ == "__main__":
    unittest.main()
