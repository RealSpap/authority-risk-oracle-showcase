"""
Unit tests for chains/hyperliquid/scripts/methodology_test.py's evm()/exception taxonomy fix,
ADDED 2026-09-22 -- closes the tracked "web3_utils helpers rendent None pour un revert comme pour
[backlog note]" risk on the ONE ecosystem that doesn't import web3_utils at all (Hyperliquid
has its own zero-dependency curl-based RPC layer, mirroring chains/tempo/scripts/methodology_test.py).

Until this fix, evm() raised HyperEvmRpcError for BOTH a genuine EVM revert (the common, expected
case -- e.g. calling getOwners() on a contract that isn't a Safe) AND a real RPC-level problem (rate
limit, internal node error), and every one of the 4 call sites that catch it degraded both the same
way (conservative unresolved, (20, 0, 0)) -- a persistent RPC failure silently retiring a target's
score to its floor, indistinguishable from a confirmed "not this interface" in the output. evm() now
inspects the JSON-RPC error code (3 = execution reverted, the same convention
chains/tempo/scripts/methodology_test.py's own rpc() already keys on) and raises HyperEvmReadError
for a confirmed revert, HyperEvmRpcError for everything else -- so a genuine RPC failure now
propagates to score_all()'s per-scorer SKIPPED isolation instead of degrading a target.

No network access: _post() is monkeypatched throughout.
"""
import importlib.util
import os
import re
import unittest
from unittest.mock import patch

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
SCRIPT = os.path.join(REPO_ROOT, "chains", "hyperliquid", "scripts", "methodology_test.py")


def _load_methodology_test():
    spec = importlib.util.spec_from_file_location("hl_methodology_test", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


hl = _load_methodology_test()

SOME_ADDR = "0x" + "1" * 40


class TestEvmClassifiesTheErrorCode(unittest.TestCase):
    """Direct tests of evm()'s own fix -- the single chokepoint every RPC call in this file goes
    through, so getting this right here is what makes the 4 downstream except-narrowing edits safe."""

    def test_a_result_key_present_is_returned_unchanged(self):
        with patch.object(hl, "_post", return_value={"jsonrpc": "2.0", "id": 1, "result": "0xdeadbeef"}):
            self.assertEqual(hl.evm("eth_call", [{}]), "0xdeadbeef")

    def test_error_code_3_raises_hyper_evm_read_error(self):
        resp = {"jsonrpc": "2.0", "id": 1, "error": {"code": 3, "message": "execution reverted"}}
        with patch.object(hl, "_post", return_value=resp):
            with self.assertRaises(hl.HyperEvmReadError) as ctx:
                hl.evm("eth_call", [{"to": SOME_ADDR}])
            self.assertIn("execution reverted", str(ctx.exception))

    def test_a_rate_limit_style_error_code_raises_hyper_evm_rpc_error_not_read_error(self):
        # -32005 is the conventional "rate limit exceeded" JSON-RPC error code -- NOT a revert.
        resp = {"jsonrpc": "2.0", "id": 1, "error": {"code": -32005, "message": "call rate limit exhausted"}}
        with patch.object(hl, "_post", return_value=resp):
            with self.assertRaises(hl.HyperEvmRpcError):
                hl.evm("eth_call", [{"to": SOME_ADDR}])
            # and specifically NOT the revert-shaped exception:
            with patch.object(hl, "_post", return_value=resp):
                try:
                    hl.evm("eth_call", [{"to": SOME_ADDR}])
                    self.fail("expected an exception")
                except hl.HyperEvmReadError:
                    self.fail("a rate-limit error must not be classified as a revert")
                except hl.HyperEvmRpcError:
                    pass

    def test_an_internal_error_code_also_raises_hyper_evm_rpc_error(self):
        resp = {"jsonrpc": "2.0", "id": 1, "error": {"code": -32603, "message": "internal error"}}
        with patch.object(hl, "_post", return_value=resp):
            with self.assertRaises(hl.HyperEvmRpcError):
                hl.evm("eth_call", [{"to": SOME_ADDR}])

    def test_no_result_and_no_error_at_all_raises_hyper_evm_rpc_error(self):
        # A malformed/empty response -- no "error" key to even inspect the code of.
        with patch.object(hl, "_post", return_value={"jsonrpc": "2.0", "id": 1}):
            with self.assertRaises(hl.HyperEvmRpcError):
                hl.evm("eth_call", [{"to": SOME_ADDR}])


class TestClassifyAuthorityHolderDegradesOnlyOnARevert(unittest.TestCase):
    """End-to-end through one real call site (_classify_authority_holder, the first of the 4 this
    fix touches): a confirmed revert while resolving the Safe still degrades gracefully to (20, 0,
    0) exactly as before; a genuine RPC failure now propagates instead of being silently absorbed."""

    def setUp(self):
        # eth_getCode must return non-"0x" so _classify_authority_holder proceeds past the
        # bare-EOA short-circuit and reaches the try/except this fix touches.
        patcher = patch.object(hl, "evm", side_effect=self._fake_evm)
        self.addCleanup(patcher.stop)
        self.fake_evm = patcher.start()
        self.read_safe_outcome = None  # set per-test

    def _fake_evm(self, method, params):
        if method == "eth_getCode":
            return "0x606060"
        raise AssertionError(f"unexpected evm() call in this test: {method}({params})")

    def test_a_confirmed_revert_while_resolving_the_safe_still_degrades_to_conservative_unresolved(self):
        with patch.object(hl, "read_safe_hyperevm", side_effect=hl.HyperEvmReadError("not a real Safe")):
            scores, info = hl._classify_authority_holder(SOME_ADDR)
        self.assertEqual(scores, (20, 0, 0))
        self.assertIn("unresolved", info["kind"])

    def test_a_genuine_rpc_failure_while_resolving_the_safe_now_propagates_instead_of_degrading(self):
        with patch.object(hl, "read_safe_hyperevm", side_effect=hl.HyperEvmRpcError("rate limited")):
            with self.assertRaises(hl.HyperEvmRpcError):
                hl._classify_authority_holder(SOME_ADDR)


class TestAllFourSitesOnlyCatchHyperEvmReadError(unittest.TestCase):
    """Static, mechanical check that all 4 sites this fix touches were edited identically -- a
    single missed site would silently keep degrading on a genuine RPC failure right there, easy to
    miss by eye across 4 near-duplicate edits in one file."""

    def test_no_site_still_catches_both_exception_types_together(self):
        with open(SCRIPT) as f:
            source = f.read()
        self.assertNotIn("except (HyperEvmReadError, HyperEvmRpcError)", source)

    def test_exactly_four_sites_now_catch_hyper_evm_read_error_alone(self):
        with open(SCRIPT) as f:
            source = f.read()
        sites = re.findall(r"except HyperEvmReadError as e:", source)
        self.assertEqual(len(sites), 4)


if __name__ == "__main__":
    unittest.main()
