#!/usr/bin/env python3
"""Keep changelog.mdx to one change per <Update>, so the per-month
mega-headline cannot come back.

The month used to be the unit of record, which forced a whole month to have a
single title: September 2026's ran to 1,614 characters and 39 commas because
the only honest title for 29 unrelated changes is a list of 29 things. That
headline was also shared mutable state, so every open pull request edited the
same line.

Checks (see STYLEGUIDE.md "Changelog"):
  1. Every <Update> opens on one line and carries a label.
  2. A label is a ship date (YYYY-MM-DD) or one of the frozen archive months.
     No new month record can be created.
  3. Only the frozen archive months may contain a '#' heading.
  4. Dated entries: 1-2 tags from the allowed set, an H2 headline under 140
     characters, a body of at most 80 words, and exactly one link, last. The
     headline is an H2 because that is what gives the entry its permalink -
     Mintlify anchors an <Update> by its label, and two changes shipping on
     one day share a label.
  5. "Also shipped" roll-ups instead carry bold-lead lines that each link out;
     a weekly bucket is addressed by its label, not per line.
  6. Dated entries sit above the archive, newest first.

Usage: check_changelog.py [path ...]   (defaults to changelog.mdx)
"""

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_TARGET = os.path.join(ROOT, "changelog.mdx")

# Month records that predate the one-change-per-Update format. Frozen: a new
# month-labelled <Update> is a new month record, which is the thing this check
# exists to prevent.
LEGACY_LABELS = {
    "September 2026",
    "August 2026",
    "July 2026",
    "June 2026",
    "May 2026",
    "April 2026",
    "March 2026",
    "February 2026",
    "December 2025",
    "November 2025",
    "June 2025",
    "May 2025",
    "March–April 2025",
}

# Of those, the ones still carrying their original '#' headline. September and
# August retired theirs into the description prop; nothing may grow one back.
LEGACY_H1_LABELS = LEGACY_LABELS - {"September 2026", "August 2026"}

ALLOWED_TAGS = [
    "Pipelines",
    "Security",
    "Cost",
    "Clusters",
    "AI",
    "GitOps",
    "CLI",
    "API",
    "Fixes",
]

MAX_BODY_WORDS = 80
MAX_HEADLINE_CHARS = 140
MAX_ROLLUP_WORDS = 200

OPEN_RE = re.compile(r"^<Update\b")
CLOSE_RE = re.compile(r"^</Update>\s*$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
LABEL_RE = re.compile(r'\blabel="([^"]*)"')
DESC_RE = re.compile(r'\bdescription="([^"]*)"')
TAGS_RE = re.compile(r"\btags=\{\[([^\]]*)\]\}")
LINK_RE = re.compile(r"\[[^\]]*\]\([^)]+\)")
ONLY_LINK_RE = re.compile(r"^\s*" + LINK_RE.pattern + r"\s*$")


class Block:
    def __init__(self, label, line, tags, description, body):
        self.label = label
        self.line = line
        self.tags = tags
        self.description = description
        self.body = body

    @property
    def dated(self):
        return bool(DATE_RE.match(self.label))

    @property
    def rollup(self):
        return "also shipped" in (self.description or "").lower()


def parse(text, rel, failures):
    """Split a changelog into <Update> blocks, reporting structural damage."""
    blocks = []
    open_line = None
    header = None
    body = []
    for n, line in enumerate(text.split("\n"), 1):
        if OPEN_RE.match(line):
            if open_line is not None:
                failures.append(
                    f"{rel}:{n}: <Update> opened while the block from line "
                    f"{open_line} is still open"
                )
            if not line.rstrip().endswith(">"):
                failures.append(
                    f"{rel}:{n}: <Update> tag must open and close on one line"
                )
            open_line, header, body = n, line, []
            continue
        if CLOSE_RE.match(line):
            if open_line is None:
                failures.append(f"{rel}:{n}: </Update> with no open <Update>")
                continue
            m = LABEL_RE.search(header)
            if not m:
                failures.append(f"{rel}:{open_line}: <Update> has no label")
            else:
                tags_m = TAGS_RE.search(header)
                tags = []
                if tags_m:
                    tags = [
                        t.strip().strip("\"'")
                        for t in tags_m.group(1).split(",")
                        if t.strip()
                    ]
                desc_m = DESC_RE.search(header)
                blocks.append(
                    Block(
                        label=m.group(1),
                        line=open_line,
                        tags=tags,
                        description=desc_m.group(1) if desc_m else None,
                        body=body,
                    )
                )
            open_line = None
            continue
        if open_line is not None:
            body.append((n, line))
    if open_line is not None:
        failures.append(f"{rel}:{open_line}: <Update> is never closed")
    return blocks


def check_label(block, rel, failures):
    if block.dated or block.label in LEGACY_LABELS:
        return
    failures.append(
        f"{rel}:{block.line}: label {block.label!r} is neither a ship date "
        f"(YYYY-MM-DD) nor a frozen archive month. One <Update> per change - "
        f"do not open a new month record."
    )


def check_no_new_h1(block, rel, failures):
    if block.label in LEGACY_H1_LABELS:
        return
    for n, line in block.body:
        if line.startswith("# "):
            failures.append(
                f"{rel}:{n}: '#' heading inside {block.label!r}. The headline is "
                f"an H2 on the first body line - an H1 is how the mega-headline "
                f"came back."
            )


def check_tags(block, rel, failures):
    if not block.tags:
        failures.append(
            f"{rel}:{block.line}: {block.label!r} has no tags. Give it one from "
            f"{', '.join(ALLOWED_TAGS)}."
        )
        return
    if len(block.tags) > 2:
        failures.append(
            f"{rel}:{block.line}: {block.label!r} has {len(block.tags)} tags "
            f"(at most 2, or the filter panel stops meaning anything)."
        )
    for tag in block.tags:
        if tag not in ALLOWED_TAGS:
            failures.append(
                f"{rel}:{block.line}: unknown tag {tag!r}. Allowed: "
                f"{', '.join(ALLOWED_TAGS)}."
            )


def check_rollup(block, rel, failures):
    words = 0
    for n, line in block.body:
        if not line.strip():
            continue
        words += len(line.split())
        if not line.lstrip().startswith("**"):
            failures.append(
                f"{rel}:{n}: every line of an 'Also shipped' roll-up starts "
                f"with a bold subject."
            )
        elif not LINK_RE.search(line):
            failures.append(f"{rel}:{n}: roll-up line has no link.")
    if words > MAX_ROLLUP_WORDS:
        failures.append(
            f"{rel}:{block.line}: roll-up is {words} words (max "
            f"{MAX_ROLLUP_WORDS}). Promote the big ones to their own entry."
        )


def check_entry(block, rel, failures):
    lines = [(n, l) for n, l in block.body if l.strip()]
    if not lines:
        failures.append(f"{rel}:{block.line}: {block.label!r} has an empty body.")
        return

    head_n, head = lines[0]
    if not head.startswith("## "):
        failures.append(
            f"{rel}:{head_n}: the first line is the headline and must be an H2 "
            f"('## One sentence.'). It is what gives the entry its permalink - "
            f"a bold line has no anchor."
        )
    headline = head[3:].strip() if head.startswith("## ") else head.strip()
    if len(headline) > MAX_HEADLINE_CHARS:
        failures.append(
            f"{rel}:{head_n}: headline is {len(headline)} characters (max "
            f"{MAX_HEADLINE_CHARS})."
        )
    for n, line in lines[1:]:
        if line.startswith("#"):
            failures.append(
                f"{rel}:{n}: an entry carries one heading, its headline. Split "
                f"this into its own <Update>."
            )

    links = [(n, l) for n, l in lines if LINK_RE.search(l)]
    if len(links) != 1:
        failures.append(
            f"{rel}:{block.line}: {block.label!r} has {len(links)} links "
            f"(exactly one, the canonical page). Extra detail belongs on that "
            f"page, not here."
        )
    elif links[0][0] != lines[-1][0]:
        failures.append(
            f"{rel}:{links[0][0]}: the link is the last line of the entry."
        )
    elif not ONLY_LINK_RE.match(links[0][1]):
        failures.append(
            f"{rel}:{links[0][0]}: the last line is the link alone, with no "
            f"prose around it."
        )

    body_words = sum(
        len(l.split())
        for n, l in lines[1:]
        if not ONLY_LINK_RE.match(l)
    )
    if body_words > MAX_BODY_WORDS:
        failures.append(
            f"{rel}:{block.line}: body is {body_words} words (max "
            f"{MAX_BODY_WORDS}). Say what the reader can now do; move the "
            f"reference detail onto the docs page you link to."
        )


def check_order(blocks, rel, failures):
    seen_legacy = None
    previous = None
    for block in blocks:
        if not block.dated:
            seen_legacy = block.label
            continue
        if seen_legacy:
            failures.append(
                f"{rel}:{block.line}: dated entry sits below the archive month "
                f"{seen_legacy!r}. New entries go at the top of the file."
            )
        if previous and block.label > previous[0]:
            failures.append(
                f"{rel}:{block.line}: {block.label} is newer than {previous[0]} "
                f"above it. Newest first."
            )
        previous = (block.label, block.line)


def check(path, failures):
    full = os.path.abspath(path)
    rel = os.path.relpath(full, ROOT) if full.startswith(ROOT + os.sep) else path
    with open(path) as f:
        text = f.read()
    blocks = parse(text, rel, failures)
    for block in blocks:
        check_label(block, rel, failures)
        check_no_new_h1(block, rel, failures)
        if not block.dated:
            continue
        check_tags(block, rel, failures)
        if block.rollup:
            check_rollup(block, rel, failures)
        else:
            check_entry(block, rel, failures)
    check_order(blocks, rel, failures)
    return blocks


def main(argv) -> int:
    targets = argv[1:] or [DEFAULT_TARGET]
    failures = []
    total = 0
    for path in targets:
        total += len(check(path, failures))

    if failures:
        print("ERROR: changelog format problems:")
        for f in failures:
            print(f"  {f}")
        print("\nSee STYLEGUIDE.md, section 'Changelog'.")
        return 1
    print(f"OK: {total} changelog entries follow the format.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
