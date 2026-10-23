# What a score says, and what it does not say

*A short page, because the honest reading of this score matters more than the score. The two tests it cites are linked; nothing here is a forecast.*

## What it says

A score answers one question about one contract: **if the people or keys that control it were compromised, how much could they do, and how long would everyone else have to react?** It is read from public chain state; a reading made by hand says so. A line that could not be read is `null`, never zero, and the label says what was not read.

Read it as **exposure**. A bare key with no delay scores near 0. A well-spread multisig behind a long timelock scores high. The five sub-scores and the formula are in the [methodology](../METHODOLOGY.md). The composite uses three of the five (admin key, multisig, timelock); the price-path and shared-control scores sit beside it and do not change it, so read all five.

## What it does not say

**It does not say who will be attacked.** We tested that twice, and both tests are public.

- **Pre-registered test (1 October 2026).** The protocol was committed before any measurement. We read the authority setup of 5 incident victims on Ethereum one month before each incident, and of 18 untouched protocols of similar size at the same blocks. The composite did not separate them: the victims were not unusually weak on paper (four sat between 43 and 49, the ordinary band of a 3-of-5 to 4-of-7 Safe without a timelock), and several untouched protocols hung on a single bare key. Read strictly the verdict is "does not discriminate"; read with the three edge cases treated sensibly it is "not conclusive". Either way a large, regular gap is ruled out, and a moderate effect remains untested. Five sets cannot say more. [The finding.](../data/finding_2026-10-01-backtest-victims-vs-controls.md)
- **Back-test of the published requirements (12 October 2026).** We read 55 incidents from our own postmortems. 48 are outside what an authority score can see. Of the 7 about who controls a contract, the six published requirements flagged 2, missed 2, and could not be applied to 3. Where the requirements could be applied, that is 2 of 4 (50 percent); counting the 3 cases they could not be applied to as misses, it is 2 of 7 (29 percent). The sample is 7 cases that we chose to write up ourselves, 4 of them measurable, so the rate says little: an exact 95 percent interval for 2 of 4 runs from 7 to 93 percent. It describes these cases; it is not an estimate of how often the requirements catch an incident. The misses are published with their reasons: in one, the keys of the signers were compromised, which a threshold does not show; in the other, a delay existed and what failed was who held the voting power. [The page.](https://realspap.github.io/oracle/backtest/)

**It does not see what happens off-chain.** Three owners of a Safe could be three employees of the same company, or the same person's three wallets. Code bugs, price manipulation and custodial wallets are outside it too. The attacks in our tests went around the configuration (a spoofed signing interface, compromised devices, a service key), not through its weakest point.

**It is not an audit, not a rating of a company, not investment advice.** Today the oracles run on testnets, with a single updater key.

## How to use it

- **As a gate on exposure.** Refuse to depend on a contract whose label is stale, whose delay was not read, or whose composite is under the line you choose. [Fourteen lines do it.](../integrations/authority_facts_gate.py)
- **Watch changes more than the static number.** Our own test points that way: the Watch reports queued operations, admin changes and signer changes as they happen, which a snapshot cannot.
- **Check it.** `python3 scripts/prove.py` replays the numbers we publish against the chain in about ten seconds.

## What would change this page

Replaying more incidents on the state of the chain just before the attack, with the readers committed first (the public archive endpoints can serve Ethereum and Arbitrum for that; Solana's public history is too short). External readers who tell us where the score misleads them. Both are open, and neither is claimed here.
