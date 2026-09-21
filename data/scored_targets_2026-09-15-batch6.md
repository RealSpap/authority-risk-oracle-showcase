# Batch 6 -- 2026-09-15

Two new targets (Pendle V2, Curve DEX) plus one revised target (Spark Savings
USDG, first pushed in batch3 with an explicitly unresolved admin-role
controller). Pushed on-chain via `scripts/update_scores.py`, tx
`0x7ad12522933f6ea821ef44689fa4ab0a0b33811506710d8dbc5851da650fb15a`, block
120105215, chain 46630 (Robinhood Chain Testnet), confirmed `success`.
Independently re-read back from `getScore()` after confirmation rather than
trusted from the push script's own printed output. `trackedTargetsCount()`
went from 32 to 34.

Source addresses for Pendle V2 and Curve DEX came from a background research
agent's report (2+ sources + on-chain bytecode check per its own methodology);
every number below is this pass's own direct `eth_call`, not the agent's
claim taken at face value.

## Spark Savings USDG (spUSDG) -- REVISED, 22 -> 32

`0xde770c84FE66E063336b31737cFE9790f18c4087`

**What batch3 left open**: `DEFAULT_ADMIN_ROLE` on this target is held by
`0x826aeaeee9233fa8ba199518dd8621a5962b1d02`, an 8,113-byte contract with
`queue`/`execute`-shaped selectors (BridgeExecutor pattern). Its own
controlling party "was not identified this pass" -- pushed anyway, at 22/100,
explicitly flagged lower-confidence.

**What this pass resolved**:

1. Replayed every `RoleGranted`/`RoleRevoked` event on the executor from
   genesis (topic hashes computed via `Web3.keccak`, not assumed). Result:
   3 grants, 1 revoke, all at blocks 27727-27859 (right at deploy time):
   - `DEFAULT_ADMIN_ROLE` (`0x00...00`): briefly held by
     `0xb328bd52b61768dd525cf209ab6c1ac688dcc547` (deployer), revoked block
     27859; currently held by the executor itself
     (`0x826aeaeee9233fa8ba199518dd8621a5962b1d02`) -- **self-administering**.
   - An unnamed role (`0x85af328ca8dd848a128ca6b89dd0d76e6255ddd3da76b6fde4e67309c27f780a`
     -- checked against and ruled out `GUARDIAN_ROLE`, `PROPOSER_ROLE`,
     `EXECUTOR_ROLE`, `OWNER_ROLE`, `TIMELOCK_ADMIN_ROLE`, `CANCELLER_ROLE`,
     `SPARK_PROXY_ROLE`, `GOVERNANCE_ROLE` -- name not identified) is held by
     `0xc12B1e59c5E337d5Acd2b4f0A9a27d9E5D7387E8`, a small (830-byte) contract.
   - Scan gap, disclosed: chunks in block range 21,450,001-23,000,000 all
     429'd (rate-limited) on `https://rpc.mainnet.chain.robinhood.com`; every
     real role change found sits at blocks 27727-27859, far below that range,
     so it's unlikely to matter, but it is a real, unaddressed gap -- not
     silently treated as a complete scan.

2. `0xc12B1e59c5E337d5Acd2b4f0A9a27d9E5D7387E8` is **not** a Gnosis Safe --
   `getOwners()` reverts with a custom error string,
   `"ArbitrumReceiver/invalid-l1Authority"`, naming its own pattern.
   `l1Authority()` returns `0x3300f198988e4C9C63F75dF86De36421f06af8c4`.

3. `0x3300f198988e4C9C63F75dF86De36421f06af8c4` is a real, 2,085-byte contract
   **on Ethereum mainnet** (checked via `https://ethereum-rpc.publicnode.com`).
   Its verified Etherscan source name is **"SubProxy"** -- a real Sky/MakerDAO
   cross-domain-governance contract type. `owner()`, `authority()`, `wards()`,
   `pause()` all revert -- its own further upstream controller is **not**
   resolved this pass. Left open, not guessed at.

4. `executor.delay()` = **0**. `executor.gracePeriod()` = 604800 (7 days).
   Confirmed, new finding: whatever action this executor gates can be queued
   and executed with **zero** delay.

**Why the score moved up, not down** (a live correction to what I told Spap
mid-session): resolving an unknown toward "worst case" is not automatically
what happened here. The admin-role holder is not a bare EOA and not an
anonymous unresolved contract -- it resolves to a real, identifiable,
mature Sky/MakerDAO governance pattern on Ethereum mainnet. That is a
materially better finding on the *adminKey* dimension than batch3's genuine
unknown, even though the local L2 `delay()=0` is a real, unchanged (now
confirmed rather than assumed) weakness on the *timelock* dimension.
`adminKeyScore` 35->50, `multisigScore` 10->30 (real chain, still not a
Safe, so capped well below an actual multisig), `timelockScore` 15->10
(confirmed 0, not just suspected). Net composite: 22 -> 32.

**Still open**: SubProxy's own upstream controller; the unnamed role's exact
purpose/name; the rate-limited block-range gap in the event scan.

## Pendle V2

Canonical target address: `MarketFactoryV6` `0x544BF81c855AE84c1e8b65d5E38770898D01EeE2`
(covers the market-creation authority; the two ProxyAdmins below gate every
contract *upgrade* across the same deployment and are traced under the same
score rather than pushed as separate targets).

- `ProxyAdmin` `0xA28c08f165116587D4F3E708743B4dEe155c5E64` ->
  `owner()` = `0x7877AdFaDEd756f3248a0EBfe8Ac2E2eF87b75Ac`, confirmed a real
  **3-of-5 Safe** (`getOwners()`/`getThreshold()` both resolve; owners:
  `0x231FC5b039d66BA234CB90357082Bf16Be79B17c`,
  `0xF517364727Fcc764D58DdF4e53280874A4d0c476`,
  `0x9Ce6De7ec862e25a515AA0D8EcFbBBb2DaA8E0fb`,
  `0x38ab4A7Dea2753757F29fe6d10280Df2C42abe27`,
  `0x7BD456937104Ca5eFfFBD895ccbba52421021C29`).
- `devProxyAdmin` `0xD37eB2E6DE40a33ba68BaD94427723b66c954EA9` ->
  `owner()` = `0xE6F0489ED91dc27f40f9dbe8f81fccbFC16b9cb1`, confirmed a real
  **3-of-6 Safe** (owners: `0xa905EcCcA95c98A42D9a00025c759FC3903451B1`,
  `0xEfd36B57d7fC077088D04c3c712fb8958Fe7f6db`,
  `0x806c8c2D35f32849Cd71A075E2Af2826bdc5987B`,
  `0xE397e61707be78f46BFB7884155C79C0e6af5C13`,
  `0xe81B325766d7A271486Ae2d7D60d7B57386Ba9e7`,
  `0x231FC5b039d66BA234CB90357082Bf16Be79B17c`).
- `MarketFactoryV6.owner()` = `0x2aD631F72fB16d91c4953A7f4260A97C2fE2f31e`
  (225 bytes, not a Safe -- `getOwners()` reverts; its own `owner()` also
  reverts). **Not traced further this pass** -- disclosed as open, not
  folded silently into the ProxyAdmin scores.

No `TimelockController` found gating either ProxyAdmin or MarketFactoryV6 --
`timelockScore = 0`. Two real, independently-composed Safes is the best
authority shape found for a non-Morpho protocol this batch; the unresolved
MarketFactoryV6 owner and the total absence of any delay are what cap the
composite at 42 rather than higher.

## Curve DEX (StableSwap-NG Factory + fee-receiver)

Canonical target address: `0x8271e06E5887FE5ba05234f5315c19f3Ec90E8aD`
(StableSwap-NG Factory).

- `StableSwapNGFactory.admin()` = `0xabc336d4C71ad275695744d32DdB1d8266Db1cbF`
- `x-gov vault (fee-receiver)` `0x193110Ce1542d7371e1515BD6A2E470fDefc310D`
  -> `owner()` = **the same** `0xabc336d4C71ad275695744d32DdB1d8266Db1cbF`
- `eth_getCode(0xabc336d4C71ad275695744d32DdB1d8266Db1cbF)` = `0x` (0 bytes)
  -- a confirmed **bare EOA**.

One key controls both the AMM's pool-creation/parameter authority and its
protocol-fee routing. Same worst-case shape as this project's earlier
Uniswap vanity-EOA finding (one EOA controlling multiple protocol surfaces),
independently found here rather than assumed from that precedent.

**Confidence caveat, stated plainly**: only checked against the single
official Robinhood Chain mainnet RPC (`https://rpc.mainnet.chain.robinhood.com`).
A second-RPC cross-check attempt against
`gateway.tenderly.co/public/robinhood_chain_mainnet` 404'd -- no working
second RPC found yet for this specific address. Flagged as single-source
rather than silently presented as this project's usual 2-RPC-confirmed
standard.

## Falsification notes

- Spark Savings: a different value at `executor.delay()` on a second RPC, a
  different `l1Authority()` return, or a different verified source name at
  `0x3300f198988e4C9C63F75dF86De36421f06af8c4` would invalidate the chain
  above.
- Pendle V2: a different owner/threshold on either ProxyAdmin, or discovery
  that MarketFactoryV6's owner resolves to one of the same two Safes, would
  change the score.
- Curve DEX: finding a second, disagreeing RPC for
  `0xabc336d4C71ad275695744d32DdB1d8266Db1cbF`'s bytecode would downgrade this
  from a confirmed bare-EOA finding to an open question.

## Not yet attempted this batch

PancakeSwap AMM V3, SushiSwap V3, Symbiosis, STRATO Bridge -- addresses in
hand from the same research agent's report, authority structure not yet
probed.
