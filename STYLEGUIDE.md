# Ankra Docs Style Guide

The goal is that a reader can trust every page: commands run as pasted, terminology is consistent, and each topic has exactly one canonical home.

## Language

- **UK English**: organisation, colour, behaviour, parameterise. Exception: keep US spelling inside code, API fields, and quoted UI labels that use it.
- **add-on** (hyphenated) in prose; `addons` only in code, YAML keys, URLs, and CLI output.
- **Stack** capitalised when referring to the Ankra concept ("deploy a Stack"); lowercase for the generic word ("the monitoring stack of tools").
- Product names as branded: Ankra, GitOps, Kubernetes, Helm, GitHub, k3s, ArgoCD.
- Dashes in prose are spaced hyphens: `word - word`. No em-dashes, and never an unspaced hyphen as a dash; it reads as a jammed word and has repeatedly been corrupted by tooling.

## Structure

Every page is one of four types. Don't mix them in one page:

| Type | Purpose | Template |
|------|---------|----------|
| Tutorial | Learn by doing, one happy path | Numbered `<Steps>`, expected outcome at each step, verification at the end |
| Guide | Accomplish a specific task | Prerequisites, steps, verification, troubleshooting |
| Concept | Understand how something works | Prose + diagrams, no step lists |
| Reference | Look up exact values | Tables, generated where possible, minimal prose |

Rules:

- Every page needs `title` and `description` frontmatter (CI enforces this).
- One canonical page per topic. Link to it; never restate setup steps on a second page.
- No REST endpoint tables in feature pages - the API Reference tab renders the live OpenAPI spec.
- The API Reference "Endpoints" sidebar is **not editable from this repo**. Mintlify generates one
  group per OpenAPI tag from the spec `docs.json` points at, so a wrong or duplicated group name is
  fixed in `ankraio/cluster` (`openapi.json` plus the convention in
  `.claude/rules/frozen-behaviour.md`), not here.
- No "Best Practices" card grids of generic advice. If a practice matters, work it into the step where it applies.
- Never fabricate AI conversation transcripts or invented metrics. Show example *prompts*, not invented responses.
- No placeholder or real customer data in examples - use `my-org/my-repo`, `my-cluster`, `<cluster-id>`.
- No referral/affiliate parameters in links.
- Vendor-neutral naming for the AI ("Ankra's AI", "the AI Assistant") except in the changelog, which is a historical record.

## Changelog

`changelog.mdx` records **one change per `<Update>`**, not one month. A month record forces a month to have a single title, and the only honest title for 109 unrelated changes is a list of 109 things - which is how the September 2026 headline reached 1,614 characters. It is also shared mutable state that every open pull request edits, so two of them collide on one line.

Every new entry is its own block, appended at the top of the file:

```mdx
<Update label="2026-09-04" tags={["Pipelines"]}>
**Stages Ankra cannot run yet are now skipped, not left pending forever.**

A pipeline declaring an unsupported stage kind used to validate cleanly, then hold its run and its concurrency group indefinitely. Validation now warns and names the stage, and the planner skips it with reason `kind_unavailable`.

[Ankra Pipelines →](/guides/ankra-pipelines)
</Update>
```

Rules:

- **`label` is the ship date, `YYYY-MM-DD`.** It renders in the left rail and creates the entry's anchor. Never a month name - a month label is a month record, which is the thing this format removes.
- **No `#` heading anywhere.** The headline is the first line of the body, bold, one complete sentence under 140 characters. There is no H1 to concatenate into, so the mega-headline cannot come back.
- **Body of at most 80 words**, saying what the reader can now do that they could not before. Not how it is implemented.
- **Exactly one link**, to the canonical docs page, as the last line.
- **One tag**, two at most, from: `Pipelines`, `Security`, `Cost`, `Clusters`, `AI`, `GitOps`, `CLI`, `API`, `Fixes`. Mintlify renders these as a filter panel beside the changelog. More tags per entry and the filter stops meaning anything.

### Three sizes

Most changes are the smallest. Without a cheap tier a one-line fix has to become an essay or go unrecorded, and it becomes an essay.

| Size | What earns it | Shape |
|------|---------------|-------|
| Line | Fixes, small improvements, an added API field | One bold-lead bullet in the week's `Also shipped` entry, about 20 words. No record of its own. |
| Entry | Something a user can now do that they could not before | Its own `<Update>`: headline, 80 words, one link. |
| Launch | A subsystem arriving - Ankra Pipelines, the Cost center | Its own `<Update>`, same 80 words, pointing at a guide that carries the depth. |

A week's small changes collect into one entry:

```mdx
<Update label="2026-09-05" tags={["Fixes"]} description="Also shipped this week">
**Clusters** - the overview now says what every cluster is. [→](/platform/clusters)
**Playground** - storage rows say what they are. [→](/platform/playground)
</Update>
```

### Depth belongs in the docs, not the changelog

If a detail is still true next quarter, it belongs on a docs page and the changelog links to it. A changelog is ordered by date, so it is the worst possible place to look something up: nobody finds `ci_run_retention_days` by remembering which month it shipped in.

This is what makes the 80-word cap lossless rather than lossy. Write the reference material onto the feature's page in the same pull request, then link to it. If an entry cannot be told in 80 words, the missing part is a docs page, not a longer entry.

### The archive

Month records up to and including **July 2026** are a genuine historical account and stay exactly as they are, `#` headings included. They are frozen: no new entry is added to an existing month record, and no new month-labelled `<Update>` is created. `scripts/check_changelog.py` enforces all of this and runs in Docs CI.

## Release status: closed beta

A feature that is behind an organisation feature flag (enabled per organisation by Ankra, off by default) is documented as **closed beta**, and every page of it says so the same way:

- Frontmatter `tag: "Closed Beta"` on the feature's canonical page *and* on every page that only works with the feature enabled (its credentials page, reference page, sub-feature guides).
- A `<Warning>` at the top of the page, before the first `<Note>`, opening with `**Closed beta.**` and carrying the enablement fact and the support link:

  ```mdx
  <Warning>
  **Closed beta.** <Feature> is in closed beta. The workflow is stable but the surface may still change, and it is enabled per organisation on request. [Contact support](/platform/support) to have it turned on for your organisation.
  </Warning>
  ```

  A sub-feature page says which feature it belongs to instead: `**Closed beta.** Branch demos are part of [Applications](/concepts/applications), which is in closed beta …`. A page that describes what the product does while the flag is dark (an error message, a hidden menu entry) keeps that in the same block.
- A gated *section* of an otherwise generally available page gets the same `<Warning>` at the top of the section, not a page tag.
- Cards, tables and headings that name the feature append `(Closed Beta)` to the name, as the landing page does for Applications.
- Never use "beta", "preview", "experimental", "rolling out" or "coming soon" as a status label - the only statuses are closed beta and generally available. When a feature becomes generally available, remove the tag, the `<Warning>` and the suffixes in the same PR that announces it in the changelog.

## CLI version requirements

Every page that shows an `ankra` command states the CLI version the reader needs, with the shared component - never in prose, so the wording and the upgrade path stay identical everywhere:

```mdx
import { CliVersion } from "/snippets/cli-version.jsx";

<CliVersion since="0.12.0" />
```

- `since` is the first **stable** release that shipped the newest command or flag the page relies on - "v0.12.0 or later" - taken from the ankra-cli tags, not guessed. `ankra-cli/tools/gendocs` regenerates `reference/cli/` from the same tree, so the narrative pages carry the requirement and the reference stays generated.
- Place it once per page, immediately above the first `ankra` command *example* - the first code block, `<Tab title="CLI">` or command table. Inside a `<CodeGroup>` it goes above the group. The import goes directly after the frontmatter. A passing mention in prose (a `<Note>`, a "Related" bullet) needs no marker; if the mention is really an instruction, turn it into a code block and mark that.
- When one section needs a newer release than the rest of the page, give that section its own `<CliVersion since="0.13.0" command="cluster debug create" />` - the `command` prop names what the newer requirement is for, so the page baseline is not inflated by one command.
- `snippets/cli-version.jsx` holds `latestStableCli`. A `since` above it renders the pre-release hint (enable the beta channel before upgrading) automatically, so a page can document an rc-only command truthfully; bump `latestStableCli` in the same PR that bumps `integrations/ankra-cli.mdx` and `integrations/ankra-cli-changelog.mdx` for a stable release, and the hints disappear on their own.
- `note` is optional free text for a genuine caveat (a flag that needs a newer agent, a provider-specific command), one sentence.

## Code blocks

- Shell fences are `bash`. Use `bash CLI` / `bash cURL` titles inside `<CodeGroup>`.
- Commands must be copy-pasteable. Long flags use `--`; continuation lines are indented two spaces.
- Pin chart versions in examples (`chart_version: 0.49.1`), never `latest`.
- YAML examples must parse. List items keep their `- ` markers.
- Mermaid arrows are `-->` (CI rejects single `->`).
- Placeholders use angle brackets: `<cluster-id>`, `<your-token>`.

## Screenshots and media

- Screenshots live in `images/` and are captured at 1440x900, light and dark variants where the UI differs.
- Prefer the automated screenshot pipeline (portal e2e `docs-screenshots` spec) over manual captures so images stay current.
- Every visual feature page (Stack Builder, dashboard map, Resource Map, logs) should have at least one screenshot or short clip.

## Voice

- Direct and factual. Say what the product does, not how revolutionary it is.
- Second person ("you"), present tense, active voice.
- State limits honestly (irreversible actions, unsupported paths) in `<Warning>` blocks near the action they affect.
