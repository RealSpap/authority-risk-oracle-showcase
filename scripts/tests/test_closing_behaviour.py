"""Behaviour tests added on 30/10/2026 to the points that were only checked by reading a source file or by no test: what a 100 means (basis_fields), the depth limit of the nested-signers check, the secondary roles with no getter, the hole in the scan of the oracle's own events, and the hosts the dashboard contacts against docs/PRIVACY.md. Each one fails when the line it covers is removed. Standard library only; no network."""
import contextlib, io, json, os, re, sys, tempfile, unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import watch_run  # noqa: E402


class TestWhatAHundredMeans(unittest.TestCase):
    """basis_fields fails closed: no declaration, or a declaration the published value contradicts, is `not_computed` and never `not_applicable`."""
    A = "0x" + "ab" * 20

    def decl(self, **kw):
        d = {"oracleAuthorityBasis": "not_applicable", "oracleAuthorityReason": "No price here.", "crossExposureBasis": "computed", "crossExposureReason": "Compared."}
        d.update(kw); return {"base-ecosystem:" + self.A: d}

    def fields(self, basis, oracle=100, cross=100, slug="base-sepolia", target=None):
        return watch_run.basis_fields(slug, {"target": target or self.A, "oracleAuthorityScore": oracle, "crossExposureScore": cross}, basis)

    def test_no_declaration_is_not_computed_never_not_applicable(self):
        f = self.fields({})
        self.assertEqual((f["oracleAuthorityBasis"], f["crossExposureBasis"]), ("not_computed", "not_computed")); self.assertEqual(f["oracleAuthorityReason"], watch_run._NO_DECLARATION)

    def test_a_missing_file_gives_no_declaration(self):
        with mock.patch.object(watch_run.json, "load", side_effect=ValueError("bad json")): self.assertEqual(watch_run.load_basis(), {})
        with mock.patch("builtins.open", side_effect=OSError("no file")): self.assertEqual(watch_run.load_basis(), {})

    def test_an_unknown_state_or_an_empty_reason_is_not_computed(self):
        for bad in ({"oracleAuthorityBasis": "maybe"}, {"oracleAuthorityReason": ""}, {"oracleAuthorityBasis": None}):
            f = self.fields(self.decl(**bad)); self.assertEqual(f["oracleAuthorityBasis"], "not_computed", bad); self.assertEqual(f["oracleAuthorityReason"], watch_run._NO_DECLARATION)

    def test_a_consistent_declaration_is_shown_as_declared(self):
        f = self.fields(self.decl()); self.assertEqual((f["oracleAuthorityBasis"], f["oracleAuthorityReason"], f["crossExposureBasis"], f["crossExposureReason"]), ("not_applicable", "No price here.", "computed", "Compared."))

    def test_a_value_under_100_contradicts_not_applicable(self):
        f = self.fields(self.decl(), oracle=60); self.assertEqual((f["oracleAuthorityBasis"], f["oracleAuthorityReason"]), ("not_computed", watch_run._OUTDATED))

    def test_a_cross_exposure_under_100_needs_a_computed_declaration(self):
        f = self.fields(self.decl(crossExposureBasis="not_computed", crossExposureReason="Placeholder."), cross=80); self.assertEqual((f["crossExposureBasis"], f["crossExposureReason"]), ("not_computed", watch_run._OUTDATED))
        f = self.fields(self.decl(), cross=80); self.assertEqual(f["crossExposureBasis"], "computed")   # a computed 80 is a finding, not a contradiction

    def test_the_two_rules_that_move_a_declaration_with_the_value(self):
        f = self.fields(self.decl(oracleAuthorityBasis="not_computed", oracleAuthorityReasonCode="no_allocation_today"), oracle=40); self.assertEqual((f["oracleAuthorityBasis"], f["oracleAuthorityReason"]), ("computed", watch_run._WALK))
        f = self.fields(self.decl(oracleAuthorityBasis="computed", oracleAuthorityReasonCode="price_walk_partial"), oracle=30); self.assertEqual((f["oracleAuthorityBasis"], f["oracleAuthorityReason"]), ("not_computed", watch_run._FLOOR))
        f = self.fields(self.decl(oracleAuthorityBasis="computed", oracleAuthorityReasonCode="price_walk_partial"), oracle=15); self.assertEqual(f["oracleAuthorityBasis"], "computed")   # under 20 it is a finding

    def test_the_key_of_an_address_ignores_case_but_a_solana_address_does_not(self):
        f = self.fields(self.decl(), target=self.A.upper().replace("0X", "0x")); self.assertEqual(f["oracleAuthorityBasis"], "not_applicable")
        sol = "So1anaAddrESS1111111111111111111111111111111"
        f = watch_run.basis_fields("solana-devnet", {"target": sol, "oracleAuthorityScore": 100, "crossExposureScore": 100}, {"solana:" + sol: {"oracleAuthorityBasis": "computed", "oracleAuthorityReason": "r", "crossExposureBasis": "computed", "crossExposureReason": "r"}})
        self.assertEqual(f["oracleAuthorityBasis"], "computed")
        f = watch_run.basis_fields("solana-devnet", {"target": sol.lower(), "oracleAuthorityScore": 100, "crossExposureScore": 100}, {"solana:" + sol: {"oracleAuthorityBasis": "computed", "oracleAuthorityReason": "r", "crossExposureBasis": "computed", "crossExposureReason": "r"}})
        self.assertEqual(f["oracleAuthorityBasis"], "not_computed")


class TestTheDepthLimitReachesTheCheck(unittest.TestCase):
    """scripts/check_nested_signers.py: a Safe found below the depth bound is reported as UNANALYZED (the tree does not hold its signers), and a plain contract there is not."""
    EOA = "0x" + "11" * 20

    def run_check(self, depth_of_safes):
        import check_nested_signers as cns
        chain = ["0x" + ("%02x" % (0xa0 + i)) * 20 for i in range(depth_of_safes)]

        def get_safe(a):
            for i, s in enumerate(chain):
                if s.lower() == a.lower(): return ([self.EOA] + ([chain[i + 1]] if i + 1 < len(chain) else []), 1)
            return None

        class W3:
            def to_checksum_address(self, x): return x
            class eth:
                @staticmethod
                def get_code(x): return b"" if x.lower() == self.EOA else b"\x60\x80" * 20
        W3.eth.get_code = staticmethod(lambda x: b"" if x.lower() == self.EOA else b"\x60\x80" * 20)
        buf = io.StringIO()
        with contextlib.ExitStack() as st:
            for name, val in (("registered_safes", lambda g: {("ethereum-l1", chain[0]): ["grp"]}), ("get_w3", lambda url: W3()), ("_gated_safe_owners_and_threshold", lambda w3, a, check_modules=False: get_safe(a)),
                              ("read_modules", lambda w3, a: []), ("read_guard", lambda w3, a: None), ("read_singleton", lambda w3, a: None), ("classify", lambda m, g: {"status": "clean"}), ("classify_singleton", lambda s: "canonical")):
                st.enter_context(mock.patch.object(cns, name, val))
            with contextlib.redirect_stdout(buf): code = cns.main()
        return code, buf.getvalue()

    def test_a_safe_below_the_bound_is_listed_and_the_exit_code_says_so(self):
        code, out = self.run_check(6)   # the root and five nested Safes: the one at depth 4 is a contract to the tree
        self.assertEqual(code, 1); self.assertIn("[UNANALYZED depth limit", out); self.assertIn("the 4-level bound", out)

    def test_a_chain_that_fits_in_the_tree_has_no_depth_limit_line(self):
        code, out = self.run_check(3)
        self.assertNotIn("depth limit", out); self.assertEqual(code, 0, out)


class TestSecondaryRolesWithNoGetter(unittest.TestCase):
    """scripts/side_roles.py lists a contract that answers none of the seven role getters in `no_getter_recognised`; a contract with one role, or one unanswered call, is not listed."""
    NONE_, CURATOR, UNKNOWN = "0x" + "a1" * 20, "0x" + "a2" * 20, "0x" + "a3" * 20
    HOLDER = "0x" + "00" * 12 + "d1" * 20

    def run_side_roles(self):
        import side_roles as sr
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "scores"))
            json.dump({"targets": [{"target": t} for t in (self.NONE_, self.CURATOR, self.UNKNOWN)]}, open(os.path.join(d, "scores", "ethereum-l1-sepolia.json"), "w"))

            def rpc(url, calls, *a, **k):
                out = []
                for m, p in calls:
                    if m == "eth_call":
                        to, data = p[0]["to"].lower(), p[0]["data"][:10]
                        if to == self.CURATOR and data == sr.ROLES["curator()"]: out.append(self.HOLDER)
                        elif to == self.UNKNOWN and data == sr.ROLES["guardian()"]: out.append(None)   # this call was not answered
                        else: out.append("0x")                                                      # reverts: no such getter
                    elif m == "eth_getCode": out.append("0x")
                    else: out.append(None)
                return out
            out = os.path.join(d, "side_roles.json")
            with mock.patch.object(sr, "rpc_batch", rpc), mock.patch.object(sys, "argv", ["side_roles.py", "--scores", os.path.join(d, "scores"), "--out", out]), contextlib.redirect_stdout(io.StringIO()):
                sr.main()
            return json.load(open(out))

    def test_only_the_contract_that_answered_every_getter_with_a_revert_is_listed(self):
        doc = self.run_side_roles()
        self.assertEqual(doc["no_getter_recognised"], ["ethereum-l1:" + self.NONE_])
        self.assertIn("ethereum-l1:" + self.CURATOR, doc["by_target"]); self.assertNotIn("ethereum-l1:" + self.NONE_, doc["by_target"])


class TestAGapInTheOraclesOwnScanIsAnAlertOfTheRun(unittest.TestCase):
    """watch_run.main wires scan_progress: a window the scan gave up appears in the alerts of latest.json, and a scan with no gap adds nothing."""
    ORA = "0x" + "50" * 20

    def doc(self, gap):
        return {"name": "Fake (Sepolia)", "kind": "evm", "oracle": self.ORA, "rpc": "http://fake", "block": 1000, "maxStaleness": 777600, "readAt": 1790000000, "targets": [],
                "self": {"gap_blocks": gap, "role_events": [], "read": gap is None}, "self_scanned_to": 900}

    def alerts(self, gap):
        with tempfile.TemporaryDirectory() as tmp, contextlib.ExitStack() as st:
            st.enter_context(mock.patch.object(watch_run, "WATCH", tmp)); st.enter_context(mock.patch.object(watch_run, "ORACLES", [("Fake (Sepolia)", self.ORA, "http://fake")]))
            st.enter_context(mock.patch.object(watch_run, "read_evm_any", lambda n, o, u, since=None: self.doc(gap)))
            st.enter_context(mock.patch.object(watch_run, "read_solana", lambda: (_ for _ in ()).throw(RuntimeError("no Solana in this test"))))
            st.enter_context(mock.patch.object(watch_run, "block_time_of", lambda rpc, block: 1790000100))
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                try: watch_run.main()
                except SystemExit: pass
            return json.load(open(os.path.join(tmp, "latest.json")))["alerts"]

    def test_a_given_up_window_is_in_the_alerts(self):
        got = [a for a in self.alerts(777) if "gave up a window of 777 blocks" in a]
        self.assertEqual(len(got), 1, got)

    def test_no_gap_no_such_alert(self):
        self.assertEqual([a for a in self.alerts(None) if "gave up a window" in a], [])


class TestTheDashboardContactsOnlyWhatThePrivacyPageNames(unittest.TestCase):
    """Every host the dashboard asks (the stylesheet, the fetch calls, the `rpc` and `apiBase` addresses) is named in docs/PRIVACY.md."""
    def hosts(self):
        t = open(os.path.join(ROOT, "dashboard", "index.html"), encoding="utf-8").read(); found = set()
        for pat in (r'<link[^>]*rel="stylesheet"[^>]*href="https://([A-Za-z0-9.-]+)', r"fetch\('https://([A-Za-z0-9.-]+)", r"\brpc: *'https://([A-Za-z0-9.-]+)", r"\bapiBase: *'https://([A-Za-z0-9.-]+)"): found |= set(re.findall(pat, t))
        return found

    def test_every_contacted_host_is_named_on_the_privacy_page(self):
        page = open(os.path.join(ROOT, "docs", "PRIVACY.md"), encoding="utf-8").read(); hosts = self.hosts()
        self.assertGreaterEqual(len(hosts), 12, hosts)   # the test would pass on nothing if the extraction broke
        for h in ("fonts.googleapis.com", "raw.githubusercontent.com", "r.jina.ai", "api.devnet.solana.com"): self.assertIn(h, hosts)
        self.assertEqual(sorted(h for h in hosts if h not in page), [])


if __name__ == "__main__":
    unittest.main()
