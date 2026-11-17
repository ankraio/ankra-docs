#!/usr/bin/env python3
"""Every link to a heading on a docs page names an id the live site renders.

Mintlify gives a heading an id by rewriting its text, and the rewrite keeps more
than a Markdown slug does. `## Ankra's build cluster` renders as
<h2 id="ankra’s-build-cluster">: the straight apostrophe becomes the typographic
one and stays. A link written #ankras-build-cluster therefore opens the page at
its top, and nothing in CI caught that (ankra-jn451h): `mint broken-links` checks
that the page exists, never the anchor. This check renders each heading's id the
way the site does and fails a link whose anchor matches none.

The rules were read off the rendered site on 2026-11-17: every heading and
Update label of 23 fetched pages, 1,262 ids, matched both ways, and a second
reader matched 661 headings with special characters on 65 pages and 308 Update
labels. One example of each rule is in the self-test:

  - letters are lowercased; whitespace and . become -
  - ' becomes ’
  - " becomes “ after a space or an opening bracket, ” anywhere else (the start
    of the heading included)
  - backticks and , : ; ? ! ( ) [ ] are dropped
  - everything else stays: & € $ / | @ _ and the non-breaking hyphen among them
  - runs of - collapse; a leading or trailing - goes
  - a second identical id on the page gets -2, a third -3
  - a heading written in backticks keeps its text
  - assumed, not read (no heading on master has one): * is dropped, and a link in
    a heading counts by its text

An <Update label> renders an id by the same rules (the changelog's 2026-11-14 and
2026-11-14-2), and an explicit id="..." on an HTML element is one. A component
prop such as <YouTube id="..."> is not. <Step> and <Card> titles render no id.
<Accordion> and <Tab> titles render ids by rules of their own (an Accordion drops
the apostrophe, turns _ and / into -, and numbers repeats from -1; a Tab keeps ,
and / percent-encoded in the id). This check does not model those: a link whose
anchor spells such a title, letters and digits only, is not judged.

What is read: every .mdx, outside the frontmatter and code fences (and, for
links, outside inline code); links written [text](/page#anchor), [text](#anchor)
or href="/page#anchor". The anchor is percent-decoded and HTML-unescaped before
the comparison (the site's own table of contents writes #clusters-%26-kubernetes
for "Clusters & Kubernetes"). A page that does not exist here is mint
broken-links' finding, not this check's, and a link to a page that is not an
.mdx (the generated API reference) is not judged.

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
SKIPPED_DIRECTORIES = {"node_modules", ".git", ".claude", ".vale", ".mr-worktrees"}

FENCE = re.compile(r"^\s*```")
INLINE_CODE = re.compile(r"`[^`\n]*`")
HEADING = re.compile(r"^\s*#{1,6}\s+(.*?)\s*$")
LINK_TEXT = re.compile(r"\[([^\]]*)\]\([^)]*\)")
MARKDOWN_LINK = re.compile(r"\]\(\s*<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\s*\)")
HREF = re.compile(r"\bhref=\"([^\"]+)\"")
# An HTML element's id. A component's prop (<YouTube id="...">) is read by the component, never rendered as an id.
ELEMENT_ID = re.compile(r"<[a-z][\w-]*\b[^>]*\bid=\"([^\"]+)\"")
UPDATE_LABEL = re.compile(r"<Update\b[^>]*?\blabel=\"([^\"]*)\"")
OTHER_TITLE = re.compile(r"<(?:Accordion|Tab)\b[^>]*?\btitle=\"([^\"]*)\"")
DROPPED = set("`*,:;?!()[]")
RULES = (
    "a heading's id is its text lowercased, ' as ’ and \" as “ or ”, spaces and . as -, "
    "with , : ; ? ! ( ) [ ] and backticks dropped and & € $ / | @ _ kept"
)


# ---------------------------------------------------------------- what the site renders


def rendered_id(text):
    """The id Mintlify renders for a heading or an Update label."""
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


def letters(text):
    """A title or anchor reduced to its letters and digits, for the ids this check does not model."""
    return re.sub(r"[^a-z0-9]", "", html.unescape(LINK_TEXT.sub(r"\1", text)).lower())


def prose_lines(text):
    """(line number, line) for every line outside the frontmatter and code fences."""
    lines = text.split("\n")
    start = 0
    if lines and lines[0].strip() == "---":  # the frontmatter: a YAML comment in it is not a heading
        for index in range(1, len(lines)):
            if lines[index].strip() == "---":
                start = index + 1
                break
    in_fence = False
    for index in range(start, len(lines)):
        line = lines[index]
        if FENCE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        yield index + 1, line


class PageIds:
    """What the page renders: `exact`, the ids this check models (headings and Update labels numbered as
    the site numbers repeats, element ids), and `unmodelled`, the Accordion and Tab titles by their letters."""

    def __init__(self, text):
        self.exact = set()
        self.unmodelled = set()
        seen = {}
        for _, line in prose_lines(text):
            heading = HEADING.match(line)
            candidates = [heading.group(1)] if heading else []
            candidates += UPDATE_LABEL.findall(line)
            for candidate in candidates:
                rendered = rendered_id(candidate)
                if not rendered:
                    continue
                count = seen.get(rendered, 0) + 1
                seen[rendered] = count
                self.exact.add(rendered if count == 1 else f"{rendered}-{count}")
            for match in ELEMENT_ID.finditer(line):
                self.exact.add(html.unescape(match.group(1)))
            for title in OTHER_TITLE.findall(line):
                self.unmodelled.add(letters(title))


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


def resolve(page, target, pages):
    """(the page the target names as a path in `pages`, or None when it is not one to judge; the anchor)."""
    path, _, fragment = target.partition("#")
    # CommonMark decodes an entity in a link destination, so &amp; in the source is &.
    anchor = html.unescape(unquote(fragment))
    if not path:
        return page, anchor
    if not path.startswith("/"):
        return None, anchor
    stem = path.strip("/")
    for candidate in [f"{stem}.mdx", f"{stem}/index.mdx"] if stem else ["index.mdx"]:
        if candidate in pages:
            return candidate, anchor
    return None, anchor


def evaluate(pages):
    """pages: {relative path: text}. Returns (links checked, links not judged, findings), a
    finding being {"page", "target", "line", "anchor", "on", "nearest"}."""
    ids = {}
    checked = 0
    unjudged = 0
    findings = []
    for page in sorted(pages):
        for line, target in links(pages[page]):
            resolved, anchor = resolve(page, target, pages)
            if resolved is None:
                unjudged += 1
                continue
            if resolved not in ids:
                ids[resolved] = PageIds(pages[resolved])
            if anchor in ids[resolved].exact:
                checked += 1
                continue
            plain = letters(anchor)
            if plain in ids[resolved].unmodelled or re.sub(r"\d+$", "", plain) in ids[resolved].unmodelled:
                unjudged += 1  # an Accordion or Tab title, or a numbered repeat of one
                continue
            checked += 1
            nearest = difflib.get_close_matches(anchor, sorted(ids[resolved].exact), n=1, cutoff=0.6)
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
        "`spec.git_repository`": "spec-git_repository",
        "`spec.stacks[].backup`": "spec-stacks-backup",
        "Follow the imports: `affected:`": "follow-the-imports-affected",
        "Make \"done\" mean evidence": "make-“done”-mean-evidence",
        "**Bold** heading": "bold-heading",
    }
    for text, expected in cases.items():
        assert rendered_id(text) == expected, (text, rendered_id(text), expected)
    page = "\n".join(
        [
            "---",
            "title: A page",
            "# a YAML comment, not a heading",
            "---",
            "## AI & Automation",
            "## AI & Automation",
            '<Accordion title="Keep Loki\'s logs in object storage">',
            "text",
            "</Accordion>",
            '<Tab title="CI/CD">',
            '<Step title="Not an id">',
            '<Update label="2026-11-14" description="x">',
            '<Update label="2026-11-14">',
            "```markdown",
            "## Not a heading",
            "```",
            "A line with `## not a heading either` in code.",
            "## `spec.log_source`",
            '<span id="the-other-half-of-the-change" />',
            '<YouTube id="HzImi_lkMmw" title="Not an id" />',
        ]
    )
    ids = PageIds(page)
    assert ids.exact == {
        "ai-&-automation", "ai-&-automation-2", "2026-11-14", "2026-11-14-2", "spec-log_source", "the-other-half-of-the-change",
    }, ids.exact
    assert ids.unmodelled == {"keeplokislogsinobjectstorage", "cicd"}, ids.unmodelled
    pages = {
        "pipelines/where-pipelines-run.mdx": "\n".join(
            [
                "## Your own cluster",
                "See [the build cluster](#ankras-build-cluster), [right](#ankra%E2%80%99s-build-cluster) and [raw](#ankra’s-build-cluster).",
                "## Ankra's build cluster",
                '<Accordion title="Keep Loki\'s logs in object storage">',
                "[the live Accordion id](#keep-lokis-logs-in-object-storage) and [the heading spelling](#keep-loki’s-logs-in-object-storage)",
                "</Accordion>",
                '<Accordion title="Full pipeline.yaml">',
                '<Accordion title="Full pipeline.yaml">',
                "[the second one, as the site numbers it](#full-pipeline-yaml-1)",
                '<Tab title="GitLab CI, Bitbucket or CircleCI">',
                "[the Tab, as the site encodes it](#gitlab-ci%2C-bitbucket-or-circleci)",
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
    checked, unjudged, findings = evaluate(pages)
    assert (checked, unjudged) == (10, 8), (checked, unjudged)
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
    checked, unjudged, findings = evaluate(pages)
    if "--update" in argv:
        write_baseline(findings)
        print(f"wrote {len({key(f) for f in findings})} entries to scripts/anchors-baseline.json")
        return 0
    baseline = load_baseline()
    baselined = {key(entry) for entry in baseline}
    failing = {key(finding) for finding in findings}
    new = [finding for finding in findings if key(finding) not in baselined]
    stale = [entry for entry in baseline if key(entry) not in failing]
    print(
        f"anchors: {checked} links to headings on {len(pages)} pages checked against the ids the site renders; "
        f"{unjudged} not judged (a page that is missing or not an .mdx is mint broken-links' job; an Accordion or Tab title has rules of its own); "
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
