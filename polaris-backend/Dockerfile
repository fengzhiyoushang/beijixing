# ─────────────────────────────────────────────────────────────
# 北极星 · 个人战略终端 —— 后端镜像
# 基础镜像：python:3.12-slim
# 依赖驱动：PyMySQL（纯 Python 实现），因此无需 gcc / mysqlclient 编译链
# 中文注释请勿直接写在本文件中：Dockerfile 按 ASCII 解析，注释含中文会告警
# 构建：docker build -t polaris-backend:1.0.0 .
# 运行：docker run --rm -p 8000:8000 --env-file .env polaris-backend:1.0.0
# ─────────────────────────────────────────────────────────────
FROM python:3.12-slim

# 环境变量：UTF-8 输出 + 东八区时区 + 关闭 pyc + 不缓冲日志（便于 docker logs 实时查看）
ENV PYTHONIOENCODING=utf-8 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=Asia/Shanghai \
    LANG=C.UTF-8

# 时区数据（tini 用于正确转发信号、优雅停止 uvicorn worker）
RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata tini \
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime \
    && echo $TZ > /etc/timezone \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 先单独拷贝依赖清单，命中 Docker 层缓存，改业务代码时不必重装依赖
COPY requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# 业务代码（app / scripts / tests 为可选冒烟测试）
COPY app/ ./app/
COPY scripts/ ./scripts/
COPY tests/ ./tests/
COPY .env.example ./.env.example

# 运行期需要落盘的目录：上传文件、备份、SQLite 回退库
# 注意：SQLITE_PATH 默认 data/polaris.db，容器内目录必须存在
RUN mkdir -p /app/uploads /app/backups /app/data

# 文档默认值，可被 --env-file / compose environment 覆盖
ENV DB_BACKEND=mysql \
    SQLITE_PATH=data/polaris.db \
    UPLOAD_DIR=uploads \
    BACKUP_DIR=backups

EXPOSE 8000

# 健康检查：直接请求 /health，返回 status=ok 或 degraded 均算存活（degraded 表示已回退 SQLite）
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4).status == 200 else 1)"]

ENTRYPOINT ["/usr/bin/tini", "--"]

# 生产启动方式：2 个 worker（SQLite 回退模式下请改为 1 个 worker，避免写锁竞争）
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
