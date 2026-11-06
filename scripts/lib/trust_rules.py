"""The trust status of a tracked target: how far what the watch publishes about it can be relied on. Pure functions, no reading, no writing.

A SCORE says how strong the authority setup looks. A TRUST STATUS says how much of that score was actually checked, how old it is, whether anything
contradicts it, and whether the record that carries it is itself intact. The two are published side by side and never mixed: a target can score 90 and be
UNVERIFIED, or score 12 and be VERIFIED. Nothing here changes a score, a band or a methodology hash.

Written on 30 October 2026. Used by scripts/trust.py, which writes watch/trust.json.

THE RULE (version 1). For each target, every reason that applies is listed with its dimension, a state and an effect. A dimension takes the worst state
of its reasons. For the status, a reason with effect "decides" counts for the state it carries, one with effect "degrades" counts for PARTIAL at most, one with
effect "info" for nothing. The status is the first line that matches, from the top:

  UNAVAILABLE  a dimension is unavailable: the oracle holding the target was not read this run, or the trust computation itself failed (trust_not_computed).
  DISPUTED     a dimension is disputed: an open public dispute, or the independent reader disagrees and nobody has reviewed it.
  STALE        a dimension is stale: the on-chain score is stale, a pause or Safe-activity state has not been readable for 3 days or more (or for a time that
               is not known), the Watch run itself is older than 8 hours, or the independent reader's file is from an earlier run than the Watch's.
  UNVERIFIED   the independent reader did not read this target (no record, unreadable, or its input file missing), there is nothing to read
               independently (a native entity), or the score is dated later than the block it was read at (its staleness can never show).
  PARTIAL      something was checked and something was not: an incomplete reading (modules or admin members not all read, signers not classified, an admin
               the reader cannot contradict: a contract it did not resolve, a program-derived address), a method that differs or is fixed by decision, an
               alert not delivered, an unsigned run, a signing key that is not pinned (or cannot be compared), a broken journal, an input file that could not
               be read or is from an earlier run; the reasons say what.
  VERIFIED     none of the above. It means the checks listed here passed: not that the contract is safe, and not that the score is right.

A reason whose effect is "info" is listed and sets its dimension's state, but never moves the status (a contract with no pause getter, money that no
source figures). The eight dimensions: reading, coverage, method, signature, journal, notification, financial_exposure, surveillance.
Unknown is never ok: an input that could not be read puts its dimension in "unverified", not in "ok".

WHEN IT IS COMPUTED. trust.json is recomputed only when the Watch runs, right after the files of the run are written. If the Watch stops, the file that stays
published keeps its statuses: the rule cannot see its own silence. A consumer must compare `generated_utc` to the present time (the Watch runs every 6 hours;
a file older than about 8 hours says nothing about now).
"""
import calendar
import time

RULE_VERSION = "1"
STATUSES = ("VERIFIED", "PARTIAL", "STALE", "DISPUTED", "UNVERIFIED", "UNAVAILABLE")
DIMENSIONS = ("reading", "coverage", "method", "signature", "journal", "notification", "financial_exposure", "surveillance")
DIM_STATES = ("ok", "not_applicable", "partial", "unverified", "stale", "disputed", "unavailable")
_RANK = {s: i for i, s in enumerate(DIM_STATES)}
_RANK["not_applicable"] = 0
WATCH_MAX_AGE_HOURS = 8
MONEY_MAX_AGE_HOURS = 48
STATE_UNVERIFIED_DAYS = 3


def norm_addr(a):
    """The key form of an address: lower case for an EVM address, as is for a Solana one (base58 tells upper and lower case apart)."""
    return str(a).lower() if str(a).startswith("0x") else str(a)

# code -> (dimension, state, effect): the whole vocabulary of reasons, in one place so a test can check that nothing else is ever emitted
REASONS = {
    "oracle_not_read": ("surveillance", "unavailable", "decides"),
    "trust_not_computed": ("surveillance", "unavailable", "decides"),
    "dispute_open": ("reading", "disputed", "decides"),
    "reader_disagrees": ("reading", "disputed", "decides"),
    "reader_disagreement_acknowledged": ("reading", "partial", "degrades"),
    "score_stale": ("reading", "stale", "decides"),
    "independent_read_missing": ("reading", "unverified", "decides"),
    "independent_read_unreadable": ("reading", "unverified", "decides"),
    "native_entity": ("reading", "unverified", "decides"),
    "score_row_unreadable": ("reading", "unverified", "decides"),      # the row of the score file has no composite between 0 and 100: nothing to rely on
    "stale_flag_unknown": ("reading", "unverified", "decides"),         # the row says neither stale nor fresh (isStale is missing or not a boolean): unknown is never ok
    "block_not_honoured": ("reading", "unverified", "decides"),      # the node ignores the block tag (its probe answered for block 1 as for the head): a reading pinned to a block cannot be replayed
    "score_future_dated": ("reading", "unverified", "decides"),      # lastUpdated is later than the time of the block read (future_dated in the score file): the on-chain staleness check measures from that date, so the score never turns stale
    "modules_truncated": ("reading", "partial", "degrades"),
    "modules_unread": ("reading", "partial", "degrades"),
    "reader_cannot_contradict": ("reading", "partial", "degrades"),
    "admin_members_not_weighed": ("reading", "partial", "degrades"),
    "admin_events_unread": ("coverage", "partial", "degrades"),
    "executor_open": ("coverage", "ok", "info"),
    "safe_signers_unclassified": ("reading", "partial", "degrades"),
    "admin_members_unread": ("reading", "partial", "degrades"),
    "score_fixed_by_decision": ("method", "partial", "degrades"),
    "method_hash_differs": ("method", "partial", "degrades"),
    "oracle_method_mixed": ("method", "ok", "info"),
    "method_version_unregistered": ("method", "ok", "info"),
    "state_unverified_pause": ("coverage", "stale", "decides"),
    "state_unverified_safe_activity": ("coverage", "stale", "decides"),
    "state_stale_pause": ("coverage", "partial", "degrades"),
    "state_stale_safe_activity": ("coverage", "partial", "degrades"),
    "pause_unread": ("coverage", "unverified", "degrades"),
    "side_roles_unread": ("coverage", "unverified", "degrades"),
    "side_roles_stale": ("coverage", "partial", "degrades"),
    "pause_no_getter": ("coverage", "ok", "info"),     # the reader cannot tell "no pause getter" from "the RPC did not answer for this contract" (pause_state.py drops both): the detail says so
    "side_roles_not_covered": ("coverage", "ok", "info"),
    "run_unsigned": ("signature", "partial", "degrades"),
    "signature_previous_run_missing": ("signature", "partial", "degrades"),      # the manifest on file is older than the previous run: the previous run was not signed (signing refused or failed), its signature.json is the one of an earlier run
    "signature_unread": ("signature", "unverified", "degrades"),
    "signature_key_not_pinned": ("signature", "partial", "degrades"),
    "signature_key_unverifiable": ("signature", "unverified", "degrades"),
    "journal_broken": ("journal", "partial", "degrades"),
    "journal_unread": ("journal", "unverified", "degrades"),
    "alert_undelivered": ("notification", "partial", "degrades"),
    "money_unknown": ("financial_exposure", "unverified", "info"),
    "money_stale": ("financial_exposure", "stale", "info"),
    "money_unread": ("financial_exposure", "unverified", "info"),
    "money_out_of_scope": ("financial_exposure", "not_applicable", "info"),
    "watch_old": ("surveillance", "stale", "decides"),
    "oracle_self_watch_unread": ("surveillance", "partial", "degrades"),
    "scan_gap": ("surveillance", "partial", "degrades"),
    # an input file the run could not read: the dimension it feeds cannot be called ok
    "input_missing:second_opinion": ("reading", "unverified", "decides"),
    "input_missing:pause_state": ("coverage", "unverified", "degrades"),
    "input_missing:safe_activity": ("coverage", "unverified", "degrades"),
    "input_missing:side_roles": ("coverage", "unverified", "degrades"),
    "input_missing:tvl": ("financial_exposure", "unverified", "info"),
    "input_missing:held_assets": ("financial_exposure", "unverified", "info"),
    "input_missing:alerts": ("notification", "unverified", "degrades"),
    "input_missing:methodology": ("method", "unverified", "degrades"),
    "input_missing:disputes": ("reading", "unverified", "degrades"),
    # an input file that is there but is from an earlier run (a step that failed leaves the previous file in place)
    "input_stale:second_opinion": ("reading", "stale", "decides"),
    "input_stale:pause_state": ("coverage", "partial", "degrades"),
    "input_stale:safe_activity": ("coverage", "partial", "degrades"),
    "input_stale:side_roles": ("coverage", "partial", "degrades"),
    "input_stale:tvl": ("financial_exposure", "stale", "info"),
    "input_stale:held_assets": ("financial_exposure", "stale", "info"),
    "input_stale:alerts": ("notification", "partial", "degrades"),
    "input_stale:methodology": ("method", "partial", "degrades"),
    "input_stale:disputes": ("reading", "partial", "degrades"),
}
# Would a later Watch run, with no change to the code, the data or the contract, take the reason away? A consumer that gets PARTIAL or STALE and is told to wait
# must know whether waiting can help. Every code of REASONS is in exactly one of the two sets (a test fails when a new code is in neither).
TRANSIENT = frozenset({
    "oracle_not_read", "trust_not_computed", "score_stale", "modules_unread", "admin_events_unread", "admin_members_unread", "state_unverified_pause", "state_unverified_safe_activity",
    "state_stale_pause", "state_stale_safe_activity", "pause_unread", "side_roles_unread", "side_roles_stale", "signature_unread", "signature_key_unverifiable", "journal_unread",
    "alert_undelivered", "signature_previous_run_missing", "watch_old", "oracle_self_watch_unread", "scan_gap", "score_row_unreadable", "stale_flag_unknown",
    "input_missing:second_opinion", "input_missing:pause_state", "input_missing:safe_activity", "input_missing:side_roles", "input_missing:tvl", "input_missing:held_assets",
    "input_missing:alerts", "input_missing:methodology", "input_missing:disputes",
    "input_stale:second_opinion", "input_stale:pause_state", "input_stale:safe_activity", "input_stale:side_roles", "input_stale:tvl", "input_stale:held_assets", "input_stale:alerts",
    "input_stale:methodology", "input_stale:disputes",
})
PERMANENT = frozenset({
    "dispute_open", "reader_disagrees", "reader_disagreement_acknowledged", "independent_read_missing", "independent_read_unreadable", "native_entity", "modules_truncated",
    "reader_cannot_contradict", "admin_members_not_weighed", "safe_signers_unclassified", "score_fixed_by_decision", "method_hash_differs", "run_unsigned", "signature_key_not_pinned",
    "journal_broken", "oracle_method_mixed", "method_version_unregistered", "executor_open", "pause_no_getter", "side_roles_not_covered", "money_unknown", "money_stale", "money_unread",
    "money_out_of_scope", "block_not_honoured", "score_future_dated",
})
INPUT_DATE_FIELD = {"second_opinion": "generated_utc", "pause_state": "generated_utc", "safe_activity": "generated_utc", "side_roles": "generated_utc", "tvl": "generated_utc",
                    "held_assets": "generated_utc", "alerts": "evaluated_utc", "methodology": "generated_utc", "disputes": "run_utc"}
INPUT_MAX_LAG_SECONDS = 3600   # every input is written AFTER latest.run_utc by the steps that follow the Watch (+10 to +25 minutes in the run of 29/10); one written more than an hour BEFORE it is the file of an earlier run (a step that failed leaves it in place)
SEV = {"info": 0, "medium": 1, "high": 2}   # as scripts/evaluate_rules.py
SCORE_FUTURE_TOLERANCE_SECONDS = 300   # as LASTUPDATED_FUTURE_TOLERANCE in scripts/lib/reader_audit.py: the pusher's clock can be a little ahead of the chain's


def _epoch(utc):
    try:
        return calendar.timegm(time.strptime(utc, "%Y-%m-%dT%H:%M:%SZ"))
    except (TypeError, ValueError):
        return None


def _is_int(x):
    return isinstance(x, int) and not isinstance(x, bool)


def _get(d, *path):
    for p in path:
        if not isinstance(d, dict):
            return None
        d = d.get(p)
    return d


def stale_days(rec, generated_utc):
    """Days a stale record has gone unread (None for a record read this run, or one whose date cannot be told)."""
    if not isinstance(rec, dict) or not rec.get("stale"):
        return None
    s, g = _epoch(rec.get("stale_since")), _epoch(generated_utc)
    return None if s is None or g is None else max(0.0, (g - s) / 86400)


def run_reasons(inputs, now, key_present):
    """The reasons that hold for EVERY target of the run: the signature, the journal, the age of the run, the missing input files.
    Returns {code: detail}. `inputs` maps a file name to its parsed content or None when it could not be read."""
    out = {}
    sig, chain, latest = inputs.get("signature"), inputs.get("chain"), inputs.get("latest")
    # the signature of THIS run is made after this file (the manifest covers this file): what can be said here is whether the key is present now, what the
    # PREVIOUS manifest says (signed or not, by which key) and nothing about the signature that will be made after. It is not a verification of any signature.
    if not isinstance(sig, dict):
        out["signature_unread"] = "watch/signature.json could not be read"
    elif not sig.get("signed") or not key_present:
        out["run_unsigned"] = "the run is not signed (" + ("the previous manifest says signed: false" if not sig.get("signed") else "no signing key in this run") + ")"
    elif not inputs.get("pinned_keys"):
        out["signature_key_unverifiable"] = "no list of pinned keys could be loaded (audit_public.PINNED_KEYS): the key of the previous manifest cannot be compared"
    elif str(sig.get("public_key", "")).lower() not in {k.lower() for k in inputs["pinned_keys"]}:
        out["signature_key_not_pinned"] = "the previous manifest is signed by a key that is not pinned (audit_public.PINNED_KEYS): a valid signature by another key proves the files match what that key signed, not who holds it"
    if isinstance(sig, dict) and sig.get("signed"):
        sig_t, prev_t = _epoch(sig.get("run_utc")), _epoch(_get(latest, "previous_run_utc"))
        if sig_t is not None and prev_t is not None and sig_t < prev_t:      # this file is written BEFORE this run is signed, so the manifest on file should be the previous run's
            out["signature_previous_run_missing"] = "the manifest on file is from %s, before the previous run (%s): that run was not signed" % (sig.get("run_utc"), _get(latest, "previous_run_utc"))
    if not isinstance(chain, dict):
        out["journal_unread"] = "watch/chain.json could not be read"
    elif chain.get("ok") is not True:
        out["journal_broken"] = "the hash chain of events.jsonl does not verify (chain.json ok is not true)"
    run_t = _epoch(_get(latest, "run_utc"))
    if run_t is None:
        out["watch_old"] = "the time of the Watch run is not known"
    elif now - run_t > WATCH_MAX_AGE_HOURS * 3600:
        out["watch_old"] = "the Watch run is %d hours old (limit %d)" % ((now - run_t) // 3600, WATCH_MAX_AGE_HOURS)
    for name, code in (("second_opinion", "input_missing:second_opinion"), ("pause_state", "input_missing:pause_state"), ("safe_activity", "input_missing:safe_activity"),
                       ("side_roles", "input_missing:side_roles"), ("tvl", "input_missing:tvl"), ("held_assets", "input_missing:held_assets"), ("alerts", "input_missing:alerts"),
                       ("methodology", "input_missing:methodology"), ("disputes", "input_missing:disputes")):
        if not isinstance(inputs.get(name), dict):
            out[code] = "watch/%s.json could not be read" % name
    for name, field in INPUT_DATE_FIELD.items():       # a reader that failed leaves the previous run's file in place: its date is compared to the Watch run's
        doc = inputs.get(name)
        if not isinstance(doc, dict) or run_t is None:
            continue
        g = _epoch(doc.get(field))
        if g is None:
            out["input_stale:" + name] = "watch/%s.json carries no usable date (%s)" % (name, field)
        elif run_t - g > INPUT_MAX_LAG_SECONDS:
            out["input_stale:" + name] = "watch/%s.json was written %d hours before the Watch run it is read with: a step that failed leaves the file of an earlier run in place" % (name, (run_t - g) // 3600)
    return out


def _dominant_hash(rows):
    counts = {}
    for t in rows:
        h = t.get("methodologyHash")
        if h:
            counts[h] = counts.get(h, 0) + 1
    return max(counts, key=counts.get) if counts else None


def derive_all(inputs, now, key_present, fixed_targets=frozenset(), evm_chains=None):
    """{target key: trust record} for every target of every scores file in `inputs["scores"]` ({slug: document}).
    `fixed_targets`: lower-case addresses whose scorer reads a configuration and publishes constants (data/scorer_pins.json).
    Target keys are '<chain>:<address>' with the chain key of the Watch (`watch_slugs`)."""
    watch_slugs = inputs.get("watch_slugs") or {}
    latest_by_slug = {o.get("slug"): o for o in (_get(inputs.get("latest"), "oracles") or []) if isinstance(o, dict)}
    run_rs = run_reasons(inputs, now, key_present)
    so = {}
    for r in (_get(inputs.get("second_opinion"), "results") or []):
        if isinstance(r, dict) and not r.get("oracle_self"):
            so[str(r.get("chain")) + ":" + norm_addr(r.get("target"))] = r
    pause, side = _get(inputs.get("pause_state"), "by_target") or {}, _get(inputs.get("side_roles"), "by_target") or {}
    pause_unread = set(_get(inputs.get("pause_state"), "unread_chains") or []); side_unread = set(_get(inputs.get("side_roles"), "unread_chains") or [])
    held_unread = set(_get(inputs.get("held_assets"), "unread_chains") or [])
    no_getter = set(_get(inputs.get("side_roles"), "no_getter_recognised") or [])
    safes = {}
    for rec in (_get(inputs.get("safe_activity"), "by_safe") or {}).values():
        for tk in (rec.get("governs") or []) if isinstance(rec, dict) else []:
            safes.setdefault(tk, []).append(rec)
    held, tvl = _get(inputs.get("held_assets"), "by_target") or {}, _get(inputs.get("tvl"), "matched") or {}
    scope = inputs.get("tvl_scope") or {}
    disputes = _get(inputs.get("disputes"), "by_target") or {}
    undelivered = {}
    chain_key = inputs.get("chain_labels") or {}                  # alerts.json carries the DISPLAY name of the chain ("Robinhood Chain"), the trust key the Watch's own ("robinhood")
    min_sev = SEV.get(inputs.get("notify_min_severity") or "medium", 1)
    for a in (_get(inputs.get("alerts"), "active") or []):
        if isinstance(a, dict) and a.get("notified") is False and SEV.get(a.get("severity"), 0) >= min_sev:      # an alert under the severity that is sent stays `notified: false` for ever, by design
            undelivered.setdefault(chain_key.get(str(a.get("chain")), str(a.get("chain"))) + ":" + norm_addr(a.get("target")), []).append(a.get("rule"))
    meth = inputs.get("methodology")
    mixed = {m.get("oracle"): m for m in (_get(meth, "mixed") or []) if isinstance(m, dict)}
    unregistered = {h for h, v in (_get(meth, "hashes") or {}).items() if isinstance(v, dict) and v.get("method_version") is None}
    out = {}
    for slug, doc in (inputs.get("scores") or {}).items():
        key = watch_slugs.get(slug) or ("solana" if (doc or {}).get("kind") == "solana" else None)
        if not key or not isinstance(doc, dict):
            continue
        oracle_row = latest_by_slug.get(slug) or {}
        rows = doc.get("targets") or []
        dom = _dominant_hash(rows)
        for t in rows:
            ka = key + ":" + norm_addr(t.get("target"))
            rs = dict(run_rs)
            if oracle_row.get("read_ok") is False:
                rs["oracle_not_read"] = "the oracle %s was not read this run" % slug
            elif oracle_row and _get(oracle_row, "self_watch", "read") is False and doc.get("kind") == "evm":
                rs["oracle_self_watch_unread"] = "the scan of the oracle's own role events was not read"
            if _get(doc, "self", "gap_blocks") or int(doc.get("scan_stalled_runs") or 0) >= 2:
                rs["scan_gap"] = "the scan of the oracle's own role events has a hole or has not advanced"
            if _get(doc, "block_probe", "honoured") is False:                  # only an explicit False: a node that is merely not told (None) is not accused
                rs["block_not_honoured"] = "the node answered for block 1 as it did for the head: it ignores the block tag, so a read pinned to a block says nothing about that block"
            comp = t.get("compositeScore")
            if not (isinstance(comp, int) and not isinstance(comp, bool) and 0 <= comp <= 100):
                rs["score_row_unreadable"] = "the score row carries no composite between 0 and 100"
            if not isinstance(t.get("stale"), bool):
                rs["stale_flag_unknown"] = "the score row says neither stale nor fresh (isStale is missing or not true/false)"
            if t.get("stale") is True:
                rs["score_stale"] = "the on-chain score is stale (isStale)"
            lu, ref = t.get("lastUpdated"), (doc.get("block_time") if _is_int(doc.get("block_time")) else (doc.get("readAt") if _is_int(doc.get("readAt")) else None))
            if norm_addr(t.get("target")) in {norm_addr(x) for x in (doc.get("future_dated") or []) if isinstance(x, str)} or (_is_int(lu) and ref is not None and lu > ref + SCORE_FUTURE_TOLERANCE_SECONDS):
                rs["score_future_dated"] = "the score is dated later than the time it was read at (lastUpdated %s, read at %s): its staleness cannot show" % (lu, ref)
            h = t.get("methodologyHash")
            if dom and h and h != dom:
                rs["method_hash_differs"] = "scored by a different method hash than the other targets of its oracle"
            if slug in mixed:
                rs["oracle_method_mixed"] = "the oracle holds more than one method hash"
            if h in unregistered:
                rs["method_version_unregistered"] = "this method hash has no version in data/method_versions.json"
            if norm_addr(t.get("target")) in fixed_targets or t.get("evaluation") == "fixed_by_decision":
                rs["score_fixed_by_decision"] = "the scorer reads this configuration and publishes constants (data/scorer_pins.json)"
            d = disputes.get(ka)
            if isinstance(d, list) and any(isinstance(x, dict) and x.get("status") == "open" for x in d):
                rs["dispute_open"] = "a public dispute of this score is open"
            r = so.get(ka)
            if isinstance(inputs.get("second_opinion"), dict):
                if r is None:
                    rs["independent_read_missing"] = "the independent reader has no record of this target"
                elif r.get("kind") == "unreadable":
                    rs["independent_read_unreadable"] = str(r.get("why") or "the independent reader could not classify the admin")[:160]
                elif r.get("kind") == "native":
                    rs["native_entity"] = "no contract code at this address: nothing for the independent reader to read"
                else:
                    if r.get("disagree"):
                        rs["reader_disagreement_acknowledged" if r.get("acknowledged") else "reader_disagrees"] = str(r["disagree"])[:160]
                    if r.get("modules_truncated") is True:
                        rs["modules_truncated"] = "the Safe has more modules than the page of 50 the reader fetched"
                    elif r.get("kind") == "safe" and (r.get("modules") is None or r.get("modules_truncated") is not False):
                        rs["modules_unread"] = "the modules of the Safe could not be read, or the reader did not say whether the list is complete (a module executes without the signatures)"
                    if str(r.get("path") or "").startswith("DEFAULT_ADMIN_ROLE member") and not r.get("admin_members"):
                        rs["admin_members_unread"] = "the admin role has several holders and the reader did not say how many it read"
                    if isinstance(r.get("admin_members"), dict) and (_get(r, "admin_members", "unread") or _get(r, "admin_members", "total") is None or _get(r, "admin_members", "unread") is None):
                        rs["admin_members_unread"] = str(_get(r, "admin_members", "note") or "the number of members of the admin role was not read")[:160]
                    if (_get(r, "admin_members_gap", "not_weighed") or 0) > 0:
                        rs["admin_members_not_weighed"] = str(_get(r, "admin_members_gap", "text") or "other holders of the admin role are not in the reading")[:160]
                    if r.get("open_executor") is True:
                        rs["executor_open"] = "address(0) holds EXECUTOR_ROLE on the timelock: anyone can execute a ready operation"
                    if r.get("kind") == "safe" and (_get(r, "owners_kinds", "unread") or 0) > 0:
                        rs["safe_signers_unclassified"] = "%d signer(s) of the Safe could not be classified (key, Safe, timelock, contract)" % _get(r, "owners_kinds", "unread")
                    if r.get("kind") == "pda" or (r.get("kind") == "contract" and not r.get("behind")):
                        rs["reader_cannot_contradict"] = ("the admin is a program-derived address: the reader names it and cannot show who controls it" if r.get("kind") == "pda" else
                                                          "the admin is a contract the reader did not resolve to a key, a Safe or a timelock: its agreement with the score checks nothing")
            if _get(inputs.get("second_opinion"), "event_windows", key, "complete") is False and r is not None and r.get("kind") not in ("native",):
                rs["admin_events_unread"] = "the admin events of the window since the previous record could not be read completely: a transfer started and cancelled inside it was not seen"
            pr = pause.get(ka)
            if isinstance(inputs.get("pause_state"), dict):
                if pr is None and doc.get("kind") == "evm":
                    rs["pause_unread" if key in pause_unread else "pause_no_getter"] = ("the pause reads of this chain got no answer this run" if key in pause_unread else "no pause reading for this contract: it has no paused() / isPaused(), or the RPC did not answer for it (the reader cannot tell the two apart)")
                elif pr and pr.get("stale"):
                    d_ = stale_days(pr, _get(inputs.get("pause_state"), "generated_utc"))
                    if d_ is None or d_ >= STATE_UNVERIFIED_DAYS:
                        rs["state_unverified_pause"] = "the pause state has not been readable for %s" % ("an unknown time" if d_ is None else "%.0f days" % d_)
                    else:
                        rs["state_stale_pause"] = "the pause state was kept from an earlier run (%.1f days)" % d_
            if isinstance(inputs.get("safe_activity"), dict):
                for sr in safes.get(ka, []):
                    if sr.get("stale"):
                        d_ = stale_days(sr, _get(inputs.get("safe_activity"), "generated_utc"))
                        if d_ is None or d_ >= STATE_UNVERIFIED_DAYS:
                            rs["state_unverified_safe_activity"] = "the activity of the Safe that governs it has not been readable for %s" % ("an unknown time" if d_ is None else "%.0f days" % d_)
                        elif "state_unverified_safe_activity" not in rs:
                            rs["state_stale_safe_activity"] = "the Safe activity was kept from an earlier run (%.1f days)" % d_
            if isinstance(inputs.get("side_roles"), dict):
                if doc.get("kind") == "evm" and key in side_unread and ka not in side:
                    rs["side_roles_unread"] = "the secondary-role reads of this chain got no answer this run"
                sr_ = side.get(ka) or {}
                if any(isinstance(v, dict) and v.get("stale") for v in (sr_.get("roles") or {}).values()):
                    rs["side_roles_stale"] = "a secondary role was kept from an earlier run because its getter did not answer"
                if ka in no_getter:
                    rs["side_roles_not_covered"] = "none of the seven role getters is recognised on this contract"
            if ka in undelivered:
                rs["alert_undelivered"] = "an alert on this target has not reached every channel: " + ", ".join(sorted(str(x) for x in undelivered[ka])[:3])
            if (scope.get(ka) or {}).get("scope") in ("retired", "peripheral"):
                rs["money_out_of_scope"] = "retired or peripheral: carries none of its protocol's money"
            elif isinstance(inputs.get("tvl"), dict) and ka not in tvl and (held.get(ka) or {}).get("held_usd") is None:   # a held amount of 0 is a known zero, not an unknown
                rs["money_unread" if key in held_unread else "money_unknown"] = ("the held-assets reads of this chain got no answer this run" if key in held_unread else "no source figures the money behind this contract")
            else:
                h_ = held.get(ka) or {}
                tvl_t = _epoch(_get(inputs.get("tvl"), "generated_utc"))
                if h_.get("stale") is True or (isinstance(h_.get("price_at"), int) and now - h_["price_at"] > MONEY_MAX_AGE_HOURS * 3600) or (ka in tvl and tvl_t is not None and now - tvl_t > MONEY_MAX_AGE_HOURS * 3600):
                    rs["money_stale"] = "the money figure behind this contract is older than %d hours" % MONEY_MAX_AGE_HOURS
            out[ka] = _record(rs)
    return out


def _record(reasons):
    dims = {d: {"state": "ok", "reasons": []} for d in DIMENSIONS}
    for code in sorted(reasons):
        dim, state, effect = REASONS[code]
        dims[dim]["reasons"].append(code)
        if _RANK[state] > _RANK[dims[dim]["state"]]:
            dims[dim]["state"] = state
    # the status: a reason whose effect is "decides" counts for its own state, one that "degrades" counts for at most PARTIAL, one that is "info" for nothing
    levels = set()
    for code in reasons:
        dim, state, effect = REASONS[code]
        if effect == "decides":
            levels.add(state)
        elif effect == "degrades":
            levels.add("partial")
    if "unavailable" in levels:
        status = "UNAVAILABLE"
    elif "disputed" in levels:
        status = "DISPUTED"
    elif "stale" in levels:
        status = "STALE"
    elif "unverified" in levels:
        status = "UNVERIFIED"
    elif "partial" in levels:
        status = "PARTIAL"
    else:
        status = "VERIFIED"
    blocking = [c for c in reasons if REASONS[c][2] != "info"]
    return {"status": status, "reasons": [{"code": c, "dimension": REASONS[c][0], "effect": REASONS[c][2], "detail": reasons[c]} for c in sorted(reasons)],
            "dimensions": {d: dims[d]["state"] for d in DIMENSIONS},
            # true only when VERIFIED is not reached yet and every reason that holds it back would go away at a later run of the Watch by itself (see TRANSIENT): waiting can help.
            # false for VERIFIED (nothing to wait for) and for a status held back by a reason that needs a change in the code, the data or the contract.
            "retry_may_help": bool(blocking) and all(c in TRANSIENT for c in blocking)}


def summary(records):
    counts = {s: 0 for s in STATUSES}
    for r in records.values():
        counts[r["status"]] += 1
    dim = {d: {s: 0 for s in DIM_STATES} for d in DIMENSIONS}
    for r in records.values():
        for d, s in r["dimensions"].items():
            dim[d][s] += 1
    return counts, dim
