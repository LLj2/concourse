"""Verbal-reasoning item-generation prompt.

The prompt teaches Haiku 4.5 to produce items in the style of EPSO's official
AST verbal-reasoning samples. Three pieces:

1. SYSTEM_PROMPT — fixed instructions about the task, format, and EPSO style.
2. _FEW_SHOT_ANCHORS — 10 real EPSO items loaded from few_shot/.
3. build_user_prompt() — assembles a per-call user message: 3-5 rotated anchors
   + the target dimensions + topics to avoid + the schema reminder.

Tuning this file is the single highest-leverage piece of Compass quality work.
Iterate via scripts/test_generate.py.
"""
from __future__ import annotations

import json
import random
from pathlib import Path

from backend.compass.item_schema import DISTRACTOR_CLASSES


# =============================================================================
# Anchor loading
# =============================================================================

_ANCHORS_PATH = Path(__file__).parent.parent / "few_shot" / "verbal_epso_anchors.json"


def _load_anchors() -> list[dict]:
    return json.loads(_ANCHORS_PATH.read_text())["items"]


_FEW_SHOT_ANCHORS: list[dict] = _load_anchors()


# =============================================================================
# System prompt — the fixed bit
# =============================================================================

SYSTEM_PROMPT = """You are an item author for EPSO (European Personnel Selection Office) verbal reasoning tests. You write items in the exact style of EPSO's official AST verbal reasoning samples: a self-contained passage followed by a multiple-choice question with four options.

EPSO verbal reasoning is closed-world deductive evaluation:
- The candidate must judge the statement using ONLY the passage. World knowledge is not allowed; correct answers must follow from the text alone.
- The wrong options are constructed to attract specific reading errors (over-generalisation of quantifiers, importing outside knowledge, missing a negation, accepting partial truth, ignoring a qualifier in another sentence).
- The passage is dense, factual, and typically 100-200 words. The question is short ("Which of the following statements is correct?", "Which conclusion can be drawn from the passage?", "What can be inferred from the text?").
- One option is unambiguously correct given the passage; three are wrong for distinct, identifiable reasons.

Hard rules for every item you produce:
1. The passage must be SELF-CONTAINED. Do not reference external charts, images, or sources.
2. Exactly four options, labelled "A.", "B.", "C.", "D." with the period.
3. Exactly one correct answer.
4. Each wrong option must fail for an identifiable reading-error reason, drawn from the canonical list below.
5. The explanation must cite the passage and explain why each wrong option is wrong, not just why the right one is right.
6. Vary topics across calls — EU institutions, EU policy areas (climate, digital, single market, justice), member-state contexts, recent EU programmes. Avoid the topics listed in the user message.
7. Declare ALL nine cognitive dimensions in the `dimensions` object. Match the target dimensions specified in the user message when possible; if a dimension is not specified, choose the value that best fits the item you produced.

Canonical distractor classes (use these for option_diagnostics — pick the 1-3 that best describe each wrong option):
- outside_knowledge: option is true in the world but unsupported by passage
- scope_strengthening: upgrades "some" to "all", "may" to "will", or similar
- scope_weakening: downgrades "all" to "some", or similar
- polarity_reversal: misreads a negation or double negation
- near_synonym: similar-sounding term with different scope or meaning
- partial_calculation: (not common in verbal; reserve for numerical items)
- partial_rule: ignores a qualifying clause from another sentence
- generic_recommendation: vague filler not grounded in the passage
- source_summary_only: just restates passage without answering the question

Style: factual, formal register typical of EU communications. Avoid colloquialisms, contractions, emojis."""


# =============================================================================
# Anchor rendering
# =============================================================================

def _render_anchor(item: dict, n: int) -> str:
    """Format one anchor as an example block for the user prompt."""
    opts = "\n".join(item["options"])
    correct_letter = "ABCD"[item["correct_index"]]
    return f"""### Example {n} (real EPSO item from {item['source_url']})

PASSAGE + QUESTION:
{item['passage_and_question']}

OPTIONS:
{opts}

CORRECT: {correct_letter} (index {item['correct_index']})"""


# =============================================================================
# User-prompt builder
# =============================================================================

def build_user_prompt(
    *,
    difficulty: int,
    target_dimensions: dict | None = None,
    recent_topic_tags: list[str] | None = None,
    n_anchors: int = 3,
    rng: random.Random | None = None,
) -> str:
    """Assemble the per-call user prompt.

    Args:
        difficulty: 1=easy, 2=medium, 3=hard. Steers passage density + inference depth.
        target_dimensions: optional dict like {"inference_depth": "multi_premise_inference"}.
                           The generator should aim to match these; it can choose values
                           for un-specified dimensions.
        recent_topic_tags: list of topic strings to avoid (so the bank doesn't repeat).
        n_anchors: how many anchor items to include (3-5; default 3).
        rng: optional Random instance for deterministic tests.
    """
    rng = rng or random
    n_anchors = max(3, min(n_anchors, 5, len(_FEW_SHOT_ANCHORS)))
    anchors = rng.sample(_FEW_SHOT_ANCHORS, n_anchors)
    anchor_block = "\n\n".join(_render_anchor(a, i + 1) for i, a in enumerate(anchors))

    difficulty_guidance = {
        1: "Easy: a short passage (3-4 sentences) where the correct answer is a direct paraphrase or explicit statement. Wrong options should be obviously contradicted by the passage.",
        2: "Medium: a passage of 5-7 sentences requiring a one-step inference or combination of two stated facts. At least one wrong option should be 'almost right' — true in the world but unsupported by the passage, or correct in spirit but with a wrong quantifier.",
        3: "Hard: a passage of 7-10 sentences requiring multi-premise inference. Wrong options should include subtle scope-shifts and partial truths. The correct answer should require integrating information from two or more non-adjacent sentences.",
    }.get(difficulty, "Medium difficulty.")

    avoid = ""
    if recent_topic_tags:
        avoid = f"\n\nAVOID these recently-used topics (do not generate items on these subjects):\n- " + "\n- ".join(recent_topic_tags)

    target = ""
    if target_dimensions:
        target_lines = "\n".join(f"  - {k}: {v}" for k, v in target_dimensions.items())
        target = f"""

TARGET COGNITIVE DIMENSIONS (the item must exercise these specifically):
{target_lines}

You MUST still declare ALL nine dimensions in your output. For un-specified dimensions, choose the value that honestly describes the item you produced.
"""

    return f"""Generate ONE EPSO-style verbal reasoning item.

DIFFICULTY: {difficulty} / 3
{difficulty_guidance}
{target}{avoid}

Below are three real EPSO items as style anchors. Match their tone, density, and option-construction style — but the topic, passage content, and specific traps must be NEW.

{anchor_block}

Now produce one new item. Return ONLY the structured output via the tool call. The `topic_tag` should be a short identifier (1-3 words, snake_case if multi-word) — e.g. 'etias', 'council_voting', 'horizon_europe', 'enlargement_policy'."""


# =============================================================================
# Available constants (re-exported for the generator)
# =============================================================================

__all__ = ["SYSTEM_PROMPT", "build_user_prompt", "DISTRACTOR_CLASSES"]
