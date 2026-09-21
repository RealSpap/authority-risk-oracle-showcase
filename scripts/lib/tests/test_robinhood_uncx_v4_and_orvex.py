"""
Unit tests for the four targets added by the Robinhood Chain rotation audit of
index 16 (2026-09-20):

  * `score_uncx_v4_locker()` -- resolves a lead left open across indexes 8,
    13, 14 and 15. Same 2-of-3 Safe root as the already-tracked V3 locker,
    so the same 50/35/0 (composite 31).
  * `score_orvex_v2_pair_factory()` -- SPLIT ROOT: a bare-EOA operational
    owner and a 3-of-7-Safe-owned ProxyAdmin. Deliberate, documented
    deviation from `score_alandale_v3_factory()`'s "score the upgrade
    authority" convention: the WEAKER root is scored, so this must come out
    5/0/0 and NOT 65/65/0.
  * `score_orvex_v4_pool_manager()` -- plain Safe-rooted, 65/65/0.
  * `score_orvex_v4_vault()` -- bare EOA with a PRINCIPAL-MOVING owner power
    (`registerApp`), so 2/0/0, not the fee-only 5/0/0; and an Ownable2Step
    transfer to the Safe that is OFFERED but not accepted, which must not
    move the score.
  * the `signer_overlap` groups touched: `uncx_v3_locker` (2 targets now,
    was 1) and `orvex` (new).

Same monkeypatch approach as test_robinhood_simple_and_saferooted_scorers.py:
the read primitives are replaced on the `scorers` module by name, so no test
here touches the network.
"""
import os
import sys
import unittest

from web3 import Web3 as RealWeb3

REPO_ROOT = os.path.join(os.path.dirname(__file__), "..", "..", "..")
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))
from lib import scorers, signer_overlap  # noqa: E402

UNCX_V4 = "0x128A800cBc615cc110Bff16E475865c67631603A"
UNCX_V4_NFPM = "0x58daec3116aae6D93017bAAea7749052E8a04fA7"
UNCX_SAFE = "0x31c44A17aa2E639B40f33DA805CB1DB55d969693"
UNCX_V3 = "0xF28704c691290547924e2129D407dA36bda8ce0f"

ORVEX_V2 = "0x5c98b2d892b37c9a1D3b69472bdDc172A64CdC09"
ORVEX_POOLMGR = "0xd01C774d4A66408326Bc65728Ac5Ae5aAf004032"
ORVEX_VAULT = "0xFe7E25dE55e5cBbEcCcb661F3679F873f72B9b0D"
ORVEX_EOA = "0x3b2b572C56dD96B351ceB95c53e7EdB97BF42F14"
ORVEX_PROXY_ADMIN = "0x2DFa221c78f19891F843811345E28ac4289B0006"
ORVEX_SAFE = "0x9DB42D3BDA1525963db3B2372C4DAABaf0491A53"

ZERO = "0x" + "00" * 40
OTHER = RealWeb3.to_checksum_address("0x" + "bb" * 20)


class FakeW3:
    pass


class FakeHelpers:
    def __init__(self):
        self.address_getters = {}
        self.slot_results = {}
        self.safe_results = {}
        self.call_raw_results = {}
        self.classification = {}

    def read_address_getter(self, w3, address, function_name, retries=4):
        return self.address_getters.get((address, function_name))

    def read_slot_as_address(self, w3, address, slot, retries=4):
        return self.slot_results.get((address, slot))

    def safe_owners_and_threshold(self, w3, address, retries=4):
        return self.safe_results.get(address)

    def call_raw(self, w3, address, abi_fragment, function_name, *args, retries=4):
        return self.call_raw_results.get((address, function_name, args))

    def classify_account(self, w3, address):
        return self.classification.get(address, {"kind": "contract", "delegate": None})


_PATCHED = [
    "read_address_getter", "read_slot_as_address", "safe_owners_and_threshold",
    "call_raw", "classify_account",
]


def _patch(test_case, fake):
    originals = {n: getattr(scorers, n) for n in _PATCHED}
    for n in _PATCHED:
        setattr(scorers, n, getattr(fake, n))
    test_case.addCleanup(lambda: [setattr(scorers, n, originals[n]) for n in _PATCHED])


def _clean_safe(fake, safe, owners, threshold):
    """A Safe that resolves, with no module and a zero guard -- the shape
    _safe_rooted_entry() needs in order NOT to append its warning."""
    fake.safe_results[safe] = (owners, threshold)
    fake.call_raw_results[(safe, "getModulesPaginated",
                           ("0x0000000000000000000000000000000000000001", 10))] = ([], ZERO)
    fake.slot_results[(safe, "0x4a204f620c8c5ccdca3fd54d003badd85ba500436a431f0cbda4f558c93c34c8")] = None


class TestUncxV4Locker(unittest.TestCase):
    def _fake(self, owner=UNCX_SAFE, nfpm=UNCX_V4_NFPM, migrator=ZERO, threshold=2, n_owners=3):
        fake = FakeHelpers()
        fake.address_getters[(UNCX_V4, "owner")] = owner
        fake.address_getters[(UNCX_V4, "positionManager")] = nfpm
        fake.address_getters[(UNCX_V4, "MIGRATOR")] = migrator
        _clean_safe(fake, owner, [RealWeb3.to_checksum_address("0x" + f"{i:02x}" * 20)
                                  for i in range(1, n_owners + 1)], threshold)
        return fake

    def test_two_of_three_safe_root_scores_like_the_published_v3_locker(self):
        fake = self._fake()
        _patch(self, fake)
        e = scorers.score_uncx_v4_locker(FakeW3())
        self.assertEqual(e["target"], UNCX_V4)
        self.assertEqual(
            (e["adminKeyScore"], e["multisigScore"], e["timelockScore"], e["oracleAuthorityScore"]),
            (50, 35, 0, 100),
        )
        # floor(0.4*50 + 0.3*35 + 0.3*0 + 0.5) = 31, the value the already
        # published UNCX V3 locker carries on the testnet oracle.
        self.assertEqual(e["compositeScore"], 31)

    def test_position_manager_matching_the_defillama_adapter_is_asserted_not_assumed(self):
        fake = self._fake()
        _patch(self, fake)
        notes = " ".join(scorers.score_uncx_v4_locker(FakeW3())["notes"])
        self.assertIn("primary source confirmed by the contract itself: True", notes)
        self.assertNotIn("WARNING", notes)

    def test_position_manager_drifting_off_the_adapter_raises_a_warning(self):
        fake = self._fake(nfpm=OTHER)
        _patch(self, fake)
        notes = " ".join(scorers.score_uncx_v4_locker(FakeW3())["notes"])
        self.assertIn("WARNING", notes)
        self.assertIn("no longer points at the position manager", notes)

    def test_migrator_is_reported_so_an_armed_migrate_path_is_visible_next_pass(self):
        fake = self._fake(migrator=OTHER)
        _patch(self, fake)
        notes = " ".join(scorers.score_uncx_v4_locker(FakeW3())["notes"])
        self.assertIn(f"MIGRATOR() = {OTHER}", notes)

    def test_threshold_three_would_score_higher_so_the_score_tracks_the_live_safe(self):
        fake = self._fake(threshold=3, n_owners=5)
        _patch(self, fake)
        e = scorers.score_uncx_v4_locker(FakeW3())
        self.assertEqual((e["adminKeyScore"], e["multisigScore"]), (65, 55))

    def test_unresolvable_owner_degrades_conservatively_instead_of_crashing(self):
        fake = FakeHelpers()
        fake.address_getters[(UNCX_V4, "owner")] = None
        fake.address_getters[(UNCX_V4, "positionManager")] = UNCX_V4_NFPM
        fake.address_getters[(UNCX_V4, "MIGRATOR")] = ZERO
        _patch(self, fake)
        e = scorers.score_uncx_v4_locker(FakeW3())
        self.assertEqual((e["adminKeyScore"], e["multisigScore"], e["timelockScore"]), (20, 0, 0))


class TestOrvexV2PairFactory(unittest.TestCase):
    def _fake(self, owner=ORVEX_EOA, kind="bare_eoa", pa=ORVEX_PROXY_ADMIN, pa_owner=ORVEX_SAFE):
        fake = FakeHelpers()
        fake.address_getters[(ORVEX_V2, "owner")] = owner
        fake.slot_results[(ORVEX_V2, scorers.EIP1967_ADMIN_SLOT)] = pa
        if pa:
            fake.address_getters[(pa, "owner")] = pa_owner
        if owner:
            fake.classification[owner] = {"kind": kind, "delegate": None}
        return fake

    def test_split_root_is_scored_on_the_bare_eoa_not_on_the_safe(self):
        fake = self._fake()
        _patch(self, fake)
        e = scorers.score_orvex_v2_pair_factory(FakeW3())
        self.assertEqual(
            (e["adminKeyScore"], e["multisigScore"], e["timelockScore"], e["compositeScore"]),
            (5, 0, 0, 2),
        )
        # The regression this test exists for: _safe_rooted_entry() would have
        # produced 65/65/0 (composite 46) off the 3-of-7 ProxyAdmin owner.
        self.assertNotEqual(e["adminKeyScore"], 65)

    def test_split_root_is_stated_in_the_notes(self):
        fake = self._fake()
        _patch(self, fake)
        notes = " ".join(scorers.score_orvex_v2_pair_factory(FakeW3())["notes"])
        self.assertIn("SPLIT ROOT", notes)
        self.assertIn(ORVEX_SAFE, notes)

    def test_no_split_root_note_when_the_two_roots_coincide(self):
        fake = self._fake(pa_owner=ORVEX_EOA)
        _patch(self, fake)
        notes = " ".join(scorers.score_orvex_v2_pair_factory(FakeW3())["notes"])
        self.assertNotIn("SPLIT ROOT", notes)

    def test_eip7702_delegated_owner_is_still_one_key(self):
        fake = self._fake(kind="eip7702_delegated")
        _patch(self, fake)
        self.assertEqual(scorers.score_orvex_v2_pair_factory(FakeW3())["adminKeyScore"], 5)

    def test_owner_becoming_a_contract_warns_and_degrades(self):
        fake = self._fake(kind="contract")
        _patch(self, fake)
        e = scorers.score_orvex_v2_pair_factory(FakeW3())
        self.assertEqual(e["adminKeyScore"], 40)
        self.assertIn("WARNING", " ".join(e["notes"]))

    def test_unresolved_owner_warns_and_degrades(self):
        fake = self._fake(owner=None)
        _patch(self, fake)
        e = scorers.score_orvex_v2_pair_factory(FakeW3())
        self.assertEqual(e["adminKeyScore"], 40)
        self.assertIn("unresolved", " ".join(e["notes"]).lower())

    def test_tvl_preamble_states_the_chain_specific_figure_and_the_usar_check(self):
        fake = self._fake()
        _patch(self, fake)
        notes = " ".join(scorers.score_orvex_v2_pair_factory(FakeW3())["notes"])
        self.assertIn("389,945", notes)
        self.assertIn("No USAR", notes)


class TestOrvexV4PoolManager(unittest.TestCase):
    def test_three_of_seven_safe_root(self):
        fake = FakeHelpers()
        fake.address_getters[(ORVEX_POOLMGR, "owner")] = ORVEX_SAFE
        _clean_safe(fake, ORVEX_SAFE,
                    [RealWeb3.to_checksum_address("0x" + f"{i:02x}" * 20) for i in range(1, 8)], 3)
        _patch(self, fake)
        e = scorers.score_orvex_v4_pool_manager(FakeW3())
        self.assertEqual(
            (e["adminKeyScore"], e["multisigScore"], e["timelockScore"], e["compositeScore"]),
            (65, 65, 0, 46),
        )
        self.assertIn("custody caveat", " ".join(e["notes"]))


class TestOrvexV4Vault(unittest.TestCase):
    def _fake(self, owner=ORVEX_EOA, kind="bare_eoa", pending=ORVEX_SAFE):
        fake = FakeHelpers()
        fake.address_getters[(ORVEX_VAULT, "owner")] = owner
        fake.address_getters[(ORVEX_VAULT, "pendingOwner")] = pending
        if owner:
            fake.classification[owner] = {"kind": kind, "delegate": None}
        return fake

    def test_bare_eoa_with_a_principal_moving_power_scores_2_not_the_fee_only_5(self):
        fake = self._fake()
        _patch(self, fake)
        e = scorers.score_orvex_v4_vault(FakeW3())
        self.assertEqual(
            (e["adminKeyScore"], e["multisigScore"], e["timelockScore"], e["compositeScore"]),
            (2, 0, 0, 1),
        )
        self.assertNotEqual(e["adminKeyScore"], 5)

    def test_offered_but_unaccepted_ownership_transfer_does_not_move_the_score(self):
        with_pending = self._fake(pending=ORVEX_SAFE)
        _patch(self, with_pending)
        a = scorers.score_orvex_v4_vault(FakeW3())
        self.assertIn("acceptOwnership() not yet called", " ".join(a["notes"]))
        self.assertEqual(a["adminKeyScore"], 2)

    def test_zero_pending_owner_produces_no_transfer_note(self):
        fake = self._fake(pending=ZERO)
        _patch(self, fake)
        notes = " ".join(scorers.score_orvex_v4_vault(FakeW3())["notes"])
        self.assertNotIn("acceptOwnership() not yet called", notes)

    def test_once_the_safe_accepts_the_scorer_rescores_itself_without_an_edit(self):
        fake = self._fake(owner=ORVEX_SAFE, kind="contract", pending=ZERO)
        _clean_safe(fake, ORVEX_SAFE,
                    [RealWeb3.to_checksum_address("0x" + f"{i:02x}" * 20) for i in range(1, 8)], 3)
        _patch(self, fake)
        e = scorers.score_orvex_v4_vault(FakeW3())
        self.assertEqual(
            (e["adminKeyScore"], e["multisigScore"], e["compositeScore"]), (65, 65, 46)
        )

    def test_owner_becoming_an_unresolvable_contract_degrades_to_20(self):
        fake = self._fake(owner=OTHER, kind="contract", pending=ZERO)
        _patch(self, fake)
        e = scorers.score_orvex_v4_vault(FakeW3())
        self.assertEqual((e["adminKeyScore"], e["multisigScore"], e["timelockScore"]), (20, 0, 0))


class TestWiring(unittest.TestCase):
    def test_all_four_scorers_are_registered(self):
        for f in (scorers.score_uncx_v4_locker, scorers.score_orvex_v2_pair_factory,
                  scorers.score_orvex_v4_pool_manager, scorers.score_orvex_v4_vault):
            self.assertIn(f, scorers.SIMPLE_SCORERS, f.__name__)

    def test_uncx_v4_joined_the_existing_group_instead_of_getting_a_new_one(self):
        group = signer_overlap.GROUPS["uncx_v3_locker"]
        self.assertEqual(sorted(a.lower() for a in group["targets"]),
                         sorted([UNCX_V3.lower(), UNCX_V4.lower()]))
        self.assertEqual([s.lower() for s in group["safes"]], [UNCX_SAFE.lower()])
        self.assertNotIn("uncx_v4_locker", signer_overlap.GROUPS)

    def test_orvex_group_holds_all_three_targets_and_both_roots(self):
        group = signer_overlap.GROUPS["orvex"]
        self.assertEqual(sorted(a.lower() for a in group["targets"]),
                         sorted(a.lower() for a in (ORVEX_V2, ORVEX_POOLMGR, ORVEX_VAULT)))
        self.assertEqual([a.lower() for a in group["known_eoa"]], [ORVEX_EOA.lower()])
        self.assertEqual([a.lower() for a in group["safes"]], [ORVEX_SAFE.lower()])

    def test_every_new_address_is_checksummed_and_in_exactly_one_group(self):
        # Scoped to the addresses THIS audit adds, on purpose. 6 entries
        # already in GROUPS before this change are stored in a different
        # casing than to_checksum_address() produces (arcus_perps_bridgevault,
        # t3tris_wbtc_vault, chainlink_admin x2, fables x2). All 6 are the
        # same 20 bytes, so nothing is broken -- every comparison in
        # signer_overlap.py lowercases first -- and they are deliberately
        # NOT touched here: they belong to other audits, not to this one.
        new_addresses = {UNCX_V4, ORVEX_V2, ORVEX_POOLMGR, ORVEX_VAULT, ORVEX_EOA, ORVEX_SAFE}
        seen = {}
        for key, group in signer_overlap.GROUPS.items():
            for addr in list(group["targets"]) + list(group["known_eoa"]) + list(group["safes"]):
                if addr in new_addresses:
                    self.assertEqual(addr, RealWeb3.to_checksum_address(addr), addr)
                seen.setdefault(addr.lower(), []).append(key)
        for addr in (UNCX_V4, ORVEX_V2, ORVEX_POOLMGR, ORVEX_VAULT, ORVEX_EOA):
            self.assertEqual(len(seen[addr.lower()]), 1, f"{addr} in {seen[addr.lower()]}")
        # ORVEX_SAFE is a root, listed once, in the orvex group only.
        self.assertEqual(seen[ORVEX_SAFE.lower()], ["orvex"])
        # UNCX_SAFE stays listed once even though it now roots two targets.
        self.assertEqual(seen[UNCX_SAFE.lower()], ["uncx_v3_locker"])


if __name__ == "__main__":
    unittest.main()
