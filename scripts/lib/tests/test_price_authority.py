"""Unit tests for scripts/lib/price_authority.py (rule of 2026-10-04): min over material upstream paths, the 1% materiality
line, UNREAD -> 20 never 100, governance-grade timelocks disclosed, and the walk through an adapter to its Chainlink feeds.
The chain is a small fake: call_raw / safe_owners_and_threshold are patched in the module, get_code on a fake w3. No network."""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import price_authority as pa  # noqa: E402

A = lambda n: "0x" + f"{n:040x}"  # noqa: E731
SAFE49, SAFE22, EOA, TL2D, TL1H, TL0 = A(1), A(2), A(3), A(4), A(5), A(6)
FEED_ETH, FEED_BTC, ADAPTER, PROVIDER, PEGGED = A(10), A(11), A(12), A(13), A(14)


class FakeEth:
    def __init__(self, codes):
        self.codes = codes

    def get_code(self, a):
        return self.codes.get(a.lower(), b"")

    def get_storage_at(self, a, slot):
        return b"\x00" * 32  # no proxy slot set anywhere in this fake


class FakeW3:
    def __init__(self, codes):
        self.eth = FakeEth(codes)


def chain():
    """Two Chainlink proxies owned by a 4-of-9 Safe; an adapter reading ETH/USD plus a rate provider; a pegged adapter
    (ASSET_TO_PEG / PEG_TO_BASE) on the BTC feed; a 2-day and a 1-hour timelock; a 2-of-2 Safe; a bare EOA."""
    answers = {
        (FEED_ETH, "aggregator"): A(20), (FEED_ETH, "owner"): SAFE49, (A(20), "owner"): SAFE49,
        (FEED_BTC, "aggregator"): A(21), (FEED_BTC, "owner"): SAFE49, (A(21), "owner"): SAFE49,
        (ADAPTER, "BASE_TO_USD_AGGREGATOR"): FEED_ETH, (ADAPTER, "RATIO_PROVIDER"): PROVIDER,
        (PEGGED, "ASSET_TO_PEG"): FEED_BTC, (PEGGED, "PEG_TO_BASE"): FEED_BTC,
        (TL2D, "getMinDelay"): 2 * 86400, (TL1H, "getMinDelay"): 3600, (TL0, "getMinDelay"): 0,
    }
    safes = {SAFE49.lower(): ([A(100 + i) for i in range(9)], 4), SAFE22.lower(): ([A(200), A(201)], 2)}
    codes = {x.lower(): b"\x60" for x in (SAFE49, SAFE22, TL2D, TL1H, TL0, FEED_ETH, FEED_BTC, ADAPTER, PROVIDER, PEGGED, A(20), A(21))}

    answers = {(a.lower(), n): v for (a, n), v in answers.items()}  # the engine passes checksummed addresses

    def call_raw(w3, address, abi, name, *args, retries=4):
        return answers.get((address.lower(), name))
    return call_raw, (lambda w3, a, retries=4: safes.get(a.lower())), FakeW3(codes)


class TestScore(unittest.TestCase):
    def setUp(self):
        call, safe, self.w3 = chain()
        for name, fn in (("call_raw", call), ("safe_owners_and_threshold", safe)):
            p = mock.patch.object(pa, name, fn)
            p.start()
            self.addCleanup(p.stop)

    def spec(self, controller):
        return {PROVIDER: lambda w3, gov: [pa.controller_path(w3, controller, gov, "rate provider")]}

    def test_chainlink_and_adapter_walk_min_is_52(self):
        notes = []
        s = pa.score(self.w3, [("WETH", FEED_ETH, 600), ("weETH", ADAPTER, 300), ("WBTC", PEGGED, 100)], 86400, self.spec(TL2D), notes=notes)
        self.assertEqual(s, 52)  # Safe 4-of-9: (65, 85, 0) -> (260 + 255 + 5) // 10
        self.assertTrue(any("governance-grade" in n for n in notes))  # the 2-day provider is disclosed, not scored

    def test_material_unread_is_20_never_100(self):
        s = pa.score(self.w3, [("WETH", FEED_ETH, 600), ("weETH", ADAPTER, 400)], 86400, {})  # provider without a spec
        self.assertEqual(s, 20)

    def test_immaterial_unread_does_not_count(self):
        s = pa.score(self.w3, [("WETH", FEED_ETH, 9950), ("weETH", ADAPTER, 50)], 86400, {})  # provider at 0.5%
        self.assertEqual(s, 52)

    def test_unread_value_counts_as_material(self):
        s = pa.score(self.w3, [("WETH", FEED_ETH, 9950), ("weETH", ADAPTER, None)], 86400, {})
        self.assertEqual(s, 20)

    def test_weaker_material_path_sets_the_min_and_eoa_floor(self):
        self.assertEqual(pa.score(self.w3, [("WETH", FEED_ETH, 600), ("x", ADAPTER, 400)], 86400, self.spec(SAFE22)), 29)  # Safe 2-of-2: (50, 30, 0) -> (200 + 90 + 5) // 10
        self.assertEqual(pa.score(self.w3, [("WETH", FEED_ETH, 600), ("x", ADAPTER, 400)], 86400, self.spec(EOA)), 2)

    def test_short_timelock_is_not_governance_grade(self):
        self.assertEqual(pa.score(self.w3, [("WETH", FEED_ETH, 600), ("x", ADAPTER, 400)], 86400, self.spec(TL1H)), 20)

    def test_zero_delay_timelock_is_never_governance_grade(self):
        self.assertEqual(pa.controller_path(self.w3, TL0, 1800, "x")["status"], "UNREAD")
        self.assertEqual(pa.controller_path(self.w3, TL1H, 1800, "x")["status"], "governance-grade")
        for gov in (0, None):  # a target with no delay of its own (Morpho 1337: timelock() = 0) gives no governance-grade bar
            self.assertEqual(pa.controller_path(self.w3, TL1H, gov, "x")["status"], "UNREAD")

    def test_no_material_path_is_100(self):
        self.assertEqual(pa.score(self.w3, [("x", ADAPTER, 400)], 86400, {PROVIDER: lambda w3, g: []}, []), 52)  # ETH feed
        self.assertEqual(pa.score(self.w3, [], 86400, {}), 100)

    def test_unread_source_row(self):
        self.assertEqual(pa.score(self.w3, [("WETH", FEED_ETH, 600), ("x", None, 400)], 86400, {}), 20)


class Chain:
    """A configurable fake: answers[(address, getter)] or answers[(address, getter, args)], storage[(address, slot)], code."""
    def __init__(self, answers=None, safes=None, codes=None, storage=None, logs=0, raises=None):
        self.answers = {tuple([k[0].lower(), *k[1:]]): v for k, v in (answers or {}).items()}
        self.safes = {k.lower(): v for k, v in (safes or {}).items()}
        self.codes = {k.lower(): v for k, v in (codes or {}).items()}
        self.storage = {(a.lower(), sl): v for (a, sl), v in (storage or {}).items()}
        self.n_logs, self.raises = logs, raises
        self.eth = self

    def call_raw(self, w3, address, abi, name, *args, retries=4):
        if self.raises:
            raise self.raises
        return self.answers.get((address.lower(), name, args), self.answers.get((address.lower(), name)))

    def safe(self, w3, address, retries=4):
        return self.safes.get(address.lower())

    def get_code(self, a):
        return self.codes.get(a.lower(), b"")

    def get_storage_at(self, a, slot):
        v = self.storage.get((a.lower(), slot))
        return bytes(12) + bytes.fromhex(v[2:]) if v else bytes(32)

    block_number = 100

    def get_logs(self, flt):
        if isinstance(self.n_logs, Exception):
            raise self.n_logs
        return [{}] * self.n_logs


CODE = b"\x60\x00\xfa"  # PUSH1 0, STATICCALL: reads others, writes nothing
OWN_ACL, OTHER_ACL, GOV = A(30), A(31), A(32)
OWN_ADAPTER, FOREIGN_ADAPTER, WRAPPER, UUPS_WRAPPER, OWNED_FEED, DELEGATED, CONST, SSTORE_WRAPPER = (A(40 + i) for i in range(8))
PROXY, AGG = A(50), A(51)


class TestWalkBranches(unittest.TestCase):
    """The branches the 2026-10-04 review found fail-open, each pinned."""
    def run_score(self, chain, rows, own=(OWN_ACL, GOV), specs=None, gov=86400):
        notes = []
        with mock.patch.object(pa, "call_raw", chain.call_raw), mock.patch.object(pa, "safe_owners_and_threshold", chain.safe):
            return pa.score(chain, rows, gov, specs or {}, own, notes), notes

    def base(self, **extra):
        answers = {(PROXY, "aggregator"): AGG, (PROXY, "owner"): SAFE49, (AGG, "owner"): SAFE49}
        answers.update(extra.pop("answers", {}))
        codes = {x: CODE for x in (PROXY, AGG, SAFE49, OWN_ADAPTER, FOREIGN_ADAPTER, WRAPPER, UUPS_WRAPPER, OWNED_FEED, CONST, SSTORE_WRAPPER)}
        codes[DELEGATED] = b"\xef\x01\x00" + bytes.fromhex("1234567890abcdef1234567890abcdef12345678")
        codes[CONST] = b"\x60\x2a\x60\x00\x52"  # PUSH 42, MSTORE: a provable constant
        codes[SSTORE_WRAPPER] = b"\x60\x00\x55"
        codes.update(extra.pop("codes", {}))
        return Chain(answers=answers, safes={SAFE49: ([A(100 + i) for i in range(9)], 4)}, codes=codes, **extra)

    def test_own_adapter_walks_to_its_feed(self):
        c = self.base(answers={(OWN_ADAPTER, "ACL_MANAGER"): OWN_ACL, (OWN_ADAPTER, "ASSET_TO_USD_AGGREGATOR"): PROXY})
        self.assertEqual(self.run_score(c, [("x", OWN_ADAPTER, 100)])[0], 52)

    def test_own_adapter_without_upstream_is_unread_not_100(self):
        c = self.base(answers={(OWN_ADAPTER, "ACL_MANAGER"): OWN_ACL})
        s, notes = self.run_score(c, [("x", OWN_ADAPTER, 100)])
        self.assertEqual(s, 20)
        self.assertTrue(any("own adapter with no known upstream getter" in n for n in notes))

    def test_foreign_acl_adapter_is_unread(self):
        c = self.base(answers={(FOREIGN_ADAPTER, "ACL_MANAGER"): OTHER_ACL, (FOREIGN_ADAPTER, "ASSET_TO_USD_AGGREGATOR"): PROXY})
        s, notes = self.run_score(c, [("x", FOREIGN_ADAPTER, 100)])
        self.assertEqual(s, 20)
        self.assertTrue(any("foreign ACLManager" in n for n in notes))

    def test_manager_is_governor_wrapper_is_own(self):
        c = self.base(answers={(WRAPPER, "manager"): GOV, (WRAPPER, "assetToBaseAggregator"): PROXY}, codes={WRAPPER: b"\x60\x00\x55"})
        self.assertEqual(self.run_score(c, [("x", WRAPPER, 100)])[0], 52)  # stateful, but the target's own: walked through

    def test_immutable_wrapper_is_walked_through(self):
        c = self.base(answers={(WRAPPER, "source"): PROXY})
        self.assertEqual(self.run_score(c, [("x", WRAPPER, 100)])[0], 52)

    def test_upgradeable_or_stateful_wrapper_without_controller_is_unread(self):
        for wrapper, storage in ((UUPS_WRAPPER, {(UUPS_WRAPPER, pa.IMPL_SLOT): A(77)}), (SSTORE_WRAPPER, {})):
            with self.subTest(wrapper=wrapper):
                c = self.base(answers={(wrapper, "source"): PROXY}, storage=storage)
                s, notes = self.run_score(c, [("x", wrapper, 100)])
                self.assertEqual(s, 20)
                self.assertTrue(any("not provably immutable" in n for n in notes))

    def test_owned_feed_scores_its_owner(self):
        c = self.base(answers={(OWNED_FEED, "owner"): EOA})
        self.assertEqual(self.run_score(c, [("x", OWNED_FEED, 100)])[0], 2)
        c = self.base(storage={(OWNED_FEED, pa.ZEPPELIN_ADMIN_SLOT): EOA})  # FiatToken-style admin slot
        self.assertEqual(self.run_score(c, [("x", OWNED_FEED, 100)])[0], 2)

    def test_aggregator_without_owner_is_unread(self):
        c = self.base()
        c.answers.pop((AGG.lower(), "owner"))
        s, notes = self.run_score(c, [("x", PROXY, 100)])
        self.assertEqual(s, 20)
        self.assertTrue(any("aggregator without a readable owner" in n for n in notes))

    def test_eip7702_source_is_a_key_and_never_a_constant(self):
        c = self.base()
        with mock.patch.object(pa, "call_raw", c.call_raw):
            self.assertFalse(pa.is_provable_constant(c, DELEGATED))
        self.assertEqual(self.run_score(c, [("x", DELEGATED, 100)])[0], 2)

    def test_provable_constant_is_disclosed(self):
        s, notes = self.run_score(self.base(), [("x", CONST, 100)])
        self.assertEqual(s, 100)
        self.assertTrue(any("provable constant" in n for n in notes))

    def test_cbor_metadata_bytes_are_not_read_as_opcodes(self):
        # A real Solidity trailer after INVALID: {"ipfs": <34 bytes>, "solc": 0.8.19}, hash bytes that look like SSTORE / DELEGATECALL.
        meta = b"\xa2\x64ipfs\x58\x22" + b"\x55\xf4" * 17 + b"\x64solc\x43\x00\x08\x13"
        self.assertTrue(pa._no_opcode(b"\x60\x00\xfa\xfe" + meta + len(meta).to_bytes(2, "big"), (0x55, 0xF2, 0xF4, 0xFF)))
        self.assertFalse(pa._no_opcode(b"\x60\x00\x55", (0x55,)))

    def test_a_trailer_without_its_stop_byte_is_scanned(self):
        meta = b"\xa2\x64ipfs\x58\x22" + b"\x55" * 34 + b"\x64solc\x43\x00\x08\x13"
        self.assertFalse(pa._no_opcode(b"\x60\x00\xfa\x5b" + meta + len(meta).to_bytes(2, "big"), (0x55,)))  # JUMPDEST, not STOP/INVALID

    def test_beacon_proxy_without_owner_scores_its_beacon_owner(self):
        beacon = A(91)
        c = self.base(answers={(beacon, "owner"): EOA, (OWNED_FEED, "source"): PROXY},
                      storage={(OWNED_FEED, pa.BEACON_SLOT): beacon}, codes={beacon: CODE})
        self.assertEqual(self.run_score(c, [("x", OWNED_FEED, 100)])[0], 2)  # not 20: the beacon's owner is resolved

    @mock.patch("time.sleep", lambda s: None)
    def test_a_transient_node_error_is_retried(self):
        c = self.base()
        real, calls = c.get_code, []

        def flaky(a):
            calls.append(a)
            if len(calls) == 1:
                raise ConnectionError("429")
            return real(a)
        c.get_code = flaky
        self.assertEqual(self.run_score(c, [("x", PROXY, 100)])[0], 52)

    def test_a_trailer_with_a_reachable_jumpdest_is_scanned(self):  # third review: 0x64 swallows 'ipfs'+0x58, 5b is live
        code = bytes.fromhex("600f5600") + b"\xa2\x64ipfs\x58\x22" + bytes.fromhex("0000005b600160005500") + bytes.fromhex("0012")
        self.assertFalse(pa._no_opcode(code, (0x55,)))

    def test_a_real_hash_with_a_jumpdest_byte_is_still_metadata(self):  # live: the Morpho V2 oracle's ipfs hash holds a 5b
        h = b"\x5b\x47\x3c" + bytes(31)  # JUMPDEST, SELFBALANCE, EXTCODECOPY inside the hash
        meta = b"\xa2\x64ipfs\x58\x22" + h + b"\x64solc\x43\x00\x08\x13"
        code = b"\x60\x00\xfa\xfe" + meta + len(meta).to_bytes(2, "big")
        self.assertTrue(pa._no_opcode(code, pa._WRITES + pa._OUTSIDE_STATE))
        target = 4 + len(b"\xa2\x64ipfs\x58\x22")  # the same trailer, but the code pushes the JUMPDEST's offset: scanned
        code = bytes([0x61]) + target.to_bytes(2, "big") + b"\xfe" + meta + len(meta).to_bytes(2, "big")
        self.assertFalse(pa._no_opcode(code, pa._WRITES + pa._OUTSIDE_STATE))

    def test_an_oversized_trailer_is_scanned(self):  # real solc metadata is 0x33 bytes, 0x41 with "experimental"
        meta = b"\xa2\x64ipfs\x58\x22" + b"\x55" * 0x70
        self.assertFalse(pa._no_opcode(b"\x60\x00\xfa\xfe" + meta + len(meta).to_bytes(2, "big"), (0x55,)))

    def test_gas_and_builder_values_are_not_constant(self):
        for op in (0x5A, 0x3A, 0x41, 0x48, 0x4A, 0x45, 0x44, 0x40):
            with self.subTest(op=hex(op)):
                c = self.base(codes={CONST: bytes([op, 0x60, 0x00, 0x52])})
                with mock.patch.object(pa, "call_raw", c.call_raw):
                    self.assertFalse(pa.is_provable_constant(c, CONST))
        c = self.base(codes={CONST: bytes([0x42, 0x60, 0x00, 0x52])})  # TIMESTAMP: a fixed feed's updatedAt
        with mock.patch.object(pa, "call_raw", c.call_raw):
            self.assertTrue(pa.is_provable_constant(c, CONST))

    def test_a_fake_trailer_does_not_hide_code(self):  # second review: LOG1 + JUMPDEST + SSTORE, ending in a plausible length
        self.assertFalse(pa._no_opcode(bytes.fromhex("6000355ba1600160005500" + "0007"), (0x55, 0xF2, 0xF4, 0xFF)))

    def test_outside_state_is_never_constant_or_immutable(self):
        for op in (0x31, 0x47, 0x3C, 0x3F, 0x5C, 0x5D):  # balances, foreign code, transient storage
            with self.subTest(op=hex(op)):
                c = self.base(codes={CONST: bytes([0x60, 0x00, op])})
                with mock.patch.object(pa, "call_raw", c.call_raw):
                    self.assertFalse(pa.is_provable_constant(c, CONST))
                    self.assertFalse(pa.is_immutable_wrapper(c, CONST))
        c = self.base(codes={WRAPPER: b"\x60\x00\x3b\xfa"})  # EXTCODESIZE before a STATICCALL (solc < 0.8.10): still a wrapper
        with mock.patch.object(pa, "call_raw", c.call_raw):
            self.assertTrue(pa.is_immutable_wrapper(c, WRAPPER))
            self.assertFalse(pa.is_provable_constant(c, WRAPPER))

    def test_beacon_owner_and_proxy_admin_of_an_aggregator_source_are_scored(self):
        beacon = A(90)
        c = self.base(answers={(OWNED_FEED, "owner"): TL2D, (beacon, "owner"): EOA, (TL2D, "getMinDelay"): 2 * 86400},
                      storage={(OWNED_FEED, pa.BEACON_SLOT): beacon}, codes={TL2D: CODE, beacon: CODE})
        s, notes = self.run_score(c, [("x", OWNED_FEED, 100)])
        self.assertEqual(s, 2)  # owner() is a governance-grade timelock; the beacon's owner is a bare key
        self.assertTrue(any("governance-grade" in n for n in notes))
        c = self.base(storage={(PROXY, pa.ADMIN_SLOT): EOA})  # answers aggregator() but is an upgradeable proxy
        self.assertEqual(self.run_score(c, [("x", PROXY, 100)])[0], 2)
        c = self.base(answers={(beacon, "owner"): EOA}, storage={(PROXY, pa.BEACON_SLOT): beacon}, codes={beacon: CODE})
        self.assertEqual(self.run_score(c, [("x", PROXY, 100)])[0], 2)  # answers aggregator() and is a beacon proxy

    def test_safe_gate_findings_stay_in_the_price_path(self):
        c = self.base()
        log = pa._wu._AUTHORITY_GATE_LOG

        def gated(w3, address, retries=4):
            log.append((address, "blocking", "unanalyzed module 0xabc"))
            return None
        c.safe = gated
        before = len(log)
        s, notes = self.run_score(c, [("x", PROXY, 100)])
        self.assertEqual(s, 20)
        self.assertEqual(len(log), before, "the consumer's own entry must not inherit a price-path Safe's gate finding")
        self.assertTrue(any("unanalyzed module" in n for n in notes))


class TestSpecsFailClosed(unittest.TestCase):
    def call(self, spec, chain, gov=86400):
        with mock.patch.object(pa, "call_raw", chain.call_raw):
            return spec(chain, gov)

    def test_every_spec_is_unread_when_its_facts_are_unread(self):
        empty = Chain()
        for spec in (pa._etherfi_weeth, pa._lido_steth, pa._kelp_rseth, pa._stakewise_oseth, pa._monad_fixed_musd):
            with self.subTest(spec=spec.__name__):
                paths = self.call(spec, empty)
                self.assertTrue(paths and all(p["status"] == "UNREAD" for p in paths), paths)

    def rseth_chain(self, logs):
        oracle, config, admin = "0x349A73444b1a310BAe67ef67973022020d70020d", "0x947Cb49334e6571ccBFEF1f1f1178d8469D65ec7", "0xb3696a817D01C8623E66D156B6798291fa10a46d"
        c = Chain(answers={(oracle, "lrtConfig"): config, (config, "hasRole"): True}, logs=logs)
        c.block_number = pa.RSETH_PROOF_BLOCK + 5  # one chunk to replay
        return c

    @mock.patch("time.sleep", lambda s: None)
    def test_rseth_admin_change_since_the_proof_is_unread(self):
        for logs, why in ((2, "grant/revoke"), (ConnectionError("down"), "replay")):
            with self.subTest(logs=logs):
                paths = self.call(pa._kelp_rseth, self.rseth_chain(logs))
                self.assertEqual([p["status"] for p in paths], ["UNREAD"])
                self.assertIn(why, paths[0]["note"])
        paths = self.call(pa._kelp_rseth, self.rseth_chain(0))  # no change since the proof: the admin path is scored
        self.assertEqual((paths[0]["status"], paths[0]["composite"]), ("scored", 2))  # the fake admin has no code: a bare key

    def test_weeth_needs_the_upgrade_timelock_as_registry_owner(self):
        rr, up, op = "0x62247D29B4B9BECf4BB73E0c722cf6445cfC7cE9", "0x9f26d4C958fD811A1F59B01B86Be7dFFc9d20761", "0xcD425f44758a08BaAB3C4908f3e3dE5776e45d7a"
        answers = {(up, "getMinDelay"): 10 * 86400, (op, "getMinDelay"): 2 * 86400, ("0x0EF8fa4760Db8f5Cd4d993f3e3416f30f942D705", "maxAcceptableRebaseAprInBps"): 1000}
        roles = {"5ba17a247620ef8426ae0fffc28eee4ee4b18eb3b8bcfa95664565c35371dfb5": up, "e6bda0fc5c63b525e475d178ed9c7fa9913b3429ade866197b11eb0f2c18c673": op}
        for role, tl in roles.items():
            answers[(rr, "roleHolders", (bytes.fromhex(role),))] = [tl]
        ok = {**answers, (rr, "owner"): up}
        self.assertEqual(self.call(pa._etherfi_weeth, Chain(answers=ok))[0]["status"], "governance-grade")
        for gov in (0, None):
            self.assertEqual(self.call(pa._etherfi_weeth, Chain(answers=ok), gov)[0]["status"], "UNREAD")
        bad = {**answers, (rr, "owner"): EOA}
        self.assertEqual(self.call(pa._etherfi_weeth, Chain(answers=bad))[0]["status"], "UNREAD")


class TestLidoShape(unittest.TestCase):
    TL, EX = pa._cs("0xCE0425301C85c5Ea2A0873A2dEe44d78E02D2316"), pa._cs("0x23E0B465633fF5178808F4A75186E2F2F9537021")
    ACL, AGENT, VOTING = (pa._cs(x) for x in ("0x9895F0F17cc1d1891b6f18ee0b483B6f221b37Bb", "0x3e40D73EB977Dc6a537aF587D48316feE66E9C8c",
                                                "0x2e59A20f205bB85a89C53f1936454680651E618e"))

    def status(self, gov=86400, **override):
        execute, run_script = pa.Web3.keccak(text="EXECUTE_ROLE"), pa.Web3.keccak(text="RUN_SCRIPT_ROLE")
        facts = {"after": 259200, "emergency": False, "owner": self.TL, "ex_exec": True, "vote_exec": False, "vote_run": False}
        facts.update(override)
        answers = {(self.TL, "getAfterSubmitDelay"): facts["after"], (self.TL, "isEmergencyModeActive"): facts["emergency"],
                   (self.EX, "owner"): facts["owner"],
                   (self.ACL, "hasPermission", (self.EX, self.AGENT, execute)): facts["ex_exec"],
                   (self.ACL, "hasPermission", (self.VOTING, self.AGENT, execute)): facts["vote_exec"],
                   (self.ACL, "hasPermission", (self.VOTING, self.AGENT, run_script)): facts["vote_run"]}
        c = Chain(answers=answers)
        with mock.patch.object(pa, "call_raw", c.call_raw):
            return pa._lido_steth(c, gov)[0]["status"]

    def test_verified_shape_is_governance_grade_and_every_deviation_unread(self):
        self.assertEqual(self.status(), "governance-grade")
        for gov in (0, None):  # a target with no delay of its own gives no governance-grade bar
            self.assertEqual(self.status(gov=gov), "UNREAD")
        for override in ({"vote_run": True}, {"vote_run": None}, {"vote_exec": True}, {"ex_exec": False}, {"emergency": True},
                         {"after": 3600}, {"owner": EOA}):
            with self.subTest(**{k: str(v) for k, v in override.items()}):
                self.assertEqual(self.status(**override), "UNREAD")


class TestEntryPointsAndRows(unittest.TestCase):
    def test_a_raised_read_gives_20_and_a_note_never_a_crash(self):
        c = Chain(raises=ConnectionError("rpc down"))
        for fn in (pa.for_aave, pa.for_comet, pa.for_morpho_v1):
            with self.subTest(fn=fn.__name__), mock.patch.object(pa, "call_raw", c.call_raw):
                notes = []
                self.assertEqual(fn(c, A(1), None, notes), 20)
                self.assertTrue(any(pa.FAILED_MARK in n for n in notes))

    def test_unread_rows_give_20_with_the_mark_the_push_guard_reads(self):
        import push_guard
        c = Chain()
        for fn in (pa.for_aave, pa.for_comet, pa.for_morpho_v1):
            with self.subTest(fn=fn.__name__), mock.patch.object(pa, "call_raw", c.call_raw):
                notes = []
                self.assertEqual(fn(c, A(1), None, notes), 20)
                self.assertTrue(any(push_guard.ORACLE_UNREAD.search(n) for n in notes))

    def test_aave_rows_values_and_unread(self):
        prov, pool, oracle, a1, a2, at1 = A(60), A(61), A(62), A(63), A(64), A(65)
        data = [0] * 8 + [at1] + [0] * 6
        c = Chain(answers={(prov, "getPool"): pool, (prov, "getPriceOracle"): oracle, (pool, "getReservesList"): [a1, a2],
                           (oracle, "BASE_CURRENCY_UNIT"): 10 ** 8, (oracle, "getSourceOfAsset", (a1,)): PROXY,
                           (oracle, "getAssetPrice", (a1,)): 2 * 10 ** 8, (pool, "getReserveData", (a1,)): data, (a1, "decimals"): 6,
                           (at1, "totalSupply"): 5 * 10 ** 6})
        with mock.patch.object(pa, "call_raw", c.call_raw):
            rows = pa.aave_rows(c, prov)
        self.assertEqual(rows[0], (a1, pa.Web3.to_checksum_address(PROXY), 10.0))  # 5 tokens at $2
        self.assertEqual(rows[1][2], None)  # a2 unread: value None, which score() counts as material

    def test_comet_rows_values(self):
        comet, base_feed, asset, feed = A(70), A(71), A(72), A(73)
        info = (0, asset, feed, 10 ** 18, 0, 0, 0, 0)
        c = Chain(answers={(comet, "numAssets"): 1, (comet, "baseTokenPriceFeed"): base_feed, (comet, "totalSupply"): 3 * 10 ** 6,
                           (comet, "baseScale"): 10 ** 6, (comet, "getPrice", (base_feed,)): 10 ** 8, (comet, "baseToken"): A(74),
                           (comet, "getAssetInfo", (0,)): info, (comet, "totalsCollateral", (asset,)): (2 * 10 ** 18, 0),
                           (comet, "getPrice", (feed,)): 4 * 10 ** 8})
        with mock.patch.object(pa, "call_raw", c.call_raw):
            rows = pa.comet_rows(c, comet)
        self.assertEqual([r[2] for r in rows], [3.0, 8.0])  # 3 USDC at $1; 2 units at $4

    def test_morpho_v1_rows_skip_idle_and_convert_shares(self):
        vault, morpho, m1, m2, oracle = A(80), "0xBBBBBbbBBb9cC5e90e3b3Af64bdAF62C37EEFFCb", b"\x01" * 32, b"\x02" * 32, A(81)
        c = Chain(answers={(vault, "withdrawQueueLength"): 2, (vault, "withdrawQueue", (0,)): m1, (vault, "withdrawQueue", (1,)): m2,
                           (morpho, "idToMarketParams", (m1,)): (A(1), A(2), oracle, A(3), 0),
                           (morpho, "idToMarketParams", (m2,)): (A(1), "0x" + "00" * 20, "0x" + "00" * 20, A(3), 0),
                           (morpho, "position", (m1, pa.Web3.to_checksum_address(vault))): (500, 0, 0),
                           (morpho, "position", (m2, pa.Web3.to_checksum_address(vault))): (1, 0, 0),
                           (morpho, "market", (m1,)): (2000, 1000, 0, 0, 0, 0), (morpho, "market", (m2,)): (1, 1, 0, 0, 0, 0)})
        with mock.patch.object(pa, "call_raw", c.call_raw):
            rows = pa.morpho_v1_rows(c, vault)
        self.assertEqual(rows, [(m1.hex(), pa.Web3.to_checksum_address(oracle), 1000)])  # 500 shares * 2000 / 1000; idle m2 skipped


class TestSlotConstants(unittest.TestCase):
    def test_each_slot_is_its_published_derivation(self):  # a wrong constant silently disables a proxy check (BEACON_SLOT was)
        k = lambda t: int.from_bytes(pa.Web3.keccak(text=t), "big")  # noqa: E731
        self.assertEqual(pa.IMPL_SLOT, k("eip1967.proxy.implementation") - 1)
        self.assertEqual(pa.ADMIN_SLOT, k("eip1967.proxy.admin") - 1)
        self.assertEqual(pa.BEACON_SLOT, k("eip1967.proxy.beacon") - 1)
        self.assertEqual(pa.ZEPPELIN_IMPL_SLOT, k("org.zeppelinos.proxy.implementation"))
        self.assertEqual(pa.ZEPPELIN_ADMIN_SLOT, k("org.zeppelinos.proxy.admin"))


class TestSafeRootedMatchesTheRepoConvention(unittest.TestCase):
    def test_same_as_lib_scorers(self):
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
        from lib.scorers import _safe_rooted_scores
        for t in range(1, 8):
            for n in range(t, 12):
                self.assertEqual(pa._safe_rooted(t, n), _safe_rooted_scores(t, n), (t, n))


if __name__ == "__main__":
    unittest.main()
