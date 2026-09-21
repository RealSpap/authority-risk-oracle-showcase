"""
Unit tests for chains/monad/scorers.py's scoring-decision logic. Monad is
this project's 9th ecosystem (added 2026-09-19, picked as the winner of an
8-candidate scouting pass -- see chains/monad/scorers.py's own module
docstring for the full rationale) -- previously zero test coverage.

Same approach as `test_plasma_ecosystem_scorers.py`/
`test_base_ecosystem_scorers.py`: monkeypatch the read-primitive names this
file imports directly (`read_address_getter`, `call_raw`,
`safe_owners_and_threshold`) with small dict-dispatch fakes, rather than
mocking Web3.py's contract-call machinery. Every scorer here also calls
`w3.eth.get_code` directly (bytecode-presence notes) -- faked via a small
`FakeW3` below.
"""
import importlib.util
import os
import sys
import unittest

from web3 import Web3 as RealWeb3

REPO_ROOT = os.path.join(os.path.dirname(__file__), "..", "..", "..")


def _load_module(unique_name, relative_path):
    file_path = os.path.abspath(os.path.join(REPO_ROOT, relative_path))
    mod_dir = os.path.dirname(file_path)
    if mod_dir not in sys.path:
        sys.path.insert(0, mod_dir)
    spec = importlib.util.spec_from_file_location(unique_name, file_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[unique_name] = mod
    spec.loader.exec_module(mod)
    return mod


sys.path.insert(0, os.path.join(REPO_ROOT, "scripts", "lib"))
scorers = _load_module("aro_test_monad_scorers", "chains/monad/scorers.py")


def _addr(n):
    return RealWeb3.to_checksum_address("0x" + hex(n)[2:].zfill(40))


def _owners(n, start=1):
    return [_addr(i) for i in range(start, start + n)]


class FakeHelpers:
    def __init__(self):
        self.address_getters = {}
        self.call_raw_results = {}
        self.safe_results = {}
        self.code_sizes = {}

    def read_address_getter(self, w3, address, function_name, retries=4):
        return self.address_getters.get((address, function_name))

    def call_raw(self, w3, address, abi_fragment, function_name, *args, retries=4):
        return self.call_raw_results.get((address, function_name, args))

    def safe_owners_and_threshold(self, w3, address, retries=4):
        # The real web3_utils.safe_owners_and_threshold() checksums its
        # `address` argument internally before use -- a scorer is free to
        # pass a lowercase address (Monad's echo_ebtc scorer does), so this
        # fake must normalize the same way rather than requiring every
        # caller to pre-checksum its lookup keys.
        return self.safe_results.get(RealWeb3.to_checksum_address(address)) if address else None


def _patch_helpers(test_case, fake):
    names = ["read_address_getter", "call_raw", "safe_owners_and_threshold"]
    originals = {n: getattr(scorers, n) for n in names}
    for n in names:
        setattr(scorers, n, getattr(fake, n))
    # The Uniswap V4 scorer opens its own Ethereum w3 (like the Base and Arbitrum siblings); the fakes ignore the w3.
    original_get_w3 = scorers.get_w3
    scorers.get_w3 = lambda rpc_url, *a, **k: object()
    test_case.addCleanup(lambda: [setattr(scorers, n, originals[n]) for n in names] + [setattr(scorers, "get_w3", original_get_w3)])


class FakeEth:
    def __init__(self, fake):
        self.fake = fake

    def get_code(self, address):
        exact = getattr(self.fake, "code_bytes", {}).get(address.lower())
        if exact is not None:
            return exact
        return b"\x00" * self.fake.code_sizes.get(address.lower(), 0)


class FakeW3:
    def __init__(self, fake):
        self.eth = FakeEth(fake)

    @staticmethod
    def to_checksum_address(addr):
        return RealWeb3.to_checksum_address(addr)


EBTC = "0xd691b0aFed67F96CEC28Ab6308Cbe5b2C103b7e9"
# The scorer hardcodes this real, dated incident's actual on-chain
# addresses (not a parameterized target) -- tests wire against those same
# real addresses rather than swapping in synthetic ones.
EBTC_SAFE = RealWeb3.to_checksum_address("0x401a33127e4946a82709b5edc60c636581cab1c5")
EBTC_ORIGINAL_EOA = RealWeb3.to_checksum_address("0xA338eC2d52B19f4A48A00FCd76A36366B3529A3B")
EBTC_ATTACKER = RealWeb3.to_checksum_address("0x6a0109D3C5aB56277096c75e8F5D1D1d45243415")
POOL_MANAGER = "0x188d586Ddcf52439676Ca21A244753fA19F9Ea8e"
WORMHOLE_RECEIVER = "0xE783DE89a7F0408687f051e3E6D0BEb62719EbAd"
NTT_MANAGER = "0x36878C6FCa7e0E8a88F90dc410CfBBcA5B695C95"
GOVERNANCE_RELAY = "0x574b7864119c9223a9870ea614dc91a8ee09e512"
CORE_BRIDGE = "0x194b123c5e96b9b2e49763619985790dc241cac0"
ROUTER = "0xd651346d7c789536ebf06dc72aE3C8502cd695CC"
MARGIN_ACCOUNT = "0x2A68ba1833cDf93fa9Da1EEbd7F46242aD8E90c5"
KURU_SAFE = _addr(1)
VAULT = "0x32841A8511D5c2c5b253f45668780B99139e476D"
CURVE_FACTORY = "0x8271e06E5887FE5ba05234f5315c19f3Ec90E8aD"
CURVANCE_VAULT = "0xaD663aC84052b52BE4ed1b27BA416505e84a00Bf"
CENTRAL_REGISTRY = "0x1310f352f1389969Ece6741671c4B919523912fF"
DAO_TIMELOCK = "0x2677738657F27e1A3591E00AD7E5a78807688C08"
PAP = "0x34793Fb9935F7bB5E5aE920fb963F39063E7A615"
EXECUTOR = "0xa9d0EAFF48cE1DF468f9eAeb7e628c413343F6A2"
PAYLOADS_CONTROLLER = "0x442CA936e5E6Db875357d0A16481145c96dd9a82"
AAVE_GUARDIAN_SAFE = _addr(1)
AAVE_ACL_MANAGER = "0xa9fEe192a76B8f5e5f3d310AB6C526cB11F3d95B"
AAVE_PROTOCOL_GUARDIAN_SAFE = RealWeb3.to_checksum_address("0xc887455536CBD4e615B745e70CaCde15B3117e74")
EVAULT_FACTORY = "0xba4Dd672062dE8FeeDb665DD4410658864483f1E"
FACTORY_GOVERNOR = "0x515C9ff619b4618284832764E2cFc7d227514f0e"
FACTORY_TIMELOCK = "0x7Fe335ADfE4b89AcDAd28814cc7b89377fcEe439"
# Real, hardcoded (not discovered via a getter) inside score_euler_v2_monad()
# itself -- same convention as e.g. Curvance's CENTRAL_REGISTRY/DAO_TIMELOCK
# above -- so these test constants must match those literal addresses, not
# arbitrary placeholders, for FakeHelpers' dict lookups to hit.
EULER_DAO_SAFE = RealWeb3.to_checksum_address("0xdA3da5c8f93c0B7630412B8cd7dE571011Df8963")
EULER_SEC_COUNCIL = RealWeb3.to_checksum_address("0x6d2d19a06A49e87bedC653CEd58c17C3B40502F9")


class TestScoreEchoEbtcMonad(unittest.TestCase):
    def setUp(self):
        self.fake = FakeHelpers()
        _patch_helpers(self, self.fake)
        self.w3 = FakeW3(self.fake)
        self.default_admin_role = b"\x00" * 32
        self.minter_role = RealWeb3.keccak(text="MINTER_ROLE")
        self.upgrader_role = RealWeb3.keccak(text="UPGRADER_ROLE")

    def _wire(self, safe_has_admin=True, safe_has_minter=False, original_eoa_admin=False, attacker_admin=False, safe_data=None):
        self.fake.code_sizes[EBTC.lower()] = 212
        self.fake.call_raw_results[(EBTC, "hasRole", (self.default_admin_role, EBTC_SAFE))] = safe_has_admin
        self.fake.call_raw_results[(EBTC, "hasRole", (self.upgrader_role, EBTC_SAFE))] = True
        self.fake.call_raw_results[(EBTC, "hasRole", (self.minter_role, EBTC_SAFE))] = safe_has_minter
        self.fake.call_raw_results[(EBTC, "hasRole", (self.default_admin_role, EBTC_ORIGINAL_EOA))] = original_eoa_admin
        self.fake.call_raw_results[(EBTC, "hasRole", (self.default_admin_role, EBTC_ATTACKER))] = attacker_admin
        self.fake.safe_results[EBTC_SAFE] = safe_data if safe_data is not None else (_owners(4), 3)

    def test_remediated_3_of_4_safe_scores_moderate(self):
        self._wire()
        result = scorers.score_echo_ebtc_monad(self.w3)
        self.assertEqual(result["adminKeyScore"], 55)
        self.assertEqual(result["multisigScore"], 3 * 15 + 1 * 5)
        self.assertEqual(result["timelockScore"], 0)
        self.assertTrue(any("genuine remediation" in n for n in result["notes"]))

    def test_original_eoa_or_attacker_still_admin_is_disclosed(self):
        self._wire(original_eoa_admin=True)
        result = scorers.score_echo_ebtc_monad(self.w3)
        self.assertTrue(any("Original compromised EOA hasRole(DEFAULT_ADMIN_ROLE)=True" in n for n in result["notes"]))

    def test_safe_no_longer_admin_degrades(self):
        self._wire(safe_has_admin=False)
        result = scorers.score_echo_ebtc_monad(self.w3)
        self.assertEqual((result["adminKeyScore"], result["multisigScore"], result["timelockScore"]), (20, 0, 0))

    # ---- ADDED 2026-09-21: a 7702-delegated signer is disclosed, never scored ----
    METAMASK_DELEGATOR = "0x63c0c19a282a1B52b07dD5a65b58948A07DAE32B"

    def _with_7702_signer(self, delegate):
        owners = _owners(4)
        self.fake.code_bytes = {owners[0].lower(): bytes.fromhex("ef0100") + bytes.fromhex(delegate[2:])}
        self._wire(safe_data=(owners, 3))
        return owners[0]

    def test_a_known_7702_delegate_is_named_and_moves_no_score(self):
        self._wire()
        base = scorers.score_echo_ebtc_monad(self.w3)
        signer = self._with_7702_signer(self.METAMASK_DELEGATOR)
        result = scorers.score_echo_ebtc_monad(self.w3)
        note = next(n for n in result["notes"] if n.startswith("Signers that are not plain EOAs"))
        self.assertIn(signer, note)
        self.assertIn("MetaMask EIP7702StatelessDeleGator", note)
        for k in ("adminKeyScore", "multisigScore", "timelockScore", "compositeScore"):
            self.assertEqual(result[k], base[k])

    def test_an_unknown_7702_delegate_is_flagged_as_not_analyzed(self):
        self._with_7702_signer("0x" + "9f" * 20)
        result = scorers.score_echo_ebtc_monad(self.w3)
        self.assertTrue(any("delegate that has NOT been analyzed" in n for n in result["notes"]))

    def test_plain_eoa_signers_add_no_note(self):
        self._wire()
        result = scorers.score_echo_ebtc_monad(self.w3)
        self.assertFalse(any(n.startswith("Signers that are not plain EOAs") for n in result["notes"]))


class TestScoreUniswapV4Monad(unittest.TestCase):
    L1_SENDER = "0xf5F4496219F31CDCBa6130B5402873624585615a"
    L1_TIMELOCK = "0x1a9C8182C09F50C8318d769245beA52c32BE35BC"

    def setUp(self):
        self.fake = FakeHelpers()
        _patch_helpers(self, self.fake)
        self.w3 = FakeW3(self.fake)

    def _wire_resolved(self, sender=None, sender_owner=None):
        self.fake.address_getters[(POOL_MANAGER, "owner")] = WORMHOLE_RECEIVER
        self.fake.address_getters[(POOL_MANAGER, "protocolFeeController")] = _addr(0)
        self.fake.code_sizes[WORMHOLE_RECEIVER.lower()] = 7068
        self.fake.address_getters[(WORMHOLE_RECEIVER, "messageSender")] = sender or self.L1_SENDER
        self.fake.address_getters[(self.L1_SENDER, "owner")] = sender_owner or self.L1_TIMELOCK
        self.fake.call_raw_results[(self.L1_TIMELOCK, "delay", ())] = 172800
        self.fake.call_raw_results[(self.L1_TIMELOCK, "admin", ())] = _addr(0x408)

    def test_the_ethereum_hop_is_read_live_not_taken_from_a_snapshot(self):
        # 2026-09-21: messageSender() on the Monad receiver, then owner() of that sender on Ethereum (own w3).
        self._wire_resolved()
        result = scorers.score_uniswap_v4_monad(self.w3)
        self.assertTrue(any("messageSender() = %s" % self.L1_SENDER in n and n.endswith("True)") for n in result["notes"]))
        self.assertTrue(any(".owner() = %s" % self.L1_TIMELOCK in n and "172800s" in n for n in result["notes"]))
        self.assertFalse(any("disclosed snapshot" in n for n in result["notes"]))
        self.assertEqual(result["crossExposureScore"], 80)

    def test_an_unexpected_message_sender_or_timelock_owner_never_asserts_the_shared_root(self):
        for kwargs in ({"sender": _addr(0xBAD)}, {"sender_owner": _addr(0xBAD)}):
            fake = FakeHelpers()
            self.fake = fake
            _patch_helpers(self, fake)
            self.w3 = FakeW3(fake)
            self._wire_resolved(**kwargs)
            result = scorers.score_uniswap_v4_monad(self.w3)
            self.assertEqual(result["crossExposureScore"], 100, kwargs)
            self.assertFalse(any("crossExposureScore = 80" in n for n in result["notes"]), kwargs)
            # the sub-scores do not move: only the cross claim depends on the live hop
            self.assertEqual((result["adminKeyScore"], result["timelockScore"]), (80, 60), kwargs)

    def test_resolved_wormhole_relay_scores_dao_timelock_band(self):
        self._wire_resolved()

        result = scorers.score_uniswap_v4_monad(self.w3)

        self.assertEqual(result["adminKeyScore"], 80)
        self.assertEqual(result["multisigScore"], 100)
        self.assertEqual(result["timelockScore"], 60)
        self.assertTrue(any("UNI Timelock" in n for n in result["notes"]))
        # 2026-09-20: the same L1 Timelock roots Uniswap targets on 4 other ecosystems -> flat cross-ecosystem 80.
        self.assertEqual(result["crossExposureScore"], 80)
        self.assertTrue(any("crossExposureScore = 80" in n and "Governance Timelock" in n for n in result["notes"]))

    def test_owner_not_expected_receiver_degrades(self):
        self.fake.address_getters[(POOL_MANAGER, "owner")] = _addr(99)
        self.fake.address_getters[(POOL_MANAGER, "protocolFeeController")] = None
        self.fake.code_sizes[WORMHOLE_RECEIVER.lower()] = 0

        result = scorers.score_uniswap_v4_monad(self.w3)
        self.assertEqual((result["adminKeyScore"], result["multisigScore"], result["timelockScore"]), (20, 20, 0))
        self.assertEqual(result["crossExposureScore"], 100)  # an unresolved chain never asserts a shared root
        self.assertFalse(any("crossExposureScore = 80" in n for n in result["notes"]))


class TestScoreMonadNativeBridge(unittest.TestCase):
    def setUp(self):
        self.fake = FakeHelpers()
        _patch_helpers(self, self.fake)
        self.w3 = FakeW3(self.fake)

    def test_resolved_guardian_quorum_scores_high(self):
        self.fake.code_sizes[NTT_MANAGER.lower()] = 177
        self.fake.address_getters[(NTT_MANAGER, "owner")] = GOVERNANCE_RELAY
        self.fake.call_raw_results[(NTT_MANAGER, "isPaused", ())] = False
        self.fake.code_sizes[GOVERNANCE_RELAY.lower()] = 3408
        self.fake.call_raw_results[(CORE_BRIDGE, "getCurrentGuardianSetIndex", ())] = 7
        self.fake.call_raw_results[(CORE_BRIDGE, "quorum", (19,))] = 13

        result = scorers.score_monad_native_bridge(self.w3)

        self.assertEqual(result["adminKeyScore"], 75)
        self.assertEqual(result["multisigScore"], 100)
        self.assertEqual(result["timelockScore"], 0)
        self.assertTrue(any("13-of-19" in n for n in result["notes"]))

    def test_wrong_quorum_value_degrades(self):
        self.fake.code_sizes[NTT_MANAGER.lower()] = 177
        self.fake.address_getters[(NTT_MANAGER, "owner")] = GOVERNANCE_RELAY
        self.fake.call_raw_results[(NTT_MANAGER, "isPaused", ())] = False
        self.fake.code_sizes[GOVERNANCE_RELAY.lower()] = 3408
        self.fake.call_raw_results[(CORE_BRIDGE, "getCurrentGuardianSetIndex", ())] = 7
        self.fake.call_raw_results[(CORE_BRIDGE, "quorum", (19,))] = None  # call failed/reverted

        result = scorers.score_monad_native_bridge(self.w3)
        self.assertEqual((result["adminKeyScore"], result["multisigScore"], result["timelockScore"]), (20, 20, 0))


class TestScoreKuruMonad(unittest.TestCase):
    def setUp(self):
        self.fake = FakeHelpers()
        _patch_helpers(self, self.fake)
        self.w3 = FakeW3(self.fake)

    def test_3_of_5_safe_no_timelock(self):
        self.fake.code_sizes[ROUTER.lower()] = 141
        self.fake.address_getters[(ROUTER, "owner")] = KURU_SAFE
        self.fake.address_getters[(MARGIN_ACCOUNT, "owner")] = KURU_SAFE
        self.fake.safe_results[KURU_SAFE] = (_owners(5), 3)

        result = scorers.score_kuru_monad(self.w3)

        self.assertEqual(result["adminKeyScore"], 65)
        self.assertEqual(result["multisigScore"], 3 * 15 + 2 * 5)
        self.assertEqual(result["timelockScore"], 0)

    def test_owner_unresolvable_degrades(self):
        self.fake.code_sizes[ROUTER.lower()] = 141
        self.fake.address_getters[(ROUTER, "owner")] = _addr(50)
        self.fake.address_getters[(MARGIN_ACCOUNT, "owner")] = _addr(50)
        self.fake.safe_results[_addr(50)] = None

        result = scorers.score_kuru_monad(self.w3)
        self.assertEqual((result["adminKeyScore"], result["multisigScore"], result["timelockScore"]), (20, 0, 0))


class TestScoreMorphoVaultMonad(unittest.TestCase):
    def setUp(self):
        self.fake = FakeHelpers()
        _patch_helpers(self, self.fake)
        self.w3 = FakeW3(self.fake)

    def _wire(self, curator_addr, guardian_addr, owner_threshold=5, curator_threshold=2):
        self.fake.code_sizes[VAULT.lower()] = 19689
        self.fake.address_getters[(VAULT, "owner")] = _addr(1)
        self.fake.address_getters[(VAULT, "curator")] = curator_addr
        self.fake.address_getters[(VAULT, "guardian")] = guardian_addr
        self.fake.safe_results[_addr(1)] = (_owners(8), owner_threshold)
        self.fake.safe_results[curator_addr] = (_owners(6, start=100), curator_threshold)
        if guardian_addr != curator_addr:
            self.fake.safe_results[guardian_addr] = (_owners(6, start=200), curator_threshold)

    def test_curator_equals_guardian_caps_timelock_score(self):
        self._wire(_addr(100), _addr(100))
        result = scorers.score_morpho_vault_monad(self.w3)

        self.assertEqual(result["adminKeyScore"], 70)
        self.assertEqual(result["multisigScore"], 2 * 15 + 4 * 5)
        self.assertEqual(result["timelockScore"], 55)
        self.assertTrue(any("SAME Safe" in n for n in result["notes"]))

    def test_independent_guardian_scores_higher_timelock(self):
        self._wire(_addr(100), _addr(200))
        result = scorers.score_morpho_vault_monad(self.w3)
        self.assertEqual(result["timelockScore"], 75)

    def test_unresolvable_safe_degrades(self):
        self.fake.code_sizes[VAULT.lower()] = 19689
        self.fake.address_getters[(VAULT, "owner")] = _addr(1)
        self.fake.address_getters[(VAULT, "curator")] = _addr(2)
        self.fake.address_getters[(VAULT, "guardian")] = _addr(2)
        self.fake.safe_results[_addr(1)] = None
        self.fake.safe_results[_addr(2)] = None

        result = scorers.score_morpho_vault_monad(self.w3)
        self.assertEqual((result["adminKeyScore"], result["multisigScore"], result["timelockScore"]), (20, 0, 0))

    def test_unrelated_signer_set_scores_cross_exposure_100(self):
        self._wire(_addr(100), _addr(200))
        result = scorers.score_morpho_vault_monad(self.w3)
        self.assertEqual(result["crossExposureScore"], 100)
        self.assertTrue(any("not computed this pass" in n or "IS wired" in n for n in result["notes"]))

    def test_curator_subset_of_known_robinhood_committee_scores_80(self):
        # Real addresses from scripts/lib/cross_ecosystem_overlap.py's own
        # MONAD_GROUPS -- this vault's real curator Safe on Monad mainnet.
        real_curator = RealWeb3.to_checksum_address("0x827e86072B06674a077f592A531dcE4590aDeCdB")
        real_owner = RealWeb3.to_checksum_address("0x0A0e559bc3b0950a7e448F0d4894db195b9cf8DD")
        self.fake.code_sizes[VAULT.lower()] = 19689
        self.fake.address_getters[(VAULT, "owner")] = real_owner
        self.fake.address_getters[(VAULT, "curator")] = real_curator
        self.fake.address_getters[(VAULT, "guardian")] = real_curator
        self.fake.safe_results[real_owner] = (_owners(8, start=900), 5)  # unrelated owner set -- only curator should trigger this
        # safe_owners_and_threshold returns (owners, threshold); wrap the frozenset as a list.
        self.fake.safe_results[real_curator] = (list(scorers._KNOWN_ROBINHOOD_STEAKHOUSE_CURATOR_OWNERS_2026_09_19), 2)

        result = scorers.score_morpho_vault_monad(self.w3)
        self.assertEqual(result["crossExposureScore"], 80)
        self.assertTrue(any("Real cross-chain finding" in n for n in result["notes"]))


class TestScoreCurveMonad(unittest.TestCase):
    def setUp(self):
        self.fake = FakeHelpers()
        _patch_helpers(self, self.fake)
        self.w3 = FakeW3(self.fake)

    def test_bare_eoa_admin_scores_lowest(self):
        self.fake.code_sizes[CURVE_FACTORY.lower()] = 13996
        self.fake.address_getters[(CURVE_FACTORY, "admin")] = _addr(1)
        self.fake.code_sizes[_addr(1).lower()] = 0  # confirmed EOA, no bytecode

        result = scorers.score_curve_monad(self.w3)

        self.assertEqual((result["adminKeyScore"], result["multisigScore"], result["timelockScore"]), (10, 0, 0))
        self.assertTrue(any("weakest authority shape" in n for n in result["notes"]))
        self.assertEqual(result["crossExposureScore"], 100)  # unrelated synthetic admin, no match

    def test_admin_matches_known_robinhood_curve_eoa_scores_80(self):
        # The real admin EOA from scripts/lib/cross_ecosystem_overlap.py's
        # own MONAD_GROUPS["curve_admin"] -- also Robinhood Chain's own
        # already-tracked Curve admin (identical factory address too, both
        # hardcoded inside score_curve_monad itself).
        real_admin = RealWeb3.to_checksum_address("0xabc336d4C71ad275695744d32DdB1d8266Db1cbF")
        self.fake.code_sizes[CURVE_FACTORY.lower()] = 13996
        self.fake.address_getters[(CURVE_FACTORY, "admin")] = real_admin
        self.fake.code_sizes[real_admin.lower()] = 0  # confirmed EOA

        result = scorers.score_curve_monad(self.w3)
        self.assertEqual(result["crossExposureScore"], 80)
        self.assertTrue(any("Real cross-chain finding" in n for n in result["notes"]))

    def test_admin_turns_out_to_be_a_safe(self):
        self.fake.code_sizes[CURVE_FACTORY.lower()] = 13996
        self.fake.address_getters[(CURVE_FACTORY, "admin")] = _addr(2)
        self.fake.code_sizes[_addr(2).lower()] = 500  # has code, not a bare EOA
        self.fake.safe_results[_addr(2)] = (_owners(5), 3)

        result = scorers.score_curve_monad(self.w3)
        self.assertEqual(result["adminKeyScore"], 65)


class TestScoreCurvanceMonad(unittest.TestCase):
    def setUp(self):
        self.fake = FakeHelpers()
        _patch_helpers(self, self.fake)
        self.w3 = FakeW3(self.fake)

    def test_active_emergency_council_scores_zero_delay(self):
        self.fake.code_sizes[CURVANCE_VAULT.lower()] = 21822
        self.fake.address_getters[(CENTRAL_REGISTRY, "emergencyCouncil")] = _addr(1)
        self.fake.call_raw_results[(DAO_TIMELOCK, "getMinDelay", ())] = 432000
        self.fake.call_raw_results[(CENTRAL_REGISTRY, "hasElevatedPermissions", (_addr(1),))] = True
        self.fake.safe_results[_addr(1)] = (_owners(5), 4)

        result = scorers.score_curvance_monad(self.w3)

        self.assertEqual(result["adminKeyScore"], 60)
        self.assertEqual(result["multisigScore"], 4 * 15 + 1 * 5)
        self.assertEqual(result["timelockScore"], 0)
        self.assertTrue(any("4-of-5 Emergency Council signers" in n for n in result["notes"]))

    def test_remediated_permissions_degrades_conservatively(self):
        self.fake.code_sizes[CURVANCE_VAULT.lower()] = 21822
        self.fake.address_getters[(CENTRAL_REGISTRY, "emergencyCouncil")] = _addr(1)
        self.fake.call_raw_results[(DAO_TIMELOCK, "getMinDelay", ())] = 432000
        self.fake.call_raw_results[(CENTRAL_REGISTRY, "hasElevatedPermissions", (_addr(1),))] = False
        self.fake.safe_results[_addr(1)] = (_owners(5), 4)

        result = scorers.score_curvance_monad(self.w3)
        self.assertEqual((result["adminKeyScore"], result["multisigScore"], result["timelockScore"]), (20, 0, 0))


class TestScoreAaveV3Monad(unittest.TestCase):
    def setUp(self):
        self.fake = FakeHelpers()
        _patch_helpers(self, self.fake)
        self.w3 = FakeW3(self.fake)
        self.default_admin_role = b"\x00" * 32

    def _wire(self, guardian_owners=None, guardian_threshold=5, loop_closes=True, l2_executor=_addr(0), l2_delay=0,
              pool_admin=False, acl=AAVE_ACL_MANAGER, pg_safe=None):
        # CHANGED 2026-09-20: the scorer now reads isPoolAdmin(PROTOCOL_GUARDIAN Safe) off the ACLManager.
        # Default pool_admin=False keeps the pre-change DAO-path scoring for the tests written before it.
        if acl:
            self.fake.address_getters[(PAP, "getACLManager")] = acl
        self.fake.call_raw_results[(AAVE_ACL_MANAGER, "isPoolAdmin", (AAVE_PROTOCOL_GUARDIAN_SAFE,))] = pool_admin
        self.fake.call_raw_results[(AAVE_ACL_MANAGER, "isEmergencyAdmin", (AAVE_PROTOCOL_GUARDIAN_SAFE,))] = True
        if pg_safe is not None:
            self.fake.safe_results[AAVE_PROTOCOL_GUARDIAN_SAFE] = pg_safe
        self.fake.address_getters[(PAP, "owner")] = EXECUTOR
        self.fake.address_getters[(EXECUTOR, "owner")] = PAYLOADS_CONTROLLER
        self.fake.address_getters[(PAYLOADS_CONTROLLER, "owner")] = EXECUTOR if loop_closes else _addr(99)
        self.fake.call_raw_results[(PAYLOADS_CONTROLLER, "getExecutorSettingsByAccessControl", (1,))] = (EXECUTOR, 86400)
        self.fake.call_raw_results[(PAYLOADS_CONTROLLER, "getExecutorSettingsByAccessControl", (2,))] = (l2_executor, l2_delay)
        self.fake.call_raw_results[(PAYLOADS_CONTROLLER, "guardian", ())] = AAVE_GUARDIAN_SAFE
        if guardian_owners is not None:
            self.fake.safe_results[AAVE_GUARDIAN_SAFE] = (guardian_owners, guardian_threshold)

    def test_closed_loop_with_known_guardian_committee_scores_cross_exposure_80(self):
        known = list(scorers._KNOWN_AAVE_GUARDIAN_OWNERS_2026_09_17)
        self._wire(guardian_owners=known, guardian_threshold=5)

        result = scorers.score_aave_v3_monad(self.w3)

        self.assertEqual(result["adminKeyScore"], 65)
        self.assertEqual(result["multisigScore"], 100)
        self.assertEqual(result["timelockScore"], 50)
        self.assertEqual(result["crossExposureScore"], 80)
        self.assertTrue(any("five chains in total" in n for n in result["notes"]))

    def test_unknown_guardian_set_scores_cross_exposure_100(self):
        self._wire(guardian_owners=_owners(9, start=500), guardian_threshold=5)

        result = scorers.score_aave_v3_monad(self.w3)

        self.assertEqual(result["crossExposureScore"], 100)
        self.assertTrue(any("not computed this pass" in n or "IS wired" in n for n in result["notes"]))

    def test_broken_loop_degrades_admin_key(self):
        self._wire(loop_closes=False, guardian_owners=_owners(9, start=500))

        result = scorers.score_aave_v3_monad(self.w3)

        self.assertEqual(result["adminKeyScore"], 30)

    def test_level_2_not_configured_is_disclosed(self):
        self._wire(guardian_owners=_owners(9, start=500))

        result = scorers.score_aave_v3_monad(self.w3)

        self.assertTrue(any("NOT yet configured on Monad" in n for n in result["notes"]))

    # ADDED 2026-09-20: the PROTOCOL_GUARDIAN Safe's isPoolAdmin seat is now scored (Safe-no-timelock rule).
    def test_pool_admin_seat_true_scores_the_safe_no_timelock_path(self):
        known = list(scorers._KNOWN_AAVE_GUARDIAN_OWNERS_2026_09_17)
        self._wire(guardian_owners=known, pool_admin=True, pg_safe=(_owners(7, start=700), 4))

        result = scorers.score_aave_v3_monad(self.w3)

        self.assertEqual(result["adminKeyScore"], 65)  # threshold 4 >= 3
        self.assertEqual(result["multisigScore"], 75)  # 4*15 + 3*5
        self.assertEqual(result["timelockScore"], 0)  # the 1-day delay does not bind the instant upgrade path
        self.assertEqual(result["compositeScore"], 49)  # was 71 on the old Executor + delay model
        self.assertEqual(result["crossExposureScore"], 80)  # unchanged: 9-signer guardian committee still matches
        self.assertTrue(any("SCORED (2026-09-20)" in n and "4-of-7" in n for n in result["notes"]))
        # the DAO path and the mitigating facts stay disclosed
        self.assertTrue(any("Executor delay (86400s)" in n for n in result["notes"]))
        self.assertTrue(any("Executor holds DEFAULT_ADMIN and can revoke the seat" in n for n in result["notes"]))

    def test_pool_admin_seat_true_admin_key_follows_the_safe_threshold(self):
        for threshold, n_owners, want_admin, want_multisig in [
            (3, 5, 65, 55),   # 3*15 + 2*5
            (2, 3, 50, 35),   # 2*15 + 1*5
            (1, 3, 10, 25),   # 1*15 + 2*5
            (7, 7, 65, 100),  # 7*15 = 105, capped at 100
        ]:
            with self.subTest(threshold=threshold, n_owners=n_owners):
                self._wire(guardian_owners=_owners(9, start=500), pool_admin=True,
                           pg_safe=(_owners(n_owners, start=700), threshold))
                result = scorers.score_aave_v3_monad(self.w3)
                self.assertEqual(
                    (result["adminKeyScore"], result["multisigScore"], result["timelockScore"]),
                    (want_admin, want_multisig, 0),
                )

    def test_pool_admin_seat_true_never_raises_a_broken_executor_loop_score(self):
        self._wire(loop_closes=False, guardian_owners=_owners(9, start=500), pool_admin=True,
                   pg_safe=(_owners(7, start=700), 4))

        result = scorers.score_aave_v3_monad(self.w3)

        self.assertEqual(result["adminKeyScore"], 30)  # min(DAO-path 30, Safe 65), not raised to 65
        self.assertEqual(result["multisigScore"], 75)
        self.assertEqual(result["timelockScore"], 0)

    def test_pool_admin_seat_false_keeps_the_dao_path_scoring(self):
        known = list(scorers._KNOWN_AAVE_GUARDIAN_OWNERS_2026_09_17)
        self._wire(guardian_owners=known, pool_admin=False, pg_safe=(_owners(7, start=700), 4))

        result = scorers.score_aave_v3_monad(self.w3)

        self.assertEqual(
            (result["adminKeyScore"], result["multisigScore"], result["timelockScore"], result["compositeScore"]),
            (65, 100, 50, 71),
        )
        self.assertEqual(result["crossExposureScore"], 80)
        self.assertFalse(any("SCORED (2026-09-20)" in n or "DEGRADED" in n for n in result["notes"]))

    def test_pool_admin_unread_degrades_conservatively(self):
        known = list(scorers._KNOWN_AAVE_GUARDIAN_OWNERS_2026_09_17)
        self._wire(guardian_owners=known, pool_admin=None, pg_safe=(_owners(7, start=700), 4))

        result = scorers.score_aave_v3_monad(self.w3)

        self.assertEqual((result["adminKeyScore"], result["multisigScore"], result["timelockScore"]), (20, 20, 0))
        self.assertEqual(result["compositeScore"], 14)
        self.assertEqual(result["crossExposureScore"], 80)  # unchanged by the degrade
        self.assertTrue(any("DEGRADED" in n and "unread" in n for n in result["notes"]))

    def test_acl_manager_unread_degrades_conservatively(self):
        self._wire(guardian_owners=_owners(9, start=500), acl=None)

        result = scorers.score_aave_v3_monad(self.w3)

        self.assertEqual((result["adminKeyScore"], result["multisigScore"], result["timelockScore"]), (20, 20, 0))
        self.assertTrue(any("DEGRADED" in n for n in result["notes"]))
        self.assertTrue(any("ACLManager unread this run" in n for n in result["notes"]))

    def test_pool_admin_true_but_safe_unresolved_degrades_conservatively(self):
        known = list(scorers._KNOWN_AAVE_GUARDIAN_OWNERS_2026_09_17)
        self._wire(guardian_owners=known, pool_admin=True, pg_safe=None)

        result = scorers.score_aave_v3_monad(self.w3)

        self.assertEqual((result["adminKeyScore"], result["multisigScore"], result["timelockScore"]), (20, 20, 0))
        self.assertEqual(result["crossExposureScore"], 80)
        self.assertTrue(any("DEGRADED" in n and "did NOT resolve" in n for n in result["notes"]))


class TestScoreEulerV2Monad(unittest.TestCase):
    def setUp(self):
        self.fake = FakeHelpers()
        _patch_helpers(self, self.fake)
        self.w3 = FakeW3(self.fake)

    def _wire(self, dao_owners=None, dao_threshold=4, delay=345600, chain_closed=True, sec_council_owners=None):
        self.fake.code_sizes[EVAULT_FACTORY.lower()] = 5631
        self.fake.address_getters[(EVAULT_FACTORY, "upgradeAdmin")] = FACTORY_GOVERNOR if chain_closed else _addr(99)
        self.fake.call_raw_results[(FACTORY_GOVERNOR, "hasRole", (b"\x00" * 32, FACTORY_TIMELOCK))] = chain_closed
        self.fake.call_raw_results[(FACTORY_TIMELOCK, "getMinDelay", ())] = delay
        proposer_role = RealWeb3.keccak(text="PROPOSER_ROLE")
        executor_role = RealWeb3.keccak(text="EXECUTOR_ROLE")
        self.fake.call_raw_results[(FACTORY_TIMELOCK, "hasRole", (proposer_role, EULER_DAO_SAFE))] = True
        self.fake.call_raw_results[(FACTORY_TIMELOCK, "hasRole", (executor_role, _addr(0)))] = True
        if dao_owners is not None:
            self.fake.safe_results[EULER_DAO_SAFE] = (dao_owners, dao_threshold)
        if sec_council_owners is not None:
            self.fake.safe_results[EULER_SEC_COUNCIL] = (sec_council_owners, 2)

    def test_closed_loop_with_known_dao_signers_scores_cross_exposure_80(self):
        known = list(scorers._KNOWN_EULER_DAO_SIGNERS_2026_09_19)
        self._wire(dao_owners=known, dao_threshold=4, sec_council_owners=_owners(3, start=700))

        result = scorers.score_euler_v2_monad(self.w3)

        self.assertEqual(result["adminKeyScore"], 55)
        self.assertEqual(result["multisigScore"], 4 * 15 + 4 * 5)
        self.assertEqual(result["timelockScore"], 60)
        self.assertEqual(result["crossExposureScore"], 80)
        self.assertTrue(any("byte-identical" in n for n in result["notes"]))

    def test_unknown_dao_signer_set_scores_cross_exposure_100(self):
        self._wire(dao_owners=_owners(8, start=600), dao_threshold=4, sec_council_owners=_owners(3, start=700))

        result = scorers.score_euler_v2_monad(self.w3)

        self.assertEqual(result["crossExposureScore"], 100)
        self.assertTrue(any("not computed this pass" in n or "IS wired" in n for n in result["notes"]))

    def test_unresolvable_dao_safe_degrades(self):
        self._wire(dao_owners=None)

        result = scorers.score_euler_v2_monad(self.w3)
        self.assertEqual((result["adminKeyScore"], result["multisigScore"], result["timelockScore"]), (20, 0, 0))

    def test_broken_admin_role_chain_degrades_admin_key(self):
        self._wire(dao_owners=_owners(8, start=600), dao_threshold=4, chain_closed=False)

        result = scorers.score_euler_v2_monad(self.w3)
        self.assertEqual(result["adminKeyScore"], 25)

    def test_shorter_delay_scores_lower_timelock(self):
        self._wire(dao_owners=_owners(8, start=600), dao_threshold=4, delay=86400)

        result = scorers.score_euler_v2_monad(self.w3)
        self.assertEqual(result["timelockScore"], 40)


class TestScoreAllMonad(unittest.TestCase):
    """Smoke test: score_all() runs every SIMPLE_SCORERS entry through
    safe_score()'s per-target isolation and returns a flat list -- does not
    re-verify each scorer's own decision logic (covered above), just that a
    single failing scorer doesn't take down the whole batch."""

    def test_a_single_failing_scorer_does_not_crash_the_batch(self):
        class ExplodingW3:
            class eth:
                @staticmethod
                def get_code(addr):
                    raise RuntimeError("RPC down")

            @staticmethod
            def to_checksum_address(addr):
                return RealWeb3.to_checksum_address(addr)

        results = scorers.score_all(ExplodingW3())
        self.assertIsInstance(results, list)


class TestPauseGuardianNote(unittest.TestCase):
    """_pause_guardian_note(): PAUSE_GUARDIAN_ROLE on the eVaultFactory Governor was
    invisible to this scorer (it searched for role names the deployed contracts do
    not use). Two bare EOAs and the Labs Safe hold it; either EOA alone can call
    pause(eVaultFactory). Notes only, no score changes."""
    GOVERNOR = FACTORY_GOVERNOR
    SAFE = RealWeb3.to_checksum_address("0x9cC876dCb0e99cC040cf5F92880d0Ee9e320CA61")
    EOA_A = RealWeb3.to_checksum_address("0xff217004BdD3A6A592162380dc0E6BbF143291eB")
    EOA_B = RealWeb3.to_checksum_address("0xcC6451385685721778E7Bd80B54F8c92b484F601")

    def _wire(self, holders, count=None):
        fake = FakeHelpers()
        role = scorers._PAUSE_GUARDIAN_ROLE
        fake.call_raw_results[(self.GOVERNOR, "getRoleMemberCount", (role,))] = len(holders) if count is None else count
        for i, (addr, code_size) in enumerate(holders):
            fake.call_raw_results[(self.GOVERNOR, "getRoleMember", (role, i))] = addr
            fake.code_sizes[addr.lower()] = code_size
        _patch_helpers(self, fake)
        return FakeW3(fake)

    def test_role_hash_is_the_real_keccak_not_a_typed_constant(self):
        self.assertEqual(scorers._PAUSE_GUARDIAN_ROLE, RealWeb3.keccak(text="PAUSE_GUARDIAN_ROLE"))

    def test_lists_every_holder_and_counts_bare_eoas(self):
        w3 = self._wire([(self.SAFE, 171), (self.EOA_A, 0), (self.EOA_B, 0)])
        note = scorers._pause_guardian_note(w3, self.GOVERNOR)
        self.assertIn("3 holder(s)", note)
        self.assertIn(f"{self.SAFE} (contract)", note)
        self.assertIn(f"{self.EOA_A} (bare EOA)", note)
        self.assertIn(f"{self.EOA_B} (bare EOA)", note)
        self.assertIn("2 bare EOA(s)", note)
        self.assertIn("NOT scored", note)

    def test_unreadable_count_is_reported_not_guessed(self):
        fake = FakeHelpers()  # nothing registered -> call_raw returns None
        _patch_helpers(self, fake)
        note = scorers._pause_guardian_note(FakeW3(fake), self.GOVERNOR)
        self.assertIn("unread this run", note)

    def test_one_unreadable_member_does_not_hide_the_others(self):
        fake = FakeHelpers()
        role = scorers._PAUSE_GUARDIAN_ROLE
        fake.call_raw_results[(self.GOVERNOR, "getRoleMemberCount", (role,))] = 2
        fake.call_raw_results[(self.GOVERNOR, "getRoleMember", (role, 1))] = self.EOA_A
        fake.code_sizes[self.EOA_A.lower()] = 0
        _patch_helpers(self, fake)
        note = scorers._pause_guardian_note(FakeW3(fake), self.GOVERNOR)
        self.assertIn("<unread>", note)
        self.assertIn(f"{self.EOA_A} (bare EOA)", note)

    def test_member_loop_is_capped_at_ten(self):
        holders = [(RealWeb3.to_checksum_address("0x" + format(0x1000 + i, "040x")), 0) for i in range(25)]
        w3 = self._wire(holders)
        note = scorers._pause_guardian_note(w3, self.GOVERNOR)
        self.assertIn("25 holder(s)", note)  # the true count is still reported
        self.assertEqual(note.count("(bare EOA)"), 10)  # but only 10 members are read


class TestAaveAclSeatsNote(unittest.TestCase):
    """_aave_acl_seats_note(): the PROTOCOL_GUARDIAN Safe (same 7 owners as Ethereum L1's) holds
    isPoolAdmin on Monad alongside the DAO Executor -- an instant aToken-upgrade path. Disclosed
    here (with the mitigating facts) since 2026-09-19; SCORED by score_aave_v3_monad() since 2026-09-20."""
    PROVIDER = "0x34793Fb9935F7bB5E5aE920fb963F39063E7A615"
    ACL = "0xa9fEe192a76B8f5e5f3d310AB6C526cB11F3d95B"
    SAFE = RealWeb3.to_checksum_address("0xc887455536CBD4e615B745e70CaCde15B3117e74")

    def _wire(self, pool_admin, emergency, acl=ACL, safe_shape=None):
        fake = FakeHelpers()
        if safe_shape is not None:
            fake.safe_results[self.SAFE] = safe_shape
        if acl:
            fake.address_getters[(self.PROVIDER, "getACLManager")] = acl
        fake.call_raw_results[(self.ACL, "isPoolAdmin", (self.SAFE,))] = pool_admin
        fake.call_raw_results[(self.ACL, "isEmergencyAdmin", (self.SAFE,))] = emergency
        _patch_helpers(self, fake)
        return FakeW3(fake)

    def test_pool_admin_seat_is_flagged_as_a_scored_instant_upgrade_path_with_mitigations(self):
        note = scorers._aave_acl_seats_note(self._wire(True, True), self.PROVIDER)
        self.assertIn("isEmergencyAdmin = True", note)
        self.assertIn("isPoolAdmin = True", note)
        self.assertIn("instantly", note)
        self.assertIn("SCORES it", note)
        self.assertNotIn("does NOT score", note)  # the old "unscored" wording is now false
        self.assertIn("can revoke the seat", note)
        self.assertIn("cannot grant roles", note)
        self.assertIn("identical to Ethereum L1", note)

    def test_safe_shape_is_read_live_when_it_resolves(self):
        note = scorers._aave_acl_seats_note(self._wire(True, True, safe_shape=(_owners(7, start=700), 4)), self.PROVIDER)
        self.assertIn("4-of-7 read live", note)

    def test_unresolved_safe_falls_back_to_the_dated_hand_check_wording(self):
        note = scorers._aave_acl_seats_note(self._wire(True, True), self.PROVIDER)
        self.assertIn("NOT resolved this run", note)

    def test_emergency_only_seat_has_no_upgrade_warning(self):
        note = scorers._aave_acl_seats_note(self._wire(False, True), self.PROVIDER)
        self.assertIn("isPoolAdmin = False", note)
        self.assertNotIn("upgrade every reserve", note)

    def test_unreadable_acl_manager_is_reported_not_guessed(self):
        note = scorers._aave_acl_seats_note(self._wire(True, True, acl=None), self.PROVIDER)
        self.assertIn("unread this run", note)

    def test_unreadable_role_reads_do_not_claim_an_upgrade_path(self):
        note = scorers._aave_acl_seats_note(self._wire(None, None), self.PROVIDER)
        self.assertIn("isPoolAdmin = None", note)
        self.assertNotIn("upgrade every reserve", note)


if __name__ == "__main__":
    unittest.main()
