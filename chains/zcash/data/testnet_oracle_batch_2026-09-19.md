# Zcash native oracle, whole set: ARO2 anchored on Testnet, 2026-09-19

Extends `data/testnet_oracle_poc_2026-09-19.md` (ARO1: one score, Zcash L1) to
every target `chains/zcash/scorers.py` `score_all()` returns, in ONE on-chain
commitment. The format was already built and unit-tested, but never broadcast,
by commit `7833263` (`scripts/attest_scores.py`, METHODOLOGY.md 9.5). This run
adds the ECDSA signature over the set, a broadcast script
(`scripts/publish_batch.py`) and the real Testnet transaction. The ARO1
attestation and its transaction are untouched.

Design and what it proves: METHODOLOGY.md 9.6. This file is the evidence trail
for the run: every number below was read live, not carried over.

**Constraints respected:** Zcash TESTNET only (`testnet.zec.rocks`, consensus
branch 0x37A5165B); the existing zero-value Testnet publisher key, loaded from
outside the repo and never printed; no faucet, no funding request (the funds
were the ARO1 change output already at the publisher address); no Mainnet write.

## 1. What was anchored (7 targets)

Re-derived from a FRESH live `score_all()` run immediately before signing, under
the methodology hash pinned in the batch header. The run aborts on any drift.

| Target (canonical order) | Admin | Multisig | Timelock | Oracle | Cross | Composite | L1 cap | Leaf (BLAKE2b-256) |
|---|---|---|---|---|---|---|---|---|
| `0xB8e62E6AeB4C400b6F3e66cAb69ACe55439035c3` (Zcash L1) | 20 | 50 | 35 | 100 | 100 | 34 | n/a | `5cf1bf5bb173f7fc...` |
| `keyring1k6vc6vhp6e6l3rxalue9v4ux` (Zenrock zenZEC keyring) | 65 | 60 | 0 | 100 | 100 | 44 | n/a | `14f29ce9df4577bd...` |
| `t1RBiXrLRdrHgsuSGQEusG2wCzPFczEVMfT` (Maya Asgard vault A) | 65 | 100 | 0 | 100 | 100 | 56 | n/a | `68b579707fd3e0da...` |
| `t1VtnnhTYhmADh7L2uKU3Sev7GscBHT6HfE` (Maya Asgard vault B) | 65 | 100 | 0 | 100 | 100 | 56 | n/a | `d634d9813d91b350...` |
| `t3cFfPt1Bcvgez9ZbMBFWeZsskxTkPzGCow` (ZCG funding stream) | 50 | 39 | 0 | 100 | 100 | 32 | 32 | `517cd168ee027743...` |
| `t3ev37Q2uL1sfTsiJQJiWJoFzQpDhmnUwYo` (ZIP 271 lockbox) | 50 | 39 | 0 | 100 | 100 | 32 | 32 | `947c434b53c737ff...` |
| `zec.omft.near` (NEAR PoA bridge, ZEC) | 5 | 18 | 0 | 100 | 100 | 7 | n/a | `318f930e70227d7a...` |

Same values as `data/scored_targets_2026-09-19.md`. Merkle root
`a323d59c09351e9cda29f27cab34ad2078568995b7e911bc40f1c0e3012c3c93`, commitment
`74f6ba041e253bb75e523e1b0d00422e44221c7a0240757cd1a40ad15d513662`, methodology
pin `8a3a1042690bfda50555667496ab9510bc86fd2d250cdb6a56334600996f4bb5`.

## 2. Preconditions, checked before broadcasting

| Check | Result |
|---|---|
| Bundle re-derives from its own records; 7/7 inclusion proofs valid | yes |
| Fresh live `score_all()` under the pinned methodology hash | MATCH, 7 targets |
| Balance at `tmDvDRYD7meGJXFoeTqtjFcrNF5378ZzaBo`, two independent reads | 9,980,000 zat on `testnet.zec.rocks` and on `api.testnet.cipherscan.app`, equal to the one UTXO to spend (`f0780a09...d575e5:1`, the ARO1 change output) |
| ZIP-317 fee required | 15,000 zat. `conventional_fee = 5000 * max(2, logical_actions)`, `logical_actions = max(ceil(tx_in_total_size / 150), ceil(tx_out_total_size / 34))` (formula re-read from the raw ZIP text). Sizes of this shape: input 148 bytes, outputs 47 (OP_RETURN) + 34 (P2PKH) = 81, so `max(1, 3) = 3` actions, 15,000 zat. Consistent with the two real verdicts on the ARO1 tx (10,000 rejected, 20,000 accepted) |
| Funds sufficient | yes: 9,980,000 - 15,000 = 9,965,000 zat change |
| Publisher key file | present outside the repo, matches the known pubkey and address, `exposed_in_git_history` false (see section 5) |

## 3. The transaction

| Field | Value |
|---|---|
| Network | Zcash Testnet (never Mainnet) |
| txid | `18791a4cdaa00b5d0aefc1dcce5576c6e43ea9e203db03b0d973772dfe32cc37` (predicted before broadcasting from the from-scratch ZIP-244/229 digest, echoed back by the server) |
| Block | 4,368,539, time 2026-09-19T21:17:12Z (lightwalletd `GetBlock`) |
| Version / size | 6 (NU6.3, ZIP 229) / 255 bytes |
| Fee | 15,000 zat (0.00015 TAZ), accepted at the first attempt |
| Expiry height | 4,368,638 (tip 4,368,538 + 100) |
| Input | `f0780a099f381d2a79fa4b6cab6d657293a5d307e30a7adde5ad95f7d4d575e5:1`, 9,980,000 zat |
| Output 0 | `OP_RETURN` 36 bytes: `41524f32` (`"ARO2"`) + `74f6ba041e253bb75e523e1b0d00422e44221c7a0240757cd1a40ad15d513662` |
| Output 1 | 9,965,000 zat change to `tmDvDRYD7meGJXFoeTqtjFcrNF5378ZzaBo` |
| ECDSA signature over the 32 commitment bytes | `30440220553d06409f49e3df922ba5e2bee4e39e706cbd6fd01cb25b1dc3a8f203aad6c302206e511340897f78a2c56daa82ac312af5cfc7373b68fe249bdc0058bba4f8ec6a` (RFC 6979, low-S, DER) |
| Balance left at the publisher address | 9,965,000 zat (0.09965 TAZ), read from `testnet.zec.rocks` after confirmation (at the time of this run; that address now holds 0, see section 7) |
| Raw tx (hex) | in `testnet_attestation_v2_2026-09-19.json`, `anchor.rawTxHex` |

Three independent confirmations, none of them this project's own parser alone:
1. `SendTransaction` returned `errorCode 0` with the predicted txid as its message.
2. A separate lightwalletd `GetTaddressTxids` read returned raw bytes identical to
   what was signed, at height 4,368,539.
3. `api.testnet.cipherscan.app` (third party, Zebra-backed) lists the transaction
   in block 4,368,539, version 6, 255 bytes, fee 15000 zat, and its `/raw` hex is
   identical to the bytes signed.

## 4. Verify without trusting this project's code

```bash
# 1. read the OP_RETURN from the chain (any lightwalletd or explorer): expect 41524f32 + the commitment
curl -s https://api.testnet.cipherscan.app/api/tx/18791a4cdaa00b5d0aefc1dcce5576c6e43ea9e203db03b0d973772dfe32cc37/raw
# 2. recompute leaves -> Merkle root -> commitment from the file's records, verify every inclusion proof
python3 chains/zcash/scripts/attest_scores.py verify chains/zcash/data/testnet_attestation_v2_2026-09-19.json
# 3. same, and additionally re-derive from a fresh live score_all() (scores may have moved since: DRIFT lines say which)
python3 chains/zcash/scripts/attest_scores.py verify chains/zcash/data/testnet_attestation_v2_2026-09-19.json --live
# 4. unit tests pinned to the real transaction bytes
python3 -m unittest scripts.lib.tests.test_zcash_batch_anchor -v
```

The dashboard's Zcash tab does step 1 and 2 in the browser (BLAKE2b-256 in JS)
and prints MATCH or MISMATCH. The methodology pin is checked with
`git show 783326342d5bbc05c07cd43f649e8878a78353d6:chains/zcash/METHODOLOGY.md | sha256sum`.

## 5. Publisher key state, stated plainly

The key's private half was committed in clear in `40ca1a4` and stays readable in
the private repo's history (`data/publisher_key_exposure_2026-09-19.md`). At the
time of this run the out-of-repo key file (pipeline `keys/zcash-testnet.json`)
carried a `send_guard_lifted` record: dated 2026-09-19, by Spap, "decision
explicite dans le chat", risk accepted ("anyone who reads the private repo's
history can forge an ARO batch from this address; a signature by it proves
'someone with access to the repo', not a specific publisher"), with the flag
`exposed_in_git_history` set to false only so that `send` does not refuse and
`was_exposed_in_git_history` kept true. This run used that state as found. The
decision itself was made in a chat this run did not see: what is checked here is
the file's record, not the conversation.

Consequence for what the anchor proves: see METHODOLOGY.md 9.6 "does NOT prove".
`publish_batch.py send` still refuses any key file marked exposed (unit-tested).

## 6. Not verified / open

- The scores are what this project's own scorer computed from public reads; the
  anchor does not make them true (METHODOLOGY.md 9.6).
- Nothing on Zcash consumes the commitment. There is no on-chain check of the
  ECDSA signature (transparent scripts cannot verify it): the chain stores only
  the hash.
- The set is the 7 targets `score_all()` returned at that moment. The two Maya
  Asgard vaults are the currently active ones and can change, which changes the
  set and needs a new batch.
- No automation: this is a second manual run. `publish_batch.py send` makes it
  repeatable, not scheduled.
- Remaining publisher balance was 9,965,000 zat at the time of this run (since swept, see
  section 7); nothing else has been funded or requested.
- The Zcash phase in the docs is not advanced by this run (a phase transition is
  a maker-checker decision, AGENTS.md).

## 7. Update 2026-09-20: the same commitment re-anchored from a rotated key

The publisher key used in this run was later rotated (`data/publisher_key_exposure_2026-09-19.md`,
METHODOLOGY.md 9.7). Its remaining 9,965,000 zat went to a new address in one sweep
(`d2b5a319...`, block 4,368,630), and the identical ARO2 commitment was anchored again from that
address, signed by the new key: txid
`eeaa894c3c46814f7228a7ecf2be84c0006c1154b5101688dd413d9a419689c0`, block 4,368,633
(2026-09-19T23:15:28Z), file `data/testnet_attestation_v2_reanchor_2026-09-20.json`. This run's
own record above is unchanged: it was made by the exposed key and still proves integrity and timing
only.

