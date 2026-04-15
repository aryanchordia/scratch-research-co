---
name: Scratch Research Co. project context
description: Weekly automated golf blog publication — architecture, stack, and setup status
type: project
---

Scratch Research Co. is an automated weekly golf blog publication at /Users/aryanchordia/Desktop/projects/scratch-research-co.

**Stack:**
- Astro v6 static site → GitHub Pages (free hosting)
- GitHub Actions cron (Sundays 9PM ET) for automation
- Python pipeline: fetch_data.py → generate_article.py → create_pr.py
- Data: ESPN Golf API (free, unofficial) + Cloudflare Browser Rendering (optional)
- AI: Claude API (Anthropic, claude-opus-4-6) with prompt caching
- Review: GitHub PR draft → user merges → auto-deploys

**Why:** User was inspired by attending The Masters 2026 and writing personal observations that others found insightful. Wants a weekly publication in a lifestyle/editorial style (House of Blanks, Malbon blogs).

**Coverage:** All pro golf globally — PGA Tour, DP World Tour, LIV Golf, majors

**Review flow:** Light review before publish — pipeline drafts, user merges PR to publish

**Setup still needed:**
- User needs to push to GitHub and configure GitHub Pages
- Secrets needed: ANTHROPIC_API_KEY (required), CLOUDFLARE_API_TOKEN + CLOUDFLARE_ACCOUNT_ID (optional)
- astro.config.mjs needs site/base updated to match GitHub username

**Key files:**
- pipeline/fetch_data.py — ESPN + Wikipedia + Cloudflare data fetching
- pipeline/generate_article.py — Claude API generation with SYSTEM_PROMPT for voice/style
- pipeline/create_pr.py — GitHub PR creation
- src/content.config.ts — Astro content schema (articles collection)
- picks/picks-history.json — Running picks record tracked in git
- .github/workflows/weekly-generation.yml — Sunday cron trigger
- .github/workflows/deploy.yml — GitHub Pages deploy on merge to main

**DataGolf:** Not integrated yet (requires $20/mo subscription). Architecture is ready to add DATAGOLF_API_KEY. ESPN free data is the current source.
