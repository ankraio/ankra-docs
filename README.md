# Ankra Documentation

Public documentation for the [Ankra platform](https://platform.ankra.app), published at [docs.ankra.ai](https://docs.ankra.ai) and built with [Mintlify](https://mintlify.com).

## Local development

```bash
npm install
npm run dev        # live preview at http://localhost:3000
```

## Checks

Every PR runs these checks in CI (`.github/workflows/docs-ci.yml`). Run them locally before pushing:

```bash
npm run check              # all of the below
npm run check:nav          # every page reachable from docs.json, no dead nav entries
npm run check:frontmatter  # every page has title + description
npm run check:snippets     # code blocks free of corruption patterns, YAML parses, mermaid arrows valid
npm run check:links        # Mintlify broken-link checker
```

Prose style is linted with [Vale](https://vale.sh) (`vale .`) using the rules in `.vale.ini` — warnings only for now.

## Repository layout

| Path | Contents |
|------|----------|
| `docs.json` | Navigation, theme, redirects, integrations |
| `index.mdx`, `quickstart.mdx` | Landing page and getting-started tutorial |
| `essentials/` | Feature documentation |
| `guides/` | End-to-end task guides |
| `integrations/` | CLI, Terraform, Git providers, registries |
| `api-reference/` | API landing page (endpoints render from the live OpenAPI spec) |
| `changelog.mdx` | Platform changelog |
| `scripts/` | CI check scripts |
| `images/` | Screenshots and static assets |

The API Reference tab renders from the live spec at `https://platform.ankra.app/openapi.json` — there is intentionally no local OpenAPI copy to drift.

## Writing docs

Read [STYLEGUIDE.md](STYLEGUIDE.md) before writing. The short version:

- UK English (`organisation`), "add-on" in prose, "Stack" capitalised when referring to the Ankra concept.
- Every page needs `title` and `description` frontmatter.
- Commands must be copy-pasteable — test them before committing.
- Prefer one canonical page per topic and link to it; don't restate setup steps.
- Spaced em-dashes (`word — word`), `bash` for shell fences.

## Intentionally undocumented surfaces

These product surfaces exist in code but are deliberately not publicly documented. If you ship changes to one and believe it should become public, open a docs PR that removes it from this list:

| Surface | Reason |
|---------|--------|
| Linear integration (`admin_linear_oauth`, `linear_webhook`) | Internal/admin tooling |
| Presence, feature flags, environment colors | Internal platform plumbing |
| Cluster scheduler, platform engine playground, recent drafts API | Internal/experimental |
| Agent shadow mode (`shadow.*` Helm values) | Engineering cutover tooling, not a user feature |

## Analytics and feedback

- Page analytics stream to PostHog (`integrations.posthog` in `docs.json`). Two dashboards are worth maintaining there (create/update manually in PostHog): **quickstart funnel** (landing → quickstart → provider/import guide) and **zero-result searches** (what readers looked for and didn't find).
- The on-page feedback widget (`feedback` in `docs.json`) enables thumbs ratings, "suggest edit", and "raise issue" on every page.
- `https://docs.ankra.ai/llms.txt` and `/llms-full.txt` are hosted automatically for AI assistants; the contextual menu offers "open in ChatGPT/Claude".

## Deployment

Merges to `master` deploy automatically via the Mintlify GitHub integration.

## Contributing

1. Branch from `master`, make your change, run `npm run check`.
2. Open a PR. CI must pass; a docs owner reviews.
3. New product features should land with a docs PR — see the docs checklist in the product repos' PR templates.
