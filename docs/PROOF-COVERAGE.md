# Which proxy patterns and authority paths the readers cover

*Written on 30 October 2026, from `watch/API.md`, `scripts/second_opinion.py` and `METHODOLOGY.md`. "The reader" is the independent reader of the Watch (`second_opinion.json`); "the scorer" is the code that computes the published scores. A pattern that is not in the table is not covered. Not covered means: the Watch does not say anything about it, and its silence is not a finding.*

## Proxy and upgrade patterns

| Pattern | Who can change it: read by the reader | An upgrade is seen by the Watch | Limit |
|---|---|---|---|
| Transparent proxy, EIP-1967 admin slot | the admin slot, then the owner of the ProxyAdmin it names | yes: the EIP-1967 implementation slot is fingerprinted at each run | |
| Transparent proxy whose admin is fixed in its bytecode (the admin slot reads zero) | read from the code, only when it is recognised by its own revert text plus `upgradeTo` and exactly one address-shaped constant is left | yes, by the implementation slot | |
| Beacon proxy (EIP-1967 beacon slot, no admin slot) | the owner of the beacon; the target's own `owner()` is forwarded to the implementation and is not used | yes, through the beacon's `implementation()` | |
| Contract with `owner()` or `admin()`, no proxy | `owner()`, else `admin()` | no implementation to watch | |
| `AccessControl` (ERC-165 id `0x7965db0b`) with enumerable `DEFAULT_ADMIN_ROLE` | the first holder of the role (the field says "member 1 of n") | by the implementation slot, if it is a proxy | the other holders are not compared with the score as of 30 October 2026 |
| `AccessControl` whose holders cannot be listed | nothing: the target is `unreadable`; the holders live in `RoleGranted` events, and a probe asks `hasRole` of known contracts (a yes is proof, absence proves nothing) | by the implementation slot, if it is a proxy | never counted as agreement |
| `AccessManaged` | `authority()`, the AccessManager that holds every role | by the implementation slot, if it is a proxy | the AccessManager's own holders are a separate target |
| Diamond (EIP-2535) | not fingerprinted by the reader | **no**: facet changes are not seen by the Watch | covered only where the private pipeline checks it by name; the Watch files do not say which |
| Token with a Zeppelin-style implementation slot (a FiatToken pattern) | not fingerprinted by the reader | **no** | same |
| Minimal proxies (clones), other custom storage layouts | no handling for upgrade watching is described (METHODOLOGY.md describes one pinned clone walk, for price authority only) | **no** | treat as not covered unless a scorer handles that target by name |
| Holder is an account with an EIP-7702 delegation (`0xef0100` + address) | read as a plain key, `kind: eoa`, `delegated_to` names the code its account runs | | what the delegated code does is not read |
| Arbitrum-stack chains: a holder without code | un-aliased and looked up on Ethereum L1 (`alias_of`) | | |
| Solana program (upgradeable loader) | the upgrade authority in the ProgramData account: plain key, program-derived address, a Squads multisig (vault 0 of a v4 multisig is derived), immutable, or program-owned | yes: the deployment slot in ProgramData moving is an upgrade executed | a program-derived authority that is not the vault 0 of a v4 multisig is reported as such, not resolved |
| Entities with no code on the chain's mainnet (HyperCore's validator set, HIP-3 dexes, an identifier for a rollup's own L1 contracts) | `native`: outside the reach of the reader | | listed, never counted as agreement |

## Where the independent reader is blind

- **Holders of a role.** Only the first holder of an enumerable `DEFAULT_ADMIN_ROLE` is read, and the secondary roles are the seven getters listed in `docs/LIMITS.md`. A role with no getter, or granted in an event the reader does not scan, is not seen.
- **Safe owners and modules.** Signer kinds are read live on the first 20 signers. The nested-signers check (a script run by hand, outside the Watch and the score) opens nested Safes three levels below the Safe it reads; the Watch's reader reads one level of them (kind, threshold and number of owners of each owner), not their own owners. The enabled modules of a Safe are read from one page of up to 50 as of 30 October 2026; beyond that the list is cut without a signal.
- **How a key is kept**, and who the people behind the keys are, are not on the chain. See `docs/LIMITS.md`.
- **Public RPC answers.** A public endpoint answers at the latest block; the span of a reading is a few blocks (`block_start`, `block_end`). One endpoint (Hyperliquid testnet) answers for the latest block whatever block is asked. A read at an old block needs an endpoint with archive state; no test in this repository covers an endpoint without it.
- **Event windows.** The Safe event scan uses a shorter, stated window on a chain that serves only short log ranges (Monad 100 blocks per call; HyperEVM 3 days). The scan of the oracle's own role events gives up a window that is too large to read and records its size (`gap_blocks`); no alert is raised for it as of 30 October 2026.
- **Agreement is not proof.** The reader and the scorer are written by the same author. An agreement between them means that two readings of the same public state match; a disagreement is a finding to review, not a verdict, and is never settled in favour of the higher score.
