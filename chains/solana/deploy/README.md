# Solana: deploy_testnet status

**Status on 2026-09-20: DEPLOYED to Solana Devnet** (launched by Spap, record
and read-back in "2026-09-20 -- real deploy on Devnet" at the end of this
file). Everything dated 2026-09-19 below describes the state before the payer
was funded: a full rehearsal on a localhost `solana-test-validator`, and a
throwaway devnet key holding 0 SOL. It is kept as history and is superseded by
the 2026-09-20 record.

## Devnet funding: was blocked until 2026-09-20 (history)

| | |
|---|---|
| Payer / upgrade authority / updater | `BcwteMtYL5wL8dvMYWedPT2V6oh1hTgd8vgKEkQyy9yx` (pipeline's `keys/solana-devnet.json`, zero-value throwaway, never committed) |
| Devnet balance | **0 SOL** (`getBalance` on `https://api.devnet.solana.com`, checked twice this run, slots 500942877 and 500947192) |
| Second RPC cross-check | not obtained: every public devnet endpoint tried needs an API key or paid plan (Ankr, dRPC, Tatum) or rate-limited us (OnFinality 429). Only the official endpoint answered. |
| Program id on devnet | `5VhiTAGLEViGgajhxPbzdWz7WLUAiRy42DY6qi6tYh4W`: `getAccountInfo` returns `null`, so nothing is deployed there yet |

### SOL needed on Devnet (estimated from the `.so` size and Devnet's own rent)

`solana_authority_oracle.so` = 214,808 bytes (sha256
`9ff05f9f9af72aadeac718a6a8bb7578555c855e495c4afffb31d72b5a7382f1`).
The rent figures come from `solana rent <bytes> --url https://api.devnet.solana.com`:

| Item | Bytes | Devnet rent |
|---|---|---|
| ProgramData account (`.so` + 45-byte header) | 214,853 | 1.0921 SOL |
| Deploy buffer (same size, refunded once the deploy finishes) | 214,853 | 1.0921 SOL, only while the deploy runs |
| Program account | 36 | 0.0008 SOL |
| `Registry` PDA | 2,133 | 0.0115 SOL |
| 13 `AuthorityScore` PDAs | 13 x 87 | 13 x 0.00109 = 0.0142 SOL |
| Fees (about 215 buffer-write transactions plus 14 oracle transactions, 5,000 lamports each) | | about 0.0012 SOL |

**Peak need is about 2.21 SOL, and about 1.12 SOL stays locked afterwards.
Funding 2.5 SOL leaves a margin.** Devnet rent is lower than the local
validator's: the same 214,853 bytes cost 1.4963 SOL locally, 37% more. So
the local SOL figures below are not the Devnet cost.

Earlier today (see `../program/README.md`, section "deploy_testnet progress,
2026-09-19") an interactive session tried every no-account path, and each
one failed: CLI airdrop rate limit, CAPTCHA-gated web faucets, faucets that
require a mainnet balance, and PoW faucets that pay too little. This cron run
did **not** request any airdrop or faucet funding, as the run's rules
require.

## What was rehearsed locally (localhost only, zero value)

The validator was a `solana-test-validator` on 127.0.0.1:8899. It was
started with `--mint BcwteM...` so the same throwaway pubkey held the local
genesis SOL. No faucet request was made. It was also started with
`--deactivate-feature B8JJXCy5amZyWG9r7EnUYLwzXSXTxG7GZ1qZ1qggo83g`, and the
next section explains why.

1. **Deploy.** Ran `solana program deploy target/deploy/solana_authority_oracle.so --program-id target/deploy/solana_authority_oracle-keypair.json`
   with the throwaway key as both payer and upgrade authority.
   Program `5VhiTAGLEViGgajhxPbzdWz7WLUAiRy42DY6qi6tYh4W`, ProgramData
   `5hBzvoKRvW4kd8HneUoK1wLogjLmjZiFuJY7rWPTDwSx`, authority `BcwteM...`,
   data length 214,808. `solana program dump` of the deployed program
   hashes to the same sha256 as the local `.so`.
2. **Push.** `python3 chains/solana/deploy/update_scores_solana.py --oracle-rpc-url http://127.0.0.1:8899 --program-id 5VhiT... --keypair-file <keys/solana-devnet.json>`
   sent `initialize` (Registry PDA `CDHtBTibohaCRLtNavArsXfthK9gbwkbmvnujncZBEib`,
   admin = updater = `BcwteM...`). It then re-derived all **13** scores
   live from Mainnet Beta (read-only) and sent 13 `update_score`
   transactions. All 13 confirmed.
3. **Read back with a new call.** `python3 chains/solana/deploy/read_scores_solana.py --oracle-rpc-url http://127.0.0.1:8899 --program-id 5VhiT...`
   does not use the push record. It re-derives the scores live again,
   re-derives every PDA and fetches each account with a new
   `getAccountInfo`. It then checks the owner, the Anchor discriminator,
   the six sub-scores, `methodology_hash` and Registry membership.
   Result: **ALL 13 ON-CHAIN SCORES == CURRENT SCORER OUTPUT**.
   Separately, the Solana CLI's own `find-program-derived-address` gave the
   same Registry PDA and the same Jupiter score PDA
   (`65Zt5pU2sf6Lu4WeEz3Dz8h3Mr7rHYDrdwweiSXyNZz2`), and `solana account`
   on that PDA gives `[55, 83, 0, 100, 40, 47]`.

The local signatures, the ledger and the genesis hash
(`2xo5nyfXREjcHPdaM69siyWFsXuqZhAbeaqUfv7byJeT`) exist only on that
throwaway validator. They cannot be resolved on Devnet or Mainnet. The raw
logs are in the pipeline run folder
`runs/2026-09-19-cron/solana/` (outside this repo).

### Scores rehearsed (live Mainnet Beta derivation, 2026-09-19)

| Target | Program / account | composite | admin | multisig | timelock | oracle | cross |
|---|---|---|---|---|---|---|---|
| Jupiter Aggregator v6 | `JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4` | 47 | 55 | 83 | 0 | 100 | 40 |
| Kamino Lend (main market) | `7u3HeHxYDLhnCoErrtycNokbQYbWGzLs6JSDqGAv5PfF` | 56 | 65 | 76 | 25 | 45 | 80 |
| Solend DAO (governance realm) | `7sf3tcWm58vhtkJMwuw2P3T6UBX7UE5VKxPMnXJUZ1Hn` | 2 | 5 | 0 | 0 | 100 | 100 |
| Drift Protocol | `dRiftyHA39MWEi3m9aunc5MzRF1JYuBsbn6VPcn33UH` | 48 | 65 | 70 | 2 | 2 | 100 |
| Raydium (AMM v4, CLMM, CPMM) | `CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK` | 35 | 45 | 57 | 0 | 100 | 100 |
| marginfi (main group) | `4qp6Fx6tnZkY5Wropq9wUYgtFxXKwE6viZxFHg3rdAG8` | 50 | 60 | 88 | 0 | 100 | 100 |
| Kamino Liquidity (yvaults) | `GKnHiWh3RRrE1zsNzWxRkomymHc374TvJPSTv2wPeYdB` | 54 | 60 | 100 | 0 | 100 | 80 |
| Jupiter Perpetual Exchange | `H4ND9aYttUVLFmNypZqLjZ52FYiGvdEB45GmwNoKEjTj` | 46 | 55 | 80 | 0 | 100 | 40 |
| Jupiter Lend | `7s1da8DduuBFqGra5bJBjpnvL5E9mGzCuMk1Qkh4or2Z` | 56 | 65 | 87 | 13 | 100 | 60 |
| PumpSwap (and pump.fun curve) | `ADyA8hdefvWN2dbGGWFotbzWxrAvLW83WG6QCVXvJKqw` | 43 | 50 | 75 | 0 | 100 | 100 |
| Meteora DAMM v2 | `cpamdpZCGKUy5JxQXB4dcpGPiikHawvSWAd6mEn1sGG` | 2 | 5 | 0 | 0 | 100 | 60 |
| Orca Whirlpool | `2LecshUwdy9xi7meFgHtFJQNSKk4KdTrcpvaB56dP2NQ` | 2 | 5 | 0 | 0 | 100 | 100 |
| Marinade Liquid Staking | `8szGkuLTAux9XMgZ2vtY39jVSowEcpBfFfD8hXSEqdGC` | 45 | 60 | 69 | 0 | 100 | 100 |

`score_all()` (`SIMPLE_SCORERS` in `scorers.py`) currently returns **13**
targets. The pipeline config and `data/scouted_targets_2026-09-17-run2.md`
list 16 scouted targets, but `scorers.py` has no `score_*` function beyond
these 13. The 3 missing targets were therefore not pushed and not guessed.
They stay open until they get a scorer (scoring work, not deploy work).

## Finding: SIMD-0500 differs between local agave 4.2.2 and Devnet

The first local deploy attempt failed with `Detected sbpf_version required
by the executable which are not enabled`. `cargo build-sbf` (4.1.0,
platform-tools v1.54) produces SBPF **v0** by default (`--arch v0`, ELF
`e_flags = 0`). `solana-test-validator` 4.2.2 turns on every feature at
genesis, including **SIMD-0500 "Disable deployment of SBPF v0, v1 and v2
programs"** (`B8JJXCy5amZyWG9r7EnUYLwzXSXTxG7GZ1qZ1qggo83g`). `solana
feature status --url https://api.devnet.solana.com` shows that feature as
**inactive** on Devnet, while SBPFv1, v2 and v3 are all active there. So
the v0 `.so` is deployable on Devnet today. The local rehearsal therefore
deactivates that one feature so it matches Devnet. **Check this again
before the real Devnet deploy.** If SIMD-0500 activates on Devnet first,
rebuild with `cargo build-sbf --arch v3` and rehearse again, because the
current `.so` will then be refused.

## Replay the Devnet deploy once funded (manual funding by Spap first)

```bash
export PATH="$HOME/.local/share/solana/install/active_release/bin:$HOME/.cargo/bin:$PATH"
cd chains/solana/program
cargo build-sbf --manifest-path programs/solana-authority-oracle/Cargo.toml
# program keypair: target/deploy/solana_authority_oracle-keypair.json must be the one whose
# pubkey is 5VhiTAGLEViGgajhxPbzdWz7WLUAiRy42DY6qi6tYh4W (matches declare_id! in lib.rs); it is
# not committed (target/ is gitignored), a copy lives in the main local checkout's target/deploy/.
# KEY = solana-keygen-format (uint8 array) copy of keys/solana-devnet.json, chmod 600, deleted after
solana program deploy target/deploy/solana_authority_oracle.so \
  --program-id target/deploy/solana_authority_oracle-keypair.json \
  --keypair "$KEY" --upgrade-authority "$KEY" \
  --max-len "$(stat -f %z target/deploy/solana_authority_oracle.so)" \
  --url https://api.devnet.solana.com
cd ../../..
python3 chains/solana/deploy/update_scores_solana.py --oracle-rpc-url https://api.devnet.solana.com \
  --program-id 5VhiTAGLEViGgajhxPbzdWz7WLUAiRy42DY6qi6tYh4W \
  --keypair-file keys/authority-risk-oracle/solana-devnet/.env --out pushed_devnet.json
python3 chains/solana/deploy/read_scores_solana.py --oracle-rpc-url https://api.devnet.solana.com \
  --program-id 5VhiTAGLEViGgajhxPbzdWz7WLUAiRy42DY6qi6tYh4W
```

`update_scores_solana.py` itself now waits until the program is invocable
before it sends `initialize` (see "Deploy -> initialize race" below), so
running it right after the deploy, as the open point at the end of this
file recommends, is safe.

`--max-len` matters: without it `solana program deploy` sizes the ProgramData
account at twice the `.so` (2.18 SOL of rent for this 214,808-byte program,
about 3.28 SOL at the peak with the buffer), which a 2.416 SOL payer cannot
cover. With `--max-len` equal to the `.so` size the peak is about 2.21 SOL.
The replay block used to omit it. (`stat -f %z` is the macOS form; use
`stat -c %s` on Linux.)

After that, fill in `Anchor.toml`'s `[programs.devnet]` and replace the
"NOT deployed" status at the top of this file with the Devnet signatures.
Both were done on 2026-09-20, see the last section.

## Files

- `update_scores_solana.py`: `--dry-run` (encoding only, unchanged). The
  non-dry-run path `push_live()` was added this run. It waits for the
  program to be invocable before sending `initialize`.
- `solana_tx.py`: stdlib + PyNaCl helpers. It builds legacy transactions,
  derives PDAs with an ed25519 off-curve check, loads keypairs in both
  formats and makes JSON-RPC calls. It has a **mainnet guard**:
  `assert_not_mainnet()` refuses any oracle RPC whose genesis hash is
  Mainnet Beta's, before the key is even read. This was checked against
  `https://api.mainnet-beta.solana.com` and exits with code 1.
- `read_scores_solana.py`: independent read-back, described above.
- Tests: `scripts/lib/tests/test_solana_deploy_tx.py` (offline). The
  expected PDAs in it come from the Solana CLI. One real bug was caught and
  fixed while writing it: `b58decode` used to zero-pad a value that was too
  short without any error.

## Deploy -> initialize race (fixed 2026-09-19, attempt 2)

A program deployed or upgraded in slot N is not invocable in slot N itself.
The runtime answers `Program is not deployed` / `UnsupportedProgramId`. The
first local replay script sent `initialize` right after `solana program
deploy` and the independent verifier hit that error 2 times out of 2. A
negative control run on 2026-09-19 (no wait, pre-fix code) reproduced it.
The same sequence would race on Devnet too.

Fix: `solana_tx.wait_program_invocable()` checks that the program account
is executable and owned by the upgradeable loader. It then reads the
ProgramData "last deployed slot" and waits until the *confirmed* slot (the
commitment `sendTransaction` preflights against) is strictly greater.
`push_live()` calls it before anything else is sent, and times out with an
error after 60 s. Offline tests: `TestWaitProgramInvocable` in
`scripts/lib/tests/test_solana_deploy_tx.py`. The local replay was run
again with this guard alone (no shell-side wait): 13/13 confirmed and ALL
13 ON-CHAIN SCORES == CURRENT SCORER OUTPUT.

## Open point: `initialize` has no caller restriction

`initialize` (lib.rs) accepts any payer and any `admin`/`updater`. On a
public cluster, whoever sends it first after the deploy owns the Registry.
On Devnet the risk is minor, but the deploy and `initialize` should run
back to back. A later version could require `payer ==` the program's
upgrade authority. This has not been changed yet because it is a program
change, not part of this deploy phase.


## 2026-09-20 -- real deploy on Devnet (launched by Spap)

Replay of the procedure above, run by Spap from `RealSpap/authority-risk-oracle`
at `a1ecc05` (the payer having been funded by hand, see "Devnet funding"
above for why it was blocked). Deploy, `initialize` and the 13 `update_score`
calls ran back to back (the open point below: `initialize` has no caller
restriction). Every value here is read back from Devnet, not copied from the
script's own output.

| | |
|---|---|
| Program | [`5VhiTAGLEViGgajhxPbzdWz7WLUAiRy42DY6qi6tYh4W`](https://explorer.solana.com/address/5VhiTAGLEViGgajhxPbzdWz7WLUAiRy42DY6qi6tYh4W?cluster=devnet), owner `BPFLoaderUpgradeab1e11111111111111111111111`, executable |
| ProgramData | `5hBzvoKRvW4kd8HneUoK1wLogjLmjZiFuJY7rWPTDwSx`, last deployed in slot 501396104, 214,808 bytes (`--max-len` = the `.so` size, zero spare bytes) |
| Upgrade authority / Registry admin / updater | `BcwteMtYL5wL8dvMYWedPT2V6oh1hTgd8vgKEkQyy9yx` (zero-value throwaway, never committed) |
| `.so` | 214,808 bytes, sha256 `9ff05f9f9af72aadeac718a6a8bb7578555c855e495c4afffb31d72b5a7382f1`, SBPF v0 (SIMD-0500 still inactive on Devnet the same day) |
| Deploy tx | [`YkP6oYbt...`](https://explorer.solana.com/tx/YkP6oYbt8tXk3aaD4nCxB1K14HrEAda269nwfmu9ahGDdcJDYqsvXijNt3kr28zdXBqEvDwBxKYA4TuJXfcL8Ej?cluster=devnet) |
| `initialize` tx | [`TsJZFnS1...`](https://explorer.solana.com/tx/TsJZFnS13APwbrXoVbdGaKfQ5tgYTp4oRjNUHMzoaUvZR6iQiHNesQ6wU1amKcgepHqi9xF2Qf9RNgUGDaxiPuv?cluster=devnet) |
| Registry PDA | `CDHtBTibohaCRLtNavArsXfthK9gbwkbmvnujncZBEib`, `maxStaleness` 777,600 s (9 days), 13 targets tracked at deploy, 18 since the evening re-push (last section) |
| Cost | payer 2.416 SOL -> 1.29622392 SOL after everything; 1.09210348 SOL of that difference is rent locked in ProgramData |

The 13 targets pushed (live-derived from Mainnet Beta, read-only, then
`update_score` on Devnet, all confirmed):

| Target | Score PDA | Composite | Tx |
|---|---|---|---|
| Jupiter Aggregator v6 | [`65Zt...NZz2`](https://explorer.solana.com/address/65Zt5pU2sf6Lu4WeEz3Dz8h3Mr7rHYDrdwweiSXyNZz2?cluster=devnet) | 47 | [`FysLvcKU...`](https://explorer.solana.com/tx/FysLvcKUUT4o82GCogdt14VkUHBfn4R42UQoAV48zNiDQnR9ngSx9u3Dctf4X8DDD6EnMWjoF17FZ5yb4JWU78w?cluster=devnet) |
| Kamino Lend (main market, SOL/BTC) | [`FMTQ...YCHa`](https://explorer.solana.com/address/FMTQ8rBhwpLfz1JmmrLqJkYBv79o5SZsu81PoM7WYCHa?cluster=devnet) | 56 | [`56QiUWwH...`](https://explorer.solana.com/tx/56QiUWwH7jRH6Jm8AYspjSER2ytumrp5TAGM6BYJ8URVHcPXqNrsuf94r6ubKyXvnTdFCmn2ganX5J6ECX38xhAP?cluster=devnet) |
| Solend DAO (governance realm) | [`3Ppa...iMpv`](https://explorer.solana.com/address/3Ppaq1anjP1qSXgyYhcr5eDNygawbpyxYqezkKu6iMpv?cluster=devnet) | 2 | [`2uQVdmie...`](https://explorer.solana.com/tx/2uQVdmieVqU5m4ocHmvdEYPxXhT6e1i7q73CkEsGRm3Z1XexUiTNvuEgLeY7mKzqfHvHyxeFDRuXktBS5cDfzAdR?cluster=devnet) |
| Drift Protocol | [`5Jp7...vMd6`](https://explorer.solana.com/address/5Jp7B2h5pW6brxY2Fkeco1UrnNywatAjV3LJEgSwvMd6?cluster=devnet) | 48 | [`sm48aWvZ...`](https://explorer.solana.com/tx/sm48aWvZ2fng7rBDEtcz35AYLhVHqA7hs8ZSetSc3n9PLaikspQSRs9k7Do5eGEvYVb9ASj1SsVCK3RefcoLu5K?cluster=devnet) |
| Raydium (AMM v4, CLMM, CPMM) | [`8Guw...mG7S`](https://explorer.solana.com/address/8GuwiTk6d4ve6tFG22mbnXpuer3DxbZBT24s5UzfmG7S?cluster=devnet) | 35 | [`3VVTpAQX...`](https://explorer.solana.com/tx/3VVTpAQXaR2XFddvz1q6DRqLPTDakaC9WFrM7PGk47ikzU8uVfiuz3ViWDyNNwbCWn7s3WK6e2n3eTgcEBTa1jyW?cluster=devnet) |
| marginfi (main lending group) | [`DwFJ...Euxk`](https://explorer.solana.com/address/DwFJ63PirUVnWvQsVY7c3qrEHnMh1CqvCqD76CseEuxk?cluster=devnet) | 50 | [`PDbcELwP...`](https://explorer.solana.com/tx/PDbcELwPn5Q6obtXqkuq85Kxa8W5xJrQz1cAFT7kj9TH2o3A8bkpXDJ473ip4XCDbaa5zJwzXPYpbfpVngZxMJe?cluster=devnet) |
| Kamino Liquidity (yvaults) | [`HRGY...bdwJ`](https://explorer.solana.com/address/HRGYSnYXQTvEtE4CnsYjaQXHvc3fWGb63z7nhaz8bdwJ?cluster=devnet) | 54 | [`a6uPvHCg...`](https://explorer.solana.com/tx/a6uPvHCgyi1wYaXU34nzbTjuVk8ykNJXPk33mVQDkREtDveRCEFN9cozcKJGyPxqXLa28ZEPtcNzxRZukPGR2tg?cluster=devnet) |
| Jupiter Perpetual Exchange | [`7rRd...Jv5f`](https://explorer.solana.com/address/7rRd5hs89Rs9uFphLx1bKB1kqWUKbzS9gPy1wckYJv5f?cluster=devnet) | 46 | [`38TPUZQT...`](https://explorer.solana.com/tx/38TPUZQTuyXJfAbTnc2aU8YnBVDWdqoDE8bag37nSVF5B1ZL39qWQF8U27kC4ogohoK3v38v2uQ8EgNZBEgxSnDC?cluster=devnet) |
| Jupiter Lend | [`B5sm...S7y4`](https://explorer.solana.com/address/B5smEtafyMrurnGJ6d1CBxfvkLtgkKcdcQy5upuZS7y4?cluster=devnet) | 56 | [`27eL6maX...`](https://explorer.solana.com/tx/27eL6maXNQAGefmLZfVJGWZWufM8dJdQ7N2Q5tJWYfXRqoPbc4PqyvNPqKF6eqRvcX7Np9JbpNjVrK2etdnyvA2d?cluster=devnet) |
| PumpSwap (and pump.fun bonding curve) | [`Hhxa...Q9ah`](https://explorer.solana.com/address/Hhxa41nq8KDfUWrcQQ3rGsiLfkz9qTKw3i9bDapXQ9ah?cluster=devnet) | 43 | [`4cgzxcdK...`](https://explorer.solana.com/tx/4cgzxcdKqoYWdPa6Z2S6r3NqFpCobE4JowTroEfyYNxubcFiuNcaGHRA8FYbCvuRnWaS5vTcm1peFNWdmWBFGMa7?cluster=devnet) |
| Meteora DAMM v2 | [`J9z7...aqA7`](https://explorer.solana.com/address/J9z7kne6ABZecnSyvRVufpD9kX1vqtmv1e7worKEaqA7?cluster=devnet) | 2 | [`XT6tgs6f...`](https://explorer.solana.com/tx/XT6tgs6fGMtHyCuC5sDwX6ynXvRNv54ZMcZkDXZ8wuAuYkczsFRq134NJFSaHwUtWno2rb4UGqC5EBkLX4wqsQB?cluster=devnet) |
| Orca Whirlpool | [`ACfv...dJnF`](https://explorer.solana.com/address/ACfvdeDF3K3fZdBUwokWGcwBAyL1KuHw34HjmgGYdJnF?cluster=devnet) | 2 | [`56HgbjZE...`](https://explorer.solana.com/tx/56HgbjZEWZYycTKzQazyrQT1EY4t2Hah1KVraiirdc4L2doSX2ATgTkikLDBxTZ2MVAWpUAszzDg9UDEA9mJiUWx?cluster=devnet) |
| Marinade Liquid Staking | [`9uMJ...gHXE`](https://explorer.solana.com/address/9uMJuH3qCmEiiib3UZpVGtXjs7weYWRLrL6Cg7q7gHXE?cluster=devnet) | 45 | [`4PKFAHSB...`](https://explorer.solana.com/tx/4PKFAHSB7E4zAAg7UmGgeFW85eazrfjWcRQE4JQytQJBbuv5XemieXaaFtqgXUxD631wnkB5QFYABGFJkaWeKbUh?cluster=devnet) |

**Verification.** Independent of the push script, all read-only:
- the ProgramData bytes on Devnet hash to the local build (`sha256 9ff05f9f...7382f1`) and its
  upgrade authority is the payer;
- [`read_scores_solana.py`](read_scores_solana.py) re-derives the 13 scores live and reads every
  score PDA back: `ALL 13 ON-CHAIN SCORES == CURRENT SCORER OUTPUT`;
- the build is reproducible: a clean `cargo build-sbf` gave the same 214,808 bytes and the same sha256
  as the one recorded on 2026-09-19.

**What was rehearsed first, and what was not.** Before the real run, the same
script ran end to end on a localhost `solana-test-validator` (SIMD-0500
deactivated to match Devnet) with a throwaway payer and a throwaway
`declare_id!`: deploy with `--max-len`, `initialize`, 13 `update_score`,
read-back. What no rehearsal could show is Devnet's public RPC rate limiting
on the roughly 215 buffer-write transactions; it did not bite.

**Still open.** `initialize` still has no caller restriction (see the last
section). The program cannot grow beyond 214,808 bytes without
`solana program extend`. Five more scouted targets were scored and pushed on-chain the
evening of 2026-09-20 (see the next section).


## 2026-09-20 (evening) -- five more targets scored, then pushed on-chain

`scorers.py` now scores 18 targets: the 13 above plus Save, the SPL Stake Pool program, JitoSOL, Sanctum
Infinity and the Sanctum validator LSTs (composites 2, 54, 54, 46, 54, in that order at oracle indexes 13 to
17). The derivation, what was re-verified and what is left open are in
[`../data/scored_targets_2026-09-20-staking-and-save.md`](../data/scored_targets_2026-09-20-staking-and-save.md).
Pushed on-chain the same evening, at 2026-09-20 18:35 UTC (repo `aa6007c`): the same `update_scores_solana.py` run as
above with no `initialize` (the Registry exists), one `update_score` per target, 18 of 18 confirmed, which also refreshed
the 13 existing entries (their `lastUpdated` is now 18:35 UTC, so the first entry turns stale at 2026-09-29 18:35 UTC).
The Registry now tracks 18 targets. Cost: payer 1.29622392 -> 1.29067292 SOL (0.0055 SOL, including about 0.006 SOL of
rent for the five new score accounts). Marinade's `crossExposureScore` moved from 100 to 20 as announced, composites
did not move.

| Target (oracle index 13 to 17) | Score PDA | Composite | crossExposure | Tx |
|---|---|---|---|---|
| Save (ex Solend) lending program | [`Cjxz...D6xH`](https://explorer.solana.com/address/CjxzGpHRj6sS6b5dFkPsHHTqnJ3NDGhH5kKif8KD6xH?cluster=devnet) | 2 | 100 | [`5gjB6yHp...`](https://explorer.solana.com/tx/5gjB6yHpUNS31X3Z8SNHFSvmPrQB5WNc6aPw8dHCUaPYYXcjqNosnjGdagdFAxBz4hEwR5D1MYsqthVLmhjqQupu?cluster=devnet) |
| SPL Stake Pool program (shared infrastructure) | [`5z4h...ghTZ`](https://explorer.solana.com/address/5z4hz41a7JhumadVJfu2sPaqyULwyoHZgQ5zxkxaghTZ?cluster=devnet) | 54 | 20 | [`sonv1xBv...`](https://explorer.solana.com/tx/sonv1xBvMFgt5DhKQrJv4JNnm37LAi5mbrdZxkzJ4TyuP6fz8NTiECPJnuxVLFBiS8M3aedTG6ZLpHo1okZCT2E?cluster=devnet) |
| JitoSOL (Jito Liquid Staking) | [`374z...EA9o`](https://explorer.solana.com/address/374zLNE3hXmD49Gu1cPS8nE44qx5zKhqefYRrAweEA9o?cluster=devnet) | 54 | 20 | [`4TWd8ZKS...`](https://explorer.solana.com/tx/4TWd8ZKSEz5DMjoRFbsqfGbcBpQN3uU1sB7QcXCwsUUBHGER14Y1nava2u9q8nbDcQv2f9R6kspuCELA3pmaomV7?cluster=devnet) |
| Sanctum Infinity (S Controller) | [`P3GS...Fy6f`](https://explorer.solana.com/address/P3GS5XibuM17sS8XPZuqAhxjdDQ4xGREFHjiDUSFy6f?cluster=devnet) | 46 | 20 | [`2aFBRJ8H...`](https://explorer.solana.com/tx/2aFBRJ8HWMZSvwaZhS5T7Yy5rAGz5gFobDSrJGvzpYgeaJri2DdwZRCEKmmyPRTjRw1xdm1kLJ8dvhREtMphU9dc?cluster=devnet) |
| Sanctum validator LSTs (SanctumSpl, SanctumSplMulti) | [`3JLU...yAub`](https://explorer.solana.com/address/3JLU3F3JUksE2ncf11kzshfqQ4aiX6m9z4ruAr2xyAub?cluster=devnet) | 54 | 20 | [`2MJcwh4s...`](https://explorer.solana.com/tx/2MJcwh4s9ZydWZFqVDnkoeYPAm74evbG5imRP3iyCbSSX4ciD4PA67NPWD5k5yLrjkWSH4nzzF2tjCEGw7o3uMz?cluster=devnet) |

Read back with the script above, independent of the push script: `ALL 18 ON-CHAIN SCORES == CURRENT SCORER OUTPUT`,
`tracked=18`. The pushed values, transaction signatures and the payer/genesis check are recorded in the pipeline's
`runs/2026-09-20-prep-financement/repushed_devnet_20260920T183516Z.json`.
