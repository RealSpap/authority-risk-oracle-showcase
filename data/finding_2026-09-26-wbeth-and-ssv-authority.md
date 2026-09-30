# The two largest untracked Ethereum protocols by TVL: one is a single-key token, the other is a 5-of-9 Safe (investigation, nothing scored)

2026-09-26. `finding_2026-09-26-tvl-coverage-by-ecosystem.md` ranks Ethereum's untracked protocols by DefiLlama value: SSV Network ($14.1B) and Binance staked ETH ($9.4B) come first.
`data/coverage_2026-09-21-tvl-by-ecosystem.md` had already set both aside as staking figures (the ETH sits behind validators' withdrawal credentials, not in a contract whose authority this oracle would score). That holds for the deposits; it does not cover the token contract, which is what is read here: for wBETH the code of a token with billions in claims sits behind one key.
Both read here directly, on two RPCs (publicnode and drpc, identical answers), read-only, no key. **No target added, no score changed.**

## Binance staked ETH (wBETH, `0xa2E33566...`): the token's code sits behind one bare key

Read: the token is a `FiatTokenProxy` (Circle-style, the OpenZeppelin-zos storage slots) in front of `WrapTokenV3ETH` (`0x9E021c96...`, 23,068 bytes, verified source).
Supply **3,175,330 wBETH** at an exchange rate of 1.1072, that is about 3.52M ETH of claim (DefiLlama's $9.4B).

- **Proxy admin: `0xA3eE6926...`, a bare EOA (no code, 3 transactions sent).** It is the only holder of `upgradeTo`, `upgradeToAndCall` and `changeAdmin`: one signature can replace the token's code, no delay, no multisig.
- **`owner`, `pauser`, `blacklister` and `masterMinter` are all one other bare EOA, `0x099d699C...` (4 transactions).** By the function names in the verified source it can pause every transfer, blacklist (freeze) any address, and configure minters. `rescuer` is unset.
- **The exchange rate has its own writer**: `oracle` is a 4,682-byte contract `0x81720695...` (not a Safe; not decoded here). `operator` `0x2B592157...` (EOA, 1,293 transactions) and `ethReceiver` `0x26ad6395...` (EOA, 67 transactions) are also single keys.
- **Addendum 30 Sep: a third bare key, on the minter.** The token has exactly one minter ever configured (one `MinterConfigured` event, full range, Tenderly gateway):
  `OperatorWallet` `0xb05a6449f383a1a43a172970858b97394fecdad6`, `isMinter` true, `minterAllowance` `0xffff...fd629a23c89cc88e78790e` (about 2^256, unlimited).
  It is a verified `TransparentUpgradeableProxy` (2,145 bytes, OpenZeppelin v0.8.4 source on Blockscout), and its EIP-1967 admin slot holds
  **`0x7cfe99c15537753682def016d17d4b29a7cab4ee`: no code, nonce 0, zero balance**. That key can `upgradeTo` the unlimited minter's code
  without any delay. Its `owner()` is `0xb2f56fc2...` and its `operator()` `0xa4243633...`, both bare EOAs. So three separate single keys
  sit on the mint path: the token's own proxy admin, the minter wallet's proxy admin, and the minter's owner. A key that has never sent a
  transaction and holds no gas is consistent with a cold key; the chain does not say. Same two RPCs, identical answers (block 26092268; the pass had read the same at 26092151);
  first noticed by the 30 Sep competitor pass through DeFiScan v2's wBETH review, re-read here directly.
- Not shown: how these keys are held (a low transaction count is consistent with a cold key and says nothing more), the rate-update rule behind `oracle`, or what limits the minter role; the underlying ETH sits with an exchange, off-chain, so the on-chain authority is over the token, not the deposits.
  A power over the token's code and balances is a real dependency for every market that takes wBETH as collateral or a pool that holds it.

## SSV Network (`0xDD9BC35a...`): 5-of-9 Safe, no module, no delay, but the $14.1B is not what it holds

Read: the proxy holds **4,795,951 SSV and 399.6 ETH**. Its `owner()` is Safe `0xb35096b0...`, **5-of-9, no module**, nine EOAs that have each sent between 1 and 693 transactions. The EIP-1967 admin slot is empty, so upgrades go through the implementation
(function not read), and there is no timelock between the owner and an upgrade.
The DefiLlama figure is not custody of this contract: it counts the ETH staked by validators that run on the network; the contract's own balance is the SSV token and a little ETH above (that the ETH stays with the stakers by design is SSV's documentation, not something I read on-chain).
So SSV is a real target with a real 5-of-9 upgrade authority, but ranking it first by DefiLlama's number overstates the value the authority controls; the token balance would need a price source I did not use.

## Why it matters for the coverage list

Ranking untracked protocols by TVL mixes two kinds of value: value the authority can move (wBETH's token holders, USDT0's locked USDT, the bridges' ETH) and value that merely runs on a network (SSV). The first kind is what this oracle exists to rate.

## Verification

One script over `ethereum-rpc.publicnode.com` and `eth.drpc.org` (storage slots `org.zeppelinos.proxy.admin` and `.implementation`, the EIP-1967 admin slot, `owner`/`pauser`/`blacklister`/`masterMinter`/`oracle`/`operator`/`ethReceiver`/`rescuer`, `totalSupply`, `exchangeRate`, Safe `getOwners`/`getThreshold`/`getModulesPaginated`, code sizes and transaction counts); ABI and source from `eth.blockscout.com`. Every figure identical on both RPCs.
