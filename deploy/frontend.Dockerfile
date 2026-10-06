FROM node:22-alpine AS dependencies
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

FROM node:22-alpine AS builder
WORKDIR /app
ARG NEXT_PUBLIC_API_BASE=""
ARG NEXT_PUBLIC_WS_BASE
ENV NEXT_PUBLIC_API_BASE=${NEXT_PUBLIC_API_BASE} \
    NEXT_PUBLIC_WS_BASE=${NEXT_PUBLIC_WS_BASE} \
    NEXT_TELEMETRY_DISABLED=1
COPY --from=dependencies /app/node_modules ./node_modules
COPY frontend/ .
RUN npm run build

FROM node:22-alpine AS runtime
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    HOSTNAME=0.0.0.0 \
    PORT=3000
WORKDIR /app
RUN addgroup --system --gid 10001 infdrawing \
    && adduser --system --uid 10001 --ingroup infdrawing infdrawing
COPY --from=builder --chown=infdrawing:infdrawing /app ./
RUN npm prune --omit=dev
USER infdrawing
EXPOSE 3000
CMD ["npm", "run", "start"]
