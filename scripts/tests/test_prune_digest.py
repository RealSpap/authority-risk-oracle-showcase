"""The daily report (watch/digest.md) is written once a day and published until the next one: a queued operation that becomes executable for more than 7 days in between must not stay in it.
No network. Each case is one that went wrong on 2026-10-21 (a Squads proposal executable for 7.4 days, still named in the report and in the review queue it carries) or the reason it could go wrong again."""
import contextlib, io, json, os, subprocess, sys, tempfile, time, unittest, warnings

warnings.simplefilter("ignore", ResourceWarning)
HERE = os.path.dirname(os.path.abspath(__file__)); SCRIPTS = os.path.join(HERE, "..")
sys.path.insert(0, SCRIPTS)
from lib import prune_digest as pd  # noqa: E402
import daily_digest  # noqa: E402
import review_queue  # noqa: E402

NOW = 2_000_000_000
DAY = 86400
MS = "7FCPaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaamvHk"          # the multisig of the stale proposal (abbreviated in the report: 7FCP\u2026mvHk)
DIGEST = """# Authority risk digest, 2026-10-21 01:20 UTC

## Needs a person, 2026-10-21T01:20:29Z: 5 item(s) (priority 1: 4, priority 2: 1, priority 3: 0); oldest 6.5 d

### Overdue: 2 priority-1 item(s) waiting for more than 2 day(s), back in the alarm
- **queued operation executable** solana an address from a lookup table (6.5 d): call: Squads proposal #128: call to an address from a lookup table via Squads v4 multisig 7FCP\u2026mvHk (7-of-15)
- **Safe AddedOwner** base 0x99249b (3.5 d): AddedOwner 0xba75\u20264520

### Something happened: read before trusting the score (4)
- **queued operation executable** solana an address from a lookup table (6.5 d): call: Squads proposal #128: call to an address from a lookup table via Squads v4 multisig 7FCP\u2026mvHk (7-of-15)
- **queued operation executable** solana USXyiSTsPEWz55pSK7sZoUL79ntoVGQbaTDT57tH6bx (0.3 d): call to the governed program: Squads proposal #253: call to the governed program via Squads v4 multisig AEb1\u2026dJGf
- **queued operation executable** solana JUPfresh111111111111111111111111111111111111 (0.1 d): call: Squads proposal #300: call to the governed program via Squads v4 multisig J3mJ\u2026vG8P
- **Safe AddedOwner** base 0x99249b (3.5 d): AddedOwner 0xba75\u20264520

### Decide (1)
- **second opinion disagrees** base 0xabc (1.0 d): x

## Timelock queue
- **executable or waiting** Compound Governance Timelock: 0x6774 sendMessage(address) ready at {WAIT} (waiting)
- **executable or waiting** Squads v4 multisig 7FCP\u2026mvHk (7-of-15, time lock 0 s): an address from a lookup table (no selector) ready at {OLD} (ready)
- **executable or waiting** Squads v4 multisig J3mJ\u2026vG8P (4-of-6, time lock 43200 s): jupfresh (no selector) ready at {RECENT} (ready)
- cleared, queued 2026-10-12: Ethena -> 0x1a44 setConfig
"""


def fmt(t): return time.strftime("%Y-%m-%d %H:%MZ", time.gmtime(t))


def digest():
    return DIGEST.replace("{WAIT}", fmt(NOW + 2 * DAY)).replace("{OLD}", fmt(NOW - 7.4 * DAY)).replace("{RECENT}", fmt(NOW - 1 * DAY))


def pending_ops(extra_ready_days=None, now=NOW):
    """what the run publishes: the proposal #300 (fresh) and a waiting timelock operation; #128 and #253 are not listed any more."""
    pend = [{"id": "squads:J3mJ:300", "index": 300, "target": "JUPfresh111111111111111111111111111111111111", "state": "ready", "ready_at": now - 1 * DAY},
            {"id": "tl:1", "target": "0x6774", "state": "waiting", "ready_at": now + 2 * DAY}]
    if extra_ready_days is not None: pend.append({"id": "tl:old", "target": "0xold", "state": "ready", "ready_at": now - extra_ready_days * DAY, "selector": "0x12345678", "decoded": "upgrade"})
    return {"results": [{"chain": "solana", "name": "Squads v4 multisig J3mJ", "family": "squads", "status": "ok", "discovered": True, "pending": pend[:1], "recent": []},
                        {"chain": "ethereum", "name": "TL", "address": "0x1", "status": "ok", "pending": pend[1:], "recent": []}]}


class TestPruneDigest(unittest.TestCase):
    def watch(self, tmp, po=None, text=None):
        w = os.path.join(tmp, "watch"); os.makedirs(w)
        json.dump(po or pending_ops(), open(os.path.join(w, "pending_ops.json"), "w")); open(os.path.join(w, "digest.md"), "w", encoding="utf-8").write(text if text is not None else digest())
        return w

    def test_a_proposal_no_longer_listed_is_dropped_from_the_report_and_the_titles_are_recounted(self):
        with tempfile.TemporaryDirectory() as tmp:
            w = self.watch(tmp); self.assertEqual(pd.prune_digest(w, NOW), ["digest.md"]); t = open(os.path.join(w, "digest.md"), encoding="utf-8").read()
        self.assertNotIn("proposal #128", t); self.assertNotIn("proposal #253", t); self.assertIn("proposal #300", t)               # the fresh one stays
        self.assertNotIn("7FCP", t)                                                                                                   # the stale 'ready at' line of the same multisig is gone
        self.assertIn("3 item(s) (priority 1: 2", t); self.assertIn("(priority 1: 2, priority 2: 1, priority 3: 0)", t)
        self.assertIn("### Overdue: 1 priority-1 item(s)", t); self.assertIn("### Something happened: read before trusting the score (2)", t); self.assertIn("### Decide (1)", t)
        self.assertIn("Compound Governance Timelock", t); self.assertIn("cleared, queued 2026-10-12", t)                              # a waiting operation and a cleared one are not touched

    def test_a_ready_at_date_older_than_a_week_is_dropped_even_without_a_proposal_number(self):
        text = "## Timelock queue\n- **executable or waiting** TL: 0xab sel ready at %s (ready)\n- **executable or waiting** TL: 0xcd sel ready at %s (ready)\n" % (fmt(NOW - 8 * DAY), fmt(NOW - 3 * DAY))
        with tempfile.TemporaryDirectory() as tmp:
            w = self.watch(tmp, text=text); pd.prune_digest(w, NOW); t = open(os.path.join(w, "digest.md"), encoding="utf-8").read()
        self.assertNotIn("0xab", t); self.assertIn("0xcd", t)

    def test_an_item_for_a_target_with_no_listed_operation_is_dropped(self):
        text = "## Needs a person, x: 2 item(s) (priority 1: 2, priority 2: 0, priority 3: 0); oldest 2.0 d\n\n### Something happened: read before trusting the score (2)\n- **queued upgrade waiting** ethereum 0xgone (2.0 d): z\n- **queued upgrade waiting** ethereum 0x6774 (1.0 d): z\n"
        with tempfile.TemporaryDirectory() as tmp:
            w = self.watch(tmp, text=text); pd.prune_digest(w, NOW); t = open(os.path.join(w, "digest.md"), encoding="utf-8").read()
        self.assertNotIn("0xgone", t); self.assertIn("0x6774", t); self.assertIn("1 item(s) (priority 1: 1", t)

    def test_idempotent_and_silent_when_there_is_nothing_to_drop(self):
        with tempfile.TemporaryDirectory() as tmp:
            w = self.watch(tmp); pd.prune_digest(w, NOW); once = open(os.path.join(w, "digest.md"), encoding="utf-8").read()
            self.assertEqual(pd.prune_digest(w, NOW), []); self.assertEqual(open(os.path.join(w, "digest.md"), encoding="utf-8").read(), once)

    def test_nothing_is_guessed_when_a_file_is_missing_or_unreadable(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(pd.prune_digest(os.path.join(tmp, "nowhere"), NOW), [])
            w = self.watch(tmp); open(os.path.join(w, "pending_ops.json"), "w").write("{not json"); before = open(os.path.join(w, "digest.md"), encoding="utf-8").read()
            self.assertEqual(pd.prune_digest(w, NOW), []); self.assertEqual(open(os.path.join(w, "digest.md"), encoding="utf-8").read(), before)      # an unreadable queue drops nothing

    def test_the_command_line_prints_file_names_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            w = self.watch(tmp); r = subprocess.run([sys.executable, os.path.join(SCRIPTS, "lib", "prune_digest.py"), "--watch", w, "--now", str(NOW)], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0); self.assertEqual(r.stdout.strip(), "files rewritten: digest.md")


class TestGeneratorsDoNotListAWeekOldOperation(unittest.TestCase):
    """Defence in depth: whatever wrote pending_ops.json, neither the report nor the review queue lists an operation executable for more than 7 days."""

    def test_the_review_queue_does_not_list_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            w = os.path.join(tmp, "watch"); d = os.path.join(tmp, "data"); os.makedirs(w); os.makedirs(d)
            json.dump(pending_ops(extra_ready_days=8, now=time.time()), open(os.path.join(w, "pending_ops.json"), "w"))     # the file as an unfiltered writer would leave it
            out, md = os.path.join(w, "review_queue.json"), os.path.join(w, "review_queue.md")
            with contextlib.redirect_stdout(io.StringIO()):
                sys.argv = ["review_queue.py", "--watch", w, "--data", d, "--out", out, "--md", md]; review_queue.main()
            txt = open(out, encoding="utf-8").read() + open(md, encoding="utf-8").read()
        self.assertIn("queued operation executable", txt)      # the fresh ready operation (#300) is there
        self.assertNotIn("0xold", txt)                                                  # the 8-day-old one is not

    def test_the_review_queue_run_also_prunes_the_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            w = os.path.join(tmp, "watch"); d = os.path.join(tmp, "data"); os.makedirs(w); os.makedirs(d)
            json.dump(pending_ops(now=time.time()), open(os.path.join(w, "pending_ops.json"), "w")); open(os.path.join(w, "digest.md"), "w", encoding="utf-8").write(digest().replace(fmt(NOW - 7.4 * DAY), fmt(time.time() - 7.4 * DAY)))
            out, md = os.path.join(w, "review_queue.json"), os.path.join(w, "review_queue.md")
            with contextlib.redirect_stdout(io.StringIO()) as o:
                sys.argv = ["review_queue.py", "--watch", w, "--data", d, "--out", out, "--md", md]; review_queue.main()
            t = open(os.path.join(w, "digest.md"), encoding="utf-8").read()
        self.assertNotIn("proposal #128", t); self.assertIn("daily report: lines of operations no longer listed dropped from digest.md", o.getvalue())

    def test_the_report_does_not_list_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, "pending_ops.json"); po = pending_ops(extra_ready_days=8)
            for r in po["results"]: r["name"] = "TL " + r["name"]; r["discovered"] = True
            json.dump(po, open(p, "w")); real = time.time
            time.time = lambda: NOW
            try: act, _recent, _unread = daily_digest.discovered_from_file(p)
            finally: time.time = real
        ids = sorted(x[1]["id"] for x in act); self.assertIn("tl:1", ids); self.assertNotIn("tl:old", ids)

    def test_the_report_does_not_list_it_from_the_timelock_scan_either(self):
        real_w, real_c, real_t, real_d = daily_digest.check_pending_ops.WATCHLIST, daily_digest.check_pending_ops.check_timelock, time.time, daily_digest.discovered_from_file
        daily_digest.check_pending_ops.WATCHLIST = [("x",)]
        daily_digest.check_pending_ops.check_timelock = lambda *a: {"status": "ok", "name": "TL", "pending": [{"id": "tl:old", "target": "0xold", "state": "ready", "ready_at": NOW - 8 * DAY}, {"id": "tl:1", "target": "0x6774", "state": "waiting", "ready_at": NOW + DAY}], "recent": []}
        daily_digest.discovered_from_file = lambda *a, **k: ([], [], []); time.time = lambda: NOW
        try: act, _r, _u = daily_digest.pending(14)
        finally: daily_digest.check_pending_ops.WATCHLIST, daily_digest.check_pending_ops.check_timelock, time.time, daily_digest.discovered_from_file = real_w, real_c, real_t, real_d
        ids = sorted(x[1]["id"] for x in act); self.assertEqual(ids, ["tl:1"])


if __name__ == "__main__":
    unittest.main()
