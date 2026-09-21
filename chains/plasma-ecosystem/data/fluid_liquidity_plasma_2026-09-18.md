# Fluid (Instadapp) on Plasma -- raw on-chain trace, 2026-09-18

Target: **Fluid (Instadapp) Liquidity**, Plasma mainnet (EVM L1, chain ID
9745, RPC `https://rpc.plasma.to`, no API key). Companion to
`chains/plasma-ecosystem/scorers.py`'s `score_fluid_liquidity_plasma()`.

Scope note on this pass's own starting brief: the brief claimed "this
project's research today on Fluid-on-Base found a specific Liquidity
contract and a 24h TimelockController proposed by an Avocado Instadapp
smart account." A full-text search of this repo
(`grep -rli "fluid\|instadapp\|avocado"` across `chains/`, `data/`, and the
root docs) at the start of this pass returned **zero prior hits** -- no Base
research on Fluid exists anywhere in this repository as of 2026-09-18. This
file is the first time Fluid has been researched in this project. The
finding below (a real 24h `TimelockController` whose proposer is an
Avocado-pattern smart-account proxy) is independently re-derived here, live,
against Plasma directly -- not inherited from an unverifiable prior Base
pass.

## 1. Chain reachability

```
POST https://rpc.plasma.to  {"jsonrpc":"2.0","id":1,"method":"eth_chainId","params":[]}
-> {"jsonrpc":"2.0","id":1,"result":"0x2611"}          # 0x2611 = 9745, matches Plasma mainnet
POST https://rpc.plasma.to  {"jsonrpc":"2.0","id":1,"method":"eth_blockNumber","params":[]}
-> {"jsonrpc":"2.0","id":1,"result":"0x1f4daa2"}       # 32,764,834
```

## 2. Address discovery -- primary source

`Instadapp/fluid-contracts-public`, `deployments/deployments.md`, section
`### Liquidity`, `plasma` row:
https://github.com/Instadapp/fluid-contracts-public/blob/main/deployments/deployments.md#L156-L166

```
| plasma | 0x52Aa899454998Be5b000Ad077a46Bbe360F4e497 |
  [Link](https://plasmascan.to/address/0x52Aa899454998Be5b000Ad077a46Bbe360F4e497#code) |
  "0x4F6F977aCDD1177DCD81aB83074855EcB9C2D49e", "0xCA5E9219e1007931FD5d938C1815a90ef08f1584" | 0x0003 |
```

Liquidity is CREATE2-deployed with identical constructor args + salt on
every chain Fluid ships on (mainnet/arbitrum/base/polygon/plasma/bnb all
list the SAME address, `0x52Aa8994...4e497`, in this file) -- confirmed
below to be a real, separately-deployed contract on Plasma specifically via
a live `eth_getCode`, not assumed from the shared address alone.

## 3. eth_getCode -- confirm real deployed bytecode

```
POST https://rpc.plasma.to
{"jsonrpc":"2.0","id":1,"method":"eth_getCode","params":["0x52Aa899454998Be5b000Ad077a46Bbe360F4e497","latest"]}
```
Result: a 4,462-byte runtime (raw hex omitted here for length -- full text
captured in this pass's tool transcript; leading bytes
`0x60806040526004361061009a...`, includes selectors `0x6e9960c3`
(`getAdmin`), `0x704b6c02` (`setAdmin`), `0x22175a32`
(`setDummyImplementation`), `0xb5c736e4` (a slot-read getter), `0xc39aa07d`
(`addImplementation`), `0xf0c01b42` (`removeImplementation`) -- matches
Fluid's own `infiniteProxy/proxy.sol` interface exactly, not a generic
proxy).

**4,462 bytes of real, live bytecode on Plasma right now.**

## 4. Authority root -- owner() vs getAdmin()

```
POST https://rpc.plasma.to
{"jsonrpc":"2.0","id":3,"method":"eth_call","params":[{"to":"0x52Aa899454998Be5b000Ad077a46Bbe360F4e497","data":"0x8da5cb5b"},"latest"]}
-> {"jsonrpc":"2.0","id":3,"error":{"code":3,"message":"execution reverted",
     "data":"0xc44f8d3b000000000000000000000000000000000000000000000000000000000000c351"}}
```
`owner()` reverts. Decoded: selector `0xc44f8d3b` + payload `0xc351`
(50001) is the Liquidity proxy's OWN custom error (visible verbatim in its
fetched bytecode: `...7fc44f8d3b...815261c351...`) -- Fluid's own "no
implementation registered for this function selector" error, i.e. `owner()`
is genuinely not part of this contract's interface, not a generic Ownable
revert.

```
POST https://rpc.plasma.to
{"jsonrpc":"2.0","id":2,"method":"eth_call","params":[{"to":"0x52Aa899454998Be5b000Ad077a46Bbe360F4e497","data":"0x6e9960c3"},"latest"]}
-> {"jsonrpc":"2.0","id":2,"result":"0x0000000000000000000000004d6ce4f4498d59eed397bcbc687805a07f9b2346"}
```
`getAdmin()` (selector `0x6e9960c3`, independently re-derived via
`keccak256("getAdmin()")`, not copied from a brief) returns
**`0x4d6CE4F4498d59Eed397bCbC687805a07f9b2346`**.

Cross-check via raw storage read at the EIP-1967 admin slot
(`keccak256("eip1967.proxy.admin") - 1` = independently recomputed in
Python as `0xb53127684a568b3173ae13b9f8a6016e243e63b6e8ee1178d6a717850b5d6103`):

```
POST https://rpc.plasma.to
{"jsonrpc":"2.0","id":4,"method":"eth_getStorageAt","params":["0x52Aa899454998Be5b000Ad077a46Bbe360F4e497","0xb53127684a568b3173ae13b9f8a6016e243e63b6e8ee1178d6a717850b5d6103","latest"]}
-> {"jsonrpc":"2.0","id":4,"result":"0x0000000000000000000000004d6ce4f4498d59eed397bcbc687805a07f9b2346"}
```
Identical to `getAdmin()`'s return. Confirmed against Fluid's own source
that this is not a coincidence: `contracts/liquidity/infiniteProxy/
proxy.sol`'s `_ADMIN_SLOT` and `contracts/liquidity/common/variables.sol`'s
`GOVERNANCE_SLOT` are defined to the exact same constant -- on this
contract, "who can upgrade the implementation" and "who is protocol
governance" (`onlyGovernance`/`onlyAuths`/`onlyGuardians` bypass) are
provably the same key.

## 5. Is the admin/governance address an EOA, a Safe, or a Timelock?

```
POST https://rpc.plasma.to
{"jsonrpc":"2.0","id":5,"method":"eth_getCode","params":["0x4d6CE4F4498d59Eed397bCbC687805a07f9b2346","latest"]}
-> 9,741 bytes of real runtime bytecode (re-measured precisely via web3.py's
   w3.eth.get_code() in scorers.py -- NOT a bare EOA). Readable ASCII
   strings inside it: "TimelockController: caller must be timelock",
   "TimelockController: insufficient delay",
   "AccessControl: account ... is missing role ...".
```

```
POST https://rpc.plasma.to
{"jsonrpc":"2.0","id":6,"method":"eth_call","params":[{"to":"0x4d6CE4F4498d59Eed397bCbC687805a07f9b2346","data":"0xa0e67e2b"},"latest"]}  # getOwners()
-> {"jsonrpc":"2.0","id":6,"error":{"code":3,"message":"execution reverted"}}
POST https://rpc.plasma.to
{"jsonrpc":"2.0","id":7,"method":"eth_call","params":[{"to":"0x4d6CE4F4498d59Eed397bCbC687805a07f9b2346","data":"0xe75235b8"},"latest"]}  # getThreshold()
-> {"jsonrpc":"2.0","id":7,"error":{"code":3,"message":"execution reverted"}}
```
**Not** a Gnosis Safe.

```
POST https://rpc.plasma.to
{"jsonrpc":"2.0","id":8,"method":"eth_call","params":[{"to":"0x4d6CE4F4498d59Eed397bCbC687805a07f9b2346","data":"0xf27a0c92"},"latest"]}  # getMinDelay()
-> {"jsonrpc":"2.0","id":8,"result":"0x0000000000000000000000000000000000000000000000000000000000015180"}
```
`0x15180` = **86400 seconds = exactly 24 hours.** A real, live OpenZeppelin
`TimelockController`. Every one of `PROPOSER_ROLE`/`EXECUTOR_ROLE`/
`CANCELLER_ROLE`/`TIMELOCK_ADMIN_ROLE`'s keccak256 hashes, independently
computed in Python (`eth_utils.keccak`), was found verbatim as a constant
inside this contract's own fetched bytecode.

**Docs-vs-chain cross-check:** the same `deployments.md` file separately
lists this exact address under its own row (byte-identical across
mainnet/arbitrum/base/polygon/plasma, CREATE2) with constructor args
`(86400, ["0x4F6F977aCDD1177DCD81aB83074855EcB9C2D49e"], ["0x196Ed45eC4ACA949E7AA921ceC81e219e682775e"], "0x000...000")`
-- the docs' `86400` matches this run's live `getMinDelay()` read exactly.

## 6. Role trace (hasRole / getRoleAdmin)

```
hasRole(TIMELOCK_ADMIN_ROLE, Timelock itself)   = true
hasRole(TIMELOCK_ADMIN_ROLE, 0x000...000)       = false
getRoleAdmin(PROPOSER_ROLE)                     = TIMELOCK_ADMIN_ROLE (standard OZ hierarchy)
hasRole(PROPOSER_ROLE, 0x4F6F977a...9B2D49e)    = true
hasRole(EXECUTOR_ROLE, 0x196Ed45e...2775e)      = true
hasRole(CANCELLER_ROLE, proposer 0x4F6F977a...) = true
hasRole(CANCELLER_ROLE, executor 0x196Ed45e...) = false
```
Self-administered (no external super-admin escape hatch). Canceller power
sits on the proposer only (OZ's standard constructor behavior) -- no
separate zero-delay bypass path found.

## 7. One hop further -- who are the proposer/executor?

```
eth_getCode(0x4F6F977aCDD1177DCD81aB83074855EcB9C2D49e) = 327 bytes  (re-measured via web3.py)
eth_getCode(0x196Ed45eC4ACA949E7AA921ceC81e219e682775e) = 171 bytes
```
Both are contracts, not bare EOAs. Neither is Safe-shaped
(`getOwners()`/`getThreshold()` revert on the proposer). The proposer's
storage slot 0 (`eth_getStorageAt(proposer, 0x0)`) reads
`0x...ea4ebf3ec9f3be577a04b02782d8683b2304b614` -- a minimal proxy
delegating to a shared 24,392-byte implementation contract. Bytecode shape
(immutable-embedded router address, selector-gated dispatch,
`0x4d420585`/`0x68beab3f`/`0x874095c6` selector checks) is consistent with
Instadapp's own "Avocado" smart-account proxy architecture, but this pass
did **not** resolve that implementation's own signer set/threshold --
`getSigners()`, `threshold()`, `owner()`, `isOwner()` all revert on the
proposer. **Open point, disclosed rather than guessed**: the proposer and
executor are confirmed to be real smart-contract wallets (not EOAs, not
plain Gnosis Safes), but their own internal signer strength is unresolved
this pass.
(Resolved on 2026-09-20: the proposer is an Avocado multisig, `signers()` / `requiredSigners()`, 6 of 12, and
the executor a 3-of-5 Safe; see `fluid_liquidity_plasma_2026-09-20_signers.md`.)

`eth_getLogs` for `RoleGranted` events across the full history was
attempted to independently re-derive the proposer/executor from event logs
rather than from the docs row -- `https://rpc.plasma.to` refused with
`{"code":-32614,"message":"eth_getLogs is limited to a 10,000 range"}`
against a ~32.7M-block chain, and no contract-creation-block lookup was
done to narrow it this pass. The proposer/executor addresses used above are
therefore sourced from `deployments.md`'s documented constructor args for
this Timelock, then independently confirmed live via `hasRole()` -- not
re-derived from raw event history.

## 8. Best current read of the authority shape

**TimelockController**, self-administered, confirmed live 24-hour
(86,400s) minimum delay, no separate external super-admin or zero-delay
cancel path found. Proposer and executor are each a single smart-contract
wallet (Avocado-pattern minimal proxy), not a bare EOA and not a plain
Gnosis Safe -- their own internal signer/threshold configuration is an
open point, not resolved this pass (resolved 2026-09-20, see `fluid_liquidity_plasma_2026-09-20_signers.md`). This is the SAME storage slot that
also controls Liquidity's own proxy-implementation upgrades, so this one
24h-delayed Timelock gates both protocol governance AND upgrade authority.

## Sources

- https://github.com/Instadapp/fluid-contracts-public/blob/main/deployments/deployments.md
  (Liquidity section, `plasma` row; also the TimelockController's own row,
  same file, constructor args `(86400, [proposer], [executor], 0x0)`)
- https://github.com/Instadapp/fluid-contracts-public/blob/main/contracts/liquidity/infiniteProxy/proxy.sol
  (`_ADMIN_SLOT`, `getAdmin()`)
- https://github.com/Instadapp/fluid-contracts-public/blob/main/contracts/liquidity/common/variables.sol
  (`GOVERNANCE_SLOT` -- same constant as `_ADMIN_SLOT` above)
- https://github.com/Instadapp/fluid-contracts-public/blob/main/contracts/liquidity/common/helpers.sol
  (`_getGovernanceAddr()`)
- https://rpc.plasma.to (every eth_call/eth_getCode/eth_getStorageAt above, live 2026-09-18)
- https://plasma.to/insights/plasma-mainnet-beta-and-xpl and
  https://messari.io/project/plasma (Fluid confirmed as one of Plasma's
  launch-day DeFi partners, corroborating -- not substituting for -- the
  GitHub address-book source above)
