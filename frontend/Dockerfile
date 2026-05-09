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
FROM nginx:1.29-alpine AS runtime

# Replace the default config with one tuned for an SPA + /api reverse-proxy.
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Copy built assets from the builder stage.
COPY --from=builder /build/dist /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD wget --quiet --spider http://localhost/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
