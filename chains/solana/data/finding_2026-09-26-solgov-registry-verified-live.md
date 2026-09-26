# SolGov's registry, checked against the chain: 99% accurate, and the 11 untracked candidates that matter

2026-09-26. Prompted by "why does SolGov have 50 to 60 protocols and we 18?". SolGov (github.com/EdgeVault/solgov, `public-dashboard/src/data/protocols.ts`, 53 protocol
entries, 63 multisigs, 183 programs) is treated here as a list of LEADS. `chains/solana/scripts/verify_solgov_leads.py` re-reads, live and read-only, every program's loader-v3
upgrade authority and every Squads v4 multisig it lists (raw data: `solgov_leads_2026-09-26.json`).

## 1. Is SolGov's data right? Almost entirely

- **183 programs**: 179 have exactly the upgrade authority SolGov states; 2 read as `None` (renounced) where SolGov writes "IMMUTABLE" (same fact, different word); 2 could not be read
  (public RPC error, not counted as matching).
- **35 Squads v4 multisigs** read: **34 have the exact threshold, member count and time lock SolGov lists**, and the index-0 vault PDA equals the authority it names for 34 of 35.
- **The one that differs is Jupiter Lend**: SolGov lists the pre-change shape; live it is 4-of-6 since a member was removed at 08:41 UTC on 2026-09-26 (see
  `finding_2026-09-26-jupiter-lend-upgrade-multisig-member-removed.md`). The changes it lags on are the ones `scripts/check_squads_changes.py` now catches between pushes.

## 2. Why 18 and 50: breadth of the tail, not a ceiling

15 of SolGov's 53 entries are already tracked here (our 18 targets: Kamino, Solend and Sanctum are two targets each). By SolGov's own self-reported TVL, those 15 carry **$14.4B** and
the 19 untracked entries that give a number carry **$1.35B**; the other 19 have no figure, are pre-launch or are below $30M. So the count gap is mostly a long tail, and the value gap is
about 9%. It is not zero: nine untracked protocols and two oracles weigh something.

## 3. The candidates, with live-verified parameters (untracked, above $30M or an oracle)

| Protocol | TVL as SolGov states it | Programs (live authority = SolGov) | Primary multisig live | Time lock |
|---|---|---|---|---|
| Solstice | $357M | 3 of 3 | 3-of-5 | 24 h (SolGov also lists a second, 2-of-3 auxiliary multisig with no delay: not re-read here) |
| GMSOL | $236M | 6 of 6 | 4-of-7 | 600 s |
| Solayer | $200M+ | none listed | 3-of-6 | none |
| Loopscale | $125M | 2 of 2 | 4-of-9 | 24 h |
| Huma Finance | $100M+ | 2 of 2 | 5-of-9 | 12 h |
| Lulo | $92M | 0 of 1 (1 unread) | 3-of-8 | none |
| Exponent | $76M | 1 of 1 | 3-of-5 | 4 h |
| Flash Trade | $50M+ | 1 of 1 | 3-of-7 | none |
| Hylo | $39M | none listed | 3-of-10 | none |
| Switchboard (oracle, "$5B secured") | n/a | 3 of 3 | 3-of-8 | none |
| Pyth (oracle, "$7B secured") | n/a | 11 of 11 | no Squads v4 multisig listed (governance goes through Wormhole) | n/a |

Nothing here is a score: it says the authority path of each is the same shape the existing Solana scorers already read (loader-v3 upgrade authority into a Squads v4 multisig, `_score_full_power_path`),
so each is a scorer of the same kind as Jupiter Lend or Marinade, plus tests, and a push by the maintainer. A new target is Spap's decision; nothing was added.

## What this does not say

TVL figures are SolGov's, not independently priced (the DefiLlama measure in `scripts/check_tvl_coverage.py` is the independent cross-check). Solstice's off-chain custody (its own docs say part
of the collateral moves to Copper and Ceffu) and Solayer's and Hylo's missing program lists are outside what an authority read shows. The scope of each multisig's powers (what it can change beyond
upgrading the programs) was not traced.

## Verification

`python3 chains/solana/scripts/verify_solgov_leads.py --out ...` (Solana mainnet public RPC through `sol_read`, `getAccountInfo` on program, ProgramData and multisig accounts; SolGov's file fetched
from raw.githubusercontent.com). No key, nothing sent.
