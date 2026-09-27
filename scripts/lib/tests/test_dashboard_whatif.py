"""The dashboard's "What would a Safe multisig score?" panel must compute exactly what the Python scorers do (parity over every threshold and owner count),
and its embedded snapshot must be a plausible list of composites. Needs node; skipped without it."""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from lib.incident_exposure import INCIDENTS, replay  # noqa: E402

PAGE = os.path.join(os.path.dirname(__file__), "..", "..", "..", "dashboard", "index.html")


def page_script():
    m = re.search(r'<script id="whatif-script">(.*?)</script>', open(PAGE).read(), re.S)
    assert m, "whatif-script not found in dashboard/index.html"
    return m.group(1)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class WhatIfParity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        path = os.path.join(cls.tmp, "whatif.js")
        with open(path, "w") as f:
            f.write(page_script())
        cls.api = path

    def run_node(self, expr):
        code = f"const a=require({json.dumps(self.api)}); console.log(JSON.stringify({expr}))"
        return json.loads(subprocess.run(["node", "-e", code], capture_output=True, text=True, check=True).stdout)

    def test_replay_matches_python_for_every_threshold_and_owner_count(self):
        js = self.run_node("(()=>{const o={};for(let n=1;n<=50;n++)for(let t=1;t<=n;t++)o[t+'/'+n]=a.replay(t,n).composite;return o})()")
        for n in range(1, 51):
            for t in range(1, n + 1):
                self.assertEqual(js[f"{t}/{n}"], replay(t, n)["compositeScore"], f"{t}-of-{n}")

    def test_documented_incidents_and_counts(self):
        rows = self.run_node("a.INCIDENTS.map(i=>[i.t,i.n,a.replay(i.t,i.n).composite,a.atOrBelow(a.replay(i.t,i.n).composite)])")
        self.assertEqual([(r[0], r[1]) for r in rows], [(t, n) for _, t, n in INCIDENTS])  # same incidents as the tool
        for (_, t, n), r in zip(INCIDENTS, rows):
            self.assertEqual(r[2], replay(t, n)["compositeScore"])
            self.assertGreater(r[3], 0)

    def test_snapshot_matches_the_finding_it_is_quoted_in(self):
        # data/finding_2026-09-26-incident-configurations-vs-published-scores.md quotes these numbers; refreshing the snapshot means updating that note (and this test).
        rows = self.run_node("[a.SNAPSHOT.composites.length, a.atOrBelow(44), a.atOrBelow(47), a.atOrBelow(52), a.atOrBelow(43)]")
        self.assertEqual(rows, [179, 91, 101, 112, 88])

    def test_snapshot_is_a_list_of_composites(self):
        snap = self.run_node("a.SNAPSHOT")
        comps = snap["composites"]
        self.assertGreater(len(comps), 100)
        self.assertTrue(all(isinstance(c, int) and 0 <= c <= 100 for c in comps))
        self.assertEqual(comps, sorted(comps))
        self.assertRegex(snap["date"], r"^\d{4}-\d{2}-\d{2}$")


if __name__ == "__main__":
    unittest.main()
