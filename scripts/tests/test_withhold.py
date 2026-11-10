"""scripts/withhold.py: entries left out of the public view. Offline, with made-up addresses (none is a real multisig or program).

Each case is one way the view could show what it should not: a queue still listed, a total that counts it, a carried file (alert history, ledger, digest) that remembers it, the list printed,
a missing or malformed list that changes what is published, a record that reaches another queue, a count of 0 that reads as a measure."""
import json, os, re, shutil, stat, subprocess, sys, tempfile, unittest, warnings

warnings.simplefilter("ignore", ResourceWarning)   # the helpers read their JSON with a bare open(): not what these tests are about

HERE = os.path.dirname(os.path.abspath(__file__)); SCRIPTS = os.path.join(HERE, ".."); SCRIPT = os.path.join(SCRIPTS, "withhold.py")
sys.path.insert(0, SCRIPTS)
import withhold as W  # noqa: E402

HELD_MS, HELD_PROG = "HeldMultisigAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA1", "HeldProgramBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB2"
OTHER_MS, OTHER_PROG = "OtherMultisigCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCC3", "OtherProgramDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDD4"
TL = "0xTimelockEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEE05"
HELD_NAME = "Example multisig v4 %s (3-of-5, time lock 0 s), found by the independent reader (1 tracked program)" % W.short(HELD_MS)
OTHER_NAME = "Example multisig v4 %s (2-of-3, time lock 0 s), found by the independent reader (1 tracked program)" % W.short(OTHER_MS)
H_ACCT, H_TX = "HeldProposalAccountFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF6", "HeldTransactionGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGG7"
H_ID1, H_ID2 = "example:%s:41" % HELD_MS, "example:%s:42" % HELD_MS
H_SIG = "Example proposal #41: Upgrade of program %s" % HELD_PROG


def held_record():
    return {"name": HELD_NAME, "chain": "solana", "address": HELD_MS, "family": "famx", "status": "ok", "discovered": True, "governs": [HELD_PROG], "delay": 0,
            "queued_events": 30, "latest_queued": 1794000000, "transaction_index": 42, "proposals": {"approved": 2, "active": 5, "executed": 9},
            "pending": [{"id": H_ID1, "index": 41, "target": HELD_PROG, "signature": H_SIG, "ready_at": 1793000000, "state": "ready", "approved_at": 1792900000, "account": H_ACCT},
                        {"id": H_ID2, "index": 42, "target": HELD_PROG, "signature": "Example proposal #42: x", "ready_at": 1794000000, "state": "waiting", "approved_at": 1793900000, "account": "HeldAccount2ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ"}],
            "recent": [{"id": "example:%s:40" % HELD_MS, "index": 40, "target": HELD_PROG, "still_queued": False, "tx": H_TX, "account": "HeldAccount3YYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYY"}],
            "active": [{"index": 43, "approvals": 1, "rejections": 0, "since": 1794100000, "account": "HeldAccount4XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"}]}


def other_record():
    return {"name": OTHER_NAME, "chain": "solana", "address": OTHER_MS, "family": "famx", "status": "ok", "discovered": True, "governs": [OTHER_PROG], "delay": 0,
            "queued_events": 3, "latest_queued": 1790000000, "transaction_index": 3, "proposals": {"approved": 1},
            "pending": [{"id": "example:%s:2" % OTHER_MS, "index": 2, "target": OTHER_PROG, "signature": "Example proposal #2: y", "ready_at": 1795000000, "state": "waiting", "account": "OtherAccountHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHH"}], "recent": [], "active": []}


def evm_record():
    return {"name": "oz timelock", "chain": "ethereum", "address": TL, "family": "oz", "status": "ok", "delay": 86400, "queued_events": 1, "latest_queued": 5,
            "pending": [{"id": "0xabc0000000000000000000000000000000000000000000000000000000000001", "target": "0xTarget", "ready_at": 1796000000, "state": "waiting"}], "recent": []}


class Base(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, self.d, True); self.w = os.path.join(self.d, "watch"); os.makedirs(self.w); self.private = os.path.join(self.d, "held.json")
        self.put("pending_ops.json", {"days": 90, "results": [held_record(), other_record(), evm_record()], "discovered": 15, "example_utc": "2026-11-09T06:00:00Z"})
        rule = "a queued change against this contract is ready to execute now"
        self.put("alerts.json", {"active": [], "history": [{"key": rule + "|solana:" + HELD_PROG, "rule": rule, "target": HELD_PROG, "title": "t"},
                                                         {"key": rule + "|solana:" + OTHER_PROG, "rule": rule, "target": OTHER_PROG, "title": "t2"},
                                                         {"key": "an upgrade was executed|solana:" + HELD_PROG, "rule": "an upgrade was executed: x", "target": HELD_PROG, "title": "t3"}]})
        self.put("warning_ledger.json", {"entries": {"solana:%s:%s" % (HELD_MS.lower(), H_ID1): {"outcome": "warned"}, "solana:%s:example:%s:2" % (OTHER_MS.lower(), OTHER_MS): {"outcome": "warned"}}})
        open(os.path.join(self.w, "digest.md"), "w").write("# digest\n- a line about %s\n- a line about %s\n- another one\n" % (HELD_NAME, OTHER_NAME))
        self.put("second_opinion.json", {"results": [{"target": HELD_PROG, "multisig": HELD_MS}]})   # who controls the program: stays
        self.env = {"WATCH_WITHHOLD": json.dumps({"addresses": [HELD_MS]}), "WATCH_WITHHOLD_PRIVATE": self.private, "PATH": os.environ.get("PATH", "")}

    def put(self, name, obj): json.dump(obj, open(os.path.join(self.w, name), "w"))
    def get(self, name): return json.load(open(os.path.join(self.w, name)))
    def text(self, name): return open(os.path.join(self.w, name)).read()
    def run_cli(self, cmd="retain", env=None, extra=()):
        e = dict(self.env if env is None else env); out = os.path.join(self.d, "gh_output"); e.setdefault("GITHUB_OUTPUT", out)
        return subprocess.run([sys.executable, "-I", SCRIPT, cmd, "--watch", self.w] + list(extra), capture_output=True, text=True, env=e), out
    def listed(self): return [r["address"] for r in self.get("pending_ops.json")["results"]]


class TestConfig(unittest.TestCase):
    def test_an_absent_or_blank_list_is_absent(self):
        self.assertEqual(W.parse(None), (None, "absent")); self.assertEqual(W.parse("  "), (None, "absent"))
    def test_a_list_that_is_not_json_is_invalid(self): self.assertEqual(W.parse("{not json"), (None, "invalid"))
    def test_a_list_that_is_not_an_object_is_invalid(self): self.assertEqual(W.parse('["a"]'), (None, "invalid"))
    def test_an_unknown_key_is_invalid_so_a_typo_cannot_hold_nothing_silently(self): self.assertEqual(W.parse('{"adress": ["a"]}'), (None, "invalid"))
    def test_an_unknown_level_is_invalid(self): self.assertEqual(W.parse('{"addresses": ["a"], "level": "show"}'), (None, "invalid"))
    def test_an_address_that_is_not_text_is_invalid(self): self.assertEqual(W.parse('{"addresses": [5]}'), (None, "invalid"))
    def test_categories_must_be_a_list(self): self.assertEqual(W.parse('{"categories": "famx"}'), (None, "invalid"))
    def test_a_valid_list_defaults_to_hide_and_lowercases(self):
        cfg, why = W.parse('{"categories": ["FamX"], "addresses": ["AbC"]}'); self.assertIsNone(why); self.assertEqual(cfg, {"categories": {"famx"}, "addresses": {"abc"}, "level": "hide"})
    def test_an_empty_object_is_valid_and_holds_nothing(self):
        cfg, why = W.parse("{}"); self.assertIsNone(why); self.assertFalse(any(W.holds(r, cfg) for r in (held_record(), other_record(), evm_record())))


class TestHolds(unittest.TestCase):
    def cfg(self, **k): return W.parse(json.dumps(k))[0]
    def test_by_the_queues_own_address(self): self.assertTrue(W.holds(held_record(), self.cfg(addresses=[HELD_MS])))
    def test_by_the_program_it_governs(self): self.assertTrue(W.holds(held_record(), self.cfg(addresses=[HELD_PROG])))
    def test_by_category(self): self.assertTrue(W.holds(held_record(), self.cfg(categories=["famx"])) and W.holds(other_record(), self.cfg(categories=["famx"])))
    def test_the_case_of_an_address_does_not_matter(self): self.assertTrue(W.holds(evm_record(), self.cfg(addresses=[TL.upper()])))
    def test_another_queue_is_not_held_by_an_address_that_is_not_its_own(self): self.assertFalse(W.holds(other_record(), self.cfg(addresses=[HELD_MS])))
    def test_a_category_does_not_reach_another_family(self): self.assertFalse(W.holds(evm_record(), self.cfg(categories=["famx"])))


class TestRetainDoc(Base):
    def doc(self): return self.get("pending_ops.json")
    def test_hide_removes_the_held_queue_and_keeps_the_others_in_order(self):
        d = self.doc(); held = W.retain_doc(d, W.parse(self.env["WATCH_WITHHOLD"])[0])
        self.assertEqual([r["address"] for r in d["results"]], [OTHER_MS, TL]); self.assertEqual([r["address"] for r in held], [HELD_MS])
    def test_hide_leaves_the_other_queues_untouched(self):
        d = self.doc(); W.retain_doc(d, W.parse(self.env["WATCH_WITHHOLD"])[0]); self.assertEqual(d["results"][0], other_record())
    def test_hide_returns_the_full_record_for_the_private_watch(self):
        d = self.doc(); held = W.retain_doc(d, W.parse(self.env["WATCH_WITHHOLD"])[0]); self.assertEqual(held[0], held_record())
    def test_count_keeps_identity_and_the_exact_number_and_nothing_else(self):
        d = self.doc(); W.retain_doc(d, W.parse(json.dumps({"addresses": [HELD_MS], "level": "count"}))[0]); r = d["results"][0]
        self.assertEqual(r["address"], HELD_MS); self.assertEqual(r["pending_count"], 2); self.assertTrue(r["detail_withheld"]); self.assertEqual(r["pending"], [])
        for k in ("recent", "active", "proposals", "queued_events", "latest_queued", "transaction_index"): self.assertNotIn(k, r)
    def test_count_of_a_queue_that_was_not_read_is_unknown_not_zero(self):
        d = self.doc(); d["results"][0]["status"] = "UNREAD (multisig account or proposals not answered)"; d["results"][0]["pending"] = []
        W.retain_doc(d, W.parse(json.dumps({"addresses": [HELD_MS], "level": "count"}))[0]); self.assertIsNone(d["results"][0]["pending_count"])
    def test_count_drops_a_field_added_later(self):
        d = self.doc(); d["results"][0]["new_detail"] = {"who": HELD_ACCOUNT_LIKE}; W.retain_doc(d, W.parse(json.dumps({"addresses": [HELD_MS], "level": "count"}))[0]); self.assertNotIn("new_detail", d["results"][0])
    def test_a_second_pass_keeps_the_count(self):
        d = self.doc(); cfg = W.parse(json.dumps({"addresses": [HELD_MS], "level": "count"}))[0]; W.retain_doc(d, cfg); W.retain_doc(d, cfg); self.assertEqual(d["results"][0]["pending_count"], 2)
    def test_the_other_queues_count_is_not_touched_by_a_count_level_on_the_held_one(self):
        d = self.doc(); W.retain_doc(d, W.parse(json.dumps({"addresses": [HELD_MS], "level": "count"}))[0]); self.assertEqual(len(d["results"][1]["pending"]), 1); self.assertNotIn("pending_count", d["results"][1])


HELD_ACCOUNT_LIKE = "HeldAccount9QQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQ"


class TestCli(Base):
    def test_with_the_list_absent_the_files_are_unchanged(self):
        before = self.text("pending_ops.json"); r, _ = self.run_cli(env={"PATH": os.environ.get("PATH", "")}); self.assertEqual(r.returncode, 0); self.assertEqual(self.text("pending_ops.json"), before)
    def test_with_the_list_absent_and_not_expected_nothing_is_said(self):
        r, out = self.run_cli(env={"PATH": os.environ.get("PATH", "")}); self.assertFalse(os.path.exists(os.path.join(self.w, "run.log"))); self.assertFalse(os.path.exists(out))
    def test_with_the_list_absent_where_it_is_expected_one_private_alarm_line_names_nobody(self):
        r, out = self.run_cli(env={"PATH": os.environ.get("PATH", ""), "WATCH_WITHHOLD_REQUIRED": "1"}); log = self.text("run.log")
        self.assertTrue(log.startswith("ALARM withhold")); self.assertEqual(log.count("\n"), 1); self.assertIn("alarm=1", open(out).read())
        for s in (HELD_MS, HELD_PROG, OTHER_MS): self.assertNotIn(s, log)
    def test_a_malformed_list_changes_nothing_and_raises_the_alarm_even_in_a_fork(self):
        before = self.text("pending_ops.json"); env = dict(self.env, WATCH_WITHHOLD='{"addresses": ["' + HELD_MS)
        r, out = self.run_cli(env=env); self.assertEqual(r.returncode, 0); self.assertEqual(self.text("pending_ops.json"), before)
        self.assertIn("ALARM withhold", self.text("run.log")); self.assertNotIn(HELD_MS, self.text("run.log")); self.assertIn("alarm=1", open(out).read())
    def test_a_valid_list_takes_the_held_queue_out_of_pending_ops(self):
        r, out = self.run_cli(); self.assertEqual(r.returncode, 0); self.assertEqual(self.listed(), [OTHER_MS, TL]); self.assertFalse(os.path.exists(out))
    def test_the_other_queues_and_the_top_level_fields_are_kept(self):
        self.run_cli(); d = self.get("pending_ops.json"); self.assertEqual(d["results"][0], other_record()); self.assertEqual((d["days"], d["discovered"]), (90, 15))
    def test_stdout_and_stderr_are_empty_and_hold_no_address(self):
        r, _ = self.run_cli(); self.assertEqual((r.stdout, r.stderr), ("", ""))
    def test_a_crash_with_a_list_present_prints_nothing_and_fails_closed(self):
        r, _ = self.run_cli(env=dict(self.env, WATCH_WITHHOLD_PRIVATE=self.d)); self.assertEqual(r.returncode, 2); self.assertEqual((r.stdout, r.stderr), ("", ""))
        self.assertIn(HELD_MS, self.text("pending_ops.json"))   # nothing was half written: the job stops and records nothing
    def test_the_private_file_holds_the_full_record_and_is_not_readable_by_others(self):
        self.run_cli(); self.assertEqual([{k: v for k, v in r.items() if k != "_targeted"} for r in json.load(open(self.private))["queues"]], [held_record()]); self.assertEqual(stat.S_IMODE(os.stat(self.private).st_mode), 0o600)
    def test_the_private_file_keeps_a_queue_held_by_an_earlier_pass(self):
        self.run_cli(); self.run_cli(); self.assertEqual([r["address"] for r in json.load(open(self.private))["queues"]], [HELD_MS])
    def test_the_private_file_is_never_under_the_published_folder_by_default(self):
        self.run_cli(); self.assertFalse(any(n == "held.json" for _, _, ns in os.walk(self.w) for n in ns))
    def test_the_alert_history_forgets_the_queue_and_upgrade_rules_of_the_held_program_only(self):
        self.run_cli(); h = self.get("alerts.json")["history"]; self.assertEqual([x["target"] for x in h], [OTHER_PROG])   # the rule about an executed upgrade of the governed program goes too
    def test_the_ledger_forgets_the_held_operations_only(self):
        self.run_cli(); e = self.get("warning_ledger.json")["entries"]; self.assertEqual(len(e), 1); self.assertIn(OTHER_MS, list(e)[0])
    def test_the_digest_loses_the_lines_about_the_held_queue_only(self):
        self.run_cli(); t = self.text("digest.md"); self.assertNotIn(W.short(HELD_MS), t); self.assertIn(W.short(OTHER_MS), t); self.assertIn("another one", t)
    def test_a_second_run_changes_nothing_more(self):
        self.run_cli(); a = {n: self.text(n) for n in os.listdir(self.w)}; self.run_cli(); self.assertEqual(a, {n: self.text(n) for n in os.listdir(self.w)})
    def test_the_authority_files_are_not_touched(self):
        before = self.text("second_opinion.json"); self.run_cli(); self.assertEqual(self.text("second_opinion.json"), before)
    def test_a_category_holds_every_queue_of_the_family_at_once(self):
        self.run_cli(env=dict(self.env, WATCH_WITHHOLD='{"categories": ["famx"]}')); self.assertEqual(self.listed(), [TL])
    def test_leaving_one_queue_out_never_reaches_another_queue(self):
        self.run_cli(env=dict(self.env, WATCH_WITHHOLD=json.dumps({"addresses": [OTHER_MS]}))); self.assertEqual(self.listed(), [HELD_MS, TL])
        self.assertEqual(len(self.get("pending_ops.json")["results"][0]["pending"]), 2)
    def test_the_warning_ledger_counts_without_the_held_queue(self):
        import warning_ledger as L
        self.run_cli(); led = L.update({"started_utc": "2026-10-12T00:00:00Z", "entries": {}}, self.get("pending_ops.json"), 1792000000)
        self.assertTrue(led["entries"]); self.assertFalse(any(HELD_MS.lower() in k or H_ID1 in k for k in led["entries"]))


class TestCheck(Base):
    def retained(self): self.run_cli(); return self.run_cli("check")[0]
    def test_a_retained_tree_passes(self): self.assertEqual(self.retained().returncode, 0)
    def test_a_leak_through_alerts_json_is_found(self):
        self.run_cli(); self.put("alerts.json", {"active": [{"evidence": [{"id": H_ID1}]}], "history": []}); r = self.run_cli("check")[0]
        self.assertEqual(r.returncode, 1); self.assertIn("alerts.json", r.stderr)
    def test_a_leak_through_moves_json_by_an_account_is_found(self):
        self.run_cli(); self.put("moves.json", {"x": H_ACCT}); self.assertEqual(self.run_cli("check")[0].returncode, 1)
    def test_a_leak_of_the_name_in_a_feed_is_found(self):
        self.run_cli(); os.makedirs(os.path.join(self.w, "feed")); open(os.path.join(self.w, "feed", "a.xml"), "w").write("<entry>%s</entry>" % HELD_NAME); self.assertEqual(self.run_cli("check")[0].returncode, 1)
    def test_a_leak_of_the_address_in_a_review_page_is_found(self):
        self.run_cli(); open(os.path.join(self.w, "review_queue.md"), "w").write("- queued %s" % HELD_MS); self.assertEqual(self.run_cli("check")[0].returncode, 1)
    def test_the_multisig_named_as_the_control_of_a_program_is_not_a_leak_of_its_queue(self):
        self.run_cli(); self.put("example_vaults.json", {"vault": HELD_MS}); self.assertEqual(self.run_cli("check")[0].returncode, 0)
    def test_at_level_count_the_record_in_pending_ops_is_allowed_and_the_detail_is_not(self):
        env = dict(self.env, WATCH_WITHHOLD=json.dumps({"addresses": [HELD_MS], "level": "count"})); self.run_cli(env=env); self.assertEqual(self.run_cli("check", env=env)[0].returncode, 0)
        self.put("alerts.json", {"x": H_ID2}); self.assertEqual(self.run_cli("check", env=env)[0].returncode, 1)
    def test_at_level_hide_the_record_in_pending_ops_would_be_a_leak(self):
        self.run_cli(); self.put("pending_ops.json", {"results": [held_record()]}); self.assertEqual(self.run_cli("check")[0].returncode, 1)
    def test_the_failure_message_names_files_never_the_string(self):
        self.run_cli(); self.put("alerts.json", {"x": H_ID1, "y": HELD_MS}); r = self.run_cli("check")[0]
        for s in (H_ID1, HELD_MS, HELD_PROG, H_ACCT, HELD_NAME): self.assertNotIn(s, r.stdout + r.stderr)
    def test_without_a_private_file_the_check_has_nothing_to_look_for(self):
        self.run_cli(); os.remove(self.private); self.put("alerts.json", {"x": H_ACCT}); self.assertEqual(self.run_cli("check")[0].returncode, 0)




# ---- revision 2: registry addresses, the event log, the per-run fields, the strict check ----
import hashlib  # noqa: E402
import verify_chain  # noqa: E402

HELD_VAULT, HELD_BUFFER = "HeldVaultPdaIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIII8", "HeldBufferJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJ9"


def chain_append(path, records):
    """The writers' link rule: seq + 1, prev = sha256 of the previous line's exact text."""
    last = ""
    if os.path.exists(path):
        ls = [l for l in open(path).read().split("\n") if l.strip()]; last = ls[-1] if ls else ""
    seq = json.loads(last).get("seq", 0) if last else 0; prev = hashlib.sha256(last.encode()).hexdigest() if last else ""
    with open(path, "a") as f:
        for r in records:
            seq += 1; line = json.dumps({**r, "seq": seq, "prev": prev}); f.write(line + "\n"); prev = hashlib.sha256(line.encode()).hexdigest()
    return prev


def ev(kind, target, text="x", **k): return dict({"run_utc": "2026-11-09T06:00:00Z", "kind": kind, "oracle": "solana", "target": target, "text": text}, **k)


class EventsBase(Base):
    """Events are appended by the writers before the queue step; the lines of THIS run that name a held queue are taken out before anything is committed."""
    def setUp(self):
        super().setUp(); self.ev = os.path.join(self.w, "events.jsonl")
        self.put("scores_solana.json", {})
        os.makedirs(os.path.join(self.w, "scores")); json.dump({"targets": [{"target": HELD_PROG}, {"target": OTHER_PROG}]}, open(os.path.join(self.w, "scores", "solana.json"), "w"))
        head = chain_append(self.ev, [ev("move", OTHER_PROG), ev("move", HELD_PROG)]); self.sign(head); self.old = open(self.ev).read()
        self.new_lines = [ev("move", OTHER_PROG, "a"), ev("upgraded", HELD_PROG, "upgrade executed"), ev("admin_change", HELD_PROG, "admin read changed: example %s 3-of-5 -> 2-of-5" % W.short(HELD_MS)),
                          ev("move", HELD_PROG, "score moved"), ev("upgraded", OTHER_PROG, "another program"), ev("alarm", None, "an alarm")]
    def sign(self, head): self.put("signature.json", {"manifest": {"events_chain_head": head}})
    def lines(self): return [json.loads(l) for l in open(self.ev).read().split("\n") if l.strip()]
    def append(self, recs=None): chain_append(self.ev, recs or self.new_lines)


class TestEvents(EventsBase):
    def test_an_upgrade_of_a_governed_program_is_not_written(self):
        self.append(); self.run_cli(); self.assertEqual([e["text"] for e in self.lines()[2:]], ["a", "score moved", "another program", "an alarm"])
    def test_a_line_that_names_the_multisig_in_short_form_is_not_written(self):
        self.append(); self.run_cli(); self.assertFalse(any("admin read changed" in e["text"] for e in self.lines()))
    def test_the_score_move_of_the_held_program_stays(self):
        self.append(); self.run_cli(); self.assertIn("score moved", [e["text"] for e in self.lines()])
    def test_the_lines_of_earlier_runs_are_byte_for_byte_unchanged(self):
        self.append(); self.run_cli(); self.assertTrue(open(self.ev).read().startswith(self.old))
    def test_the_chain_verifies_and_the_sequence_has_no_gap(self):
        self.append(); self.run_cli(); r = verify_chain.check(self.ev); self.assertTrue(r["ok"]); self.assertEqual([e["seq"] for e in self.lines()], list(range(1, len(self.lines()) + 1)))
    def test_the_head_of_the_previous_signature_is_still_a_line_of_the_log(self):
        self.append(); self.run_cli(); ls = [l for l in open(self.ev).read().split("\n") if l.strip()]
        self.assertIn(self.get("signature.json")["manifest"]["events_chain_head"], [hashlib.sha256(l.encode()).hexdigest() for l in ls])
    def test_with_nothing_to_drop_the_file_is_not_rewritten(self):
        self.append([ev("move", OTHER_PROG)]); before = open(self.ev).read(); self.run_cli(); self.assertEqual(open(self.ev).read(), before)
    def test_without_a_known_head_the_run_stops_with_the_log_untouched_and_the_private_alarm_says_so(self):
        self.append(); os.remove(os.path.join(self.w, "signature.json")); before = open(self.ev).read(); r, out = self.run_cli()
        self.assertEqual(r.returncode, 2); self.assertEqual(open(self.ev).read(), before); self.assertIn("ALARM withhold stopped the run", self.text("run.log")); self.assertNotIn(HELD_MS, self.text("run.log")); self.assertIn("alarm=1", open(out).read())
    def test_the_dropped_lines_are_kept_for_the_private_watch(self):
        self.append(); self.run_cli(); ev_ = json.load(open(self.private))["events"]; self.assertEqual(len(ev_), 2); self.assertTrue(any("upgrade executed" in l for l in ev_))
    def test_a_registry_address_that_is_not_in_any_record_still_drops_the_lines_that_name_it(self):
        self.append([ev("admin_change", OTHER_PROG, "buffer %s written" % HELD_BUFFER)]); env = dict(self.env, WATCH_WITHHOLD=json.dumps({"addresses": [HELD_MS, HELD_BUFFER]}))
        self.run_cli(env=env); self.assertFalse(any(HELD_BUFFER in e["text"] for e in self.lines()))
    def test_a_scored_program_in_the_registry_keeps_its_score_lines_and_loses_its_upgrades(self):
        self.append(); env = dict(self.env, WATCH_WITHHOLD=json.dumps({"addresses": [HELD_PROG]})); self.run_cli(env=env)
        t = [e["text"] for e in self.lines()[2:]]; self.assertIn("score moved", t); self.assertNotIn("upgrade executed", t)
    def test_activated_in_the_middle_of_the_chain_then_several_passes_the_chain_never_breaks(self):
        self.append([ev("upgraded", HELD_PROG, "before the list existed")]); self.sign(verify_chain.check(self.ev)["head"]); no_list = {"PATH": os.environ.get("PATH", "")}
        for n in range(4):   # four passes with the list on: each appends, the step drops, the run signs, the next run starts from that signature
            self.append([ev("move", OTHER_PROG, "pass %d" % n), ev("upgraded", HELD_PROG, "held %d" % n)]); self.run_cli(); r = verify_chain.check(self.ev); self.assertTrue(r["ok"], r); self.sign(r["head"])
        t = [e["text"] for e in self.lines()]; self.assertIn("before the list existed", t); self.assertEqual([x for x in t if x.startswith("held")], []); self.assertEqual([x for x in t if x.startswith("pass")], ["pass %d" % n for n in range(4)])
        self.assertEqual([e["seq"] for e in self.lines()], list(range(1, len(t) + 1)))
    def test_the_check_ignores_a_line_of_an_earlier_run_that_names_the_multisig(self):
        chain_append(self.ev, [ev("admin_change", HELD_PROG, "example %s" % W.short(HELD_MS))]); self.sign(verify_chain.check(self.ev)["head"]); self.append([ev("move", OTHER_PROG)])
        self.run_cli(); self.assertEqual(self.run_cli("check")[0].returncode, 0)
    def test_the_check_refuses_a_new_line_that_names_the_multisig(self):
        self.run_cli(); self.append([ev("admin_change", HELD_PROG, "example %s" % W.short(HELD_MS))]); self.assertEqual(self.run_cli("check")[0].returncode, 1)
    def test_the_per_run_fields_of_the_governed_program_are_taken_out_of_the_independent_reader(self):
        self.put("second_opinion.json", {"results": [{"chain": "solana", "target": HELD_PROG, "multisig": HELD_MS, "upgraded": "redeployed", "changed": "admin read changed"},
                                                      {"chain": "solana", "target": OTHER_PROG, "upgraded": "another"}], "upgrades": [{"target": HELD_PROG}, {"target": OTHER_PROG}], "changed": [{"target": HELD_PROG}]})
        self.run_cli(); d = self.get("second_opinion.json"); r = d["results"]
        self.assertNotIn("upgraded", r[0]); self.assertNotIn("changed", r[0]); self.assertEqual(r[0]["multisig"], HELD_MS); self.assertEqual(r[1]["upgraded"], "another")
        self.assertEqual(d["upgrades"], [{"target": OTHER_PROG}]); self.assertEqual(d["changed"], [])
        self.assertEqual(json.load(open(self.private))["reads"][0]["upgraded"], "redeployed")
    def test_an_alert_rule_about_an_executed_upgrade_leaves_the_history_of_the_governed_program(self):
        rule = "an upgrade was executed: the implementation behind this contract changed"; d = self.get("alerts.json")
        d["history"] += [{"key": "k", "rule": rule, "target": HELD_PROG}, {"key": "k2", "rule": rule, "target": OTHER_PROG}]; self.put("alerts.json", d); self.run_cli()
        self.assertEqual([h["target"] for h in self.get("alerts.json")["history"] if h["rule"] == rule], [OTHER_PROG])


class TestRegistryAddresses(Base):
    """Every address of the list is a criterion: the queue that names it anywhere is left out, whatever field it sits in."""
    def other_with(self, field, value):
        r = other_record()
        if field in ("governs",): r["governs"] = [value]
        elif field in ("target", "signature", "account", "id"): r["pending"][0][field] = value if field != "signature" else "Example proposal #2: Upgrade of buffer %s" % value
        elif field == "name": r["name"] = "multisig %s" % value
        elif field == "what": r["pending"][0]["what"] = "Write to %s" % value
        elif field == "touches_governed": r["pending"][0]["touches_governed"] = value
        self.put("pending_ops.json", {"results": [held_record(), r, evm_record()]}); return r
    def held_by(self, field):
        self.other_with(field, HELD_BUFFER); self.run_cli(env=dict(self.env, WATCH_WITHHOLD=json.dumps({"addresses": [HELD_BUFFER]}))); return self.listed()
    def test_a_queue_naming_the_address_in_governs_is_held(self): self.assertNotIn(OTHER_MS, self.held_by("governs"))
    def test_a_queue_naming_the_address_in_target_is_held(self): self.assertNotIn(OTHER_MS, self.held_by("target"))
    def test_a_queue_naming_the_address_in_signature_is_held(self): self.assertNotIn(OTHER_MS, self.held_by("signature"))
    def test_a_queue_naming_the_address_in_account_is_held(self): self.assertNotIn(OTHER_MS, self.held_by("account"))
    def test_a_queue_naming_the_address_in_name_is_held(self): self.assertNotIn(OTHER_MS, self.held_by("name"))
    def test_a_queue_naming_the_address_in_what_is_held(self): self.assertNotIn(OTHER_MS, self.held_by("what"))
    def test_a_queue_that_does_not_name_it_is_not_held(self): self.put("pending_ops.json", {"results": [other_record()]}); self.run_cli(env=dict(self.env, WATCH_WITHHOLD=json.dumps({"addresses": [HELD_BUFFER]}))); self.assertEqual(self.listed(), [OTHER_MS])
    def test_a_vault_address_holds_the_queue_that_names_it(self):
        r = held_record(); r["pending"][0]["what"] = "vault %s" % HELD_VAULT; self.put("pending_ops.json", {"results": [r, other_record()]})
        self.run_cli(env=dict(self.env, WATCH_WITHHOLD=json.dumps({"addresses": [HELD_VAULT]}))); self.assertEqual(self.listed(), [OTHER_MS])
    def test_too_short_a_term_is_never_matched_inside_text(self):
        self.run_cli(env=dict(self.env, WATCH_WITHHOLD=json.dumps({"addresses": ["Example"]}))); self.assertEqual(len(self.listed()), 3)


class TestStrictCheck(Base):
    """A registry address in ANY published file is a leak, whichever field carried it (the strict mode); the default mode keeps to the queue files so a known entry never stops the Watch."""
    def setUp(self):
        super().setUp(); self.env["WATCH_WITHHOLD"] = json.dumps({"addresses": [HELD_MS, HELD_BUFFER]}); self.run_cli()
    def strict(self): return self.run_cli("check", extra=("--strict",))[0]
    def test_a_clean_tree_passes_the_strict_check_except_the_structure_files(self):
        r = self.strict(); self.assertEqual(r.returncode, 1); self.assertIn("second_opinion.json", r.stderr)   # the multisig is named there as the control of a program
        os.remove(os.path.join(self.w, "second_opinion.json")); self.assertEqual(self.strict().returncode, 0)
    def test_every_unexpected_field_is_caught_in_pending_ops(self):
        for field in ("signature", "name", "what", "touches_governed", "governs", "account", "target"):
            self.put("pending_ops.json", {"results": [{"address": "X", field: HELD_BUFFER}]}); self.assertEqual(self.run_cli("check")[0].returncode, 1, field)
    def test_every_published_file_class_is_caught_in_strict_mode(self):
        os.remove(os.path.join(self.w, "second_opinion.json")); os.makedirs(os.path.join(self.w, "feed")); os.makedirs(os.path.join(self.w, "badge"))
        for name in ("moves.json", "latest.json", "status.json", "coverage.json", "trust.json", "badge/a.json", "feed/a.xml", "metrics.prom", "catalog.json"):
            p = os.path.join(self.w, name); open(p, "w").write("x %s x" % HELD_BUFFER); self.assertEqual(self.strict().returncode, 1, name); os.remove(p)
    def test_the_default_mode_does_not_stop_the_watch_for_a_controller_named_in_a_structure_file(self): self.assertEqual(self.run_cli("check")[0].returncode, 0)
    def test_a_registry_address_that_is_a_scored_target_is_not_a_leak_in_the_score_files(self):
        os.makedirs(os.path.join(self.w, "scores")); json.dump({"targets": [{"target": HELD_PROG}]}, open(os.path.join(self.w, "scores", "s.json"), "w"))
        env = dict(self.env, WATCH_WITHHOLD=json.dumps({"addresses": [HELD_PROG]})); self.run_cli(env=env); os.remove(os.path.join(self.w, "second_opinion.json"))
        self.assertEqual(self.run_cli("check", env=env, extra=("--strict",))[0].returncode, 0)
    def test_a_queue_held_by_category_has_its_controller_flagged_in_strict_mode_by_its_record(self):
        env = dict(self.env, WATCH_WITHHOLD='{"categories": ["famx"]}'); self.run_cli(env=env); r = self.run_cli("check", env=env, extra=("--strict",))[0]
        self.assertEqual(r.returncode, 1); self.assertIn("second_opinion.json", r.stderr); self.assertEqual(self.run_cli("check", env=env)[0].returncode, 0)
    def test_the_short_form_in_a_json_file_written_with_escapes_is_caught(self):
        json.dump({"title": "x %s y" % W.short(HELD_BUFFER)}, open(os.path.join(self.w, "alerts.json"), "w")); self.assertIn("\\u2026", self.text("alerts.json")); self.assertEqual(self.run_cli("check")[0].returncode, 1)
    def test_the_short_form_of_a_registry_address_is_caught_too(self):
        open(os.path.join(self.w, "alerts.xml"), "w").write("<entry>%s</entry>" % W.short(HELD_BUFFER)); self.assertEqual(self.run_cli("check")[0].returncode, 1)


class TestViews(Base):
    """The feeds are views of the whole event log: the entries that name a held string leave them, the others stay."""
    def feed(self, *entries): os.makedirs(os.path.join(self.w, "feed"), exist_ok=True); open(os.path.join(self.w, "feed", "a.xml"), "w").write("<feed>" + "".join("<entry><title>%s</title></entry>" % e for e in entries) + "</feed>")
    def test_an_entry_that_names_the_multisig_leaves_the_feed(self):
        self.feed("example %s changed" % W.short(HELD_MS), "a score move"); self.run_cli(); self.run_cli("views"); t = self.text("feed/a.xml"); self.assertNotIn(W.short(HELD_MS), t); self.assertIn("a score move", t)
    def test_an_entry_that_names_an_operation_leaves_the_feed(self):
        self.feed(H_SIG, "kept"); self.run_cli(); self.run_cli("views"); self.assertNotIn("Example proposal #41", self.text("feed/a.xml")); self.assertIn("kept", self.text("feed/a.xml"))
    def test_the_global_feed_and_the_alert_feed_are_cleaned_too(self):
        for n in ("feed.xml", "alerts.xml"): open(os.path.join(self.w, n), "w").write("<feed><entry>%s</entry><entry>ok</entry></feed>" % HELD_MS)
        self.run_cli(); self.run_cli("views"); self.assertEqual(self.text("feed.xml"), "<feed><entry>ok</entry></feed>"); self.assertEqual(self.text("alerts.xml"), "<feed><entry>ok</entry></feed>")
    def test_a_feed_with_nothing_held_is_not_rewritten(self):
        self.feed("one", "two"); before = self.text("feed/a.xml"); self.run_cli(); self.run_cli("views"); self.assertEqual(self.text("feed/a.xml"), before)
    def test_without_a_list_or_a_private_file_nothing_is_touched(self):
        self.feed("example %s" % W.short(HELD_MS)); before = self.text("feed/a.xml"); r, _ = self.run_cli("views", env={"PATH": os.environ.get("PATH", "")}); self.assertEqual((r.returncode, self.text("feed/a.xml")), (0, before))
    def test_the_check_then_passes_on_a_feed_that_carried_history_naming_the_multisig(self):
        self.feed("example %s history" % W.short(HELD_MS)); self.run_cli(); self.assertEqual(self.run_cli("check")[0].returncode, 1); self.run_cli("views"); self.assertEqual(self.run_cli("check")[0].returncode, 0)
    def test_a_feed_that_cannot_be_read_stops_the_job_rather_than_publish(self):
        self.run_cli(); os.makedirs(os.path.join(self.w, "feed")); open(os.path.join(self.w, "feed", "a.xml"), "wb").write(b"\xff\xfe<entry>")
        r, _ = self.run_cli("views"); self.assertEqual((r.returncode, r.stdout, r.stderr), (2, "", ""))
    def test_a_scored_program_in_the_registry_keeps_its_own_feed_entries(self):
        os.makedirs(os.path.join(self.w, "scores")); json.dump({"targets": [{"target": HELD_PROG}]}, open(os.path.join(self.w, "scores", "s.json"), "w")); self.feed("score move of %s" % HELD_PROG)
        env = dict(self.env, WATCH_WITHHOLD=json.dumps({"addresses": [HELD_PROG]})); self.run_cli(env=env); self.run_cli("views", env=env); self.assertIn(HELD_PROG, self.text("feed/a.xml"))


# ---- revision 3: neutral texts, the whole family, fail closed, the markdown reader's page, the record, the paper trail ----
ROOT = os.path.join(SCRIPTS, "..")
WORDS = re.compile(r"disclos|embargo|promis|window|team|confidential|held back|held-back|under (an? )?agreement", re.I)


class TestPublicTexts(unittest.TestCase):
    """The texts a reader sees must say what is true and nothing about why: no word about a disclosure, an embargo, a promise, a window or a team."""
    def read(self, *p): return open(os.path.join(ROOT, *p), encoding="utf-8").read()
    def test_the_module_text_is_neutral(self): self.assertIsNone(WORDS.search(W.__doc__))
    def test_every_message_of_the_module_is_neutral(self): self.assertEqual([n for n in dir(W) if n.isupper() and isinstance(getattr(W, n), str) and WORDS.search(getattr(W, n))], [])
    def test_the_changelog_line_is_neutral(self):
        l = [x for x in self.read("CHANGELOG.md").split("\n") if "withhold.py" in x]; self.assertEqual(len(l), 1); self.assertIsNone(WORDS.search(l[0]))
    def test_the_methodology_paragraph_is_neutral(self):
        l = [x for x in self.read("METHODOLOGY.md").split("\n") if x.startswith("**Public view.**")]; self.assertEqual(len(l), 1); self.assertIsNone(WORDS.search(l[0]))
    def test_the_api_row_is_neutral(self):
        l = [x for x in self.read("watch", "API.md").split("\n") if "(public view)" in x]; self.assertEqual(len(l), 1); self.assertIsNone(WORDS.search(l[0]))
    def test_every_step_of_the_workflow_that_runs_it_is_neutral(self):
        steps = [s for s in self.read(".github", "workflows", "watch.yml").split("\n      - name:") if "withhold" in s.lower() or "public view" in s.lower()]
        self.assertGreaterEqual(len(steps), 4); self.assertEqual([s[:60] for s in steps if WORDS.search(s)], [])
    def test_the_schema_entries_are_neutral(self): self.assertIsNone(WORDS.search(json.dumps({k: v for k, v in json.load(open(os.path.join(ROOT, "watch", "schema", "pending_ops.schema.json")))["properties"].items() if k == "not_shown"})))
    def test_the_commit_message_when_the_checkout_has_history_is_neutral(self):
        m = introducing_message(ROOT, "scripts/withhold.py")
        if m is None: self.skipTest("the checkout is shallow or has no history: the commit that added the file is not known")
        self.assertIsNone(WORDS.search(m))


def introducing_message(root, path):
    """The message of the commit that added `path`, not of the last commit that touched it (later commits are about other things). None when the checkout is shallow: its oldest commit would be read as the
    one that added every file. None too when there is no history."""
    def git(*a): return subprocess.run(["git", *a], cwd=root, capture_output=True, text=True)
    if git("rev-parse", "--is-shallow-repository").stdout.strip() != "false": return None
    r = git("log", "--diff-filter=A", "--format=%B", "--", path)
    return r.stdout if r.returncode == 0 and r.stdout.strip() else None


STEMS = [w for w in WORDS.pattern.split("|") if w.isalpha()]; BAD = STEMS[0]   # the words of the list above, taken from it: a message with one of them is not neutral


class TestIntroducingMessage(unittest.TestCase):
    """The lookup above, on repositories made here: the commit that added the file is read, a later one is not, and a shallow clone is not guessed."""
    def setUp(self):
        self.d = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, self.d, True); self.r = os.path.join(self.d, "r"); os.makedirs(os.path.join(self.r, "scripts"))
        self.git("init", "-q", "-b", "main")

    def git(self, *a, cwd=None): return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *a], cwd=cwd or self.r, capture_output=True, text=True, check=True)
    def commit(self, text, message, name="withhold.py"):
        open(os.path.join(self.r, "scripts", name), "w").write(text); self.git("add", "-A"); self.git("commit", "-q", "-m", message)

    def test_the_commit_that_added_the_file_is_read_and_a_later_one_is_not(self):
        self.commit("a", "Add the module"); self.commit("b", "Change the cadence, %s" % BAD); self.assertEqual(introducing_message(self.r, "scripts/withhold.py").strip(), "Add the module")

    def test_a_message_of_the_commit_that_added_the_file_with_one_of_the_words_is_found(self):
        for w in STEMS:
            with self.subTest(word=w): self.commit(w, "Add the module, %s" % w, name="m_%s.py" % w.replace(" ", "_")); self.assertIsNotNone(WORDS.search(introducing_message(self.r, "scripts/m_%s.py" % w.replace(" ", "_"))))

    def test_a_file_added_by_another_commit_than_the_last_one_is_read_by_its_own_commit(self):
        self.commit("a", "Add the module"); self.commit("b", "Add another file", name="other.py"); self.assertEqual(introducing_message(self.r, "scripts/withhold.py").strip(), "Add the module")

    def test_a_shallow_checkout_is_not_guessed(self):
        self.commit("a", "Add the module"); self.commit("b", "Change the cadence, %s" % BAD); c = os.path.join(self.d, "c")
        self.git("clone", "-q", "--depth", "1", "file://" + self.r, c, cwd=self.d); self.assertIsNone(introducing_message(c, "scripts/withhold.py"))

    def test_the_list_of_words_is_not_emptied(self): self.assertGreaterEqual(len(STEMS), 6)

    def outcome(self, root):
        """(failures, errors, skips) of the test of the repository, run with `root` as the repository."""
        from unittest import mock
        res = unittest.TestResult()
        with mock.patch.object(sys.modules[__name__], "ROOT", root): TestPublicTexts("test_the_commit_message_when_the_checkout_has_history_is_neutral").run(res)
        return len(res.failures), len(res.errors), len(res.skipped)

    def test_the_test_of_the_repository_passes_when_the_adding_commit_is_neutral_whatever_comes_after(self):
        self.commit("a", "Add the module"); self.commit("b", "Change the cadence, %s" % BAD); self.assertEqual(self.outcome(self.r), (0, 0, 0))

    def test_the_test_of_the_repository_fails_when_the_adding_commit_is_not_neutral(self): self.commit("a", "Add the module, %s" % BAD); self.assertEqual(self.outcome(self.r), (1, 0, 0))

    def test_the_test_of_the_repository_is_skipped_on_a_shallow_checkout(self):
        self.commit("a", "Add the module, %s" % BAD); self.commit("b", "Change the cadence"); c = os.path.join(self.d, "c")
        self.git("clone", "-q", "--depth", "1", "file://" + self.r, c, cwd=self.d); self.assertEqual(self.outcome(c), (0, 0, 1))

    def test_the_test_of_the_repository_is_skipped_without_a_repository(self): self.assertEqual(self.outcome(self.d), (0, 0, 1))
    def test_a_folder_that_is_not_a_repository_has_no_message(self): self.assertIsNone(introducing_message(self.d, "scripts/withhold.py"))
    def test_a_file_that_was_never_added_has_no_message(self): self.commit("a", "Add the module"); self.assertIsNone(introducing_message(self.r, "scripts/none.py"))


class TestPublicView(Base):
    """The whole family is left out at once, and no file says 0 where it means not shown."""
    def setUp(self):
        super().setUp(); self.env["WATCH_WITHHOLD"] = json.dumps({"categories": ["famx"]})
        self.put("coverage.json", {"chains": {"solana": {"timelock_queues_watched": 2, "blind_spots": ["a gap"]}, "ethereum": {"timelock_queues_watched": 1, "blind_spots": []}}})
        self.put("risk_by_cause.json", {"causes": {"upgrade_executable": {"contracts": 0}, "no_delay": {"contracts": 3}}}); self.put("latest.json", {"run_utc": "R1"})
        open(os.path.join(self.w, "trend.jsonl"), "w").write(json.dumps({"run_utc": "R0", "a": 1}) + "\n" + json.dumps({"run_utc": "R1", "a": 2}) + "\n")
    def views(self, env=None): self.run_cli(env=env); return self.run_cli("views", env=env)[0]
    def test_every_queue_of_the_family_leaves_the_view_and_the_others_stay(self): self.run_cli(); self.assertEqual(self.listed(), [TL])
    def test_the_queue_file_says_which_family_is_not_shown(self): self.run_cli(); self.assertEqual(self.get("pending_ops.json")["not_shown"], ["famx"])
    def test_the_coverage_count_stays_a_number_counted_without_them_and_the_file_says_why(self):
        self.views(); s = self.get("coverage.json")["chains"]["solana"]; self.assertEqual(s["timelock_queues_watched"], 2); self.assertIn("not shown in the public view", s["blind_spots"][-1]); self.assertEqual(s["blind_spots"][0], "a gap")
    def test_the_other_chains_keep_their_count(self): self.views(); self.assertEqual(self.get("coverage.json")["chains"]["ethereum"]["timelock_queues_watched"], 1)
    def test_the_coverage_file_names_the_family(self): self.views(); self.assertEqual(self.get("coverage.json")["not_shown"], ["famx"])
    def test_the_risk_file_does_not_present_a_zero_as_a_measure(self):
        self.views(); d = self.get("risk_by_cause.json"); self.assertEqual(d["not_shown"], ["famx"]); self.assertEqual(d["causes"]["upgrade_executable"]["not_counted"], ["famx"]); self.assertNotIn("not_counted", d["causes"]["no_delay"])
    def test_the_alerts_file_names_the_family(self): self.views(); self.assertEqual(self.get("alerts.json")["not_shown"], ["famx"])
    def test_the_trend_line_of_this_run_is_marked_and_the_earlier_one_is_not(self):
        self.views(); l = [json.loads(x) for x in self.text("trend.jsonl").split("\n") if x.strip()]; self.assertEqual(l[1]["not_shown"], ["famx"]); self.assertNotIn("not_shown", l[0])
    def test_a_trend_line_of_another_run_is_never_rewritten(self):
        self.put("latest.json", {"run_utc": "R9"}); before = self.text("trend.jsonl"); self.views(); self.assertEqual(self.text("trend.jsonl"), before)
    def test_a_list_of_addresses_alone_marks_nothing(self):
        self.views(env=dict(self.env, WATCH_WITHHOLD=json.dumps({"addresses": [HELD_MS]}))); self.assertNotIn("not_shown", self.get("coverage.json")); self.assertNotIn("not_shown", self.get("pending_ops.json"))
    def test_the_address_of_a_queue_left_out_only_for_its_family_is_not_a_secret(self):
        self.run_cli(); self.put("alerts.json", {"x": HELD_MS}); self.assertEqual(self.run_cli("check")[0].returncode, 0); self.assertEqual(self.run_cli("check", extra=("--strict",))[0].returncode, 0)
    def test_but_its_operations_are_still_refused_everywhere(self): self.run_cli(); self.put("alerts.json", {"x": H_ACCT}); self.assertEqual(self.run_cli("check")[0].returncode, 1)
    def test_the_ledger_forgets_every_queue_of_the_family(self):
        d = self.get("warning_ledger.json"); d["entries"]["solana:%s:example:%s:9" % (OTHER_MS.lower(), OTHER_MS)] = {"outcome": "missed"}; self.put("warning_ledger.json", d); self.run_cli(); self.assertEqual(self.get("warning_ledger.json")["entries"], {})
    def test_the_digest_forgets_the_name_of_every_queue_of_the_family(self): self.run_cli(); t = self.text("digest.md"); self.assertNotIn(W.short(HELD_MS), t); self.assertNotIn(W.short(OTHER_MS), t); self.assertIn("another one", t)


class TestInertList(Base):
    """`{}` is a list that leaves nothing out: how a list is lifted, with no alarm."""
    def setUp(self): super().setUp(); self.env["WATCH_WITHHOLD"] = "{}"; self.env["WATCH_WITHHOLD_REQUIRED"] = "1"
    def test_no_alarm_where_the_list_is_expected(self): r, out = self.run_cli(); self.assertEqual(r.returncode, 0); self.assertFalse(os.path.exists(os.path.join(self.w, "run.log"))); self.assertFalse(os.path.exists(out))
    def test_nothing_is_changed(self): before = {n: self.text(n) for n in os.listdir(self.w)}; self.run_cli(); self.assertEqual(before, {n: self.text(n) for n in os.listdir(self.w)})
    def test_views_and_check_are_quiet_too(self): self.run_cli(); self.assertEqual((self.run_cli("views")[0].returncode, self.run_cli("check")[0].returncode), (0, 0))
    def test_even_an_unreadable_queue_file_does_not_stop_the_run(self): open(os.path.join(self.w, "pending_ops.json"), "w").write("{broken"); self.assertEqual(self.run_cli()[0].returncode, 0)
    def test_an_empty_secret_is_a_list_not_read_where_it_is_expected(self):
        r, out = self.run_cli(env=dict(self.env, WATCH_WITHHOLD="")); self.assertIn("ALARM withhold list not read", self.text("run.log")); self.assertIn("alarm=1", open(out).read())


class TestFailsClosed(Base):
    def test_an_unreadable_queue_file_stops_the_run_with_the_private_alarm(self):
        open(os.path.join(self.w, "pending_ops.json"), "w").write("{broken"); r, out = self.run_cli(); self.assertEqual((r.returncode, r.stdout, r.stderr), (2, "", ""))
        self.assertIn("ALARM withhold stopped the run", self.text("run.log")); self.assertIn("alarm=1", open(out).read())
    def test_a_crash_with_a_list_present_raises_the_private_alarm(self):
        r, out = self.run_cli(env=dict(self.env, WATCH_WITHHOLD_PRIVATE=self.d)); self.assertEqual(r.returncode, 2); self.assertIn("ALARM withhold stopped the run", self.text("run.log")); self.assertIn("alarm=1", open(out).read())
    def test_a_red_check_raises_the_private_alarm(self):
        self.run_cli(); self.put("alerts.json", {"x": H_ACCT}); r, out = self.run_cli("check"); self.assertEqual(r.returncode, 1); self.assertIn("ALARM withhold stopped the run", self.text("run.log")); self.assertIn("alarm=1", open(out).read())
        for s in (H_ACCT, HELD_MS): self.assertNotIn(s, self.text("run.log"))
    def test_a_green_check_raises_nothing(self): self.run_cli(); self.run_cli("check"); self.assertFalse(os.path.exists(os.path.join(self.w, "run.log")))
    def test_a_check_without_the_secret_reads_the_list_the_first_step_kept(self):
        self.run_cli(); self.put("alerts.json", {"x": HELD_BUFFER}); env = {"PATH": os.environ.get("PATH", ""), "RUNNER_TEMP": self.d}; os.rename(self.private, os.path.join(self.d, "held_queue.json"))
        j = json.load(open(os.path.join(self.d, "held_queue.json"))); j["config"] = {"addresses": [HELD_BUFFER], "categories": [], "level": "hide"}; json.dump(j, open(os.path.join(self.d, "held_queue.json"), "w"))
        self.assertEqual(self.run_cli("check", env=env)[0].returncode, 1)


class TestRecordReadsWhatTheFirstStepKept(Base):
    def test_the_configuration_travels_with_the_private_file_so_the_record_needs_no_secret(self):
        env = dict(self.env, WATCH_WITHHOLD=json.dumps({"addresses": [HELD_MS, HELD_VAULT]})); self.run_cli(env=env)
        c = json.load(open(self.private))["config"]; self.assertEqual((sorted(c["addresses"]), c["level"]), (sorted([HELD_MS.lower(), HELD_VAULT.lower()]), "hide"))
        self.put("alerts.json", {"x": HELD_VAULT}); env2 = {"PATH": os.environ.get("PATH", ""), "WATCH_WITHHOLD_PRIVATE": self.private}
        self.assertEqual(self.run_cli("check", env=env2)[0].returncode, 1)   # no WATCH_WITHHOLD here, as in the record step


class TestSecondOpinionPage(Base):
    """second_opinion.md is written from the same lists as second_opinion.json: it must not announce what the json no longer does."""
    UP = "program redeployed since the previous run: slot 1 -> 2"; CH = "admin read changed since the previous run: a -> b"
    def setUp(self):
        super().setUp(); self.put("second_opinion.json", {"results": [{"chain": "solana", "target": HELD_PROG, "multisig": HELD_MS, "upgraded": self.UP, "changed": self.CH}, {"chain": "solana", "target": OTHER_PROG, "upgraded": "another upgrade"}], "upgrades": [], "changed": []})
    def page(self, ups=(), chs=(), dis=("**%s** on solana: the score disagrees" % OTHER_PROG,)):
        s = "## Second opinion, 2026-11-09T06:00:00Z\n\n"
        if ups: s += "### %d upgrade(s) executed since the previous run (x)\n\n%sThe code behind a tracked proxy changed.\n\n" % (len(ups), "".join("- **%s** on solana: %s\n" % x for x in ups))
        if chs: s += "### %d admin change(s) since the previous run (x)\n\n%s\nThe live admin moved.\n\n" % (len(chs), "".join("- **%s** on solana: %s\n" % x for x in chs))
        if dis: s += "### %d disagreement(s) with the published score\n\n%s\nAn independent reader.\n" % (len(dis), "".join("- %s\n" % x for x in dis))
        open(os.path.join(self.w, "second_opinion.md"), "w").write(s)
    def test_the_upgrade_section_goes_with_its_closing_sentence_when_it_has_no_bullet_left(self):
        self.page(ups=[(HELD_PROG, self.UP)]); self.run_cli(); t = self.text("second_opinion.md"); self.assertNotIn("redeployed", t); self.assertNotIn("upgrade(s) executed", t); self.assertNotIn("The code behind", t); self.assertIn("disagreement(s)", t)
    def test_a_section_that_keeps_a_bullet_is_counted_again(self):
        self.page(ups=[(HELD_PROG, self.UP), (OTHER_PROG, "another upgrade")]); self.run_cli(); t = self.text("second_opinion.md"); self.assertIn("### 1 upgrade(s) executed", t); self.assertIn("another upgrade", t); self.assertNotIn(self.UP, t)
    def test_the_admin_change_section_of_the_governed_program_goes_too(self): self.page(chs=[(HELD_PROG, self.CH)]); self.run_cli(); self.assertNotIn("admin change(s)", self.text("second_opinion.md"))
    def test_the_disagreement_section_is_untouched(self): self.page(ups=[(HELD_PROG, self.UP)]); self.run_cli(); self.assertIn("the score disagrees", self.text("second_opinion.md"))
    def test_the_file_goes_when_nothing_is_left_as_the_writer_does(self): self.page(ups=[(HELD_PROG, self.UP)], dis=()); self.run_cli(); self.assertFalse(os.path.exists(os.path.join(self.w, "second_opinion.md")))
    def test_a_page_about_other_programs_only_is_untouched(self):
        self.page(ups=[(OTHER_PROG, "another upgrade")]); before = self.text("second_opinion.md"); self.run_cli(); self.assertEqual(self.text("second_opinion.md"), before)
    def test_a_line_that_names_a_string_left_out_goes_even_without_a_text_of_ours(self):
        self.put("second_opinion.json", {"results": []}); self.page(chs=[(OTHER_PROG, "example %s changed" % W.short(HELD_MS))]); self.run_cli(); self.assertNotIn(W.short(HELD_MS), self.text("second_opinion.md") if os.path.exists(os.path.join(self.w, "second_opinion.md")) else "")


class TestPaperTrail(Base):
    def setUp(self): super().setUp(); self.put("paper_trail.json", {"docs": {}, "index": {HELD_MS: [{"file": "docs/a.md"}], OTHER_MS: [{"file": "docs/b.md"}]}})
    def test_the_address_that_names_a_string_left_out_leaves_the_index(self):
        self.run_cli(); self.run_cli("views"); self.assertEqual(list(self.get("paper_trail.json")["index"]), [OTHER_MS])
    def test_without_the_cleaning_the_check_would_stop_the_watch(self): self.run_cli(); self.assertEqual(self.run_cli("check")[0].returncode, 1)
    def test_with_it_the_check_passes(self): self.run_cli(); self.run_cli("views"); self.assertEqual(self.run_cli("check")[0].returncode, 0)


class TestJournalEdges(EventsBase):
    def test_the_six_and_four_form_of_an_address_is_recognised(self):
        self.append([ev("admin_change", OTHER_PROG, "holder %s moved" % W.shorts(HELD_MS)[1])]); self.run_cli(); self.assertFalse(any("moved" in e["text"] for e in self.lines()))
    def test_the_last_line_of_the_earlier_run_is_never_dropped_even_if_it_names_the_multisig(self):
        os.remove(self.ev); head = chain_append(self.ev, [ev("move", OTHER_PROG), ev("admin_change", HELD_PROG, "example %s" % W.short(HELD_MS))]); self.sign(head); before = open(self.ev).read()
        self.append([ev("move", OTHER_PROG, "new")]); self.run_cli(); self.assertTrue(open(self.ev).read().startswith(before)); self.assertTrue(verify_chain.check(self.ev)["ok"])
    def test_an_unknown_head_with_nothing_to_drop_still_stops_the_run(self):
        self.append([ev("move", OTHER_PROG)]); self.sign("0" * 64); r, _ = self.run_cli(); self.assertEqual(r.returncode, 2)


class TestRecord(unittest.TestCase):
    """scripts/watch_branch.sh record: the daily report records too, so the check is in the record itself."""
    def setUp(self):
        self.d = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, self.d, True); os.makedirs(os.path.join(self.d, "scripts"))
        for n in ("watch_branch.sh", "withhold.py"): shutil.copy(os.path.join(SCRIPTS, n), os.path.join(self.d, "scripts", n))
        self.run_ = lambda *a, **k: subprocess.run(list(a), cwd=self.d, capture_output=True, text=True, **k)
        self.run_("git", "init", "-q", "--bare", "remote.git"); self.run_("git", "init", "-q", "-b", "watch-data", "watch"); self.tmp = os.path.join(self.d, "tmp"); os.makedirs(self.tmp)
        self.env = dict(os.environ, WATCH_REMOTE=os.path.join(self.d, "remote.git"), RUNNER_TEMP=self.tmp)
        open(os.path.join(self.d, "watch", "alerts.json"), "w").write("{}")
        json.dump({"queues": [dict(held_record(), _targeted=True)], "config": {"addresses": [HELD_MS], "categories": [], "level": "hide"}}, open(os.path.join(self.tmp, "held_queue.json"), "w"))
    def record(self): return subprocess.run(["bash", "scripts/watch_branch.sh", "record", "m"], cwd=self.d, capture_output=True, text=True, env=self.env)
    def commits(self): return self.run_("git", "-C", "watch", "rev-list", "--all", "--count").stdout.strip()
    def test_a_clean_tree_is_recorded_and_pushed(self): r = self.record(); self.assertEqual(r.returncode, 0, r.stderr); self.assertEqual(self.run_("git", "--git-dir", "remote.git", "rev-list", "--count", "watch-data").stdout.strip(), "1")
    def test_a_file_that_names_a_string_left_out_stops_the_record_before_any_commit(self):
        open(os.path.join(self.d, "watch", "alerts.json"), "w").write(json.dumps({"x": H_ACCT})); r = self.record(); self.assertEqual(r.returncode, 1); self.assertNotIn(H_ACCT, r.stdout + r.stderr); self.assertEqual(self.commits(), "0")
    def test_without_the_runner_file_the_record_is_what_it_was(self):
        os.remove(os.path.join(self.tmp, "held_queue.json")); open(os.path.join(self.d, "watch", "alerts.json"), "w").write(json.dumps({"x": H_ACCT})); self.assertEqual(self.record().returncode, 0)
    def test_the_message_is_neutral(self): open(os.path.join(self.d, "watch", "alerts.json"), "w").write(json.dumps({"x": H_ACCT})); self.assertIsNone(WORDS.search(self.record().stderr))


# ---- revision 4: the files written after the queue step from the independent reader's page and from the queue state, with the shapes the Watch writes (made-up strings, real forms) ----
PATH = "program -> ProgramData %s -> upgrade authority (a program-derived address, off the curve: a vault or a protocol PDA) -> Example multisig v4, vault 0, of multisig %s"


def stale_alert(path):
    """An alert that is about the age of a score and quotes the independent reader's path of control: it names the multisig inside a sentence, in its own case."""
    return {"rule": "score pushed more than 7 days ago (the oracle marks it stale at 9)", "severity": "info", "target": OTHER_PROG, "title": "Example program", "new": True,
            "reading": {"composite": 80, "second_opinion": {"kind": "multisig", "path": path, "block_start": None}}}


def queue_alert():
    return {"rule": "queued operation executable", "severity": "high", "target": HELD_PROG, "title": W.short(HELD_PROG), "new": False,
            "evidence": [{"id": H_ID1, "signature": H_SIG, "timelock": HELD_NAME, "timelock_address": HELD_MS}, {"id": "example:%s:2" % OTHER_MS, "signature": "Example proposal #2: y", "timelock": OTHER_NAME}]}


class TestCarriedFiles(Base):
    """What the pass before the Watch's last steps leaves in the files that later steps write again (alerts, review queue, score series, reports): `views` reads them as `check` does and cleans what check refuses."""
    def setUp(self):
        super().setUp(); self.second = json.dumps({"results": [{"target": HELD_PROG, "multisig": HELD_MS, "path": PATH % (HELD_PROG, HELD_MS)}]}); open(os.path.join(self.w, "second_opinion.json"), "w").write(self.second)

    def go(self, *puts):
        for n, o in puts: self.put(n, o)
        self.run_cli(); v = self.run_cli("views")[0]; return v, self.run_cli("check")[0]

    def test_the_path_of_control_that_names_the_multisig_is_taken_out_with_no_mark_and_the_alert_stays(self):
        v, c = self.go(("alerts.json", {"active": [stale_alert(PATH % (OTHER_PROG, HELD_MS)), stale_alert("no queue here")], "history": []}))
        self.assertEqual((v.returncode, c.returncode), (0, 0)); a = self.get("alerts.json")["active"]; self.assertEqual(len(a), 2)
        self.assertEqual(a[0]["reading"]["second_opinion"], {"kind": "multisig", "block_start": None})
        self.assertEqual((a[0]["rule"], a[0]["target"], a[0]["reading"]["composite"]), (stale_alert("")["rule"], OTHER_PROG, 80))
        self.assertNotIn(W.MASK, self.text("alerts.json")); self.assertEqual(a[1]["reading"]["second_opinion"]["path"], "no queue here")

    def test_the_path_is_taken_out_of_the_history_entries_too_and_nothing_else_of_them(self):
        e = dict(stale_alert(PATH % (OTHER_PROG, HELD_MS)), key="k"); v, c = self.go(("alerts.json", {"active": [], "history": [e]}))
        h = self.get("alerts.json")["history"][0]; self.assertEqual((c.returncode, "path" in h["reading"]["second_opinion"], h["key"], h["rule"]), (0, False, "k", e["rule"]))

    def test_a_number_that_does_not_count_the_list_is_left_as_it_is(self):
        items = [{"text": "queued operation %s" % H_SIG}, {"text": "a stale score"}]; v, c = self.go(("review_queue.json", {"total": 99, "items": items}))
        self.assertEqual((c.returncode, self.get("review_queue.json")["total"], len(self.get("review_queue.json")["items"])), (0, 99, 1))

    def test_the_shortened_form_written_with_the_escaped_ellipsis_in_a_file_of_one_line_per_record_is_written_without_it(self):
        open(os.path.join(self.w, "trend.jsonl"), "w").write(json.dumps({"run_utc": "a", "note": "see " + W.short(HELD_MS)}) + "\n"); self.assertIn("\\u2026", self.text("trend.jsonl"))
        self.run_cli(); self.run_cli("views"); self.assertEqual(self.run_cli("check")[0].returncode, 0); self.assertEqual(json.loads(self.text("trend.jsonl").strip())["note"], "see " + W.MASK)

    def test_a_bullet_that_names_the_queue_but_no_operation_stays_with_the_mark(self):
        open(os.path.join(self.w, "review_queue.md"), "w").write("## Needs a person\n- **other** about %s\n- **stale** a score\n" % HELD_NAME); self.run_cli(); self.run_cli("views")
        self.assertEqual(self.text("review_queue.md"), "## Needs a person\n- **other** about %s\n- **stale** a score\n" % W.MASK); self.assertEqual(self.run_cli("check")[0].returncode, 0)

    def test_the_queue_file_listed_at_level_count_is_not_written_again_by_the_cleaning(self):
        self.env["WATCH_WITHHOLD"] = json.dumps({"addresses": [HELD_MS], "level": "count"}); self.run_cli(); before = self.text("pending_ops.json"); v = self.run_cli("views")[0]
        self.assertEqual((v.returncode, self.text("pending_ops.json")), (0, before)); self.assertEqual(self.run_cli("check")[0].returncode, 0)

    def test_the_text_of_the_mark_is_fixed(self): self.assertEqual(W.MASK, "(not shown)")

    def test_the_address_in_lowercase_in_a_sentence_elsewhere_than_in_a_path_is_written_with_the_mark(self):
        v, c = self.go(("alerts.json", {"active": [dict(stale_alert("x"), title="controlled by %s since then" % HELD_MS.lower())], "history": []}))
        self.assertEqual(c.returncode, 0); self.assertEqual(self.get("alerts.json")["active"][0]["title"], "controlled by %s since then" % W.MASK)

    def test_the_two_shortened_forms_are_written_without_it(self):
        v, c = self.go(("alerts.json", {"active": [dict(stale_alert("x"), title="%s and %s" % (W.shorts(HELD_MS)[0], W.shorts(HELD_MS)[1]))], "history": []}))
        self.assertEqual(c.returncode, 0); self.assertEqual(self.get("alerts.json")["active"][0]["title"], "%s and %s" % (W.MASK, W.MASK))

    def test_a_file_written_with_the_escaped_ellipsis_is_cleaned_too(self):
        open(os.path.join(self.w, "alerts.json"), "w").write(json.dumps({"active": [dict(stale_alert("x"), title=W.short(HELD_MS))], "history": []}))   # json.dumps writes …
        self.assertIn("\\u2026", self.text("alerts.json")); self.run_cli(); self.run_cli("views"); self.assertEqual(self.run_cli("check")[0].returncode, 0)

    def test_without_the_cleaning_check_stops_on_it(self):
        self.put("alerts.json", {"active": [stale_alert(PATH % (OTHER_PROG, HELD_MS))], "history": []}); self.run_cli(); r = self.run_cli("check")[0]; self.assertEqual(r.returncode, 1); self.assertIn("alerts.json", r.stderr)

    def test_an_alert_that_quotes_an_operation_of_the_queue_leaves_and_the_others_stay(self):
        v, c = self.go(("alerts.json", {"active": [queue_alert(), stale_alert("x")], "history": []}))
        self.assertEqual(c.returncode, 0); self.assertEqual([x["rule"] for x in self.get("alerts.json")["active"]], [stale_alert("")["rule"]])

    def test_an_evidence_that_names_only_the_other_queue_stays_in_its_alert(self):
        a = queue_alert(); a["evidence"] = [a["evidence"][1]]; v, c = self.go(("alerts.json", {"active": [a], "history": []}))
        self.assertEqual(self.get("alerts.json")["active"][0]["evidence"][0]["id"], "example:%s:2" % OTHER_MS)

    def test_the_items_of_the_review_queue_that_name_an_operation_leave_and_the_total_is_counted_again(self):
        items = [{"text": "queued operation %s: %s" % (HELD_NAME, H_SIG)}, {"text": "a stale score"}, {"text": "queued operation %s" % OTHER_NAME}]
        v, c = self.go(("review_queue.json", {"total": 3, "items": items}))
        self.assertEqual(c.returncode, 0); d = self.get("review_queue.json"); self.assertEqual((d["total"], [i["text"] for i in d["items"]]), (2, ["a stale score", "queued operation %s" % OTHER_NAME]))

    def test_the_bullets_of_the_review_page_that_name_an_operation_leave_and_a_line_that_names_the_multisig_is_written_without_it(self):
        open(os.path.join(self.w, "review_queue.md"), "w").write("## Needs a person\n- **queued** %s: %s\n- **stale** a score\n- **other** %s\nsee %s\n" % (HELD_NAME, H_SIG, OTHER_NAME, HELD_MS))
        self.run_cli(); self.run_cli("views"); self.assertEqual(self.run_cli("check")[0].returncode, 0)
        self.assertEqual(self.text("review_queue.md"), "## Needs a person\n- **stale** a score\n- **other** %s\nsee %s\n" % (OTHER_NAME, W.MASK))

    def test_the_actions_of_the_calibration_that_name_a_transaction_leave_and_the_count_follows(self):
        lst = [{"kind": "Example proposal executed", "key": "solana:x", "via": HELD_NAME, "tx": H_TX}, {"kind": "admin changed", "key": "solana:x", "via": None, "tx": None}]
        v, c = self.go(("score_series.json", {"series": {}, "calibration": {"actions": 2, "list": lst}}))
        d = self.get("score_series.json")["calibration"]; self.assertEqual((c.returncode, d["actions"], [x["kind"] for x in d["list"]]), (0, 1, ["admin changed"]))

    def test_an_operation_named_in_a_value_outside_any_list_is_written_without_it(self):
        v, c = self.go(("review_queue.json", {"total": 0, "note": "see %s" % H_TX, "items": []}))
        self.assertEqual((c.returncode, self.get("review_queue.json")["note"]), (0, "see " + W.MASK))

    def test_an_entry_keyed_by_the_multisig_leaves_the_file(self):
        v, c = self.go(("score_series.json", {"series": {"solana:" + HELD_MS.lower(): [1], "solana:other": [2]}}))
        self.assertEqual((c.returncode, list(self.get("score_series.json")["series"])), (0, ["solana:other"]))

    def test_a_key_inside_an_entry_is_written_without_it(self):
        v, c = self.go(("alerts.json", {"active": [{"rule": "r", "counts": {HELD_MS: 2, "other": 1}}], "history": []}))
        self.assertEqual((c.returncode, self.get("alerts.json")["active"][0]["counts"]), (0, {W.MASK: 2, "other": 1}))

    def test_the_whole_name_of_the_queue_is_written_as_one_mark_not_around_its_shortened_form(self):
        v, c = self.go(("alerts.json", {"active": [dict(stale_alert("x"), title=HELD_NAME)], "history": []}))
        self.assertEqual((c.returncode, self.get("alerts.json")["active"][0]["title"]), (0, W.MASK))

    def test_a_line_of_a_file_of_one_line_per_record_is_written_without_it_and_stays(self):
        open(os.path.join(self.w, "trend.jsonl"), "w").write(json.dumps({"run_utc": "a", "note": HELD_MS}) + "\n" + json.dumps({"run_utc": "b"}) + "\n")
        self.run_cli(); self.run_cli("views"); ls = self.text("trend.jsonl").split("\n"); self.assertEqual((len([l for l in ls if l]), json.loads(ls[0])["note"]), (2, W.MASK)); self.assertEqual(self.run_cli("check")[0].returncode, 0)

    def test_the_structure_files_are_not_touched_by_the_default_pass(self):
        self.go(("alerts.json", {"active": [stale_alert(PATH % (OTHER_PROG, HELD_MS))], "history": []})); self.assertEqual(self.text("second_opinion.json"), self.second)

    def test_a_file_with_nothing_to_clean_is_not_written_again(self):
        self.put("review_queue.json", {"total": 1, "items": [{"text": "a stale score"}]}); open(os.path.join(self.w, "review_queue.json"), "a").write("\n"); before = self.text("review_queue.json"); self.run_cli(); self.run_cli("views"); self.assertEqual(self.text("review_queue.json"), before)

    def test_a_second_pass_changes_nothing_more(self):
        self.go(("alerts.json", {"active": [queue_alert(), stale_alert(PATH % (OTHER_PROG, HELD_MS))], "history": []})); once = self.text("alerts.json"); self.run_cli("views"); self.assertEqual(self.text("alerts.json"), once)

    def test_a_scored_program_in_the_list_is_not_written_without_its_address(self):
        os.makedirs(os.path.join(self.w, "scores")); self.put("scores/s.json", {"targets": [{"target": OTHER_PROG}]})
        self.env["WATCH_WITHHOLD"] = json.dumps({"addresses": [HELD_MS, OTHER_PROG]}); v, c = self.go(("alerts.json", {"active": [stale_alert("x")], "history": []}))
        self.assertEqual((c.returncode, self.get("alerts.json")["active"][0]["target"]), (0, OTHER_PROG))

    def test_a_published_file_that_cannot_be_read_stops_the_job_instead_of_publishing_it(self):
        self.run_cli(); open(os.path.join(self.w, "alerts.json"), "w").write("{broken " + HELD_MS); v = self.run_cli("views")[0]
        self.assertEqual(v.returncode, 2); self.assertNotIn(HELD_MS, v.stdout + v.stderr); self.assertIn("ALARM withhold", self.text("run.log"))

    def test_without_a_list_nothing_is_cleaned(self):
        self.put("alerts.json", {"active": [stale_alert(PATH % (OTHER_PROG, HELD_MS))], "history": []}); before = self.text("alerts.json")
        self.run_cli(env={"PATH": os.environ.get("PATH", ""), "WATCH_WITHHOLD_PRIVATE": os.path.join(self.d, "none.json")}); self.run_cli("views", env={"PATH": os.environ.get("PATH", ""), "WATCH_WITHHOLD_PRIVATE": os.path.join(self.d, "none.json")}); self.assertEqual(self.text("alerts.json"), before)

    def test_the_message_of_a_run_that_cleaned_something_names_nothing(self):
        self.put("alerts.json", {"active": [queue_alert()], "history": []}); self.run_cli(); v = self.run_cli("views")[0]; self.assertEqual((v.stdout, v.stderr), ("", ""))


class TestCarriedFilesEvents(EventsBase):
    def test_the_event_log_is_never_rewritten_by_the_cleaning(self):
        chain_append(self.ev, [ev("admin_change", HELD_PROG, "example %s" % W.short(HELD_MS))]); self.sign(verify_chain.check(self.ev)["head"]); self.append([ev("move", OTHER_PROG)])
        self.run_cli(); before = self.text("events.jsonl"); v = self.run_cli("views")[0]; self.assertEqual((v.returncode, self.text("events.jsonl")), (0, before)); self.assertEqual(self.run_cli("check")[0].returncode, 0)


if __name__ == "__main__":
    unittest.main()
