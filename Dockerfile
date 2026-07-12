FROM node:20-alpine AS deps
WORKDIR /app

# Enable pnpm via corepack (packageManager: pnpm@11.1.2)
RUN corepack enable

# Install dependencies with lockfile for reproducible, cached installs
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile

# ---------- Production runtime ----------
FROM node:20-alpine AS runtime
WORKDIR /app

ENV NODE_ENV=production
ENV PORT=3000

RUN corepack enable

# Create a non-root user
RUN addgroup -S app && adduser -S app -G app

# Bring in installed dependencies and the docs content
COPY --from=deps /app/node_modules ./node_modules
COPY . .

RUN chown -R app:app /app
USER app

EXPOSE 3000

# Mintlify dev server; bind to all interfaces so the container is reachable
CMD ["pnpm", "exec", "mint", "dev", "--host", "0.0.0.0", "--port", "3000"]
