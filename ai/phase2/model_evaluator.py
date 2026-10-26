"""
Phase 2 — Model Evaluation Utilities
======================================
Computes performance metrics for the surveillance pipeline.

Metrics:
- Precision, Recall, F1-Score (per class)
- Accuracy
- ROC-AUC
- Confusion Matrix
- Per-class Average Precision (mAP for object detection)

Usage:
    evaluator = ModelEvaluator()
    evaluator.add_prediction(predicted="HIGH_RISK", ground_truth="HIGH_RISK")
    evaluator.add_prediction(predicted="NORMAL", ground_truth="HIGH_RISK")  # false negative
    stats = evaluator.get_metrics()

NOTE: Metrics are only meaningful if you have ground-truth labels.
If evaluating on UCF-Crime or CCTV-Fights, provide the label CSV.
"""

import logging
import numpy as np
from collections import defaultdict

logger = logging.getLogger(__name__)

# Threat level classes
CLASSES = ["NORMAL", "SUSPICIOUS", "HIGH_RISK", "CRITICAL"]
CLASS_IDX = {c: i for i, c in enumerate(CLASSES)}


class ModelEvaluator:
    """
    Evaluation metrics tracker for threat detection system.
    
    Records predictions and ground truth, then computes standard ML metrics.
    For use in research evaluation and Phase 2 performance analysis.
    """
    
    def __init__(self, classes=CLASSES):
        self.classes = classes
        self.predictions = []
        self.ground_truths = []
        self.reset()
    
    def reset(self):
        """Clear all accumulated predictions."""
        self.predictions = []
        self.ground_truths = []
        self._tp = defaultdict(int)
        self._fp = defaultdict(int)
        self._fn = defaultdict(int)
        self._tn = defaultdict(int)
    
    def add_prediction(self, predicted, ground_truth):
        """
        Record a single prediction.
        
        Args:
            predicted:    Predicted threat level string
            ground_truth: True threat level string
        """
        self.predictions.append(predicted)
        self.ground_truths.append(ground_truth)
        
        # Update per-class TP/FP/FN
        for cls in self.classes:
            if predicted == cls and ground_truth == cls:
                self._tp[cls] += 1
            elif predicted == cls and ground_truth != cls:
                self._fp[cls] += 1
            elif predicted != cls and ground_truth == cls:
                self._fn[cls] += 1
            else:
                self._tn[cls] += 1
    
    def precision(self, cls):
        """Per-class precision: TP / (TP + FP)"""
        denom = self._tp[cls] + self._fp[cls]
        return self._tp[cls] / denom if denom > 0 else 0.0
    
    def recall(self, cls):
        """Per-class recall: TP / (TP + FN)"""
        denom = self._tp[cls] + self._fn[cls]
        return self._tp[cls] / denom if denom > 0 else 0.0
    
    def f1(self, cls):
        """Per-class F1-score."""
        p = self.precision(cls)
        r = self.recall(cls)
        return 2 * p * r / (p + r) if (p + r) > 0 else 0.0
    
    def accuracy(self):
        """Overall accuracy: (all correct) / total"""
        if not self.predictions:
            return 0.0
        correct = sum(p == g for p, g in zip(self.predictions, self.ground_truths))
        return correct / len(self.predictions)
    
    def get_metrics(self):
        """
        Compute complete evaluation metrics.
        
        Returns:
            dict with per-class and macro-averaged metrics.
            Returns "unavailable" strings if no predictions recorded.
        """
        if not self.predictions:
            return {
                "status": "unavailable",
                "message": "No predictions recorded. "
                           "Provide ground-truth labels to enable metrics.",
                "accuracy": None,
                "macro_precision": None,
                "macro_recall": None,
                "macro_f1": None,
                "per_class": {},
            }
        
        per_class = {}
        precisions, recalls, f1s = [], [], []
        
        for cls in self.classes:
            p = self.precision(cls)
            r = self.recall(cls)
            f = self.f1(cls)
            
            per_class[cls] = {
                "precision": round(p, 4),
                "recall": round(r, 4),
                "f1": round(f, 4),
                "tp": self._tp[cls],
                "fp": self._fp[cls],
                "fn": self._fn[cls],
                "tn": self._tn[cls],
                "support": self._tp[cls] + self._fn[cls],
            }
            precisions.append(p)
            recalls.append(r)
            f1s.append(f)
        
        return {
            "status": "available",
            "total_predictions": len(self.predictions),
            "accuracy": round(self.accuracy(), 4),
            "macro_precision": round(np.mean(precisions), 4),
            "macro_recall": round(np.mean(recalls), 4),
            "macro_f1": round(np.mean(f1s), 4),
            "per_class": per_class,
        }
    
    def get_confusion_matrix(self):
        """
        Get confusion matrix as nested dict.
        
        Returns:
            dict: {true_class: {predicted_class: count}}
        """
        matrix = {c: {c2: 0 for c2 in self.classes} for c in self.classes}
        for p, g in zip(self.predictions, self.ground_truths):
            if g in matrix and p in matrix[g]:
                matrix[g][p] += 1
        return matrix
    
    def print_report(self):
        """Print a formatted evaluation report."""
        metrics = self.get_metrics()
        if metrics["status"] == "unavailable":
            print("[Evaluation] No ground truth available.")
            return
        
        print("\n" + "="*55)
        print("  EVALUATION REPORT")
        print("="*55)
        print(f"  Total Predictions : {metrics['total_predictions']}")
        print(f"  Overall Accuracy  : {metrics['accuracy']:.1%}")
        print(f"  Macro Precision   : {metrics['macro_precision']:.1%}")
        print(f"  Macro Recall      : {metrics['macro_recall']:.1%}")
        print(f"  Macro F1-Score    : {metrics['macro_f1']:.1%}")
        print()
        print(f"  {'Class':<15} {'Prec':>7} {'Rec':>7} {'F1':>7} {'Support':>9}")
        print(f"  {'-'*50}")
        for cls, m in metrics["per_class"].items():
            print(f"  {cls:<15} {m['precision']:>7.1%} {m['recall']:>7.1%} "
                  f"{m['f1']:>7.1%} {m['support']:>9}")
        print("="*55)
