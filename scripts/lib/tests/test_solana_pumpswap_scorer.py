"""
Unit tests for `chains/solana/scorers.py::score_pumpswap` (PumpSwap AMM and
the pump.fun bonding-curve program it succeeds).

Scope: this scorer's OWN orchestration -- how its two full-power authority
paths (the program's own upgrade authority via Squads v4, and
`GlobalConfig.admin` via a SECOND, genuinely different Squads v4 multisig)
each degrade to the unresolved floor on a vault-PDA mismatch, how ONLY the
program-upgrade path short-circuits on a renounced (None) authority (the
GlobalConfig.admin path has no such allowance -- a real asymmetry in
`score_pumpswap`'s own two `_resolve_squads_v4` call sites, not a shared
formula detail), how the two paths combine via a per-COMPONENT min()
(METHODOLOGY.md 6.2) rather than one path winning outright, and the one
abort condition reachable through this target (`_resolve_squads_v4`'s
"config_authority is set" NotImplementedError). `_score_full_power_path`'s
own squads_v4 formula curve is already covered elsewhere in this repo
(test_drift_protocol.py, test_switchboard_on_demand.py,
test_solend_governance.py) and is not re-verified here -- it is only
*called*, the same way score_pumpswap itself calls it, to compute what this
scorer's own combine logic should produce from realistic path results. Same
convention as the closest sibling in shape, test_solana_jupiter_perps_scorer.py
(also a two-full-power-path, componentwise-min scorer), adapted here for
BOTH paths being Squads v4 (PumpSwap has no Squads v3 leg).

`sol_read.read_squads_vault` (the offline Squads v4 vault-0 PDA derivation
`_resolve_squads_v4` uses for BOTH paths here) is NOT monkeypatched -- it is
a pure, no-RPC computation, so this file computes the REAL vault-0 PDAs of
UPGRADE_MS and ADMIN_MS below (the exact constants `score_pumpswap`
hardcodes) and uses them as fixture data, the same "real derived PDA, not a
mocked derivation" convention test_solana_jupiter_perps_scorer.py uses.

`sol_read.read_pumpswap_global_config`'s own byte-decode logic already has
dedicated frozen-fixture coverage in test_solana_defi_config_admins.py --
not re-tested here; it is mocked at the orchestration level (its return
dict) as instructed.

Only the primitives this scorer actually calls (`read_program`,
`read_squads`, `read_pumpswap_global_config`) are faked, monkeypatched
directly on `scorers.py`'s own module-level `sol_read` reference -- the same
convention as test_drift_protocol.py / test_switchboard_on_demand.py /
test_solana_jupiter_perps_scorer.py.
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


solana = _load_module("aro_test_solana_scorers_pumpswap", "chains/solana/scorers.py")

# score_pumpswap's own hardcoded multisig constants.
UPGRADE_MS = "2yMoQqQrtbhq3nQ3wFoQQawWS65qcqUXcwHEYha4rshW"
ADMIN_MS = "8EujzwPFNhZ5m4Kpa2XtrumNgwCbhgWwny9YWLCKA5at"

# Real, offline-derived vault-0 PDAs for the two constants above -- computed
# via the SAME pure (no-RPC) function `_resolve_squads_v4` itself uses, left
# un-mocked in this file.
UPGRADE_VAULT0 = solana.sol_read.read_squads_vault(UPGRADE_MS, 0)["vault"]
ADMIN_VAULT0 = solana.sol_read.read_squads_vault(ADMIN_MS, 0)["vault"]

WRONG_UPGRADE_AUTHORITY = "WrongUpgradeAuthorityNotTheRealVault0PDA111"
WRONG_GC_ADMIN = "WrongGlobalConfigAdminNotTheRealVault0PDA11"


class TestScorePumpswap(unittest.TestCase):
    def setUp(self):
        self._orig_read_program = solana.sol_read.read_program
        self._orig_read_pumpswap_global_config = solana.sol_read.read_pumpswap_global_config
        self._orig_read_squads = solana.sol_read.read_squads
        # ms pubkey -> squads read dict; a key ABSENT here means "must not
        # be read" -- a mismatched/renounced path degrades WITHOUT ever
        # calling read_squads for it, per _resolve_squads_v4's own contract.
        self._squads_by_ms = {}

        def dispatch_read_squads(url, pk):
            if pk not in self._squads_by_ms:
                raise AssertionError(f"sol_read.read_squads should not be reached for {pk} on this code path")
            return self._squads_by_ms[pk]

        solana.sol_read.read_squads = dispatch_read_squads

    def tearDown(self):
        solana.sol_read.read_program = self._orig_read_program
        solana.sol_read.read_pumpswap_global_config = self._orig_read_pumpswap_global_config
        solana.sol_read.read_squads = self._orig_read_squads

    # -- path A (program upgrade authority, Squads v4) fixtures --------

    def _mock_upgrade_matched(self, threshold=3, n_voters=4, delay_s=0):
        solana.sol_read.read_program = lambda url, pk: {"upgrade_authority": UPGRADE_VAULT0}
        self._squads_by_ms[UPGRADE_MS] = {
            "multisig": UPGRADE_MS, "owner": solana.SQUADS_V4_PROGRAM,
            "config_authority": solana.SYSTEM_PROGRAM_DEFAULT,
            "threshold": threshold, "time_lock_s": delay_s, "members": n_voters,
            "member_list": [{"key": f"upgrade_signer_{i}", "mask": 7} for i in range(n_voters)],
        }

    def _mock_upgrade_mismatched(self):
        solana.sol_read.read_program = lambda url, pk: {"upgrade_authority": WRONG_UPGRADE_AUTHORITY}
        self._squads_by_ms.pop(UPGRADE_MS, None)

    def _mock_upgrade_renounced(self):
        solana.sol_read.read_program = lambda url, pk: {"upgrade_authority": None}
        self._squads_by_ms.pop(UPGRADE_MS, None)

    # -- path B (GlobalConfig.admin, Squads v4 -- a DIFFERENT multisig) --

    def _mock_admin_matched(self, threshold=3, n_voters=4, delay_s=0):
        solana.sol_read.read_pumpswap_global_config = lambda url, pk: {"global_config": pk, "admin": ADMIN_VAULT0}
        self._squads_by_ms[ADMIN_MS] = {
            "multisig": ADMIN_MS, "owner": solana.SQUADS_V4_PROGRAM,
            "config_authority": solana.SYSTEM_PROGRAM_DEFAULT,
            "threshold": threshold, "time_lock_s": delay_s, "members": n_voters,
            "member_list": [{"key": f"admin_signer_{i}", "mask": 7} for i in range(n_voters)],
        }

    def _mock_admin_mismatched(self):
        solana.sol_read.read_pumpswap_global_config = lambda url, pk: {"global_config": pk, "admin": WRONG_GC_ADMIN}
        self._squads_by_ms.pop(ADMIN_MS, None)

    def _mock_admin_none(self):
        # GlobalConfig.admin reading back None is NOT the same situation as
        # a loader-v3 upgrade authority reading back None -- there is no
        # on-chain "renounced admin" concept for this field, and
        # score_pumpswap's own call site does not pass
        # none_means_renounced=True for this path (see
        # test_global_config_admin_none_is_not_treated_as_renounced below).
        solana.sol_read.read_pumpswap_global_config = lambda url, pk: {"global_config": pk, "admin": None}
        self._squads_by_ms.pop(ADMIN_MS, None)

    # ---------------------------------------------------------------

    def test_both_paths_resolved_combines_via_componentwise_min_across_paths(self):
        # Deliberately DIFFERENT threshold/voters/delay on each path so a
        # bug that picked one path's whole triple (instead of taking the
        # min of each component independently) would be caught: path A
        # wins on adminKey and timelock, path B wins on multisig, and the
        # combined result must take each field from whichever path is
        # weaker on THAT field, not the whole triple from one path.
        self._mock_upgrade_matched(threshold=4, n_voters=4, delay_s=0)
        self._mock_admin_matched(threshold=2, n_voters=4, delay_s=90000)

        result = solana.score_pumpswap("unused-url")

        path_a = solana._score_full_power_path("squads_v4", threshold=4, voters=4, delay_s=0)
        path_b = solana._score_full_power_path("squads_v4", threshold=2, voters=4, delay_s=90000)
        expected = tuple(min(path_a[i], path_b[i]) for i in range(3))

        self.assertEqual(
            (result["adminKeyScore"], result["multisigScore"], result["timelockScore"]), expected)
        self.assertEqual(result["compositeScore"], solana._composite(*expected))
        # Confirms this really is a per-component min, not "pick the
        # weaker path wholesale": neither path_a nor path_b alone equals
        # the combined result.
        self.assertNotEqual(expected, path_a)
        self.assertNotEqual(expected, path_b)
        self.assertEqual(result["target"], "ADyA8hdefvWN2dbGGWFotbzWxrAvLW83WG6QCVXvJKqw")
        self.assertEqual(result["label"], "PumpSwap (and pump.fun bonding curve)")
        # Not computed for this target -- flat per the docstring/return dict.
        self.assertEqual(result["oracleAuthorityScore"], 100)
        self.assertEqual(
            result["_signers"],
            {f"upgrade_signer_{i}" for i in range(4)} | {f"admin_signer_{i}" for i in range(4)})

    def test_real_world_symmetric_shape_matches_documented_upper_bound_composite(self):
        # Regression pin on this scorer's own headline claim (its
        # docstring): BOTH full-power paths are a genuinely different
        # multisig but the SAME 3-of-4, no-delay shape, so the combined
        # score equals either path alone rather than being pulled down
        # further -- composite 43, exactly the docstring's own cited
        # upper bound.
        self._mock_upgrade_matched(threshold=3, n_voters=4, delay_s=0)
        self._mock_admin_matched(threshold=3, n_voters=4, delay_s=0)

        result = solana.score_pumpswap("unused-url")

        same_shape = solana._score_full_power_path("squads_v4", threshold=3, voters=4, delay_s=0)
        self.assertEqual(
            (result["adminKeyScore"], result["multisigScore"], result["timelockScore"]), same_shape)
        self.assertEqual(result["compositeScore"], 43)
        # Two DIFFERENT multisigs of the same shape -> 8 distinct signers,
        # not a deduplicated/reused set of 4.
        self.assertEqual(len(result["_signers"]), 8)

    def test_renounced_upgrade_authority_defers_entirely_to_the_admin_path(self):
        self._mock_upgrade_renounced()
        self._mock_admin_matched(threshold=3, n_voters=4, delay_s=0)

        result = solana.score_pumpswap("unused-url")

        path_b = solana._score_full_power_path("squads_v4", threshold=3, voters=4, delay_s=0)
        self.assertEqual(
            (result["adminKeyScore"], result["multisigScore"], result["timelockScore"]), path_b)
        self.assertTrue(any("renounced" in n for n in result["notes"]))
        self.assertFalse(any("MISMATCH" in n for n in result["notes"]))
        # Renounced path contributes no signers of its own.
        self.assertEqual(result["_signers"], {f"admin_signer_{i}" for i in range(4)})

    def test_program_upgrade_vault_mismatch_degrades_that_path_to_the_unresolved_floor(self):
        self._mock_upgrade_mismatched()
        self._mock_admin_matched(threshold=3, n_voters=4, delay_s=0)

        result = solana.score_pumpswap("unused-url")

        # _score_full_power_path("squads_v4", threshold=3, voters=4,
        # delay_s=0) scores strictly higher on every component than the
        # (20, 20, 0) unresolved floor, so the mismatched upgrade path
        # dominates the combined min() even though the admin path DID
        # resolve.
        self.assertEqual(
            (result["adminKeyScore"], result["multisigScore"], result["timelockScore"]), (20, 20, 0))
        self.assertTrue(any("MISMATCH" in n for n in result["notes"]))
        # The admin path still resolved and still contributes its signers,
        # even though it lost the min() on every score component.
        self.assertEqual(result["_signers"], {f"admin_signer_{i}" for i in range(4)})

    def test_global_config_admin_vault_mismatch_degrades_that_path_to_the_unresolved_floor(self):
        # The mirror image of the previous test, from the OTHER path --
        # score_pumpswap wires _resolve_squads_v4 up twice, independently;
        # this confirms the second call site degrades correctly too, not
        # just the first.
        self._mock_upgrade_matched(threshold=3, n_voters=4, delay_s=0)
        self._mock_admin_mismatched()

        result = solana.score_pumpswap("unused-url")

        self.assertEqual(
            (result["adminKeyScore"], result["multisigScore"], result["timelockScore"]), (20, 20, 0))
        self.assertTrue(any("GlobalConfig.admin" in n and "MISMATCH" in n for n in result["notes"]))
        self.assertEqual(result["_signers"], {f"upgrade_signer_{i}" for i in range(4)})

    def test_global_config_admin_none_is_not_treated_as_renounced(self):
        # Asymmetry regression test: score_pumpswap passes
        # none_means_renounced=True ONLY on the program-upgrade
        # _resolve_squads_v4 call (a real loader-v3 "Option::None" concept)
        # -- NOT on the GlobalConfig.admin call. A None admin here must
        # still degrade via the ordinary MISMATCH path, never be credited
        # as the safest (100/100/100) renounced band.
        self._mock_upgrade_matched(threshold=3, n_voters=4, delay_s=0)
        self._mock_admin_none()

        result = solana.score_pumpswap("unused-url")

        self.assertEqual(
            (result["adminKeyScore"], result["multisigScore"], result["timelockScore"]), (20, 20, 0))
        gc_notes = [n for n in result["notes"] if n.startswith("GlobalConfig.admin")]
        self.assertTrue(gc_notes)
        self.assertTrue(all("renounced" not in n for n in gc_notes))
        self.assertTrue(any("MISMATCH" in n for n in gc_notes))

    def test_both_paths_mismatched_degrades_fully_with_no_signers(self):
        self._mock_upgrade_mismatched()
        self._mock_admin_mismatched()

        result = solana.score_pumpswap("unused-url")

        self.assertEqual(
            (result["adminKeyScore"], result["multisigScore"], result["timelockScore"]), (20, 20, 0))
        self.assertEqual(result["compositeScore"], solana._composite(20, 20, 0))
        self.assertEqual(result["_signers"], set())
        # Both paths independently record their own MISMATCH note.
        self.assertEqual(sum(1 for n in result["notes"] if "MISMATCH" in n), 2)

    def test_squads_v4_with_nondefault_config_authority_raises(self):
        # _resolve_squads_v4 refuses to guess a score for the "Squads v4
        # controlled" band (METHODOLOGY.md 6.1) rather than silently
        # mis-scoring it -- score_pumpswap does not catch that abort, so it
        # must propagate all the way out, for either of its two call sites.
        # Exercised here via the program-upgrade path.
        solana.sol_read.read_program = lambda url, pk: {"upgrade_authority": UPGRADE_VAULT0}
        self._squads_by_ms[UPGRADE_MS] = {
            "multisig": UPGRADE_MS, "owner": solana.SQUADS_V4_PROGRAM,
            "config_authority": "SomeNonDefaultConfigAuthority1111111111111",
            "threshold": 3, "time_lock_s": 0, "members": 4,
            "member_list": [{"key": f"upgrade_signer_{i}", "mask": 7} for i in range(4)],
        }
        with self.assertRaises(NotImplementedError):
            solana.score_pumpswap("unused-url")


if __name__ == "__main__":
    unittest.main()
