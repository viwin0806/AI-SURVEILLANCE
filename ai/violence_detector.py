"""
Violence Detection Module (Optical Flow Based)
================================================
Analyzes consecutive frames to detect violent or aggressive activity.

This module uses dense optical flow (Farneback method) to detect:
- High-intensity sudden motion
- Chaotic multi-directional movement
- Rapid motion changes (acceleration)

This is a TEMPORAL analysis — it works across multiple frames,
not single-frame classification.

Phase 1: Optical flow + motion statistics
Phase 2: Can be augmented with CNN-LSTM or 3D CNN action recognition
"""

import logging
import cv2
import numpy as np
from collections import deque

logger = logging.getLogger(__name__)


class ViolenceDetector:
    """
    Motion-based violence/aggressive activity detector.
    
    Uses dense optical flow analysis across consecutive frames to detect
    violent motion patterns. This is fundamentally different from object
    detection — it analyzes HOW things move, not WHAT they are.
    """
    
    def __init__(self, buffer_size=8, flow_threshold=5.0,
                 intensity_high=15.0, area_threshold=0.15,
                 direction_variance_threshold=1.5, score_decay=0.85):
        """
        Initialize violence detector.
        
        Args:
            buffer_size: Number of frames to keep in analysis buffer
            flow_threshold: Minimum optical flow magnitude to consider as motion
            intensity_high: Threshold for "high intensity" motion
            area_threshold: Fraction of frame area with high motion to trigger
            direction_variance_threshold: Variance in flow direction (chaos indicator)
            score_decay: How quickly violence score decays when no violence detected
        """
        self.buffer_size = buffer_size
        self.flow_threshold = flow_threshold
        self.intensity_high = intensity_high
        self.area_threshold = area_threshold
        self.direction_variance_threshold = direction_variance_threshold
        self.score_decay = score_decay
        
        # Frame buffer for temporal analysis
        self.frame_buffer = deque(maxlen=buffer_size)
        self.gray_buffer = deque(maxlen=buffer_size)
        self.flow_buffer = deque(maxlen=buffer_size)
        
        # Running violence score (smoothed over time)
        self.current_score = 0.0
        self.score_history = deque(maxlen=30)
        
        # Motion statistics history
        self.motion_history = deque(maxlen=buffer_size)
        
    def analyze(self, frame):
        """
        Analyze a frame for violence/aggressive motion.
        
        Args:
            frame: BGR image (OpenCV format)
            
        Returns:
            dict with violence analysis:
            {
                "violence_score": float (0-100),
                "violence_probability": float (0-1),
                "motion_intensity": float (0-100),
                "motion_direction_chaos": float (0-1),
                "high_motion_area": float (0-1),
                "is_violent": bool,
                "description": str,
                "frame_count_analyzed": int,
            }
        """
        if frame is None:
            return self._empty_result()
        
        # Convert to grayscale for optical flow
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        # Resize aggressively for fast optical flow (160x120 is sufficient for motion patterns)
        h, w = gray.shape
        scale = min(160 / w, 120 / h, 1.0)
        if scale < 1.0:
            gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        
        self.gray_buffer.append(gray)
        
        # Need at least 2 frames for optical flow
        if len(self.gray_buffer) < 2:
            return self._empty_result()
        
        # Compute dense optical flow between current and previous frame
        prev_gray = self.gray_buffer[-2]
        curr_gray = self.gray_buffer[-1]
        
        try:
            flow = cv2.calcOpticalFlowFarneback(
                prev_gray, curr_gray,
                None,
                pyr_scale=0.5,
                levels=2,
                winsize=11,
                iterations=2,
                poly_n=5,
                poly_sigma=1.1,
                flags=0,
            )
        except Exception as e:
            logger.error(f"Optical flow error: {e}")
            return self._empty_result()
        
        self.flow_buffer.append(flow)
        
        # Analyze motion patterns
        motion_stats = self._analyze_motion(flow)
        self.motion_history.append(motion_stats)
        
        # Calculate violence indicators from temporal motion history
        violence_result = self._calculate_violence_score(motion_stats)
        
        return violence_result
    
    def _analyze_motion(self, flow):
        """
        Extract motion statistics from optical flow field.
        
        Returns dict with motion metrics.
        """
        # Compute flow magnitude and angle
        magnitude, angle = cv2.cartToPolar(flow[..., 0], flow[..., 1])
        
        # Overall motion intensity
        mean_magnitude = float(np.mean(magnitude))
        max_magnitude = float(np.max(magnitude))
        
        # High-motion area (fraction of frame with intense motion)
        high_motion_mask = magnitude > self.flow_threshold
        high_motion_area = float(np.mean(high_motion_mask))
        
        # Very high intensity area
        very_high_mask = magnitude > self.intensity_high
        very_high_area = float(np.mean(very_high_mask))
        
        # Direction analysis — chaotic motion has high direction variance
        # Only analyze pixels with significant motion
        significant_mask = magnitude > self.flow_threshold
        if np.any(significant_mask):
            significant_angles = angle[significant_mask]
            # Circular variance of directions (0 = uniform direction, 1 = chaos)
            cos_mean = np.mean(np.cos(significant_angles))
            sin_mean = np.mean(np.sin(significant_angles))
            direction_consistency = np.sqrt(cos_mean**2 + sin_mean**2)
            direction_chaos = 1.0 - direction_consistency
        else:
            direction_chaos = 0.0
        
        # Motion acceleration (change in magnitude between frames)
        acceleration = 0.0
        if len(self.motion_history) >= 1:
            prev_magnitude = self.motion_history[-1].get("mean_magnitude", 0)
            acceleration = abs(mean_magnitude - prev_magnitude)
        
        return {
            "mean_magnitude": mean_magnitude,
            "max_magnitude": max_magnitude,
            "high_motion_area": high_motion_area,
            "very_high_area": very_high_area,
            "direction_chaos": direction_chaos,
            "acceleration": acceleration,
        }
    
    def _calculate_violence_score(self, current_stats):
        """
        Calculate violence score from motion statistics.
        
        Violence indicators:
        1. High motion intensity (people moving fast/aggressively)
        2. Large area of intense motion (widespread activity)
        3. Chaotic directions (multi-directional = fighting)
        4. Rapid acceleration (sudden movements)
        5. Temporal consistency (sustained high motion)
        """
        # Individual violence indicators (0-1 scale)
        
        # 1. Motion intensity score
        intensity_score = min(
            current_stats["mean_magnitude"] / self.intensity_high, 1.0
        )
        
        # 2. High-motion area score
        area_score = min(
            current_stats["high_motion_area"] / self.area_threshold, 1.0
        )
        
        # 3. Direction chaos score
        chaos_score = min(
            current_stats["direction_chaos"] / self.direction_variance_threshold, 1.0
        )
        
        # 4. Acceleration score (sudden movements)
        accel_score = min(
            current_stats["acceleration"] / (self.intensity_high * 0.5), 1.0
        )
        
        # 5. Temporal consistency — check if motion has been high over recent frames
        temporal_score = 0.0
        if len(self.motion_history) >= 3:
            recent_intensities = [
                m["mean_magnitude"] for m in list(self.motion_history)[-5:]
            ]
            high_frames = sum(
                1 for m in recent_intensities if m > self.flow_threshold
            )
            temporal_score = high_frames / len(recent_intensities)
        
        # Weighted combination of indicators
        raw_score = (
            intensity_score * 0.25 +
            area_score * 0.25 +
            chaos_score * 0.20 +
            accel_score * 0.15 +
            temporal_score * 0.15
        )
        
        # Convert to 0-100 scale
        frame_violence_score = raw_score * 100
        
        # Smooth the score over time with decay
        if frame_violence_score > self.current_score:
            # Score rises quickly
            self.current_score = (
                self.current_score * 0.3 + frame_violence_score * 0.7
            )
        else:
            # Score decays slowly
            self.current_score = self.current_score * self.score_decay
        
        self.current_score = max(0, min(100, self.current_score))
        self.score_history.append(self.current_score)
        
        # Determine if current state indicates violence
        is_violent = self.current_score > 50
        
        # Generate description
        if self.current_score > 75:
            description = "Intense aggressive motion detected"
        elif self.current_score > 50:
            description = "Suspicious high-intensity movement"
        elif self.current_score > 25:
            description = "Elevated motion activity"
        else:
            description = "Normal motion patterns"
        
        return {
            "violence_score": float(round(float(self.current_score), 1)),
            "violence_probability": float(round(float(self.current_score) / 100.0, 3)),
            "motion_intensity": float(round(float(intensity_score) * 100, 1)),
            "motion_direction_chaos": float(round(float(chaos_score), 3)),
            "high_motion_area": float(round(float(current_stats["high_motion_area"]), 3)),
            "is_violent": bool(is_violent),
            "description": str(description),
            "frame_count_analyzed": int(len(self.gray_buffer)),
            # Individual component scores for the dashboard breakdown
            "components": {
                "intensity": float(round(float(intensity_score) * 100, 1)),
                "area_coverage": float(round(float(area_score) * 100, 1)),
                "direction_chaos": float(round(float(chaos_score) * 100, 1)),
                "acceleration": float(round(float(accel_score) * 100, 1)),
                "temporal_consistency": float(round(float(temporal_score) * 100, 1)),
            },
        }
    
    def _empty_result(self):
        """Return empty violence analysis result."""
        return {
            "violence_score": 0,
            "violence_probability": 0,
            "motion_intensity": 0,
            "motion_direction_chaos": 0,
            "high_motion_area": 0,
            "is_violent": False,
            "description": "Insufficient frames for analysis",
            "frame_count_analyzed": len(self.gray_buffer),
            "components": {
                "intensity": 0,
                "area_coverage": 0,
                "direction_chaos": 0,
                "acceleration": 0,
                "temporal_consistency": 0,
            },
        }
    
    def reset(self):
        """Reset detector state for new video."""
        self.frame_buffer.clear()
        self.gray_buffer.clear()
        self.flow_buffer.clear()
        self.motion_history.clear()
        self.score_history.clear()
        self.current_score = 0.0
    
    def get_status(self):
        """Get detector status."""
        return {
            "method": "Dense Optical Flow (Farneback)",
            "buffer_size": self.buffer_size,
            "frames_analyzed": len(self.gray_buffer),
            "current_score": round(self.current_score, 1),
        }
