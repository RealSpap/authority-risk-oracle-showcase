# Fluid Liquidity on Plasma: proposer and executor signer sets resolved, 2026-09-20

Phase: `maintenance` (Plasma). Changes the scorer of one target, `score_fluid_liquidity_plasma()`, from
40 / 100 / 70 / cross 100 (composite 67) to 65 / 55 / 55 / cross 80 (composite 59). Pushed on-chain the same evening
(Plasma testnet tx `0x3c709f07756416a72c5fce1bd96ffa482b52df3c8bd2a9d283f88aa263e0f645`, block 34,100,595, read back 9 of 9 equal to the scorer): the oracle
held the old values until then.

## Why

The first Plasma pass (`fluid_liquidity_plasma_2026-09-18.md`) tried only the Safe ABI on the two role holders of the
Timelock, saw both revert, and left "proposer/executor signer strength unresolved", which capped `adminKeyScore` at 40 and
left `multisigScore` at 100 ("not applicable") and `crossExposureScore` at 100 ("not computed"). The Arbitrum pass of
2026-09-19 then read the same proposer with the right ABI (an Avocado multisig: `requiredSigners()`, `signers()`) and scored
the same structure on Arbitrum One as 65 / 55 / 55, cross 80, composite 59, writing that the same 12 signers and 6 required are
live on Plasma. The Plasma scorer was never updated, so the same authority structure carried two different published scores
(67 on Plasma, 59 on Arbitrum), and the Plasma row still said "not computed" for a cross-ecosystem overlap the Arbitrum
scorer had already found. The convention decided on 2026-09-20 (METHODOLOGY.md, "a cross-ecosystem overlap IS folded into
`crossExposureScore`, everywhere") folded Pendle and the two Euler targets on Plasma that day and did not reach Fluid.

## What was read (Plasma mainnet, chain 9745, and Arbitrum One, chain 42161, 2026-09-20)

| Fact | Plasma | Arbitrum |
|---|---|---|
| `0x4F6F977a...` (`DOMAIN_SEPARATOR_NAME()` = "Avocado-Multisig"): `requiredSigners()` | 6 | 6 |
| same address `signers()` | 12, identical set | 12, identical set |
| `0x196Ed45e...` (Safe v1.4.1): `getThreshold()` / `getOwners()` | 3 of 5, identical owners | 3 of 5, identical owners |
| Liquidity `getAdmin()` (the Timelock `0x4d6CE4F4...`), `getMinDelay()` | 86,400 s | 86,400 s (Arbitrum note) |

Four of the five executor Safe owners (`0x1d895e5c...`, `0xa7615cd3...`, `0xc0c72156...`, `0xd33d3fce...`) are also among the
12 Avocado signers. So three signers taken from that overlap would reach the executor Safe threshold, whereas the
proposer needs six. This is disclosed, not scored: both scorers take the weaker of the two sets, as `scripts/lib/scorers.py` does.

## Paths that skip the delay (Plasma)

`LogUpdateAuths((address,bool)[])` and `LogUpdateGuardians((address,bool)[])` events of the Liquidity contract, fetched from the
Routescan explorer API and each re-fetched from the Plasma node by block and matched on transaction hash and data:

| Block | Event | Change |
|---|---|---|
| 746,572 | LogUpdateAuths | `0x0ed35b16...` added (an EOA, no code) |
| 746,572 | LogUpdateGuardians | `0x4F6F977a...` (the Avocado multisig) added |
| 1,805,948 (one transaction) | LogUpdateAuths, four entries | `0x40385e34...`, `0x3a05f8f4...`, `0x46cc616a...`, `0x1da5e212...` added |
| 1,815,777 | LogUpdateAuths | `0x0ed35b16...` removed |

Active now: four auths and one guardian. Each of the four auths is a contract (3,845 to 5,158 bytes of code) whose
`TEAM_MULTISIG()` returns the same Avocado multisig, and the only guardian is that multisig. This is the same shape as on
Arbitrum (four config-handler auths and the same guardian), with different handler addresses. What those handlers can do is
taken from the Arbitrum analysis (bounded config and pause powers that skip the delay); it was not re-derived here for the Plasma
handler contracts, whose bytecode sizes are not all the same as Arbitrum's (4,616 bytes here against 4,606 there).
A scan of the node alone, from block 0 to block 32,983,976 in 6,250-block windows and without the explorer, finds exactly these
seven events (six auth events, one guardian event), identical in data and order to the explorer's, so the list above does
not depend on the explorer being complete.

The scorer does not read these events (it would need a log scan on every run). It states the path in its docstring and caps
`timelockScore` at 55, exactly as the Arbitrum scorer does, and this note is the enumeration behind that statement.

## Scoring

Same rule as the Arbitrum Fluid scorer, for the same structure:

| Sub-score | Before | After | Rule |
|---|---|---|---|
| adminKeyScore | 40 | 65 | the weaker signer set needs at least 3 signatures (6 of 12 and 3 of 5) |
| multisigScore | 100 | 55 | the weaker of `min(100, k*15 + max(0, n-k)*5)`: 6 of 12 gives 100, 3 of 5 gives 55 |
| timelockScore | 70 | 55 | a real 24 h delay, capped for the bounded path outside it |
| crossExposureScore | 100 | 80 | the proposer signer set read on Plasma equals the Arbitrum committee, as a set |
| composite | 67 | 59 | `(4*65 + 3*55 + 3*55 + 5) // 10` |

Two other rules change with it, for the same reason (an unconfirmed result must never score above the confirmed one):
a Timelock whose roles, signer sets or executor Safe are not confirmed this run scores the floor (20, 0, 0) instead of
(20, 100, 70), and a timelock with a zero delay is no longer treated as confirmed (it reached adminKey 40 before). Both match
the Arbitrum scorer.

Live neutrality: the other eight Plasma targets read identical before and after (`live_diff` of the two trees on public RPCs
the same day); only Fluid moves, and it moves down by 8 composite points. The oracle was rewritten by the push above, not by the scorer change itself.

## Not claimed

That the Plasma auth handlers are the same contracts as the Arbitrum ones, or that their powers are bounded (inherited, not
re-derived); that the 12 Avocado signers are independent people (unknown, only the address overlap with the Safe is shown);
that the guardian or the auths cannot pause or change configuration without the delay (they can, that is why the timelock is capped).

## Reproduce

`python3 chains/plasma-ecosystem/scripts/fluid_signers_check.py` (read-only, public RPCs and the Routescan API; add `--full-scan`
for the node-only completeness scan, about 15 minutes). It prints OK/FAIL lines and finishes with `RESULT: ALL CHECKS PASS`.
