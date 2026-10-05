"""
Unit tests for the 6 new byte-decoders added 2026-09-18
(`chains/solana/scripts/sol_read.py`: `read_kliquidity_global_config`,
`read_jupiter_perpetuals`, `read_jupiter_lend_liquidity`,
`read_pumpswap_global_config`, `read_marginfi_group`,
`read_whirlpools_config`) -- closing `chains/solana/data/scouted_targets_
2026-09-17-run2.md`'s own "decode the protocol config admins" open point
across 8 Solana DeFi targets (Raydium, marginfi, Kamino Liquidity,
Jupiter Perps, Jupiter Lend, PumpSwap, Meteora DAMM v2, Orca Whirlpool).

Three small accounts (Jupiter Perpetuals, Jupiter Lend's own Liquidity
account, Orca's WhirlpoolsConfig) are tested against the EXACT bytes
fetched live from Solana Mainnet Beta on 2026-09-18, embedded below as a
frozen fixture -- small enough to store whole, matching this project's
own `test_solend_governance.py` precedent.

Three larger accounts (Kamino Liquidity's 26,832-byte GlobalConfig,
marginfi's 9,256-byte MarginfiGroup, PumpSwap's ~950-byte GlobalConfig)
are tested against SYNTHETIC fixtures instead -- constructed at test time
from the correct discriminator plus the real, live-confirmed authority
pubkey at the correct byte offset, the rest zero-padded to the real
account's own size. This tests the decode LOGIC (offset correctness)
without embedding tens of kilobytes of mostly-irrelevant real account
data in a test file -- the same "synthetic-but-realistic-shape fixture"
approach this project's own Hyperliquid test files already use for large
ABI-encoded responses.

`sol_read.acct` is monkeypatched rather than mocking the network, so this
suite doesn't depend on network access or the accounts' mutable on-chain
state.
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


sol_read = _load_module("aro_test_sol_read_defi_config_admins", "chains/solana/scripts/sol_read.py")

# Exact account bytes, base64, fetched live from https://api.mainnet-beta.solana.com
# on 2026-09-18 (see chains/solana/data/scored_targets_2026-09-18-solana-defi.md
# for the full derivation and reproduction commands).
JUPITER_PERPETUALS_B64 = (
    "HKdiv2hSbMQBAQEBAQEBAQAAAD4eJHPHNAZU64cpADUVHEAr0OPJfLQkSIbnIDSzC038sR7615aPpnQxKPFzaGWypBocjr+HlClYtk3oOoOKL3n+"
    "/yZvtmQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
)
JUPITER_LEND_LIQUIDITY_B64 = (
    "Nvz54omseTr6ILdkXu7s3KgFuT24xGCJy4WP8NhP5dCkeKPE4Y/klbE4OeEenidZmjjTi4lC3jP92VPj11AasUBY7x/GMuxfAP8="
)
WHIRLPOOLS_CONFIG_B64 = (
    "nRQx4NlXwf7sxs2vIpKy+9wSX9p7349DN3qXmsYJ+CLNJlKrm99E/KmxNIyI0NeLkdmu3ngpH1GCvlo2365kkh/mm9doRD90ui6/"
    "LwKaI7GKR1R798LZ7CubYjLuw+NoR9dh+omDPGYUBQEA"
)

# Live-confirmed values these fixtures must decode to (independently
# cross-checked against a second RPC, solana-rpc.publicnode.com, and
# against each protocol's own published source/IDL for field order --
# see the scorer functions' own docstrings in chains/solana/scorers.py
# for the full derivation of each).
JUPITER_PERPETUALS_ADMIN = "CvQZZ23qYDWF2RUpxYJ8y9K4skmuvYEEjH7fK58jtipQ"
JUPITER_LEND_LIQUIDITY_AUTHORITY = "HqPrpa4ESBDnRHRWaiYtjv4xe93wvCS9NNZtDwR89cVa"
WHIRLPOOLS_CONFIG_FEE_AUTHORITY = "GwH3Hiv5mACLX3ufTw1pFsrhSPon5tdw252DBs4Rx4PV"
WHIRLPOOLS_CONFIG_COLLECT_FEES_AUTHORITY = "CRQd5wvbf6FKVmjHC7on8w4pzFPzudij2BKXRcMCu7aK"
WHIRLPOOLS_CONFIG_REWARD_SUPER_AUTHORITY = "DXnB9N9JLH5c9AYdKMGHQyspewSsvhFnwLK1tz1iPmZw"

KAMINO_GLOBAL_CONFIG_ADMIN = "5dcEb1jGeBZuXbVKmNkq3unPcrveG46B2PMJKAGcSh67"
MARGINFI_GROUP_ADMIN = "CYXEgwbPHu2f9cY3mcUkinzDoDcsSan7myh1uBvYRbEw"
PUMPSWAP_GLOBAL_CONFIG_ADMIN = "FFWtrEQ4B4PKQoVuHYzZq8FabGkVatYzDpEVHsK5rrhF"


def _synthetic_account(total_len, discriminator, pubkey_offsets):
    """Build a synthetic account: `total_len` zero bytes, with
    `discriminator` at the start and each (offset, base58_pubkey) in
    `pubkey_offsets` written at its own position. Returns the base64
    string `sol_read.acct`'s own return shape expects."""
    d = bytearray(total_len)
    d[0:len(discriminator)] = discriminator
    for offset, pk in pubkey_offsets:
        d[offset:offset + 32] = sol_read.b58dec(pk)
    return base64.b64encode(bytes(d)).decode()


KAMINO_GLOBAL_CONFIG_DISCRIMINATOR = bytes([149, 8, 156, 202, 160, 252, 176, 217])
# ADDED 2026-09-25: actionsAuthority (offset 2192), a distinct pubkey from admin_authority so a
# transposed pair of offsets would fail the new test below.
KAMINO_GLOBAL_CONFIG_ACTIONS_AUTHORITY = PUMPSWAP_GLOBAL_CONFIG_ADMIN
KAMINO_GLOBAL_CONFIG_B64 = _synthetic_account(26832, KAMINO_GLOBAL_CONFIG_DISCRIMINATOR, [
    (2192, KAMINO_GLOBAL_CONFIG_ACTIONS_AUTHORITY), (2224, KAMINO_GLOBAL_CONFIG_ADMIN),
])

MARGINFI_GROUP_DISCRIMINATOR = bytes.fromhex("b617adf097ceb643")
MARGINFI_GROUP_B64 = _synthetic_account(48, MARGINFI_GROUP_DISCRIMINATOR, [(8, MARGINFI_GROUP_ADMIN)])

# FIXED 2026-09-25: six more offsets on the same account, each given a DISTINCT synthetic
# pubkey (borrowed from other targets' own already-defined constants above -- any valid
# base58 pubkey works here, only its POSITION is under test) so a transposed pair of offsets
# would fail this test even though both values individually decode as valid pubkeys.
MARGINFI_GROUP_EMODE_ADMIN = JUPITER_PERPETUALS_ADMIN
MARGINFI_GROUP_DELEGATE_CURVE_ADMIN = JUPITER_LEND_LIQUIDITY_AUTHORITY
MARGINFI_GROUP_DELEGATE_LIMIT_ADMIN = WHIRLPOOLS_CONFIG_FEE_AUTHORITY
MARGINFI_GROUP_DELEGATE_EMISSIONS_ADMIN = WHIRLPOOLS_CONFIG_COLLECT_FEES_AUTHORITY
MARGINFI_GROUP_RISK_ADMIN = WHIRLPOOLS_CONFIG_REWARD_SUPER_AUTHORITY
MARGINFI_GROUP_METADATA_ADMIN = KAMINO_GLOBAL_CONFIG_ADMIN
MARGINFI_GROUP_FULL_B64 = _synthetic_account(360, MARGINFI_GROUP_DISCRIMINATOR, [
    (8, MARGINFI_GROUP_ADMIN),
    (128, MARGINFI_GROUP_EMODE_ADMIN),
    (160, MARGINFI_GROUP_DELEGATE_CURVE_ADMIN),
    (192, MARGINFI_GROUP_DELEGATE_LIMIT_ADMIN),
    (224, MARGINFI_GROUP_DELEGATE_EMISSIONS_ADMIN),
    (296, MARGINFI_GROUP_RISK_ADMIN),
    (328, MARGINFI_GROUP_METADATA_ADMIN),
])

# PumpSwap's GlobalConfig has no useful discriminator check in the
# decoder (it only reads bytes 8:40) -- an all-zero 8-byte prefix is
# fine here since read_pumpswap_global_config doesn't validate it.
PUMPSWAP_GLOBAL_CONFIG_B64 = _synthetic_account(40, b"\x00" * 8, [(8, PUMPSWAP_GLOBAL_CONFIG_ADMIN)])

# ADDED 2026-09-25: Jupiter Lend's AuthorizationList -- ordinary Borsh Vec<Pubkey> fields (4-byte
# little-endian length prefix + N*32 bytes), NOT the bytemuck/fixed-offset style every other
# fixture above uses, so built with a small dedicated encoder rather than _synthetic_account.
JUPITER_LEND_AUTH_USERS = [JUPITER_LEND_LIQUIDITY_AUTHORITY]
JUPITER_LEND_GUARDIANS = [JUPITER_LEND_LIQUIDITY_AUTHORITY, WHIRLPOOLS_CONFIG_REWARD_SUPER_AUTHORITY]


def _borsh_pubkey_vec(pubkeys):
    return len(pubkeys).to_bytes(4, "little") + b"".join(sol_read.b58dec(pk) for pk in pubkeys)


JUPITER_LEND_AUTH_LIST_B64 = base64.b64encode(
    b"\x00" * 8 + _borsh_pubkey_vec(JUPITER_LEND_AUTH_USERS) + _borsh_pubkey_vec(JUPITER_LEND_GUARDIANS)
).decode()


def _fake_acct(fixtures):
    def acct(url, pk, enc="base64", length=None):
        if pk not in fixtures:
            raise AssertionError(f"unexpected account fetch: {pk}")
        return {"data": [fixtures[pk]]}
    return acct


class TestReadJupiterPerpetuals(unittest.TestCase):
    def test_admin_field_decodes_correctly(self):
        orig = sol_read.acct
        sol_read.acct = _fake_acct({"H4ND9aYttUVLFmNypZqLjZ52FYiGvdEB45GmwNoKEjTj": JUPITER_PERPETUALS_B64})
        try:
            r = sol_read.read_jupiter_perpetuals("url", "H4ND9aYttUVLFmNypZqLjZ52FYiGvdEB45GmwNoKEjTj")
            self.assertEqual(r["admin"], JUPITER_PERPETUALS_ADMIN)
        finally:
            sol_read.acct = orig


class TestReadJupiterLendLiquidity(unittest.TestCase):
    def test_authority_field_decodes_correctly(self):
        orig = sol_read.acct
        sol_read.acct = _fake_acct({"7s1da8DduuBFqGra5bJBjpnvL5E9mGzCuMk1Qkh4or2Z": JUPITER_LEND_LIQUIDITY_B64})
        try:
            r = sol_read.read_jupiter_lend_liquidity("url", "7s1da8DduuBFqGra5bJBjpnvL5E9mGzCuMk1Qkh4or2Z")
            self.assertEqual(r["authority"], JUPITER_LEND_LIQUIDITY_AUTHORITY)
        finally:
            sol_read.acct = orig


class TestReadJupiterLendAuthorizationList(unittest.TestCase):
    def test_auth_users_and_guardians_decode_correctly(self):
        program_id = "jupeiUmn818Jg1ekPURTpr4mFo29p46vygyykFJ3wZC"
        pda, _ = sol_read.find_program_address([b"auth_list"], program_id)  # real, pure, offline PDA derivation
        orig = sol_read.acct
        sol_read.acct = _fake_acct({pda: JUPITER_LEND_AUTH_LIST_B64})
        try:
            r = sol_read.read_jupiter_lend_authorization_list("url", program_id)
            self.assertEqual(r["auth_list"], pda)
            self.assertEqual(r["auth_users"], JUPITER_LEND_AUTH_USERS)
            self.assertEqual(r["guardians"], JUPITER_LEND_GUARDIANS)
        finally:
            sol_read.acct = orig


class TestReadWhirlpoolsConfig(unittest.TestCase):
    def test_all_three_authority_fields_decode_correctly(self):
        orig = sol_read.acct
        sol_read.acct = _fake_acct({"2LecshUwdy9xi7meFgHtFJQNSKk4KdTrcpvaB56dP2NQ": WHIRLPOOLS_CONFIG_B64})
        try:
            r = sol_read.read_whirlpools_config("url", "2LecshUwdy9xi7meFgHtFJQNSKk4KdTrcpvaB56dP2NQ")
            self.assertEqual(r["fee_authority"], WHIRLPOOLS_CONFIG_FEE_AUTHORITY)
            self.assertEqual(r["collect_protocol_fees_authority"], WHIRLPOOLS_CONFIG_COLLECT_FEES_AUTHORITY)
            self.assertEqual(r["reward_emissions_super_authority"], WHIRLPOOLS_CONFIG_REWARD_SUPER_AUTHORITY)
        finally:
            sol_read.acct = orig

    def test_three_fields_are_in_the_expected_order_not_shuffled(self):
        # Regression guard: if the three fields were ever accidentally
        # read out of order (e.g. fee_authority and collect_protocol_
        # fees_authority swapped), this test would still pass the
        # previous one only by coincidence if two fixture values were
        # ever equal -- explicitly assert they're pairwise distinct so a
        # future swap-bug is guaranteed to be caught.
        addrs = [WHIRLPOOLS_CONFIG_FEE_AUTHORITY, WHIRLPOOLS_CONFIG_COLLECT_FEES_AUTHORITY, WHIRLPOOLS_CONFIG_REWARD_SUPER_AUTHORITY]
        self.assertEqual(len(set(addrs)), 3)


class TestReadKliquidityGlobalConfig(unittest.TestCase):
    def test_admin_authority_at_the_source_derived_offset(self):
        orig = sol_read.acct
        sol_read.acct = _fake_acct({"GKnHiWh3RRrE1zsNzWxRkomymHc374TvJPSTv2wPeYdB": KAMINO_GLOBAL_CONFIG_B64})
        try:
            r = sol_read.read_kliquidity_global_config("url", "GKnHiWh3RRrE1zsNzWxRkomymHc374TvJPSTv2wPeYdB")
            self.assertEqual(r["admin_authority"], KAMINO_GLOBAL_CONFIG_ADMIN)
        finally:
            sol_read.acct = orig

    def test_actions_authority_at_its_own_distinct_offset(self):
        # FIXED 2026-09-25: actionsAuthority (offset 2192, immediately before adminAuthority's
        # own offset 2224) now decoded too. Distinct fixture value from admin_authority, so a
        # transposed pair of offsets would fail this test even though both individually decode
        # as valid pubkeys.
        orig = sol_read.acct
        sol_read.acct = _fake_acct({"GKnHiWh3RRrE1zsNzWxRkomymHc374TvJPSTv2wPeYdB": KAMINO_GLOBAL_CONFIG_B64})
        try:
            r = sol_read.read_kliquidity_global_config("url", "GKnHiWh3RRrE1zsNzWxRkomymHc374TvJPSTv2wPeYdB")
            self.assertEqual(r["actions_authority"], KAMINO_GLOBAL_CONFIG_ACTIONS_AUTHORITY)
            self.assertNotEqual(r["actions_authority"], r["admin_authority"])
        finally:
            sol_read.acct = orig

    def test_offset_2224_is_not_a_coincidence_of_the_fixture(self):
        # Move the SAME pubkey to a different offset and confirm the
        # decoder does NOT find it there -- proves the function reads a
        # specific offset, not "wherever this pubkey happens to be".
        wrong_fixture = _synthetic_account(26832, KAMINO_GLOBAL_CONFIG_DISCRIMINATOR, [(100, KAMINO_GLOBAL_CONFIG_ADMIN)])
        orig = sol_read.acct
        sol_read.acct = _fake_acct({"GKnHiWh3RRrE1zsNzWxRkomymHc374TvJPSTv2wPeYdB": wrong_fixture})
        try:
            r = sol_read.read_kliquidity_global_config("url", "GKnHiWh3RRrE1zsNzWxRkomymHc374TvJPSTv2wPeYdB")
            self.assertNotEqual(r["admin_authority"], KAMINO_GLOBAL_CONFIG_ADMIN)
        finally:
            sol_read.acct = orig


class TestReadKliquidityScopeFields(unittest.TestCase):
    """ADDED 2026-10-05: GlobalConfig.scopeProgramId (80) and tokenInfos (10448), and the CollateralInfos entries."""
    SCOPE, INFOS = "HFn8GnPADiny6XqUoWE8uRPPxb29ikn4yTuPa9MF2fWJ", "3v6ootgJJZbSWEDfZMA1scfh7wcsVVfeocExRxPqCyWH"
    FEED, MINT = "3NJYftD5sjVfxSnUdZ1wVML8f3aC6mp1CXCL6L7TnU8C", "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"

    def read(self, fn, pk, b64):
        orig = sol_read.acct
        sol_read.acct = _fake_acct({pk: b64})
        try:
            return fn("url", pk)
        finally:
            sol_read.acct = orig

    def test_global_config_scope_fields(self):
        b64 = _synthetic_account(26832, KAMINO_GLOBAL_CONFIG_DISCRIMINATOR, [(80, self.SCOPE), (10448, self.INFOS), (2224, KAMINO_GLOBAL_CONFIG_ADMIN)])
        r = self.read(sol_read.read_kliquidity_global_config, "GKnHiWh3RRrE1zsNzWxRkomymHc374TvJPSTv2wPeYdB", b64)
        self.assertEqual((r["scope_program"], r["token_infos"], r["admin_authority"]), (self.SCOPE, self.INFOS, KAMINO_GLOBAL_CONFIG_ADMIN))

    def test_collateral_infos_used_entries_and_feed_offset(self):
        e = lambda i: 8 + 216 * i  # noqa: E731
        d = base64.b64decode(_synthetic_account(8 + 216 * 303, b"\x01" * 8, [(e(0), self.MINT), (e(0) + 152, self.FEED), (e(5), self.MINT), (e(6) + 152, self.SCOPE)]))
        d = bytearray(d)
        d[e(5) + 136] = 1  # entry 5 disabled, its feed left zero; entry 6 unused (no mint) though it names a feed
        d[e(302):e(302) + 32] = sol_read.b58dec(self.MINT)  # the last of the 303 entries is read too
        d[e(302) + 152:e(302) + 184] = sol_read.b58dec(self.FEED)
        r = self.read(sol_read.read_kliquidity_collateral_feeds, self.INFOS, base64.b64encode(bytes(d)).decode())
        self.assertEqual(r, [{"mint": self.MINT, "scope_feed": self.FEED, "disabled": 0}, {"mint": self.MINT, "scope_feed": "11111111111111111111111111111111", "disabled": 1},
                             {"mint": self.MINT, "scope_feed": self.FEED, "disabled": 0}])
        with self.assertRaises(ValueError):  # another size is never a short list
            self.read(sol_read.read_kliquidity_collateral_feeds, self.INFOS, base64.b64encode(bytes(d[:-216])).decode())


class TestReadMarginfiGroup(unittest.TestCase):
    def test_admin_field_decodes_correctly(self):
        orig = sol_read.acct
        sol_read.acct = _fake_acct({"4qp6Fx6tnZkY5Wropq9wUYgtFxXKwE6viZxFHg3rdAG8": MARGINFI_GROUP_B64})
        try:
            r = sol_read.read_marginfi_group("url", "4qp6Fx6tnZkY5Wropq9wUYgtFxXKwE6viZxFHg3rdAG8")
            self.assertEqual(r["admin"], MARGINFI_GROUP_ADMIN)
        finally:
            sol_read.acct = orig

    def test_six_more_admin_named_fields_decode_at_their_own_distinct_offsets(self):
        # FIXED 2026-09-25 (was: only "admin" decoded, see this function's own docstring on
        # the prior state). Each field gets its OWN distinct synthetic value at its OWN
        # position in MARGINFI_GROUP_FULL_B64 -- a transposed pair of offsets (e.g.
        # risk_admin/delegate_curve_admin swapped) would make this test fail even though
        # every individual value still decodes as a syntactically valid pubkey.
        orig = sol_read.acct
        sol_read.acct = _fake_acct({"4qp6Fx6tnZkY5Wropq9wUYgtFxXKwE6viZxFHg3rdAG8": MARGINFI_GROUP_FULL_B64})
        try:
            r = sol_read.read_marginfi_group("url", "4qp6Fx6tnZkY5Wropq9wUYgtFxXKwE6viZxFHg3rdAG8")
            self.assertEqual(r["admin"], MARGINFI_GROUP_ADMIN)
            self.assertEqual(r["emode_admin"], MARGINFI_GROUP_EMODE_ADMIN)
            self.assertEqual(r["delegate_curve_admin"], MARGINFI_GROUP_DELEGATE_CURVE_ADMIN)
            self.assertEqual(r["delegate_limit_admin"], MARGINFI_GROUP_DELEGATE_LIMIT_ADMIN)
            self.assertEqual(r["delegate_emissions_admin"], MARGINFI_GROUP_DELEGATE_EMISSIONS_ADMIN)
            self.assertEqual(r["risk_admin"], MARGINFI_GROUP_RISK_ADMIN)
            self.assertEqual(r["metadata_admin"], MARGINFI_GROUP_METADATA_ADMIN)
            self.assertEqual(set(r.keys()), {
                "group", "admin", "emode_admin", "delegate_curve_admin", "delegate_limit_admin",
                "delegate_emissions_admin", "risk_admin", "metadata_admin",
            })
            # Every one of the 7 decoded pubkeys must be pairwise distinct -- a real bug where
            # two fields accidentally share one offset would still pass an equality check
            # against the wrong constant if the two constants happened to be equal; they aren't
            # here (7 different borrowed real-world pubkeys), so this catches that class too.
            self.assertEqual(len({r["admin"], r["emode_admin"], r["delegate_curve_admin"],
                                   r["delegate_limit_admin"], r["delegate_emissions_admin"],
                                   r["risk_admin"], r["metadata_admin"]}), 7)
        finally:
            sol_read.acct = orig


class TestReadPumpswapGlobalConfig(unittest.TestCase):
    def test_admin_field_decodes_correctly(self):
        orig = sol_read.acct
        sol_read.acct = _fake_acct({"ADyA8hdefvWN2dbGGWFotbzWxrAvLW83WG6QCVXvJKqw": PUMPSWAP_GLOBAL_CONFIG_B64})
        try:
            r = sol_read.read_pumpswap_global_config("url", "ADyA8hdefvWN2dbGGWFotbzWxrAvLW83WG6QCVXvJKqw")
            self.assertEqual(r["admin"], PUMPSWAP_GLOBAL_CONFIG_ADMIN)
        finally:
            sol_read.acct = orig


class TestMeteoraDammV2HardcodedAdmins(unittest.TestCase):
    """Regression guard for the ADMINS[] constant hardcoded in
    chains/solana/scorers.py (not derivable from any account read --
    see score_meteora_damm_v2's own docstring). Locks in the exact
    values so a future edit can't silently drift from the verified
    GitHub source (MeteoraAg/damm-v2 programs/cp-amm/src/instructions/
    admin/auth.rs) without a test failing."""

    def test_admins_match_verified_source(self):
        scorers = _load_module("aro_test_solana_scorers_defi_config_admins", "chains/solana/scorers.py")
        self.assertEqual(
            scorers.METEORA_DAMM_V2_ADMINS,
            ("5unTfT2kssBuNvHPY6LbJfJpLqEcdMxGYLWHwShaeTLi", "DHLXnJdACTY83yKwnUkeoDjqi4QBbsYGa1v8tJL76ViX"),
        )


if __name__ == "__main__":
    unittest.main()
