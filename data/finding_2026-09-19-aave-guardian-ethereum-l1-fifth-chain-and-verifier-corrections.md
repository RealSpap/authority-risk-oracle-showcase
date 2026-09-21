# Finding (2026-09-19): the Aave guardian committee is on 5 chains, not 4, plus a list of repo inaccuracies an independent verification pass found

## How this surfaced

19 oracle targets had no hand-written dashboard card (`dashboard/index.html`
rendered them as "Untitled target"). Cards were drafted per chain from scorer
docstrings, repo data files and live reads, and every draft was then handed to
a SECOND agent whose only job was to refute each claim against source and a
fresh on-chain read. Most cards changed. The corrections below are what that
pass found wrong or missing in the repo's OWN text, not only in the drafts.
Nothing here was taken on trust: the two headline items were re-read by hand.

## 1. The Aave guardian committee also sits on Ethereum L1 (5 chains, not 4)

The 9-signer, 5-of-9 committee first found identical on Arbitrum and Base
(2026-09-17), later on Plasma and Monad, was described everywhere as reaching
"four chains". Ethereum L1, the root of the whole Aave Governance V3 design, was
the one chain never compared.

Live, on two independent RPCs (publicnode and drpc), Ethereum mainnet:

- `PoolAddressesProvider(0x2f39d218...4E9e).owner()` = Executor `0x5300A1a1...192A`
- `Executor.owner()` = PayloadsController `0xdAbad81a...AEc5`
- `PayloadsController.guardian()` = Safe `0xCe52ab41C40575B072A18C9700091Ccbe4A06710`
- that Safe is **5-of-9** and its 9 owners are **identical** to
  `_KNOWN_AAVE_GUARDIAN_OWNERS_2026_09_17` (the frozenset the Arbitrum, Base,
  Plasma and Monad scorers compare against).

Why it was missed: `chains/ethereum-l1/scorers.py::score_aave_v3_pool` read this
address and only LOGGED it ("can cancel proposals outside the timelock"); its
committee analysis and `cross_ecosystem_overlap.py`'s L1 `aave_guardian` group
cover a DIFFERENT emergency seat, ACLManager's `PROTOCOL_GUARDIAN` (4-of-7).

Changed in this pass: (a) `ETHEREUM_L1_GROUPS["aave_payloads_guardian"]` added,
so `scripts/check_cross_ecosystem_overlap.py` now reports each of the 9 signers
on 5 chains and 4 new containment rows; (b) `score_aave_v3_pool` now resolves
that Safe and adds a note when its owner set matches (5 tests). **No score
moved.**

Open design question, deliberately NOT decided here: this file's
`crossExposureScore` is within-L1 only by its own stated convention (see the
Morpho Blue note in the same file: "cross-ecosystem fact, not folded into this
file's within-L1 crossExposureScore"), whereas Arbitrum, Base, Plasma and Monad
DO fold cross-chain overlaps into 80. So the same committee is scored 80 on four
chains and 100 on Ethereum L1, and Robinhood's Morpho Blue is likewise not
folded while Base's is. That inconsistency is real; which convention is intended
is a decision for the maintainer, and changing it means a real on-chain push.

**UPDATE 2026-09-20: the open design question is decided.** Cross-ecosystem overlaps are
folded into `crossExposureScore` on every EVM ecosystem, as a flat 80, applied as
`min(within-ecosystem score, 80)` on Ethereum L1, Robinhood Chain and Tempo, from a dated
snapshot with no second-chain RPC. What this section reported as inconsistent is resolved in
the scorers: Ethereum L1's Aave Pool now reads `crossExposureScore` 80 (both the 9-signer
`PayloadsController.guardian()` committee and the 7-signer `PROTOCOL_GUARDIAN` committee match
a snapshot, and the cap is applied once), Ethereum L1's Morpho Blue reads 80, and Robinhood
Chain's Morpho Blue reads 80 like Base's. The "no score moved" statement above was true of
2026-09-19 and is left as written. These values were scorer output first and were pushed
on-chain the same day, 2026-09-20 (Ethereum L1 tx
`0x14b0466ab52a7bf6cab54253cda92c73d52ca1b88957632911d79136b99b7a98`, block 11,740,952). Rule,
before/after table, transaction table and verification:
`data/finding_2026-09-20-cross-exposure-convention-and-score-adjustments.md`.

Stale wording elsewhere that still says "fourth chain" / "third chain" and should
be read as "at least five": `chains/monad/scorers.py` (around lines 98-99,
856-857, 899-900), `scripts/lib/cross_ecosystem_overlap.py` (Monad group
comment), and the Plasma card in `dashboard/index.html`.

## 2. Arcus Perps: the "shared EOA" is a Safe

`scripts/lib/scorers.py::score_arcus_perps_bridgevault`'s docstring,
`scripts/lib/signer_overlap.py` (`known_eoa`) and
`data/rotation_audit_2026-09-19-robinhood-chain-index11.md` all say the address
`0x4f1d777bf36E259F3cB66f2cE969f4c5De05ebe2` (on the BridgeVault timelock's
proposer/executor/canceller roles, and one of the 3 owners of the Arcus pToken
2-of-3 Safe) is "exactly one EOA". Re-read by hand on both Robinhood mainnet
RPCs: it has 171 bytes of code and is a **2-of-4 Gnosis Safe**. The
crossExposure of 80 still stands (the same ADDRESS sits on both sides), but the
nested Safe's own four owners (`0x19687776...`, `0x32aD2818...`, `0x41111c5E...`,
`0x95B70f0e...`) appear in no repo group, so any further overlap through them
was never checked.

## 3. Other inaccuracies found

**Status update, same day, follow-up commit:** the text-only items below are now
corrected at source with dated CORRECTED notes (UNCX docstring/runtime note/README/
index-10 audit; up v3 docstring; both Base docstrings/notes; the Arcus "EOA" wording
in `scorers.py`, `signer_overlap.py` and the index-11 audit; the "fourth chain"
wording in Monad's scorer and the overlap registry). Still OPEN because they
change scoring or need a maintainer call: Euler's unscored instant pause on both
Monad and Plasma (now visible in notes and the sweep, not in the score),
Yuzu's placeholder `adminKeyScore`, and the `crossExposureScore` convention
question in section 1. The Arcus nested Safe's four owners were checked and are
bare EOAs appearing in no other tracked group, so no further overlap hides
behind that address.

Original list, as found:

- **UNCX V3 Locker** (`score_uncx_v3_locker` docstring, index-10 audit, README):
  "25 of 26 selectors matched, `withdraw()` the one that did not" is an artifact
  of the audit method. solc pushes the zero-leading selector `0x00f714ce` as
  PUSH3, so a PUSH4 scan misses it. It IS in the bytecode: 47 of 47 source
  signatures present, and `withdraw()` simulated from the owner Safe reverts
  `OWNER` on every lock. Also missing from the docstring, confirmed by
  `eth_call` simulation with state overrides: the owner Safe can name the
  auto-collect account (`setFeeParams`) and lower a lock's fee to 0
  (`setUCF`), so uncollected trading fees of any lock can be redirected. Principal
  stays out of reach.
- **up v3 Factory** (`scorers.py` docstring, ~lines 1922-1926): says the owner can
  call `enableFeeAmount` and calls it a standard Uniswap V3 fork. The bytecode has
  no `enableFeeAmount`; it exposes a tick-spacing interface
  (`enableTickSpacing`, `tickSpacingToFee`).
- **Base Aerodrome Slipstream** (`chains/base-ecosystem/scorers.py` ~573-576): the
  50% cap applies only to `setDefaultUnstakedFee`; an unstaked-fee MODULE is
  accepted up to 100% (`fee <= 1_000_000`) and a swap-fee module up to 10%.
- **Base Uniswap V4 PoolManager** (~680-681): the owner has two `onlyOwner`
  functions, `setProtocolFeeController` AND `transferOwnership`.
- **Euler V2 eVaultFactory, Monad AND Plasma** (follow-up, same day): the scorers
  looked for `GUARDIAN_ROLE`, `PAUSER_ROLE`, `EMERGENCY_ROLE`, `WILD_CARD`; the
  deployed Governors use none of those names, and no file in the repo named
  `PAUSE_GUARDIAN` or these addresses. Read live (`getRoleMember`) on each chain's
  factory Governor (Monad `0x515C9ff6...`, Plasma `0x939cA204...`): three holders,
  the Labs 2-of-6 Safe (a different address per chain) plus **the same two bare
  EOAs on both chains**, `0xff217004BdD3A6A592162380dc0E6BbF143291eB` and
  `0xcC6451385685721778E7Bd80B54F8c92b484F601`. `eth_call` simulation on both
  chains, no transaction: `pause(eVaultFactory)` from either EOA alone does not
  revert; from a random address it reverts with the access-control error. Effect:
  every upgradeable vault goes read-only, no timelock involved, so `timelockScore`
  (60 Monad, 68 Plasma) does not describe it. It is an availability freeze, not fund
  redirection. Also, the two Labs Safes' 6 signers are all among the DAO Safe's 8
  signers. **Done in this pass:** both scorers now report the role's live holders in
  `notes`, and `cross_ecosystem_overlap.py` has an `euler_pause_guardian` group per
  chain (the sweep now lists the two EOAs under "identical bare-EOA address across
  ecosystems"). **No score changed** (Monad 55/80/60/100/80, Plasma 70/80/68/100/100,
  unchanged live). Whether an instant availability path should cap a score, as the
  Aave guardian and Compound pause guardian do for `timelockScore`, is the
  maintainer's call and would mean a real on-chain push.
- **Plasma Yuzu yzUSD**: `adminKeyScore` 20 is the unresolved-contract
  placeholder. The tokens' `ADMIN_ROLE` sits with a second 12-hour timelock run
  by a 3-of-5 Safe with the same five signers as the 4-of-5 Safe on the 2-day
  timelock, and `ORDER_FILLER_ROLE` / `DISTRIBUTOR_ROLE` are held directly by bare
  EOAs outside both timelocks.
- **Compound V3**: the scorer docstring calls the Governor "Bravo"; it is the newer
  CompoundGovernor behind a proxy (no scoring consequence).
- **Robinhood up v3** (`signer_overlap.py:148`): quotes ~$8.6M TVL, stale
  (DefiLlama ~$8.4M and moving ~10% day to day).

## What was NOT changed

No scorer output, no on-chain score and no oracle state changed in this pass.
Every item in section 3 is a text or coverage fix for the maintainer; the
`crossExposureScore` convention question in section 1 needs a decision first.

**UPDATE 2026-09-20:** the `crossExposureScore` convention question in section 1 has its decision
(see the update there), so it no longer blocks anything; the Yuzu placeholder and the Euler
instant-pause scoring question in section 3 are not covered by that decision.
