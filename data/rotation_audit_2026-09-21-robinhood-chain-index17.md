# Rotation audit (2026-09-21): Robinhood Chain, tracked target index 17

`rotation_state.json -> robinhood-chain -> last_audited_target_index` was 17
going into this run. Index 17 is **AMD • Robinhood Token**,
`0x86923f96303D656E4aa86D9d42D1e57ad2023fdC`, the fifth and last member of the
`stock_tokens` group (`scripts/lib/scorers.py::STOCK_TOKEN_TARGETS`,
`scripts/lib/signer_overlap.py` l.210). With it, the whole tokenized-stock
family (indices 13 to 17: TSLA, AMZN, PLTR, NFLX, AMD) has now been through
one full rotation.

**Result: no divergence. Nothing pushed, nothing to re-push.** The published
entry is `3 / 0 / 0 / 100 / 100 / 1`, `lastUpdated` 1789934379, methodology
hash `keccak256("authority-risk-oracle-v3")`, and a live re-derivation of the
repository's own scorer reproduces all six fields.

## Part 0 - CORRECTION: this run's first attempt proved nothing

An independent verifier scored the first attempt 2/3 and refused it. **What was
wrong was the evidence, not the figures** - the numbers the first attempt
reported are the same ones re-derived here. That distinction matters, so it is
recorded plainly rather than quietly fixed:

| # | First attempt's evidence | Why it proved nothing |
|---|---|---|
| 2 | `getScore` read with selector `0x0b07e346` | Not a getter of this contract. `keccak("getScore(address)")[:4]` is `0xd47875d0`. Replayed, the `eth_call` reverted and the command exited 1 - the correct figures beside it came from somewhere else. This is the **same family** as the ABI mistake that got action rejected on 2026-09-20, on the very day the transverse fix (action) is pending approval. |
| 4 | Showed a hardcoded address had no bytecode | Reads no `owner()` and no `hasRole()`. Being codeless says nothing about holding a role. The root was presupposed from `scorers.py` l.366, not derived. |
| 5 | `floor(0.4*3+0.3*0+0.3*0+0.5)=1` from typed constants | A tautology. No chain read, so no comparison to a "published value" was possible. Cousin of the reverse-engineered `max()` formula rejected on 2026-09-20. |
| 6 | `echo` of the conclusion | No verification at all. Dropped outright this time. |

Two format faults came with it, both already on record as recurring:

* the claims file had **no header line**, so `lire_journal()` swallowed the
  first claim as the header and reported "0 exploitable steps" - a completely
  empty green;
* claim 2's command embedded about ten `;` inside a python one-liner, which
  shifts the columns of any consumer that splits on `;`
  (`feedback_claims_file_semicolons`).

A third fault is subtler and is the reason the verifier's own first pass came
back green: **`MOTS_SUCCES_AFFIRMATION` in
`succes_fabrique_agent/fabrication.py` (l.29-34) is a French-only vocabulary.**
The first attempt's claims were written in English ("verified", "retrieved",
"matches"), so not one of them was recognised as a success claim and the tool
had nothing to contradict. The claims for this attempt are written in French
for exactly that reason, and the green was checked with a positive control:
forcing every exit code to 1 makes the tool report 7 fabrications, so the
7-step green is a real result and not an empty one.

## Part 1 - How index 17 was re-derived

Seven replayable commands, one per claim, in
`authority-risk-oracle-multichain-pipeline/runs/2026-09-21/robinhood-chain/claims_tentative2.txt`.
Each is a script on disk (no `;` inside any command), stdlib-only except the
two that import the repository, and each exits non-zero if its own assertion
fails. `rh_lib.py` carries a keccak-256 implemented from scratch and
self-tested on import against two published vectors, so **every selector and
storage slot below is derived from its signature text rather than quoted**.

1. **Identity.** `trackedTargets(17)` read on two independent testnet RPCs
   (`rpc.testnet.chain.robinhood.com`, `robinhood-testnet.drpc.org`) agree on
   `0x86923f...3fdC`; `symbol()` = `AMD` and `name()` = `AMD • Robinhood Token`
   agree on three independent mainnet RPCs. The address is never typed in.

2. **Published score.** Selector derived (`0xd47875d0`), and the return data is
   **checked for length before decoding**: the struct has 8 static members, so
   256 bytes. Anything else aborts. This is the precise guard that was missing
   on 2026-09-20, when a `uint256` ABI silently returned the first word
   (`adminKeyScore = 3`) and it was published as the composite. Both testnet
   RPCs return `3, 0, 0, 100, 100, 1`, `lastUpdated` 1789934379,
   `methodologyHash 0xf2606acd…8975` = `keccak("authority-risk-oracle-v3")`,
   recomputed here.

3. **No authority of its own.** The EIP-1967 slot is derived as
   `keccak("eip1967.proxy.beacon") - 1` =
   `0xa3f0ad74…3d50`; on three mainnet RPCs it points at the shared beacon
   `0xe10b6f6b275de231345c20d14ab812db62151b00`, implementation
   `0xb35490d6f9163de4f80d88dc75c3516eb64c5ae2`, both unchanged since index 15.
   The proxy is 283 bytes of forwarding code, the beacon 2332 - which is why
   the authority analysis happens on the beacon.

4. **Authority root, derived rather than assumed.** Every `RoleGranted` /
   `RoleRevoked` event carrying `DEFAULT_ADMIN_ROLE` was replayed from genesis
   (`eth_getLogs` 0 → latest), starting from no candidate address:

   ```
   block     7662  granted 0x074377a78a9710a1d47244f89797718b4f491279  (self-bootstrap)
   block     7802  granted 0xd6f8378f8e440c65f8382f5f2728c78dfd55b66d
   block     8695  revoked 0x074377a78a9710a1d47244f89797718b4f491279
   ```

   Live holder set: exactly one address, `0xd6f8378f…5b66d`. The beacon has
   emitted **zero** `RoleAdminChanged` events ever, and `getRoleAdmin(0x00)` is
   `0x00` on all three mainnet RPCs, so that single key roots the whole tree.
   It carries no bytecode and its nonce is still 2. Each of the three events
   was re-fetched on a second provider through `eth_getTransactionReceipt`, a
   path that does not depend on that provider's log index. Only at the very end
   is the derived root compared to the address hardcoded in `scorers.py` -
   they match, so the scorer's assumption is *confirmed*, not *reused*.

   The beacon's full history is 274 events, the last at block 657134 while the
   chain head is past 68.7M: no role activity in a very long time.

5. **Chain versus re-derivation.** `score_stock_token()` and
   `compute_cross_exposure()` are re-run live from a fresh clone against
   mainnet and compared field by field with the struct read off the oracle. The
   composite is additionally recomputed straight from the `METHODOLOGY.md`
   formula, so a bug inside `_composite()` would surface as a disagreement
   instead of being reproduced on both sides.

   | field | published | re-derived | verdict |
   |---|---|---|---|
   | adminKeyScore | 3 | 3 | equal |
   | multisigScore | 0 | 0 | equal |
   | timelockScore | 0 | 0 | equal |
   | oracleAuthorityScore | 100 | 100 | equal |
   | crossExposureScore | 100 | 100 | equal |
   | compositeScore | 1 | 1 | equal |

   `compute_cross_exposure()` re-derives every group's signer set live across
   all 62 tracked addresses and still puts index 17 at 100.

## Part 2 - New targets: none

Zero added, and this is not a budget question. The reserve was declared
exhausted at the 2026-09-20 run, and the four leads it left are each blocked on
a missing primary source rather than on effort: UNCX V4 locker (source behind a
Cloudflare challenge - note that the *root* was resolved on-chain on 2026-09-20
and the target is now tracked at index 58), StonkBrokers lockers (1.76M listed
TVL, 16-20 unidentified selectors, no public source), STONX ve33 over Ekubo
(1.13M), up v3 DEX (8.6M, no dedicated DefiLlama adapter). None of them is
scoreable without guessing, and guessing is what got action rejected.

The first attempt claimed "time and resource constraints" for this and left its
new-target section as an empty placeholder. That was the wrong reason given for
a defensible outcome; the real reason is the one above.

## Part 3 - Two findings outside the rotation's scope

Both are **corrections to standing records**, not discoveries, and both are
mechanically proved by claims 6 and 7.

**(a) The oracle holds 62 targets, not 58.** `note_2026-09-20_cron` in
`rotation_state.json` records 58 and "[backlog note]".
`trackedTargetsCount()` now returns 62. Reading `getScore()` for all 62 shows
**a single distinct `lastUpdated` across every one of them**, 1789934379 =
2026-09-20T19:59:39Z. Four targets appended one at a time would each carry
their own timestamp; one shared timestamp is the signature of a full re-push of
the whole set. Spap ran it after the 2026-09-20 run. Left uncorrected, the next
run would have started from a false count.

**(b) The prepared push has already been executed.**
`scripts/prepared_pushes/2026-09-20-robinhood-index16-4-new-targets.py` was
left for Spap to broadcast. Its four targets now sit at indices 58 to 61 with
exactly the six values the file declares - the expected values are parsed out
of the file itself rather than retyped, so this compares the file on disk with
the chain:

| index | address | prepared | published |
|---|---|---|---|
| 58 | `0x128A800c…603A` UNCX V4 locker | 50/35/0/100/100/31 | identical |
| 59 | `0x5c98b2d8…dC09` Orvex V2 factory | 5/0/0/100/100/2 | identical |
| 60 | `0xd01C774d…4032` Orvex V4 PoolManager | 65/65/0/100/100/46 | identical |
| 61 | `0xFe7E25dE…9b0D` Orvex V4 Vault | 2/0/0/100/100/1 | identical |

Nothing is outstanding on that script.

## Limits of this audit, stated

* Only the **authority surface** was re-derived. Nothing here says what the
  beacon's implementation code does; the deployed bytecode was not matched
  against any published source.
* The event replay over the full range runs on one provider
  (`rpc.mainnet.chain.robinhood.com`) because it is the only one that serves
  `eth_getLogs` from genesis. The cross-check is per-transaction receipts on a
  second provider, which is independent of that provider's log index but does
  **not** prove the absence of an event the first provider failed to return.
  The zero-`RoleAdminChanged` result rests on that single provider.
* These public RPCs answer HTTP 403 to urllib's default user agent and rate
  limit hard. A swallowed 429 shows up later as a missing log or a degraded
  score rather than as an error, so `rh_lib.py` retries with backoff and raises
  if it never clears. Do not run these commands in parallel
  (`reference_robinhood_rpc_429_drift_runs`).
* Read-only throughout: mainnet was only read, the testnet oracle was only
  read, no transaction was signed or broadcast, no key file was opened, and
  `public_repo_visibility_change_allowed` was not touched.
