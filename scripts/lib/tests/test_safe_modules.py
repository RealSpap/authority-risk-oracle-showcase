"""Tests for scripts/lib/safe_modules.py and scripts/check_safe_modules_guards.py (no RPC)."""
import importlib.util
import os
import sys
import unittest
import unittest.mock

from web3 import Web3 as RealWeb3

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..")))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "..")))
import safe_modules  # noqa: E402


def _a(n):
    return RealWeb3.to_checksum_address("0x" + hex(n)[2:].zfill(40))


SAFE = _a(0x5AFE)
MOD_A, MOD_B = _a(0xA0), _a(0xB0)
GUARD = _a(0x6A)
ZERO = safe_modules.ZERO_ADDRESS
SENT = safe_modules.SENTINEL
KNOWN = {
    MOD_A.lower(): {"analyzed": "2026-09-21", "kind": "module", "name": "Module A", "summary": "checked"},
    GUARD.lower(): {"analyzed": "2026-09-21", "kind": "guard", "name": "Guard G", "summary": "positive control"},
}


class _CallRawFake:
    """call_raw(w3, address, abi, fn, *args, retries) -> the next scripted page, or None. A page
    that's an exception INSTANCE is raised instead of returned -- ADDED 2026-09-22, so tests can
    script the new RpcUnavailable-on-persistent-network-failure contract, not just the old
    None-on-any-failure one."""

    def __init__(self, pages):
        self.pages = list(pages)
        self.calls = []

    def __call__(self, w3, address, abi, fn, *args, retries=4):
        self.calls.append((address, fn, args))
        if not self.pages:
            return None
        page = self.pages.pop(0)
        if isinstance(page, BaseException):
            raise page
        return page


class TestReadModules(unittest.TestCase):
    def _run(self, pages):
        fake = _CallRawFake(pages)
        original = safe_modules.call_raw
        safe_modules.call_raw = fake
        self.addCleanup(lambda: setattr(safe_modules, "call_raw", original))
        return safe_modules.read_modules(None, SAFE), fake

    def test_no_module_is_an_empty_list_not_none(self):
        modules, fake = self._run([([], SENT)])
        self.assertEqual(modules, [])
        self.assertEqual(fake.calls[0][1:], ("getModulesPaginated", (SENT, 10)))

    def test_a_failed_read_is_none_never_an_empty_list(self):
        modules, _ = self._run([None])
        self.assertIsNone(modules)

    def test_one_page(self):
        modules, _ = self._run([([MOD_A.lower(), MOD_B], SENT)])
        self.assertEqual(modules, [MOD_A, MOD_B])

    def test_the_cursor_is_followed_across_pages(self):
        modules, fake = self._run([([MOD_A], MOD_A), ([MOD_B], SENT)])
        self.assertEqual(modules, [MOD_A, MOD_B])
        self.assertEqual(fake.calls[1][2], (MOD_A, 10))  # second page starts at the cursor

    def test_a_failure_on_a_later_page_is_none_not_a_partial_clean_result(self):
        modules, _ = self._run([([MOD_A], MOD_A), None])
        self.assertIsNone(modules)

    def test_rpc_unavailable_on_the_first_page_is_none_not_a_crash(self):
        # ADDED 2026-09-22: call_raw() now RAISES RpcUnavailable on a persistent network failure
        # instead of returning the same None a confirmed revert would (see web3_utils.RpcUnavailable
        # and _read()). read_modules() -- and, through it, gate_findings()'s "info, never blocking"
        # promise -- must still see a plain None, not an uncaught exception.
        modules, _ = self._run([safe_modules.RpcUnavailable("owner() on 0xSAFE: unreadable after 4 attempt(s)")])
        self.assertIsNone(modules)

    def test_rpc_unavailable_does_not_trigger_the_legacy_getModules_fallback(self):
        # A confirmed revert on getModulesPaginated() (the OLD contract's None) means "this Safe
        # genuinely doesn't implement pagination -- try the legacy ABI." A network failure does NOT
        # mean that: falling back to the legacy call on a network blip would waste a call and could
        # itself hit the same network issue, worse, could coincidentally "succeed" with a stale
        # cached response at some intermediary and look like a clean (if empty) read. Confirmed here
        # by asserting the legacy path is never invoked (fake.calls has exactly one entry).
        fake = _CallRawFake([safe_modules.RpcUnavailable("network blip")])
        original = safe_modules.call_raw
        safe_modules.call_raw = fake
        self.addCleanup(lambda: setattr(safe_modules, "call_raw", original))
        modules = safe_modules.read_modules(None, SAFE)
        self.assertIsNone(modules)
        self.assertEqual(len(fake.calls), 1)
        self.assertEqual(fake.calls[0][1], "getModulesPaginated")

    def test_rpc_unavailable_on_the_legacy_fallback_call_is_also_none(self):
        # start == SENTINEL and the FIRST call reverts (None, not RpcUnavailable) -- so the legacy
        # getModules() fallback IS attempted -- but that second call itself hits a persistent
        # network failure.
        fake = _CallRawFake([None, safe_modules.RpcUnavailable("network blip on the legacy call too")])
        original = safe_modules.call_raw
        safe_modules.call_raw = fake
        self.addCleanup(lambda: setattr(safe_modules, "call_raw", original))
        modules = safe_modules.read_modules(None, SAFE)
        self.assertIsNone(modules)
        self.assertEqual(len(fake.calls), 2)
        self.assertEqual(fake.calls[1][1], "getModules")


class TestClassify(unittest.TestCase):
    def test_unread_when_either_read_failed(self):
        self.assertEqual(safe_modules.classify(None, ZERO, KNOWN)["status"], "unread")
        self.assertEqual(safe_modules.classify([], None, KNOWN)["status"], "unread")

    def test_clean_means_no_module_and_a_zero_guard(self):
        self.assertEqual(safe_modules.classify([], ZERO, KNOWN)["status"], "clean")

    def test_analyzed_when_everything_present_is_known(self):
        self.assertEqual(safe_modules.classify([MOD_A], ZERO, KNOWN)["status"], "analyzed")
        self.assertEqual(safe_modules.classify([], GUARD, KNOWN)["status"], "analyzed")
        self.assertEqual(safe_modules.classify([MOD_A], GUARD, KNOWN)["status"], "analyzed")

    def test_one_unknown_module_makes_the_whole_safe_unanalyzed(self):
        v = safe_modules.classify([MOD_A, MOD_B], ZERO, KNOWN)
        self.assertEqual((v["status"], v["unanalyzed"]), ("unanalyzed", [MOD_B]))

    def test_an_unknown_guard_is_unanalyzed_even_with_known_modules(self):
        v = safe_modules.classify([MOD_A], _a(0x66), KNOWN)
        self.assertEqual(v["status"], "unanalyzed")

    def test_lookup_is_case_insensitive(self):
        self.assertEqual(safe_modules.classify([MOD_A.upper().replace("0X", "0x")], ZERO, KNOWN)["status"], "analyzed")

    def test_defaults_to_the_shipped_analyses(self):
        known_module = RealWeb3.to_checksum_address("0xe5FB4576BBED29aC3846CcdE81e2201e72cC5316")
        self.assertEqual(safe_modules.classify([known_module], ZERO)["status"], "analyzed")
        self.assertEqual(safe_modules.classify([_a(0x123456)], ZERO)["status"], "unanalyzed")


class TestNoteFor(unittest.TestCase):
    def test_clean_note_says_the_threshold_is_the_whole_authority(self):
        note = safe_modules.note_for(SAFE, [], ZERO, KNOWN)
        self.assertIn("no module and no guard", note)
        self.assertIn("whole authority", note)

    def test_unread_note_does_not_claim_a_clean_result(self):
        note = safe_modules.note_for(SAFE, None, ZERO, KNOWN)
        self.assertIn("could not be read", note)
        self.assertNotIn("no module", note)

    def test_analyzed_note_carries_what_was_found(self):
        note = safe_modules.note_for(SAFE, [MOD_A], GUARD, KNOWN)
        self.assertIn("Module A: checked", note)
        self.assertIn("guard %s = Guard G: positive control" % GUARD, note)
        self.assertFalse(note.startswith("WARNING"))

    def test_unanalyzed_note_is_a_warning(self):
        note = safe_modules.note_for(SAFE, [MOD_B], ZERO, KNOWN)
        self.assertTrue(note.startswith("WARNING"))
        self.assertIn("NOT ANALYZED", note)


CANON_S = RealWeb3.to_checksum_address("0x41675C099F32341bf84BFc5382aF534df5C7461a")
ODD_S = RealWeb3.to_checksum_address("0x113779dAF982b09f7A9dB64af132AA97496b3999")
NEW_S = RealWeb3.to_checksum_address("0x" + "9f" * 20)
CANON_H = RealWeb3.to_checksum_address("0xfd0732Dc9E303f09fCEf3a7388Ad10A83459Ec99")


class TestSingletonAndFallbackHandler(unittest.TestCase):
    def test_singleton_status(self):
        self.assertEqual(safe_modules.classify_singleton(None), "unread")
        self.assertEqual(safe_modules.classify_singleton(CANON_S), "canonical")
        self.assertEqual(safe_modules.classify_singleton(ODD_S), "analyzed")
        self.assertEqual(safe_modules.classify_singleton(NEW_S), "unanalyzed")

    def test_fallback_handler_status(self):
        self.assertEqual(safe_modules.classify_fallback_handler(None), "unread")
        self.assertEqual(safe_modules.classify_fallback_handler(ZERO), "none")
        self.assertEqual(safe_modules.classify_fallback_handler(CANON_H), "canonical")
        self.assertEqual(safe_modules.classify_fallback_handler(NEW_S), "unanalyzed")

    def test_the_readers_use_slot_zero_and_the_fallback_manager_slot(self):
        calls = []
        original = safe_modules.read_slot_as_address
        safe_modules.read_slot_as_address = lambda w3, address, slot, retries=4: calls.append((address, slot)) or CANON_S
        self.addCleanup(lambda: setattr(safe_modules, "read_slot_as_address", original))
        safe_modules.read_singleton(None, SAFE)
        safe_modules.read_fallback_handler(None, SAFE)
        self.assertEqual(calls[0], (SAFE, "0x0"))
        expected = "0x" + bytes(RealWeb3.keccak(text="fallback_manager.handler.address")).hex()
        self.assertEqual(calls[1], (SAFE, expected))

    def test_all_three_readers_turn_rpc_unavailable_into_none(self):
        # ADDED 2026-09-22: read_slot_as_address() now RAISES RpcUnavailable on ANY failure (never
        # returns None -- eth_getStorageAt can't revert, see its own docstring). read_singleton/
        # read_guard/read_fallback_handler document "None if the read failed" as THEIR OWN contract
        # -- unchanged since before this fix -- so the conversion must happen right here (_slot_or_none),
        # or gate_findings()'s "info, never blocking" promise silently breaks into an uncaught crash.
        original = safe_modules.read_slot_as_address
        safe_modules.read_slot_as_address = lambda w3, address, slot, retries=4: (_ for _ in ()).throw(
            safe_modules.RpcUnavailable(f"storage slot {slot} on {address}: unreadable after 4 attempt(s)")
        )
        self.addCleanup(lambda: setattr(safe_modules, "read_slot_as_address", original))
        self.assertIsNone(safe_modules.read_singleton(None, SAFE))
        self.assertIsNone(safe_modules.read_guard(None, SAFE))
        self.assertIsNone(safe_modules.read_fallback_handler(None, SAFE))

    def test_singleton_notes(self):
        self.assertIn("published Safe build (v1.4.1 Safe)", safe_modules.singleton_note(SAFE, CANON_S))
        self.assertIn("GuardManager.sol", safe_modules.singleton_note(SAFE, ODD_S))
        self.assertTrue(safe_modules.singleton_note(SAFE, NEW_S).startswith("WARNING"))
        self.assertIn("could not be read", safe_modules.singleton_note(SAFE, None))

    def test_tables_are_lowercase_and_the_analysis_is_dated_and_free_of_long_dashes(self):
        for table in (safe_modules.CANONICAL_SINGLETONS, safe_modules.CANONICAL_FALLBACK_HANDLERS, safe_modules.KNOWN_SINGLETON_ANALYSES):
            for addr in table:
                self.assertEqual(addr, addr.lower())
                self.assertTrue(RealWeb3.is_address(addr))
        for info in safe_modules.KNOWN_SINGLETON_ANALYSES.values():
            self.assertRegex(info["analyzed"], r"^\d{4}-\d{2}-\d{2}$")
            self.assertNotIn(chr(0x2014), info["summary"])


class TestGateFindings(unittest.TestCase):
    """gate_findings feeds web3_utils.safe_owners_and_threshold: unanalyzed module or singleton blocks, a failed read never does."""

    def _run(self, modules, singleton, legacy=None):
        originals = (safe_modules.read_modules, safe_modules.read_singleton)
        safe_modules.read_modules = lambda w3, safe, retries=4: modules
        safe_modules.read_singleton = lambda w3, safe, retries=4: singleton
        self.addCleanup(lambda: (setattr(safe_modules, "read_modules", originals[0]), setattr(safe_modules, "read_singleton", originals[1])))
        return safe_modules.gate_findings(None, SAFE)

    KNOWN_MODULE = RealWeb3.to_checksum_address("0xe5FB4576BBED29aC3846CcdE81e2201e72cC5316")

    def test_clean_safe_on_a_published_singleton_has_no_findings(self):
        self.assertEqual(self._run([], CANON_S), ([], []))

    def test_an_analyzed_module_and_an_analyzed_singleton_do_not_block(self):
        self.assertEqual(self._run([self.KNOWN_MODULE], ODD_S), ([], []))

    def test_an_unanalyzed_module_blocks(self):
        blocking, info = self._run([NEW_S], CANON_S)
        self.assertEqual(len(blocking), 1)
        self.assertIn("module(s) not analyzed", blocking[0])
        self.assertIn(NEW_S, blocking[0])
        self.assertEqual(info, [])

    def test_one_unknown_module_among_known_ones_still_blocks_and_names_only_the_unknown(self):
        blocking, _ = self._run([self.KNOWN_MODULE, NEW_S], CANON_S)
        self.assertIn(NEW_S, blocking[0])
        self.assertNotIn(self.KNOWN_MODULE, blocking[0])

    def test_an_unanalyzed_singleton_blocks(self):
        blocking, _ = self._run([], NEW_S)
        self.assertEqual(len(blocking), 1)
        self.assertIn("not a published Safe build and not analyzed", blocking[0])

    def test_unread_modules_or_singleton_are_info_never_blocking(self):
        self.assertEqual(self._run(None, CANON_S), ([], ["modules that could not be read"]))
        self.assertEqual(self._run([], None), ([], ["a singleton that could not be read"]))

    def test_a_safe_without_proxy_passes_only_on_its_pinned_code_hash(self):
        # ADDED 2026-10-05: a zero singleton is a Safe deployed without a proxy; its own code is the logic.
        known = next(iter(safe_modules.KNOWN_PROXYLESS_SAFES))
        original = safe_modules.read_code_hash
        self.addCleanup(lambda: setattr(safe_modules, "read_code_hash", original))
        for code_hash, singleton, blocks in ((known, ZERO, False), ("ab" * 32, ZERO, True), (None, ZERO, True), (known, NEW_S, True)):
            with self.subTest(code_hash=code_hash, singleton=singleton):
                safe_modules.read_code_hash = lambda w3, safe, retries=4, h=code_hash: h
                blocking, info = self._run([], singleton)
                self.assertEqual(bool(blocking), blocks)  # an unread code, another code or a non-zero singleton keep it blocked
                self.assertEqual(info, [])
        safe_modules.read_code_hash = lambda w3, safe, retries=4: known
        self.assertEqual(len(self._run([NEW_S], ZERO)[0]), 1)  # an unanalyzed module still blocks a proxyless Safe

    def test_read_code_hash_is_keccak_of_the_code_and_none_when_unread(self):
        class W3:
            class eth:
                @staticmethod
                def get_code(a):
                    return b"\x60\x00"
        self.assertEqual(safe_modules.read_code_hash(W3, SAFE), RealWeb3.keccak(b"\x60\x00").hex().removeprefix("0x"))

        class Down:
            class eth:
                @staticmethod
                def get_code(a):
                    raise ConnectionError("429")
        with unittest.mock.patch("time.sleep", lambda s: None):
            self.assertIsNone(safe_modules.read_code_hash(Down, SAFE))

    def test_proxyless_table_is_keyed_by_code_hash_dated_and_free_of_long_dashes(self):
        for code_hash, info in safe_modules.KNOWN_PROXYLESS_SAFES.items():
            self.assertRegex(code_hash, r"^[0-9a-f]{64}$")
            self.assertRegex(info["analyzed"], r"^\d{4}-\d{2}-\d{2}$")
            self.assertNotIn(chr(0x2014), info["summary"])
            self.assertIn("byte-identical", info["summary"])

    def test_a_guard_is_not_part_of_the_gate(self):
        # gate_findings never reads the guard: a guard can block, not act as the Safe.
        blocking, info = self._run([], CANON_S)
        self.assertEqual((blocking, info), ([], []))


class TestLegacyModulesFallback(unittest.TestCase):
    def test_a_safe_without_getModulesPaginated_falls_back_to_getModules(self):
        calls = []

        def fake(w3, address, abi, fn, *args, retries=4):
            calls.append(fn)
            return None if fn == "getModulesPaginated" else [MOD_A.lower()]

        original = safe_modules.call_raw
        safe_modules.call_raw = fake
        self.addCleanup(lambda: setattr(safe_modules, "call_raw", original))
        self.assertEqual(safe_modules.read_modules(None, SAFE), [MOD_A])
        self.assertEqual(calls, ["getModulesPaginated", "getModules"])

    def test_when_both_reads_fail_the_result_is_none_not_an_empty_list(self):
        original = safe_modules.call_raw
        safe_modules.call_raw = lambda *a, **k: None
        self.addCleanup(lambda: setattr(safe_modules, "call_raw", original))
        self.assertIsNone(safe_modules.read_modules(None, SAFE))


class TestKnownAnalysesShape(unittest.TestCase):
    def test_every_entry_is_dated_lowercase_and_complete(self):
        for addr, info in safe_modules.KNOWN_ANALYSES.items():
            self.assertEqual(addr, addr.lower())
            self.assertTrue(RealWeb3.is_address(addr))
            self.assertIn(info["kind"], ("module", "guard"))
            self.assertRegex(info["analyzed"], r"^\d{4}-\d{2}-\d{2}$")
            self.assertTrue(info["name"] and info["summary"])
            self.assertNotIn(chr(0x2014), info["summary"])


class TestModuleImplementationAdvisory(unittest.TestCase):
    def test_known_vulnerable_implementation_is_flagged(self):
        info = safe_modules.module_implementation_advisory("0x9646fDAD06d3e24444381f44362a3B0eB343D337")
        self.assertEqual(info["status"], "vulnerable")

    def test_lookup_is_case_insensitive(self):
        info = safe_modules.module_implementation_advisory("0x9646FDAD06D3E24444381F44362A3B0EB343D337")
        self.assertEqual(info["status"], "vulnerable")

    def test_known_patched_implementation_is_not_flagged_vulnerable(self):
        info = safe_modules.module_implementation_advisory("0xF2964CE6161ce0e75964Fe7927cE114cb0B283D5")
        self.assertEqual(info["status"], "patched")

    def test_unknown_implementation_returns_none_not_a_clean_bill(self):
        self.assertIsNone(safe_modules.module_implementation_advisory("0x" + "11" * 20))

    def test_none_input_returns_none(self):
        self.assertIsNone(safe_modules.module_implementation_advisory(None))

    def test_every_entry_is_dated_lowercase_and_complete(self):
        for addr, info in safe_modules.KNOWN_MODULE_IMPLEMENTATION_ADVISORIES.items():
            self.assertEqual(addr, addr.lower())
            self.assertTrue(RealWeb3.is_address(addr))
            self.assertIn(info["status"], ("vulnerable", "patched"))
            self.assertTrue(info["name"] and info["advisory"])
            self.assertNotIn(chr(0x2014), info["advisory"])


class TestSweepScript(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = os.path.abspath(os.path.join(HERE, "..", "..", "check_safe_modules_guards.py"))
        spec = importlib.util.spec_from_file_location("check_safe_modules_guards_under_test", path)
        cls.script = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.script)

    def test_registered_safes_collects_every_group_safe_per_ecosystem(self):
        groups = {"eco-a": {"g1": {"safes": ["0xAA"], "known_eoa": ["0xEE"]}, "g2": {"safes": ["0xaa", "0xBB"]}}, "eco-b": {"g3": {"safes": ["0xAA"]}}}
        out = self.script.registered_safes(groups)
        self.assertEqual(out[("eco-a", "0xaa")], ["g1", "g2"])  # same Safe listed by two groups: one entry
        self.assertEqual(set(out), {("eco-a", "0xaa"), ("eco-a", "0xbb"), ("eco-b", "0xaa")})  # per ecosystem, EOAs ignored

    def test_the_real_registry_lists_the_safes_the_scan_found(self):
        out = self.script.registered_safes(self.script.GROUPS)
        self.assertGreaterEqual(len(out), 70)
        self.assertIn(("robinhood", "0xee27d5ae494300902d90454e8630a3f1c68c9c52"), out)

    def test_the_five_safes_that_carry_a_module_or_guard_are_registered_so_the_sweep_reaches_them(self):
        # An analysis for a Safe the sweep never reads is dead weight; these are the ones found on 2026-09-21.
        out = self.script.registered_safes(self.script.GROUPS)
        for pair in (
            ("robinhood", "0xee27d5ae494300902d90454e8630a3f1c68c9c52"),   # Chainlink Price Feed Admin, Confirmed Transaction Module
            ("arbitrum", "0x423552c0f05baccac5bfa91c6dcf1dc53a0a1641"),    # Security Council Emergency Safe, UpgradeExecutor module
            ("arbitrum", "0xddf609735785bf8c7648fffd12be543ce6740928"),    # Radiant emergency admin, two Hypernative modules
            ("ethereum-l1", "0x3b0aaf6e6fcd4a7ceef8c92c32dfea9e64dc1862"),  # Ethena, EthenaSafeGuard
            ("plasma", "0x2c57434603f21f580c91a3bdc0cc5f3f20278632"),      # Ethena on Plasma, same guard
        ):
            self.assertIn(pair, out)


class TestSafeV150AndChainlinkModulesRecognized(unittest.TestCase):
    """ADDED 2026-09-26: the Safe v1.5.0 SafeL2 and CompatibilityFallbackHandler (a tracked Robinhood Safe migrated to them on
    2026-09-25) are published builds, and the four Chainlink feed-owner Safe modules are the analyzed Confirmed Transaction Module."""

    def test_v150_singleton_and_handler_are_canonical(self):
        self.assertEqual(safe_modules.classify_singleton("0xEdd160fEBBD92E350D4D398fb636302fccd67C7e"), "canonical")
        self.assertEqual(safe_modules.classify_fallback_handler("0x3EfCBb83A4A7AfcB4F68D501E2c2203a38be77f4"), "canonical")

    def test_an_unknown_singleton_is_still_unanalyzed(self):
        self.assertEqual(safe_modules.classify_singleton("0x" + "12" * 20), "unanalyzed")

    def test_chainlink_modules_on_four_chains_are_analyzed(self):
        for addr in ("0x2e1B5a40Edc922bCE489668b11749B8eAbd67f6b", "0xf3c72D97A5Dcf0449e89BBCE1A0581d8d15c0237",
                     "0x7F9971226aEAD3013A5dB7767E59dAc48D01C4f6", "0x412fc13437e86889b6C4c010236da46642D138Fc"):
            self.assertIn(addr.lower(), safe_modules.KNOWN_ANALYSES)
            self.assertEqual(safe_modules.KNOWN_ANALYSES[addr.lower()]["kind"], "module")


if __name__ == "__main__":
    unittest.main()
