"""
Unit tests for scripts/check_vault_v2_inventory.py's one-hop owner resolution (read_holder/_resolve_one).
Mocks web3_utils' module-level functions the same way check_vault_v2_inventory.py imports them --
no live RPC/API. fetch_vaults() (an HTTP call) is exercised live by the script itself, not here.
"""
import importlib.util
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts", "lib"))
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))

spec = importlib.util.spec_from_file_location("aro_test_check_vault_v2_inventory", os.path.join(REPO_ROOT, "scripts", "check_vault_v2_inventory.py"))
civ = importlib.util.module_from_spec(spec)
sys.modules["aro_test_check_vault_v2_inventory"] = civ
spec.loader.exec_module(civ)


class FakeEth:
    def __init__(self, code_by_addr):
        self._code_by_addr = code_by_addr

    def get_code(self, addr):
        if addr not in self._code_by_addr:
            raise LookupError(f"no fake code for {addr}")
        return self._code_by_addr[addr]


class FakeW3:
    def __init__(self, code_by_addr):
        self.eth = FakeEth(code_by_addr)

    @staticmethod
    def to_checksum_address(addr):
        return addr


VAULT_SUPERVISOR = "0x" + "a1" * 20
STEAKHOUSE_SAFE = "0x" + "a2" * 20
SUBPROXY = "0x" + "a3" * 20
BARE_EOA = "0x" + "a4" * 20
DIRECT_SAFE = "0x" + "a5" * 20
OTHER_CONTRACT = "0x" + "a6" * 20
UNKNOWN = "0x" + "a7" * 20


def _install_fakes(test_case, code_by_addr, owner_of, safes):
    """owner_of: {addr: owner_addr_or_None}. safes: {addr: (owners, threshold)} for resolvable Safes."""
    original_get_addr = civ.read_address_getter
    original_safe_fn = civ.safe_owners_and_threshold

    def fake_read_address_getter(w3, addr, fn_name, retries=4):
        assert fn_name == "owner"
        return owner_of.get(addr)

    def fake_safe_owners_and_threshold(w3, addr, retries=4):
        return safes.get(addr)

    civ.read_address_getter = fake_read_address_getter
    civ.safe_owners_and_threshold = fake_safe_owners_and_threshold
    test_case.addCleanup(lambda: setattr(civ, "read_address_getter", original_get_addr))
    test_case.addCleanup(lambda: setattr(civ, "safe_owners_and_threshold", original_safe_fn))
    return FakeW3(code_by_addr)


class TestReadHolder(unittest.TestCase):
    def test_not_set_address(self):
        w3 = _install_fakes(self, {}, {}, {})
        kind, detail = civ.read_holder(w3, None)
        self.assertEqual((kind, detail), ("unread", "not set"))
        kind, detail = civ.read_holder(w3, "0x" + "0" * 40)
        self.assertEqual((kind, detail), ("unread", "not set"))

    def test_bare_eoa_no_hop_needed(self):
        w3 = _install_fakes(self, {BARE_EOA: b""}, {}, {})
        kind, detail = civ.read_holder(w3, BARE_EOA)
        self.assertEqual(kind, "eoa")
        self.assertEqual(detail, "bare EOA")

    def test_direct_safe_no_hop_needed(self):
        w3 = _install_fakes(
            self, {DIRECT_SAFE: b"\x60\x80"}, {},
            {DIRECT_SAFE: (["a", "b", "c"], 2)},
        )
        kind, detail = civ.read_holder(w3, DIRECT_SAFE)
        self.assertEqual(kind, "safe")
        self.assertEqual(detail, "2-of-3 Safe")

    def test_supervisor_pattern_resolves_through_one_hop_to_a_safe(self):
        # The real 2026-09-25 finding: 6 Steakhouse V2 vaults' owner() is a VaultV2Supervisor
        # contract, itself owned by the already-known Steakhouse Safe.
        w3 = _install_fakes(
            self,
            {VAULT_SUPERVISOR: b"\x60\x80" * 100, STEAKHOUSE_SAFE: b"\x60\x80"},
            {VAULT_SUPERVISOR: STEAKHOUSE_SAFE},
            {STEAKHOUSE_SAFE: (["a", "b", "c", "d", "e"], 3)},
        )
        kind, detail = civ.read_holder(w3, VAULT_SUPERVISOR)
        self.assertEqual(kind, "safe")
        self.assertIn("3-of-5 Safe", detail)
        self.assertIn("via", detail)
        self.assertIn(VAULT_SUPERVISOR[:10], detail)

    def test_inner_hop_not_a_safe_is_reported_not_hidden(self):
        # The real 2026-09-25 finding: Sentora x Spark RLUSD's owner is a "SubProxy" whose own
        # owner() call fails outright (returns None) -- must not be silently treated as resolved.
        w3 = _install_fakes(
            self, {SUBPROXY: b"\x60\x80" * 50}, {SUBPROXY: None}, {},
        )
        kind, detail = civ.read_holder(w3, SUBPROXY)
        self.assertEqual(kind, "contract")
        self.assertIn("contract (not a Safe)", detail)

    def test_inner_hop_resolves_but_not_to_a_safe_is_disclosed(self):
        w3 = _install_fakes(
            self,
            {SUBPROXY: b"\x60\x80" * 50, OTHER_CONTRACT: b"\x60\x80" * 10},
            {SUBPROXY: OTHER_CONTRACT},
            {},  # OTHER_CONTRACT does not resolve as a Safe
        )
        kind, detail = civ.read_holder(w3, SUBPROXY)
        self.assertEqual(kind, "contract")
        self.assertIn("owner() ->", detail)
        self.assertIn(OTHER_CONTRACT[:10], detail)

    def test_get_code_failure_is_unread_not_a_crash(self):
        w3 = _install_fakes(self, {}, {}, {})  # no code registered -> FakeEth.get_code raises
        kind, detail = civ.read_holder(w3, UNKNOWN)
        self.assertEqual(kind, "unread")


if __name__ == "__main__":
    unittest.main()
