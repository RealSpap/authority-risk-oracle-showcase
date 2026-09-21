"""
Unit tests for `chains/solana/scorers.py::score_kamino_lend` (Kamino Lend,
main SOL/BTC market) -- the four-authority-path Solana scorer combining
klend program upgrade, market owner, Scope admin, and Scope program
upgrade via `_resolve_squads_v4`.

Two layers are covered, following this repo's established split (see
`test_solana_defi_config_admins.py`, `test_drift_protocol.py`):

  1. Orchestration (the bulk of this file): `score_kamino_lend`'s OWN
     branching logic -- which of the four resolved paths feeds
     adminKey/multisig/timelock vs. oracleAuthorityScore, and the
     all-or-nothing degradation when any one path fails to resolve.
     `sol_read.read_program`/`read_klend_market`/`read_scope_configs` and
     `scorers.py`'s own `_resolve_squads_v4` are monkeypatched directly on
     the loaded `scorers` module (not re-deriving PDA math for four
     different multisig candidates) -- `_resolve_squads_v4` itself, and
     the `_score_full_power_path`/`_composite`/`_voters_with_vote_
     permission` formulas it and `score_kamino_lend` call, are already
     covered elsewhere in this repo (test_drift_protocol.py,
     test_switchboard_on_demand.py, test_solend_governance.py) and are
     NOT re-tested here -- this file only checks that score_kamino_lend
     wires their outputs together correctly.

  2. Primitive decode logic for the two `sol_read.py` functions this
     scorer calls that had ZERO test coverage anywhere in this repo
     before this file: `read_klend_market` and `read_scope_configs`.
     Both are confidently testable without guessing any byte offset --
     every offset used below is copied verbatim from `sol_read.py`'s own
     indexing (`d[24:56]`, `d[3248:3280]`, `d[8+32*i:40+32*i]`, etc.), and
     `read_klend_market`'s one PDA derivation (`global_config`) is
     computed with the SAME real `find_program_address` function the
     production code calls, not hand-derived -- so the fixture's
     `global_config` address is guaranteed to match what the real code
     will look up, by construction. Synthetic zero-padded fixtures are
     used (real on-chain LendingMarket/Configuration bytes were not
     available to embed here), same convention as
     `test_solana_defi_config_admins.py`'s synthetic Kamino/marginfi/
     PumpSwap fixtures.
"""
import base64
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


sol_read = _load_module("aro_test_sol_read_kamino", "chains/solana/scripts/sol_read.py")
solana = _load_module("aro_test_solana_scorers_kamino", "chains/solana/scorers.py")

# The exact target constants score_kamino_lend() hardcodes (chains/solana/
# scorers.py lines 715-723) -- copied here, not re-derived, so the fakes
# below can key on the same pubkeys the real function reads.
KLEND_PROGRAM = "KLend2g3cP87fffoy8q1mQqGKjrxjC8boSyAYavgmjD"
MARKET = "7u3HeHxYDLhnCoErrtycNokbQYbWGzLs6JSDqGAv5PfF"
SCOPE_PROGRAM = "HFn8GnPADiny6XqUoWE8uRPPxb29ikn4yTuPa9MF2fWJ"
SCOPE_CONFIG = "6cMwdbrJ95D7v5655Zsoe7oXmjQJMnagWK8EcdG6qmGM"

# Arbitrary but VALID base58 32-byte pubkeys to use as fixture values,
# reused from real addresses already hardcoded elsewhere in scorers.py
# (avoids inventing new base58 strings that might not decode/on_curve
# cleanly -- these are known-good).
PK_A = "6hhBGCtmg7tPWUSgp3LG6X2rsmYWAc4tNsA6G4CnfQbM"
PK_B = "7idEEVRidWrahZJhxXMqniDbV6ESj7ZjyLrigcMcEt6H"
PK_C = "EFZxQRB58g7nTYw6bag8sJYXn7wUWHoKt3AcCNzHbe24"
PK_D = "DDJGaWjVREXffoMe9nyvb1c7wpajLdh7fTnAb2giD9RM"


def _sq(threshold, members, time_lock_s):
    """A minimal Squads v4 read()-shaped dict: `members` voters, all with
    full Initiate|Vote|Execute permission (mask=7), so
    `_voters_with_vote_permission` == `members` -- keeps these tests
    focused on score_kamino_lend's own orchestration, not on the
    mask-parsing formula already covered elsewhere."""
    return {
        "threshold": threshold, "members": members, "time_lock_s": time_lock_s,
        "member_list": [{"key": f"signer-{id(object())}-{i}", "mask": 7} for i in range(members)],
    }


def _sq_with_keys(threshold, members, time_lock_s, keys):
    sq = _sq(threshold, members, time_lock_s)
    sq["member_list"] = [{"key": k, "mask": 7} for k in keys]
    sq["members"] = len(keys)
    return sq


def _market_read(owner, owner_cached=None, name="Main Market"):
    return {"market": MARKET, "name": name, "lending_market_owner": owner,
            "lending_market_owner_cached": owner_cached if owner_cached is not None else owner}


class _OrchestrationTestBase(unittest.TestCase):
    """Shared monkeypatch plumbing for score_kamino_lend orchestration
    tests: fakes the four sol_read primitives it reads directly, plus
    scorers.py's own `_resolve_squads_v4` (simpler than re-deriving real
    Squads vault PDAs for four different hardcoded multisig candidates --
    an explicitly sanctioned shortcut for this kind of orchestration
    test). `resolve_map` is keyed by _resolve_squads_v4's own `label`
    argument ("klend upgrade" / "market owner" / "Scope admin" /
    "Scope upgrade") -> the value to return (a `_sq(...)` dict,
    `solana.RENOUNCED`, or None for "did not resolve")."""

    market_read = None
    scope_configs = None
    resolve_map = None
    klend_upgrade_authority = "unused-klend-authority"
    scope_upgrade_authority = "unused-scope-authority"

    def setUp(self):
        self._orig_read_program = solana.sol_read.read_program
        self._orig_read_klend_market = solana.sol_read.read_klend_market
        self._orig_read_scope_configs = solana.sol_read.read_scope_configs
        self._orig_resolve_squads_v4 = solana._resolve_squads_v4
        self.resolve_calls = []

        def fake_read_program(url, pk):
            if pk == KLEND_PROGRAM:
                return {"upgrade_authority": self.klend_upgrade_authority}
            if pk == SCOPE_PROGRAM:
                return {"upgrade_authority": self.scope_upgrade_authority}
            raise AssertionError(f"unexpected read_program call for {pk}")

        def fake_read_klend_market(url, pk):
            self.assertEqual(pk, MARKET)
            return self.market_read

        def fake_read_scope_configs(url, pk):
            self.assertEqual(pk, SCOPE_PROGRAM)
            return self.scope_configs

        def fake_resolve_squads_v4(url, label, authority, ms_candidate, notes, none_means_renounced=False):
            self.resolve_calls.append(
                {"label": label, "authority": authority, "ms_candidate": ms_candidate,
                 "none_means_renounced": none_means_renounced})
            notes.append(f"[fake resolve] {label}")
            return self.resolve_map[label]

        solana.sol_read.read_program = fake_read_program
        solana.sol_read.read_klend_market = fake_read_klend_market
        solana.sol_read.read_scope_configs = fake_read_scope_configs
        solana._resolve_squads_v4 = fake_resolve_squads_v4

    def tearDown(self):
        solana.sol_read.read_program = self._orig_read_program
        solana.sol_read.read_klend_market = self._orig_read_klend_market
        solana.sol_read.read_scope_configs = self._orig_read_scope_configs
        solana._resolve_squads_v4 = self._orig_resolve_squads_v4

    def _call_kwarg(self, label, kw):
        return next(c[kw] for c in self.resolve_calls if c["label"] == label)


class TestScoreKaminoLendAllResolvedComposesTheFourPaths(_OrchestrationTestBase):
    """The normal, all-resolved case. Locks in two distinct claims from
    the function's own docstring: (1) adminKeyScore/multisigScore/
    timelockScore take the min across ONLY the klend-upgrade and
    market-owner paths, even when a Scope path is far worse; (2)
    oracleAuthorityScore takes the min of each of the THREE oracle-
    relevant paths' own standalone composite (market owner included, not
    just the two Scope paths) -- the "genuinely aggravating finding" that
    an instant, undelayed Scope-admin re-map path can cap the oracle
    score below what the two slower paths alone would suggest."""

    def setUp(self):
        self.market_read = _market_read(owner="market-owner-authority")
        self.scope_configs = [{"configuration": SCOPE_CONFIG, "admin": "scope-admin-authority"}]
        self.klend_path_sq = _sq(threshold=5, members=10, time_lock_s=24 * 3600)
        self.market_path_sq = _sq(threshold=4, members=10, time_lock_s=12 * 3600)
        # threshold=1 short-circuits _score_full_power_path's squads_v4
        # branch to a flat (5, 0, 0) regardless of voters/delay -- the
        # worst realistic band, deliberately far below every other path
        # here, to prove it does NOT leak into adminKey/multisig/timelock.
        self.scope_admin_sq = _sq(threshold=1, members=10, time_lock_s=0)
        self.scope_upgrade_sq = _sq(threshold=5, members=10, time_lock_s=24 * 3600)
        self.resolve_map = {
            "klend upgrade": self.klend_path_sq,
            "market owner": self.market_path_sq,
            "Scope admin": self.scope_admin_sq,
            "Scope upgrade": self.scope_upgrade_sq,
        }
        super().setUp()

    def test_admin_multisig_timelock_are_min_of_klend_and_market_paths_only(self):
        result = solana.score_kamino_lend("unused-url")
        klend_path = solana._score_full_power_path(
            "squads_v4", threshold=5, voters=10, delay_s=24 * 3600)
        market_path = solana._score_full_power_path(
            "squads_v4", threshold=4, voters=10, delay_s=12 * 3600)
        self.assertEqual(result["adminKeyScore"], min(klend_path[0], market_path[0]))
        self.assertEqual(result["multisigScore"], min(klend_path[1], market_path[1]))
        self.assertEqual(result["timelockScore"], min(klend_path[2], market_path[2]))
        # The Scope admin path's threshold=1 -> (5, 0, 0) band must NOT
        # have dragged these three scores down to 5/0/0.
        self.assertGreater(result["adminKeyScore"], 5)
        self.assertGreater(result["multisigScore"], 0)
        self.assertGreater(result["timelockScore"], 0)

    def test_oracle_authority_is_min_of_market_and_both_scope_paths_own_composites(self):
        result = solana.score_kamino_lend("unused-url")
        market_composite = solana._composite(*solana._score_full_power_path(
            "squads_v4", threshold=4, voters=10, delay_s=12 * 3600))
        scope_admin_composite = solana._composite(*solana._score_full_power_path(
            "squads_v4", threshold=1, voters=10, delay_s=0))
        scope_upgrade_composite = solana._composite(*solana._score_full_power_path(
            "squads_v4", threshold=5, voters=10, delay_s=24 * 3600))
        expected = min(market_composite, scope_admin_composite, scope_upgrade_composite)
        self.assertEqual(result["oracleAuthorityScore"], expected)
        # The threshold=1 Scope admin path is the actual binding
        # constraint here -- confirms oracleAuthorityScore is reading it,
        # not silently defaulting to the market path alone.
        self.assertEqual(result["oracleAuthorityScore"], scope_admin_composite)

    def test_composite_score_is_derived_from_the_admin_multisig_timelock_triple(self):
        result = solana.score_kamino_lend("unused-url")
        expected = solana._composite(result["adminKeyScore"], result["multisigScore"], result["timelockScore"])
        self.assertEqual(result["compositeScore"], expected)

    def test_target_and_label_identify_the_main_market(self):
        result = solana.score_kamino_lend("unused-url")
        self.assertEqual(result["target"], MARKET)
        self.assertEqual(result["label"], "Kamino Lend (main market, SOL/BTC)")


class TestScoreKaminoLendAnyUnresolvedPathDegradesAllFour(_OrchestrationTestBase):
    """The single most important branch: `all_resolved` is a strict
    all() over the four paths -- if ANY ONE fails to resolve/match, EVERY
    score (adminKey, multisig, timelock, AND oracleAuthority) degrades
    uniformly to 20/20/0/20, not just the failed path or its own
    dimension. Two variants below deliberately fail a DIFFERENT one of
    the four paths each time, with the other three left healthy (high,
    clearly-not-20 scores) -- if the degradation were scoped to only the
    failed path's own dimension, these two tests would observe different
    (non-degraded) results from each other; instead both must produce
    the identical flat 20/20/0/20."""

    def setUp(self):
        self.market_read = _market_read(owner="market-owner-authority")
        self.scope_configs = [{"configuration": SCOPE_CONFIG, "admin": "scope-admin-authority"}]
        # All four paths would score well (high thresholds, real delay)
        # if resolved -- so a degraded 20/20/0/20 result can only come
        # from the all-or-nothing branch, not from a naturally weak path.
        self.healthy_sq = _sq(threshold=9, members=10, time_lock_s=48 * 3600)
        super().setUp()

    def _assert_fully_degraded(self, result):
        self.assertEqual(result["adminKeyScore"], 20)
        self.assertEqual(result["multisigScore"], 20)
        self.assertEqual(result["timelockScore"], 0)
        self.assertEqual(result["oracleAuthorityScore"], 20)
        self.assertEqual(result["compositeScore"], solana._composite(20, 20, 0))
        self.assertTrue(any("did not resolve" in n or "did not match" in n or "unverified" in n for n in result["notes"]))

    def test_market_owner_path_failing_degrades_everything(self):
        # resolve_map is read lazily (by label) each time
        # _resolve_squads_v4 is called, so mutating it here -- after the
        # fakes were already installed by setUp() -- is sufficient; no
        # need to (and must NOT, to avoid re-capturing already-patched
        # functions as "original") re-run the patch installation.
        self.resolve_map = {
            "klend upgrade": self.healthy_sq, "market owner": None,
            "Scope admin": self.healthy_sq, "Scope upgrade": self.healthy_sq,
        }
        self._assert_fully_degraded(solana.score_kamino_lend("unused-url"))

    def test_scope_admin_path_failing_also_degrades_admin_key_and_multisig(self):
        # Scope admin is an ORACLE-only path -- confirms the degradation
        # is truly all-or-nothing across the whole result, not scoped to
        # "only the oracle dimension degrades when an oracle-only path
        # fails" (a plausible but wrong narrower reading of the branch).
        self.resolve_map = {
            "klend upgrade": self.healthy_sq, "market owner": self.healthy_sq,
            "Scope admin": None, "Scope upgrade": self.healthy_sq,
        }
        self._assert_fully_degraded(solana.score_kamino_lend("unused-url"))


class TestScoreKaminoLendRenouncedPathsCountAsResolved(_OrchestrationTestBase):
    """klend upgrade and Scope upgrade are genuine loader-v3
    Option<Pubkey> fields, so `_resolve_squads_v4` is called with
    `none_means_renounced=True` for both and can return the RENOUNCED
    sentinel -- which is NOT None, so `all_resolved` stays True (does not
    trigger the degrade-all branch), and `_path()` scores it as the
    safest (100, 100, 100) band rather than a mismatch."""

    def setUp(self):
        self.market_read = _market_read(owner="market-owner-authority")
        self.scope_configs = [{"configuration": SCOPE_CONFIG, "admin": "scope-admin-authority"}]
        self.market_path_sq = _sq(threshold=4, members=10, time_lock_s=12 * 3600)
        self.scope_admin_sq = _sq(threshold=4, members=10, time_lock_s=0)
        self.resolve_map = {
            "klend upgrade": solana.RENOUNCED, "market owner": self.market_path_sq,
            "Scope admin": self.scope_admin_sq, "Scope upgrade": solana.RENOUNCED,
        }
        super().setUp()

    def test_renounced_klend_path_does_not_trigger_degradation(self):
        result = solana.score_kamino_lend("unused-url")
        self.assertNotEqual((result["adminKeyScore"], result["multisigScore"], result["timelockScore"]), (20, 20, 0))

    def test_renounced_klend_path_never_drags_admin_key_below_the_market_path(self):
        # klend's RENOUNCED path scores (100, 100, 100) -- the min against
        # market owner's real path must therefore equal the market path's
        # own numbers exactly (renounced never becomes the binding
        # constraint over an actually-resolved multisig).
        result = solana.score_kamino_lend("unused-url")
        market_path = solana._score_full_power_path("squads_v4", threshold=4, voters=10, delay_s=12 * 3600)
        self.assertEqual(result["adminKeyScore"], market_path[0])
        self.assertEqual(result["multisigScore"], market_path[1])
        self.assertEqual(result["timelockScore"], market_path[2])

    def test_renounced_scope_upgrade_path_does_not_dominate_oracle_authority(self):
        result = solana.score_kamino_lend("unused-url")
        market_composite = solana._composite(*solana._score_full_power_path(
            "squads_v4", threshold=4, voters=10, delay_s=12 * 3600))
        scope_admin_composite = solana._composite(*solana._score_full_power_path(
            "squads_v4", threshold=4, voters=10, delay_s=0))
        self.assertEqual(result["oracleAuthorityScore"], min(market_composite, scope_admin_composite))


class TestScoreKaminoLendSigners(_OrchestrationTestBase):
    """`_signers` unions every resolved path's member keys, EXCLUDING any
    path that resolved to the RENOUNCED sentinel (a renounced authority
    has no multisig members to add)."""

    def setUp(self):
        self.market_read = _market_read(owner="market-owner-authority")
        self.scope_configs = [{"configuration": SCOPE_CONFIG, "admin": "scope-admin-authority"}]
        self.resolve_map = {
            "klend upgrade": _sq_with_keys(5, 2, 24 * 3600, ["klend-signer-1", "klend-signer-2"]),
            "market owner": _sq_with_keys(4, 2, 12 * 3600, ["market-signer-1", "market-signer-2"]),
            "Scope admin": _sq_with_keys(4, 2, 0, ["scope-admin-signer-1", "market-signer-1"]),  # overlaps market
            "Scope upgrade": solana.RENOUNCED,
        }
        super().setUp()

    def test_signers_is_the_union_of_all_resolved_non_renounced_member_keys(self):
        result = solana.score_kamino_lend("unused-url")
        self.assertEqual(
            result["_signers"],
            {"klend-signer-1", "klend-signer-2", "market-signer-1", "market-signer-2", "scope-admin-signer-1"},
        )

    def test_renounced_scope_upgrade_contributes_no_signers(self):
        result = solana.score_kamino_lend("unused-url")
        self.assertNotIn("Scope upgrade", result["_signers"])  # sentinel string itself never leaks in


class TestScoreKaminoLendReadWiring(_OrchestrationTestBase):
    """Orchestration details specific to score_kamino_lend's own read/
    dispatch logic (not the shared _resolve_squads_v4 formula): the
    pending-governance-transfer note, and what authority value gets
    passed to _resolve_squads_v4 for the Scope admin path when the
    target's own Configuration account isn't found among the program's
    Scope configs at all."""

    def setUp(self):
        self.scope_configs = [{"configuration": SCOPE_CONFIG, "admin": "scope-admin-authority"}]
        self.market_read = _market_read(owner="current-owner", owner_cached="old-pending-owner")
        healthy = _sq(threshold=6, members=10, time_lock_s=24 * 3600)
        self.resolve_map = {"klend upgrade": healthy, "market owner": healthy,
                             "Scope admin": healthy, "Scope upgrade": healthy}
        super().setUp()

    def test_pending_owner_transfer_produces_a_disclosure_note(self):
        result = solana.score_kamino_lend("unused-url")
        self.assertTrue(any("PENDING" in n and "old-pending-owner" in n for n in result["notes"]))
        # Scored on the CURRENT (non-cached) owner, per the function's own
        # docstring -- confirm that's what actually reached _resolve_squads_v4.
        self.assertEqual(self._call_kwarg("market owner", "authority"), "current-owner")

    def test_missing_scope_config_passes_none_authority_not_a_stale_value(self):
        self.scope_configs = []  # target's own Configuration account absent from this run's read
        self.market_read = _market_read(owner="current-owner")
        solana.score_kamino_lend("unused-url")
        self.assertIsNone(self._call_kwarg("Scope admin", "authority"))
        # none_means_renounced must stay False for this path (a missing/
        # unread Configuration is a failed read, not a real on-chain
        # renouncement) -- per the function's own docstring reasoning.
        self.assertFalse(self._call_kwarg("Scope admin", "none_means_renounced"))


# ---------------------------------------------------------------------------
# Primitive-level decode tests for sol_read.read_klend_market and
# sol_read.read_scope_configs -- both had ZERO test coverage anywhere in
# this repo before this file. Every offset below is copied verbatim from
# the functions' own source (chains/solana/scripts/sol_read.py), not
# guessed; read_klend_market's global_config PDA is computed with the
# REAL find_program_address (imported, not faked) so the fixture's
# derived address matches what the production code will look up, by
# construction rather than luck.
# ---------------------------------------------------------------------------

def _b64_account(total_len, fields):
    """`fields`: list of (offset, bytes) to place into a zero buffer of
    `total_len` bytes."""
    d = bytearray(total_len)
    for offset, value in fields:
        d[offset:offset + len(value)] = value
    return base64.b64encode(bytes(d)).decode()


class TestReadKlendMarketPrimitive(unittest.TestCase):
    OWNER = PK_A
    OWNER_CACHED = PK_B
    EMERGENCY_COUNCIL = PK_C
    PROPOSER_AUTHORITY = PK_D
    GLOBAL_ADMIN = "7ZyDFzet6sKgZLN4D89JLfo7chu2n7nYdkFt5RCFk8Sf"
    NAME = b"Main Market"

    def setUp(self):
        self._orig_acct = sol_read.acct
        # Real PDA derivation (not guessed/hand-derived) -- the exact same
        # function read_klend_market itself calls, with the exact same
        # seeds (b"global_config") and the exact same owner program id
        # this fixture's market account claims as its "owner".
        self.global_config_pk, _ = sol_read.find_program_address([b"global_config"], KLEND_PROGRAM)

        market_b64 = _b64_account(3350, [
            (24, sol_read.b58dec(self.OWNER)),
            (56, sol_read.b58dec(self.OWNER_CACHED)),
            (160, sol_read.b58dec(self.EMERGENCY_COUNCIL)),
            (3248, self.NAME),
            (3305, bytes([1])),  # immutable = True
            (3312, sol_read.b58dec(self.PROPOSER_AUTHORITY)),
        ])
        global_config_b64 = _b64_account(40, [(8, sol_read.b58dec(self.GLOBAL_ADMIN))])

        fixtures = {MARKET: {"data": [market_b64], "owner": KLEND_PROGRAM},
                    self.global_config_pk: {"data": [global_config_b64]}}

        def fake_acct(url, pk, enc="base64", length=None):
            if pk not in fixtures:
                raise AssertionError(f"unexpected account fetch: {pk}")
            return fixtures[pk]

        sol_read.acct = fake_acct

    def tearDown(self):
        sol_read.acct = self._orig_acct

    def test_decodes_owner_and_cached_owner_as_distinct_fields(self):
        m = sol_read.read_klend_market("unused-url", MARKET)
        self.assertEqual(m["lending_market_owner"], self.OWNER)
        self.assertEqual(m["lending_market_owner_cached"], self.OWNER_CACHED)
        self.assertNotEqual(m["lending_market_owner"], m["lending_market_owner_cached"])

    def test_decodes_name_emergency_council_and_proposer_authority(self):
        m = sol_read.read_klend_market("unused-url", MARKET)
        self.assertEqual(m["name"], "Main Market")
        self.assertEqual(m["emergency_council"], self.EMERGENCY_COUNCIL)
        self.assertEqual(m["proposer_authority"], self.PROPOSER_AUTHORITY)
        self.assertEqual(m["immutable"], 1)

    def test_global_admin_is_read_from_the_derived_global_config_pda(self):
        m = sol_read.read_klend_market("unused-url", MARKET)
        self.assertEqual(m["global_config"], self.global_config_pk)
        self.assertEqual(m["global_admin"], self.GLOBAL_ADMIN)


class TestReadScopeConfigsPrimitive(unittest.TestCase):
    ADMIN_A = "6hhBGCtmg7tPWUSgp3LG6X2rsmYWAc4tNsA6G4CnfQbM"
    ORACLE_MAPPINGS_A = "7idEEVRidWrahZJhxXMqniDbV6ESj7ZjyLrigcMcEt6H"
    ADMIN_B = "EFZxQRB58g7nTYw6bag8sJYXn7wUWHoKt3AcCNzHbe24"

    def setUp(self):
        self._orig_rpc = sol_read.rpc

        config_a = _b64_account(264, [
            (8, sol_read.b58dec(self.ADMIN_A)),          # names[0] = "admin"
            (40, sol_read.b58dec(self.ORACLE_MAPPINGS_A)),  # names[1] = "oracle_mappings"
        ])
        config_b = _b64_account(264, [(8, sol_read.b58dec(self.ADMIN_B))])

        # Deliberately returned OUT of sorted order, to also exercise the
        # function's own final `sorted(..., key=lambda c: c["configuration"])`.
        program_accounts_response = [
            {"pubkey": "Zconfig-should-sort-last", "account": {"data": [config_b, "base64"]}},
            {"pubkey": SCOPE_CONFIG, "account": {"data": [config_a, "base64"]}},
        ]

        def fake_rpc(url, method, params=None, tries=4):
            self.assertEqual(method, "getProgramAccounts")
            return program_accounts_response

        sol_read.rpc = fake_rpc

    def tearDown(self):
        sol_read.rpc = self._orig_rpc

    def test_admin_field_decodes_at_offset_8(self):
        configs = sol_read.read_scope_configs("unused-url", SCOPE_PROGRAM)
        target = next(c for c in configs if c["configuration"] == SCOPE_CONFIG)
        self.assertEqual(target["admin"], self.ADMIN_A)

    def test_oracle_mappings_field_at_offset_40_is_not_shifted_into_admin(self):
        # Regression guard for an off-by-one-field bug: admin and
        # oracle_mappings are two DIFFERENT 32-byte windows (8:40 vs
        # 40:72) -- if the field order/offsets were ever shuffled, this
        # would either collide with admin or read zeros instead.
        configs = sol_read.read_scope_configs("unused-url", SCOPE_PROGRAM)
        target = next(c for c in configs if c["configuration"] == SCOPE_CONFIG)
        self.assertEqual(target["oracle_mappings"], self.ORACLE_MAPPINGS_A)
        self.assertNotEqual(target["admin"], target["oracle_mappings"])

    def test_results_are_sorted_by_configuration_pubkey(self):
        configs = sol_read.read_scope_configs("unused-url", SCOPE_PROGRAM)
        self.assertEqual([c["configuration"] for c in configs],
                          sorted([SCOPE_CONFIG, "Zconfig-should-sort-last"]))


if __name__ == "__main__":
    unittest.main()
