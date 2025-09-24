# Raspberry Pi Video Server
Flask-based video streaming server optimized for Logitech C920 cameras on Raspberry Pi.

## Overview
This server captures video from a USB camera and streams it via HTTP endpoints. It's specifically optimized for the Logitech C920 HD Pro Webcam but supports other V4L2-compatible cameras.

## Features
- Real-time MJPEG video streaming
- RESTful API for camera control
- Threaded video capture for smooth performance
- Automatic camera detection and configuration
- Optimized for Logitech C920 settings
- Tailscale-ready networking

## Hardware Requirements
- Raspberry Pi 4 (2GB+ recommended)
- Logitech C920 HD Pro Webcam or compatible USB camera
- MicroSD card (16GB+ Class 10)
- Stable power supply (3A recommended)

## Installation
Install system dependencies:
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install python3-pip python3-opencv v4l-utils fswebcam -y
```

Install Python packages:
```bash
pip3 install flask opencv-python requests numpy
```

Set up camera permissions:
```bash
sudo usermod -a -G video $USER
sudo reboot  # Required for group changes to take effect
```

Create udev rules for persistent camera permissions:
```bash
sudo nano /etc/udev/rules.d/99-camera-permissions.rules
```
Add:
```
KERNEL=="video[0-9]*", GROUP="video", MODE="0664"
SUBSYSTEM=="video4linux", GROUP="video", MODE="0664"
```

Reload udev rules:
```bash
sudo udevadm control --reload-rules
sudo udevadm trigger
```

## Configuration
The server automatically detects and configures the camera with optimal settings:
- **Resolution**: 1280x720 (configurable)
- **Frame Rate**: 30 FPS
- **Codec**: MJPEG (native C920 format)
- **Buffer Size**: 1 frame (minimal latency)

### Camera Detection
```bash
# List available cameras
v4l2-ctl --list-devices

# Check camera capabilities
v4l2-ctl --device=/dev/video0 --list-formats-ext

# Test camera capture
fswebcam -d /dev/video0 --no-banner test.jpg
```

## Usage
Start the server:
```bash
python3 video_server.py
```

Expected output:
```
INFO:__main__:Found accessible camera devices: ['/dev/video0', '/dev/video1']
INFO:__main__:✅ C920 camera initialized successfully at index 0
INFO:__main__:📐 Frame size: 1280x720
INFO:__main__:🎥 FPS: 30.0
INFO:__main__:📹 Codec: MJPG
 * Running on all addresses (0.0.0.0)
 * Running on http://127.0.0.1:5000
```

## API Reference
### GET /
Returns server information and available endpoints.

**Response:**
```json
{
  "status": "running",
  "endpoints": {
    "video_stream": "/video_feed",
    "status": "/status",
    "frame": "/frame"
  }
}
```

### GET /status
Returns camera status and configuration.

**Response:**
```json
{
  "camera_active": true,
  "camera_index": 0,
  "fps": 30
}
```

### GET /video_feed
Returns live MJPEG video stream.

**Content-Type:** `multipart/x-mixed-replace; boundary=frame`

**Usage:**
- Direct browser access: `http://PI_IP:5000/video_feed`
- HTML5 video: `<img src="http://PI_IP:5000/video_feed">`
- OpenCV: `cv2.VideoCapture('http://PI_IP:5000/video_feed')`

### GET /frame
Returns a single JPEG frame.

**Content-Type:** `image/jpeg`

**Usage:**
```bash
curl http://PI_IP:5000/frame -o frame.jpg
```

## Auto-Start Configuration
Create a systemd service for automatic startup:

```bash
sudo nano /etc/systemd/system/vizcar-server.service
```

Add:
```ini
[Unit]
Description=VizCar Video Streaming Server
After=network.target
Wants=network.target

[Service]
Type=simple
User=pi
Group=pi
WorkingDirectory=/home/pi/vizcar
ExecStart=/usr/bin/python3 /home/pi/vizcar/video_server.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable vizcar-server.service
sudo systemctl start vizcar-server.service
```

Monitor service:
```bash
sudo systemctl status vizcar-server.service
sudo journalctl -u vizcar-server.service -f
```

## Troubleshooting
### Camera Not Detected
```bash
# Check USB connection
lsusb | grep -i logitech

# Verify video devices
ls -la /dev/video*

# Test direct capture
fswebcam -d /dev/video0 test.jpg
```

### Permission Denied
```bash
# Check user groups
groups $USER

# Should include 'video' group
# If not, run: sudo usermod -a -G video $USER && sudo reboot
```

### Performance Issues
```bash
# Check CPU usage
htop

# Monitor USB bandwidth
sudo dmesg | grep -i usb

# Reduce resolution in video_server.py:
# self.video.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
# self.video.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
```

### Network Connectivity
```bash
# Check if server is running
sudo netstat -tlnp | grep :5000

# Test local access
curl http://localhost:5000/status

# Get Tailscale IP
tailscale ip -4
```

## Advanced Configuration
### Custom Resolution
Modify `video_server.py`:
```python
# Change these values in initialize_camera():
self.video.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)   # Width
self.video.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)  # Height
```

### JPEG Quality
Adjust compression in `generate_mjpeg_stream()`:
```python
ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 60])
```

### Frame Rate Limiting
Modify the sleep time in `generate_mjpeg_stream()`:
```python
time.sleep(1/15)  # 15 FPS instead of 30
```

## Security Considerations
- Server binds to `0.0.0.0:5000` (all interfaces)
- Use Tailscale VPN for secure remote access
- Consider adding authentication for production use
- Monitor system resources to prevent DoS

## Performance Metrics
On Raspberry Pi 4 (4GB):
- **CPU Usage**: ~15-25% single core
- **Memory Usage**: ~100-150MB
- **Network Bandwidth**: ~2-8 Mbps (depending on resolution)
- **Latency**: <100ms over local network
