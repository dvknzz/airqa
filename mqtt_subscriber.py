#!/usr/bin/env python3
"""
MQTT Subscriber for Air Quality - PM Only
Chỉ đo PM1.0, PM2.5, PM10 từ PMS7003
Loại bỏ: CO2, CO, NH4, VOC (không có MQ135)
"""

import paho.mqtt.client as mqtt
from influxdb import InfluxDBClient
import json
import ssl
import time
import logging
from datetime import datetime
import pytz

# ============ CẤU HÌNH ============
# HiveMQ Cloud
MQTT_HOST = "ec9fce1996da4e5d818fb192318fb273.s1.eu.hivemq.cloud"
MQTT_PORT = 8883
MQTT_USER = "admin"
MQTT_PASSWORD = "Dvkn2403"
MQTT_TOPIC = "airquality/sensors"

# InfluxDB
INFLUXDB_HOST = "localhost"
INFLUXDB_PORT = 8086
INFLUXDB_DB = "airquality"

# Timezone
VN_TZ = pytz.timezone('Asia/Ho_Chi_Minh')

# Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('mqtt_cloud.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# InfluxDB client
influx_client = None

# ============ TÍNH AQI THEO QCVN ============
def calculate_aqi(pm25):
    """Tính AQI theo QCVN 05:2023/BTNMT"""
    breakpoints = [
        (0, 25, 0, 50),
        (25, 50, 50, 100),
        (50, 80, 100, 150),
        (80, 150, 150, 200),
        (150, 250, 200, 300),
        (250, 500, 300, 500)
    ]
    
    for c_lo, c_hi, i_lo, i_hi in breakpoints:
        if c_lo <= pm25 <= c_hi:
            aqi = ((i_hi - i_lo) / (c_hi - c_lo)) * (pm25 - c_lo) + i_lo
            return int(round(aqi))
    return 500 if pm25 > 500 else 0

# ============ MQTT CALLBACKS ============
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        logger.info("✓ Connected to HiveMQ Cloud")
        client.subscribe(MQTT_TOPIC)
        logger.info(f"✓ Subscribed to {MQTT_TOPIC}")
    else:
        logger.error(f"✗ Connection failed, code: {rc}")

def on_message(client, userdata, msg):
    global influx_client
    
    try:
        payload = json.loads(msg.payload.decode())
        
        node_id = payload.get('node_id', 'unknown')
        pm1_0 = float(payload.get('pm1_0', 0))
        pm2_5 = float(payload.get('pm2_5', 0))
        pm10 = float(payload.get('pm10', 0))
        
        # Tính AQI
        aqi = payload.get('aqi') or calculate_aqi(pm2_5)
        
        # Log
        logger.info(f"📊 {node_id}: PM1.0={pm1_0}, PM2.5={pm2_5}, PM10={pm10}, AQI={aqi}")
        
        # Lưu vào InfluxDB
        json_body = [{
            "measurement": "air_quality",
            "tags": {
                "node_id": node_id
            },
            "time": datetime.now(VN_TZ).isoformat(),
            "fields": {
                "pm1_0": pm1_0,
                "pm2_5": pm2_5,
                "pm10": pm10,
                "aqi": aqi
            }
        }]
        
        if influx_client:
            influx_client.write_points(json_body)
            logger.debug("✓ Saved to InfluxDB")
        
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error: {e}")
    except Exception as e:
        logger.error(f"Error processing message: {e}")

def on_disconnect(client, userdata, rc):
    logger.warning(f"Disconnected from MQTT broker (rc={rc})")
    if rc != 0:
        logger.info("Attempting to reconnect...")

# ============ MAIN ============
def main():
    global influx_client
    
    logger.info("=" * 50)
    logger.info("🌬️ Air Quality MQTT Subscriber")
    logger.info("   Sensors: PMS7003 (PM1.0, PM2.5, PM10)")
    logger.info("   Standard: QCVN 05:2023/BTNMT")
    logger.info("=" * 50)
    
    # Kết nối InfluxDB
    try:
        influx_client = InfluxDBClient(
            host=INFLUXDB_HOST,
            port=INFLUXDB_PORT,
            database=INFLUXDB_DB
        )
        # Tạo database nếu chưa có
        influx_client.create_database(INFLUXDB_DB)
        logger.info("✓ Connected to InfluxDB")
    except Exception as e:
        logger.error(f"InfluxDB connection error: {e}")
        return
    
    # Kết nối MQTT
    mqtt_client = mqtt.Client(client_id=f"rpi-subscriber-{int(time.time())}")
    mqtt_client.username_pw_set(MQTT_USER, MQTT_PASSWORD)
    
    # SSL/TLS
    mqtt_client.tls_set(cert_reqs=ssl.CERT_REQUIRED, tls_version=ssl.PROTOCOL_TLS)
    
    # Callbacks
    mqtt_client.on_connect = on_connect
    mqtt_client.on_message = on_message
    mqtt_client.on_disconnect = on_disconnect
    
    # Kết nối
    try:
        logger.info(f"🔌 Connecting to {MQTT_HOST}:{MQTT_PORT}...")
        mqtt_client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
        mqtt_client.loop_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    except Exception as e:
        logger.error(f"MQTT connection error: {e}")
    finally:
        mqtt_client.disconnect()
        if influx_client:
            influx_client.close()

if __name__ == '__main__':
    main()
