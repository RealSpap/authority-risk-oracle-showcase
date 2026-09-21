# Zcash native oracle form -- real Testnet proof of concept, 2026-09-19

Resolves METHODOLOGY.md section 8's open question: "Decide the native oracle
form without contracts (for example signed score attestations in transparent
`OP_RETURN` outputs on Testnet first). Obtaining Testnet funds must not rely
on a CAPTCHA faucet." See METHODOLOGY.md section 9 for the permanent design
writeup this file supports; this file is the evidence trail for the actual
Testnet run: every claim below is independently checkable.

**Hard constraints respected throughout** (restated because this run signs
and broadcasts a real transaction): no write to Zcash Mainnet, no real-value
key generated or used, no CAPTCHA/login-gated faucet used, no fabricated
result -- every number below is either a live-verified on-chain fact or an
already-published score from `chains/zcash/scorers.py`/
`data/scored_targets_2026-09-19.md`.

## 1. Design decision (summary; full reasoning in METHODOLOGY.md section 9)

Zcash has no contract VM, so there is no `AuthorityRiskOracle.sol` to deploy
the way the EVM ecosystems in this project have. Two designs were evaluated:

1. **Embed the full score attestation directly in a transparent `OP_RETURN`
   output.** Rejected as the sole mechanism: standard OP_RETURN relay policy
   keeps payloads small (tens of bytes), a full JSON attestation with a
   signature does not fit, and Zcash's own ecosystem has moved decisively
   shielded-by-default (see section 2 below) -- a design that requires a
   transparent output for every future score update sits against that grain.
2. **Off-chain signed attestation, on-chain hash anchor (adopted).** The full
   attestation (target, all five sub-scores, `methodologyHash`/
   `methodologyVersion`, a timestamp, and an ECDSA signature) is published as
   an ordinary file in this repository. Only a compact commitment -- a
   4-byte magic tag plus a 32-byte BLAKE2b-256 hash of the attestation, 36
   bytes total -- goes on-chain, in a transparent `OP_RETURN` output. This is
   the same "hash-anchor" pattern OpenTimestamps and similar systems use for
   proof-of-existence on Bitcoin-family chains, applied here to an authority
   score instead of a document. It keeps the on-chain footprint minimal and
   fee-cheap regardless of how large a future attestation format grows, and
   is unaffected by any future move to a stricter or looser OP_RETURN policy.
   A shielded-memo variant was considered and rejected: any transaction with
   a shielded component (Sapling/Orchard output or spend) requires zk-SNARK
   proof generation, which this project cannot build from scratch without
   adopting a third-party proving stack (`librustzcash`/`orchard`) far
   outside this task's scope -- a purely transparent transaction needs only
   ECDSA and BLAKE2b, both implementable and independently verifiable in
   plain Python (this run did exactly that, see section 4).

## 2. Faucet: how real, free, transparent Testnet ZEC was obtained

Every requirement in the task was checked, not assumed:

- **No CAPTCHA, no login.** `https://zcashfaucet.jinolabs.xyz/` gates claims
  with an in-browser proof-of-work puzzle ("Your browser solves a short
  puzzle instead of a CAPTCHA"), not a CAPTCHA vendor or an account.
- **Genuinely free.** 0.1 TAZ per address per 24 hours, no payment.
- **Transparent payout, not just shielded.** The faucet's own marketing is
  "shielded-by-default" (it pays `z→z` when given a shielded address, "so
  nothing on chain ties the drip to you"), but its claim form explicitly
  accepts `tm...` (transparent) addresses too, and labels them correctly:
  "Transparent address, so this drip will be visible on-chain." This is
  documented, current behavior, not an exploited bug -- a GitHub issue on
  the faucet's own repo (`jinolabs-xyz/zcash-faucet#478`) flagged an
  inconsistency where a *Sapling* address briefly 502'd while a transparent
  one was paid, which the maintainers treat as a possible design
  inconsistency to revisit, not as unauthorized access; nothing in that
  issue says transparent payouts are disallowed, and the live claim form
  (screenshotted and driven directly this run) still explicitly supports
  and labels a transparent address as a valid input today.
- Under the hood, the faucet pays from ITS OWN shielded wallet to the
  transparent address requested -- a `z→t` transaction the FAUCET signs
  with its own zk-proving stack. This project never needed to generate a
  shielded proof itself: it only had to correctly build a fully transparent
  spend of the transparent output the faucet's transaction created, which
  needs only ECDSA and BLAKE2b (see section 4).

Two addresses were funded this run (see section 3 for why): a first, unused
one from a keygen bug, and the real, used one.

## 3. A key-generation bug, caught before it touched the network

The very first `secp256k1.py` draft hardcoded the curve's generator point
`(Gx, Gy)` from memory. `Gy` was transcribed with one hex digit missing
(`...FFB10D4B` instead of the correct `...FFB10D4B8`) -- a real, disclosed
mistake, not a hypothetical one. This produced a `G` that is **not on the
secp256k1 curve at all** (`y^2 != x^3+7 mod p`), so every "public key" and
signature computed from it before the fix was mathematically meaningless,
even though the code ran without error and looked plausible.

Caught by comparing against an independent, authoritative source before any
signature from that key was trusted: `openssl ecparam -name secp256k1
-param_enc explicit -text -noout`, which prints the real SEC2-standard
generator point. `2*G` and `N*G` (should be the point at infinity) were
checked against the corrected constant and passed; a full sign/verify
roundtrip was additionally cross-checked against `openssl dgst -sha256
-verify` (an independent implementation), which returned `Verified OK`.

**Consequence, disclosed rather than hidden:** the faucet had already paid
0.1 TAZ to the address derived from the broken key
(`tmVGrdXKVyRCYaFBJkHCMLa4Q86oJuqAjtm`, tx
`56bf09d41bde152230c0e75761ce3283c65682a8f0de8a9b517bad8b898c316e`, block
4366602) before the bug was found. That address is **abandoned, not spent
from**: no valid signature can exist for a "public key" that was never a
real curve point, so its 0.1 TAZ is unspendable by this project (and has no
value regardless -- Testnet ZEC). A second, correctly-derived key and
address (`tmDvDRYD7meGJXFoeTqtjFcrNF5378ZzaBo`) was generated after the fix
and used for everything that follows. `scripts/secp256k1.py`'s own test
suite (`scripts/lib/tests/test_zcash_tx.py`) now locks in the corrected
constant against the same OpenSSL reference so this cannot silently
regress.

## 4. Building the transaction: two more bugs caught by cross-checking

Zcash's transaction format and digest algorithm changed completely at NU5
(ZIP 225 serialization, ZIP 244 transaction-ID/signature-hash algorithm),
and again at NU6.3/ZIP 229 (a 5th "Ironwood" digest component, on top of
header/transparent/Sapling/Orchard). None of this is Bitcoin's legacy
double-SHA256 txid or SIGHASH. This project does not have, and did not
build, a Zcash wallet library -- everything here is new code, written
directly against ZIP 225/229/244/317's own text (fetched and read as raw
source from `raw.githubusercontent.com/zcash/zips`, not taken from an
AI-generated paraphrase of them) and cross-checked against the actual
reference implementation's source (`zcash/librustzcash`'s
`zcash_primitives/src/transaction/txid.rs`/`sighash_v5.rs` and
`zcash/orchard`'s `src/bundle/commitments.rs`) before being trusted to sign
anything real. This is the same "never trust an unverified paraphrase,
re-derive independently" discipline METHODOLOGY.md already states for
on-chain reads, applied here to protocol *specification* reading.

Two real mistakes were still caught only once the actual network responded:

- **First broadcast attempt: wrong `prevout` hash.** The funding transaction
  (from the faucet) is itself a v6 transaction, whose real txid is the
  ZIP-244/229 BLAKE2b digest tree -- NOT legacy double-SHA256.
  `chains/zcash/scripts/zcash_read.py`'s own `tx` CLI subcommand still
  prints a txid computed via legacy double-SHA256 for every transaction it
  parses, which is correct for pre-v5 history but **silently wrong for any
  v5/v6 transaction** -- a real, previously-undisclosed gap in that tool,
  surfaced here for the first time (flagged, not fixed in this pass: fixing
  it means adding this file's own ZIP-244/229 digest code as a dependency of
  a read-only tool, a separate decision). Using that wrong txid as the
  spend's `prevout` produced a well-formed but incorrect transaction;
  `testnet.zec.rocks` correctly rejected it: `"could not find transparent
  input UTXO in the best chain or mempool"` -- the consensus check working
  exactly as intended, not a network problem. Fixed by taking the funding
  transaction's real txid from a third-party source
  (`testnet.cipherscan.app`, itself Zebra-backed) rather than re-deriving it
  from a tool already known to have this specific gap.
- **Second broadcast attempt: fee too low under ZIP-317.** The first fee
  used (10,000 zatoshi) matches a commonly-quoted flat "minimal transaction"
  figure, but ZIP-317's real conventional-fee formula is size-based:
  `contribution_Transparent = max(ceil(tx_in_total_size/150),
  ceil(tx_out_total_size/34))`. This transaction's 36-byte OP_RETURN payload
  pushes `tx_out_total_size` to ~81 bytes, giving `ceil(81/34) = 3` logical
  actions and a conventional fee of 15,000 zatoshi, not the 10,000 used.
  `testnet.zec.rocks` rejected the underpaid transaction with a specific,
  informative error (`"failed to verify ZIP-317 transaction rules ...
  Unpaid actions is higher than the limit"`), not a generic failure. Fixed
  by raising the fee to 20,000 zatoshi (comfortable margin over the derived
  15,000) and re-deriving the formula from ZIP-317's own raw text rather
  than reusing the flat figure.

Neither mistake reached a false claim of success: both were caught by the
network's own real validation and fixed before broadcasting again. The
**third** attempt was accepted (`errorCode 0`, the server's own
`errorMessage` field echoing the txid) and confirmed in the next block.

## 5. The real, published attestation

Full JSON: `testnet_attestation_2026-09-19.json`.
Its content (target, scores, methodology hash, publisher key, timestamp) is
reproduced here for convenience:

| Field | Value |
|---|---|
| Target | Zcash L1 (consensus-rule-change authority), `0xB8e62E6AeB4C400b6F3e66cAb69ACe55439035c3` |
| adminKeyScore / multisigScore / timelockScore / oracleAuthorityScore / crossExposureScore | 20 / 50 / 35 / 100 / 100 |
| compositeScore | 34 |
| Source | `chains/zcash/scorers.py` `score_l1()`, as published in [`data/scored_targets_2026-09-19.md`](scored_targets_2026-09-19.md) -- an already-computed, already-live-verified number, not (re-)computed for this attestation |
| `methodologyHashSha256` | `b9a0c7bba90c1e42acb2c6c6804c71c29f1bd52f4d9b3efe596cc49c6536dff0` (SHA-256 of `chains/zcash/METHODOLOGY.md` as it stood immediately before this pass's own section 8/9 edits) |
| Publisher pubkey (compressed, testnet-only, no value) | `0388e6af60fe4d0fe63248e3953165f6f13dd57f733ed7283d68f12f2acfb3b41f` |
| Publisher Testnet address | `tmDvDRYD7meGJXFoeTqtjFcrNF5378ZzaBo` |
| Publisher private key | **REMOVED 2026-09-19 (CORRECTION).** It was printed here in clear (commit 40ca1a4) and is now kept only outside the repo (pipeline `keys/zcash-testnet.json`, loaded by `chains/zcash/scripts/publisher_key.py`). It is still readable in git history, so it is treated as COMPROMISED: see the note below this table. Every value in this table stays verifiable without it (the signature verifies against the pubkey above). |
| `publishedAtUtc` | `2026-09-19T03:34:31Z` |
| `attestationCommitBlake2b256` (the value anchored on-chain) | `d722a2f753e7d4538619085272d556c5a87a4e3c27a9d531dc21ca14d23c272d` |
| `attestationSignatureDer` (ECDSA over the commit hash, by the publisher key above) | `3045022100e99f485f5927cb206ef6b62a761b27f6d09266d9df46d5b8b44999e7abf80b7a02206c4a2d7e8b1412c759c7795cb9856c3510c6b9a87120754b65c5cf1ba09b3feb` |

> **CORRECTION 2026-09-19 -- exposed publisher key.** The Testnet publisher key above was committed in clear
> in 40ca1a4 and removed from tracked files afterwards, but it remains in git history. ARO1/ARO2
> authentication rests only on the anchoring transaction being spent from `tmDvDRYD7meGJXFoeTqtjFcrNF5378ZzaBo`,
> so anyone who can read this repository could publish a forged `ARO` commitment from that address. The ARO1
> transaction `f0780a09...75e5` itself is unaffected as a historical record (it is the one this project sent,
> cross-checked above), but NO further publication may be made with this key: before any deploy_testnet
> broadcast and before the repository goes public, either rotate to a fresh, never-committed key (funding its
> address is a manual action by Spap) or add an off-chain signature of each batch by an unexposed key.
> `publish_attestation.py send` now refuses to broadcast with a key file marked `exposed_in_git_history`.
>
> **Update 2026-09-20:** the key was rotated and the ARO2 set re-anchored from a new key that was never
> committed (`data/publisher_key_exposure_2026-09-19.md`, METHODOLOGY.md 9.7). This ARO1 transaction was
> made by the exposed key and stays as a historic record of integrity and timing only.

## 6. The real Testnet transaction

| Field | Value |
|---|---|
| Network | Zcash **Testnet** (never Mainnet) |
| txid | `f0780a099f381d2a79fa4b6cab6d657293a5d307e30a7adde5ad95f7d4d575e5` |
| Block | 4,366,645 |
| Confirmed | 2026-09-19, ~03:34 UTC |
| Version | 6 (NU6.3/ZIP 229) |
| Size | 254 bytes |
| Fee | 20,000 zatoshi (0.0002 TAZ) |
| Input | `tmDvDRYD7meGJXFoeTqtjFcrNF5378ZzaBo`, 10,000,000 zat (the faucet drip) |
| Output 0 | `OP_RETURN` 36 bytes: `41524f31` (`"ARO1"`) + `d722a2f753e7d4538619085272d556c5a87a4e3c27a9d531dc21ca14d23c272d` (the commit hash above) |
| Output 1 | 9,980,000 zat change, back to the same Testnet address |
| Raw tx (hex) | `0600008098b684d85b16a5370000000098a14200010521e48f08c5d31068abf0e8b1be2d389f6cf960f54cff23b3d21d05df4ea2cd000000006a47304402203a3cc5b634e6bc2d38129371d4fd3687fc31ad7210a1023f9a8fcf8d66d22ca50220573ca720333bb3532eba0235d0f6601af6f48a1c93b8a86995406e2f2904fb4f01210388e6af60fe4d0fe63248e3953165f6f13dd57f733ed7283d68f12f2acfb3b41fffffffff020000000000000000266a2441524f31d722a2f753e7d4538619085272d556c5a87a4e3c27a9d531dc21ca14d23c272d60489800000000001976a9142e1ee4d4133c8d426b3fa1f5ed8ee1755a2e491388ac00000000` |

## 7. Independent verification (do not just trust this project's own send script)

Four independent checks, not one:

1. **The server's own SendTransaction response** returned `errorCode: 0`
   with `errorMessage` containing the txid -- lightwalletd's own
   success-response convention -- and this txid matched, byte for byte,
   this project's own from-scratch ZIP-244/229 txid computation performed
   *before* broadcasting (a genuine advance prediction, not fitted after
   the fact).
2. **A second, fresh lightwalletd read** of the confirmed transaction (a
   completely separate `GetTaddressTxids` call, made minutes later)
   independently parsed the same OP_RETURN bytes:
   `6a2441524f31d722a2f753e7d4538619085272d556c5a87a4e3c27a9d531dc21ca14d23c272d`,
   which decodes to exactly the `"ARO1"` magic and commit hash above.
3. **A third-party block explorer**, `testnet.cipherscan.app` (itself
   Zebra-backed, unaffiliated with this project), independently indexed and
   displays this exact transaction: block 4,366,645, version 6, size 254
   bytes, fee 0.0002 TAZ, expiry height 4,366,744 -- every field matching
   this project's own build output.
4. **A dedicated unit test suite**
   (`scripts/lib/tests/test_zcash_tx.py`) rebuilds this exact transaction
   from the same inputs and asserts its txid, its signature's validity
   against the real per-input sighash, its exact serialized bytes, and that
   an independent parser (`zcash_read.py`'s own, written before and for
   unrelated purposes) reads back the expected outputs -- all passing.

**How to verify without trusting any of this project's own code:**

```bash
S=chains/zcash/scripts
python3 $S/zcash_read.py tx testnet.zec.rocks:443 tmDvDRYD7meGJXFoeTqtjFcrNF5378ZzaBo 4366640 4366650
# -> should print version=6, one output value=0 with the OP_RETURN script
#    above, one output value=9980000 with the P2PKH change script above.
```

or open
`https://testnet.cipherscan.app/tx/f0780a099f381d2a79fa4b6cab6d657293a5d307e30a7adde5ad95f7d4d575e5`
directly.

## 8. What this does and does not prove

- **Does prove:** a fully transparent, from-scratch-implemented Zcash v6
  transaction (secp256k1 keygen/signing, ZIP-225 serialization, ZIP-244/229
  digest algorithm) can be built and correctly validated by the real
  network without any third-party Zcash wallet library, and that this
  project's own already-computed authority score for Zcash L1 can be
  anchored on Zcash Testnet today, at negligible cost (0.0002 TAZ), with a
  fully reproducible verification path.
- **Does not prove:** that this specific mechanism is what should run in
  production, that a Mainnet key or funds are involved (none are, by
  design), or that every future attestation format will fit the same 36-byte
  commitment shape unchanged (it will, by construction: the commitment is
  always a fixed-size hash regardless of the attestation's own size).
- **Genuinely still open**, disclosed rather than glossed over: this is a
  single manual run, not a production publishing pipeline; no code exists
  yet to automate "score changes -> new attestation -> new OP_RETURN tx" on
  a schedule the way `scripts/update_scores.py` does for the EVM
  ecosystems' on-chain contract pushes. That automation is future work, not
  attempted here.
