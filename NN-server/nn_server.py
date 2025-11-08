from ultralytics import YOLO


# Load a pretrained YOLO11n model
model = YOLO("yolo11n.pt")

# Single stream with batch-size 1 inference
source = "rtsp://example.com/media.mp4"  # RTSP, RTMP, TCP, or IP streaming address

# Run inference on the source
results = model(source, stream=True)  # generator of Results objects



