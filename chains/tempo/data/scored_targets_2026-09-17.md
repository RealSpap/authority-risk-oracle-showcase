# Tempo -- scored targets, 2026-09-17

Promotes [`../METHODOLOGY.md`](../METHODOLOGY.md) section 4.1's rules
(R1-R7) into the standard `scorers.py` / `score_all()` shape every other
ecosystem in this project uses: [`../scorers.py`](../scorers.py). The
underlying read-and-score logic was already fully implemented and
live-tested in `scripts/methodology_test.py` on 2026-09-16 -- this pass
adds only the `score_all()` sequencing that file's own `main()` did inline
and unexported.

## Summary table

| Target | Address | adminKey | multisig | timelock | oracleAuthority | crossExposure | composite | chainCappedComposite |
|---|---|---|---|---|---|---|---|---|
| Tempo L1 validator registry (ValidatorConfigV2, chain baseline) | `0xCCCCCCCC00000000000000000000000000000001` | 50 | 37 | 0 | 100 | 100 | **31** | n/a (this IS the baseline) |
| USDC.e (Bridged USDC, Stargate) | `0x20C000000000000000000000b9537d11c60E8b50` | 65 | 98 | 0 | 100 | 100 | **55** | **31** |
| USDT0 | `0x20c00000000000000000000014f22ca97301eb73` | 65 | 58 | 0 | 100 | 100 | **43** | **31** |
| pathUSD (native, added 2026-09-17) | `0x20c0000000000000000000000000000000000000` | 20 | 0 | 0 | 100 | 100 | **8** | **8** |

The first three match `data/methodology_test_2026-09-16.md`'s hand-derived
numbers exactly. pathUSD is new the same day, added as a follow-up -- see
below.

### pathUSD -- the weakest-scored target on Tempo, added same day

pathUSD is Tempo's own native/first-party stablecoin (the fee-fallback
token cited in METHODOLOGY.md section 5), NOT bridged via LayerZero (not
listed among section 3.7's bridged assets) -- `score_token()` was extended
to accept `lz_oapp=None` for exactly this case (see its own comment in
`scripts/methodology_test.py`) rather than assuming every TIP-20 is
bridged. Second-largest stablecoin on Tempo by supply (~$39.3M live, bigger
than USDT0's ~$9.7M), promoted for the same reason `io` was added to
Hyperliquid the same day: real usage, not just being next on a list.

Root-control set, live-read via a full-history `RoleMembershipUpdated`
scan: `DEFAULT_ADMIN_ROLE` is a single EIP-7702-delegated EOA
(`0x79C6631F...4a4E`, `k=1,n=1`); `ISSUER_ROLE` is a 100-byte contract
(`0x8354D80E...9058`) that does not resolve via any of `owner()`/`admin()`/
`minter()`/`controller()`/`vault()` -- an "unresolved contract" per rule
R2, the weakest possible key by rule R3's own definition. This -- not a
degraded/failed read -- is what drives `adminKeyScore=20`,
`multisigScore=0`: the token's own genuinely weakest authority path could
not be resolved to a named signer set at all, a materially different (and
weaker) shape than USDC.e's 5-of-7 OneSig or USDT0's 3-of-5 Safe.
`compositeScore=8`, the lowest of any Tempo target scored so far, including
the chain baseline itself (`chainCappedComposite=8`, no effect since
pathUSD's own score is already the binding constraint).

## Verification

Every `eth_call` fact this scorer reads is cross-checked against a second,
independent RPC (`https://tempo-rpc.publicnode.com` alongside the official
`https://rpc.tempo.xyz`) INSIDE `methodology_test.py`'s own `call2()`
helper -- this isn't an optional pass run separately, the read primitive
itself raises `RuntimeError` on any disagreement between the two endpoints,
so a passing run is a cross-RPC-verified run by construction. This is a
stronger guarantee than the same-day Solana promotion could get for one of
its two targets (rate-limited on retry) or Hyperliquid (no independent
second source exists for HyperCore at all).

Role-holder enumeration for both tokens comes from a full-history
`RoleMembershipUpdated` log scan (100,000-block windows, the official
endpoint's limit) -- `https://tempo-rpc.publicnode.com` refuses this bulk
`eth_getLogs` query (HTTP 403, a documented, disclosed single-source gap
already flagged in the methodology test itself), so the SET of candidate
holders comes from one source, though each candidate's actual role
membership is then confirmed with `hasRole` on both endpoints. A role
grant missing entirely from the official endpoint's logs would not be
found by either endpoint -- carried forward as an open item, not silently
treated as fully double-sourced.

## Why these targets

USDC.e is the largest stablecoin on Tempo by supply (~61.6M) and exercises
every TIP-20-specific part of the methodology (role system, TIP-403 policy,
a bridge contract as issuer via a LayerZero OneSig multisig). USDT0 tests a
different issuer design (Tether's own proxy-based OFT, not Stargate, with a
live custom blacklist policy). pathUSD (added same day) is the weakest
authority shape found on Tempo so far -- see its own section above. The L1
validator registry is scored because it is the authority ceiling for every
other Tempo target (`chainCappedComposite`, METHODOLOGY.md rule R6b) -- the
same role the Hyperliquid L1 and Robinhood Chain's rollup-authority target
play in their own ecosystems.

## What this does NOT cover yet

- The chain baseline's `getActiveValidators()` returns registry entries
  (14 active on mainnet at last read), not the current DKG committee.
  **Resolved, not just open, as of 2026-09-17**: TIP-1070 (the spec that
  would define a `getCommitteeMembers()` read) is `status: Draft`,
  `protocolVersion: TBD`, and absent from the live mainnet fork schedule
  (`tempo_forkSchedule`, active hardfork T11) and from the next hardfork's
  own meta-TIP -- the committee-state precompile does not exist on Tempo
  mainnet yet at all, so registry size is not a stopgap for an
  undiscovered address, it is the only thing currently readable
  (METHODOLOGY.md section 7, open point 3).
- Cross-chain signer reuse (the USDT0 Safe and the Stargate OneSig control
  the same asset on Ethereum/Arbitrum too) is recorded as a fact in
  `data/methodology_test_2026-09-16.md` but not folded into any tracked
  target's `crossExposureScore`, which only counts overlap among Tempo
  targets scored in the same run (METHODOLOGY.md rule R6, matching this
  project's existing within-ecosystem convention elsewhere).

## Reproduction

```
python3 -c "
import sys; sys.path.insert(0, 'chains/tempo')
from scorers import score_all
for r in score_all():
    print(r['target'], r['compositeScore'], r.get('notes'))
"
```

Runs about 2 minutes, mostly the full-history log scan (about 400
100,000-block windows against the official endpoint).
