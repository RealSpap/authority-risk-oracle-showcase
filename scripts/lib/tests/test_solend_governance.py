"""
Unit tests for the Solend DAO governance target added 2026-09-17
(`chains/solana/scorers.py::score_solend_dao_governance`, `chains/solana/
scripts/sol_read.py::read_realm`/`read_governance`) -- the first Realms-
governed target this project scores, closing METHODOLOGY.md 6.1's
"untested" flag on the Realms governance formula.

Two things are tested independently of any live RPC call:
  1. `read_realm`/`read_governance`'s byte-decode logic, against the EXACT
     account bytes fetched live from Solana Mainnet Beta on 2026-09-17
     (embedded below as a frozen fixture, not re-fetched) -- a regression
     here would mean a future dependency change silently breaks the byte
     offsets without any test catching it.
  2. `_score_full_power_path("realms_governance", ...)` -- the new formula
     kind, generalizing METHODOLOGY.md 6.1's Realms governance row to
     `transactions_hold_up_time = 0` for the first time.

`sol_read.acct` is monkeypatched rather than mocking the network -- these
are the same real bytes `curl`/`getAccountInfo` returned live, just frozen
so the test suite doesn't depend on network access or the realm's mutable
on-chain state (a future community vote could change `voting_base_time`
without this project's own regression coverage silently breaking).
"""
import importlib.util
import os
import sys
import unittest

REPO_ROOT = os.path.join(os.path.dirname(__file__), "..", "..", "..")

# Exact account bytes, base64, fetched live from https://api.mainnet-beta.solana.com
# on 2026-09-17 (see chains/solana/data/methodology_test_2026-09-17-solend-governance.md
# for the full derivation and reproduction commands).
REALM_B64 = (
    "EAZ9atQQIPBPun2o3QZ205nSbEFAY4bwA5ygBjMDtMUrAAAAAAAAAABAQg8AAAAAAAAA5AtUAgAAAAAAAAAAAAAAAAHODKJHko7F7cplKEMqWPRD"
    "2o195FN7HrzioOvCBkQeJgoAAABTb2xlbmQgREFPAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=="
)
GOVERNANCE_B64 = (
    "FGYgL2HT/N5U9v/y90GYcU/MlVgol6zT8J9lOSpufakdBn1q1BAg8E+6fajdBnbTmdJsQUBjhvADnKAGMwO0xSsPAAAAAAEARCk1OgAAAAAAAACA"
    "9AMAAgAAAAABAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAA=="
)


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


sol_read = _load_module("aro_test_sol_read_solend", "chains/solana/scripts/sol_read.py")


class TestReadRealm(unittest.TestCase):
    def setUp(self):
        self._orig_acct = sol_read.acct
        sol_read.acct = lambda url, pk, enc="base64", length=None: {"data": [REALM_B64, "base64"]}

    def tearDown(self):
        sol_read.acct = self._orig_acct

    def test_decodes_community_mint_and_name(self):
        r = sol_read.read_realm("unused-url", "unused-pk")
        self.assertEqual(r["community_mint"], "SLNDpmoWTVADgEdndyvWzroNL7zSi1dF9PC3xHGtPwp")
        self.assertEqual(r["name"], "Solend DAO")
        self.assertEqual(r["account_type"], 16)

    def test_decodes_authority_as_bare_eoa_pubkey(self):
        r = sol_read.read_realm("unused-url", "unused-pk")
        self.assertEqual(r["authority"], "EsLAEeKA1dUJRiPpbTAm7r94KqGDAKe1ivH8PLAAuSxV")

    def test_no_council_mint(self):
        r = sol_read.read_realm("unused-url", "unused-pk")
        self.assertIsNone(r["council_mint"])

    def test_supply_fraction_max_vote_weight_source(self):
        r = sol_read.read_realm("unused-url", "unused-pk")
        self.assertEqual(r["community_mint_max_voter_weight_source"], {"kind": "SupplyFraction", "value": 10_000_000_000})


class TestReadGovernance(unittest.TestCase):
    def setUp(self):
        self._orig_acct = sol_read.acct
        sol_read.acct = lambda url, pk, enc="base64", length=None: {"data": [GOVERNANCE_B64, "base64"]}

    def tearDown(self):
        sol_read.acct = self._orig_acct

    def test_realm_and_governed_account_match_solend(self):
        g = sol_read.read_governance("unused-url", "unused-pk")
        self.assertEqual(g["realm"], "7sf3tcWm58vhtkJMwuw2P3T6UBX7UE5VKxPMnXJUZ1Hn")
        self.assertEqual(g["governed_account"], "SLNDpmoWTVADgEdndyvWzroNL7zSi1dF9PC3xHGtPwp")
        self.assertEqual(g["account_type"], 20)

    def test_zero_hold_up_time(self):
        g = sol_read.read_governance("unused-url", "unused-pk")
        self.assertEqual(g["transactions_hold_up_time_s"], 0)

    def test_three_day_voting_base_time(self):
        g = sol_read.read_governance("unused-url", "unused-pk")
        self.assertEqual(g["voting_base_time_s"], 259200)

    def test_proposals_count(self):
        g = sol_read.read_governance("unused-url", "unused-pk")
        self.assertEqual(g["proposals_count"], 15)


solana = _load_module("aro_test_solana_scorers_solend", "chains/solana/scorers.py")


class TestRealmsGovernanceFormula(unittest.TestCase):
    """`_score_full_power_path("realms_governance", ...)` -- generalizes
    METHODOLOGY.md 6.1's Realms governance row to hold-up = 0 (Solend's
    live case) without a separate branch. Also covers the countable
    council/community-threshold branch, calibrated 2026-09-17 against a
    real 5-of-7 council (the SPL Governance shared instance's own
    controller) by reusing the existing Squads t-of-n multisig formula.

    RECONCILED 2026-09-19 (METHODOLOGY.md section 7, was flagged "NOT yet
    closed"): the timelock formula used to sum voting_s + cooloff_s +
    holdup_s into the delay curve. spl-governance's own source doc
    comments establish voting_base_time/voting_cool_off_time are still
    part of the DECISION process (a proposal can still be voted on or
    vetoed), while transactions_hold_up_time is the only field that
    matches Squads v4 time_lock's own concept (a delay AFTER the decision
    is already final). The tests below reflect the reconciled formula:
    timelock depends ONLY on holdup_s, via the exact same
    `_delay_timelock_score` curve Squads v4 uses -- voting_s/cooloff_s no
    longer feed the score (still accepted params, disclosed by callers in
    their own notes)."""

    def test_token_voting_admin_and_multisig_are_flat_70(self):
        admin, multisig, timelock = solana._score_full_power_path(
            "realms_governance", voting_s=259200, holdup_s=0)
        self.assertEqual(admin, 70)
        self.assertEqual(multisig, 70)

    def test_flat_70_does_not_distinguish_real_different_vote_thresholds(self):
        # Documents, as a regression test, the exact gap METHODOLOGY.md
        # section 7's 2026-09-19 investigation found and left open: Solend's
        # REAL community_vote_threshold is YesVotePercentage(1) (1% of
        # supply) and Drift's is YesVotePercentage(2) (2%) -- two real,
        # already-decoded, materially different thresholds -- yet neither
        # value is ever passed into this formula, so both score IDENTICALLY.
        # This is not a bug to fix here (no calibrated alternative exists
        # yet, see METHODOLOGY.md 7); it is the concrete evidence that the
        # flat 70 could not have been derived from either DAO's own
        # threshold, and a future change that starts using the real
        # percentage should update or remove this test deliberately, not by
        # accident.
        solend_like = solana._score_full_power_path("realms_governance", voting_s=259200, holdup_s=0)
        drift_like = solana._score_full_power_path("realms_governance", voting_s=345600, cooloff_s=172800, holdup_s=0)
        self.assertEqual(solend_like[:2], drift_like[:2])
        self.assertEqual(solend_like[:2], (70, 70))

    def test_solend_live_parameters_give_timelock_0(self):
        # Solend's real, live parameters: 3 days voting, ZERO hold-up.
        # Reconciled formula: timelock depends only on holdup_s, so this is
        # now IDENTICAL to a Squads v4 multisig with time_lock=0 -- Solend
        # DAO can execute a passed proposal with no further notice at all,
        # exactly as risky as a zero-timelock multisig, not the old
        # formula's inflated 70 (which credited the 3-day VOTE itself as if
        # it were a post-decision notice period).
        admin, multisig, timelock = solana._score_full_power_path(
            "realms_governance", voting_s=259200, holdup_s=0)
        self.assertEqual(timelock, 0)

    def test_voting_time_alone_no_longer_affects_timelock(self):
        # A long voting period with zero hold-up must NOT score better than
        # a short voting period with zero hold-up -- voting_s is a
        # decision-forming window, not a post-decision notice period, and
        # folding it in was exactly the bug this reconciliation fixes.
        _, _, timelock_short_vote = solana._score_full_power_path(
            "realms_governance", voting_s=0, holdup_s=0)
        _, _, timelock_long_vote = solana._score_full_power_path(
            "realms_governance", voting_s=30 * 86400, holdup_s=0)
        self.assertEqual(timelock_short_vote, 0)
        self.assertEqual(timelock_long_vote, 0)

    def test_holdup_time_alone_matches_the_squads_v4_delay_curve(self):
        # The whole point of the reconciliation: a Realms holdup_s and a
        # Squads v4 delay_s of the SAME duration must now score IDENTICALLY
        # (same curve, same function) -- this is the direct regression test
        # for that equivalence, not just an indirect implication.
        _, _, realms_24h = solana._score_full_power_path("realms_governance", voting_s=0, holdup_s=86400)
        squads_24h = solana._score_full_power_path("squads_v4", threshold=2, voters=2, delay_s=86400)
        self.assertEqual(realms_24h, squads_24h[2])
        self.assertEqual(realms_24h, 50)

    def test_holdup_time_added_on_top_of_zero_no_longer_needs_voting_time(self):
        _, _, timelock_no_holdup = solana._score_full_power_path(
            "realms_governance", voting_s=86400, holdup_s=0)
        _, _, timelock_with_holdup = solana._score_full_power_path(
            "realms_governance", voting_s=86400, holdup_s=86400)
        self.assertGreater(timelock_with_holdup, timelock_no_holdup)

    def test_countable_threshold_matches_realms_security_council_calibration(self):
        # Calibrated 2026-09-17 against a real data point: the SPL Governance
        # shared instance's own controlling council is a real, live 5-of-7
        # weight-gated council (data/finding_2026-09-17-spl-governance-
        # shared-instance-controller.md). admin = 60+min(30,5*4) = 80;
        # multisig = min(100, round(15*5+40*5/7)) = min(100,104) = 100
        # (the same Squads t-of-n formula, not a new invented curve).
        admin, multisig, timelock = solana._score_full_power_path(
            "realms_governance", threshold=5, voters=7, voting_s=259200, holdup_s=0, cooloff_s=86400)
        self.assertEqual((admin, multisig), (80, 100))

    def test_countable_threshold_of_1_scores_as_on_curve_equivalent(self):
        # Same convention as Squads: a threshold of 1 means any single
        # member is decisive, regardless of member count or delay.
        admin, multisig, timelock = solana._score_full_power_path(
            "realms_governance", threshold=1, voters=7, voting_s=259200)
        self.assertEqual((admin, multisig), (5, 0))

    def test_countable_threshold_multisig_reuses_squads_formula_shape(self):
        # Higher threshold (more of the council required) should not score
        # a WORSE multisig number than a lower threshold over the same
        # voter count -- the Squads formula is monotonic in t, and this
        # branch must inherit that, not invert it.
        _, multisig_low, _ = solana._score_full_power_path(
            "realms_governance", threshold=2, voters=7, voting_s=259200)
        _, multisig_high, _ = solana._score_full_power_path(
            "realms_governance", threshold=6, voters=7, voting_s=259200)
        self.assertGreaterEqual(multisig_high, multisig_low)


class TestSolendDaoGovernanceComposite(unittest.TestCase):
    """The bare-EOA realm-authority path must dominate the combined score
    regardless of the token-voting path's own numbers -- this is the
    headline claim of the whole target, so it gets a direct regression
    test rather than relying only on a live dry-run."""

    def test_on_curve_realm_authority_beats_token_vote_path_via_min(self):
        admin_a, multisig_a, timelock_a = solana._score_full_power_path("on_curve")
        admin_b, multisig_b, timelock_b = solana._score_full_power_path(
            "realms_governance", voting_s=259200, holdup_s=0)
        admin = min(admin_a, admin_b)
        multisig = min(multisig_a, multisig_b)
        timelock = min(timelock_a, timelock_b)
        self.assertEqual((admin, multisig, timelock), (5, 0, 0))
        self.assertEqual(solana._composite(admin, multisig, timelock), 2)


if __name__ == "__main__":
    unittest.main()
