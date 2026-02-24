# Stage 1: Build frontend
FROM node:22-alpine AS frontend-builder
WORKDIR /app/frontend
RUN corepack enable && corepack prepare pnpm@latest --activate
COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY frontend/ ./
RUN NODE_ENV=production pnpm build

# Stage 2: Python runtime
FROM python:3.13-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY src/ ./src/
COPY config.example.yaml ./config.example.yaml
# Copy frontend static export
COPY --from=frontend-builder /app/frontend/out ./frontend/out/
EXPOSE 8080
CMD ["python", "-m", "src.main"]
