# Authority-related incidents 2024 to September 2026: evidence table and what it can and cannot calibrate

Compiled on 21 Sep 2026 by a research reviewer (web search and page reads only, no on-chain reads), then spot-checked by me.
**Read this as a lead list, not as verified data.** I opened three rows (Humanity, AFX, CrediX) and corrected two details; two
more incidents (SquidRouterModule, rsETH) I corroborated with separate searches, and Drift matches this repository's own backtest.
The other rows are the reviewer's reading of the cited page and I did not open them.

| Date | Protocol | Loss | Class | Configuration when it happened (only what the source states) | How authority was obtained | Source | My check |
|---|---|---|---|---|---|---|---|
| 2024-03-26 | Munchables | $62.5M | insider | upgradable proxy, owner is the developer's EOA, no timelock | hired developer, DPRK link per Halborn | [Halborn](https://www.halborn.com/blog/post/explained-the-munchables-hack-march-2024) | not opened |
| 2024-05-20 | Gala Games | about $21.8M sold (5B GALA minted) | role key | MINTER role on an EOA dormant for about 180 days, no timelock | key compromised, vector unknown | [Halborn](https://www.halborn.com/blog/post/explained-the-gala-games-hack-may-2024) | not opened |
| 2024-07-18 | WazirX | $235M | blind signing | Safe 4/6 (5 WazirX + 1 Liminal), no timelock | phishing and a fake Liminal UI | [QuillAudits](https://www.quillaudits.com/blog/hack-analysis/wazirx-235m-hack) | not opened |
| 2024-09-16 | DeltaPrime | $6M | admin key | proxy admin is an EOA, no timelock | key leaked, cause unknown | [The Block](https://www.theblock.co/post/316625/defi-protocol-delta-prime-suffers-6-million-exploit-after-admin-lost-control-of-private-key) | not opened |
| 2024-10-16 | Radiant | $53M | blind signing | Safe 3/11, no timelock (72 h added afterwards) | malware through a fake PDF, hardware wallet did not parse the Safe transaction | [Radiant post-mortem](https://medium.com/@RadiantCapital/radiant-post-mortem-fecd6cd38081) | not opened |
| 2025-02-21 | Bybit | $1.46B | UI supply chain | Safe 3/6, no timelock on the masterCopy | malicious JavaScript served from Safe{Wallet}'s storage | [NCC Group](https://www.nccgroup.com/research/in-depth-technical-analysis-of-the-bybit-hack/) | not opened |
| 2025-02-24 | Infini | $49.5M | insider | admin role kept by the contract's developer | rights never revoked | [Decrypt](https://decrypt.co/307513/crypto-neo-bank-infini-50-million-exploit) | not opened |
| about 2025-02-05 | Ionic Money | $8.6M | role abuse (listing) | listing admin, timelock unknown | social engineering (fake Lombard) | [Rekt](https://rekt.news/ionic-money-rekt) | not opened |
| 2025-04-01 | UPCX | $70M | admin key | ProxyAdmin key, no timelock | key leaked, cause unknown | [Halborn](https://www.halborn.com/blog/post/explained-the-upcx-hack-april-2025) | not opened |
| 2025-04-14 | KiloEx | $7.5M | access-control bug | Keeper role, forwarder without a check | role spoofed through a bug | [Halborn](https://www.halborn.com/blog/post/explained-the-kiloex-hack-april-2025) | not opened |
| 2025-08-04 | CrediX | $4.5M | role grants | ACLManager roles (pool, risk and bridge admin) given by the multisig to a new address about 6 days earlier | multisig compromised or insider | [Halborn](https://www.halborn.com/blog/post/explained-the-credix-hack-august-2025) | **source unreachable (HTTP 429), not verified** |
| 2025-09-08 | SwissBorg | $41M | delegated authority | stake authority run by partner Kiln | partner API compromised, authority transferred on 31 Aug | [QuillAudits](https://www.quillaudits.com/blog/hack-analysis/swissborg-exploit) | not opened |
| 2025-09-22 | UXLINK | at least $11.3M | multisig takeover | Safe, threshold unknown, no timelock | delegatecall then `addOwnerWithThreshold` | [The Block](https://www.theblock.co/post/371783/uxlink-multisig-hack) | not opened |
| 2026-01-31 | Step Finance | about $40M | team keys | Solana treasury, configuration unknown | executives' devices compromised | [BleepingComputer](https://www.bleepingcomputer.com/news/security/step-finance-says-compromised-execs-devices-led-to-40m-crypto-theft/) | not opened |
| 2026-03-22 | Resolv | $23M to $25M | off-chain service key | SERVICE_ROLE signed off-chain, no cap or sanity check | AWS KMS compromised | [Chainalysis](https://www.chainalysis.com/blog/lessons-from-the-resolv-hack/) | not opened |
| 2026-04-01 | Drift | $285M | pre-signing and governance | Security Council 2/5, timelock 0 after a migration on 26-27 Mar | two of five signers tricked (durable nonce, months of social engineering) | [BlockSec](https://blocksec.com/blog/drift-protocol-incident-multisig-governance-compromise-via-durable-nonce-exploitation) | matches this repository's own backtest and a QuillAudits read (2/5, zero timelock, admin transfer 1 Apr) |
| 2026-04-18 | Kelp DAO bridge | $292M | verification authority | verifier set of one (DVN 1-of-1), no timelock | two LayerZero RPC nodes compromised plus DDoS | [Chainalysis](https://www.chainalysis.com/blog/kelpdao-bridge-exploit-april-2026/) | the amount is also in this repository's README; not opened |
| 2026-05-07 | TrustedVolumes | $6.7M | self-assignable role | public signer-registration function | access-control bug | [FinanceFeeds](https://financefeeds.com/15-biggest-crypto-blockchain-exploit-hacks-2026/) | single aggregator source |
| about 2026-05-15 | SquidRouterModule | $3.2M to $4M | faulty Safe module | 86 Safes had enabled the module, which bypasses the threshold | a fixed string readable in the verified code | [Halborn](https://www.halborn.com/blog/post/explained-the-squidroutermodule-hack-may-2026) | corroborated by several outlets (Halborn, Common Prefix, AMBCrypto, others) |
| 2026-05-18 | Echo eBTC | $76.7M notional, about $0.87M real | single admin key | single-signature admin, no timelock, no mint cap | key compromised | [Cointelegraph](https://cointelegraph.com/news/echo-protocols-ebtc-exploited-for-76m-in-admin-key-compromise) | Echo is a live target of this oracle (37); not opened |
| 2026-06 (reported 9 Jun) | Humanity Protocol | $32M to $36M | multisig keys on one device | Safe 3/6 (Ethereum) and 3/5 (BNB Chain); keys accidentally backed up to one compromised device | device compromise | [CoinDesk](https://www.coindesk.com/tech/2026/06/09/humanity-s-usd36-million-exploit-happened-because-a-multisig-wallet-lived-on-one-laptop) | **checked**: loss, thresholds and cause match; **the article does not state a ProxyAdmin timelock** (the reviewer wrote "none") |
| 2026-07-22 | AFX Trade | $24.15M | quorum reached with stolen keys | two-thirds quorum, five hot validator signatures | validator keys held off-chain compromised | [CoinDesk](https://www.coindesk.com/tech/2026/07/23/arbitrum-based-afx-trade-drained-of-usd24-million-after-bridge-keys-compromised) | **checked**: loss and quorum match; **a 200-second dispute period existed** (the reviewer wrote "no timelock") and the validator set size is not stated (the reviewer wrote 5 of 7) |
| 2026-09-15 | rsETH Safe of a liquidity provider | $7.7M to $7.8M | buggy strategy module | module enabled by the owners, public DELEGATECALL entry, zero signatures needed | public keeper multicall | [Crypto Times](https://www.cryptotimes.io/2026/09/15/7-8m-rseth-drained-from-ethereum-safe-wallet-mev-bot-yoink-front-runs-the-exploit/) | corroborated by several outlets |

Set aside for lack of a second source: Term Labs (August 2026, $8.5M, vault governance abuse) and THORChain (May 2026, $10.8M,
malicious validator in a TSS scheme).

## What the table supports (the reviewer's answers, with my edits)

23 incidents, about $2.75B in total; amounts differ between outlets, and Bybit, WazirX, SwissBorg and Step are custodial actors
rather than DeFi protocols, which inflates the key-and-signer share.
- **Single key or low threshold:** 9 of 23 (39%); 29% of the dollars, 63% without Bybit.
- **Thresholds are rarely published:** documented for 7 of 23 (1/1, 2/5, 3/6 twice, 3/5, 3/11, 4/6); unknown for 16.
- **Timelocks:** no case of a documented timelock that existed and was bypassed. Absence is written in the source for two cases (Drift,
  Echo) and only inferred for others (an upgrade or ownership transfer executed right after signing). Radiant added a 72 h timelock afterwards.
  Note the AFX correction: a 200-second dispute period existed there, so "no delay at all" is not always the right reading.
- **The threshold gave no protection:** blind signing, falsified UI or pre-signing (Bybit, WazirX, Radiant, Drift), a module that bypasses
  signatures (SquidRouterModule, rsETH), and three cases where the quorum was reached with stolen keys (AFX, Humanity, Radiant).
- **What visibly separates victims from others: nothing that can be shown.** The common attribute is "a privileged path that runs without a
  delay" (at least 17 of 23 by the reviewer's reading), but there is no sample of protocols that were not hit, so any link between
  a configuration and an incident is untestable here (survivorship). A real test would need the configurations (threshold, timelock, modules,
  role holders) of comparable protocols a month before the incident, victims and non-victims.
- **What a scorer that reads threshold, signers, timelock, modules and role holders could have seen beforehand:** Drift (2/5 and the timelock
  set to 0 about five to six days earlier), Kelp (verifier set of one), Echo (single-signature admin, no cap), Infini (a leftover admin role), Munchables
  (owner is the developer's EOA), the missing timelock on WazirX, Bybit, UXLINK and Humanity, the modules of Squid and rsETH, and the authority
  changes at SwissBorg and Step. **What it could not have seen:** a compromised laptop, a falsified UI or a supply-chain script, a key
  inside a key-management service, pre-signed transactions not yet broadcast, a partner's API, an insider's intent, and above all the code of a module or forwarder.

## What this means for the oracle

1. **Do not claim prediction.** The honest claim is "measured exposure of the authority path", because the data cannot show that any configuration
   predicts incidents.
2. **Configuration changes are the leading indicator with days of lead time.** Drift (timelock removed about five to six days before, per the reviewer's 26 Mar and QuillAudits' 27 Mar), CrediX (roles granted
   about six days before, unverified) and SwissBorg (authority transferred eight days before, unverified) all show a change on chain days before the loss. This is the
   evidence-based reason to prioritise the posture-change monitor: timelock lowered or removed, role granted to a new address, owner added or threshold
   lowered, module enabled.
3. **Publish what the oracle cannot see.** Device compromise, falsified UI and supply-chain scripts, keys in a key-management service, pre-signed
   transactions, partner APIs, insider intent and module code all sit outside a configuration read (see the list above). A stated coverage limit is more credible than a silent one.
