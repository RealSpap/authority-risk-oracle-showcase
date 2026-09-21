# The code behind a target changes; the oracle only scores who controls it (2026-09-21)

The oracle scores authority: who can change a target, how many keys, with what delay. It says nothing about the code they control
having changed. A score can be right about the authority and stale about the code. This pass measured how often that happens and
added a watch for it.

## What was measured

Of the tracked EVM targets on the six ecosystems with a mainnet RPC (119 addresses), 26 are EIP-1967 proxies, 7 beacon proxies,
1 an ERC-1167 clone, 79 plain contracts and 6 have no code. For the proxies:

- **Robinhood Chain, from `Upgraded` events (the only public RPC that answers a full-history `eth_getLogs`):** 12 of 13 proxies
  have been upgraded at least once, and five within the last 26 days: Symbiosis Portal 9.0 days ago (2 upgrades in total),
  Pendle V2 19.0, STRATO Bridge depositRouter 23.5, Meridian Perps 24.2 and Arcus pToken factory 25.8 (6 upgrades in total).
  Spark Savings USDG was last upgraded 109.7 days ago, Lighter's escrow never.
- **Elsewhere, from a storage read 30 days back (archive access, which Ethereum and Base answered, Arbitrum for one of its three proxies and Plasma
  for its three; Robinhood Chain and Monad refused):** of the 8 proxies that could be compared, three had a
  different implementation than 30 days earlier: **Compound V3 cUSDCv3 on Ethereum** (`0x83D49126...` to `0x63e74915...`),
  **Yuzu yzUSD on Plasma** (`0x32d7d5BF...` to `0x8e023928...`), and Plasma's L1 validator-set authority, whose implementation slot
  was empty 30 days ago and holds `0xf70191Da...` now. Unchanged: USDtb, EigenLayer StrategyManager, Compound V3 on Arbitrum and
  Base, Fluid on Plasma.
- **Where the source is verified, without touching a bot-protected explorer.** Sourcify (any chain), Routescan's keyless
  Etherscan-compatible API (it serves Plasma and Ethereum, and mirrors Plasmascan: it returned `verified` for the two Plasma contracts
  documented as verified there), and Etherscan V2 only if the operator sets `ETHERSCAN_API_KEY` themselves. Of the 38 proxy, beacon and clone
  implementations: **24 verified, 1 not verified anywhere it can be asked, 13 unknown**. The unknown are Robinhood Chain 9, Monad 3 and
  HyperEVM 1, each reported with its reason (Blockscout behind a bot check, MonadScan needing a key, hoodscan's MCP indexer down on
  2026-09-21) instead of "unverified": a chain whose explorer cannot be asked has no answer, not a negative one. The one confirmed
  miss is the implementation behind Plasma's validator-set registry (Aquila), created within the last 30 days, verified neither on Sourcify
  nor on Routescan; it is a small UUPS contract (`getValidators`, `validatorCount`, `initialize`, `upgradeToAndCall`, Ownable2Step).

So a recent upgrade is common, the scored target may not have been re-read since, and nothing in the oracle would show it.

## What was added

`scripts/check_implementation_changes.py` (library `scripts/lib/implementation_watch.py`) fingerprints every target the deployed
oracles track: an EIP-1967 proxy by its implementation address and that implementation's code hash, a beacon proxy by the beacon's
implementation, an ERC-1167 clone by its implementation, anything else by its own code hash. It diffs against
`data/implementation_snapshot.json` (baseline taken 2026-09-21: 148 targets over the 8 oracles, including Tempo and HyperEVM).
It needs no archive access, since it compares one run with the last reviewed one. `repush_all_oracles.sh` now runs it first, read-only
and never blocking.

Workflow: `python3 scripts/check_implementation_changes.py` (exit 1 if a target changed or could not be read); read what the new
implementation does; `--update` to accept it. A target that could not be read is never written over a good fingerprint.

## What this does not say

- A changed implementation is not a problem: governance upgrades are normal, and it changes no score. It says the score should be
  re-read against the new code before it is trusted, which the oracle could not say before.
- Plain contracts are fingerprinted by their code hash, so a redeployment at the same address would show; contracts whose logic is
  reachable through other patterns (diamonds, custom proxy slots) are not followed.
- The watch compares runs; it cannot say when between two runs the change happened. The `Upgraded` history above is the only
  dated evidence, and only for Robinhood Chain.

## What a changed implementation is (2026-09-21, from bytecode and verified source)

`scripts/lib/code_review.py` reads a contract without an explorer: the selectors its dispatcher compares (its API), the compiler version
and metadata hash from the CBOR tail, and a diff between the old and the new implementation. Applied to the three changes:

- **Compound V3 cUSDCv3 (Ethereum): a configuration change, not new logic.** Same size (18,599 bytes), the same 66 selectors, same
  compiler and metadata; Sourcify exact match and Routescan verified as `CometWithExtendedAssetList`. Only baked-in constants differ, as
  in a Comet redeployed with new parameters. No new power.
- **Yuzu yzUSD (Plasma): a new version with new powers, none held yet.** V2 (source verified nowhere) to `YuzuUSDV3` (source verified on
  Routescan, solc 0.8.30 to 0.8.36, 21,863 to 24,543 bytes, 17 selectors added, none removed). The verified source shows `setNav` behind
  `NAV_MANAGER_ROLE`, capped at 10% per step with a one-day cooldown (an exempt role can bypass the step), fee levers bounded at 10% a
  year and 50%, mint and redeem throttles, and calls delegated to a fixed facet. A replay of the proxy's 245 role events (Routescan logs
  API) shows ten of the 18 roles V3 defines have **no holder**, `NAV_MANAGER_ROLE` among them, so `setNav` cannot be called today; the
  admin (the 12-hour timelock) can grant them, which is the path already scored. 101 accounts (97 bare EOAs, 2 contracts, 2 Safes) hold
  each of `MINTER_ROLE` and `REDEEMER_ROLE`, an allow-list for depositing and redeeming, not an administrative power. No score changes; the scorer now says so in a note.
- **Plasma validator-set registry (Aquila): a new proxy.** Its implementation slot was empty 30 days ago; the implementation is unverified
  (above).

## What still cannot be answered

Robinhood Chain's explorers are the sanctioned public route to verification data there and cannot be reached without getting past a bot
check, which this project does not do; hoodscan.co advertises a keyless read-only MCP endpoint for programmatic access, whose indexer
returned an error on 2026-09-21 (`chain_status` shows the indexer null). Retry it later. For Monad, an Etherscan V2 key from the operator
answers the question (`ETHERSCAN_API_KEY`; this project never creates an account or enters a key). Until then those 13 stay "unknown".
