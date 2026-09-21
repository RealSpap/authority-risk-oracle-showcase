"""
Unit tests for `chains/solana/scorers.py::score_jupiter_lend` (Jupiter Lend
Liquidity program, added 2026-09-19).

This is an ORCHESTRATION test, not a byte-decode test: `score_jupiter_lend`'s
own two full-power paths (program-upgrade authority, `Liquidity.authority`)
are exercised end to end by monkeypatching the `sol_read.read_program` /
`sol_read.read_jupiter_lend_liquidity` / `sol_read.read_squads` primitives it
calls -- same convention as `test_drift_protocol.py`,
`test_switchboard_on_demand.py` and `test_solana_marginfi_scorer.py` (patch
the module-level `sol_read` reference `scorers.py` itself imported,
accessible here as `solana.sol_read`, not a separately-loaded module
object).

`sol_read.read_jupiter_lend_liquidity` already has dedicated byte-level
decode coverage in `test_solana_defi_config_admins.py` (per this function's
own task notes), so it is faked here at a high level (a plain dict return
matching its documented `{"liquidity": ..., "authority": ...}` shape)
rather than re-built from new byte fixtures. `_score_full_power_path`'s own
formula correctness (the "squads_v4"/"none" bands) and `_resolve_squads_v4`'s
own internal PDA-match/config_authority logic are already tested elsewhere
in this repo (`test_drift_protocol.py`, `test_switchboard_on_demand.py`,
`test_solend_governance.py`, `test_solana_marginfi_scorer.py`) and are NOT
re-tested here -- these tests only check that `score_jupiter_lend` calls
its primitives with the right arguments, combines the two paths' outputs
with `min()` per METHODOLOGY.md 6.2, and degrades/short-circuits on the
right conditions.

Unlike `score_marginfi`, `score_jupiter_lend` has no "subset of voters"
caveat logic in its own body (confirmed by reading its full source), so no
caveat-note tests are included here -- there is no such branch to exercise.

One thing IS computed for real rather than faked: `sol_read.
read_squads_vault` is a pure, deterministic, offline PDA derivation (no RPC
call at all -- see its own docstring) of the Squads v4 vault-0 address for
a given multisig account. Rather than guessing or hardcoding a vault
address, these tests call the REAL function once at import time against the
two multisig constants `score_jupiter_lend` itself hardcodes (`UPGRADE_MS`,
`ADMIN_MS`) to get the genuine expected vault addresses -- the same two
addresses already documented in `score_jupiter_lend`'s own docstring
(`4MsgBB5VPoTrUSp5XnfbViV386C1UnsTdifLBw33ZMSJ` and
`HqPrpa4ESBDnRHRWaiYtjv4xe93wvCS9NNZtDwR89cVa`), confirmed to match below.
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


solana = _load_module("aro_test_solana_scorers_jupiter_lend", "chains/solana/scorers.py")

LIQUIDITY_PROGRAM = "jupeiUmn818Jg1ekPURTpr4mFo29p46vygyykFJ3wZC"
LIQUIDITY_ACCOUNT = "7s1da8DduuBFqGra5bJBjpnvL5E9mGzCuMk1Qkh4or2Z"
UPGRADE_MS = "J3mJ3wz6xkVUk3T8qHnuAYNxsRH3ixHsryYNZAU2vG8P"
ADMIN_MS = "5Y93cxqp8rGtjDhxGkehewfhFdxLkrCfPDWookCGeASF"

# Real vault-0 PDAs of the two hardcoded multisig constants, computed via
# the REAL sol_read.read_squads_vault (pure offline derivation, no network)
# rather than guessed -- these are the values `score_jupiter_lend` requires
# an "authority" to exactly equal for that path to resolve as MATCHED.
UPGRADE_VAULT = solana.sol_read.read_squads_vault(UPGRADE_MS, 0)["vault"]
ADMIN_VAULT = solana.sol_read.read_squads_vault(ADMIN_MS, 0)["vault"]

# Docstring-documented, so cross-checked against score_jupiter_lend's own text.
assert UPGRADE_VAULT == "4MsgBB5VPoTrUSp5XnfbViV386C1UnsTdifLBw33ZMSJ"
assert ADMIN_VAULT == "HqPrpa4ESBDnRHRWaiYtjv4xe93wvCS9NNZtDwR89cVa"

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


class ScoreJupiterLendTestCase(unittest.TestCase):
    """Shared monkeypatch/restore scaffolding for the sol_read primitives
    `score_jupiter_lend` calls -- patches `scorers.py`'s own module-level
    `sol_read` reference (`solana.sol_read`), the same convention already
    used by `test_drift_protocol.py`/`test_switchboard_on_demand.py`/
    `test_solana_marginfi_scorer.py`."""

    def setUp(self):
        self._orig_read_program = solana.sol_read.read_program
        self._orig_read_jupiter_lend_liquidity = solana.sol_read.read_jupiter_lend_liquidity
        self._orig_read_squads = solana.sol_read.read_squads

    def tearDown(self):
        solana.sol_read.read_program = self._orig_read_program
        solana.sol_read.read_jupiter_lend_liquidity = self._orig_read_jupiter_lend_liquidity
        solana.sol_read.read_squads = self._orig_read_squads

    def _patch(self, upgrade_authority, liquidity_authority, squads_by_pk):
        def fake_read_program(url, pk):
            self.assertEqual(pk, LIQUIDITY_PROGRAM)
            return {"program": pk, "upgrade_authority": upgrade_authority}

        def fake_read_jupiter_lend_liquidity(url, pk):
            self.assertEqual(pk, LIQUIDITY_ACCOUNT)
            return {"liquidity": pk, "authority": liquidity_authority}

        def fake_read_squads(url, pk):
            if pk in squads_by_pk:
                return squads_by_pk[pk]
            raise AssertionError(f"unexpected read_squads call for {pk}")

        solana.sol_read.read_program = fake_read_program
        solana.sol_read.read_jupiter_lend_liquidity = fake_read_jupiter_lend_liquidity
        solana.sol_read.read_squads = fake_read_squads


class TestBothPathsResolveAndCombineViaMin(ScoreJupiterLendTestCase):
    """The headline orchestration claim: two INDEPENDENTLY-resolved Squads
    v4 paths (program upgrade authority, Liquidity.authority), combined
    per-dimension with min() (METHODOLOGY.md 6.2) -- using threshold/voter
    shapes that deliberately differ between the two paths so a correct
    min() is actually exercised rather than coincidentally agreeing."""

    def test_combined_scores_are_elementwise_min_of_both_paths(self):
        upgrade_sq = _squads(threshold=4, member_masks=[6] * 6, time_lock_s=43200)  # 4-of-6, 12h delay
        admin_sq = _squads(threshold=5, member_masks=[6] * 10, time_lock_s=21600)  # 5-of-10, 6h delay
        self._patch(
            upgrade_authority=UPGRADE_VAULT, liquidity_authority=ADMIN_VAULT,
            squads_by_pk={UPGRADE_MS: upgrade_sq, ADMIN_MS: admin_sq},
        )

        result = solana.score_jupiter_lend("unused-url")

        expected_a = solana._score_full_power_path("squads_v4", threshold=4, voters=6, delay_s=43200)
        expected_b = solana._score_full_power_path("squads_v4", threshold=5, voters=10, delay_s=21600)
        expected = tuple(min(a, b) for a, b in zip(expected_a, expected_b))
        self.assertEqual(
            (result["adminKeyScore"], result["multisigScore"], result["timelockScore"]), expected)
        # The two paths must actually differ (different threshold/voters/
        # delay) for this to be a meaningful min(), not a coincidence where
        # both paths already agreed.
        self.assertNotEqual(expected_a, expected_b)

        self.assertEqual(result["target"], LIQUIDITY_ACCOUNT)
        self.assertEqual(result["label"], "Jupiter Lend")
        self.assertEqual(result["oracleAuthorityScore"], 100)
        self.assertEqual(result["compositeScore"], solana._composite(*expected))
        self.assertTrue(any("combined (min over both full-power paths" in n for n in result["notes"]))

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
            upgrade_authority=UPGRADE_VAULT, liquidity_authority=ADMIN_VAULT,
            squads_by_pk={UPGRADE_MS: upgrade_sq, ADMIN_MS: admin_sq},
        )
        result = solana.score_jupiter_lend("unused-url")
        expected_signers = {f"upgrade_member{i}" for i in range(3)} | {f"admin_member{i}" for i in range(3)}
        self.assertEqual(result["_signers"], expected_signers)


class TestProgramUpgradeAuthorityRenounced(ScoreJupiterLendTestCase):
    """program.upgrade_authority is None: score_jupiter_lend passes
    `none_means_renounced=True` on this path only, so this must resolve to
    the safest (100, 100, 100) band -- not the 20/20/0 degrade band -- and
    the combined score must then be driven ENTIRELY by the
    Liquidity.authority path via min() (min(100, x) == x)."""

    def test_renounced_upgrade_path_is_dominated_by_the_liquidity_authority_path(self):
        admin_sq = _squads(threshold=3, member_masks=[6, 6, 6, 6, 0], time_lock_s=3600)
        self._patch(
            upgrade_authority=None, liquidity_authority=ADMIN_VAULT,
            squads_by_pk={ADMIN_MS: admin_sq},
        )
        result = solana.score_jupiter_lend("unused-url")
        expected_b = solana._score_full_power_path("squads_v4", threshold=3, voters=4, delay_s=3600)
        self.assertEqual(
            (result["adminKeyScore"], result["multisigScore"], result["timelockScore"]), expected_b)
        self.assertTrue(any("renounced" in n for n in result["notes"]))
        self.assertFalse(any("MISMATCH" in n for n in result["notes"]))


class TestProgramUpgradePathMismatchDegrades(ScoreJupiterLendTestCase):
    """A non-None upgrade authority that does NOT match the offline-
    re-derived vault-0 of UPGRADE_MS must degrade to the fixed (20, 20, 0)
    band on that path, per `score_jupiter_lend`'s own `if upgrade_sq is
    None` branch -- never silently trusted."""

    def test_upgrade_mismatch_degrades_and_liquidity_authority_path_is_ignored_by_min(self):
        # A strong Liquidity.authority path (large threshold, long delay)
        # so this test actually exercises min() picking the weaker
        # (20, 20, 0) path, rather than coincidentally agreeing with it.
        admin_sq = _squads(threshold=8, member_masks=[6] * 10, time_lock_s=200_000)
        self._patch(
            upgrade_authority=UNRELATED_PUBKEY, liquidity_authority=ADMIN_VAULT,
            squads_by_pk={ADMIN_MS: admin_sq},
        )
        result = solana.score_jupiter_lend("unused-url")
        expected_b = solana._score_full_power_path("squads_v4", threshold=8, voters=10, delay_s=200_000)
        # Sanity: the Liquidity.authority path really is stronger on every
        # dimension, so a correct min() must land on the degraded
        # (20, 20, 0) upgrade path.
        self.assertTrue(all(b > d for b, d in zip(expected_b, (20, 20, 0))))
        self.assertEqual(
            (result["adminKeyScore"], result["multisigScore"], result["timelockScore"]), (20, 20, 0))
        self.assertTrue(any("program upgrade" in n and "MISMATCH" in n for n in result["notes"]))


class TestLiquidityAuthorityPathMismatchDegrades(ScoreJupiterLendTestCase):
    """Symmetric case on the second path: a Liquidity.authority that does
    NOT match the offline-re-derived vault-0 of ADMIN_MS must degrade to
    (20, 20, 0) via `score_jupiter_lend`'s own `if admin_sq is None`
    branch, even though the program-upgrade path resolves cleanly and
    strongly."""

    def test_liquidity_authority_mismatch_degrades_and_upgrade_path_is_ignored_by_min(self):
        upgrade_sq = _squads(threshold=8, member_masks=[6] * 10, time_lock_s=200_000)
        self._patch(
            upgrade_authority=UPGRADE_VAULT, liquidity_authority=UNRELATED_PUBKEY,
            squads_by_pk={UPGRADE_MS: upgrade_sq},
        )
        result = solana.score_jupiter_lend("unused-url")
        self.assertEqual(
            (result["adminKeyScore"], result["multisigScore"], result["timelockScore"]), (20, 20, 0))
        self.assertTrue(any("Liquidity.authority" in n and "MISMATCH" in n for n in result["notes"]))


class TestLiquidityAuthorityNoneIsNotTreatedAsRenounced(ScoreJupiterLendTestCase):
    """Asymmetry check: unlike the program-upgrade path, `score_jupiter_lend`
    calls `_resolve_squads_v4` for the Liquidity.authority path WITHOUT
    `none_means_renounced=True`. A None authority must therefore fall
    through to the ordinary mismatch/degrade band (20, 20, 0) with a
    MISMATCH note -- NOT be treated as the safe renounced band -- since a
    None `Liquidity.authority` was never documented as a genuine on-chain
    Option::None the way a renounced program upgrade authority is."""

    def test_none_liquidity_authority_degrades_instead_of_being_treated_as_renounced(self):
        upgrade_sq = _squads(threshold=4, member_masks=[6] * 6, time_lock_s=43200)
        self._patch(
            upgrade_authority=UPGRADE_VAULT, liquidity_authority=None,
            squads_by_pk={UPGRADE_MS: upgrade_sq},
        )
        result = solana.score_jupiter_lend("unused-url")
        expected_a = solana._score_full_power_path("squads_v4", threshold=4, voters=6, delay_s=43200)
        expected = tuple(min(a, b) for a, b in zip(expected_a, (20, 20, 0)))
        self.assertEqual(
            (result["adminKeyScore"], result["multisigScore"], result["timelockScore"]), expected)
        self.assertTrue(any("Liquidity.authority" in n and "MISMATCH" in n for n in result["notes"]))
        self.assertFalse(any("Liquidity.authority" in n and "renounced" in n for n in result["notes"]))


if __name__ == "__main__":
    unittest.main()
