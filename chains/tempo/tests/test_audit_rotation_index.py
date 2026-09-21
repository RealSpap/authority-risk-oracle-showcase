"""
Unit tests for chains/tempo/scripts/audit_rotation_index.py's moderato_call() -- no network. Added
2026-09-22 (backlog item "quatre reimplementations separees", itemId=251466178): every read of the
oracle's own Moderato-chain state (trackedTargetsCount, trackedTargets, getScore) used to go through
MODERATO_RPC alone, unlike this same file's own CALL_RPCS (official+drpc+publicnode) pattern for the
mainnet re-derivation side, and unlike 3 of this file's 4 sibling audit scripts, which all
double/triple-read their own oracle's getScore(). Fixed by adding MODERATO_DRPC (dRPC's Tempo
Moderato Testnet gateway, verified live 2026-09-22 to serve identical state to the official RPC)
and a moderato_call() helper mirroring the file's own existing call2().

Importing this module is safe (its audit body lives entirely inside main(), guarded by
`if __name__ == "__main__":`) -- no network call happens on import.

Run:  python3 -m unittest discover -s chains/tempo/tests -v
"""
import importlib.util
import os
import sys
import unittest
from unittest.mock import patch

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))


def _load(name, rel):
    path = os.path.join(REPO_ROOT, rel)
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


a = _load("aro_test_tempo_audit_rotation_index", "chains/tempo/scripts/audit_rotation_index.py")


class TestModeratoCall(unittest.TestCase):
    def test_two_agreeing_providers_return_the_shared_value(self):
        with patch.object(a, "rpc", return_value="0x0e"):
            out = a.moderato_call("0x835e2172", label="trackedTargetsCount()")
        self.assertEqual(out, "0x0e")

    def test_disagreeing_providers_raise_naming_both_urls_and_the_label(self):
        with patch.object(a, "rpc", side_effect=["0x0e", "0x0d"]):
            with self.assertRaises(RuntimeError) as cm:
                a.moderato_call("0x835e2172", label="trackedTargetsCount()")
        msg = str(cm.exception)
        self.assertIn("trackedTargetsCount()", msg)
        self.assertIn(a.MODERATO_RPC, msg)
        self.assertIn(a.MODERATO_DRPC, msg)
        self.assertIn("DISAGREEMENT", msg)

    def test_one_provider_answering_nothing_is_reported_distinctly_from_a_real_disagreement(self):
        # REVIEW FINDING (reservation "moderato_call() IS STRICTER THAN call2()"): distinguish "one
        # provider gave no answer" (infra hiccup, e.g. one node lagging a block) from "both answered
        # but disagree" (a real, tampering-shaped finding) -- the two used to share one message.
        with patch.object(a, "rpc", side_effect=["0x0e", "0x"]):
            with self.assertRaises(RuntimeError) as cm:
                a.moderato_call("0x835e2172", label="trackedTargetsCount()")
        msg = str(cm.exception)
        self.assertIn("NO ANSWER", msg)
        self.assertNotIn("DISAGREEMENT", msg)

    def test_uses_both_configured_moderato_rpcs_by_default(self):
        seen_urls = []

        def fake_rpc(url, method, params):
            seen_urls.append(url)
            return "0xsame"

        with patch.object(a, "rpc", side_effect=fake_rpc):
            a.moderato_call("0xdeadbeef")
        self.assertEqual(seen_urls, a.MODERATO_RPCS)
        self.assertEqual(len(a.MODERATO_RPCS), 2)  # was a single RPC before this fix

    def test_the_eth_call_target_is_always_the_oracle_address(self):
        captured = {}

        def fake_rpc(url, method, params):
            captured[url] = params
            return "0xsame"

        with patch.object(a, "rpc", side_effect=fake_rpc):
            a.moderato_call("0xdeadbeef")
        for url, params in captured.items():
            self.assertEqual(params[0]["to"], a.ORACLE)
            self.assertEqual(params[0]["data"], "0xdeadbeef")


class TestComposite(unittest.TestCase):
    def test_uses_the_exact_integer_form_not_the_float_form_that_reads_one_low(self):
        # REVIEW FINDING (review run, reservation "HOLLOW TEST" -- raised against ethereum-l1's
        # equivalent test, same defect existed here): int(0.4*a+0.3*m+0.3*t+0.5) reads one LOWER
        # than the exact form (4a+3m+3t+5)//10 on 2054/1,030,301 (a,m,t) triples, independently
        # brute-forced before this fix. (0, 1, 24) is one of them: float form gives 7, exact gives 8.
        self.assertEqual(a.composite(0, 1, 24), 8)


class TestModeratoCallWiring(unittest.TestCase):
    """REVIEW FINDING (reservation "TEMPO TESTS DO NOT COVER THE WIRING"): the 4 tests above only
    exercise moderato_call() in isolation -- none of them proves main() actually routes
    trackedTargetsCount()/trackedTargets()/getScore() through it rather than a bare
    rpc(MODERATO_RPC, ...) call. Static/no-network: walks the module's own AST and fails if any
    rpc(MODERATO_RPC, ...) call exists OUTSIDE moderato_call()'s own function body.

    KNOWN, ACCEPTED SCOPE LIMIT (REVIEW FINDING, review run, reservation "THE NEW AST WIRING
    TEST CATCHES EXACTLY ONE SPELLING"): this only catches the LITERAL spelling
    rpc(MODERATO_RPC, ...) -- rpc(MODERATO_DRPC, ...), rpc(MODERATO_RPCS[0], ...), an aliased local
    (`u = MODERATO_RPC; rpc(u, ...)`), or a call2()-with-rpcs=MODERATO_RPCS bypass would all slip
    past it undetected. A fully alias-proof static check needs real data-flow analysis, which is
    disproportionate for locking in "don't regress the one specific line this commit changed" --
    the goal here is a tripwire against an accidental future edit reintroducing the exact pattern
    this fix removed, not a defence against a deliberately obtuse rewrite. The live re-run in this
    task's proof-set (verify_tempo_live.py) remains the check that would catch a more creative
    bypass, since it asserts both RPC URLs actually appear in the real output."""

    def test_no_bare_rpc_call_to_moderato_rpc_survives_outside_moderato_call(self):
        import ast
        import inspect

        tree = ast.parse(inspect.getsource(a))
        moderato_call_node_ids = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "moderato_call":
                moderato_call_node_ids = {id(n) for n in ast.walk(node)}
                break
        self.assertTrue(moderato_call_node_ids, "moderato_call() not found in the module's AST")

        offenders = []
        for node in ast.walk(tree):
            if id(node) in moderato_call_node_ids:
                continue
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "rpc"
                    and node.args and isinstance(node.args[0], ast.Name) and node.args[0].id == "MODERATO_RPC"):
                offenders.append(f"line {node.lineno}")
        self.assertEqual(offenders, [],
                          f"bare rpc(MODERATO_RPC, ...) call(s) outside moderato_call(): {offenders}")

    def test_moderato_call_is_actually_invoked_at_least_three_times(self):
        # REVIEW FINDING (review run, reservation on the "AT LEAST ONE CHEAP IMPROVEMENT WAS
        # SKIPPED" point): the previous test alone doesn't catch a call2()-with-rpcs=MODERATO_RPCS
        # bypass -- proven live by the reviewer (mutating trackedTargetsCount's read that way makes
        # the previous test pass while this one would drop from 3 invocations to 2). Cheap and
        # data-flow-free: just count call sites of the NAME moderato_call outside its own def,
        # reusing the same AST walk. Complements, doesn't replace, the previous test.
        import ast
        import inspect

        tree = ast.parse(inspect.getsource(a))
        moderato_call_node_ids = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "moderato_call":
                moderato_call_node_ids = {id(n) for n in ast.walk(node)}
                break
        self.assertTrue(moderato_call_node_ids, "moderato_call() not found in the module's AST")

        invocations = [
            node.lineno for node in ast.walk(tree)
            if id(node) not in moderato_call_node_ids
            and isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "moderato_call"
        ]
        self.assertGreaterEqual(len(invocations), 3,
                                 f"expected moderato_call() invoked for trackedTargetsCount, "
                                 f"trackedTargets and getScore (>=3 call sites), found: {invocations}")


if __name__ == "__main__":
    unittest.main()
