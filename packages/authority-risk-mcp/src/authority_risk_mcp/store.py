"""Where the files come from, and the proof that they are the ones the Watch signed.

The Watch publishes its files on the `watch-data` branch of the public repository together with `signature.json`: the sha256 of every published file, the head of the hash-chained event log, and an
Ed25519 signature over the canonical JSON of that manifest. This module reads a file only if (1) the manifest carries a valid signature by a key this package trusts, (2) the file's sha256 is the one in the manifest.
Anything else is an error that the tools turn into `not_read` / `integrity_failed`: a file that does not match is never a value.

Two sources: HTTPS (raw.githubusercontent.com first, jsDelivr as the fall-back; a source whose copy does not match the manifest is skipped and the next one is tried) or a local folder (`--data-dir`, a clone of the
branch, offline). The folder is checked against its own `signature.json` when it has one.
"""
import calendar
import hashlib
import json
import os
import shutil
import tempfile
import time
import urllib.parse
import urllib.request

from . import ed25519

REPO = "RealSpap/authority-risk-oracle-showcase"
DEFAULT_BASES = ("https://raw.githubusercontent.com/%s/watch-data/" % REPO, "https://cdn.jsdelivr.net/gh/%s@watch-data/" % REPO)
ALLOWED_HOSTS = ("raw.githubusercontent.com", "cdn.jsdelivr.net")
# The public key of the Watch's manifest signature, as published in watch-data/signature.json on 2026-10-14. A rotation is announced in the repository; until a release carries the new key, pass it with --trust-key.
PINNED_KEYS = ("11baca3ef6a69de4901c185f6cbbd3f93318fbb74f9961a8d39aead841adf409",)
MAX_FILE_BYTES = 20 * 1024 * 1024
# What the tools read, when the manifest lists it (a file the manifest does not list is not fetched: its value is "not read").
NEEDED = ("second_opinion.json", "tvl.json", "tvl_scope.json", "held_assets.json", "pause_state.json", "safe_activity.json", "side_roles.json", "alerts.json", "latest.json", "admin_probe.json")
NEEDED_PREFIX = ("scores/",)


class IntegrityFailed(Exception):
    """The files cannot be trusted: bad or missing signature, an unpinned key, a hash that does not match."""


class NotRead(Exception):
    """The files could not be fetched (no network, a 404, a timeout): unknown, not tampered."""


def _loopback(host):
    return host in ("127.0.0.1", "localhost", "[::1]", "::1")


def _check_base(url):
    u = urllib.parse.urlparse(url)
    if u.scheme == "https": return url if url.endswith("/") else url + "/"
    if u.scheme == "http" and _loopback(u.hostname or ""): return url if url.endswith("/") else url + "/"
    raise ValueError("a base URL must be https (http is accepted for the loopback address only): %r" % url)


class _SameHostRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        host = urllib.parse.urlparse(newurl).hostname or ""
        if host not in ALLOWED_HOSTS and not _loopback(host) and host != (urllib.parse.urlparse(req.full_url).hostname or ""):
            raise NotRead("redirect to a host that is not allowed: %s" % host)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class Store:
    def __init__(self, data_dir=None, bases=None, trusted_keys=(), allow_unsigned=False, allow_unpinned=False, max_age_hours=72, ttl_seconds=900, timeout=20, now=time.time, retry_wait=3):
        self.data_dir = data_dir
        self.bases = tuple(_check_base(b) for b in (bases or DEFAULT_BASES))
        self.keys = tuple(PINNED_KEYS) + tuple(k.lower() for k in trusted_keys)
        self.allow_unsigned = allow_unsigned; self.allow_unpinned = allow_unpinned
        self.max_age_hours = max_age_hours; self.ttl = ttl_seconds; self.timeout = timeout; self.now = now; self.retry_wait = retry_wait
        self._tmp = None; self._dir = None; self._stamp = 0.0; self._integrity = None
        self._opener = urllib.request.build_opener(_SameHostRedirect)

    # ------------------------------------------------------------------ fetching
    def _fetch(self, base, rel, tail=None):
        url = base + urllib.parse.quote(rel)
        req = urllib.request.Request(url, headers={"User-Agent": "authority-risk-mcp/0.1", "Accept": "*/*"})
        if tail: req.add_header("Range", "bytes=-%d" % tail)
        try:
            with self._opener.open(req, timeout=self.timeout) as r:
                data = r.read(MAX_FILE_BYTES + 1)
        except NotRead: raise
        except Exception as e:  # noqa: BLE001 -- any network failure is "could not read", never a value
            raise NotRead("%s: %s" % (url, str(e)[:100]))
        if len(data) > MAX_FILE_BYTES: raise NotRead("%s: larger than %d bytes" % (url, MAX_FILE_BYTES))
        return data

    def _fetch_any(self, rel, expect_sha=None):
        """The bytes of `rel` from the first source whose copy matches `expect_sha` (when given). A mismatch on every source that answered is an integrity failure, not a missing file."""
        errors, mismatched = [], []
        for base in self.bases:
            try: data = self._fetch(base, rel)
            except NotRead as e: errors.append(str(e)); continue
            if expect_sha is None or hashlib.sha256(data).hexdigest() == expect_sha: return data
            mismatched.append(base)
        if mismatched: raise IntegrityFailed("%s does not match the signed manifest on %s" % (rel, ", ".join(urllib.parse.urlparse(m).hostname or m for m in mismatched)))
        raise NotRead("; ".join(errors) or "no source configured")

    def _last_event_line(self):
        """The last line of events.jsonl. A tail is asked for first; when the server refuses a range (raw.githubusercontent.com answers 416 for a file shorter than the tail) or the tail holds no complete
        earlier line, the whole file is read, up to 4 MB (a longer log is "not checked", never guessed)."""
        for tail in (8192, None):
            try:
                raw = self._fetch(self.bases[0], "events.jsonl", tail=tail)
            except NotRead:
                if tail is None: raise
                continue
            if tail is None and len(raw) >= 4 * 1024 * 1024: raise NotRead("events.jsonl is longer than 4 MB")
            text = raw.decode("utf-8", "replace").rstrip("\n"); ls = text.split("\n")
            if tail is not None and len(ls) < 2: continue   # the tail may begin in the middle of the one line it holds
            return ls[-1] if ls and ls[-1].strip() else None
        return None

    # ------------------------------------------------------------------ the manifest
    def _read_signature(self):
        if self.data_dir:
            p = os.path.join(self.data_dir, "signature.json")
            if not os.path.isfile(p): return None
            try: return json.load(open(p, encoding="utf-8"))
            except Exception as e: raise IntegrityFailed("signature.json in the folder is not readable: %s" % str(e)[:80])  # noqa: BLE001
        data = self._fetch_any("signature.json")
        try: return json.loads(data.decode("utf-8"))
        except Exception: raise IntegrityFailed("signature.json is not JSON")  # noqa: BLE001

    def _verify_manifest(self, sig):
        """(integrity record, manifest). Raises IntegrityFailed when the signature does not hold."""
        if sig is None:
            if self.data_dir: return {"verified": False, "signature": "none", "note": "the folder has no signature.json: its files are NOT checked"}, None
            raise IntegrityFailed("no signature.json")
        m = sig.get("manifest")
        if not isinstance(m, dict) or not isinstance(m.get("files"), dict): raise IntegrityFailed("signature.json has no manifest")
        if not sig.get("signed"):
            if not self.allow_unsigned: raise IntegrityFailed("the manifest is unsigned (the Watch ran without its signing key); pass --allow-unsigned to read it anyway, as unverified")
            return {"verified": False, "signature": "unsigned", "note": "the manifest is unsigned: the files are consistent with it but nobody vouches for it"}, m
        pk = str(sig.get("public_key", "")).lower()
        try: ok = ed25519.verify(bytes.fromhex(pk), json.dumps(m, sort_keys=True, separators=(",", ":")).encode(), bytes.fromhex(str(sig.get("signature", ""))))
        except ValueError: ok = False
        if not ok: raise IntegrityFailed("the signature of the manifest is not valid")
        pinned = pk in self.keys
        if not pinned and not self.allow_unpinned: raise IntegrityFailed("the manifest is signed by a key this package does not trust (%s...); pass --trust-key to trust it" % pk[:12])
        return {"verified": True, "signature": "valid", "signed_by": pk, "pinned": pinned}, m

    def _chain_head(self, m):
        head = m.get("events_chain_head")
        if not head: return "no event log in the manifest"
        try:
            if self.data_dir:
                lines = [l.rstrip("\n") for l in open(os.path.join(self.data_dir, "events.jsonl"), encoding="utf-8") if l.strip()]
                last = lines[-1] if lines else None
            else:
                last = self._last_event_line()
        except (NotRead, OSError, IndexError) as e:
            return "not checked (%s)" % str(e)[:160]
        if last is None: return "not checked (empty log)"
        if hashlib.sha256(last.encode()).hexdigest() != head: raise IntegrityFailed("the head of the event log does not match the signed manifest")
        return "verified"

    # ------------------------------------------------------------------ the verified folder the tools read
    def sync(self):
        """(path of a folder holding verified files, integrity record). Re-reads the manifest when the earlier one is older than the time to live. The Watch commits every six hours: a mismatch that
        appears while a new run lands between two reads is given one more try with a fresh manifest, and only a second mismatch is an integrity failure."""
        if self._dir and self.now() - self._stamp < self.ttl: return self._dir, self._integrity
        try: return self._sync_once()
        except IntegrityFailed:
            time.sleep(self.retry_wait)
            return self._sync_once()

    def _sync_once(self):
        sig = self._read_signature(); integ, m = self._verify_manifest(sig)
        if m is not None: integ["chain_head"] = self._chain_head(m)
        run = (sig or {}).get("run_utc"); integ["manifest_run_utc"] = run
        try:
            age = (self.now() - calendar.timegm(time.strptime(run, "%Y-%m-%dT%H:%M:%SZ"))) / 3600 if run else None
        except (TypeError, ValueError): age = None
        integ["snapshot_age_hours"] = None if age is None else round(age, 1)
        integ["snapshot_stale"] = None if age is None else age > self.max_age_hours
        if self.data_dir:
            self._dir = self.data_dir
            if m is not None: self._check_local(m)
        else:
            self._materialize(m)
        self._stamp = self.now(); self._integrity = integ
        return self._dir, integ

    def _wanted(self, m):
        return sorted(r for r in m["files"] if r in NEEDED or any(r.startswith(p) for p in NEEDED_PREFIX) and r.endswith(".json"))

    def _check_local(self, m):
        for rel in self._wanted(m):
            p = os.path.join(self.data_dir, rel)
            if not os.path.isfile(p): continue   # a file the folder does not have is a file not read, which the tools say
            if hashlib.sha256(open(p, "rb").read()).hexdigest() != m["files"][rel]: raise IntegrityFailed("%s in the folder does not match its signature.json" % rel)

    def _materialize(self, m):
        new = tempfile.mkdtemp(prefix="authority-risk-mcp-"); os.chmod(new, 0o700)
        try:
            for rel in self._wanted(m):
                data = self._fetch_any(rel, expect_sha=m["files"][rel])
                dest = os.path.join(new, rel); os.makedirs(os.path.dirname(dest), exist_ok=True); open(dest, "wb").write(data)
        except BaseException:
            shutil.rmtree(new, ignore_errors=True); raise
        old = self._tmp; self._tmp = new; self._dir = new
        if old: shutil.rmtree(old, ignore_errors=True)

    def close(self):
        if self._tmp: shutil.rmtree(self._tmp, ignore_errors=True); self._tmp = None
