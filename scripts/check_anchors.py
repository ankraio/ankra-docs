#!/usr/bin/env python3
"""Every link to a heading on a docs page names an id the live site renders.

Mintlify gives a heading an id by rewriting its text, and the rewrite keeps more
than a Markdown slug does: `## Ankra's build cluster` renders as
<h2 id="ankra’s-build-cluster">, the straight apostrophe turned into the
typographic one and kept, so a link written #ankras-build-cluster opens the page
at its top. Nothing in CI caught that (ankra-jn451h): `mint broken-links` checks
that the page exists, never the anchor. This check renders each heading's id the
way the site does and fails a link whose anchor matches none.

The rules, read off the rendered site on 2026-11-17 (every heading of 19 pages,
769 headings, matched; the self-test holds one example of each):

  lowercase; ' becomes ’; " becomes “ after a space or an opening bracket and ”
  anywhere else, the start of the heading included; whitespace and . become -;
  backticks, *, and , : ; ? ! ( ) [ ] are dropped; everything else stays (& € $
  / | @ _ and the non-breaking hyphen among them); runs of - collapse and a
  leading or trailing - goes; a second identical id on the page gets -2, a
  third -3. A link in a heading counts by its text. An <Accordion title>, a
  <Tab title> and an <Update label> render an id too, and an explicit id="..."
  is one. <Step> and <Card> titles render none.

What is read: every .mdx, outside code fences (and, for links, outside inline
code); links written
[text](/page#anchor), [text](#anchor) or href="/page#anchor". The anchor is
percent-decoded and HTML-unescaped before the comparison (the site's own table
of contents writes #clusters-%26-kubernetes for "Clusters & Kubernetes"). A page
that does not exist is mint broken-links' finding, not this check's; an exact
redirect in docs.json is followed; a link to a page that is not an .mdx (the
generated API reference) is not judged.

scripts/anchors-baseline.json holds the anchors that were already dead when the
check was introduced (2026-11-17), keyed on page and link target, never the
line, so a pull request fixing one page cannot collide with another. Nothing new
may join it except deliberately with --update. An entry that no longer fails is
reported so it can be removed: a warning, an error under --strict.

    python3 scripts/check_anchors.py              # check
    python3 scripts/check_anchors.py --strict     # stale baseline entries fail too
    python3 scripts/check_anchors.py --update     # rewrite the baseline from what fails now
    python3 scripts/check_anchors.py --self-test
"""

import difflib
import html
import json
import os
import re
import sys
from urllib.parse import unquote

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASELINE_PATH = os.path.join(ROOT, "scripts", "anchors-baseline.json")
DOCS_JSON_PATH = os.path.join(ROOT, "docs.json")
SKIPPED_DIRECTORIES = {"node_modules", ".git", ".claude", ".vale", ".mr-worktrees"}

FENCE = re.compile(r"^\s*```")
INLINE_CODE = re.compile(r"`[^`\n]*`")
HEADING = re.compile(r"^\s*#{1,6}\s+(.*?)\s*$")
LINK_TEXT = re.compile(r"\[([^\]]*)\]\([^)]*\)")
MARKDOWN_LINK = re.compile(r"\]\(\s*<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\s*\)")
HREF = re.compile(r"\bhref=\"([^\"]+)\"")
EXPLICIT_ID = re.compile(r"\bid=\"([^\"]+)\"")
TITLED = re.compile(r"<(?:Accordion|Tab)\b[^>]*?\btitle=\"([^\"]*)\"")
UPDATE_LABEL = re.compile(r"<Update\b[^>]*?\blabel=\"([^\"]*)\"")
DROPPED = set("`*,:;?!()[]")
RULES = (
    "a heading's id is its text lowercased, ' as ’ and \" as “ or ”, spaces and . as -, "
    "with , : ; ? ! ( ) [ ] and backticks dropped and & € $ / | @ _ kept"
)


# ---------------------------------------------------------------- what the site renders


def rendered_id(text):
    """The id Mintlify renders for a heading, an Accordion title or an Update label."""
    text = html.unescape(LINK_TEXT.sub(r"\1", text)).strip()
    out = []
    for index, char in enumerate(text):
        if char == "'":
            out.append("’")
        elif char == '"':
            before = text[index - 1] if index else ""
            out.append("“" if before and (before.isspace() or before in "([") else "”")
        elif char in DROPPED:
            continue
        elif char.isspace() or char == ".":
            out.append("-")
        else:
            out.append(char.lower())
    return re.sub(r"-+", "-", "".join(out)).strip("-")


def prose_lines(text):
    """(line number, line) for every line outside code fences."""
    in_fence = False
    for number, line in enumerate(text.split("\n"), start=1):
        if FENCE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        yield number, line


def page_ids(text):
    """Every id the page renders: headings, Accordion and Tab titles and Update labels,
    numbered as the site numbers repeats, plus explicit id attributes."""
    ids = set()
    seen = {}

    def add(candidate):
        if not candidate:
            return
        count = seen.get(candidate, 0) + 1
        seen[candidate] = count
        ids.add(candidate if count == 1 else f"{candidate}-{count}")

    for _, line in prose_lines(text):
        heading = HEADING.match(line)
        if heading:
            add(rendered_id(heading.group(1)))
        for match in TITLED.finditer(line):
            add(rendered_id(match.group(1)))
        for match in UPDATE_LABEL.finditer(line):
            add(rendered_id(match.group(1)))
        for match in EXPLICIT_ID.finditer(line):
            ids.add(html.unescape(match.group(1)))
    return ids


# ---------------------------------------------------------------- links


def links(text):
    """[(line, target)] for every link with a fragment on the page's prose lines."""
    found = []
    for number, line in prose_lines(text):
        line = INLINE_CODE.sub("", line)  # a link quoted in code is not a link
        for match in MARKDOWN_LINK.finditer(line):
            found.append((number, match.group(1)))
        for match in HREF.finditer(line):
            found.append((number, match.group(1)))
    return [(number, target) for number, target in found if "#" in target and "://" not in target and not target.startswith("mailto:")]


def load_redirects():
    """Exact docs.json redirects, source to destination; a wildcard pattern is left out."""
    if not os.path.exists(DOCS_JSON_PATH):
        return {}
    with open(DOCS_JSON_PATH, encoding="utf-8") as handle:
        redirects = json.load(handle).get("redirects", [])
    return {
        entry["source"]: entry["destination"]
        for entry in redirects
        if ":" not in entry["source"] and "*" not in entry["source"]
    }


def resolve(page, target, pages, redirects):
    """(the page the target names as a path in `pages`, or None when it is not one to judge; the anchor)."""
    path, _, fragment = target.partition("#")
    anchor = html.unescape(unquote(fragment))
    if not path:
        return page, anchor
    path = path.rstrip("/") or "/"
    path = redirects.get(path, path).split("#")[0]
    if not path.startswith("/"):
        return None, anchor
    stem = path.strip("/")
    for candidate in [f"{stem}.mdx", f"{stem}/index.mdx"] if stem else ["index.mdx"]:
        if candidate in pages:
            return candidate, anchor
    return None, anchor


def evaluate(pages, redirects):
    """pages: {relative path: text}. Returns (links checked, links not judged, findings), a
    finding being {"page", "target", "line", "anchor", "on", "nearest"}."""
    ids = {}
    checked = 0
    unjudged = 0
    findings = []
    for page in sorted(pages):
        for line, target in links(pages[page]):
            resolved, anchor = resolve(page, target, pages, redirects)
            if resolved is None:
                unjudged += 1
                continue
            checked += 1
            if resolved not in ids:
                ids[resolved] = page_ids(pages[resolved])
            if anchor in ids[resolved]:
                continue
            nearest = difflib.get_close_matches(anchor, sorted(ids[resolved]), n=1, cutoff=0.6)
            findings.append(
                {
                    "page": page,
                    "target": target,
                    "line": line,
                    "anchor": anchor,
                    "on": "/" + resolved[: -len(".mdx")].removesuffix("/index"),
                    "nearest": nearest[0] if nearest else None,
                }
            )
    return checked, unjudged, findings


# ---------------------------------------------------------------- pages and ratchet


def docs_pages():
    for directory, subdirectories, files in os.walk(ROOT):
        subdirectories[:] = sorted(name for name in subdirectories if name not in SKIPPED_DIRECTORIES)
        for name in sorted(files):
            if name.endswith(".mdx"):
                yield os.path.normpath(os.path.relpath(os.path.join(directory, name), ROOT))


def key(entry):
    return (entry["page"], entry["target"])


def load_baseline():
    if not os.path.exists(BASELINE_PATH):
        return []
    with open(BASELINE_PATH, encoding="utf-8") as handle:
        return json.load(handle)["entries"]


def write_baseline(findings):
    entries = sorted({key(finding): finding for finding in findings}.values(), key=key)
    lines = [
        "{",
        '  "about": "Links to anchors no heading renders that were already dead when scripts/check_anchors.py was introduced (2026-11-17). '
        "Tolerated until the page is fixed; remove an entry when its link is fixed or gone. Keyed on page and link target, never the line. "
        "A link here opens its page at the top.\",",
        '  "entries": [',
        ",\n".join("    " + json.dumps({"page": entry["page"], "target": entry["target"]}, ensure_ascii=False) for entry in entries),
        "  ]",
        "}",
    ]
    with open(BASELINE_PATH, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")


def annotate(level, page, line, message):
    """A GitHub annotation in Actions (shown on the pull request's diff), page:line: message elsewhere."""
    where = f"{page}:{line}" if line else page
    if os.environ.get("GITHUB_ACTIONS") == "true":
        location = f"file={page},line={line}" if line else f"file={page}"
        return f"::{level} {location}::{message}"
    return f"{where}: {message}"


def describe(finding):
    nearest = f" (nearest id: #{finding['nearest']})" if finding["nearest"] else ""
    return f"#{finding['anchor']} is not an id on {finding['on']}{nearest}"


# ---------------------------------------------------------------- self-test


def self_test():
    cases = {
        "Ankra's build cluster": "ankra’s-build-cluster",
        "A cluster's Security page": "a-cluster’s-security-page",
        "Delete Kubernetes & Scale Back Up": "delete-kubernetes-&-scale-back-up",
        "CLI v0.1.125 & API Updates": "cli-v0-1-125-&-api-updates",
        "Kubernetes Node Cordon, Uncordon & Drain": "kubernetes-node-cordon-uncordon-&-drain",
        "Hetzner: Automatic CCM & CSI Provisioning": "hetzner-automatic-ccm-&-csi-provisioning",
        "Welcome credit now lasts 30 days, and the Startups programme grants €1,000 for six months":
            "welcome-credit-now-lasts-30-days-and-the-startups-programme-grants-€1000-for-six-months",
        "The DevOps AI model by Ankra: $50 a month on every plan": "the-devops-ai-model-by-ankra-$50-a-month-on-every-plan",
        "Merge when green has an on/off switch per GitHub installation": "merge-when-green-has-an-on/off-switch-per-github-installation",
        "Machine-readable output (`-o json|yaml`)": "machine-readable-output-o-json|yaml",
        "Talk to it: `@ankraai`": "talk-to-it-@ankraai",
        "Skip a push with `[skip ci]`": "skip-a-push-with-skip-ci",
        "Add‑on Experience": "add‑on-experience",
        "No shell in the image?": "no-shell-in-the-image",
        "A forced stop keeps your volumes; only a deprovision deletes them": "a-forced-stop-keeps-your-volumes-only-a-deprovision-deletes-them",
        "Stack Builder: Go from 0 to 100 in 2.3s": "stack-builder-go-from-0-to-100-in-2-3s",
        "4. Optional: keep the cluster's configuration in Git": "4-optional-keep-the-cluster’s-configuration-in-git",
        '1. "Tell me fast whether my change works"': "1-“tell-me-fast-whether-my-change-works”",
        '"Read-only file system" or "permission denied"': "”read-only-file-system”-or-“permission-denied”",
        'Claude reports "Couldn\'t register with Ankra\'s sign-in service"':
            "claude-reports-“couldn’t-register-with-ankra’s-sign-in-service”",
        "Every application now gets its own registry robot account - on Ankra's registry":
            "every-application-now-gets-its-own-registry-robot-account-on-ankra’s-registry",
        "[`spec.log_source`](/reference/importcluster) and `spec.git_repository`": "spec-log_source-and-spec-git_repository",
        "**Bold** heading": "bold-heading",
        "`spec.git_repository`": "spec-git_repository",
        "`spec.stacks[].backup`": "spec-stacks-backup",
        "Follow the imports: `affected:`": "follow-the-imports-affected",
    }
    for text, expected in cases.items():
        assert rendered_id(text) == expected, (text, rendered_id(text), expected)
    page = "\n".join(
        [
            "## AI & Automation",
            "## AI & Automation",
            '<Accordion title="Is it safe to leave a cluster half upgraded?">',
            "text",
            "</Accordion>",
            '<Tab title="Portal">',
            '<Step title="Not an id">',
            '<Update label="2026-11-14" description="x">',
            '<Update label="2026-11-14">',
            "```markdown",
            "## Not a heading",
            "```",
            "## `spec.log_source`",
            "A line with `## not a heading either` in code.",
            '<a id="the-other-half-of-the-change" />',
        ]
    )
    assert page_ids(page) == {
        "ai-&-automation", "ai-&-automation-2", "is-it-safe-to-leave-a-cluster-half-upgraded", "portal",
        "2026-11-14", "2026-11-14-2", "spec-log_source", "the-other-half-of-the-change",
    }, page_ids(page)
    pages = {
        "pipelines/where-pipelines-run.mdx": "\n".join(
            [
                "## Your own cluster",
                "See [the build cluster](#ankras-build-cluster), [right](#ankra%E2%80%99s-build-cluster) and [raw](#ankra’s-build-cluster).",
                "## Ankra's build cluster",
            ]
        ),
        "guides/a.mdx": "\n".join(
            [
                "[dead](/pipelines/where-pipelines-run#ankras-build-cluster) [fine](/pipelines/where-pipelines-run#your-own-cluster)",
                "[missing page](/nowhere#x) [api](/api-reference/clusters/list#response) [redirected](/old/where#your-own-cluster)",
                '<Card title="Go" href="/pipelines/where-pipelines-run#nope" /> [tools](/platform/mcp-tools#clusters-%26-kubernetes)',
                "[entity](/platform/mcp-tools#clusters-&amp;-kubernetes) [external](https://example.com/x#y) [index](/#start)",
                "```",
                "[fenced](/pipelines/where-pipelines-run#nope)",
                "```",
                "A `[coded](/pipelines/where-pipelines-run#nope)` link and ![an image](/images/x.png).",
                "[same page](#nope) [relative](../x#y)",
            ]
        ),
        "platform/mcp-tools.mdx": "## Clusters & Kubernetes\n",
        "index.mdx": "## Start\n",
    }
    checked, unjudged, findings = evaluate(pages, {"/old/where": "/pipelines/where-pipelines-run"})
    assert (checked, unjudged) == (11, 3), (checked, unjudged)
    assert [(f["page"], f["line"], f["target"], f["nearest"]) for f in findings] == [
        ("guides/a.mdx", 1, "/pipelines/where-pipelines-run#ankras-build-cluster", "ankra’s-build-cluster"),
        ("guides/a.mdx", 3, "/pipelines/where-pipelines-run#nope", None),
        ("guides/a.mdx", 9, "#nope", None),
        ("pipelines/where-pipelines-run.mdx", 2, "#ankras-build-cluster", "ankra’s-build-cluster"),
    ], findings
    assert findings[0]["on"] == "/pipelines/where-pipelines-run"
    assert describe(findings[0]) == "#ankras-build-cluster is not an id on /pipelines/where-pipelines-run (nearest id: #ankra’s-build-cluster)"
    print("anchors self-test: ok")


# ---------------------------------------------------------------- main


def main(argv):
    if "--self-test" in argv:
        self_test()
        return 0
    strict = "--strict" in argv
    pages = {}
    for page in docs_pages():
        with open(os.path.join(ROOT, page), encoding="utf-8") as handle:
            pages[page] = handle.read()
    checked, unjudged, findings = evaluate(pages, load_redirects())
    if "--update" in argv:
        write_baseline(findings)
        print(f"wrote {len({key(f) for f in findings})} entries to scripts/anchors-baseline.json")
        return 0
    baseline = load_baseline()
    baselined = {key(entry) for entry in baseline}
    failing = {key(finding) for finding in findings}
    new = [finding for finding in findings if key(finding) not in baselined]
    stale = [entry for entry in baseline if key(entry) not in baselined - (baselined - failing)]
    print(
        f"anchors: {checked} links to headings on {len(pages)} pages checked against the ids the site renders; "
        f"{unjudged} not judged (a page that is missing or not an .mdx is mint broken-links' job); "
        f"{len(findings)} findings, {len(findings) - len(new)} baselined, {len(new)} new"
    )
    if new:
        print(
            f"{len(new)} link(s) to an anchor no heading renders, so the page opens at its top. {RULES}: "
            "write the anchor as the id (percent-encode ’ as %E2%80%99 if you prefer ASCII), or link the page without an anchor. "
            "An anchor that was already dead and waits for its page goes in scripts/anchors-baseline.json (--update rewrites it):",
            file=sys.stderr,
        )
        for finding in new:
            print("  " + annotate("error", finding["page"], finding["line"], describe(finding)), file=sys.stderr)
    if stale:
        level = "error" if strict else "warning"
        print(
            f"{len(stale)} baseline entr{'y' if len(stale) == 1 else 'ies'} no longer fail{'s' if len(stale) == 1 else ''}; remove "
            f"{'it' if len(stale) == 1 else 'them'} from scripts/anchors-baseline.json (--update rewrites it):",
            file=sys.stderr,
        )
        for entry in stale:
            print("  " + annotate(level, entry["page"], None, f"{entry['target']} no longer fails"), file=sys.stderr)
    return 1 if new or (strict and stale) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
