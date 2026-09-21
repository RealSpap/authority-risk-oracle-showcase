"""
Offline tests for chains/solana/deploy/solana_tx.py (added 2026-09-19,
deploy_testnet phase) -- the hand-written transaction / PDA / keypair
helpers used by update_scores_solana.py's real push path and by
read_scores_solana.py. No network.

Expected PDAs below were produced independently by the Solana CLI
(`solana find-program-derived-address 5VhiTAGLEViGgajhxPbzdWz7WLUAiRy42DY6qi6tYh4W
string:registry` and `... string:score pubkey:JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4`,
agave CLI 4.2.2), not by this module.
"""
import base64
import importlib.util
import json
import os
import struct
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
_spec = importlib.util.spec_from_file_location(
    "solana_tx", os.path.join(REPO_ROOT, "chains", "solana", "deploy", "solana_tx.py"))
stx = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(stx)

PROGRAM_ID = "5VhiTAGLEViGgajhxPbzdWz7WLUAiRy42DY6qi6tYh4W"
JUP = "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4"


class TestPda(unittest.TestCase):
    def test_registry_pda_matches_solana_cli(self):
        pda, _ = stx.find_program_address([b"registry"], stx.b58decode(PROGRAM_ID, 32))
        self.assertEqual(stx.b58encode(pda), "CDHtBTibohaCRLtNavArsXfthK9gbwkbmvnujncZBEib")

    def test_score_pda_matches_solana_cli(self):
        pda, _ = stx.find_program_address([b"score", stx.b58decode(JUP, 32)], stx.b58decode(PROGRAM_ID, 32))
        self.assertEqual(stx.b58encode(pda), "65Zt5pU2sf6Lu4WeEz3Dz8h3Mr7rHYDrdwweiSXyNZz2")

    def test_real_wallet_pubkeys_are_on_curve(self):
        # ed25519 public keys (not PDAs) must be on the curve
        import nacl.signing
        for i in range(20):
            vk = bytes(nacl.signing.SigningKey(bytes([i + 1]) * 32).verify_key)
            self.assertTrue(stx.is_on_curve(vk))

    def test_pda_is_off_curve(self):
        pda, _ = stx.find_program_address([b"registry"], stx.b58decode(PROGRAM_ID, 32))
        self.assertFalse(stx.is_on_curve(pda))


class TestBase58(unittest.TestCase):
    def test_roundtrip(self):
        for s in (PROGRAM_ID, JUP, stx.SYSTEM_PROGRAM_ID):
            self.assertEqual(stx.b58encode(stx.b58decode(s, 32)), s)

    def test_wrong_length_rejected(self):
        with self.assertRaises(ValueError):
            stx.b58decode(JUP, 64)


class TestCompactU16(unittest.TestCase):
    def test_known_encodings(self):
        self.assertEqual(stx._compact_u16(0), b"\x00")
        self.assertEqual(stx._compact_u16(0x7F), b"\x7f")
        self.assertEqual(stx._compact_u16(0x80), b"\x80\x01")
        self.assertEqual(stx._compact_u16(0x3FFF), b"\xff\x7f")
        self.assertEqual(stx._compact_u16(0x4000), b"\x80\x80\x01")


class TestTransaction(unittest.TestCase):
    def test_signed_tx_layout_and_signature(self):
        import nacl.signing
        sk = nacl.signing.SigningKey(b"\x07" * 32)
        payer = bytes(sk.verify_key)
        program = stx.b58decode(PROGRAM_ID, 32)
        system = stx.b58decode(stx.SYSTEM_PROGRAM_ID, 32)
        registry, _ = stx.find_program_address([b"registry"], program)
        data = b"\x01\x02\x03"
        raw = stx.build_signed_tx(sk, payer, program,
                                  [(registry, False, True), (payer, True, True), (system, False, False)],
                                  data, JUP)  # any 32-byte base58 value works as a blockhash here
        self.assertEqual(raw[0], 1)
        sig, msg = raw[1:65], raw[65:]
        sk.verify_key.verify(msg, sig)  # raises if wrong
        self.assertEqual(msg[:3], bytes([1, 0, 2]))  # 1 signer, 0 ro-signed, 2 ro-unsigned (system, program)
        self.assertEqual(msg[3], 4)  # payer, registry, system, program
        keys = [msg[4 + 32 * i: 36 + 32 * i] for i in range(4)]
        self.assertEqual(keys[0], payer)
        self.assertEqual(keys[1], registry)
        self.assertEqual(set(keys[2:]), {system, program})
        ix = msg[4 + 128 + 32 + 1:]
        self.assertEqual(keys[ix[0]], program)
        self.assertEqual(ix[1], 3)
        self.assertEqual([keys[i] for i in ix[2:5]], [registry, payer, system])
        self.assertEqual(ix[5], 3)
        self.assertEqual(ix[6:], data)


class TestKeypair(unittest.TestCase):
    def test_both_formats_and_inconsistency(self):
        import nacl.signing
        sk = nacl.signing.SigningKey(b"\x09" * 32)
        arr = list(bytes(sk) + bytes(sk.verify_key))
        with tempfile.TemporaryDirectory() as d:
            p1 = os.path.join(d, "a.json")
            json.dump(arr, open(p1, "w"))
            p2 = os.path.join(d, "b.json")
            json.dump({"pubkey_base58": stx.b58encode(bytes(sk.verify_key)), "secret_key_uint8_array": arr}, open(p2, "w"))
            self.assertEqual(stx.load_keypair(p1)[1], bytes(sk.verify_key))
            self.assertEqual(stx.load_keypair(p2)[1], bytes(sk.verify_key))
            bad = arr[:32] + [0] * 32
            p3 = os.path.join(d, "c.json")
            json.dump(bad, open(p3, "w"))
            with self.assertRaises(ValueError):
                stx.load_keypair(p3)


class TestAnchorDiscriminators(unittest.TestCase):
    def test_account_discriminator_convention(self):
        import hashlib
        self.assertEqual(stx.anchor_discriminator("account", "AuthorityScore"),
                         hashlib.sha256(b"account:AuthorityScore").digest()[:8])
        self.assertEqual(stx.anchor_discriminator("global", "update_score"),
                         hashlib.sha256(b"global:update_score").digest()[:8])



class TestWaitProgramInvocable(unittest.TestCase):
    """Deploy->initialize race guard (2026-09-19 attempt 2): a program
    deployed in slot N must not be invoked until the confirmed slot > N."""

    PDATA = "CDHtBTibohaCRLtNavArsXfthK9gbwkbmvnujncZBEib"  # any 32-byte key

    def _accounts(self, deployed_slot):
        prog = struct.pack("<I", 2) + stx.b58decode(self.PDATA, 32)
        pdata = struct.pack("<I", 3) + struct.pack("<Q", deployed_slot) + b"\x01" + b"\x00" * 32 + b"ELF"
        return prog, pdata

    def test_parsers(self):
        prog, pdata = self._accounts(1234)
        self.assertEqual(stx.parse_upgradeable_program(prog), self.PDATA)
        self.assertEqual(stx.parse_programdata_slot(pdata), 1234)
        with self.assertRaises(ValueError):
            stx.parse_upgradeable_program(pdata)
        with self.assertRaises(ValueError):
            stx.parse_programdata_slot(prog)

    def _fake_rpc(self, prog, pdata, slots):
        slots = list(slots)

        def fake(url, method, params=None, retries=4):
            if method == "getSlot":
                return slots.pop(0) if len(slots) > 1 else slots[0]
            if method == "getAccountInfo":
                if params[0] == PROGRAM_ID:
                    return {"value": {"executable": True, "owner": stx.BPF_LOADER_UPGRADEABLE_ID,
                                      "data": [base64.b64encode(prog).decode(), "base64"]}}
                if params[0] == self.PDATA:
                    return {"value": {"executable": False, "owner": stx.BPF_LOADER_UPGRADEABLE_ID,
                                      "data": [base64.b64encode(pdata).decode(), "base64"]}}
            raise AssertionError(f"unexpected {method} {params}")
        return fake

    def test_waits_until_confirmed_slot_passes_deploy_slot(self):
        prog, pdata = self._accounts(100)
        orig = stx.rpc
        stx.rpc = self._fake_rpc(prog, pdata, [99, 100, 100, 101])
        try:
            r = stx.wait_program_invocable("http://x", PROGRAM_ID, timeout_s=5, poll_s=0)
        finally:
            stx.rpc = orig
        self.assertEqual(r["last_deployed_slot"], 100)
        self.assertEqual(r["confirmed_slot"], 101)

    def test_times_out_when_slot_never_advances(self):
        prog, pdata = self._accounts(100)
        orig = stx.rpc
        stx.rpc = self._fake_rpc(prog, pdata, [100])
        try:
            with self.assertRaises(RuntimeError):
                stx.wait_program_invocable("http://x", PROGRAM_ID, timeout_s=0.2, poll_s=0.01)
        finally:
            stx.rpc = orig


if __name__ == "__main__":
    unittest.main()
