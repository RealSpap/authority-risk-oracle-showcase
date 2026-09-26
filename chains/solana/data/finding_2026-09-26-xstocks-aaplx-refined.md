# xStocks AAPLx (Solana): re-verified live, power distribution more concentrated than "4 equal keys"

2026-09-26. Re-verifies the tracker board's own already-confirmed piste ("xStocks/Backed Finance
[backlog note]
permanentDelegate/rebase, aucun multisig") -- the core finding holds, re-confirmed live via
`getAccountInfo` with parsed encoding (not re-derived from a prior pass), but the actual power
DISTRIBUTION across those 4 keys is more concentrated than "4 equal single-purpose authorities"
implies.

## The mint is a Token-2022 account with 7 extensions -- read in full, not just the 4 named powers

`getAccountInfo(XsbEhLAtcf6...,{encoding:jsonParsed})` decodes cleanly (SPL Token-2022 program,
`spl-token-2022` owner). Four distinct authority addresses confirmed, each independently re-checked
via `getAccountInfo` and confirmed to be a genuine **System Program account with zero data** (a bare
EOA, not a program-derived account, not a Squads multisig, not any kind of smart contract) --
matching the card's "aucun multisig" claim exactly:

| Authority address | Powers it actually holds (read from ALL 7 extensions, not just the named 4) |
|---|---|
| `7pt9tkctJPK7PPNQJ77GKg8ZffSF6QxoMiCFYHxrtaCj` | `mintAuthority` only |
| `JDq14BWvqCRFNu1krb12bcRpbGtJZ1FLEakMw6FdxJNs` | `freezeAuthority` **AND** `pausableConfig.authority` -- can freeze individual accounts AND pause ALL transfers network-wide (a newer, more powerful Token-2022 extension the original "4 powers" framing didn't separately name) |
| `5aMNNLQJwAEeoemTEMkv5NVjqKwvvefRYCQ5Z67HFvEq` | `permanentDelegate` (can move ANY holder's tokens without consent) **AND** `metadataPointer.authority`, `confidentialTransferMint.authority`, `transferHook.authority`, `tokenMetadata.updateAuthority` -- FIVE distinct capabilities bundled under one key, not one |
| `S7vYFFWH6BjJyEsdrPQpqpYTqLTrPRK6KW3VwsJuRaS` | `scaledUiAmountConfig.authority` -- the "rebase" key the card names (sets the price-tracking display multiplier) |

**Real refinement, not a reversal**: still 4 distinct bare-EOA addresses (the card's headline claim
holds), but the SAME single `permanentDelegate` key also controls the token's metadata, confidential-
transfer configuration, and transfer-hook program registration -- a materially larger blast radius
for that one key than "can move anyone's tokens" alone already implies.

## The "rebase" mechanism, read precisely rather than assumed

`scaledUiAmountConfig` currently shows `multiplier` = 1.0026642075893797 and a scheduled
`newMultiplier` = 1.0032690125398187 with `newMultiplierEffectiveTimestamp` = 1786149000 (2026-08-08
00:30 UTC) -- a date that has ALREADY PASSED as of this run (2026-09-26). Per Token-2022's own
extension semantics, once the effective timestamp passes the new multiplier becomes the one applied
for display-amount calculations; the stored `multiplier` field only changes on the AUTHORITY's next
explicit update call, which is why both values are still visible together. Disclosed precisely as
read, not asserted as "a safety delay of N days" -- that would need comparing several historical
updates to characterize the real cadence, not done this pass.

## TVL: the card's own "60M-880M$" range does not match this specific token's on-chain supply

Live `supply` = 15,376,269,404,504 raw units, `decimals` = 8 -> raw token count = 153,762.69, scaled
by the current multiplier -> **~154,265 AAPLx tokens** outstanding. At any plausible AAPL share
price this implies a market value far below the card's cited $60M-880M range (order of magnitude
~$30-40M at typical 2026 AAPL prices, not independently priced live this pass to avoid asserting an
unverified stock quote) -- strongly suggesting the card's cited range was the xStocks PLATFORM's
combined TVL across all its tokenized-equity products, not AAPLx specifically. Disclosed as a likely
mislabeling to correct, not asserted as a precise dollar figure without a live AAPL price source.

## What this is and isn't

Pure investigation, no scorer built or changed -- xStocks/AAPLx is not a tracked target (adding it
would be a new target on Solana, Spap's decision). Refines an already-largely-correct prior finding
rather than overturning it.

## Verification

`getAccountInfo` with `jsonParsed` encoding against `https://api.mainnet-beta.solana.com` for the
mint (all 7 extensions read directly, not assumed from the card's summary) and each of the 4
authority addresses (confirmed System Program, zero data, via raw `base64` encoding). No key read,
nothing sent.
