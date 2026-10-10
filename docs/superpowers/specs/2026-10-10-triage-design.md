# Sous-projet 2 — triage

- **Date** : 2026-10-10
- **Statut** : en attente de relecture
- **Vision** : `2026-10-10-auto-biblio-vision-design.md` (§6, §7, §9, §11 et §12)
- **Dépend de** : sous-projet 1, `2026-10-10-socle-collecte-design.md`

## 1. Objectif

Chaque semaine, transformer les quelques milliers d'items collectés en une **liste courte,
classée et justifiée** : 15 à 20 items groupés par thème, plus 2 découvertes. La liste est
envoyée par mail sous forme de **digest brut**. Le tri démarre sans jeu de référence étiqueté :
il combine l'adéquation au profil et la popularité. Il devient ensuite **adaptatif** grâce à
ton feedback, capté depuis le digest.

Principes directeurs :

- **Modèles de décision légers.** Embeddings locaux, scores en percentiles, régression
  logistique et un LLM bon marché pour le triage. Pas d'agent, pas de modèle lourd.
- **Équité entre sources.** Un item ne doit pas être favorisé parce que sa source fournit plus
  de texte (arXiv) ou des signaux plus gros (étoiles GitHub).
- **Rejouable.** Toute décision est journalisée avec les variables qui l'ont produite.

### Critères d'acceptation

1. `auto-biblio triage` produit `state/triage/<semaine ISO>.json` à partir de `state/`, en
   respectant les plafonds de budget. Le relancer pour la même semaine réutilise le cache LLM
   et ne dépasse jamais le budget de la semaine.
2. `auto-biblio digest` envoie un mail HTML : items groupés par thème, source, justification,
   badge « revenant », liens 👍/👎 et pied de page sur la santé du pipeline.
   `digest --dry-run` écrit le HTML sur disque au lieu de l'envoyer.
3. `auto-biblio feedback ingest` transforme les issues `feedback` du repo de données en
   événements, dans `state/feedback/`, puis ferme les issues.
4. `auto-biblio signals refresh` met à jour les signaux de popularité des items déjà connus.
5. Le triage aboutit même si le LLM est indisponible ou si le budget est épuisé : les items non
   triés sont marqués « non vérifié ».
6. Dès que les seuils de feedback sont atteints, le scoring appris remplace les poids fixes,
   sauf si son AUC, mesurée uniquement sur des labels fiables, est sous le minimum.
   `auto-biblio eval scoring` compare les variantes à la demande.
7. Aucune constante de décision n'est codée en dur : toutes sont dans `config/triage.yaml` ou
   `config/llm.yaml`, et validées au chargement.
8. `make check` passe (lint, pyright strict, couverture ≥ 90 %, docs).

### Hors périmètre

- Extraction du contenu intégral, fiches, pages thème : sous-projet 3.
- Site et digest final : sous-projet 4.
- Feedback implicite : sous-projet 5. Le format d'événement est prévu dès maintenant (§3.6).
- **Enrichissement Semantic Scholar, retiré par rapport à la vision.** Un papier de 7 jours n'a
  quasiment pas de citations, et les revenants sont détectés par les autres signaux. On le
  réintroduira si le feedback montre un manque.

## 2. Flux

```
QUOTIDIEN (daily.yml, 05:00 UTC, sans LLM)
  collect               (existant)
  signals refresh       mise à jour des signaux des items connus (§4)
  feedback ingest       issues `feedback` → state/feedback/AAAA-MM.jsonl → fermeture de l'issue
  health check          échec si aucun TriageRun depuis `alert_after_days` jours

HEBDOMADAIRE (weekly.yml, dimanche 05:30 UTC)
  triage
    1. fenêtre          items vus pendant `window_days` + candidats revenants
    2. embed            textes normalisés et ancres des thèmes (cache des embeddings)
    3. variables        un FeatureVector par item                                 (pur)
    4. présélection     portes, plancher par famille, places découverte          (pur)
    4b. contexte        ContextFetcher pour les candidats sans résumé
    5. triage LLM       lots, via StructuredLLM (chaîne, cache, budget)
    6. sélection        score final, porte LLM, quotas                           (pur)
    7. journal          state/triage/AAAA-Www.json
  digest
    state/triage/AAAA-Www.json → HTML → SMTP
```

`triage` et `digest` sont deux commandes distinctes. Si l'envoi du mail échoue, on relance
`digest` sans repayer d'appels LLM.

## 3. Modèle de données

Tous les modèles sont des modèles Pydantic immuables (`frozen=True`).

### 3.1 Familles de source

```python
SourceFamily = Literal["paper", "repo", "discussion", "feed"]
```

| `SourceType` | Famille |
|---|---|
| `arxiv`, `hf_papers` | `paper` |
| `github_search`, `github_releases` | `repo` |
| `hackernews` | `discussion` |
| `rss` | `feed` |

Pour un item vu sur plusieurs sources, la famille retenue est celle de la source qui a fourni le
texte embeddé. Si plusieurs sources fournissent du texte, on applique la priorité
`paper > repo > feed > discussion`.

### 3.2 Texte normalisé et niveau de contexte

```python
ContextLevel = Literal["title_only", "snippet", "abstract"]
```

- **Pour l'embedding** : titre + au plus `embed_summary_words` mots du résumé (30 par défaut).
  La forme est la même pour tous les items, ce qui corrige le biais de longueur.
- **Pour le LLM** : titre + résumé complet, ou extrait du `ContextFetcher` (au plus
  `context_max_words`, 150 par défaut).
- `context_level` vaut `abstract` si l'item a un résumé, `snippet` si le texte vient du
  `ContextFetcher`, `title_only` sinon.

### 3.3 `FeatureVector` (`domain/features.py`)

| Champ | Type | Note |
|---|---|---|
| `item_id` | `ItemId` | |
| `family` | `SourceFamily` | |
| `context_level` | `ContextLevel` | |
| `theme_similarity` | `dict[ThemeId, float]` | cosinus brut, conservé pour le diagnostic |
| `theme_percentile` | `dict[ThemeId, float]` | rang au sein de la famille, entre 0 et 1 (§5.1) |
| `relevance` | `float` | `max_t(weight_t × theme_percentile_t)` |
| `popularity` | `float` | §5.3 ; `neutral_popularity` (0,5) si l'item n'a aucun signal |
| `source_count` | `int` | nombre de familles distinctes parmi les sightings |
| `watched` | `bool` | repo ou auteur suivi par un thème |
| `revenant` | `bool` | §5.6 |
| `age_days` | `float` | depuis `published_at`, ou depuis `first_seen` à défaut |

### 3.4 Triage LLM (`llm/prompts/triage_v1`)

```python
class TriageInput(BaseModel):
    ref: str  # "i07" : référence courte, propre au lot
    title: str
    text: str | None
    source: str
    kind: ItemKind
    context_level: ContextLevel


class TriageVerdict(BaseModel):
    ref: str
    relevance: dict[ThemeId, int]  # de 0 à 5, uniquement pour les thèmes concernés
    item_type: Literal["advance", "tool", "survey", "opinion", "other"]
    novelty: Literal["low", "medium", "high"]
    confidence: Literal["low", "medium", "high"]
    reason: str  # une phrase, au plus 30 mots


class TriageBatch(BaseModel):
    verdicts: tuple[TriageVerdict, ...]
```

**Validation de `TriageBatch`, faite dans la tâche avec le contexte du lot :**
- les `ref` retournées sont exactement celles du lot ;
- chaque `ThemeId` existe dans le profil ;
- `reason` fait au plus 30 mots.

**Contenu du prompt :**
- le profil (label et description de chaque thème) et le niveau de contexte de chaque item ;
- la consigne de noter la **pertinence probable**, sans pénaliser un item parce qu'il a peu de
  texte ;
- aucune fonctionnalité propre à un fournisseur.

### 3.5 Journal hebdomadaire : `TriageRun` (`state/triage/AAAA-Www.json`)

```python
class ScoredItem(BaseModel):
    item_id: ItemId
    features: FeatureVector
    prescore: float
    verdict: TriageVerdict | None  # None : non trié (budget épuisé, lot abandonné)
    final_score: float | None
    slot: Literal["theme", "discovery"] | None  # None : candidat non retenu
    theme: ThemeId | None  # thème sous lequel l'item apparaît dans le digest


class ScoringReport(BaseModel):
    version: str  # "fixed-v1" ou "learned-<date>"
    reliable_labels: int
    auc_without_weak: float | None
    auc_with_weak: float | None
    coefficients: dict[str, float]  # vide pour les poids fixes


class TriageRun(BaseModel):
    week: str  # semaine ISO, "2026-W41"
    run_id: str
    generated_at: AwareDatetime
    scoring: ScoringReport
    items: tuple[ScoredItem, ...]  # tous les candidats, retenus ou non
    usage: tuple[LLMUsage, ...]
    degradations: tuple[str, ...]  # bascules, budget atteint, mode dégradé…
```

Le journal garde aussi les **candidats non retenus**. Ils servent à l'apprentissage (§5.9) et à
comprendre a posteriori pourquoi un item a été écarté.

### 3.6 Feedback (`state/feedback/AAAA-MM.jsonl`)

```python
class FeedbackEvent(BaseModel):
    item_id: ItemId
    polarity: Literal[1, -1]
    channel: Literal["explicit"]  # "implicit" sera ajouté par le sous-projet 5
    at: AwareDatetime
    digest_week: str | None
    origin: str  # "issue#123"
```

**Issue de feedback :**
- Chaque item du digest porte deux liens vers
  `https://github.com/<repo de données>/issues/new?labels=feedback&title=<titre>&body=week: <semaine>`.
- Le titre suit la forme `👍 <item_id>` ou `👎 <item_id>`, et il est analysé par une regex
  stricte.
- L'ingestion est idempotente : la clé est le numéro de l'issue.

**Si l'issue est mal formée** (`FeedbackParseError`) : on publie un commentaire explicatif, on
ajoute le label `feedback-invalid` et l'issue reste ouverte.

### 3.7 Couche LLM (`llm/`)

```python
class StructuredLLM(Protocol):
    def run[T: BaseModel](self, task: LLMTask[T]) -> LLMResult[T]: ...


class LLMTask[T: BaseModel](BaseModel):
    role: Literal["triage"]  # les autres rôles arrivent avec le sous-projet 3
    prompt_version: str
    payload: BaseModel
    output_type: type[T]


class LLMUsage(BaseModel):
    role: str
    model_id: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    cached: bool
    fallback_from: str | None


class LLMResult[T: BaseModel](BaseModel):
    output: T
    usage: LLMUsage
```

**Implémentations, de l'intérieur vers l'extérieur :**
1. `PydanticAILLM` : l'adaptateur vers pydantic-ai.
2. `ModelChain` : bascule au modèle suivant sur quota, indisponibilité ou sortie invalide
   après une nouvelle tentative.
3. `BudgetedLLM` : réserve le coût estimé auprès du `BudgetLedger` avant l'appel, enregistre le
   coût réel après.
4. `CachedLLM` : cache dans `state/llm_cache/<prompt_version>/<sha256>.json`. La clé est
   `sha256(prompt_version, model_id, payload)`. Le cache est commité dans le repo de données,
   ce qui rend les relances gratuites.

### 3.8 Configuration (repo de données)

`config/llm.yaml` :

```yaml
models:
  flash-lite:
    id: google:gemini-3.5-flash-lite       # palier gratuit (vérifié le 2026-10-10)
    input_usd_per_mtok: 0
    output_usd_per_mtok: 0
    batch_size: 20
  haiku:
    id: anthropic:claude-haiku-5-5         # tarif vérifié le 2026-10-10
    input_usd_per_mtok: 0.10
    output_usd_per_mtok: 0.50
    batch_size: 15
chains:
  triage: [flash-lite, haiku]
weekly_budget:
  usd: 0.50
  tokens: 300000
```

`config/triage.yaml` : **toutes les constantes de décision**, chacune avec ses bornes de
validation. Les valeurs ci-dessous sont les valeurs par défaut écrites par `init`.

| Clé | Défaut | Rôle |
|---|---|---|
| `window_days` | 7 | fenêtre des items de la semaine |
| `reference_days` | 28 | population de référence des percentiles |
| `min_family_population` | 30 | en dessous, on prend le percentile global |
| `embed_summary_words` | 30 | longueur du texte embeddé |
| `context_max_words` | 150 | longueur de l'extrait du `ContextFetcher` |
| `neutral_popularity` | 0.5 | popularité d'un item sans signal |
| `weights.relevance` / `popularity` / `multi_source` / `watched` | 0.60 / 0.25 / 0.10 / 0.15 | pré-score |
| `relevance_gate` | 0.75 | pertinence minimale pour être candidat |
| `candidates` | 50 | taille de la présélection |
| `family_floor` | 5 | places réservées par famille dans la présélection |
| `discovery.slots` | 2 | places découverte |
| `discovery.min_popularity` | 0.95 | popularité minimale pour une découverte |
| `llm_weight` (λ) | 0.6 | part du LLM dans le score final |
| `llm_gate` | 1 | `max relevance_t ≤ llm_gate` ⇒ item éliminé |
| `selected` | 18 | taille maximale de la sélection |
| `per_theme_max` | 4 | quota par thème |
| `revenant.min_age_days` | 30 | âge minimal d'un revenant |
| `revenant.min_popularity` | 0.90 | seuil de popularité d'un revenant |
| `revenant.cooldown_weeks` | 8 | délai avant qu'un même item puisse revenir |
| `refresh.horizon_days` | 180 | âge maximal des items dont on rafraîchit les signaux |
| `refresh.max_items_per_day` | 1000 | plafond quotidien du rafraîchissement |
| `learning.min_reliable_labels` | 50 | seuil d'activation de l'apprentissage |
| `learning.min_per_polarity` | 10 | idem, par polarité |
| `learning.min_auc` | 0.65 | AUC minimale pour utiliser le modèle appris |
| `learning.weak_negative_weight` | 0.2 | poids des négatifs faibles dans la loss |
| `learning.weak_negative_grace_days` | 14 | délai avant qu'un item affiché sans réaction devienne un négatif faible |
| `learning.cv_folds` | 5 | plis de la validation croisée groupée par semaine |
| `alert_after_days` | 8 | alerte quand aucun `TriageRun` n'est produit |

### 3.9 Cache des embeddings (hors git)

- Emplacement : `.cache/embeddings/<modèle>/`, en shards `.npz` ; clé `sha256(texte normalisé)`.
- Le cache est persisté entre deux runs par `actions/cache`. Ce n'est qu'une optimisation :
  s'il est perdu, on recalcule tout, en 1 à 2 minutes.
- Les ancres des thèmes sont recalculées à chaque run.
- On ne commite pas les vecteurs : ils pèseraient environ 400 Mo par an d'historique git.

## 4. Rafraîchissement des signaux (`stages/refresh.py`)

**Le besoin.** Le sous-projet 1 n'enregistre un signal que lorsqu'une source renvoie l'item.
Sans rafraîchissement, un item n'a souvent qu'une seule observation : impossible de mesurer une
vélocité, et donc de détecter un revenant par la popularité.

`SignalRefreshStage` tourne chaque jour, sur les items vus depuis moins de
`refresh.horizon_days` jours, dans la limite de `refresh.max_items_per_day` :

| Type d'item | Signal | Appel |
|---|---|---|
| `repo` (`gh:owner/repo`) | `gh_stars` | API GraphQL GitHub, 100 repos par requête |
| `paper` vu sur HF Papers | `hf_upvotes` | API Hugging Face, une requête par papier |

- **Priorité** quand le plafond est atteint : d'abord les items sélectionnés ou candidats dans un
  `TriageRun` récent, puis les plus récents.
- **HN** : on ne rafraîchit pas. Un nouveau fil HN sur un ancien contenu arrive déjà par la
  collecte, sous forme d'un nouveau sighting (§5.6).
- **Une observation par jour au plus**, par `(item_id, kind)` : c'est déjà la règle de
  `SignalStore`.

## 5. Scoring et sélection (`domain/scoring.py`, `domain/selection.py`, purs)

### 5.1 Population de référence et percentiles

- Les percentiles sont calculés par rapport aux items vus pendant les `reference_days` derniers
  jours.
- Ils sont calculés **par famille** (§3.1) pour la pertinence, et **par type de signal** pour la
  popularité.
- Si la population d'une famille est sous `min_family_population`, on utilise la population
  globale.
- Égalités : rang moyen.

### 5.2 Pertinence profil

- **Deux ancres par thème** : `description`, et `"<label> : <mots-clés joints>"`. On n'embedde
  pas les mots-clés isolés.
- `sim_t = max(cos(item, ancre))` sur les ancres du thème.
- `pct_t` = percentile de `sim_t` au sein de la famille de l'item.
- `relevance = max_t(weight_t × pct_t)`.

### 5.3 Popularité

- Pour chaque type de signal, la vélocité vaut `log1p(max(Δ, 0)) / jours`.
  - Δ est l'écart entre la dernière et la première observation dans la fenêtre.
  - Pour un item apparu dans la fenêtre avec une seule observation, Δ est sa valeur.
- On prend le percentile de cette vélocité parmi les items qui ont ce type de signal.
- `popularity` est le maximum sur les types de signal disponibles, ou `neutral_popularity` si
  l'item n'en a aucun.

### 5.4 Exclusions

**Filtre dur, appliqué avant tout score** : un item est éliminé si une règle `exclude` d'un
thème, ou `global_exclude`, correspond à son titre ou à son texte. La comparaison est
insensible à la casse et porte sur des mots entiers. Un item exclu ne revient jamais, ni par la
popularité ni par les places découverte.

### 5.5 Pré-score et présélection

```
multi    = min(source_count − 1, 2) / 2
prescore = w_rel × relevance + w_pop × popularity + w_multi × multi + w_watch × watched
```

1. **Porte de pertinence.** Seul un item avec `relevance ≥ relevance_gate` peut devenir
   candidat de thème.
2. **Déjà vus.** Un item déjà affiché dans un digest précédent est écarté, sauf s'il est
   revenant.
3. **Plancher par famille.** Chaque famille reçoit d'abord jusqu'à `family_floor` places, prises
   dans son propre top de pré-score. Le reste des `candidates` places va aux meilleurs
   pré-scores, toutes familles confondues. Raison : les percentiles égalisent les échelles,
   mais pas les volumes, et arXiv représente 70 à 80 % des items.

### 5.6 Revenants

Un item est revenant s'il a au moins `revenant.min_age_days` jours et vérifie au moins une de ces
conditions :

- `popularity ≥ revenant.min_popularity` sur la fenêtre ;
- un sighting apparu dans la fenêtre provient d'une famille où l'item n'avait jamais été vu.

Un même item ne peut revenir qu'une fois tous les `revenant.cooldown_weeks`, ce qu'on vérifie
dans les `TriageRun` précédents. Les revenants passent par la même porte de pertinence, et ils
portent le badge « revient au goût du jour ».

### 5.7 Places découverte

**Éligibilité :**
- `relevance < relevance_gate` ;
- `popularity ≥ discovery.min_popularity` ;
- l'item n'est pas exclu ;
- il n'a jamais été affiché.

**Choix :** on prend les `discovery.slots` items les plus populaires, avec au plus un item par
famille. Ces items passent par le triage LLM pour obtenir leur justification, mais la porte LLM
ne leur est pas appliquée.

### 5.8 Score final et sélection

```
llm_rel = max_t(weight_t × relevance_t / 5)
final   = λ × llm_rel + (1 − λ) × prescore        (poids fixes)
final   = P(👍 | variables, llm_rel)               (modèle appris, §5.9)
```

- **Porte LLM** : si `max_t relevance_t ≤ llm_gate`, l'item est éliminé.
- **Thème d'affichage** : celui qui maximise `weight_t × relevance_t`.
- **Quotas** : `per_theme_max` items par thème, `selected` au total. Le digest est plus court si
  moins d'items passent les portes.
- **Item non trié** par le LLM : `final = prescore`, il passe directement aux quotas, et il est
  affiché avec la mention « non vérifié ».

### 5.9 Apprentissage (`domain/learning.py`)

**Labels**, construits au moment de l'entraînement, en rapprochant les `TriageRun` et les
`FeedbackEvent` :

| Label | Origine | Poids | Évaluation |
|---|---|---|---|
| `positive` | 👍 | 1 | oui |
| `negative` | 👎 | 1 | oui |
| `weak_negative` | affiché, sans réaction après `weak_negative_grace_days` jours | `weak_negative_weight` | **jamais** |

- Les variables d'un item sont celles du `TriageRun` de la semaine où il a été affiché.
- Un 👍 ou un 👎, même tardif, remplace le label faible.
- On ne stocke pas les négatifs faibles comme événements : on les déduit à chaque fois.

**Modèle** : une régression logistique scikit-learn.
- Variables : `relevance`, `popularity`, `multi`, `watched`, `revenant`, `llm_rel`, un indicateur
  par famille et un par `context_level`.
- Les poids d'échantillon portent le poids des labels faibles.

**Activation**, à chaque `triage` :
1. Pré-requis : au moins `learning.min_reliable_labels` labels fiables, dont au moins
   `learning.min_per_polarity` de chaque polarité.
2. On entraîne deux variantes : sans et avec négatifs faibles.
3. On les évalue par validation croisée **groupée par semaine de digest** (`cv_folds` plis).
   Les plis de test ne contiennent que des labels fiables ; les labels faibles ne servent qu'à
   l'entraînement.
4. On retient la variante qui a la meilleure AUC si elle atteint `learning.min_auc`. Sinon, on
   garde les poids fixes.
5. Les AUC et les coefficients sont journalisés dans `ScoringReport` et affichés dans le pied de
   page du digest.

`auto-biblio eval scoring` affiche les trois scénarios (poids fixes, appris, appris avec
négatifs faibles) sur l'historique disponible. Cette commande remplace le jeu de référence
`eval/golden.yaml` de la vision (§11).

## 6. Contexte des items sans résumé (`sources/context.py`)

`ContextFetcher` s'applique uniquement aux candidats présélectionnés qui n'ont pas de résumé,
soit 10 à 20 par semaine. Il ne fait aucun appel LLM.

| URL | Extrait |
|---|---|
| `github.com/owner/repo` | début du README (API GitHub) |
| `huggingface.co/<modèle>` | début de la fiche du modèle |
| autre | `og:description`, à défaut `<meta name="description">` |

- L'extrait est limité à `context_max_words` mots.
- En cas d'échec (`ContextFetchError` : HTTP, timeout, contenu vide), l'item reste en
  `title_only`. L'échec est journalisé mais ne compte pas comme une erreur du run.
- Le sous-projet 3 réutilisera ce module comme premier niveau d'extraction.

## 7. Digest brut (`publish/`)

- Le rendu se fait avec un template Jinja2, en HTML simple compatible avec les clients mail
  (styles en ligne). Une version texte l'accompagne.
- **Contenu :**
  - les items sont groupés par thème, dans l'ordre des scores ;
  - pour chaque item : titre avec lien, source, `reason`, `item_type`, badges « revenant » et
    « non vérifié », liens 👍/👎 ;
  - la section « Découvertes » contient les places découverte, avec la mention « hors de tes
    thèmes ».
- **Pied de page santé :**
  - sources en échec depuis N jours (d'après `state/runs/`) ;
  - bascules de modèle et budget consommé ;
  - `scoring.version` et AUC ;
  - nombre d'items non vérifiés.
- **Envoi** par le port `MailSender`, implémenté en SMTP Gmail avec un mot de passe
  d'application. La configuration passe par `Settings` : `smtp_host`, `smtp_user`,
  `smtp_password` et `digest_to`.

## 8. Erreurs et budget

### 8.1 Nouvelles erreurs (`domain/errors.py`)

| Erreur | Réaction |
|---|---|
| `ConfigError` (`llm.yaml`, `triage.yaml`) | échec immédiat |
| `EmbeddingError` | repli : `relevance` est calculée par correspondance des mots-clés (1 si un mot-clé apparaît, sinon 0) ; dégradation journalisée, digest marqué « mode dégradé » |
| `ProviderQuotaError`, `ProviderUnavailableError` | modèle suivant de la chaîne ; si la chaîne est épuisée, les lots restants ne sont pas triés |
| `LLMOutputInvalidError` | une nouvelle tentative avec l'erreur de validation, puis modèle suivant, puis le lot n'est pas trié |
| `BudgetExhaustedError` | arrêt des appels LLM, les lots restants ne sont pas triés |
| `ContextFetchError` | l'item reste en `title_only` |
| `FeedbackParseError` | commentaire sur l'issue et label `feedback-invalid` |
| `MailDeliveryError` | échec de `digest` (workflow en rouge) ; on relance `digest` seul |

### 8.2 `BudgetLedger` (`domain/budget.py`, pur)

- `reserve(estimate)` est appelé avant chaque appel et lève `BudgetExhaustedError` si l'un des
  deux plafonds serait dépassé.
- L'estimation vaut `ceil(caractères / 4 × 1,2) + max_output_tokens`.
- `settle(reservation, usage)` remplace l'estimation par la consommation réelle.
- Les tokens comptent pour tous les modèles, les dollars pour les modèles payants seulement. Un
  appel servi par le cache ne coûte rien.
- Le ledger est initialisé avec l'usage déjà journalisé pour la semaine. Une relance ne double
  donc pas le budget.

## 9. CLI et workflows

| Commande | Rôle |
|---|---|
| `auto-biblio signals refresh` | §4 |
| `auto-biblio feedback ingest` | §3.6 |
| `auto-biblio triage [--week AAAA-Www]` | §2, étapes 1 à 7 |
| `auto-biblio digest [--week …] [--dry-run]` | §7 |
| `auto-biblio eval scoring` | §5.9 |
| `auto-biblio health` | échec si aucun `TriageRun` depuis `alert_after_days` jours |

**Workflows** (modèles écrits par `init`) :

- `daily.yml` :
  - nouvelles étapes : `signals refresh`, `feedback ingest`, `health` ;
  - permission ajoutée : `issues: write`.
- `weekly.yml` (nouveau) :
  - restaure le cache des embeddings et du modèle fastembed ;
  - enchaîne `triage` puis `digest` ;
  - commite `state/` même en cas d'échec.
- **Secrets** : `GEMINI_API_KEY`, `ANTHROPIC_API_KEY`, `SMTP_PASSWORD`.
- **Mise à jour du repo de données existant** : il faut changer le tag épinglé, ajouter
  `weekly.yml`, `llm.yaml` et `triage.yaml`, et créer les labels `feedback` et
  `feedback-invalid`. La procédure est documentée dans `docs/`.

## 10. Nouveaux modules

| Module | Contenu | E/S |
|---|---|---|
| `domain/features.py` | familles, normalisation du texte, percentiles, `FeatureVector` | pur |
| `domain/scoring.py` | pertinence, popularité, pré-score, score final | pur |
| `domain/selection.py` | fenêtre, exclusions, revenants, présélection, découvertes, quotas | pur |
| `domain/learning.py` | construction des labels, validation croisée groupée, choix de la variante | pur (scikit-learn en mémoire) |
| `domain/budget.py` | `BudgetLedger` | pur |
| `domain/feedback.py` | `FeedbackEvent`, analyse du titre d'issue | pur |
| `embeddings/` | port `Embedder`, `FastEmbedder`, `CachedEmbedder` | modèle local, disque |
| `llm/` | port `StructuredLLM`, `PydanticAILLM`, `ModelChain`, `BudgetedLLM`, `CachedLLM`, prompts | réseau, disque |
| `sources/context.py` | `ContextFetcher` | réseau |
| `sources/refresh.py` | clients GraphQL GitHub et Hugging Face pour le rafraîchissement | réseau |
| `integrations/github_issues.py` | lecture, commentaire et fermeture des issues | réseau |
| `publish/` | rendu Jinja2, port `MailSender`, `SmtpMailSender` | réseau |
| `repo_config/llm.py`, `repo_config/triage.py` | `LLMConfig`, `TriageConfig` | — |
| `store/feedback.py`, `store/triage.py`, `store/llm_cache.py` | persistance | fichiers |
| `stages/refresh.py`, `stages/feedback.py`, `stages/triage.py`, `stages/digest.py` | orchestration | — |

**Nouvelles dépendances :** `fastembed`, `numpy`, `scikit-learn`, `pydantic-ai-slim[google,anthropic]`
et `jinja2`.

## 11. Tests

| Cible | Approche |
|---|---|
| Domaine | tests unitaires sur des `FeatureVector` construits à la main : percentiles (égalités, famille sous le minimum de population), portes, plancher par famille, quotas, découvertes, revenants (avec le délai avant retour), exclusions, ledger |
| Apprentissage | données synthétiques où le label dépend de `relevance` : le coefficient doit être positif et l'AUC au-dessus du seuil. On vérifie qu'aucun négatif faible n'apparaît dans un pli de test, que les plis respectent les semaines, et le repli sur les poids fixes. |
| `FastEmbedder` | le moteur fastembed est injecté par le constructeur et remplacé par un faux ; pas de téléchargement du modèle en CI |
| Étages en aval | `FakeEmbedder` : vecteurs déterministes dérivés d'un hash |
| Couche LLM | `TestModel` et `FunctionModel` de pydantic-ai : chaîne de secours, nouvelle tentative avec l'erreur de validation, cache, budget ; aucun réseau |
| Issues GitHub, `ContextFetcher`, rafraîchissement | `httpx.MockTransport` |
| Mail | faux `MailSender` ; snapshot du HTML rendu |
| De bout en bout | `TriageStage` puis `DigestStage` sur un repo de données temporaire avec fixtures |
| Exemples | `examples/` : un script de scoring sur des items fictifs, exécuté par `tests/test_examples.py` |

## 12. Points à vérifier à l'implémentation

- Identifiant, tarif et quota gratuit de Gemini 3.5 Flash-Lite et de Claude Haiku.
- Limites des API GraphQL GitHub et Hugging Face pour le rafraîchissement.
- Préremplissage des labels dans l'URL `issues/new` : il ne s'applique qu'aux utilisateurs qui
  ont les droits de triage, ce qui est le cas du propriétaire. Sinon, le workflow filtre sur le
  préfixe du titre.
- Taille du modèle fastembed `BAAI/bge-small-en-v1.5` et temps d'embedding sur un runner
  `ubuntu-latest`.
