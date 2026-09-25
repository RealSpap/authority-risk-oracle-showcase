# Wormhole Core Bridge: Guardian quorum traced, doesn't fit the k-of-n model -- 2026-09-25

Documentation only -- **no `scorers.py` entry created for the Core Bridge itself.** This
was looked at as a candidate target (`worm2ZoG2kUd4vFXhvjh93UUH596ayRfgQ2MgjNMTth`, the
Wormhole Core Bridge, i.e. the cross-chain messaging program, not the "Portal" token
bridge), but its authority structure is a genuinely different archetype from every target
already in this repo, not a k-of-n multisig with an undecoded admin. Recorded here so the
next pass doesn't re-scout it from scratch and doesn't try to force it into
`multisigScore`.

Every value below is read live against Solana Mainnet Beta today
(`https://api.mainnet-beta.solana.com`), read-only, no keys, no signing.

## GuardianSet (current, index 7)

PDA `6YLGQQEweF82hbPSWCSeJqifWyT8Pm4QXa3mWSLwjYSh`, seeds
`["GuardianSet", index as u32 big-endian]`, bump 255 -- re-derived offline with
`sol_read.find_program_address` and matches the live address exactly.

- `index` = 7, `keys.len()` = 19 (19 secp256k1 public keys, 20 bytes each -- Ethereum-style
  addresses, not Ed25519 pubkeys).
- `expiration_time` on this account = 0 (not yet superseded -- this is the currently active
  set; a fresh future GuardianSet update would stamp the *old* set's `expiration_time` with
  `now + guardian_set_expiration_time` from the Bridge config below, not this one).

## Bridge config (fee & grace window)

PDA `2yVjuQwpsvdsrywzsJJVs9Ueh4zayyo5DYJbBNc3DDpn`, seeds `["Bridge"]`, bump 255 -- also
re-derived offline and matches.

| Field | Value |
|---|---|
| `guardian_set_index` | 7 (matches the active GuardianSet above) |
| `guardian_set_expiration_time` | 86400 (seconds) -- the 24h grace window an old guardian set stays valid for after rotation |
| `fee` | 100 lamports (per `postMessage`) |
| `last_lamports` (fees accumulated so far) | 9,537,044,558 lamports = ~9.537 SOL |

## Guardian quorum: 13-of-19, matches the code exactly

Wormhole's own quorum formula (`solana/bridge/program/src/api/post_vaa.rs`):
`(len(guardian_set) * 10 / 3) * 2 / 10 + 1`, integer division throughout. For 19 guardians:
`(19*10/3)=63` (integer division) `-> 63*2/10=12` `-> 12+1=13`. **13-of-19**, verified by
direct arithmetic against the real formula, not read off documentation (docs describe it in
prose as "more than 2/3", which for 19 is also 13, but the exact formula was checked because
the repo's own convention distrusts prose descriptions of quorum math -- see
`METHODOLOGY.md` on hardcoded constants).

## Upgrade authority: no bare key, locked behind the same quorum

The program's live upgrade authority is `2rCAC1VKz5YP1jZTHcVfWDhHMs2iEruUaATdeZe5Fjk5`,
which is itself the program's own PDA (seed `b"upgrade"`, bump 255, re-derived offline and
matching). `getAccountInfo` on that PDA returns `null` -- no account exists there, so there
is no on-chain state a key could point to and nothing to "own" it directly.

Because the PDA is derived from the Core Bridge program's own id, only the Core Bridge
program itself can sign for an upgrade (via `invoke_signed`), and the program's own
instruction set only allows that inside its governance-VAA handler -- i.e. an upgrade can
only execute as the result of a Guardian-signed governance VAA, gated by the same 13-of-19
quorum above. There is no separate "upgrade multisig" and no bare on-curve key anywhere in
the chain.

## Why this doesn't fit the repo's k-of-n model

`METHODOLOGY.md` section 3.3's classification ladder resolves an off-curve authority to a
Squads v4/v3 vault (rung 3), an SPL-Governance treasury (rung 4), or an SPL Token
`Multisig` (rung 6) -- every case assumes the quorum is checked by the Solana runtime's own
`is_signer` on a fixed list of Ed25519 keys or accounts. Wormhole's Guardian quorum is a
different archetype entirely:

- The 19 "signers" are secp256k1 (Ethereum-style) keys, not Solana accounts and not
  Ed25519 keys -- they cannot appear in any account's signer list at all.
- Guardian approval is checked by verifying secp256k1 signatures over a message hash via
  Solana's secp256k1 program (a precompile), consumed as auxiliary instruction data by
  `post_vaa`/`verify_signatures` -- not by the runtime's transaction-level signature checks
  that every multisig program in this repo (Squads, SPL Governance, SPL Token multisig)
  relies on.
- The thing being protected is a cross-chain message (a VAA), not a Solana account's admin
  field or a program's upgrade slot directly -- the upgrade-authority PDA above is a
  downstream consequence of that message-verification design, not a multisig vault.

**Conclusion: do not add a `score_wormhole_core_bridge` entry.** This is not an
under-decoded k-of-n target waiting for a `multisigScore` resolution (Squads/SPL
Multisig/Realms) -- it is a structurally different trust model (a message-verification
quorum over off-chain ECDSA keys checked by a precompile) that the current
`adminKeyScore`/`multisigScore`/`timelockScore` formulas were not built to represent. A
future methodology addition, if this project ever adds a "guardian/oracle quorum" archetype
distinct from the multisig archetype, would need its own scoring dimension, not a forced fit
into `multisigScore`.

## Exploitable angle for later (not built here): Pyth Solana Receiver's partial verification

Not scored, not scoped -- a note for a future pass. The Pyth Solana Receiver's Config PDA
(`DaWUKXCyXsnzcvLUyeJRWou8KTn7XtadgTsdhJ6RHS7b`) has `minimum_signatures = 3` (read live
today, same byte layout as `sol_read.read_pyth_config`). A consuming protocol that accepts
`VerificationLevel::Partial { num_signatures }` price updates (rather than requiring
`Full`) can be satisfied by as few as 3 of the 19 Guardians agreeing on a price -- a
threshold the *consumer* chooses when it calls the receiver, not something the bridge
itself weakens. Worth checking, for any Solana target already scored here that consumes
Pyth prices through this receiver, whether it accepts `Partial` verification and at what
`num_signatures` -- that would be a real full-power path (price manipulation) resolving to
as few as 3-of-19, well under the bridge's own 13-of-19. Nothing built or scored on this yet.

## TVL: do not attribute to the Core Bridge

The Core Bridge doesn't custody any user funds -- it only relays signed messages and holds
the ~9.54 SOL of accumulated `postMessage` fees noted above. Any Wormhole-related TVL figure
on DefiLlama or elsewhere belongs to the **Portal Bridge** (the separate token-bridge
program built on top of Core Bridge messages), not to this program. Do not reuse a
"Wormhole TVL" number here if this target is ever revisited.

## Verification

- `worm2ZoG2kUd4vFXhvjh93UUH596ayRfgQ2MgjNMTth`: confirmed `executable=true`,
  `owner=BPFLoaderUpgradeab1e11111111111111111111111`, live upgrade authority
  `2rCAC1VKz5YP1jZTHcVfWDhHMs2iEruUaATdeZe5Fjk5` (via `sol_read.read_program`).
- GuardianSet PDA, Bridge config PDA and the upgrade-authority PDA all re-derived offline
  with `sol_read.find_program_address` and matched byte-for-byte against the live addresses
  above (all three bump 255).
- GuardianSet account bytes decoded directly (`index`, key count, `expiration_time`); Bridge
  config account bytes decoded directly (`guardian_set_index`, `last_lamports`,
  `guardian_set_expiration_time`, `fee`).
- Upgrade-authority PDA account confirmed `null` via `getAccountInfo`.
- 13-of-19 quorum re-derived from the exact integer-division formula, not copied from prose
  documentation.
- Pyth Solana Receiver `minimum_signatures` decoded live with the same field layout already
  used by `sol_read.read_pyth_config`.
- `python3 -m unittest discover -s scripts/lib/tests`: no scorer touched by this note, ran
  the full suite anyway (see commit) -- 0 changes to any `scorers.py` in any chain.

## Reproduction

```
python3 -c "
import sys; sys.path.insert(0, 'chains/solana/scripts')
import sol_read as s, base64

prog = 'worm2ZoG2kUd4vFXhvjh93UUH596ayRfgQ2MgjNMTth'
url = 'https://api.mainnet-beta.solana.com'

print(s.read_program(url, prog))

gs, gs_bump = s.find_program_address([b'GuardianSet', (7).to_bytes(4, 'big')], prog)
br, br_bump = s.find_program_address([b'Bridge'], prog)
up, up_bump = s.find_program_address([b'upgrade'], prog)
print('GuardianSet', gs, gs_bump)
print('Bridge', br, br_bump)
print('upgrade authority', up, up_bump, '-> account:', s.acct(url, up))

d = base64.b64decode(s.acct(url, gs)['data'][0])
index = int.from_bytes(d[0:4], 'little'); nkeys = int.from_bytes(d[4:8], 'little')
off = 8 + 20 * nkeys
print('GuardianSet index', index, 'nkeys', nkeys,
      'expiration_time', int.from_bytes(d[off+4:off+8], 'little'))

d2 = base64.b64decode(s.acct(url, br)['data'][0])
print('guardian_set_index', int.from_bytes(d2[0:4], 'little'),
      'last_lamports', int.from_bytes(d2[4:12], 'little'),
      'guardian_set_expiration_time', int.from_bytes(d2[12:16], 'little'),
      'fee', int.from_bytes(d2[16:24], 'little'))


# Pyth Solana Receiver Config PDA -- same byte layout as sol_read.read_pyth_config,
# applied directly since we have the Config PDA address, not the receiver program id.
cfg = base64.b64decode(s.acct(url, 'DaWUKXCyXsnzcvLUyeJRWou8KTn7XtadgTsdhJ6RHS7b')['data'][0])
o = 8 + 32  # discriminator + governance_authority
o += 33 if cfg[o] == 1 else 1  # target_governance_authority: Option<Pubkey>
o += 32  # wormhole
n = int.from_bytes(cfg[o:o+4], 'little'); o += 4 + 34 * n  # valid_data_sources: Vec<DataSource>
o += 8  # single_update_fee_in_lamports
print('minimum_signatures', cfg[o])
"
```
