"""Quick pipeline test script."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ai.pipeline import SurveillancePipeline
import cv2

print("Loading AI pipeline...")
pipe = SurveillancePipeline()
print(f"Pipeline ready: {pipe.is_ready}")
print(f"Detector device: {pipe.detector.device}")

# Test with demo video
cap = cv2.VideoCapture("data/videos/demo_normal.mp4")
ret, frame = cap.read()

if ret:
    # Process a few frames to build up temporal data
    for i in range(5):
        ret2, f2 = cap.read()
        if ret2:
            result = pipe.process_frame(f2)
    
    result = pipe.process_frame(frame)
    print(f"\nResults:")
    print(f"  Detections: {result['object_count']}")
    print(f"  People: {result['person_count']}")
    print(f"  Threat score: {result['threat_score']:.1f}")
    print(f"  Threat level: {result['threat_level']}")
    print(f"  Violence score: {result['violence_score']:.1f}")
    print(f"  Pipeline FPS: {result['pipeline_fps']:.1f}")
    print(f"  Inference ms: {result['inference_time_ms']:.1f}")
    print(f"\nPipeline test PASSED!")
else:
    print("Could not read demo video")

cap.release()
