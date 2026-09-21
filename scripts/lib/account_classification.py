"""
Account classification hardening -- closes a real blind spot this project's
sister research, defi-admin-key-risk, hit across 96+ EVM protocols: the
mechanical "zero eth_getCode = bare EOA" heuristic (web3_utils.is_eoa())
silently breaks under EIP-7702 (live on every EVM chain post-Pectra, 2025).
A 7702-delegated EOA has exactly 23 bytes of code (the 0xef0100 delegation
designator + a 20-byte delegate address) -- `is_eoa()` correctly says False
for it (it DOES have code), but everywhere this project's scorers use "not a
bare EOA" as a signal to trace FURTHER (assume a real contract, root-cause
its own owner/Safe/timelock), a 7702-delegated address would get traced as
if it were that delegate contract's own logic controlling it, when the real
authority is still whatever signing key controls the underlying EOA --
functionally a single key, not the multisig/DAO/timelock the further trace
might land on. This is the exact pattern the Moonwell MAMO exploit used: an
ordinary MetaMask wallet, EIP-7702-delegated, running as an exploit contract.

Deliberately a NEW, separate function rather than a change to is_eoa()
itself -- is_eoa() is used in dozens of call sites across every chain's
scorers.py, and silently changing its return value for the 7702 case would
be a much larger, riskier blast radius than adding one new, opt-in check.
"""
from web3 import Web3

EIP7702_DELEGATION_PREFIX = bytes.fromhex("ef0100")


def classify_account(w3, address: str) -> dict:
    """Returns {"kind": "bare_eoa" | "eip7702_delegated" | "contract",
    "delegate": <address or None>}. `kind == "eip7702_delegated"` means this
    address is still fundamentally controlled by ONE signing key (same
    single-point-of-failure shape as a bare EOA) even though it has code and
    would fail a naive is_eoa() check -- callers that currently branch on
    is_eoa() to decide "trace this further as a real contract" should treat
    this case like a bare EOA, not like an unresolved contract."""
    code = w3.eth.get_code(Web3.to_checksum_address(address))
    if code == b"":
        return {"kind": "bare_eoa", "delegate": None}
    if len(code) == 23 and code[:3] == EIP7702_DELEGATION_PREFIX:
        return {"kind": "eip7702_delegated", "delegate": Web3.to_checksum_address(code[3:])}
    return {"kind": "contract", "delegate": None}


_GET_ROLE_ADMIN_ABI = [
    {"name": "getRoleAdmin", "type": "function", "stateMutability": "view", "inputs": [{"type": "bytes32"}], "outputs": [{"type": "bytes32"}]}
]


def check_self_escalation_risk(w3, contract_address: str, role: bytes) -> dict:
    """Closes another defi-admin-key-risk blind spot: AccessControl roles have
    no threshold semantics, so if `role`'s own admin role IS `role` (OZ's
    getRoleAdmin(role) == role, the self-administering pattern), then ANY
    single current holder of `role` can unilaterally grant it to a new
    address or revoke it from a legitimate multisig -- a "1-of-N roles"
    failure mode structurally identical to a 1-of-N Safe threshold, but
    invisible to a check that only counts Safe/multisig signers, since it
    lives in the role-admin graph, not the signer list.

    Returns {"checked": bool, "self_administering": bool | None,
    "role_admin": bytes32 | None}. `checked=False` means getRoleAdmin()
    itself reverted -- this contract doesn't use OZ AccessControl (or a
    non-standard variant), not a confirmed-safe result."""
    try:
        contract = w3.eth.contract(address=Web3.to_checksum_address(contract_address), abi=_GET_ROLE_ADMIN_ABI)
        role_admin = contract.functions.getRoleAdmin(role).call()
    except Exception:
        return {"checked": False, "self_administering": None, "role_admin": None}
    return {"checked": True, "self_administering": role_admin == role, "role_admin": role_admin}
