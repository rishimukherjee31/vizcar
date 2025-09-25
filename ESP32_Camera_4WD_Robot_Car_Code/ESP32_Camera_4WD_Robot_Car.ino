// ESP32_Camera_4WD_Robot_Car.ino
// Main sketch file

#include "esp_camera.h"
#include <WiFi.h>

// =======================
// WiFi Credentials - UPDATE THESE!
// =======================
const char* ssid = "SSID";
const char* password = "PASSWORD";

// =======================
// Camera Model
// =======================
#define CAMERA_MODEL_AI_THINKER

#ifdef CAMERA_MODEL_AI_THINKER
#define PWDN_GPIO_NUM     32
#define RESET_GPIO_NUM    -1
#define XCLK_GPIO_NUM      0
#define SIOD_GPIO_NUM     26
#define SIOC_GPIO_NUM     27
#define Y9_GPIO_NUM       35
#define Y8_GPIO_NUM       34
#define Y7_GPIO_NUM       39
#define Y6_GPIO_NUM       36
#define Y5_GPIO_NUM       21
#define Y4_GPIO_NUM       19
#define Y3_GPIO_NUM       18
#define Y2_GPIO_NUM        5
#define VSYNC_GPIO_NUM    25
#define HREF_GPIO_NUM     23
#define PCLK_GPIO_NUM     22
#endif

// =======================
// Global Variables
// =======================
int gpLed = 4;  // LED Flash pin
String WiFiAddr = "";

// =======================
// External Function Declarations
// =======================
extern void startCameraServer();
extern void robot_setup();
extern void robot_stop();

// =======================
// Setup Function
// =======================
void setup() {
    Serial.begin(115200);
    Serial.setDebugOutput(true);
    Serial.println("\n\nESP32-CAM Robot Starting...");

    // Initialize LED
    pinMode(gpLed, OUTPUT);
    digitalWrite(gpLed, LOW);

    // Initialize motors
    robot_setup();

    // Camera configuration
    camera_config_t config;
    config.ledc_channel = LEDC_CHANNEL_0;
    config.ledc_timer = LEDC_TIMER_0;
    config.pin_d0 = Y2_GPIO_NUM;
    config.pin_d1 = Y3_GPIO_NUM;
    config.pin_d2 = Y4_GPIO_NUM;
    config.pin_d3 = Y5_GPIO_NUM;
    config.pin_d4 = Y6_GPIO_NUM;
    config.pin_d5 = Y7_GPIO_NUM;
    config.pin_d6 = Y8_GPIO_NUM;
    config.pin_d7 = Y9_GPIO_NUM;
    config.pin_xclk = XCLK_GPIO_NUM;
    config.pin_pclk = PCLK_GPIO_NUM;
    config.pin_vsync = VSYNC_GPIO_NUM;
    config.pin_href = HREF_GPIO_NUM;
    config.pin_sscb_sda = SIOD_GPIO_NUM;
    config.pin_sscb_scl = SIOC_GPIO_NUM;
    config.pin_pwdn = PWDN_GPIO_NUM;
    config.pin_reset = RESET_GPIO_NUM;
    config.xclk_freq_hz = 20000000;
    config.pixel_format = PIXFORMAT_JPEG;

    // Frame buffer configuration
    if(psramFound()) {
        config.frame_size = FRAMESIZE_VGA;
        config.jpeg_quality = 10;
        config.fb_count = 2;
    } else {
        config.frame_size = FRAMESIZE_CIF;
        config.jpeg_quality = 12;
        config.fb_count = 1;
    }

    // Initialize camera
    esp_err_t err = esp_camera_init(&config);
    if (err != ESP_OK) {
        Serial.printf("Camera init failed with error 0x%x\n", err);
        return;
    }

    // Drop down frame size for higher initial frame rate
    sensor_t * s = esp_camera_sensor_get();
    s->set_framesize(s, FRAMESIZE_CIF);

    // Connect to WiFi
    WiFi.begin(ssid, password);
    Serial.println("Connecting to WiFi...");
    
    while (WiFi.status() != WL_CONNECTED) {
        delay(500);
        Serial.print(".");
    }
    
    Serial.println("\n====================================");
    Serial.println("WiFi Connected!");
    Serial.print("Camera Ready! Use 'http://");
    Serial.print(WiFi.localIP());
    WiFiAddr = WiFi.localIP().toString();
    Serial.println("' to connect");
    Serial.print("Stream URL: http://");
    Serial.print(WiFiAddr);
    Serial.println(":81/stream");
    Serial.println("====================================\n");

    // Start camera server
    startCameraServer();
    
    // Initialize pin 33 (might be motor enable)
    pinMode(33, OUTPUT);
    digitalWrite(33, LOW);
}

// =======================
// Loop Function
// =======================
void loop() {
    delay(10000);
}