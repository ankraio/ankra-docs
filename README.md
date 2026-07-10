# Ankra Mintlify Documentation

Welcome to the Ankra Mintlify documentation starter! This project provides a robust foundation for building and customizing your API and product documentation using [Mintlify](https://mintlify.com/).

## Features

- Structured guide pages for onboarding and usage
- Customizable navigation and theming
- Auto-generated API Reference from OpenAPI specs
- Rich component library for interactive docs
- Easy local development and preview

## Getting Started

1. **Clone this repository**
   Use this template to kickstart your own documentation project.

2. **Install Mintlify CLI**
   The Mintlify CLI lets you preview and develop your docs locally.
   Install globally with:

   ```bash
   npm i -g mintlify
   ```

3. **Preview Documentation Locally**
   From the root directory (where `docs.json` is located), run:

   ```bash
   mintlify dev
   ```

   This will start a local server so you can view and edit your documentation in real time.

## API Reference Integration

- The API Reference tab is auto-generated from your OpenAPI specification.
- To update the API docs, edit the `openapi` field in `docs.json` to point to your OpenAPI JSON or YAML file.
- Example:

  ```json
  {
    "tab": "API Reference",
    "openapi": "https://platform.ankra.app/openapi.json"
  }
  ```

## Deployment

- Connect your GitHub repository to Mintlify for automatic deployments.
- Changes pushed to your default branch will be published to your live documentation site.

## Keeping docs in sync with releases

Documentation drifts when a feature ships without a matching docs change. Run this checklist as part of every user-visible release so the docs never lag behind the product:

1. **Changelog.** Add a dated `<Update>` block to `changelog.mdx` describing the user-visible change, linking to the feature page. This file is the single source of truth for product changes.
2. **Feature page.** Create or update the relevant page under `essentials/`, `integrations/`, or `guides/`, and wire any new page into `docs.json` navigation.
3. **CLI changelog.** For a CLI release, mirror `ankra-cli/CHANGELOG.md` into `integrations/ankra-cli-changelog.mdx` (newest first, one `<Update>` per version).
4. **CLI reference sync.** Extend `integrations/ankra-cli.mdx` for any new command, flag, or exit code. If the generated reference (`tools/gendocs`) is in use, confirm its sync PR landed.
5. **Wire-format schemas.** If a wire-format Pydantic model changed, run `python scripts/dump_pydantic_schemas.py` in the platform repo and commit the diff.
6. **Publish.** Merge `develop` → `master` (or your default branch) so Mintlify publishes the update. Do this as a deliberate release step, not per-commit.

Before publishing, run `mintlify dev` (or `mintlify broken-links`) to catch broken internal links introduced by new or moved pages.

## Troubleshooting

- **Mintlify CLI not running?**
  Run `mintlify install` to re-install dependencies.
- **404 errors?**
  Ensure you are running the CLI in the directory containing `docs.json`.
- **OpenAPI not loading?**
  Double-check your `openapi` URL and ensure it is a valid OpenAPI 3.0+ document.

## Resources

- [Mintlify Documentation](https://mintlify.com/docs)
- [Ankra](https://ankra.dev)
- [OpenAPI Specification](https://swagger.io/specification/)

---

For questions or support, reach out to the Ankra team or join the Mintlify community!
