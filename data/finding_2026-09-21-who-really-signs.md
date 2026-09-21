# Who really signs the registered root Safes (2026-09-21)

`safe_owners_and_threshold` returns a list of owner addresses and a threshold, and every scorer and the cross-ecosystem overlap
check treated each owner as one independent key. Some owners are not keys. This pass resolves every registered root Safe's
signers down to the EOAs behind them (`scripts/check_nested_signers.py`, library `scripts/lib/nested_signers.py`).

## What the signers are

74 registered Safe addresses on 7 ecosystems, 405 distinct signer addresses (per ecosystem):

| Kind | Count | Note |
|---|---|---|
| Plain EOA | 376 | 193 of them have never sent a transaction (nonce 0). Not treated as a signal: a Safe owner signs off-chain and someone else submits, so a hardware or cold signer normally reads nonce 0. |
| Nested Safe | 27 | Each a Safe that is itself an owner. 17 of the 73 Safes have at least one non-EOA seat. |
| Other contract | 1 | EigenLayer's TimelockController, an owner of its 1-of-2 executor Safe; already traced and scored. |
| EOA delegated through EIP-7702 | 1 | Monad, one of the four signers of Echo's eBTC admin Safe (3-of-4). |

## The four results

1. **Effective key count.** Counting a nested Safe as what its own quorum costs, the fewest EOA keys that reach quorum equals the
   top-level threshold for 15 of the 17 Safes and is **higher** for two (Monad Euler security council, 2-of-3 over three nested
   Safes: 4 keys; Robinhood Chain Grove x Steakhouse, 2-of-2 over one EOA and one nested 2-of-7: 3 keys). No committee is weaker
   than its threshold says. The Aave protocol guardian (4-of-7, present on 5 chains) has three seats that are nested 1-of-3
   Safes, so it costs 4 keys but 13 distinct keys can contribute to it; the dispersion term of the multisig formula treats those
   nine extra keys as strength, when for a 1-of-3 seat each extra owner is one more way to fill the seat.
2. **The EIP-7702 signer is MetaMask's delegator.** `0xFA65E764...A496` delegates to `0x63c0c19a...E32B`, a Sourcify exact
   match on Ethereum mainnet for `EIP7702StatelessDeleGator` (MetaMask Delegation Framework). The Monad copy differs from the
   verified one in 33 bytes: the chain id constant (1 vs 143) and the EIP-712 domain separator. The account keeps its own key as
   the signing authority and gains the ability to redeem delegations it signed, so no new signer appears; the added exposure is a
   signed delegation redeemed by someone else. Recorded, not scored. The Echo scorer now says so in a note.
3. **The nested Safes are clean.** All 27 (per ecosystem) have no module, no guard and a published singleton. The authority gate
   reads only the Safe it resolves, so this is checked by the sweep, and the sweep fails on an unknown one.
4. **13 committee pairs are linked only through nested owners.** Expanding nested Safes to their owners shows shared keys the
   first-level check could not: Aave Horizon's two Safes with the Aave protocol guardian on every chain (7 shared keys), Euler's
   security council with its DAO and pause-guardian Safes on Monad and Plasma (6), Grove x Steakhouse with the Steakhouse
   committee on Robinhood Chain (7), and Monad's Morpho curator and owner Safes with Grove x Steakhouse (6 and 5). Twelve of the
   thirteen are inside one team or protocol; the cross-ecosystem one is already flagged at 80. **No score changes**: each of
   these targets already reads 80 or has no role that the linked committee could add.

One precision on an earlier finding: Compound V3's pause-guardian committee is "identical" at the first level (nine owners, one of
them a nested Safe at the same address `0x55bea483...` on Ethereum, Arbitrum and Base), but that nested Safe is 2-of-6 on Arbitrum
and Base and 2-of-5 on Ethereum. The keys that can act are not identical across the three chains.

## What this does not say

- The effective count is an upper bound on the true minimum (overlap between seats is ignored) and assumes an unresolved contract
  signer costs one key, the weakest reading.
- Nothing here checks a signer's own key hygiene, or whether two seats are really the same person.
- Only registered Safes are swept; a Safe a scorer discovers on its own is not.
