"""The public prose of this repository makes no promise that nothing here checks.

1. Reports: SECURITY.md and CONTRIBUTING.md say replies are best effort with no promised delay. No public text may promise an answer, a reply or an acknowledgement within a number of
   hours or days: nobody watches a clock on the inbox, so such a sentence is a promise to a stranger that nothing keeps.
2. Pushes: the scores are pushed by hand, at the latest every nine days (the staleness limit), and the weekly workflow is switched off. No document may say the scores are pushed weekly.
3. Pages: the signing key is compared on the provenance page of the site; the page `oracle/key/` does not exist.
No network, standard library only. Dated records (CHANGELOG.md, data/, chains/*/data/) are left as they were written."""
import os, re, unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PROSE = (".md", ".html", ".txt")
SKIP_DIRS = {".git", "node_modules", "tests", "cache", "out", "__pycache__"}
DATED = ("CHANGELOG.md",)
DATED_DIRS = ("data" + os.sep, os.path.join("chains", ""))

# a promise of a reply time: "answer ... within 72 hours", "reply within 3 days", "a response in 48 hours"
REPLY_TIME = re.compile(r"\b(?:answer|reply|respond|response|acknowledg\w+)\b[^.\n]{0,50}?\b(?:within|in|under)\s+\d+\s*(?:hours?|h|days?|business days?)\b"
                        r"|\b\d+\s*(?:hours?|h)\s+(?:answer|reply|response)\b", re.I)
WEEKLY_PUSH = re.compile(r"\b(?:pushed|re-derived and pushed|runs?)\s+weekly\b|\bweekly\s+(?:push|workflow|cron|production push)\b", re.I)


def prose_files():
    for base, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in files:
            rel = os.path.normpath(os.path.relpath(os.path.join(base, name), ROOT))
            if not name.endswith(PROSE) or rel in DATED or rel.startswith(DATED_DIRS): continue
            try:
                with open(os.path.join(base, name), encoding="utf-8") as fh: yield rel, fh.read()
            except (UnicodeDecodeError, OSError): continue


def hits(pattern):
    out, seen = [], 0
    for rel, text in prose_files():
        seen += 1
        out += ["%s:%d: %s" % (rel, n, line.strip()[:120]) for n, line in enumerate(text.split("\n"), 1) if pattern.search(line)]
    return out, seen


class TestNoPromiseNothingKeeps(unittest.TestCase):
    def test_the_patterns_find_what_they_are_meant_to_find(self):
        for s in ("You will get an answer within 72 hours.", "we reply within 3 days", "a response in 48 hours", "24 hour response", "acknowledged within 2 business days"):
            self.assertTrue(REPLY_TIME.search(s), s)
        for s in ("Pushed weekly by a workflow", "scores are re-derived and pushed weekly", "the weekly workflow only pushes", "runs weekly"):
            self.assertTrue(WEEKLY_PUSH.search(s), s)
        for s in ("replies are best effort, with no promised delay", "give it 14 days", "a summary every week", "the 72h timelock"):
            self.assertFalse(REPLY_TIME.search(s) or WEEKLY_PUSH.search(s), s)

    def test_no_text_promises_a_reply_time(self):
        found, seen = hits(REPLY_TIME)
        self.assertGreater(seen, 50, "the walk found almost no file")
        self.assertEqual(found, [], "a public text promises a reply time; SECURITY.md says there is none")

    def test_the_policy_still_says_there_is_no_promised_delay(self):
        for name in ("SECURITY.md", "CONTRIBUTING.md"):
            with open(os.path.join(ROOT, name), encoding="utf-8") as fh: self.assertIn("no promised delay", fh.read(), name)

    def test_no_text_says_the_scores_are_pushed_weekly(self):
        found, _ = hits(WEEKLY_PUSH)
        self.assertEqual(found, [], "the scores are pushed by hand, at the latest every nine days; the weekly workflow is switched off")

    def test_the_key_is_not_sent_to_a_page_that_does_not_exist(self):
        for rel, text in prose_files():
            self.assertNotIn("realspap.github.io/oracle/key", text, rel)


if __name__ == "__main__":
    unittest.main()
