// app_httpd.cpp
// HTTP server and motor control functions

#include "esp_http_server.h"
#include "esp_timer.h"
#include "esp_camera.h"
#include "img_converters.h"
#include "Arduino.h"

// =======================
// Motor Pin Definitions
// =======================
#define LEFT_M0     13   // Left motor backward
#define LEFT_M1     12   // Left motor forward
#define RIGHT_M0    14   // Right motor backward
#define RIGHT_M1    15   // Right motor forward

// =======================
// Global Variables
// =======================
extern int gpLed;
extern String WiFiAddr;

int speed = 150; // Motor speed (0-255)
httpd_handle_t camera_httpd = NULL;
httpd_handle_t stream_httpd = NULL;

// =======================
// Function Declarations
// =======================
void robot_stop();
void robot_fwd();
void robot_back();
void robot_left();
void robot_right();

// =======================
// Motor Control Functions
// =======================
void robot_setup() {
    Serial.println("Initializing motors...");
    
    // Initialize motor pins as outputs
    pinMode(LEFT_M0, OUTPUT);
    pinMode(LEFT_M1, OUTPUT);
    pinMode(RIGHT_M0, OUTPUT);
    pinMode(RIGHT_M1, OUTPUT);
    
    // Attach PWM to motor pins
    ledcAttach(LEFT_M0, 2000, 8);   // 2000 Hz, 8-bit resolution
    ledcAttach(LEFT_M1, 2000, 8);   
    ledcAttach(RIGHT_M0, 2000, 8);  
    ledcAttach(RIGHT_M1, 2000, 8);  
    
    robot_stop();
    Serial.println("Motors initialized");
}

void robot_stop() {
    ledcWrite(LEFT_M0, 0);
    ledcWrite(LEFT_M1, 0);
    ledcWrite(RIGHT_M0, 0);
    ledcWrite(RIGHT_M1, 0);
    Serial.println("Motors: STOP");
}

void robot_left() {
    ledcWrite(LEFT_M0, 0);
    ledcWrite(LEFT_M1, speed);
    ledcWrite(RIGHT_M0, 0);
    ledcWrite(RIGHT_M1, speed);
    Serial.println("Motors: FORWARD");
}

void robot_right() {
    ledcWrite(LEFT_M0, speed);
    ledcWrite(LEFT_M1, 0);
    ledcWrite(RIGHT_M0, speed);
    ledcWrite(RIGHT_M1, 0);
    Serial.println("Motors: BACKWARD");
}

void robot_fwd() {
    ledcWrite(LEFT_M0, speed);
    ledcWrite(LEFT_M1, 0);
    ledcWrite(RIGHT_M0, 0);
    ledcWrite(RIGHT_M1, speed);
    Serial.println("Motors: LEFT");
}

void robot_back() {
    ledcWrite(LEFT_M0, 0);
    ledcWrite(LEFT_M1, speed);
    ledcWrite(RIGHT_M0, speed);
    ledcWrite(RIGHT_M1, 0);
    Serial.println("Motors: RIGHT");
}

// =======================
// Streaming Definitions
// =======================
#define PART_BOUNDARY "123456789000000000000987654321"
static const char* _STREAM_CONTENT_TYPE = "multipart/x-mixed-replace;boundary=" PART_BOUNDARY;
static const char* _STREAM_BOUNDARY = "\r\n--" PART_BOUNDARY "\r\n";
static const char* _STREAM_PART = "Content-Type: image/jpeg\r\nContent-Length: %u\r\n\r\n";

// =======================
// HTTP Handlers
// =======================
static esp_err_t index_handler(httpd_req_t *req) {
    httpd_resp_set_type(req, "text/html");
    String page = "";
    page += "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=0\">\n";
    page += "<style>body{font-family:Arial;text-align:center;background:#f0f0f0;}";
    page += "button{width:90px;height:80px;font-size:16px;font-weight:bold;margin:5px;border-radius:10px;}</style>";
    page += "<h2>ESP32 Robot Control</h2>";
    page += "<p><img src='http://" + WiFiAddr + ":81/stream' style='width:300px;'></p>";
    page += "<script>function send(x){fetch('/'+x);}</script>";
    page += "<p><button style='background:green' onmousedown=\"send('go')\" onmouseup=\"send('stop')\" ontouchstart=\"send('go')\" ontouchend=\"send('stop')\">Forward</button></p>";
    page += "<p>";
    page += "<button style='background:green' onmousedown=\"send('left')\" onmouseup=\"send('stop')\" ontouchstart=\"send('left')\" ontouchend=\"send('stop')\">Left</button>";
    page += "<button style='background:red' onclick=\"send('stop')\">STOP</button>";
    page += "<button style='background:green' onmousedown=\"send('right')\" onmouseup=\"send('stop')\" ontouchstart=\"send('right')\" ontouchend=\"send('stop')\">Right</button>";
    page += "</p>";
    page += "<p><button style='background:green' onmousedown=\"send('back')\" onmouseup=\"send('stop')\" ontouchstart=\"send('back')\" ontouchend=\"send('stop')\">Back</button></p>";
    page += "<p><button style='background:yellow;width:140px;height:40px' onclick=\"send('ledon')\">Light ON</button>";
    page += "<button style='background:yellow;width:140px;height:40px' onclick=\"send('ledoff')\">Light OFF</button></p>";
    
    return httpd_resp_send(req, page.c_str(), page.length());
}

static esp_err_t stream_handler(httpd_req_t *req) {
    camera_fb_t * fb = NULL;
    esp_err_t res = ESP_OK;
    size_t _jpg_buf_len = 0;
    uint8_t * _jpg_buf = NULL;
    char * part_buf[64];

    res = httpd_resp_set_type(req, _STREAM_CONTENT_TYPE);
    if(res != ESP_OK) return res;

    while(true) {
        fb = esp_camera_fb_get();
        if (!fb) {
            Serial.println("Camera capture failed");
            res = ESP_FAIL;
        } else {
            if(fb->format != PIXFORMAT_JPEG) {
                bool jpeg_converted = frame2jpg(fb, 80, &_jpg_buf, &_jpg_buf_len);
                esp_camera_fb_return(fb);
                fb = NULL;
                if(!jpeg_converted) {
                    Serial.println("JPEG compression failed");
                    res = ESP_FAIL;
                }
            } else {
                _jpg_buf_len = fb->len;
                _jpg_buf = fb->buf;
            }
        }
        
        if(res == ESP_OK) {
            size_t hlen = snprintf((char *)part_buf, 64, _STREAM_PART, _jpg_buf_len);
            res = httpd_resp_send_chunk(req, (const char *)part_buf, hlen);
        }
        if(res == ESP_OK) {
            res = httpd_resp_send_chunk(req, (const char *)_jpg_buf, _jpg_buf_len);
        }
        if(res == ESP_OK) {
            res = httpd_resp_send_chunk(req, _STREAM_BOUNDARY, strlen(_STREAM_BOUNDARY));
        }
        
        if(fb) {
            esp_camera_fb_return(fb);
            fb = NULL;
            _jpg_buf = NULL;
        } else if(_jpg_buf) {
            free(_jpg_buf);
            _jpg_buf = NULL;
        }
        if(res != ESP_OK) break;
    }
    return res;
}

static esp_err_t capture_handler(httpd_req_t *req) {
    camera_fb_t * fb = NULL;
    esp_err_t res = ESP_OK;

    fb = esp_camera_fb_get();
    if (!fb) {
        Serial.println("Camera capture failed");
        httpd_resp_send_500(req);
        return ESP_FAIL;
    }

    httpd_resp_set_type(req, "image/jpeg");
    httpd_resp_set_hdr(req, "Content-Disposition", "inline; filename=capture.jpg");

    size_t fb_len = 0;
    if(fb->format == PIXFORMAT_JPEG) {
        fb_len = fb->len;
        res = httpd_resp_send(req, (const char *)fb->buf, fb->len);
    } else {
        size_t _jpg_buf_len = 0;
        uint8_t * _jpg_buf = NULL;
        bool jpeg_converted = frame2jpg(fb, 80, &_jpg_buf, &_jpg_buf_len);
        if(jpeg_converted) {
            res = httpd_resp_send(req, (const char *)_jpg_buf, _jpg_buf_len);
            free(_jpg_buf);
        } else {
            res = ESP_FAIL;
        }
    }
    esp_camera_fb_return(fb);
    return res;
}

static esp_err_t go_handler(httpd_req_t *req) {
    robot_fwd();
    httpd_resp_set_type(req, "text/html");
    return httpd_resp_send(req, "OK", 2);
}

static esp_err_t back_handler(httpd_req_t *req) {
    robot_back();
    httpd_resp_set_type(req, "text/html");
    return httpd_resp_send(req, "OK", 2);
}

static esp_err_t left_handler(httpd_req_t *req) {
    robot_left();
    httpd_resp_set_type(req, "text/html");
    return httpd_resp_send(req, "OK", 2);
}

static esp_err_t right_handler(httpd_req_t *req) {
    robot_right();
    httpd_resp_set_type(req, "text/html");
    return httpd_resp_send(req, "OK", 2);
}

static esp_err_t stop_handler(httpd_req_t *req) {
    robot_stop();
    httpd_resp_set_type(req, "text/html");
    return httpd_resp_send(req, "OK", 2);
}

static esp_err_t ledon_handler(httpd_req_t *req) {
    digitalWrite(gpLed, HIGH);
    Serial.println("LED ON");
    httpd_resp_set_type(req, "text/html");
    return httpd_resp_send(req, "OK", 2);
}

static esp_err_t ledoff_handler(httpd_req_t *req) {
    digitalWrite(gpLed, LOW);
    Serial.println("LED OFF");
    httpd_resp_set_type(req, "text/html");
    return httpd_resp_send(req, "OK", 2);
}

// =======================
// Server Initialization
// =======================
void startCameraServer() {
    httpd_config_t config = HTTPD_DEFAULT_CONFIG();
    config.server_port = 80;

    httpd_uri_t index_uri = {
        .uri = "/",
        .method = HTTP_GET,
        .handler = index_handler,
        .user_ctx = NULL
    };
    
    httpd_uri_t go_uri = {
        .uri = "/go",
        .method = HTTP_GET,
        .handler = go_handler,
        .user_ctx = NULL
    };
    
    httpd_uri_t back_uri = {
        .uri = "/back",
        .method = HTTP_GET,
        .handler = back_handler,
        .user_ctx = NULL
    };
    
    httpd_uri_t stop_uri = {
        .uri = "/stop",
        .method = HTTP_GET,
        .handler = stop_handler,
        .user_ctx = NULL
    };
    
    httpd_uri_t left_uri = {
        .uri = "/left",
        .method = HTTP_GET,
        .handler = left_handler,
        .user_ctx = NULL
    };
    
    httpd_uri_t right_uri = {
        .uri = "/right",
        .method = HTTP_GET,
        .handler = right_handler,
        .user_ctx = NULL
    };
    
    httpd_uri_t ledon_uri = {
        .uri = "/ledon",
        .method = HTTP_GET,
        .handler = ledon_handler,
        .user_ctx = NULL
    };
    
    httpd_uri_t ledoff_uri = {
        .uri = "/ledoff",
        .method = HTTP_GET,
        .handler = ledoff_handler,
        .user_ctx = NULL
    };
    
    httpd_uri_t capture_uri = {
        .uri = "/capture",
        .method = HTTP_GET,
        .handler = capture_handler,
        .user_ctx = NULL
    };
    
    httpd_uri_t stream_uri = {
        .uri = "/stream",
        .method = HTTP_GET,
        .handler = stream_handler,
        .user_ctx = NULL
    };

    Serial.printf("Starting web server on port: '%d'\n", config.server_port);
    if (httpd_start(&camera_httpd, &config) == ESP_OK) {
        httpd_register_uri_handler(camera_httpd, &index_uri);
        httpd_register_uri_handler(camera_httpd, &go_uri);
        httpd_register_uri_handler(camera_httpd, &back_uri);
        httpd_register_uri_handler(camera_httpd, &stop_uri);
        httpd_register_uri_handler(camera_httpd, &left_uri);
        httpd_register_uri_handler(camera_httpd, &right_uri);
        httpd_register_uri_handler(camera_httpd, &ledon_uri);
        httpd_register_uri_handler(camera_httpd, &ledoff_uri);
        httpd_register_uri_handler(camera_httpd, &capture_uri);
    }

    config.server_port = 81;
    config.ctrl_port += 1;
    Serial.printf("Starting stream server on port: '%d'\n", config.server_port);
    if (httpd_start(&stream_httpd, &config) == ESP_OK) {
        httpd_register_uri_handler(stream_httpd, &stream_uri);
    }
}