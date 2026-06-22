"""The item-generation pipeline.

generate_item(skill_id, difficulty, target_dimensions, ...) is the single entry point.
It:
  1. checks the org-global daily cap (events table) — returns None + logs generation_capped if hit
  2. builds the prompt from backend/compass/prompts/<skill>.py
  3. calls Anthropic via backend.ai.client.generate_json (forced tool call, JSON-schema-validated)
  4. runs semantic validation (validate_item)
  5. retries ONCE on validation failure with a stricter follow-up message
  6. inserts the item into items with archived=NOT COMPASS_AUTOAPPROVE_GENERATED
  7. logs events.generation_attempt / generation_succeeded / generation_failed

The function returns the inserted item dict (with `id`), or None if anything failed
(capped, retry exhausted, transport error). Callers decide whether to surface the
failure to the user or fall back to the bank.

This module is consumed by:
  - scripts/test_generate.py (CLI for prompt iteration; commit 2)
  - backend/compass/practice.py (the picker, when the bank is dry; commit 3)
"""
from __future__ import annotations

import json
import logging
import uuid
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.ai import client as ai_client
from backend.compass import item_schema
from backend.compass.prompts import verbal as verbal_prompt
from backend.config import settings
from backend.db.database import engine

log = logging.getLogger(__name__)


def _today_generation_count(db: Session) -> int:
    """Count `generation_succeeded` events emitted today (UTC) across all users."""
    row = db.execute(
        text(
            """
            select count(*) from events
            where kind = 'generation_succeeded'
              and created_at >= date_trunc('day', now() at time zone 'utc')
            """
        )
    ).scalar()
    return int(row or 0)


def _log_event(db: Session, kind: str, payload: dict, user_id: Optional[str] = None) -> None:
    """Append an event row. user_id is null for system-initiated generations (test CLI)."""
    db.execute(
        text("insert into events (user_id, kind, payload) values (:u, :k, :p)"),
        {"u": user_id, "k": kind, "p": json.dumps(payload)},
    )


def generate_item(
    *,
    skill_id: str,
    difficulty: int,
    target_dimensions: Optional[dict] = None,
    recent_topic_tags: Optional[list[str]] = None,
    content_domain: Optional[list[str]] = None,
    user_id: Optional[str] = None,
    dry_run: bool = False,
) -> Optional[dict]:
    """Generate one item and (unless dry_run) insert it into `items`.

    Returns the inserted dict on success, None on cap-hit or validation failure.

    Args:
        skill_id: 'verbal' is the only supported skill in v1. Raises ValueError otherwise.
        difficulty: 1-3.
        target_dimensions: optional dict steering the generation (e.g. {"inference_depth": "multi_premise_inference"}).
        recent_topic_tags: topics to avoid (so the generator doesn't repeat the bank).
        content_domain: free-form tags written to items.content_domain (e.g. ["GDPR"] for FRMCQ items; mostly unused for verbal).
        user_id: optional, for attribution in events. None for system-initiated (CLI testing).
        dry_run: if True, validate everything but skip the DB insert and skip the cap-counter increment.

    Side effects (unless dry_run):
        - Inserts a row into `items`.
        - Inserts events: generation_attempt, then one of {generation_succeeded, generation_failed, generation_capped}.

    Cost guard:
        - Reads the org-global day count from events. If >= COMPASS_DAILY_GEN_CAP, logs
          generation_capped and returns None WITHOUT making the LLM call.
    """
    if skill_id != "verbal":
        raise ValueError(
            f"generator does not yet support skill_id={skill_id!r}. v1 supports 'verbal' only."
        )

    schema = item_schema.build_schema(skill_id)
    system_prompt = verbal_prompt.SYSTEM_PROMPT
    user_prompt = verbal_prompt.build_user_prompt(
        difficulty=difficulty,
        target_dimensions=target_dimensions,
        recent_topic_tags=recent_topic_tags,
    )

    with engine.begin() as conn:
        # --- Cap check (org-global, UTC-day) -----------------------------------
        if not dry_run:
            count_today = _today_generation_count(conn)
            if count_today >= settings.compass_daily_gen_cap:
                _log_event(
                    conn,
                    "generation_capped",
                    {
                        "skill_id": skill_id,
                        "difficulty": difficulty,
                        "count_today": count_today,
                        "cap": settings.compass_daily_gen_cap,
                    },
                    user_id=user_id,
                )
                log.warning(
                    "generation_capped: %d/%d generations today",
                    count_today,
                    settings.compass_daily_gen_cap,
                )
                return None

            _log_event(
                conn,
                "generation_attempt",
                {"skill_id": skill_id, "difficulty": difficulty, "target_dimensions": target_dimensions},
                user_id=user_id,
            )

    # --- LLM call (outside transaction; transport errors propagate) ------------
    try:
        item = ai_client.generate_json(
            schema=schema,
            system=system_prompt,
            user=user_prompt,
            tool_name="emit_item",
            max_tokens=2048,
        )
    except Exception as exc:
        if not dry_run:
            with engine.begin() as conn:
                _log_event(
                    conn,
                    "generation_failed",
                    {"skill_id": skill_id, "stage": "llm_call", "error": str(exc)[:500]},
                    user_id=user_id,
                )
        log.exception("LLM call failed for skill=%s difficulty=%d", skill_id, difficulty)
        return None

    # --- Semantic validation ---------------------------------------------------
    ok, problems = item_schema.validate_item(item, skill_id)
    if not ok:
        # One retry, with the problems surfaced to the model
        retry_user_prompt = (
            user_prompt
            + "\n\nYour previous attempt failed validation with these problems:\n"
            + "\n".join(f"- {p}" for p in problems)
            + "\n\nProduce a new item that addresses all of these."
        )
        try:
            item = ai_client.generate_json(
                schema=schema,
                system=system_prompt,
                user=retry_user_prompt,
                tool_name="emit_item",
                max_tokens=2048,
            )
        except Exception as exc:
            if not dry_run:
                with engine.begin() as conn:
                    _log_event(
                        conn,
                        "generation_failed",
                        {"skill_id": skill_id, "stage": "retry_llm_call", "error": str(exc)[:500]},
                        user_id=user_id,
                    )
            log.exception("LLM retry call failed")
            return None

        ok, problems = item_schema.validate_item(item, skill_id)
        if not ok:
            if not dry_run:
                with engine.begin() as conn:
                    _log_event(
                        conn,
                        "generation_failed",
                        {
                            "skill_id": skill_id,
                            "stage": "validation_after_retry",
                            "problems": problems,
                        },
                        user_id=user_id,
                    )
            log.warning("generation failed validation after retry: %s", problems)
            return None

    if dry_run:
        return _shape_for_return(item, skill_id=skill_id, difficulty=difficulty,
                                 content_domain=content_domain, item_id=None, archived=None)

    # --- Insert into items -----------------------------------------------------
    archived = not settings.compass_autoapprove_generated  # default: hidden until approved
    new_id = str(uuid.uuid4())
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                insert into items (
                    id, skill_id, difficulty,
                    prompt, options, correct_index, explanation,
                    competition_family, content_domain, dimensions, option_diagnostics,
                    topic_tag, source, archived
                ) values (
                    :id, :skill, :diff,
                    :prompt, cast(:options as jsonb), :correct, :expl,
                    :family, cast(:content_domain as text[]), cast(:dims as jsonb), cast(:diags as jsonb),
                    :tag, 'generated', :archived
                )
                """
            ),
            {
                "id": new_id,
                "skill": skill_id,
                "diff": difficulty,
                "prompt": item["prompt"],
                "options": json.dumps(item["options"]),
                "correct": item["correct_index"],
                "expl": item["explanation"],
                "family": None,  # verbal items in v1 aren't scoped to a competition family
                "content_domain": "{" + ",".join(content_domain or []) + "}" if content_domain else None,
                "dims": json.dumps(item["dimensions"]),
                "diags": json.dumps(item["option_diagnostics"]),
                "tag": item["topic_tag"],
                "archived": archived,
            },
        )
        _log_event(
            conn,
            "generation_succeeded",
            {
                "skill_id": skill_id,
                "difficulty": difficulty,
                "item_id": new_id,
                "topic_tag": item["topic_tag"],
                "archived": archived,
            },
            user_id=user_id,
        )

    return _shape_for_return(item, skill_id=skill_id, difficulty=difficulty,
                             content_domain=content_domain, item_id=new_id, archived=archived)


def _shape_for_return(
    item: dict,
    *,
    skill_id: str,
    difficulty: int,
    content_domain: Optional[list[str]],
    item_id: Optional[str],
    archived: Optional[bool],
) -> dict:
    """Return shape for callers — combines LLM output + persistence metadata."""
    return {
        "id": item_id,
        "skill_id": skill_id,
        "difficulty": difficulty,
        "content_domain": content_domain,
        "archived": archived,
        **item,
    }
