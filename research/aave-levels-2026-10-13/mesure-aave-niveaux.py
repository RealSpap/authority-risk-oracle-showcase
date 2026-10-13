#!/usr/bin/env python3
"""Level 0-5 (Aave's Technical Asset Listing Framework) of every role read on chain,
for the Aave V3 Ethereum Core reserves. Read-only, standard library only.

Usage:
  python3 mesure-aave-niveaux.py --block 26159551 [--limit 25] [--no-extra] [--json out.json]

Grid: 0 = EOA with no delay; 1 = multisig below the honest majority (threshold <= n/2);
2 = honest-majority multisig with no timelock; 3 = multisig + timelock < 48 h;
4 = multisig + timelock >= 48 h; 5 = on-chain DAO governance with a timelock.
An API error is never a zero: it is written NOT READ and listed at the end.
"""
import argparse, base64, functools, http.client, json, os, sys, time, urllib.error, urllib.parse, urllib.request

# ---------------------------------------------------------------- keccak256 (pure Python)
_RC = [0x0000000000000001, 0x0000000000008082, 0x800000000000808A, 0x8000000080008000,
       0x000000000000808B, 0x0000000080000001, 0x8000000080008081, 0x8000000000008009,
       0x000000000000008A, 0x0000000000000088, 0x0000000080008009, 0x000000008000000A,
       0x000000008000808B, 0x800000000000008B, 0x8000000000008089, 0x8000000000008003,
       0x8000000000008002, 0x8000000000000080, 0x000000000000800A, 0x800000008000000A,
       0x8000000080008081, 0x8000000000008080, 0x0000000080000001, 0x8000000080008008]
_ROT = [[0, 36, 3, 41, 18], [1, 44, 10, 45, 2], [62, 6, 43, 15, 61], [28, 55, 25, 21, 56], [27, 20, 39, 8, 14]]
_M = (1 << 64) - 1


def _f(A):
    for rc in _RC:
        C = [A[x][0] ^ A[x][1] ^ A[x][2] ^ A[x][3] ^ A[x][4] for x in range(5)]
        D = [C[(x - 1) % 5] ^ (((C[(x + 1) % 5] << 1) | (C[(x + 1) % 5] >> 63)) & _M) for x in range(5)]
        A = [[A[x][y] ^ D[x] for y in range(5)] for x in range(5)]
        B = [[0] * 5 for _ in range(5)]
        for x in range(5):
            for y in range(5):
                r = _ROT[x][y]
                B[y][(2 * x + 3 * y) % 5] = ((A[x][y] << r) | (A[x][y] >> (64 - r))) & _M if r else A[x][y]
        A = [[B[x][y] ^ ((~B[(x + 1) % 5][y]) & B[(x + 2) % 5][y]) for y in range(5)] for x in range(5)]
        A[0][0] ^= rc
    return A


@functools.lru_cache(maxsize=None)
def keccak(data):
    if isinstance(data, str):
        data = data.encode()
    rate = 136
    p = bytearray(data) + b"\x01" + b"\x00" * ((-len(data) - 2) % rate) + b"\x80"
    if len(p) % rate:  # case where a single padding byte is enough
        p = bytearray(data) + b"\x81"
    A = [[0] * 5 for _ in range(5)]
    for off in range(0, len(p), rate):
        blk = p[off:off + rate]
        for i in range(rate // 8):
            A[i % 5][i // 5] ^= int.from_bytes(blk[8 * i:8 * i + 8], "little")
        A = _f(A)
    out = b"".join(A[i % 5][i // 5].to_bytes(8, "little") for i in range(4))
    return "0x" + out.hex()


def sel(sig):
    return keccak(sig)[:10]


assert keccak("") == "0xc5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470"
assert keccak("PAUSER_ROLE") == "0x65d7a28e3265b37a6474929f336521b332c1681b933f6cb9f3376673440d862a"
assert sel("owner()") == "0x8da5cb5b" and sel("getThreshold()") == "0xe75235b8"
assert keccak("RoleGranted(bytes32,address,address)") == "0x2f8788117e7eff1d82e926ec794901d17c78024a50270940304540a733656f0d"

# ---------------------------------------------------------------- constants
POOL = "0x87870bca3f3fd6335c3f4ce8392d69350b4fa4e2"
ENDPOINTS = ["https://mainnet.gateway.tenderly.co", "https://eth.llamarpc.com", "https://ethereum-rpc.publicnode.com"]
COUNT = {}
SLOTS = {
    "impl1967": "0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc",
    "admin1967": "0xb53127684a568b3173ae13b9f8a6016e243e63b6e8ee1178d6a717850b5d6103",
    "beacon1967": "0xa3f0ad74e5423aebfd80d3ef4346578335a9a72aeaee59ff6cb3582b35133d50",
    "zosAdmin": "0x10d6a54a4754c8869d6886b5f5d7fbfa5b4522237ea5c60d11bc4e7a1ff9390b",
    "zosImpl": "0x7050c9e0f4ca769c69bd3a8ef740bc37934f8e2c036e5a723fd8ee048ed3f8c3",
}
ROLE_NAMES = ["PAUSER_ROLE", "UNPAUSER_ROLE", "MINTER_ROLE", "BURNER_ROLE", "BLACKLISTER_ROLE",
              "BLACKLIST_MANAGER_ROLE", "UPGRADER_ROLE", "OPERATOR_ROLE", "CLAIMER_ROLE", "FREEZER_ROLE",
              "FACILITATOR_MANAGER_ROLE", "BUCKET_MANAGER_ROLE", "PROPOSER_ROLE", "EXECUTOR_ROLE",
              "CANCELLER_ROLE", "TIMELOCK_ADMIN_ROLE", "SNAPSHOT_ROLE", "GATEKEEPER_ROLE", "MANAGER_ROLE",
              "ADMIN_ROLE", "RESCUER_ROLE", "DENYLISTER_ROLE", "FREEZE_ROLE", "SANCTIONS_ROLE",
              "COLLATERAL_RATIO_PAUSER", "MINTER", "BRIDGE_ROLE", "RELAYER_ROLE"]
ROLES = {keccak(n): n for n in ROLE_NAMES}
ZERO32 = "0x" + "00" * 32
ROLES[ZERO32] = "DEFAULT_ADMIN_ROLE"
T_ROLE_GRANTED = keccak("RoleGranted(bytes32,address,address)")
T_RELY = keccak("Rely(address)")
T_LOGNOTE_RELY = sel("rely(address)") + "00" * 28
T_MINTER_CONF = keccak("MinterConfigured(address,uint256)")
# DAOs recognised by address; membership is cross-checked on chain (the Executor's owner() = PayloadsController)
AAVE_EXECUTORS = {"0x5300a1a15135ea4dc7ad5a167152c01efc9b192a": "Aave Executor lvl1",
                  "0x17dd33ed0e3dd2a80e37489b8a63063161be6957": "Aave Executor lvl2"}
AAVE_PAYLOADS_CONTROLLER = "0xdabad81af85554e9ae636395611c58f7ec1aaec5"
# assets outside the first 25: 2 reserves listed further down, 2 unlisted assets with a LlamaRisk sheet
EXTRA = [("0xb0f70c0bd6fd87dbeb7c10dc692a2a6106817072", "Core reserve outside the first 25 (LlamaRisk sheet t/25652)"),
         ("0x4c9edd5852cd905f086c759e8383e09bff1e68b3", "Core reserve outside the first 25 (USDe sheets cover other chains)"),
         ("0x07041776f5007aca2a54844f50503a18a72a8b68", "USAT, not listed on Core (LlamaRisk sheet t/25832)"),
         ("0x6c6494fd9962eb98b94ffa48f6679058f820700e", "PAXGy, not listed on Core (LlamaRisk sheet t/25831)")]

# ---------------------------------------------------------------- RPC
BLOCK = None
NON_LU = []
_cache = {}
_last = [0.0]
_conns = {}


class RpcError(Exception):
    pass


def _connect(host):
    """HTTPS connection kept open, through the environment's HTTPS proxy if there is one."""
    px = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
    if not px:
        return http.client.HTTPSConnection(host, timeout=90)
    u = urllib.parse.urlparse(px)
    conn = http.client.HTTPSConnection(u.hostname, u.port or 443, timeout=90) if u.scheme == "https" else None
    if conn is None:
        conn = http.client.HTTPSConnection(u.hostname, u.port or 80, timeout=90)
        conn._create_connection = __import__("socket").create_connection  # plain-text CONNECT tunnel to the proxy
    hdr = {}
    if u.username:
        cred = "%s:%s" % (urllib.parse.unquote(u.username), urllib.parse.unquote(u.password or ""))
        hdr["Proxy-Authorization"] = "Basic " + base64.b64encode(cred.encode()).decode()
    conn.set_tunnel(host, 443, headers=hdr)
    return conn


def _post(url, method, params):
    gap = time.time() - _last[0]
    if gap < 0.12:
        time.sleep(0.12 - gap)
    _last[0] = time.time()
    host = url.split("/")[2]
    path = "/" + "/".join(url.split("/")[3:])
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
    for attempt in (0, 1):  # connection kept open; one reconnect if the server closed it
        conn = _conns.get(host) or _connect(host)
        _conns[host] = conn
        try:
            conn.request("POST", path, body, {"content-type": "application/json", "user-agent": "curl/8.4"})
            r = conn.getresponse()
            data = r.read()
        except (http.client.HTTPException, OSError):
            conn.close()
            _conns.pop(host, None)
            if attempt:
                raise
            continue
        if r.status != 200:
            raise urllib.error.HTTPError(url, r.status, r.reason, None, None)
        return json.loads(data)


def rpc(method, params):
    """Returns ('ok', result) | ('revert', msg) | ('err', msg). Never an invented zero."""
    key = json.dumps([method, params])
    if key in _cache:
        return _cache[key]
    last = "?"
    COUNT[method] = COUNT.get(method, 0) + 1
    for url in ENDPOINTS:
        for k in range(7):
            try:
                r = _post(url, method, params)
            except urllib.error.HTTPError as e:
                last = "HTTP %s on %s" % (e.code, url)
                if e.code == 429:
                    time.sleep(0.5 * 2 ** k)
                    continue
                break
            except Exception as e:  # network, timeout, unreadable JSON
                last = "%s on %s" % (type(e).__name__, url)
                if k < 3:
                    time.sleep(1)
                    continue
                break
            if "error" in r:
                msg = str(r["error"].get("message", r["error"]))
                if r["error"].get("code") == 3 or "revert" in msg.lower():
                    out = ("revert", msg)
                    _cache[key] = out
                    return out
                last = "%s on %s" % (msg[:120], url)
                if k < 3:  # server error: retry before moving on to the next endpoint
                    time.sleep(0.5 * 2 ** k)
                    continue
                break
            out = ("ok", r["result"])
            _cache[key] = out
            return out
    out = ("err", last)
    _cache[key] = out
    return out


def note_err(what, msg):
    NON_LU.append((what, msg))


def call(to, data, what=None):
    st, res = rpc("eth_call", [{"to": to, "data": data}, BLOCK])
    if st == "err":
        note_err(what or "eth_call %s %s" % (to, data[:10]), res)
    return st, res


def word_addr(h):
    """A 32-byte word shaped like an address, otherwise None."""
    if not h or len(h) != 66 or h[2:26] != "0" * 24:
        return None
    return "0x" + h[26:]


def get_addr(to, sig):
    st, res = call(to, sel(sig), "%s on %s" % (sig, to))
    if st != "ok":
        return st, None
    a = word_addr(res)
    return ("ok", a) if a is not None else ("absent", None)


def get_uint(to, sig):
    st, res = call(to, sel(sig), "%s on %s" % (sig, to))
    if st == "ok" and res and len(res) == 66:
        return "ok", int(res, 16)
    return (st if st != "ok" else "absent"), None


def storage(addr, slot):
    st, res = rpc("eth_getStorageAt", [addr, slot, BLOCK])
    if st != "ok":
        note_err("eth_getStorageAt %s %s" % (addr, slot[:10]), res)
        return "err", None
    return "ok", "0x" + res[-40:] if int(res, 16) else None


def get_code(addr):
    st, res = rpc("eth_getCode", [addr, BLOCK])
    if st != "ok":
        note_err("eth_getCode %s" % addr, res)
        return None
    return res


def logs(addr, topics, lo=0, hi=None):
    hi = int(BLOCK, 16) if hi is None else hi
    st, res = rpc("eth_getLogs", [{"address": addr, "topics": topics, "fromBlock": hex(lo), "toBlock": hex(hi)}])
    if st == "ok":
        return res
    if hi - lo < 1000:
        note_err("eth_getLogs %s %s [%d-%d]" % (addr, topics[0][:10], lo, hi), res)
        return None
    mid = (lo + hi) // 2  # range too wide: split in two
    a, b = logs(addr, topics, lo, mid), logs(addr, topics, mid + 1, hi)
    return None if a is None or b is None else a + b


def has_role(addr, role, acct):
    st, res = call(addr, sel("hasRole(bytes32,address)") + role[2:] + "0" * 24 + acct[2:],
                   "hasRole(%s,%s) on %s" % (ROLES.get(role, role[:10]), acct, addr))
    if st != "ok" or len(res) != 66:
        return None
    return int(res, 16) == 1


def role_holders(addr):
    """Current holders of each AccessControl role: RoleGranted events, then hasRole at the frozen block."""
    lg = logs(addr, [T_ROLE_GRANTED])
    if lg is None:
        return None
    seen, out = set(), []
    for l in lg:
        role, acct = l["topics"][1], "0x" + l["topics"][2][-40:]
        if (role, acct) in seen:
            continue
        seen.add((role, acct))
        h = has_role(addr, role, acct)
        if h is None:
            out.append((role, acct, "NOT READ"))
        elif h:
            out.append((role, acct, "ok"))
    # cross-check with getRoleMemberCount when the contract is enumerable
    for role in {r for r, _, _ in out}:
        st, res = call(addr, sel("getRoleMemberCount(bytes32)") + role[2:], "getRoleMemberCount on %s" % addr)
        if st == "ok" and len(res) == 66:
            n = int(res, 16)
            k = sum(1 for r, _, s in out if r == role and s == "ok")
            if n != k:
                note_err("mismatch getRoleMemberCount(%s)=%d against %d read from events on %s" % (ROLES.get(role, role[:10]), n, k, addr), "mismatch")
    return out


def ward_holders(addr):
    st, res = call(addr, sel("wards(address)") + "00" * 32, "wards(0) on %s" % addr)
    if st != "ok" or len(res) != 66:
        return []
    cands = set()
    for topics, idx in (([T_RELY], 1), ([T_LOGNOTE_RELY], 2)):
        lg = logs(addr, topics)
        if lg is None:
            return None
        for l in lg:
            if len(l["topics"]) > idx:
                cands.add("0x" + l["topics"][idx][-40:])
    out = []
    for c in sorted(cands):
        st, res = call(addr, sel("wards(address)") + "0" * 24 + c[2:], "wards(%s) on %s" % (c, addr))
        if st == "ok" and len(res) == 66 and int(res, 16) == 1:
            out.append(("wards (rely)", c))
        elif st == "err":
            out.append(("wards (rely) NOT READ", c))
    return out


def fiat_minters(addr):
    lg = logs(addr, [T_MINTER_CONF])
    if lg is None:
        return None
    out = []
    # FiatToken: MinterConfigured(address indexed minter, uint256); falls back to data if not indexed
    for c in sorted({"0x" + (l["topics"][1][-40:] if len(l["topics"]) > 1 else l["data"][26:66]) for l in lg}):
        st, res = call(addr, sel("isMinter(address)") + "0" * 24 + c[2:], "isMinter(%s) on %s" % (c, addr))
        if st == "ok" and len(res) == 66 and int(res, 16) == 1:
            out.append(("minter (FiatToken)", c))
    return out


# ---------------------------------------------------------------- controllers of a contract
GETTERS = ["owner()", "admin()", "minter()", "controller()", "authority()", "masterMinter()", "pauser()", "blacklister()",
           "guardian()", "RISK_COUNCIL()"]


def controllers(addr, with_minters=False):
    """List of (role, holder) read on a contract: proxy slots, getters, AccessControl, wards."""
    out, proxy = [], []
    for name in ("admin1967", "zosAdmin", "beacon1967", "impl1967", "zosImpl"):
        st, a = storage(addr, SLOTS[name])
        if st == "err":
            out.append(("slot %s NOT READ" % name, None))
        elif a:
            proxy.append(name)
            if name in ("admin1967", "zosAdmin"):
                out.append(("proxy admin (%s)" % name, a))
            elif name == "beacon1967":
                out.append(("beacon (upgrade)", a))
    fiat = False
    for g in GETTERS:
        st, a = get_addr(addr, g)
        if st == "err":
            out.append(("%s NOT READ" % g, None))
        elif st == "ok":
            if g == "masterMinter()":
                fiat = True
            if int(a, 16) == 0:
                out.append(("%s = 0x0 (renounced or empty)" % g, "0x" + "0" * 40))
            elif a.lower() != addr.lower():
                out.append((g, a))
    rh = role_holders(addr)
    if rh is None:
        out.append(("RoleGranted NOT READ", None))
    else:
        for role, acct, s in rh:
            out.append((ROLES.get(role, "role " + role[:10]) + ("" if s == "ok" else " NOT READ"), acct))
    wh = ward_holders(addr)
    if wh is None:
        out.append(("Rely NOT READ", None))
    else:
        out.extend(wh)
    if fiat and with_minters:
        fm = fiat_minters(addr)
        out.extend(fm if fm is not None else [("MinterConfigured NOT READ", None)])
    return proxy, out


# ---------------------------------------------------------------- classifying a holder
_class = {}


def classify(addr, depth=0, stack=()):
    """Returns (level or None, description). None = unclassified (NOT READ, or a mechanism outside the grid)."""
    addr = addr.lower()
    if addr in _class:
        return _class[addr]
    if addr in stack or depth > 5:
        return (None, "loop or depth > 5")
    code = get_code(addr)
    if code is None:
        res = (None, "NOT READ (eth_getCode)")
    elif code in ("0x", ""):
        res = (0, "EOA")
    elif code.startswith("0xef0100"):
        res = (0, "EOA delegated by EIP-7702 to 0x%s" % code[8:48])
    else:
        res = _classify_contract(addr, depth, stack + (addr,))
    _class[addr] = res
    return res


def _short(a):
    return a[:6] + ".." + a[-4:]


def _safe(addr):
    st, s = get_uint(addr, "getThreshold()")
    kind = "Safe"
    if st != "ok":
        st2, s = get_uint(addr, "required()")
        if st2 != "ok":
            return None if st != "err" and st2 != "err" else "err"
        kind = "MultiSigWallet"
    st, res = call(addr, sel("getOwners()"), "getOwners() on %s" % addr)
    if st != "ok":
        return "err"
    n = int(res[66:130], 16) if len(res) >= 130 else None
    if not n or not s:
        return "err"
    mods = ""
    if kind == "Safe":
        st, res = call(addr, sel("getModulesPaginated(address,uint256)") + "0" * 63 + "1" + "%064x" % 10, "getModulesPaginated on %s" % addr)
        if st == "ok" and len(res) >= 194:
            k = int(res[130:194], 16)
            mods = ", %d module(s)" % k if k else ""
        elif st == "err":
            mods = ", modules NOT READ"
    lvl = 2 if s * 2 > n else 1
    return (lvl, "%s %d/%d%s" % (kind, s, n, mods), s, n)


def _is_dao(addr):
    """Description starting with 'DAO ' if the contract is on-chain governance, otherwise None."""
    if addr in AAVE_EXECUTORS:
        st, o = get_addr(addr, "owner()")
        if st == "ok" and o == AAVE_PAYLOADS_CONTROLLER:
            return "DAO %s (owner = PayloadsController)" % AAVE_EXECUTORS[addr]
        return None
    st, v = get_uint(addr, "votingPeriod()")
    if st == "ok" and v:
        return "DAO Governor (votingPeriod %d)" % v
    st, a = get_addr(addr, "hat()")
    if st == "ok":
        return "DAO DSChief (token vote, hat %s)" % _short(a)
    return None


def _eff(cl, cd):
    """Level of a controller placed in front of a timelock: a DAO counts as 5."""
    return 5 if cd.startswith("DAO ") else cl


def _after_delay(eff, d):
    """Level obtained when a controller of level eff acts through a delay d."""
    if eff is None:
        return None
    if eff == 5:
        return 5
    if eff >= 2:  # honest-majority multisig, or already behind a timelock
        return max(eff, 2 if d == 0 else (4 if d >= 172800 else 3))
    return eff  # EOA or minority multisig: the delay does not raise them (conservative)


def _brief(a, cl, cd):
    """Short description of a controller, without unfolding generic contracts."""
    if cd.startswith("contract"):
        return "%s (contract, level %s)" % (_short(a), fmt_lvl(cl))
    return "%s %s" % (_short(a), cd)


def _top(items, k=3):
    """items = (level, text): the k weakest first, then the remaining count."""
    items = sorted(items, key=lambda x: (99 if x[0] is None else x[0], 0 if " EOA" in x[1] else 1))
    out = " ; ".join(t for _, t in items[:k])
    return out + (" ; + %d other(s)" % (len(items) - k) if len(items) > k else "")


def _classify_contract(addr, depth, stack):
    dao = _is_dao(addr)
    if dao:
        # an Aave Executor already sits behind the PayloadsController delay; a Governor alone is outside the grid
        return (5 if addr in AAVE_EXECUTORS else None, dao)
    sf = _safe(addr)
    if sf == "err":
        return (None, "multisig NOT READ")
    if sf:
        return sf[0], sf[1]
    st, d = get_uint(addr, "getMinDelay()")
    if st == "ok":  # TimelockController OpenZeppelin
        rh = role_holders(addr)
        if rh is None:
            return (None, "TimelockController %d s, RoleGranted NOT READ" % d)
        by = {}
        for r, a, s_ in rh:
            by.setdefault(ROLES.get(r, r[:10]), []).append(a)
        execs = by.get("EXECUTOR_ROLE", [])
        open_exec = (not execs) or ("0x" + "0" * 40) in execs
        ex_lvl, ex_desc = None, "open executor" if open_exec else ""
        if not open_exec:
            el = [(a,) + classify(a, depth + 1, stack) for a in execs if a != addr]
            lv = [_eff(c, dsc) for _, c, dsc in el]
            ex_lvl = None if (not lv or None in lv) else min(lv)
            ex_desc = "EXECUTOR " + _top([(c, _brief(a, c, dsc)) for a, c, dsc in el])
        best, parts, unk = None, [], False
        for role in ("PROPOSER_ROLE", "TIMELOCK_ADMIN_ROLE", "DEFAULT_ADMIN_ROLE"):
            for a in by.get(role, []):
                if a == addr:
                    continue
                cl, cd = classify(a, depth + 1, stack)
                e = _eff(cl, cd)
                if role == "PROPOSER_ROLE" and not open_exec and e is not None:
                    e = None if ex_lvl is None else max(e, ex_lvl)  # proposer AND executor are both required
                lv = _after_delay(e, d)
                parts.append("%s %s" % (role.replace("_ROLE", ""), _brief(a, cl, cd)))
                if lv is None:
                    unk = True
                else:
                    best = lv if best is None else min(best, lv)
        if not parts:
            return (None, "TimelockController %d s with no proposer or admin read" % d)
        return (best, "TimelockController %d s (%.0f h) <- %s ; %s%s" % (
            d, d / 3600, " ; ".join(parts), ex_desc, " [partly unclassified]" if unk else ""))
    st, d = get_uint(addr, "delay()")
    if st == "ok":  # Compound Timelock or DSPause: admin()/owner()/authority() act through the delay
        best, parts, unk = None, [], False
        for g in ("admin()", "owner()", "authority()"):
            s2, a = get_addr(addr, g)
            if s2 == "ok" and int(a, 16) and a != addr:
                cl, cd = classify(a, depth + 1, stack)
                lv = _after_delay(_eff(cl, cd), d)
                parts.append("%s %s" % (g, _brief(a, cl, cd)))
                if lv is None:
                    unk = True
                else:
                    best = lv if best is None else min(best, lv)
        if parts:
            return (best, "Timelock delay() %d s (%.0f h) <- %s%s" % (d, d / 3600, " ; ".join(parts), " [partly unclassified]" if unk else ""))
    st, k = get_addr(addr, "kernel()")
    if st == "ok":
        return (None, "Aragon app (kernel %s), ACL not derived" % _short(k))
    _, cs = controllers(addr)  # generic contract: go up to its own controllers
    seen, best, parts, unk = set(), None, [], False
    for r, a in cs:
        if a is None:
            unk = True
            parts.append((None, r))
            continue
        if not int(a, 16) or (r, a) in seen:
            continue
        seen.add((r, a))
        cl, cd = classify(a, depth + 1, stack)
        parts.append((cl, "%s %s" % (r, _brief(a, cl, cd))))
        if cl is None:
            unk = True
        else:
            best = cl if best is None else min(best, cl)
    if not parts:
        return (None, "contract with no controller read (immutable or registry not read)")
    return (best, "contract <- " + _top(parts) + (" [partly unclassified]" if unk else ""))


# ---------------------------------------------------------------- reserves and output
def reserves():
    st, res = call(POOL, sel("getReservesList()"), "getReservesList")
    if st != "ok":
        sys.exit("getReservesList NOT READ: %s" % res)
    h = res[2:]
    n = int(h[64:128], 16)
    return ["0x" + h[128 + 64 * i + 24:128 + 64 * (i + 1)] for i in range(n)]


def symbol(a):
    st, res = call(a, sel("symbol()"), "symbol() on %s" % a)
    if st != "ok":
        return "NOT READ"
    h = res[2:]
    if len(h) == 64:
        return bytes.fromhex(h).rstrip(b"\0").decode(errors="replace")
    l = int(h[64:128], 16)
    return bytes.fromhex(h[128:128 + 2 * l]).decode(errors="replace")


def fmt_lvl(l):
    return "?" if l is None else str(l)


def witnesses():
    out = []
    st, res = call("0x000000000000000000000000000000000000dEaD", sel("getThreshold()"), "witness getThreshold on dEaD")
    out.append(("getThreshold() on 0x...dEaD", "%s %s" % (st, res), st == "ok" and res == "0x"))
    rnd = keccak("aave-levels-witness-2026-10-13")[:42]
    gho = "0x40d16fc0246ad3160ccc09b8d0d3a2cd28ae6c2f"
    fm = keccak("FACILITATOR_MANAGER_ROLE")
    h = has_role(gho, fm, rnd)
    out.append(("hasRole(FACILITATOR_MANAGER_ROLE, %s) on GHO" % rnd, str(h), h is False))
    return out


def main():
    global BLOCK
    ap = argparse.ArgumentParser()
    ap.add_argument("--block", type=int, required=True)
    ap.add_argument("--limit", type=int, default=25)
    ap.add_argument("--no-extra", action="store_true")
    ap.add_argument("--json")
    ap.add_argument("--compact", action="store_true", help="group holders of the same role and type")
    a = ap.parse_args()
    BLOCK = hex(a.block)
    lst = reserves()
    print("# Frozen block %d (%s), %d reserves on the Core Pool, first %d read\n" % (a.block, BLOCK, len(lst), min(a.limit, len(lst))))
    assets = [(x, "reserve #%d" % i) for i, x in enumerate(lst[:a.limit])]
    if not a.no_extra:
        assets += EXTRA
    rows, summary = [], []
    for addr, origin in assets:
        sym = symbol(addr)
        print("... %s %s" % (sym, addr), file=sys.stderr, flush=True)
        proxy, cs = controllers(addr, with_minters=True)
        roles = []
        for r, h in cs:
            if h is None:
                roles.append((r, "-", None, "NOT READ"))
            elif int(h, 16) == 0:
                roles.append((r, "0x0", None, "no holder"))
            else:
                l, d = classify(h)
                roles.append((r, h, l, d))
        held = [x for x in roles if x[1] not in ("-", "0x0")]
        known = [x[2] for x in held if x[2] is not None]
        unk = any(x[2] is None for x in held) or any(x[1] == "-" for x in roles)
        alvl = (fmt_lvl(min(known)) + (" (+ unclassified)" if unk else "")) if known else ("unclassified" if unk else "")
        if not held and not unk:
            alvl = "no role read"
        summary.append((sym, addr, origin, alvl, min(known) if known else None))
        px = "yes (%s)" % ",".join(proxy) if proxy else "no"
        if not roles:
            rows.append((sym, addr, px, "-", "-", "no privileged role read by the standard reads", "-", alvl))
        for r, h, l, d in roles:
            rows.append((sym, addr, px, r, h, d, fmt_lvl(l), alvl))
    if a.json:
        json.dump({"block": a.block, "rows": rows, "summary": summary, "non_lu": NON_LU}, open(a.json, "w"), indent=1)
    rows = [r[:4] + ((_short(r[4]) if r[4].startswith("0x") and len(r[4]) == 42 else r[4]),) + r[5:] for r in rows]
    if a.compact:  # same asset, same role, same type: one line with the holder count
        grouped, order = {}, []
        for r in rows:
            k = (r[0], r[3], r[5], r[6])
            if k not in grouped:
                order.append(k)
                grouped[k] = list(r)
                grouped[k].append(1)
            else:
                grouped[k][-1] += 1
        rows = [tuple(g[:4]) + ((g[4] if g[-1] == 1 else "%d holders" % g[-1]),) + tuple(g[5:8])
                for g in (grouped[k] for k in order)]
    print("| asset | address | proxy? | role | holder | type | level | asset level |")
    print("|---|---|---|---|---|---|---|---|")
    for r in rows:
        print("| " + " | ".join(str(c).replace("|", "/") for c in r) + " |")
    print("\n## Level per asset\n")
    for s in summary:
        print("- %s %s (%s) : %s" % (s[0], s[1], s[2], s[3]))
    print("\n## Witnesses\n")
    for w in witnesses():
        print("- %s -> %s : %s" % (w[0], w[1], "as expected" if w[2] else "NOT AS EXPECTED"))
    print("\n## NOT READ (%d)\n" % len(NON_LU))
    for w, m in NON_LU:
        print("- %s : %s" % (w, m))
    print("RPC calls: %s" % COUNT, file=sys.stderr)


if __name__ == "__main__":
    main()
