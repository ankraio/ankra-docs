#!/usr/bin/env python3
"""Every cluster-API path the documentation states by hand must be a route
the cluster binary registers.

The API-reference pages render the live OpenAPI spec (docs.json points at
https://platform.ankra.app/openapi.json), so they cannot drift. Everything a
writer types is another matter: curl examples, endpoint tables, `GET /org/...`
lines in text fences and inline mentions in prose. Nothing checks those
against anything, so a renamed or removed route stays documented until a
reader hits the 404. routes.json is the cluster repo's route census: every
route the real chi router registers, produced by walking it (ankraio/cluster,
docs/route-census.md). It is the truth this script checks against. CI fetches
it before this step; locally, copy it from a cluster checkout:

    cp ../cluster/routes.json . && pnpm run check:api-paths

Without routes.json the script prints SKIPPED and passes locally, so
`pnpm run check` is never red for a file the writer has not fetched; under
CI (the CI environment variable) an absent census is a failure, because the
workflow fetched it first.

What is extracted: on every line of every hand-written .mdx/.md page (the
generated reference/cli pages are skipped), each path that starts with
/api/v1/ or /org/, bare or under https://platform.ankra.app. Placeholders
are one dynamic segment whatever their spelling: {cluster_id}, <cluster-id>,
$CLUSTER_ID, ${CLUSTER_ID} and a literal UUID. A trailing `...` means "and
whatever follows", so the path is checked as a prefix. A query string, a
fragment and trailing punctuation are dropped. When the line states exactly
one HTTP verb (an endpoint table row, a `POST /org/...` fence line, a
`curl -X DELETE` example) the method is checked too, because a page that
says GET where only POST exists is as wrong as a page that names a route
that is gone.

Matching is shape-based: a route's {param} segment accepts any documented
segment and a trailing * on a route swallows the rest, but a documented
placeholder matches only a route parameter, never a literal, because the
request a reader builds from it would 404. A path is checked as written:
/org/x and /api/v1/org/x are different routes on the cluster (the session
route and its bearer-token twin), and a curl example that shows the wrong
one sends the reader to the wrong place.

scripts/api-paths-allowlist.json is a ratchet: the entries (method, path and
file, never the line, so an edit above a mention does not churn it) that did
not resolve when the check was introduced, mostly documented-ahead endpoints
and prose that has drifted. A new entry fails, a listed entry that resolves
fails too, so the list only shrinks. Regenerate it deliberately:

    pnpm run check:api-paths -- --update

`--self-test` runs the extractor's and matcher's own assertions.
"""

import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CENSUS_PATH = os.path.join(ROOT, "routes.json")
ALLOWLIST_PATH = os.path.join(ROOT, "scripts", "api-paths-allowlist.json")
PAGE_SUFFIXES = (".mdx", ".md")
SKIPPED_DIRECTORIES = {"node_modules", ".git", ".claude", ".vale"}
GENERATED_DIRECTORIES = {os.path.join("reference", "cli")}

HOST = re.compile(r"https?://platform\.ankra\.app")
# A path right after an ellipsis ("…/api/v1/clusters/{id}/k8s") is a tail, not a route.
# An angle-bracket placeholder (<cluster-id>) is consumed whole; a stray > ends the path.
PATH = re.compile(r"(?<![\w./:…-])(/(?:api/v1|org)/(?:<[^>\s]*>|[^\s\"'`)\]|>,])*)")
VERB = re.compile(r"\b(GET|POST|PUT|PATCH|DELETE)\b")
TRAILING_NOISE = "`|'\")],;:"
UUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
PLACEHOLDER = re.compile(r"\{[^}]*\}|<[^>]*>|\$\{[^}]*\}|\$[A-Za-z_][A-Za-z0-9_]*")


def hand_written_pages():
    for directory, subdirectories, files in os.walk(ROOT):
        relative = os.path.relpath(directory, ROOT)
        subdirectories[:] = [
            name
            for name in subdirectories
            if name not in SKIPPED_DIRECTORIES
            and os.path.normpath(os.path.join(relative, name)) not in GENERATED_DIRECTORIES
        ]
        for name in sorted(files):
            if name.endswith(PAGE_SUFFIXES):
                yield os.path.normpath(os.path.join(relative, name))


def extract_mentions(text):
    """(line, method or None, path) for every API path stated on each line."""
    mentions = []
    for number, raw in enumerate(text.split("\n"), start=1):
        line = HOST.sub(" ", raw)
        paths = [match.group(1) for match in PATH.finditer(line)]
        if not paths:
            continue
        verbs = VERB.findall(line)
        method = verbs[0] if len(verbs) == 1 else None
        for path in paths:
            mentions.append((number, method, path))
    return mentions


def normalize(path):
    """The shape of a documented path: placeholders to {}, a trailing ... to *,
    query, fragment and trailing punctuation dropped."""
    path = path.split("?")[0].split("#")[0].rstrip(TRAILING_NOISE)
    # "and whatever follows" is checked before a sentence's full stop is dropped.
    is_prefix = path.endswith("...")
    if is_prefix:
        path = path[: -len("...")]
    path = path.rstrip(".").rstrip(TRAILING_NOISE)
    if is_prefix:
        path = path.rstrip("/") + "/*"
    segments = []
    for segment in path.split("/"):
        collapsed = PLACEHOLDER.sub("{}", segment)
        if collapsed == "*":
            segments.append("*")
        elif "{}" in collapsed or UUID.match(segment):
            segments.append("{}")
        else:
            segments.append(collapsed)
    normalized = "/".join(segments)
    return normalized.rstrip("/") if len(normalized) > 1 else normalized


def normalize_route(path):
    return "/".join("{}" if "{" in segment else segment for segment in path.split("/"))


def matches(documented, route):
    """Whether a normalized documented path has the shape of a normalized route."""
    call = documented.split("/")
    pattern = route.split("/")
    for index, route_segment in enumerate(pattern):
        if route_segment == "*":
            return True
        if index >= len(call):
            return False
        call_segment = call[index]
        if call_segment == "*":
            return True
        if route_segment == "{}" or route_segment == call_segment:
            continue
        return False
    return len(call) == len(pattern)


def build_index(census):
    index = {}
    for route in census["routes"]:
        index.setdefault(normalize_route(route["path"]), set()).add(route["method"].upper())
    return index


def evaluate(pages, census):
    """pages: iterable of (file, text). Returns (checked, resolved, unresolved,
    locations) where unresolved entries read "METHOD path  (file)" or
    "path  (file)"."""
    index = build_index(census)
    checked = 0
    resolved = []
    unresolved = []
    locations = {}
    for file, text in pages:
        for line, method, raw in extract_mentions(text):
            checked += 1
            shape = normalize(raw)
            routes = [candidate for candidate in index if matches(shape, candidate)]
            label = f"{method} {shape}" if method else shape
            entry = f"{label}  ({file})"
            if routes and (method is None or any(method in index[candidate] for candidate in routes)):
                resolved.append(entry)
            elif entry not in locations:
                unresolved.append(entry)
                locations[entry] = f"{file}:{line}"
    resolved.sort()
    unresolved.sort()
    return checked, resolved, unresolved, locations


def self_test():
    assert normalize("/api/v1/clusters/{cluster_id}/k8s/...") == "/api/v1/clusters/{}/k8s/*"
    assert normalize("/org/clusters/<cluster-id>/cost?days=7") == "/org/clusters/{}/cost"
    assert normalize("/api/v1/clusters/$CLUSTER_ID/sync") == "/api/v1/clusters/{}/sync"
    assert normalize("/api/v1/clusters/3f6c2b1e-1234-4abc-9def-0123456789ab/sync") == "/api/v1/clusters/{}/sync"
    assert normalize("/org/stack-profiles`.") == "/org/stack-profiles"
    assert normalize("/org/stack-profiles/") == "/org/stack-profiles"
    assert matches("/org/clusters/{}/cost", "/org/clusters/{}/cost")
    assert matches("/org/clusters/abc/cost", "/org/clusters/{}/cost")
    assert not matches("/org/clusters/{}/cost", "/org/clusters/managed/cost"), "a placeholder must not match a literal"
    assert matches("/api/v1/clusters/{}/k8s/*", "/api/v1/clusters/{}/k8s/*")
    assert matches("/api/v1/clusters/{}/k8s/*", "/api/v1/clusters/{}/k8s/pods")
    assert not matches("/org/runs", "/org/runs/{}")
    text = "\n".join(
        [
            "| `GET` | `/org/stack-profiles` | List profiles |",
            "curl -X POST https://platform.ankra.app/api/v1/clusters/<cluster_id>/sync \\",
            "Read /org/me/inbox, then POST or PUT to /org/me/inbox/read.",
            "…/api/v1/clusters/{cluster_id}/k8s",
            "See https://platform.ankra.app/organisation/clusters (a portal link).",
        ]
    )
    assert extract_mentions(text) == [
        (1, "GET", "/org/stack-profiles"),
        (2, "POST", "/api/v1/clusters/<cluster_id>/sync"),
        (3, None, "/org/me/inbox"),
        (3, None, "/org/me/inbox/read."),
    ]
    census = {
        "routes": [
            {"method": "GET", "path": "/org/stack-profiles"},
            {"method": "POST", "path": "/api/v1/clusters/{cluster_id}/sync"},
            {"method": "GET", "path": "/org/me/inbox"},
        ]
    }
    checked, resolved, unresolved, locations = evaluate([("a.mdx", text)], census)
    assert checked == 4
    assert resolved == ["/org/me/inbox  (a.mdx)", "GET /org/stack-profiles  (a.mdx)", "POST /api/v1/clusters/{}/sync  (a.mdx)"], resolved
    assert unresolved == ["/org/me/inbox/read  (a.mdx)"], unresolved
    assert locations["/org/me/inbox/read  (a.mdx)"] == "a.mdx:3"
    _, _, wrong_method, _ = evaluate([("b.mdx", "| `DELETE` | `/org/stack-profiles` |")], census)
    assert wrong_method == ["DELETE /org/stack-profiles  (b.mdx)"], wrong_method
    print("api paths self-test: ok")


def main(argv):
    if "--self-test" in argv:
        self_test()
        return 0
    update = "--update" in argv
    if not os.path.exists(CENSUS_PATH):
        where = (
            "routes.json is missing. It is the cluster route census (ankraio/cluster, docs/route-census.md); "
            "CI downloads it before this step, locally run: cp ../cluster/routes.json . && pnpm run check:api-paths"
        )
        if os.environ.get("CI") is not None:
            print(where, file=sys.stderr)
            return 1
        print(f"SKIPPED api paths: nothing was checked. {where}")
        return 0
    with open(CENSUS_PATH, encoding="utf-8") as handle:
        census = json.load(handle)
    if not census.get("routes"):
        print(f"{CENSUS_PATH} lists no routes", file=sys.stderr)
        return 1

    def pages():
        for page in hand_written_pages():
            with open(os.path.join(ROOT, page), encoding="utf-8") as handle:
                yield page, handle.read()

    checked, resolved, unresolved, locations = evaluate(pages(), census)
    print(
        f"api paths: {checked} documented mentions checked against {len(census['routes'])} registered routes; "
        f"{len(resolved)} resolved, {len(unresolved)} distinct unresolved"
    )
    if update:
        with open(ALLOWLIST_PATH, "w", encoding="utf-8") as handle:
            json.dump(unresolved, handle, indent=2)
            handle.write("\n")
        print(f"wrote {len(unresolved)} unresolved entr{'y' if len(unresolved) == 1 else 'ies'} to scripts/api-paths-allowlist.json")
        return 0
    if not os.path.exists(ALLOWLIST_PATH):
        print("scripts/api-paths-allowlist.json is missing; run once with --update to create it", file=sys.stderr)
        return 1
    with open(ALLOWLIST_PATH, encoding="utf-8") as handle:
        committed = json.load(handle)
    appeared = [entry for entry in unresolved if entry not in set(committed)]
    gone = [entry for entry in committed if entry not in set(unresolved)]
    if appeared:
        print(
            f"{len(appeared)} documented path(s) or method(s) the cluster router does not register. "
            "Fix the page, or record it deliberately with --update if the endpoint is documented ahead of its release:",
            file=sys.stderr,
        )
        for entry in appeared:
            print(f"  {entry} at {locations.get(entry, '?')}", file=sys.stderr)
    if gone:
        print(
            f"{len(gone)} allowlisted entr{'y' if len(gone) == 1 else 'ies'} now resolve (or moved); "
            "drop them so the list keeps shrinking (--update rewrites it):",
            file=sys.stderr,
        )
        for entry in gone:
            print(f"  {entry}", file=sys.stderr)
    return 1 if (appeared or gone) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
