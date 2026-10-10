# Sous-projet 3 — analyse et base de connaissances

- **Date** : 2026-10-10
- **Statut** : validé en brainstorming
- **Vision** : `2026-10-10-auto-biblio-vision-design.md` (§3, §6, §8, §9 et §12)
- **Dépend de** : sous-projet 2, `2026-10-10-triage-design.md`

## 1. Objectif

Chaque semaine, transformer les items retenus par le triage en une **base de connaissances
vivante** dans le repo de données :

- une **fiche** par contenu retenu : courte, ou approfondie à partir du texte intégral ;
- une **page thème** réécrite par semaine, en rotation, qui condense l'état de l'art ;
- un **changelog** hebdomadaire, repris dans le digest.

L'autonomie est totale : le pipeline commite directement, et toute évolution est visible dans
le changelog et le digest. L'annulation se fait par `git revert`.

### Critères d'acceptation

1. `auto-biblio analyze` lit le `TriageRun` de la semaine et produit ou met à jour les fiches
   dans `kb/notes/`, une page thème dans `kb/themes/`, le changelog dans `kb/changelog/` et
   le journal dans `state/analysis/`.
2. Les `deep_count` meilleurs items retenus ont une fiche approfondie, issue du texte intégral
   quand l'extraction réussit ; les autres items retenus ont une fiche courte.
3. Relancer `analyze` pour la même semaine ne produit aucun diff dans `kb/` : les appels LLM
   sont servis par le cache et l'écriture est déterministe.
4. Une réécriture de page thème ne perd jamais un lien sans justification explicite.
5. La section `## Mes notes` d'une fiche n'est jamais modifiée par le pipeline.
6. Le digest renvoie vers les fiches, résume les analyses approfondies et contient une section
   « Évolutions de la base ». Le digest sort même si `analyze` a échoué.
7. Le budget hebdomadaire est partagé avec le triage.
8. `make check` passe.

### Hors périmètre

- Les fiches « technique » transverses (par exemple GraphRAG), qui demandent d'extraire et de
  dédoublonner des entités : v2.
- Le site consultable : sous-projet 4. En attendant, les liens pointent vers les fichiers du
  repo de données sur GitHub.
- L'assistant local : sous-projet 5.

## 2. Flux

```
HEBDOMADAIRE (weekly.yml)
  triage   (existant)
  analyze
    1. sélection    : items retenus du TriageRun. Les deep_count meilleurs (final_score,
                      slot "theme") sont approfondis, les autres traités en court. Un item
                      déjà fiché n'est refait que pour passer de court à approfondi, ou si
                      la version du prompt a changé.
    2. extraction   : texte intégral des items approfondis (§4)
    3. fiches       : rôles LLM short_note et deep_analysis
    4. page thème   : rôle synthesis, un thème en rotation (§3.3)
    5. changelog    : kb/changelog/AAAA-Www.md
    6. journal      : state/analysis/AAAA-Www.json
  digest   (enrichi : liens, extrait d'analyse, « Évolutions de la base »)
```

Ordre de consommation du budget dans `analyze` :
1. les fiches courtes ;
2. les fiches approfondies, par rang ;
3. la page thème.

Quand le budget s'épuise, ce qui reste à faire saute.

## 3. Modèle de données

### 3.1 Arborescence (repo de données)

```
kb/
├── notes/
│   ├── papers/<slug>.md      # kind paper
│   ├── tools/<slug>.md       # kind tool : repos et releases (une fiche par repo)
│   └── posts/<slug>.md       # kind post : billets, newsletters, discussions
├── themes/<theme-id>.md
└── changelog/AAAA-Www.md
state/analysis/AAAA-Www.json
```

- **Slug** : l'`ItemId` dont les caractères hors `[a-z0-9.-]` deviennent `-`. Par exemple
  `arxiv:2410.12345` devient `arxiv-2410.12345` et `gh:owner/repo` devient
  `gh-owner-repo`.
- **Releases** : une release (`gh:owner/repo@tag`) met à jour la fiche de son repo
  (`gh:owner/repo`), avec un lien vers la release.
- **Correspondance des types** : `paper` donne une fiche `paper` ; `repo` et `release`
  donnent une fiche `tool` ; `blog_post` et `discussion` donnent une fiche `post`.

### 3.2 Fiche

Front-matter YAML (`NoteMeta`, Pydantic, figé) :

| Champ | Type | Note |
|---|---|---|
| `id` | `ItemId` | l'id du repo pour une release |
| `kind` | `paper \| tool \| post` | |
| `title` | `str` | |
| `url` | `str` | |
| `themes` | `tuple[ThemeId, ...]` | thèmes du verdict de triage (score ≥ 3), sinon thème d'affichage |
| `links` | `tuple[str, ...]` | code, papier, page projet, releases ; triés, sans doublon |
| `related` | `tuple[ItemId, ...]` | `Item.links` ; triés |
| `depth` | `short \| deep` | |
| `source_text` | `abstract \| full_text \| snippet \| title` | ce que le LLM a réellement lu |
| `first_seen` | `date` | |
| `analyzed_at` | `date` | |
| `model_id` | `str` | |
| `prompt_version` | `str` | |

Le corps est rendu par un gabarit fixe à partir de la sortie structurée du LLM :

```python
class ShortNote(BaseModel):  # rôle short_note
    summary: str  # 2 à 3 phrases
    contribution: str  # 1 phrase
    relevance: str  # pourquoi c'est utile pour les thèmes du lecteur


class DeepAnalysis(ShortNote):  # rôle deep_analysis
    problem: str
    method: tuple[str, ...]  # points
    results: tuple[str, ...]  # résultats chiffrés quand le texte en donne
    limitations: tuple[str, ...]
    positioning: str  # par rapport à l'existant
    takeaways: tuple[str, ...]  # ce qu'on peut en tirer en pratique
    further_reading: tuple[str, ...]  # URLs présentes dans le texte
    verdict: str  # 1 phrase
    confidence: Literal["low", "medium", "high"]
```

**Validation :** chaque URL de `further_reading` doit apparaître dans le texte fourni au LLM,
pour éviter les liens inventés. Si ce n'est pas le cas, la sortie est rejetée et le LLM refait
une tentative avec l'erreur.

**Mise en forme :** sections `## Résumé`, `## Contribution`, `## Pourquoi c'est utile`, puis,
pour une fiche approfondie, `## Problème`, `## Méthode`, `## Résultats`, `## Limites`,
`## Positionnement`, `## En pratique`, `## Pour aller plus loin`, `## Verdict`. La fiche se
termine toujours par `## Mes notes`.

**Fusion avec une fiche existante :**
- la section `## Mes notes` est reprise octet pour octet ;
- `first_seen` est conservé ;
- `links` et `related` sont unis ;
- une fiche approfondie n'est jamais rétrogradée en courte.

### 3.3 Page thème

Front-matter : `theme`, `label`, `updated_at`, `prompt_version`, `model_id`, `notes` (ids des
fiches utilisées).

```python
class ToolRef(BaseModel):
    name: str
    url: str
    note_id: ItemId | None


class RemovedLink(BaseModel):
    url: str
    reason: str


class ThemePageContent(BaseModel):  # rôle synthesis
    overview: str
    key_concepts: tuple[str, ...]
    dominant_approaches: tuple[str, ...]
    reference_tools: tuple[ToolRef, ...]
    open_questions: tuple[str, ...]
    further_reading: tuple[str, ...]  # URLs
    removed_links: tuple[RemovedLink, ...] = ()
```

**Conservation des liens :** toute URL de l'ancienne page (outils de référence et lectures)
doit figurer dans la nouvelle, ou dans `removed_links` avec une justification. Sinon la sortie
est rejetée et le LLM refait une tentative avec l'erreur. Après deux échecs, l'ancienne page
est conservée.

**Entrées du LLM :** l'ancienne page (contenu structuré relu depuis son front-matter et ses
sections), plus les fiches du thème, les plus récentes en premier, dans la limite de
`synthesis_max_input_tokens`.

**Rotation :** parmi les thèmes ayant reçu au moins une fiche créée ou approfondie cette
semaine, on prend celui dont `updated_at` est le plus ancien (une page absente compte comme la
plus ancienne). Si aucun thème n'a reçu de fiche, on prend le plus ancien de tous. Les
égalités sont départagées par l'ordre du profil.

### 3.4 Changelog et journal

```python
class NoteChange(BaseModel):
    note_id: ItemId
    title: str
    kind: NoteKind
    change: Literal["created", "deepened", "refreshed"]
    depth: Depth
    source_text: SourceText


class ChangelogEntry(BaseModel):
    week: str
    notes: tuple[NoteChange, ...]
    theme: ThemeId | None
    links_added: tuple[str, ...]
    links_removed: tuple[RemovedLink, ...]
    degradations: tuple[str, ...]


class AnalysisOutcome(BaseModel):
    item_id: ItemId
    note_id: ItemId
    status: Literal["created", "deepened", "refreshed", "skipped", "failed"]
    depth: Depth | None
    source_text: SourceText | None
    error: str | None = None


class AnalysisRun(BaseModel):
    week: str
    run_id: str
    generated_at: AwareDatetime
    outcomes: tuple[AnalysisOutcome, ...]
    theme: ThemeId | None
    changelog: ChangelogEntry
    usage: tuple[LLMUsage, ...]
    degradations: tuple[str, ...]
```

Le changelog est rendu en Markdown dans `kb/changelog/AAAA-Www.md`. L'`AnalysisRun` est écrit
en JSON dans `state/analysis/AAAA-Www.json`.

### 3.5 Configuration

`config/analysis.yaml` (`AnalysisConfig`, facultatif, valeurs par défaut) :

| Clé | Défaut | Rôle |
|---|---|---|
| `deep_count` | 4 | nombre d'items approfondis par semaine |
| `max_input_tokens` | 30000 | taille maximale du texte intégral transmis |
| `synthesis_max_input_tokens` | 40000 | taille maximale des fiches transmises pour une page thème |
| `relevance_threshold` | 3 | score LLM minimal pour rattacher une fiche à un thème |
| `chars_per_token` | 4 | conversion de tokens en caractères pour tronquer |

`config/llm.yaml` gagne les rôles `short_note`, `deep_analysis` et `synthesis`. Le modèle par
défaut ajoute `flash: google:gemini-3.5-flash` et donne à ces trois rôles la chaîne
`[flash, gemma]`. Le plafond de tokens par défaut passe à 600 000 (palier gratuit : simple
marge).

**Compatibilité :** `Role` devient `Literal["triage", "short_note", "deep_analysis",
"synthesis"]`. Une chaîne manquante n'est requise que par l'étape qui l'utilise : un
`llm.yaml` de la v0.3, sans les nouveaux rôles, continue de servir le triage, et `analyze`
échoue proprement en `ConfigError`.

## 4. Extraction (`extract/`)

Le port `TextExtractor` expose `extract(item) -> ExtractedText(text, source: SourceText,
links)`.

| Item | Tentatives, dans l'ordre |
|---|---|
| Papier `arxiv:` | `https://arxiv.org/html/<id>`, nettoyé avec trafilatura → `https://arxiv.org/pdf/<id>`, lu par pypdf → résumé |
| Repo ou release | README par l'API GitHub, plus les notes de la dernière release (`/releases/latest`) → description |
| Billet ou newsletter | page de l'article, nettoyée avec trafilatura → résumé ou `og:description` |
| Discussion sans lien externe | titre et résumé |

**Nettoyage :** on coupe le texte à la première section intitulée `References`,
`Bibliography`, `Acknowledgements` ou `Appendix`, sur une ligne seule ou en titre Markdown, puis
on tronque à `max_input_tokens × chars_per_token` caractères.

**Liens :** les URLs du texte extrait (regex `https?://`, dédoublonnées) servent de référence
pour valider `further_reading`.

**Cache :** `.cache/fulltext/<sha256(id)>.json`, hors git, restauré par le cache GitHub
Actions avec les embeddings.

**Accès réseau :** les requêtes arXiv passent par un `Throttle` de 3 s.

**Erreurs :** `ExtractionError` (HTTP, contenu vide, PDF illisible) déclenche le repli
suivant. Quand tous les replis échouent, la fiche est analysée sur le résumé, avec
`source_text: abstract` et `depth: short`, et une dégradation est journalisée.

## 5. Digest

- Chaque item qui a une fiche affiche un lien « fiche » vers
  `https://github.com/<data_repo>/blob/main/kb/notes/<kind>s/<slug>.md`.
- Un item approfondi affiche en plus le `verdict` de son analyse.
- Une section « Évolutions de la base » liste les fiches créées ou approfondies, la page thème
  réécrite et les liens retirés avec leur justification.
- `digest` lit l'`AnalysisRun` de la semaine s'il existe. Sinon, le digest sort comme en v0.3.

## 6. Erreurs et budget

| Erreur | Réaction |
|---|---|
| `ExtractionError` | repli (§4), puis analyse courte sur le résumé |
| `ChainExhaustedError` sur une fiche | une fiche existante est conservée, une nouvelle n'est pas créée ; l'item est `failed` |
| `BudgetExhaustedError` | arrêt des appels ; le reste est `skipped` et journalisé |
| Conservation des liens violée deux fois | l'ancienne page est conservée ; dégradation |
| `TriageRunMissingError` | `analyze` échoue (code 1) ; `digest` n'est pas bloqué |

**Budget :** le ledger est initialisé avec la somme de l'usage du `TriageRun` et de
l'`AnalysisRun` existant de la même semaine.

## 7. Modules

| Module | Contenu | E/S |
|---|---|---|
| `domain/kb.py` | `NoteMeta`, `ShortNote`, `DeepAnalysis`, `ThemePageContent`, `ChangelogEntry`, slugs, rendu et relecture Markdown, fusion, conservation des liens | pur |
| `domain/analysis.py` | sélection court/approfondi, rattachement aux thèmes, rotation, `AnalysisRun` | pur |
| `extract/` | `TextExtractor`, `ArxivExtractor`, `RepoExtractor`, `ArticleExtractor`, nettoyage, cache | réseau, disque |
| `llm/prompts/notes_v1.py`, `theme_page_v1.py` | prompts et validations | — |
| `store/kb.py`, `store/analysis.py` | `kb/` et `state/analysis/` | fichiers |
| `stages/analyze.py` | orchestration | — |
| `repo_config/analysis.py` | `AnalysisConfig` | — |

Nouvelles dépendances : `pypdf`, `trafilatura`.

## 8. Tests

- **Extracteurs** : `MockTransport` et fixtures (page arXiv HTML, PDF minimal, README, billet,
  page vide), coupure des références, troncature, chaîne de replis.
- **Domaine** : slugs, aller-retour Markdown d'une fiche et d'une page thème, fusion (`## Mes
  notes` préservée, pas de rétrogradation), validation de `further_reading`, conservation des
  liens, rotation.
- **Étape** : `FakeRunner` pour les trois rôles. On couvre la relance sans diff, l'extraction
  en échec qui donne une fiche courte, le budget épuisé qui fait sauter la page thème, et le
  passage de court à approfondi.
- **Digest** : liens vers les fiches, verdict, « Évolutions de la base », digest sans
  `AnalysisRun`.
- **CLI** : `analyze` avec services simulés.
