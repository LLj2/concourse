# Concourse — Cognitive Dimensions Schema (Merged v1)

> Synthesized from two independent deep-research runs (Claude Research + ChatGPT Deep Research), executed 2026-06-22.
> Source files: `concourse-cognitive-dimensions-output.md` (Claude), `epso_cast_cognitive_dimensions_deep_research.md` (ChatGPT).
> Purpose: this is the v1 schema we encode in the `items` table. Each dimension becomes a column or a JSONB key; each item generated or seeded carries its values.

---

## 0. How the two reports compared

Both reports converged on far more than they diverged. They agree on:

- **The shape of the answer**: 6-12 cognitive dimensions per skill, generatable at LLM time, separate from topic.
- **SJT out of v1**: not in any in-scope 2024+ competition, methodologically wrong for stem-tagging.
- **FRMCQ as ranking bottleneck for EPSO specialist** (AD7 ICT); not present in AD5 generalist or CAST.
- **Written test (EUFTE / WT / FRWT)** as a distinct skill with five official EPSO anchors.
- **Test structures** verified against EPSO/AD/427/26 (AD5), EPSO/AD/429/26 (AD7 ICT), and CAST Permanent.
- **Numerical reasoning** failure modes converge on: data selection, base/referent choice, multi-step, unit/scale, ratio inversion, lure proximity, estimation.
- **Verbal reasoning** failure modes converge on: inference depth, quantifier scope, negation, cross-sentence integration, external-knowledge leakage, true/false/cannot-say discrimination.
- **Abstract reasoning** failure modes converge on: rule count, rule interaction, transformation type, spatial manipulation, distractor overlap.

They disagree on:

1. **Granularity of categoricals.** ChatGPT preferred multi-label/categorical types (e.g. `rule_operator` with 10 values). Claude preferred booleans + a smaller categorical (e.g. `transformation_type` with 7 values + a separate `spatial_manipulation_required` boolean). **Merge rule:** keep ChatGPT's richer categoricals where they preserve information that booleans would compress, but cap label counts at ~6-8 to keep the generator's job tractable.
2. **Whether to model distractors separately.** ChatGPT introduced a `distractor_diagnostic_class` cross-skill multilabel ("wrong_base", "reversed_ratio", etc.); Claude folded this into per-skill option-level dimensions like `answer_lure_proximity`. **Merge rule:** keep both layers — Claude's item-level lure intensity AND ChatGPT's per-option misconception class. They serve different jobs (intensity is for difficulty calibration; class is for why-level diagnosis).
3. **Cross-skill / meta dimensions.** Claude proposed `inhibitory_control_demand` and `working_memory_load` as item-aggregated tags; ChatGPT proposed `working_memory_elements`, `operation_switch_count`, `time_strategy_profile`. **Merge rule:** keep one working-memory load tag, one inhibition tag, one time-strategy person-level tag (not an item tag).
4. **Written test scope.** Claude included `source_verbatim_anchoring` as a binary stem feature; ChatGPT flagged that mandatory verbatim quotation is not an official EPSO rule and softened it to `source_claim_anchoring` (ordinal). **Merge rule:** use the ordinal version. Verbatim anchoring is practitioner testimony from Stefano, not EPSO doctrine.
5. **`representation_extraction` vs `data_locate_load`** — same construct, different names. **Merge rule:** use Claude's `data_locate_load` (more precise; "load" implies volume).

The merged schema below resolves each disagreement explicitly.

---

## 1. Verified competition structures (for the engine to scope by)

Both reports verified the same facts. The engine must scope items and remediation priority by these:

| Competition | Reference | Reasoning role | FRMCQ | EUFTE | SJT |
|---|---|---|---|---|---|
| EPSO generalist (AD5) | EPSO/AD/427/26 (5 Feb 2026, 1,490 places, 174k+ applicants) | Verbal = 35% of ranking; numerical + abstract = gate only (combined 10/20) | No | Yes (15% of final ranking) | No |
| EPSO specialist (AD7 ICT) | EPSO/AD/429/26 (6 May 2026, 782 places, 4 fields) | All three pass/fail; not ranked | **Yes, ranking-determining** (30 Q / 40 min, pass 15/30) | Pass/fail (40 min, pass 5/10) | No |
| CAST Permanent | Rolling; no NOC | All three reasoning tests are the entire selection | No | No | No |

**Material implication for the engine:** the same dimension (e.g. `base_referent_selection`) is tagged identically across families, but remediation *priority* is family-scoped. AD5 candidates with secure numerical gates should be routed to verbal+EUFTE practice; AD7 ICT candidates should be routed to FRMCQ practice once reasoning gates are secure; CAST candidates max out on all three reasoning tests because that is the entire game.

---

## 2. Merged dimension schema

### 2.1 Numerical reasoning (9 dimensions)

| name | type | definition | failure signal | applies_to |
|---|---|---|---|---|
| `data_locate_load` | ord1-3 | Number of distinct data points to locate from the stimulus before computing | Right method, wrong inputs (mis-read cell/period/unit) | all |
| `operation_steps` | ord1-3 | Count of chained dependent arithmetic operations | Stops after step 1; loses intermediate value | all |
| `base_referent_selection` | bool | Item requires identifying the correct base/denominator for % or ratio | Divides by wrong base; reverse-percentage error | all |
| `unit_scale_reconciliation` | bool | Must reconcile differing units or scales (thousands vs millions, %, per-capita) | Order-of-magnitude error; mixed-unit arithmetic | all |
| `relational_inversion` | bool | Must invert a relationship — work backward, take reciprocal, reverse direction | Applies forward op when inverse needed | all |
| `percentage_point_vs_percent` | bool | Answer hinges on distinguishing pp change vs % change | Conflates the two | all |
| `compound_change` | cat: `none / sequential_pct / growth_over_periods / weighted_recomposition` | Successive changes must be applied multiplicatively, not added | Adds percentages; ignores base shift | all |
| `weighted_aggregation` | bool | Subgroup values must be combined using unequal weights | Takes simple mean of unequal-size groups | all |
| `estimation_sufficient` | cat: `exact_required / bounded_estimate_sufficient / order_of_magnitude` | Precision level needed to distinguish answer options | Over-computes when approximation would suffice | all |

**Resolved disagreements:**
- Used Claude's `data_locate_load` name (clearer "load" framing) for ChatGPT's `representation_extraction`.
- Used ChatGPT's `compound_change` categorical (more informative than a boolean "multi-step %").
- Used ChatGPT's `weighted_aggregation` boolean.
- Used ChatGPT's `estimation_sufficient` categorical (richer than a boolean; tells the generator how to space options).
- Dropped Claude's `irrelevant_data_present` as a separate dimension — folded into `data_locate_load` since both reports agreed they correlate strongly, and the generator can express "decoys present" by ramping `data_locate_load` past the actually-needed data points.
- Dropped Claude's stem-level `answer_lure_proximity` ordinal — moved this concept to the distractor-class layer (section 2.7) where each distractor carries its own misconception tag, which is more diagnostic.

### 2.2 Verbal reasoning (9 dimensions)

| name | type | definition | failure signal | applies_to |
|---|---|---|---|---|
| `inference_depth` | cat: `explicit / paraphrased / single_step_inference / multi_premise_inference` | Inferential distance from passage to verdict | Defaults to "Cannot Say" or guesses on multi-premise items | all |
| `external_knowledge_lure` | bool | Keyed answer is "Cannot Say" or False because the statement is true in the world but unsupported by passage | Marks True from world knowledge | all |
| `quantifier_scope` | cat: `none / universal / existential / frequency / comparative` | Adjudication hinges on a quantifier or modal (all/some/only/may/most) | Over- or under-generalises | all |
| `negation_management` | ord0-2 | Number/interaction of negations (explicit, implicit, double) to track | Misreads polarity | all |
| `partial_truth_completeness` | bool | Statement is partly supported but adds/omits/contradicts a detail | Accepts on partial support | all |
| `cross_sentence_integration` | ord1-3 | Number of separate, non-adjacent passage locations to combine | Answers from one locally-matching sentence | all |
| `cannot_say_vs_false_discrimination` | bool | Hard call is specifically between Cannot Say and False | Systematic bias one direction | all |
| `referent_tracking` | ord0-3 | Number of entities / pronouns whose identity must be tracked across sentences | Assigns claim to wrong actor | all |
| `conditional_logic` | cat: `none / sufficient / necessary / biconditional / exception` | Logical relation encoded by if / only if / unless | Affirms consequent; confuses necessary vs sufficient | all |

**Resolved disagreements:**
- Used ChatGPT's `support_strength_required` *renamed to* `inference_depth` (Claude's name) but kept ChatGPT's 4-way categorical (richer than ord1-3).
- Used ChatGPT's `referent_tracking` and `conditional_logic` — Claude didn't have these and they are clearly distinct constructs both reports' literature supports.
- Used Claude's `external_knowledge_lure` and `partial_truth_completeness` — ChatGPT's coverage of these was thinner.
- Kept ChatGPT's `quantifier_scope` 5-way categorical (more diagnostic than Claude's boolean).
- Dropped Claude's `lexical_paraphrase_distance` — folded into `inference_depth` since "paraphrased" is one of its values.
- Dropped ChatGPT's `temporal_order_inference` for v1 — kept in v2 candidates; the construct is real but rarely the *binding* failure mode in EPSO verbal items.
- Dropped ChatGPT's `causal_vs_correlational_control` for v1 — same reason; promising but the item base will not be dense enough to score reliably in v1.

### 2.3 Abstract reasoning (9 dimensions)

| name | type | definition | failure signal | applies_to |
|---|---|---|---|---|
| `rule_count` | ord1-3plus | Number of simultaneous independent transformation rules | Finds one rule, violates another | all |
| `rule_operator` | multilabel cat: `progression / alternation / rotation / reflection / addition / subtraction / xor / intersection / distribution / quantity_change / size_change / shading_change` | Transformation operator(s) applied | Detects change but assigns wrong operator | all |
| `attribute_channels` | multilabel cat: `shape / count / position / orientation / size / fill / line_style / containment` | Visual feature channels participating in the rule | Misses non-salient feature | all |
| `rule_axis` | cat: `row / column / both / diagonal / sequence` | Spatial direction along which the rule holds | Finds pattern that works on one axis only | all |
| `rule_interaction` | bool | Rules are conditional/configural — one depends on another's state | Treats interacting rules as independent | all |
| `periodicity_phase` | bool | A rule operates on a cycle > 1 frame | Off-by-one in cycle | all |
| `spatial_manipulation_required` | bool | Requires mental rotation/reflection of a figure | Errs on rotation/mirror items specifically | all |
| `distractor_rule_overlap` | ord0-3 | Number of sub-rules satisfied by the strongest incorrect option | Picks option matching first-found rule, violating a second | all |
| `negative_space_dependency` | bool | Empty locations / absent elements carry rule-relevant info | Ignores absence as a state | all |

**Resolved disagreements:**
- Merged Claude's `transformation_type` categorical and ChatGPT's `rule_operator` multilabel. Kept ChatGPT's multilabel form because real items often combine 2-3 operators on different attributes. Truncated the list to 12 values (broader sources had more; we cap to keep the generator tractable).
- Kept `spatial_manipulation_required` as a separate boolean — both reports agreed it isolates a discrete spatial-ability weakness that does not fall out of `rule_operator`.
- Kept ChatGPT's `attribute_channels` multilabel — important for routing remediation to specific perceptual channels.
- Kept ChatGPT's `rule_axis` and `negative_space_dependency` — Claude didn't have these but they are real constructs in matrix-reasoning literature.
- Dropped Claude's `abstract_property_rule` boolean for v1 — folded into `attribute_channels` where "count of intersections" is one channel value. The construct is real but the boolean was hard to define cleanly.
- Dropped Claude's `answer_near_miss` ordinal — moved to the distractor-class layer (section 2.7).
- Dropped ChatGPT's `object_correspondence` for v1 — interesting but only meaningful for matrix-style items, not sequence-style which dominate EPSO. Held in v2 candidates.
- Dropped ChatGPT's `transformation_composition` — overlaps too much with `rule_count` and `rule_interaction`. Held in v2.

### 2.4 FRMCQ — EPSO specialist only (8 dimensions)

These apply to EPSO/AD/429/26-class items only. Items must carry both a `content_domain` (e.g. `GDPR`, `AI_Act`) and these cognitive tags.

| name | type | definition | failure signal | applies_to |
|---|---|---|---|---|
| `authority_level_required` | cat: `principle / defined_term / specific_rule / article_level / technical_standard` | Precision of authoritative knowledge required | Knows concept; cannot pin specific provision | EPSO_specialist |
| `concept_application` | ord0-3 | Distance between recalled principle and the novel scenario it must be applied to | Recognises definition; misclassifies real case | EPSO_specialist |
| `multi_source_integration` | ord1-3plus | Number of instruments/standards whose interaction determines the answer | Knows each in isolation; misses interaction/hierarchy | EPSO_specialist |
| `exception_boundary` | cat: `none / scope_exclusion / derogation / threshold / role_specific / risk_class` | Correctness turns on an exception, threshold, or carve-out | Applies general rule blindly | EPSO_specialist |
| `option_discrimination_depth` | ord1-3 | Semantic closeness of the two most plausible options | Keyword-based choice; near-synonym error | EPSO_specialist |
| `version_sensitivity` | cat: `stable / recent_amendment / transition_period / superseded_framework` | Whether the answer changes across legislative versions | Cites superseded instrument | EPSO_specialist |
| `operational_role_mapping` | cat: `none / institution / governance_role / technical_role / decision_right` | Item requires assigning a duty or authority to the correct actor | Mis-assigns responsibility | EPSO_specialist |
| `quantitative_threshold_recall` | bool | Answer depends on a specific numeric threshold / deadline / penalty | Recalls qualitatively; misses exact figure | EPSO_specialist |

**Resolved disagreements:**
- Used ChatGPT's richer categoricals throughout (better for routing remediation than Claude's booleans).
- Used ChatGPT's `concept_application` ordinal (0-3) instead of Claude's boolean — more diagnostic.
- Kept Claude's `quantitative_threshold_recall` boolean separately — both reports treated this; it is a distinct sub-skill (number memorisation) from authority-level recall.
- Folded Claude's `procedural_sequence_roles` into ChatGPT's `operational_role_mapping`; they overlap.
- Folded Claude's `definitional_boundary` into ChatGPT's `exception_boundary`; they are the same construct.
- Note: ChatGPT's `evidence_to_action` ord0-3 (incident-to-control inference) is included as a v2 candidate — high-value but harder to generate at scale until the engine has worked examples.

### 2.5 Written test — EUFTE / WT / FRWT (9 dimensions)

Anchored to the five verified EPSO marking criteria: logical flow / conciseness / clarity / audience-and-purpose adaptation / use of information provided.

| name | type | definition | failure signal | applies_to |
|---|---|---|---|---|
| `output_type_recognition` | cat: `briefing_note / executive_summary / public_communication / analysis_note / advisory_note / generic_essay` | Correctly identify the demanded output genre | Writes generic essay when briefing required | all (specialist-weighted) |
| `prompt_task_alignment` | ord1-3 | Whether every requested deliverable is explicitly answered | Omits a sub-requirement | all |
| `synthesis_transformation` | cat: `summary / selection / integration / evaluation / recommendation` | Highest transformation applied to source material | Summarises instead of answering | all |
| `source_claim_anchoring` | ord0-3 | Degree to which claims are traceable to supplied source material | Plausible assertions, no evidence trail | EPSO_generalist + EPSO_specialist (WT/FRWT) |
| `audience_register_calibration` | cat: `senior_internal / technical_peer / general_internal / public / political` | Fit of tone/terminology to specified reader | Wrong register for audience | all |
| `macro_logical_flow` | ord1-3 | Document-level progression from purpose through evidence to action | Coherent sentences, incoherent whole | all |
| `information_priority` | ord1-3 | High-value info appears in the right position and at right length | Background crowds out the analysis | all |
| `compression_efficiency` | ord1-3 | Task-relevant meaning per sentence | Verbose, runs out of time | all |
| `field_knowledge_integration` | bool | Correct domain knowledge is integrated into the writing | Thin/inaccurate substance (FRWT-only failure) | EPSO_specialist (FRWT) |

**Resolved disagreements:**
- Used ChatGPT's `source_claim_anchoring` ordinal (0-3) instead of Claude's `source_verbatim_anchoring` boolean. ChatGPT correctly flagged that mandatory verbatim quotation is practitioner testimony from Stefano, not an EPSO rule.
- Kept Claude's `output_type_recognition` and the scaffold templates concept — ChatGPT had a similar `output_schema_retrieval` but Claude's framing was sharper.
- Used ChatGPT's `synthesis_transformation` categorical (5 values) instead of Claude's `synthesis_vs_summary` ordinal — the categorical preserves the action-type information.
- Dropped Claude's `scaffold_retrieval` boolean — folded into `output_type_recognition` since having a scaffold IS recognising the type. Scaffolds belong in the remediation library, not the item schema.
- Dropped Claude's `prompt_constraint_compliance` — covered by ChatGPT's `prompt_task_alignment`.
- Kept Claude's `field_knowledge_integration` boolean for FRWT — both reports flagged FRWT as the only variant carrying field-knowledge marking.

### 2.6 Situational Judgement — omitted from v1

Both reports agreed independently:

1. SJT is not in any in-scope 2024+ competition family (AD5, AD7 specialist, CAST).
2. SJT items fail the stem-tagability test — correctness depends on a normatively-keyed effectiveness ranking, not derivable from the question text.

**Build SJT support only when:** an AST or AST-SC product line with a confirmed 2024+ NOC enters scope. The defensible axes would then be response-tendency constructs (`escalation_bias`, `rule_vs_initiative_orientation`, `interpersonal_vs_task_priority`), validated against the official scoring key.

### 2.7 Distractor-level misconception tags (cross-skill)

This is **ChatGPT's contribution that Claude under-weighted**, and it is the bridge between item metadata and why-level diagnosis. Each option (not just the correct one) carries one or more misconception class tags. When a user picks a wrong option, the engine learns *which misconception* they hold.

Each item stores per-option distractor classes from this multilabel pool:

`wrong_base, reversed_ratio, partial_rule, outside_knowledge, scope_strengthening, scope_weakening, obsolete_rule, wrong_role, partial_calculation, generic_recommendation, source_summary_only, near_synonym, near_miss_feature, overgeneralised_principle, polarity_reversal, unit_error, decoy_chase`

**Why this matters:** without distractor-level tags, a user's wrong answer tells you only "got it wrong." With them, a user picking option B that carries `wrong_base` tells you exactly which procedural error they made. After 10 such picks across different items, the engine can say "you have a base-selection problem, regardless of topic." This is the moat.

### 2.8 Meta dimensions (cross-skill aggregates)

Three person-level signals, two of which derive from item dimensions (computable at item-tag time) and one which is purely response-data:

| name | type | definition | level |
|---|---|---|---|
| `working_memory_load` | ord1-4 | Aggregate of `operation_steps + data_locate_load + rule_count + cross_sentence_integration` | item (derived) |
| `inhibitory_control_demand` | ord0-2 | Aggregate presence of decoy / lure / external-knowledge structures | item (derived) |
| `time_strategy_profile` | cat: `premature / balanced / overinvesting / timeout_prone` | Candidate's latency pattern relative to accuracy | person (not an item tag) |

The first two are computed at item-tag time from the per-skill dimensions; they are not independently set by the generator. The third is computed from response telemetry only and feeds the strategy-coaching remediation track, not item generation.

---

## 3. The consolidated schema in one table

This is the spec for the migration. All entries with `applies_to = all` mean the dimension is generated and tagged on every item across families; the engine prioritises remediation differently per family using §1.

| skill | dimension | type | applies_to |
|---|---|---|---|
| numerical | data_locate_load | ord1-3 | all |
| numerical | operation_steps | ord1-3 | all |
| numerical | base_referent_selection | bool | all |
| numerical | unit_scale_reconciliation | bool | all |
| numerical | relational_inversion | bool | all |
| numerical | percentage_point_vs_percent | bool | all |
| numerical | compound_change | cat(4) | all |
| numerical | weighted_aggregation | bool | all |
| numerical | estimation_sufficient | cat(3) | all |
| verbal | inference_depth | cat(4) | all |
| verbal | external_knowledge_lure | bool | all |
| verbal | quantifier_scope | cat(5) | all |
| verbal | negation_management | ord0-2 | all |
| verbal | partial_truth_completeness | bool | all |
| verbal | cross_sentence_integration | ord1-3 | all |
| verbal | cannot_say_vs_false_discrimination | bool | all |
| verbal | referent_tracking | ord0-3 | all |
| verbal | conditional_logic | cat(5) | all |
| abstract | rule_count | ord1-3+ | all |
| abstract | rule_operator | multilabel(12) | all |
| abstract | attribute_channels | multilabel(8) | all |
| abstract | rule_axis | cat(5) | all |
| abstract | rule_interaction | bool | all |
| abstract | periodicity_phase | bool | all |
| abstract | spatial_manipulation_required | bool | all |
| abstract | distractor_rule_overlap | ord0-3 | all |
| abstract | negative_space_dependency | bool | all |
| frmcq | authority_level_required | cat(5) | EPSO_specialist |
| frmcq | concept_application | ord0-3 | EPSO_specialist |
| frmcq | multi_source_integration | ord1-3+ | EPSO_specialist |
| frmcq | exception_boundary | cat(6) | EPSO_specialist |
| frmcq | option_discrimination_depth | ord1-3 | EPSO_specialist |
| frmcq | version_sensitivity | cat(4) | EPSO_specialist |
| frmcq | operational_role_mapping | cat(5) | EPSO_specialist |
| frmcq | quantitative_threshold_recall | bool | EPSO_specialist |
| written | output_type_recognition | cat(6) | all (spec-weighted) |
| written | prompt_task_alignment | ord1-3 | all |
| written | synthesis_transformation | cat(5) | all |
| written | source_claim_anchoring | ord0-3 | EPSO_generalist + EPSO_specialist |
| written | audience_register_calibration | cat(5) | all |
| written | macro_logical_flow | ord1-3 | all |
| written | information_priority | ord1-3 | all |
| written | compression_efficiency | ord1-3 | all |
| written | field_knowledge_integration | bool | EPSO_specialist (FRWT only) |
| option-level | distractor_diagnostic_class | multilabel(~17) | all |
| meta | working_memory_load | ord1-4 (derived) | all |
| meta | inhibitory_control_demand | ord0-2 (derived) | all |
| meta | time_strategy_profile | cat(4) (person-level, not item) | all |

**Counts (within the 6-12 band):**
- Numerical: 9
- Verbal: 9
- Abstract: 9
- FRMCQ: 8
- Written: 9 (8 universal + 1 FRWT-only)
- Distractor-class: 1 multilabel (~17 values)
- Meta: 3 (2 derived + 1 person-level)

Total dimensions tagged per generated item: ~9-18 depending on skill (8 cognitive + per-option distractor tags + 2 derived meta).

---

## 4. Item storage format

Each item in the `items` table should carry this JSON shape in a `dimensions` JSONB column (in addition to the existing `skill_id`, `difficulty`, `prompt`, `options`, `correct_index`, `explanation`):

```json
{
  "competition_family": "EPSO_specialist",
  "competition_reference": "EPSO/AD/429/26",
  "skill": "frmcq",
  "content_domain": ["data_governance", "GDPR"],
  "dimensions": {
    "authority_level_required": "specific_rule",
    "concept_application": 2,
    "multi_source_integration": 2,
    "exception_boundary": "role_specific",
    "option_discrimination_depth": 3,
    "version_sensitivity": "stable",
    "operational_role_mapping": "governance_role",
    "quantitative_threshold_recall": false
  },
  "option_diagnostics": [
    {"index": 0, "is_correct": true},
    {"index": 1, "distractor_classes": ["wrong_role"]},
    {"index": 2, "distractor_classes": ["obsolete_rule"]},
    {"index": 3, "distractor_classes": ["overgeneralised_principle"]}
  ],
  "derived": {
    "working_memory_load": 2,
    "inhibitory_control_demand": 1
  },
  "source_date": "2026-06-22",
  "source_authority": "authored"
}
```

The migration adds:
- `items.competition_family` text (nullable; defaults `all` for current verbal items)
- `items.content_domain` text[] (nullable)
- `items.dimensions` jsonb (the per-skill dimension dict above)
- `items.option_diagnostics` jsonb (per-option misconception tags)
- `items.derived` jsonb (the computed meta tags)

Existing 8 verbal items get back-filled with empty `dimensions` JSONB; the engine treats null as "not yet calibrated" and de-prioritises them once newer dimensioned items exist.

---

## 5. What this changes in the codebase

Three changes from the architecture I described in earlier turns:

1. **`backend/ai/generate_item.py`** receives a target *dimension dict*, not just `(skill_id, difficulty)`. The prompt becomes "generate a numerical item that is positive on `relational_inversion=true` and `unit_scale_reconciliation=true`, with `option_discrimination_depth=2`." Schema enforces the LLM declares dimensions in its output.

2. **`backend/logic/diagnostic.py::pick_practice_item`** runs a 3-step query:
   - Read the user's latest `pattern_analyses` LLM blob → focus dimensions
   - Build a target distribution: 60% focus dimensions, 30% other weak dimensions, 10% control (strong areas)
   - For each slot, query bank → fall back to generator with that slot's dimension target

3. **New `dimension_mastery` table** aggregates user × dimension × accuracy. Refreshed on every answer. The `pattern_analyses` LLM runs over this table every ~50 answers (or on session end) and writes the focus dimensions back.

The earlier plan's 4 commits become 5:
- Commit 1: schema migration (the dimensions added to `items`; new `dimension_mastery` and `pattern_analyses` tables).
- Commit 2: generation pipeline accepting target dimensions.
- Commit 3: bank-first picker driven by `pattern_analyses`.
- Commit 4: practice sessions API + UI.
- Commit 5: pattern-analysis worker + dimension-aware feedback rendering ("you struggle on items with two chained operations").

---

## 6. Open questions to settle before coding (decisions, ~30 min with Stefano)

These are the points where both reports flagged uncertainty or where the team has to make a product call:

1. **Distractor diagnostic class list.** The ~17 values in §2.7 are a starting set. Stefano should mark each as ✅ / ❓ / ❌ from his EPSO experience. The ❌s come out.
2. **EPSO/AD/427/26 EUFTE: source-material rule.** Was the AD5 EUFTE accompanied by pre-released background material? If yes, `source_claim_anchoring` applies; if no, it does not. Affects how the engine generates EUFTE practice.
3. **Stefano's ground-truth competition** (Data Management vs ICT Data Science vs Data LUX). Affects the FRMCQ reading-list emphasis but not the dimension schema.
4. **Verbatim-anchoring rule** (Stefano's testimony). Both reports flagged it is practitioner observation, not EPSO doctrine. Decide: encode as a soft prep tip (✓), or as a hard tagged dimension (✗)? Recommendation: tip, not dimension.
5. **Two-rater calibration plan.** Before generating items at scale, take 30 manually-authored items, tag them blind with both Stefano + one of us, measure inter-rater agreement per dimension. Dimensions with κ < 0.6 get rewritten or dropped before launch.

---

## 7. What we held in v2 (out of v1)

- Numerical: `irrelevant_data_present` (folded), `answer_lure_proximity` (moved to distractor layer).
- Verbal: `lexical_paraphrase_distance` (folded), `temporal_order_inference`, `causal_vs_correlational_control`.
- Abstract: `abstract_property_rule` (folded), `answer_near_miss` (moved to distractor layer), `object_correspondence`, `transformation_composition`.
- FRMCQ: `procedural_sequence_roles` (folded), `definitional_boundary` (folded), `evidence_to_action`.
- Written: `scaffold_retrieval` (folded), `prompt_constraint_compliance` (folded).
- Cross: `confidence_calibration`, `linguistic_translation_load`, `calculation_path_equivalence`, `visual_search_entropy`.
- SJT entirely.

Each is a genuine construct; each is held because it would either inflate the schema past tractable, duplicate a dimension already present, or require data we will not have until v2.

---

## 8. Confidence summary

| Item | Confidence |
|---|---|
| The dimension schema captures the major failure modes | High (two independent runs converged) |
| The dimensions are LLM-tagable at generation | High |
| Counts per skill (6-12) are appropriate | High |
| Distractor-class layer is the right WHY-level signal | Medium-High (one report's contribution, but methodologically sound) |
| Inter-rater agreement on dimension tagging will be acceptable | Unknown — needs the calibration test in §6.5 |
| FRMCQ dimensions are sufficient for legal/regulatory items | Medium — needs Stefano review of one tagged example |
| Verbatim-anchoring should not be a hard dimension | High (both reports flagged this) |
| SJT exclusion from v1 | High |

---

## 9. Sources

This file synthesizes content from two independent deep-research executions. Both source files cite their references in full; representative anchors:

**Verified 2024+ official sources:**
- EU Careers — Main structure of the new model, written-test FAQ, AD5/AD7 application pages, CAST Permanent
- EUR-Lex — Notice EPSO/AD/427/26 (C/2026/00711), EPSO/AD/429/26 (C/2026/02425)

**Cognitive-science anchors:**
- Kintsch (construction–integration); Bereiter & Scardamalia (knowledge-telling vs knowledge-transforming); Halford et al. (relational complexity); Shepard & Metzler (mental rotation); Cowan (working memory); Boyer et al. (proportional reasoning).

**Prep-platform / secondary:**
- EU Training, EPSO HQ, EPSOGenius, PrepAri, PassEPSO, Prep4EU, EPSOprep, ArcoEuropa, Open Exam Prep.

---

**End of merged schema.** Ready to be encoded as migration `003_dimensions.sql` once §6 questions are settled with Stefano.
