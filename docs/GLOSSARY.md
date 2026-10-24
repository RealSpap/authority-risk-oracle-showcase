# Glossary

Terms of the Authority Risk Oracle and of its method. Each definition points to the document it comes from.

**Admin key score.** Who can act as the contract's ultimate authority, and how hard that authority is to compromise or coerce.
Source: METHODOLOGY.md

**Band.** The label of a composite: critical 0 to 19, weak 20 to 39, moderate 40 to 59, decent 60 to 79, strong 80 to 100.
Source: /oracle/api/

**Composite score.** The single 0 to 100 number published for a target: 40 percent admin key, 30 percent multisig, 30 percent timelock, rounded half up. The price-path and shared-control scores sit beside it and do not change it.
Source: METHODOLOGY.md

**EIP-1967 admin slot.** The EIP-1967 standard storage position where a proxy keeps the address of its admin; reading it traces who controls an upgradeable contract.
Source: METHODOLOGY.md and https://eips.ethereum.org/EIPS/eip-1967

**EOA.** An EOA, an externally owned account: a single key with no contract code. As the root of a target's authority it is the near-worst case.
Source: METHODOLOGY.md

**Hash-chained event log.** A hash-chained event log: the Watch's log in which each line carries the sha256 of the previous one, so a rewrite shows; its head is signed every six hours.
Source: /oracle/provenance/

**Method hash.** The hash published with each push that ties a score to the exact code that produced it (methodologyHash).
Source: METHODOLOGY.md

**Multisig score.** How strong a multisig authority is, from its threshold and signer count: min(100, threshold * 15 + max(0, ownerCount - threshold) * 5) in the general case.
Source: METHODOLOGY.md

**Not applicable scores 100.** A dimension that does not apply to a target scores 100, full marks, and is not treated as a weakness. A project-wide convention.
Source: METHODOLOGY.md

**Oracle authority score.** Who can change the prices a target reports or relies on; 100 when it does not apply. Published beside the composite, not folded into it.
Source: METHODOLOGY.md

**Pre-registered backtest.** A pre-registered backtest: a test written before the data were read. Victims of incidents and untouched peers of similar size are read one month before each incident, and the composite is checked for whether it separated them.
Source: METHODOLOGY.md

**Safe.** A multisig contract (Gnosis Safe or a bespoke equivalent) whose owners and threshold decide who can act; scored better than a single key.
Source: METHODOLOGY.md

**Safe module.** An add-on that executes as the Safe without the owners' signatures, so a Safe with an unanalyzed module is not scored from its threshold by itself.
Source: METHODOLOGY.md

**Shared-control score.** Whether a target's root authority also controls another tracked target; a shared compromised key becomes a systemic risk. Called crossExposureScore in the data.
Source: METHODOLOGY.md

**Sub-score.** One of the five dimension scores of a target, each from 0 to 100 ("higher is safer" in the words of METHODOLOGY.md).
Source: METHODOLOGY.md

**Target.** In this glossary, a deployed contract, program or account that the oracle scores.
Source: our own gloss; METHODOLOGY.md uses the word without defining it.

**Timelock score.** Whether a real, enforced delay sits between an authority action being queued and taking effect; 0 if no delay mechanism covers the action.
Source: METHODOLOGY.md

**Unresolved authority.** A real contract exists but its controller was not traced this pass: scored 20 as an explicit "unknown, not assumed safe" placeholder.
Source: METHODOLOGY.md

**Upgrade executed.** A Watch alert: the implementation behind a tracked contract changed since the previous run.
Source: /oracle/watch/

**Watch.** The public monitor of the oracles: it re-reads every 6 hours and publishes what it read as public files anyone can read.
Source: /oracle/watch/
