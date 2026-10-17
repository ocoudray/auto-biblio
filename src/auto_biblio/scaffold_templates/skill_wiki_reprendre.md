---
name: wiki-reprendre
description: Traite les remarques de revue d'une PR du wiki - applique chaque remarque, répond sur chaque fil, et propose dans un commit séparé les règles à ajouter à wiki/GUIDE.md. À utiliser après la relecture d'une PR ouverte par /wiki-plan ou /wiki-rediger.
---

# Reprendre une PR du wiki après relecture

PR demandée : `$ARGUMENTS` (son numéro). Sans argument, demande-le.

## 1. Lire les remarques

```bash
gh pr checkout <PR>
gh pr view <PR> --comments
gh api repos/{owner}/{repo}/pulls/<PR>/comments --paginate
gh api repos/{owner}/{repo}/pulls/<PR>/reviews --paginate
```

Liste chaque remarque : son fil (`id` du commentaire), le fichier et la ligne, ce qui est
demandé. Relis aussi `wiki/GUIDE.md`.

## 2. Appliquer

- Applique chaque remarque. Si une remarque est ambiguë ou te semble fausse, ne devine pas :
  réponds sur son fil avec la question ou l'objection, sources à l'appui.
- Ne touche pas à `## Mes notes` sans accord explicite.
- Si la page change, mets `updated_at` à la date du jour.
- Vérifie :

  ```bash
  auto-biblio wiki check
  auto-biblio site build --out /tmp/site
  ```

- Commite les corrections (`wiki(<domaine>): suite de la relecture`) et pousse.

## 3. Répondre sur chaque fil

Pour chaque commentaire de revue, une réponse sur son fil :

```bash
gh api repos/{owner}/{repo}/pulls/<PR>/comments/<id>/replies -f body="Corrigé dans <commit>."
```

Ou, si tu ne l'as pas appliquée, pourquoi.

## 4. Capitaliser dans le guide

1. Parmi les remarques, garde celles qui valent pour d'autres pages (une préférence de
   notation, de niveau, de structure, d'illustration…), pas les corrections ponctuelles.
2. Ajoute-les à la section « Règles issues des relectures » de `wiki/GUIDE.md`, une puce par
   règle, chacune avec l'exemple qui l'a motivée et le numéro de la PR :

   ```markdown
   - Toujours donner la complexité en fonction de `n` et `d_model`. Exemple : la page
     `llm/attention` donnait « quadratique » sans préciser en quoi (PR #12).
   ```

3. Mets-les dans un **commit séparé** (`wiki: règles issues de la relecture de #<PR>`), pour
   que le propriétaire puisse le garder ou le retirer avant de fusionner. Pousse.
4. Termine par un commentaire sur la PR qui résume : remarques appliquées, remarques en
   discussion, règles proposées pour le guide.
