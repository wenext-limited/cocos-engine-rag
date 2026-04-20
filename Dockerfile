FROM python:3.12-slim

# 安装 uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# 设置工作目录
WORKDIR /app

# 先复制依赖文件并进行预安装，利用 Docker 缓存加速依赖层
COPY pyproject.toml uv.lock ./

# 安装依赖
# 将 .venv 放在工作目录下
RUN uv sync --frozen --no-dev

# 复制项目代码
COPY src/ ./src/
COPY main.py ./

# 确保持久化数据目录存在
# 注意服务器部署时可能需要挂载 /app/.data 到宿主机以保存 Chroma 数据库
RUN mkdir -p /app/.data/chroma_db

# 暴露服务端口
EXPOSE 8000

ENV PYTHONPATH=/app/src
# 激活 python virtual environment 并运行服务器
ENTRYPOINT ["uv", "run", "python", "-m", "src.server"]
