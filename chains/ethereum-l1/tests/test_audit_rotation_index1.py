"""
Unit tests for chains/ethereum-l1/scripts/audit_rotation_index1.py's own retry/exception logic and
its main()/divergences structure. Added 2026-09-22 (backlog item "quatre reimplementations
separees" -- itemId=251466178): this file used to have NO test infrastructure at all, because its
entire audit body ran as top-level code that executed real RPC calls the instant the module was
imported. Fixed by wrapping the body in main() (same shape as its 3 sibling files already have)
so it can be imported and exercised with `call()` mocked, without ever hitting the network.

No network, no `cast`/Foundry binary needed -- subprocess.run itself is mocked.

Run:  python3 -m unittest discover -s chains/ethereum-l1/tests -v
"""
import importlib.util
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))


def _load(name, rel):
    path = os.path.join(REPO_ROOT, rel)
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


a = _load("aro_test_audit_rotation_index1", "chains/ethereum-l1/scripts/audit_rotation_index1.py")


def _proc(returncode=0, stdout="", stderr=""):
    p = MagicMock()
    p.returncode = returncode
    p.stdout = stdout
    p.stderr = stderr
    return p


class TestIsTransientFailure(unittest.TestCase):
    def test_network_and_transport_errors_are_transient(self):
        for msg in ["Error sending request for url", "connection reset by peer", "request timed out",
                    "dns error: failed to lookup", "502 Bad Gateway", "429 Too Many Requests",
                    "server disconnected without sending a response"]:
            self.assertTrue(a._is_transient_failure(msg), msg)

    def test_a_revert_looking_message_is_not_transient(self):
        # cast's own wording for a deterministic EVM revert -- must NOT be retried, or a retry
        # could mask a genuine on-chain divergence as "just a flaky network".
        self.assertFalse(a._is_transient_failure(
            "server returned an error response: error code -32000: execution reverted: OnlyMinter"))
        self.assertFalse(a._is_transient_failure("Error: invalid data for function"))

    def test_a_revert_whose_abi_encoded_data_happens_to_contain_a_transient_marker_digit_string_is_still_not_transient(self):
        # REVIEW FINDING (review run, reservation "OVERSTATED RETRY CLASSIFICATION"): cast
        # prints a revert's ABI-encoded return data inline, and that hex blob can by pure chance
        # contain "502"/"503"/"429" -- must not let that override the revert classification.
        self.assertFalse(a._is_transient_failure(
            'execution reverted: Dai/insufficient-balance, data: "0x08c379a05020000429503aa"'))

    def test_the_bare_error_code_3_marker_is_anchored_not_a_loose_substring(self):
        # REVIEW FINDING (review run, reservation "_REVERT_MARKERS IS LOOSER THAN THE COMMIT
        # MESSAGE DESCRIBES"): a genuine JSON-RPC internal-error code beginning with "3" (e.g.
        # 32603, "method not found" family) must not be misread as the revert code "3" just because
        # it starts with that digit -- only checked in isolation here, since real-world negative
        # codes ("error code -32603") are already covered by the pre-existing revert test above.
        self.assertTrue(a._is_transient_failure("error sending request: error code 32603"))
        self.assertFalse(a._is_transient_failure("server returned: error code 3"))
        self.assertFalse(a._is_transient_failure("server returned: error code: 3"))


class TestCallRetry(unittest.TestCase):
    def test_success_on_first_try_makes_exactly_one_subprocess_call(self):
        with patch.object(a.subprocess, "run", return_value=_proc(0, "0xabc\n")) as mock_run, \
             patch.object(a.time, "sleep"):
            out = a.call("http://rpc", "0xTo", "owner()(address)")
        self.assertEqual(out, "0xabc")
        self.assertEqual(mock_run.call_count, 1)

    def test_a_transient_failure_then_success_retries_and_returns_the_value(self):
        # THE bug this fix closes: before, a single transient failure raised RuntimeError
        # uncaught, crashing the whole audit with a traceback instead of a clean report.
        calls = [_proc(1, "", "Error sending request for url (https://rpc)"), _proc(0, "0xabc\n")]
        with patch.object(a.subprocess, "run", side_effect=calls) as mock_run, \
             patch.object(a.time, "sleep") as mock_sleep:
            out = a.call("http://rpc", "0xTo", "owner()(address)")
        self.assertEqual(out, "0xabc")
        self.assertEqual(mock_run.call_count, 2)
        mock_sleep.assert_called_once()

    def test_transient_failures_exhausting_every_retry_raise_with_the_last_message(self):
        with patch.object(a.subprocess, "run", return_value=_proc(1, "", "connection timed out")), \
             patch.object(a.time, "sleep"):
            with self.assertRaises(RuntimeError) as cm:
                a.call("http://rpc", "0xTo", "owner()(address)", tries=3)
        self.assertIn("apres 3 tentatives", str(cm.exception))
        self.assertIn("connection timed out", str(cm.exception))

    def test_a_deterministic_revert_raises_immediately_without_retrying(self):
        with patch.object(a.subprocess, "run", return_value=_proc(
                1, "", "execution reverted: OnlyMinter")) as mock_run, \
             patch.object(a.time, "sleep") as mock_sleep:
            with self.assertRaises(RuntimeError) as cm:
                a.call("http://rpc", "0xTo", "onlyMinter()(bool)")
        self.assertEqual(mock_run.call_count, 1)  # not retried
        mock_sleep.assert_not_called()
        self.assertIn("OnlyMinter", str(cm.exception))


class TestAgree(unittest.TestCase):
    def setUp(self):
        a.divergences.clear()

    def test_matching_values_produce_no_divergence(self):
        v = a.agree("label", ["0xabc", "0xabc"])
        self.assertEqual(v, "0xabc")
        self.assertEqual(a.divergences, [])

    def test_mismatched_values_are_recorded_and_the_first_is_returned(self):
        v = a.agree("owner()", ["0xabc", "0xdef"])
        self.assertEqual(v, "0xabc")
        self.assertEqual(len(a.divergences), 1)
        self.assertIn("owner()", a.divergences[0])


class TestComposite(unittest.TestCase):
    def test_matches_methodologys_published_formula(self):
        # floor(0.4*78 + 0.3*100 + 0.3*55 + 0.5) -- the exact real-world row this file audits
        self.assertEqual(a.composite(78, 100, 55), 78)

    def test_uses_the_exact_integer_form_not_the_float_form_that_reads_one_low(self):
        # REVIEW FINDING (review run, reservation "HOLLOW TEST"): (78, 100, 55) is one of the
        # 1,030,299 triples where the defective float form int(0.4*a+0.3*m+0.3*t+0.5) and the exact
        # form (4a+3m+3t+5)//10 agree -- it would pass unchanged on the buggy implementation. This
        # is one of the 2054 triples where they DON'T: the float form gives 7, the exact form gives
        # 8 (independently brute-forced over all 1,030,301 (a,m,t) triples before this fix).
        self.assertEqual(a.composite(0, 1, 24), 8)


class TestMainStructure(unittest.TestCase):
    """main() itself is mocked at the call() boundary -- these tests are about the CONTROL FLOW
    (divergences reset between runs, return code reflects divergences), not about re-deriving the
    real Aave authority chain, which is already exercised by running the script live."""

    def setUp(self):
        # The oracle dimension is re-derived live by price_authority since 2026-10-04 (its own offline tests live in
        # scripts/lib/tests/test_price_authority.py); here it answers the fixture's published 100, with no network.
        p = patch.object(a, "oracle_authority_live", return_value=[100, 100])
        p.start()
        self.addCleanup(p.stop)

    def _mock_call_returning(self, table):
        def fake_call(rpc, addr, sig, *args, tries=4):
            key = (addr, sig, args)
            if key not in table:
                raise AssertionError(f"unexpected call: {key}")
            return table[key]
        return fake_call

    def _clean_table(self):
        target = "0xTarget"
        owner = "0xOwner"
        acl = "0xAcl"
        root = "0xRoot"
        guardian = "0xGuardian"
        return {
            (a.ORACLE, "trackedTargets(uint256)(address)", (1,)): target,
            (a.ORACLE, "getScore(address)((uint8,uint8,uint8,uint8,uint8,uint8,uint64,bytes32))", (target,)):
                "(78, 100, 55, 100, 80, 78, 1758000000, 0x00)",
            (target, "getMarketId()(string)", ()): "Aave Ethereum Market",
            (target, "owner()(address)", ()): owner,
            (target, "getACLManager()(address)", ()): acl,
            (owner, "owner()(address)", ()): root,
            (root, "getExecutorSettingsByAccessControl(uint8)((address,uint40))", (1,)): f"({owner}, 86400)",
            (root, "guardian()(address)", ()): guardian,
            (guardian, "getThreshold()(uint256)", ()): "5",
            (guardian, "getOwners()(address[])", ()): "[0x1,0x2,0x3,0x4,0x5,0x6,0x7,0x8,0x9]",  # 5-of-9
            (a.PROTOCOL_GUARDIAN, "getThreshold()(uint256)", ()): "4",
            (a.PROTOCOL_GUARDIAN, "getOwners()(address[])", ()): "[0x1,0x2,0x3,0x4,0x5,0x6,0x7]",  # 4-of-7
            (acl, "isEmergencyAdmin(address)(bool)", (owner,)): "false",
            (acl, "isEmergencyAdmin(address)(bool)", (a.PROTOCOL_GUARDIAN,)): "true",
        }

    def _env_without_fault_inject(self):
        # REVIEW FINDING (review run, reservation "NEW ETHEREUM-L1 TESTS DO NOT NEUTRALIZE THE
        # FAULT-INJECT ENV VAR"): main() reads os.environ.get("AUDIT_FAULT_INJECT") at call time --
        # a shell where the negative control was exported (a very plausible sequence, since that IS
        # the documented way to run this script's own self-check) would make these tests fail
        # spuriously. patch.dict with the key explicitly removed, regardless of the real environment.
        env = dict(os.environ)
        env.pop("AUDIT_FAULT_INJECT", None)
        return patch.dict(a.os.environ, env, clear=True)

    def test_a_fully_matching_run_returns_0_with_no_divergences(self):
        table = self._clean_table()
        with patch.object(a, "call", side_effect=self._mock_call_returning(table)), \
             self._env_without_fault_inject():
            self.assertEqual(a.main(), 0)
        self.assertEqual(a.divergences, [])

    def test_divergences_do_not_leak_between_two_calls_to_main(self):
        # THE second half of this fix: divergences.clear() at the top of main(). Before it existed,
        # a dirty run followed by a clean run would still report the FIRST run's stale divergences.
        broken_table = self._clean_table()
        target = "0xTarget"
        broken_table[(a.ORACLE, "getScore(address)((uint8,uint8,uint8,uint8,uint8,uint8,uint64,bytes32))", (target,))] = \
            "(79, 100, 55, 100, 80, 78, 1758000000, 0x00)"  # admin mismatch: derive=78 != on-chain=79

        with patch.object(a, "call", side_effect=self._mock_call_returning(broken_table)), \
             self._env_without_fault_inject():
            self.assertEqual(a.main(), 1)
        self.assertTrue(a.divergences)  # the dirty run left something behind

        clean_table = self._clean_table()
        with patch.object(a, "call", side_effect=self._mock_call_returning(clean_table)), \
             self._env_without_fault_inject():
            self.assertEqual(a.main(), 0)  # must NOT inherit the previous run's divergence
        self.assertEqual(a.divergences, [])


if __name__ == "__main__":
    unittest.main()
