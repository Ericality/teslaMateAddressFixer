#!/usr/bin/env python3
"""
配置文件示例
"""

import os

# 数据库配置
DB_HOST = os.getenv('DB_HOST', 'database')  # Docker网络中使用服务名
DB_PORT = int(os.getenv('DB_PORT', 5432))
DB_NAME = os.getenv('DB_NAME', 'teslamate')
DB_USER = os.getenv('DB_USER', 'teslamate')
DB_PASS = os.getenv('DB_PASS', 'teslamate')

# 百度地图API配置
BAIDU_AK = os.getenv('BAIDU_AK')
BAIDU_SK = os.getenv('BAIDU_SK')

# 修复配置
DAYS_TO_FIX = int(os.getenv('DAYS_TO_FIX', 7))  # 修复最近7天的数据
BATCH_SIZE = int(os.getenv('BATCH_SIZE', 2))    # 批量提交大小
LIMIT_PER_RUN = os.getenv('LIMIT_PER_RUN')      # 每次运行修复的最大数量（None表示无限制）
API_DELAY = float(os.getenv('API_DELAY', 1.0))  # API调用延迟（秒）

# 日志配置
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')

# 定时任务配置
CRON_SCHEDULE = os.getenv('CRON_SCHEDULE', '0 2 * * *')  # 默认每天凌晨2点