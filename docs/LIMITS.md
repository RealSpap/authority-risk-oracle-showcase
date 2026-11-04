# What we do not read

A score is a reading of public chain state, and some things do not show in it. This page lists them, each with the document where it is written. Numbers are counts over the 202 targets the Watch tracks, recomputed from the public files of the site and of the Watch, read between 22 and 24 October 2026.

## We read exposure, not what happens next

The score reads how much one compromise could do. It does not say who is hit. In a test written before any measurement, the composite did not separate 5 incident victims from 18 untouched peers of similar size read one month before each incident.

Written in: METHODOLOGY.md.

## We do not detect a compromise

The Watch reports changes to who controls a contract, upgrades and queued operations. It does not detect that a key has been stolen. The attacks we studied went around the configuration (a spoofed signing interface, compromised devices, a service key), which a configuration score does not show.

Written in: METHODOLOGY.md; README.md.

## We do not see how a key is kept

A plain key (an account with no code behind it) reads the same on a chain whether it sits in a hardware wallet, was leaked, or is an exchange hot wallet. In the Watch, 15 of the 202 tracked targets have a plain key as the holder of admin power.

Written in: METHODOLOGY.md.

## We do not see the people behind the keys

Three owners of a Safe could be three employees of one company, or one person's three wallets. The multisig score measures the strength of the threshold, not the independence of the signers. Approvals and arrangements made off the chain are not visible from chain state.

Written in: METHODOLOGY.md.

## The cross-ecosystem check compares EVM chains with each other

A shared-signer check between ecosystems is made among the EVM chains. On Solana, Zcash and the native multisigs of Hyperliquid, the cross exposure score compares signers inside the same ecosystem: a 100 there means that no shared signer was found inside it, not that none exists elsewhere. Key formats differ (Solana, Zcash), or the tool cannot list the signers (native Hyperliquid multisigs). 27 of the 42 Solana and Hyperliquid targets publish a cross exposure score of 100.

Written in: METHODOLOGY.md.

## Day-to-day roles are not all scored

A score follows the path that upgrades or reconfigures a contract. It does not list every role or every getter that could grant some privilege. How a role that can pause is treated is not uniform in the current reading: some targets list it without scoring it, others score it, and for many no written rule exists yet. See METHODOLOGY.md for what the method says.

Written in: METHODOLOGY.md.

## Some delays and key counts are not read

A line that could not be read is written as not read, never as a zero. Of the 202 tracked targets, 89 list the time anyone has to react as not read, and 115 list the number of keys it takes to move the contract as not read. Each target page says which.

Written in: METHODOLOGY.md; WHAT-THE-SCORE-SAYS.md.

## The oracle is a plain-key target itself

On the Ethereum oracle (Sepolia), the admin role is held by one account with no code, a plain key; scores are pushed by one updater key with no timelock. By this project's own method a bare key scores (5, 0, 0), a composite of 2 out of 100. The test oracles hold no user funds, and it is disclosed here so that a consumer weighs it first.

Written in: METHODOLOGY.md; REFERENCE.md; SECURITY.md.


## What this is for, and what it is not for

This project is research and monitoring. A score and a Watch alert are not an authority sufficient to authorize a critical operation on their own: do not release funds, change a limit or accept a counterparty on a score alone. Use them as one input, next to your own reading of the contract and a person who decides. A limit that is written on this page is documented, which does not make it acceptable for your use: whether a limit is acceptable depends on what you do with the score.

Written in: this page. See also README.md, SECURITY.md and WHAT-THE-SCORE-SAYS.md, which say that a score is not an audit and not advice.

## A role we detect is not every power the account has

The Watch names a secondary role by the getter that answered: `pauser()`, `guardian()`, `curator()`, `pauseGuardian()`, `emergencyGuardian()`, `emergencyAdmin()` and `getEmergencyAdmin()` (seven getters in `scripts/side_roles.py`). A role found that way is what that getter reports. It is not the full list of what the account or the contract can do. A contract that answers none of the seven getters is not covered: no getter means not covered, not no role. The Watch lists that case in `no_getter_recognised` of `side_roles.json`, as not covered, not as a finding.

Written in: watch/API.md (`side_roles.json`).

## Several holders are not several protections

Where a Safe has an owner that is itself a Safe, the nested-signers check (`scripts/check_nested_signers.py`, run by hand: it is not part of the Watch and not an input of the score) opens it down to its own owners, three levels below the Safe being read (`MAX_DEPTH = 4` in `scripts/lib/nested_signers.py`: the Safe being read and the nested Safes at depths 1, 2 and 3 are opened). A Safe four levels below is counted as one contract signer, is not opened, and is listed by the hand-run check as not analysed (depth limit). Shared signers between two groups are compared at the depth that was reached, so a key that sits deeper, or behind a signer that is a contract, is not seen. The independent reader of the Watch looks one level down only: for the first 20 owners of a Safe it reads whether each is a key, a Safe (its threshold and number of owners) or a timelock, and does not read the owners of those Safes. A Safe with a threshold of 1 whose owners are all multisigs of threshold 2 or more, or timelocks, is marked `nested` and counted at the lowest threshold among its owner Safes (`scripts/second_opinion.py`). Several holders of a role are not several protections either: three holders that one person can reach are one protection (see "We do not see the people behind the keys" above).

Written in: scripts/lib/nested_signers.py; data/finding_2026-09-25-nested-signers-formula-investigation.md.

## The multisig score is not one formula

The general shape is `min(100, threshold * 15 + max(0, owners - threshold) * 5)` (METHODOLOGY.md, `multisigScore`). Not every target uses it. In the code as of 30 October 2026 there are at least these shapes: (1) the shape above, in most scorers; (2) the weakest of several key sets: two Safes that each hold an upgrade path, so that the weaker sets the ceiling (`scripts/lib/scorers.py` line 701, the threshold of the weaker Safe times 15), or a proposer set and an executor set that both have to act (`chains/arbitrum-ecosystem/scorers.py` line 1086 and `chains/plasma-ecosystem/scorers.py` line 1434); (3) other weights per signature (`scripts/lib/scorers.py` line 234, one target; line 296, one target; line 334, the three Arcus pToken targets); (4) a Solana formula that counts voters (`chains/solana/scorers.py` lines 102 and 133) and a Zcash formula on miner concentration, the payout addresses needed to pass 50% and 25% (`chains/zcash/scorers.py` line 374); (5) a value set by a written rule (100 when a multisig does not apply, METHODOLOGY.md), or fixed by hand for the nine targets listed under "Known gaps" in CHANGELOG.md (that list comes from a sweep that did not read every scorer line by line; it is not claimed to be complete). A page generated from the code, `docs/MULTISIG-SHAPES.md`, lists the shape of the multisig formula in every scorer function (`python3 scripts/multisig_shapes.py --check` fails when the page is not what the code says). It is one row per scorer, not one per target: it does not say which scorer serves which target or which branch a target takes, and it lists apart the few functions whose value the parser cannot follow. To know what a target's score used, read the notes of that target: they list the owners and the threshold that were read.

Two properties of these shapes that the general shape hides (written 30 October 2026 after a second review): at a fixed threshold the multisig score RISES with the number of owners until it reaches 100 (`_safe_rooted_scores(1, 20)` gives 100, `(3, 5)` gives 55, `(9, 9)` gives 100), so a Safe where one key out of twenty suffices scores as high as a 9-of-9 on this dimension; and the Solana formula goes the other way (`15 * threshold + 40 * threshold / voters`: 2-of-2 gives 70, 2-of-10 gives 38). The two are not comparable across ecosystems. The requirement "at least a 3-of-5 multisig" of `scripts/badges_req.py` is `multisigScore >= 55`, which a 1-of-9 (55) satisfies.

Written in: METHODOLOGY.md; CHANGELOG.md (Known gaps).

## A dimension that does not apply counts as 100 in the average

When a target has no multisig (a DAO governor, a contract with no admin) its multisig sub-score is 100 by convention, and the weighted average gives it the weight 0.3. The Uniswap v3 factory scores (80, 100, 75) and a composite of 85; computed only on the two dimensions that apply, it would be 78, one band lower (decent, not strong). The comment above `_composite` in `scripts/lib/scorers.py` says such a score is "excluded from the weighting"; the code does not exclude it. Read a high composite on a DAO-governed target as "no multisig to attack", not as "a strong multisig".

## The delay score is a ladder with different rungs

The same delay does not give the same `timelockScore` in every scorer. In the code of 30 October 2026: one second scores 60 in the Spark executor (`10 if delay == 0 else 60`); any non-zero notice period scores 60 in the Lighter scorer; two days score 40 in the Morpho V2 bands (three days 60, seven days 75); 24 hours scores 60 in the Arbitrum GMX scorer; on Solana one hour scores 2, 24 hours 50 and four days or more 80; the rollup scorer gives 5, 20, 35 or 10 according to the roles, whatever the length of the delay. METHODOLOGY.md's "a confirmed real delay scores 60-75 depending on length" is the intent, not a property of every scorer. The requirements 3 and 4 of `scripts/badges_req.py` (60 and 75) apply to these different scales.

## The overlap score counts groups, not signers

`crossExposureScore` is `100 - 20` per group of targets that share at least one signer with this one (METHODOLOGY.md). One shared signer out of nine costs as much as the whole committee. A Safe whose owners could not be read (it answers with a revert) is left out of the registry without a note, and a group marked unresolved scores 100 (Spark's is labelled "not computed" in `data/dimension_basis.json`; Ekubo's is justified, it has no authority).

## Two committees under one protocol

Two public findings describe two different guardian seats of one lending protocol. One is a committee of 9 signers shared by several chains (`data/finding_2026-09-17-cross-ecosystem-aave-guardian-overlap.md`); the other is a 7-signer guardian that needs 4, found on 18 of the 19 deployments checked (`data/finding_2026-09-25-aave-guardian-18-chains.md`). They are two seats, not one committee counted twice: a later finding says the 9-signer seat had been read by a scorer and only logged, while the committee analysis covered the other seat. The cross exposure score caps a committee shared between ecosystems at 80 (METHODOLOGY.md, cross exposure, since 2026-09-20). Read the findings before reading a number about this protocol's guardian.

Written in: data/finding_2026-09-19-aave-guardian-ethereum-l1-fifth-chain-and-verifier-corrections.md (the explanation of the two seats); METHODOLOGY.md.

## Timelocks: what is read and what is not

Read: the delay of a timelock (`getMinDelay()` or `delay()`); the queue of operations, from the events `CallScheduled`, `CallExecuted` and `Cancelled` and from `QueueTransaction`, `ExecuteTransaction` and `CancelTransaction`, with `isOperationPending`; the proposer and canceller roles of a timelock, and the executor role where a scorer reads it (`scripts/lib/scorers.py`); the bypass paths named in METHODOLOGY.md.

Not read: the roles that can change the delay, in general. A change of the delay of the timelock that holds the admin role is read as an event over the blocks between two runs (`delay_change` in `second_opinion.json`: `MinDelayChange` of OpenZeppelin, `NewDelay` of Compound), and an executor role open to everyone (address zero) is read on that timelock (`open_executor`); on any other timelock neither is read. The end of an operation is told only when the chain can tell (`final_state` in `pending_ops.json`: `executed`, `cancelled`, `expired` or `unknown`), and an operation that left the queue before the read window is not seen. The queue of operations is published and shown, and no score reads it.

A Safe has no delay of its own. Its `timelockScore` is 0 unless a delay mechanism is found and read on the path, and a Safe module that is not analysed makes the Safe count as unresolved (METHODOLOGY.md); a guard does not lower the score. A module list that could not be read leaves the score as computed, with a note.

Written in: METHODOLOGY.md; scripts/check_pending_ops.py; scripts/lib/pending_ops.py.

## Money: a protocol's TVL is not the money one key could take

Two different money figures sit behind the same words. Where a contract answers `totalAssets()`, the figure is what that contract holds by its own account (`held_assets.json`). Otherwise the figure is the total value locked of the whole protocol, as DefiLlama reports it. The second is not the amount one key could move: a protocol's total value can sit behind other contracts than the one tracked. The independent reader (`second_opinion.json`) attaches that protocol figure to every tracked contract of the protocol, a retired or peripheral one included, and says which figure it used in the field `money_source` of `exposure` (`contract` or `protocol_tvl`). The totals by cause (`risk_by_cause.json`) work differently: a contract marked retired or peripheral in `tvl_scope.json` carries none of its protocol's value, a protocol is counted once per chain, and the contract's own figure is used only when there is no protocol match; they say per contract which kind of figure it is in `money_source` (`protocol_total`, `chain_figure`, `contract_figure` for a DefiLlama match at contract scope, `held_by_contract` for the contract's own balance, `out_of_scope`, `none`). These values are not those of `second_opinion.json`, where `contract` means the contract's own balance and `protocol_tvl` the DefiLlama figure of the protocol.

Written in: watch/API.md (`risk_by_cause.json`, `held_assets.json`, `second_opinion.json`).

## Money held by the contract itself is read for 31 of 176 EVM contracts

The amount a contract holds by its own account is read only for contracts that answer `totalAssets()` (and `asset()`). On the Watch run of 29 October 2026 (12:58:54 UTC), that was 31 of 176 EVM contracts (`held_assets.json`: 176 asked, 31 answered, none unpriced). A router, a pool, a token or a Solana program does not answer and is absent from the file, which is not a zero. For the other 145, the money figure, where there is one, is the protocol's value locked.

Written in: watch/API.md (`held_assets.json`).

## A figure here is dated, and a snapshot is as old as its date

- Distribution of the 202 composites on the Watch run of 29 October 2026 (12:58:54 UTC): critical 46, weak 28, moderate 75, decent 35, strong 18 (bands: critical 0 to 19, weak 20 to 39, moderate 40 to 59, decent 60 to 79, strong 80 to 100). It is recounted from `scores/*.json` of the `watch-data` branch at commit `a53d00a`, and it moves with each run.
- The check that compares signers between ecosystems uses a hard-coded snapshot of the other chain, dated in the name of its constant; the convention was decided and pushed on 2026-09-20 (METHODOLOGY.md, cross exposure). The published score files do not carry the date of that snapshot; since 30 October 2026 `cross_chain.json` does (`exposure_snapshot`: the date of the last sweep, 21 October 2026, and whether it is past its 30 days).
- The Robinhood Chain tokenized stocks and ETFs are about 230 tokens, of which 5 were sampled; the score published for them (1/100) comes from those 5 (CHANGELOG.md).
- The back-test cited in WHAT-THE-SCORE-SAYS.md (55 incidents, 7 about who controls a contract) lists its incidents on the Backtest page of the site, `realspap.github.io/oracle/backtest/`; the three `data/backtest_*.md` files in this repository are three separate retroactive back-tests of single incidents, not the 55.

Written in: CHANGELOG.md; METHODOLOGY.md; WHAT-THE-SCORE-SAYS.md.

## Amounts of past incidents are press figures

Dollar amounts of past incidents quoted in this repository (in `CHANGELOG.md`, `docs/LANDSCAPE.md`, `data/README.md` and the `data/backtest_*.md` files) are the figures given by the press or by the affected team at the time of writing. They are not measurements of chain state by this project, unless the file says it measured them, and they are not updated afterwards.

Written in: this page. The amounts appear in CHANGELOG.md, docs/LANDSCAPE.md, data/README.md and the data/backtest_*.md files.

## The oracle's own authority, by chain

On the Watch run of 29 October 2026 (`scores/<oracle>.json`, field `self.roles`), each of the eight EVM oracles lists one account that holds both the admin role and the updater role. Two accounts appear across the eight: one for Robinhood Chain and one for the seven others. The files do not say whether those accounts are plain keys; a direct read of 30 October 2026 found that all of them are (section "The oracle's own composite, by chain" below). For Solana, `scores/solana-devnet.json` carries no `self.roles`; `second_opinion.json` has a record flagged `oracle_self` for the oracle program, which reads its upgrade authority as a plain key (through its ProgramData account). On two of the eight (Base and Monad) the scan of the oracle's own role events gave up on that run (`read: false`, `gap_blocks` 214476 and 140651 in their score files), so a role change in that window was not read. The composite that the method gives to each oracle's own authority is in the section below. The other oracles hold no user funds, like the Ethereum one, and a consumer should weigh the single updater key on each of them first.

Written in: REFERENCE.md; SECURITY.md; watch/API.md.

## How long a change can stay unseen

The Watch starts every 6 hours (at 17 minutes past 0, 6, 12 and 18 UTC). A change that happens just after a run starts is first read by the next run, normally 6 hours later, plus the length of that run. The cadence is not a bound: the run of 29 October 2026 (12:58:54 UTC) came 11 hours 55 minutes after the previous one (01:04:06 UTC), because a scheduled run was missed. If you turn on the notify-me option of the dashboard on the site, it polls `latest.json` every 10 minutes, which adds up to 10 minutes. A scheduled GitHub job can also start late; no upper bound for that delay has been measured. A change that is made and undone between two runs is not seen. Alerts and feeds are published after a run ends, not when the change happens. For a change that matters within hours, read the chain directly.

Written in: watch/README.md; watch/API.md.

## What the 14-day table of actions can and cannot say

`score_series.json` lists the authority actions that the Watch itself saw in the last 14 days (a timelock operation or a Squads proposal queued or executed against a tracked contract, an admin change read independently, an upgrade executed) with the score the contract carried at that moment. On the run of 29 October 2026 it holds 21 actions, 6 of them on a contract scored under 40. The file counts the operations left out for these reasons (`calibration.excluded_undecoded`, `excluded_other_target`). It is a description of what was observed. It does not test whether low scores predict actions, it is not a calibration of the score, and with a count this small a gap between bands says little. An operation whose instructions were not decoded is not counted, and neither is one that was decoded but aims at something other than a tracked program.

Written in: watch/API.md (`score_series.json`).

## A transfer of control in progress is read by getter and, when the window was read completely, by event

A transfer of control that has been started and not yet accepted is read at each run by getter: `pendingOwner()` (Ownable2Step, on the contract or on its ProxyAdmin) and `pendingAdmin()` (Compound-style contracts). While one is set, the Watch raises a medium alert (`admin_pending`). The start, the acceptance and the cancellation of a transfer are read as events over the blocks between two runs when that window was read completely (`admin_events`: `OwnershipTransferStarted`, `OwnershipTransferred`, `DefaultAdminTransferScheduled`, `DefaultAdminTransferCanceled`, those of the target contract itself; not read: the events of its ProxyAdmin, `AdminChanged` of EIP-1967 and `NewPendingAdmin` of Compound; `null` when the window was not read completely, and then a transfer started and cancelled between two runs is not seen); in every case the Watch also compares the two readings at the next run (`pending_outcome`): `accepted` when the holder read is now the designated account, `replaced`, or `cleared` when the getter answers that nothing is designated, which is a cancellation or an acceptance on a path the record does not read (the two are not told apart). `pendingDefaultAdmin()` of `AccessControlDefaultAdminRules` is read since 30 October 2026, and so is its `defaultAdminDelay()` (`default_admin_delay_seconds`).

Written in: watch/API.md (`second_opinion.json`, `pending_admin`); rules.json.

## The oracle's own composite, by chain (direct read of 30 October 2026)

On 30 October 2026, from 03:31 UTC, `hasRole` was asked on each of the eight EVM oracles for the two accounts that the Watch knows, and the code of each account was read (public RPC endpoints, read only). On Robinhood Chain the account `0x646968c3...14ba` holds both the admin role and the updater role. On each of the seven other EVM oracles the account `0x20630C6A...32f5` holds both. Both accounts have no code: they are plain keys. On Solana, the registry account of the oracle program names one account (`BcwteMtY...y9yx`) as admin and as updater, and the upgrade authority of the program is the same account, also a plain key. The EVM oracles are not proxies: their code (3,387 to 3,619 bytes as read) is the oracle contract itself, which has no upgrade function (`src/AuthorityRiskOracle.sol`; the Robinhood Chain oracle runs an earlier version, see REFERENCE.md, "Deployed vs source").

To replay two of the calls (Foundry `cast`, read only; the first asks the admin role, the second the updater role):

```bash
cast call 0x9BF45734D09bC7CA39238e767B2af9AAc62a7f52 'hasRole(bytes32,address)(bool)' 0x0000000000000000000000000000000000000000000000000000000000000000 0x646968c33D8F6d5A343B68a6F8b1Ce52F13414ba --rpc-url https://rpc.testnet.chain.robinhood.com/rpc
cast call 0xB6F8474ccC71AF477c31c2DF663B3942ddfbf906 'hasRole(bytes32,address)(bool)' 0x73e573f9566d61418a34d5de3ff49360f9c51fec37f7486551670290f6285dab 0x20630C6Ab4BA48a80edA46F77b9b6e987A8f32f5 --rpc-url https://ethereum-sepolia-rpc.publicnode.com
```

This read shows that these accounts hold the roles. It does not show that no other account does: the contract does not list its role holders. The Watch reads the `RoleGranted` and `RoleRevoked` events of each oracle between two runs, not since the deployment, and gives up a window that is too large to read (`gap_blocks`). In the score files of the `watch-data` branch from 14 to 29 October 2026, the window was given up on 64 of 65 runs for Monad and 31 of 65 for Base.

Applying the published formula to these facts: a plain key with no multisig and no delay scores 0 for the multisig and 0 for the timelock, and METHODOLOGY.md ("The controller") scores the admin key of a plain key with no multisig and no delay 5. The composite of the oracle's own authority is therefore 2 out of 100, on each of the eight EVM oracles and on the Solana program, by the written rule. Some scorers in `scripts/lib/scorers.py` (the "same key" convention of `score_curve_dex`) give an admin key score of 2 instead of 5 when one plain key holds two separate control paths of a target; this convention is in the code, not in METHODOLOGY.md, and with it the composite would be 1 out of 100. Either way each of the nine oracles is in the critical band by the project's own method. These are calculations from the published method on what was read; they are not scores written on a chain, and the choice of 5 or 2 is a convention of the method, not a measurement. An earlier figure of about 4 on the EVM oracles and 2 on Solana, given on the oracle page until 31 October 2026, is replaced by the figures above.

Written in: this page; METHODOLOGY.md; REFERENCE.md; SECURITY.md; scripts/lib/scorers.py (`_composite`).
