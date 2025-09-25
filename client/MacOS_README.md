# macOS Video Client
OpenCV-based video streaming client for displaying live camera feeds from Raspberry Pi servers.

## Overview
This client application connects to the Raspberry Pi video server over Tailscale VPN and displays the live camera feed in a native window. It includes features for monitoring connection status, saving screenshots, and handling network interruptions gracefully.

## Features
- Real-time video display with OpenCV
- Automatic connection testing and recovery
- Screenshot capture functionality
- Connection status monitoring
- Smooth frame buffering to prevent lag
- Keyboard shortcuts for control
- Network interruption handling

## System Requirements
- macOS 10.14+ (Mojave or later)
- Python 3.8+ with pip
- Stable network connection
- Tailscale VPN (required)

## Installation
Install Homebrew (if not already installed):
```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

Install system dependencies:
```bash
brew install python opencv
```

Install Python packages:
```bash
pip3 install opencv-python requests numpy
```

Verify installation:
```bash
python3 -c "import cv2; print('OpenCV version:', cv2.__version__)"
```

## Setup
### Tailscale Configuration
Install and configure Tailscale for secure networking:
```bash
# Download from https://tailscale.com/download/mac
# Or install via Homebrew
brew install --cask tailscale
```

Start Tailscale and authenticate:
```bash
sudo tailscale up
```

### Get Raspberry Pi IP
On your Raspberry Pi, run:
```bash
tailscale ip -4
```
Note this IP address for connecting the client.

## Usage
### Basic Usage
Connect to your Raspberry Pi video server:
```bash
python3 video_client.py [PI_TAILSCALE_IP]
```

Example:
```bash
python3 video_client.py 100.64.0.15
```

### Command Line Options
```bash
python3 video_client.py [PI_IP] --port [PORT]
```

**Arguments:**
- `PI_IP`: Tailscale IP address of your Raspberry Pi
- `--port`: Server port (default: 5000)

**Examples:**
```bash
# Connect with custom port
python3 video_client.py 100.64.0.15 --port 8080

# Connect via local network
python3 video_client.py 192.168.1.100
```

### Keyboard Controls
Once the video window is active:
- **Q**: Quit the application
- **S**: Save screenshot to current directory
- **ESC**: Exit full-screen mode
- **Space**: Pause/unpause video stream

### Expected Output
```bash
🔗 Connecting to Pi camera at: http://100.64.0.15:5000
✅ Connected to server: http://100.64.0.15:5000
🎥 Starting video display...
Press 'q' to quit, 's' to save screenshot

Screenshot saved: screenshot_1699123456.jpg
```

## Features
### Connection Testing
The client automatically tests connectivity before streaming:
```python
# Automatic connection verification
response = requests.get(f"{server_url}/status", timeout=5)
```

### Frame Buffering
Smart frame queue management prevents lag:
- Maximum 5 frames in buffer
- Automatic old frame dropping
- Smooth playback even with network jitter

### Screenshot Capture
Press 's' to save the current frame:
- Saved as `screenshot_[timestamp].jpg`
- Full resolution preservation
- Automatic filename generation

### Error Recovery
Handles network interruptions gracefully:
- Automatic reconnection attempts
- Timeout handling for unresponsive servers
- User-friendly error messages

## Configuration
### Video Display Settings
Modify display parameters in `video_client.py`:

```python
# Window size (auto-scales to video)
cv2.namedWindow('Pi Camera Feed', cv2.WINDOW_NORMAL)

# Frame rate limiting
cv2.waitKey(33)  # ~30 FPS display
```

### Connection Timeouts
Adjust network timeouts for your environment:
```python
# Connection test timeout
response = requests.get(url, timeout=10)  # Increase for slow networks

# Frame timeout
frame = self.frame_queue.get(timeout=5)   # Adjust for network latency
```

### Quality Settings
The client automatically handles JPEG decompression from the server's MJPEG stream.

## Troubleshooting
### Connection Issues
```bash
# Test connectivity manually
ping [PI_TAILSCALE_IP]
curl http://[PI_TAILSCALE_IP]:5000/status

# Check Tailscale status
tailscale status
```

### Video Display Problems
```bash
# Check OpenCV installation
python3 -c "import cv2; print('OpenCV OK')"

# Verify camera access permissions on Pi
# (Run on Raspberry Pi)
groups $USER | grep video
```

### Performance Issues
Monitor system resources:
```bash
# Check CPU usage
top -pid `pgrep -f video_client.py`

# Check memory usage
ps aux | grep video_client.py
```

### Network Latency
For high-latency connections:
```python
# Increase timeouts in video_client.py
self.frame_queue.get(timeout=10)  # Increase from 1 to 10 seconds
```

## Advanced Usage
### Custom Server Endpoints
Connect to different server endpoints:
```python
# Modify the server URL in video_client.py
server_url = f"http://{args.server_ip}:{args.port}/custom_endpoint"
```

### Multiple Camera Support
Run multiple client instances:
```bash
# Terminal 1 - Camera 1
python3 video_client.py 100.64.0.15 --port 5000

# Terminal 2 - Camera 2  
python3 video_client.py 100.64.0.16 --port 5000
```

### Recording Video
Extend the client to save video:
```python
# Add to video_client.py
fourcc = cv2.VideoWriter_fourcc(*'MJPG')
out = cv2.VideoWriter('output.avi', fourcc, 20.0, (640, 480))

# In display loop
out.write(frame)
```

## Integration Examples
### Web Browser Access
Test server directly in Safari/Chrome:
```
http://[PI_TAILSCALE_IP]:5000/video_feed
```

### curl Testing
```bash
# Get single frame
curl http://[PI_TAILSCALE_IP]:5000/frame -o frame.jpg

# Check server status
curl http://[PI_TAILSCALE_IP]:5000/status
```

### Python Integration
```python
import cv2
import requests

# Capture single frame
response = requests.get('http://PI_IP:5000/frame')
with open('frame.jpg', 'wb') as f:
    f.write(response.content)

# Stream video
cap = cv2.VideoCapture('http://PI_IP:5000/video_feed')
while True:
    ret, frame = cap.read()
    if ret:
        cv2.imshow('Stream', frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
```

## Performance Optimization
### Network Settings
For better streaming performance:
```bash
# Increase network buffer sizes (if needed)
sudo sysctl -w net.core.rmem_max=134217728
sudo sysctl -w net.core.rmem_default=134217728
```

### Display Settings
```python
# Reduce display size for better performance
frame = cv2.resize(frame, (640, 480))

# Skip frames for lower CPU usage
frame_count += 1
if frame_count % 2 == 0:  # Show every other frame
    cv2.imshow('Pi Camera Feed', frame)
```

## Security Notes
- Uses HTTP (not HTTPS) over Tailscale VPN
- Tailscale provides encryption and authentication
- No credentials stored in client code
- Server access controlled by Tailscale ACLs

## Development
### Testing
```bash
# Test with mock server
python3 -m http.server 5000  # Simple HTTP server for testing

# Unit tests (if implemented)
python3 -m pytest test_video_client.py
```

### Debugging
Enable debug logging:
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Contributing
1. Fork the vizcar repository
2. Create a feature branch for client improvements
3. Test on multiple macOS versions
4. Submit pull request with detailed testing notes
