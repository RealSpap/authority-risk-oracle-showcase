# Zcash -- scored targets, 2026-09-17

**Different in kind from this project's other three 2026-09-17 promotions
(Solana, Hyperliquid, Tempo)**: those each reused a numeric mapping already
written and tested a day earlier. Zcash's [`METHODOLOGY.md`](../METHODOLOGY.md)
had qualitative rules (sections 4.1-4.5) but no 0-100 formulas -- section
4.6 and [`scorers.py`](../scorers.py) are the methodology-test step and the
promotion done together in this one pass, not a promotion of prior-day work.

## Summary table

| Target | Key | adminKey | multisig | timelock | oracleAuthority | crossExposure | composite | l1CappedComposite |
|---|---|---|---|---|---|---|---|---|
| Zcash L1 (consensus-rule-change authority) | `0xB8e62E6AeB4C400b6F3e66cAb69ACe55439035c3` (synthetic, `keccak256("zcash:mainnet:l1")` per METHODOLOGY.md section 4 target types -- no address controls it) | 20 | 50 | 35 | 100 | 100 | **34** | n/a (this IS the baseline) |
| ZIP 271 one-time lockbox disbursement | `t3ev37Q2uL1sfTsiJQJiWJoFzQpDhmnUwYo` | 50 | 39 | 0 | 100 | 100 | **32** | **32** |
| ZCG funding stream (FS_FPF_ZCG_H3) | `t3cFfPt1Bcvgez9ZbMBFWeZsskxTkPzGCow` | 50 | 39 | 0 | 100 | 100 | **32** | **32** |
| `zec.omft.near` (NEAR PoA bridge, `EXT`, added 2026-09-17) | `zec.omft.near` | 5 | 18 | 0 | 100 | 100 | **7** | n/a (off-Zcash authority, see below) |

### zec.omft.near -- resolved same day, lowest score of any Zcash target

METHODOLOGY.md section 8 left this open ("Identify the NEAR contract that
controls zec.omft.near minting and its signer set"). Resolved by reading
`github.com/near/intents`'s `contracts/poa/factory/src/contract.rs`: the
factory contract (`omft.near`) gates minting (`ft_deposit`) behind a
`near_plugins` access-control role, live-read and cross-checked against a
second NEAR RPC (`free.rpc.fastnear.com` alongside `rpc.mainnet.near.org`,
raises on disagreement -- same hard cross-RPC requirement as Tempo's
`call2()`):

- `Role::TokenDepositer` (mint-capable): `bridge-mng.near`, a bare NEAR
  account confirmed to hold exactly ONE full-access key (k=1, n=1) -- and
  `int-mnt-dao.sputnik-dao.near`, a Sputnik DAO whose "Requestor" role (the
  group that can both propose AND execute a mint call) has only 3 members
  with `threshold=1, quorum=0` -- a single vote from any ONE of those 3
  passes a call proposal outright. Structurally a 1-of-3, not a real
  majority-vote DAO for this action.
- By this project's weakest-key ordering (equal k=1, larger n=3 is
  weaker), the DAO's 1-of-3 Requestor group is the binding constraint, not
  the single bare key -- `adminKeyScore=5`, `multisigScore=18` (same
  `admin_key_score_kn`/`multisig_score_kn` ladder already used for the two
  Zcash funds above).
- Disclosed for contrast, not driving the score: the factory's OTHER
  mint-capable role, `Role::DAO`, is held solely by a DIFFERENT, genuinely
  strong Sputnik DAO (`intents.sputnik-dao.near`, 5-member council,
  `threshold=[79,100]`, i.e. 79%) -- but day-to-day minting does not have
  to go through it, since `TokenDepositer` is an independent, weaker OR
  path.
- `l1CappedComposite` deliberately NOT computed for this target: the cap
  models whether a Zcash rule change could override the target's own
  authority, which does not apply here -- this bridge's mint authority is
  entirely off-Zcash.

## What is live-verified every run versus a dated judgment call

Live, re-derived on every run:
- Each fund's current `(m, n)` threshold and full signer pubkeys, decoded
  from the most recent real spend's revealed redeem script -- cross-checked
  against a second, independent lightwalletd operator
  (`zcash.mysideoftheweb.com:9067` alongside `zec.rocks:443`), which must
  agree exactly or the scorer degrades rather than trusting one source.
- Signer-pubkey disjointness between the two funds (`crossExposureScore`) --
  a fresh set comparison, not carried over from METHODOLOGY.md 3.2's prior
  finding.
- Coinbase payout concentration (`k50`/`k25` feeding the L1's
  `multisigScore`) over the 2,000 blocks ending 10 below the lower tip of
  two lightwalletd operators, which must agree (tip-relative since the
  2026-09-17 second-run methodology test; before that the window was frozen
  at 3,483,700-3,485,699). Payout addresses are an upper bound on entities,
  so this input is an upper bound.
- That Zebra and (a version of) Zakura are both still observed answering on
  `eu.zec.rocks:443` (12 live samples).

Dated, disclosed judgment calls, NOT re-derived every run (documented in
`scorers.py`'s own docstrings, with the reasoning for each):
- Whether Zakura counts as an INDEPENDENT lineage or a fork of Zebra (it is
  scored as a fork, per METHODOLOGY.md 3.1's primary-source read of its
  README and Cargo.toml) -- a live version-string read can only confirm
  Zakura is still running, not whether the fork relationship still holds.
- The 23.8-day median scheduled-upgrade notice period (would need
  re-scanning historical GitHub release data and block headers to
  re-derive; only changes when a NEW upgrade activates).
- The emergency-bypass timelock cap (35, regardless of the measured median)
  -- reflects one disclosed historical precedent (the 2026-06 zero-notice
  emergency soft fork), not a live-recomputed penalty.
- The `L1` admin-key ladder itself (1 lineage -> 20, 2 -> 45, 3+ -> 65) --
  a first-pass calibration with only one live data point to test against
  today, written down for transparency and future-proofing rather than
  presented as mechanically derived (same convention Hyperliquid/Tempo's L1
  formulas already used for their own untested higher bands).

## What this does NOT cover yet

- `POOL` targets (Sapling/Orchard/Ironwood shielded value pools) are
  DELIBERATELY, PERMANENTLY not given a 0-100 score -- not a placeholder
  gap. See
  [`data/pool_trusted_setup_disclosure_2026-09-17.md`](pool_trusted_setup_disclosure_2026-09-17.md):
  the setup-risk framing METHODOLOGY.md 4.1 describes rests on an
  unfalsifiable historical-trust question (was at least one Sprout/Sapling
  MPC ceremony participant honest) that no live read can ever confirm,
  unlike every other score in this project.
- Testnet is explicitly out of scope for authority scoring (METHODOLOGY.md
  section 2: "Testnet uses separate funding-stream recipients... shows
  mechanics only, never Mainnet authority").

## Methodology test (2026-09-17, second run)

The ZIP 271 fund and the L1 concentration input were re-derived with an
independent reader and matched every published number above. The test
changed rules, not today's scores: unresolved P2SH thresholds now take the
ladder floor (5/16) instead of 20/20, script suffixes are validated, the
concentration window is tip-relative and two-operator. See
[`methodology_test_2026-09-17.md`](methodology_test_2026-09-17.md) and
METHODOLOGY.md 7.3.

## Reproduction

```
python3 -c "
import sys; sys.path.insert(0, 'chains/zcash')
from scorers import score_all
for r in score_all():
    print(r['target'], r['label'], r['compositeScore'], r.get('l1CappedComposite'))
"
```

Runs in under a minute: a 12-sample lineage check, a 2,000-block coinbase
scan, and a small number of `GetTaddressTxids` windows per fund (4 and
10,009 transactions scanned respectively for the two funds' full history
in the range already known to contain their real spends).
