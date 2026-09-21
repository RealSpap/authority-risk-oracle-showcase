# Batch 8 -- 2026-09-16

Prompted by a direct research question from Spap: "look at our postmortems
(`onchain-postmortems`, 42 independently-reconstructed exploits) and tell me
what's relevant for authority-risk-oracle." Three cross-cutting patterns came
out of that read, cross-checked against exactly what this project's own
scorers do and don't verify, then checked for real, live candidates on
Robinhood Chain before writing a single line of new scorer code -- consistent
with this project's rule of never building a generic check with nothing real
to run it against.

## 1. A real bug found and fixed: PROPOSER_ROLE/CANCELLER_ROLE were never re-derived live

`score_rollup_l1_authority` carried a hardcoded note from batch 4
("currently has ZERO PROPOSER_ROLE holders... gates nothing") that was still
being asserted as current fact on every subsequent push. A fresh live replay
this batch found a real holder now: `0xbFc2b53552513174A0B006D4799B39871fe0CA1d`,
itself the same 6-of-8 Safe that also holds `CANCELLER_ROLE` on that
Timelock (`0xE1e825D15192457d05a251715C3e2Cab0F8CF465`). The batch-4 finding
had simply gone stale without anyone re-checking it, while still being
printed as ground truth -- the exact silent-staleness failure mode this
project's own discipline exists to catch elsewhere in the stack, caught here
inside itself.

Fixed properly, not just patched: `PROPOSER_ROLE` and `CANCELLER_ROLE` are
now replayed live from genesis on every run (`_replay_role_holders`, a new
shared helper -- also used to re-derive `EXECUTOR_ROLE`, replacing three
near-duplicate inline replay blocks with one). The composite score for the
6 rollup-authority targets moves from 57 to **60/100**: the timelock is
real and does gate something now, but the same address that can propose a
change can also cancel any attempt to veto it -- a narrower, still-real gap
this project wasn't scoring before. `score_ramses_clv2` got the same
treatment: its `RamsesTimelock` (exact address `0xE41c07CcD69A0f19A2186f3Ad30409BD585436CE`,
never pinned down before this batch -- previously only inferred from AccessHub) has
`PROPOSER_ROLE`, `CANCELLER_ROLE` and `EXECUTOR_ROLE` all held by the
identical single address, on top of its already-known zero delay. Composite
stays at 8 (delay=0 already floors the timelock sub-score), but the finding
is now live-verified rather than carried forward from a one-time batch-4
note with an explicit "not re-derived this pass" disclaimer.

**Performance note, kept for the next person who touches this code**: a
first draft replayed each role with its own from-genesis `eth_getLogs` scan.
On Robinhood Chain mainnet (already ~64M blocks after 2.5 months) that meant
3 full genesis-to-tip scans just for Ramses -- too slow for a usable
dry-run. `_replay_role_holders` now accepts a list of role names and fetches
all of them in ONE pair of queries (GRANT + REVOKE) via an OR-filter on
`topics[1]`, regardless of how many roles are requested.

## 2. Chainlink's own oracle-admin authority, tracked for the first time

Every protocol this oracle scores that consumes a price feed has always had
`oracleAuthorityScore` fixed at 100 ("not applicable") -- this project cited
`defi-admin-key-risk`'s admin-key methodology as its source but never
actually pointed it at an oracle's own governance. Research this batch
found Chainlink is the *only* officially confirmed price-oracle provider on
Robinhood Chain (chain.link's own `feeds-robinhood-mainnet.json` dataset,
57 feeds; Pyth, RedStone and Chronicle Protocol were searched and found to
have no official integration here, and API3's dedicated market page could
not be verified further this pass -- reported as such, not silently
dropped).

`owner()` was called live on 7 independently-sampled feeds -- 3 of them
already-tracked stock-token feeds (Robinhood TSLA/AMZN/AMD), plus LINK/USD,
ETH/USD and USDG/USD -- and all 7 resolve to the SAME address:
`0xEE27D5aE494300902D90454E8630a3f1c68C9c52`, confirmed live as a real
4-of-9 Gnosis Safe. New scorer `score_chainlink_admin_safe` tracks this Safe
directly: composite **36/100** (a real, moderate-size multisig, no timelock
layer identified above it this pass -- absence of evidence isn't treated as
evidence of one, so `timelockScore` stays 0 rather than assumed). Added to
`signer_overlap.py`'s `GROUPS` as `chainlink_admin` so any future overlap
with another tracked group's signers is caught automatically.

**Disclosed, not fixed this pass**: tracing *which* Morpho-vault markets
actually use this Chainlink infrastructure (vs. a different or unidentified
provider) surfaced real heterogeneity across the 7 already-tracked Morpho
vaults -- roughly 56% of their 70 market allocations are confirmed real
Chainlink, some use Uniswap V3 TWAPs (mostly Longbow Frontier), one uses no
external oracle at all (Steakhouse's Spark-Savings-collateral market reads
Spark's own internal share price directly), and Morpho NetNet Credit vault
(100% of its 7 markets) uses a provider that matches neither Chainlink, Pyth
nor RedStone's known interfaces after a full selector scan -- genuinely
unidentified. `oracleAuthorityScore` still reads 100 for NetNet Credit
today, which is not the right signal for "unverifiable" vs. "not
applicable" -- left open rather than forced into either bucket without the
market-enumeration work (adapter -> `marketIds()` -> Morpho Blue's own
`idToMarketParams()`) this would need.

**Follow-up 2026-09-17**: did that market-enumeration work live against
`rpc.mainnet.chain.robinhood.com`. NetNet Credit's vault has exactly 1
adapter (`0xf0eeF247585b184836915e80f984246d981c55C4`, a
`MorphoMarketV1AdapterV2` per `morpho-org/vault-v2`'s own source), covering
all 7 markets confirmed via `marketIdsLength()`/`marketIds(i)`. Each
market's `oracle` field (from `idToMarketParams`) is a distinct address; 6
share identical 2,563-byte bytecode, the 7th is 1,550 bytes. Directly probed
each for Chainlink's `latestAnswer()`/`decimals()`/`description()` (all
revert), an `owner()` (reverts), and MorphoChainlinkOracleV2's immutable
feed getters `BASE_FEED_1`/`QUOTE_FEED_1`/etc. (all revert) -- confirming
the original "matches neither Chainlink, Pyth nor RedStone" finding
directly rather than by inference. What DOES work: Morpho Blue's own native
`price()` (returns a live value, e.g. `169102231517391622206302822`) and
`SCALE_FACTOR()` (`= 1e24` exactly on every oracle checked). No
`hasRole`/AccessControl surface found either. Genuinely unresolved by this
pass: whether `price()` is a hardcoded constant (in which case treating
`oracleAuthorityScore=100` as correct, not a gap, would be the right call)
or updatable by an unguessed selector -- the public RPC used doesn't retain
enough history to diff `price()` across old blocks and settle this either
way. Narrowed the gap; did not close it.

## 3. LayerZero V2's messaging core, a real surface an order of magnitude bigger than everything tracked before

A live `eth_getLogs` replay of `DelegateSet` on LayerZero's own `EndpointV2`
(`0x6F475642a6e85809B1c36Fa62763669b1b48DD5B`), from genesis to the current
tip (~64.19M blocks), returned 965 events from **709 distinct OApp
addresses** already registered -- a real, heavily-used cross-chain
messaging layer, confirmed via `eid()` returning `30416` (matches
LayerZero's own official registry entry for "robinhood"), completely absent
from this oracle before now and structurally distinct from the chain's own
L1 rollup bridge this project already tracks.

`EndpointV2`, `SendUln302` and `ReceiveUln302` were each checked
independently and all three share the identical `owner()`:
`0xE590a6730D7a8790E99ce3db11466Acb644c3942`. That address is deliberately
NOT a Gnosis Safe -- `getOwners()`/`getThreshold()` both revert on it -- it
is a bespoke on-chain multisig (bytecode contains the string "OneSig"),
exposing `getSigners()`/`threshold()` instead. New scorer
`score_layerzero_infra` resolves it via a new shared helper,
`custom_multisig_owners_and_threshold` (added to `web3_utils.py`
specifically for this pattern, and wired as a fallback in
`signer_overlap.py`'s own `_safe_owners()` too): a real **5-of-7** multisig,
confirmed live. Composite **34/100** for all three targets.

`Executor` (`0x4208d6e27538189bb48e603d6123a94b8abe0a0b`) was deliberately
EXCLUDED from this scorer: it is a separate EIP-1967 proxy whose own admin
slot resolves to a THIRD, still-unidentified 2319-byte contract matching
neither the Safe nor the bespoke-multisig pattern -- left as an open thread
rather than guessed at, same discipline this project already applies to
Pendle's `MarketFactoryV6` owner.

**Explicitly out of scope for now**: the 709 individual OApps registered
against this Endpoint are not tracked one by one -- only the shared
infrastructure they all inherit risk from. Symbiosis and STRATO Bridge,
noted as open threads in batch 5/6, remain unresolved (searched again this
batch, no address found). Chainlink CCIP (Router/ARM Proxy/TokenAdminRegistry)
and Wormhole's Core Contract were also confirmed live and deployed on
Robinhood Chain mainnet during this batch's research phase, but their own
authority structure was not yet probed -- candidates for a future batch, not
guessed at here.

## Governance-DAO dimension: researched, deliberately not built

The third pattern identified from the postmortems read (Term Finance and
BarnBridge: a real timelock delay doesn't help when nobody exercises a
veto, and a dormant DAO's takeover cost can collapse to near nothing) was
checked directly against all 34 pre-batch-8 targets and against Robinhood
Chain more broadly. Verdict, confirmed live: **no protocol deployed on
Robinhood Chain today is governed by a token-weighted voting contract that
itself lives on Robinhood Chain.** The only functioning `TokenVoting`
instance found (Aragon OSx, deployed 2026-09-08) is used exclusively by 3
internal Aragon test DAOs (throwaway tokens, zero assets, "test" in every
title). Autonolas/Olas has a real protocol deployment here governed by an
established OLAS/veOLAS DAO, but that DAO's own vote/execute contract lives
on Ethereum L1 -- only a bridge-alias "L2 Mediator" touches this chain. This
dimension is shelved, not abandoned: revisit when a real DAO actually
deploys its governance contract on Robinhood Chain itself, rather than
build a check with nothing real to point it at.

The related, narrower finding that WAS real and buildable today --
`PROPOSER_ROLE`/`CANCELLER_ROLE` separation on an existing Timelock -- is
covered under (1) above.

## Running total

38 targets (up from 34), all genuinely covered by `score_all()`. Every
existing score was re-verified unchanged except the 6 rollup-authority
targets (57 -> 60, real state change plus a scorer bug fix, not a
methodology drift) and Ramses (composite unchanged, finding re-verified
live instead of carried forward from a disclaimer).
