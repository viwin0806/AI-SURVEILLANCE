"""
Temporal Persistence Engine
============================
CORE NOVELTY: Context-Aware Temporal Threat Scoring

This engine maintains a sliding window of detection events and only
confirms threats after they persist across multiple consecutive frames.

Key Principles:
- Single-frame detections do NOT trigger critical alerts
- Threats must persist for N frames to be confirmed
- Threat scores decay when events disappear
- Persistence duration is configurable

This implements the temporal dimension of our threat scoring approach.
"""

import time
import logging
from collections import deque

logger = logging.getLogger(__name__)


class TemporalEvent:
    """Represents a tracked event across time."""
    
    def __init__(self, event_type, initial_score):
        self.event_type = event_type
        self.first_seen = time.time()
        self.last_seen = time.time()
        self.frame_count = 1
        self.scores = deque(maxlen=30)
        self.scores.append(initial_score)
        self.confirmed = False
        self.peak_score = initial_score
    
    @property
    def duration(self):
        return self.last_seen - self.first_seen
    
    @property
    def avg_score(self):
        return sum(self.scores) / len(self.scores) if self.scores else 0
    
    @property
    def current_score(self):
        return self.scores[-1] if self.scores else 0
    
    def update(self, score):
        self.last_seen = time.time()
        self.frame_count += 1
        self.scores.append(score)
        self.peak_score = max(self.peak_score, score)
    
    def to_dict(self):
        return {
            "event_type": self.event_type,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "duration": round(self.duration, 2),
            "frame_count": self.frame_count,
            "avg_score": round(self.avg_score, 1),
            "current_score": round(self.current_score, 1),
            "peak_score": round(self.peak_score, 1),
            "confirmed": self.confirmed,
        }


class TemporalEngine:
    """
    Temporal persistence engine for context-aware threat assessment.
    
    Maintains a sliding window of analysis results and tracks event
    persistence across frames. This is the KEY NOVELTY component.
    
    Logic:
    - Frame analysis → add to window
    - Check if threat indicators persist
    - Calculate persistence score
    - Only confirm events after N consecutive suspicious frames
    - Decay scores when events disappear
    """
    
    def __init__(self, window_size=15, confirm_frames=5,
                 decay_rate=0.90, min_score=10):
        """
        Initialize temporal engine.
        
        Args:
            window_size: Number of frames in sliding window
            confirm_frames: Frames needed to confirm persistent event
            decay_rate: Score decay factor when event disappears
            min_score: Minimum score to maintain tracking
        """
        self.window_size = window_size
        self.confirm_frames = confirm_frames
        self.decay_rate = decay_rate
        self.min_score = min_score
        
        # Sliding window of frame analyses
        self.window = deque(maxlen=window_size)
        
        # Tracked events by type
        self.active_events = {}
        
        # Persistence scores by category
        self.persistence_scores = {
            "weapon": 0.0,
            "violence": 0.0,
            "crowd_anomaly": 0.0,
            "overall": 0.0,
        }
        
        # Event confirmation history
        self.confirmed_events = deque(maxlen=100)
        
    def update(self, analysis_result):
        """
        Update temporal engine with new frame analysis.
        
        Args:
            analysis_result: Combined analysis from all AI modules
            
        Returns:
            dict with temporal persistence results:
            {
                "persistence_score": float (0-100),
                "is_persistent": bool,
                "confirmed_events": list,
                "active_events": dict,
                "persistence_breakdown": dict,
                "temporal_threat_modifier": float,
            }
        """
        self.window.append(analysis_result)
        
        # Extract key scores from analysis
        weapon_score = analysis_result.get("weapon_score", 0)
        violence_score = analysis_result.get("violence_score", 0)
        crowd_anomaly = analysis_result.get("crowd_anomaly_score", 0)
        threat_score = analysis_result.get("raw_threat_score", 0)
        
        # Update persistence tracking for each category
        self._update_category("weapon", weapon_score, threshold=30)
        self._update_category("violence", violence_score, threshold=30)
        self._update_category("crowd_anomaly", crowd_anomaly, threshold=30)
        
        # Calculate overall persistence
        overall_persistence = self._calculate_overall_persistence()
        
        # Check for newly confirmed events
        newly_confirmed = self._check_confirmations()
        
        # Calculate temporal threat modifier
        # This multiplier adjusts the raw threat score based on persistence
        temporal_modifier = self._calculate_temporal_modifier()
        
        return {
            "persistence_score": float(round(float(overall_persistence), 1)),
            "is_persistent": bool(overall_persistence > 50),
            "confirmed_events": [e.to_dict() for e in newly_confirmed],
            "active_events": {
                str(k): v.to_dict() for k, v in self.active_events.items()
            },
            "persistence_breakdown": {
                str(k): float(round(float(v), 1)) for k, v in self.persistence_scores.items()
            },
            "temporal_threat_modifier": float(round(float(temporal_modifier), 3)),
            "window_fill": int(len(self.window)),
            "window_size": int(self.window_size),
        }
    
    def _update_category(self, category, score, threshold=30):
        """Update persistence tracking for a specific category."""
        if score > threshold:
            # Event is active
            if category in self.active_events:
                self.active_events[category].update(score)
            else:
                self.active_events[category] = TemporalEvent(category, score)
            
            # Update persistence score — rises with consecutive detections
            self.persistence_scores[category] = min(100,
                self.persistence_scores[category] * 0.6 + score * 0.4
            )
        else:
            # Event not detected — decay the persistence score
            self.persistence_scores[category] *= self.decay_rate
            
            # Remove event if score drops below minimum
            if self.persistence_scores[category] < self.min_score:
                self.persistence_scores[category] = 0
                if category in self.active_events:
                    del self.active_events[category]
    
    def _calculate_overall_persistence(self):
        """Calculate overall persistence score from all categories."""
        scores = list(self.persistence_scores.values())
        if not scores:
            return 0.0
        
        # Overall persistence is weighted combination
        overall = (
            self.persistence_scores.get("weapon", 0) * 0.35 +
            self.persistence_scores.get("violence", 0) * 0.35 +
            self.persistence_scores.get("crowd_anomaly", 0) * 0.30
        )
        
        self.persistence_scores["overall"] = overall
        return overall
    
    def _check_confirmations(self):
        """
        Check if any active events should be confirmed.
        
        An event is CONFIRMED when it persists for confirm_frames consecutive frames.
        This is the key mechanism that prevents false alarms from single-frame detections.
        """
        newly_confirmed = []
        
        for category, event in self.active_events.items():
            if not event.confirmed and event.frame_count >= self.confirm_frames:
                event.confirmed = True
                self.confirmed_events.append(event)
                newly_confirmed.append(event)
                logger.info(
                    f"CONFIRMED persistent event: {category} "
                    f"(frames: {event.frame_count}, avg_score: {event.avg_score:.1f})"
                )
        
        return newly_confirmed
    
    def _calculate_temporal_modifier(self):
        """
        Calculate a modifier that adjusts threat score based on temporal persistence.
        
        Returns:
            float: Modifier value
            - < 1.0: Reduces threat (new/transient event)
            - = 1.0: Neutral
            - > 1.0: Amplifies threat (persistent event)
        """
        window_count = len(self.window)
        if window_count < 3:
            return 0.5  # Not enough data — reduce threat
        
        # Check how many recent frames had elevated scores
        recent_scores = []
        for analysis in list(self.window)[-min(10, window_count):]:
            score = analysis.get("raw_threat_score", 0)
            recent_scores.append(score)
        
        if not recent_scores:
            return 0.5
        
        # Percentage of recent frames with elevated threat
        elevated_count = sum(1 for s in recent_scores if s > 25)
        elevated_ratio = elevated_count / len(recent_scores)
        
        # Average recent score
        avg_recent = sum(recent_scores) / len(recent_scores)
        
        # Modifier calculation
        if elevated_ratio > 0.7 and avg_recent > 40:
            # Highly persistent — amplify
            return 1.0 + (elevated_ratio - 0.7) * 1.0
        elif elevated_ratio > 0.4:
            # Moderately persistent — slight amplification
            return 0.8 + elevated_ratio * 0.5
        elif elevated_ratio > 0.2:
            # Transient — neutral
            return 0.7
        else:
            # Not persistent — suppress
            return 0.5
    
    def get_persistence_status(self):
        """Get persistence status for dashboard display."""
        return {
            "active_event_count": len(self.active_events),
            "confirmed_event_count": len([
                e for e in self.active_events.values() if e.confirmed
            ]),
            "persistence_scores": {
                k: round(v, 1) for k, v in self.persistence_scores.items()
            },
            "window_fill": f"{len(self.window)}/{self.window_size}",
            "total_confirmed": len(self.confirmed_events),
        }
    
    def reset(self):
        """Reset temporal engine state."""
        self.window.clear()
        self.active_events.clear()
        self.persistence_scores = {
            "weapon": 0.0,
            "violence": 0.0,
            "crowd_anomaly": 0.0,
            "overall": 0.0,
        }
        self.confirmed_events.clear()
