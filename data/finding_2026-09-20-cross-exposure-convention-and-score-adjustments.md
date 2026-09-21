# Finding (2026-09-20): crossExposureScore now folds cross-ecosystem overlaps on every EVM ecosystem, and 11 scorer outputs moved

Status: decided and implemented in the scorers on 2026-09-20 (commit `042f805`), and
**pushed on-chain the same day** (section 9: six transactions, all status 1, read back with
`getScore()` on all 7 oracles with 0 differences). This file was first written before the
push, when the deployed testnet oracles still held the "Old" values in section 4 (read live,
section 6); those are now history, and every "New" value in section 4 is the on-chain value.

## 1. The question

Two conventions for `crossExposureScore` coexisted, and nobody had chosen between them:

- Arbitrum, Base, Monad and Plasma (for its Aave and Ethena targets only) **folded** a
  cross-ecosystem overlap into the score (a committee identical to a tracked target on
  another chain scored 80).
- Ethereum L1, Robinhood Chain and Tempo kept the same kind of overlap **out of the score**
  (disclosed in a scorer note or only in a finding file) and published 100, so their
  `crossExposureScore` meant "within this ecosystem" only.

The same committee therefore had a different number depending on the chain a consumer
happened to read. The 9-signer Aave `PayloadsController.guardian()` committee scored 80 on
Arbitrum, Base, Plasma and Monad and 100 on Ethereum L1. The 9 Morpho Association signers
scored 80 on Base and 100 on Ethereum L1, Robinhood Chain and Tempo. The open question was
recorded in `data/finding_2026-09-19-aave-guardian-ethereum-l1-fifth-chain-and-verifier-corrections.md`
section 1 and left for the maintainer.

## 2. Decision and rationale

**Cross-ecosystem overlaps are folded into `crossExposureScore`, on every EVM ecosystem.**

The field's documented meaning is "100 = no root signer shared with any other tracked
target" (the comment on the field in `src/AuthorityRiskOracle.sol`, and `METHODOLOGY.md`).
"Any other tracked target" is not limited to the same chain, and this project's own thesis
(the SolGov comparison in `README.md`) is that a key shared across chains is the finding a
per-chain tool cannot make. A field whose meaning changes with the chain is not something a
consumer contract can gate on. Folding everywhere makes the number mean one thing;
note-only everywhere would have kept a real, already-found shared-key risk out of the score.

## 3. The exact rule

- **Value.** A target whose root committee is identical to the committee of a tracked target
  on ANOTHER ecosystem scores a flat **80**. Otherwise the within-ecosystem value stands
  (100 when nothing overlaps). The 80 is flat: it does not fall further with the number of
  chains that share the committee (the Aave 9-signer committee is on 5 chains and reads 80),
  so the number says "shared", and the notes and the sweep script say "how widely".
- **Never raises.** On the three ecosystems changed today (Ethereum L1, Robinhood Chain,
  Tempo) the fold is `min(within-ecosystem score, 80)`, so a target already lowered by an
  in-ecosystem overlap keeps the lower value (the Robinhood Steakhouse and Morpho vault
  groups stay at 40). On Ethereum L1 the Aave Pool matches two cross-chain committees (the
  9-signer `PayloadsController.guardian()` Safe and the 7-signer `PROTOCOL_GUARDIAN` Safe);
  the cap is applied once, giving 80, not 60.
- **Dated snapshot, no second-chain RPC.** A scorer compares the owner set it just read on
  its own chain against a hardcoded snapshot of the other chain's committee, dated in the
  constant's name (for example `_KNOWN_AAVE_PROTOCOL_GUARDIAN_OWNERS_2026_09_20`,
  `_KNOWN_MORPHO_BLUE_OWNERS_2026_09_20`, `_KNOWN_PENDLE_ROBINHOOD_SAFE_OWNERS_2026_09_20`).
  This is the idiom the Aave guardian scorers already used; it avoids coupling one chain's
  push to another chain's RPC.
- **"Identical" is strict.** Exact owner-set equality (the Safe address and threshold may
  differ), with three disclosed shapes: Monad's Steakhouse Morpho vault accepts containment
  (subset), Monad's Curve factory needs the same factory address and admin EOA, and
  Robinhood Chain has no cross-ecosystem comparison in code, only a hand-set dated
  `cross_ecosystem` flag on the group in `scripts/lib/signer_overlap.py`.
- **Where it lives in code.** Ethereum L1: an internal `_crossEcosystem` flag read by
  `_apply_cross_exposure()`. Robinhood Chain: the optional `cross_ecosystem` key on `GROUPS`
  (a flagged group scores `min(within-Robinhood, 80)`, and the reason now reaches
  `api/scores.json` through `compute_cross_exposure_with_notes()`). Tempo: `cross_exposure()`
  compares the target's signer set with the Morpho committee snapshot. Plasma: a snapshot
  helper for Pendle (Robinhood Chain's Pendle Safe owners) and Euler (Monad's Euler DAO
  signers).

## 4. What moved (old on-chain value, then new value, now on-chain)

Fields are admin / multisig / timelock / oracle / **cross** / composite. Old values were read
from each testnet oracle with `getScore()` on 2026-09-20, before the push. The "New" column
was the scorer output when this table was written and is the on-chain value since the push
(section 9).

| Oracle | Target | Old (on-chain before the push) | New (scorer, then on-chain) | Why |
|---|---|---|---|---|
| Arbitrum | Radiant V2 LendingPool `0xE23B4AE3...6886` | 55/100/55/100/100/69 | 65/95/0/100/100/**55** | Pool-admin Safe path found and scored (section 5) |
| Monad | Aave V3 Pool `0x34793Fb9...A615` | 65/100/50/100/80/71 | 65/**75**/**0**/100/80/**49** | `PROTOCOL_GUARDIAN` Safe also holds `POOL_ADMIN` (section 5) |
| Ethereum L1 | Aave V3 Pool `0x2f39d218...4E9e` | 78/100/55/100/100/78 | 78/100/55/100/**80**/78 | Both Aave committees also sit on other chains |
| Ethereum L1 | Morpho Blue `0xBBBBBbbB...FFCb` | 65/95/0/100/100/55 | 65/95/0/100/**80**/55 | Same 9 Morpho Association signers as Base, Robinhood Chain, Tempo |
| Robinhood Chain | Pendle V2 `0x544BF81c...EeE2` | 70/45/0/100/100/42 | 70/45/0/100/**80**/42 | Same Safe address and 5 owners as Plasma's Pendle |
| Robinhood Chain | Curve DEX `0x8271e06E...E8aD` | 2/0/0/100/100/1 | 2/0/0/100/**80**/1 | Same bare EOA `0xabc336d4...1cbF` and factory address as Monad's Curve |
| Robinhood Chain | Morpho Blue `0x9D53d5E3...1010` | 65/95/0/100/100/55 | 65/95/0/100/**80**/55 | Same 9 signers as Ethereum L1, Base, Tempo |
| Plasma | Pendle Router + Market Factory V6 `0x88888888...F946` | 65/55/0/100/100/43 | 65/55/0/100/**80**/43 | Same Safe `0x7877AdFa...75Ac` and owners as Robinhood Chain's Pendle |
| Plasma | Euler V2 eVaultFactory `0x42388213...EeA3` | 70/80/68/100/100/72 | 70/80/68/100/**80**/72 | DAO Safe (8 signers) identical to Monad's Euler DAO signer snapshot of 2026-09-19 |
| Plasma | Euler V2 AccessControlEmergencyGovernor `0x9b3CeB22...Da2c` | 68/80/55/100/100/68 | 68/80/55/100/**80**/68 | Same DAO Safe signers |
| Tempo | Morpho Blue core `0x10EE9AAC...8f97` | 65/96/0/100/100/55 | 65/96/0/100/**80**/55 | 9 owners equal the Ethereum L1, Base, Robinhood Chain Morpho Safe owners (the Safe address differs, so the snapshot holds owners, not an address) |

Nine rows change only `crossExposureScore`, and no composite moves for them (it is not a
composite input). Two rows change the score model. Base is unchanged. Every other target on
every ecosystem is unchanged, re-run live per chain. The same push also carried the Ethereum
L1 Ethena change (a new target, the live minter, and a retired old one), which is not one of
these 11 rows; see section 9 and `data/finding_2026-09-20-ethena-live-minter.md`.

## 5. The two score-model changes behind rows 1 and 2

These came from `data/finding_2026-09-20-unscored-role-sweep.md` (sections 1 and 3), where
the maintainer decision they needed is now made.

**Radiant (Arbitrum).** The scorer credited only `PoolAddressesProvider.owner()`, a 72h
`TimelockController` (`0x27fC8f3B...Aff92`, `getMinDelay()` 259200). The
`LendingPoolConfigurator`'s `onlyPoolAdmin` functions (token-proxy upgrades, freeze, caps,
rate strategy) are gated by `getPoolAdmin()` instead, `0x111CEEee040739fD91D29C34C33E6B3E112F2177`,
a 4-of-11 Safe. That Safe holds PROPOSER and CANCELLER on the timelock and 6 of its 11 owners
hold EXECUTOR (read live 2026-09-20), but the timelock does not bind the pool-admin path, so it is
scored as a Safe with no timelock: admin 65 (threshold >= 3), multisig
`min(100, 4*15 + 7*5)` = 95, timelock 0. The timelock still gates the provider-level owner
functions, which the note discloses. `getEmergencyAdmin()` (`0xDdF60973...0928`) is a 1-of-5
Safe whose 5 owners are all owners of the 4-of-11; it can only pause, so it is disclosed and
not scored. An unread pool admin or provider owner degrades to 20/0/0 instead of keeping a
confident score. `crossExposureScore` stays 100: the pool-admin and emergency-admin owner
sets were compared with 70 root-signer groups on 7 ecosystems and none matched, which is
"found none", not proof of none.

**Aave V3 (Monad).** The PROTOCOL_GUARDIAN Safe `0xc887455536CBD4e615B745e70CaCde15B3117e74`
(4-of-7, read live) holds `POOL_ADMIN` in the ACLManager `0xa9fEe192...3d95B` (`isPoolAdmin` and
`isEmergencyAdmin` both true, read live), so it acts with no timelock. Scored as a Safe with no
timelock: admin 65, multisig `min(100, 4*15 + 3*5)` = 75, timelock 0. The admin score is
`min(DAO-path score, Safe rule)`, so a broken Executor loop is never raised. If
`isPoolAdmin` reads false the scorer returns the previous 65/100/50 (71); if it cannot be read
it degrades to 20/20/0 (14) with a DEGRADED note. `crossExposureScore` stays 80 (the 9-signer
guardian committee).

Two more changes the same day touched notes only, no score: Plasma's Pendle scorer read
storage slot 0 as the "EIP-1967 admin slot" and so always printed "NOT independently confirmed
to converge"; it now reads the canonical slot (`0xb53127...6103`), which resolves live to
ProxyAdmin `0xA28c08f1...` whose `owner()` is the Safe `0x7877...`. Tempo's `score_all()`
used to overwrite each entry's notes and now merges them, so the cross-chain finding on the
Morpho core is kept next to `chainCappedComposite`.

## 6. How each was verified

- **New values.** Each affected scorer was re-run live, read-only, on public RPCs on
  2026-09-20 (Arbitrum One, Monad, Ethereum mainnet, Plasma, Tempo, Robinhood Chain). All 11
  rows above matched, including the Radiant and Monad Aave role reads and thresholds. On
  Robinhood Chain the run used `score_all(skip_slow=True)`, which does not include the four
  slow event-replay scorers, none of which is among the three affected targets.
- **Old values.** Read with `getScore()` (plain `eth_call`, no key, no transaction) from each
  deployed testnet oracle the same day, before the push.
- **After the push.** Read back with plain `getScore()` on all 7 oracles: see section 9.
- **Tests.** `scripts.lib.tests.test_cross_ecosystem_overlap` and
  `scripts.lib.tests.test_cross_ecosystem_fixes` pass (29 tests). The full
  `scripts/lib/tests` suite ran 1031 tests with 3 failures, all Zcash tests that re-sign with an
  out-of-repo Testnet key and compare public keys; none touches a scorer or this change.
  Signer-overlap flag behaviour has its own cases in `test_signer_overlap.py`.

## 7. What is NOT done (and what has since been done)

- **Done since this file was first written: the testnet oracles were re-pushed.** The first
  version of this section said they had not been, that `getScore()` still returned the "Old"
  column and that the docs called the new values "scorer output". That was true until the
  push and is not true now: see section 9 for the six transactions and the read-back. The
  dashboard, which reads the oracles directly, shows the new values, and the Robinhood Chain
  snapshot in `api/scores.json` was regenerated by the push script with the transaction hash
  and block in section 9. Base was not part of the push because no Base score changed.
- **No new chain or signer group was added.** (One new target was added by the push, the Ethena
  live minter on Ethereum L1, but that is a scored-contract correction, not part of the
  cross-exposure decision.) In particular Radiant's two Safes were
  not added to `scripts/lib/cross_ecosystem_overlap.py`, so the sweep script does not yet
  re-check them (the comment at that spot says so).
- The comment on the field in `src/AuthorityRiskOracle.sol` still describes only the
  within-set rule; it was not edited by this pass.

## 8. Residual gaps

- **Snapshots go stale.** A committee rotation on the other chain leaves a scorer's snapshot,
  or Robinhood Chain's hand-set flag, wrong: a stale 80 can outlive the overlap and a new
  overlap can go unflagged. Only `scripts/check_cross_ecosystem_overlap.py` and the drift audit
  catch it, when re-run. Nothing re-runs the comparison live against the other chain, by design.
- **A scorer folds only the committees it holds a snapshot of.** An overlap the sweep finds
  but nobody wires into a scorer stays out of the score.
- **One deviation from a flat 80.** The older Arbitrum scorers deduct 20 per matching snapshot,
  so Arbitrum's Pendle (the same Safe is tracked on Plasma and on Robinhood Chain) reads 60,
  while the same committee reads 80 on Plasma and Robinhood Chain. Base also deducts 20 per
  overlap inside Base on top of a cross-ecosystem 80. Not changed today.
  **Closed 2026-09-21 for Arbitrum:** its Pendle now reads the flat 80 (composite unchanged, 43);
  Base's intra-Base deduction stays.
- **The three non-EVM ecosystems are not covered.** Solana, Hyperliquid and Zcash are not in the
  sweep (Solana and Zcash signer formats are not comparable to EVM addresses without a bridge;
  Hyperliquid's signer sets were never added to the registry). Tempo IS EVM-signer: its two
  resolvable Safes are in the sweep and its Morpho core now folds at 80, but its LayerZero
  OneSig and Chainlink MCMS controllers are not Gnosis Safes and are not comparable yet.
  "Not covered" is a gap, not a clean result.

## 9. Pushed on-chain 2026-09-20

The maintainer ran the re-push scripts on 2026-09-20, roughly 02:15 to 02:40 Paris time. Six
oracle writes landed and every transaction has status 1:

| Oracle | Oracle address | Transaction | Block |
|---|---|---|---|
| Ethereum L1 (Sepolia) | `0xB6F8474ccC71AF477c31c2DF663B3942ddfbf906` | `0x14b0466ab52a7bf6cab54253cda92c73d52ca1b88957632911d79136b99b7a98` | 11,740,952 |
| Arbitrum (Sepolia) | `0x50840a76...8720` | `0x308ad2c8fa527a0e5c30139b6b154ff48462cd046df9840a17f25775c21fbd23` | 310,697,409 |
| Plasma testnet | `0x50840a76...8720` | `0xa2e8f4f12ccbe3740734bccfa5ee9cf4c20018f5a453a38c00e77a8583cb3de4` | 34,034,832 |
| Monad testnet | `0x50840a76...8720` | `0xa93596300b689383572880cd4de76ee2fc7bce68ac5791db38501b07b987a019` | 64,022,942 |
| Tempo Moderato | `0x50840a76...8720` | `0xcdc3cc092d5e641de9407484a929ab40732799e0ae043f9fdea8d7ef400aa44b` | 36,054,236 |
| Robinhood Chain testnet | `0x9BF45734...7f52` | `0x020cf83c8a007afaef0eadf7ecb271432c80f1ffd9bfafed984ab6eca17c4978` | 121,858,777 |

Base was NOT re-pushed: no Base score changed. `api/scores.json` (the Robinhood Chain snapshot)
was regenerated by the push script with the Robinhood transaction hash and block above.

**What each write put on-chain.** The 11 rows of section 4, exactly as their "New" column
(Radiant 65/95/0/100/100/55 on Arbitrum; Aave V3 Monad 65/75/0/100/80/49; on Ethereum L1 Aave V3
78/100/55/100/80/78 and Morpho Blue 65/95/0/100/80/55; on Plasma cross 80 for Pendle, the Euler
eVaultFactory and the Euler AccessControlEmergencyGovernor; Tempo's Morpho Blue core
65/96/0/100/80/55; on Robinhood Chain cross 80 for Pendle V2, Curve DEX and Morpho Blue, composites
unchanged), plus one change that is not among the 11: Ethereum L1 gained a new target, index 14,
**Ethena EthenaMinting (USDe live minter)** `0xe3490297a08d6fC8Da46Edb7B6142E4F461b62D3`,
scored 65/100/55/100/20/73. What was wrong with the old target, the verified authority and the
scoring reasons are in `data/finding_2026-09-20-ethena-live-minter.md`.

**The retired Ethena target stays on the oracle.** Index 3 (`0x2CC440b721d2CaFd6D64908D6d8C4aCC57F8Afc3`,
55/100/0/100/20/52) is no longer refreshed. The oracle contract has no removal function, so the entry
stays as a historical reading and turns stale (`isStale` true) nine days after its last update,
which was the 2026-09-19 push (16:39 UTC), that is after 2026-09-28 16:39 UTC. Until then a raw
`getScore()` on it still returns a normal-looking, not-stale score for a contract that has not been
USDe's minter since 2024-07-08. Ethereum L1 therefore has 15 tracked targets of which 14 are
actively refreshed.

**Read-back.** After the six writes, plain `getScore()` (no key, no transaction) was read on all 7
oracles. Every oracle equals the scorer output of commit `042f805` exactly: 0 differences across
Ethereum L1 (14 of 14 refreshed targets), Arbitrum (9), Plasma (9), Monad (9), Tempo (14) and
Robinhood Chain (58); Base is unchanged. Re-read once more for this write-up on 2026-09-20 at
about 02:46 CEST: Ethereum L1 Ethena live minter 65/100/55/100/20/73, Aave V3 78/100/55/100/80/78,
Morpho Blue 65/95/0/100/80/55 (all three `lastUpdated` 2026-09-20 00:16:38 UTC) and Arbitrum Radiant
65/95/0/100/100/55 (`lastUpdated` 00:17:34 UTC), matching the scorer.

**Tracked-target counts after the push** (`python3 scripts/live_target_counts.py`, plain
`eth_call`): Robinhood Chain 58, Ethereum L1 15, Arbitrum 9, Base 9, Tempo 14, Plasma 9, Monad 9,
a total of **123 tracked targets on 7 oracles**, of which **122 are actively refreshed** (the
retired L1 index 3 is the difference; the script prints the 123 and does not subtract it).
