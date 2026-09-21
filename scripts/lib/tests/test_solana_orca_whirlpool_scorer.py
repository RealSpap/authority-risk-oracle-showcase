"""
Unit tests for `chains/solana/scorers.py::score_orca_whirlpool`.

This is orchestration-level coverage only, following the established
pattern in `test_drift_protocol.py`/`test_switchboard_on_demand.py`/
`test_solend_governance.py`: `sol_read.read_X` primitives are monkeypatched
DIRECTLY on the already-imported `scorers` module's own `sol_read`
reference (`solana.sol_read.read_program`, etc.), with cleanup restoring
the originals, and the real top-level `score_orca_whirlpool()` is called
end-to-end -- no re-implementation of its formula logic.

`sol_read.read_whirlpools_config` already has dedicated byte-level decode
coverage in `test_solana_defi_config_admins.py` (real on-chain bytes for
`WhirlpoolsConfig` 2LecshUwdy9xi7meFgHtFJQNSKk4KdTrcpvaB56dP2NQ), so no new
byte fixture is built here -- it is mocked at the orchestration level like
every other primitive this scorer calls.

One thing here is NOT mocked: `sol_read.read_squads_vault` (offline PDA
re-derivation of a Squads v4 vault, pure `sha256`, no RPC/network at all)
is left as the REAL function, exactly like `test_switchboard_on_demand.py`
does for its own queue-authority path. Its output for the two multisig
candidates the scorer hardcodes is deterministic and was cross-checked
directly against this pass's read of `scorers.py`'s own docstring:

    read_squads_vault("BQsDWkL417U4tVE2sDnPks469pKdm6YzFgKH77doiEjF", 0)["vault"]
        == "GwH3Hiv5mACLX3ufTw1pFsrhSPon5tdw252DBs4Rx4PV"   (the real program-upgrade vault)
    read_squads_vault("5JZFPx6Qkg9PAgYMn9wHWirsiEQBfeJuE667MWeRBLPN", 0)["vault"]
        == "DXnB9N9JLH5c9AYdKMGHQyspewSsvhFnwLK1tz1iPmZw"   (the real reward-emissions vault)

so a mocked `read_program`/`read_whirlpools_config` authority value that
equals one of these two constants is a genuine MATCH through real code,
not a hand-picked fixture; any other value is a genuine MISMATCH.
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


solana = _load_module("aro_test_solana_scorers_orca_whirlpool", "chains/solana/scorers.py")

# Exact constants copied from chains/solana/scorers.py::score_orca_whirlpool
# (read directly from the source this pass, not guessed).
WHIRLPOOL_PROGRAM = "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc"
WHIRLPOOLS_CONFIG = "2LecshUwdy9xi7meFgHtFJQNSKk4KdTrcpvaB56dP2NQ"
UPGRADE_MS = "BQsDWkL417U4tVE2sDnPks469pKdm6YzFgKH77doiEjF"
REWARD_SUPER_MS = "5JZFPx6Qkg9PAgYMn9wHWirsiEQBfeJuE667MWeRBLPN"

# Real offline vault-0 PDAs of the two candidates above, computed by the
# REAL (unmocked) sol_read.read_squads_vault -- see module docstring.
UPGRADE_VAULT0 = solana.sol_read.read_squads_vault(UPGRADE_MS, 0)["vault"]
REWARD_VAULT0 = solana.sol_read.read_squads_vault(REWARD_SUPER_MS, 0)["vault"]


def _squads_v4(threshold, member_masks, time_lock_s=0, key_prefix="member"):
    """A well-formed read_squads() return -- autonomous config_authority
    (the only band _resolve_squads_v4 supports; see its own docstring),
    given threshold/per-member vote-permission masks/time_lock."""
    return {
        "multisig": "unused-ms", "owner": solana.SQUADS_V4_PROGRAM,
        "config_authority": solana.SYSTEM_PROGRAM_DEFAULT,
        "threshold": threshold, "time_lock_s": time_lock_s,
        "members": len(member_masks),
        "member_list": [{"key": f"{key_prefix}{i}", "mask": m} for i, m in enumerate(member_masks)],
    }


def _run_scorer(upgrade_authority, reward_authority, squads_map,
                 collect_authority="CollectProtocolFeesAuthorityPlaceholder"):
    """Monkeypatch the three sol_read primitives score_orca_whirlpool calls
    (read_program, read_whirlpools_config, read_squads) directly on the
    already-loaded scorers module, call the real function, restore."""
    orig_read_program = solana.sol_read.read_program
    orig_read_whirlpools_config = solana.sol_read.read_whirlpools_config
    orig_read_squads = solana.sol_read.read_squads
    try:
        def fake_read_program(url, pk):
            assert pk == WHIRLPOOL_PROGRAM, f"unexpected program pk {pk}"
            return {"upgrade_authority": upgrade_authority}

        def fake_read_whirlpools_config(url, pk):
            assert pk == WHIRLPOOLS_CONFIG, f"unexpected config pk {pk}"
            return {
                "config": pk,
                "fee_authority": UPGRADE_VAULT0,  # informational only -- aliases the upgrade path, never read by the scorer
                "collect_protocol_fees_authority": collect_authority,
                "reward_emissions_super_authority": reward_authority,
            }

        def fake_read_squads(url, pk):
            if pk in squads_map:
                return squads_map[pk]
            raise AssertionError(f"unexpected read_squads call for {pk}")

        solana.sol_read.read_program = fake_read_program
        solana.sol_read.read_whirlpools_config = fake_read_whirlpools_config
        solana.sol_read.read_squads = fake_read_squads
        return solana.score_orca_whirlpool("unused-url")
    finally:
        solana.sol_read.read_program = orig_read_program
        solana.sol_read.read_whirlpools_config = orig_read_whirlpools_config
        solana.sol_read.read_squads = orig_read_squads


class TestScoreOrcaWhirlpool(unittest.TestCase):

    def test_real_world_reward_threshold_one_dominates_combined_score(self):
        # Reproduces the scorer's own headline finding, verbatim from its
        # docstring: program-upgrade is a real 5-of-13 (9 with Vote), 24h
        # delay Squads v4 vault; reward_emissions_super_authority is a
        # DIFFERENT, much weaker 1-of-8 Squads v4 vault, which scores as a
        # bare on-curve key per METHODOLOGY.md 6.1's threshold=1 rule and
        # collapses the combined min() score to near-floor.
        squads_map = {
            UPGRADE_MS: _squads_v4(5, [2] * 9 + [1] * 4, time_lock_s=86400),
            REWARD_SUPER_MS: _squads_v4(1, [2] * 8),
        }
        result = _run_scorer(UPGRADE_VAULT0, REWARD_VAULT0, squads_map)

        admin_a, multisig_a, timelock_a = solana._score_full_power_path(
            "squads_v4", threshold=5, voters=9, delay_s=86400)
        admin_b, multisig_b, timelock_b = solana._score_full_power_path(
            "squads_v4", threshold=1, voters=8, delay_s=0)
        self.assertEqual((admin_b, multisig_b, timelock_b), (5, 0, 0))

        expected = (min(admin_a, admin_b), min(multisig_a, multisig_b), min(timelock_a, timelock_b))
        self.assertEqual(
            (result["adminKeyScore"], result["multisigScore"], result["timelockScore"]), expected)
        self.assertEqual(expected, (5, 0, 0))
        self.assertEqual(result["compositeScore"], 2)

    def test_program_upgrade_renounced_lets_reward_path_dominate(self):
        # upgrade_authority is None -> RENOUNCED (100/100/100, the safest
        # band), so the combined score must equal the reward path's own
        # numbers exactly, not be pulled down by a phantom "mismatch".
        squads_map = {REWARD_SUPER_MS: _squads_v4(3, [2, 2, 2, 2, 1], time_lock_s=3600)}
        result = _run_scorer(None, REWARD_VAULT0, squads_map)

        admin_b, multisig_b, timelock_b = solana._score_full_power_path(
            "squads_v4", threshold=3, voters=4, delay_s=3600)
        self.assertEqual(
            (result["adminKeyScore"], result["multisigScore"], result["timelockScore"]),
            (admin_b, multisig_b, timelock_b))
        self.assertTrue(any("renounced" in n for n in result["notes"]))
        self.assertFalse(any("MISMATCH" in n for n in result["notes"]))

    def test_program_upgrade_mismatch_degrades_to_20_20_0(self):
        # upgrade_authority is present but does NOT match the offline-
        # derived vault-0 of UPGRADE_MS -> must degrade to 20/20/0 (not
        # silently trust it, per _resolve_squads_v4's own contract), and
        # that degraded path must dominate the combined min() even against
        # a much stronger reward path.
        squads_map = {REWARD_SUPER_MS: _squads_v4(6, [2] * 10, time_lock_s=259200)}
        result = _run_scorer(REWARD_VAULT0, REWARD_VAULT0, squads_map)  # REWARD_VAULT0 != UPGRADE_VAULT0 -> mismatch on the upgrade path

        self.assertEqual(
            (result["adminKeyScore"], result["multisigScore"], result["timelockScore"]), (20, 20, 0))
        self.assertTrue(any("program upgrade" in n and "MISMATCH, degrading" in n for n in result["notes"]))

    def test_reward_authority_none_degrades_not_renounced_unlike_upgrade(self):
        # Orchestration asymmetry: score_orca_whirlpool passes
        # none_means_renounced=True only for the program-upgrade path, NOT
        # for reward_emissions_super_authority -- a None reward authority
        # must degrade to 20/20/0, not be treated as the safest band.
        squads_map = {UPGRADE_MS: _squads_v4(5, [2] * 9 + [1] * 4, time_lock_s=86400)}
        result = _run_scorer(UPGRADE_VAULT0, None, squads_map)

        self.assertEqual(
            (result["adminKeyScore"], result["multisigScore"], result["timelockScore"]), (20, 20, 0))
        self.assertFalse(any(
            "reward_emissions_super_authority" in n and "renounced" in n for n in result["notes"]))
        self.assertTrue(any(
            "reward_emissions_super_authority" in n and "MISMATCH, degrading" in n for n in result["notes"]))

    def test_collect_protocol_fees_authority_is_disclosed_but_not_scored(self):
        # collect_protocol_fees_authority is a bare on-curve EOA that ONLY
        # gates withdrawing already-accrued fees (bounded, per the
        # docstring) -- changing it must not move any score, only the notes.
        squads_map = {
            UPGRADE_MS: _squads_v4(5, [2] * 9 + [1] * 4, time_lock_s=86400),
            REWARD_SUPER_MS: _squads_v4(1, [2] * 8),
        }
        result_a = _run_scorer(UPGRADE_VAULT0, REWARD_VAULT0, squads_map, collect_authority="CollectAuthorityCandidateOne")
        result_b = _run_scorer(UPGRADE_VAULT0, REWARD_VAULT0, squads_map, collect_authority="CollectAuthorityCandidateTwo")

        self.assertEqual(
            (result_a["adminKeyScore"], result_a["multisigScore"], result_a["timelockScore"]),
            (result_b["adminKeyScore"], result_b["multisigScore"], result_b["timelockScore"]))
        self.assertTrue(any("not scored as full-power" in n for n in result_a["notes"]))
        self.assertTrue(any("CollectAuthorityCandidateOne" in n for n in result_a["notes"]))

    def test_min_across_two_ordinary_nondegenerate_squads_v4_paths(self):
        # Neither path is a degenerate case (no renounce, no mismatch, no
        # threshold=1) -- a plain, general test of the min()-across-paths
        # combination the docstring calls out as METHODOLOGY.md 6.2's rule.
        squads_map = {
            UPGRADE_MS: _squads_v4(2, [2, 2, 1], time_lock_s=0),          # weaker: 2-of-3, no delay
            REWARD_SUPER_MS: _squads_v4(6, [2] * 10, time_lock_s=259200),  # stronger: 6-of-10, 72h delay
        }
        result = _run_scorer(UPGRADE_VAULT0, REWARD_VAULT0, squads_map)

        admin_a, multisig_a, timelock_a = solana._score_full_power_path(
            "squads_v4", threshold=2, voters=2, delay_s=0)
        admin_b, multisig_b, timelock_b = solana._score_full_power_path(
            "squads_v4", threshold=6, voters=10, delay_s=259200)
        expected = (min(admin_a, admin_b), min(multisig_a, multisig_b), min(timelock_a, timelock_b))

        self.assertEqual(
            (result["adminKeyScore"], result["multisigScore"], result["timelockScore"]), expected)
        # The weaker upgrade path is the one that should be binding here.
        self.assertEqual(expected, (admin_a, multisig_a, timelock_a))

    def test_composite_and_metadata_fields(self):
        squads_map = {REWARD_SUPER_MS: _squads_v4(1, [2] * 8)}
        result = _run_scorer(None, REWARD_VAULT0, squads_map)

        self.assertEqual(result["target"], WHIRLPOOLS_CONFIG)
        self.assertEqual(result["label"], "Orca Whirlpool")
        self.assertEqual(result["oracleAuthorityScore"], 100)
        self.assertEqual(
            result["compositeScore"],
            solana._composite(result["adminKeyScore"], result["multisigScore"], result["timelockScore"]))

    def test_signers_union_includes_members_from_both_matched_paths(self):
        squads_map = {
            UPGRADE_MS: _squads_v4(5, [2] * 9 + [1] * 4, time_lock_s=86400, key_prefix="up_"),
            REWARD_SUPER_MS: _squads_v4(3, [2, 2, 2, 2, 1, 1, 1, 1], time_lock_s=0, key_prefix="rw_"),
        }
        result = _run_scorer(UPGRADE_VAULT0, REWARD_VAULT0, squads_map)

        self.assertIn("up_0", result["_signers"])
        self.assertIn("rw_0", result["_signers"])
        self.assertEqual(len(result["_signers"]), 13 + 8)


if __name__ == "__main__":
    unittest.main()
