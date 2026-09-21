# Correction (2026-09-17, evening run): testnet oracle still served the pre-revision L1 rollup authority score (60, not 57)

## Context

Commit `064a30d` (same day, afternoon) revised Robinhood Chain's own L1 rollup
authority score from 60 to 57/100 in `scripts/lib/scorers.py::score_rollup_l1_authority()`
and in `README.md`, after a cross-Safe signer-overlap finding was wired in. That
commit did not push the revised score on-chain. This is the same failure shape
as `data/correction_2026-09-17-uniswap-testnet-oracle-sync.md`: code and docs
right, the published on-chain value stale.

## What the evening maintenance run found

`getScore()` on the testnet oracle (`0x9BF45734D09bC7CA39238e767B2af9AAc62a7f52`,
Robinhood Chain Testnet, chain 46630) for all 6 rollup-authority targets still
returned the pre-revision tuple:

| Field | Served on-chain before this run | Re-derived this run |
|---|---|---|
| adminKeyScore | 78 | 78 |
| multisigScore | 75 | 75 |
| timelockScore | **20** | **10** |
| oracleAuthorityScore | 100 | 100 |
| crossExposureScore | 100 | 100 |
| compositeScore | **60** | **57** |
| lastUpdated | 1789572321 (2026-09-16T15:25:21Z) | this run's push |

Targets: Rollup `0x23A19d23e89166adedbDcB432518AB01e4272D94`, SequencerInbox
`0xBd0D173EEb87D57A09521c24388a12789F33ba96`, CoreProxyAdmin
`0x1232813BDd40aa9d53066A880dE78a4Be70B90FD`, DelayedInbox
`0x1A07cc4BD17E0118BdB54D70990D2158AbAD7a2D`, Bridge
`0xDf8755334ce7A73cCF6b581C02eA649AE3E864b3`, Outbox
`0xf0ce991ea4A0d2400A4AB49b20ae333f6Dce3DE9`.

## Independent re-derivation (not read from scorers.py output)

All read with `cast call` against `https://ethereum-rpc.publicnode.com`, a
different RPC from the one `scorers.py` uses (`gateway.tenderly.co`), and the
two Safe owner lists re-read a second time on `https://eth.drpc.org` (identical).

| Check | Result |
|---|---|
| `CoreProxyAdmin.owner()` and Rollup EIP-1967 admin slot | both UpgradeExecutor `0x552603b4bc1f5E896AF2854548D6380f45f1B4bf` |
| `UpgradeExecutor.hasRole(EXECUTOR_ROLE, ...)` | Security Council Safe `0x7Ae50886...84b6` = true, L1 Timelock `0xE1e825D1...F465` = true |
| Security Council Safe | 7-of-8 |
| `Timelock.getMinDelay()` | 604,800s (7 days) |
| `Timelock.hasRole(PROPOSER_ROLE / CANCELLER_ROLE, 0xbFc2b535...A1d)` | true / true (Security Council Safe itself: false / false) |
| Proposer/Canceller Safe `0xbFc2b535...A1d` | 6-of-8 |
| Owner intersection of the two Safes | 6 of 8 identical addresses (75%) |

Applying the grid already in `scorers.py` (proposer == canceller gives 20,
capped to 10 when at least half of the Proposer/Canceller Safe's signers also
sit on the Security Council): composite = `floor(0.4*78 + 0.3*75 + 0.3*10 + 0.5)`
= 57. `scripts/update_scores.py --dry-run` gives the same (78, 75, 10, 100, 100, 57)
for all 6.

## What changed

- Pushed the 6 corrected entries to the testnet oracle in one `updateScores()`
  call restricted to those 6 addresses plus this run's single new batch-11
  target (`data/scored_targets_2026-09-17-batch11.md`). No other tracked target
  was touched. The push used a run-local helper outside the repo that calls
  this repo's own `score_rollup_l1_authority()` / `compute_cross_exposure()`
  and refuses to send if the live re-derivation differs from the hand audit
  above. Transaction `0x173db78bd97b89f94e7f6af6e9cf56055491412d612f3713883bffa8cf54f27c`
  (testnet block 120879100, status 1); its decoded `targets` array is exactly those 7 addresses.
  `getScore()` re-read afterwards returns (78, 75, 10, 100, 100, 57) for the 6 rollup targets.
- `scripts/lib/scorers.py`: `score_all()`'s inline comment still said the L1
  authority was "currently 60/100"; updated to 57 with a pointer here.

## Rotation audits in the same run that found NO divergence

| Index | Target | Published | Re-derived from scratch | Notes |
|---|---|---|---|---|
| 3 | Lighter Escrow proxy `0x94bAB9693Ba2f6358507eFfcbd372b0660AFfF9d` | (75, 65, 15, 100, 100, 54) | same | EIP-1967 admin slot = UpgradeGatekeeper `0x43CfF77C...2716`, `getMaster()` = 3-of-5 Safe v1.4.1 (no modules, no guard), `approvedUpgradeNoticePeriod()` = 1,814,400s, `securityCouncilAddress()` = `0x4972E0Ca...eFDb` with no code. The escrow is `managedContracts(2)` of that gatekeeper. Gatekeeper source re-read from Sourcify (exact match): `cutUpgradeNoticePeriod(uint256)` zeroes the notice period once an upgrade has started, gated only by `msg.sender == securityCouncilAddress`; its selector `0x389b8b3a` is present in the deployed bytecode. The source's own comment says the council "could be a multi signature wallet"; on-chain it is not. |
| 4 | UniswapX V3DutchOrderReactor `0x000000007A1C8e570011EeDF86A2A35593013cBA` | (80, 100, 75, 100, 100, 85) | same | `owner()` = `0x2BAD8182...46CD`, recomputed Arbitrum L1-to-L2 alias of Uniswap's L1 Timelock `0x1a9C8182...35BC` (no code on Robinhood Chain). On L1: `delay()` = 172,800s, `admin()` = GovernorBravo `0x408ED635...24C3`, whose `timelock()` points back to the same Timelock, `quorumVotes()` = 40M UNI. crossExposure 100 is by design: the 4 Uniswap surfaces are one group in `signer_overlap.py`. |
