"""Moonwell on Base (extended 2026-10-05): the ChainlinkOracle row recipe (feed, admin override, nativeToken branch), the
governance and own set, the admin-override spec, the LBTC/BTC bounded oracle spec (every fact re-read, any other answer
UNREAD), and the guard on number-prone getters. The fake Chain of test_price_authority. No network."""
import os
import sys
import unittest
from unittest import mock

from web3 import Web3

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import price_authority as pa  # noqa: E402
from test_price_authority import A, CODE, Chain  # noqa: E402


def setUpModule():  # the shared fakes' timelock code counts as a verified build here too
    import test_price_authority as _tpa
    _tpa.setUpModule()


def tearDownModule():
    import test_price_authority as _tpa
    _tpa.tearDownModule()


TG = pa.MOONWELL_TEMPORAL_GOVERNOR
UNI, SAFE49, EOA = A(300), A(301), A(302)
ORACLE = pa.MOONWELL_ORACLE[0]
M1, M2, M3 = (A(310 + i) for i in range(3))
U1, U2, U3 = (Web3.to_checksum_address(A(313 + i)) for i in range(3))  # the engine passes underlying() checksummed
WRAP, CL1, AGG1, COMP, CLBTC, AGGB = (A(320 + i) for i in range(6))
(BOUNDED, _), (IMPL, _), (PADMIN, _) = pa.MOONWELL_LBTC_BOUNDED.values()
PRIMARY, FALLBACK = pa.MOONWELL_LBTC_SETTINGS["primaryLBTCOracle"], pa.MOONWELL_LBTC_SETTINGS["fallbackLBTCOracle"]
AGGF = A(330)
CODES = {ORACLE: b"\x60\x01\x55", BOUNDED: b"\x60\x02", IMPL: b"\x60\x03\x55", PADMIN: b"\x60\x04\x55"}
H = lambda c: Web3.keccak(c).hex().removeprefix("0x")  # noqa: E731
PINS = {"oracle": (ORACLE, H(CODES[ORACLE])),
        "bounded": {"proxy": (BOUNDED, H(CODES[BOUNDED])), "implementation": (IMPL, H(CODES[IMPL])), "ProxyAdmin": (PADMIN, H(CODES[PADMIN]))}}


def moonwell(**over):
    """Unitroller -> TemporalGovernor (1 day), ChainlinkOracle admin TG. Markets: M1 (USDC via an OEV wrapper owned by TG ->
    a Chainlink proxy), M2 (LBTC via an immutable composite: base a Chainlink proxy, multiplier the bounded oracle), M3
    (an admin override). Every Chainlink proxy and aggregator owned by a 4-of-9 Safe."""
    answers = {
        (UNI, "admin"): TG, (UNI, "oracle"): ORACLE, (TG, "proposalDelay"): 86400, (ORACLE, "admin"): TG,
        (UNI, "getAllMarkets"): [M1, M2, M3], (ORACLE, "nativeToken"): Web3.keccak(text="GLMR"),
        (M1, "symbol"): "mUSDC", (M2, "symbol"): "mLBTC", (M3, "symbol"): "mFOO",
        (M1, "underlying"): U1, (M2, "underlying"): U2, (M3, "underlying"): U3,
        (U1, "symbol"): "USDC", (U2, "symbol"): "LBTC", (U3, "symbol"): "FOO",
        (ORACLE, "assetPrices", (U1,)): 0, (ORACLE, "assetPrices", (U2,)): 0, (ORACLE, "assetPrices", (U3,)): 10 ** 18,
        (ORACLE, "getFeed", ("USDC",)): WRAP, (ORACLE, "getFeed", ("LBTC",)): COMP,
        (ORACLE, "getUnderlyingPrice", (M1,)): 10 ** 30, (ORACLE, "getUnderlyingPrice", (M2,)): 60_000 * 10 ** 28,
        (ORACLE, "getUnderlyingPrice", (M3,)): 10 ** 18,
        (M1, "getCash"): 700 * 10 ** 6, (M1, "totalBorrows"): 400 * 10 ** 6, (M1, "totalReserves"): 100 * 10 ** 6,
        (M2, "getCash"): 10 ** 8, (M2, "totalBorrows"): 0, (M2, "totalReserves"): 0,
        (M3, "getCash"): 5000 * 10 ** 18, (M3, "totalBorrows"): 0, (M3, "totalReserves"): 0,
        (WRAP, "owner"): TG, (WRAP, "priceFeed"): CL1, (CL1, "aggregator"): AGG1, (CL1, "owner"): SAFE49, (AGG1, "owner"): SAFE49,
        (COMP, "base"): CLBTC, (COMP, "multiplier"): BOUNDED, (CLBTC, "aggregator"): AGGB, (CLBTC, "owner"): SAFE49, (AGGB, "owner"): SAFE49,
        (BOUNDED, "owner"): TG, (PADMIN, "owner"): TG, (BOUNDED, "primaryLBTCOracle"): PRIMARY, (BOUNDED, "fallbackLBTCOracle"): FALLBACK,
        (BOUNDED, "lowerBound"): 98_000_000, (BOUNDED, "upperBound"): 102_000_000,
        (FALLBACK, "aggregator"): AGGF, (FALLBACK, "owner"): SAFE49, (AGGF, "owner"): SAFE49,
    }
    answers.update(over.pop("answers", {}))
    codes = {**CODES, **{x: CODE for x in (UNI, TG, SAFE49, WRAP, CL1, AGG1, COMP, CLBTC, AGGB, FALLBACK, AGGF, PRIMARY)}}
    codes[WRAP] = b"\x60\x00\x55"  # stateful: walked only because its owner() is the target's own
    codes.update(over.pop("codes", {}))
    storage = {(BOUNDED, pa.IMPL_SLOT): IMPL, (BOUNDED, pa.ADMIN_SLOT): PADMIN}
    storage.update(over.pop("storage", {}))
    return Chain(answers=answers, safes={SAFE49: ([A(400 + i) for i in range(9)], 4)}, codes=codes, storage=storage, **over)


class TestMoonwell(unittest.TestCase):
    def setUp(self):
        for target, value in ((pa, ("MOONWELL_ORACLE", PINS["oracle"])), (pa, ("MOONWELL_LBTC_BOUNDED", PINS["bounded"]))):
            p = mock.patch.object(target, *value)
            p.start()
            self.addCleanup(p.stop)

    def run_with(self, c, fn, *args):
        with mock.patch.object(pa, "call_raw", c.call_raw), mock.patch.object(pa, "safe_owners_and_threshold", c.safe):
            return fn(c, *args)

    def entry(self, c):
        notes = []
        return self.run_with(c, pa.for_moonwell, UNI, pa.BASE_SPECS, notes), notes  # what the Base scorer passes: the entry point adds the Moonwell specs

    def test_rows_read_the_feed_the_override_and_the_value(self):
        rows = self.run_with(moonwell(), pa.moonwell_rows, UNI)
        self.assertEqual([(lbl.split()[0], src) for lbl, src, _ in rows], [("mUSDC", WRAP), ("mLBTC", COMP), ("mFOO", ORACLE)])
        self.assertEqual([round(v, 6) for _, _, v in rows], [1000, 60000, 5000])  # (cash + borrows - reserves) x price / 1e36

    def test_the_native_branch_reads_the_mtoken_symbol(self):
        c = moonwell(answers={(ORACLE, "nativeToken"): Web3.keccak(text="mFOO"), (ORACLE, "getFeed", ("mFOO",)): CL1})
        self.assertEqual(self.run_with(c, pa.moonwell_rows, UNI)[2][1], CL1)  # ignores the override, as getUnderlyingPrice does

    def test_an_unpinned_or_unread_oracle_leaves_every_row_without_a_source(self):
        for c in (moonwell(codes={ORACLE: b"\x60\x09\x55"}), moonwell(storage={(ORACLE, pa.IMPL_SLOT): IMPL}),
                  moonwell(answers={(ORACLE, "nativeToken"): None}), moonwell(answers={(ORACLE, "assetPrices", (U1,)): None})):
            with self.subTest():
                rows = self.run_with(c, pa.moonwell_rows, UNI)
                self.assertIn(None, [src for _, src, _ in rows])
                self.assertEqual(self.entry(c)[0], 20)

    def test_governance_owns_the_oracle_only_under_the_same_admin(self):
        delay, own = self.run_with(moonwell(), pa.moonwell_governance, UNI)
        self.assertEqual((delay, own), (86400, {UNI, TG, ORACLE}))
        _, own = self.run_with(moonwell(answers={(ORACLE, "admin"): EOA}), pa.moonwell_governance, UNI)
        self.assertNotIn(ORACLE, own)

    def test_a_moved_unitroller_admin_is_not_own_and_gives_no_delay(self):
        c = moonwell(answers={(UNI, "admin"): EOA, (EOA, "proposalDelay"): 86400, (ORACLE, "admin"): EOA})
        self.assertEqual(self.run_with(c, pa.moonwell_governance, UNI), (None, {UNI}))
        self.assertLessEqual(self.entry(c)[0], 20)  # never 52: the wrappers' owner is no longer the governor, and the override oracle is unread

    def test_the_specs_are_not_added_once_the_governor_is_not_confirmed(self):
        # the Unitroller admin moved but the oracle and the bounded oracle still answer to the TemporalGovernor, and only the override market
        # is material: without the governor the override is not "own" and the LBTC band is not "bounded"
        c = moonwell(answers={(UNI, "admin"): EOA, (UNI, "getAllMarkets"): [M3]})
        s, notes = self.entry(c)
        self.assertEqual(s, 20)
        self.assertFalse(any("already in the composite" in n for n in notes))

    def test_the_moonwell_specs_are_added_only_for_moonwell(self):
        self.assertEqual(pa.BASE_SPECS, {})  # Aave, Comet and Morpho on Base never see them
        self.assertTrue(set(pa.MOONWELL_SPECS) == {BOUNDED, ORACLE} or set(pa.MOONWELL_SPECS) >= {pa.MOONWELL_LBTC_BOUNDED["proxy"][0]})
        # a Morpho row reaching the bounded oracle without the specs: the TemporalGovernor is a foreign controller, not "bounded"
        c = moonwell()
        notes = []
        s = self.run_with(c, pa.score, [("x", BOUNDED, 100)], 86400, {}, set(), notes)
        self.assertNotIn("bounded", " ".join(notes))
        self.assertLessEqual(s, 52)

    def test_end_to_end_is_52_with_the_primary_bounded_and_the_override_own(self):
        s, notes = self.entry(moonwell())
        self.assertEqual(s, 52)
        self.assertTrue(any("primary" in n and ": bounded" in n for n in notes))
        self.assertTrue(any("admin price override: own" in n for n in notes))
        self.assertTrue(any(f"{FALLBACK} owner" in n and "composite 52" in n for n in notes))

    def test_an_override_under_another_admin_is_unread(self):
        s, notes = self.entry(moonwell(answers={(ORACLE, "admin"): EOA}))
        self.assertEqual(s, 20)
        self.assertTrue(any("admin price override: UNREAD" in n for n in notes))

    def test_every_bounded_oracle_fact_is_checked(self):
        cases = {"implementation code": {"codes": {IMPL: b"\x60\x08\x55"}}, "proxy code": {"codes": {BOUNDED: b"\x60\x08"}},
                 "ProxyAdmin code": {"codes": {PADMIN: b"\x60\x08\x55"}}, "implementation slot": {"storage": {(BOUNDED, pa.IMPL_SLOT): A(9)}},
                 "admin slot": {"storage": {(BOUNDED, pa.ADMIN_SLOT): A(9)}}, "beacon": {"storage": {(BOUNDED, pa.BEACON_SLOT): A(9)}},
                 "ProxyAdmin is a proxy": {"storage": {(PADMIN, pa.IMPL_SLOT): A(9)}},
                 "owner": {"answers": {(BOUNDED, "owner"): EOA}}, "ProxyAdmin owner": {"answers": {(PADMIN, "owner"): EOA}},
                 "primary": {"answers": {(BOUNDED, "primaryLBTCOracle"): A(9)}}, "fallback": {"answers": {(BOUNDED, "fallbackLBTCOracle"): A(9)}},
                 "lower bound": {"answers": {(BOUNDED, "lowerBound"): 90_000_000}}, "upper bound": {"answers": {(BOUNDED, "upperBound"): 110_000_000}},
                 "bound unread": {"answers": {(BOUNDED, "upperBound"): None}}, "fallback not Chainlink": {"answers": {(FALLBACK, "aggregator"): None}}}
        for name, over in cases.items():
            with self.subTest(name):
                paths = self.run_with(moonwell(**over), pa._moonwell_lbtc_bounded, 86400)
                self.assertEqual([p["status"] for p in paths], ["UNREAD"])
                self.assertEqual(self.entry(moonwell(**over))[0], 20)
        self.assertEqual([p["status"] for p in self.run_with(moonwell(), pa._moonwell_lbtc_bounded, 86400)], ["bounded", "scored"])

    def test_a_number_prone_getter_answering_a_codeless_address_is_unread_not_a_key(self):
        number = "0x" + f"{10 ** 18:040x}"  # multiplier() = 1e18 decoded as an address
        s, notes = self.entry(moonwell(answers={(COMP, "multiplier"): number}))
        self.assertEqual(s, 20)  # not 2: the codeless 'address' is not scored as a bare key
        self.assertTrue(any("answered an address with no code" in n for n in notes))


if __name__ == "__main__":
    unittest.main()
