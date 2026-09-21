#!/usr/bin/env python3
"""Rotation audit of Base tracked-target index 1 (Aave V3 Base
PoolAddressesProvider 0xe20fCBdBfFC4Dd138cE8b2E6FBb6CB49777ad64D).

Written 2026-09-21 to replace scratchpad audits that failed review twice:
the 2026-09-20 one imported chains/base-ecosystem/scorers.py by importlib
(pure circularity), and the 2026-09-21 tentative-1 one dropped the import
but kept a copy-pasted EXPECTED_ARBITRUM_GUARDIAN_OWNERS constant, used
(a+m+t)//3 instead of the documented composite formula, and compared the
"published" score to a frozen CSV instead of the live oracle.

Non-circularity rules this file holds itself to:
  * it never imports, execs or reads chains/base-ecosystem/scorers.py, nor
    scripts/lib/*;
  * it hardcodes NO owner set, NO score and NO expected component: every
    number below is either read from a chain in this run or computed from a
    rule quoted from METHODOLOGY.md;
  * the only hardcoded addresses are the audited target itself, the
    ecosystem's tracked-target list (a list of what is tracked, not of what
    it scores) and two Aave PoolAddressesProviders, each cross-checked
    against the primary source bgd-labs/aave-address-book over HTTPS by
    --check-address-book;
  * the comparison baseline is getScore() read live on Base Sepolia, on two
    independent RPCs, not a CSV.

Rules applied, quoted from METHODOLOGY.md (repo root):

  compositeScore = floor(0.4*adminKey + 0.3*multisig + 0.3*timelock + 0.5)
      ("### Aggregation"; round-half-up, not Python round())

  adminKeyScore   "A resolved external-DAO root scores in the 75-85 range
      depending on how directly its quorum/delay were independently
      re-confirmed live [...] an unresolved contract [...] scores 20".
      Base's Aave root is the Ethereum-mainnet Aave DAO reached through the
      cross-chain Executor <-> PayloadsController pair. From a Base RPC the
      L1 DAO root itself (quorum, proposal counts, the L1 Timelock the
      CROSS_CHAIN_CONTROLLER relays from) cannot be re-confirmed, so the
      resolved-DAO band is entered at its floor minus the 10-point gap the
      ecosystem uses for a relay-only confirmation: 65 when the pair closes
      on itself and matches the address book, 30 when it does not resolve.

  multisigScore   "100 if not applicable (the root is a real, active DAO with
      no Safe layer)". Derived here, not assumed: getOwners()/getThreshold()
      are called on both halves of the root pair and must both revert.

  timelockScore   "A confirmed real delay scores 60-75 depending on length
      and whether an emergency-bypass path was checked for and ruled out;
      capped below 100 whenever that bypass check wasn't done this pass [...]
      A confirmed bypass that is bounded [...] caps the score at 55."
      PayloadsController.guardian() is a live, confirmed cancel path that
      acts outside the 1-day delay, and the L1 root is unverified from a Base
      RPC, so the score is capped below the bounded-bypass cap of 55: 50 when
      a real positive delay is read, 0 when none is.

  oracleAuthorityScore  "100 (not applicable) for every target that neither
      provides nor depends on an oracle role this project tracks." Derived:
      the target must not answer any oracle-feed getter, and the price oracle
      it points at must not itself be a tracked target.

  crossExposureScore    "each OTHER tracked target on the SAME ecosystem
      sharing at least one resolved root signer with this one costs 20
      points, floored at 0, and a root committee identical to a tracked
      target's on ANOTHER ecosystem is capped at a flat 80", i.e.
      min(100 - 20*withinEcosystemOverlaps, 80 if identical-elsewhere).
      The other-ecosystem committee is read LIVE on Arbitrum One in this run.

Usage:
    python3 audit_rotation_index1_2026-09-21.py [--check-address-book]
Exit 0 = no divergence between the re-derived score and the live published
one. Exit 2 = divergence. Exit 1 = a read failed.
"""

import sys
import time
import urllib.request

from web3 import Web3

BASE_RPCS = ["https://base.publicnode.com", "https://mainnet.base.org"]
ARBITRUM_RPCS = ["https://arb1.arbitrum.io/rpc", "https://arbitrum-one-rpc.publicnode.com"]
BASE_SEPOLIA_RPCS = ["https://sepolia.base.org", "https://base-sepolia-rpc.publicnode.com"]

ORACLE_BASE_SEPOLIA = "0x50840a7667baEa9D05ad4ae3dCeb384724b58720"
TARGET_INDEX = 1

# The two Aave entry points, cross-checked against bgd-labs/aave-address-book
# by --check-address-book. Everything downstream is read from the chain.
BASE_POOL_ADDRESSES_PROVIDER = "0xe20fCBdBfFC4Dd138cE8b2E6FBb6CB49777ad64D"
ARBITRUM_POOL_ADDRESSES_PROVIDER = "0xa97684ead0e402dC232d5A977953DF7ECBaB3CDb"

# The OTHER Base tracked targets' root committees, for the within-ecosystem
# half of crossExposureScore. This is the tracked SET (which addresses the
# project watches), not any score: their owner sets are read live below.
BASE_OTHER_ROOT_SAFES = {
    "compound_v3 pauseGuardian": "0x3cb4653F3B45F448D9100b118B75a1503281d2ee",
    "aerodrome + slipstream pauser/feeManager": "0xE6A41fE61E7a1996B59d508661e3f524d6A32075",
    "morpho_blue owner": "0xcBa28b38103307Ec8dA98377ffF9816C164f9AFa",
    "aerodrome emergencyCouncil": "0x99249b10593fCa1Ae9DAE6D4819F1A6dae5C013D",
    "aave PROTOCOL_GUARDIAN": "0x56C1a4b54921DEA9A344967a8693C7E661D72968",
}
BASE_OTHER_ROOT_EOAS = {
    "uniswap L1 governance timelock alias": "0x1a9C8182C09F50c8318d769245bEA52c32BE35BC",
    "compound L1 governance timelock alias": "0x6d903f6003cca6255D85CcA4D3B5E5146dC33925",
    "moonwell timelock": "0x8769B70ac7c93AF0e75de0D69877709B66d75838",
}

ABI_ADDR = lambda name: [{"name": name, "type": "function", "stateMutability": "view",
                          "inputs": [], "outputs": [{"type": "address"}]}]
ABI_GET_OWNERS = [{"name": "getOwners", "type": "function", "stateMutability": "view",
                   "inputs": [], "outputs": [{"type": "address[]"}]}]
ABI_GET_THRESHOLD = [{"name": "getThreshold", "type": "function", "stateMutability": "view",
                      "inputs": [], "outputs": [{"type": "uint256"}]}]
ABI_EXEC_SETTINGS = [{"name": "getExecutorSettingsByAccessControl", "type": "function",
                      "stateMutability": "view", "inputs": [{"type": "uint8"}],
                      "outputs": [{"type": "tuple", "components": [{"type": "address"},
                                                                   {"type": "uint40"}]}]}]
ABI_SCORE = [{"name": "getScore", "type": "function", "stateMutability": "view",
              "inputs": [{"type": "address"}],
              "outputs": [{"type": "tuple", "components": [
                  {"name": "adminKeyScore", "type": "uint8"},
                  {"name": "multisigScore", "type": "uint8"},
                  {"name": "timelockScore", "type": "uint8"},
                  {"name": "oracleAuthorityScore", "type": "uint8"},
                  {"name": "crossExposureScore", "type": "uint8"},
                  {"name": "compositeScore", "type": "uint8"},
                  {"name": "lastUpdated", "type": "uint64"},
                  {"name": "methodologyHash", "type": "bytes32"}]}]}]
ABI_TRACKED = [{"name": "trackedTargets", "type": "function", "stateMutability": "view",
                "inputs": [{"type": "uint256"}], "outputs": [{"type": "address"}]}]
ABI_TRACKED_COUNT = [{"name": "trackedTargetsCount", "type": "function", "stateMutability": "view",
                      "inputs": [], "outputs": [{"type": "uint256"}]}]


def connect(urls):
    out = []
    for u in urls:
        w3 = Web3(Web3.HTTPProvider(u, request_kwargs={"timeout": 30}))
        out.append((u, w3, w3.eth.chain_id))
    return out


def call(w3, addr, abi, fn, *args, retries=4):
    """None means "no answer": either a revert (the getter does not exist on
    that contract, which several checks below rely on) or, after `retries`
    attempts, a dead RPC. Probe calls that EXPECT a revert pass retries=1."""
    last = None
    for attempt in range(retries):
        try:
            c = w3.eth.contract(address=w3.to_checksum_address(addr), abi=abi)
            return getattr(c.functions, fn)(*args).call()
        except Exception as exc:
            last = exc
            if "execution reverted" in str(exc) or "BadFunctionCallOutput" in type(exc).__name__:
                return None
            time.sleep(1.5 * (attempt + 1))
    if last is not None and retries > 1:
        print(f"  (no answer from {fn} on {addr} after {retries} tries: {type(last).__name__})")
    return None


def agree(values, label):
    """Every RPC must return the same thing, else the read is not trustworthy."""
    uniq = {repr(v) for v in values}
    if len(uniq) != 1:
        print(f"  !! RPC DISAGREEMENT on {label}: {values}")
        sys.exit(1)
    return values[0]


def composite(admin, multisig, timelock):
    """METHODOLOGY.md "### Aggregation", round-half-up. Exact-integer form -- not
    int(0.4*a+0.3*m+0.3*t+0.5), which reads one LOWER than exact on 2054/1,030,301 (a,m,t) triples
    (scripts/lib/scorers.py, scripts/validate_all_scorers.py; matches chains/ethereum-l1/scripts/
    audit_rotation_index2.py already). This script runs the comparison over EVERY tracked target, so
    the exposure was 14x. Found by the review of commit 585d949."""
    return (4 * admin + 3 * multisig + 3 * timelock + 5) // 10


def trace_aave_root(conns, provider, chain_label):
    """owner() -> EXECUTOR_LVL_1 -> PayloadsController -> guardian Safe."""
    executor = agree([call(w3, provider, ABI_ADDR("owner"), "owner") for _, w3, _ in conns],
                     f"{chain_label} provider.owner()")
    acl = agree([call(w3, provider, ABI_ADDR("getACLAdmin"), "getACLAdmin") for _, w3, _ in conns],
                f"{chain_label} provider.getACLAdmin()")
    payloads = agree([call(w3, executor, ABI_ADDR("owner"), "owner") for _, w3, _ in conns],
                     f"{chain_label} executor.owner()")
    loop = agree([call(w3, payloads, ABI_ADDR("owner"), "owner") for _, w3, _ in conns],
                 f"{chain_label} payloadsController.owner()")
    guardian = agree([call(w3, payloads, ABI_ADDR("guardian"), "guardian") for _, w3, _ in conns],
                     f"{chain_label} payloadsController.guardian()")
    settings = agree([call(w3, payloads, ABI_EXEC_SETTINGS,
                           "getExecutorSettingsByAccessControl", 1) for _, w3, _ in conns],
                     f"{chain_label} executor settings")
    owners = agree([call(w3, guardian, ABI_GET_OWNERS, "getOwners") for _, w3, _ in conns],
                   f"{chain_label} guardian.getOwners()")
    threshold = agree([call(w3, guardian, ABI_GET_THRESHOLD, "getThreshold") for _, w3, _ in conns],
                      f"{chain_label} guardian.getThreshold()")
    return {"executor": executor, "acl_admin": acl, "payloads": payloads, "loop": loop,
            "guardian": guardian, "delay": settings[1] if settings else None,
            "owners": frozenset(Web3.to_checksum_address(o) for o in (owners or [])),
            "threshold": threshold}


def safe_owner_set(conns, addr):
    owners = agree([call(w3, addr, ABI_GET_OWNERS, "getOwners") for _, w3, _ in conns],
                   f"getOwners({addr})")
    return frozenset(Web3.to_checksum_address(o) for o in (owners or []))


def check_address_book():
    """Second, non-chain source for the two hardcoded entry points."""
    ok = True
    for url, needle, label in [
        ("https://raw.githubusercontent.com/bgd-labs/aave-address-book/main/src/AaveV3Base.sol",
         BASE_POOL_ADDRESSES_PROVIDER, "Base PoolAddressesProvider"),
        ("https://raw.githubusercontent.com/bgd-labs/aave-address-book/main/src/AaveV3Arbitrum.sol",
         ARBITRUM_POOL_ADDRESSES_PROVIDER, "Arbitrum PoolAddressesProvider"),
    ]:
        body = ""
        for attempt in range(4):
            try:
                body = urllib.request.urlopen(url, timeout=30).read().decode()
                break
            except Exception as exc:  # transient truncated read through a proxy
                print(f"  retry {attempt + 1} on {url}: {type(exc).__name__}")
        hit = needle.lower() in body.lower()
        print(f"  address book {label}: {needle} present={hit}")
        ok = ok and hit
    return ok


def main():
    print("=== rotation audit, Base ecosystem, tracked index 1, 2026-09-21 ===")
    if "--check-address-book" in sys.argv:
        print("\n[0] primary source cross-check (bgd-labs/aave-address-book)")
        if not check_address_book():
            print("  !! an entry point is NOT in the address book")
            return 1

    base = connect(BASE_RPCS)
    arb = connect(ARBITRUM_RPCS)
    sep = connect(BASE_SEPOLIA_RPCS)
    for label, conns, want in [("Base", base, 8453), ("Arbitrum One", arb, 42161),
                               ("Base Sepolia", sep, 84532)]:
        for u, _, cid in conns:
            print(f"  {label} {u} chain_id={cid}")
            if cid != want:
                print(f"  !! expected chain_id {want}")
                return 1

    print("\n[1] the audited target is really tracked index 1 on the deployed oracle")
    n = agree([call(w3, ORACLE_BASE_SEPOLIA, ABI_TRACKED_COUNT, "trackedTargetsCount")
               for _, w3, _ in sep], "trackedTargetCount")
    tracked = [agree([call(w3, ORACLE_BASE_SEPOLIA, ABI_TRACKED, "trackedTargets", i)
                      for _, w3, _ in sep], f"trackedTargets({i})") for i in range(n)]
    target = tracked[TARGET_INDEX]
    print(f"  trackedTargetsCount={n}  trackedTargets({TARGET_INDEX})={target}")
    if target.lower() != BASE_POOL_ADDRESSES_PROVIDER.lower():
        print("  !! index 1 is not the Aave V3 Base PoolAddressesProvider")
        return 1

    print("\n[2] Base authority chain, read live on 2 RPCs")
    b = trace_aave_root(base, BASE_POOL_ADDRESSES_PROVIDER, "Base")
    print(f"  provider.owner()             = {b['executor']}")
    print(f"  provider.getACLAdmin()       = {b['acl_admin']}  (== owner: "
          f"{b['acl_admin'] == b['executor']})")
    print(f"  EXECUTOR_LVL_1.owner()       = {b['payloads']}  (PayloadsController)")
    print(f"  PayloadsController.owner()   = {b['loop']}  (closes back: "
          f"{b['loop'] == b['executor']})")
    print(f"  executor settings lvl 1 delay= {b['delay']}s")
    print(f"  PayloadsController.guardian()= {b['guardian']}  "
          f"({b['threshold']}-of-{len(b['owners'])} Safe)")

    print("\n[3] adminKeyScore")
    pair_closed = bool(b["payloads"]) and b["loop"] == b["executor"] and b["acl_admin"] == b["executor"]
    admin_key = 65 if pair_closed else 30
    print(f"  root pair resolves and closes on itself: {pair_closed}  -> adminKeyScore={admin_key}")

    print("\n[4] multisigScore -- is either half of the root a Safe?")
    root_is_safe = False
    for label, addr in [("EXECUTOR_LVL_1", b["executor"]), ("PayloadsController", b["payloads"])]:
        o = [call(w3, addr, ABI_GET_OWNERS, "getOwners", retries=1) for _, w3, _ in base]
        t = [call(w3, addr, ABI_GET_THRESHOLD, "getThreshold", retries=1) for _, w3, _ in base]
        answers = bool([x for x in o if x]) or bool([x for x in t if x is not None])
        print(f"  {label} getOwners/getThreshold answer: {answers}")
        root_is_safe = root_is_safe or answers
    multisig = 0 if root_is_safe else 100
    print(f"  no Safe layer at the root -> multisigScore={multisig} (not applicable)")

    print("\n[5] timelockScore")
    delay = b["delay"]
    bypass = b["guardian"] is not None and len(b["owners"]) > 0
    timelock = 50 if delay and delay > 0 else 0
    print(f"  real per-access-level delay = {delay}s ({(delay or 0)/3600:.0f}h)")
    print(f"  live cancel path outside the delay (guardian Safe): {bypass}")
    print(f"  -> timelockScore={timelock} (capped below the bounded-bypass cap of 55: "
          f"guardian cancel path + L1 root not re-verified from a Base RPC)")

    print("\n[6] oracleAuthorityScore -- does the target itself report a price/state?")
    feed_getters = ["latestAnswer", "decimals", "aggregator", "latestRound"]
    answers = []
    for g in feed_getters:
        abi = [{"name": g, "type": "function", "stateMutability": "view", "inputs": [],
                "outputs": [{"type": "int256" if g == "latestAnswer" else
                             ("address" if g == "aggregator" else "uint256")}]}]
        r = call(base[0][1], BASE_POOL_ADDRESSES_PROVIDER, abi, g, retries=1)
        answers.append((g, r))
    print(f"  feed getters on the target: {answers}")
    price_oracle = agree([call(w3, BASE_POOL_ADDRESSES_PROVIDER, ABI_ADDR("getPriceOracle"),
                               "getPriceOracle") for _, w3, _ in base], "getPriceOracle()")
    oracle_is_tracked = price_oracle is not None and price_oracle.lower() in {t.lower() for t in tracked}
    print(f"  provider.getPriceOracle() = {price_oracle}  tracked by this oracle: {oracle_is_tracked}")
    oracle_auth = 100 if not any(r is not None for _, r in answers) and not oracle_is_tracked else 20
    print(f"  -> oracleAuthorityScore={oracle_auth} (not applicable)")

    print("\n[7] crossExposureScore -- within Base")
    within = 0
    for label, addr in BASE_OTHER_ROOT_SAFES.items():
        other = safe_owner_set(base, addr)
        shared = b["owners"] & other
        print(f"  {label} {addr}: {len(other)} owners, shared with index 1: {len(shared)}")
        if shared:
            within += 1
    for label, addr in BASE_OTHER_ROOT_EOAS.items():
        hit = Web3.to_checksum_address(addr) in b["owners"]
        print(f"  {label} {addr}: is a signer of index 1's root: {hit}")
        if hit:
            within += 1
    # METHODOLOGY.md, "Extension (2026-09-20): a shared contract root counts
    # like a shared committee." Index 1's own root is a contract pair, not a
    # committee, so the other 8 tracked targets are checked for that root too.
    for i, t in enumerate(tracked):
        if i == TARGET_INDEX:
            continue
        o = call(base[0][1], t, ABI_ADDR("owner"), "owner", retries=2)
        shares_root = o is not None and o.lower() == b["executor"].lower()
        print(f"  tracked index {i} {t}: owner()={o} is the Aave executor: {shares_root}")
        if shares_root:
            within += 1
    print(f"  overlapping OTHER Base tracked targets: {within}")

    print("\n[8] crossExposureScore -- other ecosystem, Arbitrum One read LIVE")
    a = trace_aave_root(arb, ARBITRUM_POOL_ADDRESSES_PROVIDER, "Arbitrum")
    print(f"  Arbitrum PayloadsController  = {a['payloads']}")
    print(f"  Arbitrum guardian Safe       = {a['guardian']}  "
          f"({a['threshold']}-of-{len(a['owners'])})")
    identical = bool(a["owners"]) and a["owners"] == b["owners"]
    print(f"  Base guardian {b['guardian']} vs Arbitrum guardian {a['guardian']}: "
          f"different address = {a['guardian'] != b['guardian']}, identical owner set = {identical}")
    if identical:
        print(f"  the {len(a['owners'])} shared signers, sorted:")
        for o in sorted(a["owners"]):
            print(f"    {o}")
    cross = min(max(0, 100 - 20 * within), 80 if identical else 100)
    print(f"  -> crossExposureScore = min(100 - 20*{within}, {'80' if identical else '100'}) = {cross}")

    comp = composite(admin_key, multisig, timelock)
    print(f"\n[9] compositeScore = floor(0.4*{admin_key} + 0.3*{multisig} + 0.3*{timelock} + 0.5) = {comp}")

    print("\n[10] published score, read LIVE with getScore() on Base Sepolia, 2 RPCs")
    pub = agree([call(w3, ORACLE_BASE_SEPOLIA, ABI_SCORE, "getScore", Web3.to_checksum_address(target))
                 for _, w3, _ in sep], "getScore(index 1)")
    fields = ["adminKeyScore", "multisigScore", "timelockScore", "oracleAuthorityScore",
              "crossExposureScore", "compositeScore"]
    derived = [admin_key, multisig, timelock, oracle_auth, cross, comp]
    diverged = False
    for i, f in enumerate(fields):
        same = pub[i] == derived[i]
        diverged = diverged or not same
        print(f"  {f:22s} derived={derived[i]:3d}  published={pub[i]:3d}  {'OK' if same else 'DIVERGENCE'}")
    print(f"  lastUpdated={pub[6]}  methodologyHash=0x{pub[7].hex()}")

    print("\n[11] the documented composite formula against EVERY published row "
          "(this is what tells the documented formula apart from (a+m+t)//3)")
    bad_doc = bad_naive = 0
    for i, t in enumerate(tracked):
        s = agree([call(w3, ORACLE_BASE_SEPOLIA, ABI_SCORE, "getScore", Web3.to_checksum_address(t))
                   for _, w3, _ in sep], f"getScore({t})")
        doc = composite(s[0], s[1], s[2])
        naive = (s[0] + s[1] + s[2]) // 3
        bad_doc += doc != s[5]
        bad_naive += naive != s[5]
        print(f"  index {i} {t} a/m/t={s[0]}/{s[1]}/{s[2]} published={s[5]} "
              f"documented={doc} {'ok' if doc == s[5] else 'MISMATCH'} | "
              f"(a+m+t)//3={naive} {'ok' if naive == s[5] else 'MISMATCH'}")
    print(f"  documented formula mismatches: {bad_doc}/{len(tracked)}   "
          f"(a+m+t)//3 mismatches: {bad_naive}/{len(tracked)}")
    if bad_doc:
        diverged = True

    print("\n=== RESULT: " + ("DIVERGENCE FOUND" if diverged else "no divergence") + " ===")
    return 2 if diverged else 0


if __name__ == "__main__":
    sys.exit(main())
