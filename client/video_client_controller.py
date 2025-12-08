#!/usr/bin/env python3
"""
Enhanced macOS client with vision-based path planning control
- Displays video stream from Raspberry Pi
- Receives neural network pose data via HTTP
- Click to set target, robot navigates using two-phase control
- Pulse-based commands with pose feedback loop

System Architecture:
  - NN Server: Provides /video_feed (MJPEG) and /pose (JSON with front/back markers)
  - ESP32 Robot: Accepts /go, /back, /left, /right, /stop commands
  - This Client: Displays video, click to set target, runs path planning algorithm
"""

import cv2
import requests
import numpy as np
import threading
import queue
import time
import argparse
import math
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional, Tuple, List
from enum import Enum
from collections import deque

class ControlState(Enum):
    IDLE = "IDLE"
    ROTATING = "ROTATING"
    MOVING = "MOVING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"

@dataclass
class RobotPose:
    """Robot pose from neural network"""
    front_x: float  # u_front in image coordinates
    front_y: float  # v_front
    back_x: float   # u_back
    back_y: float   # v_back
    timestamp: float = field(default_factory=time.time)
    
    @property
    def center(self) -> Tuple[float, float]:
        """Center point between front and back markers"""
        return ((self.front_x + self.back_x) / 2, 
                (self.front_y + self.back_y) / 2)
    
    @property
    def front(self) -> Tuple[float, float]:
        return (self.front_x, self.front_y)
    
    @property
    def back(self) -> Tuple[float, float]:
        return (self.back_x, self.back_y)
    
    @property
    def heading(self) -> float:
        """Heading angle in radians. 
        In image coordinates: 0 = right, pi/2 = down, pi = left, -pi/2 = up
        """
        return math.atan2(self.front_y - self.back_y, 
                         self.front_x - self.back_x)
    
    @property
    def heading_degrees(self) -> float:
        return math.degrees(self.heading)


def normalize_angle(angle: float) -> float:
    """Normalize angle to [-pi, pi]"""
    while angle > math.pi:
        angle -= 2 * math.pi
    while angle < -math.pi:
        angle += 2 * math.pi
    return angle


class PathPlanningController:
    """
    Two-phase path planning controller:
    Phase 1 (ROTATING): Rotate until heading points toward target
    Phase 2 (MOVING): Move forward, re-rotate if deviation exceeds threshold
    """
    
    def __init__(self, 
                 arrival_threshold: float = 30.0,      # pixels - success radius ρ
                 heading_threshold: float = 0.15,      # radians (~8.6°) - ε_θ
                 max_iterations: int = 500,            # k_max
                 max_rotation_steps: int = 50,         # max steps in single rotation phase
                 pulse_duration: float = 0.20,         # seconds - motor pulse duration (200ms)
                 settle_time: float = 5.0):            # seconds - time to wait for new pose after pulse
        
        self.arrival_threshold = arrival_threshold  # ρ
        self.heading_threshold = heading_threshold  # ε_θ
        self.max_iterations = max_iterations        # k_max
        self.max_rotation_steps = max_rotation_steps
        self.pulse_duration = pulse_duration
        self.settle_time = settle_time
        
        # State
        self.state = ControlState.IDLE
        self.target: Optional[Tuple[float, float]] = None
        self.iteration = 0
        self.rotation_steps = 0
        
        # Path history for visualization
        self.path_history: deque = deque(maxlen=500)
        
    def set_target(self, x: float, y: float):
        """Set new target position (in image coordinates)"""
        self.target = (x, y)
        self.state = ControlState.ROTATING
        self.iteration = 0
        self.rotation_steps = 0
        self.path_history.clear()
        print(f"🎯 Target set: ({x:.1f}, {y:.1f})")
        
    def cancel(self):
        """Cancel current navigation"""
        self.state = ControlState.IDLE
        self.target = None
        print("❌ Navigation cancelled")
        
    def compute_desired_heading(self, pose: RobotPose) -> float:
        """Compute desired heading angle from front of robot to target"""
        if self.target is None:
            return 0.0
        dx = self.target[0] - pose.front_x
        dy = self.target[1] - pose.front_y
        return math.atan2(dy, dx)
    
    def compute_heading_error(self, pose: RobotPose) -> float:
        """Compute normalized heading error e_θ = norm(θ_desired - θ_current)"""
        desired = self.compute_desired_heading(pose)
        current = pose.heading
        error = normalize_angle(desired - current)
        return error
    
    def compute_distance(self, pose: RobotPose) -> float:
        """Compute distance from front of robot to target: d = ||p_front - p_target||"""
        if self.target is None:
            return float('inf')
        dx = self.target[0] - pose.front_x
        dy = self.target[1] - pose.front_y
        return math.sqrt(dx*dx + dy*dy)
    
    def get_command(self, pose: RobotPose) -> Optional[str]:
        """
        Main control loop iteration (Algorithm from your slides):
        
        At iteration k:
        1. Get pose → calculate d^k, e_θ^k
        2. If d^k ≤ ρ: SUCCESS
        3. If |e_θ^k| > ε_θ: rotate until aligned
        4. Else: execute forward pulse
        5. k ← k+1, repeat if k < k_max
        """
        if self.state == ControlState.IDLE:
            return None
        if self.state in (ControlState.SUCCESS, ControlState.FAILED):
            return None
        if self.target is None:
            return None
            
        # Record path
        self.path_history.append(pose.front)
        
        # Step 1: Calculate d^k and e_θ^k
        distance = self.compute_distance(pose)
        heading_error = self.compute_heading_error(pose)
        
        self.iteration += 1
        
        # Check failure condition: k ≥ k_max
        if self.iteration >= self.max_iterations:
            self.state = ControlState.FAILED
            print(f"❌ FAILED: Max iterations ({self.max_iterations}) exceeded")
            return "stop"
        
        # Step 2: Check success condition: d^k ≤ ρ
        if distance <= self.arrival_threshold:
            self.state = ControlState.SUCCESS
            print(f"✅ SUCCESS! Reached target in {self.iteration} iterations")
            return "stop"
        
        # Step 3: If |e_θ^k| > ε_θ: rotate until aligned
        if abs(heading_error) > self.heading_threshold:
            self.state = ControlState.ROTATING
            self.rotation_steps += 1
            
            # Check rotation timeout
            if self.rotation_steps > self.max_rotation_steps:
                self.state = ControlState.FAILED
                print(f"❌ FAILED: Rotation timeout ({self.max_rotation_steps} steps)")
                return "stop"
            
            # Determine rotation direction
            # Positive error = target is to the right (clockwise in image coords)
            # Negative error = target is to the left (counter-clockwise)
            if heading_error > 0:
                return "right"  # Turn right (clockwise)
            else:
                return "left"   # Turn left (counter-clockwise)
        
        # Step 4: Heading aligned, move forward
        self.state = ControlState.MOVING
        self.rotation_steps = 0  # Reset rotation counter
        return "back"
    
    def get_status_text(self, pose: Optional[RobotPose] = None) -> List[str]:
        """Get status text for overlay"""
        lines = [f"State: {self.state.value}"]
        
        if self.target:
            lines.append(f"Target: ({self.target[0]:.0f}, {self.target[1]:.0f})")
            
        if pose and self.target:
            distance = self.compute_distance(pose)
            heading_error = self.compute_heading_error(pose)
            lines.append(f"Distance: {distance:.1f}px (threshold: {self.arrival_threshold})")
            lines.append(f"Heading error: {math.degrees(heading_error):.1f}° (threshold: {math.degrees(self.heading_threshold):.1f}°)")
            lines.append(f"Iteration: {self.iteration}/{self.max_iterations}")
            
        return lines


class RobotCommander:
    """Sends HTTP commands to ESP32 robot with pulse timing"""
    
    def __init__(self, robot_url: str, pulse_duration: float = 0.15):
        self.robot_url = robot_url.rstrip('/')
        self.pulse_duration = pulse_duration
        self.last_command = None
        self.last_command_time = 0
        
    def send_command(self, command: str) -> bool:
        """Send command to robot"""
        try:
            response = requests.get(f"{self.robot_url}/{command}", timeout=1)
            self.last_command = command
            self.last_command_time = time.time()
            return response.status_code == 200
        except Exception as e:
            print(f"⚠️ Command failed: {e}")
            return False
    
    def pulse(self, command: str) -> bool:
        """Send a pulse command (command for duration, then stop)"""
        if command == "stop":
            return self.send_command("stop")
        
        success = self.send_command(command)
        if success:
            time.sleep(self.pulse_duration)
            self.send_command("stop")
        return success
    
    def stop(self):
        """Emergency stop"""
        self.send_command("stop")


class PoseClient:
    """Fetches pose data from NN server's /detections endpoint"""
    
    def __init__(self, nn_server_url: str, front_keypoint: int = 0, car_id: int = 0):
        self.nn_server_url = nn_server_url.rstrip('/')
        self.latest_pose: Optional[RobotPose] = None
        self.pose_lock = threading.Lock()
        self.running = False
        self.poll_thread = None
        
        # Configuration: which keypoint index is front vs back
        # keypoint_0 = front (index 0), keypoint_1 = back (index 1) by default
        # Set front_keypoint=1 if your labeling is reversed
        self.front_keypoint = front_keypoint
        self.back_keypoint = 1 - front_keypoint  # The other one
        
        # Which car to track (if multiple detections)
        self.car_id = car_id
        
        # Stats
        self.last_fps = 0
        self.last_inference_ms = 0
        self.detection_confidence = 0
        
    def fetch_pose(self) -> Optional[RobotPose]:
        """Fetch latest pose from NN server /detections endpoint"""
        try:
            response = requests.get(f"{self.nn_server_url}/detections", timeout=1)
            if response.status_code == 200:
                data = response.json()
                
                # Update stats
                self.last_fps = data.get('fps', 0)
                self.last_inference_ms = data.get('inference_ms', 0)
                
                detections = data.get('detections', [])
                
                if not detections:
                    return None
                
                # Find the detection we want to track
                detection = None
                if self.car_id < len(detections):
                    detection = detections[self.car_id]
                else:
                    # Just use the first detection
                    detection = detections[0]
                
                if not detection:
                    return None
                
                keypoints = detection.get('keypoints', [])
                
                if len(keypoints) < 2:
                    return None
                
                # Extract front and back keypoints
                front_kp = keypoints[self.front_keypoint]
                back_kp = keypoints[self.back_keypoint]
                
                # Check confidence threshold
                min_conf = min(front_kp.get('confidence', 0), back_kp.get('confidence', 0))
                self.detection_confidence = min_conf
                
                if min_conf < 0.3:  # Skip low confidence detections
                    return None
                
                pose = RobotPose(
                    front_x=front_kp['x'],
                    front_y=front_kp['y'],
                    back_x=back_kp['x'],
                    back_y=back_kp['y'],
                    timestamp=time.time()
                )
                
                with self.pose_lock:
                    self.latest_pose = pose
                return pose
                
        except Exception as e:
            pass  # Silently fail, will retry
        return None
    
    def start_polling(self, interval: float = 0.05):
        """Start background pose polling"""
        self.running = True
        self.poll_thread = threading.Thread(target=self._poll_loop, args=(interval,))
        self.poll_thread.daemon = True
        self.poll_thread.start()
        
    def _poll_loop(self, interval: float):
        while self.running:
            self.fetch_pose()
            time.sleep(interval)
            
    def stop(self):
        self.running = False
        if self.poll_thread:
            self.poll_thread.join(timeout=1)
            
    def get_latest(self) -> Optional[RobotPose]:
        with self.pose_lock:
            return self.latest_pose


class VideoStreamClient:
    """Enhanced video client with path planning control"""
    
    def __init__(self, nn_server_url: str, robot_url: str, front_keypoint: int = 0):
        self.nn_server_url = nn_server_url.rstrip('/')
        self.robot_url = robot_url.rstrip('/')
        
        self.frame_queue = queue.Queue(maxsize=5)
        self.running = False
        self.stream_thread = None
        
        # Components
        self.pose_client = PoseClient(nn_server_url, front_keypoint=front_keypoint)
        self.robot = RobotCommander(robot_url)
        self.controller = PathPlanningController()
        
        # Control thread
        self.control_thread = None
        self.control_running = False
        
        # Recording
        self.recording = False
        self.video_writer = None
        self.recording_filename = None
        self.recording_start_time = None
        self.frames_recorded = 0
        
        # Video settings
        self.fps = 30.0
        self.frame_width = 640
        self.frame_height = 480
        
    def test_connection(self) -> bool:
        """Test connections to NN server and robot"""
        try:
            # Test NN server
            response = requests.get(f"{self.nn_server_url}/status", timeout=5)
            if response.status_code == 200:
                print(f"✅ Connected to NN server: {self.nn_server_url}")
            else:
                print(f"⚠️ NN server responded with: {response.status_code}")
        except Exception as e:
            print(f"❌ Failed to connect to NN server: {e}")
            return False
            
        try:
            # Test robot (just check if reachable)
            response = requests.get(f"{self.robot_url}/", timeout=5)
            print(f"✅ Connected to robot: {self.robot_url}")
        except Exception as e:
            print(f"⚠️ Robot connection test failed (may still work): {e}")
            
        return True
    
    def fetch_frames(self):
        """Fetch frames from MJPEG stream"""
        try:
            response = requests.get(
                f"{self.nn_server_url}/video_feed", 
                stream=True, 
                timeout=10
            )
            
            if response.status_code != 200:
                print(f"Error: HTTP {response.status_code}")
                return
                
            bytes_data = b''
            
            for chunk in response.iter_content(chunk_size=1024):
                if not self.running:
                    break
                    
                bytes_data += chunk
                
                start = bytes_data.find(b'\xff\xd8')
                end = bytes_data.find(b'\xff\xd9')
                
                if start != -1 and end != -1 and start < end:
                    jpg_data = bytes_data[start:end + 2]
                    bytes_data = bytes_data[end + 2:]
                    
                    frame = cv2.imdecode(
                        np.frombuffer(jpg_data, dtype=np.uint8), 
                        cv2.IMREAD_COLOR
                    )
                    
                    if frame is not None:
                        if self.frame_width == 640:
                            self.frame_height, self.frame_width = frame.shape[:2]
                        
                        try:
                            self.frame_queue.put(frame, block=False)
                        except queue.Full:
                            try:
                                self.frame_queue.get_nowait()
                                self.frame_queue.put(frame, block=False)
                            except queue.Empty:
                                pass
                                
        except Exception as e:
            print(f"Error fetching frames: {e}")
    
    def control_loop(self):
        """Background control loop - runs path planning algorithm"""
        while self.control_running:
            if self.controller.state in (ControlState.ROTATING, ControlState.MOVING):
                pose = self.pose_client.get_latest()
                if pose:
                    command = self.controller.get_command(pose)
                    if command:
                        self.robot.pulse(command)
                        # Wait for robot to settle and new pose
                        time.sleep(self.controller.settle_time)
                else:
                    time.sleep(0.05)  # No pose available, wait
            else:
                time.sleep(0.1)  # Idle, check less frequently
    
    def draw_overlay(self, frame: np.ndarray, pose: Optional[RobotPose]) -> np.ndarray:
        """Draw visualization overlay on frame"""
        overlay = frame.copy()
        
        # Draw target
        if self.controller.target:
            tx, ty = int(self.controller.target[0]), int(self.controller.target[1])
            # Target circle with crosshair
            cv2.circle(overlay, (tx, ty), int(self.controller.arrival_threshold), (0, 255, 255), 2)
            cv2.circle(overlay, (tx, ty), 5, (0, 255, 255), -1)
            cv2.line(overlay, (tx - 15, ty), (tx + 15, ty), (0, 255, 255), 2)
            cv2.line(overlay, (tx, ty - 15), (tx, ty + 15), (0, 255, 255), 2)
        
        # Draw path history
        if len(self.controller.path_history) > 1:
            points = np.array(list(self.controller.path_history), dtype=np.int32)
            cv2.polylines(overlay, [points], False, (255, 255, 0), 2)
        
        # Draw robot pose
        if pose:
            fx, fy = int(pose.front_x), int(pose.front_y)
            bx, by = int(pose.back_x), int(pose.back_y)
            cx, cy = int(pose.center[0]), int(pose.center[1])
            
            # Robot body line
            cv2.line(overlay, (bx, by), (fx, fy), (0, 255, 0), 3)
            
            # Front marker (blue)
            cv2.circle(overlay, (fx, fy), 8, (255, 0, 0), -1)
            
            # Back marker (red)
            cv2.circle(overlay, (bx, by), 8, (0, 0, 255), -1)
            
            # Center marker
            cv2.circle(overlay, (cx, cy), 4, (0, 255, 0), -1)
            
            # Heading arrow
            arrow_len = 40
            hx = int(fx + arrow_len * math.cos(pose.heading))
            hy = int(fy + arrow_len * math.sin(pose.heading))
            cv2.arrowedLine(overlay, (fx, fy), (hx, hy), (0, 255, 0), 2, tipLength=0.3)
            
            # Draw desired heading if target exists
            if self.controller.target and self.controller.state != ControlState.IDLE:
                desired_heading = self.controller.compute_desired_heading(pose)
                dhx = int(fx + arrow_len * math.cos(desired_heading))
                dhy = int(fy + arrow_len * math.sin(desired_heading))
                cv2.arrowedLine(overlay, (fx, fy), (dhx, dhy), (0, 255, 255), 2, tipLength=0.3)
        
        # Draw status text
        y_offset = 30
        status_lines = self.controller.get_status_text(pose)
        for line in status_lines:
            cv2.putText(overlay, line, (10, y_offset), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
            y_offset += 25
        
        # State indicator
        state_colors = {
            ControlState.IDLE: (128, 128, 128),
            ControlState.ROTATING: (0, 165, 255),
            ControlState.MOVING: (0, 255, 0),
            ControlState.SUCCESS: (0, 255, 0),
            ControlState.FAILED: (0, 0, 255)
        }
        color = state_colors.get(self.controller.state, (255, 255, 255))
        cv2.rectangle(overlay, (frame.shape[1] - 120, 10), (frame.shape[1] - 10, 40), color, -1)
        cv2.putText(overlay, self.controller.state.value, (frame.shape[1] - 115, 32),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 2)
        
        # Recording indicator
        if self.recording:
            cv2.circle(overlay, (frame.shape[1] - 30, 60), 10, (0, 0, 255), -1)
            cv2.putText(overlay, "REC", (frame.shape[1] - 70, 65),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)
        
        # Timestamp and NN stats
        stats_text = f"{time.strftime('%H:%M:%S')} | NN: {self.pose_client.last_fps:.1f}fps {self.pose_client.last_inference_ms:.0f}ms"
        if pose:
            stats_text += f" | Conf: {self.pose_client.detection_confidence:.2f}"
        cv2.putText(overlay, stats_text, (10, frame.shape[0] - 10),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        
        return overlay
    
    def mouse_callback(self, event, x, y, flags, param):
        """Handle mouse clicks to set target"""
        if event == cv2.EVENT_LBUTTONDOWN:
            # Left click - set target
            self.controller.set_target(x, y)
        elif event == cv2.EVENT_RBUTTONDOWN:
            # Right click - cancel navigation
            self.controller.cancel()
            self.robot.stop()
    
    def start_recording(self, filename=None):
        """Start recording video"""
        if self.recording:
            return False
        
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"vizcar_recording_{timestamp}.mp4"
        
        self.recording_filename = filename
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        self.video_writer = cv2.VideoWriter(
            filename, fourcc, self.fps, (self.frame_width, self.frame_height)
        )
        
        if not self.video_writer.isOpened():
            print(f"❌ Failed to create video writer")
            return False
        
        self.recording = True
        self.recording_start_time = time.time()
        self.frames_recorded = 0
        print(f"🔴 Recording started: {filename}")
        return True
    
    def stop_recording(self):
        """Stop recording video"""
        if not self.recording:
            return False
        
        self.recording = False
        if self.video_writer:
            self.video_writer.release()
            self.video_writer = None
        
        print(f"⏹️ Recording stopped: {self.recording_filename}")
        return True
    
    def start_streaming(self):
        """Start video streaming with control"""
        if not self.test_connection():
            return False
        
        self.running = True
        
        # Start pose polling
        self.pose_client.start_polling()
        
        # Start frame fetching
        self.stream_thread = threading.Thread(target=self.fetch_frames)
        self.stream_thread.daemon = True
        self.stream_thread.start()
        
        # Start control loop
        self.control_running = True
        self.control_thread = threading.Thread(target=self.control_loop)
        self.control_thread.daemon = True
        self.control_thread.start()
        
        print("\n🎥 Video stream started!")
        print("📋 Controls:")
        print("  Left click  - Set target (robot will navigate)")
        print("  Right click - Cancel navigation")
        print("  'q'         - Quit")
        print("  's'         - Save screenshot")
        print("  'r'         - Start/stop recording")
        print("  'c'         - Cancel navigation")
        print("  'SPACE'     - Emergency stop")
        print("  '+'         - Increase arrival threshold")
        print("  '-'         - Decrease arrival threshold")
        print()
        
        window_name = 'VizCar Path Planning Controller'
        cv2.namedWindow(window_name)
        cv2.setMouseCallback(window_name, self.mouse_callback)
        
        while self.running:
            try:
                frame = self.frame_queue.get(timeout=1)
                
                # Get current pose for overlay
                pose = self.pose_client.get_latest()
                
                # Draw overlay
                display_frame = self.draw_overlay(frame, pose)
                
                # Record if active
                if self.recording and self.video_writer:
                    self.video_writer.write(display_frame)
                    self.frames_recorded += 1
                
                cv2.imshow(window_name, display_frame)
                
                key = cv2.waitKey(1) & 0xFF
                if key == ord('q'):
                    break
                elif key == ord('s'):
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    filename = f"screenshot_{timestamp}.jpg"
                    cv2.imwrite(filename, display_frame)
                    print(f"📸 Screenshot saved: {filename}")
                elif key == ord('r'):
                    if self.recording:
                        self.stop_recording()
                    else:
                        self.start_recording()
                elif key == ord('c'):
                    self.controller.cancel()
                    self.robot.stop()
                elif key == ord(' '):  # Space = emergency stop
                    self.controller.cancel()
                    self.robot.stop()
                    print("🛑 EMERGENCY STOP")
                elif key == ord('+') or key == ord('='):
                    self.controller.arrival_threshold += 5
                    print(f"📏 Arrival threshold: {self.controller.arrival_threshold}")
                elif key == ord('-'):
                    self.controller.arrival_threshold = max(10, self.controller.arrival_threshold - 5)
                    print(f"📏 Arrival threshold: {self.controller.arrival_threshold}")
                    
            except queue.Empty:
                continue
            except KeyboardInterrupt:
                break
        
        self.stop()
        return True
    
    def stop(self):
        """Stop all components"""
        print("\n🛑 Shutting down...")
        
        self.running = False
        self.control_running = False
        
        # Stop robot
        self.robot.stop()
        
        # Stop recording
        if self.recording:
            self.stop_recording()
        
        # Stop pose client
        self.pose_client.stop()
        
        # Wait for threads
        if self.stream_thread and self.stream_thread.is_alive():
            self.stream_thread.join(timeout=2)
        if self.control_thread and self.control_thread.is_alive():
            self.control_thread.join(timeout=2)
        
        cv2.destroyAllWindows()
        print("👋 Goodbye!")


def main():
    parser = argparse.ArgumentParser(
        description='VizCar Path Planning Controller',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s 192.168.1.100 192.168.1.50
  %(prog)s 100.64.0.1 192.168.4.1 --nn-port 5000 --robot-port 80
  %(prog)s 100.64.0.1 192.168.4.1 --arrival-threshold 50 --heading-threshold 10
        """
    )
    
    parser.add_argument('nn_server_ip', 
                        help='IP address of NN server (provides video feed and pose)')
    parser.add_argument('robot_ip', 
                        help='IP address of ESP32 robot')
    parser.add_argument('--nn-port', type=int, default=5000,
                        help='NN server port (default: 5000)')
    parser.add_argument('--robot-port', type=int, default=80,
                        help='Robot HTTP port (default: 80)')
    parser.add_argument('--arrival-threshold', type=float, default=30.0,
                        help='Distance threshold for arrival in pixels (default: 30)')
    parser.add_argument('--heading-threshold', type=float, default=8.0,
                        help='Heading error threshold in degrees (default: 8)')
    parser.add_argument('--pulse-duration', type=float, default=0.20,
                        help='Motor pulse duration in seconds (default: 0.20)')
    parser.add_argument('--settle-time', type=float, default=5.0,
                        help='Wait time after each pulse in seconds (default: 5.0)')
    parser.add_argument('--max-iterations', type=int, default=500,
                        help='Maximum control iterations (default: 500)')
    parser.add_argument('--front-keypoint', type=int, default=0, choices=[0, 1],
                        help='Which keypoint index is the front marker: 0 or 1 (default: 0)')
    
    args = parser.parse_args()
    
    nn_server_url = f"http://{args.nn_server_ip}:{args.nn_port}"
    robot_url = f"http://{args.robot_ip}:{args.robot_port}"
    
    print("=" * 60)
    print("🤖 VizCar Path Planning Controller")
    print("=" * 60)
    print(f"📡 NN Server: {nn_server_url}")
    print(f"🎮 Robot:     {robot_url}")
    print(f"📏 Arrival threshold: {args.arrival_threshold} pixels")
    print(f"🧭 Heading threshold: {args.heading_threshold}°")
    print(f"⏱️ Pulse duration: {args.pulse_duration}s")
    print(f"⏳ Settle time: {args.settle_time}s")
    print(f"🔑 Front keypoint index: {args.front_keypoint}")
    print("=" * 60)
    
    client = VideoStreamClient(nn_server_url, robot_url, front_keypoint=args.front_keypoint)
    
    # Configure controller
    client.controller.arrival_threshold = args.arrival_threshold
    client.controller.heading_threshold = math.radians(args.heading_threshold)
    client.controller.pulse_duration = args.pulse_duration
    client.controller.settle_time = args.settle_time
    client.controller.max_iterations = args.max_iterations
    client.robot.pulse_duration = args.pulse_duration
    
    try:
        client.start_streaming()
    except KeyboardInterrupt:
        pass
    finally:
        client.stop()


if __name__ == '__main__':
    main()