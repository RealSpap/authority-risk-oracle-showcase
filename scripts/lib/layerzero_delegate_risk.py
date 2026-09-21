"""
LayerZero V2 "delegate" risk check -- the attack surface The Sandbox's SAND
bridge exploit used: an OApp's `delegate` (set via `EndpointV2.setDelegate()`)
can reconfigure that OApp's entire security stack (DVNs, executors, message
libraries) WITHOUT ever touching the OApp's own owner/admin. A perfectly
governed owner (a real DAO, a strong Safe) means nothing if a weaker address
holds the delegate role instead -- the two are structurally independent
authority surfaces on the exact same contract.

Deliberately NOT wired into score_all() as a scored dimension yet: checked
live 2026-09-17 against every one of Robinhood Chain's ~42 tracked targets
(and their intermediate authority addresses, 57 addresses total) --
ZERO are registered as LayerZero OApps with a delegate set. There is
currently nothing on this chain for this dimension to say anything about;
adding a permanent per-entry score field that reads "not applicable" for
literally every tracked target forever would be clutter, not signal. This
module exists so the check is a real, reusable, one-line capability the
moment a tracked target IS a LayerZero OApp (see
scripts/check_layerzero_delegate_risk.py to re-run it), not a hypothetical
plan.
"""
from web3 import Web3

_DELEGATES_ABI = [
    {"name": "delegates", "type": "function", "stateMutability": "view", "inputs": [{"type": "address"}], "outputs": [{"type": "address"}]}
]

ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"


def get_oapp_delegate(w3, endpoint_address: str, oapp_address: str):
    """Returns the delegate address LayerZero's EndpointV2 has on file for
    `oapp_address`, or None if it's not registered as an OApp on this
    Endpoint at all (never called `setDelegate()`, or isn't a LayerZero OApp)."""
    try:
        contract = w3.eth.contract(address=Web3.to_checksum_address(endpoint_address), abi=_DELEGATES_ABI)
        delegate = contract.functions.delegates(Web3.to_checksum_address(oapp_address)).call()
        if delegate.lower() == ZERO_ADDRESS:
            return None
        return delegate
    except Exception:
        return None


def find_registered_oapps(w3, endpoint_address: str, candidate_addresses) -> dict:
    """Checks every address in `candidate_addresses` against the Endpoint and
    returns {address: delegate} for whichever ones are actually registered
    OApps (delegate set and non-zero). Pure I/O loop over get_oapp_delegate() --
    the interesting logic (what counts as "registered") lives there, tested
    without a live chain in scripts/lib/tests/test_layerzero_delegate_risk.py."""
    return {
        addr: delegate
        for addr in candidate_addresses
        if (delegate := get_oapp_delegate(w3, endpoint_address, addr)) is not None
    }
