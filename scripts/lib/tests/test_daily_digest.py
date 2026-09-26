"""Guards the one fragile seam of scripts/daily_digest.py: the parse of oracle_freshness.py's per-oracle headline (no RPC)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
import daily_digest  # noqa: E402

# Lines copied from a real oracle_freshness.py run, 2026-09-26.
SAMPLES = [
    "  Robinhood Chain           63 targets, oldest update 2026-09-26 07:42 UTC, first entry turns stale in 205.4 h (2026-10-05 07:42 UTC)",
    "  Tempo (Moderato)          14 targets, oldest update 2026-09-20 19:49 UTC, first entry turns stale in 73.6 h (2026-09-29 19:49 UTC)",
    "  Solana (Devnet)           18 targets, oldest update 2026-09-26 07:18 UTC, first entry turns stale in 205.0 h (2026-10-05 07:18 UTC)",
]


class FreshnessParse(unittest.TestCase):
    def test_real_headlines_parse(self):
        rows = [daily_digest.FRESH_LINE.match(s).groupdict() for s in SAMPLES]
        self.assertEqual([r["name"] for r in rows], ["Robinhood Chain", "Tempo (Moderato)", "Solana (Devnet)"])
        self.assertEqual([r["n"] for r in rows], ["63", "14", "18"])
        self.assertAlmostEqual(float(rows[1]["hours"]), 73.6)
        self.assertEqual(rows[1]["when"], "2026-09-29 19:49 UTC")

    def test_per_index_detail_line_is_not_a_headline(self):
        self.assertIsNone(daily_digest.FRESH_LINE.match("      stale within 240 h: index 0 0xBeEff033F34C046626B8D0A041844C5d1A5409dd (2026-10-05 07:42 UTC)"))


if __name__ == "__main__":
    unittest.main()
