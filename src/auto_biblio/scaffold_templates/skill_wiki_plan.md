---
name: wiki-plan
description: Propose le plan d'un domaine du wiki (wiki/<domaine>/index.md) - notions, prérequis et ordre de lecture - et ouvre une PR. À utiliser pour démarrer un nouveau domaine ou en revoir le plan.
---

# Planifier un domaine du wiki

Domaine demandé : `$ARGUMENTS` (un identifiant court en minuscules, par exemple `llm`).
Sans argument, demande le domaine avant de commencer.

## 1. Lire l'existant

1. Lis `wiki/GUIDE.md` en entier : il fait autorité sur la forme.
2. Si `wiki/<domaine>/index.md` existe, lis-le : la PR le fait évoluer, sans retirer une
   notion qui a déjà une page.
3. Lis `state/wiki/candidates.json` s'il existe : les concepts que la veille rencontre sans
   page, avec leur nombre de fiches. Ceux du domaine sont des notions à prévoir en priorité.
4. Lis `config/profile.yaml` pour connaître les thèmes de veille.

## 2. Construire le plan

1. Cherche sur le web deux ou trois cours de référence du domaine (cours universitaires,
   manuels reconnus, documentation officielle) et note leurs plans.
2. Liste les notions : une notion = une page qu'on lit en 10 à 20 minutes. Découpe ou
   regroupe en conséquence.
3. Pour chaque notion, fixe son identifiant `<domaine>/<notion>` (minuscules, chiffres,
   tirets), ses prérequis, et vérifie qu'il n'y a pas de cycle.
4. Ordonne les notions pour qu'une notion vienne toujours après ses prérequis.

## 3. Écrire `wiki/<domaine>/index.md`

```markdown
---
title: <Titre du domaine>
order: [<domaine>/<notion-1>, <domaine>/<notion-2>, …]
---

<Présentation : périmètre du domaine, public, comment le lire.>

## Plan

- `<domaine>/<notion-1>` — <une ligne : ce que la notion couvre> (prérequis : …)
- …

## Sources du plan

- <cours ou manuel, lien>
```

## 4. Vérifier

```bash
auto-biblio wiki check
auto-biblio site build --out /tmp/site
```

Corrige jusqu'à ce que `wiki check` ne signale plus rien (les notions prévues sans page sont
normales).

## 5. Ouvrir la PR

```bash
git switch -c wiki/plan-<domaine>
git add wiki/<domaine>/index.md
git commit -m "wiki(<domaine>): plan"
git push -u origin wiki/plan-<domaine>
gh pr create --title "wiki(<domaine>): plan" --body-file <fichier>
```

La description liste les sources consultées, les candidats de `candidates.json` retenus ou
écartés, et les choix de découpage sur lesquels l'avis du propriétaire compte le plus.
