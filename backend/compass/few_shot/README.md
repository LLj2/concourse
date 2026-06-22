# Few-shot anchors for Compass item generation

> Real EPSO sample items used as prompt anchors for the Compass item-generation pipeline (commit 2 of the Compass build).
>
> Lives inside the sealed `backend/compass/` package — see `backend/compass/README.md` for the isolation contract.

## What's here

| File | Content | Used by |
|---|---|---|
| `verbal_epso_anchors.json` | 10 real EPSO verbal-reasoning items (passage + 4 options + correct index + source URL), extracted from EPSO's official AST sample tests | Verbal generator prompt in `backend/compass/prompts/verbal.py` (commit 2) |

## Where they came from

Source: the `epso_benchmark_data` folder downloaded 2026-06-22 from EPSO's public sample-test pages (`https://eu-careers.europa.eu/node/<category_id>`). The original folder contained 25 items total — 10 verbal, 5 numerical, 10 abstract — plus the H5P content IDs and image manifests.

The benchmark folder also includes numerical (5) and abstract (10) items, but **those aren't reproduced here**:

- **Numerical** items load their data from an embedded chart/table image; the question text alone says only "How much greater is the total GDP of the eurozone than that of Japan?" without the chart. A text-only generator can't replicate that format. Compass v1 is text-only — numerical generation is post-v1 once we add image generation or text-table item authoring.
- **Abstract** items ARE images (pattern continuation series). Out of scope for v1.

The full raw download stays in `~/Library/CloudStorage/OneDrive-amazon.com/Downloads - Jan26/epso_benchmark_data/` if we need to look at the originals (images included).

## How the verbal generator uses these

Commit 2 of Compass will build `generate_item(skill_id, difficulty, target_dimensions, ...)`. For `skill_id="verbal"`, the prompt builder pulls 3-5 of these items (rotated per call to avoid the LLM over-fitting to one style) and includes them in the system prompt as anchors:

> Here are real EPSO verbal reasoning items. Your generated item must follow this exact format (passage, four options labeled A/B/C/D, one correct, common EPSO traps in the wrong options).
>
> Example 1: [item from this file]
> Example 2: [item from this file]
> ...
>
> Now generate one new item with these target dimensions: `{...}`

The LLM declares dimension values in its JSON output (per the schema in `COGNITIVE_DIMENSIONS.md`), and the rest of the generation pipeline validates and inserts.

## Licence note

EPSO sample tests are official, publicly accessible preparation material. We use them as **prompt anchors for generation** — not as a question bank served to users. Generated items are new content modeled after the style; we do not ship the source items themselves.

## Quality

These are the highest-quality verbal-reasoning anchors we can get for prompt engineering — they're literally the same format the real exam uses, written by the same authors. If Haiku 4.5 can produce items that match this style and pass Stefano's sniff test, we're done with the verbal generator.
