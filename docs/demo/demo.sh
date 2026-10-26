#!/bin/bash
# 60-second demo, one command: bash demo.sh     Needs foundry (anvil, forge, cast) and python3. Private local chain only: no network write, no real key, no real contract.
# 1. start a private chain (anvil, test accounts)  2. deploy three made-up contracts: A (3 of 5 signers, 48 hours of notice), B (1 of 5, no notice), C (answers nothing)
# 3. the reader answers three ways: A allowed, B refused with the reasons, C cannot know and says what is missing
# 4. write a lock from A, check it (green)  5. weaken A with two real calls (setThreshold(1), setMinDelay(0))  6. the lock check turns red and prints the exact difference; a lock that expects C to be readable fails too
# 7. print the time measured in milliseconds (python time.time; the clock stamps use `date`) and the way to replay it: this same command.
# First run on a machine without the Solidity compiler 0.8.24: forge downloads it (a network READ, no write); after that the demo needs no network.
export LC_ALL=C
set -u
H="$(cd "$(dirname "$0")" && pwd)"; PORT="${DEMO_PORT:-18545}"; RPC="http://127.0.0.1:$PORT"; FROM=0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266   # anvil's test account 0 (public, holds nothing real)
W="${TMPDIR:-/tmp}/aro-demo.$$"; mkdir -p "$W"
ms() { python3 -I -c 'import time; print(int(time.time() * 1000))'; }
anvil --port "$PORT" --silent --accounts 3 > "$W/anvil.txt" 2>&1 & AP=$!
trap 'kill $AP 2>/dev/null; rm -rf "$W"' EXIT
for i in $(seq 1 50); do curl -s -m 1 -X POST "$RPC" -H 'content-type: application/json' -d '{"jsonrpc":"2.0","id":1,"method":"eth_chainId","params":[]}' >/dev/null 2>&1 && break; sleep 0.2; done
sleep 0.5   # an anvil that cannot take the port exits at once: check that OUR anvil is the one that answers
kill -0 "$AP" 2>/dev/null || { echo "STOP: the private chain did not start on port $PORT (is something else using it? set DEMO_PORT to use another port)."; exit 3; }
deploy() { ( cd "$H" && forge create "$1" --rpc-url "$RPC" --unlocked --from "$FROM" --broadcast --out "$W/out" --cache-path "$W/cache" ${2:+--constructor-args $2} 2>&1 | awk '/Deployed to:/ {print $3}' ); }
A=$(deploy src/DemoAuthority.sol:DemoAuthority "3 5 172800"); B=$(deploy src/DemoAuthority.sol:DemoAuthority "1 5 0"); C=$(deploy src/DemoAuthority.sol:DemoOpaque)
[ -n "$A" ] && [ -n "$B" ] && [ -n "$C" ] || { echo "STOP: the made-up contracts were not deployed (is foundry installed?)"; exit 3; }
say() { echo; echo "$(date '+%H:%M:%S')  $*"; }
say "chain: anvil on $RPC (private, local). Three made-up contracts: A $A, B $B, C $C"
say "QUESTION: before anyone signs, can a rule tell who can change a contract, with how much notice, and what it could not read? (A short script stands in for the rule; no agent runs and no wallet is involved.)"
say "STATE 1, contract A (3 of 5 signers, 48 hours of notice)"; python3 -I "$H/reader.py" --rpc "$RPC" --target "$A" --json "$W/a.json"; RA=$?
say "STATE 2, contract B (1 of 5 signers, no notice)"; python3 -I "$H/reader.py" --rpc "$RPC" --target "$B"; RB=$?
say "STATE 3, contract C (it answers none of the three questions)"; python3 -I "$H/reader.py" --rpc "$RPC" --target "$C" --json "$W/c.json"; RC=$?
say "LOCK: write what the owner expects for A, then check it against what the chain says now"
python3 -I "$H/make_lock.py" --label "Contract A (made up)" --address "$A" --threshold 3 --owners 5 --delay-hours 48 --out "$W/a.lock"
python3 -I "$H/authority_lock_check.py" "$W/a.lock" "$W/a.json"; L1=$?
T0=$(ms); say "WEAKEN A: two real calls from anvil's test account, 3 of 5 becomes 1 of 5 and 48 hours becomes 0"
cast send --unlocked --from "$FROM" --rpc-url "$RPC" "$A" "setThreshold(uint256)" 1 >/dev/null || exit 3
cast send --unlocked --from "$FROM" --rpc-url "$RPC" "$A" "setMinDelay(uint256)" 0 >/dev/null || exit 3
T1=$(ms); say "both calls confirmed"
say "LOCK again: read A now, check the same lock"
python3 -I "$H/reader.py" --rpc "$RPC" --target "$A" --json "$W/a2.json" > "$W/a2.txt"; RA2=$?; cat "$W/a2.txt"
python3 -I "$H/authority_lock_check.py" "$W/a.lock" "$W/a2.json"; L2=$?
T2=$(ms)
say "LOCK for C: the owner expects C to be readable (3 of 5, 48 hours)"
python3 -I "$H/make_lock.py" --label "Contract C (made up)" --address "$C" --threshold 3 --owners 5 --delay-hours 48 --out "$W/c.lock"
python3 -I "$H/authority_lock_check.py" "$W/c.lock" "$W/c.json"; L3=$?
say "done"
echo "measured in milliseconds on this machine (it varies from run to run): $((T1 - T0)) ms to weaken, $((T2 - T1)) ms from the confirmed weakening to the red lock printed, $((T2 - T0)) ms in all."
echo "Replay this refusal: run the same command again, bash demo.sh. The chain is rebuilt the same way; each answer above prints the block it read and a cast command to read the same numbers again (the chain stops when the script ends, so these commands work only while it is up)."
echo "Limits: this is the reader and the lock check on a private local chain with made-up contracts. It is not the Watch (which reads every 6 hours) and it blocks no transaction; the lock check is a local script that a CI job could run, none is set up here. The rule (R1 to R3) is an example, written once, and the demo runs on a local EVM chain only."
[ "$RA" = 0 ] && [ "$RB" = 1 ] && [ "$RC" = 2 ] && [ "$L1" = 0 ] && [ "$RA2" = 1 ] && [ "$L2" = 1 ] && [ "$L3" = 1 ] && { echo "DEMO OK: A allowed, B refused, C cannot know; the lock turned red after the weakening."; exit 0; }
echo "DEMO NOT AS EXPECTED: A=$RA (0) B=$RB (1) C=$RC (2) lock1=$L1 (0) A-after=$RA2 (1) lock2=$L2 (1) lockC=$L3 (1)"; exit 1
