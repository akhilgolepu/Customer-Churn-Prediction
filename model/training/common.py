"""Data loading, the 3-way split, model recipes and metrics shared by
train.py, evaluate.py and threshold_analysis.py. All settings come from
params.yaml at the repository root.
"""

from __future__ import annotations

import hashlib
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from sklearn.metrics import average_precision_score, brier_score_loss, log_loss, roc_auc_score
from sklearn.model_selection import train_test_split

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from model.data_schema import TRAINING_SCHEMA, load_raw_training_csv, validate_frame  # noqa: E402
from model.preprocessing.preprocessing import load_artifacts, prepare_for_model, preprocess  # noqa: E402

PARAMS_PATH = REPO_ROOT / "params.yaml"
MODEL_NAMES = ("dummy", "logistic_regression", "catboost", "catboost_weighted", "lightgbm")


def load_params(path: Path = PARAMS_PATH) -> dict:
    with Path(path).open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


@dataclass
class Dataset:
    x: pd.DataFrame  # model features in feature_list order; categoricals as str
    y: pd.Series  # 1 = churned
    raw: pd.DataFrame  # original columns (for slicing), same row order
    cat_cols: list[str]


def load_dataset(params: dict) -> Dataset:
    cfg = params["data"]
    df = load_raw_training_csv(REPO_ROOT / cfg["path"])
    errors = validate_frame(df, TRAINING_SCHEMA)
    if errors:
        raise ValueError("Training data failed validation:\n  " + "\n  ".join(errors))
    y = (df[cfg["target"]] == cfg["positive_label"]).astype(int)
    raw = df.drop(columns=[cfg["target"]])
    feature_list, cat_cols = load_artifacts()
    x = prepare_for_model(preprocess(raw.drop(columns=cfg["drop_columns"])), feature_list)
    for col in cat_cols:
        x[col] = x[col].astype(str)
    return Dataset(x=x, y=y, raw=raw, cat_cols=list(cat_cols))


@dataclass
class Split:
    train: np.ndarray
    val: np.ndarray
    test: np.ndarray

    @property
    def dev(self) -> np.ndarray:
        """train + validation: everything except the held-out test split."""
        return np.sort(np.concatenate([self.train, self.val]))


def three_way_split(y: pd.Series, params: dict) -> Split:
    cfg = params["split"]
    idx = np.arange(len(y))
    dev, test = train_test_split(idx, test_size=cfg["test_size"], random_state=cfg["seed"], stratify=y)
    val_share_of_dev = cfg["val_size"] / (1.0 - cfg["test_size"])
    train, val = train_test_split(
        dev, test_size=val_share_of_dev, random_state=cfg["seed"], stratify=y.iloc[dev]
    )
    return Split(train=np.sort(train), val=np.sort(val), test=np.sort(test))


def ids_fingerprint(ids) -> str:
    return hashlib.sha256("\n".join(sorted(map(str, ids))).encode("utf-8")).hexdigest()[:16]


# --------------------------------------------------------------------------
# Model recipes. Each fit_* returns a fitted model; predict(name, model, x)
# returns P(churn) as a 1-D array.
# --------------------------------------------------------------------------


def positive_weight(y) -> float:
    y = np.asarray(y)
    return float((y == 0).sum() / (y == 1).sum())


def fit_catboost(x_fit, y_fit, x_es, y_es, cat_cols, cfg: dict, class_weight: float | None = None):
    from catboost import CatBoostClassifier

    kwargs = dict(
        iterations=cfg["max_iterations"],
        depth=cfg["depth"],
        learning_rate=cfg["learning_rate"],
        l2_leaf_reg=cfg["l2_leaf_reg"],
        bagging_temperature=cfg["bagging_temperature"],
        random_seed=cfg["seed"],
        loss_function="Logloss",
        verbose=False,
        thread_count=-1,
        allow_writing_files=False,
    )
    if class_weight is not None:
        kwargs["class_weights"] = {0: 1.0, 1: float(class_weight)}
    model = CatBoostClassifier(**kwargs)
    model.fit(
        x_fit,
        y_fit,
        cat_features=cat_cols,
        eval_set=(x_es, y_es),
        early_stopping_rounds=cfg["early_stopping_rounds"],
        use_best_model=True,
    )
    return model


def _lgbm_frame(x: pd.DataFrame, cat_cols, categories: dict) -> pd.DataFrame:
    out = x.copy()
    for col in cat_cols:
        out[col] = pd.Categorical(out[col], categories=categories[col])
    return out


def category_levels(x: pd.DataFrame, cat_cols) -> dict:
    """Known levels per categorical column (a property of the schema, not of the labels)."""
    return {col: sorted(x[col].unique().tolist()) for col in cat_cols}


def fit_lightgbm(x_fit, y_fit, x_es, y_es, cat_cols, cfg: dict, categories: dict):
    import lightgbm as lgb

    model = lgb.LGBMClassifier(
        n_estimators=cfg["max_iterations"],
        learning_rate=cfg["learning_rate"],
        num_leaves=cfg["num_leaves"],
        min_child_samples=cfg["min_child_samples"],
        subsample=cfg["subsample"],
        subsample_freq=cfg["subsample_freq"],
        colsample_bytree=cfg["colsample_bytree"],
        reg_lambda=cfg["reg_lambda"],
        random_state=cfg["seed"],
        n_jobs=-1,
        verbose=-1,
    )
    model.fit(
        _lgbm_frame(x_fit, cat_cols, categories),
        y_fit,
        eval_X=(_lgbm_frame(x_es, cat_cols, categories),),
        eval_y=(y_es,),
        callbacks=[lgb.early_stopping(cfg["early_stopping_rounds"], verbose=False)],
    )
    model._churn_categories = categories  # used by predict()
    model._churn_cat_cols = list(cat_cols)
    return model


def fit_logistic_regression(x_fit, y_fit, cat_cols, cfg: dict):
    from sklearn.compose import ColumnTransformer
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import OneHotEncoder, StandardScaler

    num_cols = [c for c in x_fit.columns if c not in cat_cols]
    model = make_pipeline(
        ColumnTransformer(
            [
                ("num", make_pipeline(SimpleImputer(strategy="median"), StandardScaler()), num_cols),
                ("cat", OneHotEncoder(handle_unknown="ignore"), list(cat_cols)),
            ]
        ),
        LogisticRegression(C=cfg["C"], max_iter=cfg["max_iter"]),
    )
    model.fit(x_fit, y_fit)
    return model


def fit_dummy(x_fit, y_fit):
    from sklearn.dummy import DummyClassifier

    return DummyClassifier(strategy="prior").fit(x_fit, y_fit)


def fit_model(name: str, x_fit, y_fit, cat_cols, params: dict, categories: dict):
    """Fit one comparison model. Boosting models early-stop on an inner split of
    the rows they are given, so the caller's scoring rows are never used."""
    mcfg = params["models"]
    if name == "dummy":
        return fit_dummy(x_fit, y_fit)
    if name == "logistic_regression":
        return fit_logistic_regression(x_fit, y_fit, cat_cols, mcfg["logistic_regression"])

    inner = params["cv"]["inner_early_stopping_size"]
    x_a, x_b, y_a, y_b = train_test_split(
        x_fit, y_fit, test_size=inner, random_state=params["cv"]["seed"], stratify=y_fit
    )
    if name == "catboost":
        return fit_catboost(x_a, y_a, x_b, y_b, cat_cols, mcfg["catboost"], class_weight=None)
    if name == "catboost_weighted":
        return fit_catboost(x_a, y_a, x_b, y_b, cat_cols, mcfg["catboost"], class_weight=positive_weight(y_a))
    if name == "lightgbm":
        return fit_lightgbm(x_a, y_a, x_b, y_b, cat_cols, mcfg["lightgbm"], categories)
    raise ValueError(name)


def predict(model, x: pd.DataFrame) -> np.ndarray:
    if hasattr(model, "_churn_categories"):
        x = _lgbm_frame(x, model._churn_cat_cols, model._churn_categories)
    return np.asarray(model.predict_proba(x)[:, 1], dtype=float)


# --------------------------------------------------------------------------
# Metrics
# --------------------------------------------------------------------------

PROB_METRICS = ("roc_auc", "pr_auc", "brier", "log_loss")


def prob_metrics(y, p) -> dict:
    y = np.asarray(y)
    p = np.clip(np.asarray(p, dtype=float), 1e-15, 1 - 1e-15)
    return {
        "roc_auc": float(roc_auc_score(y, p)),
        "pr_auc": float(average_precision_score(y, p)),
        "brier": float(brier_score_loss(y, p)),
        "log_loss": float(log_loss(y, p, labels=[0, 1])),
    }


def mean_ci(values) -> dict:
    """Mean and 95% t-interval across CV folds. Folds share training rows, so
    this interval is somewhat too narrow; treat it as a spread, not a test."""
    from scipy import stats

    v = np.asarray(values, dtype=float)
    half = float(stats.t.ppf(0.975, len(v) - 1) * v.std(ddof=1) / np.sqrt(len(v)))
    return {"mean": float(v.mean()), "ci_low": float(v.mean() - half), "ci_high": float(v.mean() + half)}


def paired_bootstrap(y, p_a, p_b, n: int, seed: int, metrics=PROB_METRICS) -> dict:
    """95% percentile interval for metric(a) - metric(b), resampling rows jointly."""
    y = np.asarray(y)
    p_a = np.asarray(p_a, dtype=float)
    p_b = np.asarray(p_b, dtype=float)
    rng = np.random.default_rng(seed)
    diffs = {m: [] for m in metrics}
    for _ in range(n):
        idx = rng.integers(0, len(y), len(y))
        yb = y[idx]
        if yb.min() == yb.max():
            continue
        ma, mb = prob_metrics(yb, p_a[idx]), prob_metrics(yb, p_b[idx])
        for m in metrics:
            diffs[m].append(ma[m] - mb[m])
    point_a, point_b = prob_metrics(y, p_a), prob_metrics(y, p_b)
    return {
        m: {
            "diff": point_a[m] - point_b[m],
            "ci_low": float(np.percentile(diffs[m], 2.5)),
            "ci_high": float(np.percentile(diffs[m], 97.5)),
        }
        for m in metrics
    }


def bootstrap_ci(y, p, metric: str, n: int, seed: int) -> list[float]:
    y = np.asarray(y)
    p = np.asarray(p, dtype=float)
    rng = np.random.default_rng(seed)
    vals = []
    for _ in range(n):
        idx = rng.integers(0, len(y), len(y))
        if y[idx].min() == y[idx].max():
            continue
        vals.append(prob_metrics(y[idx], p[idx])[metric])
    return [float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))]
