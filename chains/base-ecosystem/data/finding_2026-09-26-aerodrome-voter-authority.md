# Aerodrome (Base): Voter/Minter authority traced -- 3 real Safes, no bare key found

2026-09-26. Closes the tracker board's own open piste ("Aerodrome voter() 0x1661...480A5, racine
[backlog note]") -- the root was found live before but never
followed further. Pure investigation, no scorer built (adding Aerodrome would be a new target on an
already-tracked ecosystem, Spap's decision, not built unilaterally). `chains/base-ecosystem/
scorers.py` has zero prior references to Aerodrome -- genuinely untouched ground before this pass.

## The three authorities, traced to real Safes, live-verified

`Voter` (`0x16613524e02ad97eDfeF371bC883F2F5d6C480A5`, verified, no `owner()` -- Aerodrome's ve(3,3)
model splits authority across named roles instead of a single admin):

- **`governor()`** = `0xE6A41fE61E7a1996B59d508661e3f524d6A32075`, a **3-of-7 Gnosis Safe** --
  standard proposal/parameter governance.
- **`emergencyCouncil()`** = `0x99249b10593fCa1Ae9DAE6D4819F1A6dae5C013D`, a **3-of-5 Gnosis Safe** --
  a SEPARATE Safe from governor, smaller and with a lower threshold, presumably for fast defensive
  action (pool killswitches etc., not read further this pass).
- **`epochGovernor()`** = `0xC7150B9909DFfCB5e12E4Be6999D6f4b827eE497`, a verified `SimpleEpochGovernor`
  contract, NOT a Safe itself. Read its source before assuming it was a separate, weaker authority:
  `setResult()` -- the function that decides whether a tail-emission-rate nudge proposal passed --
  requires `msg.sender == voter.governor()`. **This is not a fourth authority; it's the SAME 3-of-7
  governor Safe acting through a purpose-built wrapper**, not a separate or weaker path.

`Minter` (`0xeB018363F0a9Af8f91F06FEe6613a751b2A33FE5`, verified, the actual root of AERO emissions --
`nudge()`/`updatePeriod()` are the functions that mint new AERO each epoch):

- **`nudge()`** (adjusts `tailEmissionRate`, the terminal per-epoch emission rate once the initial
  decay schedule ends) is gated to `msg.sender == voter.epochGovernor()` -- i.e. the governor Safe
  above, ONE nudge per epoch (`AlreadyNudged` guard), bounded: current `tailEmissionRate` = 21 basis
  points (0.21%), `MAXIMUM_TAIL_RATE`/`MINIMUM_TAIL_RATE` cap how far a single nudge can move it (at
  most ±1bp per epoch, per the function's own NatSpec).
- **`team`** = `0xBDE0c70BdC242577c52dFAD53389F82fd149EA5a`, a **4-of-7 Gnosis Safe** (a THIRD,
  distinct Safe from governor and emergencyCouncil) -- controls only its own emission cut via
  `setTeamRate()`, live-read `teamRate` = 228 basis points (2.28%), hard-capped at
  `MAXIMUM_TEAM_RATE` = 500 (5.00%) out of `MAX_BPS` = 10000. `setTeam()`/`acceptTeam()` is a 2-step
  ownership transfer for this Safe's own seat (`NotTeam()`/`NotPendingTeam()` reverts confirmed in
  source), not a separate escalation path.

## What this is and isn't

**No bare EOA and no unbounded admin key found anywhere in this trace** -- every privileged party is
either a real, distinct multisig (3 different Safes: governor 3-of-7, emergencyCouncil 3-of-5, team
4-of-7 -- none of the three share the same address, not independently checked for signer OVERLAP
this pass) or a hard-capped parameter (team rate <=5%, tail emission nudge <=1bp/epoch). A cleaner
structure than several targets already scored in this repo. Disclosed as a genuine result, not
forced into a "gap found" narrative it doesn't support.

**Not built, not scored, not added as a target** -- this is investigation only, per this project's
standing rule that a new target on an already-tracked ecosystem is Spap's call, never unilateral.
If Spap wants Aerodrome added: the read pattern above (governor/emergencyCouncil/team, all direct
zero-arg Safe-returning getters, no proxy hops needed) is straightforward to wire into
`chains/base-ecosystem/scorers.py` using the exact same `read_address_getter`/
`safe_owners_and_threshold` primitives every other Base scorer already uses -- no new pattern
required. Signer-overlap check against the other already-tracked Base Safes (and the wider
cross-ecosystem registry) is the natural next step before scoring, not done this pass.

## Verification

All addresses read live against `https://mainnet.base.org` and cross-referenced against Blockscout's
verified ABI/source for `Voter`, `Minter`, and `SimpleEpochGovernor`. `setResult()`'s
governor-only gate and `nudge()`'s epoch-governor-only gate read directly from each contract's own
verified source, not assumed from function names. No key read, nothing sent.
