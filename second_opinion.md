## Second opinion, 2026-11-15T13:34:47Z

### 2 upgrade(s) executed since the previous run (2026-11-15T07:26:35Z)

- **SPoo1Ku8WFXoNDMHPsrGSTSG1Y47rzgn41SLUNakuHy** on solana: program redeployed since the previous run: slot 429882117 -> 469669929 (2026-11-15T08:54:43Z); the score reads who may upgrade, this is an upgrade that happened
- **Jito4APyf642JPZPx3hGc6WWJ8zPKtRbRs4P815Awbb** on solana: program redeployed since the previous run: slot 429882117 -> 469669929 (2026-11-15T08:54:43Z); the score reads who may upgrade, this is an upgrade that happened

The code behind a tracked proxy changed: read what the new implementation does before trusting the score (the private pipeline's implementation check names the selectors added and dropped).

### 1 disagreement(s) with the published score

- **0xa9c251f8304b1b3fc2b9e8fcae78d94eff82ac66** on plasma: the timelock score says no delay (0), the contract enforces its own timelock of 24 h (timelock())

An independent reader (scripts/second_opinion.py); review the case, the scorer may look at a different role than the proxy admin.
