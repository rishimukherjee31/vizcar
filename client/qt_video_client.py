#!/usr/bin/env python3
"""
Simple PyQt5 video viewer for Raspberry Pi camera stream
Displays video feed only - no recording features
"""

import sys
import cv2
import requests
import numpy as np
import time
import argparse
from PyQt5.QtWidgets import QApplication, QMainWindow, QLabel, QMessageBox
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QImage, QPixmap


class StreamThread(QThread):
    """Thread for fetching video frames from server"""
    frame_ready = pyqtSignal(np.ndarray)
    connection_error = pyqtSignal(str)
    
    def __init__(self, server_url):
        super().__init__()
        self.server_url = server_url
        self.running = False
        
    def run(self):
        """Fetch frames from MJPEG stream"""
        self.running = True
        
        try:
            response = requests.get(
                f"{self.server_url}/video_feed", 
                stream=True, 
                timeout=10
            )
            
            if response.status_code != 200:
                self.connection_error.emit(f"HTTP Error {response.status_code}")
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
                        self.frame_ready.emit(frame)
                        
        except Exception as e:
            self.connection_error.emit(f"Connection error: {str(e)}")
    
    def stop(self):
        """Stop the stream thread"""
        self.running = False


class VideoViewer(QMainWindow):
    """Simple video viewer window"""
    
    def __init__(self, server_url):
        super().__init__()
        self.server_url = server_url
        self.stream_thread = None
        
        self.init_ui()
        self.start_stream()
        
    def init_ui(self):
        """Initialize the user interface"""
        self.setWindowTitle('Pi Camera Stream')
        self.setGeometry(100, 100, 1280, 720)
        
        # Video display label
        self.video_label = QLabel(self)
        self.video_label.setAlignment(Qt.AlignCenter)
        self.video_label.setStyleSheet("QLabel { background-color: black; }")
        self.setCentralWidget(self.video_label)
        
    def test_connection(self):
        """Test if server is reachable"""
        try:
            response = requests.get(f"{self.server_url}/status", timeout=5)
            return response.status_code == 200
        except:
            return False
    
    def start_stream(self):
        """Start video streaming"""
        if not self.test_connection():
            QMessageBox.critical(
                self, 
                'Connection Error', 
                f'Cannot connect to server at {self.server_url}\n\n'
                'Please check:\n'
                '- Raspberry Pi is powered on\n'
                '- Tailscale is running\n'
                '- Server is running on Pi\n'
                '- IP address is correct'
            )
            sys.exit(1)
        
        # Start stream thread
        self.stream_thread = StreamThread(self.server_url)
        self.stream_thread.frame_ready.connect(self.update_frame)
        self.stream_thread.connection_error.connect(self.handle_error)
        self.stream_thread.start()
    
    def update_frame(self, frame):
        """Update video display with new frame"""
        # Convert frame to QPixmap for display
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = frame_rgb.shape
        bytes_per_line = ch * w
        
        q_image = QImage(frame_rgb.data, w, h, bytes_per_line, QImage.Format_RGB888)
        pixmap = QPixmap.fromImage(q_image)
        
        # Scale to fit window while maintaining aspect ratio
        scaled_pixmap = pixmap.scaled(
            self.video_label.size(), 
            Qt.KeepAspectRatio, 
            Qt.SmoothTransformation
        )
        
        self.video_label.setPixmap(scaled_pixmap)
    
    def handle_error(self, error_msg):
        """Handle connection errors"""
        QMessageBox.critical(self, 'Stream Error', error_msg)
        self.close()
    
    def closeEvent(self, event):
        """Clean up when window closes"""
        if self.stream_thread:
            self.stream_thread.stop()
            self.stream_thread.wait()
        event.accept()


def main():
    parser = argparse.ArgumentParser(description='Simple Pi Camera video viewer')
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
    
    app = QApplication(sys.argv)
    viewer = VideoViewer(server_url)
    viewer.show()
    
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()