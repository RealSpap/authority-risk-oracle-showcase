# Batch 10 (2026-09-17): Fables PoolRegistry, Beefy SPY-WETH vault

Scouted from DefiLlama's live Robinhood Chain protocol list
(`https://api.llama.fi/protocols`, filtered to `chains` containing
"Robinhood Chain"), re-checked against the same list already covered by
`README.md`'s Status table before picking a target -- 175 protocols listed,
most already covered directly or via a shared authority chain already
tracked (Uniswap stack, Morpho vaults, Longbow, Pendle, etc.).

Both targets below were already flagged as open, not-yet-explored leads on
the tracker before this run (Fables and Beefy), not newly discovered here --
this run resolved their previously-unlocated root authority.

## Fables PoolRegistry -- 2/100

| Field | Value |
|---|---|
| Target | `0x159a113E012593d9B3Cc63aD45e30F0467e13ef3` (FablesPoolRegistry) |
| TVL | ~$21.8M (DefiLlama `fables`, `chainTvls["Robinhood Chain"]`, live) |
| adminKeyScore | 5 |
| multisigScore | 0 |
| timelockScore | 0 |
| compositeScore | 2 |

Address source: DefiLlama's own official TVL adapter for this protocol
(`DefiLlama-Adapters/projects/fables/index.js`, `REGISTRY` constant) --
cross-checked live: real bytecode (7,455 bytes), `activePools()` returns real
pool data.

The registry is governed by an OpenZeppelin AccessManager (`authority()` =
`0xA362D98B33A7bb5B5E2180a05f995A70FB404f30`), not a plain `Ownable`.
`register`/`deregister`/`setAuthority` are all gated by `getTargetFunctionRole()`
= roleId 0 (`ADMIN_ROLE`). Replaying every `RoleGranted`/`RoleRevoked` event
for roleId 0 from genesis finds exactly one grant, ever, no revokes: sole
holder is `0x359856655934338D798f9CCE1f181486301D36a5`.

That address's on-chain code is the EIP-7702 delegation designator
(`0xef0100` + `0x5a7fc11397e9a8ad41bf10bf13f22b0a63f96f6d`) -- an EOA that has
delegated execution to a smart-account implementation, not a Gnosis Safe (no
`getOwners()`/`getThreshold()` resolves there). It has 470 real transactions
on Robinhood Chain (a genuinely active operational key, ruling out a
fresh/vanity-mined key the way this project already rules that out
elsewhere -- see `score_uniswap_v4_poolmanager`'s docstring for the same
activity-based check), but a single delegated EOA is still single-key
control: no multisig, no timelock, `executionDelay` = 0 on the role itself
(`hasRole(0, holder)` returns `(true, 0)`).

Scored as a real, active bare-EOA equivalent -- the same convention already
used for Curve DEX's controller (`admin_key=5` case in `score_curve_dex`),
not a new number invented for this target.

## Beefy: SPY-WETH vault (representative) -- 50/100

| Field | Value |
|---|---|
| Target | `0x87673A619Fc4F3Fc08068A0BB04f60aA2D04ca62` (mooCowAlandaleRobinhoodSPY-WETH) |
| TVL | ~$2.57M total across ~14 Robinhood Chain vaults (DefiLlama `beefy`, `chainTvls["Robinhood Chain"]`) -- this one vault sampled as representative, same convention as Robinhood's ~230 tokenized stocks (5 sampled) |
| adminKeyScore | 65 |
| multisigScore | 60 |
| timelockScore | 20 |
| compositeScore | 50 |

Vault address from Beefy's own official `beefy-v2` repo
(`github.com/beefyfinance/beefy-v2`, `src/config/vault/robinhood.json`, entry
`alandale-cow-robinhood-weth-spy-vault`'s `earnContractAddress`) -- their
older standalone `address-book` npm-package repo has NO Robinhood Chain
entry at all (confirmed live by listing its full git tree: only
avax/bsc/fantom/heco/polygon exist there, a stale legacy repo), which is why
this lead had previously read "official address-book unresolved."

`vault.owner()` and `strategy.owner()` are two separate, real
`TimelockController` contracts (contract name confirmed on Blockscout, not
assumed), both governed by the identical real 3-of-6 Gnosis Safe
(`0x000000a151650b85742d8c286e09aba7be9bdb82`, 6 distinct owners, re-checked
live via `getOwners()`/`getThreshold()`) holding both `PROPOSER_ROLE` and
`CANCELLER_ROLE` on each (role holders re-derived via a live
`RoleGranted`/`RoleRevoked` replay). The deployer's own
`TIMELOCK_ADMIN_ROLE` was revoked one block after deployment on both
Timelocks (confirmed live) -- each self-administers now.

The vault-level Timelock's `getMinDelay()` = 0. The strategy-level
Timelock's `getMinDelay()` = 21,600s (6h) -- a real, non-zero delay. The
vault contract also has its own internal `approvalDelay()` = 21,600s (6h),
Beefy's standard `proposeStrat`/`upgradeStrat` cooldown on swapping the
strategy itself (the single highest-value action for a yield vault),
independent of the wrapping Timelock's own delay.

`admin_key`/`multisig` reuse the existing `_safe_rooted_scores(3, 6)`
convention already applied to PancakeSwap/SushiSwap/Symbiosis/STRATO in
batch 9 (65/60). `timelock=20` reuses the existing "real non-zero delay, but
PROPOSER_ROLE == CANCELLER_ROLE (same Safe, no independent veto path)"
convention already applied to Robinhood Chain's own L1 rollup authority and
to Ramses CL V2 -- not a new number invented for this target.

## Not added this run

- Every other Robinhood Chain protocol on DefiLlama's list with TVL above
  Beefy's was checked against `README.md`'s existing Status table and found
  already covered, directly or via a shared authority chain already tracked
  (the Uniswap stack covers Uniswap V4/V3/V2/UniswapX; the Morpho vaults
  cover Morpho Blue/Steakhouse Financial; Longbow, Pendle V2, Curve DEX,
  Ekubo, Ramses CL V2, PancakeSwap AMM V3, SushiSwap V3, LayerZero V2, Spark
  Savings, and Symbiosis are each tracked individually already).
- No other new target's authority chain could be resolved to a real,
  address-verified root via a primary source (official docs, official
  GitHub repo, or direct on-chain read) within this run's budget without
  guessing -- per this project's discipline, an unverified address is not
  published rather than filled in with a plausible-looking guess.
