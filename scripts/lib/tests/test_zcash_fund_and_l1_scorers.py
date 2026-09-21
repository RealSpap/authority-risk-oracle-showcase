"""
Unit tests for `chains/zcash/scorers.py::score_fund()` and three small pure
helpers behind `score_l1()` (`_independent_lineage_count`,
`_admin_key_score_l1`, `_timelock_score_l1`) -- found 2026-09-19 with zero
test coverage while auditing this ecosystem's scorers against the test
corpus.

`score_fund()`'s own orchestration (5 distinct outcomes: no spend found, a
malformed revealed script, an unrecognised suffix, a cross-host mismatch,
and the happy path with or without a second-host confirmation) is a
different layer than `find_multisig_spends()`'s own byte-level parsing,
which `test_zcash_read.py`/`p2sh_spends.py`'s own module already covers --
this file tests the ORCHESTRATION logic on top, the same "test the
decision layer, not just the primitive" split this project's other
scorer test files already establish (e.g. Plasma's/Robinhood's FakeHelpers
suites over already-tested `call_raw`/`get_code`).

`find_multisig_spends` is monkeypatched directly (it's imported at module
level into `scorers.py`'s own namespace, `from p2sh_spends import
find_multisig_spends`) rather than faked at the RPC layer -- this project's
usual "patch the imported name, not the transport" convention.
"""
import importlib.util
import os
import sys
import unittest

REPO_ROOT = os.path.join(os.path.dirname(__file__), "..", "..", "..")


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


scorers = _load_module("aro_test_zcash_scorers_fund_l1", "chains/zcash/scorers.py")

ADDRESS = "t3ZIfZXe4gtWH3pdKbRnh2wgc2CqLLKn4Hh"  # a syntactically valid stand-in P2SH address; NOT the real ZIP 271 lockbox (that is t3ev37Q2uL1sfTsiJQJiWJoFzQpDhmnUwYo, see scorers.FUNDS)
PK_A = "02" + "aa" * 32
PK_B = "02" + "bb" * 32
PK_C = "02" + "cc" * 32


def _spends_result(spends, scanned_txs=1):
    return {"address": ADDRESS, "scannedTxs": scanned_txs, "spendsFound": len(spends), "range": [0, 100], "spends": spends}


def _real_spend(m, n, pubkeys, op="CHECKMULTISIG", suffix=None, height=123456):
    return {"height": height, "m": m, "n": n, "op": op, "pubkeys": pubkeys, "suffix": suffix, "vin": 0, "transparentVout": 1}


class TestScoreFund(unittest.TestCase):
    def _wire(self, primary_spends, second_spends):
        orig = scorers.find_multisig_spends

        def fake(host, addr, start, end, window):
            if host == scorers.PRIMARY_HOST:
                return _spends_result(primary_spends)
            if host == scorers.SECOND_HOST:
                return _spends_result(second_spends)
            raise AssertionError(f"unexpected host: {host}")

        scorers.find_multisig_spends = fake
        self.addCleanup(lambda: setattr(scorers, "find_multisig_spends", orig))

    def test_two_of_three_cross_confirmed_scores_the_kn_ladder(self):
        spend = _real_spend(2, 3, [PK_A, PK_B, PK_C])
        self._wire([spend], [spend])
        result = scorers.score_fund("ZIP 271 lockbox", ADDRESS, 0, 100, 2000)
        self.assertEqual(result["adminKeyScore"], scorers.admin_key_score_kn(2, 3))
        self.assertEqual(result["multisigScore"], scorers.multisig_score_kn(2, 3))
        self.assertEqual(result["timelockScore"], 0)
        self.assertEqual(result["compositeScore"], scorers._composite(
            scorers.admin_key_score_kn(2, 3), scorers.multisig_score_kn(2, 3), 0))
        self.assertFalse(result["_degraded"])
        self.assertEqual(result["_pubkeys"], {PK_A, PK_B, PK_C})
        self.assertTrue(any("MATCH" in n for n in result["notes"]))

    def test_no_real_spend_on_primary_degrades_to_unresolved_floor(self):
        # A spend with only "redeemScriptHex" (not a recognised m-of-n) or a
        # "parseError" entry doesn't count as a real spend ("m" not in it).
        self._wire([{"height": 1, "redeemScriptHex": "deadbeef"}], [])
        result = scorers.score_fund("ZIP 271 lockbox", ADDRESS, 0, 100, 2000)
        self.assertEqual(result["adminKeyScore"], scorers._UNRESOLVED_P2SH_ADMIN_KEY)
        self.assertEqual(result["multisigScore"], scorers._UNRESOLVED_P2SH_MULTISIG)
        self.assertTrue(result["_degraded"])
        self.assertIsNone(result["crossExposureScore"])

    def test_malformed_script_n_mismatch_degrades(self):
        # n=3 declared but only 2 pubkeys actually present.
        spend = _real_spend(2, 3, [PK_A, PK_B])
        self._wire([spend], [])
        result = scorers.score_fund("ZIP 271 lockbox", ADDRESS, 0, 100, 2000)
        self.assertTrue(result["_degraded"])
        self.assertTrue(any("malformed" in n for n in result["notes"]))

    def test_malformed_script_m_out_of_range_degrades(self):
        spend = _real_spend(0, 3, [PK_A, PK_B, PK_C])  # m=0 is out of [1, n]
        self._wire([spend], [])
        result = scorers.score_fund("ZIP 271 lockbox", ADDRESS, 0, 100, 2000)
        self.assertTrue(result["_degraded"])

    def test_unrecognised_suffix_degrades(self):
        spend = _real_spend(2, 3, [PK_A, PK_B, PK_C], op="CHECKMULTISIGVERIFY", suffix="ff")
        self._wire([spend], [])
        result = scorers.score_fund("ZIP 271 lockbox", ADDRESS, 0, 100, 2000)
        self.assertTrue(result["_degraded"])
        self.assertTrue(any("unrecognised suffix" in n for n in result["notes"]))

    def test_recognised_checkmultisigverify_suffix_op1_is_accepted(self):
        spend = _real_spend(2, 3, [PK_A, PK_B, PK_C], op="CHECKMULTISIGVERIFY", suffix="51")
        self._wire([spend], [])
        result = scorers.score_fund("ZCG funding stream", ADDRESS, 0, 100, 2000)
        self.assertFalse(result["_degraded"])

    def test_cross_host_mismatch_on_threshold_degrades_but_keeps_primary_pubkeys(self):
        primary_spend = _real_spend(2, 3, [PK_A, PK_B, PK_C])
        second_spend = _real_spend(3, 3, [PK_A, PK_B, PK_C])  # different m
        self._wire([primary_spend], [second_spend])
        result = scorers.score_fund("ZIP 271 lockbox", ADDRESS, 0, 100, 2000)
        self.assertTrue(result["_degraded"])
        self.assertTrue(any("MISMATCH" in n for n in result["notes"]))
        self.assertEqual(result["_pubkeys"], {PK_A, PK_B, PK_C})

    def test_second_host_no_spend_proceeds_on_primary_alone_not_degraded(self):
        primary_spend = _real_spend(2, 3, [PK_A, PK_B, PK_C])
        self._wire([primary_spend], [])
        result = scorers.score_fund("ZIP 271 lockbox", ADDRESS, 0, 100, 2000)
        self.assertFalse(result["_degraded"])
        self.assertTrue(any("no multisig spend found to cross-check" in n for n in result["notes"]))

    def test_most_recent_spend_is_the_last_entry_in_the_list(self):
        # Comment in score_fund(): "most recent" = latest["m"]/["n"] uses
        # real_spends_p[-1], since a P2SH address commits to one script --
        # confirm an EARLIER, differently-shaped spend in the list doesn't
        # override the true (later) one.
        stale = _real_spend(1, 1, [PK_A], height=100)
        current = _real_spend(2, 3, [PK_A, PK_B, PK_C], height=200)
        self._wire([stale, current], [])
        result = scorers.score_fund("ZIP 271 lockbox", ADDRESS, 0, 100, 2000)
        self.assertEqual(result["adminKeyScore"], scorers.admin_key_score_kn(2, 3))


class TestIndependentLineageCount(unittest.TestCase):
    def test_single_zebra_version_counts_as_one(self):
        self.assertEqual(scorers._independent_lineage_count({"/Zebra:3.1.0/"}), 1)

    def test_zakura_fork_excluded_from_independence_count(self):
        self.assertEqual(scorers._independent_lineage_count({"/Zebra:3.1.0/", "/Zakura:1.0.0/"}), 1)

    def test_two_genuinely_independent_lineages_counts_as_two(self):
        self.assertEqual(scorers._independent_lineage_count({"/Zebra:3.1.0/", "/Ledokol:2.0.0/"}), 2)

    def test_never_returns_zero_even_if_everything_observed_is_a_fork(self):
        # "at least Zebra itself must be running for Mainnet to exist"
        self.assertEqual(scorers._independent_lineage_count({"/Zakura:1.0.0/"}), 1)

    def test_empty_observed_set_still_returns_one(self):
        self.assertEqual(scorers._independent_lineage_count(set()), 1)


class TestAdminKeyScoreL1(unittest.TestCase):
    def test_single_lineage_scores_20(self):
        self.assertEqual(scorers._admin_key_score_l1(1), 20)

    def test_two_lineages_scores_45(self):
        self.assertEqual(scorers._admin_key_score_l1(2), 45)

    def test_three_or_more_lineages_scores_65(self):
        self.assertEqual(scorers._admin_key_score_l1(3), 65)
        self.assertEqual(scorers._admin_key_score_l1(10), 65)

    def test_monotonically_non_decreasing_in_lineage_count(self):
        scores = [scorers._admin_key_score_l1(n) for n in range(1, 6)]
        self.assertEqual(scores, sorted(scores))


class TestTimelockScoreL1(unittest.TestCase):
    def test_returns_the_emergency_bypass_cap_constant(self):
        self.assertEqual(scorers._timelock_score_l1(), scorers._EMERGENCY_BYPASS_TIMELOCK_CAP)


if __name__ == "__main__":
    unittest.main()
