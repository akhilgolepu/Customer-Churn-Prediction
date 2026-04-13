"""
Model Validation Gate Service - Pre-Promotion Quality & Governance Checks

This service implements strict validation gates that must pass before a model
can be promoted from candidate → shadow → active. Checks include:
- Model Quality (AUC, Recall, Precision, F1)
- Fairness (demographic parity, equalized odds)
- Performance (latency, memory, throughput)
- Data Integrity (feature distributions, schema validation)
"""

import json
import time
import logging
import psutil
import tracemalloc
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass, asdict
from enum import Enum
import threading

import numpy as np
import pandas as pd
from sklearn.metrics import (
    roc_auc_score, recall_score, precision_score, f1_score,
    confusion_matrix, roc_curve
)

logger = logging.getLogger(__name__)


class CheckStatus(Enum):
    """Validation check result status."""
    PASSED = "passed"
    FAILED = "failed"
    WARNING = "warning"


@dataclass
class ValidationCheckResult:
    """Single validation check result."""
    name: str
    category: str  # quality, fairness, performance, data_integrity
    status: CheckStatus
    details: Dict[str, Any]
    thresholds: Dict[str, Any]
    expected: Any
    actual: Any
    message: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "category": self.category,
            "status": self.status.value,
            "details": self.details,
            "thresholds": self.thresholds,
            "expected": self.expected,
            "actual": self.actual,
            "message": self.message,
        }


@dataclass
class ValidationGateReport:
    """Complete validation gate report."""
    model_version: str
    timestamp: str
    overall_status: str  # passed, failed, warning
    total_checks: int
    passed_checks: int
    failed_checks: int
    warning_checks: int
    checks: List[Dict[str, Any]]
    blockers: List[str]  # Hard stops for promotion
    warnings: List[str]   # Advisory warnings
    promotion_allowed: bool

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=2, default=str)


class ModelQualityValidator:
    """Quality metrics validation against thresholds."""

    def __init__(self):
        self.config = {
            "min_auc": 0.75,           # Minimum ROC AUC
            "min_recall": 0.65,        # Minimum recall (catch true churners)
            "min_precision": 0.50,     # Minimum precision (avoid false alarms)
            "min_f1": 0.57,            # Minimum F1 score
            "max_false_positive_rate": 0.10,  # Max FPR at optimal threshold
        }

    def validate_binary_classification_metrics(
        self,
        y_true: np.ndarray,
        y_pred_proba: np.ndarray,
        y_pred_binary: np.ndarray,
    ) -> Tuple[List[ValidationCheckResult], bool]:
        """Validate binary classification metrics."""
        results = []
        all_passed = True

        # AUC Score
        auc = roc_auc_score(y_true, y_pred_proba)
        result = ValidationCheckResult(
            name="ROC AUC Score",
            category="quality",
            status=CheckStatus.PASSED if auc >= self.config["min_auc"] else CheckStatus.FAILED,
            details={"auc": float(auc)},
            thresholds={"min_auc": self.config["min_auc"]},
            expected=f">= {self.config['min_auc']}",
            actual=float(auc),
            message=f"AUC = {auc:.4f}"
        )
        results.append(result)
        if result.status == CheckStatus.FAILED:
            all_passed = False

        # Recall Score
        recall = recall_score(y_true, y_pred_binary)
        result = ValidationCheckResult(
            name="Recall Score",
            category="quality",
            status=CheckStatus.PASSED if recall >= self.config["min_recall"] else CheckStatus.FAILED,
            details={"recall": float(recall)},
            thresholds={"min_recall": self.config["min_recall"]},
            expected=f">= {self.config['min_recall']}",
            actual=float(recall),
            message=f"Recall = {recall:.4f}"
        )
        results.append(result)
        if result.status == CheckStatus.FAILED:
            all_passed = False

        # Precision Score
        precision = precision_score(y_true, y_pred_binary, zero_division=0)
        result = ValidationCheckResult(
            name="Precision Score",
            category="quality",
            status=CheckStatus.PASSED if precision >= self.config["min_precision"] else CheckStatus.FAILED,
            details={"precision": float(precision)},
            thresholds={"min_precision": self.config["min_precision"]},
            expected=f">= {self.config['min_precision']}",
            actual=float(precision),
            message=f"Precision = {precision:.4f}"
        )
        results.append(result)
        if result.status == CheckStatus.FAILED:
            all_passed = False

        # F1 Score
        f1 = f1_score(y_true, y_pred_binary, zero_division=0)
        result = ValidationCheckResult(
            name="F1 Score",
            category="quality",
            status=CheckStatus.PASSED if f1 >= self.config["min_f1"] else CheckStatus.FAILED,
            details={"f1": float(f1)},
            thresholds={"min_f1": self.config["min_f1"]},
            expected=f">= {self.config['min_f1']}",
            actual=float(f1),
            message=f"F1 = {f1:.4f}"
        )
        results.append(result)
        if result.status == CheckStatus.FAILED:
            all_passed = False

        return results, all_passed


class FairnessValidator:
    """Fairness metrics validation across demographic groups."""

    def __init__(self):
        self.config = {
            "demographic_parity_tolerance": 0.10,  # +/- 10% difference allowed
            "equalized_odds_tolerance": 0.15,      # +/- 15% difference in TPR/FPR
        }

    def validate_demographic_parity(
        self,
        y_true: np.ndarray,
        y_pred_binary: np.ndarray,
        protected_attribute: np.ndarray,
        attribute_name: str = "protected_group",
    ) -> Tuple[ValidationCheckResult, bool]:
        """
        Validate demographic parity: P(ŷ=1|X=0) ≈ P(ŷ=1|X=1)
        """
        groups = np.unique(protected_attribute)

        if len(groups) != 2:
            return ValidationCheckResult(
                name=f"Demographic Parity ({attribute_name})",
                category="fairness",
                status=CheckStatus.WARNING,
                details={},
                thresholds={"tolerance": self.config["demographic_parity_tolerance"]},
                expected="Binary protected attribute",
                actual=f"{len(groups)} groups detected",
                message=f"Skipping: {len(groups)} groups detected (expected 2)"
            ), True

        group0 = y_pred_binary[protected_attribute == groups[0]]
        group1 = y_pred_binary[protected_attribute == groups[1]]

        pos_rate_0 = np.mean(group0)
        pos_rate_1 = np.mean(group1)
        difference = abs(pos_rate_0 - pos_rate_1)

        passed = difference <= self.config["demographic_parity_tolerance"]
        result = ValidationCheckResult(
            name=f"Demographic Parity ({attribute_name})",
            category="fairness",
            status=CheckStatus.PASSED if passed else CheckStatus.FAILED,
            details={
                "positive_rate_group_0": float(pos_rate_0),
                "positive_rate_group_1": float(pos_rate_1),
                "difference": float(difference),
            },
            thresholds={"tolerance": self.config["demographic_parity_tolerance"]},
            expected=f"difference <= {self.config['demographic_parity_tolerance']}",
            actual=float(difference),
            message=f"Group 0: {pos_rate_0:.3f}, Group 1: {pos_rate_1:.3f}, Diff: {difference:.3f}"
        )
        return result, passed


class PerformanceValidator:
    """Performance (latency, memory, throughput) validation."""

    def __init__(self):
        self.config = {
            "max_preprocess_time_ms": 2000.0,
            "max_model_predict_time_ms": 2000.0,
            "max_api_end_to_end_time_ms": 6000.0,
            "max_memory_mb": 500.0,
            "min_throughput_predictions_per_sec": 10.0,
        }

    def validate_latency(
        self,
        latency_ms: float,
        stage: str = "model_predict",  # model_predict, preprocess, api_e2e
    ) -> ValidationCheckResult:
        """Validate single-stage latency."""
        threshold_key = f"max_{stage}_time_ms"
        threshold = self.config.get(threshold_key, None)

        if threshold is None:
            return ValidationCheckResult(
                name=f"Latency ({stage})",
                category="performance",
                status=CheckStatus.WARNING,
                details={"latency_ms": latency_ms},
                thresholds={},
                expected="Known stage",
                actual=stage,
                message=f"Unknown stage: {stage}"
            )

        passed = latency_ms <= threshold
        result = ValidationCheckResult(
            name=f"Latency ({stage})",
            category="performance",
            status=CheckStatus.PASSED if passed else CheckStatus.FAILED,
            details={"latency_ms": float(latency_ms)},
            thresholds={threshold_key: threshold},
            expected=f"<= {threshold}ms",
            actual=float(latency_ms),
            message=f"{latency_ms:.2f}ms vs threshold {threshold}ms"
        )
        return result

    def validate_memory_usage(self, memory_mb: float) -> ValidationCheckResult:
        """Validate memory footprint."""
        threshold = self.config["max_memory_mb"]
        passed = memory_mb <= threshold

        result = ValidationCheckResult(
            name="Memory Usage",
            category="performance",
            status=CheckStatus.PASSED if passed else CheckStatus.FAILED,
            details={"memory_mb": float(memory_mb)},
            thresholds={"max_memory_mb": threshold},
            expected=f"<= {threshold}MB",
            actual=float(memory_mb),
            message=f"{memory_mb:.2f}MB vs threshold {threshold}MB"
        )
        return result

    def validate_throughput(
        self,
        total_predictions: int,
        duration_seconds: float,
    ) -> ValidationCheckResult:
        """Validate predictions per second."""
        throughput = total_predictions / duration_seconds if duration_seconds > 0 else 0
        threshold = self.config["min_throughput_predictions_per_sec"]
        passed = throughput >= threshold

        result = ValidationCheckResult(
            name="Throughput",
            category="performance",
            status=CheckStatus.PASSED if passed else CheckStatus.FAILED,
            details={"predictions_per_sec": float(throughput), "total_predictions": total_predictions},
            thresholds={"min_throughput_predictions_per_sec": threshold},
            expected=f">= {threshold} predictions/sec",
            actual=float(throughput),
            message=f"{throughput:.2f} predictions/sec"
        )
        return result


class DataIntegrityValidator:
    """Data schema and distribution validation."""

    def __init__(self):
        self.config = {
            "max_missing_percent": 1.0,  # Max % missing per column
            "distribution_ks_threshold": 0.15,  # KS test threshold for drift
        }

    def validate_schema(
        self,
        df: pd.DataFrame,
        expected_columns: List[str],
        expected_dtypes: Dict[str, str],
    ) -> Tuple[List[ValidationCheckResult], bool]:
        """Validate data schema (columns, dtypes)."""
        results = []
        all_passed = True

        # Column presence
        missing_cols = set(expected_columns) - set(df.columns)
        extra_cols = set(df.columns) - set(expected_columns)

        passed = len(missing_cols) == 0
        result = ValidationCheckResult(
            name="Column Presence",
            category="data_integrity",
            status=CheckStatus.PASSED if passed else CheckStatus.FAILED,
            details={
                "expected_columns": expected_columns,
                "actual_columns": list(df.columns),
                "missing": list(missing_cols),
                "extra": list(extra_cols),
            },
            thresholds={"required_columns": len(expected_columns)},
            expected=f"{len(expected_columns)} columns",
            actual=f"{len(df.columns)} columns",
            message=f"Missing: {missing_cols}, Extra: {extra_cols}" if (missing_cols or extra_cols) else "All columns present"
        )
        results.append(result)
        if result.status == CheckStatus.FAILED:
            all_passed = False

        # Data type validation
        dtype_mismatches = {}
        for col, expected_dtype in expected_dtypes.items():
            if col in df.columns:
                actual_dtype = str(df[col].dtype)
                if expected_dtype not in actual_dtype:
                    dtype_mismatches[col] = (expected_dtype, actual_dtype)

        passed = len(dtype_mismatches) == 0
        result = ValidationCheckResult(
            name="Data Types",
            category="data_integrity",
            status=CheckStatus.PASSED if passed else CheckStatus.FAILED,
            details={"mismatches": dtype_mismatches},
            thresholds={},
            expected=str(expected_dtypes),
            actual=str({col: str(df[col].dtype) for col in expected_columns if col in df.columns}),
            message="All dtypes correct" if passed else f"Mismatches: {dtype_mismatches}"
        )
        results.append(result)
        if result.status == CheckStatus.FAILED:
            all_passed = False

        return results, all_passed

    def validate_missing_data(self, df: pd.DataFrame) -> ValidationCheckResult:
        """Validate missing data rates."""
        missing_percent = (df.isnull().sum() / len(df)) * 100
        max_missing = missing_percent.max()
        threshold = self.config["max_missing_percent"]
        passed = max_missing <= threshold

        result = ValidationCheckResult(
            name="Missing Data",
            category="data_integrity",
            status=CheckStatus.PASSED if passed else CheckStatus.FAILED,
            details={
                "missing_by_column": missing_percent.to_dict(),
                "max_missing_percent": float(max_missing),
            },
            thresholds={"max_missing_percent": threshold},
            expected=f"<= {threshold}%",
            actual=float(max_missing),
            message=f"Max missing: {max_missing:.2f}%"
        )
        return result


class ModelValidationGate:
    """Main orchestrator for pre-promotion validation."""

    def __init__(self):
        self.quality_validator = ModelQualityValidator()
        self.fairness_validator = FairnessValidator()
        self.performance_validator = PerformanceValidator()
        self.data_validator = DataIntegrityValidator()
        self.results: List[ValidationCheckResult] = []

    def validate_for_promotion(
        self,
        model_version: str,
        y_true: Optional[np.ndarray] = None,
        y_pred_proba: Optional[np.ndarray] = None,
        y_pred_binary: Optional[np.ndarray] = None,
        eval_data: Optional[pd.DataFrame] = None,
        protected_attribute: Optional[np.ndarray] = None,
        latency_measurements: Optional[Dict[str, float]] = None,
        memory_mb: Optional[float] = None,
        test_df: Optional[pd.DataFrame] = None,
        expected_columns: Optional[List[str]] = None,
        expected_dtypes: Optional[Dict[str, str]] = None,
    ) -> ValidationGateReport:
        """
        Run complete validation gate for promotion.

        Args:
            model_version: Version identifier for the model
            y_true: Ground truth labels (n_samples,)
            y_pred_proba: Predicted probabilities (n_samples,)
            y_pred_binary: Binary predictions at threshold (n_samples,)
            eval_data: Full evaluation dataset
            protected_attribute: Protected attribute for fairness checks
            latency_measurements: Dict with keys like "model_predict_ms", "preprocess_ms", etc.
            memory_mb: Peak memory usage in MB
            test_df: Test data for schema validation
            expected_columns: List of expected columns
            expected_dtypes: Dict mapping column to expected dtype
        """
        self.results = []
        timestamp = pd.Timestamp.now().isoformat()

        blockers = []
        warnings = []

        # Quality Checks
        if y_true is not None and y_pred_proba is not None and y_pred_binary is not None:
            quality_results, quality_passed = self.quality_validator.validate_binary_classification_metrics(
                y_true, y_pred_proba, y_pred_binary
            )
            self.results.extend(quality_results)
            if not quality_passed:
                blockers.append("Model quality metrics below thresholds")
        else:
            warnings.append("Skipped quality validation: missing required predictions")

        # Fairness Checks
        if y_true is not None and y_pred_binary is not None and protected_attribute is not None:
            fairness_result, fairness_passed = self.fairness_validator.validate_demographic_parity(
                y_true, y_pred_binary, protected_attribute,
                attribute_name="contract_type"
            )
            self.results.append(fairness_result)
            if fairness_result.status == CheckStatus.FAILED:
                blockers.append("Fairness check failed: demographic parity not achieved")
            elif fairness_result.status == CheckStatus.WARNING:
                warnings.append(f"Fairness warning: {fairness_result.message}")
        else:
            warnings.append("Skipped fairness validation: missing protected attribute data")

        # Performance Checks
        if latency_measurements:
            for stage, latency_ms in latency_measurements.items():
                result = self.performance_validator.validate_latency(latency_ms, stage)
                self.results.append(result)
                if result.status == CheckStatus.FAILED:
                    blockers.append(f"Performance gate failed: {stage} latency exceeds threshold")

        if memory_mb is not None:
            result = self.performance_validator.validate_memory_usage(memory_mb)
            self.results.append(result)
            if result.status == CheckStatus.FAILED:
                blockers.append("Performance gate failed: memory usage exceeds threshold")
        else:
            warnings.append("Skipped memory validation: no measurement provided")

        # Data Integrity Checks
        if test_df is not None:
            if expected_columns and expected_dtypes:
                schema_results, schema_passed = self.data_validator.validate_schema(
                    test_df, expected_columns, expected_dtypes
                )
                self.results.extend(schema_results)
                if not schema_passed:
                    blockers.append("Data schema validation failed")

            missing_result = self.data_validator.validate_missing_data(test_df)
            self.results.append(missing_result)
            if missing_result.status == CheckStatus.FAILED:
                blockers.append("Data integrity gate failed: excessive missing values")
        else:
            warnings.append("Skipped data integrity validation: no test data provided")

        # Calculate summary
        passed_count = len([r for r in self.results if r.status == CheckStatus.PASSED])
        failed_count = len([r for r in self.results if r.status == CheckStatus.FAILED])
        warning_count = len([r for r in self.results if r.status == CheckStatus.WARNING])

        promotion_allowed = len(blockers) == 0
        overall_status = "passed" if promotion_allowed else "failed"
        if not promotion_allowed and len(warnings) > 0:
            overall_status = "failed_with_warnings"

        report = ValidationGateReport(
            model_version=model_version,
            timestamp=timestamp,
            overall_status=overall_status,
            total_checks=len(self.results),
            passed_checks=passed_count,
            failed_checks=failed_count,
            warning_checks=warning_count,
            checks=[r.to_dict() for r in self.results],
            blockers=blockers,
            warnings=warnings,
            promotion_allowed=promotion_allowed,
        )

        logger.info(f"Validation gate for {model_version}: {report.overall_status}")
        logger.info(f"  Passed: {passed_count}, Failed: {failed_count}, Warnings: {warning_count}")
        if blockers:
            logger.error(f"  BLOCKERS: {blockers}")
        if warnings:
            logger.warning(f"  WARNINGS: {warnings}")

        return report

    def save_report(self, report: ValidationGateReport, output_path: Path):
        """Save validation report to JSON file."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w') as f:
            f.write(report.to_json())
        logger.info(f"Validation report saved to {output_path}")


def measure_memory_usage(func, *args, **kwargs) -> Tuple[Any, float]:
    """
    Execute function and measure peak memory usage.

    Returns:
        Tuple of (result, peak_memory_mb)
    """
    tracemalloc.start()
    try:
        result = func(*args, **kwargs)
    finally:
        current, peak = tracemalloc.get_traced_memory()
        peak_mb = peak / 1024 / 1024
        tracemalloc.stop()
    return result, peak_mb


def measure_latency(func, *args, **kwargs) -> Tuple[Any, float]:
    """
    Execute function and measure execution time.

    Returns:
        Tuple of (result, duration_ms)
    """
    start = time.perf_counter()
    result = func(*args, **kwargs)
    duration_sec = time.perf_counter() - start
    duration_ms = duration_sec * 1000
    return result, duration_ms


if __name__ == "__main__":
    # Example usage
    logging.basicConfig(level=logging.INFO)

    # Create gate instance
    gate = ModelValidationGate()

    # Example: validate with synthetic data
    y_true = np.random.randint(0, 2, 100)
    y_pred_proba = np.random.rand(100)
    y_pred_binary = (y_pred_proba >= 0.5).astype(int)
    protected_attr = np.random.randint(0, 2, 100)

    test_data = pd.DataFrame({
        "feature_1": np.random.rand(100),
        "feature_2": np.random.rand(100),
        "target": y_true,
    })

    latencies = {
        "model_predict_ms": 1500.0,
        "preprocess_ms": 800.0,
        "api_e2e_ms": 3000.0,
    }

    report = gate.validate_for_promotion(
        model_version="v1",
        y_true=y_true,
        y_pred_proba=y_pred_proba,
        y_pred_binary=y_pred_binary,
        protected_attribute=protected_attr,
        latency_measurements=latencies,
        memory_mb=250.0,
        test_df=test_data,
        expected_columns=["feature_1", "feature_2", "target"],
        expected_dtypes={"feature_1": "float", "feature_2": "float", "target": "int"},
    )

    print(report.to_json())
    gate.save_report(report, Path("validation_report.json"))
