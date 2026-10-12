# Upgrade a data repository to 0.4

Version 0.4 adds the weekly analysis and the knowledge base. Starting from a 0.2 or 0.3 data
repository:

1. **Pin the new version.** Replace the tag in both workflows by `@v0.4.1`.
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

## From 0.4.0 to 0.4.1

0.4.1 spaces and retries the LLM calls, so that the free tier of Gemini Flash (5 requests per
minute) no longer makes half of the notes fail.

1. Pin `@v0.4.1` in both workflows, and raise `timeout-minutes` of the weekly job to 60:
   pacing makes the analysis slower.
2. In `config/llm.yaml`, give each model a `min_interval_s` (seconds between two calls):

    ```yaml
    models:
      flash-lite: {min_interval_s: 5, ...}
      flash: {min_interval_s: 13, ...}
      gemma: {min_interval_s: 3, ...}
    ```

    Without it, calls are not spaced but rate limits are still retried (`max_retries`,
    default 2).
3. Re-run the weekly workflow of a week whose notes failed. The note prompts now insist on
   French, so every note of the week is written again (your `## Mes notes` are kept).
