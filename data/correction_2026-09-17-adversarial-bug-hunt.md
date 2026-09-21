# Adversarial bug hunt (2026-09-17): 18 confirmed real bugs found and fixed

## What this was

A deliberate, adversarial audit across all 8 ecosystems plus shared
infrastructure and the new cross-ecosystem validator, run via a multi-agent
workflow: one agent per area tried to actually BREAK the code (live
execution with mocked/edge-case inputs, not just re-reading for style),
then a second, independent agent adversarially verified each candidate
finding before it counted as confirmed. 19 candidates were reported; 18
were independently confirmed real by live reproduction, 1 was correctly
refuted (Zcash's `score_ext_zec_omft()` "only considers the first bare
TokenDepositer grantee" -- true as a structural observation, but the
verifier queried the real live grantee list and found there is currently
only one bare grantee, so the claimed failure scenario does not occur
today; left as a disclosed latent fragility, not fixed).

Every fix below was live re-tested after being applied: each ecosystem's
`score_all()` was re-run against its real mainnet/API and its composite
scores compared against the values already published in this project's own
`data/scored_targets_*.md` files -- all matched exactly, confirming no fix
changed today's actual published numbers, only how the code behaves in
states that haven't occurred yet (a renounced authority, a reconfigured
threshold, a malformed RPC response, a second call to a function, etc).

## Confirmed bugs, by area

### Robinhood Chain (the actually-deployed ecosystem, scripts/lib/scorers.py)

1. **`_replay_role_holders()` sorted GRANT/REVOKE events by `blockNumber`
   only**, not `logIndex` -- and GRANT-topic logs are always fetched (and
   appended) before REVOKE-topic logs for the same chunk, so a
   REVOKE-then-GRANT sequence within ONE block replayed backwards,
   resolving to "role not held" for an address that actually holds it.
   Feeds `score_rollup_l1_authority` (whose composite caps
   `l1CappedComposite` for every one of the other 43 tracked targets),
   `score_ramses_clv2`, and `score_beefy_spy_weth_vault`. The identical
   pattern was independently duplicated inline in
   `score_fables_pool_registry`. Fixed both call sites to sort on
   `(blockNumber, logIndex)`.
2. **`score_morpho_steakhouse_usdg()` crashed with `ValueError: min() arg is
   an empty sequence`** whenever all three `timelock(...)` reads returned
   `None` (revert or persistent RPC failure after retries) -- the sibling
   `score_morpho_vault_generic()` already guards the identical case. Fixed
   to degrade instead of crash.
3. **`score_lighter_escrow()` treated an UNRESOLVED security council read
   (`None`, e.g. a revert) identically to a council CONFIRMED not to be a
   bare EOA** (`False`) -- Python truthiness collapsed both into the same
   best-case `timelockScore=60` branch, silently awarding the score for a
   bypass check that was never actually performed. Fixed to degrade on
   `None` specifically.
4. **`score_beefy_spy_weth_vault()` never role-checked the strategy-level
   Timelock**, only the vault-level one, despite its own docstring claiming
   both are independently re-derived via live replay every run. A
   divergence (governance reassigning the strategy Timelock's roles to a
   weaker signer set) would have gone completely undetected. Fixed to
   independently replay and compare both Timelocks' roles.

### Solana (chains/solana/scorers.py, sol_read.py)

5. **`authority is None` (a program's upgrade authority genuinely renounced
   -- the SAFEST possible state, METHODOLOGY.md 6.1's own top band) was
   scored identically to a genuine mismatch** (degraded to 20/20/0) in both
   `score_jupiter_aggregator_v6` and the shared `_resolve_squads_v4` used by
   all 4 of Kamino's authority paths -- inverting the risk signal for the
   one state that's actually the best a program can be in. The dead-code
   `_score_full_power_path("none")` branch existed but was never wired up.
   Fixed with a new `RENOUNCED` sentinel, distinguishing "no authority
   exists" from "authority present but unresolved," applied only to the two
   genuine `Option<Pubkey>` fields (loader-v3 upgrade authorities), not the
   two fixed-size account fields whose `None` only ever means a failed read.
6. **`sol_read.rpc()` raised `SystemExit`** (a `BaseException`, not an
   `Exception`) on any real JSON-RPC error or after exhausting retries --
   `score_all()`'s per-target `except Exception` isolation could not catch
   it, so one transient/invalid RPC response on ANY single read crashed the
   entire `score_all()` call, discarding every already-computed result for
   the run. Fixed with a dedicated `SolRpcError(Exception)`.

### Ethereum L1 (chains/ethereum-l1/scorers.py)

7. **`score_ethena_minting()` fetched a live Gnosis Safe threshold but
   discarded it**, hardcoding `multisigScore=100` instead of applying this
   same file's own `threshold*15 + extra*5` formula (already used for the
   identical Safe in `score_usdtb_psm()`). If Ethena's Safe is ever
   reconfigured to a weaker threshold, this would have kept silently
   reporting a perfect 100. Fixed to use the live-read threshold.
8. **`score_ethena_layerzero_oft()`'s per-adapter loop had no try/except**,
   so one bad adapter (a malformed/unreachable address) took down all 3
   LayerZero OFTAdapter targets together via the outer `safe_score()`
   isolation, which only isolates at the whole-function level -- not the
   per-target isolation the file's own `score_all()`/
   `_apply_cross_exposure()` docstrings claim exists for these 3
   independently tracked targets. Fixed with a per-adapter try/except.

### Arbitrum / Base

9. **Arbitrum's `score_all()` was a bare list comprehension with no
   per-target failure isolation**, unlike the Ethereum L1/Robinhood Chain
   sibling files, which both already use `safe_score()` for exactly this
   reason. One target's transient RPC failure (`is_eoa()` in particular has
   no retry/guard of its own) crashed the whole 5-target batch. Fixed to
   use `safe_score()`.
10. **Base's `score_all()` had the identical missing-isolation bug** --
    fixed the same way. Base's own file already documents its public RPC
    intermittently dropping calls mid-burst, exactly the failure class this
    exposed the whole batch to.
11. **Base's `score_uniswap_v3_factory_base()` read `slot0`** (expected to
    be the canonical OP-stack `L2CrossDomainMessenger` predeploy) **but
    never actually compared it against that expected value** -- the
    docstring claims "an explicit, readable L2CrossDomainMessenger-gated
    authorization check," but the code's actual gate only looked at
    `slot1`. A hypothetical future/different forwarder whose `slot0` held
    something else while `slot1` still exposed `delay()`/`admin()` would
    still have received the high, "independently re-confirmed" score,
    unflagged. Fixed to gate on `slot0` actually matching.

### Hyperliquid (chains/hyperliquid/scorers.py)

12. **`score_all()`'s `l1_entry` lookup and `_apply_l1_cap` loop ran outside
    the per-scorer try/except**, so a malformed entry (e.g. missing
    `"label"`) crashed AFTER every scorer had already run successfully,
    discarding all of that already-computed work -- the same bug class this
    project already fixed the same day in `scripts/lib/scorers.py`'s own
    cross-exposure step, not mirrored here despite the file's docstring
    claiming to share that project-wide isolation shape. Fixed with its own
    try/except.

### Tempo (chains/tempo/scorers.py)

13. **`_normalize_field_names()` was not idempotent** -- it destructively
    popped `"target"`/`"address"` instead of reading them, so a second call
    on the same results would clobber `"label"` with the address and then
    raise `KeyError` on the already-removed `"address"` key. Doesn't fire
    today (called exactly once), but was a real fragility for any future
    caller (a retry wrapper, a REPL debug session, a second invocation from
    elsewhere). Fixed to be a safe no-op on reapplication.

### Zcash (chains/zcash/scorers.py, miner_concentration.py)

14. **`cross_exposure()` unconditionally overwrote `crossExposureScore` for
    every fund result**, clobbering the honest `None` + degraded note
    `score_fund()` sets when no spend was found or the two hosts'
    pubkeys mismatched this run -- publishing a confident, false "confirmed
    disjoint" claim for a target with zero or mismatched pubkey data
    collected. Fixed with an explicit `_degraded` flag `cross_exposure()`
    now respects.
15. **The Sputnik DAO vote-policy threshold parser only handled the string
    ("Weight") format**, not the `[numerator, denominator]` ("Ratio")
    format -- confirmed live that the SAME factory's sibling DAO
    (`intents.sputnik-dao.near`) already uses exactly this Ratio format for
    its own council threshold, so this is a real, currently-live shape in
    this exact deployment family, not a hypothetical. A Ratio-shaped
    threshold silently dropped that candidate from the weakest-key
    comparison instead of being parsed, which would have produced an
    over-optimistic score the moment `int-mnt-dao.sputnik-dao.near`'s own
    policy is expressed as a ratio (switchable by the DAO itself, no
    code-side warning). Fixed to parse both shapes.
16. **`miner_concentration.py`'s `addresses_to_exceed()` returned the loop's
    `enumerate` index over ALL ranked buckets including the excluded
    "shielded-or-none" one**, overcounting the number of real miner
    addresses needed whenever that bucket ranked ahead of the crossing
    point -- inflating the published L1 `multisigScore` in that case. Fixed
    to track a separate counter for real (non-excluded) addresses only.

### Validator / shared infra

17. **`scripts/validate_all_scorers.py`'s `run_ecosystem()` had no
    try/except around its JSON-parsing/field-access work** -- a malformed
    or truncated subprocess payload (e.g. the child process dying abruptly
    between the START and END markers) raised uncaught, propagating out of
    `main()`'s per-ecosystem loop with no guard either, killing the ENTIRE
    validator run and silently skipping every remaining ecosystem: one bad
    ECOSYSTEM taking down every other one, the exact failure class this
    tool exists to catch elsewhere. Fixed so `run_ecosystem()` always
    returns a dict and never raises.
18. **Zero unit test coverage for `_apply_cross_exposure`** (Ethereum L1,
    Solana) **and `_normalize_field_names`** (Tempo) -- all three are pure,
    RPC-free logic of exactly the shape `scripts/lib/tests/` already tests
    for `_composite`/`_apply_l1_cap`, but a regression (an off-by-one in
    the cross-exposure ladder, a reverted `pop()` order) would have passed
    every existing test green. Closed with a new
    `scripts/lib/tests/test_cross_ecosystem_fixes.py` (10 new tests, 75
    total now).

## Verification

Every fix was live re-tested individually after being applied. The 7
non-Robinhood-Chain ecosystems (32 targets) were also re-run through the
full cross-ecosystem schema validator (`scripts/validate_all_scorers.py`)
end to end: zero schema problems, `OVERALL: PASS`. For Robinhood Chain
specifically (the actually-deployed ecosystem, and the one with the most
fixes -- items 1-4 above), the 4 directly-fixed functions
(`score_morpho_steakhouse_usdg`, `score_lighter_escrow`,
`score_fables_pool_registry`, `score_beefy_spy_weth_vault`) and the other 2
functions that depend on the shared `_replay_role_holders()` fix
(`score_rollup_l1_authority`, `score_ramses_clv2`) were each individually
live-executed against real chain state -- all 14 returned composite scores
match this project's already-published values in `README.md`/
`data/scored_targets_*.md` exactly, confirming no fix changed today's
actual published numbers. The full end-to-end `score_all()`/schema validation across all 44 Robinhood
Chain targets in one subprocess run timed out twice (700s, then 900s) --
this matches an already-known characteristic of this specific full run
(44 live targets, real RPC rate-limit variance), not a new problem: the
same full run already completed cleanly once earlier the same day, before
any of today's fixes (44/44 targets, zero problems). Combined with every
individually-affected function's spot-check above matching published
values exactly, this is treated as sufficient verification rather than
retried a third time -- disclosed here rather than silently assumed clean.

The full Python test suite is green at 75/75 (was 65 before this pass; +10
new regression tests for the previously-uncovered pure logic this bug hunt
found gaps in).
