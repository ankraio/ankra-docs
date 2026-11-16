#!/usr/bin/env python3
"""Every `ankra` command a hand-written page shows must be a command the CLI
has, called with flags that command takes.

A page that tells the reader to run a command the CLI no longer has, or a
flag it never had, fails only when someone pastes it. The 2026-11-15 audit
found such commands on live pages and nothing in CI that would have caught
them (ankra-4xh2sn.3).

The truth is already in this repository: reference/cli/*.mdx is generated
from the CLI's command tree by ankra-cli tools/gendocs. Every command, group
or runnable, is one `## ankra <path>` section; a runnable one carries its
usage line (a one-line fence `ankra <path> ...`) and a flag table, and
reference/cli/index.mdx lists the global flags every command accepts. So this
check needs no other repository, and it is exactly as current as
reference/cli: a page that documents a command before the reference is
regenerated for its release fails until then (allowlist it, see below).

What is read: every hand-written .mdx page (reference/cli, changelog.mdx and
integrations/ankra-cli-changelog.mdx are records, not instructions, and are
skipped). In shell fences (bash, sh, shell, zsh, console, terminal, text,
powershell, or no language) each `ankra` in command position: at the start
of a line or after a prompt, `;`, `&&`, `||`, `|`, `(`, `$(`, a backtick, an
assignment such as ANKRA_ORG=x, or sudo, env, exec, time, nohup, if, then,
do, else. So `kubectl -n ankra get pods` and `brew upgrade ankra` are not
commands, and neither is anything after a #. Lines ending in a backslash are
joined. In prose, inline code read the same way (`ankra cluster list`).

What is checked: the words after `ankra` must walk down the command tree to
a section; a word that is not a subcommand ends the walk when the command
there is runnable (it is an argument) and fails when it is a group. Every
--flag and -f after the walk must be in the flag table of the command or of
one of its parents (a group's flags are persistent), or be a global flag,
--help or -h. A global flag may also come before the subcommand. A
placeholder where a subcommand goes (`ankra cluster <provider> stop`) passes
when some subcommand in its place makes the command valid; `a|b` where a
subcommand goes (`ankra cluster managed discover|import`) must be valid for
every alternative. Everything after a bare -- belongs to another program.

Two files make it a ratchet, both keyed on page and command text, never on
line numbers, so an edit above a command does not churn them:

  scripts/cli-commands-allowlist.json  false alarms, each with its reason: a
      plugin that is only an example, an alias the reference does not list,
      a command documented ahead of the release that regenerates the
      reference. Hand-edited.
  scripts/cli-commands-baseline.json   commands that were already wrong when
      this check was introduced. They are tolerated until the page is fixed;
      nothing new may join them except deliberately with --update.

A finding in neither file fails. An entry in either file that no longer
fails is reported so it can be removed: a warning, an error under --strict.

    python3 scripts/check_cli_commands.py              # check
    python3 scripts/check_cli_commands.py --strict     # stale entries fail too
    python3 scripts/check_cli_commands.py --update     # rewrite the baseline from what fails now
    python3 scripts/check_cli_commands.py --tree <ankra-cli>/docs/command-tree.json
        # prove the runnable sections equal a CLI command tree (ankra-cli's own census)
    python3 scripts/check_cli_commands.py --self-test
"""

import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REFERENCE_DIRECTORY = os.path.join("reference", "cli")
ALLOWLIST_PATH = os.path.join(ROOT, "scripts", "cli-commands-allowlist.json")
BASELINE_PATH = os.path.join(ROOT, "scripts", "cli-commands-baseline.json")
SKIPPED_DIRECTORIES = {"node_modules", ".git", ".claude", ".vale", ".mr-worktrees"}
GENERATED_PAGES = {"changelog.mdx", os.path.join("integrations", "ankra-cli-changelog.mdx")}
SHELL_LANGUAGES = {"", "bash", "sh", "shell", "zsh", "console", "terminal", "shellscript", "text", "powershell"}
PREFIX_WORDS = {"sudo", "env", "exec", "time", "nohup", "command", "if", "then", "elif", "else", "do", "while", "until", "!"}
ALWAYS_ALLOWED = {"--help", "-h"}
ROOT_FLAGS = {"--version"}

FENCE = re.compile(r"^\s*```(\S*)")
HEADING = re.compile(r"^## (ankra(?: [^\s].*)?)$")
FLAG_ROW = re.compile(r"^\| (`-[^|]*)\|")
FLAG_NAME = re.compile(r"`(--?[A-Za-z0-9][A-Za-z0-9-]*)`")
INLINE_CODE = re.compile(r"`([^`\n]+)`")
ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
PROMPT = re.compile(r"^\s*(?:\$|%|PS>)\s+")
SUBCOMMAND_WORD = re.compile(r"[a-z][a-z0-9-]*")
LONG_FLAG = re.compile(r"--[a-z0-9][a-z0-9-]*")
SHORT_FLAG = re.compile(r"-[a-zA-Z]")
PLACEHOLDER = re.compile(r"^(?:<[^<>]+>|\{[^{}]+\}|\[[^\[\]]+\]|\$\{?[A-Za-z_][A-Za-z0-9_]*\}?|\.\.\.|…)$")


# ---------------------------------------------------------------- the reference


class Reference:
    """The command tree as reference/cli documents it."""

    def __init__(self, sections, runnable, global_flags, version):
        self.sections = sections  # path -> set of flags in its table
        self.runnable = runnable  # paths with a usage line
        self.global_flags = global_flags
        self.version = version
        self.children = {}
        for path in sections:
            parent, _, name = path.rpartition(" ")
            if parent:
                self.children.setdefault(parent, set()).add(name)
        self.children.setdefault("ankra", set())

    def allowed_flags(self, path):
        allowed = set(ALWAYS_ALLOWED) | self.global_flags
        if path == "ankra":
            allowed |= ROOT_FLAGS
        parts = path.split(" ")
        for length in range(2, len(parts) + 1):
            allowed |= self.sections.get(" ".join(parts[:length]), set())
        return allowed


def parse_reference(pages):
    """pages: iterable of (file name, text) for reference/cli/*.mdx."""
    sections = {}
    fences = {}
    global_flags = set()
    version = None
    for _, text in pages:
        current = None
        fence = None
        in_global_table = False
        for line in text.split("\n"):
            if fence is not None:
                if FENCE.match(line):
                    if current:
                        fences[current].append(fence)
                    fence = None
                else:
                    fence.append(line)
                continue
            if FENCE.match(line):
                fence = []
                continue
            heading = HEADING.match(line)
            if heading:
                current = heading.group(1).strip()
                sections[current] = set()
                fences[current] = []
                in_global_table = False
                continue
            if line.startswith("## "):
                current = None
                in_global_table = line.strip() == "## Global Flags"
                continue
            if version is None:
                found = re.search(r"generated from ankra CLI \*\*v([0-9][^*]*)\*\*", line)
                if found:
                    version = found.group(1)
            row = FLAG_ROW.match(line)
            if row:
                flags = set(FLAG_NAME.findall(row.group(1)))
                if current:
                    sections[current] |= flags
                elif in_global_table:
                    global_flags |= flags
    runnable = set()
    for path, blocks in fences.items():
        for block in blocks:
            lines = [line.strip() for line in block if line.strip()]
            if len(lines) != 1 or not (lines[0] == path or lines[0].startswith(path + " ")):
                continue
            rest = lines[0][len(path) :].split()
            if rest and f"{path} {rest[0]}" in sections:
                continue  # a group's long text naming one of its subcommands
            runnable.add(path)
            break
    return Reference(sections, runnable, global_flags, version)


def load_reference():
    directory = os.path.join(ROOT, REFERENCE_DIRECTORY)
    pages = []
    for name in sorted(os.listdir(directory)):
        if name.endswith(".mdx"):
            with open(os.path.join(directory, name), encoding="utf-8") as handle:
                pages.append((name, handle.read()))
    return parse_reference(pages)


# ---------------------------------------------------------------- extraction


def strip_comment(line):
    """The line without a shell comment: an unquoted # at the start or after a blank."""
    quote = None
    index = 0
    while index < len(line):
        character = line[index]
        if quote:
            if character == "\\" and quote == '"':
                index += 1
            elif character == quote:
                quote = None
        elif character == "\\":
            index += 1
        elif character in "'\"":
            quote = character
        elif character == "#" and (index == 0 or line[index - 1] in " \t"):
            return line[:index]
        index += 1
    return line


def substitutions(line):
    """(outer line, [inner command lines]): $( ... ) and `...` are commands of their own."""
    inner = []
    out = []
    index = 0
    while index < len(line):
        if line.startswith("$(", index):
            depth = 1
            end = index + 2
            while end < len(line) and depth:
                if line[end] == "(":
                    depth += 1
                elif line[end] == ")":
                    depth -= 1
                end += 1
            body = line[index + 2 : end - 1] if depth == 0 else line[index + 2 :]
            nested_outer, nested_inner = substitutions(body)
            inner.append(nested_outer)
            inner.extend(nested_inner)
            out.append("SUBSTITUTION")
            index = end
        elif line[index] == "`":
            end = line.find("`", index + 1)
            end = len(line) if end < 0 else end
            inner.append(line[index + 1 : end])
            out.append("SUBSTITUTION")
            index = end + 1
        else:
            out.append(line[index])
            index += 1
    return "".join(out), inner


def shell_tokens(line):
    """Words and operators of one shell line: [(kind, text, start, end)], kind 'word' or 'op'.
    Quotes are honoured, <placeholder> is a word, a|b between words is one word (an
    alternative, not a pipe), a redirection and its target are dropped."""
    tokens = []
    word = []
    start = None
    index = 0
    skip_next_word = False

    def flush(end):
        nonlocal word, start, skip_next_word
        if start is not None:
            if skip_next_word:
                skip_next_word = False
            else:
                tokens.append(("word", "".join(word), start, end))
        word = []
        start = None

    length = len(line)
    while index < length:
        character = line[index]
        if character in " \t":
            flush(index)
            index += 1
            continue
        if start is None:
            start = index
        if character == "'":
            end = line.find("'", index + 1)
            end = length if end < 0 else end
            word.append(line[index + 1 : end])
            index = end + 1
        elif character == '"':
            end = index + 1
            while end < length and line[end] != '"':
                end += 2 if line[end] == "\\" else 1
            word.append(line[index + 1 : min(end, length)])
            index = end + 1
        elif character == "\\":
            word.append(line[index + 1 : index + 2])
            index += 2
        elif character == "<" and re.match(r"<[A-Za-z_][^<>\s]*>", line[index:]):
            placeholder = re.match(r"<[A-Za-z_][^<>\s]*>", line[index:]).group(0)
            word.append(placeholder)
            index += len(placeholder)
        elif (
            character == "|"
            and word
            and re.match(r"[a-z0-9-]", word[-1][-1:] or " ")
            and index + 1 < length
            and line[index + 1].isalpha()
        ):
            word.append("|")
            index += 1
        elif line.startswith(("&&", "||"), index):
            flush(index)
            tokens.append(("op", line[index : index + 2], index, index + 2))
            index += 2
        elif character in ";|&()":
            flush(index)
            tokens.append(("op", character, index, index + 1))
            index += 1
        elif character in "<>":
            if word and "".join(word).isdigit():
                word = []
                start = None
            else:
                flush(index)
            redirection = re.match(r"(?:<<<|<<-?|>>|>&|>\||<&|<|>)", line[index:]).group(0)
            index += len(redirection)
            if not re.match(r"\s*&?\d", line[index:]) or redirection in ("<<", "<<-", "<<<"):
                skip_next_word = True
            else:
                index += len(re.match(r"\s*&?\d+", line[index:]).group(0))
        else:
            word.append(character)
            index += 1
    flush(length)
    return tokens


def invocations_in_line(line):
    """[(text, words)] for every `ankra` command in one shell line; words exclude `ankra`."""
    line = strip_comment(PROMPT.sub("", line, count=1))
    outer, inner = substitutions(line)
    found = []
    for command_line in [outer] + inner:
        tokens = shell_tokens(command_line)
        position = True
        index = 0
        while index < len(tokens):
            kind, text, start, _ = tokens[index]
            if kind == "op":
                position = True
                index += 1
                continue
            if position and (ASSIGNMENT.match(text) or text in PREFIX_WORDS):
                index += 1
                continue
            if position and text == "ankra":
                end = index + 1
                while end < len(tokens) and tokens[end][0] == "word":
                    end += 1
                words = [token[1] for token in tokens[index + 1 : end]]
                raw = command_line[start : tokens[end - 1][3]]
                found.append((re.sub(r"\s+", " ", raw).strip(), words))
                index = end
                position = False
                continue
            position = False
            index += 1
    return found


def extract_invocations(text):
    """[(line number, command text, words)] for every `ankra` command a page shows."""
    found = []
    in_fence = False
    shell = False
    pending = None
    pending_line = 0
    for number, line in enumerate(text.split("\n"), start=1):
        fence = FENCE.match(line)
        if fence:
            if not in_fence:
                in_fence = True
                shell = fence.group(1).lower().split("{")[0] in SHELL_LANGUAGES
            else:
                in_fence = False
                pending = None
            continue
        if in_fence:
            if not shell:
                continue
            if pending is not None:
                line = pending + " " + line.strip()
            if line.rstrip().endswith("\\"):
                if pending is None:
                    pending_line = number
                pending = line.rstrip()[:-1]
                continue
            start_line = pending_line if pending is not None else number
            pending = None
            for command, words in invocations_in_line(line):
                found.append((start_line, command, words))
            continue
        for match in INLINE_CODE.finditer(line):
            if re.search(r"(?<![\w./@!=-])ankra(?![\w./@-])", match.group(1)):
                for command, words in invocations_in_line(match.group(1)):
                    found.append((number, command, words))
    return found


# ---------------------------------------------------------------- resolution


def is_placeholder(word):
    """<provider>, {id}, [name], $VAR, ${VAR}, CLUSTER_ID, ... and a $( ) substitution."""
    return bool(PLACEHOLDER.match(word) or re.fullmatch(r"[A-Z][A-Z0-9_]*", word)) or word == "SUBSTITUTION"


def alternatives(word):
    parts = word.strip("<>{}[]()").split("|")
    if len(parts) > 1 and all(SUBCOMMAND_WORD.fullmatch(part) for part in parts):
        return parts
    return None


def check_flags(reference, path, words):
    allowed = reference.allowed_flags(path)
    problems = []
    for word in words:
        if word == "--":
            break
        name = word.split("=", 1)[0]
        if word.startswith("[") and word.endswith("]"):
            name = word[1:-1].split("=", 1)[0].split(" ")[0]
        if LONG_FLAG.fullmatch(name) or SHORT_FLAG.fullmatch(name):
            if name not in allowed:
                problems.append(f'{name} is not a flag of "{path}"')
    return problems


def resolve(reference, words, path="ankra", index=0):
    """Problems with `ankra <words>`; empty when the CLI accepts it."""
    while index < len(words):
        word = words[index]
        if word == "--":
            return []
        if word.split("=", 1)[0] in reference.global_flags:
            index += 1 if "=" in word else 2  # a global flag and its value, before or after the subcommand
            continue
        if word.startswith("-"):
            return check_flags(reference, path, words[index:])
        children = reference.children.get(path, set())
        options = alternatives(word)
        if options and all(option in children for option in options):
            problems = []
            for option in options:
                problems.extend(resolve(reference, words, f"{path} {option}", index + 1))
            return problems
        if word in children:
            path = f"{path} {word}"
            index += 1
            continue
        if path == "ankra" and word == "help":
            return []
        if (is_placeholder(word) or options) and children:
            best = None
            for child in sorted(children):
                problems = resolve(reference, words, f"{path} {child}", index + 1)
                if not problems:
                    return []
                if best is None or len(problems) < len(best[1]):
                    best = (child, problems)
            if path in reference.runnable and not check_flags(reference, path, words[index + 1 :]):
                return []  # the placeholder is an argument of a runnable group
            return [f'no subcommand of "{path}" in place of {word} makes this valid (closest, {path} {best[0]}: {best[1][0]})']
        if path == "ankra":
            return [f'"ankra {word}" is not a command (reference/cli/index.mdx lists every command)']
        if path not in reference.runnable and SUBCOMMAND_WORD.fullmatch(word):
            return [f'"{path}" has no subcommand "{word}"']
        # an argument of a runnable command: only flags remain to check
        return check_flags(reference, path, words[index + 1 :])
    return []


# ---------------------------------------------------------------- pages and ratchet


def hand_written_pages():
    for directory, subdirectories, files in os.walk(ROOT):
        relative = os.path.relpath(directory, ROOT)
        subdirectories[:] = sorted(
            name
            for name in subdirectories
            if name not in SKIPPED_DIRECTORIES and os.path.normpath(os.path.join(relative, name)) != REFERENCE_DIRECTORY
        )
        for name in sorted(files):
            page = os.path.normpath(os.path.join(relative, name))
            if name.endswith(".mdx") and page not in GENERATED_PAGES:
                yield page


def evaluate(pages, reference):
    """pages: iterable of (page, text). Returns (checked, findings) where a finding is
    {"page", "command", "line", "problem"}."""
    checked = 0
    findings = []
    for page, text in pages:
        for line, command, words in extract_invocations(text):
            checked += 1
            problems = resolve(reference, words)
            if problems:
                findings.append({"page": page, "command": command, "line": line, "problem": problems[0]})
    return checked, findings


def key(entry):
    return (entry["page"], entry["command"])


def load_entries(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)["entries"]


def write_baseline(entries):
    entries = sorted({key(entry): entry for entry in entries}.values(), key=key)
    lines = [
        "{",
        '  "about": "Commands that already failed scripts/check_cli_commands.py when it was introduced (2026-11-16). '
        'Tolerated until the page is fixed; remove an entry when its page no longer shows the command. Keyed on page and command, never the line.",',
        '  "entries": [',
    ]
    body = [
        "    " + json.dumps({"page": entry["page"], "command": entry["command"], "problem": entry["problem"]}, ensure_ascii=False)
        for entry in entries
    ]
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


def compare_tree(reference, tree_path):
    with open(tree_path, encoding="utf-8") as handle:
        tree = set(json.load(handle)["commands"])
    closure = set()
    for command in tree:
        parts = command.split(" ")
        for length in range(2, len(parts) + 1):
            closure.add(" ".join(parts[:length]))
    headings = set(reference.sections)
    print(
        f"reference/cli (ankra CLI v{reference.version}): {len(headings)} sections, {len(reference.runnable)} runnable; "
        f"{tree_path}: {len(tree)} runnable commands"
    )
    report = [
        ("runnable sections not in the tree", sorted(reference.runnable - tree)),
        ("tree commands with no runnable section", sorted(tree - reference.runnable)),
        ("sections that are no prefix of a tree command (groups whose children are all hidden or deprecated)", sorted(headings - closure)),
        ("tree prefixes with no section", sorted(closure - headings)),
    ]
    for title, items in report:
        print(f"  {title}: {len(items)}")
        for item in items:
            print(f"    {item}")
    return 0 if not report[0][1] and not report[1][1] else 1


# ---------------------------------------------------------------- self-test


def self_test():
    reference = parse_reference(
        [
            (
                "index.mdx",
                "This reference is generated from ankra CLI **v9.9.9**.\n\n## Commands\n\n| [ankra cluster](/x) | y |\n\n"
                "## Global Flags\n\n| Flag | Default | Description |\n|---|---|---|\n| `--org` |   | org |\n",
            ),
            (
                "cluster.mdx",
                "\n".join(
                    [
                        "## ankra cluster",
                        "",
                        "Cluster operations.",
                        "",
                        "```bash",
                        "ankra cluster list",
                        "```",
                        "",
                        "| `--cluster` |   | persistent |",
                        "## ankra cluster list",
                        "```bash",
                        "ankra cluster list [flags]",
                        "```",
                        "**Flags**",
                        "| `-o`, `--output` |   | Output format |",
                        "## ankra cluster hetzner",
                        "## ankra cluster hetzner stop",
                        "```bash",
                        "ankra cluster hetzner stop <cluster> [flags]",
                        "```",
                        "| `--mode` |   | pause |",
                        "## ankra cluster ovh",
                        "## ankra cluster ovh stop",
                        "```bash",
                        "ankra cluster ovh stop <cluster> [flags]",
                        "```",
                        "## ankra cluster managed",
                        "## ankra cluster managed discover",
                        "```bash",
                        "ankra cluster managed discover [flags]",
                        "```",
                        "| `--provider` |   | p |",
                        "## ankra cluster managed import",
                        "```bash",
                        "ankra cluster managed import [flags]",
                        "```",
                        "## ankra chat",
                        "```bash",
                        "ankra chat [question] [flags]",
                        "```",
                        "| `--cluster` |   | c |",
                        "## ankra chat actions",
                        "```bash",
                        "ankra chat actions [flags]",
                        "```",
                    ]
                ),
            ),
        ]
    )
    assert reference.version == "9.9.9"
    assert reference.global_flags == {"--org"}, reference.global_flags
    assert reference.runnable == {
        "ankra cluster list", "ankra cluster hetzner stop", "ankra cluster ovh stop",
        "ankra cluster managed discover", "ankra cluster managed import", "ankra chat", "ankra chat actions",
    }, reference.runnable

    def problems(command):
        found = invocations_in_line(command)
        assert len(found) == 1, (command, found)
        return resolve(reference, found[0][1])

    assert problems("ankra cluster list -o json") == []
    assert problems("ankra --org acme cluster list") == [], "a global flag may come first"
    assert problems("ankra cluster list --cluster x") == [], "a group's flag is inherited"
    assert problems("ankra cluster list --wide") == ['--wide is not a flag of "ankra cluster list"']
    assert problems("ankra clusters list") == ['"ankra clusters" is not a command (reference/cli/index.mdx lists every command)']
    assert problems("ankra cluster lists") == ['"ankra cluster" has no subcommand "lists"']
    assert problems('ankra chat "why is it down?" --cluster prod') == [], "an argument of a runnable command"
    assert problems("ankra cluster <provider> stop <cluster> --mode pause") == [], "hetzner takes --mode"
    assert problems("ankra cluster <provider> stop <cluster> --force")[0].startswith('no subcommand of "ankra cluster" in place of <provider>')
    assert problems("ankra cluster managed discover|import") == []
    assert problems("ankra cluster managed discover|import --provider aks") == ['--provider is not a flag of "ankra cluster managed import"']
    assert problems("ankra cluster list -- --anything") == []
    assert problems("ankra --version") == []
    page = "\n".join(
        [
            "Run `ankra cluster list` or `kubectl -n ankra get pods`.",
            "```bash",
            "kubectl get deployment -n ankra ankra-agent -o json",
            "brew upgrade ankra   # then ankra location",
            "ANKRA_ORG=acme ankra cluster list \\",
            "  --output json | jq .",
            'export T="$(ankra chat actions)"',
            "if ankra cluster lists; then echo ok; fi",
            "```",
            "```yaml",
            "run: ankra nothing-checked-here",
            "```",
        ]
    )
    assert [(line, command) for line, command, _ in extract_invocations(page)] == [
        (1, "ankra cluster list"),
        (5, "ankra cluster list --output json"),
        (7, "ankra chat actions"),
        (8, "ankra cluster lists"),
    ], extract_invocations(page)
    checked, findings = evaluate([("a.mdx", page)], reference)
    assert checked == 4 and [(f["line"], f["command"]) for f in findings] == [(8, "ankra cluster lists")], findings
    print("cli commands self-test: ok")


# ---------------------------------------------------------------- main


def main(argv):
    if "--self-test" in argv:
        self_test()
        return 0
    reference = load_reference()
    if not reference.sections or not reference.runnable:
        print("reference/cli holds no `## ankra` sections; nothing to check against", file=sys.stderr)
        return 1
    if "--tree" in argv:
        return compare_tree(reference, argv[argv.index("--tree") + 1])
    strict = "--strict" in argv

    def pages():
        for page in hand_written_pages():
            with open(os.path.join(ROOT, page), encoding="utf-8") as handle:
                yield page, handle.read()

    checked, findings = evaluate(pages(), reference)
    allowlist = load_entries(ALLOWLIST_PATH)
    allowed = {key(entry) for entry in allowlist}
    failing = {key(finding) for finding in findings}
    remaining = [finding for finding in findings if key(finding) not in allowed]
    if "--update" in argv:
        write_baseline(remaining)
        print(f"wrote {len({key(f) for f in remaining})} entries to scripts/cli-commands-baseline.json")
        return 0
    baseline = load_entries(BASELINE_PATH)
    baselined = {key(entry) for entry in baseline}
    new = [finding for finding in remaining if key(finding) not in baselined]
    stale = [entry for entry in allowlist + baseline if key(entry) not in failing]
    print(
        f"cli commands: {checked} invocations on hand-written pages checked against reference/cli "
        f"(ankra CLI v{reference.version}: {len(reference.runnable)} commands, {len(reference.sections)} sections); "
        f"{len(findings)} findings, {len(findings) - len(remaining)} allowlisted, "
        f"{len(remaining) - len(new)} baselined, {len(new)} new"
    )
    if new:
        print(
            f"{len(new)} command(s) the CLI does not have as written. reference/cli/ is the truth (generated from "
            f"ankra CLI v{reference.version}). Fix the page; if the command ships after v{reference.version}, it "
            "passes once reference/cli is regenerated for that release, until then add it to "
            "scripts/cli-commands-allowlist.json with a reason:",
            file=sys.stderr,
        )
        for finding in new:
            print("  " + annotate("error", finding["page"], finding["line"], f"`{finding['command']}`: {finding['problem']}"), file=sys.stderr)
    if stale:
        level = "error" if strict else "warning"
        print(
            f"{len(stale)} allowlist or baseline entr{'y' if len(stale) == 1 else 'ies'} no longer fail{'s' if len(stale) == 1 else ''}; remove "
            f"{'it' if len(stale) == 1 else 'them'} from scripts/cli-commands-allowlist.json or "
            "scripts/cli-commands-baseline.json (--update rewrites the baseline):",
            file=sys.stderr,
        )
        for entry in stale:
            print("  " + annotate(level, entry["page"], None, f"`{entry['command']}` no longer fails"), file=sys.stderr)
    return 1 if new or (strict and stale) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
