"""
Canonical home for RpcUnavailable -- split out of web3_utils.py on 2026-09-22 after action
(maker-checker journal) was REJECTED for exactly the bug this file exists to prevent: web3_utils.py
can be imported two different ways in this repo (`from web3_utils import ...` after a bare
`sys.path.insert`, or `from lib.web3_utils import ...` as a package member), and Python caches a
module under the exact string used to import it -- so "web3_utils" and "lib.web3_utils" are TWO
separate module objects for the same file, with two separate `class RpcUnavailable` definitions
that are not `is`-identical and don't match each other's `except RpcUnavailable` / `isinstance`
checks. #182's fix caught this for its own new test (by importing the module object instead of the
class directly) but never checked whether the real production caller
(scripts/check_cross_ecosystem_overlap.py, which imports web3_utils via the `lib.` path) raised a
class its `except RpcUnavailable` in scripts/lib/cross_ecosystem_overlap.py (which imports web3_utils
bare) could actually catch. It could not: 6 of that script's 7 ecosystems silently fell through to
the generic `except Exception`, and its own new "unmissable summary" then printed a false all-clear.

The fix mirrors this file's neighbor, scripts/lib/abi_returndata_guard.py, and the canonicalization
comment already sitting above `import abi_returndata_guard` in web3_utils.py: import this module
BARE (`import rpc_unavailable`, never `from lib.rpc_unavailable import ...` or `from
lib import rpc_unavailable`), after appending (never inserting first) this directory to sys.path.
Because the import string `"rpc_unavailable"` is fixed no matter which cached identity of
web3_utils.py runs that import line, both `web3_utils.RpcUnavailable` and
`lib.web3_utils.RpcUnavailable` end up being literal attribute aliases of the exact same class
object in sys.modules['rpc_unavailable'].RpcUnavailable -- there is only one RpcUnavailable class in
this process, structurally, not by every caller happening to import it the same way.
"""


class RpcUnavailable(RuntimeError):
    """The chain could not be read (timeout, connection failure, rate limit, malformed response) --
    this is NOT information about the chain, unlike a confirmed revert. Raised by `_read()` in
    web3_utils.py after the last retry attempt, so a caller (`safe_score()`, or an explicit catch at
    a sweep boundary -- see scripts/lib/safe_modules.py, scripts/lib/cross_ecosystem_overlap.py)
    skips this target instead of treating a bare `None` as if the contract itself had answered "no".
    See the backlog item this closes: a read helper that returned the same `None` for both cases let
    a transient RPC failure silently retire a scoring dimension to its floor value under load (e.g.
    Base: Uniswap V3 Factory 85 vs 38, Morpho Blue 55 vs 8, observed between two runs of the same
    tree on 2026-09-2x) -- publishing a wrong score with no indication it might be wrong."""
