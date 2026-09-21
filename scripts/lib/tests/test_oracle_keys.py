"""
Tests for the oracle key uniqueness guard (scripts/lib/oracle_keys.py), for its wiring into every push script, and for
the cross-ecosystem audit tool built on it (scripts/check_oracle_key_collisions.py).

Why: the oracle stores one score per key, so two scored entries on one key silently overwrite each other (found on
Hyperliquid on 2026-09-19: 15 scores pushed, 13 stored). Only Hyperliquid's push script checked; the others assembled
their key list with no check. No network access here: entries are hand-built, push scripts are loaded in a subprocess
(several ecosystems import a different module under the same name `scorers`, so they must not share one process).
"""
import ast
import json
import os
import subprocess
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts", "lib"))
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))
import oracle_keys as ok  # noqa: E402

A_LOWER = "0x" + "a" * 40
A_UPPER = "0x" + "A" * 40
B = "0x" + "b" * 40
SOL_LOWER = "So11111111111111111111111111111111111111112"
SOL_OTHER_CASE = "SO11111111111111111111111111111111111111112"


def _entry(label, target, **extra):
    e = {"label": label, "target": target, "adminKeyScore": 10, "multisigScore": 15, "timelockScore": 0,
         "oracleAuthorityScore": 4, "crossExposureScore": 100, "compositeScore": 9}
    e.update(extra)
    return e


class TestHelper(unittest.TestCase):
    def test_unique_keys_pass(self):
        self.assertEqual(ok.find_key_collisions([_entry("a", A_LOWER), _entry("b", B)]), {})
        ok.assert_unique_oracle_keys([_entry("a", A_LOWER), _entry("b", B)])   # does not raise

    def test_checksummed_and_lowercase_forms_are_the_same_slot(self):
        found = ok.find_key_collisions([_entry("x", A_UPPER), _entry("y", A_LOWER)])
        self.assertEqual(found, {A_LOWER: ["x", "y"]})

    def test_the_exact_mode_keeps_base58_case_sensitive(self):
        entries = [_entry("x", SOL_LOWER), _entry("y", SOL_OTHER_CASE)]
        self.assertEqual(ok.find_key_collisions(entries, exact=True), {})
        self.assertEqual(ok.find_key_collisions([_entry("x", SOL_LOWER), _entry("y", SOL_LOWER)], exact=True),
                         {SOL_LOWER: ["x", "y"]})
        self.assertNotEqual(ok.find_key_collisions(entries, exact=False), {})   # the EVM rule would have merged them

    def test_a_derived_oracle_key_does_not_hide_a_collision_by_default(self):
        # the eight guarded push scripts push entry["target"] and ignore oracleKey, so two entries with the same target collide
        # whatever their oracleKey says
        derived = "0x" + "c" * 40
        entries = [_entry("dex", A_LOWER, oracleKey=derived), _entry("contract", A_LOWER)]
        self.assertEqual(ok.find_key_collisions(entries), {A_LOWER: ["dex", "contract"]})
        with self.assertRaises(SystemExit):
            ok.assert_unique_oracle_keys(entries)

    def test_a_derived_oracle_key_resolves_a_collision_only_when_asked_to_honour_it(self):
        # Hyperliquid's push script does push oracleKey when there is one (the audit tool mirrors that for it)
        derived = "0x" + "c" * 40
        entries = [_entry("dex", A_LOWER, oracleKey=derived), _entry("contract", A_LOWER)]
        self.assertEqual(ok.find_key_collisions(entries, honour_oracle_key=True), {})
        ok.assert_unique_oracle_keys(entries, honour_oracle_key=True)   # does not raise

    def test_two_entries_on_the_same_derived_key_still_collide_when_it_is_honoured(self):
        derived = "0x" + "c" * 40
        entries = [_entry("one", A_LOWER, oracleKey=derived), _entry("two", B, oracleKey=derived.upper().replace("0X", "0x"))]
        self.assertEqual(list(ok.find_key_collisions(entries, honour_oracle_key=True)), [derived])

    def test_the_forms_web3_would_unify_are_unified_here_too(self):
        # to_checksum_address accepts a prefixed or bare hex string of any case and raw bytes: all one slot
        forms = [A_LOWER, A_UPPER, "0X" + "a" * 40, "a" * 40, "  " + A_LOWER + " ", bytes.fromhex("aa" * 20)]
        found = ok.find_key_collisions([_entry(f"form{i}", f) for i, f in enumerate(forms)])
        self.assertEqual(list(found), [A_LOWER])
        self.assertEqual(len(found[A_LOWER]), len(forms))

    def test_different_addresses_are_not_merged_by_the_normalisation(self):
        self.assertEqual(ok.find_key_collisions([_entry("x", "a" * 40), _entry("y", B), _entry("z", "0x" + "c" * 40)]), {})

    def test_refusal_names_every_key_and_entry(self):
        entries = [_entry("first", A_LOWER), _entry("second", A_UPPER), _entry("third", B), _entry("fourth", B), _entry("fifth", B)]
        with self.assertRaises(SystemExit) as cm:
            ok.assert_unique_oracle_keys(entries, where="(unit push)")
        msg = str(cm.exception)
        self.assertIn("REFUSING (unit push)", msg)
        self.assertIn("2 oracle key collision(s)", msg)
        for label in ("first", "second", "third", "fourth", "fifth"):
            self.assertIn(label, msg)

    def test_an_entry_without_a_label_is_still_reported(self):
        with self.assertRaises(SystemExit) as cm:
            ok.assert_unique_oracle_keys([{"target": A_LOWER}, {"target": A_UPPER}])
        self.assertIn("<no label>", str(cm.exception))

    def test_an_entry_without_a_target_fails_loudly(self):
        with self.assertRaises(KeyError):
            ok.find_key_collisions([{"label": "no target"}])


# (script, function that assembles the keys, EVM function-under-test kind, exact key comparison)
EVM_ASSEMBLERS = (
    ("chains/arbitrum-ecosystem/deploy/push_scores.py", "build_targets_and_tuples"),
    ("chains/base-ecosystem/deploy/push_scores.py", "build_targets_and_tuples"),
    ("chains/monad/deploy/push_scores.py", "build_targets_and_tuples"),
    ("chains/plasma-ecosystem/deploy/push_scores.py", "build_targets_and_tuples"),
    ("chains/tempo/deploy/push_scores.py", "build_targets_and_tuples"),
    ("chains/ethereum-l1/deploy/update_scores_ethereum_l1.py", "build_calldata"),
)
# assembled inline in _run() / push_live() / main(): they need a live RPC, so besides the AST check they get a behaviour test
# below with the network and the key loading replaced by stand-ins
INLINE_ASSEMBLERS = (
    ("scripts/update_scores.py", "_run", 'os.environ["PRIVATE_KEY"]', False),
    ("scripts/update_scores.py", "_run", 'to_checksum_address(entry["target"])', False),
    ("chains/solana/deploy/update_scores_solana.py", "push_live", "stx.load_keypair(", True),
    ("chains/solana/deploy/update_scores_solana.py", "push_live", "stx.build_signed_tx(", True),
    ("chains/solana/deploy/update_scores_solana.py", "push_live", 'stx.b58decode(entry["target"]', True),
    ("chains/solana/deploy/update_scores_solana.py", "main", "encode_update_score_ix_data(entry", True),
)


def _function_node(rel, name):
    with open(os.path.join(REPO_ROOT, rel), encoding="utf-8") as f:
        source = f.read()
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return source, node
    raise AssertionError(f"{rel} has no function {name}")


def _is_guard_call(n):
    return isinstance(n, ast.Call) and getattr(n.func, "id", getattr(n.func, "attr", None)) == "assert_unique_oracle_keys"


def _guard_statements(node):
    """The top-level statements of the function that ARE a guard call (an Expr whose value is the call)."""
    return [st for st in node.body if isinstance(st, ast.Expr) and _is_guard_call(st.value)]


class TestTheGuardIsAnUnconditionalStatementBeforeTheKeys(unittest.TestCase):
    """The guard must be a plain top-level statement of the function (not under an `if`, a `try`, a loop or a nested def, so it cannot
    be skipped, swallowed or unreachable), must not come after a top-level return or raise, and must precede the first line that
    builds a key, reads the private key or builds a transaction."""

    def _check(self, rel, name, sink, exact):
        source, node = _function_node(rel, name)
        all_calls = [n for n in ast.walk(node) if _is_guard_call(n)]
        top = _guard_statements(node)
        self.assertEqual(len(all_calls), 1, f"{rel}: expected exactly one assert_unique_oracle_keys call in {name}()")
        self.assertEqual(len(top), 1, f"{rel}: the guard call in {name}() must be a top-level statement of the function")
        call = top[0].value
        has_exact = any(k.arg == "exact" and getattr(k.value, "value", None) is True for k in call.keywords)
        self.assertEqual(has_exact, exact, f"{rel}: the exact= flag must be {exact}")
        self.assertFalse(any(k.arg == "honour_oracle_key" for k in call.keywords), f"{rel}: pushes target, must not honour oracleKey")
        for st in node.body:
            if st.lineno >= call.lineno:
                break
            self.assertNotIsInstance(st, (ast.Return, ast.Raise), f"{rel}: a return/raise before the guard makes it unreachable")
        lines = source.splitlines()
        first_sink = next(i for i in range(node.lineno, node.end_lineno + 1) if sink in lines[i - 1])
        self.assertLess(call.lineno, first_sink, f"{rel}: the guard must run before the keys are built ({sink})")
        self.assertIn("assert_unique_oracle_keys", source.split(f"def {name}", 1)[0], f"{rel}: import missing")

    def test_evm_assemblers(self):
        for rel, name in EVM_ASSEMBLERS:
            with self.subTest(script=rel):
                self._check(rel, name, "to_checksum_address(", False)

    def test_inline_assemblers(self):
        for rel, name, sink, exact in INLINE_ASSEMBLERS:
            with self.subTest(script=rel, function=name, sink=sink):
                self._check(rel, name, sink, exact)


_CALL = """
import importlib.util, json, sys
from web3 import Web3
spec = importlib.util.spec_from_file_location("push_under_test", {path!r})
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
scored = json.loads({scored!r})
try:
    if {name!r} == "build_calldata":
        out = m.build_calldata(Web3(), scored, 1, b"\\x00" * 32)
        targets = out[1]
    else:
        out = m.build_targets_and_tuples(scored, 1, b"\\x00" * 32)
        targets = out[0]
    print(json.dumps({{"refused": False, "targets": [str(t) for t in targets]}}))
except SystemExit as e:
    print(json.dumps({{"refused": True, "message": str(e)}}))
"""


def _run(rel, name, scored):
    code = _CALL.format(path=os.path.join(REPO_ROOT, rel), name=name, scored=json.dumps(scored))
    p = subprocess.run([sys.executable, "-c", code], cwd=REPO_ROOT, capture_output=True, text=True, timeout=120)
    lines = [l for l in p.stdout.splitlines() if l.startswith("{")]
    assert lines, f"{rel}: no result (exit {p.returncode})\n{p.stderr[-800:]}"
    return json.loads(lines[-1])


class TestPushScriptsBehaviour(unittest.TestCase):
    def test_a_collision_makes_the_assembler_refuse(self):
        scored = [_entry("first", A_LOWER), _entry("second", A_UPPER), _entry("other", B)]
        for rel, name in EVM_ASSEMBLERS:
            with self.subTest(script=rel):
                r = _run(rel, name, scored)
                self.assertTrue(r["refused"], r)
                self.assertIn("REFUSING", r["message"])
                self.assertIn("first", r["message"])
                self.assertIn("second", r["message"])

    def test_distinct_keys_are_unchanged(self):
        scored = [_entry("first", A_LOWER), _entry("other", B)]
        for rel, name in EVM_ASSEMBLERS:
            with self.subTest(script=rel):
                r = _run(rel, name, scored)
                self.assertFalse(r["refused"], r)
                self.assertEqual([t.lower() for t in r["targets"]], [A_LOWER, B])


_INLINE = """
import importlib.util, json, os, sys, types
sys.argv = {argv!r}
os.environ.update({env!r})
os.environ.pop("PRIVATE_KEY", None)
spec = importlib.util.spec_from_file_location("inline_under_test", {path!r})
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
scored = json.loads({scored!r})
calls = []
{setup}
try:
    {call}
    print(json.dumps({{"refused": False, "calls": calls}}))
except SystemExit as e:
    print(json.dumps({{"refused": True, "message": str(e), "calls": calls}}))
except Exception as e:
    print(json.dumps({{"refused": False, "calls": calls, "error": type(e).__name__}}))
"""

_RH_SETUP = """
class W3:
    eth = types.SimpleNamespace(chain_id=1)
    def is_connected(self): return True
m.get_w3 = lambda url: (calls.append("get_w3:" + url), W3())[1]
m.score_all = lambda w3, skip_slow=False: scored
# ADDED 2026-09-22: check_completeness() (its own dedicated coverage lives in
# scripts/tests/test_update_scores.py::TestCheckCompleteness) would otherwise compare this test's
# tiny scripted `scored` fixture against the REAL api/scores.json this subprocess runs with cwd=
# REPO_ROOT (a real, ~60-target snapshot) and refuse every run here on an unrelated "target(s)
# missing" -- this file is about the oracle-key-collision guard, not completeness.
m.check_completeness = lambda *a, **k: None
"""

_SOL_SETUP = """
import solana_tx as stx
stx.assert_not_mainnet = lambda url: stx.DEVNET_GENESIS
stx.load_keypair = lambda f: (calls.append("load_keypair"), (b"k", b"p"))[1]
stx.rpc = lambda *a, **k: calls.append("rpc")
stx.send_and_confirm = lambda *a, **k: calls.append("send")
m.score_all = lambda url: scored
args = types.SimpleNamespace(program_id="P", keypair_file="K", oracle_rpc_url="http://oracle", read_rpc_url="http://read", out=None)
"""


def _run_inline(rel, scored, setup, call, argv=("x",), env=None):
    code = _INLINE.format(argv=list(argv), env=env or {}, path=os.path.join(REPO_ROOT, rel), scored=json.dumps(scored), setup=setup, call=call)
    p = subprocess.run([sys.executable, "-c", code], cwd=REPO_ROOT, capture_output=True, text=True, timeout=120)
    lines = [l for l in p.stdout.splitlines() if l.startswith("{")]
    assert lines, f"{rel}: no result (exit {p.returncode})\n{p.stderr[-800:]}"
    return json.loads(lines[-1])


SOL_SYSTEM = "1" * 32
RH_ENV = {"READ_RPC_URL": "read", "ORACLE_RPC_URL": "oracle", "ORACLE_ADDRESS": "0x" + "1" * 40}


class TestInlineAssemblersBehaviour(unittest.TestCase):
    """Robinhood's _run() and Solana's push_live()/main() need a live RPC and a key, so they are run here with the network, the score
    reads and the key loading replaced by stand-ins: a collision must be refused before the key is read or any transaction exists."""

    def test_robinhood_refuses_a_collision_before_the_oracle_rpc_and_the_private_key(self):
        scored = [_entry("first", A_LOWER, notes=[]), _entry("second", A_UPPER, notes=[])]
        for dry in (True, False):
            with self.subTest(dry_run=dry):
                r = _run_inline("scripts/update_scores.py", scored, _RH_SETUP, f"m._run({dry}, False)", env=RH_ENV)
                self.assertTrue(r["refused"], r)
                self.assertIn("REFUSING (robinhood push)", r["message"])
                self.assertEqual(r["calls"], ["get_w3:read"], "the oracle RPC must not be opened before the guard")

    def test_robinhood_dry_run_with_distinct_keys_still_completes(self):
        scored = [_entry("first", A_LOWER, notes=[]), _entry("second", B, notes=[])]
        r = _run_inline("scripts/update_scores.py", scored, _RH_SETUP, "m._run(True, False)", env=RH_ENV)
        self.assertEqual((r["refused"], r.get("error")), (False, None), r)

    def test_solana_push_live_refuses_a_collision_before_the_key_is_read_or_any_transaction_is_sent(self):
        scored = [_entry("first", SOL_LOWER), _entry("second", SOL_LOWER)]
        r = _run_inline("chains/solana/deploy/update_scores_solana.py", scored, _SOL_SETUP, "m.push_live(args)")
        self.assertTrue(r["refused"], r)
        self.assertIn("REFUSING (solana push)", r["message"])
        self.assertEqual(r["calls"], [], "no key read, no RPC, no transaction before the guard")

    def test_solana_push_live_with_distinct_keys_goes_on_to_the_key(self):
        scored = [_entry("first", SOL_LOWER), _entry("second", SOL_SYSTEM)]
        r = _run_inline("chains/solana/deploy/update_scores_solana.py", scored, _SOL_SETUP, "m.push_live(args)")
        self.assertFalse(r["refused"], r)
        self.assertEqual(r["calls"][:1], ["load_keypair"])

    def test_solana_dry_run_refuses_a_collision_and_encodes_nothing(self):
        scored = [_entry("first", SOL_LOWER), _entry("second", SOL_LOWER)]
        r = _run_inline("chains/solana/deploy/update_scores_solana.py", scored, "m.score_all = lambda url: scored", "m.main()",
                        argv=("x", "--dry-run"))
        self.assertTrue(r["refused"], r)
        self.assertIn("REFUSING (solana dry-run)", r["message"])

    def test_solana_dry_run_with_distinct_keys_encodes_every_entry(self):
        scored = [_entry("first", SOL_LOWER), _entry("second", SOL_SYSTEM)]
        r = _run_inline("chains/solana/deploy/update_scores_solana.py", scored, "m.score_all = lambda url: scored", "m.main()",
                        argv=("x", "--dry-run"))
        self.assertEqual((r["refused"], r.get("error")), (False, None), r)


class TestChainScorersModuleIsNotShadowed(unittest.TestCase):
    """scripts/lib has its own scorers.py (Robinhood's). The Tempo and Solana push scripts had to add scripts/lib to sys.path to import
    the guard, so they append it last: `from scorers import score_all` must still resolve to the chain's own scorers.py. A wrong
    module would still expose a `score_all`, so this checks the file, not the attribute."""

    CASES = (
        ("chains/tempo/deploy/push_scores.py", "chains/tempo/scorers.py"),
        ("chains/solana/deploy/update_scores_solana.py", "chains/solana/scorers.py"),
        ("chains/arbitrum-ecosystem/deploy/push_scores.py", "chains/arbitrum-ecosystem/scorers.py"),
        ("chains/base-ecosystem/deploy/push_scores.py", "chains/base-ecosystem/scorers.py"),
        ("chains/monad/deploy/push_scores.py", "chains/monad/scorers.py"),
        ("chains/plasma-ecosystem/deploy/push_scores.py", "chains/plasma-ecosystem/scorers.py"),
        ("chains/ethereum-l1/deploy/update_scores_ethereum_l1.py", "chains/ethereum-l1/scorers.py"),
    )

    def test_each_push_script_imports_its_own_chains_scorers(self):
        code = ("import importlib.util, os, sys\n"
                "spec = importlib.util.spec_from_file_location('push_under_test', {path!r})\n"
                "m = importlib.util.module_from_spec(spec)\n"
                "spec.loader.exec_module(m)\n"
                "print('SCORERS_FILE=' + os.path.realpath(sys.modules['scorers'].__file__))\n")
        for rel, expected in self.CASES:
            with self.subTest(script=rel):
                p = subprocess.run([sys.executable, "-c", code.format(path=os.path.join(REPO_ROOT, rel))], cwd=REPO_ROOT,
                                   capture_output=True, text=True, timeout=120)
                line = next((l for l in p.stdout.splitlines() if l.startswith("SCORERS_FILE=")), None)
                self.assertIsNotNone(line, p.stderr[-800:])
                self.assertEqual(line[len("SCORERS_FILE="):], os.path.realpath(os.path.join(REPO_ROOT, expected)))


class TestAuditTool(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import check_oracle_key_collisions as tool
        cls.tool = tool

    def _audit(self, name, entries, err=None):
        with mock.patch.object(self.tool, "fetch_entries", return_value=(entries, err)):
            return self.tool.audit(name, 1)

    def test_a_collision_is_reported(self):
        r = self._audit("base", [_entry("x", A_UPPER), _entry("y", A_LOWER), _entry("z", B)])
        self.assertIsNone(r["error"])
        self.assertEqual(r["collisions"], {A_LOWER: ["x", "y"]})

    def test_distinct_keys_are_clean(self):
        r = self._audit("base", [_entry("x", A_LOWER), _entry("z", B)])
        self.assertEqual((r["error"], r["collisions"], r["entries"]), (None, {}, 2))

    def test_an_ecosystem_that_could_not_be_run_is_never_reported_clean(self):
        r = self._audit("base", [], err="timed out after 300s")
        self.assertEqual(r["error"], "timed out after 300s")

    def test_zero_entries_is_a_failure_not_a_pass(self):
        self.assertIn("zero entries", self._audit("base", [])["error"])

    def test_solana_and_zcash_keys_are_compared_exactly(self):
        self.assertEqual(self._audit("solana", [_entry("x", SOL_LOWER), _entry("y", SOL_OTHER_CASE)])["collisions"], {})
        self.assertEqual(self._audit("zcash", [_entry("x", "t1abc"), _entry("y", "T1ABC")])["collisions"], {})
        self.assertNotEqual(self._audit("solana", [_entry("x", SOL_LOWER), _entry("y", SOL_LOWER)])["collisions"], {})

    def test_hyperliquid_derived_keys_resolve_the_known_dex_collisions(self):
        mkts = "0x71f0019cc7fa79e4f42587fb7b9a817d8d2429ec"
        r = self._audit("hyperliquid", [_entry("HIP-3 dex mkts", mkts), _entry("Kinetiq HIP3StakingManager (HyperEVM)", mkts)])
        self.assertEqual((r["error"], r["collisions"]), (None, {}))
        self.assertEqual(r["resolved"], {mkts: ["HIP-3 dex mkts", "Kinetiq HIP3StakingManager (HyperEVM)"]})

    def test_hyperliquid_collision_the_push_script_cannot_resolve_is_reported(self):
        same = "0x" + "d" * 40
        r = self._audit("hyperliquid", [_entry("some contract", same), _entry("another contract", same)])
        self.assertIn("refuses", r["error"])
        self.assertEqual(r["collisions"], {same: ["some contract", "another contract"]})

    def test_a_derived_oracle_key_does_not_hide_a_collision_outside_hyperliquid(self):
        derived = "0x" + "c" * 40
        r = self._audit("base", [_entry("x", A_LOWER, oracleKey=derived), _entry("y", A_UPPER)])
        self.assertEqual(r["collisions"], {A_LOWER: ["x", "y"]})

    def _main_exit(self, *argv):
        with mock.patch.object(sys, "argv", ["check_oracle_key_collisions.py", *argv]), mock.patch("builtins.print"):
            with self.assertRaises(SystemExit) as cm:
                self.tool.main()
        return cm.exception.code

    def test_an_empty_selection_is_refused_not_reported_clean(self):
        self.assertIn("no ecosystem selected", str(self._main_exit("--ecosystem", "base", "--skip", "base")))

    def test_an_unknown_name_in_skip_is_refused(self):
        self.assertIn("Unknown ecosystem(s) in --skip", str(self._main_exit("--skip", "bse")))

    def test_an_unknown_name_in_ecosystem_is_refused(self):
        self.assertIn("Unknown ecosystem(s)", str(self._main_exit("--ecosystem", "bse")))

    def test_the_exit_code_is_nonzero_on_a_collision_and_on_an_unrunnable_ecosystem(self):
        def run(reports):
            with mock.patch.object(self.tool, "audit", side_effect=reports), \
                 mock.patch.object(sys, "argv", ["check_oracle_key_collisions.py", "--ecosystem", "base,plasma"]), \
                 mock.patch("builtins.print"):
                with self.assertRaises(SystemExit) as cm:
                    self.tool.main()
            return cm.exception.code

        clean = {"name": "n", "error": None, "entries": 3, "collisions": {}, "resolved": {}}
        collided = dict(clean, collisions={A_LOWER: ["x", "y"]})
        failed = dict(clean, error="timed out", entries=0)
        self.assertEqual(run([dict(clean, name="base"), dict(clean, name="plasma")]), 0)
        self.assertEqual(run([dict(clean, name="base"), dict(collided, name="plasma")]), 1)
        self.assertEqual(run([dict(failed, name="base"), dict(clean, name="plasma")]), 1)


if __name__ == "__main__":
    unittest.main()
