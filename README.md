# Anima Character Prompt Generator — Vercel Fixed Edition

## Correct GitHub root structure

```text
app.py
services.py
requirements.txt
vercel.json
.python-version
templates/index.html
public/style.css
public/app.js
.gitignore
.vercelignore
README.md
```

Important: do not create an `api/` folder or upload an extra enclosing project folder. Vercel detects the Flask WSGI app exported as `app` from root `app.py`. Frontend files belong in `public/` because Vercel serves public assets through its CDN. Jinja template is bundled with the function via `includeFiles`.

## Deploy from GitHub
1. Upload the CONTENTS of this folder to the GitHub repository root.
2. In Vercel choose Add New → Project and import this repository.
3. Set Root Directory to `./` (repository root).
4. Do not set a custom Build Command or Output Directory. Let Vercel detect Flask.
5. Deploy.
6. Open `https://YOUR-DEPLOYMENT.vercel.app/api/health`. It should return JSON with `ok: true`.

## Search behavior
- AniList and Shikimori are queried for the exact name.
- Known alternate spellings are retried if exact search is empty.
- Hajun has a verified Mudae fallback independent of AniList/Shikimori.
- If public catalogs return nothing or are unavailable, a Manual result is shown so the user can still edit a profile and generate prompts.

External sources can rate-limit or block serverless requests. Danbooru image/tag collection is optional; the app remains usable without it.
