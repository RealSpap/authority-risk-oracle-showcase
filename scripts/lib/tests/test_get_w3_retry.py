"""get_w3 waits and retries on HTTP 429 instead of letting a rate limit read as an unread price path. Local HTTP server, no network."""
import http.server
import json
import os
import sys
import threading
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from lib.web3_utils import get_w3  # noqa: E402


def serve(limited, retry_after=None):
    state = {"n": 0, "methods": []}

    class H(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            state["n"] += 1
            state["methods"].append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))).get("method"))
            if state["n"] <= limited:
                self.send_response(429)
                self.send_header("Retry-After", retry_after or "0")
                self.end_headers()
                return
            body = json.dumps({"jsonrpc": "2.0", "id": 1, "result": "0x10"}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, state


class TestRetryOn429(unittest.TestCase):
    def test_two_429_then_answer(self):
        srv, state = serve(2)
        self.addCleanup(srv.shutdown)
        self.assertEqual(get_w3(f"http://127.0.0.1:{srv.server_port}").eth.block_number, 16)
        self.assertEqual(state["n"], 3)

    def test_a_transaction_is_never_replayed(self):
        # a 429 on eth_sendRawTransaction must reach the caller after ONE request: the first attempt may already be in the mempool
        srv, state = serve(5)
        self.addCleanup(srv.shutdown)
        w3 = get_w3(f"http://127.0.0.1:{srv.server_port}")
        with self.assertRaises(Exception):
            w3.eth.send_raw_transaction(b"\x01\x02")
        self.assertEqual(state["methods"], ["eth_sendRawTransaction"])

    def test_a_long_retry_after_does_not_make_the_run_sleep(self):
        import time
        srv, state = serve(1, retry_after="3600")
        self.addCleanup(srv.shutdown)
        started = time.time()
        self.assertEqual(get_w3(f"http://127.0.0.1:{srv.server_port}").eth.block_number, 16)
        self.assertLess(time.time() - started, 20)


if __name__ == "__main__":
    unittest.main()
