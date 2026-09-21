# Solana: authority-risk methodology (discovery draft)

Status: **promoted to a real scorer 2026-09-17.** Discovery output 2026-09-16, revised by
the methodology test of the same day. This document establishes the real authority primitives
of Solana from primary sources and maps the project's five score dimensions onto them. The
grid was applied end to end to Jupiter Aggregator v6 and Kamino Lend in
[`data/methodology_test_2026-09-16.md`](data/methodology_test_2026-09-16.md); the gaps that
test exposed are fixed below and listed in the changelog at the end. Section 6.1's formulas
are now live code in [`scorers.py`](scorers.py) (`score_jupiter_aggregator_v6`,
`score_kamino_lend`) -- see
[`data/scored_targets_2026-09-17.md`](data/scored_targets_2026-09-17.md) for the live-verified
numbers, which match this document's hand-derived methodology test exactly. Nothing has been
pushed on-chain yet (no devnet oracle deployed for Solana).

Every on-chain fact below was read from Solana Mainnet Beta with the read-only helper
[`scripts/sol_read.py`](scripts/sol_read.py) (plain JSON-RPC, no keys, no signing) and
re-read against a second, independent RPC (`https://solana-rpc.publicnode.com`) unless
noted. Mainnet slot at time of reading: about 447,574,545.

## 1. Why the EVM vocabulary does not map one-to-one

| EVM concept | Solana reality | Source |
|---|---|---|
| Contract with code and storage | A **program** is a stateless executable account. All mutable state lives in separate data accounts that the program owns. | [solana.com/docs/core/programs](https://solana.com/docs/core/programs) |
| `owner()` / `Ownable` | Two different things: (a) the **upgrade authority** of the program itself, stored by the loader; (b) any **authority field** a program writes into its own data accounts (e.g. `mint_authority`). Runtime rule: only an account's owner program can modify its data. | [solana.com/docs/core/accounts](https://solana.com/docs/core/accounts) |
| Proxy + `upgradeTo` | Native: a loader-v3 program is upgradeable by design while its upgrade authority is set. No proxy needed. | [solana.com/docs/core/programs/program-deployment](https://solana.com/docs/core/programs/program-deployment) |
| EOA vs contract account | **On-curve key** (an Ed25519 point, a private key can exist) vs **PDA** (off-curve, no private key exists, only the deriving program can sign through `invoke_signed`). | [solana.com/docs/core/pda](https://solana.com/docs/core/pda), [solana.com/docs/core/cpi](https://solana.com/docs/core/cpi) |
| Gnosis Safe | Not a chain primitive. Multisig is either the SPL Token native multisig (token authorities only) or a program such as Squads (v3 or v4) whose PDA "vault" holds the authority. | sections 3.4 and 3.5 |
| `TimelockController` | **No protocol-level upgrade delay exists.** Delay only exists if the authority is a program that enforces one (Squads v4 `time_lock`, SPL Governance `transactions_hold_up_time`). | sections 3.1, 3.4 and 3.6 |
| Chain id | Solana has no numeric chain id. A cluster is identified by its **genesis hash**. | section 2 |

The consequence for scoring: the "admin key" of a Solana target is almost always a
**32-byte public key whose nature must be resolved** (on-curve wallet, PDA of a multisig
program, PDA of a governance program, or `None`). The classification step is therefore
the heart of the Solana scorer, exactly like `classify_holder()` is on EVM.

## 2. Networks (confirmed by direct RPC read)

| Cluster | Public endpoint | Genesis hash (the cluster identifier) | Use in this project |
|---|---|---|---|
| Mainnet Beta | `https://api.mainnet-beta.solana.com` (also `https://api.mainnet.solana.com`) | `5eykt4UsFv8P8NJdTREpY1vzqKqZKvdpKuc147dw2N9d` | read-only scoring |
| Devnet | `https://api.devnet.solana.com` | `EtWTRABZaYq6iMfeYKouRu166VU2xqa1wcaWoxPkrZBG` | oracle deployment target |
| Testnet | `https://api.testnet.solana.com` | `4uhcVJyU9pJkvQyS88uRDiswHXSCkY3zQawwpjk2NsNY` | validator stress testing, not used |

Endpoints and purposes: [solana.com/docs/references/clusters](https://solana.com/docs/references/clusters).
Genesis hashes: `getGenesisHash` on each endpoint (see claims log). The official public
endpoints are documented as rate-limited, so a scorer must throttle and retry.

Loader difference between clusters: `LoaderV411111111111111111111111111111111111`
exists as an executable builtin on Devnet and Testnet but **does not exist on Mainnet
Beta** (`getAccountInfo` returns `null`). Mainnet programs are therefore loader-v3
(or legacy) today; loader-v4 must still be handled by the scorer for forward compatibility.

## 3. Authority primitives

### 3.1 Program upgrade authority (loader-v3, BPF Loader Upgradeable)

- Loader address `BPFLoaderUpgradeab1e11111111111111111111111`, owner of all newly
  deployed programs ([program-deployment docs, "Loader programs" table](https://solana.com/docs/core/programs/program-deployment);
  [sdk-ids/src/lib.rs](https://github.com/anza-xyz/solana-sdk/blob/master/sdk-ids/src/lib.rs)).
- A program is a pair: `Program { programdata_address }` and
  `ProgramData { slot, upgrade_authority_address: Option<Pubkey> }`
  ([loader-v3-interface/src/state.rs](https://github.com/anza-xyz/solana-sdk/blob/master/loader-v3-interface/src/state.rs)).
  The ProgramData address is the PDA of `[program_id]` under the loader
  ([loader-v3-interface/src/instruction.rs](https://github.com/anza-xyz/solana-sdk/blob/master/loader-v3-interface/src/instruction.rs)).
- Byte layout used by the scorer: ProgramData tag `u32 = 3` at offset 0, `slot u64` at 4,
  `Option` flag at 12, authority pubkey at 13..45.
- `Upgrade` only checks that the ProgramData authority matches and is not `None`; there
  is no delay parameter. `SetAuthority` to `None` makes the program immutable forever.
  `Close` on ProgramData removes the program. Source: the instruction table in the
  program-deployment docs, cross-checked against `instruction.rs` ("A program can be
  updated as long as the program's authority has not been set to `None`").
- Legacy loaders `BPFLoader1111...` and `BPFLoader2111...` are non-upgradeable
  ("loader management disabled", same docs table).

Direct reads (Mainnet, both RPCs agree):

| Program | Loader | Upgrade authority | Authority resolves to |
|---|---|---|---|
| Squads v4 `SQDS4ep65T869zMMBKyuUq6aD6EgTu8psMjkvj52pCf` | loader-v3 | `None` (immutable) | n/a |
| SPL Token `TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA` | loader-v3 | `None` (immutable) | n/a |
| Token-2022 `TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb` | loader-v3 | `AeLmXCbPaQHGWRLr2saFsEVfmMNuKnxRAbWCT9P5twgz` | PDA, authority index 1 of Squads v3 multisig `BnD53519LK7QM4ERBGvLedZDe1VoTPgtiBkGPWAACiMZ`, **4-of-6**, no time lock |
| SPL Governance `GovER5Lthms3bLBqWub97yVrMmEogzX7xNjdXpPPCVZw` | loader-v3 | `HF7gCq7BMB6cFfhharTGGm31sqDdpmvLTgF4WEoW8y9n` | PDA (off-curve, system-owned); controlling program not yet identified |
| Pyth Solana Receiver `rec5EKMGg6MxZYaMdyBfgwp4d5rB9T1VQH5pJv5LtFJ` | loader-v3 | `6oXTdojyfDS8m5VtTaYB9xRCxpKGSvKJFndLUPV3V3wT` | PDA; last upgrade executed through program `SMPLVC8MxZ5Bf5EfF7PaMiTCxoBAcmkbM2vkrvMK8ho` (not a published Squads v3 id, identity still open) |

Note on SPL Token: it is currently owned by loader-v3 with no authority (last deploy slot
419,472,000), which differs from the historical loader-v2 deployment. The scorer must read
the owner rather than assume it from documentation.

Mainnet ID of SPL Governance comes from the program README
([governance/README.md](https://github.com/Mythic-Project/solana-program-library/blob/master/governance/README.md)).
The Token-2022 chain above was confirmed three ways: (1) ProgramData read, (2) the last
upgrade transaction (`2cM3S25AJnHyy4shW7zsoqz5W8JPXPvXiUxk545n5ANf6BET9VvBRfsnSNYi9MqogjVWNBxNfaZpE9QBJX4XCbfn`) invokes Squads v3 `SMPLecH534NA9acpos4G6x7uf3LWbCAwZQE9e8ZekMu`
which CPIs `BPFLoaderUpgradeable::Upgrade`, (3) offline derivation of the Squads v3
authority PDA `["squad", ms, u32 index, "authority"]` (seeds from
[squads-mpl lib.rs](https://github.com/Squads-Protocol/squads-mpl/blob/main/programs/squads-mpl/src/lib.rs))
reproduces `AeLm...` exactly for index 1.

### 3.2 Loader-v4 (future mainnet)

`LoaderV4State { slot, authority_address_or_next_version, status }`, with status
`Retracted` (maintenance, not executable), `Deployed`, or `Finalized` (can no longer be
retracted, authority field becomes a forward pointer)
([loader-v4-interface state.rs, v3.1.0](https://github.com/anza-xyz/solana-sdk/blob/loader-v4-interface%40v3.1.0/loader-v4-interface/src/state.rs)).
Scoring treatment: `Finalized` equals loader-v3 `None`; otherwise the authority is scored
like a loader-v3 upgrade authority. `Retracted` is an availability risk in its own right.

### 3.3 Key classification: on-curve vs PDA

- A PDA is guaranteed off the Ed25519 curve, so no private key exists; only the program
  whose id was used in the derivation can sign for it
  ([solana.com/docs/core/pda](https://solana.com/docs/core/pda)).
- The helper implements the Ed25519 decompression test and `find_program_address`
  (SHA-256 of seeds, bump, program id, `"ProgramDerivedAddress"`). Self-check: it
  reproduces the on-chain ProgramData addresses of Squads v4 (bump 255), Token-2022
  (bump 255) and Pyth Receiver (bump **254**, which proves the on-curve branch rejects a
  real on-curve candidate at 255).
- Classification ladder for any authority key K:
  1. `None` / `Finalized`: immutable.
  2. K on-curve: a single private key (hot wallet, hardware wallet or MPC, undistinguishable on-chain). Worst case.
  3. K off-curve and equals a derived vault/authority PDA of a known multisig program (Squads v4, Squads v3): read that multisig.
     Resolution procedure: take the most recent successful transaction that used K
     (`getSignaturesForAddress`, then `getTransaction`); the top-level instruction names the
     multisig program and its first account is the multisig. Read it, then **re-derive** the
     vault (v4 `["multisig", ms, "vault", u8 i]`) or authority (v3 `["squad", ms, u32 i, "authority"]`)
     PDA offline and require an exact match with K. A transaction alone is not proof.
  4. K off-curve and derived from a governance program (SPL Governance native treasury or governance account): read the governance config.
  5. K off-curve, controller not identified: treat as unknown program control, never as safe by default.
  6. K is an SPL Token `Multisig` account (owner Token program, size 355): token-authority multisig only (section 3.5).

### 3.4 Multisig programs

**Squads v4** (`SQDS4ep65T869zMMBKyuUq6aD6EgTu8psMjkvj52pCf`, immutable, see 3.1)
([state/multisig.rs](https://github.com/Squads-Protocol/v4/blob/main/programs/squads_multisig_program/src/state/multisig.rs)):

- `Multisig { create_key, config_authority, threshold: u16, time_lock: u32, transaction_index, stale_transaction_index, rent_collector: Option, bump, members: Vec<Member{key, permissions mask}> }`.
- Permissions bitmask: Initiate = 1, Vote = 2, Execute = 4. Threshold counts **voters**, so
  a real quorum is `threshold` over members with the Vote bit, not over all members.
- `time_lock`: seconds between approval and execution, capped at `MAX_TIME_LOCK` = 3 months;
  enforced in both `vault_transaction_execute` and `config_transaction_execute`.
- Authority PDA ("vault"): `["multisig", multisig, "vault", u8 index]`
  ([vault_transaction_execute.rs](https://github.com/Squads-Protocol/v4/blob/main/programs/squads_multisig_program/src/instructions/vault_transaction_execute.rs)).
- **Bypass paths that must lower the score:**
  - `config_authority != Pubkey::default()` ("controlled multisig"): that single key can
    add or remove members, change threshold and set `time_lock` directly through
    `multisig_config.rs`, with no vote and no delay.
  - `SpendingLimit` accounts: listed members (not necessarily multisig members) can move
    up to `amount` per period out of a vault without a proposal or time lock
    ([state/spending_limit.rs](https://github.com/Squads-Protocol/v4/blob/main/programs/squads_multisig_program/src/state/spending_limit.rs)).
    Relevant when the vault holds funds, not for upgrade authority itself.
- Direct read of two live v4 multisigs showed both shapes that matter: `FzzZT2db...xd4A`
  is 2-of-3 with `time_lock = 0`; `7mHZpMXU...ybtc` is **1-of-1** with `time_lock = 300`.
  Being "a Squads multisig" alone therefore says nothing about strength.

**Squads v3 / squads-mpl** (`SMPLecH534NA9acpos4G6x7uf3LWbCAwZQE9e8ZekMu`, immutable on Mainnet)
([state.rs](https://github.com/Squads-Protocol/squads-mpl/blob/main/programs/squads-mpl/src/state.rs)):
`Ms { threshold, authority_index, transaction_index, ms_change_index, bump, create_key, allow_external_execute, keys }`.
**No time-lock field exists**, so any v3-controlled authority has timelock score 0.

### 3.5 SPL Token authorities (asset-level admin keys)

- `Mint { mint_authority: COption, supply, decimals, is_initialized, freeze_authority: COption }`
  ([token interface state.rs](https://github.com/solana-program/token/blob/main/interface/src/state.rs)).
  `mint_authority = None` means fixed supply; `freeze_authority` can freeze any holder account.
- Native `Multisig { m, n, is_initialized, signers[11] }`, `MIN_SIGNERS = 1`, `MAX_SIGNERS = 11`
  ([instruction.rs](https://github.com/solana-program/token/blob/main/interface/src/instruction.rs)). No delay.
- Token-2022 adds more authority-bearing extensions, each a separate admin key to score
  ([extension directory](https://github.com/solana-program/token-2022/tree/main/interface/src/extension)):
  `PermanentDelegate.delegate` (can transfer or burn from any holder),
  `TransferHook.authority` + `program_id` (can reroute transfer validation to arbitrary code),
  `Pausable.authority`, `MintCloseAuthority.close_authority`, transfer-fee and
  default-account-state configuration authorities.
- Direct read: USDC mint `EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v` has
  `mint_authority = BJE5MMbq...5ruG`, an SPL Token native multisig **2-of-4**, and
  `freeze_authority = 7dGbd2QZcCKcTndnHcTL8q7SMVXAkp688NTQYwrRCrar`, also an SPL Token multisig account (size 355).

### 3.6 Governance with delay

**SPL Governance / Realms** (`GovER5Lthms3bLBqWub97yVrMmEogzX7xNjdXpPPCVZw` default mainnet instance)
([state/governance.rs](https://github.com/Mythic-Project/solana-program-library/blob/master/governance/program/src/state/governance.rs)):
`GovernanceConfig` holds `community_vote_threshold`, `council_vote_threshold`,
`council_veto_vote_threshold`, `voting_base_time`, `voting_cool_off_time`, and
`transactions_hold_up_time` ("the wait time in seconds before transactions can be executed
after proposal is successfully voted on"). This is the closest Solana equivalent of a
`TimelockController` delay. Note the default instance itself is upgradeable by a PDA
(section 3.1), so a DAO on the shared instance inherits that authority as a dependency.

**Not every Realms DAO uses the shared default instance.** Solend DAO
(`chains/solana/data/methodology_test_2026-09-17-solend-governance.md`) deploys its own,
separate governance program (`A7kmu2kUcnQwAVn8B4znQmGJeUrsJ1WEhYVMtmiBLkEr`) -- confirmed only
after a first-pass web search wrongly assumed the shared instance, then a live
`getProgramAccounts` query against that shared instance for a Realm matching Solend's
`community_mint` returned zero results. Always confirm the governance program per-DAO (Realms'
own certified registry, `Mythic-Project/governance-ui`'s `public/realms/mainnet-beta.json`, is
the fastest primary source) rather than assuming the default. A Realm's own `authority` field
(`state/realm.rs`, distinct from any Governance account under it) is a further, separate
full-power path -- see 6.2 and the 2026-09-17 changelog entry.

### 3.7 Switchboard On-Demand

CLOSED 2026-09-19 (was section 7's "Add Switchboard On-Demand oracle authority
primitives"). Program id `SBondMDrcV3K4kxZR1HNVT7osZxAHVHgYXL5Ze1oMUv` on Mainnet
Beta -- confirmed against the OFFICIAL SDK source (`switchboard-xyz/switchboard-sdk`
`src/utils/index.ts`'s own `ON_DEMAND_MAINNET_PID` export), NOT trusted from memory:
a first recalled guess for this id was wrong in four characters (a plausible-looking
but fabricated base58 string) and was caught only because it was checked against the
primary source before use. The default mainnet oracle queue is
`A43DyUGA7s8eXPxqEjJY6EBu1KKbNgfxF8h17VAHn13w` (same source's `ON_DEMAND_MAINNET_QUEUE`).

Two account types matter for authority, both `#[repr(C)]` bytemuck `Pod` structs
prefixed by an 8-byte discriminator that is NOT part of the Rust struct itself (source:
the same SDK's `solana/rust/switchboard-on-demand-client/src/accounts/{pull_feed,queue}.rs`,
cross-checked byte-identical against the mirrored `switchboard-on-demand` crate copy):

- **`PullFeedAccountData`** (one per price feed): `submissions: [OracleSubmission; 32]`
  (2048 bytes) then `authority: Pubkey`, `queue: Pubkey`, `feed_hash: [u8; 32]`, ...
  `authority` can rewrite `feed_hash` -- i.e. redefine the ENTIRE job schema/computation
  that produces this feed's price -- with no quorum and no delay of its own, the
  Switchboard analogue of Kamino Scope's `Configuration.admin` (6.3) switching a price
  entry to `FixedPrice`. `queue` names which queue's oracles must sign an update for the
  feed to accept it.
- **`QueueAccountData`** (one per queue, shared across every feed bound to it):
  `authority: Pubkey` is the FIRST field (struct offset 0) -- "the address of the
  authority which is permitted to add/remove allowed enclave measurements", i.e. which
  oracle operators may serve on this queue at all, the Switchboard analogue of Pyth's
  `governance_authority` controlling `valid_data_sources` (section 4's Pyth row).

Live-read example (2 independent RPCs, `api.mainnet-beta.solana.com` and
`solana-rpc.publicnode.com`, byte-identical both times): Drift Protocol's AI16Z spot
market (already scanned by `score_drift_protocol`, section 6) reads its price from feed
`BHqLyA9ov1VPNzt8eb5bt75X2Vk1EVKw1d9Qa78Gk5tR`, a live `PullFeedAccountData` owned by the
program above (confirmed by `getProgramAccounts`-scanning all 66 live Drift `SpotMarket`
accounts for an `oracle` field owned by this program id -- 16 of 66 match; a check of
Drift's OWN published SDK constant, `sdk/src/constants/perpMarkets.ts`'s declared
Switchboard-On-Demand perp market, W-PERP, found that constant file STALE: the live
`amm.oracle` for that market no longer matches, migrated to PythLazer since). That feed's
`authority` is a bare on-curve EOA (`JCHodRTYqK6G5VjqbyD75JNuTFy8o1mFT7j95EXcy7q6`); its
`queue` is the official default mainnet queue above, whose `authority` --
`DREcTwxxuehtUVgnGwDpTcKT9zTK5uDmdLbnRY7cijEx` -- is ALSO, independently, the On-Demand
program's OWN loader-v3 upgrade authority (byte-identical on both RPCs): one Squads v4
vault PDA controls both "who may upgrade the whole oracle system's code" and "who may
change which oracles are allowed to answer for the default queue". Resolved (transaction
trace + offline vault-0 PDA re-derivation, required exact match, same discipline as 3.3's
ladder rung 3) to multisig `93RQfY6VHRkqXBCEhMY5u92bCGp428DTzqZUEA2Hjr9h`: 3-of-8, all 8
members hold full Initiate|Vote|Execute permissions, autonomous `config_authority`,
`time_lock = 0`.

Scoring (6.3's "provider behind an aggregator" pattern, adapted -- Switchboard here is a
direct provider, not an aggregator over a further provider): `oracleAuthorityScore` = min
over each of the three paths' own standalone composite (feed `authority`; queue
`authority`; program upgrade authority), using the EXISTING, already-calibrated
`on_curve`/`squads_v4` formulas from 6.1 -- no new curve. For the AI16Z example: feed
authority (on-curve) composite 2 dominates queue/program authority (Squads v4 3-of-8,
zero delay) composite 38 -- the same "one undelayed bare-key path caps the whole
dimension" shape 6.3's Kamino Scope-admin path already demonstrated. Code:
`chains/solana/scorers.py::score_drift_protocol`, decoders in
`chains/solana/scripts/sol_read.py::read_switchboard_pull_feed`/`read_switchboard_queue`.

Not scored (disclosed, not folded into a number): whether the other 15 live
Switchboard-On-Demand-sourced Drift spot markets share the same feed `authority` or use
distinct ones (would matter for `crossExposureScore` if shared -- not checked this pass),
and every Drift market sourced from Pyth/PythLazer instead (a separate, still-open
provider-authority surface this pass did not touch).

## 4. The five dimensions translated

| Dimension (oracle field) | Applies on Solana? | What is actually read | Primary source |
|---|---|---|---|
| `adminKeyScore` | Yes | Program upgrade authority (loader-v3 ProgramData or loader-v4 state) **and** privileged authority fields inside the protocol's own config accounts (Anchor `admin`/`authority` fields, token `mint_authority`/`freeze_authority`, Token-2022 extension authorities). Classified with the ladder in 3.3. | 3.1, 3.2, 3.3, 3.5 |
| `multisigScore` | Yes, but program-defined | Squads v4: `threshold` over members with Vote permission, `config_authority` default or not. Squads v3: `threshold`/`keys`. SPL Token multisig: `m`/`n`. Council-controlled Realms: council vote threshold. On-curve key = no multisig. | 3.4, 3.5, 3.6 |
| `timelockScore` | Only through programs | There is no chain-level timelock on upgrades. Delay = Squads v4 `time_lock`, or Realms `transactions_hold_up_time` (+ voting time). Squads v3 and SPL Token multisigs have none. Any bypass (controlled `config_authority`, a second authority path without delay) caps the score like the EVM `cutUpgradeNoticePeriod` case. | 3.1, 3.4, 3.6 |
| `oracleAuthorityScore` | Yes, where the protocol consumes a price | Pyth pull oracle: receiver `Config.governance_authority` (who can change accepted data sources and the Wormhole program), `valid_data_sources`, `minimum_signatures`, and the consumer's accepted `VerificationLevel` (`Full` vs `Partial{num_signatures}`). Wormhole guardian quorum is 13-of-19. Switchboard On-Demand: `PullFeedAccountData.authority` (per-feed, can rewrite `feed_hash`) and the bound `QueueAccountData.authority` (which oracles may serve), plus the On-Demand program's own upgrade authority -- see 3.7. For a consumer that reads prices through an aggregator (for example Kamino Scope), see 6.3. | Pyth [config.rs](https://github.com/pyth-network/pyth-crosschain/blob/main/target_chains/solana/pyth_solana_receiver_sdk/src/config.rs), [price_update.rs](https://github.com/pyth-network/pyth-crosschain/blob/main/target_chains/solana/pyth_solana_receiver_sdk/src/price_update.rs), [Pyth Solana integration docs](https://docs.pyth.network/price-feeds/core/use-real-time-data/pull-integration/solana), [Wormhole guardians](https://wormhole.com/docs/protocol/infrastructure/guardians/), 3.7 for Switchboard On-Demand |
| `crossExposureScore` | Yes | Same formula as the rest of the repo (`scripts/lib/signer_overlap.py`): `max(0, 100 - 20 x sharedGroupCount)`, where a group is one tracked protocol and its root signers are the on-curve member keys of every multisig resolved for it. Key reuse between multisigs of the same protocol does not count. The reverse lookup of every ProgramData sharing one upgrade authority (`getProgramAccounts` on the loader, `memcmp` tag 3 at offset 0 and the authority at offset 13) is published as a blast-radius note, not as a score input. | 3.1 layout, direct read below |

Direct reads for oracle authority and cross-exposure (Mainnet):

- Pyth Receiver Config PDA `DaWUKXCyXsnzcvLUyeJRWou8KTn7XtadgTsdhJ6RHS7b` (seed `"config"`):
  `governance_authority = 6oXTdojy...V3wT` (same PDA that holds the receiver's upgrade
  authority), `wormhole = HDwcJBJX...SWWaQ`, one valid data source (Wormhole chain 26, Pythnet),
  `minimum_signatures = 3`. The Pyth SDK itself warns that partially verified updates lower
  the number of guardians that must collude. Both RPCs agree.
- Blast radius (note, see the corrected `crossExposureScore` row): the Pyth authority
  `6oXT...V3wT` is the upgrade authority of **14** ProgramData accounts; the Token-2022
  authority `AeLm...twgz` controls **3**. The public `publicnode` RPC refuses this indexed
  query without a token, and `api.mainnet.solana.com` is the same operator as
  `api.mainnet-beta`, so neither is an independent second source. The independent indexed
  endpoint used since the methodology test is `https://public.rpc.solanavibestation.com`.

## 5. "Smart contract deployable" on Solana

Yes. Programs are deployed with `solana program deploy` or `anchor deploy` into loader-v3
(Mainnet) and loader-v3 or loader-v4 (Devnet/Testnet)
([program-deployment docs](https://solana.com/docs/core/programs/program-deployment)).
For the native oracle this means:

- The oracle program's own upgrade authority becomes a scored fact about the oracle itself.
  Deploying and then setting it to a Squads v4 vault with a non-zero `time_lock`, or
  finalizing it, is the only consistent choice.
- Scores are stored in PDAs of the oracle program (for example seeds `["score", target_program_id]`),
  and a consumer program reads them by account, not by CPI call.
- `UPDATER_ROLE` becomes an `updater` pubkey field in a config PDA, itself classified with ladder 3.3.

## 6. Score bands and formulas

Aligned with the repo convention (0-100, higher is safer, 100 when not applicable).

| Finding | admin | multisig | timelock |
|---|---|---|---|
| Upgrade authority `None` or loader-v4 `Finalized` | 100 | 100 | 100 |
| On-curve key | 0-10 | 0 | 0 |
| Squads v3, t-of-n | 40-60 by t and n | by t/n | 0 |
| Squads v4 autonomous (`config_authority` default), `time_lock = 0` | 40-60 | by voters and threshold | 0-10 |
| Squads v4 autonomous, `time_lock >= 24h`, no other authority path | 60-80 | by voters and threshold | 50-80 by delay |
| Squads v4 controlled (`config_authority` set) | score as the `config_authority` key | capped by that key | capped at 15 |
| Realms governance (community or council token vote) | 70 flat for token voting, or by council/community threshold when countable | 70 flat for token voting, or by council/community threshold when countable (same formula as Squads, calibrated 2026-09-17) | 0-80 by hold-up time ALONE (`transactions_hold_up_time`, the true Squads-`time_lock` equivalent; `voting_base_time`/`voting_cool_off_time` are disclosed but do not feed this score -- RECONCILED 2026-09-19, see section 7) |
| Off-curve PDA, controller not identified | 20 | 0 until resolved | 0 until resolved |

A Squads multisig (v3 or v4) or SPL Token multisig with a threshold of 1 scores as an
on-curve key, whatever its member count or time lock.

### 6.1 Deterministic formulas (methodology phase)

The bands above are the envelope; these formulas pick the number inside it. `t` = threshold,
`voters` = members with the Vote permission (all keys for Squads v3 and SPL multisigs),
`d` = delay in hours.

| Holder of a full-power path | adminKey | multisig | timelock |
|---|---|---|---|
| `None` / `Finalized` | 100 | 100 | 100 |
| On-curve key, or any multisig with t = 1 | 5 | 0 | 0 |
| Off-curve, controller not identified | 20 | 0 | 0 |
| Squads v3, or Squads v4 autonomous with `time_lock = 0`, **or a legacy "serum-style" multisig** (`owners`/`threshold`/`nonce`/`owner_set_seqno`, no timelock field at all -- gap H1, closed 2026-09-18: reuses this row unchanged, since the shape (fixed threshold-of-members, zero enforced delay) is formula-identical, not because the programs are related) | 40 + min(20, 5 (t-1)) | min(100, round(15 t + 40 t / voters)) | 0 |
| Squads v4 autonomous, 0 < d < 24 | 50 + min(20, 5 (t-1)) | same | round(50 d / 24) |
| Squads v4 autonomous, d >= 24 | 60 + min(20, 5 (t-1)) | same | 50 + min(30, 10 (d/24 - 1)), capped at 80 |
| Squads v4 controlled (`config_authority` set) | score of the `config_authority` holder | capped by that holder | min(15, value above) |
| Realms governance -- validated 2026-09-17 (Solend DAO for the token-voting, no-council-mint case; the SPL Governance shared instance's own controlling council, section 7, for the countable council-threshold case); adminKey/multisig are flat/threshold constants that do NOT vary with voting/hold-up time -- see section 7 for the still-open "derive the flat 70" point | 60 + min(30, 5 (t-1)) where t is the council or community threshold in signers when countable, otherwise a flat 70 (derivation attempt in section 7 -- not yet closed) | min(100, round(15 t + 40 t / voters)) when countable (the same Squads formula, calibrated against a real 5-of-7 council, section 7) -- otherwise a flat 70 for token voting | RECONCILED 2026-09-19 (section 7): `_delay_timelock_score(holdup_hours)`, the SAME function the Squads v4 rows above use, applied to `transactions_hold_up_time` ALONE -- `voting_base_time`/`voting_cool_off_time` are disclosed by callers but do NOT feed this score (spl-governance's own source distinguishes "before transactions can be executed after proposal is successfully voted on" [hold-up, post-decision] from "the base voting time ... open for voting" [voting/cool-off, still decision-forming, no Squads-side analogue scored anywhere in this file]) |

Composite, as elsewhere in the repo: `floor(0.4 adminKey + 0.3 multisig + 0.3 timelock + 0.5)`.
`oracleAuthorityScore` and `crossExposureScore` are published next to it, not folded in.

### 6.2 Several authorities per target

A real protocol has more than one privileged key (Kamino Lend has seven). Each authority
path is classified from the program source before scoring:

| Class | Definition | Used in |
|---|---|---|
| full-power | can replace code, move or re-value user funds, or change risk parameters (LTV, liquidation, price source) | min over these paths for adminKey, multisig and timelock |
| bounded | reach limited by the program itself to protocol-owned balances, fees, or not-yet-live assets (for example Jupiter `close_token`, Kamino global fee admin, Kamino proposer) | listed as a note with its holder classification |
| restrict-only | can only pause, block or lower limits (for example Kamino emergency council) | listed as a note |

Each dimension takes the **minimum** over full-power paths, so a path without delay caps
`timelockScore` even when the upgrade path has a long delay. Oracle-provider paths are
scored only in `oracleAuthorityScore` (6.3), to avoid counting the same weakness twice.

Hardcoded authority keys compiled into a binary are invisible to account reads. When the
program publishes an on-chain Anchor IDL (`create_with_seed(find_program_address([], program), "anchor:idl", program)`),
every account with a fixed `address` in an instruction must be classified like any other
authority. A program without an on-chain IDL gets the note "hardcoded keys not enumerable".

### 6.3 Oracle authority through an aggregator

When a consumer reads prices through an aggregator program rather than directly from a
provider, three authority paths decide which price is used:

1. the consumer's own oracle-configuration authority (for Kamino, the market owner through the oracle modes of `UpdateReserveConfig`);
2. the aggregator's mapping admin for the feed the consumer reads (for Kamino Scope, `Configuration.admin` of the configuration whose `oracle_prices` equals the reserve's `scope_price_feed`; it can switch an entry to `FixedPrice`);
3. the aggregator program's upgrade authority.

`oracleAuthorityScore` = min over these paths of each path's own composite (6.1).
Consumer-side sanity checks (TWAP divergence, heuristics) earn no bonus when the same
authority can also re-map the TWAP source. Providers behind an aggregator entry are not yet
scored recursively (open point, section 7).

## 7. Open points carried into the methodology phase

- **CLOSED 2026-09-17**: `SMPLVC8MxZ5Bf5EfF7PaMiTCxoBAcmkbM2vkrvMK8ho` (executes Pyth
  upgrades) is upgradeable by `HVx4oW785bu8QDQ8AwSVfD7H4iuH51ttakc2G5f9XTX8`, a PDA
  owned by `pytGY6tWRgGinSCvRLnSv4fHfBTMoiDGiCsesmHWM6U` -- confirmed against a primary
  Pyth source (`pyth-network/governance`'s own `staking/Anchor.toml`, `governance =
  "pytGY6tWRgGinSCvRLnSv4fHfBTMoiDGiCsesmHWM6U"` under `[programs.mainnet]`): Pyth's
  own official on-chain governance program, not a third-party or ad-hoc multisig. See
  `data/finding_2026-09-17-spl-governance-shared-instance-controller.md`.
- **CLOSED 2026-09-17**: the controller of the SPL Governance instance authority
  `HF7gCq7B...8y9n` is a 5-of-7-by-weight council ("Realms Security council 8", a
  Realms-Today-Ltd-operated internal platform-security Realm, not a consumer DAO),
  traced via a live transaction (`GOVERNANCE-INSTRUCTION: ExecuteTransaction` through
  a second SPL Governance deployment, `GoVERLMGbGF8kwAwhyNgF1BQ2uyQPawHCWbnFRmLZCf`,
  version 3.1.1) and cross-checked with `programs-by-authority` (14 controlled
  programs, including both the shared default instance and this second governance
  program itself). Full derivation, including the newly-found version-dependent
  `GovernanceV2` byte-layout difference (flagged, not yet fixed):
  `data/finding_2026-09-17-spl-governance-shared-instance-controller.md`.
- **CLOSED 2026-09-19**: Switchboard On-Demand oracle authority primitives added --
  see 3.7 for the full derivation (program id, `PullFeedAccountData`/`QueueAccountData`
  authority fields, live-verified on Drift's AI16Z spot market on 2 independent RPCs)
  and `score_drift_protocol`'s new `oracleAuthorityScore` computation in `scorers.py`.
- Recursive scoring of the providers behind an aggregator entry (Scope `MostRecentOf`, Pyth Lazer EMA).
- Kamino emergency council key `4VtJ1yCCyU2YGgPTZGHZRwzwaZ3hmzgqMtRQo8RqMa57`: controller not
  resolved (restrict-only, no score impact).
- Closed by the methodology test: Anchor config accounts are decoded one layout per target
  from the protocol's published source, with a human-readable field as layout self-check;
  second indexed RPC found (section 4).
- **New, found scoring Solend DAO governance (2026-09-17):** the "70 for token voting" flat
  adminKey/multisig baseline does not account for REALIZED voter concentration -- a DAO where
  a handful of large holders can supply the deciding "yes" weight within one short window
  (independently confirmed for Solend's own 2022 SLND1 vote, see
  `data/backtest_2026-09-17-solend-governance-emergency-powers.md`) scores identically to one
  with genuinely broad participation. A concentration-aware adjustment (for example, the
  share of a proposal's "yes" weight held by its single largest `TokenOwnerRecord`) would be a
  real improvement, but needs calibration across more than one Realms-governed target before
  it can be a deterministic formula rather than a guess -- not implemented this pass.
- **New, found the same day:** the Realm's own `authority` field (`state/realm.rs`, distinct
  from any Governance account) is a SEPARATE full-power path this section did not previously
  name -- a bare EOA there can unilaterally rewrite a Realm's voting config with no proposal at
  all, one level above every Realms-governance formula in this section, which only scores the
  token-vote path. Added to 6.2's full-power classification: a Realm's `authority` field must
  be read and classified like any other admin key, not assumed to already be a Governance PDA
  just because the realm has proposals.
- **New, found and CLOSED the same day, by adversarial review:** a first version of
  `score_solend_dao_governance` scored the two paths above but omitted a third: the governance
  PROGRAM's own upgrade authority (a dedicated, non-shared instance still has one, per 3.6) --
  inconsistent with `score_jupiter_aggregator_v6`/`score_kamino_lend`, which both score their
  own program's upgrade authority as a matter of course. Live-checked: Solend's governance
  program upgrade authority is ALSO a bare, active, on-curve EOA
  (`6EpduYmguTXpJMtEKjYXvrmuusBFrTy2stPNzbDZrqUT`), not renounced. Fixed: the function now scores
  all three paths and takes the minimum across them, matching every other target in this file.
- **Found by adversarial review 2026-09-17, CLOSED 2026-09-19:** the `realms_governance`
  timelock formula and the Squads v4 timelock formula both claimed to measure "delay before an
  authority action takes effect," but scored a comparable ~6-hour delay on wildly different
  curves (Squads: 13; Realms: ~43) and disagreed even more sharply at zero delay (Squads: 0;
  Realms: 40, an algebraic floor of the additive formula, not a deliberate choice). Investigated
  seriously rather than assumed reconcilable or dismissed as inherently different: the two
  delays turn out NOT to measure the same concept, for a documented reason, not a guess.
  spl-governance's own source (`governance/program/src/state/governance.rs`'s doc comments on
  `GovernanceConfig`) states `transactions_hold_up_time` is "the wait time ... before
  transactions can be executed AFTER proposal is successfully voted on" -- the decision is
  already final, exactly Squads v4 `time_lock`'s own concept. `voting_base_time` is "the base
  voting time ... for proposal to be open for voting. Voting is unrestricted ... any vote types
  can be cast," and `voting_cool_off_time` merely "extend[s]" it with only negative (Veto/Deny)
  votes still allowed -- BOTH are still part of reaching the decision (a proposal can still be
  voted down or vetoed during either), with no Squads-side analogue scored anywhere in this file
  (a Squads proposal's own time-to-collect-signatures is never scored as a delay). The old
  formula summed all three into one curve, conflating "time to decide" with "notice after
  deciding," which is exactly why it diverged from Squads' curve at short/zero delay. Fix:
  `_score_full_power_path("realms_governance", ...)`'s timelock now calls the SAME
  `_delay_timelock_score(d_hours)` helper Squads v4 uses, fed by `holdup_s` ALONE --
  `voting_s`/`cooloff_s` remain accepted parameters (every call site still reads and discloses
  them in its own notes) but no longer feed the score. No new curve invented; the reconciliation
  reuses the existing one, now that the inputs are conceptually aligned. Checked against every
  real target already scored (Solend, Drift, Marinade): each one's PUBLISHED overall
  timelockScore is UNCHANGED by this fix, because a different, already-dominant full-power path
  (a bare on-curve authority, or a short Squads delay) was already the binding `min()` constraint
  in all three -- the fix corrects the formula's own internal correctness and removes a landmine
  for a future target where the Realms path would be the binding one, without silently moving
  any already-published number. adminKey/multisig for `realms_governance` were NOT touched by
  this fix -- they remain the flat-70/threshold-based values from the 2026-09-17 calibration.
- **INVESTIGATED 2026-09-19, still open (no number changed):** the flat "70 for token voting"
  adminKey/multisig baseline (introduced 2026-09-16, before any Realms target existed) has never
  had a documented derivation -- no stated equivalent-multisig-threshold or participation
  assumption anywhere in this file. Seriously investigated this pass, against three lines of real
  evidence, rather than left as a bare "gap" note a second time:
  1. **Git history, checked directly:** `git log -p --all -- chains/solana/METHODOLOGY.md
     chains/solana/scorers.py` shows the constant appears ALREADY as a bare literal in the exact
     commit that first added the Realms token-voting row (`eb42e3c`, "Pipeline run 2") -- no
     comment, no commit-message rationale, no calibration reference, then or since. There is
     nothing to recover; it was never derived from anything in the first place.
  2. **A numerical coincidence exists, and is explicitly REJECTED as the derivation, not adopted:**
     `70 = 60 + min(30, 5*(t-1))` at `t=3`, exactly the SAME formula this row's own countable-
     threshold branch uses. Checked whether this was the intended reasoning -- no comment, test,
     or commit ties `t=3` to the flat-70 case anywhere; presenting a coincidence as a derivation
     after the fact would be exactly the fabrication this file's "don't guess a number" rule
     exists to prevent, so it is named here and set aside, not used.
  3. **Compared against the two real token-voting targets this file already tracks**
     (`score_solend_dao_governance`: Solend's real `community_vote_threshold` = `YesVotePercentage(1)`,
     1% of total supply; `score_drift_protocol`'s realm-authority path: Drift's real threshold =
     `YesVotePercentage(2)`, 2% of total supply) -- both score the IDENTICAL flat 70 today, because
     the formula never takes the real, already-decoded threshold percentage as an input at all.
     There is no way 70 could have been derived from either DAO's specific threshold, since
     neither value feeds the score. Attempted to go one level deeper using this project's own
     real incident data (`data/backtest_2026-09-17-solend-governance-emergency-powers.md`'s SLND1
     vote, 1,155,431.557485 SLND "yes" weight) to estimate a REAL "% of supply" participation
     figure -- but SLND's mint authority is NOT renounced (`EaFPY9LTQeFR7SEyfbKKFuVMtYvUBbYiiK7WvBJJ7iBU`,
     live-checked) and the CURRENT total supply (3,344,351.60 SLND) is dramatically different from
     2022's (almost certainly reduced by burns since), so dividing SLND1's 2022 vote weight by
     TODAY's supply would produce a number (34.5%) that describes neither the 2022 event nor
     today's DAO -- checked and explicitly discarded rather than published as if it were real.
  **Conclusion: no solid derivation exists, and none was fabricated to close this out.** What
  would actually be needed: (a) a HISTORICAL circulating-supply snapshot at the exact moment of
  a real vote (not today's supply), for more than the one incident this project has looked at;
  (b) a second, independent real Realms-DAO vote to compare against, since one data point cannot
  calibrate a curve; and (c) a stated, principled mapping from "% of supply required to pass" (or
  realized concentration) to an "equivalent independent-party count," analogous to the existing
  Squads t-of-n formula -- none of which exist today. Track as a real gap distinct from the
  voter-concentration point above (a derivation could exist and still not account for
  concentration; right now neither exists) -- both remain open, now with a documented reason why.
- **CLOSED 2026-09-17:** the countable council/community-threshold branch of the Realms
  governance row previously had a concrete adminKey formula (`60 + min(30, 5(t-1))`) but an
  unresolved multisig placeholder. Calibrated against a real data point found the same day
  (`data/finding_2026-09-17-spl-governance-shared-instance-controller.md`): the SPL Governance
  shared instance's own controlling council is a 7-member, one-token-per-seat council requiring
  60% weight to pass (`ceil(0.6*7) = 5` -- an effective 5-of-7). Since a council-threshold vote
  is structurally the same "t-of-n, weight-gated" shape the Squads formulas already score,
  `_score_full_power_path("realms_governance", threshold=t, voters=n, ...)`'s multisig column
  now reuses the SAME formula as Squads v3/v4: `min(100, round(15 t + 40 t / voters))` -- for
  this real 5-of-7 case, `min(100, round(75 + 200/7)) = min(100, 104) = 100`. Not a new,
  invented curve; the existing, already-calibrated Squads multisig formula applied to a
  structurally identical input.

## Reproducing the reads

```
python3 chains/solana/scripts/sol_read.py genesis https://api.devnet.solana.com
python3 chains/solana/scripts/sol_read.py program https://api.mainnet-beta.solana.com TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb
python3 chains/solana/scripts/sol_read.py squadsv3 https://api.mainnet-beta.solana.com BnD53519LK7QM4ERBGvLedZDe1VoTPgtiBkGPWAACiMZ 1
python3 chains/solana/scripts/sol_read.py squads https://api.mainnet-beta.solana.com FzzZT2db8TUgyxPfKn42iEqtuob7TY8DMPv6cnGLxd4A
python3 chains/solana/scripts/sol_read.py splmultisig https://api.mainnet-beta.solana.com BJE5MMbqXjVwjAF7oxwPYXnTXDyspzZyt4vwenNw5ruG
python3 chains/solana/scripts/sol_read.py pyth-config https://api.mainnet-beta.solana.com rec5EKMGg6MxZYaMdyBfgwp4d5rB9T1VQH5pJv5LtFJ
python3 chains/solana/scripts/sol_read.py programs-by-authority https://api.mainnet-beta.solana.com 6oXTdojyfDS8m5VtTaYB9xRCxpKGSvKJFndLUPV3V3wT
python3 chains/solana/scripts/sol_read.py program-of-programdata https://api.mainnet-beta.solana.com GeZ7nkkcbJ6VVV1XVFbmFnLCY3F1LPBGk6cufDZvrbGn
python3 chains/solana/scripts/sol_read.py squads-vault - 6hhBGCtmg7tPWUSgp3LG6X2rsmYWAc4tNsA6G4CnfQbM 0
python3 chains/solana/scripts/sol_read.py anchor-idl https://api.mainnet-beta.solana.com JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4
python3 chains/solana/scripts/sol_read.py klend-market https://api.mainnet-beta.solana.com 7u3HeHxYDLhnCoErrtycNokbQYbWGzLs6JSDqGAv5PfF
python3 chains/solana/scripts/sol_read.py klend-reserve-oracle https://api.mainnet-beta.solana.com d4A2prbA2whesmvHaL88BH6Ewn5N4bTSU2Ze8P6Bc4Q
python3 chains/solana/scripts/sol_read.py scope-configs https://api.mainnet-beta.solana.com HFn8GnPADiny6XqUoWE8uRPPxb29ikn4yTuPa9MF2fWJ
python3 chains/solana/scripts/sol_read.py realm https://api.mainnet-beta.solana.com 7sf3tcWm58vhtkJMwuw2P3T6UBX7UE5VKxPMnXJUZ1Hn
python3 chains/solana/scripts/sol_read.py governance https://api.mainnet-beta.solana.com 4AxRDMShhYgoP7vVsZ1oDzQQaVw3WBPUoFvonYxJXTpc
python3 chains/solana/scripts/sol_read.py program https://api.mainnet-beta.solana.com A7kmu2kUcnQwAVn8B4znQmGJeUrsJ1WEhYVMtmiBLkEr
python3 chains/solana/scripts/sol_read.py switchboard-pull-feed https://api.mainnet-beta.solana.com BHqLyA9ov1VPNzt8eb5bt75X2Vk1EVKw1d9Qa78Gk5tR
python3 chains/solana/scripts/sol_read.py switchboard-queue https://api.mainnet-beta.solana.com A43DyUGA7s8eXPxqEjJY6EBu1KKbNgfxF8h17VAHn13w
python3 chains/solana/scripts/sol_read.py program https://api.mainnet-beta.solana.com SBondMDrcV3K4kxZR1HNVT7osZxAHVHgYXL5Ze1oMUv
```

## Changelog

| Date | Change | Reason (gap id in the methodology test) |
|---|---|---|
| 2026-09-16 | Discovery draft (sections 1 to 7). | Discovery phase. |
| 2026-09-16 | Added 6.1: deterministic formulas replacing score ranges. | G1: ranges could not produce one number. |
| 2026-09-16 | Added the band 0 < `time_lock` < 24 h. | G2: Kamino market owner is at 12 h. |
| 2026-09-16 | Added 6.2: full-power / bounded / restrict-only classes, min over full-power paths, on-chain Anchor IDL read for hardcoded keys. | G3 (seven Kamino authorities), G8 (Jupiter hardcoded operator). |
| 2026-09-16 | Added 6.3: oracle authority through an aggregator (Scope). | G4: grid only covered the Pyth receiver. |
| 2026-09-16 | **Corrected** the `crossExposureScore` definition in section 4 to the repo-wide signer-overlap formula; programs-by-authority becomes a note. | G5: the discovery text contradicted `scripts/lib/signer_overlap.py`. |
| 2026-09-16 | Ladder rung 3: resolution procedure with mandatory offline PDA re-derivation. | G6. |
| 2026-09-16 | Threshold-1 rule generalised from 1-of-1 to any t = 1 multisig. | G7: Kamino proposer is 1-of-5. |
| 2026-09-16 | Independent indexed RPC recorded; `api.mainnet.solana.com` flagged as not independent. | G9. |
| 2026-09-17 | Closed the "untested" flag on the `Realms governance` row (6.1): generalized the timelock formula to hold-up = 0 (no new branch needed -- the additive voting-time term degrades gracefully). Validated against Solend DAO -- but only the timelock hold-up=0 generalization itself; the adminKey/multisig = 70 constant was carried over unchanged, not re-derived (see the 2026-09-17 adversarial-review row below). Added 3.6's note that not every Realms DAO uses the shared default governance program. Added 6.2's note that a Realm's own `authority` field is a separate full-power path from any Governance account under it. Flagged (section 7) that the flat "70 for token voting" baseline does not yet account for realized voter concentration. | Solend DAO governance methodology test (`chains/solana/data/methodology_test_2026-09-17-solend-governance.md`), surfaced while independently re-verifying the 2022 SLND1/SLND2 incident for `data/backtest_2026-09-17-solend-governance-emergency-powers.md`. |
| 2026-09-17 | Adversarial review of the above (same day): fixed `score_solend_dao_governance` to score a third full-power path it had omitted (the governance program's own upgrade authority -- also a bare, active EOA, `6EpduYmguTXpJMtEKjYXvrmuusBFrTy2stPNzbDZrqUT`). Corrected 6/6.1's Realms rows to stop claiming adminKey/multisig "credit the voting window" (they are flat constants and do not) and to disclose, rather than hide, that the Realms timelock curve is unreconciled with the Squads v4 curve at short delays. Marked the countable council-threshold multisig formula as explicitly "not yet calibrated" instead of an unresolved-looking placeholder. Corrected the changelog entry above to not overclaim the flat-70 constant was itself validated. | `authority-risk-oracle-bug-hunt`-style adversarial review workflow (5 findings, 5 confirmed, 0 refuted) run specifically against this same-day addition, following the project's own established "no shortcuts" review discipline. |
| 2026-09-17 | Closed two 2026-09-16 open points (identity of `SMPLVC8Mx...` and the controller of `HF7gCq7B...8y9n`) by retrying the same "trace a real transaction, cross-check independently" technique now that `read_realm`/`read_governance` exist. Found the SPL Governance shared instance is itself controlled by a real 5-of-7-by-weight council -- used that real data point to close the countable council-threshold multisig formula gap the same-day adversarial review had flagged, reusing the existing Squads t-of-n formula rather than inventing a new one. Flagged (not fixed) a version-dependent `GovernanceV2` byte-layout difference discovered along the way. | `data/finding_2026-09-17-spl-governance-shared-instance-controller.md`, retried per this project's own standing rule: research that hits a wall gets set aside and revisited, not abandoned. |
| 2026-09-18 | No new formula or dimension added -- closed a real BACKLOG instead: 8 already-scouted DeFi targets (`scouted_targets_2026-09-17-run2.md`) had only an upper-bound composite (program-upgrade authority alone), since each protocol's own separate application-level config admin hadn't been decoded. Decoding it, per the already-existing 6.2 minimum-over-paths rule, found 6 of 8 score LOWER than published, two (Meteora DAMM v2, Orca Whirlpool) collapsing to the same near-floor CRITICAL band Hyperliquid's Kinetiq/`para` findings already reached. One new read mechanism used for the first time on a live target: 6.2's own "on-chain Anchor IDL exposes a hardcoded `#[account(address=...)]` constant" clause (Raydium's `admin::ID`), read live via `sol_read.read_anchor_idl` rather than hardcoded from a citation. | `chains/solana/data/scored_targets_2026-09-18-defi-config-admins.md`. |
| 2026-09-18 | Adversarial review of the above (same day, 30 agents/26 findings/23 confirmed): fixed `score_marginfi` to live-verify and disclose that its two "independent" full-power paths' multisigs share almost the same people (the 7-of-15 upgrade multisig's voters are a strict subset of the 5-of-17 admin multisig's members) -- composite unchanged, disclosure only. Re-affirmed, not changed: Jupiter Perps' Squads v3 PDA resolution (a verify-pass agent's own refutation attempt had a bug in its from-scratch PDA reimplementation, caught by re-running the actual project code) and Meteora DLMM/DAMM v1's non-promotion (a proposed intermediate score tier was itself refuted as a category error against 6.2's existing tier definitions and the project's own CoreWriter/Kinetiq indirect-evidence lesson). | `chains/solana/data/scored_targets_2026-09-18-defi-config-admins.md`'s own "Adversarial review, 2026-09-18" section. |
| 2026-09-18 | Closed Methodology gap H1 (6.1: the legacy "serum-style" multisig shape reuses the Squads v3/zero-delay row unchanged, formula-identical, not merely similar) and Marinade's own "decode `State.admin_authority`" open point together, since both applied to the same target. `admin_authority` turned out to be a Realms council-governance path (community voting structurally disabled on that specific Governance record), giving this project's `realms_governance` countable-threshold branch its first real working example -- found along the way that `score_solend_dao_governance`'s own comment claiming that branch "deliberately raises NotImplementedError" had been stale since the exact day it was written (the branch was actually calibrated 2026-09-17); fixed the comment. Composite moved from the published upper bound of 54 to 45. | `chains/solana/data/scored_targets_2026-09-18-marinade-liquid-staking.md`. |
| 2026-09-19 | Closed section 7's "Add Switchboard On-Demand oracle authority primitives" open point: added 3.7 (program id, `PullFeedAccountData`/`QueueAccountData` byte layouts sourced from the official SDK, both discriminators confirmed), and gave `score_drift_protocol` a real, live-computed `oracleAuthorityScore` (previously a flat, unjustified 100 like every other non-Kamino target) using one real, live, named Switchboard-On-Demand-sourced market (Drift's AI16Z spot market) as the concrete example, the same disclosed-scope convention `score_kamino_lend` already uses. A first recalled guess for the On-Demand program id was WRONG (4 characters off, a plausible-looking fabricated string) and was caught only by checking the primary source (the SDK's own `ON_DEMAND_MAINNET_PID` constant) before use -- a live demonstration of this file's own "don't guess a number" discipline applied to an identifier, not just a formula. Also found and disclosed (not fixed, out of this pass's scope): Drift's OWN published SDK constant for W-PERP's oracle is stale (migrated to PythLazer on-chain since); the two remaining section-7 points (the Realms/Squads timelock-curve mismatch and the flat "70" baseline's derivation) were investigated the same day, see their own entries below. | `chains/solana/scripts/sol_read.py::read_switchboard_pull_feed`/`read_switchboard_queue` (new), `chains/solana/scorers.py::score_drift_protocol` (updated), `scripts/lib/tests/test_switchboard_on_demand.py` (new), live-verified on 2 independent RPCs (`api.mainnet-beta.solana.com`, `solana-rpc.publicnode.com`). |
| 2026-09-19 | CLOSED section 7's Realms-vs-Squads timelock-curve mismatch (flagged by adversarial review 2026-09-17): found a real, documented, PRINCIPLED reconciliation rather than forcing or refusing one. spl-governance's own source distinguishes `transactions_hold_up_time` (post-decision notice, the true Squads `time_lock` equivalent) from `voting_base_time`/`voting_cool_off_time` (still part of reaching the decision, no Squads-side analogue scored anywhere in this file). Extracted the shared curve into `_delay_timelock_score(d_hours)`, used identically by Squads v4 and (now, holdup-only) `realms_governance` -- pure refactor for the Squads side (verified byte-identical outputs via the existing test suite before/after), and the actual fix for the Realms side. Verified the fix is not merely theoretically nicer but doesn't silently move any already-published number: re-ran `score_solend_dao_governance`/`score_drift_protocol`/`score_marinade` live before and after -- all three composites unchanged (each already had a different, more severe full-power path dominating the `min()`), so this closes a real formula-correctness gap without disrupting any live score. | `chains/solana/scorers.py::_delay_timelock_score` (new), `_score_full_power_path` (refactored), `scripts/lib/tests/test_solend_governance.py::TestRealmsGovernanceFormula` (updated to the reconciled formula). |
| 2026-09-19 | INVESTIGATED (not closed, no number changed) section 7's undocumented flat "70 for token voting" adminKey/multisig baseline: checked git history directly (bare literal since introduction, `eb42e3c`, no comment or rationale ever attached), checked and explicitly REJECTED a numerical coincidence (`70` equals this row's own countable-threshold formula at `t=3`, but nothing ties that to why 70 was chosen), and compared against the two real targets that hit this branch (Solend's real 1% `YesVotePercentage`, Drift's real 2%) -- neither value feeds the formula, so neither could have calibrated it. Attempted one level deeper using this project's own SLND1 backtest data, and explicitly discarded the result: SLND's mint authority is not renounced and current supply (live-checked, 3,344,351.60 SLND) is not a valid stand-in for 2022's circulating supply, so no honest "% of supply" figure could be produced from it. Conclusion: no solid derivation exists, none was fabricated, and the code is UNCHANGED -- only the investigation and what would be needed to actually close this (historical supply snapshots, a second real DAO data point, a stated equivalent-party-count mapping) are now documented. | `chains/solana/scorers.py::_score_full_power_path`'s `realms_governance` branch (comment added, no behavior change), `data/backtest_2026-09-17-solend-governance-emergency-powers.md` (re-examined, not modified). |
