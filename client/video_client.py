#!/usr/bin/env python3
"""
Enhanced macOS client to display and record video stream from Raspberry Pi
Connects via Tailscale network with recording capabilities
"""

import cv2
import requests
import numpy as np
import threading
import queue
import time
import argparse
import os
from datetime import datetime

class VideoStreamClient:
    def __init__(self, server_url):
        self.server_url = server_url.rstrip('/')
        self.frame_queue = queue.Queue(maxsize=5)
        self.running = False
        self.stream_thread = None
        
        # Recording variables
        self.recording = False
        self.video_writer = None
        self.recording_filename = None
        self.recording_start_time = None
        self.frames_recorded = 0
        
        # Video settings
        self.fps = 30.0
        self.frame_width = 1280
        self.frame_height = 720
        
    def test_connection(self):
        """Test if server is reachable"""
        try:
            response = requests.get(f"{self.server_url}/status", timeout=5)
            if response.status_code == 200:
                print(f"✅ Connected to server: {self.server_url}")
                return True
        except Exception as e:
            print(f"❌ Failed to connect to server: {e}")
            return False
    
    def fetch_frames(self):
        """Fetch frames from MJPEG stream"""
        try:
            response = requests.get(
                f"{self.server_url}/video_feed", 
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
                
                start = bytes_data.find(b'\xff\xd8')  # JPEG start
                end = bytes_data.find(b'\xff\xd9')    # JPEG end
                
                if start != -1 and end != -1 and start < end:
                    jpg_data = bytes_data[start:end + 2]
                    bytes_data = bytes_data[end + 2:]
                    
                    frame = cv2.imdecode(
                        np.frombuffer(jpg_data, dtype=np.uint8), 
                        cv2.IMREAD_COLOR
                    )
                    
                    if frame is not None:
                        # Store frame dimensions on first frame
                        if self.frame_width == 1280:  # Default value
                            self.frame_height, self.frame_width = frame.shape[:2]
                        
                        try:
                            self.frame_queue.put(frame, block=False)
                        except queue.Full:
                            try:
                                self.frame_queue.get_nowait()  # Remove oldest frame
                                self.frame_queue.put(frame, block=False)
                            except queue.Empty:
                                pass
                                
        except Exception as e:
            print(f"Error fetching frames: {e}")
    
    def start_recording(self, filename=None):
        """Start recording video"""
        if self.recording:
            print("⚠️  Already recording!")
            return False
        
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"vizcar_recording_{timestamp}.mp4"
        
        self.recording_filename = filename
        
        # Create video writer with H.264 codec
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')  # or 'XVID' for .avi files
        self.video_writer = cv2.VideoWriter(
            filename, 
            fourcc, 
            self.fps, 
            (self.frame_width, self.frame_height)
        )
        
        if not self.video_writer.isOpened():
            print(f"❌ Failed to create video writer for {filename}")
            return False
        
        self.recording = True
        self.recording_start_time = time.time()
        self.frames_recorded = 0
        
        print(f"🔴 Started recording to: {filename}")
        print(f"📐 Resolution: {self.frame_width}x{self.frame_height} @ {self.fps} FPS")
        return True
    
    def stop_recording(self):
        """Stop recording video"""
        if not self.recording:
            print("⚠️  Not currently recording!")
            return False
        
        self.recording = False
        
        if self.video_writer:
            self.video_writer.release()
            self.video_writer = None
        
        recording_duration = time.time() - self.recording_start_time
        file_size = os.path.getsize(self.recording_filename) / (1024 * 1024)  # MB
        
        print(f"⏹️  Recording stopped: {self.recording_filename}")
        print(f"⏱️  Duration: {recording_duration:.1f} seconds")
        print(f"🎞️  Frames recorded: {self.frames_recorded}")
        print(f"📁 File size: {file_size:.1f} MB")
        
        return True
    
    def write_frame(self, frame):
        """Write frame to video file if recording"""
        if self.recording and self.video_writer:
            self.video_writer.write(frame)
            self.frames_recorded += 1
    
    def get_recording_info(self):
        """Get current recording information"""
        if not self.recording:
            return "Not recording"
        
        duration = time.time() - self.recording_start_time
        return f"Recording: {duration:.0f}s | Frames: {self.frames_recorded}"
    
    def start_streaming(self):
        """Start video streaming with recording support"""
        if not self.test_connection():
            return False
            
        self.running = True
        self.stream_thread = threading.Thread(target=self.fetch_frames)
        self.stream_thread.daemon = True
        self.stream_thread.start()
        
        print("🎥 Starting video display...")
        print("📋 Controls:")
        print("  'q' - Quit")
        print("  's' - Save screenshot") 
        print("  'r' - Start/stop recording")
        print("  'p' - Pause/unpause display")
        print("  'f' - Toggle fullscreen")
        
        paused = False
        fullscreen = False
        
        while self.running:
            try:
                frame = self.frame_queue.get(timeout=1)
                
                # Write frame to recording if active
                self.write_frame(frame)
                
                if not paused:
                    # Add overlay with info
                    info_text = f"Pi Camera - {time.strftime('%H:%M:%S')}"
                    cv2.putText(
                        frame, 
                        info_text,
                        (10, 30), 
                        cv2.FONT_HERSHEY_SIMPLEX, 
                        0.7, 
                        (0, 255, 0), 
                        2
                    )
                    
                    # Add recording indicator
                    if self.recording:
                        recording_info = self.get_recording_info()
                        cv2.putText(
                            frame,
                            f"🔴 {recording_info}",
                            (10, 60),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.6,
                            (0, 0, 255),
                            2
                        )
                        
                        # Add red recording dot
                        cv2.circle(frame, (frame.shape[1] - 30, 30), 10, (0, 0, 255), -1)
                    
                    # Show frame
                    window_name = 'Pi Camera Feed'
                    cv2.imshow(window_name, frame)
                    
                    # Handle fullscreen
                    if fullscreen:
                        cv2.setWindowProperty(window_name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
                    else:
                        cv2.setWindowProperty(window_name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_NORMAL)
                
                # Handle key presses
                key = cv2.waitKey(1) & 0xFF
                if key == ord('q'):
                    break
                elif key == ord('s'):
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    filename = f"screenshot_{timestamp}.jpg"
                    cv2.imwrite(filename, frame)
                    print(f"📸 Screenshot saved: {filename}")
                elif key == ord('r'):
                    if self.recording:
                        self.stop_recording()
                    else:
                        self.start_recording()
                elif key == ord('p'):
                    paused = not paused
                    status = "paused" if paused else "resumed"
                    print(f"⏸️ Display {status}")
                elif key == ord('f'):
                    fullscreen = not fullscreen
                    print(f"🖥️ Fullscreen {'enabled' if fullscreen else 'disabled'}")
                elif key == 27:  # Escape key
                    if fullscreen:
                        fullscreen = False
                        print("🖥️ Fullscreen disabled")
                    
            except queue.Empty:
                print("⚠️  No frames received (timeout)")
                continue
            except KeyboardInterrupt:
                break
        
        # Make sure to stop recording if still active
        if self.recording:
            self.stop_recording()
        
        self.stop()
        return True
    
    def stop(self):
        """Stop streaming and cleanup"""
        print("\n🛑 Stopping video stream...")
        self.running = False
        
        # Stop recording if active
        if self.recording:
            self.stop_recording()
        
        if self.stream_thread and self.stream_thread.is_alive():
            self.stream_thread.join(timeout=5)
        
        cv2.destroyAllWindows()

def main():
    parser = argparse.ArgumentParser(description='Enhanced video stream client with recording')
    parser.add_argument(
        'server_ip', 
        help='Tailscale IP address of Raspberry Pi (e.g., 100.64.0.1)'
    )
    parser.add_argument(
        '--port', 
        default=5000, 
        type=int, 
        help='Server port (default: 5000)'
    )
    parser.add_argument(
        '--output', 
        default=None, 
        help='Output filename for recording (default: auto-generated)'
    )
    parser.add_argument(
        '--fps', 
        default=30.0, 
        type=float, 
        help='Recording FPS (default: 30.0)'
    )
    parser.add_argument(
        '--auto-record', 
        action='store_true', 
        help='Start recording automatically'
    )
    
    args = parser.parse_args()
    
    server_url = f"http://{args.server_ip}:{args.port}"
    
    print(f"🔗 Connecting to Pi camera at: {server_url}")
    
    client = VideoStreamClient(server_url)
    client.fps = args.fps
    
    try:
        # Auto-start recording if requested
        if args.auto_record:
            print("🔴 Auto-recording enabled")
            
        if client.start_streaming():
            if args.auto_record:
                client.start_recording(args.output)
                
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
    finally:
        client.stop()

if __name__ == '__main__':
    main()
