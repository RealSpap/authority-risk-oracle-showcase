# Evaluation (2026-09-18): ERC-8241 "Protocol Control Disclosure" compatibility with authority-risk-oracle

Requested by a tracked GitHub Projects item: "[backlog note]
IProtocolSafetyCore pour authority-risk-oracle." Pure research --
`src/AuthorityRiskOracle.sol` is unmodified by this evaluation. Sources
checked directly rather than taken from a summary: the reference
implementation repo (`github.com/chegecjay-rgb/protocol-control-
disclosure`, cloned locally and read file-by-file), its `ERC-8241.md`
spec doc, and the actual ERC pull request
(`github.com/ethereum/ERCs/pull/1706`) and Ethereum Magicians thread
(`ethereum-magicians.org/t/protocol-control-disclosure-core/28343`) it
links to.

## Headline finding: `IProtocolSafetyCore` is the standard's OWN superseded design, not its current interface

The tracker item names `IProtocolSafetyCore` specifically. That interface
does exist in the reference repo
(`research/legacy/protocol-safety/interfaces/IProtocolSafetyCore.sol`) --
but it lives under `research/legacy/`, and the repo's own `ERC-8241.md`
names a completely different file as the canonical interface:

```
## Canonical Interface
core/IERC8241Disclosure.sol
```

That current interface is minimal -- a single function:

```solidity
interface IERC8241Disclosure {
    function disclosureURI() external view returns (string memory);
}
```

`IProtocolSafetyCore` (the legacy design) was a much richer, fully
on-chain graph -- `ComponentSet`/`GraphNodeSet`/`PowerDescriptorSet`/
`GraphEdgeSet` events, enumerable components/nodes/powers/edges,
`SafetyTypes.ControllerType` (EOA/MULTISIG/TIMELOCK/DAO/ACCESS_MANAGER/
MODULE/GUARDIAN) and `SafetyTypes.PowerKind` (UPGRADE/PAUSE_DEPOSITS/
PAUSE_WITHDRAWALS/MINT/BURN/BLACKLIST/SWEEP_FUNDS/...) enums storing the
whole disclosure graph directly on-chain. The standard evidently moved
away from that design (likely gas/complexity cost of an enumerable
on-chain graph) toward a minimal off-chain pointer. The `extensions/
safety/` directory that would be the current home for that richer shape
is currently an empty stub ("non-normative and OPTIONAL," no interface
files). **Evaluating compatibility against `IProtocolSafetyCore`
specifically would be evaluating against a design ERC-8241 itself has
already moved past.**

## The standard explicitly scopes ITSELF out of what authority-risk-oracle does

`ERC-8241.md`'s own Scope section:

> ERC-8241 does NOT standardize: execution validation, governance
> legitimacy, operational correctness, economic safety, **verification
> policy**, execution intent.

And its Architecture Position table names three separate layers:

| Layer | Responsibility |
| --- | --- |
| ERC-8241 | Structural declaration |
| Proof of Operation (PoO) | Execution events |
| Ethereum Transparency Layer (ETL) | Verification |

Authority-risk-oracle's actual function -- interpreting raw authority
facts into 5 numeric risk sub-scores (`adminKeyScore`, `multisigScore`,
`timelockScore`, `oracleAuthorityScore`, `crossExposureScore`) -- is a
**verification/interpretation layer**, structurally the same role as
that table's "ETL" row, not a competitor to ERC-8241's "structural
declaration" layer. The standard's own paragraph.com announcement makes
the same point independently: "summaries, claims, profiles, diagnostics,
and audit evidence belong in optional extensions or external
interpretation layers" -- authority-risk-oracle IS exactly that kind of
external interpretation layer, by the standard's own design intent, not
something ERC-8241 tries to replace or that would replace it.

## Practical state of the standard today

ERC-8241 is a live but early draft: PR #1706 to `ethereum/ERCs`, under
discussion on Ethereum Magicians, not finalized, no evidence found of
any deployed protocol actually publishing a `disclosureURI()` today.
There is currently no live on-chain disclosure data for authority-risk-
oracle to consume even if it wanted to -- this is a forward-looking
alignment question, not an integration blocked on engineering effort.

## Concrete, low-risk opportunity identified (not implemented here)

`IERC8241Disclosure`'s canonical interface is exactly one view function.
`AuthorityRiskOracle.sol` could optionally implement it itself --
`disclosureURI()` returning a pointer to a JSON document (e.g.
`api/scores.json`, or a purpose-built disclosure document derived from
it) -- letting this project self-declare as an ERC-8241-compliant
structural-disclosure source IN ADDITION TO being a scoring oracle nothing
about the two roles conflicts. This is a small, additive, non-breaking
contract change (one new function, no change to existing `getScore()`/
`updateScores()` behavior). **Not implemented in this pass**: it touches
`src/AuthorityRiskOracle.sol`, the actual deployed/documented contract
surface for this hackathon submission, and is the kind of change worth
Spap's own sign-off before touching the submitted contract, not a
unilateral addition from a research task.

## Answer to the tracker item's question

Not compatible in the sense of "authority-risk-oracle should implement
`IProtocolSafetyCore`" -- that interface is the standard's own
discarded prior design. Compatible and complementary in the sense that
matters: ERC-8241 (current form) and authority-risk-oracle occupy
different, non-overlapping layers by the standard's own explicit
design, and a trivial, optional `disclosureURI()` addition would let
this project participate in both layers at once, whenever the standard
matures enough for that to be worth doing.
