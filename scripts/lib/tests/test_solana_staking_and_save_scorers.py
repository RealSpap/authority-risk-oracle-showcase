"""
Offline tests for the five `chains/solana/scorers.py` scorers added on 2026-09-20: `score_save`,
`score_spl_stake_pool_program`, `score_jitosol`, `score_sanctum_infinity`, `score_sanctum_validator_lsts`
(and their two helpers). Every read goes through `sol_read`, whose reader functions are PATCHED BY NAME (the
project's usual convention); `sol_read.rpc` and `sol_read.acct` raise unless a test installs account bytes on
purpose. The pure offline primitives (`find_program_address`, `on_curve`, `b58`, `b58dec`) are NOT patched: the
scorers derive real PDAs with them, and the addresses below are real accounts whose relationships are checked in
`TestFixtureProvenance`.

FIXTURE PROVENANCE. Addresses come from `chains/solana/data/scouted_targets_2026-09-17-run2.md` (rows 9, 10, 11,
15, 16 and its reproduction block, re-run `OK` against Mainnet Beta on 2026-09-20). Every expected number is
hand-derived from METHODOLOGY.md 6.1, with the arithmetic written next to it, never copied from a run:

  composite = (4 admin + 3 multisig + 3 timelock + 5) // 10
  Squads v3 t-of-n:  admin = 40 + min(20, 5 (t - 1)), multisig = min(100, round(15 t + 40 t / n)), timelock = 0
  Squads v4 t-of-n, no delay: same admin and multisig formulas, timelock 0
  bare on-curve key 5 / 0 / 0, off-curve unresolved 20 / 0 / 0, renounced 100 / 100 / 100, degraded 20 / 20 / 0

  6-of-10 (SPL Stake Pool):    admin 40 + 25 -> capped at 60, multisig round(90 + 24) = 114 -> 100, timelock 0
                               composite (240 + 300 + 0 + 5) // 10 = 54
  6-of-11 (Sanctum):           admin 60, multisig round(90 + 21.8) = 112 -> 100, composite 54
  4-of-8 v4 no delay (Infinity admin): admin 40 + 15 = 55, multisig round(60 + 20) = 80, timelock 0
                               composite (220 + 240 + 0 + 5) // 10 = 46
  bare key: composite (20 + 0 + 0 + 5) // 10 = 2
  degraded 20 / 20 / 0: composite (80 + 60 + 0 + 5) // 10 = 14

The individual member keys of the two Squads v3 committees are not recorded in the repository (only counts and
some prefixes), so those are SYNTHETIC keys; no expected score depends on which keys they are. The signer-set
assertions are only about set arithmetic over those inventions.
"""
import base64
import importlib.util
import os
import sys
import unittest
from unittest import mock

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


solana = _load_module("aro_test_solana_staking_and_save", "chains/solana/scorers.py")
sol_read = solana.sol_read

SYSTEM_PROGRAM = "11111111111111111111111111111111"
SAVE_AUTHORITY = "RY93CZYe5g6drtG7W9PmHRPzaBLZ1uwihTzayQTmJfh"  # a bare on-curve key (row 9)
SPL_AUTHORITY = "dPpFfahSWhm5M2RB3nVaHsXfnh9ooz5bWtR3WeUguDH"  # Squads v3 authority index 1 of 3yqoHF... (row 10)
SANCTUM_AUTHORITY = "47SND7bGKvNXrqfP1bjsLCbwTgZhFBzAgmZ42QSkRScz"  # Squads v3 authority index 1 of AApfiP... (row 15)
INFINITY_ADMIN_VAULT = "8JS6XsMPo2u3EyeeY3p2jvzHEhdUtCKgarHpJ3PAonyv"  # Squads v4 vault 0 of 8EamQU... (row 15)
INFINITY_REBALANCE = "5oVNBeEEQvYi1cX3ir8Dx5n1P7pdxydbGF2X4TxVusJm"  # a single on-curve key, bounded (row 15)


def _key(n):
    return sol_read.b58(bytes([n]) * 32)


SPL_KEYS = tuple(_key(0x10 + i) for i in range(10))
SANCTUM_KEYS = tuple(_key(0x30 + i) for i in range(11))
INFINITY_VOTERS = tuple(_key(0x50 + i) for i in range(8))


def _squads_v3(threshold, keys, authority_key, authority):
    return {"ms": "x", "owner": "SMPLecH534NA9acpos4G6x7uf3LWbCAwZQE9e8ZekMu", "threshold": threshold,
            "authority_index": 1, "n_keys": len(keys), "keys": list(keys), authority_key: authority}


class _Reads:
    """Patches the `sol_read` readers the five scorers use. `programs` maps a program id to its upgrade authority
    (None = renounced); `squads_v3` maps a multisig to what `read_squadsv3` returns for authority index 1."""

    def __init__(self):
        self.programs = {}
        self.squads_v3 = {}
        self.squads_v4 = {}
        self.accounts = {}
        self.keytypes = {}
        self.mints = {}
        self.calls = []

    def read_program(self, url, pk):
        self.calls.append(("read_program", pk))
        return {"program": pk, "upgrade_authority": self.programs[pk]}

    def read_squadsv3(self, url, pk, authority_index=None):
        self.calls.append(("read_squadsv3", pk))
        return dict(self.squads_v3[pk])

    def read_squads(self, url, pk):
        self.calls.append(("read_squads", pk))
        return dict(self.squads_v4[pk])

    def acct(self, url, pk, enc="base64", length=None):
        self.calls.append(("acct", pk))
        return {"data": [base64.b64encode(self.accounts[pk]).decode(), "base64"]}

    def read_keytype(self, url, pk):
        return {"key": pk, "owner": self.keytypes[pk]}

    def read_mint(self, url, pk):
        return {"mint": pk, "mintAuthority": self.mints[pk]}

    def _no_network(self, *a, **k):
        raise AssertionError("unexpected network read")

    def install(self, testcase):
        for name, fn in (("rpc", self._no_network), ("read_program", self.read_program), ("read_squadsv3", self.read_squadsv3),
                         ("read_squads", self.read_squads), ("acct", self.acct), ("read_keytype", self.read_keytype),
                         ("read_mint", self.read_mint)):
            p = mock.patch.object(sol_read, name, fn)
            p.start()
            testcase.addCleanup(p.stop)


def _chain():
    r = _Reads()
    r.programs[solana.SAVE_PROGRAM] = SAVE_AUTHORITY
    r.programs[solana.SPL_STAKE_POOL_PROGRAM] = SPL_AUTHORITY
    r.squads_v3[solana.SPL_STAKE_POOL_MS] = _squads_v3(6, SPL_KEYS, "authority_1", SPL_AUTHORITY)
    for p in (solana.SANCTUM_S_CONTROLLER, *solana.SANCTUM_LST_PROGRAMS):
        r.programs[p] = SANCTUM_AUTHORITY
    r.squads_v3[solana.SANCTUM_MS] = _squads_v3(6, SANCTUM_KEYS, "authority_1", SANCTUM_AUTHORITY)
    r.squads_v4[solana.SANCTUM_ADMIN_MS] = {
        "multisig": solana.SANCTUM_ADMIN_MS, "config_authority": SYSTEM_PROGRAM, "threshold": 4, "time_lock_s": 0,
        "members": 8, "member_list": [{"key": k, "mask": 7} for k in INFINITY_VOTERS]}
    # S Controller state PDA: admin at bytes 16:48, rebalance_authority at 144:176.
    state = bytearray(200)
    state[16:48] = sol_read.b58dec(INFINITY_ADMIN_VAULT)
    state[144:176] = sol_read.b58dec(INFINITY_REBALANCE)
    r.accounts[sol_read.find_program_address([b"state"], solana.SANCTUM_S_CONTROLLER)[0]] = bytes(state)
    # JitoSOL pool: manager 1:33, staker 33:65, pool mint 162:194.
    staker = _key(0x77)
    pool = bytearray(260)
    pool[1:33] = sol_read.b58dec(solana.JITO_MANAGER)
    pool[33:65] = sol_read.b58dec(staker)
    pool[162:194] = sol_read.b58dec(solana.JITO_MINT)
    r.accounts[solana.JITO_POOL] = bytes(pool)
    r.keytypes[staker] = solana.JITO_STEWARD_PROGRAM
    r.mints[solana.JITO_MINT] = sol_read.find_program_address([sol_read.b58dec(solana.JITO_POOL), b"withdraw"], solana.SPL_STAKE_POOL_PROGRAM)[0]
    r.staker = staker
    return r


class _Case(unittest.TestCase):
    def setUp(self):
        self.chain = _chain()
        self.chain.install(self)

    def scores(self, r):
        return (r["adminKeyScore"], r["multisigScore"], r["timelockScore"])

    def has_note(self, r, fragment):
        return any(fragment in n for n in r["notes"])


class TestFixtureProvenance(unittest.TestCase):
    def test_spl_and_sanctum_authorities_are_the_documented_squads_v3_authority_index_1_pdas(self):
        seeds = lambda ms: [b"squad", sol_read.b58dec(ms), (1).to_bytes(4, "little"), b"authority"]
        self.assertEqual(sol_read.find_program_address(seeds(solana.SPL_STAKE_POOL_MS), solana.SQUADS_V3_PROGRAM)[0], SPL_AUTHORITY)
        self.assertEqual(sol_read.find_program_address(seeds(solana.SANCTUM_MS), solana.SQUADS_V3_PROGRAM)[0], SANCTUM_AUTHORITY)

    def test_sanctum_admin_is_vault_0_of_the_documented_squads_v4_multisig(self):
        self.assertEqual(sol_read.read_squads_vault(solana.SANCTUM_ADMIN_MS, 0)["vault"], INFINITY_ADMIN_VAULT)

    def test_documented_on_curve_and_off_curve_classification(self):
        self.assertTrue(sol_read.on_curve(SAVE_AUTHORITY))
        self.assertTrue(sol_read.on_curve(INFINITY_REBALANCE))
        self.assertFalse(sol_read.on_curve(SPL_AUTHORITY))
        self.assertFalse(sol_read.on_curve(SANCTUM_AUTHORITY))

    def test_the_five_scorers_are_registered_after_marinade_in_push_order(self):
        # The dashboard's Solana cards address targets by their index in the oracle's tracked order, which is
        # the order of SIMPLE_SCORERS. Moving these would silently shift every card.
        names = [f.__name__ for f in solana.SIMPLE_SCORERS]
        self.assertEqual(names[12:], ["score_marinade", "score_save", "score_spl_stake_pool_program", "score_jitosol",
                                      "score_sanctum_infinity", "score_sanctum_validator_lsts", "score_solgov_leads"])


class TestScoreSave(_Case):
    def test_bare_on_curve_upgrade_key_is_the_bottom_rung(self):
        r = solana.score_save("u")
        self.assertEqual(self.scores(r), (5, 0, 0))
        self.assertEqual(r["compositeScore"], 2)  # (20 + 0 + 0 + 5) // 10
        self.assertEqual(r["target"], solana.SAVE_PROGRAM)
        self.assertEqual(r["_signers"], set())
        self.assertEqual(r["oracleAuthorityScore"], 100)

    def test_renounced_authority_is_the_safest_band_not_a_failed_read(self):
        self.chain.programs[solana.SAVE_PROGRAM] = None
        r = solana.score_save("u")
        self.assertEqual(self.scores(r), (100, 100, 100))
        self.assertEqual(r["compositeScore"], 100)  # (400 + 300 + 300 + 5) // 10

    def test_off_curve_authority_degrades_to_20_0_0(self):
        self.chain.programs[solana.SAVE_PROGRAM] = SPL_AUTHORITY  # a PDA
        r = solana.score_save("u")
        self.assertEqual(self.scores(r), (20, 0, 0))
        self.assertEqual(r["compositeScore"], 8)  # (80 + 0 + 0 + 5) // 10
        self.assertTrue(self.has_note(r, "re-scout"))

    def test_notes_say_the_market_owner_cannot_lower_a_bare_key(self):
        self.assertTrue(self.has_note(solana.score_save("u"), "cannot lower a bare-key"))


class TestScoreSplStakePool(_Case):
    def test_squads_v3_6_of_10_is_60_100_0_composite_54(self):
        r = solana.score_spl_stake_pool_program("u")
        self.assertEqual(self.scores(r), (60, 100, 0))
        self.assertEqual(r["compositeScore"], 54)
        self.assertEqual(r["_signers"], set(SPL_KEYS))
        self.assertTrue(self.has_note(r, "MATCH"))

    def test_authority_that_the_candidate_multisig_does_not_reproduce_degrades_to_20_20_0(self):
        self.chain.programs[solana.SPL_STAKE_POOL_PROGRAM] = SANCTUM_AUTHORITY  # a different real PDA
        self.chain.squads_v3[solana.SPL_STAKE_POOL_MS] = _squads_v3(6, SPL_KEYS, "authority_1", SPL_AUTHORITY)
        r = solana.score_spl_stake_pool_program("u")
        # _resolve_squads_v3 re-derives authority_1 offline from the multisig; here the fake reader claims it is
        # SPL_AUTHORITY while the live authority is different, so it must NOT match.
        self.assertEqual(self.scores(r), (20, 20, 0))
        self.assertEqual(r["compositeScore"], 14)  # (80 + 60 + 0 + 5) // 10
        self.assertEqual(r["_signers"], set())
        self.assertTrue(self.has_note(r, "MISMATCH"))

    def test_renounced_upgrade_authority_is_the_safest_band(self):
        self.chain.programs[solana.SPL_STAKE_POOL_PROGRAM] = None
        r = solana.score_spl_stake_pool_program("u")
        self.assertEqual(self.scores(r), (100, 100, 100))


class TestScoreJitoSol(_Case):
    def test_full_power_path_is_the_stake_pool_upgrade_and_the_roles_are_bounded(self):
        r = solana.score_jitosol("u")
        self.assertEqual(self.scores(r), (60, 100, 0))
        self.assertEqual(r["compositeScore"], 54)
        self.assertEqual(r["target"], solana.JITO_POOL)
        self.assertEqual(r["_signers"], set(SPL_KEYS))  # inherits the SPL Stake Pool committee
        self.assertTrue(self.has_note(r, "match the bounded classification"))

    def _assert_drift_raises(self, field):
        with self.assertRaisesRegex(RuntimeError, field):
            solana.score_jitosol("u")

    def test_a_changed_manager_raises_instead_of_publishing_a_stale_classification(self):
        pool = bytearray(self.chain.accounts[solana.JITO_POOL])
        pool[1:33] = sol_read.b58dec(_key(0x99))
        self.chain.accounts[solana.JITO_POOL] = bytes(pool)
        self._assert_drift_raises("manager")

    def test_a_staker_no_longer_owned_by_the_steward_program_raises(self):
        self.chain.keytypes[self.chain.staker] = SYSTEM_PROGRAM
        self._assert_drift_raises("staker owner")

    def test_a_mint_authority_that_is_not_the_withdraw_pda_raises(self):
        self.chain.mints[solana.JITO_MINT] = _key(0x66)  # a human key could now mint
        self._assert_drift_raises("mint authority")

    def test_a_different_pool_mint_raises(self):
        pool = bytearray(self.chain.accounts[solana.JITO_POOL])
        pool[162:194] = sol_read.b58dec(_key(0x55))
        self.chain.accounts[solana.JITO_POOL] = bytes(pool)
        self.chain.mints[_key(0x55)] = self.chain.mints[solana.JITO_MINT]
        self._assert_drift_raises("pool mint")


class TestScoreSanctumInfinity(_Case):
    def test_min_over_the_upgrade_path_and_the_pool_admin_is_55_80_0_composite_46(self):
        r = solana.score_sanctum_infinity("u")
        # upgrade 60 / 100 / 0, pool admin 55 / 80 / 0: the pool admin binds admin and multisig.
        self.assertEqual(self.scores(r), (55, 80, 0))
        self.assertEqual(r["compositeScore"], 46)
        self.assertEqual(r["_signers"], set(SANCTUM_KEYS) | set(INFINITY_VOTERS))

    def test_pool_admin_that_is_not_the_candidate_multisigs_vault_degrades_the_whole_target(self):
        state = bytearray(self.chain.accounts[sol_read.find_program_address([b"state"], solana.SANCTUM_S_CONTROLLER)[0]])
        state[16:48] = sol_read.b58dec(_key(0x88))
        self.chain.accounts[sol_read.find_program_address([b"state"], solana.SANCTUM_S_CONTROLLER)[0]] = bytes(state)
        r = solana.score_sanctum_infinity("u")
        self.assertEqual(self.scores(r), (20, 20, 0))
        self.assertEqual(r["compositeScore"], 14)
        self.assertTrue(self.has_note(r, "MISMATCH"))

    def test_the_bounded_rebalance_key_is_disclosed_and_not_scored(self):
        r = solana.score_sanctum_infinity("u")
        self.assertTrue(self.has_note(r, INFINITY_REBALANCE))
        self.assertTrue(self.has_note(r, "disclosed, not scored"))

    def test_voters_are_counted_by_vote_permission_not_by_member_count(self):
        ms = self.chain.squads_v4[solana.SANCTUM_ADMIN_MS]
        ms["member_list"] = [{"key": k, "mask": 7 if i < 4 else 5} for i, k in enumerate(INFINITY_VOTERS)]  # mask 5 = no Vote bit
        r = solana.score_sanctum_infinity("u")
        # 4-of-4 voters, no delay: admin 40 + min(20, 15) = 55, multisig min(100, round(60 + 40)) = 100.
        # Upgrade path 60 / 100 / 0, so the min is 55 / 100 / 0, composite (220 + 300 + 0 + 5) // 10 = 52.
        self.assertEqual(self.scores(r), (55, 100, 0))
        self.assertEqual(r["compositeScore"], 52)


class TestScoreSanctumValidatorLsts(_Case):
    def test_both_programs_share_the_committee_score_60_100_0_composite_54(self):
        r = solana.score_sanctum_validator_lsts("u")
        self.assertEqual(self.scores(r), (60, 100, 0))
        self.assertEqual(r["compositeScore"], 54)
        self.assertEqual(r["target"], solana.SANCTUM_LST_PROGRAMS[0])
        self.assertEqual(r["_signers"], set(SANCTUM_KEYS))

    def test_it_is_labelled_an_upper_bound(self):
        self.assertTrue(self.has_note(solana.score_sanctum_validator_lsts("u"), "upper bound"))

    def test_one_program_whose_authority_moved_drags_the_target_to_the_degraded_band(self):
        self.chain.programs[solana.SANCTUM_LST_PROGRAMS[1]] = SPL_AUTHORITY
        r = solana.score_sanctum_validator_lsts("u")
        self.assertEqual(self.scores(r), (20, 20, 0))
        self.assertEqual(r["compositeScore"], 14)

    def test_both_programs_are_read(self):
        solana.score_sanctum_validator_lsts("u")
        read = [pk for name, pk in self.chain.calls if name == "read_program"]
        self.assertEqual(read, list(solana.SANCTUM_LST_PROGRAMS))


if __name__ == "__main__":
    unittest.main()
