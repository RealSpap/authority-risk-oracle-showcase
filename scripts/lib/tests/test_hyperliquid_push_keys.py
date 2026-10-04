"""
Unit tests for `chains/hyperliquid/deploy/push_scores.py::resolve_oracle_keys()`
and `hip3_dex_derived_key()`, added 2026-09-19 with the fix for a real
deploy_testnet finding: the oracle stores scores by `address` only, and two
pairs of tracked Hyperliquid targets share an address (HIP-3 dex `mkts` +
Kinetiq HIP3StakingManager at 0x71f0...29ec, HIP-3 dex `para` + para
StakingVault at 0x8888...6ed3). Before the fix, a push silently overwrote
the dex score with the HyperEVM contract's score (15 in, 13 stored) -- see
`chains/hyperliquid/deploy/README.md`, 2026-09-19 section.

No network access: the scorer is never called, entries are hand-built.
"""
import importlib.util
import os
import unittest

from web3 import Web3

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
PUSH = os.path.join(REPO_ROOT, "chains", "hyperliquid", "deploy", "push_scores.py")


def _load_push_module():
    import sys
    sys.path.insert(0, os.path.join(REPO_ROOT, "scripts", "lib"))
    sys.path.insert(0, os.path.join(REPO_ROOT, "chains", "hyperliquid"))
    spec = importlib.util.spec_from_file_location("hl_push_scores", PUSH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


push = _load_push_module()

MKTS = "0x71f0019cc7fa79e4f42587fb7b9a817d8d2429ec"
PARA = "0x8888888c43cbb7e1c4132542e46831bffd866ed3"
XYZ = "0x88806a71d74ad0a510b350545c9ae490912f0888"


def _entry(label, target, composite=9):
    return {"label": label, "target": target, "adminKeyScore": 10, "multisigScore": 15, "timelockScore": 0,
            "oracleAuthorityScore": 4, "crossExposureScore": 100, "compositeScore": composite}


class TestDerivedKey(unittest.TestCase):
    def test_same_construction_as_l1_key(self):
        # METHODOLOGY.md 4.7's L1 key uses the same last-20-bytes-of-keccak construction
        l1 = Web3.to_checksum_address(Web3.keccak(text="hyperliquid:hypercore-l1")[-20:])
        self.assertEqual(l1, "0xeA394CD63CA3a5C8A130Bb2b955cC71C22E5ea6C")

    def test_values_pinned(self):
        self.assertEqual(push.hip3_dex_derived_key("mkts"), "0xBF6d3bBCE71dBcE6f4121BfE2E2caD8C77bBc1fC")
        self.assertEqual(push.hip3_dex_derived_key("para"), "0x30E96FBD515243d47703e78581b88cba60f51360")


class TestResolveOracleKeys(unittest.TestCase):
    def test_no_collision_keeps_raw_addresses(self):
        entries = [_entry("HIP-3 dex xyz", XYZ), _entry("Kinetiq HIP3StakingManager (HyperEVM)", MKTS)]
        keys = push.resolve_oracle_keys(entries)
        self.assertEqual(keys, [Web3.to_checksum_address(XYZ), Web3.to_checksum_address(MKTS)])
        self.assertNotIn("oracleKey", entries[0])

    def test_collision_moves_only_the_hip3_dex(self):
        entries = [
            _entry("HIP-3 dex para", PARA, 5),
            _entry("HIP-3 dex mkts", MKTS, 9),
            _entry("Kinetiq HIP3StakingManager (HyperEVM)", MKTS, 4),
            _entry("para StakingVault (HyperEVM)", PARA, 4),
        ]
        keys = push.resolve_oracle_keys(entries)
        self.assertEqual(len(set(keys)), 4)
        self.assertEqual(keys[0], push.hip3_dex_derived_key("para"))
        self.assertEqual(keys[1], push.hip3_dex_derived_key("mkts"))
        self.assertEqual(keys[2], Web3.to_checksum_address(MKTS))  # HyperEVM contract keeps its real address
        self.assertEqual(keys[3], Web3.to_checksum_address(PARA))
        self.assertTrue(any("derived" in n for n in entries[0]["notes"]))

    def test_collision_is_case_insensitive(self):
        entries = [_entry("HIP-3 dex mkts", MKTS), _entry("Kinetiq HIP3StakingManager (HyperEVM)", MKTS.upper().replace("0X", "0x"))]
        keys = push.resolve_oracle_keys(entries)
        self.assertEqual(len(set(keys)), 2)

    def test_unresolvable_collision_refuses(self):
        # two non-HIP-3 entries on one address: no rule applies -> hard failure, never a silent overwrite
        entries = [_entry("Some HyperEVM contract A", MKTS), _entry("Some HyperEVM contract B", MKTS)]
        with self.assertRaises(SystemExit):
            push.resolve_oracle_keys(entries)

    def test_scores_untouched(self):
        entries = [_entry("HIP-3 dex mkts", MKTS, 9), _entry("Kinetiq HIP3StakingManager (HyperEVM)", MKTS, 4)]
        targets, tuples = push.build_targets_and_tuples(entries, 1, b"\x00" * 32)
        self.assertEqual([t[5] for t in tuples], [9, 4])
        self.assertEqual(len(set(targets)), 2)


class TestParseTargetsCsv(unittest.TestCase):
    """Added 2026-09-22 (review of commit 838f5c2, reservation "ASYMMETRIC VALIDATION"):
    filter_by_targets() used to do BOTH the syntax validation (empty/malformed-address checks) AND
    the tracked-key matching, which meant a typo'd/empty --targets only refused AFTER main() paid
    for score_all()'s ~100s live re-derivation across 4 external APIs -- the fix commit's own message
    wrongly claimed this refused fast, copy-pasting a number that actually belonged to --oracle.
    parse_targets_csv() is the syntax-only half, split out so it can run immediately after argument
    parsing (see main()), symmetric with validate_oracle_override()."""

    def test_none_is_a_no_op(self):
        self.assertIsNone(push.parse_targets_csv(None))

    def test_an_empty_or_all_comma_value_refuses(self):
        # REVIEW FINDING (review run, BLOCKING): `--targets ""` (or "," / " " / ",,") used to be
        # treated identically to --targets being omitted -- silently pushing ALL targets, with no
        # "--targets set" disclosure printed, indistinguishable from a deliberate full push.
        for empty in ("", ",", " ", ",,", "  ,  "):
            with self.assertRaises(SystemExit) as cm:
                push.parse_targets_csv(empty)
            self.assertIn("given but empty", str(cm.exception))

    def test_a_malformed_address_refuses_with_a_clean_message_not_a_raw_web3_traceback(self):
        # REVIEW FINDING (reservation): before, a malformed address raised web3's own bare
        # ValueError, inconsistent with the "refuse loudly, name the problem" convention used
        # elsewhere in this module.
        with self.assertRaises(SystemExit) as cm:
            push.parse_targets_csv("0xnotanaddress")
        self.assertIn("malformed address", str(cm.exception))

    def test_checksum_normalizes_and_deduplicates_preserving_request_order(self):
        # REVIEW FINDING (reservation, "THE NEW ORDER-PRESERVATION TEST IS TAUTOLOGICAL"): the
        # earlier version of this test requested MKTS before PARA, and MKTS's checksum address
        # ALSO sorts alphabetically first -- an alphabetical re-sort would have passed it too, so it
        # never actually distinguished "preserved request order" from "silently re-sorted". Fixed by
        # requesting PARA first, which is NOT alphabetical order (checked directly below rather than
        # trusted from a prior description of it, which -- caught here -- had this backwards).
        self.assertLess(push.Web3.to_checksum_address(MKTS), push.Web3.to_checksum_address(PARA))
        result = push.parse_targets_csv(f" {PARA} , {MKTS.upper().replace('0X', '0x')} , {PARA} ")
        self.assertEqual(result, [push.Web3.to_checksum_address(PARA), push.Web3.to_checksum_address(MKTS)])


class TestFilterByTargets(unittest.TestCase):
    """Added 2026-09-22 (backlog item, "aucune correction ciblee n'est possible, c'est tout ou
    rien"): --targets, so a correction to a handful of entries doesn't have to resend everything.
    Takes the ALREADY-VALIDATED list from parse_targets_csv() (or a literal list here, since these
    tests care about the matching logic, not the CSV syntax -- that's TestParseTargetsCsv's job)."""

    def _built(self):
        entries = [_entry("HIP-3 dex xyz", XYZ, 1), _entry("Kinetiq HIP3StakingManager (HyperEVM)", MKTS, 2),
                   _entry("para StakingVault (HyperEVM)", PARA, 3)]
        targets, tuples = push.build_targets_and_tuples(entries, 1, b"\x00" * 32)
        return targets, tuples, entries

    def test_none_is_a_no_op(self):
        targets, tuples, scored = self._built()
        t2, tu2, s2 = push.filter_by_targets(targets, tuples, scored, None)
        self.assertEqual((t2, tu2, s2), (targets, tuples, scored))

    def test_filters_to_only_the_requested_keys(self):
        targets, tuples, scored = self._built()
        wanted = push.parse_targets_csv(f"{MKTS},{PARA}")
        t2, tu2, s2 = push.filter_by_targets(targets, tuples, scored, wanted)
        self.assertEqual(set(t2), {push.Web3.to_checksum_address(MKTS), push.Web3.to_checksum_address(PARA)})
        self.assertEqual(len(t2), 2)
        self.assertEqual(len(tu2), 2)
        self.assertEqual({e["target"] for e in s2}, {MKTS, PARA})

    def test_a_raw_address_that_collided_with_a_hip3_dex_silently_matches_the_other_entry(self):
        # CHARACTERIZATION, not a fix: requesting the raw address of a group where a HIP-3 dex
        # collided with another entry matches whichever entry ISN'T the dex (documented gap in
        # filter_by_targets()'s own docstring -- the dex itself becomes unreachable by its raw
        # address, with no signal that it exists under a different key).
        entries = [_entry("HIP-3 dex mkts", MKTS, 9), _entry("Kinetiq HIP3StakingManager (HyperEVM)", MKTS, 4)]
        targets, tuples = push.build_targets_and_tuples(entries, 1, b"\x00" * 32)
        t2, tu2, s2 = push.filter_by_targets(targets, tuples, entries, push.parse_targets_csv(MKTS))
        self.assertEqual(s2[0]["label"], "Kinetiq HIP3StakingManager (HyperEVM)")  # not the dex

    def test_a_single_target_narrows_to_one(self):
        targets, tuples, scored = self._built()
        t2, tu2, s2 = push.filter_by_targets(targets, tuples, scored, push.parse_targets_csv(MKTS))
        self.assertEqual(len(t2), 1)
        self.assertEqual(s2[0]["target"], MKTS)

    def test_an_unknown_address_refuses_loudly_rather_than_pushing_nothing(self):
        targets, tuples, scored = self._built()
        bogus = "0x000000000000000000000000000000000000dead"  # well-formed, just not a tracked target
        with self.assertRaises(SystemExit) as cm:
            push.filter_by_targets(targets, tuples, scored, push.parse_targets_csv(bogus))
        self.assertIn(push.Web3.to_checksum_address(bogus), str(cm.exception))

    def test_one_good_and_one_bogus_address_still_refuses_the_whole_call(self):
        # a partial typo must not silently narrow to just the good one -- REFUSING is all-or-nothing
        # on the REQUEST, independent of the all-or-nothing-ness of the resulting push itself.
        targets, tuples, scored = self._built()
        wanted = push.parse_targets_csv(f"{MKTS},0x000000000000000000000000000000000000dead")
        with self.assertRaises(SystemExit):
            push.filter_by_targets(targets, tuples, scored, wanted)

    def test_matches_the_resolved_oracle_key_not_only_the_raw_scorer_target(self):
        # PARA and MKTS collide (both HIP-3 dex + HyperEVM contract at the same address) -- after
        # resolve_oracle_keys() the dex moves to its DERIVED key. --targets must be able to select
        # that derived key, since that's the address actually stored on-chain.
        entries = [_entry("HIP-3 dex mkts", MKTS, 9), _entry("Kinetiq HIP3StakingManager (HyperEVM)", MKTS, 4)]
        targets, tuples = push.build_targets_and_tuples(entries, 1, b"\x00" * 32)
        derived = push.hip3_dex_derived_key("mkts")
        t2, tu2, s2 = push.filter_by_targets(targets, tuples, entries, push.parse_targets_csv(derived))
        self.assertEqual(t2, [derived])
        self.assertEqual(s2[0]["label"], "HIP-3 dex mkts")


class TestParseArgs(unittest.TestCase):
    def test_defaults_match_the_original_all_or_nothing_behaviour(self):
        args = push.parse_args([])
        self.assertFalse(args.dry_run)
        self.assertIsNone(args.targets)
        self.assertIsNone(args.oracle)

    def test_dry_run_flag(self):
        self.assertTrue(push.parse_args(["--dry-run"]).dry_run)

    def test_push_guard_escape_flags_both_forms(self):
        # ADDED 2026-10-04: argparse rejected these flags, so a held entry blocked the Hyperliquid push for good.
        a = push.parse_args(["--dry-run", "--accept-held", f"{MKTS},{PARA}", "--skip-published-check"])
        self.assertEqual(a.accept_held, f"{MKTS},{PARA}")
        self.assertTrue(a.skip_published_check)
        self.assertEqual(push.parse_args([f"--accept-held={MKTS}"]).accept_held, MKTS)
        self.assertFalse(push.parse_args([]).skip_published_check)

    def test_targets_and_oracle_flags(self):
        args = push.parse_args(["--targets", f"{MKTS},{PARA}", "--oracle", XYZ])
        self.assertEqual(args.targets, f"{MKTS},{PARA}")
        self.assertEqual(args.oracle, XYZ)

    def test_all_three_flags_combine(self):
        args = push.parse_args(["--dry-run", "--targets", MKTS, "--oracle", XYZ])
        self.assertTrue(args.dry_run)
        self.assertEqual(args.targets, MKTS)
        self.assertEqual(args.oracle, XYZ)


class TestValidateOracleOverride(unittest.TestCase):
    """Added 2026-09-22 (review of commit 210aed6, reservation): --oracle used to be validated only
    at the point the transaction is built, several minutes into a live run, with a raw web3
    ValueError; and `--oracle ""` fell straight through to the ORACLE_ADDRESS environment fallback,
    the same "empty silently treated as absent" bug --targets had."""

    def test_none_is_a_no_op(self):
        self.assertIsNone(push.validate_oracle_override(None))

    def test_a_valid_address_is_checksum_normalized(self):
        self.assertEqual(push.validate_oracle_override(XYZ.lower()), push.Web3.to_checksum_address(XYZ))

    def test_an_empty_value_refuses_rather_than_silently_falling_back_to_the_environment(self):
        for empty in ("", "  "):
            with self.assertRaises(SystemExit) as cm:
                push.validate_oracle_override(empty)
            self.assertIn("given but empty", str(cm.exception))

    def test_a_malformed_address_refuses_with_a_clean_message(self):
        with self.assertRaises(SystemExit) as cm:
            push.validate_oracle_override("0xnotanaddress")
        self.assertIn("not a valid address", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
