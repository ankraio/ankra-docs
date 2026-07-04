#!/usr/bin/env python3
"""Fail if any .mdx page is unreachable from docs.json navigation, or any
nav/redirect entry points at a missing file."""

import glob
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def nav_pages(cfg: dict) -> set[str]:
    pages: set[str] = set()

    def walk(node):
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "pages" and isinstance(value, list):
                    for page in value:
                        if isinstance(page, str):
                            pages.add(page)
                        else:
                            walk(page)
                else:
                    walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(cfg["navigation"])
    return pages


def main() -> int:
    with open(os.path.join(ROOT, "docs.json")) as f:
        cfg = json.load(f)

    nav = nav_pages(cfg)
    files = {
        os.path.relpath(f, ROOT)[: -len(".mdx")]
        for f in glob.glob(os.path.join(ROOT, "**/*.mdx"), recursive=True)
        if "node_modules" not in f
    }

    redirect_sources = {
        r["source"].lstrip("/") for r in cfg.get("redirects", [])
    }

    orphans = sorted(files - nav)
    missing = sorted(nav - files)
    # A redirect source must NOT also exist as a real file.
    shadowed = sorted(redirect_sources & files)

    ok = True
    if orphans:
        ok = False
        print("ERROR: pages exist on disk but are not in docs.json navigation:")
        for p in orphans:
            print(f"  {p}.mdx")
    if missing:
        ok = False
        print("ERROR: docs.json navigation references missing files:")
        for p in missing:
            print(f"  {p}.mdx")
    if shadowed:
        ok = False
        print("ERROR: redirect sources shadow existing pages:")
        for p in shadowed:
            print(f"  {p}")

    if ok:
        print(f"OK: {len(files)} pages, all reachable from navigation.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
