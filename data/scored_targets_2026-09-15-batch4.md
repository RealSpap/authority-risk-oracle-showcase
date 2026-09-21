# Scored targets - batch 4, 2026-09-15

Eleven more scores pushed (tx
[`0x1836bb5e...`](https://explorer.testnet.chain.robinhood.com/tx/0x1836bb5e4928bb678e03d0cbd8abd1f6d6902189d11a17567abca13c6e83af16)),
bringing the total to **28 targets**. This batch reaches past every dApp already
scored to the one authority every one of them ultimately sits on top of: who
controls Robinhood Chain itself.

## Robinhood Chain's own L1 rollup upgrade authority - 57/100 (the best-governed target on this project, still not a real protection)

Robinhood Chain is an Arbitrum Orbit rollup. Its upgrade authority lives on
**Ethereum mainnet**, not on the L2 itself -- a different chain than every other
target scored so far, queried via `ethereum-rpc.publicnode.com` and `eth.drpc.org`.
Six core L1 contracts share the identical authority chain and were scored
identically: `Rollup` (`0x23A19d23e89166adedbDcB432518AB01e4272D94`, `chainId()`
independently confirmed = 4663, i.e. genuinely Robinhood Chain's own rollup, not a
lookalike), `SequencerInbox`, `CoreProxyAdmin`, `DelayedInbox`, `Bridge`, `Outbox`.

**The chain**: `Rollup.owner()` and `CoreProxyAdmin.owner()` both resolve to
`0x552603b4bc1f5E896AF2854548D6380f45f1B4bf`, an Arbitrum-standard
`UpgradeExecutor` proxy (confirmed via its `EXECUTOR_ROLE()` getter matching the
correct `keccak256("EXECUTOR_ROLE")` hash, independently recomputed rather than
assumed). `Bridge`/`SequencerInbox`/`DelayedInbox`/`Outbox` are all
`TransparentUpgradeableProxy` contracts whose `admin()` is `CoreProxyAdmin` --
CoreProxyAdmin's own upgrader is the UpgradeExecutor, whose own upgrader is
CoreProxyAdmin: a closed, standard Orbit governance loop.

**Who actually holds `EXECUTOR_ROLE`** (the power to call `execute()` against any of
the six contracts above), the full grant/revoke history walked from genesis and the
current state re-verified live on 2 independent RPCs:
- A bootstrap deployer EOA held it at launch (2026-04-30), replaced by an interim
  2-of-3 Safe the same day, which itself was fully revoked by 2026-06-12.
- **Today, confirmed via `hasRole()` on 2 independent RPCs**: a real **7-of-8 Gnosis
  Safe** (`0x7ae50886...`, 8 distinct owner addresses, threshold 7 -- independently
  re-confirmed, not taken from the discovery pass) holds `EXECUTOR_ROLE` **directly**.

**The timelock that looks real and isn't currently protecting anything**: a second
`EXECUTOR_ROLE` holder is a proxy pointing at OpenZeppelin's `TimelockControllerUpgradeable`,
`getMinDelay()` independently confirmed = `604800` (exactly 7 days, correctly
parameterized, not a decoy zero like the Ramses finding below). But
**`hasRole(PROPOSER_ROLE, ...)` was checked directly against the 7-of-8 Safe and the
UpgradeExecutor itself, on 2 independent RPCs: both `false`**. Nobody currently holds
the role needed to queue anything through this timelock -- it is not merely unused,
it is presently unusable. The 7-of-8 Safe's own `EXECUTOR_ROLE` bypasses it entirely:
that Safe can call `execute()` on the rollup, the bridge, or the sequencer inbox
**today, with zero delay**, the moment it collects 7 signatures.

**Why this scores 57 -- highest on the whole project, and still a real finding**:
`adminKeyScore=78` (a genuinely mature multisig, evolved off a bootstrap EOA through
two real on-chain rotations -- no bare-EOA exposure anywhere in this chain, unlike
every other target scored) · `multisigScore=75` (7-of-8, an 87.5% threshold, real
signer count) · `timelockScore=10` (a correctly-configured real timelock exists in
the authority graph and could be activated by one governance action -- credited
above zero for that -- but gates nothing today, since the Safe holds direct,
parallel, undelayed authority). **Every dApp already scored on Robinhood Chain
inherits this L1 risk underneath its own governance**, whatever its own score: a
7-of-8 Safe -- **correction, see batch5.md**: the council is publicly named (Robinhood, BitGo, Chainlink Labs, Fireblocks, Offchain Labs, Paxos, Talos), address-level attribution just isn't public -- can rewrite the bridge or
sequencer at will, no on-chain warning window, regardless of how well-governed any
individual dApp on top of it is.

## Uniswap V2 Factory `feeToSetter` (`0x8bcEaA40B9AcdfAedF85AdF4FF01F5Ad6517937f`) - 2/100

Confirmed live: `feeToSetter()` returns `0x2BAD8182C09F50c8318d769245beA52C32Be46CD` --
byte-for-byte the same vanity-lookalike bare EOA already found controlling Uniswap
v3 Factory, v4 PoolManager, and the UniswapX reactor. **This is a fourth surface on
the exact same private key**: v2 + v3 + v4 + UniswapX order settlement, one key,
end to end, across every Uniswap deployment on this chain.

## Ramses CL V2 - Factory, PoolDeployer, AccessHub, AccessHubProxyAdmin - 8/100

A real DEX with $6.3M chain TVL, governed through a centralized `AccessHub`
(`0x83341F891f898cb5E0cacC8a70501BBa83d9CecF`) rather than per-contract `Ownable` --
confirmed by `owner()` reverting on the Factory/PoolDeployer and AccessHub's
`AccessControl`-shaped interface responding instead. `hasRole(DEFAULT_ADMIN_ROLE, ·)`
is true for both `RamsesTimelock` and an address labeled "Ramses Team Multisig"
(`0x20D630cF1f5628285BfB91DfaC8C89eB9087BE1A`) -- traced one hop further rather than
trusting the label: `getOwners()` on that "multisig" returns **exactly one owner**,
`getThreshold()` is **1**. A Safe wrapper around a single private key, that sole
signer confirmed a bare EOA -- the same pattern already flagged on the NetNet Credit
Morpho vault. `AccessHubProxyAdmin` (the contract that can rewrite AccessHub's own
bytecode) traces to the identical 1-of-1 Safe.

**The sharper finding**: `RamsesTimelock.getMinDelay()` returns **0**. A real,
deployed timelock-shaped contract whose delay is deliberately set to zero --
arguably worse than having no timelock at all, since it creates the appearance of a
governance safeguard with none of the substance. Scored `adminKeyScore=15`,
`multisigScore=5`, `timelockScore=0` -- composite 8, tying this chain's worst
Morpho vault, on a DEX doing real volume.

## Honestly unresolved this pass -- no score forced

**Ekubo Core** (`0x00000000000014aA86C5d3c41765bb24e11bd701`, confirmed live,
$1.92M TVL): `owner()`/`admin()`/three other plausible selectors all revert. Ekubo
uses a non-standard authority interface; resolving it needs Ekubo's real ABI, not
selector guessing. **Longbow** ($3.83M TVL, architecturally another Morpho Vault V2
curator per Robinhood's own blog): no specific vault address was found this pass --
Robinhood Chain's own Blockscout sits behind a bot-detection challenge this project
will not attempt to bypass. **PancakeSwap AMM V3, SushiSwap V3, Pendle V2, Symbiosis,
Curve DEX, STRATO Bridge**: real DefiLlama-sourced TVL, no contract address
resolved yet. All six are real candidates for a future pass that starts by finding
addresses, not assumed scores.

## Running total

28 targets scored across 4 batches. The L1 rollup authority (57/100) is now the
best-governed target found anywhere on this project -- ahead of Lighter (54) -- and
it still amounts to "a real timelock exists but gates nothing today." Range across
all 28: 1/100 (Robinhood's own stock-token beacon) to 57/100 (Robinhood Chain's own
rollup authority). The chain's two most foundational things -- its flagship product
and the chain itself -- are its own best and (second-)worst-scored findings.
