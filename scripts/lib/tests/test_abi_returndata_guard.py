"""
Tests for the ABI return-data size guard (scripts/lib/abi_returndata_guard.py) and the audit tool built on it
(scripts/audit_abi_returndata.py).

The trap: `eth_abi.decode(["uint256"], data)` and web3's `contract.functions.f().call()` return the FIRST 32-byte word of `data` and
ignore the rest, so a getter that returns a struct (or several values) read with a single-value ABI hands back its first word as
if it were the answer (2026-09-20: `getScore(address)` read as `uint256` gave `adminKeyScore = 3` instead of `compositeScore`).
No network access: return data is hand-built, web3's `eth_call` is replaced by a stand-in.
"""
import os
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts", "lib"))
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))

import eth_abi  # noqa: E402
from eth_abi import encode  # noqa: E402
from eth_abi.codec import ABICodec  # noqa: E402
from eth_abi.exceptions import DecodingError, InsufficientDataBytes  # noqa: E402
from web3 import Web3  # noqa: E402
from web3.exceptions import BadFunctionCallOutput  # noqa: E402

import abi_returndata_guard as g  # noqa: E402

SCORE_STRUCT = "(uint8,uint8,uint8,uint8,uint8,uint8,uint64,bytes32)"


def words(*values):
    return b"".join(int(v).to_bytes(32, "big") for v in values)


class TestClassify(unittest.TestCase):
    def test_exact_static_sizes_are_accepted(self):
        for types, data in ((["uint256"], words(1)), (["address", "uint256"], words(1, 2)), (["bool"], words(1)),
                            (["bytes32"], words(7)), ([SCORE_STRUCT], words(*range(8))), (["uint256[3]"], words(1, 2, 3)),
                            (["(uint256,(uint256,uint256))"], words(1, 2, 3)), (["uint256[2][2]"], words(1, 2, 3, 4)),
                            (["uint256", "uint256"], words(1, 2)), ([], b"anything")):
            with self.subTest(types=types):
                self.assertIsNone(g.classify(types, data))

    def test_a_struct_read_with_a_single_value_abi_is_the_trap(self):
        kind, msg = g.classify(["uint256"], words(*range(8)))
        self.assertEqual(kind, "more")
        self.assertIn("256 bytes returned", msg)
        self.assertIn("exactly 32", msg)

    def test_fewer_bytes_than_declared(self):
        self.assertEqual(g.classify(["uint256", "uint256"], words(1))[0], "fewer")
        self.assertEqual(g.classify(["uint256"], b"x" * 31)[0], "fewer")

    def test_empty_data_for_a_function_with_outputs_is_reported_as_empty(self):
        self.assertEqual(g.classify(["address"], b"")[0], "empty")
        self.assertIsNone(g.classify([], b""))

    def test_dynamic_outputs_need_their_head_and_may_have_a_tail(self):
        self.assertIsNone(g.classify(["string"], encode(["string"], ["hello"])))
        self.assertIsNone(g.classify(["address[]"], encode(["address[]"], [["0x" + "11" * 20, "0x" + "22" * 20]])))
        self.assertIsNone(g.classify(["uint256", "string"], encode(["uint256", "string"], [5, "x" * 90])))
        self.assertEqual(g.classify(["string"], b"x" * 20)[0], "head")
        self.assertEqual(g.classify(["uint256", "string"], words(1))[0], "head")

    def test_a_getter_returning_several_values_read_with_one_dynamic_output_is_the_layout_trap(self):
        # (address[], uint256) read as address[]: decodes without error, the uint256 silently disappears
        real = encode(["address[]", "uint256"], [["0x" + "11" * 20, "0x" + "22" * 20], 3])
        self.assertEqual(len(real), 160)
        kind, msg = g.classify(["address[]"], real)
        self.assertEqual(kind, "layout")
        self.assertIn("canonical encoding takes 128", msg)
        # the same data read with the ABI it really has is fine
        self.assertIsNone(g.classify(["address[]", "uint256"], real))
        # (address[], address) read as address[] (the shape of scripts/lib/safe_modules.py's modules ABI)
        real2 = encode(["address[]", "address"], [["0x" + "11" * 20], "0x" + "22" * 20])
        self.assertEqual(g.classify(["address[]"], real2)[0], "layout")
        self.assertIsNone(g.classify(["address[]", "address"], real2))

    def test_canonical_dynamic_encodings_are_accepted(self):
        a, b = "0x" + "11" * 20, "0x" + "22" * 20
        for types, values in ((["address[]"], [[a, b]]), (["address[]"], [[]]), (["string"], ["hello" * 30]), (["bytes"], [b"\x01\x02"]),
                              (["(uint256,string)"], [(5, "x")]), (["(address,uint256)[]"], [[(a, 1), (b, 2)]]),
                              (["string[]"], [["a", "bb", "ccc"]]), (["uint256[][]"], [[[1, 2], [3]]]),
                              (["uint256", "string", "address[]"], [1, "s", [a]])):
            with self.subTest(types=types):
                self.assertIsNone(g.classify(types, encode(types, values)))

    def test_trailing_bytes_after_a_dynamic_answer_are_a_layout_mismatch(self):
        self.assertEqual(g.classify(["string"], encode(["string"], ["x"]) + b"\x00" * 32)[0], "layout")

    def test_data_that_cannot_be_decoded_is_left_to_the_original_decoder(self):
        broken = (32).to_bytes(32, "big") + (1000).to_bytes(32, "big")   # a string that claims 1000 bytes
        self.assertIsNone(g.classify(["string"], broken))

    def test_expected_size_flattens_nested_static_types(self):
        self.assertEqual(g.expected_size([SCORE_STRUCT]), (256, True))
        self.assertEqual(g.expected_size(["uint256[3]", "address"]), (128, True))
        self.assertEqual(g.expected_size(["uint256[2][2]"]), (128, True))
        self.assertEqual(g.expected_size(["uint256", "bytes"]), (64, False))
        self.assertEqual(g.expected_size(["(uint256,string)"]), (32, False))

    def test_check_return_is_the_message_of_classify(self):
        self.assertIsNone(g.check_return(["uint256"], words(1)))
        self.assertEqual(g.check_return(["uint256"], words(1, 2)), g.classify(["uint256"], words(1, 2))[1])


class _Installed(unittest.TestCase):
    def setUp(self):
        import io
        patcher = mock.patch.object(sys, "stderr", io.StringIO())     # the guard logs each refusal to stderr: keep the test output clean
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        g.uninstall()


class TestRecordMode(_Installed):
    def test_decoding_is_unchanged_and_the_mismatch_names_its_caller(self):
        original = eth_abi.decode
        g.install("record")
        self.assertIsNot(eth_abi.decode, original)
        self.assertEqual(eth_abi.decode(["uint256"], words(3, 0, 0, 100, 100, 1, 1789864661, 5)), (3,))   # still the first word
        recs = g.records()
        self.assertEqual(len(recs), 1)
        self.assertEqual((recs[0]["kind"], recs[0]["bytes"], recs[0]["count"]), ("more", 256, 1))
        self.assertTrue(recs[0]["caller"].startswith(os.path.relpath(__file__)), recs[0]["caller"])

    def test_web3_contract_calls_are_covered_too(self):
        g.install("record")
        w3 = Web3()
        contract = w3.eth.contract(address="0x" + "11" * 20, abi=[
            {"name": "getScore", "type": "function", "stateMutability": "view", "inputs": [{"type": "address"}], "outputs": [{"type": "uint256"}]}])
        with mock.patch.object(type(w3.eth), "call", return_value=words(3, 0, 0, 100, 100, 1, 1789864661, 5)):
            value = contract.functions.getScore("0x" + "22" * 20).call()
        self.assertEqual(value, 3)                       # the silent first word: what the trap looks like without the guard
        self.assertEqual([r["kind"] for r in g.records()], ["more"])

    def test_the_same_mismatch_is_counted_not_repeated(self):
        g.install("record")
        for _ in range(3):
            eth_abi.decode(["uint256"], words(1, 2))
        self.assertEqual([r["count"] for r in g.records()], [3])

    def test_correct_sizes_are_counted_as_checked_and_never_recorded(self):
        g.install("record")
        eth_abi.decode(["uint256"], words(1))
        eth_abi.decode(["string"], encode(["string"], ["ok"]))
        self.assertEqual(g.records(), [])

    def test_the_result_file_holds_the_count_and_the_mismatches(self):
        import json
        import tempfile
        sink = os.path.join(tempfile.mkdtemp(), "out.json")
        g.install("record", sink)
        eth_abi.decode(["uint256"], words(1))
        eth_abi.decode(["uint256"], words(1, 2))
        g.dump()
        with open(sink) as f:
            data = json.load(f)
        self.assertEqual(data["checked"], 2)
        self.assertEqual(len(data["mismatches"]), 1)


class TestRaiseMode(_Installed):
    def test_an_over_long_answer_raises_a_decoding_error(self):
        g.install("raise")
        with self.assertRaises(g.ReturnDataSizeMismatch) as cm:
            eth_abi.decode(["uint256"], words(1, 2))
        self.assertIsInstance(cm.exception, DecodingError)
        self.assertIsInstance(cm.exception, ValueError)

    def test_the_codec_used_by_web3_raises_too(self):
        g.install("raise")
        with self.assertRaises(g.ReturnDataSizeMismatch):
            Web3().codec.decode(["uint256"], words(1, 2))

    def test_a_dynamic_layout_mismatch_raises_and_is_recorded_in_record_mode(self):
        real = encode(["address[]", "uint256"], [["0x" + "11" * 20], 3])
        g.install("raise")
        with self.assertRaises(g.ReturnDataSizeMismatch):
            eth_abi.decode(["address[]"], real)
        g.uninstall()
        g.install("record")
        self.assertEqual(eth_abi.decode(["address[]"], real)[0][0].lower(), "0x" + "11" * 20)   # decoding unchanged
        self.assertEqual([r["kind"] for r in g.records()], ["layout"])

    def test_several_answer_sizes_from_one_call_site_give_one_stderr_line(self):
        import io
        g.install("raise")
        buf = io.StringIO()
        with mock.patch.object(sys, "stderr", buf):
            for extra in range(2, 40):                     # one call site, 38 different wrong sizes (a scorer looping over many Safes)
                with self.assertRaises(g.ReturnDataSizeMismatch):
                    eth_abi.decode(["uint256"], words(*range(extra)))
        self.assertEqual(buf.getvalue().count("ABI return-data guard: REFUSED"), 1)
        self.assertEqual(len(g._state["logged"]), 1)

    def test_a_refusal_is_logged_to_stderr_once_per_call_site(self):
        import io
        g.install("raise")
        buf = io.StringIO()
        with mock.patch.object(sys, "stderr", buf):
            for _ in range(3):
                with self.assertRaises(g.ReturnDataSizeMismatch):
                    eth_abi.decode(["uint256"], words(1, 2))
        out = buf.getvalue()
        self.assertEqual(out.count("ABI return-data guard: REFUSED"), 1)
        self.assertIn(os.path.relpath(__file__), out)

    def test_a_web3_contract_call_gets_web3s_usual_bad_output_error(self):
        g.install("raise")
        w3 = Web3()
        contract = w3.eth.contract(address="0x" + "11" * 20, abi=[
            {"name": "getScore", "type": "function", "stateMutability": "view", "inputs": [{"type": "address"}], "outputs": [{"type": "uint256"}]}])
        with mock.patch.object(type(w3.eth), "call", return_value=words(3, 0, 0, 100, 100, 1, 1789864661, 5)):
            with self.assertRaises(BadFunctionCallOutput):
                contract.functions.getScore("0x" + "22" * 20).call()

    def test_the_right_abi_reads_the_whole_struct(self):
        g.install("raise")
        w3 = Web3()
        contract = w3.eth.contract(address="0x" + "11" * 20, abi=[
            {"name": "getScore", "type": "function", "stateMutability": "view", "inputs": [{"type": "address"}], "outputs": [{
                "type": "tuple", "components": [{"name": n, "type": t} for n, t in (
                    ("a", "uint8"), ("b", "uint8"), ("c", "uint8"), ("d", "uint8"), ("e", "uint8"), ("f", "uint8"), ("t", "uint64"), ("h", "bytes32"))]}]}])
        with mock.patch.object(type(w3.eth), "call", return_value=words(3, 0, 0, 100, 100, 1, 1789864661, 5)):
            value = contract.functions.getScore("0x" + "22" * 20).call()
        self.assertEqual(tuple(value[:6]), (3, 0, 0, 100, 100, 1))

    def test_empty_data_is_left_to_the_original_decoder(self):
        g.install("raise")
        with self.assertRaises(InsufficientDataBytes):
            eth_abi.decode(["uint256"], b"")

    def test_correct_answers_are_untouched(self):
        g.install("raise")
        self.assertEqual(eth_abi.decode(["uint256", "address"], words(9, int("11" * 20, 16)))[0], 9)
        self.assertEqual(eth_abi.decode(["string"], encode(["string"], ["hello"])), ("hello",))


class TestTheGuardImportedUnderTwoNames(_Installed):
    def _second_module(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("abi_returndata_guard_second_name", g.__file__)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_a_second_module_object_does_not_stack_a_second_patch_and_keeps_the_true_original(self):
        original = g._ORIGINAL_DECODE
        g.install("raise")
        patched = ABICodec.decode
        second = self._second_module()
        self.assertIs(second._ORIGINAL_DECODE, original)                  # not the first module's wrapper
        second.install("raise")                                            # no-op: already patched
        self.assertIs(ABICodec.decode, patched)
        # the second module's own layout check still works (it decodes with the real original, not through the first guard)
        real = encode(["address[]", "uint256"], [["0x" + "11" * 20], 3])
        self.assertEqual(second.classify(["address[]"], real)[0], "layout")
        # and the one installed guard refuses
        with self.assertRaises(g.ReturnDataSizeMismatch):
            eth_abi.decode(["uint256"], words(1, 2))

    def test_uninstalling_the_first_still_restores_the_class(self):
        g.install("raise")
        self._second_module()
        g.uninstall()
        self.assertIs(ABICodec.decode, g._ORIGINAL_DECODE)
        self.assertEqual(eth_abi.decode(["uint256"], words(1, 2)), (1,))


class TestKnownLimits(unittest.TestCase):
    def test_uint256_equal_to_32_before_a_dynamic_output_is_a_valid_encoding_of_the_narrow_abi_itself(self):
        # (uint256 = 32, bytes) read as [bytes]: the first word reads as the offset, the rest re-encodes to the same bytes.
        # Documented in the note ("Not claimed"): no check on the bytes can tell the two apart.
        data = encode(["uint256", "bytes"], [32, b"x" * 20])
        self.assertIsNone(g.classify(["bytes"], data))
        # any other leading value is caught: either the guard flags the layout, or the value is no valid offset and the original decoder
        # raises by itself (classify leaves undecodable data to it)
        for lead in (0, 1, 7, 64, 33):
            with self.subTest(lead=lead):
                data = encode(["uint256", "bytes"], [lead, b"x" * 20])
                if g.classify(["bytes"], data) is None:
                    with self.assertRaises(Exception):
                        g._ORIGINAL_DECODE(eth_abi.abi.default_codec, ["bytes"], data)

    def test_a_non_canonical_layout_of_the_same_total_length_is_not_seen(self):
        a, b = "0x" + "11" * 20, "0x" + "22" * 20
        canonical = encode(["address[]", "address[]"], [[a], [b]])
        # tails swapped (legal, non-canonical): offsets 160 and 96, same total length
        first, second = canonical[64:128], canonical[128:192]
        swapped = (160).to_bytes(32, "big") + (96).to_bytes(32, "big") + second + first
        self.assertEqual(len(swapped), len(canonical))
        self.assertIsNone(g.classify(["address[]", "address[]"], swapped))


class TestInstallUninstall(_Installed):
    def test_uninstall_restores_the_original_functions(self):
        original_method, original_module = ABICodec.decode, eth_abi.decode
        g.install("raise")
        self.assertIsNot(ABICodec.decode, original_method)
        g.uninstall()
        self.assertIs(ABICodec.decode, original_method)
        self.assertIs(eth_abi.decode, original_module)
        self.assertEqual(eth_abi.decode(["uint256"], words(1, 2)), (1,))   # the trap is back once the guard is removed

    def test_install_twice_does_not_stack_the_patch(self):
        g.install("record")
        first = ABICodec.decode
        g.install("raise")
        self.assertIs(ABICodec.decode, first)
        with self.assertRaises(g.ReturnDataSizeMismatch):
            eth_abi.decode(["uint256"], words(1, 2))

    def test_the_checked_counter_is_exact_under_threads(self):
        import threading
        g.install("record")
        threads = [threading.Thread(target=lambda: [eth_abi.decode(["uint256"], words(1)) for _ in range(500)]) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(g._state["checked"], 4000)

    def test_the_atexit_handler_is_registered_once_and_writes_nothing_after_uninstall(self):
        import atexit
        import json
        import tempfile
        with mock.patch.object(atexit, "register") as reg:
            g._state["atexit"] = False
            sink_a, sink_b = os.path.join(tempfile.mkdtemp(), "a.json"), os.path.join(tempfile.mkdtemp(), "b.json")
            g.install("record", sink_a)
            g.install("record", sink_b)
            self.assertEqual(reg.call_count, 1)
        g._state["atexit"] = False
        g.uninstall()
        self.assertIsNone(g._state["sink"])
        g.dump()
        self.assertFalse(os.path.exists(sink_a) or os.path.exists(sink_b))

    def test_uninstall_leaves_the_codec_class_as_it_was_found(self):
        # compared with what the class was when the guard module was first imported (in a full test run another module may already
        # have installed the guard through web3_utils): in eth_abi 5.2 `decode` is inherited from ABIDecoder, not defined on ABICodec
        g.install("raise")
        g.uninstall()
        self.assertEqual("decode" in ABICodec.__dict__, g._HAD_OWN_DECODE)
        self.assertIs(ABICodec.decode, g._ORIGINAL_DECODE)

    def test_an_unknown_mode_is_refused(self):
        with self.assertRaises(ValueError):
            g.install("warn")


class TestEnsureInstalled(_Installed):
    def test_it_installs_in_raise_mode_when_nothing_is_installed(self):
        g.ensure_installed()
        with self.assertRaises(g.ReturnDataSizeMismatch):
            eth_abi.decode(["uint256"], words(1, 2))

    def test_it_never_overrides_an_earlier_choice(self):
        g.install("record")
        g.ensure_installed("raise")
        self.assertEqual(eth_abi.decode(["uint256"], words(1, 2)), (1,))       # still record mode: decoding unchanged
        self.assertEqual(len(g.records()), 1)


_GUARDED = """
import sys
{imports}
import abi_returndata_guard as g
from eth_abi import decode
try:
    decode(['uint256'], b'\\x00' * 64)
    print('RESULT=not guarded')
except g.ReturnDataSizeMismatch:
    print('RESULT=guarded')
print('MODULES=' + ','.join(sorted(m for m in sys.modules if m.endswith('abi_returndata_guard'))))
"""


def _run_guard_check(imports):
    import subprocess
    p = subprocess.run([sys.executable, "-c", _GUARDED.format(imports=imports)], cwd=REPO_ROOT, capture_output=True, text=True, timeout=120)
    lines = dict(l.split("=", 1) for l in p.stdout.splitlines() if l.startswith(("RESULT=", "MODULES=")))
    assert "RESULT" in lines, p.stderr[-800:]
    return lines


class TestEveryAbiDecodingEcosystemIsGuardedByItsScorers(unittest.TestCase):
    """The audit found no mismatch today, so the guard is installed in raise mode by importing any ecosystem's scorers: a future ABI
    mistake fails visibly instead of returning the first word. The scorers of Solana and Zcash decode no ABI at all."""

    def test_the_evm_ecosystems_import_the_guard_through_web3_utils_or_their_own_primitives(self):
        for eco in ("ethereum-l1", "arbitrum-ecosystem", "base-ecosystem", "monad", "plasma-ecosystem", "tempo", "hyperliquid"):
            with self.subTest(ecosystem=eco):
                r = _run_guard_check(f"sys.path.insert(0, 'scripts/lib')\nsys.path.insert(0, 'chains/{eco}')\nimport scorers")
                self.assertEqual(r["RESULT"], "guarded")
                self.assertEqual(r["MODULES"], "abi_returndata_guard", "one canonical guard module, however web3_utils was imported")

    def test_robinhoods_scorers_imported_as_a_package_share_the_same_guard_module(self):
        r = _run_guard_check("sys.path.insert(0, 'scripts')\nfrom lib import scorers")
        self.assertEqual(r["RESULT"], "guarded")
        self.assertEqual(r["MODULES"], "abi_returndata_guard")

    def test_the_chain_scorers_module_is_still_the_chains_own(self):
        import subprocess
        for eco in ("tempo", "hyperliquid"):
            with self.subTest(ecosystem=eco):
                code = (f"import sys, os\nsys.path.insert(0, 'chains/{eco}')\nimport scorers\n"
                        "print('FILE=' + os.path.realpath(scorers.__file__))")
                p = subprocess.run([sys.executable, "-c", code], cwd=REPO_ROOT, capture_output=True, text=True, timeout=120)
                line = next(l for l in p.stdout.splitlines() if l.startswith("FILE="))
                self.assertEqual(line[5:], os.path.realpath(os.path.join(REPO_ROOT, "chains", eco, "scorers.py")))

    def test_ethereum_l1s_bare_scorers_survives_its_own_lib_scorers_cross_import(self):
        # ADDED 2026-09-22: chains/ethereum-l1/scorers.py is the first chain scorers.py to itself
        # import FROM scripts/lib/scorers.py (for _replay_role_holders(), Aave Horizon's live
        # role-holder replay) -- a SAME-NAMED sibling of itself (both files are called scorers.py).
        # Reached via `from lib.scorers import _replay_role_holders` (the `lib` package, requiring
        # `scripts` on sys.path), never a bare `from scorers import ...` (which would resolve to
        # itself, since chains/ethereum-l1/scorers.py is always loaded as the bare module `scorers`
        # by every real entry point -- see that file's own comment above this import).
        #
        # A real, found-while-building-this side effect this test guards against: scripts/lib/
        # signer_overlap.py (pulled in transitively by lib.scorers) does its own
        # `sys.path.insert(0, ...)` for scripts/lib -- INSERT, not the append() web3_utils.py itself
        # uses for abi_returndata_guard/rpc_unavailable -- which pushes scripts/lib back in FRONT of
        # chains/ethereum-l1 on sys.path once lib.scorers has loaded. Harmless for every real entry
        # point (each does `from scorers import score_all` -- or `from scorers import X` -- exactly
        # ONCE per process, so sys.modules['scorers'] is already bound, before this reordering could
        # matter), but this test locks in the property directly, in the EXACT order every real entry
        # point uses (chains/ethereum-l1/deploy/update_scores_ethereum_l1.py,
        # chains/ethereum-l1/scripts/dry_run.py), rather than trusting that reasoning to stay true.
        import subprocess
        code = (
            "import sys, os\n"
            "sys.path.insert(0, os.path.join('scripts', 'lib'))\n"
            "sys.path.insert(0, os.path.join('chains', 'ethereum-l1'))\n"
            "from web3_utils import get_w3\n"
            "from scorers import score_all\n"
            "print('SCORERS_FILE=' + os.path.realpath(sys.modules['scorers'].__file__))\n"
            "print('LIB_SCORERS_FILE=' + os.path.realpath(sys.modules['lib.scorers'].__file__))\n"
        )
        p = subprocess.run([sys.executable, "-c", code], cwd=REPO_ROOT, capture_output=True, text=True, timeout=120)
        out = dict(l.split("=", 1) for l in p.stdout.splitlines() if l.startswith(("SCORERS_FILE=", "LIB_SCORERS_FILE=")))
        self.assertIn("SCORERS_FILE", out, p.stderr[-800:])
        self.assertEqual(out["SCORERS_FILE"], os.path.realpath(os.path.join(REPO_ROOT, "chains", "ethereum-l1", "scorers.py")))
        self.assertEqual(out["LIB_SCORERS_FILE"], os.path.realpath(os.path.join(REPO_ROOT, "scripts", "lib", "scorers.py")))
        self.assertNotEqual(out["SCORERS_FILE"], out["LIB_SCORERS_FILE"])

    def test_solana_and_zcash_scorers_decode_no_abi(self):
        for eco in ("solana", "zcash"):
            with self.subTest(ecosystem=eco):
                with open(os.path.join(REPO_ROOT, "chains", eco, "scorers.py"), encoding="utf-8") as f:
                    src = f.read()
                self.assertNotIn("eth_abi", src)
                self.assertNotIn("from web3", src)
                self.assertNotIn("import web3", src)


class TestAuditTool(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import audit_abi_returndata as tool
        cls.tool = tool

    def _report(self, name, mismatches=(), error=None, scored=3):
        return {"name": name, "error": error, "checked": 100, "mismatches": list(mismatches), "scored": scored}

    def _main(self, reports, *argv):
        with mock.patch.object(self.tool, "audit", side_effect=reports), \
             mock.patch.object(sys, "argv", ["audit_abi_returndata.py", *argv]), mock.patch("builtins.print"):
            with self.assertRaises(SystemExit) as cm:
                self.tool.main()
        return cm.exception.code

    def test_exit_zero_only_when_every_ecosystem_ran_clean(self):
        self.assertEqual(self._main([self._report("base"), self._report("plasma")], "--ecosystem", "base,plasma"), 0)

    def test_a_size_mismatch_fails_the_run(self):
        for kind in ("more", "fewer", "head"):
            with self.subTest(kind=kind):
                m = {"caller": "x.py:1", "count": 1, "problem": "p", "kind": kind}
                self.assertEqual(self._main([self._report("base", [m]), self._report("plasma")], "--ecosystem", "base,plasma"), 1)

    def test_an_empty_data_probe_is_informational(self):
        m = {"caller": "x.py:1", "count": 4, "problem": "p", "kind": "empty"}
        self.assertEqual(self._main([self._report("base", [m]), self._report("plasma")], "--ecosystem", "base,plasma"), 0)

    def test_an_ecosystem_that_could_not_be_run_is_never_clean(self):
        self.assertEqual(self._main([self._report("base", error="timed out"), self._report("plasma")], "--ecosystem", "base,plasma"), 1)

    def test_an_empty_selection_and_unknown_names_are_refused(self):
        for argv in (("--ecosystem", "base", "--skip", "base"), ("--skip", "bse"), ("--ecosystem", "bse")):
            with self.subTest(argv=argv):
                with mock.patch.object(sys, "argv", ["audit_abi_returndata.py", *argv]):
                    with self.assertRaises(SystemExit) as cm:
                        self.tool.main()
                self.assertIsInstance(cm.exception.code, str)

    def _run_audit(self, stdout, sink_content=None, timeout=False):
        import json
        import subprocess as sp

        def fake_run(cmd, **kw):
            if timeout:
                raise sp.TimeoutExpired(cmd, 1)
            if sink_content is not None:
                sink = cmd[2].split("install('record', ")[1].split(")")[0].strip("'\"")
                with open(sink, "w") as f:
                    json.dump(sink_content, f)
            return mock.Mock(stdout=stdout, stderr="", returncode=0)

        with mock.patch.object(self.tool.subprocess, "run", side_effect=fake_run):
            return self.tool.audit("base", 1)

    def test_audit_reads_the_guards_result_file(self):
        ok = '===AROVALIDATOR-JSON-START===\n{"ok": true, "results": [{}, {}]}\n===AROVALIDATOR-JSON-END===\n'
        r = self._run_audit(ok, {"checked": 40, "mismatches": [{"caller": "a.py:3", "count": 2, "problem": "p", "kind": "more"}]})
        self.assertEqual((r["error"], r["checked"], r["scored"], len(r["mismatches"])), (None, 40, 2, 1))

    def test_a_target_skipped_by_score_all_makes_the_audit_partial_and_fails_closed(self):
        skipped = "score_all(): SKIPPED Some Target this run -- BadFunctionCallOutput: boom\n"
        ok = skipped + '===AROVALIDATOR-JSON-START===\n{"ok": true, "results": [{}, {}]}\n===AROVALIDATOR-JSON-END===\n'
        r = self._run_audit(ok, {"checked": 40, "mismatches": []})
        self.assertIn("partial audit", r["error"])
        self.assertIn("skipped 1 target", r["error"])
        # the word inside the scores' own text (after the JSON marker) is not a skipped target
        inner = '===AROVALIDATOR-JSON-START===\n{"ok": true, "results": [{"notes": ["score_all(): SKIPPED"]}]}\n===AROVALIDATOR-JSON-END===\n'
        self.assertIsNone(self._run_audit(inner, {"checked": 1, "mismatches": []})["error"])

    def test_an_indented_skipped_line_is_still_a_skipped_target(self):
        skipped = "   score_all(): SKIPPED Some Target this run -- boom\n"
        ok = skipped + '===AROVALIDATOR-JSON-START===\n{"ok": true, "results": [{}]}\n===AROVALIDATOR-JSON-END===\n'
        self.assertIn("partial audit", self._run_audit(ok, {"checked": 1, "mismatches": []})["error"])

    def test_workers_defaults_to_four_and_can_be_one(self):
        for argv, expected in (((), 4), (("--workers", "1"), 1)):
            with self.subTest(argv=argv):
                with mock.patch.object(self.tool, "audit", return_value=self._report("base")), \
                     mock.patch.object(self.tool, "ThreadPoolExecutor", wraps=self.tool.ThreadPoolExecutor) as pool, \
                     mock.patch.object(sys, "argv", ["audit_abi_returndata.py", "--ecosystem", "base", *argv]), mock.patch("builtins.print"):
                    with self.assertRaises(SystemExit):
                        self.tool.main()
                self.assertEqual(pool.call_args.kwargs["max_workers"], expected)

    def test_audit_fails_closed_on_a_timeout_a_missing_json_and_a_missing_result_file(self):
        self.assertIn("timed out", self._run_audit("", timeout=True)["error"])
        self.assertIn("no JSON", self._run_audit("nothing here")["error"])
        ok = '===AROVALIDATOR-JSON-START===\n{"ok": true, "results": [{}]}\n===AROVALIDATOR-JSON-END===\n'
        self.assertIn("did not run", self._run_audit(ok, None)["error"])
        bad = '===AROVALIDATOR-JSON-START===\n{"ok": false, "error": "boom"}\n===AROVALIDATOR-JSON-END===\n'
        self.assertEqual(self._run_audit(bad)["error"], "boom")


if __name__ == "__main__":
    unittest.main()
