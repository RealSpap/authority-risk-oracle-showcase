"""Dolomite price paths of scripts/lib/price_authority.py (2026-10-05): governance delay 0 while a pinned bypass executor
holds both roles; rows (each aggregator entry at the whole market value, own oracles read through to their feed, GM markets
expanded, frozen markets kept with an unknown value); the ConstantPriceOracle and GM specs (the keeper surface stays UNREAD,
decision 7). The fake Chain of test_price_authority; no network."""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
import price_authority as pa  # noqa: E402
import test_price_authority as t  # noqa: E402  (a module, so its TestCases are not collected twice)


def setUpModule():  # the shared fakes' timelock code counts as a verified build here too
    import test_price_authority as _tpa
    _tpa.setUpModule()


def tearDownModule():
    import test_price_authority as _tpa
    _tpa.tearDownModule()


A, CODE, ZERO = t.A, t.CODE, t.ZERO
H = pa.Web3.keccak(CODE).hex().removeprefix("0x")
M, OWNER, AGG, OWN_CL, OTHER, PAUSE, GMO, REG, DREG = (A(500 + i) for i in range(9))
T0, T1, T2, T3, PAIR, G, MT, FEED, FP, F1 = (A(520 + i) for i in range(10))
cs = pa.Web3.to_checksum_address


def batch_for(c):
    def batch(w3, calls, chunk=300, allow_failure=False):  # Multicall3 resolved call by call on the fake chain
        out = [c.call_raw(w3, a, [f], f["name"], *args) for a, f, args in calls]
        return None if None in out and not allow_failure else out
    return batch


class TestDolomiteGovernance(unittest.TestCase):
    HOLDERS = pa.DOLOMITE_BYPASS_EXECUTORS[:2]

    def gov(self, roles, code=CODE):
        role = lambda r: pa.Web3.keccak(text=r)  # noqa: E731
        answers = {(M, "owner"): OWNER, (OWNER, "secondsTimeLocked"): 300}
        answers.update({(OWNER, "hasRole", (role(r), pa._cs(h))): True for r, h in roles})
        c = t.Chain(answers=answers, codes={OWNER: code})
        with mock.patch.object(pa, "call_raw", c.call_raw), mock.patch.multiple(pa, DOLOMITE_OWNER_V2_CODE_HASH=H):
            return pa.dolomite_governance(c, M)

    def test_a_bypass_executor_makes_the_delay_zero(self):
        a, b = self.HOLDERS
        delay, own, why = self.gov([("BYPASS_TIMELOCK_ROLE", b), ("EXECUTOR_ROLE", b)])
        self.assertEqual((delay, {a.lower() for a in own}), (0, {M.lower(), OWNER.lower()}))
        self.assertIn(pa._cs(b), why)

    def test_no_pinned_holder_left_or_another_owner_is_no_bar(self):
        a, _ = self.HOLDERS
        for roles, code in (([("BYPASS_TIMELOCK_ROLE", a)], CODE), ([("EXECUTOR_ROLE", a)], CODE), ([], CODE),
                            ([("BYPASS_TIMELOCK_ROLE", a), ("EXECUTOR_ROLE", a)], b"\x60\x01")):
            with self.subTest(roles=roles, code=code):
                self.assertIsNone(self.gov(roles, code)[0])  # never the 300 s: the bypass set is unknown, not empty


class TestDolomiteRows(unittest.TestCase):
    def chain(self, over=None, codes=None):
        par, idx = lambda s: (0, s), (10 ** 18, 10 ** 18, 0)
        entries = lambda *e: [tuple(x) for x in e]  # noqa: E731
        answers = {
            (M, "getNumMarkets"): 4,
            # market 0: an aggregator entry read through an own Chainlink oracle, one foreign oracle, a tokenPair
            (M, "getMarketTokenAddress", (0,)): T0, (M, "getMarketPriceOracle", (0,)): AGG, (M, "getMarketTotalPar", (0,)): par(10 * 10 ** 18),
            (M, "getMarketCurrentIndex", (0,)): idx, (M, "getMarketPrice", (0,)): 3 * 10 ** 18,
            (AGG, "getOraclesByToken", (cs(T0),)): entries((OWN_CL, ZERO, 60), (OTHER, PAIR, 40)),
            (AGG, "getOraclesByToken", (cs(PAIR),)): entries((OWN_CL, ZERO, 100)),
            (OWN_CL, "DOLOMITE_MARGIN"): M, (OWN_CL, "getAggregatorByToken", (cs(T0),)): FEED, (OWN_CL, "getAggregatorByToken", (cs(PAIR),)): FP,
            # market 1: a GM token, its legs expanded through the aggregator its registry names
            (M, "getMarketTokenAddress", (1,)): G, (M, "getMarketPriceOracle", (1,)): AGG, (M, "getMarketTotalPar", (1,)): par(2 * 10 ** 18),
            (M, "getMarketCurrentIndex", (1,)): idx, (M, "getMarketPrice", (1,)): 5 * 10 ** 18,
            (AGG, "getOraclesByToken", (cs(G),)): entries((GMO, ZERO, 100)), (GMO, "marketTokens", (cs(G),)): True,
            (GMO, "REGISTRY"): REG, (REG, "dolomiteRegistry"): DREG, (DREG, "oracleAggregator"): AGG, (G, "UNDERLYING_TOKEN"): MT,
            (G, "LONG_TOKEN"): T0, (G, "SHORT_TOKEN"): T1, (REG, "gmxMarketToIndexToken", (cs(MT),)): T0,
            (AGG, "getOraclesByToken", (cs(T1),)): entries((OWN_CL, ZERO, 100)), (OWN_CL, "getAggregatorByToken", (cs(T1),)): F1,
            # market 2: frozen (getMarketPrice reverts) on a non-aggregator oracle; market 3: nothing supplied
            (M, "getMarketTokenAddress", (2,)): T2, (M, "getMarketPriceOracle", (2,)): PAUSE, (M, "getMarketTotalPar", (2,)): par(7),
            (M, "getMarketCurrentIndex", (2,)): idx,
            (M, "getMarketTokenAddress", (3,)): T3, (M, "getMarketPriceOracle", (3,)): AGG, (M, "getMarketTotalPar", (3,)): par(0),
            (M, "getMarketCurrentIndex", (3,)): idx, (M, "getMarketPrice", (3,)): 10 ** 18,
        }
        answers.update(over or {})
        return t.Chain(answers=answers, codes={**{x: CODE for x in (AGG, OWN_CL, OTHER, PAUSE, GMO)}, **(codes or {})}, safes={t.SAFE49: ([A(100 + i) for i in range(9)], 4)})

    def rows(self, c, notes=None):
        with mock.patch.object(pa, "call_raw", c.call_raw), mock.patch.object(pa, "_batch", batch_for(c)):
            return pa.dolomite_rows(c, M, {cs(M), cs(OWNER)}, [] if notes is None else notes)  # checksummed, as dolomite_governance returns them

    def test_entries_reach_the_whole_market_gm_legs_expand_and_a_frozen_market_stays(self):
        notes = []
        rows, total = self.rows(self.chain(), notes)
        self.assertEqual(total, 30 + 10)  # each market once; the frozen one adds nothing known
        by = [(label.split(" ")[1], src, v) for label, src, v in rows]
        self.assertEqual(by[:3], [("0", cs(FEED), 30), ("0", cs(OTHER), 30), ("0", cs(FP), 30)])  # not 60% and 40%: no cap on an entry
        self.assertEqual(by[3:8], [("1", cs(GMO), 10), ("1", cs(FEED), 10), ("1", cs(OTHER), 10), ("1", cs(FP), 10), ("1", cs(F1), 10)])  # index = long: once
        self.assertEqual(by[8:], [("2", cs(PAUSE), None)])  # frozen: kept, value unknown (material)
        self.assertTrue(any("market 2" in n and "frozen" in n for n in notes))

    def test_unread_reads_stay_rows(self):
        cases = ({(M, "getMarketCurrentIndex", (0,)): None}, {(AGG, "getOraclesByToken", (cs(PAIR),)): []}, {(G, "SHORT_TOKEN"): None},
                 {(OWN_CL, "DOLOMITE_MARGIN"): A(9)})
        for over in cases:
            with self.subTest(over=str(over)[:60]):
                rows, _ = self.rows(self.chain(over))
                if (OWN_CL, "DOLOMITE_MARGIN") in over:  # no longer own: the oracle itself is the source, not its feed
                    self.assertIn(cs(OWN_CL), [r[1] for r in rows])
                    self.assertNotIn(cs(FEED), [r[1] for r in rows])
                else:
                    self.assertTrue(any(r[1] is None or r[2] is None for r in rows if r[0].startswith("market 0") or r[0].startswith("market 1")))
        self.assertIsNone(self.rows(self.chain({(M, "getNumMarkets"): None})))


class TestDolomiteSpecs(unittest.TestCase):
    CPO, RD, KEEPER = A(560), A(561), A(562)

    def run_spec(self, spec, c, gov=300):
        consts = dict(DOLOMITE_CONSTANT_PRICE_ORACLE=(self.CPO, H), DOLOMITE_GM_ORACLE=(GMO, H), DOLOMITE_GMX_REGISTRY=(REG, H),
                      DOLOMITE_GMX_READER=(self.RD, H))
        with mock.patch.object(pa, "call_raw", c.call_raw), mock.patch.object(pa, "safe_owners_and_threshold", c.safe), mock.patch.multiple(pa, **consts):
            return [(p["status"], p["composite"]) for p in spec(c, gov)]

    def test_constant_price_oracle_is_own_only_in_its_verified_shape(self):
        ok = {(self.CPO, "DOLOMITE_MARGIN"): pa.DOLOMITE_MARGIN_ARB}
        self.assertEqual(self.run_spec(pa._dolomite_constant_price, t.Chain(answers=ok, codes={self.CPO: CODE})), [("own", None)])
        for over in ({"answers": {(self.CPO, "DOLOMITE_MARGIN"): A(9)}}, {"answers": ok, "codes": {self.CPO: b"\x60\x01"}},
                     {"answers": ok, "storage": {(self.CPO, pa.IMPL_SLOT): A(9)}}):
            with self.subTest(over=str(over)[:60]):
                over.setdefault("codes", {self.CPO: CODE})
                self.assertEqual(self.run_spec(pa._dolomite_constant_price, t.Chain(**over)), [("UNREAD", None)])

    def gm(self, gov=300, keepers=None, **over):
        gk = pa._gk
        answers = {(GMO, "REGISTRY"): REG, (GMO, "DOLOMITE_MARGIN"): pa.DOLOMITE_MARGIN_ARB, (REG, "DOLOMITE_MARGIN"): pa.DOLOMITE_MARGIN_ARB,
                   (REG, "gmxReader"): self.RD, (REG, "gmxDataStore"): pa.GMX_DATASTORE, (pa.GMX_DATASTORE, "roleStore"): pa.GMX_ROLESTORE,
                   (pa.GMX_ROLESTORE, "getRoleMembers", (gk("ROLE_ADMIN"), 0, 50)): [t.TL2D, t.SAFE49],
                   (pa.GMX_ROLESTORE, "getRoleMembers", (gk("CONFIG_KEEPER"), 0, 100)): [self.KEEPER] if keepers is None else keepers,
                   (t.TL2D, "getMinDelay"): 86400}
        answers.update(over.pop("answers", {}))
        codes = {x: CODE for x in (GMO, REG, self.RD, t.TL2D, t.SAFE49)}
        codes.update(over.pop("codes", {}))
        c = t.Chain(answers=answers, codes=codes, safes={t.SAFE49: ([A(100 + i) for i in range(9)], 4)}, **over)
        return self.run_spec(pa._dolomite_gm_price, c, gov)

    def test_gm_price_scores_role_admins_and_keeps_the_keeper_surface_unread(self):
        self.assertEqual(self.gm(), [("governance-grade", None), ("scored", 52), ("UNREAD", None)])
        self.assertEqual(self.gm(keepers=[]), [("governance-grade", None), ("scored", 52), ("UNREAD", None)])  # never bounded by itself
        self.assertEqual(self.gm(gov=0)[0], ("UNREAD", None))  # delay 0 (a bypass executor): the 1-day timelock's proposers are not pinned
        self.assertEqual(self.gm(answers={(pa.GMX_ROLESTORE, "getRoleMembers", (pa._gk("ROLE_ADMIN"), 0, 50)): None}), [("UNREAD", None), ("UNREAD", None)])

    def test_gm_price_is_one_unread_path_outside_its_verified_shape(self):
        for over in ({"answers": {(REG, "gmxReader"): A(9)}}, {"answers": {(REG, "gmxDataStore"): A(9)}}, {"answers": {(GMO, "REGISTRY"): A(9)}},
                     {"answers": {(REG, "DOLOMITE_MARGIN"): A(9)}}, {"answers": {(pa.GMX_DATASTORE, "roleStore"): A(9)}},
                     {"codes": {self.RD: b"\x60\x01"}}, {"codes": {REG: b"\x60\x01"}}, {"storage": {(GMO, pa.IMPL_SLOT): A(9)}}):
            with self.subTest(over=str(over)[:60]):
                self.assertEqual(self.gm(**over), [("UNREAD", None)])

    def test_the_specs_are_keyed_on_their_contracts_and_name_every_unbounded_key(self):
        self.assertIs(pa.DOLOMITE_SPECS[pa.DOLOMITE_CONSTANT_PRICE_ORACLE[0]], pa._dolomite_constant_price)
        self.assertIs(pa.DOLOMITE_SPECS[pa.DOLOMITE_GM_ORACLE[0]], pa._dolomite_gm_price)
        self.assertEqual(set(pa.GMX_GM_UNBOUNDED_KEYS), {"OPEN_INTEREST_RESERVE_FACTOR", "OPTIMAL_USAGE_FACTOR", "BORROWING_EXPONENT_FACTOR",
                                                         "MAX_PNL_FACTOR", "BORROWING_FEE_RECEIVER_FACTOR", "SWAP_FEE_FACTOR"})


class TestForDolomite(unittest.TestCase):
    AGGX = A(570)

    def score_with(self, spec_status, frozen=True):
        feeds = (FEED, FP, F1, OTHER) + (() if frozen else (PAUSE,))  # Chainlink proxies owned by a 4-of-9 Safe
        over = {**{(f, "aggregator"): self.AGGX for f in feeds}, **{(f, "owner"): t.SAFE49 for f in feeds}, (self.AGGX, "owner"): t.SAFE49}
        if not frozen:
            over[(M, "getMarketPrice", (2,))] = 10 ** 36
        c = TestDolomiteRows.chain(TestDolomiteRows(), over, codes={x: CODE for x in (FEED, FP, F1, self.AGGX, t.SAFE49)})
        notes = []
        with mock.patch.object(pa, "dolomite_governance", lambda w3, m: (0, {M, OWNER}, "fake")), mock.patch.object(pa, "call_raw", c.call_raw), \
                mock.patch.object(pa, "_batch", batch_for(c)), mock.patch.object(pa, "safe_owners_and_threshold", c.safe):
            return pa.for_dolomite(c, M, {GMO: lambda w3, g: [pa.path("gm", spec_status)]}, notes), notes

    def test_the_gm_path_and_a_frozen_market_each_cap_at_20(self):
        self.assertEqual(self.score_with("bounded", frozen=False)[0], 52)  # every other path a 4-of-9 Safe
        s, notes = self.score_with("UNREAD", frozen=False)
        self.assertEqual(s, 20)
        self.assertTrue(any("priced supply 47 USD" in n for n in notes))
        self.assertEqual(self.score_with("bounded", frozen=True)[0], 20)  # the frozen market's oracle, an own contract of unknown input, at an unknown value

    def test_the_dolomite_specs_are_added_by_the_entry_point_itself(self):
        seen = {}
        c = TestDolomiteRows.chain(TestDolomiteRows(), {}, codes={})
        with mock.patch.object(pa, "dolomite_governance", lambda w3, m: (0, {M}, "fake")), mock.patch.object(pa, "dolomite_rows", lambda w3, m, own, notes: ([], 0)), \
                mock.patch.object(pa, "score", lambda w3, rows, delay, specs, *a, **k: seen.update(specs=specs) or 100):
            pa.for_dolomite(c, M, pa.ARBITRUM_SPECS, [])  # what the scorer passes: no Dolomite spec in it
        self.assertTrue(set(pa.DOLOMITE_SPECS) <= set(seen["specs"]))
        self.assertFalse(set(pa.DOLOMITE_SPECS) & set(pa.ARBITRUM_SPECS))

    def test_an_rpc_failure_is_20(self):
        boom = t.Chain(raises=RuntimeError("rpc down"))
        notes = []
        with mock.patch.object(pa, "call_raw", boom.call_raw):
            self.assertEqual(pa.for_dolomite(boom, M, {}, notes), 20)
        self.assertIn(pa.FAILED_MARK, notes[-1])


if __name__ == "__main__":
    unittest.main()
