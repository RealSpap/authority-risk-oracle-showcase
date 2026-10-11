"""
Unit tests for the seven Ethereum L1 token targets added on 2026-10-11 (WETH9, USDC, USDT, DAI, USDS, PYUSD, FDUSD): the controller
classifier, the componentwise minimum, the degraded branches and the append-only order. No network: the chain reads are replaced.

Every expected composite is hand arithmetic from compositeScore = floor(0.4*admin + 0.3*multisig + 0.3*timelock + 0.5):
  USDC / PYUSD  (5, 0, 0)    -> 2.0 + 0 + 0 + 0.5 = 2.5   -> 2
  USDT          (55, 60, 0)  -> 22 + 18 + 0 + 0.5 = 40.5  -> 40   (legacy multisig 3 of 6: 3*15 + 3*5 = 60)
  FDUSD         (65, 70, 0)  -> 26 + 21 + 0 + 0.5 = 47.5  -> 47   (Safe 4 of 6: 4*15 + 2*5 = 70)
  Sky tokens    (75, 100, 70)-> 30 + 30 + 21 + 0.5 = 81.5 -> 81   (the Sky pause target's own row)
Run:  python3 -m unittest discover -s chains/ethereum-l1/tests -v
"""
import importlib.util
import os
import sys
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts", "lib"))
spec = importlib.util.spec_from_file_location("aro_eth_l1_tokens_scorers", os.path.join(REPO_ROOT, "chains/ethereum-l1/scorers.py"))
scorers = importlib.util.module_from_spec(spec)
sys.modules["aro_eth_l1_tokens_scorers"] = scorers
spec.loader.exec_module(scorers)

EOA, EOA2 = "0x" + "11" * 20, "0x" + "22" * 20
SAFE, MSIG, PROXYADMIN, ZERO = "0x" + "33" * 20, "0x" + "44" * 20, "0x" + "55" * 20, "0x" + "00" * 20
UNKNOWN = "0x" + "66" * 20


class Fake:
    """code: {address lower: bytes}; safes: {addr: (n owners, threshold)}; multisigs: {addr: (required, n)}; owners: {addr: owner}."""
    def __init__(self, code=None, safes=None, multisigs=None, owners=None, slots=None, getters=None):
        self.code, self.safes, self.multisigs, self.owners, self.slots = code or {}, safes or {}, multisigs or {}, owners or {}, slots or {}
        self.getters = getters or {}   # {(token lower, getter name): address}

    def install(self, test):
        sc = scorers
        saved = (sc._read_code, sc.safe_owners_and_threshold, sc.call_raw, sc.read_slot_as_address, sc.read_address_getter)
        sc._read_code = lambda w3, a: self.code.get(a.lower(), b"")
        sc.safe_owners_and_threshold = lambda w3, a: ([EOA] * self.safes[a.lower()][0], self.safes[a.lower()][1]) if a.lower() in self.safes else None

        def call_raw(w3, a, abi, name, *args, **kw):
            a = a.lower()
            if name == "required": return self.multisigs[a][0] if a in self.multisigs else None
            if name == "getOwners": return [EOA] * self.multisigs[a][1] if a in self.multisigs else None
            if name == "owner": return self.owners.get(a)
            return None
        sc.call_raw = call_raw
        sc.read_slot_as_address = lambda w3, a, slot: self.slots.get((a.lower(), slot), ZERO)
        sc.read_address_getter = lambda w3, a, g: self.getters.get((a.lower(), g))
        test.addCleanup(lambda: (setattr(sc, "_read_code", saved[0]), setattr(sc, "safe_owners_and_threshold", saved[1]),
                                 setattr(sc, "call_raw", saved[2]), setattr(sc, "read_slot_as_address", saved[3]),
                                 setattr(sc, "read_address_getter", saved[4])))


def fake(test, **kw):
    f = Fake(**{k: {a.lower() if isinstance(a, str) else a: v for a, v in d.items()} if k not in ("slots", "getters") else d for k, d in kw.items()})
    f.install(test)
    return f


class TestHolderScores(unittest.TestCase):
    def go(self, address, **kw):
        fake(self, **kw)
        notes = []
        return scorers._holder_scores(None, address, notes, "x"), notes

    def test_account_with_no_code_is_a_bare_eoa_and_the_note_does_not_claim_one_key(self):
        s, notes = self.go(EOA)
        self.assertEqual(s, (5, 0, 0)); self.assertIn("cannot be observed on chain", notes[0]); self.assertNotIn("private key", notes[0])

    def test_eip7702_delegation_is_an_account(self):
        s, _ = self.go(EOA, code={EOA: bytes.fromhex("ef0100") + b"\x01" * 20})
        self.assertEqual(s, (5, 0, 0))

    def test_safe_conventions(self):
        for n, t, want in ((5, 3, (65, 3 * 15 + 2 * 5, 0)), (3, 2, (50, 2 * 15 + 1 * 5, 0)), (2, 1, (10, 15 + 5, 0))):
            s, _ = self.go(SAFE, code={SAFE: b"\x60\x80"}, safes={SAFE: (n, t)})
            self.assertEqual(s, want, (n, t))

    def test_legacy_multisig_follows_the_wbtc_convention(self):
        s, _ = self.go(MSIG, code={MSIG: b"\x60\x80"}, multisigs={MSIG: (3, 6)})
        self.assertEqual(s, (55, 60, 0))
        s, _ = self.go(MSIG, code={MSIG: b"\x60\x80"}, multisigs={MSIG: (2, 3)})
        self.assertEqual(s, (20, 2 * 15 + 1 * 5, 0))

    def test_a_contract_with_an_owner_is_followed_one_hop_and_only_one(self):
        s, _ = self.go(PROXYADMIN, code={PROXYADMIN: b"\x60\x80"}, owners={PROXYADMIN: EOA})
        self.assertEqual(s, (5, 0, 0))
        s, _ = self.go(PROXYADMIN, code={PROXYADMIN: b"\x60\x80", EOA: b"\x60\x80"}, owners={PROXYADMIN: EOA, EOA: EOA2})
        self.assertIsNone(s)   # the second hop is not followed: unresolved, not guessed

    def test_a_contract_of_an_unknown_kind_is_unresolved(self):
        s, notes = self.go(UNKNOWN, code={UNKNOWN: b"\x60\x80"})
        self.assertIsNone(s); self.assertIn("unresolved", notes[-1])


class TestScoreToken(unittest.TestCase):
    def test_minimum_across_controllers_and_hand_composites(self):
        fake(self, code={SAFE: b"\x60\x80"}, safes={SAFE: (6, 4)})
        r = scorers._score_token(None, "0x" + "77" * 20, "T", [("a", SAFE), ("b", EOA)], "g", [])
        self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["timelockScore"], r["compositeScore"]), (5, 0, 0, 2))
        fake(self, code={SAFE: b"\x60\x80"}, safes={SAFE: (6, 4)})
        r = scorers._score_token(None, "0x" + "77" * 20, "T", [("a", SAFE)], "g", [])
        self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["compositeScore"]), (65, 70, 47))

    def test_proxy_admin_slot_is_a_controller_even_when_not_named(self):
        tok = "0x" + "77" * 20
        fake(self, code={SAFE: b"\x60\x80"}, safes={SAFE: (6, 4)}, slots={(tok, scorers._ZOS_ADMIN_SLOT): EOA})
        r = scorers._score_token(None, tok, "T", [("owner()", SAFE)], "g", [])
        self.assertEqual(r["adminKeyScore"], 5)   # the proxy admin account, not the Safe, sets the floor

    def test_unresolved_or_unset_controller_degrades_the_whole_token(self):
        fake(self, code={UNKNOWN: b"\x60\x80"})
        r = scorers._score_token(None, "0x" + "77" * 20, "T", [("a", UNKNOWN)], "g", [])
        self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["timelockScore"]), (20, 20, 0))
        fake(self)
        r = scorers._score_token(None, "0x" + "77" * 20, "T", [("a", None)], "g", [])
        self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["timelockScore"]), (20, 20, 0))


class TestWeth9AndSky(unittest.TestCase):
    def test_weth9_is_immutable_only_when_every_check_holds(self):
        code = b"\x60\x80\x60\x40"
        old_hash = scorers.WETH9_CODE_HASH
        self.addCleanup(lambda: setattr(scorers, "WETH9_CODE_HASH", old_hash))
        scorers.WETH9_CODE_HASH = bytes(scorers.Web3.keccak(code)).hex()
        fake(self, code={"0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2": code})
        r = scorers.score_weth9(None)
        self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["timelockScore"], r["compositeScore"]), (100, 100, 100, 100))
        scorers.WETH9_CODE_HASH = "00" * 32            # another code at that address
        r = scorers.score_weth9(None)
        self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["timelockScore"]), (20, 20, 0))

    def test_sky_tokens_degrade_when_the_ward_set_is_not_the_expected_one(self):
        sc = scorers
        saved = (sc.score_makerdao_sky_pause, sc._wards_of, sc.call_raw, sc.read_slot_as_address)
        self.addCleanup(lambda: [setattr(sc, n, v) for n, v in zip(("score_makerdao_sky_pause", "_wards_of", "call_raw", "read_slot_as_address"), saved)])
        sc.score_makerdao_sky_pause = lambda w3: {"adminKeyScore": 75, "multisigScore": 100, "timelockScore": 70, "notes": ["n"]}
        sc.call_raw = lambda w3, a, abi, name, *args, **kw: (sc._SKY_VAT if name == "vat" else 1)
        sc.read_slot_as_address = lambda w3, a, s: ZERO
        sc._wards_of = lambda *a: {sc._USDS_JOIN, sc._SKY_PAUSE_PROXY}
        r = sc.score_usds(None)
        self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["timelockScore"], r["compositeScore"]), (75, 100, 70, 81))
        sc._wards_of = lambda *a: {sc._USDS_JOIN, sc._SKY_PAUSE_PROXY, EOA}     # a stranger holds a ward
        r = sc.score_usds(None)
        self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["timelockScore"]), (20, 20, 0))
        sc._wards_of = lambda *a: {sc._DAI_JOIN}
        self.assertEqual(sc.score_dai(None)["compositeScore"], 81)


class TestTokenScorersEndToEnd(unittest.TestCase):
    """The four per-token scorers on a fake chain shaped like the live reads of 2026-10-11 (second review: none of them was called by a test)."""
    USDC = "0xA0b86991c6218b36c1d19d4a2e9eB0cE3606eB48"
    USDT = "0xdAC17F958D2ee523a2206206994597C13D831ec7"
    PYUSD = "0x6c3ea9036406852006290770BEdFcAbA0e23A0e8"
    FDUSD = "0xc5f0f7b66764F6ec8C8Dff7BA683102295E16409"
    MASTER, SUPPLY = "0x" + "aa" * 20, "0x" + "bb" * 20

    def test_usdc_five_accounts_with_no_code_is_5_0_0_and_a_safe_among_them_does_not_raise_the_floor(self):
        g = {(self.USDC.lower(), n): EOA for n in ("owner", "blacklister", "pauser")}
        g[(self.USDC.lower(), "masterMinter")] = self.MASTER
        slots = {(self.USDC.lower(), scorers._ZOS_ADMIN_SLOT): EOA2}
        fake(self, code={self.MASTER: b"\x60\x80"}, owners={self.MASTER: EOA}, getters=g, slots=slots)
        r = scorers.score_usdc(None)
        self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["timelockScore"], r["compositeScore"]), (5, 0, 0, 2))
        self.assertEqual(r["_rootGroup"], "usdc-circle-accounts")

    def test_usdt_legacy_multisig_3_of_6(self):
        fake(self, code={MSIG: b"\x60\x80"}, multisigs={MSIG: (3, 6)}, getters={(self.USDT.lower(), "owner"): MSIG})
        r = scorers.score_usdt(None)
        self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["timelockScore"], r["compositeScore"]), (55, 60, 0, 40))

    def test_fdusd_proxy_admin_contract_is_followed_to_the_same_4_of_6_safe(self):
        slots = {(self.FDUSD.lower(), scorers._EIP1967_ADMIN_SLOT): PROXYADMIN}
        fake(self, code={PROXYADMIN: b"\x60\x80", SAFE: b"\x60\x80"}, owners={PROXYADMIN: SAFE}, safes={SAFE: (6, 4)},
             getters={(self.FDUSD.lower(), "owner"): SAFE}, slots=slots)
        r = scorers.score_fdusd(None)
        self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["timelockScore"], r["compositeScore"]), (65, 70, 0, 47))

    def test_pyusd_reads_default_admin_and_the_supply_control_contract_owner(self):
        g = {(self.PYUSD.lower(), "owner"): EOA, (self.PYUSD.lower(), "defaultAdmin"): EOA, (self.PYUSD.lower(), "supplyControl"): self.SUPPLY}
        fake(self, code={self.SUPPLY: b"\x60\x80"}, owners={self.SUPPLY: EOA2}, getters=g)
        r = scorers.score_pyusd(None)
        self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["compositeScore"]), (5, 0, 2))
        self.assertTrue(any("supplyControl()" in n and "followed" in n for n in r["notes"]))
        # a getter that does not answer degrades the token instead of being skipped
        g.pop((self.PYUSD.lower(), "supplyControl"))
        fake(self, getters=g)
        r = scorers.score_pyusd(None)
        self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["timelockScore"]), (20, 20, 0))


class TestSkyGuards(unittest.TestCase):
    def setUp(self):
        sc = scorers
        names = ("score_makerdao_sky_pause", "_wards_of", "call_raw", "read_slot_as_address")
        saved = [getattr(sc, n) for n in names]
        self.addCleanup(lambda: [setattr(sc, n, v) for n, v in zip(names, saved)])
        sc.score_makerdao_sky_pause = lambda w3: {"adminKeyScore": 75, "multisigScore": 100, "timelockScore": 70, "notes": []}
        sc.read_slot_as_address = lambda w3, a, s: ZERO
        sc._wards_of = lambda *a: {sc._USDS_JOIN, sc._SKY_PAUSE_PROXY}
        self.vat_ward, self.ward_reread = 1, 1
        sc.call_raw = lambda w3, a, abi, name, *args, **kw: (sc._SKY_VAT if name == "vat" else (self.vat_ward if a == sc._SKY_VAT else self.ward_reread))

    def test_the_vat_must_be_warded_by_the_pause_proxy(self):
        self.assertEqual(scorers.score_usds(None)["compositeScore"], 81)
        self.vat_ward = 0
        self.assertEqual(scorers.score_usds(None)["adminKeyScore"], 20)

    def test_every_replayed_ward_is_re_read_on_chain(self):
        self.ward_reread = 0     # a replay that says "ward" while the contract says no
        r = scorers.score_usds(None)
        self.assertEqual((r["adminKeyScore"], r["multisigScore"], r["timelockScore"]), (20, 20, 0))


class _Log(dict):
    pass


class TestWardsReplay(unittest.TestCase):
    """_wards_of on fake logs: the new-style Rely/Deny events (subject 1) and the legacy anonymous LogNote (subject 2)."""
    def run_replay(self, legacy, events):
        sc = scorers
        saved = sc.get_w3
        self.addCleanup(lambda: setattr(sc, "get_w3", saved))
        W = scorers.Web3

        class Eth:
            block_number = 3_000_000

            def get_logs(self, flt):
                want = flt["topics"][0]
                return [e for e in events if e["topic0"] == want and flt["fromBlock"] <= e["blockNumber"] <= flt["toBlock"]]

        sc.get_w3 = lambda url: type("W", (), {"eth": Eth()})()
        return sc._wards_of(None, "0x" + "cc" * 20, 0, legacy)

    @staticmethod
    def addr_topic(a):
        return bytes.fromhex("00" * 12 + a[2:])

    def mk(self, topic0, who, block, idx, legacy):
        topics = [topic0, self.addr_topic("0x" + "11" * 20)] + ([self.addr_topic(who)] if legacy else [])
        if not legacy:
            topics = [topic0, self.addr_topic(who)]
        return {"topic0": "0x" + topic0.hex(), "blockNumber": block, "logIndex": idx, "topics": topics}

    def test_rely_then_deny_in_order_and_across_windows(self):
        W = scorers.Web3
        rely, deny = bytes(W.keccak(text="Rely(address)")), bytes(W.keccak(text="Deny(address)"))
        a, b = "0x" + "aa" * 20, "0x" + "bb" * 20
        ev = [self.mk(rely, a, 100, 0, False), self.mk(rely, b, 2_500_000, 3, False), self.mk(deny, a, 2_500_000, 5, False)]
        got = self.run_replay(False, ev)
        self.assertEqual({x.lower() for x in got}, {b})

    def test_legacy_lognote_uses_the_selector_as_first_topic_and_the_second_subject(self):
        W = scorers.Web3
        rely, deny = bytes(W.keccak(text="rely(address)")[:4]).ljust(32, b"\0"), bytes(W.keccak(text="deny(address)")[:4]).ljust(32, b"\0")
        a, b = "0x" + "aa" * 20, "0x" + "bb" * 20
        ev = [self.mk(rely, a, 10, 0, True), self.mk(rely, b, 11, 0, True), self.mk(deny, b, 12, 0, True)]
        got = self.run_replay(True, ev)
        self.assertEqual({x.lower() for x in got}, {a})


class TestOrder(unittest.TestCase):
    def test_the_seven_tokens_are_appended_after_the_existing_targets(self):
        names = [f.__name__ for f in scorers.SIMPLE_SCORERS]
        self.assertEqual(names[-9:-7], ["score_morpho_steakhouse_prime_usdc_v2", "score_morpho_steakhouse_prime_eurcv_v2"])
        self.assertEqual(names[-7:], ["score_weth9", "score_usdc", "score_usdt", "score_dai", "score_usds", "score_pyusd", "score_fdusd"])
        self.assertEqual(len(names), len(set(names)))   # (one scorer can return several targets, so the list is shorter than the oracle)


if __name__ == "__main__":
    unittest.main()
