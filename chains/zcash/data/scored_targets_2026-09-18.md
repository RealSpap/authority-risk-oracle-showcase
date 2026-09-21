# Zcash -- scored targets, 2026-09-18

Phase `scouting` -> `scoring_build` continued: `data/scouting_candidates_2026-09-18.md`
found Maya Protocol's 2 live Asgard TSS vaults as a new target but deliberately left
them unscored (no target type fit them yet). This pass closes that gap: a new target
type, `XVAULT` (METHODOLOGY.md 3.6/4.7), and `scorers.py`'s `score_maya_asgard_vault()`.
The two pre-existing `FUND` targets and `L1` were also re-run live today (not just
carried over from 2026-09-17) to confirm nothing drifted or broke.

## Summary table (live run, 2026-09-18)

| Target | Key | adminKey | multisig | timelock | oracleAuthority | crossExposure | composite | l1CappedComposite |
|---|---|---|---|---|---|---|---|---|
| Zcash L1 (consensus-rule-change authority) | `0xB8e62E6AeB4C400b6F3e66cAb69ACe55439035c3` | 20 | 50 | 35 | 100 | 100 | **34** | n/a (baseline) |
| ZIP 271 one-time lockbox disbursement | `t3ev37Q2uL1sfTsiJQJiWJoFzQpDhmnUwYo` | 50 | 39 | 0 | 100 | 100 | **32** | **32** |
| ZCG funding stream (FS_FPF_ZCG_H3) | `t3cFfPt1Bcvgez9ZbMBFWeZsskxTkPzGCow` | 50 | 39 | 0 | 100 | 100 | **32** | **32** |
| `zec.omft.near` (NEAR PoA bridge, `EXT`) | `zec.omft.near` | 5 | 18 | 0 | 100 | 100 | **7** | n/a (off-Zcash) |
| **Maya Protocol Asgard vault A** (`XVAULT`, new) | `t1RBiXrLRdrHgsuSGQEusG2wCzPFczEVMfT` | 65 | 100 | 0 | 100 | 100 | **56** | n/a (off-Zcash authority, see METHODOLOGY.md 4.7) |
| **Maya Protocol Asgard vault B** (`XVAULT`, new) | `t1VtnnhTYhmADh7L2uKU3Sev7GscBHT6HfE` | 65 | 100 | 0 | 100 | 100 | **56** | n/a |

The first four rows are unchanged from `data/scored_targets_2026-09-17.md` -- re-run
live today, not assumed stable. `L1`'s concentration window is tip-relative
(3,485,905-3,487,904 today vs 3,483,700-3,485,699 on 2026-09-17), so `k50=3`/`k25=1`
matching again is a fresh confirmation, not a cached value.

## Maya Protocol Asgard vaults -- new `XVAULT` target, both scored today

**What they are.** Native ZEC.ZEC held in ordinary `t1` (P2PKH) Zcash Mainnet
addresses, custodied entirely by Maya Protocol's own external TSS validator network
-- no Zcash script or key governs them. See METHODOLOGY.md 3.6 for the full live
derivation; summary:

| Fact | Vault A | Vault B |
|---|---|---|
| Address | `t1RBiXrLRdrHgsuSGQEusG2wCzPFczEVMfT` | `t1VtnnhTYhmADh7L2uKU3Sev7GscBHT6HfE` |
| Live on-chain balance (both lightwalletd operators agree) | 220,970,943,152 zat | 126,951,364,578 zat |
| Mayanode internal ledger | 220,970,943,152 zat (exact match) | 129,157,478,056 zat (**+2,206,113,478 zat vs live, not fully reconciled -- see below**) |
| TSS membership (`n`) | 20 | 20 |
| Required co-signers (`k = ceil(2n/3)`) | **14** | **14** |
| Shared TSS members with the other vault | 0 (fully disjoint) | 0 (fully disjoint) |
| ZEC chain trading status | halted (`/mayachain/inbound_addresses`) | halted |

**TSS threshold, from a primary source.** `k = ceil(2n/3) = 14` is not assumed from
the generic "THORChain uses 2/3" convention -- it is Mayanode's own bifrost go-tss
`conversion.GetThreshold()` formula (`gitlab.com/mayachain/mayanode`, commit
`ad1072c33ca2091fe12917de2321578474e3e3eb`, 2026-09-17), the exact `threshold` value
every real keygen/keysign ceremony passes into the underlying TSS library using this
vault's own live `membership` count. Full derivation and file/line citations in
METHODOLOGY.md 3.6 and `scorers.py`'s `tss_required_signers()` docstring.

**adminKeyScore/multisigScore reasoning.** `k=14, n=20` reuses the same bare-`(k,n)`
ladder already applied to Zcash's own P2SH funds (`admin_key_score_kn`,
`multisig_score_kn`): `k>=3` maxes `adminKeyScore` at 65, and
`min(100, 20*14-(20-14))=274` clips `multisigScore` to 100. A 14-of-20 TSS threshold
is a materially larger, harder-to-collude quorum than any Zcash-side 2-of-3 P2SH fund
in this repo -- reflected correctly by the reused ladder, not a new one invented for
this target.

**Not reconciled, disclosed honestly (does not block the score).** Vault B's ~22.06
ZEC gap (ledger above live on-chain balance) has a plausible but NOT confirmed
explanation: `/mayachain/queue/outbound` lists a queued ZEC outbound from vault B's
exact pub_key for 2,206,088,478 zat, within 25,000 zat of the gap -- but a
`zcash_read.py tx` scan of vault B's recent history did not find a matching completed
spend in the windows checked. Separately, three ZEC figures for this target overall
disagree (live on-chain sum 3,479.22 ZEC; Mayachain's own pool ledger 2,646.56 ZEC;
DefiLlama TVL $3.89M, itself drifting within the same session) -- not chased to a
conclusion. Neither gap changes today's published scores, which use the
two-operator-agreed live on-chain balance, not the ledger or DefiLlama figures, for
its own factual disclosures (the balance is not itself a scoring dimension).

**Single-source limitation, disclosed.** Unlike every NEAR read in this project
(cross-checked on two independent RPCs) or every Zcash read (cross-checked on two
independent lightwalletd operators), the Mayachain-side reads here (membership,
halted status, outbound queue) rely on one API (`mayanode.mayachain.info`) -- no
second independent public Mayachain full-node API was found reachable this pass
(`scripts/maya_read.py`'s docstring lists the hostnames probed, all DNS failures).
This is Mayachain's own replicated consensus state, which every synced node must
agree on byte-for-byte -- a real but weaker guarantee than an independent second
read, and disclosed as such rather than presented as equivalent.

## Tooling fix landed this pass

`scripts/zcash_read.py`'s `tx` subcommand was P2SH-only (hardcoded `a914<h160>87`
matcher), so it silently returned `outputs_to_addr=0` for every real transaction to a
`t1`/`tm` (P2PKH) address -- a false negative from a tooling gap flagged but not
fixed by `data/scouting_candidates_2026-09-18.md`. Fixed by adding the standard
P2PKH matcher (`76a914<h160>88ac`), address-prefix-selected, cross-validated against
the same script-template convention `scripts/miner_concentration.py`'s own `addr()`
decoder already uses and trusts. Also extracted `taddr_balance()` as an importable
function (previously inline in `tx`'s CLI branch only) so `scorers.py` can call it
directly instead of shelling out to this file as a subprocess.

## Reproduction

```
python3 -c "
import sys; sys.path.insert(0, 'chains/zcash')
from scorers import score_all
for r in score_all():
    print(r['target'], r['label'], r['compositeScore'], r.get('l1CappedComposite'))
"
```

Runs in a few minutes: the existing `L1`/`FUND`/`EXT` reads plus one Mayanode
`/mayachain/vaults/asgard` call and, per active vault holding ZEC, one
`GetTaddressBalance` call on each of the two lightwalletd operators.
