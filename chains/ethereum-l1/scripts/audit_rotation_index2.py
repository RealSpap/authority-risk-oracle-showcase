#!/usr/bin/env python3
"""Audit de rotation, ethereum-l1, index 2 (run 2026-09-21).

LECTURE SEULE, ZERO DEPENDANCE. N'importe qui peut lancer ce fichier tel quel
depuis n'importe ou :

    python3 audit_rotation_index2.py

Aucun `pip install`, aucun `cast`/foundry, aucun import du depot, aucun acces a
keys/. Bibliotheque standard uniquement : keccak-256 est reimplemente ici (les
4 selecteurs de fonction sont RECALCULES, jamais codes en dur) et les appels
passent par urllib. C'est le point : le code de sortie de ce script doit porter
la preuve tout seul, sans environnement prepare.

Ce qu'il etablit :
  1. keccak-256 local correct (2 vecteurs de test connus) -- sinon exit 2 ;
  2. quelle cible est trackedTargets(2) sur l'oracle Sepolia deploye, lue sur
     DEUX RPC Sepolia independants (la cible n'est pas supposee, elle est lue) ;
  3. le score PUBLIE pour cette cible, via getScore(address) sur ces 2 RPC ;
  4. les FAITS d'autorite MakerDAO/Sky, relus depuis zero sur QUATRE RPC
     mainnet independants (delay/authority/hat/done + description/eta du spell) ;
  5. la comparaison entre le score publie et cinq constantes VERIFIEES contre
     ces faits -- pas cinq valeurs re-derivees d'une formule qui varierait
     avec ce qui est lu. msig et oracle sont les litteraux 100 (cette cible
     n'est ni un Gnosis Safe ni un signataire de prix, jamais verifie
     autrement) ; admin et timelock passent a 75 et 70 des que hat()/done()
     et delay() sont lisibles (le fait chiffre verifie est ailleurs, dans la
     liste `faits` plus bas : delay() == 172800 s). Trois des cinq dimensions
     ne peuvent donc pas diverger tant que la lecture reussit -- seul cross
     est une formule qui varie reellement avec ce que le script trouve
     on-chain (nombre d'autres cibles suivies enracinees dans Sky). Toute
     divergence, sur n'importe laquelle des cinq -> exit 1.

Codes de sortie (c'est ce qui rend l'affirmation rejouable) :
    0 = concordance totale, aucune divergence
    1 = au moins une divergence entre les constantes verifiees et le score publie
    2 = une lecture on-chain indispensable est impossible (RPC morts, adresse
        fausse) -- verification impossible, surtout pas un succes silencieux

Controles integres :
    AUDIT_FAULT_INJECT=1   force adminKey a 76 -> DOIT sortir 1 (prouve que le 0 mord)
    AUDIT_FAKE_PAUSE=0x..  remplace MCD_PAUSE par une adresse falsifiee -> DOIT sortir 2
"""
import json
import os
import sys
import urllib.request

ORACLE_SEPOLIA = "0xB6F8474ccC71AF477c31c2DF663B3942ddfbf906"
MCD_PAUSE = "0xbE286431454714F511008713973d3B053A2d38f3"
ROTATION_INDEX = 2

SEPOLIA_RPCS = [
    "https://ethereum-sepolia-rpc.publicnode.com",   # Allnodes
    "https://sepolia.gateway.tenderly.co",           # Tenderly
    "https://1rpc.io/sepolia",                       # Automata
]
MAINNET_RPCS = [
    "https://ethereum-rpc.publicnode.com",           # Allnodes
    "https://eth.drpc.org",                          # dRPC
    "https://1rpc.io/eth",                           # Automata
    "https://eth-pokt.nodies.app",                   # Nodies / Pocket
]

divergences = []
unreadable = []


# --------------------------------------------------------------------------
# keccak-256 (FIPS-202 Keccak, padding 0x01 -- PAS le padding 0x06 de SHA3-256
# de hashlib). Reimplemente ici pour que les selecteurs soient derives et non
# recopies : un selecteur faux ferait echouer le self-test ci-dessous.
# --------------------------------------------------------------------------
_RC = [
    0x0000000000000001, 0x0000000000008082, 0x800000000000808A, 0x8000000080008000,
    0x000000000000808B, 0x0000000080000001, 0x8000000080008081, 0x8000000000008009,
    0x000000000000008A, 0x0000000000000088, 0x0000000080008009, 0x000000008000000A,
    0x000000008000808B, 0x800000000000008B, 0x8000000000008089, 0x8000000000008003,
    0x8000000000008002, 0x8000000000000080, 0x000000000000800A, 0x800000008000000A,
    0x8000000080008081, 0x8000000000008080, 0x0000000080000001, 0x8000000080008008,
]
_ROT = [[0, 36, 3, 41, 18], [1, 44, 10, 45, 2], [62, 6, 43, 15, 61],
        [28, 55, 25, 21, 56], [27, 20, 39, 8, 14]]
_MASK = (1 << 64) - 1


def _rol(x, n):
    n %= 64
    return ((x << n) | (x >> (64 - n))) & _MASK


def _keccak_f(a):
    for rnd in range(24):
        c = [a[x][0] ^ a[x][1] ^ a[x][2] ^ a[x][3] ^ a[x][4] for x in range(5)]
        d = [c[(x - 1) % 5] ^ _rol(c[(x + 1) % 5], 1) for x in range(5)]
        for x in range(5):
            for y in range(5):
                a[x][y] ^= d[x]
        b = [[0] * 5 for _ in range(5)]
        for x in range(5):
            for y in range(5):
                b[y][(2 * x + 3 * y) % 5] = _rol(a[x][y], _ROT[x][y])
        for x in range(5):
            for y in range(5):
                a[x][y] = b[x][y] ^ ((~b[(x + 1) % 5][y]) & b[(x + 2) % 5][y])
        a[0][0] ^= _RC[rnd]
    return a


def keccak256(data: bytes) -> bytes:
    rate = 136
    padded = bytearray(data)
    padded.append(0x01)
    while len(padded) % rate != 0:
        padded.append(0x00)
    padded[-1] ^= 0x80
    a = [[0] * 5 for _ in range(5)]
    for off in range(0, len(padded), rate):
        block = padded[off:off + rate]
        for i in range(rate // 8):
            lane = int.from_bytes(block[i * 8:(i + 1) * 8], "little")
            a[i % 5][i // 5] ^= lane
        a = _keccak_f(a)
    out = bytearray()
    for i in range(4):  # 32 octets = 4 lanes de la premiere rangee du rate
        out += a[i % 5][i // 5].to_bytes(8, "little")
    return bytes(out)


def selector(signature: str) -> str:
    return "0x" + keccak256(signature.encode()).hex()[:8]


def keccak_self_test():
    """Sans ce test, un keccak casse produirait des selecteurs faux et donc des
    lectures vides -- le script mentirait en silence. Vecteurs publics."""
    vecteurs = [
        (b"", "c5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470"),
        (b"abc", "4e03657aea45a94fc7d47ba826c8d667c0d1e6e33a64a036ec44f58fa12d6c45"),
    ]
    for msg, attendu in vecteurs:
        got = keccak256(msg).hex()
        if got != attendu:
            print(f"KECCAK CASSE sur {msg!r}: {got} != {attendu}")
            return False
    # selecteur ERC-20 de reference, publiquement connu
    if selector("transfer(address,uint256)") != "0xa9059cbb":
        print("KECCAK CASSE: selecteur transfer(address,uint256) inattendu")
        return False
    print(f"  keccak-256 self-test OK (3 vecteurs) ; selecteurs derives, pas codes en dur")
    return True


# --------------------------------------------------------------------------
# JSON-RPC
# --------------------------------------------------------------------------
def rpc(url, method, params, retries=3):
    """Un appel JSON-RPC. `retries` couvre les coupures de reponse chunked
    (http.client.IncompleteRead) vues sur les gros payloads eth_getCode ; un
    revert EVM, lui, remonte immediatement en RuntimeError."""
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    derniere = None
    for _ in range(retries):
        try:
            req = urllib.request.Request(
                url, data=body,
                headers={"content-type": "application/json", "user-agent": "curl/8.7.1",
                         "connection": "close"},
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                payload = json.loads(resp.read())
            if "error" in payload:
                raise RuntimeError(f"{url}: {payload['error']}")
            return payload["result"]
        except RuntimeError:
            raise
        except Exception as exc:
            derniere = exc
    raise RuntimeError(f"{url}: {derniere}")


def eth_call(url, to, data):
    return rpc(url, "eth_call", [{"to": to, "data": data}, "latest"])


def call_all(urls, to, sig, argdata="", label=None, sonde_negative=False):
    """Meme appel sur TOUS les RPC. Exige l'unanimite : un RPC qui diverge est
    une divergence, un appel illisible partout est une lecture impossible.

    `sonde_negative=True` marque un appel dont on ATTEND qu'il ne reponde pas
    (ici getThreshold() sur un contrat qui n'est pas un Gnosis Safe). Une sonde
    negative sans reponse est le resultat normal : elle n'est pas comptee comme
    une lecture impossible et n'ecrit aucun mot d'erreur dans la sortie, sinon
    le journal d'affirmations porterait un faux signal d'echec a chaque run.
    """
    label = label or f"{to} {sig}"
    data = selector(sig) + argdata
    vues = {}
    for url in urls:
        try:
            vues[url] = eth_call(url, to, data)
        except Exception as exc:  # RPC mort, rate limit, revert attendu ou non
            vues[url] = f"SANS REPONSE: {type(exc).__name__}"
    ok = {u: v for u, v in vues.items() if not str(v).startswith("SANS REPONSE") and v not in ("0x", None)}
    if not ok:
        if sonde_negative:
            print(f"    sonde negative {label} : aucune reponse sur les {len(urls)} RPC, resultat attendu")
        else:
            unreadable.append(f"{label}: illisible sur les {len(urls)} RPC -> {list(vues.values())[:2]}")
        return None, 0
    distinctes = set(ok.values())
    if len(distinctes) != 1:
        divergences.append(f"{label}: RPC en desaccord {ok}")
    return sorted(distinctes)[0], len(ok)


def as_addr(word):
    return None if word is None else "0x" + word[-40:]


def as_uint(word):
    return None if word is None else int(word, 16)


def as_bool(word):
    return None if word is None else bool(int(word, 16))


def as_string(word):
    """Decodage ABI d'un `string` retourne seul."""
    if word is None:
        return None
    raw = bytes.fromhex(word[2:])
    off = int.from_bytes(raw[0:32], "big")
    ln = int.from_bytes(raw[off:off + 32], "big")
    return raw[off + 32:off + 32 + ln].decode("utf-8", "replace")


def pad_addr(addr):
    return addr.lower().replace("0x", "").rjust(64, "0")


def composite(admin, msig, timelock):
    """METHODOLOGY.md, section Aggregation: floor(.4a + .3m + .3t + .5),
    en arithmetique entiere exacte (meme formule que _composite du depot)."""
    return (4 * admin + 3 * msig + 3 * timelock + 5) // 10


# --------------------------------------------------------------------------
def main():
    global divergences, unreadable
    print("=" * 78)
    print("AUDIT DE ROTATION ethereum-l1 -- index", ROTATION_INDEX, "-- 2026-09-21")
    print("=" * 78)

    if not keccak_self_test():
        sys.exit(2)

    # --- 1. Quelle cible EST l'index 2 ? lue on-chain, pas supposee ------------
    idx_word, n_sep = call_all(
        SEPOLIA_RPCS, ORACLE_SEPOLIA, "trackedTargets(uint256)",
        hex(ROTATION_INDEX)[2:].rjust(64, "0"), label="trackedTargets(2)",
    )
    if idx_word is None:
        print("\nIMPOSSIBLE de lire trackedTargets(2) sur l'oracle Sepolia.")
        for u in unreadable:
            print(" -", u)
        sys.exit(2)
    target = as_addr(idx_word)
    print(f"\n[1] trackedTargets({ROTATION_INDEX}) = {target}   ({n_sep} RPC Sepolia d'accord)")
    if target.lower() != MCD_PAUSE.lower():
        divergences.append(
            f"l'index {ROTATION_INDEX} n'est plus MCD_PAUSE ({MCD_PAUSE}) mais {target} : "
            "la rotation ne porte pas sur la cible attendue"
        )

    # --- 2. Score PUBLIE on-chain ---------------------------------------------
    score_word, _ = call_all(
        SEPOLIA_RPCS, ORACLE_SEPOLIA, "getScore(address)", pad_addr(target), label="getScore(target)",
    )
    if score_word is None:
        print("\nIMPOSSIBLE de lire getScore() sur l'oracle Sepolia.")
        sys.exit(2)
    raw = bytes.fromhex(score_word[2:])
    mots = [int.from_bytes(raw[i * 32:(i + 1) * 32], "big") for i in range(7)]
    onchain = {"admin": mots[0], "msig": mots[1], "timelock": mots[2],
               "oracle": mots[3], "cross": mots[4], "composite": mots[5]}
    last_updated = mots[6]
    print(f"[2] score PUBLIE  = {onchain}  lastUpdated={last_updated}")

    # --- 3. Re-derivation depuis zero sur 4 RPC mainnet ------------------------
    pause = os.environ.get("AUDIT_FAKE_PAUSE", MCD_PAUSE)
    if pause.lower() != MCD_PAUSE.lower():
        print(f"!! AUDIT_FAKE_PAUSE actif : MCD_PAUSE remplace par {pause} (exit 2 attendu)")

    delay_w, n_main = call_all(MAINNET_RPCS, pause, "delay()", label="MCD_PAUSE.delay()")
    auth_w, _ = call_all(MAINNET_RPCS, pause, "authority()", label="MCD_PAUSE.authority()")
    delay_s, authority = as_uint(delay_w), as_addr(auth_w)
    if delay_s is None or authority is None:
        print("\n[3] MCD_PAUSE.delay()/authority() illisibles -- derivation IMPOSSIBLE.")
        for u in unreadable:
            print(" -", u)
        sys.exit(2)
    print(f"[3] MCD_PAUSE.delay()     = {delay_s} s ({delay_s / 86400:g} j)   ({n_main} RPC mainnet d'accord)")
    print(f"    MCD_PAUSE.authority() = {authority}  (DSChief / MCD_ADM)")

    hat_w, _ = call_all(MAINNET_RPCS, authority, "hat()", label="DSChief.hat()")
    hat = as_addr(hat_w)
    if hat is None:
        print("    DSChief.hat() illisible -- derivation IMPOSSIBLE.")
        sys.exit(2)
    done_w, _ = call_all(MAINNET_RPCS, hat, "done()", label="hat().done()")
    done = as_bool(done_w)
    desc_w, _ = call_all(MAINNET_RPCS, hat, "description()", label="hat().description()")
    eta_w, _ = call_all(MAINNET_RPCS, hat, "eta()", label="hat().eta()")
    description = as_string(desc_w)
    eta = as_uint(eta_w)
    print(f"    DSChief.hat()         = {hat}  (dernier spell executif)")
    print(f"    hat().done()          = {done}")
    print(f"    hat().eta()           = {eta}")
    print(f"    hat().description()   = {str(description)[:90]}")

    # Recoupement independant du code: le hat doit etre un CONTRAT, pas une EOA nue.
    # eth_getCode renvoie ici ~9 ko et la reponse chunked est parfois coupee par un
    # intermediaire reseau, sur n'importe lequel des 4 RPC. Quand AUCUN ne rend le
    # code, ce n'est pas une divergence : on retombe sur une preuve plus faible mais
    # suffisante, deja acquise plus haut -- une EOA nue ne peut pas repondre a
    # done()/description()/eta(), elle renverrait 0x.
    code_lens = set()
    for url in MAINNET_RPCS:
        try:
            code_lens.add(len(rpc(url, "eth_getCode", [hat, "latest"])))
        except Exception:
            pass
    if code_lens:
        print(f"    eth_getCode(hat)      = {sorted(code_lens)} hex chars ({len(code_lens)} valeur(s) distincte(s))")
        contrat = max(code_lens) > 4
        base_contrat = "eth_getCode"
    else:
        print("    eth_getCode(hat)      = non rendu par les 4 RPC ce passage (reponse chunked coupee)")
        contrat = done is not None and bool(description)
        base_contrat = "reponses a done()/description(), qu'une EOA nue ne peut pas produire"
    if len(code_lens) > 1:
        divergences.append(f"eth_getCode(hat) diverge entre RPC: {sorted(code_lens)}")

    # --- 3bis. crossExposureScore DERIVE, pas suppose --------------------------
    # Convention METHODOLOGY.md : 100 - 20 par AUTRE cible suivie partageant la meme
    # racine de signature. Ici la racine est la gouvernance Sky : MCD_PAUSE lui-meme,
    # son MCD_PAUSE_PROXY, et tout proxy dont MCD_PAUSE_PROXY est un ward.
    MCD_PAUSE_PROXY = "0xBE8E3e3618f7474F8cB1d074A26afFef007E98FB"
    racine_sky = {MCD_PAUSE.lower(), MCD_PAUSE_PROXY.lower(), authority.lower()}

    n_word, _ = call_all(SEPOLIA_RPCS, ORACLE_SEPOLIA, "trackedTargetsCount()", label="trackedTargetsCount()")
    n_tracked = as_uint(n_word) or 0
    print(f"\n[3bis] trackedTargetsCount() = {n_tracked} -- recherche des AUTRES cibles enracinees dans Sky")
    partages = []
    for i in range(n_tracked):
        if i == ROTATION_INDEX:
            continue
        w, _ = call_all(SEPOLIA_RPCS[:1], ORACLE_SEPOLIA, "trackedTargets(uint256)",
                        hex(i)[2:].rjust(64, "0"), label=f"trackedTargets({i})")
        other = as_addr(w)
        if other is None:
            continue
        rpc_m = MAINNET_RPCS[0]
        racines = set()
        for sig in ("owner()", "authority()"):
            try:
                r = as_addr(eth_call(rpc_m, other, selector(sig)))
                if r and int(r, 16):
                    racines.add(r.lower())
            except Exception:
                pass
        lie = bool(racines & racine_sky)
        if not lie:
            # 2e saut : le proxy proprietaire a-t-il MCD_PAUSE_PROXY pour ward ?
            for r in list(racines):
                try:
                    w2 = eth_call(rpc_m, r, selector("wards(address)") + pad_addr(MCD_PAUSE_PROXY))
                    if w2 and int(w2, 16) == 1:
                        lie = True
                except Exception:
                    pass
        if lie:
            partages.append((i, other))
            print(f"       index {i} {other} -> enracine dans la meme gouvernance Sky")
    cross_derive = max(0, 100 - 20 * len(partages))
    print(f"       {len(partages)} autre(s) cible suivie partage(nt) la racine Sky -> crossExposure derive = {cross_derive}")

    # --- 4. Faits que le score publie SUPPOSE (METHODOLOGY.md + scorer) --------
    # adminKey 75  = gouvernance MKR/SKY reelle et active : hat() ET hat().done() lisibles.
    # msig     100 = non applicable, DSChief/DSPause n'est pas un Gnosis Safe (pas de getThreshold()).
    # timelock  70 = delai reel de 2 jours confirme, plafonne sous 100 (pas de preuve d'absence
    #                de bypass d'urgence verifiee ce passage).
    # oracle   100 = non applicable (cette cible ne signe aucun prix).
    # cross    = 100 - 20 par autre cible suivie partageant la racine Sky (derive en [3bis]).
    thr_w, _ = call_all(MAINNET_RPCS, pause, "getThreshold()",
                        label="MCD_PAUSE.getThreshold()", sonde_negative=True)
    faits = [
        (f"MCD_PAUSE.delay() = 172800 s (2 jours)", delay_s == 172800),
        ("authority() resout vers un DSChief non nul", authority is not None and int(authority, 16) != 0),
        ("DSChief.hat() lisible (gouvernance non dormante)", hat is not None and int(hat, 16) != 0),
        ("hat().done() = True (spell deja execute, forme attendue)", done is True),
        (f"hat() est un CONTRAT, pas une EOA nue (base: {base_contrat})", contrat),
        ("le spell porte une description() lisible", bool(description)),
        ("MCD_PAUSE n'est PAS un Gnosis Safe (getThreshold() ne repond pas)", thr_w is None),
    ]
    print("\n[4] faits attendus par le score publie :")
    for label, ok in faits:
        print(f"    [{'OK   ' if ok else 'ECART'}] {label}")
        if not ok:
            divergences.append(f"fait attendu FAUX: {label}")

    # --- 5. Derivation et comparaison -----------------------------------------
    admin = 75 if (hat is not None and done is not None) else 20
    msig = 100
    timelock = 70 if delay_s is not None else 0
    if os.environ.get("AUDIT_FAULT_INJECT") == "1":
        admin = 76
        print("\n!! AUDIT_FAULT_INJECT=1 : adminKey force a 76, une divergence est attendue")
    derive = {"admin": admin, "msig": msig, "timelock": timelock,
              "oracle": 100, "cross": cross_derive}
    derive["composite"] = composite(admin, msig, timelock)

    for k in ("admin", "msig", "timelock", "oracle", "cross", "composite"):
        if derive[k] != onchain[k]:
            divergences.append(f"{k}: derive={derive[k]} != publie on-chain={onchain[k]}")
    recompute = composite(onchain["admin"], onchain["msig"], onchain["timelock"])
    if recompute != onchain["composite"]:
        divergences.append(f"composite publie incoherent avec ses propres dimensions: {recompute} != {onchain['composite']}")

    print(f"\n[5] derive live   = {derive}")
    print(f"    publie on-chain= {onchain}")

    if unreadable:
        print("\nLECTURES IMPOSSIBLES:")
        for u in unreadable:
            print(" -", u)
    if divergences:
        print("\nDIVERGENCES:")
        for d in divergences:
            print(" -", d)
        sys.exit(1)
    print("\nAUCUNE DIVERGENCE: les constantes verifiees contre les faits releves live sur")
    print(f"4 RPC mainnet reproduisent exactement le score publie pour l'index {ROTATION_INDEX} "
          f"(composite {onchain['composite']}).")
    sys.exit(0)


if __name__ == "__main__":
    main()
