# Sous-projet 1 — socle et collecte

- **Date** : 2026-10-10
- **Statut** : en attente de relecture
- **Vision** : `2026-10-10-auto-biblio-vision-design.md` (§5, §9 et §12)

## 1. Objectif

Livrer une **collecte quotidienne fiable** : toutes les sources v1 sont interrogées, les
contenus sont normalisés en `Item`, dédoublonnés entre sources, et leurs signaux sont
enregistrés. Le tout est versionné dans le repo de données et exécuté chaque jour par
GitHub Actions, **sans aucun appel LLM**.

Ce sous-projet pose aussi le socle commun : modèles du domaine, chargement et validation de la
configuration, store, taxonomie d'erreurs, journal d'exécution et CLI.

### Critères d'acceptation

1. `auto-biblio init <dir>` crée un repo de données prêt à l'emploi : configuration par défaut
   (profil et sources de la vision) et workflow quotidien.
2. `auto-biblio collect` interroge toutes les sources activées. Les items et signaux sont écrits
   dans `state/`, et une seconde exécution immédiate (même jour, mêmes réponses) ne produit
   **aucun diff** dans `state/items/` ni `state/signals/` (seuls `runs/` et `cursors.json`
   évoluent, par nature).
3. Un même contenu vu sur plusieurs sources (par exemple un papier arXiv présent sur HF Papers
   et sur HN) ne donne **qu'un seul** `Item`, avec plusieurs `sightings`.
4. La panne d'une source n'empêche pas les autres de tourner. Elle est consignée dans le journal
   d'exécution.
5. Une configuration invalide fait échouer immédiatement l'exécution, avec un message qui
   désigne le fichier et le champ fautifs.
6. `make check` passe (lint, pyright strict, couverture ≥ 90 %, docs).

### Hors périmètre (sous-projet 2 et suivants)

Embeddings, pré-score, rafraîchissement périodique des signaux des items déjà connus
(nécessaire pour la vélocité et les revenants), enrichissement Semantic Scholar, modèles
tendance du Hugging Face Hub, tout appel LLM.

## 2. Modèle du domaine (`domain/`, pur)

Tous les modèles sont des modèles Pydantic immuables (`frozen=True`).

### 2.1 Identité : `ItemId`

Une chaîne canonique, préfixée par un espace de noms. Elle est calculée par une fonction pure
`canonical_id(url: str) -> ItemId` :

| Entrée | Identifiant |
|---|---|
| `arxiv.org/abs/2410.12345v2`, `arxiv.org/pdf/2410.12345`, `huggingface.co/papers/2410.12345` | `arxiv:2410.12345` (sans numéro de version) |
| `github.com/Owner/Repo[/…]` | `gh:owner/repo` (en minuscules) |
| release GitHub | `gh:owner/repo@tag` |
| `doi.org/10.…` | `doi:10.…` (en minuscules) |
| toute autre URL | `url:<sha256(url normalisée)[:16]>` |

Normalisation d'URL : passage en `https`, hôte en minuscules, suppression de `www.`, des
paramètres de tracking (`utm_*`, `ref`, `source`), du fragment et de la barre oblique finale.

### 2.2 `Item`

| Champ | Type | Note |
|---|---|---|
| `id` | `ItemId` | |
| `kind` | `paper \| repo \| release \| blog_post \| discussion` | |
| `title` | `str` | |
| `summary` | `str \| None` | résumé de l'article, description du repo, extrait du billet |
| `url` | `HttpUrl` | URL canonique |
| `authors` | `tuple[str, ...]` | |
| `published_at` | `datetime \| None` | en UTC |
| `first_seen` | `datetime` | en UTC |
| `sightings` | `tuple[Sighting, ...]` | `Sighting` : nom de la source, `seen_at`, URL d'origine (par exemple le fil HN) |
| `links` | `tuple[ItemId, ...]` | liens papier ↔ code (par exemple HF Papers → repo GitHub) |
| `tags` | `tuple[str, ...]` | catégories arXiv, topics GitHub |

### 2.3 `Signal`

Champs : `item_id`, `kind` (`gh_stars`, `hf_upvotes`, `hn_points`, `hn_comments`), `value`
(entier), `observed_at`, `source`.

### 2.4 Fusion : `merge_items(existing, incoming) -> Item`

Fonction pure, commutative sur les champs ensemblistes :

- `sightings`, `links` et `tags` : union, dédoublonnée et triée.
- `first_seen` : le minimum des deux.
- `title`, `summary` et `authors` : on retient la valeur de la source la plus fiable. Ordre de
  priorité : `arxiv` > `hf_papers` > `github` > `rss` > `hackernews`. Une valeur absente est
  complétée par l'autre item.
- `kind` : celui de la source la plus prioritaire.

Dédoublonnage secondaire : pour `kind == paper` sans identifiant arXiv ni DOI, une égalité du
titre normalisé (minuscules, sans ponctuation, espaces compactés) vaut identité.

### 2.5 Erreurs (`domain/errors.py`)

`AutoBiblioError` est la classe de base. Elle a trois sous-classes : `ConfigError`,
`SourceUnavailableError` (réseau, HTTP 5xx ou 429, délai dépassé) et `SourcePayloadError`
(réponse non conforme). Chaque erreur porte le nom de la source ou le chemin du fichier
concerné.

### 2.6 Journal d'exécution : `RunReport`

Champs : `run_id`, `command`, `started_at`, `finished_at`, et pour chaque source : statut
(`ok`, `failed`, `skipped`), nombre d'items reçus, nouveaux et fusionnés, nombre de signaux,
message d'erreur.

## 3. Configuration (`config/` du repo de données)

Les fichiers YAML sont validés à la lecture par des modèles Pydantic. Toute erreur lève une
`ConfigError` qui désigne le fichier et le champ fautifs.

### 3.1 `profile.yaml`

Le schéma est celui de la vision (§3). Dans ce sous-projet, il sert à **valider** le profil
(qui sera utilisé dès le sous-projet 2) et à fournir les `watch.repos` au connecteur des
releases GitHub. `init` écrit les 7 thèmes de la vision.

### 3.2 `sources.yaml`

Le type de source sert de discriminant à une union Pydantic. Chaque entrée a un `name` unique,
un champ `enabled` (vrai par défaut) et un `min_interval_s` (délai minimum entre deux
requêtes).

```yaml
sources:
  - { name: arxiv, type: arxiv, categories: [cs.CL, cs.LG, cs.CV, cs.AI], max_results: 2000, min_interval_s: 3 }
  - { name: hf-papers, type: hf_papers }
  - { name: github-rising, type: github_search, topics: [llm, agents, rag, ocr, document-ai, tabular], min_stars: 50, created_within_days: 30 }
  - { name: github-releases, type: github_releases }     # repos : union des profile.themes[*].watch.repos
  - { name: hn, type: hackernews, min_points: 30 }
  - { name: r-machinelearning, type: rss, url: "https://www.reddit.com/r/MachineLearning/top/.rss?t=day", family: community }
  - { name: simon-willison, type: rss, url: "https://simonwillison.net/atom/everything/", family: community }
  # … blogs des labs et newsletters de la vision §4
```

### 3.3 `Settings` (`config.py`, variables d'environnement)

Le `Settings` du template est étendu :
- `data_dir: Path` (défaut `.`) ;
- `github_token: SecretStr | None` (augmente la limite de requêtes de l'API GitHub) ;
- `http_timeout_s: float = 30` ;
- `user_agent: str`.

## 4. Connecteurs (`sources/`)

```python
class Source(Protocol):
    name: str

    def fetch(self, since: datetime) -> SourceBatch: ...


# SourceBatch : items (tuple[Item, ...]), signals (tuple[Signal, ...])
```

Règles communes à tous les connecteurs :

- Le client `httpx.Client` est **injecté** par le constructeur. En test, on lui donne un
  `MockTransport`.
- La réponse brute est parsée dans un modèle Pydantic propre à la source, puis convertie en
  `Item` et `Signal`. Une réponse non conforme lève `SourcePayloadError`. Un problème de
  transport, un HTTP 5xx ou un 429 lève `SourceUnavailableError`.
- Le délai `min_interval_s` est respecté entre deux requêtes d'une même source. L'horloge et le
  `sleep` sont injectés, pour que les tests soient instantanés.

| Type | Point d'accès (à confirmer à l'implémentation) | Produit |
|---|---|---|
| `arxiv` | API d'export arXiv (Atom), requête par catégories triée par date de soumission, paginée | `paper` |
| `hf_papers` | API daily papers de Hugging Face, une requête par jour depuis `since` | `paper` + lien vers le repo GitHub ; signal `hf_upvotes` |
| `github_search` | API de recherche GitHub : `created:>…`, `stars:>…`, topics | `repo` ; signal `gh_stars` |
| `github_releases` | API releases de chaque repo suivi, filtrées sur `published_at > since` | `release` liée à `gh:owner/repo` |
| `hackernews` | API Algolia HN `search_by_date`, stories avec `points > min_points` | URL de la story canonicalisée (un lien arXiv devient `arxiv:…`) ; si la story n'a pas d'URL, `discussion` ; signaux `hn_points`, `hn_comments` |
| `rss` | flux RSS ou Atom générique | `blog_post`, ou le type déduit de l'URL canonique (un lien arXiv ou GitHub dans un flux est reconnu) |

Le parsing RSS et Atom (arXiv compris) passe par `feedparser`. Cette librairie n'est pas typée :
elle est isolée dans un seul module adaptateur (`sources/_feeds.py`), qui expose des modèles
typés. Les seuls contournements de typage du projet sont là, chacun justifié par un commentaire.

## 5. Store (`store/`)

Il lit et écrit le repo de données. Les écritures sont **déterministes**, pour garantir
l'idempotence et des diffs git propres.

| Chemin | Contenu | Écriture |
|---|---|---|
| `state/items/YYYY-MM.jsonl` | items, partitionnés par mois de `first_seen`, une ligne JSON par item, triés par `id` | réécriture complète du fichier si son contenu change |
| `state/signals/YYYY-MM.jsonl` | observations, partitionnées par mois d'`observed_at` | ajout ; au plus une observation par (`item_id`, `kind`, jour) |
| `state/cursors.json` | `{source: dernier succès}` | après chaque source réussie |
| `state/runs/<run_id>.json` | `RunReport` | en fin d'exécution |
| `state/quarantine/<run_id>/<source>.json` | extrait du payload fautif | sur `SourcePayloadError` |

`ItemStore` charge l'index complet (`id → mois`) au démarrage. Le volume attendu (quelques
centaines de milliers d'items) tient en mémoire. Les écritures passent par un fichier temporaire
puis un renommage, pour rester atomiques.

## 6. Étape de collecte (`stages/collect.py`)

`CollectStage(sources, item_store, signal_store, cursor_store, clock)` :

1. Pour chaque source activée : `since = curseur − chevauchement (2 jours)`, ou
   `maintenant − lookback (7 jours)` à la première exécution.
2. `fetch(since)`. En cas d'erreur de source : statut `failed` dans le rapport, journalisation,
   quarantaine si c'est une `SourcePayloadError`, puis on passe à la source suivante.
3. Canonicalisation et fusion avec le store (`merge_items`), enregistrement des signaux,
   avancement du curseur.
4. Écriture du `RunReport`.

Le chevauchement et le dédoublonnage rendent l'étape idempotente.

## 7. CLI (`cli.py`, Typer)

| Commande | Effet | Code de sortie |
|---|---|---|
| `auto-biblio init <dir>` | crée `config/` (profil et sources par défaut), `state/` vide, `.github/workflows/daily.yml`, `.gitignore` ; refuse d'écraser des fichiers existants | 0, ou 1 si des fichiers existent déjà |
| `auto-biblio validate-config [--data-dir]` | charge et valide toute la configuration | 0, ou 1 si la configuration est invalide |
| `auto-biblio collect [--data-dir] [--source NAME]… [--since ISO]` | exécute la collecte | 0 si au moins une source a réussi ; 1 si la configuration est invalide ; 2 si **toutes** les sources ont échoué |

`logging` est configuré une seule fois au démarrage de la CLI, via `log.configure_logging`.

## 8. Workflow quotidien (modèle écrit par `init`)

`.github/workflows/daily.yml` dans le repo de données :

- **Déclencheurs :** `schedule` (tous les jours à 05:00 UTC) et `workflow_dispatch`.
- **Concurrence :** le groupe `auto-biblio` empêche deux exécutions simultanées.
- **Étapes :**
  1. checkout ;
  2. installation de `uv` ;
  3. `uv tool install git+https://github.com/ocoudray/auto-biblio@<tag>` (tag épinglé et écrit
     par `init` à partir de la version installée) ;
  4. `auto-biblio collect` ;
  5. commit et push de `state/` s'il y a des changements (`git diff --quiet || …`).
- **Secrets :** `GITHUB_TOKEN`, fourni automatiquement, est passé à `AUTO_BIBLIO_GITHUB_TOKEN`.
- **Hypothèse :** le repo de code est public. S'il devient privé, il faudra un jeton de lecture
  dédié.

## 9. Dépendances

- **Exécution :** `httpx`, `feedparser`, `pyyaml`, `typer`.
- **Développement :** `types-pyyaml`.

## 10. Nettoyage du template

Suppression de `core.py` (démo `greet`) et de son test. `examples/quickstart.py` est remplacé
par `examples/dedup.py` : il construit des items vus par plusieurs sources et montre la fusion,
sans réseau, et il est exécuté par `tests/test_examples.py`. Mise à jour de `README.md`,
`docs/index.md` et `docs/getting-started.md` (installation, `init`, `collect`, configuration).

## 11. Tests

Un module de test par module source, conformément à `CLAUDE.md`.

| Cible | Approche |
|---|---|
| `canonical_id`, normalisation d'URL | table de cas : versions arXiv, liens HF, majuscules GitHub, paramètres de tracking, DOI |
| `merge_items` | priorités, commutativité des unions, minimum de `first_seen`, titre normalisé |
| modèles de configuration | YAML valides et invalides, message de `ConfigError` (fichier et champ) |
| connecteurs | fixtures de réponses réelles enregistrées dans `tests/fixtures/<source>/` avec `httpx.MockTransport` ; cas nominal, pagination, payload malformé (`SourcePayloadError`), 429 et 5xx (`SourceUnavailableError`) |
| store | aller-retour dans `tmp_path`, écriture déterministe (deux écritures identiques donnent des octets identiques), dédoublonnage des signaux, atomicité |
| `CollectStage` | sources factices : fusion entre sources, échec isolé d'une source, idempotence (deux exécutions → aucun changement), curseurs et chevauchement |
| CLI | `CliRunner` de Typer : `init` dans un répertoire vide puis non vide, `validate-config`, `collect` avec des sources factices injectées, codes de sortie |

Aucun test n'accède au réseau.
