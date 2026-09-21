"""
Unit tests for the 2026-09-18 additions to `chains/tempo/scripts/
methodology_test.py` that close METHODOLOGY.md section 8's open point 1
("R2 has no hop for four controller types") and open point 3 (a real
`TypeError` in `classify()`'s internal weakest-controller selection when a
controller is unresolved).

Two kinds of coverage:
  1. Pure-function tests for `_mcms_flatten_quorum` (Chainlink
     ManyChainMultiSig's hierarchical group-quorum tree, no network) and
     `_weakest_sort_key`/`weakest()` (the bug fix) -- no mocking needed.
  2. `classify()` end-to-end tests with `methodology_test.rpc` monkeypatched
     to a small fake JSON-RPC dispatcher (keyed by method, and for
     `eth_call` by (to, 4-byte selector)) -- covers the ordering between
     the 4 new branches and the existing ones (a TimelockController's
     PROPOSER role resolving to an MCMS; an MCMS's own `owner()` NOT being
     chased into a circular reference; a plain AccessControlEnumerable
     contract; the LayerZero endpoint delegate folded into the generic
     contract branch). Real, live-confirmed data shapes (cbBTC's RBACTimelock
     and its 3 MCMS instances, Cap's cUSD TimelockController, the Bridge
     issuance controller) are used as regression fixtures where practical,
     not arbitrary numbers.
"""
import importlib.util
import os
import sys
import unittest

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


mt = _load_module("aro_test_tempo_methodology_test", "chains/tempo/scripts/methodology_test.py")


# --------------------------------------------------------------------- helpers
def addr(n):
    """A deterministic, valid-looking checksum address from a small int, for
    fixtures that don't need to be real on-chain addresses."""
    return to_checksum_address("0x" + format(n, "040x"))


def selector(sig):
    return "0x" + keccak(text=sig)[:4].hex()


class FakeRpc:
    """Replaces `methodology_test.rpc`. `calls[(to.lower(), 4byte_selector)]`
    maps to a raw 0x-prefixed hex return value; `code[addr.lower()]` maps to
    an `eth_getCode` result; `storage[(addr.lower(), slot)]` to an
    `eth_getStorageAt` result; `logs[addr.lower()]` to an `eth_getLogs`
    result list. Anything not registered returns None/empty, matching a
    real node's behaviour for an unimplemented selector (this project's own
    `call()` already treats `None`/`"0x"` as "no answer", not a crash)."""

    def __init__(self):
        self.calls = {}
        self.code = {}
        self.storage = {}
        self.logs = {}
        self.block_number = "0x100000"

    def set_call(self, to, sig, ret_hex):
        self.calls[(to.lower(), selector(sig))] = ret_hex

    def __call__(self, url, method, params):
        if method == "eth_chainId":
            return "0x1079"
        if method == "eth_blockNumber":
            return self.block_number
        if method == "eth_getCode":
            return self.code.get(params[0].lower(), "0x")
        if method == "eth_getStorageAt":
            return self.storage.get((params[0].lower(), params[1]), "0x" + "00" * 32)
        if method == "eth_getLogs":
            return self.logs.get(params[0]["address"].lower(), [])
        if method == "eth_call":
            to = params[0]["to"].lower()
            data = params[0]["data"]
            sel = data[:10]
            return self.calls.get((to, sel))
        raise AssertionError(f"unexpected RPC method in test: {method}")


def _patch_rpc(test_case, fake):
    orig = mt.rpc
    mt.rpc = fake
    test_case.addCleanup(lambda: setattr(mt, "rpc", orig))


# --------------------------------------------------------------- pure functions
class TestMcmsFlattenQuorum(unittest.TestCase):
    def test_flat_2_of_3(self):
        # A trivial single-group MCMS: 3 signers all in group 0, quorum 2.
        signers = [(addr(1), 0, 0), (addr(2), 1, 0), (addr(3), 2, 0)]
        quorums = [2] + [0] * 31
        parents = [0] * 32
        self.assertEqual(mt._mcms_flatten_quorum(signers, quorums, parents), 2)

    def test_nested_groups_cheapest_children_win(self):
        # Root (group 0) needs 1-of-2 children: group 1 (2-of-2 signers,
        # cost 2) and group 2 (a bare signer, cost 1). Cheapest is group 2.
        signers = [(addr(1), 0, 1), (addr(2), 1, 1), (addr(3), 2, 2)]
        quorums = [1, 2, 1] + [0] * 29
        parents = [0, 0, 0] + [0] * 29
        self.assertEqual(mt._mcms_flatten_quorum(signers, quorums, parents), 1)

    def test_disabled_group_contributes_nothing(self):
        # Group 1 has quorum 0 (disabled) -- its signer must not count
        # toward group 0, even though the signer array lists it.
        signers = [(addr(1), 0, 0), (addr(2), 1, 1)]
        quorums = [1, 0] + [0] * 30  # group 1 disabled
        parents = [0, 0] + [0] * 30
        self.assertEqual(mt._mcms_flatten_quorum(signers, quorums, parents), 1)

    def test_unsatisfiable_root_returns_none(self):
        # Root demands quorum 5 but only has 2 children available.
        signers = [(addr(1), 0, 0), (addr(2), 1, 0)]
        quorums = [5] + [0] * 31
        parents = [0] * 32
        self.assertIsNone(mt._mcms_flatten_quorum(signers, quorums, parents))

    def test_regression_cbbtc_proposer_mcms_shape(self):
        # The real, live-confirmed 2026-09-18 shape of cbBTC/PRIME's
        # proposer MCMS (0xD3F3...C18): 42 signers split into 4 top-level
        # groups of (17, 18, 7, ... wait -- real shape is 2-of-3 GROUPS at
        # the root, each of which is itself a 2-of-N leaf) -- reproduced
        # here structurally (not the real 42 addresses, which don't matter
        # to the algorithm) as a regression pin: 3 leaf groups directly
        # under root, quorum 2-of-3 leaves needed, each leaf itself 2-of-N.
        # Confirmed independently 2026-09-18 (own from-scratch decode of
        # live getConfig() data, cross-checked against a separate research
        # agent's own independent decode and against scouted_targets_2026-
        # 09-17-run2.md's own hand-derived number) that the REAL on-chain
        # config flattens to exactly 4-of-42 -- this fixture reproduces
        # that same shape at small scale (2-of-3 leaf-groups, one of which
        # needs 2, giving overall cost 2+2=4 is NOT what happens: the root
        # itself needs 2-of-3 leaf groups to succeed, and the two CHEAPEST
        # leaf groups sum their own costs) to pin the algorithm's behavior
        # on a hierarchy at least 2 levels deep with 3 siblings, not just
        # the 2-sibling cases above.
        leaf_a = [(addr(i), i, 1) for i in range(17)]   # group 1: 17 signers, quorum 2
        leaf_b = [(addr(20 + i), i, 2) for i in range(18)]  # group 2: 18 signers, quorum 2
        leaf_c = [(addr(50 + i), i, 3) for i in range(7)]   # group 3: 7 signers, quorum 2
        signers = leaf_a + leaf_b + leaf_c
        quorums = [0] * 32
        quorums[0] = 2  # root: 2-of-3 groups
        quorums[1] = quorums[2] = quorums[3] = 2  # each leaf: 2-of-N
        parents = [0] * 32  # groups 1,2,3 all parented to root (0)
        k = mt._mcms_flatten_quorum(signers, quorums, parents)
        # Root needs the 2 CHEAPEST of its 3 children (each child group
        # costs exactly 2, since each leaf's own quorum is 2): 2 + 2 = 4.
        self.assertEqual(k, 4)
        self.assertEqual(len(signers), 42)


class TestWeakestSortKeyBugfix(unittest.TestCase):
    def test_does_not_crash_on_unresolved_entry(self):
        # This is the exact scenario scouted_targets_2026-09-17-run2.md
        # section 8's open point 3 describes: a list of resolved
        # controllers where one is unresolved (k=None) used to raise
        # TypeError comparing None to an int.
        entries = [
            {"k": 3, "n": 5, "kind": "Safe"},
            {"k": None, "n": None, "kind": "unresolved contract"},
            {"k": 1, "n": 1, "kind": "EOA"},
        ]
        result = min(entries, key=mt._weakest_sort_key)
        self.assertEqual(result["kind"], "unresolved contract")  # weakest of all, per R3

    def test_weakest_public_function_matches(self):
        entries = [
            {"k": 5, "n": 7, "kind": "Safe"},
            {"k": None, "n": None, "kind": "unresolved contract"},
        ]
        self.assertEqual(mt.weakest(entries)["kind"], "unresolved contract")

    def test_lower_k_is_weaker_on_resolved_entries(self):
        entries = [{"k": 5, "n": 5}, {"k": 2, "n": 10}]
        self.assertEqual(mt.weakest(entries)["k"], 2)

    def test_equal_k_larger_n_is_weaker(self):
        entries = [{"k": 3, "n": 5}, {"k": 3, "n": 20}]
        self.assertEqual(mt.weakest(entries)["n"], 20)


# --------------------------------------------------------------- classify() flows
class TestClassifyTimelockController(unittest.TestCase):
    def test_stock_oz_timelock_no_bypasser_resolves_proposer_via_safe(self):
        """Cap's cUSD TimelockController shape: getMinDelay + PROPOSER_ROLE
        succeed, BYPASSER_ROLE reverts (stock OZ, not RBACTimelock), no
        AccessControlEnumerable getters -- so PROPOSER_ROLE holders must be
        found via the RoleGranted log-scan fallback, not enumeration."""
        fake = FakeRpc()
        tl = addr(0xA1)
        safe = addr(0xB1)
        proposer_hash = mt.TIMELOCK_ROLES["PROPOSER_ROLE"]

        fake.code[tl.lower()] = "0x600160005260206000f3"  # any non-"0x", non-7702 code
        fake.code[safe.lower()] = "0x600160005260206000f3"
        fake.set_call(tl, "getMinDelay()", "0x" + encode(["uint256"], [86400]).hex())
        fake.set_call(tl, "PROPOSER_ROLE()", "0x" + encode(["bytes32"], [bytes.fromhex(proposer_hash[2:])]).hex())
        fake.set_call(tl, "BYPASSER_ROLE()", None)  # reverts on a stock TimelockController
        fake.set_call(tl, "getRoleMemberCount(bytes32)", None)  # not enumerable
        # RoleGranted log for PROPOSER_ROLE naming `safe` as the account
        role_topic = "0x" + keccak(text="RoleGranted(bytes32,address,address)").hex()
        fake.logs[tl.lower()] = [{
            "topics": [role_topic, "0x" + proposer_hash[2:], "0x" + ("00" * 12) + safe[2:].lower()],
        }]
        fake.set_call(tl, "hasRole(bytes32,address)", "0x" + encode(["bool"], [True]).hex())
        # `safe` resolves as a Safe (3-of-5)
        fake.set_call(safe, "getThreshold()", "0x" + encode(["uint256"], [3]).hex())
        fake.set_call(safe, "getOwners()", "0x" + encode(["address[]"], [[addr(i) for i in range(1, 6)]]).hex())
        fake.set_call(safe, "getModulesPaginated(address,uint256)", "0x" + encode(["address[]", "address"], [[], mt.SAFE_SENTINEL]).hex())
        fake.set_call(safe, "VERSION()", "0x" + encode(["string"], ["1.4.1"]).hex())
        fake.set_call(safe, "nonce()", "0x" + encode(["uint256"], [1]).hex())
        fake.storage[(safe.lower(), "0x0")] = "0x" + "00" * 31 + "01"  # nonzero -> resolvable

        _patch_rpc(self, fake)
        # LayerZero delegate check inside classify()'s Safe branch isn't
        # reached (Safe resolves before the generic contract branch), so no
        # extra stub needed there.
        result = mt.classify(tl)
        self.assertEqual(result["kind"], "TimelockController")
        self.assertEqual(result["getMinDelaySeconds"], 86400)
        self.assertFalse(result["hasBypasser"])
        self.assertEqual(result["k"], 3)
        self.assertEqual(result["n"], 5)
        self.assertEqual(result["minDelaySeconds"], 86400)  # only path is PROPOSER, real delay applies

    def test_bypasser_path_drags_delay_to_zero(self):
        """RBACTimelock shape: BYPASSER_ROLE exists and resolves to a
        weaker/zero-delay path -- minDelaySeconds must reflect the
        SHORTEST path (0), independent of which path is k/n-weakest."""
        fake = FakeRpc()
        tl = addr(0xA2)
        proposer_mcms = addr(0xC1)
        bypasser_mcms = addr(0xC2)
        proposer_hash = mt.TIMELOCK_ROLES["PROPOSER_ROLE"]
        bypasser_hash = mt.TIMELOCK_ROLES["BYPASSER_ROLE"]

        fake.code[tl.lower()] = "0x60016000"
        fake.code[proposer_mcms.lower()] = "0x60016000"
        fake.code[bypasser_mcms.lower()] = "0x60016000"
        fake.set_call(tl, "getMinDelay()", "0x" + encode(["uint256"], [10800]).hex())
        fake.set_call(tl, "PROPOSER_ROLE()", "0x" + encode(["bytes32"], [bytes.fromhex(proposer_hash[2:])]).hex())
        fake.set_call(tl, "BYPASSER_ROLE()", "0x" + encode(["bytes32"], [bytes.fromhex(bypasser_hash[2:])]).hex())
        # RBACTimelock IS AccessControlEnumerable -- both roles enumerable
        fake.set_call(tl, "getRoleMemberCount(bytes32)", None)  # handled per-role below via a dynamic stub
        fake.calls[(tl.lower(), selector("getRoleMemberCount(bytes32)"))] = None

        def dynamic_call(url, method, params):
            if method == "eth_call":
                to = params[0]["to"].lower()
                data = params[0]["data"]
                sel = data[:10]
                if to == tl.lower() and sel == selector("getRoleMemberCount(bytes32)"):
                    role_arg = data[10:]
                    if role_arg == proposer_hash[2:]:
                        return "0x" + encode(["uint256"], [1]).hex()
                    if role_arg == bypasser_hash[2:]:
                        return "0x" + encode(["uint256"], [1]).hex()
                    return "0x" + encode(["uint256"], [0]).hex()
                if to == tl.lower() and sel == selector("getRoleMember(bytes32,uint256)"):
                    role_arg = data[10:74]
                    if role_arg == proposer_hash[2:]:
                        return "0x" + encode(["address"], [proposer_mcms]).hex()
                    if role_arg == bypasser_hash[2:]:
                        return "0x" + encode(["address"], [bypasser_mcms]).hex()
            return fake_orig_call(url, method, params)

        fake_orig_call = fake.__call__
        _patch_rpc(self, dynamic_call)

        # Both MCMS: simple flat multisigs via getConfig()
        mcms_abi = mt.MCMS_CONFIG_ABI

        def config_for(k, n):
            signers = [(addr(i), i, 0) for i in range(n)]
            quorums = [k] + [0] * 31
            parents = [0] * 32
            return "0x" + encode([mcms_abi], [(signers, quorums, parents)]).hex()

        fake.set_call(proposer_mcms, "getConfig()", config_for(4, 8))
        fake.set_call(bypasser_mcms, "getConfig()", config_for(2, 8))
        # getConfig() must also NOT be misread as a TimelockController or
        # AccessControlEnumerable -- ensure those probes return None for MCMS
        fake.set_call(proposer_mcms, "getMinDelay()", None)
        fake.set_call(bypasser_mcms, "getMinDelay()", None)

        result = mt.classify(tl)
        self.assertEqual(result["kind"], "TimelockController")
        self.assertTrue(result["hasBypasser"])
        self.assertEqual(result["minDelaySeconds"], 0)  # bypasser path wins the min(), even though...
        self.assertEqual(result["k"], 2)  # ...bypasser (2-of-8) is also k/n-weaker than proposer (4-of-8) here

    def test_self_administered_admin_role_does_not_poison_the_result(self):
        """Regression test for a REAL bug caught live against Tempo mainnet
        (2026-09-18, self-caught before commit, not by review): the first
        version of the ADMIN_ROLE fix above recursed classify() on ADMIN_
        ROLE's holder unconditionally. Both real targets (Cap's Timelock
        and CCIP's RBACTimelock) self-administer -- ADMIN_ROLE/DEFAULT_
        ADMIN_ROLE is held by the timelock's OWN address -- so that
        recursion re-entered `_classify_timelock` on the SAME address,
        which re-derived the SAME self-held admin role again, forever,
        until the depth>3 cutoff returned "unresolved" (k=None) -- which
        `_weakest_sort_key` then treats as the weakest possible entry,
        wrongly dragging the WHOLE result to k=None/n=None even though
        PROPOSER_ROLE resolved perfectly well to a real 3-of-5 Safe. Fixed
        by filtering out any role holder equal to the contract's own
        address before recursing (self-administration contributes nothing
        new: reaching a self-held role still requires going through
        PROPOSER or BYPASSER first, both already tracked separately)."""
        fake = FakeRpc()
        tl = addr(0xA4)
        safe = addr(0xB4)
        proposer_hash = mt.TIMELOCK_ROLES["PROPOSER_ROLE"]

        fake.code[tl.lower()] = "0x60016000"
        fake.code[safe.lower()] = "0x60016000"
        fake.set_call(tl, "getMinDelay()", "0x" + encode(["uint256"], [86400]).hex())
        fake.set_call(tl, "PROPOSER_ROLE()", "0x" + encode(["bytes32"], [bytes.fromhex(proposer_hash[2:])]).hex())
        fake.set_call(tl, "BYPASSER_ROLE()", None)  # plain TimelockController, no bypasser
        fake.set_call(safe, "getMinDelay()", None)
        fake.set_call(safe, "PROPOSER_ROLE()", None)

        def dynamic_call(url, method, params):
            if method == "eth_call":
                to = params[0]["to"].lower()
                data = params[0]["data"]
                sel = data[:10]
                if to == tl.lower() and sel == selector("getRoleMemberCount(bytes32)"):
                    role_arg = data[10:]
                    if role_arg == proposer_hash[2:]:
                        return "0x" + encode(["uint256"], [1]).hex()
                    if role_arg == mt.DEFAULT_ADMIN_ROLE[2:]:
                        return "0x" + encode(["uint256"], [1]).hex()  # self-administered: 1 holder
                    return "0x" + encode(["uint256"], [0]).hex()
                if to == tl.lower() and sel == selector("getRoleMember(bytes32,uint256)"):
                    role_arg = data[10:74]
                    if role_arg == proposer_hash[2:]:
                        return "0x" + encode(["address"], [safe]).hex()
                    if role_arg == mt.DEFAULT_ADMIN_ROLE[2:]:
                        return "0x" + encode(["address"], [tl]).hex()  # SELF -- the bug scenario
                if to == safe.lower() and sel == selector("getThreshold()"):
                    return "0x" + encode(["uint256"], [3]).hex()
                if to == safe.lower() and sel == selector("getOwners()"):
                    return "0x" + encode(["address[]"], [[addr(0x20 + i) for i in range(5)]]).hex()
                if to == safe.lower() and sel == selector("getModulesPaginated(address,uint256)"):
                    return "0x" + encode(["address[]", "address"], [[], mt.SAFE_SENTINEL]).hex()
                if to == safe.lower() and sel == selector("VERSION()"):
                    return "0x" + encode(["string"], ["1.4.1"]).hex()
                if to == safe.lower() and sel == selector("nonce()"):
                    return "0x" + encode(["uint256"], [1]).hex()
            return fake_orig_call(url, method, params)

        fake_orig_call = fake.__call__
        fake.storage[(safe.lower(), "0x0")] = "0x" + "00" * 31 + "01"
        _patch_rpc(self, dynamic_call)

        result = mt.classify(tl)
        self.assertEqual(result["kind"], "TimelockController")
        self.assertIsNotNone(result["k"])  # the bug produced None here
        self.assertEqual(result["k"], 3)
        self.assertEqual(result["n"], 5)
        self.assertEqual(result["minDelaySeconds"], 86400)
        # confirm the self-administered path was excluded, not silently dropped for a wrong reason
        via_labels = {c["via"] for c in result["controllers"]}
        self.assertEqual(via_labels, {"PROPOSER_ROLE"})


class TestClassifyAccessControlEnumerable(unittest.TestCase):
    def test_default_admin_role_holder_resolved(self):
        """The Bridge issuance controller shape (pathUSD/USDB/DLUSD): no
        getMinDelay/PROPOSER_ROLE, but DEFAULT_ADMIN_ROLE is enumerable."""
        fake = FakeRpc()
        ctrl = addr(0xD1)
        holder_eoa = addr(0xE1)
        fake.code[ctrl.lower()] = "0x60016000"
        fake.set_call(ctrl, "getMinDelay()", None)
        fake.set_call(ctrl, "getConfig()", None)
        fake.set_call(ctrl, "getRoleMemberCount(bytes32)", "0x" + encode(["uint256"], [1]).hex())
        fake.set_call(ctrl, "getRoleMember(bytes32,uint256)", "0x" + encode(["address"], [holder_eoa]).hex())
        fake.code[holder_eoa.lower()] = "0x"  # a plain EOA
        _patch_rpc(self, fake)
        result = mt.classify(ctrl)
        self.assertEqual(result["kind"], "AccessControlEnumerable")
        self.assertEqual(result["k"], 1)
        self.assertEqual(result["n"], 1)
        self.assertEqual(result["signers"], [holder_eoa])
        self.assertEqual(result["minDelaySeconds"], 0)


class TestClassifyLayerZeroDelegate(unittest.TestCase):
    def test_delegate_folded_in_as_parallel_controller(self):
        """A generic contract (owner()-based) that is ALSO a registered
        LayerZero OApp: the delegate must be added as a third parallel
        controller candidate, and if it is weaker than owner(), it must
        win the overall weakest-key AND drag minDelaySeconds down."""
        fake = FakeRpc()
        oft = addr(0xF1)
        timelock_owner = addr(0xA3)  # a strong, delayed owner() path
        delegate_eoa = addr(0xE2)    # a bare EOA delegate -- weak, zero-delay

        fake.code[oft.lower()] = "0x60016000"
        fake.set_call(oft, "getThreshold()", None)
        fake.set_call(oft, "threshold()", None)
        fake.set_call(oft, "getMinDelay()", None)
        fake.set_call(oft, "getConfig()", None)
        fake.set_call(oft, "getRoleMemberCount(bytes32)", None)
        fake.set_call(oft, "owner()", "0x" + encode(["address"], [timelock_owner]).hex())
        fake.storage[(oft.lower(), mt.EIP1967_ADMIN)] = "0x" + "00" * 32
        # timelock_owner resolves as a strong 5-of-9-ish contract -- keep it
        # simple: make it a Safe with a strong threshold.
        fake.code[timelock_owner.lower()] = "0x60016000"
        fake.set_call(timelock_owner, "getThreshold()", "0x" + encode(["uint256"], [5]).hex())
        fake.set_call(timelock_owner, "getOwners()", "0x" + encode(["address[]"], [[addr(0x10 + i) for i in range(9)]]).hex())
        fake.set_call(timelock_owner, "getModulesPaginated(address,uint256)", "0x" + encode(["address[]", "address"], [[], mt.SAFE_SENTINEL]).hex())
        fake.set_call(timelock_owner, "VERSION()", "0x" + encode(["string"], ["1.4.1"]).hex())
        fake.set_call(timelock_owner, "nonce()", "0x" + encode(["uint256"], [1]).hex())
        fake.storage[(timelock_owner.lower(), "0x0")] = "0x" + "00" * 31 + "01"
        # delegate: bare EOA
        fake.code[delegate_eoa.lower()] = "0x"
        fake.set_call(mt.LZ_ENDPOINT_V2, "delegates(address)", "0x" + encode(["address"], [delegate_eoa]).hex())

        _patch_rpc(self, fake)
        result = mt.classify(oft)
        self.assertEqual(result["kind"], "contract")
        kinds_via = {c["via"]: c["kind"] for c in result["controllers"]}
        self.assertIn("LayerZero EndpointV2 delegate", kinds_via)
        self.assertEqual(kinds_via["LayerZero EndpointV2 delegate"], "EOA")
        # the bare EOA delegate (k=1,n=1) must win over the 5-of-9 owner path
        self.assertEqual(result["k"], 1)
        self.assertEqual(result["n"], 1)


if __name__ == "__main__":
    unittest.main()
