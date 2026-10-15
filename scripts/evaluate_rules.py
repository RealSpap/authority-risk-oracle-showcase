#!/usr/bin/env python3
"""Evaluate rules.json against the latest watch files and write watch/alerts.json: which rules fire on which targets right now
(active), and a history of every firing with the first and last time it was seen. Sends the new medium or high ones to Telegram and
Discord when the repository secrets are set; otherwise it only writes the file. Conditions are tiny boolean expressions over a fixed
set of fields, parsed with Python's ast and evaluated without any builtin, so a forked rules.json cannot run code. The timelock queue
(watch/pending_ops.json) gives three more fields, so a rule can fire BEFORE a change applies: queued_ops, ready_in_hours, executed_14d;
each such alert carries its evidence (timelock, tx, selector, when it executes).

    python3 scripts/evaluate_rules.py --rules rules.json --scores watch/scores --latest watch/latest.json --tvl watch/tvl.json --out watch/alerts.json
"""
import argparse, ast, glob, hashlib, hmac, json, os, sys, time, urllib.request
from watch_location import RAW  # the feeds live on the watch-data branch
from lib.fresh_ops import fresh_enough  # one filter for the queue everywhere: an operation executable for more than 7 days is not listed
from pending_ics import SELNAMES  # the same small selector-to-name table as the calendar and the page: an alert names the queued function when the event did not

def _dump_json(obj, path, indent=None):
    """Write the file only once the whole object is serialised: a crash half-way never leaves a truncated JSON behind
    (the previous run's file stays), and a reader never sees a half-written one."""
    import json as _j, os as _o
    tmp = path + ".tmp"
    with open(tmp, "w") as f: _j.dump(obj, f, indent=indent)
    _o.replace(tmp, path)


WATCH_SLUGS = {"robinhood-chain": "robinhood", "ethereum-l1-sepolia": "ethereum-l1", "arbitrum-sepolia": "arbitrum", "base-sepolia": "base",
               "plasma": "plasma", "tempo-moderato": "tempo", "monad": "monad", "hyperliquid-hyperevm": "hyperliquid", "solana-devnet": "solana"}
LABEL = {"robinhood": "Robinhood Chain", "ethereum-l1": "Ethereum L1", "arbitrum": "Arbitrum", "base": "Base", "plasma": "Plasma", "tempo": "Tempo", "monad": "Monad", "hyperliquid": "Hyperliquid", "solana": "Solana"}
SEV = {"info": 0, "medium": 1, "high": 2}
PENDING_CHAIN = {"ethereum": "ethereum-l1", "arbitrum": "arbitrum", "base": "base", "robinhood": "robinhood", "plasma": "plasma", "tempo": "tempo", "monad": "monad", "hyperliquid": "hyperliquid", "solana": "solana"}  # chain names of pending_ops.json -> our keys (solana: the Squads proposal queues, since 2026-10-10)
OPS = {ast.Lt: lambda a, b: a < b, ast.LtE: lambda a, b: a <= b, ast.Gt: lambda a, b: a > b, ast.GtE: lambda a, b: a >= b, ast.Eq: lambda a, b: a == b, ast.NotEq: lambda a, b: a != b}


def norm(a):
    """An EVM address compares lowercase; a Solana program id is base58 and keeps its case."""
    a = str(a); return a.lower() if a.startswith("0x") else a


def lower_keys(d):
    """The keys of a hand-entered file (data/tvl_scope.json, <chain>:<address>) in the form every lookup uses. The documents say 'lower case', but an address pasted from an explorer
    is checksummed (mixed case) and was silently ignored: the entry never matched, the money rule kept firing on a contract marked retired."""
    out = {}
    for k, v in (d or {}).items():
        chain, _, addr = str(k).partition(":"); out[chain.lower() + ":" + norm(addr)] = v
    return out

def ev(node, env):
    if isinstance(node, ast.Expression): return ev(node.body, env)
    if isinstance(node, ast.BoolOp): vals = [ev(v, env) for v in node.values]; return all(vals) if isinstance(node.op, ast.And) else any(vals)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not): return not ev(node.operand, env)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub): return -ev(node.operand, env)
    if isinstance(node, ast.Compare):
        left = ev(node.left, env)
        for op, comp in zip(node.ops, node.comparators):
            right = ev(comp, env)
            if type(op) not in OPS: raise ValueError("operator not allowed")
            if left is None or right is None:
                if isinstance(op, (ast.Eq, ast.NotEq)): ok = OPS[type(op)](left, right)
                else: return False
            else: ok = OPS[type(op)](left, right)
            if not ok: return False
            left = right
        return True
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub)):
        a, b = ev(node.left, env), ev(node.right, env)
        if a is None or b is None: return None
        return a + b if isinstance(node.op, ast.Add) else a - b
    if isinstance(node, ast.Constant): return node.value
    if isinstance(node, ast.Name):
        if node.id in env: return env[node.id]
        if node.id in ("null", "none", "None"): return None
        if node.id in ("true", "True"): return True
        if node.id in ("false", "False"): return False
        raise ValueError("unknown field " + node.id)
    raise ValueError("expression not allowed: " + type(node).__name__)

def post_json(url, payload):
    try:
        req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={"content-type": "application/json"}, method="POST")
        urllib.request.urlopen(req, timeout=20).read(); return True
    except Exception: return False

# daily mode of the public Telegram channel (TELEGRAM_MODE=daily, off by default): one summary a day, plus these critical alerts live. Everything else (roles, signers, thresholds, delays, per-protocol detail) goes to the summary and to the paid offer.
READY_FRESH_DAYS = 7   # a queued change ready for longer than this is not listed (lib/fresh_ops.py)
LIVE_ON_TELEGRAM = ("the contract's own balance fell by 70% or more", "the contract has been paused since the previous run", "an upgrade was executed")


def impl_verified_by_address(path):
    """watch/impl_sources.json (by_target: "chain:address" -> {verified}) reduced to address -> verified; a missing or unreadable file gives {}, which counts every upgrade as not verified (the cautious side: it is sent live)."""
    try: bt = (json.load(open(path, encoding="utf-8")) or {}).get("by_target") or {}
    except (OSError, ValueError): return {}
    return {str(k).split(":", 1)[-1].lower(): (v or {}).get("verified") for k, v in bt.items()}


def live_on_telegram(x, impl_sources=None):
    """True for an alert that the public channel still carries in real time in daily mode: a drain (70% or more of the contract's own balance), a pause, and an executed upgrade whose new code is NOT verified
    (an upgrade whose source is verified waits for the daily summary; an unknown state counts as not verified). Only high alerts: a rule renamed or downgraded drops out of the live set instead of leaking into it."""
    if x.get("severity") != "high" or not str(x.get("rule", "")).startswith(LIVE_ON_TELEGRAM): return False
    if str(x["rule"]).startswith("an upgrade was executed"):
        return (impl_sources or {}).get(norm(x.get("target", ""))) is not True      # impl_sources: lower-cased address -> verified (True / False / None)
    return True


def signed_webhook(url, secret, payload, now=None):
    """A webhook for a machine (12/10/2026): the JSON body is signed with HMAC-SHA256 over "<timestamp>.<body>" with a secret only the receiver and the workflow know, so the receiver can check that the alert is ours and
    refuse a replay (the timestamp is in the signature). Headers: X-ARO-Timestamp, X-ARO-Signature: sha256=<hex>. Plain http is refused: the body and the signature must not cross the network in the clear.
    Returns (headers, body) when it can be sent, None for a URL that is not https."""
    if not url.startswith("https://") or not secret: return None
    body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(); ts = str(int(time.time() if now is None else now))
    return {"content-type": "application/json", "x-aro-timestamp": ts, "x-aro-signature": "sha256=" + hmac.new(secret.encode(), ts.encode() + b"." + body, hashlib.sha256).hexdigest(), "user-agent": "authority-risk-oracle-webhook/1"}, body


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k): return None          # a 30x answer is a failure: following it could send the signed body to a plain-http address


def post_signed(url, secret, payload):
    r = signed_webhook(url, secret, payload)
    if r is None: return False
    try:
        urllib.request.build_opener(_NoRedirect).open(urllib.request.Request(url, data=r[1], headers=r[0], method="POST"), timeout=20).read(); return True
    except Exception: return False


def bal_text(b):
    """The numbers behind a balance alert, in words: the rule says 30% or more, this says how much (since 2026-10-10)."""
    f = lambda v: ("%.1fM" % (v / 1e6)) if v >= 1e6 else (("%.1fk" % (v / 1e3)) if v >= 1e3 else "%.0f" % v)
    return "%s balance from %s to %s (%+.1f%%) since %s" % (b.get("symbol") or "asset", f(b["from"]), f(b["to"]), b["change_pct"], str(b.get("since") or "the previous run").replace("T", " ")[:16] + (" UTC" if b.get("since") else ""))


def pause_text(p):
    """A pause flip in words (since 2026-10-10): what the contract answers now and what it answered at the previous run."""
    return "paused() now answers %s, it answered %s at the previous run%s" % ("true" if p.get("change") == "paused" else "false", "false" if p.get("change") == "paused" else "true", (" (" + str(p["previous_run"]).replace("T", " ")[:16] + " UTC)") if p.get("previous_run") else "")


def detail_text(x):
    """The numbers or the fact behind an alert that is not a queued operation, for the channels people read (notification, feeds)."""
    return bal_text(x["balance"]) if x.get("balance") else (pause_text(x["pause"]) if x.get("pause") else (side_text(x["side_role"]) if x.get("side_role") else (safe_text(x["safe_wake"]) if x.get("safe_wake") else "")))


def short_safe(key):
    """'arbitrum:0x…' -> '0xabcd…ef12': the Safe's address shortened, as every holder in a message people read."""
    a = str(key).split(":", 1)[-1]
    return a[:6] + "…" + a[-4:] if len(a) > 14 else a


def safe_text(w):
    """An admin Safe waking up, in words (since 2026-10-10): who, how many transactions, after how long without one."""
    return "the Safe %s that governs this contract executed %s transaction%s after %s days observed idle%s" % (w.get("safe"), w.get("delta"), "" if w.get("delta") == 1 else "s", w.get("idle_days"), (" (previous run " + str(w["previous_run"]).replace("T", " ")[:16] + " UTC)") if w.get("previous_run") else "")


KIND_WORDS = {"eoa": "a plain key", "safe": "a Safe", "timelock": "a timelock", "contract": "a contract", "unread": "not read"}


def side_text(changes):
    """A secondary role changing hands, in words (since 2026-10-10): the getter that answered, what held it, what holds it now."""
    out = []
    for c in changes[:3]:
        if c.get("change") == "announced":   # a vault announces a new guardian or a new delay before it applies (pendingGuardian() / pendingTimelock())
            at = (" from " + time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(int(c["valid_at"]))) + (" (already executable by anyone: the waiting time is over)" if int(c["valid_at"]) <= time.time() else "")) if c.get("valid_at") else ""
            if c.get("role") == "pendingTimelock()":
                f_ = lambda x: ("%s h" % (int(x) // 3600)) if x is not None else "an unread delay"  # noqa: E731
                out.append("the delay is announced to go from %s to %s%s%s" % (f_(c.get("from_seconds")), f_(c.get("to_seconds")), " (a SHORTER delay: less time to react)" if c.get("shorter") else "", at))
            else: out.append("a new guardian is announced: %s%s takes the role%s" % (KIND_WORDS.get(c.get("to_kind"), "nobody" if not c.get("to") else "a holder"), (" (" + str(c["to"]) + ")") if c.get("to") else "", at))
            continue
        w = lambda k, h: ("%s%s" % (KIND_WORDS.get(k, str(k)), (" (" + str(h) + ")") if h else "")) if k else "nobody"  # noqa: E731
        out.append("%s %s: from %s to %s" % (c.get("role"), {"changed": "changed hands", "added": "was set", "cleared": "was cleared"}.get(c.get("change"), "changed"), w(c.get("from_kind"), c.get("from")), w(c.get("to_kind"), c.get("to"))))
    return "; ".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rules", default="rules.json"); ap.add_argument("--scores", default="watch/scores"); ap.add_argument("--latest", default="watch/latest.json")
    ap.add_argument("--tvl", default="watch/tvl.json"); ap.add_argument("--pause", default="watch/pause_state.json", help="pause state of the contracts (pause_state.py)"); ap.add_argument("--side", default="watch/side_roles.json", help="secondary roles and their changes (side_roles.py)"); ap.add_argument("--safe", default="watch/safe_activity.json", help="admin Safes that woke after an idle stretch (safe_activity.py)"); ap.add_argument("--held", default="watch/held_assets.json", help="what each contract holds by its own account (held_assets.py): the money of a vault DefiLlama lists no protocol for"); ap.add_argument("--pending", default="watch/pending_ops.json"); ap.add_argument("--prev", default="watch/prev"); ap.add_argument("--second-opinion", default="watch/second_opinion.json"); ap.add_argument("--disputes", default="watch/disputes.json"); ap.add_argument("--out", default="watch/alerts.json"); ap.add_argument("--no-send", action="store_true")
    a = ap.parse_args()
    rules = json.load(open(a.rules)); compiled = [(r, ast.parse(r["when"], mode="eval")) for r in rules["rules"]]
    tvl = json.load(open(a.tvl)).get("matched", {}) if os.path.exists(a.tvl) else {}
    scoped_ = set()
    try:   # data/tvl_scope.json (since 2026-10-10): a retired or peripheral contract carries none of its protocol's TVL, so no money-based rule fires on it
        for ka_, v_ in lower_keys(json.load(open(os.path.join(os.path.dirname(a.rules) or ".", "data", "tvl_scope.json"))).get("targets")).items():   # rules.json sits at the repository root, data/ beside it
            if v_.get("scope") in ("retired", "peripheral"): scoped_.add(ka_); tvl = dict(tvl); tvl.pop(ka_, None)
    except Exception: pass  # noqa: BLE001
    side_changes = {}
    try:
        for c_ in json.load(open(a.side)).get("changes") or []: side_changes.setdefault(c_["target"], []).append(c_)   # a curator, guardian or pauser that changed hands since the previous run
    except Exception: pass  # noqa: BLE001
    safe_woke = {}
    try:
        for c_ in json.load(open(a.safe)).get("changes") or []:   # an admin Safe whose nonce moved after an idle stretch: each contract it governs carries the wake (stale records never fire, they are not in changes)
            if c_.get("woke"):
                for tk_ in c_.get("governs") or []: safe_woke.setdefault(tk_, c_)
    except Exception: pass  # noqa: BLE001
    try: pause_all = json.load(open(a.pause)).get("by_target") or {}   # a flip of paused() / isPaused() since the previous run (stale records never fire)
    except Exception: pause_all = {}  # noqa: BLE001
    try: held_all = json.load(open(a.held)).get("by_target") or {}   # the balance moves too (amount_change_pct): a contract that loses most of its assets between two runs
    except Exception: held_all = {}  # noqa: BLE001
    try:   # watch/held_assets.json (since 2026-10-10): a vault DefiLlama lists no protocol for carries what it holds by its own account, as the dashboard and risk_by_cause count it; 12 such vaults held $1.9B with no money-based rule able to fire on them
        for ka_, h_ in (json.load(open(a.held)).get("by_target") or {}).items():
            if ka_ not in tvl and ka_ not in scoped_ and h_.get("held_usd"): tvl = dict(tvl); tvl[ka_] = {"slug": "held:" + ka_, "name": "held by the contract", "tvl": float(h_["held_usd"]), "scope": "contract", "chain": ka_.split(":")[0]}
    except Exception: pass  # noqa: BLE001
    latest = json.load(open(a.latest)) if os.path.exists(a.latest) else {}
    so_status, so_changed, so_shared, so_upgraded, so_pending = {}, set(), {}, set(), set()   # the independent reader's verdict per target (scripts/second_opinion.py), two more fields a rule can use
    if os.path.exists(a.second_opinion):
        try:
            so = json.load(open(a.second_opinion))
            for r_ in so.get("results", []): so_status[r_["chain"] + ":" + norm(r_["target"])] = "disagree" if r_.get("disagree") and not r_.get("acknowledged") else "reviewed" if r_.get("acknowledged") else r_.get("kind") if r_.get("kind") in ("unreadable", "native") else "agree"
            so_shared = {r_["chain"] + ":" + norm(r_["target"]): len(r_.get("shares_admin_with") or []) for r_ in so.get("results", [])}
            for r_ in so.get("changed", []): so_changed.add(r_["chain"] + ":" + norm(r_["target"]))
            for r_ in so.get("upgrades", []): so_upgraded.add(r_["chain"] + ":" + norm(r_["target"]))
            for r_ in so.get("results", []):
                if r_.get("pending_admin"): so_pending.add(r_["chain"] + ":" + norm(r_["target"]))
        except Exception: pass  # noqa: BLE001 -- an unreadable file leaves both fields null, which no rule treats as a finding
    disputes = {}   # the public disputes (scripts/disputes.py): the status of the newest dispute on each target, "open" | "upheld" | "revised" | "withdrawn"
    if os.path.exists(a.disputes):
        try:
            for ka_, ds in json.load(open(a.disputes)).get("by_target", {}).items(): disputes[ka_] = sorted(ds, key=lambda d: d.get("opened") or "")[-1]["status"]
        except Exception: pass  # noqa: BLE001 -- unreadable: the field stays null
    queued, recent = {}, {}
    if os.path.exists(a.pending):
        for tl in json.load(open(a.pending)).get("results", []):
            for op in (o for o in tl.get("pending", []) if fresh_enough(o.get("state"), o.get("ready_at"), time.time())): queued.setdefault(PENDING_CHAIN.get(tl["chain"], tl["chain"]) + ":" + norm(op["target"]), []).append({"timelock": tl["name"], "timelock_address": tl.get("address"), "family": tl.get("family"), "id": op.get("id"), "chain": tl["chain"], "tx": op.get("tx"), "selector": op.get("selector"), "signature": op.get("signature") or SELNAMES.get(str(op.get("selector") or "").lower()), "ready_at": op.get("ready_at"), "state": op.get("state")})
            for op in (o for o in tl.get("recent", []) if not o.get("still_queued")): recent.setdefault(PENDING_CHAIN.get(tl["chain"], tl["chain"]) + ":" + norm(op["target"]), []).append({"timelock": tl["name"], "tx": op.get("tx"), "queued_at": op.get("queued_at")})
    now_s = time.time()
    prev = json.load(open(a.out)) if os.path.exists(a.out) else {"active": [], "history": []}
    was_active = {x["rule"] + "|" + x["chain"] + ":" + norm(x["target"]) for x in prev.get("active", [])}
    was_notified = {x["rule"] + "|" + x["chain"] + ":" + norm(x["target"]) for x in prev.get("active", []) if x.get("notified", True)}
    prevsub = {}
    for f in glob.glob(os.path.join(a.prev, "*.json")):
        for t in json.load(open(f))["targets"]: prevsub[os.path.basename(f)[:-5] + ":" + norm(t["target"])] = t
    seen = {h["key"]: h for h in prev.get("history", []) if h.get("rule") in {r_["name"] for r_ in rules["rules"]}}   # the history of a rule that no longer exists is not carried
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()); active = []; errors = []
    for f in sorted(glob.glob(os.path.join(a.scores, "*.json"))):
        key = WATCH_SLUGS.get(os.path.basename(f)[:-5])
        if not key: continue
        for t in json.load(open(f))["targets"]:
            addr = norm(t["target"]); ka = key + ":" + addr; m = tvl.get(key + ":" + addr.lower()); score = int(t["compositeScore"])
            prevc = t.get("previousComposite"); delta = None if prevc in (None, "") else score - int(prevc)
            ps = prevsub.get(os.path.basename(f)[:-5] + ":" + addr)
            def axd(k): return (int(t[k]) - int(ps[k])) if ps and k in ps and k in t else None
            env = {"score": score, "delta": delta, "stale": bool(t.get("stale")), "tvl_usd": m["tvl"] if m else None,
                   "at_risk_usd": (m["tvl"] * (100 - score) / 100) if m else None, "admin": t.get("adminKeyScore"), "multisig": t.get("multisigScore"),
                   "timelock": t.get("timelockScore"), "price_feed": t.get("oracleAuthorityScore"), "shared": t.get("crossExposureScore"),
                   "chain": LABEL.get(key, key), "title": (m["name"] if (m and m.get("scope") != "contract") else addr[:6] + "…" + addr[-4:]), "admin_delta": axd("adminKeyScore"), "multisig_delta": axd("multisigScore"), "timelock_delta": axd("timelockScore"),
                   "queued_ops": len(queued.get(ka, [])), "executed_14d": len(recent.get(ka, [])),
                   "held_drop_pct": (-(held_all[ka]["amount_change_pct"]) if (held_all.get(ka) or {}).get("amount_change_pct") is not None and not held_all[ka].get("stale") else None),
                   "pause_change": (pause_all.get(ka) or {}).get("change") if not (pause_all.get(ka) or {}).get("stale") else None, "paused": (pause_all.get(ka) or {}).get("paused") if not (pause_all.get(ka) or {}).get("stale") else None,
                   "side_role_change": any(not c_.get("shorter") for c_ in side_changes.get(ka, [])), "side_delay_cut": any(c_.get("shorter") for c_ in side_changes.get(ka, [])),
                   "held_vanished": bool((held_all.get(ka) or {}).get("vanished")), "safe_woke": ka in safe_woke,
                   "held_drop_usd": ((held_all[ka]["prev_amount"] - held_all[ka]["amount"]) * held_all[ka]["price_usd"] if (held_all.get(ka) or {}).get("amount_change_pct") is not None and held_all[ka].get("price_usd") and not held_all[ka].get("stale") else None),   # a stale record never fires, in dollars either (the shipped rules also test held_drop_pct, which already ignored it)
                   "second_opinion": so_status.get(ka), "admin_changed": ka in so_changed, "shared_admin": so_shared.get(ka), "dispute": disputes.get(ka), "upgraded": ka in so_upgraded, "admin_pending": ka in so_pending,
                   "age_days": ((now_s - int(t["lastUpdated"])) / 86400) if t.get("lastUpdated") else None,   # since the last push of this score; the oracles mark it stale at 9 days
                   "ready_recent": any(op.get("ready_at") and op.get("state") != "expired" and 0 <= now_s - op["ready_at"] <= READY_FRESH_DAYS * 86400 for op in queued.get(ka, [])),   # ready for at most 7 days: urgent (older ones are not listed, lib/fresh_ops.py)
                   "ready_in_hours": (min((op["ready_at"] - now_s) / 3600 for op in queued[ka] if op.get("ready_at") and op.get("state") != "expired") if any(op.get("ready_at") and op.get("state") != "expired" for op in queued.get(ka, [])) else None)}   # a Compound-style change past its grace window can no longer run: it is not "ready to execute now"
            evidence = sorted(queued.get(ka, []), key=lambda op: op.get("ready_at") or 0)[:3]
            for r, tree in compiled:
                try: hit = bool(ev(tree, env))
                except Exception as e:
                    msg = r["name"] + ": " + str(e)
                    if msg not in errors: errors.append(msg)   # one line per rule and cause, not one per target (a bad rule hit every target: 537 identical lines in a public file, seen 09/10)
                    continue
                if not hit: continue
                k = r["name"] + "|" + key + ":" + addr
                is_new = (r["name"] + "|" + env["chain"] + ":" + addr) not in was_active
                h = seen.get(k) or {"key": k, "rule": r["name"], "severity": r.get("severity", "info"), "chain": env["chain"], "target": t["target"], "title": env["title"], "first_seen": now, "last_seen": now, "times": 0}
                if is_new: h["first_seen"] = now
                bal = {"symbol": held_all[ka].get("symbol"), "from": held_all[ka]["prev_amount"], "to": held_all[ka]["amount"], "change_pct": held_all[ka]["amount_change_pct"], "since": held_all[ka].get("prev_at")} if ("held_drop" in r["when"] and (held_all.get(ka) or {}).get("amount_change_pct") is not None) else None
                h.update({"last_seen": now, "times": h.get("times", 0) + 1, "score": score, "delta": delta, "tvl_usd": env["tvl_usd"]}); seen[k] = h
                pz = {"change": pause_all[ka]["change"], "via": pause_all[ka].get("via"), "previous_run": pause_all[ka].get("previous_run")} if ("pause_change" in r["when"] and (pause_all.get(ka) or {}).get("change")) else None
                sr = [c_ for c_ in side_changes.get(ka, []) if bool(c_.get("shorter")) == ("side_delay" in r["when"])][:3] if ("side_role" in r["when"] or "side_delay" in r["when"]) else None   # each rule carries only its own changes: the high one the shorter delay, the medium one the rest
                sr = sr or None
                if sr: h["side_role"] = sr
                if bal: h["balance"] = bal
                sw = {"safe": short_safe(safe_woke[ka]["safe"]), "delta": safe_woke[ka].get("delta"), "idle_days": safe_woke[ka].get("idle_days"), "previous_run": safe_woke[ka].get("previous_run")} if ("safe_woke" in r["when"] and ka in safe_woke) else None
                if sw: h["safe_wake"] = sw
                if pz: h["pause"] = pz
                active.append({"rule": r["name"], "severity": r.get("severity", "info"), "chain": env["chain"], "target": t["target"], "title": env["title"], "score": score, "delta": delta, "tvl_usd": env["tvl_usd"], "first_seen": (now if is_new else h["first_seen"]), "new": is_new,
                               "evidence": evidence if "queued" in r["when"] or "ready_in" in r["when"] else [], "previous_run": latest.get("previous_run_utc") if delta is not None else None,
                               **({"balance": bal} if bal else {}), **({"pause": pz} if pz else {}), **({"side_role": sr} if sr else {}), **({"safe_wake": sw} if sw else {})})
    history = sorted(seen.values(), key=lambda h: h["last_seen"], reverse=True)[:500]
    out = {"evaluated_utc": now, "run_utc": latest.get("run_utc"), "rules": [r["name"] for r in rules["rules"]], "active": active, "history": history, "errors": errors}
    for x in active: x["notified"] = (x["rule"] + "|" + x["chain"] + ":" + norm(x["target"])) in was_notified and not x["new"]   # false = still to deliver (new, or not delivered last time)
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True); _dump_json(out, a.out, indent=1)
    import html as _h
    feed = ['<?xml version="1.0" encoding="utf-8"?>', '<feed xmlns="http://www.w3.org/2005/Atom">', '<title>Authority Risk Oracle: alerts</title>', '<author><name>Authority Risk Oracle</name></author>', '<link href="https://realspap.github.io/oracle/#alerts-fold"/>', '<link rel="self" href="' + RAW + 'alerts.xml"/>', '<id>https://realspap.github.io/oracle/alerts</id>', '<updated>%s</updated>' % now]
    fn_of = {}   # the queued functions behind an active alert, named: a feed reader sees "setRateLimits on Ethena Timelock", not just the rule
    for x in active:
        names = sorted(set((e.get("signature") or "").split("(")[0] + " on " + str(e.get("timelock") or "") for e in x.get("evidence", []) if e.get("signature")))
        bt = detail_text(x)
        if names or bt: fn_of[(x["rule"], x["chain"], norm(x["target"]))] = ", ".join(names[:4] + ([bt] if bt else []))   # active alerts carry no key: match the history entry on rule, chain and target
    for x in history[:60]:
        feed.append('<entry><title>%s: %s (%s, score %d)</title><id>urn:aro:alert:%s</id><updated>%s</updated><summary>%s%s, first seen %s, seen %d time(s)</summary><link href="https://realspap.github.io/oracle/#chain=all&amp;q=%s"/></entry>' % (
            _h.escape(x["severity"]), _h.escape(x["title"]), _h.escape(x["chain"]), x.get("score", 0), __import__("hashlib").sha1(x["key"].encode()).hexdigest()[:16], x["last_seen"], _h.escape(x["rule"]), (" (" + _h.escape(fn_of[(x["rule"], x["chain"], norm(x["target"]))]) + ")") if (x["rule"], x["chain"], norm(x["target"])) in fn_of else "", x["first_seen"], x.get("times", 1), _h.escape(norm(x["target"]))))
    feed.append("</feed>"); open(os.path.join(os.path.dirname(a.out) or ".", "alerts.xml"), "w").write("\n".join(feed))
    bd = os.path.join(os.path.dirname(a.out) or ".", "badge"); os.makedirs(bd, exist_ok=True)
    hi = sum(1 for x in active if x["severity"] == "high")
    _dump_json({"schemaVersion": 1, "label": "authority alerts", "message": ("%d firing" % len(active)) + (", %d high" % hi if hi else "") if active else "none firing", "color": "e05d5d" if hi else ("dfb13a" if active else "3fbf8f")}, os.path.join(bd, "alerts.json"))
    new = [x for x in active if not x["notified"] and SEV.get(x["severity"], 0) >= SEV.get(rules.get("notify", {}).get("min_severity", "medium"), 1)]   # new, or not delivered last time
    sent = []; impl_src = impl_verified_by_address(os.path.join(os.path.dirname(a.out) or ".", "impl_sources.json"))   # Sourcify state of the code behind each proxy, for the daily mode
    if new and not a.no_send:
        text = "Authority Risk Oracle: %d new alert(s)\n" % len(new) + "\n".join("[%s] %s: %s (%s, score %d)%s" % (x["severity"], x["rule"], x["title"], x["chain"], x["score"], (" " + detail_text(x)) if detail_text(x) else "") for x in new[:10]) + "\nhttps://realspap.github.io/oracle/"
        if os.environ.get("DISCORD_WEBHOOK_URL") and post_json(os.environ["DISCORD_WEBHOOK_URL"], {"content": text[:1900], "allowed_mentions": {"parse": []}}): sent.append("discord")
        if os.environ.get("ALERT_WEBHOOK_URL") and post_signed(os.environ["ALERT_WEBHOOK_URL"], os.environ.get("ALERT_WEBHOOK_SECRET", ""), {"event": "alerts", "version": 1, "sent_utc": now, "alerts": [{k: x.get(k) for k in ("rule", "severity", "chain", "target", "title", "score", "delta", "tvl_usd", "first_seen")} for x in new[:10]], "page": "https://realspap.github.io/oracle/"}): sent.append("webhook")
        daily = os.environ.get("TELEGRAM_MODE") == "daily"; tg_new = [x for x in new if live_on_telegram(x, impl_src)] if daily else new   # daily mode (12/10, off by default): the public channel gets one summary a day (scripts/telegram_digest.py --daily) and only the critical alerts live
        tg_text = text if not daily else ("Authority Risk Oracle: %d critical alert(s)\n" % len(tg_new) + "\n".join("[%s] %s: %s (%s, score %d)" % (x["severity"], x["rule"], x["title"], x["chain"], x["score"]) for x in tg_new[:10]) + "\nhttps://realspap.github.io/oracle/")
        if os.environ.get("TELEGRAM_BOT_TOKEN") and os.environ.get("TELEGRAM_CHAT_ID") and tg_new:
            try:
                sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")); import alerts
                if alerts.send_telegram_alert(tg_text if len(tg_text) <= 4000 else tg_text[:3900] + "\n... (cut at Telegram's limit of 4096 characters, the rest is on the alerts page)"): sent.append("telegram")
            except Exception: pass
    channels = bool(os.environ.get("DISCORD_WEBHOOK_URL") or (os.environ.get("ALERT_WEBHOOK_URL") and os.environ.get("ALERT_WEBHOOK_SECRET")) or (os.environ.get("TELEGRAM_BOT_TOKEN") and os.environ.get("TELEGRAM_CHAT_ID") and (os.environ.get("TELEGRAM_MODE") != "daily" or any(live_on_telegram(x, impl_src) for x in new))))
    for i, x in enumerate(new): x["notified"] = (bool(sent) and i < 10) or not channels or a.no_send   # delivered (the message carries ten at most), or nobody to deliver to; a failed or unsent one is retried next run
    _dump_json(out, a.out, indent=1)   # written again with the delivery state
    # the alarm channel that needs no secret (since 2026-10-10): a HIGH alert that appeared this run (not one that stays) is written for the workflow, which opens an issue in the private repository.
    # Before, only Discord / Telegram (secrets nobody had set yet) carried a drain, a pause or a change ready to execute: the feeds and the page, nothing that reaches a person.
    hp = os.path.join(os.path.dirname(a.out) or ".", "alerts_high.md"); highs = [x for x in active if x["severity"] == "high" and x["new"]]
    if highs:
        open(hp, "w").write("## New high alert(s) from rules.json\n\n" + "\n".join("- **%s** on %s (%s, score %d): %s%s" % (x["title"], x["chain"], x["target"], x["score"], x["rule"], (" -- " + detail_text(x)) if detail_text(x) else "") for x in highs) + "\n")
    elif os.path.exists(hp): os.remove(hp)
    print(f"rules: {len(active)} active firing(s) on {len(rules['rules'])} rule(s), {len(new)} new, sent to {sent or 'nobody'}, {len(errors)} error(s)")

if __name__ == "__main__":
    sys.exit(main())
