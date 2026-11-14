#!/usr/bin/env python3
"""R-1 : niveau 0-5 (cadre de listing d'Aave) de chaque role lu en chaine sur les collateraux Aave V3 Core, a un BLOC DATE.
Lecture seule, bibliotheque standard seulement. Ne touche et n'importe AUCUN scoreur de l'oracle.

  python3 -I mesure_aave_niveaux.py --block 26297651 --hashes HASHES-AVANT.txt --out sortie/aave-niveaux-26297651
  python3 -I mesure_aave_niveaux.py --block 26297651 --hashes HASHES-AVANT.txt --cassette-in sortie/cassette-26297651.json.gz --out /tmp/x   (rejeu SANS reseau)

La grille (GRILLE.md, a cote) est HACHEE au demarrage, pas interpretee : son sha256 doit etre celui de HASHES-AVANT.txt, de meme que celui de ce script ; les regles sont codees dans ce script (le hash garantit que le texte de la grille n'a pas bouge, pas que le code l'applique : voir test_mesure_aave_niveaux.py).
Regles de lecture (GRILLE.md, section 3) : deux noeuds, desaccord = NON LU ; erreur, limite de debit ou reponse vide pour une lecture qui devait decider = NON LU, jamais zero ;
temoins (dEaD, hasRole aleatoire, owner() de l'Executor Aave, hash de bloc) avant ET apres sur chaque noeud ; journaux d'evenements sur un seul noeud (les autres refusent les plages larges) ;
seuil de chaque multisig relu SANS cache au bloc daté et a la tete finalisee avant d'ecrire. Sortie : <out>.json et <out>.md. Codes : 0 ok, 2 refus (hash), 3 temoin avant en echec, 4 resultat INVALIDE."""
import argparse, base64, functools, gzip, hashlib, http.client, json, os, sys, time, urllib.error, urllib.parse

# ---------------------------------------------------------------- keccak256 (pure Python)
_RC = [0x0000000000000001, 0x0000000000008082, 0x800000000000808A, 0x8000000080008000,
       0x000000000000808B, 0x0000000080000001, 0x8000000080008081, 0x8000000000008009,
       0x000000000000008A, 0x0000000000000088, 0x0000000080008009, 0x000000008000000A,
       0x000000008000808B, 0x800000000000008B, 0x8000000000008089, 0x8000000000008003,
       0x8000000000008002, 0x8000000000000080, 0x000000000000800A, 0x800000008000000A,
       0x8000000080008081, 0x8000000000008080, 0x0000000080000001, 0x8000000080008008]
_ROT = [[0, 36, 3, 41, 18], [1, 44, 10, 45, 2], [62, 6, 43, 15, 61], [28, 55, 25, 21, 56], [27, 20, 39, 8, 14]]
_M = (1 << 64) - 1


def _f(A):
    for rc in _RC:
        C = [A[x][0] ^ A[x][1] ^ A[x][2] ^ A[x][3] ^ A[x][4] for x in range(5)]
        D = [C[(x - 1) % 5] ^ (((C[(x + 1) % 5] << 1) | (C[(x + 1) % 5] >> 63)) & _M) for x in range(5)]
        A = [[A[x][y] ^ D[x] for y in range(5)] for x in range(5)]
        B = [[0] * 5 for _ in range(5)]
        for x in range(5):
            for y in range(5):
                r = _ROT[x][y]
                B[y][(2 * x + 3 * y) % 5] = ((A[x][y] << r) | (A[x][y] >> (64 - r))) & _M if r else A[x][y]
        A = [[B[x][y] ^ ((~B[(x + 1) % 5][y]) & B[(x + 2) % 5][y]) for y in range(5)] for x in range(5)]
        A[0][0] ^= rc
    return A


@functools.lru_cache(maxsize=None)
def keccak(data):
    if isinstance(data, str):
        data = data.encode()
    rate = 136
    p = bytearray(data) + b"\x01" + b"\x00" * ((-len(data) - 2) % rate) + b"\x80"
    if len(p) % rate:  # case where a single padding byte is enough
        p = bytearray(data) + b"\x81"
    A = [[0] * 5 for _ in range(5)]
    for off in range(0, len(p), rate):
        blk = p[off:off + rate]
        for i in range(rate // 8):
            A[i % 5][i // 5] ^= int.from_bytes(blk[8 * i:8 * i + 8], "little")
        A = _f(A)
    out = b"".join(A[i % 5][i // 5].to_bytes(8, "little") for i in range(4))
    return "0x" + out.hex()


def sel(sig):
    return keccak(sig)[:10]


assert keccak("") == "0xc5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470"
assert keccak("PAUSER_ROLE") == "0x65d7a28e3265b37a6474929f336521b332c1681b933f6cb9f3376673440d862a"
assert sel("owner()") == "0x8da5cb5b" and sel("getThreshold()") == "0xe75235b8"
assert keccak("RoleGranted(bytes32,address,address)") == "0x2f8788117e7eff1d82e926ec794901d17c78024a50270940304540a733656f0d"

# ---------------------------------------------------------------- constants
POOL = "0x87870bca3f3fd6335c3f4ce8392d69350b4fa4e2"
DEFAULT_NODES = [("tenderly", "https://mainnet.gateway.tenderly.co"), ("blastapi", "https://eth-mainnet.public.blastapi.io")]
SLOTS = {
    "impl1967": "0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc",
    "admin1967": "0xb53127684a568b3173ae13b9f8a6016e243e63b6e8ee1178d6a717850b5d6103",
    "beacon1967": "0xa3f0ad74e5423aebfd80d3ef4346578335a9a72aeaee59ff6cb3582b35133d50",
    "zosAdmin": "0x10d6a54a4754c8869d6886b5f5d7fbfa5b4522237ea5c60d11bc4e7a1ff9390b",
    "zosImpl": "0x7050c9e0f4ca769c69bd3a8ef740bc37934f8e2c036e5a723fd8ee048ed3f8c3",
}
ROLE_NAMES = ["PAUSER_ROLE", "UNPAUSER_ROLE", "MINTER_ROLE", "BURNER_ROLE", "BLACKLISTER_ROLE",
              "BLACKLIST_MANAGER_ROLE", "UPGRADER_ROLE", "OPERATOR_ROLE", "CLAIMER_ROLE", "FREEZER_ROLE",
              "FACILITATOR_MANAGER_ROLE", "BUCKET_MANAGER_ROLE", "PROPOSER_ROLE", "EXECUTOR_ROLE",
              "CANCELLER_ROLE", "TIMELOCK_ADMIN_ROLE", "SNAPSHOT_ROLE", "GATEKEEPER_ROLE", "MANAGER_ROLE",
              "ADMIN_ROLE", "RESCUER_ROLE", "DENYLISTER_ROLE", "FREEZE_ROLE", "SANCTIONS_ROLE",
              "COLLATERAL_RATIO_PAUSER", "MINTER", "BRIDGE_ROLE", "RELAYER_ROLE"]
ROLES = {keccak(n): n for n in ROLE_NAMES}
ZERO32 = "0x" + "00" * 32
ROLES[ZERO32] = "DEFAULT_ADMIN_ROLE"
T_ROLE_GRANTED = keccak("RoleGranted(bytes32,address,address)")
T_RELY = keccak("Rely(address)")
T_LOGNOTE_RELY = sel("rely(address)") + "00" * 28
T_MINTER_CONF = keccak("MinterConfigured(address,uint256)")
AAVE_EXECUTORS = {"0x5300a1a15135ea4dc7ad5a167152c01efc9b192a": "Aave Executor lvl1",
                  "0x17dd33ed0e3dd2a80e37489b8a63063161be6957": "Aave Executor lvl2"}
AAVE_PAYLOADS_CONTROLLER = "0xdabad81af85554e9ae636395611c58f7ec1aaec5"
GHO = "0x40d16fc0246ad3160ccc09b8d0d3a2cd28ae6c2f"
DEAD = "0x000000000000000000000000000000000000dead"
EXTRA = [("0xb0f70c0bd6fd87dbeb7c10dc692a2a6106817072", "BTC.b : reserve Core hors des 25 premieres (fiche LlamaRisk t/25652)"),
         ("0x4c9edd5852cd905f086c759e8383e09bff1e68b3", "USDe : reserve Core hors des 25 premieres"),
         ("0x07041776f5007aca2a54844f50503a18a72a8b68", "USAT : non liste sur Core (fiche LlamaRisk t/25832)"),
         ("0x6c6494fd9962eb98b94ffa48f6679058f820700e", "PAXGy : non liste sur Core (fiche LlamaRisk t/25831)")]
NOTES_ACTIF = {"ENS": "le script donne 4 ; le 5 du 13/10 venait d'une lecture manuelle du bytecode du second proposeur (veto et cancel seulement), non rejouable par ce script"}
LIMITES_ACTIF = [
    ("PAXGy", "le niveau 3 est un plafond : la RolesAuthority de l'`authority()` (clé de gel unique selon la fiche LlamaRisk) n'est pas lue, ses rôles peuvent être plus faibles."),
    ("WBTC", "le custodian et la Factory de WBTC ne sont pas lus (seul l'owner du Controller l'est) : le niveau 2 peut être surestimé."),
    ("GHO", "les facilitateurs de GHO ne sont pas lus (seuls les rôles de gestion le sont) : le niveau 2 peut être surestimé."),
    ("USDe", "le niveau 0 est mécanique, par les EOA du contrat `minter()` ; les MINTER_ROLE de ce contrat soumettent des ordres bornés par bloc, bornes non lues."),
    ("USDC et cbETH", "le niveau 0 décrit la configuration en chaîne ; la garde réelle peut être hors chaîne (HSM, procédures), non lue."),
    ("rETH", "le pouvoir Rocket Pool passe par RocketStorage, non lu par ces getters : « aucun rôle lu »."),
    ("DAI", "le pouvoir passe par le Vat de Maker, non lu."),
    ("CRV et LDO", "ACL Aragon non dérivée."),
    ("BAL", "autorisation Balancer non lue."),
    ("toutes les réserves", "le statut gelé ou actif de chaque réserve n'est pas lu."),
]
MAX_ERR = 30        # erreurs finales par noeud avant de l'ecarter
LOGS_MAX = 400      # appels eth_getLogs au plus (un seul noeud) : au-dela, NON LU
# etat de l'execution
BLOCK = None        # "0x..." : bloc date
NODES = []
NON_LU = []
COUNT = {}
VIDES = {}
_cache = {}
REPLAY = None       # dict de cassette en mode rejeu (aucun reseau)
ORIGINE = {}        # statistiques de la lecture reseau d'origine (rejeu : lues dans la cassette)
RECORD = {}         # cassette enregistree : "noeud|methode|params" -> [statut, resultat]
META = {}           # holder -> type, seuil(s), delai, multisigs rencontres
INVALIDE = []       # raisons pour lesquelles le resultat est declare INVALIDE


def noter(quoi, msg):
    NON_LU.append((quoi, msg))


# ---------------------------------------------------------------- noeuds
def _connect(host):
    """HTTPS connection kept open, through the environment's HTTPS proxy if there is one."""
    px = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
    if not px:
        return http.client.HTTPSConnection(host, timeout=90)
    u = urllib.parse.urlparse(px)
    conn = http.client.HTTPSConnection(u.hostname, u.port or 443, timeout=90) if u.scheme == "https" else None
    if conn is None:
        conn = http.client.HTTPSConnection(u.hostname, u.port or 80, timeout=90)
        conn._create_connection = __import__("socket").create_connection  # plain-text CONNECT tunnel to the proxy
    hdr = {}
    if u.username:
        cred = "%s:%s" % (urllib.parse.unquote(u.username), urllib.parse.unquote(u.password or ""))
        hdr["Proxy-Authorization"] = "Basic " + base64.b64encode(cred.encode()).decode()
    conn.set_tunnel(host, 443, headers=hdr)
    return conn


class Node:
    GAP = 0.15

    def __init__(self, name, url):
        self.name, self.url, self.last, self.errs, self.dead, self.calls, self.conn, self.posts = name, url, 0.0, 0, False, 0, None, 0

    def _exchange(self, method, params):
        gap = time.time() - self.last
        if gap < self.GAP:
            time.sleep(self.GAP - gap)
        self.last = time.time()
        host = self.url.split("/")[2]
        path = "/" + "/".join(self.url.split("/")[3:])
        body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
        for attempt in (0, 1):  # connection kept open; one reconnect if the server closed it
            if self.conn is None:
                self.conn = _connect(host)
            try:
                self.conn.request("POST", path, body, {"content-type": "application/json", "user-agent": "curl/8.4"})
                r = self.conn.getresponse()
                data = r.read()
            except (http.client.HTTPException, OSError):
                self.conn.close()
                self.conn = None
                if attempt:
                    raise
                continue
            if r.status != 200:
                raise urllib.error.HTTPError(self.url, r.status, r.reason, None, None)
            return json.loads(data)

    def _live(self, method, params):
        last = "?"
        for k in range(3):
            self.calls += 1
            try:
                r = self._exchange(method, params)
            except urllib.error.HTTPError as e:
                last = "HTTP %s" % e.code
                if e.code == 429 or e.code >= 500:
                    time.sleep(1.0 * 2 ** k)
                    continue
                return ("err", last)
            except Exception as e:  # network, timeout, unreadable JSON
                last = type(e).__name__
                time.sleep(1.0 * 2 ** k)
                continue
            if "error" in r:
                msg = str(r["error"].get("message", r["error"]))
                if r["error"].get("code") == 3 or "revert" in msg.lower():
                    return ("revert", msg)
                last = "rpc: " + msg[:100]
                if k < 1:
                    time.sleep(0.5)
                    continue
                return ("err", last)
            if r.get("result") is None:
                return ("err", "resultat nul")
            return ("ok", r["result"])
        return ("err", last)

    def post(self, method, params):
        key = "%s|%s|%s" % (self.name, method, json.dumps(params, sort_keys=True))
        self.posts += 1  # demandes logiques (une demande peut coûter plusieurs appels reseau : reessais)
        if REPLAY is not None:
            v = REPLAY.get(key)
            return ("err", "cassette: lecture absente") if v is None else (v[0], v[1])
        if self.dead:
            return ("err", "noeud ecarte (%d erreurs)" % self.errs)
        out = self._live(method, params)
        RECORD[key] = [out[0], out[1]]
        if out[0] == "err":
            self.errs += 1
            if self.errs >= MAX_ERR:
                self.dead = True
        return out


def _canon(x):
    return json.dumps(x, sort_keys=True).lower()


def combine(res):
    """res = [(noeud, (statut, valeur))...] -> statut commun, ou ('err', raison) : erreur ou desaccord = NON LU, jamais une valeur de repli."""
    errs = ["%s: %s" % (n.name, r[1]) for n, r in res if r[0] == "err"]
    if errs:
        return ("err", " ; ".join(errs))
    kinds = {r[0] for _, r in res}
    if kinds == {"revert"}:
        return ("revert", res[0][1][1])
    if len(kinds) > 1:
        return ("err", "desaccord ok/revert entre noeuds")
    if len({_canon(r[1]) for _, r in res}) > 1:
        return ("err", "desaccord entre noeuds : " + " | ".join("%s=%s" % (n.name, str(r[1])[:70]) for n, r in res))
    return ("ok", res[0][1][1])


def rpc(method, params, nodes=None, fresh=False):
    """('ok', resultat) | ('revert', msg) | ('err', raison). Jamais un zero invente."""
    nodes = nodes or NODES
    key = (method, json.dumps(params), tuple(n.name for n in nodes))
    if not fresh and key in _cache:
        return _cache[key]
    COUNT[method] = COUNT.get(method, 0) + 1
    out = combine([(n, n.post(method, params)) for n in nodes])
    if not fresh:
        _cache[key] = out
    return out


def call(to, data, quoi=None, blk=None, fresh=False):
    st, res = rpc("eth_call", [{"to": to, "data": data}, blk or BLOCK], fresh=fresh)
    if st == "err":
        noter(quoi or "eth_call %s %s" % (to, data[:10]), res)
    elif st == "ok" and res in ("0x", ""):
        VIDES[data[:10]] = VIDES.get(data[:10], 0) + 1  # reponse vide : jamais prise pour une valeur
    return st, res


def word_addr(h):
    """A 32-byte word shaped like an address, otherwise None."""
    if not h or len(h) != 66 or h[2:26] != "0" * 24:
        return None
    return "0x" + h[26:]


def get_addr(to, sig):
    st, res = call(to, sel(sig), "%s on %s" % (sig, to))
    if st != "ok":
        return st, None
    a = word_addr(res)
    return ("ok", a) if a is not None else ("absent", None)


def get_uint(to, sig, blk=None, fresh=False):
    st, res = call(to, sel(sig), "%s on %s" % (sig, to), blk, fresh)
    if st == "ok" and res and len(res) == 66:
        return "ok", int(res, 16)
    return (st if st != "ok" else "absent"), None


def storage(addr, slot):
    st, res = rpc("eth_getStorageAt", [addr, slot, BLOCK])
    if st != "ok" or not isinstance(res, str) or len(res) != 66:
        noter("eth_getStorageAt %s %s" % (addr, slot[:10]), res if st != "ok" else "reponse inattendue")
        return "err", None
    return "ok", ("0x" + res[-40:] if int(res, 16) else None)


def get_code(addr):
    st, res = rpc("eth_getCode", [addr, BLOCK])
    if st != "ok":
        noter("eth_getCode %s" % addr, res)
        return None
    return res


def logs(addr, topics, lo=0, hi=None):
    """eth_getLogs sur le PREMIER noeud seulement (les autres refusent les plages larges), coupe en deux si la plage est refusee."""
    hi = int(BLOCK, 16) if hi is None else hi
    if COUNT.get("eth_getLogs", 0) >= LOGS_MAX:
        noter("eth_getLogs %s [%d-%d]" % (addr, lo, hi), "budget de %d appels epuise" % LOGS_MAX)
        return None
    st, res = rpc("eth_getLogs", [{"address": addr, "topics": topics, "fromBlock": hex(lo), "toBlock": hex(hi)}], nodes=[NODES[0]])
    if st == "ok":
        return res
    if hi - lo < 1000:
        noter("eth_getLogs %s %s [%d-%d]" % (addr, topics[0][:10], lo, hi), res)
        return None
    mid = (lo + hi) // 2  # range too wide: split in two
    a, b = logs(addr, topics, lo, mid), logs(addr, topics, mid + 1, hi)
    return None if a is None or b is None else a + b


def has_role(addr, role, acct):
    st, res = call(addr, sel("hasRole(bytes32,address)") + role[2:] + "0" * 24 + acct[2:],
                   "hasRole(%s,%s) on %s" % (ROLES.get(role, role[:10]), acct, addr))
    if st != "ok" or len(res) != 66:
        return None  # erreur, desaccord ou reponse vide : NON LU
    return int(res, 16) == 1


def role_holders(addr):
    """Current holders of each AccessControl role: RoleGranted events (un noeud), then hasRole at the dated block (deux noeuds)."""
    lg = logs(addr, [T_ROLE_GRANTED])
    if lg is None:
        return None
    seen, out = set(), []
    for l in lg:
        role, acct = l["topics"][1], "0x" + l["topics"][2][-40:]
        if (role, acct) in seen:
            continue
        seen.add((role, acct))
        h = has_role(addr, role, acct)
        if h is None:
            out.append((role, acct, "NON LU"))
        elif h:
            out.append((role, acct, "ok"))
    # cross-check with getRoleMemberCount when the contract is enumerable
    for role in {r for r, _, _ in out}:
        st, res = call(addr, sel("getRoleMemberCount(bytes32)") + role[2:], "getRoleMemberCount on %s" % addr)
        if st == "ok" and len(res) == 66:
            n = int(res, 16)
            k = sum(1 for r, _, s in out if r == role and s == "ok")
            if n != k:
                noter("ecart getRoleMemberCount(%s)=%d contre %d lus par les evenements sur %s" % (ROLES.get(role, role[:10]), n, k, addr), "ecart")
    return out


def ward_holders(addr):
    st, res = call(addr, sel("wards(address)") + "00" * 32, "wards(0) on %s" % addr)
    if st == "err":
        return None
    if st != "ok" or len(res) != 66:
        return []
    cands = set()
    for topics, idx in (([T_RELY], 1), ([T_LOGNOTE_RELY], 2)):
        lg = logs(addr, topics)
        if lg is None:
            return None
        for l in lg:
            if len(l["topics"]) > idx:
                cands.add("0x" + l["topics"][idx][-40:])
    out = []
    for c in sorted(cands):
        st, res = call(addr, sel("wards(address)") + "0" * 24 + c[2:], "wards(%s) on %s" % (c, addr))
        if st == "ok" and len(res) == 66 and int(res, 16) == 1:
            out.append(("wards (rely)", c))
        elif st == "err" or (st == "ok" and len(res) != 66):
            out.append(("wards (rely) NON LU", c))
    return out


def fiat_minters(addr):
    lg = logs(addr, [T_MINTER_CONF])
    if lg is None:
        return None
    out = []
    # FiatToken: MinterConfigured(address indexed minter, uint256); falls back to data if not indexed
    for c in sorted({"0x" + (l["topics"][1][-40:] if len(l["topics"]) > 1 else l["data"][26:66]) for l in lg}):
        st, res = call(addr, sel("isMinter(address)") + "0" * 24 + c[2:], "isMinter(%s) on %s" % (c, addr))
        if st == "ok" and len(res) == 66 and int(res, 16) == 1:
            out.append(("minter (FiatToken)", c))
        elif st == "err" or (st == "ok" and len(res) != 66):
            out.append(("minter (FiatToken) NON LU", c))
    return out


# ---------------------------------------------------------------- controllers of a contract
GETTERS = ["owner()", "admin()", "minter()", "controller()", "authority()", "masterMinter()", "pauser()", "blacklister()",
           "guardian()", "RISK_COUNCIL()"]


def controllers(addr, with_minters=False):
    """List of (role, holder) read on a contract: proxy slots, getters, AccessControl, wards."""
    out, proxy = [], []
    for name in ("admin1967", "zosAdmin", "beacon1967", "impl1967", "zosImpl"):
        st, a = storage(addr, SLOTS[name])
        if st == "err":
            out.append(("slot %s NON LU" % name, None))
        elif a:
            proxy.append(name)
            if name in ("admin1967", "zosAdmin"):
                out.append(("proxy admin (%s)" % name, a))
            elif name == "beacon1967":
                out.append(("beacon (upgrade)", a))
    fiat = False
    for g in GETTERS:
        st, a = get_addr(addr, g)
        if st == "err":
            out.append(("%s NON LU" % g, None))
        elif st == "ok":
            if g == "masterMinter()":
                fiat = True
            if int(a, 16) == 0:
                out.append(("%s = 0x0 (renonce ou vide)" % g, "0x" + "0" * 40))
            elif a.lower() != addr.lower():
                out.append((g, a))
    rh = role_holders(addr)
    if rh is None:
        out.append(("RoleGranted NON LU", None))
    else:
        for role, acct, s in rh:
            out.append((ROLES.get(role, "role " + role[:10]) + ("" if s == "ok" else " NON LU"), acct))
    wh = ward_holders(addr)
    if wh is None:
        out.append(("Rely NON LU", None))
    else:
        out.extend(wh)
    if fiat and with_minters:
        fm = fiat_minters(addr)
        out.extend(fm if fm is not None else [("MinterConfigured NON LU", None)])
    return proxy, out


# ---------------------------------------------------------------- classifying a holder
_class = {}


def _m(addr, typ, delai_s=None, multisigs=None):
    META[addr] = {"type": typ, "delai_s": delai_s, "multisigs": multisigs or []}


def _agg(addrs):
    """multisigs rencontres et plus petit delai parmi des detenteurs deja classes."""
    ms, dl = [], []
    for a in addrs:
        m = META.get(a)
        if m:
            for x in m["multisigs"]:
                if x not in ms:
                    ms.append(x)
            if m["delai_s"] is not None:
                dl.append(m["delai_s"])
    return ms, (min(dl) if dl else None)


def classify(addr, depth=0, stack=()):
    """Returns (level or None, description). None = unclassified (NON LU, or a mechanism outside the grid)."""
    addr = addr.lower()
    if addr in _class:
        return _class[addr]
    if addr in stack or depth > 5:
        return (None, "boucle ou profondeur > 5")
    code = get_code(addr)
    if code is None:
        res = (None, "NON LU (eth_getCode)")
        _m(addr, "NON LU")
    elif code in ("0x", ""):
        res = (0, "EOA")
        _m(addr, "EOA")
    elif code.startswith("0xef0100"):
        res = (0, "EOA delegated by EIP-7702 to 0x%s" % code[8:48])
        _m(addr, "EOA (EIP-7702)")
    else:
        res = _classify_contract(addr, depth, stack + (addr,))
    _class[addr] = res
    return res


def _short(a):
    return a[:6] + ".." + a[-4:]


def _safe(addr):
    st, s = get_uint(addr, "getThreshold()")
    kind = "Safe"
    if st != "ok":
        st2, s = get_uint(addr, "required()")
        if st2 != "ok":
            return None if st != "err" and st2 != "err" else "err"
        kind = "MultiSigWallet"
    st, res = call(addr, sel("getOwners()"), "getOwners() on %s" % addr)
    if st != "ok":
        return "err"
    n = int(res[66:130], 16) if len(res) >= 130 else None
    if not n or not s:
        noter("getOwners() on %s" % addr, "reponse vide ou inattendue")
        return "err"
    mods = ""
    if kind == "Safe":
        st, res2 = call(addr, sel("getModulesPaginated(address,uint256)") + "0" * 63 + "1" + "%064x" % 10, "getModulesPaginated on %s" % addr)
        if st == "ok" and len(res2) >= 194:
            k = int(res2[130:194], 16)
            mods = ", %d module(s)" % k if k else ""
        elif st != "ok" or len(res2) < 194:
            mods = ", modules NON LU"
    lvl = 2 if s * 2 > n else 1
    return (lvl, "%s %d/%d%s" % (kind, s, n, mods), s, n, kind, hashlib.sha256(res.encode()).hexdigest()[:16])


def _is_dao(addr):
    """Description starting with 'DAO ' if the contract is on-chain governance, otherwise None."""
    if addr in AAVE_EXECUTORS:
        st, o = get_addr(addr, "owner()")
        if st == "err":
            return "ERR"
        if st == "ok" and o == AAVE_PAYLOADS_CONTROLLER:
            return "DAO %s (owner = PayloadsController)" % AAVE_EXECUTORS[addr]
        return None
    st, v = get_uint(addr, "votingPeriod()")
    if st == "err":
        return "ERR"
    if st == "ok" and v:
        return "DAO Governor (votingPeriod %d)" % v
    st, a = get_addr(addr, "hat()")
    if st == "err":
        return "ERR"
    if st == "ok":
        return "DAO DSChief (token vote, hat %s)" % _short(a)
    return None


def _eff(cl, cd):
    """Level of a controller placed in front of a timelock: a DAO counts as 5."""
    return 5 if cd.startswith("DAO ") else cl


def _after_delay(eff, d):
    """Level obtained when a controller of level eff acts through a delay d."""
    if eff is None:
        return None
    if eff == 5:
        return 5
    if eff >= 2:  # honest-majority multisig, or already behind a timelock
        return max(eff, 2 if d == 0 else (4 if d >= 172800 else 3))
    return eff  # EOA or minority multisig: the delay does not raise them (conservative)


def fmt_lvl(l):
    return "?" if l is None else str(l)


def _brief(a, cl, cd):
    """Short description of a controller, without unfolding generic contracts."""
    if cd.startswith("contrat"):
        return "%s (contrat, niveau %s)" % (_short(a), fmt_lvl(cl))
    return "%s %s" % (_short(a), cd)


def _top(items, k=3):
    """items = (level, text): the k weakest first, then the remaining count."""
    items = sorted(items, key=lambda x: (99 if x[0] is None else x[0], 0 if " EOA" in x[1] else 1))
    out = " ; ".join(t for _, t in items[:k])
    return out + (" ; + %d autre(s)" % (len(items) - k) if len(items) > k else "")


def _classify_contract(addr, depth, stack):
    dao = _is_dao(addr)
    if dao == "ERR":  # une sonde qui echoue (erreur, desaccord de noeuds) n'autorise pas a essayer un autre type : NON LU
        _m(addr, "NON LU")
        return (None, "NON LU (sonde DAO)")
    if dao:
        # an Aave Executor already sits behind the PayloadsController delay; a Governor alone is outside the grid
        _m(addr, dao.split(" (")[0])
        return (5 if addr in AAVE_EXECUTORS else None, dao)
    sf = _safe(addr)
    if sf == "err":
        _m(addr, "multisig NON LU")
        return (None, "multisig NON LU")
    if sf:
        _m(addr, sf[4], None, [(addr, sf[4], sf[2], sf[3], sf[5])])
        return sf[0], sf[1]
    st, d = get_uint(addr, "getMinDelay()")
    if st == "err":
        _m(addr, "NON LU")
        return (None, "NON LU (getMinDelay)")
    if st == "ok":  # TimelockController OpenZeppelin
        rh = role_holders(addr)
        if rh is None:
            _m(addr, "TimelockController", d)
            return (None, "TimelockController %d s, RoleGranted NON LU" % d)
        if any(s_ != "ok" for _, _, s_ in rh):  # GRILLE 3.9 : un detenteur de role NON LU n'est ni un detenteur ni une absence
            _m(addr, "TimelockController", d)
            return (None, "TimelockController %d s, un detenteur de role NON LU" % d)
        by = {}
        for r, a, s_ in rh:
            by.setdefault(ROLES.get(r, r[:10]), []).append(a)
        execs = by.get("EXECUTOR_ROLE", [])
        open_exec = (not execs) or ("0x" + "0" * 40) in execs
        ex_lvl, ex_desc, kids = None, "open executor" if open_exec else "", []
        if not open_exec:
            el = [(a,) + classify(a, depth + 1, stack) for a in execs if a != addr]
            kids += [a for a, _, _ in el]
            lv = [_eff(c, dsc) for _, c, dsc in el]
            ex_lvl = None if (not lv or None in lv) else min(lv)
            ex_desc = "EXECUTOR " + _top([(c, _brief(a, c, dsc)) for a, c, dsc in el])
        best, parts, unk = None, [], False
        for role in ("PROPOSER_ROLE", "TIMELOCK_ADMIN_ROLE", "DEFAULT_ADMIN_ROLE"):
            for a in by.get(role, []):
                if a == addr:
                    continue
                cl, cd = classify(a, depth + 1, stack)
                kids.append(a)
                e = _eff(cl, cd)
                if role == "PROPOSER_ROLE" and not open_exec and e is not None:
                    e = None if ex_lvl is None else max(e, ex_lvl)  # proposer AND executor are both required
                lv = _after_delay(e, d)
                parts.append("%s %s" % (role.replace("_ROLE", ""), _brief(a, cl, cd)))
                if lv is None:
                    unk = True
                else:
                    best = lv if best is None else min(best, lv)
        ms, _ = _agg(kids)
        _m(addr, "TimelockController", d, ms)
        if not parts:
            return (None, "TimelockController %d s sans proposeur ni admin lu" % d)
        return (best, "TimelockController %d s (%.0f h) <- %s ; %s%s" % (
            d, d / 3600, " ; ".join(parts), ex_desc, " [en partie non classe]" if unk else ""))
    st, d = get_uint(addr, "delay()")
    if st == "err":
        _m(addr, "NON LU")
        return (None, "NON LU (delay)")
    if st == "ok":  # Compound Timelock or DSPause: admin()/owner()/authority() act through the delay
        best, parts, unk, kids = None, [], False, []
        for g in ("admin()", "owner()", "authority()"):
            s2, a = get_addr(addr, g)
            if s2 == "ok" and int(a, 16) and a != addr:
                cl, cd = classify(a, depth + 1, stack)
                kids.append(a)
                lv = _after_delay(_eff(cl, cd), d)
                parts.append("%s %s" % (g, _brief(a, cl, cd)))
                if lv is None:
                    unk = True
                else:
                    best = lv if best is None else min(best, lv)
        if parts:
            ms, _ = _agg(kids)
            _m(addr, "Timelock (delay())", d, ms)
            return (best, "Timelock delay() %d s (%.0f h) <- %s%s" % (d, d / 3600, " ; ".join(parts), " [en partie non classe]" if unk else ""))
    st, k = get_addr(addr, "kernel()")
    if st == "err":
        _m(addr, "NON LU")
        return (None, "NON LU (kernel)")
    if st == "ok":
        _m(addr, "Aragon app")
        return (None, "Aragon app (kernel %s), ACL non derivee" % _short(k))
    _, cs = controllers(addr)  # generic contract: go up to its own controllers
    seen, best, parts, unk, kids = set(), None, [], False, []
    for r, a in cs:
        if a is None:
            unk = True
            parts.append((None, r))
            continue
        if not int(a, 16) or (r, a) in seen:
            continue
        seen.add((r, a))
        cl, cd = classify(a, depth + 1, stack)
        kids.append(a)
        parts.append((cl, "%s %s" % (r, _brief(a, cl, cd))))
        if cl is None:
            unk = True
        else:
            best = cl if best is None else min(best, cl)
    if not parts:
        _m(addr, "contrat")
        return (None, "contrat sans controleur lu (immuable ou registre non lu)")
    ms, dl = _agg(kids)
    _m(addr, "contrat", dl, ms)
    return (best, "contrat <- " + _top(parts) + (" [en partie non classe]" if unk else ""))


# ---------------------------------------------------------------- reserves and sorties
def reserves():
    st, res = call(POOL, sel("getReservesList()"), "getReservesList")
    if st != "ok" or len(res) < 130:
        sys.exit("getReservesList NON LU : %s" % res)
    h = res[2:]
    n = int(h[64:128], 16)
    return ["0x" + h[128 + 64 * i + 24:128 + 64 * (i + 1)] for i in range(n)]


def symbol(a):
    st, res = call(a, sel("symbol()"), "symbol() on %s" % a)
    if st != "ok" or len(res) < 66:
        if st == "ok":
            noter("symbol() on %s" % a, "reponse vide ou trop courte")
        return "NON LU"
    h = res[2:]
    if len(h) == 64:
        return bytes.fromhex(h).rstrip(b"\0").decode(errors="replace")
    l = int(h[64:128], 16)
    return bytes.fromhex(h[128:128 + 2 * l]).decode(errors="replace")


def block_info(tag):
    """(numero, hash, horodatage) lus sur CHAQUE noeud ; tout ecart ou toute erreur = None."""
    vues = []
    for n in NODES:
        st, r = n.post("eth_getBlockByNumber", [tag, False])
        if st != "ok" or not isinstance(r, dict) or "hash" not in r:
            return None, "%s: %s" % (n.name, r if st != "ok" else "reponse inattendue")
        vues.append((n.name, int(r["number"], 16), r["hash"], int(r["timestamp"], 16)))
    if len({v[1:] for v in vues}) > 1:
        return None, "desaccord de bloc : " + " | ".join("%s=%d %s" % (v[0], v[1], v[2][:12]) for v in vues)
    return {"numero": vues[0][1], "hash": vues[0][2], "horodatage": vues[0][3]}, None


def temoins(phase, bloc_hex):
    """Temoins sur CHAQUE noeud pris isolement. Retourne [(nom, noeud, attendu, obtenu, ok)]."""
    out = []
    rnd = keccak("aave-niveaux-temoin-" + bloc_hex)[:42]
    fm = keccak("FACILITATOR_MANAGER_ROLE")
    for n in NODES:
        st, r = n.post("eth_call", [{"to": DEAD, "data": sel("getThreshold()")}, bloc_hex])
        out.append(("getThreshold() sur dEaD", n.name, "0x (vide)", "%s %s" % (st, r), st == "ok" and r == "0x"))
        st, r = n.post("eth_call", [{"to": GHO, "data": sel("hasRole(bytes32,address)") + fm[2:] + "0" * 24 + rnd[2:]}, bloc_hex])
        out.append(("hasRole(FACILITATOR_MANAGER_ROLE, adresse aleatoire) sur GHO", n.name, "faux (0x00..00)", "%s %s" % (st, str(r)[-4:]), st == "ok" and isinstance(r, str) and len(r) == 66 and int(r, 16) == 0))
        st, r = n.post("eth_call", [{"to": "0x5300a1a15135ea4dc7ad5a167152c01efc9b192a", "data": sel("owner()")}, bloc_hex])
        out.append(("owner() de l'Executor Aave lvl1", n.name, "PayloadsController", "%s %s" % (st, str(r)[-40:]), st == "ok" and word_addr(r) == AAVE_PAYLOADS_CONTROLLER))
    bi, err = block_info(bloc_hex)
    out.append(("meme hash de bloc sur les deux noeuds", "tous", "identique", err or bi["hash"], bi is not None))
    return out


def lire_releve(addr, kind, blk, fresh):
    """(seuil, proprietaires, empreinte) d'un multisig lu SANS cache a un bloc, ou None si NON LU."""
    st, s = get_uint(addr, "getThreshold()" if kind == "Safe" else "required()", blk, fresh)
    if st != "ok":
        return None
    st, res = call(addr, sel("getOwners()"), "getOwners() on %s" % addr, blk, fresh)
    if st != "ok" or len(res) < 130:
        return None
    return (s, int(res[66:130], 16), hashlib.sha256(res.encode()).hexdigest()[:16])


def rafraichir(bloc_num):
    """Relit chaque multisig rencontre sans cache au bloc date et a la tete finalisee ; ecrit les ecarts."""
    ms = {}
    for m in META.values():
        for x in m["multisigs"]:
            ms[x[0]] = x
    fin, err = block_info("finalized")
    tete = hex(fin["numero"]) if fin and fin["numero"] > bloc_num else None
    out = []
    for a in sorted(ms):
        _, kind, s, n, oh = ms[a]
        v = lire_releve(a, kind, BLOCK, True)
        t = lire_releve(a, kind, tete, True) if tete else None
        ligne = {"multisig": a, "type": kind, "classe": "%d/%d" % (s, n), "relu_bloc_date": ("%d/%d" % v[:2]) if v else "NON LU",
                 "stable": bool(v and v == (s, n, oh)), "tete_finalisee": int(tete, 16) if tete else None,
                 "relu_tete": ("%d/%d" % t[:2]) if t else ("NON LU" if tete else "-"),
                 "meme_proprietaires_tete": (t[2] == oh) if t else None,
                 "ecart_tete": bool(t and (t[0], t[1], t[2]) != (s, n, oh))}
        if not ligne["stable"]:
            INVALIDE.append("seuil de %s relu sans cache: %s contre %d/%d classe" % (a, ligne["relu_bloc_date"], s, n))
        out.append(ligne)
    return out, (None if tete else "tete finalisee non lue ou pas au-dela du bloc date (%s)" % (err or "-"))


def type_lisible(h):
    return META.get(h, {}).get("type") or "?"


def seuil_texte(h):
    ms = META.get(h, {}).get("multisigs", [])
    return ", ".join(sorted({"%d/%d" % (x[2], x[3]) for x in ms})) if ms else ""


def balayage(a, bloc_num):
    lst = reserves()
    assets = [(x, "reserve n°%d" % i) for i, x in enumerate(lst[:a.limit])]
    if not a.no_extra:
        assets += EXTRA
    lignes, actifs = [], []
    for addr, origine in assets:
        sym = symbol(addr)
        print("... %s %s" % (sym, addr), file=sys.stderr, flush=True)
        proxy, cs = controllers(addr, with_minters=True)
        rows = []
        for r, h in cs:
            if h is None:
                rows.append((r, None, None, "NON LU"))
            elif int(h, 16) == 0:
                rows.append((r, "0x0", None, "renonce ou vide"))
            else:
                l, d = classify(h)
                rows.append((r, h, l, d))
        held = [x for x in rows if x[1] not in (None, "0x0")]
        known = [x[2] for x in held if x[2] is not None]
        unk = any(x[2] is None for x in held) or any(x[1] is None for x in rows) or any("NON LU" in x[0] for x in rows)
        niveau = min(known) if known else None
        if not held and not unk:
            statut = "aucun role lu (absence de lecture, pas absence de pouvoir)"
        elif known:
            statut = "%d%s" % (niveau, " (+ non classe)" if unk else "")
        else:
            statut = "non classe"
        actifs.append({"actif": sym, "adresse": addr, "origine": origine, "niveau": niveau, "statut": statut, "non_lu": bool(unk),
                       "proxy": proxy})
        if not rows:
            lignes.append({"actif": sym, "adresse_actif": addr, "role": "-", "detenteur": None, "type": "-", "seuil": "", "delai_s": None,
                           "niveau": None, "bloc": bloc_num, "non_lu": False, "detail": "aucun role privilegie lu par les lectures standards"})
        for r, h, l, d in rows:
            hl = h.lower() if h and h != "0x0" else None
            nl = (h is None) or (l is None and h != "0x0") or "NON LU" in r
            lignes.append({"actif": sym, "adresse_actif": addr, "role": r, "detenteur": h if h != "0x0" else "0x0", "type": type_lisible(hl) if hl else d,
                           "seuil": seuil_texte(hl) if hl else "", "delai_s": META.get(hl, {}).get("delai_s") if hl else None,
                           "niveau": l, "bloc": bloc_num, "non_lu": nl, "detail": d,
                           "agrege": bool(hl and (seuil_texte(hl) or META.get(hl, {}).get("delai_s") is not None) and type_lisible(hl) not in ("Safe", "MultiSigWallet"))})
    return lignes, actifs, lst


def md_table(lignes):
    """Regroupe les detenteurs de meme actif, role, type et niveau."""
    g, ordre = {}, []
    for r in lignes:
        k = (r["actif"], r["role"], r["type"], r["seuil"], r["delai_s"], r["niveau"], r["non_lu"])
        if k not in g:
            g[k] = [r, 0]
            ordre.append(k)
        g[k][1] += 1
    out = ["| actif | rôle | détenteur | type | seuil | délai | niveau | bloc | non lu |", "|---|---|---|---|---|---|---|---|---|"]
    for k in ordre:
        r, c = g[k]
        h = "%d détenteurs" % c if c > 1 else (_short(r["detenteur"]) if r["detenteur"] and r["detenteur"].startswith("0x") and len(r["detenteur"]) == 42 else (r["detenteur"] or "-"))
        dl = "-" if r["delai_s"] is None else "%d s (%.0f h)" % (r["delai_s"], r["delai_s"] / 3600)
        out.append("| %s | %s | %s | %s | %s | %s | %s | %d | %s |" % (r["actif"], r["role"], h, str(r["type"]).replace("|", "/") + (" [seuil et délai agrégés]" if r.get("agrege") else ""), r["seuil"] or "-", dl,
                                                                     "NON LU" if r["niveau"] is None and r["non_lu"] else fmt_lvl(r["niveau"]) if r["niveau"] is not None else "-", r["bloc"], "OUI" if r["non_lu"] else "non"))
    return "\n".join(out)


def sha_fichier(p):
    with open(p, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def lire_hashes(p):
    d = {}
    for l in open(p, encoding="utf-8"):
        l = l.strip()
        if l and not l.startswith("#"):
            h, f = l.split(None, 1)
            d[os.path.basename(f.strip().lstrip("*"))] = h
    return d


def main():
    global BLOCK, NODES, REPLAY
    ap = argparse.ArgumentParser()
    ap.add_argument("--block", type=int, required=True, help="bloc date (numero)")
    ap.add_argument("--hashes", help="HASHES-AVANT.txt : sha256 de GRILLE.md et de ce script, ecrits avant la lecture")
    ap.add_argument("--sans-hash-avant", action="store_true", help="essais seulement : le rapport l'ecrit en toutes lettres")
    ap.add_argument("--grille", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "GRILLE.md"))
    ap.add_argument("--limit", type=int, default=25)
    ap.add_argument("--no-extra", action="store_true")
    ap.add_argument("--nodes", help="nom=url,nom=url (deux noeuds ; le premier sert aux journaux)")
    ap.add_argument("--cassette-in", help="rejeu sans reseau d'une cassette .json.gz")
    ap.add_argument("--cassette-out", help="ou ecrire la cassette (defaut : <out>-cassette.json.gz)")
    ap.add_argument("--out", required=True, help="prefixe de sortie : <out>.json et <out>.md")
    a = ap.parse_args()
    debut = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    me = os.path.abspath(__file__)
    script_sha, grille_sha = sha_fichier(me), sha_fichier(a.grille)
    avant = {}
    if a.hashes:
        h = lire_hashes(a.hashes)
        avant = {"hashes_avant_sha256": sha_fichier(a.hashes), "hashes_avant_mtime": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(os.path.getmtime(a.hashes)))}
        if h.get(os.path.basename(a.grille)) != grille_sha:
            sys.exit("REFUS : GRILLE.md n'a pas le sha256 de HASHES-AVANT.txt (%s contre %s)" % (grille_sha[:12], str(h.get(os.path.basename(a.grille)))[:12]))
        if h.get(os.path.basename(me)) != script_sha:
            sys.exit("REFUS : ce script n'a pas le sha256 de HASHES-AVANT.txt (%s contre %s)" % (script_sha[:12], str(h.get(os.path.basename(me)))[:12]))
    elif not a.sans_hash_avant:
        sys.exit("REFUS : --hashes HASHES-AVANT.txt est obligatoire (ou --sans-hash-avant pour un essai)")
    BLOCK = hex(a.block)
    noeuds = [tuple(x.split("=", 1)) for x in a.nodes.split(",")] if a.nodes else DEFAULT_NODES
    if len(noeuds) != 2:
        sys.exit("REFUS : exactement deux noeuds")
    NODES = [Node(n, u) for n, u in noeuds]
    if a.cassette_in:
        with gzip.open(a.cassette_in, "rt", encoding="utf-8") as f:
            REPLAY = json.load(f)
        ORIGINE.update(REPLAY.pop("_execution_live", {}))
    bi, err = block_info(BLOCK)
    if bi is None:
        sys.exit("ARRET : bloc %d non lu identiquement sur les deux noeuds : %s" % (a.block, err))
    t_avant = temoins("avant", BLOCK)
    if not all(t[4] for t in t_avant):
        for t in t_avant:
            print(("OK  " if t[4] else "ECHEC"), t[:4], file=sys.stderr)
        sys.exit(3)
    lignes, actifs, lst = balayage(a, a.block)
    raf, raf_note = rafraichir(a.block)
    t_apres = temoins("apres", BLOCK)
    if not all(t[4] for t in t_apres):
        INVALIDE.append("temoin en echec apres la lecture : " + "; ".join("%s/%s" % (t[0], t[1]) for t in t_apres if not t[4]))
    fin = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    nb = lambda f: sum(1 for x in actifs if f(x))
    avec = nb(lambda x: x["niveau"] is not None and not x["non_lu"])
    avec_nc = nb(lambda x: x["niveau"] is not None and x["non_lu"])
    nc = nb(lambda x: x["niveau"] is None and x["non_lu"])
    aucun = nb(lambda x: x["niveau"] is None and not x["non_lu"])
    synth = {"actifs": len(actifs), "avec_niveau": avec, "avec_niveau_plus_non_classe": avec_nc, "non_classes": nc, "aucun_role_lu": aucun,
             "lignes": len(lignes), "lignes_non_classees": sum(1 for r in lignes if r["non_lu"]), "lectures_en_erreur_ou_en_desaccord": len(NON_LU)}
    contenu = {"schema": "aave-niveaux/v1", "bloc": a.block, "bloc_hash": bi["hash"], "bloc_horodatage_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(bi["horodatage"])),
               "pool": POOL, "reserves_total": len(lst), "reserves_liste": lst, "noeuds": [n.name for n in NODES], "grille_sha256": grille_sha, "script_sha256": script_sha,
               "sans_hash_avant": bool(a.sans_hash_avant), "invalide": INVALIDE, "synthese": synth, "actifs": actifs, "lignes": lignes,
               "rafraichissement_multisigs": raf, "rafraichissement_note": raf_note,
               "temoins_avant": [list(t) for t in t_avant], "temoins_apres": [list(t) for t in t_apres],
               "non_lu": [{"lecture": w, "raison": m} for w, m in NON_LU], "reponses_vides": VIDES,
               "journaux": "un seul noeud (%s) : %d requetes eth_getLogs distinctes" % (NODES[0].name, COUNT.get("eth_getLogs", 0)), "appels": COUNT}
    contenu["contenu_sha256"] = hashlib.sha256(json.dumps(contenu, sort_keys=True).encode()).hexdigest()
    live = ORIGINE or {"appels_par_noeud": {n.name: n.calls for n in NODES}, "erreurs_par_noeud": {n.name: n.errs for n in NODES}}
    demandes = {n.name: n.posts for n in NODES}
    reessais = {k: live["appels_par_noeud"].get(k, 0) - v for k, v in demandes.items()}
    exe = dict(avant, debut_utc=debut, fin_utc=fin, appels_par_noeud=live["appels_par_noeud"], erreurs_par_noeud=live["erreurs_par_noeud"], demandes_logiques_par_noeud=demandes,
               reessais_par_noeud=reessais, rejeu=bool(a.cassette_in), lecture_reseau_d_origine=bool(ORIGINE))
    doc = dict(contenu, execution=exe)
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    json.dump(doc, open(a.out + ".json", "w", encoding="utf-8"), indent=1, ensure_ascii=False, sort_keys=True)
    if not a.cassette_in:
        gz = a.cassette_out or (a.out + "-cassette.json.gz")
        with gzip.open(gz, "wt", encoding="utf-8") as f:
            json.dump(dict(RECORD, _execution_live={"appels_par_noeud": live["appels_par_noeud"], "erreurs_par_noeud": live["erreurs_par_noeud"]}), f, sort_keys=True)
    md = ["# Aave V3 Ethereum Core : niveau 0-5 de chaque rôle lu en chaîne, bloc %d" % a.block, "",
          "**Bloc daté : %d** (`%s`), horodatage %s. Nœuds : %s. Lecture seule, aucune clé, aucune transaction." % (a.block, bi["hash"], contenu["bloc_horodatage_utc"], " + ".join(n.name for n in NODES)),
          "Grille `GRILLE.md` sha256 `%s` ; script sha256 `%s`%s." % (grille_sha, script_sha, "" if avant else " ; **NON HACHÉ AVANT (essai)**"),
          "Contenu sha256 `%s`. Début %s, fin %s UTC.%s" % (contenu["contenu_sha256"], debut, fin, " Rejeu de la cassette de la lecture réseau d'origine." if a.cassette_in else ""), ""]
    if INVALIDE:
        md += ["## RÉSULTAT INVALIDE", ""] + ["- " + x for x in INVALIDE] + [""]
    md += ["## Comment lire les chiffres", "",
           "- **Lectures en erreur ou en désaccord entre nœuds : %d.** C'est ce que ce rapport appelle « NON LU » (section en bas). Ce n'est PAS « tout est classé »." % len(NON_LU),
           "- **Actifs (%d)** : %d avec un niveau complet ; %d avec un niveau mais aussi un détenteur non classé (niveau = le plus bas des détenteurs classés) ; %d non classés, sans aucun niveau ; %d « aucun rôle lu » (absence de lecture, pas absence de pouvoir)." % (len(actifs), avec, avec_nc, nc, aucun),
           "- **Lignes (%d)** : %d portent « non lu = OUI » : un détenteur dont le mécanisme n'est pas dérivable (Aragon, registre, contrôleur illisible), ou un actif dans ce cas. Ce n'est ni un 0 ni un 5." % (len(lignes), synth["lignes_non_classees"]),
           "- **Lignes « [seuil et délai agrégés] »** : quand le détenteur est un timelock ou un contrat générique, la colonne seuil réunit TOUS les multisigs rencontrés sous lui (proposeurs, exécuteurs, contrôleurs remontés) et la colonne délai est le plus petit délai trouvé ; le niveau, lui, est celui du plus faible chemin. Exemple : BTC.b MINTER_ROLE `0x9ece..21ac` affiche « 2/11, 3/5 » et 24 h avec le niveau 0, parce qu'une EOA le tient ; le délai de 24 h n'y protège pas ce chemin. Même lecture pour USDe `minter()`.",
           "- Les journaux (`eth_getLogs`) sont lus sur UN seul nœud ; tout le reste sur deux (voir Limites).", ""]
    md += ["## Niveau par actif", ""]
    for x in actifs:
        md.append("- %s `%s` (%s) : %s%s%s" % (x["actif"], x["adresse"], x["origine"], x["statut"], " ; non classé" if x["non_lu"] else "", (" ; " + NOTES_ACTIF[x["actif"]]) if x["actif"] in NOTES_ACTIF else ""))
    md += ["", "## Tableau", "", md_table(lignes), "", "## Seuils relus avant d'écrire (sans cache, bloc daté et tête finalisée)", ""]
    if raf_note:
        md += ["*%s*" % raf_note, ""]
    md += ["| multisig | type | classé | relu au bloc daté | tête finalisée | relu en tête | mêmes propriétaires | écart |", "|---|---|---|---|---|---|---|---|"]
    for r in raf:
        md.append("| `%s` | %s | %s | %s | %s | %s | %s | %s |" % (r["multisig"], r["type"], r["classe"], r["relu_bloc_date"], r["tete_finalisee"] or "-", r["relu_tete"],
                                                               {True: "oui", False: "NON", None: "-"}[r["meme_proprietaires_tete"]], "OUI" if r["ecart_tete"] else "non"))
    md += ["", "## Témoins (avant / après, sur chaque nœud)", ""]
    for ph, ts in (("avant", t_avant), ("après", t_apres)):
        for tt in ts:
            md.append("- %s : %s sur %s -> %s (attendu %s) : %s" % (ph, tt[0], tt[1], tt[3], tt[2], "conforme" if tt[4] else "**NON CONFORME**"))
    md += ["", "## NON LU : lectures en erreur ou en désaccord (%d)" % len(NON_LU), ""] + (["- " + "%s : %s" % (w, m) for w, m in NON_LU] or ["Aucune. Les détenteurs non classés ci-dessus sont une autre chose (mécanisme hors des lectures)."])
    md += ["", "## Réponses vides par getter (fonction non servie, jamais prise pour une valeur)", "", ", ".join("`%s` ×%d" % (k, v) for k, v in sorted(VIDES.items())) or "aucune", "",
           "## Limites par actif (reprises du rapport du 13/10, non lues ici : les niveaux peuvent être SURESTIMÉS sans elles)", ""]
    md += ["- **%s** : %s" % (k, v) for k, v in LIMITES_ACTIF]
    md += ["", "## Limites propres à cette lecture", "", "- %s ; les détenteurs trouvés par les journaux sont vérifiés sur les deux nœuds par lecture d'état, mais un détenteur jamais annoncé par un événement n'est pas vu (les révocations ne sont pas lues : `hasRole` est relu au bloc)." % contenu["journaux"],
           "- Requêtes par méthode : %s. Demandes logiques par nœud : %s. Appels réseau de la lecture d'origine par nœud : %s ; **réessais** (429, 5xx ou réseau, puis succès) par nœud : %s ; erreurs finales par nœud : %s." % (json.dumps(COUNT), exe["demandes_logiques_par_noeud"], exe["appels_par_noeud"], exe["reessais_par_noeud"], exe["erreurs_par_noeud"]),
           "- La cassette garde UNE réponse par requête : les témoins « après » et les relectures sans cache du bloc daté écrasent les premières lectures. **Un rejeu ne peut donc pas reproduire un résultat INVALIDE** ; seul le comptage des appels de la lecture d'origine prouve qu'il y a eu deux passages.",
           "- Le hash de `GRILLE.md` prouve que le texte n'a pas bougé, pas que le code l'applique : les règles sont codées dans le script et vérifiées par les tests.", "",
           "## Rejouer", "", "`python3 -I mesure_aave_niveaux.py --block %d --hashes <HASHES> --cassette-in <cassette.json.gz> --out <prefixe>` (sans réseau)." % a.block, ""]
    open(a.out + ".md", "w", encoding="utf-8").write("\n".join(md))
    print("ecrit %s.json / .md ; contenu_sha256 %s ; %d lignes ; NON LU %d ; INVALIDE %d" % (a.out, contenu["contenu_sha256"], len(lignes), len(NON_LU), len(INVALIDE)))
    sys.exit(4 if INVALIDE else 0)


if __name__ == "__main__":
    main()
