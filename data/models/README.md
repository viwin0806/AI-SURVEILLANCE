# Model Weights Directory

Place custom model weights here for advanced detection.

## Phase 1 (included)

| File | Description | Status |
|------|-------------|--------|
| `../../yolov8n.pt` | YOLOv8 nano (project root) | ✓ Included |

## Phase 2 (optional, replace when available)

| File | Description | How to Get |
|------|-------------|------------|
| `cnn_lstm_violence.pth` | CNN-LSTM violence detection | Train on UCF-Crime (see below) |
| `weapon_yolov8_custom.pt` | Custom weapon detector | Train or request from KCT |

## Training CNN-LSTM on UCF-Crime

```bash
# 1. Download UCF-Crime dataset
#    https://www.crcv.ucf.edu/projects/real-world/

# 2. Organize as:
#    data/training/
#      normal/   (normal activity clips)
#      violence/ (violence/fight clips)

# 3. Train (run from project root)
python ai/phase2/train_cnn_lstm.py

# 4. Weights saved here as: cnn_lstm_violence.pth
```

## Custom Weapon Model

The YOLOv8n base model (COCO) detects:
- knife (class 43)

For a more comprehensive weapon detector:
- Request the custom KCT weapon dataset weights
- OR fine-tune YOLOv8 on a public weapon detection dataset:
  - https://universe.roboflow.com/search?q=weapon+detection
- Place weights as: `weapon_yolov8_custom.pt`
- Update `WEAPON_MODEL_PATH` in `config.py`
