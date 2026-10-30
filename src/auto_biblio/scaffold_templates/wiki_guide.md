# Guide de rédaction du wiki

Ce guide est lu par les skills `/wiki-plan`, `/wiki-rediger` et `/wiki-reprendre` avant
chaque rédaction. Il grandit avec les relectures : les règles tirées des remarques de revue
sont ajoutées à la dernière section, chacune avec l'exemple qui l'a motivée.

## Lecteur visé

- Un expert en data science : rigueur et intuition, pas de vulgarisation.
- On ne réexplique pas ce qu'une page de prérequis couvre déjà : on y renvoie.

## Langue

- Français. Les termes techniques consacrés restent en anglais (*embedding*, *softmax*,
  *self-attention*), en italique à leur première apparition.
- Phrases courtes, une idée par paragraphe.

## Organisation

- Une notion par fichier : `wiki/<domaine>/<notion>.md`. L'identifiant d'une notion est son
  chemin sans extension, par exemple `llm/attention`.
- `wiki/<domaine>/index.md` porte le titre du domaine et l'ordre de lecture (`order`), suivi
  d'une présentation libre. Une notion de `order` sans fichier est « prévue ».
- Toute notion appartient à l'`order` de son domaine.

## Front-matter d'une notion

```yaml
title: Mécanisme d'attention
aliases: [attention, self-attention, scaled dot-product attention]
prerequisites: [llm/embeddings]
related: [llm/multi-head-attention, llm/transformer]
themes: [agentic, rag]
updated_at: 2026-10-20
```

- `aliases` : les autres noms sous lesquels les fiches de veille citent la notion ; ils
  servent à relier les fiches au wiki.
- `prerequisites` et `related` : des notions existantes ou prévues, sans cycle de prérequis.
- `themes` : des thèmes de `config/profile.yaml`.

## Gabarit

1. Résumé de 3 à 5 lignes, juste sous le titre `# …` (obligatoire).
2. `## Intuition`
3. `## Formalisation` : équations LaTeX (`$…$`, `$$…$$`), dimensions, complexité.
4. `## Exemple pas à pas`
5. `## Pièges et idées reçues`
6. `## Variantes et évolutions`
7. `## Références fondatrices` (obligatoire) : papier fondateur, cours reconnus, documentation
   officielle, avec liens.
8. `## Mes notes` : réservée au propriétaire, jamais réécrite sans son accord explicite.

Les sections 2 à 6 sont omises quand elles n'ont pas lieu d'être.

## Notations

- Matrices en majuscules grasses (`\mathbf{Q}`, `\mathbf{K}`, `\mathbf{V}`), vecteurs en
  minuscules grasses, scalaires en italique.
- Dimensions nommées comme dans la littérature : `d_model`, `d_k`, `d_v`, `n` (longueur de
  séquence), `h` (nombre de têtes).
- Les dimensions de chaque tenseur sont toujours indiquées, par exemple
  `\mathbf{Q} \in \mathbb{R}^{n \times d_k}`.

## Illustrations

| Type | Outil | Fichier |
|---|---|---|
| flux, étapes, séquences | bloc ` ```mermaid ` dans la page | — |
| schémas d'architecture | SVG dessiné | `img/<nom>.svg` |
| graphiques calculés | script Python (matplotlib) | `img/<nom>.py` produit `img/<nom>.svg` |

- Une illustration seulement quand elle aide à comprendre.
- Chaque image a un texte alternatif et, sur la ligne suivante, une légende en italique qui
  donne sa provenance :

  ```markdown
  ![Calcul des scores d'attention](img/attention-scores.svg)
  *Scores d'attention pour une phrase de 4 tokens. Figure originale.*
  ```

- Une figure tierce n'est reprise que sous licence ouverte (CC-BY, Wikimedia Commons…), avec
  « Source : <auteur, lien>, <licence> » dans la légende. Sinon : schéma original inspiré de la
  source, légendé « Figure originale, d'après <source> », ou simple lien.

## Notebooks

- Un notebook se propose au téléchargement par un lien relatif depuis la page :
  `[notebook](code/<nom>.ipynb)`.
- Le site publie `wiki/<domaine>/code/*.ipynb` et rien d'autre de `code/` (`.py`, `.json`,
  `.pt`…). `wiki check` signale un lien vers un notebook absent.
- Tout ce qui est publié est visible par qui ouvre le site : ni secret ni donnée privée dans le
  notebook, sorties comprises.

## Règles issues des relectures

<!-- Ajoutées par /wiki-reprendre, une par remarque généralisable, avec son exemple. -->
