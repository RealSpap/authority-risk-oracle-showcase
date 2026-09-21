# Plasma Ecosystem -- scouted targets, 2026-09-18 (scouting phase, run 1)

Phase: scouting, Plasma mainnet (chain 9745), read-only. First research pass for this
ecosystem -- no prior candidate backlog to draw from (`chains/plasma-ecosystem/data/`
and `scripts/` existed as empty scaffolding before this pass; no plasma commit existed
in this repo's git history before this file). Reuses this project's exact methodology
(same pattern as `chains/base-ecosystem/scorers.py` and `chains/arbitrum-ecosystem/
scorers.py`): live `eth_call`/`eth_getCode` against Plasma's own public RPC, address
sourced from the protocol's own official GitHub repo, authority traced to its root
(owner/AccessControl/Safe getOwners+getThreshold, EIP-1967 proxy slots checked where
relevant), never trusted from docs or a block explorer's "verified name" alone.

RPC used for every call below: `https://rpc.plasma.to` (no API key). **Disclosed gap**:
unlike the Base/Arbitrum scouting passes, no second independent public Plasma RPC could
be found this run to cross-check byte-identical results against (tried
`plasma-rpc.publicnode.com` -- empty/no response; `plasma.drpc.org` -- "chain is not
available on free plan"; `plasma-mainnet.g.alchemy.com/v2/demo` -- empty/no response).
Every read below is single-RPC. Chain identity itself was confirmed independently
though: `eth_chainId` on `rpc.plasma.to` returns `0x2611` = decimal 9745, matching
Plasma's documented chain ID, and `eth_blockNumber` returned `0x1f4daca` (32,844,490) at
time of read -- a live, advancing chain, not a stale/inactive endpoint.

## 1. Aave V3 Plasma (PoolAddressesProvider) -- fully verified root, real cross-chain shared-committee finding

- **Target**: `0x061D8e131F26512348ee5FA42e2DF1bA9d6505E9` (Aave V3 Plasma
  `PoolAddressesProvider`).
- **Source of address**: official `bgd-labs/aave-address-book` GitHub repo,
  `src/AaveV3Plasma.sol` on `main` (confirmed at commit `81de698ada0c07410ebd920183da
  65740aa12a7d`, dated 2026-08-17 -- over a month stable, not a same-day/unstable
  entry), `POOL_ADDRESSES_PROVIDER` constant:
  <https://github.com/bgd-labs/aave-address-book/blob/81de698ada0c07410ebd920183da65740aa12a7d/src/AaveV3Plasma.sol>
  This is the *same* address-book repo this project already cites for Aave on
  Ethereum L1, Base and Arbitrum.
- **Secondary/governance corroboration**: Aave governance forum, `[ARFC] Deploy Aave
  v3 on Plasma` (ACI, first posted 2025-03-15):
  <https://governance.aave.com/t/arfc-deploy-aave-v3-on-plasma/21494> -- plus a BGD
  Labs technical network-evaluation post
  (<https://governance.aave.com/t/23133>) and multiple later `[Direct-to-AIP]` asset-
  onboarding threads for the same Plasma instance (wrsETH, wstETH, XPL, PT-USDe/PT-
  sUSDe, the latest dated 2026-03-16) -- a live, actively-governed instance, not a
  one-off announcement that stalled.
- **TVL** (DefiLlama, read live this run): `api.llama.fi/protocol/aave-v3`,
  `currentChainTvls.Plasma` = **$496,229,838.73** supplied (`Plasma-borrowed` =
  $770,841,981.06). Total Plasma chain TVL (`api.llama.fi/v2/chains`, `name=="Plasma"`)
  = $569,659,557.24 -- Aave V3 alone is ~87% of all TVL on the chain, confirming the
  task's premise that it is the dominant lender here, not assuming it.

### eth_getCode -- confirms real deployed bytecode, live right now

```
curl -s https://rpc.plasma.to -X POST -H "Content-Type: application/json" \
  --data '{"jsonrpc":"2.0","method":"eth_getCode","params":["0x061D8e131F26512348ee5FA42e2DF1bA9d6505E9","latest"],"id":1}'
```
Result (truncated -- full hex is 13,814 characters after `0x`):
```
{"jsonrpc":"2.0","id":1,"result":"0x608060405234801561000f575f5ffd5b506004361061013d575f3560e01c806376d84ffc11...000a"}
```
**Bytecode size: 6,907 bytes** (13,814 hex chars / 2). Not `0x` / empty -- a real,
live contract on Plasma mainnet right now, not merely announced.

### Authority chain -- traced live, every hop an actual eth_call

1. **`PoolAddressesProvider.owner()`** (selector `0x8da5cb5b`):
   ```
   curl -s https://rpc.plasma.to -X POST -H "Content-Type: application/json" \
     --data '{"jsonrpc":"2.0","method":"eth_call","params":[{"to":"0x061D8e131F26512348ee5FA42e2DF1bA9d6505E9","data":"0x8da5cb5b"},"latest"],"id":1}'
   ```
   Result: `0x00000000000000000000000047aadaae1f05c978e6abb7568d11b7f6e0fc4d6a`
   -> **`0x47aAdaAE1F05C978E6aBb7568d11B7F6e0FC4d6A`** (EXECUTOR_LVL_1 per the
   address-book's own naming/comment on this exact address).

2. **`PoolAddressesProvider.getACLAdmin()`** -- cross-check against `owner()`.
   Correctness note: the selector `0xf14ebc6a` suggested in this run's task brief was
   independently re-derived rather than trusted, per this project's own "never trust a
   cited number" discipline -- `keccak256("getACLAdmin()")[:4]` computed locally
   (Python `pycryptodome`) is actually **`0x0e67178c`**, not `0xf14ebc6a` (calling with
   the brief's selector reverts; it does not correspond to this function). Using the
   correct, independently-computed selector:
   ```
   curl -s https://rpc.plasma.to -X POST -H "Content-Type: application/json" \
     --data '{"jsonrpc":"2.0","method":"eth_call","params":[{"to":"0x061D8e131F26512348ee5FA42e2DF1bA9d6505E9","data":"0x0e67178c"},"latest"],"id":1}'
   ```
   Result: `0x00000000000000000000000047aadaae1f05c978e6abb7568d11b7f6e0fc4d6a` --
   **identical to `owner()`**, and identical to the address-book's own `ACL_ADMIN`
   constant. Three independent confirmations of the same address (owner(), the
   correctly-computed getACLAdmin(), and the official address book).

3. **`EXECUTOR_LVL_1.owner()`** (same selector `0x8da5cb5b`, now against
   `0x47aAdaAE1F05C978E6aBb7568d11B7F6e0FC4d6A`):
   ```
   curl -s https://rpc.plasma.to -X POST -H "Content-Type: application/json" \
     --data '{"jsonrpc":"2.0","method":"eth_call","params":[{"to":"0x47aAdaAE1F05C978E6aBb7568d11B7F6e0FC4d6A","data":"0x8da5cb5b"},"latest"],"id":1}'
   ```
   Result: `0x000000000000000000000000e76eb348e65ef163d85ce282125ff5a7f5712a1d`
   -> **`0xe76eb348e65EF163D85cE282125fF5A7F5712A1D`**. `eth_getCode` on this address
   returns 1,096 bytes -- its runtime bytecode contains the literal EIP-1967
   implementation slot constant (`0x360894a13ba1a3210667c828492db98dca3e2076cc3735a92
   0a3ca505d382bbc`) and OpenZeppelin v5 `TransparentUpgradeableProxy` revert
   selectors (`0x34ad5dbb` = `ProxyDeniedAdminAccess()`, `0x4c9c8ce3` =
   `ERC1967InvalidImplementation(address)`) -- this is a genuine EIP-1967
   TransparentUpgradeableProxy, i.e. the **PayloadsController**, matching exactly the
   shape already found for Aave V3 on Base and Arbitrum. Raw storage read of the
   implementation slot:
   ```
   curl -s https://rpc.plasma.to -X POST -H "Content-Type: application/json" \
     --data '{"jsonrpc":"2.0","method":"eth_getStorageAt","params":["0xe76eb348e65EF163D85cE282125fF5A7F5712A1D","0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc","latest"],"id":1}'
   ```
   Result: `0x0000000000000000000000007120b1f8e5b73c0c0dc99c6e52fe4937e7ea11e0` ->
   implementation `0x7120b1F8e5B73c0C0Dc99c6e52fe4937E7Ea11e0`.

4. **`PayloadsController.owner()`** (delegatecalls into the implementation above):
   ```
   curl -s https://rpc.plasma.to -X POST -H "Content-Type: application/json" \
     --data '{"jsonrpc":"2.0","method":"eth_call","params":[{"to":"0xe76eb348e65EF163D85cE282125fF5A7F5712A1D","data":"0x8da5cb5b"},"latest"],"id":1}'
   ```
   Result: `0x00000000000000000000000047aadaae1f05c978e6abb7568d11b7f6e0fc4d6a` --
   **closes back to EXECUTOR_LVL_1 exactly**. A genuine, by-design mutual `owner()`
   pair (EXECUTOR_LVL_1 <-> PayloadsController), same as the already-documented,
   already-scored Base/Arbitrum Aave Governance V3 cross-chain infra -- not a loop
   that hides the real authority.

5. **`PayloadsController.getExecutorSettingsByAccessControl(1)`** (selector
   `0xf80281fb`, independently derived from `keccak256("getExecutorSettingsByAccess
   Control(uint8)")`, confirming the task brief's own suggested name/shape rather
   than trusting an untested selector):
   ```
   curl -s https://rpc.plasma.to -X POST -H "Content-Type: application/json" \
     --data '{"jsonrpc":"2.0","method":"eth_call","params":[{"to":"0xe76eb348e65EF163D85cE282125fF5A7F5712A1D","data":"0xf80281fb0000000000000000000000000000000000000000000000000000000000000001"},"latest"],"id":1}'
   ```
   Result: `0x00000000000000000000000047aadaae1f05c978e6abb7568d11b7f6e0fc4d6a000000
   0000000000000000000000000000000000000000000000000000015180` -> tuple
   `(executor=0x47aAdaAE1F05C978E6aBb7568d11B7F6e0FC4d6A, delaySeconds=0x15180)`.
   `0x15180` = **86,400 seconds = exactly 1 day**, same enforced delay already found
   on Base and Arbitrum's own Aave V3 executor pairs.

6. **`PayloadsController.guardian()`** (selector `0x452a9320`):
   ```
   curl -s https://rpc.plasma.to -X POST -H "Content-Type: application/json" \
     --data '{"jsonrpc":"2.0","method":"eth_call","params":[{"to":"0xe76eb348e65EF163D85cE282125fF5A7F5712A1D","data":"0x452a9320"},"latest"],"id":1}'
   ```
   Result: `0x00000000000000000000000019ce4363fea478aa04b9ea2937cc5a2cbcd44be6` ->
   **`0x19cE4363fEa478Aa04B9eA2937Cc5A2CBCd44bE6`** (GOVERNANCE_GUARDIAN -- can cancel
   queued payloads outside the timelock).

7. **GOVERNANCE_GUARDIAN Safe check** -- `eth_getCode` = 171 bytes (a Safe proxy),
   `VERSION()` (`0xffa1ad74`) decodes to the ASCII string `"1.4.1"` (a real Gnosis
   Safe singleton version, not an arbitrary contract):
   ```
   curl -s https://rpc.plasma.to -X POST -H "Content-Type: application/json" \
     --data '{"jsonrpc":"2.0","method":"eth_call","params":[{"to":"0x19cE4363fEa478Aa04B9eA2937Cc5A2CBCd44bE6","data":"0xa0e67e2b"},"latest"],"id":1}'
   curl -s https://rpc.plasma.to -X POST -H "Content-Type: application/json" \
     --data '{"jsonrpc":"2.0","method":"eth_call","params":[{"to":"0x19cE4363fEa478Aa04B9eA2937Cc5A2CBCd44bE6","data":"0xe75235b8"},"latest"],"id":1}'
   ```
   `getOwners()` decodes to exactly 9 addresses; `getThreshold()` =
   `0x...05` = **5**. A real **5-of-9 Gnosis Safe v1.4.1**.

   **Cross-chain shared-committee finding (verified programmatically, not
   eyeballed)**: the 9 owner addresses returned here --
   `0xDA5Ae43e179987a66B9831F92223567e1F38BE7D`,
   `0x1e3804357eD445251FfECbb6e40107bf03888885`,
   `0x4f96743057482a2E10253AFDacDA3fd9CF2C1DC9`,
   `0xebED04E9137AfeBFF6a1B97aC0adf61a544eFE29`,
   `0xbd4DCfA978c6D0d342cE36809AfFFa49d4B7f1F7`,
   `0xA3103D0ED00d24795Faa2d641ACf6A320EeD7396`,
   `0x936CD9654271083cCF93A975919Da0aB3Bc99EF3`,
   `0x0D2394C027602Dc4c3832Ffd849b5df45DBac0E9`,
   `0x4C30E33758216aD0d676419c21CB8D014C68099f` -- are, as a set, **byte-identical**
   to `chains/base-ecosystem/scorers.py`'s own `ARBITRUM_AAVE_GUARDIAN_OWNERS_2026_
   09_17` constant (Arbitrum's own Aave V3 GOVERNANCE_GUARDIAN Safe owner set, dated
   2026-09-17). Different Safe address on each chain (CREATE2-redeployed, same
   pattern this project already documented for ether.fi/Curve in `superchain-
   multisig-overlap`), same 9 signers, same 5-of-9 threshold. One compromised
   committee now reaches Base, Arbitrum, **and** Plasma's emergency-cancel path on
   Aave's cross-chain executor infra.

### Real, disclosed gap (same shape as the Base/Arbitrum siblings' own gap)

This scouting pass confirms the Plasma-side `PoolAddressesProvider` /
`EXECUTOR_LVL_1` / `PayloadsController` triple matches the official address book
exactly and is live on-chain with the expected 1-day delay and a real 5-of-9 Safe
guardian. It does **not** independently re-verify the Ethereum-mainnet Aave DAO root
(proposal counts, quorum, the L1 Timelock/Executor that a `CROSS_CHAIN_CONTROLLER`
would ultimately relay from) -- that root lives on L1 and is covered by
`chains/ethereum-l1/scorers.py`'s own `score_aave_v3_pool()`, not re-derived here.
The address book's `CROSS_CHAIN_CONTROLLER`-equivalent relay path for Plasma
specifically was not separately called live this run either (same disclosed scope
limit as Base's own scouting doc).

### Verification commands (re-run against `https://rpc.plasma.to`)

```
cast call 0x061D8e131F26512348ee5FA42e2DF1bA9d6505E9 "owner()(address)" --rpc-url https://rpc.plasma.to
cast call 0x061D8e131F26512348ee5FA42e2DF1bA9d6505E9 "getACLAdmin()(address)" --rpc-url https://rpc.plasma.to
cast call 0x47aAdaAE1F05C978E6aBb7568d11B7F6e0FC4d6A "owner()(address)" --rpc-url https://rpc.plasma.to
cast call 0xe76eb348e65EF163D85cE282125fF5A7F5712A1D "owner()(address)" --rpc-url https://rpc.plasma.to
cast call 0xe76eb348e65EF163D85cE282125fF5A7F5712A1D "getExecutorSettingsByAccessControl(uint8)((address,uint40))" 1 --rpc-url https://rpc.plasma.to
cast call 0xe76eb348e65EF163D85cE282125fF5A7F5712A1D "guardian()(address)" --rpc-url https://rpc.plasma.to
cast call 0x19cE4363fEa478Aa04B9eA2937Cc5A2CBCd44bE6 "getOwners()(address[])" --rpc-url https://rpc.plasma.to
cast call 0x19cE4363fEa478Aa04B9eA2937Cc5A2CBCd44bE6 "getThreshold()(uint256)" --rpc-url https://rpc.plasma.to
```

No new git commit made this pass -- per this project's orchestrator convention,
commits happen after garde-fous. Nothing outside `chains/plasma-ecosystem/` was
touched.
