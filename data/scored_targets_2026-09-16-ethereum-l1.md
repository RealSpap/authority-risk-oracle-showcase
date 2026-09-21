# Ethereum L1 -- first 4 targets scored (2026-09-16)

## Provenance and why this was committed manually

`authority-risk-oracle-multichain-pipeline`'s automated worker/verifier pair
scouted and fully verified these 4 targets on 2026-09-16 (`scouting` phase),
including a corrected retry (attempt 2 fixed two real gaps attempt 1 left
open: the Aave delay-getter dead end, and the Uniswap fee-adapter's
misreported code size / unidentified contract). Both attempts scored 2/3 on
the automated verifier and the maker-checker gate never reached APPROUVEE
within the run's retry budget -- the draft sat un-committed in
`runs/2026-09-16/ethereum-l1/brouillon_non_approuve/`.

Independently re-verified live in an interactive session the same day: 5 of
the most load-bearing claims (Uniswap Timelock.delay()/admin(),
Governor.quorumVotes(), Aave PayloadsController.getExecutorSettingsByAccessControl(1),
Ethena Safe threshold, Maker DSChief.hat()) were spot-checked fresh against
`https://ethereum-rpc.publicnode.com` -- all matched the draft exactly, zero
divergence. the verifier run against the verifier's own
`sfa_attempt2.csv` also came back clean (🟢, no fabrication detected). The
underlying research holds up; the exact reason the automated gate stayed
below 3/3 was not fully reconstructable from the artifacts available in this
session (no verifier reasoning transcript was retained beyond the CSV/journal
files).

Given that, this batch was completed manually: the 4 scorer functions below
were written from the verified draft, dry-run live (which caught 2 real bugs
-- two ABI fragments reused the wrong function name, causing `Timelock.admin()`,
`GovernorBravo.quorumVotes()` and `PayloadsController.guardian()` to silently
return `None` -- fixed and re-verified clean before this commit), and pushed
directly to the private repo. This is a **disclosed, deliberate manual
override** of an automated rejection based on independent re-verification,
not a silent bypass of the maker-checker gate -- the routine's own
`ecosystems.json`/`rotation_state.json` are updated in the same commit to
reflect the phase advancing to `scoring_build`, with this note linked.

## Scores

| Target | Address | Composite | admin/multisig/timelock | Why |
|---|---|---|---|---|
| Uniswap V3 Factory | `0x1F98431c8aD98523631AE4a59f267346ea31F984` | **85/100** | 80/100/75 | Factory -> `V3OpenFeeAdapter` (Sourcify-verified, not a bare EOA) -> real Uniswap Governance Timelock (2-day delay, same address the Robinhood-chain correction identified via its L2 alias) -> GovernorBravo (40M UNI quorum, 100 proposals, real active DAO). Emergency-bypass mechanism not checked this pass. |
| Aave V3 Ethereum Pool | `0x2f39d218133AFaB8F2B819B1066c7E434Ad94E9e` | **78/100** *(corrected, was 75)* | 78/100/55 | PoolAddressesProvider -> EXECUTOR_LVL_1 <-> PayloadsController (mutual pointers) -> 1-day delay at access level 1 -> GOVERNANCE core (522 proposals, real). ACLManager's `EMERGENCY_ADMIN_ROLE` holder **identified 2026-09-16**: `PROTOCOL_GUARDIAN` Safe, 4-of-7, sourced from bgd-labs/aave-address-book and confirmed live on 2 RPCs -- see `data/correction_2026-09-16-aave-emergency-admin-identified.md`. |
| MakerDAO / Sky (MCD_PAUSE) | `0xbE286431454714F511008713973d3B053A2d38f3` | **81/100** | 75/100/70 | Pause (2-day delay) -> authority = DSChief -> hat = most recently executed governance spell, dated 2026-09-10 (6 days before this pass) -- real, active governance, not dormant. |
| Ethena EthenaMinting (USDe) | `0x2CC440b721d2CaFd6D64908D6d8C4aCC57F8Afc3` | **52/100** | 55/100/0 | `DEFAULT_ADMIN_ROLE` = the same 5-of-10 Safe already tracked for Ethena's Robinhood-Chain infra (`0x3b0aaf6e...Dc1862`) -- confirmed live, no DAO/Timelock layer at all, controls minting of a $5.14B-backed stablecoin with **zero delay**. Sibling `StakedUSDeV2`'s current admin (role moved since Nov 2023) is **not identified**. |

**Correction, 2026-09-20 (Ethena row).** The Ethena row above scores `0x2CC440b7...`, which has not
been USDe's minter since 2024-07-08 (`USDe.minter()` is `0xe3490297...`, whose admin is a 24h
timelock, not the Safe directly). The row is kept as what was believed and scored on 2026-09-16.
The live minter was scored 65/100/55 (composite 73) and pushed on-chain as a new target on
2026-09-20, and the old target is no longer refreshed (it turns stale after 2026-09-28 16:39 UTC). See
`data/finding_2026-09-20-ethena-live-minter.md`.

All four scores are the project's usual heuristic (`0.4*adminKey + 0.3*multisig
+ 0.3*timelock`), not a measured risk -- see each function's docstring in
`chains/ethereum-l1/scorers.py` for the full reasoning behind every
sub-score. One of the two open threads disclosed at launch is now closed
(Aave's emergency-admin holder, see the correction file linked above); Ethena's
StakedUSDeV2 admin remains open for a future pass.

## Not pushed on-chain yet

This batch is committed to the private repo (code + data), matching the
`testnet_push_and_private_commit_enabled` autonomy level already established
for this project. No native Ethereum-L1 oracle contract exists yet to push
these scores to (Ethereum L1 is still in `scoring_build`, the phase this
commit advances it to -- `deploy_testnet` on Sepolia is the next step, not
done here).
