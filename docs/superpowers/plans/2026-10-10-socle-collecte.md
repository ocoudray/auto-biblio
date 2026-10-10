# Socle et collecte — plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal :** une CLI `auto-biblio` capable d'initialiser un repo de données et d'y collecter
chaque jour, sans LLM, les items et signaux de six types de sources, dédoublonnés et écrits de
façon déterministe.

**Architecture :**
- Un domaine pur (`domain/`) : identifiants canoniques, modèles, fusion, erreurs, rapport
  d'exécution.
- Des modèles de configuration validés (`repo_config/`).
- Des connecteurs HTTP injectables (`sources/`).
- Un store fichiers (`store/`) et une étape d'orchestration (`stages/collect.py`).
- Une CLI Typer mince (`cli.py`), qui assemble le tout.

**Tech Stack :** Python 3.12, Pydantic 2, pydantic-settings, httpx, feedparser, PyYAML, Typer,
pytest, pyright strict, ruff, uv.

**Spec :** `docs/superpowers/specs/2026-10-10-socle-collecte-design.md`. La vision
`docs/superpowers/specs/2026-10-10-auto-biblio-vision-design.md` sert de contexte.

## Global Constraints

- Respecter `CLAUDE.md` à la lettre :
  - dépendances via `uv add` / `uv add --group dev`, jamais `pip` ;
  - pyright strict à zéro erreur, `Any` / `cast` / `# pyright: ignore` seulement en dernier
    recours et toujours commentés ;
  - docstrings Google sur tout élément public ;
  - `logging`, jamais `print` (sauf dans `examples/`) ;
  - pas de `except Exception: pass` ;
  - un module de test par module source : `src/auto_biblio/a/b.py` → `tests/a/test_b.py`.
    Créer les sous-dossiers de `tests/` sans `__init__.py`, avec des noms de fichiers de test
    uniques (pytest `rootdir`, mode `importmode` par défaut). Si un conflit de nom apparaît,
    préfixer le fichier (`test_sources_rss.py`).
- Modèles Pydantic du domaine et de la configuration immuables :
  `model_config = ConfigDict(frozen=True)`.
- Toutes les dates sont `datetime` *aware* en UTC. Une date naïve reçue d'une source est
  interprétée comme UTC.
- Aucun test n'accède au réseau. Les connecteurs reçoivent un `httpx.Client` injecté
  (`httpx.MockTransport` en test).
- La couverture de branches reste ≥ 90 %. `make check` doit passer à la fin de **chaque**
  tâche.
- Les valeurs par défaut de la spec sont exactes :
  - chevauchement 2 jours, lookback 7 jours à la première exécution ;
  - `min_interval_s` arXiv = 3, `max_results` arXiv = 2000 ;
  - `min_stars` = 50, `created_within_days` = 30, `min_points` HN = 30 ;
  - cron `0 5 * * *` ;
  - codes de sortie de `collect` : 0 / 1 / 2.
- Priorité des sources pour la fusion : `arxiv` > `hf_papers` > `github` > `rss` > `hackernews`.
  Les deux types GitHub (`github_search`, `github_releases`) partagent le rang `github`.

## Review Focus

1. **Sortie d'une source vide ou inchangée** : une source qui répond correctement mais sans
   nouveauté ne doit ni échouer, ni faire reculer le curseur, ni réécrire de fichier. Couvert
   par la tâche 10 (`test_empty_batch_writes_nothing`).
2. **Même contenu sous des URL différentes** : un lien `arxiv.org/pdf/…v3` dans un flux RSS, la
   page HF et le lien HN doivent converger vers un seul item. Couvert par les tâches 1
   (table `canonical_id`) et 10 (`test_cross_source_merge`).
3. **Dates naïves ou absentes** : un flux RSS sans date de publication, ou avec une date sans
   fuseau horaire, ne doit pas faire planter la collecte. L'entrée est incluse, et sa date naïve
   est interprétée comme UTC. Couvert par la tâche 5 (`test_entry_without_date_is_kept`,
   `test_naive_date_is_utc`).
4. **Relance le même jour** : une deuxième collecte ne doit dupliquer ni les signaux ni les
   sightings. Couvert par les tâches 4 (`test_signal_dedup_same_day`) et 10
   (`test_second_run_is_idempotent`).
5. **Exécution interrompue** : un arrêt en cours d'écriture ne doit jamais laisser un JSONL
   tronqué. Couvert par la tâche 4 (`test_atomic_write_keeps_old_file_on_error`).

---

## Structure des fichiers

```
src/auto_biblio/
├── config.py                 # (modifié) Settings
├── cli.py                    # Typer : init, validate-config, collect
├── scaffold.py               # écriture du squelette du repo de données
├── scaffold_templates/       # profile.yaml, sources.yaml, daily.yml, gitignore (données du package)
├── domain/
│   ├── __init__.py
│   ├── errors.py             # AutoBiblioError, ConfigError, SourceUnavailableError, SourcePayloadError
│   ├── ids.py                # ItemId, normalize_url, canonical_id, kind_for
│   ├── models.py             # SourceType, ItemKind, Sighting, Item, SignalKind, Signal, SourceBatch
│   ├── merge.py              # SOURCE_PRIORITY, normalized_title, merge_items
│   └── run_report.py         # SourceStatus, SourceReport, RunReport
├── repo_config/
│   ├── __init__.py
│   ├── profile.py            # Watch, Theme, Profile
│   ├── sources.py            # *SourceConfig, SourceConfig (union), SourcesConfig
│   └── loader.py             # RepoConfig, load_repo_config
├── store/
│   ├── __init__.py
│   ├── _files.py             # atomic_write_text, read_jsonl_lines
│   ├── items.py              # ItemStore, UpsertOutcome
│   ├── signals.py            # SignalStore
│   ├── cursors.py            # CursorStore
│   └── runs.py               # RunStore
├── sources/
│   ├── __init__.py           # Source (Protocol), SourceFactory, build_sources
│   ├── _http.py              # Throttle, get
│   ├── _feeds.py             # FeedEntry, parse_feed (seul module qui touche feedparser)
│   ├── rss.py
│   ├── arxiv.py
│   ├── hf_papers.py
│   ├── github.py             # GithubSearchSource, GithubReleasesSource
│   └── hackernews.py
└── stages/
    ├── __init__.py
    └── collect.py            # CollectStage
```

Les fixtures sont dans `tests/fixtures/<type>/`. Exemple : `examples/dedup.py`.

---

### Tâche 1 : identifiants canoniques et erreurs du domaine

**Files :**
- Create : `src/auto_biblio/domain/__init__.py`, `src/auto_biblio/domain/errors.py`,
  `src/auto_biblio/domain/ids.py`
- Test : `tests/domain/test_ids.py`, `tests/domain/test_errors.py`

**Interfaces :**
- Produces :
  - `ItemId = NewType("ItemId", str)`
  - `normalize_url(url: str) -> str`
  - `canonical_id(url: str) -> ItemId`
  - `kind_for(item_id: ItemId, default: ItemKind) -> ItemKind` (`ItemKind` est défini dans
    `models.py` à la tâche 2 : déclarer ici `ItemKind = Literal["paper", "repo", "release",
    "blog_post", "discussion"]` et le réexporter depuis `models.py`)
  - `class AutoBiblioError(Exception)`
  - `class ConfigError(AutoBiblioError)`, construite avec `(path: str, field: str | None,
    message: str)` et dont le `str()` vaut `"<path>: <field>: <message>"` (ou
    `"<path>: <message>"` sans champ)
  - `class SourceUnavailableError(AutoBiblioError)`, construite avec `(source: str, message:
    str)`
  - `class SourcePayloadError(AutoBiblioError)`, construite avec `(source: str, message: str,
    payload_excerpt: str = "")`. Attributs publics `source` et `payload_excerpt` ; l'extrait est
    tronqué à 10 000 caractères.

- [ ] **Étape 1 : écrire les tests qui échouent**

`test_canonical_id` paramétré, avec ces cas exacts :

| entrée | attendu |
|---|---|
| `https://arxiv.org/abs/2410.12345v2` | `arxiv:2410.12345` |
| `http://arxiv.org/pdf/2410.12345v1.pdf` | `arxiv:2410.12345` |
| `https://export.arxiv.org/abs/2410.12345` | `arxiv:2410.12345` |
| `https://huggingface.co/papers/2410.12345` | `arxiv:2410.12345` |
| `https://GitHub.com/Pydantic/Pydantic-AI` | `gh:pydantic/pydantic-ai` |
| `https://github.com/pola-rs/polars/tree/main/py-polars` | `gh:pola-rs/polars` |
| `https://github.com/astral-sh/uv/releases/tag/0.9.1` | `gh:astral-sh/uv@0.9.1` |
| `https://doi.org/10.1000/ABC.def` | `doi:10.1000/abc.def` |
| `https://www.example.com/post/?utm_source=x&id=3#top` et `http://example.com/post?id=3` | même `url:` (16 caractères hexadécimaux) |

Ajouter aussi ces tests :
- `test_normalize_url_strips_tracking` : `ref` et `source` sont aussi retirés, les autres
  paramètres sont conservés et triés.
- `test_github_non_repo_paths_are_urls` : `https://github.com/features` donne un id `url:`.
- `test_kind_for` : `arxiv:` → `paper`, `gh:o/r` → `repo`, `gh:o/r@t` → `release`, `url:` →
  le défaut.
- `test_config_error_str` : vérifier les deux formats de `str()`.
- `test_payload_excerpt_truncated` : un extrait de 20 000 caractères est ramené à 10 000.

- [ ] **Étape 2 : lancer les tests et vérifier qu'ils échouent**

Run : `uv run pytest tests/domain -v`. Attendu : `ModuleNotFoundError`.

- [ ] **Étape 3 : implémenter `errors.py` et `ids.py`**

Utiliser `urllib.parse` et des expressions régulières compilées au niveau du module :
- arXiv : `r"(\d{4}\.\d{4,5})(v\d+)?"` ;
- GitHub : les deux premiers segments du chemin, avec `releases/tag/<tag>` reconnu.

Le hash est `hashlib.sha256(normalize_url(url).encode()).hexdigest()[:16]`.

- [ ] **Étape 4 : relancer les tests**

Run : `uv run pytest tests/domain -v`. Attendu : tous passent.

- [ ] **Étape 5 : commit**

```bash
git add src/auto_biblio/domain tests/domain
git commit -m "feat(domain): canonical item ids and domain errors"
```

---

### Tâche 2 : modèles, fusion et rapport d'exécution

**Files :**
- Create : `src/auto_biblio/domain/models.py`, `src/auto_biblio/domain/merge.py`,
  `src/auto_biblio/domain/run_report.py`
- Test : `tests/domain/test_models.py`, `tests/domain/test_merge.py`,
  `tests/domain/test_run_report.py`

**Interfaces :**
- Consumes : `ItemId`, `ItemKind` (tâche 1).
- Produces :
  - `SourceType = Literal["arxiv", "hf_papers", "github_search", "github_releases",
    "hackernews", "rss"]`
  - `Sighting(source: str, source_type: SourceType, seen_at: datetime, origin_url: str)`
  - `Item(id, kind, title, summary: str | None, url: HttpUrl, authors: tuple[str, ...],
    published_at: datetime | None, first_seen: datetime, sightings: tuple[Sighting, ...],
    links: tuple[ItemId, ...] = (), tags: tuple[str, ...] = ())`. Un validateur impose au moins
    un sighting et des dates aware.
  - `SignalKind = Literal["gh_stars", "hf_upvotes", "hn_points", "hn_comments"]`
  - `Signal(item_id: ItemId, kind: SignalKind, value: int, observed_at: datetime, source: str)`
  - `SourceBatch(items: tuple[Item, ...] = (), signals: tuple[Signal, ...] = ())`
  - `SOURCE_PRIORITY: Mapping[SourceType, int]` : arxiv 0, hf_papers 1, github_search et
    github_releases 2, rss 3, hackernews 4 (plus petit = plus fiable)
  - `normalized_title(title: str) -> str`
  - `merge_items(existing: Item, incoming: Item) -> Item`. Lève `ValueError` si les `id`
    diffèrent, **sauf** quand les deux sont des `paper` de même `normalized_title` : on
    conserve alors l'id de `existing`.
  - `SourceStatus = Literal["ok", "failed", "skipped"]`
  - `SourceReport(source: str, status: SourceStatus, received: int = 0, new: int = 0,
    merged: int = 0, signals: int = 0, error: str | None = None)`
  - `RunReport(run_id: str, command: str, started_at: datetime, finished_at: datetime,
    sources: tuple[SourceReport, ...])`, avec les propriétés `all_failed: bool` (vrai seulement
    s'il y a au moins une source et qu'aucune n'est `ok`) et `any_ok: bool`.

- [ ] **Étape 1 : écrire les tests qui échouent**

- `test_merge_unions_are_sorted_and_deduplicated` : sightings, links et tags.
- `test_merge_is_commutative_on_sets` : `merge(a, b)` et `merge(b, a)` ont les mêmes
  sightings, links, tags et `first_seen`.
- `test_merge_keeps_earliest_first_seen`.
- `test_merge_prefers_higher_priority_source` : le titre arXiv l'emporte sur le titre HN quel
  que soit l'ordre.
- `test_merge_fills_missing_fields` : un `summary=None` côté prioritaire est complété par
  l'autre item.
- `test_merge_rejects_different_ids`.
- `test_merge_papers_by_normalized_title` : `"Mamba: Linear-Time  Sequence Modeling!"` et
  `"mamba linear-time sequence modeling"` fusionnent.
- `test_item_requires_sighting`, `test_item_rejects_naive_datetime`.
- `test_run_report_all_failed` : liste vide → `False` ; tout `failed` → `True` ; au moins un
  `ok` → `False`.

- [ ] **Étape 2 : lancer les tests et vérifier qu'ils échouent**

Run : `uv run pytest tests/domain -v`. Attendu : échec à l'import.

- [ ] **Étape 3 : implémenter les trois modules**

- La meilleure priorité d'un item est le minimum de `SOURCE_PRIORITY` sur ses sightings. Le
  gagnant fournit `title`, `summary`, `authors`, `kind`, `url` et `published_at` ; toute valeur
  `None` ou tuple vide est complétée par l'autre item. En cas d'égalité, `existing` gagne.
- Les sightings sont dédoublonnés sur le triplet `(source, origin_url, seen_at.date())` et
  triés par `(seen_at, source)`.
- `normalized_title` : minuscules, ponctuation remplacée par des espaces (sauf `-`), espaces
  compactés.

- [ ] **Étape 4 : relancer les tests**

Run : `uv run pytest tests/domain -v`. Attendu : tous passent.

- [ ] **Étape 5 : commit**

```bash
git add src/auto_biblio/domain tests/domain
git commit -m "feat(domain): item models, cross-source merge and run report"
```

---

### Tâche 3 : configuration du repo de données et `Settings`

**Files :**
- Create : `src/auto_biblio/repo_config/{__init__,profile,sources,loader}.py`
- Modify : `src/auto_biblio/config.py`, `.env.example`
- Test : `tests/repo_config/test_profile.py`, `tests/repo_config/test_sources.py`,
  `tests/repo_config/test_loader.py`, `tests/test_config.py`

**Interfaces :**
- Consumes : `ConfigError` (tâche 1).
- Produces :
  - `Watch(repos: tuple[str, ...] = (), authors: tuple[str, ...] = ())`, chaque repo validé
    par `^[\w.-]+/[\w.-]+$`.
  - `Theme(id: str` (slug `^[a-z0-9-]+$`)`, label: str, weight: float = 1.0` (≥ 0)`,
    description: str, keywords: tuple[str, ...] = (), exclude: tuple[str, ...] = (), watch:
    Watch = Watch())`.
  - `Profile(themes: tuple[Theme, ...]` (au moins un, ids uniques)`, global_exclude:
    tuple[str, ...] = ())`, avec la méthode `watched_repos() -> tuple[str, ...]` (minuscules,
    uniques, triés).
  - Configurations de sources : une base commune `name` (slug), `enabled: bool = True`,
    `min_interval_s: float = 1.0`, puis :
    - `ArxivSourceConfig(type="arxiv", categories` (non vide)`, max_results=2000,
      min_interval_s=3.0)`
    - `HfPapersSourceConfig(type="hf_papers")`
    - `GithubSearchSourceConfig(type="github_search", topics` (non vide)`, min_stars=50,
      created_within_days=30)`
    - `GithubReleasesSourceConfig(type="github_releases")`
    - `HackernewsSourceConfig(type="hackernews", min_points=30)`
    - `RssSourceConfig(type="rss", url: HttpUrl, family: Literal["academic", "applied",
      "community"])`
  - `SourceConfig` = l'union annotée de ces classes, avec `Field(discriminator="type")`.
  - `SourcesConfig(sources: tuple[SourceConfig, ...])`, dont les `name` sont uniques.
  - `RepoConfig(profile: Profile, sources: SourcesConfig)`
  - `load_repo_config(data_dir: Path) -> RepoConfig`, qui lit `config/profile.yaml` et
    `config/sources.yaml`.
  - `Settings` : ajouter `data_dir: Path = Path()`, `github_token: SecretStr | None = None`,
    `http_timeout_s: float = 30.0`, `user_agent: str =
    f"auto-biblio/{__version__} (+https://github.com/ocoudray/auto-biblio)"`.

- [ ] **Étape 1 : ajouter les dépendances**

```bash
uv add pyyaml
uv add --group dev types-pyyaml
```

- [ ] **Étape 2 : écrire les tests qui échouent**

- `test_profile_rejects_duplicate_theme_ids`, `test_profile_requires_a_theme`,
  `test_watched_repos_union_sorted_lowercase`.
- `test_sources_discriminated_union` : un YAML mêlant les 6 types se parse dans les bonnes
  classes.
- `test_sources_defaults` : vérifier les valeurs exactes des Global Constraints.
- `test_sources_reject_duplicate_names`, `test_unknown_source_type_rejected`.
- Dans `test_loader.py` :
  - `test_missing_file_raises_config_error` : le message contient `config/profile.yaml`.
  - `test_invalid_yaml_raises_config_error`.
  - `test_invalid_field_message` : avec `min_stars: "beaucoup"` dans la 3e source, `str(err)`
    commence par `config/sources.yaml: sources.2.min_stars:`.
- Dans `test_config.py` : `test_github_token_from_env` (une `SecretStr` dont la valeur est
  lisible avec `get_secret_value()`).

- [ ] **Étape 3 : lancer les tests et vérifier qu'ils échouent**

Run : `uv run pytest tests/repo_config tests/test_config.py -v`

- [ ] **Étape 4 : implémenter**

- Le loader utilise `yaml.safe_load`.
- Il convertit `yaml.YAMLError`, `OSError` et `pydantic.ValidationError` en `ConfigError`
  (`raise ... from exc`).
- Pour une erreur de validation, le champ est construit en joignant le `loc` de la **première**
  erreur par des points.
- Les chemins sont affichés relativement à `data_dir`.

Ajouter les nouvelles variables à `.env.example`.

- [ ] **Étape 5 : relancer les tests**

Run : `uv run pytest tests/repo_config tests/test_config.py -v`. Attendu : tous passent.

- [ ] **Étape 6 : commit**

```bash
git add pyproject.toml uv.lock src/auto_biblio/repo_config src/auto_biblio/config.py .env.example tests/repo_config tests/test_config.py
git commit -m "feat(config): data-repo configuration models and loader"
```

---

### Tâche 4 : store

**Files :**
- Create : `src/auto_biblio/store/{__init__,_files,items,signals,cursors,runs}.py`
- Test : `tests/store/test_files.py`, `tests/store/test_items.py`,
  `tests/store/test_signals.py`, `tests/store/test_cursors.py`, `tests/store/test_runs.py`

**Interfaces :**
- Consumes : `Item`, `Signal`, `RunReport`, `merge_items`, `normalized_title` (tâche 2).
- Produces (le paramètre `state_dir` désigne `<data_dir>/state`) :
  - `atomic_write_text(path: Path, content: str) -> None` : écrit dans un fichier temporaire
    du même dossier, puis appelle `os.replace`.
  - `UpsertOutcome = Literal["new", "merged", "unchanged"]`
  - `ItemStore.open(state_dir: Path) -> ItemStore`, qui charge tous les
    `items/*.jsonl`. Méthodes :
    - `get(item_id) -> Item | None`
    - `upsert(item: Item) -> UpsertOutcome` : fusionne avec l'item de même id, ou, pour un
      `paper`, avec le paper de même titre normalisé.
    - `flush() -> None` : ne réécrit que les partitions modifiées.
  - `SignalStore.open(state_dir) -> SignalStore` :
    - `add(signals: Iterable[Signal]) -> int` renvoie le nombre de signaux nouveaux ;
    - `flush() -> None`.
  - `CursorStore.open(state_dir) -> CursorStore` : `get(source: str) -> datetime | None`,
    `set(source: str, at: datetime) -> None`, `flush() -> None`.
  - `RunStore(state_dir)` : `write_report(report: RunReport) -> Path` et
    `quarantine(run_id: str, source: str, excerpt: str) -> Path`.

- [ ] **Étape 1 : écrire les tests qui échouent**

- `test_atomic_write_keeps_old_file_on_error` : simuler l'échec de `os.replace` avec
  monkeypatch ; l'ancien contenu est intact et aucun fichier temporaire ne reste.
- `test_items_roundtrip` : upsert, flush, réouverture ; les items sont égaux.
- `test_items_partitioned_by_first_seen_month_sorted_by_id` : vérifier le contenu exact de
  `items/2026-10.jsonl`.
- `test_flush_is_byte_identical_when_unchanged` : deux flushs successifs, et un `upsert`
  d'un item identique renvoie `"unchanged"` ; le `mtime` et les octets ne changent pas.
- `test_upsert_outcomes` : `new`, puis `merged` (nouveau sighting), puis `unchanged`.
- `test_upsert_matches_paper_by_title`.
- `test_signal_dedup_same_day` : le même (`item_id`, `kind`, jour) ajouté deux fois →
  `add` renvoie 1 puis 0. Une observation le lendemain → 1.
- `test_signals_partitioned_by_observed_month`.
- `test_cursors_roundtrip` : JSON trié par clé, dates ISO 8601 en UTC.
- `test_run_report_written`, `test_quarantine_written`.

- [ ] **Étape 2 : lancer les tests et vérifier qu'ils échouent**

Run : `uv run pytest tests/store -v`

- [ ] **Étape 3 : implémenter**

- Une ligne = `item.model_dump_json()`. Le fichier se termine par `\n`.
- Le store garde un index par titre normalisé (papers uniquement).
- Si une fusion change le mois de `first_seen`, retirer l'item de l'ancienne partition et
  marquer les deux partitions comme modifiées.
- `SignalStore` charge les clés de dédoublonnage de toutes les partitions existantes à
  l'ouverture. Dans un fichier, les signaux sont triés par `(observed_at, item_id, kind)`.

- [ ] **Étape 4 : relancer les tests**

Run : `uv run pytest tests/store -v`. Attendu : tous passent.

- [ ] **Étape 5 : commit**

```bash
git add src/auto_biblio/store tests/store
git commit -m "feat(store): deterministic JSONL stores for items, signals, cursors and runs"
```

---

### Tâche 5 : socle des connecteurs et connecteur RSS

**Files :**
- Create : `src/auto_biblio/sources/__init__.py`, `src/auto_biblio/sources/_http.py`,
  `src/auto_biblio/sources/_feeds.py`, `src/auto_biblio/sources/rss.py`
- Test : `tests/sources/test_http.py`, `tests/sources/test_feeds.py`,
  `tests/sources/test_rss.py`, `tests/fixtures/rss/{atom_sample.xml,rss2_sample.xml,broken.xml}`

**Interfaces :**
- Consumes : modèles (tâche 2), `canonical_id` et `kind_for` (tâche 1), `RssSourceConfig`
  (tâche 3), erreurs.
- Produces :
  - Dans `sources/__init__.py` :

    ```python
    class Source(Protocol):
        @property
        def name(self) -> str: ...
        def fetch(self, since: datetime) -> SourceBatch: ...
    ```

    (le type `SourceFactory` est ajouté à la tâche 9).
  - `Clock = Callable[[], datetime]`
  - `Throttle(min_interval_s: float, monotonic: Callable[[], float] = time.monotonic, sleep:
    Callable[[float], None] = time.sleep)`, dont `wait() -> None` dort le temps restant avant
    l'intervalle minimum (pas de pause au premier appel).
  - `get(client: httpx.Client, url: str, *, source: str, params: Mapping[str, str | int] |
    None = None, headers: Mapping[str, str] | None = None) -> httpx.Response`. Un
    `httpx.HTTPError` ou un statut hors 2xx lève `SourceUnavailableError`, avec le statut dans
    le message.
  - `FeedEntry(link: str, title: str, summary: str | None, authors: tuple[str, ...],
    published: datetime | None, categories: tuple[str, ...])`
  - `parse_feed(content: bytes, *, source: str) -> tuple[FeedEntry, ...]`. Lève
    `SourcePayloadError` si `feedparser` signale un flux mal formé **et** qu'il n'y a aucune
    entrée. Le summary est débarrassé de son HTML (tags retirés, entités décodées avec
    `html.unescape`, espaces compactés) et tronqué à 2 000 caractères.
  - `RssSource(config: RssSourceConfig, client: httpx.Client, clock: Clock, throttle: Throttle)`

- [ ] **Étape 1 : ajouter les dépendances et enregistrer les fixtures**

```bash
uv add httpx feedparser
curl -sL "https://simonwillison.net/atom/everything/" -o tests/fixtures/rss/atom_sample.xml
curl -sL "https://huggingface.co/blog/feed.xml" -o tests/fixtures/rss/rss2_sample.xml
```

Réduire chaque fixture à 3 entrées à la main. Dans `rss2_sample.xml`, retirer la date d'une
entrée et mettre une date sans fuseau horaire sur une autre. Ajouter un lien
`https://arxiv.org/abs/2410.12345v1` comme lien d'une entrée. Écrire enfin `broken.xml` (du
XML invalide, sans entrée).

- [ ] **Étape 2 : écrire les tests qui échouent**

- `test_throttle_sleeps_remaining_interval` : avec une horloge et un `sleep` factices et un
  intervalle de 3 s, des appels à t = 0 puis t = 1 doivent dormir 2 s.
- `test_get_maps_errors` : 503, 429, 404 et `httpx.ConnectError` lèvent tous
  `SourceUnavailableError`.
- `test_parse_atom_and_rss2` : vérifier les champs de la première entrée.
- `test_summary_html_stripped`, `test_broken_feed_raises_payload_error`.
- `test_entry_without_date_is_kept` : `RssSource.fetch` inclut l'entrée sans date.
- `test_naive_date_is_utc`.
- `test_rss_filters_by_since` : une entrée datée avant `since` est exclue.
- `test_rss_item_kind_from_link` : l'entrée arXiv devient `paper` avec l'id
  `arxiv:2410.12345`, les autres `blog_post`.
- `test_rss_sighting` : `source` = le nom de la configuration, `source_type="rss"`,
  `seen_at` = l'horloge, `origin_url` = le lien.

- [ ] **Étape 3 : lancer les tests et vérifier qu'ils échouent**

Run : `uv run pytest tests/sources -v`

- [ ] **Étape 4 : implémenter**

`_feeds.py` est le **seul** module qui importe `feedparser`. Les objets non typés de
`feedparser` sont lus via `typing.cast` vers des `Mapping[str, object]`, avec un commentaire
expliquant l'absence de stubs. Ce module ne contient aucun `# pyright: ignore` non justifié.

L'item RSS est construit ainsi :
- `id = canonical_id(link)` ;
- `kind = kind_for(id, "blog_post")` ;
- `first_seen = clock()`.

- [ ] **Étape 5 : relancer les tests**

Run : `uv run pytest tests/sources -v`. Attendu : tous passent.

- [ ] **Étape 6 : commit**

```bash
git add pyproject.toml uv.lock src/auto_biblio/sources tests/sources tests/fixtures/rss
git commit -m "feat(sources): HTTP/feeds foundations and RSS connector"
```

---

### Tâche 6 : connecteur arXiv

**Files :**
- Create : `src/auto_biblio/sources/arxiv.py`
- Test : `tests/sources/test_arxiv.py`, `tests/fixtures/arxiv/{page1.xml,page2.xml,empty.xml}`

**Interfaces :**
- Consumes : `get`, `Throttle`, `parse_feed`, `ArxivSourceConfig`, `Clock`.
- Produces : `ArxivSource(config: ArxivSourceConfig, client: httpx.Client, clock: Clock,
  throttle: Throttle)`, qui implémente `Source`.

- [ ] **Étape 1 : enregistrer les fixtures**

```bash
curl -s "https://export.arxiv.org/api/query?search_query=cat:cs.CL&sortBy=submittedDate&sortOrder=descending&start=0&max_results=3" -o tests/fixtures/arxiv/page1.xml
```

Construire `page2.xml` en copiant `page1.xml` avec des dates antérieures au `since` du test.
`empty.xml` est un flux Atom valide sans entrée.

- [ ] **Étape 2 : écrire les tests qui échouent**

- `test_query_params` : la première requête porte `search_query=cat:cs.CL OR cat:cs.LG …`
  (catégories jointes par ` OR `), `sortBy=submittedDate`, `sortOrder=descending`, `start=0`,
  `max_results=100`.
- `test_paginates_until_older_than_since` : 2 requêtes, et les entrées de la page 2
  antérieures à `since` sont exclues.
- `test_stops_at_max_results` : avec `max_results=3`, une seule page de 3 entrées est lue.
- `test_throttle_called_between_pages`.
- `test_item_fields` : `id=arxiv:<id sans version>`, `kind="paper"`, titre sans retours à la
  ligne, `tags` = les catégories, `source_type="arxiv"`.
- `test_empty_feed_returns_empty_batch`.

- [ ] **Étape 3 : lancer les tests et vérifier qu'ils échouent**

Run : `uv run pytest tests/sources/test_arxiv.py -v`

- [ ] **Étape 4 : implémenter**

- Taille de page fixe de 100 (`PAGE_SIZE = 100`).
- Arrêt dès qu'une page est vide, qu'une entrée est plus ancienne que `since`, ou que
  `max_results` est atteint.
- URL : `https://export.arxiv.org/api/query`.

- [ ] **Étape 5 : relancer les tests**

Run : `uv run pytest tests/sources/test_arxiv.py -v`. Attendu : tous passent.

- [ ] **Étape 6 : commit**

```bash
git add src/auto_biblio/sources/arxiv.py tests/sources/test_arxiv.py tests/fixtures/arxiv
git commit -m "feat(sources): arXiv connector"
```

---

### Tâche 7 : connecteur Hugging Face Daily Papers

**Files :**
- Create : `src/auto_biblio/sources/hf_papers.py`
- Test : `tests/sources/test_hf_papers.py`, `tests/fixtures/hf_papers/{day.json,malformed.json}`

**Interfaces :**
- Produces : `HfPapersSource(config: HfPapersSourceConfig, client: httpx.Client, clock: Clock,
  throttle: Throttle)`.

- [ ] **Étape 1 : enregistrer la fixture**

```bash
curl -s "https://huggingface.co/api/daily_papers?date=2026-10-08" -o tests/fixtures/hf_papers/day.json
```

Réduire la fixture à 3 papiers, dont un avec un lien vers un repo GitHub. **Lire la vraie
réponse** pour fixer les noms de champs du modèle Pydantic `_HfDailyPaper`. Champs attendus,
à confirmer : `paper.id`, `paper.title`, `paper.summary`, `paper.authors[].name`,
`paper.upvotes`, `paper.publishedAt`, et `paper.githubRepo` ou équivalent. `malformed.json`
est une liste d'objets sans `paper`.

- [ ] **Étape 2 : écrire les tests qui échouent**

- `test_one_request_per_day_since` : avec `since = maintenant − 2 jours`, 3 requêtes, dont les
  paramètres `date` sont les 3 jours ISO.
- `test_item_and_links` : `id=arxiv:…`, `links=(gh:owner/repo,)` quand un repo est présent.
- `test_upvotes_signal` : un `Signal(kind="hf_upvotes", observed_at=clock())` par papier.
- `test_malformed_raises_payload_error` : l'extrait du payload est renseigné.

- [ ] **Étapes 3 à 6 : lancer les tests (échec), implémenter avec un modèle Pydantic de la
  réponse, relancer (succès), puis commit**

```bash
git add src/auto_biblio/sources/hf_papers.py tests/sources/test_hf_papers.py tests/fixtures/hf_papers
git commit -m "feat(sources): Hugging Face daily papers connector"
```

---

### Tâche 8 : connecteurs GitHub et Hacker News

**Files :**
- Create : `src/auto_biblio/sources/github.py`, `src/auto_biblio/sources/hackernews.py`
- Test : `tests/sources/test_github.py`, `tests/sources/test_hackernews.py`, et les fixtures
  `tests/fixtures/github/{search.json,releases.json}`, `tests/fixtures/hackernews/stories.json`

**Interfaces :**
- Produces :
  - `GithubSearchSource(config: GithubSearchSourceConfig, client: httpx.Client, clock: Clock,
    throttle: Throttle, token: SecretStr | None)`
  - `GithubReleasesSource(config: GithubReleasesSourceConfig, repos: tuple[str, ...], client:
    httpx.Client, clock: Clock, throttle: Throttle, token: SecretStr | None)`
  - `HackernewsSource(config: HackernewsSourceConfig, client: httpx.Client, clock: Clock,
    throttle: Throttle)`

- [ ] **Étape 1 : enregistrer les fixtures**

```bash
curl -s "https://api.github.com/search/repositories?q=topic:llm+stars:>50&sort=stars&order=desc&per_page=3" -o tests/fixtures/github/search.json
curl -s "https://api.github.com/repos/astral-sh/uv/releases?per_page=3" -o tests/fixtures/github/releases.json
curl -s "https://hn.algolia.com/api/v1/search_by_date?tags=story&numericFilters=points>30&hitsPerPage=3" -o tests/fixtures/hackernews/stories.json
```

Dans `stories.json`, faire pointer l'URL d'une story vers `https://arxiv.org/abs/2410.12345`,
et retirer l'URL d'une autre (Ask HN).

- [ ] **Étape 2 : écrire les tests qui échouent**

- `test_search_one_query_per_topic` : `q == f"topic:{t} created:>{(now - 30 j).date()}
  stars:>50"`, `sort=stars`, `order=desc`, `per_page=100`. Le paramètre `since` est ignoré,
  car la fenêtre est `created_within_days`.
- `test_search_auth_header_when_token` : `Authorization: Bearer <token>`. Ajouter aussi
  l'en-tête `Accept: application/vnd.github+json`.
- `test_search_items_and_stars_signal` : `id=gh:owner/repo`, `kind="repo"`, `summary` = la
  description, `tags` = les topics, un signal `gh_stars`.
- `test_search_dedups_repo_across_topics` : un repo présent dans 2 topics donne un seul item.
- `test_releases_filters_since_and_links_repo` : `id=gh:astral-sh/uv@<tag>`,
  `kind="release"`, `links=(gh:astral-sh/uv,)`, `summary` = le body tronqué à 2 000
  caractères.
- `test_releases_no_repos_returns_empty_batch`.
- `test_hn_query` : `tags=story`, `numericFilters=created_at_i>{int(since.timestamp())},points>30`,
  `hitsPerPage=1000`.
- `test_hn_story_url_canonicalized` : la story arXiv donne l'id `arxiv:2410.12345`, le kind
  `paper`, et un sighting dont l'`origin_url` vaut `https://news.ycombinator.com/item?id=<objectID>`.
- `test_hn_story_without_url_is_discussion` : l'id est `canonical_id` de l'URL HN de l'item.
- `test_hn_signals` : `hn_points` et `hn_comments` portent l'id de l'item.

- [ ] **Étapes 3 à 6 : lancer les tests (échec), implémenter avec des modèles Pydantic des
  réponses (une réponse non conforme lève `SourcePayloadError`), relancer (succès), puis
  commit**

```bash
git add src/auto_biblio/sources/github.py src/auto_biblio/sources/hackernews.py tests/sources/test_github.py tests/sources/test_hackernews.py tests/fixtures/github tests/fixtures/hackernews
git commit -m "feat(sources): GitHub search/releases and Hacker News connectors"
```

---

### Tâche 9 : fabrique de sources

**Files :**
- Modify : `src/auto_biblio/sources/__init__.py`
- Test : `tests/sources/test_factory.py`

**Interfaces :**
- Produces :
  - `SourceFactory = Callable[[RepoConfig, Settings, httpx.Client, Clock], list[Source]]`
  - `build_sources(config: RepoConfig, settings: Settings, client: httpx.Client, clock:
    Clock) -> list[Source]`. Elle instancie uniquement les sources `enabled`, chacune avec son
    propre `Throttle(config.min_interval_s)`. `GithubReleasesSource` reçoit
    `config.profile.watched_repos()` et `settings.github_token`.

- [ ] **Étape 1 : écrire le test qui échoue**

`test_build_sources_types_and_enabled` : une configuration avec les 6 types dont 1 désactivé
donne 5 sources, de classes attendues et de noms conformes. Le repo surveillé est bien passé.

- [ ] **Étapes 2 à 5 : lancer le test (échec), implémenter avec un `match` sur le type de
  configuration, relancer (succès), puis commit**

```bash
git add src/auto_biblio/sources/__init__.py tests/sources/test_factory.py
git commit -m "feat(sources): build connectors from configuration"
```

---

### Tâche 10 : étape de collecte

**Files :**
- Create : `src/auto_biblio/stages/__init__.py`, `src/auto_biblio/stages/collect.py`
- Test : `tests/stages/test_collect.py`

**Interfaces :**
- Consumes : `Source`, stores (tâche 4), `RunReport`, erreurs.
- Produces : `CollectStage(sources: Sequence[Source], items: ItemStore, signals: SignalStore,
  cursors: CursorStore, runs: RunStore, clock: Clock, overlap: timedelta = timedelta(days=2),
  lookback: timedelta = timedelta(days=7))` et sa méthode `run(*, only: Collection[str] | None
  = None, since: datetime | None = None) -> RunReport`.
  - `run_id = f"{started:%Y%m%dT%H%M%SZ}-collect"`.
  - Une source absente de `only` est `skipped`.
  - Un `since` explicite écrase le calcul `curseur − overlap` / `maintenant − lookback`.
  - Le curseur prend la valeur de `clock()` lue **avant** le `fetch`, et n'est avancé qu'en cas
    de succès.
  - Une `SourcePayloadError` entraîne `runs.quarantine(...)`.
  - Les stores sont flushés une fois, en fin d'exécution, avant l'écriture du rapport.

- [ ] **Étape 1 : écrire les tests qui échouent**

Ils utilisent une classe `FakeSource` (nom, batch ou exception à lever, et `since` reçu
enregistré) et une horloge fixe.

- `test_first_run_uses_lookback`, `test_next_run_uses_cursor_minus_overlap`,
  `test_explicit_since_wins`.
- `test_cross_source_merge` : l'item `arxiv:2410.12345` vient de 3 sources factices (arXiv, HF,
  HN avec une URL PDF v3). On obtient 1 item avec 3 sightings, et le rapport compte `new=1`
  pour la première source et `merged=1` pour chacune des autres.
- `test_failing_source_isolated` : une source lève `SourceUnavailableError`, l'autre réussit.
  Le statut est `failed`, l'erreur est renseignée, le curseur de la source en échec ne bouge
  pas, les items de l'autre source sont écrits.
- `test_payload_error_quarantined`.
- `test_only_filter_marks_skipped`.
- `test_second_run_is_idempotent` : deux exécutions avec les mêmes batches et la même horloge.
  Les octets de `state/items/` et `state/signals/` sont identiques après chaque exécution.
- `test_empty_batch_writes_nothing` : aucun fichier dans `items/` ni `signals/`, statut `ok`,
  curseur avancé.

- [ ] **Étapes 2 à 5 : lancer les tests (échec), implémenter (une méthode privée par source,
  pas plus de 30 lignes par méthode), relancer (succès), puis commit**

```bash
git add src/auto_biblio/stages tests/stages
git commit -m "feat(stages): collect stage with per-source isolation and cursors"
```

---

### Tâche 11 : squelette du repo de données (`init`)

**Files :**
- Create : `src/auto_biblio/scaffold.py`,
  `src/auto_biblio/scaffold_templates/{profile.yaml,sources.yaml,daily.yml,gitignore}`
- Test : `tests/test_scaffold.py`

**Interfaces :**
- Consumes : `load_repo_config` (tâche 3).
- Produces :
  - `class ScaffoldExistsError(AutoBiblioError)`, qui porte la liste des chemins en conflit.
  - `scaffold_data_repo(target: Path, version: str) -> list[Path]` : écrit
    `config/profile.yaml`, `config/sources.yaml`, `.github/workflows/daily.yml`, `.gitignore`
    et `state/.gitkeep`, et renvoie les chemins créés. Si **un seul** de ces fichiers existe,
    elle lève l'erreur avant toute écriture.

Contenu des templates (lus avec `importlib.resources.files("auto_biblio.scaffold_templates")`) :

- **`profile.yaml`** : les 7 thèmes de la vision (§3), avec leurs ids, labels, descriptions
  (2 ou 3 phrases tirées de la colonne « signaux typiques ») et mots-clés. Repos `watch` :
  - `agentic` : `pydantic/pydantic-ai`, `anthropics/claude-code`
  - `ai-dev-practices` : `astral-sh/uv`, `astral-sh/ruff`, `pola-rs/polars`,
    `pydantic/pydantic`
  - `doc-dataification` : `docling-project/docling`, `datalab-to/marker`
  - `tabular-fm` : `PriorLabs/TabPFN`, `autogluon/autogluon`
  - `llm-arch` : `state-spaces/mamba`

  Avant de commiter, vérifier que chaque repo existe :
  `curl -s -o /dev/null -w "%{http_code}" https://api.github.com/repos/<r>` doit renvoyer 200.
  Corriger ou retirer les autres.
- **`sources.yaml`** :
  - `arxiv` (cs.CL, cs.LG, cs.CV, cs.AI), `hf-papers`, `github-rising` (topics : `llm`,
    `agents`, `rag`, `ocr`, `document-ai`, `tabular`), `github-releases`, `hn` ;
  - flux RSS `community` : r/MachineLearning et r/LocalLLaMA
    (`https://www.reddit.com/r/<sub>/top/.rss?t=day`), Simon Willison ;
  - flux RSS `applied` : blogs Hugging Face, OpenAI, Google DeepMind, LangChain, LlamaIndex ;
  - newsletters `community` : Import AI, Latent Space, The Batch.

  Ne garder que les URL qui renvoient un flux valide (vérifier avec `curl -sL <url> | head`).
  Pour une source sans flux officiel (par exemple Anthropic), laisser une ligne commentée qui
  l'explique.
- **`daily.yml`** : déclencheurs `schedule: cron "0 5 * * *"` et `workflow_dispatch` ;
  `concurrency: auto-biblio` ; `permissions: contents: write` ; étapes :
  1. `actions/checkout@v4` ;
  2. `astral-sh/setup-uv@v6` ;
  3. `uv tool install git+https://github.com/ocoudray/auto-biblio@v$version` ;
  4. `auto-biblio collect`, avec `AUTO_BIBLIO_GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}` ;
  5. commit et push si `git status --porcelain state` n'est pas vide, sous l'identité
     `github-actions[bot]`.

  Le placeholder `$version` est substitué avec `string.Template`.
- **`gitignore`** est écrit sous le nom `.gitignore` : `.env`, `__pycache__/`.

- [ ] **Étape 1 : écrire les tests qui échouent**

- `test_scaffold_creates_files` : vérifier la liste exacte des chemins.
- `test_scaffolded_config_is_valid` : `load_repo_config(tmp)` réussit, renvoie 7 thèmes, et
  les sources incluent les 6 types.
- `test_workflow_pins_version` : `"auto-biblio@v1.2.3"` apparaît dans `daily.yml`.
- `test_refuses_to_overwrite` : avec un `config/profile.yaml` préexistant, l'erreur est levée
  et aucun autre fichier n'est créé.
- `test_templates_ship_with_package` : la ressource est lisible via `importlib.resources`.

- [ ] **Étapes 2 à 5 : lancer les tests (échec), implémenter et écrire les templates,
  relancer (succès), puis commit**

```bash
git add src/auto_biblio/scaffold.py src/auto_biblio/scaffold_templates tests/test_scaffold.py
git commit -m "feat: scaffold a ready-to-run data repository"
```

---

### Tâche 12 : CLI

**Files :**
- Create : `src/auto_biblio/cli.py`
- Modify : `pyproject.toml`, avec `[project.scripts] auto-biblio = "auto_biblio.cli:main"`
- Test : `tests/test_cli.py`

**Interfaces :**
- Consumes : `scaffold_data_repo`, `load_repo_config`, `build_sources` / `SourceFactory`,
  stores, `CollectStage`, `Settings`, `configure_logging`.
- Produces :
  - `create_app(source_factory: SourceFactory = build_sources, clock: Clock = lambda:
    datetime.now(UTC)) -> typer.Typer`
  - `main() -> None`
- Commandes :
  - `init TARGET` ;
  - `validate-config [--data-dir PATH]` ;
  - `collect [--data-dir PATH] [--source NAME]... [--since ISO8601]`.
- `--data-dir` vaut par défaut `Settings().data_dir`.
- Codes de sortie :
  - `init` : 1 sur `ScaffoldExistsError` (message listant les fichiers) ;
  - `validate-config` et `collect` : 1 sur `ConfigError`, avec le message sur stderr ;
  - `collect` : 2 si `report.all_failed`, 0 sinon.
- `collect` ouvre un `httpx.Client(timeout=settings.http_timeout_s, headers={"User-Agent":
  settings.user_agent}, follow_redirects=True)` dans un `with`.
- `logging` est configuré dans le callback Typer, au niveau `settings.log_level`.

- [ ] **Étape 1 : ajouter la dépendance**

```bash
uv add typer
```

- [ ] **Étape 2 : écrire les tests qui échouent**

Avec `typer.testing.CliRunner` :
- `test_init_then_validate` : les deux commandes renvoient 0.
- `test_init_existing_exits_1`.
- `test_validate_invalid_exits_1_with_field` : stderr contient
  `config/sources.yaml: sources.`.
- `test_collect_with_fake_factory` : la fabrique factice renvoie 2 `FakeSource`. Code 0, les
  items sont écrits, un rapport existe dans `state/runs/`.
- `test_collect_all_failed_exits_2`.
- `test_collect_only_and_since_forwarded`.
- `test_entry_point_declared` : `importlib.metadata.entry_points(group="console_scripts")`
  contient `auto-biblio`. Lancer `uv sync` avant.

- [ ] **Étapes 3 à 6 : lancer les tests (échec), implémenter (chaque commande parse ses
  arguments, appelle le domaine ou l'étape, formate la sortie, et ne contient pas de logique
  métier), relancer (succès), puis commit**

```bash
git add pyproject.toml uv.lock src/auto_biblio/cli.py tests/test_cli.py
git commit -m "feat(cli): init, validate-config and collect commands"
```

---

### Tâche 13 : nettoyage du template, exemple et documentation

**Files :**
- Delete : `src/auto_biblio/core.py`, `tests/test_core.py`, `examples/quickstart.py`
- Create : `examples/dedup.py`
- Modify : `tests/test_examples.py`, `README.md`, `docs/index.md`, `docs/getting-started.md`,
  `zensical.toml` (nav : ajouter « Design » avec les deux specs et ce plan)

**Interfaces :**
- Consumes : `canonical_id`, `Item`, `Sighting`, `merge_items`.

- [ ] **Étape 1 : écrire le test qui échoue**

Dans `tests/test_examples.py`, remplacer le test existant par `test_dedup_example`. La sortie
attendue est exactement :

```
arxiv:2410.12345 — 3 sightings (arxiv, hf-papers, hn)
```

- [ ] **Étape 2 : lancer le test et vérifier qu'il échoue**

Run : `uv run pytest tests/test_examples.py -v`

- [ ] **Étape 3 : écrire `examples/dedup.py`**

Le script construit 3 items vus respectivement sur arXiv (`/abs/…v2`), HF (`/papers/…`) et HN
(`/pdf/…v3`), les fusionne avec `merge_items`, puis affiche la ligne ci-dessus.

- [ ] **Étape 4 : supprimer les fichiers de démo et mettre à jour la documentation**

- `README.md` et `docs/index.md` : décrire ce que fait l'outil, en renvoyant à la vision.
- `docs/getting-started.md` : `uv tool install`, `auto-biblio init`, `validate-config`,
  `collect`, et la table des variables `AUTO_BIBLIO_*`.

- [ ] **Étape 5 : vérification complète**

Run : `make check`. Attendu : lint, pyright, tests (couverture ≥ 90 %) et docs strictes au
vert.

- [ ] **Étape 6 : essai réel, manuel et hors CI**

```bash
uv run auto-biblio init /tmp/ab-data && uv run auto-biblio collect --data-dir /tmp/ab-data
```

Attendu : code 0 ; les fichiers `state/items/*.jsonl` sont non vides ; le rapport liste les 6
types de sources. Relancer la commande : `git diff --no-index` ne montre aucun changement dans
`items/` ni `signals/`. Si une source réelle échoue, corriger son parsing et ajouter le cas à
ses fixtures.

- [ ] **Étape 7 : commit**

```bash
git add -A
git commit -m "docs: replace template demo with dedup example and collection docs"
```
