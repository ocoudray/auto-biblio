# Sous-projet 6 — wiki de connaissances

- **Date** : 2026-10-17
- **Statut** : validé en brainstorming
- **Dépend de** : sous-projet 3 (`2026-10-10-analyse-kb-design.md`) et sous-projet 4
  (`2026-10-14-site-design.md`)
- **Suite prévue** : SP7, site éditable et prise de notes (dont les remarques sur le site) ;
  SP8, amélioration des fiches

## 1. Objectif

Construire, à côté de la veille, un **wiki du savoir établi** : une page par notion (par
exemple `llm/attention`), pédagogique, illustrée, validée par le propriétaire, et reliée aux
fiches de veille qui la font avancer.

Le wiki grandit **progressivement** : un domaine pilote d'abord (« LLM fondamentaux »), puis
les domaines suivants, choisis en s'appuyant sur les notions que la veille rencontre.

### Décisions

| Sujet | Choix |
|---|---|
| Rédaction | avec Claude Code, à la demande, par des skills ; le pipeline ne rédige jamais de page |
| Validation | une page par PR sur le repo de données ; fusionner vaut validation |
| Remarques | en revue de PR sur GitHub ; sur le site plus tard (SP7) |
| Capitalisation | un guide de style vivant (`wiki/GUIDE.md`) enrichi des règles tirées des remarques ; les skills restent stables |
| Organisation | arborescence propre au wiki (domaine → notion), indépendante des thèmes de veille |
| Initialisation | domaine pilote « LLM fondamentaux », plan validé avant les pages |
| Lien veille → wiki | étiquetage par le LLM (Flash-Lite), par lots, dans une étape hebdomadaire dédiée |
| Illustrations | Mermaid, SVG dessinés, scripts Python ; figures reprises seulement sous licence ouverte |

### Critères d'acceptation

1. Le repo de données contient `wiki/GUIDE.md` et `wiki/<domaine>/index.md` ; chaque notion
   est un fichier `wiki/<domaine>/<notion>.md` au gabarit du §3.
2. `auto-biblio wiki check` valide la structure du wiki (§5) et sort en erreur avec un message
   par problème.
3. Les skills `/wiki-plan`, `/wiki-rediger` et `/wiki-reprendre` sont installées dans le repo de
   données par `auto-biblio init` (et listées dans le guide de mise à jour) ; elles ouvrent ou
   reprennent des PR comme décrit au §4.
4. L'étape hebdomadaire `wiki link` écrit `state/wiki/links.json` et
   `state/wiki/candidates.json` ; elle ne réétiquette que les fiches nouvelles ou dont la
   signature de catalogue a changé.
5. Le site affiche une section Wiki (domaines, notions dans l'ordre de lecture), les prérequis
   et les « Nouveautés suivies » de chaque notion, une ligne « Notions » sur les fiches et une
   page « Notions à couvrir ». Les équations (LaTeX) et les diagrammes Mermaid s'affichent.
6. Un échec de `wiki link` n'empêche ni le site ni le digest.
7. `make check` passe.

### Hors périmètre

- Rédaction automatique de pages par le pipeline.
- Remarques directement sur le site : SP7.
- Signalement qu'une page validée mérite une mise à jour (nouveautés accumulées) : version
  suivante.
- Plans de domaines autres que « LLM fondamentaux » : ils se font ensuite avec `/wiki-plan`,
  sans code supplémentaire.

## 2. Flux

```
À la demande (Claude Code, repo de données)
  /wiki-plan llm ──► PR plan ──► revue ──► fusion
  /wiki-rediger  ──► PR page ──► revue ──► /wiki-reprendre <PR> ──► … ──► fusion
                                              └─► règles proposées pour GUIDE.md

Chaque semaine (weekly.yml)
  triage → analyze → wiki link → site build → site deploy → digest → commit
```

`wiki link` est en `continue-on-error`, comme `analyze`. Il ne tourne que si `wiki/` existe.

## 3. Pages du wiki

### Arborescence

```
wiki/
  GUIDE.md                  guide de style vivant
  llm/
    index.md                présentation du domaine et ordre de lecture
    attention.md
    img/                    figures et scripts qui les produisent
```

- L'identifiant d'une notion est son chemin sans extension : `llm/attention`.
- `index.md` d'un domaine contient un front-matter `title` et une liste ordonnée des notions
  du domaine (`order: [llm/tokenisation, llm/embeddings, …]`), suivie d'une présentation libre.
  Une notion listée sans fichier est « prévue ».
- Seules les pages validées sont sur `main`.

### Front-matter d'une notion

```yaml
title: Mécanisme d'attention
aliases: [attention, self-attention, scaled dot-product attention]
prerequisites: [llm/embeddings]
related: [llm/multi-head-attention, llm/transformer]
themes: [agentic, rag]
updated_at: 2026-10-20
```

`prerequisites` et `related` désignent des notions existantes ou prévues ; `themes` des
thèmes du profil.

### Gabarit du corps

1. Résumé (3 à 5 lignes), en tête.
2. `## Intuition`
3. `## Formalisation` : équations LaTeX, dimensions, complexité.
4. `## Exemple pas à pas`
5. `## Pièges et idées reçues`
6. `## Variantes et évolutions`
7. `## Références fondatrices`
8. `## Mes notes` : jamais réécrite par une skill sans accord explicite.

Les sections 2 à 7 peuvent être omises si elles n'ont pas lieu d'être ; le résumé et les
références sont obligatoires.

### Illustrations

| Type | Outil | Fichier |
|---|---|---|
| flux, étapes, séquences | Mermaid dans la page | — |
| schémas d'architecture | SVG dessiné | `img/<nom>.svg` |
| graphiques calculés | script Python (matplotlib) | `img/<nom>.py` produit `img/<nom>.svg` |

- Une illustration seulement quand elle aide à comprendre.
- Chaque figure a une légende, un texte alternatif et sa provenance : « Figure originale », ou
  la source et sa licence.
- Une figure tierce n'est reprise que sous licence ouverte (CC-BY, Wikimedia Commons…) ;
  sinon, schéma original inspiré de la source, cité (« d'après … »), ou simple lien.

## 4. Skills et guide de style

### Emplacements

| Élément | Emplacement | Évolution |
|---|---|---|
| Skills | modèles livrés par auto-biblio, copiés dans `.claude/skills/` du repo de données par `auto-biblio init` | avec les versions d'auto-biblio |
| `wiki/GUIDE.md` | repo de données | à chaque relecture |

### `/wiki-plan <domaine>`

Propose `wiki/<domaine>/index.md` : notions, prérequis, ordre de lecture, en s'appuyant sur
des cours de référence et sur `state/wiki/candidates.json`. Ouvre une PR.

### `/wiki-rediger [notion]`

1. Sans argument : prend la première notion de l'ordre de lecture qui n'a pas de page et dont
   les prérequis ont tous une page.
2. Lit `wiki/GUIDE.md`, les pages des prérequis et les fiches liées (`state/wiki/links.json`).
3. Cherche des sources de référence sur le web (papier fondateur, cours reconnus,
   documentation officielle).
4. Rédige la page au gabarit, avec ses illustrations ; exécute les scripts de figures.
5. Lance `auto-biblio wiki check` et le build du site ; corrige jusqu'à ce qu'ils passent.
6. Ouvre une PR dont la description liste les sources consultées et les points à vérifier en
   priorité.

### `/wiki-reprendre <PR>`

1. Lit les commentaires de revue de la PR.
2. Applique chaque remarque et répond sur chaque fil (« corrigé dans <commit> » ou pourquoi
   non).
3. Propose, dans un commit séparé de la même PR, les règles généralisables à ajouter à
   `wiki/GUIDE.md`, chacune avec l'exemple qui l'a motivée. Le propriétaire garde ou retire ce
   commit avant de fusionner.

### Guide initial

Le guide de départ contient : le gabarit, le niveau visé (expert en data science : rigueur et
intuition, pas de vulgarisation), la langue (français, termes techniques en anglais), les
notations (matrices en majuscules grasses, `d_model`, `d_k`, dimensions toujours indiquées) et
les règles d'illustration du §3.

## 5. `auto-biblio wiki check`

Vérifie, et liste chaque problème avec le fichier concerné :

- front-matter de chaque notion et de chaque `index.md` conforme au §3 ;
- `prerequisites`, `related` et `order` désignent des notions existantes ou prévues ;
- pas de cycle dans les prérequis ;
- `themes` désigne des thèmes du profil ;
- résumé et `## Références fondatrices` présents ;
- images référencées présentes, chacune avec une légende contenant sa provenance ;
- chaque notion appartient à l'`order` de son domaine.

Code de sortie 1 en cas de problème. La skill de rédaction le lance avant d'ouvrir la PR, et
un workflow du repo de données (`wiki-check.yml`, déclenché sur les PR qui touchent `wiki/`)
le relance avec le build strict du site.

## 6. Étape `wiki link`

### Entrées et sorties

- **Catalogue** : pour chaque notion, identifiant, titre et alias. Sa **signature** est le
  SHA-256 du catalogue trié.
- **Fiches à traiter** : les fiches absentes de `links.json`, ou dont la signature enregistrée
  diffère de la signature courante.
- **Appel** : rôle `wiki_link` (chaîne `[flash-lite, flash-lite-3.1, gemma]`), lots de
  `batch_size` fiches (20 par défaut). Pour chaque fiche : titre, résumé et contribution. Sortie
  par fiche : `notions` (identifiants du catalogue ; les inconnus sont ignorés) et `missing`
  (au plus 3 concepts sans page).
- **`state/wiki/links.json`** : par fiche, ses notions et la signature utilisée.
- **`state/wiki/candidates.json`** : par concept normalisé (minuscules, espaces réduits), le
  nombre de fiches, la première et la dernière date, trois fiches d'exemple. Un concept égal à
  un alias ou un titre du catalogue n'est pas candidat : il est ajouté aux notions de la fiche.

### Budget et erreurs

- Le budget hebdomadaire de tokens est partagé avec le triage et l'analyse.
- Un lot en échec laisse ses fiches à traiter la semaine suivante ; l'étape écrit ce qu'elle a
  obtenu, consigne une dégradation et sort en succès.
- Sans `wiki/`, l'étape ne fait rien.

## 7. Site

- **Navigation** : section « Wiki » ; un sous-menu par domaine, avec l'index du domaine puis
  les notions existantes dans l'ordre de lecture.
- **Page de notion** : sous le titre, une ligne « Prérequis » (liens) ; en fin de page,
  « Nouveautés suivies » : les fiches liées, de la plus récente à la plus ancienne. Cette
  section est générée au build, jamais écrite dans le fichier.
- **Index de domaine** : la liste ordonnée, les notions prévues sans lien et marquées
  « à rédiger ».
- **Fiche de veille** : une ligne « Notions » avec des liens vers les pages.
- **« Notions à couvrir »** : les candidats triés par nombre de fiches.
- **Rendu** : extension Markdown des mathématiques (`pymdownx.arithmatex`) avec MathJax, et
  blocs Mermaid. Le plan vérifie que zensical les rend ; sinon il propose une alternative
  avant d'implémenter.
- Les figures de `wiki/<domaine>/img/` sont copiées avec les pages.

## 8. Modules

| Module | Rôle | Entrées-sorties |
|---|---|---|
| `domain/wiki/pages.py` | modèles `NotionMeta`, `DomainIndex`, `Notion` ; lecture d'une page | aucune |
| `domain/wiki/check.py` | règles du §5 sur un wiki chargé | aucune |
| `domain/wiki/catalog.py` | catalogue, signature, normalisation des concepts | aucune |
| `domain/wiki/links.py` | fiches à traiter, fusion des résultats, candidats | aucune |
| `llm/prompts/wiki_link_v1.py` | tâche `wiki_link` | aucune |
| `store/wiki.py` | lecture de `wiki/`, lecture et écriture de `state/wiki/` | fichiers |
| `stages/wiki_link.py` | étape hebdomadaire | via les stores et le LLM |
| `domain/website/` | pages et navigation du wiki, « Nouveautés suivies », « Notions à couvrir », ligne « Notions » des fiches | aucune |
| `website/builder.py` | extensions maths et Mermaid, copie des figures | fichiers |
| `cli.py` | `wiki check`, `wiki link` | point d'entrée mince |
| `scaffold_templates/` | skills, `wiki/GUIDE.md`, étape `wiki link`, chaîne `wiki_link`, workflow `wiki-check.yml` | — |

## 9. Tests

- Domaine : lecture des pages et des index ; chaque règle de `wiki check` sur un cas valide et
  un cas invalide ; signature stable à l'ordre près ; sélection des fiches à traiter ;
  normalisation et fusion des candidats ; alias transformé en lien.
- Prompt : sortie validée, identifiants inconnus ignorés, `missing` limité à 3.
- Étape : runner LLM simulé ; un lot en échec laisse ses fiches à traiter ; sans `wiki/`, rien
  n'est écrit.
- Site : pages du wiki, navigation, « Nouveautés suivies », « Notions à couvrir », ligne
  « Notions » ; build strict avec une équation et un bloc Mermaid.
- CLI : `wiki check` (code 0 et 1), `wiki link`.
- Scaffold : skills, guide, étape `wiki link` et workflow `wiki-check.yml` présents.

## 10. Documentation et version

- `docs/wiki.md` : organisation, gabarit, boucle de relecture, skills.
- `docs/upgrade-0.7.md`.
- Version 0.7.0.
