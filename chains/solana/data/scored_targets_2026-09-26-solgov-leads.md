# Eight Solana targets scored from the SolGov leads (2026-09-26)

Spap's "Go solana" after `finding_2026-09-26-solgov-registry-verified-live.md`: the registry lists 50+ protocols, we tracked 18, and nine of the
missing ones were real candidates. Eight are now scored by `score_solgov_leads` in `chains/solana/scorers.py` (26 Solana targets, was 18).
Nothing is pushed on-chain: the Solana oracle is Spap's to republish.

## Scores (live 2026-09-26, Solana mainnet, every multisig re-derived offline)

| Target | Programs scored | Path that binds | Admin | Multisig | Timelock | Composite |
|---|---|---|---|---|---|---|
| Solstice | USX, YieldVault, Aux `7FaMy...` | Aux: Squads v4 2-of-3, no delay | 45 | 57 | 0 | **35** |
| GMSOL (GMTrade) | 6 programs, one committee | Squads v4 4-of-7, 600 s | 65 | 83 | 0 | **51** |
| Loopscale | Loopscale, Beam | Squads v4 4-of-7 voters (9 members), 24 h | 75 | 83 | 50 | **70** |
| Huma Finance | Permissionless, Institutional | Squads v4 5-of-7 voters (9 members), 12 h | 70 | 100 | 25 | **66** |
| Lulo | FlexLend | Squads v4 3-of-8, no delay | 50 | 60 | 0 | **38** |
| Exponent | Core | Squads v4 3-of-5, 4 h | 60 | 69 | 8 | **47** |
| Flash Trade | Perpetuals | Squads v4 3-of-7, no delay | 50 | 62 | 0 | **39** |
| Solayer | sSOL staking, Endo | Squads v4 3-of-6, no delay | 50 | 65 | 0 | **40** |

Solstice's USX and YieldVault programs alone (vault 0 and vault 1 of the same 3-of-5 multisig, 24 h) would score 70 / 69 / 50, composite 64; the third program
the registry lists under Solstice, `7FaMy...`, is upgraded by a different, weaker multisig (`BPdkMG...`), and the rule below takes the minimum.

## Method, and what the number is not

- **Rule**: score every program the registry lists for the protocol; each program's upgrade authority is read live (loader v3), the hardcoded multisig
  must reproduce it as a Squads v4 vault PDA (vault index 0, or 1 for YieldVault), and the target takes the componentwise minimum over its distinct programs. A mismatch degrades that program to 20 / 20 / 0.
- **Solayer is the one exception to "listed by the registry"**: the registry lists no program for it, so its programs are the ones a reverse lookup finds under the registry's own authority vault (`read_programs_by_authority`: exactly two ProgramData accounts, `sSo1iU21...` and `endoLNCKT...`). Vault 0 of the registry's multisig `5AQ3c2...` reproduces that authority offline.
- **Upper bound**: only the program-upgrade path is scored. The in-state admin, mint and config authorities of these seven were not traced (for
  Sanctum's validator LSTs the same limit is disclosed). A weaker in-state path could only lower a score; no one has shown one exists.
- Voters are members with the Vote permission (Loopscale and Huma have 2 non-voting members each, matching the registry's own voter counts).
- The existing formulas and constants are untouched (`_score_full_power_path`, `_composite`); the only change to shared code is a `vault_index=0` parameter on `_resolve_squads_v4`.

## Cross-exposure: no side effect

Run over all 26 targets: the eight share no signer with any existing target or with each other (each new `crossExposureScore` is 100), and no existing
target's `crossExposureScore` changed (18 of 18 identical to the value without the new targets). `check_oracle_key_collisions.py --ecosystem solana`: 26 entries, 26 distinct keys. `update_scores_solana.py --dry-run`: 25 of 25 instructions encoded before Solayer was added; rerun before the push.

## Not scored, on purpose

- **Switchboard** ($5B secured in the registry). Several outlets report that Switchboard Technology Labs announced on 2026-09-19 that it is winding down, all
  implementations deprecated, support ending 2026-09-25 (KuCoin, cryptobriefing, crypto.news; I did not verify this on-chain, and the registry entry says the same).
  A score for a service that has stopped would mislead. What the chain shows, for the record: its three programs are upgraded by three different controllers. `On-Demand`
  (`SBondMDr...`) by Squads v4 vault 0 of `93RQfY...` (3-of-8, no delay, the multisig the Drift scorer already reads); `Oracle V2` (`SW1TCH7q...`) by `2NvGRFsw...`, an off-curve
  system-owned account I could not tie to a multisig; and `Attestation` (`sbattyXr...`) by `31Sof5r1...`, **an on-curve key, that is a bare keypair holding about 10.25 SOL**, so one signature can replace that program's code.
  Whether the oracle's users depend on that program is not established here.
- **Hylo**: no program is upgraded by its registry vault (`DLkcqe...` controls zero ProgramData accounts), so there is no upgrade authority to re-derive. A vault address alone is not a target.
- **Pyth** (Wormhole governed, no Squads multisig): needs its own path.

## What a push would do

26 entries instead of 18, so eight new keys; the eight new targets have no dashboard card (the cards address entries by index, the new ones are appended after the existing 18,
whose order is unchanged and pinned by a test). Jupiter Lend stays at 56 in the scorer against 55 on-chain until the next push (see `finding_2026-09-26-jupiter-lend-upgrade-multisig-member-removed.md`).

## Reproduce

```
python3 chains/solana/scripts/verify_solgov_leads.py                       # registry vs chain, the lead selection
PYTHONPATH=. python3 -m unittest scripts/lib/tests/test_solana_solgov_leads_scorer.py
python3 scripts/check_oracle_key_collisions.py --ecosystem solana          # 26 distinct keys
```

Sources: SolGov `public-dashboard/src/data/protocols.ts` (registry, fetched raw 2026-09-26); Solana mainnet (public RPC): `getAccountInfo` on each program and ProgramData, Squads v4 multisig accounts and offline vault PDA derivation;
Switchboard wind-down: [KuCoin](https://www.kucoin.com/news/flash/oracle-protocol-switchboard-announces-shutdown-services-to-end-on-september-25), [Crypto Briefing](https://cryptobriefing.com/switchboard-oracle-shuts-down-migration/), [crypto.news](https://crypto.news/a-solana-oracles-support-ends-today-who-still-relies-on-its-prices/).
