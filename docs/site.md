# Knowledge-base site

Every week, `auto-biblio site build` turns the data repository into a static site, and the
weekly workflow publishes it on Cloudflare Pages behind Cloudflare Access: only you can open
it. The digest then links to the site instead of the files on GitHub.

## Content

| Section | Pages |
|---|---|
| Accueil | theme pages with their update date, themes without a page yet, links to this week's digest and changelog |
| Thèmes | one page per theme (`kb/themes/`) |
| Fiches | one page per note (`kb/notes/`), with its source link and metadata under the title; indexes by kind (articles, tools, posts) and by theme |
| Journal | one page per week (`kb/changelog/`) |
| Digests | the web version of each weekly digest, linked to the notes |

The search box covers the whole site. `## Mes notes` sections are published as they are: the
site is private.

Build it locally and browse it:

```bash
auto-biblio site build --out site     # from the data repository
python -m http.server -d site 8000    # then open http://localhost:8000
```

A note or theme page that cannot be read is published as it is, with a `warning:` line.
Raw HTML in titles, notes and pages is shown as text, never run. `--out` must be a new or
empty directory, or a site built earlier by `site build`: anything else is refused, so that a
wrong path never wipes your data. `site build` exits with code 5 when it fails.

## Publishing on Cloudflare (once)

1. **Account.** Create a free account on [dash.cloudflare.com](https://dash.cloudflare.com).
2. **Zero Trust.** In *Zero Trust*, pick a team name and the free plan (up to 50 users; a
   payment method may be asked but nothing is charged).
3. **Pages project.** In *Workers & Pages → Create → Pages → Upload assets*, create a project,
   e.g. `veille-ia`, and upload any small folder: the site is then served at
   `https://veille-ia.pages.dev`. The workflow replaces it every week.
4. **Access.** In *Zero Trust → Access → Applications → Add an application → Self-hosted*:
   - add two public hostnames: `veille-ia.pages.dev` and `*.veille-ia.pages.dev` (preview
     deployments have their own sub-domains);
   - add a policy *Allow* with the rule *Emails* = your address;
   - keep *One-time PIN* as login method: you receive a code by mail.
   Open the site in a private window: Cloudflare must ask for your address.
5. **API token.** In *My Profile → API Tokens → Create Token → Custom token*, grant only
   *Account → Cloudflare Pages → Edit*. Note your *Account ID* (right column of the
   *Workers & Pages* overview).
6. **Data repository settings** (*Settings → Secrets and variables → Actions*):

    | Kind | Name | Value |
    |---|---|---|
    | Secret | `CLOUDFLARE_API_TOKEN` | the token |
    | Secret | `CLOUDFLARE_ACCOUNT_ID` | the account id |
    | Variable | `CLOUDFLARE_PAGES_PROJECT` | `veille-ia` |

7. **`config/site.yaml`** in the data repository:

    ```yaml
    site_url: https://veille-ia.pages.dev/
    title: Veille IA
    ```

    Without this file the site is still built, but the digest keeps linking to GitHub.

## In the weekly workflow

```
triage → analyze → site build → site deploy → digest → commit
```

`Site build` and `Site deploy` never block the digest. If they fail, the digest is sent
anyway and the state is committed; the last step, *Report a site failure*, then marks the run
as failed so that GitHub notifies you. Links to notes created that week answer 404 until the
next successful deployment.
A dry run builds the site without deploying it and keeps it as the `site` artifact of the run.
