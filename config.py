"""
Configuration Management với Environment Variables
File: config.py
"""

import os
from dotenv import load_dotenv
from pathlib import Path

# Load environment variables
load_dotenv()

class Config:
    """Base configuration"""
    
    # MQTT Configuration
    MQTT_BROKER = os.getenv('MQTT_BROKER', 'localhost')
    MQTT_PORT = int(os.getenv('MQTT_PORT', 1883))
    MQTT_USERNAME = os.getenv('MQTT_USERNAME', None)
    MQTT_PASSWORD = os.getenv('MQTT_PASSWORD', None)
    MQTT_TOPIC = os.getenv('MQTT_TOPIC', 'airquality/#')
    MQTT_USE_AUTH = os.getenv('MQTT_USE_AUTH', 'false').lower() == 'true'
    
    # InfluxDB Configuration
    INFLUXDB_URL = os.getenv('INFLUXDB_URL', 'http://localhost:8086')
    INFLUXDB_TOKEN = os.getenv('INFLUXDB_TOKEN', '')
    INFLUXDB_ORG = os.getenv('INFLUXDB_ORG', 'airquality')
    INFLUXDB_BUCKET = os.getenv('INFLUXDB_BUCKET', 'airquality')
    
    # API Configuration
    API_HOST = os.getenv('API_HOST', '0.0.0.0')
    API_PORT = int(os.getenv('API_PORT', 5000))
    API_SECRET_KEY = os.getenv('API_SECRET_KEY', None)
    API_RATE_LIMIT = os.getenv('API_RATE_LIMIT', '100/hour')
    
    # Sensor Configuration
    SENSOR_PM25_MAX = float(os.getenv('SENSOR_PM25_MAX', 500.0))
    SENSOR_PM10_MAX = float(os.getenv('SENSOR_PM10_MAX', 600.0))
    SENSOR_VOC_MAX = float(os.getenv('SENSOR_VOC_MAX', 1000.0))
    SENSOR_TIMEOUT_SECONDS = int(os.getenv('SENSOR_TIMEOUT_SECONDS', 60))
    
    # ML Model Configuration
    ML_MODEL_PATH = os.getenv('ML_MODEL_PATH', './ml_models')
    ML_RETRAIN_INTERVAL_DAYS = int(os.getenv('ML_RETRAIN_INTERVAL_DAYS', 7))
    ML_MIN_DATA_POINTS = int(os.getenv('ML_MIN_DATA_POINTS', 1000))
    
    # Logging Configuration
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
    LOG_FILE = os.getenv('LOG_FILE', './logs/app.log')
    
    @classmethod
    def validate(cls):
        """Validate critical configuration"""
        errors = []
        
        # Check InfluxDB token in production
        if os.getenv('ENVIRONMENT') == 'production':
            if not cls.INFLUXDB_TOKEN:
                errors.append("INFLUXDB_TOKEN must be set in production")
            if not cls.API_SECRET_KEY:
                errors.append("API_SECRET_KEY must be set in production")
            if not cls.MQTT_USE_AUTH:
                errors.append("MQTT authentication should be enabled in production")
        
        if errors:
            raise ValueError(f"Configuration errors: {', '.join(errors)}")
        
        return True

class DevelopmentConfig(Config):
    """Development configuration"""
    DEBUG = True
    MQTT_USE_AUTH = False

class ProductionConfig(Config):
    """Production configuration"""
    DEBUG = False
    MQTT_USE_AUTH = True
    
    @classmethod
    def validate(cls):
        """Additional production checks"""
        super().validate()
        if cls.MQTT_USERNAME is None or cls.MQTT_PASSWORD is None:
            raise ValueError("MQTT credentials required in production")

# Select configuration
ENVIRONMENT = os.getenv('ENVIRONMENT', 'development')
if ENVIRONMENT == 'production':
    config = ProductionConfig()
else:
    config = DevelopmentConfig()

# Validate configuration
config.validate()


# ====================
# .env file example
# ====================
"""
# Save as: .env (in project root)

# Environment
ENVIRONMENT=development

# MQTT Configuration
MQTT_BROKER=192.168.1.100
MQTT_PORT=1883
MQTT_USE_AUTH=true
MQTT_USERNAME=airquality_user
MQTT_PASSWORD=secure_password_here
MQTT_TOPIC=airquality/#

# InfluxDB Configuration
INFLUXDB_URL=http://localhost:8086
INFLUXDB_TOKEN=your_influxdb_token_here
INFLUXDB_ORG=airquality
INFLUXDB_BUCKET=airquality

# API Configuration
API_HOST=0.0.0.0
API_PORT=5000
API_SECRET_KEY=your_secret_key_here_use_random_string
API_RATE_LIMIT=100/hour

# Sensor Limits
SENSOR_PM25_MAX=500.0
SENSOR_PM10_MAX=600.0
SENSOR_VOC_MAX=1000.0
SENSOR_TIMEOUT_SECONDS=60

# ML Configuration
ML_MODEL_PATH=./ml_models
ML_RETRAIN_INTERVAL_DAYS=7
ML_MIN_DATA_POINTS=1000

# Logging
LOG_LEVEL=INFO
LOG_FILE=./logs/app.log
"""
