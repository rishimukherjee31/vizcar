#!/usr/bin/env python3
"""
Video streaming server for Raspberry Pi with Logitech camera
Serves raw video footage via HTTP API endpoint
"""

from flask import Flask, Response, jsonify
import cv2
import threading
import time
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

class VideoCamera:
    def __init__(self, camera_index=0):
        self.camera_index = camera_index
        self.video = None
        self.fps = 30
        self.frame = None
        self.lock = threading.Lock()
        self.running = False
        self.thread = None
        self.camera_devices = self._find_camera_devices()
        
    def _find_camera_devices(self):
        """Find available camera devices and identify capture devices"""
        import glob
        import os
        import subprocess
        
        devices = []
        capture_devices = []
        
        for device in glob.glob('/dev/video*'):
            try:
                # Test if device is accessible
                if os.access(device, os.R_OK):
                    devices.append(device)
                    
                    # Check if it's a capture device using v4l2-ctl
                    try:
                        result = subprocess.run([
                            'v4l2-ctl', '--device', device, '--info'
                        ], capture_output=True, text=True, timeout=5)
                        
                        if result.returncode == 0 and 'Video Capture' in result.stdout:
                            capture_devices.append(device)
                            logger.info(f"Found capture device: {device}")
                    except (subprocess.TimeoutExpired, FileNotFoundError):
                        # v4l2-ctl not available or timeout
                        pass
                        
                else:
                    logger.warning(f"No read permission for {device}")
            except Exception as e:
                logger.warning(f"Error checking device {device}: {e}")
        
        logger.info(f"Found accessible devices: {devices}")
        logger.info(f"Found capture devices: {capture_devices}")
        return capture_devices if capture_devices else devices
    
    def initialize_camera(self):
        """Initialize camera with optimal settings for Logitech C920"""
        # For C920, typically video0 is capture, video1 is metadata
        # But let's try both to be sure
        devices_to_try = [0, 1]  # Start with the C920 devices
        
        logger.info(f"Initializing Logitech C920 camera...")
        
        for idx in devices_to_try:
            try:
                logger.info(f"Trying camera index {idx} (/dev/video{idx})...")
                
                # Try V4L2 backend first (best for USB cameras)
                self.video = cv2.VideoCapture(idx, cv2.CAP_V4L2)
                
                if not self.video.isOpened():
                    logger.warning(f"Camera {idx} not opened with V4L2, trying default backend")
                    if self.video:
                        self.video.release()
                    
                    # Fallback to default backend
                    self.video = cv2.VideoCapture(idx)
                    if not self.video.isOpened():
                        logger.warning(f"Camera {idx} not opened with any backend")
                        continue
                
                # C920-specific settings
                # Set MJPEG codec first (C920's native format)
                self.video.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc('M','J','P','G'))
                
                # Set resolution (C920 supports multiple resolutions)
                self.video.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
                self.video.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
                self.video.set(cv2.CAP_PROP_FPS, 30)
                
                # Optimize for streaming
                self.video.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                
                # Additional C920 optimizations
                self.video.set(cv2.CAP_PROP_AUTO_EXPOSURE, 1)  # Manual exposure mode
                self.video.set(cv2.CAP_PROP_AUTOFOCUS, 1)      # Enable autofocus
                
                # Give camera time to initialize and adjust
                import time
                time.sleep(3)
                
                # Clear any buffered frames and test
                for warm_up in range(5):
                    ret, _ = self.video.read()
                    if not ret:
                        time.sleep(0.5)
                        continue
                
                # Now test for a good frame
                ret, test_frame = self.video.read()
                if ret and test_frame is not None and test_frame.size > 0:
                    self.camera_index = idx
                    height, width = test_frame.shape[:2]
                    logger.info(f"✅ C920 camera initialized successfully at index {idx}")
                    logger.info(f"📐 Frame size: {width}x{height}")
                    logger.info(f"🎥 FPS: {self.video.get(cv2.CAP_PROP_FPS)}")
                    
                    # Check actual codec being used
                    fourcc = self.video.get(cv2.CAP_PROP_FOURCC)
                    codec = "".join([chr((int(fourcc) >> 8 * i) & 0xFF) for i in range(4)])
                    logger.info(f"📹 Codec: {codec}")
                    
                    return True
                else:
                    logger.warning(f"Camera {idx} opened but failed to capture valid frame")
                    self.video.release()
                    
            except Exception as e:
                logger.error(f"Error with camera {idx}: {e}")
                if self.video:
                    self.video.release()
                continue
        
        # If C920 devices failed, try other indices
        logger.warning("C920 devices failed, trying other indices...")
        other_devices = [2, 4, 6, 8]
        
        for idx in other_devices:
            try:
                logger.info(f"Trying camera index {idx}...")
                self.video = cv2.VideoCapture(idx, cv2.CAP_V4L2)
                
                if self.video.isOpened():
                    self.video.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc('M','J','P','G'))
                    self.video.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
                    self.video.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
                    self.video.set(cv2.CAP_PROP_FPS, 30)
                    self.video.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                    
                    time.sleep(2)
                    ret, test_frame = self.video.read()
                    if ret and test_frame is not None:
                        self.camera_index = idx
                        logger.info(f"Camera initialized at index {idx}")
                        return True
                        
                self.video.release()
            except Exception as e:
                logger.error(f"Error with camera {idx}: {e}")
                continue
        
        logger.error("❌ Failed to initialize C920 camera")
        logger.error("💡 Try running: fswebcam -d /dev/video0 test.jpg")
        logger.error("💡 Or check: v4l2-ctl --device=/dev/video0 --list-formats-ext")
        return False
    
    def start_capture(self):
        """Start video capture in separate thread"""
        if not self.initialize_camera():
            return False
            
        self.running = True
        self.thread = threading.Thread(target=self._capture_frames)
        self.thread.daemon = True
        self.thread.start()
        return True
    
    def _capture_frames(self):
        """Continuously capture frames in background thread"""
        while self.running and self.video:
            try:
                ret, frame = self.video.read()
                if ret:
                    with self.lock:
                        self.frame = frame.copy()
                else:
                    logger.warning("Failed to read frame from camera")
                    time.sleep(0.1)
                    
            except Exception as e:
                logger.error(f"Error capturing frame: {e}")
                time.sleep(0.1)
    
    def get_frame(self):
        """Get the latest frame"""
        with self.lock:
            return self.frame.copy() if self.frame is not None else None
    
    def stop(self):
        """Stop video capture and cleanup"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
        if self.video:
            self.video.release()
        logger.info("Camera stopped")

# Global camera instance
camera = VideoCamera()

def generate_mjpeg_stream():
    """Generate MJPEG stream for HTTP response"""
    while True:
        frame = camera.get_frame()
        if frame is not None:
            # Encode frame as JPEG
            ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
            if ret:
                frame_bytes = buffer.tobytes()
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
        time.sleep(1/30)  # ~30 FPS

@app.route('/')
def index():
    """Basic info endpoint"""
    return jsonify({
        'status': 'running',
        'endpoints': {
            'video_stream': '/video_feed',
            'status': '/status',
            'frame': '/frame'
        }
    })

@app.route('/status')
def status():
    """Camera status endpoint"""
    return jsonify({
        'camera_active': camera.running,
        'camera_index': camera.camera_index,
        'fps': camera.fps
    })

@app.route('/video_feed')
def video_feed():
    """Video streaming endpoint - returns MJPEG stream"""
    return Response(
        generate_mjpeg_stream(),
        mimetype='multipart/x-mixed-replace; boundary=frame'
    )

@app.route('/frame')
def get_single_frame():
    """Get a single frame as JPEG"""
    frame = camera.get_frame()
    if frame is not None:
        ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        if ret:
            return Response(buffer.tobytes(), mimetype='image/jpeg')
    
    return jsonify({'error': 'No frame available'}), 500

if __name__ == '__main__':
    try:
        logger.info("Starting video streaming server...")
        
        if not camera.start_capture():
            logger.error("Failed to start camera capture")
            exit(1)
        
        logger.info("Camera capture started successfully")
        
        # Run Flask server
        # Use 0.0.0.0 to allow connections from other devices in Tailnet
        app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
        
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        camera.stop()
