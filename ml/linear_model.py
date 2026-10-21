"""Logistic-regression churn model serialised as JSON (no pickles).

Exported from the scikit-learn pipeline in ml/training/common.py
(median imputation + standard scaling for numeric columns, one-hot for
categoricals, LogisticRegression). Scoring and explanations need only numpy.

explain() returns exact per-feature contributions in log-odds space, measured
against the average training customer: coef * standardised value for numeric
features, and the level's coefficient minus its training-average contribution
for categorical features. For a linear model with independent features this is
the same quantity SHAP's LinearExplainer computes.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

FORMAT = "churn_linear/v1"


class LinearChurnModel:
    def __init__(self, spec: dict) -> None:
        if spec.get("format") != FORMAT:
            raise ValueError("Unsupported linear model format")
        self.spec = spec
        self.feature_order: list[str] = spec["feature_order"]
        self._numeric = spec["numeric"]
        self._categorical = spec["categorical"]
        self._intercept = float(spec["intercept"])

    # -- export ---------------------------------------------------------------
    @classmethod
    def from_sklearn(cls, pipeline, x_train: pd.DataFrame, metrics: dict | None = None) -> "LinearChurnModel":
        """Build from the fitted pipeline returned by common.fit_logistic_regression."""
        transformer, lr = pipeline.steps[0][1], pipeline.steps[-1][1]
        num_pipe = transformer.named_transformers_["num"]
        imputer, scaler = num_pipe.steps[0][1], num_pipe.steps[1][1]
        encoder = transformer.named_transformers_["cat"]
        num_cols = list(transformer.transformers_[0][2])
        cat_cols = list(transformer.transformers_[1][2])
        coef = lr.coef_[0]

        numeric = [
            {
                "name": col,
                "median": float(imputer.statistics_[i]),
                "mean": float(scaler.mean_[i]),
                "scale": float(scaler.scale_[i]),
                "coef": float(coef[i]),
            }
            for i, col in enumerate(num_cols)
        ]
        offset = len(num_cols)
        categorical = []
        for col, levels in zip(cat_cols, encoder.categories_):
            weights = {str(level): float(coef[offset + j]) for j, level in enumerate(levels)}
            offset += len(levels)
            freq = x_train[col].astype(str).value_counts(normalize=True)
            baseline = float(sum(weights.get(level, 0.0) * share for level, share in freq.items()))
            categorical.append({"name": col, "weights": weights, "baseline": baseline})

        return cls({
            "format": FORMAT,
            "feature_order": list(x_train.columns),
            "numeric": numeric,
            "categorical": categorical,
            "intercept": float(lr.intercept_[0]),
            "metrics": metrics or {},
        })

    def save(self, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.spec, indent=2), encoding="utf-8")
        return path

    @classmethod
    def load(cls, path: str | Path) -> "LinearChurnModel":
        return cls(json.loads(Path(path).read_text(encoding="utf-8")))

    @staticmethod
    def is_linear_artifact(path: str | Path) -> bool:
        return Path(path).suffix.lower() == ".json"

    # -- scoring --------------------------------------------------------------
    def _contributions(self, x: pd.DataFrame) -> dict[str, np.ndarray]:
        out = {}
        for f in self._numeric:
            values = pd.to_numeric(x[f["name"]], errors="coerce").to_numpy(dtype=float)
            values = np.where(np.isnan(values), f["median"], values)
            out[f["name"]] = f["coef"] * (values - f["mean"]) / f["scale"]
        for f in self._categorical:
            weights = f["weights"]
            # Unseen levels contribute 0 to the one-hot part, like handle_unknown="ignore".
            out[f["name"]] = np.array([weights.get(str(v), 0.0) for v in x[f["name"]]]) - f["baseline"]
        return out

    def _base_logit(self) -> float:
        # Logit of the average training customer: numeric terms are 0 at the mean,
        # categorical terms equal their baselines.
        return self._intercept + sum(f["baseline"] for f in self._categorical)

    def predict_proba(self, x: pd.DataFrame) -> np.ndarray:
        contrib = self._contributions(x)
        logit = self._base_logit() + sum(contrib.values())
        return 1.0 / (1.0 + np.exp(-logit))

    def explain(self, x: pd.DataFrame) -> np.ndarray:
        """Per-feature log-odds contributions for the first row, in x's column order."""
        contrib = self._contributions(x.iloc[:1])
        return np.array([float(contrib[col][0]) if col in contrib else 0.0 for col in x.columns])
