#!/bin/bash
# Fix API server and restart

cd ~/airquality_project

# Kill existing processes
echo "Stopping existing processes..."
pkill -f api_server_improved.py
pkill -f mqtt_subscriber_improved.py
sleep 2

# Activate venv
source venv/bin/activate

# Create logs directory if not exists
mkdir -p logs

# Start MQTT Subscriber
echo "Starting MQTT Subscriber..."
nohup python3 mqtt_subscriber_improved.py > logs/mqtt_sub.log 2>&1 &
sleep 2

# Start API Server
echo "Starting API Server..."
nohup python3 api_server_improved.py > logs/api_server.log 2>&1 &
sleep 2

# Check processes
echo ""
echo "Checking processes..."
ps aux | grep -E "mqtt_subscriber|api_server" | grep -v grep

# Test API
echo ""
echo "Testing API..."
sleep 3
curl -s http://192.168.0.7:5000/health | python3 -m json.tool

echo ""
echo "✅ Done! Services started."
echo ""
echo "Check logs:"
echo "  tail -f logs/mqtt_sub.log"
echo "  tail -f logs/api_server.log"
echo ""
echo "Test API:"
echo "  curl http://192.168.0.7:5000/health"
echo "  curl http://192.168.0.7:5000/api/current?node_id=node1"
