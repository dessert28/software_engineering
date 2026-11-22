# syntax=docker/dockerfile:1
#
# 一个镜像跑两个角色：api（uvicorn）和 web（nginx 托管前端静态文件）。
# 由 docker-compose.yml 的 command 区分，避免维护两份 Dockerfile。

# ───────────── 阶段 1：构建前端 ─────────────
FROM node:22-alpine AS webbuild
WORKDIR /src
COPY frontend/package.json frontend/pnpm-lock.yaml frontend/pnpm-workspace.yaml ./
RUN npm install -g pnpm@11 && pnpm install --frozen-lockfile
COPY frontend/ ./
RUN pnpm exec vite build

# ───────────── 阶段 2：运行时 ─────────────
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
 && apt-get install -y --no-install-recommends nginx curl \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app/backend
COPY backend/pyproject.toml ./
COPY backend/app ./app
RUN pip install --no-cache-dir .

# 前端静态资源交给 nginx
COPY --from=webbuild /src/dist /usr/share/nginx/html
COPY docker/nginx.conf /etc/nginx/conf.d/default.conf

COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

# SQLite 与上传目录都落在挂载卷里，容器重建不丢数据
ENV DATABASE_URL="sqlite+aiosqlite:///./data/mmcm.db" \
    STORAGE_LOCAL_ROOT="./data/uploads"

EXPOSE 8000 80
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["api"]
