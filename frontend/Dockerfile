# syntax=docker/dockerfile:1.7
# ---------------------------------------------------------------------------
# Stage 1: builder — install npm deps and build the Vite production bundle
# ---------------------------------------------------------------------------
FROM node:20-alpine AS builder

WORKDIR /build

# Copy lockfiles first to maximise Docker layer caching.
COPY package.json package-lock.json ./
RUN npm ci

# Copy the rest of the source and build.
COPY . .
RUN npm run build

# ---------------------------------------------------------------------------
# Stage 2: runtime — Nginx serving the static bundle
# ---------------------------------------------------------------------------
# 1.30 = current stable line; bumped from 1.27 (alpine 3.21) on 2026-07-22 to
# clear fixable HIGH/CRITICAL OS-package CVEs flagged by the Trivy gate.
FROM nginx:1.30-alpine AS runtime

# Replace the default config with one tuned for an SPA + /api reverse-proxy.
COPY nginx.conf /etc/nginx/conf.d/default.conf
# Security-header snippet, included by nginx.conf. Kept outside conf.d so it is
# not auto-loaded as a server block.
COPY security_headers.conf /etc/nginx/security_headers.conf

# Copy built assets from the builder stage.
COPY --from=builder /build/dist /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD wget --quiet --spider http://localhost/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
