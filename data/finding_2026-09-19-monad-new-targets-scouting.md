# Finding (2026-09-19, second pass): 2 new Monad mainnet targets added (Aave V3, Euler V2), 1 found and honestly discarded (Pendle V2)

Task: find 2-3 legitimate new Monad MAINNET targets with real, Monad-specific
TVL (not a protocol's multi-chain total), verify authority structure on 2+
independent sources per candidate, discard anything that turns out to be a
duplicate of already-tracked authority or has too-low Monad-specific TVL,
and push to the deployed Monad testnet oracle if the key balance allows.

## Discovery: DefiLlama scan, ranked by Monad-specific TVL

`GET https://api.llama.fi/protocols`, filtered for every protocol with
`"Monad"` literally in its own `chains[]` list (135 matches as of this
pass), ranked by `chainTvls.Monad` -- not each protocol's multi-chain
total. This distinction mattered: K3 Capital shows $531.9M total TVL but
only $392.2M is Monad-specific (still large, but a naive total-TVL ranking
would have overstated it); several other "Risk Curator" category entries
(Hyperithm $195.0M, Steakhouse Financial $48.0M Monad-specific out of
$3.1B total) show the same pattern and were judged too operationally
complex (aggregated curator businesses spanning many vaults/protocols, not
a single ownable authority root) to verify cleanly in this pass's time
budget -- not scored, not claimed as either included or excluded with
confidence.

Top candidates NOT already tracked by this project's existing 7 Monad
scorers (echo_ebtc, uniswap_v4, native_bridge, kuru, morpho_vault, curve,
curvance):

| Protocol | Monad-specific TVL | Outcome |
|---|---|---|
| Aave V3 | $319.4M | **Added** (`score_aave_v3_monad`) |
| Euler V2 | $265.0M | **Added** (`score_euler_v2_monad`) |
| Pendle V2 | $206.9M | **Found, verified, discarded** -- duplicate authority (see below) |

(K3 Capital $392.2M and Hyperithm $195.0M ranked higher by raw TVL than
Pendle but were skipped for the complexity reason above, not silently
dropped -- flagged here for a future pass rather than force-scored this
one.)

## Aave V3 -- added, real cross-chain guardian-committee finding

Source 1: official `bgd-labs/aave-address-book` GitHub repo,
`src/AaveV3Monad.sol`. Source 2: MonadScan's own verified contract source
for both `Executor` and `PayloadsController` (matching BGD Labs'
`aave-delivery-infrastructure` repo line for line). Every on-chain read
cross-checked on a second independent public RPC
(`https://monad.drpc.org`, byte-identical to `https://rpc.monad.xyz` on
every field).

Authority chain: `PoolAddressesProvider.owner()` -> `Executor` ->
`PayloadsController.owner()` closes back to that same `Executor` (the
standard, deliberately self-referential Aave Governance V3 cross-chain
design -- confirmed live, not assumed). `getExecutorSettingsByAccessControl(1)`
confirms a real 86,400s (1-day) delay; `(2)` (the more sensitive
"long executor" tier) returns the zero address -- genuinely not configured
on Monad yet, disclosed as a real gap.

**Real finding**: `PayloadsController.guardian()` resolves to a real
5-of-9 Gnosis Safe whose 9 owners are BYTE-IDENTICAL to
`chains/plasma-ecosystem/scorers.py`'s own
`_KNOWN_AAVE_GUARDIAN_OWNERS_2026_09_17` -- the same emergency-cancel
committee already found sharing Arbitrum's, Base's, AND Plasma's own Aave
V3 deployments. Monad is a FOURTH chain this exact 9-signer committee now
reaches. `crossExposureScore` scored 80/100 accordingly (matching this
project's existing convention for a confirmed cross-chain signer-overlap
finding), not left at an unexamined 100.

## Euler V2 -- added, real cross-chain DAO-signer finding (surfaced only by running the actual overlap check)

Source 1: official `euler-xyz/euler-interfaces` GitHub repo,
`addresses/143/{CoreAddresses,GovernorAddresses,MultisigAddresses}.json`.
Source 2: live on-chain reads, cross-checked on `https://monad.drpc.org`.

Authority chain: `eVaultFactory.upgradeAdmin()` -> `eVaultFactoryGovernor`
(an AccessControl contract, not Ownable) -> DEFAULT_ADMIN_ROLE held
EXCLUSIVELY by `eVaultFactoryTimelockController` (confirmed real, live
`getMinDelay()` = 345,600s / 4 days -- the longer of Euler's own two
configured tiers on Monad; a separate, faster 2-day tier governs
risk-parameter changes on already-deployed vaults, disclosed but not
scored here since factory-level compromise is more catastrophic). The
Euler DAO Safe (4-of-8) holds `PROPOSER_ROLE`; `EXECUTOR_ROLE` is granted
to `address(0)` (open/permissionless execution once queued). A separate
Security Council Safe (2-of-3, matching `MultisigAddresses.json`'s own
`labs`/`securityPartnerA`/`securityPartnerB` signers) exists but was not
found holding any admin/proposer/executor/guardian-style role on either
governor this pass -- disclosed as an open point.

**Real finding, only surfaced by actually running
`scripts/check_cross_ecosystem_overlap.py`, not assumed**: the DAO Safe's
own ADDRESS is genuinely distinct from `PLASMA_GROUPS["euler"]`'s DAO Safe
address (Euler CREATE2-redeploys a different Safe per chain, unlike
Pendle) -- which is why this candidate was judged "not a duplicate target"
before wiring it into `MONAD_GROUPS`. But once wired in and the overlap
script re-run live against both chains' RPCs, all 8 individual SIGNERS
turned out to be byte-identical between Monad's and Plasma's Euler DAO
Safes -- the same 8 humans/keys behind two differently-addressed Safe
contracts. This is a genuine, separate signal from "is this the same
target" (it isn't) and was folded into `crossExposureScore` (scored
80/100, was initially written as 100/100 before this check was run --
corrected in the same pass, not left wrong).

## Pendle V2 -- found, verified, honestly discarded (not force-added)

Source 1: official `pendle-finance/pendle-core-v2-public` GitHub repo,
`deployments/143-core.json`. Source 2: live on-chain reads.

`router` (`0x888888888889758F76e7103c6CbF23ABbF58F946`) and `proxyAdmin`
both resolve to `owner() = 0x7877AdFaDEd756f3248a0EBfe8Ac2E2eF87b75Ac`, a
real 3-of-5 Gnosis Safe; `devProxyAdmin.owner() =
0xE6F0489ED91dc27f40f9dbe8f81fccbFC16b9cb1`, a real 3-of-6 Gnosis Safe. No
timelock found protecting either.

This is where the candidate was discarded, not scored: BOTH of these exact
Safe addresses -- and the exact Router contract address -- are ALREADY
tracked for Pendle on Plasma, in
`chains/plasma-ecosystem/scorers.py::score_pendle_plasma()` and
`scripts/lib/cross_ecosystem_overlap.py`'s own `PLASMA_GROUPS["pendle"]`.
This is not "the same team happens to run both" -- it is the literal same
CREATE2-deployed Router bytecode at the literal same address, administered
by the literal same two Safe contracts (also at the same addresses,
meaning Pendle's own Safe deployment is ALSO CREATE2/deterministic across
chains, unlike Aave's or Euler's per-chain-unique Safe addresses).

**Why discarded rather than scored-with-disclosure** (the path
`score_curve_monad` took for an analogous Robinhood-Chain/Monad duplicate,
kept in-file because it revealed a NEW single-EOA risk pattern not
previously stated anywhere): scoring Pendle-on-Monad here would restate
information `score_pendle_plasma()` already fully states, with zero new
authority-structure content -- not a genuinely new finding, just a second
copy of the same one. Given this task's explicit instruction to discard
duplicates rather than pad the target count, and given 2 unambiguously new
targets (Aave, Euler) were already found, this candidate was left out.
Documented here in full so a future pass doesn't have to re-derive this
same research to make the same call.

## Push status: NOT pushed to the deployed Monad testnet oracle

Checked the shared EVM testnet key's balance
(`0x20630C6Ab4BA48a80edA46F77b9b6e987A8f32f5`) on Monad testnet before
attempting anything, per this task's own explicit instruction:
**0.00204 MON**. Real `eth_estimateGas` for `updateScores()` with all 9
targets against the live deployed oracle: 445,108 gas; at the current
~102 gwei gas price with this project's usual 1.25x buffer, that's
~0.0568 MON needed -- a ~0.0547 MON shortfall. The push was not attempted.
See `chains/monad/deploy/README.md`'s own "2026-09-19 (second pass)"
section for the full numbers and next-step instructions once the key is
re-funded.

## Verification method (repeatable)

```
curl -s https://api.llama.fi/protocols | python3 -c "
import json, sys
d = json.load(sys.stdin)
monad = [p for p in d if 'Monad' in (p.get('chains') or [])]
monad.sort(key=lambda p: (p.get('chainTvls') or {}).get('Monad', 0), reverse=True)
for p in monad[:20]:
    print(p['name'], (p.get('chainTvls') or {}).get('Monad', 0))
"
python3 chains/monad/scripts/dry_run.py           # re-derive all 9 scores live
python3 scripts/check_cross_ecosystem_overlap.py  # re-derive the cross-chain signer overlaps live
```
