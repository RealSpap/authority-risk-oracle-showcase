# Correction: adversarial review of Kinetiq HIP3StakingManager (2026-09-17)

Same-day follow-up to the Kinetiq `HIP3StakingManager` addition (the first
HyperEVM-native target this project scores: new read helpers and
`score_kinetiq_staking_manager` in `chains/hyperliquid/scripts/
methodology_test.py`, wired into `chains/hyperliquid/scorers.py`, plus
`chains/hyperliquid/data/methodology_test_2026-09-17-kinetiq-staking-
manager.md`). Before committing, this addition went through an
adversarial review workflow (3 independent dimensions -- byte-decode
correctness, on-chain-facts-and-attribution, scorer-code robustness --
each finding piped to an independent verifier), matching this project's
established "no shortcuts" review discipline. Result: **7 findings
returned, 7 confirmed via independent re-verification (fresh live RPC
calls, not just re-reading the original claim), 0 refuted.**

## Fixed

1. **CRITICAL -- the scorer never checked 4 of 5 roles despite its own
   docstring claiming it did.** The first version of
   `score_kinetiq_staking_manager` read only `DEFAULT_ADMIN_ROLE`
   (resolving to a well-formed 4-of-8 Gnosis Safe) and its docstring
   asserted "every other role checked (`MANAGER_ROLE`, `OPERATOR_ROLE`,
   `SENTINEL_ROLE`, `TREASURY_ROLE`) has zero current holders" -- a claim
   that was never actually verified, only assumed to generalize from the
   one role that was checked. Independently re-verified live via fresh
   `eth_call`s before touching any code: the claim is false for 2 of 4.
   `OPERATOR_ROLE` is held by a BARE EOA
   (`0x4459872f33d7e3b61238a6edc7611463c25d82fa`, confirmed via
   `eth_getCode` = `0x`) that can call `withdrawFromSpot(uint64)` and
   `processL1Operations(uint256)`/`processL1Operations()` (confirmed
   present in the contract's own fetched ABI). `TREASURY_ROLE` is held by
   a SEPARATE 4-of-7 Gnosis Safe
   (`0x64bd77698ab7c3fd0a1f54497b228ed7a02098e3`) sharing only 1 of 7
   owners with the "root" Safe. Fixed: `score_kinetiq_staking_manager`
   now queries all 5 roles (`_role_hash`, `ROLE_NAMES`), classifies every
   current holder (`_classify_authority_holder`: Gnosis Safe, bare EOA, or
   an unresolved contract), and takes the MINIMUM across every
   currently-held role per METHODOLOGY.md 6.2's "several authorities per
   target" convention. The bare EOA is the binding constraint:
   `compositeScore` corrected from **50 to 4** (CRITICAL band). This is
   the same discipline this project applies to every other cited number --
   caught only because the docstring's claim was independently
   re-verified rather than trusted.

2. **MEDIUM -- silent fabrication risk in `read_safe_hyperevm`.** The
   original version had no validation: a target address that returned a
   single, unrelated 32-byte word instead of a real ABI-encoded
   `(address[], uint256)` response would silently decode to an empty
   owners list and a nonsensical threshold (e.g. "5-of-0") with no error
   and no warning, unlike `scripts/lib/web3_utils.py::
   safe_owners_and_threshold`'s existing try/except -> `None` ->
   caller's-conservative-fallback convention for the identical pattern on
   the Robinhood Chain side of this project. Fixed: added
   `HyperEvmReadError` and shape/threshold validation (rejects a response
   too short to contain a real ABI encoding, and rejects `threshold == 0`
   or `threshold > len(owners)` as structurally impossible). New tests:
   `TestReadSafeHyperEvmValidation` (4 cases).

3. **MEDIUM -- malformed-address bug ("0x0x...").** `"0x" +
   raw[-40:]` on a too-short `raw` (e.g. `"0x"`, the real `eth_call`
   return value for a no-code address) doesn't raise on Python's
   negative-index slicing -- it silently returns the input unchanged,
   producing a malformed `"0x0x..."` string that would then propagate two
   or three calls further before finally failing with a generic,
   confusing `ValueError` deep inside an unrelated decode step. Fixed: a
   shared `_address_from_hex(raw, context)` helper now raises
   `HyperEvmReadError` immediately, at the actual point of the bad read,
   naming what was being resolved. New tests: `TestAddressFromHex` (4
   cases).

4. **LOW -- `getModulesPaginated` pagination-truncation gap.** A full
   page of modules (the hardcoded `pageSize=10`, same constant this
   project's own `scripts/lib/scorers.py::_safe_guard_and_modules` already
   uses) was silently truncated with no signal that more modules might
   exist beyond the page. Fixed: `read_safe_hyperevm` now returns a
   `modulesPageMayBeTruncated` flag (`True` when the page came back full)
   instead of truncating silently. Not currently triggered by either Safe
   in this target (both have zero modules).

5. **LOW -- 2x byte-count inflation in `data/finding_2026-09-17-
   hyperliquid-hip3-evm-proxy-authority.md`.** Three "N bytes of code"
   figures used the hex STRING length (`len(hexstring)`) instead of the
   actual byte count (`(len(hexstring)-2)/2`), inflating each by roughly
   2x: the admin contract's 1,760 -> corrected to 879; Kinetiq's own
   implementation's 49,018 -> corrected to 24,508; para's implementation's
   16,860 -> corrected to 8,429. Fixed in that file; no score depends on
   these figures.

6. **LOW -- `HIP3L1Write` vs `L1Write` library misattribution.** The same
   finding file attributed all 8 listed CoreWriter-calling functions to a
   single library (`HIP3L1Write`), and implied all 8 were live call paths.
   In fact `HIP3StakingManager.sol` itself only calls
   `HIP3L1Write.addApiWallet` (via its own `setApiWallet`); 4 of the 8
   (`sendCDeposit`, `sendTokenDelegate`, `sendCWithdrawal`, `sendSpot`) are
   actually called via the SEPARATE sibling library `L1Write.sol`, from
   the inherited base contract `StakingManager.sol`
   (`lib/lst/src/StakingManager.sol`, 8 call sites confirmed via grep);
   3 of the 8 (`sendIocOrder`, `sendVaultTransfer`, `sendUsdClassTransfer`)
   are defined in both libraries but not invoked by any contract in the
   source bundle read -- dead code, not a live path. Fixed in that file.
   Doesn't change the finding's conclusion (still no dex-admin CoreWriter
   call found), only the precision of the attribution.

7. **LOW -- unrealistic test fixture.** `MODULES_RESPONSE` in
   `scripts/lib/tests/test_kinetiq_hyperevm.py` used an ABI offset word of
   `4` instead of the realistic `0x40` (64) a real Solidity ABI encoder
   would produce for this exact `(address[], address)` return shape.
   Harmless for `read_safe_hyperevm`'s own decoding (it assumes the fixed
   layout and never actually follows the offset word), but not
   representative of a real `eth_call` response. Fixed.

## Verification

- `python3 -m unittest discover -s scripts/lib/tests`: 128/128 pass (107
  pre-existing before this target existed, matching the count in
  `data/correction_2026-09-17-drift-protocol-adversarial-review.md` +
  the original 10 Kinetiq-HyperEVM tests + 11 new tests added in this
  correction: `TestAddressFromHex` (4), `TestReadSafeHyperEvmValidation`
  (4), `TestClassifyAuthorityHolder` (3)).
- `python3 scripts/validate_all_scorers.py --ecosystem hyperliquid`: 6/6
  targets pass, `OVERALL: PASS`.
- Live dry-run of `score_kinetiq_staking_manager` after the fix:
  `adminKeyScore=10, multisigScore=0, timelockScore=0,
  oracleAuthorityScore=100, crossExposureScore=100, compositeScore=4`
  (down from the unfixed version's `compositeScore=50`).
- Live dry-run of `score_all()`: all 6 Hyperliquid targets still resolve;
  Kinetiq's `l1CappedComposite` is now `min(4, 26) = 4` (the L1 cap has no
  effect, since Kinetiq's own corrected score is already far below it --
  previously `min(50, 26) = 26`, where the cap DID bind).

## Reproduction

```bash
python3 -m unittest discover -s scripts/lib/tests
python3 scripts/validate_all_scorers.py --ecosystem hyperliquid
cd chains/hyperliquid/scripts && python3 -c "
import json
from methodology_test import score_kinetiq_staking_manager
print(json.dumps(score_kinetiq_staking_manager(), indent=2))
"
```
