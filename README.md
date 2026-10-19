# Neutron Bytes — Nuclear Sector Intelligence

GitHub Pages static website: a cumulative **News Archive** and detailed **Weekly Updates** with newest week first.

## One-time setup

1. Create a **public** GitHub repository named `neutron-bytes-digest` (or another name) on the account hosting the site.
2. Commit all files in this folder to the new repository, preserving `.github/workflows/publish.yml` and `.nojekyll`.
3. In GitHub, go to **Settings → Secrets and variables → Actions → New repository secret** and create `OPENAI_API_KEY` with your **OpenAI API key**, not your ChatGPT login. API usage is billed separately.
4. Go to **Settings → Pages → Build and deployment → Source: GitHub Actions**.
5. **Actions → Update and publish Neutron Bytes → Run workflow** to test the first build. The October 12–18 week is seeded, so this first test rebuilds it without duplication.

The website URL will be `https://YOUR_USERNAME.github.io/REPOSITORY_NAME/`. It may take several minutes for the first deployment.

## Weekly workflow

- GitHub Actions is scheduled at **7:00 a.m. America/Chicago every Monday**; schedules may start late when GitHub is busy.
- It discovers posts from the **preceding completed Monday–Sunday**, reviews the Neutron Bytes article and accessible original links within it, extracts distinct stories including multiple roundup subsections, and checks link provenance.
- It writes one Markdown briefing for the week, builds a browsable Weekly Updates page, and appends new stories into the **existing month** of the cumulative HTML news archive. The script never deletes historical cards.
- A completed week that already exists will not be duplicated on rerun. If one post fails processing, the workflow fails *without posting a partial week's briefing*.
- Publication requires the `OPENAI_API_KEY` secret and an internet-accessible Neutron Bytes website. Automated extraction is best-effort and should be periodically reviewed; the system does not independently guarantee exhaustive archive coverage.
- **Source restriction:** Neutron Bytes posts and original documents expressly hyperlinked within those posts. Links are validated against hyperlinks extracted from the corresponding Neutron Bytes article. Original source links are omitted when not verified.

## Architecture

- `index.html`: existing cumulative reverse-chronological 2020–2026 archive; source of truth for historical cards.
- `weekly/index.html`: latest weekly briefing, with week navigation sidebar.
- `weekly/YYYY-MM-DD.md`: source Markdown edition of each weekly briefing.
- `weekly/YYYY-MM-DD.html`: standalone rendered weekly briefing (direct permalink).
- `data/weeks/YYYY-MM-DD.json`: normalized new story records and discovery log.
- `scripts/update_weekly.py`: external-source-bounded weekly ingestion + OpenAI extraction.
- `scripts/site_builder.py`: HTML renderer and de-duplicated archive append.
- `.github/workflows/publish.yml`: combined scheduled update and Pages deployment.

## Reliability and limitations

GitHub Pages itself is free for a public repository. AI API usage is separately billed by OpenAI; no API keys are stored in files or in Git. This repository does not contain a hosted backend, so the schedule must run in GitHub Actions. Some external original sources may block automated access, in which case the linked article itself remains the basis for the story. The 2020–2026 historical file is a curated archive and not a certified comprehensive inventory.