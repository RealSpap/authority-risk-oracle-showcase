# Checking a label: `scripts/conformance.py`

*Companion to [AUTHORITY-FACTS-SPEC.md](AUTHORITY-FACTS-SPEC.md), section 5. Standard library only, no key, no network unless you give it a URL.*

The script answers one question about any implementation's JSON label: **does it conform to Authority Facts v0.1?** It does not judge whether a score is right. It checks that the label says what the specification requires and never invents a number.

## Use

```bash
python3 scripts/conformance.py path/to/twin.json                                   # one label
python3 scripts/conformance.py path/to/folder_of_twins/                            # every *.json in it (index.json is skipped)
python3 scripts/conformance.py --url https://realspap.github.io/oracle/p/index.json  # follows the `addresses` list of an index and fetches each twin
python3 scripts/conformance.py --selftest                                          # offline: the script's own cases
```

## What it checks

| Check | Failure or difference |
|---|---|
| The fields and types of [`watch/schema/label.schema.json`](../watch/schema/label.schema.json) are present (`chain`, `address`, `composite`, `band`, `keys_to_move`, `react_hours`, `money_per_key_usd`, `sub`, `requirements`, `last_pushed`, `stale`, `methodology_hash`, `block`, `license`) | FAIL |
| `composite` is between 0 and 100 and `band` is the band of that number (critical 0-19, weak 20-39, moderate 40-59, decent 60-79, strong 80-100) | FAIL |
| `composite` equals `floor((4a + 3m + 3t + 5) / 10)` of the three readings | **DIFFERENCE**, not a failure: section 5 allows a documented difference (a cap, a minimum over several oracles); the implementer declares it |
| An unread line is `null`, never zero: `keys_to_move` below 1, `react_hours` below 0 and `money_per_key_usd` of 0 or less are failed reads written as numbers; money behind a key that was never counted is an invention | FAIL |
| Exactly six `requirements` checks | FAIL |
| `methodology_hash` is a 32-byte hex hash and `license` is not empty | FAIL |

## What it prints, and the exit code

One line per problem (`FAIL <label>: <reason>` or `DIFFERENCE <label>: <reason>`), then a count. Exit **0**: every label conforms (differences allowed). Exit **1**: at least one label breaks the specification. Exit **2**: nothing could be read (a network error is never a pass).

Real runs of 15 October 2026, on the published twin of one contract and on three altered copies of it:

```text
$ python3 scripts/conformance.py good.json
conformance: 1 label(s), 0 break the specification, 0 with a difference to declare           (exit 0)

$ python3 scripts/conformance.py bad-band.json          # band changed to "weak" on a composite of 85
FAIL bad-band.json: band 'weak' does not match composite 85 (expected 'strong')
conformance: 1 label(s), 1 break the specification, 0 with a difference to declare           (exit 1)

$ python3 scripts/conformance.py zero-keys.json         # keys_to_move changed to 0
FAIL zero-keys.json: keys_to_move is 0: zero keys is a failed read, write null
conformance: 1 label(s), 1 break the specification, 0 with a difference to declare           (exit 1)

$ python3 scripts/conformance.py cap.json               # composite 60 / "decent" on readings that give 85
DIFFERENCE cap.json: composite 60 differs from the formula result 85: declare the cap or minimum that explains it
conformance: 1 label(s), 0 break the specification, 1 with a difference to declare           (exit 0)

$ python3 scripts/conformance.py --url https://realspap.github.io/oracle/p/index.json
conformance: 197 label(s), 0 break the specification, 0 with a difference to declare         (exit 0)
```

## What it does not check

The display rules of section 2 of the specification (every line shown in order, the band word, the units written out, the sentence "Read from the chain, not declared by the protocol. Not an audit, not advice.") are checked by looking at the label. The independence rules of section 4 are about how a label is published, not about its JSON. A conforming label can still be wrong: `scripts/prove.py` replays the reference implementation's numbers against the chain.

## For another implementation

Publish one JSON twin per contract with the fields above, run the script on your folder, and declare each DIFFERENCE it prints in your documentation. An implementation that passes with every difference declared can say "Authority Facts v0.1 compatible" (specification, section 5).

## Added on 30 October 2026: what the checker is, and where producers differ

**It is not only a syntax check.** Beyond the fields and types of the schema, `scripts/conformance.py` applies rules about meaning: the band must be the band of the composite, the composite is compared with the formula, a number that stands for a failed read (zero keys, a negative delay, money of zero or less) is refused, exactly six requirements must be present, and the methodology hash must be 32 bytes. What it cannot check is whether the numbers are true: for that, `scripts/prove.py` replays the reference implementation against the chain.

**What the schema bounds and what it does not.** `watch/schema/label.schema.json` requires the fields and fixes the allowed bands. It sets no minimum or maximum on a number: the bounds (a composite from 0 to 100, keys of at least 1, hours of at least 0) are enforced by `scripts/conformance.py`, not by the schema, and the schema allows extra fields. A producer who validates only against the schema accepts labels the checker refuses. Since 30 October 2026 `watch/schema/label.strict.schema.json` states those bounds, and `python3 scripts/conformance.py --strict LABEL` reads a label against it and treats a difference from the formula as a failure.

**Two producers can both conform and still differ.** The specification lets an implementation declare a difference. Two labels for the same contract are comparable only if each states the date and block of its reading and the method it used; a difference of definition (what counts as a key, which delay counts) is declared in the producer's documentation, as section 5 of the specification asks, not hidden. When comparing two producers, compare those declarations first.
