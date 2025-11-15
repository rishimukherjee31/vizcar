# 🖥️ VizCar Path Planning GUI
A real-time path-planning interface for controlling an ESP32-CAM robot using:

- Raspberry Pi video streaming  
- MQTT messaging  
- Click-to-navigate control  
- Linear, Catmull–Rom, Cubic, and Bézier paths  
- Heading-aware trajectory output  

This GUI displays the live camera feed from a Raspberry Pi and allows you to click points on the video to generate navigation paths for your robot. Paths are transmitted as a list of `(x, y)` points with heading values.

---

## 📦 Dependencies

The GUI requires the following Python packages on **your PC**:

| Package             | Purpose                                 |
|--------------------|-----------------------------------------|
| `numpy`            | Path math, splines                      |
| `opencv-python`    | Video streaming, drawing                |
| `pillow`           | Conversion of OpenCV → Tkinter images   |
| `paho-mqtt`        | Publishing paths using MQTT             |
| `tkinter`          | GUI framework (built-in on most OSes)   |

Install them:

```bash
pip install numpy opencv-python pillow paho-mqtt
```

---

## 📡 Requirements on the Raspberry Pi

Raspberry Pi must be running:

1. **Video streaming server** - The Pi should stream from:
```
http://<PI-IP>:5000/video_feed
```

2. **MQTT broker (Mosquitto)**:
```bash
sudo apt install mosquitto mosquitto-clients
sudo systemctl enable mosquitto
sudo systemctl start mosquitto
```

**If using Tailscale:**
Use the Pi's Tailscale IP instead, e.g.:
```
http://100.101.214.30:5000/video_feed
```

## 🤖 Requirements on the ESP32 Robot

The robot must subscribe to the topic:
```
robot/path
```

and be able to interpret messages shaped like:
```json
{
  "method": "catmull",
  "path": [
    {"point": [305.0, 88.0], "heading": 0.23},
    {"point": [340.0, 100.0], "heading": 0.20},
    {"point": [380.0, 140.0], "heading": null}
  ]
}
```

The final point has `"heading": null` because the robot does not need a heading after arriving at the last point.

## 🌐 Communication Architecture
```
PC (GUI) → MQTT → Raspberry Pi (Broker) → ESP32 robot
```

The GUI only publishes MQTT messages. The robot must implement the path-following logic.

## How to Run the GUI

1. **Move into client folder**
```bash
cd vizcar/client
```

2. **Run the GUI**
```bash
python3 path_gui.py
```

The GUI window will open.

## Using the GUI

### 1. Enter Video URL

Use the Pi's HTTP video stream:
```
http://<PI-IP>:5000/video_feed
```

Press Enter to refresh the video stream.

### 2. Set MQTT Broker Address

Usually the Pi's IP:
```
100.101.214.30
```

### 3. Choose Path Method

| Method | Behavior |
|--------|----------|
| Linear | Straight lines between points |
| Catmull | Smooth spline passing through all points |
| Cubic | Hermite-based smooth spline |
| Bezier | Chained cubic Bézier curves |

### 4. Choose `#pts/seg`

Defines path smoothness:

| Value | Looks like |
|-------|------------|
| 5–20 | coarse |
| 50–150 | smooth |
| 150–500 | ultra smooth |

### 5. Click to Add Waypoints

**Interactions:**
* Left-click: add waypoint
* Right-click: undo last point
* Undo Button: remove last point
* Clear Button: remove all points

**GUI shows:**
* Red dots = your clicked points
* Yellow curve = computed path
* Arrow = heading for last segment

### 6. Publish the Path

Click **Publish** to send:
```json
{
  "method": "linear",
  "path": [
    {"point": [x1, y1], "heading": h1},
    {"point": [x2, y2], "heading": h2},
    ...
  ]
}
```

Robot receives via MQTT on:
```
robot/path
```

## 🔧 Features

* Live video feed
* Click-to-add waypoints
* Undo + Clear buttons
* Four path generation algorithms
* One-direction arrow preview
* Heading computation
* MQTT publishing
* Tailscale-compatible

## Troubleshooting

### ❌ GUI shows: "Could not open video stream"

* Wrong URL
* Pi video server not running
* IP changed
* Windows firewall blocking
* OpenCV missing FFMPEG backend

### ❌ MQTT "connection refused"

* Mosquitto not running
* Wrong broker IP
* Firewall blocking port 1883
* Using WiFi instead of Tailscale

## License

MIT License.
