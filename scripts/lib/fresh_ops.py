"""Which queued operations the watch publishes (watch/pending_ops.json, its calendar, the per-target feeds, the alert rules and their evidence, the digests, the warning ledger).

A queued operation is published while it waits, and while it has been executable for at most FRESH_READY_DAYS days. One that became executable longer ago is not listed anywhere, whatever its state
(an expired one included): the same function decides in every writer, so the file, the calendar, the feeds, the rules, the digests and the ledger agree. Standard library only.
"""
FRESH_READY_DAYS = 7


def due_at(op):
    """When the operation can run, in unix seconds, or None: ready_at, else eta, else queued_at + delay (a cleared or still-queued row of the 'recent' list carries those)."""
    for k in ("ready_at", "eta"):
        if isinstance(op.get(k), (int, float)) and not isinstance(op.get(k), bool): return int(op[k])
    q, d = op.get("queued_at"), op.get("delay")
    return int(q + d) if isinstance(q, (int, float)) and isinstance(d, (int, float)) else None


def fresh_enough(state, ready_at, now):
    """True unless the operation became executable more than FRESH_READY_DAYS days ago. `state` is accepted for the callers' convenience and ignored: a waiting operation has a future ready_at,
    a ready one an older one, and an expired one is not published either once it is that old. No time given: published (nothing to compare)."""
    if not ready_at: return True
    return now - ready_at <= FRESH_READY_DAYS * 86400
