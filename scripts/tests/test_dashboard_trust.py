"""Tests of what the dashboard shows from the Watch: the evidence status next to each score (trust.json) and the four ages of each oracle (latest.json, oracles[].freshness).

Source tests read dashboard/index.html. The behaviour tests run the real functions of the page in node (skipped when node is not installed); nothing touches the network.
"""
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
PAGE = open(os.path.join(ROOT, "dashboard", "index.html"), encoding="utf-8").read()
STATUSES = ("VERIFIED", "PARTIAL", "STALE", "DISPUTED", "UNVERIFIED", "UNAVAILABLE")
FOUR = ("watch_read_at", "block_time", "newest_push", "oldest_push")


class TestSource(unittest.TestCase):
    def test_the_page_reads_trust_json_and_shows_the_six_statuses_and_a_not_read_state(self):
        self.assertGreaterEqual(PAGE.count("trust.json"), 1)
        block = PAGE[PAGE.index("var TRUST_STATUSES"):PAGE.index("var TRUST_MAX_AGE_S")]
        for s in STATUSES:
            self.assertIn("'%s'" % s, block, s)
        self.assertIn("'not read'", block)
        self.assertIn("never shown as VERIFIED", PAGE)

    def test_no_default_to_verified(self):
        fn = PAGE[PAGE.index("function trustStatusOf("):PAGE.index("function trustChip(")]
        self.assertNotRegex(fn, r"(?<![A-Za-z'])'VERIFIED'\s*;")
        self.assertIn("'not read'", fn)

    def test_the_four_ages_of_an_oracle_are_shown_from_latest_json(self):
        self.assertGreaterEqual(PAGE.count("freshness"), 1)
        for f in FOUR:
            self.assertIn("f." + f, PAGE, f)
        self.assertIn("f.block", PAGE)

    def test_every_evm_and_solana_card_carries_the_status_chip_and_the_zcash_tab_does_not(self):
        cards = PAGE[PAGE.index("function renderCards("):PAGE.index("function setStatus(")]
        self.assertIn("if (chain.kind !== 'zcash') tagsHtml += trustChip(trustStatusOfGroup(activeKey,", cards)
        self.assertIn("updateWatchBand();", cards)

    def test_the_only_new_host_is_one_the_privacy_page_already_lists(self):
        priv = open(os.path.join(ROOT, "docs", "PRIVACY.md"), encoding="utf-8").read()
        self.assertIn("raw.githubusercontent.com", priv)
        self.assertIn("trust.json", priv)
        self.assertIn("latest.json", priv)
        self.assertIn("https://raw.githubusercontent.com/RealSpap/authority-risk-oracle-showcase/watch-data/", PAGE)


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class TestBehaviour(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        code = PAGE[PAGE.index("var WATCH_BASE"):PAGE.index("  readWatch();\n  function fmtDate")]
        cls.js = ("var CHAINS = {robinhood: {oracle: '0xAbC', kind: 'evm'}, solana: {oracle: 'Sol', kind: 'solana'}, zcash: {kind: 'zcash'}}, activeKey = 'robinhood';\n"
                  "function escAttr(x) { return String(x); }\nvar lastScores = null;\nfunction renderCards() {}\nvar els = {watchBand: {innerHTML: ''}};\n"
                  "var document = {getElementById: function (i) { return els[i]; }};\n" + code)

    def run_node(self, body):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "t.js")
            open(p, "w").write(self.js + "\n" + body)
            r = subprocess.run(["node", p], capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    def test_a_missing_or_unknown_status_is_not_read_never_verified(self):
        out = self.run_node("""
var A = '0x' + 'ab'.repeat(20);
var res = {};
res.nofile = trustStatusOf('robinhood', A);
watchTrust = {by_target: {}};
res.nokey = trustStatusOf('robinhood', A);
watchTrust = {by_target: {['robinhood:' + A]: {status: 'verified'}}};
res.lowercase_word = trustStatusOf('robinhood', A);
watchTrust = {by_target: {['robinhood:' + A]: {status: 'OK'}}};
res.unknown_word = trustStatusOf('robinhood', A);
watchTrust = {by_target: {['robinhood:' + A]: {}}};
res.nostatus = trustStatusOf('robinhood', A);
watchTrust = {by_target: {['robinhood:' + A]: {status: 'VERIFIED'}}};
res.verified = trustStatusOf('robinhood', A);
res.upper_address = trustStatusOf('robinhood', '0x' + 'AB'.repeat(20));
console.log(JSON.stringify(res));""")
        self.assertEqual(out, {"nofile": "not read", "nokey": "not read", "lowercase_word": "not read", "unknown_word": "not read", "nostatus": "not read", "verified": "VERIFIED", "upper_address": "VERIFIED"})

    def test_a_group_shows_its_worst_status_and_one_missing_member_makes_it_not_read(self):
        out = self.run_node("""
var a = '0x' + '01'.repeat(20), b = '0x' + '02'.repeat(20), c = '0x' + '03'.repeat(20);
watchTrust = {by_target: {['robinhood:' + a]: {status: 'VERIFIED'}, ['robinhood:' + b]: {status: 'PARTIAL'}, ['robinhood:' + c]: {status: 'DISPUTED'}}};
console.log(JSON.stringify({ab: trustStatusOfGroup('robinhood', [a, b]), abc: trustStatusOfGroup('robinhood', [a, b, c]), missing: trustStatusOfGroup('robinhood', [a, '0x' + '09'.repeat(20)]), empty: trustStatusOfGroup('robinhood', [])}));""")
        self.assertEqual(out, {"ab": "PARTIAL", "abc": "DISPUTED", "missing": "not read", "empty": "not read"})

    def test_the_band_says_not_read_when_the_file_is_missing_old_or_in_error_and_counts_when_it_is_fresh(self):
        out = self.run_node("""
var res = {};
watchTrust = null; watchWhy = 'trust.json 404'; updateWatchBand(); res.missing = els.watchBand.innerHTML;
var now = new Date().toISOString().replace(/\\.\\d+Z$/, 'Z');
watchTrust = {generated_utc: now, by_target: {'robinhood:0x1': {status: 'VERIFIED'}, 'robinhood:0x2': {status: 'STALE'}}}; watchLatest = null; updateWatchBand(); res.fresh = els.watchBand.innerHTML;
console.log(JSON.stringify(res));""")
        self.assertIn("not read", out["missing"])
        self.assertIn("never shown as VERIFIED", out["missing"])
        self.assertIn("VERIFIED <b>1</b>", out["fresh"])
        self.assertIn("STALE <b>1</b>", out["fresh"])
        self.assertIn("not read (the Watch does not publish it", out["fresh"])      # no freshness published: said, not guessed

    def test_the_four_ages_sit_side_by_side_and_a_missing_one_says_not_published(self):
        out = self.run_node("""
var n = Math.floor(Date.now() / 1000);
watchTrust = null; watchLatest = {oracles: [{oracle: '0xABC', freshness: {watch_read_at: n - 600, block: 123, block_time: n - 660, newest_push: n - 7200, oldest_push: null}}]};
updateWatchBand();
console.log(JSON.stringify({html: els.watchBand.innerHTML, none: freshnessOf({oracle: '0xdead'})}));""")
        h = out["html"]
        for label in ("Watch read", "Block", "Newest push", "Oldest push"):
            self.assertIn("<b>%s</b>" % label, h)
        self.assertIn("10 min ago", h)
        self.assertIn("2.0 h ago", h)
        self.assertRegex(h, r"Oldest push</b> not published")
        self.assertIsNone(out["none"])

    def test_an_age_that_is_zero_negative_nan_or_text_is_not_published_and_a_block_that_is_missing_is_not_published(self):
        out = self.run_node("""
var n = Math.floor(Date.now() / 1000);
var r = {zero: ageText(0), neg: ageText(-5), nan: ageText(NaN), text: ageText('12'), nul: ageText(null), ok: ageText(n - 60)};
watchTrust = null; watchLatest = {oracles: [{oracle: '0xabc', freshness: {watch_read_at: n, block_time: n - 60, newest_push: n, oldest_push: n}}]}; updateWatchBand(); r.noblock = els.watchBand.innerHTML;
console.log(JSON.stringify(r));""")
        for k in ("zero", "neg", "nan", "text", "nul"):
            self.assertEqual(out[k], "not published", k)
        self.assertEqual(out["ok"], "1 min ago")
        self.assertRegex(out["noblock"], r"Block</b> not published")

    def test_readwatch_refuses_a_file_older_than_eight_hours_one_in_error_and_one_that_is_not_json_at_all(self):
        out = self.run_node("""
function serve(files) { fetch = function (u) { var n = u.split('/').pop(); var f = files[n]; return f === undefined ? Promise.resolve({ok: false, status: 404}) : Promise.resolve({ok: true, status: 200, json: function () { return f instanceof Error ? Promise.reject(f) : Promise.resolve(f); }}); }; }
var iso = function (h) { return new Date(Date.now() - h * 3600e3).toISOString().replace(/\\.\\d+Z$/, 'Z'); };
var res = {}, by = {'robinhood:0x1': {status: 'VERIFIED'}};
(async function () {
  serve({'trust.json': {generated_utc: iso(7), by_target: by}}); await readWatch(); res.fresh = watchTrust !== null;
  serve({'trust.json': {generated_utc: iso(9), by_target: by}}); await readWatch(); res.old = watchTrust === null; res.old_why = watchWhy;
  serve({'trust.json': {generated_utc: iso(1), error: 'boom', by_target: by}}); await readWatch(); res.error = watchTrust === null;
  serve({'trust.json': {generated_utc: 'yesterday', by_target: by}}); await readWatch(); res.undated = watchTrust === null; res.undated_why = watchWhy;
  serve({'trust.json': {generated_utc: iso(1)}}); await readWatch(); res.no_targets = watchTrust === null;
  serve({'trust.json': new Error('not json')}); await readWatch(); res.garbage = watchTrust === null;
  serve({}); await readWatch(); res.missing = watchTrust === null; res.missing_why = watchWhy;
  console.log(JSON.stringify(res));
})();""")
        self.assertEqual({k: v for k, v in out.items() if k not in ("old_why", "missing_why", "undated_why")}, {"fresh": True, "old": True, "error": True, "undated": True, "no_targets": True, "garbage": True, "missing": True})
        self.assertIn("older than 8 hours", out["old_why"])
        self.assertIn("404", out["missing_why"])
        self.assertIn("no readable date", out["undated_why"])


if __name__ == "__main__":
    unittest.main()
