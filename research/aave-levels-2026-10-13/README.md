# Aave V3 Ethereum Core : niveau 0-5 de chaque rôle lu en chaîne (13/10/2026)

**In English.** The Technical Asset Listing Framework adopted by Aave governance (July 2026) classes each privileged role of a listed asset from level 0 (single key, no delay) to level 5 (on-chain DAO governance with timelock); levels 0 and 1 are "weak". This folder reads those roles on chain for 25 of the 67 reserves of Aave V3 Core (Ethereum), plus BTC.b and USDe, at block 26,184,127, with a negative witness on every call. Read this way, five listed assets are at level 0 or 1: USDC and cbETH (single keys), USDT (MultiSigWallet 3 of 6), BTC.b (a single key, second pauser a Safe 2 of 11), USDe (single keys inside its minter contract; level 1 without it). Several assets expose no role through standard getters and six route their power through Aragon, the Vat or a registry: they are left unclassified, not called safe. Not read: 40 reserves, Aragon ACLs, the RolesAuthority of PAXGy, the freeze status of reserves. Rerun: `python3 mesure-aave-niveaux.py --block 26184127 --compact` (standard library, public RPC). The detail below is in French.

---

**Bloc figé : 26184127 (0x18f89bf)**, lu par `eth_blockNumber` sur Tenderly le 13/10/2026 vers 14:20 UTC. Tous les appels (`eth_call`, `eth_getStorageAt`, `eth_getCode`, `eth_getLogs` jusqu'à ce bloc) portent ce bloc.
Mesure en lecture seule : aucune clé, aucune transaction. Script : `mesure-aave-niveaux.py` (dans ce dossier, bibliothèque standard seulement).
Volume de la passe finale : 1 248 `eth_call`, 290 `eth_getStorageAt`, 135 `eth_getCode`, 70 `eth_getLogs`. **NON LU : 0.**

## Ce qui a été lu

- Pool Core `0x87870Bca3F3fD6335C3F4ce8392D69350B4fA4E2`, `getReservesList()` : **67 réserves**. Les **25 premières** dans l'ordre de la liste sont mesurées, comme demandé. Cet ordre est celui des inscriptions : les 25 premières sont surtout les actifs historiques (WETH à KNC). Le statut gelé ou actif de chaque réserve n'a pas été lu.
- En plus, signalés comme tels dans le tableau : **BTC.b** (réserve n° 63) et **USDe** (n° 30), listés sur Core mais hors des 25, et **USAT** et **PAXGy**, non listés sur Core, mesurés comme témoins de méthode parce qu'ils ont une fiche LlamaRisk sur Ethereum rédigée selon le cadre.
- Pour chaque jeton : slots EIP-1967 (implémentation, admin, beacon), slots ZeppelinOS (admin, implémentation), getters `owner()`, `admin()`, `minter()`, `controller()`, `authority()`, `masterMinter()`, `pauser()`, `blacklister()`, `guardian()`, `RISK_COUNCIL()`. Pour AccessControl : tous les événements `RoleGranted` du contrat (bloc 0 au bloc figé), puis `hasRole(rôle, compte)` au bloc figé pour garder les seuls détenteurs actuels, avec recoupement par `getRoleMemberCount` quand le contrat l'expose (aucun écart). Pour les jetons de type Maker : `wards` via les événements `Rely` et `LogNote rely`. Pour les FiatToken (USDC, cbETH) : en plus des rôles nommés, les minters via `MinterConfigured` puis `isMinter()`.
- Pour chaque détenteur : `eth_getCode` (vide = EOA ; préfixe `0xef0100` = EOA déléguée EIP-7702, aucune rencontrée), `getThreshold()`/`getOwners()` (Safe) ou `required()`/`getOwners()` (MultiSigWallet hérité, celui de Tether), `getModulesPaginated` (aucun Safe mesuré n'a de module), `getMinDelay()` (TimelockController OpenZeppelin, puis ses rôles PROPOSER, EXECUTOR, admin par `RoleGranted`), `delay()` + `admin()`/`owner()`/`authority()` (Timelock Compound ou DSPause), `votingPeriod()` (Governor), `hat()` (DSChief), `kernel()` (application Aragon). Un contrat qui n'est rien de cela est remonté d'un cran par ses propres contrôleurs, jusqu'à 5 crans.

## Règles de classement appliquées (à relire avant de citer un chiffre)

- 0 = EOA ; 1 = multisig dont le seuil s vérifie s ≤ n/2 ; 2 = multisig avec s > n/2 sans délai ; 3 = 2 derrière un timelock < 48 h ; 4 = idem ≥ 48 h ; 5 = DAO on-chain avec timelock.
- Un Executor Aave (lvl1 `0x5300…192a`, lvl2 `0x17Dd…6957`) compte 5 seulement si son `owner()` lu au bloc est le PayloadsController `0xdAba…aEc5` (vérifié pour les deux). Un Governor qui tient un rôle sans timelock devant est « hors grille » (aucun cas rencontré : les deux Governors vus, UNI et ENS, sont derrière un timelock de 48 h).
- Timelock : chaque proposeur et chaque admin du timelock est classé. Si le rôle EXECUTOR est restreint, un proposeur ne passe qu'avec un exécuteur : on prend le plus haut des deux niveaux (le plus faible exécuteur comptant). Une EOA ou un multisig minoritaire derrière un timelock **garde son niveau 0 ou 1** : la grille ne prévoit pas ce cas, j'ai choisi la prudence.
- Niveau de l'actif = le plus bas de tous les rôles lus. « non classé » = au moins un détenteur dont le mécanisme n'est pas dérivable par ces lectures (Aragon, registre, contrat sans contrôleur lisible) : ce n'est ni un 0 ni un 5.
- `0x0` = rôle renoncé ou vide (MKR `owner()`, 1INCH `owner()`), pas un détenteur.

## Tableau (sortie `--compact` du script : les détenteurs de même rôle et même type sont regroupés)

| actif | adresse | proxy ? | role | detenteur | type | niveau | niveau de l'actif |
|---|---|---|---|---|---|---|---|
| WETH | 0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2 | non | - | - | aucun role privilegie lu par les lectures standards | - | aucun role lu |
| wstETH | 0x7f39c581f595b53c5cb19bd0b3f8da6c935e2ca0 | non | - | - | aucun role privilegie lu par les lectures standards | - | aucun role lu |
| WBTC | 0x2260fac5e5542a773aa44fbcfedf7c193bc2c599 | non | owner() | 0xca06..beb7 | contrat <- owner() 0x972e..70de MultiSigWallet 6/10 | 2 | 2 |
| USDC | 0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48 | oui (zosAdmin,zosImpl) | proxy admin (zosAdmin) | 0x807a..95d2 | EOA | 0 | 0 |
| USDC | 0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48 | oui (zosAdmin,zosImpl) | owner() | 0xfcb1..ae3a | EOA | 0 | 0 |
| USDC | 0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48 | oui (zosAdmin,zosImpl) | masterMinter() | 0xe982..de17 | contrat <- owner() 0xc1d9..c704 EOA | 0 | 0 |
| USDC | 0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48 | oui (zosAdmin,zosImpl) | pauser() | 0x4914..8566 | EOA | 0 | 0 |
| USDC | 0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48 | oui (zosAdmin,zosImpl) | blacklister() | 0x0a06..78f9 | EOA | 0 | 0 |
| USDC | 0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48 | oui (zosAdmin,zosImpl) | minter (FiatToken) | 27 detenteurs | EOA | 0 | 0 |
| USDC | 0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48 | oui (zosAdmin,zosImpl) | minter (FiatToken) | 0x2222..c205 | contrat <- owner() 0x3c54..aab6 EOA ; pauser() 0x6fa3..e6fb EOA | 0 | 0 |
| USDC | 0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48 | oui (zosAdmin,zosImpl) | minter (FiatToken) | 0x7777..00ee | contrat <- owner() 0x2a6a..58c5 EOA ; pauser() 0x9812..5b19 EOA | 0 | 0 |
| USDC | 0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48 | oui (zosAdmin,zosImpl) | minter (FiatToken) | 0xa669..48bd | contrat <- owner() 0x162a..31b5 EOA | 0 | 0 |
| USDC | 0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48 | oui (zosAdmin,zosImpl) | minter (FiatToken) | 0xc492..e907 | contrat <- owner() 0x0143..8dc8 EOA ; pauser() 0x817a..a09f EOA | 0 | 0 |
| USDC | 0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48 | oui (zosAdmin,zosImpl) | minter (FiatToken) | 0xfd78..d002 | contrat <- owner() 0x7d15..ae0e EOA ; pauser() 0x4e89..ac69 EOA | 0 | 0 |
| DAI | 0x6b175474e89094c44da98b954eedeac495271d0f | non | wards (rely) | 0x9759..1a28 | contrat sans controleur lu (immuable ou registre non lu) | ? | non classe |
| LINK | 0x514910771af9ca656af840dff83e8264ecf986ca | non | - | - | aucun role privilegie lu par les lectures standards | - | aucun role lu |
| AAVE | 0x7fc66500c84a76ad7e9c93437bfc5ac33e2ddae9 | oui (admin1967,impl1967) | proxy admin (admin1967) | 0x86c3..b517 | contrat <- owner() 0x17dd..6957 DAO Aave Executor lvl2 (owner = PayloadsController) | 5 | 5 |
| cbETH | 0xbe9895146f7af43049ca1c1ae358b0541ea49704 | oui (zosAdmin,zosImpl) | proxy admin (zosAdmin) | 0xeee4..9577 | EOA | 0 | 0 |
| cbETH | 0xbe9895146f7af43049ca1c1ae358b0541ea49704 | oui (zosAdmin,zosImpl) | owner() | 0x4b87..ea03 | EOA | 0 | 0 |
| cbETH | 0xbe9895146f7af43049ca1c1ae358b0541ea49704 | oui (zosAdmin,zosImpl) | admin() | 0xeee4..9577 | EOA | 0 | 0 |
| cbETH | 0xbe9895146f7af43049ca1c1ae358b0541ea49704 | oui (zosAdmin,zosImpl) | masterMinter() | 0x7dd4..b77a | EOA | 0 | 0 |
| cbETH | 0xbe9895146f7af43049ca1c1ae358b0541ea49704 | oui (zosAdmin,zosImpl) | pauser() | 0x9596..dcc2 | EOA | 0 | 0 |
| cbETH | 0xbe9895146f7af43049ca1c1ae358b0541ea49704 | oui (zosAdmin,zosImpl) | blacklister() | 0xbe3c..eb0a | EOA | 0 | 0 |
| cbETH | 0xbe9895146f7af43049ca1c1ae358b0541ea49704 | oui (zosAdmin,zosImpl) | minter (FiatToken) | 0x6d44..8280 | contrat <- owner() 0x4cd6..bbe5 EOA | 0 | 0 |
| cbETH | 0xbe9895146f7af43049ca1c1ae358b0541ea49704 | oui (zosAdmin,zosImpl) | minter (FiatToken) | 0x9bf9..a372 | EOA | 0 | 0 |
| USDT | 0xdac17f958d2ee523a2206206994597c13d831ec7 | non | owner() | 0xc6cd..a828 | MultiSigWallet 3/6 | 1 | 1 |
| rETH | 0xae78736cd615f374d3085123a210448e74fc6393 | non | - | - | aucun role privilegie lu par les lectures standards | - | aucun role lu |
| LUSD | 0x5f98805a4e8be255a32880fdec7f6728c6568ba0 | non | - | - | aucun role privilegie lu par les lectures standards | - | aucun role lu |
| CRV | 0xd533a949740bb3306d119cc777fa900ba034cd52 | non | admin() | 0x4090..9968 | application Aragon (kernel 0xad06..d72d), ACL non derivee | ? | non classe |
| CRV | 0xd533a949740bb3306d119cc777fa900ba034cd52 | non | minter() | 0xd061..fce0 | contrat <- controller() 0x2f50..46bb (contrat, niveau ?) [en partie non classe] | ? | non classe |
| MKR | 0x9f8f72aa9304c8b593d555f12ef6589cc3a579a2 | non | owner() = 0x0 (renonce ou vide) | 0x0 | aucun detenteur | ? | non classe |
| MKR | 0x9f8f72aa9304c8b593d555f12ef6589cc3a579a2 | non | authority() | 0x6eeb..dfb8 | contrat sans controleur lu (immuable ou registre non lu) | ? | non classe |
| SNX | 0xc011a73ee8576fb46f5e1c5751ca3b9fe0af2a6f | non | owner() | 0xeb31..7769 | Safe 4/7 | 2 | 2 |
| BAL | 0xba100000625a3754423978a60c9317c58a424e3d | non | MINTER_ROLE | 0xf302..414f | contrat sans controleur lu (immuable ou registre non lu) | ? | non classe |
| BAL | 0xba100000625a3754423978a60c9317c58a424e3d | non | SNAPSHOT_ROLE | 0xf302..414f | contrat sans controleur lu (immuable ou registre non lu) | ? | non classe |
| UNI | 0x1f9840a85d5af5bf1d1762f925bdaddc4201f984 | non | minter() | 0x1a9c..35bc | Timelock delay() 172800 s (48 h) <- admin() 0x408e..24c3 DAO Governor (votingPeriod 40320) | 5 | 5 |
| LDO | 0x5a98fcbea516cf06857215779fd812ca3bef1b32 | non | controller() | 0xf73a..3249 | application Aragon (kernel 0xb8ff..88dc), ACL non derivee | ? | non classe |
| ENS | 0xc18360217d8f7ab5e7c516566761ea12ce7f9d72 | non | owner() | 0xfe89..44b7 | TimelockController 172800 s (48 h) <- PROPOSER 0x323a..b7e3 DAO Governor (votingPeriod 45818) ; PROPOSER 0x2acb..e051 (contrat, niveau 2) ; executeur ouvert | 4 | 4 |
| 1INCH | 0x111111111117dc0aa78b770fa6a738034120c302 | non | owner() = 0x0 (renonce ou vide) | 0x0 | aucun detenteur | ? | aucun role lu |
| FRAX | 0x853d955acef822db058eb8505911ed77f175b99e | non | COLLATERAL_RATIO_PAUSER | 0x8412..39ca | Timelock delay() 172800 s (48 h) <- admin() 0xb174..3f27 Safe 3/5 | 4 | 2 |
| FRAX | 0x853d955acef822db058eb8505911ed77f175b99e | non | DEFAULT_ADMIN_ROLE | 0xb174..3f27 | Safe 3/5 | 2 | 2 |
| FRAX | 0x853d955acef822db058eb8505911ed77f175b99e | non | COLLATERAL_RATIO_PAUSER | 0xb174..3f27 | Safe 3/5 | 2 | 2 |
| GHO | 0x40d16fc0246ad3160ccc09b8d0d3a2cd28ae6c2f | non | DEFAULT_ADMIN_ROLE | 0x5300..192a | DAO Aave Executor lvl1 (owner = PayloadsController) | 5 | 2 |
| GHO | 0x40d16fc0246ad3160ccc09b8d0d3a2cd28ae6c2f | non | FACILITATOR_MANAGER_ROLE | 0x5300..192a | DAO Aave Executor lvl1 (owner = PayloadsController) | 5 | 2 |
| GHO | 0x40d16fc0246ad3160ccc09b8d0d3a2cd28ae6c2f | non | BUCKET_MANAGER_ROLE | 0x5300..192a | DAO Aave Executor lvl1 (owner = PayloadsController) | 5 | 2 |
| GHO | 0x40d16fc0246ad3160ccc09b8d0d3a2cd28ae6c2f | non | BUCKET_MANAGER_ROLE | 0x46aa..5409 | contrat <- RISK_COUNCIL() 0x8513..4b60 Safe 2/3 ; owner() 0x5300..192a DAO Aave Executor lvl1 (owner = PayloadsController) | 2 | 2 |
| RPL | 0xd33526068d116ce69f19a9ee46f0bd304f21a51f | non | - | - | aucun role privilegie lu par les lectures standards | - | aucun role lu |
| sDAI | 0x83f20f44975d03b1b09e64809b757c47f942beea | non | - | - | aucun role privilegie lu par les lectures standards | - | aucun role lu |
| STG | 0xaf5191b0de278c7286d6c7cc6ab6bb8a73ba2cd6 | non | owner() | 0xbe63..5413 | contrat sans controleur lu (immuable ou registre non lu) | ? | non classe |
| KNC | 0xdefa4e8a7bcba345f687a2f1456f5edd9ce97202 | oui (admin1967,impl1967) | proxy admin (admin1967) | 0x5001..f559 | contrat <- owner() 0x7d4d..d9d9 (contrat, niveau ?) [en partie non classe] | ? | 2 (+ non classe) |
| KNC | 0xdefa4e8a7bcba345f687a2f1456f5edd9ce97202 | oui (admin1967,impl1967) | owner() | 0x3eb0..f650 | MultiSigWallet 3/5 | 2 | 2 (+ non classe) |
| KNC | 0xdefa4e8a7bcba345f687a2f1456f5edd9ce97202 | oui (admin1967,impl1967) | minter() | 0x7d4d..d9d9 | contrat sans controleur lu (immuable ou registre non lu) | ? | 2 (+ non classe) |
| BTC.b | 0xb0f70c0bd6fd87dbeb7c10dc692a2a6106817072 | oui (admin1967,impl1967) | proxy admin (admin1967) | 0xcee8..0095 | contrat <- owner() 0x055e..7e59 TimelockController 86400 s (24 h) <- PROPOSER 0x3f6b..a079 EOA ; PROPOSER 0x251a..4892 Safe 3/5 ; EXECUTOR 0x251a..4892 Safe 3/5 | 3 | 0 |
| BTC.b | 0xb0f70c0bd6fd87dbeb7c10dc692a2a6106817072 | oui (admin1967,impl1967) | owner() | 0x055e..7e59 | TimelockController 86400 s (24 h) <- PROPOSER 0x3f6b..a079 EOA ; PROPOSER 0x251a..4892 Safe 3/5 ; EXECUTOR 0x251a..4892 Safe 3/5 | 3 | 0 |
| BTC.b | 0xb0f70c0bd6fd87dbeb7c10dc692a2a6106817072 | oui (admin1967,impl1967) | MINTER_ROLE | 0x451c..0a2d | contrat <- owner() 0x055e..7e59 TimelockController 86400 s (24 h) <- PROPOSER 0x3f6b..a079 EOA ; PROPOSER 0x251a..4892 Safe 3/5 ; EXECUTOR 0x251a..4892 Safe 3/5 ; proxy admin (admin1967) 0x6b06..cbb1 (contrat, niveau 3) | 3 | 0 |
| BTC.b | 0xb0f70c0bd6fd87dbeb7c10dc692a2a6106817072 | oui (admin1967,impl1967) | MINTER_ROLE | 0x9ece..21ac | contrat <- CLAIMER_ROLE 0xcd1b..c01b EOA ; OPERATOR_ROLE 0xcd1b..c01b EOA ; role 0x843c3a00 0x8236..4494 (contrat, niveau 0) ; + 6 autre(s) | 0 | 0 |
| BTC.b | 0xb0f70c0bd6fd87dbeb7c10dc692a2a6106817072 | oui (admin1967,impl1967) | CLAIMER_ROLE | 0xcd1b..c01b | EOA | 0 | 0 |
| BTC.b | 0xb0f70c0bd6fd87dbeb7c10dc692a2a6106817072 | oui (admin1967,impl1967) | OPERATOR_ROLE | 0xcd1b..c01b | EOA | 0 | 0 |
| BTC.b | 0xb0f70c0bd6fd87dbeb7c10dc692a2a6106817072 | oui (admin1967,impl1967) | PAUSER_ROLE | 0x251a..4892 | Safe 3/5 | 2 | 0 |
| BTC.b | 0xb0f70c0bd6fd87dbeb7c10dc692a2a6106817072 | oui (admin1967,impl1967) | DEFAULT_ADMIN_ROLE | 0x055e..7e59 | TimelockController 86400 s (24 h) <- PROPOSER 0x3f6b..a079 EOA ; PROPOSER 0x251a..4892 Safe 3/5 ; EXECUTOR 0x251a..4892 Safe 3/5 | 3 | 0 |
| BTC.b | 0xb0f70c0bd6fd87dbeb7c10dc692a2a6106817072 | oui (admin1967,impl1967) | PAUSER_ROLE | 0xad67..fd44 | Safe 2/11 | 1 | 0 |
| USDe | 0x4c9edd5852cd905f086c759e8383e09bff1e68b3 | non | owner() | 0xe8dc..7c94 | TimelockController 86400 s (24 h) <- PROPOSER 0x3b0a..1862 Safe 5/10 ; EXECUTOR 0x3520..0e8f EOA ; 0xa075..c344 Safe 3/6 ; 0x3b0a..1862 Safe 5/10 | 1 | 0 |
| USDe | 0x4c9edd5852cd905f086c759e8383e09bff1e68b3 | non | minter() | 0xe349..62d3 | contrat <- GATEKEEPER_ROLE 0xab91..a7dc EOA ; GATEKEEPER_ROLE 0x0f56..5bd9 EOA ; GATEKEEPER_ROLE 0x4960..8996 EOA ; + 44 autre(s) | 0 | 0 |
| USAT | 0x07041776f5007aca2a54844f50503a18a72a8b68 | oui (admin1967,impl1967) | proxy admin (admin1967) | 0x3e4c..d9c7 | contrat <- owner() 0x62b3..c5cb MultiSigWallet 3/5 | 2 | 2 |
| USAT | 0x07041776f5007aca2a54844f50503a18a72a8b68 | oui (admin1967,impl1967) | owner() | 0x62b3..c5cb | MultiSigWallet 3/5 | 2 | 2 |
| PAXGy | 0x6c6494fd9962eb98b94ffa48f6679058f820700e | non | owner() | 0x0dcc..df08 | TimelockController 86400 s (24 h) <- PROPOSER 0x0000..3f2f Safe 3/5 ; EXECUTOR 0x1d60..9312 EOA ; 0x317e..a024 EOA ; 0xfbf7..1a5e EOA ; + 3 autre(s) | 3 | 3 |
| PAXGy | 0x6c6494fd9962eb98b94ffa48f6679058f820700e | non | authority() | 0xc444..99dd | contrat <- owner() 0x0dcc..df08 TimelockController 86400 s (24 h) <- PROPOSER 0x0000..3f2f Safe 3/5 ; EXECUTOR 0x1d60..9312 EOA ; 0x317e..a024 EOA ; 0xfbf7..1a5e EOA ; + 3 autre(s) | 3 | 3 |


## Niveau par actif

| actif | origine | niveau | ce qui fixe le niveau |
|---|---|---|---|
| WETH | réserve 0 | aucun rôle lu | aucun getter, aucun slot de proxy |
| wstETH | réserve 1 | aucun rôle lu | idem |
| WBTC | réserve 2 | 2 | owner = contrat Controller, dont l'owner est un MultiSigWallet 6/10 |
| USDC | réserve 3 | **0** | admin du proxy, owner, pauser, blacklister : EOA ; masterMinter = contrat dont l'owner est une EOA ; 32 minters dont 27 EOA |
| DAI | réserve 4 | non classé | seul ward = DaiJoin `0x9759…1a28`, sans contrôleur lisible (le pouvoir passe par le Vat de Maker, non lu) |
| LINK | réserve 5 | aucun rôle lu | |
| AAVE | réserve 6 | 5 | admin du proxy = ProxyAdmin dont l'owner est l'Executor lvl2 |
| cbETH | réserve 7 | **0** | admin du proxy, owner, masterMinter, pauser, blacklister : EOA |
| USDT | réserve 8 | **1** | owner = MultiSigWallet 3/6 (3 sur 6 n'est pas une majorité) |
| rETH | réserve 9 | aucun rôle lu | pouvoir Rocket Pool porté par RocketStorage, non lu par ces getters |
| LUSD | réserve 10 | aucun rôle lu | |
| CRV | réserve 11 | non classé | admin = agent Aragon (`kernel()` lisible, ACL non dérivée) |
| MKR | réserve 12 | non classé | owner = 0x0 ; authority `0x6eeb…dfb8` sans contrôleur lisible |
| SNX | réserve 13 | 2 | owner = Safe 4/7 |
| BAL | réserve 14 | non classé | MINTER et SNAPSHOT tenus par `0xf302…414f`, autorisation Balancer non lue |
| UNI | réserve 15 | 5 | minter = Timelock 48 h dont l'admin est le Governor Uniswap |
| LDO | réserve 16 | non classé | controller = application Aragon |
| ENS | réserve 17 | 4 (mécanique), 5 après lecture du bytecode | voir « écarts » plus bas |
| 1INCH | réserve 18 | aucun rôle lu | owner = 0x0 |
| FRAX | réserve 19 | 2 | DEFAULT_ADMIN et COLLATERAL_RATIO_PAUSER tenus par un Safe 3/5 sans délai |
| GHO | réserve 20 | 2 | BUCKET_MANAGER tenu aussi par le steward `0x46aa…5409`, dont le RISK_COUNCIL est un Safe 2/3 ; les autres rôles sont à l'Executor lvl1 (5) |
| RPL | réserve 21 | aucun rôle lu | |
| sDAI | réserve 22 | aucun rôle lu | |
| STG | réserve 23 | non classé | owner = contrat `0xbe63…5413` sans contrôleur lisible |
| KNC | réserve 24 | 2 (+ non classé) | owner = MultiSigWallet 3/5 ; admin du proxy et minter remontent à `0x7d4d…d9d9`, non classé |
| BTC.b | réserve 63, hors des 25 | **0** | OPERATOR_ROLE et CLAIMER_ROLE tenus par l'EOA `0xcd1b…c01b` ; second PAUSER = Safe 2/11 (niveau 1) ; upgrade et admin = timelock 24 h (niveau 3) |
| USDe | réserve 30, hors des 25 | **0** | `minter()` = contrat `0xe349…62d3` dont MINTER_ROLE et GATEKEEPER_ROLE sont tenus par des EOA ; owner = timelock 24 h dont le seul proposeur est un Safe 5/10 (niveau 1) |
| USAT | non listé, témoin | 2 | owner et owner du ProxyAdmin = MultiSigWallet 3/5, aucun délai |
| PAXGy | non listé, témoin | 3 | owner et owner de l'authority = timelock 24 h, proposeur Safe 3/5 |

## Niveaux 0 et 1 : ce que le cadre classerait « weak security configuration » aujourd'hui

Parmi les 25 premières réserves lues :

1. **USDC** : niveau 0. Le proxy admin `0x807a96288a1a408dbc13de2b1d087d10356395d2`, l'owner `0xfcb19e6a322b27c06842a71e8c725399f049ae3a`, le pauser `0x4914f61d25e5c567143774b76edbf4d5109a8566` et le blacklister `0x0a06be16275b95a7d2567fbdae118b36c7da78f9` ont un code vide au bloc figé (relu par un `curl` séparé du script).
2. **cbETH** : niveau 0, même schéma FiatToken (proxy admin, owner, masterMinter, pauser, blacklister : EOA).
3. **USDT** : niveau 1. Owner `0xc6cde7c39eb2f0f0095f41570af89efc2c1ea828`, MultiSigWallet, `required()` = 3, `getOwners()` = 6 adresses (relu par `curl`).

Réserves listées hors des 25 et mesurées : **BTC.b** (0) et **USDe** (0 par le contrat `minter()` ; 1 même sans lui, par le Safe 5/10 proposeur du timelock).

Lecture : un niveau 0 ou 1 dit seulement qu'un rôle privilégié est tenu par une clé simple ou par un multisig minoritaire. Pour USDC et cbETH, la garde peut être hors chaîne (HSM, procédures) : le cadre classe la configuration en chaîne, et c'est elle qui est lue ici. Le cadre précise aussi que pause et liste noire peuvent demander des chemins plus rapides que mint ou upgrade ; il ne les sort pas de la grille.

Les réserves 25 à 66 (42) n'ont pas été passées, sauf BTC.b et USDe : 40 restent à mesurer avec `--limit 67`.

## Écarts avec les fiches LlamaRisk et Aave Labs

Fiches lues sur governance.aave.com (API JSON de Discourse), toutes publiées par LlamaRisk sous le cadre :

| actif | fiche | ce que dit la fiche | ce qui est lu au bloc | accord |
|---|---|---|---|---|
| BTC.b | t/25652 (16/09/2026) | upgrades sous LombardTimeLock 1 jour, exécutant Multisig1 3/5 ; PROPOSER = « EOA 2, Multisig1 » ; PAUSER = « Multisig1, Multisig2 » ; OPERATOR et CLAIMER = « EOA 1 ». Synthèse : « robust administrative safeguards » | timelock `getMinDelay` = 86 400 s ; PROPOSER = EOA `0x3f6b…a079` et Safe 3/5 `0x251a…4892` ; EXECUTOR = ce Safe seul ; PAUSER = ce Safe et un Safe **2/11** `0xad67…fd44` ; OPERATOR et CLAIMER = EOA `0xcd1b…c01b` | **accord sur les faits**, la fiche ne donne pas le seuil de Multisig2 (2/11, niveau 1). **Écart de niveau** : rôle par rôle, OPERATOR et CLAIMER en EOA donnent 0, le second pauser donne 1 ; la synthèse de la fiche ne le traduit pas en niveau |
| USAT | t/25832 (12/10/2026) | proxy transparent, ProxyAdmin `0x3e4C…9C7` et owner = MultiSigWallet hérité `0x62b3…c5cb` 3 de 5 ; aucun timelock | ProxyAdmin `0x3e4c…d9c7`, owner `0x62b3…c5cb`, MultiSigWallet 3/5, aucun délai | **accord** (niveau 2) |
| PAXGy | t/25831 (12/10/2026) | TimelockController 24 h owner de tous les contrats ; Safe 3/5 `0x0000000000417626…3f2F` seul proposeur et canceller ; le Safe et ses 5 signataires peuvent exécuter ; une clé opérateur unique tient le rôle de gel sur le registre de rôles | owner `0x0dcc…df08`, 86 400 s, PROPOSER Safe 3/5 `0x0000…3f2f`, EXECUTOR ce Safe plus 5 EOA | **accord** sur la chaîne owner (niveau 3). **Non mesuré** : les rôles du RolesAuthority (clé opérateur de gel), que mes getters ne lisent pas ; par la fiche, ce rôle serait niveau 0 |
| USDe | aucune fiche Ethereum trouvée | fiches USDe sur Monad (t/25255), Avalanche (t/25669), X Layer (t/25827) : autres déploiements, autres administrateurs | voir tableau | non comparable |
| PAXG | t/25359 | actif non listé sur Core, pas mesuré | | |

Correction manuelle hors script :

- **ENS** : le script donne 4 parce que le timelock `0xfe89…44b7` (48 h, exécution ouverte à tous) a deux proposeurs, le Governor ENS `0x323a…b7e3` et le contrat `0x2acbf518b3759f6e1fa163294eda55bf1d0ae051` (owner Safe 5/8, `expiration()` = 1847389751). Le bytecode de ce second contrat contient les sélecteurs de `veto(bytes32)` et `cancel(bytes32)`, pas ceux de `schedule` ; il ne fait qu'annuler. Niveau réel : 5. Recherche de sélecteurs dans le bytecode = heuristique (un sélecteur décalé via-IR peut échapper), d'où une correction écrite à part et non codée.

## Limites (ce qu'un vert ou un chiffre ici ne prouve pas)

- Les mécanismes hors getters standards ne sont pas lus : RolesAuthority (PAXGy), ACL Aragon (CRV, LDO), Vat de Maker (DAI), autorisation Balancer (BAL), RocketStorage (rETH), custodian et Factory de WBTC, facilitateurs GHO. « aucun rôle lu » n'est pas « aucun pouvoir ».
- USDe : les MINTER_ROLE du contrat `minter()` (contrat de mint d'Ethena, nom non relu en chaîne) soumettent des ordres bornés par bloc ; le niveau 0 est mécanique, il ne mesure pas ces bornes.
- Le classement d'un timelock (règle exécuteur, prudence pour EOA derrière délai) est un choix de lecture de la grille, écrit plus haut.
- Le statut gelé ou actif de chaque réserve n'a pas été lu.
- Adoption du cadre : le fil t/24988 annonce le passage en Snapshot le 09/07/2026 ; la date d'adoption (13/07) vient de la consigne, pas relue.

## Témoins

- `getThreshold()` sur `0x000000000000000000000000000000000000dEaD` → `0x` (vide) : conforme.
- `hasRole(FACILITATOR_MANAGER_ROLE, 0x89889a04b521d4fd01b4b6f45263c117f1c6db2a)` sur GHO (adresse tirée de keccak d'une chaîne fixe) → false : conforme.
- keccak256 en pur Python vérifié au chargement du script contre keccak("") , keccak("PAUSER_ROLE"), `owner()` = 0x8da5cb5b et le topic0 de `RoleGranted`.
- Deux passes complètes du script au même bloc donnent les mêmes niveaux pour les 29 actifs.

## NON LU

Passe finale : **0 appel en erreur**. Les erreurs de fournisseur (Tenderly « rate limit exceeded » code -32005, HTTP 429) ont été absorbées par les reprises du script avant tout classement.
Pendant la mise au point : une passe d'essai a eu `eth_getCode 0xca06411bd7a7296d7dbdd0050dfc846e95febeb7` (Controller WBTC) en NON LU (HTTP 525 sur eth.llamarpc.com) ; la logique de reprise a été corrigée et l'appel relu ensuite (contrat, owner MultiSigWallet 6/10). Un recoupement sur un second fournisseur a échoué : publicnode HTTP 403 et llamarpc HTTP 525 en fin de séance ; les recoupements cités plus haut ont donc été faits par `curl` séparé sur Tenderly, pas sur un fournisseur indépendant.

## Rejouer

```
python3 mesure-aave-niveaux.py --block 26184127 --compact
```

Options : `--limit 67` pour toutes les réserves, `--no-extra` sans BTC.b, USDe, USAT et PAXGy, `--json sortie.json` pour toutes les lignes avec adresses complètes. Environ 5 minutes. Points d'accès essayés dans l'ordre : Tenderly, eth.llamarpc.com, ethereum-rpc.publicnode.com ; le proxy HTTPS de l'environnement est utilisé s'il est défini.
