#!/usr/bin/env python3
"""A second opinion on every published admin-key score, from a reader that shares nothing with the scorer.

The scorer behind the oracle is a per-ecosystem program with its own methodology. This script knows none of it: on the target's
real chain it reads the EIP-1967 admin slot (then the ProxyAdmin's owner()), else owner(), else admin(), and classifies what it
finds (bare EOA, Safe t-of-n, timelock, other contract). Then it compares with the published adminKeyScore, whose public reading
is: 50 and above, "admin power is not a bare key"; under 20, "one key does everything". Two disagreements are reported:
  - the score says not a bare key, the live read finds a bare EOA;
  - the score says one key, the live read finds a Safe with a threshold of 3 or more, or a timelock.
A disagreement is a finding to review (the scorer may look at a different role than the proxy admin), not a verdict; an address
with none of the three getters is "unreadable", never "agrees". Standard library, read-only.

    python3 scripts/second_opinion.py --scores watch/scores --out watch/second_opinion.json --md watch/second_opinion.md
"""
import argparse, glob, hashlib, json, os, sys, time, urllib.request

# the targets live on mainnets; the oracles on testnets. Same map as the dashboard's MAINNET config (read 2026-10-10).
MAINNET = {"robinhood": "https://rpc.mainnet.chain.robinhood.com", "ethereum-l1": "https://ethereum-rpc.publicnode.com", "arbitrum": "https://arb1.arbitrum.io/rpc",
           "base": "https://mainnet.base.org", "plasma": "https://rpc.plasma.to", "tempo": "https://rpc.tempo.xyz", "monad": "https://rpc.monad.xyz", "hyperliquid": "https://rpc.hyperliquid.xyz/evm"}
SLOT_ADMIN = "0xb53127684a568b3173ae13b9f8a6016e243e63b6e8ee1178d6a717850b5d6103"
SLOT_IMPL = "0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc"    # EIP-1967 implementation: the code behind a proxy; a change here is an upgrade executed
SLOT_BEACON = "0xa3f0ad74e5423aebfd80d3ef4346578335a9a72aeaee59ff6cb3582b35133d50"  # EIP-1967 beacon: the implementation is the beacon's implementation()
SLOT_GUARD = "0x4a204f620c8c5ccdca3fd54d003badd85ba500436a431f0cbda4f558c93c34c8"   # Safe: keccak256("guard_manager.guard.address"), the transaction guard (checks every execution)
MODULES_PAGE = "0xcc2f8452" + "1".rjust(64, "0") + "32".rjust(64, "0")                  # Safe getModulesPaginated(SENTINEL 0x1, 50): a module executes without the owners' signatures
# Arbitrum-stack chains (Arbitrum One, Robinhood Chain as an Orbit chain): an L1 contract that calls the L2 appears under its alias,
# address + 0x1111…1111, which has no code on the L2. A "bare EOA" there may be an L1 timelock: un-alias it and look on Ethereum L1
# before calling it a key (Uniswap's governance timelock owns the Uniswap V3 factory on Robinhood Chain this way).
ARBITRUM_STACK = {"arbitrum", "robinhood"}
# Solana: the independent read is the program's upgrade authority (BPF upgradeable loader: Program account -> ProgramData account ->
# authority), then what that authority is (a plain key, a Squads multisig, immutable). Program ids checked live on mainnet 2026-10-10.
SOLANA_RPC = "https://api.mainnet-beta.solana.com"
SOL_LOADER, SOL_SYSTEM = "BPFLoaderUpgradeab1e11111111111111111111111", "11111111111111111111111111111111"
SQUADS = {"SQDS4ep65T869zMMBKyuUq6aD6EgTu8psMjkvj52pCf": "Squads v4", "SMPLecH534NA9acpos4G6x7uf3LWbCAwZQE9e8ZekMu": "Squads v3"}
_B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def b58encode(b):
    n = int.from_bytes(b, "big"); out = ""
    while n: n, r = divmod(n, 58); out = _B58[r] + out
    return "1" * (len(b) - len(b.lstrip(b"\0"))) + out


def b58decode(t):
    n = 0
    for c in t: n = n * 58 + _B58.index(c)
    return b"\0" * (len(t) - len(t.lstrip("1"))) + n.to_bytes((n.bit_length() + 7) // 8, "big")


def on_curve(pubkey):
    """A program-derived address (a Squads vault, a protocol PDA) is off the ed25519 curve: no private key can ever sign for it.
    A system-owned account on the curve is a plain key. Same test as Solana's PublicKey.isOnCurve."""
    b = b58decode(pubkey)
    if len(b) != 32: return None
    P = 2 ** 255 - 19; D = (-121665 * pow(121666, P - 2, P)) % P
    y = int.from_bytes(b, "little") & ((1 << 255) - 1)
    if y >= P: return False
    u, v = (y * y - 1) % P, (D * y * y + 1) % P
    x2 = u * pow(v, P - 2, P) % P
    return x2 == 0 or pow(x2, (P - 1) // 2, P) == 1


def on_curve_bytes(b):
    P_ = 2 ** 255 - 19; D_ = (-121665 * pow(121666, P_ - 2, P_)) % P_
    y = int.from_bytes(b, "little") & ((1 << 255) - 1)
    if y >= P_: return False
    u, v = (y * y - 1) % P_, (D_ * y * y + 1) % P_; x2 = u * pow(v, P_ - 2, P_) % P_
    return x2 == 0 or pow(x2, (P_ - 1) // 2, P_) == 1


SQUADS_V4 = "SQDS4ep65T869zMMBKyuUq6aD6EgTu8psMjkvj52pCf"; SQUADS_MULTISIG_DISC = "eYVgUYyJkvP"   # base58 of sha256("account:Multisig")[:8]


def squads_vaults(pdas, cache_path, url=None):
    """Which Squads v4 multisig stands behind each program-derived upgrade authority: a vault is PDA(["multisig", multisig, "vault", 0])
    of its multisig, and the derivation cannot be inverted, so every v4 Multisig account on mainnet (one getProgramAccounts, about
    160 000 pubkeys) has its vault 0 derived and compared with the holders to resolve. Pure Python, about 90 s on a laptop; the
    resolved pairs are cached in watch/squads_vaults.json so the scan only runs again when a holder is not in the cache."""
    try: cache = json.load(open(cache_path)).get("vaults", {})
    except Exception: cache = {}  # noqa: BLE001
    missing = [p for p in pdas if p not in cache]
    if missing:
        accts = sol_rpc("getProgramAccounts", [SQUADS_V4, {"encoding": "base64", "dataSlice": {"offset": 0, "length": 0}, "filters": [{"memcmp": {"offset": 0, "bytes": SQUADS_MULTISIG_DISC}}]}], url) or []
        prog = b58decode(SQUADS_V4); want = set(missing)
        for acc in accts:
            ms = b58decode(acc["pubkey"])
            for bump in range(255, -1, -1):
                h = hashlib.sha256(b"multisig" + ms + b"vault" + bytes([0]) + bytes([bump]) + prog + b"ProgramDerivedAddress").digest()
                if not on_curve_bytes(h):
                    v = b58encode(h)
                    if v in want: cache[v] = acc["pubkey"]
                    break
        for p in missing: cache.setdefault(p, None)   # None = scanned, not a vault 0 of a v4 multisig (another program's PDA, or a vault of another index)
        tmp = cache_path + ".tmp"; json.dump({"what": "Squads v4 vault (upgrade authority) -> its Multisig account, resolved by deriving vault 0 of every v4 multisig; null = not a v4 vault 0; written by scripts/second_opinion.py", "vaults": cache}, open(tmp, "w"), indent=1); os.replace(tmp, cache_path)
    return cache


def squads_multisig(pubkey, url=None):
    """Threshold, members, native time lock and config authority of a Squads v4 Multisig account (borsh layout: discriminator 8,
    create_key 32, config_authority 32, threshold u16, time_lock u32, transaction_index u64, stale_transaction_index u64,
    rent_collector Option<Pubkey>, bump u8, members Vec<{key 32, permissions u8}>, then reserved bytes)."""
    import base64, struct
    r = sol_rpc("getAccountInfo", [pubkey, {"encoding": "base64"}], url)
    if not r or not r.get("value"): return None
    raw = base64.b64decode(r["value"]["data"][0]); o = 8 + 32; cfg = raw[o:o + 32]; o += 32
    thr = struct.unpack_from("<H", raw, o)[0]; o += 2; tl = struct.unpack_from("<I", raw, o)[0]; o += 4; o += 16
    has_rc = raw[o]; o += 1 + (32 if has_rc else 0); o += 1; nm = struct.unpack_from("<I", raw, o)[0]; o += 4
    if nm > 200 or o + 33 * nm > len(raw) or not (1 <= thr <= nm): return None   # a layout that does not add up is not a reading
    keys = [raw[o + 33 * i:o + 33 * i + 32] for i in range(nm)]; perms = [raw[o + 33 * i + 32] for i in range(nm)]   # permissions mask: 1 initiate, 2 vote, 4 execute
    voters = sum(1 for p in perms if p & 2); initiators = sum(1 for p in perms if p & 1); executors = sum(1 for p in perms if p & 4)
    tail = raw[o + 33 * nm:]; former = sum(1 for i in range(0, len(tail) - 32, 33) if tail[i:i + 32] != bytes(32))   # entries left in the account beyond the current members: former members kept after a removal (Squads reallocates, it does not wipe)
    return {"threshold": thr, "owners": nm, "delay_seconds": tl, "config_authority": None if cfg == bytes(32) else b58encode(cfg), "owners_kinds": {"eoa": sum(1 for k in keys if on_curve_bytes(k)), "pda": sum(1 for k in keys if not on_curve_bytes(k))},
            "voters": voters, "initiators": initiators, "executors": executors, "former_members_in_account": former}


def sol_rpc(method, params, url=None):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    for attempt in range(3):
        try:
            req = urllib.request.Request(url or SOLANA_RPC, body, {"Content-Type": "application/json", "User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as r: return json.loads(r.read()).get("result")
        except Exception: time.sleep(2.0 * (attempt + 1))
    return None


def sol_account(pubkey, url=None):
    r = sol_rpc("getAccountInfo", [pubkey, {"encoding": "base64"}], url)
    if r is None: return None   # not answered
    v = r.get("value")
    if not v: return {"exists": False}
    import base64
    return {"exists": True, "owner": v.get("owner"), "executable": v.get("executable"), "data": base64.b64decode(v["data"][0]) if v.get("data") else b""}


def solana_read(target, url=None):
    """upgrade authority of a program, classified. Returns (kind, holder, path, extra) or (None, None, why, {}). url: the cluster to read
    (mainnet for the targets, the oracle's own devnet for the oracle program)."""
    acc = sol_account(target, url)
    if acc is None: return (None, None, "rpc", {})
    if not acc["exists"]: return ("native", None, "no account at this address on mainnet", {})
    if not acc["executable"]:
        # a pool, a market, a stake pool: its code is the program that owns it, so its admin is that program's upgrade authority
        if acc["owner"] in (SOL_SYSTEM, "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA", "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"): return (None, None, "a plain account (owned by %s): no program behind it to read" % acc["owner"], {})
        kind, holder, path, extra = solana_read(acc["owner"], url)
        if kind is None: return (kind, holder, path, extra)
        return (kind, holder, "account owned by program %s… -> %s" % (acc["owner"][:8], path), dict(extra, via_program=acc["owner"]))
    if acc["owner"] != SOL_LOADER: return ("immutable", None, "program under %s (not the upgradeable loader): no upgrade authority" % acc["owner"], {})
    d = acc["data"]
    if len(d) < 36: return (None, None, "program account too short", {})
    pdata = b58encode(d[4:36]); pd = sol_account(pdata, url)
    if pd is None: return (None, None, "rpc", {})
    if not pd["exists"] or len(pd["data"]) < 13: return (None, None, "ProgramData account unreadable", {})
    slot_ = int.from_bytes(pd["data"][4:12], "little")   # since 2026-10-10: the slot of the last deployment, so an upgrade is seen between two runs whoever the authority is
    if pd["data"][12] == 0: return ("immutable", None, "ProgramData %s: upgrade authority renounced" % pdata[:8], {"programdata": pdata, "deployed_slot": slot_})
    auth = b58encode(pd["data"][13:45]); aa = sol_account(auth, url)
    if aa is None: return (None, None, "rpc", {})
    path = "program -> ProgramData %s… -> upgrade authority" % pdata[:6]
    if not aa["exists"] or aa["owner"] == SOL_SYSTEM:
        oc = on_curve(auth)
        if oc is False: return ("pda", auth, path + " (a program-derived address, off the curve: a Squads vault or a protocol PDA, no key can sign for it directly)", {"programdata": pdata, "deployed_slot": slot_})
        return ("eoa", auth, path + " (on the curve: a plain key)", {"programdata": pdata, "deployed_slot": slot_})
    if aa["owner"] in SQUADS: return ("squads", auth, path + " (%s multisig account)" % SQUADS[aa["owner"]], {"programdata": pdata, "deployed_slot": slot_, "multisig_program": SQUADS[aa["owner"]]})
    return ("contract", auth, path + " (account owned by program %s)" % aa["owner"], {"programdata": pdata, "deployed_slot": slot_})

ALIAS_OFFSET = 0x1111000000000000000000000000000000001111
L1_RPC = "https://ethereum-rpc.publicnode.com"
SEL = {"owner": "0x8da5cb5b", "admin": "0xf851a440", "getThreshold": "0xe75235b8", "getOwners": "0xa0e67e2b", "getMinDelay": "0xf27a0c92", "delay": "0x6a42b8f8", "implementation": "0x5c60da1b", "txCooldown": "0xdcafac09", "avatar": "0x5aef7de6", "authority": "0xbf7e214f", "pendingOwner": "0xe30c3978", "pendingAdmin": "0x26782247", "timelock": "0xd33219b4"}   # timelock(): a delay the contract enforces on itself (MetaMorpho vaults: 7 days), invisible from the holder   # pendingOwner(): Ownable2Step; pendingAdmin(): Compound-style timelocks and proxies: a transfer designated, not yet accepted   # txCooldown()/avatar(): Zodiac modules (Delay, Roles, Bridge) behind a Safe   # delay(): the Compound-style Timelock.sol (Uniswap governance) has delay() and admin(), not getMinDelay()
UA = "Mozilla/5.0 (second opinion; realspap.github.io/oracle)"


def chain_key(slug):
    return max([k for k in MAINNET if slug.startswith(k)], key=len, default=None)


ERRORS_SEEN = {}
RPC_ERRORS = 0   # transport or batch failures, counted apart from "no getter": an RPC that refuses is not a target without an owner


def _post(url, payload):
    req = urllib.request.Request(url, json.dumps(payload).encode(), {"Content-Type": "application/json", "User-Agent": UA})
    with urllib.request.urlopen(req, timeout=40) as r: return json.loads(r.read())


def rpc_batch(url, calls):
    """calls: list of (method, params); returns list of results, None per call that got no answer. A batch the endpoint refuses
    (some mainnet RPCs cap or reject JSON-RPC batches) is retried in batches of 5, then call by call: a refused batch is never
    read as 'no getter'. A reverted call (an address without that getter) is None too, and distinguished by the caller."""
    global RPC_ERRORS
    out = [None] * len(calls); got = [False] * len(calls)
    for size in (20, 5, 1):
        pending = [i for i in range(len(calls)) if not got[i]]
        if not pending: break
        for k in range(0, len(pending), size):
            idx = pending[k:k + size]
            payload = [{"jsonrpc": "2.0", "id": n, "method": calls[i][0], "params": calls[i][1]} for n, i in enumerate(idx)]
            res = None
            for attempt in range(2):
                try: res = _post(url, payload if size > 1 else payload[0]); break
                except Exception: time.sleep(1.0 * (attempt + 1))
            if res is None: continue   # the whole batch failed: a smaller size will retry these
            if isinstance(res, dict): res = [res]
            for x in res:
                n = x.get("id")
                if isinstance(n, int) and n < len(idx):
                    if "result" in x: got[idx[n]] = True; out[idx[n]] = x["result"]
                    else:
                        msg = str((x.get("error") or {}).get("message", "")).lower(); code = (x.get("error") or {}).get("code")
                        if "revert" in msg or "invalid opcode" in msg or "out of gas" in msg or code == 3 or code == -32000 and "execution" in msg:
                            got[idx[n]] = True; out[idx[n]] = ""   # "" = answered with a revert: the getter does not exist there
                        else:
                            ERRORS_SEEN[msg[:60] or str(code)] = ERRORS_SEEN.get(msg[:60] or str(code), 0) + 1   # a quota or node error is not an answer: retried in a smaller batch, else left None
            if size > 1: time.sleep(0.2)
    RPC_ERRORS += sum(1 for g in got if not g)
    return out


def classify_module(code, cooldown, avatar, owner, owner_code, safe):
    """What a Safe module or guard is, from four reads: no code = a plain key (as a module it executes through the Safe alone);
    txCooldown() answers = a Zodiac Delay (adds a delay, cooldown in seconds); avatar() answers = another Zodiac module (Roles, Bridge,
    Exit: scoped, not a bypass); else a contract; plus who owns it and whether that owner is the Safe itself (self-governed)."""
    if code in (None, ""): return {"kind": "unreadable"}
    if is_plain(code): return dict({"kind": "eoa"}, **({"delegated_to": delegation(code)} if delegation(code) else {}))
    d = {"kind": "zodiac-delay" if (cooldown and cooldown != "0x" and len(cooldown) == 66) else ("zodiac-module" if addr_of(avatar) else "contract"), "owner": owner,
         "owner_kind": None if (not owner or owner_code in (None, "")) else ("eoa" if is_plain(owner_code) else "contract"), "owner_is_the_safe": bool(owner and safe and same_addr(owner, safe))}
    if d["kind"] == "zodiac-delay":
        try: d["cooldown_seconds"] = int(cooldown, 16)
        except ValueError: pass
    return d


def same_addr(x, y):
    """The committed file carries shortened keys (this reader's own short(), and the signer redaction): compare what both forms keep."""
    x, y = str(x or ""), str(y or "")
    if "…" not in x and "…" not in y: return x.lower() == y.lower()
    return x[:6].lower() == y[:6].lower() and x[-4:].lower() == y[-4:].lower()


def short(a):
    """A plain key is never published in full by this reader (the index redaction only covers signers already known): 0x1234…abcd keeps
    enough to recognise and compare (same_addr), not enough to target. Contracts (Safes, timelocks) stay whole."""
    a = str(a or "")
    return a if len(a) <= 14 or "…" in a else a[:6] + "…" + a[-4:]


def delegation(code):
    """EIP-7702: a plain key account can carry a delegation designator, 0xef0100 followed by the 20-byte address of the code it runs. The key still
    controls the account, so it is a plain key, not a contract: before 2026-10-10 any account with code was called a contract here, and two real
    owners (a $493M vault on Ethereum, a contract on Robinhood) were 'a contract the reader cannot classify', outside the attacker's ranking."""
    c = code or ""
    return "0x" + c[8:48] if len(c) == 48 and c.lower().startswith("0xef0100") else None


def is_plain(code):
    """No code, or only a 7702 delegation: a plain key. None (not read) is neither."""
    return code is not None and (len(code) <= 2 or delegation(code) is not None)


PROXY_MARKER = "43616e6e6f742063616c6c2066616c6c6261636b2066756e6374696f6e206672"   # "Cannot call fallback function fr(om the proxy admin)", the revert text of the transparent proxy


def immutable_admin(code, impl=None):
    """A transparent proxy whose admin is an immutable, written in its bytecode instead of the EIP-1967 admin slot: the slot reads zero, owner() and
    admin() are forwarded to the implementation, and the reader called the target unreadable (an Arbitrum proxy scored 65 on 10/10). Recognised only
    by the proxy's own revert text plus upgradeTo(address), and only when exactly one address-shaped constant (PUSH32, 12 zero bytes then 20) is left
    once the implementation is set aside; anything else is None, never a guess."""
    c = (code or "").lower()
    c = c[2:] if c.startswith("0x") else c
    if PROXY_MARKER not in c or "3659cfe6" not in c: return None
    found = {c[i + 26:i + 66] for i in range(0, len(c) - 65, 2) if c[i:i + 2] == "7f" and c[i + 2:i + 26] == "0" * 24}   # byte-aligned scan
    found.discard("0" * 40); found.discard((impl or "")[2:].lower())
    return "0x" + found.pop() if len(found) == 1 else None


def final_holder(h, owner_word, beacon_owner_word):
    """(address, path) of the holder after the ProxyAdmin hop. h = (address, path, flag): flag True = the address is a ProxyAdmin behind the EIP-1967 slot, "rpc" = the target's code was not read.
    A beacon proxy has no admin of its own: the owner of its beacon decides its implementation, so it comes before the target's own owner() (forwarded to the implementation, whose owner is not the upgrade authority)."""
    if h[0] and h[2] is True and addr_of(owner_word): return (addr_of(owner_word), h[1] + " -> ProxyAdmin owner()")
    if addr_of(beacon_owner_word): return (addr_of(beacon_owner_word), "beacon owner() (the beacon decides the implementation of every proxy on it)")
    return (h[0], "rpc" if h[2] == "rpc" else h[1])


def addr_of(word):
    if not word or len(word) < 42: return None
    a = "0x" + word[-40:]
    return None if int(a, 16) == 0 else a


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--scores", default="watch/scores"); ap.add_argument("--out", default="watch/second_opinion.json"); ap.add_argument("--md", default="watch/second_opinion.md"); ap.add_argument("--ack", default="data/second_opinion_acknowledged.json"); ap.add_argument("--tvl", default="watch/tvl.json"); ap.add_argument("--held", default="watch/held_assets.json", help="what each contract holds by its own account (held_assets.py): preferred to the protocol TVL for the attacker's question"); ap.add_argument("--events", default="watch/events.jsonl", help="the hash-chained event log: every admin change and every group that grew is appended there too")
    a = ap.parse_args(); results, dis, agree, unread, native, acked = [], [], 0, 0, 0, []
    try: ack = {str(k).lower(): v for k, v in (json.load(open(a.ack)).get("disagreements") or {}).items()}   # keys in the form every lookup below uses: an address pasted checksummed matches too   # reviewed by a human: still shown, no longer alarmed
    except Exception: ack = {}   # noqa: BLE001 -- an unreadable file acknowledges nothing
    prev = {}   # the previous run's reads: a holder that changed between two runs is an early warning the weekly scorer cannot give
    try:
        for r in json.load(open(a.out)).get("results", []): prev[r["chain"] + ":" + str(r["target"]).lower()] = r
        prev_utc = json.load(open(a.out)).get("generated_utc")
    except Exception: prev_utc = None  # noqa: BLE001
    changes = []; upgrades = []; now_utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    def carry_since(rec, pr, moved):   # "admin unchanged since": the earliest run that read the same holder, carried from run to run
        rec["since"] = (pr.get("since") or prev_utc or now_utc) if (pr and not moved and pr.get("kind") not in (None, "unreadable", "native")) else now_utc
    for f in sorted(glob.glob(os.path.join(a.scores, "*.json"))):
        d = json.load(open(f)); slug = os.path.basename(f)[:-5]; key = chain_key(slug)
        if d.get("kind") != "evm" or not key: continue
        url = MAINNET[key]; targets = [t for t in d.get("targets", []) if str(t.get("target", "")).startswith("0x")]
        # pass 1: admin slot, owner(), admin() for every target
        c1 = []
        for t in targets:
            c1 += [("eth_getStorageAt", [t["target"], SLOT_ADMIN, "latest"]), ("eth_call", [{"to": t["target"], "data": SEL["owner"]}, "latest"]), ("eth_call", [{"to": t["target"], "data": SEL["admin"]}, "latest"]), ("eth_getCode", [t["target"], "latest"]),
                   ("eth_getStorageAt", [t["target"], SLOT_IMPL, "latest"]), ("eth_getStorageAt", [t["target"], SLOT_BEACON, "latest"]),   # since 2026-10-10: the code behind the proxy, so an executed upgrade is seen between two runs
                   ("eth_call", [{"to": t["target"], "data": SEL["pendingOwner"]}, "latest"]), ("eth_call", [{"to": t["target"], "data": SEL["pendingAdmin"]}, "latest"]),   # a transfer in flight on the target itself
                   ("eth_call", [{"to": t["target"], "data": SEL["timelock"]}, "latest"])]   # since 2026-10-10: a delay the contract enforces on itself
        b0 = rpc_batch(url, [("eth_blockNumber", [])])[0]; block_start = int(b0, 16) if b0 else None   # since 2026-10-10: the reads of this chain happen between block_start and block_end, said in every record
        r1 = rpc_batch(url, c1)
        holders = []; native_idx = set(); impls = []; pendings = []; self_delays = []
        for i, t in enumerate(targets):
            slot, own, adm, tcode = r1[9 * i], r1[9 * i + 1], r1[9 * i + 2], r1[9 * i + 3]
            impls.append((addr_of(r1[9 * i + 4]), addr_of(r1[9 * i + 5])))
            pendings.append((addr_of(r1[9 * i + 6]), "pendingOwner() on the contract (Ownable2Step)") if addr_of(r1[9 * i + 6]) else ((addr_of(r1[9 * i + 7]), "pendingAdmin() on the contract") if addr_of(r1[9 * i + 7]) else (None, None)))
            sd = r1[9 * i + 8]
            try: sd = int(sd, 16) if (sd and sd != "0x" and len(sd) == 66) else None
            except ValueError: sd = None
            self_delays.append(sd if (sd is not None and 60 <= sd <= 366 * 86400) else (0 if sd == 0 else None))   # a plausible delay in seconds; 0 = the getter answers zero; None = no such getter
            if tcode in (None, ""): holders.append((None, None, "rpc")); continue   # the target's code was not read: nothing can be said, not even "native"
            if len(tcode) <= 2:   # no code at the target itself: a derived identifier for a native entity (HyperCore validator set, HIP-3 dexes, HLP, Unit) or a contract on another chain (Robinhood's rollup contracts live on its parent chain)
                native_idx.add(i); holders.append((None, None, False)); continue
            if addr_of(slot): holders.append((addr_of(slot), "EIP-1967 admin", True))
            elif immutable_admin(tcode): holders.append((immutable_admin(tcode), "admin fixed in the proxy's bytecode (transparent proxy)", False))   # before owner(): a transparent proxy forwards owner() to its implementation, whose owner is not the upgrade authority
            elif addr_of(own): holders.append((addr_of(own), "owner()", False))
            elif addr_of(adm): holders.append((addr_of(adm), "admin()", False))
            else: holders.append((None, None, False))
        # pass 1b (since 2026-10-10): a target with no admin slot, owner() or admin() may be roles-based. AccessControl (ERC-165 id 0x7965db0b):
        # when enumerable, the first holder of DEFAULT_ADMIN_ROLE is the admin; AccessManaged: authority() is the AccessManager that holds every role.
        AC_IFACE = "0x01ffc9a7" + "7965db0b".ljust(64, "0"); AC_COUNT = "0xca15c873" + "0" * 64; AC_MEMBER = "0x9010d07c" + "0" * 128
        c1b_idx = [i for i, h in enumerate(holders) if not h[0] and h[2] is False and i not in native_idx]
        if c1b_idx:
            c1b = []
            for i in c1b_idx:
                x = targets[i]["target"]; c1b += [("eth_call", [{"to": x, "data": AC_IFACE}, "latest"]), ("eth_call", [{"to": x, "data": AC_COUNT}, "latest"]), ("eth_call", [{"to": x, "data": AC_MEMBER}, "latest"]), ("eth_call", [{"to": x, "data": SEL["authority"]}, "latest"])]
            r1b = rpc_batch(url, c1b); ac_note = {}
            for j, i in enumerate(c1b_idx):
                si, cnt, mem, auth = r1b[4 * j:4 * j + 4]
                is_ac = bool(si and len(si) == 66 and int(si, 16) == 1); n_members = int(cnt, 16) if (cnt and len(cnt) == 66) else None
                if is_ac and addr_of(mem): holders[i] = (addr_of(mem), "DEFAULT_ADMIN_ROLE member 1 of %s (AccessControl)" % (n_members if n_members is not None else "?"), False)
                elif addr_of(auth): holders[i] = (addr_of(auth), "authority() (AccessManaged: the AccessManager holds every role)", False)
                elif is_ac: ac_note[i] = "AccessControl (ERC-165) whose admin-role holders are not enumerable on-chain: read them from RoleGranted events; nothing for this reader to compare"
            for i, note in ac_note.items(): holders[i] = (None, note, False)
        # pass 2: a ProxyAdmin behind the slot has an owner(): follow one hop
        c2 = [("eth_call", [{"to": h[0], "data": SEL["owner"]}, "latest"]) if h[0] and h[2] is True else ("eth_blockNumber", []) for h in holders]
        r2 = rpc_batch(url, c2)
        r2p = rpc_batch(url, [("eth_call", [{"to": h[0], "data": SEL["pendingOwner"]}, "latest"]) if h[0] and h[2] is True else ("eth_blockNumber", []) for h in holders])   # a transfer in flight on the ProxyAdmin
        for i, (h, pp) in enumerate(zip(holders, r2p)):
            if h[0] and h[2] is True and addr_of(pp) and not pendings[i][0]: pendings[i] = (addr_of(pp), "pendingOwner() on the ProxyAdmin (Ownable2Step)")
        pend_idx = [i for i, p in enumerate(pendings) if p[0]]
        if pend_idx:   # what the designated admin is: a plain key leaves shortened, a contract stays whole (the same rule as every holder)
            rcode = rpc_batch(url, [("eth_getCode", [pendings[i][0], "latest"]) for i in pend_idx])
            for i, c_ in zip(pend_idx, rcode):
                if c_ is None: pendings[i] = (short(pendings[i][0]), pendings[i][1] + ", nature not read")   # unread = may be a plain key: it leaves shortened (fail closed)
                elif is_plain(c_): pendings[i] = (short(pendings[i][0]), pendings[i][1] + ", a plain key" + (" (EIP-7702 delegation)" if delegation(c_) else ""))
                else: pendings[i] = (pendings[i][0], pendings[i][1] + ", a contract")
        c2b = [("eth_call", [{"to": b, "data": SEL["implementation"]}, "latest"]) if (b and not im) else ("eth_blockNumber", []) for im, b in impls]   # a beacon proxy: the implementation is the beacon's
        r2b = rpc_batch(url, c2b)
        impl_final = [(im, "EIP-1967 implementation slot") if im else ((addr_of(o), "beacon implementation()") if (b and addr_of(o)) else (None, None)) for (im, b), o in zip(impls, r2b)]
        r2c = rpc_batch(url, [("eth_call", [{"to": b, "data": SEL["owner"]}, "latest"]) if (b and not im and h[2] is not True and h[2] != "rpc") else ("eth_blockNumber", []) for (im, b), h in zip(impls, holders)])   # a beacon proxy has no admin of its own: whoever owns the beacon decides its implementation
        final = []
        for h, o, bo in zip(holders, r2, r2c): final.append(final_holder(h, o, bo))
        # pass 3: what is the holder (code, Safe threshold/owners, timelock delay)
        c3 = []
        for addr, _ in final:
            x = addr or "0x" + "0" * 40
            c3 += [("eth_getCode", [x, "latest"]), ("eth_call", [{"to": x, "data": SEL["getThreshold"]}, "latest"]), ("eth_call", [{"to": x, "data": SEL["getOwners"]}, "latest"]), ("eth_call", [{"to": x, "data": SEL["getMinDelay"]}, "latest"]), ("eth_call", [{"to": x, "data": SEL["delay"]}, "latest"]),
                   ("eth_call", [{"to": x, "data": MODULES_PAGE}, "latest"]), ("eth_getStorageAt", [x, SLOT_GUARD, "latest"])]   # since 2026-10-10: a Safe's modules and guard, the two things that change what "t-of-n" means
        r3 = rpc_batch(url, c3)
        b1 = rpc_batch(url, [("eth_blockNumber", [])])[0]; block_end = int(b1, 16) if b1 else None
        r3n = rpc_batch(url, [("eth_getTransactionCount", [addr or "0x" + "0" * 40, "latest"]) for addr, _ in final])   # a plain key's nonce: how many transactions it has sent (0: never acted from this address)
        def modules_of(word):   # getModulesPaginated -> (address[] array, address next): offset, next, length, then the addresses
            try:
                if not word or len(word) < 2 + 64 * 3: return None
                n = int(word[2 + 128:2 + 192], 16)
                return [("0x" + word[2 + 192 + 64 * j + 24:2 + 192 + 64 * (j + 1)]).lower() for j in range(min(n, 50))]
            except ValueError: return None
        for i, (t, (addr, path)) in enumerate(zip(targets, final)):
            code, thr, own, dly, dly2, mods, grd = r3[7 * i], r3[7 * i + 1], r3[7 * i + 2], r3[7 * i + 3], r3[7 * i + 4], r3[7 * i + 5], r3[7 * i + 6]
            rec = {"chain": key, "target": t["target"], "adminKeyScore": t.get("adminKeyScore"), "path": path, "holder": addr, "impl": impl_final[i][0], "impl_via": impl_final[i][1],   # impl: the code behind the proxy (a contract address, public by nature), None for a non-proxy
                   "pending_admin": pendings[i][0], "pending_via": pendings[i][1],   # since 2026-10-10: a transfer designated and not yet accepted, the earliest warning of a change of hands
                   "block_start": block_start, "block_end": block_end,   # the reads of this record happened between these two blocks of the chain (public RPCs answer at latest; the span is a few blocks)
                   "self_delay_seconds": self_delays[i]}   # timelock() on the contract itself (MetaMorpho vaults enforce 7 days on curator actions); None when there is no such getter
            if i in native_idx:
                rec["kind"] = "native"; rec["why"] = "no code at this address on the chain's mainnet: a derived identifier for a native (non-EVM) entity such as HyperCore, or a contract that lives on another chain (a rollup's own L1 contracts); nothing for this reader to compare here"; native += 1; results.append(rec); continue
            if not addr or code in (None, "") or thr is None or own is None or dly is None or dly2 is None:   # a probe not answered is not a classification: fail closed, never guess "contract" (dly2 too, since 10/10: a Compound-style timelock read as "contract" on one flaky run was a false admin change)
                rec["kind"] = "unreadable"; rec["why"] = ("target code not read (RPC)" if path == "rpc" else (path if (path and path.startswith("AccessControl")) else "no admin slot, owner(), admin(), DEFAULT_ADMIN_ROLE member or authority() answered")) if not addr else "holder probes not all answered (RPC)"; unread += 1
                if path and path.startswith("AccessControl"): rec["access_control"] = True; rec["path"] = None
                results.append(rec); continue
            kind = "eoa" if is_plain(code) else "contract"
            if kind == "eoa" and delegation(code): rec["delegated_to"] = delegation(code)   # a plain key whose account runs a smart-wallet implementation (EIP-7702)
            if kind == "eoa":
                try: rec["holder_tx_count"] = int(r3n[i], 16) if r3n[i] else None   # a hot operational key or one that never acted: context, not a verdict
                except (ValueError, TypeError): rec["holder_tx_count"] = None
            if kind == "eoa" and key in ARBITRUM_STACK:
                l1 = "0x%040x" % ((int(addr, 16) - ALIAS_OFFSET) % (1 << 160))
                r_l1 = rpc_batch(L1_RPC, [("eth_getCode", [l1, "latest"]), ("eth_call", [{"to": l1, "data": SEL["getThreshold"]}, "latest"]), ("eth_call", [{"to": l1, "data": SEL["getOwners"]}, "latest"]), ("eth_call", [{"to": l1, "data": SEL["getMinDelay"]}, "latest"]), ("eth_call", [{"to": l1, "data": SEL["delay"]}, "latest"])])
                if r_l1[0] and len(r_l1[0]) > 2:   # the un-aliased address is a contract on L1: that is the real holder
                    rec["alias_of"] = l1; rec["path"] = path + " (Arbitrum L1 alias of " + l1 + " on Ethereum L1)"; path = rec["path"]; addr = l1; rec["holder"] = l1
                    code, thr, own, dly, dly2 = r_l1; kind = "contract"
            if kind != "eoa":
                kind = "contract"
                try:
                    tv = int(thr, 16) if thr and thr != "0x" else 0; n = int(own[2 + 64:2 + 128], 16) if own and len(own) >= 130 else 0
                    if 0 < tv <= 50 and n >= tv:
                        kind = "safe"; rec["threshold"], rec["owners"] = tv, n
                        rec["keys_to_act"], rec["keys_lost_to_freeze"] = tv, n - tv + 1   # the two faces of a multisig: t keys collude to act, n-t+1 keys lost and nobody can act (a 3-of-3 freezes on one lost key)
                        rec["modules"] = modules_of(mods) if mods not in (None, "", "0x") else (None if mods is None else [])   # None = not read (fail closed), [] = none enabled; a module executes without the t-of-n signatures
                        rec["guard"] = addr_of(grd) if grd is not None else None
                except ValueError: pass
                if kind == "contract" and dly and dly != "0x":
                    try: rec["delay_seconds"] = int(dly, 16); kind = "timelock"
                    except ValueError: pass
                if kind == "contract" and dly2 and dly2 != "0x" and len(dly2) == 66:   # Compound-style Timelock.sol: delay() in seconds
                    try: rec["delay_seconds"] = int(dly2, 16); kind = "timelock"; rec["timelock_family"] = "compound"
                    except ValueError: pass
            rec["kind"] = kind; s = t.get("adminKeyScore"); rec["multisigScore"] = t.get("multisigScore")
            pr = prev.get(key + ":" + t["target"].lower())
            if pr and pr.get("kind") not in (None, "unreadable", "native") and (not same_addr(pr.get("holder"), addr) or pr.get("kind") != kind or pr.get("threshold") != rec.get("threshold") or pr.get("owners") != rec.get("owners") or pr.get("delay_seconds") != rec.get("delay_seconds")
                            or (pr.get("modules") is not None and rec.get("modules") is not None and sorted(map(short, pr["modules"])) != sorted(map(short, rec["modules"]))) or (pr.get("guard") != rec.get("guard") and "guard" in pr)
                            or ("pending_admin" in pr and short(str(pr.get("pending_admin") or "")).lower() != short(str(rec.get("pending_admin") or "")).lower())
                            or ("self_delay_seconds" in pr and pr.get("self_delay_seconds") is not None and rec.get("self_delay_seconds") is not None and pr["self_delay_seconds"] != rec["self_delay_seconds"])):   # on short forms: a run that could not probe the nature keeps the address whole, the next one shortens a key, the same address must not read as a change   # since 2026-10-10 the delay too: a timelock whose delay drops to 0 is the admin path changing, not waiting for the weekly scorer
                def desc(x): return "%s %s" % (x.get("kind"), (short(x.get("holder")) if x.get("kind") == "eoa" else x.get("holder")) or "") + (" %s-of-%s" % (x["threshold"], x["owners"]) if x.get("kind") == "safe" else "") + (" %ss" % x["delay_seconds"] if x.get("kind") == "timelock" else "") + ((" +%d module(s)" % len(x["modules"])) if x.get("modules") else "") + (" guard %s" % x["guard"] if x.get("guard") else "") + ((" (transfer pending to %s)" % x["pending_admin"]) if x.get("pending_admin") else "") + ((" [contract timelock %ss]" % x["self_delay_seconds"]) if x.get("self_delay_seconds") else "") + ((" [signers: %s]" % ", ".join("%d %s" % (v, k) for k, v in sorted(x["owners_kinds"].items()))) if x.get("owners_kinds") else "")
                rec["changed"] = "admin read changed since the previous run: %s -> %s (via %s)" % (desc(pr), desc(rec), path); changes.append(rec)
            carry_since(rec, pr, bool(rec.get("changed")))
            if pr and pr.get("impl") and rec.get("impl") and not same_addr(pr["impl"], rec["impl"]):   # both reads answered and differ: an upgrade was executed between two runs
                rec["upgraded"] = "implementation changed since the previous run: %s -> %s (%s); the score reads who may upgrade, this is an upgrade that happened" % (pr["impl"], rec["impl"], rec.get("impl_via")); upgrades.append(rec)
            if kind == "safe" and rec.get("threshold") == 1 and rec.get("owners_detail") and not rec.get("nested") and s is not None and s >= 50 and any(d_["kind"] == "eoa" for d_ in rec["owners_detail"]):
                rec["disagree"] = "the score says admin power is not a bare key (%d), the live read finds a Safe with a threshold of 1 whose owner %s is a plain key via %s" % (s, [d_["owner"] for d_ in rec["owners_detail"] if d_["kind"] == "eoa"][0], path)
            elif kind == "eoa" and s is not None and s >= 50:
                rec["disagree"] = "the score says admin power is not a bare key (%d), the live read finds a bare EOA %s via %s" % (s, short(addr), path)
            elif kind == "safe" and rec.get("threshold", 0) >= 3 and s is not None and s < 20:
                rec["disagree"] = "the score says one key does everything (%d), the live read finds a Safe %d-of-%d via %s" % (s, rec["threshold"], rec["owners"], path)
            elif kind == "timelock" and s is not None and s < 20:
                rec["disagree"] = "the score says one key does everything (%d), the live read finds a timelock (%ss) via %s" % (s, rec.get("delay_seconds"), path)
            if kind == "safe" and own and len(own) >= 130:   # since 2026-10-10 every Safe, not only threshold 1: what the signers ARE (counts only, no address for a threshold above 1)
                # a Safe with a threshold of 1 is one key only if one of its owners is a key: look one level down (EigenLayer's executor
                # multisig is a 1-of-2 whose owners are an ops multisig and a timelock, by design)
                try:
                    n_own = int(own[2 + 64:2 + 128], 16); owners = ["0x" + own[2 + 128 + 64 * j + 24: 2 + 128 + 64 * (j + 1)] for j in range(min(n_own, 20))]
                except ValueError: owners = []
                if owners:
                    c4 = []
                    for o_ in owners: c4 += [("eth_getCode", [o_, "latest"]), ("eth_call", [{"to": o_, "data": SEL["getThreshold"]}, "latest"]), ("eth_call", [{"to": o_, "data": SEL["getOwners"]}, "latest"]), ("eth_call", [{"to": o_, "data": SEL["getMinDelay"]}, "latest"]), ("eth_call", [{"to": o_, "data": SEL["delay"]}, "latest"])]
                    r4 = rpc_batch(url, c4); det = []
                    for j, o_ in enumerate(owners):
                        oc, ot, oo, od, od2 = r4[5 * j: 5 * j + 5]; ok_ = "unread" if oc in (None, "") or ot is None or od is None else "eoa" if is_plain(oc) else "contract"
                        if ok_ == "contract":
                            try:
                                tv_ = int(ot, 16) if ot and ot != "0x" else 0; n_ = int(oo[2 + 64:2 + 128], 16) if oo and len(oo) >= 130 else 0
                                if 0 < tv_ <= 50 and n_ >= tv_: ok_ = "safe %d-of-%d" % (tv_, n_)
                            except ValueError: pass
                            if ok_ == "contract" and ((od and od != "0x") or (od2 and od2 != "0x" and len(od2) == 66)): ok_ = "timelock"
                        det.append({"owner": o_, "kind": ok_})
                    kinds_ = {}
                    for d_ in det: k_ = "safe" if d_["kind"].startswith("safe") else d_["kind"]; kinds_[k_] = kinds_.get(k_, 0) + 1
                    rec["owners_kinds"] = kinds_   # the signer set in kinds and counts (plain keys, Safes, timelocks, contracts, unread): a 3-of-5 of five keys is not a 3-of-5 of three Safes
                    pk_ = pr.get("owners_kinds") if pr else None   # composition change, compared here (after the read), only between two complete readings: an unread signer on either side is a flake, not a change
                    if pk_ and "unread" not in pk_ and "unread" not in kinds_ and pk_ != kinds_:
                        txt_ = "signer composition changed since the previous run: %s -> %s" % (", ".join("%d %s" % (v, k) for k, v in sorted(pk_.items())), ", ".join("%d %s" % (v, k) for k, v in sorted(kinds_.items())))
                        if rec.get("changed"): rec["changed"] += "; " + txt_
                        else: rec["changed"] = txt_; changes.append(rec); rec["since"] = now_utc
                    if rec.get("threshold") == 1: rec["owners_detail"] = [{"owner": short(d_["owner"]), "kind": d_["kind"]} for d_ in det]   # the routing-layer case keeps its (shortened) detail; above threshold 1 no signer address leaves, even shortened
                    if det and all(d_["kind"].startswith(("safe", "timelock")) and not d_["kind"].startswith("safe 1-of") for d_ in det):
                        rec["nested"] = True   # every owner is itself a real multisig or a timelock: the 1-of-N is a routing layer, not a key
            tl = t.get("timelockScore"); rec["timelockScore"] = tl   # third axis, one direction only: a live timelock of a day or more in the admin path against "no delay" (0)
            if kind == "timelock" and (rec.get("delay_seconds") or 0) >= 86400 and tl == 0:
                rec["disagree"] = (rec.get("disagree") + "; " if rec.get("disagree") else "") + "the timelock score says no delay (0), the live read finds a timelock of %d h in the admin path via %s" % (rec["delay_seconds"] // 3600, path)
            elif (rec.get("self_delay_seconds") or 0) >= 86400 and tl == 0:
                rec["disagree"] = (rec.get("disagree") + "; " if rec.get("disagree") else "") + "the timelock score says no delay (0), the contract enforces its own timelock of %d h (timelock())" % (rec["self_delay_seconds"] // 3600)
            any_delay = bool(rec.get("delay_seconds")) or bool(rec.get("self_delay_seconds")) or bool((rec.get("owners_kinds") or {}).get("timelock")) or any(m_.get("kind") == "zodiac-delay" and m_.get("cooldown_seconds") for m_ in (rec.get("modules_detail") or []))
            if kind in ("eoa", "safe") and tl is not None and tl >= 60 and not any_delay and (kind == "eoa" or rec.get("self_delay_seconds") == 0):   # the generous side: a confirmed delay in the score, none anywhere the reader looked; a bare key, or a Safe on a contract whose timelock() answers zero (a Safe on a contract without the getter may hide a delay the reader cannot see: no claim)
                rec["disagree"] = (rec.get("disagree") + "; " if rec.get("disagree") else "") + "the timelock score says a confirmed delay (%d), the live read finds none: the admin is %s via %s, no delay on the holder, its modules or its owners, and the contract's own timelock() %s" % (tl, "a plain key" if kind == "eoa" else "a Safe %s-of-%s" % (rec.get("threshold"), rec.get("owners")), path, "answers zero" if rec.get("self_delay_seconds") == 0 else "does not exist")
            ms = t.get("multisigScore")   # second axis, the multisig sub-score, publicly: 55 and above = "at least a 3-of-5"; under 20 = no real multisig
            if kind == "safe" and rec.get("threshold") == 1 and ms is not None and ms >= 55 and not rec.get("nested"):
                rec["disagree"] = (rec.get("disagree") + "; " if rec.get("disagree") else "") + "the multisig score says at least a 3-of-5 (%d), the live read finds a Safe with a threshold of 1 (%d owners) via %s" % (ms, rec.get("owners"), path)
            elif kind == "safe" and rec.get("threshold", 0) >= 3 and ms is not None and ms < 20:
                rec["disagree"] = (rec.get("disagree") + "; " if rec.get("disagree") else "") + "the multisig score says no real multisig (%d), the live read finds a Safe %d-of-%d via %s" % (ms, rec["threshold"], rec["owners"], path)
            if rec.get("disagree"):
                note = ack.get(key + ":" + t["target"].lower())
                if note: rec["acknowledged"] = str(note)[:300]; acked.append(rec)
                else: dis.append(rec)
            else: agree += 1
            results.append(rec)
        # pass 3b (since 2026-10-10): a holder read as a bare contract (no Safe, no timelock getter) often has an owner() of its own, and THAT is the hand:
        # Uniswap's V3 factory is owned by a 14 KB contract owned by the governance Timelock. One more hop, classified like a holder, with the same axes.
        bare = [r_ for r_ in results if r_["chain"] == key and r_.get("kind") == "contract" and r_.get("holder") and not r_.get("oracle_self")]
        if bare:
            ro = rpc_batch(url, [("eth_call", [{"to": r_["holder"], "data": SEL["owner"]}, "latest"]) for r_ in bare]); owners2 = [addr_of(o) for o in ro]
            idx2 = [j for j, o in enumerate(owners2) if o]
            if idx2:
                c5 = []
                for j in idx2: x = owners2[j]; c5 += [("eth_getCode", [x, "latest"]), ("eth_call", [{"to": x, "data": SEL["getThreshold"]}, "latest"]), ("eth_call", [{"to": x, "data": SEL["getOwners"]}, "latest"]), ("eth_call", [{"to": x, "data": SEL["getMinDelay"]}, "latest"]), ("eth_call", [{"to": x, "data": SEL["delay"]}, "latest"])]
                r5 = rpc_batch(url, c5)
                for n_, j in enumerate(idx2):
                    code2, thr2, own2, dly2a, dly2b = r5[5 * n_:5 * n_ + 5]; r_ = bare[j]; x = owners2[j]
                    if code2 in (None, "") or thr2 is None or dly2a is None: continue   # not all answered: no claim
                    b = {"address": x, "kind": "eoa" if is_plain(code2) else "contract", "via": "owner() of the holder"}
                    if b["kind"] == "eoa" and delegation(code2): b["delegated_to"] = delegation(code2)
                    if b["kind"] == "eoa" and key in ARBITRUM_STACK:   # an address without code on an Arbitrum-stack chain may be the alias of an L1 contract (Uniswap's governance Timelock owns the factory owner that way): read it on L1
                        l1_ = "0x%040x" % ((int(x, 16) - ALIAS_OFFSET) % (1 << 160)); rl = rpc_batch(L1_RPC, [("eth_getCode", [l1_, "latest"]), ("eth_call", [{"to": l1_, "data": SEL["getThreshold"]}, "latest"]), ("eth_call", [{"to": l1_, "data": SEL["getOwners"]}, "latest"]), ("eth_call", [{"to": l1_, "data": SEL["getMinDelay"]}, "latest"]), ("eth_call", [{"to": l1_, "data": SEL["delay"]}, "latest"])])
                        if rl[0] and len(rl[0]) > 2: code2, thr2, own2, dly2a, dly2b = rl; x = l1_; b = {"address": l1_, "kind": "contract", "via": "owner() of the holder, an Arbitrum L1 alias read on Ethereum L1", "alias_of": l1_}
                    if b["kind"] == "contract":
                        try:
                            tv2 = int(thr2, 16) if thr2 and thr2 != "0x" else 0; n2 = int(own2[2 + 64:2 + 128], 16) if own2 and len(own2) >= 130 else 0
                            if 0 < tv2 <= 50 and n2 >= tv2: b.update(kind="safe", threshold=tv2, owners=n2)
                        except ValueError: pass
                        if b["kind"] == "contract" and dly2a and dly2a != "0x":
                            try: b.update(kind="timelock", delay_seconds=int(dly2a, 16))
                            except ValueError: pass
                        if b["kind"] == "contract" and dly2b and dly2b != "0x" and len(dly2b) == 66:
                            try: b.update(kind="timelock", delay_seconds=int(dly2b, 16), timelock_family="compound")
                            except ValueError: pass
                    if b["kind"] == "eoa": b["address"] = short(x)
                    r_["behind"] = b; r_["path"] = r_["path"] + " -> owner() of the holder (%s)" % (b["kind"] + ((" %s-of-%s" % (b["threshold"], b["owners"])) if b["kind"] == "safe" else (" %ss" % b["delay_seconds"]) if b["kind"] == "timelock" else ""))
                    pb = (prev.get(key + ":" + str(r_["target"]).lower()) or {}).get("behind")   # compared here, after the read: what stands behind the holder moved
                    if pb and (short(str(pb.get("address") or "")).lower(), pb.get("kind"), pb.get("threshold"), pb.get("delay_seconds")) != (short(str(b.get("address") or "")).lower(), b.get("kind"), b.get("threshold"), b.get("delay_seconds")):
                        txt_ = "behind the holder, owner() changed since the previous run: %s %s -> %s %s" % (pb.get("kind"), pb.get("address"), b.get("kind"), b.get("address"))
                        if r_.get("changed"): r_["changed"] += "; " + txt_
                        else: r_["changed"] = txt_; changes.append(r_); r_["since"] = now_utc
                    tl2 = r_.get("timelockScore"); ms2 = r_.get("multisigScore"); s2 = r_.get("adminKeyScore")
                    if b["kind"] == "timelock" and (b.get("delay_seconds") or 0) >= 86400 and tl2 == 0: r_["disagree"] = (r_.get("disagree") + "; " if r_.get("disagree") else "") + "the timelock score says no delay (0), the holder's owner is a timelock of %d h" % (b["delay_seconds"] // 3600)
                    elif b["kind"] == "eoa" and s2 is not None and s2 >= 50: r_["disagree"] = (r_.get("disagree") + "; " if r_.get("disagree") else "") + "the score says admin power is not a bare key (%d), the holder's owner is a plain key %s" % (s2, b["address"])
                    elif b["kind"] == "safe" and (b.get("threshold") or 0) >= 3 and ms2 is not None and ms2 < 20: r_["disagree"] = (r_.get("disagree") + "; " if r_.get("disagree") else "") + "the multisig score says no real multisig (%d), the holder's owner is a Safe %d-of-%d" % (ms2, b["threshold"], b["owners"])
                    if r_.get("disagree") and r_ not in dis and not r_.get("acknowledged"):
                        note = ack.get(key + ":" + str(r_["target"]).lower())
                        if note: r_["acknowledged"] = str(note)[:300]; acked.append(r_)
                        else: dis.append(r_); agree -= 1
        # pass 4 (since 2026-10-10): what each Safe module and guard IS (a plain key, a Zodiac Delay with its cooldown, another Zodiac module, a contract) and who owns it
        todo = [(r_, m_, "module") for r_ in results if r_["chain"] == key and r_.get("modules") for m_ in r_["modules"]] + [(r_, r_["guard"], "guard") for r_ in results if r_["chain"] == key and r_.get("guard")]
        if todo:
            c4 = []
            for _, x_, _ in todo: c4 += [("eth_getCode", [x_, "latest"]), ("eth_call", [{"to": x_, "data": SEL["txCooldown"]}, "latest"]), ("eth_call", [{"to": x_, "data": SEL["avatar"]}, "latest"]), ("eth_call", [{"to": x_, "data": SEL["owner"]}, "latest"])]
            r4 = rpc_batch(url, c4); owners_ = [addr_of(r4[4 * j + 3]) for j in range(len(todo))]
            r4b = rpc_batch(url, [("eth_getCode", [o_ or "0x" + "0" * 40, "latest"]) for o_ in owners_])
            for j, (r_, x_, what) in enumerate(todo):
                d_ = {"address": x_, **classify_module(r4[4 * j], r4[4 * j + 1], r4[4 * j + 2], owners_[j], r4b[j] if owners_[j] else "0x", r_.get("holder"))}
                if what == "guard": r_["guard_detail"] = d_; continue
                r_.setdefault("modules_detail", []).append(d_)
                if d_["kind"] == "eoa":   # the one case that contradicts the multisig score outright
                    txt = "a plain key %s is enabled as a module of the admin Safe and can execute through it alone, whatever the %s-of-%s threshold says" % (short(x_), r_.get("threshold"), r_.get("owners"))
                    if r_.get("disagree") or r_.get("acknowledged"): r_["disagree"] = (r_.get("disagree") or "") + "; " + txt   # already listed (or reviewed: the note covers the old finding, this one shows in the text)
                    else:
                        r_["disagree"] = txt; agree -= 1; note = ack.get(key + ":" + str(r_["target"]).lower())
                        if note: r_["acknowledged"] = str(note)[:300]; acked.append(r_)
                        else: dis.append(r_)
    for f in sorted(glob.glob(os.path.join(a.scores, "*.json"))):
        d = json.load(open(f))
        if d.get("kind") != "solana": continue
        if d.get("oracle"):   # the oracle program itself: who can upgrade it (the EVM oracles watch their own roles in watch_run.py; this is the Solana counterpart)
            kind, holder, path, extra = solana_read(str(d["oracle"]), d.get("rpc")); time.sleep(0.25)
            rec = {"chain": "solana", "target": d["oracle"], "oracle_self": True, "cluster": d.get("rpc"), "adminKeyScore": None, "kind": kind or "unreadable", "holder": holder, "path": path, **extra}
            pr = prev.get("solana:" + str(d["oracle"]).lower())
            if kind and pr and pr.get("kind") not in (None, "unreadable", "native") and (not same_addr(pr.get("holder"), holder) or pr.get("kind") != kind):
                rec["changed"] = "ORACLE PROGRAM upgrade authority changed since the previous run: %s %s -> %s %s (via %s)" % (pr.get("kind"), pr.get("holder") or "", kind, holder or "", path); changes.append(rec)
            carry_since(rec, pr, bool(rec.get("changed"))); results.append(rec)
        # since 2026-10-10: a program-derived authority that is a Squads v4 vault is read through to its multisig (threshold, members, native time lock).
        # Every target is read first, then the vaults are resolved in ONE pass (the derivation over every v4 multisig costs about 90 s; once, not per holder).
        pre = {}
        for t in d.get("targets", []): pre[str(t["target"])] = solana_read(str(t["target"])); time.sleep(0.25)
        pda_holders = sorted({v[1] for v in pre.values() if v[0] == "pda" and v[1]})
        vaults = squads_vaults(pda_holders, os.path.join(os.path.dirname(a.out) or ".", "squads_vaults.json")) if pda_holders else {}
        for t in d.get("targets", []):
            rec = {"chain": "solana", "target": t["target"], "adminKeyScore": t.get("adminKeyScore"), "path": None, "holder": None}
            kind, holder, path, extra = pre[str(t["target"])]; rec.update(extra)
            if kind == "pda" and holder:
                ms = vaults.get(holder)
                if ms:
                    info = squads_multisig(ms); time.sleep(0.25)
                    if info:
                        kind = "squads"; path = path + " -> Squads v4 vault 0 of multisig %s" % ms; rec.update(info); rec["multisig"] = ms; rec["multisig_program"] = "Squads v4"
                        voters_ = info.get("voters") or info["owners"]   # the threshold counts votes: only members with the vote permission; the two faces follow the voting set
                        rec["keys_to_act"], rec["keys_lost_to_freeze"] = info["threshold"], max(0, voters_ - info["threshold"] + 1)
                        if voters_ < info["owners"]: rec["effective"] = "%d-of-%d members, %d can vote: effectively %d-of-%d" % (info["threshold"], info["owners"], voters_, info["threshold"], voters_)
                        if voters_ < info["threshold"]: rec["note"] = "fewer voters (%d) than the threshold (%d): this multisig cannot reach its threshold, nothing can be approved until members or the threshold change" % (voters_, info["threshold"])
            if kind is None:
                rec["kind"] = "unreadable"; rec["why"] = "holder not read (RPC)" if path == "rpc" else path; unread += 1; results.append(rec); continue
            if kind == "native":
                rec["kind"] = "native"; rec["why"] = path; native += 1; results.append(rec); continue
            rec["kind"], rec["holder"], rec["path"] = kind, holder, path; sc = t.get("adminKeyScore")
            pr = prev.get("solana:" + str(t["target"]).lower())
            if rec.get("deployed_slot"):   # the program's last deployment: dated once per slot (the date is carried from the previous run when the slot did not move)
                if pr and pr.get("deployed_slot") == rec["deployed_slot"] and pr.get("deployed_at"): rec["deployed_at"] = pr["deployed_at"]
                else:
                    bt = sol_rpc("getBlockTime", [rec["deployed_slot"]]); time.sleep(0.2); rec["deployed_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(bt)) if isinstance(bt, int) else None
                if pr and pr.get("deployed_slot") and pr["deployed_slot"] != rec["deployed_slot"]:
                    rec["upgraded"] = "program redeployed since the previous run: slot %d -> %d (%s); the score reads who may upgrade, this is an upgrade that happened" % (pr["deployed_slot"], rec["deployed_slot"], rec.get("deployed_at") or "date not read"); upgrades.append(rec)
            if pr and pr.get("kind") not in (None, "unreadable", "native") and (not same_addr(pr.get("holder"), holder) or pr.get("kind") != kind
                                                                                   or (pr.get("kind") == "squads" and kind == "squads" and (pr.get("threshold"), pr.get("owners"), pr.get("delay_seconds"), pr.get("config_authority"), pr.get("voters", rec.get("voters"))) != (rec.get("threshold"), rec.get("owners"), rec.get("delay_seconds"), rec.get("config_authority"), rec.get("voters")))):   # voters too: a member losing the vote narrows the multisig without touching threshold or count
                def sdesc(x): return "%s %s" % (x.get("kind"), x.get("holder") or "") + ((" %s-of-%s (%s voters), time lock %ss" % (x.get("threshold"), x.get("owners"), x.get("voters"), x.get("delay_seconds"))) if x.get("kind") == "squads" and x.get("threshold") else "")
                rec["changed"] = "admin read changed since the previous run: %s -> %s (via %s)" % (sdesc(pr), sdesc(rec), path); changes.append(rec)
            carry_since(rec, pr, bool(rec.get("changed")))
            ms_ = t.get("multisigScore"); tl_ = t.get("timelockScore"); rec["multisigScore"], rec["timelockScore"] = ms_, tl_
            if kind == "eoa" and sc is not None and sc >= 50: rec["disagree"] = "the score says admin power is not a bare key (%d), the upgrade authority is a plain key %s via %s" % (sc, short(holder), path)
            elif kind == "squads" and sc is not None and sc < 20: rec["disagree"] = "the score says one key does everything (%d), the upgrade authority is a %s via %s" % (sc, rec.get("multisig_program") or extra.get("multisig_program"), path)
            if kind == "squads" and rec.get("threshold"):   # the same two axes as a Safe: the threshold against the multisig score, the native time lock against the timelock score
                if rec["threshold"] == 1 and ms_ is not None and ms_ >= 55: rec["disagree"] = (rec.get("disagree") + "; " if rec.get("disagree") else "") + "the multisig score says at least a 3-of-5 (%d), the Squads multisig has a threshold of 1 (%d members)" % (ms_, rec["owners"])
                elif rec["threshold"] >= 3 and ms_ is not None and ms_ < 20: rec["disagree"] = (rec.get("disagree") + "; " if rec.get("disagree") else "") + "the multisig score says no real multisig (%d), the Squads multisig is a %d-of-%d" % (ms_, rec["threshold"], rec["owners"])
                if (rec.get("delay_seconds") or 0) >= 86400 and tl_ == 0: rec["disagree"] = (rec.get("disagree") + "; " if rec.get("disagree") else "") + "the timelock score says no delay (0), the Squads multisig enforces a native time lock of %d h" % (rec["delay_seconds"] // 3600)
                if rec.get("config_authority"): rec["note"] = "config_authority %s can change threshold, members and time lock without the members' approval" % rec["config_authority"]
            elif kind == "immutable" and sc is not None and sc < 50: rec["disagree"] = "the score says a key holds admin power (%d), the program cannot be upgraded (%s)" % (sc, path)
            if rec.get("disagree"):
                note = ack.get("solana:" + str(t["target"]).lower())
                if note: rec["acknowledged"] = str(note)[:300]; acked.append(rec)
                else: dis.append(rec)
            else: agree += 1
            results.append(rec)
    bdir = os.path.join(os.path.dirname(a.out) or ".", "badge"); slug_of = {}
    for f in glob.glob(os.path.join(a.scores, "*.json")):
        try: slug_of[chain_key(os.path.basename(f)[:-5]) or ("solana" if json.load(open(f)).get("kind") == "solana" else None)] = os.path.basename(f)[:-5]
        except Exception: pass  # noqa: BLE001
    for r_ in results:   # a shields.io endpoint badge per target: what the independent read says, for a protocol that wants to show it
        sl = slug_of.get(r_["chain"]); k_ = r_.get("kind")
        if not sl or r_.get("oracle_self"): continue
        msg, col = ("disagrees" if r_.get("disagree") and not r_.get("acknowledged") else "reviewed" if r_.get("acknowledged") else "agrees" if k_ not in ("unreadable", "native") else "not readable"), ("orange" if r_.get("disagree") and not r_.get("acknowledged") else "brightgreen" if k_ not in ("unreadable", "native") else "lightgrey")
        if k_ == "safe" and r_.get("nested"): msg += ", %s-of-%s over %s" % (r_.get("threshold"), r_.get("owners"), " + ".join(d_["kind"] for d_ in r_.get("owners_detail", [])))
        elif k_ == "safe": msg += ", Safe %s-of-%s" % (r_.get("threshold"), r_.get("owners"))
        elif k_ == "timelock": msg += ", timelock %dh" % ((r_.get("delay_seconds") or 0) // 3600)
        elif k_ in ("eoa",): msg += ", plain key"
        elif k_ == "pda": msg += ", program-derived"
        elif k_ == "squads": msg += ", Squads"
        elif k_ == "immutable": msg += ", immutable"
        os.makedirs(os.path.join(bdir, sl), exist_ok=True)
        bp = os.path.join(bdir, sl, str(r_["target"]) + "-so.json"); body = json.dumps({"schemaVersion": 1, "label": "independent read", "message": msg, "color": col}, indent=1)
        if not os.path.exists(bp) or open(bp).read() != body: open(bp + ".tmp", "w").write(body); os.replace(bp + ".tmp", bp)
    def posture_line(r_):
        """One line, the reader's own view of a contract, from its fields alone: admin, delay, code, in flight. Nothing new is read."""
        k = r_.get("kind")
        if k in ("unreadable", "native") or r_.get("oracle_self"): return None
        eff = r_.get("behind") or {} if k == "contract" else {}
        kk = eff.get("kind") or k
        ok = r_.get("owners_kinds") or {}; comp = ", ".join("%d %s" % (v, {"eoa": "plain key" if v == 1 else "plain keys", "safe": "Safe" if v == 1 else "Safes", "timelock": "timelock" if v == 1 else "timelocks", "contract": "contract" if v == 1 else "contracts", "unread": "not read"}.get(kx, kx)) for kx, v in sorted(ok.items(), key=lambda kv: -kv[1]) if v)
        if kk == "eoa": admin = "a plain key" + (" (EIP-7702: its account runs the code of %s)" % short((eff or r_).get("delegated_to")) if (eff or r_).get("delegated_to") else "") + (" behind a bare contract" if eff else "") + ((", %d transactions sent" % r_["holder_tx_count"]) if r_.get("holder_tx_count") is not None else "")
        elif kk == "safe": th, ow = (eff.get("threshold"), eff.get("owners")) if eff else (r_.get("threshold"), r_.get("owners")); admin = "Safe %s-of-%s" % (th, ow) + ((" of %s" % comp) if comp and not eff else "") + ((" (+%d module%s)" % (len(r_["modules"]), "s" if len(r_["modules"]) > 1 else "")) if r_.get("modules") else "") + (" behind a bare contract" if eff else "")
        elif kk == "squads": admin = "Squads %s-of-%s" % (r_.get("threshold"), r_.get("owners")) + ((", %d can vote" % r_["voters"]) if r_.get("voters") is not None and r_.get("voters") != r_.get("owners") else "") + ((" of %s" % comp) if comp else "")
        elif kk == "timelock": admin = "a timelock" + (" behind a bare contract" if eff else "")
        elif kk == "pda": admin = "a program-derived address (not a Squads v4 vault)"
        elif kk == "immutable": admin = "nobody: the program cannot be upgraded"
        else: admin = "a contract the reader cannot classify"
        delays = []
        d_ = (eff.get("delay_seconds") if eff else None) or r_.get("delay_seconds")
        if kk == "timelock" and d_: delays.append("%d h on the timelock" % (d_ // 3600))
        if kk == "squads" and r_.get("delay_seconds"): delays.append("%d h Squads time lock" % (r_["delay_seconds"] // 3600))
        if r_.get("self_delay_seconds"): delays.append("%d h the contract enforces itself" % (r_["self_delay_seconds"] // 3600))
        for m in r_.get("modules_detail") or []:
            if m.get("kind") == "zodiac-delay" and m.get("cooldown_seconds"): delays.append("%d h Zodiac delay (for module-routed calls)" % (m["cooldown_seconds"] // 3600))
        if ok.get("timelock"): delays.append("a timelock among the signers")
        delay = "; ".join(delays) if delays else ("none" if kk in ("eoa", "safe", "squads", "timelock") else "unknown")
        flight = []
        if r_.get("pending_admin"): flight.append("admin transfer designated, not accepted")
        if r_.get("upgraded"): flight.append("upgrade executed since the previous run")
        if r_.get("changed"): flight.append("admin read changed since the previous run")
        if r_.get("config_authority"): flight.append("a config authority can change the multisig alone")
        return "admin: %s; delay: %s%s" % (admin, delay, ("; in flight: " + ", ".join(flight)) if flight else "")
    for r_ in results:
        p_ = posture_line(r_)
        if p_: r_["posture"] = p_
    for r_ in results:   # plain keys leave shortened, whatever the index says; contracts stay whole
        if r_.get("kind") in ("eoa", "unreadable") and r_.get("holder"): r_["holder"] = short(r_["holder"])   # a holder whose code could not be read may be a plain key: shortened too (fail closed)
        for d_ in (r_.get("modules_detail") or []) + ([r_["guard_detail"]] if r_.get("guard_detail") else []):   # a module or guard that is a plain key, and a plain key that owns one, leave shortened too
            if d_.get("kind") == "eoa" and d_.get("address"):
                r_["modules"] = [short(m) if same_addr(m, d_["address"]) else m for m in (r_.get("modules") or [])]
                if r_.get("guard") and same_addr(r_["guard"], d_["address"]): r_["guard"] = short(r_["guard"])
                d_["address"] = short(d_["address"])
            if d_.get("owner_kind") == "eoa" and d_.get("owner"): d_["owner"] = short(d_["owner"])

        if r_.get("changed"): r_["changed"] = r_["changed"]   # already built from short forms
    # who else does this admin govern: the same holder (a Safe, a timelock, a key, a PDA) across the tracked contracts, from this
    # reader's own reads, with no private index. Keys are already shortened: a cluster on a shortened key is still a cluster.
    by_holder = {}
    for r_ in results:
        if r_.get("holder") and r_.get("kind") not in ("unreadable", "native") and not r_.get("oracle_self"): by_holder.setdefault(str(r_["holder"]).lower(), []).append(r_)
    try: tvl = json.load(open(a.tvl)).get("matched", {})
    except Exception: tvl = {}  # noqa: BLE001
    def money(rs):
        """TVL behind a cluster without double counting: a per-chain figure counts per target; a 'total' (all chains) or 'chain-total' figure counts once per protocol slug (the 08/10 lesson)."""
        total, seen = 0.0, set()
        for x in rs:
            m = tvl.get(x["chain"] + ":" + str(x["target"]).lower())
            if not m or not m.get("tvl"): continue
            # several targets of one protocol carry that protocol's whole figure: count a protocol once per chain ("chain" scope), once in all ("total", "chain-total")
            k = (m.get("slug"),) if m.get("scope") in ("total", "chain-total") else (m.get("slug"), x["chain"])
            if k in seen: continue
            seen.add(k); total += float(m["tvl"])
        return total
    clusters = []
    for h, rs in by_holder.items():
        if len(rs) < 2: continue
        members = [{"chain": x["chain"], "target": x["target"]} for x in rs]; chains = sorted({x["chain"] for x in rs})
        clusters.append({"holder": rs[0]["holder"], "kind": rs[0]["kind"], "targets": len(rs), "chains": chains, "members": members, "tvl_usd": money(rs)})
        for x in rs: x["shares_admin_with"] = [m for m in members if m["target"] != x["target"] or m["chain"] != x["chain"]]
    clusters.sort(key=lambda c: (-c["tvl_usd"], -c["targets"]))
    for c in clusters:
        for x in by_holder[str(c["holder"]).lower()]: x["cluster_tvl_usd"] = c["tvl_usd"]
    # concentration: the share of all tracked money (a protocol counted once per chain) that sits under the five heaviest holders
    tracked_total = money([{"chain": r_["chain"], "target": r_["target"]} for r_ in results if not r_.get("oracle_self")])
    top5 = sum(c["tvl_usd"] for c in clusters[:5])
    concentration = {"tracked_tvl_usd": tracked_total, "top5_holders_tvl_usd": top5, "top5_share": (top5 / tracked_total) if tracked_total else None, "holders_with_2_plus": len(clusters)}
    # a group that grew: the same holder now also governs a contract it did not govern at the previous run (its blast radius widened)
    prev_members = {}
    for r_ in prev.values():
        if r_.get("holder") and r_.get("kind") not in ("unreadable", "native"): prev_members.setdefault(str(r_["holder"]).lower(), set()).add(r_["chain"] + ":" + str(r_["target"]).lower())
    cluster_changes = []
    for c in clusters:
        h = str(c["holder"]).lower(); was = prev_members.get(h)
        if was is None: continue   # a holder first seen this run is a change on its own targets, reported there
        new = [m for m in c["members"] if (m["chain"] + ":" + str(m["target"]).lower()) not in was]
        if new: cluster_changes.append({"holder": c["holder"], "kind": c["kind"], "now_governs": c["targets"], "tvl_usd": c["tvl_usd"], "new_members": new, "text": "%s %s now also governs %s: %d tracked contract(s) in all, about $%.0fM behind them" % (c["kind"], c["holder"], ", ".join(m["chain"] + ":" + str(m["target"])[:10] for m in new), c["targets"], c["tvl_usd"] / 1e6)})
    for x in changes:   # the blast radius travels with an admin change
        ct = x.get("cluster_tvl_usd"); n = len(x.get("shares_admin_with") or [])
        if n: x["changed"] += " (this holder governs %d tracked contract(s) in all%s)" % (n + 1, (", about $%.0fM behind them" % (ct / 1e6)) if ct else "")
    for c in clusters:   # the same for a group whose holder is a plain key, and for the text that travels with the alarm
        if c.get("kind") == "eoa" and c.get("holder"): c["holder"] = short(c["holder"])
    for x in cluster_changes:
        if x.get("kind") == "eoa" and x.get("holder"): x["text"] = x["text"].replace(x["holder"], short(x["holder"])); x["holder"] = short(x["holder"])
    comp = {}; comp_safes = 0; all_keys = 0   # the signer sets of every admin Safe, in kinds: how many of the tracked multisigs are multisigs of plain keys
    for r_ in results:
        if r_.get("owners_kinds") and not r_.get("oracle_self"):
            comp_safes += 1; all_keys += 1 if {k_ for k_, v_ in r_["owners_kinds"].items() if v_} == {"eoa"} else 0   # kinds with a count: a Squads record lists pda: 0
            for k_, v_ in r_["owners_kinds"].items(): comp[k_] = comp.get(k_, 0) + v_
    frozen_by_one = sum(1 for r_ in results if r_.get("kind") in ("safe", "squads") and not r_.get("oracle_self") and r_.get("keys_lost_to_freeze") == 1)
    signer_composition = {"safes": comp_safes, "signers": sum(comp.values()), "by_kind": comp, "safes_of_plain_keys_only": all_keys, "safes_frozen_by_one_lost_key": frozen_by_one} if comp_safes else None
    blocks = {}
    for r_ in results:
        if r_.get("block_end") and not r_.get("oracle_self"): blocks[r_["chain"]] = {"start": r_.get("block_start"), "end": r_["block_end"]}
    # the attacker's question (since 2026-10-10): how many keys move this contract, how long the users have to react, how much money one key exposes
    exposure = []
    try: tvl_scope = {str(k).lower(): v for k, v in (json.load(open(os.path.join(os.path.dirname(a.ack) or ".", "tvl_scope.json"))).get("targets") or {}).items()}   # data/tvl_scope.json: retired or peripheral contracts whose protocol TVL does not sit behind them
    except Exception: tvl_scope = {}  # noqa: BLE001
    try: held_map = json.load(open(a.held)).get("by_target", {})   # watch/held_assets.json: ERC-4626 totalAssets() priced, the contract's own money (since 2026-10-10)
    except Exception: held_map = {}  # noqa: BLE001
    for r_ in results:
        if r_.get("oracle_self") or r_.get("kind") in ("unreadable", "native", "immutable", "pda"): continue
        sc_ = (tvl_scope.get(r_["chain"] + ":" + str(r_["target"]).lower()) or {}).get("scope")
        if sc_ in ("retired", "peripheral"): r_["tvl_scope"] = sc_
        eff = r_.get("behind") if (r_.get("kind") == "contract" and r_.get("behind")) else None; k = (eff or r_).get("kind")
        import re as _re2
        if k == "eoa": keys = 1
        elif k == "safe" and r_.get("nested") and not eff:   # a 1-of-N routing Safe whose owners are real multisigs or timelocks: the cheapest route is the owner Safe with the lowest threshold
            ths = [int(m.group(1)) for d_ in (r_.get("owners_detail") or []) for m in [_re2.match(r"safe (\d+)-of-", str(d_.get("kind")))] if m]
            keys = min(ths) if ths else None   # only timelocks among the owners: the keys sit behind them, not read here
        elif k in ("safe", "squads"): keys = (eff or r_).get("threshold")
        elif k == "timelock": keys = None   # the keys sit behind the timelock's own admin, not read here
        else: keys = None
        delays = [x for x in ((eff or {}).get("delay_seconds") if eff else (r_.get("delay_seconds") if k == "timelock" else None), r_.get("delay_seconds") if r_.get("kind") == "squads" else None, r_.get("self_delay_seconds")) if x]
        for m_ in r_.get("modules_detail") or []:
            if m_.get("kind") == "zodiac-delay" and m_.get("cooldown_seconds"): pass   # a module-routed delay does not bind the owners: not counted
        hours = (min(delays) // 3600) if delays else (0 if keys is not None else None)   # 0 = "no delay" is a finding about a holder that was read; a holder not read (no key count) has no hours at all, never a 0 (conformance review, 12/10)
        m_ = tvl.get(r_["chain"] + ":" + str(r_["target"]).lower()) if isinstance(tvl, dict) else None; money = float(m_.get("tvl") or 0) if (m_ and not r_.get("tvl_scope")) else None   # a retired or peripheral contract carries no money here
        h_ = held_map.get(r_["chain"] + ":" + str(r_["target"]).lower()) or {}; src = "protocol_tvl" if money else None
        if h_.get("held_usd") is not None: money, src = float(h_["held_usd"]), "contract"   # the contract's own balance beats the protocol figure: 10 vaults with no DefiLlama match carried $0 before (10/10)
        rec_ = {"keys_to_move": keys, "react_hours": hours, "tvl_usd": money, "money_per_key_usd": (money / keys) if (money and keys) else None, "money_source": src, "held_symbol": h_.get("symbol"), "held_amount": h_.get("amount")}
        r_["exposure"] = rec_
        if keys and money: exposure.append({"chain": r_["chain"], "target": r_["target"], "keys_to_move": keys, "react_hours": hours, "tvl_usd": round(money), "money_per_key_usd": round(money / keys), "money_source": src})
    exposure.sort(key=lambda x: (-x["money_per_key_usd"], x["react_hours"]))
    out = {"generated_utc": now_utc, "blocks": blocks, "signer_composition": signer_composition, "exposure": exposure[:40], "checked": sum(1 for r_ in results if not r_.get("oracle_self")), "clusters": clusters, "concentration": concentration, "cluster_changes": cluster_changes, "agree": agree, "disagree": len(dis), "unreadable": unread, "native": native, "acknowledged": len(acked), "rpc_calls_unanswered": RPC_ERRORS,
           "disagreements": dis, "acknowledged_disagreements": acked, "changed": changes, "upgrades": upgrades, "previous_utc": prev_utc, "results": results,
           "what": "an independent reader (EVM: EIP-1967 admin slot then ProxyAdmin owner(), else owner(), else admin(); holder classified as EOA / Safe / timelock / contract. Solana: the program upgrade authority through ProgramData, classified as plain key / Squads multisig / immutable / program-owned account) against the published adminKeyScore; a disagreement is a finding to review, an unreadable target is not an agreement, a native target (no code at the address: a derived identifier for a non-EVM entity) is outside this reader's reach"}
    tmp = a.out + ".tmp"; json.dump(out, open(tmp, "w"), indent=1); os.replace(tmp, a.out)
    # every finding of this reader enters the same hash-chained log as the watch's own moves (same link rule as watch_run.py)
    if a.events and (changes or cluster_changes or upgrades):
        import hashlib as _hl
        last_line, seq = "", 0
        if os.path.exists(a.events):
            for l in open(a.events):
                if l.strip(): last_line, seq = l.rstrip("\n"), seq + 1
        prev_h = _hl.sha256(last_line.encode()).hexdigest() if last_line else ""
        if last_line and not open(a.events, "rb").read().endswith(b"\n"): open(a.events, "a").write("\n")
        import re as _re
        def scrub(t):   # a chained log is never rewritten (the redaction step would break every link after it): holders leave already shortened, whatever they are; the tracked target itself stays whole in its own field
            return _re.sub(r"0x[0-9a-fA-F]{40}|[1-9A-HJ-NP-Za-km-z]{32,44}", lambda m: short(m.group(0)), str(t))
        with open(a.events, "a") as f:
            for e in ([{"run_utc": now_utc, "kind": "admin_change", "oracle": x["chain"], "target": x["target"], "label": x.get("label"), "text": scrub(x["changed"])} for x in changes]
                      + [{"run_utc": now_utc, "kind": "admin_grew", "oracle": None, "target": None, "holder": short(x["holder"]), "text": scrub(x["text"])} for x in cluster_changes]
                      + [{"run_utc": now_utc, "kind": "upgraded", "oracle": x["chain"], "target": x["target"], "label": None, "impl": x.get("impl") or ("slot %s" % x.get("deployed_slot") if x.get("deployed_slot") else None), "text": "upgrade executed on %s %s: %s" % (x["chain"], x["target"][:10], scrub(x["upgraded"]))} for x in upgrades]):
                seq += 1; line = json.dumps({**e, "seq": seq, "prev": prev_h}); f.write(line + "\n"); prev_h = _hl.sha256(line.encode()).hexdigest()
    if dis or changes or cluster_changes or upgrades:
        open(a.md, "w").write("## Second opinion, %s\n\n" % out["generated_utc"]
                              + (("### %d upgrade(s) executed since the previous run (%s)\n\n" % (len(upgrades), prev_utc)) + "".join("- **%s** on %s: %s\n" % (x["target"], x["chain"], x["upgraded"]) for x in upgrades) + "\nThe code behind a tracked proxy changed: read what the new implementation does before trusting the score (the private pipeline's implementation check names the selectors added and dropped).\n\n" if upgrades else "")
                              + (("### %d admin(s) now govern more tracked contracts than at the previous run\n\n" % len(cluster_changes)) + "".join("- %s\n" % x["text"] for x in cluster_changes) + "\n" if cluster_changes else "")
                              + (("### %d admin change(s) since the previous run (%s)\n\n" % (len(changes), prev_utc)) + "".join("- **%s** on %s: %s\n" % (x["target"], x["chain"], x["changed"]) for x in changes) + "\nThe live admin of a tracked contract moved between two watch runs: the published score may be out of date before the next push. Read the case now.\n\n" if changes else "")
                              + (("### %d disagreement(s) with the published score\n\n" % len(dis)) + "".join("- **%s** on %s: %s\n" % (x["target"], x["chain"], x["disagree"]) for x in dis) + "\nAn independent reader (scripts/second_opinion.py); review the case, the scorer may look at a different role than the proxy admin.\n" if dis else ""))
    elif os.path.exists(a.md): os.remove(a.md)
    if ERRORS_SEEN: print("  rpc errors not taken as answers: " + "; ".join("%s x%d" % (k, v) for k, v in sorted(ERRORS_SEEN.items(), key=lambda kv: -kv[1])[:5]))
    if concentration.get("top5_share") is not None: print("  concentration: the five heaviest holders sit over %.0f%% of the tracked money ($%.0fM of $%.0fM)" % (100 * concentration["top5_share"], top5 / 1e6, tracked_total / 1e6))
    for x in cluster_changes: print("  GREW " + x["text"])
    if clusters: print("  shared admins: %d holder(s) govern 2+ tracked contracts; the heaviest, a %s, sits over %d contract(s) on %s holding about $%.0fM" % (len(clusters), clusters[0]["kind"], clusters[0]["targets"], ", ".join(clusters[0]["chains"]), clusters[0]["tvl_usd"] / 1e6))
    print("second opinion: %d checked, %d agree, %d disagree, %d reviewed, %d unreadable, %d native (no code at the address), %d admin change(s), %d upgrade(s) executed since the previous run (%d RPC call(s) unanswered after retries)" % (out["checked"], agree, len(dis), len(acked), unread, native, len(changes), len(upgrades), RPC_ERRORS))
    for x in changes: print("  CHANGED " + x["chain"] + " " + x["target"] + ": " + x["changed"])
    for x in dis: print("  DISAGREE " + x["chain"] + " " + x["target"] + ": " + x["disagree"])


if __name__ == "__main__":
    main()
