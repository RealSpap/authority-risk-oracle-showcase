# Vault V2 disclosed inventory: $2.87B across 27 vaults, none previously tracked

2026-09-25. Continues `data/finding_2026-09-25-vault-v2-scoring-scope.md` (Vault V2 scoring needs a
real methodology decision, not built) with the safe next step that finding flagged: a disclosed-only
inventory reusing already-settled patterns (owner/curator classification, timelock durations from
Morpho's own API), no new score, no `AuthorityScore` field. Built: `scripts/lib/vault_v2_inventory.py`
(12 new unit tests) + `scripts/check_vault_v2_inventory.py`.

## The gap is much larger than the 09/20 research quoted

That research flagged $110M of untracked Vault V2 deposits on Monad specifically. A fresh live query
(2026-09-25, corrected to the RIGHT chain IDs -- Plasma's real id is 9745, not 988, which the earlier
research's own chain-id table had mislabeled) found: **$2.87B across 27 Vault V2 targets of $20M or
more, on 4 of this oracle's own 10 tracked ecosystems** (Ethereum L1 $2,244.5M across 23 vaults,
Robinhood Chain $501.6M across 1, Monad $85.3M across 2, Tempo $36.4M across 1). Morpho's API does not
index Plasma at all ("unsupported chainId"); Arbitrum and Hyperliquid have Vault V2 activity but
nothing above $20M today.

## The single most striking finding: one owner key and one curator key control $1.14B across 2 chains

Live-checked individually (not just from the inventory's own summary): **Sentora RLUSD Main
($424.3M), Paypal USD Main ($423.6M), Sentora PRIME Main ($184.3M), Sentora Huma PST Main ($45.7M),
Sentora mWIN Main ($26.8M) on Ethereum L1, and Sentora pathUSD ($36.4M) on Tempo -- six vaults, two
chains, $1,141.1M combined -- share the LITERAL SAME owner address
(`0xe8C9C99EcaD0686A14A00d8521c572281E938008`) and the LITERAL SAME curator address
(`0x9e396dE3312D373b87F9BD8763fb48184b42aac0`).** Both resolve to real, distinct 1-of-1 Gnosis Safes
-- **not the same individual for both roles** (the owner Safe's single signer,
`0x295Df6B70f4Ed2bE704Bd802a4D805fE700Bd7E9`, differs from the curator Safe's,
`0x992592e073AA9b98daeD79eE05C4Af832e1D0ABE`, confirmed live -- stated precisely rather than
overclaimed as "one person controls everything"). But each layer individually is a single point of
failure: one key can act alone as owner across all 6 vaults on 2 chains, and a different single key
can act alone as curator across the same 6. `Paypal USD Main` is notable by name -- a vault whose
branding suggests institutional backing shares this identical single-key governance with the
Sentora-branded vaults.

## Other findings worth flagging (disclosed, not scored)

- **msETH Vault ($22.8M, Ethereum L1): all three disclosed timelocks read 0 days**
  (`addAdapter`/`removeAdapter`/`abdicate`) -- no delay at all on the functions that reach depositor
  principal, unlike every other vault in the inventory (3-7 days).
- **Galaxy USDT Quality ($22.3M) and Bitwise Premium RWA AUSD ($21.7M): owner AND curator are both
  bare EOAs** (no Safe wrapper at all, zero code) -- $44.0M combined behind two single keys with no
  multisig layer whatsoever.
- **UPDATE, same pass: 6 of those 9 resolved.** `read_holder()` now follows ONE hop of `owner()` when
  the first read is a non-Safe contract (the same pattern `score_aave_v3_pool`'s executor/
  PayloadsController chain and `_score_steakhouse_l1_vault` already use elsewhere in this project) --
  live-checked, `Steakhouse Prime EURCV/USDC/USDT/High Yield/Confidential Prime/ETH` ($437.1M
  combined) all read `owner()` as a single verified `VaultV2Supervisor` contract
  (`0x4D7bd498Bb24098Ca281C05519629c605407f71d`), whose OWN `owner()` is
  **the exact same Steakhouse Safe (`0x0A0e559bc3b0950a7e448F0d4894db195b9cf8DD`, 5-of-10) this oracle
  already tracks as the owner of 4 Morpho V1 vaults on Ethereum L1 and Base**
  (`scripts/lib/controller_concentration.py`, built earlier today). Not a coincidence discovered by
  re-running the same tool twice -- a genuinely new connection, directly extending this morning's own
  controller-concentration finding: that Safe's real reach is $381.8M (4 V1 vaults) **plus $437.1M
  more (6 V2 vaults via the VaultV2Supervisor indirection)**, disclosed here, not yet folded into the
  controller-concentration report itself (which is scoped to V1 targets; extending it to also walk the
  VaultV2Supervisor hop is a natural next step, not done this pass).

  The other 2 non-Safe owners were chased the same one hop and genuinely do NOT lead to a Safe --
  disclosed as still open, not guessed at: **Robinhood Chain's Steakhouse USDG ($501.5M)** owner
  resolves, one hop in, to a bare EOA (`0x337feFE49514fb901eB455A501b8Be76CDeF7660`) -- a real,
  verified finding (a single key, not a multisig, behind Robinhood Chain's largest tracked V2
  exposure), not an unresolved mystery. **Sentora x Spark RLUSD ($250.0M)**'s owner is a verified
  `SubProxy` contract (`0x3300f198988e4C9C63F75dF86De36421f06af8c4`) whose own `owner()` call returns
  nothing at all (reverts or unset). Checked further, not just left at that: its EIP-1967 admin slot
  AND implementation slot both read zero too, and Blockscout's own metadata confirms it is verified
  but not recognized as any standard proxy type (`proxy_type: null`, no listed implementation) -- a
  genuinely non-standard access-control pattern, not one of the two most common conventions this
  project already knows how to check. Reading its own source to find the real mechanism is a deeper
  dive than this pass's scope for one $250M data point; disclosed honestly as still open, not guessed
  at further.

## What this is and isn't

Disclosed only -- reuses the exact "off-chain, no score" precedent already established today
(controller-concentration, RISK_ADMIN discovery, exit capacity): no `adminKeyScore`/`multisigScore`/
`timelockScore` computed for any of these 27 targets, no `AuthorityScore` field, no on-chain push. The
open methodology questions from `data/finding_2026-09-25-vault-v2-scoring-scope.md` (what a
per-function timelock means for `timelockScore`, whether an abdicated gate counts as a protection, how
to score a non-Safe curator) remain unanswered -- this inventory does not answer them, it surfaces the
real numbers so answering them is an informed decision rather than a guess.

## Verification

`python3 scripts/check_vault_v2_inventory.py [--min 20000000]` -- read-only, Morpho's public API plus
each chain's own RPC for `owner()`/`curator()`/Safe resolution (one hop past a non-Safe owner), no
key, no transaction. 12 unit tests for the pure classification logic
(`scripts/lib/tests/test_vault_v2_inventory.py`) + 7 for the one-hop resolution itself
(`scripts/tests/test_check_vault_v2_inventory.py`, mocked web3 calls -- covers the exact
VaultV2Supervisor and SubProxy shapes found live). Full suite (6 directories, 2386 tests) green.
