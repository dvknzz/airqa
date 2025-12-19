/*
 * ESP32 Air Quality Node - PMS7003 Only
 * Chỉ đo: PM1.0, PM2.5, PM10
 * Tiêu chuẩn: QCVN 05:2023/BTNMT
 * 
 * Kết nối PMS7003:
 *   VCC → 5V
 *   GND → GND
 *   TX  → GPIO16 (RX2)
 *   RX  → GPIO17 (TX2)
 */

#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <HardwareSerial.h>

// ============ CẤU HÌNH WIFI ============
const char* WIFI_SSID = "dvkn.thta";       // ← THAY ĐỔI
const char* WIFI_PASSWORD = "Dvkn2403";   // ← THAY ĐỔI

// ============ CẤU HÌNH MQTT - HIVEMQ CLOUD ============
const char* MQTT_HOST = "ec9fce1996da4e5d818fb192318fb273.s1.eu.hivemq.cloud";
const int MQTT_PORT = 8883;
const char* MQTT_USER = "admin";
const char* MQTT_PASSWORD = "Dvkn2403";
const char* MQTT_TOPIC = "airquality/sensors";

// ============ CẤU HÌNH NODE ============
const char* NODE_ID = "node1";  // Đổi thành "node2" cho node thứ 2

// ============ CHÂN KẾT NỐI ============
#define PMS_RX 16
#define PMS_TX 17

// ============ BIẾN TOÀN CỤC ============
HardwareSerial pmsSerial(2);
WiFiClientSecure wifiClient;
PubSubClient mqtt(wifiClient);

unsigned long lastSendTime = 0;
const unsigned long SEND_INTERVAL = 30000;  // 30 giây

// Dữ liệu PMS7003
struct PMSData {
    uint16_t pm1_0;
    uint16_t pm2_5;
    uint16_t pm10;
    bool valid;
};

// ============ HiveMQ Cloud Root CA ============
const char* root_ca = R"EOF(
-----BEGIN CERTIFICATE-----
MIIFazCCA1OgAwIBAgIRAIIQz7DSQONZRGPgu2OCiwAwDQYJKoZIhvcNAQELBQAw
TzELMAkGA1UEBhMCVVMxKTAnBgNVBAoTIEludGVybmV0IFNlY3VyaXR5IFJlc2Vh
cmNoIEdyb3VwMRUwEwYDVQQDEwxJU1JHIFJvb3QgWDEwHhcNMTUwNjA0MTEwNDM4
WhcNMzUwNjA0MTEwNDM4WjBPMQswCQYDVQQGEwJVUzEpMCcGA1UEChMgSW50ZXJu
ZXQgU2VjdXJpdHkgUmVzZWFyY2ggR3JvdXAxFTATBgNVBAMTDElTUkcgUm9vdCBY
MTCCAiIwDQYJKoZIhvcNAQEBBQADggIPADCCAgoCggIBAK3oJHP0FDfzm54rVygc
h77ct984kIxuPOZXoHj3dcKi/vVqbvYATyjb3miGbESTtrFj/RQSa78f0uoxmyF+
0TM8ukj13Xnfs7j/EvEhmkvBioZxaUpmZmyPfjxwv60pIgbz5MDmgK7iS4+3mX6U
A5/TR5d8mUgjU+g4rk8Kb4Mu0UlXjIB0ttov0DiNewNwIRt18jA8+o+u3dpjq+sW
T8KOEUt+zwvo/7V3LvSye0rgTBIlDHCNAymg4VMk7BPZ7hm/ELNKjD+Jo2FR3qyH
B5T0Y3HsLuJvW5iB4YlcNHlsdu87kGJ55tukmi8mxdAQ4Q7e2RCOFvu396j3x+UC
B5iPNgiV5+I3lg02dZ77DnKxHZu8A/lJBdiB3QW0KtZB6awBdpUKD9jf1b0SHzUv
KBds0pjBqAlkd25HN7rOrFleaJ1/ctaJxQZBKT5ZPt0m9STJEadao0xAH0ahmbWn
OlFuhjuefXKnEgV4We0+UXgVCwOPjdAvBbI+e0ocS3MFEvzG6uBQE3xDk3SzynTn
jh8BCNAw1FtxNrQHusEwMFxIt4I7mKZ9YIqioymCzLq9gwQbooMDQaHWBfEbwrbw
qHyGO0aoSCqI3Haadr8faqU9GY/rOPNk3sgrDQoo//fb4hVC1CLQJ13hef4Y53CI
rU7m2Ys6xt0nUW7/vGT1M0NPAgMBAAGjQjBAMA4GA1UdDwEB/wQEAwIBBjAPBgNV
HRMBAf8EBTADAQH/MB0GA1UdDgQWBBR5tFnme7bl5AFzgAiIyBpY9umbbjANBgkq
hkiG9w0BAQsFAAOCAgEAVR9YqbyyqFDQDLHYGmkgJykIrGF1XIpu+ILlaS/V9lZL
ubhzEFnTIZd+50xx+7LSYK05qAvqFyFWhfFQDlnrzuBZ6brJFe+GnY+EgPbk6ZGQ
3BebYhtF8GaV0nxvwuo77x/Py9auJ/GpsMiu/X1+mvoiBOv/2X/qkSsisRcOj/KK
NFtY2PwByVS5uCbMiogziUwthDyC3+6WVwW6LLv3xLfHTjuCvjHIInNzktHCgKQ5
ORAzI4JMPJ+GslWYHb4phowim57iaztXOoJwTdwJx4nLCgdNbOhdjsnvzqvHu7Ur
TkXWStAmzOVyyghqpZXjFaH3pO3JLF+l+/+sKAIuvtd7u+Nxe5AW0wdeRlN8NwdC
jNPElpzVmbUq4JUagEiuTDkHzsxHpFKVK7q4+63SM1N95R1NbdWhscdCb+ZAJzVc
oyi3B43njTOQ5yOf+1CceWxG1bQVs5ZufpsMljq4Ui0/1lvh+wjChP4kqKOJ2qxq
4RgqsahDYVvTH9w7jXbyLeiNdd8XM2w9U/t7y0Ff/9yi0GE44Za4rF2LN9d11TPA
mRGunUHBcnWEvgJBQl9nJEiU0Zsnvgc/ubhPgXRR4Xq37Z0j4r7g1SgEEzwxA57d
emyPxgcYxn/eR44/KJ4EBs+lVDR3veyJm+kXQ99b21/+jh5Xos1AnX5iItreGCc=
-----END CERTIFICATE-----
)EOF";

// ============ TÍNH AQI THEO QCVN ============
int calculateAQI(float pm25) {
    // Breakpoints theo QCVN 05:2023/BTNMT
    struct { float cLo, cHi; int iLo, iHi; } bp[] = {
        {0, 25, 0, 50},
        {25, 50, 50, 100},
        {50, 80, 100, 150},
        {80, 150, 150, 200},
        {150, 250, 200, 300},
        {250, 500, 300, 500}
    };
    
    for (int i = 0; i < 6; i++) {
        if (pm25 >= bp[i].cLo && pm25 <= bp[i].cHi) {
            return (int)(((bp[i].iHi - bp[i].iLo) / (bp[i].cHi - bp[i].cLo)) * (pm25 - bp[i].cLo) + bp[i].iLo);
        }
    }
    return pm25 > 500 ? 500 : 0;
}

// ============ ĐỌC PMS7003 ============
PMSData readPMS7003() {
    PMSData data = {0, 0, 0, false};
    uint8_t buffer[32];
    int index = 0;
    
    // Xóa buffer cũ
    while (pmsSerial.available()) {
        pmsSerial.read();
    }
    
    // Đợi dữ liệu mới
    unsigned long startTime = millis();
    while (millis() - startTime < 2000) {
        if (pmsSerial.available()) {
            uint8_t c = pmsSerial.read();
            
            // Tìm header 0x42 0x4D
            if (index == 0 && c == 0x42) {
                buffer[index++] = c;
            } else if (index == 1 && c == 0x4D) {
                buffer[index++] = c;
            } else if (index >= 2 && index < 32) {
                buffer[index++] = c;
                if (index == 32) break;
            } else {
                index = 0;
            }
        }
    }
    
    // Kiểm tra đủ dữ liệu
    if (index == 32) {
        // Tính checksum
        uint16_t checksum = 0;
        for (int i = 0; i < 30; i++) {
            checksum += buffer[i];
        }
        uint16_t receivedChecksum = (buffer[30] << 8) | buffer[31];
        
        if (checksum == receivedChecksum) {
            // Lấy giá trị PM (atmospheric environment)
            data.pm1_0 = (buffer[10] << 8) | buffer[11];
            data.pm2_5 = (buffer[12] << 8) | buffer[13];
            data.pm10 = (buffer[14] << 8) | buffer[15];
            data.valid = true;
        }
    }
    
    return data;
}

// ============ KẾT NỐI WIFI ============
void connectWiFi() {
    Serial.printf("📶 Connecting to WiFi: %s", WIFI_SSID);
    WiFi.mode(WIFI_STA);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
    
    int timeout = 30;
    while (WiFi.status() != WL_CONNECTED && timeout > 0) {
        delay(500);
        Serial.print(".");
        timeout--;
    }
    
    if (WiFi.status() == WL_CONNECTED) {
        Serial.println("\n✓ WiFi connected!");
        Serial.printf("  IP: %s\n", WiFi.localIP().toString().c_str());
    } else {
        Serial.println("\n✗ WiFi connection failed!");
    }
}

// ============ KẾT NỐI MQTT ============
void connectMQTT() {
    Serial.print("🔌 Connecting to HiveMQ Cloud...");
    
    String clientId = "esp32-" + String(NODE_ID) + "-" + String(random(0xffff), HEX);
    
    int attempts = 0;
    while (!mqtt.connected() && attempts < 5) {
        if (mqtt.connect(clientId.c_str(), MQTT_USER, MQTT_PASSWORD)) {
            Serial.println("\n✓ MQTT connected!");
            return;
        }
        Serial.print(".");
        attempts++;
        delay(2000);
    }
    
    Serial.printf("\n✗ MQTT failed, rc=%d\n", mqtt.state());
}

// ============ GỬI DỮ LIỆU ============
void sendSensorData() {
    // Đọc cảm biến PMS7003
    PMSData pms = readPMS7003();
    
    // Log
    Serial.println("╔══════════════════════════════════════╗");
    Serial.println("║     📊 SENSOR READINGS               ║");
    Serial.println("╠══════════════════════════════════════╣");
    
    if (pms.valid) {
        int aqi = calculateAQI(pms.pm2_5);
        
        Serial.printf("║ 🌫️  PM1.0:  %3d μg/m³                ║\n", pms.pm1_0);
        Serial.printf("║ 🌫️  PM2.5:  %3d μg/m³  (QCVN: ≤50)   ║\n", pms.pm2_5);
        Serial.printf("║ 🌫️  PM10:   %3d μg/m³  (QCVN: ≤100)  ║\n", pms.pm10);
        Serial.printf("║ 📊 AQI:    %3d                       ║\n", aqi);
        Serial.println("╚══════════════════════════════════════╝");
        
        // Tạo JSON
        StaticJsonDocument<256> doc;
        doc["node_id"] = NODE_ID;
        doc["pm1_0"] = pms.pm1_0;
        doc["pm2_5"] = pms.pm2_5;
        doc["pm10"] = pms.pm10;
        doc["aqi"] = aqi;
        doc["timestamp"] = millis();
        
        char payload[256];
        serializeJson(doc, payload);
        
        // Gửi MQTT
        if (mqtt.connected()) {
            if (mqtt.publish(MQTT_TOPIC, payload)) {
                Serial.printf("✓ Published to %s\n\n", MQTT_TOPIC);
            } else {
                Serial.println("✗ Publish failed!\n");
            }
        } else {
            Serial.println("✗ MQTT not connected!\n");
        }
    } else {
        Serial.println("║ ⚠️  PMS7003: No data!                ║");
        Serial.println("╚══════════════════════════════════════╝\n");
    }
}

// ============ SETUP ============
void setup() {
    Serial.begin(115200);
    delay(1000);
    
    Serial.println("\n╔══════════════════════════════════════╗");
    Serial.println("║   🌬️ ESP32 AIR QUALITY MONITOR      ║");
    Serial.println("║   PMS7003 - PM Only                 ║");
    Serial.println("║   QCVN 05:2023/BTNMT                ║");
    Serial.println("╚══════════════════════════════════════╝");
    Serial.printf("Node ID: %s\n\n", NODE_ID);
    
    // Khởi tạo PMS7003
    pmsSerial.begin(9600, SERIAL_8N1, PMS_RX, PMS_TX);
    Serial.println("✓ PMS7003 initialized (GPIO16/17)");
    
    // Kết nối WiFi
    connectWiFi();
    
    // Cấu hình MQTT với SSL
    wifiClient.setCACert(root_ca);
    mqtt.setServer(MQTT_HOST, MQTT_PORT);
    mqtt.setBufferSize(512);
    
    Serial.println("\n✓ Setup complete!");
    Serial.println("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n");
}

// ============ LOOP ============
void loop() {
    // Kiểm tra kết nối WiFi
    if (WiFi.status() != WL_CONNECTED) {
        connectWiFi();
    }
    
    // Kiểm tra kết nối MQTT
    if (!mqtt.connected()) {
        connectMQTT();
    }
    mqtt.loop();
    
    // Gửi dữ liệu định kỳ
    if (millis() - lastSendTime >= SEND_INTERVAL) {
        sendSensorData();
        lastSendTime = millis();
    }
}
