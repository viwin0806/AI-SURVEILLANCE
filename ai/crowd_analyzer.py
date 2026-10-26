"""
Crowd Analysis Module
======================
Analyzes crowd density, distribution, and anomalous crowd behavior.

Uses YOLO person detections to:
- Count people in frame
- Estimate crowd density
- Detect sudden crowd changes
- Identify crowd anomalies (dispersion, gathering, sudden movement)
"""

import logging
import numpy as np
from collections import deque

logger = logging.getLogger(__name__)


class CrowdAnalyzer:
    """
    Crowd density and anomaly analyzer.
    
    Tracks crowd behavior over time to detect anomalies like sudden
    dispersions, abnormal gatherings, and unusual crowd dynamics.
    """
    
    def __init__(self, density_low=3, density_medium=8, density_high=15,
                 anomaly_speed_threshold=3.0, history_size=20):
        """
        Initialize crowd analyzer.
        
        Args:
            density_low: Person count threshold for low density
            density_medium: Person count threshold for medium density
            density_high: Person count threshold for high density
            anomaly_speed_threshold: Threshold for sudden crowd changes
            history_size: Number of frames to keep in history
        """
        self.density_low = density_low
        self.density_medium = density_medium
        self.density_high = density_high
        self.anomaly_speed_threshold = anomaly_speed_threshold
        
        # History tracking
        self.count_history = deque(maxlen=history_size)
        self.centroid_history = deque(maxlen=history_size)
        self.density_history = deque(maxlen=history_size)
        
        self.current_anomaly_score = 0.0
        self.anomaly_decay = 0.90
    
    def analyze(self, detections, frame_shape):
        """
        Analyze crowd from person detections.
        
        Args:
            detections: List of detection dicts from ObjectDetector
            frame_shape: (height, width, channels) of the frame
            
        Returns:
            dict with crowd analysis:
            {
                "person_count": int,
                "crowd_density": str,
                "density_score": float (0-100),
                "anomaly_score": float (0-100),
                "dispersion": float,
                "crowd_change_rate": float,
                "description": str,
                "is_anomalous": bool,
            }
        """
        h, w = frame_shape[:2]
        
        # Extract person detections
        persons = [d for d in detections if d.get("class_id") == 0]
        person_count = len(persons)
        
        # Calculate person centroids
        centroids = []
        for p in persons:
            bbox = p["bbox"]
            cx = (bbox[0] + bbox[2]) / 2.0
            cy = (bbox[1] + bbox[3]) / 2.0
            centroids.append([cx, cy])
        
        self.count_history.append(person_count)
        self.centroid_history.append(centroids)
        
        # Density classification
        if person_count >= self.density_high:
            density_label = "HIGH"
            density_score = min(100, 60 + (person_count - self.density_high) * 4)
        elif person_count >= self.density_medium:
            density_label = "MEDIUM"
            density_score = 30 + (person_count - self.density_medium) / (self.density_high - self.density_medium) * 30
        elif person_count >= self.density_low:
            density_label = "LOW"
            density_score = 10 + (person_count - self.density_low) / (self.density_medium - self.density_low) * 20
        else:
            density_label = "MINIMAL"
            density_score = person_count / max(self.density_low, 1) * 10
        
        self.density_history.append(density_score)
        
        # Calculate crowd dispersion (spread of people in frame)
        dispersion = self._calculate_dispersion(centroids, w, h)
        
        # Detect crowd change rate (sudden changes in count)
        change_rate = self._calculate_change_rate()
        
        # Detect crowd anomalies
        anomaly_indicators = self._detect_anomalies(centroids, person_count, change_rate)
        
        # Calculate anomaly score
        raw_anomaly = anomaly_indicators["combined_score"]
        if raw_anomaly > self.current_anomaly_score:
            self.current_anomaly_score = self.current_anomaly_score * 0.3 + raw_anomaly * 0.7
        else:
            self.current_anomaly_score *= self.anomaly_decay
        
        self.current_anomaly_score = max(0, min(100, self.current_anomaly_score))
        
        # Generate description
        description = self._generate_description(
            density_label, person_count, self.current_anomaly_score
        )
        
        return {
            "person_count": int(person_count),
            "crowd_density": str(density_label),
            "density_score": float(round(float(density_score), 1)),
            "anomaly_score": float(round(float(self.current_anomaly_score), 1)),
            "dispersion": float(round(float(dispersion), 3)),
            "crowd_change_rate": float(round(float(change_rate), 2)),
            "description": str(description),
            "is_anomalous": bool(self.current_anomaly_score > 40),
            "components": {str(k): float(v) if isinstance(v, (int, float, np.number)) else v for k, v in anomaly_indicators.items()},
        }
    
    def _calculate_dispersion(self, centroids, width, height):
        """
        Calculate spatial dispersion of people in frame.
        Higher dispersion = people spread out. Lower = clustered.
        """
        if len(centroids) < 2:
            return 0.0
        
        centroids_np = np.array(centroids)
        # Normalize coordinates
        centroids_np[:, 0] /= width
        centroids_np[:, 1] /= height
        
        # Standard deviation of positions = measure of spread
        std_x = np.std(centroids_np[:, 0])
        std_y = np.std(centroids_np[:, 1])
        dispersion = np.sqrt(std_x**2 + std_y**2)
        
        return float(dispersion)
    
    def _calculate_change_rate(self):
        """Calculate rate of change in person count."""
        if len(self.count_history) < 3:
            return 0.0
        
        counts = list(self.count_history)
        recent = counts[-3:]
        
        # Rate of change over last few frames
        if len(recent) >= 2:
            changes = [abs(recent[i] - recent[i-1]) for i in range(1, len(recent))]
            return float(np.mean(changes))
        
        return 0.0
    
    def _detect_anomalies(self, centroids, person_count, change_rate):
        """
        Detect various crowd anomalies.
        
        Returns dict of anomaly indicators with scores.
        """
        anomalies = {
            "sudden_count_change": 0.0,
            "crowd_dispersion_change": 0.0,
            "high_density_alert": 0.0,
            "combined_score": 0.0,
        }
        
        # 1. Sudden count change
        if len(self.count_history) >= 3:
            counts = list(self.count_history)
            recent_change = abs(counts[-1] - counts[-2]) if len(counts) >= 2 else 0
            avg_count = np.mean(counts[-5:]) if len(counts) >= 5 else np.mean(counts)
            
            if avg_count > 0:
                relative_change = recent_change / max(avg_count, 1)
                anomalies["sudden_count_change"] = min(100, relative_change * 100)
        
        # 2. Crowd dispersion change (sudden gathering or scattering)
        if len(self.centroid_history) >= 3 and len(centroids) >= 2:
            prev_centroids = self.centroid_history[-2]
            if len(prev_centroids) >= 2:
                curr_disp = self._calculate_dispersion(
                    centroids, 1, 1  # Already normalized
                )
                prev_disp = self._calculate_dispersion(prev_centroids, 1, 1)
                disp_change = abs(curr_disp - prev_disp)
                anomalies["crowd_dispersion_change"] = min(100, disp_change * 500)
        
        # 3. High density alert
        if person_count >= self.density_high:
            anomalies["high_density_alert"] = min(
                100, (person_count - self.density_high + 1) * 15
            )
        
        # Combined anomaly score
        anomalies["combined_score"] = (
            anomalies["sudden_count_change"] * 0.4 +
            anomalies["crowd_dispersion_change"] * 0.3 +
            anomalies["high_density_alert"] * 0.3
        )
        
        return anomalies
    
    def _generate_description(self, density_label, count, anomaly_score):
        """Generate human-readable crowd description."""
        if anomaly_score > 60:
            return f"Crowd anomaly detected ({count} people, {density_label} density)"
        elif anomaly_score > 30:
            return f"Unusual crowd activity ({count} people)"
        elif count >= self.density_high:
            return f"High crowd density ({count} people)"
        elif count >= self.density_medium:
            return f"Moderate crowd ({count} people)"
        elif count >= self.density_low:
            return f"Small group ({count} people)"
        elif count > 0:
            return f"{count} person(s) detected"
        else:
            return "No people detected"
    
    def reset(self):
        """Reset analyzer state."""
        self.count_history.clear()
        self.centroid_history.clear()
        self.density_history.clear()
        self.current_anomaly_score = 0.0
    
    def get_status(self):
        """Get analyzer status."""
        return {
            "frames_analyzed": len(self.count_history),
            "current_anomaly_score": round(self.current_anomaly_score, 1),
            "avg_person_count": round(
                np.mean(list(self.count_history)) if self.count_history else 0, 1
            ),
        }
