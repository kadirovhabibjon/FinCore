# Stage 1: build the static bundle. The API types are generated from
# contracts/openapi, which lives outside frontend/, so the build context
# is the repository root (see docker-compose.yml).
FROM node:22-alpine AS build
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY contracts/openapi /app/contracts/openapi
COPY frontend/ ./
RUN npm run gen:api && npm run build

# Stage 2: only the built files and Nginx — no Node, no sources.
FROM nginx:1.27-alpine
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY frontend/security-headers.conf /etc/nginx/snippets/security-headers.conf
COPY --from=build /app/frontend/dist /usr/share/nginx/html
HEALTHCHECK --interval=10s --timeout=3s --retries=5 CMD wget -qO- http://127.0.0.1/ >/dev/null || exit 1
