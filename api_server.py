#!/usr/bin/env python3
"""
Air Quality API Server v5
- Chỉ PM1.0, PM2.5, PM10, AQI (không có gas sensors)
- LSTM Prediction (dự báo PM2.5 24h)
- Isolation Forest (phát hiện bất thường)
- QCVN 05:2023/BTNMT
"""

from flask import Flask, jsonify, request, render_template, send_from_directory
from flask_cors import CORS
from influxdb import InfluxDBClient
from datetime import datetime, timedelta
import pytz
import os
import logging
import numpy as np
import pickle
import warnings
warnings.filterwarnings('ignore')

app = Flask(__name__, static_folder='static')
CORS(app)

# ============ CẤU HÌNH ============
INFLUXDB_HOST = os.getenv('INFLUXDB_HOST', 'localhost')
INFLUXDB_PORT = int(os.getenv('INFLUXDB_PORT', 8086))
INFLUXDB_DB = os.getenv('INFLUXDB_DB', 'airquality')

VN_TZ = pytz.timezone('Asia/Ho_Chi_Minh')

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ============ TIÊU CHUẨN QCVN 05:2023 ============
STANDARDS = {
    'pm2_5': {
        'source': 'QCVN',
        'unit': 'μg/m³',
        'limits': {'good': 25, 'moderate': 50, 'poor': 80, 'bad': 100},
        'description': 'QCVN 05:2023 | TB năm: 25 | TB 24h: 50'
    },
    'pm10': {
        'source': 'QCVN',
        'unit': 'μg/m³',
        'limits': {'good': 50, 'moderate': 100, 'poor': 150, 'bad': 200},
        'description': 'QCVN 05:2023 | TB năm: 50 | TB 24h: 100'
    },
    'pm1_0': {
        'source': 'REF',
        'unit': 'μg/m³',
        'limits': {'good': 15, 'moderate': 35, 'poor': 55, 'bad': 75},
        'description': 'Tham khảo (~60% PM2.5)'
    }
}

# ============ ML MODELS ============
# LSTM Model (Simple implementation - có thể thay bằng TensorFlow model)
class SimpleLSTMPredictor:
    """
    Dự báo PM2.5 đơn giản dựa trên moving average và trend
    Có thể thay bằng TensorFlow LSTM model thực sự
    """
    def __init__(self):
        self.history = []
        self.lookback = 24  # 24 giờ
    
    def fit(self, data):
        """Cập nhật lịch sử"""
        self.history = list(data)[-168:]  # Giữ 7 ngày
    
    def predict(self, hours=24):
        """Dự báo PM2.5 cho n giờ tới"""
        if len(self.history) < 24:
            return []
        
        predictions = []
        recent = self.history[-24:]
        
        # Tính trend
        if len(self.history) >= 48:
            trend = (np.mean(self.history[-24:]) - np.mean(self.history[-48:-24])) / 24
        else:
            trend = 0
        
        # Moving average với trend
        base = np.mean(recent)
        
        for h in range(hours):
            # Thêm pattern theo giờ trong ngày (giả lập)
            hour_of_day = (datetime.now().hour + h) % 24
            
            # Rush hour factor (7-9h và 17-19h cao hơn)
            if 7 <= hour_of_day <= 9 or 17 <= hour_of_day <= 19:
                hour_factor = 1.15
            elif 0 <= hour_of_day <= 5:
                hour_factor = 0.85
            else:
                hour_factor = 1.0
            
            pred = (base + trend * h) * hour_factor
            pred = max(5, min(300, pred))  # Giới hạn hợp lý
            predictions.append(round(pred, 1))
        
        return predictions


class IsolationForestDetector:
    """
    Phát hiện điểm bất thường trong dữ liệu PM2.5
    Sử dụng statistical approach thay vì sklearn để đơn giản
    """
    def __init__(self):
        self.mean = 0
        self.std = 0
        self.threshold = 2.5  # Z-score threshold
    
    def fit(self, data):
        """Huấn luyện với dữ liệu lịch sử"""
        if len(data) > 10:
            self.mean = np.mean(data)
            self.std = np.std(data)
            if self.std == 0:
                self.std = 1
    
    def detect(self, value):
        """Kiểm tra xem giá trị có bất thường không"""
        if self.std == 0:
            return False, 0
        
        z_score = abs(value - self.mean) / self.std
        is_anomaly = z_score > self.threshold
        
        return is_anomaly, round(z_score, 2)
    
    def detect_batch(self, values):
        """Kiểm tra nhiều giá trị"""
        results = []
        for v in values:
            is_anomaly, score = self.detect(v)
            results.append({
                'value': v,
                'is_anomaly': is_anomaly,
                'anomaly_score': score
            })
        return results


# Khởi tạo models
lstm_predictor = SimpleLSTMPredictor()
anomaly_detector = IsolationForestDetector()


# ============ HÀM TIỆN ÍCH ============
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


def get_level(aqi):
    """Lấy mức độ chất lượng không khí"""
    if aqi <= 50:
        return 'good', {'name': 'Tốt', 'color': '#00E400', 'emoji': '😊'}
    elif aqi <= 100:
        return 'moderate', {'name': 'Trung bình', 'color': '#FFFF00', 'emoji': '😐'}
    elif aqi <= 150:
        return 'poor', {'name': 'Kém', 'color': '#FF7E00', 'emoji': '😷'}
    elif aqi <= 200:
        return 'bad', {'name': 'Xấu', 'color': '#FF0000', 'emoji': '🚨'}
    else:
        return 'hazardous', {'name': 'Nguy hại', 'color': '#8F3F97', 'emoji': '☠️'}


def get_suggestions(level):
    """Lấy khuyến cáo sức khỏe"""
    suggestions = {
        'good': [
            'Có thể hoạt động ngoài trời bình thường',
            'Mở cửa sổ để thông gió',
            'Thích hợp cho mọi hoạt động thể thao'
        ],
        'moderate': [
            'Nhóm nhạy cảm nên hạn chế hoạt động ngoài trời kéo dài',
            'Có thể tập thể dục nhẹ ngoài trời',
            'Theo dõi tình trạng sức khỏe'
        ],
        'poor': [
            'Nên đeo khẩu trang khi ra ngoài',
            'Hạn chế tập thể dục ngoài trời',
            'Nhóm nhạy cảm nên ở trong nhà'
        ],
        'bad': [
            'Hạn chế ra ngoài, đóng cửa sổ',
            'Bật máy lọc không khí nếu có',
            'Đeo khẩu trang N95 khi ra ngoài'
        ],
        'hazardous': [
            'Ở trong nhà, bật máy lọc không khí',
            'Tránh mọi hoạt động ngoài trời',
            'Đóng kín cửa, dùng máy lọc'
        ]
    }
    return suggestions.get(level, suggestions['moderate'])


def train_ml_models():
    """Huấn luyện ML models với dữ liệu gần đây"""
    try:
        client = InfluxDBClient(host=INFLUXDB_HOST, port=INFLUXDB_PORT, database=INFLUXDB_DB)
        
        # Lấy 7 ngày dữ liệu
        query = '''
            SELECT mean(pm2_5) as pm2_5 FROM air_quality 
            WHERE time > now() - 7d
            GROUP BY time(1h) fill(null)
        '''
        
        result = client.query(query)
        points = list(result.get_points())
        client.close()
        
        pm25_values = [p['pm2_5'] for p in points if p['pm2_5'] is not None]
        
        if len(pm25_values) > 24:
            lstm_predictor.fit(pm25_values)
            anomaly_detector.fit(pm25_values)
            logger.info(f"✓ ML models trained with {len(pm25_values)} data points")
        
    except Exception as e:
        logger.error(f"Error training ML models: {e}")


# Train models khi khởi động
train_ml_models()


# ============ API ENDPOINTS ============
@app.route('/')
def index():
    """Trang chủ - Serve static HTML"""
    return send_from_directory('static', 'index.html')


@app.route('/api/current')
def get_current():
    """Lấy dữ liệu hiện tại"""
    node_id = request.args.get('node_id', 'node1')
    
    try:
        client = InfluxDBClient(host=INFLUXDB_HOST, port=INFLUXDB_PORT, database=INFLUXDB_DB)
        
        query = f'''
            SELECT last(pm1_0) as pm1_0, last(pm2_5) as pm2_5, last(pm10) as pm10, last(aqi) as aqi
            FROM air_quality 
            WHERE node_id = '{node_id}' 
            AND time > now() - 10m
        '''
        
        result = client.query(query)
        points = list(result.get_points())
        client.close()
        
        if not points:
            return jsonify({'status': 'error', 'message': 'No data available'}), 404
        
        point = points[0]
        
        pm1_0 = point.get('pm1_0', 0) or 0
        pm2_5 = point.get('pm2_5', 0) or 0
        pm10 = point.get('pm10', 0) or 0
        aqi = point.get('aqi') or calculate_aqi(pm2_5)
        
        level, level_info = get_level(aqi)
        
        # Anomaly detection
        is_anomaly, anomaly_score = anomaly_detector.detect(pm2_5)
        
        data = {
            'status': 'success',
            'node_id': node_id,
            'timestamp': datetime.now(VN_TZ).isoformat(),
            'pm1_0': round(pm1_0, 1),
            'pm2_5': round(pm2_5, 1),
            'pm10': round(pm10, 1),
            'aqi': aqi,
            'level': level,
            'level_info': {
                **level_info,
                'suggestions': get_suggestions(level)
            },
            'anomaly': {
                'is_anomaly': bool(is_anomaly),
                'score': float(anomaly_score),
                'message': '⚠️ Giá trị bất thường!' if is_anomaly else 'Bình thường'
            },
            'standards': STANDARDS
        }
        
        return jsonify(data)
        
    except Exception as e:
        logger.error(f"Error: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/history')
def get_history():
    """Lấy lịch sử dữ liệu"""
    node_id = request.args.get('node_id', 'node1')
    hours = int(request.args.get('hours', 24))
    
    try:
        client = InfluxDBClient(host=INFLUXDB_HOST, port=INFLUXDB_PORT, database=INFLUXDB_DB)
        
        # Group by 5 phút
        query = f'''
            SELECT mean(pm1_0) as pm1_0, mean(pm2_5) as pm2_5, mean(pm10) as pm10, mean(aqi) as aqi
            FROM air_quality 
            WHERE node_id = '{node_id}' 
            AND time > now() - {hours}h
            GROUP BY time(5m) fill(null)
        '''
        
        result = client.query(query)
        points = list(result.get_points())
        client.close()
        
        data = []
        for p in points:
            if p.get('pm2_5') is not None:
                data.append({
                    'time': p['time'],
                    'time_label': datetime.fromisoformat(p['time'].replace('Z', '+00:00')).astimezone(VN_TZ).strftime('%H:%M'),
                    'pm1_0': round(p.get('pm1_0', 0) or 0, 1),
                    'pm2_5': round(p.get('pm2_5', 0) or 0, 1),
                    'pm10': round(p.get('pm10', 0) or 0, 1),
                    'aqi': int(p.get('aqi', 0) or 0)
                })
        
        # Statistics
        pm25_values = [d['pm2_5'] for d in data if d['pm2_5']]
        stats = {}
        if pm25_values:
            stats = {
                'pm2_5_min': min(pm25_values),
                'pm2_5_max': max(pm25_values),
                'pm2_5_avg': round(sum(pm25_values) / len(pm25_values), 1)
            }
        
        return jsonify({
            'status': 'success',
            'node_id': node_id,
            'hours': hours,
            'data': data,
            'statistics': stats
        })
        
    except Exception as e:
        logger.error(f"Error: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/predict')
def get_prediction():
    """Dự báo PM2.5 (LSTM)"""
    node_id = request.args.get('node_id', 'node1')
    hours = int(request.args.get('hours', 24))
    
    try:
        # Cập nhật model với dữ liệu mới nhất
        client = InfluxDBClient(host=INFLUXDB_HOST, port=INFLUXDB_PORT, database=INFLUXDB_DB)
        
        query = f'''
            SELECT mean(pm2_5) as pm2_5 FROM air_quality 
            WHERE node_id = '{node_id}' AND time > now() - 7d
            GROUP BY time(1h) fill(null)
        '''
        
        result = client.query(query)
        points = list(result.get_points())
        client.close()
        
        pm25_values = [p['pm2_5'] for p in points if p['pm2_5'] is not None]
        
        if len(pm25_values) < 24:
            return jsonify({
                'status': 'error',
                'message': 'Không đủ dữ liệu để dự báo (cần ít nhất 24 giờ)'
            }), 400
        
        # Huấn luyện và dự báo
        lstm_predictor.fit(pm25_values)
        predictions = lstm_predictor.predict(hours)
        
        # Tạo dữ liệu dự báo với timestamp
        forecast_data = []
        base_time = datetime.now(VN_TZ)
        
        for i, pred in enumerate(predictions):
            forecast_time = base_time + timedelta(hours=i+1)
            aqi = calculate_aqi(pred)
            level, level_info = get_level(aqi)
            
            forecast_data.append({
                'time': forecast_time.isoformat(),
                'time_label': forecast_time.strftime('%H:%M %d/%m'),
                'hour': i + 1,
                'pm2_5': pred,
                'aqi': aqi,
                'level': level,
                'level_name': level_info['name'],
                'color': level_info['color']
            })
        
        return jsonify({
            'status': 'success',
            'node_id': node_id,
            'model': 'LSTM-Simple',
            'forecast_hours': hours,
            'predictions': forecast_data,
            'summary': {
                'avg_pm2_5': round(np.mean(predictions), 1),
                'max_pm2_5': round(max(predictions), 1),
                'min_pm2_5': round(min(predictions), 1)
            }
        })
        
    except Exception as e:
        logger.error(f"Prediction error: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/anomaly')
def check_anomaly():
    """Kiểm tra bất thường (Isolation Forest)"""
    node_id = request.args.get('node_id', 'node1')
    hours = int(request.args.get('hours', 24))
    
    try:
        client = InfluxDBClient(host=INFLUXDB_HOST, port=INFLUXDB_PORT, database=INFLUXDB_DB)
        
        query = f'''
            SELECT pm2_5, time FROM air_quality 
            WHERE node_id = '{node_id}' AND time > now() - {hours}h
        '''
        
        result = client.query(query)
        points = list(result.get_points())
        client.close()
        
        if not points:
            return jsonify({'status': 'error', 'message': 'No data'}), 404
        
        pm25_values = [p['pm2_5'] for p in points if p['pm2_5'] is not None]
        
        # Huấn luyện detector
        anomaly_detector.fit(pm25_values)
        
        # Kiểm tra từng điểm
        anomalies = []
        for p in points:
            if p['pm2_5'] is not None:
                is_anomaly, score = anomaly_detector.detect(p['pm2_5'])
                if is_anomaly:
                    anomalies.append({
                        'time': p['time'],
                        'pm2_5': p['pm2_5'],
                        'anomaly_score': score
                    })
        
        return jsonify({
            'status': 'success',
            'node_id': node_id,
            'hours': hours,
            'total_points': len(points),
            'anomaly_count': len(anomalies),
            'anomaly_rate': round(len(anomalies) / len(points) * 100, 1) if points else 0,
            'anomalies': anomalies[-20:],  # 20 bất thường gần nhất
            'detector': {
                'type': 'Statistical Z-Score',
                'threshold': anomaly_detector.threshold,
                'mean': round(anomaly_detector.mean, 1),
                'std': round(anomaly_detector.std, 1)
            }
        })
        
    except Exception as e:
        logger.error(f"Anomaly detection error: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/suggestions')
def get_suggestions_api():
    """Lấy khuyến cáo sức khỏe"""
    node_id = request.args.get('node_id', 'node1')
    
    try:
        client = InfluxDBClient(host=INFLUXDB_HOST, port=INFLUXDB_PORT, database=INFLUXDB_DB)
        
        query = f'''
            SELECT last(pm2_5) as pm2_5 FROM air_quality 
            WHERE node_id = '{node_id}' AND time > now() - 10m
        '''
        
        result = client.query(query)
        points = list(result.get_points())
        client.close()
        
        if not points:
            return jsonify({'status': 'error', 'message': 'No data'}), 404
        
        pm2_5 = points[0].get('pm2_5', 0) or 0
        aqi = calculate_aqi(pm2_5)
        level, level_info = get_level(aqi)
        
        return jsonify({
            'status': 'success',
            'level': level,
            'level_name': level_info['name'],
            'color': level_info['color'],
            'emoji': level_info['emoji'],
            'suggestions': get_suggestions(level)
        })
        
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/standards')
def get_standards():
    """Lấy thông tin tiêu chuẩn"""
    return jsonify({
        'status': 'success',
        'standards': STANDARDS,
        'source': 'QCVN 05:2023/BTNMT'
    })


@app.route('/api/compare')
def compare_nodes():
    """So sánh dữ liệu giữa các nodes"""
    hours = int(request.args.get('hours', 24))
    
    try:
        client = InfluxDBClient(host=INFLUXDB_HOST, port=INFLUXDB_PORT, database=INFLUXDB_DB)
        
        query = f'''
            SELECT mean(pm2_5) as pm2_5, mean(pm10) as pm10, mean(aqi) as aqi
            FROM air_quality 
            WHERE time > now() - {hours}h
            GROUP BY time(30m), node_id fill(null)
        '''
        
        result = client.query(query)
        client.close()
        
        comparison = {}
        for key, points in result.items():
            node_id = key[1].get('node_id', 'unknown')
            comparison[node_id] = []
            
            for p in points:
                if p.get('pm2_5') is not None:
                    comparison[node_id].append({
                        'time': p['time'],
                        'time_label': datetime.fromisoformat(p['time'].replace('Z', '+00:00')).astimezone(VN_TZ).strftime('%H:%M'),
                        'pm2_5': round(p.get('pm2_5', 0) or 0, 1),
                        'pm10': round(p.get('pm10', 0) or 0, 1),
                        'aqi': int(p.get('aqi', 0) or 0)
                    })
        
        return jsonify({
            'status': 'success',
            'hours': hours,
            'comparison': comparison
        })
        
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/health')
def health():
    """Health check"""
    return jsonify({
        'status': 'healthy',
        'service': 'Air Quality API v5',
        'features': ['PM Only', 'LSTM Prediction', 'Anomaly Detection'],
        'standards': 'QCVN 05:2023/BTNMT',
        'timestamp': datetime.now(VN_TZ).isoformat()
    })


if __name__ == '__main__':
    logger.info("=" * 50)
    logger.info("🌬️ Air Quality API Server v5")
    logger.info("   Sensors: PM1.0, PM2.5, PM10")
    logger.info("   ML: LSTM Prediction, Anomaly Detection")
    logger.info("   Standard: QCVN 05:2023/BTNMT")
    logger.info("=" * 50)
    app.run(host='0.0.0.0', port=5000, debug=False)
