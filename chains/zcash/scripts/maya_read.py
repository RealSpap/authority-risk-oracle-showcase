#!/usr/bin/env python3
"""Read-only Maya Protocol (Mayanode) REST helper, same style as
near_read.py/zcash_read.py (no deps, uses curl, no keys, no signing).

Added 2026-09-18 to score the Asgard TSS vaults that hold native ZEC on
Zcash Mainnet under Maya Protocol's own external authority -- the target
identified but not yet scored by `data/scouting_candidates_2026-09-18.md`
(structurally the mirror image of `zec.omft.near`: that target is ZEC
*represented on* another chain via a NEAR authority; this one is real
transparent ZEC, sitting on Zcash itself, controlled by an external
network's own TSS validator set).

Only ONE public Mayachain full-node REST API was found and could be
verified reachable this pass (`mayanode.mayachain.info`). Unlike every
NEAR read in `near_read.py` (cross-checked on two independent RPCs) or
every Zcash read in this project (cross-checked on two independent
lightwalletd operators), Mayachain-side reads here (vault membership,
halted status, outbound queue) rely on this single source -- disclosed,
not hidden. Several plausible second-provider hostnames were probed live
and none resolved (DNS failure, not a reachability/timeout issue):
mayanode.mayachain.dev, mayanode.thorswap.net, api.mayascan.org,
mayanode.ninerealms.com (this last one is quoted in this project's OWN
`test/regression/README.md`, apparently copy-pasted unchanged from the
upstream THORChain fork's docs -- it does not resolve for Mayachain).
This is Mayachain's own replicated consensus state (every synced full
node must agree byte-for-byte, unlike a centralized price feed), which is
a real but weaker guarantee than an independent second read -- the
distinction is disclosed in the scorer's notes, not glossed over.

Usage:
  maya_read.py inbound_addresses            -> /mayachain/inbound_addresses
  maya_read.py vaults_asgard                -> /mayachain/vaults/asgard
  maya_read.py nodes                        -> /mayachain/nodes
  maya_read.py queue_outbound               -> /mayachain/queue/outbound
"""
import json
import subprocess
import sys
import time

MAYANODE_HOST = "https://mayanode.mayachain.info"


def get(path, tries=4, timeout=20):
    url = f"{MAYANODE_HOST}{path}"
    last = None
    for i in range(tries):
        out = subprocess.run(
            ["curl", "-s", "-m", str(timeout), url], capture_output=True, text=True,
        ).stdout
        try:
            return json.loads(out)
        except json.JSONDecodeError:
            last = out[:200]
            time.sleep(2 * (i + 1))
    # FIXED 2026-09-19: this used to raise SystemExit -- a BaseException
    # subclass that escapes a plain `except Exception`, the same real bug
    # found and fixed the same day in the sibling near_read.py::rpc()
    # (found there first while auditing test coverage; found here via a
    # deliberate follow-up grep for the same pattern across the repo, not
    # by accident). chains/zcash/scorers.py::score_all() wraps
    # active_zec_vaults() (which calls vaults_asgard(), which calls this
    # function) in exactly that kind of `except Exception as e:` handler --
    # a single bad/slow Mayanode REST call would have crashed the entire
    # Zcash score_all() run instead of gracefully skipping just the Maya
    # Asgard vault section, the same "SKIPPED <target> -- RuntimeError:
    # ..." degradation every other target in this project gets.
    raise RuntimeError(f"Mayanode REST call failed after retries: {path} -- {last}")


def inbound_addresses():
    return get("/mayachain/inbound_addresses")


def vaults_asgard():
    return get("/mayachain/vaults/asgard")


def nodes():
    return get("/mayachain/nodes")


def queue_outbound():
    return get("/mayachain/queue/outbound")


def active_zec_vaults():
    """Every ActiveVault currently holding ZEC.ZEC > 0, with its ZEC
    address, ledger amount (zatoshi) and full TSS `membership` pubkey
    list (the literal `localStateItem.ParticipantKeys` set a keysign for
    this vault would use -- see scorers.py's tss_required_signers())."""
    out = []
    for v in vaults_asgard():
        if v.get("status") != "ActiveVault":
            continue
        coin = next((c for c in v.get("coins", []) if c.get("asset") == "ZEC.ZEC"), None)
        if not coin or int(coin.get("amount", "0")) <= 0:
            continue
        addr = next((a["address"] for a in v.get("addresses", []) if a.get("chain") == "ZEC"), None)
        out.append({
            "pub_key": v["pub_key"],
            "ledger_amount_zat": int(coin["amount"]),
            "zec_address": addr,
            "membership": v.get("membership") or [],
        })
    return out


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    fn = {"inbound_addresses": inbound_addresses, "vaults_asgard": vaults_asgard,
          "nodes": nodes, "queue_outbound": queue_outbound}.get(cmd)
    if not fn:
        raise SystemExit(__doc__)
    print(json.dumps(fn(), indent=2))
