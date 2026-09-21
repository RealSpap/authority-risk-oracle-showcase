# Finding (2026-09-19): Hyperliquid target #6 was mislabeled kHYPE, is actually kmHYPE

Prompted by re-reading `SUBMISSION.md`'s Hyperliquid narrative while fixing
an unrelated staleness issue: target #6 (`score_kinetiq_staking_manager()`
in `chains/hyperliquid/scripts/methodology_test.py`, added 2026-09-17) is
called "kHYPE liquid-staking manager" both in that bullet and in the
scorer's own docstring, while a genuinely separate, later target (#9,
`score_kinetiq_khype_staking_manager()` in
`chains/hyperliquid/scripts/scoring_build_2026_09_18.py`, added
2026-09-18) is ALSO called "Kinetiq kHYPE StakingManager" -- two different
contract addresses claiming the same product name. Flagged rather than
guessed at; this file records the independent re-verification that
resolved it.

## Addresses

- Target #6 (older): `0x71f0019cc7fa79e4f42587fb7b9a817d8d2429ec`
- Target #9 (newer): `0x393D0B87Ed38fc779FD9611144aE649BA6082109`

## Live on-chain re-verification

Using this project's own existing `methodology_test.py` helpers
(`_eth_call`, `_selector`, `evm`, `_address_from_hex`, `info()`) -- no new
RPC code hand-rolled:

1. Hyperliquid's own spot-token universe (`info({"type": "spotMeta"})`,
   502 tokens, scanned exhaustively): only **`KHYPE`** exists as a real,
   independently-listed HyperCore spot token (index 121, `fullName:
   "Kinetiq Staked HYPE"`, EVM-linked ERC20 at
   `0xfd739d4e423301ce9385c1fb8850539d657c296d`, live `symbol()`="KHYPE").
   **No `KMHYPE` ticker exists in the live spot-token list.**
2. Target #9's proxy exposes a live `oracleManager()` getter resolving to
   `0x192826e470bd65fdc2cb472edd834d096233049b` -- the exact address this
   project's own `scripts/scout_2026_09_17_run2.py::KINETIQ` dict already
   labels `"kHYPE"`'s `oracleManager`.
3. Target #6's proxy exposes a live public getter `kHYPE()` (no
   arguments) resolving to `0x74323cd0db2fd826cadcc90153995f1e2b1d0801`.
   Querying that address live: `name()` = **"Reserve LST for kmHYPE
   accounting"**, `symbol()` = `"kmGHOST"` -- the contract's own on-chain
   code names itself as kmHYPE's internal accounting layer, not kHYPE's.
4. Each proxy points to its own separate `stakingAccountant()` instance
   with genuinely different live exchange rates (target #9's accountant:
   `kHYPEToHYPE(1e18)` = 1.02501; target #6's accountant: 1.01614) --
   confirming two separately-accruing pools, not one contract read two
   ways.

## Primary-source confirmation (Kinetiq's own docs)

`kinetiq.xyz/docs` lists both as separate, real products:

- **kHYPE** ("Kinetiq Staked HYPE") -- the flagship general liquid-staking
  token; stake native HYPE, auto-delegated to top validators via
  Kinetiq's StakeHub. 10% fee on staking rewards.
- **kmHYPE** ("Markets by Kinetiq") -- a distinct liquid-staking token
  specifically for HYPE staked to support HIP-3 markets ("Markets by
  Kinetiq"), yield sourced from deployer/trading-fee revenue rather than
  base validator staking. Live ERC-20 on HyperEVM at
  `0x360C140E5344A1A0593D44B4ea6Fc7C3DAf0C473`, independently listed on
  CoinGecko ("Kinetiq Markets HYPE," ticker KMHYPE) and HyperEVMScan.

Both are real, neither is a typo or an internal-only contract nickname.

## Verdict

Target #6 was scoring kmHYPE's StakingManager the whole time, but its own
docstring (and this project's `SUBMISSION.md` narrative describing it)
called it "kHYPE" -- a real code-level mislabel, not a case of two
individually-accurate docstrings just being confusing to read side by
side. Target #9 is genuinely different and was correctly labeled from the
start.

**This was already partially caught and fixed on 2026-09-18**:
`METHODOLOGY.md`'s changelog, `scorers.py::_apply_kinetiq_oracle_
authority_fix`, `scoring_build_2026_09_18.py`, `deploy/README.md`'s
summary table, and `scout_2026_09_17_run2.py`'s own `KINETIQ` address
table all already use the corrected kHYPE/kmHYPE split. Only the numeric
`oracleAuthorityScore` was ever affected by that earlier correction
(100->7, already applied correctly) -- this is purely a labeling bug, no
score changes follow from this pass.

**What this pass closed**: two stray "kHYPE" labels the 2026-09-18
correction never reached --
`methodology_test.py::score_kinetiq_staking_manager()`'s own docstring
(line ~275), `scorers.py::score_mkts_dex()`'s explanatory comment (lines
~207-208), and `SUBMISSION.md`'s own narrative bullet -- plus a
non-destructive correction note added to the original dated research file
(`chains/hyperliquid/data/methodology_test_2026-09-17-kinetiq-staking-
manager.md`), left otherwise unedited per this project's own convention
of not silently rewriting historical records.
