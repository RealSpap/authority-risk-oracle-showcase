"""Last slot of a cron expression, in UTC, with no dependency: the latest instant that is not after `now` and matches the cron.
Usage: python3 -I cron_slot.py "<cron, 5 fields>" <epoch seconds>   prints the epoch of the last slot (exit 0); exit 1 and a message on stderr when the cron cannot be read or has no slot in 400 days.
Fields: minute 0-59, hour 0-23, day of month 1-31, month 1-12, day of week 0-7 (0 and 7 are Sunday). Each field: `*`, a number, `a-b`, `*/n`, `a-b/n`, `a/n` (a up to the maximum), or a comma list of these.
Like cron, when the day of month AND the day of week are both restricted, a day that fits either one is a slot. No names (MON, JAN), no @hourly, no `?`, `L`, `#`.
Limit: it looks back at most 400 days (a yearly cron, or the 29th of February, may have no slot: an error, never an invented value)."""
import datetime as dt, sys

BOUNDS = [(0, 59), (0, 23), (1, 31), (1, 12), (0, 7)]
MAX_DAYS = 400


def field(text, lo, hi):
    """-> (set of values, wildcard). Raises ValueError when the field cannot be read or is out of bounds."""
    if not isinstance(text, str) or text == "": raise ValueError("empty field")
    out = set(); wild = text == "*"
    for part in text.split(","):
        if part == "": raise ValueError("empty element in a list")
        span, _, step = part.partition("/")
        if "/" in part and not step.isdigit(): raise ValueError("unreadable step: %r" % part)
        p = int(step) if "/" in part else 1
        if p < 1: raise ValueError("zero step: %r" % part)
        if span == "*": a, b = lo, hi
        elif "-" in span:
            x, _, y = span.partition("-")
            if not (x.isdigit() and y.isdigit()): raise ValueError("unreadable range: %r" % part)
            a, b = int(x), int(y)
        elif span.isdigit(): a = int(span); b = hi if "/" in part else a
        else: raise ValueError("unreadable element: %r" % part)
        if a < lo or b > hi or a > b: raise ValueError("out of bounds or reversed: %r (%d to %d allowed)" % (part, lo, hi))
        out.update(range(a, b + 1, p))
    return out, wild


def parse(cron):
    f = cron.split() if isinstance(cron, str) else []
    if len(f) != 5: raise ValueError("a cron with 5 fields is expected: %r" % (cron,))
    (M, _), (H, _), (DM, dm_wild), (MO, _), (DW, dw_wild) = (field(f[i], *BOUNDS[i]) for i in range(5))
    DW = {0 if d == 7 else d for d in DW}
    return M, H, DM, dm_wild, MO, DW, dw_wild


def day_fits(day, DM, dm_wild, MO, DW, dw_wild):
    if day.month not in MO: return False
    wd = (day.weekday() + 1) % 7           # Monday=1 ... Sunday=0
    if dm_wild and dw_wild: return True
    if not dm_wild and not dw_wild: return day.day in DM or wd in DW
    return (day.day in DM) if not dm_wild else (wd in DW)


def last_slot(cron, now):
    """Epoch (UTC) of the last slot not after `now` (epoch); ValueError when the cron cannot be read or has no slot in 400 days."""
    M, H, DM, dm_wild, MO, DW, dw_wild = parse(cron)
    t = dt.datetime.fromtimestamp(int(now), dt.timezone.utc).replace(second=0, microsecond=0)
    for k in range(MAX_DAYS + 1):
        day = (t - dt.timedelta(days=k)).replace(hour=0, minute=0)
        if not day_fits(day, DM, dm_wild, MO, DW, dw_wild): continue
        limit = (t.hour, t.minute) if k == 0 else (23, 59)
        for h in sorted(H, reverse=True):
            for m in sorted(M, reverse=True):
                if (h, m) <= limit: return int(day.replace(hour=h, minute=m).timestamp())
    raise ValueError("no slot in %d days for %r" % (MAX_DAYS, cron))


if __name__ == "__main__":
    if len(sys.argv) != 3: sys.exit('usage: cron_slot.py "<cron>" <epoch>')
    try: print(last_slot(sys.argv[1], sys.argv[2]))
    except (ValueError, OverflowError, OSError) as e: sys.stderr.write("cron unreadable: %s\n" % e); sys.exit(1)
