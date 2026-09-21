"""Recompute METHODOLOGY.md 4.2 table from the live HyperCore API.
Rule: authority set(action) = {deployer} + subDeployers[action]
      + (oracleUpdater if set else deployer) for setOracle.
Each address -> (k, n): null -> (1, 1). Weakest = min by (k, -n)."""
import json, subprocess, sys
API = "https://api.hyperliquid.xyz/info"
def post(body):
    r = subprocess.run(["curl", "-s", "-m", "30", "-X", "POST", "-H", "Content-Type: application/json",
                        "-d", json.dumps(body), API], capture_output=True, text=True, check=True)
    return json.loads(r.stdout)
cache = {}
def kn(a):
    if a not in cache:
        m = post({"type": "userToMultiSigSigners", "user": a})
        cache[a] = (1, 1) if m is None else (m["threshold"], len(m["authorizedUsers"]))
    return cache[a]
def fmt(t):
    return "single key" if t == (1, 1) else f"{t[0]}-of-{t[1]}"
def weakest(addrs):
    return min((kn(a) for a in addrs), key=lambda t: (t[0], -t[1]))
out = {}
for d in post({"type": "perpDexs"}):
    if d is None:
        continue
    sub = dict((k, v) for k, v in d.get("subDeployers") or [])
    dep = d["deployer"]
    so = {dep, d.get("oracleUpdater") or dep, *sub.get("setOracle", [])}
    ht = {dep, *sub.get("haltTrading", [])}
    out[d["name"]] = (fmt(kn(dep)), fmt(weakest(so)), fmt(weakest(ht)), len(d.get("assetToStreamingOiCap") or []))
if len(sys.argv) > 1:
    print(json.dumps(out))
else:
    for k, v in out.items():
        print(f"| {k} | {v[0]} | {v[1]} | {v[2]} | {v[3]} |")
