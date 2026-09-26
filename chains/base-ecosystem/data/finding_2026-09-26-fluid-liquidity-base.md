# Fluid (Instadapp) Liquidity on Base: same Timelock, same Avocado proposer as Plasma and Arbitrum

2026-09-26. Closes the tracker board's open piste ("Fluid/Instadapp Liquidity `0x52Aa8994...360F4e497`,
[backlog note]"). The "[backlog note]"
concern is already answered -- `chains/plasma-ecosystem/scorers.py::score_fluid_liquidity_plasma()`
decoded this exact structure in depth on 2026-09-20 (and cross-checked it against Arbitrum in the
same pass). This finding independently re-verifies, LIVE on Base specifically, that the identical
structure applies there too -- never assumed to carry over from another chain by protocol-name alone,
matching that scorer's own explicit discipline ("not assumed to share an address by protocol-name
alone").

## Every load-bearing fact independently re-confirmed live on Base

- **Liquidity contract**: `0x52Aa899454998Be5b000Ad077a46Bbe360F4e497` -- `eth_getCode` returns
  **4,462 bytes**, byte-for-byte the same size Plasma's scorer documents for its own instance.
  CREATE2-deployed with identical constructor args/salt across mainnet/arbitrum/base/polygon/plasma/
  bnb per Instadapp's own `deployments.md` -- confirmed here as a genuine separate Base deployment,
  not a docs artifact.
- **`getAdmin()`** (selector `0x6e9960c3`) = `0x4d6CE4F4498d59Eed397bCbC687805a07f9b2346` -- the
  EXACT SAME address as Plasma's admin (case-insensitive match, independently re-read, not copied).
- **`getMinDelay()`** on that address = **86400** (24h), matching Plasma exactly.
- **`hasRole(PROPOSER_ROLE, 0x4F6F977aCDD1177DCD81aB83074855EcB9C2D49e)`** = **True** -- the SAME
  Avocado multisig (6-of-12, per Plasma's own already-completed decode via `requiredSigners()`/
  `signers()`) holds the proposer seat on Base too.
- **`hasRole(EXECUTOR_ROLE, 0x196Ed45eC4ACA949E7AA921ceC81e219e682775e)`** = **True** -- the SAME
  Safe (3-of-5, per Plasma's decode) holds the executor seat on Base too.

## What this means

The exact same three-tier authority (TimelockController @ `0x4d6CE4F4...`, Avocado 6-of-12 proposer,
Safe 3-of-5 executor, 24h delay) governs Fluid Liquidity on **Base, Plasma, and Arbitrum** (three of
this oracle's ten tracked ecosystems) simultaneously -- a real, substantial cross-ecosystem
concentration, not independently verified for signer-set identity across all three in one place
before (Plasma's own scorer already folds Arbitrum in via `crossExposureScore`; this pass adds Base
as a third confirmed match using the identical live-read method, not assumed from the shared address
alone).

## What this is and isn't

Pure investigation and live cross-check, no scorer built this pass. `chains/base-ecosystem/scorers.py`
has zero prior Fluid references -- adding it as a scored Base target is straightforward (the exact
same ~200-line pattern already built, tested, and proven in
`chains/plasma-ecosystem/scorers.py::score_fluid_liquidity_plasma()` would need only its constant
addresses and RPC endpoint swapped for Base's own) but was deliberately NOT duplicated wholesale in
this pass -- writing another near-identical 200-line scorer under time pressure, without its own
dedicated test suite, is exactly the kind of shortcut this pass's own ponytail-audit work
(consolidating duplicated test infrastructure) argues against introducing on the scorer side. Ready
for a focused follow-up pass: copy the Plasma function's structure, retarget the RPC to
`https://mainnet.base.org`, re-run its own test suite's assertions against the Base-specific mocks,
and register it in `chains/base-ecosystem/scorers.py`'s own `SIMPLE_SCORERS` -- Spap's go still
needed before wiring in a new scored target, per this project's standing rule.

## Verification

All reads live against `https://mainnet.base.org`: `eth_getCode`, `getAdmin()`, `getMinDelay()`,
`hasRole()` for both PROPOSER_ROLE and EXECUTOR_ROLE (role hashes independently computed via
`Web3.keccak`, not copied from Plasma's file). No key read, nothing sent.
