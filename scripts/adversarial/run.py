#!/usr/bin/env python3
"""The adversarial kit: the ten tests of the review of 2026-10-30, a baseline, the alert-proof case and the node without old state (thirteen cases), run offline against fixtures, each with the result it must give written beforehand (EXPECTED.json).

    python3 scripts/adversarial/run.py              # all cases; exit 0 only if every case gave its expected result
    python3 scripts/adversarial/run.py --case 07    # one case
    python3 scripts/adversarial/run.py --json       # the observed results as JSON

No network, no key of value (the signing cases generate throw-away keys in a temporary folder), nothing is written outside a temporary folder. The kit does
not prove the watch is safe: a case whose expected result says "detected": false is a gap the watch has and says so (`known_gap`). A case that is skipped
because a dependency is missing (PyNaCl for the signing cases) is reported as SKIPPED and fails the run unless --allow-skip is given.

Why it exists: a review of 2026-10-30 listed ten tests a reviewer would run. Each case names the attack, the component it hits and what the watch does.

WHAT EACH CASE EXERCISES (said in `exercises` in EXPECTED.json): cases 01, 02, 08 and 09 hand the trust rule a record of the independent reader written by the case
(or by the reader's own pure function) and check the status the rule gives: they test the association between a reading and a status, NOT the reader's RPC reads
(no node is asked). Case 03 runs the real timelock code on a fake chain. Case 04 runs the real reader on fake RPC answers. Case 05 runs the real signing and
verification code. Case 06 the real chain verifier. Case 07 the real delivery code with simulated receivers (HTTP transport, redirects and Telegram are not
exercised). Case 10 the trust rule on an old run. Case 11 the real alert engine and the offline replay of the proof it carries. Case 12 the real block probe on fake RPC answers and the trust rule on a scores file that carries it.
"""
import argparse
import calendar
import copy
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.abspath(os.path.join(HERE, ".."))
ROOT = os.path.abspath(os.path.join(SCRIPTS, ".."))
sys.path.insert(0, SCRIPTS)
sys.path.insert(0, os.path.join(SCRIPTS, "lib"))
sys.path.insert(0, HERE)
import trust  # noqa: E402
from lib import reader_audit as ra  # noqa: E402

EXPECTED = os.path.join(HERE, "EXPECTED.json")
sys.path.insert(0, os.path.join(SCRIPTS, "lib", "tests"))
from trust_support import BASE, NOW, A, B, C, KEY, jload, jdump, Watch, status, codes, so_edit  # noqa: E402,F401  -- shared with the tests of the trust status


class Skipped(Exception):
    pass


# ---------------------------------------------------------------------------------------------------------------------------------- the cases

def case_00():
    w = Watch()
    try:
        d = w.trust()
        return {"statuses": {"A": status(d, A), "B": status(d, B), "C": status(d, C)}}
    finally:
        w.close()


def case_01():
    """The independent reader reads DEFAULT_ADMIN_ROLE members up to a bound of 10; 25 exist."""
    w = Watch()
    try:
        members = ra.assemble_admin_members(B, 25, ["0x" + "00" * 12 + "%040x" % i for i in range(2, 11)])
        w.edit("second_opinion.json", so_edit(B, admin_members=members))
        d = w.trust()
        return {"detected": "admin_members_unread" in codes(d, B), "status_of_B": status(d, B), "reason": "admin_members_unread" if "admin_members_unread" in codes(d, B) else None, "members_unread": members["unread"]}
    finally:
        w.close()


def modules_word(n, nxt):
    return "0x" + "%064x" % 0x40 + "%064x" % nxt + "%064x" % n + "".join("%064x" % (100 + i) for i in range(n))


def case_02():
    w = Watch()
    try:
        mods, trunc = ra.parse_modules_page(modules_word(50, 0xABCDEF))
        w.edit("second_opinion.json", so_edit(A, modules=mods, modules_truncated=trunc))
        d1 = w.trust()
        w.edit("second_opinion.json", so_edit(A, modules=None, modules_truncated=None))
        d2 = w.trust()
        return {"detected": trunc is True and "modules_truncated" in codes(d1, A), "modules_truncated_flag": trunc, "status_of_A_truncated": status(d1, A),
                "reason_truncated": "modules_truncated" if "modules_truncated" in codes(d1, A) else None, "status_of_A_unread": status(d2, A),
                "reason_unread": "modules_unread" if "modules_unread" in codes(d2, A) else None}
    finally:
        w.close()


class FakeEth:
    def __init__(self, head, logs, answers):
        self.block_number, self._logs, self._answers = head, logs, answers

    def get_logs(self, flt):
        return [l for l in self._logs if l["blockNumber"] >= flt["fromBlock"] and l["topics"][0] == flt["topics"][0]]

    def get_block(self, n):
        return {"timestamp": 1_790_000_000 + n * 12}

    def call(self, tx):
        data = bytes(tx["data"])
        sel = data[:4].hex()
        fn = self._answers.get(sel)
        if fn is None:
            raise RuntimeError("no answer for " + sel)
        return fn(data[4:])


class FakeW3:
    def __init__(self, eth):
        self.eth = eth


def case_03():
    """check_pending_ops.check_timelock on a fake chain: one operation queued 40 days ago, one 10 days ago, a 30-day window."""
    import importlib
    from lib import abi_returndata_guard, pending_ops
    abi_returndata_guard.uninstall()      # another suite may have installed the ABI guard and left modules holding its wrapper: start from the real decoder
    importlib.reload(pending_ops)
    import check_pending_ops as cpo
    importlib.reload(cpo)
    from eth_abi import encode
    from web3 import Web3
    head = 25_000_000
    topic = cpo.QUEUE_TOPICS["oz"]
    def op(i, age_days):
        block = head - int(age_days * 86400 / 12)
        data = encode(["address", "uint256", "bytes", "bytes32", "uint256"], [Web3.to_checksum_address("0x" + "dd" * 20), 0, b"\x01\x02\x03\x04", b"\x00" * 32, 172800])
        return {"topics": [topic, "0x" + "%064x" % i, "0x" + "%064x" % 0], "data": "0x" + data.hex(), "blockNumber": block, "transactionHash": "0x" + "%064x" % i}
    ops = [op(40, 40), op(10, 10)]
    ready = int(time.time()) + 7200
    def sel(sig): return Web3.keccak(text=sig)[:4].hex()
    answers = {sel("getMinDelay()"): lambda a: (172800).to_bytes(32, "big"), sel("isOperationPending(bytes32)"): lambda a: (1).to_bytes(32, "big"),
               sel("getTimestamp(bytes32)"): lambda a: ready.to_bytes(32, "big"), sel("isOperationDone(bytes32)"): lambda a: (0).to_bytes(32, "big")}
    logs_w3, calls_w3 = FakeW3(FakeEth(head, ops, answers)), FakeW3(FakeEth(head, [], answers))
    orig = cpo.get_w3
    cpo.get_w3 = lambda url: logs_w3 if url == cpo.TENDERLY["ethereum"] else calls_w3
    try:
        out = cpo.check_timelock("Fake Timelock", "ethereum", "0x" + "ee" * 20, "oz", 30)
    finally:
        cpo.get_w3 = orig
    listed = {o["id"] for o in out["pending"]} | {o["id"] for o in out["recent"]}
    w = Watch()
    try:
        d = w.trust()
        return {"detected": ("0x" + "%064x" % 40) in listed, "known_gap": ("0x" + "%064x" % 40) not in listed, "op_40_days_old_listed": ("0x" + "%064x" % 40) in listed,
                "op_10_days_old_listed": ("0x" + "%064x" % 10) in listed, "window_days_declared": out.get("window_days_est"), "window_note_declared": bool(out.get("window_note"))}
    finally:
        w.close()


def case_04():
    import watch_run as wr
    # (a) a node that answers fewer targets than the last run: the list comes back from the last run
    prev = {"0x" + "%040x" % i: {"target": "0x" + "%040x" % i, "index": i, "compositeScore": 10} for i in range(3)}
    cur = [{"target": "0x" + "%040x" % 0, "index": 0, "compositeScore": 10}]
    restored = wr.restore_dropped_targets(cur, prev)
    # (b) a node that answers a target that is not an address, (c) a score word that is too short
    orig = (wr.rpc, wr.batched, wr.self_watch)
    calls = {"n": 0}
    def fake_rpc(url, calls_, tries=3):
        m = calls_[0][0]
        return ["0x64"] if m == "eth_blockNumber" else ["0x1", "0x" + "%064x" % 777600]
    def garbage(url, calls_):
        return ["0x" + "zz" * 32]
    def short_score(url, calls_):
        calls["n"] += 1
        return ["0x" + "00" * 12 + "ab" * 20] if calls["n"] == 1 else ["0x01", "0x" + "%064x" % 0]
    wr.rpc, wr.self_watch = fake_rpc, (lambda *a, **k: {"read": True})
    res = {}
    try:
        wr.batched = garbage
        try: wr.read_evm("X", "0x" + "ab" * 20, "http://x"); res["garbage"] = False
        except RuntimeError as e: res["garbage"] = "not trusted" in str(e)
        wr.batched = short_score
        calls["n"] = 0
        try: wr.read_evm("X", "0x" + "ab" * 20, "http://x"); res["short"] = False
        except ValueError: res["short"] = True
    finally:
        wr.rpc, wr.batched, wr.self_watch = orig
    w = Watch()
    try:
        w.edit("latest.json", lambda d: d["oracles"][0].update({"read_ok": False, "error": "RuntimeError: refused"}))
        d = w.trust()
        return {"detected": len(restored) == 3 and res.get("garbage") and res.get("short"), "short_list_restored": len(restored) == 3, "garbage_target_refused": res.get("garbage"),
                "short_score_refused": res.get("short"), "status_when_oracle_unread": status(d, A)}
    finally:
        w.close()


def _need_nacl():
    try:
        import nacl.signing  # noqa: F401
    except ImportError:
        raise Skipped("PyNaCl is not installed")


def _events(path, n):
    prev, seq, lines = "", 0, []
    for i in range(n):
        seq += 1
        line = json.dumps({"run_utc": "2026-10-29T00:%02d:00Z" % i, "kind": "move", "text": "e%d" % i, "seq": seq, "prev": prev}, sort_keys=True)
        lines.append(line)
        prev = hashlib.sha256(line.encode()).hexdigest()
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")


def _sign(watch, seed):
    env = dict(os.environ, WATCH_SIGNING_KEY=seed)
    return subprocess.run([sys.executable, "-B", "-E", os.path.join(SCRIPTS, "sign_run.py"), "--watch", watch], env=env, capture_output=True, text=True)


def _verify(watch):
    env = {k: v for k, v in os.environ.items() if k != "WATCH_SIGNING_KEY"}
    return subprocess.run([sys.executable, "-B", "-E", os.path.join(SCRIPTS, "sign_run.py"), "--watch", watch, "--verify"], env=env, capture_output=True, text=True)


def _signed_watch(tmp, seed, events=6):
    d = os.path.join(tmp, "watch")
    shutil.copytree(BASE, d)
    os.remove(os.path.join(d, "signature.json"))
    _events(os.path.join(d, "events.jsonl"), events)
    r = _sign(d, seed)
    if r.returncode != 0:
        raise RuntimeError("signing failed: " + r.stdout + r.stderr)
    return d


def case_05():
    _need_nacl()
    import audit_public
    seed_a, seed_b = os.urandom(32).hex(), os.urandom(32).hex()
    pinned = audit_public.PINNED_KEYS[0]
    def verify(watch, *extra):
        env = {k: v for k, v in os.environ.items() if k != "WATCH_SIGNING_KEY"}
        return subprocess.run([sys.executable, "-B", "-E", os.path.join(SCRIPTS, "sign_run.py"), "--watch", watch, "--verify", *extra], env=env, capture_output=True, text=True).returncode
    with tempfile.TemporaryDirectory() as tmp:
        d = _signed_watch(tmp, seed_a)
        # an altered file, not signed again: caught
        shutil.copytree(d, os.path.join(tmp, "w2"))
        p = os.path.join(tmp, "w2", "second_opinion.json")
        s = jload(p); s["results"][0]["kind"] = "eoa"; jdump(s, p)
        altered = _verify(os.path.join(tmp, "w2")).returncode
        # the same alteration, then signed again with the attacker's own key: the signature is valid, but the key is not the pinned one
        _sign(os.path.join(tmp, "w2"), seed_b)
        unpinned_exit = verify(os.path.join(tmp, "w2"))
        pinned_exit = verify(os.path.join(tmp, "w2"), "--pin", pinned)
        key = jload(os.path.join(tmp, "w2", "signature.json"))["public_key"]
        w = Watch()
        try:
            w.edit("signature.json", lambda sig: sig.update({"public_key": key}))
            doc = w.trust()
            noticed = "signature_key_not_pinned" in codes(doc, A)
        finally:
            w.close()
    return {"detected": pinned_exit != 0 and noticed, "known_gap": True, "altered_file_without_resign_exit": altered, "resign_with_other_key_verify_without_pin_exit": unpinned_exit,
            "resign_with_other_key_verify_with_pin_exit": pinned_exit, "other_key_is_pinned": key in audit_public.PINNED_KEYS, "trust_notices_replacement": noticed}


def case_06():
    _need_nacl()
    import verify_chain
    with tempfile.TemporaryDirectory() as tmp:
        d = _signed_watch(tmp, os.urandom(32).hex(), events=8)
        ev = os.path.join(d, "events.jsonl")
        lines = open(ev).read().splitlines()
        open(ev, "w").write("\n".join(lines[:-3]) + "\n")                       # the last three lines are cut
        chain_ok = verify_chain.check(ev)["ok"]
        r = _verify(d)
        return {"detected": r.returncode == 1, "verify_chain_ok": chain_ok, "sign_run_verify_exit": r.returncode, "chain_head_mismatch_reported": "chain head" in r.stdout}


def case_07():
    import harness
    # (a) 15 alerts, the signed webhook down for the first run only
    with harness.Delivery(15) as d:
        d.webhook.up = False
        d.run()
        d.webhook.up = True
        runs, out = d.run_until_delivered()
        total_runs = 1 + runs
        lost = sum(1 for t in d.targets if not d.discord.counts().get(t) or not d.webhook.counts().get(t))
        dups_plain = d.discord.duplicates() + d.webhook.duplicates()
    # (b) a receiver that stores each message and loses its answer once
    with harness.Delivery(4, channels=("webhook",)) as d:
        d.webhook.lose_ack = True
        d.run()
        d.webhook.lose_ack = False
        d.run_until_delivered()
        dups_ack = d.webhook.duplicates()
        lost_ack = sum(1 for t in d.targets if not d.webhook.counts().get(t))
    return {"detected": lost == 0 and lost_ack == 0, "alerts": 15, "lost": lost + lost_ack, "duplicates_without_ack_loss": dups_plain, "runs_to_deliver_all": total_runs, "duplicates_with_ack_loss": dups_ack}


def case_08():
    w = Watch()
    try:
        w.edit("second_opinion.json", so_edit(C, kind="unreadable", why="no admin slot, owner(), admin(), DEFAULT_ADMIN_ROLE member or authority() answered"))
        d = w.trust()
        return {"detected": status(d, C) == "UNVERIFIED", "status_of_C": status(d, C), "reason": "independent_read_unreadable" if "independent_read_unreadable" in codes(d, C) else None}
    finally:
        w.close()


def case_09():
    w = Watch()
    try:
        w.edit("held_assets.json", lambda d: d["by_target"].update({KEY[A]: {"held_usd": 1_000_000.0, "price_at": NOW - 5 * 86400, "symbol": "USDC"}}))
        d = w.trust()
        return {"listed": "money_stale" in codes(d, A), "financial_exposure_state": d["by_target"][KEY[A]]["dimensions"]["financial_exposure"], "status_of_A": status(d, A),
                "reason": "money_stale" if "money_stale" in codes(d, A) else None}
    finally:
        w.close()


def case_10():
    w = Watch()
    try:
        d = w.trust(now=calendar.timegm(time.strptime("2026-10-30T06:20:00Z", "%Y-%m-%dT%H:%M:%SZ")) + 73 * 3600)
        return {"detected": status(d, A) == "STALE", "status_of_A": status(d, A), "reason": "watch_old" if "watch_old" in codes(d, A) else None, "run_age_hours": 73}
    finally:
        w.close()


def case_11():
    """An alert carries the reading behind it (`reading`): replayed offline against the scores file it came from. An altered block, or no proof, is caught."""
    import harness
    with harness.Delivery(1, channels=()) as d:
        out = d.run()
        scores = jload("watch/scores/robinhood-chain.json")
        target = d.targets[0]
        reading = out["active"][0].get("reading")
        ok, bad = ra.evidence_matches(reading or {}, scores, target)
        altered = dict(reading, oracle_block=reading["oracle_block"] + 1, reproduce=reading["reproduce"].replace("--block %s" % reading["oracle_block"], "--block %s" % (reading["oracle_block"] + 1)))
        ok_alt, _ = ra.evidence_matches(altered, scores, target)
        ok_none, _ = ra.evidence_matches({}, scores, target)
    return {"detected": bool(reading) and ok and not ok_alt and not ok_none, "evidence_present": bool(reading), "proof_matches_recorded_read": ok, "altered_block_detected": not ok_alt, "missing_proof_detected": not ok_none}


def case_12():
    """A node that keeps no archive: the block tag is ignored (it answers for block 1 as for the head), or its old state is simply gone, or it honours the tag."""
    import watch_run as wr
    latest = "0x" + "%064x" % 7
    orig = wr.rpc
    probes = {}
    try:
        wr.rpc = lambda url, calls, tries=3: [latest]                                              # ignores the tag: the same answer for block 1
        probes["ignored"] = wr.probe_block("http://x", "0x" + "ab" * 20, latest)["honoured"]
        def gone(url, calls, tries=3):
            raise RuntimeError("missing trie node: historical state not available")
        wr.rpc = gone                                                                               # pruned: the old state is not there, the node says so
        probes["gone"] = wr.probe_block("http://x", "0x" + "ab" * 20, latest)["honoured"]
        wr.rpc = lambda url, calls, tries=3: ["0x"]                                                 # honours the tag: nothing existed at block 1
        probes["honoured"] = wr.probe_block("http://x", "0x" + "ab" * 20, latest)["honoured"]
    finally:
        wr.rpc = orig
    st = {}
    for name, honoured in (("ignored", probes["ignored"]), ("gone", probes["gone"]), ("honoured", probes["honoured"])):
        w = Watch()
        try:
            w.edit("scores/robinhood-chain.json", lambda d, h=honoured: d.update({"block_probe": {"honoured": h, "probe_block": 1, "note": "case 12"}}))
            doc = w.trust()
            st[name] = (status(doc, A), codes(doc, A))
        finally:
            w.close()
    return {"detected": probes["ignored"] is False and st["ignored"][0] == "UNVERIFIED", "probe_when_tag_ignored": probes["ignored"], "probe_when_old_state_missing": probes["gone"],
            "probe_when_tag_honoured": probes["honoured"], "status_of_A_when_tag_ignored": st["ignored"][0], "reason_when_tag_ignored": next((c for c in st["ignored"][1] if c == "block_not_honoured"), None),
            "status_of_A_when_tag_honoured": st["honoured"][0], "status_of_A_when_old_state_missing": st["gone"][0]}


CASES = {"00-baseline": case_00, "01-hidden-authority": case_01, "02-safe-with-module": case_02, "03-timelock-outside-window": case_03, "04-rpc-that-lies": case_04,
         "05-signature-and-key-replaced": case_05, "06-journal-truncated": case_06, "07-webhook-loss": case_07, "08-proxy-outside-patterns": case_08, "09-finance-stale": case_09,
         "10-surveillance-interrupted": case_10, "11-alert-proof-replayable": case_11, "12-node-without-old-state": case_12}


def compare(expected, observed):
    """The expected keys that the observation does not match. `attack`, `known_gap` and `written_*` are descriptions, not observations (known_gap is both: compared when observed)."""
    bad = []
    for k, v in expected.items():
        if k in ("attack", "exercises", "limits"):
            continue
        if k not in observed:
            bad.append("%s: not observed" % k)
        elif observed[k] != v:
            bad.append("%s: expected %r, observed %r" % (k, v, observed[k]))
    return bad


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0]); ap.add_argument("--case"); ap.add_argument("--json", action="store_true"); ap.add_argument("--allow-skip", action="store_true")
    a = ap.parse_args(argv)
    expected = jload(EXPECTED)["cases"]
    results, failed = {}, 0
    for name, fn in CASES.items():
        if a.case and not name.startswith(a.case):
            continue
        try:
            obs = fn()
            bad = compare(expected[name], obs)
            results[name] = {"observed": obs, "mismatch": bad}
            line = "OK        " if not bad else "MISMATCH  "
            failed += bool(bad)
        except Skipped as e:
            results[name] = {"skipped": str(e)}
            line = "SKIPPED   "
            failed += 0 if a.allow_skip else 1
        if not a.json:
            gap = " (a known gap, said so)" if expected[name].get("known_gap") else ""
            print(line + name + gap)
            for b in results[name].get("mismatch", []):
                print("            " + b)
            if "skipped" in results[name]:
                print("            " + results[name]["skipped"])
    if a.json:
        print(json.dumps(results, indent=1, sort_keys=True))
    else:
        print("%d case(s) run, %d not as expected" % (len(results), failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
