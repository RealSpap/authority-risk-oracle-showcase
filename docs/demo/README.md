# Technical demo: a refusal you can replay

Before anyone signs, can a rule tell who can change a contract, with how much notice, and what it could not read? This folder answers on your own machine, in about three seconds, on a private local chain with made-up contracts. No network write, no real key, no real contract.

## Run it

You need [Foundry](https://getfoundry.sh) (`anvil`, `forge`, `cast`) and `python3`. On a machine that has not yet compiled with Solidity 0.8.24, `forge` downloads that compiler: that is a network read (nothing is written to any chain or server), and after it the demo needs no network. From this folder:

```
bash demo.sh
```

What happens, in order:

1. `anvil` starts a private chain on port 18545 (set `DEMO_PORT` to use another port; the script stops with a clear message if its own chain cannot start there; the chain's public test accounts hold nothing real) and three made-up contracts are deployed: A (3 signers must agree, out of 5, with 48 hours of notice), B (1 of 5, no notice) and C (it answers none of the three questions).
2. `reader.py` reads three numbers from each contract with `eth_call` and applies the written rule in `rule.json`. Three different answers:
   - A: `ALLOWED BY THE RULE` (the rule allows this; it does not say the target is safe).
   - B: `REFUSED`, with the reasons: `R2 SMALL MULTISIG: 1 of 5 is below 3 of 5` and `R3 NO NOTICE: 0.0 hours is below 48 hours`.
   - C: `CANNOT KNOW`. It is neither allowed nor refused: the rule cannot answer, and the output lists what is missing (`threshold()`, `ownerCount()` and `minDelay()` each ended in `execution reverted`).
3. `make_lock.py` writes a small lock from A (a copy of the result of a fresh run, `authority.lock`, is in this folder): what its owner expects (3 of 5, 48 hours). `authority_lock_check.py` compares it with what the chain says now: `GREEN MATCHES`.
4. A is weakened with two real transactions from the anvil test account: `setThreshold(1)` and `setMinDelay(0)`. No storage slot is written by hand.
5. The same lock now prints `RED   CHANGED` with the exact difference: `number of signers needed was 3 when the lock was written, now 1; notice period (hours) was 48.0 when the lock was written, now 0.0`. A second lock, which expects C to be readable, prints `RED   NOT READ`.
6. The script prints the time measured in milliseconds.

Timing is measured in milliseconds by the script. Runs on one machine printed between about 0.2 and 0.3 seconds from the confirmed weakening to the red lock: about a quarter of a second, and it varies from run to run.

## Replay it

Run the same command again: `bash demo.sh`. The chain is rebuilt the same way, so the addresses and block numbers are the same, and each answer prints the block it read and a `cast call ... --block N` command that reads the same number again while the chain is up. The chain stops when the script ends, so those commands work while it runs and not after; to replay, run the script again. To replay the published readings of the repository, which is a separate check, run `python3 scripts/prove.py` at the repository root.

## The written rule

`rule.json` has three lines of rule. R1: a number that cannot be read gives `CANNOT KNOW`, which is not a pass and not a silent refusal. R2: fewer than 3 signers required, or fewer than 5 owners, is a refusal. R3: a notice period shorter than 48 hours is a refusal. The thresholds are an example written for this demo. They are not a standard and not a score. The rule is written once; this demo runs it on a local EVM chain.

Try R1 without any chain: `python3 -I reader.py --rpc http://127.0.0.1:1 --target 0x0000000000000000000000000000000000000001` cannot reach anything, prints `CANNOT KNOW` and exits with code 2.

## What this is not

- The reader does not check that a target is a multisig. `DemoAuthority` is not one: it stores just three numbers, and the demo says so. The three numbers are three separate `eth_call` requests at the same block number, not one atomic read of a real multisig.
- It is the reader and the lock check on a local chain. It is not the Watch, which reads the tracked contracts every 6 hours, and it blocks no transaction.
- The contracts are made up and the setters can be called by anyone. On a real chain, weakening a multisig needs valid signatures from its signers.
- The lock check is a local script that a CI job could run; none is set up here. The checker and the lock file in this folder are examples written for this demo.
- No agent runs: a short script stands in for the rule, and no wallet is involved.
- The reader is a short independent script. It is not the code that computes the published scores.
- The time is a local measurement. It says nothing about the delay on a real chain.
- "Allowed" does not mean safe. "Refused" does not say that someone is attacking. "Cannot know" is not an alert.

## Files

- `demo.sh`: the one command.
- `reader.py`: reads three numbers and applies the rule (Python standard library, no other package).
- `rule.json`: the written rule.
- `make_lock.py`, `authority_lock_check.py`: write a lock and compare it with a reading. `authority.lock`: the lock for the made-up contract A of a fresh run.
- `src/DemoAuthority.sol`, `foundry.toml`: the made-up contracts.
