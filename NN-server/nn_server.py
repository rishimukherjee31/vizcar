#!/usr/bin/env python3

from flask import Flask, Response, jsonify, request
from flask_cors import CORS
import cv2
import numpy as np
from ultralytics import YOLO
import threading
import time
import logging
from collections import deque
from datetime import datetime
import json
import torch

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)  # Enable CORS for cross-origin requests

class YOLOPoseProcessor:
    def __init__(self, source_url, model_name="best.pt"):
        """
        Initialize YOLO pose processor
        
        Args:
            source_url: URL of the video stream (e.g., http://pi-hostname:5000/video_feed)
            model_name: YOLO model to use (yolo11n-pose.pt, yolo11s-pose.pt, etc.)
        """
        self.source_url = source_url
        self.model_name = model_name
        self.model = None
        
        # Frame storage
        self.annotated_frame = None
        self.frame_lock = threading.Lock()
        
        # Detection results storage
        self.latest_results = None
        self.results_lock = threading.Lock()
        self.results_history = deque(maxlen=100)  # Keep last 100 results
        
        # Processing state
        self.running = False
        self.processing_thread = None
        self.fps = 0
        self.frame_count = 0
        self.last_fps_update = time.time()
        
        # Performance metrics
        self.inference_time = 0
        self.total_inference_time = 0
        self.total_frames_processed = 0
        
    def initialize_model(self):
        """Load YOLO model"""
        try:
            logger.info(f"Loading YOLO model: {self.model_name}")
            self.model = YOLO(self.model_name)
            
            # Verify CUDA is available
            
            if torch.cuda.is_available():
                logger.info(f"CUDA available - GPU: {torch.cuda.get_device_name(0)}")
                logger.info(f"CUDA version: {torch.version.cuda}")
            else:
                logger.warning("⚠ CUDA not available, using CPU (will be slow)")
            
            logger.info("Model loaded successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to load model: {e}")
            return False
    
    def start_processing(self):
        """Start video processing in separate thread"""
        if not self.initialize_model():
            return False
        
        self.running = True
        self.processing_thread = threading.Thread(target=self._process_stream)
        self.processing_thread.daemon = True
        self.processing_thread.start()
        
        logger.info(f"Started processing stream from {self.source_url}")
        return True
    
    def _process_stream(self):
        """Main processing loop - runs YOLO on video stream"""
        logger.info("Processing thread started")
        
        try:
            # Run inference on the stream
            # stream=True returns a generator for efficient processing
            results_generator = self.model(
                self.source_url,
                stream=True,
                verbose=False,
                device=0  # Use GPU 0 (your 4070)
            )
            
            for result in results_generator:
                if not self.running:
                    break
                
                start_time = time.time()
                
                # Get annotated frame with pose keypoints drawn
                annotated_frame = result.plot()
                
                # Extract detection data
                detection_data = self._extract_detections(result)
                
                # Update stored frame and results
                with self.frame_lock:
                    self.annotated_frame = annotated_frame.copy()
                
                with self.results_lock:
                    self.latest_results = detection_data
                    self.results_history.append({
                        'timestamp': datetime.now().isoformat(),
                        'detections': detection_data
                    })
                
                # Update performance metrics
                self.inference_time = time.time() - start_time
                self.total_inference_time += self.inference_time
                self.total_frames_processed += 1
                
                # Update FPS counter
                self.frame_count += 1
                if time.time() - self.last_fps_update >= 1.0:
                    self.fps = self.frame_count
                    self.frame_count = 0
                    self.last_fps_update = time.time()
                    
                    avg_inference = self.total_inference_time / self.total_frames_processed
                    logger.info(f"FPS: {self.fps} | Inference: {avg_inference*1000:.1f}ms")
        
        except Exception as e:
            logger.error(f"Error in processing stream: {e}")
            logger.exception(e)
        finally:
            logger.info("Processing thread stopped")
    
    def _extract_detections(self, result):
        """
        Extract pose detection data from YOLO result
        
        Returns structured detection data with bounding boxes and keypoints
        For custom car dataset: 2 keypoints with flip_idx [1, 0]
        """
        detections = []
        
        # Check if pose keypoints are available
        if result.keypoints is None or len(result.keypoints) == 0:
            return detections
        
        # Get boxes and keypoints
        boxes = result.boxes
        keypoints = result.keypoints
        
        for i in range(len(boxes)):
            detection = {}
            
            # Bounding box
            box = boxes[i]
            xyxy = box.xyxy[0].cpu().numpy()  # x1, y1, x2, y2
            detection['bbox'] = {
                'x1': float(xyxy[0]),
                'y1': float(xyxy[1]),
                'x2': float(xyxy[2]),
                'y2': float(xyxy[3]),
                'confidence': float(box.conf[0])
            }
            
            # Class information
            detection['class'] = 'Car'
            detection['class_id'] = int(box.cls[0])
            
            # Pose keypoints
            # Custom dataset has 2 keypoints: typically front and back of car
            kpts = keypoints[i].xy[0].cpu().numpy()  # Shape: (2, 2)
            kpts_conf = keypoints[i].conf[0].cpu().numpy()  # Shape: (2,)
            
            # Based on your dataset, these would be the two key points of the car
            keypoint_names = ['keypoint_0', 'keypoint_1']  # You can rename these based on what they represent
            # For example: ['front', 'back'] or ['left', 'right']
            
            pose_keypoints = []
            for j, name in enumerate(keypoint_names):
                if j < len(kpts):
                    pose_keypoints.append({
                        'name': name,
                        'x': float(kpts[j][0]),
                        'y': float(kpts[j][1]),
                        'confidence': float(kpts_conf[j])
                    })
            
            detection['keypoints'] = pose_keypoints
            detection['car_id'] = i  # Simple ID based on detection order
            
            detections.append(detection)
        
        return detections
    
    def get_annotated_frame(self):
        """Get latest annotated frame with pose overlay"""
        with self.frame_lock:
            return self.annotated_frame.copy() if self.annotated_frame is not None else None
    
    def get_latest_results(self):
        """Get latest detection results"""
        with self.results_lock:
            return self.latest_results
    
    def get_results_history(self):
        """Get history of detection results"""
        with self.results_lock:
            return list(self.results_history)
    
    def get_stats(self):
        """Get processing statistics"""
        avg_inference = (self.total_inference_time / self.total_frames_processed 
                        if self.total_frames_processed > 0 else 0)
        
        return {
            'fps': self.fps,
            'total_frames_processed': self.total_frames_processed,
            'average_inference_ms': avg_inference * 1000,
            'latest_inference_ms': self.inference_time * 1000,
            'running': self.running
        }
    
    def stop(self):
        """Stop processing"""
        logger.info("Stopping processor...")
        self.running = False
        if self.processing_thread:
            self.processing_thread.join(timeout=5)
        logger.info("Processor stopped")


# Global processor instance
processor = None


def generate_mjpeg_stream(get_frame_func):
    """
    Generate MJPEG stream from frame getter function
    
    Args:
        get_frame_func: Function that returns a frame (numpy array)
    """
    while True:
        frame = get_frame_func()
        if frame is not None:
            # Encode as JPEG
            ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
            if ret:
                frame_bytes = buffer.tobytes()
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
        time.sleep(1/30)  # ~30 FPS


@app.route('/')
def index():
    """API information endpoint"""
    return jsonify({
        'service': 'YOLO Pose Detection Server - Custom Car Model',
        'status': 'running' if processor and processor.running else 'stopped',
        'model_info': {
            'keypoints': 2,
            'classes': ['Car']
        },
        'endpoints': {
            'annotated_stream': '/video_feed',
            'detections': '/detections',
            'detections_history': '/detections/history',
            'single_frame': '/frame',
            'stats': '/stats',
            'health': '/health'
        }
    })


@app.route('/health')
def health():
    """Health check endpoint"""
    if processor and processor.running:
        return jsonify({
            'status': 'healthy',
            'processor_running': True
        }), 200
    else:
        return jsonify({
            'status': 'unhealthy',
            'processor_running': False
        }), 503


@app.route('/stats')
def stats():
    """Statistics endpoint"""
    if processor:
        return jsonify(processor.get_stats())
    return jsonify({'error': 'Processor not initialized'}), 500


@app.route('/video_feed')
def video_feed():
    """
    Video streaming endpoint - returns MJPEG stream with pose annotations
    """
    if not processor or not processor.running:
        return jsonify({'error': 'Processor not running'}), 503
    
    return Response(
        generate_mjpeg_stream(processor.get_annotated_frame),
        mimetype='multipart/x-mixed-replace; boundary=frame'
    )


@app.route('/frame')
def get_single_frame():
    """Get a single annotated frame as JPEG"""
    if not processor or not processor.running:
        return jsonify({'error': 'Processor not running'}), 503
    
    frame = processor.get_annotated_frame()
    if frame is not None:
        ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        if ret:
            return Response(buffer.tobytes(), mimetype='image/jpeg')
    
    return jsonify({'error': 'No frame available'}), 500


@app.route('/detections')
def get_detections():
    """
    Get latest pose detection results
    
    Returns JSON with bounding boxes and keypoints for all detected persons
    """
    if not processor or not processor.running:
        return jsonify({'error': 'Processor not running'}), 503
    
    results = processor.get_latest_results()
    stats = processor.get_stats()
    
    return jsonify({
        'timestamp': datetime.now().isoformat(),
        'detections': results if results else [],
        'num_detections': len(results) if results else 0,
        'fps': stats['fps'],
        'inference_ms': stats['latest_inference_ms']
    })


@app.route('/detections/history')
def get_detections_history():
    """
    Get historical pose detection results
    
    Query params:
        limit: Maximum number of results to return (default: 100)
    """
    if not processor or not processor.running:
        return jsonify({'error': 'Processor not running'}), 503
    
    limit = request.args.get('limit', default=100, type=int)
    history = processor.get_results_history()
    
    return jsonify({
        'history': history[-limit:],
        'count': len(history[-limit:])
    })


def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description='YOLO Pose Detection Server')
    parser.add_argument(
        '--source',
        type=str,
        required=True,
        help='Video source URL (e.g., http://raspberry-pi:5000/video_feed)'
    )
    parser.add_argument(
        '--model',
        type=str,
        default='best.pt',
        help='YOLO model to use (default: best.pt for custom trained model)'
    )
    parser.add_argument(
        '--host',
        type=str,
        default='0.0.0.0',
        help='Host to bind to (default: 0.0.0.0)'
    )
    parser.add_argument(
        '--port',
        type=int,
        default=5001,
        help='Port to bind to (default: 5001)'
    )
    
    args = parser.parse_args()
    
    global processor
    
    try:
        logger.info("="*60)
        logger.info("YOLO Pose Detection Server - ESP32 Car Model")
        logger.info("="*60)
        logger.info(f"Source: {args.source}")
        logger.info(f"Model: {args.model}")
        logger.info(f"Server: {args.host}:{args.port}")
        logger.info("="*60)
        
        # Initialize processor
        processor = YOLOPoseProcessor(
            source_url=args.source,
            model_name=args.model
        )
        
        # Start processing
        if not processor.start_processing():
            logger.error("Failed to start processor")
            return 1
        
        logger.info("Processor started successfully")
        logger.info("\nEndpoints:")
        logger.info(f"  - Annotated stream: http://{args.host}:{args.port}/video_feed")
        logger.info(f"  - Detections:       http://{args.host}:{args.port}/detections")
        logger.info(f"  - Stats:            http://{args.host}:{args.port}/stats")
        logger.info("")
        
        # Run Flask server
        app.run(host=args.host, port=args.port, debug=False, threaded=True)
        
    except KeyboardInterrupt:
        logger.info("\nShutting down...")
    except Exception as e:
        logger.error(f"Error: {e}")
        logger.exception(e)
        return 1
    finally:
        if processor:
            processor.stop()
    
    return 0


if __name__ == '__main__':
    exit(main())