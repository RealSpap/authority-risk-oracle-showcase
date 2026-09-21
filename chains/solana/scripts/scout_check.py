#!/usr/bin/env python3
"""Scouting 2026-09-17 run 2: deterministic read-only claim checker. No keys, no signing, JSON-RPC reads only.
Used by data/scouted_targets_2026-09-17-run2.md. Checker (exit 0 + prints OK only if every assertion holds on BOTH RPCs;
historical transactions use solanavibestation as the second RPC because publicnode does not serve old transactions).
Subcommands:
  authority <program> <expected_upgrade_authority>
  v4 <multisig> <vault_index> <expected_vault> <threshold> <members> <voters> <time_lock_s>   (also asserts config_authority default)
  v4controlled <multisig> <vault_index> <expected_vault> <threshold> <members> <time_lock_s> <config_authority>
  v3 <ms> <authority_index> <expected_authority> <threshold> <n_keys>
  coral <ms> <program> <expected_signer> <threshold> <n_owners>
  oncurve <pubkey> <true|false>
  event <signature> <programdata> <type> <old_authority> <new_authority_or_-> <wrapper_program_or_-> <wrapper_first_account_or_->  (- = top-level, no multisig wrapper)
  gov <governance> <expected_native_treasury> <hold_up_s> <voting_base_s> <cool_off_s>
  infinity-admin <expected_admin> <expected_lp_mint>
  jitopool <expected_manager> <expected_staker_owner> <expected_mint_authority>
  tvl <defillama_slug>:<min_usd> ...
  shared <pubkey> <kind:ms> <kind:ms>   (kind in v4,v3,coral)
"""
import sys, json, base64
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sol_read as s
RPCS = ["https://api.mainnet-beta.solana.com", "https://solana-rpc.publicnode.com"]
V3 = "SMPLecH534NA9acpos4G6x7uf3LWbCAwZQE9e8ZekMu"; DEF = "11111111111111111111111111111111"
a = sys.argv[1:]; cmd = a[0]
if cmd == "tvl":
    # tvl <defillama_slug>:<min_usd> ...  (Solana chain TVL from api.llama.fi, retried; lower bounds only)
    import subprocess, time
    bad = []
    for arg in a[1:]:
        slug, lo = arg.split(":"); v = None
        for _ in range(5):
            try:
                out = subprocess.run(["curl", "-s", "-m", "120", "https://api.llama.fi/protocol/" + slug], capture_output=True, text=True).stdout
                v = json.loads(out)["currentChainTvls"].get("Solana", 0); break
            except Exception:
                time.sleep(5)
        if v is None or v < float(lo): bad.append((slug, v))
    assert not bad, bad
    print("OK"); sys.exit(0)
def members(u, kind, ms):
    if kind == "v4": return [m["key"] for m in s.read_squads(u, ms)["member_list"]]
    if kind == "v3": return s.read_squadsv3(u, ms)["keys"]
    d = base64.b64decode(s.acct(u, ms)["data"][0]); n = int.from_bytes(d[8:12], "little")
    return [s.b58(d[12+32*i:44+32*i]) for i in range(n)]
if cmd == "event":
    RPCS = ["https://api.mainnet-beta.solana.com", "https://public.rpc.solanavibestation.com"]
for u in RPCS:
    if cmd == "authority":
        assert s.read_program(u, a[1])["upgrade_authority"] == a[2], u
    elif cmd in ("v4", "v4controlled"):
        assert s.read_squads_vault(a[1], int(a[2]))["vault"] == a[3]
        m = s.read_squads(u, a[1]); voters = sum(1 for x in m["member_list"] if x["mask"] & 2)
        if cmd == "v4":
            assert (m["threshold"], m["members"], voters, m["time_lock_s"], m["config_authority"]) == (int(a[4]), int(a[5]), int(a[6]), int(a[7]), DEF), (u, m["threshold"], m["members"], voters, m["time_lock_s"], m["config_authority"])
        else:
            assert (m["threshold"], m["members"], m["time_lock_s"], m["config_authority"]) == (int(a[4]), int(a[5]), int(a[6]), a[7]), u
    elif cmd == "v3":
        m = s.read_squadsv3(u, a[1], a[2])
        assert (m["owner"], m["authority_%s" % a[2]], m["threshold"], m["n_keys"]) == (V3, a[3], int(a[4]), int(a[5])), (u, m["threshold"], m["n_keys"])
    elif cmd == "coral":
        acc = s.acct(u, a[1]); d = base64.b64decode(acc["data"][0]); n = int.from_bytes(d[8:12], "little"); o = 12 + 32*n
        thr = int.from_bytes(d[o:o+8], "little"); nonce = d[o+8]
        k, bump = s.find_program_address([s.b58dec(a[1])], a[2])
        assert (acc["owner"], k, bump, thr, n) == (a[2], a[3], nonce, int(a[4]), int(a[5])), (u, k, bump, nonce, thr, n)
    elif cmd == "oncurve":
        assert s.on_curve(a[1]) == (a[2] == "true"); break
    elif cmd == "event":
        tx = s.rpc(u, "getTransaction", [a[1], {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}])
        assert tx["meta"]["err"] is None
        top = tx["transaction"]["message"]["instructions"]; ok = False
        groups = [{"index": None, "instructions": top}] if a[6] == "-" else []
        for g in groups + (tx["meta"].get("innerInstructions") or []):
            for ix in g["instructions"]:
                p = ix.get("parsed") if isinstance(ix.get("parsed"), dict) else None
                if ix.get("programId") != "BPFLoaderUpgradeab1e11111111111111111111111" or not p: continue
                i = p["info"]; acct_ = i.get("programDataAccount") or i.get("account")
                if p["type"] == a[3] and acct_ == a[2] and i.get("authority") == a[4] and (i.get("newAuthority") or "-") == a[5] \
                   and ((a[6] == "-" and g["index"] is None) or (g["index"] is not None and top[g["index"]].get("programId") == a[6] and top[g["index"]]["accounts"][0] == a[7])):
                    ok = True
        assert ok, u
    elif cmd == "gov":
        acc = s.acct(u, a[1]); d = base64.b64decode(acc["data"][0]); o = 69
        def vt():
            global o
            t = d[o]; o += 1 if t == 2 else 2
        vt(); o += 8; hold = int.from_bytes(d[o:o+4], "little"); o += 4; vb = int.from_bytes(d[o:o+4], "little"); o += 4; o += 1
        vt(); vt(); o += 8; o += 1; vt(); cool = int.from_bytes(d[o:o+4], "little")
        nt = s.find_program_address([b"native-treasury", s.b58dec(a[1])], acc["owner"])[0]
        assert (nt, hold, vb, cool) == (a[2], int(a[3]), int(a[4]), int(a[5])), (u, nt, hold, vb, cool)
    elif cmd == "infinity-admin":
        st = s.find_program_address([b"state"], "5ocnV1qiCgaQR8Jb8xWnVbApfaygJ8tNoZfgPwsgx9kx")[0]
        d = base64.b64decode(s.acct(u, st)["data"][0])
        assert (s.b58(d[16:48]), s.b58(d[144:176])) == (a[1], a[2]), u
    elif cmd == "jitopool":
        d = base64.b64decode(s.acct(u, "Jito4APyf642JPZPx3hGc6WWJ8zPKtRbRs4P815Awbb")["data"][0])
        wa = s.find_program_address([s.b58dec("Jito4APyf642JPZPx3hGc6WWJ8zPKtRbRs4P815Awbb"), b"withdraw"], "SPoo1Ku8WFXoNDMHPsrGSTSG1Y47rzgn41SLUNakuHy")[0]
        mint = s.b58(d[162:194])
        assert (s.b58(d[1:33]), s.read_keytype(u, s.b58(d[33:65]))["owner"], s.read_mint(u, mint)["mintAuthority"], wa, mint) == (a[1], a[2], a[3], a[3], "J1toso1uCk3RLmjorhTtrVwY9HJ7X8V9yYac6Y7kGCPn"), u
    elif cmd == "shared":
        k1, m1 = a[2].split(":"); k2, m2 = a[3].split(":")
        assert a[1] in members(u, k1, m1) and a[1] in members(u, k2, m2) and s.on_curve(a[1]), u
    else:
        raise SystemExit("unknown")
print("OK")
