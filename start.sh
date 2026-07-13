#!/bin/bash

echo "=========================================="
echo "Teslamate地址修复工具 - Docker容器启动"
echo "=========================================="

[ -z "$BAIDU_AK" ] || [ -z "$BAIDU_SK" ] && {
    echo "错误：必须设置BAIDU_AK和BAIDU_SK环境变量"
    exit 1
}

[ -n "$TZ" ] && {
    ln -sf "/usr/share/zoneinfo/$TZ" /etc/localtime 2>/dev/null || true
    echo "$TZ" > /etc/timezone 2>/dev/null || true
}

echo "配置信息："
echo "DB_HOST: $DB_HOST  DB_PORT: $DB_PORT  DB_NAME: $DB_NAME"
echo "DAYS_TO_FIX: ${DAYS_TO_FIX:-7}  BATCH_SIZE: ${BATCH_SIZE:-2}"
echo "CRON_SCHEDULE: ${CRON_SCHEDULE:-0 2 * * *}  TZ: ${TZ:-UTC}"
echo ""

echo "测试数据库连接..."
python3 -c "
import psycopg2
try:
    conn = psycopg2.connect(host='$DB_HOST',port=$DB_PORT,database='$DB_NAME',user='$DB_USER',password='$DB_PASS')
    print('✅ 数据库连接成功'); conn.close()
except Exception as e:
    print(f'❌ 数据库连接失败: {e}'); exit(1)
" || exit 1

echo "测试百度API连接..."
python3 -c "
import requests,hashlib,urllib.parse
try:
    p={'ak':'$BAIDU_AK','location':'31.2304,121.4737','output':'json','coordtype':'wgs84ll'}
    q='&'.join(f'{k}={v}' for k,v in p.items())
    s=urllib.parse.quote(f'/reverse_geocoding/v3/?{q}',safe=\"/:=&?#+!$,;'@()*[]\")+'$BAIDU_SK'
    p['sn']=hashlib.md5(urllib.parse.quote_plus(s).encode()).hexdigest()
    r=requests.get('http://api.map.baidu.com/reverse_geocoding/v3/?'+'&'.join(f'{k}={v}' for k,v in p.items()),timeout=10,verify=False)
    if r.json().get('status')==0: print('✅ 百度API连接成功')
    else: print(f\"❌ 百度API错误: {r.json().get('message')}\"); exit(1)
except Exception as e: print(f'❌ 百度API连接失败: {e}'); exit(1)
" || exit 1

echo ""; echo "所有检查通过，开始启动服务..."

LOG_FILE="/var/log/teslamate/fixer.log"
touch "$LOG_FILE"

# 通过 env 命令生成 export 文件，shell 可直接 source
env | while IFS='=' read -r name value; do
    printf "export %s='%s'\n" "$name" "$value"
done > /app/container.env
chmod 644 /app/container.env

# 创建 cron 执行的 wrapper 脚本
cat > /app/cron_job.sh << 'WRAPPER_EOF'
#!/bin/bash
set -a
source /app/container.env
set +a
exec /usr/local/bin/python3 /app/teslamate_fixer.py
WRAPPER_EOF
chmod +x /app/cron_job.sh

SCHEDULE="${CRON_SCHEDULE:-0 2 * * *}"
echo "${SCHEDULE} /bin/bash /app/cron_job.sh >> ${LOG_FILE} 2>&1" | crontab -

echo "Cron 任务: ${SCHEDULE}"
crontab -l
echo ""

[ "$RUN_ON_STARTUP" = "true" ] && {
    echo "立即运行一次修复..."
    python3 /app/teslamate_fixer.py
    echo "立即修复完成"
}

echo "启动cron服务..."
cron -f &
tail -f "$LOG_FILE"