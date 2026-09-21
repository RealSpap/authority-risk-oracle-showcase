# Plasma Ecosystem -- scored targets, 2026-09-18 (scoring_build)

Final live-verified output of `chains/plasma-ecosystem/scorers.py::score_all()`
against `https://rpc.plasma.to` (chain 9745), after consolidating several
parallel research passes into one clean file and independently re-verifying
every address and authority-chain claim a second time (see the scorer file's
own top docstring for the disclosed operational note on why that
re-verification pass was necessary). Reproduce with
`python3 chains/plasma-ecosystem/scripts/dry_run.py`.

| # | Target | Address | Composite | adminKey | multisig | timelock | crossExposure |
|---|---|---|---|---|---|---|---|
| 0 | Plasma L1 validator-set authority (Aquila) | `0x6c50b8ca8EeAa1c75dEe5b5EA79772AcAbc92F48` | 35 | 50 | 50 | 0 | 100 |
| 1 | Aave V3 Pool (PoolAddressesProvider) | `0x061D8e131F26512348ee5FA42e2DF1bA9d6505E9` | 71 | 65 | 100 | 50 | 80 |
| 2 | Pendle (Router + Market Factory V6) | `0x888888888889758F76e7103c6CbF23ABbF58F946` | 43 | 65 | 55 | 0 | 100 |
| 3 | Ethena USDe OFT | `0x5d3a1Ff2b6BAb83b63cd9AD0787074081a52ef34` | 52 | 55 | 100 | 0 | 80 |
| 4 | Euler V2 eVaultFactory | `0x42388213C6F56D7E1477632b58Ae6Bba9adeEeA3` | 72 | 70 | 80 | 68 | 100 |
| 5 | Euler V2 AccessControlEmergencyGovernor | `0x9b3CeB22Cab2F1b9Ace4CD3132C8a123552eDa2c` | 68 | 68 | 80 | 55 | 100 |
| 6 | Fluid (Instadapp) Liquidity | `0x52Aa899454998Be5b000Ad077a46Bbe360F4e497` | 67 | 40 | 100 | 70 | 100 |

Mean composite: 58.3. Worst: 35 (the chain's own validator-set baseline --
consistent with this project's own pattern elsewhere of the L1 baseline
scoring at or near the bottom of its own ecosystem, since every other
target's authority ultimately depends on it). Best: 72 (Euler V2's
eVaultFactory -- the only target here with BOTH a real Timelock delay of
multiple days AND a plain-Safe cancel path, not a bare owner()-to-Safe
single hop).

## Cross-chain signer-overlap findings (crossExposureScore column above)

Two of the `crossExposureScore` values above (targets 1 and 3) are not
"not computed" defaults -- both are real, independently re-confirmed live
findings:

- **Aave V3's guardian Safe** (`0x19CE4363FEA478Aa04B9EA2937cc5A2cbcD44be6`,
  5-of-9) shares the IDENTICAL 9 owners as the guardian Safes already
  tracked on Arbitrum and Base (different address per chain,
  CREATE2-redeployed) -- a third chain sharing this committee, not two.
- **Ethena's USDe OFT owner Safe**
  (`0x2C57434603F21f580c91A3Bdc0CC5F3F20278632`, 5-of-10) shares the
  IDENTICAL 10 owners as Ethereum L1's own already-tracked Ethena Safe
  (`0x3b0aaf6e...`, `chains/ethereum-l1/scorers.py`) -- the same people
  control both, on two different chains, at two different addresses.

A third finding, found only by `scripts/check_cross_ecosystem_overlap.py`'s
own generic set-overlap check (not baked into either scorer's own
`crossExposureScore`, since it wasn't known at the time either was
written): Pendle's Plasma Safe (`0x7877AdFaDEd756f3248a0EBfe8Ac2E2eF87b75Ac`,
3-of-5) is not merely signer-identical but the LITERAL SAME Safe address
as Robinhood Chain's own already-tracked Pendle Safe -- this project's
first-ever hit on the "identical Safe address across ecosystems" check
(every prior run found signer overlap only). See `README.md`'s
"Cross-ECOSYSTEM signer overlap" section for the full live re-run output.

> UPDATED 2026-09-20: the paragraph above says the Pendle finding is not
> baked into the scorer's `crossExposureScore`. That is no longer true. Under
> the project convention decided 2026-09-20 (root `METHODOLOGY.md`, paragraph
> "Convention (decided 2026-09-20)"), a cross-ecosystem overlap is folded into
> `crossExposureScore` as a flat 80. Scorer output 2026-09-20: Pendle (Router +
> Market Factory V6, Safe `0x7877AdFa...75Ac` with the same address and 5
> owners as Robinhood Chain's Pendle Safe) 100 -> 80, composite 43 unchanged;
> Euler V2 eVaultFactory and Euler V2 AccessControlEmergencyGovernor (Plasma's
> Euler DAO Safe, 4-of-8, same 8 signers as Monad's Euler DAO Safe) 100 -> 80,
> composites 72 and 68 unchanged. The table above is left as the 2026-09-18
> record. The Plasma testnet oracle was re-pushed on 2026-09-20 (tx
> `0xa2e8f4f12ccbe3740734bccfa5ee9cf4c20018f5a453a38c00e77a8583cb3de4`,
> block 34034832) and now holds these three values as 80, read back equal to
> the scorer output.

## What this does NOT do

- Not deployed to any oracle contract yet -- dry-run only, same stage as
  Solana/Hyperliquid/Tempo/Zcash. (2026-09-18 state. The Plasma testnet oracle
  was deployed and pushed on 2026-09-19 and re-pushed on 2026-09-20, see
  `deploy/README.md`.)
- Single-RPC for most targets: no second independent public Plasma RPC
  could be found this pass (publicnode/drpc/Alchemy demo endpoints tried,
  none usable) except for Pendle, which WAS cross-checked against
  `https://9745.rpc.thirdweb.com` and matched byte-for-byte.
- Euler's eVaultFactory scorer does not enumerate all 156 vaults deployed
  through it to confirm how many are actually `upgradeable=true` (scored
  on the confirmed-live mechanism, not its full unconfirmed reach) -- see
  that scorer's own docstring.
- Fluid's proposer/executor signer strength (behind its Timelock) is
  unresolved -- both are smart-contract wallets, not EOAs, not Safe-shaped,
  and no `getSigners()`/`threshold()`-style interface responded this pass.
  (Resolved on 2026-09-20: the proposer is an Avocado multisig, `signers()` /
  `requiredSigners()`, 6 of 12, and the executor a 3-of-5 Safe; see
  `fluid_liquidity_plasma_2026-09-20_signers.md`.)
