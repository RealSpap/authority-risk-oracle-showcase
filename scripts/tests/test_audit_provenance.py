"""Tests of the provenance additions of 30/10/2026 (audit of the published checks): the strict gate and schema, signature checks of authority_check, sign_run and verify_chain, the shared score-file rules,
the retired filter of agent_tools, the run identifier, and the test workflow. The default behaviours that the changed code touches are sampled here to be unchanged. Standard library only (PyNaCl for the signing tests: skipped without it)."""
import contextlib, hashlib, importlib.util, io, json, os, re, sys, tempfile, time, unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts")); sys.path.insert(0, os.path.join(ROOT, "integrations")); sys.path.insert(0, os.path.join(ROOT, "packages", "authority-risk-mcp"))
import agent_tools, authority_check, check_run_id, conformance, run_id, sign_run, snapshot_rules, verify_chain  # noqa: E402
import authority_facts_gate, authority_facts_gate_strict  # noqa: E402

try:
    import nacl.signing
    HAVE_NACL = True
except ImportError:
    HAVE_NACL = False

SEED = "11" * 32
PUB = nacl.signing.SigningKey(bytes.fromhex(SEED)).verify_key.encode().hex() if HAVE_NACL else ""
A = "0xaaa0000000000000000000000000000000000001"
B = "0xbbb0000000000000000000000000000000000002"
LABEL = {"chain": "Base", "address": "0xabc", "composite": 55, "band": "moderate", "keys_to_move": 2, "react_hours": 48, "money_per_key_usd": 10.5,
         "sub": {"adminKeyScore": 65, "multisigScore": 95, "timelockScore": 0, "oracleAuthorityScore": 100, "crossExposureScore": 80}, "requirements": [{"label": "r", "met": True}] * 6, "independent_read": None,
         "last_pushed": 1, "stale": False, "methodology_hash": "0x" + "ab" * 32, "block": 5, "license": "CC BY 4.0"}

GL = dict(LABEL, composite=70, band="decent")   # a label for the gate: the demonstration lines are composite 60 and 24 hours


def lines():
    out = []
    return out, out.append


def run_script(mod_main, args, env=None):
    """(exit code, printed text) of a script's main() that prints and exits."""
    buf = io.StringIO()
    with mock.patch.object(sys, "argv", ["x"] + list(args)), mock.patch.dict(os.environ, env or {}), contextlib.redirect_stdout(buf), contextlib.redirect_stderr(io.StringIO()):
        try: r = mod_main(); code = r if isinstance(r, int) else 0
        except SystemExit as e: code = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
    return code, buf.getvalue()


def no_nacl():
    return mock.patch.dict(sys.modules, {"nacl": None, "nacl.signing": None})   # an import of PyNaCl now raises ImportError


class Folder(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.watch = os.path.join(self.tmp.name, "watch"); os.makedirs(os.path.join(self.watch, "scores"))
        self.score_path = os.path.join(self.watch, "scores", "base-sepolia.json")
        self.write_score()

    def write_score(self, **over):
        t = {"target": A, "compositeScore": 65, "adminKeyScore": 70, "multisigScore": 80, "timelockScore": 20, "stale": False, "previousComposite": 66}; t.update(over)
        json.dump({"targets": [t], "readAt": time.time()}, open(self.score_path, "w"))

    def sign(self, key=SEED, env_extra=None):
        return run_script(sign_run.main, ["--watch", self.watch], dict({"WATCH_SIGNING_KEY": key}, **(env_extra or {})))

    def verify(self, *extra, env=None):
        return run_script(sign_run.main, ["--watch", self.watch, "--verify"] + list(extra), env)

    def check(self, *extra):
        out, add = lines(); code = authority_check.main(["--source", os.path.join(self.watch, "scores"), "--target", "base:%s:0" % A] + list(extra), out=add); return code, out


class TestGateOptions(unittest.TestCase):
    def test_the_published_gate_is_unchanged(self):
        self.assertEqual(authority_facts_gate.gate(GL), (True, "ok: Base 70 (decent), 48 h to react"))
        self.assertEqual(authority_facts_gate.gate(dict(GL, keys_to_move=None))[0], True)   # default: keys not required
        self.assertEqual(len(open(os.path.join(ROOT, "integrations", "authority_facts_gate.py")).read().splitlines()), 18)   # the file the page links to: 18 lines since the second round of review made it refuse what it does not know (it was 16)

    def test_the_lines_are_options(self):
        self.assertFalse(authority_facts_gate_strict.strict_gate(GL, min_composite=80)[0])
        self.assertFalse(authority_facts_gate_strict.strict_gate(GL, min_react_hours=72)[0])
        self.assertEqual(authority_facts_gate_strict.strict_gate(GL), authority_facts_gate.gate(GL))

    def test_strict_refuses_what_the_default_accepts(self):
        unread = dict(GL, keys_to_move=None, money_per_key_usd=None)
        self.assertTrue(authority_facts_gate_strict.strict_gate(unread)[0])
        self.assertFalse(authority_facts_gate_strict.strict_gate(unread, strict=True)[0])
        listed = dict(GL, not_assessed=["no TVL match"])
        self.assertTrue(authority_facts_gate_strict.strict_gate(listed)[0])
        ok, why = authority_facts_gate_strict.strict_gate(listed, strict=True); self.assertFalse(ok); self.assertIn("no TVL match", why)
        self.assertTrue(authority_facts_gate_strict.strict_gate(dict(GL, not_assessed=[]), strict=True)[0])

    def test_a_not_assessed_that_is_not_a_list_is_still_refused_cleanly(self):
        for na in ("no TVL match", {"a": 1}, 3): self.assertFalse(authority_facts_gate_strict.strict_gate(dict(GL, not_assessed=na), strict=True)[0], na)

    def test_the_command_line(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "l.json"); json.dump(GL, open(p, "w"))
            self.assertEqual(run_script(lambda: authority_facts_gate_strict.main([p]), [])[0], 0)
            self.assertEqual(run_script(lambda: authority_facts_gate_strict.main([p, "--min-composite", "90"]), [])[0], 1)
            json.dump(dict(GL, keys_to_move=None, money_per_key_usd=None), open(p, "w"))
            self.assertEqual(run_script(lambda: authority_facts_gate_strict.main([p, "--require-keys"]), [])[0], 1)
            self.assertEqual(run_script(lambda: authority_facts_gate_strict.main([p, "--strict"]), [])[0], 1)


class TestStrictSchema(unittest.TestCase):
    def setUp(self):
        self.schema = json.load(open(conformance.SCHEMA)); self.strict = json.load(open(conformance.STRICT_SCHEMA))

    def test_the_published_schema_is_untouched_and_the_strict_one_sits_next_to_it(self):
        self.assertEqual(hashlib.md5(open(conformance.SCHEMA, "rb").read()).hexdigest(), "03064a4cdf6ec5e6d929b64184483a74")
        self.assertTrue(os.path.basename(conformance.STRICT_SCHEMA) == "label.strict.schema.json" and os.path.dirname(conformance.STRICT_SCHEMA) == os.path.dirname(conformance.SCHEMA))

    def test_a_good_label_passes_both_ways(self):
        self.assertEqual(conformance.judge(LABEL, self.schema), ([], [])); self.assertEqual(conformance.judge(LABEL, self.schema, self.strict), ([], []))

    def test_what_only_the_strict_reading_refuses(self):
        for name, label in (("missing sub-scores", dict(LABEL, sub={"adminKeyScore": 65, "multisigScore": 95, "timelockScore": 0})),
                            ("sub-score over 100", dict(LABEL, sub=dict(LABEL["sub"], crossExposureScore=101))),
                            ("negative block", dict(LABEL, block=-1)), ("last_pushed zero", dict(LABEL, last_pushed=0)), ("empty chain", dict(LABEL, chain=""))):
            with self.subTest(name):
                self.assertEqual(conformance.judge(label, self.schema)[0], [], "the plain reading accepted it before and still does")
                self.assertTrue(conformance.judge(label, self.schema, self.strict)[0], name)

    def test_a_difference_from_the_formula_is_a_failure_in_strict_mode_only(self):
        capped = dict(LABEL, composite=60, band="decent")
        self.assertEqual(conformance.judge(capped, self.schema)[0], []); self.assertTrue(conformance.judge(capped, self.schema)[1])
        errs, diffs = conformance.judge(capped, self.schema, self.strict); self.assertTrue(any(e.startswith("strict:") for e in errs)); self.assertEqual(diffs, [])

    def test_a_number_that_is_not_finite_is_refused(self):
        for bad in (float("nan"), float("inf")):
            errs = []; conformance.check_bounds(dict(LABEL, money_per_key_usd=bad), self.strict, "label", errs); self.assertTrue(errs, bad)

    def test_each_bound_of_the_strict_schema_on_its_own(self):
        for field, bad in (("methodology_hash", "0x12"), ("composite", 101), ("composite", -1), ("keys_to_move", 0), ("react_hours", -1), ("money_per_key_usd", 0), ("requirements", [{"label": "r", "met": True}] * 5), ("requirements", [{"label": "r", "met": True}] * 7), ("license", "")):
            errs = []; conformance.check_bounds(dict(LABEL, **{field: bad}), self.strict, "label", errs); self.assertTrue(errs, (field, bad))
        errs = []; conformance.check_bounds(LABEL, self.strict, "label", errs); self.assertEqual(errs, []); conformance.check_bounds(dict(LABEL, keys_to_move=None, react_hours=None, money_per_key_usd=None, composite=True), self.strict, "label", errs); self.assertEqual(errs, [])

    def test_the_command_line_and_its_default_output(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "t.json"); json.dump(dict(LABEL, sub={"adminKeyScore": 65, "multisigScore": 95, "timelockScore": 0}), open(p, "w"))
            out, add = lines(); self.assertEqual(conformance.main([p], out=add), 0); self.assertEqual(out, ["conformance: 1 label(s), 0 break the specification, 0 with a difference to declare"])
            out, add = lines(); self.assertEqual(conformance.main(["--strict", p], out=add), 1); self.assertTrue(out[0].startswith("FAIL t.json: label.sub: required"))


class TestChainHead(unittest.TestCase):
    def events(self, n=3):
        d = tempfile.TemporaryDirectory(); self.addCleanup(d.cleanup); p = os.path.join(d.name, "events.jsonl"); prev = ""; ls = []
        for i in range(1, n + 1):
            l = json.dumps({"seq": i, "prev": prev, "run_utc": "2026-10-1%dT00:00:00Z" % i}); ls.append(l); prev = hashlib.sha256(l.encode()).hexdigest()
        open(p, "w").write("\n".join(ls) + "\n"); return p, prev, ls

    def test_the_default_is_unchanged(self):
        p, head, _ = self.events(); code, out = run_script(verify_chain.main, ["--events", p]); self.assertEqual(code, 0); self.assertIn("chain intact: 3 chained line(s)", out)

    def test_the_pinned_head_must_be_the_end_of_the_log(self):
        p, head, ls = self.events()
        self.assertEqual(run_script(verify_chain.main, ["--events", p, "--head", head])[0], 0)
        self.assertEqual(run_script(verify_chain.main, ["--events", p, "--head", head.upper()])[0], 0)
        open(p, "w").write("\n".join(ls[:2]) + "\n")                                  # the tail was cut: every remaining link still holds
        self.assertEqual(run_script(verify_chain.main, ["--events", p])[0], 0)       # which is why links alone cannot see it
        code, out = run_script(verify_chain.main, ["--events", p, "--head", head]); self.assertEqual(code, 1); self.assertIn("CHAIN HEAD MISMATCH", out)

    def test_a_broken_chain_and_a_missing_file_keep_their_codes(self):
        p, head, ls = self.events(); open(p, "w").write("\n".join([ls[0], ls[2]]) + "\n")
        self.assertEqual(run_script(verify_chain.main, ["--events", p, "--head", head])[0], 1)
        self.assertEqual(run_script(verify_chain.main, ["--events", p + ".none"])[0], 2)                  # no pinned head: as before
        code, out = run_script(verify_chain.main, ["--events", p + ".none", "--head", head]); self.assertEqual(code, 1); self.assertIn("the log is gone", out)   # a pinned head and no log is a cut tail
        for blank in ("", "  "): self.assertEqual(run_script(verify_chain.main, ["--events", p, "--head", blank])[0], 1)
        open(p, "w").write("")                                                                              # an emptied log has head None: a blank --head must not match it
        for blank in ("", "  "): self.assertEqual(run_script(verify_chain.main, ["--events", p, "--head", blank])[0], 1, repr(blank))   # an empty head would pass an emptied log: refused (1, not the 2 that the workflow tolerates)


class TestWithoutPyNaClAtAll(Folder):
    """These run whether or not PyNaCl is installed here: the signature.json is written by hand and PyNaCl is made unimportable, so the INCOMPLETE guard is exercised on every machine."""
    KEY = "ab" * 32

    def hand_signed(self):
        json.dump({"run_utc": "2026-10-30T00:00:00Z", "manifest": sign_run.manifest(self.watch), "signed": True, "public_key": self.KEY, "signature": "00" * 64}, open(os.path.join(self.watch, "signature.json"), "w"))

    def test_sign_run_verify_is_incomplete_exit_3(self):
        self.hand_signed()
        with no_nacl(): code, out = self.verify()
        self.assertEqual((code, "INCOMPLETE" in out, "NOT CHECKED" in out), (3, True, True))

    def test_sign_run_signing_is_incomplete_exit_3_and_writes_nothing(self):
        with no_nacl(): code, out = self.sign()
        self.assertEqual(code, 3); self.assertIn("INCOMPLETE", out); self.assertFalse(os.path.exists(os.path.join(self.watch, "signature.json")))

    def test_authority_check_is_incomplete_exit_3_even_with_allow_unread(self):
        self.hand_signed()
        with no_nacl(): code, out = self.check("--verify-signature", "--pin", self.KEY, "--allow-unread")
        self.assertEqual(code, 3); self.assertTrue(any(l.startswith("SIGNATURE INCOMPLETE") for l in out), out)

    def test_a_changed_file_is_still_a_failure_without_pynacl(self):
        self.hand_signed(); self.write_score(compositeScore=10)
        with no_nacl(): self.assertEqual(self.verify()[0], 1)


@unittest.skipUnless(HAVE_NACL, "PyNaCl is not installed")
class TestSignRun(Folder):
    def test_a_signed_run_verifies_by_default_as_before(self):
        self.assertEqual(self.sign()[0], 0); code, out = self.verify(); self.assertEqual(code, 0); self.assertIn("signature valid", out)

    def test_pin_accepts_the_key_and_refuses_another(self):
        self.sign(); self.assertEqual(self.verify("--pin", PUB)[0], 0)
        code, out = self.verify("--pin", "22" * 32); self.assertEqual(code, 1); self.assertIn("not a pinned key", out)
        self.assertEqual(self.verify("--pin", PUB.upper())[0], 0)
        self.assertEqual(self.verify("--pin", "published")[0], 1)   # the test key is not the published one

    def test_an_unsigned_run_cannot_satisfy_a_pin(self):
        self.sign(key=""); code, out = self.verify("--pin", PUB); self.assertEqual(code, 1); self.assertIn("unsigned", out)
        self.assertEqual(self.verify()[0], 0)   # without a pin an unsigned run still verifies, as before

    def test_pin_goes_with_verify(self):
        self.assertEqual(run_script(sign_run.main, ["--watch", self.watch, "--pin", PUB])[0], 2)

    def test_without_pynacl_a_check_is_incomplete_never_a_pass_or_a_traceback(self):
        self.sign()
        with no_nacl(): code, out = self.verify()
        self.assertEqual(code, 3); self.assertIn("INCOMPLETE", out); self.assertIn("NOT CHECKED", out)
        self.write_score(compositeScore=10)
        with no_nacl(): code, out = self.verify()
        self.assertEqual(code, 1, "a changed file is a failure whether or not the signature could be checked"); self.assertIn("scores/base-sepolia.json", out)

    def test_without_pynacl_nothing_is_signed_and_nothing_is_written(self):
        with no_nacl(): code, out = self.sign()
        self.assertEqual(code, 3); self.assertIn("INCOMPLETE", out); self.assertFalse(os.path.exists(os.path.join(self.watch, "signature.json")))
        with no_nacl(): self.assertEqual(run_script(sign_run.main, ["--new-key"])[0], 3)

    def test_without_a_key_the_manifest_is_still_written_unsigned(self):
        code, out = self.sign(key=""); self.assertEqual(code, 0); self.assertFalse(json.load(open(os.path.join(self.watch, "signature.json")))["signed"])


@unittest.skipUnless(HAVE_NACL, "PyNaCl is not installed")
class TestAuthorityCheckSignature(Folder):
    def test_the_default_does_not_look_at_the_signature_as_before(self):
        self.sign(); self.write_score(compositeScore=66)                        # changed after signing
        code, out = self.check(); self.assertEqual(code, 0); self.assertFalse(any("SIGNATURE" in l for l in out))

    def test_a_valid_pinned_signature_over_the_file_that_was_read(self):
        self.sign(); code, out = self.check("--verify-signature", "--pin", PUB)
        self.assertEqual(code, 0, out); self.assertTrue(any(l.startswith("SIGNATURE ok: ") and "scores/base-sepolia.json" in l and "(pinned)" in l for l in out), out)

    def test_a_key_that_is_not_pinned_fails(self):
        self.sign(); code, out = self.check("--verify-signature"); self.assertEqual(code, 1); self.assertTrue(any("not pinned" in l for l in out))

    def test_a_score_file_that_is_not_the_signed_one_fails(self):
        self.sign(); self.write_score(compositeScore=66)
        code, out = self.check("--verify-signature", "--pin", PUB); self.assertEqual(code, 1); self.assertTrue(any("SIGNATURE FAIL" in l and "scores/base-sepolia.json" in l for l in out), out)

    def test_no_signature_is_unread_not_a_pass(self):
        code, out = self.check("--verify-signature", "--pin", PUB); self.assertEqual(code, 3); self.assertTrue(any(l.startswith("SIGNATURE UNREAD") for l in out))
        self.assertEqual(self.check("--verify-signature", "--pin", PUB, "--allow-unread")[0], 3, "--allow-unread covers a score file that cannot be read, not a signature that was asked for")

    def test_an_unsigned_run_fails(self):
        self.sign(key=""); code, out = self.check("--verify-signature"); self.assertEqual(code, 1); self.assertTrue(any("unsigned" in l for l in out))

    def test_a_forged_or_edited_signature_fails(self):
        self.sign(); p = os.path.join(self.watch, "signature.json"); good = json.load(open(p))
        json.dump(dict(good, signature="00" * 64), open(p, "w")); code, out = self.check("--verify-signature", "--pin", PUB)
        self.assertEqual(code, 1); self.assertTrue(any("not valid" in l for l in out), out)
        edited = json.loads(json.dumps(good)); edited["manifest"]["count"] = 999; json.dump(edited, open(p, "w"))
        self.assertEqual(self.check("--verify-signature", "--pin", PUB)[0], 1)

    def test_a_public_key_written_in_capitals_is_the_same_key(self):
        self.sign(); p = os.path.join(self.watch, "signature.json"); d = json.load(open(p)); json.dump(dict(d, public_key=d["public_key"].upper()), open(p, "w"))
        self.assertEqual(self.check("--verify-signature", "--pin", PUB)[0], 0)

    def test_a_failing_score_outranks_an_unread_signature(self):
        out, add = lines(); code = authority_check.main(["--source", os.path.join(self.watch, "scores"), "--target", "base:%s:99" % A, "--verify-signature", "--pin", PUB, "--allow-unread"], out=add)
        self.assertEqual(code, 1, out)   # no signature.json here, and the composite 65 is under 99: the failure outranks the unread signature

    def test_a_signature_file_that_is_not_json_is_unread_not_a_traceback(self):
        open(os.path.join(self.watch, "signature.json"), "w").write("not json"); code, out = self.check("--verify-signature", "--pin", PUB)
        self.assertEqual(code, 3); self.assertTrue(any(l.startswith("SIGNATURE UNREAD") for l in out))

    def test_pin_published_takes_the_published_key(self):
        self.sign()
        with mock.patch.object(sign_run.audit_public, "PINNED_KEYS", (PUB,)): self.assertEqual(self.verify("--pin", "published")[0], 0)

    def test_the_url_branch_of_the_location_needs_a_path_boundary(self):
        self.assertEqual(authority_check.signature_location("https://h/b/myscores"), "https://h/b/myscores/signature.json")

    def test_a_signature_that_covers_no_file_that_was_read_says_so(self):
        self.sign(); out, add = lines(); authority_check.main(["--source", os.path.join(self.watch, "scores"), "--target", "monad:0x1", "--verify-signature", "--pin", PUB, "--allow-unread"], out=add)
        self.assertTrue(any("covers no score file that was read" in l for l in out), out)

    def test_without_pynacl_it_is_incomplete(self):
        self.sign()
        with no_nacl(): code, out = self.check("--verify-signature", "--pin", PUB)
        self.assertEqual(code, 3); self.assertTrue(any(l.startswith("SIGNATURE INCOMPLETE") for l in out))

    def test_the_signature_is_looked_for_next_to_the_scores_folder_or_where_it_is_told(self):
        self.assertEqual(authority_check.signature_location(os.path.join(self.watch, "scores")), os.path.join(self.watch, "signature.json"))
        self.assertEqual(authority_check.signature_location("https://h/b/scores/"), "https://h/b/signature.json")
        self.assertEqual(authority_check.signature_location("/x", "/y/s.json"), "/y/s.json")


class TestSharedRules(unittest.TestCase):
    def test_one_age_limit_and_the_gate_uses_it(self):
        self.assertEqual(snapshot_rules.MAX_AGE_HOURS, 48)
        self.assertEqual(authority_check.check_one.__defaults__[-1], snapshot_rules.MAX_AGE_HOURS)
        ap_default = [a for a in re.findall(r"default=rules\.MAX_AGE_HOURS", open(os.path.join(ROOT, "scripts", "authority_check.py")).read())]
        self.assertTrue(ap_default, "the command line default comes from the shared constant")

    def test_the_agent_tools_and_the_package_carry_the_same_rules(self):
        self.assertIs(agent_tools.snapshot_rules, snapshot_rules)
        import vendor_tools
        self.assertIn("snapshot_rules", vendor_tools.MODULES); self.assertIn("snapshot_rules.py", vendor_tools.expected())

    def test_the_rules(self):
        now = 1_000_000.0
        self.assertIsNone(snapshot_rules.document_problem({"targets": [], "readAt": now}, now))
        for doc in (None, [1], {"targets": "x"}, {"targets": []}, {"targets": [], "readAt": True}, {"targets": [], "readAt": now + 7200}, {"targets": [], "readAt": now - 49 * 3600}):
            self.assertTrue(snapshot_rules.document_problem(doc, now), doc)
        self.assertTrue(snapshot_rules.document_problem({"targets": [], "readAt": now - 5 * 3600}, now, max_age_hours=4))
        self.assertIsNone(snapshot_rules.document_problem({"targets": [], "readAt": now - 47 * 3600}, now, max_age_hours=0))   # a limit of 0 falls back to 48, it does not switch the check off
        self.assertTrue(snapshot_rules.composite_problem({"compositeScore": True})); self.assertIsNone(snapshot_rules.composite_problem({"compositeScore": 0}))
        self.assertTrue(snapshot_rules.stale_problem({"stale": None})); self.assertTrue(snapshot_rules.stale_problem({})); self.assertIsNone(snapshot_rules.stale_problem({"stale": True}))


class TestRetiredTargets(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup); self.W = self.tmp.name; os.makedirs(os.path.join(self.W, "scores"))
        def tgt(addr, comp): return {"target": addr, "adminKeyScore": 80, "multisigScore": 100, "timelockScore": 75, "oracleAuthorityScore": 100, "crossExposureScore": 80, "compositeScore": comp, "lastUpdated": 1790000000, "stale": False, "methodologyHash": "0x" + "11" * 32}
        json.dump({"name": "Base (Sepolia)", "kind": "evm", "oracle": "0x50840a7667baEa9D05ad4ae3dCeb384724b58720", "rpc": "https://sepolia.base.org", "block": 1, "maxStaleness": 777600, "readAt": int(time.time()) - 3600, "targets": [tgt(A, 70), tgt(B, 30)]},
                  open(os.path.join(self.W, "scores", "base-sepolia.json"), "w"))

    def scope(self, **rec): json.dump({"targets": {"base:" + B.upper().replace("0X", "0x"): rec}}, open(os.path.join(self.W, "tvl_scope.json"), "w"))

    def test_without_a_scope_file_nothing_changes(self):
        self.assertEqual(agent_tools.get_score(self.W, "base", B)["status"], "ok"); self.assertEqual(agent_tools.list_targets(self.W)["of"], 2)

    def test_a_retired_contract_answers_retired_with_no_score(self):
        self.scope(scope="retired", note="minter retired on 2026-09-20", since="2026-10-10")
        r = agent_tools.get_score(self.W, "base", B); self.assertEqual((r["status"], r["composite"]), ("retired", None)); self.assertIn("minter retired", r["reason"])
        self.assertEqual(agent_tools.who_controls(self.W, "base", B)["status"], "retired")
        self.assertEqual(agent_tools.get_score(self.W, "base", A)["status"], "ok")

    def test_it_is_left_out_of_the_lists_and_counted(self):
        self.scope(scope="retired"); r = agent_tools.list_targets(self.W)
        self.assertEqual((r["of"], r["retired_not_listed"]), (1, 1)); self.assertEqual([x["address"] for x in r["rows"]], [A])

    def test_a_retired_contract_is_not_counted_in_a_protocol(self):
        json.dump({"matched": {"base:" + A: {"name": "Alpha Swap V3", "slug": "alpha-swap-v3", "tvl": 1000000}, "base:" + B: {"name": "Alpha Swap V3", "slug": "alpha-swap-v3", "tvl": 1000000}}}, open(os.path.join(self.W, "tvl.json"), "w"))
        before = agent_tools.check_protocol(self.W, "Alpha Swap V3", 0)
        self.assertEqual(before.get("status"), "ok", before)
        self.assertEqual(before["contracts"], 2); self.scope(scope="retired")
        after = agent_tools.check_protocol(self.W, "Alpha Swap V3", 0); self.assertEqual(after["contracts"], 1)
        json.dump({"targets": {"base:" + A: {"scope": "retired"}, "base:" + B: {"scope": "retired"}}}, open(os.path.join(self.W, "tvl_scope.json"), "w"))
        self.assertEqual(agent_tools.check_protocol(self.W, "Alpha Swap V3", 0)["status"], "retired")
        self.assertEqual(agent_tools.check_protocol(self.W, "nothing at all", 0)["status"], "not_tracked", "a protocol that never existed is not a retired one")

    def test_a_fully_retired_protocol_does_not_fall_through_to_another_whose_name_contains_the_query(self):
        json.dump({"matched": {"base:" + A: {"name": "Ethena", "slug": "ethena", "tvl": 1}, "base:" + B: {"name": "Ethena Staking", "slug": "ethena-staking", "tvl": 1}}}, open(os.path.join(self.W, "tvl.json"), "w"))
        self.assertEqual(agent_tools.check_protocol(self.W, "ethena", 0)["name"], "Ethena")
        json.dump({"targets": {"base:" + A: {"scope": "retired"}}}, open(os.path.join(self.W, "tvl_scope.json"), "w"))
        self.assertEqual(agent_tools.check_protocol(self.W, "ethena", 0)["status"], "retired")

    def test_a_peripheral_contract_is_not_retired(self):
        self.scope(scope="peripheral"); self.assertEqual(agent_tools.get_score(self.W, "base", B)["status"], "ok")


class TestRunId(Folder):
    def test_the_identifier(self):
        self.assertEqual(run_id.current({"GITHUB_RUN_ID": "123", "GITHUB_RUN_ATTEMPT": "2"}), "123.2"); self.assertEqual(run_id.current({"GITHUB_RUN_ID": "123"}), "123.1")
        for bad in ({}, {"GITHUB_RUN_ID": ""}, {"GITHUB_RUN_ID": "12x"}, {"GITHUB_RUN_ID": "12; rm"}): self.assertIsNone(run_id.current(bad))

    @unittest.skipUnless(HAVE_NACL, "PyNaCl is not installed")
    def test_the_signature_record_carries_it_only_inside_actions(self):
        env = {"GITHUB_RUN_ID": "", "WATCH_SIGNING_KEY": SEED}
        self.sign(env_extra={"GITHUB_RUN_ID": ""}); self.assertNotIn("run_id", json.load(open(os.path.join(self.watch, "signature.json"))))
        self.sign(env_extra={"GITHUB_RUN_ID": "777", "GITHUB_RUN_ATTEMPT": "1"}); rec = json.load(open(os.path.join(self.watch, "signature.json")))
        self.assertEqual(rec["run_id"], "777.1"); self.assertNotIn("run_id", rec["manifest"], "the signed format is not changed")

    def test_the_check(self):
        def put(n, rid): json.dump({"run_id": rid} if rid else {}, open(os.path.join(self.watch, n), "w"))
        self.assertEqual(check_run_id.main(["--watch", self.watch], out=lambda t: None), 3)                    # nothing carries one: nothing to compare, not a pass
        put("latest.json", "5.1"); self.assertEqual(check_run_id.main(["--watch", self.watch], out=lambda t: None), 3)
        put("status.json", "5.1"); put("signature.json", "5.1"); self.assertEqual(check_run_id.main(["--watch", self.watch], out=lambda t: None), 0)
        out = []; put("status.json", "4.1"); self.assertEqual(check_run_id.main(["--watch", self.watch], out=out.append), 1); self.assertIn("status.json=4.1", out[0])


class TestWorkflowAndLock(unittest.TestCase):
    def test_the_test_workflow_has_minimal_permissions_and_pinned_actions(self):
        t = open(os.path.join(ROOT, ".github", "workflows", "test.yml")).read()
        self.assertRegex(t, r"(?m)^permissions:\n  contents: read\n")
        unpinned = [m for m in re.findall(r"uses:\s*(\S+)", t) if not re.search(r"@[0-9a-f]{40}$", m)]
        self.assertEqual(unpinned, [], "every action of the test workflow is pinned to a commit")

    def test_a_lock_file_when_it_exists_pins_every_package_with_hashes(self):
        p = os.path.join(ROOT, "scripts", "requirements.lock")
        if not os.path.exists(p): self.skipTest("scripts/requirements.lock is not there yet (see the lot notes)")
        blocks = re.split(r"\n(?=[A-Za-z0-9_.-]+==)", open(p).read())
        pkgs = [b for b in blocks if re.match(r"[A-Za-z0-9_.-]+==", b)]
        self.assertTrue(pkgs); self.assertTrue(all("--hash=sha256:" in b for b in pkgs))


if __name__ == "__main__":
    unittest.main()
