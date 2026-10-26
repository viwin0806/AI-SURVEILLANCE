"""
YOLO Object Detection Module
=============================
Wraps the Ultralytics YOLOv8 model for real-time object detection.
Provides bounding boxes, labels, confidence scores, and person counting.

This module handles:
- Model loading with GPU/CPU fallback
- Inference on individual frames
- Result parsing and formatting
- FPS and latency tracking
"""

import time
import logging
import numpy as np

logger = logging.getLogger(__name__)


class ObjectDetector:
    """
    YOLO-based object detector for surveillance applications.
    
    Uses YOLOv8n (nano) by default for fast inference on moderate hardware.
    Automatically selects GPU if available, falls back to CPU.
    """
    
    def __init__(self, model_path="yolov8n.pt", confidence=0.35, 
                 iou_threshold=0.45, device="auto", img_size=640):
        """
        Initialize the YOLO detector.
        
        Args:
            model_path: Path to YOLO model weights (auto-downloads if not present)
            confidence: Minimum confidence threshold for detections
            iou_threshold: NMS IoU threshold
            device: "auto", "cuda", "cpu"
            img_size: Inference image size
        """
        self.model_path = model_path
        self.confidence = confidence
        self.iou_threshold = iou_threshold
        self.img_size = img_size
        self.device = device
        self.model = None
        self.is_loaded = False
        self.load_error = None
        
        # Performance tracking
        self.last_inference_time = 0
        self.fps = 0
        self.frame_count = 0
        self.total_inference_time = 0
        
        self._load_model()
    
    def _load_model(self):
        """Load the YOLO model with error handling and device selection."""
        try:
            from ultralytics import YOLO
            import torch
            
            # Determine device
            if self.device == "auto":
                if torch.cuda.is_available():
                    self.device = "cuda"
                    logger.info(f"CUDA available: {torch.cuda.get_device_name(0)}")
                else:
                    self.device = "cpu"
                    logger.info("CUDA not available, using CPU")
            
            logger.info(f"Loading YOLO model: {self.model_path} on {self.device}")
            self.model = YOLO(self.model_path)
            
            # Warm up the model with a dummy inference
            dummy = np.zeros((640, 640, 3), dtype=np.uint8)
            self.model.predict(dummy, verbose=False, device=self.device)
            
            self.is_loaded = True
            logger.info("YOLO model loaded successfully")
            
        except Exception as e:
            self.load_error = str(e)
            self.is_loaded = False
            logger.error(f"Failed to load YOLO model: {e}")
    
    def detect(self, frame):
        """
        Run object detection on a single frame.
        
        Args:
            frame: BGR image as numpy array (OpenCV format)
            
        Returns:
            dict with detection results:
            {
                "detections": [
                    {
                        "bbox": [x1, y1, x2, y2],
                        "label": "person",
                        "class_id": 0,
                        "confidence": 0.92,
                    }, ...
                ],
                "person_count": int,
                "object_count": int,
                "inference_time_ms": float,
                "fps": float,
            }
        """
        if not self.is_loaded or frame is None:
            return self._empty_result()
        
        try:
            start_time = time.time()
            
            # Run YOLO inference
            results = self.model.predict(
                frame,
                conf=self.confidence,
                iou=self.iou_threshold,
                imgsz=self.img_size,
                device=self.device,
                verbose=False,
                classes=None,  # Detect all classes
            )
            
            inference_time = time.time() - start_time
            self.last_inference_time = inference_time
            self.frame_count += 1
            self.total_inference_time += inference_time
            self.fps = 1.0 / inference_time if inference_time > 0 else 0
            
            # Parse results
            detections = []
            person_count = 0
            
            if results and len(results) > 0:
                result = results[0]
                if result.boxes is not None:
                    for box in result.boxes:
                        x1, y1, x2, y2 = box.xyxy[0].cpu().numpy().astype(int)
                        conf = float(box.conf[0].cpu().numpy())
                        cls_id = int(box.cls[0].cpu().numpy())
                        label = result.names.get(cls_id, f"class_{cls_id}")
                        
                        detection = {
                            "bbox": [int(x1), int(y1), int(x2), int(y2)],
                            "label": label,
                            "class_id": cls_id,
                            "confidence": round(conf, 3),
                        }
                        detections.append(detection)
                        
                        if cls_id == 0:  # person class
                            person_count += 1
            
            return {
                "detections": detections,
                "person_count": person_count,
                "object_count": len(detections),
                "inference_time_ms": round(inference_time * 1000, 1),
                "fps": round(self.fps, 1),
            }
            
        except Exception as e:
            logger.error(f"Detection error: {e}")
            return self._empty_result()
    
    def _empty_result(self):
        """Return empty detection result."""
        return {
            "detections": [],
            "person_count": 0,
            "object_count": 0,
            "inference_time_ms": 0,
            "fps": 0,
        }
    
    def update_confidence(self, confidence):
        """Update confidence threshold at runtime."""
        self.confidence = max(0.1, min(0.95, confidence))
    
    def get_status(self):
        """Get detector status for dashboard display."""
        return {
            "model": self.model_path,
            "loaded": self.is_loaded,
            "device": self.device,
            "confidence": self.confidence,
            "error": self.load_error,
            "avg_inference_ms": round(
                (self.total_inference_time / self.frame_count * 1000) 
                if self.frame_count > 0 else 0, 1
            ),
            "total_frames": self.frame_count,
        }
    
    def draw_detections(self, frame, detections, threat_level="NORMAL"):
        """
        Draw bounding boxes and labels on frame.
        
        Args:
            frame: BGR image
            detections: list of detection dicts from detect()
            threat_level: Current threat level for color coding
            
        Returns:
            Annotated frame
        """
        import cv2
        
        annotated = frame.copy()
        
        # Color scheme based on detection type
        colors = {
            "person": (0, 200, 0),       # Green
            "knife": (0, 0, 255),         # Red - weapon
            "car": (200, 150, 0),         # Teal
            "motorcycle": (200, 150, 0),
            "bus": (200, 150, 0),
            "truck": (200, 150, 0),
            "backpack": (180, 120, 0),
            "handbag": (180, 120, 0),
            "suitcase": (180, 120, 0),
            "default": (200, 200, 0),     # Cyan
        }
        
        for det in detections:
            x1, y1, x2, y2 = det["bbox"]
            label = det["label"]
            conf = det["confidence"]
            
            # Select color
            if label in ["knife"]:
                color = (0, 0, 255)  # Red for weapons
            elif label == "person":
                color = (0, 200, 0)  # Green for people
            else:
                color = colors.get(label, colors["default"])
            
            # Draw bounding box
            cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)
            
            # Draw label background
            text = f"{label} {conf:.0%}"
            (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
            cv2.rectangle(annotated, (x1, y1 - th - 8), (x1 + tw + 4, y1), color, -1)
            cv2.putText(annotated, text, (x1 + 2, y1 - 4),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        
        return annotated
