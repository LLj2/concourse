"""CLI for prompt iteration on the Compass item generator.

Usage:
    python -m scripts.test_generate verbal 2
    python -m scripts.test_generate verbal 2 --dims '{"inference_depth":"multi_premise_inference"}'
    python -m scripts.test_generate verbal 3 --avoid etias --avoid gdpr --dry-run
    python -m scripts.test_generate verbal 2 -n 5         # generate 5 items in a row

Flags:
    --dims JSON     target_dimensions (JSON object, keys from COGNITIVE_DIMENSIONS.md §2.2)
    --avoid TAG     topic to avoid (repeatable)
    --dry-run       call the LLM and validate, but DO NOT insert into items
    -n N            generate N items (default 1)
    --raw           print the raw LLM output dict (not the readable formatted version)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Repo root on sys.path so `backend.*` imports work when invoked from anywhere
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.compass.generate_item import generate_item


def _format_item_for_human(item: dict) -> str:
    """Render the generated item as readable text for eyeballing."""
    out: list[str] = []
    out.append("─" * 70)
    out.append(f"item_id:        {item.get('id') or '(dry-run; not inserted)'}")
    out.append(f"skill_id:       {item['skill_id']}")
    out.append(f"difficulty:     {item['difficulty']}")
    out.append(f"topic_tag:      {item['topic_tag']}")
    out.append(f"archived:       {item.get('archived')}  (True = hidden from picker until human-approved)")
    out.append("─" * 70)
    out.append(item["prompt"])
    out.append("")
    for opt in item["options"]:
        marker = "  ← CORRECT" if item["options"].index(opt) == item["correct_index"] else ""
        out.append(f"{opt}{marker}")
    out.append("")
    out.append("EXPLANATION:")
    out.append(item["explanation"])
    out.append("")
    out.append("DIMENSIONS:")
    for k, v in item["dimensions"].items():
        out.append(f"  {k}: {v}")
    out.append("")
    out.append("OPTION DIAGNOSTICS (why each wrong option attracts a wrong reader):")
    for d in item["option_diagnostics"]:
        letter = "ABCD"[d["index"]]
        out.append(f"  {letter}: {', '.join(d['distractor_classes'])}")
    out.append("─" * 70)
    return "\n".join(out)


def main() -> int:
    p = argparse.ArgumentParser(description="Generate Compass items for prompt iteration.")
    p.add_argument("skill", help="skill_id (verbal only in v1)")
    p.add_argument("difficulty", type=int, choices=[1, 2, 3], help="difficulty 1-3")
    p.add_argument("--dims", default=None, help='target dimensions as JSON (e.g. \'{"inference_depth":"multi_premise_inference"}\')')
    p.add_argument("--avoid", action="append", default=[], help="topic tag to avoid; repeatable")
    p.add_argument("--dry-run", action="store_true", help="generate + validate but don't insert into items")
    p.add_argument("-n", "--count", type=int, default=1, help="how many items to generate (default 1)")
    p.add_argument("--raw", action="store_true", help="print raw LLM output dict instead of formatted text")
    args = p.parse_args()

    target_dimensions = json.loads(args.dims) if args.dims else None

    n_ok = 0
    for i in range(args.count):
        if args.count > 1:
            print(f"\n=== generating item {i+1}/{args.count} ===")
        item = generate_item(
            skill_id=args.skill,
            difficulty=args.difficulty,
            target_dimensions=target_dimensions,
            recent_topic_tags=args.avoid or None,
            dry_run=args.dry_run,
        )
        if item is None:
            print("(generation failed — see logs above for the reason)")
            continue
        n_ok += 1
        if args.raw:
            print(json.dumps(item, indent=2, ensure_ascii=False))
        else:
            print(_format_item_for_human(item))

    if args.count > 1:
        print(f"\n=== {n_ok}/{args.count} items generated successfully ===")

    return 0 if n_ok > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
