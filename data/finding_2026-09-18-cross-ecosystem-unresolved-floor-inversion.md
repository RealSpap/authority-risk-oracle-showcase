# Finding (2026-09-18): the "unresolved authority" fallback score outranks a confirmed weak authority in most ecosystems -- Zcash already fixed it, Solana and Ethereum L1 have not

Surfaced from a tracked GitHub Projects item ("le repli 20/20 pour un
[backlog note]").
Investigated via a dedicated Explore pass, cross-checked independently
against the real source before writing this up. Pure investigation --
**no scorer file is modified by this finding.** A fix touches published
scores across (potentially) three ecosystems and needs this project's
own adversarial-review discipline before committing, per `AGENTS.md`'s
"Before committing" section -- not attempted here.

## The pattern, and why it matters

Every ecosystem in this project treats "a live read failed / an
authority type didn't match anything known" as a DEGRADED result, never
a crash -- that discipline is solid and consistent. The problem is what
"degraded" actually SCORES: in most of the sites found below, the
degraded/unresolved fallback scores HIGHER (safer-looking) than this
same file's own confirmed-weakest real authority (a bare 1-of-1 EOA or
Safe). An oracle whose "I don't know" answer looks safer than its own
worst *confirmed* answer defeats the fail-closed principle this project
states everywhere else (see AGENTS.md's verification-discipline section:
"a getter succeeding is not evidence of real gating").

## Solana (`chains/solana/scorers.py`) -- the dominant case, 21 sites

Confirmed floor (`_score_full_power_path`, lines 70-78): a bare EOA or a
confirmed 1-of-N Squads multisig both score **adminKey 5, multisig 0**.
The unresolved fallback `admin, multisig, timelock = 20, 20, 0` appears
at **21 call sites** (verified via `grep -c`) across 11 of the file's 13
scorer functions -- lines 216, 439, 619 (`20,20,0,20`), 730, 744, 749,
836, 850, 936, 950, 1019, 1033, 1107, 1121, 1181, 1195, 1303, 1398, 1415,
1553, 1573. A separate `"off_curve_unresolved"` path (lines 74-75, `20,
0, 0`) is called at lines 318 and 476. Every one of these scores
adminKey 20 (and often multisig 20) above the file's own 5/0 floor. This
is the file's dominant idiom for "unresolved," not an edge case --
fixing this one file addresses the large majority of instances found.

## Ethereum L1 (`chains/ethereum-l1/scorers.py`) -- same pattern, 8 sites, less uniform

Confirmed floor: `score_usdtb`'s bare EOA case, **adminKey 5** (line
474), **multisig 0** (line 479). 8 fallback sites across 6 functions,
and the fallback value is NOT always literally 20/20 (worth noting
since the tracker item's own title assumed "20/20" as a given):
- `score_uniswap_v3_factory:149` adminKey=20 (confirmed 80 at line 147)
- `score_aave_v3_pool:259` adminKey=20 (confirmed 78 at line 257)
- `score_makerdao_sky_pause:299` adminKey=20 (confirmed 75 at line 297)
- `score_ethena_minting:393-394` adminKey=**10**, multisig=20 (confirmed 55/up-to-100 at 384/391)
- `score_usdtb:477` adminKey=20 (confirmed 5 at line 474 -- the file's OWN floor, inverted by its own fallback)
- `score_usdtb_psm:580` adminKey=multisig=20 (confirmed 30-65/100)
- `score_ethena_layerzero_oft:719,722` (x3 adapters) adminKey=multisig=20 (confirmed 55/100)

All 8 sites score above the file's own 5/0 floor.

## Zcash (`chains/zcash/scorers.py`) -- mostly already fixed

The exact case this finding's title describes was already fixed in a
prior commit (`_UNRESOLVED_P2SH_ADMIN_KEY = 5`, `_UNRESOLVED_P2SH_MULTISIG
= 16`, lines 123-124, used at 326-335) -- the code's own comment states
it directly: "never the previous 20/20 placeholder, which scored an
unknown script ABOVE a known 1-of-3 (5/18)." (`multisig_score_kn(1,3) =
max(16, min(100, 20*1-(3-1))) = 18` -- a real 1-of-3's actual score;
`_UNRESOLVED_P2SH_MULTISIG=16` is the absolute floor across every k/n,
lower than that specific example, so the fallback still never outranks
ANY confirmed real script.) **This ecosystem's main instance is closed,
not a live gap.**

Two smaller spots remain, one real and one not:
- `score_l1():284` -- multisig fallback of 20 on a miner-concentration
  read failure. The worst *achievable* resolved value today (k50=k25=1,
  score 15+5=20) ties this exactly -- **not an inversion**, coincidence
  of the floor, not a bug.
- `score_ext_zec_omft():530` -- `admin_key, multisig = 20, 20` when no
  TokenDepositer path resolves. The file's live-confirmed weakest real
  key today (the Requestor group, 1-of-3, lines 519-528) scores **5/18**
  -- below this fallback. A genuine inversion, currently dormant only
  because the live read succeeds every run so far, not because the code
  guards against it.

## Open question for the fix (explicitly not decided here)

AdminKey's confirmed floor is 5 in all three files -- a shared
"unresolved adminKey must score below 5" rule may generalize cleanly.
Multisig is structurally different: Zcash's `multisig_score_kn` has a
built-in `max(16, ...)` floor baked into its own formula, while Solana
and Ethereum L1 can legitimately reach a confirmed 0 (no Safe at all).
Whether one project-wide multisig floor makes sense given that
structural difference, or whether each ecosystem needs its own value,
is a real design question for whoever runs the actual fix through this
project's adversarial-review process -- not settled by this
investigation.

## What this does NOT do

- Does not change any currently-published score in any ecosystem.
- Does not modify `chains/solana/scorers.py`, `chains/ethereum-l1/
  scorers.py`, or `chains/zcash/scorers.py`.
- Does not propose a specific replacement number -- see "Open question"
  above.
- Does not check Robinhood Chain, Base, Arbitrum, Hyperliquid, or Tempo
  for the same pattern -- the tracker item named zcash/solana/ethereum-l1
  specifically; whether the same idiom exists elsewhere is a follow-up,
  not covered here.
