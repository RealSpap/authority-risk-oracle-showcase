# Retroactive backtest: Drift Protocol's $285M Security Council compromise (2026-04-01)

Third retroactive backtest of the after-hackathon roadmap (see
`data/backtest_2026-09-17-wasabi-protocol.md` and `data/backtest_2026-09-17-
solend-governance-emergency-powers.md` for the first two). Chosen because
it directly ties into this project's own README (the SolGov comparison
section cites the Drift exploit as SolGov's own founding motivation) and
because -- unlike Wasabi's bare-EOA case or Solend's token-vote case -- it
is a **compromised low-threshold, zero-delay multisig**, independently
re-derived here to a level of precision beyond either prior backtest: the
exact malicious transactions were fetched and decoded directly, not only
cited from press.

## The incident, as independently corroborated by press

On 2026-04-01, Drift Protocol (a top Solana perpetuals DEX, ~$550M TVL at
the time) lost **$285,279,417.69** across ~31 withdrawal transactions in
about 12 minutes -- the largest DeFi hack of 2026 and Solana's second-
largest ever, behind Wormhole. Chainalysis, TRM Labs, Elliptic, BlockSec,
and QuillAudits all independently describe the SAME mechanism: attackers
(TRM Labs attributes this to North Korea-linked operators) spent roughly a
week (March 23-30) social-engineering Security Council multisig signers
into pre-signing transactions bundled with Solana **durable nonces** --
which, unlike an ordinary transaction's short blockhash expiry, persist
indefinitely, letting a pre-signed approval be executed at any later time.
A planned Security Council migration on 2026-03-27 did not stop this --
nonce accounts kept appearing through March 30, implying signers were
compromised even into the new council. TRM Labs and BlockSec agree the
multisig was a 2-of-5 Squads configuration with **zero timelock** --
"any two of five signers could authorize administrative actions with
immediate effect" (BlockSec). This was not a smart-contract logic bug --
every drain transaction carried validly-collected signatures.

## What was independently re-derived live on-chain today (2026-09-17)

Both malicious transaction signatures were published by QuillAudits and
BlockSec; both were fetched directly from `api.mainnet-beta.solana.com` and
decoded, not just cited:

```
Tx 1: 2HvMSgDEfKhNryYZKhjowrBY55rUx5MWtcWkG9hqxZCFBaTiahPwfynP1dxBSRk9s5UTVc8LFeS4Btvkm9pc2C4H
  blockTime = 1775059518 -> 2026-04-01T16:05:18 UTC (matches press exactly)
  Program SQDS4ep65T869zMMBKyuUq6aD6EgTu8psMjkvj52pCf: VaultTransactionCreate, ProposalCreate, ProposalApprove

Tx 2: 4BKBmAJn6TdsENij7CsVbyMVLJU1tX27nfrMM1zgKv1bs2KJy6Am2NqdA3nJm4g9C6eC64UAf5sNs974ygB9RsN1
  blockTime = 1775059519 -> 2026-04-01T16:05:19 UTC
  Program SQDS4ep65T869zMMBKyuUq6aD6EgTu8psMjkvj52pCf: ProposalApprove, VaultTransactionExecute
  -> CPI into dRiftyHA39MWEi3m9aunc5MzRF1JYuBsbn6VPcn33UH ("Instruction: UpdateAdmin")
     Program log: "admin: AiLGdNitMjv8n5HMS7HAdV2kaeJZZFd4jdfn5xp1PKrW -> H7PiGqqUaanBovwKgEtreJbKmQe6dbq6VTrw6guy7ZgL"
```

**Corrected after adversarial review**: an earlier draft of this section
omitted Tx 1's own `ProposalApprove` instruction, listing only
`VaultTransactionCreate, ProposalCreate` -- independently re-fetched and
confirmed present in Tx 1's own logs (`Program log: Instruction:
ProposalApprove`, right after `ProposalCreate` succeeds). This matters
mechanically, not just cosmetically: the multisig's 2-of-5 threshold needs
TWO approvals, and the two-transaction narrative as originally written
showed only one (`ProposalApprove` in Tx 2), which alone could not have
satisfied that threshold. The real sequence is: Tx 1's signer creates the
proposal AND immediately casts the first approval (a self-approval, since
Squads lets a proposal's creator approve their own proposal); Tx 2, one
second later, casts the second approval (from a different signer) and
executes once the 2-of-5 threshold is met.

This is the actual mechanism, more precise than any single press write-up:
the multisig didn't touch user funds directly -- it executed Drift's own
`UpdateAdmin` instruction, reassigning Drift's protocol-level `admin`
pubkey field itself to the attacker's address. The 31 withdrawal
transactions that followed (not independently re-derived this pass, time-
boxed) would then have used that hijacked admin authority.

The multisig itself was identified and independently verified, not merely
assumed from the transaction's account list -- one of the four non-signer,
writable accounts in Tx 1 decodes with this project's own
`sol_read.py squads` as a real Squads v4 multisig:

```
$ sol_read.py squads <rpc> 2LW6PSEjp81xSEttWwXDB6Etb1eKdhYPbFEojYbyhx88
threshold=2  time_lock_s=0  members=5 (all mask=7, full permissions)
config_authority = A1eC8n2tQBHPodn8sZHsc5XWciunZy9B1VgmcHgK1xhP  (NOT the system default)
```

**Offline-derived, not just read**: this project's own `squads-vault`
PDA re-derivation for this exact multisig at vault index 0 produces
`AiLGdNitMjv8n5HMS7HAdV2kaeJZZFd4jdfn5xp1PKrW` -- an EXACT match for the
"admin" address the `UpdateAdmin` log shows being replaced. This confirms,
independently of trusting the transaction's own account ordering, that
`2LW6PSEjp81xSEttWwXDB6Etb1eKdhYPbFEojYbyhx88` really is the multisig that
controlled Drift's admin authority before the hack, and that its 2-of-5,
zero-timelock configuration (matching press exactly) is the real one, not
a different multisig incidentally present in the same transaction. One of
its five members, `39JyWrdbVdRqjzw9yyEjxNtTbTKcTPLdtdCgbz7C7Aq8`, is the
fee-payer/signer of Tx 1 -- a real, on-chain-identifiable signer, not
merely "someone" per the press account.

**A genuinely new finding, not reported by any source reviewed for this
backtest**: `config_authority` on this multisig was NOT the system default
-- meaning some other key or program (`A1eC8n2tQBHPodn8sZHsc5XWciunZy9B1VgmcHgK1xhP`,
itself off-curve, i.e. a further PDA) could unilaterally reconfigure this
multisig's members and threshold with no multisig vote at all. Not
resolved further this pass (the multisig is defunct/superseded today, so
there's nothing live left to trace this to) -- disclosed as a real,
independently-found aggravating factor beyond the "2-of-5, zero timelock"
headline, not chased down given the multisig no longer matters for
current risk.

## What this project's methodology would have said (2026-04-01 parameters)

```
kind = "squads_v4", threshold=2, voters=5, delay_s=0
adminKeyScore  = 40 + min(20, 5*(2-1)) = 45
multisigScore  = min(100, round(15*2 + 40*2/5)) = min(100, 46) = 46
timelockScore  = 0   (delay_s = 0, matches the zero-timelock finding exactly)
compositeScore = floor(0.4*45 + 0.3*46 + 0.3*0 + 0.5) = 32
```

`32/100` -- not the absolute floor this project reserves for a bare EOA
(Wasabi's `2/100`), but a real, correctly MODERATE-to-weak score reflecting
that a 2-of-5 threshold with zero delay is a meaningfully softer target
than a single key, while still being far short of what a 24h+-delay
autonomous Squads v4 setup would score (60-80). The independently-found
`config_authority` issue is NOT folded into this number -- this project's
own methodology (`chains/solana/scorers.py::_resolve_squads_v4`) already
declines to score the "config_authority set" band without a real target to
calibrate it against, the same discipline applied here rather than
guessing a worse number just because the finding is aggravating.

## What changed since: Drift's CURRENT authority, live-verified today

Drift's program (`dRiftyHA39MWEi3m9aunc5MzRF1JYuBsbn6VPcn33UH`) was last
deployed 2026-06-29 (slot 429731225, independently confirmed via
`getBlockTime`) -- after the hack. Its current loader-v3 upgrade authority
is now a DIFFERENT Squads v4 multisig, `7qipzLR9j1JcvdxE1XJEFgvoyFmgBpgw5hMdHBMPcJtM`
(offline vault-0 re-derivation confirms an exact match): **4-of-7
threshold** (one of the seven members, mask=1, has no Vote permission,
leaving 6 real voters), **`time_lock_s = 3600`** (a real 1-hour delay,
where before there was none), `config_authority` back to the system
default (autonomous, no external override this time).

```
This path alone (kind = "squads_v4", threshold=4, voters=6, delay_s=3600):
adminKeyScore  = 50 + min(20, 5*(4-1)) = 65
multisigScore  = min(100, round(15*4 + 40*4/6)) = min(100, 87) = 87
timelockScore  = round(50 * (3600/3600) / 24) = round(50/24) = 2
compositeScore for THIS path alone = floor(0.4*65 + 0.3*87 + 0.3*2 + 0.5) = 53
```

**Corrected after adversarial review**: an earlier draft of this section
jumped straight from these single-path numbers to a bare `= 48`, which is
not what that formula evaluates to (`53`, as shown above) -- an internal
inconsistency, not a different number pulled from nowhere. `48` IS the
correct, live-verified score for Drift Protocol as a whole, but only once
METHODOLOGY.md 6.2's "minimum over every full-power path" rule is applied
against the SECOND path (Drift DAO's own Realms governance -- self-
governed, unlike Solend's bare EOA, with `multisigScore = 70`, lower than
this path's `87`): `multisigScore = min(87, 70) = 70`, giving
`compositeScore = floor(0.4*65 + 0.3*70 + 0.3*2 + 0.5) = 48`. Full
derivation of both paths and the combination step:
`chains/solana/data/methodology_test_2026-09-17-drift-protocol.md`.

Either way -- `53` for this path alone, or `48` combined -- this is a real
improvement over the incident-era `32`, consistent with a genuine post-
incident reform (higher threshold, a real delay where none existed), but
the STILL-short 1-hour delay is what caps `timelockScore` at 2 and keeps
the overall composite well short of a strong score -- this project's own
formula correctly does not reward "some delay" as much as "meaningful
delay" (the same curve that gives a 24h Squads delay `timelockScore=50`).
Full derivation, including a second full-power path (Drift DAO's own
Realms governance, which is self-governed and materially SLOWER):
`chains/solana/data/methodology_test_2026-09-17-drift-protocol.md`.

## Honest limitations of this backtest

- **The 31 actual withdrawal transactions that drained the $285M were NOT
  individually re-derived this pass** -- time-boxed rather than left
  unstated. What IS independently verified: the two transactions that
  actually hijacked the admin authority itself (the root cause), matching
  every technical detail press coverage reported (timestamps to the
  second, the exact multisig threshold/delay, the exact admin-address
  swap) plus one new detail no source reviewed reported (the non-default
  `config_authority`).
- **`config_authority = A1eC8n2tQBHPodn8sZHsc5XWciunZy9B1VgmcHgK1xhP` was
  not traced further.** The multisig is defunct today (superseded by the
  current one), so there is no live risk to chase, but a stronger version
  of this backtest would identify what that PDA was and whether it was
  itself a legitimate Drift-controlled account or a further weakness.
- **This is a retrospective classification, not a real-time flag.** Drift
  was never a tracked target of this oracle before this backtest.
- **Attribution (North Korea/Lazarus per TRM Labs) was not independently
  verified** -- outside this project's own on-chain-verification scope,
  cited from TRM Labs only.

## Reproduction

```bash
curl -s https://api.mainnet-beta.solana.com -X POST -H "Content-Type: application/json" -d \
  '{"jsonrpc":"2.0","id":1,"method":"getTransaction","params":["4BKBmAJn6TdsENij7CsVbyMVLJU1tX27nfrMM1zgKv1bs2KJy6Am2NqdA3nJm4g9C6eC64UAf5sNs974ygB9RsN1",{"encoding":"jsonParsed","maxSupportedTransactionVersion":0}]}'

python3 chains/solana/scripts/sol_read.py squads https://api.mainnet-beta.solana.com 2LW6PSEjp81xSEttWwXDB6Etb1eKdhYPbFEojYbyhx88
python3 chains/solana/scripts/sol_read.py squads-vault - 2LW6PSEjp81xSEttWwXDB6Etb1eKdhYPbFEojYbyhx88 0
python3 chains/solana/scripts/sol_read.py program https://api.mainnet-beta.solana.com dRiftyHA39MWEi3m9aunc5MzRF1JYuBsbn6VPcn33UH
python3 chains/solana/scripts/sol_read.py squads https://api.mainnet-beta.solana.com 7qipzLR9j1JcvdxE1XJEFgvoyFmgBpgw5hMdHBMPcJtM
```
