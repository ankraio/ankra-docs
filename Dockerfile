# syntax=docker/dockerfile:1

# The image serves a static `mint export` of the docs. The Mintlify CLI and its
# dependency tree only run at build time, so none of it ships: the runtime is
# node plus scripts/serve.mjs, which uses Node built-ins only. Mintlify pins
# transitive dependencies (zod 3.24.0 has no fixed 3.x release for
# CVE-2023-54404) that the image gate would otherwise block on.
#
# The deps and export stages run on the build platform: the export is
# platform independent, and running it once natively beats running it under
# emulation for every target platform.

##########
# deps: resolve node_modules from the committed pnpm lockfile
##########
FROM --platform=$BUILDPLATFORM node:22-alpine AS deps
WORKDIR /app

ENV COREPACK_ENABLE_DOWNLOAD_PROMPT=0
RUN corepack enable

# Lock/manifest files first so this layer caches until deps actually change.
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./

RUN --mount=type=cache,target=/root/.local/share/pnpm/store \
    pnpm install --frozen-lockfile

##########
# export: render every page to static HTML with the `mint` CLI
##########
FROM deps AS export

# Docs content: .mdx pages, docs.json navigation, images, logos, styles.
COPY . .

# The export also carries every non-page repository file and Mintlify's own
# local-viewer launchers; drop them so only the site is served. Text assets are
# then stored gzipped (the OpenAPI pages are ~1 MB of HTML each and compress
# about 7:1); serve.mjs sends them with Content-Encoding: gzip.
RUN pnpm exec mint export --output /tmp/docs.zip \
 && mkdir /site \
 && unzip -q /tmp/docs.zip -d /site \
 && rm /tmp/docs.zip \
 && cd /site \
 && rm -rf serve.js 'Start Docs.bat' 'Start Docs.command' Dockerfile \
      .dockerignore .gitignore .vale .vale.ini scripts \
 && test -f index.html \
 && find . -type f \( -name '*.html' -o -name '*.js' -o -name '*.css' \
      -o -name '*.json' -o -name '*.svg' -o -name '*.txt' -o -name '*.xml' \) \
      -exec gzip -9 {} +

##########
# runtime: static file server
##########
FROM node:22-alpine AS runner
WORKDIR /app

ENV NODE_ENV=production \
    PORT=3000 \
    SITE_DIR=/app/site

# Only node itself is needed. npm, npx, corepack and yarn are removed because
# each bundles its own dependency tree that the image gate scans.
RUN rm -rf /usr/local/lib/node_modules /opt/yarn-* \
      /usr/local/bin/npm /usr/local/bin/npx /usr/local/bin/corepack \
      /usr/local/bin/yarn /usr/local/bin/yarnpkg

# Root-owned and read-only to the server; it runs as the image's `node` user
# (uid 1000, the uid the application's Deployment runs as).
COPY --from=export /site ./site
COPY scripts/serve.mjs ./serve.mjs

USER node

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD node -e "fetch('http://127.0.0.1:3000/').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"

CMD ["node", "serve.mjs"]
