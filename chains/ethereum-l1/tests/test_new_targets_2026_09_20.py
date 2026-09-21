"""
Unit tests for the 4 Ethereum L1 targets added on 2026-09-20
(score_lido_steth, score_eigenlayer_strategy_manager,
score_curve_stableswap_ng_factory, score_rocketpool_storage): the resolved
branch and at least one degraded branch of each, plus the two traps this
pass actually fell into and fixed (HashConsensus.getMembers() returning TWO
arrays, and RocketStorage keys being keccak of the PACKED concatenation),
plus the check that the 4 new _rootGroup values leave every preexisting
target's crossExposureScore untouched.

Kept inside chains/ethereum-l1/ (not scripts/lib/tests/) so this ecosystem's
worker never edits shared repo-root files. Same FakeHelpers monkeypatch
approach as test_new_targets_2026_09_19.py, extended with the two helpers the
new scorers need (read_slot_as_address, is_eoa). No network, no RPC.

Run:  PYTHONPATH=. python3 -m unittest discover -s chains/ethereum-l1/tests -v
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


scorers = _load("aro_eth_l1_targets_2026_09_20", "chains/ethereum-l1/scorers.py")
cs = RealWeb3.to_checksum_address

# Live addresses, as read on 2026-09-20 on publicnode AND drpc.
STETH = cs("0xae7ab96520DE3A18E5e111B5EaAb095312D7fE84")
KERNEL = cs("0xb8FFC3Cd6e7Cf5a098A1c92F48009765B24088Dc")
ACL = cs("0x9895F0F17cc1d1891b6f18ee0b483B6f221b37Bb")
AGENT = cs("0x3e40D73EB977Dc6a537aF587D48316feE66E9C8c")
VOTING = cs("0x2e59A20f205bB85a89C53f1936454680651E618e")
DG_EXECUTOR = cs("0x23E0B465633FF5178808F4A75186E2F2F9537021")
DG_TIMELOCK = cs("0xCE0425301C85c5Ea2A0873A2dEe44d78E02D2316")
LOCATOR = cs("0xC1d0b3DE6792Bf6b4b37EccdcC24e45978Cfd2Eb")
ACCOUNTING_ORACLE = cs("0x852deD011285fe67063a08005c71a85690503Cee")
HASH_CONSENSUS = cs("0xD624B08C83bAECF0807Dd2c6880C3154a5F0B288")

EIGEN_SM = cs("0x858646372CC42E1A627fcE94aa7A7033e7CF075A")
EIGEN_PROXY_ADMIN = cs("0x8b9566AdA63B64d1E1dcF1418b43fd1433b72444")
EIGEN_EXECUTOR = cs("0x369e6F597e22EaB55fFb173C6d9cD234BD699111")
EIGEN_TIMELOCK = cs("0xC06Fd4F821eaC1fF1ae8067b36342899b57BAa2d")
EIGEN_COMMUNITY = cs("0xFEA47018D632A77bA579846c840d5706705Dc598")

CURVE_FACTORY = cs("0x6A8cbed756804B16E05E741eDaBd5cB544AE21bf")
CURVE_AGENT = cs("0x40907540d8a6C65c637785e8f8B742ae6b0b9968")
CURVE_KERNEL = cs("0xad06868167BC5Ac5cFcbEf2CAFa82bc76961D72d")
CURVE_ACL = cs("0xBd0697BA421e7fEc529E3E76D9e9F3a710490369")
CURVE_VOTING = cs("0xE478de485ad2fe566d49342Cbd03E49ed7DB3356")

ROCKET_STORAGE = cs("0x1d8f8f00cfa6758d7bE78336684788Fb0ee0Fa46")
ROCKET_GUARDIAN = cs("0x0cCF14983364A7735d369879603930Afe10df21e")
ROCKET_DAO = cs("0xCaC25e88276A333cF9d4196d112D93af67ef809A")
ZERO = "0x" + "0" * 40


class FakeHelpers:
    def __init__(self):
        self.calls = {}
        self.safes = {}
        self.slots = {}
        self.eoas = set()

    def call_raw(self, w3, address, abi_fragment, function_name, *args, retries=4):
        key = (cs(address) if address else address, function_name, args)
        return self.calls.get(key)

    def safe_owners_and_threshold(self, w3, address, retries=4):
        return self.safes.get(cs(address))

    def read_slot_as_address(self, w3, address, slot, retries=4):
        return self.slots.get((cs(address), slot))

    def is_eoa(self, w3, address):
        return cs(address) in self.eoas

    def cross_checked(self, rpc_urls, fn, *args):
        return fn(FakeW3(), *args)


class FakeW3:
    @staticmethod
    def to_checksum_address(addr):
        return cs(addr)


def _patch(tc, fake):
    names = ["call_raw", "safe_owners_and_threshold", "cross_checked", "read_slot_as_address", "is_eoa"]
    orig = {n: getattr(scorers, n) for n in names}
    for n in names:
        setattr(scorers, n, getattr(fake, n))
    tc.addCleanup(lambda: [setattr(scorers, n, orig[n]) for n in names])


def _owners(n, start=1):
    return [cs("0x" + hex(i)[2:].zfill(40)) for i in range(start, start + n)]


def _lido_fake(quorum=5, members=9, voting_has=False, dg_has=True,
               submit=259200, schedule=86400):
    f = FakeHelpers()
    f.calls[(STETH, "kernel", ())] = KERNEL
    f.calls[(KERNEL, "acl", ())] = ACL
    f.calls[(ACL, "getPermissionManager", (KERNEL, scorers._ARAGON_APP_MANAGER_ROLE))] = AGENT
    f.calls[(ACL, "hasPermission", (VOTING, AGENT, scorers._ARAGON_EXECUTE_ROLE))] = voting_has
    f.calls[(ACL, "hasPermission", (DG_EXECUTOR, AGENT, scorers._ARAGON_EXECUTE_ROLE))] = dg_has
    f.calls[(DG_EXECUTOR, "owner", ())] = DG_TIMELOCK
    f.calls[(DG_TIMELOCK, "getAfterSubmitDelay", ())] = submit
    f.calls[(DG_TIMELOCK, "getAfterScheduleDelay", ())] = schedule
    f.calls[(DG_TIMELOCK, "isEmergencyModeActive", ())] = False
    f.calls[(STETH, "getLidoLocator", ())] = LOCATOR
    f.calls[(LOCATOR, "accountingOracle", ())] = ACCOUNTING_ORACLE
    f.calls[(ACCOUNTING_ORACLE, "getConsensusContract", ())] = HASH_CONSENSUS
    f.calls[(HASH_CONSENSUS, "getQuorum", ())] = quorum
    # The real getMembers() returns TWO arrays. The fake must too.
    f.calls[(HASH_CONSENSUS, "getMembers", ())] = (_owners(members), [15256799] * members)
    return f


class TestLidoStETH(unittest.TestCase):
    def test_resolved_matches_live_2026_09_20(self):
        _patch(self, _lido_fake())
        r = scorers.score_lido_steth(FakeW3())
        self.assertEqual(r["target"], STETH)
        self.assertEqual(
            (r["adminKeyScore"], r["multisigScore"], r["timelockScore"],
             r["oracleAuthorityScore"], r["compositeScore"]),
            (80, 100, 60, 95, 80),
        )
        self.assertEqual(r["_rootGroup"], "lido-dual-governance-executor-0x23e0b465")

    def test_aragon_voting_no_longer_executes_is_recorded(self):
        """The load-bearing finding of this pass: the Aragon Voting app does NOT
        hold EXECUTE_ROLE on the Agent any more; the Dual Governance executor does."""
        _patch(self, _lido_fake())
        r = scorers.score_lido_steth(FakeW3())
        joined = " ".join(r["notes"])
        self.assertIn(f"Aragon Voting {VOTING}", joined)
        self.assertIn("EXECUTE_ROLE) = False", joined)
        self.assertIn(f"{DG_EXECUTOR}, Agent, EXECUTE_ROLE) = True", joined)

    def test_get_members_two_array_shape_is_handled(self):
        """Regression: reusing the single-array getOwners ABI here silently
        returned None on the first live dry-run and cost 75 oracle points."""
        _patch(self, _lido_fake(quorum=7, members=11))
        r = scorers.score_lido_steth(FakeW3())
        self.assertEqual(r["oracleAuthorityScore"], min(100, 7 * 15 + 4 * 5))

    def test_oracle_committee_unreadable_is_not_waved_through(self):
        f = _lido_fake()
        f.calls[(HASH_CONSENSUS, "getMembers", ())] = None
        _patch(self, f)
        r = scorers.score_lido_steth(FakeW3())
        self.assertEqual(r["oracleAuthorityScore"], 20)
        self.assertNotEqual(r["oracleAuthorityScore"], 100)

    def test_short_delay_does_not_earn_the_timelock_credit(self):
        _patch(self, _lido_fake(submit=3600, schedule=3600))
        r = scorers.score_lido_steth(FakeW3())
        self.assertEqual(r["timelockScore"], 0)

    def test_unresolved_execute_role_degrades(self):
        _patch(self, _lido_fake(dg_has=False))
        r = scorers.score_lido_steth(FakeW3())
        self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["timelockScore"]), (20, 0, 0))


def _eigen_fake(exec_threshold=1, community=(9, 13), min_delay=864000, owners=None):
    f = FakeHelpers()
    f.slots[(EIGEN_SM, scorers._EIP1967_ADMIN_SLOT)] = EIGEN_PROXY_ADMIN
    f.calls[(EIGEN_PROXY_ADMIN, "owner", ())] = EIGEN_EXECUTOR
    f.safes[EIGEN_EXECUTOR] = (owners if owners is not None else [EIGEN_TIMELOCK, EIGEN_COMMUNITY], exec_threshold)
    f.calls[(EIGEN_TIMELOCK, "getMinDelay", ())] = min_delay
    f.safes[EIGEN_COMMUNITY] = (_owners(community[1], start=100), community[0])
    return f


class TestEigenLayerStrategyManager(unittest.TestCase):
    def test_resolved_matches_live_2026_09_20(self):
        _patch(self, _eigen_fake())
        r = scorers.score_eigenlayer_strategy_manager(FakeW3())
        self.assertEqual(r["target"], EIGEN_SM)
        self.assertEqual(
            (r["adminKeyScore"], r["multisigScore"], r["timelockScore"], r["compositeScore"]),
            (60, 100, 20, 60),
        )

    def test_threshold_one_is_scored_on_the_bypass_not_the_timelock(self):
        _patch(self, _eigen_fake())
        r = scorers.score_eigenlayer_strategy_manager(FakeW3())
        self.assertEqual(r["timelockScore"], 20)
        self.assertIn("bypassable by the community Safe acting alone", " ".join(r["notes"]))

    def test_threshold_above_one_restores_the_timelock_credit(self):
        _patch(self, _eigen_fake(exec_threshold=2))
        r = scorers.score_eigenlayer_strategy_manager(FakeW3())
        self.assertEqual((r["adminKeyScore"], r["timelockScore"]), (70, 60))

    def test_owner_set_drift_degrades_rather_than_guesses(self):
        _patch(self, _eigen_fake(owners=[EIGEN_TIMELOCK, cs("0x" + "ab" * 20)]))
        r = scorers.score_eigenlayer_strategy_manager(FakeW3())
        self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["timelockScore"]), (20, 0, 0))
        self.assertIn("authority chain changed", " ".join(r["notes"]))

    def test_proxy_admin_unreadable_degrades(self):
        f = _eigen_fake()
        f.slots = {}
        _patch(self, f)
        r = scorers.score_eigenlayer_strategy_manager(FakeW3())
        self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["timelockScore"]), (20, 0, 0))


def _curve_fake(vote_time=604800, has=True, voting=CURVE_VOTING):
    f = FakeHelpers()
    f.calls[(CURVE_FACTORY, "admin", ())] = CURVE_AGENT
    f.calls[(CURVE_AGENT, "kernel", ())] = CURVE_KERNEL
    f.calls[(CURVE_KERNEL, "acl", ())] = CURVE_ACL
    f.calls[(CURVE_ACL, "getPermissionManager", (CURVE_AGENT, scorers._ARAGON_EXECUTE_ROLE))] = voting
    f.calls[(CURVE_ACL, "hasPermission", (voting, CURVE_AGENT, scorers._ARAGON_EXECUTE_ROLE))] = has
    f.calls[(cs(voting), "voteTime", ())] = vote_time
    f.calls[(cs(voting), "supportRequiredPct", ())] = 510000000000000000
    f.calls[(cs(voting), "minAcceptQuorumPct", ())] = 300000000000000000
    return f


class TestCurveStableswapNGFactory(unittest.TestCase):
    def test_resolved_matches_live_2026_09_20(self):
        _patch(self, _curve_fake())
        r = scorers.score_curve_stableswap_ng_factory(FakeW3())
        self.assertEqual(r["target"], CURVE_FACTORY)
        self.assertEqual(
            (r["adminKeyScore"], r["multisigScore"], r["timelockScore"], r["compositeScore"]),
            (78, 100, 65, 81),
        )

    def test_shorter_vote_period_lowers_the_delay_credit(self):
        _patch(self, _curve_fake(vote_time=3 * 86400))
        r = scorers.score_curve_stableswap_ng_factory(FakeW3())
        self.assertEqual(r["timelockScore"], 45)

    def test_zero_permission_manager_degrades(self):
        """Curve's Agent uses EXECUTE_ROLE, not RUN_SCRIPT_ROLE: reading the wrong
        role gives a zero-address manager, which must degrade, never crash."""
        _patch(self, _curve_fake(voting=ZERO))
        r = scorers.score_curve_stableswap_ng_factory(FakeW3())
        self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["timelockScore"]), (20, 0, 0))

    def test_voting_without_the_permission_degrades(self):
        _patch(self, _curve_fake(has=False))
        r = scorers.score_curve_stableswap_ng_factory(FakeW3())
        self.assertEqual(r["adminKeyScore"], 20)


def _rocket_fake(deployed=True, bootstrap_disabled=True, guardian=ROCKET_GUARDIAN, eoa=True):
    f = FakeHelpers()
    f.calls[(ROCKET_STORAGE, "getGuardian", ())] = guardian
    f.calls[(ROCKET_STORAGE, "getDeployedStatus", ())] = deployed
    f.calls[(ROCKET_STORAGE, "getAddress", (scorers._rocket_storage_key("rocketDAOProtocol"),))] = ROCKET_DAO
    f.calls[(ROCKET_DAO, "getBootstrapModeDisabled", ())] = bootstrap_disabled
    if eoa and guardian:
        f.eoas.add(cs(guardian))
    return f


class TestRocketPoolStorage(unittest.TestCase):
    def test_resolved_matches_live_2026_09_20(self):
        _patch(self, _rocket_fake())
        r = scorers.score_rocketpool_storage(FakeW3())
        self.assertEqual(r["target"], ROCKET_STORAGE)
        self.assertEqual(
            (r["adminKeyScore"], r["multisigScore"], r["timelockScore"], r["compositeScore"]),
            (55, 0, 0, 22),
        )

    def test_live_bootstrap_power_is_scored_as_a_bare_eoa_admin(self):
        """The attenuating context is what earns the 55. Remove it and the same
        EOA must fall to a bare-EOA score, not keep the benefit of the doubt."""
        _patch(self, _rocket_fake(bootstrap_disabled=False))
        r = scorers.score_rocketpool_storage(FakeW3())
        self.assertEqual(r["adminKeyScore"], 5)

    def test_not_yet_deployed_is_scored_as_a_bare_eoa_admin(self):
        _patch(self, _rocket_fake(deployed=False))
        r = scorers.score_rocketpool_storage(FakeW3())
        self.assertEqual(r["adminKeyScore"], 5)

    def test_contract_guardian_is_unknown_not_safe(self):
        _patch(self, _rocket_fake(guardian=cs("0x" + "cd" * 20), eoa=False))
        r = scorers.score_rocketpool_storage(FakeW3())
        self.assertEqual(r["adminKeyScore"], 20)

    def test_storage_key_is_packed_keccak(self):
        """abi.encode instead of encodePacked returns address(0) silently."""
        self.assertEqual(
            scorers._rocket_storage_key("rocketDAOProtocol").hex().removeprefix("0x"),
            "dd8392ea82afe5d437031f1c54f58ffdabbe6bd40476c61bf349c74639bc99bb",
        )


class TestRegistryAndCrossExposure(unittest.TestCase):
    NEW = [
        "score_lido_steth",
        "score_eigenlayer_strategy_manager",
        "score_curve_stableswap_ng_factory",
        "score_rocketpool_storage",
    ]

    def test_new_scorers_registered_exactly_once(self):
        names = [f.__name__ for f in scorers.SIMPLE_SCORERS]
        for n in self.NEW:
            self.assertEqual(names.count(n), 1, f"{n} registered {names.count(n)} time(s)")

    def test_new_root_groups_are_distinct_and_leave_existing_targets_untouched(self):
        """_apply_cross_exposure() groups by _rootGroup, so 4 brand-new groups must
        not move any preexisting crossExposureScore."""
        existing = [
            ("Uniswap V3", "uniswap-l1-governance", False),
            ("Uniswap V4", "uniswap-l1-governance", False),
            ("Aave V3", "aave-governance-l1", True),
            ("Maker/Sky", "makerdao-sky-governance", False),
            ("SparkLend", "makerdao-sky-governance", False),
            ("Ethena live", "ethena-safe-0x3b0aaf6e", False),
            ("USDtb PSM", "ethena-safe-0x3b0aaf6e", False),
            ("Morpho Blue", "morpho-association-safe", True),
            ("WBTC", "wbtc-multisigwallet-0x972eed35", False),
        ]
        new = [
            ("Lido", "lido-dual-governance-executor-0x23e0b465", False),
            ("EigenLayer", "eigenlayer-executor-multisig-0x369e6f59", False),
            ("Curve", "curve-dao-ownership-agent-0x40907540", False),
            ("Rocket Pool", "rocketpool-guardian-eoa-0x0ccf1498", False),
        ]

        def run(rows):
            res = [{"label": a, "notes": [], "_rootGroup": b, "_crossEcosystem": c} for a, b, c in rows]
            scorers._apply_cross_exposure(res)
            return {r["label"]: r["crossExposureScore"] for r in res}

        before = run(existing)
        after = run(existing + new)
        for label, value in before.items():
            self.assertEqual(after[label], value, f"{label} moved: {value} -> {after[label]}")
        for label, _, _ in new:
            self.assertEqual(after[label], 100, f"{label} should have no overlap")


if __name__ == "__main__":
    unittest.main()
