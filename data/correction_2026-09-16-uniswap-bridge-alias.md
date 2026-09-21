# Correction (2026-09-16): Uniswap stack's "vanity-ground bare EOA" was wrong

## What was published, and what was wrong with it

`score_uniswap_v3_factory`, `score_uniswap_v4_poolmanager`, `score_uniswapx_reactor`,
and `score_uniswap_v2_factory_feetosetter` all resolve `owner()`/`feeToSetter()` to
`0x2BAD8182C09F50c8318d769245beA52C32Be46CD`. Since batch 4, this project has
described that address in `scorers.py`, `dashboard/index.html`, and `README.md` as a
"vanity-ground bare EOA" built to resemble Uniswap's real governance address closely
enough to fool anyone skimming a truncated address -- implying a compromised or
maliciously-mined private key with zero real protection.

That characterization is **wrong**.

## What's actually true, re-verified today (not just recalled)

`0x2BAD8182C09F50c8318d769245beA52C32Be46CD` is the **legitimate Arbitrum L1->L2
address alias** of Uniswap's real Ethereum-mainnet Governance Timelock,
`0x1a9C8182C09F50c8318d769245bEA52c32BE35BC`. The Arbitrum canonical-bridge aliasing
formula is deterministic, not a coincidence:

```
alias = (L1_address + 0x1111000000000000000000000000000000001111) mod 2^160
```

Re-derived exactly today:

```python
l1 = int('1a9C8182C09F50c8318d769245bEA52c32BE35BC', 16)
offset = int('1111000000000000000000000000000000001111', 16)
alias = (l1 + offset) % (2**160)
# -> 0x2bad8182c09f50c8318d769245bea52c32be46cd  (matches, case-insensitive)
```

Live bytecode check today (`eth_getCode`, both addresses, 2026-09-16):
- L1 address (`gateway.tenderly.co/public/mainnet`): **real deployed bytecode**
  (a genuine contract, consistent with the Uniswap Governance Timelock).
- L2 alias (`rpc.mainnet.chain.robinhood.com`): **`0x`, no bytecode**.

The empty bytecode at the L2 alias is *expected*, not suspicious: an L1->L2 alias is
a `msg.sender` identity that the Arbitrum canonical bridge assigns to a message when
the L1 contract relays it -- it is never itself the target of a contract deployment,
so `eth_getCode` on it will always return empty, exactly as if it were a bare EOA.
This is precisely why the earlier "vanity-ground bare EOA" read was made -- the
mechanical `is_eoa()` check (no bytecode = true) was never wrong on its own, but the
narrative built on top of it was.

## What this does NOT mean

- It does not mean this authority chain is risk-free. The true authority is
  Uniswap's real Ethereum L1 Governor Bravo + Timelock (UNI-token-holder vote +
  quorum + a real, well-known ~2-day timelock delay), reached via the Arbitrum
  canonical bridge with **no Robinhood-Chain-native control layer of its own**.
  That is a materially different risk shape from "single leaked/vanity-mined
  private key, zero delay, zero DAO process" -- but it is not zero risk either
  (bridge-relay trust, and the fact that this chain inherits Uniswap L1
  governance's decisions with no local override).
- It does not mean the current numeric scores (2/100 composite on all four
  surfaces, driven by `adminKeyScore = 5` because `is_eoa()` returns true) are
  automatically wrong in the "too low" direction -- they might still be
  appropriate, or they might need a dedicated new scoring path for "external L1
  DAO governance reached via a bridge alias" (this project's existing
  `admin_key`/`multisig`/`timelock` three-dimension model was built around
  Gnosis Safes and TimelockControllers, not Governor Bravo). **This has not been
  resolved -- flagged as an open question, not silently patched with a guessed
  number.**

## What changed in this commit

- `scripts/lib/scorers.py`: corrected docstrings on all four Uniswap-stack scorer
  functions (`score_uniswap_v3_factory`, `score_uniswap_v4_poolmanager`,
  `score_uniswapx_reactor`, `score_uniswap_v2_factory_feetosetter`) and their
  runtime `notes.append()` text where it repeated the wrong claim. Also corrected
  a **stale docstring** on `score_curve_dex` that still said "second-RPC
  cross-check attempt 404'd" even though batch 9 had already resolved it (the
  function's own `notes.append()` line and the README were already updated by
  batch 9 -- only the docstring was stale, a `chiffres-perimes`-style gap caught
  while making an unrelated correction, not a new finding of its own).
- `scripts/lib/signer_overlap.py`: added a correcting comment on the
  `uniswap_stack` group entry in `GROUPS` (left in `known_eoa` structurally,
  since the cross-exposure check still needs to treat it as one root identity,
  but flagged as not actually EOA-controlled).
- `dashboard/index.html`: corrected the Uniswap card's summary/detail text.
- `README.md`: corrected the four Uniswap table rows, each marked
  *(rescore pending)* rather than silently left at the old score with the old
  (wrong) justification.
- **No numeric score was changed in this commit.** `compositeScore` for all four
  Uniswap surfaces remains 2/100 on-chain and in the README until a proper
  re-derivation happens -- see "What this does NOT mean" above.

## Open follow-up (not done here)

A dedicated re-scoring pass needs: (1) Uniswap's actual Governor Bravo parameters
(proposal threshold, quorum, voting delay, timelock delay -- publicly documented,
not yet re-verified by this project), (2) a decision on whether/how the existing
3-dimension scoring model should represent "external L1 DAO governance via bridge
alias" as a distinct authority shape, and (3) a check on whether any *other*
Robinhood-Chain-tracked target flagged as a "bare EOA" is actually the same
aliasing pattern rather than a real EOA (Curve's controller was checked today and
ruled OUT via real Arbitrum transaction history -- see the corrected
`score_curve_dex` docstring -- but no other "bare EOA" target has been checked
against this pattern yet).

## RESOLVED 2026-09-17 -- items (1) and (2) closed

Added `scripts/lib/web3_utils.py::arbitrum_l1_l2_alias()` (the alias formula as a
reusable, re-derived-every-run function, not a one-off hand calculation) and
`scripts/lib/scorers.py::_score_uniswap_bridge_alias_root()`, a shared scoring
path for all four Uniswap-stack surfaces. It re-confirms the alias match AND
independently re-derives the L1 Timelock/GovernorBravo live on every run (own
Ethereum-mainnet Web3 instance, exactly the discipline `score_rollup_l1_authority()`
already used in this file) -- re-verified live today: `delay()` = 172,800s (2 days),
`quorumVotes()` = 40,000,000 UNI, both unchanged since the original correction.

Uses the SAME admin_key=80/multisig=100/timelock=75 convention already established
for this identical authority shape elsewhere in this project (`chains/base-ecosystem
/scorers.py`'s `score_uniswap_v3_factory_base()`, reached via OP-stack cross-domain
messaging instead of an Arbitrum alias, and confirmed directly on L1 itself in
`chains/ethereum-l1/scorers.py`'s `score_uniswap_v3_factory()`) -- not a new number
invented for this correction. If the alias stops matching or the L1 re-read fails on
any future run, this degrades to the original bare-EOA-equivalent scoring rather
than silently keeping the higher score.

**All four Uniswap-stack surfaces now score 85/100** (up from 2/100), each
independently re-verified live via `python3` against `rpc.mainnet.chain.robinhood.com`
+ `https://ethereum-rpc.publicnode.com` before being committed. README's target table
updated to match; `dashboard/index.html`'s static score references were already
correct (they read live from the oracle) but its Uniswap card copy is updated in the
same commit as this note.

## RESOLVED 2026-09-17 -- item (3) closed: no other target matches this pattern

Swept every remaining target whose notes mention a bare EOA (`scripts/lib/scorers.py::score_all()`
output, live): Pendle V2's `MarketFactoryV6.owner()`, Lighter Escrow's
`securityCouncilAddress`, Spark Savings USDG's executor, and Ramses CL V2's
AccessHub owner. For each, computed the REVERSE alias (`address - offset mod 2^160`)
and checked for real bytecode at that hypothetical L1 address on Ethereum mainnet,
plus each address's real transaction count on Arbitrum mainnet (the same
independent-activity signal that ruled Curve's controller OUT in the original
correction: a genuine bridge alias can never have organic, independently-signed
activity of its own on Arbitrum).

Result: none reverse-alias to a real deployed L1 contract (0 bytecode at every
computed reverse address), and Ramses' AccessHub owner specifically has 666 real
transactions on Arbitrum mainnet -- strong, independent confirmation it's a real,
actively-used key, not a mathematical alias byproduct (the same signal, even
stronger, as Curve's 287-tx ruling). All four remain correctly scored as bare
EOAs; the Uniswap-stack correction in this document does not generalize to any
other tracked target.
