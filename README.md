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
    "openapi": "https://charizard.ankra.dev/openapi.json"
  }
  ```

## Deployment

- Connect your GitHub repository to Mintlify for automatic deployments.
- Changes pushed to your default branch will be published to your live documentation site.

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
