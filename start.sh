#!/bin/bash

# 启动脚本

echo "=========================================="
echo "Teslamate地址修复工具 - Docker容器启动"
echo "=========================================="

# 检查必需的环境变量
if [ -z "$BAIDU_AK" ] || [ -z "$BAIDU_SK" ]; then
    echo "错误：必须设置BAIDU_AK和BAIDU_SK环境变量"
    exit 1
fi

# 显示配置信息（不显示敏感信息）
echo "配置信息："
echo "DB_HOST: $DB_HOST"
echo "DB_PORT: $DB_PORT"
echo "DB_NAME: $DB_NAME"
echo "DB_USER: $DB_USER"
echo "DAYS_TO_FIX: ${DAYS_TO_FIX:-7}"
echo "BATCH_SIZE: ${BATCH_SIZE:-2}"
echo "LOG_LEVEL: ${LOG_LEVEL:-INFO}"
echo "CRON_SCHEDULE: ${CRON_SCHEDULE:-0 2 * * *}"
echo ""

# 测试数据库连接
echo "测试数据库连接..."
python3 -c "
import psycopg2
try:
    conn = psycopg2.connect(
        host='$DB_HOST',
        port=$DB_PORT,
        database='$DB_NAME',
        user='$DB_USER',
        password='$DB_PASS'
    )
    print('✅ 数据库连接成功')
    conn.close()
except Exception as e:
    print(f'❌ 数据库连接失败: {e}')
    exit(1)
"

if [ $? -ne 0 ]; then
    exit 1
fi

# 测试百度API连接
echo "测试百度API连接..."
python3 -c "
import requests
import hashlib
import urllib.parse
import json

ak = '$BAIDU_AK'
sk = '$BAIDU_SK'

# 测试坐标
lat, lng = 31.2304, 121.4737

# 构建参数
params = {
    'ak': ak,
    'location': f'{lat},{lng}',
    'output': 'json',
    'coordtype': 'wgs84ll',
}

# 生成SN
query_parts = []
for key, value in params.items():
    query_parts.append(f'{key}={value}')

query_str = '&'.join(query_parts)
full_query_str = f'/reverse_geocoding/v3/?{query_str}'
encoded_str = urllib.parse.quote(full_query_str, safe=\"/:=&?#+!$,;'@()*[]\")
raw_str = encoded_str + sk
final_str = urllib.parse.quote_plus(raw_str)
sn = hashlib.md5(final_str.encode()).hexdigest()

params['sn'] = sn

# 构建URL
query_parts = []
for key, value in params.items():
    if key == 'location':
        query_parts.append(f'{key}={value}')
    else:
        query_parts.append(f'{key}={value}')

query_str = '&'.join(query_parts)
url = f'http://api.map.baidu.com/reverse_geocoding/v3/?{query_str}'

try:
    response = requests.get(url, timeout=10, verify=False)
    data = response.json()

    if data.get('status') == 0:
        address = data.get('result', {}).get('formatted_address', '')
        print(f'✅ 百度API连接成功: {address}')
    else:
        print(f'❌ 百度API错误: {data.get(\"message\")}')
        exit(1)
except Exception as e:
    print(f'❌ 百度API连接失败: {e}')
    exit(1)
"

if [ $? -ne 0 ]; then
    exit 1
fi

echo ""
echo "所有检查通过，开始启动服务..."

# 创建日志文件
touch /var/log/teslamate/fixer.log

# 动态生成 cron 配置（支持 CRON_SCHEDULE 环境变量）
SCHEDULE="${CRON_SCHEDULE:-0 2 * * *}"
echo "${SCHEDULE} cd /app && python3 teslamate_fixer.py >> /var/log/teslamate/fixer.log 2>&1" | crontab -

# 显示 cron 配置
echo "Cron 任务配置: ${SCHEDULE}"
crontab -l
echo ""

# 立即运行一次修复（可选）
if [ "$RUN_ON_STARTUP" = "true" ]; then
    echo "立即运行一次修复..."
    python3 /app/teslamate_fixer.py
    echo "立即修复完成"
fi

echo ""
echo "启动cron服务..."

# 启动cron并保持容器运行
exec cron -f