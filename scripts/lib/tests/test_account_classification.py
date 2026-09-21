"""
Unit tests for scripts/lib/account_classification.py -- no live RPC, mocks
w3.eth.get_code / w3.eth.contract.
"""
import os
import sys
import unittest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from lib.account_classification import check_self_escalation_risk, classify_account  # noqa: E402


ADDR = "0x" + "1" * 40


def _mock_w3_with_code(code: bytes):
    w3 = MagicMock()
    w3.eth.get_code.return_value = code
    return w3


class TestClassifyAccount(unittest.TestCase):
    def test_empty_code_is_bare_eoa(self):
        w3 = _mock_w3_with_code(b"")
        result = classify_account(w3, ADDR)
        self.assertEqual(result["kind"], "bare_eoa")
        self.assertIsNone(result["delegate"])

    def test_eip7702_prefix_is_delegated(self):
        # 0xef0100 followed by a 20-byte delegate address = exactly 23 bytes,
        # EIP-7702's exact on-chain shape.
        delegate_addr = bytes.fromhex("2" * 40)
        code = bytes.fromhex("ef0100") + delegate_addr
        w3 = _mock_w3_with_code(code)
        result = classify_account(w3, ADDR)
        self.assertEqual(result["kind"], "eip7702_delegated")
        self.assertEqual(result["delegate"].lower(), "0x" + delegate_addr.hex())

    def test_a_real_contract_is_not_misclassified_as_delegated(self):
        # Ordinary deployed bytecode, longer than 23 bytes and not starting
        # with the 7702 prefix.
        w3 = _mock_w3_with_code(b"\x60\x80\x60\x40" * 50)
        result = classify_account(w3, ADDR)
        self.assertEqual(result["kind"], "contract")
        self.assertIsNone(result["delegate"])

    def test_23_bytes_without_the_7702_prefix_is_not_misclassified(self):
        # Same length as a 7702 delegation, but the wrong prefix -- must not
        # be treated as a delegation just because the length matches.
        code = bytes.fromhex("aa0100") + bytes.fromhex("3" * 40)
        w3 = _mock_w3_with_code(code)
        result = classify_account(w3, ADDR)
        self.assertEqual(result["kind"], "contract")


class TestCheckSelfEscalationRisk(unittest.TestCase):
    def _mock_w3_role_admin(self, role_admin: bytes):
        w3 = MagicMock()
        contract = MagicMock()
        contract.functions.getRoleAdmin.return_value.call.return_value = role_admin
        w3.eth.contract.return_value = contract
        return w3

    def test_self_administering_role_is_flagged(self):
        role = b"\x01" * 32
        w3 = self._mock_w3_role_admin(role_admin=role)  # getRoleAdmin(role) == role
        result = check_self_escalation_risk(w3, ADDR, role)
        self.assertTrue(result["checked"])
        self.assertTrue(result["self_administering"])

    def test_normal_default_admin_gated_role_is_not_flagged(self):
        role = b"\x01" * 32
        default_admin_role = b"\x00" * 32
        w3 = self._mock_w3_role_admin(role_admin=default_admin_role)
        result = check_self_escalation_risk(w3, ADDR, role)
        self.assertTrue(result["checked"])
        self.assertFalse(result["self_administering"])

    def test_reverting_call_means_not_checked_not_assumed_safe(self):
        w3 = MagicMock()
        w3.eth.contract.side_effect = Exception("execution reverted")
        result = check_self_escalation_risk(w3, ADDR, b"\x01" * 32)
        self.assertFalse(result["checked"])
        self.assertIsNone(result["self_administering"])


if __name__ == "__main__":
    unittest.main()
