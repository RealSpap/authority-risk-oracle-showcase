# Zcash -- scored targets, 2026-09-19

Resumes the `zenZEC` lead `data/scouting_candidates_2026-09-18.md` deferred: Zenrock's
docs/API were re-checked today and are still down (identical HTTP 402/503), but a
working alternative primary source (zrchain's own Tendermint RPC, hand-decoded
against its own published protobuf schema) resolved the live dMPC keyring threshold
this project's methodology needs. New target type `MPCKEYRING` (METHODOLOGY.md
3.7/4.8) and `scorers.py`'s `score_zenzec_mpc_keyring()`. Full derivation, every
cross-check, and every disclosed limitation:
[`data/zenzec_mpc_keyring_2026-09-19.md`](zenzec_mpc_keyring_2026-09-19.md). The six
pre-existing targets were also re-run live today, not carried over.

## Summary table (live run, 2026-09-19)

| Target | Key | adminKey | multisig | timelock | oracleAuthority | crossExposure | composite | l1CappedComposite |
|---|---|---|---|---|---|---|---|---|
| Zcash L1 (consensus-rule-change authority) | `0xB8e62E6AeB4C400b6F3e66cAb69ACe55439035c3` | 20 | 50 | 35 | 100 | 100 | **34** | n/a (baseline) |
| ZIP 271 one-time lockbox disbursement | `t3ev37Q2uL1sfTsiJQJiWJoFzQpDhmnUwYo` | 50 | 39 | 0 | 100 | 100 | **32** | **32** |
| ZCG funding stream (FS_FPF_ZCG_H3) | `t3cFfPt1Bcvgez9ZbMBFWeZsskxTkPzGCow` | 50 | 39 | 0 | 100 | 100 | **32** | **32** |
| `zec.omft.near` (NEAR PoA bridge, `EXT`) | `zec.omft.near` | 5 | 18 | 0 | 100 | 100 | **7** | n/a (off-Zcash) |
| Maya Protocol Asgard vault A (`XVAULT`) | `t1RBiXrLRdrHgsuSGQEusG2wCzPFczEVMfT` | 65 | 100 | 0 | 100 | 100 | **56** | n/a (off-Zcash authority, METHODOLOGY.md 4.7) |
| Maya Protocol Asgard vault B (`XVAULT`) | `t1VtnnhTYhmADh7L2uKU3Sev7GscBHT6HfE` | 65 | 100 | 0 | 100 | 100 | **56** | n/a |
| **Zenrock `zenZEC` dMPC custody keyring** (`MPCKEYRING`, new) | `keyring1k6vc6vhp6e6l3rxalue9v4ux` | 65 | 60 | 0 | 100 | 100 | **44** | n/a (off-Zcash authority, METHODOLOGY.md 4.8) |

The first six rows are unchanged in shape from `data/scored_targets_2026-09-18.md`,
re-run live today: `L1`'s concentration window is tip-relative
(3,486,232-3,488,231 today), `k50=3`/`k25=1` matching again is a fresh confirmation.
Both `FUND`s' revealed thresholds are unchanged (fixed forever by their `HASH160`
commitment, per METHODOLOGY.md 4.2). Both Asgard vaults' balances and 14-of-20
threshold are unchanged.

## Zenrock `zenZEC` dMPC custody keyring -- new `MPCKEYRING` target

**What it is.** A 3-of-3 (`party_threshold=3`, `len(parties)=3`) dMPC signer keyring
on Zenrock's own `zrchain` Mainnet (`diamond-1`), live-confirmed as the
`DepositKeyringAddr` `x/dct` module uses for `ASSET_ZENZEC` -- the authority that
gates every Zcash-side key this custody system ever generates, including a
freshly-created per-deposit one. Zenrock's own hosted docs (`docs.zenrocklabs.io`)
and REST/LCD gateway (`api.diamond.zenrocklabs.io`) were re-checked today and remain
down (HTTP 402 / 503, identical to 2026-09-18) -- resolved instead via hand-built
ABCI queries against zrchain's own Tendermint RPC (`rpc.diamond.zenrocklabs.io`),
using message shapes read directly from zrchain's own published `.pb.go` source. Full
derivation and every cross-check: `data/zenzec_mpc_keyring_2026-09-19.md`.

| Fact | Value |
|---|---|
| Keyring address | `keyring1k6vc6vhp6e6l3rxalue9v4ux` ("Zenrock MPC") |
| Party threshold (`k`) / parties (`n`) | 3 / 3 -- unanimous |
| Admins | 1 (`zen1wa2l79s9v9fxl0ergelvv55nmfdh6ms052c9rq`) |
| Wrapped-asset value (Solana, re-read today, unchanged from 2026-09-18) | 494.51437135 zenZEC, ~$769,707 at today's spot |
| Two nameable Zcash-mainnet infra addresses (rewards-deposit key 387, change-address key 388) | Both independently re-derived correctly from their live pubkeys; both hold **0 ZEC** on both lightwalletd operators today |
| Same keyring also backs | zenBTC's `DepositKeyringAddr` (live-confirmed, `zrchain.zenbtc.Query/QueryParams`) |

**Scoring.** `adminKeyScore`/`multisigScore` reuse the same bare-`(k,n)` ladder
already applied to Zcash's own `FUND`s and to `XVAULT`'s TSS vaults (`k=3` maxes
`adminKeyScore` at 65; `multisigScore = max(16, min(100, 20*3-(3-3))) = 60`).
`timelockScore` 0 (no on-chain delay on a completed dMPC signature, same ruling as
`FUND`/`XVAULT`; `x/policy` not checked, disclosed as an open item, not scored).
`oracleAuthorityScore` 100. `crossExposureScore` 100 (no OTHER target this Zcash
scorer tracks shares this key space; the zenBTC overlap is disclosed in the scorer's
notes, not scored against this dimension, per METHODOLOGY.md 4.4's "counted once"
discipline). `l1CappedComposite` not computed (off-Zcash authority, same reasoning as
`EXT`/`XVAULT`). `compositeScore = floor(0.4*65+0.3*60+0.3*0+0.5) = 44`.

**What is still NOT determined, disclosed rather than glossed over.** The literal
Zcash-side address(es) holding the real ~494.51-zenZEC-equivalent of native ZEC today
were not found: this is a genuine limitation of Zenrock's own per-deposit key model
(no small enumerable vault set, unlike Maya), not a gap this pass could close by
trying harder with the tools available. The keyring's own party identities were not
traced to named real-world operators, and `rpc.diamond.zenrocklabs.io` is a SINGLE,
~40-day-stale source (its own `/status` shows 0 p2p peers) -- the second RPC operator
the Cosmos chain-registry lists (`rpc.zenrock.nodestake.org`) refused every
connection this pass. A keyring's threshold is also a MUTABLE governance parameter,
unlike a Zcash P2SH script's `HASH160` commitment, so today's reading could already be
stale in a way no `FUND` in this project ever is.

## Bug fixed this pass

`scripts/zcash_read.py`'s `taddr_balance()` raised `StopIteration` instead of
returning 0 for a genuinely empty address (lightwalletd omits `valueZat` on the wire
when it is exactly 0) -- hit live while checking the two zenZEC infra addresses
above, both of which are legitimately empty. Also affects `score_maya_asgard_vault()`
(same function, direct call) -- fixed for both.

## Reproduction

```bash
python3 -c "
import sys; sys.path.insert(0, 'chains/zcash')
from scorers import score_all
for r in score_all():
    print(r['target'], r['label'], r['compositeScore'], r.get('l1CappedComposite'))
"
```

Runs in a few minutes: the existing `L1`/`FUND`/`EXT`/`XVAULT` reads plus one
`zrchain.identity.Query/KeyringByAddress` ABCI query, two
`zrchain.treasury.Query/KeyByID` ABCI queries, and 4 `GetTaddressBalance` calls (2
addresses x 2 lightwalletd operators) for the new `MPCKEYRING` target.
