# Scratch Research Co.

Weekly golf intelligence — tournament recaps, course history, and picks. Every Sunday.

---

## What This Is

An automated weekly golf publication that runs every Sunday evening. The pipeline fetches tournament results, scrapes course history and context, generates a full article via Claude (Anthropic's AI), then opens a GitHub PR for you to review before it publishes to GitHub Pages.

**Stack:**
- **Blog:** [Astro](https://astro.build) static site → GitHub Pages (free)
- **Automation:** GitHub Actions (Sunday 9PM ET cron)
- **Data:** ESPN Golf API + Cloudflare Browser Rendering
- **AI:** Claude API (Anthropic) with prompt caching
- **Review:** GitHub PR draft → merge to publish

---

## Setup (One-Time)

### 1. Create the GitHub repo

```bash
git remote add origin https://github.com/YOUR_USERNAME/scratch-research-co.git
git branch -M main
git push -u origin main
```

### 2. Enable GitHub Pages

1. Go to **Settings → Pages** in your repo
2. Set source to **GitHub Actions**

### 3. Add repository secrets

Go to **Settings → Secrets and variables → Actions** and add:

| Secret | Where to get it |
|---|---|
| `ANTHROPIC_API_KEY` | [console.anthropic.com](https://console.anthropic.com) |
| `CLOUDFLARE_API_TOKEN` | Cloudflare dashboard → API Tokens → create token with "Browser Rendering Edit" permission |
| `CLOUDFLARE_ACCOUNT_ID` | Cloudflare dashboard → right sidebar |

> **Note:** Cloudflare credentials are optional for the first run. Without them, Wikipedia and ESPN data still work — you just won't get JS-rendered page scraping.

### 4. Update the site URL

In `astro.config.mjs`, update `site` and `base` to match your GitHub username:

```js
site: 'https://YOUR_USERNAME.github.io',
base: '/scratch-research-co',
```

### 5. Done

The pipeline runs automatically every Sunday at 9PM ET. You'll get a GitHub PR notification — review it, merge it, and it publishes.

To run it manually any time: **Actions → Weekly Article Generation → Run workflow**

---

## Project Structure

```
scratch-research-co/
├── .github/workflows/
│   ├── weekly-generation.yml   # Sunday cron → fetches data, generates article, opens PR
│   └── deploy.yml              # On merge to main → builds & deploys to GitHub Pages
│
├── pipeline/
│   ├── fetch_data.py           # ESPN + Cloudflare + Wikipedia data fetching
│   ├── generate_article.py     # Claude API article generation
│   └── create_pr.py            # GitHub PR creation
│
├── src/
│   ├── content/articles/       # All published articles (MDX)
│   │   └── 2026/
│   ├── content.config.ts       # Astro content schema
│   ├── components/             # Header, Footer, ArticleCard
│   ├── layouts/                # BaseLayout, ArticleLayout
│   └── pages/                  # index, picks, about, articles/[slug]
│
├── picks/
│   └── picks-history.json      # Running picks record (tracked in git)
│
└── data/                       # Ephemeral pipeline data (gitignored)
```

---

## The Article Format

Each weekly article covers:
1. **Recap** — narrative of the week's tournaments
2. **By The Numbers** — key stats in a visual grid
3. **What Actually Happened** — 3-5 deeper observations
4. **Course & History** — venue facts and tournament history
5. **Last Week's Picks** — cross-reference against actual results
6. **Looking Ahead** — next tournament preview
7. **Our Picks** — 5 players with reasoning for the following week

---

## Upgrading Data Quality

For deeper stats and predictive picks, consider adding a **DataGolf** subscription ($20/mo):

1. Get an API key at [datagolf.com/api-access](https://datagolf.com/api-access)
2. Add `DATAGOLF_API_KEY` to repo secrets
3. The pipeline is already structured to accept it — DataGolf endpoints are documented in `pipeline/fetch_data.py`

---

## Local Development

```bash
npm install
npm run dev          # Dev server at localhost:4321/scratch-research-co
npm run build        # Production build to ./dist
```

Running the pipeline locally:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
python pipeline/fetch_data.py
python pipeline/generate_article.py
# (create_pr.py requires GH_TOKEN and runs in CI)
```

---

*AI-assisted. Human-curated. Published every Sunday.*
