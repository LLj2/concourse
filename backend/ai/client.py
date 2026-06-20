"""Anthropic client wrapper with JSON-schema-validated output.

Every LLM call in Concourse goes through `generate_json`, which forces the model
to return data matching a JSON schema (via a forced tool call) so callers always
get a validated dict — never free-form prose to parse. This is the typed,
schema-validated pattern the build plan requires for all LLM calls (scoring,
plan narration, CV-fit, log parsing).

Model: Haiku 4.5 (claude-haiku-4-5-20251001), per HANDOFF — cheap, fast, enough
for narration and structured extraction.
"""
from __future__ import annotations

from typing import Optional

from anthropic import Anthropic

from backend.config import settings

MODEL = "claude-haiku-4-5-20251001"

_client: Optional[Anthropic] = None


def _get_client() -> Anthropic:
    global _client
    if not settings.anthropic_api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set")
    if _client is None:
        _client = Anthropic(api_key=settings.anthropic_api_key)
    return _client


def generate_json(
    *,
    schema: dict,
    system: str,
    user: str,
    tool_name: str = "emit",
    max_tokens: int = 1024,
) -> dict:
    """Call the model and return a dict guaranteed to match `schema`.

    Uses a forced tool call: the model must invoke a tool whose input_schema is
    our schema, so the Anthropic API validates the structure for us. Raises on
    transport errors or if the model returns no tool call.
    """
    client = _get_client()
    resp = client.messages.create(
        model=MODEL,
        max_tokens=max_tokens,
        system=system,
        tools=[
            {
                "name": tool_name,
                "description": "Return the result in the required structure.",
                "input_schema": schema,
            }
        ],
        tool_choice={"type": "tool", "name": tool_name},
        messages=[{"role": "user", "content": user}],
    )
    for block in resp.content:
        if getattr(block, "type", None) == "tool_use" and getattr(block, "name", None) == tool_name:
            # block.input is already a dict validated against input_schema
            return dict(getattr(block, "input"))
    raise RuntimeError(f"model returned no '{tool_name}' tool call: {resp.stop_reason}")


def is_configured() -> bool:
    return bool(settings.anthropic_api_key)
