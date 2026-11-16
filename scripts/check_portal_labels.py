#!/usr/bin/env python3
"""Every bold menu path and every /next address a hand-written page states must
be something the Ankra portal has.

The 2026-11-15 audit found 146 of 170 pages with portal steps describing a
portal that is no longer served: menu paths through labels that are gone and
addresses that are not routes, and nothing in CI that would have caught it
(ankra-4xh2sn.3). The portal's source (ankraio/ankra-frontend) is private, so
Docs CI cannot read it. scripts/portal-inventory.json is the vendored truth:
the routes the portal serves and the strings it can show as a label, with the
commit and date they were read from. scripts/gen_portal_inventory.py writes
it; regenerate it when the portal changes:

    git -C ../ankra-frontend fetch origin
    python3 scripts/gen_portal_inventory.py --frontend-repo ../ankra-frontend

What is read: every hand-written .mdx page (reference/cli, changelog.mdx and
integrations/ankra-cli-changelog.mdx are records, not instructions), outside
code fences:

  menu paths  bold labels joined by an arrow, **A** → **B** → **C**, or one
              bold span holding the arrows, **A → B → C**. The arrow is →,
              -> or a spaced > (also written &gt;). A part that is only a
              placeholder (<cluster>, [Your cluster], {name}) or only an icon
              (⋯) is not checked; around a placeholder inside a part (Upgrade
              to <version>) the words are checked on their own. A bold span
              whose parts read as a sentence (a full stop, a colon, more than
              six words) is prose, not a path.
  addresses   /next/... in prose, bare or under https://platform.ankra.app,
              and in code fences under the host only.

A label passes when the inventory has a string equal to it or holding it as
whole words (Billing is in "Billing and limits"), case-sensitively, with the
two apostrophes, &amp; and &, and … and ... read as one. An address passes
when a route has its shape: [id] takes one segment, [...x] one or more,
[[...x]] zero or more; a placeholder (<cluster-id>, {id}, a UUID, CVE-...)
fills only a dynamic segment, never a literal one, because the reader would
type an id there; a trailing ... means "and whatever follows". A query and a
fragment are not checked.

Two files make it a ratchet, both keyed on page and label (or address),
never on line numbers, so the pull requests fixing pages do not collide:

  scripts/portal-labels-allowlist.json  false alarms, each with its reason: a
      label of another product (GitHub, Cloudflare, the Azure portal), a name
      that is data rather than a label. Hand-edited.
  scripts/portal-labels-baseline.json   labels and addresses that were
      already stale when this check was introduced, tolerated until their page
      is fixed; nothing new may join them except deliberately with --update.

A finding in neither file fails, and the message names the inventory commit
and date: a page that documents a label newer than the inventory fails until
the inventory is regenerated. An entry in either file that no longer fails is
reported so it can be removed: a warning, an error under --strict.

    python3 scripts/check_portal_labels.py              # check
    python3 scripts/check_portal_labels.py --strict     # stale entries fail too
    python3 scripts/check_portal_labels.py --update     # rewrite the baseline from what fails now
    python3 scripts/check_portal_labels.py --self-test
"""

import datetime
import html
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INVENTORY_PATH = os.path.join(ROOT, "scripts", "portal-inventory.json")
ALLOWLIST_PATH = os.path.join(ROOT, "scripts", "portal-labels-allowlist.json")
BASELINE_PATH = os.path.join(ROOT, "scripts", "portal-labels-baseline.json")
SKIPPED_DIRECTORIES = {"node_modules", ".git", ".claude", ".vale", ".mr-worktrees"}
GENERATED_DIRECTORY = os.path.join("reference", "cli")
GENERATED_PAGES = {"changelog.mdx", os.path.join("integrations", "ankra-cli-changelog.mdx")}
REGENERATE = "python3 scripts/gen_portal_inventory.py --frontend-repo <ankra-frontend checkout> (git fetch it first)"
# The inventory is a copy, so it ages. Past this many days the run says so: a label the portal gained since
# the copy was taken fails here although the page is right.
INVENTORY_WARN_AFTER_DAYS = 14

FENCE = re.compile(r"^\s*```")
BOLD = re.compile(r"\*\*(?!\s)([^*\n]+?)\*\*")
BETWEEN_SPANS = re.compile(r"^\s*(?:→|->|&gt;|>)\s*$")
IN_SPAN = re.compile(r"\s*(?:→|->)\s*|\s+(?:>|&gt;)\s+")
PLACEHOLDER = re.compile(r"<[^<>]+>|&lt;.*?&gt;|\[[^\[\]]+\](?!\()|\{[^{}]+\}")
LINK = re.compile(r"\[([^\]]+)\]\([^)]*\)")
HOST = r"https?://platform\.ankra\.app"
ADDRESS_CHARACTERS = r"[^\s\"'`)\]|,*]"
PROSE_ADDRESS = re.compile(rf"(?<![\w./-])(?:{HOST})?(/next(?![\w-]){ADDRESS_CHARACTERS}*)")
CODE_ADDRESS = re.compile(rf"(?<![\w./-]){HOST}(/next(?![\w-]){ADDRESS_CHARACTERS}*)")
UUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
DYNAMIC_SEGMENT = re.compile(r"^(?:<.*>|&lt;.*&gt;|\{.*\}|\[.*\]|\$\{?\w+\}?|:\w+)$")
MAX_LABEL_WORDS = 6


# ---------------------------------------------------------------- the inventory


def normalize(text):
    text = html.unescape(text)
    for curly, straight in (("\u2019", "'"), ("\u2018", "'"), ("\u201c", '"'), ("\u201d", '"'), ("\u2026", "..."), ("\u00a0", " ")):
        text = text.replace(curly, straight)
    return re.sub(r"\s+", " ", text).strip()


class Inventory:
    def __init__(self, data):
        self.commit = data.get("commit", "?")
        self.date = data.get("commit_date", "?")
        self.repository = data.get("repository", "ankraio/ankra-frontend")
        self.labels = {normalize(label) for label in data["labels"]}
        self.blob = "\n".join(sorted(self.labels))
        self.routes = [route.strip("/").split("/") for route in data["routes"]]
        self.route_count = len(data["routes"])

    def where(self):
        return f"{self.repository} {self.commit[:12]} of {self.date[:10]}"

    def age_days(self, today=None):
        """Whole days since the commit the inventory was read from, or None when its date cannot be read."""
        try:
            read = datetime.date.fromisoformat(self.date[:10])
        except (TypeError, ValueError):
            return None
        today = today or datetime.datetime.now(datetime.timezone.utc).date()
        return (today - read).days

    def has_label(self, label):
        label = normalize(label)
        if label in self.labels:
            return True
        return re.search(r"(?<![A-Za-z0-9])" + re.escape(label) + r"(?![A-Za-z0-9])", self.blob) is not None

    def has_route(self, address):
        documented = address_segments(address)
        return any(route_matches(documented, route) for route in self.routes)


def load_inventory():
    with open(INVENTORY_PATH, encoding="utf-8") as handle:
        return Inventory(json.load(handle))


# ---------------------------------------------------------------- labels


def label_parts(span):
    """The labels in one bold span's text, split at the arrows."""
    return [part for part in IN_SPAN.split(span) if part.strip()]


def is_prose(parts):
    for part in parts:
        text = part.strip()
        if len(text.split()) > MAX_LABEL_WORDS or re.search(r"[.?!:]$", text) and not text.endswith("...") or ": " in text:
            return True
    return False


def menu_paths(line):
    """[[label, ...]] for every menu path on one prose line."""
    spans = list(BOLD.finditer(line))
    paths = []
    chain = []
    previous_end = None
    for span in spans:
        joined = previous_end is not None and BETWEEN_SPANS.match(line[previous_end : span.start()])
        if not joined:
            if len(chain) > 1 or (len(chain) == 1 and len(chain[0]) > 1):
                paths.append(chain)
            chain = []
        chain.append(label_parts(span.group(1)))
        previous_end = span.end()
    if len(chain) > 1 or (len(chain) == 1 and len(chain[0]) > 1):
        paths.append(chain)
    result = []
    for chain in paths:
        if len(chain) == 1 and is_prose(chain[0]):
            continue  # **Settings > Avura shows unavailable.** is a sentence in bold
        result.append([part.strip() for span_parts in chain for part in span_parts])
    return result


def label_words(label):
    """The text of a label to look up, or [] when there is nothing to check: a placeholder,
    an icon, inline code. A placeholder inside a label splits it into the words around it."""
    label = LINK.sub(r"\1", label).strip()
    if re.fullmatch(r"`[^`]*`", label):
        return []
    label = label.replace("`", "")
    label = re.sub(r"(?<!\.)[.:]$", "", label).strip()
    pieces = [piece.strip() for piece in PLACEHOLDER.split(label)]
    return [piece for piece in pieces if re.search(r"[A-Za-z0-9]", piece)]


def label_found(inventory, label):
    for words in label_words(label):
        if inventory.has_label(words):
            continue
        bare = re.sub(r"^[^\w(]+|[^\w)]+$", "", words)  # "+ Add", "⋯ More": an icon beside the text
        if bare and bare != words and inventory.has_label(bare):
            continue
        return False
    return True


# ---------------------------------------------------------------- addresses


def address_segments(address):
    address = re.split(r"[?#]", address, maxsplit=1)[0]
    is_prefix = address.endswith("...") or address.endswith("…")
    address = re.sub(r"(?:\.\.\.|…)$", "", address).rstrip(".,:;").rstrip("/")
    segments = [segment for segment in address.strip("/").split("/") if segment]
    out = []
    for segment in segments:
        if DYNAMIC_SEGMENT.match(segment) or UUID.match(segment) or "..." in segment or "…" in segment:
            out.append("{}")
        else:
            out.append(segment)
    if is_prefix:
        out.append("*")
    return out


def route_matches(documented, route):
    for index, segment in enumerate(route):
        if segment.startswith("[[..."):
            return True
        if segment.startswith("[..."):
            return len(documented) > index
        if index >= len(documented):
            return False
        part = documented[index]
        if part == "*":
            return True
        if segment.startswith("["):
            continue
        if part != segment:
            return False
    return len(documented) == len(route) or documented[len(route) :] == ["*"]


def extract(text):
    """[(line, kind, value, context)]: kind 'label' (value the label, context the path) or 'route'."""
    found = []
    in_fence = False
    for number, line in enumerate(text.split("\n"), start=1):
        if FENCE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            for match in CODE_ADDRESS.finditer(line):
                found.append((number, "route", trim_address(match.group(1)), match.group(0)))
            continue
        for path in menu_paths(line):
            for label in path:
                found.append((number, "label", label, " → ".join(path)))
        for match in PROSE_ADDRESS.finditer(line):
            found.append((number, "route", trim_address(match.group(1)), match.group(0)))
    return found


def trim_address(address):
    """The address without the sentence's punctuation after it; a trailing ... stays (a prefix)."""
    while address and address[-1] in ".,:;!?" and not address.endswith("..."):
        address = address[:-1]
    return address


# ---------------------------------------------------------------- pages and ratchet


def hand_written_pages():
    for directory, subdirectories, files in os.walk(ROOT):
        relative = os.path.relpath(directory, ROOT)
        subdirectories[:] = sorted(
            name
            for name in subdirectories
            if name not in SKIPPED_DIRECTORIES and os.path.normpath(os.path.join(relative, name)) != GENERATED_DIRECTORY
        )
        for name in sorted(files):
            page = os.path.normpath(os.path.join(relative, name))
            if name.endswith(".mdx") and page not in GENERATED_PAGES:
                yield page


def evaluate(pages, inventory):
    """pages: iterable of (page, text). Returns (labels checked, routes checked, findings), a
    finding being {"page", "label" or "route", "line", "path"}."""
    labels = 0
    routes = 0
    findings = []
    for page, text in pages:
        for line, kind, value, context in extract(text):
            if kind == "label":
                if not label_words(value):
                    continue
                labels += 1
                if not label_found(inventory, value):
                    findings.append({"page": page, "label": value, "line": line, "path": context})
            else:
                routes += 1
                if not inventory.has_route(value):
                    findings.append({"page": page, "route": value, "line": line, "path": context})
    return labels, routes, findings


def key(entry):
    kind = "label" if "label" in entry else "route"
    return (entry["page"], kind, entry[kind])


def load_entries(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)["entries"]


def write_baseline(entries):
    entries = sorted({key(entry): entry for entry in entries}.values(), key=key)
    lines = [
        "{",
        '  "about": "Menu labels and /next addresses that were already stale when scripts/check_portal_labels.py was introduced (2026-11-16), '
        'checked against scripts/portal-inventory.json. Tolerated until the page is fixed; remove an entry when its page no longer states it. '
        'Keyed on page and label or address, never the line.",',
        '  "entries": [',
    ]
    body = []
    for entry in entries:
        kind = "label" if "label" in entry else "route"
        body.append("    " + json.dumps({"page": entry["page"], kind: entry[kind]}, ensure_ascii=False))
    lines.append(",\n".join(body))
    lines += ["  ]", "}"]
    with open(BASELINE_PATH, "w", encoding="utf-8") as handle:
        handle.write("\n".join(line for line in lines if line) + "\n")


def annotate(level, page, line, message):
    """A GitHub annotation in Actions (shown on the pull request's diff), page:line: message elsewhere."""
    where = f"{page}:{line}" if line else page
    if os.environ.get("GITHUB_ACTIONS") == "true":
        location = f"file={page},line={line}" if line else f"file={page}"
        return f"::{level} {location}::{message}"
    return f"{where}: {message}"


def describe(finding):
    if "label" in finding:
        return f'label "{finding["label"]}" is not in the portal (path: {finding["path"]})'
    return f"{finding['route']} is not a route the portal serves"


# ---------------------------------------------------------------- self-test


def self_test():
    inventory = Inventory(
        {
            "commit": "0123456789abcdef",
            "commit_date": "2026-11-16T00:00:00Z",
            "routes": [
                "/next",
                "/next/clusters",
                "/next/clusters/new",
                "/next/clusters/[id]",
                "/next/clusters/[id]/settings",
                "/next/clusters/[id]/kubernetes/[...resource]",
                "/next/ai/tickets/[id]",
                "/next/support/[[...path]]",
            ],
            "labels": ["Settings", "General", "Danger zone", "Billing and limits", "Source control & AI review", "Add", "What’s new", "Set up…"],
        }
    )
    assert inventory.has_label("Settings") and inventory.has_label("Billing"), "whole words of a longer label"
    assert not inventory.has_label("Bill"), "never part of a word"
    assert not inventory.has_label("Danger Zone"), "case matters: the portal writes sentence case"
    assert inventory.has_label("Source control &amp; AI review") and inventory.has_label("What's new") and inventory.has_label("Set up...")
    assert label_found(inventory, "+ Add") and not label_found(inventory, "+ Remove")
    assert label_words("<cluster>") == [] and label_words("[Your cluster]") == [] and label_words("⋯") == [] and label_words("`main`") == []
    assert label_words("Upgrade to &lt;version&gt;") == ["Upgrade to"]
    assert menu_paths("Open **Settings** → **General** and then **Danger zone**.") == [["Settings", "General"]]
    assert menu_paths("Go to **Settings → General → Danger zone**") == [["Settings", "General", "Danger zone"]]
    assert menu_paths("**AI** -> **Settings > Connections**") == [["AI", "Settings", "Connections"]]
    assert menu_paths("**Settings &gt; General**") == [["Settings", "General"]]
    assert menu_paths("**Upgrade to &lt;version&gt;** and **Nothing from &lt;cluster&gt; reached Ankra**") == [], "an escaped placeholder is no arrow"
    assert menu_paths("**Settings > Avura shows unavailable, or the count is Unknown.**") == [], "a sentence in bold is prose"
    assert menu_paths("**the more specific one wins: Stack > cluster > organisation**") == []
    assert menu_paths("Click **Save**.") == []
    for address in ["/next", "/next/clusters/<cluster-id>/settings", "/next/clusters/new", "/next/clusters/3f6c2b1e-1234-4abc-9def-0123456789ab",
                    "/next/clusters/<cluster-id>/kubernetes/pods/default", "/next/ai/tickets/<ticket-id>", "/next/support", "/next/support/a/b",
                    "/next/clusters/...", "/next/clusters?provider=hetzner", "/next/clusters/<cluster-id>#addons"]:
        assert inventory.has_route(address), address
    for address in ["/next/organisation/clusters", "/next/clusters/<cluster-id>/kubernetes", "/next/clusters/<id>/settings/extra"]:
        assert not inventory.has_route(address), address
    assert address_segments("/next/clusters/new") == ["next", "clusters", "new"]
    assert not route_matches(address_segments("/next/clusters/<id>/x"), ["next", "clusters", "new", "x"]), "a placeholder never fills a literal"
    page = "\n".join(
        [
            "Open **Settings** → **General** → **Danger Zone**, then [the page](https://platform.ankra.app/next/clusters/<cluster-id>).",
            "Or go to `/next/organisation/clusters`.",
            "```text",
            "https://platform.ankra.app/next/nowhere and /next/also-not-checked",
            "```",
            "In GitHub, **Settings** → **Developer settings**.",
        ]
    )
    assert [(line, kind, value) for line, kind, value, _ in extract(page)] == [
        (1, "label", "Settings"), (1, "label", "General"), (1, "label", "Danger Zone"), (1, "route", "/next/clusters/<cluster-id>"),
        (2, "route", "/next/organisation/clusters"), (4, "route", "/next/nowhere"),
        (6, "label", "Settings"), (6, "label", "Developer settings"),
    ], extract(page)
    labels, routes, findings = evaluate([("a.mdx", page)], inventory)
    assert (labels, routes) == (5, 3), (labels, routes)
    assert [key(finding) for finding in findings] == [
        ("a.mdx", "label", "Danger Zone"), ("a.mdx", "route", "/next/organisation/clusters"), ("a.mdx", "route", "/next/nowhere"),
        ("a.mdx", "label", "Developer settings"),
    ], findings
    assert inventory.age_days(datetime.date(2026, 11, 16)) == 0
    assert inventory.age_days(datetime.date(2026, 12, 1)) == 15
    assert Inventory({"commit_date": "?", "routes": [], "labels": []}).age_days() is None
    assert Inventory({"routes": [], "labels": []}).age_days() is None
    print("portal labels self-test: ok")


# ---------------------------------------------------------------- main


def main(argv):
    if "--self-test" in argv:
        self_test()
        return 0
    strict = "--strict" in argv
    if not os.path.exists(INVENTORY_PATH):
        print(f"scripts/portal-inventory.json is missing; generate it: {REGENERATE}", file=sys.stderr)
        return 1
    inventory = load_inventory()

    def pages():
        for page in hand_written_pages():
            with open(os.path.join(ROOT, page), encoding="utf-8") as handle:
                yield page, handle.read()

    labels, routes, findings = evaluate(pages(), inventory)
    allowlist = load_entries(ALLOWLIST_PATH)
    allowed = {key(entry) for entry in allowlist}
    failing = {key(finding) for finding in findings}
    remaining = [finding for finding in findings if key(finding) not in allowed]
    if "--update" in argv:
        write_baseline(remaining)
        print(f"wrote {len({key(f) for f in remaining})} entries to scripts/portal-labels-baseline.json")
        return 0
    baseline = load_entries(BASELINE_PATH)
    baselined = {key(entry) for entry in baseline}
    new = [finding for finding in remaining if key(finding) not in baselined]
    stale = [entry for entry in allowlist + baseline if key(entry) not in failing]
    print(
        f"portal labels: {labels} menu labels and {routes} /next addresses on hand-written pages checked against "
        f"scripts/portal-inventory.json ({inventory.where()}: {len(inventory.labels)} labels, {inventory.route_count} routes); "
        f"{len(findings)} findings, {len(findings) - len(remaining)} allowlisted, {len(remaining) - len(new)} baselined, {len(new)} new"
    )
    age = inventory.age_days()
    aged = age is not None and age > INVENTORY_WARN_AFTER_DAYS
    if aged:
        print(
            annotate(
                "warning",
                "scripts/portal-inventory.json",
                None,
                f"the portal inventory was read {age} days ago ({inventory.where()}). A label or route the portal gained "
                f"since then fails this check although the page is right. Regenerate it: {REGENERATE}",
            ),
            file=sys.stderr,
        )
    if new:
        print(
            f"{len(new)} menu label(s) or address(es) the portal does not have, checked against scripts/portal-inventory.json, "
            f"read from {inventory.where()}{f', {age} days ago' if aged else ''}. Fix the page to what the portal shows. If the label or route is newer than "
            f"that commit, regenerate the inventory: {REGENERATE}. A label of another product (GitHub, Cloudflare, ...) or a "
            "name that is data goes in scripts/portal-labels-allowlist.json with a reason:",
            file=sys.stderr,
        )
        for finding in new:
            print("  " + annotate("error", finding["page"], finding["line"], describe(finding)), file=sys.stderr)
    if stale:
        level = "error" if strict else "warning"
        print(
            f"{len(stale)} allowlist or baseline entr{'y' if len(stale) == 1 else 'ies'} no longer fail{'s' if len(stale) == 1 else ''}; remove "
            f"{'it' if len(stale) == 1 else 'them'} from scripts/portal-labels-allowlist.json or "
            "scripts/portal-labels-baseline.json (--update rewrites the baseline):",
            file=sys.stderr,
        )
        for entry in stale:
            what = f'label "{entry["label"]}"' if "label" in entry else entry["route"]
            print("  " + annotate(level, entry["page"], None, f"{what} no longer fails"), file=sys.stderr)
    return 1 if new or (strict and stale) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
