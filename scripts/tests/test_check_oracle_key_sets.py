"""
Unit tests for scripts/check_oracle_key_sets.py -- no live RPC, no subprocess. Added 2026-09-22
(backlog item, "[backlog note]"): the existing count-only audit
(data/audit_oracle_key_collisions_2026-09-20.md, scripts/check_oracle_key_collisions.py) can miss a
SWAP -- an orphan on-chain key that happens to cancel out against a missing scored key, leaving the
totals equal while the sets differ. These tests cover the new SET-diff logic in audit_one()/
scored_keys(), and main()'s argument handling, all with the network and subprocess boundaries mocked.
"""
import io
import os
import sys
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import check_oracle_key_sets as k  # noqa: E402


class TestAuditOneSetDiff(unittest.TestCase):
    def test_matching_sets_report_no_orphan_or_gap(self):
        with patch.object(k, "scored_keys", return_value=({"0xaaa", "0xbbb"}, None)):
            r = k.audit_one("ethereum-l1", "Ethereum L1 (Sepolia)", lambda: {"0xaaa", "0xbbb"}, timeout=10)
        self.assertIsNone(r["error"])
        self.assertEqual(r["orphans"], set())
        self.assertEqual(r["gaps"], set())
        self.assertEqual(r["onchain_count"], 2)
        self.assertEqual(r["scored_count"], 2)

    def test_an_onchain_key_with_no_scored_counterpart_is_an_orphan(self):
        # the general case of the already-documented Ethereum L1 retired-minter row
        with patch.object(k, "scored_keys", return_value=({"0xaaa"}, None)):
            r = k.audit_one("ethereum-l1", "Ethereum L1 (Sepolia)", lambda: {"0xaaa", "0xretired"}, timeout=10)
        self.assertEqual(r["orphans"], {"0xretired"})
        self.assertEqual(r["gaps"], set())

    def test_a_scored_key_with_no_onchain_counterpart_is_a_gap(self):
        with patch.object(k, "scored_keys", return_value=({"0xaaa", "0xnew"}, None)):
            r = k.audit_one("ethereum-l1", "Ethereum L1 (Sepolia)", lambda: {"0xaaa"}, timeout=10)
        self.assertEqual(r["orphans"], set())
        self.assertEqual(r["gaps"], {"0xnew"})

    def test_same_count_but_swapped_keys_is_caught_as_both_an_orphan_and_a_gap(self):
        # THE motivating case: a count-only audit (equal totals) would report this ecosystem clean.
        with patch.object(k, "scored_keys", return_value=({"0xaaa", "0xnew"}, None)):
            r = k.audit_one("ethereum-l1", "Ethereum L1 (Sepolia)", lambda: {"0xaaa", "0xold"}, timeout=10)
        self.assertEqual(r["onchain_count"], r["scored_count"])  # counts agree...
        self.assertEqual(r["orphans"], {"0xold"})  # ...but the sets don't
        self.assertEqual(r["gaps"], {"0xnew"})

    def test_onchain_read_failure_is_reported_failed_not_treated_as_an_empty_clean_set(self):
        def boom():
            raise RuntimeError("simulated persistent RPC failure")
        with patch.object(k, "scored_keys") as mock_scored:
            r = k.audit_one("ethereum-l1", "Ethereum L1 (Sepolia)", boom, timeout=10)
        mock_scored.assert_not_called()  # the scored side must not even be fetched once on-chain already failed
        self.assertIsNotNone(r["error"])
        self.assertIn("RuntimeError", r["error"])
        self.assertNotIn("orphans", r)

    def test_scored_read_failure_is_reported_failed_not_treated_as_an_empty_clean_set(self):
        with patch.object(k, "scored_keys", return_value=(None, "timed out after 10s")):
            r = k.audit_one("ethereum-l1", "Ethereum L1 (Sepolia)", lambda: {"0xaaa"}, timeout=10)
        self.assertIsNotNone(r["error"])
        self.assertIn("timed out", r["error"])

    def test_scored_keys_raising_unexpectedly_is_reported_failed_not_crashed(self):
        # REVIEW FINDING (reviewer, review run, reservation): scored_keys()'s (None, err) return
        # contract is only ONE of its failure modes -- ckc.fetch_entries or ckc._hyperliquid_resolver
        # can also raise directly (subprocess spawn OSError, ImportError loading push_scores.py live).
        # Before this fix, that propagated straight through audit_one() into ThreadPoolExecutor.map(),
        # which has no per-item try/except of its own (see main()) -- crashing the WHOLE audit and
        # losing every other oracle's report, not just failing this one.
        with patch.object(k, "scored_keys", side_effect=OSError("simulated subprocess spawn failure")):
            r = k.audit_one("ethereum-l1", "Ethereum L1 (Sepolia)", lambda: {"0xaaa"}, timeout=10)
        self.assertIsNotNone(r["error"])
        self.assertIn("OSError", r["error"])
        self.assertNotIn("orphans", r)


class TestScoredKeys(unittest.TestCase):
    def test_zero_entries_is_an_error_not_an_empty_clean_set(self):
        with patch.object(k.ckc, "fetch_entries", return_value=([], None)):
            keys, err = k.scored_keys("ethereum-l1", timeout=10)
        self.assertIsNone(keys)
        self.assertIn("zero entries", err)

    def test_fetch_error_propagates(self):
        with patch.object(k.ckc, "fetch_entries", return_value=([], "timed out after 10s")):
            keys, err = k.scored_keys("ethereum-l1", timeout=10)
        self.assertIsNone(keys)
        self.assertEqual(err, "timed out after 10s")

    def test_non_hyperliquid_uses_target_not_oracle_key(self):
        entries = [{"target": "0xAAA", "oracleKey": "0xdecoyshouldnotbeused"}]
        with patch.object(k.ckc, "fetch_entries", return_value=(entries, None)):
            keys, err = k.scored_keys("ethereum-l1", timeout=10)
        self.assertIsNone(err)
        self.assertEqual(keys, {"0xaaa"})  # normalized target, oracleKey ignored

    def test_solana_keys_are_compared_exact_not_lowercased(self):
        entries = [{"target": "AbCdEf"}]
        with patch.object(k.ckc, "fetch_entries", return_value=(entries, None)):
            keys, err = k.scored_keys("solana", timeout=10)
        self.assertIsNone(err)
        self.assertEqual(keys, {"AbCdEf"})  # exact, case preserved -- base58 is case-sensitive

    def test_hyperliquid_honours_the_derived_oracle_key(self):
        entries = [{"target": "0xhip3dex", "oracleKey": "0xderivedkey"}]

        def fake_resolver():
            return lambda es: es  # a no-op resolution: the entries already carry their final oracleKey

        with patch.object(k.ckc, "fetch_entries", return_value=(entries, None)), \
             patch.object(k.ckc, "_hyperliquid_resolver", side_effect=fake_resolver):
            keys, err = k.scored_keys("hyperliquid", timeout=10)
        self.assertIsNone(err)
        self.assertEqual(keys, {"0xderivedkey"})  # oracleKey honoured, not target

    def test_hyperliquid_resolution_refusal_is_reported_as_an_error(self):
        entries = [{"target": "0xa"}, {"target": "0xb"}]

        def refusing_resolver():
            def resolve(es):
                raise SystemExit("REFUSING: unresolved collision")
            return resolve

        with patch.object(k.ckc, "fetch_entries", return_value=(entries, None)), \
             patch.object(k.ckc, "_hyperliquid_resolver", side_effect=refusing_resolver):
            keys, err = k.scored_keys("hyperliquid", timeout=10)
        self.assertIsNone(keys)
        self.assertIn("REFUSING", err)

    def test_exactness_comes_from_ckcs_own_table_not_a_hardcoded_solana_check(self):
        # REVIEW FINDING (reservation): the original code hardcoded `exact = name == "solana"` instead
        # of reusing ckc.EXACT_KEY_ECOSYSTEMS, already imported in this file -- a second source of
        # truth for the same convention. Proven here by patching that TABLE (not the ecosystem name)
        # and confirming an entirely different, fake ecosystem name is compared exact as a result --
        # which only a real table lookup, not a literal "== \"solana\"", could produce.
        entries = [{"target": "AbCdEf"}]
        with patch.object(k.ckc, "fetch_entries", return_value=(entries, None)), \
             patch.object(k.ckc, "EXACT_KEY_ECOSYSTEMS", {"totally-fake-eco"}):
            keys, err = k.scored_keys("totally-fake-eco", timeout=10)
        self.assertIsNone(err)
        self.assertEqual(keys, {"AbCdEf"})  # exact/case-preserved, even though the name isn't "solana"


class TestMainArgumentHandling(unittest.TestCase):
    def _run(self, argv):
        with patch.object(sys, "argv", ["check_oracle_key_sets.py"] + argv), \
             patch.object(k, "audit_one", return_value={
                 "ecosystem": "x", "display": "x", "error": None,
                 "onchain_count": 1, "scored_count": 1, "orphans": set(), "gaps": set()}), \
             self.assertRaises(SystemExit) as cm:
            buf = io.StringIO()
            with redirect_stdout(buf):
                k.main()
        return cm.exception.code

    def test_unknown_ecosystem_is_refused(self):
        with self.assertRaises(SystemExit) as cm:
            with patch.object(sys, "argv", ["check_oracle_key_sets.py", "--ecosystem", "not-a-real-chain"]):
                k.main()
        self.assertIn("Unknown ecosystem", str(cm.exception))

    def test_skipping_every_ecosystem_refuses_to_report_a_clean_empty_result(self):
        all_names = ",".join(k.ALL_ECOSYSTEMS)
        with self.assertRaises(SystemExit) as cm:
            with patch.object(sys, "argv", ["check_oracle_key_sets.py", "--skip", all_names]):
                k.main()
        self.assertIn("no ecosystem selected", str(cm.exception))

    def test_a_clean_result_across_every_default_ecosystem_exits_zero(self):
        self.assertEqual(self._run([]), 0)

    def test_an_ecosystem_filter_narrows_which_jobs_run(self):
        calls = []

        def fake_audit_one(eco, display, onchain_fn, timeout):
            calls.append(eco)
            return {"ecosystem": eco, "display": display, "error": None,
                    "onchain_count": 0, "scored_count": 0, "orphans": set(), "gaps": set()}

        with patch.object(sys, "argv", ["check_oracle_key_sets.py", "--ecosystem", "solana,base"]), \
             patch.object(k, "audit_one", side_effect=fake_audit_one), \
             self.assertRaises(SystemExit):
            buf = io.StringIO()
            with redirect_stdout(buf):
                k.main()
        self.assertEqual(sorted(calls), ["base", "solana"])

    def test_an_orphan_or_gap_anywhere_exits_nonzero(self):
        with patch.object(sys, "argv", ["check_oracle_key_sets.py"]), \
             patch.object(k, "audit_one", return_value={
                 "ecosystem": "x", "display": "x", "error": None,
                 "onchain_count": 2, "scored_count": 1, "orphans": {"0xstale"}, "gaps": set()}), \
             self.assertRaises(SystemExit) as cm:
            buf = io.StringIO()
            with redirect_stdout(buf):
                k.main()
        self.assertEqual(cm.exception.code, 1)

    def test_a_failed_oracle_exits_nonzero_even_if_every_other_oracle_is_clean(self):
        with patch.object(sys, "argv", ["check_oracle_key_sets.py"]), \
             patch.object(k, "audit_one", return_value={
                 "ecosystem": "x", "display": "x", "error": "on-chain read failed: RuntimeError: boom"}), \
             self.assertRaises(SystemExit) as cm:
            buf = io.StringIO()
            with redirect_stdout(buf):
                k.main()
        self.assertEqual(cm.exception.code, 1)

    def _run_capture(self, argv):
        """Like _run() but also returns the printed text, for scope-disclosure assertions."""
        with patch.object(sys, "argv", ["check_oracle_key_sets.py"] + argv), \
             patch.object(k, "audit_one", return_value={
                 "ecosystem": "x", "display": "x", "error": None,
                 "onchain_count": 1, "scored_count": 1, "orphans": set(), "gaps": set()}), \
             self.assertRaises(SystemExit) as cm:
            buf = io.StringIO()
            with redirect_stdout(buf):
                k.main()
        return cm.exception.code, buf.getvalue()

    def test_a_full_run_discloses_9_of_9_audited_with_no_incomplete_marker(self):
        # REVIEW FINDING (BLOCKING, review run): a partial run used to print the unqualified
        # "RESULT: EVERY ON-CHAIN KEY SET MATCHES ITS SCORED SET" and exit 0 with no mention of scope
        # -- and the module's own docstring recommends exactly such a partial invocation
        # (--skip robinhood-chain). This locks in the disclosure for the FULL-scope case first.
        code, out = self._run_capture([])
        self.assertEqual(code, 0)
        self.assertIn(f"{len(k.ALL_ECOSYSTEMS)} of {len(k.ALL_ECOSYSTEMS)} oracle(s) audited", out)
        self.assertNotIn("INCOMPLETE", out)
        self.assertIn("RESULT: EVERY AUDITED ON-CHAIN KEY SET MATCHES ITS SCORED SET", out)

    def test_a_skip_run_discloses_incomplete_scope_and_names_whats_missing(self):
        # THE exact scenario the review demonstrated live: --skip robinhood-chain (the module
        # docstring's own example usage) must not read as full coverage.
        code, out = self._run_capture(["--skip", "robinhood-chain"])
        self.assertEqual(code, 0)  # what WAS audited is clean -- narrowing scope on purpose isn't a failure
        self.assertIn(f"{len(k.ALL_ECOSYSTEMS) - 1} of {len(k.ALL_ECOSYSTEMS)} oracle(s) audited", out)
        self.assertIn("INCOMPLETE", out)
        self.assertIn("robinhood-chain", out)
        self.assertNotIn("RESULT: EVERY AUDITED ON-CHAIN KEY SET MATCHES ITS SCORED SET", out)  # not the unqualified claim
        self.assertIn("RESULT: EVERY AUDITED KEY SET MATCHES (SCOPE INCOMPLETE, SEE ABOVE)", out)

    def test_an_ecosystem_filter_run_also_discloses_incomplete_scope(self):
        code, out = self._run_capture(["--ecosystem", "solana,base"])
        self.assertEqual(code, 0)
        self.assertIn(f"2 of {len(k.ALL_ECOSYSTEMS)} oracle(s) audited", out)
        self.assertIn("INCOMPLETE", out)


class TestMaxWorkersCapped(unittest.TestCase):
    def test_concurrency_is_capped_even_when_every_oracle_is_selected(self):
        # REVIEW FINDING (reservation): up to 9 parallel live score_all() subprocesses plus up to 8
        # parallel EVM on-chain reads against public RPCs exceeds this project's own documented limit
        # (ABI-returndata-guard project note: at most 2-3 live calculations in parallel).
        captured = {}
        real_executor = k.ThreadPoolExecutor

        class _SpyExecutor(real_executor):
            def __init__(self, *a, max_workers=None, **kw):
                captured["max_workers"] = max_workers
                super().__init__(*a, max_workers=max_workers, **kw)

        with patch.object(sys, "argv", ["check_oracle_key_sets.py"]), \
             patch.object(k, "audit_one", return_value={
                 "ecosystem": "x", "display": "x", "error": None,
                 "onchain_count": 0, "scored_count": 0, "orphans": set(), "gaps": set()}), \
             patch.object(k, "ThreadPoolExecutor", _SpyExecutor), \
             self.assertRaises(SystemExit):
            buf = io.StringIO()
            with redirect_stdout(buf):
                k.main()
        self.assertEqual(captured["max_workers"], 3)  # not len(jobs) == 9


class _Call:
    """A web3.py contract-function call stand-in: .call() returns a fixed value or raises."""
    def __init__(self, v):
        self.v = v

    def call(self):
        if isinstance(self.v, Exception):
            raise self.v
        return self.v


class _FakeWeb3:
    """Per-RPC behavior table, keyed by the RPC URL -- same convention as
    scripts/lib/tests/test_live_target_counts.py's own _FakeWeb3, extended with trackedTargets(i)."""
    behavior = {}

    @staticmethod
    def HTTPProvider(url, request_kwargs=None):
        return url

    @staticmethod
    def to_checksum_address(a):
        return a

    def __init__(self, url):
        b = self.behavior[url]

        class _Eth:
            def get_code(self_inner, addr):
                return b["code"]

            def contract(self_inner, address, abi):
                class _C:
                    class functions:
                        @staticmethod
                        def trackedTargetsCount():
                            return _Call(b["count"])

                        @staticmethod
                        def trackedTargets(i):
                            return _Call(b["targets"][i])
                return _C()

        self.eth = _Eth()


class TestReadOnchainKeysEvm(unittest.TestCase):
    # REVIEW FINDING (reservation): read_onchain_keys_evm/read_onchain_keys_solana had NO tests at
    # all -- only the single live ethereum-l1 run ever exercised them. live_target_counts.py's own
    # near-identical reads ARE tested (scripts/lib/tests/test_live_target_counts.py) -- this follows
    # that established convention on the file that most needed it.
    def test_every_target_is_read_and_normalized(self):
        _FakeWeb3.behavior = {"rpc-a": {"code": b"\x60", "count": 3,
                                         "targets": ["0xAAA", "0xbbb", "0xCcC"]}}
        keys = k.read_onchain_keys_evm("0x01", "rpc-a", web3_cls=_FakeWeb3)
        self.assertEqual(keys, {"0xaaa", "0xbbb", "0xccc"})  # normalized, deduplicated by construction

    def test_missing_bytecode_raises_not_returns_an_empty_set(self):
        _FakeWeb3.behavior = {"rpc-a": {"code": b"", "count": 5, "targets": []}}
        with self.assertRaises(RuntimeError) as cm:
            k.read_onchain_keys_evm("0x01", "rpc-a", web3_cls=_FakeWeb3)
        self.assertIn("no bytecode", str(cm.exception))

    def test_a_failure_reading_the_count_propagates_not_swallowed(self):
        _FakeWeb3.behavior = {"rpc-a": {"code": b"\x60", "count": ConnectionError("rpc down"), "targets": []}}
        with self.assertRaises(ConnectionError):
            k.read_onchain_keys_evm("0x01", "rpc-a", web3_cls=_FakeWeb3)

    def test_a_failure_partway_through_the_targets_propagates_not_a_partial_set(self):
        _FakeWeb3.behavior = {"rpc-a": {"code": b"\x60", "count": 3,
                                         "targets": ["0xaaa", ConnectionError("rpc down"), "0xccc"]}}
        with self.assertRaises(ConnectionError):
            k.read_onchain_keys_evm("0x01", "rpc-a", web3_cls=_FakeWeb3)


class TestReadOnchainKeysSolana(unittest.TestCase):
    def test_reads_the_registrys_tracked_targets(self):
        with patch.object(k.solana_oracle_reader, "read_oracle", return_value={"tracked": ["a", "b", "c"]}):
            self.assertEqual(k.read_onchain_keys_solana(), {"a", "b", "c"})

    def test_a_failing_read_propagates_not_swallowed(self):
        # Also proves the default-argument-capture trap this function used to have is gone: if
        # read_oracle were still a bound default, patch.object on the module would have no effect and
        # this test would hit the REAL network instead of raising the simulated failure below.
        with patch.object(k.solana_oracle_reader, "read_oracle", side_effect=ConnectionError("rpc down")):
            with self.assertRaises(ConnectionError):
                k.read_onchain_keys_solana()


if __name__ == "__main__":
    unittest.main()
