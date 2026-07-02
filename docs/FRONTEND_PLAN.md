# Concourse — Frontend MVP Plan (closed pilot)

> **Purpose:** the working plan to make the frontend coherent and credible for a closed pilot of 10–30 paying adult users. Explains the *how*; status/checkboxes live only in `ROADMAP.md` (per CLAUDE.md single-source rule).
> **Basis:** two independent deep-research reports — `../concourse-frontend-mvp-research.md` and `concourse-frontend-deep-research.md` — which converged on the same recommendation with high confidence, plus a grounding pass over the actual repo (2026-07-02).
> **Scope:** frontend transformation only. Does not cover ROADMAP §6 hardening gates (prod Supabase, SMTP, GDPR, secret rotation) — those are separate pilot blockers.

---

## 1. Decision (settled — stop researching the stack)

**Stay build-step-free for the pilot.** Both reports agree: the credibility problem is **inconsistency, not technology**. Paying adults can't see the stack; they can see that the nav differs on every page.

Convert the current hand-rolled HTML pages into:
- **FastAPI + Jinja2 templates** — one `base.html` + shared partials/macros (kills duplication).
- **One design-token CSS layer** — `tokens.css` + `components.css` (~12 primitives).
- **Native ES modules** for behaviour; Compass gets a disciplined module split.
- **Chart.js** (CDN) for the dashboard's limited viz.
- **Supabase magic-link + signed cookies: untouched.**
- **One Railway service, push-to-deploy: unchanged.** No npm, no bundler, no second deploy target, no CI change.

**Runner-up (post-pilot only):** Preact/React + Vite compiled into FastAPI-served static assets. **Not Next.js just to get React.**

**Switch triggers (revisit only when ≥2 are true):** Compass has ≥5 substantially different question interactions; client state persists across several routes; ≥3 devs touch the frontend; component testing becomes necessary; duplicated UI logic keeps growing despite the shared layer; or full i18n across EU languages with locale routing. *Don't switch because vanilla feels unfashionable.*

## 2. Where the reports diverged, and the call made

| Question | Decision | Why |
|---|---|---|
| Alpine.js? | **Start vanilla-only.** Add Alpine later only if one page's local state gets genuinely ugly. | Fewest moving parts; avoids "two ways to do the same thing" during the pilot. |
| Cognitive-fingerprint chart | **Labelled horizontal bar / matrix**, not radar. Keep at most one radar as a summary flourish. | Radar is hard to compare precisely, especially on mobile — our audience studies on phones. |

Otherwise the reports are complementary: **MVP report** = decision, rationale, page priority, effort. **Deep report** = concrete build specs (module split, event taxonomy, a11y checklist, provenance labels).

## 3. Repo grounding (verified 2026-07-02)

- **8 pages, not 7.** `index, intake, me, diagnostic, profile, plan, cv` in `backend/static/`, **plus `compass.html` in the sealed `backend/compass/` tree** (415 lines, served by `backend/compass/api.py` at `/compass`).
- **`/me` is the canonical dashboard** (newer; every page links to it as "Dashboard"). **`/profile` is a secondary detail page** reachable via an "Open →" button on `/me` — not dead, just lower priority.
- **Serving today:** `FileResponse` per route + a `StaticFiles` mount in `backend/main.py`. No Jinja2 yet, no build step → swapping `FileResponse` → `TemplateResponse` page-by-page is low-risk, each page independently deployable.
- **Compass seal (CLAUDE.md):** all Compass code stays under `backend/compass/`; don't couple it to `backend/logic/`, `backend/ai/client.py`, or `backend/auth/`. **This is compatible with the plan** — both reports want Compass to have its *own focused session shell* anyway. Resolution: Compass **consumes the shared `tokens.css`/`components.css` via `<link>`** (visual consistency) but **keeps its own template + JS inside `backend/compass/`** (seal intact, no cross-boundary Python coupling).

## 4. Recommended MVP stack

| Layer | Choice | Note |
|---|---|---|
| App structure | FastAPI + Jinja2 template inheritance | `base.html` + `layouts/` + `components/` macros |
| Styling | Plain CSS custom properties: `tokens.css`, `base.css`, `components.css`, small `utilities.css` | Near-black text on off-white, one confident blue/teal accent, generous whitespace (Linear/Notion cues) |
| Components | ~12 Jinja macros/partials | button, input/select, field(label+hint+error), card, page-header, progress, status-badge, alert/toast, empty-state, modal, skeleton, ai-insight |
| Compass JS | vanilla ES-module split: `state / api / renderer / timer / feedback / session` | framework-like discipline, no framework; keeps a future Preact port cheap |
| Charts | Chart.js v4 (CDN) | mastery line; fingerprint as **bar/matrix**; charts always paired with a text summary |
| Animation | CSS transitions only (120–180ms hover, 180–250ms panels) + `prefers-reduced-motion` | no animation package, no page-transition system |
| Auth | Supabase magic-link + signed cookies, unchanged | biggest hidden cost of a framework — fully avoided |
| Deploy | one Railway service, FastAPI serves everything | unchanged |

**Explicitly rejected for the pilot:** Tailwind Play CDN (runtime CSS, permanent console warnings), shadcn/DaisyUI/Radix/Headless (require React/Tailwind build), Web Components (verbose at this scale), Panda/vanilla-extract (compiled).

**Total new moving parts:** one `templates/` dir, a handful of CSS files, the Compass JS modules, and 1 CDN `<script>` (Chart.js). That's the whole migration.

## 5. Execution plan

Rule: **everything depends on Phase 0 (tokens + shell).** Do it first, together. After that, Compass (protected, non-parallelizable) and the dashboard/other pages run in parallel across the two founders.

### Phase 0 — Foundation (2–3 days, together, blocks everything)
- Add `Jinja2Templates` to `backend/main.py`; create `backend/templates/` (`base.html`, `layouts/{app,auth,marketing}_shell.html`, `components/*.html`).
- Write `static/css/tokens.css` (starter palette + scale in the deep report §2) + `components.css` (~12 primitives). **Version-string the CSS** (`tokens.css?v=1`) — no hash-busting without a build.
- **Migrate `/me` first as the reference page**, end-to-end. Freeze the token/component vocabulary against it before touching other pages.
- Land the **event taxonomy** (§6) so the pilot actually produces learning.

**Phase 0 acceptance bar:** usable at 360px; visible keyboard focus; labelled inputs + inline errors; consistent loading states; no layout shift; one primary action per view; no page-specific inline colours.

### Phase 1 — Core loop (4–5 days)
- **Compass (priority 1 — the product).** Refactor `compass.html` into the module split; `<link>` the shared CSS; build the focused session shell (no dashboard chrome), explanatory feedback (correct/incorrect + error-type + tight rationale + optional "show reasoning"), and a results screen (score, per-dimension delta, one specific insight, one CTA). **Latency trick: pre-generate the next question while the user answers the current one** so the quiz path never visibly waits on the LLM. Autosave + reconnect/retry.
- **Onboarding/intake + diagnostic + auth screens** onto the shell (the trust surfaces). Sequence intake→diagnostic→profile→plan as one coherent flow with progress + "why we ask this."

### Phase 2 — Confidence surfaces (3–4 days)
- **`/me` dashboard:** 4–5 panels max; Chart.js (mastery line + bar/matrix fingerprint). Each insight follows **Observation → Evidence → Implication → Action → Confidence**.
- **`plan`** (primary "Start today's session" card + secondary tasks), **`cv`** (upload/analysis states + provenance), **`profile`** (secondary detail, shell + cleanup), **landing** (credible not optimised — one hero, clear EPSO promise, one CTA), **admin** (shell/typography only).

### Phase 3 — Polish (buffer)
- Real-phone mobile pass on every page (weekly, not just DevTools). Loading/empty/error states everywhere. A11y baseline (§7). `prefers-reduced-motion`.

**Calendar:** ~10–15 focused eng-days ≈ 2.5–3.5 weeks for two people alongside other pilot prep.

### Page priority
| # | Page | Effort | Why |
|---|---|---|---|
| 1 | Compass session + results | 3–5d | The product; 80% of pilot user time |
| 2 | Landing | 1–2d | First impression → converts the 10–30 |
| 3 | `/me` dashboard + insights | 2–3d | Where "the AI understands me" shows; charts live here |
| 4 | Onboarding intake + auth | 1–2d | Everyone passes through once; must feel trustworthy |
| 5 | Study plan | 1d | Daily-return surface |
| 6 | Catalog / CV | 0.5–1d | Used ~once per user |
| 7 | `/profile` (secondary detail) | 0.5d | Shell + cleanup; reachable from `/me` |
| 8 | Admin health | 0–0.5d | Internal; shell only |

## 6. Pilot instrumentation (land in Phase 0, before inviting users)
Event taxonomy: `auth_link_requested, auth_completed, onboarding_started, onboarding_completed, diagnostic_started, diagnostic_completed, plan_viewed, session_started, question_answered, question_timed_out, explanation_opened, session_abandoned, session_completed, next_session_started, cv_uploaded, cv_analysis_completed, ai_operation_failed`.
Per Compass question, record: item tag, selected answer, correctness, response duration, explanation-opened, session position, retry behaviour, generated-vs-curated, (internal) model + prompt version, fallback use.

## 7. Accessibility & mobile baseline (cannot wait)
Semantic heading order · native buttons/links · label every input · visible keyboard focus · ~44px touch targets · sufficient contrast · errors tied to fields · live-region status announcements · no colour-only correctness · keyboard answer-selection in Compass · escape-to-close modals · motion reduction · charts + text summary · test on desktop and 360–430px phones.
**i18n:** pilot in English; just keep strings out of JS logic where easy, avoid text-in-images, don't fix control widths.

## 8. AI-in-the-loop patterns
- **Skeletons + staged status** for generation waits (`Analyzing your last session… → Selecting question patterns…`); never a bare spinner or fake percent bar.
- **Stream only long-form text** (insights, CV fit-read). **Quiz questions appear whole** — pre-generation buffer hides LLM latency.
- **"Why am I seeing this?"** ⓘ on every adaptive recommendation, one plain evidence sentence.
- **Graceful degradation:** LLM slow → pre-generated bank; LLM down → generic practice + honest banner. Never block practice on the model.
- **Hedged insights** ("pattern suggests…") with sample size + thumbs up/down (trust + free labels). Return structured JSON from AI endpoints; render through controlled templates — never let the model emit raw HTML.
- **Provenance labels** where relevant: **Your data** · **Concourse analysis** · **Competition information**.

## 9. Explicitly deferred to post-pilot
Framework migration · separate frontend deploy · full design-system package · Tailwind/CSS-in-JS · dark mode/theming · full i18n pipeline · advanced animation · drag-and-drop planning · realtime/collab · crafted marketing site/SEO · dense data-viz · PWA/offline · native app · full visual-regression testing · generic form engine · Web Component design system.

## 10. Risks / anti-patterns
- **#1 trap: the mid-migration half-framework state** — the recommended path avoids it by never opening it. If a framework is adopted post-pilot, migrate page-by-page with a hard boundary (Compass is the first island) and finish each slice.
- **Don't redesign while restyling** — reskin onto tokens+shell with layouts intact; change UX only where §5 says it pays (Compass, dashboard).
- **One state owner per feature** — templates for structure, vanilla modules for Compass/API-heavy flows; don't mix Alpine + htmx + vanilla on the same feature.
- **Don't build a generic component abstraction before its second real use.**
- **Don't add Tailwind Play CDN "just for now."** Don't split deployment. Version-string CSS. Verify the JWT cookie server-side on state-changing routes.
- **Don't let the dashboard be the main value demo** — Compass demonstrates adaptation during and right after practice.
