"""Support for the tests of the trust status (S15) and for the adversarial kit (S16): the base fixture of a Watch run, a temporary copy a test can alter, and the trust document built from it.

The fixture is `scripts/lib/tests/fixtures/trust-base-watch/` (a compact copy of the shapes of a real run)."""
import calendar
import json
import os
import shutil
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.abspath(os.path.join(HERE, "..", ".."))
ROOT = os.path.abspath(os.path.join(SCRIPTS, ".."))
for _p in (SCRIPTS, os.path.join(SCRIPTS, "lib")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import trust  # noqa: E402

BASE = os.path.join(HERE, "fixtures", "trust-base-watch")
NOW = calendar.timegm(time.strptime("2026-10-30T07:20:00Z", "%Y-%m-%dT%H:%M:%SZ"))
A, B, C = "0x" + "a1" * 20, "0x" + "b2" * 20, "0x" + "c3" * 20
KEY = {A: "robinhood:" + A, B: "robinhood:" + B, C: "robinhood:" + C}



def jload(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def jdump(obj, p):
    with open(p, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=1)


class Watch:
    """A temporary copy of the base fixture the case can alter, and the trust document built from it."""

    def __init__(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = os.path.join(self.tmp.name, "watch")
        shutil.copytree(BASE, self.dir)
        self.data = os.path.join(self.tmp.name, "data")
        os.makedirs(self.data)

    def edit(self, name, fn):
        p = os.path.join(self.dir, name)
        d = jload(p)
        out = fn(d)
        jdump(d if out is None else out, p)

    def rm(self, name):
        os.remove(os.path.join(self.dir, name))

    def trust(self, now=NOW, key_present=True):
        return trust.build(self.dir, self.data, now=now, key_present=key_present)

    def close(self):
        self.tmp.cleanup()


def status(doc, addr):
    return doc["by_target"][KEY[addr]]["status"]


def codes(doc, addr):
    return [r["code"] for r in doc["by_target"][KEY[addr]]["reasons"]]


def so_edit(addr, **fields):
    def f(d):
        for r in d["results"]:
            if r["target"] == addr:
                r.update(fields)
    return f
