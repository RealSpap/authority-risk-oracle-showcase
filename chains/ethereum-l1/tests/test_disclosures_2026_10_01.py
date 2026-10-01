"""Offline tests for the 2026-10-01 disclosures in chains/ethereum-l1/scorers.py (_disclose_role_holders): the success path,
and the rule that an empty replay, an unanswered hasRole or a crash is never read as "nobody holds the role". No network."""
import importlib.util
import os
import sys
import unittest
from unittest import mock

from web3 import Web3 as RealWeb3

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts", "lib"))


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, os.path.join(REPO_ROOT, rel))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


scorers = _load("aro_eth_l1_disclosures_2026_10_01", "chains/ethereum-l1/scorers.py")
GRANT = bytes(RealWeb3.keccak(text="RoleGranted(bytes32,address,address)"))
REVOKE = bytes(RealWeb3.keccak(text="RoleRevoked(bytes32,address,address)"))
ROLE = bytes(32)
A, B = "0x" + "aa" * 20, "0x" + "bb" * 20


def log(topic, who, block):
    return {"topics": [topic, ROLE, bytes(12) + bytes.fromhex(who[2:]), bytes(32)], "blockNumber": block, "logIndex": 0}


class FakeEth:
    def __init__(self, logs, block_number=1_000):
        self.block_number, self._logs = block_number, logs

    def get_logs(self, flt):
        return [l for l in self._logs if flt["fromBlock"] <= l["blockNumber"] <= flt["toBlock"]]


class FakeW3:
    def __init__(self, logs):
        self.eth = FakeEth(logs)


def run(logs, has_role):
    with mock.patch.object(scorers, "get_w3", lambda url: FakeW3(logs)), \
         mock.patch.object(scorers, "cross_checked", lambda rpcs, fn, who: has_role(RealWeb3.to_checksum_address(who))), \
         mock.patch.object(scorers, "_holder_kind", lambda a: "kind"):
        return scorers._disclose_role_holders("0x" + "cc" * 20, "Vault", ROLE, "DEFAULT_ADMIN_ROLE", 0, "power")


class TestDiscloseRoleHolders(unittest.TestCase):
    def test_holders_confirmed_live_revoked_dropped(self):
        note = run([log(GRANT, A, 10), log(GRANT, B, 20), log(REVOKE, B, 30)], lambda who: who == RealWeb3.to_checksum_address(A))
        self.assertIn(RealWeb3.to_checksum_address(A) + " (kind)", note)
        self.assertNotIn(RealWeb3.to_checksum_address(B), note)
        self.assertTrue(note.endswith("-- power"))

    def test_an_empty_replay_is_an_anomaly_not_nobody(self):
        note = run([], lambda who: True)
        self.assertIn("no event at all", note)
        self.assertNotIn("no holder confirmed live", note)

    def test_an_unanswered_hasrole_is_unread_not_no(self):
        note = run([log(GRANT, A, 10)], lambda who: None)
        self.assertIn("hasRole UNREAD", note)
        self.assertIn("no holder confirmed live", note)  # none confirmed, and it says why

    def test_a_crash_is_reported_not_raised(self):
        def boom(who):
            raise ValueError("decode")
        with mock.patch.object(scorers, "get_w3", lambda url: (_ for _ in ()).throw(ConnectionError("down"))):
            note = scorers._disclose_role_holders("0x" + "cc" * 20, "Vault", ROLE, "X", 0, "power")
        self.assertIn("FAILED", note)
        self.assertIn("UNREAD", run([log(GRANT, A, 10)], boom))


if __name__ == "__main__":
    unittest.main()
