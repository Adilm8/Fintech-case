# syntax=docker/dockerfile:1

FROM node:24-alpine AS base
RUN apk add --no-cache libc6-compat
WORKDIR /app

FROM base AS deps
COPY package.json package-lock.json ./
RUN npm ci

FROM base AS prod-deps
COPY package.json package-lock.json ./
RUN npm ci --omit=dev

FROM base AS builder
COPY --from=deps /app/node_modules ./node_modules
COPY . .

ARG NEXT_PUBLIC_APP_MODE=demo
ARG BACKEND_URL=http://backend:8000
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ARG NEXT_PUBLIC_DEMO_LOGINS=

ENV NEXT_PUBLIC_APP_MODE=${NEXT_PUBLIC_APP_MODE} \
    BACKEND_URL=${BACKEND_URL} \
    NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL} \
    NEXT_PUBLIC_DEMO_LOGINS=${NEXT_PUBLIC_DEMO_LOGINS} \
    NEXT_TELEMETRY_DISABLED=1

RUN npm run build

FROM base AS runner

ARG NEXT_PUBLIC_APP_MODE=demo
ARG BACKEND_URL=http://backend:8000

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    NEXT_PUBLIC_APP_MODE=${NEXT_PUBLIC_APP_MODE} \
    BACKEND_URL=${BACKEND_URL} \
    HOSTNAME=0.0.0.0 \
    PORT=3000 \
    PATH="/app/node_modules/.bin:${PATH}"

RUN addgroup --system --gid 1001 nodejs \
    && adduser --system --uid 1001 nextjs

COPY --from=prod-deps /app/node_modules ./node_modules
COPY --from=builder /app/package.json ./package.json
COPY --from=builder /app/next.config.ts ./next.config.ts
COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next ./.next

USER nextjs

EXPOSE 3000

CMD ["next", "start", "-H", "0.0.0.0", "-p", "3000"]
