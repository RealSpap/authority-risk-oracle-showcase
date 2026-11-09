"""scripts/cron_slot.py: the last slot of a cron at the edges (midnight, change of day, month and year, */6, lists, ranges, steps, days of the week, errors). No network, UTC only."""
import datetime as dt, os, subprocess, sys, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, SCRIPTS)
import cron_slot as C
CLI = os.path.join(SCRIPTS, "cron_slot.py")
ep = lambda s: int(dt.datetime.strptime(s, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=dt.timezone.utc).timestamp())
iso = lambda e: dt.datetime.fromtimestamp(e, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M")
def slot(cron, now): return iso(C.last_slot(cron, ep(now)))


class TestEverySixHours(unittest.TestCase):
    def test_17_every_6_hours_at_the_edges(self):
        c = "17 */6 * * *"
        self.assertEqual(slot(c, "2026-11-10T12:17:00"), "2026-11-10T12:17")      # the slot itself
        self.assertEqual(slot(c, "2026-11-10T12:16:59"), "2026-11-10T06:17")      # one second before
        self.assertEqual(slot(c, "2026-11-10T12:17:59"), "2026-11-10T12:17")      # seconds do not count
        self.assertEqual(slot(c, "2026-11-10T23:59:59"), "2026-11-10T18:17")
        self.assertEqual(slot(c, "2026-11-10T00:17:00"), "2026-11-10T00:17")
        self.assertEqual(slot(c, "2026-11-10T00:16:59"), "2026-11-09T18:17")      # midnight: the slot of the day before
        self.assertEqual(slot(c, "2026-11-10T00:00:00"), "2026-11-09T18:17")
        self.assertEqual(slot(c, "2026-11-10T05:58:38"), "2026-11-10T00:17")      # a real run of 8 Nov: 05:58 is still the slot of 00:17
        self.assertEqual(slot(c, "2026-11-10T18:30:00"), "2026-11-10T18:17")

    def test_change_of_month_and_year(self):
        c = "17 */6 * * *"
        self.assertEqual(slot(c, "2026-12-01T00:10:00"), "2026-11-30T18:17")
        self.assertEqual(slot(c, "2027-01-01T00:05:00"), "2026-12-31T18:17")
        self.assertEqual(slot(c, "2028-03-01T00:05:00"), "2028-02-29T18:17")       # leap year
        self.assertEqual(slot(c, "2027-03-01T00:05:00"), "2027-02-28T18:17")

    def test_the_daily_crons_of_the_other_workflows(self):
        for c, now, want in (("23 7 * * *", "2026-11-10T12:28:00", "2026-11-10T07:23"), ("23 7 * * *", "2026-11-10T07:22:59", "2026-11-09T07:23"),
                             ("37 6 * * *", "2026-11-10T06:37:00", "2026-11-10T06:37"), ("41 5 * * *", "2026-11-10T05:40:59", "2026-11-09T05:41"),
                             ("17 6 * * *", "2026-11-10T23:59:00", "2026-11-10T06:17"), ("0 0 * * *", "2026-11-10T00:00:00", "2026-11-10T00:00"),
                             ("0 0 * * *", "2026-11-10T23:59:59", "2026-11-10T00:00"), ("59 23 * * *", "2026-11-10T00:00:00", "2026-11-09T23:59")):
            self.assertEqual(slot(c, now), want, (c, now))


class TestSyntax(unittest.TestCase):
    def test_lists_ranges_steps(self):
        self.assertEqual(slot("5,35 * * * *", "2026-11-10T12:34:00"), "2026-11-10T12:05")
        self.assertEqual(slot("5,35 * * * *", "2026-11-10T12:35:00"), "2026-11-10T12:35")
        self.assertEqual(slot("5,35 * * * *", "2026-11-10T12:04:00"), "2026-11-10T11:35")
        self.assertEqual(slot("0 9-17 * * *", "2026-11-10T08:30:00"), "2026-11-09T17:00")
        self.assertEqual(slot("0 9-17 * * *", "2026-11-10T13:30:00"), "2026-11-10T13:00")
        self.assertEqual(slot("*/20 * * * *", "2026-11-10T12:59:00"), "2026-11-10T12:40")
        self.assertEqual(slot("10-50/20 * * * *", "2026-11-10T12:09:00"), "2026-11-10T11:50")     # 10, 30, 50
        self.assertEqual(slot("10-50/20 * * * *", "2026-11-10T12:49:00"), "2026-11-10T12:30")
        self.assertEqual(slot("7/20 * * * *", "2026-11-10T12:46:00"), "2026-11-10T12:27")           # 7, 27, 47
        self.assertEqual(slot("0 0,12 * * *", "2026-11-10T11:59:00"), "2026-11-10T00:00")
        self.assertEqual(slot("0 */6 * * *", "2026-11-10T05:59:00"), "2026-11-10T00:00")
        self.assertEqual(slot("* * * * *", "2026-11-10T12:34:56"), "2026-11-10T12:34")
        self.assertEqual(slot("0 5-7,20 * * *", "2026-11-10T19:00:00"), "2026-11-10T07:00")
        self.assertEqual(slot("  17   */6  *  *  * ", "2026-11-10T12:17:00"), "2026-11-10T12:17")      # several spaces

    def test_days_of_the_week_of_the_month_and_both(self):
        self.assertEqual(slot("30 4 * * 1", "2026-11-10T12:00:00"), "2026-11-09T04:30")              # Tuesday 10 Nov -> Monday 9 Nov
        self.assertEqual(slot("30 4 * * 1", "2026-11-09T04:30:00"), "2026-11-09T04:30")
        self.assertEqual(slot("30 4 * * 1", "2026-11-09T04:29:00"), "2026-11-02T04:30")
        self.assertEqual(slot("0 6 * * 0", "2026-11-10T12:00:00"), "2026-11-08T06:00")              # Sunday 8 Nov
        self.assertEqual(slot("0 6 * * 7", "2026-11-10T12:00:00"), "2026-11-08T06:00")              # 7 is Sunday too
        self.assertEqual(slot("0 6 * * 1-5", "2026-11-08T12:00:00"), "2026-11-06T06:00")            # Sunday -> Friday
        self.assertEqual(slot("0 0 1 * *", "2026-11-10T12:00:00"), "2026-11-01T00:00")
        self.assertEqual(slot("0 0 1 * *", "2026-12-01T00:00:00"), "2026-12-01T00:00")
        self.assertEqual(slot("0 0 31 * *", "2026-11-10T12:00:00"), "2026-10-31T00:00")            # November has no 31st
        self.assertEqual(slot("0 0 1,15 * 1", "2026-11-10T12:00:00"), "2026-11-09T00:00")           # day of month AND of week restricted: either one (Monday 9 Nov)
        self.assertEqual(slot("0 0 1,15 * 1", "2026-11-14T12:00:00"), "2026-11-09T00:00")
        self.assertEqual(slot("0 0 1,15 * 1", "2026-11-15T12:00:00"), "2026-11-15T00:00")
        self.assertEqual(slot("0 12 * 11 *", "2026-12-05T00:00:00"), "2026-11-30T12:00")           # a single month
        self.assertEqual(slot("0 0 29 2 *", "2028-03-01T00:00:00"), "2028-02-29T00:00")

    def test_errors(self):
        for c in ("", "* * * *", "* * * * * *", "60 * * * *", "* 24 * * *", "* * 0 * *", "* * 32 * *", "* * * 0 *", "* * * 13 *", "* * * * 8", "-1 * * * *",
                  "5-1 * * * *", "*/0 * * * *", "*/x * * * *", "a * * * *", "1,,2 * * * *", ",1 * * * *", "1- * * * *", "MON * * * *", "* * * JAN *", "@hourly", "*/-1 * * * *", "1.5 * * * *", "0/ * * * *", None, 5):
            with self.assertRaises(ValueError, msg=repr(c)): C.last_slot(c, ep("2026-11-10T12:00:00"))

    def test_the_errors_say_why(self):
        for c, word in (("60 * * * *", "out of bounds"), ("* 24 * * *", "out of bounds"), ("* * 32 * *", "out of bounds"), ("* * * 13 *", "out of bounds"), ("* * * * 8", "out of bounds"),
                        ("5-1 * * * *", "out of bounds"), ("*/0 * * * *", "zero step"), ("1,,2 * * * *", "empty"), ("* * * *", "5 fields")):
            with self.assertRaises(ValueError, msg=c) as cm: C.last_slot(c, ep("2026-11-10T12:00:00"))
            self.assertIn(word, str(cm.exception), c)

    def test_no_slot_in_400_days_is_an_error_not_a_value(self):
        with self.assertRaises(ValueError): C.last_slot("0 0 29 2 *", ep("2026-11-10T12:00:00"))     # the last 29 February is 20 months back
        self.assertEqual(slot("0 0 1 1 *", "2026-11-10T12:00:00"), "2026-01-01T00:00")                # yearly: within 400 days


class TestCli(unittest.TestCase):
    def run_cli(self, *a, env=None): return subprocess.run([sys.executable, "-I", CLI, *a], capture_output=True, text=True, env=env)

    def test_output_and_codes(self):
        r = self.run_cli("17 */6 * * *", str(ep("2026-11-10T12:28:00"))); self.assertEqual((r.returncode, r.stdout.strip()), (0, str(ep("2026-11-10T12:17:00"))))
        r = self.run_cli("61 * * * *", str(ep("2026-11-10T12:28:00"))); self.assertEqual(r.returncode, 1); self.assertIn("cron unreadable", r.stderr); self.assertEqual(r.stdout, "")
        r = self.run_cli("17 */6 * * *", "not a number"); self.assertEqual(r.returncode, 1)
        r = self.run_cli(); self.assertNotEqual(r.returncode, 0)

    def test_pure_utc_no_local_clock(self):
        r = self.run_cli("17 */6 * * *", str(ep("2026-11-10T12:28:00")), env=dict(os.environ, TZ="Pacific/Auckland"))
        self.assertEqual(r.stdout.strip(), str(ep("2026-11-10T12:17:00")))


if __name__ == "__main__":
    unittest.main()
