"""
Unit tests for stHYPE liquid staking (`chains/hyperliquid/scripts/methodology_test.py::
score_sthype_liquid_staking`, added 2026-09-25) -- the FOURTH HyperEVM-native Hyperliquid
target this project scores, and for the new shared helper it introduced (`_has_role`, a
plain OpenZeppelin `AccessControl` `hasRole(bytes32,address)` check -- stHYPE has neither
Kinetiq's `AccessControlEnumerable` shape nor para's/Ventuals' `RoleRegistry.roleHolders`
shape, both confirmed live to revert against it).

The main thing these tests lock in: today's independent research proposed
adminKeyScore=65/multisigScore=78/compositeScore=49 for this target's 4-of-6 root Safe,
read off METHODOLOGY.md 4.6's HyperCore-multisig example table (`key_score(4, 6)`) -- the
wrong ladder for a REAL on-chain Gnosis Safe. `score_sthype_liquid_staking` instead routes
through `_classify_authority_holder` (the same function Kinetiq's/para's/Ventuals' own
Safe-shaped role holders already use), giving multisigScore=70, compositeScore=47 --
verified here against a frozen fixture, not just asserted in prose.

`evm()`/`_eth_call()` are monkeypatched with real responses fetched live from
`https://rpc.hyperliquid.xyz/evm` on 2026-09-25 (the 6-owner Safe and the Overseer V1 ->
Safe `owner()` chain), frozen so this suite doesn't depend on network access or mutable
on-chain state -- same discipline `test_kinetiq_hyperevm.py`/
`test_para_staking_vault_hyperevm.py`/`test_ventuals_vhype_staking_hyperevm.py` already
established for this ecosystem.
"""
import importlib.util
import os
import sys
import unittest

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


mt = _load_module("aro_test_hyperliquid_methodology_test_sthype", "chains/hyperliquid/scripts/methodology_test.py")

PROXY = "0xffaa4a3d97fe9107cef8a3f48c069f577ff76cc1"
WSTHYPE_WRAPPER = "0x94e8396e0869c9f2200760af0621afd240e1cf38"  # NOT the target -- see module docstring
SAFE = "0x97dee0ea4ca10560f260a0f6f45bdc128a1d51f9"
OVERSEER_V1 = "0xb96f07367e69e86d6e9c3f29215885104813eeae"
SAFE_OWNERS = [
    "0x4f1badad95b7a5901b6927d6c4a6761b3e8a00b4",
    "0xd78a2374d5459ed44087fcfe5a40105b03cd9d71",
    "0x5cd0448cc4aae28e46babdb285b9e3b601872378",
    "0x10f6160f0033700cb55c478826068dad4d210465",
    "0x785c7df2717c119929bc5a3d6c52638d2918ac2c",
    "0x4993522ee8091cc7a452af7a98d5ef4a269f6fc5",
]
# A different, unrelated 2-of-3 Safe, used only by the "overseer resolves elsewhere" test.
OTHER_SAFE = "0x5a24d40ef0b6856aefeefe65c332ce7cc7d9ba04"
OTHER_SAFE_OWNERS = [
    "0x4661580641ccb1d6d0b07c34a97553e9b319ceba",
    "0xf5df74aaad29a3e0e2e1d5683fd11b551cc97d31",
    "0x8d23a255656f4c8e26d1010e0aa2b6d20885ca91",
]


def _encode_addr_array(addrs):
    """Real (address[]) ABI encoding: offset word, length word, one right-padded 32-byte
    word per address -- the same shape `read_safe_hyperevm` and every existing Hyperliquid
    HyperEVM test fixture in this suite already assume."""
    body = "".join("0" * 24 + a[2:].lower() for a in addrs)
    return "0x" + ("%064x" % 0x20) + ("%064x" % len(addrs)) + body


GUARD_RESPONSE = "0x" + "0" * 64
MODULES_RESPONSE = "0x" + ("%064x" % 0x40) + ("0" * 64) + ("0" * 64)
DEFAULT_ADMIN_ROLE_HASH = "0x" + "0" * 64
REBASER_ROLE_MARKER = "0x" + "cc" * 32  # not the real 32-byte hash -- only used as a call-matching marker here


class TestHasRole(unittest.TestCase):
    """Unit tests for the new shared helper stHYPE needed: no enumerable role interface
    exists on this contract, so `hasRole(bytes32,address)` is the only live way to confirm
    a candidate holder."""

    def test_true_when_contract_reports_the_role_held(self):
        orig = mt._eth_call
        try:
            mt._eth_call = lambda to, data: "0x" + "0" * 63 + "1"
            self.assertTrue(mt._has_role(PROXY, DEFAULT_ADMIN_ROLE_HASH, SAFE))
        finally:
            mt._eth_call = orig

    def test_false_when_contract_reports_the_role_not_held(self):
        orig = mt._eth_call
        try:
            mt._eth_call = lambda to, data: "0x" + "0" * 64
            self.assertFalse(mt._has_role(PROXY, DEFAULT_ADMIN_ROLE_HASH, SAFE))
        finally:
            mt._eth_call = orig

    def test_encodes_role_and_account_into_the_calldata(self):
        seen = {}

        def fake_eth_call(to, data):
            seen["data"] = data
            return "0x" + "0" * 63 + "1"
        orig = mt._eth_call
        try:
            mt._eth_call = fake_eth_call
            mt._has_role(PROXY, REBASER_ROLE_MARKER, OVERSEER_V1)
        finally:
            mt._eth_call = orig
        self.assertTrue(seen["data"].startswith(mt._selector("hasRole(bytes32,address)")))
        self.assertIn(REBASER_ROLE_MARKER[2:], seen["data"])
        self.assertIn(OVERSEER_V1[2:], seen["data"])


def _full_fake_evm(default_admin=SAFE, default_admin_owners=SAFE_OWNERS, default_admin_threshold=4,
                    overseer_owner=SAFE, overseer_owner_owners=SAFE_OWNERS, overseer_owner_threshold=4,
                    default_admin_has_role=True, rebaser_has_role=True):
    """A complete, end-to-end fake for score_sthype_liquid_staking()'s every eth_call/
    eth_getCode/eth_getStorageAt, built from real selectors (mt._selector), matching
    test_ventuals_vhype_staking_hyperevm.py's own `_full_fake_evm` convention."""
    real_default_admin = mt._selector("defaultAdmin()")
    real_rebaser_role = mt._selector("REBASER_ROLE()")
    real_has_role = mt._selector("hasRole(bytes32,address)")
    real_owner = mt._selector("owner()")
    real_get_owners = mt._selector("getOwners()")
    real_get_threshold = mt._selector("getThreshold()")
    real_get_modules = mt._selector("getModulesPaginated(address,uint256)")

    def fake_evm(method, params):
        if method == "eth_getCode":
            return "0x6080604052"  # every address here has code (a Safe or a controller contract)
        if method == "eth_getStorageAt":
            return GUARD_RESPONSE
        if method == "eth_call":
            data = params[0]["data"]
            to = params[0]["to"].lower()
            if data.startswith(real_default_admin):
                return "0x" + "0" * 24 + default_admin[2:].lower()
            if data.startswith(real_rebaser_role):
                return REBASER_ROLE_MARKER
            if data.startswith(real_has_role):
                role = data[len(real_has_role):len(real_has_role) + 64]
                account = data[len(real_has_role) + 64:len(real_has_role) + 128][-40:]
                if role == DEFAULT_ADMIN_ROLE_HASH[2:].rjust(64, "0"):
                    ok = default_admin_has_role and account.lower() == default_admin[2:].lower()
                elif role == REBASER_ROLE_MARKER[2:].rjust(64, "0"):
                    ok = rebaser_has_role and account.lower() == OVERSEER_V1[2:].lower()
                else:
                    raise AssertionError(f"unexpected hasRole role: {role}")
                return "0x" + "0" * 63 + ("1" if ok else "0")
            if data.startswith(real_owner) and to == OVERSEER_V1.lower():
                return "0x" + "0" * 24 + overseer_owner[2:].lower()
            if data.startswith(real_get_owners):
                owners = default_admin_owners if to == default_admin.lower() else overseer_owner_owners
                return _encode_addr_array(owners)
            if data.startswith(real_get_threshold):
                threshold = default_admin_threshold if to == default_admin.lower() else overseer_owner_threshold
                return "0x" + "0" * 63 + ("%x" % threshold)
            if data.startswith(real_get_modules):
                return MODULES_RESPONSE
            raise AssertionError(f"unexpected eth_call data: {data}")
        raise AssertionError(f"unexpected method: {method}")

    return fake_evm


class TestScoreSthypeLiquidStakingEndToEnd(unittest.TestCase):
    def _run(self, **kwargs):
        orig_evm = mt.evm
        mt.evm = _full_fake_evm(**kwargs)
        try:
            return mt.score_sthype_liquid_staking()
        finally:
            mt.evm = orig_evm

    def test_target_is_sthype_not_the_wstype_wrapper(self):
        r = self._run()
        self.assertEqual(r["target"], PROXY)
        self.assertNotEqual(r["target"], WSTHYPE_WRAPPER)

    def test_corrected_scores_not_the_naive_key_score_ones(self):
        # (k=4, n=6) via _classify_authority_holder -> _safe_rooted_scores_hyperevm:
        # adminKeyScore=65 (agrees with the naive key_score(4,6) ladder at k>=3),
        # multisigScore=70 (NOT 78 -- that number is key_score(4,6), the wrong ladder for a
        # real Gnosis Safe), compositeScore=47 (NOT 49).
        r = self._run()
        self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["timelockScore"]), (65, 70, 0))
        self.assertEqual(r["compositeScore"], 47)
        self.assertNotEqual(r["multisigScore"], 78)
        self.assertNotEqual(r["compositeScore"], 49)
        self.assertEqual(mt.composite(65, 70, 0), 47)

    def test_reads_expose_default_admin_role_key_for_the_generic_cross_exposure_pass(self):
        # chains/hyperliquid/scorers.py::_apply_hyperevm_shared_root_exposure keys off a
        # "DEFAULT_ADMIN_ROLE:<address>" entry in reads.roleHolders -- without this exact
        # shape, this target would silently be excluded from that generic, every-run check
        # against Kinetiq's own root Safe.
        r = self._run()
        self.assertIn(f"DEFAULT_ADMIN_ROLE:{SAFE}", r["reads"]["roleHolders"])

    def test_stale_default_admin_role_raises_instead_of_trusting_defaultadmin_alone(self):
        with self.assertRaises(mt.HyperEvmReadError):
            self._run(default_admin_has_role=False)

    def test_stale_rebaser_role_raises_instead_of_trusting_a_stale_address(self):
        with self.assertRaises(mt.HyperEvmReadError):
            self._run(rebaser_has_role=False)

    def test_overseer_resolving_to_a_different_safe_is_scored_independently(self):
        # If Overseer V1's owner() ever pointed somewhere other than defaultAdmin()'s own
        # Safe, that path must be classified on its own merits (min-over-paths), not
        # silently assumed identical.
        r = self._run(overseer_owner=OTHER_SAFE, overseer_owner_owners=OTHER_SAFE_OWNERS, overseer_owner_threshold=1)
        rebaser_note = next(n for n in r["notes"] if n.startswith("REBASER_ROLE:"))
        self.assertIn("DIFFERENT from defaultAdmin()", rebaser_note)
        # OTHER_SAFE is 1-of-3 -> weaker than the 4-of-6 root -> becomes the binding minimum.
        self.assertEqual(r["adminKeyScore"], 10)
        self.assertEqual(r["multisigScore"], min(70, mt._safe_rooted_scores_hyperevm(1, 3)[1]))

    def test_oracle_authority_and_cross_exposure_left_at_the_not_applicable_default(self):
        r = self._run()
        self.assertEqual(r["oracleAuthorityScore"], 100)
        self.assertEqual(r["crossExposureScore"], 100)


if __name__ == "__main__":
    unittest.main()
