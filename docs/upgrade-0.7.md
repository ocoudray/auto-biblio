# Upgrade a data repository to 0.7

Version 0.7 adds the [knowledge wiki](wiki.md): the skills that draft its pages, the weekly
`wiki link` step and the wiki section of the site.

Generate the new files in a scratch directory, then copy them:

```bash
auto-biblio init /tmp/fresh
```

1. **Pin the new version.** Replace the tag in both workflows by `@v0.7.0`.
2. **Skills and guide.** Copy `/tmp/fresh/.claude/skills/` (`wiki-plan`, `wiki-rediger`,
   `wiki-reprendre`) and `/tmp/fresh/wiki/GUIDE.md` into the data repository.
3. **Workflows.** Copy `/tmp/fresh/.github/workflows/wiki-check.yml`, and replace
   `.github/workflows/weekly.yml` by the new one: it adds the `Wiki link` step between
   `Analyze` and `Site build`.
4. **LLM chain.** Add the `wiki_link` chain to `config/llm.yaml`:

   ```yaml
   chains:
     wiki_link: [flash-lite, flash-lite-3.1, gemma]
   ```

5. **First domain.** Run `/wiki-plan llm` with Claude Code in the data repository, review and
   merge its pull request, then draft the pages one by one with `/wiki-rediger`.

As soon as `wiki/` exists (the guide is enough), `wiki link` runs every week: with no notion
yet, it only collects the concepts the notes use into `state/wiki/candidates.json`, which
`/wiki-plan` reads. The site shows its wiki section once a domain `index.md` is merged.
