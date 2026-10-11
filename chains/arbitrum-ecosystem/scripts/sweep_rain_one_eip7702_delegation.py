#!/usr/bin/env python3
"""Independent cross-check: rain.one (Arbitrum), EIP-7702 delegation.

Read-only. No key, no destructive call. All values are
read live (Arbitrum RPC, DefiLlama, GitHub, Blockscout); nothing is
copied from a previous report. Each assertion prints its source.

Usage: python3 verify_rain_one.py
"""
import json
import time

import requests

ARB_RPC = "https://arb1.arbitrum.io/rpc"
UA = "Mozilla/5.0 (research-verification-script)"

EIP1967_IMPL_SLOT = "0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc"
SEL_OWNER = "0x8da5cb5b"          # owner()
SEL_THRESHOLD = "0xe75235b8"      # getThreshold()
SEL_OWNERS = "0xa0e67e2b"         # getOwners()
EIP7702_PREFIX = "ef0100"


def http_get(url, timeout=20, retries=3):
    last_err = None
    for _ in range(retries):
        try:
            r = requests.get(url, headers={"User-Agent": UA}, timeout=timeout)
            r.raise_for_status()
            return r.content
        except Exception as e:  # pragma: no cover - network flakiness
            last_err = e
            time.sleep(1)
    raise last_err


def rpc(method, params, timeout=20, retries=3):
    body = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    last_err = None
    for _ in range(retries):
        try:
            r = requests.post(ARB_RPC, json=body, headers={"User-Agent": UA}, timeout=timeout)
            r.raise_for_status()
            out = r.json()
            if "error" in out:
                raise RuntimeError(f"{method}{params} -> RPC error {out['error']}")
            return out["result"]
        except Exception as e:
            last_err = e
            time.sleep(1)
    raise last_err


def eth_call(to, data):
    return rpc("eth_call", [{"to": to, "data": data}, "latest"])


def addr_from_word(word_hex):
    """Last 20 bytes of a 32-byte word (checksum not applied, just lowercase)."""
    h = word_hex[2:] if word_hex.startswith("0x") else word_hex
    h = h.rjust(64, "0")
    return "0x" + h[-40:]


def decode_owners_array(hex_data):
    """Minimal ABI decode for address[] (getOwners() return)."""
    h = hex_data[2:]
    offset = int(h[0:64], 16) * 2
    length = int(h[offset:offset + 64], 16)
    out = []
    for i in range(length):
        start = offset + 64 + i * 64
        out.append(addr_from_word(h[start:start + 64]))
    return out


def main():
    findings = {}
    print("=== 1. DefiLlama identification (api.llama.fi/protocol/rain) ===")
    llama = json.loads(http_get("https://api.llama.fi/protocol/rain"))
    print(f"  name={llama.get('name')} category={llama.get('category')} chains={llama.get('chains')}")
    print(f"  url={llama.get('url')} github={llama.get('github')} address={llama.get('address')}")
    token_addr = llama["address"].split(":")[-1]
    findings["defillama_token_address"] = token_addr
    findings["defillama_category"] = llama.get("category")
    findings["defillama_chains"] = llama.get("chains")
    findings["defillama_github"] = llama.get("github")

    print("\n=== 2. GitHub org rain1-labs (api.github.com) ===")
    gh = json.loads(http_get("https://api.github.com/orgs/rain1-labs"))
    print(f"  login={gh.get('login')} created_at={gh.get('created_at')} blog={gh.get('blog')} type={gh.get('type')}")
    findings["github_org_verified"] = gh.get("login") == "rain1-labs"
    findings["github_org_blog"] = gh.get("blog")

    print("\n=== 3. Official docs rain1-labs/docs (raw.githubusercontent.com) ===")
    doc = http_get(
        "https://raw.githubusercontent.com/rain1-labs/docs/main/"
        "For-Developers/Rain-SDK/Environments-and-Configuration.mdx"
    ).decode()
    factory_addr = None
    for line in doc.splitlines():
        if "| production" in line:
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            factory_addr = cells[-1]
    print(f"  Production Factory extracted from the docs = {factory_addr}")
    findings["factory_from_docs"] = factory_addr
    if not factory_addr or not factory_addr.startswith("0x") or len(factory_addr) != 42:
        print("  FAILURE: factory address not found/malformed in the docs.")
        findings["worth_committing"] = False
        print(json.dumps(findings, indent=2))
        return

    print(f"\n=== 4. On-chain reads on Arbitrum (RPC {ARB_RPC}) ===")
    bn = rpc("eth_blockNumber", [])
    print(f"  current block = {int(bn, 16)}")

    def describe_eip1967(addr, label):
        code = rpc("eth_getCode", [addr, "latest"])
        code_len = (len(code) - 2) // 2
        impl_word = rpc("eth_getStorageAt", [addr, EIP1967_IMPL_SLOT, "latest"])
        impl = addr_from_word(impl_word)
        is_proxy = impl != "0x" + "0" * 40
        print(f"  {label} ({addr}): {code_len} bytes of code")
        print(f"    EIP-1967 impl slot = {impl if is_proxy else '(empty, not an EIP-1967 proxy)'}")
        return code_len, (impl if is_proxy else None)

    factory_len, factory_impl = describe_eip1967(factory_addr, "Factory")
    findings["factory_code_len"] = factory_len
    findings["factory_eip1967_impl"] = factory_impl

    factory_owner = addr_from_word(eth_call(factory_addr, SEL_OWNER))
    factory_owner_code = rpc("eth_getCode", [factory_owner, "latest"])
    factory_owner_nonce = rpc("eth_getTransactionCount", [factory_owner, "latest"])
    print(f"  Factory.owner() = {factory_owner}")
    print(f"    owner code = {factory_owner_code!r} ({'EOA' if factory_owner_code == '0x' else 'CONTRACT'}), nonce={int(factory_owner_nonce, 16)}")
    findings["factory_owner"] = factory_owner
    findings["factory_owner_is_eoa"] = factory_owner_code == "0x"
    findings["factory_owner_nonce"] = int(factory_owner_nonce, 16)
    findings["factory_owner_has_7702_delegation"] = factory_owner_code.startswith("0x" + EIP7702_PREFIX)

    print(f"\n--- Token RAIN ({token_addr}) ---")
    token_len, token_impl = describe_eip1967(token_addr, "Token RAIN")
    findings["token_code_len"] = token_len
    findings["token_eip1967_impl"] = token_impl

    token_owner = addr_from_word(eth_call(token_addr, SEL_OWNER))
    token_owner_code = rpc("eth_getCode", [token_owner, "latest"])
    print(f"  Token.owner() = {token_owner}")
    print(f"    owner code = {(len(token_owner_code) - 2) // 2} bytes ({'EOA' if token_owner_code == '0x' else 'CONTRACT'})")
    findings["token_owner"] = token_owner
    findings["token_owner_is_contract"] = token_owner_code != "0x"

    threshold = None
    owners = []
    if token_owner_code != "0x":
        try:
            threshold = int(eth_call(token_owner, SEL_THRESHOLD), 16)
            owners = decode_owners_array(eth_call(token_owner, SEL_OWNERS))
            print(f"    getThreshold()={threshold}, getOwners()={owners}  (Safe standard)")
        except Exception as e:
            print(f"    not a standard Safe (getThreshold/getOwners failed: {e})")
    findings["safe_threshold"] = threshold
    findings["safe_owners"] = owners

    print("\n=== 5. EIP-7702 delegations on each Safe signer ===")
    delegated = {}
    for o in owners:
        code = rpc("eth_getCode", [o, "latest"])
        nonce = int(rpc("eth_getTransactionCount", [o, "latest"]), 16)
        if code.startswith("0x" + EIP7702_PREFIX):
            target = "0x" + code[2 + 6:2 + 6 + 40]
            print(f"  {o}: EIP-7702 DELEGATION -> {target}  (nonce={nonce})")
            delegated[o] = {"target": target, "nonce": nonce}
        else:
            kind = "EOA" if code == "0x" else f"CONTRACT ({(len(code) - 2) // 2} bytes)"
            print(f"  {o}: {kind}, no delegation (nonce={nonce})")
    findings["signers_with_7702_delegation"] = delegated

    print("\n=== 6. Comparison with the address already documented in pass 8 ===")
    KNOWN_PASS8_DELEGATE = "0x63c0c19a282a1B52b07dD5a65b58948A07DAE32B".lower()
    print(f"  Known address (read in the repo's scripts/lib/nested_signers.py) = {KNOWN_PASS8_DELEGATE}")
    matches = [addr for addr, d in delegated.items() if d["target"].lower() == KNOWN_PASS8_DELEGATE]
    print(f"  Signers whose delegation targets this exact address: {matches}")
    findings["known_pass8_delegate"] = KNOWN_PASS8_DELEGATE
    findings["signers_matching_pass8_delegate"] = matches

    if matches:
        target = delegated[matches[0]]["target"]
        target_code_len = (len(rpc("eth_getCode", [target, "latest"])) - 2) // 2
        print(f"  Size of the delegate contract ({target}) on Arbitrum = {target_code_len} bytes")
        findings["delegate_contract_len_arbitrum"] = target_code_len

    print("\n=== 7. Independent cross-check: Blockscout Arbitrum (arbitrum.blockscout.com) ===")
    try:
        bs = json.loads(http_get(f"https://arbitrum.blockscout.com/api/v2/addresses/{token_owner}"))
        print(f"  Blockscout: is_contract={bs.get('is_contract')} name={bs.get('name')} "
              f"proxy_type={bs.get('proxy_type')}")
        findings["blockscout_token_owner_name"] = bs.get("name")
        findings["blockscout_token_owner_is_contract"] = bs.get("is_contract")
    except Exception as e:
        print(f"  Blockscout unreachable/error: {e}")
        findings["blockscout_error"] = str(e)

    print("\n=== 8. www.rain.one direct ===")
    try:
        http_get("https://www.rain.one/", timeout=10)
        findings["rain_one_site_status"] = "OK"
    except Exception as e:
        print(f"  {e}")
        findings["rain_one_site_status"] = str(e)

    print("\n=== SUMMARY (values observed by THIS run) ===")
    print(json.dumps(findings, indent=2, default=str))


if __name__ == "__main__":
    main()
