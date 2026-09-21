# Batch 11 (2026-09-17, evening run): Snuggle (MaxFi Robinhood vault)

Scouted from DefiLlama's live protocol list (`https://api.llama.fi/protocols`,
`chains` containing "Robinhood Chain"), sorted by Robinhood Chain TVL, skipping
protocols already tracked directly or through a shared authority chain.
One target only. Of the untracked leads with more Robinhood Chain TVL, up v3's
DefiLlama module path (`projects/up-v3/index.js`) returned 404 at the time of
this run, and UNCX Network V3 (a liquidity locker, a different authority shape)
was not investigated in this pass. Both are left open rather than guessed.

## Snuggle: MaxFi Robinhood vault -- 1/100

| Field | Value |
|---|---|
| Target | `0x1195C074F898b7644bA732407619c9804dFE6DCE` (TransparentUpgradeableProxy, implementation `SnuggleVaultUpgradeable`) |
| TVL | ~$6.2M (DefiLlama `snuggle`, `chainTvls["Robinhood Chain"]`, live) |
| Custody | 11,849 Uniswap V3 position NFTs held by the vault (`balanceOf` on NonfungiblePositionManager `0x73991a25C818Bf1f1128dEAaB1492D45638DE0D3`) |
| adminKeyScore | 2 |
| multisigScore | 0 |
| timelockScore | 0 |
| crossExposureScore | 100 |
| compositeScore | 1 |

### Address source

DefiLlama's official adapter `DefiLlama-Adapters/projects/snuggle/index.js`,
`ROBINHOOD_VAULTS` (labelled "MaxFi Robinhood", a Snuggle white-label on the
same contract architecture, the only Robinhood Chain vault listed).
Cross-checked on Sourcify (runtime and creation bytecode `match` for proxy and implementation,
`src/SnuggleVaultUpgradeable.sol`) and by the live NFT balance above.

### Authority chain

| Step | Live result |
|---|---|
| Proxy EIP-1967 admin slot | ProxyAdmin `0x413Ca90D38D964546c2fE03cB103df57372630F6` |
| `ProxyAdmin.owner()` | `0x6aC51A706539D4F5A326dA2892520180858e25FF` |
| `vault.owner()` | same `0x6aC51A70...25FF` |
| That address | no bytecode (not a Safe, no EIP-7702 designator), 759 transactions on Robinhood Chain: a live private key |
| `vault.adminSatellite()` | `0xf1F413aB4eF210f2AeE5CDb998362b743a9e4fa2` (`SnuggleVaultAdminSatellite`, Sourcify bytecode match), `TIMELOCK_DELAY()` = 86,400s |

### Mitigating context looked for, and why it does not move the score

The vault's admin surface is split into an AdminSatellite with a real 24h
`TIMELOCK_DELAY`. Reading the verified source, that delay only applies to
`proposeTreasury`/`executeTreasury` and `proposeStakingManager`/`executeStakingManager`.
Everything else on the satellite is `onlyVaultOwner` (= `vault.owner()`) and
instant, including `addPool()`, which makes the vault call
`setApprovalForAll(positionAdapter, true)` on its NFT manager for an adapter
the caller chooses, and `updatePoolRewardAdapter()`, which does the same for a
reward adapter. `vault.setAdminSatellite()` is `onlyOwner` directly on the
vault, and the same key can upgrade the implementation instantly through the
ProxyAdmin. The 24h delay is real but gates nothing that key cannot route
around.

### Scoring

Same convention as Curve DEX (`score_curve_dex`: one bare key controlling both
the custody-side role and the other privileged path gives `admin_key = 2`), not
a new number: `floor(0.4*2 + 0.3*0 + 0.3*0 + 0.5)` = 1. Wired into
`scripts/lib/scorers.py::score_snuggle_maxfi_vault()` (fails closed if the
controller stops resolving, flags a re-score if it becomes a Safe) and into
`scripts/lib/signer_overlap.py` as group `snuggle`. Pushed to the testnet oracle in tx
`0x173db78bd97b89f94e7f6af6e9cf56055491412d612f3713883bffa8cf54f27c` (block 120879100);
`trackedTargetsCount()` went from 44 to 45 and `getScore()` re-reads (2, 0, 0, 100, 100, 1). The controller address does
not appear in any other tracked group, so crossExposureScore = 100.

What this does NOT say: nothing here suggests the key is compromised or that
the team acts in bad faith. It is a statement about how many keys must be lost
or misused before the 11,849 deposited positions are at risk: one.
