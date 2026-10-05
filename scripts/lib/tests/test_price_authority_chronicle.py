"""Unit tests for the Chronicle Scribe spec (Ethereum and Monad), SparkLend's governance delay and the median of three feeds
(decisions of 2026-10-05). The chain is the fake of test_price_authority. No network."""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
import price_authority as pa  # noqa: E402
from test_price_authority import A, CODE, EOA, Chain  # noqa: E402


def setUpModule():  # the shared fakes' timelock code counts as a verified build here too
    import test_price_authority as _tpa
    _tpa.setUpModule()


def tearDownModule():
    import test_price_authority as _tpa
    _tpa.tearDownModule()


H = pa.Web3.keccak(CODE).hex().removeprefix("0x")
SCRIBE, TL, KISS, ACC, SE, OWNER = (pa._cs(A(1000 + i)) for i in range(6))
DAY = 86400


def patched(chain):
    return (mock.patch.object(pa, "call_raw", chain.call_raw), mock.patch.object(pa, "safe_owners_and_threshold", chain.safe))


class TestChronicleScribe(unittest.TestCase):
    WARDS = {TL: ("timelock", H), KISS: ("kiss", H), ACC: ("accessor", H)}

    def chain(self, answers=None, codes=None, **kw):
        a = {(SCRIBE, "authed"): [TL, KISS, ACC], (ACC, "spellExecutor"): SE, (SE, "owner"): OWNER, (TL, "getMinDelay"): 7 * DAY,
             (OWNER, "getMinDelay"): 7 * DAY, (SCRIBE, "bar"): 13, (SCRIBE, "opChallengePeriod"): 600}
        a.update(answers or {})
        c = {x: CODE for x in (SCRIBE, TL, KISS, ACC, SE, OWNER)}
        c.update(codes or {})
        return Chain(answers=a, codes=c, **kw)

    def paths(self, chain, gov=2 * DAY):
        spec = pa.chronicle_scribe_spec(SCRIBE, H, self.WARDS, (SE, H, OWNER, H))
        p1, p2 = patched(chain)
        with p1, p2:
            return spec(chain, gov)

    def test_verified_shape_kiss_bounded_and_both_timelocks_scored_by_their_delay(self):
        got = self.paths(self.chain())
        self.assertEqual([(p["status"], p["composite"]) for p in got], [("bounded", None), ("governance-grade", None), ("governance-grade", None)])
        self.assertTrue(all("bar() = 13" in p["note"] and "opChallengePeriod() = 600s" in p["note"] for p in got))
        self.assertNotIn("opChallengePeriod", self.paths(self.chain({(SCRIBE, "opChallengePeriod"): None}))[0]["note"])  # a plain Scribe

    def test_every_other_answer_is_unread(self):
        other = b"\x60\x01"
        for name, chain in (("extra ward", self.chain({(SCRIBE, "authed"): [TL, KISS, ACC, EOA]})),
                            ("missing ward", self.chain({(SCRIBE, "authed"): [TL, ACC]})),
                            ("duplicate ward", self.chain({(SCRIBE, "authed"): [TL, KISS, ACC, ACC]})),
                            ("authed unread", self.chain({(SCRIBE, "authed"): None})),
                            ("scribe code", self.chain(codes={SCRIBE: other})), ("kisser code", self.chain(codes={KISS: other})),
                            ("timelock code", self.chain(codes={TL: other})), ("accessor code", self.chain(codes={ACC: other})),
                            ("executor code", self.chain(codes={SE: other})), ("owner code", self.chain(codes={OWNER: other})),
                            ("spellExecutor", self.chain({(ACC, "spellExecutor"): EOA})), ("spellExecutor unread", self.chain({(ACC, "spellExecutor"): None})),
                            ("executor owner", self.chain({(SE, "owner"): EOA}))):
            with self.subTest(name):
                self.assertEqual([p["status"] for p in self.paths(chain)], ["UNREAD"])

    def test_a_ward_of_an_unknown_kind_is_unread_never_dropped(self):
        wards = {**self.WARDS, EOA: ("operator", H)}  # a new kind no branch scores
        spec = pa.chronicle_scribe_spec(SCRIBE, H, wards, (SE, H, OWNER, H))
        chain = self.chain({(SCRIBE, "authed"): [TL, KISS, ACC, EOA]}, codes={EOA: CODE})  # the ward has the pinned code: only its kind is off
        p1, p2 = patched(chain)
        with p1, p2:
            self.assertEqual([p["status"] for p in spec(chain, 2 * DAY)], ["UNREAD"])
            self.assertIn("unknown kind", spec(chain, 2 * DAY)[0]["note"])

    def test_a_short_timelock_is_unread_until_its_proposers_are_pinned(self):
        got = self.paths(self.chain(), gov=14 * DAY)
        self.assertEqual([p["status"] for p in got], ["bounded", "UNREAD", "UNREAD"])

    def test_the_real_pins_are_not_a_fake_code(self):
        for specs, scribes in ((pa.ETHEREUM_SPECS, pa.CHRONICLE_ETH_SCRIBES), (pa.MONAD_SPECS, pa.CHRONICLE_MONAD_SCRIBES)):
            for s in scribes:
                c = self.chain()
                p1, p2 = patched(c)
                with self.subTest(s=s), p1, p2:
                    self.assertEqual([p["status"] for p in specs[s](c, 2 * DAY)], ["UNREAD"])


class TestChronicleMonad(unittest.TestCase):
    """The registered Monad spec with its real addresses: both 7-day timelocks are pinned in TIMELOCK_HOLDERS, so at the
    vault's 14-day bar each scores its proposer Safe 2-of-3 behind 7 days (decision 1)."""
    SPELL_TL, WARD_TL = pa._cs(pa.CHRONICLE_MONAD_EXECUTOR[2]), pa._cs("0x2F8C90726Bc6bEc5D01313476F2e211a366A921a")

    def chain(self, logs=0, holds=True):
        se = pa._cs(pa.CHRONICLE_MONAD_EXECUTOR[0])
        props = [pa._cs(pa.TIMELOCK_HOLDERS[t.lower()][2][0][1]) for t in (self.SPELL_TL, self.WARD_TL)]
        answers = {(se, "owner"): self.SPELL_TL, (self.SPELL_TL, "getMinDelay"): 7 * DAY, (self.WARD_TL, "getMinDelay"): 7 * DAY,
                   (self.SPELL_TL, "hasRole"): holds, (self.WARD_TL, "hasRole"): holds}
        answers.update({(w, "spellExecutor"): se for w, (kind, _) in pa.CHRONICLE_MONAD_WARDS.items() if kind == "accessor"})
        answers.update({(s, "authed"): list(pa.CHRONICLE_MONAD_WARDS) for s in pa.CHRONICLE_MONAD_SCRIBES})
        c = Chain(answers=answers, codes={a: CODE for a in [*pa.CHRONICLE_MONAD_WARDS, se, self.SPELL_TL, *props]},
                  safes={p: ([A(1100 + i) for i in range(3)], 2) for p in props}, logs=logs)
        c.chain_id, c.block_number = 143, max(pa.TIMELOCK_HOLDERS[t.lower()][1] for t in (self.SPELL_TL, self.WARD_TL)) + 2
        return c

    def run_score(self, chain):
        p1, p2 = patched(chain)
        h = pa.Web3.keccak(CODE).hex().removeprefix("0x")  # the fake timelocks carry CODE, not the pinned build
        pins = {t.lower(): pa.TIMELOCK_HOLDERS[t.lower()][:3] + (h,) for t in (self.SPELL_TL, self.WARD_TL)}
        with p1, p2, mock.patch.object(pa, "_code_is", lambda w3, a, h: True), mock.patch.dict(pa.LOG_SOURCES, clear=True), \
                mock.patch.dict(pa.TIMELOCK_HOLDERS, pins), mock.patch("time.sleep", lambda s: None):
            notes = []
            rows = [(f"market {i}", s, 100) for i, s in enumerate(pa.CHRONICLE_MONAD_SCRIBES)]
            return pa.score(chain, rows, 14 * DAY, pa.MONAD_SPECS, (), notes), notes

    def test_proposer_safes_behind_seven_days_give_49(self):
        s, notes = self.run_score(self.chain())
        self.assertEqual(s, pa.composite(50, 35, 60))
        self.assertEqual(s, 49)
        self.assertEqual(sum("bounded" in n for n in notes), 8)  # two kiss-only wards on each of the four Scribes
        for t in (self.SPELL_TL, self.WARD_TL):
            self.assertTrue(any(f"{t}: timelock getMinDelay() = 604800s" in n for n in notes))

    def test_a_role_change_or_failed_replay_is_unread(self):
        for chain in (self.chain(logs=1), self.chain(holds=False), self.chain(logs=ConnectionError("down"))):
            with self.subTest(chain=chain):
                self.assertEqual(self.run_score(chain)[0], 20)


class TestSparkGovernance(unittest.TestCase):
    PROVIDER = pa._cs("0x02C3eA4e34C0cBd694D2adFa2c690EECbC1793eE")

    def chain(self, answers=None, codes=None, logs=0):
        sp, pp = pa._cs(pa.SPARK_PROXY), pa._cs(pa.SKY_PAUSE_PROXY)
        a = {(self.PROVIDER, "owner"): sp, (self.PROVIDER, "getACLAdmin"): sp, (self.PROVIDER, "getACLManager"): pa.SPARK_ACL,
             (pa.SPARK_ACL, "hasRole"): True, (pa.SPARK_STAR_GUARD, "subProxy"): sp, (pp, "owner"): pa.SKY_PAUSE, (pa.SKY_PAUSE, "delay"): 2 * DAY,
             (pa.SPARK_STAR_GUARD, "wards", (pp,)): 1}
        a.update({(sp, "wards", (pa._cs(w),)): 1 for w in (pp, pa.SPARK_ESM, pa.SPARK_STAR_GUARD)})
        a.update(answers or {})
        c = {x: CODE for x in pa.SPARK_CODE}
        c.update(codes or {})
        chain = Chain(answers=a, codes=c, logs=logs)
        chain.block_number = pa.SPARK_PROOF_BLOCK + 3
        return chain

    def governance(self, chain):
        p1, p2 = patched(chain)
        with p1, p2, mock.patch.dict(pa.SPARK_CODE, {k: H for k in pa.SPARK_CODE}), mock.patch("time.sleep", lambda s: None):
            return pa.spark_governance(chain, self.PROVIDER)

    def test_the_pause_delay_while_every_link_holds(self):
        delay, own, how = self.governance(self.chain())
        self.assertEqual(delay, 2 * DAY)
        self.assertEqual({a.lower() for a in own}, {a.lower() for a in (pa.SPARK_PROXY, pa.SPARK_ACL, pa.SKY_PAUSE_PROXY, pa.SKY_PAUSE)})
        self.assertIn("no change since", how)

    def test_any_broken_link_gives_no_delay(self):
        sp, pp = pa._cs(pa.SPARK_PROXY), pa._cs(pa.SKY_PAUSE_PROXY)
        pool_admin = (pa.SPARK_ACL, "hasRole", (pa._SPARK_ROLES[1], sp))
        for name, chain in (("owner", self.chain({(self.PROVIDER, "owner"): EOA})), ("ACL admin", self.chain({(self.PROVIDER, "getACLAdmin"): EOA})),
                            ("ACL manager", self.chain({(self.PROVIDER, "getACLManager"): EOA})), ("POOL_ADMIN", self.chain({pool_admin: False})),
                            ("roles unread", self.chain({(pa.SPARK_ACL, "hasRole"): None})),
                            ("ESM ward", self.chain({(sp, "wards", (pa._cs(pa.SPARK_ESM),)): 0})),
                            ("pause proxy ward", self.chain({(sp, "wards", (pp,)): None})),
                            ("StarGuard ward", self.chain({(pa.SPARK_STAR_GUARD, "wards", (pp,)): 0})),
                            ("StarGuard subProxy", self.chain({(pa.SPARK_STAR_GUARD, "subProxy"): EOA})),
                            ("pause proxy owner", self.chain({(pp, "owner"): EOA})), ("pause owner", self.chain({(pa.SKY_PAUSE, "owner"): EOA})),
                            ("code", self.chain(codes={pa.SPARK_ESM: b"\x60\x01"})),
                            ("change since the proof", self.chain(logs=1)), ("failed replay", self.chain(logs=ConnectionError("down")))):
            with self.subTest(name):
                self.assertIsNone(self.governance(chain)[0])

    def test_the_real_code_pins_are_not_a_fake_code(self):
        chain = self.chain()
        p1, p2 = patched(chain)
        with p1, p2:
            self.assertIsNone(pa.spark_governance(chain, self.PROVIDER)[0])

    def test_for_sparklend_scores_the_aave_rows_behind_that_delay(self):
        seen = {}
        with mock.patch.object(pa, "spark_governance", lambda w3, p: (2 * DAY, {"own"}, "checked")), \
                mock.patch.object(pa, "aave_rows", lambda w3, p: [("WETH", A(7), 1)]), \
                mock.patch.object(pa, "score", lambda w3, rows, gov, specs, own, notes: seen.update(gov=gov, own=own) or 31):
            notes = []
            self.assertEqual(pa.for_sparklend(None, self.PROVIDER, {}, notes), 31)
        self.assertEqual(seen, {"gov": 2 * DAY, "own": {"own"}})
        self.assertIn("172800s: checked", notes[0])
        with mock.patch.object(pa, "spark_governance", lambda w3, p: (None, set(), "x")), mock.patch.object(pa, "aave_rows", lambda w3, p: None):
            self.assertEqual(pa.for_sparklend(None, self.PROVIDER, {}, []), 20)


class TestMedianOfThree(unittest.TestCase):
    """Decision 3: an immutable median (Chronicle's Aggor) walks each of its three feeds and the weakest one binds."""
    AGGOR, CHRON, CL, CL_AGG, RS, RS_ADMIN, SAFE49, SAFE23 = (pa._cs(A(1200 + i)) for i in range(8))

    def test_the_weakest_feed_binds(self):
        answers = {(self.AGGOR, "chronicle"): self.CHRON, (self.AGGOR, "chainlink"): self.CL, (self.AGGOR, "redstone"): self.RS,
                   (self.CL, "aggregator"): self.CL_AGG, (self.CL, "owner"): self.SAFE49, (self.CL_AGG, "owner"): self.SAFE49,
                   (self.RS_ADMIN, "owner"): self.SAFE23}
        chain = Chain(answers=answers, codes={a: CODE for a in (self.AGGOR, self.CHRON, self.CL, self.CL_AGG, self.RS, self.RS_ADMIN, self.SAFE49, self.SAFE23)},
                      safes={self.SAFE49: ([A(1300 + i) for i in range(9)], 4), self.SAFE23: ([A(1310 + i) for i in range(3)], 2)},
                      storage={(self.RS, pa.ADMIN_SLOT): self.RS_ADMIN})
        specs = {self.CHRON: lambda w3, gov: [pa.path("chronicle", "governance-grade")]}
        p1, p2 = patched(chain)
        with p1, p2:
            notes = []
            self.assertEqual(pa.score(chain, [("WETH", self.AGGOR, 100)], 2 * DAY, specs, (), notes), 31)  # RedStone ProxyAdmin, Safe 2-of-3
            self.assertTrue(any(f"Chainlink proxy {self.CL} owner" in n and "composite 52" in n for n in notes))
            self.assertTrue(any("chronicle: governance-grade" in n for n in notes))


if __name__ == "__main__":
    unittest.main()
