# Finding (2026-09-17): some HIP-3 dex deployer addresses are ALSO live, upgradeable EVM proxies -- the specific one checked turned out to be unrelated infrastructure, corrected after reading its verified source

**Correction, added after this file's own second revision overclaimed**:
an earlier version of this file said the evidence gathered (Hyperliquid's
own CoreWriter docs plus the implementation bytecode containing the
CoreWriter address) made it "likely a real, not just theoretical" second
root-control path over the `mkts`/`km` HIP-3 markets. Reading the
contract's actual VERIFIED SOURCE CODE on `hyperevmscan.io` (not attempted
in either earlier pass) shows this was too strong a claim: the
implementation is **Kinetiq's `HIP3StakingManager`**, a liquid-staking
(kHYPE) manager contract, and every CoreWriter-calling function reachable
from it (`sendIocOrder`, `sendVaultTransfer`, `sendTokenDelegate`,
`sendCDeposit`, `sendCWithdrawal`, `sendSpot`, `sendUsdClassTransfer`,
`addApiWallet`) is scoped to staking/trading actions available to any
ordinary account, NOT to the HIP-3 deployer-privileged actions this
project's own root-control set tracks (`haltTrading`, `setOracle`,
`setSubDeployers`, etc.). The general mechanism this file already
established (a HyperEVM contract's own address becomes its HyperCore
identity when it calls CoreWriter) remains real and worth knowing for
FUTURE targets -- but for THIS specific contract, it does not appear to
reach dex-admin privileges. See the "Corrected conclusion" section below
for the full, humbler read.

**Second correction, added 2026-09-17 (same day), after an adversarial
review of this file and the Kinetiq scorer built from it**: two further
inaccuracies in the ORIGINAL evidence write-up below, both now fixed in
place rather than left standing: (a) three "bytes of code" figures used
the hex STRING length instead of the actual byte count (`(len(hex)-2)/2`),
inflating every one by roughly 2x -- corrected to 879 (admin contract),
24,508 (Kinetiq implementation), and 8,429 (para's implementation); (b)
step 6 attributed ALL eight listed CoreWriter-calling functions to the
`HIP3L1Write` library, but `HIP3StakingManager.sol` itself only calls
`HIP3L1Write.addApiWallet` (via `setApiWallet`) -- `sendCDeposit`,
`sendTokenDelegate`, `sendCWithdrawal`, and `sendSpot` are actually called
via the SEPARATE sibling library `L1Write.sol`, from the inherited base
contract `StakingManager.sol` (`lib/lst/src/StakingManager.sol`, 8 call
sites confirmed via grep). The remaining three (`sendIocOrder`,
`sendVaultTransfer`, `sendUsdClassTransfer`) are defined in BOTH libraries
but not invoked by any contract in the source bundle read -- dead code,
not a live path. None of this changes the conclusion (still no dex-admin
CoreWriter call found), only the precision of how it's attributed.

Surfaced while promoting `para` and `mkts` as new HIP-3 dex targets
(`chains/hyperliquid/scorers.py`). This project's own established
convention (noted in `chains/hyperliquid/data/scored_targets_2026-09-17.md`)
was that HyperEVM-side code doesn't apply to any scored target -- true for
`xyz` and `io` (confirmed: `eth_getCode` returns `0x`, no code, on every
authority address either uses), but turns out to be FALSE for `para` and
for `mkts`/`km` (which share a deployer address, see the promotion
commit): all three have REAL, deployed HyperEVM bytecode at their
HyperCore-native deployer address.

## What was independently verified, live, on HyperEVM (`https://rpc.hyperliquid.xyz/evm`)

1. **`para`'s deployer** (`0x8888888c43cbb7e1c4132542e46831bffd866ed3`) and
   **`mkts`/`km`'s shared deployer** (`0x71f0019cc7fa79e4f42587fb7b9a817d8d2429ec`)
   both have real EVM bytecode (nonce 1 and 2 respectively) recognizable as
   EIP-1967 proxy patterns (the classic `PUSH32
   0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc`
   implementation-slot constant appears in both).
2. **Independently computed the EIP-1967 slot constants from scratch**
   (`keccak256("eip1967.proxy.implementation") - 1` and
   `keccak256("eip1967.proxy.admin") - 1`, via `Crypto.Hash.keccak`) rather
   than trusting a remembered value -- a first attempt using a
   from-memory constant was one hex digit short and silently read an
   unrelated, empty slot; recomputing properly and re-reading caught this
   before it became a false "no implementation set" conclusion.
3. **`para`'s proxy**: implementation slot resolves to
   `0x00000006711dce34e37ec3e1b18f21a3d5399fbe`, a real deployed contract
   (8,429 bytes of code -- `(len(hex string)-2)/2`, not the hex string's
   own character count) -- live, not dormant. Its EIP-1967 **admin slot
   reads as zero** -- **closed 2026-09-17, same day, before this was
   ever taken as final**: this file's own earlier text on this point was
   already hedged ("not independently confirmed beyond this, since
   para's own deployment transaction was not traced") and its "What this
   does NOT do" section already flagged reading `para`'s own
   implementation source as the explicit open follow-up. Doing that
   follow-up shows the hedge understated the real gap: the contract
   (name `StakingVault`, verified source) is a UUPS proxy (`OpenZeppelin
   UUPSUpgradeable`), which never uses the EIP-1967 ADMIN slot at all --
   only a TRANSPARENT proxy does. A zero admin slot therefore carries NO
   evidentiary weight either way for a UUPS proxy, not even as a hedged
   signal toward immutability -- it should not have been cited as
   "consistent with" anything. The real, LIVE upgrade authority is gated
   by `_authorizeUpgrade` inside the implementation itself, which checks
   an EXTERNAL `RoleRegistry` contract's `owner()` -- a real, resolvable
   1-of-1 Gnosis Safe, not an immutable dead end. This is now scored in
   its own right as a separate target (`para StakingVault`,
   `chains/hyperliquid/data/methodology_test_2026-09-17-para-staking-
   vault.md`) -- see that file for the full derivation, including two
   OTHER authority paths (`MANAGER_ROLE`, held by a contract whose
   implementation has no verified source; `OPERATOR_ROLE`, a
   separate 1-of-3 Safe) this same investigation found.
4. **`mkts`/`km`'s proxy**: implementation slot resolves to
   `0x26264514cd6018d6f944eb30b782aee2794b70b8` (24,508 bytes of code,
   also live). Its EIP-1967 **admin slot resolves to
   `0x6181cb542015490dd2985043f9ff119896ca92d0`** -- a real contract
   (879 bytes), confirmed via `eth_call` to expose standard OpenZeppelin
   `Ownable` selectors (`owner()`, `transferOwnership(address)`,
   `renounceOwnership()`).
5. **Traced one level further**: calling `owner()` on that admin contract
   returns `0x18a82c968b992d28d4d812920eb7b4305306f8f1` -- confirmed via
   its own bytecode signature (the classic Gnosis Safe proxy pattern,
   `masterCopy()` selector `0xa619486e`) and a live `getThreshold()` /
   `getOwners()` call to be a real **4-of-8 Gnosis Safe** with 8 named
   owner addresses (see reproduction section).
6. **Read the implementation contract's actual VERIFIED SOURCE**, rather
   than stopping at "its bytecode contains the CoreWriter address" as
   sufficient evidence (an earlier revision of this file did stop there,
   and overclaimed as a result -- see the correction at the top). Fetched
   `hyperevmscan.io`'s Source Code tab for `0x26264514cd6018d6f944eb30b7
   82aee2794b70b8`: **Source Code Verified, Exact Match**, contract name
   `HIP3StakingManager`, contract creator tagged `Kinetiq: Deployer`. TWO
   textually near-identical libraries both reference `CORE_WRITER`
   (confirming step 4's bytecode-level observation, not a coincidental
   byte match) -- but they are not the same call path:
   `HIP3StakingManager.sol` itself only calls `HIP3L1Write.addApiWallet`
   (via its own `setApiWallet`); the four CoreWriter sends actually
   exercised elsewhere (`sendCDeposit`, `sendTokenDelegate`,
   `sendCWithdrawal`, `sendSpot`) go through the SEPARATE sibling library
   `L1Write.sol`, called from the inherited base contract
   `StakingManager.sol` (`lib/lst/src/StakingManager.sol`, 8 call sites
   confirmed via grep). Three more (`sendIocOrder`, `sendVaultTransfer`,
   `sendUsdClassTransfer`) are defined in both libraries but not invoked by
   any contract in the source bundle read -- dead code, not a live path.
   None of these eight is a HIP-3 deployer-admin action. The contract's
   own ABI (also fetched) confirms this: its
   externally-callable functions and roles (`MANAGER_ROLE`,
   `OPERATOR_ROLE`, `SENTINEL_ROLE`, `TREASURY_ROLE`, staking limits,
   withdrawal delays/queues, validator delegation, emergency withdrawal)
   are all Kinetiq's own kHYPE liquid-staking product concerns.

## Corrected conclusion: real mechanism, but not (as far as verified) a real path to dex-admin privileges for THIS target

**Confirmed, and still true**: `mkts`/`km`'s shared HyperCore-native
deployer address also functions, on HyperEVM, as an upgradeable proxy
whose implementation can ultimately be changed by a real 4-of-8 Gnosis
Safe -- a genuine, live, on-chain authority chain neither `xyz` nor `io`
(the only targets scored before today) have any equivalent of.

**Confirmed, and still true**: Hyperliquid's own documentation on
`CoreWriter` (the fixed system contract at
`0x3333333333333333333333333333333333333333`) states plainly: *"When a
contract calls CoreWriter, the action is on behalf of the contract
address, not the EOA that called your contract."* -- a smart contract's
own address genuinely is a first-class HyperCore identity when it calls
CoreWriter. This is real, useful, general methodology knowledge for any
FUTURE Hyperliquid target whose deployer address turns out to be a smart
contract: it must be checked what that contract can actually send, not
assumed benign just because it's "only" EVM-side code.

**Corrected**: for THIS specific implementation, having now read its
verified source rather than stopping at "the bytecode contains the
CoreWriter address," the contract in question is Kinetiq's own staking
manager, and its CoreWriter usage is scoped to staking/trading helpers
available to any account -- not to `haltTrading`/`setOracle`/
`setSubDeployers`-type deployer-privileged actions. The 4-of-8 Safe behind
it is real, on-chain, and controls something real (Kinetiq's own kHYPE
staking-manager upgrade path) -- but the evidence gathered does NOT
support the earlier, stronger claim that it constitutes a second
root-control path over the `mkts`/`km` perp markets specifically. Most
likely explanation, not independently confirmed further: Kinetiq
operates the `mkts`/`km` HIP-3 dexes under this deployer identity as part
of its own protocol, and separately reuses that same identity's EVM
address for its unrelated staking-manager infrastructure -- two things
sharing one address, not one thing controlling the other.

**What remains genuinely open**: whether `HIP3StakingManager.sol` (not
just the `HIP3L1Write` library) has any function that constructs and
sends an arbitrary raw CoreWriter action (bypassing the specific helper
functions listed above) was not fully ruled out -- the ABI and file
outline gathered strongly suggest not (no generically-named "execute" or
"sendRawAction"-passthrough function appears among its own external
functions), but the full contract source was not read line by line. Also
not resolved: attribution of the 4-of-8 Safe's 8 owners to named
individuals, and whether the "Kinetiq: Deployer" tag on `hyperevmscan.io`
(a private, explorer-provided name tag, not an on-chain fact) is itself
reliable.

## What this does NOT do

- **Does not change `compositeScore` for `para`, `mkts`, or `km`.** Even
  under the original, stronger (since-corrected) reading this would not
  have lowered the score: this project's own "several authorities per
  target" convention (METHODOLOGY.md 6.2, same convention applied on the
  Solana side this same day) takes the MINIMUM across every full-power
  path, and `mkts`/`km`'s direct HyperCore-native path is already a bare
  single key (`adminKeyScore=10`, near the floor). Now that the specific
  EVM-side contract is confirmed to be staking infrastructure rather than
  a dex-admin path, there is in any case nothing dex-specific to fold in.
- Does not check whether `xyz`'s or `io`'s deployer addresses might
  ALSO gain EVM-side code in the future (both currently read `0x`, no
  code, confirmed live today) -- a re-check worth doing on any future
  Hyperliquid re-scout, not assumed permanent.
- Does not identify the 4-of-8 Safe's 8 owners beyond their bare
  addresses (no attempt made to attribute them to named individuals or
  entities), and does not independently verify Kinetiq's own identity
  beyond the explorer-provided "Kinetiq: Deployer" tag.
- Does not check whether this SAME Safe (or the SAME admin-contract
  pattern) sits behind any OTHER HIP-3 dex deployer's EVM-side code
  beyond `para` and `mkts`/`km` -- the other 6 dexes' deployer addresses
  were not re-checked for EVM-side code as part of this finding (their
  open-interest sweep, done the same day, did not itself query
  `eth_getCode`).
- Does not read `HIP3StakingManager.sol`, `StakingManager.sol`, or either
  `L1Write` library (the contracts themselves, as opposed to the ABI/
  function list and the specific call sites already grepped) line by
  line -- the concrete, well-scoped next step if a reason emerges to
  revisit this.
- **CLOSED, same day**: `para`'s own implementation source WAS read
  (contract name `StakingVault`, unrelated to Kinetiq's contract) --
  see the corrected point 3 above and `chains/hyperliquid/data/
  methodology_test_2026-09-17-para-staking-vault.md` for the full
  derivation and its own separately-scored target.

## Reproduction

```bash
cd chains/hyperliquid/scripts
python3 -c "
from methodology_test import evm
IMPL = '0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc'
ADMIN = '0xb53127684a568b3173ae13b9f8a6016e243e63b6e8ee1178d6a717850b5d6103'
for addr in ['0x8888888c43cbb7e1c4132542e46831bffd866ed3', '0x71f0019cc7fa79e4f42587fb7b9a817d8d2429ec']:
    print(addr, 'impl=', evm('eth_getStorageAt',[addr,IMPL,'latest'])[-40:], 'admin=', evm('eth_getStorageAt',[addr,ADMIN,'latest'])[-40:])
print(evm('eth_call', [{'to':'0x6181cb542015490dd2985043f9ff119896ca92d0','data':'0x8da5cb5b'},'latest']))  # owner()
print(evm('eth_call', [{'to':'0x18a82c968b992d28d4d812920eb7b4305306f8f1','data':'0xe75235b8'},'latest']))  # getThreshold()
print(evm('eth_call', [{'to':'0x18a82c968b992d28d4d812920eb7b4305306f8f1','data':'0xa0e67e2b'},'latest']))  # getOwners()
# Confirm the implementation contract's own bytecode references CoreWriter
code = evm('eth_getCode', ['0x26264514cd6018d6f944eb30b782aee2794b70b8', 'latest'])
print('references CoreWriter:', '3333333333333333333333333333333333333333' in code.lower())
"
```

Verified source (contract name `HIP3StakingManager`, creator tagged
`Kinetiq: Deployer`), confirming it is Kinetiq's staking manager, not a
dex-admin tool:

```
https://hyperevmscan.io/address/0x26264514cd6018d6f944eb30b782aee2794b70b8#code
```
