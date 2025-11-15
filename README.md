[vizcar](./README.md) | [Client](./client/MacOS_README.md) | [Server](./server/RPI_README.md) | [Path GUI](./client/PathGUI_README.md)


# vizcar
[./video/baseline.mp4](https://github.com/user-attachments/assets/a0b385c3-4cb0-4201-a864-ad12884572af)

<p align="center"><em>Baseline method of using human input for motor commands.</em></p>




## Overview
The vizcar system consists of three main components:
- **Raspberry Pi Video Server**: Captures and streams video from a Logitech camera
- **macOS Video Client**: Displays the live video feed for monitoring and control
- **Robot Control System**: Processes visual data for autonomous navigation (coming soon)

## System Requirements
- Raspberry Pi 5 (required) with Ubuntu latest LTS
- Logitech C920 HD Pro Webcam or compatible USB camera
- macOS device for client-side applications (M1/Intel Mac)
- Tailscale VPN for secure device communication

## Installation
First, install the Python dependencies for the web server on the Raspberry Pi (We did this over SSH from a Mac):

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install python3-pip python3-opencv v4l-utils -y
pip3 install flask opencv-python requests numpy
sudo raspi-config  # Enable camera in Interface Options if using Pi camera
```

Add your user to the video group for camera access:
```bash
sudo usermod -a -G video $USER
sudo reboot  # Required for group changes
```

Install dependencies on macOS:
```bash
# Install Homebrew if not already installed
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Install OpenCV and Python packages
brew install python opencv
pip3 install opencv-python requests numpy
```

## Quick Start
1. **Set up Tailscale** on both devices for secure networking
2. **Connect the Logitech camera** to your Raspberry Pi
3. **Run the video server** on the Pi:
   ```bash
   python3 video_server.py
   ```
4. **Get your Pi's Tailscale IP**:
   ```bash
   tailscale ip -4
   ```
5. **Run the video client** on your Mac:
   ```bash
   python3 video_client.py [PI_TAILSCALE_IP]
   ```

## API Endpoints
The video server exposes the following REST API endpoints:
- `GET /` - Server status and endpoint information
- `GET /status` - Camera status and configuration
- `GET /video_feed` - Live MJPEG video stream
- `GET /frame` - Single JPEG frame capture

## Architecture
```
┌─────────────────┐    Tailscale VPN    ┌─────────────────┐
│   Raspberry Pi  │◄─────────────────-─►│   macOS Client  │
│                 │     HTTP/MJPEG      │                 │
│ ┌─────────────┐ │                     │ ┌─────────────┐ │
│ │   Camera    │ │                     │ │OpenCV Viewer│ │
│ │  (C920)     │ │                     │ │             │ │
│ └─────────────┘ │                     │ └─────────────┘ │
│ ┌─────────────┐ │                     │                 │
│ │Flask Server │ │                     │                 │
│ │   :5000     │ │                     │                 │
│ └─────────────┘ │                     │                 │
└─────────────────┘                     └─────────────────┘
```

## Troubleshooting
### Camera Issues
```bash
# Check camera detection
lsusb | grep -i camera
v4l2-ctl --list-devices

# Test camera capture
fswebcam -d /dev/video0 test.jpg

# Check permissions
ls -la /dev/video*
groups $USER
```

### Network Issues
```bash
# Verify Tailscale status
tailscale status

# Test connectivity
ping [PI_TAILSCALE_IP]

# Check if server is running
curl http://[PI_TAILSCALE_IP]:5000/status
```

### Performance Optimization
- Adjust video resolution in `video_server.py`
- Modify JPEG quality settings for bandwidth optimization
- Use wired Ethernet connection for better stability

## Development
This project uses a modular architecture allowing for easy extension:
- **Video Server**: Flask-based HTTP API with threading for concurrent access
- **Video Client**: OpenCV-based display with real-time streaming
- **Camera Interface**: Abstracted camera handling supporting multiple devices

## Contributing
1. Fork the repository
2. Create a feature branch
3. Test on both Raspberry Pi and macOS
4. Submit a pull request with detailed description

## License
MIT License - see LICENSE file for details


