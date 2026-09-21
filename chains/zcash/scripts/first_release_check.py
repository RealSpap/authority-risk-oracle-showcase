#!/usr/bin/env python3
"""Prove that each release cited in notice_period.py is the FIRST release setting the
Mainnet activation height: the height line is present in the node source at that tag and
absent at the immediately preceding release tag. Reads raw.githubusercontent.com (read-only).
Usage: first_release_check.py
"""
import re, subprocess

ZN = "zebra-chain/src/parameters/network_upgrade.rs"
ZC = "zebra-chain/src/parameters/constants.rs"
ZNET = "zebra-chain/src/parameters/network.rs"
CP = "src/chainparams.cpp"
# (upgrade, repo, cited tag, previous release tag, path, regex of the Mainnet height line)
CASES = [
    ("NU6", "zcash/zcash", "v6.0.0", "v6.0.0-rc1", CP, r"UPGRADE_NU6\]\.nActivationHeight = 2726400;"),
    ("NU6", "ZcashFoundation/zebra", "v2.0.0", "v2.0.0-rc.0", ZN, r"^\s*\(block::Height\(2_726_400\), Nu6\),"),
    ("NU6.1", "zcash/zcash", "v6.10.0", "v6.3.0", CP, r"UPGRADE_NU6_1\]\.nActivationHeight = 3146400;"),
    ("NU6.1", "ZcashFoundation/zebra", "v3.0.0-rc.0", "v2.5.0", ZC, r"pub const NU6_1: Height = Height\(3_146_400\);"),
    ("emergency-orchard-disable", "zcash/zcash", "v6.12.5", "v6.12.3", CP, r"nTemporaryOrchardDisablingSoftForkHeight = 3363426;"),
    ("emergency-orchard-disable", "ZcashFoundation/zebra", "v4.5.3", "v4.5.1", ZNET, r"MAINNET_TEMPORARY_ORCHARD_DISABLING_SOFT_FORK_HEIGHT: Height = Height\(3_363_426\);"),
    ("NU6.2", "zcash/zcash", "v6.20.0", "v6.12.5", CP, r"UPGRADE_NU6_2\]\.nActivationHeight = 3364600;"),
    ("NU6.2", "ZcashFoundation/zebra", "v5.0.0", "v4.5.3", ZC, r"pub const NU6_2: Height = Height\(3_364_600\);"),
    ("NU6.3", "ZcashFoundation/zebra", "v6.0.0", "v6.0.0-rc.0", ZC, r"pub const NU6_3: Height = Height\(3_428_143\);"),
]


def get(repo, tag, path):
    r = subprocess.run(["curl", "-s", "-f", "-m", "30", f"https://raw.githubusercontent.com/{repo}/{tag}/{path}"],
                       capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else None


for up, repo, tag, prev, path, rx in CASES:
    cur, old = get(repo, tag, path), get(repo, prev, path)
    has_cur = bool(cur and re.search(rx, cur, re.M))
    has_old = bool(old and re.search(rx, old, re.M))
    verdict = "FIRST_RELEASE_OK" if has_cur and not has_old and old is not None else "CHECK_FAILED"
    print(f"{up} {repo}@{tag} present={has_cur} prev={prev} prev_fetched={old is not None} prev_present={has_old} {verdict}")
