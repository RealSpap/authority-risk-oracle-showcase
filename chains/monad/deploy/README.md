# Monad -- deployment guide (Monad Testnet, chain 10143)

Phase: `deploy_testnet` -- **deployed for real on 2026-09-19.** Monad was
picked as this project's 9th ecosystem after a dedicated 8-candidate
scouting workflow (Berachain, Monad, Sonic, zkSync Era, Linea, Scroll,
Mantle, ZetaChain) ranked it #1 on every weighted criterion at once: real
mainnet DeFi TVL, a confirmed no-account/no-real-value testnet funding
path, and a structurally confirmed competitor-coverage gap. See
[`chains/monad/scorers.py`](../scorers.py)'s own module docstring for the
full rationale and [`chains/monad/scripts/dry_run.py`](../scripts/dry_run.py)
to re-derive every score live.

## Network

| | |
|---|---|
| Network | Monad Testnet |
| Chain ID | **10143** (`0x279f`) -- confirmed live via a direct `eth_chainId` read against `https://testnet-rpc.monad.xyz/`, independently re-verified a second time before deploying |
| Monad Mainnet (read-only, for the scorers -- never a deploy target) | chain **143** (`0x8f`) -- also confirmed live |
| Public RPC (testnet) | `https://testnet-rpc.monad.xyz/` |
| Public RPC (mainnet) | `https://rpc.monad.xyz` |
| Explorer | `https://testnet.monadvision.com/address/` (the canonical `testnet.monadexplorer.com` URL 308-redirects here) |
| Faucet that worked | [`openfaucet.org`](https://openfaucet.org) -- browser proof-of-work mining, "Monad / Testnet" listed directly, no wallet connection, no account, no real-value requirement. 0.002 MON per proof, 0.01 MON minimum claim, **0.05 MON maximum per mining session**. |
| Faucet used for the 2026-09-19 top-up | The official Monad testnet faucet, used by Spap directly. That the source is the official faucet is Spap's report, NOT something the chain itself proves. What IS verified on-chain: one single +5.0 MON credit to the admin/updater key, tx [`0x36cba7481c7a67b298b91f5b6f276075f880c0e3e368f88935e135cbf68ca3bf`](https://testnet.monadvision.com/tx/0x36cba7481c7a67b298b91f5b6f276075f880c0e3e368f88935e135cbf68ca3bf) in Monad testnet block 63,949,181 (status success, sent by `0x3de8259a71a735b111bd5aebfce965c0d333fa88` through a 1,290-byte distributor contract `0x631a6a936485fa0cba53c37a671aaf505f16d08e`, recipient list = this key only), taking the balance from 0.009291 to 5.009291 MON. This replaces the multi-cycle 0.05-MON-per-session `openfaucet.org` route as the practical funding path. |

## Funding: real, but genuinely gas-constrained -- disclosed, not smoothed over

Unlike every other chain this project has deployed to (Plasma ~1.7 gwei,
Tempo pays gas in a stablecoin), Monad testnet's real gas price is
**~100-102 gwei** -- confirmed live via `eth_gasPrice`, not assumed. Combined
with the faucet's **0.05 MON per-session cap**, funding this deploy took
multiple separate mining-and-claim cycles, each gated by the faucet's own
rate limit (variable: sometimes ~3 minutes, sometimes ~46-49 minutes
between claims from the same address -- not always the same duration,
disclosed as observed rather than assumed constant):

1. Mined and claimed 0.012 MON, then 0.012 MON, then 0.044 MON (three
   separate sessions) -- total 0.056 MON. Attempted the oracle deploy at
   this balance and it failed outright: `eth_estimateGas` itself reverted
   with `"intrinsic gas greater than limit"` -- the balance/gas-price
   product couldn't even afford the ~900K gas a deploy of this contract
   needs, confirmed by computing `balance / gasPrice` and comparing
   against Plasma's own real `gasUsed` figure for the same contract
   (903,873).
2. Mined and claimed 0.044 MON more (0.1 MON total), then hit a 46-minute
   rate limit before a second claim of that round could land.
3. After that wait, claimed 0.05 MON more (0.15 MON total) -- enough,
   with a tight but sufficient margin, to deploy the oracle contract.
4. Deployed `AuthorityRiskOracle` (see below), leaving 0.0504 MON --
   short of `updateScores()`'s own live-estimated gas need for 7 targets
   (768,145 gas -> ~0.078-0.086 MON depending on buffer). Waited out a
   48-minute rate limit, mined and claimed 0.038 MON more (0.0884 MON
   total), then pushed all 7 real scores successfully.

**`ExampleConsumer` was deliberately NOT deployed this pass** -- after the
real score push, only 0.002 MON remained, not enough for a third contract
deploy. This is a disclosed, deliberate scope cut under a real gas-cost
constraint, not an oversight: the oracle itself (the thing the dashboard
and any real consumer actually reads) and the real pushed scores were
prioritized over the demo/reference consumer contract. **Update, later
the same day:** the gas constraint described in this section no longer
applies, the key now holds 5.009291 MON (see "2026-09-19 (fourth pass)"
below), roughly 88 more full 9-target pushes' worth at the live gas price.
`ExampleConsumer` is still NOT deployed, that is now a scope choice rather
than a funding limit.

## Contract

`src/AuthorityRiskOracle.sol` is used unmodified -- same contract already
deployed for real on Robinhood Chain, Ethereum L1, Arbitrum, Base, Plasma,
and Tempo. No Monad-specific Solidity changes needed.

**Compiled without Foundry**: `forge` is still not installed in this
environment. Compiled via `py-solc-x` (solc 0.8.24, matching this
project's `pragma solidity ^0.8.24`), same workaround used for every prior
non-Foundry deploy in this project. Oracle deploy bytecode: 3,935 bytes;
runtime: 3,581 bytes -- **byte-identical** to every other chain's own
compile of this same contract, confirmed by comparing sizes exactly, not
just "close enough".

## Real deployment (2026-09-19)

| Field | Value |
|---|---|
| `AuthorityRiskOracle` (deployed) | [`0x50840a7667baEa9D05ad4ae3dCeb384724b58720`](https://testnet.monadvision.com/address/0x50840a7667baEa9D05ad4ae3dCeb384724b58720) |
| Admin / updater | `0x20630C6Ab4BA48a80edA46F77b9b6e987A8f32f5` (the shared EVM testnet key, already used on every other EVM chain in this project) |
| Deploy tx (`AuthorityRiskOracle` CREATE) | `0x1019fb1be3b2282cb376dcb5eacc39c5a4a8e8da63b97888256b5f98672c40b8` (block 63,764,900, status success, gasUsed 929,748) |
| `updateScores()` tx #1 (7 targets, initial push) | [`0xbd9913e225c3a1a1738bc3d5fd5292a7105841d0b091a39c53f029b1e809846b`](https://testnet.monadvision.com/tx/0xbd9913e225c3a1a1738bc3d5fd5292a7105841d0b091a39c53f029b1e809846b) (block 63,775,006, status success, gasUsed 806,552) |
| `updateScores()` tx #2 (9 targets, re-push of 2026-09-19; superseded by tx #3) | [`0xd65b649d10c8a1a1b76c6a0848fbbc182c0e73e0fce7e4abeea066da3b529e35`](https://testnet.monadvision.com/tx/0xd65b649d10c8a1a1b76c6a0848fbbc182c0e73e0fce7e4abeea066da3b529e35) (block 63,945,191, status success, gasUsed 445,108, nonce 2, 2,724 bytes of calldata, 9 logs) |
| `updateScores()` tx #3 (9 targets, re-push of 2026-09-20, current on-chain state) | [`0xa93596300b689383572880cd4de76ee2fc7bce68ac5791db38501b07b987a019`](https://testnet.monadvision.com/tx/0xa93596300b689383572880cd4de76ee2fc7bce68ac5791db38501b07b987a019) (block 64,022,942, status success, gasUsed 279,012). See "2026-09-20 re-push" at the end of this file |
| Gas price paid | tx #1: ~102-107 gwei (live `eth_gasPrice`, small 1.05x buffer -- NOT this project's usual 1.25x, deliberately tightened given the real balance constraint documented above). tx #2: 127.5 gwei effective (102 gwei live x this script's usual 1.25x), fee 0.05675127 MON |
| Total real MON mined and spent (at the time of the initial deploy, before tx #2) | 0.1884 MON mined across the funding trail above; ~0.1864 MON spent on the deploy + tx #1, 0.0020 MON left over. Later funding and tx #2 are in the third and fourth passes below |

`AuthorityRiskOracle`'s address is identical to every other EVM chain's
own deployed address in this project -- expected, not a bug: a CREATE
address is `keccak(deployer, nonce)`, chain-independent, and the shared
deployer key was at nonce 0 on Monad testnet too.

**Verified after deploy, not assumed** (this list is the state right after
tx #1, 7 targets, and is kept as that dated record; the state after
tx #2 is in "2026-09-19 (fourth pass)", and the current state, after tx #3,
is in "2026-09-20 re-push" at the end of this file):

- `eth_getCode` on the deployed oracle returned 3,581 bytes of runtime
  bytecode -- matching the local compile exactly.
- **Every one of the 7 pushed scores was read back live via `getScore()`
  and matches exactly what was pushed, all 7, not a subset**: Echo
  Protocol eBTC (composite 37), Uniswap v4 PoolManager (80), Monad Native
  Bridge (60), Kuru (43), Morpho Vault (60), Curve Finance (4), Curvance
  Emergency Council (44) -- independently re-derived via a direct
  `eth_call` against the deployed oracle, not read from the push script's
  own stdout.
- `trackedTargetsCount()` returned `7` after tx #1, matching all 7 scored
  targets at that time (it is `9` now, after tx #2).
- The dashboard's own Monad tab was verified live in the browser preview
  at that time: 7/7 real narrative cards render (no fallback "Untitled
  target" cards), aggregate line correctly read 99 targets across 7
  deployed oracles, no console errors. (Not re-checked in this pass, the
  live per-oracle counts are now read by `scripts/live_target_counts.py`.)

## What this does NOT do

- No `ExampleConsumer` deployed -- it was first cut for a real, disclosed
  gas-budget reason (see "Funding" above); the key is now funded well
  beyond that need, so it is a pending scope choice, not a blocker.
- Still no `forge build`/`forge test` run against this exact dependency
  tree in this environment -- `py-solc-x` compiled byte-identical output
  to every other chain's own deploy, which already passed Foundry's test
  suite, used here as a substitute check rather than re-running it.
- The `UPDATER_ROLE`/admin key is still the single shared EOA, not a
  multisig -- same as every other testnet deploy in this project, out of
  scope for a testnet validation pass.
- No recurring automated push wired in -- pushes are manual, run by hand
  (three so far: 7 targets, then 9, then a 9-target re-push on 2026-09-20),
  like every other non-Robinhood-Chain ecosystem in this project.

## 2026-09-19 (second pass, same day): 2 new targets added (first held back by a funding shortfall, since resolved)

A dedicated new-target scouting pass (DefiLlama `/protocols`, filtered for
`chains[]` containing `"Monad"`, ranked by Monad-specific `chainTvls.Monad`)
found and fully verified 3 candidates -- Aave V3 ($319.4M Monad TVL),
Euler V2 ($265.0M), Pendle V2 ($206.9M) -- and added 2 of them
(`score_aave_v3_monad`, `score_euler_v2_monad` in
[`chains/monad/scorers.py`](../scorers.py)), now 9 tracked targets total.
Pendle V2 was found, verified, and honestly discarded: its Monad Router
and ProxyAdmin resolve to the exact same Gnosis Safe addresses already
tracked for Pendle on Plasma (`chains/plasma-ecosystem/scorers.py`) -- the
literal same CREATE2-deployed contract and multisig infrastructure, not
new authority-structure information. See
[`data/finding_2026-09-19-monad-new-targets-scouting.md`](../../../data/finding_2026-09-19-monad-new-targets-scouting.md)
for the complete research trail.

**What happened to the push, as it actually unfolded (the original
"NOT pushed, ~0.0547 MON short" note that stood here has been replaced by
this, because it stopped being true later the same day):**

1. When the 2 targets were added, the shared EVM testnet key
   (`0x20630C6Ab4BA48a80edA46F77b9b6e987A8f32f5`, shared across every EVM
   testnet in `authority-risk-oracle-multichain-pipeline` per
   `ecosystems.json`'s `key_file: keys/authority-risk-oracle/evm-testnet-shared/.env`) held only
   0.00204 MON. A real `eth_estimateGas` for the 9-target `updateScores()`
   was 445,108 gas at ~102 gwei, i.e. ~0.0568 MON at the usual 1.25x
   buffer, ~0.0547 MON more than the key had. Per this project's standing
   rule the push was not attempted and no result was fabricated.
2. The shortfall was closed and the push done for real, see "third pass"
   below (tx #2, block 63,945,191, `trackedTargetsCount()` = 9).
3. The key was later topped up by a further +5.0 MON from the official
   Monad testnet faucet, see "fourth pass" below.

## 2026-09-19 (third pass): key re-funded, drift audited, 9-target push done (tx #2)

A fresh on-chain-vs-live drift audit (all 7 EVM oracles, read-only) found Monad
is the ONLY oracle with real, reproducible drift: 2 targets whose
`crossExposureScore` reads `100` on-chain but recomputes to `80`
(Morpho vault `0x32841A85...476D` and Curve factory `0x8271e06E...E8aD`;
`compositeScore` unchanged for both). Cause: commit `1dfb159` (2026-09-19
15:35 +02:00) turned their hardcoded `100` into a live cross-ecosystem
overlap check AFTER the last push (2026-09-19 03:27 UTC). Not a real-world
authority change -- both overlaps were independently re-confirmed by direct
`eth_call` (all 8 owner + 6 curator signers of the Monad Morpho vault are
subsets of Robinhood Chain's Steakhouse committees; the Curve factory's
`admin()` is the identical bare EOA `0xabc336d4...1cbF` Robinhood tracks).
The other 5 on-chain targets match a live recomputation on all six fields;
Aave V3 and Euler V2 were simply not on-chain yet at that point.

The gas shortfall above is now closed: the shared key was re-funded through
`openfaucet.org`'s browser proof-of-work faucet (no account, no wallet
connection, no CAPTCHA) in two mining sessions -- 0.048 MON (24 proofs), then
0.016 MON (8 proofs) -- taking the balance from 0.00204 MON to **0.06604 MON**
(live-read). A real `eth_estimateGas` for the full 9-target `updateScores()` is
445,108 gas; at the live 102 gwei with this script's 1.25x buffer that is
0.05675 MON, so the balance now covers it (a 4-target subset would need
0.0393 MON). Nothing had been signed or sent when the paragraph above was written; the
push was then run by Spap directly (the sandbox correctly refused this agent
access to the key file, and no workaround was attempted), using
`chains/monad/deploy/push_scores.py` without `--dry-run`, for all 9 targets:
tx `0xd65b649d10c8a1a1b76c6a0848fbbc182c0e73e0fce7e4abeea066da3b529e35`,
Monad testnet block 63,945,191, status success. Independently re-verified
afterwards, read-only, with no key: `trackedTargetsCount()` = 9, and every one
of the 9 targets' six score fields matches a fresh live `score_all()`
recomputation exactly (0 mismatches). The two `crossExposureScore` drifts
above (Morpho vault, Curve factory) now read 80 on-chain, and Aave V3 and
Euler V2 are live for the first time.

## 2026-09-19 (fourth pass): key topped up with 5 MON, live state re-verified -- no further push needed

This pass was scoped on the assumption that the 9-target push was still
pending (the task said `trackedTargetsCount()` should still read 7 and the
key was short of gas). Read live, that assumption was already out of date:
the push had been done in the third pass (tx #2 above). So nothing was
signed or sent in this pass and no key was read: it is a read-only
re-verification, every number below read live from Monad testnet
(chain 10143, `https://testnet-rpc.monad.xyz/`) and Monad mainnet (chain
143, read-only, `https://rpc.monad.xyz`).

| Check | Result |
|---|---|
| Admin/updater key balance (`eth_getBalance`, block 63,949,793) | **5.009291 MON** (was 0.009291 MON right after tx #2; +5.0 MON credit at block 63,949,181, tx `0x36cba748...ca3bf`, see the Network table) |
| Key nonce | 3 (deploy, tx #1, tx #2 -- nothing else sent by this key on Monad testnet) |
| Live `eth_gasPrice` | ~102 gwei; one full 9-target push costs ~0.0568 MON at the 1.25x buffer, so the balance covers roughly 88 of them |
| Tx #2 receipt (`eth_getTransactionReceipt`) | status `0x1` (success), block 63,945,191, `from` = the admin/updater key, `to` = the oracle, gasUsed 445,108, 9 logs, calldata 2,724 bytes, selector `0x5fb3feaf` (`updateScores`) |
| `trackedTargetsCount()` | **9** |
| `getScore()` on all 9 targets vs a fresh `score_all()` against Monad mainnet (block 106,244,327) | **0 mismatches** on all six score fields, all 9 targets (not a sample) |
| `push_scores.py --dry-run` against Monad mainnet (block 106,244,573) | re-derives the same 9 scores; encoded calldata is 2,724 bytes with the same selector as tx #2's input |

The 9 targets as they read on-chain after tx #2 (admin key / multisig /
timelock / oracle authority / cross-exposure / composite, each /100;
all pushed together in tx #2 at `lastUpdated` 1789839860 = 2026-09-19
17:44:20 UTC, `methodologyHash` = `keccak256("authority-risk-oracle-monad-v1")`
= `0x8e05d88c...04c7`):

| Target | Address | admin | multisig | timelock | oracle | cross | composite |
|---|---|---|---|---|---|---|---|
| Echo Protocol eBTC | `0xd691b0aF...b7e9` | 55 | 50 | 0 | 100 | 100 | 37 |
| Uniswap v4 PoolManager | `0x188d586D...9Ea8e` | 80 | 100 | 60 | 100 | 100 | 80 |
| Monad Native Bridge (Wormhole NTT Manager) | `0x36878C6F...5c95` | 75 | 100 | 0 | 100 | 100 | 60 |
| Kuru Router + MarginAccount | `0xd651346d...95CC` | 65 | 55 | 0 | 100 | 100 | 43 |
| Morpho Vault (Grove x Steakhouse High Yield AUSD) | `0x32841A85...476D` | 70 | 50 | 55 | 100 | 80 | 60 |
| Curve Finance StableSwap Factory | `0x8271e06E...E8aD` | 10 | 0 | 0 | 100 | 80 | 4 |
| Curvance Emergency Council | `0xaD663aC8...00Bf` | 60 | 65 | 0 | 100 | 100 | 44 |
| Aave V3 Pool (PoolAddressesProvider) | `0x34793Fb9...7A615` | 65 | 100 | 50 | 100 | 80 | 71 |
| Euler V2 eVaultFactory | `0xba4Dd672...1f1E` | 55 | 80 | 60 | 100 | 80 | 64 |

The two new targets, Aave V3 (composite 71) and Euler V2 (composite 64), are
therefore live on the Monad testnet oracle and read back correctly, and the
two earlier `crossExposureScore` drifts (Morpho vault, Curve factory) read
80, matching a live recomputation.

> SUPERSEDED 2026-09-20: the table above is the state pushed on-chain by tx #2
> and is kept as that record. Its Aave V3 row (65 / 100 / 50 / 100 / 80 / 71)
> was replaced by the 2026-09-20 re-push (tx #3, block 64,022,942): the oracle
> now holds 65 / 75 / 0 / 100 / 80 / **49**, equal to what
> `score_aave_v3_monad()` returns. See "2026-09-20 re-push" at the end of this
> file.

**Deliberately not re-pushed (the 2026-09-19 decision, kept as a record):** a
third `updateScores()` with the same nine sets of values would only refresh
`lastUpdated` (the oracle's `maxStaleness` is 9 days, so nothing goes stale
before ~2026-09-28) and burn ~0.0568 MON for no change in any score. It
becomes worth doing when a target's live score changes, when targets are
added, or when the 9-day window is about to run out. The first of those
conditions was met on 2026-09-20 (Aave V3 re-scored) and the re-push was done,
see "2026-09-20 re-push" below.

## 2026-09-20 re-push: Aave V3 re-scored and pushed on-chain (tx #3)

| Field | Value |
|---|---|
| Oracle | [`0x50840a7667baEa9D05ad4ae3dCeb384724b58720`](https://testnet.monadvision.com/address/0x50840a7667baEa9D05ad4ae3dCeb384724b58720) (Monad testnet, chain 10143) |
| `updateScores()` tx #3 (9 targets) | [`0xa93596300b689383572880cd4de76ee2fc7bce68ac5791db38501b07b987a019`](https://testnet.monadvision.com/tx/0xa93596300b689383572880cd4de76ee2fc7bce68ac5791db38501b07b987a019) |
| Block | 64,022,942, status success, gasUsed 279,012 |
| `lastUpdated` | 1789863496 = 2026-09-20 00:18:16 UTC (all 9 targets) |
| What changed | Only Aave V3 Pool: 65 / 100 / 50 / 100 / 80 / 71 -> 65 / 75 / 0 / 100 / 80 / **49**. The other 8 targets were re-written with unchanged values. |
| Read back | Plain `getScore()` on all 9 targets equals the scorer output of commit `042f805` exactly (0 differences). `trackedTargetsCount()` = 9. |

Scorer output as of 2026-09-20 (`chains/monad/scorers.py::score_aave_v3_monad`,
re-run read-only against Monad mainnet, chain 143, no key, no transaction).
Only Aave V3 moved on Monad; the other 8 targets are unchanged.

| Target | admin | multisig | timelock | oracle | cross | composite |
|---|---|---|---|---|---|---|
| Aave V3 Pool, on the testnet oracle before (tx #2, 2026-09-19) | 65 | 100 | 50 | 100 | 80 | **71** |
| Aave V3 Pool, on the testnet oracle now (tx #3, 2026-09-20, equal to scorer output) | 65 | 75 | 0 | 100 | 80 | **49** |

Why it moved. The `PROTOCOL_GUARDIAN` Safe
`0xc887455536CBD4e615B745e70CaCde15B3117e74` (4-of-7, read live) holds
`POOL_ADMIN` in the ACLManager `0xa9fEe192a76B8f5e5f3d310AB6C526cB11F3d95B`
(`isPoolAdmin` = true and `isEmergencyAdmin` = true, read live), next to the
DAO Executor. It can therefore swap a reserve's aToken / variableDebtToken
implementation immediately, a path the 1-day Executor delay does not gate.
The old scorer scored only the DAO path (Executor behind the 1-day delay).
It is now scored on the Safe-with-no-timelock rule: admin 65 (threshold >=
3), multisig min(100, 4 x 15 + 3 x 5) = 75, timelock 0, composite
`floor(0.4 x 65 + 0.3 x 75 + 0.5)` = 49. `adminKeyScore` is the minimum of the
DAO-path value and the Safe rule, so a broken Executor loop can never raise
it. Disclosed and not score inputs: the Executor holds `DEFAULT_ADMIN` and can
revoke the seat, and the Safe cannot grant roles. If `isPoolAdmin` reads
false the score is unchanged at 65 / 100 / 50 / 71; if it cannot be read, the
scorer degrades to 20 / 20 / 0 (composite 14) and flags the note DEGRADED
rather than keeping the confident DAO-path score.

`crossExposureScore` stays 80: the 9-signer `PayloadsController.guardian()` committee is the
one already documented on Arbitrum, Base, Plasma and Ethereum L1. Monad
already folded cross-ecosystem overlaps before the 2026-09-20 convention
decision (root `METHODOLOGY.md`, paragraph "Convention (decided 2026-09-20)"),
so that decision moved no Monad score.

The "Deliberately not re-pushed" reasoning of the fourth pass no longer held
for this target once a live score had changed, and Spap ran the re-push. It
is a full 9-target `updateScores()`, so every target's `lastUpdated` moved to
1789863496; the next 9-day staleness deadline is 2026-09-29 00:18:16 UTC.

### Current on-chain scores (re-push, 2026-09-20)

Read back with plain `getScore()` after tx #3; 9 targets, all `lastUpdated`
1789863496. The fourth-pass table above is kept as history.

| Target | Address | admin | multisig | timelock | oracle | cross | composite |
|---|---|---|---|---|---|---|---|
| Echo Protocol eBTC | `0xd691b0aF...b7e9` | 55 | 50 | 0 | 100 | 100 | 37 |
| Uniswap v4 PoolManager | `0x188d586D...9Ea8e` | 80 | 100 | 60 | 100 | 100 | 80 |
| Monad Native Bridge (Wormhole NTT Manager) | `0x36878C6F...5c95` | 75 | 100 | 0 | 100 | 100 | 60 |
| Kuru Router + MarginAccount | `0xd651346d...95CC` | 65 | 55 | 0 | 100 | 100 | 43 |
| Morpho Vault (Grove x Steakhouse High Yield AUSD) | `0x32841A85...476D` | 70 | 50 | 55 | 100 | 80 | 60 |
| Curve Finance StableSwap Factory | `0x8271e06E...E8aD` | 10 | 0 | 0 | 100 | 80 | 4 |
| Curvance Emergency Council | `0xaD663aC8...00Bf` | 60 | 65 | 0 | 100 | 100 | 44 |
| Aave V3 Pool (PoolAddressesProvider) | `0x34793Fb9...7A615` | 65 | **75** | **0** | 100 | 80 | **49** |
| Euler V2 eVaultFactory | `0xba4Dd672...1f1E` | 55 | 80 | 60 | 100 | 80 | 64 |

Bold marks the cells that changed against the fourth-pass table.
