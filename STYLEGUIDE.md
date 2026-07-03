# Ankra Docs Style Guide

The goal is that a reader can trust every page: commands run as pasted, terminology is consistent, and each topic has exactly one canonical home.

## Language

- **UK English**: organisation, colour, behaviour, parameterise. Exception: keep US spelling inside code, API fields, and quoted UI labels that use it.
- **add-on** (hyphenated) in prose; `addons` only in code, YAML keys, URLs, and CLI output.
- **Stack** capitalised when referring to the Ankra concept ("deploy a Stack"); lowercase for the generic word ("the monitoring stack of tools").
- Product names as branded: Ankra, GitOps, Kubernetes, Helm, GitHub, k3s, ArgoCD.
- Em-dashes are spaced: `word — word`. Never a bare hyphen as a dash; it reads as a jammed word and has repeatedly been corrupted by tooling.

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
- No REST endpoint tables in feature pages — the API Reference tab renders the live OpenAPI spec.
- No "Best Practices" card grids of generic advice. If a practice matters, work it into the step where it applies.
- Never fabricate AI conversation transcripts or invented metrics. Show example *prompts*, not invented responses.
- No placeholder or real customer data in examples — use `my-org/my-repo`, `my-cluster`, `<cluster-id>`.
- No referral/affiliate parameters in links.
- Vendor-neutral naming for the AI ("Ankra's AI", "the AI Assistant") except in the changelog, which is a historical record.

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
