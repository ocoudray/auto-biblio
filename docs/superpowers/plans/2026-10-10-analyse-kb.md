# Analyse et base de connaissances — plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal :** chaque semaine, une fiche par item retenu (courte, ou approfondie à partir du texte
intégral), une page thème réécrite en rotation et un changelog, commités dans `kb/` et repris
dans le digest.

**Architecture :**
- Domaine pur : `domain/kb.py` (fiches, pages thème, changelog, Markdown) et
  `domain/analysis.py` (sélection, rotation, journal).
- Extracteurs injectables (`extract/`) et prompts versionnés (`llm/prompts/`).
- Stores fichiers et une étape `stages/analyze.py`.
- La CLI et les workflows sont étendus.

**Spec :** `docs/superpowers/specs/2026-10-10-analyse-kb-design.md`. Les numéros de section
(« §3.2 ») renvoient à ce document.

## Global Constraints

- `CLAUDE.md` et les contraintes du plan du sous-projet 2 s'appliquent : TDD, pyright strict,
  couverture ≥ 90 %, aucun réseau dans les tests, horloge injectée, `make check` vert à chaque
  tâche.
- Les constantes de décision vivent dans `AnalysisConfig` ou `LLMConfig`, jamais en dur.
- **Écriture déterministe de `kb/`** : front-matter aux clés ordonnées, listes triées, une
  seule ligne vide entre sections, fin de fichier `\n`. Relancer ne doit produire aucun diff.
- La section `## Mes notes` est traitée comme une donnée opaque : jamais réécrite.

## Review Focus

1. **Aucune perte de lien** sur une page thème : tâche 3, `test_link_dropped_without_reason_rejected`.
2. **Annotations préservées** : tâche 2, `test_merge_keeps_my_notes_verbatim`.
3. **Aucun lien inventé** dans une fiche : tâche 6, `test_further_reading_must_come_from_text`.
4. **Relance sans diff** : tâche 8, `test_rerun_same_week_changes_nothing`.
5. **Le digest sort toujours** : tâche 9, `test_digest_without_analysis_run`.

---

### Tâche 1 : configuration (rôles, `analysis.yaml`, budget)

**Files :** `repo_config/llm.py`, `repo_config/analysis.py` (nouveau), `repo_config/loader.py`,
le modèle `llm.yaml`, et leurs tests.

- `Role = Literal["triage", "short_note", "deep_analysis", "synthesis"]`.
- `LLMConfig` n'exige plus de chaîne pour chaque rôle. `chain(role)` lève `ConfigError` quand
  le rôle n'a pas de chaîne. Pour un rôle présent, les noms de modèles restent validés.
- `AnalysisConfig` reprend les clés et valeurs par défaut du §3.5, avec `extra="forbid"` et des
  bornes. `RepoConfig.analysis` vaut `AnalysisConfig()` quand `config/analysis.yaml` est absent.
- Modèle `llm.yaml` : ajout de `flash` et des chaînes des trois rôles, plafond de 600 000
  tokens.
- Tests :
  - `test_role_chain_missing_is_config_error` ;
  - `test_v03_llm_yaml_still_loads` ;
  - `test_analysis_defaults` et `test_analysis_bounds` ;
  - `test_loader_reads_analysis`.

### Tâche 2 : fiches (`domain/kb.py`, partie 1)

- `note_slug(item_id)`, `note_kind(item_kind)`, `note_id_for(item_id)` (une release donne son
  repo), `note_path(kind, slug)`.
- `NoteMeta`, `ShortNote`, `DeepAnalysis` et `Note(meta, content, my_notes: str)`.
- `render_note(note) -> str` et `parse_note(text) -> Note`.
- `merge_note(existing, new) -> Note`, selon les règles de fusion du §3.2.
- Tests :
  - `test_slug` (arXiv, repo, release, url) ;
  - `test_note_roundtrip` ;
  - `test_render_is_deterministic` ;
  - `test_merge_keeps_my_notes_verbatim` ;
  - `test_merge_never_downgrades` ;
  - `test_merge_unions_links` ;
  - `test_parse_rejects_bad_front_matter`.

### Tâche 3 : pages thème et changelog (`domain/kb.py`, partie 2)

- `ThemePage(meta, content)`, avec `render_theme_page` et `parse_theme_page`.
- `page_links(content) -> frozenset[str]`.
- `check_links_kept(old, new, model_id)`, qui lève `LLMOutputInvalidError` en listant les
  liens manquants.
- `render_changelog(entry) -> str`.
- Tests :
  - `test_theme_page_roundtrip` ;
  - `test_link_dropped_without_reason_rejected` ;
  - `test_link_removed_with_reason_accepted` ;
  - `test_first_page_has_no_constraint` ;
  - `test_changelog_render`.

### Tâche 4 : sélection et journal (`domain/analysis.py`)

- `plan_notes(run, existing, cfg, prompt_versions) -> tuple[NotePlan, ...]`. Un `NotePlan`
  porte `item_id`, `note_id`, `depth` et `action` (`create`, `deepen`, `refresh` ou `skip`).
  Le rang suit `final_score` parmi les items `slot == "theme"` ; les découvertes sont toujours
  traitées en court.
- `note_themes(scored, cfg) -> tuple[ThemeId, ...]`.
- `pick_theme(profile_order, pages_updated, touched) -> ThemeId`.
- Modèles `AnalysisOutcome` et `AnalysisRun` (§3.4).
- Tests :
  - `test_top_items_are_deep` ;
  - `test_existing_deep_note_skipped` ;
  - `test_short_note_deepened_when_top` ;
  - `test_prompt_version_change_refreshes` ;
  - `test_releases_map_to_repo_note` ;
  - `test_discoveries_short` ;
  - `test_rotation_prefers_touched_oldest` ;
  - `test_rotation_without_touched`.

### Tâche 5 : extracteurs (`extract/`)

- `ExtractedText(text, source, links)`.
- `clean_text(text, max_chars)` : coupe aux références et annexes, puis tronque.
- Extracteurs à client `httpx` injecté :
  - `ArxivExtractor` : HTML avec trafilatura, puis PDF avec pypdf ;
  - `RepoExtractor` : README et dernière release ;
  - `ArticleExtractor` : article avec trafilatura.
- `CompositeExtractor` : dispatch selon l'item, replis, cache `.cache/fulltext`.
- `uv add pypdf trafilatura` ; stubs dans `typings/` si nécessaire.
- Tests :
  - `test_clean_cuts_references` et `test_clean_truncates` ;
  - `test_arxiv_html` et `test_arxiv_pdf_fallback` (PDF minimal en fixture) ;
  - `test_repo_readme_and_release` et `test_article` ;
  - `test_all_fail_raises` ;
  - `test_cache_hit_no_network` ;
  - `test_links_collected`.

### Tâche 6 : prompts (`llm/prompts/notes_v1.py`, `theme_page_v1.py`)

- `short_note_task(item, text, themes)` et `deep_analysis_task(item, extracted, themes)`.
  Consigne de rédaction en français, termes techniques en anglais.
- La validation de `deep_analysis` rejette toute URL de `further_reading` absente de
  `extracted.links` et du texte.
- `theme_page_task(theme, old_page, notes, max_chars)`. Sa validation appelle
  `check_links_kept`.
- Tests :
  - `test_further_reading_must_come_from_text` ;
  - `test_theme_task_rejects_lost_link` ;
  - `test_notes_truncated_to_budget` ;
  - `test_prompts_deterministic`.

### Tâche 7 : stores (`store/kb.py`, `store/analysis.py`)

- `KBStore(root)`, avec :
  - `read_note(note_id)` et `write_note(note)` ;
  - `notes_for_theme(theme)` ;
  - `read_theme(theme)` et `write_theme(page)` ;
  - `write_changelog(entry)` ;
  - `all_notes()`.
- `AnalysisStore(state_dir)`, avec `read(week)` et `write(run)`.
- Tests : allers-retours, écriture idempotente, fiche absente.

### Tâche 8 : étape `analyze` (`stages/analyze.py`)

- `AnalyzeStage(config, items, triage_store, analysis_store, kb, extractor, llm_factory,
  clock)`, avec `run(week=None) -> AnalysisRun`.
- Déroulé : les étapes 1 à 6 du §2, dans l'ordre budgétaire du §2. La gestion des erreurs suit
  le §6.
- Tests :
  - `test_creates_short_and_deep_notes` ;
  - `test_rerun_same_week_changes_nothing` ;
  - `test_extraction_failure_gives_short_note` ;
  - `test_budget_exhausted_skips_theme_page` ;
  - `test_failed_note_keeps_existing` ;
  - `test_theme_page_written_and_changelog`.

### Tâche 9 : digest enrichi

- `build_view` reçoit un `AnalysisRun | None`.
- `DigestItem` gagne `note_url` et `verdict`.
- `DigestView` gagne `kb_changes` (rendu de « Évolutions de la base »).
- Les templates HTML et texte sont mis à jour ; le snapshot est régénéré et relu.
- Tests :
  - `test_note_links_and_verdict` ;
  - `test_kb_changes_section` ;
  - `test_digest_without_analysis_run`.

### Tâche 10 : CLI et assemblage

- Commande `auto-biblio analyze [--data-dir] [--week]` ; codes de sortie 0 et 1.
- `Services` gagne `extractor`.
- Le texte extrait est mis en cache sous `root/.cache/fulltext`.
- `digest` passe l'`AnalysisRun` de la semaine à la vue.
- Tests : `test_analyze_command`, `test_analyze_needs_roles`, `test_digest_uses_analysis`.

### Tâche 11 : workflows, `init`, documentation et version 0.4.0

- `weekly.yml` : nouvelle étape `auto-biblio analyze` entre `triage` et `digest`, avec
  `continue-on-error: true` pour que le digest parte quand même ; le commit inclut `kb/`.
- `init` écrit `config/analysis.yaml` et `kb/.gitkeep`.
- Documentation : `docs/knowledge-base.md` et `docs/upgrade-0.4.md` ; navigation, README et
  index mis à jour.
- Version 0.4.0. Exemple `examples/note.py` : rendu d'une fiche à partir d'une sortie fictive.
- Tests : scaffold (nouveaux fichiers, configuration valide), contenu de `weekly.yml`.
