"""
Unit tests for `chains/solana/scorers.py::score_kamino_liquidity` (Kamino
Liquidity / yvaults, added 2026-09-17) -- this target's OWN orchestration:
how its two full-power paths (program upgrade authority, and
`GlobalConfig.adminAuthority`) are each resolved via `_resolve_squads_v4`
and combined via `min()` PER DIMENSION (METHODOLOGY.md 6.2), not the
already-tested shared formula helpers themselves.

`sol_read.read_kliquidity_global_config` already has dedicated byte-level
decode coverage in `test_solana_defi_config_admins.py` -- per this task's
own instructions, it is mocked here at the orchestration level with a
plain dict matching its documented return shape ({"global_config":...,
"admin_authority":...}), no new byte fixture needed.

`sol_read.read_squads_vault` (the OFFLINE Squads-v4 vault-0 PDA
re-derivation `_resolve_squads_v4` uses to decide whether a hardcoded
multisig candidate is a MATCH or a MISMATCH) is pure arithmetic with no
network call, so it is deliberately left UNPATCHED and called for real in
every test below -- the "matching" authority for a resolved-path scenario
is always the real derived vault address, never guessed.

Only `sol_read.read_program`, `sol_read.read_kliquidity_global_config` and
`sol_read.read_squads` touch the network, so only those three are
monkeypatched -- directly on `solana.sol_read` (scorers.py's own imported
module reference), per this repo's established pattern (see
test_drift_protocol.py's own comment on why the separately-loaded
standalone `sol_read` alias must NOT be patched instead: it is a distinct
module object under a different sys.modules key and patching it would
silently no-op).
"""
import importlib.util
import os
import sys
import unittest

REPO_ROOT = os.path.join(os.path.dirname(__file__), "..", "..", "..")

# Copied verbatim from chains/solana/scorers.py::score_kamino_liquidity's
# own local constants -- not guessed, and not re-derived here beyond the
# pure offline PDA math `read_squads_vault` already performs.
UPGRADE_MS = "E7994UpSGhSpbpnuSepPXHBuMy3eRvHJL36DjTs1kb2b"
ADMIN_MS = "HvYoRSJdVcj6WRWV57yLu2Vmwh1ccqJRdkCwhNsSfRu4"
GLOBAL_CONFIG = "GKnHiWh3RRrE1zsNzWxRkomymHc374TvJPSTv2wPeYdB"
KLIQUIDITY_PROGRAM = "6LtLpnUFNByNXLyCoK9wA2MykKAmQNZKBdY8s47dehDc"
# oracleAuthorityScore (2026-10-05): the Scope feed the strategies price from, its Configuration and the two Scope multisigs.
SCOPE_PROGRAM = "HFn8GnPADiny6XqUoWE8uRPPxb29ikn4yTuPa9MF2fWJ"
SCOPE_ADMIN_MS = "EFZxQRB58g7nTYw6bag8sJYXn7wUWHoKt3AcCNzHbe24"
SCOPE_UPGRADE_MS = "DDJGaWjVREXffoMe9nyvb1c7wpajLdh7fTnAb2giD9RM"
TOKEN_INFOS = "3v6ootgJJZbSWEDfZMA1scfh7wcsVVfeocExRxPqCyWH"
FEED, FEED2 = "3NJYftD5sjVfxSnUdZ1wVML8f3aC6mp1CXCL6L7TnU8C", "Feed2222222222222222222222222222222222222222"


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


solana = _load_module("aro_test_solana_scorers_kliquidity", "chains/solana/scorers.py")

# The real, offline-derived vault-0 PDAs of each hardcoded multisig
# candidate -- computed once via the pure `read_squads_vault` (no RPC),
# exactly as `_resolve_squads_v4` itself does. Using these as the mocked
# "live" authority is what makes a resolved-path test scenario a genuine
# MATCH rather than a fabricated one.
DERIVED_UPGRADE_VAULT = solana.sol_read.read_squads_vault(UPGRADE_MS, 0)["vault"]
DERIVED_ADMIN_VAULT = solana.sol_read.read_squads_vault(ADMIN_MS, 0)["vault"]
DERIVED_SCOPE_ADMIN_VAULT = solana.sol_read.read_squads_vault(SCOPE_ADMIN_MS, 0)["vault"]
DERIVED_SCOPE_UPGRADE_VAULT = solana.sol_read.read_squads_vault(SCOPE_UPGRADE_MS, 0)["vault"]


def _squads(threshold, voters, delay_s, prefix="signer", config_authority=None):
    """A realistic Squads v4 `read_squads()`-shaped dict: `voters` members,
    all Vote-permissioned (mask=2), so `_voters_with_vote_permission()`
    equals `voters` directly -- keeps each test's chosen threshold/voters
    pair exactly the ones fed to `_score_full_power_path` for the expected
    value, with no separate accounting for non-voting members."""
    members = [{"key": f"{prefix}-{i}", "mask": 2} for i in range(voters)]
    return {
        "multisig": "unused-ms-pubkey",
        "owner": solana.SQUADS_V4_PROGRAM,
        "config_authority": config_authority or solana.SYSTEM_PROGRAM_DEFAULT,
        "threshold": threshold,
        "time_lock_s": delay_s,
        "members": len(members),
        "member_list": members,
    }


class _KaminoLiquidityScorerTestCase(unittest.TestCase):
    def setUp(self):
        self._orig_read_program = solana.sol_read.read_program
        self._orig_read_gc = solana.sol_read.read_kliquidity_global_config
        self._orig_read_squads = solana.sol_read.read_squads
        self._orig_read_feeds = solana.sol_read.read_kliquidity_collateral_feeds
        self._orig_read_scope = solana.sol_read.read_scope_configs

    def tearDown(self):
        solana.sol_read.read_program = self._orig_read_program
        solana.sol_read.read_kliquidity_global_config = self._orig_read_gc
        solana.sol_read.read_squads = self._orig_read_squads
        solana.sol_read.read_kliquidity_collateral_feeds = self._orig_read_feeds
        solana.sol_read.read_scope_configs = self._orig_read_scope

    def _patch(self, upgrade_authority, admin_authority, squads_by_ms, actions_authority="ActionsAuthorityEOA111111111111111111111X",
               entries=(), configs=(), scope_upgrade=None, scope_program=SCOPE_PROGRAM):
        """Every reader the scorer calls is replaced: the Scope ones default to an empty tokenInfos (oracle field 20)."""
        programs = {KLIQUIDITY_PROGRAM: upgrade_authority, SCOPE_PROGRAM: scope_upgrade}
        solana.sol_read.read_program = lambda url, pk: {"upgrade_authority": programs[pk]}
        solana.sol_read.read_kliquidity_global_config = lambda url, pk: {
            "global_config": pk, "admin_authority": admin_authority, "actions_authority": actions_authority,
            "scope_program": scope_program, "token_infos": TOKEN_INFOS}
        solana.sol_read.read_kliquidity_collateral_feeds = lambda url, pk: list(entries) if pk == TOKEN_INFOS else None
        solana.sol_read.read_scope_configs = lambda url, pk: list(configs) if pk == SCOPE_PROGRAM else None

        def fake_read_squads(url, pk):
            return squads_by_ms[pk]
        solana.sol_read.read_squads = fake_read_squads


class TestBothPathsResolveHeadlineScenario(_KaminoLiquidityScorerTestCase):
    """The exact scenario the function's own docstring describes: BOTH
    paths resolve to a matching 5-of-7 Squads v4 vault, the upgrade path
    with a 24h delay, the GlobalConfig path with none. Confirms the
    combined score is the real per-dimension min of the two REAL
    `_score_full_power_path` outputs (computed here via the shared,
    already-tested helper -- not hand-derived numbers), not a
    reimplementation of that formula."""

    def test_combined_equals_elementwise_min_of_both_real_paths(self):
        self._patch(
            upgrade_authority=DERIVED_UPGRADE_VAULT,
            admin_authority=DERIVED_ADMIN_VAULT,
            squads_by_ms={
                UPGRADE_MS: _squads(5, 7, 86400, prefix="upgrade"),
                ADMIN_MS: _squads(5, 7, 0, prefix="admin"),
            },
        )
        result = solana.score_kamino_liquidity("unused-url")

        path_a = solana._score_full_power_path("squads_v4", threshold=5, voters=7, delay_s=86400)
        path_b = solana._score_full_power_path("squads_v4", threshold=5, voters=7, delay_s=0)
        expected = tuple(min(a, b) for a, b in zip(path_a, path_b))

        actual = (result["adminKeyScore"], result["multisigScore"], result["timelockScore"])
        self.assertEqual(actual, expected)

    def test_zero_delay_admin_path_drags_the_combined_timelock_below_the_upgrade_paths_own(self):
        # The concrete claim this target exists to make: the GlobalConfig
        # path's zero delay is the binding constraint on timelockScore,
        # even though the program-upgrade path alone has a real 24h delay.
        self._patch(
            upgrade_authority=DERIVED_UPGRADE_VAULT,
            admin_authority=DERIVED_ADMIN_VAULT,
            squads_by_ms={
                UPGRADE_MS: _squads(5, 7, 86400, prefix="upgrade"),
                ADMIN_MS: _squads(5, 7, 0, prefix="admin"),
            },
        )
        result = solana.score_kamino_liquidity("unused-url")
        upgrade_alone = solana._score_full_power_path("squads_v4", threshold=5, voters=7, delay_s=86400)
        self.assertLess(result["timelockScore"], upgrade_alone[2])
        self.assertEqual(result["timelockScore"], 0)


class TestCombinationIsPerDimensionNotPerPath(_KaminoLiquidityScorerTestCase):
    """METHODOLOGY.md 6.2's actual rule is min() taken independently on
    EACH of adminKey/multisig/timelock, not "pick whichever whole path
    scores worse overall". Constructs two paths that are each stronger on
    a DIFFERENT dimension than the other, so a buggy "select one whole
    path" implementation would produce a result equal to one of the two
    input tuples -- the correct elementwise-min implementation must not."""

    def test_combined_triple_matches_neither_input_path_wholesale(self):
        self._patch(
            upgrade_authority=DERIVED_UPGRADE_VAULT,
            admin_authority=DERIVED_ADMIN_VAULT,
            squads_by_ms={
                # Small council, low threshold, but delayed past 24h ->
                # decent multisig+timelock, weaker admin band.
                UPGRADE_MS: _squads(3, 4, 90000, prefix="upgrade"),
                # Larger council, higher threshold, zero delay -> weaker
                # multisig ratio and zero timelock, but a stronger admin band.
                ADMIN_MS: _squads(6, 8, 0, prefix="admin"),
            },
        )
        result = solana.score_kamino_liquidity("unused-url")
        actual = (result["adminKeyScore"], result["multisigScore"], result["timelockScore"])

        path_a = solana._score_full_power_path("squads_v4", threshold=3, voters=4, delay_s=90000)
        path_b = solana._score_full_power_path("squads_v4", threshold=6, voters=8, delay_s=0)
        expected = tuple(min(a, b) for a, b in zip(path_a, path_b))

        self.assertEqual(actual, expected)
        self.assertNotEqual(actual, path_a)
        self.assertNotEqual(actual, path_b)


class TestProgramUpgradeRenounced(_KaminoLiquidityScorerTestCase):
    """`none_means_renounced=True` is passed ONLY for the program-upgrade
    path -- a None upgrade authority must resolve to the safest
    100/100/100 band (via the RENOUNCED sentinel), not the 20/20/0
    mismatch-degrade band, and the GlobalConfig path (which does resolve)
    must be the one that actually binds the combined score."""

    def test_renounced_upgrade_path_does_not_drag_down_the_resolved_admin_path(self):
        self._patch(
            upgrade_authority=None,
            admin_authority=DERIVED_ADMIN_VAULT,
            squads_by_ms={ADMIN_MS: _squads(4, 6, 0, prefix="admin")},
        )
        result = solana.score_kamino_liquidity("unused-url")
        admin_path = solana._score_full_power_path("squads_v4", threshold=4, voters=6, delay_s=0)
        actual = (result["adminKeyScore"], result["multisigScore"], result["timelockScore"])
        self.assertEqual(actual, admin_path)

    def test_renounced_path_is_not_logged_as_a_mismatch(self):
        self._patch(
            upgrade_authority=None,
            admin_authority=DERIVED_ADMIN_VAULT,
            squads_by_ms={ADMIN_MS: _squads(4, 6, 0, prefix="admin")},
        )
        result = solana.score_kamino_liquidity("unused-url")
        self.assertFalse(any("MISMATCH" in n for n in result["notes"]))
        self.assertTrue(any("renounced" in n.lower() for n in result["notes"]))


class TestProgramUpgradeMismatchDegrades(_KaminoLiquidityScorerTestCase):
    """A live upgrade authority that does NOT match the offline-derived
    vault-0 PDA of the hardcoded UPGRADE_MS candidate must degrade to
    20/20/0 rather than raise or silently trust the hardcoded constant --
    and that degrade must still correctly bind the combined score via
    min() even when the OTHER path resolves to a strong, matching
    multisig."""

    def test_mismatched_upgrade_authority_degrades_to_20_20_0_and_dominates_combined_score(self):
        self._patch(
            upgrade_authority="SomeUnrelatedAuthorityNotMatchingAnyVaultPDA1",
            admin_authority=DERIVED_ADMIN_VAULT,
            # A deliberately strong, fully-matching admin path (max
            # threshold shape, multi-day delay) so this test isolates the
            # mismatch branch's own effect rather than relying on the
            # admin path also being weak.
            squads_by_ms={ADMIN_MS: _squads(7, 7, 999999, prefix="admin")},
        )
        result = solana.score_kamino_liquidity("unused-url")
        admin_path = solana._score_full_power_path("squads_v4", threshold=7, voters=7, delay_s=999999)
        # Sanity check the admin path really is strong on every dimension,
        # so (20, 20, 0) below is demonstrably the mismatch branch binding,
        # not a coincidence of a weak admin path.
        self.assertTrue(all(v >= 20 for v in admin_path))
        actual = (result["adminKeyScore"], result["multisigScore"], result["timelockScore"])
        self.assertEqual(actual, (20, 20, 0))
        self.assertTrue(any("program upgrade" in n and "MISMATCH, degrading" in n for n in result["notes"]))


class TestGlobalConfigPathHasNoRenouncedHandling(_KaminoLiquidityScorerTestCase):
    """Asymmetry regression test: unlike the program-upgrade path,
    `_resolve_squads_v4` is called for `GlobalConfig.adminAuthority`
    WITHOUT `none_means_renounced=True` (score_kamino_liquidity's own
    source calls it with the default `False`). A None adminAuthority must
    therefore be treated as an ordinary MISMATCH/degrade, never as the
    safest renounced band -- if a future edit accidentally added
    `none_means_renounced=True` here too, this test would catch it."""

    def test_none_admin_authority_is_logged_as_mismatch_not_renounced(self):
        self._patch(
            upgrade_authority=DERIVED_UPGRADE_VAULT,
            admin_authority=None,
            squads_by_ms={UPGRADE_MS: _squads(5, 6, 3600, prefix="upgrade")},
        )
        result = solana.score_kamino_liquidity("unused-url")
        gc_notes = [n for n in result["notes"] if "GlobalConfig.adminAuthority" in n and "vault-0 PDA" in n]
        self.assertTrue(gc_notes, "expected a _resolve_squads_v4 resolution note for the GlobalConfig path")
        self.assertTrue(any("MISMATCH, degrading" in n for n in gc_notes))
        self.assertFalse(any("renounced" in n.lower() for n in gc_notes))

    def test_none_admin_authority_degrades_to_20_20_0_for_that_dimension_pair(self):
        self._patch(
            upgrade_authority=DERIVED_UPGRADE_VAULT,
            admin_authority=None,
            squads_by_ms={UPGRADE_MS: _squads(5, 6, 3600, prefix="upgrade")},
        )
        result = solana.score_kamino_liquidity("unused-url")
        upgrade_path = solana._score_full_power_path("squads_v4", threshold=5, voters=6, delay_s=3600)
        expected = (min(upgrade_path[0], 20), min(upgrade_path[1], 20), min(upgrade_path[2], 0))
        actual = (result["adminKeyScore"], result["multisigScore"], result["timelockScore"])
        self.assertEqual(actual, expected)


class TestNonDefaultConfigAuthorityAborts(_KaminoLiquidityScorerTestCase):
    """`_resolve_squads_v4` deliberately raises NotImplementedError rather
    than guessing a score when a resolved multisig's own `config_authority`
    is set (not the system default) -- the "Squads v4 controlled" band
    METHODOLOGY.md 6.1 documents but this project has never calibrated.
    Must propagate out of score_kamino_liquidity uncaught, an abort
    condition, not a silently-degraded score."""

    def test_non_default_config_authority_on_the_matched_upgrade_multisig_raises(self):
        self._patch(
            upgrade_authority=DERIVED_UPGRADE_VAULT,
            admin_authority=None,  # never reached -- the raise happens first
            squads_by_ms={
                UPGRADE_MS: _squads(
                    5, 7, 3600, prefix="upgrade",
                    config_authority="SomeNonDefaultConfigAuthority1111111111111"),
            },
        )
        with self.assertRaises(NotImplementedError):
            solana.score_kamino_liquidity("unused-url")


class TestSignersAccumulateFromBothResolvedMultisigs(_KaminoLiquidityScorerTestCase):
    """`_signers` must be the UNION of both resolved multisigs' member
    keys, not just one path's -- both are genuinely independent full-power
    paths and either's members could execute the corresponding action."""

    def test_signers_include_members_of_both_multisigs(self):
        self._patch(
            upgrade_authority=DERIVED_UPGRADE_VAULT,
            admin_authority=DERIVED_ADMIN_VAULT,
            squads_by_ms={
                UPGRADE_MS: _squads(3, 4, 3600, prefix="upgrade"),
                ADMIN_MS: _squads(2, 3, 0, prefix="admin"),
            },
        )
        result = solana.score_kamino_liquidity("unused-url")
        expected_upgrade_signers = {f"upgrade-{i}" for i in range(4)}
        expected_admin_signers = {f"admin-{i}" for i in range(3)}
        self.assertTrue(expected_upgrade_signers <= result["_signers"])
        self.assertTrue(expected_admin_signers <= result["_signers"])
        self.assertEqual(len(result["_signers"]), 7)


class TestReturnedDictShapeAndCompositeAndNotes(_KaminoLiquidityScorerTestCase):
    """The rest of the returned dict's contract: target/label identity,
    oracleAuthorityScore's fixed 100 (this target's authority chain is the
    only thing scored, not any price-oracle path), compositeScore computed
    from the SAME combined triple via the shared `_composite` helper, and a
    combined-summary note line."""

    def test_target_label_oracle_and_composite(self):
        self._patch(
            upgrade_authority=DERIVED_UPGRADE_VAULT,
            admin_authority=DERIVED_ADMIN_VAULT,
            squads_by_ms={
                UPGRADE_MS: _squads(5, 7, 86400, prefix="upgrade"),
                ADMIN_MS: _squads(5, 7, 0, prefix="admin"),
            },
        )
        result = solana.score_kamino_liquidity("unused-url")
        self.assertEqual(result["target"], GLOBAL_CONFIG)
        self.assertEqual(result["label"], "Kamino Liquidity (yvaults)")
        self.assertEqual(result["oracleAuthorityScore"], 20)  # no used CollateralInfo in this fixture: unknown, never 100
        expected_composite = solana._composite(
            result["adminKeyScore"], result["multisigScore"], result["timelockScore"])
        self.assertEqual(result["compositeScore"], expected_composite)
        self.assertTrue(any(n.startswith("combined (min over both full-power paths") for n in result["notes"]))


class TestOracleAuthorityScope(_KaminoLiquidityScorerTestCase):
    """oracleAuthorityScore (2026-10-05): min over the Scope paths of every feed the CollateralInfos name, Solana formula,
    governance-grade at the GlobalConfig admin's own delay, UNREAD -> 20 never 100. Each test fails when its branch goes."""
    ENTRY = {"mint": "Mint1111111111111111111111111111111111111111", "scope_feed": FEED, "disabled": 0}
    CONFIG = {"configuration": "Config111111111111111111111111111111111111111", "oracle_prices": FEED, "admin": DERIVED_SCOPE_ADMIN_VAULT}

    def score(self, admin_delay=0, scope_admin=(4, 10, 0), scope_upgrade=(5, 10, 86400), entries=None, configs=None,
              upgrade_authority=DERIVED_SCOPE_UPGRADE_VAULT, **kw):
        squads = {UPGRADE_MS: _squads(5, 7, 86400, prefix="upgrade"), ADMIN_MS: _squads(5, 7, admin_delay, prefix="admin"),
                  SCOPE_ADMIN_MS: _squads(*scope_admin, prefix="scope-admin"), SCOPE_UPGRADE_MS: _squads(*scope_upgrade, prefix="scope-upgrade")}
        self._patch(DERIVED_UPGRADE_VAULT, DERIVED_ADMIN_VAULT, squads, entries=[self.ENTRY] if entries is None else entries,
                    configs=[self.CONFIG] if configs is None else configs, scope_upgrade=upgrade_authority, **kw)
        return solana.score_kamino_liquidity("unused-url")

    def composite(self, t, n, d):
        return solana._composite(*solana._score_full_power_path("squads_v4", threshold=t, voters=n, delay_s=d))

    def test_scope_admin_sets_the_min_as_on_kamino_lend(self):
        r = self.score()
        self.assertEqual(r["oracleAuthorityScore"], min(self.composite(4, 10, 0), self.composite(5, 10, 86400)))
        self.assertEqual(r["oracleAuthorityScore"], 45)
        self.assertEqual(self.score(scope_admin=(9, 10, 86400 * 9), scope_upgrade=(3, 10, 3600))["oracleAuthorityScore"], self.composite(3, 10, 3600))

    def test_a_delay_at_least_the_targets_own_is_governance_grade(self):
        r = self.score(admin_delay=3600, scope_admin=(4, 10, 7200))  # Scope admin 2 h, upgrade 24 h, own 1 h: both disclosed
        self.assertEqual(r["oracleAuthorityScore"], 100)
        self.assertEqual(self.score(admin_delay=3600, scope_admin=(4, 10, 600))["oracleAuthorityScore"], self.composite(4, 10, 600))

    def test_renounced_scope_upgrade_is_disclosed(self):
        r = self.score(upgrade_authority=None, scope_upgrade=(1, 1, 0))
        self.assertEqual(r["oracleAuthorityScore"], 45)
        self.assertTrue(any("Scope program upgrade: renounced" in n for n in r["notes"]))

    def test_every_unknown_is_20_never_100(self):
        cases = {"feed without a Configuration": {"configs": []},
                 "Scope admin not the pinned multisig's vault": {"configs": [dict(self.CONFIG, admin=DERIVED_ADMIN_VAULT)]},
                 "Scope upgrade not the pinned multisig's vault": {"upgrade_authority": DERIVED_ADMIN_VAULT},
                 "no used CollateralInfo": {"entries": []},
                 "another Scope program": {"scope_program": KLIQUIDITY_PROGRAM}}
        for name, kw in cases.items():
            with self.subTest(name):
                r = self.score(scope_admin=(9, 10, 86400 * 9), scope_upgrade=(9, 10, 86400 * 9), **kw)
                self.assertEqual(r["oracleAuthorityScore"], 20)
                self.assertTrue(any(solana.PRICE_UNREAD_MARK in n for n in r["notes"]))

    def test_each_distinct_feed_is_walked(self):
        second = dict(self.CONFIG, configuration="Config222222222222222222222222222222222222222", oracle_prices=FEED2, admin=DERIVED_ADMIN_VAULT)
        r = self.score(entries=[self.ENTRY, dict(self.ENTRY, scope_feed=FEED2)], configs=[self.CONFIG, second])
        self.assertEqual(r["oracleAuthorityScore"], 20)  # the second feed's admin does not match: UNREAD, min(20, 45)

    def test_a_failed_multisig_read_is_20_not_a_crash(self):
        self.score()
        real = solana.sol_read.read_squads

        def flaky(url, pk):
            if pk == SCOPE_ADMIN_MS:
                raise solana.sol_read.SolRpcError("rpc down")
            return real(url, pk)
        solana.sol_read.read_squads = flaky
        r = solana.score_kamino_liquidity("unused-url")
        self.assertEqual(r["oracleAuthorityScore"], 20)
        self.assertTrue(any("price walk failed" in n for n in r["notes"]))

    def test_a_failed_read_after_a_lower_scored_path_keeps_it(self):
        self.score(scope_admin=(1, 10, 0))  # the Scope admin path scores below 20
        low = self.composite(1, 10, 0)
        real = solana.sol_read.read_squads

        def flaky(url, pk):
            if pk == SCOPE_UPGRADE_MS:
                raise solana.sol_read.SolRpcError("rpc down")
            return real(url, pk)
        solana.sol_read.read_squads = flaky
        r = solana.score_kamino_liquidity("unused-url")
        self.assertLess(low, 20)
        self.assertEqual(r["oracleAuthorityScore"], low)
        self.assertTrue(any("price walk failed" in n for n in r["notes"]))

    def test_a_failed_read_is_20(self):
        def boom(url, pk):
            raise solana.sol_read.SolRpcError("rpc down")
        self.score()
        solana.sol_read.read_kliquidity_collateral_feeds = boom
        r = solana.score_kamino_liquidity("unused-url")
        self.assertEqual(r["oracleAuthorityScore"], 20)
        self.assertTrue(any("price walk failed" in n for n in r["notes"]))


if __name__ == "__main__":
    unittest.main()
