# Authority Facts: specification v0.1 (draft)

A plain, verifiable disclosure of one thing about a DeFi contract: **who can move the money, how many of them, and how long everyone else has to react.** One label per contract, readable by a beginner, re-derivable by anyone from public chain reads.

Version 0.1, 15 October 2026. Status: draft for comment. Licence of this text: CC0. Reference implementation: Authority Risk Oracle (this repository). Nothing here is an audit, a rating of a company or investment advice.

Contents: 1 Why a format · 2 The label · 3 The machine-readable twin · 4 Independence rules · 5 Conformance · 6 Crosswalk · 7 What is not in v0.1 · 8 Versioning and governance. How to check a label: [`docs/CONFORMANCE.md`](CONFORMANCE.md). A 14-line way to use one: [`integrations/authority_facts_gate.py`](../integrations/authority_facts_gate.py).

## 1. Why a format

Regulators ask for disclosures that are "accurate, comprehensive, non-technical where appropriate" and ask authorities to identify the persons who hold control, administrative keys included (IOSCO, final report on DeFi, December 2023, recommendations on Responsible Persons and on disclosure). They do not say what the disclosure looks like. Frameworks that grade decentralisation exist (DeFiScan's stages and five risk dimensions, L2BEAT's Stages for rollups), and on-chain building blocks are being proposed (SOAC and ERC-8089 on Ethereum Magicians). What is missing is a short, standard, end-user label that anyone can recompute. This document defines one.

## 2. The label

A label has a fixed set of lines. A line that cannot be read is shown as **not read**, never as zero (a failed call is not a measurement). A contract whose score itself could not be read has no label at all: the score, its three readings and the freshness flag are therefore required fields; the other lines may be `null`.

| Line | Field | Definition | How to verify |
|---|---|---|---|
| Score | `composite` | `floor((4a + 3m + 3t + 5) / 10)` where a, m, t are the admin-key, multisig and timelock readings, each 0 to 100 (40% / 30% / 30%, rounded). Bands: critical 0-19, weak 20-39, moderate 40-59, decent 60-79, strong 80-100. | `reproduce` in the contract's JSON twin |
| Keys to move | `keys_to_move` | The fewest distinct signatures that can change or move the contract: 1 for a plain key; the threshold for a Safe or Squads multisig; for a nested 1-of-N routing Safe, the cheapest owner route. `null` when the keys sit behind a timelock or the holder is not read. | `independent_read_reproduce` |
| Hours to react | `react_hours` | Whole hours of the shortest delay that binds the actor (timelock, Squads time lock, self-delay). A delay routed through a module that does not bind the owners is not counted. No delay is 0. | `independent_read_reproduce` |
| Money behind one key | `money_per_key_usd` | Money attached to the contract divided by `keys_to_move`, money counted once per protocol and chain by the published rule. `null` when either side is unknown. | `tvl_usd` and its source |
| Admin power | `requirements` | Six yes/no checks: admin power is not a bare key; at least a 3-of-5 multisig; a confirmed delay before changes apply, no bypass; bypass paths ruled out; price feed not under one hand; no key shared with another tracked protocol. | the JSON twin |
| Independent reading | `independent_read` | The finding of a second reader that shares no code with the scorer, and whether it agrees. A disagreement is published, not smoothed. | `independent_read_reproduce` |
| Freshness | `last_pushed`, `stale` | When the score was last published on-chain and whether the oracle reports it stale. A stale label says so on its face. | the oracle's `isStale` |
| Source | `block`, `methodology_hash` | The block the reading was taken at and the hash of the method it was scored under. | `reproduce` |

### An example

The label of one tracked contract, as its JSON twin carries it (taken from the twin published on 14 October 2026, abridged: the reference implementation adds fields, which a conforming twin may do). Two lines are `null` because they were not read: the number of keys (the holder is a timelock) and the money behind one key. The twin says so in `not_assessed`.

```json
{
  "name": "Uniswap v2 + v3 + v4 + UniswapX",
  "chain": "Robinhood Chain",
  "address": "0x1f7d7550b1b028f7571e69a784071f0205fd2efa",
  "composite": 85,
  "band": "strong",
  "keys_to_move": null,
  "react_hours": 48,
  "money_per_key_usd": null,
  "not_assessed": [
    "how many keys it takes to move it",
    "the money behind one key (no money figure, or no key count)"
  ],
  "sub": {
    "adminKeyScore": 80,
    "multisigScore": 100,
    "timelockScore": 75,
    "oracleAuthorityScore": 100,
    "crossExposureScore": 80
  },
  "requirements": [
    {
      "label": "Admin power is not a bare key",
      "met": true
    },
    {
      "label": "At least a 3-of-5 multisig",
      "met": true
    },
    {
      "label": "A confirmed delay before changes apply, no bypass",
      "met": true
    },
    {
      "label": "Bypass paths of the delay checked and ruled out",
      "met": true
    },
    {
      "label": "Price feed not under one hand",
      "met": true
    },
    {
      "label": "No key shared with another tracked protocol",
      "met": false
    }
  ],
  "last_pushed": 1791862006,
  "stale": false,
  "methodology_hash": "0x667dc486af9557a83488110fdb18fe653ba6d3be4773420590ee53b4a052fa45",
  "block": 135056600,
  "license": "CC BY 4.0, attribution: Authority Risk Oracle, realspap.github.io/oracle",
  "independent_read": null
}
```

Display rules: every line above is shown, in this order; the score is shown with its band word; units are written out; the sentence "Read from the chain, not declared by the protocol. Not an audit, not advice." is shown on the label.

## 3. The machine-readable twin

Each label has a JSON twin with the same field names (see `watch/API.md` for the per-contract file and `watch/schema/` for the schemas). A conforming twin carries the fields of section 2, the date of the reading, and the licence. Unknown is `null`, with the reason when one exists. The fields that must be present (and their types) are those of [`watch/schema/label.schema.json`](../watch/schema/label.schema.json): `chain`, `address`, `composite`, `band`, `keys_to_move`, `react_hours`, `money_per_key_usd`, `sub` (with `adminKeyScore`, `multisigScore`, `timelockScore`), `requirements` (six objects with `label` and `met`), `last_pushed`, `stale`, `methodology_hash`, `block` and `license`; `name`, `not_assessed` and `independent_read` are optional. Extra fields are allowed.

## 4. Independence rules (what makes a label a label)

1. A rated party cannot pay for, edit or remove its own label. It can dispute it: a public issue, answered in public, with the evidence.
2. Whoever publishes labels discloses any commercial relationship with a rated party next to the label.
3. Sponsorship of monitoring is allowed only if the sponsor list is public and the formula and method hash do not move because of it.
4. A method change gets a new `methodology_hash` and a dated entry; old readings are kept and labelled with the method they used.

## 5. Conformance

An implementation is "Authority Facts v0.1 compatible" if it: computes the fields as defined in section 2 or declares and documents each difference; shows every line, with "not read" for unknowns; shows the date and block of the reading; publishes the JSON twin; and respects section 4. The check is mechanical and open to anyone: `python3 scripts/conformance.py <twin.json | folder | --url INDEX_URL>` validates the JSON twins against `watch/schema/label.schema.json` (the required fields and types), the band against the composite, the composite against the formula of section 2, and that an unread line is `null` (zero keys, or an amount of zero where the keys were not read, is a failure). A composite that differs from the formula is reported as a DIFFERENCE that the implementer must declare, as this section requires (a cap or a minimum over several oracles, for example). The script exits 0 when every label conforms (differences allowed), 1 when at least one breaks the specification, 2 when nothing could be read. It checks the machine-readable part only; the display rules of section 2 are checked by looking at the label. The reference implementation runs it on every JSON twin before each site build is published, and `scripts/prove.py` runs it on the published twins. Details and examples: [`CONFORMANCE.md`](CONFORMANCE.md).

## 6. Crosswalk (draft, to be validated by the other parties)

| Neighbour | Relation |
|---|---|
| IOSCO, Responsible Persons | `keys_to_move` and the holder kind answer "who holds control" in a form a regulator can read. |
| IOSCO, disclosure | the label is a short, non-technical, sourced disclosure. |
| DeFiScan (stages and dimensions) | `react_hours` corresponds to its exit window; the admin-key and multisig readings to its upgradeability dimension. A mapping to Stage 0/1/2 is future work. |
| L2BEAT Stages | for rollups only; not covered here. |
| SOAC (ERC-8083, 8305, 8306), ERC-8089 | where a contract implements a delayed role grant, `react_hours` should read the delay from it; a registry lets a protocol list its own contracts. Future work. |

## 7. What is not in v0.1

Smart-contract code quality, economic and oracle-manipulation risk, off-chain operations, the identity of any signer. Signer identity is deliberately never published: a label says how many keys, never whose.

## 8. Versioning and governance

Semantic versions. Every change is a pull request or an issue, answered in public, with a dated changelog. The aim of v0.2 is to be edited by at least one party that does not run the reference implementation (a researcher, a vault curator, a DAO delegate).
