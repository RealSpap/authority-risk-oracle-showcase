# Aerodrome Voter's authority, traced -- 2026-09-18

Closes an open question `chains/base-ecosystem/scorers.py`'s
`score_aerodrome_poolfactory` and `data/scored_targets_2026-09-16.md`
(section 3) both explicitly flagged from the start: `Voter` at
`0x16613524e02ad97eDfeF371bC883F2F5d6C480A5` (confirmed live via
`PoolFactory.voter()`, matches the official `aerodrome-finance/contracts`
GitHub README's Voter row exactly) governs AERO emissions -- "arguably
the higher-value lever" than the already-scored pause/fee powers -- but
was never traced further.

## Answer

`Voter.governor()` is the EXACT SAME Gnosis Safe as `PoolFactory.pauser()`
and `PoolFactory.feeManager()` -- not a coincidentally shared signer, the
identical contract address, `0xE6A41fE61E7a1996B59d508661e3f524d6A32075`
(3-of-7). Confirmed live on two independent RPCs (`https://mainnet.base.org`
and `https://base-rpc.publicnode.com`, both agree byte-for-byte):

| Getter | Contract | Value |
|---|---|---|
| `Voter.governor()` | `0x1661...480A5` | `0xE6A4...2075` |
| `PoolFactory.pauser()` | `0x420D...E40Da` | `0xE6A4...2075` |
| `PoolFactory.feeManager()` | `0x420D...E40Da` | `0xE6A4...2075` |
| `Voter.emergencyCouncil()` | `0x1661...480A5` | `0x9924...c013D` (SEPARATE Safe, 3-of-5, zero owner overlap) |
| `Voter.epochGovernor()` | `0x1661...480A5` | `0xC715...eE497` (a thin wrapper gated by `msg.sender == governor()`, adds no independent authority) |

Because `governor` and `pauser`/`feeManager` are the identical key, this
is NOT a second, independently-weaker full-power path to take a minimum
over (METHODOLOGY.md 6.2's usual convention when a target has more than
one authority) -- the already-published composite (46/100: adminKey=65,
multisig=65, timelock=0) already reflects this key's real strength. What
was actually missing was the DISCLOSED SCOPE of what that one key can do.

## What `governor` can actually do (real source, not selector guessing)

Source: `aerodrome-finance/contracts`, `contracts/Voter.sol`, `main`
(commit `a4fe56813c9e64907038f447a7358f83ec32dc14` at read time) --
Aerodrome's own repo, not a Velodrome fallback (confirmed unnecessary
since `PoolFactory.voter()` matches this exact deployed address).

| Function | Guard | Class | Why |
|---|---|---|---|
| `setGovernor(addr)` | `governor` | **Full -- self-reassignment** | No timelock, no other governance check (only a trivial non-zero-address guard, `if (_governor == address(0)) revert ZeroAddress()`) |
| `whitelistToken(addr, bool)` | `governor` | **Full** | Gatekeeps which ERC20s may receive gauge emissions |
| `createGauge(factory, pool)` | public, but `governor` bypasses both safety checks | **Full** | A non-governor caller must pass a real `Pool` with both tokens already whitelisted; `governor` skips both checks -- can create an emission-eligible gauge for an arbitrary address, not necessarily even a real pool |
| `whitelistNFT`, `setEpochGovernor`, `setMaxVotingNum` | `governor` | Full, narrower blast radius | Config-only, no direct fund movement |
| `killGauge(addr)` / `reviveGauge(addr)` | `emergencyCouncil` | **Bounded** | Sets `isAlive=false` (reversible via revive); sweeps only that ONE gauge's own already-accrued, still-unclaimed emissions back to `minter` -- cannot touch other gauges, cannot whitelist/blacklist, cannot move already-claimed funds |
| `setEmergencyCouncil(addr)` | `emergencyCouncil` | Full, but scoped to its own bounded role | Self-reassignment of the bounded role only |

No fee-split function exists in `Voter.sol` at all -- fee splits live
entirely on `PoolFactory.feeManager()`, already scored. `governor`'s real
leverage is emissions-direction (the whitelist gate plus the
gauge-creation bypass) and self-reassignment, not fees.

**No timelock anywhere in this chain**: every governor/council-gated
function checks only `msg.sender == governor` / `== emergencyCouncil`,
immediate on execution. Both Safes have zero modules attached
(`getModulesPaginated` confirmed empty on both) -- no Zodiac Delay
Module, no TimelockController. Contrary to what a ve(3,3)-style protocol
might suggest, these admin roles are NOT routed through veAERO
token-holder voting; that governs gauge WEIGHT (how existing emissions
are split), a separate mechanism from `governor`'s own instant powers.

## emergencyCouncil, disclosed not scored

`0x99249b10593fCa1Ae9DAE6D4819F1A6dae5C013D`, a genuinely separate 3-of-5
Safe (owners: `0x586b...de14, 0xef0c...4766, 0x24a9...1d59, 0x8499...a40f,
0x8dae...cecbe` -- zero overlap with the governor/pauser/feeManager
Safe's 7 owners). Per METHODOLOGY.md 6.2, `killGauge`/`reviveGauge` are
restrict-only/bounded (can only pause a single already-live gauge,
reversibly, no whitelist/fund-movement power) -- disclosed in
`score_aerodrome_poolfactory`'s own `notes` every run, not folded into
the composite, the same treatment this project already gives Kamino's
emergency council on Solana.

## Cross-exposure checked, no match found

`emergencyCouncil`'s 5 owners checked against every other already-scored
Base target's own owner set (Morpho Blue's 5-of-9 owner Safe, Aave's
**5-of-9** `GOVERNANCE_GUARDIAN` Safe -- corrected 2026-09-18 by
adversarial review, which caught an earlier draft of this section
mis-stating it as 3-of-9; live-reread against `score_aave_v3_base`'s own
already-scored threshold, not restated from memory) -- zero overlap
either direction. Compound's `Comet.governor()` (a LocalTimelock, not a
Safe) and Uniswap's fee-adapter owner are both address-distinct from
both Voter roles too.

## Verification

- Every address re-read live on two independent RPCs
  (`https://mainnet.base.org`, `https://base-rpc.publicnode.com`), not
  assumed from a prior pass -- and `score_aerodrome_poolfactory` now
  asserts this identity every run (degrades to the unresolved-authority
  branch, doesn't silently keep scoring the old assumption, if the Safes
  were ever rotated to diverge).
- `emergencyCouncil` resolved as a genuine Gnosis Safe via
  `getOwners()`/`getThreshold()`, not assumed from its name.
- `python3 -m unittest discover -s scripts/lib/tests`: 187/187 pass
  (no new tests added this pass -- no new decode logic, only a live
  identity check and additional disclosure on an existing, already-tested
  scorer).
- `python3 scripts/validate_all_scorers.py --ecosystem base`: 5/5 targets
  pass, `OVERALL: PASS`. Aerodrome's composite unchanged at 46/100.

## Adversarial review, 2026-09-18

2-dimension review before commit (governor identity and scope -- the
headline claims; emergencyCouncil and cross-exposure), each finding
independently re-verified by a separate agent instructed to try to
refute it. 8 agents, 6 findings, 5 confirmed, 1 refuted. The three
headline claims (governor==pauser==feeManager identity; governor's
whitelistToken/createGauge-bypass/setGovernor powers; specifically that
a governor-created gauge can target a genuinely arbitrary, even
non-contract, address) all came back CONFIRMED with the reviewer tracing
even further than this document does (into `GaugeFactory.sol`,
`Gauge.sol`, `VotingRewardsFactory.sol`, `VotingReward.sol` to confirm
zero downstream calls ever touch the arbitrary address). Real fixes
applied, both above: Aave's `GOVERNANCE_GUARDIAN` Safe corrected from a
mis-stated 3-of-9 to the real, live 5-of-9; and `score_aerodrome_
poolfactory`'s emergencyCouncil-overlap note, which asserted "zero
overlap" as fixed prose without the code ever actually computing it, now
genuinely intersects both owner sets live every run. One proposed
"correction" to this document's `epochGovernor` characterization was
itself REFUTED after independent re-verification: the proposing agent
had found real source for `contracts/EpochGovernor.sol` (a genuine
veAERO-voting contract) but never confirmed that's what's actually
deployed at the live address -- bytecode/selector/Blockscout
cross-checks show the real deployed contract is `SimpleEpochGovernor`,
exactly the "thin wrapper gated by `msg.sender == governor()`" this
document already said. No change made there. No change to the composite
(46/100) from any of this.

## Reproduction

```
python3 -c "
import sys; sys.path.insert(0, 'scripts/lib'); sys.path.insert(0, 'chains/base-ecosystem')
from web3_utils import get_w3
from scorers import score_aerodrome_poolfactory
r = score_aerodrome_poolfactory(get_w3('https://mainnet.base.org'))
print(r['label'], r['compositeScore'])
for n in r['notes']: print(' -', n)
"
```
