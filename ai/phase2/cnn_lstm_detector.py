"""
Phase 2 — CNN-LSTM Temporal Action Recognition
================================================
Advanced violence and action detection using a temporal neural network.

Phase 1 uses optical flow (real-time, no GPU required).
Phase 2 EXTENDS with a CNN-LSTM that learns spatial+temporal features
across a sequence of frames.

Architecture:
  Frame t-n ... Frame t  →  CNN Feature Extractor (MobileNetV2)
                          →  LSTM  (temporal modeling)
                          →  Classification: [normal, suspicious, violent]

This module is designed to be SWAPPABLE with a pretrained model.
If a pretrained model weight file is available, place it at:
  data/models/cnn_lstm_violence.pth

If no model is available, the module gracefully falls back to Phase 1
optical flow violence detection.

Training Data Compatible:
- UCF-Crime Dataset (recommended): https://www.crcv.ucf.edu/projects/real-world/
- NTU CCTV-Fights:                 https://rose1.ntu.edu.sg/dataset/cctvFights/

Hardware:
- Phase 1 optical flow: runs on any CPU
- Phase 2 CNN-LSTM:     recommended GPU (CUDA), but runs on CPU (~2–5 FPS)
"""

import os
import logging
import numpy as np
from collections import deque

logger = logging.getLogger(__name__)

# Default paths
DEFAULT_MODEL_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "data", "models", "cnn_lstm_violence.pth"
)

# Sequence length for temporal analysis
SEQUENCE_LENGTH = 16   # Number of frames per clip


class CNNLSTMDetector:
    """
    CNN-LSTM based violence/action detector.

    Replaces optical flow for improved temporal action recognition.
    Falls back to optical flow if model is not available.

    Usage:
        detector = CNNLSTMDetector(model_path="data/models/cnn_lstm_violence.pth")
        result = detector.analyze(frame)

    Output keys (same interface as Phase 1 ViolenceDetector):
        violence_score:       float (0-100)
        violence_probability: float (0-1)
        motion_intensity:     float (0-100)
        is_violent:           bool
        description:          str
        method:               "cnn_lstm" or "optical_flow_fallback"
    """

    def __init__(self, model_path=None, sequence_length=SEQUENCE_LENGTH,
                 device="auto", fallback_violence_detector=None):
        """
        Initialize CNN-LSTM detector.

        Args:
            model_path:   Path to pretrained .pth model weights
            sequence_length: Number of frames per input clip
            device:       "auto", "cuda", "cpu"
            fallback_violence_detector: Phase 1 ViolenceDetector instance to use
                                        if model not available
        """
        self.model_path = model_path or DEFAULT_MODEL_PATH
        self.sequence_length = sequence_length
        self.fallback = fallback_violence_detector
        self.model = None
        self.transform = None
        self.device = device
        self.is_loaded = False
        self.frame_buffer = deque(maxlen=sequence_length)
        self.last_score = 0.0

        self._try_load_model()

    def _try_load_model(self):
        """
        Attempt to load pretrained CNN-LSTM model.
        Falls back gracefully if model or libraries not available.
        """
        if not os.path.exists(self.model_path):
            logger.info(
                f"[Phase 2] CNN-LSTM model not found at {self.model_path}. "
                "Using Phase 1 optical flow fallback. "
                "To enable Phase 2: place trained weights at data/models/cnn_lstm_violence.pth"
            )
            return

        try:
            import torch
            import torch.nn as nn
            import torchvision.transforms as transforms
            import torchvision.models as models

            # ── Resolve device ────────────────────────────────
            if self.device == "auto":
                self.device = "cuda" if torch.cuda.is_available() else "cpu"

            # ── Define model architecture ─────────────────────
            self.model = self._build_model().to(self.device)
            state = torch.load(self.model_path, map_location=self.device)
            self.model.load_state_dict(state)
            self.model.eval()

            # ── Preprocessing transforms ──────────────────────
            self.transform = transforms.Compose([
                transforms.ToPILImage(),
                transforms.Resize((112, 112)),
                transforms.ToTensor(),
                transforms.Normalize(
                    mean=[0.485, 0.456, 0.406],
                    std=[0.229, 0.224, 0.225]
                ),
            ])

            self.is_loaded = True
            logger.info(f"[Phase 2] CNN-LSTM model loaded on {self.device}")

        except ImportError as e:
            logger.warning(f"[Phase 2] torch/torchvision not available for CNN-LSTM: {e}")
        except Exception as e:
            logger.error(f"[Phase 2] Failed to load CNN-LSTM model: {e}")

    def _build_model(self):
        """
        Build CNN-LSTM architecture.

        CNN: MobileNetV2 (lightweight feature extractor)
        LSTM: 2-layer LSTM (temporal modeling)
        Output: 3 classes [normal, suspicious, violent]

        This is the architecture to use for training on UCF-Crime / CCTV-Fights.
        """
        import torch.nn as nn
        import torchvision.models as models

        class ViolenceCNNLSTM(nn.Module):
            def __init__(self, num_classes=3, hidden_size=256, num_layers=2):
                super().__init__()

                # CNN backbone (feature extractor per frame)
                mobilenet = models.mobilenet_v2(weights=None)
                self.cnn = nn.Sequential(*list(mobilenet.children())[:-1])
                self.cnn_out_features = 1280  # MobileNetV2 output size

                # LSTM for temporal modeling
                self.lstm = nn.LSTM(
                    input_size=self.cnn_out_features,
                    hidden_size=hidden_size,
                    num_layers=num_layers,
                    batch_first=True,
                    dropout=0.5,
                )

                # Classifier head
                self.classifier = nn.Sequential(
                    nn.Dropout(0.5),
                    nn.Linear(hidden_size, num_classes),
                    nn.Softmax(dim=1),
                )

            def forward(self, x):
                # x: (batch, sequence, C, H, W)
                batch, seq, C, H, W = x.shape
                # Extract features for each frame
                x = x.view(batch * seq, C, H, W)
                features = self.cnn(x)
                features = features.view(batch * seq, -1)
                features = features.view(batch, seq, -1)
                # LSTM over sequence
                lstm_out, _ = self.lstm(features)
                # Use last timestep
                out = self.classifier(lstm_out[:, -1, :])
                return out

        return ViolenceCNNLSTM(num_classes=3, hidden_size=256, num_layers=2)

    def analyze(self, frame):
        """
        Analyze frame for violence using CNN-LSTM.
        Falls back to Phase 1 optical flow if model not loaded.

        Args:
            frame: BGR numpy array (OpenCV format)

        Returns:
            dict: Same interface as Phase 1 ViolenceDetector.analyze()
        """
        # Fall back to Phase 1 if model not available
        if not self.is_loaded:
            if self.fallback is not None:
                result = self.fallback.analyze(frame)
                result["method"] = "optical_flow_fallback"
                return result
            return self._empty_result()

        try:
            import torch
            import cv2

            # Preprocess frame
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            tensor = self.transform(frame_rgb)
            self.frame_buffer.append(tensor)

            # Need full sequence before inference
            if len(self.frame_buffer) < self.sequence_length:
                return self._empty_result(method="cnn_lstm", warming_up=True)

            # Build batch: (1, seq, C, H, W)
            seq = torch.stack(list(self.frame_buffer)).unsqueeze(0).to(self.device)

            with torch.no_grad():
                probs = self.model(seq)[0].cpu().numpy()

            # Classes: [normal=0, suspicious=1, violent=2]
            normal_prob = float(probs[0])
            suspicious_prob = float(probs[1])
            violent_prob = float(probs[2])

            # Convert to violence score
            violence_score = (suspicious_prob * 50 + violent_prob * 100)
            violence_score = min(100, violence_score)

            # Smooth score
            self.last_score = self.last_score * 0.3 + violence_score * 0.7

            if self.last_score > 75:
                desc = "CNN-LSTM: Violent/aggressive action detected"
            elif self.last_score > 45:
                desc = "CNN-LSTM: Suspicious activity detected"
            elif self.last_score > 20:
                desc = "CNN-LSTM: Elevated motion activity"
            else:
                desc = "CNN-LSTM: Normal activity"

            return {
                "violence_score": round(self.last_score, 1),
                "violence_probability": round(self.last_score / 100.0, 3),
                "motion_intensity": round(violent_prob * 100, 1),
                "motion_direction_chaos": round(suspicious_prob, 3),
                "high_motion_area": round(violent_prob, 3),
                "is_violent": self.last_score > 50,
                "description": desc,
                "method": "cnn_lstm",
                "probs": {
                    "normal": round(normal_prob, 3),
                    "suspicious": round(suspicious_prob, 3),
                    "violent": round(violent_prob, 3),
                },
                "frame_count_analyzed": len(self.frame_buffer),
                "components": {
                    "intensity": round(violent_prob * 100, 1),
                    "area_coverage": round(suspicious_prob * 100, 1),
                    "direction_chaos": 0,
                    "acceleration": 0,
                    "temporal_consistency": round(self.last_score, 1),
                },
            }

        except Exception as e:
            logger.error(f"[Phase 2] CNN-LSTM inference error: {e}")
            if self.fallback is not None:
                result = self.fallback.analyze(frame)
                result["method"] = "optical_flow_fallback"
                return result
            return self._empty_result()

    def _empty_result(self, method="cnn_lstm", warming_up=False):
        """Return empty/default result."""
        desc = "Building frame buffer..." if warming_up else "Model not available"
        return {
            "violence_score": 0,
            "violence_probability": 0,
            "motion_intensity": 0,
            "motion_direction_chaos": 0,
            "high_motion_area": 0,
            "is_violent": False,
            "description": desc,
            "method": method,
            "frame_count_analyzed": len(self.frame_buffer),
            "components": {
                "intensity": 0,
                "area_coverage": 0,
                "direction_chaos": 0,
                "acceleration": 0,
                "temporal_consistency": 0,
            },
        }

    def reset(self):
        """Reset detector state."""
        self.frame_buffer.clear()
        self.last_score = 0.0

    def get_status(self):
        """Get status for dashboard."""
        return {
            "method": "CNN-LSTM (MobileNetV2 + LSTM)" if self.is_loaded else "Optical Flow Fallback",
            "model_loaded": self.is_loaded,
            "model_path": self.model_path,
            "model_exists": os.path.exists(self.model_path),
            "sequence_length": self.sequence_length,
            "device": self.device if self.is_loaded else "N/A",
            "buffer_fill": len(self.frame_buffer),
            "phase": 2 if self.is_loaded else 1,
        }


# ── Training Script Integration Note ────────────────────────────
#
# To train CNN-LSTM on UCF-Crime / CCTV-Fights:
#
#   1. Download UCF-Crime: https://www.crcv.ucf.edu/projects/real-world/
#   2. Organize into:
#      data/training/
#        normal/    <-- normal activity clips
#        violence/  <-- violence/fight clips
#
#   3. Run training:
#      python ai/phase2/train_cnn_lstm.py
#
#   4. Trained weights saved to:
#      data/models/cnn_lstm_violence.pth
#
#   5. The detector will automatically load on next startup.
#
# Hardware recommendation: NVIDIA GPU with 4GB+ VRAM for training.
# Inference runs on CPU (~2-5 FPS) or GPU (~15-30 FPS).
