# Keys: what is signed, how a key would be changed, and the keys used so far

*Written on 30 October 2026. The procedure below has not been used yet: no rotation of the signing key has happened. It describes how a rotation would be made, so that it is written down before it is needed; it is the procedure the maintainer would follow, not a promise of a date. Nothing here is run by an automated job.*

## The signing key of the Watch

Each Watch run writes `signature.json`: the manifest of the published files (`watch/API.md` lists the exceptions), the head of the event-log chain and the commit, signed with Ed25519 by a key that the workflow reads from a secret. The public key in use at the Watch run of 29 October 2026 (12:58:54 UTC; its signature record is dated 13:39:57 UTC) is:

`11baca3ef6a69de4901c185f6cbbd3f93318fbb74f9961a8d39aead841adf409`

It is written in `watch/API.md`, `docs/TOOLS.md`, in `scripts/audit_public.py` (`PINNED_KEYS`), in the installable package and its README, and in the dashboard script of the site (`ARO_PUBKEY`), which is built outside this repository. The runs have been signed since 2026-10-11 21:18 UTC; before that they were not. All these copies are published by the maintainer, so a change of the key together with the files would not be seen by someone who only compares with them. A copy kept by someone else does not exist (see SECURITY.md).

## How a rotation would go

1. **Announce.** A commit on `main` would add the new public key to `PINNED_KEYS` in `scripts/audit_public.py` (the comment of that variable already says that a rotation is a commit that adds the new key there first), to the pin of the dashboard script of the site, to the package and to every file of this repository that contains the key (`grep -rl 11baca3e`), with the date from which it applies, and a dated entry in CHANGELOG.md. The notice would come before the first run signed with the new key; the maintainer would choose the notice period and state it in the notice.
2. **Overlap.** For the period stated in the notice, both keys would be accepted by the checks: `python3 scripts/audit_public.py --pin KEY` accepts a key given on the command line. The current format of `signature.json` carries one signature, so a run cannot carry two. Signing each run with both keys needs a second record next to `signature.json` and is not implemented. Until it is, the switch would happen at a stated run: the last run signed by the old key and the first signed by the new one are named in the notice.
3. **Revocation.** The old key would be added to the table below under "Retired", with the date and time of the last run it signed and the reason (planned change, or suspected compromise), and removed from `PINNED_KEYS`, from the package and from every file that contains it. From that date a signature by the old key on a later run is to be treated as invalid; the scripts do not check dates of keys, they check the list of pinned keys. If the reason is a compromise, the notice says from when the key is considered compromised; files signed before that date are as trustworthy as the date is credible, and `scripts/audit_public.py --ref COMMIT` audits a past run as it was committed.
4. **Check.** Anyone can verify with the new key given explicitly (`--pin`) without relying on this repository's copy of it.

## Keys listed so far

| Key | Used for | Status |
|---|---|---|
| `11baca3e...f409` (Ed25519) | signature of the Watch manifest | in use; retired keys: none |

## Zcash testnet publication keys

The Zcash tab anchors a commitment in an `OP_RETURN` output of a Zcash **testnet** transaction. These keys hold no value and are for testnet only. The first publisher key was committed in clear in the history of the private repository, was rotated on 2026-09-19, and is listed here so that nobody takes a signature by it for more than it is. A signature by it proves that someone with access to that history signed, not a specific publisher. `ARO1` and `ARO2` are two formats: `ARO1` commits to one score, `ARO2` to the whole set of scores of the time.

| Publication | Date (UTC) | Transaction | Targets | Commitment (start) | Publisher address (testnet) | Status |
|---|---|---|---|---|---|---|
| ARO1, first proof of concept | 2026-09-19 | `f0780a099f381d2a79fa4b6cab6d657293a5d307e30a7adde5ad95f7d4d575e5` | 1 | not recorded here | `tmDvDRYD7meGJXFoeTqtjFcrNF5378ZzaBo` | a commitment that this repository cannot re-check (its attestation file is not published: it embeds a legacy account name and is hashed byte for byte); publisher key exposed |
| ARO2, first anchor | 2026-09-19 21:17:12 | `18791a4cdaa00b5d0aefc1dcce5576c6e43ea9e203db03b0d973772dfe32cc37` | 7 | `74f6ba04...` | `tmDvDRYD7meGJXFoeTqtjFcrNF5378ZzaBo` | a valid commitment; publisher key exposed |
| ARO2, re-anchor from the new key | 2026-09-19 23:15:28 | `eeaa894c3c46814f7228a7ecf2be84c0006c1154b5101688dd413d9a419689c0` | 7 (same commitment) | `74f6ba04...` | `tmCj66nwJY8xgNj3jwEyUMhLGmZzbHYiHY8` | current key; funded by one sweep from the exposed address, so the chain alone does not show a different holder |
| ARO2, six live targets | 2026-09-20 19:23:45 | `462de12bf72e5e635a1feed4a4cedb02c03f17745bd15176787f8f5f8fcd701c` | 6 | `214f8105...` | `tmCj66nwJY8xgNj3jwEyUMhLGmZzbHYiHY8` | latest; the seventh target was retired from the live set on 2026-09-20 |

Where to read them: `chains/zcash/data/` (the attestation files, except the ARO1 one) and `chains/zcash/METHODOLOGY.md`, sections 9.5 to 9.8. The dashboard fetches each ARO2 transaction, decodes the `OP_RETURN` and recomputes the commitment in your browser.

## Rehearsal of 30 October 2026

The procedure above was rehearsed on 30 October 2026 on a copy of the repository and of the Watch files, with two test keys: the variable `WATCH_SIGNING_KEY` was set to test seeds, and the real signing key was not read or used. What the rehearsal showed:

1. A run signed by the old key verifies with `sign_run.py --verify --pin OLD` and with `audit_public.py --pin OLD`. The options differ: `sign_run.py --verify --pin KEY` accepts only the keys given; `audit_public.py --pin KEY` and `authority_check.py --verify-signature --pin KEY` add a key to the published one.
2. Once the new key is added to `PINNED_KEYS` in `scripts/audit_public.py`, `audit_public.py` accepts runs signed by either key with no option.
3. A run cannot carry two signatures: `signature.json` holds one `public_key` and one `signature`. The overlap is therefore the switch at a stated run (the last run signed by the old key, the first signed by the new one), not a double signature.
4. Once the old key is removed from `PINNED_KEYS`, an older run fails the audit with "valid Ed25519 signature, but by a key this audit does not pin", unless the auditor passes `--pin OLD`.
5. `sign_run.py --verify` also compares the hashes of the code that produced a run (every `.py` file under `scripts/` and `chains/` except the tests, `rules.json`, the workflow) with the current checkout, so any later change of these files, the change of `PINNED_KEYS` included, is reported as a code difference on older runs. `audit_public.py` does not compare the code: it checks an older run's files and signature (`--watch DIR`, or `--ref COMMIT` for a commit of the `watch-data` branch), with `--pin OLD` once the old key is removed. `--ref` was not rehearsed.
6. The installable package trusts the key built into its release, or a key given with `--trust-key` (or the environment variable `AUTHORITY_RISK_TRUSTED_KEYS`). After a rotation, a package release that carries the new key is needed; until then its users pass `--trust-key`.

Every `audit_public.py` run of the rehearsal exited 1 for another reason: the copied Watch run was 25 hours old ("watch alive"). Results 1, 2 and 4 are those of its signature line.

Not rehearsed: the pin in the dashboard script of the site, which is outside this repository.

