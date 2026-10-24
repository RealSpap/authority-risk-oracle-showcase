#!/bin/bash
# Redo it: the score of the Pendle V2 Router on Ethereum L1, from public reads only (no key, no account, no transaction).
# Needs Foundry (https://getfoundry.sh) for `cast`. Any public Ethereum RPC works; set ETH_RPC / SEPOLIA_RPC to change them.
# Last line: VERDICT: MATCH when the reads end at one Safe AND the recomputed scores equal the published ones.
set -u
ETH_RPC="${ETH_RPC:-https://ethereum-rpc.publicnode.com}"; SEPOLIA_RPC="${SEPOLIA_RPC:-https://ethereum-sepolia-rpc.publicnode.com}"
ORACLE=0xB6F8474ccC71AF477c31c2DF663B3942ddfbf906           # Authority Risk Oracle, Ethereum L1 (Sepolia testnet)
ROUTER=0x888888888889758F76e7103c6CbF23ABbF58F946           # the target: Pendle V2 Router on Ethereum mainnet
SAFE="${SAFE:-0x8119EC16F0573B7dAc7C0CB94EB504FB32456ee1}"  # the Safe we expect at the root
MARKET_FACTORY=0x6d247b1c044fA1E22e6B04fA9F71Baf99EB29A9f; YIELD_FACTORY=0x3E6EBa46AbC5ab18ED95F6667d8B2fd4020E4637
TIMELOCK=0x68d8D192dF476bC01895E16b0ED3945673d777AC; GOV_PROXY=0x2aD631F72fB16d91c4953A7f4260A97C2fE2f31e; DEPLOYER=0x1FcCC097db89A86Bfc474A1028F93958295b1Fb7
ZERO32=0x0000000000000000000000000000000000000000000000000000000000000000
c() { cast call "$@" --rpc-url "$ETH_RPC"; }
low() { echo "$1" | tr 'A-F' 'a-f'; }
echo "1. The published score (oracle on Sepolia): admin, multisig, timelock, oracle-authority, cross-exposure, composite"
PUB=$(cast call $ORACLE 'getScore(address)(uint8,uint8,uint8,uint8,uint8,uint8,uint64,bytes32)' $ROUTER --rpc-url "$SEPOLIA_RPC" | awk 'NR<=6 {print $1}' | tr '\n' ' '); echo "   $PUB"
echo "2. Four paths that must all end at ONE Safe ($SAFE)"
RO=$(c $ROUTER 'owner()(address)'); PO=$(c $ROUTER 'pendingOwner()(address)'); PA=$(cast admin $MARKET_FACTORY --rpc-url "$ETH_RPC"); PAO=$(c "$PA" 'owner()(address)')
YO=$(c $YIELD_FACTORY 'owner()(address)'); MO=$(c $MARKET_FACTORY 'owner()(address)'); GS=$(c $GOV_PROXY 'hasRole(bytes32,address)(bool)' $ZERO32 $SAFE); GD=$(c $GOV_PROXY 'hasRole(bytes32,address)(bool)' $ZERO32 $DEPLOYER)
echo "   Router.owner()                 = $RO"
echo "   Router.pendingOwner()          = $PO   (zero: no transfer in flight)"
echo "   MarketFactory proxy admin      = $PA"
echo "   ProxyAdmin.owner()             = $PAO"
echo "   YieldFactory.owner()           = $YO"
echo "   MarketFactory.owner()          = $MO   (must be the governance proxy $GOV_PROXY)"
echo "   governance proxy: Safe is DEFAULT_ADMIN?     $GS"
echo "   governance proxy: deployer is DEFAULT_ADMIN? $GD   (must be false)"
CONV=no
[ "$(low "$RO")" = "$(low "$SAFE")" ] && [ "$(low "$PAO")" = "$(low "$SAFE")" ] && [ "$(low "$YO")" = "$(low "$SAFE")" ] && [ "$(low "$MO")" = "$(low "$GOV_PROXY")" ] && [ "$GS" = true ] && [ "$GD" = false ] && [ "$PO" = 0x0000000000000000000000000000000000000000 ] && CONV=yes
echo "   the four paths end at the Safe: $CONV"
echo "3. The Safe"
T=$(c "$SAFE" 'getThreshold()(uint256)' 2>/dev/null | awk '{print $1}'); N=$(c "$SAFE" 'getOwners()(address[])' 2>/dev/null | grep -o '0x[0-9a-fA-F]\{40\}' | wc -l | tr -d ' ')
echo "   threshold = ${T:-unread}, owners = $N, version = $(c "$SAFE" 'VERSION()(string)' 2>/dev/null), modules = $(c "$SAFE" 'getModulesPaginated(address,uint256)(address[],address)' 0x0000000000000000000000000000000000000001 10 2>/dev/null | head -1)"
echo "   singleton (slot 0) = $(cast storage "$SAFE" 0 --rpc-url "$ETH_RPC" 2>/dev/null)   (the published Safe v1.4.1 singleton ends in 5c7461a)"
echo "4. The rule applied to what was read (Safe rule of chains/ethereum-l1/scorers.py, score_convex_finance_booster; multisig formula in METHODOLOGY.md):"
echo "   admin = 65 if threshold >= 3, 50 if 2, else 10; multisig = min(100, 15t + 5(n - t)); timelock = 0 when no path read above goes through a delay"
if [ -n "${T:-}" ] && [ "$CONV" = yes ]; then
  ADMIN=$([ "$T" -ge 3 ] && echo 65 || ([ "$T" -eq 2 ] && echo 50 || echo 10)); MS=$(( 15*T + 5*(N-T) )); [ $MS -gt 100 ] && MS=100; TL=0
  COMP=$(( (40*ADMIN + 30*MS + 30*TL + 50) / 100 ))
  echo "   admin = $ADMIN, multisig = $MS, timelock = $TL  ->  composite = floor(0.4*$ADMIN + 0.3*$MS + 0.3*$TL + 0.5) = $COMP"
  MINE="$ADMIN $MS $TL"; THEIRS=$(echo $PUB | awk '{print $1, $2, $3}'); PUBCOMP=$(echo $PUB | awk '{print $6}')
else MINE="not computed (the paths do not end at one Safe, or the Safe was not read)"; THEIRS=""; COMP=""; PUBCOMP=""; echo "   $MINE"; fi
echo "5. A timelock exists but is on none of the paths above, so it is not credited: TimelockController $TIMELOCK getMinDelay() = $(c $TIMELOCK 'getMinDelay()(uint256)' | awk '{print $1}') s"
echo "   Oracle-authority (100) and cross-exposure (80) are read from the oracle in step 1 and are not recomputed here."
if [ "$CONV" = yes ] && [ "$MINE" = "$THEIRS" ] && [ "$COMP" = "$PUBCOMP" ]; then echo "VERDICT: MATCH (admin/multisig/timelock = $MINE, composite = $COMP, as published)"; exit 0
else echo "VERDICT: NO MATCH (recomputed: ${MINE}${COMP:+, composite $COMP}; published: ${THEIRS}${PUBCOMP:+, composite $PUBCOMP}; paths end at the Safe: $CONV)"; exit 1; fi
