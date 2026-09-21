# Ethereum L1 -- maintenance run, 2026-09-20 (second worker attempt)

Read-only on Ethereum mainnet (chain 1) and on the Sepolia oracle
(0xB6F8474ccC71AF477c31c2DF663B3942ddfbf906). **Nothing was pushed on-chain
by this pass**, by rule: the push command is prepared below and left for
Spap to run.

## (A) Audit rotation, index 1

`rotation_state.json -> ethereum-l1 -> last_audited_target_index = 1`.

`trackedTargets(1)` was **read live**, not assumed, on two independent
Sepolia RPCs (publicnode and tenderly -- drpc's Sepolia is paywalled on the
free plan and was skipped rather than silently counted):

    0x2f39d218133AFaB8F2B819B1066c7E434Ad94E9e
    = Aave V3 Ethereum PoolAddressesProvider (getMarketId() = "Aave Ethereum Market")

`getScore()` reads **78 / 100 / 55 / 100 / 80 / 78**, `lastUpdated`
1789863398 (2026-09-20 00:16:38 UTC).

The score was then re-derived from zero on two independent **mainnet** RPCs
(publicnode + drpc), without reading `chains/ethereum-l1/scorers.py`:

| Read live | Value |
|---|---|
| `PoolAddressesProvider.owner()` | `0x5300A1a15135EA4dc7aD5a167152C01EFc9b192A` (Executor lvl 1) |
| `Executor.owner()` | `0xdAbad81aF85554E9ae636395611C58F7eC1aAEc5` (PayloadsController) |
| `getExecutorSettingsByAccessControl(1)` | (Executor lvl 1, **86400 s**) |
| `PayloadsController.guardian()` | `0xCe52ab41C40575B072A18C9700091Ccbe4A06710`, Safe **5-of-9** |
| PROTOCOL_GUARDIAN `0x2CFe3ec4...8Aa30` | Safe **4-of-7** |
| `ACLManager.isEmergencyAdmin(Executor lvl 1)` | false |
| `ACLManager.isEmergencyAdmin(PROTOCOL_GUARDIAN)` | **true** (the bypass that keeps timelockScore at 55) |

Composite recomputed by hand from METHODOLOGY.md's published formula
`floor(0.4a + 0.3m + 0.3t + 0.5)` = `floor(0.4*78 + 0.3*100 + 0.3*55 + 0.5)`
= **78**, equal to the on-chain value.

**Zero divergence, so no correction and no re-push is needed for index 1.**
The check is a runnable script, not a claim: it exits 0 on agreement and 1
on any disagreement, and it was proved to have teeth by running it once with
a deliberately falsified expected value (`AUDIT_FAULT_INJECT=1`), which does
exit 1.

## (B) New targets: 4 added, out of a budget of 10

The budget is a ceiling. Four were taken rather than ten, because each one
was traced to its root live on two independent RPCs in this same pass; none
was accepted on a literal or on a prior file. Addresses all come from
DefiLlama-Adapters (this project's accepted primary address source).

| Target | Address | admin | msig | tl | oracle | cross | composite |
|---|---|---|---|---|---|---|---|
| Lido stETH | `0xae7ab96520DE3A18E5e111B5EaAb095312D7fE84` | 80 | 100 | 60 | **95** | 100 | 80 |
| EigenLayer StrategyManager | `0x858646372CC42E1A627fcE94aa7A7033e7CF075A` | 60 | 100 | **20** | 100 | 100 | 60 |
| Curve Stableswap-NG factory | `0x6A8cbed756804B16E05E741eDaBd5cB544AE21bf` | 78 | 100 | 65 | 100 | 100 | 81 |
| Rocket Pool RocketStorage | `0x1d8f8f00cfa6758d7bE78336684788Fb0ee0Fa46` | 55 | 0 | 0 | 100 | 100 | 22 |

TVL at the time of writing, from `api.llama.fi/protocol/<slug>`,
`currentChainTvls.Ethereum`: Lido $25.22B, EigenCloud (EigenLayer) $6.87B,
Rocket Pool $1.36B, Curve DEX $1.24B.

### What is actually new here

**Lido** -- the Aragon Voting app `0x2e59A20f` **no longer holds
`EXECUTE_ROLE`** on the Lido DAO Agent (`hasPermission` reads false live).
It is held by `0x23E0B465`, the Dual Governance admin executor, whose
`owner()` is the EmergencyProtectedTimelock `0xCE042530`:
`getAfterSubmitDelay()` 259200 s + `getAfterScheduleDelay()` 86400 s = a
**4-day enforced delay**, `isEmergencyModeActive()` false. A configured
emergency-governance path exists and was NOT bounded this pass, so
`timelockScore` stays at 60 rather than the 75 a bypass-free delay earns.
`oracleAuthorityScore` is deliberately **not** 100: stETH's share rate is
consumed as an oracle elsewhere and is set by the AccountingOracle, whose
HashConsensus reads `getQuorum()` = 5 of 9 members -> 95 under this file's
multisig formula.

**EigenLayer** -- the ProxyAdmin's owner is a Gnosis Safe with
`getThreshold()` = **1 of 2**. That is not a 1-of-2 signed by two people:
owner A is a real `TimelockController` with `getMinDelay()` = 864000 s
(10 days) and owner B is a **9-of-13** Safe. Threshold 1 means the 9-of-13
Safe can execute the same StrategyManager upgrade **with no delay at all**,
so the 10-day delay is a norm and not a guarantee. METHODOLOGY.md says to
score the gap, so `timelockScore` is 20. Attenuating context was looked for
and recorded: no Safe module is enabled on that executor Safe, so there is
no third, quieter path.

**Curve** -- `factory.admin()` is the Curve DAO Ownership Agent on Curve's
OWN Aragon deployment (a different Kernel and a different ACL from Lido's;
both were re-read rather than assumed). The role in use is `EXECUTE_ROLE`,
**not** `RUN_SCRIPT_ROLE` -- reading the wrong one returns a zero-address
manager and would have produced a false "unresolved root". Voting reads
`voteTime()` 604800 s (7 days), 51 % support, 30 % quorum.

**Rocket Pool** -- `getGuardian()` is a **bare EOA** (`0x0cCF1498`, no
bytecode) holding a named role on a $1.36B protocol. Before calling that
notable, the attenuating context was hunted for, and it is decisive:
`getDeployedStatus()` = true (the pre-deployment blanket write access is
closed) and the protocol DAO -- resolved **through RocketStorage itself**,
`getAddress(keccak256("contract.address" + "rocketDAOProtocol"))` =
`0xCaC25e88`, not from a literal -- reads `getBootstrapModeDisabled()` =
true. So this is a retired role, scored 55, not the 2-10 a live bare-EOA
admin earns. What remains to the EOA is the guardian handover itself
(selector `0x8a0dac4a` is present in the deployed bytecode), with no delay,
which is why `timelockScore` is 0 and `multisigScore` is 0.

### Side effects on the 14 existing targets: none

`_apply_cross_exposure()` groups by `_rootGroup`, and the four new groups are
all distinct from every existing one. This was verified by running the real
`score_all()` **twice against the same RPC** -- once with the 12 original
scorer functions, once with all 16 -- and diffing all six dimensions of
every preexisting target. All 14 are byte-identical; the four new ones score
`crossExposureScore` 100. The script exits 1 if any preexisting value moves.

### Correction to a previous run's wording

The Ethena USDe live minter `0xe3490297a08d6fC8Da46Edb7B6142E4F461b62D3`
(index 14) is **not** a finding of this run and is not counted in the 4
above. It entered the repo in commits `11657b3`, `042f805` and `f7af724` and
is already published in the table in `chains/ethereum-l1/deploy/README.md`.
A previous worker summary presented it as "1 new USDe minter" without
marking it as preexisting; that framing is corrected here, explicitly, per
the project's rule that a correction is labelled as one.

## Prepared push command -- for Spap to run, not for an agent

The scorer now produces **18 targets**. Nothing below was executed by this
session; the dry run was, and it exits 0 and encodes 10634 bytes of
`updateScores()` calldata (selector `0x5fb3feaf`).

Step 1, the dry run (safe, read-only, no key, no write RPC):

    python3 chains/ethereum-l1/deploy/update_scores_ethereum_l1.py --dry-run

Step 2, the real push -- **Spap runs this**, with the key never read by an
agent:

    READ_RPC_URL=https://ethereum-rpc.publicnode.com \
    ORACLE_RPC_URL=https://ethereum-sepolia-rpc.publicnode.com \
    ORACLE_ADDRESS=0xB6F8474ccC71AF477c31c2DF663B3942ddfbf906 \
    PRIVATE_KEY=<la cle du pipeline, jamais lue par un agent> \
    python3 chains/ethereum-l1/deploy/update_scores_ethereum_l1.py

Step 3, read-back verification (read-only, an agent may run this):

    cast call 0xB6F8474ccC71AF477c31c2DF663B3942ddfbf906 "trackedTargetsCount()(uint256)" \
      --rpc-url https://ethereum-sepolia-rpc.publicnode.com   # expect 19 after the push

The oracle has no removal function, so a push appends the 4 new targets to
the 15 already tracked and refreshes the rest. Index 3 (the retired Ethena
minter) is still deliberately unscored and will keep its 2026-09-19 reading.

## Executed, 2026-09-20 18:37 UTC (maker-checker proposal)

Spap ran the push through a wrapper pinned to commit `1481133` (dry run first, then the real run). The wrapper refuses to
send unless the oracle still tracks 15 targets, the dry run lists 18 targets with selector `0x5fb3feaf`, and the key
belongs to the updater `0x20630C6A...` and holds `UPDATER_ROLE`. The agent never read the key.

| Field | Value |
|---|---|
| `updateScores()` tx | `0xc4873381005620ab0f560b5d8a1f998d316dd55081bba217297b95ad8e3cba46` |
| Block / status / gas | Sepolia 11745959 / 1 / 661,920 |
| Events | 18 `ScoreUpdated` |
| `trackedTargetsCount()` | 15 before, 19 after (Lido stETH 15, EigenLayer StrategyManager 16, Curve Stableswap-NG factory 17, Rocket Pool RocketStorage 18) |
| Read-back | `getScore()` on all 18 scored targets equals the scorer output of `1481133`, 0 differences; index 3 (retired Ethena minter) is not compared |

Rehearsed before the real run on a local anvil fork of Sepolia with a throwaway key granted `UPDATER_ROLE` by impersonating
the admin: same transaction, count 19, 18 of 18 matching. The read-back was done twice, by the run itself and by a separate
read-only pass. The script's own text "--dry-run not set: this phase (scoring_build) does not send" is out of date (the
send path ran), and is left as found.
