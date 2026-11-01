# ERC-8107 coordinator tests

Executable tests for the coordinator side of [ERC-8107](https://github.com/ethereum/ERCs/blob/6b7a48ffa791e30ceee94d869b5eae9521fe158f/ERCS/erc-8107.md) (ENS trust registry for agent identity gates), on a fork of Ethereum mainnet. They use the real ENS contracts and the reference `TrustRegistry` and `RegistrationBoundary` of `ethereum/ERCs`, pinned at commit `6b7a48ffa791e30ceee94d869b5eae9521fe158f`: the text that [PR #2099](https://github.com/ethereum/ERCs/pull/2099) proposes for Last Call (that PR changes only the header of this commit; on master, read on 2026-10-25, it was still in Review, and master had gained PR #2100 and PR #2101, merged on 2026-10-23, so master's text is not the text of #2099). No transaction is sent: the fork lives in forge's memory and the node is only read.

**Licence.** This folder is CC0-1.0 (see `LICENSE`): free to reuse. It is an exception to the rest of this repository (code MIT, text and data CC BY 4.0).

## What is here

- `test/Coordinator8107.sol`: one complete coordinator written from the text of the ERC, in two stages. **Decision** (block B): `verifyPath` with `enforceExpiry`; continuity of registration with the reference `RegistrationBoundary` (`Unknown` fails closed); liveness of every wrapped trustor on the path; the expiry E of every `.eth` second-level name on the path. **Execution** (the executing transaction): the registry's own `validateParticipantAddress`; for each recorded name, `block.timestamp <= E + GRACE_PERIOD` or `nameExpires` still returns E; the NameWrapper's `ownerOf` of every wrapped trustor on the path (not the terminal node) is not the zero address. Each step can be switched off by name.
- `test/CompleteCoordinator.t.sol`: seven scenarios, each aimed at one step. S5 is the case added to the ERC by [PR #2098](https://github.com/ethereum/ERCs/pull/2098): a wrapped trustor in the middle of the path (an emancipated subname that passes its NameWrapper expiry) loses its controller between the decision and the execution, while the registry's evaluation still accepts the path.
- `test/TwoAliases.t.sol`: two ENS names that resolve to the same address. The gatekeeper endorses both and denies one at universal scope. What does `validateParticipantAddress` return for that address?
- `test/Base8107.sol`: the shared fork setup.
- `jouer.sh`: runs everything, then runs each test file again with one step (or one denial) left out. `fetch.sh`: downloads the three reference files at the pinned commit and checks their sha256.
- `sorties/`: the raw output of the run recorded below, unedited.

## Replay

```bash
forge install foundry-rs/forge-std@v1.9.7 OpenZeppelin/openzeppelin-contracts@v5.4.0 --no-git   # once
bash fetch.sh                            # downloads the three reference files at the pinned commit and checks their sha256
NODE=<archive node URL> bash jouer.sh    # block 26192453, Ethereum mainnet, ENS v1
```

`NODE` should be an archive node of Ethereum mainnet that can read block 26192453 (state from the past). If `NODE` is not set, `jouer.sh` falls back to a public gateway (`https://gateway.tenderly.co/public/mainnet`). That gateway answered a single balance read of this block on 2026-11-01, but a public gateway can limit old state or the request rate: if the run fails on reads, use your own archive node.

No key is needed or used. Foundry 1.8.3 was used (solc 0.8.28, via-IR). Under via-IR the compiler may reuse a `block.timestamp` read across `vm.warp`: the tests read time with `vm.getBlockTimestamp()`. In `Coordinator8107.sol`, `block.timestamp` is the real thing a deployed coordinator would read.

## Results (run of 2026-10-23, block 26192453)

**Two aliases.** `agent.eth` and `backup.eth` both resolve to X; the gatekeeper G endorses both and then denies `agent.eth` at universal scope.

| Case | `validateParticipantAddress(X)` via `[G, agent.eth]` | via `[G, backup.eth]` |
|---|---|---|
| no denial | accepts | accepts |
| G denies `agent.eth` | refuses | **accepts** |
| G denies both names | refuses | refuses |
| denial cleared | accepts | accepts |

After one name is denied, the address is still admitted through the other name, whose path contains no denied node, and no new endorsement is needed. A name that resolves to X but that G never endorsed is refused. This describes the reference contracts at the pinned commit, and the alias cases here measure that commit, not a later text. At the pinned commit the ERC text says quarantine denies a counterparty (a name) and does not say what happens to an address that another eligible name resolves to. Since then PR #2100 (merged 2026-10-23; master 4891ba3b, read on 2026-10-25) added an Address Aliases section (master lines 2876-2897) and a test bullet (line 2625) that state this case with the same two names: denial excludes a name, not the address it resolves to, and the address is still admitted through the other name with no new endorsement. The first two rows above agree with that text; the last two (both names denied, denial cleared) are not stated by it.

**Complete coordinator.** `bash jouer.sh`, real run: 7 of 7 scenarios pass. Then each step is switched off in turn, and exactly the scenario aimed at it fails:

| Step switched off | Scenario that then fails | What the coordinator then wrongly accepts |
|---|---|---|
| `verify` | S0 | an edge past its end date |
| `continuity` | S2 | a path whose middle name was registered again after the endorsement |
| `liveness-decision` | S6 | a wrapped trustor with no controller at the decision |
| `deadline` | S3 | a name registered again after the decision, in the executing block |
| `liveness-execution` | S5 | a wrapped trustor in the middle of the path that lost its controller before the execution |

S1 and S4 (nothing happens; a renewal in the grace period) are controls: they pass in every run. For the two aliases, leaving out the second denial makes the assertion "X is refused when G denies both names" fail.

## Limits

One block, ENS v1, one scenario per step, one pair of aliases. A passing run shows that the coordinator written here refuses these cases and accepts the controls; it does not show that the list of steps is complete or that the coordinator is correct for every path. "A wrapped trustor" is recognised here by the ENS registry owner being the NameWrapper, a choice the text does not specify. The tests make no claim about the ERC's design: they report what the reference contracts do. The dated statements about PR #2099, PR #2100, PR #2101 and master were read on the dates given and were not re-read when this folder was added to this repository.
