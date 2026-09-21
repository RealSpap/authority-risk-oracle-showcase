"""
Offline tests for scripts/solana_oracle_reader.py, the keyless reader that `oracle_freshness.py` and
`live_target_counts.py` use for the native Solana program. The account layouts under test come from
`chains/solana/program/programs/solana-authority-oracle/src/lib.rs`. No network: the RPC is a fake.

Two things must hold for the freshness tool to be trusted on Solana: a Registry and its score accounts
that disagree are an ERROR (never a silently shorter list), and the base58 / PDA helpers agree with the
ones the deploy scripts already use (`chains/solana/deploy/solana_tx.py`, itself checked against the CLI).
"""
import base64
import importlib.util
import os
import struct
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))


def _load(name, rel):
    path = os.path.join(REPO_ROOT, rel)
    if os.path.dirname(path) not in sys.path:
        sys.path.insert(0, os.path.dirname(path))
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


sor = _load("aro_test_solana_oracle_reader", "scripts/solana_oracle_reader.py")
stx = _load("aro_test_solana_tx", "chains/solana/deploy/solana_tx.py")

T1 = bytes([1]) * 32
T2 = bytes([2]) * 32
ADMIN = bytes([9]) * 32
METH = bytes(range(32))


def score_bytes(target, comp, last_updated, subs=(11, 22, 33, 44, 55)):
    return (sor.anchor_discriminator("AuthorityScore") + target + bytes(subs) + bytes([comp])
            + struct.pack("<q", last_updated) + METH + bytes([254]))


def registry_bytes(tracked, max_staleness=777600, pad=2133):
    body = (sor.anchor_discriminator("Registry") + ADMIN + ADMIN + struct.pack("<q", max_staleness)
            + struct.pack("<I", len(tracked)) + b"".join(tracked) + bytes([255]))
    return body + bytes(pad - len(body))


class TestBase58(unittest.TestCase):
    def test_matches_the_deploy_scripts_encoder_including_leading_zero_bytes(self):
        for raw in (T1, ADMIN, bytes(32), bytes([0, 0, 7]) + bytes(29), bytes(range(32)), bytes([255]) * 32):
            self.assertEqual(sor.b58encode(raw), stx.b58encode(raw))

    def test_known_program_id_round_trip(self):
        self.assertEqual(sor.b58encode(stx.b58decode(sor.PROGRAM_ID, 32)), sor.PROGRAM_ID)

    def test_registry_pda_constant_is_the_programs_own_derivation(self):
        pda, _ = stx.find_program_address([b"registry"], stx.b58decode(sor.PROGRAM_ID, 32))
        self.assertEqual(stx.b58encode(pda), sor.REGISTRY_PDA)


class TestDecode(unittest.TestCase):
    def test_score_fields_land_where_the_program_writes_them(self):
        s = sor.decode_score(score_bytes(T1, 47, 1_789_909_917))
        self.assertEqual(s["target"], sor.b58encode(T1))
        self.assertEqual((s["adminKeyScore"], s["multisigScore"], s["timelockScore"], s["oracleAuthorityScore"],
                          s["crossExposureScore"], s["compositeScore"]), (11, 22, 33, 44, 55, 47))
        self.assertEqual(s["lastUpdated"], 1_789_909_917)
        self.assertEqual(s["methodologyHash"], "0x" + METH.hex())

    def test_score_account_of_the_wrong_size_or_type_is_refused(self):
        good = score_bytes(T1, 1, 1)
        self.assertEqual(len(good), sor.SCORE_ACCOUNT_SIZE)
        with self.assertRaises(ValueError):
            sor.decode_score(good[:-1])
        with self.assertRaises(ValueError):
            sor.decode_score(bytes(8) + good[8:])  # right size, wrong discriminator
        with self.assertRaises(ValueError):
            sor.decode_score(registry_bytes([T1])[:87])

    def test_registry_lists_targets_in_tracked_order_with_the_staleness_window(self):
        r = sor.decode_registry(registry_bytes([T2, T1], max_staleness=5 * 86400))
        self.assertEqual(r["tracked"], [sor.b58encode(T2), sor.b58encode(T1)])
        self.assertEqual(r["max_staleness"], 5 * 86400)
        self.assertEqual((r["admin"], r["updater"]), (sor.b58encode(ADMIN), sor.b58encode(ADMIN)))

    def test_registry_that_claims_more_targets_than_it_holds_is_refused(self):
        raw = bytearray(registry_bytes([T1]))
        struct.pack_into("<I", raw, 80, 10_000)
        with self.assertRaises(ValueError):
            sor.decode_registry(bytes(raw))

    def test_score_bytes_are_not_a_registry(self):
        with self.assertRaises(ValueError):
            sor.decode_registry(score_bytes(T1, 1, 1))


def _rpc_for(registry_owner=None, registry=True, scores=None, program=sor.PROGRAM_ID):
    """A fake `rpc_fn`: getAccountInfo answers the registry, getProgramAccounts the score accounts."""
    scores = scores if scores is not None else []
    calls = []

    def fn(url, method, params):
        calls.append(method)
        if method == "getAccountInfo":
            if not registry:
                return {"value": None}
            return {"value": {"owner": registry_owner or program, "data": [base64.b64encode(registry_bytes([T1, T2])).decode(), "base64"]}}
        if method == "getProgramAccounts":
            assert params[1]["filters"] == [{"dataSize": sor.SCORE_ACCOUNT_SIZE}], "must filter on the exact score size"
            return [{"account": {"data": [base64.b64encode(b).decode(), "base64"]}} for b in scores]
        raise AssertionError(method)

    fn.calls = calls
    return fn


class TestReadOracle(unittest.TestCase):
    def test_scores_come_back_in_registry_order_whatever_order_the_rpc_returns_them_in(self):
        fn = _rpc_for(scores=[score_bytes(T2, 20, 200), score_bytes(T1, 10, 100)])
        o = sor.read_oracle(rpc_fn=fn)
        self.assertEqual([s["compositeScore"] for s in o["scores"]], [10, 20])
        self.assertEqual(o["max_staleness"], 777600)
        self.assertEqual(len(o["tracked"]), 2)

    def test_a_tracked_target_without_a_score_account_is_an_error_not_a_shorter_list(self):
        with self.assertRaisesRegex(RuntimeError, "1 tracked without a score"):
            sor.read_oracle(rpc_fn=_rpc_for(scores=[score_bytes(T1, 10, 100)]))

    def test_a_score_nobody_tracks_is_an_error(self):
        extra = score_bytes(bytes([3]) * 32, 5, 5)
        with self.assertRaisesRegex(RuntimeError, "1 scored but not tracked"):
            sor.read_oracle(rpc_fn=_rpc_for(scores=[score_bytes(T1, 10, 100), score_bytes(T2, 20, 200), extra]))

    def test_missing_registry_is_an_error(self):
        with self.assertRaisesRegex(RuntimeError, "no Registry account"):
            sor.read_oracle(rpc_fn=_rpc_for(registry=False))

    def test_registry_owned_by_another_program_is_refused(self):
        with self.assertRaisesRegex(RuntimeError, "owned by"):
            sor.read_oracle(rpc_fn=_rpc_for(registry_owner="11111111111111111111111111111111", scores=[]))


if __name__ == "__main__":
    unittest.main()
