# Retroactive backtest: Wasabi Protocol ($5.9M, 2026-04-30)

Item 8 of the after-hackathon roadmap: would this project's methodology have
flagged a real, already-happened incident as high risk, using facts anyone
can re-verify live today -- not a claim taken on faith from a citation.

## The incident, as independently corroborated

- **DeFiLlama's own hacks database** (`api.llama.fi/protocol/wasabi`,
  queried live 2026-09-17): `classification: "Key Compromise"`,
  `technique: "Deployer Key Compromised"`, `amount: $5,500,000`,
  `chain: ["Ethereum", "Base", "Berachain", "Blast"]`, `date: 1777507200`
  (decodes to 2026-04-30, matching every press citation).
- **rekt.news's technical writeup** (2026-05-04, credited to QuillAudits,
  PeckShield, Blockaid, CertiK, Hypernative, Cyvers, Blocksec Phalcon, TRM
  Labs): the deployer EOA "held unchecked ADMIN_ROLE across every
  upgradeable vault Wasabi had ever deployed. No multisig shared that
  authority. No timelock slowed it down. No governance body had a vote. One
  wallet. One key. Total control." Mechanism: the deployer key granted
  `ADMIN_ROLE` to an attacker-controlled helper contract, which then
  upgraded the perp vaults and LongPool (UUPS proxy pattern) to a malicious
  implementation that drained balances. 840.9 WETH from a single wWETH
  vault, seven other vaults emptied in the same transaction, then the same
  playbook repeated simultaneously on Base, Berachain, and Blast. Total:
  $5.9M.
- **Blockaid's own incident tweet** independently named the exact
  compromised address: `0x5C629f8C0B5368F523C85bFe79d2A8EFB64fB0c8`
  ("Wasabi: Deployer" on Etherscan), and warned that every Wasabi/Spicy
  LP-share token should be treated as compromised while that key remained
  live.

## What was independently re-verified live today (2026-09-17), not just cited

```
0x5C629f8C0B5368F523C85bFe79d2A8EFB64fB0c8 (Blockaid-confirmed compromised deployer)
  eth_getCode  = 0x  (0 bytes -- a real, bare EOA, still true today)
  eth_getTransactionCount = 5366  (a real, actively-used key over 3+ years,
                                    not a throwaway or an anomaly)
  balance      = 0.007 ETH
```

A genuinely interesting side-finding, exactly the kind of "never trust a
name" trap this project's own discipline exists to catch: the ENS name
`wasabideployer.eth` cited in press coverage currently resolves (live
lookup, today) to a **different** address, `0x2eB7F20c38455AE3d5F21D01eFEa
49988E043Cc4` -- also a bare EOA, but NOT the same one Blockaid identified
as the actually-compromised key. Either the ENS name was reassigned since
the incident, or press coverage conflated the informal name with the
Etherscan-labeled "Wasabi: Deployer" address -- not resolved further this
pass; the Blockaid-confirmed address is the one used below, since it's
independently corroborated by the incident responders themselves, not a
name a journalist typed.

## What this project's methodology would have said

This project's own scoring convention (`scripts/lib/scorers.py::_composite()`,
documented in `METHODOLOGY.md`) treats a bare EOA with no Safe layer and no
timelock exactly the way several currently-tracked Robinhood Chain targets
with this identical shape are scored today -- Curve DEX's controller and the
Robinhood tokenized-stock beacon's admin both score **1/100** for precisely
this pattern (`adminKeyScore` in the 2-5 range for a bare EOA, `multisigScore
= 0`, no Safe found, `timelockScore = 0`, no delay found):

```
adminKeyScore ~ 5   (bare EOA, near-worst-case per this project's convention)
multisigScore = 0   (no Safe layer -- confirmed, this IS the root, not a
                      Safe-wrapped intermediate)
timelockScore = 0   (no delay -- rekt.news's own reporting confirms none existed)
compositeScore = floor(0.4*5 + 0.3*0 + 0.3*0 + 0.5) = 2/100  -- CRITICAL band
```

A `2/100` composite score, in the same CRITICAL band this project's dashboard
already uses for its worst-scored real targets, computed from the exact same
formula already live on Robinhood Chain today -- not a bespoke "would have
caught it" narrative invented after the fact.

## Honest limitations of this backtest

- **The specific vault contract's `hasRole(ADMIN_ROLE, deployer)` call was
  NOT independently re-verified this pass** -- time-boxed rather than left
  unstated. What IS independently verified: the deployer address itself
  (Blockaid-confirmed, cross-referenced against DeFiLlama's and rekt.news's
  independent accounts of the same incident) is a real, long-lived, bare
  EOA today, which is the necessary precondition for the scoring claim
  above, not a sufficient proof that this exact contract call would have
  returned `true` before the exploit. A stronger version of this backtest
  would find the actual vault proxy address, its `ADMIN_ROLE` holder at a
  block before 2026-04-30 (an archive RPC, same technique as this pass's
  Ethena StakedUSDeV2 investigation), and confirm the live call resolves to
  this same address -- flagged as real follow-up work, not silently skipped.
- **This is a retrospective classification, not a real-time flag.** Wasabi
  was never a tracked target of this oracle before the incident -- this
  backtest demonstrates the METHODOLOGY would have scored this authority
  shape as critical, not that this project actually caught it live.
- **DeFiLlama cites $5.5M, most press cites $5.9M** for the same incident --
  a real, disclosed discrepancy between sources, not silently resolved by
  picking whichever number looked better.

## Reproduction

```python
from web3 import Web3
w3 = Web3(Web3.HTTPProvider("https://ethereum-rpc.publicnode.com"))
addr = w3.to_checksum_address("0x5C629f8C0B5368F523C85bFe79d2A8EFB64fB0c8")
print(len(w3.eth.get_code(addr)))          # 0 -- bare EOA
print(w3.eth.get_transaction_count(addr))  # a real, active nonce
```

```bash
curl -s "https://api.llama.fi/protocol/wasabi" | python3 -c "import json,sys; print(json.load(sys.stdin)['hacks'])"
```
