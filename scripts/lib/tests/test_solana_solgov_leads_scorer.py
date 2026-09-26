"""Unit tests for the SolGov-lead scorers in `chains/solana/scorers.py` (added 2026-09-26): `_squads_v4_upgrade_path`,
`_score_solgov_lead`, `score_solgov_leads` and the `vault_index` parameter of `_resolve_squads_v4`. Like test_solana_raydium_scorer.py,
`sol_read` is monkeypatched on the loaded module; `_score_full_power_path` is used to build expected values, not re-tested."""
import contextlib
import importlib.util
import io
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


solana = _load_module("aro_test_solana_scorers_solgov", "chains/solana/scorers.py")


def _squads(threshold, n, delay_s):
    return {"threshold": threshold, "members": n, "time_lock_s": delay_s, "config_authority": solana.SYSTEM_PROGRAM_DEFAULT,
            "member_list": [{"key": f"member{i}", "mask": 7} for i in range(n)]}


@contextlib.contextmanager
def patched(**attrs):
    old = {k: getattr(solana, k) for k in attrs}
    for k, v in attrs.items():
        setattr(solana, k, v)
    try:
        yield
    finally:
        for k, v in old.items():
            setattr(solana, k, v)


@contextlib.contextmanager
def read_program_returns(authority):
    old = solana.sol_read.read_program
    solana.sol_read.read_program = lambda url, pk: {"upgrade_authority": authority}
    try:
        yield
    finally:
        solana.sol_read.read_program = old


class TestUpgradePath(unittest.TestCase):
    def test_match_scores_the_squads_v4_path(self):
        seen = {}

        def resolver(url, label, authority, ms, notes, none_means_renounced=False, vault_index=0):
            seen.update(ms=ms, vault_index=vault_index, renounced=none_means_renounced)
            return _squads(3, 5, 86400)

        with patched(_resolve_squads_v4=resolver), read_program_returns("Auth"):
            admin, multisig, timelock, signers = solana._squads_v4_upgrade_path("u", "USX upgrade", "P", "MS", 1, [])
        self.assertEqual((admin, multisig, timelock), solana._score_full_power_path("squads_v4", threshold=3, voters=5, delay_s=86400))
        self.assertEqual(signers, {f"member{i}" for i in range(5)})
        self.assertEqual(seen, {"ms": "MS", "vault_index": 1, "renounced": True})

    def test_voters_exclude_members_without_vote_permission(self):
        sq = _squads(3, 5, 0)
        sq["member_list"][0]["mask"] = 5  # initiate + execute, no vote
        with patched(_resolve_squads_v4=lambda *a, **k: sq), read_program_returns("Auth"):
            admin, multisig, _, _ = solana._squads_v4_upgrade_path("u", "x", "P", "MS", 0, [])
        self.assertEqual((admin, multisig), solana._score_full_power_path("squads_v4", threshold=3, voters=4, delay_s=0)[:2])

    def test_mismatch_degrades_instead_of_trusting_the_candidate(self):
        with patched(_resolve_squads_v4=lambda *a, **k: None), read_program_returns("Auth"):
            self.assertEqual(solana._squads_v4_upgrade_path("u", "x", "P", "MS", 0, []), (20, 20, 0, set()))

    def test_renounced_authority_is_the_safest_band(self):
        with read_program_returns(None):
            self.assertEqual(solana._squads_v4_upgrade_path("u", "x", "P", "MS", 0, []), (100, 100, 100, set()))


class TestResolverVaultIndex(unittest.TestCase):
    def test_vault_index_reaches_the_pda_derivation(self):
        asked = []
        old = (solana.sol_read.read_squads_vault, solana.sol_read.read_squads)
        solana.sol_read.read_squads_vault = lambda ms, i: asked.append(i) or {"vault": "V" + str(i)}
        solana.sol_read.read_squads = lambda url, ms: _squads(3, 5, 0)
        try:
            self.assertIsNotNone(solana._resolve_squads_v4("u", "x", "V1", "MS", [], vault_index=1))
            self.assertIsNone(solana._resolve_squads_v4("u", "x", "V0", "MS", [], vault_index=1))  # authority is vault 0, candidate says vault 1
        finally:
            solana.sol_read.read_squads_vault, solana.sol_read.read_squads = old
        self.assertEqual(asked, [1, 1])


class TestScoreLead(unittest.TestCase):
    def test_componentwise_minimum_over_paths_and_signer_union(self):
        squads = {"STRONG": _squads(5, 9, 43200), "WEAK": _squads(2, 3, 0)}
        with patched(_resolve_squads_v4=lambda url, label, auth, ms, notes, **k: squads[ms]), read_program_returns("Auth"):
            r = solana._score_solgov_lead("u", "T", "Lead", (("a", "P1", "STRONG", 0), ("b", "P2", "WEAK", 0)))
        strong = solana._score_full_power_path("squads_v4", threshold=5, voters=9, delay_s=43200)
        weak = solana._score_full_power_path("squads_v4", threshold=2, voters=3, delay_s=0)
        want = tuple(min(a, b) for a, b in zip(strong, weak))
        self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["timelockScore"]), want)
        self.assertEqual(r["compositeScore"], solana._composite(*want))
        self.assertEqual(r["target"], "T")
        self.assertEqual(r["oracleAuthorityScore"], 100)
        self.assertEqual(r["_signers"], {f"member{i}" for i in range(9)})
        self.assertTrue(any("upper bound" in n for n in r["notes"]))


class TestScoreLeads(unittest.TestCase):
    def test_a_failing_lead_is_skipped_alone(self):
        def scorer(url, target, label, paths):
            if target == SkipMe:
                raise RuntimeError("rpc down")
            return {"target": target}

        SkipMe = solana.SOLGOV_LEADS[1][1]
        buf = io.StringIO()
        with patched(_score_solgov_lead=scorer), contextlib.redirect_stdout(buf):
            out = solana.score_solgov_leads("u")
        self.assertEqual(len(out), len(solana.SOLGOV_LEADS) - 1)
        self.assertNotIn(SkipMe, [o["target"] for o in out])
        self.assertIn("score_all(): SKIPPED score_solgov_leads", buf.getvalue())

    def test_lead_table_is_well_formed(self):
        targets = [t for _, t, _, _ in solana.SOLGOV_LEADS]
        self.assertEqual(len(set(targets)), len(targets), "target ids must be unique: they key the on-chain entry")
        existing = {getattr(solana, n) for n in dir(solana) if n.endswith("_PROGRAM")}
        for name, target, label, paths in solana.SOLGOV_LEADS:
            self.assertEqual(target, paths[0][1], f"{name}: the target is the first program id")
            for pname, program, ms, vault in paths:
                self.assertTrue(32 <= len(program) <= 44 and 32 <= len(ms) <= 44, f"{name}/{pname}: not a base58 address")
                self.assertIn(vault, range(4))
        self.assertNotIn(targets[0], existing)

    def test_registered_once_in_the_simple_scorer_list(self):
        self.assertEqual(solana.SIMPLE_SCORERS.count(solana.score_solgov_leads), 1)


if __name__ == "__main__":
    unittest.main()
