#!/usr/bin/env python3
"""
Teslamate地址修复工具 - Docker版本
支持环境变量配置，定时运行
"""

import psycopg2
import requests
import hashlib
import urllib.parse
import json
import time
import os
import sys
from datetime import datetime, timedelta
import logging


# ============ 配置部分 - 从环境变量读取 ============
def load_config():
    """从环境变量加载配置"""
    config = {
        # 数据库配置
        'db_host': os.getenv('DB_HOST', 'database'),  # 默认使用Docker网络别名
        'db_port': int(os.getenv('DB_PORT', '5432')),
        'db_name': os.getenv('DB_NAME', 'teslamate'),
        'db_user': os.getenv('DB_USER', 'teslamate'),
        'db_pass': os.getenv('DB_PASS', 'teslamate'),

        # 百度API配置
        'baidu_ak': os.getenv('BAIDU_AK'),
        'baidu_sk': os.getenv('BAIDU_SK'),

        # 修复配置
        'days_to_fix': int(os.getenv('DAYS_TO_FIX', '7')),  # 修复最近多少天的数据
        'batch_size': int(os.getenv('BATCH_SIZE', '2')),  # 批量提交大小
        'limit_per_run': os.getenv('LIMIT_PER_RUN'),  # 每次运行修复的最大数量
        'api_delay': float(os.getenv('API_DELAY', '1.0')),  # API调用延迟（秒）

        # 日志配置
        'log_level': os.getenv('LOG_LEVEL', 'INFO'),
    }

    # 验证必需配置
    if not config['baidu_ak'] or not config['baidu_sk']:
        raise ValueError("百度AK和SK必须通过环境变量设置")

    return config


# ============ 初始化日志 ============
def setup_logging(log_level='INFO'):
    """设置日志配置"""
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

    logging.basicConfig(
        level=getattr(logging, log_level),
        format=log_format,
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler('/var/log/teslamate-fixer.log')
        ]
    )

    # 抑制不必要的日志
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('requests').setLevel(logging.WARNING)

    return logging.getLogger(__name__)


# ============ 百度API函数 ============
class BaiduGeocoder:
    """百度地理编码器"""

    def __init__(self, ak, sk):
        self.ak = ak
        self.sk = sk
        self.logger = logging.getLogger(__name__)

    def generate_sn(self, params):
        """生成百度API的SN签名（不排序参数）"""
        # 构建查询字符串（不排序！保持原始顺序）
        query_parts = []
        for key, value in params.items():
            query_parts.append(f"{key}={value}")

        query_str = "&".join(query_parts)
        full_query_str = f"/reverse_geocoding/v3/?{query_str}"

        # URL编码（safe参数保留逗号不编码）
        encoded_str = urllib.parse.quote(full_query_str, safe="/:=&?#+!$,;'@()*[]")

        # 添加SK并计算MD5
        raw_str = encoded_str + self.sk
        final_str = urllib.parse.quote_plus(raw_str)
        sn = hashlib.md5(final_str.encode()).hexdigest()

        return sn

    def get_address(self, lng, lat):
        """
        从百度地图获取地址信息（带POI扩展）
        """
        # 构建参数 - 注意顺序！不要改变！
        params = {
            "ak": self.ak,
            "location": f"{lat},{lng}",  # 百度要求：纬度在前
            "output": "json",
            "coordtype": "wgs84ll",  # 必须的参数
            "extensions_poi": "1",  # 启用POI扩展
            "sort_strategy": "distance",  # 按距离排序
            "radius": "1000",  # 搜索半径1000米
            "extensions_road": "false",  # 不返回道路信息
        }

        # 生成SN（不排序）
        sn = self.generate_sn(params)
        params["sn"] = sn

        # 构建查询字符串（保持原始顺序）
        query_parts = []
        for key, value in params.items():
            if key == "location":
                query_parts.append(f"{key}={value}")
            else:
                query_parts.append(f"{key}={value}")

        query_str = "&".join(query_parts)
        url = f"http://api.map.baidu.com/reverse_geocoding/v3/?{query_str}"

        try:
            self.logger.debug(f"调用百度API: {lat:.6f}, {lng:.6f}")

            response = requests.get(url, timeout=10, verify=False)
            data = response.json()

            if data.get("status") == 0:
                result = data.get("result", {})
                address_component = result.get("addressComponent", {})

                # 优先使用formatted_address_poi（带POI的格式化地址）
                formatted_address_poi = result.get("formatted_address_poi", "")

                # 如果没有POI地址，使用普通格式化地址
                formatted_address = result.get("formatted_address", "")

                # 选择显示地址
                display_address = ""

                if formatted_address_poi:
                    display_address = formatted_address_poi
                elif formatted_address:
                    display_address = formatted_address
                else:
                    # 如果没有地址，从组件构建
                    parts = [
                        address_component.get("province", ""),
                        address_component.get("city", ""),
                        address_component.get("district", ""),
                        address_component.get("street", ""),
                        address_component.get("street_number", "")
                    ]
                    display_address = "".join([p for p in parts if p])

                # 获取POI列表（如果有）
                pois = result.get("pois", [])
                nearby_poi = ""
                if pois:
                    nearby_poi = pois[0].get("name", "") if len(pois) > 0 else ""

                return {
                    'display_name': display_address,
                    'province': address_component.get('province', ''),
                    'city': address_component.get('city', ''),
                    'district': address_component.get('district', ''),
                    'street': address_component.get('street', ''),
                    'street_number': address_component.get('street_number', ''),
                    'country': address_component.get('country', '中国'),
                    'country_code': 'cn',
                    'latitude': lat,
                    'longitude': lng,
                    'nearby_poi': nearby_poi,
                    'poi_count': len(pois),
                }
            else:
                self.logger.error(f"百度API错误: {data.get('message')}")
                return None

        except Exception as e:
            self.logger.error(f"调用百度API失败: {e}")
            return None


# ============ 数据库函数 ============
class DatabaseManager:
    """数据库管理器"""

    def __init__(self, config):
        self.config = config
        self.logger = logging.getLogger(__name__)

    def connect(self):
        """连接数据库"""
        try:
            conn = psycopg2.connect(
                host=self.config['db_host'],
                port=self.config['db_port'],
                database=self.config['db_name'],
                user=self.config['db_user'],
                password=self.config['db_pass']
            )
            return conn
        except Exception as e:
            self.logger.error(f"数据库连接失败: {e}")
            return None

    def check_database(self):
        """检查数据库状态"""
        conn = self.connect()
        if not conn:
            return None

        cursor = conn.cursor()

        try:
            # 统计信息
            cursor.execute("""
                SELECT 
                    COUNT(*) as total_drives,
                    SUM(CASE WHEN start_address_id IS NULL THEN 1 ELSE 0 END) as null_start,
                    SUM(CASE WHEN end_address_id IS NULL THEN 1 ELSE 0 END) as null_end
                FROM drives
                WHERE start_date > NOW() - INTERVAL %s
            """, (f"{self.config['days_to_fix']} days",))

            total, null_start, null_end = cursor.fetchone()

            self.logger.info(f"数据库统计 - 总行程数: {total}, 起点地址为空: {null_start}, 终点地址为空: {null_end}")

            return {
                "total": total,
                "null_start": null_start,
                "null_end": null_end
            }

        finally:
            cursor.close()
            conn.close()

    def get_drives_to_fix(self, limit=None):
        """获取需要修复的行程"""
        conn = self.connect()
        if not conn:
            return []

        cursor = conn.cursor()

        try:
            query = """
                SELECT d.id, d.start_date,
                       d.start_position_id, d.end_position_id,
                       d.start_address_id, d.end_address_id,
                       p_start.latitude as start_lat, p_start.longitude as start_lng,
                       p_end.latitude as end_lat, p_end.longitude as end_lng
                FROM drives d
                LEFT JOIN positions p_start ON d.start_position_id = p_start.id
                LEFT JOIN positions p_end ON d.end_position_id = p_end.id
                WHERE (d.start_address_id IS NULL OR d.end_address_id IS NULL)
                AND d.start_date > NOW() - INTERVAL %s
                ORDER BY d.start_date DESC
            """

            params = [f"{self.config['days_to_fix']} days"]

            if limit:
                query += " LIMIT %s"
                params.append(limit)

            cursor.execute(query, params)
            drives = cursor.fetchall()

            self.logger.info(f"找到 {len(drives)} 条需要修复的行程")
            return drives

        finally:
            cursor.close()
            conn.close()

    def create_address_record(self, cursor, lat, lng, address_info):
        """创建地址记录"""
        if not address_info:
            return None

        # 生成唯一的osm_id（使用坐标哈希）
        coord_hash = abs(hash(f"{lat:.8f},{lng:.8f}")) % (10 ** 15)

        # 先查找相同坐标的地址
        cursor.execute("""
            SELECT id FROM addresses 
            WHERE ABS(latitude - %s) < 0.0001 
            AND ABS(longitude - %s) < 0.0001
            LIMIT 1
        """, (lat, lng))

        existing = cursor.fetchone()
        if existing:
            self.logger.debug(f"已存在相同坐标的地址，ID: {existing[0]}")
            return existing[0]

        # 创建新地址记录
        insert_sql = """
            INSERT INTO addresses 
            (display_name, latitude, longitude, name, house_number, road, neighbourhood, 
             city, county, postcode, state, state_district, country, raw, 
             inserted_at, updated_at, osm_id, osm_type)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW(), %s, %s)
            RETURNING id
        """

        params = (
            address_info['display_name'],
            lat,
            lng,
            address_info.get('street_number', ''),
            address_info.get('street_number', ''),
            address_info.get('street', ''),
            '',
            address_info.get('city', ''),
            address_info.get('district', ''),
            '',
            address_info.get('province', ''),
            address_info.get('district', ''),
            address_info.get('country', '中国'),
            json.dumps(address_info, ensure_ascii=False),
            coord_hash,
            ''
        )

        try:
            cursor.execute(insert_sql, params)
            address_id = cursor.fetchone()[0]
            self.logger.debug(f"创建新地址成功，ID: {address_id}")
            return address_id
        except Exception as e:
            self.logger.error(f"创建地址失败: {e}")
            return None

    def update_drive_address(self, cursor, drive_id, address_id, is_start=True):
        """更新行程的地址ID"""
        column = "start_address_id" if is_start else "end_address_id"
        cursor.execute(
            f"UPDATE drives SET {column} = %s WHERE id = %s",
            (address_id, drive_id)
        )
        return cursor.rowcount > 0


# ============ 修复器主类 ============
class TeslamateAddressFixer:
    """Teslamate地址修复器"""

    def __init__(self, config):
        self.config = config
        self.logger = setup_logging(config['log_level'])
        self.db_manager = DatabaseManager(config)
        self.geocoder = BaiduGeocoder(config['baidu_ak'], config['baidu_sk'])

        # 禁用SSL警告
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    def run_fix(self):
        """执行修复"""
        self.logger.info("=" * 60)
        self.logger.info("开始Teslamate地址修复")
        self.logger.info("=" * 60)

        try:
            # 检查数据库状态
            stats = self.db_manager.check_database()
            if not stats:
                self.logger.error("无法获取数据库状态")
                return False

            total_to_fix = stats['null_start'] + stats['null_end']
            if total_to_fix == 0:
                self.logger.info("没有需要修复的地址")
                return True

            self.logger.info(f"需要修复的地址数量: {total_to_fix}")

            # 获取需要修复的行程
            limit = int(self.config['limit_per_run']) if self.config['limit_per_run'] else None
            drives = self.db_manager.get_drives_to_fix(limit)

            if not drives:
                self.logger.info("没有找到需要修复的行程")
                return True

            # 开始修复
            fixed_count = 0
            error_count = 0
            conn = self.db_manager.connect()

            if not conn:
                return False

            cursor = conn.cursor()

            try:
                for i, drive in enumerate(drives, 1):
                    (drive_id, start_date, start_pos_id, end_pos_id,
                     start_addr_id, end_addr_id, start_lat, start_lng, end_lat, end_lng) = drive

                    self.logger.info(f"[{i}/{len(drives)}] 处理行程 {drive_id} ({start_date})")

                    # 修复起点
                    if start_addr_id is None and start_lat and start_lng:
                        self.logger.debug(f"修复起点坐标: {start_lat:.6f}, {start_lng:.6f}")
                        address_info = self.geocoder.get_address(start_lng, start_lat)

                        if address_info:
                            address_id = self.db_manager.create_address_record(cursor, start_lat, start_lng,
                                                                               address_info)

                            if address_id:
                                if self.db_manager.update_drive_address(cursor, drive_id, address_id, is_start=True):
                                    self.logger.info(f"✅ 起点修复: {address_info['display_name'][:60]}...")
                                    fixed_count += 1
                                else:
                                    self.logger.error(f"❌ 更新起点地址失败")
                                    error_count += 1
                            else:
                                self.logger.error(f"❌ 创建起点地址失败")
                                error_count += 1
                        else:
                            self.logger.error(f"❌ 获取起点地址失败")
                            error_count += 1

                    # 修复终点
                    if end_addr_id is None and end_lat and end_lng:
                        self.logger.debug(f"修复终点坐标: {end_lat:.6f}, {end_lng:.6f}")
                        address_info = self.geocoder.get_address(end_lng, end_lat)

                        if address_info:
                            address_id = self.db_manager.create_address_record(cursor, end_lat, end_lng, address_info)

                            if address_id:
                                if self.db_manager.update_drive_address(cursor, drive_id, address_id, is_start=False):
                                    self.logger.info(f"✅ 终点修复: {address_info['display_name'][:60]}...")
                                    fixed_count += 1
                                else:
                                    self.logger.error(f"❌ 更新终点地址失败")
                                    error_count += 1
                            else:
                                self.logger.error(f"❌ 创建终点地址失败")
                                error_count += 1
                        else:
                            self.logger.error(f"❌ 获取终点地址失败")
                            error_count += 1

                    # 批量提交
                    if i % self.config['batch_size'] == 0:
                        conn.commit()
                        self.logger.debug(f"已提交 {i} 条记录")

                    # 遵守百度API限制
                    if i < len(drives):
                        time.sleep(self.config['api_delay'])

                # 提交剩余更改
                conn.commit()

                self.logger.info("=" * 60)
                self.logger.info(f"修复完成!")
                self.logger.info(f"处理行程: {len(drives)} 条")
                self.logger.info(f"成功修复: {fixed_count} 处地址")
                self.logger.info(f"失败次数: {error_count}")
                self.logger.info("=" * 60)

                return error_count == 0

            except Exception as e:
                self.logger.error(f"修复过程中出错: {e}")
                conn.rollback()
                raise
            finally:
                cursor.close()
                conn.close()

        except Exception as e:
            self.logger.error(f"运行修复时出错: {e}")
            return False


# ============ 主程序入口 ============
def main():
    """主函数"""
    try:
        # 加载配置
        config = load_config()

        # 创建修复器并运行
        fixer = TeslamateAddressFixer(config)
        success = fixer.run_fix()

        if success:
            sys.exit(0)
        else:
            sys.exit(1)

    except ValueError as e:
        print(f"配置错误: {e}")
        print("\n必需的环境变量:")
        print("DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASS - 数据库配置")
        print("BAIDU_AK, BAIDU_SK - 百度地图API配置")
        sys.exit(1)
    except Exception as e:
        print(f"程序错误: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()