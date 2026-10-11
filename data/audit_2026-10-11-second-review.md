# Audit: second line-by-line review of the scoring library, the dashboard and the push scripts (2026-10-11)

Six independent reviewers read the shared scoring library, the per-chain scorers, the dashboard script, the Solana and Zcash code and the push
scripts, each told to refute the code rather than confirm it. Every finding below was re-checked against the code before being acted on. The
score fixes touch failure and rotation branches, which a healthy read does not take; they have not been replayed against live Robinhood state, so the
next Robinhood re-push starts with a dry-run preview that shows whether any published value moves.

## Fixed

| Where | Defect | Fix |
|---|---|---|
| `scripts/lib/safe_modules.py` | Module pagination restarted from the wrong cursor on Safe v1.3.0, so a Safe v1.3.0 with more than one page of modules lost one module at each page boundary | Resume from the last returned module; test added that fails on the old code |
| `scripts/lib/push_guard.py` | A `crossExposureScore` defaulted to 100 after a failed computation was held only if the composite moved, and it never does; a rotated stock-token admin and an unreadable Spark `delay()` published without a hold | A default note holds the entry whenever the published value differs; both unresolved branches now carry an "unresolved authority" note |
| `scripts/lib/scorers.py`, stock tokens | A role check that came back False or unread scored the admin key 40, above the 20 floor for an unresolved read | 20, with a note |
| `scripts/lib/scorers.py`, two Spark scorers | An unreadable `delay()` scored the timelock 60, the best case | 0: unknown is never better than a confirmed zero delay (10) |
| `dashboard/index.html` | A slow read could paint its scores under the tab the visitor had moved to; an empty `eth_call` showed as a green "0 targets" or a STRONG row; a malformed `#chain=` stopped the page; RPC-supplied strings reached the HTML unchecked | Load-sequence guard, address and length checks, ignored malformed hash, numeric coercion |
| `scripts/update_scores.py` | A snapshot file that existed but could not be parsed was treated as a first publish, which switched the completeness and alert guards off; it was also written non-atomically | The run refuses; the file is written then renamed |

## Open, known, not fixed before the submission

- **Completeness of a batch on the non-Robinhood EVM push scripts.** Only the Robinhood script compares the batch with the last published
  snapshot. On the other EVM oracles a target skipped by an RPC failure is simply not refreshed, and goes stale after nine days. Mitigation
  today: every re-push is run by a person who reads the held-and-skipped report. (The Solana push script gained the same guard on 2026-10-11:
  it now reads the Registry and the published scores, refuses a tracked target the scorer lost, and holds drops and degraded branches through
  `push_guard`; `--accept-held`, `--accept-missing` and `--skip-published-check` are the explicit overrides.)
- **Fixed admin scores independent of the Safe threshold** in a few scorers (Lighter, Arcus, Pendle, LayerZero, rollup L1 contracts): the
  admin component is a literal chosen when the target was reviewed, not recomputed from the multisig read.
- **Older scorers keep fallbacks of 40 or 60 for an unresolved read** where newer ones use the 20 floor (T3tris, Saffron, Curve, Meridian,
  PancakeSwap V2 among the Robinhood targets). Changing them moves published scores, so it waits for a re-push.
- **Solana:** a program under loader-v4 would be read as "renounced" because only loader-v3 upgrade authority is read (no tracked program uses
  loader-v4 today); a Sputnik `Ratio` threshold is rounded with `ceil` where the DAO contract uses floor plus one (no tracked DAO is affected).
- **Zcash:** `zec.omft.near` is scored from its `Requestor` role, which in the live policy cannot approve a `call`; the approving path is
  `Approver`, which scores slightly better (10/20, composite 10, instead of 5/18, composite 7). The node-lineage count counts two versions of
  the same client as two lineages.
- **Dashboard:** the Zcash tab trusts the explorer proxy for the raw transaction bytes (the page says "commitment matches the transaction the
  proxy served", not "the chain says so"), and the proxy's rate limit (20 requests a minute) can be hit by repeated visits.
- **Dashboard indexes are positional.** Cards are tied to an oracle by index, and nothing checks the address behind an index. Indexes are
  append-only on chain, so a published index never moves, but a card written against the wrong index would show another target's score.
- **Methodology hash granularity.** The hash of a chain's scorer files includes `scripts/lib/scorers.py` for several chains, so a comment change
  in the Robinhood scorer changes every oracle's hash. It never hides a change; it can report one that did not happen.

## Open: calibration findings from the per-chain scorer read (not changed before the submission, because each one moves a published score)

Reproduced with fake reads (no network, no writes). Fixing them changes numbers on a live oracle, so each waits for a dry-run preview and a re-push.

- **Monad Uniswap v4** scores 80/100/60 even when the L1 hop is not confirmed (the Base and Arbitrum twins degrade to 5 or 20).
- **Ethereum L1 and Plasma, Ethena OFT adapters:** the timelock component is inverted (closing the `setPeer` bypass lowers the score) and
  `getMinDelay` and the Safe threshold are literals, not reads.
- **Compound V3 on Arbitrum and Base:** an unreadable or EOA `pauseGuardian` scores 65 against 60 for a Safe.
- **Monad Euler V2:** `dao_is_proposer` is read but does not enter the score, and a 7-day delay scores 40 against 60 for 4 days.
- **Morpho V1 vaults** (seven scorers): the timelock component is a literal chosen by who the owner is; `timelock()` is not read.
- **Base Spark USDC vault:** an unresolved owner is scored from the curator alone (70/75/75) where the methodology says 20.
- **Plasma Pendle:** a diverging ProxyAdmin owner is noted, not scored. **Plasma Aquila:** the admin-key scale is one step lower than the
  rest of the file, and the tests quote the code instead of the method.
- **Reads that only reach the notes:** Lido (`voting_can_execute`, emergency mode), Arbitrum Security Council (`has_exec_role`), Echo eBTC
  (is the compromised EOA still admin), Kuru (`MarginAccount.owner()`).
- **A zero delay is credited** by Uniswap V3 (75), Maker (70) and Aave (55) as if it were a delay.
- **Unreadable read taken as "no bypass"** in the Arbitrum bridge scorer and the Plasma Euler scorer.
- **Labels without a matching read:** Adpend is described as an EIP-7702 EOA without a code check; `_crossEcosystem` is hard-coded for two vaults.
- **A wrong address in a docstring** (Plasma "EVK Vault exUSD-2" has no code); no effect on any score.
- **Hyperliquid:** an UNRESOLVED or zero holder counts as a shared root holder (not confirmed against live state).
- The claims audit also found text to correct, handled in the README and METHODOLOGY: the RPC cross-check is one per chain plus a second RPC on Ethereum L1
  and its tokens, not two independent RPCs on every run; the Solana push script has no guard; the timelock scale is not uniform across scorers;
  published methodology numbers are the values at the dated decision, not today's on-chain values.

## Found by the review of tonight's fixes

- The dashboard's Tempo tab was broken against the live RPC: it answers HTTP 413 above about 1.8 KB per request (8 calls pass, 9 do not) and the page sent chunks of 14. Chunks are now 6.
- The `ACCEPT_*` guard in `repush_all_oracles.sh` skipped step names with a digit (`l1`).
- METHODOLOGY said no scheduled job sends transactions; `update_scores.yml` runs weekly (Sunday 06:00 UTC) and pushes Robinhood Chain testnet, behind the same push guard and completeness check. It has failed at that check on 2026-10-04 and 2026-10-11 because one Robinhood pool-registry read is refused by the RPC.
