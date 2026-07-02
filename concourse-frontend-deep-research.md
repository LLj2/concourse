# Concourse frontend recommendation for the closed pilot

## Executive decision

**Stay build-step-free for the pilot.**

Keep FastAPI as the single application and deployment unit. Replace the seven isolated page implementations with:

- shared server-rendered templates and partials
- one design-token CSS foundation
- a small set of reusable CSS components
- native ES modules for page behaviour
- Alpine.js only where local reactive state materially reduces code
- a dedicated vanilla JavaScript module for Compass
- Chart.js for the limited dashboard visualisations

Do **not** introduce React, Next.js, SvelteKit, Nuxt, Astro or a separate frontend service before the pilot.

The current frontend problem is mostly duplication, inconsistent styling and weak information hierarchy. A framework would solve those problems eventually, but adopting one now would also create a migration, build pipeline, routing decisions, auth changes and possibly a second Railway service. None of those directly improves the first 10–30 users’ experience.

The runner-up is **Preact or React with Vite, compiled to static assets and served by FastAPI**. This becomes the preferred direction when Compass develops enough interconnected client state that changes regularly become risky, or when the product reaches roughly 15–20 meaningful application screens with several engineers working on them.

The specific post-pilot switching trigger should be:

> Move Compass, and eventually the authenticated application shell, to a compiled component framework when two or more of the following are true: Compass has at least five substantially different question interactions; client state persists across several routes; three or more developers modify the frontend; automated component testing becomes necessary; or duplicated UI logic continues growing despite the shared template and module layer.

Do not switch solely because the vanilla code feels unfashionable.

## 1. Weighted stack comparison

Weights reflect the stated pilot objective:

| Criterion | Weight |
|---|---:|
| Development velocity and migration cost | 35% |
| Deployment simplicity | 25% |
| Credible design quality | 15% |
| Adaptive quiz suitability | 10% |
| Accessibility and mobile basics | 5% |
| Maintainability and AI coding | 5% |
| Performance | 5% |

Scores are 1–10. Weighted totals are out of 100.

| Option | Velocity / migration | Deploy | Design | Quiz | A11y / mobile | Maintainability | Performance | Total |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| **FastAPI templates + CSS tokens + ES modules + selective Alpine** | 9.5 | 10 | 8 | 7.5 | 8 | 7.5 | 9.5 | **90** |
| **FastAPI + htmx + Alpine + CSS tokens** | 8.5 | 9.5 | 8 | 7 | 8 | 8 | 9 | **85** |
| **Preact/React + Vite build served by FastAPI** | 6 | 8 | 9 | 9 | 8.5 | 9 | 8.5 | **74** |
| **Next.js or SvelteKit as a separate application** | 3.5 | 4.5 | 9.5 | 9.5 | 8.5 | 9 | 8 | **59** |

### Why the first option wins

FastAPI can continue to serve all HTML, API routes and static assets from one Railway service. Railway’s current FastAPI guidance supports direct GitHub deployment and configuration inside the repository, preserving the existing push-to-deploy workflow.

Native Web Components could technically provide reusable custom elements without a framework. The underlying browser technologies are mature and designed for reusable, encapsulated elements. However, introducing Shadow DOM, custom-element lifecycle rules and styling boundaries would add conceptual overhead disproportionate to seven pages. Use ordinary templates and CSS classes first.

Alpine can be added with a script tag and supplies local state, event handling, binding, conditional rendering and transitions without a build process. That makes it suitable for dropdowns, onboarding steps, tabs and lightweight dashboard interactions.

htmx is also build-free and dependency-free, and can progressively enhance normal links and forms. It is useful when the server naturally returns HTML fragments. Concourse already has working vanilla fetch-based flows, so converting everything to fragment endpoints would create unnecessary churn. Use htmx only where it removes code rather than as a new architectural religion.

## 2. Recommended pilot stack

### Application structure

**FastAPI + Jinja2 templates and partials**

Create one shared base template containing the document head, typography imports, global navigation, alert area, footer and script loading. Break repeated structures into partials or macros:

```text
templates/
  base.html
  layouts/
    app_shell.html
    auth_shell.html
    marketing_shell.html
  components/
    button.html
    field.html
    progress.html
    card.html
    status_badge.html
    empty_state.html
    ai_insight.html
  pages/
    landing.html
    login.html
    onboarding.html
    diagnostic.html
    compass.html
    plan.html
    me.html
    admin.html
```

This is the highest-return architectural change. It produces visible consistency while preserving every existing backend route.

### Styling

**Plain CSS custom properties, organised into four files**

```text
static/css/
  tokens.css
  base.css
  components.css
  utilities.css
```

A fifth page-specific stylesheet is acceptable for Compass:

```text
static/css/pages/compass.css
```

Do not reproduce Tailwind through hundreds of home-grown utility classes. Keep utilities to a limited set for spacing, layout, visibility and text alignment.

Recommended token categories:

```css
:root {
  /* Colour */
  --color-canvas: #f7f8fa;
  --color-surface: #ffffff;
  --color-surface-subtle: #f0f3f6;
  --color-text: #17202a;
  --color-text-muted: #647182;
  --color-border: #dbe1e8;
  --color-accent: #3659d9;
  --color-accent-hover: #2947ba;
  --color-success: #237a57;
  --color-warning: #9a6517;
  --color-danger: #b34444;

  /* Typography */
  --font-sans: Inter, system-ui, -apple-system, BlinkMacSystemFont, sans-serif;
  --text-xs: 0.75rem;
  --text-sm: 0.875rem;
  --text-base: 1rem;
  --text-lg: 1.125rem;
  --text-xl: 1.375rem;
  --text-2xl: 1.75rem;

  /* Geometry */
  --radius-sm: 6px;
  --radius-md: 10px;
  --radius-lg: 16px;

  /* Spacing */
  --space-1: 0.25rem;
  --space-2: 0.5rem;
  --space-3: 0.75rem;
  --space-4: 1rem;
  --space-6: 1.5rem;
  --space-8: 2rem;

  /* Effects */
  --shadow-card: 0 1px 2px rgb(20 30 45 / 6%),
                 0 5px 18px rgb(20 30 45 / 5%);
}
```

The design should use restrained surfaces, obvious hierarchy, clear labels, moderate rounding and minimal decoration. The distinguishing visual element should be Compass’s cognitive insights, rather than a large palette or extensive animation.

### Components

Build approximately twelve primitives:

1. Button
2. Text input and select
3. Form field with label, hint and error
4. Card
5. Page header
6. Progress indicator
7. Status badge
8. Alert or toast
9. Empty state
10. Modal or confirmation dialog
11. Skeleton or loading panel
12. AI insight panel

Avoid building a generalized design-system package. Shared HTML macros plus stable classes are enough for the pilot.

### JavaScript

**Native ES modules as the default**

```text
static/js/
  app.js
  lib/
    api.js
    auth.js
    dom.js
    errors.js
  components/
    modal.js
    toast.js
    file-upload.js
  pages/
    onboarding.js
    diagnostic.js
    compass.js
    plan.js
    me.js
```

Separate state and API communication from DOM manipulation inside Compass:

```text
compass/
  state.js
  api.js
  renderer.js
  timer.js
  feedback.js
  session.js
```

This gives Compass framework-like discipline without requiring a framework.

### Alpine.js

Use Alpine for small bounded behaviours:

- mobile navigation
- disclosure panels
- tabs
- onboarding step visibility
- modal state
- filters
- “show explanation” controls

Do not put the whole Compass session state into a large inline `x-data` object.

Vendor the production file into the repository instead of loading it from a public CDN.

### Charts

**Chart.js**

Use it for:

- mastery trend line
- competency bar chart
- one compact radar chart, only when the dimensions are stable
- session accuracy or speed trend

For cognitive fingerprints, prefer a labelled horizontal bar or matrix to a radar chart. Radar charts look distinctive but are harder to compare precisely, particularly on mobile. One radar can serve as a memorable summary; detailed diagnosis should remain textual and tabular.

### Animation

Use native CSS transitions only:

- 120–180 ms for hover and focus changes
- 180–250 ms for panel changes
- no page transition system
- no animation package
- respect `prefers-reduced-motion`

Feedback should feel immediate, not theatrical.

### Deployment topology

```text
Railway service
└── FastAPI
    ├── HTML routes
    ├── API routes
    ├── auth and signed cookies
    ├── static CSS
    ├── static JavaScript
    └── static icons/fonts
```

No second service, Node server, frontend domain, CORS configuration or extra CI process.

### Authentication

Keep the existing Supabase magic-link flow and server-set signed cookies.

Moving to Next.js SSR would require introducing Supabase’s JavaScript SSR client, separate browser and server clients, token-refresh proxy logic and careful cookie handling. There is no pilot benefit in replacing an auth implementation that already works.

One current housekeeping point: Supabase is moving from legacy `anon` and `service_role` keys toward publishable and secret keys, with legacy keys expected to be deprecated by the end of 2026. That should be scheduled as a backend security task, independent of the frontend migration.

## 3. MVP execution plan

A credible transformation can be completed in approximately **10–15 focused engineering days**, excluding major content or backend changes.

This assumes one founder drives implementation while the other makes rapid product and design decisions. Calendar duration may be two to three weeks because the work will compete with backend and pilot preparation.

### Phase 1: establish the system, 2–3 days

Create:

- base template and application shell
- tokens
- typography and layout rules
- buttons, inputs, cards and alerts
- responsive breakpoints
- error, loading and empty-state conventions
- one icon set
- page-width and spacing rules

Choose one representative page, probably `/me`, and migrate it completely. Use it to validate the system before touching the remaining pages.

Required acceptance standard:

- usable at 360 px width
- visible keyboard focus
- form labels and error text
- consistent loading states
- no layout shift caused by late content
- one primary action per view
- no inline page-specific colour values unless genuinely semantic

### Phase 2: rebuild the pilot’s core loop, 4–5 days

#### Priority 1: Compass

Compass determines whether users believe the product has differentiated value.

The practice screen should contain:

- session purpose
- question number and restrained progress bar
- timer that does not dominate the page
- one question at a time
- clearly selectable answers
- persistent submit button placement
- immediate answer state
- concise rationale
- a specific error classification
- optional deeper explanation
- clear next-question action
- autosaved progress
- reconnect and retry behaviour

Do not place the full navigation and dashboard chrome around the test. Use a focused session shell.

After the session, show:

1. completion
2. accuracy and pacing
3. the pattern detected
4. what the next session will adjust
5. one primary action

Borrow:

- clear session boundaries
- one dominant task
- instant, explanatory feedback
- targeted repetition
- progressively harder material
- visible mastery dimensions
- a reason for the next recommendation

Avoid:

- hearts or lives
- mascots
- confetti after ordinary actions
- public leagues
- XP as the main progress measure
- exaggerated streak pressure
- dense animations
- “AI magic” language

For adult professionals, progress should be framed as readiness, mastery, consistency and decision confidence.

#### Priority 2: diagnostic and onboarding

Combine the journey into a coherent sequence:

```text
Account
→ target competition
→ professional background
→ diagnostic
→ initial cognitive profile
→ first recommended plan
```

Show progress through the sequence, explain why each input is requested and let users resume.

Avoid a long survey feel. Ask only questions that change the study plan or pilot segmentation.

#### Priority 3: daily plan

The daily plan should answer three questions immediately:

- What should I do today?
- Why this task?
- How long will it take?

Use a primary “Start today’s session” card, followed by secondary tasks and the broader weekly context.

### Phase 3: build confidence and continuity, 3–4 days

#### Priority 4: `/me` dashboard

The dashboard should include:

- next recommended action
- current target competition and date
- recent study activity
- mastery by dimension
- the current cognitive insight
- plan adherence
- progress over time

Limit the dashboard to four or five panels. Pilot users need interpretation rather than a business-intelligence interface.

Every insight should contain:

```text
Observation
Evidence
Practical implication
Recommended action
Confidence or data sufficiency
```

#### Priority 5: study-plan master view

Expose the next one or two weeks in detail and the longer horizon at a summary level. Do not create an elaborate draggable planner.

#### Priority 6: CV or LinkedIn fit analysis

Standardise:

- upload affordance
- file requirements
- upload progress
- analysis state
- error recovery
- provenance statement
- structured results
- caution around recommendations

This page can remain functionally simple as long as it feels deliberate and does not leave the user staring at an indefinite spinner.

### Phase 4: supporting surfaces, 1–3 days

#### Priority 7: authentication

Give login, magic-link confirmation, expired-link and resend states the same visual system.

#### Priority 8: landing page

For a closed, invitation-led pilot, make the landing page credible rather than highly optimised:

- clear EPSO-specific promise
- concise explanation of Compass
- three-step product explanation
- credible screenshots
- pilot call to action
- privacy and data-handling reassurance
- no elaborate marketing animation

#### Priority 9: admin health page

Apply the typography, buttons, tables and status badges. Do not redesign its information architecture unless founders are currently unable to operate the pilot.

## 4. Parallel work split

### Engineering founder

- base templates and static structure
- shared API helper
- Compass state and error handling
- auth preservation
- instrumentation
- deployment checks
- mobile and accessibility fixes

### Product founder

- final page hierarchy
- copy and terminology
- question-feedback structure
- AI trust language
- cognitive-dimension definitions
- sample empty, loading and failure states
- pilot acceptance testing

Both founders should conduct a daily 20-minute product review on a real phone.

## 5. Adaptive quiz UX specification

### Before the session

Show:

- expected duration
- number of questions
- targeted ability
- why the system selected it
- whether the session is timed
- a start button

### During the session

The visual hierarchy should be:

1. question
2. answer choices
3. submit
4. session context

Keep peripheral analytics out of the practice view.

### Feedback

Feedback should distinguish:

- correct answer
- reasoning quality
- error type
- speed
- next adaptation

Use one of four feedback depths:

1. immediate result
2. concise explanation
3. “show full reasoning”
4. related practice suggestion

Do not expose chain-of-thought-style internal model reasoning. Show a user-facing explanation based on evidence and pedagogical rules.

### Session completion

Use:

- “Session complete”
- objective result
- detected pattern
- updated mastery
- next adjustment
- optional review of mistakes

A small positive transition is enough.

## 6. AI-in-the-loop interaction patterns

### Distinguish deterministic and AI states

Use labels such as:

- Uploading document
- Extracting experience
- Comparing with competition requirements
- Preparing your fit summary

### Stream only where it improves comprehension

Use streaming for narrative CV analysis or longer insights, provided the UI handles incomplete streams and errors.

Do not stream short labels, scores or question feedback. Return those as structured, complete objects.

### Show “why am I seeing this?”

Every adaptive recommendation should have a compact explanation.

### Represent uncertainty

Avoid false precision. Prefer categories, sample size and confidence levels.

### Failure modes

For each AI operation, support:

- skeleton or progress state
- slow-state message after a threshold
- retry
- safe fallback
- preservation of submitted data
- ability to continue where possible

### Data provenance

Use three visually distinct labels where relevant:

- **Your data**
- **Concourse analysis**
- **Competition information**

## 7. Component-library assessment

### Plain CSS custom properties

**Recommended now.**

Advantages:

- no build step
- incremental adoption
- direct control over visual identity
- easy for AI coding tools to understand
- no framework lock-in
- tokens can later feed React or another framework

### Tailwind

**Defer.**

It adds a compiler and encourages rewriting every class on every page. It does not automatically create a coherent product.

### shadcn/ui

**Not suitable for the pilot architecture.**

It is strongest inside a React and Tailwind stack. Choosing it means choosing the wider React build decision.

### Radix UI

**Defer until React.**

Strong for accessible behaviour primitives, but it is not a styling system and does not help the current HTML pages without migration.

### Headless UI

**Defer.**

Primarily useful with React or Vue.

### Ark UI and Park UI

**Defer.**

Too much architecture for the current scope.

### DaisyUI

**Not recommended.**

It can create a recognisable template aesthetic unless significantly customised.

### Panda CSS and vanilla-extract

**Not recommended before the pilot.**

Both introduce compiled styling infrastructure.

### Web Components

**Selective future option, not the default.**

Use a custom element only if a genuinely reusable, behaviour-heavy widget must operate independently across pages.

## 8. Accessibility and mobile baseline

These items cannot wait:

- semantic heading order
- native buttons and links
- labels for every input
- visible keyboard focus
- 44 px approximate touch targets
- sufficient text and control contrast
- errors associated with fields
- status changes announced with appropriate live regions
- no colour-only correctness states
- keyboard-answer selection in Compass
- escape-to-close for modals
- motion reduction
- charts accompanied by textual summaries
- desktop and 360–430 px phone testing

Full multilingual support can be deferred, but prepare for it by:

- keeping user-facing strings out of JavaScript logic where practical
- avoiding text embedded in images
- allowing controls to grow
- not fixing button widths
- storing dates and numbers semantically

## 9. Instrumentation required for the pilot

Add a small event taxonomy before inviting users:

```text
auth_link_requested
auth_completed
onboarding_started
onboarding_completed
diagnostic_started
diagnostic_completed
plan_viewed
session_started
question_answered
question_timed_out
explanation_opened
session_abandoned
session_completed
next_session_started
cv_uploaded
cv_analysis_completed
ai_operation_failed
```

For Compass record:

- question tag
- selected answer
- correctness
- response duration
- whether explanation was opened
- session position
- retry or change behaviour
- generated versus curated item
- generation model and prompt version, internally
- fallback use

## 10. Defer explicitly to post-pilot

| Item | Why it is safe to defer |
|---|---|
| Framework migration | Current pages can meet the pilot bar without it; migration risk is higher than the immediate UX benefit. |
| Separate frontend deployment | Creates domains, CORS, environment variables and service coordination without improving pilot learning. |
| Full design-system package | Twelve stable primitives are sufficient. |
| Tailwind or CSS-in-JS | Existing CSS can be consolidated faster than it can be replaced. |
| Dark mode | Does not validate the core product proposition. |
| Theme switching | One strong visual identity is enough. |
| Full i18n pipeline | Implement languages when pilot demand is known. |
| Advanced animation | Subtle CSS feedback clears the credibility threshold. |
| Drag-and-drop study planning | High interaction and mobile complexity with weak pilot value. |
| Real-time collaborative features | Outside the core individual study loop. |
| Highly crafted public marketing site | The initial cohort is closed and can be acquired directly. |
| Complex data visualisations | Users need actionable interpretation, not analytics density. |
| PWA and offline mode | Adds caching and state-sync risk. |
| Native application | Responsive web is sufficient for usage validation. |
| Full automated visual testing | Start with critical-path browser tests and manual visual review. |
| Generic schema-driven form engine | The number of forms is too small to justify abstraction. |
| Web Component design system | Templates and CSS classes are materially simpler for this scale. |

## 11. Risks and anti-patterns

### Do not begin a page-by-page React migration without a boundary

A half-migrated application often ends with:

- duplicated navigation
- two styling systems
- separate form conventions
- inconsistent auth handling
- incompatible event systems
- unclear ownership of routing
- larger page payloads
- founders maintaining both paradigms

When the framework migration begins, give it a strong boundary. Compass is the likely first island.

### Do not mix Alpine, htmx and custom vanilla state on the same feature

Assign a simple rule:

- server templates for structure
- Alpine for small local state
- vanilla modules for Compass and API-heavy workflows
- htmx only for a specifically chosen server-fragment interaction

One feature should have one state owner.

### Do not build a generic component abstraction before the second real use

Create the first implementation, use it again and then extract it.

### Do not redesign all pages simultaneously

Complete one reference page first. Freeze its tokens and component vocabulary, then migrate the rest.

### Do not hide slow AI work behind an indefinite spinner

Show the operation stage, preserve input and provide a retry or fallback.

### Do not let the AI generate uncontrolled HTML

Return structured JSON from AI-backed endpoints wherever possible. Render through controlled templates.

### Do not make generated insights sound diagnostic or certain

Phrase them as evidence-based observations. State the sample size and what the system will do next.

### Do not use the dashboard as the product’s main value demonstration

Compass should demonstrate adaptation during and immediately after practice.

### Do not introduce Next.js solely to obtain React

When a framework becomes justified, Vite plus React or Preact compiled into FastAPI-served assets is the lower-complexity intermediate step.

## Final recommendation

For the closed pilot, Concourse should remain a **single FastAPI application with shared Jinja templates, plain tokenised CSS, native ES modules, selective Alpine.js and Chart.js**.

The work should focus on three outcomes:

1. every page visibly belongs to the same product
2. Compass feels focused, responsive and genuinely adaptive
3. AI recommendations explain their evidence and fail gracefully

This path preserves the existing deployment and authentication model and concentrates the next two to three weeks on user-visible quality. A React or Preact migration should remain a planned option with explicit triggers, rather than a prerequisite for charging the first users.
