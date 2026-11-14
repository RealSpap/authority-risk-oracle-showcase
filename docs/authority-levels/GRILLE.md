# Grille R-1 : niveau 0-5 de chaque rôle des collatéraux Aave V3 Core (écrite et hachée AVANT la lecture)

Ce fichier est HACHÉ par `mesure_aave_niveaux.py` au démarrage (le script ne l'interprète pas : les règles sont codées dans le script et vérifiées par `test_mesure_aave_niveaux.py`). Le script refuse de lire si le sha256 de ce fichier ou du script n'est pas celui du fichier de hash donné, et le rapport recopie les hash. Changer un mot ici après le hachage = nouvelle lecture sous un autre hash, jamais une correction silencieuse du résultat.

## 1. Niveaux (cadre « Technical Asset Listing Framework » d'Aave Labs, adopté par Snapshot le 13/07/2026)

| niveau | sens |
|---|---|
| 0 | clé simple (EOA, y compris une EOA déléguée par EIP-7702), sans délai |
| 1 | multisig dont le seuil s vérifie s ≤ n/2 (sous la majorité honnête) |
| 2 | multisig avec s > n/2, sans timelock |
| 3 | multisig s > n/2 derrière un timelock < 48 h |
| 4 | multisig s > n/2 derrière un timelock ≥ 48 h |
| 5 | gouvernance DAO on-chain avec timelock |

Niveaux 0 et 1 = « weak security configuration » dans le cadre. Le cadre ne fixe pas de seuil de notation ; les choix ci-dessous sont les miens, repris à l'identique de la mesure du 13/10/2026.

## 2. Choix de grille (ce que le cadre ne dit pas)

1. **Une EOA ou un multisig minoritaire derrière un timelock garde son niveau (0 ou 1).** Le délai ne les relève pas (choix prudent).
2. **Timelock OpenZeppelin** : chaque PROPOSER et chaque TIMELOCK_ADMIN / DEFAULT_ADMIN du timelock est classé. Si EXECUTOR est restreint, un proposeur ne vaut que si son exécuteur est aussi bon : on prend le plus haut des deux niveaux (le plus faible exécuteur comptant). EXECUTOR ouvert (vide ou adresse 0x0) = ne contraint pas.
3. **Timelock Compound / DSPause** (`delay()`) : `admin()`, `owner()` et `authority()` agissent à travers le délai.
4. Un **Executor Aave** (lvl1 `0x5300a1a15135ea4dc7ad5a167152c01efc9b192a`, lvl2 `0x17dd33ed0e3dd2a80e37489b8a63063161be6957`) compte 5 seulement si son `owner()` lu AU BLOC est le PayloadsController `0xdabad81af85554e9ae636395611c58f7ec1aaec5` ; sinon non classé. Un Governor (`votingPeriod()` non nul) ou un DSChief (`hat()`) seul, sans timelock devant, est **hors grille** (non classé), jamais 5.
5. **Niveau de l'actif = le plus bas de tous ses rôles classés.** « non classé » = au moins un détenteur dont le mécanisme n'est pas dérivable par ces lectures (Aragon `kernel()`, registre, contrat sans contrôleur lisible, multisig inconnu) : ce n'est ni un 0 ni un 5, et il est marqué NON LU dans la sortie.
6. `0x0` = rôle renoncé ou vide, pas un détenteur. Un actif sans rôle lu = « aucun rôle lu » : **absence de lecture, jamais « aucun pouvoir »**.
7. Un contrat qui n'est rien de connu est remonté d'un cran par ses propres contrôleurs (`owner()`, `admin()`…), jusqu'à 5 crans ; au-delà, boucle ou profondeur = non classé.
8. Les rôles AccessControl sont les détenteurs ACTUELS : événements `RoleGranted` (bloc 0 au bloc daté) puis `hasRole` au bloc daté ; recoupés par `getRoleMemberCount` quand il existe. Pour les FiatToken, les minters sont ajoutés (`MinterConfigured` puis `isMinter`) ; pour les contrats de type Maker, `wards` (`Rely`, `LogNote rely`).

## 3. Règles de lecture (NON LU, jamais zéro)

1. **Tous les appels portent le bloc daté.** Le bloc (numéro, hash, horodatage) est lu sur les deux nœuds ; hash différent = arrêt.
2. **Deux nœuds** : chaque lecture d'état (`eth_call`, `eth_getStorageAt`, `eth_getCode`) est faite sur les deux nœuds ; **désaccord = NON LU**, jamais « l'un des deux » ni la valeur de repli.
3. **Erreur d'API, limite de débit, délai dépassé, nœud écarté = NON LU.** Pas de repli sur un troisième nœud, pas de boucle : 3 essais par appel et par nœud au plus, un nœud qui accumule 30 erreurs est écarté (ses lectures suivantes sont NON LU sans appel).
4. **Réponse vide** : un `eth_call` qui rend `0x` n'est jamais pris pour une valeur. Pour un getter (`owner()`, `getThreshold()`…) il veut dire « fonction non servie par ce contrat » (type exclu, compté et listé dans « Réponses vides ») ; pour une lecture qui devait décider (`hasRole`, `getOwners` d'un contrat déjà reconnu comme multisig, `symbol()`) il vaut NON LU. Un contrat reconnu comme multisig dont le seuil ou les propriétaires ne se lisent pas = NON LU.
5. **Témoins avant ET après la lecture, sur chaque nœud** : `getThreshold()` sur `0x000000000000000000000000000000000000dEaD` doit rendre `0x` ; `hasRole(FACILITATOR_MANAGER_ROLE, adresse aléatoire)` sur GHO doit rendre faux ; `owner()` de l'Executor lvl1 doit rendre le PayloadsController ; les deux nœuds rendent le même hash de bloc. Un témoin en échec avant = arrêt sans rien lire ; après = le résultat est déclaré INVALIDE.
6. **Journaux d'événements (`eth_getLogs`) sur UN SEUL nœud** (Tenderly) : les autres nœuds publics refusent les plages larges (10 blocs, 50 blocs, 10 000 blocs). Les détenteurs trouvés par les journaux sont ensuite vérifiés sur les deux nœuds par lecture d'état (`hasRole`, `isMinter`, `wards`) ; ce qui n'a pas de journal (un détenteur jamais annoncé par événement) n'est pas vu. C'est une limite écrite dans le rapport, pas un NON LU.
7. **Rafraîchissement des seuils avant d'écrire** (leçon Steakhouse, 2/7 → 3/9 : un seuil lu le 19/09 était périmé) : aucun seuil ne vient d'un fichier ou d'une fiche ; chaque multisig rencontré est relu SANS cache au bloc daté (doit rendre exactement le même seuil, les mêmes propriétaires) et à la tête finalisée (écart signalé : « seuil changé depuis le bloc daté »). Une relecture qui diffère du classement = résultat INVALIDE.
8. **Un seul balayage** : le script ne boucle pas, ne relance pas, ne tourne pas par fournisseur plus d'une fois par exécution.

9. **Détenteur de rôle NON LU dans un timelock** : si, pour un TimelockController, le `hasRole` d'un octroi trouvé par les journaux est NON LU (erreur, désaccord, vide), le timelock est NON CLASSÉ (jamais compté comme détenteur réel, jamais ignoré).
10. **Trois choses différentes à ne pas confondre dans les rapports** : (a) « NON LU » = lecture en erreur ou en désaccord entre nœuds ; (b) « non classé » = mécanisme que les lectures ne savent pas dériver (Aragon, registre, contrôleur illisible) ; (c) « aucun rôle lu » = aucun getter standard n'a rendu de détenteur (absence de lecture, pas absence de pouvoir). Un actif peut avoir un niveau ET un détenteur non classé (niveau = le plus bas des détenteurs classés).
11. **Colonnes seuil et délai** : pour un timelock ou un contrat générique, elles réunissent tous les multisigs rencontrés sous le détenteur (seuils) et le plus petit délai trouvé ; le niveau reste celui du plus faible chemin. Ces lignes sont marquées « [seuil et délai agrégés] ».

## 4. Périmètre

- Pool Core Aave V3 Ethereum `0x87870bca3f3fd6335c3f4ce8392d69350b4fa4e2`, `getReservesList()` au bloc daté. **Les 25 premières réserves** dans l'ordre de la liste (comme le 13/10), plus BTC.b `0xb0f70c0bd6fd87dbeb7c10dc692a2a6106817072` et USDe `0x4c9edd5852cd905f086c759e8383e09bff1e68b3` (réserves listées hors des 25), plus USAT `0x07041776f5007aca2a54844f50503a18a72a8b68` et PAXGy `0x6c6494fd9962eb98b94ffa48f6679058f820700e` (non listés sur Core, témoins de méthode des fiches LlamaRisk).
- Lecture seule : aucune clé, aucune transaction, aucun envoi. Aucun scoreur de l'oracle n'est touché ni importé.

## 5. Limites par actif (reprises du rapport du 13/10 : non lues ici, les niveaux peuvent être SURESTIMÉS)

PAXGy (RolesAuthority de l'authority non lue : le 3 est un plafond), WBTC (custodian et Factory non lus : le 2 peut être surestimé), GHO (facilitateurs non lus : le 2 peut être surestimé), USDe (bornes par bloc des ordres de mint non lues), USDC et cbETH (garde possiblement hors chaîne), rETH (RocketStorage), DAI (Vat de Maker), CRV et LDO (ACL Aragon), BAL (autorisation Balancer), statut gelé ou actif de chaque réserve. Le rapport généré les recopie.

## 6. Ce qu'un résultat ici ne prouve pas

- Un niveau décrit ce que la chaîne montre AU BLOC : pas les clés hors chaîne, pas la compromission, pas ce qui est signé hors chaîne.
- L'heuristique d'un contrat est dérivée des appels listés ; un contrat qui répond autrement (proxy exotique, ACL Aragon, registre) reste non classé.
- Le statut gelé/actif de chaque réserve n'est pas lu.
