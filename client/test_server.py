#!/usr/bin/env python3
"""
Mock NN Server for testing the VizCar Path Planning Controller

This simulates the neural network server API that provides:
1. /video_feed - MJPEG video stream
2. /pose - JSON with robot pose (front/back marker positions)
3. /status - Server status

Run this to test the client without the actual hardware.
"""

from flask import Flask, Response, jsonify
import cv2
import numpy as np
import time
import math
import threading

app = Flask(__name__)

# Simulated robot state
class SimulatedRobot:
    def __init__(self):
        self.x = 320  # Center x
        self.y = 240  # Center y
        self.heading = 0  # radians
        self.marker_distance = 40  # pixels between front/back
        self.lock = threading.Lock()
        
    def get_pose(self):
        with self.lock:
            front_x = self.x + self.marker_distance/2 * math.cos(self.heading)
            front_y = self.y + self.marker_distance/2 * math.sin(self.heading)
            back_x = self.x - self.marker_distance/2 * math.cos(self.heading)
            back_y = self.y - self.marker_distance/2 * math.sin(self.heading)
            return {
                'front_x': front_x,
                'front_y': front_y,
                'back_x': back_x,
                'back_y': back_y,
                'timestamp': time.time()
            }
    
    def move_forward(self, distance=5):
        with self.lock:
            self.x += distance * math.cos(self.heading)
            self.y += distance * math.sin(self.heading)
            # Keep in bounds
            self.x = max(50, min(590, self.x))
            self.y = max(50, min(430, self.y))
    
    def rotate(self, angle=0.1):
        with self.lock:
            self.heading += angle

robot = SimulatedRobot()

def generate_frames():
    """Generate simulated video frames with robot visualization"""
    while True:
        # Create frame
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        frame[:] = (50, 50, 50)  # Dark gray background
        
        # Draw grid
        for x in range(0, 640, 50):
            cv2.line(frame, (x, 0), (x, 480), (70, 70, 70), 1)
        for y in range(0, 480, 50):
            cv2.line(frame, (0, y), (640, y), (70, 70, 70), 1)
        
        # Get robot pose
        pose = robot.get_pose()
        fx, fy = int(pose['front_x']), int(pose['front_y'])
        bx, by = int(pose['back_x']), int(pose['back_y'])
        
        # Draw robot
        cv2.line(frame, (bx, by), (fx, fy), (0, 255, 0), 3)
        cv2.circle(frame, (fx, fy), 10, (255, 0, 0), -1)  # Front - blue
        cv2.circle(frame, (bx, by), 10, (0, 0, 255), -1)  # Back - red
        
        # Add label
        cv2.putText(frame, "MOCK SERVER - Simulated Robot", (10, 30),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        cv2.putText(frame, f"Pos: ({robot.x:.0f}, {robot.y:.0f}) Heading: {math.degrees(robot.heading):.1f}°",
                   (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
        
        # Encode as JPEG
        _, buffer = cv2.imencode('.jpg', frame)
        frame_bytes = buffer.tobytes()
        
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
        
        time.sleep(0.033)  # ~30 fps

@app.route('/video_feed')
def video_feed():
    return Response(generate_frames(),
                   mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/detections')
def get_detections():
    """Return current robot pose in the same format as real NN server"""
    pose = robot.get_pose()
    
    return jsonify({
        'timestamp': time.strftime('%Y-%m-%dT%H:%M:%S'),
        'detections': [
            {
                'bbox': {
                    'x1': pose['front_x'] - 30,
                    'y1': pose['front_y'] - 30,
                    'x2': pose['back_x'] + 30,
                    'y2': pose['back_y'] + 30,
                    'confidence': 0.95
                },
                'class': 'Car',
                'class_id': 0,
                'keypoints': [
                    {'name': 'keypoint_0', 'x': pose['front_x'], 'y': pose['front_y'], 'confidence': 0.95},
                    {'name': 'keypoint_1', 'x': pose['back_x'], 'y': pose['back_y'], 'confidence': 0.93}
                ],
                'car_id': 0
            }
        ],
        'num_detections': 1,
        'fps': 30.0,
        'inference_ms': 15.5
    })

# Keep old endpoint for compatibility
@app.route('/pose')
def get_pose():
    """Return current robot pose as JSON (legacy endpoint)"""
    return jsonify(robot.get_pose())

@app.route('/status')
def status():
    return jsonify({
        'status': 'running',
        'type': 'mock_nn_server',
        'timestamp': time.time()
    })

# Simulated robot control endpoints (mimics ESP32)
@app.route('/go')
def go():
    robot.move_forward(8)
    return 'OK'

@app.route('/back')
def back():
    robot.move_forward(-8)
    return 'OK'

@app.route('/left')
def left():
    robot.rotate(-0.15)
    return 'OK'

@app.route('/right')
def right():
    robot.rotate(0.15)
    return 'OK'

@app.route('/stop')
def stop():
    return 'OK'

@app.route('/')
def index():
    return """
    <h1>Mock NN Server</h1>
    <p>This is a simulated NN server for testing the VizCar controller.</p>
    <ul>
        <li><a href="/video_feed">/video_feed</a> - MJPEG video stream</li>
        <li><a href="/detections">/detections</a> - Robot pose detections (JSON)</li>
        <li><a href="/status">/status</a> - Server status</li>
    </ul>
    <h2>Robot Control (for testing)</h2>
    <ul>
        <li><a href="/go">/go</a> - Move forward</li>
        <li><a href="/back">/back</a> - Move backward</li>
        <li><a href="/left">/left</a> - Rotate left</li>
        <li><a href="/right">/right</a> - Rotate right</li>
        <li><a href="/stop">/stop</a> - Stop</li>
    </ul>
    """

if __name__ == '__main__':
    print("=" * 50)
    print("Mock NN Server for VizCar Testing")
    print("=" * 50)
    print("This server simulates both the NN server and robot.")
    print()
    print("To test the controller, run in separate terminals:")
    print("  Terminal 1: python mock_nn_server.py")
    print("  Terminal 2: python video_client_controller.py localhost localhost --nn-port 5001 --robot-port 5001")
    print()
    print("API Endpoints:")
    print("  /video_feed - MJPEG video stream")
    print("  /pose       - Robot pose as JSON")
    print("  /status     - Server status")
    print("  /go, /back, /left, /right, /stop - Robot control")
    print("=" * 50)
    
    app.run(host='0.0.0.0', port=5001, threaded=True)