# Instruction Prompt — Concourse Frontend Redesign (for a coding assistant)

> **Paste this entire file to your coding assistant as its task brief.** It is self-contained: repo access, environment setup, the redesign scope, hard constraints, and the definition of done. Where it says **[ASK THE OWNER]**, request that value from the human before proceeding — do not guess or invent it.

---

## 0. Your role and the one rule that matters most

You are doing an **isolated frontend redesign** of an existing web app called **Concourse**. The goal is a visually better, more coherent UI that the founders can review side-by-side against the current version and *then* decide whether to merge.

**THE RULE: never touch, commit to, or push to `main`.** `main` auto-deploys to production on Railway. All your work happens on the branch **`giovanni/frontend-redesign`** and nowhere else. If you ever find yourself on `main`, stop and switch back.

You are also **redesigning, not re-architecting.** Do not change the backend, the database, the API routes, the auth flow, or the build/deploy model. This is a build-step-free project (no npm, no bundler, no framework) and it must stay that way — see §4.

---

## 1. Repository access

- **Repo:** `https://github.com/LLj2/concourse.git` (private).
  - ⚠️ Note: the project README shows an older URL (`giovannifoglietta/concourse`). The **correct** remote is `LLj2/concourse`. Use that.
- **Authentication:** this is a private repo. You will need a GitHub credential (personal access token or SSH key) with read/write to `LLj2/concourse`. **[ASK THE OWNER]** to provide access or to run the push commands themselves if you cannot authenticate. **Never hardcode a token into a file, a commit, or the git remote URL.**
- **Branch to work on:** `giovanni/frontend-redesign` (already created locally; may not be pushed yet — see §2). The team's convention is `firstname/feature` branches; keep to it.
- **Base branch (read-only reference):** `main`.

## 2. First steps — get onto the branch safely

```bash
git clone https://github.com/LLj2/concourse.git
cd concourse
git fetch origin

# If the redesign branch is already on origin:
git switch giovanni/frontend-redesign
# If it is NOT on origin yet, the owner has it locally; either have them push it,
# or create it from main and they will reconcile:
#   git switch -c giovanni/frontend-redesign origin/main

git branch --show-current   # MUST print: giovanni/frontend-redesign
```

Confirm you are on the branch before writing any code. Push your branch to origin early so the founders can pull it:
```bash
git push -u origin giovanni/frontend-redesign
```

## 3. Local setup (how to run and see the app)

Stack: **Python 3 / FastAPI + uvicorn**, served straight from one process. There is **no frontend build step** — HTML/CSS/JS are served as static files and via `FileResponse` routes.

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # if .env.example is missing, ASK THE OWNER for the env keys
uvicorn backend.main:app --reload
```

Then browse:
- `http://localhost:8000/` — landing page
- `http://localhost:8000/health` — health + config sanity check (does not touch the DB)
- `http://localhost:8000/me` — the main dashboard (the app's hub)
- `http://localhost:8000/compass` — the adaptive practice engine (the flagship feature)

**Environment variables** (names only — **[ASK THE OWNER]** for values; never commit them). The app reads these from `.env`:
`SUPABASE_URL`, `SUPABASE_ANON_KEY`, `DATABASE_URL`, `SESSION_SECRET`, `ANTHROPIC_API_KEY`, `APP_ENV`, `PUBLIC_BASE_URL`, `POSTHOG_PUBLIC_KEY`, `POSTHOG_HOST`, `STRIPE_SECRET_KEY`, `STRIPE_PRICE_ID`, `STRIPE_WEBHOOK_SECRET`.

If you cannot get real Supabase/Anthropic credentials, you can still do most of the redesign against the static HTML and the `/health` page; note in your PR which pages you could not exercise live.

## 4. Hard constraints (do NOT violate — this project has explicit guardrails)

These come from the repo's `CLAUDE.md` and `docs/FRONTEND_PLAN.md`. Read both before starting.

1. **No new toolchain.** No npm, no bundler, no framework (React/Vue/Svelte/Next/Astro), no Tailwind build, no CSS-in-JS, no Web Components. Plain HTML, CSS custom properties, and vanilla ES-module JavaScript only. One allowed CDN `<script>`: **Chart.js** (for dashboard charts). If you believe a library is unavoidable, STOP and ask.
2. **Do not touch the backend.** No changes to Python route logic, API contracts, SQL, migrations, or `backend/auth/`. You may edit the HTML that routes serve and add static CSS/JS. If a redesign needs a route to return a template instead of a file, that is allowed (FastAPI + Jinja2), but keep the response and URL identical.
3. **Compass is sealed.** All Compass code lives under `backend/compass/` and is exposed at `/api/compass/*`. **Do not modify `backend/logic/`, `backend/ai/client.py`, or `backend/auth/`.** You MAY restyle `backend/compass/static/compass.html` and its JS, and have it `<link>` the shared CSS — but keep Compass's template and JS inside `backend/compass/` (do not couple it to the rest of the app's Python).
4. **Auth stays as-is.** Supabase magic-link + server-set signed cookies. Do not replace or re-plumb it.
5. **Deployment stays as-is.** One Railway service, `Procfile` runs `uvicorn backend.main:app`. Do not add a second service, a Node server, CORS config, or a separate frontend domain.
6. **Secrets discipline.** `.env`, `*SECRETS*.md`, `HANDOVER_*.md` are gitignored — keep it that way. Never commit a secret or a token-embedded git URL.
7. **No production data changes.** You are working locally; do not run migrations against any shared/prod database.

## 5. What to build — the redesign scope

The full rationale, page priority, and specs are in **`docs/FRONTEND_PLAN.md`** (read it — it is the source of truth for this work). The short version:

**The problem:** the app is 8 hand-rolled single-file HTML pages, each with its own inline `<style>` and vanilla JS — no shared design system, inconsistent nav/typography/spacing across pages. It works; it just looks incoherent. The credibility problem is **inconsistency, not technology.**

**The transformation (build-step-free):**
1. **Foundation first (do this before touching individual pages):**
   - Introduce **FastAPI + Jinja2 templates**: a `base.html` + shared layout/partials so nav, footer, `<head>`, typography, and script-loading are defined once.
   - Create a **design-token CSS layer**: `static/css/tokens.css` (colors, type scale, spacing scale, radii, shadows, transitions) + `static/css/components.css` (~12 primitives: button, input, form-field with label/hint/error, card, page-header, progress, status-badge, alert/toast, empty-state, modal, skeleton, ai-insight).
   - **Design language:** serious, calm, credible for **adult professionals** (EPSO exam candidates, 25–45, on laptop and mobile). Near-black text on off-white, one confident blue/teal accent, generous whitespace — Linear/Notion cues. **NOT** a gamified kids' aesthetic: no mascots, XP/gems/lives, confetti, or cartoon styling.
   - **Version-string the CSS** (e.g. `tokens.css?v=1`) since there is no build-time cache-busting.
2. **Migrate one reference page first** — **`/me`** (the dashboard; it is the canonical hub — every page links to it). Get it fully onto the shell + tokens, freeze the vocabulary, then migrate the rest.
3. **Then the rest, in this priority order** (effort estimates in the plan):
   1. **Compass session + results** (`/compass`) — the product; where users spend ~80% of their time. Focused session shell (no dashboard chrome), one question per screen, thin progress bar, subdued timer, immediate explanatory feedback, a strong results screen (score, per-dimension delta, one specific insight, one CTA).
   2. **Landing** (`/`) — first impression; one hero, clear EPSO promise, one CTA.
   3. **`/me` dashboard** — 4–5 panels max; Chart.js (mastery line + a **labelled bar/matrix** cognitive-fingerprint chart, **not** a radar — radar is hard to read on mobile). Pair every chart with a text summary.
   4. **Onboarding intake + auth screens** — trust surfaces; smooth, labelled, clear states.
   5. **Study plan** (`/plan`), **CV** (`/cv`), **`/profile`** (secondary detail page reached from `/me`), **admin health** (shell/typography only).
4. **AI-in-the-loop UX:** skeletons + staged status text for LLM waits (never a bare spinner); "why am I seeing this?" affordance on adaptive recommendations; graceful fallback if the LLM is slow/down. Provenance labels where relevant: **Your data** / **Concourse analysis** / **Competition information**.
5. **Accessibility & mobile baseline (required, not optional):** semantic headings, labelled inputs, visible keyboard focus, ~44px touch targets, sufficient contrast, no colour-only states, keyboard answer-selection in Compass, escape-to-close modals, `prefers-reduced-motion`, and real testing at 360–430px width.

**Explicitly OUT of scope (defer — do not build):** any framework migration, dark mode/theming, full i18n, advanced animation systems, drag-and-drop planning, PWA/offline, marketing-site craft/SEO, a generalized design-system package. Keep it to the smallest change that makes the app coherent and credible.

## 6. How to work — process expectations

- **Incremental, page-by-page.** Each page migration should be an independent, self-contained commit that leaves the app working. Old (un-migrated) and new pages must coexist — they are all still server-rendered HTML, so this is safe.
- **Don't redesign while restyling.** Keep each page's existing layout/UX intact while moving it onto the shared shell + tokens; only change interaction where the plan explicitly says it pays (Compass, dashboard).
- **Commit style:** clear messages, present tense, one logical change each. Example: `Frontend: extract base.html shell + tokens.css; migrate /me as reference page`.
- **Do not build a generic abstraction before its second real use.** Implement, reuse, then extract.
- **One state owner per feature.** Templates for structure; vanilla ES modules for Compass/API-heavy flows. Don't mix competing state approaches on one feature.

## 7. Definition of done (what to hand back)

- All work committed to **`giovanni/frontend-redesign`** and pushed to origin. **`main` untouched** (verify: `git log origin/main` is unchanged from when you started).
- The app runs locally with `uvicorn backend.main:app --reload` and every page renders on the new shared shell.
- A short **`REDESIGN_NOTES.md`** in the repo root summarizing: which pages you migrated, before/after screenshots (or a description if you couldn't capture them), any page you couldn't exercise live (missing creds), and anything you deliberately left for the founders to decide.
- Open a **pull request** from `giovanni/frontend-redesign` into `main` **but do NOT merge it** — it exists so the founders (Giovanni, Leonardo, Stefano) can review and decide. Mark it as a draft / "do not merge — review only."

## 8. If you get stuck or unsure

Stop and ask the owner rather than guessing, specifically for: any credential/secret, any request to add a library or build step, anything that would touch the backend/auth/DB, or anything that would put work on `main`. When in doubt, prefer the smallest, most reversible change.
