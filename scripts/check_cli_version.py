#!/usr/bin/env python3
"""Fail when latestStableCli in snippets/cli-version.jsx is behind the newest
stable ankra-cli release.

<CliVersion since="X.Y.Z"> tells readers a command is "a pre-release today,
so enable the beta channel before upgrading" whenever since is above
latestStableCli. The constant is bumped by hand and nothing failed when a
release left it behind, so commands that had shipped read as pre-releases on
live pages until someone noticed (ankra-y3hfc).

The newest stable release is ankraio/ankra-cli's releases/latest: the most
recent release that is neither a draft nor a pre-release, and the endpoint
`ankra upgrade` (beta channel off) and install.sh install from, so the
constant is held to what a reader actually gets.

  behind  error, exit 1: set latestStableCli to that release.
  ahead   warning, exit 0: a coordinated release cut bumps the docs before
          the tag exists, and the check must not block the cut.
  equal   OK, exit 0.
  The release cannot be read: error, exit 1. A ratchet that passes without
  its input is switched off without anyone noticing.

GH_TOKEN, when set, authenticates the request. CI passes the workflow token:
unauthenticated calls get 60 an hour per IP address, shared with every other
job on the runner's address. Locally:

    GH_TOKEN="$(gh auth token)" python3 scripts/check_cli_version.py

Usage: check_cli_version.py [path]   (defaults to snippets/cli-version.jsx)
"""

import json
import os
import re
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_TARGET = os.path.join(ROOT, "snippets", "cli-version.jsx")
RELEASE_URL = "https://api.github.com/repos/ankraio/ankra-cli/releases/latest"
CONSTANT = re.compile(r'\blatestStableCli\s*=\s*"([^"]*)"')
VERSION = re.compile(r"([0-9]+)\.([0-9]+)\.([0-9]+)")


def parse_version(text):
    """(major, minor, patch) from X.Y.Z. Anything else raises ValueError: a
    pre-release suffix, and a leading v, which the component's parseInt
    reads as 0. The caller strips the v from the release tag."""
    match = VERSION.fullmatch(text)
    if not match:
        raise ValueError(f"{text!r} is not a version of the form X.Y.Z")
    return tuple(int(part) for part in match.groups())


def newest_stable_tag():
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "ankra-docs scripts/check_cli_version.py",
    }
    token = os.environ.get("GH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(RELEASE_URL, headers=headers)
    # urllib waits forever by default: a stalled connection would hold the
    # job until the runner's six-hour limit instead of failing here.
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.load(response)["tag_name"]


def main(argv) -> int:
    path = argv[1] if len(argv) > 1 else DEFAULT_TARGET
    full = os.path.abspath(path)
    rel = os.path.relpath(full, ROOT) if full.startswith(ROOT + os.sep) else path
    with open(path, encoding="utf-8") as f:
        text = f.read()
    match = CONSTANT.search(text)
    if not match:
        print(
            f'::error::{rel}: no latestStableCli = "X.Y.Z" found, so nothing holds the '
            "CliVersion markers to the newest stable ankra-cli release."
        )
        return 1
    line = text.count("\n", 0, match.start()) + 1
    where = f"{rel}:{line}"
    constant = match.group(1)
    try:
        ours = parse_version(constant)
    except ValueError as error:
        print(f"::error::{where}: latestStableCli {error}; it must name a stable release.")
        return 1

    try:
        tag = newest_stable_tag()
    except (OSError, ValueError) as error:
        # OSError: an HTTP error status, a refused connection, a timeout.
        # ValueError: a body that is not JSON.
        print(
            f"::error::Could not read the newest stable ankra-cli release from {RELEASE_URL}: {error}. "
            "Not a docs drift: re-run the job. If it keeps failing, a 401 means GH_TOKEN was rejected, "
            "a 403 or 429 a rate limit (set GH_TOKEN), anything else that the endpoint changed."
        )
        return 1
    try:
        newest = parse_version(tag.removeprefix("v"))
    except ValueError:
        print(
            f"::error::ankraio/ankra-cli's latest release is tagged {tag!r}, not vX.Y.Z; "
            "a stable release must carry a vX.Y.Z tag."
        )
        return 1

    wanted = ".".join(str(part) for part in newest)
    if ours < newest:
        print(
            f'::error::{where}: latestStableCli is "{constant}", behind the newest stable ankra-cli release '
            f"{tag}, so CliVersion markers above {constant} tell readers a released command is a pre-release. "
            f'Set it to "{wanted}".'
        )
        return 1
    if ours > newest:
        print(
            f'::warning::{where}: latestStableCli is "{constant}", ahead of the newest stable ankra-cli release '
            f"{tag}, so CliVersion markers up to {constant} render as released. Expected only while a "
            f'coordinated release cut waits for its tag; otherwise set it back to "{wanted}".'
        )
        return 0
    print(f"OK: latestStableCli {constant} is the newest stable ankra-cli release ({tag}).")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
