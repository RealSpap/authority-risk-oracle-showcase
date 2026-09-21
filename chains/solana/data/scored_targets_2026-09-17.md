# Solana -- scored targets, 2026-09-17

Promotes [`../METHODOLOGY.md`](../METHODOLOGY.md) section 6.1's deterministic
formulas and the two targets already worked by hand in
[`methodology_test_2026-09-16.md`](methodology_test_2026-09-16.md) into a
real, re-runnable scorer: [`../scorers.py`](../scorers.py). Every number
below is re-derived live by `score_all()` against Solana Mainnet Beta, not
replayed from the methodology test -- and matches that hand-derived test
exactly, which is itself a form of independent verification (two different
passes, one by hand and one in code, landing on identical numbers).

## Summary table

| Target | Address | adminKey | multisig | timelock | oracleAuthority | composite |
|---|---|---|---|---|---|---|
| Jupiter Aggregator v6 | `JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4` | 55 | 83 | 0 | 100 (n/a) | **47** |
| Kamino Lend, main market (SOL/BTC) | `7u3HeHxYDLhnCoErrtycNokbQYbWGzLs6JSDqGAv5PfF` | 65 | 76 | 25 | 45 | **56** |

`crossExposureScore` is not computed this pass (100, "not applicable" per
this project's convention) -- no cross-ecosystem signer-overlap dataset
exists yet linking Solana's on-curve keys to the other tracked ecosystems'
Safes; the two targets' own root signer sets don't overlap each other
either (Jupiter's Squads v3 Ms has 7 members, Kamino's six Squads
multisigs share 11 distinct keys among themselves, zero intersection with
Jupiter's 7).

## Verification

- Both targets' composite and every sub-score match
  `methodology_test_2026-09-16.md`'s hand-derived numbers exactly (Jupiter
  55/83/0/100/47, Kamino 65/76/25/45/56) -- confirmation that translating
  the written formulas into code did not silently change the result.
- Every off-curve authority's claimed controlling Squads multisig (Jupiter's
  Ms, and Kamino's four: klend-upgrade, market-owner, Scope-admin,
  Scope-upgrade) is re-derived offline (PDA math, no RPC) and required to
  exactly match the live-read authority pubkey on every run -- not trusted
  from the hardcoded candidate address alone. All 5 matched live at commit
  time.
- Jupiter cross-checked against a second, independent RPC
  (`https://public.rpc.solanavibestation.com`) -- identical result.
- Kamino's `getProgramAccounts`-based Scope-configuration read (needed to
  confirm the Scope admin's address) could NOT be cross-checked against
  that same second RPC this run: it returned `{"code": -32005, "message":
  "Too Many Requests"}` on every retry (a plain `getSlot` against the same
  endpoint succeeded, so the endpoint itself was reachable -- only the
  indexed query was rate-limited). Kamino's numbers are therefore verified
  on the primary RPC (`api.mainnet-beta.solana.com`) plus the exact match
  against the independently hand-derived methodology test, but not
  cross-RPC-verified this run the way Jupiter and every EVM-chain target in
  this project are. Disclosed as an open item, not silently treated as
  equivalent to a full cross-check -- retry on a future pass rather than
  block on it (this project's standing "retry, then set aside and
  continue" convention).

## Reproduction

```
python3 -c "
import sys; sys.path.insert(0, 'chains/solana')
from scorers import score_all
for r in score_all('https://api.mainnet-beta.solana.com'):
    print(r['label'], r['compositeScore'])
"
```

## Not yet promoted

`METHODOLOGY.md` documents open points not resolved by this pass (section
7): the Kamino emergency council key's controller, recursive oracle-provider
scoring behind Scope's aggregated entries, programs without an on-chain
Anchor IDL, and the Squads v3 program-manager in Jupiter's upgrade flow.
None of these block the two scores above (each is either restrict-only, or
an already-disclosed non-scored blast-radius note) but are carried forward
rather than silently resolved.
