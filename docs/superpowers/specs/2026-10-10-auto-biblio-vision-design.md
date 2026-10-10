# Auto Biblio Recap — vision d'ensemble

- **Date** : 2026-10-10
- **Statut** : validé en brainstorming, en attente de relecture
- **Portée** : vision globale et découpage. Chaque sous-projet a sa propre spec détaillée
  (le sous-projet 1 : `2026-10-10-socle-collecte-design.md`).

## 1. Intention

Me maintenir à l'état de l'art en IA avec un effort humain minimal, en croisant la littérature
académique (papiers) et appliquée (outils, librairies, repos, blogs, releases), et en filtrant
agressivement le bruit selon mes centres d'intérêt.

Utilisateur unique : moi. Pas de multi-utilisateur, pas de produit public.

### Critères de succès

1. Chaque semaine, un digest lisible en 5 à 10 minutes, qui me signale ce qui compte vraiment
   dans mes thèmes, y compris les sujets qui reviennent au goût du jour.
2. Une base de connaissances consultable qui condense l'état de l'art par thème et donne les
   bons liens pour approfondir, et qui s'enrichit sans intervention de ma part.
3. Une exploration interactive d'un sujet en quelques minutes, adossée à cette base.
4. Une automatisation qui tourne sans surveillance, se dégrade proprement en cas de panne et
   me signale les problèmes, avec un coût LLM maîtrisé (quelques euros par mois, ou un quota
   gratuit).

## 2. Livrables

| Livrable | Forme | Fréquence |
|---|---|---|
| Digest | mail HTML court, avec liens vers le site | hebdomadaire (dimanche matin) |
| Site | base de connaissances navigable : pages thème, fiches, archive des digests | mis à jour à chaque exécution hebdomadaire |
| Assistant | Claude Code en local dans le repo de données, avec skills dédiées | à la demande |

## 3. Profil d'intérêts

Le profil est **déclaratif** (YAML versionné) en v1. Un feedback léger viendra l'ajuster en v2
(approche hybride, voir §11).

Thèmes initiaux :

| id | Thème | Signaux typiques |
|---|---|---|
| `agentic` | Architectures agentiques | orchestration multi-agents, harness, skills, tools, MCP, mémoire, évaluation d'agents |
| `rag-scale` | RAG à l'échelle | retrieval hybride, reranking, GraphRAG, indexation de gros corpus, évaluation RAG |
| `tabular-fm` | Modèles fondation tabulaires vs AutoML | TabPFN, TabICL, CARTE… comparés à AutoGluon, FLAML |
| `llm-arch` | Architectures LLM/VLM | SSM/Mamba, JEPA, MoE, attention linéaire, architectures hybrides |
| `ai-dev-practices` | Bonnes pratiques de dev IA | outillage Python sur base Rust (uv, ruff, polars, pydantic, pydantic-ai), patterns de prod |
| `vlm-vs-ocr` | Multimodal dans les VLM vs OCR | VLM sur documents, comparés aux pipelines OCR |
| `doc-dataification` | Dataification de documents | OCR avec prise en compte de la structure, parsing de layout, tableaux, Docling, Marker |

Chaque thème déclare : `label`, `weight`, `description` (ancre sémantique embeddée),
`keywords`, `exclude` et `watch` (repos et auteurs suivis). Le profil contient aussi un
`global_exclude`.

## 4. Sources

La liste des sources est **extensible par configuration** (`config/sources.yaml`). Ajouter une
instance d'un type existant (un flux RSS, une catégorie arXiv, un subreddit) ne demande que de
la configuration. Un nouveau type de source demande un connecteur, c'est-à-dire une nouvelle
implémentation du `Protocol` `Source`.

| Famille | Sources v1 |
|---|---|
| Académique | arXiv (cs.CL, cs.LG, cs.CV, cs.AI), Hugging Face Daily Papers, Semantic Scholar (citations, pour l'enrichissement) |
| Appliqué | GitHub (repos montants, releases des repos suivis), blogs des labs et éditeurs (RSS), modèles tendance du Hugging Face Hub |
| Communautaire | Hacker News (API Algolia), Reddit r/MachineLearning et r/LocalLLaMA (RSS), newsletters (RSS : The Batch, Import AI, Latent Space, Simon Willison…) |

Exclus : X/Twitter et LinkedIn (API fermées, scraping fragile). Papers with Code n'est plus
une source autonome : ses liens papier ↔ code passent par Hugging Face Papers.

## 5. Architecture

### 5.1 Deux repos

- **`auto-biblio`** (ce repo, code) : librairie Python et CLI, sans aucune donnée. Développée
  selon `CLAUDE.md` (domaine pur, pyright strict, couverture ≥ 90 %).
- **`auto-biblio-data`** (privé) : configuration, état du pipeline, base de connaissances,
  workflows GitHub Actions et secrets. Les workflows installent la CLI en version épinglée
  (`uv tool install git+https://github.com/ocoudray/auto-biblio@<tag>`). Une évolution du code
  ne change donc la veille qu'après une montée de version volontaire.

Structure du repo de données :

```
auto-biblio-data/
├── config/            profile.yaml · sources.yaml · llm.yaml
├── state/             items/  signals/  cursors.json  llm_cache/  runs/
├── kb/                themes/  entities/{papers,tools,techniques}/  digests/  changelog/
├── CLAUDE.md + .claude/skills/
└── .github/workflows/ daily.yml · weekly.yml
```

### 5.2 Approche : un pipeline piloté par le code, le LLM traité comme une fonction

Python orchestre tout de façon déterministe. Chaque appel au LLM est une fonction : entrées
typées, prompt versionné, sortie validée par un modèle Pydantic. Le LLM ne décide jamais du
flux. Approches écartées :

- **Pipeline piloté par un agent** : coût imprévisible et non-déterminisme, incompatibles avec
  l'objectif de fiabilité.
- **Hybride avec un agent pour l'analyse approfondie** : réintroduit l'imprévisibilité là où on
  consomme le plus. L'exploration de type agent est réservée à l'assistant local.

### 5.3 Flux

```
QUOTIDIEN (aucun appel LLM)
  collecte → normalisation en Item → dédoublonnage → enregistrement des signaux
  → embeddings locaux → pré-score → commit de state/

HEBDOMADAIRE (samedi nuit, budget plafonné)
  sélection : candidats de la semaine + revenants
  → triage LLM (lots) → analyses (approfondies et courtes)
  → mise à jour de kb/ (fiches + 1 page thème en rotation) + changelog
  → digest → commit → build du site → déploiement → mail
```

Chaque étape lit ses entrées dans `state/` et y écrit ses sorties. Les étapes sont donc
**rejouables et idempotentes**.

### 5.4 Découpage du package

| Module | Rôle | E/S |
|---|---|---|
| `domain/` | modèles, scoring, dédoublonnage, budget, sélection, erreurs | aucune (pur) |
| `sources/` | un connecteur par type de source (`Protocol` `Source`) | réseau |
| `llm/` | port `StructuredLLM`, adaptateur pydantic-ai, chaînes de modèles, cache, prompts versionnés | réseau |
| `embeddings/` | port `Embedder`, implémentation locale | modèle local |
| `store/` | lecture et écriture du repo de données | fichiers |
| `stages/` | une classe par étape, dépendances injectées | orchestration |
| `publish/` | rendu du site et du mail, envoi SMTP | réseau |
| `cli.py` | points d'entrée minces | — |

## 6. Entonnoir et scoring

| Étage | Volume hebdomadaire indicatif | Traitement | Coût LLM |
|---|---|---|---|
| 0. Collecte | 3 000 à 5 000 items | API, RSS | nul |
| 1. Pré-filtre | → 40 à 60 candidats | embeddings locaux + signaux + règles du profil | nul |
| 2. Triage | → 15 à 20 retenus | LLM du rôle `triage`, titre et résumé, par lots | faible |
| 3. Analyse | 3 à 6 approfondies + fiches courtes | LLM des rôles `deep_analysis` / `short_note` | principal |
| 4. Synthèse | 1 digest + 1 page thème | LLM du rôle `synthesis`, à partir des fiches | modéré |

Les volumes et plafonds de chaque étage sont **paramétrables**.

**Pré-score (pur, sans LLM) :**

```
pre = max_t( weight_t × sim(embed(item), embed(theme_t)) )
    + α × buzz(signals)          # vélocité normalisée (log)
    + β × multi_source           # vu à au moins deux endroits
    + bonus_watch − penalty_exclude
```

**Revenants :** items de plus de 30 jours dont la vélocité d'un signal (étoiles, citations,
nouveau fil HN, release majeure) dépasse un seuil. Ils réintègrent la sélection et portent
l'étiquette « revient au goût du jour ».

**Triage LLM :** pour chaque item, pertinence par thème (0 à 5), nouveauté, type (avancée,
outil, état de l'art, opinion) et justification en une phrase. Le score final combine le
pré-score et la pertinence LLM. La sélection applique un **quota de diversité** (N items au
plus par thème).

## 7. Couche LLM, agnostique du fournisseur

- **Port** `StructuredLLM.run(LLMTask[T]) -> LLMResult[T]`. Une tâche porte un rôle, un prompt
  versionné, des entrées et un type de sortie Pydantic. Le résultat porte la sortie validée,
  la consommation, le modèle effectivement utilisé et le coût estimé.
- **Implémentation v1 : pydantic-ai.** Elle couvre Anthropic, Google (Gemini, Gemma avec quota
  gratuit), les modèles locaux compatibles OpenAI (Ollama, LM Studio, vLLM), Mistral, Groq et
  OpenRouter. Notre adaptateur ajoute le cache, le budget et la bascule de secours.
- **Rôles** `triage`, `short_note`, `deep_analysis`, `synthesis`. Chaque rôle a une **chaîne de
  modèles** (`config/llm.yaml`), et on passe au modèle suivant sur quota atteint,
  indisponibilité ou sortie invalide après une nouvelle tentative. Chaque bascule est
  journalisée et signalée dans le digest.
- **Catalogue de modèles** : identifiant, coût par million de tokens (0 pour un quota gratuit),
  limites de requêtes, taille de lot conseillée.
- **Prompts portables** : aucune fonctionnalité propre à un fournisseur dans les prompts. Les
  optimisations (cache de prompt, Batches API) sont activées dans l'adaptateur quand le
  fournisseur les supporte.
- **Cache** indexé par `hash(prompt_version, model_id, entrée)`.
- **Configuration par défaut v1** : quota gratuit Gemma/Gemini pour le triage et les fiches
  courtes, Claude Haiku en secours, Claude Sonnet pour l'analyse approfondie et la synthèse,
  avec une clé API facturée à l'usage. Ordre de grandeur estimé : quelques dollars par mois.
  Les identifiants, tarifs et quotas sont à vérifier au moment de l'implémentation.
- **Modèles locaux** : possibles par configuration, mais les runners GitHub (processeur seul)
  ne font tourner que de petits modèles. Un vrai modèle local suppose un runner auto-hébergé.
  Ce n'est pas l'objectif de la v1.
- **Abonnement Claude Pro** : réservé à l'assistant local. Un adaptateur `claude -p` reste
  possible, mais il n'est pas prévu : `--bare` n'accepte pas l'authentification par abonnement,
  et l'usage automatisé de l'abonnement est une zone grise des conditions d'utilisation.

## 8. Base de connaissances

- **Pages thème** (une par thème) : concepts clés, approches dominantes, outils de référence,
  questions ouvertes, liens pour approfondir. Une page est réécrite par semaine, en rotation.
  Règle de conservation : ne jamais retirer un lien existant sans justification explicite.
- **Fiches entité** (papier, outil, technique), une par entité et non par mention. Front-matter
  validé par Pydantic (`id`, `kind`, `themes`, `links`, `related`, `first_seen`, `last_signal`,
  `depth`), puis corps Markdown (résumé, contribution, limites, liens).
- **Digests datés** et **changelog** hebdomadaire.
- **Autonomie totale** : le pipeline commite directement. Le digest contient une section
  « Évolutions de la base » avec un diff résumé, et l'annulation se fait par revert git.

## 9. Fiabilité, erreurs et budget

- **Budget** : double plafond hebdomadaire, en dollars (modèles payants) et en tokens (quotas
  gratuits). Le `BudgetLedger` (pur) réserve une estimation avant chaque appel et enregistre le
  coût réel après.
- **Ordre de dégradation** quand le budget manque : triage, puis digest, puis analyses
  approfondies, puis réécriture de page thème. Un digest sort toujours, au pire en version
  brute.
- **Taxonomie d'erreurs** (`domain/errors.py`) :

| Erreur | Réaction |
|---|---|
| `ConfigError` | échec immédiat de l'exécution (seul cas de workflow rouge) |
| `SourceUnavailableError`, `SourcePayloadError` | la source est ignorée pour cette exécution, les autres continuent ; le payload fautif est mis en quarantaine ; le digest signale une source en échec depuis N jours |
| `ProviderQuotaError`, `ProviderUnavailableError` | bascule vers le modèle suivant de la chaîne ; si la chaîne est épuisée, arrêt propre de l'étape et reprise à l'exécution suivante |
| `LLMOutputInvalidError` | une nouvelle tentative avec l'erreur de validation, puis modèle suivant, puis abandon de l'item ou du lot |
| `BudgetExhaustedError` | dégradation selon l'ordre ci-dessus |
| `ExtractionError` | repli sur le résumé, fiche marquée `depth: short` |

- **Observabilité** : journal d'exécution `state/runs/` (volumes par étage, tokens et coûts par
  rôle, erreurs, bascules) et pied de page « santé du pipeline » dans chaque digest.
- **Surveillance** : GitHub notifie l'échec d'un workflow. Le workflow quotidien envoie une
  alerte si aucun digest n'est sorti depuis 8 jours.
- `weekly --dry-run` exécute tout sauf l'envoi du mail et le déploiement.

## 10. Publication et assistant

- **Site** : généré avec zensical (déjà dans le template), à partir de `kb/`. Déployé sur
  Cloudflare Pages avec un accès protégé (Cloudflare Access), ou sur GitHub Pages en non
  référencé. Le choix définitif se fera dans la spec du sous-projet 4.
- **Mail** : HTML court, envoyé depuis l'action GitHub via le SMTP Gmail, avec un mot de passe
  d'application stocké en secret.
- **Assistant** (Claude Code local, abonnement Pro) : un `CLAUDE.md` et des skills dans le repo
  de données :
  - `/creuser <sujet>` : lit les fiches liées, va chercher les sources, répond, puis enregistre
    ses conclusions dans une fiche ;
  - `/comparer A B` : tableau comparatif sourcé ;
  - `/ajouter <url>` : force l'ingestion d'un contenu.

## 11. Qualité du tri

- **Tests du code** : pytest, ports simulés (réseau, LLM, embeddings) et vrais objets
  ailleurs ; couverture de branches ≥ 90 %.
- **Jeu de référence** `eval/golden.yaml` : 50 à 100 items étiquetés à la main.
  `auto-biblio eval triage --model <m>` mesure la précision et le rappel du pré-filtre et du
  triage. Il sert à comparer les modèles et à régler les seuils. Il est lancé à la demande,
  hors CI.

## 12. Découpage en sous-projets

| # | Sous-projet | Livrable | Dépend de |
|---|---|---|---|
| 1 | **Socle et collecte** | collecte quotidienne qui alimente `state/` dans le repo de données | — |
| 2 | **Triage** : embeddings, pré-score, couche LLM, triage, budget, revenants, enrichissement Semantic Scholar, jeu de référence | liste hebdomadaire classée et justifiée, plus un **digest brut** envoyé par mail | 1 |
| 3 | **Analyse et base de connaissances** : extraction de texte, fiches, pages thème, changelog | base Markdown vivante | 2 |
| 4 | **Publication** : site protégé, digest final | le livrable consulté | 3 |
| 5 | **Assistant local** : `CLAUDE.md` et skills | exploration interactive | 3 |

Point d'étape : à la fin du sous-projet 2, faire tourner le digest brut une à deux semaines
pour calibrer le profil avant d'investir dans les sous-projets 3 à 5.

## 13. Hors périmètre v1 (pistes v2)

- Feedback 👍/👎 depuis le digest, qui ajuste les poids et propose de nouveaux thèmes
  (volet hybride du profil).
- Analyse approfondie déclenchée par une issue GitHub (`deep-dive: <url>`).
- Runner auto-hébergé pour les modèles locaux.
- Nouvelles sources (X/Twitter, podcasts, conférences) via de nouveaux connecteurs.

## 14. Points à vérifier à l'implémentation

- Identifiants, tarifs et quotas gratuits des modèles retenus.
- Conditions d'utilisation et limites de chaque API source (arXiv : 3 s entre deux requêtes ;
  limites de l'API de recherche GitHub ; accès aux flux RSS de Reddit).
- Hébergement du site : Cloudflare Access ou GitHub Pages non référencé.
