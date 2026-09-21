# ABI return-data audit, all ecosystems, 2026-09-21

Phase: `maintenance` (transverse). Changes no score, no oracle and no push. Adds a guard that refuses an ABI read whose answer has the
wrong size, and a tool that audits every ecosystem's `score_all()` with it, and records the first result. Measured on the tree at
`2324848` plus this change; the patch is delivered on a later base, and the commits in between change no scoring logic (checked when
the patch was rebased: only comments and docstrings in the scorers they touch).

## Why

`eth_abi.decode(["uint256"], data)` returns the first 32-byte word of `data` and ignores the rest, and web3.py's
`contract.functions.f().call()` goes through the same decoder. A getter that returns a struct or several values, read with a
single-value ABI, therefore does not revert and does not raise: it hands back the first word as if it were the answer. It
happened on 2026-09-20: `getScore(address)` returns the `AuthorityScore` struct, was read as `uint256`, gave `adminKeyScore = 3`
instead of `compositeScore`, and a verification "agreed" on the wrong number
(`data/rotation_audit_2026-09-20-robinhood-chain-index16.md`, the finding that opened this task on the tracker). The same decoder is behind
every scorer read in this repository, and a scorer reading an authority getter with an ABI that is too short would produce a
confident wrong score.

## What was added

- `scripts/lib/abi_returndata_guard.py`: compares the return data with what the declared outputs require. All-static outputs
  (uint, int, bool, address, bytesN, static arrays and tuples of them) must be exactly the sum of their sizes (more means a struct or
  extra outputs were read with a shorter ABI, fewer means the data is not what the ABI says). Outputs with a dynamic type must cover
  their head, and what was decoded must re-encode to exactly the length that came back: a getter returning `(address[], uint256)` read
  as `address[]` decodes without error and drops the `uint256`, but its canonical encoding is shorter than the data, which is how it is
  caught. Solidity and Vyper emit canonical encodings, and an answer whose canonical re-encoding has a different length than the one
  returned is refused (the target degrades instead of an unusual layout being trusted). Empty data for a function with outputs is reported as its own kind (an address without code answers
  an `eth_call` with empty data instead of reverting). It patches `eth_abi.codec.ABICodec.decode` (web3's contract calls) and the
  module-level `eth_abi.decode`, either to RECORD every mismatch with the file and line of the caller (nothing changes for the caller) or
  to RAISE `ReturnDataSizeMismatch`, a `DecodingError`, so web3 turns it into its usual `BadFunctionCallOutput`. Empty data is left to
  the original decoder, which already raises. A refusal is logged once per call site and output types to stderr (`ABI return-data guard: REFUSED at
  file:line`).
- `scripts/audit_abi_returndata.py`: runs every ecosystem's `score_all()` live, each in its own subprocess, four at a time by default
  (`--workers`; the table and isolation of `validate_all_scorers.py`), with the guard in record mode. An ecosystem that cannot be run, or
  where `score_all()` skipped a target after a failed read, is reported FAILED (partial audit), never clean.
- The guard is installed in raise mode when any scorer imports `scripts/lib/web3_utils.py` (Ethereum L1, Arbitrum, Base, Monad, Plasma,
  Robinhood Chain) and by the Tempo and Hyperliquid scorers, which read through their own primitives. Solana and Zcash scorers decode no ABI.
  A future ABI mistake is now refused instead of returning a first word. Every helper in `web3_utils.py` and Tempo's own `call()` swallow
  the exception and return `None`, so the effect is an unresolved read (the target degrades) plus the stderr line, not a crash: what
  disappears is the confident wrong number.

## Result (score_all() at `2324848` plus this change, run in record mode)

| Ecosystem | Entries scored | ABI decodes checked | Size or layout mismatches | Empty-data probes |
|---|---|---|---|---|
| Robinhood Chain | 62 | 287 | 0 | 4 |
| Ethereum L1 | 19 | 167 | 0 | 0 |
| Arbitrum | 10 | 123 | 0 | 4 |
| Base | 9 | 60 | 0 | 0 |
| Solana | 18 | 0 (no ABI) | 0 | 0 |
| Hyperliquid | 15 | 17 (see below) | 0 | 0 |
| Tempo | 14 | 932 | 0 | 0 |
| Zcash | 6 | 0 (no ABI) | 0 | 0 |
| Plasma | 9 | 103 | 0 | 0 |
| Monad | 9 | 69 | 0 | 0 |

1,758 ABI decodes checked, no silent truncation, no dropped value and no short answer on any path a live run takes today, every ecosystem
scored completely (no skipped target). The eight empty-data occurrences are two records (four each, Robinhood Chain and Arbitrum) from one
call site, `scripts/lib/web3_utils.py:162`, `getOwners()` on an address that has no code (a bare EOA probed to see whether it is a Safe):
web3 raises `BadFunctionCallOutput`, the helper returns `None`, the caller treats the address as not a Safe. Nothing in the scorers takes
an empty answer for a success.

Hyperliquid is prevention, not coverage: its reads go through `chains/hyperliquid/scripts/methodology_test.py::_eth_call` (a raw
`eth_call` and hex slicing, with its own shape checks such as `HyperEvmReadError`), so 15 entries produce only 17 ABI decodes. The
guard is installed there for future decodes; it does not check today's reads.

## Neutrality (live, the same public reads on two trees)

The guard changes a result only when an answer has a wrong non-empty size or layout, and the record-mode run above saw none, so it
cannot change a score. Checked anyway: `score_all()` of every ecosystem run live on the tree at `2324848` (without the guard) and on
the same tree with it, the six sub-scores of every target compared (`runs/2026-09-20-scorer-fixes/live_diff.py`,
`check_abi_neutrality.py`), each ecosystem run on its own so that the public RPCs are not overloaded.

| Ecosystem | Targets compared | Sub-score differences |
|---|---|---|
| Robinhood Chain | 62 | 0 |
| Ethereum L1 | 19 | 0 |
| Arbitrum | 10 | 0 |
| Base | 9 | 0 (see below) |
| Solana | 18 | 0 |
| Hyperliquid | 15 | 0 |
| Tempo | 14 | 0 |
| Zcash | 6 | 0 |
| Plasma | 9 | 0 |
| Monad | 9 | 0 |

One transient difference is kept here rather than hidden: in the first pass over Base, Aave V3 Base read `crossExposureScore` 80 on the
tree without the guard and 100 with it (composite 71 on both). That value comes from a live read of the Aave guardian Safe on Arbitrum
inside Base's own run, and a failed read makes the overlap unfound, which reads as 100. Six further one-at-a-time runs of Base (three per
tree) and a rerun through the comparison tool all gave 80 on both trees and no difference; no refusal line of the guard was logged.

Two things a first, fully parallel attempt taught, kept because they matter beyond this change. Running twenty ecosystem runs at once
against the public RPCs made reads fail at random: four Base targets differed between the two trees and, just as much, between two
runs of the SAME tree (Uniswap V3 Factory on Base read 85 in one run and 38 in another, Morpho Blue 55 or 8), and a Robinhood target
(Fables PoolRegistry) and five Hyperliquid entries were missing from a run. So a score computed while the public RPC is rate-limiting
can silently be a floor instead of the real value: the helpers in `scripts/lib/web3_utils.py` turn every exception, a revert and a
rate-limit alike, into `None`, and a persistent `None` degrades the target (their docstrings say the caller cannot tell the two apart).
That is a separate robustness issue, tracked as its own card on the tracker.

## Not claimed

- This covers the code paths a live run executes today, for the targets and shapes they have today. A wrong ABI in a branch that is not
  taken now would be caught when that branch runs (the guard is on), not by this audit.
- A wrong ABI of the right size is not detectable by size: reading `totalSupply()` where the contract's meaning is `totalAssets()` is
  a semantic error, not a size error.
- Raw `eth_call` sites that do their own slicing bypass the decoder and are not covered: the whole Hyperliquid read path (above),
  `chains/plasma-ecosystem/scorers.py` reads the self-identification getter `0x54fd4d50` as raw bytes for an informational note (an
  empty answer gives an empty note, no score depends on it) and `chains/plasma-ecosystem/scripts/fluid_signers_check.py` slices the last 20
  bytes of an answer in a read-only check script.
- The layout check compares LENGTHS: it refuses a dynamic answer whose canonical re-encoding has a different length than the one
  returned. Solidity and Vyper emit canonical encodings and none was refused today; a contract with an unusual hand-written layout
  would make its target degrade to unresolved, which is the safe direction. A non-canonical layout of the same total length is not
  seen, and one case cannot be seen by any check on the bytes: an output `(uint256 = 32, T)` read with the ABI `[T]` is itself a valid
  canonical encoding of `[T]` (the first word reads as the offset, the rest re-encodes to the same bytes). No call site of the
  repository declares a single `bytes` or `string` output.
- Solana and Zcash read paths (JSON-RPC account data, lightwalletd) have no ABI and are outside this audit.
