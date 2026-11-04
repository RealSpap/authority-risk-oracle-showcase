"""An offline delivery harness: evaluate_rules.main() on a fixture directory, with simulated receivers (a chat webhook and a signed webhook) that can be
down, or that store a message and lose their answer. Nothing leaves the process: the senders of evaluate_rules are replaced, the HMAC signature of the
webhook is still built by the real `signed_webhook` and checked by the receiver, so the signing path is exercised.

NOT exercised: the HTTP transport itself (post_json and post_signed are replaced, so timeouts, TLS, redirects and status codes are not run), and the Telegram channel
(alerts.send_telegram_alert is not replaced here; the channel is left unconfigured). What a lost answer does to the delivery state is exercised; what a real network does is not.

Used by scripts/adversarial/run.py (case 07) and by the tests (scripts/lib/tests/test_reader_audit.py, test_trust.py).
"""
import contextlib
import hashlib
import hmac
import io
import json
import os
import re
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.abspath(os.path.join(HERE, ".."))
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)
import evaluate_rules as ev  # noqa: E402

SECRET = "test-secret"


class Receiver:
    """A simulated receiver. `up` False: the request fails before the receiver sees it. `lose_ack`: the receiver stores the message and the answer is lost
    (the sender sees a failure), the case that makes a sender send twice."""

    def __init__(self, name):
        self.name, self.up, self.lose_ack = name, True, False
        self.received = []        # one item per message stored: the alert targets it carried

    def accept(self, targets):
        if not self.up:
            return False
        self.received.append(list(targets))
        return not self.lose_ack

    def counts(self):
        seen = {}
        for batch in self.received:
            for t in batch:
                seen[t] = seen.get(t, 0) + 1
        return seen

    def duplicates(self):
        return sum(n - 1 for n in self.counts().values() if n > 1)


class Delivery:
    """with Delivery(n_alerts, channels=("discord", "webhook")) as d: d.run(); d.discord.up = False ..."""

    def __init__(self, n_alerts, channels=("discord", "webhook")):
        self.n, self.channels = n_alerts, channels
        self.discord, self.webhook = Receiver("discord"), Receiver("webhook")

    def __enter__(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cwd = os.getcwd()
        os.chdir(self.tmp.name)
        os.makedirs("watch/scores")
        json.dump({"version": 1, "about": "x", "rules": [{"name": "low score", "when": "score < 50", "severity": "high"}], "notify": {"min_severity": "medium"}}, open("rules.json", "w"))
        json.dump({"run_utc": "2026-10-30T00:00:00Z"}, open("watch/latest.json", "w"))
        json.dump({"matched": {}}, open("watch/tvl.json", "w"))
        self.targets = ["0x" + "%040x" % i for i in range(1, self.n + 1)]
        json.dump({"kind": "evm", "name": "Robinhood", "oracle": "0x" + "ab" * 20, "rpc": "https://x", "block": 100, "readAt": 1790000000,
                   "targets": [{"target": t, "compositeScore": 10, "adminKeyScore": 10, "multisigScore": 10, "timelockScore": 10, "oracleAuthorityScore": 100,
                                "crossExposureScore": 100, "lastUpdated": 1789999000, "stale": False} for t in self.targets]}, open("watch/scores/robinhood-chain.json", "w"))
        self._orig = (ev.post_json, ev.post_signed)

        def fake_discord(url, payload):
            # a chat message carries lines, not addresses: the alerts it carries are read back from the shortened address of each line
            short = {self.short(a): a for a in self.targets}
            hits = [short[m.group(1)] for l in payload["content"].split("\n") for m in [re.search(r": (0x[0-9a-f]{4}…[0-9a-f]{4}) \(", l)] if m and m.group(1) in short]
            return self.discord.accept(hits)

        def fake_webhook(url, secret, payload):
            signed = ev.signed_webhook(url, secret, payload)          # the real signing code
            if signed is None:
                return False
            headers, body = signed
            ts, sig = headers["x-aro-timestamp"], headers["x-aro-signature"]
            good = "sha256=" + hmac.new(SECRET.encode(), ts.encode() + b"." + body, hashlib.sha256).hexdigest()
            if not hmac.compare_digest(sig, good):                  # a receiver that checks the signature
                return False
            return self.webhook.accept([a["target"] for a in json.loads(body)["alerts"]])

        ev.post_json, ev.post_signed = fake_discord, fake_webhook
        self._env = {k: os.environ.get(k) for k in ("DISCORD_WEBHOOK_URL", "ALERT_WEBHOOK_URL", "ALERT_WEBHOOK_SECRET", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "TELEGRAM_MODE")}
        for k in self._env:
            os.environ.pop(k, None)
        if "discord" in self.channels:
            os.environ["DISCORD_WEBHOOK_URL"] = "http://discord.local/x"
        if "webhook" in self.channels:
            os.environ["ALERT_WEBHOOK_URL"] = "https://hook.local/x"
            os.environ["ALERT_WEBHOOK_SECRET"] = SECRET
        return self

    @staticmethod
    def short(addr):
        return addr[:6] + "…" + addr[-4:]

    def __exit__(self, *exc):
        ev.post_json, ev.post_signed = self._orig
        for k, v in self._env.items():
            os.environ.pop(k, None)
            if v is not None:
                os.environ[k] = v
        os.chdir(self.cwd)
        self.tmp.cleanup()

    def run(self):
        sys.argv = ["evaluate_rules.py", "--rules", "rules.json", "--scores", "watch/scores", "--latest", "watch/latest.json", "--out", "watch/alerts.json"]
        with contextlib.redirect_stdout(io.StringIO()):
            try:
                ev.main()
            except SystemExit:
                pass
        return json.load(open("watch/alerts.json"))

    def delivered_everywhere(self, out):
        return all(x.get("notified") for x in out["active"])

    def run_until_delivered(self, limit=10):
        out, runs = None, 0
        while runs < limit:
            out = self.run()
            runs += 1
            if self.delivered_everywhere(out):
                break
        return runs, out
