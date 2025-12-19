#!/usr/bin/env python3
"""
Firebase Push Notification Service for Air Quality Alerts
Gửi cảnh báo khi chất lượng không khí xấu theo QCVN 05:2023/BTNMT
"""

import firebase_admin
from firebase_admin import credentials, messaging
from influxdb import InfluxDBClient
import time
import logging
import json
import os
from datetime import datetime
import pytz

# ============ CẤU HÌNH ============
FIREBASE_CRED_PATH = os.path.expanduser("~/airquality_project/firebase-credentials.json")
INFLUXDB_HOST = "localhost"
INFLUXDB_PORT = 8086
INFLUXDB_DB = "airquality"

CHECK_INTERVAL = 60  # Kiểm tra mỗi 60 giây
ALERT_COOLDOWN = 1800  # Không gửi lại trong 30 phút

# File lưu FCM tokens
FCM_TOKENS_FILE = os.path.expanduser("~/airquality_project/fcm_tokens.json")

# ============ NGƯỠNG CẢNH BÁO THEO QCVN 05:2023/BTNMT ============
THRESHOLDS = {
    'pm2_5': {
        'moderate': 25,      # Vượt TB năm
        'poor': 50,          # Vượt TB 24h
        'bad': 80,           # Xấu
        'hazardous': 100     # Nguy hại
    },
    'pm10': {
        'moderate': 50,
        'poor': 100,
        'bad': 150,
        'hazardous': 200
    },
    'co2_ppm': {  # WHO Indoor
        'moderate': 800,
        'poor': 1000,
        'bad': 1500,
        'hazardous': 2000
    },
    'co_ppm': {  # QCVN
        'poor': 9,
        'bad': 15,
        'hazardous': 26
    }
}

# ============ SETUP LOGGING ============
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.expanduser("~/airquality_project/notification.log")),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ============ BIẾN TOÀN CỤC ============
last_alert_time = {}  # {node_id: timestamp}
fcm_tokens = []

# ============ KHỞI TẠO FIREBASE ============
def init_firebase():
    """Khởi tạo Firebase Admin SDK"""
    try:
        if not os.path.exists(FIREBASE_CRED_PATH):
            logger.error(f"Firebase credentials not found: {FIREBASE_CRED_PATH}")
            return False
        
        cred = credentials.Certificate(FIREBASE_CRED_PATH)
        firebase_admin.initialize_app(cred)
        logger.info("✓ Firebase initialized")
        return True
    except Exception as e:
        logger.error(f"Firebase init error: {e}")
        return False

# ============ QUẢN LÝ FCM TOKENS ============
def load_fcm_tokens():
    """Tải danh sách FCM tokens từ file"""
    global fcm_tokens
    try:
        if os.path.exists(FCM_TOKENS_FILE):
            with open(FCM_TOKENS_FILE, 'r') as f:
                data = json.load(f)
                fcm_tokens = data.get('tokens', [])
        logger.info(f"Loaded {len(fcm_tokens)} FCM tokens")
    except Exception as e:
        logger.error(f"Error loading FCM tokens: {e}")
        fcm_tokens = []

def save_fcm_token(token, user_id=None):
    """Lưu FCM token mới"""
    global fcm_tokens
    if token not in fcm_tokens:
        fcm_tokens.append(token)
        try:
            with open(FCM_TOKENS_FILE, 'w') as f:
                json.dump({'tokens': fcm_tokens, 'updated': datetime.now().isoformat()}, f)
            logger.info(f"Saved new FCM token: {token[:20]}...")
        except Exception as e:
            logger.error(f"Error saving FCM token: {e}")

def remove_invalid_token(token):
    """Xóa token không hợp lệ"""
    global fcm_tokens
    if token in fcm_tokens:
        fcm_tokens.remove(token)
        try:
            with open(FCM_TOKENS_FILE, 'w') as f:
                json.dump({'tokens': fcm_tokens}, f)
        except:
            pass

# ============ ĐÁNH GIÁ MỨC ĐỘ ============
def get_air_quality_level(pm25, pm10=None, co2=None, co=None):
    """Đánh giá mức độ chất lượng không khí theo QCVN"""
    if pm25 > THRESHOLDS['pm2_5']['hazardous']:
        return 'hazardous', 'Nguy hại', '☠️'
    elif pm25 > THRESHOLDS['pm2_5']['bad']:
        return 'bad', 'Xấu', '🚨'
    elif pm25 > THRESHOLDS['pm2_5']['poor']:
        return 'poor', 'Kém', '😷'
    elif pm25 > THRESHOLDS['pm2_5']['moderate']:
        return 'moderate', 'Trung bình', '😐'
    else:
        return 'good', 'Tốt', '😊'

def should_alert(level):
    """Kiểm tra có cần gửi cảnh báo không"""
    # Chỉ cảnh báo khi mức Kém trở lên
    return level in ['poor', 'bad', 'hazardous']

# ============ GỬI NOTIFICATION ============
def send_notification(node_id, level, level_name, pm25, pm10, co2, emoji):
    """Gửi push notification qua Firebase"""
    global last_alert_time
    
    # Kiểm tra cooldown
    now = time.time()
    key = f"{node_id}_{level}"
    if key in last_alert_time:
        if now - last_alert_time[key] < ALERT_COOLDOWN:
            logger.debug(f"Skipping alert for {node_id} (cooldown)")
            return False
    
    if not fcm_tokens:
        logger.warning("No FCM tokens registered")
        return False
    
    # Tạo message
    title = f"{emoji} Cảnh báo không khí - {level_name}"
    body = f"Node {node_id}: PM2.5={pm25:.0f} μg/m³"
    if pm10:
        body += f", PM10={pm10:.0f}"
    if co2 and co2 > 800:
        body += f", CO2={co2:.0f} ppm"
    
    # Tạo data payload
    data = {
        'node_id': node_id,
        'level': level,
        'pm2_5': str(pm25),
        'pm10': str(pm10 or 0),
        'co2_ppm': str(co2 or 0),
        'timestamp': datetime.now().isoformat(),
        'click_action': 'FLUTTER_NOTIFICATION_CLICK'
    }
    
    # Gửi đến từng token
    success_count = 0
    for token in fcm_tokens[:]:
        try:
            message = messaging.Message(
                notification=messaging.Notification(
                    title=title,
                    body=body
                ),
                data=data,
                token=token,
                android=messaging.AndroidConfig(
                    priority='high',
                    notification=messaging.AndroidNotification(
                        icon='ic_notification',
                        color='#FF5722',
                        sound='default',
                        channel_id='air_quality_alerts'
                    )
                )
            )
            
            response = messaging.send(message)
            logger.info(f"✓ Notification sent: {response}")
            success_count += 1
            
        except messaging.UnregisteredError:
            logger.warning(f"Token unregistered, removing: {token[:20]}...")
            remove_invalid_token(token)
        except Exception as e:
            logger.error(f"Send error: {e}")
    
    if success_count > 0:
        last_alert_time[key] = now
        return True
    
    return False

# ============ KIỂM TRA DỮ LIỆU ============
def check_air_quality():
    """Kiểm tra chất lượng không khí và gửi cảnh báo nếu cần"""
    try:
        client = InfluxDBClient(host=INFLUXDB_HOST, port=INFLUXDB_PORT, database=INFLUXDB_DB)
        
        # Lấy dữ liệu mới nhất từ mỗi node
        query = """
            SELECT last(pm2_5) as pm2_5, last(pm10) as pm10, 
                   last(co2_ppm) as co2_ppm, last(co_ppm) as co_ppm
            FROM air_quality 
            WHERE time > now() - 5m 
            GROUP BY node_id
        """
        
        result = client.query(query)
        
        for key, points in result.items():
            node_id = key[1].get('node_id', 'unknown')
            
            for point in points:
                pm25 = point.get('pm2_5', 0) or 0
                pm10 = point.get('pm10', 0) or 0
                co2 = point.get('co2_ppm', 0) or 0
                co = point.get('co_ppm', 0) or 0
                
                # Đánh giá mức độ
                level, level_name, emoji = get_air_quality_level(pm25, pm10, co2, co)
                
                logger.info(f"Node {node_id}: PM2.5={pm25:.1f}, Level={level_name}")
                
                # Gửi cảnh báo nếu cần
                if should_alert(level):
                    send_notification(node_id, level, level_name, pm25, pm10, co2, emoji)
        
        client.close()
        
    except Exception as e:
        logger.error(f"Check error: {e}")

# ============ API ENDPOINT CHO FCM TOKEN ============
# Thêm vào api_server_v3.py:
"""
@app.route('/api/register-fcm', methods=['POST'])
def register_fcm():
    data = request.json
    token = data.get('token')
    user_id = data.get('user_id', 'anonymous')
    
    if token:
        # Gọi hàm save_fcm_token
        from notification_service import save_fcm_token
        save_fcm_token(token, user_id)
        return jsonify({'status': 'success', 'message': 'Token registered'})
    
    return jsonify({'status': 'error', 'message': 'Token required'}), 400
"""

# ============ MAIN ============
def main():
    logger.info("🔔 Air Quality Notification Service")
    logger.info("   QCVN 05:2023/BTNMT + WHO 2021")
    logger.info("=" * 50)
    
    # Khởi tạo Firebase
    if not init_firebase():
        logger.error("Failed to initialize Firebase. Exiting.")
        return
    
    # Tải FCM tokens
    load_fcm_tokens()
    
    # Vòng lặp chính
    logger.info(f"Starting monitoring (interval: {CHECK_INTERVAL}s)")
    
    while True:
        try:
            check_air_quality()
            time.sleep(CHECK_INTERVAL)
        except KeyboardInterrupt:
            logger.info("Shutting down...")
            break
        except Exception as e:
            logger.error(f"Main loop error: {e}")
            time.sleep(10)

if __name__ == '__main__':
    main()
