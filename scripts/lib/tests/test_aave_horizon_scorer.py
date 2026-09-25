"""
Unit tests for chains/ethereum-l1/scorers.py::score_aave_v3_horizon_pool (Aave V3 Horizon, the RWA
instance on Ethereum), with every chain read patched.

FIXTURE PROVENANCE
------------------
  READ     a value read on Ethereum mainnet on 2026-09-20 on two RPCs (publicnode and drpc): the provider's
           owner() and getACLAdmin() are the governance Executor 0x5300A1a1..., hasRole(POOL_ADMIN) and
           hasRole(EMERGENCY_ADMIN) are true for the Safe 0x13B57382... (4-of-6, six owners, Safe v1.4.1,
           no module), hasRole(RISK_ADMIN) is true for the Safe 0xE6ec1f0A... (3-of-4), and three of the
           four risk-Safe owners are also owners of the 4-of-6. The verified PoolConfigurator source
           (0x898E245D...) puts updateAToken, updateVariableDebtToken, dropReserve and setReserveActive
           behind onlyPoolAdmin, and UpdateATokenInput carries a caller-supplied `implementation`.
  HAND     arithmetic from the written rule, with the working next to it: the Ethereum L1 Safe rule used by
           score_morpho_blue_l1 (adminKeyScore 65 for a threshold of 3 or more, 50 for 2, 10 otherwise;
           multisigScore = min(100, 15t + 5(n - t)); timelockScore 0) and
           composite = floor(0.4a + 0.3m + 0.3t + 0.5) = (4a + 3m + 3t + 5) // 10.
  PROBE    an invented state (a 2-of-3, a 1-of-3, a 6-of-6, a different root, a revoked role). The expected
           value is hand arithmetic, and the test says PROBE.
  CHARACTERISATION  what the scorer does today where no written policy decides it.

HONEST LIMIT: the live values in READ are the same reads the scorer makes, so the happy-path row is a
regression anchor, not an independent oracle. The independent parts are the role hashes (recomputed here
with keccak, and equal to the values `cast keccak` printed) and the hand arithmetic.
"""
import os
import sys
import unittest
from fractions import Fraction

from web3 import Web3 as RealWeb3

sys.path.insert(0, os.path.dirname(__file__))
from test_ethereum_l1_scorers import FakeHelpers, FakeW3, _patch_helpers, scorers  # noqa: E402

cs = RealWeb3.to_checksum_address
PROVIDER = cs("0x5D39E06b825C1F2B80bf2756a73e28eFAA128ba0")
ACL = cs("0xEFD5df7b87d2dCe6DD454b4240b3e0A4db562321")
ADMIN_SAFE = cs("0x13B57382c36BAB566E75C72303622AF29E27e1d3")
RISK_SAFE = cs("0xE6ec1f0Ae6Cd023bd0a9B4d0253BDC755103253c")
EXECUTOR = cs("0x5300A1a15135EA4dc7aD5a167152C01EFc9b192A")
SENTINEL = "0x0000000000000000000000000000000000000001"

SHARED = ["0xb647055a9915bf9c8021a684e175a353525b9890", "0x2fe367d6f8a755ca22efae7f29004f9b5fa868e8",
          "0x606dc57cd166643760e049609bfd1d8a698d3bac"]
ADMIN_OWNERS = [cs(a) for a in ["0xbf113fa52454a94185b65e6f2e818b7f178f937a", "0xfea7688ff78a4913e80836a097d133ae78bc31e7",
                                 *SHARED, "0x75c26ed4d9c5d331665766394d933e12f8597a55"]]
RISK_OWNERS = [cs(a) for a in [*SHARED, "0x2ed1df8f475b1f9c7493fc0eb0bfd4d1fd17f27b"]]


def _role(name):
    return bytes(RealWeb3.keccak(text=name))


def _hand_composite(a, m, t):
    return int(Fraction(4 * a + 3 * m + 3 * t + 5, 10))  # exact rational, floor


DEFAULT_ADMIN_ROLE = b"\x00" * 32  # bytes32(0), OZ convention -- NOT keccak(text="DEFAULT_ADMIN_ROLE")


class _Base(unittest.TestCase):
    def _run(self, owner=EXECUTOR, acl_admin=EXECUTOR, pool_admin=True, emergency=True, risk=True,
             admin_safe=(ADMIN_OWNERS, 4), risk_safe=(RISK_OWNERS, 3), modules=([], SENTINEL), pool_admin_raises=False,
             default_admin=True):
        fake = FakeHelpers()
        fake.call_raw_results[(PROVIDER, "owner", ())] = owner
        fake.call_raw_results[(PROVIDER, "getACLAdmin", ())] = acl_admin
        fake.call_raw_results[(ACL, "hasRole", (_role("POOL_ADMIN"), ADMIN_SAFE))] = pool_admin
        fake.call_raw_results[(ACL, "hasRole", (_role("EMERGENCY_ADMIN"), ADMIN_SAFE))] = emergency
        fake.call_raw_results[(ACL, "hasRole", (_role("RISK_ADMIN"), RISK_SAFE))] = risk
        fake.call_raw_results[(ACL, "hasRole", (DEFAULT_ADMIN_ROLE, EXECUTOR))] = default_admin
        fake.call_raw_results[(ADMIN_SAFE, "getModulesPaginated", (SENTINEL, 10))] = modules
        if admin_safe is not None:
            fake.safe_results[ADMIN_SAFE] = admin_safe
        if risk_safe is not None:
            fake.safe_results[RISK_SAFE] = risk_safe
        _patch_helpers(self, fake)
        self.fake = fake
        return scorers.score_aave_v3_horizon_pool(FakeW3())


class TestRoleHashes(unittest.TestCase):
    def test_role_hashes_match_the_values_cast_keccak_printed(self):
        # PROVENANCE: `cast keccak POOL_ADMIN` etc., run separately on 2026-09-20.
        self.assertEqual(scorers._acl_role("POOL_ADMIN").hex(), "12ad05bde78c5ab75238ce885307f96ecd482bb402ef831f99e7018a0f169b7b")
        self.assertEqual(scorers._acl_role("EMERGENCY_ADMIN").hex(), "5c91514091af31f62f596a314af7d5be40146b2f2355969392f055e12e0982fb")
        self.assertEqual(scorers._acl_role("RISK_ADMIN").hex(), "8aa855a911518ecfbe5bc3088c8f3dda7badf130faaf8ace33fdc33828e18167")


class TestHappyPath(_Base):
    def test_live_row_65_70_0_composite_47(self):
        r = self._run()
        # HAND: admin 65 (threshold 4 >= 3), multisig min(100, 4*15 + 2*5) = 70, timelock 0, composite (260 + 210 + 0 + 5) // 10 = 47
        self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["timelockScore"], r["oracleAuthorityScore"]), (65, 70, 0, 100))
        self.assertEqual(r["compositeScore"], 47)
        self.assertEqual(r["compositeScore"], _hand_composite(65, 70, 0))

    def test_identity_and_root_group(self):
        r = self._run()
        self.assertEqual(r["target"], PROVIDER)
        self.assertEqual(r["label"], "Aave V3 Horizon Pool (PoolAddressesProvider)")
        self.assertEqual(r["_rootGroup"], "aave-l1-governance")
        self.assertNotIn("_crossEcosystem", r)  # no committee known on another chain

    def test_notes_carry_the_disclosed_limits(self):
        notes = " | ".join(self._run()["notes"])
        for needle in ("4-of-6", "POOL_ADMIN", "full-power path", "no module enabled", "3-of-4", "not scored", "0x09e8E140", "GHO direct minter", "3 signer(s) sit in both"):
            self.assertIn(needle, notes)

    def test_shares_its_root_with_the_main_pool_and_moves_no_other_score(self):
        # CHARACTERISATION: same _rootGroup as the main Aave pool, so the repo-wide formula 100 - 20 x others gives both 80.
        horizon = self._run()
        main = {"label": "main", "_rootGroup": "aave-l1-governance", "notes": []}
        other = {"label": "other", "_rootGroup": "x", "notes": []}
        scorers._apply_cross_exposure([horizon, main, other])
        self.assertEqual((horizon["crossExposureScore"], main["crossExposureScore"], other["crossExposureScore"]), (80, 80, 100))
        self.assertNotIn("_rootGroup", horizon)


class TestThresholdRule(_Base):
    def _score(self, t, n):
        owners = [cs("0x" + hex(i)[2:].zfill(40)) for i in range(1, n + 1)]
        r = self._run(admin_safe=(owners, t))
        return r["adminKeyScore"], r["multisigScore"], r["timelockScore"], r["compositeScore"]

    def test_probe_two_of_three(self):
        # PROBE, HAND: admin 50, multisig min(100, 30 + 5) = 35, composite (200 + 105 + 0 + 5) // 10 = 31
        self.assertEqual(self._score(2, 3), (50, 35, 0, 31))

    def test_probe_one_of_three(self):
        # PROBE, HAND: admin 10, multisig 15 + 10 = 25, composite (40 + 75 + 5) // 10 = 12
        self.assertEqual(self._score(1, 3), (10, 25, 0, 12))

    def test_probe_three_of_three_and_six_of_six(self):
        # PROBE, HAND: 3-of-3 -> 65 / 45 / 0 -> (260 + 135 + 5) // 10 = 40 ; 6-of-6 -> 65 / 90 / 0 -> (260 + 270 + 5) // 10 = 53
        self.assertEqual(self._score(3, 3), (65, 45, 0, 40))
        self.assertEqual(self._score(6, 6), (65, 90, 0, 53))

    def test_multisig_is_capped_at_100(self):
        # PROBE, HAND: 8-of-9 -> 120 + 5 = 125 -> capped at 100
        self.assertEqual(self._score(8, 9)[1], 100)

    def test_every_composite_matches_exact_rational_arithmetic(self):
        for t, n in ((1, 3), (2, 3), (3, 3), (4, 6), (6, 6)):
            a, m, tl, c = self._score(t, n)
            self.assertEqual(c, _hand_composite(a, m, tl))


class TestDriftRaises(_Base):
    def test_owner_is_no_longer_the_executor(self):
        with self.assertRaisesRegex(RuntimeError, r"root changed: PoolAddressesProvider\.owner\(\)"):
            self._run(owner=cs("0x" + "ab" * 20))

    def test_acl_admin_is_no_longer_the_executor(self):
        with self.assertRaisesRegex(RuntimeError, r"root changed: PoolAddressesProvider\.getACLAdmin\(\)"):
            self._run(acl_admin=cs("0x" + "cd" * 20))

    def test_admin_safe_lost_pool_admin(self):
        with self.assertRaisesRegex(RuntimeError, "no longer holds POOL_ADMIN"):
            self._run(pool_admin=False)

    def test_lowercase_executor_is_still_the_executor(self):
        # PROBE: address comparison is case-insensitive
        r = self._run(owner=EXECUTOR.lower(), acl_admin=EXECUTOR.lower())
        self.assertEqual(r["compositeScore"], 47)

    def test_safe_score_skips_a_drifted_target_instead_of_publishing_it(self):
        fake = FakeHelpers()
        fake.call_raw_results[(PROVIDER, "owner", ())] = cs("0x" + "ab" * 20)
        _patch_helpers(self, fake)
        self.assertEqual(scorers.safe_score("score_aave_v3_horizon_pool", scorers.score_aave_v3_horizon_pool, FakeW3()), [])


class TestDegradesToTheFloor(_Base):
    def _floor(self, r):
        self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["timelockScore"]), (20, 0, 0))
        self.assertEqual(r["compositeScore"], _hand_composite(20, 0, 0))  # (80 + 5) // 10 = 8
        self.assertTrue(any("unresolved" in n for n in r["notes"]))

    def test_owner_unread(self):
        self._floor(self._run(owner=None))

    def test_acl_admin_unread(self):
        self._floor(self._run(acl_admin=None))

    def test_pool_admin_unread(self):
        self._floor(self._run(pool_admin=None))

    def test_admin_safe_not_resolvable(self):
        self._floor(self._run(admin_safe=None))

    def test_two_rpcs_disagreeing_on_pool_admin_degrades_and_says_so(self):
        fake = FakeHelpers()
        fake.call_raw_results[(PROVIDER, "owner", ())] = EXECUTOR
        fake.call_raw_results[(PROVIDER, "getACLAdmin", ())] = EXECUTOR
        fake.safe_results[ADMIN_SAFE] = (ADMIN_OWNERS, 4)
        fake.cross_checked_raises = RuntimeError("RPC disagreement")
        _patch_helpers(self, fake)
        r = scorers.score_aave_v3_horizon_pool(FakeW3())
        self._floor(r)
        self.assertTrue(any("cross-RPC check FAILED" in n for n in r["notes"]))


class TestRiskSafeAndModules(_Base):
    def test_three_shared_signers_can_act_as_the_risk_safe(self):
        notes = " | ".join(self._run()["notes"])
        self.assertIn("those signers alone can act as the risk Safe", notes)

    def test_two_shared_signers_cannot(self):
        risk_owners = [ADMIN_OWNERS[0], ADMIN_OWNERS[1], cs("0x" + "11" * 20), cs("0x" + "22" * 20)]
        notes = " | ".join(self._run(risk_safe=(risk_owners, 3))["notes"])
        self.assertIn("2 signer(s) sit in both", notes)
        self.assertIn("they cannot act alone as the risk Safe", notes)

    def test_risk_safe_unread_is_disclosed_and_does_not_change_the_score(self):
        r = self._run(risk_safe=None)
        self.assertEqual(r["compositeScore"], 47)
        self.assertTrue(any("RISK_ADMIN Safe getOwners()/getThreshold() unread" in n for n in r["notes"]))

    def test_module_present_leaves_timelock_at_zero_and_says_it_is_unresolved(self):
        r = self._run(modules=([cs("0x" + "77" * 20)], SENTINEL))
        self.assertEqual(r["timelockScore"], 0)
        self.assertTrue(any("1 module(s) enabled" in n and "timelockScore stays 0" in n for n in r["notes"]))

    def test_modules_unread_leaves_timelock_at_zero(self):
        r = self._run(modules=None)
        self.assertEqual(r["timelockScore"], 0)
        self.assertTrue(any("modules unread" in n for n in r["notes"]))


class TestLiveRoleHolderReplay(_Base):
    """ADDED 2026-09-22, closes the backlog item's own "[backlog note]
    pas vu" limitation: score_aave_v3_horizon_pool() now also replays the ACLManager's full
    RoleGranted/RoleRevoked history via Tenderly (scripts/lib/scorers.py's _replay_role_holders(),
    already proven live against Ethereum mainnet by score_rollup_l1_authority() in that same file),
    not just hasRole on the two already-known Safes. FakeHelpers.replay_role_holders_result/_raises
    (test_ethereum_l1_scorers.py) control this without a live network call."""

    def _replay(self, confirm_extras=True, extra_confirmations=None, **overrides):
        # confirm_extras=True (default): every "extra" address (present in an override set but not in
        # the corresponding KNOWN set) is auto-confirmed by hasRole -- matches every existing test's
        # intent (an extra IS a real, confirmed holder) without each of them having to set up that
        # fixture by hand. extra_confirmations={addr: True/False/None} overrides individual addresses
        # -- False simulates a phantom (replay says granted, hasRole says no longer held -- a grant
        # this scan's window caught without also catching its later revoke), None simulates hasRole
        # itself failing to resolve for that specific address.
        known_pool_emergency = set(scorers._HORIZON_KNOWN_POOL_EMERGENCY_ADMIN)
        known_risk = set(scorers._HORIZON_KNOWN_RISK_ADMIN)
        known_listing = set(scorers._HORIZON_KNOWN_ASSET_LISTING_ADMIN)
        role_sets = {
            "POOL_ADMIN": (set(overrides.get("pool", known_pool_emergency)), known_pool_emergency),
            "EMERGENCY_ADMIN": (set(overrides.get("emergency", known_pool_emergency)), known_pool_emergency),
            "RISK_ADMIN": (set(overrides.get("risk", known_risk)), known_risk),
            "ASSET_LISTING_ADMIN": (set(overrides.get("listing", known_listing)), known_listing),
        }
        result = {role: replayed for role, (replayed, known) in role_sets.items()}
        fake = FakeHelpers()
        fake.call_raw_results[(PROVIDER, "owner", ())] = EXECUTOR
        fake.call_raw_results[(PROVIDER, "getACLAdmin", ())] = EXECUTOR
        fake.call_raw_results[(ACL, "hasRole", (_role("POOL_ADMIN"), ADMIN_SAFE))] = True
        fake.call_raw_results[(ACL, "hasRole", (_role("EMERGENCY_ADMIN"), ADMIN_SAFE))] = True
        fake.call_raw_results[(ACL, "hasRole", (_role("RISK_ADMIN"), RISK_SAFE))] = True
        fake.call_raw_results[(ACL, "hasRole", (DEFAULT_ADMIN_ROLE, EXECUTOR))] = True
        fake.call_raw_results[(ADMIN_SAFE, "getModulesPaginated", (SENTINEL, 10))] = ([], SENTINEL)
        fake.safe_results[ADMIN_SAFE] = (ADMIN_OWNERS, 4)
        fake.safe_results[RISK_SAFE] = (RISK_OWNERS, 3)
        fake.replay_role_holders_result = result
        extra_confirmations = extra_confirmations or {}
        for role, (replayed, known) in role_sets.items():
            for addr in replayed - known:
                value = extra_confirmations[addr] if addr in extra_confirmations else (True if confirm_extras else None)
                fake.call_raw_results[(ACL, "hasRole", (_role(role), cs(addr)))] = value
        _patch_helpers(self, fake)
        return fake

    def test_matching_known_set_adds_an_honest_not_a_certifying_note_and_does_not_change_the_score(self):
        # REDESIGNED 2026-09-22 after a second live-reproduced rejection (#189) of a positive-control
        # attempt at proving the replay complete: this scorer no longer ever claims "no undisclosed
        # holder EXISTS" (a completeness claim), only "no undisclosed holder was found in what was
        # scanned" (a plain report) -- see the block's own comment in chains/ethereum-l1/scorers.py.
        self._replay()
        r = scorers.score_aave_v3_horizon_pool(FakeW3())
        self.assertEqual(r["compositeScore"], 47)
        notes = " | ".join(r["notes"])
        self.assertIn("found no POOL_ADMIN/EMERGENCY_ADMIN/RISK_ADMIN/ASSET_LISTING_ADMIN holder beyond the known set in what it scanned", notes)
        self.assertIn("NOT a certification that none exists", notes)

    def test_an_undisclosed_pool_admin_holder_raises(self):
        extra = cs("0x" + "ee" * 20)
        self._replay(pool={*scorers._HORIZON_KNOWN_POOL_EMERGENCY_ADMIN, extra.lower()})
        with self.assertRaisesRegex(RuntimeError, "POOL_ADMIN/EMERGENCY_ADMIN holder outside the known set"):
            scorers.score_aave_v3_horizon_pool(FakeW3())

    def test_an_undisclosed_emergency_admin_holder_raises(self):
        extra = cs("0x" + "ff" * 20)
        self._replay(emergency={*scorers._HORIZON_KNOWN_POOL_EMERGENCY_ADMIN, extra.lower()})
        with self.assertRaisesRegex(RuntimeError, "POOL_ADMIN/EMERGENCY_ADMIN holder outside the known set"):
            scorers.score_aave_v3_horizon_pool(FakeW3())

    def test_an_undisclosed_pool_admin_holder_makes_safe_score_skip_the_target(self):
        extra = cs("0x" + "ee" * 20)
        self._replay(pool={*scorers._HORIZON_KNOWN_POOL_EMERGENCY_ADMIN, extra.lower()})
        self.assertEqual(scorers.safe_score("score_aave_v3_horizon_pool", scorers.score_aave_v3_horizon_pool, FakeW3()), [])

    def test_an_undisclosed_risk_admin_holder_is_a_note_only_score_unaffected(self):
        extra = cs("0x" + "11" * 20)
        self._replay(risk={*scorers._HORIZON_KNOWN_RISK_ADMIN, extra.lower()})
        r = scorers.score_aave_v3_horizon_pool(FakeW3())
        self.assertEqual(r["compositeScore"], 47)  # bounded role, not scored -- unaffected
        self.assertTrue(any("RISK_ADMIN/ASSET_LISTING_ADMIN holder outside the known" in n for n in r["notes"]))
        self.assertTrue(any(extra in n for n in r["notes"]))

    def test_an_undisclosed_asset_listing_admin_holder_is_a_note_only_score_unaffected(self):
        extra = cs("0x" + "22" * 20)
        self._replay(listing={*scorers._HORIZON_KNOWN_ASSET_LISTING_ADMIN, extra.lower()})
        r = scorers.score_aave_v3_horizon_pool(FakeW3())
        self.assertEqual(r["compositeScore"], 47)
        self.assertTrue(any("RISK_ADMIN/ASSET_LISTING_ADMIN holder outside the known" in n for n in r["notes"]))

    def test_replay_failure_degrades_to_an_honest_note_not_a_crash_and_does_not_change_the_score(self):
        fake = self._replay()
        fake.replay_role_holders_raises = RuntimeError("['POOL_ADMIN'] log fetch failed after 4 attempts: boom")
        r = scorers.score_aave_v3_horizon_pool(FakeW3())
        self.assertEqual(r["compositeScore"], 47)  # the known-holder hasRole checks alone still give the same score
        self.assertTrue(any("Live role-holder discovery" in n and "FAILED this run" in n for n in r["notes"]))
        self.assertTrue(any("cannot say whether an undisclosed holder exists this run" in n for n in r["notes"]))

    def test_a_missing_role_key_in_the_replay_result_fails_loud_not_silently(self):
        # PROBE, CHARACTERISATION: the scorer indexes live_holders[role] directly (no .get()), so a
        # hypothetical future _replay_role_holders change that drops a role key this scorer asks for
        # raises KeyError -- a loud crash score_all()'s own safe_score() wrapper catches and skips
        # the target, not a silent "0 holders" read as "nothing new found". Documents the actual,
        # current behavior rather than assuming an untested softer one.
        fake = self._replay()
        fake.replay_role_holders_result = {"POOL_ADMIN": set(scorers._HORIZON_KNOWN_POOL_EMERGENCY_ADMIN)}
        with self.assertRaises(KeyError):
            scorers.score_aave_v3_horizon_pool(FakeW3())

    def test_an_empty_replay_never_claims_undisclosed_holders_dont_exist(self):
        # THE core regression this class exists to lock in, across TWO rejections of two different
        # positive-control designs (#187, then #189 finding the first control's own witness -- hasRole
        # -- could independently fail and vacuously bypass it, live-reproduced against real mainnet
        # both times): an empty (or partial) replay result -- a wrong/renamed role name, a too-late
        # start block, a gateway silently serving a short or truncated window, hasRole itself failing
        # -- must NEVER be reported as "no undisclosed holder EXISTS". Only ever "none found in what
        # was scanned". No amount of hasRole cross-checking closes this: the fix instead never makes
        # the stronger claim at all. See the block's own comment in chains/ethereum-l1/scorers.py.
        self._replay(pool=set(), emergency=set(), risk=set(), listing=set())
        r = scorers.score_aave_v3_horizon_pool(FakeW3())
        self.assertEqual(r["compositeScore"], 47)  # hasRole alone still gives the same, correct score
        notes = " | ".join(r["notes"])
        self.assertIn("found no POOL_ADMIN/EMERGENCY_ADMIN/RISK_ADMIN/ASSET_LISTING_ADMIN holder beyond the known set in what it scanned", notes)
        self.assertIn("NOT a certification that none exists", notes)

    def test_the_same_honest_note_fires_even_when_hasrole_itself_also_failed(self):
        # THE exact #189 exploit: the previous (rejected) positive control was conditioned on
        # pool_admin/emergency_admin/risk_admin being `is True` -- if hasRole's own cross-RPC check
        # failed (both public RPCs disagreeing/rate-limited, a routine, already-tested failure mode
        # elsewhere in this file), all three became None, the control's guards never fired, and the
        # vacuous "matches exactly" note was republished on a run where NOTHING was verified at all.
        # This redesign has no such conditional path -- the honest note is unconditional on whether
        # the replay itself succeeded, entirely independent of hasRole's own outcome.
        fake = self._replay()
        original_cross_checked = scorers.cross_checked

        def _always_fail(rpc_urls, fn, *args):
            raise RuntimeError("both public RPCs rate-limited (simulated)")

        scorers.cross_checked = _always_fail
        self.addCleanup(lambda: setattr(scorers, "cross_checked", original_cross_checked))
        r = scorers.score_aave_v3_horizon_pool(FakeW3())
        self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["timelockScore"]), (20, 0, 0))  # hasRole unresolved -> floor, as before this feature existed
        notes = " | ".join(r["notes"])
        self.assertIn("found no POOL_ADMIN/EMERGENCY_ADMIN/RISK_ADMIN/ASSET_LISTING_ADMIN holder beyond the known set in what it scanned", notes)
        self.assertIn("NOT a certification that none exists", notes)
        self.assertNotIn("matches the known, disclosed holder set exactly", notes)
        self.assertNotIn("reproduces every hasRole-confirmed holder", notes)

    def test_a_full_matching_replay_still_reports_what_it_found(self):
        # CHARACTERISATION, guards against the fix over-correcting: the happy path (already covered by
        # test_matching_known_set_adds_an_honest_not_a_certifying_note_and_does_not_change_the_score)
        # must still reach the reporting note when the replay genuinely agrees with hasRole on every
        # point -- the redesign removes the CERTIFYING claim, not the reporting of a clean scan.
        self._replay()
        r = scorers.score_aave_v3_horizon_pool(FakeW3())
        notes = " | ".join(r["notes"])
        self.assertIn("found no POOL_ADMIN/EMERGENCY_ADMIN/RISK_ADMIN/ASSET_LISTING_ADMIN holder beyond the known set in what it scanned", notes)

    def test_a_phantom_pool_admin_candidate_does_not_raise_and_is_disclosed_as_unconfirmed(self):
        # THE core regression this method exists to lock in (action's live-reproduced finding,
        # the third and symmetric defect after two false-negative rejections): a raw "extra" from the
        # replay is NOT itself trustworthy -- a block range that catches a grant without also catching
        # its later revoke fabricates a phantom CURRENT holder. Confirmed live against real mainnet
        # with a real grant-then-revoke pair for this exact ACLManager. hasRole=False for the candidate
        # (the ground truth: it does not currently hold the role) must prevent the raise entirely.
        extra = cs("0x" + "77" * 20)
        self._replay(pool={*scorers._HORIZON_KNOWN_POOL_EMERGENCY_ADMIN, extra.lower()},
                     extra_confirmations={extra.lower(): False})
        r = scorers.score_aave_v3_horizon_pool(FakeW3())  # must not raise
        self.assertEqual(r["compositeScore"], 47)
        notes = " | ".join(r["notes"])
        self.assertIn("no longer confirms", notes)
        self.assertIn(extra, notes)
        self.assertNotIn("POOL_ADMIN/EMERGENCY_ADMIN holder outside the known set, confirmed live by hasRole", notes)

    def test_hasrole_itself_failing_for_a_candidate_is_also_treated_as_unconfirmed_not_raised(self):
        extra = cs("0x" + "88" * 20)
        self._replay(emergency={*scorers._HORIZON_KNOWN_POOL_EMERGENCY_ADMIN, extra.lower()},
                     extra_confirmations={extra.lower(): None})
        r = scorers.score_aave_v3_horizon_pool(FakeW3())  # must not raise
        self.assertEqual(r["compositeScore"], 47)
        self.assertTrue(any("no longer confirms" in n and extra in n for n in r["notes"]))

    def test_a_phantom_risk_admin_candidate_is_disclosed_not_treated_as_a_real_finding(self):
        extra = cs("0x" + "33" * 20)
        self._replay(risk={*scorers._HORIZON_KNOWN_RISK_ADMIN, extra.lower()},
                     extra_confirmations={extra.lower(): False})
        r = scorers.score_aave_v3_horizon_pool(FakeW3())
        self.assertEqual(r["compositeScore"], 47)
        notes = " | ".join(r["notes"])
        self.assertNotIn("RISK_ADMIN/ASSET_LISTING_ADMIN holder outside the known, disclosed set, confirmed live by hasRole", notes)
        self.assertIn("no longer confirms", notes)

    def test_a_confirmed_extra_finding_does_not_also_print_the_all_clear_note(self):
        # Closes action's secondary finding: printing the "found no ... holder beyond the known
        # set" note UNCONDITIONALLY, even in the same run as a genuine finding's own note, made the
        # two contradict each other (a reader sees the LAST one, "found no...", and misses the real
        # finding printed just above it). The two notes must now be mutually exclusive.
        extra = cs("0x" + "44" * 20)
        self._replay(risk={*scorers._HORIZON_KNOWN_RISK_ADMIN, extra.lower()})  # confirmed by default
        r = scorers.score_aave_v3_horizon_pool(FakeW3())
        notes = " | ".join(r["notes"])
        self.assertIn("RISK_ADMIN/ASSET_LISTING_ADMIN holder outside the known, disclosed set, confirmed live by hasRole", notes)
        self.assertNotIn("found no POOL_ADMIN/EMERGENCY_ADMIN/RISK_ADMIN/ASSET_LISTING_ADMIN holder beyond the known set in what it scanned", notes)

    def test_a_finding_still_carries_the_scope_disclaimer(self):
        # Closes one of action's own non-blocking approval reservations: the honesty disclaimer
        # ("NOT a certification that nothing else is undisclosed") used to live only inside the
        # "nothing found" note, so it silently vanished from a run's notes exactly when something WAS
        # found -- the case a reader most needs the reminder for.
        extra = cs("0x" + "55" * 20)
        self._replay(risk={*scorers._HORIZON_KNOWN_RISK_ADMIN, extra.lower()})
        r = scorers.score_aave_v3_horizon_pool(FakeW3())
        notes = " | ".join(r["notes"])
        self.assertIn("NOT a certification that nothing else is undisclosed", notes)

    def test_unconfirmed_candidates_are_named_per_role_not_merged_into_one_anonymous_set(self):
        # Closes the other action reservation: a POOL_ADMIN phantom and an ASSET_LISTING_ADMIN
        # phantom used to print word-for-word identical notes (only the address differed) despite very
        # different implications, because all four roles' unconfirmed candidates were merged into one
        # flat, role-less set.
        pool_phantom = cs("0x" + "66" * 20)
        listing_phantom = cs("0x" + "67" * 20)
        self._replay(
            pool={*scorers._HORIZON_KNOWN_POOL_EMERGENCY_ADMIN, pool_phantom.lower()},
            listing={*scorers._HORIZON_KNOWN_ASSET_LISTING_ADMIN, listing_phantom.lower()},
            extra_confirmations={pool_phantom.lower(): False, listing_phantom.lower(): False},
        )
        r = scorers.score_aave_v3_horizon_pool(FakeW3())
        notes = " | ".join(r["notes"])
        self.assertIn(f"POOL_ADMIN:{pool_phantom}", notes)
        self.assertIn(f"ASSET_LISTING_ADMIN:{listing_phantom}", notes)


class TestDefaultAdminRole(_Base):
    """ADDED 2026-09-22, closes the second half of action's rejection: DEFAULT_ADMIN_ROLE -- the
    role the docstring's whole "only governance grants a role" claim rests on -- is bytes32(0) by OZ
    convention, not keccak(text="DEFAULT_ADMIN_ROLE"), so _acl_role()/_replay_role_holders() can never
    check it by name. Checked directly via hasRole instead, matching score_sparklend_pool's own
    established DEFAULT_ADMIN_ROLE pattern in this same file, and now gates the scored path the same
    way pool_admin already does."""

    def test_confirmed_true_is_disclosed_and_does_not_change_the_score(self):
        r = self._run(default_admin=True)
        self.assertEqual(r["compositeScore"], 47)
        self.assertTrue(any("hasRole(DEFAULT_ADMIN_ROLE, executor) = True" in n for n in r["notes"]))

    def test_no_longer_held_by_the_executor_raises(self):
        with self.assertRaisesRegex(RuntimeError, "no longer holds DEFAULT_ADMIN_ROLE"):
            self._run(default_admin=False)

    def test_unresolved_degrades_to_the_floor(self):
        fake = FakeHelpers()
        fake.call_raw_results[(PROVIDER, "owner", ())] = EXECUTOR
        fake.call_raw_results[(PROVIDER, "getACLAdmin", ())] = EXECUTOR
        fake.call_raw_results[(ACL, "hasRole", (_role("POOL_ADMIN"), ADMIN_SAFE))] = True
        fake.safe_results[ADMIN_SAFE] = (ADMIN_OWNERS, 4)
        fake.safe_results[RISK_SAFE] = (RISK_OWNERS, 3)
        fake.cross_checked_raises = RuntimeError("RPC disagreement")
        _patch_helpers(self, fake)
        r = scorers.score_aave_v3_horizon_pool(FakeW3())
        self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["timelockScore"]), (20, 0, 0))
        self.assertTrue(any("DEFAULT_ADMIN_ROLE" in n and "unresolved" in n for n in r["notes"]))

    def test_unresolved_default_admin_alone_degrades_the_score_even_when_pool_admin_resolves(self):
        # Isolates default_admin specifically from pool_admin's own resolution -- the blanket
        # cross_checked_raises fixture above fails EVERY cross_checked call, so it can't tell "the
        # final gate needs default_admin is True" apart from "pool_admin never resolved either".
        # Found missing by mutation-testing the gate itself: removing `default_admin is True` from
        # `if root_resolved and pool_admin is True and default_admin is True and safe:` survived every
        # test above unnoticed.
        self._run(default_admin=True)  # sets every OTHER hasRole to True via _Base's own fixtures
        original_cross_checked = scorers.cross_checked  # the fake's cross_checked, already patched in by _run()

        def _fail_only_default_admin(rpc_urls, fn, *args):
            # Isolates the DEFAULT_ADMIN_ROLE check specifically -- it's the only hasRole call in this
            # scorer keyed on the executor address; POOL_ADMIN/EMERGENCY_ADMIN/RISK_ADMIN are all keyed
            # on a Safe address instead.
            if args and args[0] == EXECUTOR:
                raise RuntimeError("RPC disagreement on DEFAULT_ADMIN_ROLE specifically")
            return original_cross_checked(rpc_urls, fn, *args)

        scorers.cross_checked = _fail_only_default_admin
        self.addCleanup(lambda: setattr(scorers, "cross_checked", original_cross_checked))
        r = scorers.score_aave_v3_horizon_pool(FakeW3())
        self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["timelockScore"]), (20, 0, 0))
        self.assertTrue(any("hasRole(DEFAULT_ADMIN_ROLE, executor) cross-RPC check FAILED" in n for n in r["notes"]))


class TestRegistry(unittest.TestCase):
    # UPDATED 2026-09-25 (twice): score_convex_finance_booster was appended right after Horizon
    # (its own tests live in chains/ethereum-l1/tests/test_new_targets_2026_09_25.py); then 4 more
    # Morpho V1 vault scorers (commit 15543f2, same day) were appended after THAT -- found by
    # running the full suite before committing the controller-concentration work, not by re-reading
    # that earlier diff. Horizon and Convex both keep their relative order, just further from the
    # end now; pinned by position from the end (-6, -5) rather than a hardcoded absolute count, so
    # the next addition doesn't silently break this test's own assumption a second time.
    def test_horizon_keeps_its_position_ahead_of_later_additions(self):
        self.assertIs(scorers.SIMPLE_SCORERS[-6], scorers.score_aave_v3_horizon_pool)
        self.assertIs(scorers.SIMPLE_SCORERS[-5], scorers.score_convex_finance_booster)
        self.assertEqual(len(scorers.SIMPLE_SCORERS), 22)


if __name__ == "__main__":
    unittest.main()
