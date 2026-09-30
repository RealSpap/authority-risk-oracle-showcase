# Switchboard shut down entirely on 2026-09-25 -- confirmed live on-chain, Drift's AI16Z spot market still names the dead feed as its oracle today, not just a stale SDK file

2026-09-30, same "voit large" session as the two findings above. This one is different in kind: not a new candidate, a possible
inaccuracy in a score **already live in `scorers.py`**.

## The shutdown, confirmed independently of the earlier findings in this file

Web search, multiple independent outlets (KuCoin, CryptoBriefing, SolanaCompass): **Switchboard Technology Labs Inc. announced on
2026-09-19 that all oracle implementations are deprecated effective immediately, with support ending 2026-09-25.** Solana's largest
Switchboard-dependent protocols (Kamino, Drift, MarginFi, Jito) were given 6 days to migrate to Pyth or RedStone. Cited reasons: AI
tooling lowered the cost of bespoke oracle solutions, a compressed bear-market budget environment, and eroded confidence after sector
security exploits.

This retroactively explains (and understates) the `scorers.py` comment above `SOLGOV_LEADS` calling Switchboard "winding down" -- as of
this pass it is not winding down, it is **already fully shut down**, 5 days before this run.

## Why this matters for a score already in this project, not just the new candidates above

`score_drift_protocol`'s `oracleAuthorityScore` (closed 2026-09-19 -- **the exact day of the shutdown announcement**, coincidentally)
is derived from one concrete, named example: the AI16Z spot market's Switchboard On-Demand feed
(`BHqLyA9ov1VPNzt8eb5bt75X2Vk1EVKw1d9Qa78Gk5tR`), cited as one of "16 live SPOT markets" using Switchboard at the time, found via a
`getProgramAccounts` scan of Drift's 66 spot markets on that date.

**Checked live today: this exact feed account's last on-chain transaction was 2026-04-02.** Almost six months of no price update
activity -- stale well before Switchboard's own shutdown, not caused by it. Either this specific market was already effectively
unused/delisted by Drift before 09-19, or Drift itself had stopped actively reading it, in which case the 2026-09-19 scan may have
counted a market that was only nominally, not actually, live on Switchboard. Combined with the company-wide shutdown 6 days later, it
is very unlikely this feed is still Drift's real, current oracle source for AI16Z today.

## Update, same session: confirmed directly on-chain, not inferred -- Drift has NOT migrated this market

Pulled the live SpotMarket account for AI16Z (index 35 -- confirmed against Drift's own SDK constants file, `sdk/src/constants/spotMarkets.ts`,
used only to locate the market, not trusted for the oracle field itself, same discipline as the W-PERP lesson already in this file's
neighboring docstring). PDA re-derived independently: `find_program_address(["spot_market", u16le(35)], dRiftyHA...)` ->
`4gvRdpSTQg6i4M9bpFojwvEWkMtaGm8AnPdcU6M3obz3`. Read raw (776 bytes, owner = Drift program, both RPCs agree byte-for-byte) and searched
for the old Switchboard feed's 32 raw bytes directly in the account data rather than guessing the struct's field offsets: **found at
byte offset 40 on both RPCs.**

**This settles it: as of right now, today, Drift's live on-chain SpotMarket account for AI16Z still names the dead Switchboard feed
as its oracle.** Not a stale SDK file, not an inference from the feed's own silence -- read from Drift's own current account state.
Whether that market is still actually tradeable, paused, or has some other safety mechanism around a stale price was not checked (would
need to decode more of the 776 bytes -- market status flags, if any -- without a full IDL for the struct layout, not done this pass).

## Update, same session: not a one-off -- spot-checked 3 more of the SDK's other listed Switchboard markets, all 4 for 4 unmigrated

Drift's own SDK constants file lists 13 spot markets with `oracleSource: SWITCHBOARD_ON_DEMAND` (fetched fresh, not from an old cache):
META(29), AI16Z(35), JitoSOL-3(40), 3 PT-tokens(41/42/43), JTO-3(44), SOL-2(49), JitoSOL-2(50), JTO-2(51), dfdvSOL(52), sACRED(53),
PT-fragSOL-31OCT25-3(55). Spot-checked JTO-3(44), SOL-2(49) and sACRED(53) the same way as AI16Z -- independently re-derived each
SpotMarket PDA, read live, searched for the SDK's own listed oracle bytes in the raw account data: **all 3 found at the identical byte
offset 40, same as AI16Z, on mainnet-beta.** None migrated. Their oracle feeds' own last on-chain activity: SOL-2 2026-08-26, JTO-3
2026-05-12, sACRED 2026-04-01 -- all stale, and notably all predate the 2026-09-19 shutdown announcement itself, consistent with
Switchboard's On-Demand service already degrading for weeks before the formal shutdown, not everything going stale the instant the
announcement landed. **4 for 4 sampled, 0 migrated** -- strong evidence this is systemic across Drift's Switchboard-sourced markets,
not particular to the one example `scorers.py` happens to cite, including SOL-2, a much more consequential asset than AI16Z or sACRED.
The other 9 listed markets were not individually checked (time-bounded sampling, not exhaustive).

## What this is not, and what it would take to fix properly

Not a re-score yet, and not a claim that trading is currently broken -- only that the recorded oracle authority path is confirmed
unchanged and confirmed dead-company. `score_drift_protocol`'s `oracleAuthorityScore` example (AI16Z) is not just "possibly stale", it
is now confirmed to still literally be the account it was on 2026-09-19, five days after that company shut down. The underlying
METHODOLOGY (three full-power paths: feed authority, queue authority, program upgrade authority) doesn't need to change -- what needs
a fresh look is whether "the feed's own operator no longer exists" should itself be scored as a new failure mode (a company shutting
down is a different risk shape than a bare EOA or a weak multisig, and this project's scoring vocabulary doesn't have a category for it
yet), and whether Drift has a market-pause mechanism this project should also read before calling the risk "live" versus "frozen and
therefore less exploitable, not more."

**Flagged, not fixed**, in keeping with tonight's rule of not silently touching an already-published score without Spap looking at it
first (this one is a bigger change than a headline-number sync: it could shift an actual `compositeScore` already on record, and might
need a genuinely new scoring category, not just a number update). Concrete next step for whoever picks this up: decode the SpotMarket's
status/pause flags (needs the struct layout, not derived this pass), and re-run the same `getProgramAccounts` scan the 2026-09-19
pass used across all 66 spot markets to see how many still resolve to Switchboard today, not just this one confirmed example.
