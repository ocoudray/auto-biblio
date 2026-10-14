# Upgrade a data repository to 0.6

Version 0.6 publishes the knowledge base as a private site and links the digest to it.

1. **Pin the new version.** Replace the tag in both workflows by `@v0.6.0`.
2. **The weekly workflow.** Replace `.github/workflows/weekly.yml` by the one `auto-biblio
   init /tmp/fresh` writes. It adds the `Site build`, `Site deploy` and `Keep the dry-run site`
   steps. Add `site/` to `.gitignore`.
3. **Cloudflare.** Follow [Knowledge-base site](site.md#publishing-on-cloudflare-once):
   account, Pages project, Access application, token, two secrets and one variable.
4. **`config/site.yaml`.** Add it with your `site_url` once the first deployment works: from
   then on, the digest links to the site and has a *Voir en ligne* link.

Until step 3 is done, `Site deploy` fails without blocking anything else.
