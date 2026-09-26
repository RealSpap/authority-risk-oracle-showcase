# Morpho vault controllers: EIP-7702 across 165 vaults, and one timelock the Adpend USDC scorer does not count

2026-09-26. Read-only, disclosed only, no score or scorer changed.

## 1. EIP-7702 among the controllers of 165 Morpho vaults ($6.56B, Ethereum, Base, Robinhood, Monad, Arbitrum)

`chains/ethereum-l1/scripts/sweep_morpho_vault_owners.py` (V1 >= $2M, V2 >= $1M, listed or not; 47 V1 and 118 V2 vaults) already classifies a bare
owner as EOA or EIP-7702-delegated. Its dump was then extended one hop with the `eth_getCode` classification of `who_controls.py`: every signer of every
owner or curator Safe.

- **Bare 7702 owners**: 2 vaults. **`Adpend USDC` (Ethereum V1, $370M, not listed on Morpho's app): owner AND curator are the same EIP-7702-delegated EOA
  `0xf630D85a...`** (delegate `0x63c0c19a...`, MetaMask's `EIP7702StatelessDeleGator` by Ethereum Blockscout; nonce 67), guardian unset. Already a
  tracked, scored target (`score_morpho_adpend_usdc`, with the "not listed, deposit disabled, impaired market" context disclosed there). The second is the
  curator (not owner) of `Metronome msUSD` (V2, $9M, unlisted, owner a 3-of-6 Safe).
- **7702 among Safe signers**: 67 distinct owner or curator Safes (all read), 238 (chain, signer) pairs: 227 EOA, **1 EIP-7702**, 10 contracts. The one
  is `0x80c9aC86...` (same MetaMask delegate), a signer of the 4-of-7 Safe `0xe5e2Baf9...` that governs 9 vaults ($48M: WETH ARM Vault, Yearn OG USDC, Yearn USDC, ...).
- Prevalence is low (1 of 238 here, 3 of 580 in the tracked-group registry): the 7702 risk is real but rare, and every delegate seen so far is MetaMask's
  or Ambire's. A delegated key that is a SINGLE root, as at Adpend, is the case that matters.

## 2. Adpend USDC: the vault's own 14-day timelock is not in the score

`score_morpho_adpend_usdc` notes "a single key holds every V1 role with no independent veto party **and no timelock layer above it**" and sets
timelockScore 0. Live read today: `timelock()` on the vault = **1,209,600 s (14 days)**, the delay on cap increases, guardian and timelock changes. The other
large L1 V1 vaults read the same way: Steakhouse USDT and USDC 7 days (credited `timelock_score = 75` in `_score_steakhouse_l1_vault`, "V1 curator-timelocked
cap changes"), 1337 USDC 0 days (score 0, consistent). So the convention credits a V1 vault-level timelock for Steakhouse and not for Adpend.

**The same convention exists at a lower rate for the case closest to Adpend**: `score_morpho_gauntlet_usdc_prime_base` (and `score_morpho_vault_monad`) credit
`timelock_score = 55` when the delay's only veto party holds the same signers as the proposer ("a real delay whose only veto party is the same signers ... scores
well below one with an independent guardian", 75 with an independent one). A vault with no guardian and owner = curator is at least that case. The vault-level
delay is credited at 55 to 75 wherever it exists with a guardian; Adpend is the one place read here where it exists and is credited 0.

Numbers if the Steakhouse convention were applied as is: composite `(4*5 + 3*0 + 3*75 + 5) // 10 = 25` (75) or `= 19` (55, the same-signers rate) instead of `(4*5 + 0 + 0 + 5) // 10 = 2` on a $370M vault.
Reasons it may still be right to leave it at 0: owner and curator are one key with no guardian (nobody else can veto a pending change), the Steakhouse credit
notes "guardian not independently resolved so not credited the higher band", and the vault is unlisted with deposits disabled and its assets in one impaired
market. Reasons to change it: the delay is real against a compromised key that has to wait 14 days, and the same rule is applied to one family and not another.
This is a calibration decision, so it is left as it is and put to Spap on the board; the note "no timelock layer" is imprecise either way (there is a vault timelock,
there is no external Timelock contract).

## Verification

`python3 chains/ethereum-l1/scripts/sweep_morpho_vault_owners.py --chains 1,8453,4663,143,42161 --dump ...` (165 vaults), then `safe_owners_and_threshold`
(no module gate) and `lib/authority_index.classify_code` on every signer; `timelock()` read by `eth_call` on the L1 vaults above. No key, nothing sent.
