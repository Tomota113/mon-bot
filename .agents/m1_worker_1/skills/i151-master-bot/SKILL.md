---
name: i151-master-bot
description: Guide et boîte à outils pour concevoir, optimiser et packager des bots de compétition de haut niveau ELO 1900+ sur l'arène i151.
---

# Guide Expert Développement i151 Arena

## Architecture Algorithmique Championne (ELO 1900+)
- **PIMC (Perfect Information Monte Carlo)** : Échantillonnage de N états cachés (mains adverses + banque) cohérents avec les cartes observées.
- **Minimax Alpha-Bêta (Profondeur 5-8)** : Évaluation exacte des réponses adverses, contres d'As et enchaînements de Dames.
- **Table de Transposition** : Cache de hachage `(phase, player_idx, hands, top_card, required_suit, ace_effect, depth)` pour élaguer instantanément les branches dupliquées.
- **Finisseur Exact de Fin de Manche** : Résolution déterministe immédiate dès que le nombre total de cartes <= 6.

## Invariants Critiques
- **Dame en 2J** : Ne JAMAIS poser une Dame si c'est la seule carte en main.
- **Débarras des pénalités** : Défausser les 8 (32 pts), As (11 pts) et 10 (10 pts) dès que l'adversaire a <= 3 cartes.
- **Bonus de série** : À 2 victoires consécutives, viser agressivement la 3e pour -10 pts.

## Workflow CLI
- Validation locale : `arena test bot.py`
- Match de référence : `arena match bot.py --vs medium --games 20 --format summary`
- Packaging soumission : `arena pack .` -> génère `mon-bot-submission.zip`
