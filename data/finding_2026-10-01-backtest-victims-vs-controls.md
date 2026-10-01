# Backtest, victims against controls one month before the incident: the score does not separate them (pre-registered, Ethereum, 5 sets)

2026-10-01. The test this repository said it lacked (`data/research_2026-09-21-authority-incidents-evidence-table.md:48-51`): read the
authority configuration of incident victims 30 days before the incident, and of comparable untouched protocols at the same blocks, and see
whether the oracle's composite separates them. Protocol written, criticised by two independent lenses and **committed before any
measurement** (`30e8ae4`, cited as `e05c634` before the commits were rebuilt, see `COMMITS.md` in that folder; `data/backtest_2026-10-01_preregistration/PROTOCOLE.md`, in French). Measured blind (subjects read in address
order, labels only attached after `p_min` was computed), with the formula as of `fa97b69`. Full execution report, independent re-read and
conformity audit in `data/backtest_2026-10-01_preregistration/resultats/`.

## Result

**Verdict, as pre-registered: DOES NOT DISCRIMINATE (at this size).** S = 2.375, p_low = 0.58, p_high = 0.46, victims below their controls'
median in 2 of 5 sets. Every sensitivity (without Wasabi, the draft lists, the original C2 list, ownership paths only, no Safe-module gate,
"no authority" scored 8) points the same way; none gives "discriminates" either way.

| Set (read at J-30) | Victim composite | Controls |
|---|---|---|
| Bybit (cold-wallet Safe 3-of-6) | 44 | Bitfinex Safe 3-of-5: 43; Remitano Safe 2-of-4: 32 |
| Gala (GALA token, Safe 3-of-5 admin) | 43 | floki 2; ENS 80 (governor + 48 h timelock); beam 55; memecoin 31 |
| Humanity (old H token, Safe 4-of-7 via ProxyAdmin) | 49 | POL 2; Starknet 44; Chainlink 101 (no authority); Immutable X 101 |
| Resolv (USR, Safe 3-of-5) | 43 | bitwise-uscc 2; bitfi-basis 2 (bare EOAs); aegis 43; Falcon 47 |
| Wasabi (LongPool, AccessManager unresolved) | 8 | hakka 32; derivadex 101; apex-pro 101; aevo 56 |

Quality: 0 read failures on 23 subjects; an independent re-read of 6 subjects with separate code matched every root, sub-score and
composite; the conformity audit found the run "compliant with minor deviations", none touching selection, formula or test.

## What it means

- The victims were not unusually weak on paper. Bybit, Gala, Humanity and Resolv sat at 43 to 49, the ordinary band of 3-of-5 to 4-of-7
  Safes without a timelock; several untouched controls were rooted in a single bare key. The attacks behind these incidents (spoofed signing
  interface, compromised devices, a service key in KMS, a stolen minter key) went around the configuration rather than through its weakest
  point, which is what the evidence table had suggested.
- Missing timelock is not distinctive either: 5 of 5 victims and 13 of 18 controls had timelockScore 0.
- So the published score is best read as **exposure** (how much one compromise can do), not as a predictor of who gets hit. It supports
  giving priority to watching **changes** (`scripts/check_safe_changes.py`, `scripts/check_pending_ops.py`, `scripts/score_history.py`) over
  refining the static formula. It does not show the score is wrong.
- Five sets can only detect a large, regular gap. "Does not discriminate" rules that out on these cases; a moderate effect remains untested.

## Reservations that decide the wording (both reviewers agree)

Three edge cases were scored by the letter of the protocol. The protocol treats only the zero address as a renounced key.
- floki's owner is `0x…dead`, and POL's timelock admin is `0x…0001` (the ecrecover precompile). Nobody holds either key, yet both count as a bare EOA (2).
- Wasabi's LongPool sits behind an OpenZeppelin AccessManager whose `hasRole(uint64,address)` is not among the pre-registered reads. It therefore ends
  "unresolved contract" (8) instead of the EOA it resolves to (2).

Read sensibly (floki 101, POL 80, Wasabi 2), the exploratory outcome is S = 2.875, p_low = 0.35, 3 of 5 below the median: **NOT CONCLUSIVE**.
A large regular gap is still ruled out; the label "does not discriminate" should be read with that caveat.

## Gaps in our own reading rules, found on the way

- Burn addresses (`0x…dead`, precompiles) held as owner or admin are not treated as renounced anywhere in the repository's EVM rules (Solana
  has a RENOUNCED sentinel). Checked the same day: none of the 161 tracked EVM targets has a burn address or a precompile as `owner()` or
  EIP-1967 proxy admin, so no published score is affected at the first hop. Deeper hops (a timelock admin, as for POL here) were not swept.
  Worth a shared helper next to the zero-address check before one appears.
- OpenZeppelin v5 `AccessManager` roles (`hasRole(uint64,address)`) were not among the backtest's pre-registered reads. Checked the same day
  across the live oracle: of the 161 tracked EVM targets on 8 chains, exactly one sits behind an AccessManager (Robinhood Chain, Fables
  PoolRegistry `0x159a113E...`, authority `0xa362d98b...`), and `scripts/lib/scorers.py` already scores it by replaying the manager's grants
  from genesis (composite 2). So the gap was in the backtest's protocol, not in the published scores.

## Limits

Five sets, one chain, current CoinGecko/DefiLlama categories used for selection, "untouched" detected by name in a public list, the rated
object differs from the attacked contract for Gala and Resolv. Contamination declared in the protocol: the victims' configurations for
Bybit and Wasabi were known before the protocol was written.
