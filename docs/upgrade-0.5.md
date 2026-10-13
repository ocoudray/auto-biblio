# Upgrade a data repository to 0.5

Version 0.5 makes the most of Google's free tier, where every model has its own quota (Flash:
20 requests per day each; Flash-Lite: 500; Gemma: 14,400 but 16,000 tokens per minute).

1. **Pin the new version.** Replace the tag in both workflows by `@v0.5.0`.
2. **`config/llm.yaml`.** Replace it by the one `auto-biblio init /tmp/fresh` writes, or at
   least:
    - give Gemma `tpm: 16000` and `max_output_tokens: 8192`, so that it is skipped for the
      prompts it cannot take (deep analyses, theme page);
    - move `triage` and `short_note` to Flash-Lite, and chain several Flash models for
      `deep_analysis` and `synthesis`.

Nothing else changes: a spent daily quota or an unknown model id is now detected once and the
model skipped for the rest of the run.
