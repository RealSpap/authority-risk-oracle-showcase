"""Robinhood Chain Morpho Vault V2 Purinta USDG and Steakhouse Turbo USDG (2026-10-05): a Safe read as 4-of-8 behind the API3
OwnableCallForwarder scores 50 (the Safe reader is faked here: the proxyless-Safe gate itself is tested in
test_safe_modules.py, with the real code hash checked live), and the spUSDG spec (Sky governance through Spark's bridge,
the rate bounded by code) re-reads every fact on both chains. Fake chains only, no network."""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import price_authority as pa  # noqa: E402
from test_price_authority import A, CODE, Chain  # noqa: E402


def setUpModule():  # the shared fakes' timelock code counts as a verified build here too
    import test_price_authority as _tpa
    _tpa.setUpModule()


def tearDownModule():
    import test_price_authority as _tpa
    _tpa.tearDownModule()


RAY = 10**27
DAY = 86400


class TestApi3ForwarderSafe(unittest.TestCase):
    def test_a_reader_proxy_owned_through_the_forwarder_by_a_4_of_8_safe_scores_50(self):
        proxy, forwarder, safe = A(700), A(701), A(702)
        c = Chain(answers={(proxy, "owner"): forwarder, (forwarder, "owner"): safe},
                  safes={safe: ([A(800 + i) for i in range(8)], 4)}, codes={proxy: CODE, forwarder: CODE, safe: CODE})
        with mock.patch.object(pa, "call_raw", c.call_raw), mock.patch.object(pa, "safe_owners_and_threshold", c.safe):
            paths = pa.controller_of_path(c, proxy, 7 * DAY)
        self.assertEqual([(p["status"], p["composite"]) for p in paths], [("scored", 50)])  # (65, 80, 0)
        self.assertIn("Safe 4-of-8", paths[0]["note"])


class TestSparkSavingsUsdg(unittest.TestCase):
    VAULT, IMPL = pa._cs(pa.SPUSDG[0]), A(710)
    EX, RCV = pa._cs(pa.SPARK_RH_EXECUTOR[0]), pa._cs(pa.SPARK_RH_RECEIVER[0])
    SP, SG, ESM = pa._cs(pa.SPARK_SUBPROXY[0]), pa._cs(pa.SPARK_STARGUARD[0]), pa._cs(pa.SPARK_ESM_PIN[0])
    PP, PAUSE, CHIEF, HAT = pa._cs(pa.SKY_PAUSE_PROXY), pa._cs(pa.SKY_PAUSE), pa._cs(pa.SKY_CHIEF), A(711)

    def code(self, a):
        return CODE + a.lower().encode()  # one distinct code per contract: a swapped contract changes its hash

    def chains(self, rh_over=None, l1_over=None, rh_logs=0, l1_logs=0, l1_chain=1):
        zero = b"\x00" * 32
        rh = Chain(answers={(self.VAULT, "getRoleMemberCount"): 1, (self.VAULT, "getRoleMember"): self.EX,
                            (self.EX, "hasRole", (zero, self.EX)): True, (self.EX, "hasRole", (pa._SUBMISSION_ROLE, self.RCV)): True,
                            (self.VAULT, "minVsr"): RAY, (self.VAULT, "maxVsr"): RAY + 1847694957439350562,
                            (self.VAULT, "vsr"): RAY + 1090862085746321732, (self.EX, "delay"): 0, **(rh_over or {})},
                   codes={a: self.code(a) for a in (self.VAULT, self.IMPL, self.EX, self.RCV)},
                   storage={(self.VAULT, pa.IMPL_SLOT): self.IMPL}, logs=rh_logs)
        l1 = Chain(answers={(self.SP, "wards", (a,)): 1 for a in (self.PP, self.ESM, self.SG)}
                   | {(self.SG, "wards", (self.PP,)): 1, (self.PP, "owner"): self.PAUSE, (self.PAUSE, "authority"): self.CHIEF,
                      (self.PAUSE, "delay"): 2 * DAY, (self.CHIEF, "hat"): self.HAT, (self.HAT, "done"): True, **(l1_over or {})},
                   codes={a: self.code(a) for a in (self.SP, self.SG, self.ESM)}, logs=l1_logs)
        rh.block_number, l1.block_number, l1.chain_id = pa.SPARK_RH_PROOF_BLOCK + 2, pa.SPARK_L1_PROOF_BLOCK + 2, l1_chain
        return rh, l1

    def run_spec(self, rh, l1, gov=3 * DAY, hashes=True):
        h = lambda a: pa.Web3.keccak(self.code(a)).hex().removeprefix("0x")  # noqa: E731
        pins = {"SPUSDG": (self.VAULT, h(self.VAULT), self.IMPL.lower(), h(self.IMPL)), "SPARK_RH_EXECUTOR": (self.EX, h(self.EX)),
                "SPARK_RH_RECEIVER": (self.RCV, h(self.RCV)), "SPARK_SUBPROXY": (self.SP, h(self.SP)),
                "SPARK_STARGUARD": (self.SG, h(self.SG)), "SPARK_ESM_PIN": (self.ESM, h(self.ESM))} if hashes else {}
        with mock.patch.multiple(pa, call_raw=lambda w3, *a, **k: w3.call_raw(w3, *a, **k), **pins), \
                mock.patch.object(pa._wu, "get_w3", lambda url: l1), mock.patch("time.sleep", lambda s: None):
            return [(p["status"], p["composite"]) for p in pa._spark_savings_usdg(rh, gov)]

    def test_sky_governance_through_the_bridge_and_a_bounded_rate(self):
        self.assertEqual(self.run_spec(*self.chains()), [("scored", 81), ("bounded", None)])
        self.assertEqual(self.run_spec(*self.chains(), gov=2 * DAY), [("governance-grade", None), ("bounded", None)])

    def test_registered_and_reached_by_the_walk(self):
        self.assertIs(pa.ROBINHOOD_SPECS[pa.SPUSDG[0]], pa._spark_savings_usdg)
        rh, l1 = self.chains()
        with mock.patch.dict(pa.ROBINHOOD_SPECS, {pa.SPUSDG[0]: lambda w3, gov: [pa.path("x", "bounded")]}):
            self.assertEqual(pa.score(rh, [("spUSDG market", self.VAULT, 100)], 3 * DAY, pa.ROBINHOOD_SPECS), 100)

    def test_every_fact_is_re_read_and_any_other_answer_is_unread(self):
        zero = b"\x00" * 32
        cases = {
            "a second DEFAULT_ADMIN": self.chains(rh_over={(self.VAULT, "getRoleMemberCount"): 2}),
            "DEFAULT_ADMIN is someone else": self.chains(rh_over={(self.VAULT, "getRoleMember"): A(9)}),
            "executor not self-admin": self.chains(rh_over={(self.EX, "hasRole", (zero, self.EX)): False}),
            "receiver lost SUBMISSION": self.chains(rh_over={(self.EX, "hasRole", (pa._SUBMISSION_ROLE, self.RCV)): None}),
            "minVsr below RAY": self.chains(rh_over={(self.VAULT, "minVsr"): RAY - 1}),
            "maxVsr unread": self.chains(rh_over={(self.VAULT, "maxVsr"): None}),
            "a role event on the executor": self.chains(rh_logs=1),
            "a failed role replay": self.chains(rh_logs=ConnectionError("429")),
            "L1 is another chain": self.chains(l1_chain=5),
            "SubProxy lost the pause proxy": self.chains(l1_over={(self.SP, "wards", (self.PP,)): 0}),
            "SubProxy ward unread": self.chains(l1_over={(self.SP, "wards", (self.SG,)): None}),
            "StarGuard ward gone": self.chains(l1_over={(self.SG, "wards", (self.PP,)): 0}),
            "a Rely or Deny on L1": self.chains(l1_logs=1),
            "a failed ward replay": self.chains(l1_logs=ConnectionError("down")),
        }
        for name, (rh, l1) in cases.items():
            with self.subTest(name):
                self.assertEqual(self.run_spec(rh, l1), [("UNREAD", None)])
        rh, l1 = self.chains(l1_over={(self.PAUSE, "owner"): A(9)})  # the pause has an owner: it plots without DSChief
        self.assertEqual(self.run_spec(rh, l1), [("UNREAD", None), ("bounded", None)])  # the governance path is UNREAD, the rate stays bounded
        for who in (self.SP, self.SG):  # each L1 ward set is replayed on its own
            with self.subTest(replay=who):
                rh, l1 = self.chains()
                l1.get_logs = lambda flt, who=who: [{}] if flt["address"].lower() == who.lower() else []
                self.assertEqual(self.run_spec(rh, l1), [("UNREAD", None)])
        rh, l1 = self.chains()
        rh.storage[(self.VAULT.lower(), pa.IMPL_SLOT)] = A(9)  # an upgraded implementation
        self.assertEqual(self.run_spec(rh, l1), [("UNREAD", None)])
        for who in (self.EX, self.RCV, self.VAULT):  # swapped code on Robinhood Chain
            with self.subTest(code=who):
                rh, l1 = self.chains()
                rh.codes[who.lower()] = CODE
                self.assertEqual(self.run_spec(rh, l1), [("UNREAD", None)])
        for who in (self.SP, self.SG, self.ESM):  # swapped code on Ethereum
            with self.subTest(code=who):
                rh, l1 = self.chains()
                l1.codes[who.lower()] = CODE
                self.assertEqual(self.run_spec(rh, l1), [("UNREAD", None)])

    def test_the_pinned_hashes_are_the_real_ones(self):
        self.assertEqual(self.run_spec(*self.chains(), hashes=False), [("UNREAD", None)])  # fake code is not the pinned code
        for pin in (pa.SPUSDG[1], pa.SPUSDG[3], pa.SPARK_RH_EXECUTOR[1], pa.SPARK_RH_RECEIVER[1], pa.SPARK_SUBPROXY[1],
                    pa.SPARK_STARGUARD[1], pa.SPARK_ESM_PIN[1]):
            self.assertRegex(pin, r"^[0-9a-f]{64}$")


if __name__ == "__main__":
    unittest.main()
