#!/usr/bin/env python3
"""Planted cases for scripts/prove.py (offline, invented data): python3 test_prove.py [path to prove.py]
A consistent world gives all OK; ONE falsified value gives DIFFERENCE; an unread oracle gives UNREAD, never OK; no network at all gives no OK line and exit code 2."""
import importlib.util, json, os, sys, time, unittest

PROVE = sys.argv.pop(1) if len(sys.argv) > 1 and sys.argv[1].endswith(".py") else os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "prove.py")
spec = importlib.util.spec_from_file_location("prove", PROVE); P = importlib.util.module_from_spec(spec); sys.path.insert(0, os.path.dirname(os.path.abspath(PROVE))); spec.loader.exec_module(P)

H = "0x" + "11" * 32; T0 = 1_790_000_000
A = ["0x" + ("%02x" % i) * 20 for i in (1, 2)]


def score(i, h=H): return dict(adminKeyScore=10 + i, multisigScore=20, timelockScore=30, oracleAuthorityScore=40, crossExposureScore=50, compositeScore=25, lastUpdated=T0, methodologyHash=h)


README_TEXT = """## Try it

```bash
cast call 0x9BF45734D09bC7CA39238e767B2af9AAc62a7f52 \\
  "getScore(address)(uint8,uint8,uint8,uint8,uint8,uint8,uint64,bytes32)" \\
  0x1f7d7550B1b028f7571E69A784071F0205FD2EfA \\
  --rpc-url https://rpc.testnet.chain.robinhood.com/rpc
# adminKey, multisig, timelock, oracleAuthority, crossExposure, composite, lastUpdated, methodologyHash
# 80, 100, 75, 100, 80, 85, 1791664867, 0x795edc64...   (read live on 2026-10-11)
```
"""


def world():
    chain = {slug: {"count": 2, "targets": {a: score(i) for i, a in enumerate(A)}} for slug, *_ in P.ORACLES}
    watch = {slug: {"targets": [dict(score(i), target=a) for i, a in enumerate(A)]} for slug, *_ in P.ORACLES}
    watch["solana-devnet"] = {"targets": [dict(score(0), target="SolFake1")]}
    names = {slug: name for slug, name, *_ in P.ORACLES}
    cl = {name: {"hash": H, "targets": 2, "pushed": float(T0)} for name in names.values()}
    slug, addr, want = "robinhood-chain", "0x1f7d7550b1b028f7571e69a784071f0205fd2efa", (80, 100, 75, 100, 80, 85)   # the values the README text above prints
    chain[slug]["targets"][addr] = dict(zip(P.SUBS, want), lastUpdated=T0, methodologyHash=H); chain[slug]["count"] = 3
    watch[slug]["targets"].append(dict(chain[slug]["targets"][addr], target=addr)); cl["Robinhood Chain"]["targets"] = 3
    api = {"generatedAt": T0, "methodologyHash": H, "scores": [dict(chain[slug]["targets"][a], target=a) for a in chain[slug]["targets"]]}
    inc = {"incidents": [{"loss_usd": 1e9}, {"loss_usd": 2e8}], "in_scope": [{"loss_usd": 2e8, "flagged": "yes"}]}
    page = "flagged 1, missed 0, and could not be applied to 0 $1.2B $200.0M $200.0M of the $"
    return {"readme": README_TEXT, "names": names, "chain": chain, "sol": {"count": 1, "targets": {"SolFake1": score(0)}}, "watch": watch, "cl": cl, "api": api, "inc": inc, "page": page, "twins": [None], "twin_urls": [], "schema": None}


def statuses(data):
    P.judge_twins = lambda d: [("x", [], [])]      # one conforming twin (conformance itself is tested by scripts/conformance.py --selftest)
    return [s for s, _t in P.lines(data)]


class TestProve(unittest.TestCase):
    def test_a_consistent_world_is_all_ok(self):
        self.assertEqual(set(statuses(world())), {P.OK})

    def test_one_falsified_value_comes_out_as_a_difference(self):
        d = world(); d["watch"]["plasma"]["targets"][1]["timelockScore"] = 31          # a falsified Watch value
        st = statuses(d); self.assertIn(P.DIFF, st); self.assertEqual(st.count(P.DIFF), 1)
        d = world(); d["chain"]["monad"]["targets"][A[0]]["compositeScore"] = 99          # a falsified chain value
        self.assertIn(P.DIFF, statuses(d))
        d = world(); d["cl"]["Base"]["hash"] = "0x" + "22" * 32                           # a falsified CHANGELOG hash
        self.assertIn(P.DIFF, statuses(d))
        d = world(); d["api"]["methodologyHash"] = "0x" + "33" * 32                       # an out-of-date published file
        self.assertIn(P.DIFF, statuses(d))
        d = world(); d["page"] = d["page"].replace("flagged 1", "flagged 2")              # a falsified back-test figure
        self.assertIn(P.DIFF, statuses(d))

    def test_an_unread_oracle_is_unread_never_ok(self):
        d = world(); d["chain"]["base-sepolia"] = None
        st = statuses(d); self.assertIn(P.UNREAD, st); self.assertNotIn(P.DIFF, st)
        d = world(); d["sol"] = None; self.assertIn(P.UNREAD, statuses(d))
        d = world(); d["inc"] = None; self.assertIn(P.UNREAD, statuses(d))

    def test_the_readme_example_is_read_from_the_readme_not_from_the_script(self):
        d = world(); self.assertEqual(statuses(d).count(P.DIFF), 0)
        d = world(); d["readme"] = d["readme"].replace("# 80, 100, 75, 100, 80, 85,", "# 80, 100, 75, 100, 80, 86,"); st = statuses(d); self.assertEqual(st.count(P.DIFF), 1)        # a falsified README value
        d = world(); d["readme"] = d["readme"].replace("0x1f7d7550B1b028f7571E69A784071F0205FD2EfA", "0x2f7d7550B1b028f7571E69A784071F0205FD2EfA"); self.assertIn(P.DIFF, statuses(d))   # an example target the oracle does not track
        d = world(); d["readme"] = d["readme"].replace("0x9BF45734D09bC7CA39238e767B2af9AAc62a7f52", "0x1111111111111111111111111111111111111111"); self.assertIn(P.DIFF, statuses(d))   # another oracle than the one it names
        d = world(); d["readme"] = None; self.assertIn(P.UNREAD, statuses(d))
        d = world(); d["readme"] = "no example here"; self.assertIn(P.UNREAD, statuses(d))
        self.assertEqual(P.cmp_readme({"robinhood-chain": None}, README_TEXT)[0], P.UNREAD)
        self.assertIsNone(P.parse_readme_example("nothing")); self.assertEqual(P.parse_readme_example(README_TEXT)[2], (80, 100, 75, 100, 80, 85))

    def test_each_comparison_says_unread_on_its_own_when_its_input_is_missing(self):
        d = world(); names = d["names"]
        self.assertEqual(P.cmp_changelog({"base-sepolia": None}, {"base-sepolia": "Base"}, d["cl"])[0], P.UNREAD)
        self.assertEqual(P.cmp_changelog(d["chain"], names, {})[0], P.UNREAD)
        self.assertEqual(P.cmp_counts({"base-sepolia": None}, d["watch"])[0], P.UNREAD); self.assertEqual(P.cmp_scores(d["chain"], {})[0], P.UNREAD)
        self.assertEqual(P.cmp_readme({}, README_TEXT)[0], P.UNREAD); self.assertEqual(P.cmp_api(d["chain"], None)[0], P.UNREAD); self.assertEqual(P.cmp_solana(None, d["watch"])[0], P.UNREAD)
        self.assertEqual(P.cmp_backtest(d["inc"], None)[0], P.UNREAD); self.assertEqual(P.cmp_twins([])[0], P.UNREAD); self.assertEqual(P.cmp_twins([None, ("x", [], [])])[0], P.UNREAD)

    def test_no_network_at_all_gives_no_ok_line_and_exit_code_2(self):
        d = world()
        d["chain"] = {k: None for k in d["chain"]}; d["sol"] = None; d["watch"] = {k: None for k in d["watch"]}; d["cl"] = None; d["api"] = None; d["inc"] = None; d["page"] = None
        P.judge_twins = lambda dd: []
        res = P.lines(d); self.assertEqual({s for s, _t in res}, {P.UNREAD})
        rows, code = P.render(res, 1.0); self.assertEqual(code, 2)

    def test_exit_codes_and_the_last_line_say_what_is_not_proven(self):
        rows, code = P.render([(P.OK, "a")], 3); self.assertEqual(code, 0); self.assertIn("Does not prove", rows[-1])
        self.assertEqual(P.render([(P.OK, "a"), (P.DIFF, "b"), (P.UNREAD, "c")], 3)[1], 1)

    def test_the_changelog_table_is_parsed(self):
        t = "### 2026.10.2 (x)\n\n| Oracle | methodologyHash | Pushed |\n|---|---|---|\n| Base | `0x%s` (13 targets) | 2026-10-12 23:32Z |\n| Plasma | `0x%s` | 2026-10-12 23:56Z |\n" % ("ab" * 32, "cd" * 32)
        r = P.parse_changelog("# Changelog\n\n" + t); self.assertEqual(r["Base"]["targets"], 13); self.assertIsNone(r["Plasma"]["targets"]); self.assertEqual(r["Base"]["pushed"], 1_791_847_920.0)

    def test_the_selftest_of_the_script_passes(self):
        P.selftest()


if __name__ == "__main__": unittest.main(verbosity=1)
