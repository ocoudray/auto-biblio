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
    | Secret | `GEMINI_API_KEY` | Google AI Studio key (free tier): covers both Flash-Lite and Gemma |
    | Secret | `SMTP_PASSWORD` | Gmail **application password** (see below), not your account password |
    | Variable | `AUTO_BIBLIO_SMTP_USER` | Full Gmail address sending the digest, e.g. `you@gmail.com` |
    | Variable | `AUTO_BIBLIO_DIGEST_TO` | Address receiving the digest (can be the same) |
    | Secret (optional) | `ANTHROPIC_API_KEY` | Only if you add a Claude model to `llm.yaml` |

    A missing (or empty) model key only removes that model from the chain.

6. **Gmail application password.** Gmail refuses SMTP logins with the account password; it
   needs a 16-character application password:
    1. Turn on 2-Step Verification on the sending Google account
       (*Google Account → Security*): application passwords require it.
    2. Open <https://myaccount.google.com/apppasswords>, name it `auto-biblio`, create it.
    3. Copy the 16 letters shown (`abcd efgh ijkl mnop`) **without the spaces** into the
       `SMTP_PASSWORD` secret. Google shows it only once; revoke it from the same page if
       it leaks, and create a new one.

    The defaults `smtp.gmail.com` and port `465` (TLS) need no setting. On a Google
    Workspace account, the administrator may have disabled application passwords.

7. **First run.** Trigger *Weekly triage and digest* by hand with `dry_run` checked, check
   the `digest` artifact and `state/triage/`, then let the Sunday schedule take over.
