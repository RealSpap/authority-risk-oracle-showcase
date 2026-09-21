//! solana-authority-oracle
//!
//! Solana-native counterpart to `src/AuthorityRiskOracle.sol` (the EVM oracle
//! this project already publishes on Robinhood Chain/Ethereum L1/Arbitrum/
//! Base). Same data model, same "publication point, not a computation
//! engine" boundary (scores are computed off-chain by
//! `chains/solana/scorers.py::score_all()`, re-derived live from Solana
//! Mainnet Beta every run, and pushed here by an UPDATER-authority
//! keypair) -- adapted to Solana idioms rather than translated line-by-line:
//!
//!   - Solidity `mapping(address => AuthorityScore)` -> one PDA per target,
//!     seeds `[b"score", target.as_ref()]`. Anchor derives and validates the
//!     address itself; there is no equivalent of Solidity's implicit
//!     "unscored target reads as a zero struct" -- an unscored target's PDA
//!     simply does not exist yet (`get_account_info` on it fails), which is
//!     an HONEST improvement over the EVM contract's own documented
//!     footgun (`getScore`'s natspec: "an unstaled zero score and a
//!     genuinely-uncovered target both read as zero").
//!   - Solidity `AccessControl`'s `UPDATER_ROLE`/`DEFAULT_ADMIN_ROLE` ->
//!     a single `Registry` PDA holding one `updater` pubkey (equivalent to
//!     UPDATER_ROLE) and one `admin` pubkey (DEFAULT_ADMIN_ROLE),
//!     deliberately NOT OpenZeppelin's full many-holders-per-role model --
//!     this project's actual usage on the EVM side is one EOA per role, and
//!     a minimal two-pubkey struct is enough for a hackathon-phase oracle;
//!     multi-holder roles are a real future extension, not implemented here
//!     (see `AuthorityOracleError` doc comment).
//!   - Solidity's dynamic `trackedTargets` array -> `Registry.tracked` is a
//!     `Vec<Pubkey>`, capacity-bounded at `MAX_TRACKED_TARGETS` (space is
//!     fixed at `initialize` time, Solana account data cannot grow without
//!     an explicit `realloc`) rather than unbounded like the EVM version --
//!     64 is comfortably above the 13 targets `scorers.py` currently covers
//!     (`chains/solana/data/scored_targets_2026-09-18-defi-config-admins.md`,
//!     `..._marinade-liquid-staking.md`).
//!   - Each 0-100 sub-score is still validated on push (mirrors the EVM
//!     contract's `ScoreOutOfRange` fix, item 9 in
//!     `data/contract_review_2026-09-17-llamaguard-comparison.md`) --
//!     u8 alone does not bound a Solana account field to 0-100 any more
//!     than it does a Solidity one.
//!
//! Status: SKETCH for the `scoring_build` phase of
//! `authority-risk-oracle-multichain-pipeline` (id: solana). Not deployed
//! anywhere yet -- deployment (Solana Devnet only, zero-value keypair,
//! never mainnet) is `deploy_testnet` phase work. See
//! `chains/solana/program/README.md` for the local dry-run this phase
//! actually exercises, and `chains/solana/deploy/update_scores_solana.py`
//! for the off-chain push-script sketch (dry-run only, no oracle address
//! exists yet to send to).
use anchor_lang::prelude::*;

// Placeholder program ID. `cargo build-sbf` auto-generates its own program
// keypair at `target/deploy/solana_authority_oracle-keypair.json` on first
// build if none exists there yet (a real gotcha hit while building this
// sketch: that auto-generated pubkey does NOT start out matching whatever
// `declare_id!` says, and the two must agree before a real deploy --
// `anchor keys sync` normally does this automatically, not available here
// since no `anchor` CLI is installed, see Anchor.toml's `[toolchain]` note)
// -- this constant is that build's own auto-generated pubkey, copied here
// by hand so the two agree. The keypair file itself is NOT committed
// anywhere in this repo (target/ is build output) and is zero value by
// construction (a program address, never funded, never a deploy target for
// real money). Whoever actually deploys this in the `deploy_testnet` phase
// should either reuse that same local keypair file (regenerate it with
// `cargo build-sbf` if lost -- the pubkey below would then need updating
// again) or generate a fresh one and update this constant to match -- same
// "regenerate before real use, never reuse a key that appeared in a log"
// discipline this project's own operating memory already applies to the
// EVM-side testnet keys.
declare_id!("5VhiTAGLEViGgajhxPbzdWz7WLUAiRy42DY6qi6tYh4W");

/// Registry capacity. See the module doc's "tracked targets" note -- fixed
/// at `initialize` time, 64 is ~5x the 13 targets scored as of 2026-09-18.
pub const MAX_TRACKED_TARGETS: usize = 64;

/// A score is considered stale after this many seconds without an update.
/// Mirrors `AuthorityRiskOracle.sol`'s `maxStaleness` default (9 days),
/// same rationale: the off-chain scoring run cadence, not a protocol-level
/// constant, so it lives in `Registry` (admin-tunable) rather than here.
pub const DEFAULT_MAX_STALENESS_SECONDS: i64 = 9 * 24 * 60 * 60;

#[program]
pub mod solana_authority_oracle {
    use super::*;

    /// One-time setup: creates the `Registry` PDA and sets the initial
    /// admin/updater. Mirrors the EVM constructor's
    /// `_grantRole(DEFAULT_ADMIN_ROLE, admin); _grantRole(UPDATER_ROLE,
    /// admin);` -- same target, one keypair holds both roles at genesis,
    /// splittable later via `set_updater`/`set_admin`.
    pub fn initialize(ctx: Context<Initialize>, admin: Pubkey, updater: Pubkey) -> Result<()> {
        let registry = &mut ctx.accounts.registry;
        registry.admin = admin;
        registry.updater = updater;
        registry.max_staleness_seconds = DEFAULT_MAX_STALENESS_SECONDS;
        registry.tracked = Vec::new();
        registry.bump = ctx.bumps.registry;
        Ok(())
    }

    /// Push (create-or-overwrite) one target's score. Mirrors
    /// `AuthorityRiskOracle.sol::updateScore`. `target` need not be a
    /// Solana account that exists or is owned by this program -- exactly
    /// like the EVM version, this is a publication point for an
    /// off-chain-computed score ABOUT an address, not a claim that the
    /// address is itself controlled by this program.
    pub fn update_score(
        ctx: Context<UpdateScore>,
        target: Pubkey,
        admin_key_score: u8,
        multisig_score: u8,
        timelock_score: u8,
        oracle_authority_score: u8,
        cross_exposure_score: u8,
        composite_score: u8,
        methodology_hash: [u8; 32],
    ) -> Result<()> {
        require_keys_eq!(
            ctx.accounts.updater.key(),
            ctx.accounts.registry.updater,
            AuthorityOracleError::UnauthorizedUpdater
        );
        require!(
            [
                admin_key_score,
                multisig_score,
                timelock_score,
                oracle_authority_score,
                cross_exposure_score,
                composite_score
            ]
            .iter()
            .all(|s| *s <= 100),
            AuthorityOracleError::ScoreOutOfRange
        );

        let score_account = &mut ctx.accounts.score;
        let is_new = score_account.target == Pubkey::default();
        score_account.target = target;
        score_account.admin_key_score = admin_key_score;
        score_account.multisig_score = multisig_score;
        score_account.timelock_score = timelock_score;
        score_account.oracle_authority_score = oracle_authority_score;
        score_account.cross_exposure_score = cross_exposure_score;
        score_account.composite_score = composite_score;
        score_account.last_updated = Clock::get()?.unix_timestamp;
        score_account.methodology_hash = methodology_hash;
        score_account.bump = ctx.bumps.score;

        if is_new {
            let registry = &mut ctx.accounts.registry;
            require!(
                registry.tracked.len() < MAX_TRACKED_TARGETS,
                AuthorityOracleError::RegistryFull
            );
            registry.tracked.push(target);
        }

        emit!(ScoreUpdated {
            target,
            composite_score,
            last_updated: score_account.last_updated,
            methodology_hash,
        });
        Ok(())
    }

    /// Admin-only: adjust how long a score stays valid before an
    /// `is_stale` check (left to off-chain/consumer-side computation for
    /// now, same as the EVM side's `isStale` reading `maxStaleness`) should
    /// treat it as stale.
    pub fn set_max_staleness(ctx: Context<AdminOnly>, new_max_staleness_seconds: i64) -> Result<()> {
        require!(new_max_staleness_seconds > 0, AuthorityOracleError::InvalidStaleness);
        ctx.accounts.registry.max_staleness_seconds = new_max_staleness_seconds;
        Ok(())
    }

    /// Admin-only: rotate the updater keypair (e.g. the devnet throwaway
    /// key gets regenerated -- see `feedback_repo_visibility_default`-
    /// adjacent hygiene notes in this project's own operating memory about
    /// never reusing a key seen in a log).
    pub fn set_updater(ctx: Context<AdminOnly>, new_updater: Pubkey) -> Result<()> {
        ctx.accounts.registry.updater = new_updater;
        Ok(())
    }
}

#[derive(Accounts)]
pub struct Initialize<'info> {
    #[account(
        init,
        payer = payer,
        space = Registry::SPACE,
        seeds = [Registry::SEED],
        bump
    )]
    pub registry: Account<'info, Registry>,
    #[account(mut)]
    pub payer: Signer<'info>,
    pub system_program: Program<'info, System>,
}

#[derive(Accounts)]
#[instruction(target: Pubkey)]
pub struct UpdateScore<'info> {
    #[account(
        mut,
        seeds = [Registry::SEED],
        bump = registry.bump
    )]
    pub registry: Account<'info, Registry>,
    #[account(
        init_if_needed,
        payer = updater,
        space = AuthorityScore::SPACE,
        seeds = [AuthorityScore::SEED, target.as_ref()],
        bump
    )]
    pub score: Account<'info, AuthorityScore>,
    #[account(mut)]
    pub updater: Signer<'info>,
    pub system_program: Program<'info, System>,
}

#[derive(Accounts)]
pub struct AdminOnly<'info> {
    #[account(
        mut,
        seeds = [Registry::SEED],
        bump = registry.bump,
        has_one = admin @ AuthorityOracleError::UnauthorizedAdmin
    )]
    pub registry: Account<'info, Registry>,
    pub admin: Signer<'info>,
}

#[account]
pub struct Registry {
    pub admin: Pubkey,
    pub updater: Pubkey,
    pub max_staleness_seconds: i64,
    pub tracked: Vec<Pubkey>,
    pub bump: u8,
}

impl Registry {
    pub const SEED: &'static [u8] = b"registry";
    // discriminator(8) + admin(32) + updater(32) + max_staleness(8)
    // + vec_len_prefix(4) + tracked(32 * MAX_TRACKED_TARGETS) + bump(1)
    pub const SPACE: usize = 8 + 32 + 32 + 8 + 4 + (32 * MAX_TRACKED_TARGETS) + 1;
}

/// Solana counterpart to `AuthorityRiskOracle.sol`'s `AuthorityScore`
/// struct -- same six 0-100 sub-scores, same `lastUpdated`/
/// `methodologyHash` provenance fields, one PDA per target instead of one
/// mapping slot.
#[account]
pub struct AuthorityScore {
    pub target: Pubkey,
    pub admin_key_score: u8,
    pub multisig_score: u8,
    pub timelock_score: u8,
    pub oracle_authority_score: u8,
    pub cross_exposure_score: u8,
    pub composite_score: u8,
    pub last_updated: i64,
    pub methodology_hash: [u8; 32],
    pub bump: u8,
}

impl AuthorityScore {
    pub const SEED: &'static [u8] = b"score";
    // discriminator(8) + target(32) + 6*u8(6) + last_updated(8)
    // + methodology_hash(32) + bump(1)
    pub const SPACE: usize = 8 + 32 + 6 + 8 + 32 + 1;
}

#[event]
pub struct ScoreUpdated {
    pub target: Pubkey,
    pub composite_score: u8,
    pub last_updated: i64,
    pub methodology_hash: [u8; 32],
}

#[error_code]
pub enum AuthorityOracleError {
    #[msg("caller does not hold the registry's updater key")]
    UnauthorizedUpdater,
    #[msg("caller does not hold the registry's admin key")]
    UnauthorizedAdmin,
    #[msg("a sub-score exceeds 100")]
    ScoreOutOfRange,
    #[msg("registry is at MAX_TRACKED_TARGETS capacity -- not implemented yet: growing this would need an explicit account realloc, see module doc")]
    RegistryFull,
    #[msg("max_staleness_seconds must be positive")]
    InvalidStaleness,
}
