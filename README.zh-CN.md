# TeslaMate 地址修复工具

[![Docker Pulls](https://img.shields.io/docker/pulls/ericality/teslamate-fixer)](https://hub.docker.com/r/ericality/teslamate-fixer)
[![Platforms](https://img.shields.io/badge/platform-linux%2Famd64%20%7C%20linux%2Farm64-blue)](https://hub.docker.com/r/ericality/teslamate-fixer/tags)

[English](README.md) | **中文**

基于 cron 的 Docker 服务，使用百度地图逆地理编码 API 自动修复 [TeslaMate](https://github.com/teslamate-org/teslamate) 中缺失的中文地址。

## 功能特性

- 自动检测并修复 `start_address` 或 `end_address` 为空的驾驶记录
- 调用百度地图逆地理编码 API，支持 POI 兴趣点
- 通过环境变量灵活配置 cron 执行频率
- 同时支持 Docker Compose 和 Kubernetes 部署
- 多架构镜像（`linux/amd64` + `linux/arm64`）
- 坐标相近自动复用已创建的地址，避免重复
- 支持每次运行限量，便于调试

## 工作原理

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  PostgreSQL  │────▶│  地址修复器   │────▶│  百度地图     │
│  (TeslaMate) │     │  (cron 任务) │     │  逆地理 API  │
│              │◀────│              │◀────│              │
└──────────────┘     └──────────────┘     └──────────────┘
```

1. 从 TeslaMate 的 `drives` 表中查询 `start_address_id` 或 `end_address_id` 为 NULL 的记录
2. 通过 `positions` 表获取对应的 GPS 坐标
3. 调用百度地图逆地理编码 API
4. 在 `addresses` 表中创建或复用地址记录
5. 更新 `drives` 表中的地址引用

## 快速开始

### 前置条件

- 已部署的 TeslaMate 实例（PostgreSQL 数据库可访问）
- 百度地图 API 密钥（AK + SK）— [点此申请](https://lbsyun.baidu.com/apiconsole/key)

### Docker Compose（独立部署）

```bash
# 克隆仓库
git clone https://github.com/Ericality/teslaMateAddressFixer.git
cd teslaMateAddressFixer

# 创建 .env 文件
cat > .env << 'EOF'
BAIDU_MAP_AK=你的百度AK
BAIDU_MAP_SK=你的百度SK
TESLAMATE_DB_PASSWORD=你的数据库密码
EOF

# 启动（需要接入 teslamate Docker 网络）
docker compose -f deploy/docker-compose.example.yaml up -d
```

### 直接拉取镜像

无需本地构建，直接使用预构建的多架构镜像：

```bash
docker pull ericality/teslamate-fixer:latest
```

> 群晖等无法直连 Docker Hub 的环境，可通过代理拉取：`docker.1ms.run/ericality/teslamate-fixer:latest`

## 配置说明

所有参数通过环境变量设置：

| 变量 | 默认值 | 说明 |
|----------|---------|-------------|
| **数据库** | | |
| `DB_HOST` | `database` | 数据库主机地址 |
| `DB_PORT` | `5432` | 数据库端口 |
| `DB_NAME` | `teslamate` | 数据库名 |
| `DB_USER` | `teslamate` | 数据库用户名 |
| `DB_PASS` | （必填） | 数据库密码 |
| **百度地图** | | |
| `BAIDU_AK` | （必填） | 百度地图 API Key |
| `BAIDU_SK` | （必填） | 百度地图 Secret Key |
| **修复行为** | | |
| `DAYS_TO_FIX` | `7` | 仅修复最近 N 天的记录 |
| `BATCH_SIZE` | `2` | 每处理 N 条地址提交一次事务 |
| `LIMIT_PER_RUN` | 不限制 | 每次 cron 执行最多修复的行程数 |
| `API_DELAY` | `1.0` | 百度 API 调用间隔（秒） |
| **定时调度** | | |
| `CRON_SCHEDULE` | `0 2 * * *` | Cron 表达式（动态生效，会覆盖静态 cronjob 文件） |
| `RUN_ON_STARTUP` | `true` | 容器启动时立即执行一次修复 |
| **日志** | | |
| `LOG_LEVEL` | `INFO` | Python 日志级别 |
| `LOG_FILE` | `/var/log/teslamate/fixer.log` | 日志文件路径 |
| **其他** | | |
| `TZ` | （UTC） | 时区（如 `Asia/Shanghai`） |

## 部署方式

### Docker Compose

```yaml
# deploy/docker-compose.example.yaml
services:
  teslamate-fixer:
    build: .
    container_name: teslamate-address-fixer
    restart: unless-stopped
    environment:
      - DB_HOST=database
      - DB_PORT=5432
      - DB_NAME=teslamate
      - DB_USER=teslamate
      - DB_PASS=${TESLAMATE_DB_PASSWORD}
      - BAIDU_AK=${BAIDU_MAP_AK}
      - BAIDU_SK=${BAIDU_MAP_SK}
      - CRON_SCHEDULE=0 * * * *
      - RUN_ON_STARTUP=true
      - TZ=Asia/Shanghai
    volumes:
      - ./logs:/var/log/teslamate
    networks:
      - teslamate

networks:
  teslamate:
    external: true
```

### Kubernetes

```bash
# 创建 Secret
kubectl create secret generic teslamate-fixer-secret \
  --from-literal=DB_PASS='你的密码' \
  --from-literal=BAIDU_AK='你的AK' \
  --from-literal=BAIDU_SK='你的SK' \
  -n teslamate

# 部署
kubectl apply -f deploy/k8s.yaml
```

详细部署清单见 `deploy/k8s.yaml`。

## 从源码构建

```bash
# 构建本地架构
docker build -t teslamate-address-fixer .

# 构建并推送多平台镜像
docker buildx build --platform linux/amd64,linux/arm64 \
  -t your-registry/teslamate-fixer:latest --push .
```

## 项目结构

```
.
├── teslamate_fixer.py          # 主程序
├── start.sh                    # 容器入口（数据库/API 检测、cron 设置）
├── cronjob                     # 静态 cron 配置（备用）
├── Dockerfile                  # Docker 镜像定义
├── requirements.txt            # Python 依赖
├── config.py                   # 配置模块（备用）
├── deploy/
│   ├── docker-compose.example.yaml   # Docker Compose 示例
│   └── k8s.yaml                      # Kubernetes 部署清单
├── .env.example                # 环境变量模板
└── .gitignore
```

## License

MIT