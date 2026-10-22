# Control week #1 (11 to 18 Oct 2026)

1. Robinhood Chain (mainnet, chain 4663): the proxy 0x14b107cf534239c59571b066cb6497a321da897c (the Watch matches it to Arcus Perps on DefiLlama) now points to implementation 0x71fc...6319; it pointed to 0x44c6...bf78 before. Changed in block 89453534 on 15 Oct, 18:52 UTC, tx 0x39f23e30ae4ce4605f2c1976ec507f170a2db5b1e8aaef1587c333f606e573f0. It went through a 1-day timelock and was executed 5 seconds after it became executable.

Redo it:

```
for b in 89453533 89453534; do cast storage 0x14b107cf534239c59571b066cb6497a321da897c 0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc --block $b --rpc-url https://robinhood.drpc.org; done
```

(This public archive RPC sometimes answers "Unknown state"; run it again.)

Redo it (the timelock's delay):

```
cast call 0x0da180b14721ce46a83669b4816cb652caa1001d 'getMinDelay()(uint256)' --rpc-url https://robinhood.drpc.org
```

(prints 86400, that is 1 day in seconds)

2. No timelock score moved this week in the Watch's public event log (the 6 such moves on file are from 10 Oct). This is the Watch's score, not a direct read of each delay.

Redo it:

```
curl -s https://raw.githubusercontent.com/RealSpap/authority-risk-oracle-showcase/watch-data/events.jsonl | grep '"field": "timelockScore"' | grep -c -E '"run_utc": "2026-10-1[1-8]'
```

(prints 0)

Limit: this is a selection of the changes the Watch logged this week, not all of them. The Watch reads 202 contracts on 9 chains every 6 hours, so it does not see the whole week either. A change like this can be a normal event.

Question: if you work on one of these contracts and I read it wrong, where would you want me to look?
