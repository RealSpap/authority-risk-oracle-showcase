# Bridge2 (Hyperliquid's Arbitrum bridge), re-read 2026-09-26: what is new against the 19/09 work (investigation, nothing scored)

**Already covered, and scored.** The Hyperliquid oracle tracks this contract as "Hyperliquid legacy USDC bridge (Bridge2, Arbitrum One)" (`chains/hyperliquid/scripts/scoring_build_2026_09_18.py::score_bridge2`: 3-of-4 equal-weight hot and cold sets,
admin 65, multisig 59, timelock 15 for the 200-second dispute window with 2 of 5 lockers able to pause) and `chains/hyperliquid/data/finding_2026-09-19-section6-open-questions.md` decoded the same validator sets and showed zero overlap with the 27 active L1 validators.
I re-derived all of it before finding that out (I picked the contract from the TVL-coverage list, where the name match had listed it as untracked; it is not): the result agrees with the existing note on every point of overlap. No score changes.
This note keeps only what the earlier work did not state.

## What is new

- **Balance today: $581.9M USDC** in the contract (581,921,222 and 581,920,697 on two Arbitrum RPCs a few blocks apart); the scorer's note says "$544M+". The docs cited there call the bridge deprecated in favor of Circle CCTP and under 10% of HyperCore USDC (mitigating, and worth remembering next to this number).
- **The five lockers are named**, replayed from `ModifiedLocker` logs and matched to live `lockers()`: the four hot validators (`0xEF2364dB...`, `0xda6816df...`, `0x58E1b0E6...`, `0x26329403...`) plus `0xf9d2282A...` (EOA, 700 transactions). The five finalizers are the same five addresses.
  In the source, adding a locker or finalizer needs the hot set, removing one needs the cold set.
- **The brake is not independent of the signers.** The timelock score of 15 counts the lockers as protection during the 200-second window; four of the five lockers are the hot keys that sign withdrawals. If three hot keys act together, the pause still has the fourth hot key and `0xf9d2282A...`,
  exactly the 2 votes needed; if the fifth locker is one of the colluders, or the one honest hot key or the fifth locker does not respond within the 200 seconds, it does not. This does not overturn the 15; it is the condition under which it holds. The cold set (3 of 4) is a second brake: `invalidateWithdrawals` (by message hash) and `changeDisputePeriodSeconds` (no minimum in the code).
- **Key activity**: each hot key has sent about 841,000 transactions on Arbitrum (automated, online signers); three of four cold keys have never sent one; the fifth locker has sent 700. On Ethereum L1 all nine have sent 0 or 1.
- **The two hashes were recomputed** locally (`keccak256(abi.encode(validators, powers, epoch))`) from the decoded calldata and match the live hot and cold checkpoints.

## A correction to my own first version of this note

It cited tx `0x62a66b84...` as an `updateValidatorSet` sent by a hot key. The transaction that set the live state is that one, **an `emergencyUnlock`** (the 19/09 note already corrected the same wording). What I had decoded was the earlier `RequestedValidatorSetUpdate`
transaction (`0x336a0255...`, block 399,538,350, an `updateValidatorSet` request carrying the identical sets, 1,564 blocks before the unlock). The sets, hashes and conclusions are identical either way.

## Verification

`Bridge2` ABI and source from `arbitrum.blockscout.com`; live reads by `eth_call` on `arbitrum-one-rpc.publicnode.com` and `arb1.arbitrum.io/rpc` (`nValidators`, `totalValidatorPower`, `lockerThreshold`, `disputePeriodSeconds`, `paused`, `epoch`, the two hashes, `lockers`, `finalizers`, USDC `balanceOf`); lockers and finalizers from a Blockscout `getLogs` replay matched to the live mappings; hashes with `eth_abi`.
