"""
AI Pipeline Orchestrator
=========================
Orchestrates all AI modules in the correct sequence for each video frame.

Pipeline Flow:
  Frame → YOLO Detection → Weapon Detection → Violence Analysis
  → Crowd Analysis → Temporal Persistence → Threat Scoring → Result

Each module is independent and can be replaced/upgraded individually.
"""

import time
import logging
import cv2
import numpy as np

from ai.detector import ObjectDetector
from ai.weapon_detector import WeaponDetector
from ai.violence_detector import ViolenceDetector
from ai.crowd_analyzer import CrowdAnalyzer
from ai.temporal_engine import TemporalEngine
from ai.threat_scorer import ThreatScorer

def sanitize_json(obj):
    """Recursively convert numpy types to native Python types for JSON serialization."""
    if isinstance(obj, dict):
        return {str(k): sanitize_json(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [sanitize_json(v) for v in obj]
    elif isinstance(obj, (np.bool_,)):
        return bool(obj)
    elif isinstance(obj, (np.floating,)):
        return float(obj)
    elif isinstance(obj, (np.integer,)):
        return int(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    return obj

logger = logging.getLogger(__name__)


class SurveillancePipeline:
    """
    Main AI processing pipeline for the surveillance system.
    
    Coordinates all detection and analysis modules, processes video frames,
    and produces unified threat assessments.
    """
    
    def __init__(self, config=None):
        """
        Initialize all AI modules.
        
        Args:
            config: Optional config module (uses defaults if None)
        """
        if config is None:
            import config as cfg
            config = cfg
        
        self.config = config
        
        logger.info("Initializing AI Surveillance Pipeline...")
        
        # Initialize modules
        self.detector = ObjectDetector(
            model_path=config.YOLO_MODEL,
            confidence=config.YOLO_CONFIDENCE,
            iou_threshold=config.YOLO_IOU,
            device=config.YOLO_DEVICE,
            img_size=config.YOLO_IMG_SIZE,
        )
        
        self.weapon_detector = WeaponDetector(
            custom_model_path=config.WEAPON_MODEL_PATH,
            confidence_threshold=config.WEAPON_CONFIDENCE_THRESHOLD,
        )
        
        self.violence_detector = ViolenceDetector(
            buffer_size=config.VIOLENCE_FRAME_BUFFER,
            flow_threshold=config.VIOLENCE_FLOW_THRESHOLD,
            intensity_high=config.VIOLENCE_INTENSITY_HIGH,
            area_threshold=config.VIOLENCE_AREA_THRESHOLD,
            direction_variance_threshold=config.VIOLENCE_DIRECTION_VARIANCE,
            score_decay=config.VIOLENCE_SCORE_DECAY,
        )
        
        self.crowd_analyzer = CrowdAnalyzer(
            density_low=config.CROWD_DENSITY_LOW,
            density_medium=config.CROWD_DENSITY_MEDIUM,
            density_high=config.CROWD_DENSITY_HIGH,
        )
        
        self.temporal_engine = TemporalEngine(
            window_size=config.TEMPORAL_WINDOW_SIZE,
            confirm_frames=config.PERSISTENCE_CONFIRM_FRAMES,
            decay_rate=config.PERSISTENCE_DECAY_RATE,
            min_score=config.PERSISTENCE_MIN_SCORE,
        )
        
        self.threat_scorer = ThreatScorer(
            weights=dict(config.THREAT_WEIGHTS),
            levels=dict(config.THREAT_LEVELS),
        )
        
        # Performance metrics
        self.total_frames = 0
        self.total_pipeline_time = 0
        self.pipeline_fps = 0
        
        self.is_ready = self.detector.is_loaded
        logger.info(f"Pipeline initialized. Detector ready: {self.is_ready}")
    
    def process_frame(self, frame):
        """
        Process a single video frame through the complete AI pipeline.
        
        Args:
            frame: BGR image (numpy array)
            
        Returns:
            dict with complete analysis results including annotated frame
        """
        if frame is None:
            return self._empty_result()
        
        pipeline_start = time.time()
        
        # ── Stage 1: YOLO Object Detection ──────────────────────
        detection_result = self.detector.detect(frame)
        detections = detection_result.get("detections", [])
        
        # ── Stage 2: Weapon Detection ───────────────────────────
        weapon_result = self.weapon_detector.analyze(detections, frame)
        
        # ── Stage 3: Violence / Motion Analysis ─────────────────
        violence_result = self.violence_detector.analyze(frame)
        
        # ── Stage 4: Crowd Analysis ─────────────────────────────
        crowd_result = self.crowd_analyzer.analyze(detections, frame.shape)
        
        # ── Stage 5: Pre-calculate raw threat score for temporal ─
        # Quick preliminary score for the temporal engine
        raw_threat = (
            weapon_result.get("weapon_score", 0) * 0.3 +
            violence_result.get("violence_score", 0) * 0.3 +
            crowd_result.get("anomaly_score", 0) * 0.2 +
            violence_result.get("motion_intensity", 0) * 0.2
        )
        
        # ── Stage 6: Temporal Persistence ───────────────────────
        temporal_input = {
            "weapon_score": weapon_result.get("weapon_score", 0),
            "violence_score": violence_result.get("violence_score", 0),
            "crowd_anomaly_score": crowd_result.get("anomaly_score", 0),
            "raw_threat_score": raw_threat,
        }
        temporal_result = self.temporal_engine.update(temporal_input)
        
        # ── Stage 7: Final Threat Scoring ───────────────────────
        threat_result = self.threat_scorer.calculate(
            weapon_result=weapon_result,
            violence_result=violence_result,
            crowd_result=crowd_result,
            temporal_result=temporal_result,
            detection_result=detection_result,
        )
        
        # ── Draw Annotations ────────────────────────────────────
        annotated_frame = self.detector.draw_detections(
            frame, detections, threat_result.get("threat_level", "NORMAL")
        )
        
        # Draw threat level overlay
        annotated_frame = self._draw_threat_overlay(
            annotated_frame, threat_result
        )
        
        # Performance tracking
        pipeline_time = time.time() - pipeline_start
        self.total_frames += 1
        self.total_pipeline_time += pipeline_time
        self.pipeline_fps = 1.0 / pipeline_time if pipeline_time > 0 else 0
        
        # ── Assemble Complete Result ────────────────────────────
        result = {
            "frame_number": self.total_frames,
            "timestamp": time.time(),
            
            # Detection results
            "detection": detection_result,
            "person_count": detection_result.get("person_count", 0),
            "object_count": detection_result.get("object_count", 0),
            
            # Weapon analysis
            "weapon": weapon_result,
            "weapon_detected": weapon_result.get("weapon_detected", False),
            "weapon_score": weapon_result.get("weapon_score", 0),
            
            # Violence analysis
            "violence": violence_result,
            "violence_score": violence_result.get("violence_score", 0),
            "violence_probability": violence_result.get("violence_probability", 0),
            
            # Crowd analysis
            "crowd": crowd_result,
            "crowd_density": crowd_result.get("crowd_density", "MINIMAL"),
            "crowd_anomaly_score": crowd_result.get("anomaly_score", 0),
            
            # Temporal persistence
            "temporal": temporal_result,
            "persistence_score": temporal_result.get("persistence_score", 0),
            "is_persistent": temporal_result.get("is_persistent", False),
            
            # Threat assessment
            "threat": threat_result,
            "threat_score": threat_result.get("threat_score", 0),
            "threat_level": threat_result.get("threat_level", "NORMAL"),
            
            # Performance
            "pipeline_time_ms": round(pipeline_time * 1000, 1),
            "pipeline_fps": round(self.pipeline_fps, 1),
            "inference_time_ms": detection_result.get("inference_time_ms", 0),
            
            # Annotated frame (for streaming)
            "annotated_frame": annotated_frame,
        }
        
        # Ensure all fields are JSON-serializable
        raw_ann = result.pop("annotated_frame", None)
        sanitized = sanitize_json(result)
        sanitized["annotated_frame"] = raw_ann
        return sanitized
    
    def _draw_threat_overlay(self, frame, threat_result):
        """Draw threat level indicator on frame."""
        h, w = frame.shape[:2]
        level = threat_result.get("threat_level", "NORMAL")
        score = threat_result.get("threat_score", 0)
        
        # Color based on threat level
        colors = {
            "NORMAL":     (34, 197, 94),    # Green (BGR)
            "SUSPICIOUS": (8, 179, 234),     # Yellow (BGR)
            "HIGH_RISK":  (22, 115, 249),    # Orange (BGR)
            "CRITICAL":   (68, 68, 239),     # Red (BGR)
        }
        color = colors.get(level, (200, 200, 200))
        
        # Draw threat bar at top
        bar_height = 35
        overlay = frame.copy()
        cv2.rectangle(overlay, (0, 0), (w, bar_height), (0, 0, 0), -1)
        frame = cv2.addWeighted(overlay, 0.7, frame, 0.3, 0)
        
        # Threat text
        text = f"THREAT: {level} ({score:.0f}/100)"
        cv2.putText(frame, text, (10, 25), cv2.FONT_HERSHEY_SIMPLEX,
                   0.7, color, 2)
        
        # Score bar
        bar_w = int((w - 20) * (score / 100.0))
        cv2.rectangle(frame, (10, bar_height), (10 + bar_w, bar_height + 4), color, -1)
        
        # FPS counter at top right
        fps_text = f"FPS: {self.pipeline_fps:.0f}"
        (tw, _), _ = cv2.getTextSize(fps_text, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
        cv2.putText(frame, fps_text, (w - tw - 10, 25),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
        
        return frame
    
    def _empty_result(self):
        """Return empty pipeline result."""
        return {
            "frame_number": self.total_frames,
            "timestamp": time.time(),
            "detection": {"detections": [], "person_count": 0, "object_count": 0,
                         "inference_time_ms": 0, "fps": 0},
            "person_count": 0, "object_count": 0,
            "weapon": {"weapon_detected": False, "weapon_score": 0, "weapons": []},
            "weapon_detected": False, "weapon_score": 0,
            "violence": {"violence_score": 0, "violence_probability": 0,
                        "motion_intensity": 0, "is_violent": False},
            "violence_score": 0, "violence_probability": 0,
            "crowd": {"person_count": 0, "crowd_density": "MINIMAL",
                     "anomaly_score": 0},
            "crowd_density": "MINIMAL", "crowd_anomaly_score": 0,
            "temporal": {"persistence_score": 0, "is_persistent": False},
            "persistence_score": 0, "is_persistent": False,
            "threat": {"threat_score": 0, "threat_level": "NORMAL"},
            "threat_score": 0, "threat_level": "NORMAL",
            "pipeline_time_ms": 0, "pipeline_fps": 0, "inference_time_ms": 0,
            "annotated_frame": None,
        }
    
    def reset(self):
        """Reset all module states (for new video)."""
        self.violence_detector.reset()
        self.crowd_analyzer.reset()
        self.temporal_engine.reset()
        self.total_frames = 0
        self.total_pipeline_time = 0
        logger.info("Pipeline reset for new video source")
    
    def get_status(self):
        """Get pipeline status for dashboard."""
        return {
            "pipeline_ready": self.is_ready,
            "detector": self.detector.get_status(),
            "weapon_detector": self.weapon_detector.get_status(),
            "violence_detector": self.violence_detector.get_status(),
            "crowd_analyzer": self.crowd_analyzer.get_status(),
            "temporal_engine": self.temporal_engine.get_persistence_status(),
            "threat_scorer": self.threat_scorer.get_stats(),
            "total_frames": self.total_frames,
            "avg_pipeline_ms": round(
                (self.total_pipeline_time / self.total_frames * 1000)
                if self.total_frames > 0 else 0, 1
            ),
        }
    
    def update_settings(self, settings):
        """Update pipeline settings at runtime."""
        if "yolo_confidence" in settings:
            self.detector.update_confidence(settings["yolo_confidence"])
        if "threat_weights" in settings:
            self.threat_scorer.update_weights(settings["threat_weights"])
        if "threat_levels" in settings:
            self.threat_scorer.update_levels(settings["threat_levels"])
        logger.info("Pipeline settings updated")
