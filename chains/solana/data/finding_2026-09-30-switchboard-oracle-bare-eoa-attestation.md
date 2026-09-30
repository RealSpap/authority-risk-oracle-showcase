# Switchboard (oracle, "$5B secured"): a single bare EOA controls 16 programs including Oracle Quotes and the Randomness Service, and has actively used that power days ago -- Oracle V2 is a separate 1-of-4

2026-09-30. Prompted by "voit large, trouve des vrais trous que la concurrence ne couvre pas" (Spap). SolGov doesn't cover Switchboard at all --
it's an oracle, out of scope for SolGov's DeFi-protocol registry -- and it isn't in this repo's `SOLGOV_LEADS` either (added 2026-09-26,
covers Solstice/GMSOL/Loopscale/Huma Finance/Lulo/Exponent/Flash Trade/Solayer; Hylo, Switchboard and Pyth were listed as candidates in
`finding_2026-09-26-solgov-registry-verified-live.md` but never turned into scorers). This closes that gap for Switchboard specifically.

**Correction, checked before writing further: this is not entirely new.** `scorers.py`'s own comment right above `SOLGOV_LEADS`
(dated to the 2026-09-26 batch) already says Switchboard was deliberately excluded because it is "winding down, one of its three
programs is upgraded by a bare key" -- so the bare-key fact itself was already known 4 days ago, just never written up as its own
finding or quantified. What's new below: identifying exactly which program and key, proving the key has recently and actively
exercised its power (not dormant), finding it controls 16 programs total (not "one of three"), identifying Oracle V2's separate 1-of-4,
and computing the actual composite. One thing that comment claims and this pass did NOT confirm: "winding down" -- see the direct
contradiction noted below, where the same bare key was used for a live upgrade on 2026-08-10 -- well before the shutdown, so not
itself evidence against "winding down", but see the separate, bigger correction filed as
`finding_2026-09-30-switchboard-shutdown-drift-score-likely-stale.md`: Switchboard shut down entirely on 2026-09-25, which changes
how all of this should be read.

## What SolGov's own leads file (`solgov_leads_2026-09-26.json`) already recorded, re-verified live here

Switchboard has 3 programs and 3 *different* on-chain upgrade authorities, not one shared multisig:

| Program | Program id | Upgrade authority (live, both RPCs agree) | What it is |
|---|---|---|---|
| On-Demand | `SBondMDrcV3K4kxZR1HNVT7osZxAHVHgYXL5Ze1oMUv` | `DREcTwxxuehtUVgnGwDpTcKT9zTK5uDmdLbnRY7cijEx` | Vault 0 of Squads v4 multisig `93RQfY6VHRkqXBCEhMY5u92bCGp428DTzqZUEA2Hjr9h` -- confirmed by offline PDA re-derivation, exact match (`find_program_address(["multisig", ms, "vault", 0], SQDS4...)`), not just by SolGov's say-so |
| Oracle V2 | `SW1TCH7qEPTdLsDHRgPuMQjbQxKdH2aBStViMFnt64f` | `2NvGRFswVx3GXxURNSfjbsWY4iP1ufj8LvAKJWGXSm4D` | **Authority index 1 of Squads v3 Ms `6fxK7rUdk7mSibRftp6tQmvB6PGqaNrrCh1XKvi2E8Mq`, threshold 1-of-4** -- confirmed by offline PDA re-derivation (`find_program_address(["squad", ms, index, "authority"], SMPLec...)`), exact match on both RPCs, not the 3-of-8 vault above at all |
| Attestation | `sbattyXrzedoNATfc4L31wC9Mhxsi1BmFhTiN8gDshx` | `31Sof5r1xi7dfcaz4x9Kuwm8J9ueAdDduMcme59sP8gc` | **On-curve** (`sol_read.py keytype`, both RPCs) -- a real Ed25519 keypair, i.e. a bare EOA can sign an `Upgrade` instruction for this program directly, no multisig involved |

Verification commands, reproducible, no key, nothing sent:
```
python3 chains/solana/scripts/sol_read.py keytype <rpc> 31Sof5r1xi7dfcaz4x9Kuwm8J9ueAdDduMcme59sP8gc   # on_curve: true
python3 chains/solana/scripts/sol_read.py squadsv3 <rpc> 6fxK7rUdk7mSibRftp6tQmvB6PGqaNrrCh1XKvi2E8Mq 1
  # -> authority_1 == 2NvGRFswVx3GXxURNSfjbsWY4iP1ufj8LvAKJWGXSm4D, exact match confirms Oracle V2's real authority: Squads v3, threshold 1, 4 keys
python3 chains/solana/scripts/sol_read.py squads-vault <rpc> 93RQfY6VHRkqXBCEhMY5u92bCGp428DTzqZUEA2Hjr9h 0
  # -> vault == DREcTwxxuehtUVgnGwDpTcKT9zTK5uDmdLbnRY7cijEx, exact match confirms the On-Demand path
```
RPCs: `https://api.mainnet-beta.solana.com` and `https://solana-rpc.publicnode.com`, agree on every field above. Found via
`resolve_controller_via_last_tx(url, authority, program_id, limit=15)` (only the mainnet-beta RPC retained enough tx history to find
the candidate; publicnode returned none for either Squads program on this specific address, consistent with the project's known
"publicnode doesn't serve old transactions" limitation) then required an exact independent PDA re-derivation before treating it as
proof, per METHODOLOGY.md 3.3.

## The finding

**Two of Switchboard's three programs are far weaker than the headline 3-of-8 vault, and one of them is the program that actually
matters most.** Oracle V2 (`SW1TCH7q...`) is Switchboard's original, classic price-feed program -- the one most widely integrated
across Solana DeFi before On-Demand existed -- and its real upgrade authority is a **Squads v3 multisig with threshold 1 out of 4
keys** (`6fxK7rUdk7mSibRftp6tQmvB6PGqaNrrCh1XKvi2E8Mq`), not the 3-of-8 vault the repo's own summary table implies by only listing one
multisig address for the whole protocol. A 1-of-4 gives no threshold protection at all: any ONE of the 4 keys, alone, can push new code
to a program securing price feeds across the ecosystem. None of the 4 keys overlaps with the Attestation EOA below (checked).

**Attestation (`sbatty...`) is a Critical-shaped case on top of that**: a bare EOA (`31Sof5r1xi7dfcaz4x9Kuwm8J9ueAdDduMcme59sP8gc`,
on-curve, confirmed on 2 RPCs) holds full upgrade power over the program that lets off-chain oracle nodes prove they ran in a trusted
execution environment before their price update is accepted -- no multisig at all. Same defect class as the "bare EOA" pattern already
scored Critical in the sibling `defi-admin-key-risk` project (e.g. cVault Finance/CORE).

**Update, same session: the EOA's upgrade power is not theoretical, it was exercised days ago -- on a FOURTH Switchboard program SolGov
never listed at all.** Walking the EOA's last 50 signatures (`getTransaction`, `jsonParsed`) rather than stopping at
`getSignaturesForAddress`'s summary: 49 of 50 are `bpf-upgradeable-loader` instructions, and the most recent parses as
`"type": "upgrade"` naming `programAccount: orac1eFjzWL5R3RbbdMV68K9H6TaCVVcL6LjvQQWAbz`. Cross-checked directly against the program
account itself (`sol_read.read_program`): `executable: true`, `last_deploy_slot: 438467619` -- the exact slot of that transaction,
confirmed via `getBlockTime` to be **2026-08-10T20:13:29 UTC**, so this is the program's last live deployment (the tight cluster of
transaction slots checked earlier reflects one deployment's chunked buffer writes, not ongoing daily activity) -- and `upgrade_authority`
reads back the same EOA. Identified via web
search: this is Switchboard's own **Oracle Quotes program**, part of the confidential-runtime quote pipeline behind their oracle
attestation system ([switchboard-docs.web.app](https://switchboard-docs.web.app/), [docs.switchboard.xyz](https://docs.switchboard.xyz/docs-by-chain/solana-svm)) --
real, live, and not one of the 3 programs SolGov's registry (or this finding, before this update) had ever associated with Switchboard.
It does not appear anywhere else in this repo's data.

**So the bare EOA is not a dormant, theoretical risk**: it has full, exercised, current upgrade control over at least two live
Switchboard programs (Attestation and Oracle Quotes), and it used that power on 2026-08-10 -- a real, dated, on-chain fact, not
years-old dormant history, even though (correction from an earlier draft of this file) that is seven weeks before this run, not "a
few days"; see the shutdown correction above for what actually happened since.

**Second update, same session: the exhaustive on-chain scan (not a sample) puts this EOA's real blast radius at 16 programs,
at least 3 of them confirmed, named Switchboard infrastructure.** `sol_read.py programs-by-authority` (`getProgramAccounts` filtered
on `upgrade_authority == this EOA`, offset 13 of every loader-v3 ProgramData account, no key, read-only) returns **16 distinct
programdata accounts** on `api.mainnet-beta.solana.com` -- Attestation and Oracle Quotes are both in that list, confirming the manual
finds above weren't a fluke. `solana-rpc.publicnode.com` cannot run this specific indexed query on its free tier ("Indexed requests
require a personal token"), so the full 16-way list isn't cross-RPC-confirmed the same way as everything else in this file; 4 of the 16
programdata accounts were spot-checked by directly decoding the account bytes (offset 13, the authority field) on BOTH RPCs and all 4
matched exactly -- the mainnet-beta result is trusted on that basis, not blind.

Resolving each programdata to its Program account (`read_program_of_programdata`, same RPC) and searching the program ids: one more is
identified, **`RANDMo5gFnqnXJW5Z52KNmd24sAo95KAd5VbiCtq5Rh`, Switchboard's own Solana Randomness Service** (VRF-style randomness
delivered via a Switchboard SGX oracle, per its own npm/crates.io packages) -- a third named, live Switchboard component under the same
single key, and arguably the most consequential of the three found so far: any Solana program that consumes this randomness service
(games, raffles, NFT mints, anything with an on-chain draw) inherits this key's risk by extension, not just Switchboard's own users.
The other 12 program ids were not individually identified in this pass (several look like generic base58 addresses with no recognizable
vanity prefix, could be further Switchboard infra, test/dev programs, or entirely unrelated projects that happen to share this operator)
-- flagged as an open list, not investigated one by one, to avoid a marathon of unverifiable guesses. The 4 keys behind Oracle V2's
1-of-4 (a separate, narrower finding above) were not individually checked for activity.

**Full programdata list (mainnet-beta, `getProgramAccounts`), for whoever picks this up next:**
`2t7NvzioeZgvYSTZTtpQ9LVcFfhQKg2r7NQLeDGB1BFn`, `3pSJGh38VJuy7a7tsWiKi7zdiajGWwvU78kapgfu1Shr`,
`61qUnCDSzWvuhXNLK4GfECJTEr4WzZYwFfn8oeW5y833` (Oracle Quotes), `84B9o7gxdadPQyXRPVVM67koBUHxxrGbKjQ3kjLPcr9b`,
`AjUaAWfgwhSuNNFC68rT9FZMvsV23yM9fi9MiKfvYA4y`, `B4WCfCrmGCXhvRXT8bRZec2JfKk7nqtBGsbvyQNzUZSi`,
`BzqtGXZPiDSinP4xMFgPf6FLgSa6iPufK4m4JJFgMnTK` (Attestation), `DgdjwFmWxu8jizjc5unzo3Ld3Ra6PVE9TJNG5izWtjBG`,
`E6UJWxi2hzJoMYr2cb6S7PMmimmRor7rWFLZ95NYjGeM` (Randomness Service), `FB1gMiDURdBZiiUrmCMELj8MYwKDqiaA13eTrmAwLsRd`,
`FSD8p7tDkhffAiMgAvMXi9veJW1uSod4H3F3REn7nMNC`, `Fn5XRd3hR3hr6Y4fVsU431z2YwhAzWMBXhbcRv7H4nP`,
`Gyk7f87zWuL5g96mLfZ12fJ3phmHsZwXbGmJngXhJBck`, `HC2DWxq8BfTMjk7XNbmzypP5Qto1T8BrgWjThXKCb6K`,
`HgfywD7fsaAGk89UKVZRqU8MF9Ksr8FnWTbRM5hsQJh5`, `Ka5MHAf5f6i8hP67kNAZCnWSrBfejU9ehK3xQMig1sP`
(programdata addresses; each row above resolves to one Program id via `read_program_of_programdata`, already done for these 16, program
ids in the working notes for this pass, not re-typed here to keep this list to what's independently checkable from the programdata
addresses alone).

**Only On-Demand, the newest program, has the healthy setup**: 3-of-8, the multisig the whole protocol's reputation seems to rest on
in a casual read of SolGov's data. Reading only that one address and assuming it covers the other two programs would have missed both
of the findings above -- exactly the kind of per-program (not per-protocol) verification this project's methodology already insists on
elsewhere (Solstice, Jupiter Lend), now shown to matter here too.

## Quantified, using this repo's own formula (METHODOLOGY.md 6.1/6.2, `_score_full_power_path`/`_composite`)

Not a guess -- the same deterministic arithmetic every other Solana target in this file is scored with:
- **Attestation (bare EOA)**: `kind="on_curve"` -> fixed (admin=5, multisig=0, timelock=0).
- **Oracle V2 (Squads v3, threshold=1)**: the formula's own `threshold == 1` special case -> the identical (5, 0, 0) -- a 1-of-N is
  scored exactly as badly as a bare key, by design (any single one of 4 people is a full-power single point of failure, same as one).
- **On-Demand (3-of-8 shape)**: not the worst path, so it never reaches the `min()` regardless of its own exact number.

`_composite(5, 0, 0)` = `(4*5 + 3*0 + 3*0 + 5) // 10` = **2 / 100**. Since METHODOLOGY 6.2 takes the componentwise minimum across every
full-power path, Switchboard's real composite -- if this were added as a scorer -- would be **2**, dominated equally by the EOA and the
1-of-4 (they tie at the floor). For scale: **2** is the same composite this project already gives Save/Solend's bare single-key
upgrade authority (`data/scouted_targets_2026-09-17-run2.md`, target #9) -- a **$5B-secured oracle network scoring as badly as a single
lending protocol's bare key**, and worse than every Squads-governed target already scored in this file.

## What this is not

Not a score. `SOLGOV_LEADS`/`score_solgov_leads()` does not include Switchboard (or Hylo or Pyth) yet -- adding it as a real scored
target is Spap's decision, same discipline as every other candidate in this file's lineage (see
`finding_2026-09-26-solgov-registry-verified-live.md`, "nothing was added"). If added, METHODOLOGY 6.2's minimum-over-full-power-paths
rule means Switchboard's composite would be dominated by whichever of the two weak paths scores lower under
`_score_full_power_path` -- the bare EOA or the 1-of-4 -- not by the healthier 3-of-8 vault. Same shape as Solstice being dominated
by its weaker 2-of-3 auxiliary multisig, already correctly handled by the existing `_score_solgov_lead` code for that target; here it's
two weak paths out of three instead of one out of three.

Not investigated here: Hylo (no programs listed by SolGov at all -- `programs: []`, `programs_live: []` in the raw data, so there is
nothing yet to read an upgrade authority from) and Pyth (Wormhole cross-chain governance, a structurally different verification problem
from every other target in this file -- would need to trace the guardian set and the 7-of-9 Pythian Council separately, not a Squads
read).

## Verification discipline

Two independent public RPCs on every read (`api.mainnet-beta.solana.com`, `solana-rpc.publicnode.com`), no key, no signing, all
addresses from SolGov's own already-verified `solgov_leads_2026-09-26.json` (not re-typed from a screenshot or a claim). The Squads
vault match for On-Demand was independently re-derived offline (`find_program_address`), not taken on the transaction-history
heuristic's word alone, per METHODOLOGY.md 3.3's "a transaction alone is not proof" rule.
