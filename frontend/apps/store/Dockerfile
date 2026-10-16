FROM node:24.22.0-alpine3.23 AS builder
ENV COREPACK_ENABLE_DOWNLOAD_PROMPT=0 \
    NEXT_TELEMETRY_DISABLED=1 \
    CI=true
RUN corepack enable
WORKDIR /repo
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml .npmrc ./
COPY packages/config/package.json ./packages/config/package.json
COPY packages/api-client/package.json ./packages/api-client/package.json
COPY packages/auth/package.json ./packages/auth/package.json
COPY packages/ui/package.json ./packages/ui/package.json
COPY apps/store/package.json ./apps/store/package.json
RUN pnpm install --frozen-lockfile --filter @ecommerce/store...
COPY packages/config/next ./packages/config/next
COPY packages/config/styles ./packages/config/styles
COPY packages/config/tsconfig ./packages/config/tsconfig
COPY packages/api-client/src ./packages/api-client/src
COPY packages/auth/src ./packages/auth/src
COPY packages/ui/src ./packages/ui/src
COPY apps/store ./apps/store
RUN pnpm --filter @ecommerce/store build

FROM node:24.22.0-alpine3.23 AS runtime
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0
WORKDIR /app
COPY --from=builder --chown=node:node /repo/apps/store/.next/standalone ./
COPY --from=builder --chown=node:node /repo/apps/store/.next/static ./apps/store/.next/static
COPY --from=builder --chown=node:node /repo/apps/store/public ./apps/store/public
USER node
EXPOSE 3000
CMD ["node", "apps/store/server.js"]
