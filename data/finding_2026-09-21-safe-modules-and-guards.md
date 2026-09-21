# Safe modules and guards on the registered root Safes (2026-09-21)

A Safe's owner set and threshold only say who can act if nothing else can. A **module** executes transactions as the Safe
without the owners' signatures; a **guard** can block them. Until today the shared helper every scorer uses
(`safe_owners_and_threshold`) read neither, and only some scorers looked (Robinhood Chain's `_safe_rooted_entry`, the Ethena
and Aave Horizon scorers on Ethereum L1, Tempo, Hyperliquid). So "4-of-9" or "1-of-5" was a claim about the threshold, not
about the authority. This pass reads both for every registered root Safe.

## Result

`python3 scripts/check_safe_modules_guards.py` (new; exit status 1 on any unanalyzed module or unread Safe):

**74 registered Safe addresses on 7 ecosystems: 68 clean (no module, no guard), 5 with an analyzed module or guard, 0 unanalyzed,
0 unread, 1 bespoke multisig that is not a Safe** (LayerZero's infrastructure owner on Robinhood Chain, already scored as a
custom multisig). The first version of this scan reported four more "not a Safe" entries on Base; they were transient RPC
failures, the three Safes resolve with retries, which is why the library returns `None` for a failed read and never an empty list.

| Safe | Enabled | What was found |
|---|---|---|
| Chainlink Price Feed Admin (Robinhood Chain, 4-of-9, owner of the 7 sampled Chainlink feeds; 57 are listed for the chain) | "Confirmed Transaction Module" 0.1.0 | `confirmTransaction`, `setExecutor` and `revokeTransaction` are manager-only (a random address reverts, the Safe succeeds), `executeTransaction` is executor-only and reverts for both; none of the 9 owners is an executor; the module has emitted no log and the Safe no `ExecutionFromModuleSuccess` event. It does not bypass the threshold, it separates approving from executing. Unused. |
| Arbitrum Security Council Emergency Safe (9-of-12) | the L2 `UpgradeExecutor` | The same address whose `EXECUTOR_ROLE` this Safe holds. The DAO's executor path can act as the Safe without Council signatures, beside the Council acting through it. Consistent with Arbitrum's documented design, not checked against its documentation here. |
| Radiant emergency-admin Safe (1-of-5) | two "HypernativeModule" pause modules | Both owned by one bare EOA (9 transactions, ~0.04 ETH), the Safe as their `updater`. From that EOA `pause()` succeeds; from the Safe and from a random address it reverts. Pause-class powers over two protected contracts, one extra key beside the Safe's five. No fund-moving call among their functions. |
| Ethena 5-of-10 Safe (Ethereum L1 and Plasma) | `EthenaSafeGuard` `0x74abe780...` as guard | Already a recorded positive control on L1 (whitelisted executors only, 48h in public to remove). The same guard address is set on the Plasma Safe; its own Plasma configuration was not read. |

Every power above was tested by `eth_call` simulation (no transaction), from the owner, from the Safe and from a random address.

## Singleton and fallback handler

The same sweep reads each Safe's singleton (the `masterCopy` in storage slot 0, which IS the Safe's logic) and its fallback
handler, and compares them with the published Safe builds (each address checked against Sourcify on Ethereum mainnet).

- **72 of 73 Safes point at a published build** (v1.4.1 `SafeL2` for 45, v1.3.0 for 22, v1.4.1
  `Safe` for 4, v1.1.1 for 1). No Safe uses a fallback handler that is not a published one; 2 have none set.
- **One does not: the Chainlink feed-admin Safe on Robinhood Chain**, the same Safe as the module above. Its singleton is
  `0x113779dA...3999` (23,328 bytes), an address the deployment lists do not publish, and its bytecode matches none of the
  published v1.3.0 builds (22,958 and 23,800 bytes). It is a Sourcify exact match on Robinhood Chain (chain 4663) for
  `contracts/GnosisSafe.sol`, solc 0.7.6, and its verified sources were diffed against `safe-global/safe-contracts` at tag
  v1.3.0: every core file is identical (GnosisSafe, Executor, OwnerManager, ModuleManager, FallbackManager, SelfAuthorized,
  SignatureDecoder, StorageAccessible and the rest) **except `GuardManager.sol`, where `setGuard` additionally requires the new
  guard to support the Guard interface (ERC-165, error GS300)**. That is a later upstream hardening, stricter than the
  published build, and touches nothing about owners, threshold, modules or execution. Benign, and now written down so it is
  not re-derived. Every other Safe on Robinhood Chain uses a published singleton.

The comparison used the verified sources, not the label: a bytecode that merely says "1.3.0" in `VERSION()` proves nothing.

## What changed in the code

- `scripts/lib/safe_modules.py`: `read_modules`, `read_guard`, `read_singleton`, `read_fallback_handler` (retried, `None` on
  failure), `classify` (clean, analyzed, unanalyzed, unread), the singleton and handler classifiers, `note_for`,
  `singleton_note`, and `KNOWN_ANALYSES` / `KNOWN_SINGLETON_ANALYSES`: every module, guard or odd singleton above with what was
  established and when.
  Anything not in that table is reported as **UNANALYZED**, so a module added later stands out instead of passing silently.
- The Arbitrum Security Council, Radiant, Plasma Ethena OFT and Robinhood Chainlink scorers now read their Safe's modules and
  guard live and add one note. **No score moves**: composites stay 64, 55, 52 and 36, verified live.
- 25 tests for the library and the sweep, and note tests in the four scorers' suites.

## What this does not say

- Before the gate below, this was a sweep over the registry plus four scorer notes. Now every scorer that resolves a Safe through
  the shared helper reads modules and singleton on each run and degrades on an unanalyzed one; the four notes stay because they
  carry what was found. Scorers that read a Safe's owners some other way (Tempo, Hyperliquid and Solana have their own
  resolvers) are not gated; Tempo and Hyperliquid read modules themselves.
- No module was found that lets a party other than the owners move funds unrestrained. That is a statement about these five
  modules as analyzed on 2026-09-21, not about modules added later, and the Radiant modules' source is not verified (their
  behaviour comes from revert strings, selectors and simulations).
- Guards and fallback handlers are read but never degrade a score: they can block or answer calls, not act as the Safe.

## Policy: an unanalyzed module or singleton degrades the score (decided 2026-09-21)

Until this point an unknown module only produced a note. It now changes the score, in one place instead of in ~76 call sites:
`safe_owners_and_threshold()` in `scripts/lib/web3_utils.py` reads the Safe's modules and singleton and returns `None`
("unresolved", the same as "not a Safe") when a module is enabled that is not in `KNOWN_ANALYSES`, or the singleton is neither a
published build nor in `KNOWN_SINGLETON_ANALYSES`. Every scorer already maps that result to the conservative unresolved-authority
score, so nothing else had to change, and `safe_score()` adds a `SAFE AUTHORITY GATE` note to the affected results naming the Safe
and the reason.

- **A read that fails does not degrade.** If the module list or the singleton cannot be read, the score is left as computed and
  a note says it was not confirmed. A transient RPC failure must not push a floor score on-chain.
- **Analyzed modules pass.** The five recorded here (Chainlink's Confirmed Transaction Module, Arbitrum's UpgradeExecutor,
  Radiant's two Hypernative pause modules, EthenaSafeGuard) and the Chainlink Safe's odd singleton change nothing. A module that can
  act as the Safe by design (the UpgradeExecutor) is accepted with its power disclosed, not scored.
- **Lifting a block is an analysis, not a switch.** Add the module or singleton to `safe_modules.py` with what was found and when;
  the sweep (`scripts/check_safe_modules_guards.py`) fails until someone has.
- **Owner-only tools skip the gate** (`check_modules=False`): the cross-ecosystem sweep and the modules sweep must still see a
  gated Safe's signers.
- Verified live on 2026-09-21: with the analyses present the Chainlink Safe scores 65/85/0 (52); with its module removed from the
  table it scores 20/0/0 (8) with the gate note; with only its singleton removed, the same. The other five EVM ecosystems'
  drift checks show no Safe gated by accident.

## Not on-chain yet

Scorer output only, and today it changes nothing on-chain: every Safe currently in the registry is clean or analyzed.
