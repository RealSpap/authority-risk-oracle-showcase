# Hyperliquid: methodology test, 2026-09-16

Purpose: apply `chains/hyperliquid/METHODOLOGY.md` section 4 end to end to real,
significant HyperCore targets, read live, and record every place where the written
rules were not enough to produce a number. The fixes are in METHODOLOGY.md
(sections 4.6, 4.7 and the changelog in section 7).

Reads: 2026-09-16 around 20:05-20:10 UTC, official info API
`https://api.hyperliquid.xyz/info` and official HyperEVM RPC
`https://rpc.hyperliquid.xyz/evm`, read only. Live values drift; the orders of
magnitude below are what matters.

Reproduce everything below with one command:

```bash
python3 chains/hyperliquid/scripts/methodology_test.py          # full reads + scores (JSON)
python3 chains/hyperliquid/scripts/methodology_test.py scores   # scores only
```

Result on this run:

| Target | adminKey | multisig | timelock | oracleAuthority | crossExposure | composite |
|---|---|---|---|---|---|---|
| `xyz` HIP-3 dex (trade[XYZ]) | 10 | 15 | 0 | 4 | 100 | 9 |
| Hyperliquid L1 (validator set) | 15 | 65 | 0 | 40 | 100 | 26 |

Not published on chain. This is a methodology test only.

## Target 1: `xyz` HIP-3 perp dex (trade[XYZ])

### Why this target

Largest HIP-3 dex by listed assets. Live read: 120 assets, open interest of about
3.9 billion USD notional (sum of `openInterest * markPx` from `metaAndAssetCtxs` with
`dex: "xyz"`), about 1.1 billion USD `totalNetDeposit` (`perpDexStatus`). It exercises
the HyperCore-only part of the methodology: native multisig, sub-deployers, deployer
oracle push.

### Identifier and sources

| Fact | Source 1 (protocol) | Source 2 (independent) |
|---|---|---|
| Dex `xyz`, deployer `0x88806a71d74ad0a510b350545c9ae490912f0888` | `perpDexs` on the official API | trade[XYZ] official docs, [Perpetuals Architecture](https://docs.trade.xyz/architecture.md), "Deployer" row |
| `setOracle` authority `0x1234567890545d1df9ee64b35fdd16966e08acec` | `perpDexs.subDeployers["setOracle"]` | same docs page, "Oracle Updater" row |
| trade[XYZ] runs "a distributed set of relayer instances" pushing prices about every 3 s | n/a | same docs page |

Note: in `perpDexs` the dex-level `oracleUpdater` field is `null`; the address trade[XYZ]
calls "Oracle Updater" is a `setOracle` sub-deployer. Rule 4.2.3 already covers both
paths, so the authority set is the same either way.

### Raw reads

| Address | Role(s) | `userToMultiSigSigners` | HyperEVM code / nonce |
|---|---|---|---|
| `0x88806a71...0888` | deployer | 2-of-3 | `0x` / 0 |
| `0x7d16f116...6657` | sub-deployer: registerAsset, setFeeRecipient, **haltTrading**, setMarginTableIds, setOpenInterestCaps, setFundingMultipliers, setMarginModes, setDeployerFees, setFundingInterestRates, setPerpAnnotation | `null` (single key) | `0x` / 0 |
| `0xc0892b4f...059d` | same as above except setDeployerFees | `null` (single key) | `0x` / 0 |
| `0x8c419001...0ff2` | registerAsset, setMarginTableIds, setOpenInterestCaps, setFundingMultipliers, setMarginModes, setFundingInterestRates, setPerpAnnotation | `null` (single key) | not in a scored set |
| `0x12345678...acec` | sub-deployer: **setOracle** | 1-of-6 | `0x` / 0 |

Other reads: deployer `delegatorSummary.delegated` about 500.5k HYPE (the HIP-3 slashable
stake is 500k HYPE); no other HIP-3 dex shares any authority address or multisig signer
with `xyz` (10 dexes checked, root keys expanded to signers).

### Derivation, dimension by dimension

| Dimension | Rule applied | Derivation | Score |
|---|---|---|---|
| adminKeyScore | 4.1 (as corrected) + 4.6 ladder | Root-control set = deployer (2-of-3) + `haltTrading` sub-deployers (two single keys). Weakest by rule 4.2 = single key. `haltTrading` "cancels all orders and settles positions to the current mark price" ([HIP-3](https://hyperliquid.gitbook.io/hyperliquid-docs/hyperliquid-improvement-proposals-hips/hip-3-builder-deployed-perpetuals.md)) | 10 |
| multisigScore | 4.2 + 4.6 | Same weakest key, single key = (1, 1) | 15 |
| timelockScore | 4.3 | No delay on `haltTrading`, `setOracle`, `setSubDeployers` or multisig signer changes, none found | 0 |
| oracleAuthorityScore | 4.4 + 4.6 | Oracle set = deployer (2-of-3, also implied updater since `oracleUpdater` is null) + `setOracle` sub-deployer (1-of-6). Weakest = 1-of-6 | 4 |
| crossExposureScore | 4.5 | 0 other HIP-3 dexes share a root key; no HyperEVM code or nonce on any scored authority address, so no cross-layer role to bypass today | 100 |
| compositeScore | repo `_composite` | floor(0.4 x 10 + 0.3 x 15 + 0.3 x 0 + 0.5) | 9 |

L1 cap (4.5): `min(9, 26) = 9`, no effect.

### Context before qualifying

Mitigating:

- The 1-of-6 oracle key matches trade[XYZ]'s documented design of several independent
  relayer instances: 1-of-N favors liveness of price pushes, at the cost that any one
  relayer key can push alone.
- Protocol clamps on `setOracle` (official [HIP-3 deployer actions](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/hip-3-deployer-actions.md) doc comment): markPx moves at most 1% from the previous markPx per update, at least 2.5 s between updates, all prices within 10x of the start-of-day value. These bound speed, not direction: 0.99^69 is about 0.4998, so a mark price can still be halved in 69 updates, about 3 minutes.
- 500k HYPE slashable by validator stake-weighted vote, still slashable during the 7-day unstaking queue. Ex-post, and HIP-3 docs state slashed stake is burned, not paid to affected users.
- Single-key sub-deployers have no HyperEVM activity, so the HyperEVM bypass of 4.5 is not live for this dex.

Aggravating:

- The deployer is a 2-of-3 multisig, but two single keys can halt and settle any of the
  120 markets, and three single keys can change margin tables, open interest caps and
  funding parameters. The multisig only protects `setSubDeployers` and the deployer
  address itself.

Qualification: the low score describes the key structure as read, not misuse. No
irregular action was looked for or found.

## Target 2: Hyperliquid L1 (HyperCore validator set)

### Why this target

It is the authority behind every HyperCore market and the cap for every other
HyperCore target (4.5). Live read: 234 main-dex perps, about 10.3 billion USD open
interest (sum of `openInterest * oraclePx`).

### Identifier and sources

Target key (4.7): `0xeA394CD63CA3a5C8A130Bb2b955cC71C22E5ea6C` = last 20 bytes of
`keccak256("hyperliquid:hypercore-l1")`.

| Fact | Source |
|---|---|
| Quorum > 2/3 stake; oracle = stake-weighted median of validator prices | [Staking](https://hyperliquid.gitbook.io/hyperliquid-docs/hypercore/staking.md), [Oracle](https://hyperliquid.gitbook.io/hyperliquid-docs/hypercore/oracle.md) |
| Active set and stake | `validatorSummaries`, official API. Single operator source, see gaps |
| "Foundation validators" exist and the Foundation runs a delegation program | [Delegation program](https://hyperliquid.gitbook.io/hyperliquid-docs/validators/delegation-program.md) |

### Raw reads

| Read | Validators | Entities (Foundation-labeled merged) |
|---|---|---|
| Active | 27 | 23 |
| Foundation-labeled share of active stake | 5 validators | about 48.0% |
| Count to exceed 1/3 | 3 (36.7%) | 1 (48.0%) |
| Count to exceed 1/2 | 5 (51.6%) | 2 (55.0%) |
| Count to exceed 2/3 | 8 (68.3%) | 4 (66.71%, only 0.04 points above 2/3) |

### Derivation, dimension by dimension

| Dimension | Rule applied | Derivation | Score |
|---|---|---|---|
| adminKeyScore | 4.1 | Signed binary auto-pulled by `hl-visor`, no public `hl-node` source | 15 |
| multisigScore | 4.2 (as corrected) + 4.6 | k_f = 4 entities, k_l = 1 entity: min(100, 15 x 4 + 5 x 1) | 65 |
| timelockScore | 4.3 | No documented upgrade notice | 0 |
| oracleAuthorityScore | 4.4 (as corrected) + 4.6 | m = 2 entities over 1/2: 20 x 2 | 40 |
| crossExposureScore | 4.5 | The L1 is the shared root itself; exposure is expressed as the cap on other targets | 100 |
| compositeScore | repo `_composite` | floor(0.4 x 15 + 0.3 x 65 + 0.3 x 0 + 0.5) | 26 |

Sensitivity: the entity count for 2/3 sits 0.04 points above the threshold. A small
stake shift makes it 5 entities (multisigScore 80, composite 30). Counted per validator
without merging, multisigScore would be 100 and composite 36: the merge rule moves this
score by 10 points, which is why it had to be written down.

### Context before qualifying

Mitigating: the Foundation-labeled set is below both a simple majority and the 2/3
quorum, so it cannot finalize or move the oracle median alone. Labels are self-set, and
merging them is the conservative direction.

Aggravating: the Foundation also delegates stake to other validators and "reserves the
right to cease delegation at any time" (delegation program page), so its influence may
exceed its own labeled share. Not scored, not measurable from `validatorSummaries`.

## Methodology gaps found

| # | Gap | Effect on this test | Fixed in METHODOLOGY.md? |
|---|---|---|---|
| G1 | No dimension had a 0-100 formula; section 4 ordered keys but produced no number | No score could be derived from the text alone | Yes, new 4.6 |
| G2 | 4.1 scored a HIP-3 dex on the deployer ladder, while 4.2.3 says sub-deployers bypass the deployer | `xyz` adminKeyScore would be 50 (deployer 2-of-3) instead of 10 (single-key `haltTrading`) | Yes, 4.1 row rewritten, changelog |
| G3 | The repo Safe formula `15 k + 5 (n - k)` rewards larger n, the approved rule 4.2 says larger n is weaker | Weakest-key selection and scoring could disagree (3-of-6 selected as weaker than 3-of-5 but scored higher) | Yes, 4.6 formula monotone with 4.2, comparability cost stated |
| G4 | L1 coefficients counted validators, not entities | multisigScore 100 vs 65 on the same data | Yes, 4.2 and 4.4, entity merge |
| G5 | "L1 caps all HyperCore targets" and crossExposure had no arithmetic | Not computable | Yes, 4.5 |
| G6 | `SetOracle` clamps (1% per update, 2.5 s, 10x start of day) not mentioned | A reader could not tell a 1-of-6 push is rate-limited | Yes, 4.4, as notes |
| G7 | No target identifier for a target without an address (L1) | Could not be keyed in the oracle | Yes, 4.7 |
| G8 | Only `setOracle` and `haltTrading` are classified; xyz has 11 delegated variants | `setMarginTableIds` / `setMarginModes` might force liquidations on open positions, not confirmed by a primary source | Partly: listed as open question in section 6, kept out of the score |
| G9 | HyperCore reads still rest on one operator's API (no self-run `--serve-info` node) | For `xyz`, the two key addresses are confirmed by trade[XYZ] docs; multisig thresholds and validator stake are not independently confirmed | No, infrastructure, still open in section 6 |
| G10 | Foundation delegated stake to third-party validators is not visible in `validatorSummaries` | L1 entity counts may overstate decentralization | No, open |
| G11 | No primary source for L1 upgrade notice practice | L1 timelockScore 0 by default | No, still open in section 6 |

Verdict: the methodology, after the G1 to G7 fixes, produced every dimension of both
targets from live reads with no manual judgment left in the arithmetic. G8 to G11 are
open questions that change context or confidence, not the ability to score.
