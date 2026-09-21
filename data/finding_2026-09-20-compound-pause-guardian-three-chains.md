# Finding (2026-09-20): Compound V3's pause guardian is one 9-signer committee on three chains

## How it surfaced

The cross-ecosystem overlap sweep (`scripts/check_cross_ecosystem_overlap.py`) is the tool that found the
Aave guardian committees on five chains and the Morpho committee on four, but its registry only listed the
Safes each scorer already knew about. A coverage count on 2026-09-20 showed how thin that was: of the tracked
targets on each oracle, the registry named 7 of 20 on Ethereum L1, 6 of 10 on Arbitrum, 3 of 9 on Base,
7 of 9 on Plasma, 7 of 9 on Monad and 2 of 14 on Tempo (Robinhood 62 of 62). This pass ran every unregistered
target's scorer, took the Safes and bare EOAs its notes name, checked each on chain, and registered the real
ones (11 new groups plus Compound on Base).

## The finding

`Comet.pauseGuardian()` for the USDC market is a Gnosis Safe on each chain, read live on each chain's public RPC:

| Chain | pauseGuardian Safe | Threshold | Owners |
|---|---|---|---|
| Ethereum L1 | `0xbbf3f1421D886E9b2c5D716B5192aC998af2012c` | 5-of-9 | 9 (8 bare EOAs, 1 contract) |
| Arbitrum | `0x78E6317DD6D43DdbDa00Dce32C2CbaFc99361a9d` | 5-of-9 | the same 9 |
| Base | `0x3cb4653F3B45F448D9100b118B75a1503281d2ee` | 5-of-9 | the same 9 |

Three different Safe addresses, byte-identical owner sets, compared as sets. The seat can pause supply, transfer,
withdraw, absorb and buy instantly, outside the timelock: an availability power, not a fund redirect, which is why
every Compound score already caps `timelockScore` for it. What is new is that ONE committee holds that seat on three
Comets, so one compromised or coerced quorum freezes Compound V3 on three chains at once. No scorer or note said so.

## What changed

- `crossExposureScore` of Compound V3 on Ethereum L1, Arbitrum and Base is now **80** (was 100), by the 2026-09-20
  convention (`METHODOLOGY.md`, "Convention (decided 2026-09-20)"): each scorer compares the owner set it reads itself
  with the dated snapshot `_KNOWN_COMPOUND_PAUSE_GUARDIAN_OWNERS_2026_09_20`, no second-chain RPC. Composites do not
  move (79, 80, 80). Base's scorer did not read the guardian at all before; it now does and notes it.
- The registry has the new groups, so the sweep reports the committee (9 signers on 3 chains) and a containment row.

## Negative results (registered and swept, no overlap found)

EigenLayer StrategyManager (two Safes, 1-of-2 and 9-of-13), Aave V3 Horizon (4-of-6 and 3-of-4), Rocket Pool's guardian
EOA, Aerodrome Slipstream's 3-of-7, Moonwell's EOA, Telos Consilium's 2-of-5. "No overlap found" is a dated result
against the 86 groups registered, not proof of none. Two overlaps the sweep already knew were re-confirmed: Fluid's Safe
`0x196Ed45e...` is the same address on Arbitrum and Plasma, and Pendle's `0x7877AdFa...` is the same address on Arbitrum,
Plasma and Robinhood.

## Negative results (checked live, 2026-09-20)

Every registered group of the seven registry ecosystems was resolved to its live signer set (86 groups), then compared with the
two ecosystems that have no registry.

- **Tempo, 14 targets:** the only overlap is Morpho Blue core (9 signers shared with the Robinhood, Ethereum L1 and Base
  Morpho Blue groups), already folded to 80. The other 13 Tempo targets share no signer with any registered group.
- **Hyperliquid, 15 targets:** no address named in any target's scorer output (bridge validators, HIP-3 deployers, staking
  managers, vault leaders) appears in any registered committee. This checks named addresses only; the HyperCore validator set
  is not an EVM signer list and is out of scope of this comparison.

A negative result is a result: it says the 80 fold applies to the Morpho and Compound committees and to nothing else in these two
ecosystems, as of this sweep.

## Later the same day

- **Precision (2026-09-21).** The nine owners are identical as addresses, and one of them is a nested Safe at the same address
  (`0x55bea483...`) on all three chains, but that Safe is 2-of-6 on Arbitrum and Base and 2-of-5 on Ethereum. The set of keys
  that can act is therefore not identical across the three chains
  ([`finding_2026-09-21-who-really-signs.md`](finding_2026-09-21-who-really-signs.md)).

- **A second shared root, the DAO.** Compound's Ethereum Governance Timelock (`0x6d903f60...C33925`, 2-day delay, GovernorBravo
  behind it) governs all three Comets: directly on L1 (`Comet.governor()`), and through the Arbitrum and Base bridge receivers
  (`govTimelock()` on each, re-read live by the scorers). It is now registered in the three Compound groups, so the sweep reports
  it next to the pause guardian committee. It changes no score: the three Comets already read 80 for the committee, and the flat
  80 is the same for a shared DAO root (see the Uniswap finding below).

- **WBTC's legacy multisig** (6-of-10, 7 bare EOAs and 3 contracts) was registered as a dated owner snapshot and compared with
  every registered committee on six ecosystems: no overlap.
- **Uniswap's L1 Timelock**, a contract root the sweep could not compare, turned out to root 11 targets on 5 ecosystems:
  [`data/finding_2026-09-20-uniswap-one-timelock-eleven-targets.md`](finding_2026-09-20-uniswap-one-timelock-eleven-targets.md).

## Not done here

The non-EVM Solana set is not in the registry (its signer format is a Squads/native multisig, not a Safe). Ethereum L1 targets
rooted in a token-vote or Aragon DAO with no signer identity (Maker's pause, Lido's DAO agent, Curve's ownership agent,
SparkLend) are not registered; each is either L1-only in this oracle or already grouped by its scorer. The Arbitrum, Base and
Ethereum L1 oracles carry the old Compound cross value until their next re-push.
