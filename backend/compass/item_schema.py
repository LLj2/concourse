"""JSON schema the LLM must match when generating an item.

The schema is enforced via Anthropic's forced-tool-call mechanism (see
backend/ai/client.py::generate_json) — the model literally cannot return
malformed JSON, only valid-but-semantically-wrong content. Semantic checks
(distinct options, valid distractor classes, etc.) happen in validate_item().

v1 supports the `verbal` skill end-to-end. Numerical/abstract are stubbed —
they're image-dependent and out of scope for the text-only generator.

Dimension values come from COGNITIVE_DIMENSIONS.md §2.2 (verbal). They are
hardcoded here so the generator and the schema stay in lockstep — if the
schema doc changes, this file must be edited in tandem (and the new schema
will reject items tagged with old values, surfacing the drift).
"""
from __future__ import annotations

from typing import Any


# =============================================================================
# Canonical distractor classes (COGNITIVE_DIMENSIONS.md §2.7)
# =============================================================================
DISTRACTOR_CLASSES: list[str] = [
    "wrong_base",
    "reversed_ratio",
    "partial_calculation",
    "unit_error",
    "decoy_chase",
    "outside_knowledge",
    "scope_strengthening",
    "scope_weakening",
    "polarity_reversal",
    "near_synonym",
    "partial_rule",
    "near_miss_feature",
    "wrong_role",
    "obsolete_rule",
    "overgeneralised_principle",
    "generic_recommendation",
    "source_summary_only",
]


# =============================================================================
# Per-skill cognitive dimensions (COGNITIVE_DIMENSIONS.md §2.1–§2.5)
#
# Each dimension entry maps name → JSON-schema fragment for that dimension's value.
# These define exactly what the LLM is allowed to declare per dimension.
# =============================================================================

_VERBAL_DIMENSIONS: dict[str, dict[str, Any]] = {
    "inference_depth": {
        "type": "string",
        "enum": ["explicit", "paraphrased", "single_step_inference", "multi_premise_inference"],
        "description": "How far from passage text to verdict.",
    },
    "external_knowledge_lure": {
        "type": "boolean",
        "description": "True if the keyed answer is 'Cannot Say' or False because the statement is true in the world but unsupported by the passage.",
    },
    "quantifier_scope": {
        "type": "string",
        "enum": ["none", "universal", "existential", "frequency", "comparative"],
        "description": "Whether the verdict hinges on a quantifier or modal.",
    },
    "negation_management": {
        "type": "integer",
        "minimum": 0,
        "maximum": 2,
        "description": "Number/interaction of negations to track (0=none, 2=double/interaction).",
    },
    "partial_truth_completeness": {
        "type": "boolean",
        "description": "True if the statement is partly supported but adds/omits/contradicts a detail.",
    },
    "cross_sentence_integration": {
        "type": "integer",
        "minimum": 1,
        "maximum": 3,
        "description": "Number of non-adjacent passage locations to combine (1=single sentence, 3=three+ dispersed).",
    },
    "cannot_say_vs_false_discrimination": {
        "type": "boolean",
        "description": "True if the hard call is specifically Cannot Say vs False.",
    },
    "referent_tracking": {
        "type": "integer",
        "minimum": 0,
        "maximum": 3,
        "description": "Number of entities/pronouns tracked across sentences.",
    },
    "conditional_logic": {
        "type": "string",
        "enum": ["none", "sufficient", "necessary", "biconditional", "exception"],
        "description": "Logical relation in the passage (if/only if/unless).",
    },
}


# =============================================================================
# Schema builder
# =============================================================================

def build_schema(skill_id: str) -> dict[str, Any]:
    """Return the JSON schema for a generated item of `skill_id`.

    Raises ValueError if the skill is not yet supported by the generator.
    """
    if skill_id != "verbal":
        raise ValueError(
            f"generator does not yet support skill_id={skill_id!r} — "
            f"v1 is text-only verbal; numerical/abstract require image generation."
        )

    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["prompt", "options", "correct_index", "explanation", "topic_tag", "dimensions", "option_diagnostics"],
        "properties": {
            "prompt": {
                "type": "string",
                "minLength": 200,
                "maxLength": 1500,
                "description": "Self-contained passage followed by the question. Must be answerable from the passage alone.",
            },
            "options": {
                "type": "array",
                "minItems": 4,
                "maxItems": 4,
                "items": {
                    "type": "string",
                    "minLength": 5,
                    "maxLength": 300,
                    "description": "Option text WITH the A./B./C./D. prefix.",
                },
                "description": "Exactly four answer options. Must be distinct. Format: 'A. ...', 'B. ...', 'C. ...', 'D. ...'.",
            },
            "correct_index": {
                "type": "integer",
                "minimum": 0,
                "maximum": 3,
                "description": "Zero-based index of the correct option (0=A, 1=B, 2=C, 3=D).",
            },
            "explanation": {
                "type": "string",
                "minLength": 80,
                "maxLength": 800,
                "description": "Why the correct answer is correct AND why each distractor is wrong, citing the passage.",
            },
            "topic_tag": {
                "type": "string",
                "minLength": 2,
                "maxLength": 40,
                "description": "Short topic identifier (1-3 words, snake_case if multi-word). E.g. 'etias', 'council_voting', 'ai_act'.",
            },
            "dimensions": {
                "type": "object",
                "additionalProperties": False,
                "required": list(_VERBAL_DIMENSIONS.keys()),
                "properties": _VERBAL_DIMENSIONS,
                "description": "Cognitive-dimension tags declared at generation time. ALL nine keys required.",
            },
            "option_diagnostics": {
                "type": "array",
                "minItems": 3,
                "maxItems": 3,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["index", "distractor_classes"],
                    "properties": {
                        "index": {
                            "type": "integer",
                            "minimum": 0,
                            "maximum": 3,
                            "description": "Index of the WRONG option (must not equal correct_index).",
                        },
                        "distractor_classes": {
                            "type": "array",
                            "minItems": 1,
                            "maxItems": 3,
                            "items": {"type": "string", "enum": DISTRACTOR_CLASSES},
                            "description": "Why this wrong option attracts a wrong reader. 1-3 tags from the canonical 17.",
                        },
                    },
                },
                "description": "Exactly 3 entries — one per wrong option. Together with correct_index, must cover indexes 0,1,2,3 exactly.",
            },
        },
    }


# =============================================================================
# Semantic validation (post-LLM, beyond what JSON schema can express)
# =============================================================================

def validate_item(item: dict, skill_id: str) -> tuple[bool, list[str]]:
    """Return (is_valid, list_of_problems).

    JSON schema already enforces structure (4 options, correct_index 0-3, etc).
    Here we check rules JSON schema can't:
      - options are distinct
      - option_diagnostics indexes cover the three wrong options exactly
      - option_diagnostics indexes don't include correct_index
      - options use the 'A./B./C./D.' prefix convention
    """
    problems: list[str] = []

    options = item.get("options") or []
    correct_index = item.get("correct_index")

    # Distinct options
    if len(set(o.strip() for o in options)) != 4:
        problems.append("options are not 4 distinct strings")

    # A./B./C./D. prefix convention
    expected_prefixes = ["A.", "B.", "C.", "D."]
    for i, opt in enumerate(options):
        if not opt.lstrip().startswith(expected_prefixes[i]):
            problems.append(f"option {i} does not start with '{expected_prefixes[i]}'")

    # Diagnostics cover the three wrong options exactly
    diags = item.get("option_diagnostics") or []
    diag_idx = [d.get("index") for d in diags]
    if len(set(diag_idx)) != 3:
        problems.append("option_diagnostics indexes not distinct or wrong count")
    if correct_index in diag_idx:
        problems.append(f"option_diagnostics include correct_index {correct_index}")
    expected_wrong = {0, 1, 2, 3} - {correct_index}
    if set(diag_idx) != expected_wrong:
        problems.append(
            f"option_diagnostics indexes {sorted(diag_idx)} do not match wrong options {sorted(expected_wrong)}"
        )

    return (len(problems) == 0, problems)
