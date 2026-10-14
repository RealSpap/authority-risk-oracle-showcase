import argparse
import os
import sys

from . import __version__
from .store import Store


def main(argv=None):
    ap = argparse.ArgumentParser(prog="authority-risk-mcp", description="Read-only MCP server: who can change a smart contract, how fast, and how strong the setup is, from the files of the Authority Risk Oracle Watch, checked against its signed manifest.")
    ap.add_argument("--data-dir", help="read a local clone of the watch-data branch instead of the network (offline); checked against its signature.json when it has one")
    ap.add_argument("--base-url", action="append", help="where the branch files are served (https, repeatable, tried in order); default: raw.githubusercontent.com then jsDelivr")
    ap.add_argument("--trust-key", action="append", default=[], help="an extra Ed25519 public key (64 hex characters) whose manifest signature is accepted, for a key rotation")
    ap.add_argument("--allow-unsigned", action="store_true", help="read a manifest that carries no signature, reported as unverified")
    ap.add_argument("--allow-unpinned", action="store_true", help="accept a valid signature by a key that is not pinned, reported as not pinned")
    ap.add_argument("--max-age-hours", type=float, default=72, help="a snapshot older than this is flagged snapshot_stale (default 72)")
    ap.add_argument("--version", action="version", version="authority-risk-mcp " + __version__)
    a = ap.parse_args(argv)
    from .server import serve
    keys = list(a.trust_key) + [k for k in os.environ.get("AUTHORITY_RISK_TRUSTED_KEYS", "").split(",") if k.strip()]
    store = Store(data_dir=a.data_dir, bases=a.base_url, trusted_keys=[k.strip() for k in keys], allow_unsigned=a.allow_unsigned, allow_unpinned=a.allow_unpinned, max_age_hours=a.max_age_hours)
    serve(store)
    return 0


if __name__ == "__main__":
    sys.exit(main())
