"""
Data Drift Detection Service - Using Evidently AI.

Monitors production data for drift, data quality issues, and model performance.
Generates drift reports and triggers alerts when thresholds are exceeded.
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict

import numpy as np
import pandas as pd

try:
    from evidently.report import Report # type: ignore
    from evidently.metrics import (     
        DataDriftTable, # type: ignore
        DataQualityTable, # type: ignore
    )
    HAS_EVIDENTLY = True
except ImportError:
    HAS_EVIDENTLY = False
    logger = logging.getLogger(__name__)
    logger.warning("Evidently AI not installed. Install with: pip install evidently")

logger = logging.getLogger(__name__)


@dataclass
class DriftAlert:
    """Alert for detected drift."""
    timestamp: str
    feature_name: str
    drift_detected: bool
    drift_type: str  # "statistical", "domain", "performance"
    magnitude: float  # Drift magnitude/p-value
    threshold: float
    reference_value: Optional[float] = None
    production_value: Optional[float] = None
    message: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)


@dataclass
class DriftReport:
    """Complete drift detection report."""
    report_id: str
    timestamp: str
    reference_period: str
    production_period: str
    drifted_features: List[str]
    data_quality_issues: List[str]
    alerts: List[Dict[str, Any]]
    metrics: Dict[str, Any]
    report_path: Optional[str] = None
    html_path: Optional[str] = None
    alerts_severity: str = "normal"  # critical, high, medium, low, normal

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=2, default=str)


class EvidentiallyDriftDetector:
    """Data drift detection using Evidently AI."""

    def __init__(
        self,
        reference_data: Optional[pd.DataFrame] = None,
        feature_names: Optional[List[str]] = None,
        numerical_features: Optional[List[str]] = None,
        categorical_features: Optional[List[str]] = None,
        target_column: Optional[str] = None,
        drift_threshold: float = 0.05,  # p-value threshold for drift
    ):
        """
        Initialize drift detector.

        Args:
            reference_data: Historical data to establish baseline
            feature_names: List of feature names
            numerical_features: Numerical columns for analysis
            categorical_features: Categorical columns for analysis
            target_column: Target column name for performance drift
            drift_threshold: Statistical test p-value threshold (default 0.05)
        """
        if not HAS_EVIDENTLY:
            raise ImportError("Evidently AI not installed. Install with: pip install evidently")

        self.reference_data = reference_data
        self.feature_names = feature_names or []
        self.numerical_features = numerical_features or []
        self.categorical_features = categorical_features or []
        self.target_column = target_column
        self.drift_threshold = drift_threshold

        self.alerts: List[DriftAlert] = []
        logger.info(f"Drift detector initialized with {len(self.feature_names)} features")

    def detect_data_drift(
        self,
        production_data: pd.DataFrame,
        as_is_data: Optional[pd.DataFrame] = None,
        columns: Optional[List[str]] = None,
    ) -> DriftReport:
        """
        Detect data drift between reference and production data.

        Args:
            production_data: Current production data
            as_is_data: Optional comparison data (use production if None)
            columns: Specific columns to analyze (use all if None)

        Returns:
            DriftReport with findings and alerts
        """
        if self.reference_data is None:
            raise ValueError("Reference data not provided during initialization")

        report_id = f"drift_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
        timestamp = datetime.utcnow().isoformat()

        if as_is_data is None:
            as_is_data = production_data

        # Prepare data for report
        reference_period = f"Reference: {len(self.reference_data)} samples"
        production_period = f"Production: {len(production_data)} samples"

        # Create Evidently report
        report = Report(
            metrics=[
                DataDriftTable(columns=columns or self.feature_names),
                DataQualityTable(),
            ]
        )

        report.run(reference_data=self.reference_data, current_data=production_data)

        # Extract metrics
        drift_data = report.as_dict()["metrics"]

        drifted_features = self._extract_drifted_features(drift_data)
        data_quality_issues = self._extract_data_quality_issues(drift_data)

        # Generate alerts
        alerts, severity = self._generate_alerts(
            drifted_features, data_quality_issues, production_data
        )

        drift_report = DriftReport(
            report_id=report_id,
            timestamp=timestamp,
            reference_period=reference_period,
            production_period=production_period,
            drifted_features=drifted_features,
            data_quality_issues=data_quality_issues,
            alerts=[a.to_dict() for a in alerts],
            metrics=self._extract_summary_metrics(drift_data),
            alerts_severity=severity,
        )

        return drift_report

    def detect_performance_drift(
        self,
        production_data: pd.DataFrame,
        y_true: np.ndarray,
        y_pred_proba: np.ndarray,
        y_pred_binary: np.ndarray,
        reference_auc: float = 0.85,
    ) -> DriftReport:
        """
        Detect model performance drift.

        Args:
            production_data: Production features
            y_true: Ground truth labels
            y_pred_proba: Predicted probabilities
            y_pred_binary: Binary predictions
            reference_auc: Baseline AUC from training

        Returns:
            DriftReport with performance metrics
        """
        from sklearn.metrics import roc_auc_score

        report_id = f"perf_drift_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
        timestamp = datetime.utcnow().isoformat()

        # Ensure scikit-learn returns native floats
        current_auc = float(roc_auc_score(y_true, y_pred_proba))
        auc_drop = float(reference_auc - current_auc)

        drifted = auc_drop > 0.05  # > 5% drop indicates drift

        alerts = []
        if drifted:
            alerts.append(
                DriftAlert(
                    timestamp=timestamp,
                    feature_name="model_performance",
                    drift_detected=True,
                    drift_type="performance",
                    magnitude=auc_drop,
                    threshold=0.05,
                    reference_value=reference_auc,
                    production_value=current_auc,
                    message=f"AUC dropped from {reference_auc:.4f} to {current_auc:.4f}",
                ).to_dict()
            )

        drift_report = DriftReport(
            report_id=report_id,
            timestamp=timestamp,
            reference_period=f"Training AUC: {reference_auc:.4f}",
            production_period=f"Production AUC: {current_auc:.4f}",
            drifted_features=["model_performance"] if drifted else [],
            data_quality_issues=[],
            alerts=alerts,
            metrics={
                "reference_auc": reference_auc,
                "production_auc": current_auc,
                "auc_drop": auc_drop,
                "performance_drift_detected": drifted,
            },
            alerts_severity="critical" if drifted else "normal",
        )

        return drift_report

    def detect_outliers(
        self,
        production_data: pd.DataFrame,
        sigma_threshold: float = 3.0,
    ) -> DriftReport:
        """
        Detect outliers in production data.

        Args:
            production_data: Production data to analyze
            sigma_threshold: Number of standard deviations for outlier detection

        Returns:
            Report with outlier information
        """
        report_id = f"outliers_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
        timestamp = datetime.utcnow().isoformat()

        outlier_features = []
        outlier_counts = {}

        for col in self.numerical_features:
            if col not in production_data.columns:
                continue

            # Explicitly cast to native Python floats to satisfy static typing
            mean = float(production_data[col].mean())
            std = float(production_data[col].std())

            outliers = np.abs(production_data[col] - mean) > sigma_threshold * std
            outlier_count = int(outliers.sum())
            outlier_pct = float(outlier_count / len(production_data) * 100)

            if outlier_pct > 1.0:  # Flag if > 1% outliers
                outlier_features.append(col)
                outlier_counts[col] = {
                    "count": int(outlier_count),
                    "percentage": float(outlier_pct),
                }

        alerts = []
        for col, stats in outlier_counts.items():
            alerts.append(
                DriftAlert(
                    timestamp=timestamp,
                    feature_name=col,
                    drift_detected=True,
                    drift_type="outlier",
                    magnitude=stats["percentage"],
                    threshold=1.0,
                    message=f"{stats['percentage']:.2f}% outliers detected",
                ).to_dict()
            )

        severity = "critical" if len(outlier_features) > 3 else "medium" if outlier_features else "normal"

        drift_report = DriftReport(
            report_id=report_id,
            timestamp=timestamp,
            reference_period="Historical data",
            production_period=f"Current: {len(production_data)} samples",
            drifted_features=outlier_features,
            data_quality_issues=[f"Outliers in {col}" for col in outlier_features],
            alerts=alerts,
            metrics=outlier_counts,
            alerts_severity=severity,
        )

        return drift_report

    def _extract_drifted_features(self, drift_data: Dict) -> List[str]:
        """Extract list of features with drift detected."""
        drifted = []
        # Parse Evidently drift table metrics
        try:
            drift_table = drift_data.get("data_drift_table", {})
            for metric in drift_table.get("result", {}).get("drift_by_columns", []):
                if metric.get("drift_detected"):
                    drifted.append(metric.get("column_name"))
        except Exception as e:
            logger.warning(f"Error parsing drift table: {e}")

        return drifted

    def _extract_data_quality_issues(self, drift_data: Dict) -> List[str]:
        """Extract data quality issues from report."""
        issues = []
        try:
            quality_table = drift_data.get("data_quality_table", {})
            for col_issue in quality_table.get("result", {}).get("missing_values", []):
                if col_issue.get("missing_percentage", 0) > 1.0:
                    issues.append(f"Missing values in {col_issue.get('column_name')}")
        except Exception as e:
            logger.warning(f"Error parsing quality table: {e}")

        return issues

    def _generate_alerts(
        self,
        drifted_features: List[str],
        data_quality_issues: List[str],
        production_data: pd.DataFrame,
    ) -> Tuple[List[DriftAlert], str]:
        """Generate alerts from drift findings."""
        alerts = []
        timestamp = datetime.utcnow().isoformat()

        # Drift alerts
        for feature in drifted_features:
            alerts.append(
                DriftAlert(
                    timestamp=timestamp,
                    feature_name=feature,
                    drift_detected=True,
                    drift_type="statistical",
                    magnitude=0.0,
                    threshold=self.drift_threshold,
                    message=f"Statistical drift detected in {feature}",
                )
            )

        # Quality alerts
        for issue in data_quality_issues:
            alerts.append(
                DriftAlert(
                    timestamp=timestamp,
                    feature_name=issue.split()[-1],
                    drift_detected=True,
                    drift_type="data_quality",
                    magnitude=0.0,
                    threshold=1.0,
                    message=issue,
                )
            )

        # Determine severity
        if len(drifted_features) > 5 or len(data_quality_issues) > 3:
            severity = "critical"
        elif len(drifted_features) > 2 or data_quality_issues:
            severity = "high"
        else:
            severity = "normal"

        return alerts, severity

    def _extract_summary_metrics(self, drift_data: Dict) -> Dict[str, Any]:
        """Extract key metrics from drift data."""
        metrics = {
            "n_features_drifted": 0,
            "drift_share": 0.0,
            "timestamp": datetime.utcnow().isoformat(),
        }

        try:
            drift_table = drift_data.get("data_drift_table", {})
            result = drift_table.get("result", {})
            n_drifted = len(result.get("drift_by_columns", []))
            n_total = len(result.get("drift_by_columns", [])) or 1

            metrics["n_features_drifted"] = n_drifted
            metrics["drift_share"] = float(n_drifted / n_total) if n_total > 0 else 0.0
        except Exception as e:
            logger.warning(f"Error extracting metrics: {e}")

        return metrics

    def save_report(
        self,
        report: DriftReport,
        output_dir: Path,
        include_html: bool = True,
    ) -> Path:
        """
        Save drift report to JSON (and optional HTML).

        Args:
            report: DriftReport to save
            output_dir: Directory for saved reports
            include_html: Whether to generate HTML report

        Returns:
            Path to saved JSON report
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Save JSON
        json_path = output_dir / f"{report.report_id}.json"
        with open(json_path, "w") as f:
            f.write(report.to_json())

        logger.info(f"Drift report saved: {json_path}")

        return json_path

    def should_retrain(
        self,
        report: DriftReport,
        drift_feature_threshold: int = 3,
    ) -> bool:
        """
        Determine if retraining should be triggered.

        Args:
            report: DriftReport to evaluate
            drift_feature_threshold: Number of drifted features to trigger retrain

        Returns:
            True if retraining recommended
        """
        # Retrain if:
        # 1. Too many drifted features
        # 2. Critical severity
        # 3. Performance drift detected
        return (
            len(report.drifted_features) >= drift_feature_threshold
            or report.alerts_severity == "critical"
            or "model_performance" in report.drifted_features
        )


class ConceptDriftMonitor:
    """Monitor for concept drift (model performance degradation)."""

    def __init__(
        self,
        baseline_metrics: Dict[str, float],
        degradation_threshold: float = 0.05,  # 5% drop
    ):
        """
        Initialize concept drift monitor.

        Args:
            baseline_metrics: Baseline metrics from training (auc, recall, etc.)
            degradation_threshold: Fraction drop to trigger alert
        """
        self.baseline_metrics = baseline_metrics
        self.degradation_threshold = degradation_threshold
        self.history: List[Dict[str, Any]] = []

    def check_metrics(
        self,
        current_metrics: Dict[str, float],
        window_size: int = 100,
    ) -> Tuple[bool, List[str]]:
        """
        Check for concept drift in current metrics.

        Args:
            current_metrics: Current metrics dict
            window_size: Number of recent predictions to consider

        Returns:
            Tuple of (drift_detected, degraded_metrics_list)
        """
        timestamp = datetime.utcnow().isoformat()
        degraded_metrics = []

        for metric_name, baseline_value in self.baseline_metrics.items():
            if metric_name not in current_metrics:
                continue

            current_value = current_metrics[metric_name]
            degradation = baseline_value - current_value

            if degradation > baseline_value * self.degradation_threshold:
                degraded_metrics.append(
                    f"{metric_name}: {baseline_value:.4f} → {current_value:.4f} ({degradation:.1%})"
                )

        # Record in history
        self.history.append({
            "timestamp": timestamp,
            "metrics": current_metrics,
            "degradations": degraded_metrics,
        })

        drift_detected = len(degraded_metrics) > 0
        return drift_detected, degraded_metrics

    def get_drift_history(self, days: int = 7) -> List[Dict[str, Any]]:
        """Get drift events from last N days."""
        cutoff = datetime.utcnow() - timedelta(days=days)
        return [
            h for h in self.history
            if datetime.fromisoformat(h["timestamp"]) > cutoff
        ]


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    if HAS_EVIDENTLY:
        # Example usage
        np.random.seed(42)

        # Create reference data
        reference_data = pd.DataFrame({
            "feature_1": np.random.normal(0, 1, 1000),
            "feature_2": np.random.normal(0, 1, 1000),
            "feature_3": np.random.normal(0, 1, 1000),
        })

        # Create detector
        detector = EvidentiallyDriftDetector(
            reference_data=reference_data,
            feature_names=["feature_1", "feature_2", "feature_3"],
            numerical_features=["feature_1", "feature_2", "feature_3"],
        )

        # Create production data with drift in feature_1
        production_data = pd.DataFrame({
            "feature_1": np.random.normal(0.5, 1.5, 500),  # Drifted
            "feature_2": np.random.normal(0, 1, 500),
            "feature_3": np.random.normal(0, 1, 500),
        })

        # Detect drift
        report = detector.detect_data_drift(production_data)
        print(json.dumps(report.to_dict(), indent=2, default=str))

        # Save report
        detector.save_report(report, Path("backend/data/drift_reports"))
    else:
        print("Evidently AI not installed. Install with: pip install evidently")
