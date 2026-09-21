# Plasma Ecosystem -- deployment guide (Plasma Testnet, chain 9746)

Phase: `deploy_testnet` -- **deployed for real on 2026-09-19.** The funding
blocker documented in every earlier attempt below is resolved: Spap funded
the shared deploy key on Plasma Testnet specifically via a proof-of-work
faucet (`openfaucet.org` -- no wallet-connect/OAuth/mainnet-balance
requirement, unlike QuickNode's and Chainstack's faucets, which both
rejected the funding attempt over "insufficient wallet history" -- see
"Funding" below for the full trail), then this run compiled the contracts
directly with `py-solc-x` (Foundry is still not installed in this
environment -- worked around it rather than waiting on it), deployed both
contracts for real via `web3.py` (`--broadcast`-equivalent, no `forge`
needed), pushed real scores via `deploy/push_scores.py` (no `--dry-run`),
and read every score back via `getScore()` to confirm the written data
matches exactly. See "Real deployment (2026-09-19)" below for addresses,
tx hashes, and balances. The sections further down (network info, prior
dry-runs) are kept as the historical record of the `scoring_build` ->
`deploy_testnet` work that led here.

Latest state: the oracle was re-pushed on 2026-09-20 (three
`crossExposureScore` values 100 -> 80, tx `0xa2e8f4f1...b3de4`, block
34034832). The current on-chain table is in "2026-09-20 re-push" at the end
of this file.

## Network

| | |
|---|---|
| Network | Plasma Testnet |
| Chain ID | **9746** -- confirmed live via a direct `eth_chainId` read against `https://testnet-rpc.plasma.to`, independently cross-checked against `chainid.network/chain/9746` |
| Public RPC (official) | `https://testnet-rpc.plasma.to` |
| Explorer | `https://testnet.plasmascan.to` -- confirmed via `datawallet.com`'s Plasma network-config guide, not independently browsed this pass |
| Faucet that actually worked | [`openfaucet.org`](https://openfaucet.org) -- browser proof-of-work mining, only needs a public address pasted in, no wallet connection, no account, no real-value requirement. Select network "Plasma / Testnet", paste an address, mine until the 0.01 XPL minimum is reached (took ~9 proofs / under a minute with 4 workers), claim. |

Plasma mainnet (read-only, for the scorers -- never a deploy target) is
chain **9745**.

## Funding (2026-09-19): two faucets rejected the shared key, one worked

Documented because it's a real, repeatable obstacle, not a one-off fluke:

- **QuickNode** (`faucet.quicknode.com/plasma/testnet`) requires connecting
  a browser wallet (MetaMask/Coinbase/Uniswap/Phantom) and explicitly
  rejected the attempt: *"Nous exigeons que les portefeuilles aient un
  [backlog note]
  [backlog note]"* -- an anti-sybil check tied to wallet
  age/activity, not something a throwaway or lightly-used wallet passes.
- **Chainstack** requires signing into a Chainstack console account, an
  API key, AND a minimum 0.08 ETH real balance on Ethereum mainnet held by
  the requesting address -- a real-value gate, out of scope entirely.
- **Chainlink** (`faucets.chain.link`) only drips LINK for Plasma
  Testnet, not native XPL -- wrong token for paying gas, not usable
  regardless of wallet history.
- **`openfaucet.org`** worked cleanly: no wallet connection, no account,
  no balance check -- browser-side proof-of-work is its own anti-sybil
  mechanism instead of gating on wallet history or real funds. Mined 9
  valid proofs (0.018 XPL, above the 0.01 XPL minimum) and claimed
  successfully; balance confirmed live via a direct `eth_getBalance` call
  immediately after, not just trusted from the page's own success message.

## Contract

`src/AuthorityRiskOracle.sol` is used unmodified -- same contract already
deployed for real on Robinhood Chain testnet, Ethereum L1 Sepolia, Arbitrum
Sepolia and Base Sepolia. No Plasma-specific Solidity changes needed.

**Compiled without Foundry**: `forge` is still not installed in this
environment. Installed `py-solc-x` instead (`pip3 install --user
py-solc-x`), pulled solc `0.8.24` (the exact version this project's
`foundry.toml` pins), and compiled both `src/AuthorityRiskOracle.sol` and
`src/ExampleConsumer.sol` via `solcx.compile_standard()` with the same
`@openzeppelin/contracts/=lib/openzeppelin-contracts/contracts/` remapping
`foundry.toml` declares. **0 errors, 0 warnings.** Oracle bytecode: 3,935
bytes (deploy) / 3,581 bytes (runtime, confirmed live via `eth_getCode`
after deploy). Consumer bytecode: 1,355 bytes (deploy) / 1,210 bytes
(runtime, confirmed live). Solidity unit tests (`AuthorityRiskOracle.t.sol`,
`ExampleConsumer.t.sol`) were NOT run this pass -- still no `forge test`
available -- relying instead on this exact source being byte-identical to
what already passed those tests and deployed clean on 4 other chains, plus
this pass's own live on-chain verification (bytecode size, deployment
success, a full `getScore()` read-back matching every pushed value exactly)
as a substitute check.

## Real deployment (2026-09-19)

| Field | Value |
|---|---|
| `AuthorityRiskOracle` (deployed) | `0x50840a7667baEa9D05ad4ae3dCeb384724b58720` |
| `ExampleConsumer` (deployed) | `0xB7403b365a58B31Ae030DB423f6B703AD67f003a` |
| Admin / updater | `0x20630C6Ab4BA48a80edA46F77b9b6e987A8f32f5` (the shared EVM testnet key, already used on Ethereum L1/Arbitrum/Base) |
| Deploy tx (`AuthorityRiskOracle` CREATE) | `0xb0569d597ddf5dd81cef765f11a7e7a71ae89e2a7540658d12b802a48e2e0909` (block 33941499, status success, gasUsed 903,873) |
| Deploy tx (`ExampleConsumer` CREATE) | `0x974f76cb9f3524832937e841a459166f5cb79b001079bb0e822769af11d409e2` (block 33941514, status success, gasUsed 316,189) |
| `updateScores()` tx (7 targets, real push) | `0xcb5c8a3ae7e27eddf0376328a7a27cb9aa28bc2971c878f965a3e1edfb300b99` (block 33941556, status success) |
| Gas price paid | ~1.73 gwei (live `eth_gasPrice` × 1.25 buffer, same convention as every sibling deploy script) |
| Balance before | 0.018000000000000002 XPL (mined via `openfaucet.org`) |
| Balance after both deploys + push | 0.013798681176659342 XPL -- spent ~0.0042 XPL total, plenty of margin left in the 0.05 XPL/session faucet cap if more is ever needed |

Arbitrum's and Base's `AuthorityRiskOracle`/`ExampleConsumer` addresses are
identical to Plasma's own -- expected, not a bug: a CREATE address is
`keccak(deployer, nonce)`, chain-independent, and the shared deployer key
was at the same nonce on all three chains when each pair was deployed.

**Verified after deploy, not assumed:**

- `eth_getCode` on both deployed addresses returned non-empty bytecode
  matching the compiled runtime bytecode's expected size (oracle: 3,581
  bytes; consumer: 1,210 bytes).
- **Every one of the 7 pushed scores was read back live via `getScore()`
  and matches exactly what `push_scores.py` sent**, not spot-checked on a
  subset: Aquila (35, cross=100), Aave V3 (71, cross=80), Pendle (43,
  cross=100), Ethena (52, cross=80) -- independently re-derived via a
  direct `eth_call` against the deployed oracle, not read from the
  push script's own stdout.
- `trackedTargetsCount()` returns `7`, matching all 7 scored targets.

> SUPERSEDED 2026-09-20: the `crossExposureScore` values read back above are
> the state pushed on 2026-09-19 and stay as that record. The 2026-09-20
> re-push (tx `0xa2e8f4f1...b3de4`, block 34034832) wrote 80 (not 100) for
> Pendle and for both Euler targets, equal to the scorer output; see
> "2026-09-20 re-push" at the end of this file.

## Second real push (2026-09-19): 2 new targets added, 9 total

Phase: still `deploy_testnet`, same deployed contracts as above (no
redeploy needed). This pass's own scouting found 2 new legitimate Plasma
MAINNET targets with real Plasma-specific TVL --
`score_telos_consilium_euler_earn_plasma()` and `score_yuzu_money_plasma()`
-- see `chains/plasma-ecosystem/data/scouted_targets_2026-09-19-new-mainnet-candidates.md`
for the full scouting writeup (what was found, what was checked and
excluded, and why) and each scorer's own docstring in `scorers.py` for its
individual sourcing/authority-chain trace.

**Balance checked before pushing, not assumed**: `eth_getBalance` on the
shared deploy key (`0x20630C6Ab4BA48a80edA46F77b9b6e987A8f32f5`) read
`0.013798681176659342` XPL live from `https://testnet-rpc.plasma.to`
immediately before this push -- matching exactly the "Balance after" this
file's own 2026-09-18 section already recorded, confirming no other
session had spent from this key in between.

| Field | Value |
|---|---|
| `updateScores()` tx (9 targets, real push) | `0xe5ad84982980d30c7954b3f06655d09e135e26b314a0816365906d2ed0b232e0` (block 34004083, status success, gasUsed 344,587) |
| Balance before | 0.013798681176659342 XPL |
| Balance after | 0.013054373252524298 XPL -- spent ~0.00074 XPL, plenty of margin left |
| `trackedTargetsCount()` after push | `9` (7 original + Telos Consilium + Yuzu Money) |

**Verified after push, not assumed**: both new targets' scores were
read back live via `getScore()` (a direct `eth_call` against the deployed
oracle, not the push script's own stdout) and decoded to confirm an
EXACT match against what `push_scores.py` computed and sent:

- Telos Consilium `TelosC Surge` (`0xA9C251f8304b1B3Fc2B9e8FCAE78D94eFF82Ac66`):
  adminKeyScore=40, multisigScore=45, timelockScore=0,
  oracleAuthorityScore=100, crossExposureScore=100, compositeScore=30.
- Yuzu Money `yzUSD` (`0x6695c0f8706c5ace3bdf8995073179cca47926dc`):
  adminKeyScore=20, multisigScore=100, timelockScore=55,
  oracleAuthorityScore=100, crossExposureScore=100, compositeScore=55.

No redeploy of `AuthorityRiskOracle`/`ExampleConsumer` was needed or done
this pass -- same testnet contracts as the 2026-09-18 deployment above.

## What this does NOT do

- Still no `forge build`/`forge test` run against this exact dependency
  tree -- `py-solc-x` compiled clean, but Foundry's own test suite
  (`AuthorityRiskOracle.t.sol`/`ExampleConsumer.t.sol`) was not exercised
  in this environment. Low risk (byte-identical source to 4 already-tested
  deploys) but disclosed, not assumed equivalent.
- The `UPDATER_ROLE`/admin key is still the single shared EOA, not a
  multisig -- same as every other testnet deploy in this project, and
  explicitly out of scope for a testnet validation pass (see the root
  `README.md`'s "Status" section on the mainnet migration plan).
- Robinhood Chain's weekly recurring `.github/workflows/update_scores.yml`
  cron does NOT cover Plasma -- this was a one-time manual push, not a
  wired-in recurring job.

## 2026-09-20 re-push: cross-ecosystem overlaps folded into crossExposureScore, pushed on-chain

| Field | Value |
|---|---|
| Oracle | `0x50840a7667baEa9D05ad4ae3dCeb384724b58720` (Plasma testnet, chain 9746) |
| `updateScores()` tx (9 targets) | `0xa2e8f4f12ccbe3740734bccfa5ee9cf4c20018f5a453a38c00e77a8583cb3de4` |
| Block | 34034832, status 1, gasUsed 180,611 |
| `lastUpdated` | 1789863481 = 2026-09-20 00:18:01 UTC (all 9 targets) |
| What changed | `crossExposureScore` 100 -> 80 for Pendle, Euler V2 eVaultFactory and Euler V2 AccessControlEmergencyGovernor. Composites unchanged. The other 6 targets were re-written with unchanged values. |
| Read back | Plain `getScore()` on all 9 targets equals the scorer output of commit `042f805` exactly (0 differences). `trackedTargetsCount()` = 9. |

Scorer output as of 2026-09-20 (`chains/plasma-ecosystem/scorers.py`,
re-run read-only against Plasma mainnet, chain 9745, no key, no
transaction). Three targets move on `crossExposureScore` only; their
composites do not change, because `crossExposureScore` is not an input of the
composite.

| Target | crossExp on the oracle before (2026-09-19 push) | crossExp on the oracle now (pushed 2026-09-20, equal to scorer) | composite (unchanged) |
|---|---|---|---|
| Pendle (Router + Market Factory V6) | 100 | 80 | 43 |
| Euler V2 eVaultFactory | 100 | 80 | 72 |
| Euler V2 AccessControlEmergencyGovernor | 100 | 80 | 68 |

Why. The project decided on 2026-09-20 that a cross-ecosystem overlap is
folded into `crossExposureScore` on every ecosystem: a flat 80 when a target's
root committee is identical to a tracked target's on another ecosystem,
`min()` with the within-ecosystem value, dated snapshots, and no second-chain
RPC inside a scorer (root `METHODOLOGY.md`, paragraph "Convention (decided
2026-09-20)"). On Plasma:

- Pendle's owner Safe `0x7877AdFa...75Ac` (3-of-5) is the same address with
  the same 5 owners as Pendle's Safe on Robinhood Chain (snapshot
  `_KNOWN_PENDLE_ROBINHOOD_SAFE_OWNERS_2026_09_20`).
- Plasma's Euler DAO Safe `0xfD30738f...E539` (4-of-8) has the same 8 signers
  as Monad's Euler DAO Safe, at a different address (snapshot
  `_KNOWN_EULER_DAO_SIGNERS_2026_09_19`). Both Euler targets share that
  Safe, so both move.

Before this, the Pendle overlap was recorded only as a finding of
`scripts/check_cross_ecosystem_overlap.py`, and both Euler scorers reported
100 with a note that no cross-ecosystem check had been done; neither was in
the score. Every other Plasma target is unchanged.

### Current on-chain scores (re-push, 2026-09-20)

Read back with plain `getScore()` after the push; 9 targets, all
`lastUpdated` 1789863481. The 2026-09-19 read-backs quoted earlier in this
file are kept as history.

| Idx | Target | admin | multisig | timelock | oracle | cross | composite |
|---|---|---|---|---|---|---|---|
| 0 | Plasma L1 validator-set authority (Aquila) | 50 | 50 | 0 | 100 | 100 | 35 |
| 1 | Aave V3 Pool (PoolAddressesProvider) | 65 | 100 | 50 | 100 | 80 | 71 |
| 2 | Pendle (Router + Market Factory V6) | 65 | 55 | 0 | 100 | **80** | 43 |
| 3 | Ethena USDe OFT | 55 | 100 | 0 | 100 | 80 | 52 |
| 4 | Euler V2 eVaultFactory | 70 | 80 | 68 | 100 | **80** | 72 |
| 5 | Euler V2 AccessControlEmergencyGovernor | 68 | 80 | 55 | 100 | **80** | 68 |
| 6 | Fluid (Instadapp) Liquidity | 40 | 100 | 70 | 100 | 100 | 67 |
| 7 | Telos Consilium TelosC Surge | 40 | 45 | 0 | 100 | 100 | 30 |
| 8 | Yuzu Money yzUSD | 20 | 100 | 55 | 100 | 100 | 55 |

Bold marks the three cells that changed against the 2026-09-19 push.

Row 6 is what this push wrote. The later re-push of the same evening (last section) rewrote it: Fluid now
reads 65 / 55 / 55 / 100 / 80 / 59 (proposer and executor signer sets resolved, same committee as Fluid on
Arbitrum, see `data/fluid_liquidity_plasma_2026-09-20_signers.md`).

### 2026-09-20 (later): Yuzu Money's placeholder replaced by the traced authority chain (pushed on-chain)

Row 8 above (Yuzu Money yzUSD, 20 / 100 / 55 / 100 / 100 / 55) was a placeholder: adminKey 20 rested on a
`hasRole(TIMELOCK_ADMIN_ROLE, ...)` test with the OpenZeppelin-4 hash against OpenZeppelin-5 timelocks, which
administer through `DEFAULT_ADMIN_ROLE`. Traced live on two RPCs and adversarially re-verified (full record:
`data/finding_2026-09-20-yuzu-authority-trace.md`): a 2-day timelock (4-of-5 Safe) owns every ProxyAdmin, a
12-hour timelock (3-of-5 Safe, the same five bare-EOA signers) holds `ADMIN_ROLE`, and that 3-of-5 Safe also
holds `POOL_MANAGER_ROLE` and `DISTRIBUTOR_ROLE` on yzPP directly with no delay. Scored by the instant-Safe-seat
convention:

| Idx | Target | admin | multisig | timelock | oracle | cross | composite |
|---|---|---|---|---|---|---|---|
| 8 | Yuzu Money yzUSD, before that re-push | 20 | 100 | 55 | 100 | 100 | 55 |
| 8 | Yuzu Money yzUSD, on the oracle since the 2026-09-20 re-push | **65** | **55** | **0** | 100 | 100 | **43** |

Pushed by Spap on 2026-09-20 (Plasma testnet, tx `0x490f5bb8ec6c6a436bfde4aee358928e24b8ac5597e74b72cd2f0c5f01adbb1a`, block 34,083,939, status 1); the full 9-target scorer output read back identical to the oracle (0 differences). The Safes are
registered as the group `yuzu` in the cross-ecosystem sweep registry (72 groups, no overlap found).

## 2026-09-20 (evening) re-push: Fluid Liquidity signer sets resolved, pushed on-chain

| Field | Value |
|---|---|
| Oracle | `0x50840a7667baEa9D05ad4ae3dCeb384724b58720` (Plasma testnet, chain 9746) |
| `updateScores()` tx (9 targets) | [`0x3c709f07...f645`](https://testnet.plasmascan.to/tx/0x3c709f07756416a72c5fce1bd96ffa482b52df3c8bd2a9d283f88aa263e0f645) |
| Block | 34,100,595, status 1, gasUsed 180,599, from the updater `0x20630C6Ab4BA48a80edA46F77b9b6e987A8f32f5` |
| What changed | Fluid Liquidity only: 40 / 100 / 70 / 100 / 100 (composite 67) became 65 / 55 / 55 / 100 / 80 (composite 59). The other 8 targets were re-written with unchanged values. |
| Read back | Plain `getScore()` on all 9 targets equals the scorer output of commit `aa6007c` exactly (0 differences), `trackedTargetsCount()` = 9. |
| Approved | maker-checker #133 (verifier the verifier), scorer change pushed as `aa6007c` before the send |

Why: the first pass tried only the Safe ABI on the Timelock's proposer and executor and left their signer strength
unresolved. The proposer is an Avocado multisig (`requiredSigners()` 6, `signers()` 12) and the executor a Safe 3-of-5,
the same two contracts with the same signers as on Arbitrum One, where the tracked Fluid Liquidity already scored 59.
The Plasma scorer now reads both, scores the weaker of the two like the Arbitrum scorer, caps `timelockScore` at 55 for the
bounded auths and guardian that act without the delay, and folds the committee overlap into `crossExposureScore` (80).
Evidence and the read-only check: `data/fluid_liquidity_plasma_2026-09-20_signers.md` and
`scripts/fluid_signers_check.py`. The re-push was run with the pipeline's
`runs/2026-09-20-scorer-fixes/plasma-repush/repush_plasma_fluid.sh` (chain and scorer compared before the send:
exactly Fluid differed).

### Current on-chain scores (evening re-push, 2026-09-20)

| Idx | Target | admin | multisig | timelock | oracle | cross | composite |
|---|---|---|---|---|---|---|---|
| 0 | Plasma L1 validator-set authority (Aquila) | 50 | 50 | 0 | 100 | 100 | 35 |
| 1 | Aave V3 Pool (PoolAddressesProvider) | 65 | 100 | 50 | 100 | 80 | 71 |
| 2 | Pendle (Router + Market Factory V6) | 65 | 55 | 0 | 100 | 80 | 43 |
| 3 | Ethena USDe OFT | 55 | 100 | 0 | 100 | 80 | 52 |
| 4 | Euler V2 eVaultFactory | 70 | 80 | 68 | 100 | 80 | 72 |
| 5 | Euler V2 AccessControlEmergencyGovernor | 68 | 80 | 55 | 100 | 80 | 68 |
| 6 | Fluid (Instadapp) Liquidity | **65** | **55** | **55** | 100 | **80** | **59** |
| 7 | Telos Consilium TelosC Surge | 40 | 45 | 0 | 100 | 100 | 30 |
| 8 | Yuzu Money yzUSD | 65 | 55 | 0 | 100 | 100 | 43 |

Bold marks the cells that changed against the earlier 2026-09-20 push.

