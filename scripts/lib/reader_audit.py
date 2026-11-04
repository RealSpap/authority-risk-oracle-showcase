"""Pure helpers for the readers (the Watch and the independent reader), added on 30 October 2026.

Nothing here reads the chain, writes a file or sends a message: every function takes what was read and returns what to say, so a test can
feed it a fixture. The scripts (`watch_run.py`, `evaluate_rules.py`, `alarm_gate.py`, `second_opinion.py`, `pause_state.py`, `safe_activity.py`,
`warning_ledger.py`, `check_pending_ops.py`, `check_nested_signers.py`) call them. This file is NOT one of the files the methodology hash covers
(`scripts/lib/methodology.py`, `scoring_files`): no scorer imports it, and a test (`test_reader_audit.py`) checks that.


"""
import time

# ---------------------------------------------------------------- [107] a hole in the oracle's own role-event scan

STALL_REPEAT_RUNS = 4   # a stall that goes on is said again every 4 runs (once a day)
SCAN_STALL_RUNS = 2   # runs (12 hours at four a day) in which the scanned-to marker did not move while the chain did, before it is an alert


def scan_progress(prev_doc, cur_doc):
    """(stalled_runs, alerts) for one EVM oracle document.

    `gap_blocks` (watch_run.scanned_to): a window too large to scan was given up and the marker jumped over it, so a RoleGranted inside it was
    never looked at: that is a hole in the watch, said as an alert. `self_scanned_to` that does not advance while `block` does, for
    SCAN_STALL_RUNS runs in a row, is a scan that keeps failing (the marker is kept at the old start on failure, so it is the visible symptom).
    The count of stalled runs is carried in the document (`scan_stalled_runs`) from run to run."""
    name = cur_doc.get("name") or "oracle"
    out = []
    sw = cur_doc.get("self") or {}
    gap = sw.get("gap_blocks")
    if gap:
        out.append(f"{name}: the scan of the oracle's own role events gave up a window of {gap} blocks; a RoleGranted or RoleRevoked inside it was not seen")
    prev_doc = prev_doc if isinstance(prev_doc, dict) else {}
    pb, ps = prev_doc.get("block"), prev_doc.get("self_scanned_to")
    cb, cs = cur_doc.get("block"), cur_doc.get("self_scanned_to")
    stalled = 0
    if all(isinstance(v, int) for v in (pb, ps, cb, cs)) and cb > pb and cs <= ps:
        stalled = int(prev_doc.get("scan_stalled_runs") or 0) + 1
    if stalled >= SCAN_STALL_RUNS and (stalled - SCAN_STALL_RUNS) % STALL_REPEAT_RUNS == 0:   # a standing state is said when it starts and then once a day, not at every run: the chained journal and the feeds hold events
        out.append(f"{name}: the scan of the oracle's own role events has not advanced for several runs{VOLATILE}{stalled} runs, scanned to block {cs}, chain at block {cb}")
    return stalled, out


# ---------------------------------------------------------------- [lastUpdated] F1 / F2

VOLATILE = " ~ "   # what follows in an alarm line changes at every run; alarm_gate.findings cuts the line here before it makes the identifier of the finding

LASTUPDATED_FUTURE_TOLERANCE = 300   # seconds: the pusher's clock can be a little ahead of the chain's


def future_dated(targets, block_time):
    """The targets whose date is later than the block time plus the tolerance (sorted addresses), [] when the block time is not known. Carried in the document
    (`future_dated`) so that the next run says F1 for a target only when it is NEW in that list: the state stands in the file, the journal gets the event."""
    if block_time is None:
        return []
    return sorted(t["target"] for t in targets if isinstance(t.get("lastUpdated"), int) and t["lastUpdated"] > block_time + LASTUPDATED_FUTURE_TOLERANCE)


def last_updated_alerts(name, targets, prev_by_target, block_time, label_of=lambda t: t["target"][:6] + "..." + t["target"][-4:], already_future=()):
    """Alerts about the date an EVM oracle holds for a target. The updater supplies `lastUpdated` (the contract does not check it).

    F1: a date later than the block time plus the tolerance (a score dated in the future never turns stale).
    F2: a date earlier than the one the previous run read for the same target (a score written back to an older date).
    `block_time` None (the block was not read) skips F1 and says so by returning the marker string in the second item; F2 needs no block.
    A target in `already_future` (flagged by the previous run) is not said again: F1 is an event when it starts, the standing state is `future_dated` in the file."""
    alerts, skipped = [], block_time is None
    for t in targets:
        lu = t.get("lastUpdated")
        if not isinstance(lu, int):
            continue
        lab = label_of(t)
        if not skipped and lu > block_time + LASTUPDATED_FUTURE_TOLERANCE and t["target"] not in set(already_future):
            alerts.append(f"{name}: {lab} has a last-update date after the block time (the updater supplies it; a future date never turns stale){VOLATILE}{lu - block_time} s after")
        p = (prev_by_target or {}).get(t["target"])
        if p and isinstance(p.get("lastUpdated"), int) and lu < p["lastUpdated"]:
            alerts.append(f"{name}: {lab} last-update date went back from {p['lastUpdated']} to {lu}")
    return alerts, ("block time not read: the future-date check (F1) was skipped" if skipped else None)


# ---------------------------------------------------------------- [80] the freshness of each thing, side by side

def freshness_record(run_utc_epoch, block, block_time, targets):
    """Four ages in one place for one oracle: when the Watch read it, the block read and its time, the newest and the oldest push on the oracle.
    Every value is a unix time or None (unknown, never zero)."""
    pushes = [t["lastUpdated"] for t in targets if isinstance(t.get("lastUpdated"), int) and not isinstance(t["lastUpdated"], bool) and t["lastUpdated"] > 0]   # 0 is "never pushed", not 1970
    return {"watch_read_at": run_utc_epoch, "block": block, "block_time": block_time,
            "newest_push": max(pushes) if pushes else None, "oldest_push": min(pushes) if pushes else None}


# ---------------------------------------------------------------- [84] delivered per channel

MESSAGE_ALERTS = 10   # the message carries ten alerts at most (evaluate_rules)
CHANNELS = ("discord", "webhook", "telegram")


def configured_channels(env):
    """The channels that exist, in a fixed order, from the environment: a webhook needs its URL AND its secret, Telegram its token AND its chat."""
    out = []
    if env.get("DISCORD_WEBHOOK_URL"): out.append("discord")
    if env.get("ALERT_WEBHOOK_URL") and env.get("ALERT_WEBHOOK_SECRET"): out.append("webhook")
    if env.get("TELEGRAM_BOT_TOKEN") and env.get("TELEGRAM_CHAT_ID"): out.append("telegram")
    return out


def channels_still_owed(prev_entry, configured):
    """The channels an alert still has to reach, from its previous entry. A new alert (no previous entry) is owed to every channel. An entry
    with a `delivered` list is owed to the channels not in it. An entry written before this change has none: `notified` then meant "delivered
    to the channels of that day", so it counts as delivered everywhere, and a not-notified one as owed everywhere."""
    if not prev_entry:
        return list(configured)
    got = prev_entry.get("delivered")
    if got is None:
        return [] if prev_entry.get("notified", True) else list(configured)
    return [c for c in configured if c not in got]


def batches_for(keys, owed, configured, cap=MESSAGE_ALERTS):
    """{channel: [alert keys it is sent]}: for each channel the alerts it still owes, in order, at most `cap` (the message size)."""
    return {c: [k for k in keys if c in owed.get(k, [])][:cap] for c in configured}


def delivered_after(prev_delivered, key, batches, results):
    """The channels that carry the alert after this run: the ones it already had, plus every channel whose send succeeded and whose
    batch contained it. A channel that failed, or whose batch was cut at the cap, is not added: that is the point of tracking per channel."""
    got = set(prev_delivered or [])
    got.update(c for c, ks in batches.items() if results.get(c) and key in ks)
    return sorted(got)


def is_notified(delivered, required):
    """True when every required channel carries the alert (and trivially when no channel is required)."""
    return all(c in delivered for c in required)


# ---------------------------------------------------------------- [100][101] a state nobody could read for days

STATE_UNVERIFIED_DAYS = 3


def _epoch(utc):
    try:
        import calendar
        return calendar.timegm(time.strptime(utc, "%Y-%m-%dT%H:%M:%SZ"))
    except (TypeError, ValueError):
        return None


def unverified_days(rec, generated_utc):
    """Days a stale record has gone unread: None for a record read this run (not stale), else days since `stale_since` (the run that last read it).
    A stale record with no usable `stale_since` is None as well: unknown is not zero days."""
    if not rec or not rec.get("stale"):
        return None
    s, g = _epoch(rec.get("stale_since")), _epoch(generated_utc)
    if s is None or g is None:
        return None
    return max(0.0, (g - s) / 86400)


def state_unverified(rec, generated_utc, days=STATE_UNVERIFIED_DAYS):
    """True when a pause or Safe-activity record has not been read for `days` days or more: the state shown is the last one read, not the current one."""
    d = unverified_days(rec, generated_utc)
    return d is not None and d >= days


# ---------------------------------------------------------------- [92] recovery and escalation of the alarm gate

ESCALATE_HOURS = 72   # a finding that stands this long is said louder: it is not a reminder any more


def decide_gate(found, state, now, reminder_hours=24, escalate_hours=ESCALATE_HOURS, strptime=None, condition_holds=None):
    """Extends alarm_gate.decide: 'new', 'reminder', 'escalation', 'quiet', 'recovered', 'unrecognised'.

    'recovered': the standing findings (everything but the one-pass `alarm:` events) of the last notice are all gone, a notice had been sent AND the alarm
    condition of the workflow says it is over (`condition_holds` False). A condition that still holds, or one the caller did not pass, with no finding the gate reads is 'unrecognised':
    a cause the gate does not read is never taken for the end of an alarm (an empty step output used to read as true and would have closed it).
    'escalation': the same findings stand since `escalate_hours` after the first notice, and the last notice is older than a reminder period."""
    import calendar
    parse = strptime or (lambda s: calendar.timegm(time.strptime(s, "%Y-%m-%dT%H:%M:%SZ")))
    seen = set((state or {}).get("findings") or [])
    last = (state or {}).get("notified_utc")
    first = (state or {}).get("first_notified_utc") or last   # a state written before the lot has no first notice: the last one is the best date there is
    if not found:
        standing_kinds = {f for f in seen if not f.startswith("alarm:")}      # an `alarm:` line is an event of one pass (a score fell, a role changed): there is nothing to "clear" afterwards
        return "recovered" if standing_kinds and last and condition_holds is False else "unrecognised"
    if found - seen or not state:
        return "new"
    try:
        age = (now - parse(last)) / 3600 if last else 1e9
    except (ValueError, TypeError, OverflowError):
        return "new"      # a notice date that cannot be read is no notice
    if age < -1:
        return "new"      # a notice dated in the future (the state file is not signed) must not keep the alarm quiet
    if age < reminder_hours:
        return "quiet"
    first_seen = (state or {}).get("first_seen") or {}
    oldest = [parse(first_seen[f]) for f in found if f in first_seen]      # how long the OLDEST finding still standing has stood: a new finding next to it does not restart the clock
    standing = (now - min(oldest)) / 3600 if oldest else ((now - parse(first)) / 3600 if first else 0)
    return "escalation" if standing >= escalate_hours else "reminder"


# ---------------------------------------------------------------- [8] every holder of DEFAULT_ADMIN_ROLE, within a bound

ADMIN_MEMBERS_CAP = 10
_MEMBER_SEL = "0x9010d07c"   # getRoleMember(bytes32,uint256)


def admin_member_calls(target, total, cap=ADMIN_MEMBERS_CAP):
    """The eth_call requests for members 1 .. min(total, cap) - 1 of DEFAULT_ADMIN_ROLE (member 0 is read by the first pass)."""
    n = min(total, cap) if isinstance(total, int) else 0
    return [("eth_call", [{"to": target, "data": _MEMBER_SEL + "0" * 64 + f"{j:064x}"}, "latest"]) for j in range(1, n)]


def assemble_admin_members(first, total, answers, cap=ADMIN_MEMBERS_CAP):
    """{members, total, read, unread, note}. `first` is member 0 (an address or None), `answers` the raw answers for members 1 ..
    An unanswered or malformed answer is an unread member, never an absent one."""
    def addr(w):
        try:
            return ("0x" + w[-40:]).lower() if isinstance(w, str) and len(w) == 66 and int(w, 16) != 0 else None
        except ValueError:   # 66 characters that are not hexadecimal: an unreadable answer, counted unread
            return None
    members = [first.lower()] if first else []
    bad = 0
    for w in answers or []:
        a = addr(w)
        if a:
            members.append(a)
        else:
            bad += 1
    if not isinstance(total, int):
        return {"members": members, "total": None, "read": len(members), "unread": None, "note": "the number of members was not read"}
    unread = max(0, total - len(members))
    note = None
    if unread:
        note = f"{unread} of {total} members of DEFAULT_ADMIN_ROLE not read" + (" (above the bound of %d)" % cap if total > cap else " (an answer was missing)")
    return {"members": members, "total": total, "read": len(members), "unread": unread, "note": note}


# ---------------------------------------------------------------- [10] Safe modules: the page of 50 and its cursor

SENTINEL_MODULES = "0x" + "0" * 63 + "1"


def modules_truncated_of(word, page=50):
    """True / False / None for the `modules_truncated` field: None when the answer is absent or cannot be read (an unreadable page is not a complete list)."""
    if word in (None, "", "0x"):
        return None
    mods, trunc = parse_modules_page(word, page)
    return None if mods is None else bool(trunc)


def parse_modules_page(word, page=50):
    """(modules, truncated) from a getModulesPaginated answer (offset, next, length, addresses). `truncated` is True when `next` is not the
    sentinel: more modules exist than the page returned. (None, None) for an answer that cannot be read."""
    try:
        if not word or len(word) < 2 + 64 * 3:
            return None, None
        nxt = "0x" + word[2 + 64 + 24:2 + 128]
        n = int(word[2 + 128:2 + 192], 16)
        if len(word) < 2 + 192 + 64 * min(n, page):
            return None, None
        mods = [("0x" + word[2 + 192 + 64 * j + 24:2 + 192 + 64 * (j + 1)]).lower() for j in range(min(n, page))]
        return mods, (int(nxt, 16) not in (0, 1))
    except ValueError:
        return None, None


# ---------------------------------------------------------------- [9][11] nested signers: the depth limit

def depth_limit_hits(tree, get_safe, max_depth):
    """The nodes at depth `max_depth` that are contracts and turn out to be Safes: the tree stopped there (build_tree resolves no Safe below
    MAX_DEPTH), so the signers under them are not in the tree. Returns a list of addresses; a get_safe that fails (None) is not a hit.
    `tree` is a node from nested_signers.build_tree; the root is depth 0."""
    hits = []

    def walk(node, depth):
        if node.get("kind") == "contract" and depth >= max_depth:
            try:
                if get_safe(node["addr"]):
                    hits.append(node["addr"])
            except Exception:  # noqa: BLE001 -- an unreadable probe is not a hit
                pass
        for kid in node.get("kids", []):
            walk(kid, depth + 1)

    walk(tree, 0)
    return hits


# ---------------------------------------------------------------- [83][16] how a queued operation ended

FINAL_STATES = ("executed", "cancelled", "expired", "unknown")


def final_state(family, still_queued, done=None, expired=False, executed_events=None, cancelled_events=None):
    """executed / cancelled / expired / unknown for an operation that is no longer queued; None while it is still queued.

    OpenZeppelin timelock: `done` is isOperationDone(id) (True = executed; False with the operation no longer pending = cancelled).
    Compound-style timelock: no such getter, so the answer comes from the events looked for by the script (`executed_events` /
    `cancelled_events` = number found, None = not looked for or the read failed). An operation past eta + grace that is STILL in the queue is "expired"
    (told by check_pending_ops from the queue state, not here); one that left the queue with neither event found is "unknown".
    Anything that cannot be told is "unknown", never a guess."""
    if still_queued:
        return None
    if family == "oz":
        return "executed" if done is True else ("cancelled" if done is False else "unknown")
    if executed_events:
        return "executed"
    if cancelled_events:
        return "cancelled"
    return "unknown"      # an operation that left `queuedTransactions` was executed or cancelled; no event found means the event read missed it, not that it expired


# ---------------------------------------------------------------- [74] the window each timelock was read over

def window_fields(head_block, start_block, seconds_per_block):
    """window_blocks / window_days_est / window_note for a timelock read from start_block to head_block (same names as pending_ops_discovered)."""
    blocks = max(0, head_block - start_block)
    return {"window_blocks": blocks, "window_days_est": round(blocks * seconds_per_block / 86400, 1),
            "window_note": "an operation queued before this window is not seen"}


# ---------------------------------------------------------------- [32] a transfer of the default admin in flight (AccessControlDefaultAdminRules)

PENDING_DEFAULT_ADMIN_SEL = "0xcf6eefb7"   # pendingDefaultAdmin() -> (address newAdmin, uint48 schedule)


def parse_pending_default_admin(word):
    """(address or None, schedule or None) from a pendingDefaultAdmin() answer. A zero address means no transfer in flight; an answer that is
    not two words is not a reading (None, None) and is not told apart from a contract without the getter."""
    try:
        if not isinstance(word, str) or len(word) != 2 + 128:
            return None, None
        a = int(word[2 + 24:2 + 64], 16)
        if a == 0:
            return None, None
        return "0x%040x" % a, int(word[2 + 64:], 16) or None
    except ValueError:
        return None, None


# ---------------------------------------------------------------- [17] the gap between the reading of the scores and the second reading

def since_score_push_seconds(last_updated, now):
    """Seconds between the last push of the score (`lastUpdated`, supplied by the updater) and this reading of the live chain: the gap that matters when the two
    are compared, since the scorer read the chain when it computed the score, not when the Watch read the oracle. None when the date is not known."""
    if not isinstance(last_updated, int) or isinstance(last_updated, bool):
        return None
    return max(0, int(now) - last_updated)


def read_gap_seconds(scores_read_at, now):
    """Seconds between the Watch's reading of the oracle (`readAt` of the scores file) and this second reading of the same target on the chain it
    governs. Never a block gap: the oracle runs on a test network and the contract it scores on another one, so their block numbers cannot be
    subtracted. None when the first reading time is not known."""
    if not isinstance(scores_read_at, int) or isinstance(scores_read_at, bool):
        return None
    return max(0, int(now) - scores_read_at)


# ---------------------------------------------------------------- [23][97] a change of method between two points of a series

PASS_SECONDS = 3600   # one Watch pass lasts well under an hour


def mark_method_breaks(series, meth_changes):
    """Marks, in place, every point of every series that comes AFTER a methodology change on its chain: `method_break` True (and `method_change`
    {from, to} of the latest change since the previous point) when a change was recorded at a time t with previous_point.t < t <= point.t + PASS_SECONDS,
    False otherwise (the first point has no previous one: False). The margin is there because the events of one Watch pass do not carry the same time: the
    score move takes the time the pass started and the change of method the time the methodology check ran, minutes later, in the same pass. Times are ISO
    strings; the chain is the part of the key before the first colon."""
    import calendar
    for ka, pts in series.items():
        chain = ka.split(":", 1)[0]
        changes = sorted(meth_changes.get(chain) or [], key=lambda c: c.get("t") or "")
        for i, p in enumerate(pts):
            upper = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(calendar.timegm(time.strptime(p["t"], "%Y-%m-%dT%H:%M:%SZ")) + PASS_SECONDS)) if i > 0 else None
            hit = [c for c in changes if i > 0 and pts[i - 1]["t"] < (c.get("t") or "") <= upper]
            p["method_break"] = bool(hit)
            if hit:
                p["method_change"] = {"from": hit[-1].get("from"), "to": hit[-1].get("to")}
    return series


# ---------------------------------------------------------------- [78] what the calibration left out

def count_exclusion(op):
    """'undecoded' (the call was not decoded), 'other_target' (decoded and aimed at another program or a transfer) or None (the operation counts)."""
    if op.get("undecoded"):
        return "undecoded"
    if op.get("touches_governed") is False:
        return "other_target"
    return None


# ---------------------------------------------------------------- [28] the date of the shared-signer snapshot

def snapshot_status(swept_utc, valid_days, now):
    """{swept_utc, valid_until_utc, expired}: the sweep of the shared-signer table that the crossExposure scores read, and whether it is past its
    validity at unix time `now`. A date that cannot be read gives swept_utc None and expired None (unknown, not valid and not expired)."""
    import calendar
    try:
        t = calendar.timegm(time.strptime(swept_utc, "%Y-%m-%d"))
    except (TypeError, ValueError):
        return {"swept_utc": None, "valid_until_utc": None, "expired": None}
    until = t + int(valid_days) * 86400
    return {"swept_utc": swept_utc, "valid_until_utc": time.strftime("%Y-%m-%d", time.gmtime(until)), "expired": now > until}


def snapshot_for(snap, ka, now):
    """The sweep of the shared-signer table that ONE target rests on: {swept_utc, valid_until_utc, expired, from}. `snap` is data/cross_snapshot.json:
    an entry in `targets` (key '<chain>:<address>', lower case) wins over one in `chains` (key '<chain>'), which wins over the file's own date; `from` says which
    one answered ('target', 'chain', 'global') or 'none' (no readable date: swept_utc and expired are None, never a made-up date). An entry without `valid_days`
    uses the file's (30 by default)."""
    snap = snap if isinstance(snap, dict) else {}
    chain = str(ka).split(":", 1)[0]
    lower = lambda m: {str(k).lower(): v for k, v in m.items()} if isinstance(m, dict) else {}      # keys written by hand: an address pasted with capitals still matches
    for scope, entry in (("target", lower(snap.get("targets")).get(str(ka).lower())), ("chain", lower(snap.get("chains")).get(chain.lower())), ("global", snap)):
        if isinstance(entry, dict) and isinstance(entry.get("swept_utc"), str):
            st = snapshot_status(entry.get("swept_utc"), entry.get("valid_days", snap.get("valid_days", 30)), now)
            if st["swept_utc"] is not None:
                return dict(st, **{"from": scope})
    return {"swept_utc": None, "valid_until_utc": None, "expired": None, "from": "none"}


# ---------------------------------------------------------------- [18] where the money figure of a contract comes from

def money_source(ka, tvl, scope, held):
    """'out_of_scope' (retired or peripheral: carries none), 'protocol_total' / 'chain_figure' / 'contract_figure' (DefiLlama matched it at that
    scope), 'held_by_contract' (no match, but it holds assets by its own account, held_assets.json), or 'none'. TVL is what a protocol
    locks, not what a key can move: this says which of the two kinds of figure a contract's money is."""
    if (scope.get(ka) or {}).get("scope") in ("retired", "peripheral"):
        return "out_of_scope"
    m = tvl.get(ka)
    if m:
        return {"total": "protocol_total", "chain": "chain_figure", "contract": "contract_figure"}.get(m.get("scope"), "chain_figure")
    if (held.get(ka) or {}).get("held_usd"):
        return "held_by_contract"
    return "none"


# ---------------------------------------------------------------- [24] was the score recomputed in the last pass, kept from an earlier one, or fixed by decision

RECOMPUTED_WINDOW = 6 * 3600   # entries pushed within six hours of the newest push of their oracle belong to the same pass


def evaluation_of(last_updated, newest_push, fixed):
    """'fixed_by_decision' (the scorer reads the configuration but at least one of its three admin sub-scores is a constant; data/scorer_pins.json says which: scripts/check_scorer_pins.py watches it),
    'recomputed' (pushed in the newest pass of its oracle), 'kept' (older than that pass: not rewritten since), or None (no date).
    'inherited' (a score copied from a sibling target) is not told: nothing in the chain data says it."""
    if fixed:
        return "fixed_by_decision"
    if not isinstance(last_updated, int) or not isinstance(newest_push, int):
        return None
    return "recomputed" if newest_push - last_updated <= RECOMPUTED_WINDOW else "kept"


# ---------------------------------------------------------------- scorers that read a configuration and publish constants (balayage 30/10, class 1)

def evaluate_pin(pin, observed):
    """Compares what was read to what the scorer's own documentation says it is, for one pin of data/scorer_pins.json.

    `observed` maps a read's name to its value, or to None when it could not be read. A read that answers something else than `expect` is a
    difference; an unread one is unread (never a difference and never ok). Returns {id, status, differences, unread}, status 'ok' only when
    every read matched, 'changed' when at least one differs, else 'unread'. A pin with no reads is 'unread'."""
    diffs, unread = [], []
    for r in pin.get("reads", []):
        v = observed.get(r["name"])
        if v is None:
            unread.append(r["name"])
        elif v != r["expect"]:
            diffs.append({"read": r["name"], "expected": r["expect"], "observed": v, "source": r.get("source")})
    status = "changed" if diffs else ("unread" if unread or not pin.get("reads") else "ok")
    return {"id": pin.get("id"), "status": status, "differences": diffs, "unread": unread}


# ---------------------------------------------------------------- [102] a contract with none of the role getters

def no_getter_recognised(answers):
    """True when every getter was ANSWERED and none of the answers is an address-shaped word: the contract has none of the role getters this reader
    knows, which is "not covered", not "no such role". A getter that got no answer (None) makes the contract unknown, not 'no getter'."""
    if not answers or any(a is None for a in answers):
        return False
    return not any(isinstance(a, str) and len(a) == 66 for a in answers)


# ---------------------------------------------------------------- [104] when the verification was checked, and against which code

def stamp_check(entry, now_iso, code_sha256, prev_entry=None):
    """`checked_at` (the time Sourcify or OtterSec ANSWERED about this implementation) and `deployed_code_sha256` (sha256 of the code deployed at the
    implementation address when it was checked), added to an impl_sources entry. An answer kept from the previous run because the service did not
    answer (`stale`) keeps ITS time, not this run's; an entry with no answer at all (verified None) gets no time. A code that could not be read is None."""
    e = dict(entry)
    if e.get("stale"):
        e["checked_at"] = (prev_entry or {}).get("checked_at")
        e["deployed_code_sha256"] = (prev_entry or {}).get("deployed_code_sha256")
    elif e.get("verified") is None:
        e["checked_at"], e["deployed_code_sha256"] = None, code_sha256
    else:
        e["checked_at"], e["deployed_code_sha256"] = now_iso, code_sha256
    return e


# ---------------------------------------------------------------- [103] a contract under several causes

def cause_overlaps(hit_sets, money_fn):
    """{"pairs": {"a + b": {contracts, tvl_usd}}, "any_cause": {contracts, tvl_usd}} from {cause: set of contract keys}.
    `money_fn(keys)` is the money rule of the file (one figure per protocol and chain), so a shared protocol counts once. The pairs list only
    causes that share at least one contract; `any_cause` is the union: the money exposed to at least one cause, which the per-cause figures
    cannot be added up to."""
    ids = list(hit_sets)
    pairs = {}
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            shared = set(hit_sets[a]) & set(hit_sets[b])
            if shared:
                pairs[a + " + " + b] = {"contracts": len(shared), "tvl_usd": round(money_fn(sorted(shared)))}
    union = set().union(*hit_sets.values()) if hit_sets else set()
    return {"pairs": pairs, "any_cause": {"contracts": len(union), "tvl_usd": round(money_fn(sorted(union)))}}


# ---------------------------------------------------------------- [58] an alert with its proof

def reading_evidence(meta, so_rec, target, ka):
    """The reading behind an alert, machine-readable: which oracle was read, at which block and when, the score and its date as read, what the
    independent reader found (its blocks), and the call that redoes the oracle read. Missing parts are None, never made up.
    `meta` = {oracle, rpc, block, readAt} of the scores file; `so_rec` = the second_opinion record of the target or None."""
    ev = {"oracle": meta.get("oracle"), "oracle_block": meta.get("block"), "oracle_read_at": meta.get("readAt"),
          "composite": target.get("compositeScore"), "previous_composite": target.get("previousComposite"), "score_last_updated": target.get("lastUpdated"),
          "second_opinion": None, "reproduce": None, "reproduce_exact": False}
    if so_rec:
        ev["second_opinion"] = {k: so_rec.get(k) for k in ("kind", "path", "block_start", "block_end", "read_gap_seconds", "since_score_push_seconds")}
    if meta.get("oracle") and meta.get("rpc") and meta.get("block") and str(target.get("target", "")).startswith("0x"):
        ev["reproduce"] = "cast call %s 'getScore(address)' %s --rpc-url %s --block %s" % (meta["oracle"], target["target"], meta["rpc"], meta["block"])
        ev["reproduce_exact"] = meta.get("read_tag") == "pinned"   # a read made at `latest` is replayed at the block that was the head then: the nearest replay, not an identical one (the head may have moved between the two asks of a pass)
    return ev


# ---------------------------------------------------------------- [32] what became of a transfer of the admin that was in flight

def pending_family(via):
    """Which getter a `pending_via` sentence names: the four places a transfer can be designated."""
    v = str(via or "")
    if v.startswith("pendingDefaultAdmin"):
        return "default_admin"
    if "ProxyAdmin" in v:
        return "proxy_admin"
    if v.startswith("pendingAdmin"):
        return "contract_admin"
    if v.startswith("pendingOwner"):
        return "contract_owner"
    return None


def first_read_through_new_getter(prev_rec, pending_admin, pending_via):
    """True when a pending transfer is seen through `pendingDefaultAdmin()` and the previous record never read that getter (it has no `pending_getters` with it):
    the lot began to read it, so a transfer already in flight appears without anything having changed on chain. Not a change of the admin."""
    return bool(prev_rec) and bool(pending_admin) and pending_family(pending_via) == "default_admin" and "default_admin" not in (prev_rec.get("pending_getters") or [])


def transfer_outcome(prev_pending, holder_now, pending_now, short=lambda a: str(a).lower(), prev_via=None, clean_families=None):
    """Told at the run after a pending admin transfer was seen: 'accepted' (the holder is now the designated account), 'replaced' (another account is designated
    now), 'cleared' (the getter that showed the transfer answered, this run, that nothing is designated, and the holder as THIS record reads it is not the
    designated account: the transfer was cancelled, or it was accepted on a path the record does not read, such as the owner of a proxy's own admin contract;
    the two are not told apart),
    'unread' (that getter did not answer cleanly this run, or the previous run did not say which getter it was: nothing is told), or None when nothing was
    pending before. It is the difference between two readings: a transfer started and cancelled between two runs is not seen at all."""
    if not prev_pending:
        return None
    if holder_now and short(holder_now) == short(prev_pending):
        return "accepted"
    if pending_now:
        return None if short(pending_now) == short(prev_pending) else "replaced"
    fam = pending_family(prev_via)
    return "cleared" if fam is not None and fam in (clean_families or ()) else "unread"


PENDING_FOLLOW_NOTE = ("a transfer of the admin is read as a state at every run (about every 6 hours) and, since the second part of the readers, the events of the target contract and of its timelock "
                       "since the last block read are read too (`admin_events`, `event_windows`): a transfer started and cancelled on the TARGET inside a window that was read completely is seen as events. "
                       "Not read as events: the ProxyAdmin's own transfers, EIP-1967 AdminChanged, Compound NewPendingAdmin, RoleGranted and RoleRevoked; a window that could not be read completely "
                       "(`complete: false`) is read again at the next run; the outcome of a transfer that was seen is told at the next run (accepted, replaced, cleared or unread), by comparing the two readings; "
                       "cleared is a cancellation or an acceptance on a path the record does not read")


# ---------------------------------------------------------------- [17][86] does the node answer for the block that was asked

OLD_STATE_MARKERS = ("historical state", "trie node", "pruned", "not available", "missing", "state is not", "archive")


def block_honoured(latest_answer, old_answer=None, old_error=None):
    """True / False / None for 'does this node answer for the block that is asked': the same call is asked again at a block where the contract did not exist
    (block 1). True: the node answered differently (an empty answer or a revert: it looked at the old state). False: it gave the SAME answer as at the head, so
    the block tag is ignored. None: not told (no answer at the head to compare, a transport failure, or the node does not keep old state)."""
    if not isinstance(latest_answer, str) or latest_answer in ("", "0x"):
        return None
    if old_error:
        e = str(old_error).lower()
        if any(m in e for m in OLD_STATE_MARKERS):
            return None
        return True if "revert" in e or "no contract" in e or "empty" in e else None
    if old_answer is None:
        return None
    if old_answer in ("", "0x"):
        return True
    return False if old_answer == latest_answer else True


# ---------------------------------------------------------------- [58] an alert's proof can be replayed

def evidence_matches(reading, scores_doc, target):
    """Does the proof of an alert (`reading`, from reading_evidence) describe the read that is recorded in the scores file it came from? Offline replay: the oracle, the
    block, the time and the composite must be the ones of the file, the `reproduce` command must name that oracle, target, RPC and block. Returns (ok, [what differs])."""
    bad = []
    row = next((t for t in (scores_doc or {}).get("targets", []) if str(t.get("target")).lower() == str(target).lower()), None)
    if row is None:
        return False, ["the target is not in the scores file"]
    for k_ev, k_doc in (("oracle", "oracle"), ("oracle_block", "block"), ("oracle_read_at", "readAt")):
        if reading.get(k_ev) != scores_doc.get(k_doc):
            bad.append("%s %r != file %r" % (k_ev, reading.get(k_ev), scores_doc.get(k_doc)))
    if reading.get("composite") != row.get("compositeScore"):
        bad.append("composite %r != file %r" % (reading.get("composite"), row.get("compositeScore")))
    cmd = reading.get("reproduce") or ""
    for part in (scores_doc.get("oracle"), target, scores_doc.get("rpc"), "--block %s" % scores_doc.get("block")):
        if part is None or str(part).lower() not in cmd.lower():
            bad.append("the command does not name %r" % (part,))
    return (not bad), bad
