# Frontend redesign — handover notes

Branch: `giovanni/frontend-redesign` · Base: `main` @ `d3bf374` (untouched).
Executed per `docs/REDESIGN_BRIEF_FOR_CODING_ASSISTANT.md` + `docs/FRONTEND_PLAN.md`.
Build-step-free: no npm, no bundler, no framework. One CDN script (Chart.js, on `/me` only).

## What changed

### Foundation (commit `97505b6`)
- `backend/templates/base.html` — Jinja2 shell: `<head>`, nav, footer, script loading defined once. Pages override blocks (`nav`, `content`, `head`, `scripts`, `wrap_class`).
- `backend/static/css/tokens.css` — design tokens (near-black ink on off-white, one blue accent `#2255c4`, type/spacing scales, radii, shadows, motion, focus ring). Version-stringed (`?v=1`); bump the query string on every CSS change.
- `backend/static/css/base.css` — reset, typography, nav/footer shell, skip link, global `:focus-visible`, `prefers-reduced-motion`.
- `backend/static/css/components.css` — ~12 primitives: btn, card (+cta), field/input, kv, badge, progress, alert, empty-state, modal, skeleton, ai-insight, option (quiz answer), choice (picker/likert chips).
- `backend/static/js/app.js` — shared shell behaviour: PostHog init (all pages now instrumented, was landing-only), `window.ctrack()` event helper, `[data-logout]`, Escape/scrim-close for modals.
- `backend/main.py` — added `Jinja2Templates`; page routes swapped `FileResponse` → `TemplateResponse` one-by-one (same URLs, same auth, same response type). No other backend changes. `requirements.txt`: + `jinja2`.

### Pages (in plan priority order)
| Page | Commit | Notes |
|---|---|---|
| `/me` (reference page) | `97505b6` | Reorganized 9 cards → 5 panels: practice CTA, Progress (score tiles + Chart.js accuracy-trend line + text summary + recent sessions), AI insight (provenance-labelled), prep summary (kv), next steps (CV + calibration). All API calls/states preserved. |
| `/compass` | `ac6e468` | Focused session shell (no dashboard chrome), thin progress bar, subdued session timer, keyboard answers (1–4 + Enter), aria-live feedback, correct/wrong marked with ✓/✕ text (not colour-only), staged status text on session start, results screen with observation as labelled analysis callout. Template + JS stay in `backend/compass/` — single file by design (see open questions). |
| `/` landing | `b5abe5d` | One hero, one primary CTA ("How it works" demoted to text link), shared modal for signup/OTP. UTM capture moved to `<head>` so it precedes PostHog init. |
| `/intake` + `/diagnostic` | `8350d9b` | Intake: accessible radio-backed likert/toggle chips, "why we ask this" per card, plan-first submit flow untouched. Diagnostic: focused shell, shared quiz vocabulary, keyboard selection. |
| `/plan`, `/cv`, `/profile` | `3e70ed2` | Restyle only, layouts intact. Allocation bars on shared progress primitive with aria labels; CV fit + profile AI read get skeleton + staged status text; provenance labels (Your data / Concourse analysis / Competition information) where relevant. |

All 8 `backend/static/*.html` files are retired; every page is served from `backend/templates/` (Compass from `backend/compass/static/`).

### Pilot instrumentation (plan §6, partial)
`ctrack()` wired for: `auth_link_requested`, `auth_completed` (OTP path), `onboarding_completed`, `diagnostic_started/completed`, `plan_viewed`, `session_started`, `question_answered` (with time, position, source), `session_completed`, `cv_uploaded`, `cv_analysis_completed`, `ai_operation_failed`. Not wired (no clean client hook): `question_timed_out`, `explanation_opened`, `session_abandoned`, `next_session_started`, magic-link `auth_completed` (fires inside the sealed callback page).

## Accessibility & mobile baseline
Semantic headings on every page (diagnostic gets an sr-only h1) · every input labelled (or `aria-labelledby`) · visible keyboard focus ring everywhere · 44px touch targets on buttons/options/chips · correctness states carry text markers, not colour alone · `aria-live` on quiz feedback and async status · Escape closes modals · `prefers-reduced-motion` kills transitions/skeleton shimmer · responsive at 360–430px via media queries (score grids, energy grid, CTA cards, alloc rows collapse to one column).

## What I could NOT exercise live (please verify before merging)
My sandbox couldn't open raw TCP to Supabase Postgres (HTTP-only egress), so **every DB/LLM-backed flow was verified only as served HTML + JS syntax, not end-to-end**: real dashboard data, intake submit, diagnostic/Compass sessions with live questions, plan generate, profile narrate, CV states. All page routes return 200 and all JS parses, but do one logged-in click-through on :8000 vs :8001. CV upload additionally blocked by `storage_configured: false` (expected). No real-phone pass — DevTools-width only.

## Deliberately left for you three to decide
1. **Compass ES-module split** — the plan wants `state/api/renderer/timer/feedback/session` as separate ES modules, but serving extra JS files from `backend/compass/` needs a new static mount/route in `compass/api.py` (backend change, seal-adjacent). I kept one file with module-section comments instead. Decide: add the mount, or accept the single file for the pilot.
2. **Auth callback interstitial** (`backend/auth/__init__.py`) — inline-styled spinner page inside the sealed auth module; left untouched. It flashes for ~1s; restyling means editing sealed code.
3. **Admin compass health page** (`backend/compass/api.py`) — inline HTML in sealed Compass code; left as-is (internal-only, plan priority 8 / 0–0.5d).
4. **Cognitive-fingerprint chart** — no API currently exposes per-dimension mastery, so `/me` has the mastery/accuracy trend line + baseline score tiles, no fingerprint bar/matrix yet. Needs a small Compass API addition first.
5. **Question pre-generation** (plan §5 latency trick) and autosave/reconnect — backend work, out of a frontend-only branch.
6. **Landing copy/pricing** (€24.99, "watches EUTraining and ORSEU") — carried over verbatim; review before pilot invites.
7. **PostHog on all pages** — analytics now loads everywhere (was landing-only). If you don't want authed-page tracking yet, comment out the init in `static/js/app.js`.

## Before/after in one line
Eight hand-rolled pages with eight inline `<style>` blocks and three different navs → one token file, one component vocabulary, one shell, every page recognisably the same product.

No screenshots (no browser in my sandbox) — run `uvicorn backend.main:app --reload --port 8001` next to prod-main on :8000 and compare side by side.
