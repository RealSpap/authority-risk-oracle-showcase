# Tempo: bridged TIP-20 token scouting, 2026-09-19 (closes METHODOLOGY.md section 7, open point 2)

Phase: `maintenance` (real deploy already done 2026-09-19, see `../deploy/README.md`). Read-only
Tempo mainnet (chain id `4217`). No transaction, no key, no write. This is the follow-up to the
open point left in `../METHODOLOGY.md` section 7.2: "other, not-yet-scouted bridged TIP-20
tokens remain open for future scouting."

## 1. Sources (2 independent registries + 2 independent RPC endpoints)

| Source | What it gave | Result |
|---|---|---|
| Official Tempo token list, `https://tokenlist.tempo.xyz/list/4217` | The chain's own registry of every TIP-20 token, version 1.0.34, generated 2026-09-10 | **34 tokens**, symbol/name/address/decimals |
| Tempo mainnet block explorer, `https://explore.tempo.xyz/tokens` (3 pages, read live) | Independent confirmation of the same 34 addresses, plus real holder counts and "created" age (not in the token list) | **34 tokens**, byte-for-byte the same 34 addresses as the token list -- cross-check passed |
| `stablecoins.llama.fi/stablecoins` (DefiLlama) | Circulating-supply cross-check for the USD/EUR/GBP-pegged subset that DefiLlama tracks | Used to sanity-check the RPC reads below (e.g. cUSD: DefiLlama $50,337.23 vs RPC $50,337.23 -- exact match) |
| `eth_call totalSupply()`/`decimals()` on `https://rpc.tempo.xyz` (official) | Live on-chain supply for all 34 tokens | Primary number used below |
| Same calls re-read on `https://tempo-rpc.publicnode.com` (independent) | Cross-check on the largest new candidates (senpathUSDE, GBPA, BRLA) and one already-covered token (cUSD) as a control | Identical (cUSD, GBPA, BRLA byte-for-byte; senpathUSDE +884 units higher a few seconds later, consistent with a live-growing supply, not a data error) |

No token beyond these 34 exists on Tempo mainnet today: the official registry and the
independent block explorer enumerate the identical 34 addresses, so this is treated as the
complete set of TIP-20 tokens deployed on-chain, not a sample.

## 2. Already covered (9 of 34) -- not re-scouted

`USDC.e`, `USDT0`, `pathUSD`, `USDB`, `cbBTC`, `PRIME`, `DLUSD`, `EURC.e`, `cUSD` (the 9 tokens
already in `TOKENS` in `../scripts/methodology_test.py`, live-scored in
`../data/scored_targets_2026-09-18-controller-types.md` and pushed for real 2026-09-19, see
`../deploy/README.md`). The open point's own text (`METHODOLOGY.md` 7.2) undercounted this list
as "USDC.e, USDT0, pathUSD, cUSD" -- it was written 2026-09-17 before the 2026-09-18 pass added
USDB/cbBTC/PRIME/DLUSD/EURC.e; those 5 are correctly excluded here too, not re-scouted as if new.

## 3. The other 25, ranked by on-chain `totalSupply()` (own peg currency, all 6-decimal TIP-20s)

Holders from the explorer, read 2026-09-19. `totalSupply()`/`decimals()` from `rpc.tempo.xyz`,
re-read on `tempo-rpc.publicnode.com` where noted.

| Token | Name | Address | Holders | totalSupply() | Note |
|---|---|---|---|---|---|
| senpathUSDE | Sentora pathUSD (Earn) | `0x20c0...baac91f6ca72f768` | 77 | 116,422.5 USD-denominated | **Not bridged** -- `asset()` (ERC-4626 probe) reverts, this is a plain TIP-20, not a vault contract. Almost certainly a receipt/wrapper token issued by Sentora against pathUSD balances already inside the Sentora pathUSD Morpho Vault V2 (`0x9a044AE0...e957a626`, already scored, rule R8) -- same issuer, same root-authority family as an already-scored target, not an independent bridge. Cross-checked on the independent RPC: +884 units in the few seconds between reads, i.e. genuinely live, not a stale mirror. |
| BRLA | BRLA Token | `0x20c0...f047dd7018e50367` | **5** | 50,100.0 BRL-denominated | 5 holders for a $50k-equivalent mint reads as a treasury/seed balance held by very few wallets, not organic distribution. |
| GBPA | Agant GBP | `0x20c0...0a6da882d075a4c3` | **1** | 50,001.0 GBP-denominated | **1 holder.** The entire supply sits in a single address -- textbook issuer self-mint, not usage. Verified byte-for-byte identical on both RPC endpoints. |
| stcUSD | Staked Cap USD | `0x20c0...8ee4fcff88888888` | 27 | 23,869.6 USD-denominated | Cap Protocol's own staked wrapper of the already-scored `cUSD` (same issuer family, name pattern `st<asset>` mirrors Cap's other staked assets) -- not an independent bridge either. |
| USD1 | USD1 | `0x20c0...111111111e910f0f` | 30 | 1,119.9 USD-denominated | |
| goUSD | goUSD | `0x20c0...6d194f9810e6f886` | 8 | 1,117.0 USD-denominated | |
| syrupUSDC | Syrup USDC | `0x20c0...8191667423f70e67` | 13 | 886.1 USD-denominated | |
| reUSD | Re Protocol reUSD | `0x20c0...383a23bacb546ab9` | 1 | 233.7 USD-denominated | |
| MACH | MACH | `0x20c0...f37de3740adec032` | 26 | 156.2 USD-denominated | |
| CADD | CAD Digital | `0x20c0...d65b4808c85dbb81` | 3 | 99.0 CAD-denominated | |
| SBC | Stable Coin | `0x20c0...ae247a1130450f09` | 11 | 96.3 USD-denominated | |
| EURAU | AllUnity EUR | `0x20c0...9a4a4b17e0dc6651` | 51 | 41.0 EUR-denominated | |
| frxUSD | Frax USD | `0x20c0...3554d28269e0f3c2` | 23 | 44.5 USD-denominated | |
| USDY | Ondo U.S. Dollar Yield | `0x20c0...d479b9f6ec0ceff9` | 12 | 468.9 USD-denominated | |
| USDe | USDe | `0x20c0...2f52d5cc21a3207b` | 8 | 22.3 USD-denominated | |
| wYLDS | Hastra wYLDS | `0x20c0...30fdd4a919e93fcf` | 2 | 5.1 USD-denominated | |
| sUSDe | Staked USDe | `0x20c0...bd95bfb69fbe6ce3` | 6 | 5.6 USD-denominated | |
| YLDS | YLDS | `0x20c0...3337951a5a9d94b2` | 3 | 5.5 USD-denominated | |
| siUSD | InfiniFi Staked USD | `0x20c0...048c8f36df1c9a4a` | 3 | 4.0 USD-denominated | |
| wsrUSD | Wrapped Savings rUSD | `0x20c0...aeed2ec36a54d0e5` | 4 | 3.9 USD-denominated | |
| rUSD | Reservoir Stablecoin | `0x20c0...7f7ba549dd0251b9` | 1 | 0.00001 USD-denominated | |
| iUSD | InfiniFi USD | `0x20c0...ab02d39df30bd17e` | 0 | 0 | |
| CHFAU | AllUnity CHF | `0x20c0...42109aef2f8b28e1` | 0 | 0 | |
| SEKAU | AllUnity SEK | `0x20c0...2e2829d90e7da7fa` | 0 | 0 | |
| GUSD | Generic USD | `0x20c0...5c0bac7cef389a11` | 0 | 0 | |

## 4. Why none of these is added as a new scored target

The comparison bar is the *weakest already-covered independent token*, not the strongest:
`DLUSD` at $3.66M supply / 639 holders, or even `cUSD` at $50,337 supply / **332** holders (the
smallest by value, but the smallest by holders too is `EURC.e` at 21 holders on $1.46M supply --
still a real, broadly-issued Stargate-bridged blue chip). No candidate above clears a comparable
bar on **both** axes at once:

- The two tokens with a comparable dollar figure to `cUSD` (`BRLA` $50,100, `GBPA` $50,001) each
  sit in essentially one wallet (5 and 1 holders) -- a self-mint, not usage a scorer would be
  telling anyone anything new about.
- The one token with more holders than several already-covered tokens (`senpathUSDE`, 77
  holders) is not bridged at all, and is a receipt token of an already-scored Morpho Vault V2
  target -- scoring it would not surface a new authority surface, it would double-count the
  Sentora vault's own root control set under a different address.
- `stcUSD` is the same story one level down: Cap Protocol's own staked wrapper of the
  already-scored `cUSD`, same issuer.
- Every other token (20 of the 25) has under $1,120 of supply, several literally 0, and single-
  digit-to-zero holders -- these read as issuer test/demo mints made against a live mainnet
  token registry, not deployments with real usage to score.

**Conclusion, honestly: nothing new and significant was found.** The open point is closed by
this negative result, not forced onto a weak target. `../scripts/methodology_test.py`'s `TOKENS`
dict and `../scorers.py` are unchanged this pass; nothing new was pushed to Moderato (no
`deploy/push_scores.py` run without `--dry-run`); no key was used.

## 5. Re-check trigger (for whoever picks this open point up again)

Re-scout when the official token list's `version.patch` in `tokenlist.tempo.xyz/list/4217`
increases past `34`, or when a re-run of the `totalSupply()`/holders table above shows one of
the 25 tokens above crossing roughly two orders of magnitude past where it sits today (i.e.
moving from "hundreds of dollars, single-digit holders" into `cUSD`/`DLUSD` territory) -- not on
a fixed calendar cadence, since nothing here suggests a schedule would catch a real change any
better than the next session that touches this ecosystem checking the same 3 sources again.

## Reproducing the reads

```bash
curl -s https://tokenlist.tempo.xyz/list/4217 | python3 -m json.tool   # official registry, 34 tokens
# explore.tempo.xyz/tokens (3 pages) -- rendered page, read via browser tooling, not a JSON API
curl -s -X POST -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"eth_call","params":[{"to":"<TIP-20 address>","data":"0x18160ddd"},"latest"]}' \
  https://rpc.tempo.xyz                                                # totalSupply()
curl -s -X POST -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"eth_call","params":[{"to":"<TIP-20 address>","data":"0x313ce567"},"latest"]}' \
  https://rpc.tempo.xyz                                                # decimals()
curl -s https://stablecoins.llama.fi/stablecoin/<id>                   # DefiLlama cross-check
```
