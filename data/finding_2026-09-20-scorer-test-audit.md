# Scorer test audit, 2026-09-20: what executing the untested scorer bodies found

Phase: cross-ecosystem (Zcash, Solana, Ethereum L1, Base, Plasma). Changes two computations (both provably
value-preserving on every published score) and pins the rest as tests. Nothing is re-pushed and no anchor changes.

## Why

Coverage measured over `chains/` and `scripts/` showed 19 scorer functions whose bodies no unit test executed, only
their `def` line: `score_marinade`, `score_solend_dao_governance`, `score_meteora_damm_v2`, `score_sparklend_pool`,
`score_compound_v3_cusdc`, `score_uniswap_v4_pool_manager`, `score_wbtc`, `score_moonwell_comptroller_base`,
`score_aerodrome_slipstream_clfactory`, `score_fluid_liquidity_plasma`, and Zcash's `score_all`, `score_ext_zec_omft`,
`score_maya_asgard_vault`, `score_l1`, `cross_exposure`, among others. They were checked only by live runs.

## Result

Statement coverage of `chains/` and `scripts/` went from 70.4% (2,303 of 7,789 statements not run) to 77.3% (1,771 not run). Each of the 19 targeted functions now has every statement executed. The suite went from 1,087 to 1,643 tests, all passing, with 20 `expectedFailure` tests that document the open findings below and 6 skips (tests that need a key file). After the arithmetic fixes, the Zcash ARO2 commitment still re-derives from a live `score_all()` run (`attest_scores.py verify --live`: MATCH).

## Method

One author per scorers file wrote a new offline test file with the chain reads patched. Expected values had to come
from documented real observations or from hand arithmetic on the written formula, never from the function's own
output. A separate verifier then sabotaged a COPY of each scorer (at least three realistic mutations per function:
a threshold, a comparison, a swapped sub-score, a dropped degrade path, a deleted note) and checked that the tests
noticed, and the author repaired the surviving mutants. Tests: `scripts/lib/tests/test_{zcash,solana,ethereum_l1,base,plasma}_scorer_bodies.py`.

| File | Tests | Mutations tried | Killed before repair | Non-equivalent survivors before repair |
|---|---|---|---|---|
| `test_zcash_scorer_bodies.py` | 96 | 171 | 86% | 16 |
| `test_solana_scorer_bodies.py` | 108 | 129 | 84% | 8 |
| `test_ethereum_l1_scorer_bodies.py` | 155 | 166 | 90% | 4 |
| `test_base_scorer_bodies.py` | 88 | 113 | 88% | 3 |
| `test_plasma_scorer_bodies.py` | 104 | 82 | 77% | 15 |

The findings below come from the authoring pass. Every one is pinned by a test (a characterization test, or an
`expectedFailure` test that asserts the documented behaviour). The code lines behind the Ethereum L1 timelock and
multisig items, Fluid's `multisig = 100`, Base's unconditional forwarder note and the two fixed items were re-read
by the maintainer's session; the rest is as reported by the authors and has not been independently re-derived.

## Fixed in this change

- **`_composite` in nine places** (`chains/{base-ecosystem,plasma-ecosystem,ethereum-l1,solana,monad,arbitrum-ecosystem,zcash}/scorers.py`,
  `scripts/lib/scorers.py`, `scripts/validate_all_scorers.py`) evaluated `floor(0.4a + 0.3m + 0.3t + 0.5)` in binary floating
  point. That is one LOWER than the exact value for 2,054 of the 1,030,301 possible `(a, m, t)`, for example `(0, 1, 24)`
  gives 7 instead of 8. Now `(4a + 3m + 3t + 5) // 10`. Value-preserving on every published score: all 123 live EVM oracle entries
  read on 2026-09-20 (Robinhood 58, Ethereum L1 15, Arbitrum 9, Base 9, Plasma 9, Tempo 14, Monad 9), the 7 Zcash records
  and the 58 entries of `api/scores.json` are unaffected, so no oracle needs a re-push and the Zcash commitment is unchanged.
  Guarded by `test_composite_exact_arithmetic.py` (a `Fraction` reference, checked on the 2,054 affected triples).
- **Solana council threshold** (`score_marinade`): `math.ceil(pct / 100 * total_weight)` is off by one when the float product
  lands just above an integer (28% of 25 gave 8, the exact value is 7). Now `-(-pct * total_weight // 100)`. Marinade's live
  50%-of-5 is unaffected.

## Open: possible bugs (mostly degraded or dormant paths; live published scores reproduce)

| Ecosystem | Function | Finding |
|---|---|---|
| zcash | `score_ext_zec_omft` | **Fixed (#109: the fallback is now 5/16, composite 7, below the confirmed 1-of-3 path).** The degraded fallback when no TokenDepositer path resolves (admin_key, multisig = 20, 20; composite 14) scores ABOVE the live-confirmed weakest real path (1-of-3 Requestor group = 5/18, composite 7). Documented as a dormant inversion; only dormant because the live read succeeds every run. Kept as an expectedFailure test asserting the documented invariant (fallback <= 5/18), plus a separate test pinning today's 20/20. |
| solana | `score_marinade / _resolve_legacy_serum_multisig (same gap in _resolve_squads_v3 used by score_meteora_damm_v2)` | **Fixed (#109: Meteora DAMM v2 and Marinade now score None as renounced, the safest band).** A renounced (None) program upgrade authority is treated as a failed read and scored 20/20/0 with a 'MISMATCH, degrading' note, instead of the safest band 100/100/100 that METHODOLOGY.md 6.1 assigns to None. The same 2026-09-17 bug (Jupiter v6, Squads v4 via none_means_renounced=True) was fixed there but not for the legacy-multisig and Squads v3 helpers. Dormant today (Marinade's authority is 551FBX..., not None; in Meteora the hardcoded ADMINS[] 5/0/0 masks it). For Marinade the documented value would be combined 70/69/0, composite 49, versus 20/20/0, composite 14 computed. Test kept asserting the documented value and marked expectedFailure. Production change needed if desired: add a ... |
| ethereum-l1 | `score_uniswap_v4_pool_manager` | **Fixed (#111: a delay of at least 172800 s is now required, a project decision matching Compound and SparkLend, METHODOLOGY only says 60-75 by length).** timelockScore is 75 for ANY delay() that reads, even 0 or 1 hour. The docstring quotes 'delay = MINIMUM_DELAY = 2 days' and METHODOLOGY.md says only a confirmed real delay scores 60-75, and the sibling scorers score_compound_v3_cusdc and score_sparklend_pool require delay >= 172800. score_uniswap_v3_factory has the same 'delay is not None' rule. Pinned by a characterisation test so a fix is a deliberate test edit. |
| ethereum-l1 | `score_uniswap_v4_pool_manager` | **Fixed (#111).** Timelock credit is not gated on PoolManager.owner() being the known Uniswap Timelock. If owner() were a different contract that answers delay(), admin() and quorumVotes(), adminKeyScore drops to 20 with the note 'owner is not the known Timelock' yet timelockScore stays 75, because delay is read from whatever address owner() returned. |
| ethereum-l1 | `score_sparklend_pool` | **Fixed (#111: credit now needs a resolved root and a read FreezerMom ward).** timelockScore 60 is credited even when the SparkProxy -> MCD_PAUSE_PROXY -> MCD_PAUSE chain did NOT resolve, because delay() is read from the hardcoded MCD_PAUSE constant, not through the resolved chain. With PoolAddressesProvider.owner() replaced by an EOA, or MCD_PAUSE_PROXY.owner() pointing elsewhere, the scorer publishes admin 20 with the 2-day Sky delay still credited (composite 56). |
| ethereum-l1 | `score_compound_v3_cusdc` | **Fixed (#111 for Compound, SparkLend and V4, which now score multisig 20 when the root is not confirmed, and #110 for Fluid. Still open in `score_uniswap_v3_factory` and `score_makerdao_sky_pause`, which keep the old rule).** multisigScore is hardcoded 100 ('not applicable, root is a DAO') in the degraded branches of score_compound_v3_cusdc, score_sparklend_pool and score_uniswap_v4_pool_manager, so a run where nothing resolves still publishes composite 38, whereas score_wbtc's unresolved floor is 10/20/0 composite 10 and Ethena/Morpho floors also lower multisig. METHODOLOGY.md reserves 100 for 'the root is a real, active DAO'; an unresolved root is not confirmed to be one. |
| ethereum-l1 | `score_compound_v3_cusdc` | The upgrade-path convergence check uses HARDCODED CometProxyAdmin and Configurator addresses. The docstring says the Comet proxy's EIP-1967 admin slot 'resolves to CometProxyAdmin 0x1EC63B58...', but the scorer never reads that slot, so a proxy-admin swap on the Comet proxy would go unnoticed and the gate would keep reading the old ProxyAdmin. The Configurator is likewise not tied to the Comet by any read. |
| base-ecosystem | `_uniswap_direct_forwarder_score` | **Fixed (#109: the note is now emitted only when both addresses are compared and equal).** The note 'Same forwarder and same L1 Governance Timelock as the already-tracked Uniswap V3 Factory (Base): one DAO root for V2/V3/V4 on Base' is appended unconditionally. Nothing compares the forwarder or the L1 timelock with the V3 Factory's (0x31FAfd48...72A9 / 0x1a9C8182...35BC). A different forwarder with a different L1 timelock passes every gate (slot 0 predeploy, resolved delay and admin) and gets the confident 80/100/75/85 with the note still asserting sameness. Scores are not affected, but published evidence text asserts a fact the code never checked, the same defect class already fixed on 2026-09-18 for Aerodrome's 'zero owner overlap' note. |
| base-ecosystem | `score_aerodrome_slipstream_clfactory` | A non-Safe owner() is scored with the 'unresolved contract' floor (adminKey 20, composite 8), whatever it is. METHODOLOGY.md says a bare EOA scores 2-10 and 20 is only for an unresolved contract. The scorer never reads bytecode, so an owner rotated to a bare EOA would score better (20) than the methodology allows. Same pattern in score_morpho_blue (lines 138-140) and score_aerodrome_poolfactory (lines 351-355). No published score is affected today (owner is a real 3-of-7 Safe). |
| plasma-ecosystem | `score_fluid_liquidity_plasma` | **Fixed (#110: unresolved admin now scores 20/0/0).** multisigScore is hard-coded to 100 for every outcome, including an unreadable getAdmin(). A transient RPC failure or revert on getAdmin() therefore scores (adminKey 20, multisig 100, timelock 0), composite 38, instead of the ecosystem's unresolved floor (20, 0, 0), composite 8, while the note calls it a 'conservative score'. |
| plasma-ecosystem | `score_fluid_liquidity_plasma` | **Fixed (#110: bare EOA 5/0/0, plain contract 20/0/0, Safe by the METHODOLOGY formula).** The same unconditional multisig=100 (and adminKey 20) is used when getAdmin() is a bare EOA, a plain contract, or a real Gnosis Safe, contradicting METHODOLOGY. A bare EOA gets adminKey 20 (documented band 2-10) and multisig 100 (documented 0); a 3-of-5 Safe gets multisig 100 (formula gives 55) and adminKey 20 (Aquila's 3-of-4 Safe branch in the same file scores 50). |

## Open: documentation that no longer matches the code

- **zcash / `score_maya_asgard_vault`**: **Fixed (#109: the scorer now discloses it in a note, never as a score input).** METHODOLOGY.md 4.7 says the halted/paused status of the ZEC chain is 'disclosed in the scorer's notes (via /mayachain/inbound_addresses)'. The scorer never calls inbound_addresses() and none of its notes mentions the halt (METHODOLOGY 3.6 records halted:true, chain_trading_paused:true), so either the disclosure is missing from the scorer or the methodology row is stale. Kept as an expectedFailure test.
- **zcash / `score_fund`**: **Fixed (#109: docstring corrected).** The docstring says the scorer 'raises rather than silently trusting one source' when the two lightwalletd operators disagree on (m, n) or pubkeys. The code does not raise: it returns the unresolved-P2SH floor (5/16, composite 7, _degraded=True) with a MISMATCH note. Behaviour matches METHODOLOGY 4.2; the docstring is stale.
- **zcash / `test_zcash_fund_and_l1_scorers.ADDRESS`**: Another test file labels ADDRESS = 't3ZIfZXe4gtWH3pdKbRnh2wgc2CqLLKn4Hh' as the 'real ZIP 271 lockbox address'. The real one is t3ev37Q2uL1sfTsiJQJiWJoFzQpDhmnUwYo (scorers.FUNDS, METHODOLOGY 3.2); the string appears nowhere else in the repo. Harmless to that file's tests (find_multisig_spends is patched) but the comment is wrong. Not edited (outside my assigned file).
- **solana / `score_solend_dao_governance`**: Two documents predate the 2026-09-19 reconciliation of the Realms timelock (hold-up time alone) and now disagree with what the scorer computes. (1) methodology_test_2026-09-17-solend-governance.md still derives Path B timelock = 70 (from 72h voting) and 'timelock = min(0, 70, 0)'; the current formula gives Path B timelock 0 for Solend's real hold-up 0 (voting 259200s no longer feeds it), so the scorer's note reads ...
- **ethereum-l1 / `scripts/lib/tests/README.md`**: The 'What's intentionally NOT covered' section says the ~50 individual scorer functions (score_uniswap_v3_factory, score_aave_v3_pool, ...) 'aren't unit-tested here'. That is no longer true: test_ethereum_l1_scorers.py and the per-ecosystem *_scorers.py files test them, and this file executes four more bodies against published rows. Not edited (outside my assigned file).
- **base-ecosystem / `score_all`**: Docs still describe a 5-target set while SIMPLE_SCORERS has 9 entries: module docstring 'first 5 flagship targets', _composite docstring 'any of these 5 targets', score_all comment 'this whole 5-target batch'. Also scripts/lib/tests/README.md says the individual scorer functions 'aren't unit-tested here', which is no longer true (test_base_ecosystem_scorers.py and about twenty sibling files test them).
- **plasma-ecosystem / `score_fluid_liquidity_plasma`**: **Fixed (#133: the scorer now reads the Avocado and Safe signer sets, docs updated).** The 'proposer/executor signer strength UNRESOLVED' disclosure (docstring, emitted notes, README row, dashboard/index.html row 6) is stale. The sibling Arbitrum work resolved it on 2026-09-19 for the SAME proposer address, read live on Plasma: an Avocado Multisig with 12 signers / 6 required; the executor is a Safe v1.4.1 3-of-5. The Plasma scorer never tries signers()/requiredSigners() and never probes the executor ...
- **plasma-ecosystem / `score_fluid_liquidity_plasma`**: **Fixed (#133: docstring corrected).** The docstring gives the proposer and executor bytecode sizes as '~190 and ~150 bytes', but the data note records 327 and 171 bytes, re-measured with web3.py (the same get_code call the scorer makes, and the value its note prints).

## Open: oddities (behaviour worth knowing, pinned by tests)

- **zcash / `score_ext_zec_omft`**: Only the FIRST non-sputnik grantee and the FIRST sputnik-dao grantee of Role::TokenDepositer are evaluated (next(...) at lines 572-573). Any further grantee is silently dropped from the weakest-key comparison although the docstring says any one grantee alone can mint (OR grant). Dormant today (2 grantees). A grantee is also ...
- **zcash / `score_ext_zec_omft`**: access_key_count() returns every access key of the bare account (near_read.py: result['keys']), regardless of permission, while the note says 'full-access key(s)'. A zero-key account gives (k=1, n=0): adminKey 5 but multisig 20*1-(0-1)=21, higher than the single-key (1,1) value 20.
- **zcash / `score_ext_zec_omft`**: The Requestor branch indexes requestor['vote_policy'] and requestor['kind']['Group'] without guarding, so a malformed Requestor role raises KeyError/TypeError and skips the whole target instead of degrading with a note, although the line just after uses .get('vote_policy', {}) tolerance.
- **zcash / `score_l1`**: When both operators return None for k50/k25 (attributed addresses never exceed the threshold), the identical-on-both-operators success note is still emitted with the text 'None payout addresses exceed 50%, None exceed 25%', then a second note says the read did not resolve and multisig is degraded to 20. Correct scores, ...
- **zcash / `score_maya_asgard_vault`**: An active vault with an empty membership list (maya_read.active_zec_vaults defaults membership to []) is scored n=0, k=0: adminKey 5, multisig 16, composite 7, i.e. the unresolved floor, but the notes only say 'membership n=0' / 'k=ceil(2n/3)=0 of n=0' with no warning that the signer set is missing.
- **solana / `score_marinade`**: Council 'voters' is the total token WEIGHT (mint supply), not the number of distinct signers. METHODOLOGY.md 6.1 defines t as the threshold 'in signers when countable' and scores any t=1 as a bare key (5/0/0). If one member held at least the threshold weight (e.g. 3 of 5 tokens), a single key could pass proposals but the scorer ...
- **solana / `score_solend_dao_governance`**: prog.get('upgrade_authority') is used directly for the governance program's upgrade authority. sol_read.read_program only sets that key when the program is owned by loader-v3, so a program owned by any other loader yields no key, .get returns None, and the scorer publishes the renounced/safest band (100/100/100) for it, i.e. an ...
- **ethereum-l1 / `score_compound_v3_cusdc`**: MINIMUM_DELAY is read and printed in the notes but never scored. The docstring and the inline comment ('real 2-day delay with a 2-day floor') present the floor as part of the reason for the 60, yet MINIMUM_DELAY = 0 still yields 60. Separately, the pauseGuardian Safe's threshold (and the docstring's 'no module, no guard') is ...
- **ethereum-l1 / `score_sparklend_pool`**: Several facts the docstring relies on are not read live: SparkProxy's other wards (ESM, StarGuard) and any newly added ward, FreezerMom.authority() (the Sky Chief hat that can also freeze instantly), and the KillSwitchOracle/CapAutomator RISK_ADMIN holders. The claim 'every privileged SparkProxy path is rooted in the SAME ...
- **ethereum-l1 / `score_compound_v3_cusdc`**: **Fixed (#111 for Compound, SparkLend and V4, still open in the Base notes).** Cosmetic: an unread delay renders in the notes as 'Nones' (the f-string appends 's' to None), e.g. 'Timelock.delay() = Nones ; MINIMUM_DELAY = Nones'. Same in SparkLend ('MCD_PAUSE.delay() = Nones') and V4 ('Timelock.delay() = Nones'). Tests assert only the 'delay() = None' prefix so a cosmetic fix will not break them.
- **ethereum-l1 / `score_makerdao_sky_pause`**: Found while building the SparkLend sibling test (not one of the four assigned functions): hat = call_raw(w3, authority, ...) is not guarded against authority being None, unlike every call in the four functions under test. With the real call_raw a None address raises inside its try, returns None, and burns _retrying's sleeps ...
- **base-ecosystem / `score_aerodrome_slipstream_clfactory`**: When the three roles disagree (or a fee manager read fails) the degraded branch also sets rootSafeOwners to [], even though owner() was read and resolved as a real Safe. _apply_intra_base_overlap then skips the target, so if Slipstream's fee managers ever moved off the owner Safe, the fact that owner() is still the same 3-of-7 ...
- **base-ecosystem / `score_moonwell_comptroller_base`**: The note "only trusted sender is Moonwell's MULTICHAIN_GOVERNOR_V2_PROXY (chains/1.json): True" reads as if no other sender exists, but only Wormhole chain 2 is queried (allTrustedSenders(2)). A sender registered for chains 16/23/24/30 or any other id would go unseen; the maintenance doc says those ids were checked by hand ...
- **base-ecosystem / `score_moonwell_comptroller_base`**: The note states 'pauseGuardian (3-of-5 Safe) and borrow/supplyCapGuardian (2-of-4 Safe) on the Comptroller are bounded pause/cap roles' as fixed prose. The function never reads pauseGuardian or the cap guardians, and no data file in the repo records those Safe sizes (only dashboard/index.html line 759 repeats them). If those ...
- **base-ecosystem / `score_moonwell_comptroller_base`**: The guardian, which per the docstring can pause once and then fast-track a VAA past the delay, has no effect on any sub-score: an unresolved guardian, a guardian that is a bare EOA, or guardianPauseAllowed False/None all give the identical 65/100/50/71. Unlike score_aave_v3_base and the Aerodrome scorer, there is no 'NOT ...
- **base-ecosystem / `_uniswap_direct_forwarder_score`**: When a numeric read fails, the notes format the f-string as '...delay() = Nones' (f"{l1_delay}s" with None), and likewise 'proposalDelay() = Nones' in the Moonwell scorer. Cosmetic, but the phrase ends up in published evidence text.
- **plasma-ecosystem / `score_fluid_liquidity_plasma`**: **Fixed (#110: the slot is read at run time and the note reports identical, different, unread or not attempted).** The emitted note claims getAdmin() was 'cross-checked live via a raw eth_getStorageAt read at that slot, which returned the identical address', and the docstring says the same, but the function never performs that read. read_slot_as_address is imported and used by other scorers (Pendle, Arbitrum Fluid) but not called here, so ...
- **plasma-ecosystem / `score_fluid_liquidity_plasma`**: **Fixed (#110: the match is stated only when the delay equals 86400).** The docs-vs-chain delay cross-check is a hard-coded sentence: the timelock note always says the live delay 'matches deployments.md's documented constructor arg (86400) ... exactly', whatever getMinDelay() returns. A live 48 h delay is still reported as matching the docs (and still scores 70).
- **plasma-ecosystem / `score_fluid_liquidity_plasma`**: **Fixed (#110, and the self-administered conclusion is conditional too).** The emergency-bypass note is printed unconditionally: 'canceller power sits on the same address as PROPOSER_ROLE only ... no separate zero-delay cancel path found', directly after a read that can show the executor also holds CANCELLER_ROLE. The two canceller reads are never used in the score, so timelockScore stays at the ...
- **plasma-ecosystem / `score_fluid_liquidity_plasma`**: **Fixed (#110).** Notes mislabel degraded reads. With getAdmin() unresolved (None) the code size is skipped (`if admin else b""`) and the note says 'getAdmin() target code size = 0 bytes (NO CODE -- a bare EOA)', although nothing was resolved. An empty Liquidity bytecode read is also reported as '0 bytes of real deployed bytecode ... confirms ...
- **plasma-ecosystem / `score_fluid_liquidity_plasma`**: **Fixed (#133 for (2), a zero delay is no longer confirmed, and (1) is still open, now as a flat 55).** Timelock and admin scoring inputs are looser than the comments claim. (1) timelockScore is 70 for ANY positive delay, so a 1 second delay scores like 24 h, although METHODOLOGY says 60-75 'depending on length'. (2) chain_closed does not require delay > 0, so a 0 s timelock keeps adminKey 40 (only timelock drops to 0). (3) ...

## What to do with them

## Status after the follow-up fixes

The same day the marked items above were fixed through maker-checker (#109 Zcash, Solana, Base, #110 Plasma, #111
Ethereum L1), each with independent verification on fresh clones: the suite green, every scorer hunk sabotaged
on its own and caught by a test (the only survivors are a docstring and pure refactors), and the live scores of 52
targets across 5 ecosystems identical before and after, so no oracle needs a re-push and no anchor changes. Left open on
purpose: the two `expectedFailure` tests (Solana council weight versus signers, Plasma delay tiers), the Ethereum scorers'
inability to tell a bare-EOA root from an unresolved one (both get multisig 20 where METHODOLOGY gives 0 for a known EOA),
V3 and MakerDAO still on the old multisig and timelock rules, and everything not marked above.

## What to do with the rest

Everything unmarked is still open, because each is a scoring or wording decision rather than
a bug with one right answer (for example, what floor an unresolved root should get, or whether a delay under a day earns
timelock credit). Each pinned test says which decision it encodes; when a decision is taken, editing that test is the
deliberate step, and an `expectedFailure` turning into an unexpected success shows a fix landed. The natural route is
the normal one: a scorer change proposed through maker-checker with independent verification.

