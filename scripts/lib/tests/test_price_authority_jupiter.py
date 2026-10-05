"""oracleAuthorityScore of Jupiter Lend (chains/solana/scorers.py::_jupiter_lend_oracle_authority, rule of 2026-10-04 with the
Solana formula, extended 2026-10-05). Offline: a fake Solana account store answers sol_read.rpc (getMultipleAccounts,
getProgramAccounts) with byte layouts built from the IDLs and sources the scorer cites; the structured readers (programs,
Squads, serum multisig, Pyth Config, spl-governance) return dicts. The pure PDA math (find_program_address, read_squads_vault)
runs for real, so every PDA relation in the fixture is a real one. The EVM fake Chain of test_price_authority does not apply
to Solana accounts.

Fixture: five priced vaults (a Chainlink feed $100, the Huma PST $10, a Pyth push feed $10, a Sanctum stake pool $10, Marinade
$0.5 = 0.38%, immaterial) and one DEX smart-collateral vault whose shares are unpriced (value unknown: material) pegged
through the same Chainlink feed. Expected composites, by the Solana formula (METHODOLOGY 6.1, squads_v3 shape for a t-of-n
without delay): Chainlink 4-of-9 (55, 78, 0) = 45; Pyth guardians 3-of-5 (50, 69, 0) = 41; Pyth governance 6-of-9 (60, 100, 0)
= 54; Pyth DAO (70, 70, 0) = 49; Sanctum 6-of-11 (60, 100, 0) = 54; Huma loss authority Squads v4 2-of-3 no delay (45, 57, 0) =
35. The Huma pool owner and Huma owner (12 h) are governance-grade against the 6 h VaultAdmin delay."""
import base64
import importlib.util
import os
import sys
import unittest

REPO_ROOT = os.path.join(os.path.dirname(__file__), "..", "..", "..")


def _load(name, rel):
    path = os.path.abspath(os.path.join(REPO_ROOT, rel))
    if os.path.dirname(path) not in sys.path:
        sys.path.insert(0, os.path.dirname(path))
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


S = _load("aro_test_solana_scorers_jupiter_price", "chains/solana/scorers.py")
R = S.sol_read
PDA = R.find_program_address
key = R.b58dec
VAULT0 = lambda ms: R.read_squads_vault(ms, 0)["vault"]  # noqa: E731
TOKEN = S.TOKEN_PROGRAMS[0]
SANCTUM = S.SANCTUM_LST_PROGRAMS[0]
FEED = "CH31Xns5z3M1cTAbKW34jcxPPciazARpijcHj9rxtemt"  # SOL/USD
CL_SIGNER, CL_BUMP = PDA([key(S.CHAINLINK_MULTISIG)], S.CHAINLINK_MULTISIG_PROGRAM)
PYTH_GOV = PDA([b"squad", key(S.PYTH_GOVERNANCE_MULTISIG), (1).to_bytes(4, "little"), b"authority"], S.PYTH_SQUADS_PROGRAM)[0]
FEED_ID = bytes(range(32))
PYTH_ACCOUNT = PDA([(0).to_bytes(2, "little"), FEED_ID], S.PYTH_PUSH_ORACLE)[0]
POOL_STATE = PDA([b"pool_state", key(S.HUMA_POOL_CONFIG)], S.HUMA_PROGRAMS[0])[0]
HUMA_ID = bytes([7] * 32)
HUMA_CONFIG = PDA([b"huma_config", HUMA_ID], S.HUMA_PROGRAMS[1])[0]
POOL_AUTHORITY = PDA([b"pool_authority", key(S.HUMA_POOL_CONFIG)], S.HUMA_PROGRAMS[0])[0]
STAKE_POOL, MARINADE_STATE = "pyZMBjpWsVjKANAYK5mpNbKiws2krjRPZ2N2UYCSnbP", "8szGkuLTAux9XMgZ2vtY39jVSowEcpBfFfD8hXSEqdGC"
DEX, DEX_PEG = "G41Dqz9A1vW2kGpMRUkTFt3Nmn8D1ysYPNcZGGKD7N1f", "H8i4Bz4i7ttvp2E5S8TfAj5ATD4qPsT1QtmSZ1fK3dgB"
MINT_A, MINT_B, MINT_C, MINT_D = (R.b58(bytes([i]) * 32) for i in (11, 12, 13, 14))
ORACLES = {n: R.b58(bytes([40 + n]) * 32) for n in range(1, 9)}
STAKE_ACCOUNT, SINGLE_MINT = R.b58(bytes([21]) * 32), R.b58(bytes([22]) * 32)
GOVERNANCE_DELAY = 21600


def _types(name):
    return S.JL_SOURCE_TYPES.index(name)


def vault_config(vid, oracle, mint):
    d = bytearray(219)
    d[:8], d[8:10] = S._disc("VaultConfig"), vid.to_bytes(2, "little")
    d[26:58], d[122:154], d[154:186] = key(oracle), key(S.JL_ORACLE_PROGRAM), key(mint)
    return bytes(d)


def vault_state(vid, tokens):
    d = bytearray(127)
    d[:8], d[8:10] = S._disc("VaultState"), vid.to_bytes(2, "little")
    d[23:31], d[99:107] = int(tokens * 10**9).to_bytes(8, "little"), (10**12).to_bytes(8, "little")
    return bytes(d)


def oracle(*sources):
    d = bytearray(279)
    d[:8], d[10:14] = S._disc("Oracle"), len(sources).to_bytes(4, "little")
    for i, (src, kind) in enumerate(sources):
        d[14 + 66 * i:46 + 66 * i], d[79 + 66 * i] = key(src), _types(kind)
    return bytes(d)


class FakeSolana:
    def __init__(self):
        self.accounts = {}  # pubkey: (owner, data, lamports)
        self.fail = False

    def put(self, pk, owner, data, lamports=1):
        self.accounts[pk] = (owner, bytes(data), lamports)

    def rpc(self, url, method, params=None, tries=4):
        if self.fail:
            raise R.SolRpcError("down")
        enc = lambda d: [base64.b64encode(d).decode(), "base64"]  # noqa: E731
        if method == "getMultipleAccounts":
            return {"value": [None if (a := self.accounts.get(k)) is None else {"owner": a[0], "data": enc(a[1]), "lamports": a[2]} for k in params[0]]}
        if method == "getProgramAccounts":
            program, cfg = params
            disc, n = cfg["filters"][0]["memcmp"]["bytes"], (cfg.get("dataSlice") or {}).get("length")
            return [{"pubkey": k, "account": {"data": enc(a[1][:n] if n else a[1])}} for k, a in self.accounts.items()
                    if a[0] == program and R.b58(a[1][:8]) == disc]
        raise AssertionError(f"unexpected rpc {method}")


class JupiterLendPriceAuthorityTest(unittest.TestCase):
    PATCHED = ("rpc", "read_program", "read_squads", "read_squadsv3", "read_legacy_serum_multisig", "read_pyth_config",
               "read_governance_v2", "read_realm")

    def setUp(self):
        self._orig = {n: getattr(R, n) for n in self.PATCHED}
        self._orig_prices = S._usd_prices
        self._reset()

    def _reset(self):
        """The live shape of 2026-10-05, rebuilt from scratch (each guard case starts from it)."""
        f = self.f = FakeSolana()
        self.prices = {MINT_A: 1.0, S.HUMA_PST_MINT: 1.0, MINT_B: 1.0, MINT_C: 1.0, MINT_D: 1.0, S.WSOL_MINT: 1.0}
        self.programs = {p: {"upgrade_authority": VAULT0(S.JL_UPGRADE_MS)} for p in S.JL_OWN_PROGRAMS}
        self.programs.update({p: {"upgrade_authority": CL_SIGNER} for p in (S.CHAINLINK_STORE_PROGRAM, S.CHAINLINK_OCR2_PROGRAM, S.CHAINLINK_MULTISIG_PROGRAM)})
        self.programs.update({p: {"upgrade_authority": PYTH_GOV} for p in (S.PYTH_RECEIVER, S.PYTH_PUSH_ORACLE)})
        self.programs[S.PYTH_WORMHOLE] = {"upgrade_authority": PYTH_GOV, "last_deploy_slot": S.PYTH_WORMHOLE_DEPLOY_SLOT}
        self.programs.update({p: {"upgrade_authority": S.PYTH_DAO_GOVERNANCE} for p in (S.PYTH_SQUADS_PROGRAM, S.PYTH_DAO_PROGRAM, S.PYTH_STAKING_PROGRAM)})
        self.programs[SANCTUM] = {"upgrade_authority": PDA([b"squad", key(S.SANCTUM_MS), (1).to_bytes(4, "little"), b"authority"], S.SQUADS_V3_PROGRAM)[0]}
        self.programs.update({p: {"upgrade_authority": VAULT0(S.HUMA_MS)} for p in S.HUMA_PROGRAMS})
        self.programs[S.STAKE_PROGRAM] = {"upgrade_authority": None}
        self.squads = {S.JL_ADMIN_MS: (5, 10, GOVERNANCE_DELAY), S.HUMA_MS: (5, 9, 43200), S.HUMA_POOL_OWNER_MS: (3, 4, 43200), S.HUMA_LOSS_MS: (2, 3, 0)}
        self.v3 = {S.SANCTUM_MS: (6, 11), S.PYTH_GOVERNANCE_MULTISIG: (6, 9)}
        self.serum = {"owners": [f"o{i}" for i in range(9)], "threshold": 4, "nonce": CL_BUMP}
        self.pyth_config = {"governance_authority": PYTH_GOV, "target_governance_authority": None, "wormhole": S.PYTH_WORMHOLE,
                            "valid_data_sources": list(S.PYTH_DATA_SOURCES), "minimum_signatures": 3}
        self.dao = {"account_type": 19, "realm": S.PYTH_DAO_REALM, "council_vote_threshold": {"kind": "Disabled", "pct": None},
                    "community_vote_threshold": {"kind": "YesVotePercentage", "pct": 67}, "transactions_hold_up_time_s": 0,
                    "voting_base_time_s": 604800, "voting_cool_off_time_s": 0, "community_vote_tipping": 0}
        self.realm = {"authority": None, "council_mint": None}
        R.rpc = f.rpc
        R.read_program = lambda url, p: dict(self.programs[p], program=p)
        R.read_squads = lambda url, ms: {"config_authority": S.SYSTEM_PROGRAM_DEFAULT, "threshold": self.squads[ms][0], "time_lock_s": self.squads[ms][2],
                                         "members": self.squads[ms][1], "member_list": [{"key": f"{ms}{i}", "mask": 7} for i in range(self.squads[ms][1])]}
        R.read_squadsv3 = lambda url, ms, authority_index=None: {"threshold": self.v3[ms][0], "n_keys": self.v3[ms][1], "keys": [], **(
            {f"authority_{authority_index}": PDA([b"squad", key(ms), authority_index.to_bytes(4, "little"), b"authority"], S.SQUADS_V3_PROGRAM)[0]} if authority_index else {})}
        R.read_legacy_serum_multisig = lambda url, ms: dict(self.serum) if ms == S.CHAINLINK_MULTISIG else None
        R.read_pyth_config = lambda url, p: dict(self.pyth_config)
        R.read_governance_v2 = lambda url, g: dict(self.dao) if g == S.PYTH_DAO_GOVERNANCE else None
        R.read_realm = lambda url, r: dict(self.realm) if r == S.PYTH_DAO_REALM else None
        S._usd_prices = lambda mints: {m: self.prices.get(m) for m in mints}
        self._build()

    def tearDown(self):
        for n, fn in self._orig.items():
            setattr(R, n, fn)
        S._usd_prices = self._orig_prices

    def _build(self):
        f = self.f
        admin = bytearray(111)
        admin[:8], admin[8:40], admin[74:78], admin[78:110] = S._disc("VaultAdmin"), key(VAULT0(S.JL_ADMIN_MS)), (1).to_bytes(4, "little"), key(VAULT0(S.JL_ADMIN_MS))
        self.admin = admin
        f.put(PDA([b"vault_admin"], S.JL_VAULTS_PROGRAM)[0], S.JL_VAULTS_PROGRAM, admin)
        vaults = {1: (ORACLES[1], MINT_A, 100, [(FEED, "Chainlink")]),
                  2: (ORACLES[2], S.HUMA_PST_MINT, 10, [(POOL_STATE, "PstPool"), (S.HUMA_PST_MINT, "PstPool")]),
                  3: (ORACLES[3], MINT_B, 10, [(PYTH_ACCOUNT, "Pyth")]),
                  4: (ORACLES[4], MINT_C, 10, [(STAKE_POOL, "StakePool")]),
                  5: (ORACLES[5], MINT_D, 0.5, [(MARINADE_STATE, "MsolPool")]),
                  6: (ORACLES[6], DEX, 5, [(DEX_PEG, "DexSmartColPegOracle")])}
        for vid, (orc, mint, tokens, sources) in vaults.items():
            f.put(f"cfg{vid}", S.JL_VAULTS_PROGRAM, vault_config(vid, orc, mint))
            f.put(f"state{vid}", S.JL_VAULTS_PROGRAM, vault_state(vid, tokens))
            f.put(orc, S.JL_ORACLE_PROGRAM, oracle(*sources))
        feed = bytearray(248)
        writer_state = R.b58(bytes([31]) * 32)
        feed[:8], feed[10:42], feed[74:106] = S._disc("Transmissions"), key(CL_SIGNER), key(PDA([b"store", key(writer_state)], S.CHAINLINK_OCR2_PROGRAM)[0])
        f.put(FEED, S.CHAINLINK_STORE_PROGRAM, feed)
        state = bytearray(200)
        state[:8], state[16:48], state[48:80] = S._disc("State"), key(FEED), key(CL_SIGNER)
        f.put(writer_state, S.CHAINLINK_OCR2_PROGRAM, state)
        f.put(S.CHAINLINK_MULTISIG, S.CHAINLINK_MULTISIG_PROGRAM, b"ms")
        price = bytearray(134)
        price[:8], price[8:40], price[40], price[41:73] = S._disc("PriceUpdateV2"), key(PYTH_ACCOUNT), 1, FEED_ID
        f.put(PYTH_ACCOUNT, S.PYTH_RECEIVER, price)
        f.put(PDA([b"Bridge"], S.PYTH_WORMHOLE)[0], S.PYTH_WORMHOLE, (1).to_bytes(4, "little") + bytes(20))
        sets = [PDA([b"GuardianSet", i.to_bytes(4, "big")], S.PYTH_WORMHOLE)[0] for i in (0, 1)]
        keys = b"".join(bytes.fromhex(k) for k in S.PYTH_GUARDIANS)
        f.put(sets[0], S.PYTH_WORMHOLE, (0).to_bytes(4, "little") + (5).to_bytes(4, "little") + keys + (1).to_bytes(4, "little") + (1000).to_bytes(4, "little"))
        f.put(sets[1], S.PYTH_WORMHOLE, S._disc("GuardianSet") + (1).to_bytes(4, "little") + (5).to_bytes(4, "little") + keys + bytes(8))
        self.sets = sets
        f.put(S.PYTH_GOVERNANCE_MULTISIG, S.PYTH_SQUADS_PROGRAM, b"ms")
        f.put(S.PYTH_DAO_GOVERNANCE, S.PYTH_DAO_PROGRAM, b"gov")
        f.put(STAKE_POOL, SANCTUM, b"\x01" + bytes(610))
        f.put(MARINADE_STATE, "MarBmsSgKXdrN1egZf5sqe1TMai9K1rChYNDJgjq7aD", bytes(10))
        f.put(POOL_STATE, S.HUMA_PROGRAMS[0], bytes(10))
        f.put(S.HUMA_POOL_CONFIG, S.HUMA_PROGRAMS[0], self.pool_config(VAULT0(S.HUMA_LOSS_MS)))
        f.put(HUMA_CONFIG, S.HUMA_PROGRAMS[1], S._disc("HumaConfig") + HUMA_ID + b"\xfe" + key(VAULT0(S.HUMA_MS)) + bytes(67))
        f.put(S.HUMA_PST_MINT, TOKEN, b"\x01\x00\x00\x00" + key(POOL_AUTHORITY) + bytes(46))
        peg = bytearray(287)
        peg[:8], peg[10:42], peg[171:203], peg[236] = S._disc("DexPegOracleConfig"), key(DEX), key(FEED), _types("Chainlink")
        f.put(DEX_PEG, S.JL_ORACLE_PROGRAM, peg)
        f.put(DEX, S.JL_DEX_PROGRAM, bytes(10))

    @staticmethod
    def pool_config(loss):
        """PoolConfig, field by field from the permissionless IDL: disc, bump, huma_config, pool_owner, treasury, mint, pool
        authority bump, pool_id, pool_name, LPConfig (208), InstantWithdrawalConfig (u64, Vec<164-byte fee config>, Option<Pubkey>,
        [u8; 127]), loss_authority, two u64 limits, [u8; 112]."""
        name = b"Huma 2.0 Genesis"
        return (S._disc("PoolConfig") + b"\xff" + key(HUMA_CONFIG) + key(VAULT0(S.HUMA_POOL_OWNER_MS)) + bytes(64) + b"\xff" + bytes(32)
                + len(name).to_bytes(4, "little") + name + bytes(208) + bytes(8) + (2).to_bytes(4, "little") + bytes(328)
                + b"\x01" + bytes(32) + bytes(127) + key(loss) + bytes(16 + 112))

    def score(self):
        notes = []
        return S._jupiter_lend_oracle_authority("u", notes), notes

    def note(self, notes, text):
        return next((n for n in notes if text in n), None)


class TestHeadline(JupiterLendPriceAuthorityTest):
    def test_the_huma_loss_authority_sets_35(self):
        result, notes = self.score()
        self.assertEqual(result, 35)
        self.assertIn("composite 35", self.note(notes, "Huma loss authority"))
        self.assertIn("composite 45", self.note(notes, f"Chainlink feed {FEED}"))
        self.assertIn("composite 41", self.note(notes, "Pyth guardian set 1"))
        self.assertIn("3-of-5", self.note(notes, "Pyth guardian set 1"))
        self.assertIn("composite 54", self.note(notes, f"stake pool {STAKE_POOL}"))
        self.assertIn("composite 49", self.note(notes, "Pyth DAO"))  # Strict tipping: a vote can end early, so no window
        self.assertIn("governance-grade", self.note(notes, "Huma pool owner"))
        self.assertIn("governance-grade", self.note(notes, "Huma owner"))
        self.assertIn("(immaterial)", self.note(notes, "MsolPool source"))
        self.assertIn("own,", self.note(notes, "Jupiter Lend own programs"))

    def test_the_composites_follow_the_solana_formula(self):
        q = lambda t, n: S._composite(*S._score_full_power_path("squads_v3", threshold=t, voters=n))  # noqa: E731
        self.assertEqual((q(4, 9), q(3, 5), q(6, 9), q(6, 11)), (45, 41, 54, 54))
        self.assertEqual(S._composite(*S._score_full_power_path("squads_v4", threshold=2, voters=3, delay_s=0)), 35)
        self.assertEqual(S._composite(*S._score_full_power_path("realms_governance", holdup_s=0)), 49)

    def test_a_delayed_loss_authority_leaves_the_pyth_quorum(self):
        self.squads[S.HUMA_LOSS_MS] = (2, 3, GOVERNANCE_DELAY)
        result, notes = self.score()
        self.assertEqual(result, 41)
        self.assertIn("governance-grade", self.note(notes, "Huma loss authority"))

    def test_a_dao_that_cannot_tip_early_is_governance_grade(self):
        self.dao["community_vote_tipping"] = 2
        _, notes = self.score()
        self.assertIn("window 604800s >= the target's 21600s", self.note(notes, "Pyth DAO"))


class TestGuards(JupiterLendPriceAuthorityTest):
    """Each fact a spec pins: any other answer makes that material path UNREAD, so the field falls to 20 (35 is the only
    lower scored path, and it is the one broken in the Huma cases)."""

    def _flip(self, pk, offset, value):
        owner, data, lamports = self.f.accounts[pk]
        d = bytearray(data)
        d[offset:offset + len(value)] = value
        self.f.accounts[pk] = (owner, bytes(d), lamports)

    def test_every_broken_fact_is_unread(self):
        other = key("11111111111111111111111111111112")
        cases = {
            "feed owner": lambda: self._flip(FEED, 10, other),
            "feed pending owner": lambda: self._flip(FEED, 42, other),
            "feed writer": lambda: self._flip(FEED, 74, other),
            "OCR2 config owner": lambda: self._flip(R.b58(bytes([31]) * 32), 48, other),
            "serum nonce": lambda: self.serum.update(nonce=CL_BUMP - 1),
            "Store upgrade": lambda: self.programs[S.CHAINLINK_STORE_PROGRAM].update(upgrade_authority="x"),
            "multisig program upgrade": lambda: self.programs[S.CHAINLINK_MULTISIG_PROGRAM].update(upgrade_authority="x"),
            "Pyth partial update": lambda: self._flip(PYTH_ACCOUNT, 40, b"\x00"),
            "Pyth other writer": lambda: self._flip(PYTH_ACCOUNT, 8, other),
            "Pyth governance authority": lambda: self.pyth_config.update(governance_authority="x"),
            "Pyth data source": lambda: self.pyth_config.update(valid_data_sources=[]),
            "wormhole redeployed": lambda: self.programs[S.PYTH_WORMHOLE].update(last_deploy_slot=1),
            "guardian key": lambda: self._flip(self.sets[1], 16, b"\x00"),
            "guardian set 0 live": lambda: self._flip(self.sets[0], 8 + 100 + 4, bytes(4)),
            "squads fork upgrade": lambda: self.programs[S.PYTH_SQUADS_PROGRAM].update(upgrade_authority="x"),
            "realm authority": lambda: self.realm.update(authority="x"),
            "DAO council": lambda: self.dao.update(council_vote_threshold={"kind": "YesVotePercentage", "pct": 60}),
            "Huma loss authority": lambda: self.f.put(S.HUMA_POOL_CONFIG, S.HUMA_PROGRAMS[0], self.pool_config("11111111111111111111111111111112")),
            "PST mint authority": lambda: self._flip(S.HUMA_PST_MINT, 4, other),
            "HumaConfig owner program": lambda: self.f.put(HUMA_CONFIG, "x", self.f.accounts[HUMA_CONFIG][1]),
            "stake pool type": lambda: self._flip(STAKE_POOL, 0, b"\x02"),
            "Sanctum upgrade": lambda: self.programs[SANCTUM].update(upgrade_authority="x"),
            "own DEX program upgrade": lambda: self.programs[S.JL_DEX_PROGRAM].update(upgrade_authority="x"),
            "DEX not own": lambda: self.f.put(DEX, "x", bytes(10)),
            "VaultAdmin extra auth": lambda: self.f.put(PDA([b"vault_admin"], S.JL_VAULTS_PROGRAM)[0], S.JL_VAULTS_PROGRAM,
                                                         bytes(self.admin[:74]) + (2).to_bytes(4, "little") + bytes(self.admin[78:110]) + other + b"\xff"),
            "vault oracle program": lambda: self._flip("cfg1", 122, other),
            "oracle not Jupiter's": lambda: self.f.put(ORACLES[3], "x", self.f.accounts[ORACLES[3]][1]),
        }
        for name, mutate in cases.items():
            with self.subTest(name):
                self._reset()
                mutate()
                result, notes = self.score()
                self.assertEqual(result, 20, notes[-1])
                self.assertIn(S.PRICE_UNREAD_MARK, notes[-1])


class TestMateriality(JupiterLendPriceAuthorityTest):
    def test_a_source_without_spec_counts_from_one_percent(self):
        self.assertEqual(self.score()[0], 35)  # Marinade at 0.5 / 130.5 = 0.38%
        self.f.put("state5", S.JL_VAULTS_PROGRAM, vault_state(5, 2))  # 2 / 132 = 1.5%
        result, notes = self.score()
        self.assertEqual(result, 20)
        self.assertIn("MsolPool source", notes[-1])

    def test_an_unpriced_row_is_material(self):
        del self.prices[MINT_D]
        self.assertEqual(self.score()[0], 20)

    def test_an_empty_vault_weighs_nothing(self):
        del self.prices[MINT_D]
        self.f.put("state5", S.JL_VAULTS_PROGRAM, vault_state(5, 0))
        self.assertEqual(self.score()[0], 35)

    def test_a_single_validator_pool_is_valued_on_chain(self):
        self.f.put("cfg7", S.JL_VAULTS_PROGRAM, vault_config(7, ORACLES[7], SINGLE_MINT))
        self.f.put("state7", S.JL_VAULTS_PROGRAM, vault_state(7, 1))
        self.f.put(ORACLES[7], S.JL_ORACLE_PROGRAM, oracle((STAKE_ACCOUNT, "SinglePool"), (SINGLE_MINT, "SinglePool"), (S.STAKE_PROGRAM, "SinglePool")))
        self.f.put(STAKE_ACCOUNT, S.STAKE_PROGRAM, bytes(200), lamports=2 * 10**8)  # 0.2 SOL backing
        self.f.put(SINGLE_MINT, TOKEN, b"\x01\x00\x00\x00" + bytes(32) + (10**9).to_bytes(8, "little") + bytes(38))  # supply 1 token
        self.f.put(S.STAKE_PROGRAM, "BPFLoaderUpgradeab1e11111111111111111111111", bytes(36))
        result, notes = self.score()
        self.assertEqual(result, 35)  # 1 token x 0.2 SOL x $1 = $0.2: immaterial although the pool has no spec
        self.assertIn("(immaterial)", self.note(notes, f"SinglePool source {STAKE_ACCOUNT}"))
        self.assertIn("constant", self.note(notes, "native Stake program"))
        del self.f.accounts[STAKE_ACCOUNT]  # its backing cannot be read: unknown value, material
        self.assertEqual(self.score()[0], 20)


class TestFailures(JupiterLendPriceAuthorityTest):
    def test_a_failed_read_is_20(self):
        self.f.fail = True
        result, notes = self.score()
        self.assertEqual(result, 20)
        self.assertIn("price walk failed", notes[-1])

    def test_a_failed_price_api_is_20(self):
        def down(mints):
            raise ValueError("no JSON")
        S._usd_prices = down
        self.assertEqual(self.score()[0], 20)

    def test_a_failed_spec_read_is_unread_and_keeps_a_lower_scored_path(self):
        def rate_limited(url, p):
            raise R.SolRpcError("429")
        R.read_pyth_config = rate_limited
        result, notes = self.score()
        self.assertEqual(result, 20)
        self.assertIn("read failed (SolRpcError: 429)", self.note(notes, f"price path pyth:{PYTH_ACCOUNT}"))
        self.squads[S.HUMA_LOSS_MS] = (1, 3, 0)  # a 1-of-3 is a single key: (5, 0, 0) = 2, below the cap
        self.assertEqual(self.score()[0], 2)


if __name__ == "__main__":
    unittest.main()
