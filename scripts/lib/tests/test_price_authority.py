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

    def test_a_tuple_source_walks_each_and_its_value_reaches_every_path(self):
        notes = []
        s = pa.score(self.w3, [("vault", (FEED_ETH, ADAPTER), 500), ("other", FEED_BTC, 9500)], 86400, self.spec(EOA), notes=notes)
        self.assertEqual(s, 2)  # the second element's rate provider, a bare EOA, at the row's 5%
        self.assertTrue(any("rate provider: scored, composite 2, reach 5.00%" in n for n in notes))
        self.assertTrue(any(f"{FEED_ETH} owner" in n and "reach 5.00%" in n for n in notes))  # the first element, same row value
        self.assertEqual(pa.score(self.w3, [("vault", (FEED_ETH, ADAPTER), 50), ("other", FEED_BTC, 9950)], 86400, self.spec(EOA)), 52)  # 0.5%: immaterial


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
    chain_id = 1
    now = 1_800_000_000

    def get_block(self, which):
        return {"timestamp": self.now}

    def get_logs(self, flt):
        if isinstance(self.n_logs, Exception):
            raise self.n_logs
        return [{}] * self.n_logs


CODE = b"\x60\x00\xfa"  # PUSH1 0, STATICCALL: reads others, writes nothing
# The fakes' timelocks carry CODE (or the one-byte code of chain()): accepted as a verified timelock build in these tests;
# TestShortTimelocks.test_an_unverified_timelock_build_is_unread checks the rule itself.
_FAKE_TIMELOCKS = mock.patch.dict(pa.VERIFIED_TIMELOCKS, {pa.Web3.keccak(c).hex().removeprefix("0x"): "test fake" for c in (CODE, b"\x60")})


def setUpModule():
    _FAKE_TIMELOCKS.start()


def tearDownModule():
    _FAKE_TIMELOCKS.stop()
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

    def test_a_wrapper_owned_by_the_target_is_its_own(self):
        c = self.base(answers={(WRAPPER, "owner"): GOV, (WRAPPER, "priceFeed"): PROXY}, codes={WRAPPER: b"\x60\x00\x55"})
        self.assertEqual(self.run_score(c, [("x", WRAPPER, 100)])[0], 52)  # stateful, owned by the governor: walked to its feed
        c = self.base(answers={(WRAPPER, "DOLOMITE_MARGIN"): GOV, (WRAPPER, "priceFeed"): PROXY}, codes={WRAPPER: b"\x60\x00\x55"})
        self.assertEqual(self.run_score(c, [("x", WRAPPER, 100)])[0], 52)
        c = self.base(answers={(WRAPPER, "owner"): GOV}, codes={WRAPPER: b"\x60\x00\x55"})
        s, notes = self.run_score(c, [("x", WRAPPER, 100)])
        self.assertEqual(s, 20)  # own, but its input is not seen
        self.assertTrue(any("own adapter with no known upstream getter" in n for n in notes))

    def test_an_owned_wrapper_someone_else_can_upgrade_is_not_own(self):
        admin, beacon = A(92), A(93)
        for storage, extra in (({(WRAPPER, pa.ADMIN_SLOT): admin}, {(admin, "owner"): EOA}), ({(WRAPPER, pa.BEACON_SLOT): beacon}, {(beacon, "owner"): EOA})):
            with self.subTest(storage=storage):
                c = self.base(answers={(WRAPPER, "owner"): GOV, (WRAPPER, "priceFeed"): PROXY, **extra}, storage=storage, codes={admin: CODE, beacon: CODE})
                self.assertEqual(self.run_score(c, [("x", WRAPPER, 100)])[0], 2)  # controller-of: the foreign key is scored
        c = self.base(answers={(WRAPPER, "owner"): GOV, (WRAPPER, "priceFeed"): PROXY, (admin, "owner"): GOV}, storage={(WRAPPER, pa.ADMIN_SLOT): admin}, codes={admin: CODE})
        self.assertEqual(self.run_score(c, [("x", WRAPPER, 100)])[0], 52)  # its ProxyAdmin is owned by the governor too

    def test_an_eth_source_wrapper_needs_exactly_one_rate_leg(self):
        rate = A(94)
        c = self.base(answers={(WRAPPER, "ethSource"): PROXY, (WRAPPER, "reth"): rate})
        s, notes = self.run_score(c, [("x", WRAPPER, 100)], specs={rate: lambda w3, g: [pa.path("r", "scored", 7)]})
        self.assertEqual(s, 7)  # both legs walked: ETH/USD (52) and the rate (7)
        for extra in ({}, {(WRAPPER, "oracle"): A(95)}):  # no rate leg seen, or two
            with self.subTest(extra=extra):
                answers = {(WRAPPER, "ethSource"): PROXY, **({(WRAPPER, "reth"): rate} if extra else {}), **extra}
                s, notes = self.run_score(self.base(answers=answers), [("x", WRAPPER, 100)])
                self.assertEqual(s, 20)
                self.assertTrue(any("ethSource() wrapper" in n for n in notes))

    def test_base_is_followed_only_with_a_multiplier(self):
        token, mult = A(97), A(98)  # an Euler adapter's base() is a token whose owner sets no price
        c = self.base(answers={(WRAPPER, "base"): token, (token, "owner"): EOA, (WRAPPER, "source"): PROXY}, codes={token: CODE})
        self.assertEqual(self.run_score(c, [("x", WRAPPER, 100)])[0], 52)
        c = self.base(answers={(WRAPPER, "base"): PROXY, (WRAPPER, "multiplier"): mult, (mult, "owner"): EOA}, codes={mult: CODE})
        self.assertEqual(self.run_score(c, [("x", WRAPPER, 100)])[0], 2)  # a composite: both legs walked
        c = self.base(answers={(WRAPPER, "base"): PROXY, (WRAPPER, "multiplier"): A(10 ** 18)})  # a uint read as an address: no code
        s, notes = self.run_score(c, [("x", WRAPPER, 100)])
        self.assertEqual(s, 20)  # UNREAD, never a bare key scoring 2
        self.assertTrue(any("answered an address with no code" in n for n in notes))

    def test_oracle_alone_is_not_followed(self):  # a GMX data-stream provider's oracle() is GMX's own Oracle, not an input
        c = self.base(answers={(WRAPPER, "oracle"): A(96), (WRAPPER, "source"): PROXY})
        self.assertEqual(self.run_score(c, [("x", WRAPPER, 100)])[0], 52)

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
        for spec in (pa._etherfi_weeth, pa._lido_steth, pa._kelp_rseth, pa._stakewise_oseth, pa._monad_fixed_musd,
                     pa._midas_mglo_feed, pa._robinhood_stock_beacon):
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

    def weeth_chain(self, owner, logs=0, proposer_holds=True):
        rr, up, op = "0x62247D29B4B9BECf4BB73E0c722cf6445cfC7cE9", "0x9f26d4C958fD811A1F59B01B86Be7dFFc9d20761", "0xcD425f44758a08BaAB3C4908f3e3dE5776e45d7a"
        answers = {(up, "getMinDelay"): 10 * 86400, (op, "getMinDelay"): 2 * 86400, ("0x0EF8fa4760Db8f5Cd4d993f3e3416f30f942D705", "maxAcceptableRebaseAprInBps"): 1000,
                   (rr, "owner"): owner, (op, "hasRole"): proposer_holds, (up, "hasRole"): proposer_holds}
        roles = {"5ba17a247620ef8426ae0fffc28eee4ee4b18eb3b8bcfa95664565c35371dfb5": up, "e6bda0fc5c63b525e475d178ed9c7fa9913b3429ade866197b11eb0f2c18c673": op}
        for role, tl in roles.items():
            answers[(rr, "roleHolders", (bytes.fromhex(role),))] = [tl]
        safe = "0x2aCA71020De61bb532008049e1Bd41E451aE8AdC"
        c = Chain(answers=answers, codes={up: CODE, op: CODE, safe: CODE, "0xcdd57D11476c22d265722F68390b036f3DA48c21": CODE},
                  safes={safe: ([A(100 + i) for i in range(7)], 4), "0xcdd57D11476c22d265722F68390b036f3DA48c21": ([A(120 + i) for i in range(10)], 6)}, logs=logs)
        c.block_number = 26125251 + 3
        return c

    def weeth(self, chain, gov):
        h = pa.Web3.keccak(CODE).hex().removeprefix("0x")
        pins = {k: v[:3] + (h,) for k, v in pa.TIMELOCK_HOLDERS.items() if v[0] == 1}
        with mock.patch.object(pa, "safe_owners_and_threshold", chain.safe), mock.patch.dict(pa.TIMELOCK_HOLDERS, pins):
            return [(p["status"], p["composite"]) for p in self.call(pa._etherfi_weeth, chain, gov)]

    @mock.patch("time.sleep", lambda s: None)
    def test_weeth_timelocks_are_controller_paths(self):
        up = "0x9f26d4C958fD811A1F59B01B86Be7dFFc9d20761"
        self.assertEqual(self.weeth(self.weeth_chain(up), 86400), [("governance-grade", None)] * 2)
        # a 7-day target: UPGRADE (10 d) governance-grade, OPERATION (2 d) its pinned proposer, a Safe 4-of-7, behind 2 days
        self.assertEqual(self.weeth(self.weeth_chain(up), 7 * 86400), [("governance-grade", None), ("scored", pa.composite(65, 75, 60))])
        for gov in (0, None):  # no bar: both proposers scored behind their delays
            self.assertEqual(self.weeth(self.weeth_chain(up), gov), [("scored", pa.composite(65, 100, 60)), ("scored", pa.composite(65, 75, 60))])
        for chain in (self.weeth_chain(up, logs=1), self.weeth_chain(up, proposer_holds=False), self.weeth_chain(up, logs=ConnectionError("down"))):
            with self.subTest(chain=chain):
                self.assertEqual(self.weeth(chain, 7 * 86400)[1][0], "UNREAD")
        self.assertEqual(self.weeth(self.weeth_chain(EOA), 86400), [("UNREAD", None)])


class TestLidoShape(unittest.TestCase):
    TL, EX = pa._cs("0xCE0425301C85c5Ea2A0873A2dEe44d78E02D2316"), pa._cs("0x23E0B465633fF5178808F4A75186E2F2F9537021")
    ACL, AGENT, VOTING = (pa._cs(x) for x in ("0x9895F0F17cc1d1891b6f18ee0b483B6f221b37Bb", "0x3e40D73EB977Dc6a537aF587D48316feE66E9C8c",
                                                "0x2e59A20f205bB85a89C53f1936454680651E618e"))
    DG, IMPL = A(900), A(901)

    def status(self, gov=86400, **override):
        execute, run_script = pa.Web3.keccak(text="EXECUTE_ROLE"), pa.Web3.keccak(text="RUN_SCRIPT_ROLE")
        facts = {"after": 259200, "schedule": 86400, "vote": 432000, "emergency": False, "owner": self.TL, "ex_exec": True, "vote_exec": False,
                 "vote_run": False, "proposers": [(self.VOTING, self.EX)], "impl": self.IMPL, "impl_code": CODE, "protection": False}
        facts.update(override)
        answers = {(self.TL, "getAfterSubmitDelay"): facts["after"], (self.TL, "getAfterScheduleDelay"): facts["schedule"],
                   (self.TL, "isEmergencyProtectionEnabled"): facts["protection"],
                   (self.VOTING, "voteTime"): facts["vote"], (self.TL, "isEmergencyModeActive"): facts["emergency"],
                   (self.EX, "owner"): facts["owner"], (self.TL, "getGovernance"): self.DG, (self.DG, "getProposers"): facts["proposers"],
                   (self.VOTING, "implementation"): facts["impl"],
                   (self.ACL, "hasPermission", (self.EX, self.AGENT, execute)): facts["ex_exec"],
                   (self.ACL, "hasPermission", (self.VOTING, self.AGENT, execute)): facts["vote_exec"],
                   (self.ACL, "hasPermission", (self.VOTING, self.AGENT, run_script)): facts["vote_run"]}
        c = Chain(answers=answers, codes={self.IMPL: facts["impl_code"]})
        pin = (self.IMPL, pa.Web3.keccak(CODE).hex().removeprefix("0x"))
        with mock.patch.object(pa, "call_raw", c.call_raw), mock.patch.object(pa, "LIDO_VOTING_IMPL", pin):
            return pa._lido_steth(c, gov)[0]["status"]

    def test_verified_shape_is_governance_grade_and_every_deviation_unread(self):
        self.assertEqual(self.status(), "governance-grade")
        for gov in (0, None):  # a target with no delay of its own gives no governance-grade bar
            self.assertEqual(self.status(gov=gov), "UNREAD")
        for override in ({"vote_run": True}, {"vote_run": None}, {"vote_exec": True}, {"ex_exec": False}, {"emergency": True},
                         {"owner": EOA}, {"vote": None}, {"schedule": None}, {"proposers": [(self.VOTING, self.EX), (EOA, self.EX)]},
                         {"proposers": None}, {"impl": A(902)}, {"impl_code": b"\x60\x01"}, {"protection": None}):
            with self.subTest(**{k: str(v) for k, v in override.items()}):
                self.assertEqual(self.status(**override), "UNREAD")

    def test_the_window_counts_the_vote_and_both_timelock_stages(self):
        window = 432000 + 259200 + 86400  # 9 days, from the vote's start to execution
        self.assertEqual(self.status(gov=7 * 86400), "governance-grade")  # the 7-day Morpho vaults
        self.assertEqual(self.status(gov=window), "governance-grade")
        self.assertEqual(self.status(gov=window + 1), "UNREAD")
        self.assertEqual(self.status(gov=7 * 86400, vote=86400), "UNREAD")  # a 1-day vote: 5 days in all
        # emergency protection on: the committees can skip afterSchedule, so the window is 5 + 3 = 8 days
        self.assertEqual(self.status(gov=window - 86400, protection=True), "governance-grade")
        self.assertEqual(self.status(gov=window - 86400 + 1, protection=True), "UNREAD")


class TestShortTimelocks(unittest.TestCase):
    """Decision of 2026-10-05: a timelock shorter than the target's delay is a controller path through the accounts that can
    schedule on it, scored behind its delay (delay_points); unknown holders stay UNREAD."""
    TL, PROP, SAFE7 = "0xcD425f44758a08BaAB3C4908f3e3dE5776e45d7a", "0x2aCA71020De61bb532008049e1Bd41E451aE8AdC", A(950)

    def path(self, chain, address, gov, delay=0):
        with mock.patch.object(pa, "call_raw", chain.call_raw), mock.patch.object(pa, "safe_owners_and_threshold", chain.safe):
            return pa.controller_path(chain, address, gov, "x", delay=delay)

    def test_delay_points_follow_the_notice_curve_capped_at_60(self):
        self.assertEqual([pa.delay_points(h * 3600) for h in (0, 1, 6, 12, 24, 36, 48, 168, 24 * 30)], [0, 2, 13, 25, 50, 55, 60, 60, 60])
        self.assertEqual(pa.delay_points(None), 0)

    def test_an_account_behind_a_delay_is_credited(self):
        c = Chain(codes={self.SAFE7: CODE}, safes={self.SAFE7: ([A(i) for i in range(7)], 4)})
        self.assertEqual(self.path(c, EOA, 7 * 86400, delay=86400)["composite"], pa.composite(5, 0, 50))
        self.assertEqual(self.path(c, self.SAFE7, 7 * 86400, delay=2 * 86400)["composite"], pa.composite(65, 75, 60))
        self.assertEqual(self.path(c, self.SAFE7, 7 * 86400)["composite"], pa.composite(65, 75, 0))  # no delay: unchanged

    def setUp(self):
        pin = pa.TIMELOCK_HOLDERS[self.TL.lower()]
        p = mock.patch.dict(pa.TIMELOCK_HOLDERS, {self.TL.lower(): pin[:3] + (pa.Web3.keccak(CODE).hex().removeprefix("0x"),)})
        p.start()
        self.addCleanup(p.stop)

    def chain(self, **kw):
        answers = {(self.TL, "getMinDelay"): 2 * 86400, (self.TL, "hasRole"): kw.pop("holds", True)}
        c = Chain(answers=answers, codes={self.TL: CODE, self.PROP: CODE}, safes={self.PROP: ([A(i) for i in range(7)], 4)}, **kw)
        c.block_number = pa.TIMELOCK_HOLDERS[self.TL.lower()][1] + 2
        return c

    @mock.patch("time.sleep", lambda s: None)
    def test_a_pinned_timelock_scores_its_proposer_and_every_doubt_is_unread(self):
        p = self.path(self.chain(), self.TL, 7 * 86400)
        self.assertEqual((p["status"], p["composite"]), ("scored", pa.composite(65, 75, 60)))
        self.assertIn("pinned at block", p["note"])
        self.assertEqual(self.path(self.chain(), self.TL, 2 * 86400)["status"], "governance-grade")
        for c in (self.chain(holds=False), self.chain(logs=1), self.chain(logs=ConnectionError("down"))):
            with self.subTest(c=c):
                self.assertEqual(self.path(c, self.TL, 7 * 86400)["status"], "UNREAD")
        other = self.chain()
        other.chain_id = 8453  # the pin is for Ethereum
        self.assertEqual(self.path(other, self.TL, 7 * 86400)["status"], "UNREAD")
        other = self.chain()
        other.codes[self.TL.lower()] = b"\x60\x01"  # another build at the same address: not the pinned code
        p = self.path(other, self.TL, 7 * 86400)
        self.assertEqual(p["status"], "UNREAD")
        self.assertIn("not a verified timelock build", p["note"])  # caught before the pin is read

    def test_an_unverified_timelock_build_is_unread(self):
        c = Chain(answers={(TL2D, "getMinDelay"): 30 * 86400}, codes={TL2D: b"\x60\x02"})  # long delay, unlisted code
        p = self.path(c, TL2D, 7 * 86400)
        self.assertEqual(p["status"], "UNREAD")
        self.assertIn("not a verified timelock build", p["note"])
        c.storage[(TL2D.lower(), pa.IMPL_SLOT)] = A(9)  # a listed build behind a proxy is not that build either
        c.codes[TL2D.lower()] = CODE
        self.assertEqual(self.path(c, TL2D, 7 * 86400)["status"], "UNREAD")

    def test_an_unpinned_timelock_stays_unread(self):
        c = Chain(answers={(TL2D, "getMinDelay"): 2 * 86400}, codes={TL2D: CODE})
        p = self.path(c, TL2D, 7 * 86400)
        self.assertEqual(p["status"], "UNREAD")
        self.assertIn("not pinned", p["note"])

    def test_a_compound_timelock_scores_its_admin_and_pending_admin(self):
        tl = A(960)
        answers = {(tl, "delay"): 2 * 86400, (tl, "GRACE_PERIOD"): 14 * 86400, (tl, "MINIMUM_DELAY"): 86400, (tl, "MAXIMUM_DELAY"): 30 * 86400,
                   (tl, "admin"): self.SAFE7}
        c = Chain(answers=answers, codes={tl: CODE, self.SAFE7: CODE}, safes={self.SAFE7: ([A(i) for i in range(7)], 4)})
        self.assertEqual(self.path(c, tl, 7 * 86400)["composite"], pa.composite(65, 75, 60))
        c.answers[(tl.lower(), "pendingAdmin")] = EOA  # a pending admin takes over at once: the worst of the two
        self.assertEqual(self.path(c, tl, 7 * 86400)["composite"], pa.composite(5, 0, 60))
        c.answers.pop((tl.lower(), "GRACE_PERIOD"))  # delay() without the Compound shape: not resolved
        self.assertEqual(self.path(c, tl, 7 * 86400)["status"], "UNREAD")

    def test_nested_timelocks_add_up(self):
        outer, inner = A(970), A(971)
        c = Chain(answers={(outer, "getMinDelay"): 4 * 86400, (inner, "getMinDelay"): 3 * 86400, (outer, "hasRole"): True},
                  codes={outer: CODE, inner: CODE})
        c.block_number = 12
        with mock.patch.dict(pa.TIMELOCK_HOLDERS, {outer.lower(): (1, 10, (("PROPOSER_ROLE", inner),), pa.Web3.keccak(CODE).hex().removeprefix("0x"))}):
            self.assertEqual(self.path(c, outer, 7 * 86400)["status"], "governance-grade")  # 4 d + 3 d >= 7 d
            self.assertEqual(self.path(c, outer, 8 * 86400)["status"], "UNREAD")  # 7 d < 8 d and the inner one is not pinned


class TestSkyAndVaultV2(unittest.TestCase):
    PP, PAUSE, CHIEF, HAT = pa._cs(pa.SKY_PAUSE_PROXY), pa._cs(pa.SKY_PAUSE), pa._cs(pa.SKY_CHIEF), A(980)

    def gov_answers(self, delay=172800):
        return {(self.PP, "owner"): self.PAUSE, (self.PAUSE, "authority"): self.CHIEF, (self.PAUSE, "delay"): delay,
                (self.CHIEF, "hat"): self.HAT, (self.HAT, "done"): True}

    def gov(self, answers, target):
        c = Chain(answers=answers)
        with mock.patch.object(pa, "call_raw", c.call_raw):
            return pa.sky_governance_path(c, target, "sky")

    def test_sky_governance_is_its_convention_below_the_bar(self):
        p = self.gov(self.gov_answers(), 7 * 86400)
        self.assertEqual((p["status"], p["composite"]), ("scored", 81))
        self.assertEqual(self.gov(self.gov_answers(), 2 * 86400)["status"], "governance-grade")
        no_hat = {**self.gov_answers(), (self.HAT, "done"): None}
        self.assertEqual(self.gov(no_hat, 7 * 86400)["composite"], pa.composite(20, 100, 70))
        short = self.gov_answers(delay=3600)
        self.assertEqual(self.gov(short, 7 * 86400)["composite"], pa.composite(75, 100, pa.delay_points(3600)))
        for k in ((self.PP, "owner"), (self.PAUSE, "authority"), (self.PAUSE, "delay")):
            with self.subTest(k=k):
                a = self.gov_answers()
                a.pop(k)
                self.assertEqual(self.gov(a, 7 * 86400)["status"], "UNREAD")

    def susds_chain(self, logs=0, override=None):
        s, beam, mom = pa._cs(pa.SKY_SUSDS), pa._cs(pa.SKY_SPBEAM), pa._cs(pa.SKY_SPBEAM_MOM)
        impl = "0x4e7991e5C547ce825BdEb665EE14a3274f9F61e0"
        answers = {**self.gov_answers(), (s, "wards", (self.PP,)): 1, (s, "wards", (beam,)): 1, (beam, "wards", (self.PP,)): 1,
                   (beam, "wards", (mom,)): 1, (beam, "cfgs"): [200, 3000, 400]}
        answers.update(override or {})
        c = Chain(answers=answers, codes={a: CODE for a in pa.SKY_CODE}, storage={(s, pa.IMPL_SLOT): impl}, logs=logs)
        c.block_number = pa.SKY_WARDS_PROOF_BLOCK + 2
        return c

    @mock.patch("time.sleep", lambda s: None)
    def test_susds_is_sky_governance_plus_a_bounded_rate(self):
        h = pa.Web3.keccak(CODE).hex().removeprefix("0x")
        with mock.patch.dict(pa.SKY_CODE, {a: h for a in pa.SKY_CODE}):
            def run(c):
                with mock.patch.object(pa, "call_raw", c.call_raw):
                    return [(p["status"], p["composite"]) for p in pa._sky_susds(c, 7 * 86400)]
            self.assertEqual(run(self.susds_chain()), [("scored", 81), ("bounded", None)])
            beam = pa._cs(pa.SKY_SPBEAM)
            for c in (self.susds_chain(logs=1), self.susds_chain(logs=ConnectionError("down")),
                      self.susds_chain(override={(beam, "wards", (pa._cs(pa.SKY_SPBEAM_MOM),)): 0}), self.susds_chain(override={(beam, "cfgs"): None})):
                with self.subTest(c=c):
                    self.assertEqual(run(c), [("UNREAD", None)])
        c = self.susds_chain()  # the pinned code hashes are the real ones: a fake code is not them
        with mock.patch.object(pa, "call_raw", c.call_raw):
            self.assertEqual(pa._sky_susds(c, 7 * 86400)[0]["status"], "UNREAD")

    def test_a_vault_v2_share_price_is_its_curator_and_owner_behind_its_timelock(self):
        vault, curator, owner = A(990), A(991), A(992)
        c = Chain(answers={(vault, "curator"): curator, (vault, "owner"): owner}, codes={curator: CODE, owner: CODE},
                  safes={curator: ([A(i) for i in range(7)], 2), owner: ([A(i) for i in range(10)], 5)})
        for d, gov, want in ((7 * 86400, 7 * 86400, ("governance-grade", None)), (3 * 86400, 7 * 86400, ("scored", pa.composite(50, 55, 60))),
                             (float("inf"), 7 * 86400, ("bounded", None)), (None, 7 * 86400, ("UNREAD", None))):
            with self.subTest(d=d, gov=gov), mock.patch.object(pa.morpho_v2, "timelock_and_gates", lambda w3, v, call=None, d=d: (d, [])), \
                    mock.patch.object(pa, "call_raw", c.call_raw), mock.patch.object(pa, "safe_owners_and_threshold", c.safe):
                p = pa.vault_v2_share_paths(c, vault, gov)[0]
                self.assertEqual((p["status"], p["composite"]), want)
        # setCurator is instant: a bare-key owner installs itself as curator and acts behind the same timelock
        c.codes.pop(owner.lower())
        with mock.patch.object(pa.morpho_v2, "timelock_and_gates", lambda w3, v, call=None: (3 * 86400, [])), \
                mock.patch.object(pa, "call_raw", c.call_raw), mock.patch.object(pa, "safe_owners_and_threshold", c.safe):
            p = pa.vault_v2_share_paths(c, vault, 7 * 86400)[0]
        self.assertEqual((p["status"], p["composite"]), ("scored", pa.composite(5, 0, 60)))
        c.answers.pop((vault.lower(), "owner"))  # an unread owner: unknown, not the curator's score
        with mock.patch.object(pa.morpho_v2, "timelock_and_gates", lambda w3, v, call=None: (3 * 86400, [])), \
                mock.patch.object(pa, "call_raw", c.call_raw), mock.patch.object(pa, "safe_owners_and_threshold", c.safe):
            self.assertEqual(pa.vault_v2_share_paths(c, vault, 7 * 86400)[0]["status"], "UNREAD")


class TestDataBeforeTheTrailer(unittest.TestCase):
    """solc can put constant data (a revert string, a description()) between the last INVALID and the metadata trailer."""
    META = b"\xa2\x64ipfs\x58\x22" + b"\x55\xf4" * 17 + b"\x64solc\x43\x00\x08\x13"

    def code(self, body):
        return body + self.META + len(self.META).to_bytes(2, "big")

    def test_data_after_the_last_invalid_is_not_scanned(self):
        data = b"Target contract does not contain"  # 'A'-like bytes: COINBASE, DELEGATECALL-looking text
        self.assertTrue(pa._no_opcode(self.code(b"\x60\x00\xfa\xfe" + data + b"\xf4\x41"), pa._WRITES + pa._OUTSIDE_STATE))

    def test_code_reachable_past_an_invalid_is_scanned(self):
        # PUSH1 5, JUMP, INVALID, JUMPDEST, SSTORE: the JUMPDEST past the INVALID is a pushed target
        self.assertFalse(pa._no_opcode(self.code(bytes.fromhex("600456fe5b55") + b"text"), (0x55,)))
        # a later INVALID that nothing jumps past is still a cut point: the SSTORE before it is scanned, the data after it is not
        self.assertFalse(pa._no_opcode(self.code(bytes.fromhex("600456fe5b55fe") + b"\x55text"), (0x55,)))
        self.assertTrue(pa._no_opcode(self.code(bytes.fromhex("600456fe5b00fe") + b"\x55text"), (0x55,)))

    def test_no_exact_trailer_means_the_whole_code(self):
        self.assertFalse(pa._no_opcode(b"\x60\x00\xfa\xfe\x55" + b"\x00\x05", (0x55,)))

    def test_a_jumpdest_hidden_in_push_data_is_not_a_target(self):  # the EVM's own sweep: 0x5b inside PUSH2 data is not valid
        self.assertTrue(pa._no_opcode(self.code(bytes.fromhex("600556fe615b55") + b"txt"), (0x55,)))


class TestEntryPointsAndRows(unittest.TestCase):
    def test_a_raised_read_gives_20_and_a_note_never_a_crash(self):
        c = Chain(raises=ConnectionError("rpc down"))
        for fn in (pa.for_aave, pa.for_aave_v2, pa.for_comet, pa.for_morpho_v1, pa.for_morpho_v2, pa.for_gmx_v2, pa.for_gmx_v1, pa.for_euler_factory, pa.for_euler_earn):
            with self.subTest(fn=fn.__name__), mock.patch.object(pa, "call_raw", c.call_raw):
                notes = []
                self.assertEqual(fn(c, A(1), None, notes), 20)
                self.assertTrue(any(pa.FAILED_MARK in n for n in notes))

    def test_unread_rows_give_20_with_the_mark_the_push_guard_reads(self):
        import push_guard
        c = Chain()
        for fn in (pa.for_aave, pa.for_aave_v2, pa.for_comet, pa.for_morpho_v1, pa.for_morpho_v2, pa.for_gmx_v2, pa.for_gmx_v1, pa.for_euler_factory, pa.for_euler_earn):
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
        vault, morpho, m1, m2, oracle = A(80), A(82), b"\x01" * 32, b"\x02" * 32, A(81)  # a singleton other than 0xBBBB (Monad's)
        c = Chain(answers={(vault, "MORPHO"): morpho, (vault, "withdrawQueueLength"): 2, (vault, "withdrawQueue", (0,)): m1, (vault, "withdrawQueue", (1,)): m2,
                           (morpho, "idToMarketParams", (m1,)): (A(1), A(2), oracle, A(3), 0),
                           (morpho, "idToMarketParams", (m2,)): (A(1), "0x" + "00" * 20, "0x" + "00" * 20, A(3), 0),
                           (morpho, "position", (m1, pa.Web3.to_checksum_address(vault))): (500, 0, 0),
                           (morpho, "position", (m2, pa.Web3.to_checksum_address(vault))): (1, 0, 0),
                           (morpho, "market", (m1,)): (2000, 1000, 0, 0, 0, 0), (morpho, "market", (m2,)): (1, 1, 0, 0, 0, 0)})
        with mock.patch.object(pa, "call_raw", c.call_raw):
            rows = pa.morpho_v1_rows(c, vault)
        self.assertEqual(rows, [(m1.hex(), pa.Web3.to_checksum_address(oracle), 1000)])  # 500 shares * 2000 / 1000; idle m2 skipped
        c.answers.pop((vault.lower(), "MORPHO"))  # unread singleton: no fallback to the Ethereum default, the rows are unread
        with mock.patch.object(pa, "call_raw", c.call_raw):
            self.assertIsNone(pa.morpho_v1_rows(c, vault))


ZERO = "0x" + "00" * 20
EIP1167_CODE = lambda impl: pa.EIP1167[0] + bytes.fromhex(impl[2:]) + pa.EIP1167[1]  # noqa: E731
IMPL, CLONE, ORACLE2, STOCK_ORACLE, TOKEN, BEACON, PROXY2 = A(300), A(301), A(302), A(303), A(304), A(305), A(306)


class TestMorphoV2Walk(TestWalkBranches):
    """EIP-1167 passthrough clones, the input-less MorphoChainlinkOracleV2, template input getters and beacon specs
    (2026-10-05). Each test fails when its branch is removed."""
    IMPL_CODE = b"\x60\x00\x60\x00\x55"  # the implementation's own code (it writes its state: that is why it is pinned)

    def setUp(self):
        p = mock.patch.object(pa, "PASSTHROUGH_IMPLS", {IMPL: (pa.Web3.keccak(self.IMPL_CODE).hex().removeprefix("0x"), ("primaryOracle", "backupOracle"))})
        p.start()
        self.addCleanup(p.stop)

    def clone_chain(self, **kw):
        answers = {(CLONE, "primaryOracle"): PROXY, (CLONE, "backupOracle"): OWNED_FEED, (OWNED_FEED, "owner"): SAFE22}
        answers.update(kw.pop("answers", {}))
        c = self.base(answers=answers, codes={CLONE: EIP1167_CODE(IMPL), IMPL: self.IMPL_CODE, SAFE22: CODE}, **kw)
        c.safes[SAFE22.lower()] = ([A(200), A(201)], 2)
        return c

    def test_clone_is_walked_to_both_oracles(self):
        s, notes = self.run_score(self.clone_chain(), [("x", CLONE, 100)])
        self.assertEqual(s, 29)  # backup's owner, a 2-of-2 Safe; primary's Chainlink owner 52
        self.assertTrue(any("composite 52" in n for n in notes))

    def test_clone_with_changed_implementation_or_unread_getter_is_unread(self):
        for kw in ({"codes": {IMPL: b"\x60\x01\x55"}}, {"storage": {(IMPL, pa.IMPL_SLOT): A(9)}}):
            with self.subTest(kw=kw):
                c = self.clone_chain(storage=kw.get("storage"))
                c.codes.update({k.lower(): v for k, v in kw.get("codes", {}).items()})
                s, notes = self.run_score(c, [("x", CLONE, 100)])
                self.assertEqual(s, 20)
                self.assertTrue(any("changed since its proof" in n for n in notes))
        c = self.clone_chain()
        c.answers.pop((CLONE.lower(), "backupOracle"))
        s, notes = self.run_score(c, [("x", CLONE, 100)])
        self.assertEqual(s, 20)
        self.assertTrue(any("not all readable" in n for n in notes))

    def test_a_clone_lookalike_is_not_walked(self):  # one byte longer, or another tail: not an EIP-1167 clone of the listed implementation
        for code in (pa.EIP1167[0] + bytes.fromhex(IMPL[2:]) + b"\x00" + pa.EIP1167[1], EIP1167_CODE(IMPL)[:-1] + b"\xf4"):
            with self.subTest(code=code.hex()[-6:]):
                c = self.clone_chain()
                c.codes[CLONE.lower()] = code
                self.assertEqual(self.run_score(c, [("x", CLONE, 100)])[0], 20)

    LAYOUT2 = (0, "SCALE_FACTOR", 1)  # a short layout for the fake: a feed site (0), the scale, a conversion sample

    def oracle2_chain(self, **inputs):
        ops = inputs.get("ops", (0, 10 ** 24, 1))  # one feed site, SCALE_FACTOR, one sample: STATICCALL makes it not a provable constant
        code = b"\x60\x00\xfa" + b"".join(b"\x7f" + v.to_bytes(32, "big") for v in ops)
        answers = {(ORACLE2, g): inputs.get(g, ZERO) for g in pa.MORPHO_ORACLE_V2_INPUTS}
        answers.update({(ORACLE2, "price"): inputs.get("price", 10 ** 24), (ORACLE2, "SCALE_FACTOR"): inputs.get("SCALE_FACTOR", 10 ** 24)})
        c = self.base(answers=answers, codes={ORACLE2: code})
        return c, pa.masked_template(b"\x60\x00\xfa" + (b"\x7f" + b"\x22" * 32) * 3)  # the template ignores the PUSH32 operands

    def test_inputless_morpho_oracle_is_a_template_pinned_constant(self):
        c, template = self.oracle2_chain()
        with mock.patch.object(pa, "MORPHO_ORACLE_V2_TEMPLATE", template), mock.patch.object(pa, "MORPHO_ORACLE_V2_INPUTLESS_LAYOUT", self.LAYOUT2):
            s, notes = self.run_score(c, [("x", ORACLE2, 100)])
            self.assertEqual(s, 100)
            self.assertTrue(any("input-less MorphoChainlinkOracleV2, template-pinned" in n for n in notes))
            self.assertFalse(any("provable constant" in n for n in notes))
            dirty = (1 << 255) | int("ab" * 20, 16)
            for bad in ({"price": 10 ** 24 + 1}, {"BASE_VAULT": None}, {"price": None, "SCALE_FACTOR": None},  # moved, unread, both unread
                        {"ops": (int("ab" * 20, 16), 10 ** 24, 1)}, {"ops": (dirty, 10 ** 24, 1)},  # a feed at the feed site, dirty bits too
                        {"ops": (10 ** 24, 0, 1)}):  # sites swapped (a missing site changes the template itself)
                with self.subTest(bad=bad):
                    self.assertEqual(self.run_score(self.oracle2_chain(**bad)[0], [("x", ORACLE2, 100)])[0], 20)
        self.assertEqual(self.run_score(c, [("x", ORACLE2, 100)])[0], 20)  # another template: UNREAD

    def stock_chain(self):
        code = b"\x60\x00\xfa\x60\x01"
        c = self.base(answers={(STOCK_ORACLE, "baseFeed"): PROXY, (STOCK_ORACLE, "token"): TOKEN},
                      codes={STOCK_ORACLE: code, TOKEN: CODE, BEACON: CODE}, storage={(TOKEN, pa.BEACON_SLOT): BEACON})
        return c, pa.masked_template(code)

    def test_template_input_getter_follows_token_to_its_beacon_spec(self):
        c, template = self.stock_chain()
        spec = {BEACON: lambda w3, gov: [pa.controller_path(w3, EOA, gov, "beacon admin")]}
        with mock.patch.object(pa, "TEMPLATE_INPUT_GETTERS", {template: (("token",), ())}):
            self.assertEqual(self.run_score(c, [("x", STOCK_ORACLE, 100)], specs=spec)[0], 2)  # the token's beacon admin, a bare key
            s, notes = self.run_score(c, [("x", STOCK_ORACLE, 100)])  # no spec: the beacon has no owner(), UNREAD
            self.assertEqual(s, 20)
        self.assertEqual(self.run_score(c, [("x", STOCK_ORACLE, 100)], specs=spec)[0], 52)  # another build: token() not followed
        self.assertNotIn("token", pa.FEED_GETTERS + pa.RATE_GETTERS)

    def test_template_operands_must_match_the_pinned_layout_site_by_site(self):
        feed, loan = "0x" + "ab" * 20, "0x" + "cd" * 20  # address-sized, like real immutables
        F, L = int(feed, 16), int(loan, 16)

        def chain(ops):
            code = b"\x60\x00\xfa" + b"".join(b"\x7f" + v.to_bytes(32, "big") for v in ops)
            c = self.base(answers={(STOCK_ORACLE, "baseFeed"): feed, (STOCK_ORACLE, "token"): TOKEN, (STOCK_ORACLE, "loanToken"): loan,
                                   (STOCK_ORACLE, "SCALE_FACTOR"): 10 ** 24, (feed, "aggregator"): AGG, (feed, "owner"): SAFE49},
                          codes={STOCK_ORACLE: code, TOKEN: CODE, BEACON: CODE, feed: CODE}, storage={(TOKEN, pa.BEACON_SLOT): BEACON})
            return c, pa.masked_template(code)
        spec = {BEACON: lambda w3, gov: [pa.controller_path(w3, EOA, gov, "beacon admin")]}
        layout = ("loanToken", 8, "baseFeed", "SCALE_FACTOR")
        c, template = chain((L, 8, F, 10 ** 24))
        with mock.patch.object(pa, "TEMPLATE_INPUT_GETTERS", {template: (("token",), layout)}):
            self.assertEqual(self.run_score(c, [("x", STOCK_ORACLE, 100)], specs=spec)[0], 2)  # the layout holds: token() followed
            for ops in ((F, 8, L, 10 ** 24),  # the loan token moved to the feed site (never walked there)
                        (L, 8, (1 << 255) | F, 10 ** 24),  # dirty high bit on the feed
                        (L, 9, F, 10 ** 24)):  # a constant changed (a site added or removed changes the template itself)
                with self.subTest(ops=[hex(o)[:8] for o in ops]):
                    s, notes = self.run_score(chain(ops)[0], [("x", STOCK_ORACLE, 100)], specs=spec)
                    self.assertEqual(s, 20)
                    self.assertTrue(any("pinned layout" in n for n in notes))
        with mock.patch.object(pa, "TEMPLATE_INPUT_GETTERS", {template: (("token",), layout + (8,))}):  # a layout longer than the code
            self.assertEqual(self.run_score(c, [("x", STOCK_ORACLE, 100)], specs=spec)[0], 20)
        c.answers.pop((STOCK_ORACLE.lower(), "token"))
        with mock.patch.object(pa, "TEMPLATE_INPUT_GETTERS", {template: (("token",), layout)}):  # the input getter unread
            s, notes = self.run_score(c, [("x", STOCK_ORACLE, 100)], specs=spec)
            self.assertEqual(s, 20)
            self.assertTrue(any("unread or zero" in n for n in notes))

    def test_each_new_getter_is_followed(self):
        wrapper = A(310)
        spec = {PROVIDER: lambda w3, gov: [pa.path("lst rate", "scored", 7, note="spec reached")]}
        for getter, upstream, expected in (("stETHtoETHPriceFeed", OWNED_FEED, 2), ("underlyingFeed", OWNED_FEED, 2), ("baseFeed", OWNED_FEED, 2),
                                           ("quoteFeed", OWNED_FEED, 2), ("wstETH", PROVIDER, 7), ("WEETH", PROVIDER, 7),
                                           ("chainlinkFeed", OWNED_FEED, 2), ("iassetUsdOracle", OWNED_FEED, 2),  # Radiant adapters
                                           ("exchangeRatioOracle", OWNED_FEED, 2), ("verifier", OWNED_FEED, 2),  # GMX data-stream provider
                                           ("feed", OWNED_FEED, 2), ("oracleBaseCross", OWNED_FEED, 2), ("oracleCrossQuote", OWNED_FEED, 2)):  # Euler adapters
            with self.subTest(getter=getter):  # an unfollowed getter leaves the wrapper with no input: UNREAD, 20
                c = self.base(answers={(wrapper, getter): upstream, (OWNED_FEED, "owner"): EOA}, codes={wrapper: CODE, PROVIDER: CODE})
                self.assertEqual(self.run_score(c, [("x", wrapper, 100)], specs=spec)[0], expected)

class TestSolcOnlyTrailerAndTemplate(unittest.TestCase):
    def test_solc_version_only_trailer_is_metadata(self):  # bytecodeHash none: a1 64 'solc' 43 <3 bytes>, length 0x000a
        meta = b"\xa1\x64solc\x43\x00\x08\x15"
        self.assertTrue(pa._is_metadata(meta))
        self.assertEqual(pa._strip_metadata(b"\x60\x00\xfe" + meta + b"\x00\x0a"), b"\x60\x00\xfe")
        self.assertFalse(pa._is_metadata(meta + b"\x00"))

    def test_masked_template_zeroes_push32_and_the_trailer(self):
        a = b"\x7f" + b"\x01" * 32 + b"\x60\x05\xfe"
        b = b"\x7f" + b"\x02" * 32 + b"\x60\x05\xfe"
        meta = b"\xa1\x64solc\x43\x00\x08\x15\x00\x0a"
        self.assertEqual(pa.masked_template(a), pa.masked_template(b + meta))
        self.assertNotEqual(pa.masked_template(a), pa.masked_template(b"\x7f" + b"\x01" * 32 + b"\x60\x06\xfe"))  # PUSH1 kept


class TestRobinhoodSpecs(unittest.TestCase):
    HOLDER_MIDAS, HOLDER_STOCK = "0x83b573AA8C4b567c0466c9d5e32D6513676d795b", "0xd6f8378f8e440c65f8382f5f2728c78dfd55b66d"
    FEED, BEACON_RH, AC, IMPL_RH = "0x49D9Dd1Fa6EA3709aB8A5d5f16a1cf207eb91dd0", "0xe10b6f6B275de231345c20D14Ab812db62151b00", "0xe5F087203F9e7A6104c821ec25b1F0a4505D3cb5", A(400)

    def run_spec(self, spec, chain, **consts):
        with mock.patch.object(pa, "call_raw", chain.call_raw), mock.patch.multiple(pa, **consts):
            return spec(chain, 86400)

    def midas(self, has=True, holder_code=b""):
        c = Chain(answers={(self.FEED, "accessControl"): self.AC, (self.FEED, "feedAdminRole"): b"\x5a" * 32, (self.AC, "hasRole"): has},
                  codes={self.IMPL_RH: CODE, self.HOLDER_MIDAS: holder_code}, storage={(self.FEED, pa.IMPL_SLOT): self.IMPL_RH})
        return self.run_spec(pa._midas_mglo_feed, c, MIDAS_MGLO_IMPL_HASH=pa.Web3.keccak(CODE).hex().removeprefix("0x"))

    def beacon(self, has=True, holder_code=b""):
        c = Chain(answers={(self.BEACON_RH, "hasRole"): has}, codes={self.BEACON_RH: CODE, self.HOLDER_STOCK: holder_code})
        return self.run_spec(pa._robinhood_stock_beacon, c, STOCK_BEACON_CODE_HASH=pa.Web3.keccak(CODE).hex().removeprefix("0x"))

    def test_a_bare_key_holder_scores_the_floor_and_anything_else_is_unread(self):
        for spec in (self.midas, self.beacon):
            with self.subTest(spec=spec.__name__):
                self.assertEqual([(p["status"], p["composite"]) for p in spec()], [("scored", 2)])
                for kw in ({"has": False}, {"has": None}, {"holder_code": CODE}):  # not a holder, unread, a contract
                    self.assertEqual([p["status"] for p in spec(**kw)], ["UNREAD"], kw)

    def test_pinned_code_hashes_hold(self):
        c = Chain(answers={(self.BEACON_RH, "hasRole"): True}, codes={self.BEACON_RH: CODE})
        self.assertEqual(self.run_spec(pa._robinhood_stock_beacon, c, STOCK_BEACON_CODE_HASH="00" * 32)[0]["status"], "UNREAD")

    def test_any_other_shape_is_unread(self):
        ok_hash = pa.Web3.keccak(CODE).hex().removeprefix("0x")
        c = Chain(answers={(self.FEED, "accessControl"): self.AC, (self.FEED, "feedAdminRole"): b"\x5a" * 32, (self.AC, "hasRole"): True},
                  codes={self.IMPL_RH: CODE}, storage={(self.FEED, pa.IMPL_SLOT): self.IMPL_RH})
        self.assertEqual(self.run_spec(pa._midas_mglo_feed, c, MIDAS_MGLO_IMPL_HASH="00" * 32)[0]["status"], "UNREAD")  # implementation changed
        c.answers[(self.FEED.lower(), "accessControl")] = A(401)
        self.assertEqual(self.run_spec(pa._midas_mglo_feed, c, MIDAS_MGLO_IMPL_HASH=ok_hash)[0]["status"], "UNREAD")  # another access control
        b = Chain(answers={(self.BEACON_RH, "hasRole"): True}, codes={self.BEACON_RH: CODE}, storage={(self.BEACON_RH, pa.IMPL_SLOT): A(402)})
        self.assertEqual(self.run_spec(pa._robinhood_stock_beacon, b, STOCK_BEACON_CODE_HASH=ok_hash)[0]["status"], "UNREAD")  # now a proxy


class TestMorphoV2Rows(unittest.TestCase):
    VAULT, MKT_AD, OLD_AD, V1_AD, BOX, EMPTY, V1, BLUE, ASSET, OWNER, SAFE, CURATOR = (A(500 + i) for i in range(12))
    M1, M2, M3 = b"\x01" * 32, b"\x02" * 32, b"\x03" * 32
    O1, O2, O3 = A(520), A(521), A(522)
    PARAMS3 = (A(530), A(531), A(522), A(532), 860000000000000000)

    def chain(self):
        cs = pa.Web3.to_checksum_address
        m3 = pa.Web3.keccak(pa.abi_encode(["address", "address", "address", "address", "uint256"], list(self.PARAMS3)))
        answers = {(self.VAULT, "adaptersLength"): 5, (self.VAULT, "totalAssets"): 1000, (self.VAULT, "asset"): self.ASSET,
                   (self.ASSET, "balanceOf", (cs(self.VAULT),)): 250}
        for i, a in enumerate((self.MKT_AD, self.OLD_AD, self.V1_AD, self.BOX, self.EMPTY)):
            answers[(self.VAULT, "adapters", (i,))] = a
        answers.update({(self.MKT_AD, "morpho"): self.BLUE, (self.MKT_AD, "marketIdsLength"): 1, (self.MKT_AD, "marketIds", (0,)): self.M1,
                        (self.OLD_AD, "morpho"): self.BLUE, (self.OLD_AD, "marketParamsListLength"): 1,  # first adapter version
                        (self.OLD_AD, "marketParamsList", (0,)): self.PARAMS3,
                        (self.V1_AD, "morphoVaultV1"): self.V1, (self.V1, "MORPHO"): self.BLUE, (self.V1, "withdrawQueueLength"): 1,
                        (self.V1, "withdrawQueue", (0,)): self.M2, (self.V1, "balanceOf", (self.V1_AD,)): 1, (self.V1, "totalSupply"): 4,
                        (self.BOX, "realAssets"): 70, (self.EMPTY, "realAssets"): 0, (self.MKT_AD, "realAssets"): 100, (self.OLD_AD, "realAssets"): 30})
        for mid, oracle, holder, shares in ((self.M1, self.O1, self.MKT_AD, 100), (self.M2, self.O2, self.V1, 400), (m3, self.O3, self.OLD_AD, 30)):
            answers[(self.BLUE, "idToMarketParams", (mid,))] = (A(1), A(2), oracle, A(3), 0)
            answers[(self.BLUE, "position", (mid, cs(holder)))] = (shares, 0, 0)
            answers[(self.BLUE, "market", (mid,))] = (1, 1, 0, 0, 0, 0)
        return Chain(answers=answers), m3

    def rows(self, c):
        notes = []
        with mock.patch.object(pa, "call_raw", c.call_raw):
            return pa.morpho_v2_rows(c, self.VAULT, notes), notes

    def test_every_adapter_kind(self):
        c, m3 = self.chain()
        rows, notes = self.rows(c)
        cs = pa.Web3.to_checksum_address
        self.assertCountEqual([(r[1], r[2]) for r in rows], [
            (cs(self.O1), 100),           # MorphoMarketV1AdapterV2: its own position
            (cs(self.O3), 30),            # marketParamsList variant: id = keccak(abi.encode(params))
            (cs(self.O2), 100),           # V1 vault adapter: 400 x its 1/4 share of the V1 vault
            (None, 70)])                  # unknown adapter holding assets: a row with no source (UNREAD)
        self.assertTrue(any(self.EMPTY in n and "realAssets() = 0" in n for n in notes))  # an empty unknown adapter: a note
        self.assertTrue(any("idle assets 250 of totalAssets 1000 (25.00%)" in n for n in notes))

    def test_unread_adapter_parts_are_unread_rows(self):
        c, _ = self.chain()
        for key in ((self.MKT_AD, "marketIds", (0,)), (self.V1, "MORPHO"), (self.BOX, "realAssets"), (self.VAULT, "adapters", (0,)),
                    (self.OLD_AD, "marketParamsList", (0,)), (self.MKT_AD, "realAssets")):
            with self.subTest(key=key[1]):
                c, _ = self.chain()
                c.answers.pop(tuple([key[0].lower(), *key[1:]]))
                rows, _ = self.rows(c)
                no_source = [r[2] for r in rows if r[1] is None]  # beyond the unknown adapter's (None, 70): one more row, or its value unread
                self.assertTrue(len(no_source) >= 2 or None in no_source, no_source)
                if key[1] in ("marketIds", "marketParamsList"):  # one unread entry: the whole adapter, not a silently shorter list
                    self.assertTrue(any("markets unread" in r[0] for r in rows), rows)
        c.answers.pop((self.VAULT.lower(), "adaptersLength"))
        self.assertIsNone(self.rows(c)[0])

    def test_adapter_funds_its_market_rows_do_not_show_are_a_row(self):
        c, _ = self.chain()
        c.answers[(self.MKT_AD.lower(), "realAssets")] = 150  # 50 more than its one market row
        rows, _ = self.rows(c)
        self.assertIn((None, 50), [(r[1], r[2]) for r in rows])
        c.answers[(self.MKT_AD.lower(), "realAssets")] = 100 + 1  # within 1%: no row
        rows, _ = self.rows(c)
        self.assertNotIn(None, [r[1] for r in rows if r[2] == 1])

    def test_a_live_cap_on_an_unallocated_adapter_is_noted(self):
        c, _ = self.chain()
        cs = pa.Web3.to_checksum_address
        cid = pa.Web3.keccak(pa.abi_encode(["string", "address"], ["this", cs(self.EMPTY)]))
        c.answers[(self.VAULT.lower(), "absoluteCap", (cid,))] = 10 ** 18
        rows, notes = self.rows(c)
        self.assertFalse(any("allocators can allocate" in n for n in notes))  # no relative cap read: no note
        c.answers[(self.VAULT.lower(), "relativeCap", (cid,))] = 10 ** 18
        rows, notes = self.rows(c)
        self.assertTrue(any(cs(self.EMPTY) in n and "allocators can allocate without a timelock" in n for n in notes))
        cid = pa.Web3.keccak(pa.abi_encode(["string", "address"], ["this", cs(self.MKT_AD)]))
        c.answers[(self.VAULT.lower(), "absoluteCap", (cid,))] = c.answers[(self.VAULT.lower(), "relativeCap", (cid,))] = 10 ** 18
        rows, notes = self.rows(c)
        self.assertFalse(any(cs(self.MKT_AD) in n and "allocators can allocate" in n for n in notes))  # allocated today: no note
        c.answers.pop((self.MKT_AD.lower(), "marketIds", (0,)))
        c.answers.pop((self.MKT_AD.lower(), "realAssets"))  # its allocation unread: not 'nothing allocated'
        rows, notes = self.rows(c)
        self.assertFalse(any(cs(self.MKT_AD) in n and "allocators can allocate" in n for n in notes))

    def test_idle_market_supply_is_not_a_reconcile_gap(self):
        c, _ = self.chain()
        idle_id = b"\x04" * 32
        c.answers[(self.MKT_AD.lower(), "marketIdsLength")] = 2
        c.answers[(self.MKT_AD.lower(), "marketIds", (1,))] = idle_id
        c.answers[(self.BLUE.lower(), "idToMarketParams", (idle_id,))] = (A(1), "0x" + "00" * 20, "0x" + "00" * 20, A(3), 0)
        c.answers[(self.BLUE.lower(), "position", (idle_id, pa.Web3.to_checksum_address(self.MKT_AD)))] = (40, 0, 0)
        c.answers[(self.BLUE.lower(), "market", (idle_id,))] = (1, 1, 0, 0, 0, 0)
        c.answers[(self.MKT_AD.lower(), "realAssets")] = 140  # 100 priced + 40 idle
        rows, _ = self.rows(c)
        self.assertNotIn(40, [r[2] for r in rows if r[1] is None])

    def test_governance_delay_and_own_addresses(self):
        cs = pa.Web3.to_checksum_address
        c = Chain(answers={(self.VAULT, "abdicated"): False, (self.VAULT, "timelock"): 604800, (self.VAULT, "owner"): self.OWNER,
                           (self.OWNER, "owner"): self.SAFE, (self.VAULT, "curator"): self.CURATOR}, codes={self.OWNER: CODE})
        with mock.patch.object(pa, "call_raw", c.call_raw):
            # no own set: the owner and curator act at once outside the vault, so a wrapper they control is scored
            self.assertEqual(pa.morpho_v2_governance(c, self.VAULT), (604800, set()))
            c.answers[(self.VAULT.lower(), "abdicated")] = True  # everything abdicated: no bar
            self.assertIsNone(pa.morpho_v2_governance(c, self.VAULT)[0])
            c.answers[(self.VAULT.lower(), "abdicated")] = None  # unread: no bar
            self.assertIsNone(pa.morpho_v2_governance(c, self.VAULT)[0])

    def test_for_morpho_v2_scores_its_rows_with_its_delay(self):
        c, _ = self.chain()
        seen = {}

        def fake_score(w3, rows, delay, specs, own, notes):
            seen.update(rows=rows, delay=delay)
            return 52
        with mock.patch.object(pa, "call_raw", c.call_raw), mock.patch.object(pa, "score", fake_score), \
                mock.patch.object(pa, "morpho_v2_governance", lambda w3, v: (604800, set())):
            self.assertEqual(pa.for_morpho_v2(c, self.VAULT, None, []), 52)
        self.assertEqual((len(seen["rows"]), seen["delay"]), (4, 604800))


class TestAaveV2(unittest.TestCase):
    """Radiant (Aave V2 fork, 2026-10-05): V2 ReserveData rows, the fallback oracle, the oracle owner's delay."""
    PROV, POOL, ORACLE, A1, A2, AT1, TL, OWNER = (A(600 + i) for i in range(8))
    cs = staticmethod(pa.Web3.to_checksum_address)

    def chain(self, extra=None):
        data = (0,) * 7 + (self.AT1, A(9), A(9), A(9), 0)  # aToken at index 7 (V3 has it at 8)
        answers = {(self.PROV, "getLendingPool"): self.POOL, (self.PROV, "getPriceOracle"): self.ORACLE, (self.POOL, "getReservesList"): [self.A1, self.A2],
                   (self.ORACLE, "getSourceOfAsset", (self.A1,)): PROXY, (self.ORACLE, "getAssetPrice", (self.A1,)): 2 * 10 ** 8,
                   (self.POOL, "getReserveData", (self.A1,)): data, (self.A1, "decimals"): 6, (self.AT1, "totalSupply"): 5 * 10 ** 6,
                   (self.ORACLE, "getFallbackOracle"): ZERO}
        answers.update(extra or {})
        return Chain(answers=answers, codes={self.TL: CODE, self.OWNER: CODE})

    def rows(self, c):
        with mock.patch.object(pa, "call_raw", c.call_raw):
            return pa.aave_v2_rows(c, self.PROV)

    def test_rows_read_the_v2_atoken_and_leave_unread_values_none(self):
        self.assertEqual(self.rows(self.chain()), [(self.A1, self.cs(PROXY), 10 ** 9), (self.A2, None, None)])  # 5 units at 2e8
        self.assertIsNone(self.rows(Chain()))

    def test_a_fallback_oracle_set_or_unread_is_a_material_row(self):
        rows = self.rows(self.chain({(self.ORACLE, "getFallbackOracle"): A(77)}))
        self.assertEqual(rows[-1][1:], (self.cs(A(77)), None))  # walked, value None: material
        c = self.chain()
        c.answers.pop((self.ORACLE.lower(), "getFallbackOracle"))
        self.assertEqual(self.rows(c)[-1], ("fallback oracle (unread)", None, None))

    def test_governance_delay_is_the_oracle_owner_timelock_else_zero(self):
        base = {(self.ORACLE, "owner"): self.TL, (self.TL, "getMinDelay"): 259200, (self.PROV, "owner"): self.TL, (self.PROV, "getPoolAdmin"): A(71)}
        c = self.chain(base)
        with mock.patch.object(pa, "call_raw", c.call_raw):
            delay, own, stray = pa.aave_v2_governance(c, self.PROV)
        self.assertEqual((delay, own, stray), (259200, {self.cs(x) for x in (self.PROV, self.ORACLE, self.TL, A(71))}, None))
        for owner, expected in ((self.OWNER, 0), (EOA, 0)):  # a Safe or a key re-points a source at once: no governance-grade bar
            c = self.chain({**base, (self.ORACLE, "owner"): owner, (self.PROV, "getPoolAdmin"): owner})
            with mock.patch.object(pa, "call_raw", c.call_raw):
                self.assertEqual(pa.aave_v2_governance(c, self.PROV)[0], expected)
        with mock.patch.object(pa, "call_raw", self.chain().call_raw):
            self.assertIsNone(pa.aave_v2_governance(self.chain(), self.PROV)[0])  # owner unread

    def test_an_oracle_owner_the_composite_does_not_score_is_an_unread_row(self):
        c = self.chain({(self.ORACLE, "owner"): self.OWNER, (self.PROV, "owner"): A(70), (self.PROV, "getPoolAdmin"): A(71)})
        with mock.patch.object(pa, "call_raw", c.call_raw):
            delay, own, stray = pa.aave_v2_governance(c, self.PROV)
        self.assertEqual(stray, self.cs(self.OWNER))
        self.assertNotIn(self.cs(self.OWNER), own)
        seen = {}
        with mock.patch.object(pa, "call_raw", c.call_raw), mock.patch.object(pa, "score", lambda w3, rows, *a, **k: seen.setdefault("rows", rows) and 52):
            pa.for_aave_v2(c, self.PROV, None, [])
        self.assertIn((None, None), [r[1:] for r in seen["rows"] if "a root the composite does not score" in r[0]])

    def test_an_unread_oracle_owner_is_a_row_and_a_renounced_one_is_not(self):
        for owner, expect_row in ((None, True), (ZERO, False)):
            with self.subTest(owner=owner):
                c = self.chain({(self.ORACLE, "owner"): owner})
                seen = {}
                with mock.patch.object(pa, "call_raw", c.call_raw), mock.patch.object(pa, "score", lambda w3, rows, *a, **k: seen.setdefault("rows", rows) and 52):
                    pa.for_aave_v2(c, self.PROV, None, [])
                self.assertEqual(any("owner() unread" in r[0] for r in seen["rows"]), expect_row)

    def test_an_unread_reserve_list_is_unread(self):
        c = self.chain()
        c.answers.pop((self.POOL.lower(), "getReservesList"))
        self.assertIsNone(self.rows(c))


V1_VPF, V1_PFT = pa._cs(pa.GMX_V1_VAULT_PRICE_FEED), pa._cs(pa.GMX_V1_PRICE_FEED_TIMELOCK)
CODE_HASH = pa.Web3.keccak(CODE).hex().removeprefix("0x")


class TestArbitrumSpecs(unittest.TestCase):
    """Chainlink Data Streams VerifierProxy and GMX V1 VaultPriceFeed specs (2026-10-05): every fact re-read, any other
    answer UNREAD."""
    def run_spec(self, spec, c, gov=86400, **consts):
        with mock.patch.object(pa, "call_raw", c.call_raw), mock.patch.object(pa, "safe_owners_and_threshold", c.safe), mock.patch.multiple(pa, **consts):
            return [(p["status"], p["composite"]) for p in spec(c, gov)]

    def streams(self, logs=0, v_owner=SAFE49, storage=None, code_hash=CODE_HASH):
        proxy, (v1, v2) = pa.CL_VERIFIER_PROXY_ARB, pa.CL_VERIFIERS_ARB
        c = Chain(answers={(proxy, "owner"): SAFE49, (v1, "owner"): SAFE49, (v2, "owner"): v_owner}, codes={proxy: CODE, SAFE49: CODE},
                  safes={SAFE49: ([A(100 + i) for i in range(9)], 4)}, storage=storage, logs=logs)
        c.block_number = pa.CL_VERIFIER_PROOF_BLOCK + 5
        return self.run_spec(pa._chainlink_data_streams_arb, c, CL_VERIFIER_PROXY_ARB_CODE_HASH=code_hash)

    @mock.patch("time.sleep", lambda s: None)
    def test_data_streams_proxy(self):
        self.assertEqual(self.streams(), [("scored", 52)])  # both Verifiers owned by the proxy's Safe: one path
        self.assertEqual(self.streams(v_owner=EOA), [("scored", 52), ("scored", 2)])  # a Verifier owner that differs is scored
        self.assertIn("UNREAD", [st for st, _ in self.streams(v_owner=None)])  # a Verifier owner unread: never dropped
        for kw in ({"logs": 1}, {"logs": ConnectionError("no getLogs")}, {"code_hash": "00" * 32},
                   {"storage": {(pa.CL_VERIFIER_PROXY_ARB, pa.IMPL_SLOT): A(9)}}):
            with self.subTest(kw=str(kw)[:40]):
                self.assertEqual(self.streams(**kw), [("UNREAD", None)])

    def vpf(self, gov=86400, **over):
        answers = {(V1_VPF, "gov"): V1_PFT, (V1_PFT, "admin"): EOA, (V1_PFT, "tokenManager"): SAFE49, (V1_PFT, "buffer"): 86400,
                   (V1_VPF, "isSecondaryPriceEnabled"): False, (V1_VPF, "isAmmEnabled"): False}
        answers.update(over.pop("answers", {}))
        c = Chain(answers=answers, codes={V1_VPF: CODE, V1_PFT: CODE, SAFE49: CODE}, safes={SAFE49: ([A(100 + i) for i in range(9)], 4)}, **over)
        return self.run_spec(pa._gmx_v1_vault_price_feed, c, gov, GMX_V1_VAULT_PRICE_FEED_CODE_HASH=CODE_HASH, GMX_V1_PRICE_FEED_TIMELOCK_CODE_HASH=CODE_HASH)

    def test_gmx_v1_vault_price_feed(self):
        self.assertEqual(self.vpf(), [("scored", 2), ("scored", 52), ("governance-grade", None)])  # bare-EOA admin, Safe tokenManager
        for gov, answers in ((86400, {(V1_PFT, "buffer"): 3600}), (86400, {(V1_PFT, "buffer"): None}), (0, {}), (None, {})):
            with self.subTest(gov=gov, answers=answers):  # buffer below the Vault's delay, unread, or no bar: the signalled actions are UNREAD
                self.assertEqual(self.vpf(gov, answers=answers)[2], ("UNREAD", None))
        for flag in ("isSecondaryPriceEnabled", "isAmmEnabled"):
            for v in (True, None):
                with self.subTest(flag=flag, v=v):
                    self.assertEqual(self.vpf(answers={(V1_VPF, flag): v})[3:], [("UNREAD", None)])
        for over in ({"answers": {(V1_VPF, "gov"): A(9)}}, {"storage": {(V1_PFT, pa.ADMIN_SLOT): A(9)}}):
            with self.subTest(over=str(over)[:50]):
                self.assertEqual(self.vpf(**over), [("UNREAD", None)])
        c = Chain(answers={(V1_VPF, "gov"): V1_PFT}, codes={V1_VPF: CODE, V1_PFT: b"\x60\x01"})  # the timelock's code changed
        self.assertEqual(self.run_spec(pa._gmx_v1_vault_price_feed, c, GMX_V1_VAULT_PRICE_FEED_CODE_HASH=CODE_HASH,
                                       GMX_V1_PRICE_FEED_TIMELOCK_CODE_HASH=CODE_HASH), [("UNREAD", None)])

    def test_the_specs_are_keyed_on_their_contracts(self):
        self.assertIs(pa.ARBITRUM_SPECS[pa.CL_VERIFIER_PROXY_ARB], pa._chainlink_data_streams_arb)
        self.assertIs(pa.ARBITRUM_SPECS[pa.GMX_V1_VAULT_PRICE_FEED], pa._gmx_v1_vault_price_feed)


class TestOverlappingRows(unittest.TestCase):
    def test_total_override_weighs_rows_against_the_priced_supply(self):
        c = TestWalkBranches.base(self, answers={(OWNED_FEED, "owner"): EOA})
        rows = [("pool", PROXY, 1000), ("same pool, other token", PROXY, 1000), ("small", OWNED_FEED, 15)]
        with mock.patch.object(pa, "call_raw", c.call_raw), mock.patch.object(pa, "safe_owners_and_threshold", c.safe):
            self.assertEqual(pa.score(c, rows, 86400), 52)  # 15 / 2015 = 0.74%: immaterial
            self.assertEqual(pa.score(c, rows, 86400, total=1000), 2)  # 15 / 1000 = 1.5% of the priced supply: material


class TestGmxRows(unittest.TestCase):
    DS, READER, PF = pa.GMX_DATASTORE, pa.GMX_READER, pa.GMX_CHAINLINK_PRICE_FEED_PROVIDER
    MT1, MT2, ETH, USDC, ANIME, FE, FU, PROV, ORC, H1 = (A(700 + i) for i in range(10))
    cs = staticmethod(pa.Web3.to_checksum_address)

    def chain(self, anime_provider=None, enabled=True, atomic=True, disabled=False):
        gk, gkey = pa._gk, pa._gkey
        u = lambda *tv: (self.DS, "getUint", (gkey(*tv),))  # noqa: E731
        ad = lambda *tv: (self.DS, "getAddress", (gkey(*tv),))  # noqa: E731
        answers = {(self.DS, "getAddressCount", (gk("MARKET_LIST"),)): 2, (self.DS, "getAddressValuesAt", (gk("MARKET_LIST"), 0, 2)): [self.MT1, self.MT2],
                   (self.READER, "getMarket", (self.DS, self.MT1)): (self.MT1, self.ETH, self.ETH, self.USDC),
                   (self.READER, "getMarket", (self.DS, self.MT2)): (self.MT2, ZERO, self.ANIME, self.USDC),  # swap-only market
                   (self.FE, "latestRoundData"): (0, 2000 * 10 ** 8, 0, 0, 0), (self.FU, "latestRoundData"): (0, 10 ** 8, 0, 0, 0)}
        for mt, t, amt in ((self.MT1, self.ETH, 10 ** 18), (self.MT1, self.USDC, 1000 * 10 ** 6), (self.MT2, self.ANIME, 5), (self.MT2, self.USDC, 500 * 10 ** 6)):
            answers[u(("bytes32", gk("POOL_AMOUNT")), ("address", mt), ("address", t))] = amt
        for c in (self.ETH, self.USDC):
            for is_long in (True, False):  # 1 USD of open interest per collateral and side: 4 USD on ETH
                answers[u(("bytes32", gk("OPEN_INTEREST")), ("address", self.MT1), ("address", c), ("bool", is_long))] = 10 ** 30
        for t, feed, mult, prov in ((self.ETH, self.FE, 10 ** 34, self.PROV), (self.USDC, self.FU, 10 ** 46, self.PROV),
                                    (self.ANIME, ZERO, 0, anime_provider or self.PROV)):
            answers[ad(("bytes32", gk("PRICE_FEED")), ("address", t))] = feed
            answers[u(("bytes32", gk("PRICE_FEED_MULTIPLIER")), ("address", t))] = mult
            answers[ad(("bytes32", gk("ORACLE_PROVIDER_FOR_TOKEN")), ("address", self.ORC), ("address", t))] = prov
        answers[(self.DS, "getBool", (gkey(("bytes32", gk("IS_ORACLE_PROVIDER_ENABLED")), ("address", self.PF)),))] = enabled
        answers[(self.DS, "getBool", (gkey(("bytes32", gk("IS_ATOMIC_ORACLE_PROVIDER")), ("address", self.PF)),))] = atomic
        answers[(pa.GMX_ROLESTORE, "getRoleMembers", (gk("CONTROLLER"), 0, 500))] = [self.H1, A(9)]
        answers.update({(self.H1, "withdrawalVault"): A(8), (self.H1, "oracle"): self.ORC, (A(9), "oracle"): self.ORC})  # A(9): not a WithdrawalHandler
        answers[(self.DS, "getBool", (gkey(("bytes32", gk("EXECUTE_ATOMIC_WITHDRAWAL_FEATURE_DISABLED")), ("address", self.H1)),))] = disabled
        return Chain(answers=answers)

    def rows(self, c):
        def batch(w3, calls, chunk=300, allow_failure=False):  # Multicall3 resolved call by call on the fake chain (_batch has its own test)
            out = [c.call_raw(w3, t, [f], f["name"], *a) for t, f, a in calls]
            return None if None in out and not allow_failure else out
        with mock.patch.object(pa, "call_raw", c.call_raw), mock.patch.object(pa, "_batch", batch):
            got = pa.gmx_v2_rows(c, self.ORC)
        return got and ([(label.split(" ")[-1] if "atomic" in label else label.split(" ")[0], src, None if v is None else round(v, 6)) for label, src, v in got[0]], round(got[1], 6))

    def test_provider_rows_value_pools_and_open_interest_and_atomic_rows_overlap(self):
        cs = self.cs
        rows, total = self.rows(self.chain())
        self.assertEqual(rows[:3], [(cs(t), cs(self.PROV), v) for t, v in sorted(
            [(self.ETH, 2004.0), (self.USDC, 1500.0), (self.ANIME, None)], key=lambda x: cs(x[0]))])  # ANIME: a pool, no price
        self.assertEqual(total, 3504.0)  # the provider rows: the priced supply
        self.assertCountEqual(rows[3:], [(cs(self.ETH), cs(self.FE), 3000.0), (cs(self.USDC), cs(self.FU), 3000.0)])  # MT1 only: ANIME has no feed

    def test_a_token_without_provider_is_skipped_and_atomic_rows_need_every_switch(self):
        rows, _ = self.rows(self.chain(anime_provider=ZERO))
        self.assertNotIn(self.cs(self.ANIME), [r[0] for r in rows])
        for kw in ({"enabled": False}, {"atomic": False}, {"disabled": True}):
            with self.subTest(**kw):
                self.assertEqual(len(self.rows(self.chain(**kw))[0]), 3)
        for kw in ({"enabled": None}, {"atomic": None}):
            with self.subTest(**kw):
                self.assertIsNone(self.rows(self.chain(**kw)))
        c = self.chain(disabled=None)  # the withdrawal flag unread: raises, the entry point fails closed
        with self.assertRaises(RuntimeError):
            self.rows(c)

    def test_every_unread_part_of_the_market_read_is_unread(self):
        gk = pa._gk
        c = self.chain()
        c.answers.pop((self.READER.lower(), "getMarket", (self.DS, self.MT2)))  # one market unread
        self.assertIsNone(self.rows(c))
        c = self.chain()
        c.answers[(self.DS.lower(), "getAddressValuesAt", (gk("MARKET_LIST"), 0, 2))] = [self.MT1]  # the list shorter than its count
        self.assertIsNone(self.rows(c))
        c = self.chain(anime_provider=ZERO)
        for t in (self.ETH, self.USDC):  # no token the resolved Oracle can price: a wrong or stale oracle, unknown
            c.answers[(self.DS.lower(), "getAddress", (pa._gkey(("bytes32", gk("ORACLE_PROVIDER_FOR_TOKEN")), ("address", self.ORC), ("address", t)),))] = ZERO
        self.assertIsNone(self.rows(c))

    def test_an_atomic_row_with_an_unpriced_leg_is_unknown_not_zero(self):
        c = self.chain()
        c.answers[(self.FE.lower(), "latestRoundData")] = (0, -1, 0, 0, 0)  # ETH has no usable price
        rows, _ = self.rows(c)
        self.assertEqual({r[2] for r in rows[3:]}, {None})  # MT1's atomic rows: material, not 0

    def test_batch_decodes_through_the_patched_decoder(self):  # the return-data guard patches eth_abi.decode after import
        f = pa._fn("getUint", ("bytes32",), ("uint256",))
        with mock.patch.object(pa, "call_raw", lambda *a, **k: [(True, pa.abi_encode(["uint256"], [7]))]), \
                mock.patch.object(pa.eth_abi, "decode", side_effect=ValueError("wrong size")):
            with self.assertRaises(ValueError):
                pa._batch(None, [(A(1), f, (b"\x01" * 32,))])

    def test_an_unread_controller_delay_is_no_delay(self):
        gk, rs = pa._gk, pa.GMX_ROLESTORE
        dao, ctc, tc = A(720), A(721), A(722)
        c = Chain(answers={(rs, "getRoleMembers", (gk("ROLE_ADMIN"), 0, 50)): [dao, ctc, tc], (tc, "timelockController"): ctc, (ctc, "oracle"): self.ORC})
        with mock.patch.object(pa, "call_raw", c.call_raw):
            self.assertIsNone(pa.gmx_v2_governance(c)[0])

    def test_batch_encodes_decodes_and_fails_closed(self):
        f = pa._fn("getUint", ("bytes32",), ("uint256",))
        key = b"\x01" * 32
        seen = []

        def agg(ok, data):
            def call(w3, address, abi, name, enc, retries=4):
                seen.append(enc)
                return [(ok, data)]
            return call
        with mock.patch.object(pa, "call_raw", agg(True, pa.abi_encode(["uint256"], [7]))):
            self.assertEqual(pa._batch(None, [(A(1), f, (key,))]), [7])
        self.assertEqual(seen[0][0][2], pa.Web3.keccak(text="getUint(bytes32)")[:4] + key)
        with mock.patch.object(pa, "call_raw", agg(False, b"")):
            self.assertIsNone(pa._batch(None, [(A(1), f, (key,))]))  # a failed sub-call: the batch is unread, never a zero
            self.assertEqual(pa._batch(None, [(A(1), f, (key,))], allow_failure=True), [None])  # probing: that getter is absent
        with mock.patch.object(pa, "call_raw", lambda *a, **k: None):
            self.assertIsNone(pa._batch(None, [(A(1), f, (key,))]))

    def test_governance_resolves_the_live_controller(self):
        gk, rs = pa._gk, pa.GMX_ROLESTORE
        dao, ctc, tc = A(720), A(721), A(722)
        c = Chain(answers={(rs, "getRoleMembers", (gk("ROLE_ADMIN"), 0, 50)): [dao, ctc, tc], (tc, "timelockController"): ctc,
                           (ctc, "getMinDelay"): 86400, (ctc, "oracle"): self.ORC})
        with mock.patch.object(pa, "call_raw", c.call_raw):
            delay, own, controller, oracle = pa.gmx_v2_governance(c)
            self.assertEqual((delay, controller, oracle), (86400, self.cs(ctc), self.cs(self.ORC)))
            self.assertTrue({dao, ctc, tc} <= own)
            c.answers[(tc.lower(), "timelockController")] = A(723)  # names a contract that is not ROLE_ADMIN: unresolved
            self.assertEqual(pa.gmx_v2_governance(c)[2:], (None, None))

    def test_entry_points_pass_the_priced_supply_as_total(self):
        seen = {}

        def fake_score(w3, rows, delay, specs, own, notes, total=None):
            seen.update(delay=delay, total=total)
            return 52
        c = Chain(answers={(pa.GMX_V1_VAULT, "gov"): A(730), (A(730), "buffer"): 86400})
        with mock.patch.object(pa, "call_raw", c.call_raw), mock.patch.object(pa, "score", fake_score), \
                mock.patch.object(pa, "gmx_v1_rows", lambda w3, v: ([("x", A(1), 10), ("all", A(2), 10)], 10)), \
                mock.patch.object(pa, "gmx_v2_rows", lambda w3, o: ([("x", A(1), 10), ("y", A(2), 10)], 10)), \
                mock.patch.object(pa, "gmx_v2_governance", lambda w3, r: (86400, set(), A(3), A(4))):
            self.assertEqual(pa.for_gmx_v1(c, pa.GMX_V1_VAULT, None, []), 52)
            self.assertEqual(seen, {"delay": 86400, "total": 10})
            seen.clear()
            self.assertEqual(pa.for_gmx_v2(c, pa.GMX_ROLESTORE, None, []), 52)
            self.assertEqual(seen, {"delay": 86400, "total": 10})


class TestGmxV1Rows(unittest.TestCase):
    V, VPF, T1, T2, T3, F1, F3 = (A(800 + i) for i in range(7))

    def rows(self, **over):
        cs = pa.Web3.to_checksum_address
        answers = {(self.V, "priceFeed"): self.VPF, (self.V, "allWhitelistedTokensLength"): 3}
        for i, t in enumerate((self.T1, self.T2, self.T3)):
            answers[(self.V, "allWhitelistedTokens", (i,))] = t
        answers.update({(self.V, "whitelistedTokens", (cs(self.T1),)): True, (self.V, "whitelistedTokens", (cs(self.T2),)): False,  # T2 delisted (MIM)
                        (self.V, "whitelistedTokens", (cs(self.T3),)): True,
                        (self.VPF, "priceFeeds", (cs(self.T1),)): self.F1, (self.VPF, "priceFeeds", (cs(self.T3),)): self.F3,
                        (self.V, "poolAmounts", (cs(self.T1),)): 2 * 10 ** 8, (self.V, "getMaxPrice", (cs(self.T1),)): 3 * 10 ** 30,
                        (self.V, "tokenDecimals", (cs(self.T1),)): 8, (self.V, "poolAmounts", (cs(self.T3),)): 10 ** 6,
                        (self.V, "getMaxPrice", (cs(self.T3),)): 10 ** 30, (self.V, "tokenDecimals", (cs(self.T3),)): 6})
        for k, v in over.items():
            answers[(self.V, k, (cs(self.T3),))] = v
        c = Chain(answers=answers)
        with mock.patch.object(pa, "call_raw", c.call_raw):
            return pa.gmx_v1_rows(c, self.V)

    def test_whitelisted_tokens_and_a_configuration_row_over_the_pool(self):
        cs = pa.Web3.to_checksum_address
        self.assertEqual(self.rows(), ([(cs(self.T1), cs(self.F1), 6.0), (cs(self.T3), cs(self.F3), 1.0),
                                        ("VaultPriceFeed configuration (all tokens)", cs(self.VPF), 7.0)], 7.0))
        rows, total = self.rows(poolAmounts=None)  # an unread token: its row and the configuration row are unknown (material)
        self.assertEqual([r[2] for r in rows], [6.0, None, None])
        self.assertEqual(total, 6.0)
        rows, _ = self.rows(whitelistedTokens=None)  # whether the Vault still prices T3 is unknown: a row with no source
        self.assertIn((cs(self.T3), None, None), rows)
        self.assertIsNone(rows[-1][2])

    def test_an_unread_token_address_is_a_row(self):
        cs = pa.Web3.to_checksum_address
        answers = {(self.V, "priceFeed"): self.VPF, (self.V, "allWhitelistedTokensLength"): 1}
        c = Chain(answers=answers)
        with mock.patch.object(pa, "call_raw", c.call_raw):
            rows, _ = pa.gmx_v1_rows(c, self.V)
        self.assertEqual(rows[0], ("whitelisted token 0", None, None))
        self.assertEqual(rows[-1], ("VaultPriceFeed configuration (all tokens)", cs(self.VPF), None))


CS = pa.Web3.to_checksum_address
R_CODE, P_CODE = b"\x60\x01\x60\x00\x55", b"\x60\x02\x60\x00\xfa"  # a router build (it writes its state), a Pendle adapter build
USD = pa.EULER_USD
(FACTORY, UA, TL, ROUTER, V1, V2, V3, V4, ASSET_A, ASSET_B, COL_EVK, COL_ASSET, COL_X, COL_NONE, ADAPTER_A, ADAPTER_C, ORACLE_B,
 PENDLE, MARKET, SY, SY_IMPL, PADMIN, EARN, CROSS) = (A(600 + i) for i in range(24))


class TestEuler(unittest.TestCase):
    """Euler V2 (2026-10-05): router, factory-upgrade, EVK-rate and Pendle specs, the vault sources, the factory and Earn
    entry points. Each test fails when its branch is removed."""
    def setUp(self):
        p = mock.patch.object(pa, "EULER_FACTORY_GOVERNOR_HASH", pa.Web3.keccak(CODE).hex().removeprefix("0x"))  # the fake FactoryGovernor
        p.start()
        self.addCleanup(p.stop)
        self.revert = pa.EULER_NOT_SUPPORTED  # what an unanswered resolveOracle reverts with in this fake
        p = mock.patch.object(pa, "_revert_selector", lambda *a, **k: self.revert)
        p.start()
        self.addCleanup(p.stop)
        for name, value in (("EULER_ROUTER_TEMPLATE", pa.masked_template(R_CODE)), ("PENDLE_UNIVERSAL_TEMPLATE", pa.masked_template(P_CODE))):
            p = mock.patch.object(pa, name, value)
            p.start()
            self.addCleanup(p.stop)

    def chain(self, answers=None, codes=None, storage=None):
        a = {(PROXY, "aggregator"): AGG, (PROXY, "owner"): SAFE49, (AGG, "owner"): SAFE49, (OWNED_FEED, "owner"): EOA,
             (FACTORY, "upgradeAdmin"): UA, (UA, "getRoleMemberCount"): 1, (UA, "getRoleMember"): TL, (TL, "getMinDelay"): 345600}
        a.update(answers or {})
        cd = {x: CODE for x in (PROXY, AGG, SAFE49, SAFE22, ADAPTER_A, ORACLE_B, UA, TL, SY_IMPL, PADMIN, OWNED_FEED, CROSS)}
        cd.update({ROUTER: R_CODE, PENDLE: P_CODE, ADAPTER_C: b"\x60\x2a\x60\x00\x52", MARKET: CODE, SY: CODE})
        cd.update(codes or {})
        return Chain(answers=a, safes={SAFE49: ([A(100 + i) for i in range(9)], 4), SAFE22: ([A(200), A(201)], 2)}, codes=cd, storage=storage)

    def run_spec(self, spec, c, gov=86400):
        with mock.patch.object(pa, "call_raw", c.call_raw), mock.patch.object(pa, "safe_owners_and_threshold", c.safe):
            return spec(c, gov)

    def statuses(self, paths):
        return [(p["status"], p["composite"]) for p in paths]

    def test_router_spec(self):
        spec = lambda own=(): pa.euler_router_spec(ROUTER, own)  # noqa: E731
        self.assertEqual(self.statuses(self.run_spec(spec(), self.chain({(ROUTER, "governor"): SAFE22}))), [("scored", 29)])
        self.assertEqual(self.statuses(self.run_spec(spec((SAFE22,)), self.chain({(ROUTER, "governor"): SAFE22}))), [("own", None)])
        self.assertEqual(self.statuses(self.run_spec(spec(), self.chain({(ROUTER, "governor"): ZERO}))), [("constant", None)])
        self.assertEqual(self.statuses(self.run_spec(spec(), self.chain())), [("UNREAD", None)])  # governor() unread: never frozen
        for kw in ({"codes": {ROUTER: R_CODE + b"\x00"}}, {"storage": {(ROUTER, pa.IMPL_SLOT): A(9)}}):  # another build, a proxy
            c = self.chain({(ROUTER, "governor"): SAFE22}, **kw)
            self.assertEqual(self.statuses(self.run_spec(spec(), c)), [("UNREAD", None)], kw)

    def test_factory_upgrade_path(self):
        up = lambda c, gov=86400, own=(): self.run_spec(lambda w3, g: [pa.euler_factory_upgrade_path(w3, FACTORY, g, {a.lower() for a in own})], c, gov)[0]["status"]  # noqa: E731
        self.assertEqual(up(self.chain()), "governance-grade")
        self.assertEqual(up(self.chain(), gov=400000), "UNREAD")  # a timelock shorter than the target's delay
        self.assertEqual(up(self.chain(), gov=None), "UNREAD")  # no delay of its own: no bar
        self.assertEqual(up(self.chain(), own=(UA,)), "own")
        self.assertEqual(up(self.chain(), own=(TL,)), "own")
        self.assertEqual(up(self.chain({(UA, "getRoleMemberCount"): 2})), "UNREAD")  # a second admin is not resolved
        self.assertEqual(up(self.chain({(FACTORY, "upgradeAdmin"): None})), "UNREAD")
        c = self.chain()
        c.codes[TL.lower()] = b"\x60\x02"  # the admin timelock's code is not a verified build: its delay does not count
        self.assertEqual(up(c), "UNREAD")
        c = self.chain()
        c.codes[UA.lower()] = b"\x60\x02"  # nor is a FactoryGovernor that is another build: it may route setImplementation elsewhere
        self.assertEqual(up(c), "UNREAD")
        c = self.chain(storage={(UA, pa.IMPL_SLOT): A(9)})  # the pinned build behind a proxy slot is not that build either
        self.assertEqual(up(c), "UNREAD")

    def test_evk_rate_spec(self):
        spec = pa.evk_rate_spec(COL_EVK, FACTORY, ())
        cfg = lambda up: {(FACTORY, "isProxy"): True, (FACTORY, "getProxyConfig"): (up, A(1), b"")}  # noqa: E731
        self.assertEqual([p["status"] for p in self.run_spec(spec, self.chain(cfg(False)))], ["bounded"])
        self.assertEqual([p["status"] for p in self.run_spec(spec, self.chain(cfg(True)))], ["bounded", "governance-grade"])
        self.assertEqual([p["status"] for p in self.run_spec(spec, self.chain({(FACTORY, "isProxy"): True}))], ["bounded", "governance-grade"])  # config unread
        for answers in ({(FACTORY, "isProxy"): False}, {}):  # not listed by the factory, or unread
            self.assertEqual([p["status"] for p in self.run_spec(spec, self.chain(answers))], ["UNREAD"])
        self.assertEqual([p["status"] for p in self.run_spec(pa.evk_rate_spec(COL_EVK, None, ()), self.chain(cfg(False)))], ["UNREAD"])

    def pendle(self, answers=None, storage=None, codes=None, pinned=True):
        a = {(PENDLE, "pendleMarket"): MARKET, (MARKET, "readTokens"): (SY, A(1), A(2)), (PENDLE, "quote"): USD, (PADMIN, "owner"): SAFE22, (SY, "owner"): EOA}
        a.update(answers or {})
        st = {(SY, pa.ADMIN_SLOT): PADMIN, (SY, pa.IMPL_SLOT): SY_IMPL}
        st.update(storage or {})
        with mock.patch.object(pa, "PENDLE_SY_PAUSE_ONLY_IMPLS", {SY_IMPL: pa.Web3.keccak(CODE).hex().removeprefix("0x")} if pinned else {}):
            return self.statuses(self.run_spec(pa.pendle_universal_spec(PENDLE), self.chain(a, codes=codes, storage=st)))

    def test_pendle_spec(self):
        self.assertEqual(self.pendle(), [("scored", 29)])  # the SY upgrade: ProxyAdmin -> owner(), a 2-of-2 Safe
        self.assertEqual(self.pendle(pinned=False), [("scored", 29), ("scored", 2)])  # an implementation not analyzed: its owner() too
        self.assertEqual(self.pendle({(PENDLE, "quote"): SY}), [("bounded", None)])  # quoted in SY: the SY rate is not read
        self.assertEqual(self.pendle(storage={(SY, pa.ADMIN_SLOT): None}), [("UNREAD", None)])  # a proxy with no readable admin
        self.assertEqual(self.pendle(storage={(SY, pa.ADMIN_SLOT): None, (SY, pa.IMPL_SLOT): None}), [("scored", 2)])  # not a proxy: owner()
        self.assertEqual(self.pendle({(PENDLE, "quote"): None}), [("UNREAD", None)])
        self.assertEqual(self.pendle(codes={PENDLE: P_CODE + b"\x00"}), [("UNREAD", None)])  # another build
        self.assertEqual(self.pendle(storage={(MARKET, pa.IMPL_SLOT): A(9)}), [("UNREAD", None)])  # an upgradeable market
        self.assertEqual(self.pendle({(MARKET, "readTokens"): None}), [("UNREAD", None)])
        beacon = A(960)  # a BeaconProxy SY: no admin or implementation slot, its beacon's owner upgrades it
        self.assertEqual(self.pendle({(beacon, "owner"): EOA, (beacon, "implementation"): SY_IMPL, (SY, "owner"): SAFE22},
                                     storage={(SY, pa.ADMIN_SLOT): None, (SY, pa.IMPL_SLOT): None, (SY, pa.BEACON_SLOT): beacon},
                                     codes={beacon: CODE}), [("scored", 2)])  # the beacon owner; the pinned implementation's owner() only pauses

    def test_pendle_adapters_get_their_spec_through_cross_legs(self):
        specs = {}
        c = self.chain({(CROSS, "oracleBaseCross"): PENDLE, (CROSS, "oracleCrossQuote"): ADAPTER_A, (PENDLE, "pendleMarket"): MARKET})
        with mock.patch.object(pa, "call_raw", c.call_raw):
            pa._register_adapter_specs(c, CROSS, specs)
        self.assertEqual(set(specs), {PENDLE.lower()})

    def factory_chain(self, extra=None):
        ltv = lambda b, l: (b, l, 0, 0, 0)  # noqa: E731
        a = {(FACTORY, "getProxyListLength"): 4, (FACTORY, "getProxyListSlice"): [V1, V2, V3, V4],
             (V1, "oracle"): ROUTER, (V1, "unitOfAccount"): USD, (V1, "asset"): ASSET_A, (V1, "LTVList"): [COL_EVK, COL_X, COL_NONE],
             (V1, "LTVFull", (CS(COL_EVK),)): ltv(8000, 8500), (V1, "LTVFull", (CS(COL_X),)): ltv(0, 0), (V1, "LTVFull", (CS(COL_NONE),)): ltv(7000, 0),
             (ROUTER, "governor"): UA, (ROUTER, "resolveOracle", (10 ** 18, CS(ASSET_A), CS(USD))): (1, ASSET_A, USD, ADAPTER_A),
             (ROUTER, "resolveOracle", (10 ** 18, CS(COL_EVK), CS(USD))): (1, COL_ASSET, USD, ADAPTER_C),
             (ROUTER, "resolvedVaults", (CS(COL_EVK),)): COL_ASSET, (V1, "totalAssets"): 10 ** 9,
             (ROUTER, "getQuote", (10 ** 9, CS(ASSET_A), CS(USD))): 1000,
             (FACTORY, "isProxy"): True, (FACTORY, "getProxyConfig"): (False, A(1), b""), (ADAPTER_A, "feed"): PROXY,
             (V2, "oracle"): ZERO,  # an escrow vault: reads no price
             (V3, "oracle"): ROUTER, (V3, "unitOfAccount"): USD, (V3, "asset"): ASSET_A, (V3, "LTVList"): [],  # lends against nothing
             (V4, "oracle"): ORACLE_B, (V4, "unitOfAccount"): A(0xBBBB), (V4, "asset"): ASSET_B, (V4, "LTVList"): [COL_X],
             (V4, "LTVFull", (CS(COL_X),)): None, (V4, "totalAssets"): 5, (ORACLE_B, "feed"): OWNED_FEED}
        a.update(extra or {})
        return self.chain(a)

    def test_vault_sources_and_rows(self):
        c, notes, specs = self.factory_chain(), [], {}
        with mock.patch.object(pa, "call_raw", c.call_raw):
            rows = pa.euler_rows(c, [V1, V2, V3, V4], FACTORY, {UA.lower()}, specs, notes)
        self.assertEqual(rows, [(V1, (CS(ROUTER), CS(ADAPTER_A), CS(COL_EVK), CS(ADAPTER_C)), 1000), (V4, (CS(ORACLE_B),), None)])
        self.assertEqual(set(specs), {ROUTER.lower(), COL_EVK.lower()})  # the router and the vault it converts through
        with mock.patch.object(pa, "call_raw", c.call_raw):  # a USD vault is valued by its own oracle's quote
            self.assertEqual(pa.euler_vault_sources(c, V1, FACTORY, set(), {}, [])[1], 1000)
        self.assertTrue(any(f"prices no {CS(COL_NONE)}" in n for n in notes))  # an unpriced collateral secures nothing
        c = self.factory_chain({(ROUTER, "getQuote", (5, CS(ASSET_B), CS(USD))): 7})  # a non-USD vault priced by a USD vault's oracle
        with mock.patch.object(pa, "call_raw", c.call_raw):
            self.assertEqual(pa.euler_rows(c, [V1, V4], FACTORY, set(), {}, [])[1][2], 7)
        with mock.patch.object(pa, "call_raw", c.call_raw):  # weights replace the USD value; a label that is no address is an unread row
            self.assertEqual(pa.euler_rows(c, [V1, "strategy 3"], FACTORY, set(), {}, [], {V1.lower(): 40}), [(V1, rows[0][1], 40), ("strategy 3", None, None)])

    def test_unread_vault_parts_are_rows_with_no_source(self):
        for extra in ({(V1, "oracle"): None}, {(V1, "LTVList"): None}):
            c = self.factory_chain(extra)
            with mock.patch.object(pa, "call_raw", c.call_raw):
                self.assertEqual(pa.euler_vault_sources(c, V1, FACTORY, set(), {}, []), ((), None), extra)
        c = self.factory_chain({(ROUTER, "resolvedVaults", (CS(COL_EVK),)): None})  # a conversion step unread: that part is UNREAD
        with mock.patch.object(pa, "call_raw", c.call_raw):
            srcs, _ = pa.euler_vault_sources(c, V1, FACTORY, set(), {}, [])
        self.assertIn(CS(ADAPTER_A), srcs)  # what was resolved is still walked
        self.assertTrue(any(isinstance(x, str) and x.startswith("unread:") and "conversion chain" in x for x in srcs))
        c = self.factory_chain({(V1, "totalAssets"): None})
        with mock.patch.object(pa, "call_raw", c.call_raw):
            self.assertIsNone(pa.euler_vault_sources(c, V1, FACTORY, set(), {}, [])[1])
        c, notes = self.factory_chain({(V1, "LTVFull", (CS(COL_X),)): None}), []  # an unread LTV counts as live: COL_X is resolved
        with mock.patch.object(pa, "call_raw", c.call_raw):
            pa.euler_vault_sources(c, V1, FACTORY, set(), {}, notes)
        self.assertTrue(any(f"prices no {CS(COL_X)}" in n for n in notes))

    def test_only_price_oracle_not_supported_means_unpriced(self):
        self.revert = bytes.fromhex("08c379a0")  # Error("Stale price") from an ERC4626 the router converts through
        c, notes = self.factory_chain(), []
        with mock.patch.object(pa, "call_raw", c.call_raw):
            srcs, _ = pa.euler_vault_sources(c, V1, FACTORY, set(), {}, notes)
        self.assertIn(CS(ADAPTER_A), srcs)  # the asset's resolved adapter is still walked
        self.assertTrue(any(x.startswith("unread:") and "not with PriceOracle_NotSupported" in x for x in srcs))
        self.assertFalse(any("unpriced" in n for n in notes))
        nts = []
        with mock.patch.object(pa, "call_raw", c.call_raw), mock.patch.object(pa, "safe_owners_and_threshold", c.safe):
            self.assertLessEqual(pa.score(c, [("v", srcs, 100)], 86400, {}, set(), nts), 20)  # capped at 20; a lower resolved path still counts
        self.assertTrue(any("resolveOracle" in n and "UNREAD" in n for n in nts))

    def test_a_liquidation_ltv_still_ramping_keeps_the_collateral_live(self):
        for target, live in ((Chain.now + 1000, True), (Chain.now - 1, False)):
            with self.subTest(live=live):
                c, notes = self.factory_chain({(V1, "LTVFull", (CS(COL_EVK),)): (0, 0, 9600, target, 2592000),
                                               (V1, "LTVFull", (CS(COL_NONE),)): (0, 0, 0, 0, 0)}), []
                with mock.patch.object(pa, "call_raw", c.call_raw):
                    got = pa.euler_vault_sources(c, V1, FACTORY, set(), {}, notes)
                self.assertEqual(got[0] is not None and CS(COL_EVK) in (got[0] or ()), live)

    def test_a_self_referencing_cross_adapter_terminates(self):
        specs, c = {}, self.chain({(CROSS, "oracleBaseCross"): CROSS, (CROSS, "oracleCrossQuote"): CROSS})
        with mock.patch.object(pa, "call_raw", c.call_raw):
            pa._register_adapter_specs(c, CROSS, specs)
        self.assertEqual(specs, {})

    def test_a_long_conversion_chain_is_unread(self):
        hops = [A(900 + i) for i in range(7)]  # base -> 6 vaults -> the priced base: more than 4 hops
        extra = {(ROUTER, "resolveOracle", (10 ** 18, CS(COL_EVK), CS(USD))): (1, hops[-1], USD, ADAPTER_C),
                 (ROUTER, "resolvedVaults", (CS(COL_EVK),)): hops[0]}
        for a, b in zip(hops, hops[1:]):
            extra[(ROUTER, "resolvedVaults", (CS(a),))] = b
        c = self.factory_chain(extra)
        with mock.patch.object(pa, "call_raw", c.call_raw):
            srcs, _ = pa.euler_vault_sources(c, V1, FACTORY, set(), {}, [])
        self.assertTrue(any(isinstance(x, str) and x.startswith("unread:") for x in srcs))
        self.assertNotIn(CS(ADAPTER_C), srcs)  # the adapter at the end of an unread chain is not taken as known

    def test_an_unread_part_keeps_a_lower_scored_path(self):
        rows = [("v", (FEED_ETH, "unread: something"), 100)]
        call, safe, w3 = chain()
        with mock.patch.object(pa, "call_raw", call), mock.patch.object(pa, "safe_owners_and_threshold", safe):
            self.assertEqual(pa.score(w3, rows, 86400, {}, set(), []), 20)  # the Chainlink 52 is above the cap: 20
        rows = [("v", (EOA, "unread: something"), 100)]
        with mock.patch.object(pa, "call_raw", call), mock.patch.object(pa, "safe_owners_and_threshold", safe):
            self.assertEqual(pa.score(w3, rows, 86400, {}, set(), []), 2)  # a bare key below the cap still counts

    def test_a_zero_quote_tries_the_next_usd_oracle(self):
        router2 = A(950)
        c = self.factory_chain({(ROUTER, "getQuote", (5, CS(ASSET_B), CS(USD))): 0, (router2, "getQuote", (5, CS(ASSET_B), CS(USD))): 7,
                                (V3, "oracle"): router2, (V3, "LTVList"): [COL_EVK], (V3, "LTVFull", (CS(COL_EVK),)): (8000, 8500, 0, 0, 0)})
        with mock.patch.object(pa, "call_raw", c.call_raw):
            rows = pa.euler_rows(c, [V1, V3, V4], FACTORY, set(), {}, [])
        self.assertEqual([r[2] for r in rows if r[0] == V4], [7])

    def test_a_chain_spec_wins_over_the_generic_rate_spec(self):
        c, specs = self.factory_chain(), {COL_EVK.lower(): "chain spec"}
        with mock.patch.object(pa, "call_raw", c.call_raw):
            pa.euler_vault_sources(c, V1, FACTORY, set(), specs, [])
        self.assertEqual(specs[COL_EVK.lower()], "chain spec")

    def test_for_euler_factory(self):
        c, notes = self.factory_chain(), []
        with mock.patch.object(pa, "call_raw", c.call_raw), mock.patch.object(pa, "safe_owners_and_threshold", c.safe):
            self.assertEqual(pa.for_euler_factory(c, FACTORY, None, notes), 2)  # V4's feed owner, a bare EOA; V4 value unknown: material
        self.assertTrue(any(f"EulerRouter {CS(ROUTER)}: own" in n for n in notes))  # governor = upgradeAdmin: own
        self.assertTrue(any("EVK vault rate" in n and "bounded" in n for n in notes))
        self.assertTrue(any("345600s" in n and "2 lending vaults of 4" in n for n in notes))

    def test_for_euler_earn(self):
        c = self.factory_chain({(EARN, "timelock"): 86400, (EARN, "owner"): SAFE22, (EARN, "curator"): SAFE22, (EARN, "withdrawQueueLength"): 3,
                                (EARN, "withdrawQueue", (0,)): V1, (EARN, "withdrawQueue", (1,)): V3, (EARN, "config", (CS(V1),)): (10, 0, True, 0),
                                (EARN, "config", (CS(V3),)): (0, 0, True, 0), (V1, "previewRedeem", (10,)): 100, (ROUTER, "governor"): SAFE22})
        notes = []
        with mock.patch.object(pa, "call_raw", c.call_raw), mock.patch.object(pa, "safe_owners_and_threshold", c.safe):
            self.assertEqual(pa.for_euler_earn(c, EARN, None, notes, factory=FACTORY), 20)  # strategy 2 unread
        self.assertTrue(any("strategy 2" in n for n in notes if pa.UNREAD_MARK in n))
        # the router's governor is the Earn's curator Safe, which re-points prices at once: scored, not own
        self.assertTrue(any(f"EulerRouter {CS(ROUTER)} governor" in n and "scored" in n and "reach 100.00%" in n for n in notes))
        self.assertTrue(any(f"EVK vault rate {COL_EVK}: bounded" in n for n in notes))  # its collateral vault, on the factory passed in
        with mock.patch.object(pa, "call_raw", c.call_raw):
            self.assertEqual(pa.euler_earn_weights(c, EARN), {V1.lower(): 100, V3.lower(): 0, "strategy 2": None})

    def test_the_earn_curator_is_not_own(self):
        c = self.factory_chain({(EARN, "timelock"): 86400, (EARN, "owner"): SAFE49, (EARN, "curator"): SAFE22, (EARN, "withdrawQueueLength"): 1,
                                (EARN, "withdrawQueue", (0,)): V1, (EARN, "config", (CS(V1),)): (10, 0, True, 0), (V1, "previewRedeem", (10,)): 100,
                                (ROUTER, "governor"): SAFE22})
        notes = []
        with mock.patch.object(pa, "call_raw", c.call_raw), mock.patch.object(pa, "safe_owners_and_threshold", c.safe):
            pa.for_euler_earn(c, EARN, None, notes, factory=FACTORY)
        self.assertFalse(any(f"EulerRouter {CS(ROUTER)}: own" in n for n in notes))  # the Earn's timelock does not gate the router
        self.assertTrue(any(f"EulerRouter {CS(ROUTER)} governor" in n and f"composite {pa.composite(*pa._safe_rooted(2, 2))}" in n for n in notes))

    def test_euler_factory_governance(self):
        c = self.chain()
        with mock.patch.object(pa, "call_raw", c.call_raw):
            self.assertEqual(pa.euler_factory_governance(c, FACTORY), (345600, {CS(FACTORY), CS(UA), CS(TL)}))
        c = self.chain({(UA, "getRoleMemberCount"): 2})
        with mock.patch.object(pa, "call_raw", c.call_raw):
            self.assertEqual(pa.euler_factory_governance(c, FACTORY), (None, {CS(FACTORY), CS(UA)}))


class TestEulerChainSpecs(unittest.TestCase):
    """The Plasma sdeUSD and Monad vUSD rate specs: scored while every pinned fact holds, UNREAD otherwise."""
    SDE, SDE_IMPL, VUSD, STRAT, STRAT_IMPL, GLOBALS = ("0x7884A8457f0E63e82C89A87fE48E8Ba8223DB069", "0xb2F28684B04660a334ea27401E5468323213011B",
                                                       pa.VUSD_MONAD[0], pa.VUSD_STRATEGY[0], pa.VUSD_STRATEGY[1], A(700))
    H = pa.Web3.keccak(CODE).hex().removeprefix("0x")

    def run_spec(self, spec, c, **consts):
        with mock.patch.object(pa, "call_raw", c.call_raw), mock.patch.object(pa, "safe_owners_and_threshold", c.safe), mock.patch.multiple(pa, **consts):
            return [(p["status"], p["composite"]) for p in spec(c, 86400)]

    def sde(self, answers=None, impl=None, code=CODE):
        a = {(self.SDE, "owner"): EOA, (self.SDE, "hasRole"): True}
        a.update(answers or {})
        c = Chain(answers=a, codes={self.SDE_IMPL: code, A(9): CODE}, storage={(self.SDE, pa.IMPL_SLOT): impl or self.SDE_IMPL})  # A(9): same code, other address
        return self.run_spec(pa._elixir_sdeusd_plasma, c, SDEUSD_PLASMA_IMPL_HASH=self.H)

    def test_sdeusd_plasma(self):
        self.assertEqual(self.sde(), [("scored", 2)])
        for kw in ({"answers": {(self.SDE, "hasRole"): False}}, {"answers": {(self.SDE, "hasRole"): None}}, {"answers": {(self.SDE, "owner"): None}},
                   {"impl": A(9)}, {"code": CODE + b"\x00"}):
            self.assertEqual(self.sde(**kw), [("UNREAD", None)], kw)

    def vusd(self, answers=None, impl=None, vault_code=CODE):
        a = {(self.VUSD, "strategy"): self.STRAT, (self.STRAT, "securityAdminEnabled"): True, (self.STRAT, "operationsAdminEnabled"): False,
             (self.STRAT, "safetyModule"): ZERO, (self.STRAT, "globals"): self.GLOBALS, (self.STRAT, "investmentManager"): EOA,
             (self.GLOBALS, "securityAdmin"): SAFE22, (self.GLOBALS, "operationsAdmin"): EOA, (self.GLOBALS, "owner"): SAFE22}
        a.update(answers or {})
        c = Chain(answers=a, safes={SAFE22: ([A(200), A(201)], 2)}, codes={self.VUSD: vault_code, self.STRAT_IMPL: CODE, SAFE22: CODE, self.GLOBALS: CODE, A(9): CODE},
                  storage={(self.STRAT, pa.IMPL_SLOT): impl or self.STRAT_IMPL})
        return self.run_spec(pa._accountable_vusd, c, VUSD_MONAD=(self.VUSD, self.H), VUSD_STRATEGY=(self.STRAT, self.STRAT_IMPL.lower(), self.H))

    def test_vusd_monad(self):
        self.assertEqual(self.vusd(), [("scored", 2), ("scored", 29), ("scored", 29)])  # manager EOA; securityAdmin; globals owner
        self.assertEqual(self.vusd({(self.STRAT, "securityAdminEnabled"): False, (self.STRAT, "operationsAdminEnabled"): True}),
                         [("scored", 2), ("scored", 2), ("scored", 29)])  # operationsAdmin (an EOA here) when enabled
        self.assertIn(("UNREAD", None), self.vusd({(self.STRAT, "safetyModule"): A(9)}))  # a safety module: not analyzed
        for kw in ({"answers": {(self.STRAT, "securityAdminEnabled"): None}}, {"answers": {(self.STRAT, "safetyModule"): None}}):
            self.assertIn(("UNREAD", None), self.vusd(**kw), kw)
        for kw in ({"answers": {(self.VUSD, "strategy"): A(9)}}, {"impl": A(9)}, {"vault_code": CODE + b"\x00"}):
            self.assertEqual(self.vusd(**kw), [("UNREAD", None)], kw)

    def test_specs_are_keyed_on_their_contracts(self):
        self.assertIs(pa.PLASMA_SPECS[self.SDE], pa._elixir_sdeusd_plasma)
        self.assertIs(pa.MONAD_SPECS[self.VUSD], pa._accountable_vusd)


class TestRevertSelector(unittest.TestCase):
    """_revert_selector on web3's own exceptions: the selector of a custom error or Error(string), b"" for a bare revert, None
    when the call succeeds; a network failure retries and raises, never a revert."""
    @staticmethod
    def w3(exc=None):
        class Fn:
            def call(self):
                if exc:
                    raise exc
                return 1

        class Functions:
            def __getattr__(self, name):
                return lambda *a: Fn()

        class Contract:
            functions = Functions()

        class Eth:
            def contract(self, address, abi):
                return Contract()

        class W3:
            eth = Eth()
        return W3()

    @mock.patch("time.sleep", lambda s: None)
    def test_each_kind_of_answer(self):
        from web3.exceptions import ContractCustomError, ContractLogicError
        sel = lambda w3: pa._revert_selector(w3, A(1), pa._RESOLVE, "resolveOracle", 1, A(2), A(3))  # noqa: E731
        self.assertEqual(sel(self.w3(ContractCustomError("custom", data="0x4ca22af0" + "00" * 64))), pa.EULER_NOT_SUPPORTED)
        self.assertEqual(sel(self.w3(ContractLogicError("Stale price", data="0x08c379a0" + "00" * 96))), bytes.fromhex("08c379a0"))
        self.assertEqual(sel(self.w3(ContractLogicError("execution reverted", data=None))), b"")
        self.assertIsNone(sel(self.w3()))
        with self.assertRaises(Exception) as ctx:
            sel(self.w3(ConnectionError("rpc down")))
        self.assertIn("-- ConnectionError:", str(ctx.exception))  # retried as a network failure, never read as a revert


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
