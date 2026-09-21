"""
Optional push layer on top of the recurring updater.

Two independent things live here:
- a Telegram notifier, no-op (never raises) if TELEGRAM_BOT_TOKEN /
  TELEGRAM_CHAT_ID aren't set, so the scoring pipeline never depends on
  alerting being configured
- a diff between the previous published snapshot (api/scores.json) and the
  freshly re-derived scores, producing one alert per target whose risk got
  meaningfully worse -- never for an improvement, this is a risk feed, not
  a changelog

Uses only the standard library (urllib) rather than adding `requests` as a
dependency for one POST call.
"""
from __future__ import annotations  # dict | None / list[dict] hints, Python 3.9-safe

import json
import os
import urllib.error
import urllib.request

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"

# A drop below this many points on an existing target's compositeScore
# triggers an alert even if the band (see dashboard's band()) didn't change --
# catches e.g. 55 -> 46, both "moderate", still a real move worth flagging.
DROP_THRESHOLD = 10

# A brand-new target first published below this composite score is worth a
# heads-up on its own, independent of any prior value to diff against.
NEW_TARGET_ALERT_CEILING = 40


def send_telegram_alert(message: str) -> bool:
    """POST one message to the configured Telegram chat. Returns False (never
    raises) if alerting isn't configured or the request fails -- alerting is
    a convenience layer, never allowed to break the scoring pipeline."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return False

    payload = json.dumps(
        {"chat_id": chat_id, "text": message, "disable_web_page_preview": True}
    ).encode("utf-8")
    req = urllib.request.Request(
        TELEGRAM_API.format(token=token),
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return 200 <= resp.status < 300
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError):
        return False


def _band(score: int) -> str:
    if score < 20:
        return "CRITICAL"
    if score < 40:
        return "WEAK"
    if score < 60:
        return "MODERATE"
    if score < 80:
        return "DECENT"
    return "STRONG"


def diff_alerts(previous_snapshot: dict | None, current_scores: list[dict]) -> list[str]:
    """Compare the last published api/scores.json (or None if this is the
    first publish) against the freshly re-derived scores. Returns formatted
    alert strings, worst first -- empty list if nothing crossed a threshold.

    ADDED 2026-09-22: this used to only ever iterate `current_scores`, so a target present in
    `previous_snapshot` but ABSENT from `current_scores` -- because score_all() skipped it this run
    over a persistent RPC failure (see web3_utils.RpcUnavailable, and this file's DROP/NEW alerts
    above, which this closes the gap next to) -- produced no alert at all: not a wrong number, an
    invisible omission from api/scores.json with nothing in either the alert stream or the JSON
    itself saying so. scripts/update_scores.py's own completeness guard is the first line of
    defense (it can refuse to publish); this is the second, for whatever count it does let through."""
    previous_by_target = {}
    if previous_snapshot:
        for entry in previous_snapshot.get("scores", []):
            previous_by_target[entry["target"].lower()] = entry

    current_targets = {entry["target"].lower() for entry in current_scores}
    alerts = []
    for entry in current_scores:
        target = entry["target"].lower()
        label = entry.get("label", target)
        new_score = entry["compositeScore"]
        prev = previous_by_target.get(target)

        if prev is None:
            if new_score <= NEW_TARGET_ALERT_CEILING:
                alerts.append(
                    f"[NEW · {_band(new_score)} {new_score}/100] {label} ({entry['target']})"
                )
            continue

        old_score = prev["compositeScore"]
        drop = old_score - new_score
        old_band, new_band = _band(old_score), _band(new_score)
        if drop >= DROP_THRESHOLD or (old_band != new_band and new_score < old_score):
            alerts.append(
                f"[DROP · {old_band} {old_score} -> {new_band} {new_score}] {label} ({entry['target']})"
            )

    # `current_scores` being entirely empty means this run produced NOTHING, not a partial skip --
    # that's scripts/update_scores.py's own completeness guard's job to refuse before ever reaching
    # here (or, if it somehow still does, main()'s own run-FAILED alert), not this function's to
    # enumerate as N individual MISSING targets. Matches the pre-existing
    # test_empty_current_scores_no_alerts contract.
    for target, prev in (previous_by_target.items() if current_scores else ()):
        if target not in current_targets:
            label = prev.get("label", target)
            alerts.append(
                f"[MISSING · was {_band(prev['compositeScore'])} {prev['compositeScore']}/100] "
                f"{label} ({prev['target']}) -- published last run, absent from this one "
                f"(likely skipped over a persistent RPC failure, not a real removal)"
            )

    # FIXED 2026-09-17 (caught by a new unit test, scripts/lib/tests/test_alerts.py):
    # this comment used to claim "NEW before DROP" -- plain alphabetical sort on
    # "[DROP..." vs "[NEW..." actually orders "D" before "N", so DROP alerts sort
    # first. Comment corrected to describe the real behavior rather than changing
    # the sort itself (no strong basis this pass to say NEW-first was the intended
    # design rather than a stale comment).
    alerts.sort(key=lambda line: line.split("]")[0])  # DROP before NEW, both internally grouped
    return alerts


def format_summary(alerts: list[str], dashboard_url: str) -> str:
    header = f"Authority Risk Oracle: {len(alerts)} target(s) worth a look this run\n"
    body = "\n".join(alerts)
    return f"{header}\n{body}\n\n{dashboard_url}"
