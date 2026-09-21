#!/usr/bin/env python3
"""Read-only NEAR RPC helper for the zec.omft.near PoA bridge authority
(no deps, uses curl, same style as zcash_read.py -- plain JSON-RPC, no
keys, no signing).

Added 2026-09-17 to resolve METHODOLOGY.md section 8's open question
("Identify the NEAR contract that controls zec.omft.near minting and its
signer set"). Source for the contract shape: `github.com/near/intents`,
`contracts/poa/factory/src/contract.rs` -- the factory contract
(`omft.near`) gates minting (`ft_deposit`) behind a `near_plugins`
access-control role (`Role::TokenDepositer`, OR'd with `Role::DAO`), the
same access-control-list pattern already handled elsewhere in this project
for EVM `AccessControl` and Tempo's TIP-20 roles, just NEAR's own
implementation of it.

Usage:
  near_read.py acl <rpc> <account_id>                 -> acl_get_permissioned_accounts()
  near_read.py keys <rpc> <account_id>                 -> view_access_key_list
  near_read.py policy <rpc> <account_id>               -> Sputnik DAO get_policy()
  near_read.py supply <rpc> <account_id>               -> ft_total_supply() (decimals via ft_metadata())
"""
import base64
import json
import subprocess
import sys


def rpc(url, method, params, tries=4):
    import time
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
    last = None
    for i in range(tries):
        out = subprocess.run(
            ["curl", "-s", "-m", "30", "-X", "POST", "-H", "Content-Type: application/json", "-d", body, url],
            capture_output=True, text=True,
        ).stdout
        try:
            r = json.loads(out)
        except json.JSONDecodeError:
            last = out[:200]
            time.sleep(2 * (i + 1))
            continue
        if "error" in r:
            last = r["error"]
            time.sleep(2 * (i + 1))
            continue
        return r["result"]
    # FIXED 2026-09-19: this used to raise SystemExit, a BaseException
    # subclass that escapes a plain `except Exception` -- every caller of
    # this module (chains/zcash/scorers.py::score_ext_zec_omft(), reached
    # through score_all()'s `except Exception as e:` wrapper, same pattern
    # every other target in this project degrades through) would have had
    # a single bad/slow NEAR RPC call crash the ENTIRE score_all() run
    # instead of gracefully skipping just this one target, the same class
    # of bug this project's own "SKIPPED <target> -- RuntimeError: RPC
    # down" convention exists to avoid everywhere else. Found while
    # deciding whether this module needed dedicated tests, not by a test
    # itself -- no score, on-chain state, or behavior other than this
    # exception type changes.
    raise RuntimeError(f"NEAR RPC failed after retries: {method} {params} -- {last}")


def call_view(url, account_id, method_name, args=None):
    args_b64 = base64.b64encode(json.dumps(args or {}).encode()).decode()
    result = rpc(url, "query", {
        "request_type": "call_function", "finality": "final",
        "account_id": account_id, "method_name": method_name, "args_base64": args_b64,
    })
    raw = bytes(result["result"])
    try:
        return json.loads(raw.decode())
    except (json.JSONDecodeError, UnicodeDecodeError):
        return raw.decode(errors="replace")


def access_key_count(url, account_id):
    result = rpc(url, "query", {"request_type": "view_access_key_list", "finality": "final", "account_id": account_id})
    return result["keys"]


def permissioned_accounts(url, factory_account_id):
    """near_plugins access-control: super_admins plus, per role, admins/grantees."""
    return call_view(url, factory_account_id, "acl_get_permissioned_accounts")


def dao_policy(url, dao_account_id):
    """Sputnik DAO v2 get_policy() -- roles (each a group of members plus a
    per-permission vote_policy: {weight_kind, quorum, threshold})."""
    return call_view(url, dao_account_id, "get_policy")


def ft_total_supply(url, token_account_id):
    return call_view(url, token_account_id, "ft_total_supply")


if __name__ == "__main__":
    cmd, url, acct = sys.argv[1], sys.argv[2], sys.argv[3]
    if cmd == "acl":
        print(json.dumps(permissioned_accounts(url, acct), indent=1))
    elif cmd == "keys":
        print(json.dumps(access_key_count(url, acct), indent=1))
    elif cmd == "policy":
        print(json.dumps(dao_policy(url, acct), indent=1))
    elif cmd == "supply":
        print(ft_total_supply(url, acct))
    else:
        raise SystemExit(f"unknown command: {cmd}")
