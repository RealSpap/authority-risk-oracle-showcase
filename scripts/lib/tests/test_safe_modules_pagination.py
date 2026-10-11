"""read_modules must not skip a module between two pages (Safe v1.3.0 returns the first unread module in `next`, v1.4.0 the last read one)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import safe_modules  # noqa: E402

SENT = safe_modules.SENTINEL
MODS = ["0x" + f"{i:040x}" for i in range(1, 13)]   # 12 modules, page size 10 in the code under test


def fake_call_raw(version):
    def call_raw(w3, safe, abi, name, start, page, retries=4):
        after = [] if start.lower() == SENT.lower() else [m for m in MODS if int(m, 16) <= int(start, 16)]
        pos = 0 if start.lower() == SENT.lower() else MODS.index(next(m for m in MODS if m.lower() == start.lower())) + 1
        found = MODS[pos:pos + page]
        rest = MODS[pos + page:]
        if not rest:
            nxt = SENT
        elif version == "1.3.0":
            nxt = rest[0]            # the first module not returned
        else:
            nxt = found[-1]          # v1.4.0: the last module returned
        return found, nxt
    return call_raw


class TestPagination(unittest.TestCase):
    def run_version(self, version):
        saved = safe_modules.call_raw
        self.addCleanup(lambda: setattr(safe_modules, "call_raw", saved))
        safe_modules.call_raw = fake_call_raw(version)
        got = safe_modules.read_modules(None, "0x" + "ee" * 20)
        return [m.lower() for m in got]

    def test_no_module_is_skipped_on_either_safe_version(self):
        for v in ("1.3.0", "1.4.0"):
            self.assertEqual(self.run_version(v), [m.lower() for m in MODS], v)


if __name__ == "__main__":
    unittest.main()
