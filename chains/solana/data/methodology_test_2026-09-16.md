# Solana methodology test: Jupiter Aggregator v6 and Kamino Lend (2026-09-16)

Purpose: apply [`../METHODOLOGY.md`](../METHODOLOGY.md) end to end to two real, high-usage
Solana protocols, derive every score dimension from live Mainnet Beta state, and record
where the written grid was not enough. Nothing was pushed on-chain. All reads are plain
JSON-RPC through [`../scripts/sol_read.py`](../scripts/sol_read.py) (no keys, no signing).

| Item | Value |
|---|---|
| Cluster | Solana Mainnet Beta (genesis `5eykt4UsFv8P8NJdTREpY1vzqKqZKvdpKuc147dw2N9d`) |
| Slot at time of reading | about 447,610,000 |
| Primary RPC | `https://api.mainnet-beta.solana.com` |
| Independent second RPC (account reads) | `https://solana-rpc.publicnode.com` |
| Independent second RPC (indexed `getProgramAccounts`) | `https://public.rpc.solanavibestation.com` |

Result summary (composite = floor(0.4 admin + 0.3 multisig + 0.3 timelock + 0.5), the repo convention; oracle and cross-exposure are published separately):

| Target | adminKey | multisig | timelock | oracleAuthority | crossExposure | composite |
|---|---|---|---|---|---|---|
| Jupiter Aggregator v6 | 55 | 83 | 0 | 100 (not applicable) | 100 | **47** |
| Kamino Lend, main market | 65 | 76 | 25 | **45** | 100 | **56** |

Formulas used are the deterministic ones added to METHODOLOGY.md section 6.1 during this
test (see "Methodology gaps found" below: the original bands were ranges and could not
produce a single number).

---

## Target 1: Jupiter Aggregator v6

### 1.1 Identity (primary sources)

| Fact | Source |
|---|---|
| Program id `JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4` | Jupiter's own CPI crate [jup-ag/jupiter-cpi `src/lib.rs`](https://github.com/jup-ag/jupiter-cpi/blob/main/src/lib.rs) and example [jup-ag/sol-swap-cpi](https://github.com/jup-ag/sol-swap-cpi/blob/main/programs/swap-to-sol/src/lib.rs) (two files, same org) |
| On-chain Anchor IDL at `C88XWfp26heEmDkmfSzeXP7Fd7GQJ2j9dDTUsyiZbUTa` | metadata `"name": "jupiter"`, `"description": "Jupiter aggregator program"`, `"address"` equal to the program id |

### 1.2 Raw reads

```
$ sol_read.py program <rpc> JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4        (both RPCs identical)
owner BPFLoaderUpgradeab1e11111111111111111111111   programdata 4Ec7ZxZS6Sbdg5UGSLHbAnM7GQHp2eFd4KYWRexAipQT
last_deploy_slot 445747349   upgrade_authority CvQZZ23qYDWF2RUpxYJ8y9K4skmuvYEEjH7fK58jtipQ

$ sol_read.py keytype <rpc> CvQZZ23q...tipQ     -> on_curve false, owner System (a PDA)

last upgrade tx (slot 445747349):
2EEg5nAibYYZub3cX1AjHuKYJRY9M4GueLwaruqAVQNmywquFCWS8ZPg6VxNV54L2pmXCJchyvE7eJFQ7i1y5ctt
  top-level: SMPLecH534NA9acpos4G6x7uf3LWbCAwZQE9e8ZekMu  "Instruction: ExecuteTransaction"
             accounts[0] = 7ZyDFzet6sKgZLN4D89JLfo7chu2n7nYdkFt5RCFk8Sf (the Ms account)
  inner:     BPFLoaderUpgradeable upgrade, authority CvQZZ23q...tipQ

$ sol_read.py squadsv3 <rpc> 7ZyDFzet6sKgZLN4D89JLfo7chu2n7nYdkFt5RCFk8Sf 1     (both RPCs identical)
owner SMPLecH534NA9acpos4G6x7uf3LWbCAwZQE9e8ZekMu  threshold 4  n_keys 7
authority_1 (offline PDA derivation) = CvQZZ23qYDWF2RUpxYJ8y9K4skmuvYEEjH7fK58jtipQ   <- exact match
all 7 member keys: on_curve true (no nested multisig)

$ sol_read.py anchor-idl <rpc> JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4
idl_authority 9u9iZBWqGsp5hXBxkVZtBTuLSGNAG9gEQLgpuVw39ASg (on-curve)
accounts: [TokenLedger]  (no config / admin account type)
hardcoded addresses: claim.wallet and claim_token.wallet = 7JQeyNK55fkUPUmEotupBFpiBGpgEQYLe8Ht1VdSfxcP
                     close_token.operator (signer)       = 9RAufBfjGQjDfrwxeyKmZWPADHSb8HcoqCdrmpqvCr1g (on-curve)

$ sol_read.py programs-by-authority <rpc> CvQZZ23q...tipQ
programdata_count 22 on api.mainnet-beta.solana.com, 22 on public.rpc.solanavibestation.com
```

### 1.3 Authority paths

| Path | Holder | Class | Why |
|---|---|---|---|
| Program upgrade (replace all code) | Squads v3 `7ZyD...k8Sf`, authority index 1, 4-of-7 | **full-power** | loader-v3 `Upgrade`, no delay parameter exists (METHODOLOGY 3.1) |
| `close_token` (close or burn token accounts held by the program authority PDA) | on-curve key `9RAu...Cr1g`, hardcoded in the binary | bounded | reach limited to the program-authority token accounts used as intermediate and fee accounts; no instruction in the IDL lets it touch a user wallet or change routing |
| `claim` / `claim_token` | anyone, destination hardcoded to `7JQe...xcP` | bounded | sweeps program-authority balances to a fixed wallet, destination not changeable without an upgrade |
| IDL account | on-curve key `9u9i...9ASg` | not scored | rewrites published interface metadata only; noted because integrators decode with it |

### 1.4 Derivation

| Dimension | Rule applied | Inputs | Score |
|---|---|---|---|
| adminKeyScore | 6.1: Squads v3 t-of-n with t >= 2 = 40 + min(20, 5 (t-1)) | t = 4 | **55** |
| multisigScore | 6.1: min(100, round(15 t + 40 t / voters)) | t = 4, voters = 7 | **83** |
| timelockScore | Squads v3 has no time-lock field (METHODOLOGY 3.4) | delay 0 on the only full-power path | **0** |
| oracleAuthorityScore | not applicable = 100 | IDL contains no oracle account; price protection is the user-supplied minimum out amount (`SlippageToleranceExceeded`) | **100** |
| crossExposureScore | repo formula max(0, 100 - 20 x sharedGroupCount) over tracked groups | no root signer shared with the Kamino group (intersection of 7 and 11 keys is empty) | **100** |
| composite | floor(0.4x55 + 0.3x83 + 0.3x0 + 0.5) | | **47** |

Context before qualifying:

- Attenuating: a swap router does not custody user funds between transactions, so an
  upgrade risk is a risk to in-flight swaps and to token approvals routed through it, not
  to a deposited balance.
- Aggravating: the same authority PDA upgrades **22** programs (blast radius published as a
  note, not a score input). A 4-of-7 compromise or coercion changes all of them at once,
  with zero delay for users to react.

---

## Target 2: Kamino Lend (klend), main market

### 2.1 Identity (primary sources)

| Fact | Source |
|---|---|
| Program id `KLend2g3cP87fffoy8q1mQqGKjrxjC8boSyAYavgmjD` | [Kamino-Finance/klend README](https://github.com/Kamino-Finance/klend/blob/master/README.md), "Mainnet" |
| Primary market `7u3HeHxYDLhnCoErrtycNokbQYbWGzLs6JSDqGAv5PfF` | official Kamino API `https://api.kamino.finance/v2/kamino-market` (`"isPrimary": true`); cross-checked on-chain: owner program is klend and the decoded `name` field reads `SOL/BTC Market` |
| Scope oracle program `HFn8GnPADiny6XqUoWE8uRPPxb29ikn4yTuPa9MF2fWJ` | [Kamino-Finance/scope `program_id.rs`](https://github.com/Kamino-Finance/scope/blob/master/programs/scope/src/program_id.rs), `mainnet` feature |
| Usage | Kamino API reserve metrics: SOL reserve total supply in the hundreds of millions of USD at time of reading |

Account layouts used: [`lending_market.rs`](https://github.com/Kamino-Finance/klend/blob/master/programs/klend/src/state/lending_market.rs),
[`token_info.rs`](https://github.com/Kamino-Finance/klend/blob/master/programs/klend/src/state/token_info.rs),
[`global_config.rs`](https://github.com/Kamino-Finance/klend/blob/master/programs/klend/src/state/global_config.rs),
Scope [`configuration.rs`](https://github.com/Kamino-Finance/scope/blob/master/programs/scope/src/states/configuration.rs)
and [`oracle_mappings.rs`](https://github.com/Kamino-Finance/scope/blob/master/programs/scope/src/states/oracle_mappings.rs).
Each decoder self-checks by reading a human-readable field (`name` = `SOL/BTC Market`, reserve name `SOL` and `USDC`).

### 2.2 Raw reads

```
$ sol_read.py program <rpc> KLend2g3cP87fffoy8q1mQqGKjrxjC8boSyAYavgmjD            (both RPCs identical)
programdata 9uSbGW1y9H5Av6H5TKxQ1wnFApSq2t3oEpfF2YfjDQGA  last_deploy_slot 440486775
upgrade_authority GzFgdRJXmawPhGeBsyRCDLx4jAKPsvbUqoqitzppkzkW  (off-curve)

last upgrade tx 3tTU214kgvZxi2x9SbSCJDNLnvFxAqRGktnMT6gP6SiTAMzUawc8N7GR23tySTAbsR8hc2J98f2Mg2nDXa1MubRi
  SQDS4ep65T869zMMBKyuUq6aD6EgTu8psMjkvj52pCf "VaultTransactionExecute", accounts[0] = 6hhBGCtmg7tPWUSgp3LG6X2rsmYWAc4tNsA6G4CnfQbM
$ sol_read.py squads-vault - 6hhBGCtmg7tPWUSgp3LG6X2rsmYWAc4tNsA6G4CnfQbM 0  -> GzFgdRJX...kzkW   <- exact match

$ sol_read.py klend-market <rpc> 7u3HeHxYDLhnCoErrtycNokbQYbWGzLs6JSDqGAv5PfF      (both RPCs identical)
lending_market_owner 24LjDBukaUSHgPowcF2wY1XscnhChcBUDETN2UhBZMMT (= owner_cached, no pending transfer)
emergency_council   4VtJ1yCCyU2YGgPTZGHZRwzwaZ3hmzgqMtRQo8RqMa57
proposer_authority  6pwkb7uMsvqgmwPBKc3o4hnte6JnHpisSUrsdyvGcEUv
immutable 0
global_admin        A9rQoX1sictAQkyXxaZA8nz674xutHwoqpK2mwLyexCZ   (GlobalConfig PDA BEe6HXZf6cByeb8iCxukjB8k74kJN3cVbBAGi49Hfi6W)

$ sol_read.py klend-reserve-oracle <rpc> d4A2prbA2whesmvHaL88BH6Ewn5N4bTSU2Ze8P6Bc4Q   (SOL reserve)
scope_price_feed 3t4JZcueEzTbVP6kLxXrL3VpWx45jDer4eqysweBchNH  price_chain [3]  twap_chain [455]
max_twap_divergence_bps 1000   switchboard and pyth fields unset (default key 1111...1111)
$ sol_read.py klend-reserve-oracle <rpc2> D6q6wuQSrifJKZYpR1M8R4YawnLDtDsMmWM1NbBmgJ59  (USDC reserve)
same scope_price_feed, price_chain [13], max_twap_divergence_bps 300

$ sol_read.py scope-configs <rpc> HFn8GnPADiny6XqUoWE8uRPPxb29ikn4yTuPa9MF2fWJ
configuration 6cMwdbrJ95D7v5655Zsoe7oXmjQJMnagWK8EcdG6qmGM: oracle_prices 3t4JZ...BchNH, admin CzwQ3dFHekGbHcGYNwUHAjShX9KmhFdWsfJBmYFMHoh7
oracle_mappings 4zh6bmb77qX2CL7t5AJYCqa6YqFafbz3QJNeFvZjLowg: entry 3 type 28 (MostRecentOf), entry 455 type 48 (PythLazerEMA)

$ sol_read.py program <rpc> HFn8GnPADiny6XqUoWE8uRPPxb29ikn4yTuPa9MF2fWJ
upgrade_authority 4R33WT7isNgzALNyvpZKiZQARtZNAXarWB3prUbPkXX7
```

Each off-curve authority was resolved the same way (latest transaction signed through it,
multisig account read, vault or authority PDA re-derived offline and compared):

| Authority key | Controller found in tx | Offline derivation | Multisig state (both RPCs where checked) |
|---|---|---|---|
| klend upgrade `GzFg...kzkW` | Squads v4 `6hhB...fQbM` | vault 0 matches | 5-of-10, all 10 can vote, `time_lock` 86,400 s, `config_authority` default |
| market owner `24Lj...ZMMT` | Squads v4 `7idE...Et6H` (tx executes `UpdateLendingMarket`) | vault 0 matches | 4-of-10, `time_lock` 43,200 s, `config_authority` default |
| Scope feed admin `CzwQ...Hoh7` | Squads v4 `EFZx...be24` (tx executes `UpdateMappingAndMetadata`) | vault 0 matches | **4-of-10, `time_lock` 0**, `config_authority` default |
| Scope upgrade `4R33...kXX7` | Squads v4 `DDJG...D9RM` | vault 0 matches | 5-of-10, `time_lock` 86,400 s, `config_authority` default |
| global admin `A9rQ...exCZ` | Squads v3 `4htL...DpvX` (tx executes `UpdateReserveConfig`) | authority index 1 matches | 4-of-10, no time lock (v3) |
| proposer `6pwk...cEUv` | Squads v3 `9e2E...N2xr` | authority index 1 matches | **1-of-5** |
| emergency council `4VtJ...Ma57` | a Squads v4 tx from `HvYo...fRu4` (5-of-7, `time_lock` 0) lists it, but it is not vault 0 to 15 of that multisig | not resolved | controller open |

The upgrade multisig, market-owner multisig, Scope admin multisig and Scope upgrade multisig
share the same signer set (10 identical keys for `6hhB`, `EFZx`, `DDJG`; 9 of 10 for `7idE`).

### 2.3 Authority paths (from klend and Scope source)

| Path | Holder | Class | Evidence in source |
|---|---|---|---|
| klend program upgrade | `6hhB` 5-of-10, 24 h | full-power | loader-v3 |
| Reserve risk config (LTV, liquidation threshold, limits, oracle mapping `UpdatePythPrice`, `UpdateSwitchboardFeed`, `UpdateTokenInfoScopeChain`) | market owner `7idE` 4-of-10, 12 h | full-power | `is_allowed_signer_to_update_reserve_config`: every mode that is not global-admin-only and not an emergency-council restriction falls to `lending_market_owner` |
| Scope price mapping of the feed used by SOL and USDC reserves (can switch an entry to `FixedPrice` or another source, and re-point TWAP sources) | Scope admin `EFZx` 4-of-10, **0 s** | full-power, oracle | `UpdateOracleMappingAndMetadata` requires `has_one = admin`; `OracleType::FixedPrice = 23` exists |
| Scope program upgrade | `DDJG` 5-of-10, 24 h | full-power, oracle | loader-v3 |
| Protocol fees (take rate, origination, flash-loan fee), `UpdateBlockCTokenUsage` | global admin `4htL` 4-of-10, 0 s | bounded | `is_update_reserve_config_mode_global_admin_only` lists fee modes only; no principal, price or LTV mode |
| Emergency council | `4VtJ` | restrict-only | `is_update_reserve_config_mode_allowed_for_emergency_council` only accepts setting limits to 0, blocking price usage, enabling emergency mode |
| Proposer | `9e2E` 1-of-5 | bounded | allowed only while a reserve is unused, usage-blocked and `proposer_authority_locked == false`; un-blocking usage requires `lending_market_owner` |

### 2.4 Derivation

| Dimension | Rule applied | Inputs | Score |
|---|---|---|---|
| adminKeyScore | min over full-power, non-oracle paths. Upgrade: v4 autonomous, delay >= 24 h = 60 + min(20, 5 (t-1)) = 80. Market owner: 0 < delay < 24 h = 50 + min(20, 5 (t-1)) = 65 | 80, 65 | **65** |
| multisigScore | min over the same paths of min(100, round(15 t + 40 t / voters)) | 5-of-10 = 95, 4-of-10 = 76 | **76** |
| timelockScore | min over the same paths. >= 24 h: 50 + min(30, 10 (days - 1)) = 50. 0 < d < 24 h: round(50 d / 24) = 25 | 50, 25 | **25** |
| oracleAuthorityScore | min over oracle paths of that path's own composite. Scope admin: admin 55, multisig 76, timelock 0 = floor(22 + 22.8 + 0 + 0.5) = 45. Market-owner oracle modes: 56. Scope upgrade: 80/95/50 = 76 | 45, 56, 76 | **45** |
| crossExposureScore | repo formula over tracked groups; intra-protocol key reuse does not count | no signer shared with the Jupiter group | **100** |
| composite | floor(0.4x65 + 0.3x76 + 0.3x25 + 0.5) | | **56** |

Context before qualifying:

- Aggravating: the code path is protected by a 24 h delay and the risk-parameter path by a
  12 h delay, but the **same ten signers** can re-map the SOL and USDC price entries through
  the Scope admin with **no delay**. A price source is as powerful as an LTV change for a
  lending market, so the delay on the other paths does not protect depositors from this one.
  This is exactly the "second authority path without delay" case the grid was written to catch.
- Attenuating: klend rejects a price whose distance to the TWAP exceeds
  `max_twap_divergence_bps` (1,000 for SOL, 300 for USDC), which limits a single-step
  mis-pricing. It does not bound the admin, because the TWAP source is re-mappable by the
  same admin in the same transaction (`MappingTwapEntry`). No score bonus was given.
- Attenuating: all multisigs are autonomous (`config_authority` default), every member has
  the Vote permission, and all 11 distinct member keys across the six Kamino multisigs are on-curve wallets (no hidden nesting).
- Noted, not scored: the proposer authority is effectively a single signer (1-of-5 Squads
  v3). Source limits it to reserves still in their initialization phase.

---

## Methodology gaps found

| # | Gap observed while scoring | Effect on this test | Fix applied in METHODOLOGY.md |
|---|---|---|---|
| G1 | Section 6 gave score **ranges** ("40-60 by t and n"), not a function. Two scorers could publish different numbers for the same state. | Could not produce a single number. | New section 6.1 with deterministic formulas (used above). |
| G2 | No band for a Squads v4 `time_lock` strictly between 0 and 24 h. Kamino's market owner sits at exactly 12 h. | Market owner could not be placed. | Band added: admin 50 + min(20, 5 (t-1)), timelock round(50 d / 24). |
| G3 | The grid assumed one admin key per target. Real protocols have several authorities with very different powers (Kamino has 7). | No rule for which one drives the score. | Section 6.2: classify each path as full-power, bounded or restrict-only; dimensions take the min over full-power paths; the rest are listed as notes. |
| G4 | `oracleAuthorityScore` only described Pyth receiver fields. Kamino consumes prices through an aggregator (Scope) whose admin can re-map sources, including a fixed price. | Oracle dimension not derivable from the written grid. | Section 6.3: min composite over (consumer oracle-config authority, aggregator mapping admin, aggregator upgrade authority). Upstream providers behind the aggregator (for example the Pyth Lazer EMA used as TWAP) are not yet recursed: still open. |
| G5 | Section 4 described `crossExposureScore` as the count of programs sharing an upgrade authority, which contradicts the repo-wide formula (shared root signers across tracked groups). | Would have scored Jupiter 22 programs as cross-exposure against itself. | Section 4 row corrected: repo formula; the programs-by-authority count becomes a published blast-radius note. |
| G6 | Ladder rung 3 said "equals a derived vault PDA of a known multisig" without saying how to find which multisig. | Solved in practice by reading the last transaction that used the authority, then re-deriving. | Resolution procedure written into 3.3, with offline re-derivation mandatory as proof. |
| G7 | "A 1-of-1 Squads multisig scores as an on-curve key" did not cover threshold 1 with several members (Kamino proposer, 1-of-5). | Same risk, rule silent. | Generalised to any threshold of 1, v3 or v4. |
| G8 | Hardcoded authority keys compiled into a program (Jupiter `close_token.operator`) are invisible to account reads. | Found only through the on-chain Anchor IDL `address` constraints. | Discovery step added: read the on-chain Anchor IDL when present; programs without a published IDL get an explicit "hardcoded keys not enumerable" note. |
| G9 | Open point "second indexed RPC" from discovery. `publicnode` refuses `getProgramAccounts`; `api.mainnet.solana.com` is the same operator as `api.mainnet-beta`. | Needed for the 22 and 2 program counts. | `public.rpc.solanavibestation.com` answers the indexed query and returned identical counts; recorded as the second source. |

Still open after this test (carried, not blocking a score):

- Controller of the Kamino emergency council key `4VtJ...Ma57` (restrict-only, so no score impact).
- Recursive scoring of oracle providers behind an aggregator entry (Scope entry 3 is a `MostRecentOf` aggregate whose inputs were not decoded; TWAP entry 455 is Pyth Lazer EMA).
- Programs without an on-chain IDL: hardcoded keys cannot be enumerated from account data alone.
- Upgrade authority of the Squads v3 program-manager `SMPLKTQhrgo22hFCVq2VGX1KAktTWjeizkhrdB1eauK` that appears in Jupiter's upgrade flow was not checked (it records execution state, it does not hold the authority).
