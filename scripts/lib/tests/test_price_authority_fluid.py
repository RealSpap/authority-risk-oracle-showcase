"""Fluid Liquidity (2026-10-05): the walk of pinned Fluid oracle builds through their operands, the DEX, Uniswap V3 pool,
sequencer and VaultFactory-auth specs, the reUSD NAV spec, the rows and the entry point. Fake chain, no network. Each test
fails when its branch is removed."""
import json
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
from test_price_authority import A, CODE, Chain, pa  # noqa: E402


def setUpModule():  # the shared fakes' timelock code counts as a verified build here too
    import test_price_authority as _tpa
    _tpa.setUpModule()


def tearDownModule():
    import test_price_authority as _tpa
    _tpa.tearDownModule()


ZERO = "0x" + "00" * 20
B = lambda n: pa._cs("0x" + f"{(1 << 150) + n:040x}")  # noqa: E731  (above 2**32: an operand the walk reads as an address)
LIQ, VF, DEXF, TEAM = (pa._cs(x) for x in (pa.FLUID_LIQUIDITY, pa.FLUID_VAULT_FACTORY, pa.FLUID_DEX_FACTORY, pa.FLUID_TEAM_MULTISIG))
SEQ = pa._cs(next(iter(pa.FLUID_SEQUENCER_FEEDS)))
FEED, AGG, RATE, O1, O2, O3, CAP, DEX, POOL, OTHER_LIQ, EOA_FEED = (B(i) for i in range(11))
SAFE49, SAFE35, EOA = A(1), A(2), A(3)
AVO_IMPL = A(950)
SAFES = {SAFE49: ([A(100 + i) for i in range(9)], 4), SAFE35: ([A(200 + i) for i in range(5)], 3)}
OP = lambda *addrs, tag=1: b"".join(b"\x7f" + bytes(12) + bytes.fromhex(a[2:]) for a in addrs) + bytes([0x60, tag, 0x00])  # noqa: E731
SLOAD = lambda *addrs: OP(*addrs, tag=9)[:-1] + b"\x54\x00"  # noqa: E731  (a build that reads storage)


def builds(*pairs):
    """{masked template: (name, kind)} for the fake codes given, as FLUID_BUILDS pins the real ones."""
    return {pa.masked_template(code): (f"build {kind}", kind) for code, kind in pairs}


class FluidCase(unittest.TestCase):
    def chain(self, answers=None, codes=None, storage=None, logs=0):
        a = {(FEED, "aggregator"): AGG, (FEED, "owner"): SAFE49, (AGG, "owner"): SAFE49, (FEED, "latestRoundData"): (1, 1, 1, 1, 1)}
        a.update(answers or {})
        cd = {x: CODE for x in (FEED, AGG, RATE, SAFE49, SAFE35, OTHER_LIQ, LIQ, TEAM, AVO_IMPL)}  # TEAM: the Avocado proxy, its implementation
        cd.update(codes or {})
        c = Chain(answers=a, safes=SAFES, codes=cd, storage={(TEAM, 0): AVO_IMPL, **(storage or {})}, logs=logs)
        c.chain_id = 42161
        return c

    def patched(self, c, **consts):
        h = pa.Web3.keccak(CODE).hex().removeprefix("0x")  # the fake Avocado proxy and implementation count as the pinned ones
        consts = {"AVOCADO_PROXY_HASH": h, "AVOCADO_IMPL": (AVO_IMPL, {h}), **consts}
        return mock.patch.multiple(pa, call_raw=c.call_raw, safe_owners_and_threshold=c.safe, **consts)

    def score(self, c, rows, fluid_builds, specs=None, gov=86400):
        notes, specs = [], dict(specs or {})
        with self.patched(c, FLUID_BUILDS=fluid_builds):
            memo, out = {}, []
            for label, oracle, value in rows:
                out.append((label, tuple(pa.fluid_oracle_sources(c, oracle, specs, memo)), value))
            return pa.score(c, out, gov, specs, {LIQ}, notes), notes


class TestFluidWalk(FluidCase):
    def test_nested_builds_reach_their_feeds_and_skip_the_target(self):
        cap, o2 = OP(LIQ, FEED, tag=2), OP(FEED, CAP)
        c = self.chain(codes={O1: o2, CAP: cap})
        s, notes = self.score(c, [("vault", O1, 100)], builds((o2, "oracle"), (cap, "capped")))
        self.assertEqual(s, 52)  # the Chainlink feed behind the oracle and its CappedRate: Safe 4-of-9
        self.assertFalse(any(LIQ in n for n in notes))  # the target Liquidity is not a price path

    def test_unknown_build_proxy_or_account_is_unread(self):
        o = OP(FEED)
        for codes, storage in (({O1: o + b"\x00"}, None), ({O1: o}, {(O1, pa.IMPL_SLOT): A(9)}), ({}, None)):
            with self.subTest(codes=bool(codes), storage=storage):
                c = self.chain(codes=codes, storage=storage)
                self.assertEqual(self.score(c, [("vault", O1, 100)], builds((o, "oracle")))[0], 20)

    def test_a_capped_rate_source_that_is_not_a_feed_is_unread_unless_a_spec_names_it(self):
        cap, o = OP(LIQ, RATE, tag=2), OP(FEED, CAP)
        c = self.chain(codes={O1: o, CAP: cap})
        fb = builds((o, "oracle"), (cap, "capped"))
        s, notes = self.score(c, [("vault", O1, 100)], fb)
        self.assertEqual(s, 20)
        self.assertTrue(any(f"rate source {RATE}" in n and "UNREAD" in n for n in notes))
        spec = {RATE.lower(): lambda w3, gov: [pa.path("rate", "scored", 31)]}
        self.assertEqual(self.score(c, [("vault", O1, 100)], fb, spec)[0], 31)  # a chain spec wins

    def test_a_capped_rate_of_another_liquidity_is_unread(self):
        cap, o = OP(OTHER_LIQ, FEED, tag=2), OP(CAP)
        c = self.chain(codes={O1: o, CAP: cap})
        s, notes = self.score(c, [("vault", O1, 100)], builds((o, "oracle"), (cap, "capped")))
        self.assertEqual(s, 20)
        self.assertTrue(any("another Liquidity" in n for n in notes))

    def test_slot0_build_needs_the_sequencer_feed_in_storage(self):
        o = SLOAD(FEED)
        fb = builds((o, "slot0"))
        c = self.chain(codes={O1: o, SEQ: CODE}, storage={(O1, 0): SEQ})
        self.assertEqual(self.score(c, [("vault", O1, 100)], fb)[0], 52)
        c = self.chain(codes={O1: o}, storage={(O1, 0): A(9)})
        self.assertEqual(self.score(c, [("vault", O1, 100)], fb)[0], 20)

    def test_the_sequencer_feed_is_disclosed_not_scored(self):
        o = OP(SEQ)
        c = self.chain(codes={O1: o, SEQ: CODE}, answers={(SEQ, "aggregator"): AGG, (SEQ, "owner"): EOA})
        s, notes = self.score(c, [("vault", O1, 100)], builds((o, "oracle")))
        self.assertEqual(s, 100)  # an uptime feed halts the oracle; even owned by a bare key it moves no price
        self.assertTrue(any("L2 sequencer feed" in n and "bounded" in n for n in notes))

    def test_dex_and_pool_specs(self):
        dex_code, pool_code, o = OP(LIQ, tag=3), OP(B(50), tag=4), OP(DEX, POOL)
        good = {(DEX, "constantsView"): (1, int(LIQ, 16), int(DEXF, 16)) + (0,) * 15, (DEXF, "owner"): TEAM,
                (POOL, "factory"): pa._cs("0x1F98431c8aD98523631AE4a59f267346ea31F984"),
                (TEAM, "requiredSigners"): 6, (TEAM, "signers"): [A(900 + i) for i in range(12)]}
        fb = builds((o, "oracle"))
        consts = {"FLUID_DEX_TEMPLATE": pa.masked_template(dex_code), "UNIV3_POOL_TEMPLATE": pa.masked_template(pool_code)}
        with mock.patch.multiple(pa, **consts):
            c = self.chain(good, codes={O1: o, DEX: dex_code, POOL: pool_code, B(50): CODE})
            s, notes = self.score(c, [("vault", O1, 100)], fb)
            self.assertEqual(s, pa.composite(*pa._safe_rooted(6, 12)))  # the DexFactory owner, an Avocado 6-of-12, acts at once: 56
            self.assertTrue(any(f"Fluid DEX {DEX}: own" in n for n in notes) and any("Uniswap V3 pool" in n and "bounded" in n for n in notes))
            self.assertTrue(any("Avocado multisig 6-of-12, no delay" in n for n in notes))
            for over in ({(DEXF, "owner"): EOA}, {(DEX, "constantsView"): (1, int(OTHER_LIQ, 16), int(DEXF, 16)) + (0,) * 15},
                         {(POOL, "factory"): A(9)}):
                with self.subTest(over=str(over)[:40]):
                    self.assertEqual(self.score(self.chain({**good, **over}, codes={O1: o, DEX: dex_code, POOL: pool_code}), [("vault", O1, 100)], fb)[0], 20)

    def test_a_cycle_is_one_unread_row_and_a_deep_chain_is_unread(self):
        o1, o2 = OP(O2), OP(O1)  # O1 reads O2 and O2 reads O1: the same pinned build
        c = self.chain(codes={O1: o1, O2: o2})
        s, notes = self.score(c, [("vault", O1, 100)], builds((o1, "oracle")))
        self.assertEqual(s, 20)  # no RecursionError, and the target is not lost: one UNREAD row
        self.assertTrue(any("reads itself through a cycle" in n or "price path" in n and "UNREAD" in n for n in notes))
        chain_ids = [B(200 + i) for i in range(7)]  # a chain of 7 pinned builds, each reading the next
        codes = {chain_ids[i]: OP(chain_ids[i + 1]) for i in range(6)}
        codes[chain_ids[6]] = OP(FEED)
        s, _ = self.score(self.chain(codes=codes), [("vault", chain_ids[0], 100)], builds((codes[chain_ids[0]], "oracle")))
        self.assertEqual(s, 20)  # deeper than 4: UNREAD
        codes2 = {chain_ids[i]: OP(chain_ids[i + 1]) for i in range(2)}
        codes2[chain_ids[2]] = OP(FEED)
        s, _ = self.score(self.chain(codes=codes2), [("vault", chain_ids[0], 100)], builds((codes2[chain_ids[0]], "oracle")))
        self.assertEqual(s, 52)  # three deep resolves to the Chainlink feed

    def test_operands_without_code_and_small_numbers_are_not_inputs(self):
        o = OP(B(77), A(5))  # B(77) is below 2**152 and has no code: a number; A(5) is below 2**32
        c = self.chain(codes={O1: o})
        self.assertEqual(self.score(c, [("vault", O1, 100)], builds((o, "oracle")))[0], 20)  # no input named: UNREAD, never 100

    def test_an_address_like_operand_without_code_is_a_bare_key_and_a_build_with_no_input_is_unread(self):
        key = pa._cs("0x" + f"{(1 << 158) + 77:040x}")
        o = OP(key, A(5))
        c = self.chain(codes={O1: o})
        s, notes = self.score(c, [("vault", O1, 100)], builds((o, "oracle")))
        self.assertEqual(s, 2)  # the account answering for a price is scored as a bare key
        self.assertTrue(any("bare EOA" in n or "not a contract" in n for n in notes))
        peg = OP(A(5))  # a plain PegOracle with no ERC4626 feed set: a 1:1 peg that reads nothing, not UNREAD
        s, _ = self.score(self.chain(codes={O1: peg}), [("vault", O1, 100)], {pa.masked_template(peg): ("PegOracle", "oracle")})
        self.assertEqual(s, 100)
        self.assertEqual(self.score(self.chain(codes={O1: peg}), [("vault", O1, 100)], {pa.masked_template(peg): ("DexSmartColPegOracle", "oracle")})[0], 20)
        ones = pa._cs("0x" + "ff" * 20)  # all ones is a constant, not an account
        o2 = OP(ones, A(5))
        self.assertEqual(self.score(self.chain(codes={O1: o2}), [("vault", O1, 100)], builds((o2, "oracle")))[0], 20)


class TestVaultAuths(FluidCase):
    OWNER, FEE = "0xD7ae7c8848f7C550F10c40f5B39c596CEC75fe9c", "0x3Bc96922e90f13B0Fa0c6a2db035D09681d966ea"

    def run_auths(self, answers=None, codes=None, logs=0, chain_id=42161):
        h = pa.Web3.keccak(CODE).hex().removeprefix("0x")
        a = {(VF, "owner"): self.OWNER, (VF, "isGlobalAuth"): True, (self.OWNER, "LIQUIDITY"): LIQ, (self.OWNER, "FACTORY"): VF}
        a.update(answers or {})
        c = self.chain(a, codes={VF: CODE, self.OWNER: CODE, self.FEE: CODE, **(codes or {})}, logs=logs)
        c.chain_id, c.block_number = chain_id, 511887500
        pins = {42161: (511887408, self.OWNER, {self.FEE: ("fee auth", h), TEAM: ("team multisig", None)})}
        with self.patched(c, FLUID_VAULT_AUTHS=pins, FLUID_CODE={VF: h, "owner": h}), mock.patch("time.sleep", lambda s: None):
            return [(p["status"], p["note"]) for p in pa._fluid_vault_auths(c, 86400)]

    def test_own_for_the_timelock_side_and_the_team_multisig_scored_at_no_delay(self):
        got = self.run_auths(answers={(TEAM, "requiredSigners"): 6, (TEAM, "signers"): [A(900 + i) for i in range(12)]})
        self.assertEqual([g[0] for g in got], ["own", "scored"])
        self.assertIn("the fee auths only set rates", got[0][1])
        self.assertIn("Avocado multisig 6-of-12, no delay", got[1][1])
        # an Avocado that cannot be read as t-of-n is UNREAD, never skipped
        self.assertEqual([g[0] for g in self.run_auths()], ["own", "UNREAD"])
        ok = {(TEAM, "signers"): [A(900 + i) for i in range(12)]}
        for name, answers in (("zero signers required", {**ok, (TEAM, "requiredSigners"): 0}), ("more required than signers", {**ok, (TEAM, "requiredSigners"): 13})):
            with self.subTest(name):
                self.assertEqual([g[0] for g in self.run_auths(answers=answers)], ["own", "UNREAD"])
        for name, codes in (("another proxy", {TEAM: b"\x60\x02"}), ("another implementation", {AVO_IMPL: b"\x60\x03"})):
            with self.subTest(name):
                self.assertEqual([g[0] for g in self.run_auths(answers={(TEAM, "requiredSigners"): 6, **ok}, codes=codes)], ["own", "UNREAD"])

    def test_any_other_answer_is_unread(self):
        for kw in ({"answers": {(VF, "owner"): EOA}}, {"answers": {(VF, "isGlobalAuth"): False}}, {"answers": {(self.OWNER, "LIQUIDITY"): A(9)}},
                   {"codes": {self.FEE: b"\x60\x01"}}, {"codes": {VF: b"\x60\x01"}}, {"logs": 1}, {"logs": ConnectionError("no getLogs")},
                   {"chain_id": 1}):
            with self.subTest(kw=str(kw)[:50]):
                self.assertEqual(self.run_auths(**kw)[0][0], "UNREAD")


class TestReusdNav(FluidCase):
    def run_spec(self, gov=86400, answers=None, codes=None, logs=0, storage=None):
        h = pa.Web3.keccak(CODE).hex().removeprefix("0x")
        px, feed, core, am = (pa._cs(x) for x in (pa.REUSD_NAV_PROXY, pa.REUSD_NAV_FEED, pa.REUSD_NAV_ORACLE, pa.REUSD_ACCESS_MANAGER))
        submit = (core, pa.Web3.keccak(text="submitReport(uint256,uint256)")[:4])
        a = {(px, "aggregator"): feed, (feed, "oracle"): core, (px, "authority"): am, (core, "authority"): am,
             (am, "getTargetFunctionRole"): 0, (am, "getTargetFunctionRole", submit): pa.REUSD_SUBMITTER_ROLE, (am, "hasRole"): (True, 0),
             (px, "REVIEW_DELAY"): 172800, (core, "markdownDelay"): 86400, (core, "maxCumulativeBps"): 200, (core, "velocityWindow"): 1209600}
        a.update(answers or {})
        c = self.chain(a, codes={px: CODE, feed: CODE, core: CODE, am: CODE, pa._cs(pa.REUSD_ADMIN): CODE, **(codes or {})}, logs=logs, storage=storage)
        c.block_number = pa.REUSD_ADMIN_PROOF_BLOCK + 10
        c.safes[pa.REUSD_ADMIN.lower()] = SAFES[SAFE35]
        with self.patched(c, REUSD_CODE={x: h for x in (px, feed, core, am)}), mock.patch("time.sleep", lambda s: None):
            return [(p["status"], p["composite"]) for p in pa._reusd_nav_arb(c, gov)]

    def test_admin_safe_scored_swap_and_markdown_governance_grade(self):
        self.assertEqual(self.run_spec(), [("governance-grade", None), ("governance-grade", None), ("bounded", None), ("scored", 43)])
        self.assertEqual(self.run_spec(gov=200000)[:2], [("UNREAD", None), ("UNREAD", None)])  # delays below the target's

    def test_any_other_fact_is_unread(self):
        px, core, am = pa._cs(pa.REUSD_NAV_PROXY), pa._cs(pa.REUSD_NAV_ORACLE), pa._cs(pa.REUSD_ACCESS_MANAGER)
        force = (core, pa.Web3.keccak(text="forceNAVUpdate(uint256,string)")[:4])
        for kw in ({"answers": {(px, "aggregator"): A(9)}}, {"answers": {(am, "getTargetFunctionRole", force): 7}},
                   {"answers": {(am, "hasRole"): (True, 3600)}}, {"answers": {(am, "hasRole"): (False, 0)}},
                   {"answers": {(core, "markdownDelay"): None}}, {"codes": {core: b"\x60\x01"}}, {"storage": {(px, pa.IMPL_SLOT): A(9)}},
                   {"logs": 1}, {"logs": ConnectionError("no getLogs")}):
            with self.subTest(kw=str(kw)[:60]):
                self.assertEqual(self.run_spec(**kw), [("UNREAD", None)])

    def test_keyed_on_the_proxy(self):
        self.assertIs(pa.ARBITRUM_SPECS[pa.REUSD_NAV_PROXY], pa._reusd_nav_arb)


class TestRowsAndEntryPoint(FluidCase):
    T1V, T2V, T3V, NOV, DEBTV = B(100), B(101), B(102), B(103), B(104)
    USDC, ETH, DEXB = B(110), B(111), B(112)

    def resolver(self, oracle_t1=O1):
        r = pa._cs(pa.FLUID_VAULT_RESOLVER)
        st = lambda borrow: (0,) * 4 + (borrow,) + (0,) * 8  # noqa: E731
        t1c = (LIQ, VF, B(1), B(2), self.ETH, self.USDC, 18, 6, 1, b"", b"", b"", b"")
        tnc = lambda bor, toks: (LIQ, VF, B(1), B(2), B(3), B(4), B(5), bor, (self.ETH, ZERO), toks, 2, 0, b"", b"", b"", b"")  # noqa: E731
        a = {(r, "getAllVaultsAddresses"): [self.T1V, self.T2V, self.T3V, self.NOV, self.DEBTV],
             (r, "getVaultType", (self.T1V,)): 10000, (r, "getVaultType", (self.T2V,)): 20000, (r, "getVaultType", (self.T3V,)): 30000,
             (r, "getVaultType", (self.NOV,)): 10000, (r, "getVaultType", (self.DEBTV,)): 10000,
             (r, "getVaultVariables2Raw", (self.T1V,)): int(oracle_t1, 16) << 96, (r, "getVaultVariables2Raw", (self.T2V,)): 3 << 92,
             (r, "getVaultVariables2Raw", (self.T3V,)): 4 << 92, (r, "getVaultVariables2Raw", (self.NOV,)): 0, (r, "getVaultVariables2Raw", (self.DEBTV,)): 0,
             (r, "getContractForDeployerIndex", (self.T2V, 3)): O1, (r, "getContractForDeployerIndex", (self.T3V, 4)): O1,
             (r, "getVaultState", (self.T1V,)): st(2_000_000), (r, "getVaultState", (self.T2V,)): st(1_000_000), (r, "getVaultState", (self.T3V,)): st(10 ** 18),
             (r, "getVaultState", (self.NOV,)): st(0), (r, "getVaultState", (self.DEBTV,)): st(5_000_000),
             (self.T1V, "constantsView"): t1c, (self.DEBTV, "constantsView"): t1c, (self.T2V, "constantsView"): tnc(LIQ, (self.USDC, ZERO)),
             (self.T3V, "constantsView"): tnc(self.DEXB, (self.USDC, self.ETH))}
        return a

    PRICES = ({B(110).lower(): (1.0, 6), B(111).lower(): (2000.0, 18)}, {B(112).lower(): (B(110).lower(), B(111).lower(), 10 ** 6, 10 ** 15)})

    def test_debt_usd_normal_and_smart(self):
        o = OP(FEED)
        c = self.chain(self.resolver(), codes={O1: o})
        with self.patched(c, FLUID_BUILDS=builds((o, "oracle"))):
            rows = pa.fluid_rows(c, {}, [], self.PRICES)
        values = {r[0]: r[2] for r in rows}
        self.assertEqual(values[self.T1V], 2.0)  # 2,000,000 USDC units, 6 decimals
        self.assertEqual(values[self.T2V], 1.0)
        self.assertEqual(values[self.T3V], 1.0 + 2.0)  # one DEX share: 1 USDC + 0.001 ETH
        self.assertNotIn(self.NOV, values)  # no oracle, no debt: reads no price
        self.assertIsNone([r for r in rows if r[0] == self.DEBTV][0][1])  # no oracle but debt: a row with no source (UNREAD)
        self.assertEqual(rows[0][1][0], VF)  # every row reaches the VaultFactory auths
        with self.patched(c, FLUID_BUILDS=builds((o, "oracle"))):
            rows = pa.fluid_rows(c, {}, [], ({}, {}))  # no API price: unvalued, hence material
        self.assertEqual({r[0]: r[2] for r in rows}[self.T1V], None)

    def test_entry_point_scores_the_weakest_material_path(self):
        o, o_eoa = OP(FEED), OP(EOA_FEED, tag=7)
        a = self.resolver()
        a.update({(VF, "owner"): A(70), (LIQ, "getAdmin"): A(71), (A(71), "getMinDelay"): 86400, (EOA_FEED, "aggregator"): B(121),
                  (EOA_FEED, "owner"): EOA, (B(121), "owner"): EOA, (EOA_FEED, "latestRoundData"): (1, 1, 1, 1, 1)})
        c = self.chain(a, codes={O1: o, O2: o_eoa, EOA_FEED: CODE, B(121): CODE, A(71): CODE})
        own_auths = lambda w3, gov: [pa.path("auths", "own")]  # noqa: E731
        r = pa.FLUID_VAULT_RESOLVER.lower()
        with self.patched(c, FLUID_BUILDS=builds((o, "oracle"), (o_eoa, "oracle")), _fluid_vault_auths=own_auths):
            notes = []
            self.assertEqual(pa.for_fluid(c, LIQ, {}, notes, weights=self.PRICES), 20)  # DEBTV owes 5 of 11 USD and has no oracle: UNREAD
            self.assertTrue(any("governance delay" in n and "86400s" in n for n in notes))
            c.answers[(r, "getVaultState", (self.DEBTV,))] = (0,) * 13
            self.assertEqual(pa.for_fluid(c, LIQ, {}, [], weights=self.PRICES), 52)
            c.answers[(r, "getContractForDeployerIndex", (self.T3V, 4))] = O2
            self.assertEqual(pa.for_fluid(c, LIQ, {}, [], weights=self.PRICES), 2)  # the bare-key feed behind T3V (3 of 6 USD)
            self.assertEqual(pa.for_fluid(c, B(999), {}, [], weights=self.PRICES), 20)  # not the Fluid Liquidity
            c.codes[A(71).lower()] = b"\x60\x02"  # the Liquidity admin timelock is not a verified build: no governance bar
            notes = []
            pa.for_fluid(c, LIQ, {}, notes, weights=self.PRICES)
            self.assertTrue(any("governance delay" in n and "None" in n for n in notes))


class TestApiWeights(unittest.TestCase):
    API = [{"supplyToken": {"token0": {"address": "0xAA", "price": "2", "decimals": 18}, "token1": {"address": ZERO}},
            "borrowToken": {"token0": {"address": "0xBB", "price": "1", "decimals": 6}, "token1": {"address": "0xCC", "price": "3", "decimals": 8}},
            "supplyDexData": {"address": ZERO}, "borrowDexData": {"address": "0xDD", "token0PerShare": "5", "token1PerShare": "6"}}]

    def test_prices_and_dex_shares_from_the_api_and_empty_on_failure(self):
        body = mock.MagicMock()
        body.read.return_value = json.dumps(self.API).encode()
        with mock.patch("urllib.request.urlopen", return_value=body):
            prices, dexes = pa.fluid_usd_weights(42161)
        self.assertEqual(prices, {"0xaa": (2.0, 18), "0xbb": (1.0, 6), "0xcc": (3.0, 8)})
        self.assertEqual(dexes, {"0xdd": ("0xbb", "0xcc", 5, 6)})
        with mock.patch("urllib.request.urlopen", side_effect=OSError("down")):
            self.assertEqual(pa.fluid_usd_weights(42161), ({}, {}))



class TestPins(unittest.TestCase):
    def test_every_pinned_build_has_a_known_kind(self):
        self.assertTrue(all(kind in ("oracle", "slot0", "capped") for _, kind in pa.FLUID_BUILDS.values()))
        self.assertEqual(len(pa.FLUID_BUILDS), 24)
        self.assertTrue(all(len(t) == 64 for t in pa.FLUID_BUILDS))


if __name__ == "__main__":
    unittest.main()
