# Steakhouse Safe's true reach folded into the controller-concentration report

2026-09-26. Closes the gap `data/finding_2026-09-25-vault-v2-inventory.md` explicitly flagged as
"not yet folded into the controller-concentration tool itself": the Steakhouse Safe
(`0x0A0e559b...`) governs $376.2M across 5 tracked Morpho V1 vaults, but ALSO resolves (via the
VaultV2Supervisor one-hop indirection `check_vault_v2_inventory.py` already chases) as the owner of
several disclosed-only Vault V2 targets -- a reach invisible in a report scoped only to V1.

## Built

`scripts/lib/controller_concentration.py::fold_in_vault_v2_reach()` (4 new unit tests) annotates a
V1 registry controller with its extra V2 TVL/vault count, purely informational -- never merged into
`vault_count`/`tvl`/`ecosystems`, which stay scoped to the oracle's actually tracked/scored V1
vaults (Vault V2 remains disclosed-only, no score, per `data/finding_2026-09-25-vault-v2-scoring-scope.md`,
an open methodology decision that stays Spap's). `scripts/check_controller_concentration.py` wires
this in: fetches $20M+ Vault V2 targets on tracked ecosystems, matches each one's owner (following
the same one-hop chase for a non-Safe intermediate) against the existing V1 registry, and prints the
match as a clearly separate `<-- PLUS $X disclosed-only Vault V2 reach` annotation.

**Live result**: the Steakhouse Safe's total reach is now visible in one place -- $376.2M (V1, 5
vaults) + $482.7M (V2, 7 vaults) = **$858.9M across both layers**, up from the $818.9M figure in the
09/25 finding (organic TVL growth in the days between, not a discrepancy -- re-verified against the
same live sources).

## A real bug found and fixed in already-shipped code, not just in what was built today

`check_vault_v2_inventory.py::fetch_vaults()` (shipped 2026-09-25) reliably hit
`IncompleteRead(0 bytes read, ...)` from `urllib.request.urlopen` on this exact query, reproduced 3
times in a row in this run environment -- the identical query via raw `curl` succeeded instantly
every time. Same class of environment quirk already found and fixed today for Blockscout in
`check_issuer_power.py` (there: 403 from a missing User-Agent; here: a urllib/http.client chunked-
transfer read curl doesn't hit) -- same fix, shell out to curl with a browser User-Agent. This means
`check_vault_v2_inventory.py` itself may have been silently failing in some environments since
09/25; fixed at the root (the shared `fetch_vaults()`), not worked around in the new caller.

## What this is and isn't

Disclosed only, same precedent as everything else this week: no score change, no `AuthorityScore`
field. The Vault V2 scoring-scope question remains explicitly open for Spap -- this makes the
existing disclosure more honest about a controller's TRUE cross-layer reach, it doesn't answer
whether or how V2 should ever be scored.

## Verification

`python3 scripts/check_controller_concentration.py` -- read-only, live RPC + Morpho's public API
(via `curl`, fixed this pass). 4 new unit tests for `fold_in_vault_v2_reach()`
(`scripts/lib/tests/test_controller_concentration.py`, 19 total in that file). Full suite (6
directories) green.
