"""
Unit tests for `chains/solana/scorers.py::score_raydium` (added 2026-09-17,
lines ~834-948) -- Raydium's own multi-path orchestration: three programs'
upgrade authorities must agree or the scorer aborts, two SEPARATE full-power
paths (shared program-upgrade Squads v4 vault, and the `admin::ID` Squads v3
multisig read off the live CLMM Anchor IDL) are each resolved independently,
and the final score is the componentwise min() across both paths per
METHODOLOGY.md 6.2.

This file does NOT re-test `_score_full_power_path`'s own formula
correctness (already covered by test_drift_protocol.py,
test_switchboard_on_demand.py and test_solend_governance.py) -- it uses that
helper only as a fixture-building tool (to get realistic, internally
consistent (admin, multisig, timelock) triples) and to compute expected
values the same way the repo's own TestSolendDaoGovernanceComposite does.

Following the pattern in test_drift_protocol.py / test_switchboard_on_demand.py:
`sol_read.read_program` / `sol_read.read_anchor_idl` are monkeypatched
directly on the loaded scorers module's own `sol_read` reference
(`solana.sol_read.*`, restored in a finally block). Additionally -- since
this function's OWN orchestration is what's under test, not
`_resolve_squads_v4`/`_resolve_squads_v3`'s byte-level PDA-matching logic
(which has no dedicated coverage of its own yet, but is a pure "offline PDA
re-derive and compare" helper, not this function's job to verify) -- those
two module-level helpers are monkeypatched directly too
(`solana._resolve_squads_v4` / `solana._resolve_squads_v3`), exactly as the
task notes suggest is simpler than faking their own `sol_read` dependencies
(`read_squads_vault`, `read_squads`, `read_squadsv3`). Because Python
resolves a module-level function's global names against that module's own
`__dict__` at call time, patching `solana._resolve_squads_v4` this way is
visible to `score_raydium` exactly the same way patching `solana.sol_read.*`
is -- the same mechanism used throughout this test suite.
"""
import contextlib
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


solana = _load_module("aro_test_solana_scorers_raydium", "chains/solana/scorers.py")

# The three real program ids score_raydium reads, copied verbatim from its
# own source (chains/solana/scorers.py::score_raydium) so the divergence
# test exercises the real call sites rather than made-up addresses.
RAYDIUM_AMM_V4 = "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8"
RAYDIUM_CLMM = "CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK"
RAYDIUM_CPMM = "CPMMoo8L3F4NbTegBCKVNunggL7H1ZpdTHKxQB5qKP1C"

SHARED_UPGRADE_AUTHORITY = "SharedUpgradeAuthorityPda1111111111111111111"


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------

def _read_program_same_authority(url, pk):
    # All three Raydium programs (AMM v4 / CLMM / CPMM) report the SAME
    # upgrade authority -- the non-divergent case every other test needs
    # just to get past score_raydium's own abort guard.
    return {"upgrade_authority": SHARED_UPGRADE_AUTHORITY}


def _read_program_diverging(url, pk):
    # The three real program ids are distinct, so keying the (fake)
    # upgrade_authority off `pk` itself guarantees three different values
    # without needing to know or guess any real on-chain authority.
    return {"upgrade_authority": f"authority-of-{pk}"}


def _idl_with_admin_id(admin_id):
    def fake(url, pk):
        return {"hardcoded_addresses": [
            {"instruction": "update_amm_config", "account": "owner", "address": admin_id},
        ]}
    return fake


def _idl_without_admin_id(url, pk):
    # No entry for (update_amm_config, owner) at all -- score_raydium's own
    # `.get(...)` must come back None, same as a live IDL that doesn't
    # expose the hardcoded admin::ID constant.
    return {"hardcoded_addresses": []}


def _idl_account_missing(url, pk):
    # sol_read.read_anchor_idl's own real return value (FIXED 2026-09-25)
    # when the on-chain IDL account itself doesn't exist at all -- a
    # DIFFERENT failure mode than "exists but has no admin::ID entry"
    # above: this one used to crash score_raydium with a TypeError on
    # `idl["hardcoded_addresses"]` before the fix, skipping the whole
    # scorer instead of degrading path B like every other unreadable case.
    return None


def _resolve_v4_returning(value):
    def fake(url, label, authority, ms_candidate, notes, none_means_renounced=False):
        return value
    return fake


def _resolve_v3_returning(value):
    def fake(url, label, authority, ms_candidate, notes, authority_index=1):
        return value
    return fake


def _never_called(name):
    def fake(*args, **kwargs):
        raise AssertionError(f"{name} should not be called on this path")
    return fake


def _squads_v4(threshold, n_members, delay_s=0):
    # Shape returned by the real sol_read.read_squads() / _resolve_squads_v4:
    # score_raydium reads ["threshold"], ["time_lock_s"], and
    # _voters_with_vote_permission() reads ["member_list"][i]["mask"].
    # mask=7 (Initiate|Vote|Execute) so every member counts as a voter.
    return {
        "threshold": threshold, "time_lock_s": delay_s, "members": n_members,
        "member_list": [{"key": f"v4-member-{i}", "mask": 7} for i in range(n_members)],
    }


def _squads_v3(threshold, n_keys):
    # Shape returned by the real sol_read.read_squadsv3() / _resolve_squads_v3:
    # score_raydium reads ["threshold"] and ["n_keys"], and unions ["keys"]
    # into _signers.
    return {"threshold": threshold, "n_keys": n_keys, "keys": [f"v3-key-{i}" for i in range(n_keys)]}


@contextlib.contextmanager
def _patched(read_program=None, read_anchor_idl=None, resolve_v4=None, resolve_v3=None):
    origs = (
        solana.sol_read.read_program, solana.sol_read.read_anchor_idl,
        solana._resolve_squads_v4, solana._resolve_squads_v3,
    )
    if read_program is not None:
        solana.sol_read.read_program = read_program
    if read_anchor_idl is not None:
        solana.sol_read.read_anchor_idl = read_anchor_idl
    if resolve_v4 is not None:
        solana._resolve_squads_v4 = resolve_v4
    if resolve_v3 is not None:
        solana._resolve_squads_v3 = resolve_v3
    try:
        yield
    finally:
        (solana.sol_read.read_program, solana.sol_read.read_anchor_idl,
         solana._resolve_squads_v4, solana._resolve_squads_v3) = origs


# ---------------------------------------------------------------------------
# 1. The divergence abort guard
# ---------------------------------------------------------------------------

class TestUpgradeAuthorityDivergenceGuard(unittest.TestCase):
    """A real, deliberate 'abort rather than trust a stale same-authority
    assumption' guard (score_raydium's own docstring) -- if the three
    Raydium programs' upgrade_authority values ever disagree, the function
    must raise rather than silently scoring against just one of them."""

    def test_diverging_upgrade_authorities_raises_value_error(self):
        with _patched(
            read_program=_read_program_diverging,
            read_anchor_idl=_never_called("sol_read.read_anchor_idl"),
            resolve_v4=_never_called("_resolve_squads_v4"),
            resolve_v3=_never_called("_resolve_squads_v3"),
        ):
            with self.assertRaisesRegex(ValueError, "diverged"):
                solana.score_raydium("unused-url")

    def test_matching_upgrade_authorities_does_not_raise(self):
        # Sanity converse: the same guard must NOT fire when all three
        # programs genuinely agree (every other test in this file relies on
        # this not raising, so it gets its own explicit assertion too).
        with _patched(
            read_program=_read_program_same_authority,
            read_anchor_idl=_idl_without_admin_id,
            resolve_v4=_resolve_v4_returning(None),
            resolve_v3=_resolve_v3_returning(None),
        ):
            result = solana.score_raydium("unused-url")
        self.assertEqual(result["target"], RAYDIUM_CLMM)
        self.assertEqual(result["label"], "Raydium (AMM v4, CLMM, CPMM)")


# ---------------------------------------------------------------------------
# 2. Path A (shared program-upgrade Squads v4) sub-branches
#
# B is pinned to a fixed, strong Squads v3 (5-of-5 -> (60, 100, 0)) in all
# three of these so each of path A's three sub-branches (resolved normally /
# unresolved-None / RENOUNCED) produces a numerically DISTINCT final
# composite instead of being masked by min() -- see module docstring.
# ---------------------------------------------------------------------------

B_STRONG = _squads_v3(5, 5)  # -> (60, 100, 0), confirmed against _score_full_power_path directly


class TestSharedUpgradeSquadsV4Resolution(unittest.TestCase):
    def test_normal_resolution_feeds_path_a_into_the_combination(self):
        # A: squads_v4 3-of-4, delay=0 -> (50, 75, 0) (weaker than B_STRONG
        # on both adminKey and multisig) -- final result must equal A's own
        # numbers, and _signers must include BOTH paths' members (the union
        # score_raydium builds via `signers |= ...`).
        with _patched(
            read_program=_read_program_same_authority,
            read_anchor_idl=_idl_with_admin_id("admin-id-const"),
            resolve_v4=_resolve_v4_returning(_squads_v4(3, 4, delay_s=0)),
            resolve_v3=_resolve_v3_returning(B_STRONG),
        ):
            result = solana.score_raydium("unused-url")
        self.assertEqual((result["adminKeyScore"], result["multisigScore"], result["timelockScore"]), (50, 75, 0))
        self.assertIn("v4-member-0", result["_signers"])
        self.assertIn("v3-key-0", result["_signers"])
        self.assertTrue(any("shared program upgrade Squads v4: 3-of-4" in n for n in result["notes"]))

    def test_unresolved_mismatch_degrades_path_a_to_20_20_0(self):
        # _resolve_squads_v4 returning None means the offline PDA
        # re-derivation did NOT match the hardcoded multisig candidate --
        # score_raydium's own documented degrade, not a crash.
        with _patched(
            read_program=_read_program_same_authority,
            read_anchor_idl=_idl_with_admin_id("admin-id-const"),
            resolve_v4=_resolve_v4_returning(None),
            resolve_v3=_resolve_v3_returning(B_STRONG),
        ):
            result = solana.score_raydium("unused-url")
        # B_STRONG=(60,100,0) does not mask a degraded A=(20,20,0): min gives A.
        self.assertEqual((result["adminKeyScore"], result["multisigScore"], result["timelockScore"]), (20, 20, 0))

    def test_renounced_upgrade_authority_scores_full_power_none_not_degraded(self):
        # FIXED 2026-09-17 bug class (see score_drift_protocol's own
        # regression test in test_drift_protocol.py): a renounced (None)
        # upgrade authority is the SAFEST band (100/100/100), and must NOT
        # be scored as a mismatch. Distinguished numerically from the
        # unresolved-None case above because here A=(100,100,100) no longer
        # limits the min() at all -- the final adminKeyScore equals
        # B_STRONG's own 60, not the degraded-path's 20.
        with _patched(
            read_program=_read_program_same_authority,
            read_anchor_idl=_idl_with_admin_id("admin-id-const"),
            resolve_v4=_resolve_v4_returning(solana.RENOUNCED),
            resolve_v3=_resolve_v3_returning(B_STRONG),
        ):
            result = solana.score_raydium("unused-url")
        self.assertEqual((result["adminKeyScore"], result["multisigScore"], result["timelockScore"]), (60, 100, 0))


# ---------------------------------------------------------------------------
# 3. Path B (admin::ID Squads v3) sub-branches
#
# A is pinned to a fixed, strong Squads v4 (5-of-5, delay=0 -> (60, 100, 0))
# so path B's own sub-branches show through the min() the same way.
# ---------------------------------------------------------------------------

A_STRONG = _squads_v4(5, 5, delay_s=0)  # -> (60, 100, 0)


class TestAdminIdSquadsV3Resolution(unittest.TestCase):
    def test_admin_id_found_and_resolved_feeds_path_b_into_the_combination(self):
        # B: squads_v3 2-of-3 -> (45, 57, 0), weaker than A_STRONG on both
        # adminKey and multisig -- final result must equal B's own numbers.
        with _patched(
            read_program=_read_program_same_authority,
            read_anchor_idl=_idl_with_admin_id("admin-id-const"),
            resolve_v4=_resolve_v4_returning(A_STRONG),
            resolve_v3=_resolve_v3_returning(_squads_v3(2, 3)),
        ):
            result = solana.score_raydium("unused-url")
        self.assertEqual((result["adminKeyScore"], result["multisigScore"], result["timelockScore"]), (45, 57, 0))
        self.assertIn("v3-key-0", result["_signers"])
        self.assertTrue(any("admin::ID Squads v3: 2-of-3" in n for n in result["notes"]))

    def test_admin_id_missing_from_live_idl_degrades_path_b_to_20_20_0(self):
        # The live on-chain Anchor IDL simply doesn't expose the hardcoded
        # admin::ID constant this run -- score_raydium must degrade rather
        # than trust a stale citation, and must say so in its own notes
        # (distinguishing this from the "found but didn't match" case below).
        with _patched(
            read_program=_read_program_same_authority,
            read_anchor_idl=_idl_without_admin_id,
            resolve_v4=_resolve_v4_returning(A_STRONG),
            resolve_v3=_never_called("_resolve_squads_v3"),
        ):
            result = solana.score_raydium("unused-url")
        self.assertEqual((result["adminKeyScore"], result["multisigScore"], result["timelockScore"]), (20, 20, 0))
        self.assertTrue(any("admin::ID not found in the live on-chain IDL this run" in n for n in result["notes"]))

    def test_idl_account_itself_missing_degrades_path_b_to_20_20_0_not_a_crash(self):
        # FIXED 2026-09-25 regression: read_anchor_idl returning None (no
        # on-chain IDL account at all, reproduced live against CLMM's real
        # derived PDA on 2026-09-25) must degrade path B exactly like the
        # "IDL exists but lacks admin::ID" case, not raise a TypeError that
        # takes down the whole scorer (and silently drops Raydium from
        # score_all() every run, as it did between 2026-09-18 and today).
        with _patched(
            read_program=_read_program_same_authority,
            read_anchor_idl=_idl_account_missing,
            resolve_v4=_resolve_v4_returning(A_STRONG),
            resolve_v3=_never_called("_resolve_squads_v3"),
        ):
            result = solana.score_raydium("unused-url")
        self.assertEqual((result["adminKeyScore"], result["multisigScore"], result["timelockScore"]), (20, 20, 0))
        self.assertTrue(any("no on-chain Anchor IDL account this run" in n for n in result["notes"]))

    def test_admin_id_found_but_squads_v3_unresolved_degrades_path_b_to_20_20_0(self):
        # admin_id WAS read from the live IDL (not None), but the offline
        # Squads v3 PDA re-derivation didn't match the hardcoded candidate
        # -- a different failure mode than "not found in the IDL" above,
        # same numeric degrade, distinguished by which notes line appears.
        with _patched(
            read_program=_read_program_same_authority,
            read_anchor_idl=_idl_with_admin_id("admin-id-const"),
            resolve_v4=_resolve_v4_returning(A_STRONG),
            resolve_v3=_resolve_v3_returning(None),
        ):
            result = solana.score_raydium("unused-url")
        self.assertEqual((result["adminKeyScore"], result["multisigScore"], result["timelockScore"]), (20, 20, 0))
        self.assertFalse(any("admin::ID not found in the live on-chain IDL this run" in n for n in result["notes"]))
        self.assertTrue(any("admin-id-const" in n for n in result["notes"]))


# ---------------------------------------------------------------------------
# 4. Final combination: min() across both full-power paths, both directions
# ---------------------------------------------------------------------------

class TestCombinedScoreIsMinAcrossBothPaths(unittest.TestCase):
    """METHODOLOGY.md 6.2's minimum-over-paths convention, worth its own
    direct test in each direction rather than only relying on the
    per-branch tests above (which always pin one side to a fixed strong
    value) -- here BOTH paths are genuinely live/resolved and score_raydium
    itself must pick the weaker one on every one of the three dimensions."""

    def test_path_a_weaker_wins_the_combination(self):
        # A: squads_v4 threshold=1 -> (5, 0, 0) (any single signer decisive,
        # regardless of voters/delay -- METHODOLOGY.md's own threshold=1
        # short-circuit). B: squads_v3 3-of-3 -> (50, 85, 0), clearly
        # stronger on every dimension.
        with _patched(
            read_program=_read_program_same_authority,
            read_anchor_idl=_idl_with_admin_id("admin-id-const"),
            resolve_v4=_resolve_v4_returning(_squads_v4(1, 4, delay_s=0)),
            resolve_v3=_resolve_v3_returning(_squads_v3(3, 3)),
        ):
            result = solana.score_raydium("unused-url")
        self.assertEqual((result["adminKeyScore"], result["multisigScore"], result["timelockScore"]), (5, 0, 0))
        self.assertEqual(result["compositeScore"], solana._composite(5, 0, 0))

    def test_path_b_weaker_wins_the_combination(self):
        # A: squads_v4 4-of-4, delay=0 -> (55, 100, 0), clearly stronger.
        # B: squads_v3 threshold=1 -> (5, 0, 0) -- the weaker path this time,
        # confirming score_raydium takes the min per-dimension regardless of
        # which named path (A or B) happens to be weaker.
        with _patched(
            read_program=_read_program_same_authority,
            read_anchor_idl=_idl_with_admin_id("admin-id-const"),
            resolve_v4=_resolve_v4_returning(_squads_v4(4, 4, delay_s=0)),
            resolve_v3=_resolve_v3_returning(_squads_v3(1, 5)),
        ):
            result = solana.score_raydium("unused-url")
        self.assertEqual((result["adminKeyScore"], result["multisigScore"], result["timelockScore"]), (5, 0, 0))
        self.assertEqual(result["compositeScore"], solana._composite(5, 0, 0))


if __name__ == "__main__":
    unittest.main()
