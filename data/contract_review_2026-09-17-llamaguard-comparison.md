# Contract review against the LlamaGuard PT pattern (2026-09-17)

Item 9 of the after-hackathon roadmap: "the entire pitch is 'we flag who has
too much unchecked power' -- so this project's own contract should adopt the
LlamaGuard pattern first." This is that review.

## The reference pattern (LlamaRisk's actual deployed model on Aave)

Per this project's own earlier research (`BUSINESS.md`): Aave governance owns
every contract; LlamaRisk holds only a scoped "Updater" role on an on-chain
ParameterRegistry, able to tune specific parameters but never redeploy or
override; every update passes on-chain-enforced caps (capped step size,
deviation gates, minimum delay between updates, range validation) set by
governance, not by the updater; a separate `DEFAULT_ADMIN_ROLE`
(governance-held) can change those bounds; every change is an on-chain event.

## `src/AuthorityRiskOracle.sol`, checked against each element

| LlamaGuard element | This contract, before this pass | Verdict |
|---|---|---|
| Governance owns the contract, updater has a scoped role | `AccessControl`-based, `DEFAULT_ADMIN_ROLE`/`UPDATER_ROLE` separation exists in the contract's own design | Structurally present |
| Every update is an on-chain event | `ScoreUpdated`/`MaxStalenessUpdated` emitted on every write | Present |
| Range validation on pushed values | **Nothing** -- a `uint8` is only bounded to 0-255 by the type system; nothing enforced the documented 0-100 range | **Gap, fixed this pass** |
| Deviation gates / minimum delay between updates | Not present | **Gap, not fixed this pass** (see below) |
| Admin and Updater held by different parties | `script/Deploy.s.sol`'s own comment: "admin/updater = the deploying key for the hackathon MVP" -- both roles granted to the same address at deployment | **Already disclosed** (README's own "Next" section: migrate `UPDATER_ROLE` to a real multisig before mainnet) -- not a new finding, not re-fixed here |

## Fixed this pass: on-chain score-range validation

`_updateScore()` now reverts with `ScoreOutOfRange(target, compositeScore)` if
any of the five sub-scores exceeds 100. This isn't a hypothetical hardening --
**`ExampleConsumer.sol`'s own `collateralFactorBps()` has a real, exploitable
bug without it**: it computes `scoreAboveMin = score.compositeScore -
MIN_SAFE_SCORE` and scales that into a basis-points collateral factor assuming
`compositeScore <= 100`. A pushed value of 255 (a bug in the off-chain
scorer, or a compromised `UPDATER_ROLE` key) would compute a collateral
factor of **~196%**, nearly 2.5x the contract's own documented maximum of
80%. This is a real bug in the reference consumer contract this project
ships, not an abstract worry.

**Verified this pass** (Foundry isn't installed in this environment, so
`forge test` itself could not be run -- disclosed rather than skipped):
compiled both `src/AuthorityRiskOracle.sol` and `src/ExampleConsumer.sol`,
plus the updated `test/AuthorityRiskOracle.t.sol` (5 new tests:
`compositeScore` alone out of range, any sub-score out of range even when
`compositeScore` itself is valid, exactly 100 is accepted, a batch reverts
entirely -- not partially -- if any single entry is out of range), via
`solc 0.8.24` (the exact version this project's `foundry.toml` targets)
using the correct `@openzeppelin/contracts/=lib/openzeppelin-contracts/contracts/`
and `forge-std/=lib/forge-std/src/` remappings. **Zero errors, zero
warnings**, ABI correctly includes the new `ScoreOutOfRange` error with its
`(address, uint8)` parameters. This confirms the code is syntactically and
type-correct against the real dependency tree, not just eyeballed -- but it
is NOT the same guarantee as `forge test` actually executing the 5 new
assertions against the EVM and confirming they pass. **Before deploying
this, run `forge test` in an environment with Foundry installed** -- this
is flagged as the explicit remaining verification step, not silently
assumed to be equivalent to a compile check.

## NOT fixed this pass, and why

- **Deviation gates / minimum delay between updates**: LlamaGuard's pattern
  caps how much a single update can move a parameter and enforces a minimum
  time between updates. This project's off-chain pipeline already has an
  analogous check at the DATA layer (`scripts/lib/alerts.py`'s
  `diff_alerts()`, `DROP_THRESHOLD = 10` points), but nothing prevents the
  UPDATER_ROLE key itself from pushing an arbitrary jump on-chain if that
  off-chain layer were bypassed or compromised. Left open: this needs a
  real design decision (how much deviation is legitimate -- a genuine
  signer rotation can legitimately drop a score by 60+ points in one
  update, so a naive cap would break correct behavior, not just attacks),
  not a number invented this pass without that judgment call.
- **Admin/Updater role separation, migrating to a real multisig**: already
  disclosed in README as the explicit "Next" step before mainnet, not
  re-litigated here. Doing it now on the testnet deployment would need a
  redeploy (new address, re-populate all 42 scores) for a role-separation
  concern that only matters once real value is at stake -- deferred to the
  mainnet migration itself, where it was already planned.

## What's explicitly out of scope for this repo/session

Item 9 also named a legal entity and a paid/contest-style audit as
prerequisites for a real paid mandate. Both are real-world actions
(registering a business entity, commissioning and paying for external
review) that need Spap's own identity, banking, and judgment -- not
something a coding session can do on his behalf. The market-reference data
already gathered this pass (`BUSINESS.md`'s "Path to a real product",
and the earlier `productization-path` research: boutique audits run
$8K-$25K for a narrow single-contract scope) stands as the input for that
decision whenever he's ready to make it.

## Deployment status

**Not deployed.** This is a source-code change only -- the currently-live
testnet oracle at the address in `README.md`'s "Status" section still runs
the pre-this-pass contract. Deploying the fixed version needs: (1) `forge
test` passing in a Foundry-enabled environment (not verified this pass, see
above), (2) a decision on whether to redeploy now (a new contract address,
requiring every doc/dashboard/submission reference to be updated, and a
fresh weekly push to re-populate all scores) or bundle this fix into the
already-planned mainnet migration.
