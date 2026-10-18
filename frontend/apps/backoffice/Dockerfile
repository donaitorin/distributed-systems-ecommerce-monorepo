FROM node:24.22.0-alpine3.23 AS builder
ENV COREPACK_ENABLE_DOWNLOAD_PROMPT=0 \
    NEXT_TELEMETRY_DISABLED=1 \
    CI=true \
    npm_config_fetch_retries=5 \
    npm_config_fetch_retry_mintimeout=2000 \
    npm_config_fetch_retry_maxtimeout=20000
RUN corepack enable
WORKDIR /repo
COPY package.json ./
RUN set -eu; \
    for attempt in 1 2 3 4 5; do \
      corepack install && pnpm --version && exit 0; \
      echo "preparing pnpm failed (attempt $attempt of 5)" >&2; \
      sleep $((attempt * 5)); \
    done; \
    exit 1
COPY pnpm-lock.yaml pnpm-workspace.yaml .npmrc ./
COPY packages/config/package.json ./packages/config/package.json
COPY packages/api-client/package.json ./packages/api-client/package.json
COPY packages/auth/package.json ./packages/auth/package.json
COPY packages/ui/package.json ./packages/ui/package.json
COPY packages/web-core/package.json ./packages/web-core/package.json
COPY apps/backoffice/package.json ./apps/backoffice/package.json
RUN set -eu; \
    for attempt in 1 2 3; do \
      pnpm install --frozen-lockfile --filter @ecommerce/backoffice... && exit 0; \
      echo "pnpm install failed (attempt $attempt of 3)" >&2; \
      sleep $((attempt * 5)); \
    done; \
    exit 1
COPY packages/config/next ./packages/config/next
COPY packages/config/styles ./packages/config/styles
COPY packages/config/tsconfig ./packages/config/tsconfig
COPY packages/api-client/src ./packages/api-client/src
COPY packages/auth/src ./packages/auth/src
COPY packages/ui/src ./packages/ui/src
COPY packages/web-core/src ./packages/web-core/src
COPY apps/backoffice ./apps/backoffice
RUN pnpm --filter @ecommerce/backoffice build

FROM node:24.22.0-alpine3.23 AS runtime
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0
WORKDIR /app
COPY --from=builder --chown=node:node /repo/apps/backoffice/.next/standalone ./
COPY --from=builder --chown=node:node /repo/apps/backoffice/.next/static ./apps/backoffice/.next/static
COPY --from=builder --chown=node:node /repo/apps/backoffice/public ./apps/backoffice/public
USER node
EXPOSE 3000
CMD ["node", "apps/backoffice/server.js"]
