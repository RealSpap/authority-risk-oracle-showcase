"""
Unit tests for scripts/lib/cross_ecosystem_overlap.py's pure set logic --
no live RPC. group_root_signers() itself (which does call a live
owner-resolution function) is exercised by scripts/check_cross_ecosystem_overlap.py
against real chains, not here.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from lib import cross_ecosystem_overlap  # noqa: E402
from lib.cross_ecosystem_overlap import find_cross_ecosystem_overlaps, find_identical_safe_addresses, find_subset_committees, group_root_signers  # noqa: E402

# NOT `from lib.web3_utils import RpcUnavailable`. UPDATED 2026-09-22 (action,
# scripts/lib/rpc_unavailable.py): `web3_utils` (bare) and `lib.web3_utils` ARE now two separate
# cached modules -- `sys.modules['web3_utils']` and `sys.modules['lib.web3_utils']` remain distinct
# entries, same as before -- but their `.RpcUnavailable` attributes are no longer two different
# class objects: both are aliases (`RpcUnavailable = rpc_unavailable.RpcUnavailable`) pointing at the
# single class in `sys.modules['rpc_unavailable']`, imported bare from both copies of web3_utils.py.
# This project's OWN earlier attempt (action, REJECTED as #183) got bitten by exactly the
# confusion this comment used to encode: the test here was written correctly, importing the module
# object and referencing its attribute, but the real production caller
# (scripts/check_cross_ecosystem_overlap.py) still hit a mismatched class until the canonicalization
# landed. Referencing RpcUnavailable through the already-imported module, as done below, remains the
# right pattern regardless -- it is what stays correct if a future importer ever reaches
# scripts/lib/rpc_unavailable.py through a non-canonical path (`from lib import rpc_unavailable`
# instead of the bare `import rpc_unavailable` web3_utils.py itself uses), which rpc_unavailable.py's
# own docstring says never to do but nothing enforces.
RpcUnavailable = cross_ecosystem_overlap.RpcUnavailable


def _addr(n: int) -> str:
    # A valid, deterministic 20-byte hex address built from a digit repeated
    # 40 times -- never hand-typed, so there's no transcription risk (the
    # exact trap this project's own discipline exists to avoid).
    return "0x" + str(n) * 40


class TestFindCrossEcosystemOverlaps(unittest.TestCase):
    def test_no_overlap_returns_empty(self):
        groups = {
            ("robinhood", "a"): {_addr(1), _addr(2)},
            ("ethereum-l1", "b"): {_addr(3), _addr(4)},
        }
        self.assertEqual(find_cross_ecosystem_overlaps(groups), {})

    def test_shared_signer_across_two_ecosystems_is_found(self):
        shared = _addr(9)
        groups = {
            ("robinhood", "a"): {_addr(1), shared},
            ("ethereum-l1", "b"): {_addr(3), shared},
        }
        overlaps = find_cross_ecosystem_overlaps(groups)
        self.assertIn(shared, overlaps)
        self.assertEqual(overlaps[shared], {("robinhood", "a"), ("ethereum-l1", "b")})

    def test_same_signer_in_two_groups_of_the_SAME_ecosystem_is_not_a_cross_ecosystem_overlap(self):
        # This is exactly what scripts/lib/signer_overlap.py's own
        # compute_cross_exposure() already covers (within Robinhood Chain) --
        # this module's job starts where that one stops.
        shared = _addr(9)
        groups = {
            ("robinhood", "a"): {_addr(1), shared},
            ("robinhood", "b"): {_addr(3), shared},
        }
        self.assertEqual(find_cross_ecosystem_overlaps(groups), {})

    def test_signer_in_three_ecosystems_lists_all_three(self):
        shared = _addr(9)
        groups = {
            ("robinhood", "a"): {shared},
            ("ethereum-l1", "b"): {shared},
            ("base", "c"): {shared},
        }
        overlaps = find_cross_ecosystem_overlaps(groups)
        self.assertEqual(overlaps[shared], {("robinhood", "a"), ("ethereum-l1", "b"), ("base", "c")})

    def test_empty_input(self):
        self.assertEqual(find_cross_ecosystem_overlaps({}), {})


class TestFindIdenticalSafeAddresses(unittest.TestCase):
    def test_no_shared_address_returns_empty(self):
        safes = {
            ("robinhood", "a"): _addr(1),
            ("ethereum-l1", "b"): _addr(2),
        }
        self.assertEqual(find_identical_safe_addresses(safes), {})

    def test_identical_address_on_two_chains_is_found(self):
        # The ether.fi/Curve/Aave-style pattern multisig-overlap
        # documented: the SAME Safe (same address, CREATE2) redeployed on
        # more than one chain.
        shared = _addr(7)
        safes = {
            ("robinhood", "vault-a"): shared,
            ("base", "vault-b"): shared,
        }
        overlaps = find_identical_safe_addresses(safes)
        self.assertIn(shared, overlaps)
        self.assertEqual(overlaps[shared], {("robinhood", "vault-a"), ("base", "vault-b")})

    def test_case_insensitive_matching(self):
        # Web3.to_checksum_address normalizes case -- the same address typed
        # with different capitalization in two ecosystems' hardcoded lists
        # must still match.
        safes = {
            ("robinhood", "a"): "0x" + "a" * 40,
            ("base", "b"): "0x" + "A" * 40,
        }
        overlaps = find_identical_safe_addresses(safes)
        self.assertEqual(len(overlaps), 1)

    def test_same_ecosystem_duplicate_address_is_not_flagged(self):
        # Two group keys in the SAME ecosystem happening to reference the
        # same Safe isn't a cross-ecosystem finding.
        shared = _addr(7)
        safes = {
            ("robinhood", "a"): shared,
            ("robinhood", "b"): shared,
        }
        self.assertEqual(find_identical_safe_addresses(safes), {})


class TestFindSubsetCommittees(unittest.TestCase):
    """Closes the real gap the Monad/Robinhood Morpho vault finding exposed:
    find_cross_ecosystem_overlaps() flags individual shared signers, but
    doesn't say a SMALLER committee is entirely contained in a LARGER one --
    that had to be reasoned about by hand before this function existed."""

    def test_no_containment_returns_empty(self):
        groups = {
            ("robinhood", "a"): {_addr(1), _addr(2)},
            ("base", "b"): {_addr(3), _addr(4)},
        }
        self.assertEqual(find_subset_committees(groups), [])

    def test_full_containment_across_ecosystems_is_found(self):
        smaller = {_addr(1), _addr(2)}
        larger = smaller | {_addr(3), _addr(4), _addr(5)}
        groups = {
            ("monad", "vault_curator"): smaller,
            ("robinhood", "steakhouse"): larger,
        }
        results = find_subset_committees(groups)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["smaller"], ("monad", "vault_curator"))
        self.assertEqual(results[0]["larger"], ("robinhood", "steakhouse"))
        self.assertEqual(results[0]["shared"], smaller)

    def test_equal_sets_are_flagged_too(self):
        same = {_addr(1), _addr(2), _addr(3)}
        groups = {
            ("base", "morpho_blue"): same,
            ("robinhood", "morpho_blue"): same,
        }
        results = find_subset_committees(groups)
        self.assertEqual(len(results), 1)

    def test_same_ecosystem_containment_is_not_flagged(self):
        # Two groups in the SAME ecosystem containing each other isn't a
        # cross-ecosystem finding -- scripts/lib/signer_overlap.py's own
        # within-Robinhood-Chain check already covers that.
        smaller = {_addr(1)}
        larger = {_addr(1), _addr(2)}
        groups = {
            ("robinhood", "a"): smaller,
            ("robinhood", "b"): larger,
        }
        self.assertEqual(find_subset_committees(groups), [])

    def test_trivial_single_signer_groups_excluded_by_default_min_size(self):
        groups = {
            ("monad", "tiny"): {_addr(1)},
            ("robinhood", "big"): {_addr(1), _addr(2), _addr(3)},
        }
        self.assertEqual(find_subset_committees(groups), [])
        # explicit min_size=1 opts back in
        results = find_subset_committees(groups, min_size=1)
        self.assertEqual(len(results), 1)

    def test_results_sorted_smallest_shared_set_first(self):
        groups = {
            ("monad", "small"): {_addr(1), _addr(2)},
            ("robinhood", "big1"): {_addr(1), _addr(2), _addr(3), _addr(4)},
            ("plasma", "medium"): {_addr(5), _addr(6), _addr(7)},
            ("robinhood", "big2"): {_addr(5), _addr(6), _addr(7), _addr(8), _addr(9)},
        }
        results = find_subset_committees(groups)
        sizes = [len(r["shared"]) for r in results]
        self.assertEqual(sizes, sorted(sizes))


class TestGroupRootSigners(unittest.TestCase):
    def test_known_eoa_only(self):
        group = {"known_eoa": [_addr(1), _addr(2)], "safes": []}
        signers = group_root_signers(None, group, safe_owners_fn=lambda w3, addr: None)
        self.assertEqual(len(signers), 2)  # both known_eoa addresses present (case-normalized)

    def test_accepts_plain_list_return_shape(self):
        # signer_overlap.py's own _safe_owners() returns a plain list (or None).
        group = {"known_eoa": [], "safes": ["0x" + "5" * 40]}
        signers = group_root_signers(None, group, safe_owners_fn=lambda w3, addr: [_addr(3), _addr(4)])
        self.assertEqual(len(signers), 2)

    def test_accepts_tuple_return_shape(self):
        # web3_utils.safe_owners_and_threshold() returns (owners, threshold).
        group = {"known_eoa": [], "safes": ["0x" + "5" * 40]}
        signers = group_root_signers(None, group, safe_owners_fn=lambda w3, addr: ([_addr(3), _addr(4)], 2))
        self.assertEqual(len(signers), 2)

    def test_none_from_safe_owners_fn_is_skipped_not_crashed_on(self):
        group = {"known_eoa": [_addr(1)], "safes": ["0x" + "5" * 40]}
        signers = group_root_signers(None, group, safe_owners_fn=lambda w3, addr: None)
        self.assertEqual(len(signers), 1)  # only the known_eoa entry

    def test_a_raising_safe_owners_fn_is_skipped_not_crashed_on(self):
        # ADDED 2026-09-22: web3_utils.safe_owners_and_threshold() (one real safe_owners_fn this
        # gets called with, per scripts/check_cross_ecosystem_overlap.py) now RAISES on a persistent
        # RPC failure instead of returning the same None a confirmed "not a Safe" would (see
        # web3_utils.RpcUnavailable). One bad Safe must not crash the whole group's resolution, let
        # alone the caller's whole multi-group, multi-ecosystem sweep.
        def boom(w3, addr):
            raise RuntimeError(f"{addr}: unreadable after 4 attempt(s)")
        group = {"known_eoa": [_addr(1)], "safes": ["0x" + "5" * 40]}
        signers = group_root_signers(None, group, safe_owners_fn=boom)
        self.assertEqual(len(signers), 1)  # only the known_eoa entry -- the raising Safe is skipped

    def test_rpc_unavailable_is_recognized_by_name_and_recorded_when_incomplete_out_is_passed(self):
        # ADDED 2026-09-22, closes a residual of the same-day live-path fix (see
        # scripts/lib/web3_utils.RpcUnavailable and scripts/lib/signer_overlap.py's own history):
        # this module stays deliberately agnostic about most exception types (it never feeds a live
        # score, see its own header), but a network failure silently narrowing a group's signer set
        # here can still make a real cross-ecosystem overlap go unflagged -- the one thing this
        # sweep exists to catch. incomplete_out lets a caller collect exactly which reads failed.
        group = {"known_eoa": [_addr(1)], "safes": ["0x" + "5" * 40]}
        incomplete = []
        signers = group_root_signers(
            None, group,
            safe_owners_fn=lambda w3, addr: (_ for _ in ()).throw(RpcUnavailable(f"{addr}: unreadable")),
            incomplete_out=incomplete,
        )
        self.assertEqual(len(signers), 1)  # only the known_eoa entry -- still isolated, not crashed
        self.assertEqual(len(incomplete), 1)
        self.assertEqual(incomplete[0][0], "0x" + "5" * 40)
        self.assertIsInstance(incomplete[0][1], RpcUnavailable)

    def test_incomplete_out_defaults_to_none_and_is_optional(self):
        # Existing callers (scripts/check_cross_ecosystem_overlap.py before this date, and every
        # existing test above) never pass incomplete_out -- must keep working unchanged.
        group = {"known_eoa": [_addr(1)], "safes": ["0x" + "5" * 40]}

        def boom(w3, addr):
            raise RpcUnavailable("network blip")
        signers = group_root_signers(None, group, safe_owners_fn=boom)  # no incomplete_out at all
        self.assertEqual(len(signers), 1)

    def test_a_non_rpcunavailable_exception_is_not_recorded_in_incomplete_out(self):
        # A generic exception (a genuine bug, or a fixture error) is still isolated the same way as
        # before -- but it is NOT a network-failure signal, so it must not be recorded as one.
        group = {"known_eoa": [], "safes": ["0x" + "5" * 40]}
        incomplete = []
        signers = group_root_signers(
            None, group,
            safe_owners_fn=lambda w3, addr: (_ for _ in ()).throw(RuntimeError("unrelated bug")),
            incomplete_out=incomplete,
        )
        self.assertEqual(len(signers), 0)
        self.assertEqual(incomplete, [])

    def test_a_raising_safe_does_not_stop_the_next_safe_in_the_same_group(self):
        calls = []

        def flaky(w3, addr):
            calls.append(addr)
            if addr == "0x" + "5" * 40:
                raise RuntimeError("network blip")
            return [_addr(3)]
        group = {"known_eoa": [], "safes": ["0x" + "5" * 40, "0x" + "6" * 40]}
        signers = group_root_signers(None, group, safe_owners_fn=flaky)
        self.assertEqual(signers, {_addr(3)})  # the second (healthy) safe's owner still resolves
        self.assertEqual(len(calls), 2)  # both safes were attempted, the first failing did not stop the loop


class TestRadiantIsInTheSweepRegistry(unittest.TestCase):
    """ADDED 2026-09-20: Radiant's two Safes were checked against the sweep by hand only, until the group
    existed in the registry. Locks the group, its target and both Safes in, so a later edit cannot drop them."""

    def test_radiant_pool_admin_group_lists_the_target_and_both_safes(self):
        from lib.cross_ecosystem_overlap import ARBITRUM_GROUPS
        g = ARBITRUM_GROUPS["radiant_pool_admin"]
        self.assertEqual([a.lower() for a in g["targets"]], ["0xe23b4ae3624fb6f7cdef29bc8ead912f1ede6886"])
        self.assertEqual({a.lower() for a in g["safes"]}, {
            "0x111ceeee040739fd91d29c34c33e6b3e112f2177",  # getPoolAdmin(), 4-of-11
            "0xddf609735785bf8c7648fffd12be543ce6740928",  # getEmergencyAdmin(), 1-of-5
        })
        self.assertEqual(g["known_eoa"], [])

    def test_radiant_target_matches_the_scorer_target(self):
        import importlib.util
        root = os.path.join(os.path.dirname(__file__), "..", "..", "..")
        path = os.path.abspath(os.path.join(root, "chains", "arbitrum-ecosystem", "scorers.py"))
        text = open(path).read()
        from lib.cross_ecosystem_overlap import ARBITRUM_GROUPS
        self.assertIn(ARBITRUM_GROUPS["radiant_pool_admin"]["targets"][0], text)


class TestUniswapDaoTimelockRegistered(unittest.TestCase):
    """ADDED 2026-09-20: Uniswap's Ethereum L1 Governance Timelock is one root identity behind 11 tracked targets on 5
    ecosystems. It is registered like a known EOA in each ecosystem's registry so the live sweep reports it."""

    TIMELOCK = "0x1a9c8182c09f50c8318d769245bea52c32be35bc"
    ALIAS = "0x2bad8182c09f50c8318d769245bea52c32be46cd"  # its Arbitrum form
    EXPECTED_TARGETS = {
        "ETHEREUM_L1_GROUPS": 2, "ARBITRUM_GROUPS": 1, "BASE_GROUPS": 3, "MONAD_GROUPS": 1,
    }

    def test_each_ecosystem_registers_its_uniswap_targets_under_the_timelock_identity(self):
        from lib import cross_ecosystem_overlap as ceo
        for name, count in self.EXPECTED_TARGETS.items():
            g = getattr(ceo, name)["uniswap_dao_timelock"]
            self.assertEqual(len(g["targets"]), count, name)
            self.assertIn(self.TIMELOCK, {a.lower() for a in g["known_eoa"]}, name)
            self.assertEqual(g["safes"], [], name)
        self.assertIn(self.ALIAS, {a.lower() for a in ceo.ARBITRUM_GROUPS["uniswap_dao_timelock"]["known_eoa"]})

    def test_robinhood_uniswap_group_carries_both_forms_of_the_root(self):
        from lib import signer_overlap
        g = signer_overlap.GROUPS["uniswap_stack"]
        self.assertEqual({a.lower() for a in g["known_eoa"]}, {self.TIMELOCK, self.ALIAS})
        self.assertEqual(len(g["targets"]), 4)

    def test_the_sweep_finds_the_shared_root_across_five_ecosystems(self):
        from lib import cross_ecosystem_overlap as ceo
        from lib import signer_overlap
        from web3 import Web3
        eco_groups = {}
        for eco, groups in (("ethereum-l1", ceo.ETHEREUM_L1_GROUPS), ("arbitrum", ceo.ARBITRUM_GROUPS),
                            ("base", ceo.BASE_GROUPS), ("monad", ceo.MONAD_GROUPS), ("robinhood", signer_overlap.GROUPS)):
            key = "uniswap_dao_timelock" if eco != "robinhood" else "uniswap_stack"
            eco_groups[(eco, key)] = {Web3.to_checksum_address(a) for a in groups[key]["known_eoa"]}
        overlaps = ceo.find_cross_ecosystem_overlaps(eco_groups)
        shared = overlaps[Web3.to_checksum_address(self.TIMELOCK)]
        self.assertEqual({eco for eco, _ in shared}, {"ethereum-l1", "arbitrum", "base", "monad", "robinhood"})


if __name__ == "__main__":
    unittest.main()
