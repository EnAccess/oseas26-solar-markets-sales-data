"""Model feature importance (NOT causal)."""
from __future__ import annotations

import numpy as np

from ...config import FEATURE_LABELS


def feature_importance(model, features: list[str]) -> list[dict]:
    """Normalised impurity/gain importance as reported by the fitted model (sums to 1)."""
    imp = np.asarray(model.feature_importances_, dtype=float)
    total = imp.sum()
    share = imp / total if total > 0 else np.zeros_like(imp)
    items = [
        {"feature": f, "label": FEATURE_LABELS.get(f, f), "importance": float(s)}
        for f, s in zip(features, share)
    ]
    return sorted(items, key=lambda d: d["importance"], reverse=True)
