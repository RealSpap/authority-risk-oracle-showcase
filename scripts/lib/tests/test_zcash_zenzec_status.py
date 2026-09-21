"""
Unit tests for `chains/zcash/scripts/zenzec_status_check.py` (the read-only zenZEC status check).

No network: the Solana reads go through an injected fake `rpc`. What is pinned: that the authority chain is
parsed from the account shapes Solana really returns (jsonParsed multisig, program-owned signer, upgradeable
program with a ProgramData account), and that each reversal trigger of
`chains/zcash/data/zenzec_status_2026-09-20.md` fires when, and only when, its condition changes.
"""
import importlib.util
import os
import sys
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
SCRIPTS = os.path.join(REPO_ROOT, "chains/zcash/scripts")
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)

spec = importlib.util.spec_from_file_location("aro_test_zenzec_status", os.path.join(SCRIPTS, "zenzec_status_check.py"))
zs = importlib.util.module_from_spec(spec)
sys.modules["aro_test_zenzec_status"] = zs
spec.loader.exec_module(zs)

B = zs.BASELINE
PROGDATA = "9qMAjSE2VkiRoZbZhYZDSj4HJbgxJ8x6uiqANLhh2ung"


def fake_rpc_factory(overrides=None):
    o = overrides or {}

    def rpc(method, params, **_):
        acct = params[0]
        if method == "getAccountInfo":
            if acct == zs.MINT:
                return {"value": {"data": {"parsed": {"info": {"supply": o.get("supply", B["supply_raw"]),
                                                                "mintAuthority": B["mint_authority"], "freezeAuthority": None}}}}}
            if acct == B["mint_authority"]:
                return {"value": {"data": {"parsed": {"type": "multisig", "info": {
                    "numRequiredSigners": 1, "numValidSigners": 1, "signers": [B["signer"]]}}}}}
            if acct == B["signer"]:
                return {"value": {"owner": B["program"], "data": ["", "base64"]}}
            if acct == B["program"]:
                return {"value": {"data": {"parsed": {"type": "program", "info": {"programData": PROGDATA}}}}}
            if acct == PROGDATA:
                return {"value": {"data": {"parsed": {"type": "programData", "info": {
                    "authority": B["upgrade_authority"], "slot": o.get("slot", B["deploy_slot"])}}}}}
        if method == "getSignaturesForAddress":
            if acct == B["mint_authority"]:
                return [{"blockTime": o.get("multisig_ts", 1785931111)}]   # 2026-08-05T11:58:31Z, the last real one
            return [{"blockTime": 1789082062}]                               # 2026-09-10T23:14:22Z
        raise AssertionError((method, params))
    return rpc


def _load_scorers():
    spec2 = importlib.util.spec_from_file_location("aro_test_zenzec_scorers", os.path.join(REPO_ROOT, "chains/zcash/scorers.py"))
    m = importlib.util.module_from_spec(spec2)
    sys.modules["aro_test_zenzec_scorers"] = m
    spec2.loader.exec_module(m)
    return m


class TestScorerStatusFlag(unittest.TestCase):
    """The scorer marks target 7 as a frozen snapshot, and asks for a re-read once the node moves."""

    def _score(self, height):
        sc = _load_scorers()
        kr = {"height": height, "party_threshold": 3, "parties": ["a", "b", "c"], "description": "Zenrock MPC",
              "is_active": True, "admins": ["x"]}
        sc.zr.get_keyring = lambda addr: kr
        def no_key(_kid):
            raise RuntimeError("offline")
        sc.zr.get_key_by_id = no_key
        return sc.score_zenzec_mpc_keyring()

    def test_frozen_height_flags_the_snapshot_without_changing_the_score(self):
        r = self._score(9_534_552)
        self.assertEqual((r["status"], r["asOf"]), ("frozen_snapshot", "2026-08-10T23:19:52Z"))
        self.assertTrue(r["notes"][0].startswith("STATUS: FROZEN SNAPSHOT"))
        self.assertEqual(r["compositeScore"], 44)

    def test_an_advanced_node_height_asks_for_a_human_re_read(self):
        r = self._score(9_600_000)
        self.assertEqual((r["status"], r["asOf"]), ("status_review_needed", None))
        self.assertTrue(r["notes"][0].startswith("STATUS FLAG NEEDS REVIEW"))
        self.assertEqual(r["compositeScore"], 44)   # the score itself is a function of (k, n) only

    def test_the_new_fields_do_not_enter_the_anchored_commitment(self):
        import attest_scores as at
        r = self._score(9_534_552)
        rec = at.canonical_record(r)
        self.assertNotIn("status", rec)
        self.assertNotIn("notes", rec)


class TestReadSolana(unittest.TestCase):
    def test_authority_chain_is_parsed_from_real_account_shapes(self):
        sol = zs.read_solana(rpc=fake_rpc_factory())
        for k in ("supply_raw", "mint_authority", "freeze_authority", "multisig", "signer", "program", "upgrade_authority", "deploy_slot"):
            self.assertEqual(sol[k], B[k], k)
        self.assertRegex(sol["upgrade_key_latest_tx"], r"^2026-09-\d\dT")


class TestTriggers(unittest.TestCase):
    def setUp(self):
        self.sol = zs.read_solana(rpc=fake_rpc_factory())
        self.backing = [B["backing_zat"], B["backing_zat"]]

    def fired(self, sol=None, backing=None, height=B["zrchain_height"]):
        return zs.triggers(sol or self.sol, self.backing if backing is None else backing, height)

    def test_baseline_fires_nothing(self):
        self.assertEqual(self.fired(), [])

    def test_each_condition_fires_exactly_its_own_trigger(self):
        cases = {
            "deploy_slot changed": dict(sol={**self.sol, "deploy_slot": 383091029}),
            "supply_raw changed": dict(sol={**self.sol, "supply_raw": "49451437136"}),
            "upgrade_authority changed": dict(sol={**self.sol, "upgrade_authority": "SomeoneElse"}),
            "multisig changed": dict(sol={**self.sol, "multisig": (2, 3)}),
            "backing address balance changed": dict(backing=[B["backing_zat"] - 1, B["backing_zat"] - 1]),
            "ZEC hosts disagree": dict(backing=[B["backing_zat"], 0]),
            "zrchain tip advanced": dict(height=B["zrchain_height"] + 1),
            "after 2026-08-06": dict(sol={**self.sol, "last_multisig_activity": "2026-09-01T00:00:00Z"}),
        }
        for needle, kwargs in cases.items():
            got = self.fired(**kwargs)
            self.assertEqual(len(got), 1, (needle, got))
            self.assertIn(needle, got[0])

    def test_unreachable_zrchain_is_not_a_trigger(self):
        self.assertEqual(zs.triggers(self.sol, self.backing, None), [])


if __name__ == "__main__":
    unittest.main()
