# Tempo -- deployment guide (Tempo Testnet / Moderato, chain 42431)

**Real deployment done, 2026-09-19** (phase `deploy_testnet`, action
approved 2026-09-18): `AuthorityRiskOracle` deployed at
[`0x50840a7667baEa9D05ad4ae3dCeb384724b58720`](https://explore.testnet.tempo.xyz/address/0x50840a7667baEa9D05ad4ae3dCeb384724b58720),
`ExampleConsumer` at `0xB7403b365a58B31Ae030DB423f6B703AD67f003a`, all 13
tracked targets pushed for real via `updateScores()` and read back live via
`getScore()`. See "Real deployment (2026-09-19)" below for the full record.
Everything below this point that still reads as a plan (the 2026-09-18 pass)
is kept as-is for the historical trail; it was accurate when written.

Latest state: the oracle now tracks 14 targets (Morpho Blue core added
2026-09-19) and was re-pushed on 2026-09-20 (Morpho Blue core cross exposure
100 -> 80, tx `0xcdc3cc09...aa44b`, block 36054236). The current on-chain
table is in "2026-09-20 re-push" at the end of this file.

---

Phase at time of writing: `scoring_build` (2026-09-18 pass). This README
documents how the project's **existing** native EVM contract
(`src/AuthorityRiskOracle.sol`, reused as-is, no Tempo-specific Solidity
changes) will be deployed to Tempo Testnet (Moderato), and what had been
verified as of that pass. **No deployment had happened yet** -- `scoring_build`,
not `deploy_testnet`, was the phase this ecosystem was in during that pass
(see `ecosystems.json`), and the deployer key's actual fee-token balance on
Moderato was unconfirmed either way (see "Gas token and funding" below, a
real, Tempo-specific wrinkle none of the other EVM ecosystems in this repo
have).

## Network

| | |
|---|---|
| Network | Tempo Testnet (Moderato) |
| Chain ID | **42431** -- confirmed live this run via `cast chain-id --rpc-url https://rpc.moderato.tempo.xyz` |
| Tempo Mainnet (read-only, for the scorer -- never a deploy target) | chain **4217** -- also confirmed live this run via `cast chain-id --rpc-url https://rpc.tempo.xyz` |
| Public RPC (official, testnet) | `https://rpc.moderato.tempo.xyz` |
| Public RPC (official, mainnet) | `https://rpc.tempo.xyz` |
| Public RPC (independent, mainnet, used for dual-read cross-checks) | `https://tempo-rpc.publicnode.com` |
| Explorer (testnet) | `https://explore.testnet.tempo.xyz` |
| Faucet | `tempo_fundAddress` JSON-RPC method on the Moderato endpoint ([protocol/rpc](https://tempo.xyz/developers/docs/protocol/rpc/), see `../METHODOLOGY.md` section 2) -- **called for real 2026-09-19**: confirmed live to take a single `address` param, no captcha/login/real-value deposit, so it is exactly the "free path with no guardrail" a later pass was explicitly told it could use itself. See "Real deployment (2026-09-19)" below. |

Both chain IDs were re-confirmed live this run, matching
`../METHODOLOGY.md` section 2's own table exactly (that table was itself
already primary-sourced during the discovery phase, not re-derived from
scratch here).

## Contract

`src/AuthorityRiskOracle.sol` is used unmodified -- the SAME contract every
other EVM ecosystem in this repo (`ethereum-l1`, `arbitrum-ecosystem`,
`base-ecosystem`, `hyperliquid`) already deploys or prepares per-chain. No
Tempo-specific Solidity changes are needed: the contract is chain-agnostic
(`AccessControl`-gated `UPDATER_ROLE`, `updateScore`/`updateScores`,
`getScore`, `isStale`). `../METHODOLOGY.md` section 5 already established,
during the methodology phase, that standard Foundry/Hardhat deployment
works unchanged on Tempo (EVM-compatible, targeting the Osaka hard fork).

`script/Deploy.s.sol` (repo root, also reused unmodified) deploys
`AuthorityRiskOracle` with `admin = deployer` and a demo `ExampleConsumer`
wired to it.

The `updateScores(address[],AuthorityScore[])` function selector was
verified live this run via
`cast sig "updateScores(address[],(uint8,uint8,uint8,uint8,uint8,uint8,uint64,bytes32)[])"`
-> `0x5fb3feaf` -- the same selector every other EVM ecosystem's README in
this repo independently re-derives (it depends only on the shared
`AuthorityRiskOracle` ABI, not on anything Tempo-specific), and matching
the calldata `deploy/push_scores.py --dry-run` actually encodes below
(byte-for-byte, not assumed).

## Build and test (this pass, read-only, no deploy)

Every ecosystem's agent shares this one clone -- always pass separate
`--out`/`--cache-path` so parallel agents never clobber each other's build
artifacts:

```
forge build --out <this run's forge-out dir> --cache-path <this run's forge-cache dir>
forge test  --out <this run's forge-out dir> --cache-path <this run's forge-cache dir>
```

Result this run (2026-09-18): `Compiler run successful!` (30 files, Solc
0.8.36, 3 pre-existing lint warnings unrelated to this change --
`missing-events-arithmetic`, `require-revert-in-loop`, `block-timestamp`,
none Tempo-specific). `forge test`: **20/20 tests passed** (15 in
`AuthorityRiskOracle.t.sol` + 5 in `ExampleConsumer.t.sol`, 0 failed, 0
skipped) -- identical suite and result to every EVM sibling's own pass,
confirming the unmodified contract behaves the same regardless of which
chain's deploy this README targets.

## Gas token and funding -- a real Tempo-specific wrinkle

Unlike every other EVM ecosystem in this repo, Tempo has **no native gas
token** (`../METHODOLOGY.md` sections 1 and 5): `BALANCE`/`SELFBALANCE`/
`CALLVALUE` are always 0, and transaction fees are paid in a USD TIP-20
stablecoin (pathUSD from the testnet faucet, used as the fallback fee
token for non-TIP-20 calls). This means the Arbitrum/Base/Ethereum-L1
siblings' simple "check `cast balance`, it's 0 wei, funding is an open
thread" story does not directly transfer here -- `eth_getBalance` is not
obviously even the right question to ask on a chain with no native
balance concept.

Checked live this run, independently on **3 separate RPC endpoints**
(`rpc.tempo.xyz` mainnet, `rpc.moderato.tempo.xyz` testnet, and the
independent `tempo-rpc.publicnode.com`) and **2 different addresses** (the
shared deployer `0xA08a76457b758aFF9702dBf5b870679E1232B715` and an
arbitrary unrelated address, `0x0000...0001`):

```
curl -s -X POST -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"eth_getBalance","params":["0xA08a76457b758aFF9702dBf5b870679E1232B715","latest"]}' \
  https://rpc.tempo.xyz
# -> {"jsonrpc":"2.0","id":1,"result":"0x9612084f0316e0ebd5182f398e5195a51b5ca47667d4c9b26c9b26c9b26c9b2"}
```

Every one of these 3 endpoints returns the exact same value,
`0x9612084f0316e0ebd5182f398e5195a51b5ca47667d4c9b26c9b26c9b26c9b2`
(decimal `961208...` -- a repeating `...4242424242...` pattern once you
look past the leading digits), **for every address tried, including an
address that has obviously never been touched**. This is not a real,
per-account, spendable native balance -- it is a fixed sentinel/placeholder
`eth_getBalance` response, consistent with Tempo's own documented design
(no native gas token, so the standard EVM "native balance" RPC method has
nothing real to report). **Disclosed explicitly so a future pass does not
mistake this for "the deployer is funded"**: it is not evidence of funds
either way, real or otherwise, and it is not something a captcha/login
faucet or `tempo_fundAddress` call would change (it is unrelated to the
fee-token balance that actually matters for sending a transaction here).

What would actually be needed for a real `forge script ... --broadcast`
deploy on Moderato: the shared deployer key holding a nonzero balance of a
whitelisted TIP-20 fee token (pathUSD from the Moderato faucet is the
documented fallback). Checked live this run (the actually-correct
question, not `eth_getBalance`):

```
cast call 0x20c0000000000000000000000000000000000000 "balanceOf(address)(uint256)" \
  0xA08a76457b758aFF9702dBf5b870679E1232B715 --rpc-url https://rpc.moderato.tempo.xyz
# -> 0
```

pathUSD's precompile code (`0xef...`, confirmed present via `cast code` at
the same address on Moderato) resolves fine on testnet -- the deployer's
balance of it is a real, confirmed **0**, the correct "unfunded" fact for
this chain (replacing the "0 wei" framing the EVM siblings use, which does
not mean anything on a chain with no native gas token -- see the sentinel
`eth_getBalance` finding above). The faucet (`tempo_fundAddress`, see
"Faucet" row above) was not called this pass, per `keys/evm-testnet-
shared.json`'s "never request funding autonomously" instruction. Same
open thread as every EVM sibling, just correctly framed for Tempo's own
fee-token model: nothing to deploy for real until Spap funds the shared
deployer with pathUSD on Moderato (or another whitelisted fee token),
manually, if/when wanted.

## Pushing scores (dry-run only in this phase)

See [`push_scores.py`](push_scores.py), modeled directly on
`chains/hyperliquid/deploy/push_scores.py` (the closest sibling:
`chains/tempo/scorers.py::score_all()` also takes no RPC argument, since
Tempo's reads are the fixed, dual-cross-checked endpoints already defined
inside `scripts/methodology_test.py`, not one caller-supplied chain).
`--dry-run` re-derives every one of the 10 currently-tracked targets' scores
live from `chains/tempo/scorers.py` (Tempo MAINNET read state, the actual
target contracts) and encodes the `updateScores(address[],AuthorityScore[])`
calldata that WOULD be sent to the oracle on Moderato, printing the calldata
hex without ever building a transaction, signing, or sending anything. No
`PRIVATE_KEY` is required for `--dry-run`.

```
python3 chains/tempo/deploy/push_scores.py --dry-run
```

Confirmed 2026-09-18 (first pass), re-derived live from Tempo Mainnet, matching
`data/scored_targets_2026-09-18-controller-types.md` exactly:

| Target | Composite | crossExposure |
|---|---|---|
| Tempo L1 validator registry (ValidatorConfigV2) | 31 | 100 |
| USDC.e | 55 | 80 |
| USDT0 | 43 | 100 |
| pathUSD | 9 | 60 |
| USDB | 9 | 60 |
| cbBTC | 39 | 80 |
| PRIME | 39 | 80 |
| DLUSD | 9 | 60 |
| EURC.e | 55 | 80 |
| cUSD | 43 | 100 |

`updateScores()` calldata encoded to **3,012 bytes** for the 10 targets,
starting with selector `0x5fb3feaf` (matching the `cast sig` value above
byte-for-byte), `methodologyHash = 0xe653d28506a2817ef2eca397d999966bd56a35d9024e25cdfccbb618d1a3909a`
(`keccak256("authority-risk-oracle-tempo-v1")`). No transaction built,
signed, or sent; `ORACLE_RPC_URL`/`ORACLE_ADDRESS`/`PRIVATE_KEY` were not
read (`--dry-run` returns before that line, confirmed by source
inspection, same as every EVM sibling's script).

**Re-confirmed 2026-09-18 (second pass, same day), now with 13 targets**
after `score_vault_v2()` (rule R8, see `../METHODOLOGY.md` and
`../data/scored_targets_2026-09-18-vault-v2.md`) wired the 3 Morpho Vault
V2 instances into `chains/tempo/scorers.py::score_all()`. Full pipeline
re-run live end to end (`python3 chains/tempo/scripts/methodology_test.py`
equivalent, ~500 s wall clock -- `cUSD`'s plain-`TimelockController`
log-scan fallback, not any Vault V2 code, is the single slowest step): the
10 targets above are UNCHANGED (byte-for-byte identical scores, confirming
the Vault V2 addition introduces no regression), plus:

| Target | Composite | crossExposure |
|---|---|---|
| Sentora pathUSD (Morpho Vault V2) | 27 | 100 |
| Unnamed pathUSD Vault V2 feeding Sentora | 9 | 100 |
| Tempo Earn (Morpho Vault V2, Gauntlet-curated) | 61 | 100 |

`updateScores()` calldata re-encoded to **3,876 bytes** for all 13 targets
(confirmed by feeding this exact live run's scores through the same
ABI-encoding `push_scores.py` uses), same selector `0x5fb3feaf` and
`methodologyHash`. Still no transaction built, signed, or sent.

Once a real deploy happens (a future `deploy_testnet` phase, once the
funding question above is actually resolved) the same script (without
`--dry-run`, plus `ORACLE_RPC_URL=https://rpc.moderato.tempo.xyz`,
`ORACLE_ADDRESS`, `PRIVATE_KEY`) sends the real transaction, following the
exact same pattern as the repo root's `scripts/update_scores.py` and every
EVM sibling's own `push_scores.py`. The script refuses outright (before
reading `PRIVATE_KEY` at all) if `ORACLE_RPC_URL` ever resolves to chain ID
4217 (Tempo Mainnet) -- this pipeline never writes to mainnet, for any
ecosystem, and that guard is unconditional, not something an env var can
override.

## Not yet promoted / disclosed limitations

- 13 targets are now live in `chains/tempo/scorers.py` (chain baseline +
  USDC.e/USDT0/pathUSD/USDB/cbBTC/PRIME/DLUSD/EURC.e/cUSD, plus the 3
  Morpho Vault V2 instances added 2026-09-18's second pass, rule R8 --
  see `../METHODOLOGY.md` and `../data/scored_targets_2026-09-18-vault-v2.md`).
  `chains/tempo/data/scouted_targets_2026-09-17-run2.md` and
  `runs/.../claims_attempt1.txt` (outside this repo, this pipeline's own
  run-folder convention) still hold live-verified reads for 2 more real
  targets that are NOT yet wired into `scorers.py`'s `score_all()`: Morpho
  Blue itself (owner = Safe 5-of-9, same 9 signers as Morpho's Ethereum
  owner -- a DIFFERENT shape from Vault V2, no curator/adapter-timelock
  concept, an owner-only fee/IRM-allowlist authority) and the Uniswap V4
  PoolManager / V2 Factory pair (both resolve to the same Uniswap Wormhole
  Message Receiver, itself governed cross-chain by Ethereum's own 2-day
  Uniswap Timelock -- classify() only resolves authority ON Tempo today, so
  this target's true weakest link is on a DIFFERENT chain, a genuinely new
  shape none of the 4 controller types or rule R8 added 2026-09-18 cover).
  The Stablecoin DEX and Fee AMM precompiles (no `owner()`, code changes
  only via hardfork) were also scouted but deliberately were not force-fit
  into the per-target scoring shape -- their authority is already fully
  captured by the chain baseline score. Not promoted this pass: correctly
  wiring the cross-chain Uniswap case in particular needs care (a wrong
  "weakest key" computed only from Tempo-side state would UNDERSTATE the
  real risk if Ethereum's timelock were ever bypassable, or overstate it by
  ignoring the 2-day delay entirely) -- flagged here as a credible, concrete
  next step rather than rushed.
- Only pathUSD's `balanceOf()` was checked for the deployer on Moderato
  (confirmed 0, see "Gas token and funding" above). Whether any OTHER
  TIP-20 is also whitelisted as a fee token on Moderato, and whether the
  deployer holds a nonzero balance of one, was not checked this pass.
- **Stale-address correction (found and fixed 2026-09-19)**: this file's
  "Gas token and funding" section above, and `ecosystems.json`'s own action
  #70 approval text, checked `balanceOf()` for
  `0xA08a76457b758aFF9702dBf5b870679E1232B715` -- the shared deployer key
  that WAS current when this file's deploy scaffolding was committed
  (`0b32100`, 2026-09-18 16:10:52), but was superseded 37 minutes later the
  same day (16:47) when the whole pipeline rotated to
  `0x20630C6Ab4BA48a80edA46F77b9b6e987A8f32f5` after the old key was flagged
  as possibly exposed in a local session transcript (see
  `keys/evm-testnet-shared_SUPERSEDED_2026-09-18_exposed.json` in the
  pipeline's local config dir, and `chains/ethereum-l1/deploy/README.md`,
  which documents the same rotation for its own ecosystem). Ethereum L1's
  and Base's own deploy READMEs were updated after the rotation; this one
  was not, until now. No funds were ever at risk on the old key (it was
  never funded either), but the address named in this file was stale by
  the time of the actual deploy. Re-verified live on the CURRENT key before
  funding or deploying it (also 0 pathUSD, 0 nonce -- see "Real deployment"
  below).

## Real deployment (2026-09-19)

Executed by a later session, after action (2026-09-18) approved the
move to `deploy_testnet`. Chain ids re-confirmed live one more time before
touching anything (`eth_chainId` via plain JSON-RPC and independently via
`web3.py`): Moderato `0xa5bf` = 42431, Tempo Mainnet `0x1079` = 4217,
identical on `rpc.moderato.tempo.xyz`, `rpc.tempo.xyz` and the independent
`tempo-rpc.publicnode.com`.

**Key decision**: reused the shared EVM testnet key
(`keys/evm-testnet-shared.json`, address
`0x20630C6Ab4BA48a80edA46F77b9b6e987A8f32f5`) -- the same key already used
for Ethereum L1 (Sepolia), Arbitrum Sepolia, Base Sepolia and Hyperliquid
Testnet -- rather than a Tempo-specific dedicated key. Reasoning: Tempo is a
standard EVM Layer 1 with ordinary secp256k1 EOA accounts (confirmed live
and in `../METHODOLOGY.md` section 1 -- "fully compatible with the EVM",
standard JSON-RPC, standard tx signing); the two ecosystems in this repo
that DO get a dedicated key each have a real reason Tempo doesn't share:
Solana needs one because it is ed25519, not secp256k1 -- structurally
unable to reuse an EVM keypair at all; Robinhood Chain's dedicated key is a
historical artifact of its migration from a separate pipeline
(`multisig-overlap-loop-pipeline`) that already had its own key before the
two pipelines were consolidated, not an account-model difference. Tempo has
neither reason to diverge, so it follows the established "one EVM keypair
across EVM testnets" convention already shared by 4 sibling ecosystems --
the deployer key's identity is not part of what "native per-chain
deployment" means in this project; the CONTRACT deployed on each chain is
what's native, not the key that signs the deploy tx.

**Funding**: `tempo_fundAddress` (see "Faucet" row above) called directly
against the current shared key on Moderato -- a single JSON-RPC call with
one `address` param, no captcha, no login, no real-value deposit, matching
this pass's explicit instruction that a free, guardrail-free faucet path
can be used directly rather than left for Spap. Returned 4 transaction
hashes (pathUSD, AlphaUSD, BetaUSD, ThetaUSD each minted), all confirmed
`status: 1` via `eth_getTransactionReceipt`. Resulting pathUSD balance:
1,000,000,000,000 raw units = 1,000,000 pathUSD (6 decimals), confirmed via
`balanceOf()`. Deployer nonce stayed at 0 (the faucet's own fee-payer is a
different address, not the deployer being funded).

**Compiling and deploying**: `forge`/`cast` are not installed in this
session's sandbox (same gap the Plasma deploy hit the day before, see the
root `README.md`'s Plasma section). Compiled `src/AuthorityRiskOracle.sol`
and `src/ExampleConsumer.sol` locally with `py-solc-x`, solc **0.8.36**
(installed to match the version `forge build` used during the 2026-09-18
pass, not the 0.8.24 already on hand, so the deployed bytecode is the same
compiler output every other ecosystem's real deploy already uses) and the
same `optimizer=true, runs=200` settings as `foundry.toml`. Cross-checked
the compiled creation bytecode against the real, previously-broadcast
`AuthorityRiskOracle` deployment on Base Sepolia
(`broadcast/Deploy.s.sol/84532/run-latest.json`): identical for the entire
body of the contract, differing only in the trailing CBOR metadata hash
(expected -- that hash is a function of exact source paths/compiler
settings fed to solc, not of contract behavior) and the appended,
per-chain constructor argument.

Deployed with `web3.py` directly (no Foundry `Script`), replicating
`script/Deploy.s.sol` exactly: `AuthorityRiskOracle(deployer)` first, then
`ExampleConsumer(address(oracle))`, both as ordinary signed legacy
transactions (Tempo's own docs confirm standard legacy/EIP-1559
transactions work unmodified, with the fee token defaulting to pathUSD for
any call to a non-TIP-20 contract -- no special `feeToken` field needed in
the signed tx itself):

| Contract | Address | Tx hash | Block | Gas used |
|---|---|---|---|---|
| `AuthorityRiskOracle` | [`0x50840a7667baEa9D05ad4ae3dCeb384724b58720`](https://explore.testnet.tempo.xyz/address/0x50840a7667baEa9D05ad4ae3dCeb384724b58720) | [`0x84224eae...245cb`](https://explore.testnet.tempo.xyz/tx/0x84224eae65d5aa2cd69ab28253f13a35200380c63209b3742d8c90404cf245cb) | 35905341 | 5,217,910 |
| `ExampleConsumer` | `0xB7403b365a58B31Ae030DB423f6B703AD67f003a` | `0xd8125dd3310ed0adcec37e1cc160f3527925a6d626d68fc2bc9fa538b17e65b2` | 35905344 | 1,751,137 |

Both receipts read `status: 1`. `AuthorityRiskOracle`'s address is
identical to Arbitrum Sepolia's and Base Sepolia's own deployed address --
a coincidence, not a bug: a CREATE address is `keccak(deployer, nonce)`,
chain-independent, and the shared deployer key was at nonce 0 on all three
chains when each oracle was deployed.

**Bytecode verification**: `eth_getCode` on the deployed
`AuthorityRiskOracle` address returns runtime bytecode that matches the
locally compiled `bin-runtime` byte-for-byte (`True`, checked
programmatically, not eyeballed). Cost of both deployments together:
0.083145 pathUSD (999,999.916855 pathUSD left of the 1,000,000 minted).

**Pushing scores for real**: ran `deploy/push_scores.py` WITHOUT
`--dry-run`, with `ORACLE_RPC_URL=https://rpc.moderato.tempo.xyz`,
`ORACLE_ADDRESS=0x50840a7667baEa9D05ad4ae3dCeb384724b58720` and
`PRIVATE_KEY` read from the key file (never printed, never logged). All 13
targets re-derived live from Tempo Mainnet at push time, byte-identical to
the composites already published in
`../data/scored_targets_2026-09-18-controller-types.md` and
`../data/scored_targets_2026-09-18-vault-v2.md`
(31/55/43/9/9/39/39/9/55/43 for the original 10, plus 27/9/61 for the 3
Vault V2 targets). `updateScores()` sent as a real transaction:

```
Sent updateScores() tx: 0x286ef2c4b03cde0174c4afa00dda96f5d34b4ed1260cc89db94ab35da736c49d
Confirmed in block 35906259: success
```

**Read-back verification**: called `getScore()` live for 6 of the 13
targets (chain baseline, USDC.e, pathUSD, cUSD, and both Morpho Vault V2
extremes) plus `trackedTargetsCount()`. All match exactly what was pushed,
including `methodologyHash = 0xe653d28506a2817ef2eca397d999966bd56a35d9024e25cdfccbb618d1a3909a`
on every entry; `trackedTargetsCount()` returns `13`.

**Not done this pass**: `ecosystems.json`'s `phase` field for `tempo` is
left at `deploy_testnet`, not advanced to `maintenance`, even though every
sibling ecosystem that reached a real deploy (Ethereum L1, Arbitrum, Base)
did advance -- in every one of those cases the advance came from a
separate, numbered maker-checker action approved by a distinct verifier
identity (`verifier-ethereum-l1`, `verifier-arbitrum-ecosystem`,
`verifier-base-ecosystem`), not from the same session/identity that did the
deploy. this pass is not that separate verifier and has no way to
produce that independent check honestly, so the phase transition is left
for that process rather than asserted here.

## Maintenance run (2026-09-19): rotation audit index 0 + Morpho Blue core

First run in phase `maintenance`. Rotation audit index 0 (`trackedTargets(0)` = the validator
registry) re-derived from scratch on both mainnet RPCs: `(50, 37, 0, 100, 100, 31)`, identical to
what was published, no correction. One new target added under rule R9: Morpho Blue core
`0x10EE9AAC980A180dd4DcFc96C746d60B0EA88f97` (owner Safe 5-of-9, composite 55). All 14 targets
pushed in `updateScores()` tx
[`0xe34510ed...029cc6`](https://explore.testnet.tempo.xyz/tx/0xe34510ed23b72647195fc312d0de7156840fa8280de38d029ef50516e6029cc6)
(block 36006957, status 1); `trackedTargetsCount()` now reads **14**. Details:
`../data/scored_targets_2026-09-19-morpho-blue.md`.

## 2026-09-20 re-push: Morpho Blue core cross exposure 100 -> 80, pushed on-chain

| Field | Value |
|---|---|
| Oracle | [`0x50840a7667baEa9D05ad4ae3dCeb384724b58720`](https://explore.testnet.tempo.xyz/address/0x50840a7667baEa9D05ad4ae3dCeb384724b58720) (Tempo Moderato, chain 42431) |
| `updateScores()` tx (14 targets) | [`0xcdc3cc092d5e641de9407484a929ab40732799e0ae043f9fdea8d7ef400aa44b`](https://explore.testnet.tempo.xyz/tx/0xcdc3cc092d5e641de9407484a929ab40732799e0ae043f9fdea8d7ef400aa44b) |
| Block | 36054236, status 1, gasUsed 267,628 |
| `lastUpdated` | 1789864510 = 2026-09-20 00:35:10 UTC (all 14 targets) |
| What changed | Only the Morpho Blue core: 65 / 96 / 0 / 100 / 100 / 55 -> 65 / 96 / 0 / 100 / **80** / 55. The other 13 targets were re-written with unchanged values. |
| Read back | Plain `getScore()` on all 14 targets equals the scorer output of commit `042f805` exactly (0 differences). `trackedTargetsCount()` = 14. |

Scorer output as of 2026-09-20 (`chains/tempo/scorers.py`, live Tempo mainnet
reads, no key, no transaction): the Morpho Blue core
(`0x10EE9AAC980A180dd4DcFc96C746d60B0EA88f97`) returns
65 / 96 / 0 / 100 / **80** / 55, where the 2026-09-19 push above wrote
65 / 96 / 0 / 100 / 100 / 55. Composite (55) and chain-capped composite (31)
are unchanged. The 2026-09-20 re-push put the 80 on the Moderato oracle.

Why: the project decided on 2026-09-20 that a cross-ecosystem overlap is
folded into `crossExposureScore` on every ecosystem (root `METHODOLOGY.md`,
paragraph "Convention (decided 2026-09-20)"; Tempo rule R6 in
`../METHODOLOGY.md`). The Morpho Blue core's owner Safe has the same 9
signers as the Morpho Blue owner Safes tracked on Ethereum L1, Base and
Robinhood Chain, so its score is `min(within-Tempo value, 80)`. Tempo used to
keep this as a note only. The scorer compares the 9 owners it reads on Tempo
against a dated snapshot (`_KNOWN_MORPHO_BLUE_OWNERS_2026_09_20`) and does
not query the other chains. Every other Tempo target is unchanged.

Also fixed the same day: `score_all()` used to overwrite each target's
`notes` with `chainCappedComposite`; it now merges, so the cross-chain finding
(`notes.crossChainSignerOverlap`) is kept next to `chainCappedComposite` in
the returned notes.

### Current on-chain scores (re-push, 2026-09-20)

Read back with plain `getScore()` after the push; 14 targets, all
`lastUpdated` 1789864510. The 2026-09-19 composites quoted earlier in this
file are kept as history.

| Idx | Target | Address | admin | multisig | timelock | oracle | cross | composite |
|---|---|---|---|---|---|---|---|---|
| 0 | Tempo L1 validator registry (ValidatorConfigV2) | `0xCcCCCCcC00000000000000000000000000000001` | 50 | 37 | 0 | 100 | 100 | 31 |
| 1 | USDC.e | `0x20C000000000000000000000b9537d11c60E8b50` | 65 | 98 | 0 | 100 | 80 | 55 |
| 2 | USDT0 | `0x20C00000000000000000000014f22CA97301EB73` | 65 | 58 | 0 | 100 | 100 | 43 |
| 3 | pathUSD | `0x20C0000000000000000000000000000000000000` | 10 | 15 | 0 | 100 | 60 | 9 |
| 4 | USDB | `0x20C0000000000000000000003158081EFd85bFc2` | 10 | 15 | 0 | 100 | 60 | 9 |
| 5 | cbBTC | `0x20C000000000000000000000c412Ec89D0c08be5` | 65 | 42 | 0 | 100 | 80 | 39 |
| 6 | PRIME | `0x20C00000000000000000000058d0B8b2CFDb358c` | 65 | 42 | 0 | 100 | 80 | 39 |
| 7 | DLUSD | `0x20c0000000000000000000006fD9A167923ba194` | 10 | 15 | 0 | 100 | 60 | 9 |
| 8 | EURC.e | `0x20c0000000000000000000001621e21F71CF12fb` | 65 | 98 | 0 | 100 | 80 | 55 |
| 9 | cUSD | `0x20C0000000000000000000000520792DcCccCccC` | 65 | 58 | 0 | 100 | 100 | 43 |
| 10 | Sentora pathUSD (Morpho Vault V2) | `0x9a044AE05E5e6290DcF56afd69548565e957a626` | 10 | 15 | 60 | 100 | 100 | 27 |
| 11 | Unnamed pathUSD Vault V2 feeding Sentora | `0x83a1491f3e7f8dAAB8F787a631334b9ca7a87023` | 10 | 15 | 0 | 100 | 100 | 9 |
| 12 | Tempo Earn (Morpho Vault V2, Gauntlet-curated) | `0xC609656Ed9ef219c98C8e549bF729144F211f06E` | 65 | 56 | 60 | 100 | 100 | 61 |
| 13 | Morpho Blue core | `0x10EE9AAC980A180dd4DcFc96C746d60B0EA88f97` | 65 | 96 | 0 | 100 | **80** | 55 |

Bold marks the one cell that changed against the 2026-09-19 push.
