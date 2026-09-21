# Zcash: authority-risk methodology (discovery)

Status: **promoted to a real scorer 2026-09-17, same day as this discovery pass.**
Discovery output, 2026-09-17 (third pass). Two earlier drafts were not approved.
The first claimed the ZIP 200 three-month upgrade notice was honoured (it was not, see
4.3) and counted Zakura as an independent implementation (it is a declared fork of
Zebra, see 3.1). The second miscounted the ZIP Editors. This pass re-reads every
figure and name against its primary source. Section 7 lists every correction,
including corrections to figures quoted during review. Section 4.6 (new) is this
project's FIRST Zcash numeric mapping -- unlike Solana/Hyperliquid/Tempo (each promoted
from an already-tested formula written a day earlier), no prior methodology-test pass
existed for Zcash to promote from, so 4.6 and [`scorers.py`](scorers.py) are the
methodology-test step and the promotion in one pass. See
[`data/scored_targets_2026-09-17.md`](data/scored_targets_2026-09-17.md) for the
live-verified numbers this produced, and each score function's own docstring in
`scorers.py` for exactly which inputs are live-verified every run versus a dated,
disclosed interpretive judgment (lineage independence, the emergency-bypass timelock
cap). Nothing has been deployed or signed on-chain.

**Update 2026-09-18**: a new target type, `XVAULT` (section 3.6/4.7), scores Maya
Protocol's Asgard TSS vaults -- native ZEC held on Zcash Mainnet itself but controlled
by an external network's own validator set, the target
[`data/scouting_candidates_2026-09-18.md`](data/scouting_candidates_2026-09-18.md)
found but deliberately left unscored pending this methodology decision. See
[`data/scored_targets_2026-09-18.md`](data/scored_targets_2026-09-18.md) for the
live-verified numbers this run, including the two pre-existing `FUND` targets and
`L1` re-derived fresh the same day (all six targets `scorers.py`'s `score_all()`
currently returns).

**Update 2026-09-19**: a second new target type, `MPCKEYRING` (section 3.7/4.8),
scores Zenrock's `zenZEC` dMPC custody keyring -- the lead 2026-09-18's scouting pass
found but deferred (Zenrock's hosted docs and REST API were down, and its per-deposit
freshly-generated-key custody model does not fit `XVAULT`). Re-checked today: still
down (same HTTP 402/503), resolved instead via hand-built ABCI queries against
zrchain's own Tendermint RPC. See
[`data/zenzec_mpc_keyring_2026-09-19.md`](data/zenzec_mpc_keyring_2026-09-19.md) for
every cross-check performed and
[`data/scored_targets_2026-09-19.md`](data/scored_targets_2026-09-19.md) for the
live-verified numbers this run (all seven targets `scorers.py`'s `score_all()` now
returns).

**Update 2026-09-19 (second pass, same day)**: section 8's three remaining open
items are addressed. The native-oracle-form question (no `AuthorityRiskOracle.sol`
to deploy on a chain with no contract VM) is resolved with a real design decision
AND a real, third-party-verified Zcash Testnet transaction publishing this
project's own already-computed L1 score -- new section 9, and
[`data/testnet_oracle_poc_2026-09-19.md`](data/testnet_oracle_poc_2026-09-19.md).
The ZCG key-holder question is resolved partially (the administering entity is
named; the specific on-chain signers are not) and the ZIP 1016 coinholder-vote
question is resolved fully (real votes have occurred, more than once) -- both in
section 8 with primary-source citations, both folded into `scorers.py`'s notes.

Methodology test, 2026-09-17 (second run of the day): two targets (the ZIP 271 fund
`t3ev37...` and the `L1` concentration input, plus the ZCG fund as a control) were
re-derived from primary sources with a from-scratch reader that does not import this
folder's scripts, and compared with the published scores. The numbers held; the test
found four gaps in the rules themselves, fixed here and in `scorers.py`. See section 7.3
and [`data/methodology_test_2026-09-17.md`](data/methodology_test_2026-09-17.md).

Primary sources only: the official `zcash/zips` repository (rendered at `zips.z.cash`),
the Zcash protocol specification source in that repository, the official node
repositories (`ZcashFoundation/zebra`, `zcash/zcash`, `zakura-core/zakura`), their
GitHub release and tag data, crates.io and Docker Hub for Zebra distribution, the
official Zcash documentation, NEAR Intents documentation, and direct reads of Zcash
Mainnet and Testnet through public lightwalletd gRPC servers with the read-only helpers
in [`scripts/`](scripts/) (plain `curl` plus Python standard library, no keys, no
signing). Live values were read on 2026-09-17 (Mainnet tip 3,486,406) and drift.

Scale convention is the repo's existing one (`src/AuthorityRiskOracle.sol`): every
sub-score is 0-100, higher is safer.

## 1. What kind of chain this is

| Question | Answer | Source |
|---|---|---|
| General-purpose smart contracts? | No. Zcash is a UTXO chain with a transparent pool (Bitcoin-style script) and shielded pools (Sprout, Sapling, Orchard, and since NU6.3 Ironwood). There is no contract VM on Mainnet, so "deploy a contract" does not apply | [ZIP 258](https://zips.z.cash/zip-0258), [ZIP 224](https://zips.z.cash/zip-0224) |
| Programmable extensions planned? | Transparent Zcash Extensions (ZIP 222) and Zcash Shielded Assets (ZIP 226, ZIP 227) are Draft. No deployment ZIP schedules them: ZIP 254 (NU7 deployment) is Withdrawn and its replacement draft `draft-arya-deploy-nu7` has Mainnet activation height "TBD" and does not list ZIP 222, 226 or 227 | [ZIP 222](https://zips.z.cash/zip-0222), [ZIP 226](https://zips.z.cash/zip-0226), [ZIP 227](https://zips.z.cash/zip-0227), [ZIP 254](https://zips.z.cash/zip-0254), [draft-arya-deploy-nu7](https://github.com/zcash/zips/blob/main/zips/draft-arya-deploy-nu7.md) |
| Multisig primitive | Transparent P2SH `m-of-n` scripts (`OP_CHECKMULTISIG` or `OP_CHECKMULTISIGVERIFY`), wallet conventions in Draft ZIP 48. FROST threshold signatures for shielded spends exist only as Draft ZIP 312 | [ZIP 48](https://zips.z.cash/zip-0048), [ZIP 312](https://zips.z.cash/zip-0312), on-chain redeem scripts in 3.2 |
| Timelock primitive | Transaction `lock_time` (absolute) and transaction expiry. The specification states Zcash "does not currently support BIP 68" (no relative locks). No protocol-level delay on rule changes; the only notice mechanism is the ZIP 200 upgrade schedule plus node End-of-Service halts | [Protocol spec source](https://github.com/zcash/zips/blob/main/protocol/protocol.tex) (§ 7.1.2 'Transaction Consensus Rules'), [ZIP 203](https://zips.z.cash/zip-0203), [ZIP 200](https://zips.z.cash/zip-0200) |

Consequence: "admin key of a contract" does not exist on Zcash L1. The authority
objects are (a) the consensus rules and whoever can get a rule change activated,
(b) protocol-defined funds and the keys that receive them, (c) proving-system
parameters that shielded-pool soundness depends on, (d) block producers, and
(e) representations of ZEC on other chains, whose authority lives on those chains.

## 2. Networks and endpoints (confirmed by direct read)

Zcash has no EVM-style chain id. A network is identified by its P2P magic bytes, its
address prefixes and, for a given rule set, its consensus branch id.

| Network | P2P magic | Transparent prefixes | Live branch id | Endpoints read | Evidence |
|---|---|---|---|---|---|
| Mainnet | `24 e9 27 64` | `t1` (P2PKH, lead bytes `1C B8`), `t3` (P2SH, `1C BD`) | `0x37a5165b` (NU6.3) | `zec.rocks:443`, `zcash.mysideoftheweb.com:9067` (two distinct domains), `eu.zec.rocks:443` | `GetLightdInfo` returns `chainName=main`, `consensusBranchId=37a5165b`, tip 3,486,406 on both first endpoints; magic bytes in [Zebra constants.rs](https://github.com/ZcashFoundation/zebra/blob/main/zebra-chain/src/parameters/constants.rs); prefixes from the lead bytes defined in the protocol spec source (transparent address encoding) |
| Testnet | `fa 1a f9 bf` | `tm` (P2PKH, `1D 25`), `t2` (P2SH, `1C BA`) | `0x37a5165b` (NU6.3, Testnet height 4,134,000) | `testnet.zec.rocks:443` | `GetLightdInfo` returns `chainName=test`, tip 4,359,624; height in [ZIP 258](https://zips.z.cash/zip-0258) and Zebra constants.rs |
| Regtest | `aa e8 3f 5f` | not used here | local | local node only | Zebra constants.rs |

Notes for scorer implementation:

- Reads use the lightwalletd gRPC service `cash.z.wallet.sdk.rpc.CompactTxStreamer`
  (`GetLightdInfo`, `GetBlock`, `GetBlockRange`, `GetTaddressTxids`,
  `GetTaddressBalance`). The two Mainnet domains read here reported `/Zebra:6.3.0/`
  backends, so they are distinct operators of the same implementation. A load-balanced
  domain can answer from different backends per request (see `eu.zec.rocks` in 3.1).
- Since NU6.3, blocks carry version 6 transactions ([ZIP 229](https://zips.z.cash/zip-0229)).
  Their header layout is the same as v5 up to `tx_in_count`; `scripts/zcash_read.py`
  parses both.
- Shielded state is not readable without viewing keys. Any authority object whose funds
  move into a shielded pool becomes unscorable on chain from that point.
- Testnet uses separate funding-stream recipients ([ZIP 214](https://zips.z.cash/zip-0214)
  lists `t2HifwjUj9uyxr9bknR8LFuQbc98c3vkXtu` for the Testnet ZCG stream), so Testnet
  shows mechanics only, never Mainnet authority.

## 3. Real authority primitives

### 3.1 Consensus rule changes and who ships them

| Fact | Source |
|---|---|
| Rule changes ship as network upgrades gated by `ACTIVATION_HEIGHT` and a new `CONSENSUS_BRANCH_ID`. Nodes that do not upgrade stay on the old branch | [ZIP 200](https://zips.z.cash/zip-0200) |
| The ZIP process is run by the ZIP Editors. ZIP 0 (exact wording): "The ZIP Editors MAY reject a new ZIP draft or an update to an existing ZIP, by consensus among the current Editors"; "Additional Editors may be selected, with their consent, by consensus among the current Editors"; "An Editor may be removed or replaced by consensus among the current Editors. However, if the other ZIP Editors have consensus, an Editor can not prevent their own removal" | [ZIP 0](https://zips.z.cash/zip-0000) (source `zips/zip-0000.rst`, same wording on the rendered page) |
| Minimum composition. ZIP 0 (exact wording): "The current design of the ZIP Process dictates that there are always at least two ZIP Editors, including at least one from the Zcash Foundation." This is a statement about the current design, not an RFC 2119 MUST, and ZIP 0 itself is edited by the same Editors | [ZIP 0](https://zips.z.cash/zip-0000) |
| Current ZIP Editors: **ten** people. Three in their individual capacities (Jack Grigg, Daira-Emma Hopwood, Kris Nuttycombe); two associated with the Zcash Foundation (Arya, Marek); two with Shielded Labs (Mark Henderson, Sam H. Smith); two with Project Tachyon (Sean Bowe, Tal Derei); one with Valar Group (Dev Ojha). Last change: Marek added on 2026-07-31 (commit `378239909e`) | [ZIP 0 source](https://github.com/zcash/zips/blob/main/zips/zip-0000.rst), cross-checked on the rendered [zips.z.cash/zip-0000](https://zips.z.cash/zip-0000) |
| Declared conflicts in ZIP 0: Daira-Emma Hopwood (Head of Research and Assurance at Zcash Open Development Lab); Sean Bowe ("a maintainer of Zakura, a Zcash consensus full node implementation") | [ZIP 0](https://zips.z.cash/zip-0000) |
| ZIP 1016 states that a process ZIP cannot affect "the autonomy of developers of Zcash consensus node software to publish (or not) the software they want to publish" | [ZIP 1016](https://zips.z.cash/zip-1016) |
| `zcashd` is archived on GitHub ("archived by the owner on Jul 19, 2026"); its README says it "is succeeded by" Zebra. Its last release, v6.20.0, sets the NU6.2 height but has no NU6.3 height in `chainparams.cpp` (also absent on `master`), and its End-of-Service height (3,417,100) is below the NU6.3 activation height, so `zcashd` cannot follow Mainnet today | [zcash/zcash](https://github.com/zcash/zcash), `scripts/eos_vs_activation.py`, `scripts/first_release_check.py` |
| Zebra (Zcash Foundation) is the reference node. Mainnet heights: NU6 2,726,400, NU6.1 3,146,400, NU6.2 3,364,600, NU6.3 3,428,143 | [Zebra constants.rs](https://github.com/ZcashFoundation/zebra/blob/main/zebra-chain/src/parameters/constants.rs), [ZIP 253](https://zips.z.cash/zip-0253), [ZIP 255](https://zips.z.cash/zip-0255), [ZIP 257](https://zips.z.cash/zip-0257), [ZIP 258](https://zips.z.cash/zip-0258) |
| Zakura is a second node that is live on Mainnet: 12 successive `GetLightdInfo` reads of `eu.zec.rocks:443` returned `/Zakura:1.3.1/` 6 times and `/Zebra:6.3.0/` 6 times, all on branch id `37a5165b`. Its README says "Zakura is forked from Zebra" and cites Project Tachyon and Valargroup; its `Cargo.toml` uses renamed forks of the proving crates (`zakura-orchard`, `zakura-sapling-crypto`, `zakura-halo2-proofs`, and names `zakura-halo2-gadgets` in its build profiles) and still depends on upstream `zcash_protocol` and `zcash_script` | [zakura-core/zakura README](https://github.com/zakura-core/zakura), [Zakura Cargo.toml](https://github.com/zakura-core/zakura/blob/main/Cargo.toml), live `GetLightdInfo` |

Interpretation: Mainnet today runs one code lineage (Zebra) with one downstream fork
(Zakura). A consensus bug in shared upstream crates or in code Zakura inherited
unchanged hits both. Zakura is evidence of a second maintainer group, not of an
independent implementation, and one of its maintainers is a ZIP Editor. Its share of
nodes and hash rate was not measured from a reproducible source and must not be assumed.

### 3.2 Protocol-defined funds (the only on-chain treasury keys)

| Object | Rule | Who controls | Source |
|---|---|---|---|
| `FS_FPF_ZCG_H3`: 8% of block subsidy, Mainnet heights 3,146,400 to 4,406,400 | Consensus requires every Mainnet coinbase in that range to pay `t3cFfPt1Bcvgez9ZbMBFWeZsskxTkPzGCow`; the same address is listed for all 36 periods (no rotation) | Financial Privacy Foundation (FPF) for the Zcash Community Grants committee (ZCG). Key holders of this address are not named in any primary source found | [ZIP 214](https://zips.z.cash/zip-0214), [ZIP 1015](https://zips.z.cash/zip-1015) |
| `FS_CCF_H3`: 12% of block subsidy, same heights | Paid to `DEFERRED_POOL` (the lockbox), a protocol-tracked balance with no address and no key | Nobody until a future network upgrade defines a disbursement | [ZIP 214](https://zips.z.cash/zip-0214), [ZIP 2001](https://zips.z.cash/zip-2001) |
| One-time lockbox disbursement at NU6.1 | 78,750 ZEC in 10 equal outputs to `t3ev37Q2uL1sfTsiJQJiWJoFzQpDhmnUwYo` | 2-of-3 P2SH multisig, keys held by the "Key-Holder Organizations": Zcash Foundation, Electric Coin Company and Shielded Labs | [ZIP 271](https://zips.z.cash/zip-0271) |
| Coinholder-Controlled Fund policy (the fund "seeded by the Deferred Dev Fund Lockbox") | Grant votes every three months after 30 days of community review; at least 420,000 ZEC voted with a simple majority; Key-Holders "SHOULD sign"; veto by any one Key-Holder on legal or reporting grounds, or by two or more on principled grounds. The voting model itself is "specified in another ZIP [TBD]" | Off-chain process, not consensus | [ZIP 1016](https://zips.z.cash/zip-1016) |
| Precedent | ZIP 1015: substantial unremedied violation by FPF "will result in a modified version of Zcash node software that removes ZCG's Dev Fund slice" | Node maintainers plus adopters | [ZIP 1015](https://zips.z.cash/zip-1015) |

Live reads (Mainnet, 2026-09-17, `scripts/p2sh_spends.py`, `scripts/zcash_read.py`,
identical on both operators where cross-checked):

| Read | Result |
|---|---|
| Transactions touching `t3ev37...` since 3,146,400 | 4: the disbursement coinbase at 3,146,400 (10 outputs, 78,750 ZEC), spends at 3,227,947 and 3,308,125, and an incoming transaction at 3,227,959. Both spends reveal a redeem script hashing to the address: `OP_2 <3 pubkeys> OP_3 OP_CHECKMULTISIG` |
| Flow | 3,227,947 spent one 7,875 ZEC chunk with no transparent output; 12 blocks later (3,227,959) a transaction with no transparent input paid 7,438.2295 ZEC back to `t3ev37...`. 3,308,125 spent that output and paid 7,308.4093 ZEC back to the address. Net outflow 566.5907 ZEC |
| Balance of `t3ev37...` | 78,183.4093 ZEC (7,818,340,930,000 zatoshi on both operators): 9 of the 10 original chunks never moved, 99.3% of the disbursement is still in the transparent 2-of-3 |
| Spends from ZCG `t3cFfPt1...`, blocks 3,475,800 to 3,485,800 | 8 sweep transactions (heights 3,478,969 and 3,478,971; 1,001 inputs each, no transparent output) out of 10,009 transactions scanned. Redeem script: `OP_2 <3 pubkeys> OP_3 OP_CHECKMULTISIGVERIFY <4-byte nonce> OP_DROP OP_DEPTH OP_0 OP_EQUAL`, i.e. a 2-of-3. Its three public keys (prefixes `0352d50656`, `02f39d0b69`, `027072ba23`) differ from those of `t3ev37...` (`0248ca6a21`, `027f05a867`, `030b7820b7`) |

Norm versus practice. Two different layers apply to the one-time disbursement:

- Consensus: a transaction with a transparent input from a coinbase transaction "MUST
  have no transparent outputs" (protocol spec § 7.1.2), so each coinbase chunk can only
  leave `t3ev37...` into a shielded pool. The observed spend with no transparent output
  is that rule, not a choice.
- Rationale, not a MUST: ZIP 271 expects the shielded destination "would presumably be
  to a FROST address in order to maintain consistent security position over the lockbox
  funds". In practice the one shielded chunk returned, mostly, to the same transparent
  2-of-3 twelve blocks later.

Mitigating context: transparent custody keeps the balance auditable; low outflow is
consistent with grants being paid only after coinholder votes; ZIP 271 splits the
disbursement into 10 outputs precisely to allow shielding "only part of the disbursement
at a time". Aggravating context: ZIP 271 states "Compromise or loss of 2 of these 3 keys
would result in total loss of funds", and key rotation means moving the funds by hand.

### 3.3 Proving-system parameters (soundness authority)

| Pool | Proving system | Setup | Source |
|---|---|---|---|
| Sprout, Sapling | Groth16 | "Trusted setup": a Structured Reference String from an MPC whose hidden structure "if known could be used to create fake proofs and thus counterfeit funds". ZIP 224 notes 6 participants in the Sprout MPC and "around 90 per round" for Sapling | [ZIP 224](https://zips.z.cash/zip-0224) |
| Orchard | Halo 2 | Chosen as a proving system that "does not require an SRS". A soundness bug in the Orchard Action circuit implementation (balance violation and theft possible) was reported on 2026-05-29 and fixed at NU6.2 | [ZIP 224](https://zips.z.cash/zip-0224), [ZIP 257](https://zips.z.cash/zip-0257) |
| Ironwood (NU6.3) | Orchard protocol, new pool | Since NU6.3 no new value may enter the Orchard pool; value may leave it, including across the turnstile into Ironwood | [ZIP 258](https://zips.z.cash/zip-0258) |

[ZIP 209](https://zips.z.cash/zip-0209): if any chain value pool balance would become
negative, "all nodes MUST reject the block as invalid", which bounds a counterfeiting
bug to that pool's visible balance.

### 3.4 Block production

| Fact | Source |
|---|---|
| Proof of work (Equihash). No validator set, no stake, no slashing | [Protocol spec source](https://github.com/zcash/zips/blob/main/protocol/protocol.tex), [Zebra equihash.rs](https://github.com/ZcashFoundation/zebra/blob/main/zebra-chain/src/work/equihash.rs) |
| Miners decide whether a soft fork is enforced in practice: `zcashd` v6.12.4 used Mainnet height 3,363,366 for the Orchard-disabling soft fork; "Some mining pools failed to upgrade in time, so the activation was re-attempted successfully" at 3,363,426 | [ZIP 257](https://zips.z.cash/zip-0257) |
| Blocks 3,483,700 to 3,485,699 (2,000 blocks), each attributed to its largest coinbase transparent output excluding the two fund addresses: 15 distinct transparent payout addresses plus 93 blocks (4.7%) with no attributable transparent payout. Shares of all 2,000 blocks: top address 29.1%, top 2 44.7%, top 3 59.1%, top 4 72.2%. Byte-identical output on both operators | `scripts/miner_concentration.py` |

Caveat: payout addresses are not pool identities; pool names are not asserted. The 4.7%
unattributed blocks may belong to any of the listed payers, so top-N shares are lower
bounds.

### 3.5 ZEC outside Zcash

| Fact | Source |
|---|---|
| NEAR Intents documents a "POA (Proof of Authority) Bridge" that "uses a Proof of Authority consensus model to validate cross-chain transfers" and lists Zcash among supported chains | [NEAR Intents docs](https://docs.near-intents.org/llms-full.txt) |
| `zec.omft.near` is a NEP-141 token, symbol `ZEC`, 8 decimals, total supply between 139,000 and 140,000 ZEC on 2026-09-17 (139,679.21 then 139,248.95 ZEC in two reads minutes apart: it moves with bridge flows), no access keys on the token account | NEAR RPC `ft_metadata`, `ft_total_supply`, `view_access_key_list` on `rpc.mainnet.near.org`, supply cross-checked on `free.rpc.fastnear.com` (same value at the same moment) |

These are claims on ZEC held by an off-Zcash authority, scored with the host chain's
method and relevant only to cross-exposure.

### 3.6 Native ZEC vaulted for an external network (Maya Protocol Asgard vaults)

The mirror image of 3.5: not ZEC *represented on* another chain, but real transparent
ZEC that sits *on Zcash Mainnet itself*, in ordinary-looking `t1` (P2PKH) addresses,
controlled entirely by an external network's own validator set through a Threshold
Signature Scheme (TSS) -- no Zcash script, no Zcash key. Identified by
`data/scouting_candidates_2026-09-18.md`'s DefiLlama-wide scan (the only new real
target out of 3 hits) and left unscored pending this section, per that scouting
pass's own "why this is a target and not scored yet" note.

| Fact | Source |
|---|---|
| Maya Protocol (`mayaprotocol.com`, a THORChain-model fork) holds ZEC in "Asgard" vaults; membership and coin balances are read from its own full-node REST API, authoritative for vault state the way a Safe's own `getOwners()` is for an EVM multisig | `mayanode.mayachain.info` (`/mayachain/vaults/asgard`) |
| Two `ActiveVault` entries hold ZEC.ZEC as of 2026-09-18 (two further `RetiringVault` entries also list a ZEC address but hold `0` ZEC.ZEC -- immaterial, not scored): vault A `t1RBiXrLRdrHgsuSGQEusG2wCzPFczEVMfT` (pub_key `...pljmch`), vault B `t1VtnnhTYhmADh7L2uKU3Sev7GscBHT6HfE` (pub_key `...8225yt4w`) | `/mayachain/vaults/asgard`, re-read live 2026-09-18 |
| Live on-chain balance, both Zcash lightwalletd operators agreeing: vault A 220,970,943,152 zat (exact match to Mayanode's internal ledger); vault B 126,951,364,578 zat (Mayanode's internal ledger says 129,157,478,056 zat -- see reconciliation below) | `chains/zcash/scripts/zcash_read.py taddr_balance()`, `zec.rocks:443` and `zcash.mysideoftheweb.com:9067` |
| Each vault's own TSS `membership` list (the literal signer-key set, equivalent to `getOwners()`) has exactly 20 pubkeys today. The two vaults' 20-member sets are **completely disjoint** (0 shared members) -- verified by direct set intersection, not assumed | `/mayachain/vaults/asgard`, field `membership` |
| ZEC inbound/outbound through these vaults is currently halted by Mayachain's own network (`"halted": true, "chain_trading_paused": true` for chain `ZEC`) -- the balances above are real value at rest, not evidence of live flow | `/mayachain/inbound_addresses` |

**TSS required-signer threshold, derived from a primary source, not assumed.**
`data/scouting_candidates_2026-09-18.md` left this as an explicit open item ("the
actual signing threshold enforced among those 20 ... was not confirmed from a primary
source this pass"). Resolved by reading Mayanode's own source
(`gitlab.com/mayachain/mayanode`, commit `ad1072c33ca2091fe12917de2321578474e3e3eb`,
`develop` branch, 2026-09-17):

- `bifrost/tss/go-tss/conversion/conversion.go`, `func GetThreshold(value int)`:
  `threshold := int(math.Ceil(float64(value)*2.0/3.0)) - 1`.
- Every keygen/keysign call site in `bifrost/` (8 call sites, e.g.
  `bifrost/tss/go-tss/keygen/ecdsa/tss_keygen.go:84`,
  `bifrost/tss/go-tss/keygen/ecdsa/tss_keysign.go:106`) passes this `threshold`
  straight into the underlying tss-lib ceremony
  (`btss.NewParameters(curve, ctx, partyID, len(partiesID), threshold)`) using
  `len(localStateItem.ParticipantKeys)` -- i.e. the specific vault's own live
  membership count, not a hardcoded network constant.
- tss-lib's own convention: a degree-`t` polynomial needs `t + 1` shares to sign, so
  the real minimum co-signer count is `threshold + 1 = ceil(n * 2/3)`.
- For `n = 20` (both vaults today): `ceil(40/3) = 14`. **14-of-20** for each vault.

Disclosed limitation: this is inferred from the generic TSS code path every ceremony
uses, not from an API field literally named "signing threshold" for a given vault --
no such field exists on `/mayachain/vaults/asgard`. A second, independent Mayachain
full-node API to cross-check this and the membership/halted reads against was sought
and not found reachable (`chains/zcash/scripts/maya_read.py`'s module docstring lists
the hostnames probed, all DNS failures) -- unlike every Zcash-side read in this
project, which stays cross-checked on two independent lightwalletd operators, this
Mayachain-side data relies on one source, disclosed rather than presented as having
the same guarantee.

**Reconciliation, disclosed rather than smoothed over.** Three ZEC figures for this
target do not agree, all re-read live on 2026-09-18: live on-chain sum today is
3,479.22307730 ZEC; Mayachain's own `ZEC.ZEC` pool ledger (`/mayachain/pool/ZEC.ZEC`,
`balance_asset`) reads 2,646.55627636 ZEC (unchanged from the scouting pass earlier
the same day); DefiLlama's `currentChainTvls.Zcash` for `maya-protocol` reads
$3,893,942.38 (drifted from $3,878,122.63 a few hours earlier the same day -- a
live-fluctuating figure, not a fixed one). Not chased to a conclusion -- flagged, not
guessed at.
Separately, vault B's own ~22.06 ZEC gap (internal ledger above live on-chain balance
by 2,206,113,478 zat) remains **genuinely unresolved, not just unconfirmed**: an
earlier draft of this note proposed a specific `/mayachain/queue/outbound` entry
(~2,206,088,478 zat) as a plausible cause, but independent re-reads of that same
endpoint on the same day matched that amount to different `vault_pub_key` values
across checks -- the queue is live and mutates (entries are processed/resubmitted)
faster than it can be reliably cross-checked, so amount-matching against it cannot
attribute a specific entry to this vault with confidence. No confirmed explanation
for the gap exists. The scorer uses the live on-chain balance (the two-operator-agreed,
directly-verified figure) for its own disclosure, not the ledger or DefiLlama number.

**Tooling fix, 2026-09-18:** `scripts/zcash_read.py`'s `tx` subcommand hardcoded a
P2SH-only output matcher, so it silently returned `outputs_to_addr=0` for every real
transaction to a `t1`-prefixed (P2PKH) address such as either Maya vault -- a false
negative from a tooling gap, flagged but not fixed by the scouting pass. Fixed by
adding the standard P2PKH matcher (`76a914<hash160>88ac`), selected from the
address's own prefix (mainnet `t1`/testnet `tm` -> P2PKH, `t3`/`t2` -> P2SH, per
section 2's table) -- the same script-template convention already independently used
and trusted by `scripts/miner_concentration.py`'s own `addr()` decoder, cross-checked
against it rather than invented fresh.

### 3.7 Native ZEC vaulted for a per-deposit dMPC keyring (Zenrock `zenZEC`)

A close cousin of 3.6, not the same shape: real transparent ZEC sitting on Zcash
Mainnet, controlled by an off-Zcash signer network -- but Zenrock's own custody model
generates a FRESH Zcash key per user deposit rather than a small fixed set of vault
addresses, so no enumerable "vault" the way Maya's two Asgard vaults are exists.
Identified by `data/scouting_candidates_2026-09-18.md`'s second (beyond-DefiLlama)
scouting pass, deferred that day because Zenrock's hosted docs
(`docs.zenrocklabs.io`) and REST/LCD gateway (`api.diamond.zenrocklabs.io`) both
returned `Payment Required` (HTTP 402) / HTTP 503. Re-checked 2026-09-19: identical
failure, not a stale check.

| Fact | Source |
|---|---|
| `zenZEC` (Zenrock, `zenrocklabs.io`) wraps native ZEC 1:1 on Solana. Live Solana Mainnet supply, re-read 2026-09-19 (unchanged from 2026-09-18): 494.51437135 zenZEC, on the order of $770K at today's CoinGecko spot ($1,556.49/ZEC) | Solana Mainnet RPC (`api.mainnet-beta.solana.com`), `getTokenSupply` on mint `JDt9rRGaieF6aN1cJkXFeUmsy7ZE4yY3CZb8tVMXVroS`; independently corroborated by CoinDesk and Bitget News reporting (2026-09-18 finding) |
| Zenrock's own docs/API workaround: its Tendermint/CometBFT RPC (`rpc.diamond.zenrocklabs.io`) DOES answer, and CometBFT's `/abci_query` routes to the same gRPC-gateway Query services the REST gateway would otherwise translate -- confirmed by Zenrock's own validator-setup guide (`zenrocklabs/zenrock-validators`) and the Cosmos chain-registry (`diamond-1` = "Zenrock Mainnet") | `chains/zcash/scripts/zenrock_read.py`, hand-built against `github.com/Zenrock-Foundation/zrchain`'s own published `.pb.go` source |
| Live `zrchain.dct.Query/QueryParams` read resolves `ASSET_ZENZEC`'s `DepositKeyringAddr` to `keyring1k6vc6vhp6e6l3rxalue9v4ux`, description `"Zenrock MPC"` -- NOT the placeholder hardcoded in zrchain's own `x/dct/keeper/params.go` `DefaultParams()` (`keyring1pfnq7r04rept47gaf5cpdew2`), which a live `KeyringByAddress` query resolves to `"not found: unknown request"` (a dev/test fixture never deployed, confirmed by trying it) | `zenrock_read.get_dct_asset_params(2)`, `get_keyring()` |
| That same live read's `Solana.MintAddress` field matches, byte for byte, the mint independently verified live on Solana above -- strong cross-source evidence this is the real deployed configuration | `zenrock_read.get_dct_asset_params(2)` |
| The keyring's live `parties`/`party_threshold` (`x/identity`'s own "the number of parties required to submit signed txs" definition): 3 parties, threshold 3 -- a 3-of-3, unanimous dMPC signer set, 1 admin | `zenrock_read.get_keyring()`, `zrchain.identity.Query/KeyringByAddress` |
| The two Zcash-mainnet infrastructure addresses nameable from this config (rewards-deposit key 387, change-address key 388) both independently re-derive correctly from their live on-chain pubkeys (this project's own P2PKH math matches zrchain's own reported address exactly, both keys) but hold 0 ZEC on both of this project's own lightwalletd operators today | `zenrock_read.get_key_by_id()`, `scripts/zcash_read.py taddr_balance()`, `zec.rocks:443` and `zcash.mysideoftheweb.com:9067` |
| The SAME keyring is live-confirmed as zenBTC's own `DepositKeyringAddr` too -- Zenrock's shared core dMPC custody keyring across at least two wrapped assets, not zenZEC-specific | `zrchain.zenbtc.Query/QueryParams`, live 2026-09-19 |

**Disclosed limitations (not smoothed over):**

- SINGLE SOURCE, DATED. Only `rpc.diamond.zenrocklabs.io` answered this pass; the
  chain-registry's second RPC operator (`rpc.zenrock.nodestake.org`) refused every
  connection. That one node's own `/status` reports its last ingested block at height
  9,534,552 / `2026-08-10T23:19:52Z` with `n_peers: 0` -- isolated from the network,
  not proof the whole `diamond-1` Mainnet (chain-registry: `"status": "live"`) is
  halted, but no fresher zrchain endpoint could be found to confirm today's real tip.
  Every fact above is that ~40-day-old snapshot.
- MUTABLE, unlike a P2SH script. A keyring's `parties`/`party_threshold` can change
  on-chain (`x/identity`'s own `message_add_keyring_party.go` /
  `message_remove_keyring_party.go` / `message_update_keyring.go` exist) -- not a
  cryptographic commitment fixed forever the way a P2SH redeem script's `HASH160` is.
- Bulk custody address(es) still not determined. Confirms, not overturns, the
  2026-09-18 scouting finding: the two named infrastructure addresses hold 0 ZEC, and
  the real per-deposit addresses are not enumerable from public on-chain config (would
  need the still-down indexer/REST API, or brute-forcing sequential Key IDs -- not
  attempted).
- Party identities are zrchain accounts, not named operators. Whether the 3 `Parties`
  map to 3 distinct physical institutions (Zenrock's own marketing claims "eight
  institutional operators", an unverified secondary claim per the 2026-09-18 scouting
  pass) was not checked.
- `x/policy` ("Approval policies and governance", per zrchain's own module table) may
  impose additional signing constraints atop the raw keyring threshold -- not checked
  this pass, an open item, not assumed irrelevant.

## 4. The five dimensions, translated

Target types:

| Target type | Identifier proposal |
|---|---|
| `L1` | the Zcash Mainnet rule set, keyed by consensus branch id |
| `FUND` | a protocol-defined recipient (`t3ev37...`, `t3cFfPt1...`) or `DEFERRED_POOL` |
| `POOL` | a shielded value pool (Sapling, Orchard, Ironwood) |
| `EXT` | an off-Zcash ZEC representation, for example `zec.omft.near` |
| `ASSET` | future ZSA issuer (ZIP 227 issuance keys), not live, not scored |
| `XVAULT` (added 2026-09-18) | native ZEC held on Zcash Mainnet itself (an ordinary `t1`/`t3` address, not a protocol-defined `FUND`), custodied by an external network's own TSS/validator authority rather than a Zcash key -- the mirror image of `EXT`. See section 3.6/4.7. First target: Maya Protocol's Asgard vaults |
| `MPCKEYRING` (added 2026-09-19) | native ZEC destined for Zcash Mainnet under an off-Zcash dMPC signer network's authority, close cousin of `XVAULT` but scored at the KEYRING level (the party-threshold object that gates every key that network ever generates) rather than at the address/vault level, because the custody model generates a fresh Zcash key per deposit instead of a small fixed set of vaults -- no single enumerable vault address exists to score the way `XVAULT` does. See section 3.7/4.8. First target: Zenrock's `zenZEC` custody keyring |

The oracle keys scores by `address`; the methodology phase must fix a deterministic
mapping such as `address(uint160(uint256(keccak256("zcash:mainnet:<id>"))))`.

### 4.1 adminKeyScore

Meaning on Zcash: who can change what the target does, and how few parties that takes.

| Target | Rule and measurable input |
|---|---|
| `L1` | No on-chain key. The admin is the release process of the node software that Mainnet runs. Inputs: number of distinct code lineages following Mainnet (today 1, Zebra, with Zakura as a fork; `zcashd` can no longer follow); number of distinct node software projects observed live (today 2, Zebra and Zakura, from `nodeSubversion`); the size and composition of the ZIP Editor group that gates specifications (10 Editors, 3 individual plus 4 organisations). The ZIP 257 emergency path shows Mainnet rules can change with no public release before activation (4.3) |
| `FUND` multisig | The keys are the admin: 2 signatures move everything in one transaction. Scored with 4.2 |
| `DEFERRED_POOL` | No key. Only a network upgrade can move it (ZIP 271 did once). Inherits the `L1` score |
| `POOL` | No key. Replaced by setup risk: no SRS (Halo 2) scores higher than an MPC SRS (Groth16) |
| `EXT` | Host-chain methodology |

### 4.2 multisigScore

Meaning on Zcash: the P2SH threshold revealed on chain, plus signer independence from
primary governance documents.

| Target | Rule and measurable input |
|---|---|
| `FUND` | Decode the redeem script of a spend and check `HASH160(script)` equals the address. Live: `t3ev37...` 2-of-3 (signers named in ZIP 271), `t3cFfPt1...` 2-of-3 (signers not publicly named, which lowers the independence part). Key disjointness between the two funds is checked by comparing pubkeys (disjoint today). A P2SH address commits to exactly one script, so one valid spend fixes the threshold for that address for good; key rotation means moving funds to a new address, which is a new target |
| Recognised script shape | Only `OP_m <n compressed pubkeys> OP_n OP_CHECKMULTISIG` with nothing after it, or `... OP_CHECKMULTISIGVERIFY` followed by zero or more `<push> OP_DROP` pairs and then `OP_DEPTH OP_0 OP_EQUAL` or `OP_1` (constraint-only suffixes; the ZCG address uses a 4-byte nonce plus the clean-stack check). Bytes after a plain `OP_CHECKMULTISIG` can invert the result (for example `OP_DROP OP_1` makes it anyone-can-spend), so any other shape is unresolved |
| `L1` | The quorum that enforces rules is hash rate. Input: number of payout addresses needed to exceed 50% (`k50`) and 25% (`k25`) of the 2,000 blocks ending 10 blocks below the lower tip of two lightwalletd operators (window recomputed every run, both operators must agree). Today 3 and 1. A payout address is not an entity: one operator can pay to several addresses, and 4.7 to 5.1% of blocks pay no attributable transparent output. `k50` is therefore an upper bound on the number of independent entities, and the score derived from it is an upper bound (see the sensitivity check in 7.3) |
| Unresolved P2SH (replaces "Unspent P2SH: score 0") | Applies when no spend in the scanned history reveals a script hashing to the address, when the revealed script is not a recognised shape, or when the two operators disagree. The threshold is unknown, and a declared threshold in a ZIP does not count (ZIP 271 names a 2-of-3 but publishes no pubkeys; `t3ev37...` was in this state for 81,547 blocks, from 3,146,400 to its first spend at 3,227,947). Score: the floor of the 4.6 ladder for any real m-of-n, `adminKeyScore` 5 and `multisigScore` 16, flagged unresolved, `crossExposureScore` left null. Not 0: 0 is outside the ladder and would rank an unknown script below every script that can exist. Not the former 20/20 placeholder: it ranked an unknown script above a known 1-of-3 (5/18) |
| Shielded custody (FROST, ZIP 312) | Threshold invisible on chain: score only from a published key-generation transcript or viewing key |

### 4.3 timelockScore

Meaning on Zcash: real notice between public availability of a rule change and its
activation. The declared norm and the measured practice differ, and the score must use
the measured value.

Declared norm ([ZIP 200](https://zips.z.cash/zip-0200)): `ACTIVATION_HEIGHT` "MUST be
greater than the value of DEPRECATION_HEIGHT in the last software version that will not
contain support for the network upgrade" and "SHOULD be chosen to be reached
approximately three months after" the first software version containing support is
released.

Measured notice (GitHub release publication time, or tag time when no release exists,
versus activation block timestamp read by lightwalletd, `scripts/notice_period.py`).
Each cited tag is proven to be the first tag whose node source carries the Mainnet
height, with the height absent at the preceding release tag
(`scripts/first_release_check.py`, reading `src/chainparams.cpp` for `zcashd` and
`zebra-chain/src/parameters/network_upgrade.rs`, `constants.rs` or `network.rs` for
Zebra). The preceding tags were checked against the full tag lists: there is no Zebra
`v4.5.2` tag and no public `zcashd` `v6.12.4` tag.

| Upgrade | Activation block time (UTC) | First release setting the Mainnet height | Notice |
|---|---|---|---|
| NU6 (2,726,400) | 2024-11-23 11:02 | zcashd v6.0.0 / zebra v2.0.0 | 49.5 days (zcashd release) / 28.5 days (Zebra v2.0.0, a lightweight git tag, so this is the date of the tagged commit, 2024-10-25 22:52 UTC, an upper bound) / 23.8 days (Zebra v2.0.1, released 2024-10-30 14:53 UTC). Zebra v2.0.0 has no GitHub Release, no crates.io version and no Docker Hub `zfnd/zebra` tag (all return 404); v2.0.1 exists on all three and is the first distributed Zebra build with the NU6 Mainnet height |
| NU6.1 (3,146,400) | 2025-11-24 19:56 | zcashd v6.10.0 / zebra v3.0.0-rc.0 | 51.7 / 39.2 days |
| Orchard emergency soft fork (3,363,426) | 2026-06-02 03:30 | zcashd v6.12.5 / zebra v4.5.3 | release pages published 2.2 h / 2.9 h after activation; annotated tags dated 02:52 / 03:13 UTC, about 38 / 17 minutes before activation |
| NU6.2 (3,364,600) | 2026-06-03 04:03 | zebra v5.0.0 / zcashd v6.20.0 | release pages published 3.3 h / 17.4 h after activation. Zebra's release notes tell operators "If the activation height has passed and your node followed a fork, you will need to sync from scratch" |
| NU6.3 (3,428,143) | 2026-07-28 14:07 | zebra v6.0.0 (no zcashd support) | 17.7 days; the Mainnet height was committed to ZIP 258 in `zcash/zips` on 2026-07-09 19:56 UTC (commit `cc03f14217`), 18.8 days before activation |

ZIP 200 MUST on End-of-Service heights (`scripts/eos_vs_activation.py`, 1,152 blocks per
day):

| Upgrade | Last release without support | End-of-Service height | MUST met? |
|---|---|---|---|
| NU6.1 | zebra v2.5.0 (105 days) / zcashd v6.3.0 (14 weeks) | 3,142,360 / 3,132,000 | yes / yes |
| NU6.2 | zebra v4.5.3 (105 days) / zcashd v6.12.5 (7 weeks) | 3,479,160 / 3,417,100 | no / no |
| NU6.3 | zebra v5.2.0 (37 days) / zebra v6.0.0-rc.0 (10 days) / zcashd v6.20.0 (7 weeks) | 3,424,813 / 3,410,520 / 3,417,100 | yes / yes / yes |

Findings: the three-month SHOULD was not met by any of the last five rule activations
(three scheduled upgrades plus NU6.2 and the emergency soft fork), the best being 51.7
days (zcashd, NU6.1). For Zebra, the node Mainnet runs today, the measured notice of the
three scheduled upgrades is 23.8 (NU6, first distributed release), 39.2 (NU6.1) and 17.7
days (NU6.3): median 23.8 days, against about 90 days declared.

For NU6.3 the MUST was met with a stable Zebra release whose End-of-Service window was
explicitly shortened from 105 to 37 days (v5.2.0, source comment "Reduced to 37 days for
the NU7 network upgrade expected at end of July 2026"), which is compliance with the
letter while cutting the upgrade window. Release candidates are not comparable:
v2.0.0-rc.0 used 35 days "to end support before Mainnet Nu6 activation", v3.0.0-rc.0
used 35 days "for release candidate" with "TODO: Revert to 15 weeks (105 days) for
stable release", and v6.0.0-rc.0 set 10 days while its comment still reads "Reduced to
37 days". The stable v6.0.0 is back to 105 days ("Currently set to 15 weeks").

Mitigating context: the emergency fork and NU6.2 responded to a privately reported
fund-theft vulnerability; ZIP 257 explains that disabling and re-enabling at the same
time "was ruled out due to the risk of revealing the vulnerability before it had been
mitigated"; the emergency change only restricted a feature; the `zcashd` advisory
[GHSA-ghc3-g8w4-whf9](https://github.com/zcash/zcash/security/advisories/GHSA-ghc3-g8w4-whf9)
says the v6.12.4 release was "coordinated with mining-pool partners". Aggravating
context: that path changed Mainnet rules with no public release before activation, and
the v6.12.4 named in ZIP 257 and in the advisory has no tag in the public `zcash/zcash`
repository.

| Target | Rule |
|---|---|
| `L1` | Score from the measured notice of recent scheduled upgrades (median, not the ZIP 200 figure), capped by the existence of an emergency path with no public notice, like an EVM timelock with a guardian bypass |
| `FUND` multisig | No delay: a 2-of-3 spend settles after normal confirmations. ZIP 1016 quarterly votes and 30-day review are off-chain context, not a timelock |
| `DEFERRED_POOL` | Inherits the `L1` scheduled-upgrade notice |
| Coinbase maturity | 100 blocks for transparent coinbase outputs (consensus rule quoted in ZIP 271). Too short to count |

### 4.4 oracleAuthorityScore

Zcash consensus reads no external price or data feed, so a price-oracle signer does not
exist on L1.

| Target | Rule |
|---|---|
| `L1` | Price-oracle part not applicable: 100. The block producer does write data into consensus (ordering, coinbase, timestamps within bounds), but that is the same hash-rate concentration already scored in 4.2's `L1` `multisigScore`. Counting it once only: it is disclosed in the notes of this dimension and never lowers `oracleAuthorityScore` (no double counting of one measurement across two dimensions) |
| Light-client data | The official [wallet app threat model](https://zcash.readthedocs.io/en/latest/rtd_pages/wallet_threat_model.html) (linked from the [lightwalletd README](https://github.com/zcash/lightwalletd)) says a compromised lightwalletd "can't make the user send the wrong amount of funds" but can "omit transactions destined to user" and make a failed transaction look mined. Input: number of independent server operators and backend lineages a wallet can cross-check (today 2 Mainnet domains read, all backends Zebra or its Zakura fork). Disclosed, not scored: the backend lineage count is the input already used by 4.1's `L1` `adminKeyScore`, so scoring it here would count it twice |
| `ASSET` (future ZSA) | ZIP 227 issuance keys would be the supply authority. Not live |
| `EXT` | The bridge's proof-of-authority signer set is the oracle for "ZEC was deposited". Host-chain method |

### 4.5 crossExposureScore

| Exposure | Rule and current evidence |
|---|---|
| Shared organisations | Zcash Foundation maintains Zebra, holds a ZIP Editor seat under ZIP 0 ("The current design of the ZIP Process dictates that there are always at least two ZIP Editors, including at least one from the Zcash Foundation", two today), and holds a key of the 2-of-3 fund `t3ev37...`. Shielded Labs holds two ZIP Editor seats and a fund key. Project Tachyon holds two ZIP Editor seats and one of them (Sean Bowe) declares he maintains Zakura. One organisation acting as node maintainer, spec editor and fund key-holder is a shared root across `L1` and `FUND` |
| Shared code | Zebra and Zakura share lineage and upstream crates; the Orchard bug was in `halo2_gadgets` (ZIP 257), and Zakura's `Cargo.toml` names a renamed `zakura-halo2-gadgets` package |
| Shared infrastructure | The lightwalletd servers read here all sit on Zebra-lineage backends; a Zebra consensus bug reaches every wallet behind them |
| Fund keys | The two on-chain funds use disjoint public keys (checked in 3.2); re-check at every spend |
| Wrapped ZEC | `EXT` targets depend on a signer set outside Zcash; score overlap if those signers appear in other bridges scored in this repo |

### 4.6 Numeric mapping (added 2026-09-17 by the first scorer promotion)

Sections 4.1-4.5 above named measurable inputs and qualitative rules but produced no 0-100
number -- the same gap Hyperliquid's 4.6 and Tempo's 4.1 closed for their own ecosystems on
2026-09-16. This section closes it for Zcash. Reference implementation:
[`scorers.py`](scorers.py) (this project's first Zcash scorer; no prior
`scripts/methodology_test.py` existed to promote from, unlike the other three ecosystems).

| Target | adminKeyScore | multisigScore | timelockScore |
|---|---|---|---|
| `FUND` (P2SH m-of-n, live-decoded from the most recent spend's redeem script) | Reuses `chains/hyperliquid`/`chains/tempo`'s existing k-of-n ladder unchanged (a P2SH redeem-script threshold is the same primitive class -- a bare signature threshold, no role system or vote-permission bitmask): `k>=3` to 65, `k=2` to 50, single key to 10, 1-of-N (N>1) to 5 | Same ladder, Tempo's floored form: `max(16, min(100, 20k - (n-k)))` | 0 -- METHODOLOGY.md 4.3's own explicit ruling: a fund spend has no on-chain delay; ZIP 1016's quarterly-vote/30-day-review process is off-chain context, not a timelock |
| `L1` | Ladder on the count of INDEPENDENT code lineages actually running Mainnet (not raw `nodeSubversion` string count -- Zakura is excluded as a declared fork of Zebra per 3.1, a dated interpretive finding, not something a live read alone determines): 1 lineage to 20 (public source, unlike a closed-source single-signer chain, but the 2026-06 emergency release proves that mitigant does not always hold -- see 4.3), 2 to 45, 3+ to 65. Higher bands are untested: only one live data point exists today | `min(100, 15*k50 + 5*k25)`, `k50`/`k25` = live count of distinct coinbase-payout addresses needed to exceed 50%/25% of the 2,000 blocks ending 10 below the lower tip of two operators, identical on both or degraded to 20 (`scripts/miner_concentration.py`; frozen at 3,483,700-3,485,699 before 2026-09-17 run2). Counted in this dimension only (4.4) -- same formula shape as Hyperliquid's L1 (`15*k_f + 5*k_l`) and Tempo's L1 (`15*k_f + 5*k_l`), adapted to Zcash's own 50%/25% break points from 4.2's stated measurable input rather than reusing Hyperliquid/Tempo's 2/3 and 1/3 (Zcash's real bottleneck is majority hash rate, not a BFT quorum fraction) | Capped at 35 regardless of the measured median scheduled-upgrade notice (23.8 days across Zebra's three scheduled upgrades, which alone would place it in a "80" band on a Tempo-style delay scale) -- the cap reflects the 2026-06 emergency Orchard-disabling soft fork, which shipped with a release carrying NO public tag before activation, the same "instant-bypass exists, cap below the clean value" convention already used for USDtb PSM's freeze bypass on the Ethereum L1 side of this project |

`oracleAuthorityScore` = 100 for every target scored this pass (4.4: Zcash consensus reads
no price). `crossExposureScore`: `FUND` targets with an unresolved threshold use 4.2's unresolved-P2SH floor (5 / 16 / 0, composite 7). `FUND` targets use the repo-wide signer-overlap formula
(`max(0, 100 - 20 * count of other tracked Zcash funds sharing >=1 pubkey)`, live-checked
via redeem-script decoding on every run, not trusted from 3.2's prior finding); `L1` is 100
(it is the shared root itself, same convention as Hyperliquid/Tempo). `compositeScore` uses
the repo-wide `floor(0.4*adminKey + 0.3*multisig + 0.3*timelock + 0.5)`.
`l1CappedComposite = min(compositeScore, L1 compositeScore)` is published alongside every
`FUND` target's own score, never overwriting it (same convention as every other ecosystem's
L1/chain-baseline cap).

`EXT` (`zec.omft.near`) resolved and scored 2026-09-17, same day -- see section 8's
changelog note and `scorers.py`'s `score_ext_zec_omft()`.

### 4.7 XVAULT numeric mapping (added 2026-09-18)

Closes `data/scouting_candidates_2026-09-18.md`'s open item 1 (where a native-ZEC/
off-Zcash-TSS-authority target fits) and item 2 (confirm the real signing threshold
from a primary source, done in 3.6). Reference implementation:
[`scorers.py`](scorers.py)'s `score_maya_asgard_vault()`.

| Dimension | Rule |
|---|---|
| `adminKeyScore` / `multisigScore` | Reuses the SAME bare-`(k, n)`-threshold ladder already applied to Zcash's own P2SH `FUND` targets and to `zec.omft.near`'s DAO Requestor group unchanged: a TSS signing threshold is the same primitive class (a bare co-signer-count threshold, no role system or vote-permission bitmask on top). `k = tss_required_signers(n) = ceil(n * 2/3)` (3.6), `n` = the vault's own live `membership` count |
| `timelockScore` | 0. No on-chain delay gates a completed TSS signature from broadcasting once signed -- the same "`FUND` multisig: no delay" ruling 4.3 already makes for a Zcash P2SH spend |
| `oracleAuthorityScore` | 100. No price or external data feed gates this target |
| `crossExposureScore` | `max(0, 100 - 20 * count of other tracked active XVAULT targets sharing >= 1 TSS member pubkey)`, live-checked by set intersection every run (same signer-overlap formula already used for the two Zcash `FUND` targets, scoped to XVAULT's own member-pubkey space rather than P2SH redeem-script pubkeys, a different key space) |
| `l1CappedComposite` | Deliberately NOT computed, same reasoning as `score_ext_zec_omft()`: this target's controlling authority (Mayachain's own TSS validator set) is entirely off-Zcash. Unlike `EXT`, the ZEC itself does sit on Zcash Mainnet, but Zcash L1 governance has no NAMED, targeted power over this specific address the way it does over a `FUND` (a protocol-defined recipient enforced by consensus itself) -- every other ZEC holder is equally subject to the same generic consensus rules, which is not a targeted authority relationship worth capping against |
| Halted/paused status | Disclosed in the scorer's notes (via `/mayachain/inbound_addresses`), not folded into any of the five dimensions -- it is a fact about current flow, not about who controls the vault, and folding it in would invent a sixth, undocumented scoring input |

Today's live values (both active vaults, 2026-09-18): `n=20`, `k=14` (14-of-20),
`adminKeyScore` 65, `multisigScore` 100 (`min(100, 20*14-(20-14))=274` clipped to 100
by the existing ladder's own cap), `timelockScore` 0, `compositeScore`
`floor(0.4*65+0.3*100+0.3*0+0.5)=56`, `crossExposureScore` 100 for both (membership
sets confirmed disjoint, 3.6).

### 4.8 MPCKEYRING numeric mapping (added 2026-09-19)

Closes `data/scouting_candidates_2026-09-18.md`'s deferred `zenZEC` lead: a real,
non-trivial candidate whose custody model ("whoever can request/sign a new key," not
"whoever holds vault address X") did not fit `XVAULT` as written. Reference
implementation: [`scorers.py`](scorers.py)'s `score_zenzec_mpc_keyring()`.

| Dimension | Rule |
|---|---|
| `adminKeyScore` / `multisigScore` | Reuses the SAME bare-`(k, n)`-threshold ladder already applied to Zcash's own P2SH `FUND` targets, `zec.omft.near`'s DAO Requestor group, and `XVAULT`'s TSS vaults, unchanged: a keyring's `party_threshold` is the same primitive class (a bare co-signer-count threshold, no role system or vote-permission bitmask on top) -- here `k` = the keyring's live `party_threshold`, `n` = its live `len(parties)`, both read fresh every run (`zrchain.identity.Query/KeyringByAddress`), never cached, because unlike a P2SH script's `HASH160` commitment this IS a mutable on-chain parameter |
| `timelockScore` | 0. No on-chain delay of any kind gates a completed dMPC signature from broadcasting once the party threshold is met -- the same "no delay" ruling 4.3/4.7 already make for a Zcash `FUND` spend and an `XVAULT` TSS spend. `x/policy` ("Approval policies and governance") may impose an additional layer not checked this pass -- disclosed as an open item, not assumed irrelevant, and not folded into this score |
| `oracleAuthorityScore` | 100. No price or external data feed gates this target |
| `crossExposureScore` | 100 this run: no OTHER target this Zcash scorer tracks shares this keyring or key space. The live-confirmed fact that this SAME keyring is also zenBTC's `DepositKeyringAddr` is disclosed in the scorer's notes, not scored against this dimension -- zenBTC is not itself a target this Zcash scorer tracks (a different chain/key space entirely), the same "counted once, disclosed not scored twice" discipline 4.4 already applies to backend-lineage counting |
| `l1CappedComposite` | Deliberately NOT computed, same reasoning as `score_ext_zec_omft()`/`score_maya_asgard_vault()`: this target's controlling authority (Zenrock's own dMPC signer network) is entirely off-Zcash and would be unaffected by any Zcash consensus rule change |
| Bulk balance / value-at-risk | NOT computed as a direct on-chain sum (no enumerable vault set exists to sum, unlike `XVAULT`). The two nameable infrastructure addresses (rewards-deposit, change-address) are live-checked every run and both currently hold 0 ZEC on both established lightwalletd operators -- disclosed in the scorer's notes as a real finding, not a gap. The wrapped-supply read on Solana (3.7) is the value-at-risk proxy this project has, one authority-hop removed but independently confirmed to be minted under this exact keyring's control |

Today's live values (2026-09-19): `k=3`, `n=3` (3-of-3, unanimous), `adminKeyScore` 65
(`k>=3`), `multisigScore` `max(16, min(100, 20*3-(3-3)))` = 60, `timelockScore` 0,
`compositeScore` `floor(0.4*65+0.3*60+0.3*0+0.5)` = 44, `oracleAuthorityScore` 100,
`crossExposureScore` 100.

`POOL` deliberately, permanently NOT scored as a 0-100 number: 4.1's own setup-risk
framing (no SRS scores higher than an MPC SRS) rests on an input -- whether at least
one Sprout/Sapling MPC ceremony participant was honest -- that no live read, API call,
or future re-verification can ever confirm or refute, unlike every other score in this
project. Assigning a plausible-looking number here would misrepresent an unfalsifiable
historical-trust judgment as a re-checkable live fact. Full reasoning and the
cross-verified ceremony facts (6 Sprout / ~90 Sapling-per-round participants, Orchard/
Ironwood needing no SRS at all) are in
[`data/pool_trusted_setup_disclosure_2026-09-17.md`](data/pool_trusted_setup_disclosure_2026-09-17.md).

### 4.8.1 A frozen single-source target (added 2026-09-20, applied to target 7 only)

`MPCKEYRING`'s only source is one operator-run zrchain node. On 2026-09-20 that node's latest block was
9,534,552 (2026-08-10T23:19:52Z), about 40 days old, with no peers, and the product behind the keyring was
winding down (`data/zenzec_status_2026-09-20.md`). Convention for that situation, adopted for this target
and NOT yet generalized to other ecosystems (a general rule is a methodology decision for review):

1. A target read from a single source carries its `as_of` (height and block time) and says so. The scorer
   returns `status` and `asOf` next to the score, and the first note is the status line.
2. It is `frozen` while its source tip equals the recorded frozen height. The flag drops itself and asks for
   a human re-read the moment the node moves (`status_review_needed`), rather than staying silent.
3. A frozen target keeps its score, which is a dated reading of the keyring structure and a function of
   `(k, n)` only, but is shown as such, kept out of live ranges and averages, and never described as a live
   risk reading. Nothing is recomputed and no anchored history is rewritten.
4. Say "frozen at height X as seen from the operator RPC", never "halted", unless a second independent source
   confirms it.
5. A zero balance on a derived address is not evidence of absent custody until sweeps have been checked on
   the chain (here, key 388 had 36 transactions and was swept on 2026-06-05).
6. A frozen target is retired (published as a legacy snapshot, never silently deleted) at the next anchor
   when its product is in a documented wind-down and its source cannot be refreshed. When that happens is
   Spap's call. Reversal: independent evidence that the source is producing blocks again.

`scripts/zenzec_status_check.py` reads the triggers that would reopen the question (the Solana authority
chain of the zenZEC mint, the program's deployment slot, the mint authority's activity, the ZEC backing
address, the zrchain tip).

**Retired on 2026-09-20 (rule 6 applied, Spap's decision).** Target 7 is no longer part of the live set:

- `scorers.score_all()` returns the six live targets. `score_all(include_retired=True)` (or a set of ids) still
  returns the seventh, for one reason only: the two ARO2 anchors made before the retirement contain it, and
  `attest_scores.py verify --live` re-derives such a bundle with exactly the retired targets it holds. The list of
  retired targets, the single switch, is `scripts/zcash_retired_targets.py`.
- Its record, exactly as anchored, and the two transactions that contain it are in
  `data/legacy_snapshot_zenzec_keyring_2026-09-20.json`. Nothing is deleted or rewritten: the three anchors that were
  on Zcash Testnet at that moment (ARO1 for the L1 score alone, and both ARO2 for all seven targets) are immutable and still verify.
- Every commitment built from a fresh `score_all()` after this date covers the six live targets and none covers the retired
  one; the first is the anchor of 2026-09-20 (9.8). (A republication of an earlier commitment, `publish_batch.py --reanchors`, republishes that earlier set as it was.)
- Reversal: the rule-2 evidence (the source producing blocks again, confirmed independently) reopens the question. The
  target is put back by removing it from `RETIRED_TARGETS`: the default `score_all()` returns it again, so the next
  commitment covers seven targets, and the two earlier anchors, which contain it, still verify (with the default set).
- Verifying the two earlier anchors LIVE (`verify --live`) still reads the frozen zrchain node for that target; if that
  endpoint disappears the live verification fails closed. The offline verification (`verify` without `--live`) needs no
  network and is unaffected.

## 5. Declared status versus live rules

A scorer must decide what is in force from activation heights and live branch ids, not
from ZIP status. [ZIP 0](https://zips.z.cash/zip-0000) defines Final as "When a
Consensus or Standards ZIP is both implemented and activated on the Zcash network", and
Reserved as a number for which "no ZIP has been published". Measured on 2026-09-17 from
the `Status` header of each file in `zcash/zips`:

| ZIP | Status shown | Live on Mainnet since |
|---|---|---|
| ZIP 258 (NU6.3 deployment) | Draft | 3,428,143 (2026-07-28) |
| ZIP 229 (version 6 transaction format) | Draft | 3,428,143 |
| ZIP 2006 (restricting transfers into the Orchard pool) | Reserved, stub only | 3,428,143, rules restated in ZIP 258 |
| ZIP 2005 (Ironwood quantum recoverability) | Proposed | 3,428,143 |
| ZIP 214 revision 2 (NU6.1 funding streams) | Proposed | 3,146,400 (2025-11-24) |
| ZIP 271 (dev fund extension, disbursement) | Proposed | 3,146,400 |
| ZIP 1016 (Coinholder-Controlled Fund) | Proposed | governs the fund seeded from the lockbox; voting model still "[TBD]" |

## 6. Reproduction commands

```bash
S=chains/zcash/scripts

# Network identity (two Mainnet operators, the Zakura-backed server, Testnet)
python3 $S/zcash_read.py info zec.rocks:443
python3 $S/zcash_read.py info zcash.mysideoftheweb.com:9067
for i in $(seq 12); do python3 $S/zcash_read.py info eu.zec.rocks:443 | grep nodeSub; done | sort | uniq -c
python3 $S/zcash_read.py info testnet.zec.rocks:443

# ZIP Editors (count the bullet lines under "The current ZIP Editors are")
curl -s https://raw.githubusercontent.com/zcash/zips/main/zips/zip-0000.rst | sed -n '/current ZIP Editors are/,/All can be reached/p'

# Upgrade notice: release publication vs activation block time; ZIP 200 End-of-Service MUST
python3 $S/notice_period.py zec.rocks:443
python3 $S/eos_vs_activation.py
python3 $S/first_release_check.py

# Funds: spends and redeem scripts, balance
python3 $S/p2sh_spends.py zec.rocks:443 t3ev37Q2uL1sfTsiJQJiWJoFzQpDhmnUwYo 3146400 3486400 50000
python3 $S/zcash_read.py tx zec.rocks:443 t3ev37Q2uL1sfTsiJQJiWJoFzQpDhmnUwYo 3146400 3486400
python3 $S/zcash_read.py balance zec.rocks:443 t3ev37Q2uL1sfTsiJQJiWJoFzQpDhmnUwYo
python3 $S/p2sh_spends.py zec.rocks:443 t3cFfPt1Bcvgez9ZbMBFWeZsskxTkPzGCow 3475800 3485800 1000

# Coinbase payout concentration over 2,000 blocks
python3 $S/miner_concentration.py zec.rocks:443 3483700 3485699
```

## 7. Corrections

### 7.1 To the first draft (2026-09-16, not approved)

| First draft said | Corrected to | Evidence |
|---|---|---|
| The three-month notice "is honoured for scheduled upgrades" | Never met in the last five activations (4.3) | 4.3 |
| Independent node implementations "today Zebra and Zakura" | One lineage: Zakura is a declared fork of Zebra; `zcashd` cannot follow Mainnet | 3.1 |
| ZCG recipient threshold unknown, score as single key | 2-of-3 decoded from 8 sweep transactions | 3.2 |
| Only the v5 transaction layout was parsed | v6 (post-NU6.3) handled | 2 |
| 1,200-block concentration window | 2,000 blocks | 3.4 |

### 7.2 To the second draft (2026-09-16, not approved) and to figures quoted in its review

| Second draft or review said | Corrected to | Evidence |
|---|---|---|
| ZIP Editors: "three individuals, two associated with the Zcash Foundation, ..." (read as three Editors). The review of that draft gave "seven" | **Ten** Editors, named in 3.1. Both earlier figures were wrong | `zips/zip-0000.rst` on `main` and the rendered page |
| Zebra NU6 notice "28.5 days (Zebra v2.0.0 git tag)" presented as a tag time | v2.0.0 is a lightweight tag: 28.5 days is measured from the tagged commit date and is an upper bound; 23.8 days (v2.0.1) is the first distributed build | GitHub refs API (`object.type=commit`) |
| v2.0.0-rc.0 and v3.0.0-rc.0 both carry "Currently set to 5 weeks for release candidate" | Only v3.0.0-rc.0 does; v2.0.0-rc.0 says 5 weeks "to end support before Mainnet Nu6 activation"; v6.0.0-rc.0's comment says 37 days while the value is 10 | `end_of_support.rs` at each tag |
| "The NU7 deployment ZIP that would have carried" TZE and ZSA "is Withdrawn" | ZIP 254 is Withdrawn but a replacement NU7 draft exists with TBD height, and it does not list ZIP 222, 226 or 227 | ZIP 254, `draft-arya-deploy-nu7.md` |
| ZIP 271 shielding described as "rationale text, not a MUST" | Spending the coinbase chunks into a shielded pool is a consensus MUST (spec § 7.1.2); only the FROST destination is rationale | 3.2 |
| "16 distinct payout scripts" | 15 transparent payout addresses plus an unattributed bucket of 93 blocks | 3.4 |
| `zec.omft.near` supply "of order 139,000 ZEC" | Kept as a range (139,000 to 140,000 ZEC on 2026-09-17), because the supply moved by about 430 ZEC between two reads | 3.5 |
| Lightwalletd "cannot forge spends but can withhold or delay data" (unsourced) | Replaced by the official wallet threat model wording | 4.4 |
| Regtest address prefixes "as Testnet" (unsourced) and `na`/`ap`/`sa.zec.rocks` "same operator" (not read) | Removed | 2 |

### 7.3 Methodology test on real targets (2026-09-17, second run)

Independent re-derivation with `rederive.py` (kept in the pipeline run folder, not in
this repository; it parses gRPC, transactions and scripts from scratch and does not import
`scripts/` or `scorers.py`). Mainnet tip 3,486,770 at the time of the reads.

| Target and input | Re-derived | Published (`data/scored_targets_2026-09-17.md`) | Agree? |
|---|---|---|---|
| `t3ev37...` spends since 3,146,400 | 2 spends (3,227,947 and 3,308,125), both `OP_2 <0248ca6a21, 027f05a867, 030b7820b7> OP_3 OP_CHECKMULTISIG`, no suffix, identical on `zec.rocks` and `zcash.mysideoftheweb.com`, 4 transactions scanned | 2-of-3, same keys | yes |
| `t3ev37...` balance | 7,818,340,930,000 zatoshi on three operators (`zec.rocks`, `zcash.mysideoftheweb.com`, `na.zec.rocks`) | 78,183.4093 ZEC | yes |
| `t3ev37...` scores by hand from 4.6 | adminKey 50, multisig `max(16, min(100, 40 - 1))` = 39, timelock 0, composite `floor(20 + 11.7 + 0 + 0.5)` = 32, crossExposure 100, capped `min(32, 34)` = 32 | 50 / 39 / 0 / 100 / 100 / 32 / 32 | yes |
| ZCG `t3cFfPt1...` (control, different window 3,476,771-3,486,770) | 8 spends, 2-of-3 `OP_CHECKMULTISIGVERIFY` with suffix `04f3bc7045 75 74 00 87` (nonce, `OP_DROP`, `OP_DEPTH OP_0 OP_EQUAL`), keys `0352d50656, 02f39d0b69, 027072ba23`, disjoint from `t3ev37...`; identical on two operators | 2-of-3, same keys | yes |
| `L1` concentration, published window 3,483,700-3,485,699 | 15 payers, 93 unattributed, top 3 59.1%, `k50` 3, `k25` 1 | same | yes |
| `L1` concentration, fresh window 3,484,771-3,486,770 | 15 payers, 102 unattributed (5.1%), top 3 59.3%, `k50` 3, `k25` 1 on all blocks and on attributed blocks only; identical on two operators | not published | same inputs, multisig 50 |
| `L1` lineage | 12 reads of `eu.zec.rocks`: 5 `/Zakura:1.3.1/`, 7 `/Zebra:6.3.0/`; Zakura README still says "forked from Zebra" | 1 independent lineage, adminKey 20 | yes |
| `L1` synthetic key | `keccak256("zcash:mainnet:l1")` last 20 bytes = `0xB8e62E6AeB4C400b6F3e66cAb69ACe55439035c3` (`cast keccak`) | same | yes |

Gaps found by the test, all fixed in this section's run:

| Gap | Fix |
|---|---|
| 4.2 said an unspent P2SH scores 0 while `scorers.py` returned 20/20, and 20/20 ranked an unknown script above a known 1-of-3 | Single unresolved-P2SH rule in 4.2 (floor 5/16), implemented in `score_fund()` |
| `scorers.py` accepted any bytes after `OP_CHECKMULTISIG(VERIFY)` as a valid m-of-n | Recognised-shape rule in 4.2, enforced by `_suffix_is_constraint_only()`; both live funds still pass |
| The `L1` concentration window was frozen at 3,483,700-3,485,699 and read from one operator, while 4.2 says "recent blocks" and 3.4 claims two-operator agreement | Tip-relative window, computed on both operators, degraded on any disagreement |
| Double counting: 4.4 recorded the 3.4 concentration under `oracleAuthorityScore` although 4.2/4.6 score it in `multisigScore`, and the lightwalletd backend lineage in 4.4 is the input of 4.1's `adminKeyScore` | Each measurement is scored in one dimension only; 4.4 now discloses without scoring |
| ZIP 0 was paraphrased inside quotation marks (a single "by consensus" quote covering three rules, the "add" rule missing "with their consent", "There are always at least two..." quoted without "The current design of the ZIP Process dictates") and 4.5 turned that statement into "must always" | Exact sentences quoted in 3.1 and 4.5, cross-checked on `zip-0000.rst` and the rendered page |

Sensitivity of the address-versus-entity bound (not scored). Coinbase input text of every
10th block of the fresh window (200 blocks, `GetTransaction`): each tagged pool maps to a
single payout address in the sample ("Mined by Luxor", "Foundry Zcash Pool", "2miners",
"KuPool"), and the second payer's tags name individual miners ("Mined by <name>"), so no
tagged pool was seen splitting across addresses. The top payer (29.6%) and the fifth
(7.7%) carry no text. If those two untagged addresses were one entity, `k50` would be 2 and
`multisigScore` 35 instead of 50 (`L1` composite 29 instead of 34). No primary source links
them, so the published value stays 50 with the upper-bound disclosure.

## 8. Open questions for the methodology phase

- Measure node lineage shares from a reproducible P2P crawl; a one-off handshake
  survey gave unstable results and is not used.
- ~~Find a primary source naming the key holders of the ZCG address `t3cFfPt1...`.~~
  **Resolved (partially) 2026-09-19**: the ADMINISTERING ENTITY is named and
  documented in primary sources -- the Financial Privacy Foundation (FPF), a
  Cayman Islands-incorporated nonprofit, per [ZIP 1015](https://zips.z.cash/zip-1015)
  ("Financial Privacy Foundation... refers to the Cayman Islands-incorporated
  non-profit foundation company") and [ZIP 1016](https://zips.z.cash/zip-1016)
  (line 130 of `zip-1016.md`: obligations relating to the previous `FS_FPF_ZCG`
  stream continue for Zcash Community Grants), and FPF's own public quarterly
  reports (financialprivacyfoundation.org/post/fpf-q2-2026-report, released
  2026-07-08, which confirms FPF "receives and manages these funds" and lists
  real Q2 2026 ZCG financials). The SPECIFIC individual or sub-entity holders of
  the 2-of-3 on-chain keys at `t3cFfPt1...` itself are NOT named in any primary
  source found this pass (checked: ZIP 1015, ZIP 1016, zcashcommunitygrants.org,
  FPF's Q4 2025/Q1 2026/Q2 2026 reports, forum.zcashcommunity.com) -- a real,
  disclosed gap, not silently dropped. This must not be confused with ZIP 271's
  explicitly named Key-Holder Organizations (Zcash Foundation, Electric Coin
  Company, Shielded Labs) for the DIFFERENT `t3ev37...` fund: ZIP 271's own text
  scopes that naming to its own one-time lockbox disbursement only, a distinction
  at least one secondary/AI-generated search summary conflated during this
  research pass (caught by checking ZIP 271's raw source directly rather than
  trusting the summary). Integrated into `scorers.py`'s `FUND_STATIC_NOTES`.
- ~~Check whether any coinholder vote under ZIP 1016 has been held, from a primary source,
  before interpreting the low outflow of `t3ev37...`.~~
  **Resolved 2026-09-19**: yes, real coinholder votes under ZIP 1016 have occurred,
  more than once. The "Coinholder-Directed Retroactive Grants Program"
  (forum.zcashcommunity.com/t/nu6-1-coinholder-directed-retroactive-grants-program/51713,
  dated July 2025) explicitly operationalizes ZIP 1016 ("Under this model, ZIP
  1016 states: 12% of block rewards will flow to the Coinholder Grants Program
  from November 2025 until Zcash's third halving"). An inaugural vote closed
  2025-11-26 (9 proposals, 5 approved, more than 1,000,000 ZEC voted on most
  questions per the results thread -- comfortably over ZIP 1016's 420,000 ZEC
  threshold), a Q4 2025 disbursement round and a Q1 2026 round also completed,
  and a Q2 2026 round was explicitly postponed to Q3 2026 "due to ongoing work
  on the Ironwood upgrade" (FPF's own Q2 2026 report,
  financialprivacyfoundation.org, released 2026-07-08). The low transparent
  outflow from `t3ev37...` (3.2) should therefore be read as consistent with
  this fund's own shielded-disbursement design, not as evidence the coinholder-
  vote governance mechanism itself is untested or unused. Integrated into
  `scorers.py`'s `FUND_STATIC_NOTES`.
- ~~Decide the native oracle form without contracts (for example signed score attestations
  in transparent `OP_RETURN` outputs on Testnet first). Obtaining Testnet funds must not
  rely on a CAPTCHA faucet.~~ **Resolved 2026-09-19**: adopted an off-chain
  signed attestation with an on-chain hash-commitment anchor (a compact,
  fixed-size `OP_RETURN` output regardless of attestation size), evaluated
  against a full-payload-in-`OP_RETURN` design and a shielded-memo design and
  chosen over both -- see section 9 for the full design writeup, and
  [`data/testnet_oracle_poc_2026-09-19.md`](data/testnet_oracle_poc_2026-09-19.md)
  for a REAL, live, third-party-verified Testnet proof of concept: a genuine
  free, CAPTCHA-free, login-free Testnet faucet was found and used
  (`zcashfaucet.jinolabs.xyz`, proof-of-work gated), and a real transaction
  publishing this project's own already-computed Zcash L1 score is confirmed
  on Zcash Testnet at block 4,366,645, txid
  `f0780a099f381d2a79fa4b6cab6d657293a5d307e30a7adde5ad95f7d4d575e5`.
- ~~Identify the NEAR contract that controls `zec.omft.near` minting and its signer set.~~
  **Resolved 2026-09-17**: `omft.near` (source: `github.com/near/intents`,
  `contracts/poa/factory/src/contract.rs`), a `near_plugins` access-control-gated
  factory. Minting is gated by `Role::TokenDepositer`, held by a bare single-key
  NEAR account and a Sputnik DAO whose relevant voting group is a 1-of-3
  threshold -- see `scorers.py`'s `score_ext_zec_omft()` and
  `data/scored_targets_2026-09-17.md` for the full live-verified derivation.
- Decide how to score an emergency path whose release was distributed privately to
  miners before activation (`zcashd` v6.12.4).
- ~~Unspent P2SH rule, double counting of miner concentration, exact ZIP 0 citation.~~
  **Resolved 2026-09-17 (second run)**, see 4.2, 4.4, 3.1 and 7.3.
- Link untagged coinbase payout addresses to entities from a primary source (pool
  documentation or signed pool statements) before tightening the `k50` upper bound.
- ~~Define where a native-Zcash-value/off-Zcash-TSS-authority target (Maya Protocol's
  Asgard vaults) fits in the target-type table; confirm its real TSS signing
  threshold from a primary source instead of assuming the THORChain-fork
  convention.~~ **Resolved 2026-09-18**: new `XVAULT` type, 3.6/4.7,
  `score_maya_asgard_vault()`. Threshold formula cited to Mayanode's own bifrost
  go-tss source, not assumed.
- Reconcile the three disagreeing Maya Protocol ZEC figures (live on-chain sum,
  Mayachain pool ledger, DefiLlama TVL) and confirm whether vault B's queued
  `/mayachain/queue/outbound` entry is the actual cause of its ~22.06 ZEC
  ledger-vs-on-chain gap -- both re-verified live 2026-09-18 (3.6) but still not
  chased to a conclusion; a second independent Mayachain full-node API to
  cross-check against was sought and not found.
- ~~Determine `zenZEC`'s real custody Zcash address(es) and dMPC signer threshold from
  a primary source once Zenrock's docs/API are reachable again, and make the
  target-type decision its per-deposit custody model needs.~~ **Resolved (partially)
  2026-09-19**: docs/API still down on re-check (same HTTP 402/503) -- resolved via
  hand-built ABCI queries against zrchain's own Tendermint RPC instead. New
  `MPCKEYRING` type, 3.7/4.8, `score_zenzec_mpc_keyring()`: the keyring's live
  3-of-3 party threshold IS determined from a primary source. The literal Zcash-side
  bulk custody address(es) are NOT (per-deposit ephemeral keys, not enumerable from
  public config) -- this remains open, and is disclosed as still open, not silently
  dropped. Also open: whether `x/policy` adds constraints beyond the raw threshold,
  and whether the keyring's 3 party identities map to distinct physical operators.
- Find a second, independent zrchain full-node RPC to cross-check
  `rpc.diamond.zenrocklabs.io` against (`rpc.zenrock.nodestake.org` refused every
  connection 2026-09-19) -- every `MPCKEYRING` read currently relies on one source,
  unlike every other live read in this project.

## 9. On-chain publication mechanism (native oracle form, added 2026-09-19)

Every other ecosystem this project scores has a real `AuthorityRiskOracle.sol`
to push scores to (`scripts/update_scores.py`). Zcash has no contract VM (section
1), so "deploy the oracle" does not translate -- this is why Zcash has been in
`scoring_build` rather than `deploy_testnet` since day one (until maker-checker action moved it on
2026-09-20; for Zcash, `deploy_testnet` means publishing the commitment on Testnet, see 9.6 and 9.7), and this section is
what closes that gap conceptually, not by forcing a contract-shaped analogy onto
a chain that structurally cannot have one.

### 9.1 Designs considered

| Design | Verdict |
|---|---|
| Full attestation embedded directly in a transparent `OP_RETURN` output | Rejected as the sole mechanism. Standard `OP_RETURN` relay policy keeps payloads small; a full JSON record with a signature does not fit without either truncating fields or relying on non-standard, possibly-unrelayed transactions. Also sits against Zcash's own current direction: every currently-live public Testnet faucet found this pass defaults to shielded payouts specifically to avoid linking a claim to a transparent address (section 9.2) -- a design that requires a NEW transparent output for every future score update runs against that grain, not with it. |
| Shielded memo carrying the attestation (or its hash) | Rejected, not on policy grounds but on capability: any transaction with a shielded component (a Sapling/Orchard spend or output) requires zk-SNARK proof generation. This project has no Zcash proving stack and building one (adopting `librustzcash`/`orchard` or reimplementing Halo2/Groth16 from scratch) is far outside this task's scope. A purely transparent transaction needs only ECDSA (secp256k1) and BLAKE2b -- both implementable in plain Python and independently checkable, which is what made a real Testnet proof of concept possible at all this pass (section 9.3). |
| **Off-chain signed attestation, on-chain hash-commitment anchor (adopted)** | The full attestation -- target, all five sub-scores, `methodologyHash`/`methodologyVersion` (mirroring the on-chain fields the EVM contract already carries per METHODOLOGY.md's top-level "Data collection discipline"), a timestamp, and an ECDSA signature by the oracle's own publishing key -- is published as an ordinary file in this repository. Only a compact commitment goes on-chain: a 4-byte magic tag (`"ARO1"`) plus a 32-byte BLAKE2b-256 hash of the attestation, 36 bytes total, in a transparent `OP_RETURN` output. This is the same hash-anchor pattern OpenTimestamps and similar systems use for proof-of-existence on Bitcoin-family chains, applied here to an authority score. It stays comfortably inside any OP_RETURN size policy regardless of how large a future attestation format grows (the commitment is always a fixed-size hash), needs no shielded proving, and gives any verifier a simple three-step check: read the OP_RETURN via any lightwalletd operator, fetch the attestation file, hash it and compare, then verify the signature against the publisher's own published pubkey. |

### 9.2 Why "shielded-first" made this harder than it looks

A `t`-address-funded transparent transaction sounds like the easy case, but
every currently-live public Zcash Testnet faucet found this pass (`zcashfaucet.jinolabs.xyz`,
`fauzec.com`) defaults to paying shielded addresses specifically so "nothing on
chain ties the drip to you" -- a deliberate privacy choice, not an oversight.
Older transparent-paying faucets (`faucet.zecpages.com`, `faucet.testnet.z.cash`)
are dead (checked live 2026-09-19: connection refused/timed out). The task's own
constraint against a CAPTCHA/login-gated faucet ruled out `fauzec.com` (a
Cloudflare bot-check gate) entirely. `zcashfaucet.jinolabs.xyz` was the one path
that is simultaneously free, CAPTCHA-free, login-free, AND -- confirmed live,
not assumed -- willing to pay a transparent address on request, labeling it
correctly rather than silently rejecting it. See
[`data/testnet_oracle_poc_2026-09-19.md`](data/testnet_oracle_poc_2026-09-19.md)
section 2 for the exact verification steps.

### 9.3 Real proof of concept, not a paper design

The mechanism above was not just designed: it was built and used for real on
Zcash Testnet on 2026-09-19, publishing this project's own already-computed
Zcash L1 score (`compositeScore` 34, from `data/scored_targets_2026-09-19.md`)
in a real, confirmed transaction (block 4,366,645, txid
`f0780a099f381d2a79fa4b6cab6d657293a5d307e30a7adde5ad95f7d4d575e5`), built with
new from-scratch code (`scripts/secp256k1.py`, `scripts/zcash_tx.py`,
`scripts/publish_attestation.py`) implementing Zcash's post-NU5 transaction
format and ZIP-244/229 digest algorithm without any third-party Zcash wallet
library. Three real, disclosed mistakes were caught before or by the network
itself during this process (a transcription bug in a hardcoded curve constant;
a wrong `prevout` reference from assuming legacy double-SHA256 txids on a v6
transaction; an underpaid ZIP-317 fee) -- none reached a false claim of
success. Full trail, every verification step, and exactly what this does and
does not prove: [`data/testnet_oracle_poc_2026-09-19.md`](data/testnet_oracle_poc_2026-09-19.md).
Regression tests grounded in the real broadcast transaction:
`scripts/lib/tests/test_zcash_tx.py` (top-level repo path).

### 9.4 What is deliberately NOT done here

No automation exists yet to turn a `scorers.py` re-run into a new attestation
and a new `OP_RETURN` transaction on a schedule, the way `scripts/update_scores.py`
does for the EVM ecosystems' on-chain contract pushes -- this section resolves
the DESIGN and demonstrates it with a real Testnet transaction, not a
production publishing pipeline. Building that pipeline, and any decision about
whether/when to do the equivalent on Zcash MAINNET with a real key, are
separate, later decisions, explicitly out of scope for this pass and not
attempted.

### 9.5 Batch attestation of the whole `score_all()` output (added 2026-09-19, later run)

Closes the first half of 9.4 (the automation step), still WITHOUT broadcasting
anything. `scripts/attest_scores.py` turns a `score_all()` run into one
deterministic 32-byte commitment covering every scored target, instead of one
hand-copied score per transaction:

| Step | Rule |
|---|---|
| Canonical record | `target` + the five sub-scores + `compositeScore` + `l1CappedComposite` (JSON `null` where it does not apply). Integers in [0,100] only, anything else is refused. `label` and `notes` are excluded on purpose: notes carry live balances and sample windows that move between runs, so hashing them would change the commitment with no score change. |
| Leaf | BLAKE2b-256, personalization `AROzecLeaf___v1_`, over the record's canonical JSON (sorted keys, no whitespace). |
| Merkle root | Leaves sorted by `target`, paired with `AROzecNode___v1_`. An odd node is promoted, never duplicated (so `[a,b,c]` and `[a,b,c,c]` cannot share a root). Every record ships with its inclusion proof. |
| Commitment | BLAKE2b-256 (`AROzecBatch__v1_`) over `{format, ecosystem, methodologyHashSha256, merkleRoot, targetCount}`. No timestamp inside: the commitment depends only on (scores, methodology), so an unchanged re-run re-derives the same value and nothing needs republishing. The publication time is the block's own time. |
| On-chain payload | `OP_RETURN` = `"ARO2"` + commitment, 36 bytes (same size as the `"ARO1"` proof of concept). |
| Transaction | `plan-tx` builds and signs (RFC 6979) a transparent v6 Testnet tx spending the publisher's one live UTXO (`f0780a09...d575e5:1`, 9,980,000 zat, unspent on 2026-09-19 per `testnet.zec.rocks` and `api.testnet.cipherscan.app`). The fee is the ZIP-317 conventional fee computed from the real serialized sizes (15,000 zat for this shape, which fits both network verdicts on the ARO1 tx: 10,000 rejected, 20,000 accepted). The module has no send path at all. |

First batch: [`data/attestation_batch_2026-09-19.json`](data/attestation_batch_2026-09-19.json),
7 targets, the same values as `data/scored_targets_2026-09-19.md` (re-derived from a
fresh live `score_all()` run on 2026-09-19, no drift). Tests:
`scripts/lib/tests/test_zcash_attest_scores.py`. They include a byte-for-byte rebuild of the
real, confirmed ARO1 transaction through the new builder, as a regression anchor.

Still open: (1) broadcasting the ARO2 transaction (deploy_testnet phase:
rebuild with a fresh `--expiry-height`, then `zcash_tx.send_transaction`), (2) no
lightwalletd exposes a dry-run mempool check, so the 15,000 zat fee has only been
checked against the formula and the two real verdicts, not submitted, (3) the
batch is not yet signed off-chain the way ARO1's attestation was. The on-chain anchor
from the publisher address serves as authentication. A separate signature is
optional future work.

**Update, same day (see 9.6):** items (1) and (2) are closed (the ARO2 transaction was
broadcast and accepted at the 15,000 zat conventional fee) and item (3) is closed
(the batch is now signed off-chain). The "optional" wording on the separate signature
is superseded by `data/publisher_key_exposure_2026-09-19.md` and by 9.6.

### 9.6 ARO2 broadcast: the whole `score_all()` set anchored on Testnet (added 2026-09-19, later run)

Every one of the 7 targets `score_all()` returns is now covered by ONE real Zcash
Testnet transaction, using the 9.5 format unchanged (no second, competing "v2"
format was invented: 9.5's is the v2 of the mechanism, ARO1 of 9.1-9.3 is the v1).

| | ARO1 (9.1-9.3) | ARO2 (9.5-9.6) |
|---|---|---|
| Scope | one score (Zcash L1, composite 34) | 7 targets: every row of `score_all()` |
| On-chain payload | `"ARO1"` + BLAKE2b-256 (`AuthRiskOracle_1`) of one attestation JSON | `"ARO2"` + BLAKE2b-256 (`AROzecBatch__v1_`) of the batch header (Merkle root, target count, methodology hash) |
| Canonical form | sorted-key JSON of the whole attestation, timestamp inside | per record: sorted-key, no-whitespace JSON of target + 5 sub-scores + composite + `l1CappedComposite` (`null` if n/a), hashed as a leaf; leaves sorted by target; odd node promoted; no timestamp inside |
| Timestamp | `publishedAtUtc` inside the hash | the block's own time (`anchor.blockTimeUtc`); `publishedAtUtc` in the file is informational and not committed |
| Signature | ECDSA over the commit hash | ECDSA over the 32 raw commitment bytes (RFC 6979, low-S, DER), same publisher key |
| Per-target proof | none (one target) | log2(n) inclusion proof per record, in the file |

Real transaction (Testnet only): txid
`18791a4cdaa00b5d0aefc1dcce5576c6e43ea9e203db03b0d973772dfe32cc37`, block 4,368,539
(2026-09-19T21:17:12Z), OP_RETURN `41524f32` + commitment
`74f6ba041e253bb75e523e1b0d00422e44221c7a0240757cd1a40ad15d513662`, 7 targets, fee
15,000 zat (ZIP-317 conventional fee for this shape, accepted at the first attempt),
9,965,000 zat left at `tmDvDRYD7meGJXFoeTqtjFcrNF5378ZzaBo`. The attestation file is
`data/testnet_attestation_v2_2026-09-19.json` (records, inclusion proofs, signature,
anchor record with the raw transaction); the run record with every preflight and
independent read is `data/testnet_oracle_batch_2026-09-19.md`. The transaction was
built and sent by `scripts/publish_batch.py`, which re-derives the commitment from a
fresh live `score_all()` immediately before signing and aborts on any drift. The
ARO1 file and transaction are untouched. Unit tests pinned to the real transaction
bytes: `scripts/lib/tests/test_zcash_batch_anchor.py`. The dashboard's Zcash tab
verifies both the ARO2 set and the ARO1 attestation live in the browser.

`header.methodologyHashSha256` pins METHODOLOGY.md as committed in
`783326342d5bbc05c07cd43f649e8878a78353d6`. This section was written after the
broadcast, so the CURRENT file hashes differently: verify the pin with
`git show 783326342d5bbc05c07cd43f649e8878a78353d6:chains/zcash/METHODOLOGY.md | sha256sum`.

**What this proves.** Integrity and timestamping of a SET of scores: the seven
records (and the methodology hash they were computed under) were fixed no later than
block 4,368,539, and none of them can be altered, dropped or added afterwards without
the commitment changing; any single target can be proven against the anchored root
with its inclusion proof. Immediately before signing, a fresh live run of
`score_all()` gave exactly these numbers. The transaction spends from the publisher
address and a valid ECDSA signature by that key over the commitment exists.

**What this does NOT prove.**
- **That the scores are true.** They are this project's own scorer output from
  public reads. A wrong score would be anchored exactly as faithfully as a right one;
  the anchor freezes and dates a claim, it does not audit it.
- **Who published.** The key's private half was committed in clear in `40ca1a4` and
  stays readable in the private repo's history. Spap's recorded decision (2026-09-19,
  in the out-of-repo key file's `send_guard_lifted`, not seen in chat by the session
  that ran this) accepted that risk for this key: a signature or a spend by it proves
  "someone with access to that history", not a specific publisher. Rotating the key or
  adding a signature by an unexposed key remains the stronger fix
  (`data/publisher_key_exposure_2026-09-19.md`). **Update 2026-09-20: the key was
  rotated and the same set re-anchored from the new key, see 9.7.**
- **Anything about later scores.** The set is a snapshot; scores and the two active Maya
  vaults move, and nothing republishes automatically.
- **That the signature is checked on chain.** Transparent scripts cannot verify it; only
  the hash is on chain, the signature is verified off chain by anyone with the file.
- **A phase change.** Zcash's own phase in its docs is not advanced by this run (a phase
  transition is a maker-checker decision, AGENTS.md). Nothing on Zcash Mainnet was
  written, and nothing on Zcash consumes this commitment.

### 9.7 Publisher key rotation and ARO2 re-anchor (added 2026-09-20 Europe/Paris; both transactions are 2026-09-19 UTC)

The 9.6 anchor was made by a key whose private half sits in this repository's git
history (`40ca1a4`). It was rotated with two real Testnet transactions, no faucet
involved (Spap's instruction: rotate if it can be done without manual funding, and
the exposed key's send guard is lifted for this one key only):

| Step | txid | Block (UTC) | What |
|---|---|---|---|
| Sweep | `d2b5a31914bc66168f3f0ea8db2fd61ffffeb81fbcec4a2ea2f62de3d19d8074` | 4,368,630 (2026-09-19T23:08:08Z) | Signed by the exposed key. Its whole remaining balance, the 9,965,000 zat change output of the first ARO2 transaction, goes in one output of 9,955,000 zat to `tmCj66nwJY8xgNj3jwEyUMhLGmZzbHYiHY8` (fee 10,000 zat, the ZIP-317 conventional fee for 1 input and 1 output). The old address is left at 0 zat (lightwalletd and cipherscan). |
| Re-anchor | `eeaa894c3c46814f7228a7ecf2be84c0006c1154b5101688dd413d9a419689c0` | 4,368,633 (2026-09-19T23:15:28Z) | Spends the sweep output, signed by the new key. OP_RETURN `41524f32` + `74f6ba041e253bb75e523e1b0d00422e44221c7a0240757cd1a40ad15d513662`, byte for byte the payload of the first ARO2 transaction. Fee 15,000 zat, 9,940,000 zat left at the new address. |

The new key is a fresh `os.urandom` key kept only in the out-of-repo `keys/zcash-testnet.json`
(chmod 600); it was never written to a tracked file, a commit or a log. The old key
file was renamed and re-marked `exposed_in_git_history: true`, so every `send` path
refuses it again. Just before signing, `publish_batch.py` re-derived the commitment
from a fresh live `score_all()` run and it matched (7 targets), so no score was
re-anchored stale. The published record is
`data/testnet_attestation_v2_reanchor_2026-09-20.json` (same header, records and
methodology pin as the first ARO2 file, a new signature and anchor block, plus
`reanchorsTxid` pointing at the first anchor). The signature is over the 32 commitment bytes
used directly as the ECDSA message digest, with no SHA-256 or other hashing on top: a verifier
that hashes first will not validate it. Unit tests pinned to the raw bytes of
both transactions: `scripts/lib/tests/test_zcash_key_rotation.py`. The dashboard's
Zcash tab verifies all the publications live (three when this section was written, four since 9.8).

**What this changes.** For this set of 7 scores there is now an ARO2 anchor whose
publisher key was never in the repository: the transaction spends from an address
only the key file's holder controls, and the commitment is signed by that key
(verifies against the new public key, not the old one). Read the provenance caveat
below together with this: the chain alone cannot show that only the maintainer holds it.

**What this does NOT change.**
- The ARO1 transaction (`f0780a09...`) and the first ARO2 transaction (`18791a4c...`)
  were made by the exposed key and stay as historic records: they prove integrity and
  timing only, not who published. They are not withdrawn, and the dashboard labels them.
- The old private key is still readable in this repository's git history (history is
  not rewritten). Spap's stated plan is that this is a test repository and a new one is
  created when the time comes (2026-09-20, chat), which would not carry that history.
- "Who published" still means "whoever holds the key file", not a named legal identity,
  and the new key's secrecy rests on one file on one machine. That is proportionate for a
  zero-value Testnet key and would not be for a Mainnet one.
- The new address was funded only by the sweep from the exposed address. On the chain alone that
  cannot tell the maintainer from anyone who had read the old key in this repository's history: the
  same sweep and re-anchor could have been made by them. What the third anchor adds is that its
  key was never in the repository, a property of the repository's history and of the key file, not
  something the chain proves.
- The sweep was built by a one-off script that is not committed (it would be a signing path for
  an exposed key). Its result is committed as raw transaction bytes, verifiable by anyone.
- The send guard is active again: on 2026-09-20 Spap asked to reactivate the guard lifted on
  2026-09-19. `publisher_key.load()` now refuses the legacy exposed key by identity (whatever the key
  file's flag says), `send` in `publish_batch.py` and `publish_attestation.py` also refuses any key flagged
  exposed, and plan modes only warn. The guard protects this project's scripts, not the key: anyone who
  reads it in git history can sign elsewhere. The sweep, the first ARO2 and ARO1 were signed by that key
  before the guard was re-armed (the first ARO2 about 17 hours after the exposure, under the lifted
  guard). Details: `data/publisher_key_exposure_2026-09-19.md`.
- One of the 7 anchored targets, the Zenrock zenZEC keyring (composite 44), is a dated single-source
  snapshot: the only reachable zrchain node (`rpc.diamond.zenrocklabs.io`) reports its last block at height
  9,534,552 / 2026-08-10T23:19:52Z with no peers (see 4.8 and `scorers.py`, "SINGLE SOURCE, DATED"). A live
  `score_all()` re-derivation therefore matches that target vacuously, and no maker-checker approval covers
  it; the other 6 targets are corroborated by live reads. The anchor freezes and dates what the project
  computed; it does not validate that target.
- Nothing republishes automatically. (This rotation itself changed no phase; the move to `deploy_testnet` came later
  through maker-checker action, 2026-09-20, which does not authorize automatic broadcasts: Zcash anchors stay manual.)

### 9.8 ARO2 over the six live targets (added 2026-09-20, after the retirement of target 7)

Once maker-checker #138 retired the Zenrock zenZEC keyring from the live set (4.8.1), a fresh `score_all()` returns six
targets, and that set was committed and anchored the same evening, with the same construction as 9.5 to 9.7
(`attest_scores.py snapshot`, then `bundle`, then `publish_batch.py plan` and `send`; the send re-derived the commitment
from a fresh live `score_all()` first: MATCH, 6 targets).

| | |
|---|---|
| Transaction | `462de12bf72e5e635a1feed4a4cedb02c03f17745bd15176787f8f5f8fcd701c`, Zcash Testnet |
| Block | 4,371,248, 2026-09-20T19:23:45Z |
| Commitment | `214f8105de87576532d84c10e86478c6228bb54a7e426dfb4c349f7dcaeb24ca` (OP_RETURN `ARO2` + commitment, 36 bytes) |
| Merkle root | `fa8d11f841ba14a8f15ffc8e114e1e296306f06faf9270756b9daedfc07b1d7b`, 6 leaves |
| Publisher | `tmCj66nwJY8xgNj3jwEyUMhLGmZzbHYiHY8`, the rotated key of 9.7 (never committed), signature over the commitment in the file |
| Spent and change | spent `eeaa894c...:1` (9,940,000 zat, the change of the 9.7 re-anchor), fee 15,000 zat (ZIP-317 conventional), change 9,925,000 zat to the same address, now the default UTXO |
| Methodology pin | SHA-256 of this file as committed at `0ae4f94e0dfc16fb52e1e3f6c2f3bd8ee29217ea` (the retirement commit), `0c8e585cb713e363d9b7375cb654947ddcd6c4582ce9b57521d41df8fa3d0b13`; the file was edited afterwards, as in 9.6 and 9.7 |
| Files | `data/attestation_batch_2026-09-20_six_live.json` (the bundle), `data/testnet_attestation_v2_six_live_2026-09-20.json` (the published record) |

What it changes: nothing before it. The three earlier anchors are immutable and still verify; the two ARO2 ones still contain
target 7, whose record as anchored is in `data/legacy_snapshot_zenzec_keyring_2026-09-20.json`. What it proves is what 9.6
says of any ARO2 anchor: integrity and timing of a set of scores this project computed, not that they are true and not
who computed them beyond the publisher key. Reproduce with `python3 attest_scores.py verify ../data/testnet_attestation_v2_six_live_2026-09-20.json --live`
(re-derives the commitment from a fresh live run: MATCH, VERIFY PASS) and the Zcash tab of `dashboard/index.html`, which
fetches the transaction and recomputes the commitment in the browser. The six composites are those of the six live rows of the
9.7 re-anchor, unchanged.

Corrected after the broadcast, disclosed here: `publish_batch.py` writes the first ARO2 anchor's commit (`7833263...`) into the record's
informational field `methodologyPinnedAt.gitCommit` by a hard-coded default, which is wrong for this bundle, whose pin is the hash of this
file at `0ae4f94...` (checked by hashing it). The field was corrected in the published record; it is not part of the commitment or of the
signature, both unchanged. A unit test now checks every published ARO2 record against `git show <commit>:chains/zcash/METHODOLOGY.md`
(skipped in a clone that lacks the commit). The hard-coded default in the tool itself is not fixed yet: the next anchor will need the same
correction, and that test will fail until it is made.
