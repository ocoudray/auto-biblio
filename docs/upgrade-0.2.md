# Upgrade a data repository to 0.2

Version 0.2 adds the weekly triage and the raw digest. An existing data repository needs:

1. **New configuration files.** Run `auto-biblio init /tmp/fresh` with the new version and
   copy `config/llm.yaml`, `config/triage.yaml` and `.github/workflows/weekly.yml` into the
   data repository. `triage.yaml` is optional (defaults apply when it is absent).
2. **The daily workflow.** Replace `.github/workflows/daily.yml` by the new one (it adds
   `signals refresh`, `feedback ingest` and `health`, and the `issues: write` permission),
   then report your own changes into it. Pin the same tag in both workflows (`@v0.2.0`).
3. **The `.gitignore`.** Add `.cache/` and `digest.html`.
4. **Labels.** Create the `feedback` and `feedback-invalid` labels in the repository
   (*Issues → Labels*).
5. **Secrets** (*Settings → Secrets and variables → Actions*):

    | Kind | Name | Value |
    |---|---|---|
    | Secret | `GEMINI_API_KEY` | Google AI Studio key (free tier) |
    | Secret | `ANTHROPIC_API_KEY` | Anthropic API key (fallback model) |
    | Secret | `SMTP_PASSWORD` | Gmail application password |
    | Variable | `AUTO_BIBLIO_SMTP_USER` | Gmail address sending the digest |
    | Variable | `AUTO_BIBLIO_DIGEST_TO` | Address receiving the digest |

    A missing model key only removes that model from the chain.

6. **First run.** Trigger *Weekly triage and digest* by hand with `dry_run` checked, check
   the `digest` artifact and `state/triage/`, then let the Sunday schedule take over.
