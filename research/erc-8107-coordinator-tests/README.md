# ERC-8107 coordinator tests

Executable tests for the coordinator side of [ERC-8107](https://github.com/ethereum/ERCs/blob/6b7a48ffa791e30ceee94d869b5eae9521fe158f/ERCS/erc-8107.md) (ENS trust registry for agent identity gates), on a fork of Ethereum mainnet. They use the real ENS contracts and the reference `TrustRegistry` and `RegistrationBoundary` of `ethereum/ERCs`, pinned at commit `6b7a48ffa791e30ceee94d869b5eae9521fe158f`: the text that [PR #2099](https://github.com/ethereum/ERCs/pull/2099) proposes for Last Call (that PR changes only the header of this commit; on master, read on 2026-10-25, it was still in Review, and master had gained PR #2100 and PR #2101, merged on 2026-10-23, so master's text is not the text of #2099). No transaction is sent: the fork lives in forge's memory and the node is only read.

**Licence.** This folder is CC0-1.0 (see `LICENSE`): free to reuse. It is an exception to the rest of this repository (code MIT, text and data CC BY 4.0).

## What is here

- `test/Coordinator8107.sol`: one complete coordinator written from the text of the ERC, in two stages. **Decision** (block B): `verifyPath` with `enforceExpiry`; continuity of registration with the reference `RegistrationBoundary` (`Unknown` fails closed); liveness of every wrapped trustor on the path; the expiry E of every `.eth` second-level name on the path. **Execution** (the executing transaction): the registry's own `validateParticipantAddress`; for each recorded name, `block.timestamp <= E + GRACE_PERIOD` or `nameExpires` still returns E; the NameWrapper's `ownerOf` of every wrapped trustor on the path (not the terminal node) is not the zero address. Each step can be switched off by name.
- `test/CompleteCoordinator.t.sol`: seven scenarios (S0 to S6), each aimed at one step. S5 is the case added to the ERC by [PR #2098](https://github.com/ethereum/ERCs/pull/2098): a wrapped trustor in the middle of the path (an emancipated subname that passes its NameWrapper expiry) loses its controller between the decision and the execution, while the registry's evaluation still accepts the path.
- `test/Wrapped2LDGrace.t.sol`: S7, added on 2026-11-03: a wrapped `.eth` second-level trustor decided on in its grace period (three tests, S7, S7b and S7c; see "S7" below).
- `test/TwoAliases.t.sol`: two ENS names that resolve to the same address. The gatekeeper endorses both and denies one at universal scope. What does `validateParticipantAddress` return for that address?
- `test/Base8107.sol`: the shared fork setup.
- `jouer.sh`: runs everything, then runs each test file again with one step (or one denial) left out. `jouer-s7.sh`: runs S7 only, then again with each step left out. `fetch.sh`: downloads the three reference files at the pinned commit and checks their sha256.
- `sorties/`: the raw output of the runs recorded below, unedited. The run of 2026-10-23 is in `aliases-*`, `coordinator-*` and `lignes-OBS-*` of those; the run of S7 (2026-11-03) is in `wrapped2ld-*`, with the same run on a second node in `sorties/drpc/`; `pr2101-test-at-26192453-*` is described under S7.

## Replay

```bash
forge install foundry-rs/forge-std@v1.9.7 OpenZeppelin/openzeppelin-contracts@v5.4.0 --no-git   # once
bash fetch.sh                            # downloads the three reference files at the pinned commit and checks their sha256
NODE=<archive node URL> bash jouer.sh    # block 26192453, Ethereum mainnet, ENS v1
NODE=<archive node URL> bash jouer-s7.sh # S7 only (it is not part of jouer.sh)
```

`NODE` should be an archive node of Ethereum mainnet that can read block 26192453 (state from the past). If `NODE` is not set, `jouer.sh` falls back to a public gateway (`https://gateway.tenderly.co/public/mainnet`). That gateway answered a single balance read of this block on 2026-11-01, but a public gateway can limit old state or the request rate: if the run fails on reads, use your own archive node.

No key is needed or used. Foundry 1.8.3 (commit `cae51ad`) was used for both runs, with solc 0.8.28 and via-IR. Under via-IR the compiler may reuse a `block.timestamp` read across `vm.warp`: the tests read time with `vm.getBlockTimestamp()`. In `Coordinator8107.sol`, `block.timestamp` is the real thing a deployed coordinator would read.

## Results (run of 2026-10-23, block 26192453)

**Two aliases.** `agent.eth` and `backup.eth` both resolve to X; the gatekeeper G endorses both and then denies `agent.eth` at universal scope.

| Case | `validateParticipantAddress(X)` via `[G, agent.eth]` | via `[G, backup.eth]` |
|---|---|---|
| no denial | accepts | accepts |
| G denies `agent.eth` | refuses | **accepts** |
| G denies both names | refuses | refuses |
| denial cleared | accepts | accepts |

After one name is denied, the address is still admitted through the other name, whose path contains no denied node, and no new endorsement is needed. A name that resolves to X but that G never endorsed is refused. This describes the reference contracts at the pinned commit, and the alias cases here measure that commit, not a later text. At the pinned commit the ERC text says quarantine denies a counterparty (a name) and does not say what happens to an address that another eligible name resolves to. Since then PR #2100 (merged 2026-10-23; master 4891ba3b, read on 2026-10-25) added an Address Aliases section (master lines 2876-2897) and a test bullet (line 2625) that state this case with the same two names: denial excludes a name, not the address it resolves to, and the address is still admitted through the other name with no new endorsement. The first two rows above agree with that text; the last two (both names denied, denial cleared) are not stated by it.

**Complete coordinator.** `bash jouer.sh`, real run of 2026-10-23: 7 of 7 scenarios pass (S0 to S6). S7 is run apart, by `bash jouer-s7.sh` (run of 2026-11-03, see "S7" below): it passes too, which makes eight scenarios of eight, in two runs. Then each step is switched off in turn, and exactly the scenario aimed at it fails:

| Step switched off | Scenario that then fails | What the coordinator then wrongly accepts |
|---|---|---|
| `verify` | S0 | an edge past its end date |
| `continuity` | S2 | a path whose middle name was registered again after the endorsement |
| `liveness-decision` | S6 | a wrapped trustor with no controller at the decision |
| `deadline` | S3 | a name registered again after the decision, in the executing block |
| `liveness-execution` | S5 | a wrapped trustor in the middle of the path that lost its controller before the execution |

S1 and S4 (nothing happens; a renewal in the grace period) are controls: they pass in every run. For the two aliases, leaving out the second denial makes the assertion "X is refused when G denies both names" fail.

## S7: a wrapped `.eth` second-level trustor decided on in its grace period (run of 2026-11-03)

The case is the one tested as `test_Wrapped2LDTrustorPastWrapperExpiry` in [PR #2101](https://github.com/ethereum/ERCs/pull/2101) (reference coordinator tests, merged 2026-10-23, merge commit `831b1c15a6d83bf3fbb46c6ce4c2c8ec13a59743`). The scenario here is written from that description for the coordinator of this folder; it is not copied from the PR. The path is G > T > M, where T is a `.eth` second-level name registered for one year and then wrapped in the NameWrapper.

- **Decision.** The block time is moved (`vm.warp`) to E + 30 days, where E is T's expiry at the BaseRegistrar: T is in its grace period and the NameWrapper still has a holder for it. The decision accepts.
- **Execution.** The time is moved to E + GRACE_PERIOD + 1 second (90 days after E). The NameWrapper has let T's wrapper expire, so `ownerOf(T)` is the zero address. Nobody registered the name again, so `nameExpires` still returns E and the expiry check is satisfied. The registry's evaluation still accepts: `validateParticipantAddress` reads the controller of the terminal node only. **The execution is refused only by the liveness check at execution.**
- **S7b.** At the same moment both registry evaluations are logged, `validateParticipantAddress` and `validateParticipantWithPath` (the latter with the terminal node and the same path). Both accept. The block number printed by that line, 26192459, is the fork block plus the few blocks created by the test's own setup.
- **S7c.** The decision is taken at E + GRACE_PERIOD exactly: `ownerOf(T)` is not the zero address and the decision accepts. One second later the execution is refused by the liveness check.

| Step switched off | S7 | S7c | S7b (logs only) |
|---|---|---|---|
| none | passes | passes | accepts / accepts |
| `verify`, `continuity`, `liveness-decision`, `deadline` | passes (same result) | passes | accepts / accepts |
| `liveness-execution` | **fails**: the execution is accepted | **fails**: the execution is accepted | accepts / accepts |

So, for this coordinator, the liveness check at execution is the only step that tells this case apart: removing any other step changes nothing.

**Where and with what.** Fork of Ethereum mainnet at block 26192453 (chain id 1; block hash `0xfd5d63d6e68614eb2dfa50100dd4542b12f828ba3a5bceae8a98a2609d3b4778`; timestamp 1792001507, 2026-10-14 18:11:47 UTC; the hash and timestamp read on two nodes, which agree). Two public nodes, run on 2026-11-03: `https://gateway.tenderly.co/public/mainnet` at 16:25:54Z (`sorties/wrapped2ld-*`) and `https://eth.drpc.org` at 16:26:33Z (`sorties/drpc/wrapped2ld-*`); the `OBS|` lines of the two are identical, file by file. Foundry 1.8.3, solc 0.8.28, via-IR, `--no-storage-caching`, the reference files pinned at `6b7a48ff` (sha256 checked by `fetch.sh`). No transaction is sent; no key is used.

**The tests of PR #2101 at the same block.** The six tests of `ReferenceCoordinatorForkTest` of that PR, at its merge commit, with one change (the pinned block constant, 26194700, replaced by 26192453), pass 6 of 6 on the same two nodes with `--no-storage-caching` (read on 2026-11-03 at 10:42-10:43 UTC; the outputs are `sorties/pr2101-test-at-26192453-*.txt`), `test_Wrapped2LDTrustorPastWrapperExpiry` and `test_EmancipatedTrustorExpiresBeforeExecution` among them. The PR's files are not copied into this folder.

**What S7 shows.** That the coordinator written here, from the text at `6b7a48ff`, reaches the same verdict as the reference coordinator of PR #2101 on this case at this block: the case can be built on a fork at block 26192453, the registry's evaluation does not refuse it, and the liveness check at execution does. The grace period and the wrapper expiry are dates moved by `vm.warp`: the block fixes only the state of ENS v1 and of the contracts, not whether T is in grace at that block.

**What S7 does not show.** That the two coordinators agree on every path: the coordinator here is ours, and agreement on one case is not a proof that either is correct. Nothing about another block, a recent block, ENS v2 or another NameWrapper, or other names than the one the test registers. Nothing about what a deployed coordinator should do: the test reports what the reference contracts and this coordinator do. S7b is a test added here to log the two registry evaluations; it passes through this coordinator's world, not through the PR's `ReferenceCoordinator`.

## Limits

One block, ENS v1, one scenario per step (S7 adds one more case, on the liveness step), one pair of aliases. A passing run shows that the coordinator written here refuses these cases and accepts the controls; it does not show that the list of steps is complete or that the coordinator is correct for every path. "A wrapped trustor" is recognised here by the ENS registry owner being the NameWrapper, a choice the text does not specify. The tests make no claim about the ERC's design: they report what the reference contracts do. The dated statements about PR #2099, PR #2100, PR #2101 and master were read on the dates given and were not re-read when this folder was added to this repository. The statements about PR #2101 under S7 (merge commit and its six tests at block 26192453) were read on 2026-11-03.
