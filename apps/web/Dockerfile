# Build from the repository root; no runtime configuration or secrets are build args.
FROM node:24-bookworm-slim@sha256:c86ecead9e55a5210ac1727de38a4ca840bf03dcaf34dc9749addbf383b1920c AS dependencies
ENV NEXT_TELEMETRY_DISABLED=1
WORKDIR /app/apps/web
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci --ignore-scripts --no-audit --no-fund

FROM node:24-bookworm-slim@sha256:c86ecead9e55a5210ac1727de38a4ca840bf03dcaf34dc9749addbf383b1920c AS build
ENV NEXT_TELEMETRY_DISABLED=1
WORKDIR /app/apps/web
COPY --from=dependencies /app/apps/web/node_modules ./node_modules
COPY apps/web/package.json apps/web/package-lock.json apps/web/tsconfig.json apps/web/next.config.ts ./
COPY apps/web/src ./src
RUN mkdir -p public && npm run build

FROM node:24-bookworm-slim@sha256:c86ecead9e55a5210ac1727de38a4ca840bf03dcaf34dc9749addbf383b1920c AS runtime
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=8080 HOSTNAME=0.0.0.0 HOME=/tmp
WORKDIR /app
COPY --from=build --chown=65532:65532 /app/apps/web/.next/standalone ./
COPY --from=build --chown=65532:65532 /app/apps/web/.next/static ./.next/static
COPY --from=build --chown=65532:65532 /app/apps/web/public ./public
USER 65532:65532
EXPOSE 8080
CMD ["node", "server.js"]
