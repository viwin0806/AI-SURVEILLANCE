"""
AI-Driven Intelligent Surveillance Framework
Configuration File

All configurable parameters are centralized here.
Modify thresholds, weights, and settings without touching application code.
"""

import os

# =============================================================================
# BASE PATHS
# =============================================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
VIDEO_DIR = os.path.join(DATA_DIR, "videos")
SNAPSHOT_DIR = os.path.join(DATA_DIR, "snapshots")
MODEL_DIR = os.path.join(DATA_DIR, "models")
DB_DIR = os.path.join(BASE_DIR, "database")
DB_PATH = os.path.join(DB_DIR, "surveillance.db")

# Ensure directories exist
for d in [DATA_DIR, VIDEO_DIR, SNAPSHOT_DIR, MODEL_DIR, DB_DIR]:
    os.makedirs(d, exist_ok=True)

# =============================================================================
# FLASK SETTINGS
# =============================================================================
FLASK_HOST = "0.0.0.0"
FLASK_PORT = 5000
FLASK_DEBUG = False
SECRET_KEY = "surveillance-framework-dev-key-2024"

# =============================================================================
# YOLO OBJECT DETECTION
# =============================================================================
YOLO_MODEL = "yolov8n.pt"  # Lightweight model; auto-downloads on first run
YOLO_CONFIDENCE = 0.35      # Minimum confidence threshold
YOLO_IOU = 0.45             # NMS IoU threshold
YOLO_DEVICE = "auto"        # "auto", "cuda", "cpu"
YOLO_IMG_SIZE = 416          # Smaller = faster; 416 gives ~2.5x speedup over 640

# COCO classes that are relevant for surveillance
PERSON_CLASS_ID = 0
WEAPON_CLASSES = {
    # Standard COCO weapon-related classes
    43: "knife",
    # Custom weapon model classes can be added here
}
VEHICLE_CLASSES = {2: "car", 3: "motorcycle", 5: "bus", 7: "truck"}
RELEVANT_CLASSES = {
    0: "person",
    24: "backpack",
    25: "umbrella",
    26: "handbag",
    27: "suitcase",
    28: "tie",
    43: "knife",
    # Vehicles
    2: "car", 3: "motorcycle", 5: "bus", 7: "truck",
}

# =============================================================================
# WEAPON DETECTION
# =============================================================================
WEAPON_MODEL_PATH = None  # Path to custom weapon detection model (None = use YOLO)
WEAPON_CONFIDENCE_THRESHOLD = 0.30
WEAPON_SCORE_BOOST = 40  # Score boost when weapon detected

# =============================================================================
# VIOLENCE DETECTION (Optical Flow Based)
# =============================================================================
VIOLENCE_FLOW_THRESHOLD = 5.0        # Optical flow magnitude threshold
VIOLENCE_INTENSITY_HIGH = 15.0       # High-intensity motion threshold
VIOLENCE_AREA_THRESHOLD = 0.15       # Fraction of frame with high motion
VIOLENCE_DIRECTION_VARIANCE = 1.5    # Direction variance threshold (chaotic motion)
VIOLENCE_FRAME_BUFFER = 8            # Number of frames to analyze for violence
VIOLENCE_SCORE_DECAY = 0.85          # Score decay per frame when no violence

# =============================================================================
# CROWD ANALYSIS
# =============================================================================
CROWD_DENSITY_LOW = 3                # Low crowd threshold (people count)
CROWD_DENSITY_MEDIUM = 8             # Medium crowd threshold
CROWD_DENSITY_HIGH = 15              # High crowd threshold
CROWD_ANOMALY_SPEED_THRESHOLD = 3.0  # Sudden movement threshold
CROWD_DISPERSION_THRESHOLD = 50      # Pixel distance for dispersion detection

# =============================================================================
# TEMPORAL PERSISTENCE ENGINE
# =============================================================================
TEMPORAL_WINDOW_SIZE = 15            # Number of frames in sliding window
PERSISTENCE_CONFIRM_FRAMES = 5      # Frames needed to confirm persistent event
PERSISTENCE_DECAY_RATE = 0.90        # Score decay when event disappears
PERSISTENCE_MIN_SCORE = 10           # Minimum score to maintain event tracking
EVENT_COOLDOWN_SECONDS = 10          # Cooldown between repeated alerts

# =============================================================================
# THREAT SCORING ENGINE — WEIGHTS
# =============================================================================
# These weights determine how each signal contributes to the final threat score.
# All weights should sum to approximately 1.0 for normalized scoring.
THREAT_WEIGHTS = {
    "weapon_presence":    0.30,   # Weapon detection score
    "violence_score":     0.25,   # Violence/action detection score
    "crowd_anomaly":      0.15,   # Crowd anomaly score
    "movement_intensity": 0.10,   # Overall movement intensity
    "temporal_persistence": 0.15, # Persistence of suspicious activity
    "detection_confidence": 0.05, # Average detection confidence
}

# =============================================================================
# THREAT LEVEL THRESHOLDS
# =============================================================================
THREAT_LEVELS = {
    "NORMAL":     (0, 30),
    "SUSPICIOUS": (31, 60),
    "HIGH_RISK":  (61, 80),
    "CRITICAL":   (81, 100),
}

THREAT_COLORS = {
    "NORMAL":     "#22c55e",  # Green
    "SUSPICIOUS": "#eab308",  # Yellow
    "HIGH_RISK":  "#f97316",  # Orange
    "CRITICAL":   "#ef4444",  # Red
}

# =============================================================================
# ALERT SYSTEM
# =============================================================================
ALERT_THRESHOLD_LEVEL = "HIGH_RISK"  # Minimum level to trigger alert
ALERT_SCREENSHOT_QUALITY = 85        # JPEG quality for alert screenshots
ALERT_MAX_PER_MINUTE = 5             # Rate limit for alerts
ALERT_DEDUP_SECONDS = 15             # Ignore duplicate alerts within this window

# =============================================================================
# VIDEO PROCESSING
# =============================================================================
PROCESSING_FPS = 10          # Target processing FPS (limits CPU/GPU usage)
MAX_DISPLAY_WIDTH = 960      # Maximum width for display frames
MAX_DISPLAY_HEIGHT = 540     # Maximum height for display frames
FRAME_SKIP = 1               # Process every Nth frame (1 = every frame)

# =============================================================================
# DEMO MODE
# =============================================================================
DEMO_VIDEOS = {
    "normal_crowd": {
        "filename": "demo_normal.mp4",
        "description": "Normal street/crowd activity",
        "expected_threat": "NORMAL to SUSPICIOUS",
    },
    "suspicious_motion": {
        "filename": "demo_suspicious.mp4",
        "description": "High-motion suspicious activity",
        "expected_threat": "SUSPICIOUS to HIGH_RISK",
    },
    "fight_scene": {
        "filename": "demo_fight.mp4",
        "description": "Violence/fight scenario",
        "expected_threat": "HIGH_RISK to CRITICAL",
    },
}

# =============================================================================
# RUNTIME STATE (modified at runtime, not by user)
# =============================================================================
class RuntimeConfig:
    """Mutable runtime configuration that can be updated from the settings UI."""
    
    def __init__(self):
        self.reset()
    
    def reset(self):
        """Reset to default values from config."""
        self.yolo_confidence = YOLO_CONFIDENCE
        self.processing_fps = PROCESSING_FPS
        self.threat_weights = dict(THREAT_WEIGHTS)
        self.threat_levels = dict(THREAT_LEVELS)
        self.persistence_window = TEMPORAL_WINDOW_SIZE
        self.persistence_confirm = PERSISTENCE_CONFIRM_FRAMES
        self.alert_threshold = ALERT_THRESHOLD_LEVEL
        self.is_running = False
        self.current_source = None
        self.demo_mode = False
    
    def update_weights(self, weights: dict):
        """Update threat scoring weights."""
        for key, value in weights.items():
            if key in self.threat_weights:
                self.threat_weights[key] = float(value)
    
    def update_thresholds(self, thresholds: dict):
        """Update threat level thresholds."""
        self.threat_levels = thresholds
    
    def to_dict(self):
        """Serialize for API responses."""
        return {
            "yolo_confidence": self.yolo_confidence,
            "processing_fps": self.processing_fps,
            "threat_weights": self.threat_weights,
            "threat_levels": {k: list(v) for k, v in self.threat_levels.items()},
            "persistence_window": self.persistence_window,
            "persistence_confirm": self.persistence_confirm,
            "alert_threshold": self.alert_threshold,
            "is_running": self.is_running,
            "current_source": self.current_source,
            "demo_mode": self.demo_mode,
        }


# Global runtime config instance
runtime = RuntimeConfig()
