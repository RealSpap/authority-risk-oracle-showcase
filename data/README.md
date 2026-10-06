# Data

Every dated note behind a number or a claim in this repository. Notes are never rewritten after the fact: a mistake is published as a `correction_*` note next to the one it corrects.

JSON files here (`authority_index_*`, `implementation_snapshot`, `signer_kinds_snapshot`, `squads_snapshot`, `score_change_causes`) are the snapshots the watch tools diff against.

## Findings (59)

What a sweep, a trace or a comparison found, dated.

- [`finding_2026-09-17-cross-ecosystem-aave-guardian-overlap.md`](finding_2026-09-17-cross-ecosystem-aave-guardian-overlap.md): Cross-ecosystem finding (2026-09-17): Aave V3's emergency guardian is the SAME 9-person committee on Arbitrum and Base
- [`finding_2026-09-17-hyperliquid-hip3-evm-proxy-authority.md`](finding_2026-09-17-hyperliquid-hip3-evm-proxy-authority.md): some HIP-3 dex deployer addresses are ALSO live, upgradeable EVM proxies -- the specific one checked turned out to be unrelated infrastructu
- [`finding_2026-09-17-spl-governance-shared-instance-controller.md`](finding_2026-09-17-spl-governance-shared-instance-controller.md): who actually controls the SPL Governance shared default instance
- [`finding_2026-09-18-competitive-positioning-cross-chain-overlap.md`](finding_2026-09-18-competitive-positioning-cross-chain-overlap.md): four targeted competitive checks, not a repeat of the general scan
- [`finding_2026-09-18-cross-chain-dao-bridge-and-multisig-grid.md`](finding_2026-09-18-cross-chain-dao-bridge-and-multisig-grid.md): the DAO-via-bridge sub-model and the cross-chain multisig grid, quantified
- [`finding_2026-09-18-cross-ecosystem-overlap-tempo-aerodrome.md`](finding_2026-09-18-cross-ecosystem-overlap-tempo-aerodrome.md): Cross-ecosystem check extended to Tempo and Aerodrome's emergencyCouncil (2026-09-18) -- clean result
- [`finding_2026-09-18-cross-ecosystem-unresolved-floor-inversion.md`](finding_2026-09-18-cross-ecosystem-unresolved-floor-inversion.md): the "unresolved authority" fallback score outranks a confirmed weak authority in most ecosystems -- Zcash already fixed it, Solana and Ether
- [`finding_2026-09-18-erc8241-compatibility-evaluation.md`](finding_2026-09-18-erc8241-compatibility-evaluation.md): Evaluation (2026-09-18): ERC-8241 "Protocol Control Disclosure" compatibility with authority-risk-oracle
- [`finding_2026-09-18-morpho-generic-1of1-safe-treatment.md`](finding_2026-09-18-morpho-generic-1of1-safe-treatment.md): should `score_morpho_vault_generic` treat a 1-of-1 Safe as EOA-equivalent? Evidence for the decision, not a fix
- [`finding_2026-09-18-scorers-hardcoded-score-literals.md`](finding_2026-09-18-scorers-hardcoded-score-literals.md): 5 scorers in `scripts/lib/scorers.py` perform real live reads but never actually condition their score on the result
- [`finding_2026-09-18-signer-overlap-unresolved-note-registry-leak.md`](finding_2026-09-18-signer-overlap-unresolved-note-registry-leak.md): an `unresolved_note` group in `signer_overlap.py` is exempt from being SCORED on overlap, but not from COUNTING as another group's overlap
- [`finding_2026-09-19-aave-guardian-ethereum-l1-fifth-chain-and-verifier-corrections.md`](finding_2026-09-19-aave-guardian-ethereum-l1-fifth-chain-and-verifier-corrections.md): the Aave guardian committee is on 5 chains, not 4, plus a list of repo inaccuracies an independent verification pass found
- [`finding_2026-09-19-base-morpho-blue-robinhood-overlap.md`](finding_2026-09-19-base-morpho-blue-robinhood-overlap.md): Base's Morpho Blue and Robinhood Chain's Morpho Blue share the identical governance committee -- found by sweeping already-established ecosy
- [`finding_2026-09-19-hyperliquid-khype-kmhype-identity.md`](finding_2026-09-19-hyperliquid-khype-kmhype-identity.md): Hyperliquid target #6 was mislabeled kHYPE, is actually kmHYPE
- [`finding_2026-09-19-monad-cross-ecosystem-overlap.md`](finding_2026-09-19-monad-cross-ecosystem-overlap.md): two real cross-chain signer/address overlaps, found by wiring Monad into `check_cross_ecosystem_overlap.py`
- [`finding_2026-09-19-monad-new-targets-scouting.md`](finding_2026-09-19-monad-new-targets-scouting.md): 2 new Monad mainnet targets added (Aave V3, Euler V2), 1 found and honestly discarded (Pendle V2)
- [`finding_2026-09-20-competitor-gaps-and-morpho-vault-layer.md`](finding_2026-09-20-competitor-gaps-and-morpho-vault-layer.md): where competitors leave holes the oracle can fill, and one new territory found on the way
- [`finding_2026-09-20-compound-pause-guardian-three-chains.md`](finding_2026-09-20-compound-pause-guardian-three-chains.md): Compound V3's pause guardian is one 9-signer committee on three chains
- [`finding_2026-09-20-cross-exposure-convention-and-score-adjustments.md`](finding_2026-09-20-cross-exposure-convention-and-score-adjustments.md): crossExposureScore now folds cross-ecosystem overlaps on every EVM ecosystem, and 11 scorer outputs moved
- [`finding_2026-09-20-ethena-live-minter.md`](finding_2026-09-20-ethena-live-minter.md): the Ethena target was USDe's retired minter, and the live minter now scores 65/100/55
- [`finding_2026-09-20-scorer-test-audit.md`](finding_2026-09-20-scorer-test-audit.md): Scorer test audit, 2026-09-20: what executing the untested scorer bodies found
- [`finding_2026-09-20-uniswap-one-timelock-eleven-targets.md`](finding_2026-09-20-uniswap-one-timelock-eleven-targets.md): One Uniswap Timelock is the root of 11 tracked targets on 5 ecosystems (2026-09-20)
- [`finding_2026-09-20-unscored-role-sweep.md`](finding_2026-09-20-unscored-role-sweep.md): an unscored-role sweep of every EVM ecosystem, and a second Aave committee on five chains
- [`finding_2026-09-20-yuzu-authority-trace.md`](finding_2026-09-20-yuzu-authority-trace.md): Yuzu Money's placeholder score rested on a false negative; the real authority chain is a 3-of-5 Safe with an instant pool seat
- [`finding_2026-09-21-cross-exposure-consistency-audit.md`](finding_2026-09-21-cross-exposure-consistency-audit.md): Cross-exposure consistency audit (2026-09-21)
- [`finding_2026-09-21-implementation-changes.md`](finding_2026-09-21-implementation-changes.md): The code behind a target changes; the oracle only scores who controls it (2026-09-21)
- [`finding_2026-09-21-safe-modules-and-guards.md`](finding_2026-09-21-safe-modules-and-guards.md): Safe modules and guards on the registered root Safes (2026-09-21)
- [`finding_2026-09-21-who-really-signs.md`](finding_2026-09-21-who-really-signs.md): Who really signs the registered root Safes (2026-09-21)
- [`finding_2026-09-25-aave-guardian-18-chains.md`](finding_2026-09-25-aave-guardian-18-chains.md): One 7-signer committee holds Aave V3's emergency-pause seat on 18 of ~19 real deployments
- [`finding_2026-09-25-aave-v3-pool-risk-admin-discovery.md`](finding_2026-09-25-aave-v3-pool-risk-admin-discovery.md): Aave V3 Ethereum Pool: role-holder discovery extended to the flagship target
- [`finding_2026-09-25-bounded-power-cap-investigation.md`](finding_2026-09-25-bounded-power-cap-investigation.md): Bounded-power timelockScore cap: investigated across 8 files, no unfixed gap found
- [`finding_2026-09-25-controller-concentration.md`](finding_2026-09-25-controller-concentration.md): Controller-level concentration over this oracle's own tracked Morpho V1 vaults
- [`finding_2026-09-25-exit-capacity-vs-timelock.md`](finding_2026-09-25-exit-capacity-vs-timelock.md): A vault's timelock next to its actual exit capacity
- [`finding_2026-09-25-governance-capture-quantified.md`](finding_2026-09-25-governance-capture-quantified.md): Governance-capture concentration, quantified for the first time (Uniswap + Aave Governance V3 + Solend/Realms)
- [`finding_2026-09-25-hyperliquid-cross-ecosystem-overlap.md`](finding_2026-09-25-hyperliquid-cross-ecosystem-overlap.md): Hyperliquid added to the cross-ecosystem signer-overlap registry
- [`finding_2026-09-25-nested-signers-formula-investigation.md`](finding_2026-09-25-nested-signers-formula-investigation.md): Nested-signers multisig formula: investigated, no live bug found, not applied
- [`finding_2026-09-25-vault-v2-inventory.md`](finding_2026-09-25-vault-v2-inventory.md): Vault V2 disclosed inventory: $2.87B across 27 vaults, none previously tracked
- [`finding_2026-09-25-vault-v2-scoring-scope.md`](finding_2026-09-25-vault-v2-scoring-scope.md): Morpho Vault V2 scoring: scoped, not built -- a real methodology decision, not a mechanical extension
- [`finding_2026-09-26-aave-v3-pool-reserve-issuer-power.md`](finding_2026-09-26-aave-v3-pool-reserve-issuer-power.md): Issuer power extended to Aave V3 Ethereum Pool's 67 reserve assets ($14.77B TVL)
- [`finding_2026-09-26-authority-index-and-7702-signers.md`](finding_2026-09-26-authority-index-and-7702-signers.md): Authority index ("what can this key touch?") and a first EIP-7702 signer scan
- [`finding_2026-09-26-controller-v2-reach-folded-in.md`](finding_2026-09-26-controller-v2-reach-folded-in.md): Steakhouse Safe's true reach folded into the controller-concentration report
- [`finding_2026-09-26-incident-configurations-vs-published-scores.md`](finding_2026-09-26-incident-configurations-vs-published-scores.md): Between a quarter and a half of what the oracle publishes scores at or below Bybit's configuration before the hack (exposure, not prediction
- [`finding_2026-09-26-issuer-power-tracked-assets.md`](finding_2026-09-26-issuer-power-tracked-assets.md): Issuer power on the 4 assets this oracle's own tracked vaults actually hold
- [`finding_2026-09-26-l1-custody-authority-traces.md`](finding_2026-09-26-l1-custody-authority-traces.md): Six large Ethereum L1 custody contracts: who can move them (investigation, nothing scored)
- [`finding_2026-09-26-morpho-admin-posted-price-feeds.md`](finding_2026-09-26-morpho-admin-posted-price-feeds.md): Nine Morpho markets ($130M) price their collateral from a number a role holder POSTS, not from a market
- [`finding_2026-09-26-morpho-market-oracle-authority-rerun.md`](finding_2026-09-26-morpho-market-oracle-authority-rerun.md): Who can move the price a Morpho market trusts: 5-day rerun, MetaOracles unwrapped, a second feed committee found
- [`finding_2026-09-26-pending-timelock-ops.md`](finding_2026-09-26-pending-timelock-ops.md): What is queued behind the watched timelocks (2026-09-26): nothing executable, 24 dead entries, recent traffic listed
- [`finding_2026-09-26-safe-changes-30d-and-v150-singleton.md`](finding_2026-09-26-safe-changes-30d-and-v150-singleton.md): What changed on the tracked Safes in 30 days, and a Safe v1.5.0 blind spot it exposed
- [`finding_2026-09-26-sentora-spark-rlusd-subproxy-resolved.md`](finding_2026-09-26-sentora-spark-rlusd-subproxy-resolved.md): Sentora x Spark RLUSD's $250M SubProxy owner: resolved, not a mystery
- [`finding_2026-09-26-tvl-coverage-by-ecosystem.md`](finding_2026-09-26-tvl-coverage-by-ecosystem.md): Share of each ecosystem's TVL the tracked targets cover, and the biggest untracked protocols (2026-09-26, figures re-read 2026-09-27)
- [`finding_2026-09-26-vault-controller-7702-and-adpend-timelock.md`](finding_2026-09-26-vault-controller-7702-and-adpend-timelock.md): Morpho vault controllers: EIP-7702 across 165 vaults, and one timelock the Adpend USDC scorer does not count
- [`finding_2026-09-26-wbeth-and-ssv-authority.md`](finding_2026-09-26-wbeth-and-ssv-authority.md): The two largest untracked Ethereum protocols by TVL: one is a single-key token, the other is a 5-of-9 Safe (investigation, nothing scored)
- [`finding_2026-09-27-five-custody-protocols-edgex-sodex-aera-valos-derive.md`](finding_2026-09-27-five-custody-protocols-edgex-sodex-aera-valos-derive.md): Five more custody protocols traced: edgeX, SoDEX, Aera V3, Valos, Derive (investigation, nothing scored)
- [`finding_2026-09-27-posture-drift-sweep-and-hyperliquid-false-positive.md`](finding_2026-09-27-posture-drift-sweep-and-hyperliquid-false-positive.md): Full posture-drift sweep (27/09): one real drift explained, one tool false-positive found and fixed
- [`finding_2026-09-30-defiscan-diff-triage.md`](finding_2026-09-30-defiscan-diff-triage.md): DeFiScan v2 diff, first triage: 4 real coverage gaps, no published score changes, 5 DeFiScan errors (investigation, nothing scored)
- [`finding_2026-10-01-aave-capo-price-authority.md`](finding_2026-10-01-aave-capo-price-authority.md): Who can move the prices Aave V3 Ethereum Core lends against: 58% of supply is priced by Aave's own adapters, moved by a two-key council and 
- [`finding_2026-10-01-backtest-victims-vs-controls.md`](finding_2026-10-01-backtest-victims-vs-controls.md): the score does not separate them (pre-registered, Ethereum, 5 sets)
- [`finding_2026-10-04-price-paths-beyond-one-hop.md`](finding_2026-10-04-price-paths-beyond-one-hop.md): Price paths one hop further upstream than the oracleAuthorityScore looks: disclosed, not scored
- [`finding_2026-10-05-price-consumer-scope-study.md`](finding_2026-10-05-price-consumer-scope-study.md): Which other tracked targets read prices, how to score them, and what that needs decided first

## Corrections (14)

Errors found by this project's own review, published rather than edited away.

- [`correction_2026-09-16-aave-emergency-admin-identified.md`](correction_2026-09-16-aave-emergency-admin-identified.md): Aave V3 Ethereum's EMERGENCY_ADMIN_ROLE holder identified (2026-09-16)
- [`correction_2026-09-16-uniswap-bridge-alias.md`](correction_2026-09-16-uniswap-bridge-alias.md): Uniswap stack's "vanity-ground bare EOA" was wrong
- [`correction_2026-09-17-adversarial-bug-hunt.md`](correction_2026-09-17-adversarial-bug-hunt.md): Adversarial bug hunt (2026-09-17): 18 confirmed real bugs found and fixed
- [`correction_2026-09-17-drift-protocol-adversarial-review.md`](correction_2026-09-17-drift-protocol-adversarial-review.md): adversarial review of Drift Protocol (2026-09-17)
- [`correction_2026-09-17-kinetiq-staking-manager-adversarial-review.md`](correction_2026-09-17-kinetiq-staking-manager-adversarial-review.md): adversarial review of Kinetiq HIP3StakingManager (2026-09-17)
- [`correction_2026-09-17-missing-crossexposure-field.md`](correction_2026-09-17-missing-crossexposure-field.md): `crossExposureScore` was entirely missing from two ecosystem scorers
- [`correction_2026-09-17-para-staking-vault-adversarial-review.md`](correction_2026-09-17-para-staking-vault-adversarial-review.md): adversarial review of para StakingVault (2026-09-17)
- [`correction_2026-09-17-rollup-l1-testnet-oracle-sync.md`](correction_2026-09-17-rollup-l1-testnet-oracle-sync.md): testnet oracle still served the pre-revision L1 rollup authority score (60, not 57)
- [`correction_2026-09-17-solend-governance-adversarial-review.md`](correction_2026-09-17-solend-governance-adversarial-review.md): adversarial review of Solend DAO governance (2026-09-17)
- [`correction_2026-09-17-tempo-field-name-swap.md`](correction_2026-09-17-tempo-field-name-swap.md): Tempo's scorer used the opposite target/label field convention
- [`correction_2026-09-17-uniswap-testnet-oracle-sync.md`](correction_2026-09-17-uniswap-testnet-oracle-sync.md): testnet oracle was still serving the pre-correction Uniswap score
- [`correction_2026-09-18-ventuals-vhype-staking-adversarial-review.md`](correction_2026-09-18-ventuals-vhype-staking-adversarial-review.md): adversarial review of Ventuals vHYPE staking (2026-09-18)
- [`correction_2026-09-20-arbitrum-oracle-scores-csv-stale-gmx.md`](correction_2026-09-20-arbitrum-oracle-scores-csv-stale-gmx.md): Correction (2026-09-20) -- the Arbitrum score record published for 2026-09-20 was stale for index 0
- [`correction_2026-09-21-chainlink-layerzero-multisig-formula.md`](correction_2026-09-21-chainlink-layerzero-multisig-formula.md): Chainlink and LayerZero on Robinhood Chain used a leftover multisig formula (2026-09-21)

## Backtests (3)

The formula applied to the configuration behind a documented incident.

- [`backtest_2026-09-17-drift-protocol-security-council-compromise.md`](backtest_2026-09-17-drift-protocol-security-council-compromise.md): Retroactive backtest: Drift Protocol's $285M Security Council compromise (2026-04-01)
- [`backtest_2026-09-17-solend-governance-emergency-powers.md`](backtest_2026-09-17-solend-governance-emergency-powers.md): Retroactive backtest: Solend DAO "emergency powers" governance incident (2022-06-19/20)
- [`backtest_2026-09-17-wasabi-protocol.md`](backtest_2026-09-17-wasabi-protocol.md): Retroactive backtest: Wasabi Protocol ($5.9M, 2026-04-30)

## Rotation audits (13)

A target re-derived from scratch by a separate pass told to refute the first.

13 files, `rotation_audit_2026-09-18-robinhood-chain-index5.md` to `rotation_audit_2026-09-21-robinhood-chain-index17.md`.

## Scoring batches (13)

The batches in which targets were added, with the sources of each.

13 files, `scored_targets_2026-09-15-batch2.md` to `scored_targets_2026-09-18-batch12.md`.

## Audits (2)

Checks of the project's own tooling.

- [`audit_abi_returndata_2026-09-21.md`](audit_abi_returndata_2026-09-21.md): ABI return-data audit, all ecosystems, 2026-09-21
- [`audit_oracle_key_collisions_2026-09-20.md`](audit_oracle_key_collisions_2026-09-20.md): Oracle key collision audit, all ecosystems, 2026-09-20

## Research (1)

- [`research_2026-09-21-authority-incidents-evidence-table.md`](research_2026-09-21-authority-incidents-evidence-table.md): Authority-related incidents 2024 to September 2026: evidence table and what it can and cannot calibrate

## Coverage (1)

- [`coverage_2026-09-21-tvl-by-ecosystem.md`](coverage_2026-09-21-tvl-by-ecosystem.md): How much of each ecosystem's value do the tracked targets cover? (2026-09-21)

## Contract review (1)

- [`contract_review_2026-09-17-llamaguard-comparison.md`](contract_review_2026-09-17-llamaguard-comparison.md): Contract review against the LlamaGuard PT pattern (2026-09-17)

## Re-push records (1)

- [`repush_2026-09-20-evening-all-oracles.md`](repush_2026-09-20-evening-all-oracles.md): Re-push of all nine oracles, 2026-09-20 evening
