"""Each price-consumer scorer puts price_authority's result into oracleAuthorityScore (rule of 2026-10-04), and the Robinhood
Chainlink admin (a provider) carries its own composite. Static checks on the scorer sources. No network."""
import os
import re
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts", "lib"))
sys.path.insert(0, os.path.join(ROOT, "scripts"))


CASES = [  # (scorer file, function, engine entry point, address it must receive)
    ("chains/ethereum-l1/scorers.py", "score_aave_v3_pool", "for_aave", "0x2f39d218133AFaB8F2B819B1066c7E434Ad94E9e"),
    ("chains/ethereum-l1/scorers.py", "score_compound_v3_cusdc", "for_comet", "0xc3d688B66703497DAA19211EEdff47f25384cdc3"),
    ("chains/ethereum-l1/scorers.py", "score_morpho_adpend_usdc", "for_morpho_v1", "0x55555815a5595991C3A0Ff119B59AEF6C8B55555"),
    ("chains/ethereum-l1/scorers.py", "score_morpho_1337_usdc", "for_morpho_v1", "0x94643e86aa5E38DDAc6c7791C1297f4E40cD96c1"),
    ("chains/base-ecosystem/scorers.py", "score_aave_v3_base", "for_aave", "0xe20fCBdBfFC4Dd138cE8b2E6FBb6CB49777ad64D"),
    ("chains/base-ecosystem/scorers.py", "score_compound_v3_comet_base_usdc", "for_comet", "0xb125E6687d4313864e53df431d5425969c15Eb2F"),
    ("chains/arbitrum-ecosystem/scorers.py", "score_aave_v3_pool_arbitrum", "for_aave", "0xa97684ead0e402dC232d5A977953DF7ECBaB3CDb"),
    ("chains/arbitrum-ecosystem/scorers.py", "score_compound_v3_comet_arbitrum_usdc", "for_comet", "0x9c4ec768c28520B50860ea7a15bd7213a9fF58bf"),
    ("chains/plasma-ecosystem/scorers.py", "score_aave_v3_pool_plasma", "for_aave", "0x061D8e131F26512348ee5FA42e2DF1bA9d6505E9"),
    ("chains/monad/scorers.py", "score_aave_v3_monad", "for_aave", "0x34793Fb9935F7bB5E5aE920fb963F39063E7A615"),
    # extended 2026-10-05 to the other price consumers the engine reads as is (live 52 each)
    ("chains/ethereum-l1/scorers.py", "score_aave_v3_horizon_pool", "for_aave", "0x5D39E06b825C1F2B80bf2756a73e28eFAA128ba0"),
    ("chains/base-ecosystem/scorers.py", "score_morpho_gauntlet_usdc_prime_base", "for_morpho_v1", "0xeE8F4eC5672F09119b96Ab6fB59C27E1b7e44b61"),
    ("chains/base-ecosystem/scorers.py", "score_morpho_spark_usdc_vault_base", "for_morpho_v1", "0x7BfA7C4f149E7415b73bdeDfe609237e29CBF34A"),
    ("chains/base-ecosystem/scorers.py", "score_morpho_steakhouse_usdc_base", "for_morpho_v1", "0xbeeF010f9cb27031ad51e3333f9aF9C6B1228183"),
    ("chains/base-ecosystem/scorers.py", "score_morpho_grove_steakhouse_usdc_high_yield_base", "for_morpho_v1", "0xBeEf2d50B428675a1921bC6bBF4bfb9D8cF1461A"),
    # extended 2026-10-05 to the Morpho V1 Steakhouse vaults, the Monad vault and the Morpho Vault V2 targets
    ("chains/ethereum-l1/scorers.py", "score_morpho_steakhouse_usdt_l1", "for_morpho_v1", "0xbEef047a543E45807105E51A8BBEFCc5950fcfBa"),
    ("chains/ethereum-l1/scorers.py", "score_morpho_steakhouse_usdc_l1", "for_morpho_v1", "0xBEEF01735c132Ada46AA9aA4c54623cAA92A64CB"),
    ("chains/ethereum-l1/scorers.py", "score_morpho_steakhouse_prime_usdc_v2", "for_morpho_v2", "0xbeef088055857739C12CD3765F20b7679Def0f51"),
    ("chains/ethereum-l1/scorers.py", "score_morpho_steakhouse_prime_eurcv_v2", "for_morpho_v2", "0xbeef0C075Da5D01112AE5cF34d257074fB5DDB2f"),
    ("chains/monad/scorers.py", "score_morpho_vault_monad", "for_morpho_v1", "0x32841A8511D5c2c5b253f45668780B99139e476D"),
    ("scripts/lib/scorers.py", "score_morpho_steakhouse_usdg", "for_morpho_v2", "0xBeEff033F34C046626B8D0A041844C5d1A5409dd"),
    ("scripts/lib/scorers.py", "score_morpho_vault_generic", "for_morpho_v2", None),  # vault is a parameter: MORE_MORPHO_VAULTS
    # extended 2026-10-05 to the Arbitrum consumers the scope study gave recipes for (live: Radiant 52, GMX V2 52, GMX V1 2)
    ("chains/arbitrum-ecosystem/scorers.py", "score_radiant_lendingpool", "for_aave_v2", "0x454a8dAf74B24037eE2fa073Ce1be9277Ed6160a"),
    ("chains/arbitrum-ecosystem/scorers.py", "score_gmx_v2_rolestore", "for_gmx_v2", "0x3c3d99FD298f679DBC2CEcd132b4eC4d0F5e6e72"),
    ("chains/arbitrum-ecosystem/scorers.py", "score_gmx_v1_vault", "for_gmx_v1", "0x489ee077994B6658eAfA855C308275EAd8097C4A"),
    # extended 2026-10-05 to Euler V2 (live: Plasma eVaultFactory 2, Monad eVaultFactory 2, TelosC Surge EulerEarn 43)
    ("chains/plasma-ecosystem/scorers.py", "score_euler_v2_evault_factory_plasma", "for_euler_factory", "0x42388213C6F56D7E1477632b58Ae6Bba9adeEeA3"),
    ("chains/monad/scorers.py", "score_euler_v2_monad", "for_euler_factory", "0xba4Dd672062dE8FeeDb665DD4410658864483f1E"),
    ("chains/plasma-ecosystem/scorers.py", "score_telos_consilium_euler_earn_plasma", "for_euler_earn", "0xA9C251f8304b1B3Fc2B9e8FCAE78D94eFF82Ac66"),
    # extended 2026-10-05 to SparkLend (Aave V3 rows behind the Sky pause delay, Chronicle Aggor medians)
    ("chains/ethereum-l1/scorers.py", "score_sparklend_pool", "for_sparklend", "0x02C3eA4e34C0cBd694D2adFa2c690EECbC1793eE"),
    # extended 2026-10-05 to Moonwell on Base (a Compound V2 fork; live 52)
    ("chains/base-ecosystem/scorers.py", "score_moonwell_comptroller_base", "for_moonwell", "0xfBb21d0380beE3312B33c4353c8936a0F13EF26C"),
    # extended 2026-10-05 to Fluid Liquidity (its vaults' oracles, weighted by debt)
    ("chains/arbitrum-ecosystem/scorers.py", "score_fluid_liquidity_arbitrum", "for_fluid", "0x52Aa899454998Be5b000Ad077a46Bbe360F4e497"),
    ("chains/plasma-ecosystem/scorers.py", "score_fluid_liquidity_plasma", "for_fluid", "0x52Aa899454998Be5b000Ad077a46Bbe360F4e497"),
    # extended 2026-10-05 to Dolomite on Arbitrum (live: 20, the GMX keeper keys of its GM markets are not bounded)
    ("chains/arbitrum-ecosystem/scorers.py", "score_dolomite_margin_arbitrum", "for_dolomite", "0x6Bd780E7fDf01D77e4d475c821f1e7AE05409072"),
]
SOLANA_CASES = [  # (scorer, its walk call): Kamino Liquidity and Jupiter Lend (live 2026-10-05: 45 and 35)
    ("score_kamino_liquidity", '_kliquidity_oracle_authority(url, gc, admin_sq["time_lock_s"] if admin_sq else None, notes)'),
    ("score_jupiter_lend", "_jupiter_lend_oracle_authority(url, notes)"),
]
MORE_MORPHO_VAULTS = {"0x99347d5F70D3838763f6Bddcf80304C8aa953B57", "0x37788ff0c1d4e45A7FE06BC7e71e0cc00121d0A8", "0xbEeFF0fb1Dc19344A87b8479dAb60A2e16160737",
                      "0xBEEff039907422219Fb367e525954DDC092854d9", "0xbeEfFF136E3684273e6aA75A1669B784B373A4FD"}


SPECS = {"chains/ethereum-l1/": "price_authority.ETHEREUM_SPECS", "chains/monad/": "price_authority.MONAD_SPECS",
         "scripts/lib/": "price_authority.ROBINHOOD_SPECS", "chains/arbitrum-ecosystem/": "price_authority.ARBITRUM_SPECS",
         "chains/plasma-ecosystem/": "price_authority.PLASMA_SPECS", "chains/base-ecosystem/": "price_authority.BASE_SPECS"}


def body_of(rel, fn):
    src = open(os.path.join(ROOT, rel)).read()
    i = src.index(f"\ndef {fn}(")
    j = src.find("\ndef ", i + 5)
    return src[i:j if j > 0 else None]


class TestWiring(unittest.TestCase):
    def test_wiring_is_in_the_source_for_every_case(self):
        """The call is in the function body, with the chain's own w3, the target's address, that chain's specs and the entry's
        own notes list, and its value is what the scorer returns (a behavioural check needs a full fake chain per scorer;
        the live dry-runs of 2026-10-04 exercised each one end to end)."""
        for rel, fn, entry, address in CASES:
            with self.subTest(fn=fn):
                body = body_of(rel, fn)
                self.assertRegex(body, rf"^\ndef {fn}\(w3(: Web3)?[,)]", "the scorer's own chain w3 is what the engine reads")
                call = re.search(rf"oracle_authority = price_authority\.{entry}\((.*)\)", body)
                self.assertIsNotNone(call)
                args = [x.strip() for x in call.group(1).split(",")]
                self.assertEqual(args[0], "w3")
                if address is None:  # the vault is the scorer's parameter, never reassigned, and score_all passes each listed vault
                    self.assertRegex(body, rf"^\ndef {fn}\(w3: Web3, {args[1]}: str, label: str\)")
                    self.assertNotRegex(body, re.compile(rf"^\s*{args[1]} = ", re.M))
                    src = open(os.path.join(ROOT, rel)).read()
                    self.assertIn(f"for addr, label in MORE_MORPHO_VAULTS:\n        results.extend(_safe_score(label, {fn}, w3, addr, label))", src)
                    listed = re.search(r"^MORE_MORPHO_VAULTS = \[(.*?)^\]", src, re.M | re.S).group(1)
                    self.assertEqual(set(re.findall(r'^\s*\("(0x[0-9a-fA-F]{40})"', listed, re.M)), MORE_MORPHO_VAULTS)
                else:
                    value = re.findall(rf"^\s*{args[1]} = (.+)$", body, re.M)
                    if value and not value[0].startswith('"'):  # a module constant, e.g. provider = _HORIZON_PROVIDER
                        value = re.findall(rf"^{value[0]} = (.+)$", open(os.path.join(ROOT, rel)).read(), re.M)
                    self.assertEqual(value, [f'"{address}"'])
                self.assertEqual(args[2], next((v for k, v in SPECS.items() if rel.startswith(k)), "None"))
                self.assertEqual(args[3], "notes")
                after = body[call.end():]
                self.assertNotRegex(after, re.compile(r"^\s*notes = ", re.M), "notes must not be replaced after the engine wrote into it")
                self.assertIn('"notes": notes', after)
                self.assertEqual(body.count('"oracleAuthorityScore":'), 1)
                self.assertIn('"oracleAuthorityScore": oracle_authority', body)

    def test_euler_earn_reads_its_strategies_on_the_plasma_evault_factory(self):
        rel = "chains/plasma-ecosystem/scorers.py"
        body = body_of(rel, "score_telos_consilium_euler_earn_plasma")
        self.assertIn("price_authority.for_euler_earn(w3, surge, price_authority.PLASMA_SPECS, notes, factory=EULER_EVAULT_FACTORY_PLASMA)", body)
        self.assertRegex(open(os.path.join(ROOT, rel)).read(), r'(?m)^EULER_EVAULT_FACTORY_PLASMA = "0x42388213C6F56D7E1477632b58Ae6Bba9adeEeA3"')

    def test_euler_access_control_governor_stays_not_applicable(self):
        body = body_of("chains/plasma-ecosystem/scorers.py", "score_euler_v2_access_control_emergency_governor_plasma")
        self.assertNotIn("price_authority.", body)
        self.assertIn('"oracleAuthorityScore": 100,', body)

    def test_solana_price_consumers_publish_their_own_walk(self):
        """Solana keeps its own engine and formula (decision of 2026-10-05): each consumer's walk is called in its body with
        the scorer's own url and notes, and its value is the published field."""
        for fn, call in SOLANA_CASES:
            with self.subTest(fn=fn):
                body = body_of("chains/solana/scorers.py", fn)
                self.assertRegex(body, rf"^\ndef {fn}\(url\)")
                self.assertEqual(body.count(f"oracle_authority = {call}"), 1)
                after = body[body.index(f"oracle_authority = {call}"):]
                self.assertNotRegex(after, re.compile(r"^\s*notes = ", re.M))
                self.assertIn('"notes": notes', after)
                self.assertEqual(body.count('"oracleAuthorityScore":'), 1)
                self.assertIn('"oracleAuthorityScore": oracle_authority', body)

    def test_robinhood_chainlink_admin_is_its_own_composite(self):
        src = open(os.path.join(ROOT, "scripts/lib/scorers.py")).read()
        i = src.index("\ndef score_chainlink_admin_safe(")
        body = src[i:src.find("\ndef ", i + 5)]
        self.assertIn('"oracleAuthorityScore": composite, "compositeScore": composite', body)


if __name__ == "__main__":
    unittest.main()
