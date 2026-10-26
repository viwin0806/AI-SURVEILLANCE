"""
Threat Scoring Engine
======================
Combines multiple detection signals into a single Threat Severity Score.

This is the CENTRAL SCORING MODULE that implements context-aware
multi-signal threat assessment.

Input Signals:
- Weapon presence score (from weapon_detector)
- Violence probability (from violence_detector)
- Crowd anomaly score (from crowd_analyzer)
- Movement intensity (from violence_detector motion analysis)
- Temporal persistence (from temporal_engine)
- Detection confidence (from YOLO detector)

Output:
- Threat Score (0-100)
- Threat Level (NORMAL, SUSPICIOUS, HIGH_RISK, CRITICAL)
- Score breakdown per component

All weights are configurable via config.py / runtime settings.
"""

import logging

logger = logging.getLogger(__name__)

# Default threat levels
DEFAULT_LEVELS = {
    "NORMAL":     (0, 30),
    "SUSPICIOUS": (31, 60),
    "HIGH_RISK":  (61, 80),
    "CRITICAL":   (81, 100),
}

# Default weights
DEFAULT_WEIGHTS = {
    "weapon_presence":      0.30,
    "violence_score":       0.25,
    "crowd_anomaly":        0.15,
    "movement_intensity":   0.10,
    "temporal_persistence": 0.15,
    "detection_confidence": 0.05,
}


class ThreatScorer:
    """
    Multi-signal threat scoring engine.
    
    Combines all detection signals with configurable weights to produce
    a unified Threat Score and Threat Level classification.
    """
    
    def __init__(self, weights=None, levels=None):
        """
        Initialize threat scorer.
        
        Args:
            weights: Dict of signal weights (should sum to ~1.0)
            levels: Dict of threat level thresholds
        """
        self.weights = weights or dict(DEFAULT_WEIGHTS)
        self.levels = levels or dict(DEFAULT_LEVELS)
        self.score_history = []
    
    def calculate(self, weapon_result, violence_result, crowd_result,
                  temporal_result, detection_result):
        """
        Calculate threat score from all analysis signals.
        
        Args:
            weapon_result: dict from WeaponDetector.analyze()
            violence_result: dict from ViolenceDetector.analyze()
            crowd_result: dict from CrowdAnalyzer.analyze()
            temporal_result: dict from TemporalEngine.update()
            detection_result: dict from ObjectDetector.detect()
            
        Returns:
            dict with complete threat assessment:
            {
                "threat_score": float (0-100),
                "threat_level": str,
                "breakdown": {signal: score},
                "weighted_breakdown": {signal: weighted_score},
                "raw_scores": {signal: raw_score},
                "temporal_modifier": float,
                "description": str,
            }
        """
        # Extract raw scores from each module (all normalized to 0-100)
        raw_scores = {
            "weapon_presence": min(100, weapon_result.get("weapon_score", 0)),
            "violence_score": min(100, violence_result.get("violence_score", 0)),
            "crowd_anomaly": min(100, crowd_result.get("anomaly_score", 0)),
            "movement_intensity": min(100, violence_result.get("motion_intensity", 0)),
            "temporal_persistence": min(100, temporal_result.get("persistence_score", 0)),
            "detection_confidence": self._calc_confidence_score(detection_result),
        }
        
        # Apply weights
        weighted_scores = {}
        for signal, raw_score in raw_scores.items():
            weight = self.weights.get(signal, 0)
            weighted_scores[signal] = raw_score * weight
        
        # Base threat score (weighted sum)
        base_score = sum(weighted_scores.values())
        
        # Apply temporal modifier
        temporal_modifier = temporal_result.get("temporal_threat_modifier", 1.0)
        modified_score = base_score * temporal_modifier
        
        # Clamp to 0-100
        final_score = max(0, min(100, modified_score))
        
        # Determine threat level
        threat_level = self._classify_level(final_score)
        
        # Generate description
        description = self._generate_description(
            threat_level, final_score, raw_scores, weapon_result, violence_result
        )
        
        # Store in history
        self.score_history.append(final_score)
        if len(self.score_history) > 100:
            self.score_history = self.score_history[-100:]
        
        return {
            "threat_score": float(round(float(final_score), 1)),
            "threat_level": str(threat_level),
            "breakdown": {
                str(k): float(round(float(v), 1)) for k, v in weighted_scores.items()
            },
            "weighted_breakdown": {
                str(k): float(round(float(v), 1)) for k, v in weighted_scores.items()
            },
            "raw_scores": {
                str(k): float(round(float(v), 1)) for k, v in raw_scores.items()
            },
            "temporal_modifier": float(round(float(temporal_modifier), 3)),
            "description": str(description),
            "threat_color": self._get_threat_color(threat_level),
        }
    
    def _calc_confidence_score(self, detection_result):
        """
        Calculate a confidence-based score.
        Higher when there are many high-confidence detections.
        """
        detections = detection_result.get("detections", [])
        if not detections:
            return 0
        
        confidences = [d["confidence"] for d in detections]
        avg_conf = sum(confidences) / len(confidences)
        detection_count_factor = min(len(detections) / 10.0, 1.0)
        
        # Higher confidence + more detections = higher score
        return min(100, avg_conf * 60 + detection_count_factor * 40)
    
    def _classify_level(self, score):
        """Classify threat score into threat level."""
        for level, (low, high) in self.levels.items():
            if low <= score <= high:
                return level
        
        if score > 80:
            return "CRITICAL"
        return "NORMAL"
    
    def _get_threat_color(self, level):
        """Get color for threat level."""
        colors = {
            "NORMAL":     "#22c55e",
            "SUSPICIOUS": "#eab308",
            "HIGH_RISK":  "#f97316",
            "CRITICAL":   "#ef4444",
        }
        return colors.get(level, "#6b7280")
    
    def _generate_description(self, level, score, raw_scores, weapon_result, violence_result):
        """Generate human-readable threat description."""
        parts = []
        
        if weapon_result.get("weapon_detected"):
            weapons = weapon_result.get("weapons", [])
            weapon_types = [w["type"] for w in weapons]
            parts.append(f"Weapon detected: {', '.join(weapon_types)}")
        
        if raw_scores["violence_score"] > 50:
            parts.append("Violent/aggressive activity detected")
        elif raw_scores["violence_score"] > 25:
            parts.append("Suspicious movement patterns")
        
        if raw_scores["crowd_anomaly"] > 40:
            parts.append("Crowd anomaly detected")
        
        if raw_scores["temporal_persistence"] > 50:
            parts.append("Persistent threat activity")
        
        if not parts:
            if level == "NORMAL":
                return "Normal activity — no threats detected"
            else:
                return "Elevated activity levels detected"
        
        return "; ".join(parts)
    
    def update_weights(self, new_weights):
        """Update scoring weights at runtime."""
        for key, value in new_weights.items():
            if key in self.weights:
                self.weights[key] = float(value)
        logger.info(f"Threat weights updated: {self.weights}")
    
    def update_levels(self, new_levels):
        """Update threat level thresholds at runtime."""
        self.levels = new_levels
        logger.info(f"Threat levels updated: {self.levels}")
    
    def get_stats(self):
        """Get scoring statistics."""
        if not self.score_history:
            return {"avg_score": 0, "max_score": 0, "min_score": 0, "count": 0}
        
        return {
            "avg_score": round(sum(self.score_history) / len(self.score_history), 1),
            "max_score": round(max(self.score_history), 1),
            "min_score": round(min(self.score_history), 1),
            "count": len(self.score_history),
            "current_weights": self.weights,
            "current_levels": {k: list(v) for k, v in self.levels.items()},
        }
