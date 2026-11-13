#!/usr/bin/env python3
"""Which network each target lives on, and at which block that network was read. Standard library only, no key. Only the Watch calls this file:
no scorer imports it, so the methodology hash does not change (see scripts/lib/methodology.py, scoring_files).

Why: watch/scores/<oracle>.json is a read of the ORACLE contract, which lives on a TEST network (Sepolia, devnet, Moderato). Its `rpc`, `block` and
`reference_block` are those of that test network. The contracts the oracle scores (the targets) live on MAINNET. The file did not say so. This module adds,
by reading and never by a constant alone:

  record : oracle_network, oracle_chain_id (eth_chainId read on the oracle RPC), target_network, target_chain_id (eth_chainId read on the mainnet RPC),
           target_block, target_block_hash, target_block_time (the head of the target network when the Watch read the oracle: NOT the block the scorer read),
           target_block_kind, target_rpc (host only); or target_read_error with the cause.
  target : target_network, target_chain_id, target_network_read (what was read, and where), target_read_block, code_on_target_network (eth_getCode at the pinned block).

A target with no code on the main network of its oracle is looked up where the repository says it lives: Robinhood rollup contracts on Ethereum (the parent chain),
the Hyperliquid bridge on Arbitrum One, Hyperliquid natives on HyperCore (info API, userRole). Anything still not found is written "unplaced", never a default.
A failed read leaves null with its cause: never a zero, never "mainnet" by default: a network name is written only once its chain id (Solana: its genesis) was read and is the expected one, otherwise the name is "unplaced (read impossible)". A chain id read that differs from the expected one refuses that RPC.
Limit: the same code at the same address can exist on several networks (deterministic deployment), so code alone does not prove the network; the network is the one of
the RPC whose chain id was read and whose block is named."""
HELD = "0xe80694d6fec5d676ad4b7d51478559be8cc54f3e"   # Held arbiter (Sandbox Shop): the one target read on a TEST network (chains/tempo/scripts/methodology_test.py, HELD_ARBITER_TARGETS)
HELD_NETWORK = ("Tempo Moderato (testnet)", 42431)
HYPERCORE_API = "https://api.hyperliquid.xyz/info"
# Keys the oracle derives for HyperCore objects that have no account of their own (chains/hyperliquid/METHODOLOGY.md, section 4.7): the last 20 bytes of keccak256 of the string.
# The test recomputes each key from its string. kind: "l1" (the L1 itself) or "dex" (a HIP-3 dex whose deployer address collides with a HyperEVM contract).
DERIVED_KEYS = {"0xea394cd63ca3a5c8a130bb2b955cc71c22e5ea6c": ("hyperliquid:hypercore-l1", "l1", None),
                "0x30e96fbd515243d47703e78581b88cba60f51360": ("hyperliquid:hip3-dex:para", "dex", "para"),
                "0xbf6d3bbce71dbce6f4121bfe2e2cad8c77bbc1fc": ("hyperliquid:hip3-dex:mkts", "dex", "mkts")}
# oracle name (live_target_counts.ORACLES): (oracle network, expected chain id, target network, expected chain id, mainnet RPCs)
TABLE = {
    "Robinhood Chain": ("Robinhood Chain testnet", 46630, "Robinhood Chain mainnet", 4663, ["https://rpc.mainnet.chain.robinhood.com"]),
    "Ethereum L1 (Sepolia)": ("Ethereum Sepolia (testnet)", 11155111, "Ethereum mainnet", 1, ["https://ethereum-rpc.publicnode.com", "https://gateway.tenderly.co/public/mainnet"]),
    "Arbitrum (Sepolia)": ("Arbitrum Sepolia (testnet)", 421614, "Arbitrum One mainnet", 42161, ["https://arb1.arbitrum.io/rpc", "https://arbitrum-one-rpc.publicnode.com"]),
    "Base (Sepolia)": ("Base Sepolia (testnet)", 84532, "Base mainnet", 8453, ["https://base-rpc.publicnode.com", "https://gateway.tenderly.co/public/base"]),
    "Tempo (Moderato)": ("Tempo Moderato (testnet)", 42431, "Tempo mainnet", 4217, ["https://rpc.tempo.xyz", "https://tempo-rpc.publicnode.com"]),
    "Plasma": ("Plasma testnet", 9746, "Plasma mainnet", 9745, ["https://rpc.plasma.to"]),
    "Monad": ("Monad testnet", 10143, "Monad mainnet", 143, ["https://rpc2.monad.xyz", "https://rpc3.monad.xyz"]),
    "Hyperliquid (HyperEVM)": ("HyperEVM testnet", 998, "HyperEVM mainnet", 999, ["https://rpc.hyperliquid.xyz/evm"]),
}
# where a target without code on the main network is looked up next (the repository's own words: scripts/lib/scorers.py score_rollup_l1_authority for Robinhood,
# chains/hyperliquid/METHODOLOGY.md section 3.6 for the bridge)
FALLBACK = {
    "Robinhood Chain": [("Ethereum mainnet", 1, ["https://ethereum-rpc.publicnode.com", "https://gateway.tenderly.co/public/mainnet"])],
    "Hyperliquid (HyperEVM)": [("Arbitrum One mainnet", 42161, ["https://arb1.arbitrum.io/rpc", "https://arbitrum-one-rpc.publicnode.com"])],
}
SOLANA = ("Solana devnet", "Solana mainnet-beta", ["https://api.mainnet-beta.solana.com", "https://solana-rpc.publicnode.com"])
GENESIS = {"Solana mainnet-beta": "5eykt4UsFv8P8NJdTREpY1vzqKqZKvdpKuc147dw2N9d", "Solana devnet": "EtWTRABZaYq6iMfeYKouRu166VU2xqa1wcaWoxPkrZBG"}
NOT_ESTABLISHED = "unplaced"
UNREAD = NOT_ESTABLISHED + " (read impossible)"


def _host(u):
    return u.split("/")[2] if "//" in u else u


def _int(h):
    return int(h, 16) if isinstance(h, str) and h.startswith("0x") else None


def _head(urls, expected_id, rpc, errors):
    """(url, chain id, block number, hash, time) of the first RPC that answers the expected chain id, or None; the causes go to `errors`"""
    for u in urls:
        try:
            cid, num = rpc(u, [("eth_chainId", []), ("eth_blockNumber", [])])
            cid, num = _int(cid), _int(num)
            if cid != expected_id:
                errors.append("%s answers chain %s, expected %s" % (_host(u), cid, expected_id)); continue
            b = rpc(u, [("eth_getBlockByNumber", [hex(num), False])])[0]
            return u, cid, num, b.get("hash"), _int(b.get("timestamp"))
        except Exception as e:  # noqa: BLE001
            errors.append("%s: %s" % (_host(u), str(e)[:80]))
    return None


def evm_fields(name, oracle_url, targets, rpc, batched=None, post_json=None):
    """(record fields, {lower case address: target fields}). `rpc(url, [(method, params)...])` returns the results in order; `batched` is the same by batches
    (default: rpc); `post_json(url, body)` returns the JSON answer of the HyperCore info API (None: that lookup is skipped and said)."""
    batched = batched or rpc
    if name not in TABLE:
        raise KeyError("oracle without an established network in the table: " + name)
    o_net, o_id, t_net, t_id, urls = TABLE[name]
    mod = {"oracle_network": UNREAD, "oracle_chain_id": None, "target_network": UNREAD, "target_chain_id": None, "target_block": None, "target_block_hash": None,
           "target_block_time": None, "target_block_kind": "head of the target network when the Watch read the oracle (not the block the scorer read)", "target_rpc": None}
    try:
        mod["oracle_chain_id"] = _int(rpc(oracle_url, [("eth_chainId", [])])[0])
    except Exception as e:  # noqa: BLE001
        mod["oracle_chain_read_error"] = str(e)[:100]
    if mod["oracle_chain_id"] == o_id:
        mod["oracle_network"] = o_net
    elif mod["oracle_chain_id"] is not None:
        mod["oracle_chain_read_error"] = "the oracle RPC answers chain %s, expected %s (%s)" % (mod["oracle_chain_id"], o_id, o_net)
    errors = []
    head = _head(urls, t_id, rpc, errors)
    if head is None:
        mod["target_read_error"] = "; ".join(errors)[:300] or "no RPC"
    else:
        mod.update(target_network=t_net, target_chain_id=head[1], target_block=head[2], target_block_hash=head[3], target_block_time=head[4], target_rpc=_host(head[0]))
    addresses = [t["target"] if isinstance(t, dict) else t for t in targets]
    out = {}
    for a in addresses:
        out[a.lower()] = {"target_network": UNREAD, "target_chain_id": None, "target_network_read": None, "target_read_block": None, "code_on_target_network": None}
    todo = [a for a in addresses if a.lower() != HELD]
    if HELD in out:   # the one target on a test network: its code is read on the oracle's own RPC
        r = {"target_network": UNREAD, "target_chain_id": None, "target_network_read": None, "target_read_block": None, "code_on_target_network": None}
        try:
            num = _int(rpc(oracle_url, [("eth_blockNumber", [])])[0]); code = rpc(oracle_url, [("eth_getCode", [HELD, hex(num)])])[0]
            r["code_on_target_network"] = isinstance(code, str) and len(code) > 2; r["target_read_block"] = num
            r["target_network_read"] = "code at block %d on %s (chain %s)" % (num, _host(oracle_url), mod["oracle_chain_id"])
            if not r["code_on_target_network"]: r["target_network"] = NOT_ESTABLISHED + " (no code at this address on " + HELD_NETWORK[0] + ")"
            elif mod["oracle_chain_id"] == HELD_NETWORK[1]: r.update(target_network=HELD_NETWORK[0], target_chain_id=HELD_NETWORK[1])   # placed only when the chain id read on that RPC is the one of the test network
            else: r["target_network"] = NOT_ESTABLISHED + " (the RPC does not answer chain %d)" % HELD_NETWORK[1]
        except Exception as e:  # noqa: BLE001
            r.update(target_network=UNREAD, target_network_read=str(e)[:80])
        out[HELD] = r
    if head is not None and todo:
        try:
            codes = batched(head[0], [("eth_getCode", [a, hex(head[2])]) for a in todo])
        except Exception as e:  # noqa: BLE001
            mod["target_code_read_error"] = str(e)[:100]; codes = None
        for i, a in enumerate(todo):
            k = a.lower()
            if codes is None or not isinstance(codes[i], str):
                continue
            if len(codes[i]) > 2:
                out[k] = {"target_network": t_net, "target_chain_id": t_id, "target_network_read": "code at block %d on %s" % (head[2], _host(head[0])), "target_read_block": head[2], "code_on_target_network": True}
            else:
                out[k] = {"target_network": NOT_ESTABLISHED + " (no code at this address on " + t_net + ")", "target_chain_id": None, "target_network_read": None, "target_read_block": head[2], "code_on_target_network": False}
        rest = [a for a in todo if out[a.lower()]["code_on_target_network"] is False]
        for f_net, f_id, f_urls in FALLBACK.get(name, []):
            if not rest:
                break
            errs = []; fh = _head(f_urls, f_id, rpc, errs)
            if fh is None:
                mod.setdefault("target_fallback_errors", []).append("%s: %s" % (f_net, "; ".join(errs)[:150])); continue
            try:
                codes2 = batched(fh[0], [("eth_getCode", [a, hex(fh[2])]) for a in rest])
            except Exception as e:  # noqa: BLE001
                mod.setdefault("target_fallback_errors", []).append("%s: %s" % (f_net, str(e)[:100])); continue
            for i, a in enumerate(rest):
                if isinstance(codes2[i], str) and len(codes2[i]) > 2:
                    out[a.lower()].update(target_network=f_net, target_chain_id=f_id, target_network_read="code at block %d on %s" % (fh[2], _host(fh[0])), target_read_block=fh[2], code_on_target_network=True)
            rest = [a for a in rest if out[a.lower()]["target_chain_id"] is None]
        if rest and name == "Hyperliquid (HyperEVM)":   # natives of HyperCore have no code anywhere: the info API says whether the address exists there
            cache = {}
            def info(kind):
                if kind not in cache: cache[kind] = post_json(HYPERCORE_API, {"type": kind})
                return cache[kind]
            for a in [a for a in rest if a.lower() in DERIVED_KEYS]:   # a key the oracle derives for a HyperCore object: the object is looked up by name, the key is not an account
                string, kind, dex = DERIVED_KEYS[a.lower()]; k = a.lower()
                if post_json is None:
                    out[k]["target_network_read"] = "HyperCore lookup skipped (no client)"; continue
                try:
                    if kind == "l1": found, what = any(isinstance(v, dict) and v.get("validator") for v in (info("validatorSummaries") or [])), "the validator set is listed by validatorSummaries"
                    else: found, what = any(isinstance(d, dict) and d.get("name") == dex for d in (info("perpDexs") or [])), "dex %s is listed by perpDexs" % dex
                except Exception as e:  # noqa: BLE001
                    out[k]["target_network_read"] = "HyperCore lookup failed: " + str(e)[:60]; continue
                if found:
                    out[k].update(target_network="Hyperliquid mainnet (HyperCore)", target_chain_id=None, target_read_block=None, code_on_target_network=None, target_network_read="key derived by the oracle from keccak256(\"%s\"), not an account; %s on %s" % (string, what, _host(HYPERCORE_API)))
            rest = [a for a in rest if a.lower() not in DERIVED_KEYS]
            for a in rest:
                if post_json is None:
                    out[a.lower()]["target_network_read"] = "HyperCore lookup skipped (no client)"; continue
                try:
                    role = (post_json(HYPERCORE_API, {"type": "userRole", "user": a}) or {}).get("role")
                except Exception as e:  # noqa: BLE001
                    out[a.lower()]["target_network_read"] = "HyperCore lookup failed: " + str(e)[:60]; continue
                if isinstance(role, str) and role not in ("missing", ""):
                    out[a.lower()].update(target_network="Hyperliquid mainnet (HyperCore)", target_chain_id=None, target_read_block=None, code_on_target_network=None, target_network_read="HyperCore role=%s on %s (no EVM chain id exists)" % (role, _host(HYPERCORE_API)))
    return mod, out


def solana_fields(targets, rpc_json):
    """Solana has no chain id: the genesis hash read names the network. `rpc_json(url, method, params)` returns the result. A target is on mainnet-beta when its
    account exists there (getMultipleAccounts, 100 at a time)."""
    o_net, t_net, urls = SOLANA
    mod = {"oracle_network": UNREAD, "oracle_chain_id": None, "target_network": UNREAD, "target_chain_id": None, "target_block": None, "target_block_hash": None, "target_block_time": None,
           "target_block_kind": "slot of the target network when the Watch read the oracle (Solana has no chain id: the genesis hash names the network)", "target_rpc": None}
    errors, url = [], None
    for u in urls:
        try:
            g = rpc_json(u, "getGenesisHash", [])
            if g != GENESIS[t_net]:
                errors.append("%s answers genesis %s, expected mainnet-beta" % (_host(u), str(g)[:8])); continue
            mod.update(target_network=t_net, target_genesis=g, target_block=rpc_json(u, "getSlot", [{"commitment": "finalized"}]), target_rpc=_host(u)); url = u; break
        except Exception as e:  # noqa: BLE001
            errors.append("%s: %s" % (_host(u), str(e)[:80]))
    if url is None:
        mod["target_read_error"] = "; ".join(errors)[:300] or "no RPC"
    addresses = [t["target"] if isinstance(t, dict) else t for t in targets]
    out = {}
    for i in range(0, len(addresses), 100):
        lot = addresses[i:i + 100]
        try:
            seen = rpc_json(url, "getMultipleAccounts", [lot, {"encoding": "base64", "dataSlice": {"offset": 0, "length": 0}, "commitment": "finalized"}])["value"] if url else None
        except Exception:  # noqa: BLE001
            seen = None
        for j, a in enumerate(lot):
            if seen is None or len(seen) != len(lot):
                out[a] = {"target_network": UNREAD, "target_chain_id": None, "target_network_read": None, "target_read_block": None, "account_on_target_network": None}
            elif seen[j]:
                out[a] = {"target_network": t_net, "target_chain_id": None, "target_network_read": "account exists on %s (genesis %s)" % (_host(url), g[:8]), "target_read_block": mod["target_block"], "account_on_target_network": True}
            else:
                out[a] = {"target_network": NOT_ESTABLISHED + " (no account at this address on " + t_net + ")", "target_chain_id": None, "target_network_read": None, "target_read_block": mod["target_block"], "account_on_target_network": False}
    return mod, out


def apply(doc, mod, per_target):
    """put the fields on the document read (record and every target); a target missing from `per_target` gets "unplaced", never nothing"""
    doc.update(mod)
    for t in doc.get("targets", []):
        c = per_target.get(t["target"].lower()) or per_target.get(t["target"]) or {"target_network": NOT_ESTABLISHED + " (target not read)", "target_chain_id": None}
        t.update(c)
    return doc
