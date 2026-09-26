# Authority index ("what can this key touch?") and a first EIP-7702 signer scan

2026-09-26. New read-only tool `scripts/who_controls.py` (+ `scripts/lib/authority_index.py`, 11 unit
tests). It reuses the live resolution `check_cross_ecosystem_overlap.py` already does for every
registry group (110 groups, 8 EVM ecosystems), extracted into `resolve_all()` so both scripts share
one code path, and inverts it. Disclosed only: no score, no scorer, no on-chain push reads any of it.

## Why it is a gap, not decoration

Every public risk product answers the forward question (protocol X: how risky is its admin?). Nobody
publishes the inverse, which is what an incident responder, a Safe signer or a listing committee
actually asks the moment a key is suspected: **which protocols does this one address touch?**

    python3 scripts/who_controls.py 0xADDRESS ...     # blast radius (also follows the L1 -> L2 alias)
    python3 scripts/who_controls.py --top 20          # most-connected signers
    python3 scripts/who_controls.py --code-scan       # EOA / EIP-7702 / contract for every root signer
    python3 scripts/who_controls.py --write-index P   # full JSON (snapshot: data/authority_index_2026-09-26.json)

## Live result (2026-09-26, 0 group unresolved; 110 groups after adding the missing Tempo Morpho Blue Safe and the 10 feed-admin Safes, see below)

- 110 groups, **457 distinct addresses** indexed, **372 are signers of at least one group**.
- Distribution by ecosystems reached: 281 signers in 1 ecosystem, 38 in 2, 15 in 3, 12 in 4 (Morpho Association's 9 plus 3 RedStone feed-admin signers), **26 in 5** (the 17 Aave guardians plus the 9 Chainlink feed-owner signers).
- The 17 five-ecosystem signers are the Aave guardian committees (Protocol Guardian and Governance
  Guardian Safes) shared across Ethereum L1, Arbitrum, Base, Monad and Plasma. Already known
  (`data/finding_2026-09-25-aave-guardian-18-chains.md`); the index re-derives it independently, which is the point.
- Next tier: 4 ecosystems, Morpho Blue owner committee (L1/Base/Robinhood/Tempo, 9 signers, 5-of-9
  Safes); 3 ecosystems each, Pendle (Arbitrum/Plasma/Robinhood) and Compound V3 (L1/Arbitrum/Base). 2 ecosystems: Ethena (L1/Plasma, 10 signers), Fluid
  (Arbitrum/Plasma), Euler DAO (Monad/Plasma), Steakhouse curators (Monad/Robinhood), Curve.
  All of these were already known individually; none is new. What is new is having them in one
  queryable place.
- **L1 -> L2 alias handling matters**: the Uniswap timelock `0x1a9C...35BC` and the address
  `0x2BAD...46CD` on Arbitrum are the same actor (alias offset `0x1111...1111`), but a plain address
  index treats them as two strangers. `blast_radius()` follows the alias both ways (tested), so a
  query on either returns all 5 ecosystems.

## EIP-7702 signer scan (first ever, 580 (chain, signer) pairs, 0 unread)

`{'eoa': 538, 'eip7702': 3, 'contract': 39}`. Why it matters: a Safe treats a 65-byte ECDSA
signature from an owner as a plain key, but a signature of type v=0 is validated by calling
`isValidSignature` on the owner address, and an EOA that has delegated (EIP-7702) answers with
whatever its delegate implements. A delegated owner is therefore not necessarily "one key".

| Chain | Signer | Group | Delegate (code identical? name) |
|---|---|---|---|
| Robinhood | `0x58CA1eaE...7c9` | `saffron_vault_factory` (hand-listed single EOA) | `0x63c0c19a...E32B`: Blockscout Ethereum names it `EIP7702StatelessDeleGator` (MetaMask). Same address and size (11,185 B) on Monad and Robinhood but the code hash DIFFERS per chain, so it is NOT asserted to be the same build there |
| Monad | `0xFA65E764...A496` | `echo_ebtc_admin` (1 of 4 owners of a 3-of-4 Safe `0x401a3312...b1c5`, read live) | same delegate as above |
| Robinhood | `0x35985665...36a5` | `fables` (hand-listed single EOA) | `0x5A7FC113...6f6d`: Blockscout Ethereum names it `AmbireAccount7702`; byte-identical on L1, Monad and Robinhood |

Follow-up read on the two admin EOAs, because Ambire's 7702 account lets any address holding a
non-zero `privileges(key)` authorize `execute` on the account's behalf, which would mean n > 1 behind
what the scorer counts as k=1, n=1:

- `fables` EOA: `privileges(itself)` = 2 (its own key), **zero events emitted from its address over the
  whole chain history** (full-range `eth_getLogs`, positive control on 3 Robinhood Safes returned
  36/50/32 logs so the RPC does return full-range results), hence no `LogPrivilegeChanged`, no extra
  privileged key added. The k=1, n=1 assumption **holds today** for this EOA.
- `saffron_vault_factory` EOA: MetaMask's stateless delegator has no on-chain key list (authority is
  extended by off-chain signed delegations, not enumerable from the chain); the address has emitted
  zero events. Nothing on chain contradicts k=1, n=1, but off-chain delegations cannot be ruled out.
- 39 (chain, signer) pairs are contracts (nested Safes, timelocks or other), not classified further
  here; `check_nested_signers.py` is the tool that resolves nested signers.
- `echo_ebtc_admin`: the delegated owner is 1 of 4 in a 3-of-4 Safe, so on its own it cannot move the
  Safe (threshold 3); it still counts toward the threshold, which is why the delegate matters.

## Registry correction found while building it

The backlog item "[backlog note]" was still partly true: Tempo's Morpho Blue core
owner Safe `0x645890a0...0fbbc` was missing from `TEMPO_GROUPS`, although the Tempo scorer already
folds its overlap into crossExposureScore. Re-read live 2026-09-26: 5-of-9 with exactly the 9 signers
of the L1/Base/Robinhood Morpho Blue owner Safes (set equality against the dated snapshot). Added as
group `morpho_blue` (registry only, no score reads the registry). The card's other items (GMX,
Pendle/Fluid Arbitrum, Slipstream Base) were already in the registry; its SUBMISSION.md/README
per-ecosystem totals are a separate doc refresh, not done here.

## Feed-admin groups added later the same day

The Morpho market oracle rerun (`finding_2026-09-26-morpho-market-oracle-authority-rerun.md`) added 10 groups for the Safes that own
price-feed proxies (Chainlink 4-of-9 on 5 chains, RedStone-built 2-of-3 on 4, a 1-of-1 on 2). The index therefore now ranks the
Chainlink signers next to the Aave guardians, and the RedStone signers with the Morpho committee.

Later the same day two Midas groups (default admin, feed posters) and the 2 feed-admin EOAs brought the registry to 115 groups and 469 indexed addresses
(code scan 582 pairs, same 3 EIP-7702 signers); the counts above are those of the earlier read, the snapshot file is the latest.

## What this is and isn't

Pure disclosure and tooling. No target, no scorer, no score change. Snapshot and lookup are limited to
what the 99 hand-curated registry groups contain (8 EVM ecosystems; Solana and Zcash key formats are
not bridged; Hyperliquid covers its 4 HyperEVM Safe-rooted targets). "Not found" therefore means "not
in a tracked group", never "safe". The Aave-dominated top of the ranking reflects the registry's
composition, not a claim that Aave is the riskiest.

## Verification

`python3 scripts/who_controls.py --top 20 --code-scan --write-index ...` against 8 public RPCs, exit 0,
0 INCOMPLETE groups, 0 unread. `python3 -m unittest` on `test_authority_index.py` (11) and
`test_cross_ecosystem_overlap.py` (35) green after extracting `resolve_all()` from `check_cross_ecosystem_overlap.py`.
No key read, nothing sent.
