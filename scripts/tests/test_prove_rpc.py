#!/usr/bin/env python3
"""scripts/prove.py reading an RPC that refuses batches (offline, an in-process fake endpoint, no socket): python3 test_prove_rpc.py [path to prove.py]
The fake answers like testnet-rpc.monad.xyz: HTTP 403 to any JSON-RPC array (one call included), HTTP 200 to a single object. Whatever happens, a read is either complete or None, never a partial list."""
import importlib.util, io, json, os, sys, time, unittest, urllib.error

PROVE = sys.argv.pop(1) if len(sys.argv) > 1 and sys.argv[1].endswith(".py") else os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "prove.py")
spec = importlib.util.spec_from_file_location("prove", PROVE); P = importlib.util.module_from_spec(spec); sys.path.insert(0, os.path.dirname(os.path.abspath(PROVE))); spec.loader.exec_module(P)

URL = "http://fake.invalid/rpc"; CALLS = [("0x" + "ab" * 20, "0x%08x" % i) for i in range(5)]


class Fake:
    """403 to an array; to an object, `answer(n, req)` for the n-th single call (0-based). Counts what it received."""
    def __init__(self, answer): self.answer, self.arrays, self.singles = answer, 0, 0
    def __call__(self, req, timeout=0):
        body = json.loads(req.data.decode())
        if isinstance(body, list): self.arrays += 1; raise urllib.error.HTTPError(URL, 403, "Forbidden", {}, io.BytesIO(b"error code: 1010"))
        n = self.singles; self.singles += 1; out = self.answer(n, body)
        if isinstance(out, Exception): raise out
        class R:
            def read(s): return json.dumps(out).encode()
        return R()


def ok(n, req): return {"jsonrpc": "2.0", "id": req["id"], "result": "0x" + req["params"][0]["data"][2:].rjust(64, "0")}   # the answer is a function of the call, so a retry heals nothing
def is_call(req, k): return req["params"][0]["data"] == CALLS[k][1]   # a PERSISTENT fault: the same call fails on every try


class TestRpcBatchRefused(unittest.TestCase):
    def setUp(self):
        self.saved = (P.urllib.request.urlopen, P.time.sleep, P.DEADLINE); P.time.sleep = lambda s: None; P._NO_BATCH.clear(); P.DEADLINE = time.time() + 1000
    def tearDown(self): P.urllib.request.urlopen, P.time.sleep, P.DEADLINE = self.saved; P._NO_BATCH.clear()
    def run_with(self, answer):
        f = Fake(answer); P.urllib.request.urlopen = f; return P.rpc_batch(URL, CALLS), f

    def test_403_on_the_array_then_every_call_alone_gives_the_full_list_in_order(self):
        out, f = self.run_with(ok)
        self.assertEqual(out, ["0x" + d[2:].rjust(64, "0") for _t, d in CALLS]); self.assertEqual((f.arrays, f.singles), (1, 5))

    def test_after_the_first_403_the_next_reads_skip_the_batch(self):
        self.run_with(ok); out, f = self.run_with(ok)
        self.assertEqual(f.arrays, 0); self.assertEqual(len(out), 5)

    def test_an_error_in_the_middle_of_the_list_is_none_never_a_partial_list(self):
        out, _f = self.run_with(lambda n, req: {"jsonrpc": "2.0", "id": req["id"], "error": {"code": -32000, "message": "boom"}} if is_call(req, 2) else ok(n, req))
        self.assertIsNone(out)

    def test_a_call_that_never_answers_is_none(self):
        out, _f = self.run_with(lambda n, req: OSError("reset") if is_call(req, 3) else ok(n, req)); self.assertIsNone(out)

    def test_an_answer_with_somebody_elses_id_is_not_taken(self):
        out, _f = self.run_with(lambda n, req: dict(ok(n, req), id=7) if is_call(req, 1) else ok(n, req)); self.assertIsNone(out)
        out, _f = self.run_with(lambda n, req: {"jsonrpc": "2.0", "id": req["id"], "result": None}); self.assertIsNone(out)   # a null result is not a hex answer

    def test_past_the_deadline_no_retry_starts_and_the_read_is_none(self):
        P.DEADLINE = time.time() - 1; f = Fake(lambda n, req: OSError("down")); P.urllib.request.urlopen = f
        self.assertIsNone(P.rpc_singles(URL, CALLS)); self.assertEqual(f.singles, 1)   # the first try of the first call, no second one
        P._NO_BATCH.clear(); f = Fake(lambda n, req: OSError("down")); P.urllib.request.urlopen = f
        self.assertIsNone(P.rpc_batch(URL, CALLS)); self.assertLessEqual(f.arrays + f.singles, 2)   # the array tried once (403), the first single tried once


if __name__ == "__main__": unittest.main(verbosity=1)
