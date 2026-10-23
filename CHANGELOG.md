# Changelog

<!-- readers:begin -->
## Changes for readers

One entry per method version, named `YYYY.MM.N` (`data/method_versions.json`). `N` counts, within the month, the changes of `METHODOLOGY.md` or of the scoring code that move a published score. The `methodologyHash` stays the machine identifier: it is a digest of the scoring code of one oracle (`scripts/lib/methodology.py`), not a hash of the text of `METHODOLOGY.md`, and each oracle has its own. The hashes of 2026.10.2 were read from `getScore()` on each oracle on 2026-10-13 (about 15:30Z); an earlier draft of this section had read older hashes from the public pages of the Watch, which lagged the chain, and called a correct hash a divergence. The hashes of 2026.10.3 were read from `getScore()` on each EVM oracle and from the Solana accounts on 2026-10-20 (about 16:50Z). Versions before 2026.09.0 are not named: see the engineering log below.

### Known gaps, dated and not corrected

- 2026-10-13: the Watch alert on `Gmso1uvJnLbawvw7yezdfCDcPydwW2s2iqG3w6MDucLo` was labelled with another protocol's name: the address is GMX-Solana's `gmsol_store` (the scorer labels it correctly).
- 2026-10-13: a Watch alert on a queued change carries the same score whatever the instruction in the queue does (a price-feed setting and a full replacement of the core program read the same).

### 2026.10.3 (2026-10-19 and 2026-10-20, on the oracles today)

| Oracle | methodologyHash | Pushed |
|---|---|---|
| Robinhood Chain | `0x7a8280d6128fcfffdfcab3e45d617360c4caa1a521e1ecf4f002e4762b4b3606` (63 targets) | 2026-10-19 22:28Z |
| Ethereum L1 | `0x0e0dadb9b93f111850c6149be1a61b089f1e14e39d9a2acc56a7e0d4d88ef32b` (38 targets) | 2026-10-20 00:07Z |
| Arbitrum | `0x42f5ef04fd9a03dfddc9044d63bef7e44548ac53b0a3cc84940339d79638c7ae` (13 targets) | 2026-10-19 22:33Z |
| Base | `0xb55a2d7d5c9f1c87b278a0c86beeca7d03a2540019f031930109b54b653d3b74` (13 targets) | 2026-10-19 21:38Z |
| Plasma | `0xc1d1ba0a9ddfabd18ba1ec3ed1f66dce9babca05f05eaa76acd37cc1d671034c` (9 targets) | 2026-10-19 22:01Z |
| Monad | `0xf4a5c40caa27b1952c9235737d4bcc6b134faaea8d54c2db3a963aacf896a904` (9 targets) | 2026-10-19 21:42Z |
| Hyperliquid | `0xc06d60184165fe36f356e6196dac10f0adf5963726a5d1574b5ab896fbc8c365` (16 targets) | 2026-10-19 21:34Z |
| Tempo | `0xe267de1a8e2c7ace54eac7fd4376bfbd66cb87cba7b39e30d883e4cda7ab787a` (14 targets) | 2026-10-19 21:31Z |
| Solana | `0x58be578c4ad50dbee98dc0666a228ec6d0b36c7dc71bb1506393477156219fa5` (26 targets) | 2026-10-19 21:26Z |

- Pushed from commit `4d21558f789725be539996e1dc1ca9747a3b19fb`; the hashes were computed from the scoring files of that commit before the push and match the ones read on the oracles. 202 targets are tracked across the nine oracles; every score was read back from the oracles after the push and equals the value computed before it. The Ethereum L1 oracle keeps one entry under an older hash (the retired Ethena minting entry, 2026.09.0). The Tempo hash also covers a change of its log reader (it waits and retries when the public RPC says rate limited; no score is computed differently).

- Covers: five more targets on Ethereum L1 (Arbitrum bridge 60, Pendle V2 43, Aave V4 53, Fluid Liquidity 77, Base bridge 56); one rule for nested Safe seats (a Safe whose owner is another Safe is counted on the EOA keys that must really sign, only when those keys are distinct and only upward); a Safe is recognised on its code (a published Safe proxy), not only on what `getOwners()` answers; the limit that Safe owners can write the Safe's storage is now recorded as a known limit.
- The nested-seat rule for a Morpho vault curator Safe now applies on every chain (one shared module, `scripts/lib/curator_multisig.py`, in the working repository, not yet public), after a live case on 2026-10-13: the curator of the Spark USDC Vault on Base was rewritten at 13:17:05Z (block 52554039, one Safe transaction) from a 3-of-5 into a 2-of-2 whose owners are a 3-of-5 Safe and a 1-of-2 Safe, so four keys must sign; read at the first level it looked like a 2-of-2 and the vault would have fallen from 63 to 44, on the keys that really sign it scores 65.
- Moved a score on that push (read back from the oracles): a tracked adapter on Arbitrum (8 to 40: the Zodiac Delay module of its Safe, analysed on 2026-10-12, no longer blocks the Safe); a tracked vault on Ethereum (2 to 19: the vault's own 14-day timelock counts, confirmed by a second script that uses only the standard library, written by the same author and reading the same public RPC); a tracked vault on Base (63 to 65, instead of the 44 a first-level reading gives); a tracked curator vault on Robinhood Chain (multisig 30 to 60, composite 40 to 49); a tracked vault on Monad (cross exposure 100 to 80, composite unchanged); two tracked lending pools on Ethereum L1 (cross exposure 80 to 60: a new access-control contract in this push shares their root authority); two tracked contracts on Robinhood Chain (composite 32 to 29: an executor delay read as 0 now scores 0, a positive delay under one day 40, one day or more 60); a tracked lending program on Solana (multisig 87 to 83, composite 56 to 55: what the scorer read that day, the same value with the previous code). The five new Ethereum L1 targets carry their first scores. Two other changes of this version moved no score read on the oracles: a Safe at a threshold of 1 no longer adds its owner count to `multisigScore`, and an EIP-7702 delegated key counts as one key in three scorers. A timelock delay under one day no longer scores as the confirmed two-day delay, on two tracked timelock families (the live delays are two days: no published score moves).
- api/scores.json remains the raw public data, with the names it has always carried.
- Proposals refused after a second reader on 2026-10-13, so no score moves: Orvex V2 (46 proposed, 2 kept: the pair fee is uncapped), Gains Network (32 proposed, 4 kept: a 2-of-4 Safe can grant itself an allowance over the collateral). Kinetiq (4) keeps its score with a note: a bounded-power reading is under review and not applied.

### 2026.10.2 (2026-10-12 and 2026-10-13, on the oracles today)

| Oracle | methodologyHash | Pushed |
|---|---|---|
| Robinhood Chain | `0x667dc486af9557a83488110fdb18fe653ba6d3be4773420590ee53b4a052fa45` (63 targets) | 2026-10-13 03:26Z |
| Ethereum L1 | `0x46a1a85b619e7db0f81e543674e8aa0a3a1afba36b7500fe2cb256e0024db645` (33 targets) | 2026-10-13 01:45Z |
| Arbitrum | `0x51163f3cce4612011bca19a651e2c0b650d9c670559f9036a37acfadf0532f54` (13 targets) | 2026-10-13 00:54Z |
| Base | `0x0ffe08e65a4a36a26b89b8257fca91ff5c4c558f13e367f9bf457231d6848c70` (13 targets) | 2026-10-12 23:32Z |
| Plasma | `0x026c7c3b27bb926e395674381dba1df191de242b8b5a46f8fe3359fa6001ad1e` (9 targets) | 2026-10-12 23:56Z |
| Monad | `0x4988d9ca0f32092144d3ced871e2c454f9e6d071f4d1ab71c97f6970a925ed4f` (9 targets) | 2026-10-13 00:12Z |
| Hyperliquid | `0x36452ea42a84016f691a665855cc3482c3e8bb4d87155901b491b293457a4004` (16 targets) | 2026-10-12 05:46Z |
| Tempo | `0x0a3df5ccf0492a8006278d8f559a8ee72202d8b3d3b01ff5561fa9729045c276` (14 targets) | 2026-10-13 01:57Z |

- Covers: the push of 2026-10-12 / 2026-10-13 on the eight EVM oracles. Solana was not read from the chain: the registry lists a computed hash for it (the digest of the Solana scoring code at commit 06b3b21, the commit whose code reproduces the eight hashes above to the byte), to be confirmed with a read of the Solana oracle. The Robinhood oracle (`0x9BF4...7f52`) holds `0x667dc486...fa45` since 2026-10-13 03:26Z (table above); the committed `api/scores.json` still carries `0x795edc64...14c5`, the hash of the push of 2026-10-10 (file generated 2026-10-10 20:41Z), and is regenerated at the next snapshot.
- Moves a score: what each target's scorer read on that day; the detail per target is in the oracle itself.
- Ethereum L1 keeps one entry under an older hash (the retired Ethena minting entry, 2026.09.0) because the push did not rewrite it.

### 2026.10.1 (2026-10-10, replaced on eight oracles)

Hashes read on 2026-10-12 from the public pages of the Watch (the Solana one was not re-read after that):

| Oracle | methodologyHash |
|---|---|
| Robinhood Chain | `0x795edc64fdbb202de7639a1c6c1148aee4788c27ffc66050f9aa6cf0e09614c5` |
| Ethereum L1 | `0xa39b4e35813b802d9f7b0daf2e685521ca2ffae61b210674e8ea97493c54f84b` |
| Arbitrum | `0xf178bca63c9d3257a306dd7cf6a4e5b3e3817a4ae59fd289ae3486d7bbc25374` |
| Base | `0x4fad7e994ac7045d9e23e7bda2f85c5c3f210b8ac57da920ea123896f807df9d` |
| Plasma | `0x6a1d6a17504a5faeab692225b82e197898a47dbd96137e4c1a3cc17cf977e754` |
| Monad | `0xc4646c69178e9032868eadce229305ce026b8a28cae49546218c82834f7e28a7` |
| Hyperliquid | `0xf39ff2bfb9ca0b609b00f3f3058fc2ef40d3d8abbcb08228bfc8091235a5fbd4` |
| Tempo | `0x134e33c2b59f03981c62fbafe19942062b82862cc2f79fa62d23294eeb97d268` |
| Solana | `0x79b73242ae50124e8d706211eb7f67dd3a891d87b9192fe3973da17fdc63b49d` |

- Covers: 197 targets across nine oracles; five sub-scores (admin key, multisig, timelock, oracle authority, cross exposure) and a composite = floor(0.4a + 0.3m + 0.3t + 0.5).
- Moves a score: the oracle-authority score follows the price paths one hop upstream, and a target that shares a root signer set with another loses cross-exposure points.

### 2026.09.0 (retroactive, entries last written 2026-09-23 and 2026-09-24)

- Covers: the entries older than the pushes above: one Ethena minting entry on Ethereum L1 (`0xac9104d9774a01ae1bbb28a4725f597425697a1d7e68b1d8cf915439eec6b167`, written 2026-09-23, retired, still on the oracle) and three HIP-3 dex entries on Hyperliquid (`0xfbf38ff91abf710728e2df3d5370bf18eeb2a9085168612fa03955b13cc958ad`, written 2026-09-24, rewritten by the push of 2026-10-12).
- Moves a score: nothing today; they are old values under older code. Scores written under different hashes are not strictly comparable.

### Site

- The Compare page lists the neighbouring tools one row each, what each reads and does not read, according to its own pages, read on 2026-10-12; no ranking. Built 2026-10-12, live since 2026-10-12. The two neighbours found after that reading are not on it yet (Upcoming 4).
- The Backtest page reads 55 incidents from public postmortems against the six requirements the oracle publishes for every contract, and says which it could not apply: for the 7 that are about who controls a contract, the requirements flagged 2, missed 2 and could not be applied to 3 (figures read on the live page on 2026-10-14). Built 2026-10-12, live since 2026-10-12. It is not a replay by the scorer (Upcoming 8).
- Each contract page shows an "Exit window" line, the time a user has to leave after a harmful change is queued, derived from the timelock sub-score (in the page code since 2026-10-11).

### Repository

- `examples/gated-vault/` and `src/AuthorityGatedVault.sol` (in the working repository, not yet public): an example consumer, a vault that refuses a deposit when the oracle's score for its target is too low, stale, too old, never set or unreadable, and never gates a withdrawal. Replay the refusals on a local fork with `bash examples/gated-vault/replay.sh fork`. It is an example, not deployed and not audited; it had one independent review.
- The Watch writes its generated files to the `watch-data` branch; `main` keeps the code, the documents and a "moved" notice at each old address under `watch/`.
- The Watch checks the age of the last commit on main and warns at 45, 52 and 58 days: GitHub disables scheduled workflows after 60 days without repository activity.
- authority-risk-mcp 0.1.0 is on PyPI, npm and the official MCP registry (io.github.RealSpap/authority-risk-mcp).

### Research

- Aave levels 0-5 per privileged role: 25 of the 67 Aave V3 Core reserves plus BTC.b and USDe, read at block 26,184,127, with the calls to rerun: `research/aave-levels-2026-10-13/`.

## Upcoming

No dates are promised. "next" is the immediate queue, "planned" is decided and written down, "explored" is measured or verified but not yet decided. Everything here is read-only research until a build is announced in "Changes for readers". Read against the repository and the live site on 2026-10-14: what is built has moved to "Changes for readers", and a line marked "(partly built)" says what exists today and what is still missing.

### 2026.10.4 (in preparation, not on the oracles)

- Nothing is decided yet and no scoring code is written for this version; the next push that carries a change moving a published score will be named here first.

### Next

1. Readable method versions in the published files (partly built): the registry `data/method_versions.json` and the named versions above exist; the `methodVersion` and `methodVersionDate` fields appear in `api/scores.json` at the next generation of that file, and the Watch's `methodology.json` does not carry them yet. (see note)
2. Watch fixes recorded as known gaps on 2026-10-13 (see "Known gaps"): a wrong label on a Solana target, and the same score for a parameter change and a full code replacement in a queue.
3. Aave levels 0-5 for the Core reserves not yet read (the Status line of `research/aave-levels-2026-10-13/` says which are read).
4. The Compare page, updated with the two neighbouring tools found after it was read on 2026-10-12 (Keyholder for Solana programs, OneKeyAway for EVM contracts), criterion by criterion, with sources and "not read" where we do not know. (see note)
5. A trust page per protocol (partly built): a prototype for one protocol (Aave V3) exists in the working repository, not yet public and is not on the live site; the page shows the weakest score among the protocol's contracts, the table of its contracts, the method in plain words and how to contest a reading. Extending it to the tracked protocols is decided. (see note)

### Planned: what a depositor asked for

6. A permission diff per governance proposal, and an authority column under it: for a proposal, the matrix "privileged function by holder, before and after", with the Safe threshold and the cumulated delay, each call simulated from each holder with a negative witness, shown as PASS/WARN/INFO (first targets: Compound, Aave, Sky). We compared with the Uniswap governance-seatbelt fork (its permission-diff check), read on 2026-10-13: it reads events and state diffs, and does not build this matrix across several DAOs with the multisig threshold, the delay and the simulated executor.
7. The shared-signer contagion map on the front page: which other protocols a given key can move. The shared-control sub-score exists per contract; the map does not.
8. A published backtest by the scorer (partly built): a backtest page is live (see "Changes for readers"); what is planned is the replay by the scorer of real incidents, stating which rules existed before each incident and whether they would have warned. (see note)
9. A claims registry: a team states its control configuration, the Watch re-checks it every run, a broken statement is published the same day.
10. Per-protocol, per-event alerts (queued timelock, rotated signer, granted role, executed freeze, changed implementation) on Telegram and Discord, driven by the 6-hour Watch, with a waiting list first (preparation files exist in the working repository, not yet public; the page is not live). The Watch itself stays free. (see note)
11. An on-chain guard (Zodiac Roles ScoreCondition) on a testnet, refusing a deposit when the score is below a policy or stale, with a real refusal shown (partly built). (see note)
12. "My money": paste an address, see your positions on the tracked contracts and the three worst scores, read-only, no wallet connection (cheapest path measured: a static page over the Zerion positions API). (see note)
13. The tokens you hold: can this stablecoin be frozen, by whom, how fast (44 stablecoin entries where every power sits behind one key are already extracted).
14. Powers actually exercised: a per-contract history of upgrades, pauses, freezes, admin mints and role changes, read from logs, with a registry of non-standard upgrade paths (Lighter on Robinhood Chain emits no EIP-1967 event).
15. A DAO proposal ready to paste from the score sliders.
16. Insurers and lenders as readers (Nexus Mutual, Chainproof, Munich Re DeFi Protect): a subscription file per protocol with replayable calls.
17. A warning at signing time (partly built): a MetaMask Snap with scores embedded in the package, later a Safe guard or an ERC-7579 hook "refuse if score below threshold". (see note)

### Planned: per-application cross-chain and real-world assets

18. LayerZero and Hyperlane configuration per application (DVN set, owner, delegate, ISM), starting with the applications that hold the most value. A delegate check exists (`scripts/lib/layerzero_delegate_risk.py`) and is not wired into the score.
19. Tokenized funds and bonds (BUIDL, USDY, OUSG, Superstate, Centrifuge, Ondo GM): freeze, forced redemption, allowlist and upgrade powers per issuer, with Aave Horizon levels.
20. Tokenized stocks on Solana (xStocks, Ondo GM): freeze authority and permanent delegate.
21. Change-of-role and upgrade alerts on RWA tokens accepted as collateral, for curators and risk providers.

### Planned: tools around the oracle

22. A Solidity package (interface, mock, consumer) on npm and Soldeer (partly built). (see note)
23. CSV and OpenAPI exports, plus a public Dune feed, next to the JSON data contract v1 that is already served (partly built, see "API" on the site).
24. The AgentKit action and the LangChain tools published as packages and listed in their registries (partly built). (see note)
25. A Telegram bot: /score address, /watch address.
26. Signed receipts per answer, caps, and scores as EAS attestations (Base Sepolia first).
27. A simple fixed-threshold grid next to the score, in the style of the L2BEAT rosette. (see note)
28. A feed adapter for the defi-dna aggregator, and a dataset deposit (shared-signer set and incident cases) with a DOI.
29. A check "threshold + delay + simulated executor" contributed next to check-permission-diff.ts in the Uniswap governance-seatbelt fork.

### Planned: method and standards

30. Import of L2BEAT discovered.json as an external reader, closing the rollup gap.
31. Exit window = update delay minus withdrawal delay, with L2BEAT thresholds (below 7 days bad, below 30 days warning) and the DeFiScan Security Council criterion (partly built). (see note)
32. The "ultimate permission" model (chains of act calls with cumulative delays, a 1-of-N Safe counts as each signer acting alone), rewritten in Python.
33. Receipt fields: JCS canonical JSON with a versioned prefix, per-fact coverage checked/partial/not_checked/unavailable, a refUID to the previous attestation.
34. A batch canary: if a fifth of the proxies turn "non upgradeable" in one run, the node is lying and the batch is refused.
35. A class for EIP-7702 delegated accounts: a delegated EOA is still one key (partly built). (see note)
36. A date for the last change of threshold, timelock or config authority on every multisig (the Drift lesson: 2-of-5 and no timelock set five days before the loss).
37. Solana depth: Realms parameters (hold-up, veto, council vs community) and authority recursion (transfer hook and price oracle programs behind a target), and a program owned by a loader other than the upgradeable one read as "unresolved", not "renounced".
38. Sui and Aptos readings if those chains enter the oracle: UpgradeCap state and policy, upgrade_policy and upgrade_number, publisher key type.
39. An on-chain verifiable Watch: a daily commitment of the Watch state (already anchored on Zcash for scores; extended to every run).

### Planned: audit and mainnet

40. External audit, then mainnet, if people find the oracle useful. The oracle stays on testnets until then. No dates are promised.

### Explored, not decided

41. A verifier and an extension profile for ERC-8241 (Protocol Control Disclosure): chainId, contract, selector, holder, threshold, delay, signature.
42. A verified compliance grid per page: Trail of Bits levels 1-4, the two EthTrust v3 requirements, SEAL thresholds; level 4 verified on chain as a "certificate of absence" of admin power.
43. A state-mate YAML and a moesi manifest per contract, generated from the readings.
44. A Slither plugin "authority" with RPC reads (owner or proxy admin as EOA or 7702, roles without delay, Aragon ANY_ADDR), SARIF output.
45. A "control" evidence file in the sense of the FATF 2026 guidance, never presented as a legal qualification.
46. "Under watch" and "outlook" statuses on queued actions that would move a score, with a published realization rate.
47. A public counter-reading next to institutional ratings (S&P vault assessments, Credora vault ratings): the on-chain reading of the day and the gap.
48. "White paper versus chain" per MiCA issuer: ESMA register, contract address, real powers.
49. A replayable log of power changes on regulated stablecoins (the StablR case: multisig owners changed before the unbacked mint).
50. A public reference table of the technical powers of regulated stablecoins.
51. Drift of configuration for SEAL-certified protocols, once a public list of certified protocols exists.
52. A config "pin" reading on Stellar Soroban fleets (CAP-85 executable references, timelock, pin) if Stellar stays in scope.
53. A per-position authority risk for a pasted address, once a positions API without a browser-exposed key is chosen.
54. A score block on the pages where people vote (a Snapshot plugin, a governance front end), fed by the permission diff of item 6, once a third party accepts one.

### Not planned

Selling single checks over x402 (eight sellers measured on chain in 2026, a few dollars each). Email alerts as a product (a Telegram channel exists). Any claim of being first, only or alone.

### Notes on items marked "see note" (re-read on 2026-10-14 from the repository, the live site and the public registries)

- 1: a version registry (`data/method_versions.json`, scheme YYYY.MM.N) is in the repository; the `methodVersion` and `methodVersionDate` fields are written by `scripts/update_scores.py` at the next generation of `api/scores.json`, and the file in the repository today does not carry them; the Watch's `methodology.json` is produced by the Watch job and does not carry them yet.
- 4: the Compare page is live and lists the neighbouring tools it read on 2026-10-12; the two tools named here are not on it.
- 5: the prototype builder (in the working repository, not yet public) writes the page only when the owner releases it with a marker file after reading it; the pages of the live site do not include it today.
- 8: the live backtest page reads incidents from public postmortems against the six published requirements and says which it could not apply; it is not a replay by the scorer, and the "rules that existed before the incident" are not on it.
- 10: `scripts/lib/alerts.py` posts a Telegram message when a score gets worse after a push; per-protocol, per-event alerts do not exist. The waiting-list files are in the working repository, not yet public and the page is not served.
- 11: a Safe transaction guard that refuses a call to a low or stale score exists as source (in the working repository, not yet public), `src/SafeAuthorityGuardV2.sol`, tested locally and reviewed once; it is not deployed. `src/AuthorityGatedVault.sol` (in the working repository, not yet public) is an example consumer that refuses a deposit on a weak, stale or unscored target, with 32 passing tests and 1 skipped in a run on 2026-10-14; its refusals replay on a local fork, and the replay on the real testnet is not done yet. The Zodiac Roles `ScoreCondition` is a different mechanism and does not exist yet.
- 12: a "What do I hold?" panel exists on the dashboard for EVM wallets; the version in this item (a positions API, no wallet connection) is the planned one.
- 17: the MetaMask Snap exists in the working repository, not yet public (`snap/authority-insight`) and was hardened on 2026-10-13; it is not published in the Snaps directory and not installed in a real MetaMask. The Safe guard is the item 11 note.
- 22: the contract sources and tests exist (`src/`, `test/`); no package is published.
- 24: the read-only MCP server is published and is in "Changes for readers". The AgentKit action provider and the LangChain tools exist as source in `integrations/` of the public repository; neither is published as a package or listed in a registry (checked on 2026-10-14: no package of that kind on PyPI or npm under the names tried).
- 27: every page already shows six fixed requirements, each met, not met or not assessed; what is missing is the rosette-style grid.
- 31: each contract page shows an "Exit window" line derived from the timelock sub-score (live since 2026-10-11); the arithmetic with the withdrawal delay and the L2BEAT thresholds is not built.
- 35: an account classifier that knows EIP-7702 exists (`scripts/lib/account_classification.py`) and Tempo treats a delegated account as an EOA, but the review of 2026-10-13 found most scorers still test `is_eoa()`, so the same key can score differently. The class is not applied everywhere.
<!-- readers:end -->

The dated engineering log of the scoring and deployment work, kept verbatim as evidence of what was checked, when, and what was left open. It reads as a working log on purpose: each entry says what that pass verified and what it did not. For the current state read the README; for the rules, METHODOLOGY.md; for the live numbers, the dashboard.

---

## History of the README section "Why this, and why now"

Three dated asides used to live in the README's SolGov paragraph, as the Status section did for everything else.

   blind 100. **Updated 2026-09-20**: that is now the rule on every EVM
   ecosystem, not just those two chains (decision and rationale in
   `METHODOLOGY.md`; what it moved, now pushed on-chain (2026-09-20),
   in `data/finding_2026-09-20-cross-exposure-convention-and-score-adjustments.md`).

   signal list this project does not fully check yet. **Correction 2026-09-17**:
   an earlier version of this paragraph said closing that gap was "the honest bar"
   before promoting Solana out of `methodology` phase -- Solana reached
   `scoring_build` the same day (`chains/solana/scorers.py`, 2 targets, see
   `chains/solana/data/scored_targets_2026-09-17.md`) using this project's existing
   cross-chain 5-dimension model, without first matching SolGov's extended signal
   set. Recording that honestly rather than quietly dropping the earlier claim:
   the stated precondition was not met, matching SolGov's fuller benchmark on
   Solana remains a real, separate, still-open item, not a completed step.
   **Correction 2026-09-18** (this paragraph had gone stale, caught via the
   research tracker rather than silently left): `chains/solana/scorers.py`
   now covers **13 targets**, not 2 -- 8 more were added 2026-09-18 (Raydium,
   marginfi, Kamino Liquidity, Jupiter Perps, Jupiter Lend, PumpSwap, Meteora
   DAMM v2, Orca Whirlpool, see `chains/solana/data/scored_targets_2026-09-18-
   defi-config-admins.md`), plus Marinade the same day (`chains/solana/data/
   scored_targets_2026-09-18-marinade-liquid-staking.md`). Re-verified live
   2026-09-18: `len(chains/solana/scorers.py:SIMPLE_SCORERS) == 13`, every
   entry a single-target `-> dict` scorer, matching the 13 count exactly.
   The SolGov-benchmark-depth gap itself remains genuinely open regardless of
   target count -- this correction is about the number, not the underlying claim.

---

## Status

Deployed on [Robinhood Chain Testnet](https://explorer.testnet.chain.robinhood.com)
(chain ID 46630) as a first, no-cost validation pass before a mainnet deploy:

| Contract | Address |
|---|---|
| `AuthorityRiskOracle` | [`0x9BF45734D09bC7CA39238e767B2af9AAc62a7f52`](https://explorer.testnet.chain.robinhood.com/address/0x9BF45734D09bC7CA39238e767B2af9AAc62a7f52) |
| `ExampleConsumer` | [`0xE34116e259cDB1b6F3a58F528f8A5213F5d397B3`](https://explorer.testnet.chain.robinhood.com/address/0xE34116e259cDB1b6F3a58F528f8A5213F5d397B3) |

*(Redeployed in batch 7 -- the previous address `0x0e84614e12e202D3e71f0Ef5F71d322E1d9BFaAe` is
superseded, not upgraded in place, after a breaking `AuthorityScore` struct change; see below.)*

**[`dashboard/index.html`](dashboard/index.html)** reads every score directly from
the deployed oracle in your own browser via raw `eth_call` -- no backend, nothing to
trust but the RPC and the contract itself. Chain tabs read all 4 real deployed
oracles live (Robinhood Chain, Ethereum L1 Sepolia, Arbitrum Sepolia, Base
Sepolia -- see "Real multi-chain deploys" below), each finding gets a shareable
deep link, and a sourced panel ties the scoring dimensions directly to two real
2026 exploits (Drift Protocol's $285M compromised admin key, KelpDAO's $292M
1-of-1 cross-chain verifier). Search by target/finding/address and filter by risk
band (Critical/Weak/Moderate/Decent/Strong), same idea as SolGov's column
filters, applied to a page that never leaves the chain to render.

**46 real scores pushed** (testnet), every one independently re-derived via `eth_call`
rather than trusted from a UI or third-party write-up -- reaching from individual
dApps all the way up to Robinhood Chain's own L1 rollup authority, and now to the
oracle and cross-chain-messaging infrastructure those dApps themselves depend on.
**All 46 are genuinely covered by the automated re-scorer** (`scripts/lib/scorers.py`'s
`score_all()`), continuing from batch 7's fix of the 15 targets that had been pushed
once by hand and never wired into the recurring updater.

**Rotation audit (2026-09-20, run 8)** re-derived tracked target index 15
(Robinhood Token: PLTR, the 3rd of 5 tokenized-stock beacon-proxy targets)
from scratch on independent RPCs and found the published score (3, 0, 0, 100,
100, 1) exact, nothing pushed for it. What is new is how far the re-derivation
went: indexes 13 and 14 read the proxy's EIP-1967 slot and the beacon's
`DEFAULT_ADMIN_ROLE` holder only. This pass also read the beacon address as an
immutable in both the proxy and the implementation bytecode, replayed the
beacon's whole event history (274 events, 19 role changes, no
`RoleAdminChanged`), and enumerated every live role holder: 13 roles, 13 bare
EOAs, every role administered by `DEFAULT_ADMIN_ROLE`, no Safe and no timelock
anywhere. That corrects a phrasing, not a score: the admin key cannot call
`upgradeTo` / `pause` / `blockAccounts` directly (simulation reverts), it needs
one zero-delay `grantRole` to itself first, and today those roles sit on 12
other bare EOAs (the upgrader has actually executed `upgradeTo`, the blocker
has 246 `Blocked` events). Those 12 are now in the `stock_tokens` overlap
group.

The same pass added **Saffron Vaults** (fixed-yield Uniswap V3 vaults) as the
58th tracked target: factory `0xb24b143a...6904`, `Ownable2Step`, restricted
variant (only the owner creates vaults, 111 of them), owner = `feeReceiver()`
= an **EIP-7702-delegated EOA** (MetaMask `EIP7702StatelessDeleGator`, one
signing key, the second 7702 root among tracked targets after Fables
PoolRegistry's sole admin, classified by the
existing `classify_account()`). Scored 2/0/0 -> **1/100** by the same-key
convention of the Curve factory. TVL recomputed on chain from 111 vaults and 13
Uniswap V3 positions: ~$803k (DefiLlama $821k, DexScreener prices agree), but
57% of it is one launchpad token (STONKBROKER) and only ~$260k is USDG plus
tokenized stocks. The score encodes the controller only: the public source
says the owner cannot touch existing vaults' principal, but the deployed code
was not matched to it (no compiler run), so no blast-radius claim is made.
Pushed as a single-target `updateScores()`: tx
[`0x409b98f767c485c533a3fba9d1a108d7e3238440158b545229c93322d2b3149d`](https://explorer.testnet.chain.robinhood.com/tx/0x409b98f767c485c533a3fba9d1a108d7e3238440158b545229c93322d2b3149d),
testnet block 121828009, `trackedTargetsCount` 57 -> 58. Robinhood Chain
mainnet read only; no key of real value; `public_repo_visibility_change_allowed`
untouched. Documented, with the limits of the pass (self-refutation instead of
a separate refuting agent; the full event replay exists on one RPC only), in
[`data/rotation_audit_2026-09-20-robinhood-chain-index15.md`](data/rotation_audit_2026-09-20-robinhood-chain-index15.md).

**Rotation audit (2026-09-19, run 7)** re-derived tracked target index 14
(Robinhood Token: AMZN, the 2nd of 5 tokenized-stock beacon-proxy targets)
from scratch against two independent RPCs -- read the target's own EIP-1967
beacon storage slot directly (`score_stock_token()` itself never does: it goes
straight to the shared beacon for every token), confirmed it points at the
shared stock-token beacon, that `hasRole(DEFAULT_ADMIN_ROLE, ...)` still holds
for the known admin key and that key is still a bare EOA (0 bytecode, nonce 2,
identical on both RPCs). Published score (3, 0, 0, 100, 100, 1) matched
exactly, no correction needed.

The same pass added **Alandale V3** (a ve(3,3) DEX native to Robinhood Chain,
Algebra Integral v1.0-based) as the 57th tracked target. Its factory's
`owner()`, its ProxyAdmin's `owner()` and its sole `DEFAULT_ADMIN_ROLE` holder
are all one plain 3-of-5 Gnosis Safe (v1.4.1, no module, guard slot zero, 5
bare-EOA owners with real nonces), no timelock anywhere in the chain -- scored
65/55/0 -> **43/100** via the existing `_safe_rooted_entry()` convention, no
overlap with any tracked signer (`crossExposureScore` 100, re-derived live).
Two things worth knowing: the deployed factory is Algebra v1.0 plus 10 custom
selectors, source unreachable, so the score rests only on the ownership/upgrade
chain and says so; and DefiLlama's ~$1.99M TVL for it is inflated by one wrong
price -- coins.llama.fi lists the USAR token at $757.70 while the on-chain
Uniswap pool and DexScreener both say ~$15.5 -- so the honest figure, from a
pinned-block on-chain recomputation that DexScreener independently matches to
0.07%, is ~$1.14M. Leads examined and set aside with evidence rather than
added: Lighter Robinhood Perps ($101M) is the already-tracked zkLighter escrow
(balances match on 17 tokens), up v2 is governed end to end by the same Safe as
the already-tracked up v3, Ramses DLMM / Legacy V2 resolve to the already-tracked
AccessHub; GIGA V3 and StonkBrokers left open (owner roles / locker source not
verifiable); UNCX V4 still open -- the real explorer host is
`robinhoodchain.blockscout.com` (earlier guesses were wrong hostnames) but it
sits behind a Cloudflare challenge, not bypassed. Pushed as a single-target
`updateScores()`: tx
[`0x2aad6395bf90681108a03eb80928461a806bc19044939c59146591a71755c813`](https://explorer.testnet.chain.robinhood.com/tx/0x2aad6395bf90681108a03eb80928461a806bc19044939c59146591a71755c813),
testnet block 121750260, `trackedTargetsCount` 56 -> 57. New scorer
`score_alandale_v3_factory()` + signer-overlap group `alandale_v3` + 3 new unit
tests -- suite at 788 tests OK after the final rebase; `update_scores.py --dry-run --skip-slow` scored
45 of the 57 targets through `score_all()` with 0 divergences against the
published on-chain scores (the 12 omitted are the 4 documented slow scorers'
targets, by design; `validate_all_scorers.py --ecosystem robinhood-chain` ran
in full this time thanks to upstream's new 3600s default timeout: 57 targets, 0
problems, PASS -- a schema check, not a factual re-derivation). Robinhood Chain
mainnet read only,
never written; no key of real value used, generated, or requested;
`public_repo_visibility_change_allowed` untouched (stays false). Documented in
[`data/rotation_audit_2026-09-19-robinhood-chain-index14.md`](data/rotation_audit_2026-09-19-robinhood-chain-index14.md).

**Rotation audit (2026-09-19, run 6)** re-derived tracked target index 13
(Robinhood Token: TSLA, one of 5 tokenized-stock beacon-proxy targets) from
scratch against two independent RPCs -- confirmed live, before trusting the
hardcoded target list, that this address really is a beacon proxy pointing
at the shared stock-token beacon (its own EIP-1967 beacon storage slot read
directly, not assumed), then re-confirmed the beacon's
`hasRole(DEFAULT_ADMIN_ROLE, ...)` still holds for the known admin key and
that key is still a bare EOA (0 bytecode, nonce 2, identical on both RPCs).
Published score (3, 0, 0, 100, 100, 1) matched exactly, no correction
needed. `crossExposureScore` re-derived live via `compute_cross_exposure()`
on both RPCs, unchanged.

The same pass resumed the **`up v3`** lead left open across rotation-audit
indices 8, 9, and 12 (DefiLlama's `projects/up-v3/index.js` genuinely does
not exist -- every prior pass grepping for it came up empty). Resolved this
time by looking in the right place: DefiLlama tracks this native
Robinhood-Chain-only "(3,3)" CLMM exchange's TVL (~$8.5M) through the
SHARED `registries/uniswapV3.js` factory-log-replay registry instead of a
per-protocol adapter file, whose own entry names the factory address
directly. Confirmed a genuine Uniswap-V3-fork factory (matching
`PoolCreated` event topic) before trusting that; `owner()` resolves live on
2 independent RPCs to a real, independent 2-of-4 Gnosis Safe (no module,
guard slot zero) -- grepped against every existing tracked signer group
first and confirmed NOT a duplicate of the other Uniswap-family targets'
shared L1 alias root. Scored 50/40/0 -> **32/100** via this project's
existing threshold-aware `_safe_rooted_entry()` convention (same helper
already used for PancakeSwap V3/SushiSwap V3/Symbiosis/STRATO). `UNCX V4`
(`unicrypt-v4`, open since index 10) was re-checked this pass too --
UNCX's official GitHub org (`github.com/uncx-network`) still only publishes
V2/V3 lockers, vesting, and Solana lockers, no `v4` repo; a broader GitHub
search and direct Sourcify/Blockscout lookups on the deployed address also
came up empty -- left open, still not guessed at. Pushed `up v3` Factory as
a single-target `updateScores()`: tx
[`0xfaa53839b3f8a0383e71a310c987f2c759d135ae46b740d57e3c9b01f65e3452`](https://explorer.testnet.chain.robinhood.com/tx/0xfaa53839b3f8a0383e71a310c987f2c759d135ae46b740d57e3c9b01f65e3452),
testnet block 121726193, `trackedTargetsCount` 55 -> 56. New scorer
`score_up_v3_factory()` + signer-overlap group `up_v3` + 2 new unit tests --
suite at 531 tests OK (`python3 scripts/validate_all_scorers.py
--ecosystem robinhood-chain` not run this pass either, same documented
"2 lents" timeout gap noted at every prior robinhood-chain rotation-audit
pass -- not substituted by a fabricated result, live 2-RPC re-derivation
plus the unit-test suite carry this pass instead). Robinhood Chain mainnet
read only, never written; no key of real value used, generated, or
requested; `public_repo_visibility_change_allowed` untouched (stays
false). Documented in
[`data/rotation_audit_2026-09-19-robinhood-chain-index13.md`](data/rotation_audit_2026-09-19-robinhood-chain-index13.md).

*(Also noting, not silently fixing: this changelog has no entry for
rotation-audit index 12 (T3tris Finance WBTC vault), even though it was
pushed and committed -- see `rotation_state.json`'s own
`note_2026-09-19_index12` and
`data/rotation_audit_2026-09-19-robinhood-chain-index12.md` for that work.
Same discipline as the "46/65/72" counter staleness already flagged in
this file rather than half-corrected: not backfilled here without the time
to re-verify that pass's own numbers first-hand.)*

**Rotation audit (2026-09-19, run 4)** re-derived tracked target index 11
(Arcus pBTC 1x, part of the already-tracked pToken family) from scratch
against two independent RPCs -- published `adminKeyScore`/`multisigScore`/
`timelockScore`/`compositeScore` (65, 55, 0, 43) matched exactly, but
`crossExposureScore` independently re-derived to **80**, not the published
100 (see below). The same pass's new-target search found **Arcus Perps
BridgeVault** (DefiLlama slug `arcus-perps`, ~$24.13M chain-specific TVL),
a genuinely different Arcus product from the pToken family -- its
`DEFAULT_ADMIN_ROLE` resolves to THREE contracts at once: a real 24h
`TimelockController`, a `ValidatorConsensus` (2-of-3 bare-EOA quorum) and
a `CheckpointManager`, where the validator quorum can reach the full admin
surface via `executeGovernanceAction()` with **zero minimum delay** -- so
the real 24h timelock does not cover the action that actually matters,
scored `timelockScore=0` per this project's own "delay that doesn't gate
the action that matters" convention rather than credited for merely
existing. Scored `adminKeyScore=50`/`multisigScore=35`/`timelockScore=0`
-> **compositeScore=31**. One of `ValidatorConsensus`'s admin-holding EOAs
is already a signer in the tracked `arcus` pToken group -- a real,
live-confirmed cross-protocol overlap, dropping ALL 4 Arcus targets'
`crossExposureScore` from 100 to 80 (`compositeScore` unaffected, that
field isn't a `_composite()` input). Pushed as a single 4-target
`updateScores()`: tx
[`0x0e6d41855d42012f7f8c16db7eb1d90df163b047df2dc5723efc604c134df464`](https://explorer.testnet.chain.robinhood.com/tx/0x0e6d41855d42012f7f8c16db7eb1d90df163b047df2dc5723efc604c134df464),
testnet block 121699881, `trackedTargetsCount` 53 -> 54. New scorer
`score_arcus_perps_bridgevault()` + `arcus_perps_bridgevault`
signer-overlap group. See
`data/rotation_audit_2026-09-19-robinhood-chain-index11.md`.

**Rotation audit (2026-09-19, run 3)** re-derived tracked target index 10
(Arcus pToken factory + beacon) from scratch against two independent RPCs --
published score (65, 55, 0, 100, 100, 43) matched exactly (the beacon's
`owner()` **and** the factory's own AccessControl `DEFAULT_ADMIN_ROLE`
independently re-confirmed as the same real 2-of-3 Safe, no module, no
guard; both live pTokens re-confirmed pointing at the same beacon via their
own EIP-1967 slot), no correction needed. The same pass finally resolved
**UNCX Network's V3 Locker**, a lead re-investigated at index 9 and left
open twice: found UNCX's real, official GitHub org
(`github.com/uncx-network`, confirmed via its own profile linking
`uncx.network`) and its `liquidity-locker-univ3-contracts` source, then
cross-checked that source against the deployed bytecode (an initial
PUSH4-only scan matched 25 of 26 known function/error selectors; the miss,
`withdraw()`, was a scan artifact -- its selector is pushed as PUSH3 -- and a
later re-check found 47 of 47 present). The source shows `withdraw()`/`migrate()`
gate on the individual lock's own owner, not the contract's `onlyOwner` --
the 2-of-3 Safe cannot pull a user's locked LP position directly; its real
powers are fee configuration, allowed position managers, and
`setMigrator`/`setMigrateInContract` (an indirect rug vector on a lock
owner's own future `migrate()` call, not direct seizure). Scored 50/35/0 ->
**31/100** using the threshold-aware formula introduced for Morpho Blue
Singleton (50 for a 2-of-3 Safe, not the older flat 65 branch). UNCX's
*second* locker (`unicrypt-v4`) shares the same Safe but is a materially
different, larger contract (120 candidate selectors vs. 62, only 9/26
matched) -- its own source was not found this pass, left open rather than
guessed at. Pushed UNCX V3 Locker as a single-target `updateScores()`: tx
[`0x945dcbd3c139d819785c529766a9e2d5e8c352aa75c0cdb5d23a286fec88d10c`](https://explorer.testnet.chain.robinhood.com/tx/0x945dcbd3c139d819785c529766a9e2d5e8c352aa75c0cdb5d23a286fec88d10c),
testnet block 121470191, `trackedTargetsCount` 52 -> 53. New scorer
`score_uncx_v3_locker()` + `uncx_v3_locker` signer-overlap group + 3 new
unit tests (467 total, full suite green). See
`data/rotation_audit_2026-09-19-robinhood-chain-index10.md`.

**Rotation audit (2026-09-19, run 2)** re-derived tracked target index 9
(Uniswap V2 Factory feeToSetter) from scratch against two independent RPCs --
published score (80, 100, 75, 100, 100, 85) matched exactly (the L1-alias
formula re-derived independently, and the real L1 Timelock/GovernorBravo
re-confirmed live on 2 DIFFERENT L1 RPCs than the scorer's own), no
correction needed. The same pass resolved **NOXA Fun Launch Locker**, a lead
found but deliberately left open at index 7: `owner()` is a bare, active EOA
(nonce 45), and this time **every** PUSH4 selector in the locker's full
4,823-byte bytecode (36 total) was extracted and identified against
`4byte.directory` -- not the earlier partial scan -- finding only a coherent
fee-management module (`setFeeCollector`/`setProtocolFeeRecipient`/
`setProtocolFeeShare`/`collectFees`) and the standard OZ `Ownable` pattern, with
**no** withdraw/unlock/migrate/decreaseLiquidity selector anywhere in the
complete set. `balanceOf(locker)` on the shared Uniswap V3 position manager
confirmed 60,142 real, live LP NFTs on both RPCs. Scored 5/0/0 -> **2/100**
(the same standalone-bare-EOA convention as Curve DEX, no scope-based
discount invented). `UNCX Network` was also re-investigated this pass (its two
lockers' `owner()` both resolve to the same real 2-of-3 Gnosis Safe, confirmed
on both RPCs) but is still **not resolved** -- no verified source was found
(Sourcify 404, no public repo, the chain's Blockscout explorer serves only a
client-rendered shell with no discoverable API), so it stays open rather than
being scored on an unknown power scope. Pushed NOXA Fun as a single-target
`updateScores()`: tx
[`0xc93fcb228114021080695da0de95dd69ea7a1dcd7462f71cbbd9bc7e20973e72`](https://explorer.testnet.chain.robinhood.com/tx/0xc93fcb228114021080695da0de95dd69ea7a1dcd7462f71cbbd9bc7e20973e72),
testnet block 121454086, `trackedTargetsCount` 51 -> 52. New scorer
`score_noxa_fun_launch_locker()` + `noxa_fun` signer-overlap group + 3 new
unit tests (464 total, full suite green). See
`data/rotation_audit_2026-09-19-robinhood-chain-index9.md`.

**Rotation audit (2026-09-19)** re-derived tracked target index 8 (Ekubo Core)
from scratch against two independent RPCs -- published score (100, 100, 100,
100, 100, 100) matched exactly (source-level re-check of `EkuboProtocol/
evm-contracts`, plus the same `owner()`/`0xdeadbeef`/real-selector differential
test independently re-run and re-decoded: `swap_6269342730()` reverts with
`InvalidSqrtRatioLimit()`, not empty data), no correction needed. The same pass
found that batch 10's new-target search had wrongly closed out **Morpho Blue**,
the shared lending singleton every Morpho vault on this chain is built on
top of (`chainTvls["Robinhood Chain"]` ~$538M, the single largest surface on
this chain) -- batch 10 asserted it was "covered" by the individual vaults
already tracked, but a vault's own owner only governs that vault's fund
allocation, not the singleton's own separate `owner()` (which can enable new
IRMs/LLTVs and set the protocol fee for every market on the chain, Longbow's
55 isolated markets included). Address `0x9D53d5E3bd5E8d4Cbfa6DB1ca238AEA02E651010`
sourced from `DefiLlama-Adapters/projects/morpho-blue/config.js`; `owner()`
resolves identically on both RPCs to a real 5-of-9 Gnosis Safe (no module, no
guard), scored 65/95/0 -> **55/100** using the same formula already
established for this exact protocol on Base
(`chains/base-ecosystem/scorers.py::score_morpho_blue`). `crossExposureScore`
re-derived live = 100 (none of the 9 signers appear in any other tracked
group; re-checked that no *other* tracked target's score moved as a side
effect). Pushed as a single-target `updateScores()` (same rationale as index
7's Meridian Perps push -- avoids a 50min+ full run for one target): tx
[`0x3d59ce9ef8582dd226f5d12bb1a7c34cca250846c7b1dbc4b333c07e4b4d920e`](https://explorer.testnet.chain.robinhood.com/tx/0x3d59ce9ef8582dd226f5d12bb1a7c34cca250846c7b1dbc4b333c07e4b4d920e),
testnet block 121428547, `trackedTargetsCount` 50 -> 51. New scorer
`score_morpho_blue_singleton()` + `morpho_blue` signer-overlap group + 4 new
unit tests (461 total, full suite green).
`python3 scripts/validate_all_scorers.py --ecosystem robinhood-chain` hit its
own 300s per-ecosystem timeout on this run (a pre-existing tooling gap for
this specific slow ecosystem, not something this pass introduced or a
substitute for -- see `data/rotation_audit_2026-09-19-robinhood-chain-index8.md`
for the full live-verification trail used instead). The "46 real scores"
figure above (and the "65"/"72" cross-ecosystem totals further down) predate
batches 12-13 and the index 6-8 rotation audits and are now stale by several
targets each -- flagged here rather than silently left, not recomputed in
this pass since the other 4 ecosystems' current counts were not
independently re-verified this pass.

**Correction 2026-09-19**: resolved, and the resolution is durable now, not
just a one-time recount. Every one of the 5 deployed oracles' own
`trackedTargetsCount()` was read live (not assumed from any prose above):
Robinhood Chain **52**, Ethereum L1 **9**, Arbitrum **5**, Base **5**,
Plasma **7** -- **78 real, live-tracked targets across 5 real deployed
oracles**, all 52 of Robinhood Chain's own now genuinely reflected in
[`dashboard/index.html`](dashboard/index.html) (a real gap: 14 of them had
zero card until this pass, invisible despite counting toward the aggregate
stats -- see that file's own commit history for the fix). The dashboard
itself now also refuses to silently drop a target again: any future index a
chain's own oracle reports that the hand-written narrative doesn't yet
cover renders as an honestly-labeled fallback card instead of disappearing,
so this specific staleness class shouldn't recur silently in the UI even if
this prose count does.

**Rotation audit (2026-09-18)** re-derived tracked target index 5 (Spark Savings
USDG) from scratch against two independent RPCs -- published score (50, 30, 10,
100, 100, 32) matched exactly, no correction needed. The same maintenance pass
added **PancakeSwap AMM (V2) Factory** (~$1.9B TVL across all chains DefiLlama
attributes to the protocol; feeToSetter is a bare, actively-used EOA -- scores
2/100, same shape as Curve DEX) and, as a direct consequence of wiring it in,
found that its feeToSetter is one of the 3-of-6 signers on the Safe governing
the already-tracked **PancakeSwap V3 Factory** -- a real cross-protocol signer
overlap the mechanical `crossExposureScore` check could only catch once both
were tracked together. V3's own `compositeScore` (44) is unchanged; its
`crossExposureScore` was corrected from a stale 100 to 80. See
`data/rotation_audit_2026-09-18-robinhood-chain-index5.md` and
`data/scored_targets_2026-09-18-batch12.md`.

**Batch 10** added 2 new targets scouted from DefiLlama's live Robinhood Chain
protocol list (both previously flagged, unresolved leads): Fables PoolRegistry
(root authority is a single EIP-7702-delegated EOA, not a multisig) and a
representative Beefy vault (owner is a real 3-of-6-Safe-governed Timelock, split
across a 0-delay vault layer and a real 6h-delay strategy layer). See
`data/scored_targets_2026-09-17-batch10.md`. The same maintenance pass also found
that Uniswap v4 PoolManager's testnet oracle entry was still serving the
pre-correction score from before yesterday's bridge-alias fix (`scorers.py`/
`README.md` had the right number, the on-chain push had just never happened) --
pushed the already-correct 85/100 on-chain; see
`data/correction_2026-09-17-uniswap-testnet-oracle-sync.md`.

**Batch 11** (evening run) added Snuggle's MaxFi Robinhood vault (~$6.2M TVL,
11,849 deposited Uniswap V3 positions): one bare EOA owns both the vault and its
ProxyAdmin, and the vault's 24h admin timelock only covers treasury/staking-manager
changes, so it scores 1/100. See `data/scored_targets_2026-09-17-batch11.md`. The
same run found the L1 rollup authority's on-chain testnet entries still serving 60
after this afternoon's revision to 57 and pushed the corrected score; see
`data/correction_2026-09-17-rollup-l1-testnet-oracle-sync.md`.

**Batch 9** added 4 Safe-rooted targets (PancakeSwap V3 Factory, SushiSwap V3 Factory,
Symbiosis Portal, STRATO Bridge depositRouter), each authority chain traced to its root
Safe and read identically on two independent RPCs (`rpc.mainnet.chain.robinhood.com` and
`robinhood.drpc.org`), with modules/guards confirmed empty and signers compared against
every existing `GROUPS` entry (zero overlap). It also corrected a stale table row (Morpho
NetNet Credit read 8 here while the oracle has served 22 since batch 7) and closed Curve's
second-RPC caveat. See `data/scored_targets_2026-09-16-batch9.md`.

**Batch 8** added 4 new targets found by tracing what the existing 34 actually
depend on rather than searching for more dApps: the Gnosis Safe that administers
every Chainlink price feed on this chain (including 3 already-tracked stock token
feeds), and the bespoke 5-of-7 multisig that owns LayerZero V2's messaging core
(discovered via a live `DelegateSet` replay showing 722 real OApps already
registered on it -- a surface an order of magnitude larger than everything this
oracle tracked before, only the shared infrastructure scored for now, not the 722
individual consumers). Batch 8 also fixed a real bug: `score_rollup_l1_authority`
had a hardcoded note from batch 4 claiming "zero `PROPOSER_ROLE` holders" that had
gone stale without being re-checked -- a Safe was granted that role since, and the
note kept asserting the old finding as current fact on every push. Both
`PROPOSER_ROLE` and `CANCELLER_ROLE` are now re-derived live every run (same
discipline the `EXECUTOR_ROLE` check already used), which also surfaced that
neither this Timelock nor Ramses' has any real separation between who can propose
a change and who can cancel one -- the same single address holds both roles on
each, a real (if narrower) authority gap this project hadn't been scoring for:

| Target | Score | Why |
|---|---|---|
| Robinhood tokenized stocks/ETFs (~230 tokens, 5 sampled) | **1/100** | One bare EOA holds sole `DEFAULT_ADMIN_ROLE` on the shared beacon behind every token -- can upgrade the logic *or* freeze/blocklist any holder, across the entire product line, with zero delay |
| Curve DEX (StableSwap-NG Factory + fee-receiver) | 1/100 | The exact same bare EOA is both `factory.admin()` and the fee-receiver/x-gov vault's `owner()` -- one key controls the AMM's parameters and its protocol fees. Cross-checked on a second RPC in batch 9: identical; the key has never transacted on this chain but has 287 transactions on Arbitrum, a real, actively-used key |
| Ramses CL V2 (real DEX, $6.3M TVL) | 8/100 | A real Timelock exists on-chain -- with its delay deliberately set to 0 |
| Morpho Steakhouse USDG vault | 19/100 (crossExposure: **80**) | Root owner is a bare EOA 2 hops down; the 7-day timelock never covers `setOwner`/`setCurator`. Its curator Safe's all 7 owners are also shared by the Ethena x Steakhouse vault below -- the one signer overlap found across all 21 tracked groups |
| Morpho NetNet Credit vault | 22/100 | Curator and owner collapse into the same 1-of-1 Safe -- one key, wearing a Safe wrapper. **Corrected in batch 9**: this row read 8 (the hand-derived batch-3 score) while the oracle has served 22 since batch 7 moved the vault onto the generic Morpho scorer, whose known limitation is not treating a 1-of-1 Safe as an EOA (documented in `scorers.py`) |
| STRATO Bridge depositRouter (Robinhood side) | 29/100 | The same plain 2-of-3 Safe both holds the bridged funds (custody) and is `owner()` of the UUPS router that deposits into it -- no separation between custody and upgrade. That identical Safe, same 3 owners, also exists on Ethereum and Base |
| SushiSwap V3 Factory | 31/100 | Owner is an Ownable2Step fee-manager wrapper controlled by a plain 2-of-3 Safe, no timelock; not found at the same address on any other chain checked, no public signer documentation found |
| Spark Savings USDG (~$16.8M TVL, corrected 2026-09-17 -- was ~$37.4M, re-verified live via `totalAssets()`) | 32/100 | **Revised from 22 (batch3)**: the admin-role holder's own controller is now traced -- a self-administering L2 executor, gated by an L1-authenticated receiver resolving to Sky/MakerDAO's own verified "SubProxy" contract on Ethereum mainnet. A real, identifiable governance chain scores *better* than the earlier unresolved-contract placeholder, even though the local delay is confirmably **0** |
| Longbow Core / Frontier / ETH vaults | 33/100 | Owner and curator are two separately-deployed Safes with the identical 3 signers and 2-of-3 threshold -- no real separation of duties |
| LayerZero V2 messaging core (EndpointV2/SendUln302/ReceiveUln302) | 48/100 (34 until 2026-09-21, see the correction below) | A bespoke, non-Gnosis-Safe 5-of-7 multisig owns all three -- 722 real OApps already registered against this Endpoint (live `DelegateSet` replay from genesis, re-counted 2026-09-17 -- organic growth from the 709 first recorded, not a correction), only the shared infrastructure scored so far |
| Chainlink Price Feed Admin (Robinhood Chain) | 52/100 (36 until 2026-09-21, see the correction below) | A single 4-of-9 Safe is `owner()` on every sampled Chainlink feed on this chain, including 3 already-tracked stock-token feeds and the native ETH/USD and USDG/USD feeds -- every protocol that reads a Chainlink price here, tracked or not, inherits this Safe's authority |
| Morpho Purinta USDG vault | 37/100 | Real, distinct 3-of-5 Safes for curator and owner -- the best-separated Morpho vault found |
| Pendle V2 (ProxyAdmin + devProxyAdmin + MarketFactoryV6) | 42/100 | Both ProxyAdmins are real, distinct Safes (3-of-5 and 3-of-6) -- and `MarketFactoryV6.owner()` is Pendle's governance proxy, whose `DEFAULT_ADMIN_ROLE` is held by the same 3-of-5 Safe (traced in rotation audit batch 13, re-read by `hasRole` on 2026-09-20), and no timelock gates any of the three |
| Symbiosis Portal | 43/100 | One 3-of-5 Safe is both the ProxyAdmin owner (upgrades) and `Portal.owner()` (pause/business logic) of the contract holding cross-chain locked assets, no timelock |
| Arcus pToken factory + pBTC + pBTC3x | 43/100 | Real 2-of-3 Safe, but it's a single point of control over every pToken via a beacon, with zero timelock |
| PancakeSwap V3 Factory | 44/100 (crossExposure: **80**, corrected 2026-09-18 from a stale 100) | Owner is a UUPS wrapper whose owner is a plain 3-of-6 Safe -- PancakeSwap's own ops Safe, same address as its 3-of-7 on Ethereum/Arbitrum/Base/BSC (one owner fewer here); controls both the factory and upgrades of the wrapper, no timelock. One of its 6 signers is also the V2 Factory's `feeToSetter` below -- the two "separate" PancakeSwap deployments share a real key |
| Morpho Ethena x Steakhouse USDG vault (~$23.6M TVL) | 46/100 (crossExposure: **80**) | Best-governed vault found on this chain (5-of-10 Safe), still capped by the same zero-delay authority gap; shares its curator Safe with Steakhouse above |
| Lighter Escrow proxy | 54/100 | Real 3-of-5 Safe + real 21-day delay, undercut by a single bare-EOA override that can zero the delay on demand |
| Robinhood Chain's own L1 rollup authority | 57/100 | A real, publicly-named 7-of-8 Security Council Safe (Robinhood, BitGo, Chainlink Labs, Fireblocks, Offchain Labs, Paxos, Talos) plus a real 7-day Timelock that -- corrected in batch 8 -- does have a live `PROPOSER_ROLE` holder now, but that holder is the identical address also holding `CANCELLER_ROLE`: real delay, zero separation between proposing and vetoing. **Revised 2026-09-17** (was 60): that Proposer/Canceller Safe's own internal signers turn out to overlap 75% (6 of 8) with the Security Council Safe itself, live-verified -- the two "independent" layers are substantially the same people, not just the same address holding both roles, capping `timelockScore` further. That Timelock has also never once been used (0 `CallScheduled`/`CallExecuted` in its entire history, live-checked). Every dApp above inherits this risk underneath its own |
| Uniswap v3 Factory | 85/100 | **RESOLVED 2026-09-17** (see `data/correction_2026-09-16-uniswap-bridge-alias.md`): owner() is the legitimate Arbitrum L1→L2 bridge alias of Uniswap's real Ethereum-mainnet Governance Timelock (0x1a9C8182...BE35BC), not the vanity-ground/lookalike key previously described here -- re-scored via a dedicated "external L1 DAO governance via bridge alias" model (same convention already used for this project's Base sibling scorer), which independently re-confirms the L1 Timelock's real 172,800s / 2-day delay and GovernorBravo's real 40M-UNI quorum live on every run rather than trusting the correction alone |
| Uniswap v4 PoolManager | 85/100 | Same corrected identity and re-scoring as v3 Factory above -- see that row |
| UniswapX V3DutchOrderReactor | 85/100 | Same corrected identity and re-scoring as v3 Factory above -- a third protocol surface |
| Uniswap V2 Factory | 85/100 | Same corrected identity and re-scoring as v3 Factory above -- a fourth surface, spanning every Uniswap deployment on this chain |
| **Ekubo Core** | **100/100** | Verified ownerless by design -- source code, official docs, and an on-chain differential revert test all agree no privileged account exists at all. The only perfect score on this project |
| Fables PoolRegistry (ve(3,3) DEX, ~$21.8M TVL) | 2/100 | Governed by an OpenZeppelin AccessManager whose sole ADMIN_ROLE holder (confirmed via a full grant/revoke replay from genesis) is a single EIP-7702-delegated EOA -- real activity (470 txs), not vanity/compromised, but still single-key control with zero delay over listing/delisting pools |
| Beefy: SPY-WETH vault (representative, ~$2.57M TVL across ~14 vaults) | 50/100 | Owner and strategy-owner are two real TimelockControllers, both governed by the identical real 3-of-6 Safe; the vault layer's delay is 0, but the strategy-swap path (highest-value action) has a real 6h delay via both the strategy Timelock and the vault's own internal `approvalDelay` -- undercut by proposer/canceller being the same Safe, no independent veto |
| Snuggle: MaxFi Robinhood vault (LP manager, ~$6.2M TVL) | 1/100 | One bare EOA (759 txs, no code) is both `vault.owner()` and the ProxyAdmin owner over 11,849 deposited Uniswap V3 positions; the AdminSatellite's real 24h timelock only covers treasury/staking-manager changes, while pool/adapter approvals and upgrades stay instant |
| PancakeSwap AMM (V2) Factory (~$1.9B TVL across all chains, 156 real pairs on this one) | 2/100 (crossExposure: **80**) | `feeToSetter()` is a bare, actively-used EOA (nonce 20) that alone can redirect protocol fees with zero delay -- pairs are immutable so there is no upgrade surface, but this single key is also one of the 3-of-6 signers on PancakeSwap V3's own Safe (see that row) |

*(Purinta and Ethena x Steakhouse corrected 1-2pts from earlier revisions of this table -- the pushed sub-scores were always right, the hand-written table had drifted; caught while building the live dashboard rather than left uncorrected.)*

**`crossExposureScore`** (added batch 7) is a 5th dimension, separate from the
composite: for each target's group of real root signers (a bare EOA, or a Gnosis
Safe's individual owners), it checks whether any of those signers also control
*another* tracked target -- reusing this project's own
[`multisig-overlap`](https://github.com/RealSpap/multisig-overlap-showcase) methodology
(337 protocols, 547 confirmed Safes, corrected 2026-09-17), which this oracle had never actually applied
to itself until now. `100` = no shared signer with any other group; it drops 20
points per additional group sharing a root signer. Kept out of `compositeScore`
deliberately -- it's a property of the tracked *set*, not of any one target's own
authority setup in isolation. Computed fresh every run in
[`scripts/lib/signer_overlap.py`](scripts/lib/signer_overlap.py), never cached.
**Updated 2026-09-20**: a group whose committee is identical to a tracked
target's on another ecosystem also scores at most 80 here, through an optional
hand-set, dated `cross_ecosystem` flag on the group (`min(within-Robinhood score,
80)`, never raising a lower score). Three Robinhood Chain groups carry it today:
Pendle, Curve and the Morpho Blue singleton, and their 80 is on-chain since the
2026-09-20 re-push. The flag is not a live comparison
with the other chain, so it must be removed by hand if that committee rotates.

See `data/scored_targets_2026-09-15*.md` (6 files),
[`data/scored_targets_2026-09-16-batch7.md`](data/scored_targets_2026-09-16-batch7.md)
and [`data/scored_targets_2026-09-16-batch8.md`](data/scored_targets_2026-09-16-batch8.md)
for the full on-chain trace behind every score.

**Cross-ECOSYSTEM signer overlap (added 2026-09-17)**: `signer_overlap.py` above only
checks overlap *within* Robinhood Chain's own ~21 tracked groups -- a real,
project-wide gap this project's own audit named: does a Robinhood Chain Safe's owner
also sit on an Ethereum L1 or Base Safe this project separately tracks? Or is the
exact same Safe *address* (a real pattern -- see `multisig-overlap`'s own findings on
ether.fi, Curve, Aave V3 sharing one CREATE2-deployed Safe across chains) redeployed
on more than one of them? New module,
[`scripts/lib/cross_ecosystem_overlap.py`](scripts/lib/cross_ecosystem_overlap.py),
answers both, live against all three chains at once:
[`scripts/check_cross_ecosystem_overlap.py`](scripts/check_cross_ecosystem_overlap.py).
Live result, 2026-09-17 (25 groups: 21 Robinhood Chain, 2 Ethereum L1, 2 Base):
**none found**, on either check -- a genuine, re-runnable negative result, not an
assumption. Deliberately not wired into any live `score_all()`/`crossExposureScore`
push yet (Ethereum L1 and Base aren't deployed, so there's no live score for this to
feed there; coupling Robinhood Chain's own weekly production push to L1/Base RPC
calls needs more reliability testing first) -- re-run the script above as more
targets and ecosystems get added.

**Correction 2026-09-18**: both premises above are now stale. Ethereum L1,
Arbitrum and Base are all real deployed oracles as of today (see "Real
multi-chain deploys" below) -- there is live score data for a cross-ecosystem
check to feed now. And a real overlap WAS found since this negative result, by
the individual Arbitrum and Base Aave V3 scorers themselves rather than this
shared module: `chains/arbitrum-ecosystem/scorers.py::score_aave_v3_pool_arbitrum`
and `chains/base-ecosystem/scorers.py::score_aave_v3_base` each independently
compare their own `GOVERNANCE_GUARDIAN` Safe's live owner set against a dated
snapshot of the other chain's -- and found the identical 9 owners at 5-of-9,
a different address on each chain, the same CREATE2-redeployed shared-committee
pattern `multisig-overlap` already documented for ether.fi/Curve. Both scorers'
`crossExposureScore` reflects it (80, not 100). `cross_ecosystem_overlap.py`'s
own 3-chains-at-once live re-run, and wiring that shared module into
`score_all()` now that all 3 have live data, remain not done -- the finding
above closes the specific Aave-guardian case, not the general question.

**Second correction 2026-09-18**: the shared module HAS now been re-run live,
extended to 5 ecosystems -- Arbitrum and Tempo were added to
`cross_ecosystem_overlap.py` the same day (see `ARBITRUM_GROUPS`/`TEMPO_GROUPS`
in that file), closing the "own 3-chains-at-once live re-run... remain not
done" gap immediately above. Live result,
`python3 scripts/check_cross_ecosystem_overlap.py`: **38 groups across 5
ecosystems** (Robinhood Chain 25, Ethereum L1 3, Arbitrum 4, Base 4, Tempo 2).
Signer overlap: the same 9 Aave-guardian signers already found above (Arbitrum
`aave_guardian` × Base `aave_guardian`) -- no NEW overlap surfaced, and
Tempo's 2 resolvable Safes (`cap_safe`, `usdt0_safe`) share zero signers with
any other tracked ecosystem. Identical-Safe-address check: still none found.
Tempo was chosen for this pass specifically because competitive research the
same day found payment/stablecoin-settlement L1s (Plasma, Tempo, Arc) are
structurally excluded from L2Beat's Stage coverage (L2Beat only tracks chains
deriving security from L1 Ethereum) and have disclosed, currently-centralized
validator sets that no independent risk-scoring provider tracks at the chain
level -- this module's cross-chain signer-overlap capability is, as far as
that research found, not replicated anywhere else even for a single chain,
let alone applied to this specific chain category. See
`data/finding_2026-09-18-competitive-positioning-cross-chain-overlap.md`.

**Third correction, same day**: acted on that research immediately -- Plasma
now has a real scorer (`chains/plasma-ecosystem/scorers.py`, 7 targets, see
"Plasma" under Status below) and was wired into `cross_ecosystem_overlap.py`
as a 6th ecosystem the same pass. Live re-run,
`python3 scripts/check_cross_ecosystem_overlap.py`: **45 groups across 6
ecosystems** (Robinhood Chain 27, Ethereum L1 3, Arbitrum 4, Base 4, Tempo 2,
Plasma 5). Three real overlaps surfaced, all independently re-confirmed via
direct `eth_call`s before being written into any scorer or this file:

1. Plasma's own Aave V3 guardian Safe shares the identical 9-signer,
   5-of-9 committee already found on Arbitrum and Base -- now a **third**
   chain, not two.
2. Plasma's Ethena USDe OFT owner Safe shares the identical 10-signer,
   5-of-10 owner set as Ethereum L1's own already-tracked Ethena Safe (a
   previously undocumented fact -- carries the SAME people, not just a
   similar structure).
3. **New, found only by this run, not by any individual scorer**: Plasma's
   Pendle Safe (`0x7877AdFaDEd756f3248a0EBfe8Ac2E2eF87b75Ac`) is not just
   signer-identical but **the literal same Safe address** as Robinhood
   Chain's own already-tracked Pendle Safe -- a CREATE2-redeployed
   identical contract across two unrelated chains, the "identical Safe
   ADDRESS" check's first-ever real hit in this project (every prior run
   found signer overlap only, never an address match).

`chains/plasma-ecosystem/scorers.py`'s own `score_aave_v3_pool_plasma()`
and `score_ethena_usde_oft_plasma()` already reflect findings 1-2 in their
published `crossExposureScore` (80, not 100). Finding 3 was not
independently baked into any scorer's own hardcoded comparison when it was
found and was disclosed here instead, since it was this shared module's own
generic check that caught it, not a scorer-specific one; since 2026-09-20
`score_pendle_plasma()` folds it too (see the convention decision below).

**Convention decision, 2026-09-20 (supersedes the "not wired into any live
`score_all()`/`crossExposureScore`" premise at the top of this section and the
80-versus-100 split between chains)**: a cross-ecosystem committee match is now
folded into `crossExposureScore` on every EVM ecosystem, as a flat 80
(`min(within-ecosystem score, 80)` on Ethereum L1, Robinhood Chain and Tempo).
Each scorer compares the owner set it just read on its own chain with a
hardcoded, dated snapshot of the other chain's committee; none calls a second
chain's RPC. Before this, Ethereum L1, Robinhood Chain and Tempo kept such an
overlap out of the score while Arbitrum, Base, Monad and Plasma (Aave and Ethena
only) folded it, so the
same committee read 80 on one chain and 100 on another. **Pushed on-chain on
2026-09-20 (six transactions, all status 1, table below); the oracles were read
back with `getScore()` and equal the scorer output exactly.** `crossExposureScore`
moved from 100 to 80, composites unchanged, for: Ethereum L1 (Aave V3 Pool, Morpho
Blue), Robinhood Chain (Pendle V2, Curve DEX, Morpho Blue singleton), Plasma
(Pendle, Euler eVaultFactory, Euler AccessControlEmergencyGovernor) and Tempo
(Morpho Blue core). Two more targets changed sub-scores for a different reason,
a second admin path the same day's role sweep found: Radiant's LendingPool
(Arbitrum) 55/100/55/100/100/69 became 65/95/0/100/100/55, because its pool
admin is a 4-of-11 Safe with no timelock, separate from the 72h timelock the
scorer had credited; Monad's Aave V3 Pool 65/100/50/100/80/71 became
65/75/0/100/80/49, because its 4-of-7 `PROTOCOL_GUARDIAN` Safe also holds
`POOL_ADMIN`. The same push also swapped Ethereum L1's Ethena target: the old one
was USDe's retired minter, so the live minter (`0xe3490297...b62D3`, admin a 24h
timelock behind a 5-of-10 Safe) was added as index 14 at 65/100/55/100/20/73 and
the old one (index 3) is no longer refreshed (it turns stale after 2026-09-28 16:39 UTC) (see
`data/finding_2026-09-20-ethena-live-minter.md`).

**Registry coverage pass and a new cross-chain committee, 2026-09-20 (late)**: the sweep's registry named only 7
of 20 Ethereum L1 targets, 6 of 10 on Arbitrum, 3 of 9 on Base and 2 of 14 on Tempo, so it could only find
overlaps a scorer already knew. Every unregistered target's Safes and bare EOAs were taken from its scorer notes,
checked on chain and registered (86 groups on 7 ecosystems at that point, 92 after the Uniswap groups and WBTC's legacy multisig below). First result: **Compound V3's `pauseGuardian`
is one 9-signer 5-of-9 committee on Ethereum L1, Arbitrum and Base** (three Safe addresses, identical owner sets,
8 bare EOAs and 1 contract), so one quorum can freeze three Comets. `crossExposureScore` of Compound on those
three chains is now 80 (composites unchanged), record in
[`data/finding_2026-09-20-compound-pause-guardian-three-chains.md`](data/finding_2026-09-20-compound-pause-guardian-three-chains.md);
the six other newly registered groups (EigenLayer, Aave Horizon, Rocket Pool, Aerodrome Slipstream, Moonwell, Telos)
found no overlap. The oracle holds the old value for these three until the next re-push.

**One Uniswap Timelock, 11 tracked targets on 5 ecosystems, 2026-09-20 (late)**: asking the cross-exposure
question of the contract roots the sweep could not compare (a DAO Timelock has no signer set) found that
Uniswap's Ethereum L1 Governance Timelock roots V3/V4 on L1, V3 on Arbitrum, V3/V2/V4 on Base, four targets on
Robinhood Chain and V4 on Monad, reached through a bridge alias, an OP-stack forwarder or a Wormhole relay. Nine of
them still read `crossExposureScore` 100 because an older rule said Timelock-rooted targets are "not counted", a limit
of the sweep rather than a decision. All eleven now read 80 (composites unchanged), each scorer folding only on a root
it confirmed that run; the sweep now reports the shared root across five ecosystems. Record in
[`data/finding_2026-09-20-uniswap-one-timelock-eleven-targets.md`](data/finding_2026-09-20-uniswap-one-timelock-eleven-targets.md);
scorer output only until the next re-push of Arbitrum, Base, Monad and Robinhood Chain.

**Cross-exposure consistency audit, 2026-09-21**: asking whether the same relation gets the same number
wherever it appears found four inconsistencies, now fixed with composites unchanged: GMX V2's RoleStore read 100
while the V1 Vault reading the same shared Safe read 80 (the relation is symmetric, both now 80); Arbitrum's Pendle
read 60 for a committee that reads 80 on the two other chains it sits on (a disclosed deviation from the flat-80
convention, closed, and note this one goes up); Monad's Uniswap hop to Ethereum, taken from a note, is read live; and
Kinetiq's two StakingManagers on Hyperliquid share one root Safe yet read 100 each, because the methodology counted only
HyperCore keys (both now 80, methodology 4.5 extended to HyperEVM root holders). Three open points are listed
([`data/finding_2026-09-21-cross-exposure-consistency-audit.md`](data/finding_2026-09-21-cross-exposure-consistency-audit.md)).
Scorer output only until the next Arbitrum, Monad and Hyperliquid re-push.

**Safe modules and guards, 2026-09-21**: the helper every scorer uses reads a Safe's owners and threshold, never its
modules or guard, and a module can execute as the Safe without the owners. A new sweep
(`python3 scripts/check_safe_modules_guards.py`) reads both for every registered root Safe: of 74, 68 have neither and
5 carry an analyzed one (Chainlink's feed-admin Safe on Robinhood Chain, Arbitrum's Security Council, Radiant's
emergency-admin Safe with two Hypernative pause modules, and Ethena's guard on L1 and Plasma). None bypasses the threshold in
a way that moves funds; no score moves. It also reads each Safe's singleton and fallback handler: 72 of 73 are on a
published Safe build, and the one that is not (Chainlink's feed-admin Safe) was diffed against the official v1.3.0 sources,
identical except a stricter `setGuard`. **Policy (decided 2026-09-21): a Safe with an unanalyzed module, or a singleton that is
neither published nor analyzed, is treated as unresolved authority by every scorer** (one gate in `safe_owners_and_threshold`,
with a `SAFE AUTHORITY GATE` note); a module list that cannot be read only adds a note. Anything unknown is reported as UNANALYZED
([`data/finding_2026-09-21-safe-modules-and-guards.md`](data/finding_2026-09-21-safe-modules-and-guards.md)).

**Correction, 2026-09-21: two Robinhood Chain scores used a leftover multisig formula.** Chainlink's feed-admin Safe (4-of-9)
and LayerZero's messaging-core multisig (5-of-7) took `multisigScore = threshold * 8` (32 and 40), a batch-8 heuristic with no
rationale written down, while every other Safe-rooted target uses `15 per required signer + 5 per extra owner` (85 and 85 for
the same shapes). Both now use the shared formula: Chainlink 36 to **52**, the three LayerZero targets 34 to **48**. The
LayerZero discount for a non-Safe multisig stays in adminKeyScore (55, not 65). The Chainlink scorer also kept adminKeyScore
65 when its Safe did not resolve; it now degrades to the unresolved floor (20, 0, 0). The Morpho vault heuristic in the same file
is documented and calibrated to manual scores, and is left alone. Both values go **up** (less risk reported).
Record: [`data/correction_2026-09-21-chainlink-layerzero-multisig-formula.md`](data/correction_2026-09-21-chainlink-layerzero-multisig-formula.md).
Scorer output only until the next Robinhood Chain re-push.

**Who really signs, 2026-09-21**: an owner of a Safe is not always one key. Of 405 distinct signers of the registered root
Safes, 376 are plain EOAs, 27 are themselves Safes, one is a TimelockController and one is an EOA delegated through EIP-7702
(MetaMask's delegator, on Monad). `scripts/check_nested_signers.py` resolves them to the EOAs behind them: no committee is weaker
than its threshold says (the effective key count equals the threshold for 15 of 17 Safes with such a seat and is higher for two),
all 27 nested Safes are clean, and 13 committee pairs turn out to share keys only through nested owners, none of which changes a
score. Compound's "identical" pause-guardian committee has a nested Safe that is 2-of-6 on two chains and 2-of-5 on the third
([`data/finding_2026-09-21-who-really-signs.md`](data/finding_2026-09-21-who-really-signs.md)).

**The code moves, the score does not notice, 2026-09-21**: the oracle scores who controls a target, not the code they control.
On Robinhood Chain 12 of 13 proxies have been upgraded and five of them within the last 26 days (Symbiosis 9 days ago); where an
archive read was possible, Compound V3 on Ethereum and Yuzu yzUSD on Plasma had a different implementation than 30 days earlier.
`scripts/check_implementation_changes.py` now fingerprints all 148 tracked targets (implementation address and code hash for
proxies and clones, code hash otherwise) and diffs against `data/implementation_snapshot.json`; the re-push script runs it first.
For each change it says, without touching a bot-protected explorer, what the new code adds or drops (selectors from the bytecode) and
where its source is verified (Sourcify, Routescan for Plasma and Ethereum, Etherscan only with the operator's own key): of 38 proxy
implementations, 24 verified, 1 not verified anywhere it can be asked, 13 unknown (Robinhood Chain, Monad, HyperEVM: explorer behind a
bot check or a key). Yuzu yzUSD moved to a V3 that adds a NAV setter and fee levers, none granted to anyone yet.
A changed implementation is normal and changes no score, it says the score should be re-read against the new code
([`data/finding_2026-09-21-implementation-changes.md`](data/finding_2026-09-21-implementation-changes.md)).

**Coverage by listed TVL, 2026-09-21**: matching DefiLlama's per-chain TVL to the tracked targets by protocol name, Robinhood Chain reads
**99.0%** ($16.3M untracked over 126 protocols, the largest $2.2M), Plasma 88%, Base 60%, Ethereum L1 53%, Arbitrum 51%, Monad 46%.
An estimate, corrected by hand only for Robinhood Chain, and TVL is not custody (SSV Network's $14B on L1 is staking attestation, not funds
in a contract this oracle would score). The real-custody leads (Maple, USDT0, the Base vault layer, the L1 rollup bridges) are named, not
traced ([`data/coverage_2026-09-21-tvl-by-ecosystem.md`](data/coverage_2026-09-21-tvl-by-ecosystem.md)).

| Oracle | Transaction | Block |
|---|---|---|
| Ethereum L1 (Sepolia) | `0x14b0466ab52a7bf6cab54253cda92c73d52ca1b88957632911d79136b99b7a98` | 11,740,952 |
| Arbitrum (Sepolia) | `0x308ad2c8fa527a0e5c30139b6b154ff48462cd046df9840a17f25775c21fbd23` | 310,697,409 |
| Plasma testnet | `0xa2e8f4f12ccbe3740734bccfa5ee9cf4c20018f5a453a38c00e77a8583cb3de4` | 34,034,832 |
| Monad testnet | `0xa93596300b689383572880cd4de76ee2fc7bce68ac5791db38501b07b987a019` | 64,022,942 |
| Tempo Moderato | `0xcdc3cc092d5e641de9407484a929ab40732799e0ae043f9fdea8d7ef400aa44b` | 36,054,236 |
| Robinhood Chain testnet | `0x020cf83c8a007afaef0eadf7ecb271432c80f1ffd9bfafed984ab6eca17c4978` | 121,858,777 |

Base was not re-pushed (no Base score changed). `api/scores.json`, the Robinhood
Chain snapshot, was regenerated by the push script with the Robinhood transaction and
block above. Not solved: a snapshot goes stale on a committee rotation and is
only caught when this section's sweep script or the drift audit is re-run, and
Solana, Hyperliquid and Zcash are not covered at all (Tempo is EVM-signer and is).
Rule, table, verification and residual gaps:
`data/finding_2026-09-20-cross-exposure-convention-and-score-adjustments.md`
(section 9 has the transaction table and the read-back).

**Chain-level authority ceiling, `l1CappedComposite` (added 2026-09-17, off-chain
only)**: no protocol built on Robinhood Chain can be meaningfully safer than the L1
authority that can upgrade or reconfigure the rollup itself -- a perfect
`compositeScore` on a protocol means little if the chain underneath it can still be
altered by a real 7-of-8 Security Council Safe (`score_rollup_l1_authority()`,
currently 57/100 -- revised the same day from 60 after a cross-Safe signer-overlap
finding was wired in, see the target table above). `l1CappedComposite =
min(target's own compositeScore, that 57)`, published as a SEPARATE field (see
`METHODOLOGY.md`) -- `compositeScore` itself
is never overwritten, same reasoning as `crossExposureScore`. Deliberately
**off-chain only**: the deployed oracle's `AuthorityScore` struct has no field for
this (a contract migration is a bigger, separate decision), so it's published in
`api/scores.json`, not pushed on-chain, and not read by `dashboard/index.html`
either -- the dashboard's own stated design ("reads every score directly from the
deployed oracle... nothing to trust but the RPC and the contract itself") stays
true without a silent exception.

**Two dimensions checked, not (yet) scored (2026-09-17)**: real recent exploits named
two authority surfaces this project's five dimensions don't cover -- checked both
against currently-tracked targets rather than left as a plan.

- *Cross-chain messaging delegate.* The Sandbox's SAND bridge exploit hijacked
  LayerZero's `delegate` role for an OApp -- a surface that can reconfigure the
  entire security stack (DVNs, executors) without ever touching the OApp's own
  owner/admin. New reusable check,
  [`scripts/lib/layerzero_delegate_risk.py`](scripts/lib/layerzero_delegate_risk.py)
  (`scripts/check_layerzero_delegate_risk.py` to re-run it): checked all 57
  addresses this project hardcodes anywhere in `scripts/lib/scorers.py` (every
  tracked target plus its intermediate authority chain) against Robinhood Chain's
  LayerZero V2 `EndpointV2.delegates()`, live. Result: **zero are registered
  OApps with a delegate set.** Not wired into `score_all()` as a scored field --
  a dimension that would read "not applicable" for literally every current target
  forever is clutter, not signal. The capability is real and one command away
  the moment a tracked target is a LayerZero OApp.
- *Governance capture.* Term Finance's Meta Vault was drained by a
  self-deployed proposal that self-proposed, self-voted, and waited out a real
  (not reset) timelock -- the vote itself was capturable, the delay didn't help.
  Live-verified against Uniswap's GovernorBravo (already tracked,
  `chains/ethereum-l1/scorers.py`): quorum (40M UNI) is 4.0% of total supply,
  proposalThreshold is 0.1%, and the 5 most recent real proposals (ids 96-100)
  cast 46.9M-73.0M UNI, consistently clearing quorum with real margin. Added as
  disclosed facts/notes on that scorer, deliberately **not** turned into a 0-100
  sub-score: the piece that would actually calibrate capture risk (how
  concentrated that turnout is among delegates who could coordinate alone) needs
  a `DelegateVotesChanged` replay back to UNI's 2020 genesis -- infeasible on
  free RPCs the same way this project's other genesis-scale replays have been.
  Publishing a confident-looking number without that data would be exactly the
  fabricated-but-plausible score this project's own discipline exists to catch.

**Data-collection hardening from a sister project's own postmortems (2026-09-17)**:
`defi-admin-key-risk` (96+ EVM protocols, 20+ verification rounds) found two
recurring blind spots that could silently break this project's own classifiers.
New module, [`scripts/lib/account_classification.py`](scripts/lib/account_classification.py)
(`scripts/check_data_collection_hardening.py` to re-run both checks):

- *EIP-7702 delegation.* An EIP-7702-delegated EOA (exactly 23 bytes of code:
  the `0xef0100` designator + a 20-byte delegate) has code, so `is_eoa()`
  correctly says "not a bare EOA" -- but it's still fundamentally controlled by
  ONE signing key, the same single-point-of-failure shape as a bare EOA, not the
  independently-controlled contract a naive "has code" check might assume (this
  is exactly the pattern Moonwell's MAMO attacker used: an ordinary MetaMask
  wallet, 7702-delegated, run as an exploit contract). Checked all 57 addresses
  this project hardcodes anywhere -- **zero are EIP-7702-delegated today.** A
  new, separate function rather than a change to `is_eoa()` itself, which is
  called from dozens of sites across every chain's scorers -- silently changing
  its return value for this case would be a much larger blast radius than
  adding one new, opt-in check.
- *AccessControl self-escalation.* Roles have no threshold semantics: if a
  role's own admin role IS itself (`getRoleAdmin(role) == role`), any single
  current holder can grant it to a new address or revoke a legitimate
  multisig's membership unilaterally -- a "1-of-N roles" failure invisible to a
  check that only counts Safe signers. Checked the newly-discovered
  `EthenaTimelockController` (this pass's Ethena investigation) directly:
  `DEFAULT_ADMIN_ROLE` is self-administering (expected, standard OpenZeppelin
  behavior), but `PROPOSER_ROLE`/`EXECUTOR_ROLE`/`CANCELLER_ROLE`/
  `WHITELISTED_EXECUTOR_ROLE` are all correctly gated by `DEFAULT_ADMIN_ROLE`
  instead -- a genuinely sound role hierarchy, confirmed rather than assumed.

**Retroactive backtest (2026-09-17)**: does this methodology actually catch real
incidents, checked against one that already happened rather than argued in the
abstract? [`data/backtest_2026-09-17-wasabi-protocol.md`](data/backtest_2026-09-17-wasabi-protocol.md):
Wasabi Protocol's $5.9M deployer-key compromise (2026-04-30, cross-corroborated
live today against DeFiLlama's own hacks database and Blockaid's incident
tweet) resolves to a real, bare EOA -- live-verified today, not just cited --
with the exact same authority shape (no Safe, no timelock) this project's own
formula already scores at 1/100 for its worst currently-tracked Robinhood Chain
targets. Same formula, real incident, `compositeScore = 2/100`, CRITICAL band.
Honest limitations disclosed in the file itself: the specific vault contract's
`hasRole()` call wasn't independently re-verified this pass (time-boxed, flagged
as real follow-up, not silently skipped), and this is a retrospective
classification, not a claim the oracle caught it live (Wasabi was never a
tracked target).

**Second retroactive backtest (2026-09-17)**: a non-EVM, non-multisig authority
shape, to prove the methodology generalizes past "bare EOA."
[`data/backtest_2026-09-17-solend-governance-emergency-powers.md`](data/backtest_2026-09-17-solend-governance-emergency-powers.md):
Solend DAO's June 2022 "emergency powers" governance incident (SLND1 granting the
team emergency OTC-liquidation power over a whale's ~$170M position, reversed the
next day by SLND2 after backlash). Decoded live, byte-for-byte, straight from
Solana account data (`chains/solana/scripts/sol_read.py`'s own RPC conventions,
extended to a new account type): the exact vote tallies to 6 decimal places
(SLND2: 1,480,264.26 yes / 3,535.29 no, matching press exactly once rounded), the
exact ~6-hour voting-window timestamps for both proposals, and -- caught before it
became a wrong citation -- that Solend runs its own dedicated governance program
(`A7kmu2kUcnQwAVn8B4znQmGJeUrsJ1WEhYVMtmiBLkEr`), not the shared default instance
already documented in `chains/solana/METHODOLOGY.md`. Generalizing this project's
timelock dimension from "Solidity `delay` value" to its exact token-vote analogue
(time between a proposal passing and it taking irreversible effect) gives
`timelockScore = 0` for SLND1's 6-hour, zero-hold-up window -- an illustrative
`compositeScore = 8/100`, CRITICAL band, computed before the same-day formula
this generalization fed into (`realms_governance`, METHODOLOGY.md 6.1) had
actually been written and tested. **Corrected same day, in the backtest file
itself**: applying the tested formula to these SAME 2022 parameters gives
`~62/100`, not 8 -- the original number gave no credit for the voting window
itself being a real, if short, delay. That correction doesn't change this
backtest's bottom line, though: Solend DAO was promoted the same day to a real
scored target (`chains/solana/scorers.py::score_solend_dao_governance`), and
its actual live score is `2/100`, WORSE than either number here, dominated by
a separate authority path this backtest's own scope never covered -- a bare,
still-active EOA that controls the Realm's own voting configuration with no
vote required at all. Honest limitations disclosed in the file itself: SLND1's
exact instruction payload wasn't decoded (which specific power was granted,
beyond the vote record itself), the reported $700k vote-buying claim for
SLND2 wasn't independently re-verified on-chain, and this is retrospective, not a
live catch.

**Third retroactive backtest (2026-09-17)**: a compromised multisig, and a
real before/after live score, not just a historical estimate.
[`data/backtest_2026-09-17-drift-protocol-security-council-compromise.md`](data/backtest_2026-09-17-drift-protocol-security-council-compromise.md):
Drift Protocol's 2026-04-01 $285M Security Council compromise -- cited in
this project's own README as SolGov's founding motivation, making it an
obvious next target once confirmed (via Chainalysis, TRM Labs, Elliptic,
BlockSec) to be a genuine authority-risk failure, not a smart-contract bug.
Decoded live, straight from the two actual malicious transactions (not
cited from press): the exact compromised Squads multisig (2-of-5, zero
timelock, a non-default `config_authority` -- independently found, not
reported by any source reviewed), and offline PDA re-derivation confirming
the exact vault address the `UpdateAdmin` log shows being swapped to the
attacker. `compositeScore = 32/100` for that configuration. Drift's
CURRENT program-upgrade authority (a different, live-verified Squads v4
multisig) is 4-of-7 with a real 1-hour delay where none existed before --
`compositeScore = 48/100` combined with a second full-power path (Drift
DAO's own self-governed Realms governance, unlike Solend's bare-EOA realm
authority). A real, measured improvement (`32 -> 48`), not merely claimed --
and this target is now live-scored going forward
(`chains/solana/scorers.py::score_drift_protocol`), not just backtested.
Went through its own adversarial review before committing: 1 real code bug
found and fixed (a missing `none_means_renounced` flag that would have
inverted the risk signal for a future renouncement -- Drift's authority
isn't currently renounced, so the published score was unaffected) plus 2
documentation issues in the backtest file itself (an incomplete
transaction-log transcript; a composite-score arithmetic box that skipped
the cross-path `min()` step) -- both corrected, not swept under a rug. See
`data/correction_2026-09-17-drift-protocol-adversarial-review.md`.

**Open thread, narrowed 2026-09-17, still not fully closed**: batch 8's reconnaissance
found that Morpho NetNet Credit vault's oracle provider (all 7 of its markets) does
not match Chainlink, Pyth, or RedStone's known interfaces -- genuinely unidentified,
not "no oracle dependency." This pass did the market-enumeration work batch 8 flagged
as missing (`adapter (0xf0eeF247...) -> marketIds() -> Blue singleton's
idToMarketParams()`, live against `rpc.mainnet.chain.robinhood.com`) and confirmed the
"not Chainlink/Pyth/RedStone" finding directly rather than by inference: each of the 7
markets has its own oracle contract (6 share identical 2,563-byte bytecode, the 7th is
1,550 bytes), all exposing only Morpho Blue's own minimal native `price()`/
`SCALE_FACTOR()` interface (`SCALE_FACTOR = 1e24`) -- no `owner()`, no `hasRole()`, no
Chainlink-style `latestAnswer()`, no MorphoChainlinkOracleV2-style `BASE_FEED_1`/
`QUOTE_FEED_1` getters found either. What this pass could NOT determine: whether the
price is genuinely fixed forever (in which case `oracleAuthorityScore=100` may be the
right call after all, not a gap) or updatable by some mechanism under a name not yet
guessed -- the public RPC used doesn't retain enough history to compare `price()`
across old blocks and settle this. Narrowed from "genuinely unidentified interface"
to "identified interface, unresolved updatability" -- still open, not silently
resolved either direction.

**Recurring updater wired**: [`scripts/update_scores.py`](scripts/update_scores.py)
re-derives every target's score directly from live chain state (not a cached value)
and pushes a fresh `updateScores()` batch. Runs weekly via
`.github/workflows/update_scores.yml`, or
on demand:

```bash
pip install -r scripts/requirements.txt
READ_RPC_URL=https://rpc.mainnet.chain.robinhood.com \
ORACLE_RPC_URL=https://rpc.testnet.chain.robinhood.com/rpc \
ORACLE_ADDRESS=0x9BF45734D09bC7CA39238e767B2af9AAc62a7f52 \
PRIVATE_KEY=... \
python3 scripts/update_scores.py [--dry-run] [--skip-slow]
```

`--skip-slow` (only valid together with `--dry-run`) skips the 4 scorers
that each replay full chain history via `eth_getLogs` -- the reason a
complete run has been clocked exceeding 50 minutes. Useful for a fast local
check; never for a real publish, since it would omit 4+ tracked targets.

Mainnet target: [Robinhood Chain](https://docs.robinhood.com/chain) (Arbitrum Orbit
rollup, mainnet since 2026-07-01), chosen because it already carries real, checkable
authority risk with no existing independent risk-monitoring coverage found. Next:
move the whole stack (oracle + updater's `UPDATER_ROLE` key) to mainnet, migrating
that key to a real multisig rather than the single deploy key used for testnet
validation -- the same weak-authority pattern this oracle exists to catch.

### Real multi-chain deploys (2026-09-18): 3 more chains, not just Robinhood Chain

Everything above this line describes Robinhood Chain, the first validation deploy.
The same day, this project deployed the identical, unmodified
[`src/AuthorityRiskOracle.sol`](src/AuthorityRiskOracle.sol) and pushed a real,
live-derived `updateScores()` batch on three more public testnets, using a
rotated, separately-funded shared key
(`0x20630C6Ab4BA48a80edA46F77b9b6e987A8f32f5` -- replacing an abandoned,
never-funded key flagged as possibly exposed in local working notes, see
[`chains/ethereum-l1/deploy/README.md`](chains/ethereum-l1/deploy/README.md)).
Every address, tx hash and target count below is copied from each ecosystem's own
deploy record (`chains/<ecosystem>/deploy/README.md`), re-verified against the
live oracle read after each push, not hand-typed once and trusted:

| Chain | `AuthorityRiskOracle` | `updateScores()` tx | Targets pushed |
|---|---|---|---|
| [Ethereum L1 Sepolia](https://sepolia.etherscan.io/address/0xB6F8474ccC71AF477c31c2DF663B3942ddfbf906) (chain 11155111) | `0xB6F8...bf906` | [`0xfbb1caf4...4952`](https://sepolia.etherscan.io/tx/0xfbb1caf4ef05f303b7b231495baa58c5638de831f0f5cfe64e789bd249522e51) (first push, 9 targets; later maintenance pushes since) | 15 |
| [Arbitrum Sepolia](https://sepolia.arbiscan.io/address/0x50840a7667baEa9D05ad4ae3dCeb384724b58720) (chain 421614) | `0x5084...8720` | [`0xa934822b...d85b`](https://sepolia.arbiscan.io/tx/0xa934822b3ed2959761641e312b4646890243ede3f82648e433fecfea1d57d85b) (2026-09-19; first push [`0x1c6f9bb9...5649`](https://sepolia.arbiscan.io/tx/0x1c6f9bb9644eaaed87d21ee5fe9d594d9b04bc35b6e374541ba4caf089a85649)) | 9 |
| [Base Sepolia](https://sepolia.basescan.org/address/0x50840a7667baEa9D05ad4ae3dCeb384724b58720) (chain 84532) | `0x5084...8720` | [`0xc412f6dc...14fa1`](https://sepolia.basescan.org/tx/0xc412f6dc76299177db63ab207a9609ae5124215d2ac52ac280e98fa9a1c14fa1) (latest, 2026-09-19 maintenance; first push [`0xd7483e0a...897f0`](https://sepolia.basescan.org/tx/0xd7483e0a50f292e8da859dbc37895f3fd7f7f1bba2c413bb137f5c483ca897f0), 5 targets) | 9 |

Arbitrum Sepolia's and Base Sepolia's `AuthorityRiskOracle` share the identical
address by coincidence, not a bug: a CREATE address is `keccak(deployer, nonce)`,
chain-independent -- the same shared deployer key happened to be at the same
nonce on both chains when each oracle was deployed. Every tx above is a real
broadcast (`status: 1`), independently confirmed via `cast receipt`, not a
`--dry-run` rehearsal -- see each ecosystem's own deploy README for the full
bytecode/`getScore()` spot-check trail.

This makes **65 real, live-tracked targets across 4 real deployed oracles**, not
46 on one chain. [`dashboard/index.html`](dashboard/index.html) reads all four
live in the same page now (chain tabs, no build step, still nothing but a raw
`eth_call` from your own browser) -- see the next section.

### Plasma -- live since 2026-09-19, a 5th real deployed oracle

[`chains/plasma-ecosystem/scorers.py`](chains/plasma-ecosystem/scorers.py) --
**9 targets**, scored live against `https://rpc.plasma.to` (chain 9745) and
now pushed for real to a deployed oracle on Plasma Testnet (chain 9746) --
see [`chains/plasma-ecosystem/deploy/README.md`](chains/plasma-ecosystem/deploy/README.md)
for the full real-deploy record (addresses, tx hashes, a full `getScore()`
read-back confirming every pushed value). Added 2026-09-18 the same day
competitive research (see "Cross-ECOSYSTEM signer overlap" above)
identified payment/stablecoin L1s as real, uncontested territory; deployed
the very next day. Deployed without Foundry (`forge` still isn't installed
in this environment) -- compiled with `py-solc-x` instead and broadcast the
transactions directly via `web3.py`, same bytecode, 0 compile errors:

| Target | Composite | Authority shape |
|---|---|---|
| Plasma L1 validator-set (Aquila) | 35 | 3-of-4 Safe, no timelock -- chain-level baseline every other target inherits |
| Aave V3 Pool | 71 | Executor/PayloadsController pair, real 1-day delay, 5-of-9 guardian Safe shared with Arbitrum + Base |
| Pendle (Router + Market Factory V6) | 43 | 3-of-5 Safe, same literal address as Robinhood Chain's own tracked Pendle Safe |
| Ethena USDe OFT | 52 | 5-of-10 Safe, same 10 signers as Ethereum L1's own tracked Ethena Safe, no timelock active yet (one queued) |
| Euler V2 eVaultFactory | 72 | Governor -> 4-day Timelock -> 4-of-8 DAO Safe, 2-of-3 securityCouncil cancel path |
| Euler V2 AccessControlEmergencyGovernor | 68 | Same shape, 2-day delay, per-vault risk-parameter authority |
| Fluid (Instadapp) Liquidity | 59 (was 67 until the 2026-09-20 evening re-push) | Self-administered TimelockController, real 24h delay, proposer = 6-of-12 Avocado multisig, executor = 3-of-5 Safe, same committee as Fluid on Arbitrum (resolved 2026-09-20) |

*(Pushed on-chain 2026-09-20, tx
[`0xa2e8f4f1...3de4`](https://testnet.plasmascan.to/tx/0xa2e8f4f12ccbe3740734bccfa5ee9cf4c20018f5a453a38c00e77a8583cb3de4),
block 34,034,832: the Pendle, Euler V2 eVaultFactory and Euler V2
AccessControlEmergencyGovernor rows now read `crossExposureScore` 80 (was 100,
composites 43, 72 and 68 unchanged), because the same committee is tracked on
another chain (Pendle: Robinhood Chain; the two Euler rows: Monad); see the
convention note under "Cross-ECOSYSTEM signer overlap". The deployed oracle was
read back and holds these values; the Fluid row was rewritten by a later push, see the next note.)*

*(Pushed on-chain 2026-09-20 evening, Plasma testnet tx [`0x3c709f07...f645`](https://testnet.plasmascan.to/tx/0x3c709f07756416a72c5fce1bd96ffa482b52df3c8bd2a9d283f88aa263e0f645), block 34,100,595, read back 9 of 9 equal to the scorer: Fluid's proposer and executor signer sets are now read instead of
left unresolved. The proposer is an Avocado multisig (6 of 12), the executor a 3-of-5 Safe, both identical
on Arbitrum One where the same structure was already scored. Fluid moves from 40 / 100 / 70, cross 100,
composite 67 to 65 / 55 / 55, cross 80, composite 59, the value the Arbitrum scorer gives the same
structure; the oracle held 67 until this push. Evidence:
`chains/plasma-ecosystem/data/fluid_liquidity_plasma_2026-09-20_signers.md`.)*

Aave alone is ~$496M of Plasma's ~$570M total chain TVL (DefiLlama,
~87%). Every address sourced from each protocol's own official GitHub
address-book (`bgd-labs/aave-address-book`, `pendle-finance/
pendle-core-v2-public`, `euler-xyz/euler-interfaces`, `Instadapp/
fluid-contracts-public`), never from a dashboard or block explorer's
"verified name" label. Run it yourself:
`python3 chains/plasma-ecosystem/scripts/dry_run.py`.

**Disclosed operational risk**: this file was built by several parallel
research passes writing to the same shared path with no lock/merge step,
and the file was overwritten wholesale multiple times mid-way before
being consolidated -- every address and authority-chain claim was
independently re-verified live a second time (fresh `eth_call`s, not just
re-reading the research reports) before this version was written out and
committed. See the file's own top docstring.

**Real deployment, 2026-09-19**: `AuthorityRiskOracle` =
[`0x50840a7667baEa9D05ad4ae3dCeb384724b58720`](https://testnet.plasmascan.to/address/0x50840a7667baEa9D05ad4ae3dCeb384724b58720),
`updateScores()` tx `0xcb5c8a3ae7e27eddf0376328a7a27cb9aa28bc2971c878f965a3e1edfb300b99`
(7 targets, real push, status success). Funding took two failed faucet
attempts first (QuickNode rejected the shared key over "insufficient
wallet history", Chainstack requires 0.08 real ETH on Ethereum mainnet)
before `openfaucet.org`'s browser proof-of-work faucet worked cleanly --
no wallet connection, no account, no real-value requirement. Full trail
in the deploy README.

This makes **72 real, live-tracked targets across 5 real deployed
oracles**, not 65 on 4. The dashboard does not yet have a Plasma tab (only
Robinhood Chain, Ethereum L1, Arbitrum, Base) -- a disclosed gap, not done
this pass.

### Tempo -- live since 2026-09-19, a 6th real deployed oracle

[`chains/tempo/scorers.py`](chains/tempo/scorers.py) -- **14 targets** (13 at the 2026-09-19 deploy, Morpho Blue core added the same day in maintenance, see below),
scored live against `https://rpc.tempo.xyz` (Tempo Mainnet, chain 4217) and
now pushed for real to a deployed oracle on Tempo Testnet (Moderato, chain
42431) -- see [`chains/tempo/deploy/README.md`](chains/tempo/deploy/README.md)
for the full real-deploy record. Tempo has **no native gas token**: fees are
paid in a TIP-20 stablecoin (pathUSD), a real difference from every other
EVM chain this project deploys to (see "Gas token and funding" in the
deploy README). Deployed without Foundry (`forge` still isn't installed in
this environment) -- compiled locally with `py-solc-x` (solc 0.8.36,
matching the version this same contract was compiled with here previously)
and broadcast directly via `web3.py`, same unmodified `AuthorityRiskOracle`/
`ExampleConsumer` sources: the on-chain runtime code at the deployed address
was read back with `eth_getCode` and matches the locally compiled runtime
bytecode byte-for-byte.

| Target | Composite | Authority shape |
|---|---|---|
| Tempo L1 validator registry (ValidatorConfigV2) | 31 | 2-of-5 Safe, no timelock -- chain-level baseline every other target inherits |
| USDC.e | 55 | Stargate OFT holds `ISSUER_ROLE`, owner is a 5-of-7 LayerZero OneSig |
| USDT0 | 43 | Policy-3 blacklist admin is the USDT0 Safe, 3-of-5 |
| pathUSD | 9 | `ISSUER_ROLE` sits with an upgradeable bridge controller whose only `DEFAULT_ADMIN` is one bare EIP-7702-delegated EOA (`0x79C6631F...4a4E`, traced on two RPCs) -- lowest composite on Tempo, about $132M of pathUSD + USDB + DLUSD supply under that one key on 2026-09-20 |
| USDB | 9 | Same bridge controller and same single bare EOA as pathUSD |
| cbBTC | 39 | Bridged TIP-20, issuer-role controller resolved per methodology |
| PRIME | 39 | `ISSUER_ROLE` is the weakest path (its `DEFAULT_ADMIN_ROLE` was revoked 2026-07-30) |
| DLUSD | 9 | Same bridge controller and same single bare EOA as pathUSD/USDB |
| EURC.e | 55 | Same Stargate/OneSig shape as USDC.e |
| cUSD | 43 | Plain OpenZeppelin `TimelockController`, 24h delay, log-scan-resolved role holders |
| Sentora pathUSD (Morpho Vault V2) | 27 | `{owner, curator}` root set, Vault V2 shape (rule R8) |
| Unnamed pathUSD Vault V2 feeding Sentora | 9 | owner = curator = one EOA |
| Tempo Earn (Morpho Vault V2, Gauntlet-curated) | 61 | Vault V2 shape, real curator timelock present |
| Morpho Blue core (added 2026-09-19, maintenance) | 55 | owner Safe 5-of-9 (same 9 signers as Morpho on Ethereum), no timelock, fee/IRM/LLTV powers only (rule R9) |

*(Pushed on-chain 2026-09-20, tx
[`0xcdc3cc09...a44b`](https://explore.testnet.tempo.xyz/tx/0xcdc3cc092d5e641de9407484a929ab40732799e0ae043f9fdea8d7ef400aa44b),
block 36,054,236: the Morpho Blue core row reads `crossExposureScore` 80 (was 100,
composite 55 unchanged), because its 9 owners equal the Morpho Association owners
tracked on Ethereum L1, Base and Robinhood Chain. Tempo's signers are ordinary
EVM Safe owners, so it is covered by the cross-ecosystem check. Read back on
chain: 65/96/0/100/80/55.)*

Funding: the official `tempo_fundAddress` JSON-RPC method (Moderato-only,
documented at [tempo.xyz/developers/docs/protocol/rpc](https://tempo.xyz/developers/docs/protocol/rpc/))
takes a single address and mints test pathUSD/AlphaUSD/BetaUSD/ThetaUSD --
no captcha, no login, no real-value deposit -- so this pass called it
directly (4 tx, all `status: 1`, confirmed via `eth_getTransactionReceipt`)
instead of stopping to ask Spap, unlike every other ecosystem's faucet in
this project (each of which needs a browser, a captcha, or a real-value
deposit and is therefore left for Spap to run manually).

**Real deployment, 2026-09-19**: `AuthorityRiskOracle` =
[`0x50840a7667baEa9D05ad4ae3dCeb384724b58720`](https://explore.testnet.tempo.xyz/address/0x50840a7667baEa9D05ad4ae3dCeb384724b58720)
(tx [`0x84224eae...245cb`](https://explore.testnet.tempo.xyz/tx/0x84224eae65d5aa2cd69ab28253f13a35200380c63209b3742d8c90404cf245cb),
block 35905341), `ExampleConsumer` = `0xB7403b365a58B31Ae030DB423f6B703AD67f003a`
(tx `0xd8125dd3310ed0adcec37e1cc160f3527925a6d626d68fc2bc9fa538b17e65b2`,
block 35905344). `updateScores()` tx
[`0x286ef2c4...36c49d`](https://explore.testnet.tempo.xyz/tx/0x286ef2c4b03cde0174c4afa00dda96f5d34b4ed1260cc89db94ab35da736c49d)
(13 targets, real push, status success, block 35906259). Total cost for both
deployments: 0.083145 pathUSD out of the 1,000,000 minted. `getScore()` was
read back live for 6 of the 13 targets after the push -- every field
matches what was pushed exactly, including `methodologyHash`;
`trackedTargetsCount()` returns 13.

`AuthorityRiskOracle`'s address is identical to Arbitrum Sepolia's and Base
Sepolia's own deployed address for the same reason disclosed above: same
shared deployer key, same nonce (0) at deploy time on each chain -- a
CREATE address is chain-independent given `(deployer, nonce)`.

**Correction applied this pass**: `chains/tempo/deploy/README.md` and
`ecosystems.json`'s own action approval text had checked the deployer's
pathUSD balance against the OLD shared key
(`0xA08a76457b758aFF9702dBf5b870679E1232B715`) -- correct when that
scaffolding was written (16:10 that day) but superseded 37 minutes later
the same day (16:47) when the whole pipeline rotated to the current shared
key after the old one was flagged as possibly exposed in a transcript (see
"Real multi-chain deploys" above). Ethereum L1's and Base's own READMEs
were updated after the rotation; Tempo's was not. Re-verified live on the
CURRENT key before funding or deploying (also 0 pathUSD, 0 nonce, confirmed
both ways) -- no funds were ever at risk on the old key either (it was
never funded), but the address named in the documentation was stale.

**Correction, same day**: the "85 real, live-tracked targets" count above
was already stale the moment it was written -- Robinhood Chain's own
`trackedTargetsCount()` was 52 at the time, not the smaller figure that
math assumed, and the dashboard's own Tempo gap this paragraph disclosed
has since been closed too. Both re-verified live, not recomputed from
prose: `trackedTargetsCount()` read directly from all 6 deployed oracles
gives Robinhood Chain **52**, Ethereum L1 **9**, Arbitrum **5**, Base
**5**, Plasma **7**, Tempo **13** -- **91 real, live-tracked targets
across 6 real deployed oracles**. [`dashboard/index.html`](dashboard/index.html)
now has a Tempo tab with all 13 targets given hand-written narrative
cards (no fallback cards on that tab), on top of the fallback-card
mechanism from the correction above that keeps any future gap like this
one visible instead of silent.
Phase left at `deploy_testnet` in `ecosystems.json`, not advanced to
`maintenance`: that transition needs this pipeline's own independent
maker-checker verification (a distinct `verifier-tempo` identity, the same
discipline actions #70/#72/#73/#74 already followed), which this one-off pass is not positioned to substitute for or fabricate.

**Maintenance, 2026-09-19 (first run in phase `maintenance`)**: rotation audit index 0 (the
validator registry) re-derived from scratch on both mainnet RPCs, identical to the published score,
no correction. Morpho Blue core (`0x10EE9AAC...8f97`, DefiLlama $42.6M on Tempo, the largest Tempo
protocol) added under a new rule R9 and pushed with the other 13 in tx
[`0xe34510ed...029cc6`](https://explore.testnet.tempo.xyz/tx/0xe34510ed23b72647195fc312d0de7156840fa8280de38d029ef50516e6029cc6);
Tempo's `trackedTargetsCount()` now reads **14**. The running totals elsewhere in this file that
say "Tempo 13" were correct when written and are left as dated history; add 1 to any of them for
the current count. See `chains/tempo/data/scored_targets_2026-09-19-morpho-blue.md`.

### Monad -- live since 2026-09-19, a 7th real deployed oracle

[`chains/monad/scorers.py`](chains/monad/scorers.py) -- **9 targets**,
picked as this project's next ecosystem after a dedicated 8-candidate
scouting workflow (Berachain, Monad, Sonic, zkSync Era, Linea, Scroll,
Mantle, ZetaChain) ranked Monad #1 on every weighted criterion at once:
~$1.04B real mainnet DeFi TVL (30-60x every other qualifying candidate,
live-queried from DefiLlama), a confirmed no-account/no-real-value
testnet funding path (`openfaucet.org` lists "Monad / Testnet" directly),
and a structurally confirmed competitor-coverage gap (Monad appears
nowhere in L2Beat's 101 tracked chains -- a standalone parallel-EVM L1,
not an Ethereum-derived L2, the same shape as this project's own Plasma
precedent). The 4 candidates that looked plausible on TVL alone (Mantle,
zkSync Era, Linea, Scroll) were all rejected: each is an L2Beat-tracked
rollup already documented in more admin-key/timelock detail than this
project could add.

| Target | Composite | Authority shape |
|---|---|---|
| Echo Protocol eBTC | 37 | A real, dated May-2026 admin-key exploit (~$76.6M notional minted via a compromised bare EOA) -- since remediated to a real 3-of-4 Safe, both compromised addresses confirmed to no longer hold the role, minting currently paused (no MINTER_ROLE holder) |
| Uniswap v4 PoolManager | 80 | Owned via a Wormhole message relay by Uniswap's own UNI-token-holder-governed Ethereum Timelock, real 2-day delay -- the best-governed target on this chain |
| Monad Native Bridge (Wormhole NTT) | 60 | Governed by a live-verified 13-of-19 Wormhole Guardian quorum, read directly from Monad's own deployed Core Bridge contract |
| Kuru Router + MarginAccount | 43 | A real, actively-used 3-of-5 Safe (70 prior txns), no timelock at all |
| Morpho Vault (Grove x Steakhouse High Yield AUSD) | 60 | curator() and guardian() resolve to the identical 2-of-6 Safe -- no independent veto during the vault's own 14-day cap-change timelock |
| Curve Finance StableSwap Factory | 4 | Admin is a single bare EOA, not even a Safe -- explicitly "deployer as admin until DAO ownership transfer" per Curve's own repo, the weakest authority shape found on any chain this project tracks |
| Curvance Emergency Council | 44 | A 4-of-5 Safe with a proven, actively-exercised zero-delay allocation path running in parallel to a 5-day DAO timelock that never actually gates it -- caught via a decoded on-chain transaction, not just a live permission read |

Funding: real, but genuinely gas-constrained -- Monad testnet's real gas
price is ~100-102 gwei (confirmed live, not assumed) and `openfaucet.org`
caps sessions at 0.05 MON, so this pass took multiple mining-and-claim
cycles across two rate-limit waits (46 and 48 minutes) to fund both the
oracle deploy and the real score push. See
[`chains/monad/deploy/README.md`](chains/monad/deploy/README.md) for the
full funding trail, disclosed rather than smoothed over.

**Real deployment, 2026-09-19**: `AuthorityRiskOracle` =
[`0x50840a7667baEa9D05ad4ae3dCeb384724b58720`](https://testnet.monadvision.com/address/0x50840a7667baEa9D05ad4ae3dCeb384724b58720)
(tx `0x1019fb1be3b2282cb376dcb5eacc39c5a4a8e8da63b97888256b5f98672c40b8`,
block 63,764,900). `updateScores()` tx
[`0xbd9913e225c3a1a1738bc3d5fd5292a7105841d0b091a39c53f029b1e809846b`](https://testnet.monadvision.com/tx/0xbd9913e225c3a1a1738bc3d5fd5292a7105841d0b091a39c53f029b1e809846b)
(7 targets, real push, status success, block 63,775,006). `getScore()`
was read back live for all 7 targets after the push -- every field
matches exactly what was pushed; `trackedTargetsCount()` returns 7.
`ExampleConsumer` was deliberately NOT deployed this pass -- a disclosed
gas-budget cut (0.002 MON remained after the push), not an oversight.

`AuthorityRiskOracle`'s address is identical to every other EVM chain's
own deployed address in this project for the same reason disclosed
above: same shared deployer key, same nonce (0) at deploy time.

This makes **99 real, live-tracked targets across 7 real deployed
oracles** -- re-verified live via a direct `trackedTargetsCount()` read
against all 7 oracles, not recomputed from prose: Robinhood Chain **53**,
Ethereum L1 **9**, Arbitrum **5**, Base **5**, Plasma **7**, Tempo **13**,
Monad **7**. [`dashboard/index.html`](dashboard/index.html) now has a
Monad tab with all 7 targets given hand-written narrative cards (no
fallback cards on that tab), verified live in the browser preview.

**Correction, 2026-09-19 (supersedes every running-total figure above)**:
the rotation audit's own index-11 pass (`Rotation audit (2026-09-19, run
4)` above) took Robinhood Chain's `trackedTargetsCount()` from 53 to 54 by
adding Arcus Perps BridgeVault -- but that addition was never folded into
the two "Correction" tallies earlier in this file (78 across 5 oracles, 91
across 6) or the "99 across 7" figure immediately above, all of which
still say Robinhood Chain 52 or 53. Re-verified live just now, directly
against all 7 oracles' own `trackedTargetsCount()`, not recomputed from
prose: Robinhood Chain **54**, Ethereum L1 **9**, Arbitrum **5**, Base
**5**, Plasma **7**, Tempo **13**, Monad **7** -- **100 real, live-tracked
targets across all 7 real deployed oracles**, matching the hackathon submission text's
own current count exactly (`54+9+5+5+13+7+7`). Flagged here rather than
silently edited into the older figures, same discipline already used
above for the stale "46 real scores" figure.

**Correction, 2026-09-19 (Arbitrum maintenance run, later the same day)**:
Arbitrum's `trackedTargetsCount()` is now **9**, not 5. Four targets were
added (Compound V3, Pendle V2, Fluid, Uniswap V3), and tracked index 0
(GMX V2 RoleStore) was CORRECTED from 71 to 22 after a bare EOA was found
holding `TIMELOCK_ADMIN` on the live RoleStore. See
[`chains/arbitrum-ecosystem/data/rotation_audit_2026-09-19-index0-gmx-rolestore.md`](chains/arbitrum-ecosystem/data/rotation_audit_2026-09-19-index0-gmx-rolestore.md).
Every earlier Arbitrum tally of 5 above describes the state before that run.
The cross-oracle total was not recomputed here: that needs a fresh live
read of the other 6 oracles, which this Arbitrum-scoped run did not do.

### Hyperliquid -- live since 2026-09-20, an 8th real deployed oracle

[`chains/hyperliquid/scorers.py`](chains/hyperliquid/scorers.py) -- **15 targets**: the HyperCore L1
validator set, four HIP-3 perp dexes (xyz, io, para, mkts), four HyperEVM contracts (Kinetiq's two
staking managers, para's vault, Ventuals), the HLP vault, the three Unit treasuries, the legacy
USDC bridge on Arbitrum One and HyperLend. Pushed for real to the same unmodified
`AuthorityRiskOracle.sol` on HyperEVM Testnet (chain 998), at `0x5084...8720`, in one
`updateScores()` transaction (block 64,778,632, 1,502,093 gas), then read back on two RPCs:
15 of 15 equal to the scorer, none stale. Composites run from 4 to 61 (mean 17.9). Most of these
targets are HyperCore-native accounts with no contract VM behind them, so the score describes key
structure, and two dexes are stored under a derived key because their deployer address is also a
scored HyperEVM contract (`chains/hyperliquid/METHODOLOGY.md` 4.7). The first launch aborted before
any transaction because the public RPC's `eth_feeHistory` fails intermittently, and the deploy now
uses legacy fees. Full record: [`chains/hyperliquid/deploy/README.md`](chains/hyperliquid/deploy/README.md).

### Solana -- live since 2026-09-20, a 9th real deployed oracle, and the first native one

[`chains/solana/scorers.py`](chains/solana/scorers.py) -- **18 targets**, of which the **13** below are on-chain today (Jupiter, Kamino, Solend DAO,
Drift, Raydium, marginfi, Meteora, Orca, Marinade, PumpSwap and others), pushed to a **native Anchor
program** on Solana Devnet, not an EVM contract: one `AuthorityScore` account per target plus a
`Registry` account that lists the tracked targets in push order. Program
`5VhiTAGLEViGgajhxPbzdWz7WLUAiRy42DY6qi6tYh4W`, deployed with `--max-len` equal to the `.so` size
(peak cost about 2.21 SOL instead of 3.28), `initialize` and 13 `update_score` back to back.
Read back independently: the program's bytes on Devnet hash to the reproducible build
(sha256 `9ff05f9f...7382f1`) and all 13 scores equal the scorer. Composites run from 2 to 56 (mean
37.4); Solend DAO, Meteora DAMM v2 and Orca Whirlpool sit at 2. Five more targets (Save, the SPL Stake Pool
program, JitoSOL, Sanctum Infinity and the Sanctum LSTs) are scored in `scorers.py` since the evening of
2026-09-20 and wait for a re-push, so the oracle holds 13 while the scorer produces 18. Read it without any key with
[`scripts/solana_oracle_reader.py`](scripts/solana_oracle_reader.py). Full record:
[`chains/solana/deploy/README.md`](chains/solana/deploy/README.md).

### Base maintenance run, 2026-09-19 -- 5 -> 9 tracked targets, 1 CORRECTION

Base's own `trackedTargetsCount()` is now **9** (read live on
`sepolia.base.org` and `base-sepolia-rpc.publicnode.com` after tx
[`0xc412f6dc...14fa1`](https://sepolia.basescan.org/tx/0xc412f6dc76299177db63ab207a9609ae5124215d2ac52ac280e98fa9a1c14fa1),
block 47,033,666). Every "Base **5**" in the dated count snapshots above
was true when written and is left as-is; any cross-ecosystem total quoted
above (e.g. "100 across 7") is now stale by at least +4 on Base's side
alone -- not recomputed here because other ecosystems' counts move
concurrently. New targets: Aerodrome Slipstream CLFactory (46), Uniswap V2
Factory (85), Uniswap V4 PoolManager (85), Moonwell Comptroller (71).
**CORRECTION**: Aerodrome V1 PoolFactory `crossExposureScore` 100 -> 80
(composite unchanged at 46) -- Slipstream's owner/fee managers are the exact
same 3-of-7 Safe, so the tracked set now contains two targets on one key.
Audit rotation index 0 (Morpho Blue) re-derived from zero on 2 Base RPCs:
no divergence. Full detail:
[`chains/base-ecosystem/data/scored_targets_2026-09-19-maintenance.md`](chains/base-ecosystem/data/scored_targets_2026-09-19-maintenance.md).

### Base's Morpho Blue -- a real cross-chain finding on an already-shipped ecosystem, 2026-09-19

Depth work, not more breadth: wiring Monad into
[`scripts/check_cross_ecosystem_overlap.py`](scripts/check_cross_ecosystem_overlap.py)
meant re-running it in full, and its output for groups that had nothing to
do with Monad turned up something real that had been sitting unexamined
for days. Base's Morpho Blue singleton -- **this project's single largest
tracked target, $3.90B TVL** -- has an owner Safe that is byte-identical,
as a signer SET at the identical 5-of-9 threshold, to Robinhood Chain's
own already-tracked Morpho Blue owner Safe (different CREATE2 address,
same 9 people). Both chains had been scoring this `crossExposureScore` as
100 ("no overlap") since each was deployed, which was simply wrong, not
unconfirmed -- the comparison had never actually been run. Full writeup:
[`data/finding_2026-09-19-base-morpho-blue-robinhood-overlap.md`](data/finding_2026-09-19-base-morpho-blue-robinhood-overlap.md).

`chains/base-ecosystem/scorers.py::score_morpho_blue()` now computes this
live and was **re-pushed for real** to Base's already-deployed Sepolia
oracle (tx
[`0x7b7ed211e327dcc7940aea129398a96e36d157066185fe24709c395cda392e62`](https://sepolia.basescan.org/tx/0x7b7ed211e327dcc7940aea129398a96e36d157066185fe24709c395cda392e62),
block 47,028,948) -- `getScore()` read back live confirms
`crossExposureScore=80`, matching exactly what was sent. Robinhood
Chain's own side of this finding was NOT modified (that file is the
pipeline's own continuously-edited, weekly-auto-pushed territory) --
flagged in the finding doc for that side to close in its own pass.
**Update 2026-09-20**: closed in the scorer code. Robinhood Chain's Morpho Blue
singleton group now carries a hand-set, dated `cross_ecosystem` flag and reads
`crossExposureScore` 80 (was 100; pushed on-chain 2026-09-20, Robinhood Chain tx
[`0x020cf83c...4978`](https://explorer.testnet.chain.robinhood.com/tx/0x020cf83c8a007afaef0eadf7ecb271432c80f1ffd9bfafed984ab6eca17c4978),
block 121,858,777), and Ethereum L1's and Tempo's Morpho Blue targets fold the
same 9-signer committee at 80 too, pushed in the same run.

**Correction, 2026-09-19 (Monad 7 -> 9, and a live recount of every oracle)**:
Monad's `trackedTargetsCount()` is now **9**, not 7. Two targets were added
after the tx #1 push described above -- Aave V3 Pool (composite 71) and
Euler V2 eVaultFactory (composite 64) -- and pushed for real in a second
`updateScores()` (tx
[`0xd65b649d...9e35`](https://testnet.monadvision.com/tx/0xd65b649d10c8a1a1b76c6a0848fbbc182c0e73e0fce7e4abeea066da3b529e35),
block 63,945,191, 9 targets, status success). All 9 stored scores were
re-derived independently against live Monad mainnet and matched on all six
fields with zero difference. Every "Monad **7**" / "all 7 targets" above was
true when written and is left as dated history. Live
`trackedTargetsCount()` read directly against all 7 oracles at the time of
this correction (not recomputed from prose): Robinhood Chain **57**,
Ethereum L1 **14**, Arbitrum **9**, Base **9**, Plasma **9**, Tempo **14**,
Monad **9** -- **121 targets across 7 real deployed oracles** (as of
2026-09-19; superseded by the 2026-09-20 correction below). These
counts keep moving because several maintenance runs write to this
repository concurrently; treat any total in this file as a dated snapshot
and re-read the chain (or `dashboard/index.html`, which does) for the
current figure.

**Correction, 2026-09-20 (supersedes the 121 above and every older running
total in this file)**: `trackedTargetsCount()` read live against all 7 oracles at
02:46 CEST, after that morning's re-push, with `python3
scripts/live_target_counts.py` (plain `eth_call`, no key): Robinhood Chain
**58**, Ethereum L1 **15**, Arbitrum **9**, Base **9**, Tempo **14**, Plasma
**9**, Monad **9** -- **123 tracked targets on 7 real deployed oracles**
(58+15+9+9+14+9+9). **122 of them are actively refreshed**: Ethereum L1's index
3 is the retired Ethena minter, which the oracle contract cannot remove, so it
stays tracked as a historical reading and turns stale nine days after its last
update (2026-09-19 16:39 UTC). The script prints the 123; the 122 is that total
minus the retired target. Two things changed since the 121: one target was added
to Robinhood Chain (57 to 58, its own push at testnet block 121,828,009, rotation
audit index 15) and the live Ethena minter was added to Ethereum L1 (14 to 15) by
the re-push described under "Cross-ECOSYSTEM signer overlap". Freshness is a separate
question from the count: every entry turns stale nine days after its last update, and
`python3 scripts/oracle_freshness.py` (plain `eth_call`, no key) prints, per oracle, when its
first entry does (on 2026-09-20: Base 2026-09-28 16:33 UTC, Ethereum L1 2026-09-28 16:39 UTC,
the others 2026-09-29), exiting non-zero when a re-push is due within 48 hours.

**Correction, 2026-09-20 20:41 CEST (supersedes the 123 and every "7 oracles"
figure above)**: Hyperliquid (HyperEVM Testnet, chain 998) and Solana (Devnet, a
native Anchor program) went live that afternoon, see
[`chains/hyperliquid/deploy/README.md`](chains/hyperliquid/deploy/README.md) and
[`chains/solana/deploy/README.md`](chains/solana/deploy/README.md).
`python3 scripts/live_target_counts.py` (plain `eth_call`, plus `getAccountInfo` and
`getProgramAccounts` for Solana, no key) now reads Robinhood Chain **58**, Ethereum L1
**19**, Arbitrum **9**, Base **9**, Tempo **14**, Plasma **9**, Monad **9**, Hyperliquid
**15**, Solana **18** -- **160 tracked targets on 9 real deployed oracles**
(58+19+9+9+14+9+9+15+18), after two pushes that
evening: Ethereum L1 gained four targets (Lido stETH, EigenLayer StrategyManager, Curve
Stableswap-NG factory, Rocket Pool RocketStorage; maker-checker proposal, tx
`0xc4873381...ba46`, Sepolia block 11,745,959, read back identical to the scorer) and
Solana went from 13 to 18 (read back identical). **159 of them are actively refreshed**: the retired Ethena
minter (Ethereum L1, index 3) is still the one tracked target nobody refreshes. Zcash is
the tenth ecosystem: it has no oracle contract, its latest on-chain commitment covers its 6 live
targets (7 in the two earlier ones), so it is not part of the 160. `scripts/oracle_freshness.py` now reads Hyperliquid
and Solana too (first entries turn stale between 2026-09-28 16:33 UTC, Base, and
2026-09-29 18:35 UTC, Solana), and `dashboard/index.html` has a tab for each.

**Update 2026-09-20 22:01 CEST, after the evening re-push of all nine oracles** (record:
`data/repush_2026-09-20-evening-all-oracles.md`): `python3 scripts/live_target_counts.py` now reads Robinhood Chain
**62**, Ethereum L1 **20**, Arbitrum **10**, Base **9**, Tempo **14**, Plasma **9**, Monad **9**, Hyperliquid **15**,
Solana **18** -- **166 tracked targets on 9 oracles, 165 of them actively refreshed** (62+20+10+9+14+9+9+15+18). The
re-push carried five targets scored and merged earlier but not yet on-chain (Robinhood four, Ethereum L1's Aave V3
Horizon, Arbitrum's GMX V1 Vault). Every refreshed entry now dates from 2026-09-20 19:38 to 19:59 UTC, so the first
turn stale on 2026-09-29; the retired Ethena minter still expires on 2026-09-28 16:39 UTC. The 160 above is the figure
before that run.
 To keep every entry fresh, `bash scripts/repush_all_oracles.sh`
re-pushes all nine oracles in one run (`DRY=1` recomputes and encodes without reading a key or sending;
`ONLY="base plasma"` limits it; a real run reads the updater keys and is for the maintainer only) and prints
the freshness table before and after.

**Deployed oracles at a glance, 2026-09-20 20:41 CEST** (addresses from each ecosystem's
own deploy record, counts read live with `python3 scripts/live_target_counts.py`):

| Ecosystem | Network | Oracle | Targets |
|---|---|---|---|
| Robinhood Chain | Testnet, chain 46630 | [`0x9BF4...7f52`](https://explorer.testnet.chain.robinhood.com/address/0x9BF45734D09bC7CA39238e767B2af9AAc62a7f52) | 58 |
| Ethereum L1 | Sepolia, chain 11155111 | [`0xB6F8...f906`](https://sepolia.etherscan.io/address/0xB6F8474ccC71AF477c31c2DF663B3942ddfbf906) | 19 |
| Arbitrum | Sepolia, chain 421614 | [`0x5084...8720`](https://sepolia.arbiscan.io/address/0x50840a7667baEa9D05ad4ae3dCeb384724b58720) | 9 |
| Base | Sepolia, chain 84532 | [`0x5084...8720`](https://sepolia.basescan.org/address/0x50840a7667baEa9D05ad4ae3dCeb384724b58720) | 9 |
| Tempo | Moderato, chain 42431 | [`0x5084...8720`](https://explore.testnet.tempo.xyz/address/0x50840a7667baEa9D05ad4ae3dCeb384724b58720) | 14 |
| Plasma | Testnet, chain 9746 | [`0x5084...8720`](https://testnet.plasmascan.to/address/0x50840a7667baEa9D05ad4ae3dCeb384724b58720) | 9 |
| Monad | Testnet, chain 10143 | [`0x5084...8720`](https://testnet.monadvision.com/address/0x50840a7667baEa9D05ad4ae3dCeb384724b58720) | 9 |
| **Hyperliquid** | HyperEVM Testnet, chain 998 | `0x5084...8720` (no public explorer is listed for this network) | 15 |
| **Solana** | Devnet, native Anchor program | [`5VhiTA...Yh4W`](https://explorer.solana.com/address/5VhiTAGLEViGgajhxPbzdWz7WLUAiRy42DY6qi6tYh4W?cluster=devnet) (Registry PDA `CDHtBT...ZBEib`) | 18 |
| Zcash | Testnet, no contract | latest OP_RETURN commitment, [`462de12b...701c`](https://testnet.cipherscan.app/tx/462de12bf72e5e635a1feed4a4cedb02c03f17745bd15176787f8f5f8fcd701c) | 6 live (not in the total) |

The seven EVM oracles at `0x5084...8720` are one address by construction: a CREATE address
is `keccak(deployer, nonce)`, and the same shared deployer key was at nonce 0 on each chain.
Robinhood Chain and Ethereum L1 have their own addresses. 160 targets on the 9 oracles.

**Score update, 2026-09-20 (Monad's Aave V3 Pool, pushed on-chain)**: the
Aave V3 Pool target added above (composite 71 on-chain until then) now scores
65/75/0/100/80/49, on-chain since Monad tx
[`0xa9359630...a019`](https://testnet.monadvision.com/tx/0xa93596300b689383572880cd4de76ee2fc7bce68ac5791db38501b07b987a019)
(block 64,022,942, read back). Its `PROTOCOL_GUARDIAN` Safe (4-of-7, read live) also holds
`POOL_ADMIN` in the ACLManager, so it can swap a reserve's aToken or debt-token
implementation with no delay; the 1-day Executor delay does not bind it. The
scorer therefore uses the Safe-with-no-timelock rule (multisig `min(100,
4*15+3*5)` = 75, timelock 0). `crossExposureScore` stays 80. The Monad oracle no
longer holds the old 71. Found by the 2026-09-20 role sweep
(`data/finding_2026-09-20-unscored-role-sweep.md`); values and verification in
`data/finding_2026-09-20-cross-exposure-convention-and-score-adjustments.md`.

