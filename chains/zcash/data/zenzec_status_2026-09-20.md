# Zenrock zenZEC: status as of 2026-09-20 (Zcash target 7 is a frozen snapshot)

Phase: `deploy_testnet` (Zcash). This note changes how target 7 is presented; it changes no score and
re-anchors nothing (the three Testnet anchors are immutable and include this target).

## Summary

Zcash target 7 (`keyring1k6vc6vhp6e6l3rxalue9v4ux`, Zenrock's dMPC keyring, composite 44) was read from a
single operator-run zrchain node. That node reports its last block at height 9,534,552, block time
2026-08-10T23:19:52Z, about 40 days before this note, with no peers. The product behind it, zenZEC, shows every
sign of a wind-down: no mint since 2026-03-17, its Solana mint authority list emptied on 2026-03-26, the
operating company in UK administration since 2026-04-08, and the ZEC that backed it consolidated into one
address that is not derived from any key of the keyring. So composite 44 describes a keyring structure as
it was read at that height. It is not a live risk reading and must not be shown as one.

## How this was established

Three independent modalities and two adversarial skeptics, run on 2026-09-20 between about 11:00 and 12:45
UTC: Solana on-chain forensics on several public RPC operators (four readers, three operators, plus an
explorer), public-source research, and an attempt to establish zrchain liveness from independent endpoints
(it found none). The maintainer's session then re-checked, itself, three load-bearing facts: the Solana
authority chain of the zenZEC mint, Zenrock Laboratories Ltd's status at Companies House ("In
Administration"), and the balance of the address holding the backing on two lightwalletd operators. Where a
fact below was reproduced only by the investigators, it says so.

## Established (on-chain or a fetchable register)

| Fact | Evidence |
|---|---|
| zenZEC supply is 494.51437135, freeze authority none, mint `JDt9rRGaieF6aN1cJkXFeUmsy7ZE4yY3CZb8tVMXVroS` | Solana, several RPC operators |
| Mint authority `6kgpWRR277ZeibFzgEVVXaYz2AztVTD5bCbVEiFq13Mk` is an SPL Token multisig 1-of-1; its sole signer `8y1Zmkj4uJhU9ykuK7hXgTar1YeoDASX2CnhpD8EsJ7s` is a program-derived account owned by program `BTzxmuLgNUfBeNCFxsoSVpEKjRTma75eWcaPjyDCUF88` | re-derived by the maintainer's session and by the investigators |
| That program is upgradeable, last deployed 2025-11-28 12:53 UTC (slot 383091028), upgrade authority `2RoRSPwFmMcFDd3DLgoomMRFkhUSaVNSDo7XyH2tw6de`, a single ed25519 key that signed that upgrade; no timelock or multisig is observed on it. It is not the Solana wallet of any zrchain key read | re-derived by the maintainer's session and by the investigators |
| That key was active on 2026-09-10 (one signature seen: a USDC transfer) | investigators |
| The program's mint-authority list was emptied on 2026-03-26 13:54 UTC by two calls signed by that key; the last wrap was 2026-03-17 and the last user unwrap 2026-03-20; no program instruction since 2026-03-26 | decoded state and transactions, reproduced by several investigators (not re-derived by the maintainer's session) |
| Zenrock Laboratories Ltd (UK company 15425285) has status "In Administration" | Companies House, read by the maintainer's session on 2026-09-20 |
| The zrchain public RPC (`rpc.diamond.zenrocklabs.io`, three backends behind one ingress) reports height 9,534,552 / 2026-08-10T23:19:52Z and 0 peers. Other listed endpoints do not resolve or answer 502/503 | maintainer's session and investigators |
| `t1g7BWsvsqfiYb2j1ManbK6gKhmYjXLAFn4` holds 498.73980102 ZEC (1.0085 times the supply), received by consolidation transactions at blocks 3,391,499 and 3,391,502 (2026-06-26) and not spent since | two lightwalletd operators, maintainer's session |
| The 547 Zcash addresses derived from the keyring's 547 secp256k1 keys hold 3,000 zat in total, and `t1g7BWs...` is not derived from any of the 613 keys read | investigators, three independent derivations |

## Probable, not proven

- **A deliberate wind-down led by the Foundation and the administrators, starting with an emergency stop on
  2026-03-26.** All three modalities lean this way. The on-chain stop, the register status and the silence
  of the project's channels support it. The Foundation's own statements (reported wind-down announcement of
  2026-04-10, and a 2026-07-01 update that the administrators were seeking legal guidance) were read on its
  X account in a logged-out browser by two investigators and cannot be reproduced by machine. Treat them as
  reported.
- **zrchain has stopped producing blocks.** All the evidence comes from Zenrock-operated backends that see no
  peers, so an isolated RPC fleet fits equally. This note says "frozen at height X as seen from the operator
  RPC", never "halted".
- **The June ZEC sweeps were an authorised custody move.** The funds were consolidated, not dispersed, and
  sit at 1.0085 times the supply, untouched for 86 days. But the address is not derived from the keyring, and one investigator, reading the frozen node's own
  transaction search, found no signing request recorded on zrchain after 2026-03-26, so compromise cannot be
  ruled out from the chain.
- **No working redemption path exists today.** No unwrap has been processed since 2026-03-20 and none was
  simulated. "No path observed" is supportable. "Cannot be redeemed" is not: an off-chain redemption from
  the reserve remains possible.

## Unknown

Who controls `t1g7BWs...` and whether the movements were authorised; who holds the upgrade key and what
the September transfer was for; whether zrchain is halted or its RPC fleet isolated; whether zenZEC can
be redeemed at all, and whether the promised redemption programme exists; what the administrators' filings
of June and July say (not opened); whether the frozen key table matches the live keyring.

## Corrections to the 2026-09-19 note

- The keyring holds 613 keys (ids up to 648), not the 428 counted on an earlier partial read. It is generic,
  not zenZEC-exclusive.
- Key 388 (`t1S9DvnjtxgP4HMo1W6sTxVh95f6cmZ9dcw`) has 36 transactions, a peak balance of about 451 ZEC and a
  last spend on 2026-06-05; key 387 (`t1WrUBdocqpubAHoRrpihYBoDFjPg7utLka`) never had one. A zero balance on
  either is a sweep, not an absence of custody.
- Composite 44 is unaffected: `score_zenzec_mpc_keyring()` computes it only from the keyring's party threshold
  (3 of 3 parties) and the fixed timelock, oracle and cross-exposure terms. The balance reads are notes. The
  score is not recomputed and the history is preserved.

## The Solana authority chain (an unscored observation)

Any future minting of zenZEC depends on one chain: mint authority (SPL multisig 1-of-1) to the program's
config account to the program, whose upgrade authority is one live single-signature key. With the mint
authority list empty, nobody can mint until that key adds one or upgrades the program. It is documented here,
not scored: a single upgrade authority is the Solana default, who holds the key is unknown, and the product is
winding down, so a number would imply an exposure that is not live. It becomes a candidate target if any of
these happens: the program's deployment slot changes from 383091028; an admin instruction by that key (add a
mint authority, change the global authority); any mint of zenZEC; any spend from `t1g7BWs...`; an
administrator-published redemption programme that relies on this program or a new one; independent evidence
that zrchain is producing blocks. `scripts/zenzec_status_check.py` prints these triggers.

## The August 2026 Solana activity is not a migration

Between 2026-08-02 and 2026-08-07 an unrelated key deployed a look-alike test program
(`CkUW6hJrnMLm68krLQeNJMwSNrEd2EPvqtRWAstExTSi`), ran two dust-sized calls (one burn of 0.01413427 of its own
zenZEC) and closed the program's data account on 2026-08-06 14:48 UTC. It never invoked the real program. The
actor is unidentified. It was first mistaken here for a Zenrock operation before being ruled out.

## What this means for target 7

- Flag now: it is presented as a frozen snapshot, single source, with the wind-down context (scorer notes, this
  note, the dashboard badge, SUBMISSION).
- Do not refresh it: there is no independent source to refresh from.
- Do not substitute `t1g7BWs...` for it: its controller is unknown, so an authority score would be false
  precision. It is an unscored watch item.
- Retire it, without deleting it, at the next anchor: publish it as a legacy snapshot and keep it out of
  every live aggregate. **Done on 2026-09-20 on Spap's call** (`chains/zcash/METHODOLOGY.md` 4.8.1, "Retired on
  2026-09-20"): `score_all()` no longer returns it, the legacy snapshot is
  `legacy_snapshot_zenzec_keyring_2026-09-20.json`, and the anchor of the same evening (txid `462de12bf72e5e635a1feed4a4cedb02c03f17745bd15176787f8f5f8fcd701c`, block
  4,371,248) covers the six live targets. The two anchors made before this date are unchanged and still contain it.
- Reversal: lift the flag and re-read if block production is confirmed from an independent endpoint or the
  keyring is shown signing inside zrchain again.

## Not claimed

That zrchain is halted; that the ZEC was stolen, or that it is safe; that the product "is in administration"
(the operating company is); that the upgrade key is a hot key or held by a person; that zenZEC is worthless
(there is no functioning market, prices are stale); that the August activity or the September drain of an
unrelated program says anything about the upgrade key.

## Reproduce

`python3 chains/zcash/scripts/zenzec_status_check.py` (read-only, public data) prints the authority chain, the
program's deployment slot, the upgrade key's latest signature, the mint's latest non-price activity, the
backing address balance and the zrchain tip. Companies House:
`https://find-and-update.company-information.service.gov.uk/company/15425285`.
