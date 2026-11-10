"""No public text of this repository may promise a cadence of the Watch that the Watch does not keep.

The Watch is scheduled every 6 hours, and GitHub starts a scheduled run late by a variable amount. The real gap between two runs is a measure, written by each run in
`status.json` (`hours_since_previous_run`, `runs_7d`); a sentence written by hand ("about 2 runs a day", "every 6 hours" with nothing else) is true on the day it is written and
false a week later. So a text may say that the Watch is SCHEDULED every 6 hours, and may point to `status.json`; it may not count runs per day or say the Watch runs every 6 hours.
Dated notes keep what was true on their date (CHANGELOG.md, the notes under data/ and chains/*/data/). No network, standard library only."""
import os, re, unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SKIP_DIRS = {".git", "node_modules", "tests", "cache", "out", "__pycache__", "lib/tests"}
TEXT_SUFFIXES = (".md", ".py", ".html", ".yml", ".yaml", ".json", ".sh", ".txt", ".toml", ".cff", ".js")
DATED = ("CHANGELOG.md",)                                   # a dated record of what was true then
DATED_DIRS = ("data" + os.sep, os.path.join("chains", ""))  # dated notes (data/finding_*, chains/*/data/*)
SCHEDULED_FIELD = '"schedule": "'                           # the schedule written in latest.json is the plan, not a measure

# a count of runs, or a claim that the Watch runs at a fixed interval
COUNTS = re.compile(r"\b(?:\d+|one|two|three|four|several)(?:\s+to\s+\d+)?\s+(?:runs|passes)\s+(?:a|per)\s+day\b"
                    r"|\b(?:about|around|roughly|nearly)\s+\d+\s+a\s+day\b"
                    r"|\b(?:twice|several times|\d+ times)\s+a\s+day\b"
                    r"|\bfour\s+a\s+day\b", re.I)
EVERY = re.compile(r"every\s+(?:6|six)\s+hours", re.I)


def problems(text):
    """The forbidden formulations of one text: (line, what, the line)."""
    out = []
    for n, line in enumerate(text.split("\n"), 1):
        if COUNTS.search(line): out.append((n, "a count of runs per day", line.strip()[:120]))
        for m in EVERY.finditer(line):
            before = line[:m.start()]
            if before.lower().endswith("scheduled ") or before.endswith(SCHEDULED_FIELD): continue
            out.append((n, "'every 6 hours' without 'scheduled'", line.strip()[:120]))
    return out


def public_files():
    for base, dirs, files in os.walk(ROOT):
        rel_base = os.path.relpath(base, ROOT)
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not (rel_base == "." and d == "watch-data")]
        for name in files:
            rel = os.path.normpath(os.path.join(rel_base, name))
            if not name.endswith(TEXT_SUFFIXES) or rel in DATED or rel.startswith(DATED_DIRS): continue
            if rel.endswith(("test_public_text_cadence.py",)) or "tests" + os.sep in rel: continue
            path = os.path.join(base, name)
            if os.path.getsize(path) > 3_000_000: continue
            yield rel, path


class TestNoCadenceByHand(unittest.TestCase):
    def test_the_formulations_are_found(self):
        for text in ("about 2 runs a day since 4 Nov", "2 to 4 runs " "a day", "about 2 passes a day", "measured at about 2 a day", "usually several times " "a day",
                     "it runs four a day", "refreshed every 6 hours;", "Every six hours the watch signs", "the Watch runs every 6 hours"):
            self.assertTrue(problems(text), text)

    def test_the_true_formulations_are_not_flagged(self):
        for text in ("scheduled every 6 hours; GitHub starts a run late", "(scheduled every six hours, started late)", 'x = {"schedule": "every 6 hours (GitHub Actions)"}',
                     "refreshed at each run (scheduled every 6 hours)", "the real gap is `hours_since_previous_run` in `status.json`", "once a day, at most"):
            self.assertEqual(problems(text), [], text)

    def test_no_public_text_counts_runs_or_says_the_watch_runs_every_6_hours(self):
        found = []; seen = 0
        for rel, path in public_files():
            try:
                with open(path, encoding="utf-8") as fh: text = fh.read()
            except (UnicodeDecodeError, OSError): continue
            seen += 1
            found += ["%s:%d: %s: %s" % (rel, n, what, line) for n, what, line in problems(text)]
        self.assertGreater(seen, 100, "the walk found almost no file: the test would pass on nothing")
        self.assertEqual(found, [], "a public text writes a cadence of the Watch by hand: say 'scheduled every 6 hours' and point to status.json")

    def test_status_json_documents_the_fields_the_texts_point_to(self):
        with open(os.path.join(ROOT, "watch", "API.md"), encoding="utf-8") as fh: api = fh.read()
        for field in ("hours_since_previous_run", "runs_7d"): self.assertIn(field, api, field)


if __name__ == "__main__":
    unittest.main()
