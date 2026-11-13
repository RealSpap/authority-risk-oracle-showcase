"""Source tests for the texts corrected after the second round of review: each sentence that was wrong or missing is checked where it is written. No network."""
import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))


def read(*p):
    return open(os.path.join(ROOT, *p), encoding="utf-8").read()


class TestReadme(unittest.TestCase):
    R = read("README.md")

    def test_the_gate_line_count_is_the_real_one_everywhere(self):
        n = len(read("integrations", "authority_facts_gate.py").splitlines())
        self.assertEqual(self.R.count("in %d lines" % n), 1)   # the strict gate is the one used in the commands; the simple gate is named once, with its line count
        self.assertRegex(self.R, r"(?<![0-9])%d lines" % len(read("integrations", "authority_facts_gate_strict.py").splitlines()))
        self.assertNotIn("14 lines", self.R)

    def test_a_score_is_not_a_status_and_the_chain_composite_is_not_the_cap(self):
        self.assertIn("A score is not a status.", self.R)
        self.assertIn("`l1CappedComposite`", self.R)
        self.assertIn("watch/trust.json", self.R)

    def test_the_two_values_of_the_same_reading_are_explained(self):
        self.assertIn("was 80 on 22 October and is 40 since the push of 27 October", self.R)


class TestMethodWords(unittest.TestCase):
    def test_the_method_document_says_which_method_it_describes(self):
        m = read("METHODOLOGY.md")
        self.assertIn("Which method this document describes", m)
        self.assertIn("the CHANGELOG describes what the chain runs", m)

    def test_numbers_that_were_out_of_date(self):
        m = read("METHODOLOGY.md")
        self.assertNotIn("five modules or guards", m)
        self.assertIn("ten analysed Safe modules or guards", m)
        self.assertIn("202 live entries", m)

    def test_the_multisig_formula_rises_with_owners_and_it_is_said_where_it_is_defined_and_where_limits_are_listed(self):
        self.assertIn("RISES with the number of owners", read("METHODOLOGY.md"))
        lim = read("docs", "LIMITS.md")
        for want in ("`_safe_rooted_scores(1, 20)` gives 100", "A dimension that does not apply counts as 100 in the average", "The delay score is a ladder with different rungs", "The overlap score counts groups, not signers"):
            self.assertIn(want, lim, want)

    def test_the_rise_is_true_in_the_code(self):
        import sys
        sys.path.insert(0, os.path.join(ROOT, "scripts")); sys.path.insert(0, os.path.join(ROOT, "scripts", "lib"))
        from lib import scorers
        self.assertEqual(scorers._safe_rooted_scores(1, 20)[1], 100)
        self.assertEqual(scorers._safe_rooted_scores(3, 5)[1], 55)
        self.assertEqual(scorers._safe_rooted_scores(9, 9)[1], 100)


class TestTheBacktestWording(unittest.TestCase):
    def test_a_large_gap_is_not_said_to_be_ruled_out(self):
        for f in (("docs", "WHAT-THE-SCORE-SAYS.md"), ("data", "finding_2026-10-01-backtest-victims-vs-controls.md")):
            t = read(*f)
            self.assertNotIn("ruled out", t, f)
            self.assertIn("-58 to +31", t, f) if "finding" in f[1] else self.assertIn("-58 to +31", t)

    def test_the_base_rate_of_the_requirements_is_written_and_true(self):
        import json, importlib.util
        spec = importlib.util.spec_from_file_location("br", os.path.join(ROOT, "scripts", "badges_req.py")); br = importlib.util.module_from_spec(spec); spec.loader.exec_module(br)
        rows = json.load(open(os.path.join(ROOT, "api", "scores.json")))["scores"]
        failing = sum(1 for r in rows if br.met(r) < 6)
        self.assertEqual((failing, len(rows)), (62, 63))
        self.assertIn("62 of the 63 contracts", read("docs", "WHAT-THE-SCORE-SAYS.md"))

    def test_the_cap_numbers_are_true(self):
        import json
        rows = json.load(open(os.path.join(ROOT, "api", "scores.json")))["scores"]
        self.assertEqual(sum(1 for r in rows if r["l1CappedComposite"] < r["compositeScore"]), 8)
        self.assertEqual(max(r["l1CappedComposite"] for r in rows), 57)


class TestApiAndSecurityTexts(unittest.TestCase):
    A = read("watch", "API.md")

    def test_the_signature_example_does_not_promise_what_it_does_not_check(self):
        self.assertNotIn("// true: every file listed in sig.manifest.files hashes", self.A)
        self.assertIn("You must still compare sig.public_key to a key you pinned", self.A)

    def test_the_two_summaries_say_they_are_not_signed(self):
        for name in ("| `status.json` |", "| `badge/integrity.json` |"):
            line = next(l for l in self.A.splitlines() if l.startswith(name))
            self.assertIn("NOT in the signed manifest", line, name)

    def test_the_dashboard_of_this_repository_is_not_said_to_verify_signatures(self):
        self.assertNotIn("the dashboard verifies it in the browser", self.A)
        self.assertIn("which does not verify signatures", self.A)

    def test_the_squads_pending_line_does_not_say_that_a_stale_proposal_is_dead(self):
        """05/11 (N-20): in Squads v4 an approved proposal past the stale index stays executable. The line says only what the Watch lists (approved and above the stale index) and
        never that 'live' means 'not stale' or that a stale one is 'dead'. The sentence that said so must not come back."""
        self.assertNotIn("approved and live (past the multisig's stale index", self.A)
        self.assertNotIn("approved but dead", self.A)
        self.assertIn("`pending` = approved and above the multisig's stale index (executable by any executor from `ready_at`", self.A)

    def test_compatibility_is_stated_for_consumers(self):
        self.assertIn("A consumer must refuse a `schemaVersion` it does not know", self.A)

    def test_the_alert_feed_is_a_history(self):
        line = next(l for l in self.A.splitlines() if l.startswith("| `alerts.xml` |"))
        self.assertIn("history", line)
        self.assertIn("does not say whether it is active", line)

    def test_the_new_trust_fields_are_documented(self):
        for w in ("retry_may_help", "run.alert_channels", "score_row_unreadable", "stale_flag_unknown", "signature_previous_run_missing"):
            self.assertIn(w, self.A, w)

    def test_the_code_field_scope_is_the_same_in_the_three_places_that_describe_it_and_in_the_code(self):
        for text in (self.A, read("docs", "KEY-ROTATION.md"), read("scripts", "sign_run.py")):
            self.assertIn("chains/", text)
            self.assertNotIn("scripts/*.py", text)

    def test_security_says_what_the_agent_tools_check_now(self):
        s = read("SECURITY.md")
        self.assertIn("`getScore` and `checkProtocol` apply the same age limit", s)

    def test_the_action_says_what_the_drop_is_measured_against(self):
        self.assertIn("not since your last build", read("action.yml"))

    def test_the_langchain_import_is_the_real_one(self):
        self.assertNotIn("from authority_risk_oracle.langchain", read("integrations", "langchain_authority_risk.py"))
        self.assertIn("from integrations.langchain_authority_risk import", read("integrations", "langchain_authority_risk.py"))


if __name__ == "__main__":
    unittest.main()
