"""Pure helpers for the second part of the readers (30/10/2026): what the independent reader says about the admin events of the last window, the delay of a
timelock and of the default admin, an executor that anyone can use, and the holders of an admin role that the score does not weigh.

Nothing here reads the chain or writes a file: every function takes what was read and returns what to say. The caller (scripts/second_opinion.py) does the reads.
No scoring file, no hashed file imports this module.

THE WINDOW. A transfer of the admin that is started and cancelled between two runs (about 6 hours) is invisible to a reader that only reads state. The reader now also
reads the EVENTS of the contract over the blocks between the previous record and this one (`window_for`), in chunks (`scan_logs`): OwnershipTransferStarted,
OwnershipTransferred, DefaultAdminTransferScheduled, DefaultAdminTransferCanceled on the target, MinDelayChange (OpenZeppelin) and NewDelay (Compound) on its timelock.
A window that could not be read completely is said so (`complete: false`); it is never an empty list. A first run has no window (`null`, with the reason).
"""

# topic0 of the events read, and the selectors / role hashes (checked against keccak in the tests)
OWNERSHIP_TRANSFER_STARTED = "0x38d16b8cac22d99fc7c124b9cd0de2d3fa1faef420bfe791d8c362d765e22700"
OWNERSHIP_TRANSFERRED = "0x8be0079c531659141344cd1fd0a4f28419497f9722a3daafe3b4186f6b6457e0"
DEFAULT_ADMIN_TRANSFER_SCHEDULED = "0x3377dc44241e779dd06afab5b788a35ca5f3b778836e2990bdb26a2a4b2e5ed6"
DEFAULT_ADMIN_TRANSFER_CANCELED = "0x8886ebfc4259abdbc16601dd8fb5678e54878f47b3c34836cfc51154a9605109"
DEFAULT_ADMIN_DELAY_CHANGE_SCHEDULED = "0xf1038c18cf84a56e432fdbfaf746924b7ea511dfe03a6506a0ceba4888788d9b"
MIN_DELAY_CHANGE = "0x11c24f4ead16507c69ac467fbd5e4eed5fb5c699626d2cc6d66421df253886d5"
NEW_DELAY = "0x948b1f6a42ee138b7e34058ba85a37f716d55ff25ff05a763f15bed6a04c8d2c"
ADMIN_TOPICS = (OWNERSHIP_TRANSFER_STARTED, OWNERSHIP_TRANSFERRED, DEFAULT_ADMIN_TRANSFER_SCHEDULED, DEFAULT_ADMIN_TRANSFER_CANCELED, DEFAULT_ADMIN_DELAY_CHANGE_SCHEDULED)
DELAY_TOPICS = (MIN_DELAY_CHANGE, NEW_DELAY)
NAMES = {OWNERSHIP_TRANSFER_STARTED: "OwnershipTransferStarted", OWNERSHIP_TRANSFERRED: "OwnershipTransferred",
         DEFAULT_ADMIN_TRANSFER_SCHEDULED: "DefaultAdminTransferScheduled", DEFAULT_ADMIN_TRANSFER_CANCELED: "DefaultAdminTransferCanceled",
         DEFAULT_ADMIN_DELAY_CHANGE_SCHEDULED: "DefaultAdminDelayChangeScheduled",
         MIN_DELAY_CHANGE: "MinDelayChange", NEW_DELAY: "NewDelay"}
DEFAULT_ADMIN_DELAY_SEL = "0xcc8463c8"        # defaultAdminDelay() -> uint48 (AccessControlDefaultAdminRules)
HAS_ROLE_SEL = "0x91d14854"                   # hasRole(bytes32,address)
EXECUTOR_ROLE = "d8aa0f3194971a2a116679f7c2090f6939c8d4e01a2a8d7e41d55e5351469e63"
ZERO_ADDRESS_WORD = "0" * 64

MAX_WINDOW_BLOCKS = 600_000     # a window longer than this is cut to its last blocks and said so (and counts as NOT read completely)
LOG_STEP_BLOCKS = 100_000       # one eth_getLogs asks for at most this many blocks, unless the chain is in LOG_STEP_BY_CHAIN
# measured 30/10/2026 with the filter of the reader (1 address, 6 topics in OR; lectures-getlogs.txt): the widest range each RPC accepts. Monad refuses 200 blocks (100 is the largest
# that answered), Hyperliquid answers up to 1000 but rate-limits, Plasma refuses 100000, mainnet.base.org answered 429 to every width. A window that needs more calls than MAX_LOG_CALLS is incomplete.
LOG_STEP_BY_CHAIN = {"monad": 100, "hyperliquid": 1000, "plasma": 10_000, "base": 10_000}
MAX_LOG_CALLS = 60              # per chain and run
MAX_EVENTS_PER_RECORD = 10


def window_for(prev_block_end, block_end, max_blocks=MAX_WINDOW_BLOCKS):
    """{from, to, cut} for the events between the last block already read and this one, or {reason} when there is none to read. `prev_block_end` is the last block whose
    events were read completely (`scanned_to` of the previous run) or, for the first run of this lot, the `block_end` of the previous record; `from` is the block after it.
    A previous block that is not an integer, or not before this one, gives no window; a window above `max_blocks` is cut to its last blocks (cut: true)."""
    if not isinstance(prev_block_end, int) or isinstance(prev_block_end, bool):
        return {"reason": "no block read before this one on this chain: the first run has no window"}
    if not isinstance(block_end, int) or isinstance(block_end, bool):
        return {"reason": "the block of this record was not read"}
    if prev_block_end >= block_end:
        return {"reason": "the chain did not advance since the previous record"}
    lo = prev_block_end + 1
    cut = block_end - lo + 1 > max_blocks
    if cut:
        lo = block_end - max_blocks + 1
    return {"from": lo, "to": block_end, "cut": cut}


def scan_logs(getlogs, lo, hi, step=LOG_STEP_BLOCKS, max_calls=MAX_LOG_CALLS):
    """(logs, complete). `getlogs(a, b)` returns the list of logs for blocks a..b, or None when the node did not answer. A chunk that got no answer makes the
    scan incomplete (complete False); it is never read as 'no events'. Past `max_calls` the rest is not read and the scan is incomplete."""
    out, calls, a = [], 0, lo
    while a <= hi:
        b = min(hi, a + step - 1)
        if calls >= max_calls:
            return out, False
        calls += 1
        got = getlogs(a, b)
        if got is None:
            return out, False
        out.extend(got)
        a = b + 1
    return out, True


def _addr(topic):
    return ("0x" + str(topic)[-40:]).lower() if isinstance(topic, str) and len(topic) >= 42 else None


def _int(word):
    try:
        return int(word, 16)
    except (TypeError, ValueError):
        return None


def decode_event(log):
    """{event, address, block, tx, ...args} for a log of one of the events above, or None for any other. Unreadable numbers are None, never 0."""
    topics = log.get("topics") or []
    if not topics or topics[0] not in NAMES:
        return None
    t0, data = topics[0], str(log.get("data") or "0x")[2:]
    block = log.get("blockNumber")
    ev = {"event": NAMES[t0], "address": str(log.get("address") or "").lower(), "block": _int(block) if isinstance(block, str) else block, "tx": log.get("transactionHash")}
    if t0 in (OWNERSHIP_TRANSFER_STARTED, OWNERSHIP_TRANSFERRED) and len(topics) >= 3:
        ev["previous"], ev["new"] = _addr(topics[1]), _addr(topics[2])
    elif t0 == DEFAULT_ADMIN_TRANSFER_SCHEDULED and len(topics) >= 2:
        ev["new"] = _addr(topics[1]); ev["accept_schedule"] = _int(data[:64]) if len(data) >= 64 else None
    elif t0 == DEFAULT_ADMIN_DELAY_CHANGE_SCHEDULED:
        ev["new_delay"], ev["effect_schedule"] = (_int(data[:64]) if len(data) >= 128 else None), (_int(data[64:128]) if len(data) >= 128 else None)
    elif t0 == MIN_DELAY_CHANGE:
        ev["old"], ev["new"] = (_int(data[:64]) if len(data) >= 128 else None), (_int(data[64:128]) if len(data) >= 128 else None)
    elif t0 == NEW_DELAY and len(topics) >= 2:
        ev["old"], ev["new"] = None, _int(topics[1])
    return ev


def events_by_address(logs):
    """{address: [event, ...]} in block order, only for the logs that decode."""
    out = {}
    for lg in logs or []:
        ev = decode_event(lg)
        if ev:
            out.setdefault(ev["address"], []).append(ev)
    for evs in out.values():
        evs.sort(key=lambda e: (e["block"] if isinstance(e["block"], int) else 0))
    return out


def admin_events_of(events, limit=MAX_EVENTS_PER_RECORD):
    """(kept, total): the admin events of a target, oldest first, only the newest `limit` kept, and how many there were: the delay events of a timelock are not admin events."""
    keep = [e for e in events or [] if e["event"] in {NAMES[t] for t in ADMIN_TOPICS}]
    return keep[-limit:], len(keep)


def delay_change_of(events, current_delay=None, previous_delay=None):
    """The latest delay change among `events` of a timelock: {old, new, block, direction}. `direction` is 'shorter' or 'longer' (None when old or new is not known).
    A Compound NewDelay event carries only the new delay: `old` is then `previous_delay` (the delay the previous record read) when it is known. None when there is none."""
    last = None
    for e in events or []:
        if e["event"] in ("MinDelayChange", "NewDelay"):
            last = e
    if last is None:
        return None
    old = last.get("old") if last.get("old") is not None else previous_delay
    new = last.get("new")
    direction = None if (old is None or new is None or old == new) else ("shorter" if new < old else "longer")
    return {"old": old, "new": new, "block": last.get("block"), "direction": direction}


def default_admin_delay_of(word):
    """Seconds from a defaultAdminDelay() answer, or None (no such getter, or an answer that is not one word)."""
    if not isinstance(word, str) or len(word) != 66 or not word.startswith("0x"):
        return None
    n = _int(word)
    return n if n is not None and n < 10 * 366 * 86400 else None


def open_executor_call(timelock):
    """The eth_call asking whether address(0) holds EXECUTOR_ROLE on an OpenZeppelin TimelockController: anyone can then execute a ready operation."""
    return ("eth_call", [{"to": timelock, "data": HAS_ROLE_SEL + EXECUTOR_ROLE + ZERO_ADDRESS_WORD}, "latest"])


def open_executor_of(word):
    """True / False / None for the answer of `open_executor_call`: None when the contract has no such getter (a Compound timelock) or did not answer."""
    if not isinstance(word, str) or len(word) != 66 or not word.startswith("0x"):
        return None
    n = _int(word)
    return None if n is None else bool(n)


def admin_gap(holder, admin_members, member_kinds):
    """What the score does not weigh among the holders of DEFAULT_ADMIN_ROLE. The independent reader (like the admin analysis of the score) follows ONE holder,
    `holder`, the first member; every other member holds the same power and is in neither the kind nor the threshold that was read.
    `admin_members` is the record's {members, total, read, unread}; `member_kinds` maps a member address to 'eoa', 'contract' or None (not read).
    Returns {weighed_holder, total, read, not_weighed, not_weighed_plain_keys, not_weighed_contracts, not_weighed_unclassified, unread, text}, or None without members."""
    if not isinstance(admin_members, dict) or not isinstance(admin_members.get("members"), list):
        return None
    h = str(holder or "").lower()
    others = [m for m in admin_members["members"] if str(m).lower() != h]
    kinds = [member_kinds.get(str(m).lower()) for m in others]
    plain, contracts = kinds.count("eoa"), kinds.count("contract")
    unclassified = len(kinds) - plain - contracts
    unread = admin_members.get("unread")
    total = admin_members.get("total")
    parts = []
    if others:
        parts.append("%d other holder(s) of DEFAULT_ADMIN_ROLE read (%d plain key(s), %d contract(s)%s)" % (len(others), plain, contracts, ", %d not classified" % unclassified if unclassified else ""))
    if unread:
        parts.append("%d more not read" % unread)
    elif unread is None and total is None:
        parts.append("the number of holders was not read")
    text = "the score and this reading follow one holder; " + "; ".join(parts) if parts else None
    return {"weighed_holder": holder, "total": total, "read": admin_members.get("read"), "not_weighed": len(others), "not_weighed_plain_keys": plain, "not_weighed_contracts": contracts,
            "not_weighed_unclassified": unclassified, "unread": unread, "text": text}


def member_disagreement(admin_key_score, gap):
    """The sentence of a disagreement, or None: the score says admin power is not a bare key (>= 50) while another holder of the admin role IS a plain key that can
    act alone. Only what was read counts: a member that was not classified or not read makes no claim."""
    if not isinstance(gap, dict) or not isinstance(admin_key_score, int) or isinstance(admin_key_score, bool) or admin_key_score < 50:
        return None
    if gap.get("not_weighed_plain_keys", 0) > 0:
        return ("%d other holder(s) of DEFAULT_ADMIN_ROLE are plain keys and can act alone, whatever the score says (%d): the score follows one holder" % (gap["not_weighed_plain_keys"], admin_key_score))
    return None
