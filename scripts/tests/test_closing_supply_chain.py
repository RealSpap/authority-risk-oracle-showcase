"""Closing additions of 30/10/2026: the lock file of the Python dependencies and the pinned actions of every workflow. Standard library only; no network."""
import contextlib, io, json, os, re, subprocess, sys, tempfile, unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts"))


class TestLockAndPins(unittest.TestCase):
    def test_the_lock_pins_every_requirement_with_hashes(self):
        lock = open(os.path.join(ROOT, "scripts", "requirements.lock"), encoding="utf-8").read()
        names = {re.sub(r"[-_.]+", "-", m).lower() for m in re.findall(r"(?m)^([A-Za-z0-9_.-]+)==", lock)}
        wanted = {re.sub(r"[-_.]+", "-", re.match(r"[A-Za-z0-9_.-]+", l).group(0)).lower() for l in open(os.path.join(ROOT, "scripts", "requirements.txt")) if l.strip() and not l.startswith("#")}
        self.assertTrue(wanted <= names, wanted - names)
        for block in re.split(r"\n(?=[A-Za-z0-9_.-]+==)", lock)[1:]:
            self.assertIn("--hash=sha256:", block); self.assertTrue(all(re.fullmatch(r"[0-9a-f]{64}", h) for h in re.findall(r"--hash=sha256:(\S+)", block)))

    def test_every_action_of_every_workflow_is_pinned_to_a_commit(self):
        d = os.path.join(ROOT, ".github", "workflows"); bad = []
        for n in sorted(os.listdir(d)):
            if n.endswith(".yml"): bad += [(n, m) for m in re.findall(r"uses:\s*(\S+)", open(os.path.join(d, n), encoding="utf-8").read()) if not re.search(r"@[0-9a-f]{40}$", m)]
        self.assertEqual(bad, [])


if __name__ == "__main__":
    unittest.main()
