---
name: wiki-rediger
description: Rédige une page de notion du wiki (wiki/<domaine>/<notion>.md) au gabarit du guide, avec ses illustrations, et ouvre une PR. À utiliser pour écrire la prochaine notion de l'ordre de lecture ou une notion donnée.
---

# Rédiger une notion du wiki

Notion demandée : `$ARGUMENTS` (un identifiant `<domaine>/<notion>`, par exemple
`llm/attention`).

## 1. Choisir la notion

- Avec un argument : cette notion. Elle doit figurer dans l'`order` de
  `wiki/<domaine>/index.md` ; sinon, arrête-toi et propose `/wiki-plan`.
- Sans argument : parcours l'`order` de chaque domaine et prends la première notion qui n'a
  pas de page et dont tous les prérequis ont une page.

## 2. Lire

1. `wiki/GUIDE.md` en entier, y compris « Règles issues des relectures » : chaque règle
   s'applique.
2. Les pages des prérequis et des notions liées : réutilise leurs notations, renvoie vers
   elles au lieu de réexpliquer.
3. Les fiches de veille liées à la notion : dans `state/wiki/links.json`, les fiches dont
   `notions` contient l'identifiant ; leurs fichiers sont dans `kb/notes/`. Elles nourrissent
   « Variantes et évolutions ».

## 3. Chercher les sources

Cherche sur le web le papier fondateur, deux cours reconnus et la documentation officielle
s'il y en a. Garde la liste des pages consultées pour la description de la PR. Vérifie chaque
équation et chaque ordre de grandeur sur au moins une source.

## 4. Rédiger

- Écris `wiki/<domaine>/<notion>.md` au gabarit du guide : front-matter complet
  (`updated_at` = date du jour, `aliases` = les noms sous lesquels la littérature et les
  fiches citent la notion), résumé, sections, références.
- Si la page existe déjà, ne touche pas à `## Mes notes` sans accord explicite.
- Illustrations, seulement quand elles aident :
  - flux et étapes : bloc ` ```mermaid ` ;
  - schéma d'architecture : SVG dessiné dans `wiki/<domaine>/img/<nom>.svg` ;
  - graphique calculé : script `wiki/<domaine>/img/<nom>.py` (matplotlib) qui écrit
    `img/<nom>.svg`. Exécute-le (`uv run --with matplotlib python wiki/<domaine>/img/<nom>.py`)
    et versionne le script et le SVG.
- Chaque image : texte alternatif, puis sur la ligne suivante une légende en italique avec sa
  provenance (« Figure originale. » ou « Source : <auteur, lien>, <licence>. »). Une figure
  tierce n'est reprise que sous licence ouverte ; sinon, schéma original légendé
  « Figure originale, d'après <source>. » (`wiki check` exige « Figure originale » ou « Source : »).
- Notebook à télécharger, s'il aide : `wiki/<domaine>/code/<nom>.ipynb`, lié depuis la page par
  `[notebook](code/<nom>.ipynb)`. Le site ne publie de `code/` que les `.ipynb`.

## 5. Vérifier

```bash
auto-biblio wiki check
auto-biblio site build --out /tmp/site
```

Corrige jusqu'à ce que `wiki check` ne signale plus rien pour cette page et que le site se
construise. Relis la page rendue (`/tmp/site/wiki/<domaine>/<notion>/index.html`) : équations,
diagrammes et figures s'affichent, le lien du notebook éventuel le télécharge.

## 6. Ouvrir la PR

Une PR par page :

```bash
git switch -c wiki/<domaine>-<notion>
git add wiki/<domaine>/
git commit -m "wiki(<domaine>): <notion>"
git push -u origin wiki/<domaine>-<notion>
gh pr create --title "wiki(<domaine>): <titre>" --body-file <fichier>
```

La description contient :

- les sources consultées, avec liens ;
- les points à vérifier en priorité (équations, affirmations non triviales, choix de
  présentation) ;
- les figures et leur provenance.

Le propriétaire relit et commente la PR ; `/wiki-reprendre <PR>` traite ses remarques.
