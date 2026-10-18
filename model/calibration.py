"""Post-hoc probability calibration, serialisable to JSON.

Fitting uses scikit-learn; applying a fitted calibrator needs only numpy, so
the API can turn a raw CatBoost score into a calibrated probability without
pickles. A missing calibration file means "identity" (raw score served as-is),
which keeps old artifacts loadable.

Methods
  identity  p
  platt     sigmoid(a * logit(p) + b)        (logistic fit on the raw log-odds)
  isotonic  piecewise-linear interpolation of an isotonic fit, clipped at the ends
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

METHODS = ("identity", "platt", "isotonic")
_EPS = 1e-6


def _logit(p: np.ndarray) -> np.ndarray:
    p = np.clip(np.asarray(p, dtype=float), _EPS, 1 - _EPS)
    return np.log(p / (1 - p))


class Calibrator:
    def __init__(self, method: str = "identity", params: dict | None = None) -> None:
        if method not in METHODS:
            raise ValueError(f"Unknown calibration method: {method}")
        self.method = method
        self.params = params or {}

    @classmethod
    def fit(cls, method: str, scores, y) -> "Calibrator":
        scores = np.asarray(scores, dtype=float)
        y = np.asarray(y, dtype=int)
        if method == "identity":
            return cls("identity")
        if method == "platt":
            from sklearn.linear_model import LogisticRegression

            lr = LogisticRegression(C=1e10, max_iter=1000)  # effectively unpenalised
            lr.fit(_logit(scores).reshape(-1, 1), y)
            return cls("platt", {"a": float(lr.coef_[0][0]), "b": float(lr.intercept_[0])})
        if method == "isotonic":
            from sklearn.isotonic import IsotonicRegression

            iso = IsotonicRegression(y_min=0.0, y_max=1.0, out_of_bounds="clip")
            iso.fit(scores, y)
            return cls("isotonic", {"x": iso.X_thresholds_.tolist(), "y": iso.y_thresholds_.tolist()})
        raise ValueError(f"Unknown calibration method: {method}")

    def transform(self, scores):
        s = np.asarray(scores, dtype=float)
        if self.method == "identity":
            return s
        if self.method == "platt":
            z = self.params["a"] * _logit(s) + self.params["b"]
            return 1.0 / (1.0 + np.exp(-z))
        return np.interp(s, self.params["x"], self.params["y"])

    def to_dict(self) -> dict:
        return {"format": "churn_calibrator/v1", "method": self.method, "params": self.params}

    @classmethod
    def from_dict(cls, data: dict) -> "Calibrator":
        if data.get("format") != "churn_calibrator/v1":
            raise ValueError("Unsupported calibrator format")
        return cls(data["method"], data.get("params") or {})

    def save(self, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
        return path

    @classmethod
    def load(cls, path: str | Path) -> "Calibrator":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def calibration_path_for(model_path: str | Path) -> Path:
    """Sibling calibration file for a .cbm artifact: foo.cbm -> foo.calibration.json."""
    model_path = Path(model_path)
    return model_path.with_name(model_path.stem + ".calibration.json")


def load_for_model(model_path: str | Path) -> Calibrator:
    path = calibration_path_for(model_path)
    return Calibrator.load(path) if path.exists() else Calibrator("identity")


def cross_fit(method: str, scores, y, folds: int, seed: int) -> np.ndarray:
    """Out-of-fold calibrated scores: each row is calibrated by a fit that did not see it."""
    from sklearn.model_selection import StratifiedKFold

    scores = np.asarray(scores, dtype=float)
    y = np.asarray(y, dtype=int)
    out = np.zeros_like(scores)
    skf = StratifiedKFold(n_splits=folds, shuffle=True, random_state=seed)
    for fit_idx, apply_idx in skf.split(scores, y):
        out[apply_idx] = Calibrator.fit(method, scores[fit_idx], y[fit_idx]).transform(scores[apply_idx])
    return out
