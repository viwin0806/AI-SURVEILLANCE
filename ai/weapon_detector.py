"""
Weapon Detection Module
========================
Modular weapon detection component that can use:
1. Standard YOLO COCO classes (knife detection)
2. Custom weapon detection model (when available)

This module is designed to be swappable — you can load a custom-trained
weapon detection model by setting WEAPON_MODEL_PATH in config.py.

The module clearly distinguishes between:
- Normal objects
- Weapon detections
- Unknown/low-confidence detections
"""

import logging
import numpy as np

logger = logging.getLogger(__name__)

# COCO classes that could indicate weapons
YOLO_WEAPON_CLASSES = {
    43: "knife",
}

# Extended weapon categories for custom models
WEAPON_CATEGORIES = {
    "firearm": ["gun", "pistol", "rifle", "shotgun", "firearm"],
    "blade": ["knife", "sword", "machete", "blade", "dagger"],
    "blunt": ["bat", "club", "hammer"],
    "other": ["weapon", "explosive"],
}


class WeaponDetector:
    """
    Weapon detection module for surveillance system.
    
    Phase 1: Uses YOLO COCO detections (knife class).
    Phase 2: Supports loading a custom weapon detection model.
    """
    
    def __init__(self, custom_model_path=None, confidence_threshold=0.30):
        """
        Initialize weapon detector.
        
        Args:
            custom_model_path: Path to custom weapon detection model (optional)
            confidence_threshold: Minimum confidence for weapon detection
        """
        self.custom_model = None
        self.custom_model_path = custom_model_path
        self.confidence_threshold = confidence_threshold
        self.using_custom_model = False
        
        if custom_model_path:
            self._load_custom_model(custom_model_path)
    
    def _load_custom_model(self, model_path):
        """
        Load a custom weapon detection model.
        
        This is a placeholder for Phase 2 — when a custom-trained model
        is available, it can be loaded here.
        """
        try:
            import os
            if os.path.exists(model_path):
                from ultralytics import YOLO
                self.custom_model = YOLO(model_path)
                self.using_custom_model = True
                logger.info(f"Custom weapon model loaded: {model_path}")
            else:
                logger.warning(f"Custom weapon model not found: {model_path}")
        except Exception as e:
            logger.error(f"Failed to load custom weapon model: {e}")
    
    def analyze(self, detections, frame=None):
        """
        Analyze detections for weapon presence.
        
        Args:
            detections: List of detection dicts from ObjectDetector
            frame: Original frame (used with custom model only)
            
        Returns:
            dict with weapon analysis:
            {
                "weapon_detected": bool,
                "weapon_score": float (0-100),
                "weapons": [
                    {
                        "type": "knife",
                        "category": "blade",
                        "confidence": 0.75,
                        "bbox": [x1, y1, x2, y2],
                        "source": "yolo_coco" | "custom_model",
                    }
                ],
                "detection_source": str,
            }
        """
        weapons_found = []
        
        # Method 1: Check YOLO COCO detections for weapon classes
        for det in detections:
            class_id = det.get("class_id", -1)
            label = det.get("label", "").lower()
            conf = det.get("confidence", 0)
            
            # Check if detection is a known weapon class
            is_weapon = False
            weapon_category = "other"
            
            if class_id in YOLO_WEAPON_CLASSES:
                is_weapon = True
            
            # Also check label text for weapon keywords
            for category, keywords in WEAPON_CATEGORIES.items():
                if any(kw in label for kw in keywords):
                    is_weapon = True
                    weapon_category = category
                    break
            
            if is_weapon and conf >= self.confidence_threshold:
                weapons_found.append({
                    "type": label,
                    "category": weapon_category,
                    "confidence": conf,
                    "bbox": det.get("bbox", [0, 0, 0, 0]),
                    "source": "yolo_coco",
                })
        
        # Method 2: Run custom weapon model if available
        if self.using_custom_model and frame is not None:
            custom_weapons = self._run_custom_model(frame)
            weapons_found.extend(custom_weapons)
        
        # Calculate weapon presence score (0-100)
        weapon_score = 0
        if weapons_found:
            # Score based on highest confidence weapon detection
            max_conf = max(w["confidence"] for w in weapons_found)
            weapon_count_factor = min(len(weapons_found) / 3.0, 1.0)
            weapon_score = max_conf * 80 + weapon_count_factor * 20
            weapon_score = min(100, weapon_score)
        
        return {
            "weapon_detected": len(weapons_found) > 0,
            "weapon_score": round(weapon_score, 1),
            "weapons": weapons_found,
            "weapon_count": len(weapons_found),
            "detection_source": "custom_model" if self.using_custom_model else "yolo_coco",
            "model_note": (
                "Using standard YOLO COCO model (knife class only). "
                "For comprehensive weapon detection, load a custom-trained model."
                if not self.using_custom_model else
                f"Using custom weapon model: {self.custom_model_path}"
            ),
        }
    
    def _run_custom_model(self, frame):
        """Run custom weapon detection model on frame."""
        weapons = []
        try:
            if self.custom_model is None:
                return weapons
            
            results = self.custom_model.predict(
                frame, conf=self.confidence_threshold, verbose=False
            )
            
            if results and len(results) > 0:
                result = results[0]
                if result.boxes is not None:
                    for box in result.boxes:
                        x1, y1, x2, y2 = box.xyxy[0].cpu().numpy().astype(int)
                        conf = float(box.conf[0].cpu().numpy())
                        cls_id = int(box.cls[0].cpu().numpy())
                        label = result.names.get(cls_id, "weapon")
                        
                        weapons.append({
                            "type": label,
                            "category": self._categorize_weapon(label),
                            "confidence": round(conf, 3),
                            "bbox": [int(x1), int(y1), int(x2), int(y2)],
                            "source": "custom_model",
                        })
        except Exception as e:
            logger.error(f"Custom weapon model inference error: {e}")
        
        return weapons
    
    def _categorize_weapon(self, label):
        """Categorize a weapon label into a category."""
        label_lower = label.lower()
        for category, keywords in WEAPON_CATEGORIES.items():
            if any(kw in label_lower for kw in keywords):
                return category
        return "other"
    
    def get_status(self):
        """Get weapon detector status."""
        return {
            "using_custom_model": self.using_custom_model,
            "custom_model_path": self.custom_model_path,
            "confidence_threshold": self.confidence_threshold,
            "supported_classes": (
                list(YOLO_WEAPON_CLASSES.values()) 
                if not self.using_custom_model 
                else "custom model classes"
            ),
        }
