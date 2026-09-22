# Solana -- native on-chain oracle program (sketch, `scoring_build` phase)

Status: **DEPLOYED to Solana Devnet on 2026-09-20** (record and read-back in
[`../deploy/README.md`](../deploy/README.md)). Until then this program was a
**SKETCH**, written and locally build-verified 2026-09-18 and not deployed
anywhere; the sections below are written from that earlier vantage point
and are kept as the history of how it got there. This mirrors
`chains/ethereum-l1/deploy/README.md`'s own "rehearsed but not yet
deployed" status for that ecosystem, and the same convention Arbitrum/Base
already went through before their own `deploy_testnet` runs.

## What this is

`programs/solana-authority-oracle/src/lib.rs` -- an Anchor program that is
the Solana-native counterpart to `src/AuthorityRiskOracle.sol` (the EVM
oracle already used for Robinhood Chain/Ethereum L1/Arbitrum/Base): same
data model (six 0-100 sub-scores, `lastUpdated`, `methodologyHash`), same
"publication point, not a computation engine" boundary (scores are
computed off-chain by `chains/solana/scorers.py::score_all()`, re-derived
live from Solana Mainnet Beta), adapted to Solana idioms rather than
translated line-by-line -- see the module doc at the top of `lib.rs` for
the full mapping (PDA-per-target instead of a Solidity mapping, a
`Registry` PDA instead of OpenZeppelin `AccessControl`, etc.).

## Why no `anchor` CLI

This build environment had no Rust/Solana/Anchor tooling installed at the
start of this phase (`rustup`, the Solana CLI, and `anchor`/`avm` were all
absent). `rustup` and the Solana CLI (which bundles `cargo-build-sbf`) were
installed this phase; `anchor-cli` (via `cargo install anchor-cli` or
`avm`) was not -- compiling it from source is a long build for a phase
whose actual requirement is a working PROGRAM, not the CLI convenience
wrapper. `anchor-lang` (the Rust crate the program actually depends on) is
unaffected by this -- it is not the same thing as the `anchor` CLI binary.
The program is built directly with `cargo build-sbf` instead of
`anchor build`; `Anchor.toml` is kept (see its own `[toolchain]` note) for
the day a real `anchor` CLI is available, and is not load-bearing for the
current build path.

## Local dry run actually performed this phase

**1. Compiles to a deployable program** (the real, reproducible bar this
phase's own instructions ask for -- "dry-run/test local avant tout push"):

```bash
export PATH="$HOME/.local/share/solana/install/active_release/bin:$PATH"
source "$HOME/.cargo/env"
cd chains/solana/program
cargo build-sbf --manifest-path programs/solana-authority-oracle/Cargo.toml
```

Exit code 0, produces `target/deploy/solana_authority_oracle.so` (a
loadable BPF/SBF program, ~215KB) and
`target/deploy/solana_authority_oracle-keypair.json` (the program's own
address keypair -- NOT committed here, see `lib.rs`'s `declare_id!` comment
for why the constant there has to match it by hand without `anchor keys
sync`). Only benign `unexpected cfg condition value: anchor-debug` lint
warnings remain (Anchor's own generated code referencing a cfg flag this
Cargo edition's stricter `check-cfg` lint doesn't recognize by default --
cosmetic, not a build blocker, same class of warning anchor-lang 0.30.x
produces on any sufficiently new Rust toolchain).

Real bug hit and fixed while getting to this point, kept as a comment in
both files rather than silently fixed: `init_if_needed` (used on the
per-target `score` PDA in `UpdateScore`, so the same instruction both
creates a target's first score and overwrites every later one) requires
Anchor's `init-if-needed` Cargo feature to be explicitly enabled --
omitting it does not produce an obvious error message, it cascades into
`UpdateScore<'_>: Bumps is not satisfied` / `try_accounts not found`,
which look like genuine trait-bound bugs in the account struct itself
until you know to look for the missing feature flag
(`programs/solana-authority-oracle/Cargo.toml`).

**2. Real local round-trip** (localhost `solana-test-validator`, NOT
Devnet, NOT Mainnet -- zero value, a throwaway in-memory validator that
only this machine can see):

```bash
export PATH="$HOME/.local/share/solana/install/active_release/bin:$PATH"
solana-test-validator --reset --quiet \
  --bpf-program ENVgJeWHRBH9U9w44Mx8a1L4u58AMtZYgmPXZ7ySKj8a \
  chains/solana/program/target/deploy/solana_authority_oracle.so
# separate terminal:
cd <local_dry_run client dir> && cargo run
```

The client ([`local_dry_run/`](local_dry_run/), a small standalone
`solana-client`/`solana-sdk` binary, excluded from the Anchor program's own
Cargo workspace -- see the root `Cargo.toml`'s `exclude` comment) airdrops
itself 2 SOL from the local validator's own free faucet (a
`solana-test-validator` feature, not a real faucet, not Devnet), calls
`initialize`, then calls `update_score` for Jupiter Aggregator v6 with the
SAME live-mainnet-derived numbers `update_scores_solana.py --dry-run`
encoded this same session (adminKey=55 multisig=83 timelock=0
oracleAuthority=100 crossExposure=40 composite=47), reads the
`AuthorityScore` PDA back, and asserts every field round-trips exactly.

**Actually run, 2026-09-18** (`cargo run` from `local_dry_run/`, against a
`solana-test-validator --reset` freshly started with
`--bpf-program ENVgJeWHRBH9U9w44Mx8a1L4u58AMtZYgmPXZ7ySKj8a target/deploy/solana_authority_oracle.so`):

```
payer = 5epfnM5z8YiUh7y7Q43rR5SrD3mqEVvfeMrAvbeZUF8w
airdrop confirmed on LOCAL test validator (localhost:8899, not devnet/mainnet), balance = 2000000000
registry PDA = HytuVqtf6E2sBtMNGoy81rByVzuvHx8NSmY1KQ72x7PX
initialize tx = 2BxyeanHPXwt3uqdEkhTwvigohctLBdjfz1E7HGnVeLcxig1QQnKUrJ6uWc64xyysAV8GgXNSFq539PsFHJFdXxw
score PDA = 4jgtkDrkrKaWXHFpxUuYh7qmXpxbXKFUbEL722NkMosm
update_score tx = 2vThpt2XMxVwbj1bd7YK6taW7fu2GA7aS99YqJGHs4sst7aHFSu1Nf1pYhhVuNnaQ1MbmghLMtYFDknoxzjk1aWa
score account data len = 87
read back: target=JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4 admin=55 multisig=83 timelock=0 oracle=100 cross=40 composite=47
ALL ASSERTIONS PASSED -- local solana-test-validator (localhost only, zero value) round trip verified
```

Both transaction signatures and the airdropped payer are local-validator-only
(that validator's ledger is not persisted anywhere in this repo, was reset
before the run, and was torn down after) -- not resolvable against Devnet or
Mainnet Beta, not evidence of anything having happened on a public network.
See the journal entry for this run's exact reproduction commands -- do not
trust this README's prose over that journal if they ever disagree.

## Off-chain push script

[`../deploy/update_scores_solana.py`](../deploy/update_scores_solana.py),
parameterized the same way as
[`chains/ethereum-l1/deploy/update_scores_ethereum_l1.py`](../../ethereum-l1/deploy/update_scores_ethereum_l1.py):

```bash
python3 chains/solana/deploy/update_scores_solana.py --dry-run
```

`--dry-run` re-derives all 13 scores live from Solana Mainnet Beta and
builds the exact `update_score` instruction DATA bytes (8-byte Anchor
discriminator + Borsh-encoded args) that would be sent for each target --
**without opening any connection to Devnet, without reading a keypair, and
without sending anything.** Does not depend on `solana-py`/`anchorpy`
(neither installed) -- the discriminator and Borsh layout are computed by
hand from Anchor's own documented convention, same "stdlib only" discipline
`chains/solana/scripts/sol_read.py` already uses. Correctness of the
hand-written base58 decoder was checked against `sol_read.py`'s own `b58()`
encoder (round-tripped on 20 random 32-byte values plus a real program ID)
before being trusted for the actual dry-run output -- see the journal.

The non-dry-run path (build/sign/send a real transaction to Devnet) is not
runnable yet -- it needs `ORACLE_PROGRAM_ID` from an actual Devnet deploy,
which does not exist until `deploy_testnet`.

## What deploy_testnet still needs to do

1. `solana program deploy` the same `.so` to Solana Devnet using
   `keys/solana-devnet.json` (the pipeline's existing zero-value devnet
   keypair) as the payer/upgrade-authority -- NOT the throwaway program
   keypair used for this phase's local build (that one was never intended
   to hold real SOL or persist).
2. Record the resulting Devnet program ID in `ecosystems.json`'s `solana`
   entry and in `Anchor.toml`'s `[programs.devnet]` section (deliberately
   left blank this phase).
3. Re-point `update_scores_solana.py`'s non-dry-run path at that program ID
   and actually send the 13 `update_score` transactions to Devnet.
4. `MAX_TRACKED_TARGETS = 64` (see `lib.rs`) is comfortably above the
   current 13 -- no `Registry` capacity work needed yet, but worth
   re-checking if the target count approaches it.

## `deploy_testnet` progress, 2026-09-19: program ready, real deploy blocked on funding

Rebuilt clean (`cargo build-sbf`, exit 0, same benign `anchor-debug`/`no-idl`
cfg warnings as the sketch above -- nothing new). The prior sketch's program
keypair (`ENVgJeWHRBH9U9w44Mx8a1L4u58AMtZYgmPXZ7ySKj8a`) was never
committed (by design -- `target/` is build output), so a fresh one was
generated this pass: **`5VhiTAGLEViGgajhxPbzdWz7WLUAiRy42DY6qi6tYh4W`**,
now the actual program address should this exact `.so` be deployed.
`declare_id!` in `lib.rs` and `Anchor.toml`'s `[programs.localnet]` were
both updated to match -- exactly the "regenerate before real use" step this
file's own `lib.rs` comment already asked whoever ran deploy_testnet to do.
`[programs.devnet]` is still deliberately left blank: no devnet deploy
happened.

**Funding: genuinely blocked this pass, not for lack of trying.** The
payer is `keys/solana-devnet.json`'s existing zero-value devnet keypair
(`BcwteMtYL5wL8dvMYWedPT2V6oh1hTgd8vgKEkQyy9yx`, generated 2026-09-16,
confirmed 0 SOL both before and after this pass). Every no-real-value,
no-account path this project's own discipline allows was tried, in this
order, before stopping:

- `solana airdrop 2` (official CLI, twice, ~30s apart) -- both attempts:
  `Error: airdrop request failed. This can happen when the rate limit is
  reached.`
- `faucet.solana.com` (the official web faucet) -- the no-login tier gates
  the actual airdrop behind a Cloudflare Turnstile CAPTCHA. Not attempted
  further: completing a CAPTCHA is outside what this pass does under
  any circumstance, not just a funding-specific rule.
- The same faucet's own "I am an AI Agent" panel explicitly recommends
  `devnet-pow` (a proof-of-work faucet CLI) as the agent-appropriate path.
  Installed it (`cargo install devnet-pow`, clean build) and queried
  `get-all-faucets`: 5 community PoW faucets exist, only one with a
  nonzero balance (0.999973 SOL) -- but its reward is 0.0000001 SOL per
  successful mine, meaning tens of millions of mines to reach the ~1.5-3
  SOL a program deploy of this size needs. Not a practical path, disclosed
  rather than forced.
- `faucet.quicknode.com` (Solana Devnet, plain address paste, no wallet
  connect needed) -- rejected: *"Insufficient SOL balance. Please note,
  you'll need a small mainnet balance on this wallet in order to use the
  faucet."* The same real-value/wallet-history gate class already
  documented in `chains/plasma-ecosystem/deploy/README.md` and
  `chains/hyperliquid/deploy/README.md` for their own QuickNode/Chainstack
  rejections -- out of scope by the same standing rule.
- `solana-faucet.zalalena.com` (third-party, no login/wallet/balance per
  its own claims) -- also CAPTCHA-gated before delivery, and its reward
  (0.025 SOL, max 10/day, 60min cooldown) would take multiple days even if
  the CAPTCHA weren't a hard stop.
- `jumpbit.io`'s Solana Devnet faucet (no wallet connect, plain address
  paste) -- got furthest of any third-party option, but failed at the same
  point as the official CLI: *"Requesting airdrop from Solana devnet --
  Rate limit exceeds."* Since an entirely separate frontend, on different
  infrastructure, hit the identical failure, this reads as Solana Devnet's
  own airdrop capacity being genuinely constrained right now, not a
  sandbox-specific IP block.
- Helius's and ZAN's devnet faucets both require creating an account first
  -- out of scope for this pass regardless of funding, per this
  project's standing rule against creating accounts autonomously.
  Chainstack's requires the same 0.8 SOL real mainnet balance as
  QuickNode's.

No funding was requested from Spap for this -- unlike Plasma's and Tempo's
funding, which had Spap's live "go testnet, continue chain by chain"
authorization already in hand, this dead end doesn't change that
authorization's scope (still no-real-value, no-account paths only), it
just means none of those paths are working against Solana Devnet's faucet
capacity at this specific moment. **The program itself is deploy-ready
today** -- rebuilt, ID-synced, `.so` on disk -- the instant Devnet SOL is
reachable by any of the paths above (or the official faucet's rate limit
resets), steps 1-3 above are what is left to actually run.

## `deploy_testnet` cron run, 2026-09-19: full local rehearsal, Devnet still unfunded

See [`../deploy/README.md`](../deploy/README.md). The devnet key still holds
0 SOL. This run requested no faucet funding. The rehearsal on a localhost
`solana-test-validator` covered the real `solana program deploy` of this
`.so` (program `5VhiTAGLEViGgajhxPbzdWz7WLUAiRy42DY6qi6tYh4W`), `initialize`,
13 live-derived `update_score` pushes, and an independent read-back where
all 13 matched the current scorer. Estimated Devnet need: about 2.21 SOL at
peak, 2.5 SOL recommended. Also found: the local validator's SIMD-0500
refuses SBPF v0 deploys, while Devnet does not refuse them yet. Details are
in that file.
