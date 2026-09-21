"""
Unit tests for `chains/solana/scorers.py::score_jupiter_aggregator_v6`.

Two independent layers, in two test classes:

  1. `TestReadSquadsv3Primitive` -- `chains/solana/scripts/sol_read.py::
     read_squadsv3`'s own byte-decode logic. This primitive has ZERO
     dedicated test coverage anywhere else in this repo (confirmed via
     `grep -rn "read_squadsv3" --include="*.py" .` before writing this
     file -- only call sites in scorers.py/scout_check.py and the CLI
     dispatch in sol_read.py itself, no test file). Its source is simple
     enough to build a correct fixture confidently WITHOUT guessing any
     offset: the function itself is short, un-branching, and (unlike some
     other decoders in the same file) never validates an account
     discriminator, so no real on-chain bytes are needed to exercise it
     correctly -- an all-zero 8-byte prefix is fine, exactly the same
     reasoning `test_solana_defi_config_admins.py` already documents for
     PumpSwap's GlobalConfig decoder. The fixture below is entirely
     SYNTHETIC (built field-by-field from the function's own offsets:
     threshold u16 @8, stored authority_index u16 @10, then a fixed
     8+1+32+1=42 byte skip, n_keys u32 @54, keys 32 bytes each from @58),
     not frozen real account bytes.

     The `authority_N` PDA field is a SEPARATE thing: it is derived
     entirely offline from (`pk`, `idx`, the fixed Squads v3 program id)
     via `find_program_address` -- it does not depend on the account
     bytes at all, so testing it needs no fixture, only a call with a
     known `pk`/`idx` and a property check (must land off the ed25519
     curve, like every real PDA).

  2. `TestScoreJupiterAggregatorV6` -- the scorer function's OWN
     orchestration (not `read_program`'s or `read_squadsv3`'s internals,
     which are exercised above / already covered elsewhere for
     `read_program`): which of the 3 branches fires (renounced / offline-
     derivation MATCH / MISMATCH), and how that feeds
     `_score_full_power_path`. Follows this repo's established pattern
     (`test_drift_protocol.py`, `test_switchboard_on_demand.py`):
     monkeypatch `sol_read.read_program`/`sol_read.read_squadsv3` DIRECTLY
     on `solana.sol_read` (the module object `chains/solana/scorers.py`'s
     own `import sol_read` resolved to -- NOT this file's separately
     loaded `sol_read` alias used above, a different module object under
     a different `sys.modules` key; patching the wrong one would silently
     no-op), then call the real `score_jupiter_aggregator_v6` end-to-end
     and assert on its returned dict.

     The MATCH/MISMATCH distinction gets dedicated regression coverage
     because it was a real, disclosed bug in this project's history
     (FIXED 2026-09-17, see the docstring on `score_jupiter_aggregator_v6`
     itself and on `_resolve_squads_v4`): a bare truthy check on
     `authority` used to collapse the "renounced" (`None`) case into the
     same degraded MISMATCH branch as a genuine offline/live divergence,
     inverting the risk signal for the single safest state a program can
     be in. `_score_full_power_path`'s own internal formula correctness
     (the numbers a given `kind`/`threshold`/`voters` combination produces)
     is already covered by `test_drift_protocol.py`, `test_switchboard_
     on_demand.py` and `test_solend_governance.py` and is NOT re-tested
     here -- these tests call it too, but only to compute the SAME
     expected numbers the scorer itself should reuse, not to re-verify
     the formula's arithmetic.
"""
import base64
import importlib.util
import os
import sys
import unittest


REPO_ROOT = os.path.join(os.path.dirname(__file__), "..", "..", "..")


def _load_module(unique_name, relative_path):
    file_path = os.path.abspath(os.path.join(REPO_ROOT, relative_path))
    ecosystem_dir = os.path.dirname(file_path)
    if ecosystem_dir not in sys.path:
        sys.path.insert(0, ecosystem_dir)
    spec = importlib.util.spec_from_file_location(unique_name, file_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[unique_name] = mod
    spec.loader.exec_module(mod)
    return mod


sol_read = _load_module("aro_test_sol_read_jupiter_v6", "chains/solana/scripts/sol_read.py")


def _fake_acct(fixtures):
    def acct(url, pk, enc="base64", length=None):
        if pk not in fixtures:
            raise AssertionError(f"unexpected account fetch: {pk}")
        return {"data": [fixtures[pk]], "owner": "unused-owner"}
    return acct


# Two arbitrary, but validly-shaped, 32-byte pubkeys built from raw bytes
# (not copied/guessed from any real account) -- used only to exercise the
# "list of member keys" slot of the synthetic Squads v3 Ms fixture below.
_SYNTH_KEY0 = sol_read.b58(bytes([0x11]) * 32)
_SYNTH_KEY1 = sol_read.b58(bytes([0x22]) * 32)


def _synthetic_squadsv3_ms(threshold, stored_authority_index, keys):
    """Build a synthetic Squads v3 Ms account matching `read_squadsv3`'s
    OWN offsets exactly (no discriminator check exists in that decoder,
    so the first 8 bytes can be zero):
      [0:8]   discriminator (unchecked, left zero)
      [8:10]  threshold, u16 LE
      [10:12] authority_index (the STORED on-chain field -- distinct from
              the `authority_index=` kwarg callers pass to request a PDA
              derivation, which never touches these bytes at all), u16 LE
      [12:54] 42 bytes (8+1+32+1 per read_squadsv3's own `o +=`) skipped
              entirely by the decoder -- left zero
      [54:58] n_keys, u32 LE
      [58:]   n_keys * 32-byte pubkeys
    """
    total_len = 58 + 32 * len(keys)
    d = bytearray(total_len)
    d[8:10] = threshold.to_bytes(2, "little")
    d[10:12] = stored_authority_index.to_bytes(2, "little")
    d[54:58] = len(keys).to_bytes(4, "little")
    for i, k in enumerate(keys):
        d[58 + 32 * i:58 + 32 * (i + 1)] = sol_read.b58dec(k)
    return base64.b64encode(bytes(d)).decode()


class TestReadSquadsv3Primitive(unittest.TestCase):
    """Primitive-level: `read_squadsv3`'s own byte decode + PDA derivation.
    See module docstring for why a synthetic (not frozen real) fixture is
    used here and why that is safe for this specific decoder."""

    # `pk` must be a real, valid base58 32-byte pubkey (not a placeholder
    # string) because read_squadsv3 offline-derives the authority_N PDA
    # from it via b58dec/find_program_address -- reusing the real Jupiter
    # multisig address this scorer actually queries, same convention as
    # the orchestration tests below.
    MS_PUBKEY = "7ZyDFzet6sKgZLN4D89JLfo7chu2n7nYdkFt5RCFk8Sf"

    def setUp(self):
        self._orig_acct = sol_read.acct
        sol_read.acct = _fake_acct({
            self.MS_PUBKEY: _synthetic_squadsv3_ms(
                threshold=4, stored_authority_index=3, keys=[_SYNTH_KEY0, _SYNTH_KEY1]),
        })

    def tearDown(self):
        sol_read.acct = self._orig_acct

    def test_decodes_threshold_stored_index_and_keys_from_correct_offsets(self):
        r = sol_read.read_squadsv3("unused-url", self.MS_PUBKEY, authority_index=1)
        self.assertEqual(r["threshold"], 4)
        # The STORED byte field at offset 10 (3) must be read independently
        # of the `authority_index=1` kwarg passed to this call (which only
        # controls which authority_N PDA gets derived below) -- using the
        # wrong offset, or accidentally echoing the kwarg instead of
        # decoding the bytes, would make these collide and this test
        # wouldn't catch it.
        self.assertEqual(r["authority_index"], 3)
        self.assertEqual(r["n_keys"], 2)
        self.assertEqual(r["keys"], [_SYNTH_KEY0, _SYNTH_KEY1])

    def test_requested_authority_pda_is_off_curve_and_specific_to_its_index(self):
        r1 = sol_read.read_squadsv3("unused-url", self.MS_PUBKEY, authority_index=1)
        r2 = sol_read.read_squadsv3("unused-url", self.MS_PUBKEY, authority_index=2)
        # A PDA is by construction off the ed25519 curve (no private key can
        # sign for it directly) -- a genuine correctness property of the
        # derivation, not a tautological restatement of the formula.
        self.assertFalse(sol_read.on_curve(r1["authority_1"]))
        self.assertFalse(sol_read.on_curve(r2["authority_2"]))
        # Different index -> different seeds -> different derived address.
        self.assertNotEqual(r1["authority_1"], r2["authority_2"])
        # Only the requested index's key is present.
        self.assertNotIn("authority_2", r1)
        self.assertNotIn("authority_1", r2)


solana = _load_module("aro_test_solana_scorers_jupiter_v6", "chains/solana/scorers.py")

JUPITER_PROGRAM = "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4"
JUPITER_MS = "7ZyDFzet6sKgZLN4D89JLfo7chu2n7nYdkFt5RCFk8Sf"


class _PatchSolRead:
    """Shared setUp/tearDown: monkeypatch solana.sol_read.read_program and
    solana.sol_read.read_squadsv3 -- the two primitives
    score_jupiter_aggregator_v6 actually calls -- on the module object
    scorers.py's own `import sol_read` resolved to."""

    def setUp(self):
        self._orig_read_program = solana.sol_read.read_program
        self._orig_read_squadsv3 = solana.sol_read.read_squadsv3
        self.read_program_calls = []
        self.read_squadsv3_calls = []

    def tearDown(self):
        solana.sol_read.read_program = self._orig_read_program
        solana.sol_read.read_squadsv3 = self._orig_read_squadsv3

    def _install(self, upgrade_authority, squadsv3_result):
        def fake_read_program(url, pk):
            self.read_program_calls.append(pk)
            return {"upgrade_authority": upgrade_authority}

        def fake_read_squadsv3(url, pk, authority_index=None):
            self.read_squadsv3_calls.append((pk, authority_index))
            return squadsv3_result

        solana.sol_read.read_program = fake_read_program
        solana.sol_read.read_squadsv3 = fake_read_squadsv3


class TestScoreJupiterAggregatorV6Renounced(_PatchSolRead, unittest.TestCase):
    """Branch 1: `program.upgrade_authority is None`. Regression coverage
    for the disclosed 2026-09-17 bug: this must be checked and handled
    BEFORE any MATCH/MISMATCH comparison, not folded into the mismatch
    branch. To make that ordering explicit, the Squads v3 fixture here
    deliberately returns a TRUTHY `authority_1` value -- if the code
    regressed to comparing `authority == derived` first (with `authority`
    falsy/None), it would take the degraded (20, 20, 0) mismatch branch
    instead and this test would catch it."""

    def test_renounced_upgrade_authority_scores_full_power_and_is_not_a_mismatch(self):
        self._install(
            upgrade_authority=None,
            squadsv3_result={"threshold": 4, "n_keys": 7, "keys": ["k1"], "authority_1": "SomeTruthyDerivedValue"},
        )
        result = solana.score_jupiter_aggregator_v6("unused-url")
        self.assertEqual(
            (result["adminKeyScore"], result["multisigScore"], result["timelockScore"]),
            (100, 100, 100),
        )
        self.assertEqual(result["compositeScore"], solana._composite(100, 100, 100))
        self.assertFalse(any("did NOT match" in n for n in result["notes"]))
        self.assertTrue(any("renounced" in n.lower() for n in result["notes"]))
        # Renounced short-circuits before the multisig-signers path is ever
        # populated.
        self.assertEqual(result["_signers"], set())


class TestScoreJupiterAggregatorV6Match(_PatchSolRead, unittest.TestCase):
    """Branch 2: offline-derived Squads v3 authority_1 MATCHES the live
    program.upgrade_authority -- the real, calibrated 4-of-7 case
    (METHODOLOGY.md 3.4 / this function's own docstring)."""

    def test_match_reuses_squads_v3_formula_and_populates_signers(self):
        live_authority = "LiveUpgradeAuthorityPDA"
        member_keys = [f"member{i}" for i in range(7)]
        self._install(
            upgrade_authority=live_authority,
            squadsv3_result={
                "threshold": 4, "n_keys": 7, "keys": member_keys,
                "authority_1": live_authority,
            },
        )
        result = solana.score_jupiter_aggregator_v6("unused-url")

        expected_admin, expected_multisig, expected_timelock = solana._score_full_power_path(
            "squads_v3", threshold=4, voters=7)
        self.assertEqual(
            (result["adminKeyScore"], result["multisigScore"], result["timelockScore"]),
            (expected_admin, expected_multisig, expected_timelock),
        )
        self.assertEqual(
            result["compositeScore"],
            solana._composite(expected_admin, expected_multisig, expected_timelock),
        )
        self.assertEqual(result["_signers"], set(member_keys))
        self.assertTrue(any("MATCH" in n and "MISMATCH" not in n for n in result["notes"]))
        self.assertEqual(result["oracleAuthorityScore"], 100)
        self.assertEqual(result["target"], JUPITER_PROGRAM)
        self.assertEqual(result["label"], "Jupiter Aggregator v6")

        # Orchestration correctness: the right program/multisig constants
        # and the right authority_index were actually used to query.
        self.assertEqual(self.read_program_calls, [JUPITER_PROGRAM])
        self.assertEqual(self.read_squadsv3_calls, [(JUPITER_MS, 1)])


class TestScoreJupiterAggregatorV6Mismatch(_PatchSolRead, unittest.TestCase):
    """Branch 3: offline-derived authority does NOT match the live
    upgrade authority -- degrades to the fixed (20, 20, 0) rather than
    trusting the hardcoded JUPITER_MS constant. Two distinct ways this can
    happen are both covered: an explicit mismatching value, and the
    `authority_1` key being absent altogether (`ms.get("authority_1")`
    falls back to `None`, which must ALSO degrade, not raise or silently
    treat a missing key as a match)."""

    def test_explicit_mismatch_degrades_to_20_20_0(self):
        self._install(
            upgrade_authority="LiveUpgradeAuthorityPDA",
            squadsv3_result={"threshold": 4, "n_keys": 7, "keys": ["k1"], "authority_1": "SomeOtherDerivedPDA"},
        )
        result = solana.score_jupiter_aggregator_v6("unused-url")
        self.assertEqual(
            (result["adminKeyScore"], result["multisigScore"], result["timelockScore"]),
            (20, 20, 0),
        )
        self.assertEqual(result["compositeScore"], solana._composite(20, 20, 0))
        self.assertTrue(any("did NOT match" in n for n in result["notes"]))
        # The mismatch branch never populates _signers.
        self.assertEqual(result["_signers"], set())

    def test_missing_authority_1_key_also_degrades_rather_than_matching(self):
        self._install(
            upgrade_authority="LiveUpgradeAuthorityPDA",
            squadsv3_result={"threshold": 4, "n_keys": 7, "keys": ["k1"]},  # no "authority_1" at all
        )
        result = solana.score_jupiter_aggregator_v6("unused-url")
        self.assertEqual(
            (result["adminKeyScore"], result["multisigScore"], result["timelockScore"]),
            (20, 20, 0),
        )
        self.assertEqual(result["_signers"], set())


if __name__ == "__main__":
    unittest.main()
