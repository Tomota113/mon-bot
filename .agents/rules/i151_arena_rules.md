---
description: Règles fondamentales et contraintes tactiques pour le jeu i151 Arena
always_on: true
---

# Invariants & Stratégies Critiques i151 Arena

## 1. Contraintes Techniques & Sandbox Serveur (Règlement Officiel)
- **Temps de décision serveur** : **400 ms max par décision** (et non 1000 ms). Le bot doit cibler **80–180 ms** avec un coupe-circuit strict à **250 ms** pour garantir 0 forfait/timeout.
- **Taille ZIP maximale** : **50 Mo**. Possibilité d'embarquer des tables précalculées, ouvertures ou structures d'inférence compactes.
- **Interdictions strictes sous peine de forfait** :
  - `eval()`, `exec()`, `pickle.load`, `torch.load(weights_only=False)`.
  - Tout accès réseau (`requests`, `socket`, `ssl`, `asyncio`).
  - Lecture hors du dossier de soumission (`/dev/shm`, `/etc`, `/proc`).
  - Décision illégale, crash ou timeout -> forfait immédiat.
- **Critère de classement officiel** : Le podium est déterminé par le **NOMBRE TOTAL DE VICTOIRES** (l'Elo K=32 est l'indicateur de puissance).

## 2. Invariants de Jeu & Gestion des Cartes Clés
1. **Conservation Sacrée des 8 en Début de Manche** :
   - Interdiction formelle de jouer un 8 si la main compte >= 5 cartes et qu'une carte naturelle est jouable.
   - Les 8 sont des jokers universels et des pare-feux contre les As ; les gaspiller prématurément entraîne une famine de pioche et la défaite.
2. **Délestage d'Urgence Intra-Manche** :
   - Le délestage des cartes lourdes (8 à 32 pts, As à 11 pts, 10 à 10 pts) ne s'active **que si l'adversaire a <= 3 cartes** ou si notre main a <= 2 cartes. Jamais sur un score global de match.
3. **Règle de Fin sur la Dame en 2 Joueurs** :
   - Interdiction absolue de poser une Dame comme dernière carte en duel 2J (pénalité de pioche forcée de 1 carte et passe le tour).
   - En revanche, jouer une Dame quand il reste d'autres cartes en main saute le tour adverse et offre un tempo décisif.
4. **Combos Multi-Cartes (Paires / Triples / Quadruples)** :
   - Poser plusieurs cartes de même rang en un coup réduit la main 2x à 3x plus vite et neutralise l'adversaire.
5. **Chasse aux Victoires Consécutives (-10 pts)** :
   - À 2 victoires consécutives (consecutive_round_wins == 2), jouer en mode ultra-offensif pour empocher la réduction de -10 points au score du match.
   - Si l'adversaire a 2 victoires consécutives, casser sa série en priorité.
6. **Pression & Famine des Couleurs sur un 8** :
   - Mémoriser l'historique complet de la manche pour identifier les couleurs désertées par l'adversaire et lui imposer systématiquement une couleur manquante.
