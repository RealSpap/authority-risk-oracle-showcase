"""
Unit tests for scripts/lib/signer_overlap.py -- ZERO existing coverage before
this file (confirmed via grep), despite being real, load-bearing production
code: `scripts/lib/scorers.py`'s `score_all()` imports
`compute_cross_exposure` directly (`from .signer_overlap import
compute_cross_exposure`, ~line 1588) and calls it every run, wrapped in a
try/except whose documented fail-safe is "every crossExposureScore defaults
to 100 with a disclosure note", not a crash.

Two read primitives / boundaries this module has, tested at two different
levels (same split this project uses everywhere else -- test a primitive's
own internal control flow directly, then treat it as an opaque boundary when
testing the algorithm built on top of it):

  1. `_safe_owners(w3, addr)` -- tested directly against a FakeW3 whose
     `.eth.contract(address=.., abi=..)` returns a fake Contract object
     dispatching `.functions.<name>().call()` by (address, function_name),
     same shape as test_robinhood_event_replay_scorers.py's `_FakeContract`.
     Keyed purely on address+function-name (not on the literal ABI object
     passed in) so each test controls, per address, whether the Safe path
     (getOwners) and the custom-multisig path (getSigners) each raise or
     succeed.

  2. `compute_cross_exposure(w3)` -- the pure-Python aggregation algorithm
     over the module's `GROUPS` registry. Tested the same way
     test_cross_ecosystem_fixes.py tests `_apply_cross_exposure`: GROUPS is
     monkeypatched to small, hand-built synthetic registries (restored via
     addCleanup) so expected scores are exact and don't drift every time a
     real tracked target is added to the live registry. `_safe_owners`
     itself is ALSO monkeypatched for these tests (its own internal
     Safe-vs-fallback control flow is already covered by
     TestSafeOwnersReadPrimitive above) -- treated here purely as a
     (w3, addr) -> list-of-owners-or-None primitive boundary, same as this
     project treats call_raw/read_address_getter/safe_owners_and_threshold
     everywhere else.

  3. (ADDED 2026-09-20) the optional "cross_ecosystem" group key, which caps a
     group's crossExposureScore at 80 via min() and adds a note through
     `compute_cross_exposure_with_notes()` -- tested on synthetic registries
     (section 4, TestCrossEcosystemFold) and structurally on the shipped GROUPS
     with no RPC (TestCrossEcosystemFoldOnTheRealRegistry).

Production-bug investigation (reported, not fixed -- scripts/lib/signer_overlap.py
is never modified by this file): does an `unresolved_note` group's real
known_eoa/safes entries (when it happens to have any alongside the note)
get excluded from OTHER groups' overlap counts, or do they still silently
feed the shared `registry` even though the note-bearing group's OWN score
is always forced to 100? `TestUnresolvedNoteRegistryLeak` below traces this
by hand-constructing exactly that shape and asserting on the CURRENT
(as-shipped) behavior -- see that class's docstring for the finding.
"""
import os
import sys
import unittest

from web3 import Web3 as RealWeb3
from web3.exceptions import ContractLogicError

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from lib import signer_overlap  # noqa: E402


# ===========================================================================
# FakeW3 for _safe_owners -- controllable .eth.contract(address=, abi=)
# ===========================================================================
class _FakeContractCall:
    def __init__(self, value):
        self._value = value

    def call(self):
        if isinstance(self._value, BaseException):
            raise self._value
        return self._value


class _FakeContractFunctions:
    def __init__(self, address, results):
        self._address = address
        self._results = results

    def __getattr__(self, function_name):
        def make_call(*args):
            key = (self._address, function_name)
            if key not in self._results:
                raise AssertionError(f"FakeContract: no fixture registered for {key}")
            return _FakeContractCall(self._results[key])
        return make_call


class _FakeContract:
    def __init__(self, address, results):
        self.functions = _FakeContractFunctions(address, results)


class FakeEth:
    def __init__(self, contract_results=None):
        self._contract_results = contract_results or {}

    def contract(self, address, abi=None):
        # Deliberately keyed on address+function-name only, not on `abi` --
        # the module always passes address as a positional-or-keyword and
        # abi as a keyword; either call shape lands here the same way.
        return _FakeContract(address, self._contract_results)


class FakeW3:
    def __init__(self, contract_results=None):
        self.eth = FakeEth(contract_results)


def _addr(n):
    """A deterministic, valid 20-byte hex address for slot n (checksummed)."""
    return RealWeb3.to_checksum_address("0x" + hex(n)[2:].zfill(40))


# ===========================================================================
# 1. _safe_owners -- the module's own read-primitive boundary
# ===========================================================================
class TestSafeOwnersReadPrimitive(unittest.TestCase):
    SAFE_ADDR = _addr(0xA1)

    def test_standard_safe_succeeds_never_reaches_fallback(self):
        owner1, owner2 = _addr(1), _addr(2)
        # getSigners deliberately left unregistered: if the code wrongly fell
        # through to the fallback, the fake would raise AssertionError
        # ("no fixture registered") instead of quietly returning something
        # plausible, so this test would fail loudly rather than passing by
        # accident.
        w3 = FakeW3(contract_results={
            (self.SAFE_ADDR, "getOwners"): [owner1, owner2],
        })
        result = signer_overlap._safe_owners(w3, self.SAFE_ADDR)
        self.assertEqual(result, [owner1, owner2])

    def test_safe_reverts_then_custom_multisig_fallback_succeeds(self):
        signer1, signer2 = _addr(3), _addr(4)
        w3 = FakeW3(contract_results={
            (self.SAFE_ADDR, "getOwners"): ContractLogicError("execution reverted: not a Safe"),
            (self.SAFE_ADDR, "getSigners"): [signer1, signer2],
        })
        result = signer_overlap._safe_owners(w3, self.SAFE_ADDR)
        self.assertEqual(result, [signer1, signer2])

    def test_both_paths_revert_returns_none_does_not_raise(self):
        w3 = FakeW3(contract_results={
            (self.SAFE_ADDR, "getOwners"): ContractLogicError("execution reverted"),
            (self.SAFE_ADDR, "getSigners"): ContractLogicError("execution reverted: no such function"),
        })
        result = signer_overlap._safe_owners(w3, self.SAFE_ADDR)
        self.assertIsNone(result)

    def test_a_persistent_network_failure_on_getowners_raises_rpcunavailable(self):
        # ADDED 2026-09-22: a confirmed revert (ContractLogicError) still falls through to the
        # custom-multisig ABI, tested above -- but a genuine network failure must NOT: it must
        # raise immediately, not be silently taken for "not a Safe" and fall through.
        w3 = FakeW3(contract_results={
            (self.SAFE_ADDR, "getOwners"): ConnectionError("boom"),
        })
        with self.assertRaises(signer_overlap.RpcUnavailable):
            signer_overlap._safe_owners(w3, self.SAFE_ADDR)

    def test_a_persistent_network_failure_on_getsigners_after_a_confirmed_revert_raises(self):
        w3 = FakeW3(contract_results={
            (self.SAFE_ADDR, "getOwners"): ContractLogicError("execution reverted: not a Safe"),
            (self.SAFE_ADDR, "getSigners"): ConnectionError("boom"),
        })
        with self.assertRaises(signer_overlap.RpcUnavailable):
            signer_overlap._safe_owners(w3, self.SAFE_ADDR)

    def test_returned_owners_are_checksummed_even_if_fake_returns_lowercase(self):
        lower_owner = "0x" + "5" * 40
        w3 = FakeW3(contract_results={
            (self.SAFE_ADDR, "getOwners"): [lower_owner],
        })
        result = signer_overlap._safe_owners(w3, self.SAFE_ADDR)
        self.assertEqual(result, [RealWeb3.to_checksum_address(lower_owner)])


# ===========================================================================
# 2. compute_cross_exposure -- pure aggregation over (monkeypatched) GROUPS
# ===========================================================================
class _ComputeCrossExposureTestBase(unittest.TestCase):
    """Shared monkeypatch plumbing: replaces signer_overlap.GROUPS and
    signer_overlap._safe_owners for the duration of one test, restoring both
    via addCleanup -- same pattern this project uses for every other
    module-level monkeypatch (see test_cross_ecosystem_fixes.py,
    test_robinhood_event_replay_scorers.py's _patch_helpers, etc.)."""

    def _set_groups(self, groups):
        original = signer_overlap.GROUPS
        signer_overlap.GROUPS = groups
        self.addCleanup(lambda: setattr(signer_overlap, "GROUPS", original))

    def _set_safe_owners(self, mapping):
        """mapping: {safe_addr: list-of-owner-addrs-or-None-or-an-exception-INSTANCE}. Missing keys
        raise loudly rather than silently returning None, so a test that
        forgets to register a Safe address fails with a clear error instead
        of a confusing wrong score. A mapped exception INSTANCE (ADDED
        2026-09-22, e.g. signer_overlap.RpcUnavailable(...)) is raised, not
        returned -- lets a test simulate a persistent network failure
        distinctly from a confirmed revert (None)."""
        original = signer_overlap._safe_owners

        def fake(w3, addr):
            if addr not in mapping:
                raise AssertionError(f"no fake _safe_owners fixture for {addr}")
            value = mapping[addr]
            if isinstance(value, BaseException):
                raise value
            return value

        signer_overlap._safe_owners = fake
        self.addCleanup(lambda: setattr(signer_overlap, "_safe_owners", original))


class TestComputeCrossExposure(_ComputeCrossExposureTestBase):
    def test_two_groups_sharing_zero_signers_both_score_100(self):
        self._set_groups({
            "alpha": {"targets": [_addr(1)], "known_eoa": [_addr(0x10)], "safes": []},
            "beta": {"targets": [_addr(2)], "known_eoa": [_addr(0x20)], "safes": []},
        })
        self._set_safe_owners({})
        result = signer_overlap.compute_cross_exposure(w3=None)
        self.assertEqual(result[_addr(1)], 100)
        self.assertEqual(result[_addr(2)], 100)

    def test_shared_known_eoa_drops_both_groups_to_80_and_every_target_inherits_it(self):
        shared = _addr(0x99)
        self._set_groups({
            "alpha": {"targets": [_addr(1), _addr(2)], "known_eoa": [shared], "safes": []},
            "beta": {"targets": [_addr(3)], "known_eoa": [shared], "safes": []},
        })
        self._set_safe_owners({})
        result = signer_overlap.compute_cross_exposure(w3=None)
        # both of alpha's targets must inherit the SAME group-level score
        self.assertEqual(result[_addr(1)], 80)
        self.assertEqual(result[_addr(2)], 80)
        self.assertEqual(result[_addr(3)], 80)

    def test_overlap_discovered_through_live_safe_resolution_not_literal_known_eoa_match(self):
        # The whole point of this module: alpha's Safe owner (resolved live
        # via the faked _safe_owners) turns out to be the SAME address beta
        # lists as a bare known_eoa. Nothing in the two groups' literal
        # known_eoa lists matches -- the overlap only exists once alpha's
        # Safe is actually resolved.
        safe_addr = _addr(0xAA)
        shared_via_safe = _addr(0xBB)
        self._set_groups({
            "alpha": {"targets": [_addr(1)], "known_eoa": [], "safes": [safe_addr]},
            "beta": {"targets": [_addr(2)], "known_eoa": [shared_via_safe], "safes": []},
        })
        self._set_safe_owners({safe_addr: [shared_via_safe]})
        result = signer_overlap.compute_cross_exposure(w3=None)
        self.assertEqual(result[_addr(1)], 80)
        self.assertEqual(result[_addr(2)], 80)

    def test_three_way_sharing_each_group_counts_the_other_two_only(self):
        shared = _addr(0x77)
        self._set_groups({
            "g1": {"targets": [_addr(1)], "known_eoa": [shared], "safes": []},
            "g2": {"targets": [_addr(2)], "known_eoa": [shared], "safes": []},
            "g3": {"targets": [_addr(3)], "known_eoa": [shared], "safes": []},
        })
        self._set_safe_owners({})
        result = signer_overlap.compute_cross_exposure(w3=None)
        # 100 - 20*2 = 60 for all three -- each sees exactly the OTHER two,
        # never itself.
        self.assertEqual(result[_addr(1)], 60)
        self.assertEqual(result[_addr(2)], 60)
        self.assertEqual(result[_addr(3)], 60)

    def test_unresolved_safe_this_run_does_not_crash_and_group_still_scores_from_what_did_resolve(self):
        # g1's Safe fails to resolve this run (_safe_owners -> None, hitting
        # `if owners is None: continue`), but g1 ALSO has a known_eoa entry
        # that IS shared with g2 -- proving g1 still gets a real,
        # non-crashing score driven by whatever data did resolve, rather
        # than either crashing or silently treating the unresolved Safe as
        # "confirmed zero owners" in a way indistinguishable from a Safe
        # that genuinely has no owners.
        shared = _addr(0x55)
        unresolved_safe = _addr(0x56)
        self._set_groups({
            "g1": {"targets": [_addr(1)], "known_eoa": [shared], "safes": [unresolved_safe]},
            "g2": {"targets": [_addr(2)], "known_eoa": [shared], "safes": []},
        })
        self._set_safe_owners({unresolved_safe: None})
        result = signer_overlap.compute_cross_exposure(w3=None)
        self.assertEqual(result[_addr(1)], 80)
        self.assertEqual(result[_addr(2)], 80)

    def test_a_persistent_network_failure_on_any_safe_propagates_not_silently_narrows(self):
        # ADDED 2026-09-22, REVISED same day after adversarial review (see
        # scripts/lib/signer_overlap.py's own docstring on compute_cross_exposure_with_notes for
        # the full story): a first version of this fix caught RpcUnavailable per-Safe and marked
        # just the OWNING group unresolved. That was unsound -- `registry` is GLOBAL, so the
        # missing Safe's owners silently vanish from every OTHER group's overlap count too, not
        # just the one that owns the failing Safe, and a group with no Safe of its own (all
        # known_eoa) could never be marked unresolved while still getting silently pulled up by the
        # same missing signer set. Proven on the real registry (arcus/arcus_perps_bridgevault):
        # rate-limiting arcus's one Safe "fixed" arcus's own score but left arcus_perps_bridgevault
        # silently wrong, reproducing exactly the risk-under-estimation direction this whole fix
        # exists to close. The only sound fix: don't try to contain the damage locally at all -- let
        # it propagate, and rely on score_all()'s EXISTING outer catch (scripts/lib/scorers.py) to
        # force EVERY target's crossExposureScore to 100 with an honest note, not just the directly
        # affected ones. This test proves the propagation half of that; TestScoreAllFallback in
        # scripts/lib/tests/test_scorers.py (if present) or an equivalent proves the catching half.
        shared = _addr(0x55)
        unresolved_safe = _addr(0x56)
        self._set_groups({
            "g1": {"targets": [_addr(1)], "known_eoa": [shared], "safes": [unresolved_safe]},
            "g2": {"targets": [_addr(2)], "known_eoa": [shared], "safes": []},
        })
        self._set_safe_owners({unresolved_safe: signer_overlap.RpcUnavailable("network blip")})
        with self.assertRaises(signer_overlap.RpcUnavailable):
            signer_overlap.compute_cross_exposure_with_notes(w3=None)

    def test_compute_cross_exposure_the_notes_free_wrapper_also_propagates(self):
        # scripts/prepared_pushes/2026-09-20-robinhood-index16-4-new-targets.py imports
        # compute_cross_exposure() directly (not through score_all()'s protective wrapper) -- it
        # must see the same RpcUnavailable, not a silently-narrowed partial result, so it aborts
        # (consistent with its own "any mismatch aborts" safety philosophy) rather than broadcasting
        # a wrong crossExposureScore with no note at all (that wrapper drops notes entirely).
        unresolved_safe = _addr(0x58)
        self._set_groups({
            "g1": {"targets": [_addr(1)], "known_eoa": [], "safes": [unresolved_safe]},
        })
        self._set_safe_owners({unresolved_safe: signer_overlap.RpcUnavailable("network blip")})
        with self.assertRaises(signer_overlap.RpcUnavailable):
            signer_overlap.compute_cross_exposure(w3=None)

    def test_a_confirmed_revert_still_does_not_propagate_only_network_failures_do(self):
        # Contrast case, so the two tests above aren't trivially satisfied by "raises on anything":
        # a confirmed revert (_safe_owners -> None) must still NOT raise and still score from
        # whatever did resolve -- see test_unresolved_safe_this_run_does_not_crash_and_group_still_
        # scores_from_what_did_resolve above, which already covers this exact contract and remains
        # unchanged by this revision.
        shared = _addr(0x55)
        reverting_safe = _addr(0x59)
        self._set_groups({
            "g1": {"targets": [_addr(1)], "known_eoa": [shared], "safes": [reverting_safe]},
            "g2": {"targets": [_addr(2)], "known_eoa": [shared], "safes": []},
        })
        self._set_safe_owners({reverting_safe: None})  # a confirmed revert, not RpcUnavailable
        result = signer_overlap.compute_cross_exposure(w3=None)
        self.assertEqual(result[_addr(1)], 80)
        self.assertEqual(result[_addr(2)], 80)

    def test_unresolved_note_group_always_scores_100_even_with_signers_that_would_otherwise_lower_it(self):
        # Same shape as the real spark_savings/ekubo entries (known_eoa: [],
        # safes: [], plus "unresolved_note") except this synthetic group is
        # deliberately GIVEN a known_eoa that WOULD produce a lower score if
        # the note weren't honored, to prove the note truly overrides the
        # computed overlap rather than just happening to coincide with a
        # group that has no signers anyway.
        shared = _addr(0x66)
        self._set_groups({
            "noted": {
                "targets": [_addr(1)],
                "known_eoa": [shared],
                "safes": [],
                "unresolved_note": "Executor is a self-administering contract, not a Safe.",
            },
            "other": {"targets": [_addr(2)], "known_eoa": [shared], "safes": []},
        })
        self._set_safe_owners({})
        result = signer_overlap.compute_cross_exposure(w3=None)
        self.assertEqual(result[_addr(1)], 100)  # forced flat 100 by the note

    def test_floor_at_zero_not_negative_with_five_plus_shared_groups(self):
        # 7 groups all sharing one signer -> each sees 6 "others" ->
        # 100 - 20*6 = -20, which must floor at 0, not report -20.
        shared = _addr(0x88)
        groups = {
            f"g{i}": {"targets": [_addr(i)], "known_eoa": [shared], "safes": []}
            for i in range(7)
        }
        self._set_groups(groups)
        self._set_safe_owners({})
        result = signer_overlap.compute_cross_exposure(w3=None)
        for i in range(7):
            self.assertEqual(result[_addr(i)], 0)

    def test_self_exclusion_a_solo_groups_own_key_never_counts_as_a_shared_other_group(self):
        # `registry[s] - {key}` in compute_cross_exposure must exclude the
        # group's OWN key from its own shared_groups count. This group's
        # Safe owner resolves to the SAME address already listed in its own
        # known_eoa -- so the registry entry for that signer is populated by
        # nothing but this one group's own key. If `- {key}` were
        # accidentally omitted, shared_groups would incorrectly gain this
        # group's own key (every group registers itself for each of its own
        # signers), giving 100-20*1=80 for a group with genuinely ZERO
        # overlap with any OTHER group. The correct, self-excluding
        # algorithm must score it 100.
        own_signer = _addr(0x11)
        own_safe = _addr(0x12)
        self._set_groups({
            "solo": {"targets": [_addr(1)], "known_eoa": [own_signer], "safes": [own_safe]},
        })
        self._set_safe_owners({own_safe: [own_signer]})  # redundant with known_eoa, on purpose
        result = signer_overlap.compute_cross_exposure(w3=None)
        self.assertEqual(result[_addr(1)], 100)

    def test_return_value_keys_every_target_under_its_checksummed_address(self):
        lowercase_target = "0x" + "c" * 40
        self._set_groups({
            "alpha": {"targets": [lowercase_target], "known_eoa": [], "safes": []},
        })
        self._set_safe_owners({})
        result = signer_overlap.compute_cross_exposure(w3=None)
        checksummed = RealWeb3.to_checksum_address(lowercase_target)
        self.assertIn(checksummed, result)
        self.assertNotIn(lowercase_target, result)
        self.assertEqual(result[checksummed], 100)


# ===========================================================================
# 3. Production-bug investigation: does an unresolved_note group's real
#    signers still leak into OTHER groups' overlap counts?
# ===========================================================================
class TestUnresolvedNoteRegistryLeak(_ComputeCrossExposureTestBase):
    """Traced by hand against the real source (scripts/lib/signer_overlap.py):

    The registry-building loop --

        for key, g in GROUPS.items():
            signers = set(Web3.to_checksum_address(a) for a in g.get("known_eoa", []))
            for safe_addr in g.get("safes", []):
                owners = _safe_owners(w3, safe_addr)
                if owners is None:
                    continue
                signers.update(owners)
            group_all_signers[key] = signers
            for s in signers:
                registry.setdefault(s, set()).add(key)

    -- runs unconditionally for EVERY group, `unresolved_note` included: it
    never checks that key before computing `signers` and feeding `registry`.
    Only the SECOND loop (the actual scoring loop) checks
    `g.get("unresolved_note")`, and only to force THAT group's own score to
    100 -- it does nothing to `registry` and never removes the note-bearing
    group's signers from it.

    Net effect: if an `unresolved_note` group ever has a non-empty
    `known_eoa`/`safes` alongside the note (the two REAL current instances,
    spark_savings and ekubo, both happen to have empty known_eoa/safes, so
    this has zero live impact TODAY), that group's signers still populate
    `registry`, and any OTHER group sharing one of those signers gets its
    own shared_groups count -- and therefore its own crossExposureScore --
    penalized because of a group whose own overlap was declared
    not-applicable. This is a real gap in the module's stated purpose
    (flagging cross-protocol signer overlap as a systemic-risk signal):
    an unresolved-note group is exempted from being scored on its overlap,
    but not from COUNTING as another group's overlap. The test below proves
    it against the current, unmodified source (this file never edits
    signer_overlap.py) -- it documents present behavior, it is not a claim
    that this behavior is correct.
    """

    def test_noted_groups_known_eoa_still_inflates_another_groups_shared_count(self):
        shared = _addr(0x33)
        self._set_groups({
            "noted": {
                "targets": [_addr(1)],
                "known_eoa": [shared],
                "safes": [],
                "unresolved_note": "Not applicable this run.",
            },
            "victim": {"targets": [_addr(2)], "known_eoa": [shared], "safes": []},
        })
        self._set_safe_owners({})
        result = signer_overlap.compute_cross_exposure(w3=None)
        # "noted" itself is exempt, forced to 100 regardless:
        self.assertEqual(result[_addr(1)], 100)
        # but "victim" IS penalized for sharing with "noted" -- confirming
        # noted's signer leaked into the shared registry despite noted's
        # own overlap being declared not-applicable.
        self.assertEqual(result[_addr(2)], 80)


# ===========================================================================
# 4. Cross-ecosystem fold (ADDED 2026-09-20): the optional "cross_ecosystem"
#    group key caps crossExposureScore at 80 via min(), never raises it.
# ===========================================================================
class TestCrossEcosystemFold(_ComputeCrossExposureTestBase):
    REASON = "2026-09-20: same committee as the tracked target on another chain"

    def test_flagged_group_alone_scores_80_where_it_used_to_score_100(self):
        self._set_groups({
            "flagged": {
                "targets": [_addr(1), _addr(2)],
                "known_eoa": [_addr(0x10)],
                "safes": [],
                "cross_ecosystem": self.REASON,
            },
        })
        self._set_safe_owners({})
        result = signer_overlap.compute_cross_exposure(w3=None)
        # every target of the group inherits the cap, like any other group-level score
        self.assertEqual(result[_addr(1)], 80)
        self.assertEqual(result[_addr(2)], 80)

    def test_flagged_group_already_lowered_by_within_robinhood_sharing_keeps_the_lower_value(self):
        # 3 groups share one signer -> each would score 60 on within-Robinhood
        # sharing. "flagged" must stay 60 (min(60, 80)), NOT be raised to 80.
        shared = _addr(0x77)
        self._set_groups({
            "flagged": {"targets": [_addr(1)], "known_eoa": [shared], "safes": [], "cross_ecosystem": self.REASON},
            "g2": {"targets": [_addr(2)], "known_eoa": [shared], "safes": []},
            "g3": {"targets": [_addr(3)], "known_eoa": [shared], "safes": []},
        })
        self._set_safe_owners({})
        result = signer_overlap.compute_cross_exposure(w3=None)
        self.assertEqual(result[_addr(1)], 60)
        # ...and the unflagged neighbours are untouched, they were already 60
        self.assertEqual(result[_addr(2)], 60)
        self.assertEqual(result[_addr(3)], 60)

    def test_flagged_group_with_exactly_one_within_sharing_is_80_either_way(self):
        # 100 - 20*1 = 80 within-Robinhood; min(80, 80) = 80, boundary of the cap.
        shared = _addr(0x78)
        self._set_groups({
            "flagged": {"targets": [_addr(1)], "known_eoa": [shared], "safes": [], "cross_ecosystem": self.REASON},
            "g2": {"targets": [_addr(2)], "known_eoa": [shared], "safes": []},
        })
        self._set_safe_owners({})
        result = signer_overlap.compute_cross_exposure(w3=None)
        self.assertEqual(result[_addr(1)], 80)
        self.assertEqual(result[_addr(2)], 80)

    def test_unflagged_group_is_untouched_and_gets_no_note(self):
        self._set_groups({
            "plain": {"targets": [_addr(1)], "known_eoa": [_addr(0x10)], "safes": []},
            "flagged": {"targets": [_addr(2)], "known_eoa": [_addr(0x20)], "safes": [], "cross_ecosystem": self.REASON},
        })
        self._set_safe_owners({})
        scores, notes = signer_overlap.compute_cross_exposure_with_notes(w3=None)
        self.assertEqual(scores[_addr(1)], 100)
        self.assertEqual(scores[_addr(2)], 80)
        self.assertNotIn(_addr(1), notes)

    def test_empty_or_none_cross_ecosystem_value_does_not_flag_the_group(self):
        self._set_groups({
            "empty": {"targets": [_addr(1)], "known_eoa": [], "safes": [], "cross_ecosystem": ""},
            "none": {"targets": [_addr(2)], "known_eoa": [], "safes": [], "cross_ecosystem": None},
        })
        self._set_safe_owners({})
        scores, notes = signer_overlap.compute_cross_exposure_with_notes(w3=None)
        self.assertEqual(scores[_addr(1)], 100)
        self.assertEqual(scores[_addr(2)], 100)
        self.assertEqual(notes, {})

    def test_note_is_present_and_carries_the_reason_for_a_flagged_target(self):
        self._set_groups({
            "flagged": {"targets": [_addr(1)], "known_eoa": [_addr(0x10)], "safes": [], "cross_ecosystem": self.REASON},
        })
        self._set_safe_owners({})
        _, notes = signer_overlap.compute_cross_exposure_with_notes(w3=None)
        self.assertEqual(len(notes[_addr(1)]), 1)
        note = notes[_addr(1)][0]
        self.assertIn("crossExposureScore = 80", note)
        self.assertIn("would be 100", note)  # says what the score would be without the fold
        self.assertIn(self.REASON, note)
        self.assertNotIn(chr(0x2014), note)  # house style: no em-dashes

    def test_note_explains_a_kept_lower_value_when_within_sharing_already_scored_below_the_cap(self):
        shared = _addr(0x79)
        self._set_groups({
            "flagged": {"targets": [_addr(1)], "known_eoa": [shared], "safes": [], "cross_ecosystem": self.REASON},
            "g2": {"targets": [_addr(2)], "known_eoa": [shared], "safes": []},
            "g3": {"targets": [_addr(3)], "known_eoa": [shared], "safes": []},
        })
        self._set_safe_owners({})
        scores, notes = signer_overlap.compute_cross_exposure_with_notes(w3=None)
        self.assertEqual(scores[_addr(1)], 60)
        note = notes[_addr(1)][0]
        self.assertIn("crossExposureScore = 60", note)
        self.assertIn("lower value is kept", note)
        self.assertIn(self.REASON, note)

    def test_every_target_of_a_flagged_group_gets_a_note_keyed_by_checksummed_address(self):
        lowercase_target = "0x" + "c" * 40
        self._set_groups({
            "flagged": {"targets": [lowercase_target, _addr(2)], "known_eoa": [], "safes": [], "cross_ecosystem": self.REASON},
        })
        self._set_safe_owners({})
        scores, notes = signer_overlap.compute_cross_exposure_with_notes(w3=None)
        checksummed = RealWeb3.to_checksum_address(lowercase_target)
        self.assertEqual(scores[checksummed], 80)
        self.assertIn(checksummed, notes)
        self.assertIn(_addr(2), notes)
        self.assertNotIn(lowercase_target, notes)

    def test_compute_cross_exposure_return_shape_is_unchanged_scores_only(self):
        # score_all() does cross_exposure.get(addr, 100): the return value must stay a
        # plain {address: int} dict equal to the first element of the with-notes result.
        self._set_groups({
            "flagged": {"targets": [_addr(1)], "known_eoa": [], "safes": [], "cross_ecosystem": self.REASON},
            "plain": {"targets": [_addr(2)], "known_eoa": [], "safes": []},
        })
        self._set_safe_owners({})
        plain = signer_overlap.compute_cross_exposure(w3=None)
        scores, _ = signer_overlap.compute_cross_exposure_with_notes(w3=None)
        self.assertIsInstance(plain, dict)
        self.assertEqual(plain, scores)
        self.assertEqual(plain, {_addr(1): 80, _addr(2): 100})

    def test_flag_is_applied_after_the_unresolved_note_override_not_instead_of_it(self):
        # A group carrying BOTH keys (none exists today) still gets the cross-ecosystem
        # cap: unresolved_note only says the within-Robinhood side is not applicable.
        self._set_groups({
            "both": {
                "targets": [_addr(1)],
                "known_eoa": [],
                "safes": [],
                "unresolved_note": "Not applicable this run.",
                "cross_ecosystem": self.REASON,
            },
        })
        self._set_safe_owners({})
        result = signer_overlap.compute_cross_exposure(w3=None)
        self.assertEqual(result[_addr(1)], 80)


class TestCrossEcosystemFoldOnTheRealRegistry(_ComputeCrossExposureTestBase):
    """Structural checks against the shipped GROUPS (no RPC): which groups carry
    the flag, that the extra key is invisible to the cross-ecosystem sweep's
    helpers, and that flipping the flags changes ONLY the four intended groups
    (Uniswap's shared L1 Timelock root was added 2026-09-20)."""

    FLAGGED = {"pendle", "morpho_blue", "curve", "uniswap_stack"}

    def test_exactly_the_four_verified_groups_carry_the_flag_with_a_dated_reason(self):
        flagged = {k for k, g in signer_overlap.GROUPS.items() if "cross_ecosystem" in g}
        self.assertEqual(flagged, self.FLAGGED)
        for key in self.FLAGGED:
            reason = signer_overlap.GROUPS[key]["cross_ecosystem"]
            self.assertIsInstance(reason, str)
            self.assertTrue(reason.startswith("2026-09-20:"), reason)
            self.assertNotIn(chr(0x2014), reason)

    def test_sweep_helper_group_root_signers_ignores_the_extra_key(self):
        from lib.cross_ecosystem_overlap import group_root_signers

        def fake_owners(w3, addr):
            return [_addr(0xF0)] if addr == signer_overlap.GROUPS["morpho_blue"]["safes"][0] else [_addr(0xF1)]

        for key in self.FLAGGED:
            g = signer_overlap.GROUPS[key]
            with_key = group_root_signers(None, g, fake_owners)
            without_key = group_root_signers(None, {k: v for k, v in g.items() if k != "cross_ecosystem"}, fake_owners)
            self.assertEqual(with_key, without_key)
            self.assertTrue(with_key)  # non-empty: the key did not swallow the real signers

    def test_flag_changes_only_the_four_groups_on_the_real_registry(self):
        # Fake owners: each Safe's only owner is its own address, so within-Robinhood
        # sharing exists exactly where two groups list the SAME Safe address (the real
        # Steakhouse/Ethena/Turbo/Grove sharing) and nowhere else.
        self._set_safe_owners({
            addr: [RealWeb3.to_checksum_address(addr)]
            for g in signer_overlap.GROUPS.values() for addr in g.get("safes", [])
        })
        with_flags, notes = signer_overlap.compute_cross_exposure_with_notes(w3=None)

        stripped = {k: {kk: vv for kk, vv in g.items() if kk != "cross_ecosystem"} for k, g in signer_overlap.GROUPS.items()}
        self._set_groups(stripped)
        without_flags = signer_overlap.compute_cross_exposure(w3=None)

        flagged_targets = {RealWeb3.to_checksum_address(t) for k in self.FLAGGED for t in stripped[k]["targets"]}

        self.assertEqual(set(with_flags), set(without_flags))
        for target, score in with_flags.items():
            if target in flagged_targets:
                self.assertEqual(score, min(without_flags[target], 80), target)
                self.assertIn(target, notes)
            else:
                self.assertEqual(score, without_flags[target], target)  # every other target exactly as before
                self.assertNotIn(target, notes)
        # ...and on the real registry the four groups have no within-Robinhood sharing,
        # so the fold is exactly the 100 -> 80 the brief expects.
        for target in flagged_targets:
            self.assertEqual(without_flags[target], 100, target)
            self.assertEqual(with_flags[target], 80, target)


if __name__ == "__main__":
    unittest.main()
