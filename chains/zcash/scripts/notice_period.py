#!/usr/bin/env python3
"""Measure real notice periods of Zcash Mainnet network upgrades (read-only).

For each upgrade: first node release that set the Mainnet activation height
(publication time shown on the GitHub release page) vs the timestamp of the activation
block (lightwalletd GetBlock, CompactBlock.time). Prints days of notice.
Usage: notice_period.py <lightwalletd host:port>
"""
import sys, os, re, subprocess, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from zcash_read import grpc, decode, field_varint

# (upgrade, mainnet activation height, [(repo, tag) of first release setting that Mainnet height])
# Each tag is proven to be the first release carrying the Mainnet height by first_release_check.py.
UPGRADES = [
    ("NU6", 2726400, [("zcash/zcash", "v6.0.0"), ("ZcashFoundation/zebra", "v2.0.0"),
             ("ZcashFoundation/zebra", "v2.0.1")]),  # v2.0.0 is a bare tag; v2.0.1 is the first published Release
    ("NU6.1", 3146400, [("zcash/zcash", "v6.10.0"), ("ZcashFoundation/zebra", "v3.0.0-rc.0")]),
    ("emergency-orchard-disable", 3363426, [("zcash/zcash", "v6.12.5"), ("ZcashFoundation/zebra", "v4.5.3")]),
    ("NU6.2", 3364600, [("zcash/zcash", "v6.20.0"), ("ZcashFoundation/zebra", "v5.0.0")]),
    ("NU6.3", 3428143, [("ZcashFoundation/zebra", "v6.0.0")]),
]


def published(repo, tag):
    # Release page HTML (no API rate limit). If a GitHub Release exists the page says
    # "released this" and the first ISO datetime is its publication time. If only a git tag
    # exists the page says "tagged this" and the first ISO datetime is the tag time.
    # (Space-separated datetimes on the page belong to GPG signature popovers and are ignored.)
    out = subprocess.run(["curl", "-s", "-m", "30", f"https://github.com/{repo}/releases/tag/{tag}"],
                         capture_output=True, check=True, text=True).stdout
    iso = re.search(r'datetime="(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ)"', out).group(1)
    kind = "release" if "released this" in out else ("tag_only" if "tagged this" in out else "unknown")
    return datetime.datetime.fromisoformat(iso.replace("Z", "+00:00")), kind


def block_time(host, h):
    blk = dict(decode(grpc(host, "GetBlock", field_varint(1, h))[0]))
    return datetime.datetime.fromtimestamp(blk[5], datetime.timezone.utc)


host = sys.argv[1]
for name, h, rels in UPGRADES:
    bt = block_time(host, h)
    for repo, tag in rels:
        pt, kind = published(repo, tag)
        days = (bt - pt).total_seconds() / 86400
        print(f"{name} height={h} block_time={bt:%Y-%m-%dT%H:%MZ} {repo}@{tag} kind={kind} published={pt:%Y-%m-%dT%H:%MZ} notice_days={days:.1f} notice_hours={days*24:.1f}")
