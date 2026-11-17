# Rapport d'Exploration Détaillé : Règles du Jeu i151, CLI Arena, Environnement & Packaging

**Auteur** : Survey Explorer 1 (Game Rules, Arena CLI & Environment Specialist)  
**Date** : 2026-08-30  
**Statut** : Vérifié & Autoritaire (basé sur l'inspection directe des codes sources `i151_engine`, `arena_sdk` et exécutions CLI en direct).

---

## 1. Vue d'Ensemble & Architecture de l'Environnement

### 1.1 Environnement Système & Dépendances
- **OS** : Linux (x86_64)
- **Python Version** : `Python 3.14.4` (`/home/ibrahim-tomota/.platformio/penv/bin/python3`)
- **Modules Compétition & Moteur** :
  - `arena_sdk` (v0.2.10)
  - `i151_engine` (v0.2.4)
- **Dépendances & Packages Whitelistés** :
  - Packages autorisés dans l'environnement d'arène : `numpy`, `scikit-learn`, `sklearn`, `joblib`, `onnxruntime`, `torch`, `pandas`.
  - Modules internes fournis par le runtime : `arena_sdk`, `i151_engine`.
  - Environnement multi-thread BLAS/OpenMP restreint à 1 thread dans le sandbox (`OMP_NUM_THREADS=1`, `MKL_NUM_THREADS=1`, `OPENBLAS_NUM_THREADS=1`).

### 1.2 Structure du Dépôt Projet (`/home/ibrahim-tomota/mon-bot/`)
- `bot.py` : Point d'entrée principal du bot challenger (implémentation de `setup`, `decide`, `observe`, `teardown`).
- `card_tracker.py` : Module de suivi des cartes vues, des cartes non révélées et d'échantillonnage PIMC.
- `evaluator.py` : Module d'évaluation heuristique experte, pression de couleur et calcul contextuel.
- `requirements.txt` : Liste des dépendances pip (automatiquement filtrée lors du pack).
- `README.md` : Instructions de base pour l'arène.
- `mon-bot-submission.zip` : Archive de soumission générée par `arena pack .`.

---

## 2. Règles Détaillées du Jeu i151

Le jeu **i151** est un jeu de défausse tactique pour 2 à 4 joueurs (ici standardisé en 1 contre 1) utilisant un jeu de 32 cartes, combinant des éléments de 8 américain / Uno avec des cartes d'attaque, de saut, de chaînage et un système de points de pénalité cumulatifs. L'objectif ultime est d'avoir le **score le plus bas possible** à l'issue de la partie.

### 2.1 Composition du Jeu & Valeurs des Cartes
Le jeu contient **32 cartes** (4 couleurs × 8 rangs).
- **Couleurs (`Suit`)** : Pique (`SPADES` / `'S'`), Cœur (`HEARTS` / `'H'`), Carreau (`DIAMONDS` / `'D'`), Trèfle (`CLUBS` / `'C'`).
- **Rangs & Points de Pénalité (`Rank`)** :

| Rang | Nom | Symbole | Valeur Points de Pénalité | Ordre de Tri | Pouvoir / Effet Spécial |
|---|---|---|---|---|---|
| **8** | Huit | `8` | **32 pts** | 7 | **Joker Universel / Choix de Couleur** : Jouable sur n'importe quelle carte ; impose la couleur suivante. |
| **A** | As | `A` (ou `1`) | **11 pts** | 6 | **Carte d'Attaque** : Active `ace_effect_active`. L'adversaire doit contrer par As/8 ou piocher 2 cartes et passer. |
| **T** | Dix | `T` (ou `10`) | **10 pts** | 0 | Carte standard forte pénalité. |
| **9** | Neuf | `9` | **9 pts** | 1 | Carte standard. |
| **7** | Sept | `7` | **7 pts** | 2 | Carte standard. |
| **K** | Roi | `K` (ou `R`) | **4 pts** | 3 | Carte standard. |
| **Q** | Dame | `Q` (ou `D`) | **3 pts** | 5 | **Saut de Tour (`Skip`)** : En 2 joueurs, redonne immédiatement la main au joueur. **Piège mortel en fin de manche !** |
| **J** | Valet | `J` (ou `V`) | **2 pts** | 4 | Carte standard faible pénalité. |

**Total des points du jeu** : 312 points (78 points par couleur).

---

### 2.2 Déroulement d'un Match et des Manches

1. **Configuration Initiale** :
   - `target_score` : **151 points** (seuil éliminatoire).
   - `cards_per_player` : **8 cartes** distribuées au début de chaque manche.
   - En 2 joueurs : 16 cartes distribuées, 16 cartes dans la banque (`bank`).
   - Donne et premier joueur :
     * Manche 1 : Le donneur initial est `0` par défaut (`p0`), donc le premier joueur à jouer est `p1` (l'adversaire).
     * Manches suivantes : Le donneur alterne (`(dealer + 1) % 2`), et le premier joueur est `(dealer + 1) % 2`.
   - Début de manche : La table est vide (`top_card = None`, `required_suit = None`). Le premier joueur peut poser n'importe quelle carte.

2. **Structure d'un Tour de Jeu** :
   Le joueur actif a le choix entre :
   - **`PLAY_CARD`** : Jouer une carte légale.
   - **`PLAY_MULTIPLE_CARDS`** : Jouer simultanément plusieurs cartes de même rang (ou enchaînement légal Dame).
   - **`DRAW_CARD`** : Piocher (1 carte normalement, 2 cartes si sous effet d'As actif).
   - **`PASS_TURN`** : Passer son tour (autorisé uniquement après avoir pioché ou en cours de chaînage).
   - **`CHOOSE_SUIT`** : Choisir une couleur après la pose d'un 8 (si non spécifiée directement dans l'action).

3. **Légalité de Pose (`can_play_on`)** :
   - Sur table vide : Toute carte est légale.
   - Sur une carte normale : Doit correspondre à la couleur de la carte du dessus (`suit == top_card.suit`) OU au même rang (`rank == top_card.rank`) OU être un **8** (jouable partout).
   - Sous couleur imposée (`required_suit`) : Doit correspondre à la couleur demandée (`suit == required_suit`) OU être un **8**.
   - Sous effet d'As actif (`ace_effect_active`) : Seul un **As** (n'importe quelle couleur) ou un **8** peut être joué. Tout autre coup est illégal.

---

### 2.3 Mécaniques Spéciales & Combinaisons Avancées

#### A. Le Huit (`8`) — Le Joker & Imposition de Couleur
- Un 8 est jouable à tout moment, sur n'importe quelle carte (y compris sur un As ou sous une couleur imposée).
- L'action peut spécifier la couleur immédiatement (`Action.play_card(card, chosen_suit=Suit.HEARTS)`) ou dans une action séparée `CHOOSE_SUIT`.
- *Attention* : Un 8 coûte **32 points** s'il reste en main à la fin de la manche.

#### B. L'As (`A`) — L'Attaque Cumulable
- Poser un As active `ace_effect_active = True`.
- Le joueur suivant est contraint de :
  1. Contrer en posant un autre As (de n'importe quelle couleur) ou un 8.
  2. Ou exécuter `DRAW_CARD`, ce qui lui fait piocher **2 cartes** dans la banque et termine immédiatement son tour.

#### C. La Dame (`Q`) — Le Saut de Tour & Le Piège Mortel en 2 Joueurs
- Poser une Dame active `skip_next_player = True`.
- En 2 joueurs, sauter l'adversaire signifie que **le tour revient immédiatement au joueur qui vient de poser la Dame**.
- **LE PIÈGE ABSOLU DE LA DAME EN 2 JOUEURS** :
  - Si un joueur pose une Dame comme **dernière carte** de sa main (se retrouvant à 0 carte), **IL NE GAGNE PAS LA MANCHE**.
  - Le moteur de jeu intercepte ce cas (`_handle_play` dans `reducer.py`), force le joueur à piocher **1 carte de pénalité** dans la banque, et passe la main à l'adversaire !
  - **Règle d'or de l'IA** : Ne JAMAIS terminer une manche sur une Dame en 2 joueurs.
- **Combinaisons Multiples de Dames en 2 Joueurs** :
  Le moteur autorise les coups combinés suivants dans `PLAY_MULTIPLE_CARDS` :
  - Plusieurs Dames consécutives : `[Q, Q, ...]`.
  - Dames suivies de 8 : `[Q, 8]`, `[Q, Q, 8, 8]`.
  - Dames suivies d'une carte valide sur la dernière Dame : e.g. `[Q♠, K♠]` ou `[Q♥, 10♥]`.

#### D. Le Chaînage (`is_chaining`)
- Si un joueur pose une carte du même rang que la carte au sommet de la table (ou un 8), et qu'il possède encore d'autres cartes de ce même rang en main :
  - Le joueur entre en mode `is_chaining = True`.
  - Il conserve la main et peut enchaîner immédiatement la pose d'une autre carte de même rang.
  - Il peut également choisir de passer son tour (`PASS_TURN`).

---

### 2.4 Système de Scoring & Condition de Victoire

1. **Fin de Manche (`RoundPhase.ENDED`)** :
   - Une manche se termine dès qu'un joueur n'a plus aucune carte en main (sauf le cas piège de la Dame en 2J).
   - Le gagnant de la manche marque **0 point de pénalité**.
   - Le perdant se voit ajouter la somme des points de toutes les cartes restant dans sa main (`hand_score(hand)`).

2. **Bonus de Série de Victoires (`consecutive_round_wins`)** :
   - Le moteur suit le nombre de manches consécutives remportées par chaque joueur.
   - À la **3ᵉ victoire consécutive** (`consecutive_round_wins == 3`), le joueur reçoit un bonus exceptionnel de **-10 points** retranchés de son score global (`total_score -= 10`), et le compteur de série se réinitialise à 0.
   - Si l'adversaire remporte une manche, la série est brisée et retombe à 0.

3. **Fin du Match & Élimination** :
   - Un joueur est éliminé dès que `total_score >= 151`.
   - En 1v1, dès qu'un joueur atteint ou dépasse 151 points, l'autre joueur est déclaré vainqueur du match.

---

### 2.5 Contraintes Temporelles, Forfaits & Sécurité

1. **Budgets Temporels** :
   - **Timeout par décision (`decide`)** : 1000 ms par défaut (mesuré via `signal.setitimer(ITIMER_REAL)` / `SIGALRM`).
   - **Cible de performance compétitive** : Temps de calcul recommandé entre **50 ms et 300 ms** par décision (pour garantir zéro timeout sous charge processeur).
   - **Timeout global de match** : 600 000 ms (10 minutes).
   - **Limite de pas par manche** : 500 actions maximum par manche.
   - **Limite de pas par match** : 100 000 actions (200 manches × 500).

2. **Déclencheurs de Forfait Immédiat (`reason: forfeit / timeout / max_steps`)** :
   - Dépassement du temps imparti dans `decide()` (`TimeoutError`).
   - Exception Python non gérée levée dans `decide()`.
   - Renvoi d'une action qui ne figure pas dans `legal_actions`.
   - Tentative d'appliquer une action invalide.
   - Dépassement du nombre maximal de pas (boucle infinie de pioche/passe).

3. **Pénalité de Forfait** :
   - En cas de forfait, le joueur fautif prend immédiatement en pénalité les points des cartes qu'il a en main à l'instant T.
   - Le match est instantanément accordé à l'adversaire.

4. **Sandbox & Isolation Compétition (`--isolated`)** :
   - Processus enfant durci avec communication NDJSON.
   - Blocage strict de plus de 40 modules système/réseau (`os`, `sys`, `socket`, `subprocess`, `urllib`, `requests`, `ctypes`, `pickle`, `asyncio`, etc.).
   - `sys.path` figé en lecture seule (`_FrozenSysPath`).
   - Système de fichiers restreint au dossier de soumission et aux bibliothèques système.

---

## 3. Guide de la CLI Arena

L'outil `arena` (`/home/ibrahim-tomota/.platformio/penv/bin/arena`) fournit 4 sous-commandes principales :

```
usage: arena [-h] {match,test,init,pack} ...
```

### 3.1 `arena match`
Lance un match ou une série de matchs entre deux bots.

**Syntaxe** :
```bash
arena match [OPTIONS] <bot_challenger>
```

**Options clés** :
- `--vs <OPPONENT>` : Adversaire ciblé :
  - `random` / `builtin:random` (bot aléatoire)
  - `basic` / `basic_bot` (bot glouton simple)
  - `medium` / `medium_bot` (bot tactique expert)
  - `starter`, `starter-c`, `starter-java`, `starter-node`
  - Chemin vers un fichier `bot.py` ou une archive `.zip`.
- `--seed <INT>` : Seed de départ pour le générateur aléatoire (défaut `42`).
- `--games <N>` : Nombre de matchs à jouer en série (défaut `1`).
- `--random` : Tirage aléatoire de N seeds.
- `--format {text, summary, table, json}` : Format de sortie (détaillé, résumé, tableau, JSON).
- `--isolated` / `--no-isolated` : Active l'exécution dans le bac à sable sandbox NDJSON.
- `--starter {p0, p1, bot, opponent}` : Définit qui commence la manche 1 (défaut `p1`).
- `--p0-first-rate <RATE>` : Fraction de matchs où p0 commence (ex. `0.5`).
- `--decision-timeout-ms <MS>` : Override du timeout SIGALRM par coup (défaut 1000 ms).
- `--replay-out <FILE.json>` : Enregistre le replay complet au format JSON.

### 3.2 `arena test`
Smoke test rapide validant la conformité du bot contre `builtin:random`.

**Syntaxe** :
```bash
arena test bot.py
```
- Vérifie l'absence de crash, d'actions illégales, de timeouts ou de forfaits.

### 3.3 `arena pack`
Génère l'archive ZIP optimisée pour la soumission officielle sur l'arène.

**Syntaxe** :
```bash
arena pack [directory] [OPTIONS]
```

**Options clés** :
- `-o, --output <ZIP_FILE>` : Nom du fichier de sortie (défaut `<dossier>-submission.zip`).
- `--entry <ENTRY.py>` : Point d'entrée principal (défaut `bot.py`).
- `--model <PATH.pt>` : Fichier de poids Torch / modèle ML embarqué sous `model.pt`.
- Overrides pour moteurs MCTS/PIMC : `--simulations`, `--determinizations`, `--budget-ms`, `--mode`, `--value-mode`.

---

## 4. Règles & Contraintes de Packaging (`arena pack`)

1. **Détection des Dépendances Locales par AST** :
   - `arena pack` analyse statiquement l'arbre syntaxique (AST) de `bot.py`.
   - Il résout et inclut **automatiquement tous les modules Python locaux importés récursivement** (ex. `card_tracker.py`, `evaluator.py`).
   - Tout module local importé manquant provoquera une erreur `PackError`.

2. **Filtrage de `requirements.txt`** :
   - `requirements.txt` est inspecté et nettoyé : seuls les packages de la whitelist (`numpy`, `torch`, `scikit-learn`, `joblib`, `onnxruntime`, `pandas`) sont conservés.
   - Les packages internes tels que `i151-arena-sdk` sont automatiquement supprimés du ZIP.

3. **Inclusion d'Assets** :
   - Tout fichier `.pt`, `.pth`, `.onnx`, `.joblib` référencé textuellement dans le code est inclus dans l'archive.

4. **Compatibilité du ZIP** :
   - Le ZIP résultant (`mon-bot-submission.zip`) peut être testé directement par la CLI :
     ```bash
     arena match mon-bot-submission.zip --vs medium --games 10 --format summary
     ```

---

## 5. Tableaux Récapitulatifs des Spécifications

### 5.1 Features & Règles Découvertes

| # | Catégorie | Feature | Description | Entrées | Sorties | Comportement d'Erreur | Découvert Via |
|---|---|---|---|---|---|---|---|
| 1 | Moteur | `PLAY_CARD` | Jouer 1 carte sur le dessus de la pile | `Action.play_card(card, chosen_suit)` | Nouvel état de manche | Forfait si carte non possédée ou non concordante | `reducer.py`, `rules.py` |
| 2 | Moteur | `PLAY_MULTIPLE_CARDS` | Jouer plusieurs cartes de même rang (ou combo Dame) | `Action.play_multiple_cards(cards, chosen_suit)` | Nouvel état de manche | Forfait si cartes invalides ou rangs différents | `rules.py`, `reducer.py` |
| 3 | Moteur | `DRAW_CARD` | Piocher dans la banque (1 ou 2 cartes) | `Action.draw_card()` | Carte(s) ajoutée(s) à la main | Forfait si déjà pioché sans jouer/passer | `reducer.py` |
| 4 | Moteur | `PASS_TURN` | Passer son tour | `Action.pass_turn()` | Passage au joueur suivant | Forfait si tenté avant d'avoir pioché | `reducer.py` |
| 5 | Moteur | `CHOOSE_SUIT` | Imposer une couleur après avoir posé un 8 | `Action.choose_suit(suit)` | `required_suit` mis à jour | Forfait si pas de 8 actif ou suit manquant | `reducer.py` |
| 6 | Pouvoir | Joker Huit (`8`) | Jouable sur n'importe quelle carte, impose une couleur | Carte rang 8 | Change `required_suit` | Pénalité 32 pts si conservé en fin de manche | `card.py`, `reducer.py` |
| 7 | Pouvoir | Attaque As (`A`) | Force l'adversaire à contrer par As/8 ou piocher 2 | Carte rang As | `ace_effect_active = True` | Pénalité 11 pts si conservé | `reducer.py` |
| 8 | Pouvoir | Saut Dame (`Q`) | Saute le tour de l'adversaire (rejoue en 2J) | Carte rang Dame | `skip_next_player = True` | **Piège 2J** : interdit de finir la manche sur une Dame | `reducer.py`, `rules.py` |
| 9 | Pouvoir | Chaînage de rang | Conserve le tour si pose de carte de même rang | Carte même rang | `is_chaining = True` | Fin du chaînage si passe ou pose autre rang | `reducer.py` |
| 10 | Scoring | Points de pénalité | Somme des points des cartes restantes au perdant | Main du perdant | Points ajoutés au `total_score` | Défaite du match si score >= 151 | `scoring.py` |
| 11 | Scoring | Bonus de série | -10 pts au joueur qui gagne 3 manches consécutives | Compteur victoires = 3 | `total_score -= 10` | Réinitialisation de la série si manche perdue | `scoring.py` |
| 12 | Sécurité | SIGALRM Timeout | Limite de 1000 ms par coup | Temps d'exécution `decide()` | Action retournée | Forfait immédiat si > timeout | `match_runner.py` |
| 13 | Sécurité | Sandbox Isolation | Processus cloisonné sans accès réseau/FS | `--isolated` | Exécution étanche | PermissionError / Forfait si import interdit | `sandbox.py` |
| 14 | Packaging| AST Dependency Packing | Extraction transitive des modules locaux | `arena pack .` | `mon-bot-submission.zip` | PackError si fichier requis introuvable | `pack.py` |

### 5.2 Cas Limites & Invariants Observés

| # | Feature / Règle | Cas Limite / Entrée | Comportement Observé & Conséquence |
|---|---|---|---|
| 1 | Dame en 2 Joueurs | Poser une Dame comme seule et unique carte restante en main | Le joueur ne gagne PAS : il pioche 1 carte de pénalité dans la banque et la main passe à l'adversaire. |
| 2 | As sur As | L'adversaire pose un As sous un effet d'As actif | L'effet d'As reste actif (`ace_effect_active = True`) pour le joueur suivant. |
| 3 | Banque vide | Un joueur doit piocher alors que la banque est vide | La pile de cartes jouées (`played_pile`) est automatiquement recyclée dans la banque. |
| 4 | Choix de couleur direct | Poser un 8 avec `chosen_suit` spécifié dans l'action `PLAY_CARD` | La couleur est immédiatement fixée sans nécessiter d'action intermédiaire `CHOOSE_SUIT`. |
| 5 | Fin de manche simultanée | Un joueur vide sa main sur un coup multiple | La manche s'arrête instantanément, le joueur remporte la manche (0 pt). |
| 6 | Seuil 151 dépassé | Le perdant atteint 152 points sur une manche | Le match se termine immédiatement (`MatchStatus.FINISHED`), le vainqueur est désigné. |
| 7 | Forfait en cours de jeu | Bot lève une exception inattendue dans `decide()` | Forfait immédiat, la pénalité de la main actuelle est ajoutée à son score, victoire adverse. |

---

## 6. Synthèse pour la Suite du Projet

1. **Moteur d'IA (R1, R2, R3)** :
   - L'architecture PIMC Minimax avec élagage Alpha-Bêta, table de transposition et finisseur exact est parfaitement alignée avec les contraintes du moteur.
   - Les invariants clés (protection anti-Dame en 2J, conservation des 8 en début de manche, délestage préventif des grosses cartes et quête agressive du bonus -10 pts) doivent être scrupuleusement respectés.
2. **Performance & Temps d'Exécution** :
   - Le budget temps par coup de 150 ms (avec marge 50-300 ms) assure une sécurité totale vis-à-vis du timeout de 1000 ms.
3. **Packaging & Déploiement** :
   - `arena pack .` fonctionne parfaitement avec l'architecture multi-fichiers (`bot.py`, `card_tracker.py`, `evaluator.py`).

