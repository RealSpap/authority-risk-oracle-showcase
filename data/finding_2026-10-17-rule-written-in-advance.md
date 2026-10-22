# A rule written in advance from 2 incidents, then tested on the rest (17 Oct 2026)

I wrote a rule from just two incidents, froze it, and tested it on the 55 incidents of the Backtest page of this site: the 7 about who controls a contract (which include the two origin cases) and the 48 others. The two origin cases are Term Finance (a governance proposal executed 6 days 1 hour after it was submitted, with one voter) and AFX Bridge (5 of 7 validators signed a fraudulent withdrawal, and I could not find the required threshold written anywhere).

The rule flags an incident if R1 or R2 holds. R1 covers a delayed authority (governance, timelock, queue): the delay between proposal and execution is under 604,800 seconds (7 days; the frozen file says queue or proposal, and I measured from the proposal), no veto was exercised, and exactly one distinct address voted for the proposal before it was executed. R2 covers an authority of signers (multisig, validators, signing oracle): the minimum number of signatures required is not written anywhere readable (verified code, ABI, project documentation or an on-chain read), and fewer valid signatures authorised the action than there are authorised signers.

An incident where neither path was used (a code bug, a price manipulation, a single key) is not applicable and is not flagged. An incident that used one of the paths but where a needed field cannot be read is not evaluable: not flagged, and counted apart, never as a zero. The choices are arbitrary and were stated in advance: 7 days is the smallest round number above 6 days 1 hour, and each branch is fitted to one incident, so over-fitting is built in. The test measures exactly that.

The success threshold was written before the test: at least 4 of the 7 flagged, and at most 5 false alarms among the 48 others. I froze the rule on 17 Oct 2026 at 19:59:15 Geneva time (17:59:15 UTC). The SHA-256 of the rule file is 2fdd097fff00275fd707cf72f5c0d9586e92103f7518f45f535349d63851fc74. The rule is summarised here, not copied. The frozen file is in French and dated; it is not on the site, but I can send it on request, and a copy must match this hash (if you receive it, `openssl dgst -sha256 REGLE.md` must print the value above; some versions of openssl put a prefix in front). The hash does not prove when the file was written. It only commits me to one file. The order, rule before data, rests on my word and on my working log, not on the hash. I opened the Backtest page at 19:59:32 and its incident file at 20:00:01.

Correction, 19 October 2026: the frozen rule file for test 5 gave the Term Finance delay as 525,612 seconds; the correct value is 522,012 seconds (6 days 1 hour 12 seconds); both values are below the 604,800-second (seven-day) threshold, so the verdict is unchanged, and the sha256 of the rule file is unchanged.

Result: the test failed, and this page reports a failure on purpose. 2 of the 7 were flagged, and those 2 are Term Finance and AFX Bridge, flagged by construction because the rule was written from them. Outside the origin pair, 0 of 5. Drift and Ostium are not evaluable (the write-ups do not give the required threshold, or the number of signers). Fetch.ai / NuNet is not applicable (one key signs). BarnBridge is not flagged (its shortest delay was 7 days 5 minutes). Virtue is not flagged (all 14 signers signed). The threshold of 4 was not reached.

Among the 48 others there were 0 false alarms, under the limit of 5, but that 0 says little: 43 of the 48 are not applicable, 3 are not evaluable and just 2 were evaluated and not flagged. On the cases with a signer path outside the origin pair, the rule flagged nothing.

One classification changed after the initial result. Coinsbuy, a hot-wallet theft whose write-up says the official statement withholds the mechanism, was at first counted as not applicable. That label needs the write-up to show that neither path was used, and it does not, so I moved it to not evaluable. Before: 44 not applicable, 2 not evaluable, 2 evaluated and not flagged. After: 43, 3 and 2. Nothing was flagged either way.

Limits. The freeze holds for the day of 17 Oct: before that day I had already seen a numeric summary of the index of the postmortems repository (56 entries) and about twenty incident folder names (14 Oct), and on 15 Oct I had seen other folder names and learned that the write-ups of Term Finance, Fetch.ai / NuNet and Ostium, three of the 7, had been corrected after the oracle's own backtest. I did not use that to set the thresholds, but I cannot prove it did not influence me. One reader (me) filled every field from the write-ups, not from the chain, and 21 of the not applicable incidents were classed by a keyword sweep, so a path described in other words (council, admin key, committee) may have escaped me. Other readings change nothing in the outcome: if every unknown field made an incident not evaluable, BarnBridge would move from not flagged to not evaluable; if a threshold I could not read were treated as not written, Drift would be flagged, which gives 3 of 7, still under 4.

This shows that a rule fitted on two incidents did not carry over to the other cases I could read. It does not show that no such rule can work, and it says nothing about the six requirements the oracle publishes.

Redo it (the incident file, and the write-ups of the two origin cases at the commit I used):

```
curl -s https://realspap.github.io/oracle/backtest/incidents.json | openssl dgst -sha256
```

(prints 74aae1def019fa014658962f821c4f203901a4dcaec6fd318dd5037b9dc249a1, as long as the file has not changed since 17 Oct; some versions of openssl put a prefix such as "SHA2-256(stdin)= " in front)

```
curl -s https://realspap.github.io/oracle/backtest/incidents.json | python3 -c 'import json,sys; d=json.load(sys.stdin); print(len(d["incidents"]), len(d["in_scope"]), len(d["incidents"])-len(d["in_scope"]))'
```

(prints 55 7 48, as long as the file has not changed since 17 Oct)

```
for d in termfinance-metavault-governance afx-bridge-validator-key-compromise; do curl -s https://raw.githubusercontent.com/RealSpap/onchain-postmortems/f278ca56a42a51797ea952ffa4ca958136a94045/$d/README.md | openssl md5; done
```

(prints 0c1943796d63d78aba3ca2c847a29529 then 7dc000220d70dfc4e5e237f94d4de869; some versions of openssl put "MD5(stdin)= " in front)

What you cannot redo from this page: applying the rule to the 53 other write-ups. They are public at that commit, so you can read them and apply the rule yourself. My field-by-field readings, the script and the rule file are not on the site; I can send them on request, best effort, with no promised delay. The erratum is included in this note.

Question: if you froze a rule written on two incidents, what would you test it on?
