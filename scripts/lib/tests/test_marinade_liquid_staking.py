"""
Unit tests for the 3 new decoders added 2026-09-18 (`chains/solana/
scripts/sol_read.py`: `read_marinade_state`, `read_legacy_serum_multisig`,
`read_token_owner_record`) -- closing `chains/solana/data/scouted_targets_
2026-09-17-run2.md`'s "decode Marinade State.admin_authority" AND
"Methodology gap H1 (legacy serum-style multisig)" open points.

Two small real accounts (the legacy multisig, one TokenOwnerRecordV2) are
tested against EXACT bytes fetched live from Solana Mainnet Beta on
2026-09-18, matching this project's own `test_solana_defi_config_admins.py`
precedent. One large account (Marinade's 2616-byte `State`) is tested
against a SYNTHETIC fixture instead, same reasoning as that file's own
large-account tests: this checks offset correctness, not full-account
fidelity, without embedding thousands of mostly-irrelevant real bytes.

`list_token_owner_records` (a live `getProgramAccounts` enumeration) is
NOT unit tested here, matching this project's existing precedent for
other network-dependent enumeration helpers (e.g.
`resolve_controller_via_last_tx` has no unit test either) -- it is
exercised instead by the live dry-run in `score_marinade`'s own
verification (see `chains/solana/data/scored_targets_2026-09-18-
marinade-liquid-staking.md`).

`sol_read.acct` is monkeypatched rather than mocking the network.
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


sol_read = _load_module("aro_test_sol_read_marinade", "chains/solana/scripts/sol_read.py")

# Exact account bytes, base64, fetched live from https://api.mainnet-beta.solana.com
# on 2026-09-18 -- see chains/solana/data/scored_targets_2026-09-18-
# marinade-liquid-staking.md for the full derivation and reproduction commands.
LEGACY_MULTISIG_B64 = (
    "4HR5ukShT+wNAAAAa1Y09sy89Lzydy8G0GXp4AkLfSuiY13iv8oiI7rXT5Uk1dz1+v/NoHUMouHBpE6dSWLHj82IN/aJD1R1uRZoLq94Erew5MPzyQFt"
    "S2yJqnCc4CgTbscdZSTrmdbfyBhwq6WhhsMStmP68sR+I38GLzJZplQyYahnZ/3xsmcR/AlQDfg0K+06fV/ahebbPXm4G9kYs25KbWFQPqXYy36/RZKl"
    "kx87Gw/N9KG3SXmuDcDkwB4509kFm9/IspE3egNebDtfKzaM4fZjPRe2nhdYdyZcw65rI9Y5iANP3epL4TjGMiVc5PXc8cIb9UeM1dOsa59aFI3p1Eyt"
    "C/qdgJjG3ZZcACCTi+yToGlT38pqPih6qA+KtszslhjUUl0oaRQH4iSH27V1qLfA7OMudff8gd1dfyO4fmQHNP9VI+m1IkZY8CaCN9kiKOLGb2H0cyBm"
    "e8GoEJ8gRMVwSPM2Qn5U1SKvETqmpyblytCLcltKe1Vuuuh0DMPTnN1H3z3QKqYESfOv6E8sbK3nigXtYf7FSABixk/m2c5R+5SzEU2nolwGAAAAAAAA"
    "AP0BAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
)
TOKEN_OWNER_RECORD_B64 = (
    "EWoYHCgTvlJMvNSguAOdd9J7UJmNH1jJh2PXJTjd97biT3wUh3bKQoGx4+zmqgIV/mux203lz6q5nyucRaTAl15sO18rNozh9mM9F7aeF1h3JlzDrmsj"
    "1jmIA0/d6kvhOAEAAAAAAAAAcwAAAAAAAAAAAQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
)

# Live-confirmed values these fixtures must decode to (independently
# cross-checked against a second RPC, solana-rpc.publicnode.com, and
# re-derived offline via each account's own PDA formula -- see
# score_marinade's docstring in chains/solana/scorers.py).
LEGACY_MULTISIG_OWNER_0 = "8DzsCSvbvBDYxGB4ytNF698zi6Dyo9dUBVRNjZQFHSUt"
LEGACY_MULTISIG_OWNER_6 = "8HVYKgq2PA4SCDuPZSfHBH1aupTBJYPVru6kq3UfuSX9"
LEGACY_MULTISIG_OWNER_12 = "5ygHFBRddFh7v4PpqquQu2yeRdxWvN1PhyjyzfENdUVh"
TOR_REALM = "899YG3yk4F66ZgbNWLHriZHTXSKk9e1kvsKEquW7L6Mo"
TOR_COUNCIL_MINT = "6MGwpuJ5YE1c8jJaF8FKurQdDJeYRf1adX76dovkXxRs"
TOR_OWNER = "8HVYKgq2PA4SCDuPZSfHBH1aupTBJYPVru6kq3UfuSX9"

MARINADE_STATE_ADMIN_AUTHORITY = "42VJbDihcS81YJPbuhHnHgvo1ehu42j8VK9sNwrnAarR"
MARINADE_STATE_MSOL_MINT = "mSoLzYCxHdYgdzU16g5QSh3i5K3z3KZK7ytfqcJm7So"
MARINADE_STATE_PAUSE_AUTHORITY = "AjGjLWx7vbzgPNxPSQUPjLNjeavQCHVS9VoJNWpnyP6n"


def _synthetic_account(total_len, discriminator, pubkey_offsets, byte_offsets=None):
    d = bytearray(total_len)
    d[0:len(discriminator)] = discriminator
    for offset, pk in pubkey_offsets:
        d[offset:offset + 32] = sol_read.b58dec(pk)
    for offset, val in (byte_offsets or []):
        d[offset] = val
    return base64.b64encode(bytes(d)).decode()


MARINADE_STATE_DISCRIMINATOR = bytes.fromhex("d8926b5e684bb6b1")
MARINADE_STATE_B64 = _synthetic_account(
    2616, MARINADE_STATE_DISCRIMINATOR,
    [(8, MARINADE_STATE_MSOL_MINT), (40, MARINADE_STATE_ADMIN_AUTHORITY), (576, MARINADE_STATE_PAUSE_AUTHORITY)],
    [(608, 0)],
)


def _fake_acct(fixtures):
    def acct(url, pk, enc="base64", length=None):
        if pk not in fixtures:
            raise AssertionError(f"unexpected account fetch: {pk}")
        return {"data": [fixtures[pk]]}
    return acct


class TestReadMarinadeState(unittest.TestCase):
    def test_admin_authority_and_pause_authority_decode_correctly(self):
        orig = sol_read.acct
        sol_read.acct = _fake_acct({"8szGkuLTAux9XMgZ2vtY39jVSowEcpBfFfD8hXSEqdGC": MARINADE_STATE_B64})
        try:
            r = sol_read.read_marinade_state("url", "8szGkuLTAux9XMgZ2vtY39jVSowEcpBfFfD8hXSEqdGC")
            self.assertEqual(r["msol_mint"], MARINADE_STATE_MSOL_MINT)
            self.assertEqual(r["admin_authority"], MARINADE_STATE_ADMIN_AUTHORITY)
            self.assertEqual(r["pause_authority"], MARINADE_STATE_PAUSE_AUTHORITY)
            self.assertFalse(r["paused"])
        finally:
            sol_read.acct = orig

    def test_offset_40_is_not_a_coincidence_of_the_fixture(self):
        # Move admin_authority to a different offset (72, where
        # operational_sol_account actually lives) and confirm it is NOT
        # found at 40 anymore -- guards against a decoder that reads a
        # hardcoded slice regardless of what's really there.
        orig = sol_read.acct
        moved = _synthetic_account(2616, MARINADE_STATE_DISCRIMINATOR, [(72, MARINADE_STATE_ADMIN_AUTHORITY)])
        sol_read.acct = _fake_acct({"8szGkuLTAux9XMgZ2vtY39jVSowEcpBfFfD8hXSEqdGC": moved})
        try:
            r = sol_read.read_marinade_state("url", "8szGkuLTAux9XMgZ2vtY39jVSowEcpBfFfD8hXSEqdGC")
            self.assertNotEqual(r["admin_authority"], MARINADE_STATE_ADMIN_AUTHORITY)
        finally:
            sol_read.acct = orig


class TestReadLegacySerumMultisig(unittest.TestCase):
    def test_owners_threshold_nonce_decode_correctly(self):
        orig = sol_read.acct
        sol_read.acct = _fake_acct({"magrsHFQxkkioAy45VWnZnFBBdKVdy2ZiRoRGYT9Wed": LEGACY_MULTISIG_B64})
        try:
            r = sol_read.read_legacy_serum_multisig("url", "magrsHFQxkkioAy45VWnZnFBBdKVdy2ZiRoRGYT9Wed")
            self.assertEqual(r["threshold"], 6)
            self.assertEqual(r["nonce"], 253)
            self.assertEqual(r["owner_set_seqno"], 1)
            self.assertEqual(len(r["owners"]), 13)
            self.assertEqual(r["owners"][0], LEGACY_MULTISIG_OWNER_0)
            self.assertEqual(r["owners"][6], LEGACY_MULTISIG_OWNER_6)
            self.assertEqual(r["owners"][12], LEGACY_MULTISIG_OWNER_12)
        finally:
            sol_read.acct = orig


class TestReadTokenOwnerRecord(unittest.TestCase):
    def test_realm_mint_owner_deposit_decode_correctly(self):
        orig = sol_read.acct
        sol_read.acct = _fake_acct({"2st6oPs6gsXM2KY2SBXamz1gdRE6cVQUgnDqRZZrbt47": TOKEN_OWNER_RECORD_B64})
        try:
            r = sol_read.read_token_owner_record("url", "2st6oPs6gsXM2KY2SBXamz1gdRE6cVQUgnDqRZZrbt47")
            self.assertEqual(r["account_type"], 17)
            self.assertEqual(r["realm"], TOR_REALM)
            self.assertEqual(r["governing_token_mint"], TOR_COUNCIL_MINT)
            self.assertEqual(r["governing_token_owner"], TOR_OWNER)
            self.assertEqual(r["governing_token_deposit_amount"], 1)
        finally:
            sol_read.acct = orig


if __name__ == "__main__":
    unittest.main()
