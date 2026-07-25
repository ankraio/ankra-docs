# syntax=docker/dockerfile:1

##########
# deps: resolve node_modules from the committed pnpm lockfile
##########
FROM node:22-alpine AS deps
WORKDIR /app

ENV COREPACK_ENABLE_DOWNLOAD_PROMPT=0
RUN corepack enable

# Lock/manifest files first so this layer caches until deps actually change.
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./

RUN --mount=type=cache,target=/root/.local/share/pnpm/store \
    pnpm install --frozen-lockfile

##########
# runtime: Mintlify docs server
##########
FROM node:22-alpine AS runner
WORKDIR /app

ENV NODE_ENV=production \
    COREPACK_ENABLE_DOWNLOAD_PROMPT=0 \
    PORT=3000 \
    HOSTNAME=0.0.0.0

RUN corepack enable \
 && apk add --no-cache python3 \
 && addgroup -S -g 1001 docs \
 && adduser -S -u 1001 -G docs -h /app docs

# Pre-resolved dependencies (includes the `mint` CLI from devDependencies).
COPY --from=deps --chown=docs:docs /app/node_modules ./node_modules

# Docs content: .mdx pages, docs.json navigation, images, logos, styles, scripts.
COPY --chown=docs:docs . .

USER docs

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD node -e "fetch('http://127.0.0.1:3000/').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"

CMD ["pnpm", "exec", "mint", "dev", "--port", "3000"]
