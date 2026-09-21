"""
Unit tests for the 2026-09-20 crossExposureScore fold in
`chains/tempo/scripts/methodology_test.py::cross_exposure()`.

Convention decided 2026-09-20 for the whole project: `crossExposureScore`
means "does the same root signer also control ANOTHER tracked target",
cross-ecosystem overlaps included. Tempo's Morpho Blue core is owned by a
5-of-9 Safe whose 9 signers are exactly the Morpho Association committee that
also owns the tracked Morpho Blue cores on Ethereum L1, Base and Robinhood
Chain, so it scores min(within-Tempo value, 80) instead of the within-Tempo
100 it used to read, with a real-finding note on its result.

`cross_exposure()` itself is a pure function of a results list, so most tests
build that list by hand (no RPC). Two more tests cover the wiring: the real
`score_morpho_blue()` through a fake RPC, and `chains/tempo/scorers.py::
score_all()` (whose old `notes = {...}` assignment would have wiped the
finding) with every network-facing scorer stubbed out.
"""
import importlib.util
import os
import sys
import unittest
from unittest import mock

from eth_abi import encode
from eth_utils import keccak, to_checksum_address

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


mt = _load_module("aro_test_tempo_methodology_test_cross_exposure", "chains/tempo/scripts/methodology_test.py")

KNOWN = sorted(mt._KNOWN_MORPHO_BLUE_OWNERS_2026_09_20)
NOTE_KEY = "crossChainSignerOverlap"


def addr(n):
    return to_checksum_address("0x" + format(n, "040x"))


def selector(sig):
    return "0x" + keccak(text=sig)[:4].hex()


def _target(label, signers, **extra):
    """Minimal result dict, the shape cross_exposure() reads and writes."""
    return {"target": label, "rootControlSet": [{"signers": list(signers)}], "compositeScore": 55, **extra}


def _pre_fold_expected(results):
    """The within-Tempo formula exactly as it read before 2026-09-20, re-derived
    independently of the code under test."""
    sets = [{s.lower() for k in r["rootControlSet"] for s in k["signers"]} for r in results]
    out = []
    for i in range(len(results)):
        shared = [results[j]["target"] for j in range(len(results)) if j != i and sets[i] & sets[j]]
        out.append((max(0, 100 - 20 * len(shared)), shared))
    return out


class TestKnownCommitteeSnapshot(unittest.TestCase):
    def test_nine_lowercase_addresses(self):
        self.assertIsInstance(mt._KNOWN_MORPHO_BLUE_OWNERS_2026_09_20, frozenset)
        self.assertEqual(len(mt._KNOWN_MORPHO_BLUE_OWNERS_2026_09_20), 9)
        for a in mt._KNOWN_MORPHO_BLUE_OWNERS_2026_09_20:
            self.assertEqual(a, a.lower())
            self.assertRegex(a, r"^0x[0-9a-f]{40}$")


class TestCrossExposureFold(unittest.TestCase):
    def _run(self, core_signers, others=()):
        results = [
            _target("Tempo L1 validator registry (ValidatorConfigV2)", [addr(0x1), addr(0x2)]),
            *others,
            _target("Morpho Blue core", core_signers),
        ]
        mt.cross_exposure(results)
        return results

    def test_match_scores_80_with_real_finding_note(self):
        results = self._run(KNOWN)
        core = results[-1]
        self.assertEqual(core["crossExposureScore"], 80)
        self.assertEqual(list(core["notes"]), [NOTE_KEY])
        note = core["notes"][NOTE_KEY]
        self.assertIn("independently re-confirmed", note)
        self.assertIn("80", note)
        self.assertIn("Ethereum L1", note)
        self.assertNotIn(chr(0x2014), note)  # house style: no em-dashes
        self.assertNotIn("kept out", note)

    def test_match_is_case_insensitive_like_classify_checksummed_output(self):
        # classify() returns checksummed signers; the snapshot is lowercase.
        results = self._run([to_checksum_address(a) for a in KNOWN])
        self.assertEqual(results[-1]["crossExposureScore"], 80)
        results = self._run([a.upper().replace("0X", "0x") for a in KNOWN])
        self.assertEqual(results[-1]["crossExposureScore"], 80)

    def test_mismatch_stays_100_and_no_note(self):
        cases = {
            "one owner rotated out": KNOWN[:-1] + [addr(0x99)],
            "subset (8 of 9)": KNOWN[:-1],
            "superset (9 + 1)": KNOWN + [addr(0x99)],
            "unrelated committee": [addr(0x50 + i) for i in range(9)],
            "unresolved authority (empty signer set)": [],
        }
        for name, signers in cases.items():
            with self.subTest(name):
                core = self._run(signers)[-1]
                self.assertEqual(core["crossExposureScore"], 100)
                self.assertNotIn("notes", core)

    def test_within_tempo_lower_value_is_never_raised(self):
        # Three other Tempo targets each share one of the 9 signers with the core
        # (and not with each other): within-Tempo score for the core = 100 - 60 = 40.
        others = [_target(f"other {i}", [KNOWN[i], addr(0x300 + i)]) for i in range(3)]
        results = self._run(KNOWN, others)
        core = results[-1]
        self.assertEqual(core["crossExposureScore"], 40)  # min(40, 80), not 80
        self.assertEqual(sorted(core["sharedRootSignersWith"]), ["other 0", "other 1", "other 2"])
        # The cross-chain finding is still real and still reported.
        self.assertIn(NOTE_KEY, core["notes"])

    def test_one_within_tempo_share_is_exactly_the_cap(self):
        other = _target("other", [KNOWN[0], addr(0x301)])
        core = self._run(KNOWN, [other])[-1]
        self.assertEqual(core["crossExposureScore"], 80)  # min(80, 80)

    def test_other_targets_are_untouched(self):
        others = [
            _target("shares with core", [KNOWN[0], addr(0x301)]),
            _target("shares with nobody", [addr(0x302)]),
            _target("shares with the baseline", [addr(0x2), addr(0x303)]),
        ]
        results = self._run(KNOWN, others)
        expected = _pre_fold_expected(results)
        for i, r in enumerate(results):
            if r["target"] == "Morpho Blue core":
                continue
            with self.subTest(r["target"]):
                self.assertEqual((r["crossExposureScore"], r["sharedRootSignersWith"]), expected[i])
                self.assertNotIn("notes", r)
        by_label = {r["target"]: r for r in results}
        self.assertEqual(by_label["shares with nobody"]["crossExposureScore"], 100)
        self.assertEqual(by_label["shares with core"]["crossExposureScore"], 80)

    def test_result_shape_gains_only_notes_and_no_internal_keys(self):
        before = set(_target("x", KNOWN))
        results = self._run(KNOWN)
        core = results[-1]
        self.assertEqual(set(core) - before, {"crossExposureScore", "sharedRootSignersWith", "notes"})
        for r in results:
            self.assertEqual([k for k in r if k.startswith("_")], [])

    def test_idempotent_on_a_second_call(self):
        results = self._run(KNOWN)
        snapshot = [(r["crossExposureScore"], r.get("notes")) for r in results]
        mt.cross_exposure(results)
        self.assertEqual([(r["crossExposureScore"], r.get("notes")) for r in results], snapshot)


class FakeRpc:
    """Same dict-dispatch style as test_tempo_top_level_scorers.py's FakeRpc,
    kept as a small self-contained copy (each test file owns its fixtures)."""

    def __init__(self):
        self.calls = {}
        self.code = {}

    def set_call(self, to, sig, ret_hex):
        self.calls[(to.lower(), selector(sig))] = ret_hex

    def __call__(self, url, method, params):
        if method == "eth_getCode":
            return self.code.get(params[0].lower(), "0x")
        if method == "eth_getStorageAt":
            return "0x" + "00" * 32
        if method == "eth_call":
            return self.calls.get((params[0]["to"].lower(), params[0]["data"][:10]))
        raise AssertionError(f"unexpected RPC method in test: {method}")


class TestFoldThroughRealScoreMorphoBlue(unittest.TestCase):
    CORE = addr(0xB10E)
    SAFE = addr(0xA0)

    def _score(self, owners, k=5):
        fake = FakeRpc()
        fake.code[self.SAFE.lower()] = "0x600160005260206000f3"
        for o in owners:
            fake.code[o.lower()] = "0x"  # plain EOA signers
        fake.set_call(self.SAFE, "getThreshold()", "0x" + encode(["uint256"], [k]).hex())
        fake.set_call(self.SAFE, "getOwners()", "0x" + encode(["address[]"], [list(owners)]).hex())
        fake.set_call(self.SAFE, "getModulesPaginated(address,uint256)",
                      "0x" + encode(["address[]", "address"], [[], mt.SAFE_SENTINEL]).hex())
        fake.set_call(self.SAFE, "VERSION()", "0x" + encode(["string"], ["1.4.1"]).hex())
        fake.set_call(self.SAFE, "nonce()", "0x" + encode(["uint256"], [1]).hex())
        fake.set_call(self.CORE, "owner()", "0x" + encode(["address"], [self.SAFE]).hex())
        fake.set_call(self.CORE, "feeRecipient()", "0x" + encode(["address"], [addr(0)]).hex())
        patcher = mock.patch.object(mt, "rpc", fake)
        patcher.start()
        self.addCleanup(patcher.stop)
        results = [_target("baseline", [addr(0x1)]), mt.score_morpho_blue("Morpho Blue core", self.CORE)]
        mt.cross_exposure(results)
        return results[1]

    def test_live_shape_5of9_known_committee_folds_to_80_composite_unchanged(self):
        core = self._score([to_checksum_address(a) for a in KNOWN])
        self.assertEqual(core["crossExposureScore"], 80)
        self.assertEqual(
            (core["adminKeyScore"], core["multisigScore"], core["timelockScore"],
             core["oracleAuthorityScore"], core["compositeScore"]),
            (65, 96, 0, 100, 55),
        )
        self.assertIn(NOTE_KEY, core["notes"])

    def test_same_shape_with_a_different_committee_stays_100(self):
        core = self._score([addr(0x2000 + i) for i in range(9)])
        self.assertEqual(core["crossExposureScore"], 100)
        self.assertEqual(core["compositeScore"], 55)
        self.assertNotIn("notes", core)


class TestScoreAllKeepsTheNote(unittest.TestCase):
    """scorers.py::score_all() used to assign `notes = {chainCappedComposite}`
    after cross_exposure(), which would have wiped the finding."""

    @classmethod
    def setUpClass(cls):
        # scorers.py does a bare `import methodology_test`; other ecosystems (Hyperliquid)
        # ship a module with that same name, so pin Tempo's under the bare name while loading
        # and restore whatever a previous test left there.
        _missing = object()
        prev = sys.modules.get("methodology_test", _missing)
        sys.modules["methodology_test"] = mt
        try:
            cls.scorers = _load_module("aro_test_tempo_scorers_cross_exposure", "chains/tempo/scorers.py")
        finally:
            if prev is _missing:
                sys.modules.pop("methodology_test", None)
            else:
                sys.modules["methodology_test"] = prev

    def _fake_result(self, label, address, signers, composite):
        return {
            "target": label, "address": address, "rootControlSet": [{"signers": list(signers)}],
            "adminKeyScore": 65, "multisigScore": 96, "timelockScore": 0, "oracleAuthorityScore": 100,
            "compositeScore": composite,
        }

    def test_score_all_output_keeps_finding_next_to_chain_cap(self):
        s_mt = self.scorers.mt
        core_addr = addr(0xB10E)
        patches = [
            mock.patch.object(s_mt, "TOKENS", {"TOK": {"address": addr(0x11), "lz_oapp": None}}),
            mock.patch.object(s_mt, "VAULT_V2_TARGETS", {}),
            mock.patch.object(s_mt, "MORPHO_BLUE_TARGETS", {"Morpho Blue core": core_addr}),
            mock.patch.object(s_mt, "scan_role_logs", lambda addresses: (1, {to_checksum_address(a): [] for a in addresses})),
            mock.patch.object(s_mt, "score_chain_baseline",
                              lambda: self._fake_result("Tempo L1 validator registry (ValidatorConfigV2)", addr(0x2), [addr(0x1)], 31)),
            mock.patch.object(s_mt, "score_token",
                              lambda label, token, lz, events: self._fake_result(label, token, [addr(0x77)], 40)),
            mock.patch.object(s_mt, "score_morpho_blue",
                              lambda label, core: self._fake_result(label, core, KNOWN, 55)),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

        out = self.scorers.score_all()
        by_label = {r["label"]: r for r in out}
        self.assertEqual(len(out), 3)

        core = by_label["Morpho Blue core"]
        self.assertEqual(core["target"], core_addr)  # legacy target/address swap still applied
        self.assertEqual(core["crossExposureScore"], 80)
        self.assertEqual(core["notes"]["chainCappedComposite"], 31)
        self.assertIn(NOTE_KEY, core["notes"])

        token = by_label["TOK"]
        self.assertEqual(token["crossExposureScore"], 100)
        self.assertEqual(token["notes"], {"chainCappedComposite": 31})  # min(40, baseline 31), and nothing else
        for r in out:
            self.assertEqual([k for k in r if k.startswith("_")], [])


if __name__ == "__main__":
    unittest.main()
