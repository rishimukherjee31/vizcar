#!/usr/bin/env python3
"""
macOS client to display video stream from Raspberry Pi
Connects via Tailscale network
"""

import cv2
import requests
import numpy as np
import threading
import queue
import time
import argparse

class VideoStreamClient:
    def __init__(self, server_url):
        self.server_url = server_url.rstrip('/')
        self.frame_queue = queue.Queue(maxsize=5)
        self.running = False
        self.stream_thread = None
        
    def test_connection(self):
        """Test if server is reachable"""
        try:
            response = requests.get(f"{self.server_url}/status", timeout=5)
            if response.status_code == 200:
                print(f"Connected to server: {self.server_url}")
                return True
        except Exception as e:
            print(f"Failed to connect to server: {e}")
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
    
    def start_streaming(self):
        """Start video streaming"""
        if not self.test_connection():
            return False
            
        self.running = True
        self.stream_thread = threading.Thread(target=self.fetch_frames)
        self.stream_thread.daemon = True
        self.stream_thread.start()
        
        print("Starting video display...")
        print("Press 'q' to quit, 's' to save screenshot")
        
        while self.running:
            try:
                frame = self.frame_queue.get(timeout=1)
                
                # Add overlay with info
                cv2.putText(
                    frame, 
                    f"Pi Camera - {time.strftime('%H:%M:%S')}", 
                    (10, 30), 
                    cv2.FONT_HERSHEY_SIMPLEX, 
                    1, 
                    (0, 255, 0), 
                    2
                )
                
                cv2.imshow('Pi Camera Feed', frame)
                
                key = cv2.waitKey(1) & 0xFF
                if key == ord('q'):
                    break
                elif key == ord('s'):
                    filename = f"screenshot_{int(time.time())}.jpg"
                    cv2.imwrite(filename, frame)
                    print(f"Screenshot saved: {filename}")
                    
            except queue.Empty:
                print("⚠️  No frames received (timeout)")
                continue
            except KeyboardInterrupt:
                break
        
        self.stop()
        return True
    
    def stop(self):
        """Stop streaming and cleanup"""
        print("\nStopping video stream...")
        self.running = False
        
        if self.stream_thread and self.stream_thread.is_alive():
            self.stream_thread.join(timeout=5)
        
        cv2.destroyAllWindows()

def main():
    parser = argparse.ArgumentParser(description='Video stream client for Pi camera')
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
    
    args = parser.parse_args()
    
    server_url = f"http://{args.server_ip}:{args.port}"
    
    print(f"Connecting to Pi camera at: {server_url}")
    
    client = VideoStreamClient(server_url)
    
    try:
        client.start_streaming()
    except KeyboardInterrupt:
        print("\nGoodbye!")
    finally:
        client.stop()

if __name__ == '__main__':
    main()
