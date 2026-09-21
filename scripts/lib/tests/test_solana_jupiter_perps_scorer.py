"""
Unit tests for `chains/solana/scorers.py::score_jupiter_perps` (Jupiter
Perpetual Exchange).

Scope: this scorer's OWN orchestration -- how its two full-power authority
paths (the program's own upgrade authority via Squads v4, and
`Perpetuals.admin` via Squads v3) each degrade to a floor on a vault-PDA
mismatch, short-circuit on a renounced upgrade authority, and combine via a
per-COMPONENT min() (METHODOLOGY.md 6.2) rather than one path winning
outright -- plus the one abort condition reachable through this target
(`_resolve_squads_v4`'s "config_authority is set" NotImplementedError).
`_score_full_power_path`'s own squads_v4/squads_v3 formula curves are
already covered elsewhere in this repo (test_drift_protocol.py,
test_switchboard_on_demand.py, test_solend_governance.py) and are not
re-verified here -- they are only *called*, the same way score_jupiter_perps
itself calls them, to compute what this scorer's own combine logic should
produce from realistic path results.

`sol_read.read_squads_vault` (the offline Squads v4 vault-0 PDA derivation
`_resolve_squads_v4` uses) and the seed formula `read_squadsv3` uses for its
own `authority_N` PDA are NOT monkeypatched -- both are pure, no-RPC
computations, so this file computes the REAL vault-0 PDA of UPGRADE_MS and
the real authority-index-1 PDA of ADMIN_MS below (the exact constants
`score_jupiter_perps` hardcodes) and uses them as fixture data, the same
"real derived PDA, not a mocked derivation" convention
test_switchboard_on_demand.py uses for its QUEUE_AUTHORITY fixture. The
first of the two (`5myNNmEmPm3UAnJ2ggLEpnTFb9t9Gk8369wKw6n3uAKx`) matches
the literal `score_jupiter_perps` docstring already quotes for that vault,
confirming this isn't a coincidental match.

Only the network-touching primitives this scorer actually calls
(`read_program`, `read_squads`, `read_jupiter_perpetuals`, `read_squadsv3`)
are faked, monkeypatched directly on `scorers.py`'s own module-level
`sol_read` reference -- the same convention as test_drift_protocol.py /
test_switchboard_on_demand.py.
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


solana = _load_module("aro_test_solana_scorers_jupiter_perps", "chains/solana/scorers.py")

# score_jupiter_perps's own hardcoded multisig constants.
UPGRADE_MS = "AxkJ8oH5aDu4ZRWfsujPtxdb6Vhq4gDehpoReBgrUUSm"
ADMIN_MS = "7ZyDFzet6sKgZLN4D89JLfo7chu2n7nYdkFt5RCFk8Sf"

# Real, offline-derived PDAs for the two constants above -- computed via the
# SAME pure (no-RPC) functions/seed formulas _resolve_squads_v4 and
# read_squadsv3 themselves use, left un-mocked in this file.
UPGRADE_VAULT0 = solana.sol_read.read_squads_vault(UPGRADE_MS, 0)["vault"]
ADMIN_AUTHORITY_1 = solana.sol_read.find_program_address(
    [b"squad", solana.sol_read.b58dec(ADMIN_MS), (1).to_bytes(4, "little"), b"authority"],
    solana.SQUADS_V3_PROGRAM,
)[0]

WRONG_UPGRADE_AUTHORITY = "WrongUpgradeAuthorityNotTheRealVault0PDA111"
WRONG_PERP_ADMIN = "WrongPerpAdminNotTheRealAuthority1PDA111111"


def _fail_if_called(url, pk):
    raise AssertionError(f"sol_read.read_squads should not be reached for {pk} on this code path")


class TestScoreJupiterPerps(unittest.TestCase):
    def setUp(self):
        self._orig_read_program = solana.sol_read.read_program
        self._orig_read_squads = solana.sol_read.read_squads
        self._orig_read_jupiter_perpetuals = solana.sol_read.read_jupiter_perpetuals
        self._orig_read_squadsv3 = solana.sol_read.read_squadsv3

    def tearDown(self):
        solana.sol_read.read_program = self._orig_read_program
        solana.sol_read.read_squads = self._orig_read_squads
        solana.sol_read.read_jupiter_perpetuals = self._orig_read_jupiter_perpetuals
        solana.sol_read.read_squadsv3 = self._orig_read_squadsv3

    # -- path A (program upgrade authority, Squads v4) fixtures --------

    def _mock_upgrade_matched(self, threshold=4, n_voters=8, delay_s=86400):
        solana.sol_read.read_program = lambda url, pk: {"upgrade_authority": UPGRADE_VAULT0}
        solana.sol_read.read_squads = lambda url, pk: {
            "multisig": pk, "owner": solana.SQUADS_V4_PROGRAM,
            "config_authority": solana.SYSTEM_PROGRAM_DEFAULT,
            "threshold": threshold, "time_lock_s": delay_s, "members": n_voters,
            "member_list": [{"key": f"upgrade_signer_{i}", "mask": 7} for i in range(n_voters)],
        }

    def _mock_upgrade_mismatched(self):
        solana.sol_read.read_program = lambda url, pk: {"upgrade_authority": WRONG_UPGRADE_AUTHORITY}
        solana.sol_read.read_squads = _fail_if_called  # a mismatch must degrade without ever reading the multisig

    def _mock_upgrade_renounced(self):
        solana.sol_read.read_program = lambda url, pk: {"upgrade_authority": None}
        solana.sol_read.read_squads = _fail_if_called  # renounced short-circuits before any multisig read

    # -- path B (Perpetuals.admin, Squads v3) fixtures ------------------

    def _mock_admin_matched(self, threshold=4, n_keys=7):
        solana.sol_read.read_jupiter_perpetuals = lambda url, pk: {"perpetuals": pk, "admin": ADMIN_AUTHORITY_1}
        solana.sol_read.read_squadsv3 = lambda url, pk, authority_index=None: {
            "ms": pk, "owner": solana.SQUADS_V3_PROGRAM, "threshold": threshold,
            "authority_index": authority_index, "n_keys": n_keys,
            "keys": [f"admin_signer_{i}" for i in range(n_keys)],
            f"authority_{authority_index}": ADMIN_AUTHORITY_1,
        }

    def _mock_admin_mismatched(self):
        solana.sol_read.read_jupiter_perpetuals = lambda url, pk: {"perpetuals": pk, "admin": WRONG_PERP_ADMIN}
        solana.sol_read.read_squadsv3 = lambda url, pk, authority_index=None: {
            "ms": pk, "owner": solana.SQUADS_V3_PROGRAM, "threshold": 4,
            "authority_index": authority_index, "n_keys": 7,
            "keys": [f"admin_signer_{i}" for i in range(7)],
            f"authority_{authority_index}": ADMIN_AUTHORITY_1,  # real PDA, but live admin (WRONG_PERP_ADMIN) disagrees
        }

    # ---------------------------------------------------------------

    def test_both_paths_resolved_combines_via_componentwise_min_across_paths(self):
        self._mock_upgrade_matched(threshold=4, n_voters=8, delay_s=86400)
        self._mock_admin_matched(threshold=4, n_keys=7)

        result = solana.score_jupiter_perps("unused-url")

        path_a = solana._score_full_power_path("squads_v4", threshold=4, voters=8, delay_s=86400)
        path_b = solana._score_full_power_path("squads_v3", threshold=4, voters=7)
        expected = tuple(min(path_a[i], path_b[i]) for i in range(3))

        self.assertEqual(
            (result["adminKeyScore"], result["multisigScore"], result["timelockScore"]), expected)
        self.assertEqual(result["compositeScore"], solana._composite(*expected))
        # The docstring's headline claim: path B (Squads v3, no time-lock
        # field at all) has zero delay while path A has a real 24h delay --
        # the COMBINED timelock must come from B, not A, i.e. the 24h
        # upgrade delay's protection is fully bypassed by the admin path.
        self.assertLess(path_b[2], path_a[2])
        self.assertEqual(expected[2], 0)
        self.assertEqual(result["target"], "H4ND9aYttUVLFmNypZqLjZ52FYiGvdEB45GmwNoKEjTj")
        self.assertEqual(result["label"], "Jupiter Perpetual Exchange")
        # Not scored per the docstring's own "not chased further" note.
        self.assertEqual(result["oracleAuthorityScore"], 100)
        # _signers is a UNION of both resolved paths' members, not just the
        # weaker/winning one -- used elsewhere in this project for
        # cross-target signer-overlap analysis.
        self.assertEqual(
            result["_signers"],
            {f"upgrade_signer_{i}" for i in range(8)} | {f"admin_signer_{i}" for i in range(7)})

    def test_renounced_upgrade_authority_defers_entirely_to_the_admin_path(self):
        self._mock_upgrade_renounced()
        self._mock_admin_matched(threshold=4, n_keys=7)

        result = solana.score_jupiter_perps("unused-url")

        path_b = solana._score_full_power_path("squads_v3", threshold=4, voters=7)
        self.assertEqual(
            (result["adminKeyScore"], result["multisigScore"], result["timelockScore"]), path_b)
        self.assertTrue(any("renounced" in n for n in result["notes"]))
        self.assertFalse(any("MISMATCH" in n for n in result["notes"]))
        # Renounced path contributes no signers of its own.
        self.assertEqual(result["_signers"], {f"admin_signer_{i}" for i in range(7)})

    def test_program_upgrade_vault_mismatch_degrades_that_path_to_the_unresolved_floor(self):
        self._mock_upgrade_mismatched()
        self._mock_admin_matched(threshold=4, n_keys=7)

        result = solana.score_jupiter_perps("unused-url")

        # _score_full_power_path("squads_v3", threshold=4, voters=7) scores
        # strictly higher on every component than the (20, 20, 0)
        # unresolved floor, so the mismatched upgrade path dominates the
        # combined min() here even though the admin path DID resolve.
        self.assertEqual(
            (result["adminKeyScore"], result["multisigScore"], result["timelockScore"]), (20, 20, 0))
        self.assertTrue(any("MISMATCH" in n for n in result["notes"]))
        # The admin path still resolved and still contributes its signers,
        # even though it lost the min() on every score component.
        self.assertEqual(result["_signers"], {f"admin_signer_{i}" for i in range(7)})

    def test_both_paths_mismatched_degrades_fully_with_no_signers(self):
        self._mock_upgrade_mismatched()
        self._mock_admin_mismatched()

        result = solana.score_jupiter_perps("unused-url")

        self.assertEqual(
            (result["adminKeyScore"], result["multisigScore"], result["timelockScore"]), (20, 20, 0))
        self.assertEqual(result["compositeScore"], solana._composite(20, 20, 0))
        self.assertEqual(result["_signers"], set())
        # Both paths independently record their own MISMATCH note.
        self.assertEqual(sum(1 for n in result["notes"] if "MISMATCH" in n), 2)

    def test_program_upgrade_squads_v4_with_nondefault_config_authority_raises(self):
        # _resolve_squads_v4 refuses to guess a score for the "Squads v4
        # controlled" band (METHODOLOGY.md 6.1) rather than silently
        # mis-scoring it -- this scorer does not catch that abort, so it
        # must propagate all the way out of score_jupiter_perps.
        solana.sol_read.read_program = lambda url, pk: {"upgrade_authority": UPGRADE_VAULT0}
        solana.sol_read.read_squads = lambda url, pk: {
            "multisig": pk, "owner": solana.SQUADS_V4_PROGRAM,
            "config_authority": "SomeNonDefaultConfigAuthority1111111111111",
            "threshold": 4, "time_lock_s": 86400, "members": 8,
            "member_list": [{"key": f"upgrade_signer_{i}", "mask": 7} for i in range(8)],
        }
        with self.assertRaises(NotImplementedError):
            solana.score_jupiter_perps("unused-url")


if __name__ == "__main__":
    unittest.main()
