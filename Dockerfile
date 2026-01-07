# 使用Python官方镜像
FROM python:3.9-slim

# 设置工作目录
WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    cron \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY requirements.txt .

# 安装Python依赖
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用程序文件
COPY teslamate_fixer.py .
COPY config.py .

# 复制启动脚本
COPY start.sh .
RUN chmod +x start.sh

# 复制cron配置文件
COPY cronjob /etc/cron.d/teslamate-fixer-cron
RUN chmod 0644 /etc/cron.d/teslamate-fixer-cron

# 创建日志目录
RUN mkdir -p /var/log/teslamate

# 创建运行用户（非root）
RUN useradd -m -u 1000 teslamate && \
    chown -R teslamate:teslamate /app /var/log/teslamate

# 切换到非root用户
USER teslamate

# 设置环境变量
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost/ || exit 1

# 设置cron日志
RUN touch /var/log/cron.log

# 应用cron job
RUN crontab /etc/cron.d/teslamate-fixer-cron

# 暴露端口（如果需要）
# EXPOSE 8000

# 设置容器启动命令
CMD ["./start.sh"]