# Correction: Chainlink and LayerZero on Robinhood Chain used a leftover multisig formula (2026-09-21)

## What was found

`scripts/lib/scorers.py` scores a Safe-rooted target with `_safe_rooted_scores` (the batch-9 convention): adminKeyScore 65 for
threshold >= 3, and `multisigScore = min(100, 15 * threshold + 5 * (owners - threshold))`, "rewards both threshold and
dispersion". Two older scorers did not: `score_chainlink_admin_safe` and `score_layerzero_infra` (both added in commit `58c8409`,
2026-09-16, batch 8) took `multisigScore = threshold * 8`, and the Chainlink one kept adminKeyScore 65 even when its Safe did
not resolve.

I searched for a reason. None is written down: not in the commit message, not in `data/scored_targets_2026-09-16-batch8.md`
(which calls the result "a real, moderate-size multisig" and states the composite 36), not in the scorers' docstrings. The
only trace is the `_safe_rooted_scores` docstring, which says the batch-9 formula "lands the four batch-9 targets in the same
range as the closest existing shapes (... Chainlink 4-of-9 = 36, LayerZero 5-of-7 = 34)": the older numbers were used as
calibration anchors for the newer formula, which is not a statement that they were right. METHODOLOGY.md documents that some
scorers use a tuned variant "see that function's own docstring"; these two had none.

## Correction

| Target | Shape | multisigScore | composite |
|---|---|---|---|
| Chainlink Price Feed Admin (Robinhood Chain) | 4-of-9 Safe | 32 to **85** | 36 to **52** |
| LayerZero V2 EndpointV2, SendUln302, ReceiveUln302 | bespoke 5-of-7 multisig | 40 to **85** | 34 to **48** |

- The LayerZero owner is not a Safe, so its discount stays where it was, in adminKeyScore (55 instead of 65).
- An unresolved Chainlink Safe now degrades to (20, 0, 0) with a note, like every other unresolved authority, instead of
  keeping adminKeyScore 65.
- Verified live on 2026-09-21: 65/85/0 = 52 and 55/85/0 = 48 (three targets).

## What was left alone

The Morpho vault scorer (`score_morpho_vault_generic`) also uses a `* 8` shape (curator and owner thresholds summed). Unlike
the two above it documents itself as a heuristic, names its known limitation and is calibrated to the manual scores of the same
vaults (`data/scored_targets_2026-09-15-batch3.md`). It stays.

## Direction of the change

Both values go **up**: the oracle now reports less risk for two systemically central targets (every Chainlink price feed read
on the chain, and LayerZero's messaging core). That follows from applying one documented formula to the same shapes, and it is
recorded here so it is not read as a quiet improvement. Neither target has a timelock, so their timelockScore stays 0; the
scores remain in the middle of the range for that reason.

## Not on-chain yet

Scorer output only. The deployed Robinhood Chain testnet oracle holds 36 and 34 until its next re-push.
