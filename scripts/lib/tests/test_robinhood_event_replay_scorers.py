"""
Unit tests for the event-log-replay family of scoring logic in
`scripts/lib/scorers.py` (Robinhood Chain) -- "batch C" (event-log-replay
family) of the 2026-09-18 test-coverage audit, the hardest/most novel batch:
the shared `_replay_role_holders()` chunked eth_getLogs replay helper, plus
its three callers/siblings `score_rollup_l1_authority`,
`score_beefy_spy_weth_vault`, and `score_fables_pool_registry`.

Same FakeHelpers/FakeW3 approach as test_robinhood_uniswap_family_scorers.py
and the same package-relative-import workaround (`sys.path.insert` +
`from lib import scorers`) as that file and test_scorers.py -- scorers.py
uses `from .web3_utils import ...`, so it cannot be loaded standalone via
importlib.util.spec_from_file_location the way the per-ecosystem
chains/*/scorers.py files can.

New wrinkle for this batch: none of the read primitives this project already
mocks (call_raw, read_address_getter, safe_owners_and_threshold, is_eoa,
read_slot_as_address) cover raw `eth_getLogs` or raw `.eth.contract(...)`
object usage. FakeEth below adds:
  - a controllable `get_logs(filter_dict)`, keyed by
    (address, fromBlock, toBlock, topic0) -- precise enough to give a
    genuinely different canned response per chunk and per event kind (GRANT
    vs REVOKE), so a multi-chunk test can actually exercise the chunk loop
    assembling >1 window rather than a single short-circuited fetch that
    ignores its own range.
  - a controllable `.eth.contract(address, abi)` returning a fake Contract
    object whose `.functions.<name>().call()` is dispatched by
    (address, function_name) -> value, mirroring call_raw's own
    dispatch-table fake but shaped for score_rollup_l1_authority's raw
    Web3.py contract-object calling convention (it does not go through
    call_raw/read_address_getter/safe_owners_and_threshold at all).
  - a controllable `.eth.get_code(addr)` and `.eth.get_transaction_count(addr)`
    (both already precedented by test_robinhood_uniswap_family_scorers.py /
    the address-classification scorers, reused here for
    score_fables_pool_registry's EIP-7702-vs-bare-EOA classification and
    score_rollup_l1_authority's Safe-vs-Timelock code-size heuristic).
  - a plain int `.eth.block_number`, which drives `_replay_role_holders()`'s
    own chunk loop.

Confidence notes (read before trusting any single assertion below -- see
the final report for the full list): the multi-chunk assembly test and the
three regression tests for `_replay_role_holders()`'s own documented FIXED
bugs are the ones this file is most confident in, since they were built by
reading that function character-by-character. `score_rollup_l1_authority`'s
signer-overlap cap (>=50%) is a single boundary-value construction (exactly
2-of-4 shared) rather than an exhaustive sweep -- confirmed by reading the
`>=` in the source, not assumed.
"""
import os
import sys
import unittest

from web3 import Web3 as RealWeb3

REPO_ROOT = os.path.join(os.path.dirname(__file__), "..", "..", "..")

sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))
from lib import scorers  # noqa: E402


# --------------------------------------------------------------------- fakes

RAISE_LOGS = object()  # sentinel: a canned get_logs() response of this exact value raises instead of returning


def _log_key(filter_dict):
    """(address, fromBlock, toBlock, topic0) -- precise enough to give a
    different canned response per chunk and per event kind (GRANT vs
    REVOKE); a fake that ignored fromBlock/toBlock could never prove the
    chunk loop actually assembles >1 window correctly."""
    topics = filter_dict["topics"]
    return (filter_dict.get("address"), filter_dict.get("fromBlock"), filter_dict.get("toBlock"), topics[0])


def _canned_get_logs(responses):
    """responses: {(address, fromBlock, toBlock, topic0_hex): list[log-dict] or RAISE_LOGS}.
    A missing key returns [] (no logs found for that chunk/kind), matching a
    real RPC returning nothing rather than erroring."""
    def _get_logs(filter_dict):
        result = responses.get(_log_key(filter_dict), [])
        if result is RAISE_LOGS:
            raise RuntimeError("simulated eth_getLogs RPC failure")
        return result
    return _get_logs


def _addr_topic(address):
    """32-byte, 12-zero-padded topic encoding of an address -- exactly the
    shape `_replay_role_holders()`'s malformed-topic guard expects."""
    return b"\x00" * 12 + bytes.fromhex(RealWeb3.to_checksum_address(address)[2:])


def _role_log(block_number, log_index, topic1, holder_address, topic0=b"\x00" * 32):
    """A well-formed RoleGranted/RoleRevoked-shaped log entry. `topic1` is
    whatever the caller wants in topics[1] (a role hash for
    `_replay_role_holders()`'s callers, or a 32-byte roleId encoding for
    score_fables_pool_registry -- topics[0] is never actually read back by
    either consumer, only used to pick which canned response list a query
    lands on)."""
    return {"topics": [topic0, topic1, _addr_topic(holder_address)], "blockNumber": block_number, "logIndex": log_index}


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
        self.address = address
        self.functions = _FakeContractFunctions(address, results)


class FakeEth:
    def __init__(self, code_sizes=None, get_logs_fn=None, block_number=0, contract_results=None, tx_counts=None):
        self._code_sizes = code_sizes or {}                # address -> bytes
        self._get_logs_fn = get_logs_fn or (lambda filter_dict: [])
        self.block_number = block_number                    # plain int -- drives _replay_role_holders()'s chunk loop
        self._contract_results = contract_results or {}     # (address, function_name) -> value-or-Exception
        self._tx_counts = tx_counts or {}

    def get_code(self, addr):
        return self._code_sizes.get(addr, b"")

    def get_logs(self, filter_dict):
        return self._get_logs_fn(filter_dict)

    def get_transaction_count(self, addr):
        return self._tx_counts.get(addr, 0)

    def contract(self, address, abi=None):
        return _FakeContract(address, self._contract_results)


class FakeW3:
    def __init__(self, code_sizes=None, get_logs_fn=None, block_number=0, contract_results=None, tx_counts=None):
        self.eth = FakeEth(code_sizes, get_logs_fn, block_number, contract_results, tx_counts)

    @staticmethod
    def to_checksum_address(addr):
        return RealWeb3.to_checksum_address(addr)


class FakeHelpers:
    """Same shape as test_robinhood_uniswap_family_scorers.py's FakeHelpers --
    kept even though most tests in this file only need a subset (call_raw /
    read_address_getter / safe_owners_and_threshold for the beefy+fables
    scorers, get_w3 alone for the rollup scorer), so `_patch_helpers` can
    stay one uniform helper."""

    def __init__(self):
        self.address_getters = {}
        self.call_raw_results = {}
        self.slot_results = {}
        self.safe_results = {}
        self.eoa_results = {}
        self.l1_w3 = FakeW3()

    def read_address_getter(self, w3, address, function_name, retries=4):
        return self.address_getters.get((address, function_name))

    def call_raw(self, w3, address, abi_fragment, function_name, *args, retries=4):
        return self.call_raw_results.get((address, function_name, args))

    def read_slot_as_address(self, w3, address, slot, retries=4):
        return self.slot_results.get((address, slot))

    def safe_owners_and_threshold(self, w3, address, retries=4):
        return self.safe_results.get(address)

    def is_eoa(self, w3, address):
        return self.eoa_results.get(address, True)

    def get_w3(self, rpc_url):
        return self.l1_w3


def _patch_helpers(test_case, fake):
    names = ["read_address_getter", "call_raw", "read_slot_as_address", "safe_owners_and_threshold", "is_eoa", "get_w3"]
    originals = {n: getattr(scorers, n) for n in names}
    for n in names:
        setattr(scorers, n, getattr(fake, n))
    test_case.addCleanup(lambda: [setattr(scorers, n, originals[n]) for n in names])


def _owners(n, start=1):
    return [RealWeb3.to_checksum_address("0x" + hex(i)[2:].zfill(40)) for i in range(start, start + n)]


# --------------------------------------------------------------------- shared constants (independently recomputed, never copy-pasted)
GRANT_TOPIC = "0x" + RealWeb3.keccak(text="RoleGranted(bytes32,address,address)").hex()
REVOKE_TOPIC = "0x" + RealWeb3.keccak(text="RoleRevoked(bytes32,address,address)").hex()
EXECUTOR_ROLE_HASH = RealWeb3.keccak(text="EXECUTOR_ROLE")
PROPOSER_ROLE_HASH = RealWeb3.keccak(text="PROPOSER_ROLE")
CANCELLER_ROLE_HASH = RealWeb3.keccak(text="CANCELLER_ROLE")

ADDR_A = RealWeb3.to_checksum_address("0x" + "aa" * 20)
ADDR_B = RealWeb3.to_checksum_address("0x" + "bb" * 20)


# =======================================================================
# _replay_role_holders (shared helper, tested directly)
# =======================================================================
class TestReplayRoleHolders(unittest.TestCase):
    CONTRACT = RealWeb3.to_checksum_address("0x" + "c0" * 20)

    def test_single_role_name_returns_a_plain_set(self):
        responses = {
            (self.CONTRACT, 0, 100, GRANT_TOPIC): [
                _role_log(10, 0, EXECUTOR_ROLE_HASH, ADDR_A),
                _role_log(11, 0, EXECUTOR_ROLE_HASH, ADDR_B),
            ],
        }
        w3 = FakeW3(get_logs_fn=_canned_get_logs(responses), block_number=100)
        holders = scorers._replay_role_holders(w3, self.CONTRACT, "EXECUTOR_ROLE", start_block=0)
        self.assertIsInstance(holders, set)
        self.assertEqual(holders, {ADDR_A, ADDR_B})

    def test_list_of_role_names_returns_dict_of_sets_via_one_shared_fetch(self):
        # Both roles are fetched via ONE OR-filter query per event kind (2
        # log-fetches total for the whole chunk, not 2 per role) -- a single
        # canned GRANT response containing logs for BOTH roles proves the
        # function still buckets them correctly by their own topics[1].
        responses = {
            (self.CONTRACT, 0, 100, GRANT_TOPIC): [
                _role_log(10, 0, PROPOSER_ROLE_HASH, ADDR_A),
                _role_log(11, 0, CANCELLER_ROLE_HASH, ADDR_B),
            ],
        }
        w3 = FakeW3(get_logs_fn=_canned_get_logs(responses), block_number=100)
        roles = scorers._replay_role_holders(w3, self.CONTRACT, ["PROPOSER_ROLE", "CANCELLER_ROLE"], start_block=0)
        self.assertEqual(roles, {"PROPOSER_ROLE": {ADDR_A}, "CANCELLER_ROLE": {ADDR_B}})

    def test_multi_chunk_assembly_across_a_chunk_boundary(self):
        # block_number=60_000, chunk size 50_000 -> exactly 2 chunks:
        # [0, 49_999] and [50_000, 60_000]. ADDR_A is granted in chunk 1,
        # then revoked in chunk 2; ADDR_B is granted only in chunk 2. This
        # only comes out right if BOTH chunks are actually queried (not just
        # the first, short-circuited) AND the running holder state carries
        # across chunks (not reset per chunk) -- a dropped second chunk
        # would leave {ADDR_A}; a per-chunk-reset bug would leave {ADDR_A,
        # ADDR_B} (chunk 2's revoke never able to remove a grant chunk 1
        # "forgot" about).
        responses = {
            (self.CONTRACT, 0, 49_999, GRANT_TOPIC): [_role_log(20_000, 0, EXECUTOR_ROLE_HASH, ADDR_A)],
            (self.CONTRACT, 50_000, 60_000, GRANT_TOPIC): [_role_log(56_000, 1, EXECUTOR_ROLE_HASH, ADDR_B)],
            (self.CONTRACT, 50_000, 60_000, REVOKE_TOPIC): [_role_log(55_000, 0, EXECUTOR_ROLE_HASH, ADDR_A)],
        }
        w3 = FakeW3(get_logs_fn=_canned_get_logs(responses), block_number=60_000)
        holders = scorers._replay_role_holders(w3, self.CONTRACT, "EXECUTOR_ROLE", start_block=0)
        self.assertEqual(holders, {ADDR_B})

    def test_regression_same_block_sorts_by_log_index_not_fetch_order(self):
        # FIXED 2026-09-17: GRANT-topic logs are always fetched (and
        # appended to the internal `events` list) BEFORE REVOKE-topic logs
        # for the same chunk, regardless of true chronological order. Here
        # ADDR_A is REVOKED at logIndex=3 and then, later in the SAME block,
        # GRANTED at logIndex=7 -- the correct final state is "holds the
        # role". Trusting raw fetch/insertion order (GRANT-topic results
        # appended first) would process GRANT(7) before REVOKE(3) and
        # wrongly conclude ADDR_A does NOT hold the role.
        responses = {
            (self.CONTRACT, 0, 100, GRANT_TOPIC): [_role_log(50, 7, EXECUTOR_ROLE_HASH, ADDR_A)],
            (self.CONTRACT, 0, 100, REVOKE_TOPIC): [_role_log(50, 3, EXECUTOR_ROLE_HASH, ADDR_A)],
        }
        w3 = FakeW3(get_logs_fn=_canned_get_logs(responses), block_number=100)
        holders = scorers._replay_role_holders(w3, self.CONTRACT, "EXECUTOR_ROLE", start_block=0)

        # Prove this fixture actually distinguishes fixed-vs-broken behavior:
        # replaying in raw fetch order (GRANT-topic results first, matching
        # how `events` is actually built before the sort) gives the WRONG
        # answer for this exact scenario.
        naive_fetch_order = [("GRANT", 7), ("REVOKE", 3)]
        naive_result = set()
        for kind, _ in naive_fetch_order:
            naive_result.add(ADDR_A) if kind == "GRANT" else naive_result.discard(ADDR_A)
        self.assertNotIn(ADDR_A, naive_result)  # the old, broken behavior

        self.assertIn(ADDR_A, holders)  # the real function's current, correct (blockNumber, logIndex)-sorted behavior

    def test_regression_malformed_topics2_skipped_not_crashed(self):
        # FIXED 2026-09-17: a malformed topics[2] (not exactly 32 bytes with
        # 12 zero padding bytes) used to be sliced into a spurious address
        # with no guard. One well-formed log (ADDR_A) and one malformed log
        # (20 raw address bytes, no zero-padding at all -- the exact shape a
        # non-address-typed or mis-decoded indexed param would produce) in
        # the SAME response: the malformed one must be silently skipped, not
        # crash the scan or corrupt ADDR_A's own result.
        good_log = _role_log(10, 0, EXECUTOR_ROLE_HASH, ADDR_A)
        malformed_log = {
            "topics": [b"\x00" * 32, EXECUTOR_ROLE_HASH, bytes.fromhex(ADDR_B[2:])],  # 20 bytes, not 32 -- no padding at all
            "blockNumber": 10, "logIndex": 1,
        }
        responses = {(self.CONTRACT, 0, 100, GRANT_TOPIC): [good_log, malformed_log]}
        w3 = FakeW3(get_logs_fn=_canned_get_logs(responses), block_number=100)
        holders = scorers._replay_role_holders(w3, self.CONTRACT, "EXECUTOR_ROLE", start_block=0)
        self.assertEqual(holders, {ADDR_A})  # malformed log skipped; good one unaffected; no exception raised

    def test_regression_raises_runtimeerror_after_4_failed_attempts(self):
        # FIXED 2026-09-17: 4 failed attempts on one chunk must raise
        # RuntimeError, never silently return an empty set (which would
        # read as "nobody holds this role" instead of "the scan failed").
        # Real retries sleep 1.5*attempt between tries -- patch scorers.time
        # to keep this test fast rather than ~15s of real sleeping.
        original_sleep = scorers.time.sleep
        scorers.time.sleep = lambda *a, **kw: None
        self.addCleanup(lambda: setattr(scorers.time, "sleep", original_sleep))

        responses = {(self.CONTRACT, 0, 100, GRANT_TOPIC): RAISE_LOGS}
        w3 = FakeW3(get_logs_fn=_canned_get_logs(responses), block_number=100)
        with self.assertRaises(RuntimeError):
            scorers._replay_role_holders(w3, self.CONTRACT, "EXECUTOR_ROLE", start_block=0)


# =======================================================================
# score_rollup_l1_authority
# =======================================================================
EXECUTOR = "0x552603b4bc1f5E896AF2854548D6380f45f1B4bf"  # hardcoded literal in the source -- not a hash, copied as-is
L1_START_BLOCK = 25_300_000

SAFE_ADDR = RealWeb3.to_checksum_address("0x" + "5a" * 20)       # Security Council Safe -- holds EXECUTOR_ROLE
TIMELOCK_ADDR = RealWeb3.to_checksum_address("0x" + "71" * 20)   # holds EXECUTOR_ROLE alongside the Safe
PROPOSER_ADDR = RealWeb3.to_checksum_address("0x" + "70" * 20)   # veto-path: distinct proposer
CANCELLER_ADDR = RealWeb3.to_checksum_address("0x" + "c1" * 20)  # veto-path: distinct canceller
PC_SAFE_ADDR = RealWeb3.to_checksum_address("0x" + "9c" * 20)    # single holder of BOTH PROPOSER_ROLE and CANCELLER_ROLE


def _executor_role_logs(safe_addr, timelock_addr, block_number=L1_START_BLOCK):
    return {
        (EXECUTOR, L1_START_BLOCK, block_number, GRANT_TOPIC): [
            _role_log(L1_START_BLOCK, 0, EXECUTOR_ROLE_HASH, safe_addr),
            _role_log(L1_START_BLOCK, 1, EXECUTOR_ROLE_HASH, timelock_addr),
        ],
    }


def _proposer_canceller_logs(timelock_addr, proposer_holder, canceller_holder, block_number=L1_START_BLOCK):
    return {
        (timelock_addr, L1_START_BLOCK, block_number, GRANT_TOPIC): [
            _role_log(L1_START_BLOCK, 0, PROPOSER_ROLE_HASH, proposer_holder),
            _role_log(L1_START_BLOCK, 1, CANCELLER_ROLE_HASH, canceller_holder),
        ],
    }


def _l1_fakew3(get_logs_responses, contract_results, code_sizes=None):
    return FakeW3(
        get_logs_fn=_canned_get_logs(get_logs_responses),
        block_number=L1_START_BLOCK,
        contract_results=contract_results,
        code_sizes=code_sizes or {SAFE_ADDR: b"\x00" * 200, TIMELOCK_ADDR: b"\x00" * 5000},
    )


def _patch_get_w3(test_case, l1_fake_w3):
    fake = FakeHelpers()
    fake.l1_w3 = l1_fake_w3
    _patch_helpers(test_case, fake)


class TestScoreRollupL1Authority(unittest.TestCase):
    SAFE_OWNERS = _owners(8, start=1)  # same 8 addresses ("Security Council") reused across every test in this class

    def _base_contract_results(self, min_delay=604_800):
        return {
            (SAFE_ADDR, "getOwners"): self.SAFE_OWNERS,
            (SAFE_ADDR, "getThreshold"): 7,
            (TIMELOCK_ADDR, "getMinDelay"): min_delay,
        }

    def test_veto_path_happy_path_everything_resolves_and_returns_six_targets(self):
        responses = {
            **_executor_role_logs(SAFE_ADDR, TIMELOCK_ADDR),
            **_proposer_canceller_logs(TIMELOCK_ADDR, PROPOSER_ADDR, CANCELLER_ADDR),
        }
        _patch_get_w3(self, _l1_fakew3(responses, self._base_contract_results()))

        result = scorers.score_rollup_l1_authority(FakeW3())

        # (f) 6 targets, all sharing one identically-computed composite/
        # admin_key/multisig/timelock_score, only target/label differing.
        self.assertEqual(len(result), 6)
        self.assertEqual(len({r["target"] for r in result}), 6)
        self.assertEqual(len({r["label"] for r in result}), 6)
        first = result[0]
        self.assertEqual((first["adminKeyScore"], first["multisigScore"], first["timelockScore"]), (78, 75, 35))
        self.assertEqual(first["compositeScore"], scorers._composite(78, 75, 35))
        for r in result[1:]:
            self.assertEqual(r["adminKeyScore"], first["adminKeyScore"])
            self.assertEqual(r["multisigScore"], first["multisigScore"])
            self.assertEqual(r["timelockScore"], first["timelockScore"])
            self.assertEqual(r["compositeScore"], first["compositeScore"])
        self.assertTrue(any("genuinely distinct addresses" in n for n in first["notes"]))

    def test_min_delay_zero_scores_timelock_zero(self):
        responses = _executor_role_logs(SAFE_ADDR, TIMELOCK_ADDR)  # no PROPOSER/CANCELLER grants needed -- branch never reaches them
        _patch_get_w3(self, _l1_fakew3(responses, self._base_contract_results(min_delay=0)))

        result = scorers.score_rollup_l1_authority(FakeW3())
        self.assertEqual((result[0]["adminKeyScore"], result[0]["multisigScore"], result[0]["timelockScore"]), (78, 75, 0))
        self.assertTrue(any("Timelock delay is 0" in n for n in result[0]["notes"]))

    def test_real_delay_but_zero_proposer_holders_scores_decorative_five(self):
        responses = _executor_role_logs(SAFE_ADDR, TIMELOCK_ADDR)  # no PROPOSER_ROLE/CANCELLER_ROLE grants at all -> both empty sets
        _patch_get_w3(self, _l1_fakew3(responses, self._base_contract_results()))

        result = scorers.score_rollup_l1_authority(FakeW3())
        self.assertEqual(result[0]["timelockScore"], 5)
        self.assertTrue(any("decorative" in n for n in result[0]["notes"]))

    def test_proposer_equals_canceller_stays_at_20_below_50_percent_overlap(self):
        pc_owners = [self.SAFE_OWNERS[0]] + _owners(3, start=100)  # 1 of 4 shared with Security Council = 25%
        responses = {
            **_executor_role_logs(SAFE_ADDR, TIMELOCK_ADDR),
            **_proposer_canceller_logs(TIMELOCK_ADDR, PC_SAFE_ADDR, PC_SAFE_ADDR),
        }
        contract_results = self._base_contract_results()
        contract_results[(PC_SAFE_ADDR, "getOwners")] = pc_owners
        _patch_get_w3(self, _l1_fakew3(responses, contract_results))

        result = scorers.score_rollup_l1_authority(FakeW3())
        self.assertEqual(result[0]["timelockScore"], 20)
        self.assertTrue(any("no real separation of powers" in n for n in result[0]["notes"]))

    def test_proposer_equals_canceller_caps_to_10_at_50_percent_overlap(self):
        pc_owners = self.SAFE_OWNERS[0:2] + _owners(2, start=200)  # 2 of 4 shared with Security Council = 50% (the `>=` boundary itself)
        responses = {
            **_executor_role_logs(SAFE_ADDR, TIMELOCK_ADDR),
            **_proposer_canceller_logs(TIMELOCK_ADDR, PC_SAFE_ADDR, PC_SAFE_ADDR),
        }
        contract_results = self._base_contract_results()
        contract_results[(PC_SAFE_ADDR, "getOwners")] = pc_owners
        _patch_get_w3(self, _l1_fakew3(responses, contract_results))

        result = scorers.score_rollup_l1_authority(FakeW3())
        self.assertEqual(result[0]["timelockScore"], 10)
        self.assertTrue(any("substantially the same" in n for n in result[0]["notes"]))

    def test_executor_role_empty_raises_runtimeerror(self):
        _patch_get_w3(self, _l1_fakew3({}, {}))  # no GRANT/REVOKE logs at all for EXECUTOR -> empty holder set
        with self.assertRaises(RuntimeError):
            scorers.score_rollup_l1_authority(FakeW3())


# =======================================================================
# score_beefy_spy_weth_vault
# =======================================================================
BEEFY_VAULT = "0x87673A619Fc4F3Fc08068A0BB04f60aA2D04ca62"  # hardcoded literal in the source
VAULT_TIMELOCK = RealWeb3.to_checksum_address("0x" + "7a" * 20)     # vault.owner()
BEEFY_STRATEGY = RealWeb3.to_checksum_address("0x" + "57" * 20)     # vault.strategy()
STRATEGY_TIMELOCK = RealWeb3.to_checksum_address("0x" + "7b" * 20)  # strategy.owner()
BEEFY_SAFE = RealWeb3.to_checksum_address("0x" + "5f" * 20)         # PROPOSER_ROLE == CANCELLER_ROLE holder on both Timelocks (real scenario)
STRAT_ONLY_HOLDER = RealWeb3.to_checksum_address("0x" + "5e" * 20)  # a DIFFERENT holder on the strategy Timelock (regression scenario)


class TestScoreBeefySpyWethVault(unittest.TestCase):
    def test_happy_path_roles_match_same_safe_governs_both_timelocks(self):
        fake = FakeHelpers()
        fake.address_getters[(BEEFY_VAULT, "owner")] = VAULT_TIMELOCK
        fake.call_raw_results[(BEEFY_VAULT, "strategy", ())] = BEEFY_STRATEGY
        fake.address_getters[(BEEFY_STRATEGY, "owner")] = STRATEGY_TIMELOCK
        fake.call_raw_results[(BEEFY_VAULT, "approvalDelay", ())] = 21_600
        fake.call_raw_results[(VAULT_TIMELOCK, "getMinDelay", ())] = 0
        fake.call_raw_results[(STRATEGY_TIMELOCK, "getMinDelay", ())] = 21_600
        fake.safe_results[BEEFY_SAFE] = (_owners(6, start=1), 3)
        _patch_helpers(self, fake)

        responses = {
            (VAULT_TIMELOCK, 0, 1000, GRANT_TOPIC): [
                _role_log(1, 0, PROPOSER_ROLE_HASH, BEEFY_SAFE),
                _role_log(1, 1, CANCELLER_ROLE_HASH, BEEFY_SAFE),
            ],
            (STRATEGY_TIMELOCK, 0, 1000, GRANT_TOPIC): [
                _role_log(1, 0, PROPOSER_ROLE_HASH, BEEFY_SAFE),
                _role_log(1, 1, CANCELLER_ROLE_HASH, BEEFY_SAFE),
            ],
        }
        w3 = FakeW3(get_logs_fn=_canned_get_logs(responses), block_number=1000)

        result = scorers.score_beefy_spy_weth_vault(w3)
        self.assertEqual(result["adminKeyScore"], 65)   # _safe_rooted_scores(threshold=3, ...) -> threshold >= 3
        self.assertEqual(result["multisigScore"], 60)   # 3*15 + (6-3)*5 = 45+15 = 60
        self.assertEqual(result["timelockScore"], 20)   # real >0 approvalDelay, but PROPOSER_ROLE == CANCELLER_ROLE: no independent veto
        self.assertEqual(result["compositeScore"], scorers._composite(65, 60, 20))

    def test_regression_strategy_timelock_roles_not_matching_vault_degrades(self):
        # FIXED 2026-09-17: the strategy Timelock's own PROPOSER_ROLE/
        # CANCELLER_ROLE were never independently replayed before -- a
        # divergence from the vault Timelock's roles would go completely
        # undetected. Here the strategy Timelock's roles are held by a
        # DIFFERENT address than the vault Timelock's -- must degrade to the
        # conservative 15/0/0 default rather than trusting the vault-only
        # read (which alone still resolves a real, well-formed 3-of-6 Safe).
        fake = FakeHelpers()
        fake.address_getters[(BEEFY_VAULT, "owner")] = VAULT_TIMELOCK
        fake.call_raw_results[(BEEFY_VAULT, "strategy", ())] = BEEFY_STRATEGY
        fake.address_getters[(BEEFY_STRATEGY, "owner")] = STRATEGY_TIMELOCK
        fake.call_raw_results[(BEEFY_VAULT, "approvalDelay", ())] = 21_600
        fake.safe_results[BEEFY_SAFE] = (_owners(6, start=1), 3)
        _patch_helpers(self, fake)

        responses = {
            (VAULT_TIMELOCK, 0, 1000, GRANT_TOPIC): [
                _role_log(1, 0, PROPOSER_ROLE_HASH, BEEFY_SAFE),
                _role_log(1, 1, CANCELLER_ROLE_HASH, BEEFY_SAFE),
            ],
            (STRATEGY_TIMELOCK, 0, 1000, GRANT_TOPIC): [
                _role_log(1, 0, PROPOSER_ROLE_HASH, STRAT_ONLY_HOLDER),
                _role_log(1, 1, CANCELLER_ROLE_HASH, STRAT_ONLY_HOLDER),
            ],
        }
        w3 = FakeW3(get_logs_fn=_canned_get_logs(responses), block_number=1000)

        result = scorers.score_beefy_spy_weth_vault(w3)
        self.assertEqual((result["adminKeyScore"], result["multisigScore"], result["timelockScore"]), (15, 0, 0))
        self.assertTrue(any("do NOT match the vault Timelock" in n for n in result["notes"]))


# =======================================================================
# score_fables_pool_registry
# =======================================================================
FABLES_REGISTRY = "0x159a113E012593d9B3Cc63aD45e30F0467e13ef3"  # hardcoded literal in the source
FABLES_MANAGER = RealWeb3.to_checksum_address("0x" + "4a" * 20)
FABLES_HOLDER = RealWeb3.to_checksum_address("0x" + "10" * 20)
FABLES_HOLDER_2 = RealWeb3.to_checksum_address("0x" + "20" * 20)
FABLES_IMPL = RealWeb3.to_checksum_address("0x" + "77" * 20)

# A genuinely different event shape from _replay_role_holders()'s own
# RoleGranted/RoleRevoked(bytes32,address,address) -- independently
# recomputed, never copy-pasted.
FABLES_GRANT_TOPIC = "0x" + RealWeb3.keccak(text="RoleGranted(uint64,address,uint32,uint48,bool)").hex()
FABLES_REVOKE_TOPIC = "0x" + RealWeb3.keccak(text="RoleRevoked(uint64,address)").hex()


class TestScoreFablesPoolRegistry(unittest.TestCase):
    def test_single_admin_holder_happy_path_eip7702_delegated(self):
        fake = FakeHelpers()
        fake.call_raw_results[(FABLES_REGISTRY, "authority", ())] = FABLES_MANAGER
        _patch_helpers(self, fake)

        responses = {
            (FABLES_MANAGER, 0, "latest", FABLES_GRANT_TOPIC): [_role_log(500, 0, b"\x00" * 32, FABLES_HOLDER)],
        }
        code_7702 = b"\xef\x01\x00" + bytes.fromhex(FABLES_IMPL[2:])
        w3 = FakeW3(
            get_logs_fn=_canned_get_logs(responses),
            code_sizes={FABLES_HOLDER: code_7702},
            tx_counts={FABLES_HOLDER: 470},
        )

        result = scorers.score_fables_pool_registry(w3)
        self.assertEqual((result["adminKeyScore"], result["multisigScore"], result["timelockScore"]), (5, 0, 0))
        self.assertEqual(result["compositeScore"], scorers._composite(5, 0, 0))
        self.assertTrue(any("EIP-7702 delegated code = True" in n for n in result["notes"]))

    def test_zero_admin_holders_does_not_raise_unlike_rollup_scorer(self):
        # Explicitly the OPPOSITE behavior of score_rollup_l1_authority's
        # EXECUTOR_ROLE-empty guard: this function has no such raise.
        fake = FakeHelpers()
        fake.call_raw_results[(FABLES_REGISTRY, "authority", ())] = FABLES_MANAGER
        _patch_helpers(self, fake)
        w3 = FakeW3(get_logs_fn=_canned_get_logs({}))  # no GRANT/REVOKE logs at all -> zero holders

        result = scorers.score_fables_pool_registry(w3)  # must NOT raise
        self.assertEqual((result["adminKeyScore"], result["multisigScore"], result["timelockScore"]), (5, 0, 0))

    def test_multiple_admin_holders_warns_but_does_not_crash(self):
        fake = FakeHelpers()
        fake.call_raw_results[(FABLES_REGISTRY, "authority", ())] = FABLES_MANAGER
        _patch_helpers(self, fake)
        responses = {
            (FABLES_MANAGER, 0, "latest", FABLES_GRANT_TOPIC): [
                _role_log(500, 0, b"\x00" * 32, FABLES_HOLDER),
                _role_log(501, 0, b"\x00" * 32, FABLES_HOLDER_2),
            ],
        }
        w3 = FakeW3(get_logs_fn=_canned_get_logs(responses))

        result = scorers.score_fables_pool_registry(w3)
        self.assertTrue(any("WARNING: 2 ADMIN_ROLE holders found" in n for n in result["notes"]))
        self.assertEqual((result["adminKeyScore"], result["multisigScore"], result["timelockScore"]), (5, 0, 0))


if __name__ == "__main__":
    unittest.main()
