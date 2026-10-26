"""
Event Manager
==============
Manages event logging and history for the surveillance system.
"""

import time
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class EventManager:
    """
    Manages surveillance event logging and querying.
    
    Events are logged periodically (not every frame) to avoid
    overwhelming the database with thousands of identical entries.
    """
    
    def __init__(self, db, log_interval=5.0):
        """
        Initialize event manager.
        
        Args:
            db: Database instance
            log_interval: Minimum seconds between event logs
        """
        self.db = db
        self.log_interval = log_interval
        self.last_log_time = 0
        self.total_logged = 0
    
    def log_event(self, analysis_result, source_name="unknown", force=False):
        """
        Log a detection event if the interval has elapsed.
        
        Events at SUSPICIOUS or higher are logged more frequently.
        
        Args:
            analysis_result: Pipeline analysis result
            source_name: Video source name
            force: Force logging regardless of interval
        """
        current_time = time.time()
        threat_level = analysis_result.get("threat_level", "NORMAL")
        
        # Determine logging interval based on severity
        if threat_level in ("HIGH_RISK", "CRITICAL"):
            interval = max(1.0, self.log_interval / 3)
        elif threat_level == "SUSPICIOUS":
            interval = max(2.0, self.log_interval / 2)
        else:
            interval = self.log_interval
        
        if not force and (current_time - self.last_log_time) < interval:
            return None
        
        # Create event data
        event_data = {
            "timestamp": float(current_time),
            "event_type": str(self._determine_event_type(analysis_result)),
            "threat_score": float(analysis_result.get("threat_score", 0)),
            "severity": str(threat_level),
            "confidence": float(self._avg_confidence(analysis_result)),
            "source": str(source_name),
            "person_count": int(analysis_result.get("person_count", 0)),
            "object_count": int(analysis_result.get("object_count", 0)),
            "weapon_detected": bool(analysis_result.get("weapon_detected", False)),
            "violence_score": float(analysis_result.get("violence_score", 0)),
            "crowd_anomaly": float(analysis_result.get("crowd_anomaly_score", 0)),
            "persistence_score": float(analysis_result.get("persistence_score", 0)),
            "details": {
                "violence_probability": float(analysis_result.get("violence_probability", 0)),
                "crowd_density": str(analysis_result.get("crowd_density", "MINIMAL")),
                "is_persistent": bool(analysis_result.get("is_persistent", False)),
            },
        }
        
        event_id = self.db.save_event(event_data)
        self.last_log_time = current_time
        self.total_logged += 1
        
        return event_id
    
    def log_analytics(self, analysis_result):
        """Log performance analytics data."""
        analytics_data = {
            "fps": analysis_result.get("pipeline_fps", 0),
            "inference_ms": analysis_result.get("inference_time_ms", 0),
            "pipeline_ms": analysis_result.get("pipeline_time_ms", 0),
            "threat_score": analysis_result.get("threat_score", 0),
            "person_count": analysis_result.get("person_count", 0),
            "detection_count": analysis_result.get("object_count", 0),
        }
        self.db.save_analytics(analytics_data)
    
    def _determine_event_type(self, analysis):
        """Determine event type from analysis."""
        if analysis.get("weapon_detected"):
            return "weapon_detection"
        elif analysis.get("violence_score", 0) > 50:
            return "violence_detected"
        elif analysis.get("crowd_anomaly_score", 0) > 40:
            return "crowd_anomaly"
        elif analysis.get("threat_level") in ("HIGH_RISK", "CRITICAL"):
            return "high_threat"
        elif analysis.get("threat_level") == "SUSPICIOUS":
            return "suspicious_activity"
        else:
            return "routine_scan"
    
    def _avg_confidence(self, analysis):
        """Calculate average detection confidence."""
        detections = analysis.get("detection", {}).get("detections", [])
        if not detections:
            return 0
        confs = [d["confidence"] for d in detections]
        return round(sum(confs) / len(confs), 3)
    
    def get_events(self, **kwargs):
        """Get events with filters."""
        return self.db.get_events(**kwargs)
    
    def get_statistics(self):
        """Get event statistics."""
        return self.db.get_statistics()
