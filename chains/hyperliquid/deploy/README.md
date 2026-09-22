# Hyperliquid -- deployment guide (HyperEVM Testnet, chain 998)

Phase: `deploy_testnet` (per `ecosystems.json`, since the 2026-09-18
`scoring_build` commit below; re-checked 2026-09-18, second pass). This
README documents how the project's **existing** native EVM contract
(`src/AuthorityRiskOracle.sol`, reused as-is, not modified for Hyperliquid)
will be deployed to HyperEVM Testnet, and what has already been verified.
**Status on 2026-09-20: DEPLOYED to HyperEVM Testnet** (launched by Spap,
record and read-back in "2026-09-20 -- real deploy on HyperEVM Testnet" at
the end of this file). The 2026-09-18 and 2026-09-19 passes below stopped
at an unfunded deployer key (0 wei on both the old and the current
address) and deployed nothing; those sections are kept as history and are
superseded by the 2026-09-20 record.

## Scope: HyperEVM vs HyperCore

Per [`../METHODOLOGY.md`](../METHODOLOGY.md) section 1: "smart contract
admin key" only exists on **HyperEVM**. **HyperCore** (the native
exchange/validator engine that actually holds almost every target this
ecosystem scores -- HIP-3 dexes, the L1 itself, Unit treasuries, HLP) has
**no smart-contract deployment concept at all** -- only native, typed
actions (`spotDeploy`, `perpDeploy`, `CValidatorAction`, ...). There is
therefore no separate "native HyperCore program" a Solidity contract (or
anything else) could ever target the way an Anchor program targets Solana,
or the way `src/AuthorityRiskOracle.sol` targets any other EVM chain in
this repo. This is a structural fact about Hyperliquid's own architecture,
disclosed here rather than chased further -- the same category of
disclosed limitation METHODOLOGY.md section 2 already records for
HyperCore's single-operator-API read gap.

What CAN be deployed, and is what this folder targets, is
`src/AuthorityRiskOracle.sol` on **HyperEVM** -- the SAME contract every
other EVM ecosystem in this repo (`ethereum-l1`, `arbitrum-ecosystem`,
`base-ecosystem`) already targets per-chain. It stores scores for
HyperCore-native targets exactly as it already stores scores for
Arbitrum/Base mainnet targets today: the oracle contract's own chain and
the chain(s) its scored targets actually live on are independent by
design throughout this whole repo (see e.g. `arbitrum-ecosystem/deploy/
README.md`'s own framing) -- Hyperliquid does not need a new pattern, only
the same one pointed at 15 HyperCore- and HyperEVM-native targets instead
of Arbitrum-native ones.

## Network

| | |
|---|---|
| Network | HyperEVM Testnet |
| Chain ID | **998** (`0x3e6`) -- confirmed live this run via `eth_chainId` on `https://rpc.hyperliquid-testnet.xyz/evm` |
| HyperEVM Mainnet (read-only, for the scorer -- never a deploy target) | chain **999** (`0x3e7`) -- also confirmed live this run |
| Public RPC (official) | `https://rpc.hyperliquid-testnet.xyz/evm` |
| Public RPC, mainnet (read-only) | `https://rpc.hyperliquid.xyz/evm` |
| Explorer | https://testnet.purrsec.com (per Hyperliquid docs; not independently checked this pass) |
| Faucet | Hyperliquid's testnet faucet **requires a prior mainnet deposit from the same address** (METHODOLOGY.md section 2) -- a real blocker for the shared throwaway key, disclosed, not chased around |

Both chain IDs were re-confirmed live again on 2026-09-18 (second
independent pass, same day as the `scoring_build` commit above -- not
assumed from that prior pass, from this doc, or from ecosystems.json's own
`network.testnet_deploy` field, which still read "A CONFIRMER" at the
start of this pass): primary source
[hyperliquid.gitbook.io/hyperliquid-docs/for-developers/hyperevm](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/hyperevm)
states Mainnet "Chain ID: 999", Testnet "Chain ID: 998"; then confirmed
live via a direct `eth_chainId` JSON-RPC call against
`https://rpc.hyperliquid-testnet.xyz/evm` -> `0x3e6` (998) and against
`https://rpc.hyperliquid.xyz/evm` -> `0x3e7` (999), both matching the doc
exactly. `cast chain-id` (Foundry) was attempted first but failed in this
session's sandbox with a local TLS error (`invalid peer certificate`,
unrelated to Hyperliquid's endpoint -- plain `curl` to the same URL
succeeds), so the raw `eth_chainId` RPC call was used instead, exactly as
the task instructions allow ("cast chain-id OU un appel RPC eth_chainId").
The task instructions for this ecosystem explicitly warn not to guess the
HyperEVM testnet chain ID -- it was not guessed either pass.

## Contract

`src/AuthorityRiskOracle.sol` is used unmodified -- same contract already
prepared or deployed for Robinhood Chain, Arbitrum Sepolia, and Base
Sepolia (see those ecosystems' own `deploy/README.md`). No
Hyperliquid-specific Solidity changes are needed: the contract is
chain-agnostic (`AccessControl`-gated `UPDATER_ROLE`,
`updateScore`/`updateScores`, `getScore`, `isStale`).

`script/Deploy.s.sol` (repo root, also reused unmodified) deploys
`AuthorityRiskOracle` with `admin = deployer` and a demo `ExampleConsumer`
wired to it.

The `updateScores(address[],AuthorityScore[])` selector was verified live
this run via
`cast sig "updateScores(address[],(uint8,uint8,uint8,uint8,uint8,uint8,uint64,bytes32)[])"`
-> `0x5fb3feaf`, matching the same value `deploy/push_scores.py --dry-run`
actually encodes below (byte-for-byte, not assumed) and the same selector
every other ecosystem's README already documents for this identical
contract.

## Build and test (this pass, read-only, no deploy)

Every ecosystem's agent shares this one clone -- always pass separate
`--out`/`--cache-path` so parallel agents never clobber each other's build
artifacts:

```
forge build --out runs_hyperliquid_out --cache-path runs_hyperliquid_cache
forge test  --out runs_hyperliquid_out --cache-path runs_hyperliquid_cache
```

Result this run (2026-09-18, `scoring_build`): `Compiler run successful!`
(30 files, Solc 0.8.36, 3 pre-existing lint warnings unrelated to this
pass -- `missing-events-arithmetic`, `require-revert-in-loop`,
`block-timestamp`, all in `src/AuthorityRiskOracle.sol` itself, not
introduced this pass), **20/20 tests passed** (5 in
`ExampleConsumer.t.sol`, 15 in `AuthorityRiskOracle.t.sol`), 0 failed,
0 skipped.

## Deploy key and current balance

Uses the shared EVM testnet key, `keys/evm-testnet-shared.json`. **This
key was rotated on 2026-09-18**, after the `scoring_build` pass above was
committed: the address `0xA08a76457b758aFF9702dBf5b870679E1232B715` used
in that pass is now superseded (flagged as possibly written into a local
session transcript on 2026-09-17; it was never funded on any of the 3
shared testnets, so no funds were at risk). The current address is
`0x20630C6Ab4BA48a80edA46F77b9b6e987A8f32f5`. Private key never copied
into this repo, never printed to any output or log; per the key file's own
note, valid ONLY for the HyperEVM sub-layer of this ecosystem, never for
HyperCore -- which has no key-based contract deployment concept to begin
with, per the scope note above.

Balance on HyperEVM Testnet (chain 998), re-checked live this pass (same
2026-09-18 pass that re-confirmed the chain ID above) via a direct
`eth_getBalance` JSON-RPC call against
`https://rpc.hyperliquid-testnet.xyz/evm` for the new address (`cast
balance` was not used here for the same local sandbox TLS reason noted
above for `cast chain-id`; the old, superseded address was also re-checked
for continuity and is likewise 0):

**0 wei** (`0x20630C6Ab4BA48a80edA46F77b9b6e987A8f32f5`) -- still
insufficient. **No deployment happened this pass either.**

No faucet with a captcha/login requirement was used, and no funding was
requested from anyone; per this pipeline's rules an unfunded key is simply
a fact to disclose, not something to chase. Hyperliquid's own testnet
faucet additionally requires a prior MAINNET deposit from the same
address before it will fund the testnet side at all (METHODOLOGY.md
section 2) -- a structural blocker specific to this ecosystem, beyond the
"just use a faucet" pattern the Arbitrum/Base siblings' own unfunded-key
notes describe. This pass stopped here per its own instructions (confirm
chain ID -> check balance -> deploy only if funded) rather than guessing,
forcing a deployment, or requesting funding autonomously.

## Pushing scores (dry-run only in this phase)

See [`push_scores.py`](push_scores.py), modeled directly on
`chains/arbitrum-ecosystem/deploy/push_scores.py` and the Base Ecosystem
sibling script, adapted for the fact that `chains/hyperliquid/scorers.py::
score_all()` takes no RPC argument (Hyperliquid's reads are fixed official
endpoints, not one caller-supplied chain). Supports `--dry-run`, which
re-derives every tracked target's score from LIVE mainnet/HyperEVM/
Arbitrum One state and encodes the `updateScores(address[],AuthorityScore[])`
calldata that WOULD be sent to the oracle on HyperEVM Testnet, printing the
calldata hex without ever building a transaction, signing, or sending
anything. No `PRIVATE_KEY` is required for `--dry-run`.

```
python3 chains/hyperliquid/deploy/push_scores.py --dry-run
```

Confirmed this run, TWICE in a row (a fresh live run each time, not a
cached replay) to check determinism: **15 targets scored, identical
composite/oracle/crossExposure numbers both times** --

| Target | composite | l1Capped | oracle | crossExposure |
|---|---|---|---|---|
| Hyperliquid L1 | 26 | n/a | 40 | 100 |
| HIP-3 dex xyz | 9 | 9 | 4 | 100 |
| HIP-3 dex io | 32 | 26 | 58 | 60 |
| HIP-3 dex para | 5 | 5 | 10 | 100 |
| HIP-3 dex mkts | 9 | 9 | 15 | 80 |
| Kinetiq HIP3StakingManager (kmHYPE) | 4 | 4 | 7 | 100 |
| para StakingVault | 4 | 4 | 100 | 100 |
| Ventuals vHYPE staking | 31 | 26 | 100 | 100 |
| Kinetiq kHYPE StakingManager | 4 | 4 | 15 | 100 |
| HLP vault | 9 | 9 | 100 | 100 |
| Unit UBTC treasury | 9 | 9 | 100 | 100 |
| Unit UETH treasury | 9 | 9 | 100 | 100 |
| Unit USOL treasury | 9 | 9 | 100 | 100 |
| Bridge2 (Arbitrum One) | 48 | 26 | 100 | 100 |
| HyperLend Pooled | 61 | 26 | 100 | 100 |

**CORRECTION 2026-09-19**: these 15 scores do NOT land in 15 oracle slots
under the push code as it stood here. The oracle is keyed by address, and
`mkts`/Kinetiq HIP3StakingManager share `0x71f0...29ec` and `para`/para
StakingVault share `0x8888...6ed3`, so a push stored only 13 and read back
`mkts`=4 and `para`=4 (the HyperEVM contracts' scores). Fixed in
`push_scores.py` (derived keys for the two dexes, METHODOLOGY.md 4.7
amendment). See "2026-09-19 -- eth_call rehearsal" below.

Calldata encoded to 4,452 bytes for these 15 targets, selector `0x5fb3feaf`
at the start of the calldata matching the `cast sig` value above exactly,
`methodologyHash = 0xfbf38ff91abf710728e2df3d5370bf18eeb2a9085168612fa03955b13cc958ad`
(`keccak256("authority-risk-oracle-hyperliquid-v1")`).

## Deploy command (run on 2026-09-20, record at the end of this file)

```
PRIVATE_KEY=<from keys/evm-testnet-shared.json, never echoed/logged> \
forge script script/Deploy.s.sol \
  --rpc-url https://rpc.hyperliquid-testnet.xyz/evm \
  --broadcast --legacy --with-gas-price <3x eth_gasPrice, 0.3 gwei on 2026-09-20> \
  --out <this run's forge-out dir> \
  --cache-path <this run's forge-cache dir>
```

`--legacy` is deliberate: the public HyperEVM testnet RPC intermittently
answers `eth_feeHistory` with `-32602 invalid block range`, which aborts
forge's EIP-1559 fee estimation before anything is sent (the first real
attempt on 2026-09-20 died that way with the deployer's nonce still at 0).
Legacy fees never call `eth_feeHistory`.

Record the resulting `AuthorityRiskOracle` and `ExampleConsumer` addresses
(and update `push_scores.py`'s expected `ORACLE_ADDRESS` env var
convention) once that phase actually runs, plus fund the deployer key
first -- both blocked on Spap, not on anything this pass could resolve
autonomously (mainnet-deposit-gated faucet, no funding requested
autonomously per this pipeline's rules). Both were done on 2026-09-20.

`push_scores.py` itself already refuses to send to chain 999 (HyperEVM
mainnet) even if `ORACLE_RPC_URL` were ever pointed there by mistake --
belt-and-suspenders on top of this whole pipeline never writing to any
real mainnet, for any ecosystem, under any instruction.

## 2026-09-18, second pass -- summary

- Chain ID re-confirmed independently, from the primary source AND live:
  HyperEVM Testnet = **998**, Mainnet = **999**. Not guessed.
- Deployer key had been rotated since the `scoring_build` commit above
  (old address flagged as possibly exposed in a transcript, never funded).
  New address `0x20630C6Ab4BA48a80edA46F77b9b6e987A8f32f5` balance
  re-checked live: **0 wei**.
- Per instructions: insufficient balance -> stop here, do not deploy, do
  not request funding autonomously. No transaction was sent, no contract
  address was created, `ecosystems.json`'s `hyperliquid` field updated
  accordingly (phase stays `deploy_testnet`).

## 2026-09-19 -- eth_call rehearsal on HyperEVM Testnet (still no deploy)

**Balance.** Deployer `0x20630C6Ab4BA48a80edA46F77b9b6e987A8f32f5` re-checked
live with `eth_getBalance` on three independent HyperEVM Testnet endpoints
(official `rpc.hyperliquid-testnet.xyz/evm`, `hyperliquid-testnet.drpc.org`,
`rpcs.chain.link/hyperevm/testnet`), all reporting chain id `0x3e6`: **0 wei**
on all three. No deployment, no transaction, no funding requested.

**Why not an anvil fork.** Foundry (`anvil`/`forge`/`cast`) is no longer
installed on the host that runs this pipeline (`~/.foundry` is gone, no other
copy found), and installing it means downloading and running a binary, which
this autonomous run does not do on its own. The anvil-fork rehearsal used by
the Arbitrum/Base folders could not be replayed. **Spap: reinstall Foundry
(`foundryup`) if you want the anvil path back.**

**What was done instead: `rehearsal/rehearse_ethcall.py`.** The whole
deploy -> `updateScores()` -> `getScore()` sequence runs inside ONE `eth_call`
on the real HyperEVM Testnet: the init code of
[`rehearsal/EthCallRehearsal.sol`](rehearsal/EthCallRehearsal.sol) deploys
the unmodified `src/AuthorityRiskOracle.sol` and `src/ExampleConsumer.sol`,
pushes the live-scored batch through the real `updateScores()`, reads every
target back through separate external `getScore()`/`isStale()` calls and
returns the lot. `eth_call` is a read: nothing is signed or broadcast, no key
is read, nothing persists, and gasPrice 0 means no balance is needed. Compiled
with the solc 0.8.36 binary already on disk (`py-solc-x`), optimizer 200, the
same settings as `foundry.toml`. Scores go through the same
`push_scores.build_targets_and_tuples()` a real push would use.

```
python3 chains/hyperliquid/deploy/rehearsal/rehearse_ethcall.py                  # cancun (default)
python3 chains/hyperliquid/deploy/rehearsal/rehearse_ethcall.py --evm-version prague
python3 chains/hyperliquid/deploy/rehearsal/rehearse_ethcall.py --legacy-keys    # reproduces the collision, exits 1
```

Results (evidence in the pipeline's `runs/2026-09-19-cron/hyperliquid/`):

| Check | Official RPC | drpc (independent) |
|---|---|---|
| chain id | 998 | 998 |
| 15 scores sent == 15 read back (all 8 fields), none stale | yes | yes |
| `trackedTargetsCount()` | 15 | 15 |
| `UPDATER_ROLE` held by the deployer after construction | yes | yes |
| `ExampleConsumer.ORACLE()` == the simulated oracle | yes | yes |
| deployed oracle codehash == keccak of the compiled runtime | yes (`0xcd05c93c...1354804`, cancun) | yes |
| same with `--evm-version prague` / `osaka` | OK / OK | OK / OK |
| `--legacy-keys` (the push as it was before today) | FAILS: 13/15 tracked, mkts 9->4, para 5->4 | same |

The 15 composites in the rehearsal (26, 9, 32, 5, 9, 4, 4, 31, 4, 9, 9, 9, 9,
48, 61) are identical to two separate live `push_scores.py --dry-run` runs
the same day and to the table above. So the scorer is unchanged after
today's other commits (e2caf6f kHYPE/kmHYPE label, 0262ff5 Bridge2 tests).

**Gas and HyperEVM's two block sizes.** Read live on 2026-09-19: HyperEVM
Testnet small blocks have `gasLimit` 3,000,000 and big blocks 30,000,000
(1 big block among 80 consecutive ones sampled). Execution gas measured
inside the rehearsal: oracle deploy 829,351, consumer deploy 274,701,
`updateScores` for 15 targets 1,458,429 (about 97k per new target). Add
21,000 intrinsic gas plus calldata. As three separate transactions, each one
fits under the 3M small-block limit, so the deployer does not need big blocks
for today's 15 targets. A single `updateScores` batch goes over 3M at about
30 new targets, so it would need splitting or big blocks. Everything in one
transaction (3.85M, `eth_estimateGas` on the official RPC) would NOT fit. drpc
also caps `eth_estimateGas` at 3M.

**What this does NOT prove.** No real transaction exists, so there are no
addresses, tx hashes or blocks to record. The addresses the rehearsal prints
are simulated CREATE addresses from the harness. The real deploy is still
blocked on funding the deployer, which needs a mainnet deposit first and is
Spap's call. Once funded, the path is the "Deploy command" above plus
`push_scores.py` (now collision-safe). Pushing each batch as its own
transaction keeps every step under 3M gas.


## 2026-09-20 -- real deploy on HyperEVM Testnet (launched by Spap)

Run by Spap from `RealSpap/authority-risk-oracle` at `a1ecc05`, with the deployer
funded by hand (0.01 HYPE of testnet balance, through a faucet that requires a
prior mainnet balance, see "Deploy key and current balance"). Same unmodified
`src/AuthorityRiskOracle.sol` and `src/ExampleConsumer.sol` as every other EVM
chain in this repo; the scores went through the collision-safe
`push_scores.py` from the 2026-09-19 correction. Every value below was read
back from the chain, not copied from the script's output.

| | |
|---|---|
| Chain | HyperEVM Testnet, chain id 998 (`rpc.hyperliquid-testnet.xyz/evm`) |
| Deployer / admin / updater | `0x20630C6Ab4BA48a80edA46F77b9b6e987A8f32f5` |
| `AuthorityRiskOracle` | `0x50840a7667baEa9D05ad4ae3dCeb384724b58720`, tx `0x3d49452aa7ce39ae8f1e66caea7de7f68d0b7f90f9a6072a84c47d948b304de8`, block 64778486, 912,110 gas |
| `ExampleConsumer` | `0xB7403b365a58B31Ae030DB423f6B703AD67f003a`, tx `0x4c1a806d94c43f21021b797bfc8db0124e26682b27aa5b4af6f2edfb9048b60a`, block 64778488, 315,937 gas, `ORACLE()` = the oracle above |
| `updateScores()` | tx `0x9c8a758f3fbf20f3484485b531c736684da8dec81bc4f02c009ee1dc4def0a9d`, block 64778632, 15 targets in one transaction, 1,502,093 gas |
| Cost | 0.00051862 HYPE in total (deployer 0.01 -> 0.0094813766, nonce 0 -> 3) |

The oracle address is the same as on Arbitrum Sepolia, Base Sepolia, Plasma,
Tempo and Monad: a CREATE address is `keccak(deployer, nonce)` and this shared
deployer sat at nonce 0 here too.

**First attempt.** The first real launch aborted inside `forge script` on
`eth_feeHistory` (`-32602 invalid block range`) before any transaction was
sent; the nonce stayed 0. The dry run just before had passed and three later
broadcast attempts with an unfunded throwaway key got past the same step, so
the failure is intermittent, not deterministic. The deploy script then switched
to legacy fees (see "Deploy command"). Only the second launch sent anything.

The 15 targets on-chain (oracle key, composite):

| Target | Oracle key | Composite |
|---|---|---|
| Hyperliquid L1 (HyperCore validator set) | `0xeA394CD63CA3a5C8A130Bb2b955cC71C22E5ea6C` | 26 |
| HIP-3 dex xyz | `0x88806a71D74ad0a510b350545C9aE490912F0888` | 9 |
| HIP-3 dex io | `0x320c8988e3D1B5198F335802d7BFd2728a8FCaC6` | 32 |
| HIP-3 dex para | `0x30E96FBD515243d47703e78581b88cba60f51360` (derived key) | 5 |
| HIP-3 dex mkts | `0xBF6d3bBCE71dBcE6f4121BfE2E2caD8C77bBc1fC` (derived key) | 9 |
| Kinetiq HIP3StakingManager (HyperEVM) | `0x71F0019cC7fa79E4f42587FB7b9a817D8d2429EC` | 4 |
| para StakingVault (HyperEVM) | `0x8888888c43cbB7e1C4132542E46831BffD866ED3` | 4 |
| Ventuals vHYPE staking (HyperEVM) | `0x8888888192a4A0593c13532Ba48449FC24C3bEDA` | 31 |
| Kinetiq kHYPE StakingManager (HyperEVM) | `0x393D0B87Ed38fc779FD9611144aE649BA6082109` | 4 |
| Hyperliquidity Provider (HLP) vault | `0xdfc24b077bc1425AD1DEA75bCB6f8158E10Df303` | 9 |
| Unit UBTC treasury | `0x574bAFCe69d9411f662a433896e74e4F153096FA` | 9 |
| Unit UETH treasury | `0x8DAfBe89302656a7Df43c470e9EbCB4c540835c0` | 9 |
| Unit USOL treasury | `0xA822a9cEB6D6CB5b565bD10098AbCFA9Cf18D748` | 9 |
| Hyperliquid legacy USDC bridge (Bridge2, Arbitrum One) | `0x2Df1c51E09aECF9cacB7bc98cB1742757f163dF7` | 48 |
| HyperLend Pooled (Aave v3 fork, HyperEVM) | `0x72c98246a98bFe64022a3190e7710E157497170C` | 61 |

**Verification.** Independent of the push script, all read-only, on two RPCs
(`rpc.hyperliquid-testnet.xyz/evm` and `hyperliquid-testnet.drpc.org`):
- [`read_scores_hyperliquid.py`](read_scores_hyperliquid.py) (new, the counterpart of
  `../../solana/deploy/read_scores_solana.py`) recomputes the 15 scores live, rebuilds the oracle
  keys, reads `getScore()` for each and compares all six scores and the methodology hash:
  `RESULT: ALL MATCH`, none stale, `trackedTargetsCount()` = 15, and the deployer holds
  `UPDATER_ROLE`;
- the three receipts have `status: 1`;
- the oracle's runtime bytecode on-chain (3,619 bytes) is byte-for-byte the `deployedBytecode`
  of the forge build artifact for that commit. Its keccak differs from the one recorded on
  2026-09-19 for the `eth_call` rehearsal, which was compiled through `py-solc-x`: the likely
  cause is different compilation metadata, not checked. The comparison that matters is the one
  against the forge artifact.

**What was rehearsed first, and what was not.** The dry run simulated the deploy against the
real testnet RPC (1,596,461 gas, about 0.0005 HYPE at the price used) and encoded the 15-target
calldata. The whole real path (deploy, push, read-back) ran on a local `anvil --chain-id 998`,
and the read-back was checked to flag a deliberately falsified score. HyperEVM's real block
timing and fee behaviour could only be seen on the real launch, which is how the
`eth_feeHistory` failure surfaced.

**Still open.** The 15 scores are a snapshot: `isStale()` turns true after 9 days
(`maxStaleness`), and a committee rotation on any target makes its entry wrong before that.
Re-push with `push_scores.py` against this oracle address (`ORACLE_RPC_URL`, `ORACLE_ADDRESS`,
`PRIVATE_KEY`), then re-run `read_scores_hyperliquid.py`.

### `push_scores.py` now supports `--targets`/`--oracle` (added 2026-09-22, closing the 2026-09-21 gap described just below)

The gap this section used to warn about is closed. Before commit `210aed6`, an
agent run on 2026-09-21 prepared a hand-off script that passed `--targets <two
addresses> --oracle <address>` to `push_scores.py`, believing it was a
two-address correction push. It was not one, and would not have errored
either: the script had no `argparse` at all and read exactly one thing from
`sys.argv`, the literal string `--dry-run` -- any other flag, including a
would-be `--targets`, was silently discarded, and a correction always meant
re-pushing **all 15** targets with every `lastUpdated` refreshed.

`push_scores.py` now has real `argparse` (`parse_args()`), and `--targets
<comma-separated addresses>` genuinely narrows the push to just those oracle
keys -- every other tracked target's on-chain entry (score AND `lastUpdated`)
is left untouched. `--oracle <address>` overrides `ORACLE_ADDRESS` from the
CLI. Check the capability is really there before trusting any wrapper (the
grep this section used to recommend now proves the OPPOSITE of what it used
to):

```
grep -c add_argument chains/hyperliquid/deploy/push_scores.py   # 3 (--dry-run, --targets, --oracle)
grep -n 'def filter_by_targets\|def validate_oracle_override' chains/hyperliquid/deploy/push_scores.py
```

**Known, deliberately-not-fixed gap** (commit `210aed6`'s own review, kept
honest rather than rushed): requesting the RAW address of a HIP-3 dex that
collided with another entry (the `mkts`/Kinetiq and `para`/StakingVault pairs
documented above in this file) silently matches whichever entry is NOT the
dex -- the dex itself is unreachable by its raw address (it lives under a
derived key, see `hip3_dex_derived_key()`), with no error and no signal that
a dex also shares that raw address. `filter_by_targets()`'s own docstring
carries the same note. If a targeted push is ever meant to touch `mkts` or
`para` specifically, pass the derived key (printed on every run's per-target
review lines, in the `oracle key ...` field), not the raw deployer address.

Operator checklist for a real, keyed correction push, unchanged in spirit
from before this fix, updated for the new flag:

```
python3 chains/hyperliquid/deploy/read_scores_hyperliquid.py <oracle>   # confirm the DIFF set first
ORACLE_RPC_URL=... ORACLE_ADDRESS=... PRIVATE_KEY=... \
    python3 chains/hyperliquid/deploy/push_scores.py --targets <addr1,addr2>   # then push just those
```
