"""Tests for scripts/lib/code_review.py (no network: openers are injected)."""
import io
import json
import os
import sys
import unittest
import urllib.error

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..")))
import code_review as cr  # noqa: E402


def dispatcher(*sels, junk=b""):
    """Runtime-like code: DUP1 PUSH4 <sel> EQ PUSH2 <dest> JUMPI for each selector, then some data."""
    body = b""
    for s in sels:
        body += b"\x80\x63" + bytes.fromhex(s[2:]) + b"\x14\x61\x00\x10\x57"
    return body + junk


def with_metadata(code, solc=(0, 8, 30), ipfs_digest=b"\x11" * 32):
    cbor = b"\xa2\x64ipfs\x58\x22" + b"\x12\x20" + ipfs_digest + b"\x64solc\x43" + bytes(solc)
    return code + cbor + len(cbor).to_bytes(2, "big")


class Response:
    def __init__(self, payload):
        self._data = json.dumps(payload).encode()

    def __enter__(self):
        return io.BytesIO(self._data)

    def __exit__(self, *a):
        return False


def opener_for(routes):
    """routes: {substring: payload or Exception}; the first matching substring answers."""
    calls = []

    def opener(req, timeout=None):
        url = req.full_url
        calls.append(url)
        for sub, val in routes.items():
            if sub in url:
                if isinstance(val, Exception):
                    raise val
                return Response(val)
        raise urllib.error.HTTPError(url, 404, "not found", {}, None)

    opener.calls = calls
    return opener


class TestSelectors(unittest.TestCase):
    def test_a_compared_selector_is_found_and_plain_data_is_not(self):
        code = dispatcher("0xa9059cbb", "0x70a08231", junk=b"\x63\xde\xad\xbe\xef\x60\x00")
        self.assertEqual(cr.selectors(code), {"0xa9059cbb", "0x70a08231"})

    def test_the_dup2_eq_form_is_recognized(self):
        code = b"\x63\x01\x02\x03\x04\x81\x14\x61\x00\x10\x57"
        self.assertEqual(cr.selectors(code), {"0x01020304"})

    def test_empty_and_tiny_code(self):
        self.assertEqual(cr.selectors(b""), set())
        self.assertEqual(cr.selectors(b"\x63\x01"), set())


class TestMetadata(unittest.TestCase):
    def test_solc_version_and_ipfs_hash_are_read_from_the_cbor_tail(self):
        meta = cr.compiler_metadata(with_metadata(b"\x60\x80" * 40, solc=(0, 8, 36)))
        self.assertEqual(meta["solc"], "0.8.36")
        self.assertTrue(meta["ipfs"].startswith("Qm") and len(meta["ipfs"]) == 46)

    def test_different_digests_give_different_ipfs_hashes(self):
        a = cr.compiler_metadata(with_metadata(b"\x60\x80", ipfs_digest=b"\x01" * 32))["ipfs"]
        b = cr.compiler_metadata(with_metadata(b"\x60\x80", ipfs_digest=b"\x02" * 32))["ipfs"]
        self.assertNotEqual(a, b)

    def test_code_without_a_tail_gives_nothing_and_never_raises(self):
        self.assertEqual(cr.compiler_metadata(b"\x60\x80\x60\x40"), {"solc": None, "ipfs": None, "swarm": False})
        self.assertEqual(cr.compiler_metadata(b""), {"solc": None, "ipfs": None, "swarm": False})


class TestCompare(unittest.TestCase):
    def test_added_and_removed_selectors_and_compiler_change(self):
        old = with_metadata(dispatcher("0xaaaaaaaa", "0xbbbbbbbb"), solc=(0, 8, 30), ipfs_digest=b"\x01" * 32)
        new = with_metadata(dispatcher("0xaaaaaaaa", "0xcccccccc", "0xdddddddd"), solc=(0, 8, 36), ipfs_digest=b"\x02" * 32)
        r = cr.compare(old, new)
        self.assertEqual((r["added"], r["removed"], r["kept"]), (["0xcccccccc", "0xdddddddd"], ["0xbbbbbbbb"], 1))
        self.assertEqual((r["metadataOld"]["solc"], r["metadataNew"]["solc"]), ("0.8.30", "0.8.36"))
        self.assertFalse(r["identicalCode"])

    def test_identical_code_is_reported_as_such(self):
        code = with_metadata(dispatcher("0xaaaaaaaa"))
        r = cr.compare(code, code)
        self.assertTrue(r["identicalCode"])
        self.assertEqual(cr.summarize(r), ["the two implementations are byte-identical (the address changed, the code did not)"])

    def test_same_selectors_different_bytes_is_a_config_change_not_a_new_api(self):
        # e.g. an immutable (a price feed, a cap) baked into the code: the API surface is the same
        a = with_metadata(dispatcher("0xaaaaaaaa", junk=b"\x00" * 32))
        b = with_metadata(dispatcher("0xaaaaaaaa", junk=b"\x01" * 32))
        r = cr.compare(a, b)
        self.assertEqual((r["added"], r["removed"], r["identicalCode"]), ([], [], False))
        self.assertIn("0 added, 0 removed", cr.summarize(r)[0])

    def test_summary_uses_resolved_names_and_keeps_unknown_selectors_as_hex(self):
        r = cr.compare(with_metadata(dispatcher("0xaaaaaaaa")), with_metadata(dispatcher("0xaaaaaaaa", "0x11111111", "0x22222222")))
        text = "\n".join(cr.summarize(r, {"0x11111111": ["setNav(uint256)"], "0x22222222": None}))
        self.assertIn("setNav(uint256)", text)
        self.assertIn("0x22222222", text)


class TestResolveNames(unittest.TestCase):
    def test_names_come_from_the_database_and_misses_are_none(self):
        payload = {"result": {"function": {"0x11111111": [{"name": "setNav(uint256)"}], "0x22222222": None}}}
        out = cr.resolve_names({"0x11111111", "0x22222222"}, opener=opener_for({"openchain": payload}))
        self.assertEqual(out, {"0x11111111": ["setNav(uint256)"], "0x22222222": None})

    def test_an_unreachable_database_gives_none_for_everything_never_a_guess(self):
        out = cr.resolve_names({"0x11111111"}, opener=opener_for({"openchain": OSError("down")}))
        self.assertEqual(out, {"0x11111111": None})

    def test_nothing_to_resolve(self):
        self.assertEqual(cr.resolve_names(set()), {})


VERIFIED = {"status": "1", "message": "OK", "result": [{"SourceCode": "contract X {}", "ABI": "[]", "ContractName": "YuzuUSDV3"}]}
NOT_VERIFIED = {"status": "1", "message": "OK", "result": [{"SourceCode": "", "ABI": "Contract source code not verified", "ContractName": ""}]}
SOURCIFY_404 = urllib.error.HTTPError("u", 404, "nf", {}, None)


class TestVerification(unittest.TestCase):
    def test_plasma_is_answered_by_routescan_and_a_hit_there_is_a_verification(self):
        res = cr.verification(9745, "0xabc", opener=opener_for({"sourcify": SOURCIFY_404, "routescan": VERIFIED}), environ={})
        self.assertEqual([(r["source"], r["status"]) for r in res], [("sourcify", "not verified"), ("routescan", "verified")])
        self.assertTrue(cr.verified_anywhere(res))

    def test_plasma_not_verified_everywhere_it_can_be_asked_is_reported_as_not_verified(self):
        res = cr.verification(9745, "0xabc", opener=opener_for({"sourcify": SOURCIFY_404, "routescan": NOT_VERIFIED}), environ={})
        self.assertIs(cr.verified_anywhere(res), False)

    def test_robinhood_chain_can_never_be_called_unverified_because_its_explorers_are_not_queryable(self):
        res = cr.verification(4663, "0xabc", opener=opener_for({"sourcify": SOURCIFY_404}), environ={})
        self.assertIsNone(cr.verified_anywhere(res))
        self.assertTrue(any(r["status"].startswith("unknown") and "bot check" in r["status"] for r in res))

    def test_a_sourcify_hit_is_a_verification_even_where_explorers_are_unqueryable(self):
        res = cr.verification(4663, "0xabc", opener=opener_for({"sourcify": {"match": "exact_match", "compilation": {"name": "GnosisSafe"}}}), environ={})
        self.assertIs(cr.verified_anywhere(res), True)

    def test_monad_without_a_key_is_unknown_and_with_a_key_the_etherscan_answer_counts(self):
        without = cr.verification(143, "0xabc", opener=opener_for({"sourcify": SOURCIFY_404}), environ={})
        self.assertIsNone(cr.verified_anywhere(without))
        self.assertTrue(any("ETHERSCAN_API_KEY" in r["status"] for r in without))
        opener = opener_for({"sourcify": SOURCIFY_404, "etherscan.io/v2": VERIFIED})
        with_key = cr.verification(143, "0xabc", opener=opener, environ={"ETHERSCAN_API_KEY": "k"})
        self.assertIs(cr.verified_anywhere(with_key), True)
        self.assertEqual([u for u in opener.calls if "apikey=k" in u], [u for u in opener.calls if "etherscan.io/v2" in u])  # only Etherscan gets it
        self.assertEqual(len([u for u in opener.calls if "etherscan.io/v2" in u]), 1)

    def test_a_key_is_never_sent_to_sourcify_or_routescan(self):
        opener = opener_for({"sourcify": SOURCIFY_404, "routescan": NOT_VERIFIED, "etherscan.io/v2": NOT_VERIFIED})
        cr.verification(1, "0xabc", opener=opener, environ={"ETHERSCAN_API_KEY": "SECRETKEY"})
        for url in opener.calls:
            if "etherscan.io" not in url:
                self.assertNotIn("SECRETKEY", url)

    def test_ethereum_is_covered_by_sourcify_and_routescan_with_no_unknown_placeholder(self):
        res = cr.verification(1, "0xabc", opener=opener_for({"sourcify": SOURCIFY_404, "routescan": NOT_VERIFIED}), environ={})
        self.assertEqual({r["source"] for r in res}, {"sourcify", "routescan"})
        self.assertIs(cr.verified_anywhere(res), False)

    def test_an_unreachable_source_is_unknown_never_not_verified(self):
        res = cr.verification(9745, "0xabc", opener=opener_for({"sourcify": OSError("down"), "routescan": OSError("down")}), environ={})
        self.assertIsNone(cr.verified_anywhere(res))


class TestTables(unittest.TestCase):
    def test_every_unqueryable_chain_states_a_reason(self):
        for chain, reason in cr.UNQUERYABLE_EXPLORERS.items():
            self.assertTrue(reason and chain not in cr.ROUTESCAN_CHAINS)
            self.assertNotIn(chr(0x2014), reason)


if __name__ == "__main__":
    unittest.main()
