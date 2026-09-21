#!/usr/bin/env python3
"""
Read-only check of the Fluid Liquidity (Plasma) signer sets and immediate paths, 2026-09-20.
No key, no signature, no transaction. Companion of data/fluid_liquidity_plasma_2026-09-20_signers.md.

    python3 chains/plasma-ecosystem/scripts/fluid_signers_check.py [--full-scan]

What it checks (exit 0 only if every line is OK):
  1. Plasma (9745) and Arbitrum One (42161) answer, and the Fluid team Avocado multisig 0x4F6F977a... returns the SAME
     requiredSigners() (6) and signers() (12) on both, equal to the snapshot the Plasma scorer compares against.
  2. The executor Safe 0x196Ed45e... returns the same owners and threshold (3) on both chains.
  3. Liquidity's LogUpdateAuths / LogUpdateGuardians events on Plasma (fetched from the Routescan explorer API, every event
     then re-fetched from the Plasma node itself by block and matched on transaction hash and data): four active auths, one
     guardian. With --full-scan the node alone is scanned over the whole chain in 6,250-block windows (about 15 minutes) and
     must find exactly the same events, which removes the dependence on the explorer for completeness.
  4. Each active auth is a contract whose TEAM_MULTISIG() is the same Avocado multisig, and the only guardian is that
     multisig.
  5. score_fluid_liquidity_plasma() run live returns 65 / 55 / 55 / oracle 100 / cross 80 / composite 59, and equals the
     Arbitrum Fluid scorer run live on the same structure (admin, multisig, timelock, cross, composite).
"""
import json
import os
import sys
import urllib.request

from eth_abi import decode
from web3 import Web3

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts", "lib"))
sys.path.insert(0, os.path.join(REPO_ROOT, "chains", "plasma-ecosystem"))
import scorers  # noqa: E402

PLASMA_RPC, ARB_RPC = "https://rpc.plasma.to", "https://arb1.arbitrum.io/rpc"
LIQ = Web3.to_checksum_address("0x52Aa899454998Be5b000Ad077a46Bbe360F4e497")
AVO = Web3.to_checksum_address("0x4F6F977aCDD1177DCD81aB83074855EcB9C2D49e")
SAFE = Web3.to_checksum_address("0x196Ed45eC4ACA949E7AA921ceC81e219e682775e")
ROUTESCAN = "https://api.routescan.io/v2/network/mainnet/evm/9745/etherscan/api"
ABI = [
    {"name": "signers", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "address[]"}]},
    {"name": "requiredSigners", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "uint8"}]},
    {"name": "getOwners", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "address[]"}]},
    {"name": "getThreshold", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "uint256"}]},
]
failures = []


def check(ok, msg):
    print(("OK   " if ok else "FAIL ") + msg)
    if not ok:
        failures.append(msg)


def topic(sig):
    return "0x" + Web3.keccak(text=sig).hex().removeprefix("0x")


T_AUTHS, T_GUARDIANS = topic("LogUpdateAuths((address,bool)[])"), topic("LogUpdateGuardians((address,bool)[])")


def fold(events):
    state = {}
    for lg in events:
        (arr,) = decode(["(address,bool)[]"], bytes(lg["data"]))
        for addr, val in arr:
            state[addr.lower()] = val
    return state


plasma = Web3(Web3.HTTPProvider(PLASMA_RPC, request_kwargs={"timeout": 60}))
arb = Web3(Web3.HTTPProvider(ARB_RPC, request_kwargs={"timeout": 60}))
check((plasma.eth.chain_id, arb.eth.chain_id) == (9745, 42161), f"chain ids {plasma.eth.chain_id} / {arb.eth.chain_id} (expected 9745 / 42161)")

reads = {}
for name, w in (("plasma", plasma), ("arbitrum", arb)):
    a, s = w.eth.contract(address=AVO, abi=ABI), w.eth.contract(address=SAFE, abi=ABI)
    reads[name] = dict(req=a.functions.requiredSigners().call(), signers=sorted(x.lower() for x in a.functions.signers().call()),
                       owners=sorted(x.lower() for x in s.functions.getOwners().call()), thr=s.functions.getThreshold().call())
p, a = reads["plasma"], reads["arbitrum"]
check(p["req"] == a["req"] == 6 and len(p["signers"]) == len(a["signers"]) == 12 and p["signers"] == a["signers"],
      f"Avocado multisig {AVO}: requiredSigners {p['req']} / {a['req']}, signers {len(p['signers'])} / {len(a['signers'])}, identical sets on both chains")
check(set(a["signers"]) == set(scorers._FLUID_TEAM_SIGNERS_ARBITRUM_2026_09_20), "the Arbitrum read equals the snapshot in the Plasma scorer")
check(p["thr"] == a["thr"] == 3 and p["owners"] == a["owners"] and len(p["owners"]) == 5,
      f"executor Safe {SAFE}: threshold {p['thr']} / {a['thr']}, {len(p['owners'])} owners, identical on both chains")
overlap = sorted(set(p["owners"]) & set(p["signers"]))
print(f"NOTE {len(overlap)} of the {len(p['owners'])} executor Safe owners are also among the {len(p['signers'])} Avocado signers (disclosed, not scored)")

# ---- events
node_events = {}
if "--full-scan" in sys.argv:
    tip, step, cur, found = plasma.eth.block_number, 6250, 0, []
    while cur <= tip:
        end = min(cur + step - 1, tip)
        found += plasma.eth.get_logs({"address": LIQ, "topics": [[T_AUTHS, T_GUARDIANS]], "fromBlock": cur, "toBlock": end})
        cur = end + 1
    node_events = {"auths": [l for l in found if l["topics"][0].hex().removeprefix("0x") == T_AUTHS.removeprefix("0x")],
                   "guardians": [l for l in found if l["topics"][0].hex().removeprefix("0x") == T_GUARDIANS.removeprefix("0x")]}
    print(f"NOTE full node scan to block {tip}: {len(node_events['auths'])} auth events, {len(node_events['guardians'])} guardian events")
explorer = {}
for name, t in (("auths", T_AUTHS), ("guardians", T_GUARDIANS)):
    r = json.load(urllib.request.urlopen(f"{ROUTESCAN}?module=logs&action=getLogs&address={LIQ}&topic0={t}&fromBlock=0&toBlock=latest", timeout=60))
    logs = r["result"] if r.get("status") == "1" else []
    confirmed = 0
    for lg in logs:
        blk = int(lg["blockNumber"], 16)
        node = plasma.eth.get_logs({"address": LIQ, "topics": [t], "fromBlock": blk, "toBlock": blk})
        confirmed += any(n["transactionHash"].hex().removeprefix("0x") == lg["transactionHash"].removeprefix("0x") and bytes(n["data"]).hex() == lg["data"][2:] for n in node)
    check(len(logs) > 0 and confirmed == len(logs), f"{name}: {len(logs)} events from the explorer, {confirmed} re-fetched and matched on the Plasma node")
    explorer[name] = [{"data": bytes.fromhex(lg["data"][2:]), "blockNumber": int(lg["blockNumber"], 16)} for lg in sorted(logs, key=lambda l: (int(l["blockNumber"], 16), int(l["logIndex"], 16)))]
    if node_events:
        nodes = sorted(node_events[name], key=lambda l: (l["blockNumber"], l["logIndex"]))
        check(len(nodes) == len(logs) and [bytes(n["data"]) for n in nodes] == [e["data"] for e in explorer[name]],
              f"{name}: the full node scan finds exactly the {len(logs)} explorer events")
auths, guardians = fold(explorer["auths"]), fold(explorer["guardians"])
active_auths = sorted(x for x, v in auths.items() if v)
active_guardians = sorted(x for x, v in guardians.items() if v)
check(len(active_auths) == 4, f"{len(active_auths)} active auths (of {len(auths)} ever listed)")
check(active_guardians == [AVO.lower()], f"active guardians: {active_guardians}")
sel = Web3.keccak(text="TEAM_MULTISIG()")[:4]
for x in active_auths:
    addr = Web3.to_checksum_address(x)
    code = len(plasma.eth.get_code(addr))
    try:
        tm = Web3.to_checksum_address(plasma.eth.call({"to": addr, "data": sel})[-20:])
    except Exception:
        tm = None
    check(code > 0 and tm == AVO, f"active auth {x}: {code} bytes of code, TEAM_MULTISIG() = {tm and tm.lower()}")
for x in sorted(set(auths) - set(active_auths)):
    print(f"NOTE revoked auth {x} has {len(plasma.eth.get_code(Web3.to_checksum_address(x)))} bytes of code")

# ---- the scorer, live
r = scorers.score_fluid_liquidity_plasma(plasma)
got = (r["adminKeyScore"], r["multisigScore"], r["timelockScore"], r["oracleAuthorityScore"], r["crossExposureScore"], r["compositeScore"])
check(got == (65, 55, 55, 100, 80, 59), f"score_fluid_liquidity_plasma() live = {got} (expected 65, 55, 55, 100, 80, 59)")

# ---- the sibling scorer: the same structure must score the same on both chains
import importlib.util  # noqa: E402


def _load(name, rel):
    path = os.path.join(REPO_ROOT, rel)
    sys.path.insert(0, os.path.dirname(path))
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


arb_scorers = _load("aro_arbitrum_scorers_for_fluid_check", "chains/arbitrum-ecosystem/scorers.py")
ra = arb_scorers.score_fluid_liquidity_arbitrum(arb)
fields = ("adminKeyScore", "multisigScore", "timelockScore", "crossExposureScore", "compositeScore")
check([r[f] for f in fields] == [ra[f] for f in fields],
      f"the Plasma scorer {[r[f] for f in fields]} equals the Arbitrum scorer {[ra[f] for f in fields]} on the same structure "
      f"({', '.join(fields)})")

print()
print("RESULT:", "ALL CHECKS PASS" if not failures else f"{len(failures)} FAILURE(S)")
sys.exit(1 if failures else 0)
