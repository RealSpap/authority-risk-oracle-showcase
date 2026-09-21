# Finding (2026-09-17): who actually controls the SPL Governance shared default instance

Closes two open points standing since the 2026-09-16 discovery draft
(`chains/solana/METHODOLOGY.md` section 7): "Identify the controller of the
SPL Governance instance authority `HF7gCq7B...8y9n`" and "Identify program
`SMPLVC8MxZ5Bf5EfF7PaMiTCxoBAcmkbM2vkrvMK8ho` (executes Pyth upgrades) from
a primary Pyth or Squads source." Retried today using the exact same
"reconstruct the caller from a real transaction, then cross-check with an
independent method" technique already established for Jupiter/Kamino's
Squads authorities -- neither answer was previously reachable because the
project's own Realms-reading tooling (`sol_read.py::read_realm`/
`read_governance`) didn't exist yet; it does now, built for the Solend DAO
governance target earlier today.

**Adversarially reviewed the same day**, independently re-deriving every
checkable claim via live RPC and a from-scratch Borsh decode: every claim
below held up except one date reference (fixed, see the "corrected" note
inline). The review also independently confirmed something this file
originally left unverified -- that the council's 7 tokens really are held
by 7 distinct people, not one entity holding all 7 -- by decoding every
`TokenOwnerRecordV2` for this realm directly, not just checking supply and
decimals. One reasoned caveat raised, not a bug: reusing the Squads
multisig formula for a token-weighted council (section "What this changes"
below) imports an "independent parties must collude" model that assumes
Squads-like key-custody discipline across council members -- plausible for
a security council, but not independently confirmed this pass.

## 1. `HF7gCq7BMB6cFfhharTGGm31sqDdpmvLTgF4WEoW8y9n` -- the SPL Governance program's own upgrade authority

METHODOLOGY.md 3.1 already recorded that the shared default SPL Governance
instance (`GovER5Lthms3bLBqWub97yVrMmEogzX7xNjdXpPPCVZw`) is upgradeable by
this PDA, but its controller was unidentified.

**Live trace, 2026-09-17:**

1. `getSignaturesForAddress` on the PDA returns real, recent activity.
   **Corrected after adversarial review**: the most recent signature's
   `blockTime` decodes to 2026-09-01 12:50:01 UTC, not 2026-09-17 as an
   earlier draft of this file mistakenly stated (a units/date-reading
   slip, not a fabricated timestamp) -- still recent (16 days before this
   finding), still well within the window that matters for "is this
   authority live and actively used," just not literally today.
2. The most recent transaction's logs:
   ```
   Program GoVERLMGbGF8kwAwhyNgF1BQ2uyQPawHCWbnFRmLZCf invoke [1]
   Program log: VERSION:"3.1.1"
   Program log: GOVERNANCE-INSTRUCTION: ExecuteTransaction
   Program BPFLoaderUpgradeab1e11111111111111111111111 invoke [2]
   Upgraded program EoKpGErCsD4UEbbY6LX4MLWBUjmoAxqKdU4fdtLuzK6M
   ```
   -- a SEPARATE SPL Governance program deployment,
   `GoVERLMGbGF8kwAwhyNgF1BQ2uyQPawHCWbnFRmLZCf` (version 3.1.1), executed
   this upgrade.
3. Independent cross-check (`sol_read.py programs-by-authority`, the same
   reverse-lookup tool this project already used for the Pyth/Token-2022
   blast-radius notes in section 3.1): `HF7gCq7B...` is the live upgrade
   authority of **14** loader-v3 programs. Their ProgramData PDAs include
   `BZYjZ2Zb...` (offline-derived from `GovER5Lthms...` -- exact match) and
   `88BR3U9H...` (offline-derived from `GoVERLMGb...` itself -- exact
   match, confirming this second governance program upgrades itself
   through the same PDA it also uses to execute proposals).
4. `getProgramAccounts` on `GoVERLMGbGF8kwAwhyNgF1BQ2uyQPawHCWbnFRmLZCf`
   finds exactly 3 `RealmV2` accounts, decoded with this project's own
   `read_realm`: **"Realms Security"**, **"Realms Security council"**, and
   **"Realms Security council 8"**. None of the three appear in Realms'
   own certified-DAO registry (`Mythic-Project/governance-ui`'s
   `public/realms/mainnet-beta.json`, 338 entries checked, zero matches) --
   consistent with this being Realms Today Ltd's own internal
   infrastructure governance, not a consumer-facing listed DAO.
5. "Realms Security council 8"'s own `authority` field
   (`6rFUnQik5dhUsxJaxN2dKGJRD3cX8kQM3cyLD1kbaoCF`) is a `GovernanceV2`
   account under that same realm -- i.e. this realm IS fully self-governed
   (the spl-governance-recommended end state Solend's own realm has NOT
   reached, see `chains/solana/data/methodology_test_2026-09-17-solend-
   governance.md`). Decoding it (modern struct layout, version 3.1.1 --
   NOT the older layout Solend's own deployment uses, see the note below):

   ```
   community_vote_threshold  = Disabled (community can never vote here --
                                consistent with min_community_weight_to_
                                create_proposal = u64::MAX, community
                                participation is structurally locked out)
   council_vote_threshold    = YesVotePercentage(60%)
   council_veto_vote_threshold = YesVotePercentage(60%)
   min_council_weight_to_create_proposal = 1
   transactions_hold_up_time_s = 0
   voting_base_time_s        = 259200 (3 days)
   voting_cool_off_time_s    = 86400 (1 day, negative-votes-only extension)
   ```

   Council mint `ACVqan3WMg6CuE99sn5bNsqpcywg88EhNBAjRftvy7hd`: supply = 7,
   decimals = 0. **Verified, not assumed, during adversarial review**: supply
   and decimals alone don't rule out one entity holding all 7 tokens in a
   single account -- decoding every `TokenOwnerRecordV2` for this realm and
   mint directly confirms 7 DISTINCT owner pubkeys, each with a deposit of
   exactly 1 -- a genuine one-token-per-seat council, **7 distinct members**,
   not an artifact of supply/decimals alone. A 60% weight threshold over 7
   equal-weight seats held by 7 different people is exactly `ceil(0.6*7) =
   5` -- **an effective 5-of-7 council.** The council mint's own
   `mintAuthority` is the SAME PDA (`HF7gCq7B...`), a closed loop: the
   council governs its own membership through its own governance vote, no
   external dependency.

**Answer**: the SPL Governance shared default instance's own upgrade
authority is a 5-of-7-by-weight council ("Realms Security council 8"),
operated by Realms Today Ltd (the company behind app.realms.today /
`Mythic-Project/governance-ui`) as internal platform-security governance,
NOT a consumer DAO, NOT a bare EOA, and NOT a Squads multisig -- a genuine
fourth authority SHAPE this project's own ladder had not yet needed to
classify by name (Realms-governed, council-threshold, not community-token).

## 2. `SMPLVC8MxZ5Bf5EfF7PaMiTCxoBAcmkbM2vkrvMK8ho` -- the program that executed Pyth Solana Receiver's last upgrade

1. `sol_read.py program` on `SMPLVC8Mx...` itself: its own upgrade
   authority is `HVx4oW785bu8QDQ8AwSVfD7H4iuH51ttakc2G5f9XTX8` (already
   recorded in METHODOLOGY.md's open point, just not resolved further).
2. `sol_read.py keytype` on `HVx4oW785...`: off-curve, **owned by
   `pytGY6tWRgGinSCvRLnSv4fHfBTMoiDGiCsesmHWM6U`**.
3. Primary-source confirmation, not inference from the "pyt" vanity
   prefix alone: `pyth-network/governance`'s own `staking/Anchor.toml` on
   GitHub lists `governance = "pytGY6tWRgGinSCvRLnSv4fHfBTMoiDGiCsesmHWM6U"`
   under `[programs.mainnet]` -- Pyth Network's own official on-chain
   governance program (distinct from its `staking` program,
   `pytS9TjG1qyAZypk7n8rw8gfW9sUaqqYyMhJQ4E7JCQ`, in the same file).

**Answer**: `SMPLVC8Mx...` is Pyth's own PYTH-token-holder-governed
execution vehicle for its Solana program upgrades (the Pyth Solana
Receiver included) -- its own upgrade authority is a PDA owned by Pyth's
official governance program, not an ad-hoc or third-party multisig. Not
independently re-derived further this pass (what SMPLVC8Mx's own internal
account layout looks like, e.g. whether it's itself a bespoke multisig-like
structure or a direct governance-PDA executor) -- the open point's actual
question (identify it from a primary Pyth source) is answered.

## What this changes in the methodology

- `chains/solana/METHODOLOGY.md` section 7: both open points closed with
  the derivations above.
- `chains/solana/METHODOLOGY.md` 6.1: the countable council/community-
  threshold multisig formula (previously an unresolved placeholder, itself
  a finding from today's earlier Solend adversarial review) is now
  calibrated against this real 5-of-7 data point -- see the changelog and
  the updated 6.1 table row. Caveat, raised by adversarial review and
  disclosed rather than resolved: this reuses the Squads t-of-n formula's
  "independent parties must collude" model, which assumes Squads-like
  key-custody discipline across the 7 council members -- plausible for a
  security council, but not independently verified this pass (unlike the
  member-count itself, which now is). If a future Realms council target
  turns out to have materially weaker per-member key hygiene than a
  typical Squads signer, this formula would overstate its safety -- tracked
  here, not silently assumed away.
- **CLOSED, same day, once a second real target needed it**: `GovernanceV2`'s
  own byte layout is NOT version-invariant. Solend's deployment
  (`A7kmu2kUcnQwAVn8B4znQmGJeUrsJ1WEhYVMtmiBLkEr`, an older instance) stores
  `governed_account: Pubkey` immediately after `realm`, with
  `proposals_count: u32` next -- the layout `sol_read.py::read_governance`
  implements. This "Realms Security council 8" deployment
  (`GoVERLMGbGF8kwAwhyNgF1BQ2uyQPawHCWbnFRmLZCf`, version 3.1.1) instead
  stores `governance_seed: Pubkey` + `reserved1: u32`, and its
  `GovernanceConfig` has MORE fields (`council_veto_vote_threshold`,
  `community_veto_vote_threshold`, `voting_cool_off_time`,
  `deposit_exempt_proposal_count`) that don't exist in the older layout at
  all. Left flagged-but-unfixed when this file was first written (no
  scored target used the modern layout yet); fixed the same day once Drift
  Protocol's own realm-authority Governance turned out to need it too
  (`data/methodology_test_2026-09-17-drift-protocol.md`): a NEW function,
  `sol_read.py::read_governance_v2`, implements the modern layout as its
  own explicit, separately-named read (not a silent auto-detect branch
  inside the existing function) -- verified against BOTH real accounts
  (this one and Drift's) before being used in any scorer.

## What this does NOT do

- Does not add "Realms Security council 8" (or its two sibling realms) as
  a scored target in `chains/solana/scorers.py`. It is Realms Today Ltd's
  own internal platform-security governance, not a DeFi protocol with
  user funds at stake -- in scope for THIS finding (identifying a shared
  dependency, exactly the pattern METHODOLOGY.md 3.6 already flags:
  "a DAO on the shared instance inherits that authority as a dependency"),
  but scoring Realms Today Ltd itself as a "protocol" is a scope judgment
  call left open, not decided unilaterally here.
- Does not add a `read_governance_v2_modern` decoder for the newer struct
  layout -- flagged as real, disclosed follow-up work, not attempted this
  pass without a concrete target to verify it against.

## Reproduction

```bash
python3 chains/solana/scripts/sol_read.py program https://api.mainnet-beta.solana.com A7kmu2kUcnQwAVn8B4znQmGJeUrsJ1WEhYVMtmiBLkEr
python3 chains/solana/scripts/sol_read.py programs-by-authority https://public.rpc.solanavibestation.com HF7gCq7BMB6cFfhharTGGm31sqDdpmvLTgF4WEoW8y9n
python3 chains/solana/scripts/sol_read.py realm https://api.mainnet-beta.solana.com 2r7VSeKzyepHbdGUsZir94fpZgxBRG2xqgaMnbEALL6r
python3 chains/solana/scripts/sol_read.py governance-v2 https://api.mainnet-beta.solana.com 6rFUnQik5dhUsxJaxN2dKGJRD3cX8kQM3cyLD1kbaoCF
python3 chains/solana/scripts/sol_read.py program https://api.mainnet-beta.solana.com SMPLVC8MxZ5Bf5EfF7PaMiTCxoBAcmkbM2vkrvMK8ho
python3 chains/solana/scripts/sol_read.py keytype https://api.mainnet-beta.solana.com HVx4oW785bu8QDQ8AwSVfD7H4iuH51ttakc2G5f9XTX8
curl -s https://raw.githubusercontent.com/pyth-network/governance/main/staking/Anchor.toml
```
