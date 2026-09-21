"""
Unit tests for scripts/lib/layerzero_delegate_risk.py -- no live RPC, mocks
the web3 contract call.
"""
import os
import sys
import unittest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from lib.layerzero_delegate_risk import find_registered_oapps, get_oapp_delegate  # noqa: E402


def _mock_w3(delegate_by_address: dict):
    """A minimal fake w3 whose eth.contract(...).functions.delegates(addr).call()
    looks up `delegate_by_address`, defaulting to the zero address (LayerZero's
    own convention for "not registered")."""
    w3 = MagicMock()

    def fake_contract(address, abi):
        contract = MagicMock()

        def fake_delegates(addr):
            call_result = MagicMock()
            call_result.call.return_value = delegate_by_address.get(addr, "0x0000000000000000000000000000000000000000")
            return call_result

        contract.functions.delegates.side_effect = fake_delegates
        return contract

    w3.eth.contract.side_effect = fake_contract
    return w3


ADDR_A = "0x" + "1" * 40
ADDR_B = "0x" + "2" * 40
ENDPOINT = "0x" + "9" * 40


class TestGetOappDelegate(unittest.TestCase):
    def test_unregistered_address_returns_none(self):
        w3 = _mock_w3({})
        self.assertIsNone(get_oapp_delegate(w3, ENDPOINT, ADDR_A))

    def test_registered_address_returns_the_delegate(self):
        delegate = "0x" + "5" * 40
        w3 = _mock_w3({ADDR_A: delegate})
        self.assertEqual(get_oapp_delegate(w3, ENDPOINT, ADDR_A), delegate)

    def test_a_reverting_call_is_treated_as_unregistered_not_a_crash(self):
        w3 = MagicMock()
        w3.eth.contract.side_effect = Exception("execution reverted")
        self.assertIsNone(get_oapp_delegate(w3, ENDPOINT, ADDR_A))


class TestFindRegisteredOapps(unittest.TestCase):
    def test_no_candidates_registered_returns_empty(self):
        w3 = _mock_w3({})
        self.assertEqual(find_registered_oapps(w3, ENDPOINT, [ADDR_A, ADDR_B]), {})

    def test_only_registered_candidates_are_returned(self):
        delegate = "0x" + "5" * 40
        w3 = _mock_w3({ADDR_A: delegate})
        result = find_registered_oapps(w3, ENDPOINT, [ADDR_A, ADDR_B])
        self.assertEqual(result, {ADDR_A: delegate})

    def test_empty_candidate_list(self):
        w3 = _mock_w3({})
        self.assertEqual(find_registered_oapps(w3, ENDPOINT, []), {})


if __name__ == "__main__":
    unittest.main()
