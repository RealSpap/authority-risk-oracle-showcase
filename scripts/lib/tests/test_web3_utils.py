"""
Unit tests for scripts/lib/web3_utils.py's pure/mockable logic -- no live RPC.
The live eth_call-dependent functions (is_eoa, call_raw, safe_owners_and_threshold,
etc.) are exercised by the project's existing --dry-run scripts against real
chains, not here; these tests cover the two things that can silently break
without ever touching a chain: the retry loop's own control flow, and the
Arbitrum bridge-alias arithmetic (data/correction_2026-09-16-uniswap-bridge-alias.md).
"""
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from eth_abi.exceptions import DecodingError  # noqa: E402
from web3.exceptions import BadFunctionCallOutput, ContractLogicError, Web3RPCError  # noqa: E402

from lib import web3_utils  # noqa: E402
from lib.web3_utils import (  # noqa: E402
    RpcUnavailable,
    _is_revert,
    _read,
    _retrying,
    arbitrum_l1_l2_alias,
    safe_score,
)


class TestArbitrumL1L2Alias(unittest.TestCase):
    def test_known_uniswap_timelock_alias(self):
        # Ground truth from data/correction_2026-09-16-uniswap-bridge-alias.md:
        # Uniswap's real Ethereum-mainnet Governance Timelock and its confirmed
        # Arbitrum L2 alias, independently re-verified live on-chain (both this
        # session and the correction that first found it).
        l1_timelock = "0x1a9C8182C09F50c8318d769245bEA52c32BE35BC"
        expected_alias = "0x2BAD8182C09F50c8318d769245beA52C32Be46CD"
        self.assertEqual(
            arbitrum_l1_l2_alias(l1_timelock).lower(),
            expected_alias.lower(),
        )

    def test_alias_wraps_mod_2_160(self):
        # An L1 address near the top of the 160-bit range must wrap around
        # rather than overflow into a >20-byte value.
        near_max = "0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF"
        alias = arbitrum_l1_l2_alias(near_max)
        self.assertEqual(len(alias), 42)  # "0x" + 40 hex chars, always a valid address

    def test_alias_is_deterministic(self):
        # Built via string repetition, not hand-typed -- a manually-counted
        # hex string is exactly the transcription trap this project's own
        # discipline exists to avoid (see this pass's Ethena investigation,
        # where a hand-copied event-topic hash silently dropped a character).
        addr = "0x" + "3" * 40
        self.assertEqual(arbitrum_l1_l2_alias(addr), arbitrum_l1_l2_alias(addr))

    def test_different_l1_addresses_give_different_aliases(self):
        a = arbitrum_l1_l2_alias("0x" + "3" * 40)
        b = arbitrum_l1_l2_alias("0x" + "4" * 40)
        self.assertNotEqual(a, b)


class TestRetrying(unittest.TestCase):
    def setUp(self):
        # Real _retrying() sleeps 0.4*attempt seconds between tries -- mock
        # it out so these tests run in milliseconds, not seconds.
        patcher = patch("lib.web3_utils.time.sleep", return_value=None)
        self.addCleanup(patcher.stop)
        patcher.start()

    def test_returns_immediately_on_first_success(self):
        calls = []

        def fn():
            calls.append(1)
            return "ok"

        self.assertEqual(_retrying(fn), "ok")
        self.assertEqual(len(calls), 1)

    def test_retries_until_success(self):
        results = iter([None, None, "ok"])

        def fn():
            return next(results)

        self.assertEqual(_retrying(fn, retries=4), "ok")

    def test_gives_up_after_retries_exhausted(self):
        calls = []

        def fn():
            calls.append(1)
            return None

        self.assertIsNone(_retrying(fn, retries=3))
        self.assertEqual(len(calls), 3)  # exactly `retries` attempts, not more

    def test_default_retries_is_four(self):
        calls = []

        def fn():
            calls.append(1)
            return None

        _retrying(fn)
        self.assertEqual(len(calls), 4)

    def test_retries_of_one_means_a_single_attempt(self):
        # This is the exact override chains/base-ecosystem/scorers.py uses at
        # call sites EXPECTED to revert (e.g. Aerodrome PoolFactory.owner()),
        # where a bare None on the first try is the correct result, not a
        # transient failure worth retrying.
        calls = []

        def fn():
            calls.append(1)
            return None

        _retrying(fn, retries=1)
        self.assertEqual(len(calls), 1)


class TestIsRevert(unittest.TestCase):
    """ADDED 2026-09-22, closes the tracked 'web3_utils helpers rendent None pour un revert comme
    [backlog note]
    on to tell a confirmed EVM revert apart from a network/rate-limit failure. Every branch of its
    own logic gets one direct test here, independent of any retry loop or live w3."""

    def test_contract_logic_error_is_a_revert(self):
        self.assertTrue(_is_revert(ContractLogicError("execution reverted")))

    def test_bad_function_call_output_is_a_revert(self):
        self.assertTrue(_is_revert(BadFunctionCallOutput("could not decode contract function call")))

    def test_decoding_error_is_a_revert(self):
        # Raised by eth_abi (and by this module's own abi_returndata_guard) for a return of the
        # wrong size/shape -- a real "not this interface" fact, not a network problem.
        self.assertTrue(_is_revert(DecodingError("Insufficient bytes")))

    def test_web3_rpc_error_with_code_3_is_a_revert(self):
        # The same JSON-RPC error code chains/tempo/scripts/methodology_test.py already keys on.
        exc = Web3RPCError("eth_call failed", rpc_response={"jsonrpc": "2.0", "id": 1, "error": {"code": 3, "message": "execution reverted"}})
        self.assertTrue(_is_revert(exc))

    def test_web3_rpc_error_with_execution_reverted_message_is_a_revert(self):
        # Some providers use a different code but still say "execution reverted" in the message.
        exc = Web3RPCError("eth_call failed", rpc_response={"error": {"code": -32000, "message": "execution reverted: custom error"}})
        self.assertTrue(_is_revert(exc))

    def test_web3_rpc_error_with_an_unrelated_code_is_not_a_revert(self):
        # -32005 is the conventional "rate limit exceeded" JSON-RPC error code several public
        # providers this project depends on (publicnode, drpc, 1rpc) actually use.
        exc = Web3RPCError("rate limited", rpc_response={"error": {"code": -32005, "message": "call rate limit exhausted, please try again"}})
        self.assertFalse(_is_revert(exc))

    def test_web3_rpc_error_with_no_rpc_response_is_not_a_revert(self):
        # Defensive: a Web3RPCError somehow raised without its rpc_response set must not crash
        # _is_revert(), and must default to "network" (not a revert) like everything else unknown.
        self.assertFalse(_is_revert(Web3RPCError("mystery failure")))

    def test_a_connection_error_is_not_a_revert(self):
        self.assertFalse(_is_revert(ConnectionError("Connection refused")))

    def test_a_timeout_is_not_a_revert(self):
        self.assertFalse(_is_revert(TimeoutError("timed out")))

    def test_an_unrecognized_exception_type_defaults_to_not_a_revert(self):
        # The core safety property: an exception type this function has never heard of must default
        # to "network failure" (skip the target), never to "revert" (silently score it wrong).
        class SomeFutureWeb3Exception(Exception):
            pass
        self.assertFalse(_is_revert(SomeFutureWeb3Exception("who knows")))


class TestRead(unittest.TestCase):
    """_read() replaces the bare `except Exception: return None` every helper below used to have."""

    def setUp(self):
        patcher = patch("lib.web3_utils.time.sleep", return_value=None)
        self.addCleanup(patcher.stop)
        self.sleep = patcher.start()

    def test_returns_immediately_on_first_success(self):
        calls = []

        def fn():
            calls.append(1)
            return "ok"

        self.assertEqual(_read(fn), "ok")
        self.assertEqual(len(calls), 1)
        self.sleep.assert_not_called()

    def test_a_confirmed_revert_returns_none_immediately_without_retrying(self):
        calls = []

        def fn():
            calls.append(1)
            raise ContractLogicError("execution reverted")

        self.assertIsNone(_read(fn, retries=4))
        self.assertEqual(len(calls), 1)  # NOT 4 -- a deterministic revert doesn't need retrying
        self.sleep.assert_not_called()  # and doesn't pay the 0.4/0.8/1.2s backoff either

    def test_a_network_failure_retries_then_raises_rpc_unavailable(self):
        calls = []

        def fn():
            calls.append(1)
            raise ConnectionError("Connection refused")

        with self.assertRaises(RpcUnavailable) as ctx:
            _read(fn, retries=3, what="owner() on 0xABC")
        self.assertEqual(len(calls), 3)  # exactly `retries` attempts, not more
        self.assertIn("owner() on 0xABC", str(ctx.exception))
        self.assertIn("ConnectionError", str(ctx.exception))
        self.assertIn("Connection refused", str(ctx.exception))

    def test_a_network_failure_then_success_returns_the_success(self):
        results = iter([ConnectionError("boom"), ConnectionError("boom"), "ok"])

        def fn():
            r = next(results)
            if isinstance(r, Exception):
                raise r
            return r

        self.assertEqual(_read(fn, retries=4), "ok")

    def test_retries_of_one_means_a_single_attempt_and_still_raises_on_failure(self):
        # The exact override several ecosystems pass at call sites EXPECTED to revert (e.g.
        # Aerodrome PoolFactory.owner() in chains/base-ecosystem/scorers.py) -- retries=1 still
        # means "one attempt", but since 2026-09-22 a NETWORK failure on that one attempt raises
        # instead of being silently taken for the expected revert (only an actual revert still
        # returns bare None on the first try).
        calls = []

        def fn():
            calls.append(1)
            raise TimeoutError("timed out")

        with self.assertRaises(RpcUnavailable):
            _read(fn, retries=1)
        self.assertEqual(len(calls), 1)

    def test_retries_of_one_on_a_revert_still_returns_none(self):
        def fn():
            raise ContractLogicError("execution reverted")

        self.assertIsNone(_read(fn, retries=1))

    def test_an_unrecognized_exception_type_is_treated_as_network_and_raises(self):
        class SomeFutureWeb3Exception(Exception):
            pass

        def fn():
            raise SomeFutureWeb3Exception("who knows")

        with self.assertRaises(RpcUnavailable):
            _read(fn, retries=2)


class _FakeContractCall:
    """w3.eth.contract(...).functions.<fn>(...).call() that either returns a fixed value or raises
    a fixed exception -- shared by the helper-level revert-vs-network tests below."""

    def __init__(self, value=None, raises=None):
        self._value, self._raises = value, raises

    def call(self):
        if self._raises is not None:
            raise self._raises
        return self._value


class _FakeHelperW3:
    """Fakes just enough of Web3 for read_address_getter/call_raw/safe_owners_and_threshold/
    custom_multisig_owners_and_threshold/read_slot_as_address to run against, driven entirely by
    what `outcomes` (a list consumed in order, one per underlying eth_call the target function
    makes) says each call should do."""

    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.eth = self

    def contract(self, address, abi):
        return self

    @property
    def functions(self):
        return self

    def __getattr__(self, name):
        def _fn(*args, **kwargs):
            value, raises = self.outcomes.pop(0)
            return _FakeContractCall(value=value, raises=raises)
        return _fn

    def get_storage_at(self, address, slot):
        value, raises = self.outcomes.pop(0)
        if raises is not None:
            raise raises
        return value


class TestHelperRevertVsNetwork(unittest.TestCase):
    """Each of the 5 public helpers routes through _read()/_is_revert() now (2026-09-22) instead of
    a bare `except Exception: return None`. One revert-returns-None and one network-raises test per
    helper, plus the read_slot_as_address-specific 'never returns None' property."""

    def setUp(self):
        patcher = patch("lib.web3_utils.time.sleep", return_value=None)
        self.addCleanup(patcher.stop)
        patcher.start()

    def test_read_address_getter_returns_none_on_revert(self):
        w3 = _FakeHelperW3([(None, ContractLogicError("execution reverted"))])
        self.assertIsNone(web3_utils.read_address_getter(w3, "0x" + "1" * 40, "owner"))

    def test_read_address_getter_raises_on_persistent_network_failure(self):
        w3 = _FakeHelperW3([(None, ConnectionError("boom"))] * 4)
        with self.assertRaises(RpcUnavailable):
            web3_utils.read_address_getter(w3, "0x" + "1" * 40, "owner")

    def test_call_raw_returns_none_on_revert(self):
        w3 = _FakeHelperW3([(None, ContractLogicError("execution reverted"))])
        self.assertIsNone(web3_utils.call_raw(w3, "0x" + "1" * 40, [], "delay"))

    def test_call_raw_raises_on_persistent_network_failure(self):
        w3 = _FakeHelperW3([(None, TimeoutError("timed out"))] * 4)
        with self.assertRaises(RpcUnavailable):
            web3_utils.call_raw(w3, "0x" + "1" * 40, [], "delay")

    def test_read_address_array_getter_returns_value(self):
        addr = "0x" + "2" * 40
        w3 = _FakeHelperW3([([addr], None)])
        self.assertEqual(web3_utils.read_address_array_getter(w3, "0x" + "1" * 40, "getFreezerRoleMembers"), [addr])

    def test_read_address_array_getter_returns_none_on_revert(self):
        w3 = _FakeHelperW3([(None, ContractLogicError("execution reverted"))])
        self.assertIsNone(web3_utils.read_address_array_getter(w3, "0x" + "1" * 40, "getFreezerRoleMembers"))

    def test_read_address_array_getter_raises_on_persistent_network_failure(self):
        w3 = _FakeHelperW3([(None, ConnectionError("boom"))] * 4)
        with self.assertRaises(RpcUnavailable):
            web3_utils.read_address_array_getter(w3, "0x" + "1" * 40, "getFreezerRoleMembers")

    def test_custom_multisig_owners_and_threshold_returns_none_on_revert(self):
        w3 = _FakeHelperW3([(None, ContractLogicError("execution reverted"))])
        self.assertIsNone(web3_utils.custom_multisig_owners_and_threshold(w3, "0x" + "1" * 40))

    def test_custom_multisig_owners_and_threshold_raises_on_persistent_network_failure(self):
        w3 = _FakeHelperW3([(None, ConnectionError("boom"))] * 4)
        with self.assertRaises(RpcUnavailable):
            web3_utils.custom_multisig_owners_and_threshold(w3, "0x" + "1" * 40)

    def test_read_slot_as_address_raises_rather_than_returning_none_on_any_failure(self):
        # The property specific to this helper: eth_getStorageAt cannot revert (a slot on an
        # address with no code, or never written, just reads back as zero), so EVERY failure here
        # is unambiguously a network problem -- there is no "confirmed revert" case to return None
        # for at all, unlike every other helper in this module.
        w3 = _FakeHelperW3([(None, ConnectionError("boom"))] * 4)
        with self.assertRaises(RpcUnavailable):
            web3_utils.read_slot_as_address(w3, "0x" + "1" * 40, "0x0")

    def test_read_slot_as_address_never_returns_none_even_given_a_revert_shaped_exception(self):
        # Even if something upstream somehow raised a revert-shaped exception (it shouldn't, for
        # eth_getStorageAt) -- read_slot_as_address's contract is still "raise, never None", so a
        # caller can never mistake a failed slot read for a genuinely-unset slot (which decodes as
        # the zero address, a normal successful call, not a failure at all).
        w3 = _FakeHelperW3([(None, ContractLogicError("execution reverted"))])
        with self.assertRaises(RpcUnavailable):
            web3_utils.read_slot_as_address(w3, "0x" + "1" * 40, "0x0")


class TestSafeOwnersAndThresholdRevertVsNetwork(unittest.TestCase):
    """safe_owners_and_threshold() makes two calls (getOwners then getThreshold) per attempt, so it
    needs its own fixture rather than _FakeHelperW3's single-outcome-per-call model."""

    def setUp(self):
        patcher = patch("lib.web3_utils.time.sleep", return_value=None)
        self.addCleanup(patcher.stop)
        patcher.start()
        # No module/singleton gate findings for these tests -- covered separately by
        # TestSafeAuthorityGate above.
        gate_patcher = patch("lib.web3_utils._safe_modules_lib", return_value=_GateStub())
        self.addCleanup(gate_patcher.stop)
        gate_patcher.start()
        web3_utils._AUTHORITY_GATE_CACHE.clear()
        self.addCleanup(web3_utils._AUTHORITY_GATE_CACHE.clear)

    def test_returns_none_on_revert(self):
        w3 = _FakeHelperW3([(None, ContractLogicError("execution reverted"))])
        self.assertIsNone(web3_utils.safe_owners_and_threshold(w3, SAFE_ADDR))

    def test_raises_on_persistent_network_failure(self):
        w3 = _FakeHelperW3([(None, ConnectionError("boom"))] * 4)
        with self.assertRaises(RpcUnavailable):
            web3_utils.safe_owners_and_threshold(w3, SAFE_ADDR)


class TestSafeScore(unittest.TestCase):
    # Moved here 2026-09-17 from scripts/lib/tests/test_scorers.py -- safe_score()
    # itself moved from scripts/lib/scorers.py to this module the same day, so
    # every ecosystem's score_all() can import one canonical copy (the same
    # de-duplication already done for _retrying()).
    def test_wraps_a_single_dict_result_in_a_list(self):
        result = safe_score("target", lambda: {"label": "x"})
        self.assertEqual(result, [{"label": "x"}])

    def test_passes_through_a_list_result_unchanged(self):
        entries = [{"label": "a"}, {"label": "b"}]
        result = safe_score("target", lambda: entries)
        self.assertEqual(result, entries)

    def test_catches_a_transient_style_exception_and_returns_empty(self):
        def boom():
            raise ConnectionError("RPC timed out")

        self.assertEqual(safe_score("flaky-target", boom), [])

    def test_catches_a_deliberate_runtime_error_and_returns_empty(self):
        # Matches score_rollup_l1_authority()'s own deliberate loud-failure
        # guard (raises RuntimeError rather than a silent conservative
        # default) -- safe_score() must isolate that too, not let it crash
        # score_all() and take every OTHER target down with it.
        def scan_bug():
            raise RuntimeError("EXECUTOR_ROLE holders came back EMPTY")

        self.assertEqual(safe_score("rollup-authority", scan_bug), [])

    def test_one_failing_target_does_not_affect_a_sibling_call(self):
        def boom():
            raise ValueError("bad state")

        def ok():
            return {"label": "healthy"}

        results = []
        results.extend(safe_score("bad", boom))
        results.extend(safe_score("good", ok))
        self.assertEqual(results, [{"label": "healthy"}])

    def test_passes_through_extra_args_to_fn(self):
        result = safe_score("target", lambda addr, label: {"target": addr, "label": label}, "0xABC", "My Vault")
        self.assertEqual(result, [{"target": "0xABC", "label": "My Vault"}])


if __name__ == "__main__":
    unittest.main()


class _FakeSafeContract:
    """w3.eth.contract(...).functions.getOwners()/getThreshold().call() for the Safe ABI."""

    def __init__(self, owners, threshold):
        self.functions = self
        self._owners, self._threshold = owners, threshold

    def getOwners(self):  # noqa: N802
        return _Call(self._owners)

    def getThreshold(self):  # noqa: N802
        return _Call(self._threshold)


class _Call:
    def __init__(self, value):
        self.value = value

    def call(self):
        return self.value


class _FakeSafeW3:
    def __init__(self, safes):
        self.safes = {k.lower(): v for k, v in safes.items()}
        self.eth = self

    def contract(self, address, abi):
        if address.lower() not in self.safes:
            # A real non-Safe address reverts on getOwners()/getThreshold() -- ContractLogicError is
            # what web3.py actually raises for that, and is exactly what _is_revert() must recognize
            # as "not this interface" (None), distinct from a persistent RPC failure (RpcUnavailable).
            # A bare RuntimeError here would (correctly, since 2026-09-22) be classified as network.
            raise ContractLogicError("execution reverted")
        return _FakeSafeContract(*self.safes[address.lower()])


class _GateStub:
    """Stands in for scripts/lib/safe_modules.py: gate_findings(w3, safe, retries) -> (blocking, info)."""

    def __init__(self, blocking=(), info=()):
        self.blocking, self.info, self.calls = list(blocking), list(info), []

    def gate_findings(self, w3, safe, retries=4):
        self.calls.append(safe)
        return list(self.blocking), list(self.info)


SAFE_ADDR = "0x" + "5a" * 20
OWNERS = ["0x" + "0%d" % i * 20 for i in range(1, 4)]


class TestSafeAuthorityGate(unittest.TestCase):
    """ADDED 2026-09-21: safe_owners_and_threshold() returns None for a Safe with an unanalyzed module or singleton."""

    def setUp(self):
        for patcher in (patch("lib.web3_utils.time.sleep", return_value=None),):
            self.addCleanup(patcher.stop)
            patcher.start()
        web3_utils._AUTHORITY_GATE_LOG.clear()
        web3_utils._AUTHORITY_GATE_CACHE.clear()
        self.addCleanup(web3_utils._AUTHORITY_GATE_LOG.clear)
        self.addCleanup(web3_utils._AUTHORITY_GATE_CACHE.clear)
        self.w3 = _FakeSafeW3({SAFE_ADDR: (OWNERS, 2)})

    def _with_stub(self, stub):
        patcher = patch("lib.web3_utils._safe_modules_lib", return_value=stub)
        self.addCleanup(patcher.stop)
        patcher.start()

    def test_a_clean_safe_resolves_and_logs_nothing(self):
        stub = _GateStub()
        self._with_stub(stub)
        self.assertEqual(web3_utils.safe_owners_and_threshold(self.w3, SAFE_ADDR), (OWNERS, 2))
        self.assertEqual(web3_utils._AUTHORITY_GATE_LOG, [])

    def test_a_blocking_finding_makes_the_safe_unresolved_like_not_a_safe(self):
        self._with_stub(_GateStub(blocking=["module(s) not analyzed: 0xabc"]))
        self.assertIsNone(web3_utils.safe_owners_and_threshold(self.w3, SAFE_ADDR))
        self.assertEqual([kind for _, kind, _ in web3_utils._AUTHORITY_GATE_LOG], ["blocking"])

    def test_an_info_only_finding_keeps_the_score_and_only_records_it(self):
        self._with_stub(_GateStub(info=["modules that could not be read"]))
        self.assertEqual(web3_utils.safe_owners_and_threshold(self.w3, SAFE_ADDR), (OWNERS, 2))
        self.assertEqual([kind for _, kind, _ in web3_utils._AUTHORITY_GATE_LOG], ["info"])

    def test_check_modules_false_skips_the_gate_entirely(self):
        stub = _GateStub(blocking=["module(s) not analyzed: 0xabc"])
        self._with_stub(stub)
        self.assertEqual(web3_utils.safe_owners_and_threshold(self.w3, SAFE_ADDR, check_modules=False), (OWNERS, 2))
        self.assertEqual(stub.calls, [])

    def test_a_non_safe_is_none_and_never_reaches_the_gate(self):
        stub = _GateStub()
        self._with_stub(stub)
        self.assertIsNone(web3_utils.safe_owners_and_threshold(self.w3, "0x" + "77" * 20))
        self.assertEqual(stub.calls, [])

    def test_the_gate_result_is_cached_briefly_then_read_again(self):
        stub = _GateStub()
        self._with_stub(stub)
        # monotonic() is read on a lookup that finds an entry, and when storing: store@100, lookup@150, lookup@1000, store@1000
        with patch("lib.web3_utils.time.monotonic", side_effect=[100.0, 150.0, 1000.0, 1000.0]):
            web3_utils.safe_owners_and_threshold(self.w3, SAFE_ADDR)
            web3_utils.safe_owners_and_threshold(self.w3, SAFE_ADDR)   # 50 s later: cached
            self.assertEqual(len(stub.calls), 1)
            web3_utils.safe_owners_and_threshold(self.w3, SAFE_ADDR)   # 900 s later: past the TTL
        self.assertEqual(len(stub.calls), 2)

    def test_safe_score_turns_a_blocking_gate_into_a_note_on_the_result_and_drains_the_log(self):
        self._with_stub(_GateStub(blocking=["module(s) not analyzed: 0xabc"]))

        def scorer(w3):
            resolved = web3_utils.safe_owners_and_threshold(w3, SAFE_ADDR)
            return {"target": "t", "notes": ["a scorer note"], "resolved": resolved}

        results = safe_score("t", scorer, self.w3)
        self.assertIsNone(results[0]["resolved"])
        gate_notes = [n for n in results[0]["notes"] if n.startswith("SAFE AUTHORITY GATE")]
        self.assertEqual(len(gate_notes), 1)
        self.assertIn("module(s) not analyzed: 0xabc", gate_notes[0])
        self.assertIn("treated as unresolved", gate_notes[0])
        self.assertEqual(web3_utils._AUTHORITY_GATE_LOG, [])

    def test_safe_score_notes_an_info_finding_without_claiming_a_degradation(self):
        self._with_stub(_GateStub(info=["modules that could not be read"]))

        def scorer(w3):
            web3_utils.safe_owners_and_threshold(w3, SAFE_ADDR)
            return {"target": "t", "notes": []}

        note = safe_score("t", scorer, self.w3)[0]["notes"][0]
        self.assertIn("score was left as computed, not confirmed", note)
        self.assertNotIn("SAFE AUTHORITY GATE", note)

    def test_a_gate_note_lands_on_every_result_of_a_multi_result_scorer_once(self):
        self._with_stub(_GateStub(blocking=["singleton 0x1 that is not a published Safe build and not analyzed"]))

        def scorer(w3):
            web3_utils.safe_owners_and_threshold(w3, SAFE_ADDR)
            web3_utils.safe_owners_and_threshold(w3, SAFE_ADDR)  # read twice: one note, not two
            return [{"target": "a", "notes": []}, {"target": "b", "notes": []}]

        results = safe_score("t", scorer, self.w3)
        for r in results:
            self.assertEqual(sum(n.startswith("SAFE AUTHORITY GATE") for n in r["notes"]), 1)

    def test_a_scorer_that_raises_leaves_no_stale_log_for_the_next_one(self):
        self._with_stub(_GateStub(blocking=["module(s) not analyzed: 0xabc"]))

        def broken(w3):
            web3_utils.safe_owners_and_threshold(w3, SAFE_ADDR)
            raise RuntimeError("boom")

        self.assertEqual(safe_score("broken", broken, self.w3), [])
        self.assertEqual(web3_utils._AUTHORITY_GATE_LOG, [])
        self.assertEqual(safe_score("fine", lambda w3: {"target": "x", "notes": []}, self.w3), [{"target": "x", "notes": []}])

