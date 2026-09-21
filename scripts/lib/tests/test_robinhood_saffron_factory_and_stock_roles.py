"""
Unit tests for the Robinhood Chain rotation audit of index 15 (2026-09-19):

  * `score_saffron_vault_factory()` -- new target. Owner of the Saffron Vaults
    factory is an EIP-7702-delegated EOA (`classify_account()` kind
    "eip7702_delegated", MetaMask EIP7702StatelessDeleGator), the first live
    7702 authority root on this chain. Same-key convention as
    `score_curve_dex()` (owner == feeReceiver -> 2), a 7702-delegated EOA
    counted as a bare EOA per METHODOLOGY.md.
  * the `signer_overlap` groups touched by that audit: `saffron_vault_factory`
    (new) and `stock_tokens` (13 known EOAs now, was 1).

Same monkeypatch approach as test_robinhood_simple_and_saferooted_scorers.py:
the two read primitives the scorer uses (`read_address_getter`,
`classify_account`) are replaced on the `scorers` module by name.
"""
import os
import sys
import unittest

from web3 import Web3 as RealWeb3

REPO_ROOT = os.path.join(os.path.dirname(__file__), "..", "..", "..")
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))
from lib import scorers, signer_overlap  # noqa: E402

FACTORY = "0xb24b143ad6bB5bE9559CcC75f34A2261b7456904"
OWNER = "0x58CA1eaED80896400122164Abe16d77B2b4ff7c9"
DELEGATE = "0x63c0c19a282a1B52b07dD5a65b58948A07DAE32B"
OTHER = RealWeb3.to_checksum_address("0x" + "bb" * 20)
ZERO = RealWeb3.to_checksum_address("0x" + "00" * 20)


class FakeW3:
    pass


class FakeReads:
    def __init__(self):
        self.getters = {}          # (address, function_name) -> address-or-None
        self.classification = {}   # address -> {"kind": ..., "delegate": ...}

    def read_address_getter(self, w3, address, function_name, retries=4):
        return self.getters.get((address, function_name))

    def classify_account(self, w3, address):
        return self.classification.get(address, {"kind": "contract", "delegate": None})


_PATCHED = ["read_address_getter", "classify_account"]


def _patch(test_case, fake):
    originals = {n: getattr(scorers, n) for n in _PATCHED}
    for n in _PATCHED:
        setattr(scorers, n, getattr(fake, n))
    test_case.addCleanup(lambda: [setattr(scorers, n, originals[n]) for n in _PATCHED])


class TestScoreSaffronVaultFactory(unittest.TestCase):
    def _fake(self, owner=OWNER, fee_receiver=OWNER, pending=None, kind="eip7702_delegated", delegate=DELEGATE):
        fake = FakeReads()
        fake.getters[(FACTORY, "owner")] = owner
        fake.getters[(FACTORY, "feeReceiver")] = fee_receiver
        fake.getters[(FACTORY, "pendingOwner")] = pending
        if owner:
            fake.classification[owner] = {"kind": kind, "delegate": delegate if kind == "eip7702_delegated" else None}
        return fake

    def test_7702_delegated_owner_same_as_fee_receiver_scores_2(self):
        # The real live shape found 2026-09-19: owner() == feeReceiver(), both
        # the 7702-delegated EOA. Treated like a bare EOA, same-key -> 2.
        _patch(self, self._fake())
        result = scorers.score_saffron_vault_factory(FakeW3())
        self.assertEqual(
            (result["adminKeyScore"], result["multisigScore"], result["timelockScore"], result["oracleAuthorityScore"]),
            (2, 0, 0, 100),
        )
        self.assertEqual(result["compositeScore"], scorers._composite(2, 0, 0))
        self.assertEqual(result["compositeScore"], 1)
        self.assertEqual(result["target"], FACTORY)
        self.assertEqual(result["label"], "Saffron Vaults factory (Robinhood Chain)")
        self.assertTrue(any("eip7702_delegated" in n and DELEGATE in n for n in result["notes"]))
        self.assertTrue(any("owner() == feeReceiver(): True" in n for n in result["notes"]))

    def test_bare_eoa_owner_same_as_fee_receiver_scores_2(self):
        _patch(self, self._fake(kind="bare_eoa"))
        result = scorers.score_saffron_vault_factory(FakeW3())
        self.assertEqual(result["adminKeyScore"], 2)

    def test_owner_and_fee_receiver_differ_scores_lone_eoa_5(self):
        _patch(self, self._fake(fee_receiver=OTHER))
        result = scorers.score_saffron_vault_factory(FakeW3())
        self.assertEqual(result["adminKeyScore"], 5)
        self.assertEqual(result["compositeScore"], scorers._composite(5, 0, 0))
        self.assertTrue(any("owner() == feeReceiver(): False" in n for n in result["notes"]))

    def test_owner_turned_into_a_real_contract_scores_40_with_warning(self):
        # e.g. ownership moved to a Safe: the default must NOT keep the
        # confident 2, it must fall to the conservative branch and say so.
        _patch(self, self._fake(kind="contract"))
        result = scorers.score_saffron_vault_factory(FakeW3())
        self.assertEqual(result["adminKeyScore"], 40)
        self.assertTrue(any(n.startswith("WARNING") for n in result["notes"]))

    def test_unresolved_owner_degrades_without_crashing(self):
        fake = FakeReads()  # every getter returns None
        _patch(self, fake)
        result = scorers.score_saffron_vault_factory(FakeW3())  # must not raise
        self.assertEqual(result["adminKeyScore"], 40)
        self.assertTrue(any(n.startswith("WARNING") for n in result["notes"]))

    def test_pending_owner_is_surfaced_in_notes(self):
        _patch(self, self._fake(pending=OTHER))
        result = scorers.score_saffron_vault_factory(FakeW3())
        self.assertTrue(any(f"pendingOwner() = {OTHER}" in n for n in result["notes"]))

    def test_scorer_is_wired_into_simple_scorers(self):
        self.assertIn(scorers.score_saffron_vault_factory, scorers.SIMPLE_SCORERS)


class TestSignerOverlapGroupsFromIndex15(unittest.TestCase):
    STOCK_EOAS = [
        "0xD6f8378F8e440c65F8382F5f2728c78DfD55B66d",  # DEFAULT_ADMIN_ROLE root
        "0xCd8C6182e7C6Ca3B5156D6a90a67719d7e2Be094",  # BEACON_UPGRADER_ROLE
        "0x2b94105fFf37630f98e1f24811daD588FC5C3A87",  # MINTER_ROLE
        "0x6E40B50A40C1db42A85a0E8fe8FF7d9CbFc2D8C1",  # BURNER_ROLE
        "0x957B6de6525C63349f7619743Ef1E0ad93cd74D4",
        "0xe7BCB188254Bc6eBBfF63014DfED4cD4A024F22A",  # PAUSER_ROLE
        "0xFCcF56B674113d9C4eb0F9B3370930ceD9E6Ab23",  # TOKEN_PAUSER_ROLE
        "0x7369d100c00F28E45D779ac9d4b1c7afa61e4aBC",
        "0x5516B3451d4d6C9f63353Fe7Bc9537477ECCE000",
        "0x697e774d60c1a3769f2eD0b919AAcf17be0ae553",
        "0x92905e8d0e2301BA143215B8D86D63fFD4188143",
        "0xcba16C2b9048AF033c5b34E43dd1D47D1358524A",
        "0x913cA87347391218e5De2C17c5A0AEba8B0b28fD",  # BLOCKER_ROLE
    ]

    def test_stock_tokens_group_lists_all_13_beacon_role_holders(self):
        got = {RealWeb3.to_checksum_address(a) for a in signer_overlap.GROUPS["stock_tokens"]["known_eoa"]}
        self.assertEqual(got, {RealWeb3.to_checksum_address(a) for a in self.STOCK_EOAS})
        self.assertEqual(len(signer_overlap.GROUPS["stock_tokens"]["known_eoa"]), 13)  # no duplicates

    def test_every_listed_address_is_a_valid_checksum(self):
        # A mistyped hex digit would silently make an address match nothing.
        for a in self.STOCK_EOAS + [OWNER, FACTORY]:
            self.assertEqual(a, RealWeb3.to_checksum_address(a), a)

    def test_saffron_group_exists_with_owner_and_factory(self):
        g = signer_overlap.GROUPS["saffron_vault_factory"]
        self.assertEqual(g["targets"], [FACTORY])
        self.assertEqual(g["known_eoa"], [OWNER])
        self.assertEqual(g["safes"], [])

    def test_new_addresses_belong_to_exactly_one_group(self):
        # The point of listing them is to catch a FUTURE overlap; today none of
        # them may already be shared with a different group (that would change
        # a published crossExposureScore and must be looked at, not absorbed).
        for addr in self.STOCK_EOAS + [OWNER]:
            groups = [
                key for key, g in signer_overlap.GROUPS.items()
                if addr.lower() in {a.lower() for a in g.get("known_eoa", [])}
            ]
            self.assertEqual(len(groups), 1, f"{addr} appears in groups {groups}")


if __name__ == "__main__":
    unittest.main()
