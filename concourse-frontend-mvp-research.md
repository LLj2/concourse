# Concourse Frontend — MVP/Pilot Deep-Research Report

*Prepared July 2026. Scope: cheapest, fastest frontend transformation credible for a closed pilot of 10–30 paying adult users in the next few weeks.*

---

## 1. Recommendation

**Primary path: stay build-step-free (Option A, with a thin slice of C).** Convert the 7 static HTML pages into **Jinja2 templates served by your existing FastAPI app**, extract a **shared design-token CSS layer** (one `tokens.css` + one `components.css`), a **shared shell template** (nav, footer, typography), and keep **vanilla ES-module JS** — upgrading only the Compass quiz surface to a small self-contained "island" (vanilla, or Preact+HTM via CDN if state gets hairy). No npm, no bundler, no second deploy target, no CI change. Railway deploy stays exactly as it is: git push.

Confidence: **high**. For a 2-person team, 7 pages, a few weeks, and one Python-led deployment, every framework option loses on the three dominant criteria (velocity, migration cost, deploy simplicity) while buying design ceiling you don't need until post-pilot. Your credibility problem is **inconsistency, not technology** — paying adults can't see your stack; they can see that the nav is different on every page.

**Runner-up:** SvelteKit (or Vite+React SPA) as a separate frontend, built and mounted into FastAPI as static output. Genuinely nice, but it adds a Node toolchain, a build step in CI, a client-side auth story to re-verify, and a mid-migration two-worlds state — all pure cost inside the pilot window.

**Post-pilot switch trigger — be specific about it:** adopt a framework when *any* of these becomes true:

- The Compass quiz island exceeds roughly ~1,500 lines of hand-rolled state logic, or you need offline/optimistic sync, cross-component reactive state, or real-time collaboration. (Complex client-side state is exactly the case where lightweight stacks stop paying off — [OpenReplay](https://blog.openreplay.com/htmx-vs-alpine-when-use/), [PkgPulse 2026 guide](https://www.pkgpulse.com/guides/htmx-vs-alpinejs-2026).)
- You commit to full i18n across 24 EU languages with locale routing — framework i18n tooling starts earning its keep.
- You hire a frontend specialist whose velocity is higher in React/Svelte than in templates.

If none fire, you can ride this stack well past the pilot. Note also: FastAPI 0.138 (June 2026) shipped native `app.frontend()` for serving a built SPA with client-routing fallback ([explainer](https://umesh-malik.com/blog/fastapi-spa-app-frontend-explained)) — so the *later* migration path to a real SPA on the same Railway service is now smoother than it was, which lowers the cost of deferring the decision. Deferring is cheap; that's the point.

---

## 2. Comparison table

Weights (MVP-tuned): **Velocity & migration cost 35%, Deploy simplicity on Railway 25%, Credible-for-adults design 20%**, quiz-UI fit 8%, a11y/mobile 5%, maintainability/AI-friendliness 4%, performance 3%. Scores 1–5.

| Criterion (weight) | **A. Build-step-free: Jinja2 + token CSS + vanilla/htmx** | **B1. SvelteKit app** | **B2. Vite + React SPA + shadcn** | **C. Astro (marketing) + islands** |
|---|---|---|---|---|
| Velocity & migration cost (35%) | **5** — page-by-page, each page shippable same day; zero new concepts | 2.5 — new framework + Node toolchain + rewrite of all 7 pages | 2.5 — same, plus SPA routing/auth plumbing | 3 — new toolchain but templates map naturally to `.astro` |
| Railway deploy simplicity (25%) | **5** — unchanged; FastAPI serves everything | 2.5 — second service or Node build in CI; SSR needs a Node runtime | 3 — static build can mount into FastAPI (`app.frontend()`), but CI now needs Node | 3 — static output mountable, but build step in CI |
| Credible design for paying adults (20%) | **4** — a token system + consistent shell clears the bar; ceiling lower than framework ecosystems | 5 | 5 — shadcn/Radix is the polish king ([comparison](https://windframe.dev/blog/daisyui-vs-shadcn-ui)) | 4.5 |
| Adaptive quiz UI fit (8%) | 3.5 — fine for one island now; hurts if state grows | 5 | 5 | 4 — islands are literally the model |
| A11y & mobile basics (5%) | 4 — semantic HTML is a head start; discipline required | 4 | 4.5 (Radix primitives) | 4 |
| Maintainability & AI-coding friendliness (4%) | 4 — LLMs excel at plain HTML/CSS/Jinja; no version-churn traps | 4 | 4.5 — largest training corpus | 4 |
| Performance / first load (3%) | **5** — no JS bundle at all on marketing page | 4.5 | 3.5 | 5 |
| **Weighted total** | **≈4.7** | ≈3.3 | ≈3.5 | ≈3.6 |

The gap is not close, and it's driven entirely by the three dominant criteria. B2 and C only win if you re-weight for design ceiling and long-run product complexity — which is the post-pilot question, not this one.

---

## 3. Recommended MVP stack (concrete)

| Layer | Choice | One-line justification |
|---|---|---|
| Framework | **None — FastAPI + Jinja2 template inheritance** | Turns 7 duplicated HTML files into 1 base template + 7 thin children with zero new toolchain; FastAPI's Jinja2 support is first-class ([docs](https://fastapi.tiangolo.com/advanced/templates/)). |
| Styling | **Hand-rolled design tokens in CSS custom properties** (`tokens.css`) + a small `components.css` (~300–500 lines: buttons, cards, forms, badges, nav) | Custom properties *are* a design-token system with no compiler ([CSS-Tricks](https://css-tricks.com/open-props-and-custom-properties-as-a-system/)); it looks intentional rather than templated because you chose the values. Crib scale/shadow/easing values from [Open Props](https://open-props.style/) without importing it. |
| Component reuse | **Jinja2 macros/partials** (`_button.html`, `_card.html`, `_nav.html`) | Server-side components with props, no JS framework needed; underscore-prefix partials are the established convention ([FastAPI+HTMX guide](https://blakecrosley.com/guides/fastapi-htmx)). |
| Dynamic fragments (optional) | **htmx (~14 kB, CDN)** only where a page needs partial updates (catalog filters, dashboard panels) — pair with [jinja2-fragments](https://github.com/sponsfreixes/jinja2-fragments) | Server-driven interactivity with zero build; skip it entirely on pages that don't need it. |
| Quiz island | **Vanilla ES module now; Preact + HTM via CDN/import-map (~5 kB) if state outgrows it** | Preact+HTM gives the React component model with no build step ([Preact no-build docs](https://preactjs.com/guide/v10/no-build-workflows/), [worked example](https://www.endpointdev.com/blog/2025/10/preact-web-app-without-npm-build/)). |
| Charts | **Chart.js v4 via CDN** — line (mastery over time) + radar (cognitive fingerprint) built in | The pragmatic default in 2026; both chart types out of the box, minutes to first chart ([Strapi comparison](https://strapi.io/blog/chart-libraries)). uPlot is smaller but line-only and sparsely documented; ECharts is overkill. A pure-CSS heatmap grid needs no library at all. |
| Animation | **CSS transitions + `prefers-reduced-motion`; nothing else** | Micro-transitions on buttons/cards/answer-reveal deliver 90% of perceived polish for ~0 cost; animation *systems* are post-pilot. |
| Auth | **Keep Supabase magic-link + server-set signed cookies, untouched** | It's the architecturally correct pattern for a server-rendered app (tokens in secure cookies, validated server-side — [Supabase SSR guide](https://supabase.com/docs/guides/auth/server-side/advanced-guide)); every framework option would force you to re-verify or rebuild it. Biggest hidden cost of Option B, fully avoided. |
| Deployment | **One Railway service, FastAPI serves templates + `/static`, auto-deploy on push — unchanged** | Anything else adds a deploy target for zero pilot benefit. |
| Explicitly rejected for the pilot | Tailwind Play CDN (dev-only, runtime-generated CSS, unsuppressable production warnings — [issue](https://github.com/tailwindlabs/tailwindcss/issues/18731)); shadcn/DaisyUI (require Tailwind build); Web Components (verbose, low payoff at 7 pages); Alpine.js (fine tool, but vanilla JS covers your needs — don't add two ways to do the same thing) | Fewest moving parts that clear the bar. |

**New moving parts total: one `templates/` directory, two CSS files, one shared JS module, and two CDN `<script>` tags (Chart.js; htmx if used).** That's the whole migration.

---

## 4. MVP execution plan (the core)

### 4.1 The smallest credible transformation

Credibility for adult professionals = **coherence + calm + fast + nothing broken on mobile**. Concretely: same nav/footer/typography on every page, one accent color used consistently, real form states (focus, error, disabled, loading), no layout shift, tap targets ≥44px, and honest AI loading states. That is achievable without touching your architecture.

### 4.2 What to standardize first (in order)

1. **`tokens.css`** — one afternoon, highest leverage file in the project. Define: 2 font stacks (a good variable font for headings — e.g. Inter or a serif accent — + system stack for body), a 5-step type scale, a spacing scale (4/8/12/16/24/32/48/64), one brand accent + neutral gray ramp (9 steps) + semantic colors (success/warn/error), 3 radii, 3 shadows, 2 transition durations. Serious-adult palette: near-black text on off-white, one confident blue/teal accent, generous whitespace — Linear/Notion cues, zero cartoon mascots.
2. **Shared shell** — `base.html` with nav, footer, `<meta viewport>`, font loading, and the two CSS files. Convert pages to extend it one at a time.
3. **`components.css`** — buttons (primary/secondary/ghost + loading spinner state), form fields with visible focus rings and inline error text, card, badge/pill, progress bar, skeleton-shimmer block. ~400 lines covers the whole app.
4. **Forms & buttons audit** — onboarding intake and auth are where trust is won or lost; make every input use the shared classes, every submit show a pending state.

Introduction pattern (no big bang): ship `base.html` + tokens with page 1; each subsequent page conversion is an independent, deployable PR. Old and new pages coexist harmlessly because everything is still server-rendered HTML — this is the classic page-by-page strategy, lowest-risk of all migration shapes ([Vercel incremental-migration guide](https://vercel.com/kb/guide/incremental-migrations-with-microfrontends), [frontend migration guide](https://frontendmastery.com/posts/frontend-migration-guide/)).

### 4.3 Page priority for pilot credibility

| Priority | Page | Why | Effort |
|---|---|---|---|
| 1 | **Compass quiz session + results** | The product. Pilot users spend 80% of their time here; it must feel instant, focused, and polished. | 3–5 days |
| 2 | **Landing page** | First impression → conversion of the 10–30. One strong hero, clear promise, one CTA. Craft beyond that: deferred. | 1–2 days |
| 3 | **/me dashboard + insight panels** | Where "the AI understands me" becomes visible; this is the retention/wow surface. Charts live here. | 2–3 days |
| 4 | **Onboarding intake + magic-link screens** | Every pilot user passes through once; must be smooth and trustworthy, not beautiful. | 1–2 days |
| 5 | **Study plan view** | Daily-return surface; needs the shared shell + a clean task list, nothing fancy. | 1 day |
| 6 | **Catalog picker** | Used once per user; shell + card grid is enough. | 0.5–1 day |
| 7 | **Admin health page** | Internal. Shell only, or leave it ugly. | 0–0.5 day |

### 4.4 Sequencing for 2 people (~2.5–3.5 weeks total)

- **Week 1** — Founder A (eng lead): tokens + base shell + components.css; convert landing + auth + onboarding onto it. Founder B (parallel): audit copy/content of all 7 pages; spec quiz-session UX (states, feedback, timer, results — see §4.6); pick palette/font.
- **Week 2** — A: quiz session rebuild on the island pattern (biggest single chunk, not parallelizable — protect this time). B: dashboard layout + Chart.js panels (parallelizable once tokens exist); convert study plan + catalog.
- **Week 3** — Integration polish: mobile pass on every page (real phones), loading/error states everywhere, empty states for new users, a11y basics pass (focus order, labels, contrast-check the palette, `prefers-reduced-motion`). Buffer for the inevitable.

Parallelization rule: everything depends on tokens+shell (do first, together if needed); after that, quiz and dashboard/other pages proceed in parallel.

### 4.5 Defer-to-post-pilot list (do NOT do these now)

- **Framework adoption** — re-evaluate against §1 triggers with real pilot data; `app.frontend()` keeps the door open cheaply.
- **Full component-library maturity** — 8 components cover 7 pages; a Storybook-grade system serves an audience you don't have.
- **Animation polish / page transitions** — CSS micro-transitions clear the bar; motion design has near-zero pilot ROI.
- **Dark mode / theming** — tokens make it a cheap *later* add (that's why you're building tokens); zero pilot users will churn over it.
- **Full i18n** — pilot in English (EPSO candidates are professionally fluent; the exams themselves have major English components). Confirm with pilot users; 24-language support is a launch problem. Just avoid hardcoding strings into JS where easy.
- **Deep accessibility hardening** — do the basics now (semantic HTML, labels, contrast, focus, touch targets); full WCAG 2.1 AA audit + screen-reader testing at launch. Semantic server-rendered HTML means you're not digging a hole meanwhile.
- **Marketing-page craft** (testimonials, comparison pages, SEO, OG polish) — pilot users arrive by invite, not search.
- **CDN/asset pipeline, cache-busting, image optimization** — 30 users on Railway will never notice; version-query-string your two CSS files and move on.

### 4.6 Adaptive-quiz UX: what to borrow, what to avoid

**Borrow** (patterns consistent across Duolingo, Khan Academy, Brilliant — [Khan's adaptive design](https://www.edtechupdate.com/adaptive-learning/khan-academy/), [Duolingo UX analyses](https://uxplanet.org/analyzing-duolingo-from-product-design-perspective-after-400-days-of-non-stop-practice-c4d4809bdb37)):

- **One question per screen, chrome-free.** Full-width focused card, thin progress bar top, timer top-right (subdued — countdown anxiety is real for exam-anxious users; consider count-up with a soft limit for practice mode vs. strict countdown for exam-sim mode).
- **Immediate, explanatory feedback.** Answer → instant correct/incorrect + a tight explanation + "what pattern this tests." The explanation is where an adult tool earns trust; Brilliant's explain-why model over Duolingo's ding.
- **Session-sized chunks with a clean end-screen.** 10–15 questions, then a results screen: score, per-dimension deltas, one specific insight ("your numerical-reasoning speed under time pressure improved"), one CTA ("tomorrow: abstract-pattern drills"). This end-screen *is* your Compass demo — invest here.
- **Streaks/progress as calm data, not celebration.** Adults respond to evidence of progress (mastery curves, "23% faster than last week") — Linear-style, not confetti.
- **Spaced resurfacing made visible.** "You last missed this pattern 4 days ago" — showing the engine's memory is the cheapest way to make Compass feel intelligent.

**Avoid as too childish:** mascots/characters, XP/gems/lives, celebratory full-screen animations, streak-guilt notifications, leaderboards (pilot cohort is too small and it's competitive-anxiety fuel for this audience), cutesy error copy. Tone: a sharp, encouraging tutor — never a game.

### 4.7 AI-in-the-loop UI patterns

- **Skeletons + staged status for generation waits.** LLM latency is variable (1–25 s); show a skeleton of the *shape* of what's coming plus honest staged text ("Analyzing your last session… → Selecting question patterns…") — never a bare spinner, never a fake percent bar ([AI loading-states pattern](https://uxpatterns.dev/patterns/ai-intelligence/ai-loading-states), [Cloudscape gen-AI patterns](https://cloudscape.design/gen-ai/patterns/generative-ai-loading-states/)).
- **Stream only long-form text.** Insights/fit-reads stream token-by-token (SSE from FastAPI is trivial, htmx has an SSE extension); quiz questions should *appear whole* — pre-generate the next question while the user answers the current one, so the quiz path never visibly waits on the LLM. This buffer is your single best latency trick.
- **"Why am I seeing this" affordance.** A small ⓘ on every AI insight/next-session choice with one plain sentence ("You missed 3 of 4 syllogism items on Tuesday"). Cheap, and it's the difference between "smart tool" and "black box" ([AI chat UX best practices](https://thefrontkit.com/blogs/ai-chat-ui-best-practices)).
- **Graceful degradation ladder.** LLM slow → cached/pre-generated question bank; LLM down → generic (non-adaptive) practice set + honest banner ("personalization is catching up — here's a solid session meanwhile"). Never block practice on the model ([degradation-tier pattern](https://www.getunleash.io/blog/graceful-degradation-featureops-resilience)).
- **Hedged, feedback-able insights.** Phrase fingerprint claims as observations ("pattern suggests…"), add thumbs up/down — trust for skeptical professionals *and* free label data.

---

## 5. Risks, gotchas, anti-patterns

- **#1 trap: the mid-migration half-framework state.** Two rendering paradigms, duplicated components, an auth story that works in one world and not the other — with a 2-person team you *will* stall there and demo from the stalled state. The recommended path avoids the trap by never opening it; if you do adopt a framework post-pilot, migrate page-by-page with the same discipline and finish each slice ([migration guide](https://frontendmastery.com/posts/frontend-migration-guide/)).
- **Don't redesign while restyling.** Reskin pages onto tokens+shell with layouts intact; UX changes only where §4.3 says they pay (quiz, dashboard). Combining redesign + restyle doubles scope invisibly.
- **Don't hand-roll quiz state as scattered globals.** One island, one explicit state object (`{session, currentQuestion, answers, phase}`), pure render functions. This is also what keeps the future Preact/framework port cheap.
- **Don't add Tailwind Play CDN "just for now."** Dev-only, runtime CSS generation, permanent console warnings ([issue #18731](https://github.com/tailwindlabs/tailwindcss/issues/18731)) — and it drags you toward the build step you're avoiding.
- **Don't split deployment.** A separate Vercel/Netlify frontend means CORS, cookie-domain config for your auth, env drift, and a second thing to break during the pilot. One Railway service.
- **Don't trust the JWT cookie without verification** on state-changing routes — validate server-side (`auth.getUser` or JWT verification), per Supabase's own SSR guidance ([advanced guide](https://supabase.com/docs/guides/auth/server-side/advanced-guide)).
- **Do version-string your CSS** (`tokens.css?v=3`) — with no build step there's no hash-busting, and stale-CSS bugs during a pilot look like broken product.
- **Test on real phones weekly.** Your audience studies on mobile in short sessions; DevTools emulation misses Safari quirks, keyboard-overlap on forms, and tap-target reality.
- **The honest case against this recommendation** (so you can falsify it): if the Compass UI you actually spec has heavy cross-component reactivity — live-updating fingerprint viz *during* the session, drag interactions, offline queuing — vanilla will hurt within weeks, and jumping straight to a Vite+Preact (or React) island *now*, embedded in otherwise-server-rendered pages, would be the right call at the cost of one build step. Decide when B specs the quiz in week 1, not later.

---

## Sources

Stack & migration: [OpenReplay — HTMX vs Alpine](https://blog.openreplay.com/htmx-vs-alpine-when-use/) · [PkgPulse 2026](https://www.pkgpulse.com/guides/htmx-vs-alpinejs-2026) · [Django forum: React vs htmx+Alpine](https://forum.djangoproject.com/t/react-vs-htmx-alpine-js/22345) · [Vercel incremental migrations](https://vercel.com/kb/guide/incremental-migrations-with-microfrontends) · [Frontend Mastery migration guide](https://frontendmastery.com/posts/frontend-migration-guide/) · [FastAPI templates docs](https://fastapi.tiangolo.com/advanced/templates/) · [FastAPI `app.frontend()` explained](https://umesh-malik.com/blog/fastapi-spa-app-frontend-explained) · [FastAPI+HTMX no-build guide](https://blakecrosley.com/guides/fastapi-htmx) · [jinja2-fragments](https://github.com/sponsfreixes/jinja2-fragments) · [Railway FastAPI guide](https://docs.railway.com/guides/fastapi) · [Preact no-build workflows](https://preactjs.com/guide/v10/no-build-workflows/) · [Preact without npm (2025)](https://www.endpointdev.com/blog/2025/10/preact-web-app-without-npm-build/)

Design layer & charts: [CSS-Tricks — Open Props & custom properties as a system](https://css-tricks.com/open-props-and-custom-properties-as-a-system/) · [Open Props](https://open-props.style/) · [Pico CSS](https://github.com/picocss/pico) · [DaisyUI vs shadcn](https://windframe.dev/blog/daisyui-vs-shadcn-ui) · [Strapi chart-library comparison](https://strapi.io/blog/chart-libraries) · [Tailwind Play CDN docs](https://tailwindcss.com/docs/installation/play-cdn) · [Tailwind CDN production warning issue](https://github.com/tailwindlabs/tailwindcss/issues/18731)

Auth: [Supabase server-side auth advanced guide](https://supabase.com/docs/guides/auth/server-side/advanced-guide) · [Supabase Auth + FastAPI](https://phillyharper.medium.com/using-supabase-auth-on-the-server-side-with-fastapi-bb2300296d9b)

UX patterns: [Khan Academy adaptive learning](https://www.edtechupdate.com/adaptive-learning/khan-academy/) · [Duolingo product-design analysis](https://uxplanet.org/analyzing-duolingo-from-product-design-perspective-after-400-days-of-non-stop-practice-c4d4809bdb37) · [Brilliant vs Khan](https://www.studley.ai/blog/brilliant-vs-khan-academy) · [AI loading states pattern](https://uxpatterns.dev/patterns/ai-intelligence/ai-loading-states) · [Cloudscape generative-AI loading patterns](https://cloudscape.design/gen-ai/patterns/generative-ai-loading-states/) · [AI chat UI best practices](https://thefrontkit.com/blogs/ai-chat-ui-best-practices) · [Graceful degradation in practice](https://www.getunleash.io/blog/graceful-degradation-featureops-resilience)
