"""A label that cannot be read in full is UNREAD (exit 3), never a traceback: the server sends fewer bytes than it announced."""
import contextlib, http.server, io, os, sys, threading, unittest
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "integrations"))
import authority_facts_gate_strict as g


class Truncated(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200); self.send_header("Content-Length", "500"); self.end_headers(); self.wfile.write(b'{"composite": 80'); self.wfile.flush()
    def log_message(self, *a): pass


class T(unittest.TestCase):
    def test_incomplete_read_is_unread(self):
        srv = http.server.HTTPServer(("127.0.0.1", 0), Truncated); threading.Thread(target=srv.serve_forever, daemon=True).start()
        out = io.StringIO()
        try:
            with contextlib.redirect_stdout(out): rc = g.main(["http://127.0.0.1:%d/x.json" % srv.server_port])
        finally: srv.shutdown()
        self.assertEqual(rc, 3); self.assertIn("UNREAD", out.getvalue())


if __name__ == "__main__": unittest.main()
