# Zenrock `zenZEC` -- dMPC custody keyring, resolved (partially) 2026-09-19

> **STATUS UPDATE 2026-09-20:** the premise of this note (a live custody keyring) no longer holds. See
> `zenzec_status_2026-09-20.md`: the zrchain node it was read from is frozen since 2026-08-10, the product is
> winding down, the backing ZEC sits at an address not derived from this keyring, and the key counts and
> transaction counts below are corrected there (613 keys, key 388 has 36 transactions). The composite is a
> dated reading and is flagged as such.

Resumes the lead `data/scouting_candidates_2026-09-18.md` deferred the day before:
a real, non-trivial `zenZEC` wrapper (494.51 zenZEC, ~$722K at that day's spot price,
live Solana Mainnet supply, independently corroborated by CoinDesk/Bitget) whose
custody model generates a fresh Zcash key per deposit -- not a small fixed set of
vaults like Maya Protocol -- so it did not fit the `XVAULT` type as written, and
Zenrock's own docs/API were down at read time, blocking any attempt to name a real
address or signer threshold from a primary source.

**Re-check, 2026-09-19: docs.zenrocklabs.io and Zenrock's REST/LCD API are still
down, identical failure to 2026-09-18.**

```
docs.zenrocklabs.io/zenZEC/introduction -> HTTP 402 (Payment Required)
api.diamond.zenrocklabs.io (node_info)  -> HTTP 503
api.zenrock.nodestake.org (community)   -> connection failed (curl: (7))
zenrock.api.m.stavr.tech (community)    -> HTTP 502
```

**What did work: Zenrock's own Tendermint/CometBFT RPC.** `rpc.diamond.zenrocklabs.io`
answers (`/status`, `/abci_query`). Confirmed this IS Zenrock Mainnet (`diamond-1`),
not a testnet, from two independent sources: Zenrock's own validator-setup guide
(`github.com/zenrocklabs/zenrock-validators`, `README.md`, "# Mainnet" section uses
exactly this node with `--chain-id diamond-1`) and the Cosmos chain-registry
(`cosmos/chain-registry`, `zenrock/chain.json`: `"chain_id": "diamond-1"`,
`"pretty_name": "Zenrock Mainnet"`, `"status": "live"`).

CometBFT's `/abci_query` endpoint routes to the SAME gRPC-gateway Query services the
REST/LCD gateway (`api.diamond.zenrocklabs.io`) would otherwise translate HTTP paths
into -- this is how the REST gateway works internally, not a side channel. Message
shapes (field numbers, request/response types) were read directly from
`github.com/Zenrock-Foundation/zrchain`'s own published `.pb.go` source (`x/identity`,
`x/treasury`, `x/dct`), never guessed. Implementation: `scripts/zenrock_read.py`
(a hand-rolled varint + length-delimited protobuf reader, no full protobuf runtime,
same class of tool as `scripts/zcash_read.py`'s own `decode()`).

## What was found, in order of discovery

**1. Which keyring actually custodies `zenZEC` deposits, from a live read, not a
guess.** `zrchain.dct.Query/QueryParams` (empty request) returns every configured
`AssetParams` entry; the one with `asset == ASSET_ZENZEC` (enum value 2) resolves:

```
deposit_keyring_addr:    keyring1k6vc6vhp6e6l3rxalue9v4ux
rewards_deposit_key_id:  387
change_address_key_ids:  [388]
proxy_address:           zen1mgl98jt30nemuqtt5asldk49ju9lnx0pfke79q
solana_signer_key_id:    384
solana_mint_address:     JDt9rRGaieF6aN1cJkXFeUmsy7ZE4yY3CZb8tVMXVroS
```

**Cross-check that clears the "is this even the real config" bar.**
`solana_mint_address` above is BYTE FOR BYTE the same mint this project already
independently verified live on Solana Mainnet RPC on 2026-09-18
(`getTokenSupply` on `JDt9rRGaieF6aN1cJkXFeUmsy7ZE4yY3CZb8tVMXVroS`). Two unrelated
primary sources (Zenrock's own chain state; Solana's own chain state) agree on the
same address for the same asset -- strong evidence this is the real deployed
configuration, not a stale or wrong one, despite the reading node itself being stale
(see limitations below). Re-read live again today: supply unchanged at
494.51437135 zenZEC; at today's CoinGecko spot ($1,556.49/ZEC) that is ~$769,707.

**Also worth noting: this is NOT the value hardcoded in zrchain's own source.**
zrchain's `x/dct/keeper/params.go` `DefaultParams()` hardcodes a DIFFERENT
`DepositKeyringAddr` (`keyring1pfnq7r04rept47gaf5cpdew2`) and a different Solana mint
(`4q9DEzEHLqNG637jsGMYSg8E56SbotNcGeH3GjtaYYJT`) as a compiled-in fallback. A live
`KeyringByAddress` query against that placeholder address resolves to
`"not found: unknown request"` on this same RPC -- confirming it is a dev/test
fixture never actually deployed, not assumed from the variable's name alone.

**2. The keyring's live party-threshold -- the actual "k-of-n dMPC signer
threshold" asked for.** `zrchain.identity.Query/KeyringByAddress` on
`keyring1k6vc6vhp6e6l3rxalue9v4ux`:

```json
{
  "address": "keyring1k6vc6vhp6e6l3rxalue9v4ux",
  "creator": "zen1wa2l79s9v9fxl0ergelvv55nmfdh6ms052c9rq",
  "description": "Zenrock MPC",
  "party_threshold": 3,
  "key_req_fee": 75000000,
  "sig_req_fee": 50000000,
  "is_active": true,
  "admins": ["zen1wa2l79s9v9fxl0ergelvv55nmfdh6ms052c9rq"],
  "parties": [
    "zen1vxl32yly7zgrssnxnhlk4dcryylmz6zvkszclh",
    "zen1dy5mleccrc0sq3gflxklc3v32269c5704jrz8z",
    "zen12ppadg7mwmtf9e4mm8wvk2hkvduqh43vhn0zjr"
  ]
}
```

`party_threshold` is `x/identity`'s own field, documented in its source
(`keyring.pb.go`) as "the number of parties required to submit signed txs in order
for a request to be fulfilled" -- i.e. exactly the k-of-n dMPC signer threshold this
task asked for. **k = 3, n = 3: a 3-of-3, unanimous dMPC signer set, with 1 admin
account able to add/remove parties or change the threshold itself.** This threshold
applies to every key this keyring ever generates -- including a brand-new per-deposit
key -- so it IS the answer to "what's the signer threshold for zenZEC custody," even
though (see below) it is not tied to one single enumerable address the way Maya
Protocol's vaults are.

**3. The two Zcash-mainnet addresses nameable from this config, independently
re-derived and live-checked.** `rewards_deposit_key_id` (387) and
`change_address_key_ids[0]` (388) are `x/treasury` `Key` objects.
`zrchain.treasury.Query/KeyByID` on each returns the raw public key plus every
derived wallet address zrchain itself computes:

| Key ID | Role | Raw pubkey (compressed secp256k1) | Zcash Mainnet address (chain-reported) | Independently re-derived | Match? |
|---|---|---|---|---|---|
| 387 | rewards_deposit | `0391daf66eac2b84b652359c1061e29626165043193533e3784e748a72ef987d62` | `t1WrUBdocqpubAHoRrpihYBoDFjPg7utLka` | `t1WrUBdocqpubAHoRrpihYBoDFjPg7utLka` | yes |
| 388 | change_address | `03e5d0279abc84956df6ce9764ea49d5e942278b2fbc988a70ba050924743913dd` | `t1S9DvnjtxgP4HMo1W6sTxVh95f6cmZ9dcw` | `t1S9DvnjtxgP4HMo1W6sTxVh95f6cmZ9dcw` | yes |

Re-derivation used zrchain's own published algorithm
(`x/treasury/types/wallet_zcash.go`: HASH160 of the compressed pubkey, Zcash's 2-byte
mainnet P2PKH version prefix `0x1C 0xB8`, Base58Check) implemented independently in
Python (`zenrock_read.zcash_mainnet_p2pkh_address()`), not trusted from the chain's
own reported string alone -- both match exactly.

**Live balance of both addresses, both of this project's own established lightwalletd
operators (same two-operator convention as every other Zcash-side read in this
project):**

```
t1WrUBdocqpubAHoRrpihYBoDFjPg7utLka: 0 zat on zec.rocks:443 AND zcash.mysideoftheweb.com:9067
t1S9DvnjtxgP4HMo1W6sTxVh95f6cmZ9dcw: 0 zat on zec.rocks:443 AND zcash.mysideoftheweb.com:9067
```

**Both hold 0 ZEC today.** This is a genuine finding, disclosed rather than hidden:
it CONFIRMS the 2026-09-18 scouting pass's read of Zenrock's own deposit-sequence
diagram ("Request new deposit address" -> "Create new ZCash key request" -> the dMPC
signer stack "Generate new ZCash key" -> "Return deposit address") -- these two named
infrastructure roles are not where the real ~494.51-zenZEC-equivalent of native ZEC
sits. The actual bulk custody is spread across per-deposit ephemeral keys that are
not enumerable from `AssetParams` and were not brute-forced this pass (would mean
querying `KeyByID` for an unknown, potentially large range of sequential IDs against
a single, already-fragile RPC node -- not attempted).

**4. Bonus finding, not asked for but load-bearing for `crossExposureScore`:** the
SAME `zrchain.zenbtc.Query/QueryParams` method resolves zenBTC's own
`DepositKeyringAddr` to the IDENTICAL `keyring1k6vc6vhp6e6l3rxalue9v4ux`, and shares
its `ProxyAddress`, Solana `FeeWallet`, and Solana `EventStoreProgramId` with zenZEC
too. This 3-of-3 "Zenrock MPC" keyring is Zenrock's shared core dMPC custody signer
set across at least two wrapped assets, not something zenZEC-specific.

## Bug found and fixed along the way

`scripts/zcash_read.py`'s `taddr_balance()` raised `StopIteration` for an address
with a genuinely zero balance (lightwalletd omits the `valueZat` field on the wire
when it is exactly 0, proto3's own default-value convention) -- indistinguishable
from a communication failure, and hit live while checking the two addresses above
(both are legitimately empty). Fixed to default to 0. This also affects
`score_maya_asgard_vault()`, which calls the same function directly and would have
hit the identical crash the day either Asgard vault's live balance happened to be
exactly 0.

## Disclosed limitations (not smoothed over)

- **SINGLE SOURCE.** `rpc.zenrock.nodestake.org` (the Cosmos chain-registry's second
  listed RPC operator for `zenrock`) refused every connection this pass
  (`curl: (7) Failed to connect`). No independent second zrchain full node could be
  reached -- unlike every other read in this project (Zcash's own two lightwalletd
  operators, NEAR's two RPCs), every fact above relies on one node.
- **DATED, not live-current.** `rpc.diamond.zenrocklabs.io`'s own `/status` reports
  its last ingested block at height 9,534,552 / `2026-08-10T23:19:52Z`, with
  `n_peers: 0` -- isolated from the rest of the p2p network. This does NOT prove the
  whole `diamond-1` Mainnet is halted (the Cosmos chain-registry still lists it
  `"status": "live"`), but no fresher zrchain endpoint (RPC, REST, gRPC, or a
  third-party explorer's own backing API) could be found or reached to confirm
  today's real chain tip. Every fact in this file reflects that ~40-day-old snapshot.
- **MUTABLE, unlike a P2SH script.** A keyring's `parties`/`party_threshold` is NOT a
  cryptographic commitment fixed forever the way a P2SH redeem script's `HASH160` is
  -- `x/identity`'s own `message_add_keyring_party.go`, `message_remove_keyring_party.go`
  and `message_update_keyring.go` exist. This reading could already be stale in a way
  a Zcash `FUND` threshold never can be, on top of the node's own 40-day lag.
  A future re-run against a fresher/second endpoint should re-confirm it, not assume
  it holds.
- **Party identities are zrchain accounts, not named operators.** Whether the 3
  `Parties` map to 3 distinct physical institutions -- Zenrock's own marketing
  claims "eight institutional operators" (blog post / litepaper, unverified secondary
  claim per the 2026-09-18 scouting pass) -- was not checked. Same class of disclosed
  gap as Maya's TSS "20 signers, not confirmed as 20 distinct companies."
- **`x/policy` not checked.** zrchain's own module table (`README.md`) lists
  `x/policy` as "Approval policies and governance" -- this could in principle impose
  additional signing constraints (amount limits, extra approvers) on top of the raw
  keyring threshold. Not investigated this pass; an open item, not assumed away.
- **Bulk custody address(es) still not determined.** Confirmed, not overturned: no
  small fixed vault set exists (unlike Maya's `XVAULT`), and the real per-deposit
  addresses are not enumerable from any public on-chain config found this pass.

## Verdict

**Partially resolved, not fully.** Zenrock's docs/API remain down (re-checked, same
failure as 2026-09-18) -- this specific blocker did not clear. But this pass found a
working alternative primary source (zrchain's own consensus RPC, hand-decoded against
its own published protobuf schema) and used it to determine, with real cross-checks,
the ONE fact this project's methodology actually needs to score this target: the live
dMPC keyring's party threshold (3-of-3). The literal "real custody Zcash address" the
task also asked for does not exist as a single answerable fact given Zenrock's
per-deposit design -- confirmed today by checking the two addresses that CAN be named
and finding both empty, not merely re-asserted from yesterday's read. Added to
`scorers.py` as a new target type, `MPCKEYRING` (METHODOLOGY.md 3.7/4.8), with every
limitation above disclosed in the scorer's own notes.

## Reproduction

```bash
S=chains/zcash/scripts

# Re-check Zenrock's docs/API (expect 402 / 503, unchanged from 2026-09-18)
curl -sk -o /dev/null -w "%{http_code}\n" https://docs.zenrocklabs.io/zenZEC/introduction
curl -sk -o /dev/null -w "%{http_code}\n" https://api.diamond.zenrocklabs.io/cosmos/base/tendermint/v1beta1/node_info

# Confirm diamond-1 = Zenrock Mainnet, and its own RPC's sync state
curl -sk https://rpc.diamond.zenrocklabs.io/status | python3 -m json.tool

# Live zenZEC config, live keyring threshold, live infra-key addresses/balances
python3 $S/zenrock_read.py dct_asset_params 2
python3 $S/zenrock_read.py keyring keyring1k6vc6vhp6e6l3rxalue9v4ux
python3 $S/zenrock_read.py key 387
python3 $S/zenrock_read.py key 388
python3 $S/zcash_read.py balance zec.rocks:443 t1WrUBdocqpubAHoRrpihYBoDFjPg7utLka t1S9DvnjtxgP4HMo1W6sTxVh95f6cmZ9dcw
python3 $S/zcash_read.py balance zcash.mysideoftheweb.com:9067 t1WrUBdocqpubAHoRrpihYBoDFjPg7utLka t1S9DvnjtxgP4HMo1W6sTxVh95f6cmZ9dcw

# Confirm the same keyring backs zenBTC too
curl -sk -G "https://rpc.diamond.zenrocklabs.io/abci_query" \
  --data-urlencode 'path="/zrchain.zenbtc.Query/QueryParams"' --data-urlencode 'data=0x'

# Re-confirm the Solana mint independently (should be unchanged from 2026-09-18)
curl -s -X POST -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"getTokenSupply","params":["JDt9rRGaieF6aN1cJkXFeUmsy7ZE4yY3CZb8tVMXVroS"]}' \
  https://api.mainnet-beta.solana.com

# Full scorer run
python3 -c "
import sys; sys.path.insert(0, 'chains/zcash')
from scorers import score_zenzec_mpc_keyring
import json; print(json.dumps(score_zenzec_mpc_keyring(), indent=2))
"
```
