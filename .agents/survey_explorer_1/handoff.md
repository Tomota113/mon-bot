# Handoff Report — Survey Explorer 1

## 1. Observation
1. **Environnement & CLI** :
   - Python 3.14.4 exécuté à `/home/ibrahim-tomota/.platformio/penv/bin/python3`.
   - CLI `arena` exécutable à `/home/ibrahim-tomota/.platformio/penv/bin/arena`.
   - Moteur de jeu `i151_engine` (v0.2.4) et SDK `arena_sdk` (v0.2.10) installés dans `/home/ibrahim-tomota/.platformio/penv/lib/python3.14/site-packages/`.
   - Sous-commandes `arena` vérifiées : `match`, `test`, `init`, `pack`.
2. **Règles du Jeu & Mécaniques (`i151_engine/core/` et `i151_engine/models/`)** :
   - Jeu de 32 cartes (4 couleurs : `SPADES`, `HEARTS`, `DIAMONDS`, `CLUBS` ; 8 rangs : 7, 8, 9, 10, Jack, Queen, King, Ace).
   - Points de pénalité par carte : 8 = 32 pts, As = 11 pts, 10 = 10 pts, 9 = 9 pts, 7 = 7 pts, Roi = 4 pts, Dame = 3 pts, Valet = 2 pts (`card.py:49-58`).
   - Seuil éliminatoire : `target_score = 151` (`config.py:10`). Cartes distribuées : 8 par joueur (`config.py:11`).
   - Pouvoir du 8 : Joker universel et impose une couleur (`card.py:86`, `reducer.py:154-161`).
   - Pouvoir de l'As : Active `ace_effect_active`, obligeant le joueur suivant à poser un As/8 ou à piocher 2 cartes et passer (`reducer.py:111-125`).
   - Pouvoir de la Dame : Saut du joueur suivant (`reducer.py:164-166`).
   - **Piège de la Dame en 2 Joueurs** : Poser une Dame comme dernière carte ne permet PAS de gagner ; le joueur pioche 1 carte de pénalité (`reducer.py:86-94`).
   - Bonus de série : 3 victoires consécutives accordent un bonus de -10 points (`scoring.py:160-164`).
   - Chaînage : Poser une carte de même rang que le dessus de la pile permet d'enchaîner immédiatement (`reducer.py:56-65`).
3. **Contraintes Temporelles & Forfaits (`match_runner.py`)** :
   - Timeout par coup : 1000 ms par défaut géré par `signal.setitimer(ITIMER_REAL)` (`match_runner.py:277`).
   - Forfait immédiat si `TimeoutError`, exception non interceptée, action hors `legal_actions`, ou plus de 500 pas/manche (`match_runner.py:207-219`).
4. **Packaging (`pack.py`)** :
   - `arena pack .` analyse l'AST de `bot.py`, extrait tous les modules locaux dépendants (`card_tracker.py`, `evaluator.py`), nettoie `requirements.txt`, et crée `mon-bot-submission.zip` (`pack.py:220-267`).
   - `arena match mon-bot-submission.zip --vs medium --games 2 --format summary` a été exécuté avec succès (score: 2-0).

## 2. Logic Chain
1. L'inspection des fichiers sources du moteur `i151_engine` et du SDK `arena_sdk` a fourni les définitions exactes et exhaustives des règles de jeu, des valeurs de cartes, des transitions d'états, des pénalités, des bonus de série, et des conditions de forfait.
2. Les commandes CLI réelles (`arena test`, `arena match`, `arena pack`) ont confirmé que le système local et le runtime sandbox fonctionnent conformément aux spécifications documentées.
3. Les observations confirment que le projet `mon-bot` nécessite une prise en compte impérative des cas limites : filtrage de la Dame en fin de main 2J, gestion de l'effet d'As, calcul de pression de couleur sur le 8, respect strict du budget temps [50ms, 300ms], et maintien des modules locaux sous la racine pour le packaging AST.

## 3. Caveats
- Les adversaires `builtin:minmax_d3`, `builtin:minmax_d5`, `builtin:minmax_d6` dans le catalogue `catalog.py` ont `implemented=False` dans le SDK public standard ; les adversaires disponibles pour l'évaluation locale sont `builtin:random`, `basic` (`basic_bot`), `medium` (`medium_bot`), les starters natifs et les soumissions ZIP.
- Aucun autre caveat.

## 4. Conclusion
L'exploration complète du domaine, des règles de jeu, de l'environnement, de la CLI et des contraintes de soumission est achevée avec succès et intégralement consignée dans `/home/ibrahim-tomota/mon-bot/.agents/survey_explorer_1/survey_report.md`. L'équipe de développement dispose de toutes les spécifications autoritaires requises pour construire, optimiser et valider le bot de compétition.

## 5. Verification Method
1. Tester la conformité du bot :
   ```bash
   arena test bot.py
   ```
2. Tester le match contre différents adversaires :
   ```bash
   arena match bot.py --vs random --seed 42 --games 5 --format summary
   arena match bot.py --vs basic --seed 42 --games 5 --format summary
   arena match bot.py --vs medium --seed 42 --games 5 --format summary
   ```
3. Tester le packaging et la validité de l'archive de soumission :
   ```bash
   arena pack .
   arena match mon-bot-submission.zip --vs medium --seed 42 --games 2 --format summary
   ```
4. Inspecter le rapport complet :
   ```bash
   cat /home/ibrahim-tomota/mon-bot/.agents/survey_explorer_1/survey_report.md
   ```
