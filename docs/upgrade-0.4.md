# Upgrade a data repository to 0.4

Version 0.4 adds the weekly analysis and the knowledge base. Starting from a 0.2 or 0.3 data
repository:

1. **Pin the new version.** Replace the tag in both workflows by `@v0.4.0`.
2. **The weekly workflow.** Replace `.github/workflows/weekly.yml` by the one `auto-biblio
   init /tmp/fresh` writes. It adds the `analyze` step, which does not block the digest when
   it fails, and commits `kb/` along with `state/`.
3. **`config/llm.yaml`.** Add the `flash` model (`google:gemini-3.5-flash`, free tier, same
   key) and the chains of the three new roles, then raise the token cap:

    ```yaml
    models:
      flash:
        id: google:gemini-3.5-flash
        input_usd_per_mtok: 0
        output_usd_per_mtok: 0
        batch_size: 1
        max_output_tokens: 8192
    chains:
      short_note: [flash, gemma]
      deep_analysis: [flash, gemma]
      synthesis: [flash, gemma]
    weekly_budget:
      tokens: 600000
    ```

    Without these chains, the triage keeps working and only `analyze` fails, with a message
    naming the missing roles.
4. **Optional:** copy `config/analysis.yaml` to tune the analysis (defaults apply without
   it).
5. **First run.** Trigger *Weekly triage, analysis and digest* by hand with `dry_run`
   checked, then look at `kb/` and the `digest` artifact.
