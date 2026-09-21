#!/usr/bin/env python3
"""Check ZIP 200's MUST: ACTIVATION_HEIGHT must be greater than the End-of-Service height
of the last node release that does not support the upgrade. Reads source files at release
tags from raw.githubusercontent.com (read-only). Post-Blossom spacing 75 s => 1152 blocks/day,
48 blocks/hour (as computed in zebrad end_of_support.rs and zcashd deprecation.h).
Usage: eos_vs_activation.py
"""
import re, subprocess

CASES = [  # (upgrade, activation height, repo, last tag WITHOUT Mainnet support)
    ("NU6.1", 3146400, "ZcashFoundation/zebra", "v2.5.0"),
    ("NU6.1", 3146400, "zcash/zcash", "v6.3.0"),
    ("NU6.2", 3364600, "ZcashFoundation/zebra", "v4.5.3"),
    ("NU6.2", 3364600, "zcash/zcash", "v6.12.5"),
    ("NU6.3", 3428143, "ZcashFoundation/zebra", "v5.2.0"),
    ("NU6.3", 3428143, "ZcashFoundation/zebra", "v6.0.0-rc.0"),
    ("NU6.3", 3428143, "zcash/zcash", "v6.20.0"),
]


def get(repo, tag, path):
    return subprocess.run(["curl", "-s", "-m", "30", f"https://raw.githubusercontent.com/{repo}/{tag}/{path}"],
                          capture_output=True, check=True, text=True).stdout


for up, act, repo, tag in CASES:
    if repo.endswith("zebra"):
        src = get(repo, tag, "zebrad/src/components/sync/end_of_support.rs")
        rel = int(re.search(r"ESTIMATED_RELEASE_HEIGHT: u32 = ([\d_]+);", src).group(1).replace("_", ""))
        days = int(re.search(r"EOS_PANIC_AFTER: u32 = (\d+);", src).group(1))
        eos, window = rel + days * 1152, f"{days}d"
    else:
        src = get(repo, tag, "src/deprecation.h")
        rel = int(re.search(r"APPROX_RELEASE_HEIGHT = (\d+);", src).group(1))
        weeks = int(re.search(r"RELEASE_TO_DEPRECATION_WEEKS = (\d+);", src).group(1))
        eos, window = rel + weeks * 7 * 24 * 48, f"{weeks}w"
    ok = "MUST_MET" if act > eos else "MUST_NOT_MET"
    print(f"{up} activation={act} {repo}@{tag} release_height={rel} eos_window={window} eos_height={eos} {ok}")
