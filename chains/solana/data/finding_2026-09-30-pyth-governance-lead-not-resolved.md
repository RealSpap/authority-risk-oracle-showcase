# Pyth ("$7B secured"): no Solana-side committee at all -- it's a pure Wormhole-VAA execution layer, sourced from Pyth's own code, exact emitter PDA not yet re-derived

2026-09-30. Third of the 3 SolGov-adjacent candidates never turned into scorers (`finding_2026-09-26-solgov-registry-verified-live.md`
listed Hylo, Switchboard, Pyth as untracked; Hylo and Switchboard closed tonight, see their own findings). This one is **not resolved**
-- written up honestly as a partial lead, not stretched into a conclusion the evidence doesn't support.

## What's actually confirmed on-chain

All 11 Solana programs SolGov lists for Pyth (Legacy Oracle, Pull Oracle, Push Oracle, Pyth Governance, Pyth Crosschain, and 6 more)
share the exact same upgrade authority: `6oXTdojyfDS8m5VtTaYB9xRCxpKGSvKJFndLUPV3V3wT`. Confirmed live on both RPCs. That address is
off-curve, System-Program-owned, no data -- shaped like a PDA, same as every other multisig vault checked tonight, but it does **not**
match any Squads v4 vault (0/1/2) or Squads v3 authority derivation tried (tried both program ids the rest of this codebase already
knows about -- `SQDS4ep...` and `SMPLecH...` -- neither derives this key).

Its 10 most recent transactions all route through a program called `SMPLVC8MxZ5Bf5EfF7PaMiTCxoBAcmkbM2vkrvMK8ho` running an
`ExecuteInstruction` that itself invokes Wormhole's Solana Core Bridge (`worm2ZoG2kUd4vFXhvjh93UUH596ayRfgQ2MgjNMTth`, a well-known,
independently recognized address) to post a sequenced message. So there IS a real on-chain multisig-shaped construct behind this
authority, and it genuinely does talk to Wormhole -- consistent with SolGov's own note that this is "Wormhole"-versioned governance,
not a plain Squads multisig. What `SMPLVC8...` actually is (its own program logic, member set, threshold) was not identified: it
doesn't match any known program id already in this codebase, and it wasn't found by name in a web search.

## Why this stops here instead of guessing a threshold

SolGov's raw data describes the real mechanism as "Pythian Council multisig (cross-chain messages verified by a 5-key Pyth-controlled
guardian set since 26 August 2026)" and separately lists a nominal "threshold 7, members 9" -- two different numbers for two different
things (a council and a guardian set), neither independently confirmed here. Getting this right needs reading Pyth's own governance
program logic (likely in `pyth-network/pyth-crosschain` on GitHub, not fetched this pass) to find: (1) the real seed/derivation that
produces `6oXTdojy...`, (2) what `SMPLVC8...` requires to execute (a Squads-like on-chain quorum, or just a relay callable by anyone
once a valid VAA exists), and (3) the actual guardian/council membership and threshold that gates the VAA itself. None of that was
traced tonight. Reporting a "7-of-9" or "5-key" number here without having independently derived it would be exactly the kind of
unverified claim this project's whole discipline exists to avoid -- so this is written up as an open lead, not a score.

## Update, same session: the mechanism is now identified from Pyth's own source -- the real answer is "no Solana-side committee at all"

Read `pyth-network/pyth-crosschain`'s own `governance/remote_executor/programs/remote-executor/src/lib.rs` directly. This IS the
open-source program family this on-chain construct belongs to (Pyth's official cross-chain governance executor):

- Its own `declare_id!` is `exe6S3AxPVNmy46L4Nj6HrnnAVQUhwyYzMSNcnRn3qq` -- checked on both RPCs, **this exact address does not exist
  on Solana mainnet** (empty account, both RPCs agree). So the live deployment uses a different keypair than the current `main` branch
  source shows; `SMPLVC8MxZ5Bf5EfF7PaMiTCxoBAcmkbM2vkrvMK8ho` (confirmed live, executable, actively invoked) is presumably that real
  deployed instance, not independently proven byte-for-byte identical to this source revision, but the same program family.
- **The signing authority PDA is seeded `["EXECUTOR_KEY", emitter_address]`** -- derived from whichever Wormhole emitter posted the
  VAA, not from any Solana-side multisig account. Re-deriving this precisely needs Pyth's specific governance emitter address (chain +
  32-byte address in Wormhole's format), not found this pass.
- **Critically: the executor program's own logic has no threshold, quorum, or guardian check at all.** Quoting the analysis of its
  logic: it validates VAA magic bytes, checks the emitter chain is the expected one, and enforces strictly increasing sequence numbers
  against replay -- "an execution layer that assumes messages have been validated upstream by Wormhole's guardian network." There is
  no on-chain Solana committee to characterize as 5-of-N or 7-of-9 -- **the real security boundary is Wormhole's own guardian network
  consensus** (the main Wormhole network runs a 13-of-19 guardian threshold; whether Pyth governance messages route through that
  general network or a Pyth-specific guardian subset, as SolGov's "5-key Pyth-controlled guardian set since 26 August 2026" note
  claims, was not independently confirmed here) **plus** whatever token-holder/DAO process (`pyth_governance_voter` in the same repo,
  not read this pass) actually authorizes the VAA to be emitted in the first place.

**Update, same day (EVM side confirmed):** the "5-key Pyth-controlled guardian set" is real on EVM. On Ethereum, Base and Arbitrum
(2 RPCs each) Pyth's `wormhole()` no longer points at Wormhole Core (13-of-19) but at a Pyth-specific receiver whose current set
(index 1) is 5 keys, and whose implementation bytecode matches the published 3-of-5 `ReceiverImplementationHalf`; Pyth's OP-PIP-132
says governance VAAs, upgrades included, verify against that set. So "the real security boundary is Wormhole's own guardian network"
above is no longer right for EVM since 26/08: it is 3 of 5 Pyth keys. Whether the Solana receiver moved the same way (the verifier
of the 30/09 pass cites a companion proposal, OP-PIP-131, with 3 signatures) was NOT re-read here. See
`chains/ethereum-l1/data/finding_2026-09-30-pyth-evm-receiver-3of5.md`.

This resolves the shape of the mechanism with real sourcing, even though the exact emitter bytes weren't derived. Reporting a
Solana-side "N-of-M" for Pyth would be actively wrong now, not just unverified -- there isn't one at this layer.

## What a real pass would still need (for whoever picks this up)

1. Find Pyth's specific Wormhole governance emitter chain + address (likely in `governance/xc_admin` config, not read this pass) and
   re-derive the `EXECUTOR_KEY` PDA to confirm it equals `6oXTdojyfDS8m5VtTaYB9xRCxpKGSvKJFndLUPV3V3wT` exactly.
2. Read `pyth_governance_voter` to find the REAL question this project should be asking for Pyth: not "what Solana multisig can
   execute", but "what token-holder threshold/process can get a VAA emitted in the first place" -- that's the actual authority.
3. If this ecosystem's own guardian-set claim (5 keys, since 26/08) matters, verify it directly against Wormhole/Pyth's guardian
   registry rather than SolGov's unverified note.

Not added as a scorer -- would need METHODOLOGY.md to grow a Wormhole-VAA-governance path type first (a DAO-vote-gates-a-VAA model,
not a Squads threshold), a bigger addition than a normal new target.
