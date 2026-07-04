#!/usr/bin/env python3
"""Guard against the corruption patterns that have previously shipped broken
commands, plus basic YAML/mermaid validity inside fenced code blocks.

Checks:
  1. Corruption denylist in code blocks (jammed flags like `curlX`, bare
     `H "Authorization..."` continuation lines, `create-name`, single-dash
     long flags, jammed ssh flags).
  2. Every ```yaml block parses with PyYAML (template/values blocks with Go
     templating or `${{ }}` placeholders are skipped).
  3. Mermaid flowcharts use `-->` arrows, never bare `->`.
  4. Prose lines outside code blocks that lost their `- ` list markers
     (single-space indented bold-start lines).
"""

import glob
import os
import re
import sys

try:
    import yaml  # type: ignore
except ImportError:  # pragma: no cover
    yaml = None

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CODE_DENYLIST = [
    (re.compile(r"\bcurlX\b"), "jammed 'curl -X'"),
    (re.compile(r"^\s*H ['\"](Authorization|Content-Type|Accept)"), "bare 'H' header (should be -H)"),
    (re.compile(r"^\s*d '\{"), "bare 'd' body (should be -d)"),
    (re.compile(r"\bssh[JL]\b"), "jammed ssh flag (ssh -J / ssh -L)"),
    (re.compile(r"\bcreate-name\b"), "jammed 'create --name'"),
    (re.compile(r"^\s*-set\s"), "single-dash '--set'"),
    (re.compile(r"get-login-password-region"), "jammed aws '--region'"),
    (re.compile(r"create-for-rbac-name"), "jammed az '--name'"),
    (
        re.compile(
            r"^\s*-(name|credential-id|ssh-key-credential-ids?|location|region|zone|"
            r"control-plane-(count|server-type|flavor-id|plan)|worker-(count|server-type|flavor-id|plan)|"
            r"instance-type|count|project-id|public-key|generate|scopes|role)\b"
        ),
        "single-dash long flag",
    ),
]

MERMAID_BAD_ARROW = re.compile(r"(\]|\))\s*->\s")
STRIPPED_BULLET = re.compile(r"^ \*\*[A-Z]")

YAML_SKIP_MARKERS = ("{{", "${{", "<base64", "<your-", "<cluster")


def iter_blocks(text: str):
    """Yield (lang, start_line, block_lines, is_code) segments."""
    lines = text.split("\n")
    i = 0
    while i < len(lines):
        stripped = lines[i].strip()
        if stripped.startswith("```"):
            lang = stripped[3:].strip().split()[0] if stripped[3:].strip() else ""
            start = i + 1
            j = start
            while j < len(lines) and not lines[j].strip().startswith("```"):
                j += 1
            yield lang, start + 1, lines[start:j], True
            i = j + 1
        else:
            yield "", i + 1, [lines[i]], False
            i += 1


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

        for lang, start, block, is_code in iter_blocks(text):
            if is_code:
                body = "\n".join(block)
                for n, line in enumerate(block, start):
                    for pattern, label in CODE_DENYLIST:
                        if pattern.search(line):
                            failures.append(f"{rel}:{n}: [{label}] {line.strip()[:80]}")
                if lang == "mermaid":
                    for n, line in enumerate(block, start):
                        if MERMAID_BAD_ARROW.search(line):
                            failures.append(
                                f"{rel}:{n}: [mermaid single '->' arrow] {line.strip()[:80]}"
                            )
                if lang in ("yaml", "yml") and yaml is not None:
                    if not any(marker in body for marker in YAML_SKIP_MARKERS):
                        try:
                            list(yaml.safe_load_all(body))
                        except yaml.YAMLError as exc:
                            msg = str(exc).split("\n")[0]
                            failures.append(f"{rel}:{start}: [yaml parse error] {msg}")
            else:
                line = block[0]
                if STRIPPED_BULLET.match(line):
                    failures.append(
                        f"{rel}:{start}: [stripped list marker] {line.strip()[:80]}"
                    )

    if failures:
        print("ERROR: snippet problems:")
        for f in failures:
            print(f"  {f}")
        return 1
    print(f"OK: {len(files)} pages pass snippet checks.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
