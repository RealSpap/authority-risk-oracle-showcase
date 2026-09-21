"""
Unit tests for `chains/tempo/scripts/methodology_test.py`'s three top-level
scorer functions (`score_chain_baseline`, `score_token`, `score_vault_v2`) --
found 2026-09-19 with zero test coverage while auditing this ecosystem's
scorers against the test corpus, even though `test_tempo_controller_types.py`
already establishes a full end-to-end `classify()`-mocking convention for
this ecosystem (unlike Hyperliquid/Zcash, where most of this project's
top-level scorers deliberately rely on live dry-runs instead -- Tempo's own
convention is different, so these ARE real gaps under it, not a case of
respecting an established "primitives only" choice).

`score_token()`'s own orchestration (collecting role-holder CANDIDATES from
`RoleMembershipUpdated` events, then confirming each one's CURRENT role via
a live `hasRole` call, then building the root-control set and taking the
policy-admin branch only when `transferPolicyId >= 2`) is a different layer
than `classify()`'s already-tested address-resolution logic -- this file
tests that orchestration layer, reusing `classify()`'s simplest branch (a
bare EOA, `code() == "0x"`, no further mocking needed) wherever the test's
own point isn't about classification itself.

`score_vault_v2()`'s tests reproduce the exact live-verified T1/T2/T3
shapes its own docstring already documents (`chains/tempo/scripts/
methodology_test.py::score_vault_v2`'s docstring) and assert against those
same published numbers -- a regression lock on real, previously-derived
data, not arbitrary fixture numbers.
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


mt = _load_module("aro_test_tempo_methodology_test_toplevel", "chains/tempo/scripts/methodology_test.py")


def addr(n):
    return to_checksum_address("0x" + format(n, "040x"))


def selector(sig):
    return "0x" + keccak(text=sig)[:4].hex()


class FakeRpc:
    """Same shape as test_tempo_controller_types.py's own FakeRpc -- kept
    as a separate, self-contained copy in this file rather than imported
    across test files, matching this project's existing convention of each
    test file owning its own fixtures."""

    def __init__(self):
        self.calls = {}
        self.dynamic = None  # optional callable(to, sig_selector, raw_arg_bytes) -> "0x..." or None
        self.code = {}
        self.storage = {}
        self.logs = {}

    def set_call(self, to, sig, ret_hex):
        self.calls[(to.lower(), selector(sig))] = ret_hex

    def __call__(self, url, method, params):
        if method == "eth_chainId":
            return "0x1079"
        if method == "eth_blockNumber":
            return "0x100000"
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
            if self.dynamic is not None:
                dyn = self.dynamic(to, sel, data[10:])
                if dyn is not None:
                    return dyn
            return self.calls.get((to, sel))
        raise AssertionError(f"unexpected RPC method in test: {method}")


def _patch_rpc(test_case, fake):
    orig = mt.rpc
    mt.rpc = fake
    test_case.addCleanup(lambda: setattr(mt, "rpc", orig))


def _mark_eoa(fake, address):
    fake.code[address.lower()] = "0x"


# --------------------------------------------------------------- score_chain_baseline
class TestScoreChainBaseline(unittest.TestCase):
    def test_owner_eoa_and_no_active_validators(self):
        fake = FakeRpc()
        owner = addr(0x1)
        _mark_eoa(fake, owner)
        fake.set_call(mt.VALIDATOR_CONFIG_V2, "owner()", "0x" + encode(["address"], [owner]).hex())
        fake.set_call(mt.VALIDATOR_CONFIG_V2, "getActiveValidators()",
                      "0x" + encode(["(bytes32,address,string,string,address,uint64,uint64,uint64)[]"], [[]]).hex())
        fake.code[mt.VALIDATOR_CONFIG_V2.lower()] = "0x600160005260206000f3"
        _patch_rpc(self, fake)

        result = mt.score_chain_baseline()
        self.assertEqual(result["address"], mt.VALIDATOR_CONFIG_V2)
        self.assertEqual(result["reads"]["activeValidatorEntries"], 0)
        self.assertEqual(result["weakestKey"], {"k": 1, "n": 1, "address": owner})
        self.assertEqual(result["adminKeyScore"], mt.admin_key_score({"k": 1, "n": 1, "address": owner}))
        self.assertEqual(result["multisigScore"], mt.multisig_score({"k": 1, "n": 1, "address": owner}))
        self.assertEqual(result["timelockScore"], 0)  # EOA carries no minDelaySeconds
        self.assertEqual(
            result["compositeScore"],
            mt.composite(result["adminKeyScore"], result["multisigScore"], result["timelockScore"]),
        )

    def test_reports_the_real_active_validator_count(self):
        fake = FakeRpc()
        owner = addr(0x1)
        _mark_eoa(fake, owner)
        fake.set_call(mt.VALIDATOR_CONFIG_V2, "owner()", "0x" + encode(["address"], [owner]).hex())
        validator_tuple = (b"\x00" * 32, addr(0x2), "validator-a", "https://example.test", addr(0x3), 1, 2, 3)
        fake.set_call(mt.VALIDATOR_CONFIG_V2, "getActiveValidators()",
                      "0x" + encode(["(bytes32,address,string,string,address,uint64,uint64,uint64)[]"], [[validator_tuple]]).hex())
        fake.code[mt.VALIDATOR_CONFIG_V2.lower()] = "0x600160005260206000f3"
        _patch_rpc(self, fake)

        result = mt.score_chain_baseline()
        self.assertEqual(result["reads"]["activeValidatorEntries"], 1)


# --------------------------------------------------------------- score_token
class TestScoreToken(unittest.TestCase):
    TOKEN = addr(0x10)

    def _wire_basic_token_fields(self, fake, paused=False, supply_cap=10**24, transfer_policy_id=1):
        fake.set_call(self.TOKEN, "name()", "0x" + encode(["string"], ["Test Token"]).hex())
        fake.set_call(self.TOKEN, "totalSupply()", "0x" + encode(["uint256"], [10**20]).hex())
        fake.set_call(self.TOKEN, "decimals()", "0x" + encode(["uint8"], [6]).hex())
        fake.set_call(self.TOKEN, "transferPolicyId()", "0x" + encode(["uint64"], [transfer_policy_id]).hex())
        fake.set_call(self.TOKEN, "paused()", "0x" + encode(["bool"], [paused]).hex())
        fake.set_call(self.TOKEN, "supplyCap()", "0x" + encode(["uint256"], [supply_cap]).hex())
        fake.code[self.TOKEN.lower()] = "0xef01"  # not the exact "0xef" precompile marker on purpose in most tests

    def _wire_has_role(self, fake, holders_by_role):
        """holders_by_role: {role_name: [account, ...]}. Answers hasRole(account, roleHash)
        for exactly the accounts/roles registered; anything else is False."""
        role_hash_by_name = mt.ROLES

        def dynamic(to, sel, raw_arg):
            if to != self.TOKEN.lower() or sel != selector("hasRole(address,bytes32)"):
                return None
            account = to_checksum_address("0x" + raw_arg[24:64])
            role_hash = "0x" + raw_arg[64:128]
            role_name = next((r for r, h in role_hash_by_name.items() if h.lower() == role_hash.lower()), None)
            held = role_name is not None and account in holders_by_role.get(role_name, [])
            return "0x" + encode(["bool"], [held]).hex()

        fake.dynamic = dynamic

    def test_no_role_membership_events_gives_an_empty_root_and_admin_key_100(self):
        fake = FakeRpc()
        self._wire_basic_token_fields(fake, transfer_policy_id=1)  # always-allow, no policy admin branch
        self._wire_has_role(fake, {})
        _patch_rpc(self, fake)

        result = mt.score_token("Test Token", self.TOKEN, None, events=[])
        self.assertEqual(result["rootControlSet"], [])
        self.assertIsNone(result["weakestKey"])
        self.assertEqual(result["adminKeyScore"], mt.admin_key_score(None))
        self.assertEqual(result["multisigScore"], mt.multisig_score(None))
        self.assertEqual(result["timelockScore"], 0)
        self.assertIsNone(result["reads"]["layerZeroInbound"])

    def test_single_default_admin_holder_becomes_the_root_control_set(self):
        fake = FakeRpc()
        holder = addr(0x20)
        _mark_eoa(fake, holder)
        self._wire_basic_token_fields(fake, transfer_policy_id=1)
        self._wire_has_role(fake, {"DEFAULT_ADMIN_ROLE": [holder]})
        _patch_rpc(self, fake)

        events = [{"event": "RoleMembershipUpdated", "account": holder}]
        result = mt.score_token("Test Token", self.TOKEN, None, events=events)
        self.assertEqual(len(result["rootControlSet"]), 1)
        self.assertEqual(result["rootControlSet"][0]["role"], "DEFAULT_ADMIN_ROLE")
        self.assertEqual(result["weakestKey"]["address"], holder)
        self.assertEqual(result["adminKeyScore"], mt.admin_key_score({"k": 1, "n": 1}))

    def test_candidate_no_longer_holding_any_role_is_excluded(self):
        # A real regression class: RoleMembershipUpdated only means the
        # account held (or was granted) a role AT SOME POINT -- score_token()
        # must re-confirm via a LIVE hasRole() call, not trust the log alone.
        fake = FakeRpc()
        former_holder = addr(0x21)
        _mark_eoa(fake, former_holder)
        self._wire_basic_token_fields(fake, transfer_policy_id=1)
        self._wire_has_role(fake, {})  # nobody currently holds anything
        _patch_rpc(self, fake)

        events = [{"event": "RoleMembershipUpdated", "account": former_holder}]
        result = mt.score_token("Test Token", self.TOKEN, None, events=events)
        self.assertEqual(result["rootControlSet"], [])
        self.assertIsNone(result["weakestKey"])

    def test_always_reject_policy_id_zero_has_no_policy_admin_branch(self):
        fake = FakeRpc()
        self._wire_basic_token_fields(fake, transfer_policy_id=0)
        self._wire_has_role(fake, {})
        _patch_rpc(self, fake)

        result = mt.score_token("Test Token", self.TOKEN, None, events=[])
        self.assertEqual(result["reads"]["policy"], {"id": 0, "type": "always-reject", "admin": None})
        self.assertEqual(result["rootControlSet"], [])

    def test_real_policy_adds_the_policy_admin_to_the_root_control_set(self):
        fake = FakeRpc()
        policy_admin = addr(0x30)
        _mark_eoa(fake, policy_admin)
        self._wire_basic_token_fields(fake, transfer_policy_id=5)
        self._wire_has_role(fake, {})
        fake.set_call(mt.TIP403_REGISTRY, "policyData(uint64)",
                      "0x" + encode(["uint8", "address"], [0, policy_admin]).hex())
        _patch_rpc(self, fake)

        result = mt.score_token("Test Token", self.TOKEN, None, events=[])
        self.assertEqual(result["reads"]["policy"]["admin"], policy_admin)
        self.assertEqual(result["reads"]["policy"]["type"], "WHITELIST")
        roles_in_root = [r["role"] for r in result["rootControlSet"]]
        self.assertIn("TIP-403 policy 5 admin", roles_in_root)

    def test_weakest_key_is_the_minimum_over_multiple_root_roles(self):
        # DEFAULT_ADMIN_ROLE holder is a 1-of-1 EOA (weak); if a second root
        # role were held by a stronger key, the WEAKEST must still win.
        fake = FakeRpc()
        admin_holder = addr(0x40)
        issuer_holder = addr(0x41)
        _mark_eoa(fake, admin_holder)
        _mark_eoa(fake, issuer_holder)
        self._wire_basic_token_fields(fake, transfer_policy_id=1)
        self._wire_has_role(fake, {"DEFAULT_ADMIN_ROLE": [admin_holder], "ISSUER_ROLE": [issuer_holder]})
        _patch_rpc(self, fake)

        events = [
            {"event": "RoleMembershipUpdated", "account": admin_holder},
            {"event": "RoleMembershipUpdated", "account": issuer_holder},
        ]
        result = mt.score_token("Test Token", self.TOKEN, None, events=events)
        self.assertEqual(len(result["rootControlSet"]), 2)
        # Both are (1,1) EOAs here -- weakest() must still resolve deterministically to one of them.
        self.assertIn(result["weakestKey"]["address"], (admin_holder, issuer_holder))


# --------------------------------------------------------------- score_vault_v2
class TestScoreVaultV2(unittest.TestCase):
    """Reproduces score_vault_v2()'s own docstring-documented, live-verified
    T1/T2/T3 regression shapes and asserts against those already-published
    numbers."""

    VAULT = addr(0x50)

    def _wire_safe(self, fake, safe_addr, k, n):
        fake.code[safe_addr.lower()] = "0x600160005260206000f3"
        owners = [addr(0x1000 + i) for i in range(n)]
        for o in owners:
            fake.code[o.lower()] = "0x"  # each owner is a bare EOA
        fake.set_call(safe_addr, "getThreshold()", "0x" + encode(["uint256"], [k]).hex())
        fake.set_call(safe_addr, "getOwners()", "0x" + encode(["address[]"], [owners]).hex())
        fake.set_call(safe_addr, "getModulesPaginated(address,uint256)",
                      "0x" + encode(["address[]", "address"], [[], mt.SAFE_SENTINEL]).hex())
        fake.set_call(safe_addr, "VERSION()", "0x" + encode(["string"], ["1.4.1"]).hex())
        fake.set_call(safe_addr, "nonce()", "0x" + encode(["uint256"], [1]).hex())
        fake.storage[(safe_addr.lower(), "0x0")] = "0x" + "00" * 31 + "01"

    def _wire_selector_delays(self, fake, delays_by_name, abdicated_names=frozenset()):
        # mt.VAULT_V2_FUND_DESTINATION_SELECTORS values are raw 4-byte
        # `bytes` (mt.selector() returns bytes, not a hex string) -- the
        # queried selector must be converted the same way before lookup.
        sel_to_name = {v: k for k, v in mt.VAULT_V2_FUND_DESTINATION_SELECTORS.items()}

        def dynamic(to, sel, raw_arg):
            if to != self.VAULT.lower():
                return None
            if sel == selector("abdicated(bytes4)"):
                queried_sel = bytes.fromhex(raw_arg[:8])
                name = sel_to_name.get(queried_sel)
                return "0x" + encode(["bool"], [name in abdicated_names]).hex()
            if sel == selector("timelock(bytes4)"):
                queried_sel = bytes.fromhex(raw_arg[:8])
                name = sel_to_name.get(queried_sel)
                return "0x" + encode(["uint256"], [delays_by_name.get(name, 0)]).hex()
            return None

        fake.dynamic = dynamic

    def test_t1_owner_1of1_curator_1of1_matches_published_scores(self):
        fake = FakeRpc()
        owner_safe, curator_safe = addr(0x60), addr(0x61)
        self._wire_safe(fake, owner_safe, 1, 1)
        self._wire_safe(fake, curator_safe, 1, 1)
        fake.set_call(self.VAULT, "owner()", "0x" + encode(["address"], [owner_safe]).hex())
        fake.set_call(self.VAULT, "curator()", "0x" + encode(["address"], [curator_safe]).hex())
        self._wire_selector_delays(fake, {
            "addAdapter": 259200, "removeAdapter": 259200,
            "increaseAbsoluteCap": 259200, "increaseRelativeCap": 259200,
        }, abdicated_names={"setAdapterRegistry"})
        _patch_rpc(self, fake)

        result = mt.score_vault_v2("Sentora pathUSD (Morpho Vault V2)", self.VAULT)
        self.assertEqual(result["reads"]["fundDestinationDelaySeconds"], 259200)
        self.assertEqual(
            (result["adminKeyScore"], result["multisigScore"], result["timelockScore"], result["compositeScore"]),
            (10, 15, 60, 27),
        )

    def test_t3_owner_4of7_curator_3of7_matches_published_scores(self):
        fake = FakeRpc()
        owner_safe, curator_safe = addr(0x70), addr(0x71)
        self._wire_safe(fake, owner_safe, 4, 7)
        self._wire_safe(fake, curator_safe, 3, 7)
        fake.set_call(self.VAULT, "owner()", "0x" + encode(["address"], [owner_safe]).hex())
        fake.set_call(self.VAULT, "curator()", "0x" + encode(["address"], [curator_safe]).hex())
        self._wire_selector_delays(fake, {
            "addAdapter": 259200, "removeAdapter": 259200,
            "increaseAbsoluteCap": 259200, "increaseRelativeCap": 259200,
        }, abdicated_names={"setAdapterRegistry"})
        _patch_rpc(self, fake)

        result = mt.score_vault_v2("Tempo Earn (Morpho Vault V2, Gauntlet-curated)", self.VAULT)
        self.assertEqual(
            (result["adminKeyScore"], result["multisigScore"], result["timelockScore"], result["compositeScore"]),
            (65, 56, 60, 61),
        )
        # The curator (3-of-7), not the owner (4-of-7), is the weaker/binding key.
        self.assertEqual(result["weakestKey"]["role"], "curator")

    def test_t2_owner_equals_curator_bare_eoa_zero_delay_matches_published_scores(self):
        fake = FakeRpc()
        eoa = addr(0x80)
        _mark_eoa(fake, eoa)
        fake.set_call(self.VAULT, "owner()", "0x" + encode(["address"], [eoa]).hex())
        fake.set_call(self.VAULT, "curator()", "0x" + encode(["address"], [eoa]).hex())
        # addAdapter/removeAdapter abdicated; the 3 cap/registry selectors are not, delay 0.
        self._wire_selector_delays(fake, {
            "setAdapterRegistry": 0, "increaseAbsoluteCap": 0, "increaseRelativeCap": 0,
        }, abdicated_names={"addAdapter", "removeAdapter"})
        _patch_rpc(self, fake)

        result = mt.score_vault_v2("Unnamed pathUSD Vault V2 feeding Sentora", self.VAULT)
        self.assertEqual(result["reads"]["fundDestinationDelaySeconds"], 0)
        self.assertEqual(
            (result["adminKeyScore"], result["multisigScore"], result["timelockScore"], result["compositeScore"]),
            (10, 15, 0, 9),
        )

    def test_every_selector_abdicated_uses_the_seven_day_top_band(self):
        fake = FakeRpc()
        eoa = addr(0x90)
        _mark_eoa(fake, eoa)
        fake.set_call(self.VAULT, "owner()", "0x" + encode(["address"], [eoa]).hex())
        fake.set_call(self.VAULT, "curator()", "0x" + encode(["address"], [eoa]).hex())
        self._wire_selector_delays(fake, {}, abdicated_names=set(mt.VAULT_V2_FUND_DESTINATION_SELECTORS.keys()))
        _patch_rpc(self, fake)

        result = mt.score_vault_v2("fully abdicated vault", self.VAULT)
        self.assertEqual(result["reads"]["fundDestinationDelaySeconds"], 7 * 86400)
        self.assertEqual(result["timelockScore"], mt.timelock_score(7 * 86400))


# ------------------------------------------------------------------ score_morpho_blue
class TestScoreMorphoBlue(unittest.TestCase):
    """ADDED 2026-09-19 with rule R9 (Morpho Blue core). The live shape
    (owner = Safe 5-of-9, 9 EOA signers, no module/guard, no timelock)
    must reproduce the published 65/96/0/55."""

    CORE = addr(0xB10E)

    def _wire_safe(self, fake, safe_addr, k, n, base=0x2000):
        fake.code[safe_addr.lower()] = "0x600160005260206000f3"
        owners = [addr(base + i) for i in range(n)]
        for o in owners:
            fake.code[o.lower()] = "0x"
        fake.set_call(safe_addr, "getThreshold()", "0x" + encode(["uint256"], [k]).hex())
        fake.set_call(safe_addr, "getOwners()", "0x" + encode(["address[]"], [owners]).hex())
        fake.set_call(safe_addr, "getModulesPaginated(address,uint256)",
                      "0x" + encode(["address[]", "address"], [[], mt.SAFE_SENTINEL]).hex())
        fake.set_call(safe_addr, "VERSION()", "0x" + encode(["string"], ["1.4.1"]).hex())
        fake.set_call(safe_addr, "nonce()", "0x" + encode(["uint256"], [1]).hex())
        return owners

    def test_owner_safe_5of9_matches_published_scores(self):
        fake = FakeRpc()
        safe = addr(0xA0)
        owners = self._wire_safe(fake, safe, 5, 9)
        fake.set_call(self.CORE, "owner()", "0x" + encode(["address"], [safe]).hex())
        fake.set_call(self.CORE, "feeRecipient()", "0x" + encode(["address"], [addr(0)]).hex())
        _patch_rpc(self, fake)

        result = mt.score_morpho_blue("Morpho Blue core", self.CORE)
        self.assertEqual(
            (result["adminKeyScore"], result["multisigScore"], result["timelockScore"],
             result["oracleAuthorityScore"], result["compositeScore"]),
            (65, 96, 0, 100, 55),
        )
        self.assertEqual(result["weakestKey"]["role"], "owner")
        self.assertEqual((result["weakestKey"]["k"], result["weakestKey"]["n"]), (5, 9))
        self.assertEqual(sorted(result["rootControlSet"][0]["signers"]), sorted(owners))
        self.assertIsNone(result["reads"]["proxyImplementation"])

    def test_eoa_owner_scores_as_single_key(self):
        fake = FakeRpc()
        eoa = addr(0xA1)
        _mark_eoa(fake, eoa)
        fake.set_call(self.CORE, "owner()", "0x" + encode(["address"], [eoa]).hex())
        _patch_rpc(self, fake)

        result = mt.score_morpho_blue("Morpho Blue core", self.CORE)
        self.assertEqual((result["adminKeyScore"], result["multisigScore"], result["compositeScore"]), (10, 15, 9))

    def test_renounced_owner_gives_empty_root_and_top_admin_score(self):
        fake = FakeRpc()
        fake.set_call(self.CORE, "owner()", "0x" + encode(["address"], [addr(0)]).hex())
        _patch_rpc(self, fake)

        result = mt.score_morpho_blue("Morpho Blue core", self.CORE)
        self.assertEqual(result["rootControlSet"], [])
        self.assertIsNone(result["weakestKey"])
        self.assertEqual((result["adminKeyScore"], result["multisigScore"]), (100, 100))


if __name__ == "__main__":
    unittest.main()
