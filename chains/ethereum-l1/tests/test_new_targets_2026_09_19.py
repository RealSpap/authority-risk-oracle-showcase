"""
Unit tests for the 5 Ethereum L1 targets added on 2026-09-19
(score_compound_v3_cusdc, score_sparklend_pool, score_uniswap_v4_pool_manager,
score_morpho_blue_l1, score_wbtc) -- the resolved branch and the degraded
branch of each, plus the root-group sharing they introduce (Uniswap V3+V4,
Maker+Spark).

Kept inside chains/ethereum-l1/ (not scripts/lib/tests/) so this
ecosystem's worker never edits shared repo-root files. Same FakeHelpers
monkeypatch approach as scripts/lib/tests/test_ethereum_l1_scorers.py: no
network, no RPC.

Run:  python3 -m unittest discover -s chains/ethereum-l1/tests -v
"""
import importlib.util
import os
import sys
import unittest

from web3 import Web3 as RealWeb3

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts", "lib"))


def _load(name, rel):
    path = os.path.join(REPO_ROOT, rel)
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


scorers = _load("aro_eth_l1_new_targets_scorers", "chains/ethereum-l1/scorers.py")


# ADDED 2026-10-04: these tests pin the composite logic on a fake chain the price-path engine cannot walk. The engine is
# replaced here by a stub returning 100; scripts/lib/tests/test_price_authority_wiring.py checks that each consumer scorer
# really puts the engine's value into oracleAuthorityScore.
_PA_NAMES = ("for_aave", "for_aave_v2", "for_comet", "for_morpho_v1", "for_morpho_v2", "for_gmx_v2", "for_gmx_v1", "for_euler_factory", "for_euler_earn",
            "for_sparklend")
_PA_ORIG = {}


def setUpModule():
    for n in _PA_NAMES:
        _PA_ORIG[n] = getattr(scorers.price_authority, n)
        setattr(scorers.price_authority, n, lambda *a, **k: 100)


def tearDownModule():
    for n, f in _PA_ORIG.items():
        setattr(scorers.price_authority, n, f)
cs = RealWeb3.to_checksum_address


class FakeHelpers:
    def __init__(self):
        self.calls = {}
        self.safes = {}

    def call_raw(self, w3, address, abi_fragment, function_name, *args, retries=4):
        return self.calls.get((cs(address) if address else address, function_name, args))

    def safe_owners_and_threshold(self, w3, address, retries=4):
        return self.safes.get(cs(address))

    def cross_checked(self, rpc_urls, fn, *args):
        return fn(FakeW3(), *args)


class FakeW3:
    @staticmethod
    def to_checksum_address(addr):
        return cs(addr)


def _patch(tc, fake):
    names = ["call_raw", "safe_owners_and_threshold", "cross_checked"]
    orig = {n: getattr(scorers, n) for n in names}
    for n in names:
        setattr(scorers, n, getattr(fake, n))
    tc.addCleanup(lambda: [setattr(scorers, n, orig[n]) for n in names])


def _owners(n, start=1):
    return [cs("0x" + hex(i)[2:].zfill(40)) for i in range(start, start + n)]


# ------------------------------------------------------------------ Compound V3
COMET = cs("0xc3d688B66703497DAA19211EEdff47f25384cdc3")
COMP_TL = cs("0x6d903f6003cca6255D85CcA4D3B5E5146dC33925")
COMP_GOV = cs("0x309a862bbC1A00e45506cB8A802D1ff10004c8C0")
COMP_PA = cs("0x1EC63B5883C3481134FD50D5DAebc83Ecd2E8779")
COMP_CFG = cs("0x316f9708bB98af7dA9c68C1C3b5e79039cD336E3")
COMP_GUARD = cs("0xbbf3f1421D886E9b2c5D716B5192aC998af2012c")


class TestCompoundV3(unittest.TestCase):
    def _fake(self):
        f = FakeHelpers()
        f.calls[(COMET, "governor", ())] = COMP_TL
        f.calls[(COMP_TL, "delay", ())] = 172800
        f.calls[(COMP_TL, "MINIMUM_DELAY", ())] = 172800
        f.calls[(COMP_TL, "admin", ())] = COMP_GOV
        f.calls[(COMP_GOV, "proposalCount", ())] = 608
        f.calls[(COMP_PA, "owner", ())] = COMP_TL
        f.calls[(COMP_CFG, "governor", ())] = COMP_TL
        f.calls[(COMET, "pauseGuardian", ())] = COMP_GUARD
        f.safes[COMP_GUARD] = (_owners(9), 5)
        return f

    def test_resolved(self):
        _patch(self, self._fake())
        r = scorers.score_compound_v3_cusdc(FakeW3())
        self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["timelockScore"], r["compositeScore"]), (78, 100, 60, 79))
        self.assertEqual(r["_rootGroup"], "compound-l1-governance")

    def test_pause_guardian_committee_shared_with_arbitrum_and_base_folds_cross_exposure(self):
        # ADDED 2026-09-20: the 9 owners equal the dated snapshot of the Arbitrum and Base pauseGuardian Safes.
        f = self._fake()
        f.safes[COMP_GUARD] = (sorted(cs(a) for a in scorers._KNOWN_COMPOUND_PAUSE_GUARDIAN_OWNERS_2026_09_20), 5)
        _patch(self, f)
        r = scorers.score_compound_v3_cusdc(FakeW3())
        self.assertTrue(r["_crossEcosystem"])
        self.assertEqual(r["compositeScore"], 79)  # the fold never moves the composite
        self.assertIn("IDENTICAL, as an exact set", " ".join(r["notes"]))

    def test_a_different_or_changed_guardian_committee_does_not_fold(self):
        f = self._fake()  # 9 unrelated fake owners
        _patch(self, f)
        self.assertFalse(scorers.score_compound_v3_cusdc(FakeW3())["_crossEcosystem"])
        owners = sorted(cs(a) for a in scorers._KNOWN_COMPOUND_PAUSE_GUARDIAN_OWNERS_2026_09_20)
        f.safes[COMP_GUARD] = (owners[:-1] + [cs("0x" + "cd" * 20)], 5)  # one rotated signer
        _patch(self, f)
        self.assertFalse(scorers.score_compound_v3_cusdc(FakeW3())["_crossEcosystem"])

    def test_unresolved_guardian_never_folds(self):
        f = self._fake()
        f.safes[COMP_GUARD] = None
        _patch(self, f)
        self.assertFalse(scorers.score_compound_v3_cusdc(FakeW3())["_crossEcosystem"])

    def test_snapshot_is_nine_lowercase_addresses(self):
        snap = scorers._KNOWN_COMPOUND_PAUSE_GUARDIAN_OWNERS_2026_09_20
        self.assertEqual(len(snap), 9)
        self.assertTrue(all(a == a.lower() and len(a) == 42 for a in snap))

    def test_proxy_admin_not_on_timelock_degrades(self):
        f = self._fake()
        f.calls[(COMP_PA, "owner", ())] = cs("0x" + "ee" * 20)
        _patch(self, f)
        r = scorers.score_compound_v3_cusdc(FakeW3())
        self.assertEqual(r["adminKeyScore"], 20)

    def test_short_delay_degrades_timelock(self):
        f = self._fake()
        f.calls[(COMP_TL, "delay", ())] = 3600
        _patch(self, f)
        r = scorers.score_compound_v3_cusdc(FakeW3())
        self.assertEqual(r["timelockScore"], 0)


# ------------------------------------------------------------------ SparkLend
SPK_PAP = cs("0x02C3eA4e34C0cBd694D2adFa2c690EECbC1793eE")
SPK_ACL = cs("0xdA135Cd78A086025BcdC87B038a1C462032b510C")
SPK_PROXY = cs("0x3300f198988e4C9C63F75dF86De36421f06af8c4")
PAUSE_PROXY = cs("0xBE8E3e3618f7474F8cB1d074A26afFef007E98FB")
MCD_PAUSE = cs("0xbE286431454714F511008713973d3B053A2d38f3")
FREEZER_MOM = cs("0x237e3985dD7E373F2ec878EC1Ac48A228Cf2e7a3")
FREEZER_MSIG = cs("0x44efFc473e81632B12486866AA1678edbb7BEeC3")


class TestSparkLend(unittest.TestCase):
    def _fake(self):
        f = FakeHelpers()
        f.calls[(SPK_PAP, "owner", ())] = SPK_PROXY
        f.calls[(SPK_ACL, "hasRole", (b"\x00" * 32, SPK_PROXY))] = True
        f.calls[(SPK_PROXY, "wards", (PAUSE_PROXY,))] = 1
        f.calls[(PAUSE_PROXY, "owner", ())] = MCD_PAUSE
        f.calls[(MCD_PAUSE, "delay", ())] = 172800
        f.calls[(FREEZER_MOM, "wards", (FREEZER_MSIG,))] = 1
        f.safes[FREEZER_MSIG] = (_owners(5), 3)
        return f

    def test_resolved(self):
        _patch(self, self._fake())
        r = scorers.score_sparklend_pool(FakeW3())
        self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["timelockScore"], r["compositeScore"]), (75, 100, 60, 78))
        self.assertEqual(r["_rootGroup"], "makerdao-sky-governance")

    def test_pause_proxy_not_ward_degrades(self):
        f = self._fake()
        f.calls[(SPK_PROXY, "wards", (PAUSE_PROXY,))] = 0
        _patch(self, f)
        self.assertEqual(scorers.score_sparklend_pool(FakeW3())["adminKeyScore"], 20)

    def test_delay_unread_degrades(self):
        f = self._fake()
        del f.calls[(MCD_PAUSE, "delay", ())]
        _patch(self, f)
        self.assertEqual(scorers.score_sparklend_pool(FakeW3())["timelockScore"], 0)


# ------------------------------------------------------------------ Uniswap V4
PM = cs("0x000000000004444c5dc75cB358380D2e3dE08A90")
UNI_TL = cs(scorers.UNISWAP_TIMELOCK)
UNI_GOV = cs("0x408ED6354d4973f66138C91495F2f2FCbd8724C3")
FEE_CTL = cs("0x89A5D5bF00a27D55c02951E49078a5C5771051dB")


class TestUniswapV4(unittest.TestCase):
    def _fake(self):
        f = FakeHelpers()
        f.calls[(PM, "owner", ())] = UNI_TL
        f.calls[(PM, "protocolFeeController", ())] = FEE_CTL
        f.calls[(FEE_CTL, "owner", ())] = UNI_TL
        f.calls[(FEE_CTL, "feeSetter", ())] = UNI_TL
        f.calls[(UNI_TL, "delay", ())] = 172800
        f.calls[(UNI_TL, "admin", ())] = UNI_GOV
        f.calls[(UNI_GOV, "quorumVotes", ())] = 40_000_000 * 10**18
        return f

    def test_resolved_matches_v3_convention(self):
        _patch(self, self._fake())
        r = scorers.score_uniswap_v4_pool_manager(FakeW3())
        self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["timelockScore"], r["compositeScore"]), (80, 100, 75, 85))
        self.assertEqual(r["_rootGroup"], "uniswap-l1-governance")

    def test_fee_setter_off_timelock_lowers_admin(self):
        f = self._fake()
        f.calls[(FEE_CTL, "feeSetter", ())] = cs("0x" + "ab" * 20)
        _patch(self, f)
        self.assertEqual(scorers.score_uniswap_v4_pool_manager(FakeW3())["adminKeyScore"], 60)

    def test_owner_not_timelock_degrades(self):
        f = self._fake()
        f.calls[(PM, "owner", ())] = cs("0x" + "cd" * 20)
        _patch(self, f)
        self.assertEqual(scorers.score_uniswap_v4_pool_manager(FakeW3())["adminKeyScore"], 20)


# ------------------------------------------------------------------ Morpho Blue
MORPHO = cs("0xBBBBBbbBBb9cC5e90e3b3Af64bdAF62C37EEFFCb")
MORPHO_SAFE = cs("0xcBa28b38103307Ec8dA98377ffF9816C164f9AFa")


class TestMorphoBlueL1(unittest.TestCase):
    def test_resolved_known_committee(self):
        f = FakeHelpers()
        f.calls[(MORPHO, "owner", ())] = MORPHO_SAFE
        f.safes[MORPHO_SAFE] = (sorted(scorers._KNOWN_MORPHO_COMMITTEE_2026_09_19), 5)
        _patch(self, f)
        r = scorers.score_morpho_blue_l1(FakeW3())
        self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["timelockScore"], r["compositeScore"]), (65, 95, 0, 55))
        self.assertTrue(any("IDENTICAL" in n for n in r["notes"]))

    def test_not_a_safe_degrades(self):
        f = FakeHelpers()
        f.calls[(MORPHO, "owner", ())] = MORPHO_SAFE
        _patch(self, f)
        r = scorers.score_morpho_blue_l1(FakeW3())
        self.assertEqual((r["adminKeyScore"], r["multisigScore"]), (20, 0))


# ------------------------------------------------------------------ WBTC
WBTC = cs("0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599")
WBTC_CTL = cs("0xCA06411bd7a7296d7dbdd0050DFc846E95fEBEB7")
WBTC_MSIG = cs("0x972Eed35781f09987a5c40F761f6A24623C570DE")


class TestWBTC(unittest.TestCase):
    def _fake(self):
        f = FakeHelpers()
        f.calls[(WBTC, "owner", ())] = WBTC_CTL
        f.calls[(WBTC_CTL, "token", ())] = WBTC
        f.calls[(WBTC_CTL, "owner", ())] = WBTC_MSIG
        f.calls[(WBTC_MSIG, "required", ())] = 6
        f.calls[(WBTC_MSIG, "getOwners", ())] = _owners(10)
        return f

    def test_resolved(self):
        _patch(self, self._fake())
        r = scorers.score_wbtc(FakeW3())
        self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["timelockScore"], r["compositeScore"]), (55, 100, 0, 52))

    def test_controller_token_mismatch_degrades(self):
        f = self._fake()
        f.calls[(WBTC_CTL, "token", ())] = cs("0x" + "12" * 20)
        _patch(self, f)
        r = scorers.score_wbtc(FakeW3())
        self.assertEqual((r["adminKeyScore"], r["multisigScore"]), (10, 20))


# ------------------------------------------------------------------ registry / grouping
class TestRegistryAndGroups(unittest.TestCase):
    def test_new_scorers_registered_once(self):
        names = [s.__name__ for s in scorers.SIMPLE_SCORERS]
        for n in ["score_compound_v3_cusdc", "score_sparklend_pool", "score_uniswap_v4_pool_manager", "score_morpho_blue_l1", "score_wbtc"]:
            self.assertEqual(names.count(n), 1, n)

    def test_v3_v4_and_maker_spark_share_groups(self):
        entries = [
            {"label": "V3", "notes": [], "_rootGroup": "uniswap-l1-governance"},
            {"label": "V4", "notes": [], "_rootGroup": "uniswap-l1-governance"},
            {"label": "Maker", "notes": [], "_rootGroup": "makerdao-sky-governance"},
            {"label": "Spark", "notes": [], "_rootGroup": "makerdao-sky-governance"},
            {"label": "Compound", "notes": [], "_rootGroup": "compound-l1-governance"},
        ]
        scorers._apply_cross_exposure(entries)
        self.assertEqual([e["crossExposureScore"] for e in entries], [80, 80, 80, 80, 100])


if __name__ == "__main__":
    unittest.main()
