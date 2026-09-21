# Ethereum L1 -- deploy_testnet re-check, 2026-09-18

## Why this run does not repeat the fork rehearsal a third time

Two full dress rehearsals of the deploy pipeline on a local anvil fork of
Sepolia already exist and are committed:
[`deploy_rehearsal_2026-09-17.md`](deploy_rehearsal_2026-09-17.md) (morning,
4-target scorer) and
[`deploy_rehearsal_2026-09-17-run2.md`](deploy_rehearsal_2026-09-17-run2.md)
(evening, 9-target scorer, current state). Before doing anything else, this
run checked whether either of the two things that justified run 2 (a changed
scorer, or a funded deployer) had happened again since:

```bash
git log -1 --format=%H -- chains/ethereum-l1
# -> a58cde8cf93fa8ce5cc8e4892c19c15c0afcb636 (2026-09-17 20:24:33 +0200,
#    the evening run 2 commit -- no commit has touched chains/ethereum-l1
#    since)
```

`chains/ethereum-l1/scorers.py`, `script/Deploy.s.sol` and
`update_scores_ethereum_l1.py` are byte-identical to run 2. Re-running the
exact same anvil-fork rehearsal against unchanged inputs would reproduce
run 2's result with no new information -- so this run instead does two
things a fork rehearsal does not already prove: re-check the real Sepolia
balance (funding is the only real blocker), and re-derive the 9 scores live
against Ethereum L1 mainnet *today* (mainnet state itself can drift day to
day even when the scorer code does not).

## Real Sepolia balance -- still 0 ETH

```bash
cast balance 0xA08a76457b758aFF9702dBf5b870679E1232B715 --rpc-url https://ethereum-sepolia-rpc.publicnode.com
# -> 0
cast balance 0xA08a76457b758aFF9702dBf5b870679E1232B715 --rpc-url https://sepolia.gateway.tenderly.co
# -> 0
```

Unchanged since 2026-09-16. No faucet was used or requested (agent policy --
Spap funds manually per `keys/evm-testnet-shared.json`'s own
`faucets_to_use_manually_if_funding_needed` field). This same shared
throwaway key also blocks Arbitrum Sepolia and Base Sepolia deployment for
those two other ecosystems in this pipeline -- funding it once would unblock
all three at once.

## Live mainnet re-derivation -- scores unchanged

```bash
python3 chains/ethereum-l1/deploy/update_scores_ethereum_l1.py --dry-run
```

Read RPC chain ID confirmed `1` (Ethereum L1 mainnet). All 9 composites
re-derived live today match run 2's committed record exactly:

| Target | Composite (run 2, 09-17 evening) | Composite (today, 09-18) | Match |
|---|---|---|---|
| Uniswap V3 Factory | 85 | 85 | yes |
| Aave V3 Ethereum Pool | 78 | 78 | yes |
| MakerDAO / Sky (MCD_PAUSE) | 81 | 81 | yes |
| Ethena EthenaMinting | 52 | 52 | yes |
| USDtb | 2 | 2 | yes |
| USDtb PSM | 73 | 73 | yes |
| USDe OFTAdapter | 57 | 57 | yes |
| sUSDe OFTAdapter | 57 | 57 | yes |
| ENA OFTAdapter | 57 | 57 | yes |

Encoded calldata selector confirmed `0x5fb3feaf` (unchanged, 9-target ABI
shape). No connection was opened to any Sepolia RPC by this script
(`--dry-run`), no `PRIVATE_KEY` was read, nothing was sent.

## What this closes and does not close

- Closes: re-confirms, on 2026-09-18, that (a) the only real blocker to a
  real Sepolia deployment is deployer funding, not stale code or stale
  scores, and (b) the 9 scores that would be pushed once deployed are still
  accurate as of today, re-derived fresh from live mainnet rather than
  assumed from yesterday's record.
- Does not close: the real Sepolia deployment itself. Still blocked --
  `0xA08a76457b758aFF9702dBf5b870679E1232B715` remains at 0 ETH on real
  Sepolia. No faucet use, no funds moved, no mainnet transaction of any
  kind (Sepolia deploy pipeline is proven and ready; nothing further to
  rehearse on the fork until either the scorer changes again or the
  deployer gets funded).

## Recommended transition

`deploy_testnet -> deploy_testnet` (maintained, not advanced) -- same
recommendation as both 2026-09-17 runs, for the same reason: no real deploy
happened because the deployer is still unfunded.
