FROM python:3.12-slim

# 安装 uv，设置工作目录
RUN pip install uv
WORKDIR /app

# 先复制依赖文件进行安装，利用 Docker 缓存加速
COPY pyproject.toml uv.lock ./

# 安装依赖
RUN uv sync --frozen --no-dev

# 复制项目代码
COPY src/ ./src/
COPY main.py ./

# 确保持久化数据目录存在
RUN mkdir -p /app/.data/chroma_db

# 暴露 SSE 可能使用的端口（仅供参考）
EXPOSE 8000

# 默认使用 stdio 模式运行（最常用的 MCP 客户端连接方式）
ENV PYTHONPATH=/app/src
ENTRYPOINT ["/app/.venv/bin/python", "-m", "src.server"]
