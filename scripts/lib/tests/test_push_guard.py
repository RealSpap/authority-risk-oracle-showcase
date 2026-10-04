"""Unit tests for scripts/lib/push_guard.py: which entries are held before a push, and that a failed read of the published
scores refuses the push instead of passing it. Fixtures: the two live cases of the 2026-10-04 dry re-scoring (Plasma
Ethena OFT degraded 52 -> 14; Arbitrum USD AI degraded at 8, unchanged since published). No network."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import push_guard as g  # noqa: E402

OFT = "0x5d3a1Ff2b6BAb83b63cd9AD0787074081a52ef34"
USDAI = "0xffA10065Ce1d1C42FABc46e06B84Ed8FfEb4baE5"
OK = "0x" + "11" * 20


def entry(target, comp, notes=(), subs=(55, 100, 15)):
    return {"target": target, "label": target[:8], "compositeScore": comp, "notes": list(notes),
            "adminKeyScore": subs[0], "multisigScore": subs[1], "timelockScore": subs[2]}


DEGRADED_NOTE = "0xabD3: NOT resolvable as a Gnosis Safe this run -- unresolved authority, conservative score"


class TestReview(unittest.TestCase):
    def test_new_degradation_is_held_known_one_is_not(self):
        scored = [entry(OFT, 14, [DEGRADED_NOTE], (20, 20, 0)), entry(USDAI, 8, [DEGRADED_NOTE], (20, 0, 0)), entry(OK, 57)]
        held, lines = g.review(scored, {OFT.lower(): 52, USDAI.lower(): 8, OK.lower(): 57})
        self.assertEqual([e["target"] for e in held], [OFT])
        self.assertIn("published 52 -> new 14", lines[0])

    def test_big_drop_is_held_even_without_marker(self):
        held, _ = g.review([entry(OK, 30)], {OK.lower(): 46})
        self.assertEqual(len(held), 1)
        held, _ = g.review([entry(OK, 31)], {OK.lower(): 46})  # exactly MAX_DROP: not held
        self.assertEqual(held, [])

    def test_unread_published_holds_every_degraded_entry(self):
        held, _ = g.review([entry(USDAI, 8, [DEGRADED_NOTE])], None)
        self.assertEqual(len(held), 1)

    def test_accept_by_address(self):
        held, lines = g.review([entry(OFT, 14, [DEGRADED_NOTE])], {OFT.lower(): 52}, accepted=[OFT.upper().replace("0X", "0x")])
        self.assertEqual(held, [])
        self.assertIn("accepted by hand", lines[0])

    def test_new_target_not_yet_published_is_only_held_if_degraded(self):
        held, _ = g.review([entry(OK, 10)], {})
        self.assertEqual(held, [])
        held, _ = g.review([entry(OK, 14, subs=(20, 20, 0))], {})
        self.assertEqual(len(held), 1)


class TestOracleAuthorityField(unittest.TestCase):
    """oracleAuthorityScore is outside the composite: a drop or a new UNKNOWN on it is held too (2026-10-04)."""
    def oracle_entry(self, o, notes=()):
        return dict(entry(OK, 57, notes), oracleAuthorityScore=o)

    def test_rule_change_100_to_52_is_held_then_accepted(self):
        held, lines = g.review([self.oracle_entry(52)], {OK.lower(): 57}, published_oracle={OK.lower(): 100})
        self.assertEqual(len(held), 1)
        self.assertIn("oracleAuthorityScore 100 -> 52", lines[0])
        held, _ = g.review([self.oracle_entry(52)], {OK.lower(): 57}, accepted=[OK], published_oracle={OK.lower(): 100})
        self.assertEqual(held, [])

    def test_unread_path_is_held_on_any_move(self):  # an UNREAD next to a scored EOA gives 2, not 20: the marker decides
        for new in (20, 12, 2):
            with self.subTest(new=new):
                held, lines = g.review([self.oracle_entry(new, ["oracleAuthorityScore 12: material price path(s) UNREAD ['x']"])],
                                       {OK.lower(): 57}, published_oracle={OK.lower(): 25})
                self.assertEqual(len(held), 1)
                self.assertIn("UNREAD", lines[0])
        held, _ = g.review([self.oracle_entry(20, ["oracleAuthorityScore 20: price walk failed (RpcUnavailable: x)"])],
                           {OK.lower(): 57}, published_oracle={OK.lower(): 31})
        self.assertEqual(len(held), 1)
        held, _ = g.review([self.oracle_entry(20, ["material price path(s) UNREAD"])], {OK.lower(): 57}, published_oracle={OK.lower(): 20})
        self.assertEqual(held, [])  # known and unchanged: not news

    def test_rise_to_100_is_held(self):
        held, lines = g.review([self.oracle_entry(100, ["oracleAuthorityScore 100: no material price path"])], {OK.lower(): 57},
                               published_oracle={OK.lower(): 52})
        self.assertEqual(len(held), 1)
        self.assertIn("-> 100", lines[0])

    def test_markers_are_the_engines_and_do_not_mark_the_composite_degraded(self):
        import price_authority as pa
        for mark in (pa.UNREAD_MARK, pa.FAILED_MARK):
            with self.subTest(mark=mark):
                self.assertTrue(g.ORACLE_UNREAD.search(mark))
                self.assertFalse(g.DEGRADED.search(mark), "a price-walk mark must not read as a degraded composite")

    def test_unchanged_or_small_move_is_not_held(self):
        for old, new in ((52, 52), (20, 20), (52, 40), (31, 52), (100, 100)):
            with self.subTest(old=old, new=new):
                held, _ = g.review([self.oracle_entry(new)], {OK.lower(): 57}, published_oracle={OK.lower(): old})
                self.assertEqual(held, [])

    def test_enforce_reads_the_oracle_field_from_the_same_getscore(self):
        o = RecordingOracle({OK.lower(): 57})
        orig = g._read_scores
        g._read_scores = lambda w3, a, ts: {OK.lower(): (0, 0, 0, 100, 0, 57, 1, b"")}
        try:
            with self.assertRaises(SystemExit):
                g.enforce([self.oracle_entry(52)], oracle_w3=o, oracle_address=OK, argv=[])
            self.assertEqual(g.enforce([self.oracle_entry(52)], oracle_w3=o, oracle_address=OK, argv=[f"--accept-held={OK}"]), [])
        finally:
            g._read_scores = orig


class FailingOracle:
    class eth:
        @staticmethod
        def contract(**kw):
            raise ConnectionError("rpc down")


class TestEnforce(unittest.TestCase):
    def test_failed_published_read_refuses(self):
        with self.assertRaises(SystemExit):
            g.enforce([entry(OK, 57)], FailingOracle, OK, argv=[])

    def test_skip_flag_falls_back_to_unread_rules(self):
        with self.assertRaises(SystemExit):  # degraded + unread published -> still held
            g.enforce([entry(OFT, 14, [DEGRADED_NOTE])], FailingOracle, OK, argv=["--skip-published-check"])
        g.enforce([entry(OK, 57)], FailingOracle, OK, argv=["--skip-published-check"])

    def test_dry_run_never_exits(self):
        held = g.enforce([entry(OFT, 14, [DEGRADED_NOTE])], argv=[])
        self.assertEqual(len(held), 1)


class TestCallSites(unittest.TestCase):
    """Every EVM push script runs the guard twice (dry-run report, then before signing), and the two argparse scripts accept
    the guard's own escape flags (a second review of 2026-10-04 found both rejected them: a held entry blocked the push)."""
    ROOT = os.path.join(os.path.dirname(__file__), "..", "..", "..")
    SCRIPTS = ["chains/arbitrum-ecosystem/deploy/push_scores.py", "chains/base-ecosystem/deploy/push_scores.py",
               "chains/hyperliquid/deploy/push_scores.py", "chains/monad/deploy/push_scores.py",
               "chains/plasma-ecosystem/deploy/push_scores.py", "chains/tempo/deploy/push_scores.py",
               "chains/ethereum-l1/deploy/update_scores_ethereum_l1.py", "scripts/update_scores.py"]

    def test_guard_before_signing_everywhere(self):
        for rel in self.SCRIPTS:
            with self.subTest(script=rel):
                src = open(os.path.join(self.ROOT, rel)).read()
                self.assertEqual(src.count("push_guard.enforce(scored"), 2)
                live = src.index("push_guard.enforce(scored, oracle_w3")
                self.assertLess(live, src.index("sign_transaction("))
                self.assertLess(live, src.index(".updateScores(targets, tuples).build_transaction("))  # not the docstring mention (tempo)

    def test_argparse_scripts_declare_the_escape_flags(self):
        for rel in ("chains/hyperliquid/deploy/push_scores.py", "chains/ethereum-l1/deploy/update_scores_ethereum_l1.py"):
            with self.subTest(script=rel):
                src = open(os.path.join(self.ROOT, rel)).read()
                self.assertIn('"--accept-held"', src)
                self.assertIn('"--skip-published-check"', src)


class TestOracleKey(unittest.TestCase):
    def test_hyperliquid_derived_key_is_what_is_compared_and_accepted(self):
        dex = dict(entry("0x8888888c43cbB7e1C4132542E46831BffD866ED3", 5, [DEGRADED_NOTE]), oracleKey=OK)
        held, _ = g.review([dex], {OK.lower(): 9, "0x8888888c43cbb7e1c4132542e46831bffd866ed3": 5})
        self.assertEqual(len(held), 1)  # compared with the dex's own slot (9), not the raw address's (5)
        held, _ = g.review([dex], {OK.lower(): 9}, accepted=["0x8888888c43cbB7e1C4132542E46831BffD866ED3"])
        self.assertEqual(len(held), 1)  # accepting the raw address does not accept the dex
        held, _ = g.review([dex], {OK.lower(): 9}, accepted=[OK])
        self.assertEqual(held, [])


class RecordingOracle:
    """Answers getScore like the deployed oracle, and records which addresses were asked."""
    def __init__(self, published):
        self.published, self.asked = published, []
        outer = self

        class _Fn:
            def __init__(self, addr):
                self.addr = addr

            def call(self):
                outer.asked.append(self.addr.lower())
                comp = outer.published.get(self.addr.lower())
                return (0, 0, 0, 0, 0, comp or 0, 1 if comp is not None else 0, b"\0" * 32)

        class _Contract:
            class functions:
                getScore = staticmethod(lambda addr: _Fn(addr))

        class _Eth:
            @staticmethod
            def contract(**kw):
                return _Contract()
        self.eth = _Eth()


class TestExplicitFlagsAndKeys(unittest.TestCase):
    """The parts of the second-review fixes a mutation run showed untested (2026-10-04)."""

    def test_explicit_accepted_and_skip_override_argv(self):
        self.assertEqual(g.enforce([entry(OFT, 14, [DEGRADED_NOTE])], accepted=[OFT], argv=[]), [])
        g.enforce([entry(OK, 57)], FailingOracle, OK, argv=[], skip_published_check=True)  # must not raise

    def test_space_form_of_the_flag(self):
        self.assertEqual(g._accepted(["x.py", "--accept-held", "0xA, 0xB"]), ["0xA", "0xB"])
        self.assertEqual(g._accepted(["--accept-held=0xA,"]), ["0xA"])

    def test_published_read_and_suggestion_use_the_oracle_key(self):
        dex = dict(entry("0x8888888c43cbB7e1C4132542E46831BffD866ED3", 5, [DEGRADED_NOTE]), oracleKey=OK)
        oracle = RecordingOracle({OK.lower(): 9})
        with self.assertRaises(SystemExit) as cm:
            g.enforce([dex], oracle, OK, argv=[])
        self.assertEqual(oracle.asked, [OK.lower()])
        self.assertIn(f"--accept-held={OK}", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
