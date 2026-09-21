# Zcash -- scouting candidates, 2026-09-18

Scouting-phase pass. Budget: up to 50 new targets, never forced -- see
[`METHODOLOGY.md`](../METHODOLOGY.md) section 1 for why Zcash's real
target universe (no general-purpose contracts) is narrow to begin with.
This pass scanned every DefiLlama-tracked protocol for one that lists
"Zcash" as a supported chain (the closest available proxy for "verifiable
TVL/volume" on a chain with no DEX/lending ecosystem of its own), then
live-verified the admin/signer-set equivalent (Zcash has no `owner()` --
see METHODOLOGY.md section 1's "consequence" paragraph) for every hit
with real value.

**Retained: 1 new target (2 live addresses, one logical authority).
Rejected: 2 (documented below, not silently dropped).** This is close to
the real reserve for Zcash after this pass -- `data/scored_targets_2026-09-17.md`
already covers the only two protocol-defined funds and the only other
cross-chain representation found to date (`zec.omft.near`); this pass's
own DefiLlama scan (`chains` array containing "Zcash", across every
listed protocol, not just bridges) turned up exactly three hits total,
and only one is new and real.

**Update, same day, second pass:** a follow-up search deliberately looked *beyond*
DefiLlama (THORChain-direct integration, remaining ZIP-1015 funding streams, ZCG/ECC/
ZF governance, other ZEC wrappers) -- see "Second pass, same day: searching beyond
DefiLlama" near the end of this file. No new target was added: three leads resolve to
authorities already tracked, THORChain's own integration is real but holds zero ZEC
live today, and one real candidate (Zenrock's `zenZEC`) could not be verified to this
project's bar and is documented as deferred, not scored.

## Retained: Maya Protocol -- Zcash custody (2 live Asgard TSS vaults)

**What it is.** Maya Protocol (`mayaprotocol.com`, DefiLlama slug
`maya-protocol`, category "Cross Chain Bridge", a THORChain-model fork)
holds native ZEC in "Asgard" vaults controlled by a Threshold Signature
Scheme (TSS) among its own active validator nodes -- structurally the
mirror image of the already-scored `zec.omft.near` (that one is ZEC
*represented on* another chain via a NEAR MPC/DAO authority; this one is
*real transparent ZEC, on Zcash itself*, controlled by an external
network's validator set). Primary source: Maya Protocol's own full-node
REST API (`mayanode.mayachain.info`), which is authoritative for vault
membership and addresses the way a contract's own `getOwners()` would be
for an EVM Safe.

**Live-verified addresses and balances** (2026-09-18, cross-checked on
two independent lightwalletd operators, `zec.rocks:443` and
`zcash.mysideoftheweb.com:9067` -- same two-operator convention as every
other Zcash target in this repo):

| Vault | Address | Mayachain internal ledger | Live on-chain balance (both operators agree) |
|---|---|---|---|
| A | `t1RBiXrLRdrHgsuSGQEusG2wCzPFczEVMfT` | 220,970,943,152 zat | **220,970,943,152 zat = 2,209.70943152 ZEC** (exact match) |
| B | `t1VtnnhTYhmADh7L2uKU3Sev7GscBHT6HfE` | 129,157,478,056 zat | **126,951,364,578 zat = 1,269.51364578 ZEC** (ledger overstates on-chain by 2,206,113,478 zat = 22.06106478 ZEC, not resolved this pass) |
| Combined | -- | -- | **347,922,307,730 zat = 3,479.22307730 ZEC** |

At the CoinGecko spot price read the same session ($1,460.4736/ZEC), the
combined live balance is on the order of **$5.08M** actually held on
Zcash Mainnet by this authority today -- real value at risk, independent
of whether new deposits are currently flowing (see "not active right
now" below).

**Signer set, live-read (the `getOwners()` equivalent).** Both vault
pubkeys appear in exactly **20 of 40** currently-Active Mayachain
validator nodes' `signer_membership` list (`/mayachain/nodes`,
cross-referenced against the vault pubkeys from `/mayachain/vaults/asgard`).
This is a TSS scheme, not an on-chain P2SH script: the 20-of-40
membership is verifiable live from Mayachain's own primary source, but
the actual *signing threshold* enforced among those 20 (THORChain-fork
convention is a 2/3-majority of vault signers, not of all active nodes)
was **not** confirmed from a primary source this pass -- open item below,
not assumed.

**Reconciliation gaps found, disclosed rather than smoothed over:**
- DefiLlama's own `currentChainTvls.Zcash` for this protocol reads
  **$3,878,122.63** (`api.llama.fi/protocol/maya-protocol`) -- lower than
  the $5.08M live on-chain sum above. Mayachain's own AMM pool ledger
  (`/mayachain/pool/ZEC.ZEC`, `balance_asset`) reads 2,646.55627636 ZEC
  (~$3.865M), close to DefiLlama's figure but not to either vault's raw
  on-chain balance individually or combined. Three different numbers
  (live on-chain sum, pool ledger, DefiLlama) that don't reconcile to
  each other -- plausible explanations (additional retiring vaults not
  surfaced by this pass's queries, LP-unit vs. raw-balance accounting,
  pending cross-chain state) were not chased down; flagged for
  scoring_build rather than guessed at.
- `chains/zcash/scripts/zcash_read.py`'s `tx` subcommand hardcodes a
  P2SH output matcher (`p2sh = "a914" + h160 + "87"`, line ~141) and has
  no P2PKH matcher. Both vault addresses are `t1`-prefix (P2PKH), so
  running `tx` against them silently returns `outputs_to_addr=0` on
  every real transaction in range -- **a false negative from a tooling
  gap, not evidence of no activity.** This was caught by reading the
  script's source, not trusted from its output. Tx-history/recency for
  these two addresses is genuinely unverified this pass; only the
  balance (via the separate, unaffected `GetTaddressBalance` call) is
  confirmed.

**Not active right now, disclosed:** `/mayachain/inbound_addresses`
reports `"halted": true, "chain_trading_paused": true` for `ZEC` at read
time -- Mayachain's own network has currently paused new ZEC deposits and
withdrawals through this bridge. The balances above are real value
sitting in a live, externally-controlled vault, not evidence of current
inbound/outbound volume. Worth its own note for a future methodology
pass: a counterparty network's own unilateral power to halt a Zcash
asset's flow is itself an authority fact this project has not yet had a
target that exercises it live.

**Why this is a target and not scored yet.** METHODOLOGY.md section 4
only defines five target types (`L1`, `FUND`, `POOL`, `EXT`, `ASSET`).
This does not cleanly fit any of them: it is native on-Zcash value (not
`EXT`), but the controlling keys are entirely off-Zcash and TSS-based
(not `FUND`'s on-chain P2SH multisig). Assigning it a 0-100 number
requires a methodology decision this scouting pass should not make
unilaterally -- see Open items.

## Rejected: Templar Protocol (resolves to an already-scored target, not new)

DefiLlama lists Templar Protocol (`templarfi.org`, NEAR-based
"Cypher Lending", audited) with "Zcash" in its `chains` array and a live
`currentChainTvls`-equivalent Zcash collateral figure of **$150,259**
(`api.llama.fi/protocol/templar-protocol`, `chainTvls["Zcash"]`, latest
point). Read the DefiLlama adapter's own source
(`DefiLlama-Adapters/projects/templarfi/index.js`,
`detectCrossChainToken()`) to find the underlying asset: Templar's
"Zcash" exposure is entirely the NEP-141 token `zec.omft.near` --
**the exact same NEAR `omft.near` factory / `TokenDepositer` authority
this repo already scored in
[`data/scored_targets_2026-09-17.md`](scored_targets_2026-09-17.md)**
(`adminKeyScore` 5, `multisigScore` 18, from `scorers.py`'s
`score_ext_zec_omft()`). Adding Templar as a separate target would score
the same authority object twice under two names. Not added. Retained
only as corroboration that `zec.omft.near` sees real third-party usage
(a lending protocol accepting it as collateral) beyond the bridge itself
-- a fact worth a one-line mention next time `scored_targets` is
revisited, not a new scored line.

## Rejected: Zenrock Bridge (no real value)

DefiLlama lists Zenrock Bridge (`zenrocklabs.io`, category "Bridge",
chains `['Zcash', 'Bitcoin']`) with **`tvl: 0`** at read time
(`api.llama.fi/protocols`, entry `name == "Zenrock Bridge"`). Fails this
project's own "real value/usage, verifiable TVL" bar before any address
or signer-set verification was attempted. Not pursued further. Re-check
in a future scouting pass if its TVL becomes nonzero.

## Open items for scoring_build (not decided here)

1. Define where a native-Zcash-value / off-Zcash-TSS-authority target
   fits in METHODOLOGY.md's target-type table (new type, or a documented
   variant of `FUND`) before `scorers.py` can assign it numbers.
2. Confirm Mayachain's actual TSS signing threshold among each vault's 20
   live signers from a primary source (Mayachain docs/spec), not assumed
   from the THORChain-fork convention.
3. Add a P2PKH matcher to `scripts/zcash_read.py`'s `tx` subcommand
   (currently P2SH-only) so tx-history/recency can be checked for `t1`
   addresses -- needed for this target and for any future one that isn't
   a P2SH fund.
4. Reconcile the three disagreeing ZEC figures (live on-chain sum
   3,479.22 ZEC; Mayachain pool ledger 2,646.56 ZEC; DefiLlama-attributed
   $3.878M) before publishing a TVL claim for this target.
5. Resolve the ~22.06 ZEC gap between vault B's Mayachain-internal ledger
   entry and its live on-chain balance.

## Reproduction

```bash
# DefiLlama scan: every protocol whose chains[] includes "Zcash"
curl -s "https://api.llama.fi/protocols" | python3 -c "
import json,sys
d=json.load(sys.stdin)
for p in d:
    if any('zcash' in str(c).lower() for c in (p.get('chains') or [])):
        print(p.get('name'), p.get('category'), p.get('tvl'))
"

# Maya Protocol's own primary source: current ZEC vault + halt status
curl -s "https://mayanode.mayachain.info/mayachain/inbound_addresses" | python3 -m json.tool

# Both active vaults' ZEC balances and addresses
curl -s "https://mayanode.mayachain.info/mayachain/vaults/asgard" | python3 -c "
import json,sys
d=json.load(sys.stdin)
for v in d:
    if v.get('status')=='ActiveVault':
        zec=[c for c in v['coins'] if c['asset']=='ZEC.ZEC']
        addr=[a for a in v.get('addresses',[]) if a['chain']=='ZEC']
        print(v['pub_key'], zec, addr)
"

# Live on-chain balance, both vaults, both operators (must agree)
python3 chains/zcash/scripts/zcash_read.py balance zec.rocks:443 \
  t1RBiXrLRdrHgsuSGQEusG2wCzPFczEVMfT t1VtnnhTYhmADh7L2uKU3Sev7GscBHT6HfE
python3 chains/zcash/scripts/zcash_read.py balance zcash.mysideoftheweb.com:9067 \
  t1RBiXrLRdrHgsuSGQEusG2wCzPFczEVMfT t1VtnnhTYhmADh7L2uKU3Sev7GscBHT6HfE

# Signer-set membership (getOwners() equivalent): count Active nodes
# whose signer_membership includes each vault's pub_key
curl -s "https://mayanode.mayachain.info/mayachain/nodes" | python3 -c "
import json,sys
d=json.load(sys.stdin)
vaults={'A':'mayapub1addwnpepqdgafgd6gv8x09m9vu6fvqzkj0e0v2wj64ezs7vm5p2w5tmf0t0hvpljmch',
        'B':'mayapub1addwnpepq24t2hk53nz9k5rkcs0vaqn5crc08rmznlpmgvsx670wxdd7htw8225yt4w'}
active=[n for n in d if n.get('status')=='Active']
print('active nodes:', len(active))
for k,pk in vaults.items():
    print(k, sum(1 for n in active if pk in (n.get('signer_membership') or [])))
"

# Templar Protocol's ZEC exposure resolves to zec.omft.near, already scored
curl -s "https://raw.githubusercontent.com/DefiLlama/DefiLlama-Adapters/main/projects/templarfi/index.js" \
  | grep -A2 "zec.omft.near"
```

## Second pass, same day: searching beyond DefiLlama

**Result: no new solid target found.** This pass deliberately looked past DefiLlama's
own listings (the first pass's proxy for "verifiable TVL") for other legitimate Zcash
authority objects: additional ZIP funding-stream addresses, a THORChain-direct ZEC
integration, other cross-chain wrappers of ZEC, and any identifiable on-chain
ECC/Zcash Foundation treasury separate from what is already tracked. Five leads were
run down; three resolve to authorities this repo already scores (not new), one is a
real but currently-empty authority (rejected, no live value), and one is a real,
non-trivial candidate this pass could **not** verify to this project's own bar and is
therefore left unscored rather than forced - see "Deferred" below.

### Not new: resolve to an already-tracked authority

**ECC / Zcash Foundation / Shielded Labs multisig -- is the already-scored ZIP 271
address, not a separate target.** [ZIP 271](https://zips.z.cash/zip-0271) (fetched
today) states in its own text: "The coinbase transaction of the activation block of
this ZIP MUST include one or more lockbox disbursement output(s) to a 2-of-3 P2SH
multisig with keys held by the following 'Key-Holder Organizations': Zcash
Foundation, the Electric Coin Company, and Shielded Labs" -- Mainnet address
`t3ev37Q2uL1sfTsiJQJiWJoFzQpDhmnUwYo`. That is exactly the "ZIP 271 one-time lockbox
disbursement" fund `scorers.py` already scores (2-of-3 confirmed live by an actual
on-chain spend, `adminKeyScore` 50 / `multisigScore` 39 in today's run). No second,
separate ECC/ZF-controlled on-chain address was found.

**Zcash Community Grants (ZCG) governance -- same conclusion.** [ZIP 1015](https://zips.z.cash/zip-1015)
(fetched today) defines the two NU6 funding streams: `FS_DEFERRED` (12%, the
in-protocol lockbox, one-time-disbursed to the address above by ZIP 271 -- not itself
a spendable key) and `FS_FPF_ZCG` (8%, paid to the Financial Privacy Foundation "for
the express use of the Zcash Community Grants Committee") -- the second is the same
funding-stream mechanism already tracked as "ZCG funding stream (FS_FPF_ZCG_H3)". The
5-person Grants Committee approves disbursements from this same already-tracked
stream; it is not a separate on-chain authority. ZIP 1015 itself does not publish
addresses (only allocation percentages and height ranges), so no new address surfaced
here either.

**Zolana Bridge (ZEC on Solana) -- resolves to the already-scored `zec.omft.near`
authority, same pattern as the already-rejected Templar Protocol.** NEAR Protocol's
own announcement (`x.com/NEARProtocol`, 2026, "The Zolana Bridge is live... with NEAR
Intents + OmniBridge powering Zcash's $ZEC token on Solana") and three independent
write-ups (KuCoin, CryptoRank, Solana Echo) agree: Zolana routes real ZEC through
NEAR's Chain Signatures / Intents OmniBridge -- the same `omft.near` factory /
`TokenDepositer` role this repo already scores in `score_ext_zec_omft()`
(`adminKeyScore` 5, `multisigScore` 18). Whatever downstream chain an Intents solver
delivers the asset to (NEAR itself, or Solana via Zolana), the authority that decides
"ZEC was deposited" is the same one already tracked. Not a new target, for the same
reason Templar Protocol was rejected on 2026-09-18 (first pass, above).

### Rejected: real integration, but zero live value today

**THORChain -- direct ZEC integration is coded and announced, but not live: no ZEC
pool, no ZEC inbound address, no ZEC in any Asgard vault, checked live today.** News
coverage (Decrypt, The Defiant, Crypto Daily) confirms THORChain's v3.20 upgrade
activated 2026-08-25 with native, non-wrapped ZEC/XMR swap support merged into the
codebase. But THORChain's own node API (`thornode.thorchain.liquify.com`, a
community-run gateway to the same chain state every THORChain full node replicates --
this project's own primary source for this pass, since `thornode.ninerealms.com` and
`thornode-v1.ninerealms.com` were unreachable from this pass) shows, live-read
2026-09-18:
- `/thorchain/pools`: 43 pools, none for `ZEC.ZEC` (`AVAX`/`BASE`/`BCH`/`BSC`/`BTC`/
  `DOGE`/`ETH`/`GAIA`/`LTC`/`SOL`/`THOR`/`TRON`/`XRP` only).
- `/thorchain/inbound_addresses`: 12 chains listed, `ZEC` not among them.
- `/thorchain/vaults/asgard`: 5 active vaults, zero hold any `ZEC`-asset coin.

So THORChain does not yet custody a single satoshi of real ZEC -- there is no
authority object to score, the same "real integration, zero real value" reason the
first pass (above) rejected the DefiLlama-listed "Zenrock Bridge" entry (`tvl: 0`,
re-confirmed still 0 today via `api.llama.fi/protocols`). Worth re-checking once
THORChain's ZEC pool is actually funded and live.

### Deferred, not scored: a real candidate this pass could not verify

**Update 2026-09-19: partially resolved.** Zenrock's docs/API were re-checked and are
still down (identical HTTP 402/503), but a hand-built ABCI query against zrchain's own
Tendermint RPC resolved the live dMPC keyring threshold (3-of-3) from a primary
source, and a new target type, `MPCKEYRING`, now scores it in `scorers.py`. The
literal custody address(es) remain not determined (confirmed, not just re-asserted --
see below). Full derivation:
[`data/zenzec_mpc_keyring_2026-09-19.md`](zenzec_mpc_keyring_2026-09-19.md),
METHODOLOGY.md 3.7/4.8.

**Zenrock's `zenZEC` (dMPC custody of native ZEC, wrapped on Solana) -- real,
non-trivial value confirmed live, but the specific authority facts this project
requires (custody address(es), signer threshold) could not be read from a primary
source today, and the custody model itself does not obviously fit the existing
`XVAULT` type as written.**

- **Real value, confirmed live.** Solana mainnet RPC (`api.mainnet-beta.solana.com`,
  `getTokenSupply` on mint `JDt9rRGaieF6aN1cJkXFeUmsy7ZE4yY3CZb8tVMXVroS`, read
  2026-09-18): total supply **494.51437135 zenZEC** -- at this project's own
  CoinGecko spot read used elsewhere ($1,460.4736/ZEC), on the order of **$722K**.
  Independently corroborated (not just the project's own marketing) by CoinDesk
  ("Zcash Privacy Meets Solana DeFi with Zenrock's Wrapped ZEC Crossing $15M in
  Volume") and Bitget News ("zenZEC supply hits all time high"): 13,200+ holder
  addresses, $15M+ cumulative volume since an Oct-31 launch. This is a real bridge
  with real usage, clearing the same "verifiable TVL/usage" bar the first pass used
  to retain Maya Protocol and reject Zenrock Bridge / Templar Protocol.
- **Custody model does not match `XVAULT` as currently defined.** `XVAULT`
  (METHODOLOGY.md 4.7) was written for a small, stable, enumerable set of vaults
  (Maya Protocol's 2 Asgard vaults). Zenrock's own `zrchain` GitHub repository
  (`github.com/Zenrock-Foundation/zrchain`, `docs/README.md`'s deposit sequence
  diagram, read today) documents a materially different model: each deposit gets a
  **freshly generated** Zcash key ("Request new deposit address" -> zrChain "Create
  new ZCash key request" -> the dMPC signer stack "Generate new ZCash key" -> "Return
  deposit address"), not a fixed small set of addresses. Scoring this properly would
  need its own target-type decision (is the authority "whoever can request/sign a new
  key," not "whoever holds vault address X") -- a methodology call, not something to
  make unilaterally in a scouting pass, the same discipline already applied to Maya
  Protocol's vaults on 2026-09-17/18.
- **No primary source reachable today for the facts that would matter anyway.** Even
  setting the target-type question aside, this pass could not confirm, from a primary
  source, either (a) the live custody address(es)/aggregate ZEC balance actually held
  today, or (b) the real k-of-n dMPC signer threshold. Zenrock's own docs site
  (`docs.zenrocklabs.io/zenZEC/introduction`, `.../zenBTC/zenbtc-technical`) returned
  `Payment Required` / `DEPLOYMENT_DISABLED` (its hosting appears to be down, not a
  wrong URL). Its official REST API (`api.diamond.zenrocklabs.io`) returned HTTP 503;
  two community-run mirrors (`api.zenrock.nodestake.org`,
  `zenrock.api.m.stavr.tech`) were unreachable or 502. Only the Tendermint RPC mirror
  (`rpc.diamond.zenrocklabs.io`) answered, which is the consensus-layer endpoint, not
  the REST/LCD gateway a custom Cosmos SDK module's data (the `x/treasury` /
  `x/dct` keys this would need) is served from -- querying it live would need a
  hand-built ABCI query against zrChain's own protobuf schema, not attempted this
  pass. The "eight institutional operators" and "1:1 backed" claims found via search
  are Zenrock's own marketing copy (blog post, litepaper PDF that did not parse
  legibly) -- disclosed as unverified secondary claims, not confirmed technical facts,
  consistent with this project's own "no plausible-looking number without a primary
  source" discipline.
- **Not pursued as a consolation target either.** `WZEC` (Wrapped ZEC, Ethereum
  ERC-20 `0x4A64515E5E1d1073e83f30cB97BEd20400b66E10`) was also checked as a possible
  alternative: real but marginal (429.97 WZEC max supply, ~$628K, 397 holders per
  Etherscan, read today), markets itself on Chainlink Proof-of-Reserve + institutional
  custody, but Etherscan's own scan flags the deployed contract as unaudited with an
  old, generic Solidity 0.5.16 implementation, and no custodian identity, reserve
  address, or PoR feed address could be located on the token's page or in its
  (garbled, non-parseable) whitepaper PDF. Rejected on the same "cannot verify"
  grounds as `zenZEC`, with an added authenticity concern `zenZEC` does not have.

**Honest bottom line:** after checking THORChain-direct integration, the remaining
ZIP-1015 funding-stream addresses, the ECC/ZF/ZCG governance angle, and four
cross-chain ZEC wrappers beyond `zec.omft.near` and Maya Protocol, nothing cleared
this project's bar for a new scored line today. `zenZEC` is the one lead worth
revisiting -- once Zenrock's own docs/API are reachable again and a target-type
decision is made for a per-deposit (not per-vault) custody model -- and THORChain is
worth re-checking once its ZEC pool actually holds funds. `scorers.py` is unchanged
this pass.

### Reproduction

```bash
# THORChain: live pools / inbound addresses / Asgard vault coins, today
curl -sk "https://thornode.thorchain.liquify.com/thorchain/pools" \
  | python3 -c "import json,sys; d=json.load(sys.stdin); print([p['asset'] for p in d if 'ZEC' in p['asset'].upper()] or 'no ZEC pool')"
curl -sk "https://thornode.thorchain.liquify.com/thorchain/inbound_addresses" \
  | python3 -c "import json,sys; d=json.load(sys.stdin); print(sorted(set(e['chain'] for e in d)))"
curl -sk "https://thornode.thorchain.liquify.com/thorchain/vaults/asgard" \
  | python3 -c "import json,sys; d=json.load(sys.stdin); print(any('ZEC' in c['asset'].upper() for v in d for c in v.get('coins',[])))"

# zenZEC: live Solana mint supply
curl -s -X POST -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"getTokenSupply","params":["JDt9rRGaieF6aN1cJkXFeUmsy7ZE4yY3CZb8tVMXVroS"]}' \
  https://api.mainnet-beta.solana.com

# Zenrock's own infra, down at read time (2026-09-18)
curl -sk -o /dev/null -w "%{http_code}\n" https://docs.zenrocklabs.io/zenZEC/introduction
curl -sk -o /dev/null -w "%{http_code}\n" https://api.diamond.zenrocklabs.io/cosmos/base/tendermint/v1beta1/node_info

# DefiLlama's Zenrock Bridge entry, re-confirmed still tvl:0 today
curl -s "https://api.llama.fi/protocols" | python3 -c "
import json,sys
d=json.load(sys.stdin)
print(next(p for p in d if p.get('name')=='Zenrock Bridge'))
"
```
