#!/usr/bin/env python3
"""Fail if any .mdx page is missing frontmatter with a non-empty title and
description."""

import glob
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---", re.DOTALL)


def main() -> int:
    failures = []
    files = [
        f
        for f in glob.glob(os.path.join(ROOT, "**/*.mdx"), recursive=True)
        if "node_modules" not in f
    ]
    for path in sorted(files):
        rel = os.path.relpath(path, ROOT)
        with open(path) as f:
            text = f.read()
        m = FRONTMATTER_RE.match(text)
        if not m:
            failures.append(f"{rel}: no frontmatter block")
            continue
        fm = m.group(1)
        for field in ("title", "description"):
            fm_match = re.search(
                rf"^{field}:\s*(.+)$", fm, re.MULTILINE
            )
            if not fm_match or not fm_match.group(1).strip().strip("\"'"):
                failures.append(f"{rel}: missing or empty '{field}'")

    if failures:
        print("ERROR: frontmatter problems:")
        for f in failures:
            print(f"  {f}")
        return 1
    print(f"OK: {len(files)} pages have title + description frontmatter.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
