"""
Alert Manager
==============
Generates, manages, and deduplicates threat alerts.

Alerts are triggered when the threat level reaches HIGH_RISK or above.
Each alert captures a screenshot and stores detailed information.
"""

import os
import time
import cv2
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class AlertManager:
    """
    Manages threat alert generation and deduplication.
    
    Features:
    - Alert generation on HIGH_RISK/CRITICAL threat levels
    - Screenshot capture on alert
    - Rate limiting to prevent alert spam
    - Deduplication of similar alerts
    - Database persistence
    """
    
    def __init__(self, db, snapshot_dir="data/snapshots",
                 max_per_minute=5, dedup_seconds=15):
        """
        Initialize alert manager.
        
        Args:
            db: Database instance
            snapshot_dir: Directory for alert screenshots
            max_per_minute: Maximum alerts per minute
            dedup_seconds: Ignore duplicate alerts within this window
        """
        self.db = db
        self.snapshot_dir = snapshot_dir
        self.max_per_minute = max_per_minute
        self.dedup_seconds = dedup_seconds
        
        os.makedirs(snapshot_dir, exist_ok=True)
        
        # Alert tracking
        self.recent_alerts = []  # [(timestamp, threat_level), ...]
        self.last_alert_time = 0
        self.last_alert_level = None
        self.total_alerts = 0
        
        # Callbacks for real-time notification
        self.on_alert_callbacks = []
    
    def check_and_alert(self, analysis_result, frame=None, source_name="unknown"):
        """
        Check if an alert should be generated based on analysis results.
        
        Args:
            analysis_result: Complete pipeline analysis result
            frame: Current video frame (for screenshot)
            source_name: Name of the video source
            
        Returns:
            alert dict if alert was generated, None otherwise
        """
        threat_level = analysis_result.get("threat_level", "NORMAL")
        threat_score = analysis_result.get("threat_score", 0)
        
        # Only alert on HIGH_RISK or CRITICAL
        if threat_level not in ("HIGH_RISK", "CRITICAL"):
            return None
        
        # Rate limiting
        current_time = time.time()
        self._clean_recent_alerts(current_time)
        
        if len(self.recent_alerts) >= self.max_per_minute:
            return None
        
        # Deduplication — don't repeat same level alert too quickly
        if (current_time - self.last_alert_time < self.dedup_seconds and 
            self.last_alert_level == threat_level):
            return None
        
        # Generate alert
        alert = self._create_alert(
            analysis_result, frame, source_name, current_time
        )
        
        # Save to database
        alert_id = self.db.save_alert(alert)
        alert["id"] = alert_id
        
        # Also save as event
        event_data = {
            "timestamp": current_time,
            "event_type": "alert",
            "threat_score": threat_score,
            "severity": threat_level,
            "confidence": analysis_result.get("violence_probability", 0),
            "source": source_name,
            "person_count": analysis_result.get("person_count", 0),
            "object_count": analysis_result.get("object_count", 0),
            "weapon_detected": analysis_result.get("weapon_detected", False),
            "violence_score": analysis_result.get("violence_score", 0),
            "crowd_anomaly": analysis_result.get("crowd_anomaly_score", 0),
            "persistence_score": analysis_result.get("persistence_score", 0),
            "snapshot_path": alert.get("snapshot_path", ""),
            "details": {
                "threat_level": threat_level,
                "reason": alert.get("reason", ""),
            },
        }
        self.db.save_event(event_data)
        
        # Track alert
        self.recent_alerts.append((current_time, threat_level))
        self.last_alert_time = current_time
        self.last_alert_level = threat_level
        self.total_alerts += 1
        
        # Fire callbacks
        for callback in self.on_alert_callbacks:
            try:
                callback(alert)
            except Exception as e:
                logger.error(f"Alert callback error: {e}")
        
        logger.warning(
            f"ALERT [{threat_level}]: Score={threat_score:.0f}, "
            f"Reason={alert.get('reason', 'N/A')}"
        )
        
        return alert
    
    def _create_alert(self, analysis, frame, source_name, timestamp):
        """Create an alert dict from analysis results."""
        # Capture screenshot
        snapshot_path = ""
        if frame is not None:
            snapshot_filename = f"alert_{int(timestamp)}_{analysis.get('threat_level', 'UNK')}.jpg"
            snapshot_path = os.path.join(self.snapshot_dir, snapshot_filename)
            try:
                cv2.imwrite(snapshot_path, frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
            except Exception as e:
                logger.error(f"Failed to save snapshot: {e}")
                snapshot_path = ""
        
        # Build detected objects list
        detections = analysis.get("detection", {}).get("detections", [])
        detected_objects = [
            {"label": d["label"], "confidence": d["confidence"]}
            for d in detections[:10]  # Limit to 10
        ]
        
        # Build reason
        threat_result = analysis.get("threat", {})
        reason = threat_result.get("description", "Threat level exceeded threshold")
        
        # Build breakdown
        breakdown = threat_result.get("raw_scores", {})
        
        # Calculate event duration from temporal data
        temporal = analysis.get("temporal", {})
        active_events = temporal.get("active_events", {})
        max_duration = 0
        for event in active_events.values():
            if isinstance(event, dict):
                max_duration = max(max_duration, event.get("duration", 0))
        
        return {
            "timestamp": float(timestamp),
            "datetime": datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S"),
            "threat_level": str(analysis.get("threat_level", "UNKNOWN")),
            "threat_score": float(analysis.get("threat_score", 0)),
            "source": str(source_name),
            "detected_objects": detected_objects,
            "reason": str(reason),
            "confidence": float(max([d["confidence"] for d in detections] + [0])),
            "snapshot_path": str(snapshot_path),
            "snapshot_url": f"/snapshots/{os.path.basename(snapshot_path)}" if snapshot_path else "",
            "event_duration": float(round(max_duration, 1)),
            "breakdown": {str(k): float(v) for k, v in breakdown.items()} if isinstance(breakdown, dict) else {},
        }
    
    def _clean_recent_alerts(self, current_time):
        """Remove alerts older than 60 seconds from recent tracking."""
        self.recent_alerts = [
            (t, l) for t, l in self.recent_alerts
            if current_time - t < 60
        ]
    
    def register_callback(self, callback):
        """Register a callback function to be called on new alerts."""
        self.on_alert_callbacks.append(callback)
    
    def get_recent_alerts(self, count=10):
        """Get recent alerts from database."""
        return self.db.get_alerts(limit=count)
    
    def get_stats(self):
        """Get alert statistics."""
        return {
            "total_alerts": self.total_alerts,
            "last_alert_time": self.last_alert_time,
            "last_alert_level": self.last_alert_level,
            "alerts_in_last_minute": len(self.recent_alerts),
        }
