#!/usr/bin/env python3
"""Read-only Solana RPC helper for authority discovery (no signing, no keys).
Usage:
  sol_read.py genesis <rpc>
  sol_read.py program <rpc> <program_id>    -> owner loader, executable, programdata, upgrade authority
  sol_read.py mint <rpc> <mint>             -> mint/freeze authority (jsonParsed)
  sol_read.py keytype <rpc> <pubkey>       -> on/off ed25519 curve + owner
  sol_read.py splmultisig <rpc> <acct>     -> SPL Token native multisig m/n/signers
  sol_read.py pda-programdata - <program_id> -> offline derivation of ProgramData PDA
  sol_read.py squads-vault - <multisig> [i] -> offline derivation of Squads v4 vault PDA
  sol_read.py pyth-config <rpc> <receiver_program> -> Pyth receiver Config (governance authority, wormhole, min sigs)
  sol_read.py squadsv3 <rpc> <ms> [idx]  -> Squads v3 Ms threshold/keys (+ derived authority PDA)
  sol_read.py programs-by-authority <rpc> <authority> -> ProgramData accounts sharing one upgrade authority (cross-exposure)
  sol_read.py squads <rpc> <multisig_pda>   -> threshold, time_lock, config_authority, members
  sol_read.py realm <rpc> <realm_pda>       -> RealmV2: community_mint, authority, council_mint, name
  sol_read.py governance <rpc> <governance_pda> -> GovernanceV2 (legacy/pre-v3 layout, e.g. Solend's own deployment): realm, governed_account, vote threshold, hold-up/voting time
  sol_read.py governance-v2 <rpc> <governance_pda> -> GovernanceV2 (modern layout, e.g. Drift/most Realms deployments): realm, governance_seed, full vote-threshold/veto/cooloff config -- NOT interchangeable with `governance` above, same discriminant, different bytes
  sol_read.py switchboard-pull-feed <rpc> <feed_pda> -> Switchboard On-Demand PullFeedAccountData: authority (feed_hash update key), queue, feed_hash
  sol_read.py switchboard-queue <rpc> <queue_pda>    -> Switchboard On-Demand QueueAccountData: authority (which oracles may serve this queue)

REFACTORED 2026-09-17 (closed a reuse gap): every decoder below used to live
inline in main()'s if/elif chain, and main() ran unconditionally at module
scope (no `if __name__ == "__main__":` guard) -- so nothing else in this
project could `import sol_read` without main() immediately crashing on
sys.argv. Extracted one function per account type, same byte offsets and
same decode logic as the original (verified identical output against every
reproduction command in ../METHODOLOGY.md before and after this change, see
data/sol_read_refactor_check_2026-09-17.md), so `chains/solana/scorers.py`
can import these directly instead of re-deriving or duplicating the byte
layouts a second time -- the same "one canonical copy" discipline already
applied this pass to `_retrying()`/`safe_score()` on the EVM side.
"""
import sys, json, base64, hashlib

B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def b58(b):
    n = int.from_bytes(b, "big"); s = ""
    while n: n, r = divmod(n, 58); s = B58[r] + s
    return "1" * (len(b) - len(b.lstrip(b"\0"))) + s


class SolRpcError(Exception):
    """Real RPC failure (a JSON-RPC error response, or retries exhausted) --
    an ordinary Exception subclass, not SystemExit. FIXED 2026-09-17 (closed
    a bug hunt finding): this used to raise SystemExit, which subclasses
    BaseException, not Exception -- every caller's `except Exception`
    per-target isolation (e.g. chains/solana/scorers.py's score_all()) could
    not catch it, so one transient/invalid RPC response on any single read
    crashed the entire score_all() call and discarded every already-computed
    result for the run, not just the offending target."""


def rpc(url, method, params=None, tries=4):
    import subprocess, time
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params or []})
    for i in range(tries):
        out = subprocess.run(["curl", "-s", "-m", "60", url, "-X", "POST", "-H", "Content-Type: application/json", "-d", body],
                             capture_output=True, text=True).stdout
        try:
            r = json.loads(out)
        except ValueError:
            time.sleep(2 * (i + 1)); continue
        if "error" in r:
            if r["error"].get("code") == 429: time.sleep(3 * (i + 1)); continue
            raise SolRpcError(json.dumps(r["error"]))
        return r["result"]
    raise SolRpcError("rpc failed after retries: " + method)


def acct(url, pk, enc="base64", length=None):
    cfg = {"encoding": enc}
    if length is not None: cfg["dataSlice"] = {"offset": 0, "length": length}
    return rpc(url, "getAccountInfo", [pk, cfg])["value"]


P = 2**255 - 19
D = (-121665 * pow(121666, P - 2, P)) % P


def b58dec(s):
    n = 0
    for c in s: n = n * 58 + B58.index(c)
    b = n.to_bytes(32, "big")
    return b


def on_curve(pk):
    """True if the 32-byte key decompresses to an ed25519 point (can have a private key).
    False = off-curve = PDA, only a program can sign for it via invoke_signed."""
    b = b58dec(pk); y = int.from_bytes(b, "little") & ((1 << 255) - 1); sign = b[31] >> 7
    if y >= P: return False
    y2 = y * y % P; u = (y2 - 1) % P; v = (D * y2 + 1) % P
    x2 = u * pow(v, P - 2, P) % P
    x = pow(x2, (P + 3) // 8, P)
    if (x * x - x2) % P != 0:
        x = x * pow(2, (P - 1) // 4, P) % P
    if (x * x - x2) % P != 0: return False
    if x == 0 and sign == 1: return False
    return True


def find_program_address(seeds, program_id):
    """Pubkey::find_program_address: sha256(seeds || bump || program_id || "ProgramDerivedAddress"), first off-curve bump from 255 down."""
    for bump in range(255, -1, -1):
        h = hashlib.sha256(b"".join(seeds) + bytes([bump]) + b58dec(program_id) + b"ProgramDerivedAddress").digest()
        k = b58(h)
        if not on_curve(k): return k, bump
    raise ValueError("no bump")


def read_keytype(url, pk):
    a = acct(url, pk, length=0)
    return {"key": pk, "on_curve": on_curve(pk), "exists": a is not None,
            "owner": a and a["owner"], "executable": a and a["executable"]}


def read_pda_programdata(pk):
    return dict(zip(("programdata", "bump"), find_program_address([b58dec(pk)], "BPFLoaderUpgradeab1e11111111111111111111111")))


def read_squads_vault(pk, idx=0):
    k, b = find_program_address([b"multisig", b58dec(pk), b"vault", bytes([idx])], "SQDS4ep65T869zMMBKyuUq6aD6EgTu8psMjkvj52pCf")
    return {"multisig": pk, "vault_index": idx, "vault": k, "bump": b}


def read_pyth_config(url, receiver_program):
    # Config PDA seeds = [b"config"]
    cfg, _ = find_program_address([b"config"], receiver_program)
    d = base64.b64decode(acct(url, cfg)["data"][0]); o = 8
    gov = b58(d[o:o+32]); o += 32
    tgt = None
    if d[o] == 1: tgt = b58(d[o+1:o+33]); o += 33
    else: o += 1
    wh = b58(d[o:o+32]); o += 32
    n = int.from_bytes(d[o:o+4], "little"); o += 4
    srcs = []
    for _ in range(n):
        srcs.append({"chain": int.from_bytes(d[o:o+2], "little"), "emitter": b58(d[o+2:o+34])}); o += 34
    fee = int.from_bytes(d[o:o+8], "little"); o += 8
    return {"config": cfg, "governance_authority": gov, "target_governance_authority": tgt, "wormhole": wh,
            "valid_data_sources": srcs, "single_update_fee_lamports": fee, "minimum_signatures": d[o]}


SWITCHBOARD_ON_DEMAND_PROGRAM = "SBondMDrcV3K4kxZR1HNVT7osZxAHVHgYXL5Ze1oMUv"
SWITCHBOARD_ON_DEMAND_MAINNET_QUEUE = "A43DyUGA7s8eXPxqEjJY6EBu1KKbNgfxF8h17VAHn13w"
# Both constants confirmed 2026-09-19 against the OFFICIAL SDK source, NOT
# guessed/recalled from memory: switchboard-xyz/switchboard-sdk (a fork/mirror
# of switchboard-xyz/on-demand) `src/utils/index.ts`'s own
# `ON_DEMAND_MAINNET_PID`/`ON_DEMAND_MAINNET_QUEUE` exports. A first recalled
# guess for the program id was wrong in 4 characters (a plausible-looking but
# fabricated base58 string) -- caught only because it was checked against the
# primary source before being used, not trusted from memory.

_PULL_FEED_DISCRIMINATOR = bytes([196, 27, 108, 196, 10, 215, 219, 40])
_QUEUE_ACCOUNT_DISCRIMINATOR = bytes([217, 194, 55, 127, 184, 83, 138, 1])


def read_switchboard_pull_feed(url, pk):
    """Switchboard On-Demand `PullFeedAccountData` (the "classic PullFeed"
    layout; still the layout in live use by every consumer checked this
    pass -- see METHODOLOGY.md 3.7). Source: the OFFICIAL SDK's own Rust
    struct, `switchboard-xyz/switchboard-sdk`
    `solana/rust/switchboard-on-demand-client/src/accounts/pull_feed.rs`
    (mirrored byte-for-byte in `solana/rust/switchboard-on-demand/src/
    on_demand/accounts/pull_feed.rs`, cross-checked identical).

    Layout (bytemuck Pod, `#[repr(C)]`, preceded by an 8-byte Anchor-style
    discriminator that is NOT part of the Rust struct itself):
      [0:8]      discriminator (must equal `_PULL_FEED_DISCRIMINATOR`)
      [8:2056]   submissions: [OracleSubmission; 32] (32 * 64 bytes; each
                 OracleSubmission = oracle Pubkey(32) + slot u64(8) +
                 landed_at u64(8) + value i128(16), naturally 16-byte
                 aligned/padded already, no gaps)
      [2056:2088] authority: Pubkey -- can rewrite `feed_hash` (which job
                 schema/computation produces this feed's price) with NO
                 quorum and NO delay of its own.
      [2088:2120] queue: Pubkey -- which Switchboard queue's oracles must
                 sign an update for this feed to accept it.
      [2120:2152] feed_hash: [u8; 32] (SHA-256 of the job schema; not
                 decoded further here, disclosed as a note only).
    Fields past `feed_hash` (permissions, min_responses, name, the
    `CurrentResult` price itself, ...) are not read -- not needed for the
    authority classification and their offsets require accounting for
    compiler-inserted alignment padding this project has not verified."""
    a = acct(url, pk)
    d = base64.b64decode(a["data"][0])
    disc_ok = d[0:8] == _PULL_FEED_DISCRIMINATOR
    return {"feed": pk, "owner": a["owner"], "discriminator_ok": disc_ok,
            "authority": b58(d[2056:2088]), "queue": b58(d[2088:2120]),
            "feed_hash": d[2120:2152].hex()}


def read_switchboard_queue(url, pk):
    """Switchboard On-Demand `QueueAccountData`. Source: the same official
    SDK, `.../accounts/queue.rs` (both crate copies identical). `authority`
    is the FIRST field of the struct (struct offset 0, so raw account
    offset 8, right after the 8-byte discriminator) -- "the address of the
    authority which is permitted to add/remove allowed enclave measurements"
    per the struct's own doc comment, i.e. which oracle operators may
    participate on this queue at all, the Switchboard analogue of Pyth's
    `governance_authority` controlling `valid_data_sources`."""
    a = acct(url, pk)
    d = base64.b64decode(a["data"][0])
    disc_ok = d[0:8] == _QUEUE_ACCOUNT_DISCRIMINATOR
    return {"queue": pk, "owner": a["owner"], "discriminator_ok": disc_ok, "authority": b58(d[8:40])}


def read_squadsv3(url, pk, authority_index=None):
    # Squads v3 (squads-mpl, SMPLecH534NA9acpos4G6x7uf3LWbCAwZQE9e8ZekMu) Ms account
    a = acct(url, pk); d = base64.b64decode(a["data"][0]); o = 8
    thr = int.from_bytes(d[o:o+2], "little"); o += 2
    ai = int.from_bytes(d[o:o+2], "little"); o += 2
    o += 8 + 1 + 32 + 1
    n = int.from_bytes(d[o:o+4], "little"); o += 4
    keys = [b58(d[o+32*i:o+32*(i+1)]) for i in range(n)]
    out = {"ms": pk, "owner": a["owner"], "threshold": thr, "authority_index": ai, "n_keys": n, "keys": keys}
    if authority_index is not None:
        idx = int(authority_index)
        out["authority_%d" % idx] = find_program_address([b"squad", b58dec(pk), idx.to_bytes(4, "little"), b"authority"],
                                                        "SMPLecH534NA9acpos4G6x7uf3LWbCAwZQE9e8ZekMu")[0]
    return out


def read_programs_by_authority(url, authority):
    # reverse lookup: every ProgramData (u32 tag 3) whose upgrade_authority (offset 13) == authority
    r = rpc(url, "getProgramAccounts", ["BPFLoaderUpgradeab1e11111111111111111111111",
            {"encoding": "base64", "dataSlice": {"offset": 0, "length": 0},
             "filters": [{"memcmp": {"offset": 0, "bytes": "4"}}, {"memcmp": {"offset": 13, "bytes": authority}}]}])
    return {"authority": authority, "programdata_count": len(r), "programdata": sorted(x["pubkey"] for x in r)}


def read_program_of_programdata(url, programdata):
    # reverse of read_program: the Program account (u32 tag 2, size 36) whose programdata_address == programdata
    r = rpc(url, "getProgramAccounts", ["BPFLoaderUpgradeab1e11111111111111111111111",
            {"encoding": "base64", "dataSlice": {"offset": 0, "length": 0},
             "filters": [{"dataSize": 36}, {"memcmp": {"offset": 4, "bytes": programdata}}]}])
    return {"programdata": programdata, "program": [x["pubkey"] for x in r]}


def read_kliquidity_global_config(url, pk):
    # Kamino kliquidity (yvaults) GlobalConfig -- a DIFFERENT Kamino
    # product/program than klend (read_klend_market above), separate
    # on-chain account layout. Offset for `adminAuthority` computed field
    # by field from the actual Codama-generated codec source
    # (Kamino-Finance/kliquidity-sdk src/@codegen/kliquidity/accounts/
    # globalConfig.ts, getGlobalConfigDecoder's own field/size list, not
    # guessed): discriminator(8) + 7×u64(56) + 2×u32(8) + u64(8) +
    # 2×Address(64) + u64[256](2048) + Address(32) = 2224 -- independently
    # confirmed 2026-09-18 by also searching the raw account bytes for
    # the expected pubkey and finding it at this exact offset, not just
    # trusting the arithmetic.
    #
    # ADDED 2026-09-25: `actionsAuthority` (offset 2192, the "2×Address(64)"
    # pair immediately before `adminAuthority`'s own Address(32) in the same
    # field list) -- cross-checked exactly like `admin_authority`: decoding
    # BOTH at once and confirming `admin_authority` still lands on its own
    # already-published value proves this second offset in the same
    # sequential read is sound too, not a fluke.
    #
    # ADDED 2026-10-05 (oracleAuthorityScore of Kamino Liquidity), from the kliquidity program's on-chain Anchor IDL:
    # `scopeProgramId` at 80 (discriminator(8) + 7×u64(56) + 2×u32(8) + u64(8)) and `tokenInfos` at 10448 (adminAuthority
    # 2224 + Address(32) + treasuryFeeVaults Address[256](8192)), the CollateralInfos account every strategy prices from.
    d = base64.b64decode(acct(url, pk)["data"][0])
    return {"global_config": pk, "actions_authority": b58(d[2192:2224]), "admin_authority": b58(d[2224:2256]),
            "scope_program": b58(d[80:112]), "token_infos": b58(d[10448:10480])}


def read_kliquidity_collateral_feeds(url, pk):
    # ADDED 2026-10-05: Kamino Liquidity CollateralInfos (GlobalConfig.tokenInfos): discriminator(8) + CollateralInfo[303],
    # 216 bytes each, field by field from the kliquidity on-chain Anchor IDL: mint(32) + 4×u64(32) + scopeTwapPriceChain
    # [u16;4](8) + scopePriceChain [u16;4](8) + name [u8;32](32) + 3×u64(24) + disabled u8 (offset 136) + padding0 [u8;7] +
    # scopeStakingRateChain [u16;4](8) = 152: scopeFeed (the Scope OraclePrices account its price chains index), then
    # padding [u64;4]. An entry whose mint is zero is unused and skipped. Any other account size raises: never a short list.
    d = base64.b64decode(acct(url, pk)["data"][0])
    if len(d) != 8 + 216 * 303:
        raise ValueError(f"CollateralInfos {pk}: {len(d)} bytes, expected {8 + 216 * 303}")
    entries = (d[8 + 216 * i:8 + 216 * (i + 1)] for i in range(303))
    return [{"mint": b58(e[:32]), "scope_feed": b58(e[152:184]), "disabled": e[136]} for e in entries if any(e[:32])]


def read_jupiter_perpetuals(url, pk):
    # Jupiter Perpetuals global account. `admin` confirmed at offset 51
    # (right after an 8-byte discriminator + a 1-byte enum/flag field +
    # 2 pubkeys -- permissions/other header fields precede it) by
    # searching the raw account bytes for the known admin pubkey; this
    # account is small (120 bytes total) so a byte-presence match here is
    # effectively conclusive (no realistic chance of a coincidental
    # 32-byte collision in a 120-byte account).
    d = base64.b64decode(acct(url, pk)["data"][0])
    return {"perpetuals": pk, "admin": b58(d[51:83])}


def read_jupiter_lend_liquidity(url, pk):
    # Jupiter Lend's Liquidity program's own top-level state account.
    # `authority` confirmed as the FIRST field (offset 8, right after the
    # 8-byte Anchor discriminator) via jup-ag/jupiter-lend's own published
    # target/idl/liquidity.json (type "Liquidity": authority: pubkey,
    # revenue_collector: pubkey, status: bool, bump: u8 -- the exact
    # field order Anchor's IDL generator emits, not guessed).
    d = base64.b64decode(acct(url, pk)["data"][0])
    return {"liquidity": pk, "authority": b58(d[8:40])}


def read_jupiter_lend_authorization_list(url, program_id):
    # ADDED 2026-09-25: closes score_jupiter_lend's own "NOT decoded this pass" open point on
    # the AuthorizationList account. Ordinary Borsh (Vec<Pubkey> fields, standard Anchor, NOT the
    # bytemuck/zero-copy style marginfi/Kamino use), so each field is a 4-byte little-endian
    # length prefix followed by that many 32-byte pubkeys -- type confirmed live via jup-ag/
    # jupiter-lend's own published target/idl/liquidity.json ("AuthorizationList": auth_users:
    # Vec<pubkey>, guardians: Vec<pubkey>, user_classes: Vec<UserClass> -- only the first two are
    # decoded here, user_classes not needed for authority scoring). PDA seed (b"auth_list", no
    # per-account variance) from the SAME IDL's own init_liquidity instruction account list, not
    # guessed.
    addr, _ = find_program_address([b"auth_list"], program_id)
    d = base64.b64decode(acct(url, addr)["data"][0])
    o = 8
    n_auth_users = int.from_bytes(d[o:o + 4], "little"); o += 4
    auth_users = [b58(d[o + i * 32:o + i * 32 + 32]) for i in range(n_auth_users)]; o += 32 * n_auth_users
    n_guardians = int.from_bytes(d[o:o + 4], "little"); o += 4
    guardians = [b58(d[o + i * 32:o + i * 32 + 32]) for i in range(n_guardians)]
    return {"auth_list": addr, "auth_users": auth_users, "guardians": guardians}


def read_pumpswap_global_config(url, pk):
    # PumpSwap's GlobalConfig. `admin` confirmed as the FIRST field
    # (offset 8) via the program's own on-chain Anchor IDL (type
    # "GlobalConfig": admin: pubkey, lp_fee_basis_points: u64, ... --
    # fetched live 2026-09-18, not from a static repo citation).
    d = base64.b64decode(acct(url, pk)["data"][0])
    return {"global_config": pk, "admin": b58(d[8:40])}


def read_whirlpools_config(url, pk):
    # Orca Whirlpool's global WhirlpoolsConfig. Exact layout confirmed
    # 2026-09-18 from orca-so/whirlpools' own Rust source (programs/
    # whirlpool/src/state/config.rs): `#[account] pub struct
    # WhirlpoolsConfig { pub fee_authority: Pubkey, pub collect_protocol_
    # fees_authority: Pubkey, pub reward_emissions_super_authority:
    # Pubkey, ... }` -- three consecutive Pubkeys right after the 8-byte
    # Anchor discriminator, no padding or hidden fields between them
    # (the struct's own `pub const LEN: usize = 8 + 96 + 4` confirms
    # exactly 96 bytes = 3 Pubkeys between the discriminator and the two
    # trailing u16 fields).
    d = base64.b64decode(acct(url, pk)["data"][0])
    return {
        "config": pk,
        "fee_authority": b58(d[8:40]),
        "collect_protocol_fees_authority": b58(d[40:72]),
        "reward_emissions_super_authority": b58(d[72:104]),
    }


def read_marginfi_group(url, pk):
    # marginfi's MarginfiGroup (Anchor zero-copy, 8-byte discriminator,
    # #[repr(C)] + bytemuck::Pod -- every gap is a hand-inserted pad field
    # in the struct itself, so no implicit-compiler-padding guesswork is
    # needed between fields; offsets are a plain running sum of field sizes
    # in declared order). `admin` (offset 8) decoded since 2026-09-18.
    #
    # FIXED 2026-09-25: the SIX further admin-named fields this account's
    # own on-chain IDL lists were "not computed" until now, sitting after
    # `fee_state_cache`/`panic_state_cache`/`deleverage_withdraw_window_
    # cache` (three `defined` types whose own field lists were fetched from
    # the same live IDL, not guessed -- FeeStateCache 72B, PanicStateCache
    # 24B, WithdrawWindowCache 16B, each independently size-checked against
    # its own field list before use). Every field below cross-checks two
    # ways before being trusted: (a) three offsets in the SAME sequential
    # read (`admin`@8, `emode_admin`@128, `risk_admin`@296) independently
    # decode to the exact SAME already-known, already-published pubkey
    # (CYXEgwbPHu2f9cY3mcUkinzDoDcsSan7myh1uBvYRbEw) -- a coincidental
    # garbage match at three unrelated offsets is not a realistic failure
    # mode, so this confirms the whole offset chain up to risk_admin is
    # sound; (b) read on 2 independent RPCs (api.mainnet-beta.solana.com,
    # solana-rpc.publicnode.com), byte-identical. `delegate_flow_admin`
    # (past `rate_limiter`, a further not-yet-resolved `defined` type)
    # stays undecoded -- its own docstring already says a compromised
    # holder "does not itself compromise any funds", so leaving it open
    # costs nothing per METHODOLOGY.md 6.2's own bounded/full-power split.
    d = base64.b64decode(acct(url, pk)["data"][0])
    return {
        "group": pk,
        "admin": b58(d[8:40]),                      # offset 0 (+8 discriminator)
        "emode_admin": b58(d[128:160]),              # offset 120: 32(admin)+8(group_flags)+72(fee_state_cache)+2(banks)+6(pad0)
        "delegate_curve_admin": b58(d[160:192]),     # offset 152: += 32 (emode_admin)
        "delegate_limit_admin": b58(d[192:224]),     # offset 184: += 32 (delegate_curve_admin)
        "delegate_emissions_admin": b58(d[224:256]), # offset 216: += 32 (delegate_limit_admin)
        "risk_admin": b58(d[296:328]),               # offset 288: += 32(delegate_emissions_admin)+24(panic_state_cache)+16(withdraw_window_cache)
        "metadata_admin": b58(d[328:360]),           # offset 320: += 32 (risk_admin)
    }


def read_klend_market(url, pk):
    # Kamino klend LendingMarket (zero-copy, 8-byte Anchor discriminator), offsets from
    # programs/klend/src/state/lending_market.rs; `name` is decoded as a layout self-check
    a = acct(url, pk); d = base64.b64decode(a["data"][0])
    gc, _ = find_program_address([b"global_config"], a["owner"])
    g = base64.b64decode(acct(url, gc)["data"][0])
    return {"market": pk, "owner_program": a["owner"], "name": d[3248:3280].rstrip(b"\0").decode(),
            "lending_market_owner": b58(d[24:56]), "lending_market_owner_cached": b58(d[56:88]),
            "emergency_council": b58(d[160:192]), "immutable": d[3305], "proposer_authority": b58(d[3312:3344]),
            "global_config": gc, "global_admin": b58(g[8:40])}


def read_klend_reserve_oracle(url, pk):
    # TokenInfo inside the Reserve account: name at 5032, scope price_feed at 5112,
    # price_chain/twap_chain u16[4] at 5144/5152, switchboard 5160/5192, pyth 5224
    d = base64.b64decode(acct(url, pk)["data"][0]); u = lambda o: int.from_bytes(d[o:o+8], "little")
    return {"reserve": pk, "name": d[5032:5064].rstrip(b"\0").decode(), "max_twap_divergence_bps": u(5088),
            "max_age_price_s": u(5096), "scope_price_feed": b58(d[5112:5144]),
            "scope_price_chain": [int.from_bytes(d[5144+2*i:5146+2*i], "little") for i in range(4)],
            "scope_twap_chain": [int.from_bytes(d[5152+2*i:5154+2*i], "little") for i in range(4)],
            "switchboard_price": b58(d[5160:5192]), "pyth_price": b58(d[5224:5256])}


def read_scope_configs(url, pk):
    # every Kamino Scope Configuration account (Anchor discriminator of "account:Configuration")
    disc = b58(hashlib.sha256(b"account:Configuration").digest()[:8])
    r = rpc(url, "getProgramAccounts", [pk, {"encoding": "base64", "dataSlice": {"offset": 0, "length": 264},
            "filters": [{"memcmp": {"offset": 0, "bytes": disc}}]}])
    names = ("admin", "oracle_mappings", "oracle_prices", "tokens_metadata", "oracle_twaps", "admin_cached", "emergency_council", "resume_authority")
    out = []
    for x in r:
        d = base64.b64decode(x["account"]["data"][0])
        out.append(dict([("configuration", x["pubkey"])] + [(n, b58(d[8+32*i:40+32*i])) for i, n in enumerate(names)]))
    return sorted(out, key=lambda c: c["configuration"])


def read_anchor_idl(url, pk):
    # on-chain Anchor IDL account: create_with_seed(find_program_address([], pid), "anchor:idl", pid)
    import zlib
    base, _ = find_program_address([], pk)
    idl = b58(hashlib.sha256(b58dec(base) + b"anchor:idl" + b58dec(pk)).digest())
    raw = acct(url, idl)
    if raw is None:
        return None  # FIXED 2026-09-25: no on-chain IDL account for this program (getAccountInfo -> null) is a
        # real, distinct outcome from a malformed/unreadable one -- callers must check for it, not crash on ["data"]
    d = base64.b64decode(raw["data"][0]); n = int.from_bytes(d[40:44], "little")
    j = json.loads(zlib.decompress(d[44:44+n]))
    fixed = sorted({(i["name"], a["name"], a["address"]) for i in j["instructions"] for a in i["accounts"]
                    if "address" in a and not a["address"].endswith("1111111111111111") and a["address"] != "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL"})
    return {"idl_account": idl, "idl_authority": b58(d[8:40]), "instructions": [i["name"] for i in j["instructions"]],
            "accounts": [x["name"] for x in j.get("accounts", [])],
            "hardcoded_addresses": [{"instruction": f[0], "account": f[1], "address": f[2]} for f in fixed]}


def read_realm(url, pk):
    # RealmV2 (spl-governance state/realm.rs), Borsh layout confirmed byte-for-byte
    # against the canonical struct source (solana-labs/solana-program-library
    # governance/program/src/state/realm.rs) and cross-checked against Realms'
    # own UI (app.realms.today) showing the identical realm pubkey, 2026-09-17:
    #   account_type: u8 (1) | community_mint: Pubkey (32)
    #   RealmConfig: legacy1 u8 (1) | legacy2 u8 (1) | reserved [u8;6] (6) |
    #     min_community_weight_to_create_governance: u64 (8) |
    #     community_mint_max_voter_weight_source: tag u8 (1) + value u64 (8) |
    #     council_mint: Option<Pubkey> (1, +32 if Some)
    #   reserved [u8;6] (6) | legacy1 (old voting_proposal_count): u16 (2) |
    #   authority: Option<Pubkey> (1, +32 if Some) | name: String (u32 len + bytes)
    d = base64.b64decode(acct(url, pk)["data"][0]); o = 0
    account_type = d[o]; o += 1
    community_mint = b58(d[o:o+32]); o += 32
    o += 1 + 1 + 6  # RealmConfig legacy1/legacy2/reserved
    min_weight_to_create_governance = int.from_bytes(d[o:o+8], "little"); o += 8
    mmvw_tag = d[o]; o += 1
    mmvw_value = int.from_bytes(d[o:o+8], "little"); o += 8
    has_council = d[o]; o += 1
    council_mint = None
    if has_council == 1:
        council_mint = b58(d[o:o+32]); o += 32
    o += 6 + 2  # RealmV2 reserved + legacy1 (old voting_proposal_count)
    has_authority = d[o]; o += 1
    authority = None
    if has_authority == 1:
        authority = b58(d[o:o+32]); o += 32
    name_len = int.from_bytes(d[o:o+4], "little"); o += 4
    name = d[o:o+name_len].decode("utf-8", "replace")
    return {"realm": pk, "account_type": account_type, "community_mint": community_mint,
            "min_community_weight_to_create_governance": min_weight_to_create_governance,
            "community_mint_max_voter_weight_source": {"kind": "SupplyFraction" if mmvw_tag == 0 else "Absolute", "value": mmvw_value},
            "council_mint": council_mint, "authority": authority, "name": name}


def read_governance(url, pk):
    # GovernanceV2, the pre-"program V3 active_proposal_count" layout Solend's
    # own deployed program (a separate instance, NOT the shared default) still
    # uses -- confirmed by anchoring on the one field independently re-derived
    # two other ways in data/methodology_test_2026-09-17-solend-governance.md
    # (voting_base_time = 259200s, matching both a raw-byte brute-force scan
    # and the known SLND7 "increase to 3 days" follow-up proposal):
    #   account_type: u8 (1) | realm: Pubkey (32) | governed_account: Pubkey (32) |
    #   proposals_count: u32 (4)
    #   GovernanceConfig: community_vote_threshold: tag u8 (1) + value u8 (1) |
    #     min_community_weight_to_create_proposal: u64 (8) |
    #     transactions_hold_up_time: u32 (4) | voting_base_time: u32 (4) |
    #     community_vote_tipping: u8 (1) | council_vote_threshold: tag u8 (1) + value u8 (1)
    # NOT decoded past this point (min_council_weight_to_create_proposal onward):
    # Solend's realm has no council mint, so nothing past here can affect a
    # target that only has community-token voting.
    d = base64.b64decode(acct(url, pk)["data"][0]); o = 0
    account_type = d[o]; o += 1
    realm = b58(d[o:o+32]); o += 32
    governed_account = b58(d[o:o+32]); o += 32
    proposals_count = int.from_bytes(d[o:o+4], "little"); o += 4
    threshold_tag = d[o]; o += 1
    threshold_value = d[o]; o += 1
    min_weight_to_create_proposal = int.from_bytes(d[o:o+8], "little"); o += 8
    transactions_hold_up_time = int.from_bytes(d[o:o+4], "little"); o += 4
    voting_base_time = int.from_bytes(d[o:o+4], "little"); o += 4
    return {"governance": pk, "account_type": account_type, "realm": realm,
            "governed_account": governed_account, "proposals_count": proposals_count,
            "community_vote_threshold": {"kind": "YesVotePercentage" if threshold_tag == 0 else "QuorumPercentage", "value": threshold_value},
            "min_community_weight_to_create_proposal": min_weight_to_create_proposal,
            "transactions_hold_up_time_s": transactions_hold_up_time,
            "voting_base_time_s": voting_base_time}


def _vote_threshold(d, o):
    # VoteThreshold enum (state/enums.rs): tag 0 YesVotePercentage(u8) or
    # tag 1 QuorumPercentage(u8) consume one payload byte; tag 2 Disabled
    # consumes NONE -- this variable-length encoding is exactly the bug
    # class this project already caught once decoding by hand (see
    # data/finding_2026-09-17-spl-governance-shared-instance-controller.md).
    tag = d[o]; o += 1
    if tag in (0, 1):
        val = d[o]; o += 1
        return {"tag": tag, "kind": "YesVotePercentage" if tag == 0 else "QuorumPercentage", "pct": val}, o
    return {"tag": tag, "kind": "Disabled", "pct": None}, o


def read_governance_v2(url, pk):
    # GovernanceV2, the MODERN layout (program version >= ~3.x, seen on
    # every governance program deployment checked this pass EXCEPT
    # Solend's own decade-old one -- Drift's dgov7NC8..., and the "Realms
    # Security council 8" deployment GoVERLMGb...). NOT interchangeable
    # with read_governance() above: same account_type discriminant number,
    # DIFFERENT byte layout -- a real, disclosed version-dependent trap
    # (data/finding_2026-09-17-spl-governance-shared-instance-controller.md's
    # "What this changes" section), closed here rather than left flagged
    # once a second real target (Drift) needed it too:
    #   account_type: u8 (1) | realm: Pubkey (32) | governance_seed: Pubkey (32) |
    #   reserved1: u32 (4)
    #   GovernanceConfig: community_vote_threshold: VoteThreshold |
    #     min_community_weight_to_create_proposal: u64 (8) |
    #     transactions_hold_up_time: u32 (4) | voting_base_time: u32 (4) |
    #     community_vote_tipping: u8 (1) | council_vote_threshold: VoteThreshold |
    #     council_veto_vote_threshold: VoteThreshold |
    #     min_council_weight_to_create_proposal: u64 (8) |
    #     council_vote_tipping: u8 (1) | community_veto_vote_threshold: VoteThreshold |
    #     voting_cool_off_time: u32 (4) | deposit_exempt_proposal_count: u8 (1)
    # Verified against two independent real accounts this pass (Drift
    # DAO's own realm-authority Governance, and "Realms Security council
    # 8"'s Governance) -- see their respective methodology-test/finding
    # files for the byte-level cross-check.
    d = base64.b64decode(acct(url, pk)["data"][0]); o = 0
    account_type = d[o]; o += 1
    realm = b58(d[o:o+32]); o += 32
    governance_seed = b58(d[o:o+32]); o += 32
    o += 4  # reserved1
    community_vote_threshold, o = _vote_threshold(d, o)
    min_weight_to_create_proposal = int.from_bytes(d[o:o+8], "little"); o += 8
    transactions_hold_up_time = int.from_bytes(d[o:o+4], "little"); o += 4
    voting_base_time = int.from_bytes(d[o:o+4], "little"); o += 4
    community_vote_tipping = d[o]; o += 1
    council_vote_threshold, o = _vote_threshold(d, o)
    council_veto_vote_threshold, o = _vote_threshold(d, o)
    min_council_weight_to_create_proposal = int.from_bytes(d[o:o+8], "little"); o += 8
    council_vote_tipping = d[o]; o += 1
    community_veto_vote_threshold, o = _vote_threshold(d, o)
    voting_cool_off_time = int.from_bytes(d[o:o+4], "little"); o += 4
    deposit_exempt_proposal_count = d[o]; o += 1
    return {"governance": pk, "account_type": account_type, "realm": realm,
            "governance_seed": governance_seed,
            "community_vote_threshold": community_vote_threshold,
            "min_community_weight_to_create_proposal": min_weight_to_create_proposal,
            "transactions_hold_up_time_s": transactions_hold_up_time,
            "voting_base_time_s": voting_base_time,
            "community_vote_tipping": community_vote_tipping,
            "council_vote_threshold": council_vote_threshold,
            "council_veto_vote_threshold": council_veto_vote_threshold,
            "min_council_weight_to_create_proposal": min_council_weight_to_create_proposal,
            "council_vote_tipping": council_vote_tipping,
            "community_veto_vote_threshold": community_veto_vote_threshold,
            "voting_cool_off_time_s": voting_cool_off_time,
            "deposit_exempt_proposal_count": deposit_exempt_proposal_count}


def read_splmultisig(url, pk):
    a = acct(url, pk, "jsonParsed")
    return {"account": pk, "owner": a["owner"], "parsed": a["data"]["parsed"]}


def read_marinade_state(url, pk):
    # Marinade `State` account (programs/marinade-finance/src/state/mod.rs),
    # confirmed byte-for-byte two independent ways: field-order arithmetic
    # from the real source AND the program's own on-chain Anchor IDL
    # (both agree: admin_authority is the 2nd field, offset 40, right after
    # the 8-byte discriminator + 32-byte msol_mint). Only admin_authority
    # and pause_authority are decoded here; every other field on this large
    # (2616-byte) account is disclosed as NOT decoded, not guessed.
    d = base64.b64decode(acct(url, pk)["data"][0])
    return {
        "state": pk,
        "msol_mint": b58(d[8:40]),
        "admin_authority": b58(d[40:72]),
        "pause_authority": b58(d[576:608]),
        "paused": d[608] == 1,
    }


def read_legacy_serum_multisig(url, pk):
    # A "serum-style" multisig (project-serum/multisig, forked verbatim by
    # several teams incl. marinade-finance/multisig) -- an OLD (2021-era)
    # multisig shape, structurally distinct from both Squads v3 and v4:
    # no permission bitmask (every owner can sign), no time_lock field at
    # all (execute_transaction only checks did_execute + sig_count >=
    # threshold), and a single-seed signer PDA `[multisig_pubkey]` with
    # `bump = multisig.nonce` (not derived/searched -- the stored nonce IS
    # the bump, confirmed against marinade-finance/multisig@v0.7.0's own
    # `execute_transaction` re-derivation code). Borsh layout, no padding:
    #   owners: Vec<Pubkey> (4-byte len + N*32) | threshold: u64 (8) |
    #   nonce: u8 (1) | owner_set_seqno: u32 (4)
    d = base64.b64decode(acct(url, pk)["data"][0])
    n = int.from_bytes(d[8:12], "little")
    owners = [b58(d[12 + 32 * i: 44 + 32 * i]) for i in range(n)]
    o = 12 + 32 * n
    threshold = int.from_bytes(d[o:o + 8], "little")
    nonce = d[o + 8]
    owner_set_seqno = int.from_bytes(d[o + 9:o + 13], "little")
    return {"multisig": pk, "owners": owners, "threshold": threshold, "nonce": nonce, "owner_set_seqno": owner_set_seqno}


def read_token_owner_record(url, pk):
    # TokenOwnerRecordV2 (spl-governance state/token_owner_record.rs),
    # Borsh layout confirmed against the real struct source and live
    # cross-checked by re-deriving this account's own PDA (seeds =
    # ["governance", realm, governing_token_mint, governing_token_owner])
    # and requiring an exact match, the same offline-re-derivation
    # discipline every other multisig/authority read in this file uses:
    #   account_type: u8 (1) | realm: Pubkey (32) | governing_token_mint:
    #   Pubkey (32) | governing_token_owner: Pubkey (32) |
    #   governing_token_deposit_amount: u64 (8)
    # NOT decoded past this point (unlocked_governing_token_deposit_amount
    # onward) -- not needed for a deposit-weight census.
    d = base64.b64decode(acct(url, pk)["data"][0])
    return {
        "tor": pk, "account_type": d[0], "realm": b58(d[1:33]),
        "governing_token_mint": b58(d[33:65]), "governing_token_owner": b58(d[65:97]),
        "governing_token_deposit_amount": int.from_bytes(d[97:105], "little"),
    }


def list_token_owner_records(url, governance_program, realm, mint, account_type=17):
    # Enumerates every TokenOwnerRecordV2 for one (realm, governing_token_mint)
    # pair via getProgramAccounts + memcmp, rather than hardcoding a member
    # list -- so a future re-run picks up real membership changes instead of
    # silently going stale. account_type=17 is TokenOwnerRecordV2's discriminant
    # in the GovernanceAccountType enum (confirmed against solana-program-
    # library's governance/program/src/state/enums.rs: RealmV2=16 and
    # GovernanceV2=18 bracket it, both independently confirmed live elsewhere
    # in this file's callers).
    filters = [
        {"memcmp": {"offset": 0, "bytes": b58(bytes([account_type]))}},
        {"memcmp": {"offset": 1, "bytes": realm}},
        {"memcmp": {"offset": 33, "bytes": mint}},
    ]
    accounts = rpc(url, "getProgramAccounts", [governance_program, {"encoding": "base64", "filters": filters}])
    out = []
    for a in accounts:
        d = base64.b64decode(a["account"]["data"][0])
        out.append({
            "tor": a["pubkey"], "governing_token_owner": b58(d[65:97]),
            "governing_token_deposit_amount": int.from_bytes(d[97:105], "little"),
        })
    return out


def resolve_controller_via_last_tx(url, authority, multisig_program_id, limit=5):
    """METHODOLOGY.md 3.3 ladder rung 3's resolution procedure, as a reusable
    function (previously done by hand in data/methodology_test_2026-09-16.md
    for each of Jupiter/Kamino's off-curve authorities, not yet a callable
    helper). Finds the most recent transaction signed through `authority`
    that invokes `multisig_program_id` as a top-level instruction, and
    returns that instruction's first account (the Ms/multisig account per
    Squads' own instruction layout -- NOT proof by itself, the caller MUST
    still offline-re-derive the vault/authority PDA from the returned
    account and require an exact match against `authority`, exactly as
    METHODOLOGY.md requires: 'A transaction alone is not proof.'

    Scans up to `limit` most recent signatures (not just the newest one) in
    case the very latest transaction touching this key isn't itself a
    Squads execute call (e.g. a plain lamport transfer to the PDA)."""
    sigs = rpc(url, "getSignaturesForAddress", [authority, {"limit": limit}])
    for s in sigs:
        if s.get("err") is not None:
            continue
        tx = rpc(url, "getTransaction", [s["signature"], {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}])
        if not tx:
            continue
        for ix in tx["transaction"]["message"]["instructions"]:
            if ix.get("programId") == multisig_program_id and ix.get("accounts"):
                return {"signature": s["signature"], "multisig_candidate": ix["accounts"][0]}
    return None


def read_program(url, pk):
    a = acct(url, pk, length=36)
    out = {"program": pk, "owner": a["owner"], "executable": a["executable"]}
    if a["owner"] == "BPFLoaderUpgradeab1e11111111111111111111111":
        d = base64.b64decode(a["data"][0])
        assert int.from_bytes(d[:4], "little") == 2, "not a Program state"
        pd = b58(d[4:36]); out["programdata"] = pd
        p = base64.b64decode(acct(url, pd, length=45)["data"][0])
        assert int.from_bytes(p[:4], "little") == 3
        out["last_deploy_slot"] = int.from_bytes(p[4:12], "little")
        out["upgrade_authority"] = b58(p[13:45]) if p[12] == 1 else None
    return out


def read_mint(url, pk):
    a = acct(url, pk, "jsonParsed")
    info = a["data"]["parsed"]["info"]
    return {"mint": pk, "owner": a["owner"], "mintAuthority": info.get("mintAuthority"),
            "freezeAuthority": info.get("freezeAuthority"), "supply": int(info["supply"]),
            "decimals": info.get("decimals"),
            "extensions": [e.get("extension") for e in info.get("extensions", [])]}


def read_squads(url, pk):
    a = acct(url, pk); d = base64.b64decode(a["data"][0]); o = 8
    create_key = b58(d[o:o+32]); o += 32
    cfg = b58(d[o:o+32]); o += 32
    thr = int.from_bytes(d[o:o+2], "little"); o += 2
    tl = int.from_bytes(d[o:o+4], "little"); o += 4
    o += 16
    if d[o] == 1: o += 33
    else: o += 1
    o += 1
    n = int.from_bytes(d[o:o+4], "little"); o += 4
    members = []
    for _ in range(n):
        members.append({"key": b58(d[o:o+32]), "mask": d[o+32]}); o += 33
    return {"multisig": pk, "owner": a["owner"], "config_authority": cfg, "threshold": thr,
            "time_lock_s": tl, "members": len(members), "member_list": members}


def main():
    cmd, url = sys.argv[1], sys.argv[2]
    if cmd == "genesis":
        print(rpc(url, "getGenesisHash")); return
    pk = sys.argv[3]
    if cmd == "keytype":
        print(json.dumps(read_keytype(url, pk))); return
    if cmd == "pda-programdata":
        print(json.dumps(read_pda_programdata(pk))); return
    if cmd == "squads-vault":
        idx = int(sys.argv[4]) if len(sys.argv) > 4 else 0
        print(json.dumps(read_squads_vault(pk, idx))); return
    if cmd == "pyth-config":
        print(json.dumps(read_pyth_config(url, pk))); return
    if cmd == "squadsv3":
        authority_index = sys.argv[4] if len(sys.argv) > 4 else None
        print(json.dumps(read_squadsv3(url, pk, authority_index))); return
    if cmd == "programs-by-authority":
        print(json.dumps(read_programs_by_authority(url, pk))); return
    if cmd == "program-of-programdata":
        print(json.dumps(read_program_of_programdata(url, pk))); return
    if cmd == "klend-market":
        print(json.dumps(read_klend_market(url, pk))); return
    if cmd == "klend-reserve-oracle":
        print(json.dumps(read_klend_reserve_oracle(url, pk))); return
    if cmd == "scope-configs":
        print(json.dumps(read_scope_configs(url, pk))); return
    if cmd == "anchor-idl":
        print(json.dumps(read_anchor_idl(url, pk))); return
    if cmd == "splmultisig":
        print(json.dumps(read_splmultisig(url, pk))); return
    if cmd == "realm":
        print(json.dumps(read_realm(url, pk))); return
    if cmd == "governance":
        print(json.dumps(read_governance(url, pk))); return
    if cmd == "governance-v2":
        print(json.dumps(read_governance_v2(url, pk))); return
    if cmd == "program":
        print(json.dumps(read_program(url, pk))); return
    if cmd == "mint":
        print(json.dumps(read_mint(url, pk))); return
    if cmd == "squads":
        print(json.dumps(read_squads(url, pk))); return
    if cmd == "switchboard-pull-feed":
        print(json.dumps(read_switchboard_pull_feed(url, pk))); return
    if cmd == "switchboard-queue":
        print(json.dumps(read_switchboard_queue(url, pk))); return
    raise SystemExit(f"unknown command: {cmd}")


if __name__ == "__main__":
    main()
