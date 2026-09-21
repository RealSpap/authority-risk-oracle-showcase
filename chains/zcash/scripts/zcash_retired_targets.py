"""
Zcash targets RETIRED from the live set, kept as legacy snapshots (not deleted).

Why a separate, import-light module: `scorers.py` (which decides what `score_all()` returns) and
`attest_scores.py` / `publish_batch.py` (which re-derive and anchor commitments) must agree on which
targets are retired without importing each other's heavy dependencies, and the unit tests load these
files under different module names.

A retired target:
  * is NOT returned by `scorers.score_all()` (default) and so is in no commitment made after its
    retirement date;
  * IS still returned when a run asks for it (`score_all(include_retired=True)` for all of them, or a set of ids), so that a
    commitment made BEFORE the retirement (which contains it) can still be re-derived from a live run
    (`attest_scores.py verify --live` asks for exactly the retired targets the bundle holds);
  * is live again as soon as it is removed from this registry (the registry is the single switch);
  * keeps its record, with the anchors that contain it, in the legacy snapshot file named below.
The commitments already anchored on Zcash Testnet are immutable and unchanged.
"""

RETIRED_TARGETS = {
    "keyring1k6vc6vhp6e6l3rxalue9v4ux": {
        "label": "Zenrock zenZEC dMPC custody keyring (\"Zenrock MPC\")",
        "retired": "2026-09-20",
        "reason": (
            "Frozen single-source snapshot of a product in wind-down: the zrchain node it was read from reports its last "
            "block on 2026-08-10, the operating company is in UK administration since 2026-04-08, no zenZEC minted since "
            "2026-03-17. It does not describe a live authority, so it is kept out of every live aggregate."
        ),
        "status_note": "chains/zcash/data/zenzec_status_2026-09-20.md",
        "legacy_snapshot": "chains/zcash/data/legacy_snapshot_zenzec_keyring_2026-09-20.json",
    },
}


def retired_in_bundle(bundle) -> frozenset:
    """The retired targets an attestation bundle (a dict with a `records` list) holds: exactly the ones a live re-derivation of
    it must ask for (`score_all(include_retired=<this set>)`), so a bundle never gets a retired target it does not contain."""
    return frozenset(r["target"] for r in bundle.get("records", []) if r.get("target") in RETIRED_TARGETS)


def bundle_includes_retired(bundle) -> bool:
    return bool(retired_in_bundle(bundle))


RECORD_FIELDS = ("adminKeyScore", "multisigScore", "timelockScore", "oracleAuthorityScore", "crossExposureScore",
                 "compositeScore", "l1CappedComposite")


def build_legacy_snapshot(target, anchored):
    """The legacy snapshot of a retired target, from the anchored attestation files that contain it.

    `anchored` is a list of (attestationFile relative to the repo root, parsed attestation dict). The record and its Merkle
    leaf must be identical in every one of them (they are: the second anchor republishes the first commitment), else this
    raises, so a snapshot can never say something an anchor does not."""
    meta = RETIRED_TARGETS[target]
    records = []
    committed_in = []
    for rel, att in anchored:
        rec = next(r for r in att["records"] if r["target"] == target)
        records.append({k: rec.get(k) for k in RECORD_FIELDS} | {"leafHash": rec["leafHash"], "label": rec["label"]})
        committed_in.append({
            "attestationFile": rel,
            "txid": att["anchor"]["txid"],
            "commitmentBlake2b256": att["commitmentBlake2b256"],
        })
    if any(r != records[0] for r in records):
        raise ValueError(f"{target}: the anchored records differ between anchors, refusing to write a snapshot")
    rec = records[0]
    return {
        "format": "aro-zcash-legacy-snapshot-v1",
        "target": target,
        "label": rec["label"],
        "retiredOn": meta["retired"],
        "reason": meta["reason"],
        "statusNote": meta["status_note"],
        "record": {k: rec[k] for k in RECORD_FIELDS},
        "leafHash": rec["leafHash"],
        "committedIn": committed_in,
        "note": ("This is the record exactly as anchored, not a current reading. The commitments listed are immutable and still "
                 "contain it; every commitment made after the retirement date does not. Nothing here is deleted from them."),
    }
