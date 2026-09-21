"""
Unit tests for the Drift Protocol target added 2026-09-17
(`chains/solana/scorers.py::score_drift_protocol`) and the new
`chains/solana/scripts/sol_read.py::read_governance_v2` decoder it needed
-- the modern GovernanceV2 byte layout, distinct from the legacy layout
`read_governance` implements for Solend's older deployment (same
account_type discriminant, different bytes -- see
`data/finding_2026-09-17-spl-governance-shared-instance-controller.md`'s
"What this changes" section for why this split exists).

`sol_read.acct` is monkeypatched with real account bytes fetched live from
Solana Mainnet Beta on 2026-09-17 (see `chains/solana/data/
methodology_test_2026-09-17-drift-protocol.md` for the full derivation),
frozen so this suite doesn't depend on network access or mutable on-chain
state.
"""
import base64
import importlib.util
import os
import sys
import unittest

REPO_ROOT = os.path.join(os.path.dirname(__file__), "..", "..", "..")

# Exact account bytes, base64, fetched live from https://api.mainnet-beta.solana.com
# on 2026-09-17. Stored compactly (one literal, no manual line-wrapping) to
# avoid a transcription error silently corrupting the fixture -- decoded
# once at import time below as a self-check.
DRIFT_REALM_B64 = "EL8IWhu1N2dSALhWuqVql/AqT0hITx1XafbfRKCxv9aEAAAAAAAAAAAAsFtMNkQAAAEAYLeYbIgAAAFQdsZ5CEto5KlSlTShsyCoQvnsRUVjvkOCWIHhg+OoDQAAAAAAAAAAAQNn3XAHVtcnLEs9pNXmpZ9sF3wUxkWkFkIm24rjC9m9CQAAAERyaWZ0IERBTwAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
DRIFT_GOV_B64 = "EtdQJEMl0k1arz+CioA1+M49XU0ju3UjfYtmRt4+404+t7kkxdRa/TV97Gugf8x7hXNOqCgSb4PPH54RgT2h2MQAAAAAAAIAyBeoBAAAAIBRAQAARgUAAgIAHgEAAAAAAAAAAAIAowIAAQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
DRIFT_SQUADS_B64 = "4HR5ukShT+yhlNKKtyEMrX97u+W6I3h+jBBntuPSbrJwi6BKrIghQwAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAABAAQDgAAcQAAAAAAAABXAAAAAAAAAAD9BwAAAAxCn85ycaFaVngUNrXlivK109VpfcVXEdhQ+IlFr8oSASkymLJWt34KFzjr5HaXUIcmjLQaUeXbxaG/p+QZLEt5B1wcclsjYrprcTqfnww+OpFfeK57ei7D99joY7Tun3bfB4HFLBdA9TkpsI8L8ojtZ/pQ8g3T8zFFrG/WGbTSSO18B7esqxfp2m6qmY1pojFa6d4AXsrhRKNeiYut5gBCWoU7B9JRZfgM2bmumUtF8H2dYqrDWG+svhd56uKZ1gz8ZD1pB9NUOY29Ga81/0fhMxTUKmVbMzbsmamC5O+zUL2M2UbjBwAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"

for _name in ("DRIFT_REALM_B64", "DRIFT_GOV_B64", "DRIFT_SQUADS_B64"):
    base64.b64decode(globals()[_name], validate=True)  # fail fast on a corrupted fixture


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


sol_read = _load_module("aro_test_sol_read_drift", "chains/solana/scripts/sol_read.py")


class TestReadGovernanceV2(unittest.TestCase):
    def setUp(self):
        self._orig_acct = sol_read.acct
        sol_read.acct = lambda url, pk, enc="base64", length=None: {"data": [DRIFT_GOV_B64, "base64"]}

    def tearDown(self):
        sol_read.acct = self._orig_acct

    def test_realm_matches_drift_dao(self):
        g = sol_read.read_governance_v2("unused-url", "unused-pk")
        self.assertEqual(g["realm"], "FVVXu18aNUqyFCfq8sGktPM62mqJAGaenv4z6UGUs5em")
        self.assertEqual(g["account_type"], 18)

    def test_community_vote_threshold_2_percent(self):
        g = sol_read.read_governance_v2("unused-url", "unused-pk")
        self.assertEqual(g["community_vote_threshold"], {"tag": 0, "kind": "YesVotePercentage", "pct": 2})

    def test_council_can_veto_but_not_pass(self):
        g = sol_read.read_governance_v2("unused-url", "unused-pk")
        self.assertEqual(g["council_vote_threshold"]["kind"], "Disabled")
        self.assertEqual(g["council_veto_vote_threshold"], {"tag": 0, "kind": "YesVotePercentage", "pct": 30})

    def test_real_one_day_holdup_and_four_day_voting(self):
        g = sol_read.read_governance_v2("unused-url", "unused-pk")
        self.assertEqual(g["transactions_hold_up_time_s"], 86400)
        self.assertEqual(g["voting_base_time_s"], 345600)
        self.assertEqual(g["voting_cool_off_time_s"], 172800)

    def test_disabled_threshold_consumes_no_payload_byte(self):
        # Regression test for the exact bug class this project already
        # caught once decoding by hand: VoteThreshold's Disabled variant
        # (tag 2) has NO payload byte, unlike YesVotePercentage/
        # QuorumPercentage (tag 0/1). Both council_vote_threshold and
        # community_veto_vote_threshold are Disabled here -- if the parser
        # wrongly consumed a byte for them, every field after would be
        # shifted and voting_cool_off_time_s (a known, distinctive value)
        # would NOT come out to exactly 172800.
        g = sol_read.read_governance_v2("unused-url", "unused-pk")
        self.assertEqual(g["council_vote_threshold"]["pct"], None)
        self.assertEqual(g["community_veto_vote_threshold"]["pct"], None)
        self.assertEqual(g["voting_cool_off_time_s"], 172800)


class TestReadRealmDrift(unittest.TestCase):
    def setUp(self):
        self._orig_acct = sol_read.acct
        sol_read.acct = lambda url, pk, enc="base64", length=None: {"data": [DRIFT_REALM_B64, "base64"]}

    def tearDown(self):
        sol_read.acct = self._orig_acct

    def test_decodes_drift_dao(self):
        r = sol_read.read_realm("unused-url", "unused-pk")
        self.assertEqual(r["name"], "Drift DAO")
        self.assertEqual(r["community_mint"], "DriFtupJYLTosbwoN8koMbEYSx54aFAVLddWsbksjwg7")

    def test_has_a_council_mint_unlike_solend(self):
        r = sol_read.read_realm("unused-url", "unused-pk")
        self.assertIsNotNone(r["council_mint"])

    def test_authority_is_not_a_bare_wallet_pubkey_string(self):
        # Not itself proof of self-governance (that requires the keytype
        # check the scorer does), but the realm decode must at least
        # produce SOME authority pubkey to check further.
        r = sol_read.read_realm("unused-url", "unused-pk")
        self.assertIsNotNone(r["authority"])
        self.assertEqual(r["authority"], "EJ5kEb9XkQC4rbc7uM45xoLM8TiagGCLad5YpGtMyz4")


class TestReadSquadsDrift(unittest.TestCase):
    def setUp(self):
        self._orig_acct = sol_read.acct
        sol_read.acct = lambda url, pk, enc="base64", length=None: {
            "data": [DRIFT_SQUADS_B64, "base64"], "owner": "SQDS4ep65T869zMMBKyuUq6aD6EgTu8psMjkvj52pCf"}

    def tearDown(self):
        sol_read.acct = self._orig_acct

    def test_current_multisig_is_4_of_7_with_real_delay(self):
        sq = sol_read.read_squads("unused-url", "unused-pk")
        self.assertEqual(sq["threshold"], 4)
        self.assertEqual(sq["members"], 7)
        self.assertEqual(sq["time_lock_s"], 3600)

    def test_config_authority_is_autonomous_default(self):
        # Contrasts with the INCIDENT-era multisig (data/backtest_2026-09-17-
        # drift-protocol-security-council-compromise.md), whose
        # config_authority was NOT the system default -- a real,
        # independently-found aggravating factor this project's own
        # methodology declines to score without a calibration target.
        sq = sol_read.read_squads("unused-url", "unused-pk")
        self.assertEqual(sq["config_authority"], "11111111111111111111111111111111")

    def test_one_member_lacks_vote_permission(self):
        solana = _load_module("aro_test_solana_scorers_drift_voters", "chains/solana/scorers.py")
        sq = sol_read.read_squads("unused-url", "unused-pk")
        self.assertEqual(solana._voters_with_vote_permission(sq), 6)


solana = _load_module("aro_test_solana_scorers_drift", "chains/solana/scorers.py")


class TestDriftBeforeAfterComposite(unittest.TestCase):
    """The headline claim of this target: a real, live-verified
    improvement over the 2026-04-01 incident's own 2-of-5/zero-timelock
    configuration, computed via the SAME formula, not two different
    stories -- a direct regression test, not just a live dry-run."""

    def test_incident_era_configuration_scores_32(self):
        admin, multisig, timelock = solana._score_full_power_path(
            "squads_v4", threshold=2, voters=5, delay_s=0)
        self.assertEqual((admin, multisig, timelock), (45, 46, 0))
        self.assertEqual(solana._composite(admin, multisig, timelock), 32)

    def test_current_configuration_scores_higher_than_incident_era(self):
        admin, multisig, timelock = solana._score_full_power_path(
            "squads_v4", threshold=4, voters=6, delay_s=3600)
        incident_composite = 32
        self.assertGreater(solana._composite(admin, multisig, timelock), incident_composite)

    def test_realm_authority_governance_path_does_not_dominate_today(self):
        # The program-upgrade Squads path's short 1-hour delay is the
        # binding constraint on timelock, not the multi-day governance
        # path -- confirms the combined score is NOT accidentally reading
        # only one path.
        squads_path = solana._score_full_power_path("squads_v4", threshold=4, voters=6, delay_s=3600)
        governance_path = solana._score_full_power_path(
            "realms_governance", voting_s=345600, cooloff_s=172800, holdup_s=86400)
        self.assertLess(squads_path[2], governance_path[2])


class TestScoreDriftProtocolRenouncedProgramAuthority(unittest.TestCase):
    """Regression test for an adversarial-review finding on this same-day
    addition: score_drift_protocol's program-upgrade path originally
    omitted `none_means_renounced=True`, so a renounced (None) upgrade
    authority scored as a false MISMATCH (20/20/0) instead of the safest
    band (100/100/100) -- the same bug class Jupiter/Kamino already guard
    against elsewhere in this file. Drift's authority isn't actually
    renounced today, so this monkeypatches the read to exercise the path
    directly rather than waiting for a real renouncement to test it."""

    def test_renounced_program_authority_is_not_scored_as_a_mismatch(self):
        # Patch the sol_read reference score_drift_protocol ACTUALLY calls
        # -- scorers.py's own module-level `import sol_read`, accessible as
        # `solana.sol_read` -- not this test file's own separately-loaded
        # `sol_read` alias (a different module object under a different
        # sys.modules key; patching the wrong one would silently no-op).
        orig_read_program = solana.sol_read.read_program
        orig_read_realm = solana.sol_read.read_realm
        orig_read_switchboard_pull_feed = solana.sol_read.read_switchboard_pull_feed
        orig_read_switchboard_queue = solana.sol_read.read_switchboard_queue
        try:
            # Renounced (None) for BOTH the Drift program (what this test is
            # actually about) and the Switchboard On-Demand program (added
            # 2026-09-19, see test_switchboard_on_demand.py for that path's
            # own dedicated coverage) -- keeps this test isolated to the bug
            # it targets instead of also exercising the newer code path.
            solana.sol_read.read_program = lambda url, pk: {"upgrade_authority": None}
            solana.sol_read.read_realm = lambda url, pk: {
                "community_mint": "DriFtupJYLTosbwoN8koMbEYSx54aFAVLddWsbksjwg7",
                "council_mint": None, "authority": None, "name": "Drift DAO",
            }
            solana.sol_read.read_switchboard_pull_feed = lambda url, pk: {
                "feed": pk, "owner": solana.sol_read.SWITCHBOARD_ON_DEMAND_PROGRAM, "discriminator_ok": True,
                "authority": None, "queue": "unused-queue", "feed_hash": "00" * 32}
            solana.sol_read.read_switchboard_queue = lambda url, pk: {
                "queue": pk, "owner": solana.sol_read.SWITCHBOARD_ON_DEMAND_PROGRAM,
                "discriminator_ok": True, "authority": None}
            result = solana.score_drift_protocol("unused-url")
        finally:
            solana.sol_read.read_program = orig_read_program
            solana.sol_read.read_realm = orig_read_realm
            solana.sol_read.read_switchboard_pull_feed = orig_read_switchboard_pull_feed
            solana.sol_read.read_switchboard_queue = orig_read_switchboard_queue
        self.assertEqual((result["adminKeyScore"], result["multisigScore"], result["timelockScore"]), (100, 100, 100))
        self.assertFalse(any("MISMATCH" in n for n in result["notes"]))


if __name__ == "__main__":
    unittest.main()
