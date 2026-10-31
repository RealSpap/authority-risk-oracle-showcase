# What your browser contacts

*Written on 30 October 2026, from `dashboard/index.html` of this repository. The page served on the site is built from code that is not in this repository, and can differ from this file: it can keep settings in your browser and, if you turn on its notify-me option, polls `latest.json`. This page describes the file in the repository; for the online page, check what it contacts with your browser's network tab.*

The dashboard has no server of ours behind it: it is a static page. The file in the repository sets no cookie, keeps nothing in `localStorage` or `sessionStorage`, and contains no analytics code. It does send requests to other parties, because it reads the chains from your browser:

| When | Who receives the request | What they can see |
|---|---|---|
| The page loads | `fonts.googleapis.com` (a stylesheet of two typefaces), and the font files that stylesheet loads | your IP address and browser details, as for any web request |
| Page load, then 1.2 s later | the public RPC endpoint of the chain shown, and 1.2 seconds after load, without any click, of every other chain except Zcash (the page reads the number of tracked targets there): `rpc.testnet.chain.robinhood.com`, `ethereum-sepolia-rpc.publicnode.com`, `sepolia-rollup.arbitrum.io`, `sepolia.base.org`, `testnet-rpc.plasma.to`, `rpc.moderato.tempo.xyz`, `testnet-rpc.monad.xyz`, `rpc.hyperliquid-testnet.xyz`, `api.devnet.solana.com` | your IP address and the contract addresses read (`getScore`, `trackedTargets`) |
| The Zcash tab is opened | `r.jina.ai`, a public reader service used as a passthrough, which fetches for your browser the Zcash testnet transactions from `api.testnet.cipherscan.app` (that API refuses direct browser requests) | your IP address and the transaction ids requested. The dashboard recomputes the commitment from what comes back, so an answer that was changed on the way fails the check; the service still sees which transactions you asked for |
| You follow a link | the site you click (explorers, GitHub) | what any link click shows |

The files of the attestations are fetched from the same origin as the page.

**The pages under `/oracle/` and the Watch files** are served by GitHub (GitHub Pages and `raw.githubusercontent.com`), which receives your request like any host does. This project runs no server and receives none of them.

**The scripts** that check the work (`scripts/audit_public.py`, `scripts/prove.py`) run on your machine and contact the public RPC endpoints, `raw.githubusercontent.com` and `realspap.github.io`; `scripts/mcp_server.py` reads a folder; the installable package fetches the Watch files from `raw.githubusercontent.com`, then `cdn.jsdelivr.net`, unless it is given a folder (`--data-dir`). Nothing is sent to this project.

**What is not claimed.** This page does not describe the privacy practice of any of the parties above. If a third party seeing your IP address and your reads matters to you, do not open the Zcash tab (the RPC reads happen on load for all the other chains), or replace the RPC addresses in the scripts by your own endpoint.
