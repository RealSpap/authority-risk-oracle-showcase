#!/usr/bin/env python3
"""Read every deployed oracle and record what moved since the previous run (read-only, public RPC, no key).

For each EVM oracle in `live_target_counts.ORACLES`: `trackedTargetsCount()`, every `trackedTargets(i)`, then `getScore(target)`
and `isStale(target)` for each; the Solana program is read through `solana_oracle_reader`. Each oracle's result goes to
`watch/scores/<oracle>.json` (with the previous composite of every target), the run is summarised in `watch/latest.json`,
one line is appended to `watch/history.jsonl`, every move or alarm to `watch/events.jsonl`, and from those: `watch/feed.xml`
(Atom, the last 60 events) and `watch/badge.json` (a shields.io endpoint). When something needs a person, `watch/alarm.md` is
written and the exit code is 2.

Exit codes: 0 nothing to flag; 1 at least one oracle could not be read (its targets are unknown, not zero); 2 alarm
(a composite dropped by 10 points or more, a target turned stale, a new target first published below 40, or an oracle
that answered last time could not be read).

    python3 scripts/watch_run.py            # about 2 to 4 minutes
"""
import datetime
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from xml.sax.saxutils import escape as _xml_escape
def escape(t): return _xml_escape(str(t), {'"': "&quot;"})

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from live_target_counts import ORACLES  # noqa: E402
sys.path.insert(0, os.path.join(HERE, "lib"))
import retired as retired_targets  # noqa: E402   # data/retired_targets.json: targets tracked on purpose but no longer scored, listed apart
import run_id  # noqa: E402  -- the Actions run of this passage, written in latest.json so that files can be shown to belong to one run (scripts/check_run_id.py)
from lib.reader_audit import block_honoured, evaluation_of, freshness_record, future_dated, last_updated_alerts, scan_progress  # noqa: E402  -- scan stall, lastUpdated checks, freshness
import solana_oracle_reader  # noqa: E402
import target_networks  # noqa: E402  -- the network of the oracle (test) and of each target (mainnet), read, never assumed

def _dump_json(obj, path, indent=None):
    """Write the file only once the whole object is serialised: a crash half-way never leaves a truncated JSON behind
    (the previous run's file stays), and a reader never sees a half-written one."""
    import json as _j, os as _o
    tmp = path + ".tmp"
    with open(tmp, "w") as f: _j.dump(obj, f, indent=indent)
    _o.replace(tmp, path)


WATCH = os.path.join(ROOT, "watch")
REPO = "https://github.com/RealSpap/authority-risk-oracle-showcase"
from watch_location import RAW  # noqa: E402  -- the state lives on the watch-data branch
PAGE = "https://realspap.github.io/oracle/"
SEL_COUNT, SEL_TARGET, SEL_SCORE, SEL_STALE, SEL_MAX = "0x835e2172", "0x9481e5e0", "0xd47875d0", "0xf461f6e7", "0x87cf4696"
# the oracle watches itself: any RoleGranted / RoleRevoked on the oracle contract since the previous run, a change of its code or of
# maxStaleness is an alarm (who can push scores, who can administer the oracle: the same questions the oracle asks of others)
TOPIC_GRANTED, TOPIC_REVOKED = "0x2f8788117e7eff1d82e926ec794901d17c78024a50270940304540a733656f0d", "0xf6391f5c32d9c69d2a47ea670b442974b53935d1edc7fd64eb21e047a839171b"
ROLE_NAMES = {"0x" + "0" * 64: "DEFAULT_ADMIN_ROLE", "0x73e573f9566d61418a34d5de3ff49360f9c51fec37f7486551670290f6285dab": "UPDATER_ROLE"}
LOG_SPANS = (5000, 1000, 200, 100)   # blocks per eth_getLogs call, tried from the widest: Base Sepolia allows 200, Monad 100, HyperEVM 1000
LOG_CALL_CAP = 120                    # at most this many eth_getLogs calls per oracle per run; beyond it the window is reported unread, never as "no event"
# role holders confirmed on-chain on 2026-10-10 (hasRole on every oracle): the shared updater key of the seven testnet oracles, and
# Robinhood's own. Read directly at every run (hasRole), so a revoked or added role is seen even where eth_getLogs is not usable.
KNOWN_HOLDERS = {"0x20630C6Ab4BA48a80edA46F77b9b6e987A8f32f5": "shared updater (seven oracles)", "0x646968c33D8F6d5A343B68a6F8b1Ce52F13414ba": "Robinhood updater"}
SEL_HAS_ROLE = "0x91d14854"
FIELDS = ["adminKeyScore", "multisigScore", "timelockScore", "oracleAuthorityScore", "crossExposureScore", "compositeScore"]
DROP_THRESHOLD = 10  # same threshold as scripts/lib/alerts.py
NEW_TARGET_ALERT_CEILING = 40
CHUNK = 20           # the Robinhood edge mishandles batch bodies above about 10 KB


def slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


class RateLimited(RuntimeError):
    """The node answered "rate limited" (JSON-RPC code -32005, or HTTP 429). The same call a little later works; a smaller batch only means more calls, which is worse against a limit per address."""


RATE_WAITS = (6, 15, 30, 60)   # seconds: one wait per rate-limited answer of the same call, growing
RATE_BUDGET = 240              # seconds one run may spend waiting on one endpoint; after that the read is reported as unread and the run moves on
_rate_spent, _rate_seen, _rate_cap = {}, set(), {}
# The public Hyperliquid testnet node answers "rate limited" to GitHub's shared runner addresses (11/10: the manual Watch of 15:33 UTC still could not read it after a 240 s wait). Two other public
# nodes of the same chain (998) return exactly the same 16 rows (same lastUpdated, same methodologyHash, same three stale entries): read on them in turn when the official one limits us.
FALLBACK_RPC = {"https://rpc.hyperliquid-testnet.xyz/evm": ["https://998.rpc.thirdweb.com", "https://hyperliquid-testnet.drpc.org"]}


def _rate_limited(out):
    if isinstance(out, dict) and isinstance(out.get("error"), dict):
        e = out["error"]; return e.get("code") == -32005 or "rate" in str(e.get("message", "")).lower()
    return False


class BatchRefused(RuntimeError):
    """HTTP 403 to a JSON-RPC batch."""


_single_only = set()   # endpoints that refused a JSON-RPC batch with HTTP 403 (testnet-rpc.monad.xyz does, even for one call, while it answers the same call sent alone): read call by call from then on


def _singles(url, calls, tries=3):
    """The same calls sent one at a time (a plain JSON-RPC object, no array). Returns the results in order only if EVERY call answered: a partial list is never returned, the read is unread (RuntimeError).
    A rate-limited answer raises RateLimited at once and marks the endpoint (batched then paces its calls). `tries` is the caller's: tries=1 means one attempt and no pause after it.
    The table is read over several seconds, not in one request: a push of the oracle in between would mix two states under one reference block (a few seconds for 9 targets, and already true between the lots of `batched`).
    ponytail: a fixed 0.2 s between calls, no growing wait (the batch path keeps that); add it when an endpoint that refuses batches also rate-limits."""
    out = []
    for m, p in calls:
        if out: time.sleep(0.2)
        body = json.dumps({"jsonrpc": "2.0", "id": 0, "method": m, "params": p}).encode(); last = None
        for attempt in range(tries):
            try:
                req = urllib.request.Request(url, data=body, headers={"content-type": "application/json", "user-agent": "watch_run/1"})
                with urllib.request.urlopen(req, timeout=40) as r:
                    one = json.loads(r.read().decode())
                if _rate_limited(one): raise RateLimited(str(one.get("error"))[:100])
                if not isinstance(one, dict) or one.get("id") != 0 or "error" in one or "result" not in one: raise ValueError(f"malformed single answer ({str(one)[:80]})")
                out.append(one["result"]); break
            except RateLimited: _rate_seen.add(url); raise
            except urllib.error.HTTPError as e:
                if e.code == 429: _rate_seen.add(url); raise RateLimited("HTTP 429")
                last = e
            except Exception as e:  # noqa: BLE001 -- retried, then reported
                last = e
            if attempt < tries - 1: time.sleep(1 + attempt)
        else:
            raise RuntimeError(f"{type(last).__name__}: {last} (read one call at a time)")
    return out


def rpc(url, calls, tries=3):
    """One JSON-RPC batch; returns a list of results in order. Raises on the last failed try. A rate-limited answer (the public Hyperliquid testnet node does this to GitHub's shared runner
    addresses, 11/10: three reads in four came back unread) is waited out with growing pauses instead of being counted as one of the `tries`."""
    if url in _single_only: return _singles(url, calls, tries)
    body = json.dumps([{"jsonrpc": "2.0", "id": i, "method": m, "params": p} for i, (m, p) in enumerate(calls)]).encode()
    last, attempt, waits = None, 0, 0
    while True:
        try:
            req = urllib.request.Request(url, data=body, headers={"content-type": "application/json", "user-agent": "watch_run/1"})
            try:
                with urllib.request.urlopen(req, timeout=40) as r:
                    out = json.loads(r.read().decode())
            except urllib.error.HTTPError as e:
                if e.code == 429: raise RateLimited("HTTP 429")
                if e.code == 403: raise BatchRefused("HTTP 403")   # the endpoint refuses batches: the same calls, one by one (handled below, outside the retry of the batch)
                raise
            if _rate_limited(out): raise RateLimited(str(out.get("error"))[:100])
            if not isinstance(out, list) or len(out) != len(calls):
                raise ValueError(f"malformed batch answer ({str(out)[:80]})")
            res = sorted(out, key=lambda x: x["id"])
            if any("error" in x for x in res):
                if any(_rate_limited(x) for x in res): raise RateLimited(str([x["error"] for x in res if "error" in x])[:100])
                raise ValueError(str([x["error"] for x in res if "error" in x])[:160])
            return [x["result"] for x in res]
        except BatchRefused:
            _single_only.add(url); return _singles(url, calls, tries)   # an error raised here is not retried by the clauses below: the batch is not sent again
        except RateLimited as e:
            last = e; _rate_seen.add(url)
            if waits >= len(RATE_WAITS) or _rate_spent.get(url, 0) + RATE_WAITS[waits] > _rate_cap.get(url, RATE_BUDGET): break
            _rate_spent[url] = _rate_spent.get(url, 0) + RATE_WAITS[waits]; time.sleep(RATE_WAITS[waits]); waits += 1
        except Exception as e:  # noqa: BLE001 -- retried, then reported
            last = e; attempt += 1
            if attempt >= tries: break
            time.sleep(2 * attempt)
    if isinstance(last, RateLimited): raise RateLimited(f"RateLimited: {last}")
    raise RuntimeError(f"{type(last).__name__}: {last}")


def batched(url, calls):
    """Send `calls` in batches the endpoint accepts: 20 at a time, then 5 with a pause, then one by one.
    Some testnet RPCs reject or rate-limit batches (HTTP 413, 'requests limited to 15/sec', 'batch too large'). A rate limit is not a size problem: the pause grows and the size stays
    (a smaller batch is more calls), and once an endpoint has limited us the pace between calls is at least half a second for the rest of the run."""
    last = None
    for size, pause in ((CHUNK, 0.0), (5, 1.0), (1, 0.25)):
        try:
            out = []
            for i in range(0, len(calls), size):
                out += rpc(url, calls[i:i + size], tries=2)
                time.sleep(max(pause, 0.5 if url in _rate_seen else 0.0))
            return out
        except RateLimited: raise
        except Exception as e:  # noqa: BLE001 -- try a smaller batch before giving up
            last = e
    raise last


def read_evm_any(name, oracle, url, since_block=None):
    """read_evm on the oracle's node, then on its fallback nodes when that one limits or fails. With a fallback available the wait on the first node is cut to one pause (the next node is
    the better use of the time). The document says which node served it (`rpc`), and `read_via` when it was not the first."""
    urls = [url] + FALLBACK_RPC.get(url, []); last = None
    if len(urls) > 1: _rate_cap[url] = RATE_WAITS[0]
    for u in urls:
        try:
            doc = read_evm(name, oracle, u, since_block)
            if u != url: doc["read_via"] = u; print(f"{name}: {url} was not readable ({last}); read on {u}")
            return doc
        except Exception as e:  # noqa: BLE001 -- the next node, then the error of the last one
            last = e
    raise last


def call(oracle, data, tag="latest"):
    return ("eth_call", [{"to": oracle, "data": data}, tag])


def pin_on():
    """WATCH_PIN_BLOCK=1: the reads of the oracle's table (count, targets, scores, staleness) are asked AT the reference block of the run, so a third party can replay them exactly.
    Off by default (the reads stay at `latest`, the outputs are the same as before): some public nodes keep no old state or ignore the block tag (see `block_probe`)."""
    return os.environ.get("WATCH_PIN_BLOCK") == "1"


def probe_block(url, oracle, latest_count_hex):
    """Does this node answer for the block that is asked? The same call (trackedTargetsCount) is asked at block 1, where the oracle did not exist: a node that honours the tag
    answers empty or reverts, a node that ignores it repeats its answer for the head. Never raises: {"honoured": True|False|None, "probe_block": 1, "note"}."""
    try:
        old = rpc(url, [("eth_call", [{"to": oracle, "data": SEL_COUNT}, "0x1"])], tries=1)[0]
        h = block_honoured(latest_count_hex, old_answer=old)
    except Exception as e:  # noqa: BLE001 -- the error text says whether the node keeps no old state
        old, h = None, block_honoured(latest_count_hex, old_error=str(e)[:200])
    return {"honoured": h, "probe_block": 1, "note": ("the node answered for block 1 as it did for the head: it ignores the block tag" if h is False else
                                                      "the node answered differently at block 1: it honours the block tag" if h is True else "not told (no old state served, or no answer to compare)")}


def pad(addr):
    return addr.lower().replace("0x", "").rjust(64, "0")


def scan_start(prev_doc):
    """Where the next scan of the oracle's role events starts: the last block that was scanned successfully, not the block of the previous run. Before 2026-10-10 it was the previous run's
    block whether the scan had worked or not, so a window lost to an eth_getLogs failure (4 of 8 oracles on a cold run, rate limits and range caps) was never looked at again: a RoleGranted
    to an account the watch does not know, in that window, was missed for good."""
    if not isinstance(prev_doc, dict) or prev_doc.get("kind") != "evm": return None
    return prev_doc.get("self_scanned_to") or prev_doc.get("block")


def scanned_to(self_w, since, block):
    """The block up to which the role events have now been scanned: this run's block when the scan worked (or there was nothing before to scan: the first read is a baseline, the hasRole reads give
    the current state), the old start when it failed, so the next run covers the lost window too. A window too large to scan at all would never close, so it is given up, said so (`gap_blocks`) and the start moves on."""
    if since is None: return block
    if self_w.get("read"): return max(block, since)   # a fallback node that is behind (block < since) must not move the marker back: the next run would scan the same window again and log a RoleGranted twice
    if "window of" in str(self_w.get("error")): self_w["gap_blocks"] = block - since; return block
    return since


def self_watch(oracle, url, since_block, block):
    """The oracle's own authority since the previous run: role events on the contract, its code hash. An eth_getLogs failure is
    reported as unread, never as 'no event'."""
    import hashlib as _hl
    out = {"code_hash": None, "role_events": [], "from_block": since_block, "to_block": block, "read": False}
    try:
        code = rpc(url, [("eth_getCode", [oracle, "latest"])])[0]
        out["code_hash"] = _hl.sha256(bytes.fromhex(code[2:])).hexdigest() if code and code != "0x" else "no-code"
    except Exception as e:  # noqa: BLE001
        out["error"] = f"getCode: {str(e)[:120]}"; return out
    try:   # direct reads, no log range needed: does each known holder still hold admin / updater
        roles = {}
        for acct in KNOWN_HOLDERS:
            adm, upd = rpc(url, [call(oracle, SEL_HAS_ROLE + "0" * 64 + pad(acct)), call(oracle, SEL_HAS_ROLE + list(ROLE_NAMES)[1][2:] + pad(acct))])
            roles[acct] = {"admin": int(adm, 16) == 1, "updater": int(upd, 16) == 1}
        out["roles"] = roles
    except Exception as e:  # noqa: BLE001
        out["error"] = f"hasRole: {str(e)[:120]}"
    if since_block is None or since_block >= block:
        out["read"] = since_block is not None and "roles" in out; return out
    def scan(span):
        found, calls = [], 0
        for a in range(since_block + 1, block + 1, span):
            calls += 1
            if calls > LOG_CALL_CAP: raise RuntimeError(f"window of {block - since_block} blocks needs more than {LOG_CALL_CAP} calls at {span} blocks each")
            b = min(a + span - 1, block)
            for l in rpc(url, [("eth_getLogs", [{"address": oracle, "fromBlock": hex(a), "toBlock": hex(b), "topics": [[TOPIC_GRANTED, TOPIC_REVOKED]]}])])[0] or []:
                t = l.get("topics") or []
                if len(t) < 3: continue
                found.append({"event": "RoleGranted" if t[0].lower() == TOPIC_GRANTED else "RoleRevoked", "role": ROLE_NAMES.get(t[1].lower(), t[1]),
                              "account": "0x" + t[2][-40:], "sender": ("0x" + t[3][-40:]) if len(t) > 3 else None, "block": int(l["blockNumber"], 16), "tx": l.get("transactionHash")})
        return found
    last = None
    for span in LOG_SPANS:
        try:
            out["role_events"] = scan(span); out["read"] = "roles" in out; out["log_span"] = span; break
        except Exception as e:  # noqa: BLE001
            last = e
            if "window of" in str(e): break   # a smaller span would only need more calls
    else:
        pass
    if not out["read"]: out["error"] = (out.get("error") + "; " if out.get("error") else "") + f"getLogs: {str(last)[:120]}"
    return out


def read_evm(name, oracle, url, since_block=None):
    block = int(rpc(url, [("eth_blockNumber", [])])[0], 16)
    tag = hex(block) if pin_on() else "latest"
    count_hex, max_hex = rpc(url, [call(oracle, SEL_COUNT, tag), call(oracle, SEL_MAX, tag)])
    count, max_staleness = int(count_hex, 16), int(max_hex, 16)
    probe = probe_block(url, oracle, count_hex)
    self_w = self_watch(oracle, url, since_block, block)
    targets = ["0x" + r[-40:] for r in batched(url, [call(oracle, SEL_TARGET + f"{j:064x}", tag) for j in range(count)])]
    bad = [t for t in targets if not re.fullmatch(r"0x[0-9a-fA-F]{40}", t)]
    if bad: raise RuntimeError(f"{len(bad)} target(s) are not addresses (RPC answer not trusted): {bad[:2]}")
    rows = []
    if targets:
        res = batched(url, [call(oracle, SEL_SCORE + pad(t), tag) for t in targets] + [call(oracle, SEL_STALE + pad(t), tag) for t in targets])
        for i, (t, s, st) in enumerate(zip(targets, res[:len(targets)], res[len(targets):])):
            if len(s) < 2 + 64 * 8:
                raise ValueError(f"getScore returned {len(s)} chars for {t}")
            words = [s[2 + 64 * k: 2 + 64 * (k + 1)] for k in range(8)]
            rows.append({"index": i, "target": t, **{f: int(words[k], 16) for k, f in enumerate(FIELDS)},
                         "lastUpdated": int(words[6], 16), "methodologyHash": "0x" + (words[7] if re.fullmatch(r"[0-9a-fA-F]{64}", words[7]) else "0" * 64), "stale": int(st, 16) == 1})
    return {"name": name, "kind": "evm", "oracle": oracle, "rpc": url, "block": block, "maxStaleness": max_staleness,
            "readAt": int(time.time()), "targets": rows, "self": self_w, "self_scanned_to": scanned_to(self_w, since_block, block),
            "reference_block": block, "pinned_block": block if tag != "latest" else None, "read_tag": "pinned" if tag != "latest" else "latest", "block_probe": probe}   # the reference block of the run (always), the block the table was ASKED at (only when WATCH_PIN_BLOCK=1, else None: a read at `latest` is not a read at that block), the tag, and whether this node honours a block tag


def block_time_of(url, block):
    """The time of `block` as the chain says it (unix seconds), or None when it could not be read: a failed read skips the date checks (F1), it never raises and never counts as zero."""
    try:
        b = rpc(url, [("eth_getBlockByNumber", [hex(block), False])], tries=1)[0]
        return int(b["timestamp"], 16) if isinstance(b, dict) and b.get("timestamp") else None
    except Exception:  # noqa: BLE001
        return None


def fixed_scorer_targets():
    """The targets whose scorer reads a configuration and publishes constants (data/scorer_pins.json, lower case), or an empty set when the file is missing or unreadable."""
    try:
        return {a.lower() for pin in json.load(open(os.path.join(ROOT, "data", "scorer_pins.json")))["pins"] for a in pin.get("targets", [])}
    except Exception:  # noqa: BLE001
        return set()


def _sol_rpc(url, method, params):
    req = urllib.request.Request(url, data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode(), headers={"content-type": "application/json", "user-agent": "watch_run/1"})
    with urllib.request.urlopen(req, timeout=25) as r: out = json.load(r)
    if "error" in out: raise RuntimeError(str(out["error"])[:100])
    return out["result"]


def _post_json(url, body):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"content-type": "application/json", "user-agent": "watch_run/1"})
    with urllib.request.urlopen(req, timeout=25) as r: return json.load(r)


NETWORKS_BUDGET_S = 300   # the network reads are an extra of the run: once they have taken this many seconds IN TOTAL (the time of the oracle reads is not counted), the next ones are written as unplaced with that cause
_NETWORKS_SPENT = [0.0]   # seconds spent inside add_networks since begin_networks_pass()


def begin_networks_pass():
    """called once at the start of a pass of the Watch: the budget of the network reads starts again"""
    _NETWORKS_SPENT[0] = 0.0


def add_networks(name, doc):
    """The network of the oracle and of each target, with the block of the target network that was read. A failed read is written as a cause (never a zero, never a default
    "mainnet": a network name is written only once its chain id was read) and never stops the run. The record is marked `networks_version`: from then on the schema requires the networks."""
    t0 = time.time()
    try:
        if _NETWORKS_SPENT[0] >= NETWORKS_BUDGET_S:
            raise RuntimeError("the time budget of %d s for the network reads is spent" % NETWORKS_BUDGET_S)
        if doc.get("kind") == "solana":
            mod, per = target_networks.solana_fields(doc["targets"], _sol_rpc)
            try:
                og = _sol_rpc(doc["rpc"], "getGenesisHash", []); mod["oracle_genesis"] = og
                if og == target_networks.GENESIS[target_networks.SOLANA[0]]: mod["oracle_network"] = target_networks.SOLANA[0]
                else: mod["oracle_chain_read_error"] = "the oracle RPC answers genesis %s, expected devnet" % str(og)[:8]
            except Exception as e: mod["oracle_chain_read_error"] = str(e)[:100]  # noqa: BLE001
        else:
            mod, per = target_networks.evm_fields(name, doc["rpc"], doc["targets"], lambda url, calls: rpc(url, calls, tries=1), batched, _post_json)
        target_networks.apply(doc, mod, per)
    except Exception as e:  # noqa: BLE001
        doc["target_read_error"] = "networks could not be obtained: %s" % str(e)[:160]
        doc.setdefault("oracle_network", target_networks.UNREAD); doc.setdefault("target_network", target_networks.UNREAD)
        for t in doc.get("targets", []): t.setdefault("target_network", target_networks.UNREAD)
    finally:
        _NETWORKS_SPENT[0] += time.time() - t0
    doc["networks_version"] = 1
    return doc


def read_solana():
    reg = solana_oracle_reader.read_oracle()
    now = int(time.time())
    rows = [{"index": i, **s, "stale": now - s["lastUpdated"] > reg["max_staleness"]} for i, s in enumerate(reg["scores"])]
    return {"name": "Solana (Devnet)", "kind": "solana", "oracle": solana_oracle_reader.PROGRAM_ID, "rpc": solana_oracle_reader.DEVNET_RPC,
            "block": None, "maxStaleness": reg["max_staleness"], "readAt": now, "targets": rows}


def labels():
    try:
        d = json.load(open(os.path.join(ROOT, "api", "scores.json")))
        return {s["target"].lower(): s["label"] for s in d["scores"]}
    except Exception:  # noqa: BLE001
        return {}


def iso(ts):
    return datetime.datetime.fromtimestamp(ts, datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def write_feed(events):
    """Atom feed of the last 60 moves and alarms, newest first."""
    items = events[-60:][::-1]
    updated = items[0]["run_utc"] if items else iso(time.time())
    out = ['<?xml version="1.0" encoding="utf-8"?>', '<feed xmlns="http://www.w3.org/2005/Atom">',
           "<title>Authority Risk Oracle: what moved</title>", f'<link href="{PAGE}"/>', f'<link rel="self" href="{RAW}feed.xml"/>',
           f"<id>{PAGE}feed</id>", f"<updated>{updated}</updated>", "<author><name>RealSpap</name></author>"]
    seen_ids = {}
    for e in items:
        k = e.get("kind")   # move (this watch), alarm (this watch), admin_change / admin_grew (the independent reader, appended after the run): only a move has field/before/after
        if k == "move": title = f"{e['oracle']}: {e['label']} added at {e['after']}" if e["before"] is None else f"{e['oracle']}: {e['label']} {e['field']} {e['before']} to {e['after']}"
        elif k == "admin_change": title = f"ADMIN CHANGED {e.get('oracle')} {str(e.get('target'))[:10]}: {e.get('text')}"
        else: title = ("ALARM " if k == "alarm" else "") + str(e.get("text"))
        out += ["<entry>", f"<title>{escape(title)}</title>",
                f'<link href="{PAGE}#chain=all&amp;q={escape(e.get("target") or "")}"/>',
                f"<id>{PAGE}event/{e['run_utc']}/{(lambda h: (seen_ids.__setitem__(h, seen_ids.get(h, 0) + 1), h + ('' if seen_ids[h] == 1 else '/' + str(seen_ids[h])))[1])(hashlib.sha1(json.dumps(e, sort_keys=True).encode()).hexdigest()[:12])}</id>", f"<updated>{e['run_utc']}</updated>",
                f"<summary>{escape(title)}. Read-only watch run of {e['run_utc']}.</summary>", "</entry>"]
    out.append("</feed>")
    open(os.path.join(WATCH, "feed.xml"), "w").write("\n".join(out) + "\n")


def restore_dropped_targets(current, prev_by_target):
    """A smaller list than the last run is not trusted (the contract cannot remove a target): the targets that are missing from the answer come back from the last run, unchanged, in their original order."""
    have = {t["target"] for t in current}
    back = [dict(p) for k, p in prev_by_target.items() if k not in have]
    return sorted(list(current) + back, key=lambda t: t.get("index", 0))


# 2026.10.5 proposal: what a 100 means, declared per target (scripts/export_dimension_basis.py writes the file from scripts/lib/dimension_basis.py).
# Fail closed: a missing file, a missing declaration, or a declaration the published value contradicts gives "not_computed", never "not_applicable" and never no field.
# The Watch shows the DECLARED state. A score run that could not read something downgrades it in api/scores.json only (the Watch has no notes to read).
_SLUG_ECO = {"robinhood-chain": "robinhood-chain", "ethereum-l1-sepolia": "ethereum-l1", "arbitrum-sepolia": "arbitrum-ecosystem", "base-sepolia": "base-ecosystem", "tempo-moderato": "tempo",
             "plasma": "plasma-ecosystem", "monad": "monad", "hyperliquid-hyperevm": "hyperliquid", "solana-devnet": "solana"}
_BASIS_STATES = ("computed", "not_computed", "not_applicable")
_NO_DECLARATION = "No declaration for this target: treated as not scored, never as not applicable."
_WALK = "Scored as the weakest of the material price paths one hop upstream (rule of 2026-10-04)."
_FLOOR = "A material price path could not be read in this run; the number is a floor, not a finding."
_OUTDATED = "The declaration for this target says one thing and the published value says another: treated as not scored until the declaration is reviewed."


def load_basis():
    try:
        return json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "dimension_basis.json"), encoding="utf-8")).get("targets", {})
    except (OSError, ValueError, AttributeError):
        return {}


def basis_fields(slug, t, basis):
    d = basis.get("%s:%s" % (_SLUG_ECO.get(slug, slug), t["target"].lower() if t["target"].startswith("0x") else t["target"])) or {}
    out = {}
    for dim in ("oracleAuthority", "crossExposure"):
        b, r, v = d.get(dim + "Basis"), d.get(dim + "Reason"), t.get(dim + "Score")
        if b not in _BASIS_STATES or not isinstance(r, str) or not r: b, r = "not_computed", _NO_DECLARATION
        elif isinstance(v, (int, float)) and v < 100 and dim == "oracleAuthority" and d.get(dim + "ReasonCode") == "no_allocation_today": b, r = "computed", _WALK      # money arrived since the declaration was written
        elif isinstance(v, (int, float)) and v >= 20 and dim == "oracleAuthority" and d.get(dim + "ReasonCode") == "price_walk_partial": b, r = "not_computed", _FLOOR      # back at the floor of 20: a placeholder again
        elif isinstance(v, (int, float)) and v < 100 and ((dim == "oracleAuthority" and b == "not_applicable") or (dim == "crossExposure" and b != "computed")): b, r = "not_computed", _OUTDATED
        out[dim + "Basis"], out[dim + "Reason"] = b, r
    return out


def main():
    os.makedirs(os.path.join(WATCH, "scores"), exist_ok=True)
    BASIS = load_basis()
    now = datetime.datetime.now(datetime.timezone.utc)
    run_utc = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    names = labels()
    summary, movers, alerts, unread = [], [], [], []
    RETIRED, retired_err = retired_targets.load()   # a file that cannot be read retires nothing (everything is counted as before) and is an alarm, never a silent fallback
    if retired_err: alerts.append("retired targets file not read, nothing is treated as retired this run (%s)" % retired_err)
    retired_all = []
    prev_latest = {}
    try:
        prev_latest = json.load(open(os.path.join(WATCH, "latest.json")))
    except Exception:  # noqa: BLE001
        pass
    prev_ok = {o["slug"] for o in prev_latest.get("oracles", []) if o.get("read_ok")}

    begin_networks_pass()   # budget of the network reads (add_networks)
    readers = [(name, lambda since, n=name, o=oracle, u=url: read_evm_any(n, o, u, since)) for name, oracle, url in ORACLES] + [("Solana (Devnet)", lambda since: read_solana())]
    for name, reader in readers:
        s = slug(name)
        path = os.path.join(WATCH, "scores", s + ".json")
        prev_doc = {}
        try: prev_doc = json.load(open(path))
        except Exception: pass  # noqa: BLE001
        try:
            cur = reader(scan_start(prev_doc))
        except Exception as e:  # noqa: BLE001 -- an unread oracle is reported, never counted as empty
            err = re.sub(r"[^A-Za-z0-9 :._/()-]", " ", f"{type(e).__name__}: {str(e)[:160]}")   # plain text only: it ends up in a public issue
            unread.append(name)
            summary.append({"name": name, "slug": s, "read_ok": False, "error": err})
            if s in prev_ok:
                alerts.append(f"{name}: could not be read this run (it answered last time): {err}")
            continue
        prev = None
        try:
            prev = {t["target"]: t for t in json.load(open(path))["targets"]}
        except Exception:  # noqa: BLE001
            pass
        if cur.get("kind") == "evm":   # a hole in the scan of the oracle's own role events is an alarm; the block time lets the dates the updater supplies be checked against the chain
            cur["block_time"] = block_time_of(cur["rpc"], cur["block"])
            cur["scan_stalled_runs"], extra = scan_progress(prev_doc, cur); alerts.extend(extra)
        if prev is not None and len(cur["targets"]) < len(prev):   # the contract cannot remove a target: a smaller list is an RPC answer not to trust
            alerts.append(f"{name}: {len(cur['targets'])} targets read, {len(prev)} last run: the oracle cannot remove a target, this RPC answer is not trusted")
            cur["targets"] = restore_dropped_targets(cur["targets"], prev)   # QA 11/10: the short list used to be written as it was, and the targets that came back next run were announced as new ones, for ever in the chained log
        add_networks(name, cur)   # oracle network (test) and target network (mainnet), read; after the dropped targets came back, so that every target of the file carries its network
        ret_here, woken = retired_targets.apply(s, cur["targets"], RETIRED)   # retired: kept out of the stale count and the methodology hashes in use, listed apart; woken: written again, counted as a normal target
        for t in woken: alerts.append(f"{name}: retired target {t['target'][:6]}…{t['target'][-4:]} was written again (last update {iso(t['lastUpdated'])}, retired at {iso(RETIRED[s + ':' + t['target'].lower()]['last_update_at_retirement'])}): counted as a normal target until data/retired_targets.json is edited")
        retired_all += retired_targets.listing(s, ret_here, RETIRED)
        stale = [t for t in cur["targets"] if t["stale"] and not t.get("retired")]
        sw = cur.get("self") or {}
        if sw:
            for ev in sw.get("role_events", []):
                alerts.append(f"{name}: ORACLE {ev['event']} {ev['role']} {'to' if ev['event'] == 'RoleGranted' else 'from'} {ev['account']} at block {ev['block']} (tx {ev['tx']})")
            ps = prev_doc.get("self") or {}
            if ps.get("code_hash") and sw.get("code_hash") and ps["code_hash"] != sw["code_hash"]:
                alerts.append(f"{name}: ORACLE code changed (sha256 {ps['code_hash'][:12]} -> {sw['code_hash'][:12]})")
            for acct, now_r in (sw.get("roles") or {}).items():   # a role seen last run and gone, or new, is an alarm even where the logs could not be read
                was = ((prev_doc.get("self") or {}).get("roles") or {}).get(acct)
                if was is not None and was != now_r:
                    alerts.append(f"{name}: ORACLE roles of {acct} ({KNOWN_HOLDERS.get(acct, '')}) changed: admin {was.get('admin')} -> {now_r['admin']}, updater {was.get('updater')} -> {now_r['updater']}")
            if prev_doc.get("maxStaleness") is not None and prev_doc["maxStaleness"] != cur.get("maxStaleness"):
                alerts.append(f"{name}: ORACLE maxStaleness changed {prev_doc['maxStaleness']} -> {cur['maxStaleness']}")
        if cur.get("kind") == "evm":   # F1 (a date in the future) and F2 (a date that went back); the updater supplies lastUpdated and the contract does not check it
            lu_alerts, lu_skip = last_updated_alerts(name, cur["targets"], prev, cur.get("block_time"), label_of=lambda t_: names.get(t_["target"].lower(), t_["target"][:6] + "…" + t_["target"][-4:]), already_future=prev_doc.get("future_dated") or [])
            cur["future_dated"] = future_dated(cur["targets"], cur.get("block_time"))
            alerts.extend(lu_alerts); cur["lastupdated_check"] = lu_skip or "ok"
        newest_push = max((x["lastUpdated"] for x in cur["targets"] if isinstance(x.get("lastUpdated"), int)), default=None)
        fixed_set = fixed_scorer_targets()
        for t in cur["targets"]:
            label = names.get(t["target"].lower(), t["target"][:6] + "…" + t["target"][-4:])
            p = prev.get(t["target"]) if prev else None
            t["evaluation"] = evaluation_of(t.get("lastUpdated"), newest_push, str(t["target"]).lower() in fixed_set)   # recomputed in the newest pass, kept from an older one, or fixed by decision
            t["previousComposite"] = p["compositeScore"] if p else None
            t["previousRun"] = prev_latest.get("run_utc") if p else None
            t.update(basis_fields(s, t, BASIS))
            if p is None:
                if prev is not None:
                    movers.append({"oracle": name, "target": t["target"], "label": label, "field": "new", "before": None, "after": t["compositeScore"]})
                    if t["compositeScore"] < NEW_TARGET_ALERT_CEILING:
                        alerts.append(f"{name}: new target {label} first published at composite {t['compositeScore']}")
                continue
            for f in FIELDS:
                if p.get(f) != t[f]:
                    movers.append({"oracle": name, "target": t["target"], "label": label, "field": f, "before": p.get(f), "after": t[f]})
            if p.get("compositeScore", 0) - t["compositeScore"] >= DROP_THRESHOLD:
                alerts.append(f"{name}: {label} composite {p['compositeScore']} -> {t['compositeScore']}")
            if t["stale"] and not p.get("stale") and not t.get("retired"):
                alerts.append(f"{name}: {label} turned stale (last update {iso(t['lastUpdated'])})")
        last_push = max((t["lastUpdated"] for t in cur["targets"]), default=0)
        summary.append({"name": name, "slug": s, "kind": cur["kind"], "oracle": cur["oracle"], "read_ok": True, "block": cur["block"],
                        "targets": len(cur["targets"]), "stale": len(stale), "retired": len(ret_here), "lastUpdated": last_push, "maxStaleness": cur["maxStaleness"],
                        "freshness": freshness_record(cur.get("readAt"), cur.get("block"), cur.get("block_time"), cur["targets"]),   # when the Watch read it, the block and its time, the newest and the oldest push, side by side
                        "self_watch": ({"read": bool(sw.get("read")), "role_events": len(sw.get("role_events", [])), "code_hash": (sw.get("code_hash") or "")[:16], "roles": sw.get("roles"), "error": sw.get("error")} if sw else None)})
        _dump_json(cur, path, indent=1)
        # one shields.io endpoint per target, so a protocol can show its own score in its README
        bdir = os.path.join(WATCH, "badge", s)
        os.makedirs(bdir, exist_ok=True)
        for t in cur["targets"]:
            v = t["compositeScore"]
            _dump_json({"schemaVersion": 1, "label": "authority risk", "message": f"{v}/100" + (" (retired)" if t.get("retired") else " (stale)" if t["stale"] else ""),
                       "color": "red" if v < 20 else "orange" if v < 40 else "yellow" if v < 60 else "green" if v < 80 else "brightgreen"}, os.path.join(bdir, (t["target"].lower() if str(t["target"]).startswith("0x") else t["target"]) + ".json"))   # a Solana id keeps its case

    latest = {
        "run_utc": run_utc, "previous_run_utc": prev_latest.get("run_utc"), "schedule": "every 6 hours (GitHub Actions, cron 17 */6 * * *)",
        "oracles": summary, "total_targets": sum(o.get("targets", 0) for o in summary), "stale_total": sum(o.get("stale", 0) for o in summary),
        "retired_total": len(retired_all), "retired": retired_all,   # kept apart on purpose (data/retired_targets.json): counted in total_targets, not in stale_total; names, notes and dates are published
        "movers": movers, "alerts": alerts, "unread": unread,
        "note": "The Zcash commitments are verified by the dashboard itself. An oracle in `unread` has unknown targets, not zero.",
    }
    if run_id.current(): latest["run_id"] = run_id.current()
    _dump_json(latest, os.path.join(WATCH, "latest.json"), indent=1)
    with open(os.path.join(WATCH, "history.jsonl"), "a") as f:
        f.write(json.dumps({"run_utc": run_utc, "targets": latest["total_targets"], "stale": latest["stale_total"], "retired": latest["retired_total"],
                            "movers": len(movers), "alerts": len(alerts), "unread": len(unread), "unread_oracles": unread}) + "\n")   # names since 2026-10-10: the dashboard shows each oracle's read reliability over 7 days
    events_path = os.path.join(WATCH, "events.jsonl")
    # Hash-chained since 2026-10-10: every line carries `seq` and `prev`, the sha256 of the previous line's exact text ("" for the
    # first). A line edited, removed or inserted after the fact breaks every hash after it: scripts/verify_chain.py and the
    # dashboard both check the whole chain. Lines written before the chain (no `prev`) are kept as they are and reported as such.
    import hashlib as _hl
    last_line, seq = "", 0
    if os.path.exists(events_path):
        for l in open(events_path):
            if l.strip(): last_line, seq = l.rstrip("\n"), seq + 1
    prev = _hl.sha256(last_line.encode()).hexdigest() if last_line else ""
    if last_line and not open(events_path, "rb").read().endswith(b"\n"):   # a file cut without its final newline would glue the next line to the last one and break the chain
        open(events_path, "a").write("\n")
    with open(events_path, "a") as f:
        for e in [{"run_utc": run_utc, "kind": "move", **m} for m in movers] + [{"run_utc": run_utc, "kind": "alarm", "text": a} for a in alerts]:
            seq += 1
            line = json.dumps({**e, "seq": seq, "prev": prev})
            f.write(line + "\n"); prev = _hl.sha256(line.encode()).hexdigest()
    events = []
    for l in open(events_path):
        if not l.strip(): continue
        try: events.append(json.loads(l))
        except ValueError: continue   # one corrupt line must not silence the whole run
    write_feed(events)
    read = len(summary) - len(unread)
    _dump_json({"schemaVersion": 1, "label": "authority risk oracle",
               "message": f"{latest['total_targets']} targets, {latest['stale_total']} stale, " + (f"{latest['retired_total']} retired, " if latest["retired_total"] else "") + f"{len(alerts)} alarm{'s' if len(alerts) != 1 else ''}",
               "color": "red" if alerts else "orange" if latest["stale_total"] or unread else "brightgreen"}, os.path.join(WATCH, "badge.json"), indent=1)
    alarm = os.path.join(WATCH, "alarm.md")
    if alerts:
        with open(alarm, "w") as f:
            f.write(f"# Alarm, {run_utc}\n\n" + "".join(f"- {a}\n" for a in alerts)
                    + f"\nRead-only watch of the deployed oracles (`scripts/watch_run.py`). Details: `watch/latest.json`, page: {PAGE}\n")
    elif os.path.exists(alarm):
        os.remove(alarm)
    print(f"{latest['total_targets']} targets read on {read} of {len(readers)} oracles, {latest['stale_total']} stale, {latest['retired_total']} retired, "
          f"{len(movers)} moves, {len(alerts)} alerts, unread: {', '.join(unread) or 'none'}")
    for a in alerts:
        print("  ALARM", a)
    sys.exit(2 if alerts else 1 if unread else 0)


if __name__ == "__main__":
    if "--feed-only" in sys.argv:   # rebuild feed.xml from events.jsonl after other scripts appended to it (the independent reader's findings), no RPC
        evs = []
        for l in open(os.path.join(WATCH, "events.jsonl")) if os.path.exists(os.path.join(WATCH, "events.jsonl")) else []:
            try: evs.append(json.loads(l))
            except ValueError: continue
        write_feed(evs); print("feed.xml rebuilt from %d event(s)" % len(evs)); sys.exit(0)
    main()
