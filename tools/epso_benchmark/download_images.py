"""
Download the stimulus images for EPSO sample questions that need them.

Numerical and abstract reasoning items keep their actual stimulus (data table /
diagram series) in an image, not in the question text. The H5P export endpoint
serves a `.h5p` package (a zip) per content that bundles `content/images/*`.
This script reads the cached embeds, finds items with a real `file.path`,
downloads each export once and extracts its images into data/images/<id>/.

Run after scrape.py:
    python tools/epso_benchmark/download_images.py
    python tools/epso_benchmark/download_images.py --delay 4

It is idempotent: already-extracted images and a cached export are skipped.
"""
from __future__ import annotations

import argparse
import io
import json
import zipfile
from pathlib import Path

# reuse the polite client + constants from the scraper
from scrape import BASE, RAW_DIR, DATA_DIR, Crawler

IMAGES_DIR = DATA_DIR / "images"
EXPORT_URL = BASE + "/sites/default/files/tmp/exports/interactive-content-{id}.h5p"


def in_scope_ids() -> set[str] | None:
    """content_ids present in the current benchmark.json, to avoid pulling
    exports for every cached embed (e.g. leftover other-language items).
    Returns None if there is no benchmark yet (then all cached embeds apply)."""
    bf = DATA_DIR / "benchmark.json"
    if not bf.exists():
        return None
    data = json.loads(bf.read_text(encoding="utf-8"))
    return {it["content_id"] for it in data.get("items", [])}


def items_with_images() -> dict[str, dict]:
    """Map content_id -> {image_path, alt} for embeds carrying a real image."""
    scope = in_scope_ids()
    out: dict[str, dict] = {}
    for f in sorted(RAW_DIR.glob("*.json")):
        emb = json.loads(f.read_text(encoding="utf-8"))
        if scope is not None and emb["content_id"] not in scope:
            continue
        jc = emb.get("jsonContent", {})
        params = (jc.get("media", {}).get("type", {}).get("params", {})) or {}
        file = params.get("file")
        if file and file.get("path"):
            out[emb["content_id"]] = {
                "image_path": file["path"],
                "alt": params.get("alt", ""),
                "width": file.get("width"),
                "height": file.get("height"),
            }
    return out


def main():
    ap = argparse.ArgumentParser(description="Download EPSO stimulus images via .h5p exports")
    ap.add_argument("--delay", type=float, default=3.0)
    args = ap.parse_args()

    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    targets = items_with_images()
    print(f"{len(targets)} item(s) with a real stimulus image\n")

    crawler = Crawler(delay=args.delay)
    manifest: dict[str, list[str]] = {}
    try:
        for cid, info in targets.items():
            dest_dir = IMAGES_DIR / cid
            existing = list(dest_dir.glob("*")) if dest_dir.exists() else []
            if existing:
                manifest[cid] = [str(p.relative_to(DATA_DIR)) for p in existing]
                print(f"  = {cid}: cached ({len(existing)} img)")
                continue

            r = crawler.get(EXPORT_URL.format(id=cid))
            if not r or r.status_code != 200:
                print(f"  ! {cid}: export {r.status_code if r else 'ERR'}")
                continue
            try:
                z = zipfile.ZipFile(io.BytesIO(r.content))
            except zipfile.BadZipFile:
                print(f"  ! {cid}: not a zip")
                continue

            dest_dir.mkdir(parents=True, exist_ok=True)
            saved = []
            for name in z.namelist():
                if name.startswith("content/images/") and not name.endswith("/"):
                    data = z.read(name)
                    out = dest_dir / Path(name).name
                    out.write_bytes(data)
                    saved.append(str(out.relative_to(DATA_DIR)))
            manifest[cid] = saved
            print(f"  + {cid}: {info['alt'] or 'image'} -> {len(saved)} file(s)")
    finally:
        crawler.close()

    (IMAGES_DIR / "manifest.json").write_text(
        json.dumps({"images": manifest, "meta": targets}, ensure_ascii=False, indent=1),
        encoding="utf-8")
    total = sum(len(v) for v in manifest.values())
    print(f"\nExtracted {total} image file(s) for {len(manifest)} item(s)")
    print(f"-> {IMAGES_DIR}")


if __name__ == "__main__":
    main()
