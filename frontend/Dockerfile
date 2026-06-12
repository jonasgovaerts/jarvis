# Build from the repo root: docker build -f frontend/Dockerfile .
FROM node:22-alpine AS build
WORKDIR /app
COPY libs/ts/jarvis-events/ libs/ts/jarvis-events/
# The file-linked package resolves zod from its own node_modules (real-path
# module resolution through the symlink).
RUN cd libs/ts/jarvis-events && npm ci
COPY frontend/package.json frontend/package-lock.json frontend/
RUN cd frontend && npm ci
COPY frontend/ frontend/
RUN cd frontend && npm run build

FROM nginx:1.27-alpine
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/frontend/dist /usr/share/nginx/html
EXPOSE 8080
