"""Closing addition of 30/10/2026: the hash of a Solana program in impl_sources.json is the one OtterSec reports. Standard library only; no network."""
import contextlib, io, json, os, re, subprocess, sys, tempfile, unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import impl_sources  # noqa: E402


def run_main(mod, argv):
    old, buf = sys.argv, io.StringIO(); sys.argv = [mod.__name__ + ".py", *argv]
    try:
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            try: r = mod.main(); code = r if isinstance(r, int) else 0
            except SystemExit as e: code = e.code
    finally: sys.argv = old
    return code, buf.getvalue()


class TestSolanaCodeHash(unittest.TestCase):
    H = "d4" * 32

    def osec_with(self, payload):
        class R:
            def read(self_): return json.dumps(payload).encode()
        with mock.patch.object(impl_sources.urllib.request, "urlopen", return_value=R()):
            return impl_sources.osec("Prog1111111111111111111111111111111111111111")

    def test_osec_returns_the_hash_it_reads(self):
        self.assertEqual(self.osec_with({"is_verified": False, "on_chain_hash": self.H.upper(), "repo_url": "https://github.com/x/y"})["on_chain_hash"], self.H)

    def test_an_empty_or_malformed_hash_is_none_never_a_value(self):
        for bad in ("", None, "abc", "z" * 64, self.H + "00"): self.assertIsNone(self.osec_with({"is_verified": True, "on_chain_hash": bad})["on_chain_hash"], bad)

    def run_main_with(self, osec_answer, prev=None):
        with tempfile.TemporaryDirectory() as tmp:
            so = os.path.join(tmp, "so.json"); out = os.path.join(tmp, "out.json")
            json.dump({"results": [{"chain": "solana", "target": "Acct11111111111111111111111111111111111111", "via_program": "Prog1111111111111111111111111111111111111111", "kind": "squads"}]}, open(so, "w"))
            if prev: json.dump({"by_target": prev}, open(out, "w"))
            with mock.patch.object(impl_sources, "osec", return_value=osec_answer), mock.patch.object(impl_sources.time, "sleep"):
                run_main(impl_sources, ["--so", so, "--out", out]); return json.load(open(out))["by_target"]["solana:acct11111111111111111111111111111111111111"]

    def test_the_hash_becomes_the_deployed_code_hash_and_names_its_source(self):
        e = self.run_main_with({"verified": True, "match": "verified build", "name": None, "compiler": None, "verified_at": "2026-10-01", "on_chain_hash": self.H, "source": "osec", "note": None})
        self.assertEqual(e["deployed_code_sha256"], self.H); self.assertEqual(e["code_hash_source"], "OtterSec on_chain_hash"); self.assertNotIn("on_chain_hash", e); self.assertTrue(e["checked_at"])

    def test_no_hash_from_osec_means_none_and_no_source_claim(self):
        e = self.run_main_with({"verified": False, "match": None, "name": None, "compiler": None, "verified_at": None, "on_chain_hash": None, "source": "osec", "note": "x"})
        self.assertIsNone(e["deployed_code_sha256"]); self.assertNotIn("code_hash_source", e)


if __name__ == "__main__":
    unittest.main()
