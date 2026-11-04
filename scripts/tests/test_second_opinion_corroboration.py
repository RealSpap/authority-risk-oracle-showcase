"""Tests of the corroboration added to the second reader (29/10/2026). Fake RPC, no network.
Run:  python3 -B test_second_opinion_corroboration.py [path/to/second_opinion.py]   (default: ./second_opinion.py)
For each of the ten cases: a test that corroborates (fails on the ORIGINAL reader, which has no corroborate_all) and a WITNESS built from the
same case that must STAY a disagreement. Then mutants of the new code: each must make at least one test fail."""
import importlib.util, os, re, sys, time, types, unittest

HERE = os.path.dirname(os.path.abspath(__file__))


def load(path, name="so_under_test", text=None):
    src = text if text is not None else open(path, encoding="utf-8").read()
    mod = types.ModuleType(name); mod.__file__ = path; exec(compile(src, path, "exec"), mod.__dict__); return mod


def w(x): return "%064x" % x
def aw(a): return "0x" + "0" * 24 + a[2:].lower()


class Chain:
    """A fake EVM chain: rpc_batch answers getCode / eth_call from tables; an unknown call REVERTS (""), unknown code is unread (None)."""
    def __init__(s, so): s.so = so; s.code = {}; s.calls = {}
    def eoa(s, a): s.code[a.lower()] = "0x"
    def contract(s, a): s.code.setdefault(a.lower(), "0x6080604052")
    def call(s, to, data, res): s.calls[(to.lower(), data.lower())] = res
    def safe(s, a, k, n, modules=0):
        s.contract(a); s.call(a, s.so.SEL["getThreshold"], "0x" + w(k)); s.call(a, s.so.SEL["getOwners"], "0x" + w(32) + w(n) + "".join(w(i + 1) for i in range(n)))
        s.call(a, s.so.MODULES_PAGE, "0x" + w(64) + w(1) + w(modules) + "".join(w(7) for _ in range(modules)))
    def timelock(s, a, delay): s.contract(a); s.call(a, s.so.SEL["getMinDelay"], "0x" + w(delay))
    def rpc(s, url, calls):
        out = []
        for m, p in calls:
            if m == "eth_getCode": out.append(s.code.get(p[0].lower()))
            elif m == "eth_call":
                d = p[0]["data"]; assert d.startswith("0x") and len(d) % 2 == 0, "malformed calldata (an RPC would refuse it): " + d[:20]
                out.append(s.calls.get((p[0]["to"].lower(), p[0]["data"].lower()), ""))
            elif m == "eth_blockNumber": out.append("0x1")
            else: out.append("")
        return out


def rec(chain, target, holder, disagree, **kw):
    return dict({"chain": chain, "target": target, "holder": holder, "disagree": disagree, "block_start": 10, "block_end": 12}, **kw)


# the disagreement texts exactly as the reader writes them (second_opinion.py:431-480)
T_KEY = "the score says one key does everything (%d), the live read finds a timelock (1209600s) via EIP-1967 admin -> ProxyAdmin owner()"
T_DELAY = "the timelock score says no delay (0), the live read finds a timelock of 336 h in the admin path via EIP-1967 admin -> ProxyAdmin owner()"
T_MS = "the multisig score says no real multisig (0), the live read finds a Safe 3-of-7 via EIP-1967 admin -> ProxyAdmin owner()"
T_GENEROUS = "the score says admin power is not a bare key (65), the live read finds a bare EOA 0x1234…abcd via owner()"


def run_case(so, r, chain):
    so.rpc_batch = chain.rpc; dis = [r]; out = so.corroborate_all([r], dis); return out, dis


# ---------------------------------------------------------------- EVM
GT = "0xff162c694eaa571f685030649814282ea457f169"; GT_TL = "0x893FCf48D56CE2e92AFB4a085941135243D5E75a"
GT_S4, GT_S2, GT_EOA = "0xc07EEd650aB255190CA9766162CfB47cFDf72f3a", "0xe8997C502fCD0729B462FCA19A50cF0DAEA0cAB5", "0x80fd0accC8Da81b0852d2Dca17b5DDab68f22253"
RAD = "0xe23b4ae3624fb6f7cdef29bc8ead912f1ede6886"; RAD_PROV = "0x454a8dAf74B24037eE2fa073Ce1be9277Ed6160a"; RAD_SAFE = "0x1111111111111111111111111111111111111111"
STH = "0xffaa4a3d97fe9107cef8a3f48c069f577ff76cc1"; STH_SAFE = "0x97dee0ea4ca10560f260a0f6f45bdc128a1d51f9"; STH_TL = "0xc5ded4f7f53919c714059a17d31371ae847e23d2"
YZ = "0x6695c0f8706c5ace3bdf8995073179cca47926dc"; YZPP = "0xebfc8c2fe73c431ef2a371aea9132110aab50dca"; S1 = "0xe61ad2de346db42879b6ee3c7cf0c6a2cdc0530d"; YZ_T2 = "0x2130457539612ae9838e0314cda1a8abbdb7cfbc"
ARC = "0x14b107cf534239c59571b066cb6497a321da897c"; ARC_TL = "0x0da180b14721ce46a83669b4816cb652caa1001d"; ARC_VC = "0x9d032106" + "0" * 24 + "b4e55da8"; ARC_CP = "0xa3d46d24" + "0" * 24 + "123df487"
ORV = "0x5c98b2d892b37c9a1d3b69472bddc172a64cdc09"; ORV_SAFE = "0x9db4" + "0" * 32 + "1a53"; ORV_EOA = "0x2222222222222222222222222222222222222222"
RD = "0x393d0b87ed38fc779fd9611144ae649ba6082109"; RD_OP = "0x23a4604cdfe8e9e2e9cf7c10d7492b0f3f4b4038"; RD_SAFE = "0x18a82c968b992d28d4d812920eb7b4305306f8f1"
DW = "0xa9c251f8304b1b3fc2b9e8fcae78d94eff82ac66"; DW_SAFE = "0x7d07" + "0" * 32 + "dcd8"


def gtrade(so, eoa_proposes=True, probe=True):
    c = Chain(so); c.timelock(GT_TL, 36000); c.safe(GT_S4, 4, 7); c.safe(GT_S2, 2, 4); c.eoa(GT_EOA)
    if probe: c.call(GT, so._hex_args(so.S_HAS_ROLE_U8, "0" * 24 + GT_TL[2:].lower(), w(3)), "0x" + w(1))
    for a in (GT_S4, GT_S2) + ((GT_EOA,) if eoa_proposes else ()): c.call(GT_TL, so._hex_args(so.S_HAS_ROLE, so.H_ROLE["PROPOSER_ROLE"], "0" * 24 + a[2:].lower()), "0x" + w(1))
    return c, rec("arbitrum", GT, "0x5f5e4892bab94d94dc57a3edea3c138167c4df0f", T_KEY % 10 + "; " + T_DELAY)


def radiant(so, module=0, provider_named=True):
    c = Chain(so); c.safe(RAD_SAFE, 4, 11, modules=module); c.timelock("0x454a000000000000000000000000000000000072", 259200)
    if provider_named: c.call(RAD, so.S_PROVIDER, aw(RAD_PROV))
    c.call(RAD_PROV, so.S_POOL_ADMIN, aw(RAD_SAFE))
    return c, rec("arbitrum", RAD, "0x454a8daf74b24037ee2fa073ce1be9277ed6160a", "the timelock score says no delay (0), the holder's owner is a timelock of 72 h")


def sthype(so, admin_is_safe=True):
    c = Chain(so)
    if admin_is_safe: c.safe(STH_SAFE, 4, 6); c.call(STH, so.S_DEFAULT_ADMIN, aw(STH_SAFE))
    else: c.timelock(STH_TL, 172800); c.call(STH, so.S_DEFAULT_ADMIN, aw(STH_TL))
    return c, rec("hyperliquid", STH, STH_TL, "the timelock score says no delay (0), the live read finds a timelock of 48 h in the admin path via EIP-1967 admin -> ProxyAdmin owner()")


def yuzu(so, holds=True, module=0):
    c = Chain(so); c.safe(S1, 3, 5, modules=module)
    if holds: c.call(YZPP, so._hex_args(so.S_HAS_ROLE, so.H_ROLE["POOL_MANAGER_ROLE"], "0" * 24 + S1[2:]), "0x" + w(1))
    return c, rec("plasma", YZ, YZ_T2, "the timelock score says no delay (0), the live read finds a timelock of 48 h in the admin path via EIP-1967 admin -> ProxyAdmin owner()")


def arcus(so, others_timelocked=False):
    c = Chain(so); c.timelock(ARC_TL, 86400)
    if others_timelocked: c.timelock(ARC_VC, 86400); c.timelock(ARC_CP, 604800)
    else: c.contract(ARC_VC); c.contract(ARC_CP)
    c.call(ARC, so.S_ROLE_COUNT + so.H_ROLE["DEFAULT_ADMIN_ROLE"][2:], "0x" + w(3))
    for i, a in enumerate((ARC_TL, ARC_VC, ARC_CP)): c.call(ARC, so.S_ROLE_MEMBER + so.H_ROLE["DEFAULT_ADMIN_ROLE"][2:] + w(i), aw(a))
    return c, rec("robinhood", ARC, ARC_TL, "the timelock score says no delay (0), the live read finds a timelock of 24 h in the admin path via DEFAULT_ADMIN_ROLE member 1 of 3 (AccessControl)")


def orvex(so, owner_is_eoa=True):
    c = Chain(so); c.safe(ORV_SAFE, 3, 7)
    if owner_is_eoa: c.eoa(ORV_EOA); c.call(ORV, so.SEL["owner"], aw(ORV_EOA))
    else: c.safe(ORV_EOA, 3, 5); c.call(ORV, so.SEL["owner"], aw(ORV_EOA))
    return c, rec("robinhood", ORV, ORV_SAFE, "the score says one key does everything (5), the live read finds a Safe 3-of-7 via EIP-1967 admin -> ProxyAdmin owner(); the multisig score says no real multisig (0), the live read finds a Safe 3-of-7 via EIP-1967 admin -> ProxyAdmin owner()")


def role_display_case(so):
    c = Chain(so); c.eoa(RD_OP)
    c.call(RD, so.S_ROLE_COUNT + so.H_ROLE["OPERATOR_ROLE"][2:], "0x" + w(1)); c.call(RD, so.S_ROLE_MEMBER + so.H_ROLE["OPERATOR_ROLE"][2:] + w(0), aw(RD_OP))
    return c, rec("hyperliquid", RD, RD_SAFE, "the score says one key does everything (10), the live read finds a Safe 4-of-8 via EIP-1967 admin -> ProxyAdmin owner(); the multisig score says no real multisig (0), the live read finds a Safe 4-of-8 via EIP-1967 admin -> ProxyAdmin owner()")


def delay_weight_case(so):
    c = Chain(so); c.safe(DW_SAFE, 2, 5); c.call(DW, so.SEL["owner"], aw(DW_SAFE))
    return c, rec("plasma", DW, DW_SAFE, "the timelock score says no delay (0), the contract enforces its own timelock of 24 h (timelock())")


class EVM(unittest.TestCase):
    so = None
    def test_01_gtrade_corroborated(self):
        c, r = gtrade(self.so); out, dis = run_case(self.so, r, c); self.assertEqual(len(out), 1); self.assertEqual(dis, []); self.assertEqual({a["axis"] for a in out[0]["corroborated"]["axes"]}, {"key_low", "delay_zero"})
    def test_01w_gtrade_witness_no_bare_key(self):   # only Safes propose: no bare key, the "one key" part stays
        c, r = gtrade(self.so, eoa_proposes=False); out, dis = run_case(self.so, r, c); self.assertEqual(out, []); self.assertEqual(dis, [r])
    def test_01x_gtrade_witness_timelock_not_shown_on_target(self):   # an unverified hint corroborates nothing
        c, r = gtrade(self.so, probe=False); out, dis = run_case(self.so, r, c); self.assertEqual(out, [])
    def test_01y_gtrade_witness_unanswered_probes_are_not_a_zero(self):   # a rate-limited probe (None) is not "the timelock holds nothing" and not a corroboration
        c, r = gtrade(self.so); orig = c.rpc
        def rpc(url, calls): return [None if (m == "eth_call" and p[0]["data"].startswith(self.so.S_HAS_ROLE_U8)) else x for (m, p), x in zip(calls, orig(url, calls))]
        self.so.rpc_batch = rpc; dis = [r]; out = self.so.corroborate_all([r], dis); self.assertEqual(out, []); self.assertEqual(dis, [r])
    def test_02_radiant(self):
        c, r = radiant(self.so); out, dis = run_case(self.so, r, c); self.assertEqual(len(out), 1); self.assertEqual(dis, [])
    def test_02w_radiant_witness_module(self):       # a module may carry a delay: fail closed
        c, r = radiant(self.so, module=1); out, dis = run_case(self.so, r, c); self.assertEqual(out, [])
    def test_02x_radiant_witness_provider_not_named_by_target(self):
        c, r = radiant(self.so, provider_named=False); out, dis = run_case(self.so, r, c); self.assertEqual(out, [])
    def test_05_sthype(self):
        c, r = sthype(self.so); out, dis = run_case(self.so, r, c); self.assertEqual(len(out), 1)
    def test_05w_sthype_witness_admin_is_a_timelock(self):
        c, r = sthype(self.so, admin_is_safe=False); out, dis = run_case(self.so, r, c); self.assertEqual(out, [])
    def test_07_yuzu(self):
        c, r = yuzu(self.so); out, dis = run_case(self.so, r, c); self.assertEqual(len(out), 1)
    def test_07w_yuzu_false_hint_corroborates_nothing(self):   # hasRole is false: the hinted Safe holds nothing there
        c, r = yuzu(self.so, holds=False); out, dis = run_case(self.so, r, c); self.assertEqual(out, []); self.assertEqual(dis, [r])
    def test_08_arcus(self):
        c, r = arcus(self.so); out, dis = run_case(self.so, r, c); self.assertEqual(len(out), 1)
    def test_08w_arcus_witness_all_members_timelocked(self):
        c, r = arcus(self.so, others_timelocked=True); out, dis = run_case(self.so, r, c); self.assertEqual(out, [])
    def test_09_orvex(self):
        c, r = orvex(self.so); out, dis = run_case(self.so, r, c); self.assertEqual(len(out), 1); self.assertEqual({a["axis"] for a in out[0]["corroborated"]["axes"]}, {"key_low", "multisig_low"})
    def test_09w_orvex_witness_owner_is_a_safe(self):
        c, r = orvex(self.so, owner_is_eoa=False); out, dis = run_case(self.so, r, c); self.assertEqual(out, [])
    def test_03_04_role_holders_shown_never_corroborated(self):
        c, r = role_display_case(self.so); out, dis = run_case(self.so, r, c); self.assertEqual(out, []); self.assertEqual(dis, [r])
        self.assertTrue(any(p["kind"] == "eoa" and p.get("display_only") for p in r["other_paths"]))   # the bare key IS shown
    def test_06_delay_weight_disagreement_stays(self):
        c, r = delay_weight_case(self.so); out, dis = run_case(self.so, r, c); self.assertEqual(out, []); self.assertEqual(dis, [r])
    def test_generous_side_is_never_answered(self):   # a weaker path never answers "the score says it is NOT a bare key", even beside a part it does answer
        c, r = orvex(self.so); r["disagree"] = T_GENEROUS; out, dis = run_case(self.so, r, c); self.assertEqual(out, [])
        c, r = orvex(self.so); r["disagree"] = "the score says one key does everything (5), the live read finds a Safe 3-of-7; " + T_GENEROUS; out, dis = run_case(self.so, r, c); self.assertEqual((out, dis), ([], [r]))
    def test_08x_arcus_witness_a_contract_that_answers_a_delay_getter(self):   # a contract holder with its own timelock() is not "no delay getter"
        c, r = arcus(self.so)
        for a in (ARC_VC, ARC_CP): c.call(a, self.so.SEL["timelock"], "0x" + w(86400))
        out, dis = run_case(self.so, r, c); self.assertEqual(out, [])
    def test_recomputed_every_run(self):              # the same record, the path gone: the disagreement comes back at once (not an acknowledgement)
        c, r = orvex(self.so); out, dis = run_case(self.so, r, c); self.assertEqual(len(out), 1)
        c2, r2 = orvex(self.so, owner_is_eoa=False); out2, dis2 = run_case(self.so, r2, c2); self.assertEqual((out2, dis2), ([], [r2]))
    def test_other_rows_are_never_touched(self):       # "no other line moves": only the records of `dis` are read or changed
        import copy
        c, r = orvex(self.so); other = {"chain": "arbitrum", "target": "0xaaa", "kind": "safe", "holder": "0x1", "agree": True}; keep = copy.deepcopy(other)
        self.so.rpc_batch = c.rpc; dis = [r]; self.so.corroborate_all([other, r], dis); self.assertEqual(other, keep); self.assertEqual(dis, [])
    def test_unread_path_is_not_a_corroboration(self):
        c, r = orvex(self.so); c.code.pop(ORV_EOA.lower()); out, dis = run_case(self.so, r, c); self.assertEqual(out, [])


# ---------------------------------------------------------------- Solana
def v4_data(so, ms_vault_authority, n=7): return {"exists": True, "data": b"\0" * 5000}


class Sol(unittest.TestCase):
    so = None
    def setUp(self):
        so = self.so; self.ms = "HvYoRSJdVcj6WRWV57yLu2Vmwh1ccqJRdkCwhNsSfRu4"; self.v = so._v4_vault(self.ms, 0)
    def _acct(self, offset, value, size=3000):
        d = bytearray(size); d[offset:offset + 32] = self.so.b58decode(value); return {"exists": True, "owner": "x", "data": bytes(d)}
    def _run(self, r, accts, squads=None, solana_read=None):
        so = self.so; so.sol_account = lambda pk, url=None: accts.get(pk); so.squads_multisig = lambda pk, url=None: (squads or {}).get(pk)
        if solana_read: so.solana_read = solana_read
        dis = [r]; out = so.corroborate_all([r], dis); return out, dis
    def test_10_kamino(self):
        t = "GKnHiWh3RRrE1zsNzWxRkomymHc374TvJPSTv2wPeYdB"; r = rec("solana", t, "x", "the timelock score says no delay (0), the Squads multisig enforces a native time lock of 24 h")
        out, dis = self._run(r, {t: self._acct(2224, self.v)}, {self.ms: {"threshold": 5, "owners": 7, "voters": 7, "delay_seconds": 0}}); self.assertEqual(len(out), 1); self.assertEqual(dis, [])
    def test_10w_kamino_witness_delay(self):
        t = "GKnHiWh3RRrE1zsNzWxRkomymHc374TvJPSTv2wPeYdB"; r = rec("solana", t, "x", "the timelock score says no delay (0), the Squads multisig enforces a native time lock of 24 h")
        out, dis = self._run(r, {t: self._acct(2224, self.v)}, {self.ms: {"threshold": 5, "owners": 7, "voters": 7, "delay_seconds": 86400}}); self.assertEqual(out, [])
    def test_10x_kamino_witness_field_is_not_the_hinted_vault(self):   # a false hint: the field holds another authority
        t = "GKnHiWh3RRrE1zsNzWxRkomymHc374TvJPSTv2wPeYdB"; r = rec("solana", t, "x", "the timelock score says no delay (0), the Squads multisig enforces a native time lock of 24 h")
        other = self.so._v4_vault("5JZFPx6Qkg9PAgYMn9wHWirsiEQBfeJuE667MWeRBLPN", 0)
        out, dis = self._run(r, {t: self._acct(2224, other)}, {self.ms: {"threshold": 5, "owners": 7, "voters": 7, "delay_seconds": 0}}); self.assertEqual(out, [])
    def test_11_jupiter_perps(self):
        so = self.so; t = "H4ND9aYttUVLFmNypZqLjZ52FYiGvdEB45GmwNoKEjTj"; ms = "7ZyDFzet6sKgZLN4D89JLfo7chu2n7nYdkFt5RCFk8Sf"; auth = so._v3_authority(ms, 1)
        d = bytearray(120); d[51:83] = so.b58decode(auth); msd = bytearray(400); msd[8:10] = (4).to_bytes(2, "little"); msd[54:58] = (7).to_bytes(4, "little")
        accts = {t: {"exists": True, "owner": "p", "data": bytes(d)}, ms: {"exists": True, "owner": so.SQDS_V3, "data": bytes(msd)}}
        r = rec("solana", t, "x", "the timelock score says no delay (0), the Squads multisig enforces a native time lock of 24 h"); out, dis = self._run(r, accts); self.assertEqual(len(out), 1); self.assertNotIn("disagree", out[0]); self.assertIn("native time lock", out[0]["corroborated"]["disagreement"])   # the finding moved INTO the corroboration: consumers of `disagree` see none
        accts[ms]["owner"] = "SomeOtherProgram1111111111111111111111111111"; r2 = rec("solana", t, "x", out[0]["corroborated"]["disagreement"]); out2, dis2 = self._run(r2, accts); self.assertEqual(out2, [])   # witness: not a Squads v3 account
    def test_12_orca(self):
        so = self.so; t = "2LecshUwdy9xi7meFgHtFJQNSKk4KdTrcpvaB56dP2NQ"; ms = "5JZFPx6Qkg9PAgYMn9wHWirsiEQBfeJuE667MWeRBLPN"; v = so._v4_vault(ms, 0)
        txt = "the score says one key does everything (5), the upgrade authority is a Squads v4; the multisig score says no real multisig (0), the Squads multisig is a 5-of-13; the timelock score says no delay (0), the Squads multisig enforces a native time lock of 24 h"
        r = rec("solana", t, "x", txt); out, dis = self._run(r, {t: self._acct(72, v)}, {ms: {"threshold": 1, "owners": 8, "voters": 8, "delay_seconds": 0}}); self.assertEqual(len(out), 1)
        self.assertEqual({a["axis"] for a in out[0]["corroborated"]["axes"]}, {"key_low", "multisig_low", "delay_zero"}); self.assertTrue(out[0]["corroborated"]["paths"][0]["note"])   # the judgment call is said in the field
        r2 = rec("solana", t, "x", txt); out2, dis2 = self._run(r2, {t: self._acct(72, v)}, {ms: {"threshold": 5, "owners": 8, "voters": 8, "delay_seconds": 86400}}); self.assertEqual(out2, [])   # witness: a real 5-of-8 with a day
    def test_13_solstice(self):
        so = self.so; t = "USXyiSTsPEWz55pSK7sZoUL79ntoVGQbaTDT57tH6bx"; ms_aux = "BPdkMGWnttz4izo6RD6pXpcbVgGiqD2GR3Jds7HvaXEE"; ms_y = "AEb1u8FK8EuXLcPtprCy8s4NkqBNoP5mfbuEEop2dJGf"
        vaults = {"7FaMyGiTVdjm8dd3PxpjjCX15ibbmuE1zWVFX2PHxYUK": so._v4_vault(ms_aux, 0), "eUSXyKoZ6aGejYVbnp3wtWQ1E8zuokLAJPecPxxtgG3": so._v4_vault(ms_y, 1)}
        sr = lambda program, url=None: ("pda", vaults[program], "program -> ProgramData -> authority", {})
        r = rec("solana", t, "x", "the timelock score says no delay (0), the Squads multisig enforces a native time lock of 24 h")
        out, dis = self._run(r, {}, {ms_aux: {"threshold": 2, "owners": 3, "voters": 3, "delay_seconds": 0}, ms_y: {"threshold": 3, "owners": 7, "voters": 7, "delay_seconds": 86400}}, solana_read=sr); self.assertEqual(len(out), 1)
        r2 = rec("solana", t, "x", out[0]["corroborated"]["disagreement"]); out2, dis2 = self._run(r2, {}, {ms_aux: {"threshold": 2, "owners": 3, "voters": 3, "delay_seconds": 86400}, ms_y: {"threshold": 3, "owners": 7, "voters": 7, "delay_seconds": 86400}}, solana_read=sr); self.assertEqual(out2, [])


class Ack(unittest.TestCase):
    so = None
    def test_acknowledgement_expires_after_30_days(self):
        so = self.so; now = __import__("calendar").timegm(time.strptime("2026-11-20", "%Y-%m-%d"))
        self.assertTrue(so.ack_fresh("2026-10-29 note", now)); self.assertTrue(so.ack_fresh("2026-10-21 note", now))   # 30 days or fewer
        self.assertFalse(so.ack_fresh("2026-10-20 note", now)); self.assertFalse(so.ack_fresh("a note without a date", now)); self.assertFalse(so.ack_fresh("2026-13-40 bad", now))
        self.assertFalse(so.ack_fresh("2027-01-01 a date in the future", now))


class Independence(unittest.TestCase):
    so_path = None
    def test_no_scorer_is_imported_or_named(self):
        src = open(self.so_path, encoding="utf-8").read()
        self.assertEqual(re.findall(r"^\s*(?:import|from)\s+\S*(?:scorer|methodology_test|scoring_build|sol_read)\S*", src, re.M), [])
        self.assertNotIn("sol_read", "".join(l for l in src.splitlines() if not l.lstrip().startswith("#")))
        self.assertNotIn("__import__(", src.split("def corroborate_all")[0].split("# CORROBORATION")[1])   # no dynamic import in the new section


# ---------------------------------------------------------------- mutants
MUTANTS = {
    "M1 the reader ignores the new paths (evaluate never answers)": ("def evaluate(rec, paths):\n", "def evaluate(rec, paths):\n    return None\n"),
    "M2 a false hint corroborates (hasRole not checked)": ('if hv[0] and len(hv[0]) == 66 and int(hv[0], 16) == 1: add(', 'if True: add('),
    "M3 any path answers the delay axis": ("def _no_delay(p):  # no delay the reader can see on this path\n", "def _no_delay(p):  # no delay the reader can see on this path\n    return True\n"),
    "M4 the generous side is corroborated too": ("        else: return None\n        if not ok: return None", "        else: continue\n        if not ok: return None"),
    "M5 Solana: the derived vault is not compared with the field": ("    if _v4_vault(ms, idx) != authority: return None\n", ""),
    "M6 display-only paths count": ("verdict = evaluate(rec, [p for p in paths if not p.get(\"display_only\")])", "verdict = evaluate(rec, paths)"),
    "M7 the path the disagreement is about is not excluded": ("    own = [rec.get(\"holder\"), (rec.get(\"behind\") or {}).get(\"address\")]\n", "    own = []\n"),
    "M8 the Safe's modules are ignored": ('if k == "safe": return p.get("modules") == []', 'if k == "safe": return True'),
    "M11 calldata built without its 0x prefix (what the first real read did)": ('def _hex_args(*words): return "0x" + "".join(', 'def _hex_args(*words): return "".join('),
    "M10 an old acknowledgement still silences": ("0 <= ((now if now is not None else time.time()) - d) <= days * 86400", "True"),
    "M12 the corroborated record keeps its `disagree` text (consumers see a disagreement)": ('rec["corroborated"]["disagreement"] = rec.pop("disagree", None)', 'rec["corroborated"]["disagreement"] = rec.get("disagree")'),
    "M9 a revert on every delay getter is not required": ('p["no_delay_getter"] = not answered and all(x in ("", "0x") for x in (d1, d2, d3))', 'p["no_delay_getter"] = True'),
}


def suite(so, so_path):
    EVM.so = so; Sol.so = so; Ack.so = so; Independence.so_path = so_path
    s = unittest.TestSuite()
    for c in (EVM, Sol, Ack, Independence): s.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(c))
    return s


def _default_path():
    for p in (os.path.join(HERE, "second_opinion.py"), os.path.join(HERE, "..", "second_opinion.py")):
        if os.path.exists(p): return os.path.abspath(p)


def setUpModule():   # `python3 -m unittest discover -s scripts/tests` (the CI): the reader under test is scripts/second_opinion.py
    if EVM.so is not None: return   # run as a script: the (possibly mutated) reader under test is already set
    p = _default_path(); so = load(p); EVM.so = so; Sol.so = so; Ack.so = so; Independence.so_path = p


if __name__ == "__main__":
    path = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "second_opinion.py"))
    base = open(path, encoding="utf-8").read()
    res = unittest.TextTestRunner(verbosity=1).run(suite(load(path), path))
    survivors = []
    if len(sys.argv) <= 2 or sys.argv[2] != "--no-mutants":
        for name, (a, b) in MUTANTS.items():
            assert base.count(a) == 1, ("mutant pattern not unique", name, base.count(a))
            mod = load(path, "mutant", base.replace(a, b)); r = unittest.TextTestRunner(stream=open(os.devnull, "w")).run(suite(mod, path))
            print("%-70s %s" % (name, "KILLED (%d failing)" % (len(r.failures) + len(r.errors)) if (r.failures or r.errors) else "SURVIVED"))
            if not (r.failures or r.errors): survivors.append(name)
    print("tests: %d run, %d failures, %d errors; mutant survivors: %d" % (res.testsRun, len(res.failures), len(res.errors), len(survivors)))
    sys.exit(0 if res.wasSuccessful() and not survivors else 1)
