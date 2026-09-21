"""Read what a contract does from its bytecode alone, and where its source is verified, without depending on a block explorer.

ADDED 2026-09-21. Some chains' explorers sit behind bot protection (Robinhood Chain's Blockscout, Monad's MonadVision) or need an API key
(Etherscan V2), and this project does not get around a bot check. Everything here uses open, keyless interfaces or the chain's own RPC:

- `selectors(code)`: the function selectors a contract's dispatcher compares against (solc and vyper style), which is its ABI surface;
- `compiler_metadata(code)`: the compiler version and the IPFS metadata hash from the CBOR tail solc appends;
- `compare(old, new)`: what a new implementation adds or drops compared with the old one, by selector;
- `resolve_names(selectors)`: selector -> signature through the public signature database (openchain.xyz), best effort;
- `verification(chain_id, address)`: where the source is verified, asked of Sourcify (any chain) and Routescan (keyless, where supported)
  and, only if the operator supplies a key in ETHERSCAN_API_KEY, Etherscan V2. Anything not answerable is "unknown", never "unverified".

The network readers are injected so the parsing logic runs without a chain.
"""
import json
import os
import urllib.error
import urllib.request

_UA = {"User-Agent": "authority-risk-oracle-research/1.0 (read-only)"}

# Routescan serves keyless Etherscan-compatible calls for these chains (checked 2026-09-21: Plasma and Ethereum answered, Monad and
# Robinhood Chain answered "chain not supported").
ROUTESCAN_CHAINS = {1, 9745}
# Etherscan V2 chain ids the operator's own key is used for, if they provide one. Monad mainnet is 143.
ETHERSCAN_V2_CHAINS = {1, 143, 9745, 8453, 42161}
# Chains where an explorer exists that this module does NOT query, and why. For these a Sourcify "not verified" is NOT "unverified":
# the source may be verified on the explorer. The reason is part of every answer, so nobody reads silence as absence.
UNQUERYABLE_EXPLORERS = {
    4663: "Robinhood Chain's explorers cannot be queried: Blockscout sits behind a bot check and hoodscan's MCP indexer was down",
    143: "MonadScan needs an Etherscan V2 key (ETHERSCAN_API_KEY) and MonadVision sits behind a bot check",
    42161: "Arbiscan needs an Etherscan V2 key (ETHERSCAN_API_KEY)",
    8453: "Basescan needs an Etherscan V2 key (ETHERSCAN_API_KEY)",
    4217: "the Tempo explorer was not queried",
    999: "the HyperEVM explorers were not queried",
}

_B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def selectors(code):
    """Function selectors compared in the dispatcher: a PUSH4 (0x63) whose next opcode is EQ (0x14), or DUP2 EQ (0x81 0x14).
    Requiring the comparison drops the 4-byte constants that are only data. Returns a set of '0x' + 8 hex characters."""
    code = bytes(code)
    out, i, n = set(), 0, len(code)
    while i < n - 5:
        if code[i] == 0x63:
            nxt = code[i + 5]
            if nxt == 0x14 or (nxt == 0x81 and i + 6 < n and code[i + 6] == 0x14):
                out.add("0x" + code[i + 1:i + 5].hex())
            i += 5
        else:
            i += 1
    return out


def _b58(raw):
    num = int.from_bytes(raw, "big")
    out = ""
    while num:
        num, rem = divmod(num, 58)
        out = _B58[rem] + out
    return "1" * (len(raw) - len(raw.lstrip(b"\x00"))) + out


def compiler_metadata(code):
    """{"solc": "0.8.24" or None, "ipfs": "Qm..." or None, "swarm": bool} from the CBOR tail solc appends (last two bytes = its length)."""
    code = bytes(code)
    result = {"solc": None, "ipfs": None, "swarm": False}
    if len(code) < 4:
        return result
    length = int.from_bytes(code[-2:], "big")
    if length + 2 > len(code) or length < 10:
        return result
    tail = code[-(length + 2):-2]
    marker = b"\x64ipfs\x58\x22"
    at = tail.find(marker)
    if at >= 0 and len(tail) >= at + len(marker) + 34:
        result["ipfs"] = _b58(tail[at + len(marker):at + len(marker) + 34])
    at = tail.find(b"\x64solc\x43")
    if at >= 0 and len(tail) >= at + 9:
        major, minor, patch = tail[at + 6:at + 9]
        result["solc"] = f"{major}.{minor}.{patch}"
    result["swarm"] = b"bzzr" in tail
    return result


def compare(old_code, new_code):
    """What changed between two implementations: sizes, added and removed selectors, compiler metadata of each."""
    old_sel, new_sel = selectors(old_code), selectors(new_code)
    return {
        "sizeOld": len(old_code), "sizeNew": len(new_code),
        "added": sorted(new_sel - old_sel), "removed": sorted(old_sel - new_sel), "kept": len(old_sel & new_sel),
        "metadataOld": compiler_metadata(old_code), "metadataNew": compiler_metadata(new_code),
        "identicalCode": bytes(old_code) == bytes(new_code),
    }


def _get_json(url, headers=None, timeout=25, opener=urllib.request.urlopen):
    req = urllib.request.Request(url, headers={**_UA, **(headers or {})})
    with opener(req, timeout=timeout) as f:
        return json.load(f)


def resolve_names(sels, opener=urllib.request.urlopen):
    """{selector: [signature, ...] or None}; an unreachable or empty database gives None for every selector, never a guess."""
    sels = sorted(sels)
    if not sels:
        return {}
    out = {s: None for s in sels}
    for i in range(0, len(sels), 40):
        chunk = sels[i:i + 40]
        try:
            d = _get_json("https://api.openchain.xyz/signature-database/v1/lookup?filter=true&function=" + ",".join(chunk), opener=opener)
            for k, v in d["result"]["function"].items():
                out[k] = [x["name"] for x in v] if v else None
        except Exception:  # noqa: BLE001 -- best effort, a missing name is reported as unknown
            continue
    return out


def _sourcify(chain_id, address, opener):
    try:
        d = _get_json(f"https://sourcify.dev/server/v2/contract/{chain_id}/{address}?fields=compilation", opener=opener)
        return {"source": "sourcify", "status": d.get("match") or "verified", "name": (d.get("compilation") or {}).get("name")}
    except urllib.error.HTTPError as e:
        return {"source": "sourcify", "status": "not verified" if e.code == 404 else f"unknown (HTTP {e.code})", "name": None}
    except Exception:  # noqa: BLE001
        return {"source": "sourcify", "status": "unknown (unreachable)", "name": None}


def _etherscan_like(source, url, opener):
    try:
        d = _get_json(url, opener=opener)
    except Exception:  # noqa: BLE001
        return {"source": source, "status": "unknown (unreachable)", "name": None}
    result = d.get("result")
    if d.get("status") == "1" and isinstance(result, list) and result:
        row = result[0]
        if row.get("SourceCode") and row.get("ABI") != "Contract source code not verified":
            return {"source": source, "status": "verified", "name": row.get("ContractName") or None}
        return {"source": source, "status": "not verified", "name": None}
    return {"source": source, "status": f"unknown ({d.get('message') or 'no answer'})", "name": None}


def verification(chain_id, address, opener=urllib.request.urlopen, environ=None):
    """Where the source of `address` on `chain_id` is verified: a list of {"source", "status", "name"}. A source that cannot answer
    says "unknown ...", and a chain no open source covers is stated as such: absence from one explorer is not "unverified"."""
    environ = os.environ if environ is None else environ
    out = [_sourcify(chain_id, address, opener)]
    if chain_id in ROUTESCAN_CHAINS:
        out.append(_etherscan_like(
            "routescan", f"https://api.routescan.io/v2/network/mainnet/evm/{chain_id}/etherscan/api?module=contract&action=getsourcecode&address={address}", opener))
    key = environ.get("ETHERSCAN_API_KEY")
    answered_by_key = False
    if key and chain_id in ETHERSCAN_V2_CHAINS:
        answered_by_key = True
        out.append(_etherscan_like(
            "etherscan-v2", f"https://api.etherscan.io/v2/api?chainid={chain_id}&module=contract&action=getsourcecode&address={address}&apikey={key}", opener))
    reason = UNQUERYABLE_EXPLORERS.get(chain_id)
    # A key answers the Etherscan-family chains (Monad, Arbitrum, Base); it does not make Robinhood Chain's explorers queryable.
    if reason and not (answered_by_key and chain_id in (143, 42161, 8453)):
        out.append({"source": "explorer", "status": f"unknown ({reason})", "name": None})
    return out


def verified_anywhere(results):
    """True if any answering source says verified, False if every source answered "not verified", None if any is unknown and none verified."""
    if any(r["status"] not in ("not verified",) and not r["status"].startswith("unknown") for r in results):
        return True
    if results and all(r["status"] == "not verified" for r in results):
        return False
    return None


def summarize(review, names=None):
    """Plain-text lines for a `compare()` result. `names` maps selector -> [signature] from resolve_names."""
    names = names or {}
    label = lambda s: (names.get(s) or [s])[0]  # noqa: E731
    lines = []
    if review["identicalCode"]:
        lines.append("the two implementations are byte-identical (the address changed, the code did not)")
        return lines
    lines.append(f"size {review['sizeOld']} -> {review['sizeNew']} bytes; {review['kept']} selectors kept, "
                 f"{len(review['added'])} added, {len(review['removed'])} removed")
    if review["added"]:
        lines.append("  added:   " + ", ".join(label(s) for s in review["added"][:25]) + (" ..." if len(review["added"]) > 25 else ""))
    if review["removed"]:
        lines.append("  removed: " + ", ".join(label(s) for s in review["removed"][:25]) + (" ..." if len(review["removed"]) > 25 else ""))
    mo, mn = review["metadataOld"], review["metadataNew"]
    lines.append(f"  compiler: solc {mo['solc']} -> {mn['solc']}; metadata {'same' if mo['ipfs'] == mn['ipfs'] else 'different'}")
    return lines
