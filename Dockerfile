# 米家Web版 容器镜像
# 官方基础镜像同时提供 linux/amd64 与 linux/arm64，覆盖群晖 / 飞牛等 x86 与 ARM 机型。
# 前端构建产物 static/vue/ 已随仓库提供，容器内不需要 Node。
FROM python:3.13-slim

LABEL org.opencontainers.image.title="Mijia-Web" \
      org.opencontainers.image.description="米家Web版 - 本地米家设备控制面板" \
      org.opencontainers.image.source="https://github.com/xuechao188/Mijia-Web"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=Asia/Shanghai \
    MIHOME_HOST=0.0.0.0 \
    MIHOME_PORT=8765 \
    MIHOME_NO_BROWSER=1 \
    MIHOME_DATA_DIR=/data \
    MIHOME_UPDATE_REPO=

WORKDIR /app

# 先只复制依赖清单装依赖，利用 Docker 层缓存：源码变动不必重装依赖。
COPY requirements.txt ./
RUN pip install --no-cache-dir --disable-pip-version-check \
        -i https://pypi.tuna.tsinghua.edu.cn/simple \
        -r requirements.txt || \
    pip install --no-cache-dir --disable-pip-version-check -r requirements.txt

COPY . .

# 数据目录：token / 缓存 / 数据库 / 日志全部落这里，用卷持久化。
# 容器内以 root 运行（NAS 场景最常见，避免卷权限问题）。
RUN mkdir -p /data
VOLUME ["/data"]

EXPOSE 8765

# 启动前由 config.ensure_dirs() 建好数据子目录；run.py 会拉起后台轮询线程并跑 waitress。
CMD ["python", "run.py"]
