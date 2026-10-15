# Sous-projet 4 — site de la base de connaissances et digest final

- **Date** : 2026-10-14
- **Statut** : validé en brainstorming
- **Vision** : `2026-10-10-auto-biblio-vision-design.md` (§2, §10 et §12)
- **Dépend de** : sous-projet 3, `2026-10-10-analyse-kb-design.md`

## 1. Objectif

Publier chaque semaine la base de connaissances du repo de données sous forme de **site
statique privé** : pages thème, fiches, journal et archive des digests, avec une recherche
plein texte. Le digest renvoie vers ce site au lieu des fichiers GitHub.

### Décisions

| Sujet | Choix |
|---|---|
| Confidentialité | site privé : Cloudflare Pages protégé par Cloudflare Access (code à usage unique envoyé à l'adresse du propriétaire) |
| Adresse | `<projet>.pages.dev`, sans domaine personnel ; compte Cloudflare à créer |
| Contenu | pages thème, fiches et leurs index, journal hebdomadaire, archive des digests, recherche plein texte |
| Digest | seuls les liens changent : ils pointent vers le site, plus un lien « Voir en ligne » |
| Build | `auto-biblio site build` génère un projet zensical puis lance `zensical build` |
| Déploiement | envoi direct depuis GitHub Actions avec `wrangler pages deploy` |

### Critères d'acceptation

1. `auto-biblio site build --out <dossier>` produit un site statique complet à partir de `kb/`
   et `state/`, sans appel réseau ni LLM.
2. Le site contient : une page d'accueil, les pages thème, toutes les fiches, les index de
   fiches par type et par thème, une page par semaine de journal et une page par digest
   archivé, ainsi qu'un index de recherche.
3. Chaque fiche du site affiche en tête son lien source et ses métadonnées. Les fichiers de
   `kb/` ne sont pas modifiés.
4. Les liens internes (page thème → fiche, digest → fiche) sont résolus : le build de test en
   mode strict ne signale aucun avertissement.
5. Avec `config/site.yaml`, les liens du digest pointent vers le site, et le digest contient
   un lien « Voir en ligne » vers sa page d'archive. Sans ce fichier, le digest est inchangé.
6. Dans le workflow hebdomadaire, le site est construit et déployé avant l'envoi du digest. Un
   échec du site n'empêche jamais l'envoi du digest. En dry run, le site est construit,
   conservé comme artefact et non déployé.
7. `docs/site.md` décrit pas à pas la mise en place de Cloudflare (compte, projet Pages,
   application Access, jeton, secrets).
8. `make check` passe.

### Hors périmètre

- La refonte du contenu du mail (extraits de page thème, verdicts mis en avant) : plus tard,
  après quelques semaines d'usage.
- Les défauts de qualité du triage (regroupement des releases, quota par repo) : issue #6.
- Une page « santé du pipeline », un flux RSS, des pages par source, un graphe des fiches.
- Un domaine personnel.

## 2. Flux

```
weekly.yml : triage → analyze → site build → site deploy → digest → commit
                                 (auto-biblio)  (wrangler)
```

- `site build` et `site deploy` sont en `continue-on-error`.
- `site deploy` ne tourne pas en dry run ; le dossier `site/` est alors téléversé comme
  artefact du run, comme le digest.
- Le site est reconstruit en entier à chaque run : il n'a pas d'état propre.

## 3. Contenu du site

### Navigation

```
Accueil
Thèmes     → une page par thème (kb/themes)
Fiches     → Articles · Outils · Billets · Par thème
Journal    → une page par semaine (kb/changelog)
Digests    → une page par semaine (archive)
```

La recherche plein texte de zensical est activée sur tout le site. La langue du thème est le
français.

### Pages générées

- **Accueil** (`index.md`) : les thèmes du profil qui ont une page, avec leur date de mise à
  jour ; les thèmes sans page encore ; un bloc « Cette semaine » qui renvoie au dernier
  digest et au dernier journal.
- **Index des fiches** (`notes/papers.md`, `notes/tools.md`, `notes/posts.md`) : un tableau
  trié de la plus récente à la plus ancienne (date de première apparition), avec le titre
  (lien vers la fiche), les thèmes, la profondeur et la date.
- **Fiches par thème** (`notes/by-theme.md`) : une section par thème du profil, qui liste ses
  fiches.
- **Index du journal** (`changelog/index.md`) et **index des digests** (`digests/index.md`) :
  les semaines, de la plus récente à la plus ancienne.
- **Archive des digests** (`digests/<semaine>.md`) : une page par `TriageRun`, rendue en
  Markdown à partir du même modèle de vue que le mail (`build_view`), avec les liens vers les
  fiches et les évolutions de la base de la semaine. Le pied de page « santé du pipeline »
  n'y figure pas : il décrit l'état au moment de l'envoi et ne peut pas être recalculé pour
  une semaine passée.

### Pages reprises de `kb/`

- **Fiches** (`kb/notes/**`) : le contenu du fichier est repris, et une ligne de
  métadonnées est insérée sous le titre : lien source, type, thèmes, profondeur, date de
  première apparition et date d'analyse. La section `## Mes notes` est publiée telle quelle :
  le site est privé.
- **Pages thème** (`kb/themes/*`) : reprises avec, sous le titre, la date de mise à jour.
- **Journal** (`kb/changelog/*`) : repris tel quel.
- Un fichier illisible (`KBFormatError`) est repris sans en-tête, et un avertissement est
  journalisé.

### Adresses

Le site utilise les adresses en répertoire de zensical : une fiche `kb/notes/papers/x.md`
est servie à `notes/papers/x/`, un digest à `digests/2026-W42/`. Elles restent stables tant
que l'identifiant de l'item ne change pas, ce qui garde valides les liens des anciens mails.

## 4. Configuration

`config/site.yaml`, optionnel :

```yaml
site_url: https://veille.pages.dev/   # adresse publique du site, avec la barre finale
title: Veille IA                      # titre affiché, "Veille IA" par défaut
```

Le modèle `SiteConfig` est figé et validé (URL en `https`). `RepoConfig.site` vaut `None`
quand le fichier est absent. `site build` fonctionne sans fichier : le site est alors
construit avec les valeurs par défaut, et seuls les liens du digest restent sur GitHub.

## 5. Modules

| Module | Rôle | Entrées-sorties |
|---|---|---|
| `repo_config/site.py` | `SiteConfig` | aucune |
| `domain/site.py` | `SiteInputs` (fiches, pages thème, changelogs, vues des digests, profil) → `SitePlan` (pages `PurePosixPath` → Markdown, navigation) ; `note_page`, `theme_page`, index, accueil | aucune |
| `publish/templates/digest.md.j2` | rendu Markdown d'une `DigestView`, par le moteur de templates existant | aucune |
| `website/builder.py` | `SiteBuilder.build(plan, out)` : écrit les pages et un `zensical.toml` généré dans un dossier temporaire, lance `zensical build`, copie le résultat dans `out` | fichiers, sous-processus |
| `stages/site.py` | `SiteStage` : lit `kb/` et `state/` via les stores, construit `SiteInputs`, appelle le domaine puis le builder | via les stores |
| `publish/view.py` | `kb_url(base, path)` : vers le site quand `site_url` est défini, sinon vers GitHub ; `DigestView.online_url` | aucune |
| `cli.py` | `auto-biblio site build [--out site]` | point d'entrée mince |
| `scaffold_templates/weekly.yml` | étapes `Site build`, `Site deploy` (`cloudflare/wrangler-action`), artefact en dry run | — |

`zensical` passe des dépendances de développement aux dépendances d'exécution. Le paquet
s'appelle `website` et non `site`, pour ne pas masquer le module `site` de la bibliothèque
standard.

### Appel de zensical

Le builder appelle `zensical build -f <tmp>/zensical.toml` en sous-processus (l'API Python de
zensical n'est pas publique). Un code de sortie non nul lève `SiteBuildError` avec les
dernières lignes de la sortie d'erreur. En production, le build n'est pas strict : un lien
cassé dans un texte du LLM ne doit pas faire tomber le site. Les tests appellent le builder
en mode strict.

## 6. Déploiement et sécurité

Étape du workflow hebdomadaire :

```yaml
- name: Site deploy
  if: ${{ !inputs.dry_run }}
  continue-on-error: true
  uses: cloudflare/wrangler-action@v3
  with:
    apiToken: ${{ secrets.CLOUDFLARE_API_TOKEN }}
    accountId: ${{ secrets.CLOUDFLARE_ACCOUNT_ID }}
    command: pages deploy site --project-name=${{ vars.CLOUDFLARE_PAGES_PROJECT }} --branch=main
```

- Le jeton Cloudflare n'a que la permission « Cloudflare Pages : Edit ».
- L'application Cloudflare Access couvre `<projet>.pages.dev` **et** `*.<projet>.pages.dev`,
  pour protéger aussi les déploiements de prévisualisation.
- La règle Access autorise une seule adresse mail, avec un code à usage unique.
- Sans les secrets, l'étape échoue sans bloquer le reste ; GitHub signale l'échec.

`docs/site.md` décrit la mise en place : création du compte, activation de Zero Trust (nom
d'équipe), création du projet Pages par un premier déploiement, application Access et règle,
jeton d'API, secrets et variable du repo, `config/site.yaml`.

## 7. Erreurs

| Situation | Comportement |
|---|---|
| Fiche ou page thème illisible | reprise sans en-tête, avertissement journalisé |
| `zensical build` échoue | `SiteBuildError`, l'étape échoue, le digest part (ses nouveaux liens donnent une 404 jusqu'au prochain déploiement réussi) |
| Déploiement échoue | l'étape échoue, notification GitHub, le digest part |
| `config/site.yaml` invalide | `ConfigError` à la lecture de la configuration, comme les autres fichiers |

## 8. Tests

- `tests/domain/test_site.py` : à partir de fiches, pages thème, changelogs et vues de test,
  vérifie les pages produites, la navigation, l'en-tête des fiches, l'ordre des index,
  l'accueil avec et sans page thème, et le traitement d'un fichier illisible.
- `tests/website/test_builder.py` : vrai `zensical build --strict` sur une petite base de test ;
  vérifie que les pages HTML attendues existent, que les liens page thème → fiche pointent
  vers une page existante et que l'index de recherche est produit. Un build qui échoue lève
  `SiteBuildError`.
- `tests/stages/test_stage_site.py` : la stage lit un repo de données de test et produit le
  plan attendu.
- `tests/test_cli.py` : `site build` sur un repo de données de test.
- `tests/publish/test_view.py` : `kb_url` avec et sans `site_url`, lien « Voir en ligne ».
- `tests/test_scaffold.py` : le `weekly.yml` généré contient `Site build` et `Site deploy` en
  `continue-on-error`, dans le bon ordre, et le déploiement est sauté en dry run.

## 9. Documentation et version

- `docs/site.md` : contenu du site et guide Cloudflare.
- `docs/upgrade-0.6.md` : workflow hebdomadaire, secrets et variable, `config/site.yaml`.
- Version 0.6.0.
