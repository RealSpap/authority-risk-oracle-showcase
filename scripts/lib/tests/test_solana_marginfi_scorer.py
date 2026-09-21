"""
Unit tests for `chains/solana/scorers.py::score_marginfi` (marginfi main
lending group, added 2026-09-18/19).

This is an ORCHESTRATION test, not a byte-decode test: `score_marginfi`'s
own two full-power paths (program-upgrade authority, `MarginfiGroup.admin`)
are exercised end to end by monkeypatching the `sol_read.read_program` /
`sol_read.read_marginfi_group` / `sol_read.read_squads` primitives it calls
-- same convention as `test_drift_protocol.py` and
`test_switchboard_on_demand.py` (patch the module-level `sol_read`
reference `scorers.py` itself imported, accessible here as
`solana.sol_read`, not a separately-loaded module object).

`sol_read.read_marginfi_group` already has dedicated byte-level decode
coverage in `test_solana_defi_config_admins.py` (per this function's own
task notes), so it is faked here at a high level (a plain dict return
matching its documented `{"group": ..., "admin": ...}` shape) rather than
re-built from new byte fixtures. `_score_full_power_path`'s own formula
correctness (the "squads_v4"/"none" bands) is already tested elsewhere in
this repo (`test_drift_protocol.py`, `test_switchboard_on_demand.py`,
`test_solend_governance.py`) and is NOT re-tested here -- these tests only
check that `score_marginfi` calls it with the right arguments, combines
the two paths' outputs with `min()` per METHODOLOGY.md 6.2, and degrades/
short-circuits on the right conditions.

One thing IS computed for real rather than faked: `sol_read.
read_squads_vault` is a pure, deterministic, offline PDA derivation (no
RPC call at all -- see its own docstring) of the Squads v4 vault-0 address
for a given multisig account. Rather than guessing or hardcoding a vault
address, these tests call the REAL function once at import time against
the two multisig constants `score_marginfi` itself hardcodes
(`UPGRADE_MS`, `ADMIN_MS`) to get the genuine expected vault addresses --
the same two addresses already documented in `score_marginfi`'s own
docstring (`J3oBkTkDXU3TcAggJEa3YeBZE5om5yNAdTtLVNXFD47` and
`CYXEgwbPHu2f9cY3mcUkinzDoDcsSan7myh1uBvYRbEw`), confirmed to match below.
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


solana = _load_module("aro_test_solana_scorers_marginfi", "chains/solana/scorers.py")

MARGINFI_PROGRAM = "MFv2hWf31Z9kbCa1snEPYctwafyhdvnV7FZnsebVacA"
MAIN_GROUP = "4qp6Fx6tnZkY5Wropq9wUYgtFxXKwE6viZxFHg3rdAG8"
UPGRADE_MS = "7FCPipJWVbPbdHymVt1gJYwKciakkJz5GahdQySemvHk"
ADMIN_MS = "74QKjjvoSrq2cGqFzzQNN8ox3gomYS1mBwcLsbiYaH8j"

# Real vault-0 PDAs of the two hardcoded multisig constants, computed via
# the REAL sol_read.read_squads_vault (pure offline derivation, no network)
# rather than guessed -- these are the values `score_marginfi` requires an
# "authority" to exactly equal for that path to resolve as MATCHED.
UPGRADE_VAULT = solana.sol_read.read_squads_vault(UPGRADE_MS, 0)["vault"]
ADMIN_VAULT = solana.sol_read.read_squads_vault(ADMIN_MS, 0)["vault"]

# Docstring-documented, so cross-checked against score_marginfi's own text.
assert UPGRADE_VAULT == "J3oBkTkDXU3TcAggJEa3YeBZE5om5yNAdTtLVNXFD47"
assert ADMIN_VAULT == "CYXEgwbPHu2f9cY3mcUkinzDoDcsSan7myh1uBvYRbEw"

# A syntactically-unrelated pubkey-shaped string that is NOT either derived
# vault -- used to exercise the mismatch/degrade branch.
UNRELATED_PUBKEY = "UnreLated1111111111111111111111111111111X"


def _squads(threshold, member_masks, time_lock_s=0):
    """A fake sol_read.read_squads() return, matching its documented shape
    ({"multisig", "owner", "config_authority", "threshold", "time_lock_s",
    "members", "member_list"}) with `len(member_masks)` members named
    member0.. and the given permission masks (bit 1=Initiate, 2=Vote,
    4=Execute per METHODOLOGY.md 3.4)."""
    return {
        "multisig": "unused-ms", "owner": solana.SQUADS_V4_PROGRAM,
        "config_authority": solana.SYSTEM_PROGRAM_DEFAULT,
        "threshold": threshold, "time_lock_s": time_lock_s,
        "members": len(member_masks),
        "member_list": [{"key": f"member{i}", "mask": m} for i, m in enumerate(member_masks)],
    }


class ScoreMarginfiTestCase(unittest.TestCase):
    """Shared monkeypatch/restore scaffolding for the sol_read primitives
    `score_marginfi` calls -- patches `scorers.py`'s own module-level
    `sol_read` reference (`solana.sol_read`), the same convention already
    used by `test_drift_protocol.py`/`test_switchboard_on_demand.py`."""

    def setUp(self):
        self._orig_read_program = solana.sol_read.read_program
        self._orig_read_marginfi_group = solana.sol_read.read_marginfi_group
        self._orig_read_squads = solana.sol_read.read_squads

    def tearDown(self):
        solana.sol_read.read_program = self._orig_read_program
        solana.sol_read.read_marginfi_group = self._orig_read_marginfi_group
        solana.sol_read.read_squads = self._orig_read_squads

    def _patch(self, upgrade_authority, group_admin, squads_by_pk):
        def fake_read_program(url, pk):
            self.assertEqual(pk, MARGINFI_PROGRAM)
            return {"program": pk, "upgrade_authority": upgrade_authority}

        def fake_read_marginfi_group(url, pk):
            self.assertEqual(pk, MAIN_GROUP)
            return {"group": pk, "admin": group_admin}

        def fake_read_squads(url, pk):
            if pk in squads_by_pk:
                return squads_by_pk[pk]
            raise AssertionError(f"unexpected read_squads call for {pk}")

        solana.sol_read.read_program = fake_read_program
        solana.sol_read.read_marginfi_group = fake_read_marginfi_group
        solana.sol_read.read_squads = fake_read_squads


class TestBothPathsResolveAndCombineViaMin(ScoreMarginfiTestCase):
    """The headline orchestration claim: two INDEPENDENTLY-resolved Squads
    v4 paths, combined per-dimension with min() (METHODOLOGY.md 6.2) --
    using the exact 7-of-15 / 5-of-17(15 voters) numbers score_marginfi's
    own docstring documents, including the "upgrade voters are a subset of
    admin voters" caveat it describes."""

    def test_combined_scores_are_elementwise_min_of_both_paths(self):
        upgrade_sq = _squads(threshold=7, member_masks=[6] * 15)  # 7-of-15, all 15 have Vote
        admin_sq = _squads(threshold=5, member_masks=[6] * 15 + [0, 1])  # 5-of-17, same 15 voters + 2 non-voters
        self._patch(
            upgrade_authority=UPGRADE_VAULT, group_admin=ADMIN_VAULT,
            squads_by_pk={UPGRADE_MS: upgrade_sq, ADMIN_MS: admin_sq},
        )

        result = solana.score_marginfi("unused-url")

        expected_a = solana._score_full_power_path("squads_v4", threshold=7, voters=15, delay_s=0)
        expected_b = solana._score_full_power_path("squads_v4", threshold=5, voters=15, delay_s=0)
        expected = tuple(min(a, b) for a, b in zip(expected_a, expected_b))
        self.assertEqual(
            (result["adminKeyScore"], result["multisigScore"], result["timelockScore"]), expected)
        # The two paths must actually differ (17 vs 15 total members changes
        # the multisig formula's denominator) for this to be a meaningful
        # min(), not a coincidence where both paths already agreed.
        self.assertNotEqual(expected_a, expected_b)

        self.assertEqual(result["target"], MAIN_GROUP)
        self.assertEqual(result["label"], "marginfi (main lending group)")
        self.assertEqual(result["oracleAuthorityScore"], 100)
        self.assertEqual(result["compositeScore"], solana._composite(*expected))
        self.assertTrue(any("combined (min over both full-power paths" in n for n in result["notes"]))

    def test_subset_caveat_note_fires_when_upgrade_voters_subset_of_admin_voters(self):
        upgrade_sq = _squads(threshold=7, member_masks=[6] * 15)
        admin_sq = _squads(threshold=5, member_masks=[6] * 15 + [0, 1])
        self._patch(
            upgrade_authority=UPGRADE_VAULT, group_admin=ADMIN_VAULT,
            squads_by_pk={UPGRADE_MS: upgrade_sq, ADMIN_MS: admin_sq},
        )
        result = solana.score_marginfi("unused-url")
        self.assertTrue(any(n.startswith("caveat:") for n in result["notes"]))


class TestNoSubsetCaveatWhenVotersAreIndependent(ScoreMarginfiTestCase):
    def test_no_caveat_note_when_upgrade_voters_are_not_a_subset_of_admin_voters(self):
        # Disjoint membership between the two multisigs -- no subset relation.
        upgrade_sq = {
            "multisig": UPGRADE_MS, "owner": solana.SQUADS_V4_PROGRAM,
            "config_authority": solana.SYSTEM_PROGRAM_DEFAULT,
            "threshold": 2, "time_lock_s": 0, "members": 3,
            "member_list": [{"key": f"upgrade_member{i}", "mask": 6} for i in range(3)],
        }
        admin_sq = {
            "multisig": ADMIN_MS, "owner": solana.SQUADS_V4_PROGRAM,
            "config_authority": solana.SYSTEM_PROGRAM_DEFAULT,
            "threshold": 2, "time_lock_s": 0, "members": 3,
            "member_list": [{"key": f"admin_member{i}", "mask": 6} for i in range(3)],
        }
        self._patch(
            upgrade_authority=UPGRADE_VAULT, group_admin=ADMIN_VAULT,
            squads_by_pk={UPGRADE_MS: upgrade_sq, ADMIN_MS: admin_sq},
        )
        result = solana.score_marginfi("unused-url")
        self.assertFalse(any(n.startswith("caveat:") for n in result["notes"]))

    def test_signers_is_the_union_of_both_resolved_paths_member_keys(self):
        upgrade_sq = {
            "multisig": UPGRADE_MS, "owner": solana.SQUADS_V4_PROGRAM,
            "config_authority": solana.SYSTEM_PROGRAM_DEFAULT,
            "threshold": 2, "time_lock_s": 0, "members": 3,
            "member_list": [{"key": f"upgrade_member{i}", "mask": 6} for i in range(3)],
        }
        admin_sq = {
            "multisig": ADMIN_MS, "owner": solana.SQUADS_V4_PROGRAM,
            "config_authority": solana.SYSTEM_PROGRAM_DEFAULT,
            "threshold": 2, "time_lock_s": 0, "members": 3,
            "member_list": [{"key": f"admin_member{i}", "mask": 6} for i in range(3)],
        }
        self._patch(
            upgrade_authority=UPGRADE_VAULT, group_admin=ADMIN_VAULT,
            squads_by_pk={UPGRADE_MS: upgrade_sq, ADMIN_MS: admin_sq},
        )
        result = solana.score_marginfi("unused-url")
        expected_signers = {f"upgrade_member{i}" for i in range(3)} | {f"admin_member{i}" for i in range(3)}
        self.assertEqual(result["_signers"], expected_signers)


class TestProgramUpgradeAuthorityRenounced(ScoreMarginfiTestCase):
    """program.upgrade_authority is None: score_marginfi passes
    `none_means_renounced=True` on this path only, so this must resolve to
    the safest (100, 100, 100) band -- not the 20/20/0 degrade band -- and
    the combined score must then be driven ENTIRELY by the
    MarginfiGroup.admin path via min() (min(100, x) == x)."""

    def test_renounced_upgrade_path_is_dominated_by_the_admin_path(self):
        admin_sq = _squads(threshold=3, member_masks=[6, 6, 6, 6, 0], time_lock_s=3600)
        self._patch(
            upgrade_authority=None, group_admin=ADMIN_VAULT,
            squads_by_pk={ADMIN_MS: admin_sq},
        )
        result = solana.score_marginfi("unused-url")
        expected_b = solana._score_full_power_path("squads_v4", threshold=3, voters=4, delay_s=3600)
        self.assertEqual(
            (result["adminKeyScore"], result["multisigScore"], result["timelockScore"]), expected_b)
        self.assertTrue(any("renounced" in n for n in result["notes"]))
        self.assertFalse(any("MISMATCH" in n for n in result["notes"]))
        # RENOUNCED is neither None nor a resolved dict, so the "both paths
        # resolved" subset-caveat branch must not fire here.
        self.assertFalse(any(n.startswith("caveat:") for n in result["notes"]))


class TestProgramUpgradePathMismatchDegrades(ScoreMarginfiTestCase):
    """A non-None upgrade authority that does NOT match the offline-
    re-derived vault-0 of UPGRADE_MS must degrade to the fixed (20, 20, 0)
    band on that path, per `score_marginfi`'s own `if upgrade_sq is None`
    branch -- never silently trusted."""

    def test_upgrade_mismatch_degrades_and_admin_path_is_ignored_by_min(self):
        # A strong admin path (large threshold, long delay) so this test
        # actually exercises min() picking the weaker (20, 20, 0) path,
        # rather than coincidentally agreeing with it.
        admin_sq = _squads(threshold=8, member_masks=[6] * 10, time_lock_s=200_000)
        self._patch(
            upgrade_authority=UNRELATED_PUBKEY, group_admin=ADMIN_VAULT,
            squads_by_pk={ADMIN_MS: admin_sq},
        )
        result = solana.score_marginfi("unused-url")
        expected_b = solana._score_full_power_path("squads_v4", threshold=8, voters=10, delay_s=200_000)
        # Sanity: the admin path really is stronger on every dimension, so a
        # correct min() must land on the degraded (20, 20, 0) upgrade path.
        self.assertTrue(all(b > d for b, d in zip(expected_b, (20, 20, 0))))
        self.assertEqual(
            (result["adminKeyScore"], result["multisigScore"], result["timelockScore"]), (20, 20, 0))
        self.assertTrue(any("program upgrade" in n and "MISMATCH" in n for n in result["notes"]))


class TestMarginfiGroupAdminPathMismatchDegrades(ScoreMarginfiTestCase):
    """Symmetric case on the second path: a MarginfiGroup.admin that does
    NOT match the offline-re-derived vault-0 of ADMIN_MS must degrade to
    (20, 20, 0) via `score_marginfi`'s own `if admin_sq is None` branch,
    even though the program-upgrade path resolves cleanly and strongly."""

    def test_admin_mismatch_degrades_and_upgrade_path_is_ignored_by_min(self):
        upgrade_sq = _squads(threshold=8, member_masks=[6] * 10, time_lock_s=200_000)
        self._patch(
            upgrade_authority=UPGRADE_VAULT, group_admin=UNRELATED_PUBKEY,
            squads_by_pk={UPGRADE_MS: upgrade_sq},
        )
        result = solana.score_marginfi("unused-url")
        self.assertEqual(
            (result["adminKeyScore"], result["multisigScore"], result["timelockScore"]), (20, 20, 0))
        self.assertTrue(any("MarginfiGroup.admin" in n and "MISMATCH" in n for n in result["notes"]))


class TestMarginfiGroupAdminNoneIsNotTreatedAsRenounced(ScoreMarginfiTestCase):
    """Asymmetry check: unlike the program-upgrade path, `score_marginfi`
    calls `_resolve_squads_v4` for the MarginfiGroup.admin path WITHOUT
    `none_means_renounced=True`. A None admin must therefore fall through
    to the ordinary mismatch/degrade band (20, 20, 0) with a MISMATCH note
    -- NOT be treated as the safe renounced band -- since a None
    `MarginfiGroup.admin` was never documented as a genuine on-chain
    Option::None the way a renounced program upgrade authority is."""

    def test_none_group_admin_degrades_instead_of_being_treated_as_renounced(self):
        upgrade_sq = _squads(threshold=7, member_masks=[6] * 15)
        self._patch(
            upgrade_authority=UPGRADE_VAULT, group_admin=None,
            squads_by_pk={UPGRADE_MS: upgrade_sq},
        )
        result = solana.score_marginfi("unused-url")
        expected_a = solana._score_full_power_path("squads_v4", threshold=7, voters=15, delay_s=0)
        expected = tuple(min(a, b) for a, b in zip(expected_a, (20, 20, 0)))
        self.assertEqual(
            (result["adminKeyScore"], result["multisigScore"], result["timelockScore"]), expected)
        self.assertTrue(any("MarginfiGroup.admin" in n and "MISMATCH" in n for n in result["notes"]))
        self.assertFalse(any("MarginfiGroup.admin" in n and "renounced" in n for n in result["notes"]))


if __name__ == "__main__":
    unittest.main()
