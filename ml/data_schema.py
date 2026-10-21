"""Data validation for raw Telco customer rows, shared by training and the API.

One rule table (CONSISTENCY_RULES) is rendered two ways:
  * pandera checks inside FEATURE_SCHEMA / TRAINING_SCHEMA, used for the
    training data (DVC stage validate_data) and for batch-scoring files;
  * consistency_errors(record), a plain-Python version used by the /predict
    request model. Pandera costs about 24 ms per call however small the frame
    (measured on one row; 57 ms for all 7,043 rows), which is too much for a
    single request whose whole p95 was 41 ms. A test checks both renderings
    agree.

FEATURE_SCHEMA  model input columns: value domains + cross-field consistency.
TRAINING_SCHEMA plus unique customerID, gender, Churn label, blank TotalCharges
                only at tenure 0, sanity ranges; no unexpected columns.
"""

from __future__ import annotations

import pandas as pd
import pandera.pandas as pa

YES_NO = ["Yes", "No"]
INTERNET_ADDONS = ["OnlineSecurity", "OnlineBackup", "DeviceProtection", "TechSupport", "StreamingTV", "StreamingMovies"]
PAYMENT_METHODS = ["Electronic check", "Mailed check", "Bank transfer (automatic)", "Credit card (automatic)"]

# (trigger column, trigger value, dependent columns, dependent value):
# trigger == value  <=>  every dependent column == dependent value
CONSISTENCY_RULES = [
    ("PhoneService", "No", ["MultipleLines"], "No phone service"),
    ("InternetService", "No", INTERNET_ADDONS, "No internet service"),
]


def _rule_message(trigger, value, dependents, dep_value) -> str:
    return f"{trigger}={value!r} must coincide with {'/'.join(dependents)}={dep_value!r}"


def consistency_errors(record: dict) -> list[str]:
    """Plain-Python rendering of CONSISTENCY_RULES for a single record."""
    errors = []
    for trigger, value, dependents, dep_value in CONSISTENCY_RULES:
        is_trigger = record.get(trigger) == value
        if any((record.get(col) == dep_value) != is_trigger for col in dependents):
            errors.append(_rule_message(trigger, value, dependents, dep_value))
    return errors


def _rule_check(trigger, value, dependents, dep_value) -> pa.Check:
    def check(df: pd.DataFrame) -> pd.Series:
        is_trigger = df[trigger] == value
        ok = pd.Series(True, index=df.index)
        for col in dependents:
            ok &= (df[col] == dep_value) == is_trigger
        return ok

    return pa.Check(check, error=_rule_message(trigger, value, dependents, dep_value))


_CONSISTENCY_CHECKS = [_rule_check(*rule) for rule in CONSISTENCY_RULES]


def _feature_columns(numeric_ranges: bool) -> dict:
    tenure_checks = [pa.Check.ge(0)] + ([pa.Check.le(120)] if numeric_ranges else [])
    monthly_checks = [pa.Check.gt(0)] + ([pa.Check.le(500)] if numeric_ranges else [])
    columns = {
        "SeniorCitizen": pa.Column(int, pa.Check.isin([0, 1]), coerce=True),
        "Partner": pa.Column(str, pa.Check.isin(YES_NO)),
        "Dependents": pa.Column(str, pa.Check.isin(YES_NO)),
        "tenure": pa.Column(int, tenure_checks, coerce=True),
        "PhoneService": pa.Column(str, pa.Check.isin(YES_NO)),
        "MultipleLines": pa.Column(str, pa.Check.isin(["Yes", "No", "No phone service"])),
        "InternetService": pa.Column(str, pa.Check.isin(["DSL", "Fiber optic", "No"])),
        "Contract": pa.Column(str, pa.Check.isin(["Month-to-month", "One year", "Two year"])),
        "PaperlessBilling": pa.Column(str, pa.Check.isin(YES_NO)),
        "PaymentMethod": pa.Column(str, pa.Check.isin(PAYMENT_METHODS)),
        "MonthlyCharges": pa.Column(float, monthly_checks, coerce=True),
        "TotalCharges": pa.Column(float, pa.Check.ge(0), coerce=True, nullable=True),
    }
    for col in INTERNET_ADDONS:
        columns[col] = pa.Column(str, pa.Check.isin(["Yes", "No", "No internet service"]))
    return columns


# Batch files: domains + consistency. No upper ranges and no TotalCharges/tenure
# rule, so customers outside the training range are still scored.
FEATURE_SCHEMA = pa.DataFrameSchema(
    _feature_columns(numeric_ranges=False), checks=_CONSISTENCY_CHECKS, strict=False, name="churn_features"
)

TRAINING_SCHEMA = pa.DataFrameSchema(
    {
        **_feature_columns(numeric_ranges=True),
        "customerID": pa.Column(str, unique=True),
        "gender": pa.Column(str, pa.Check.isin(["Female", "Male"])),
        "Churn": pa.Column(str, pa.Check.isin(YES_NO)),
    },
    checks=_CONSISTENCY_CHECKS + [
        pa.Check(lambda df: df["TotalCharges"].notna() | (df["tenure"] == 0),
                 error="blank TotalCharges is only allowed at tenure 0"),
    ],
    strict=True,
    name="churn_training_rows",
)


def validate_frame(frame: pd.DataFrame, schema: pa.DataFrameSchema = FEATURE_SCHEMA, max_errors: int = 50) -> list[str]:
    """Readable error strings for every failing check (empty list when valid).

    Row numbers are 0-based positions in the frame. A failed cross-field check
    is reported once per row, not once per column.
    """
    try:
        schema.validate(frame, lazy=True)
    except pa.errors.SchemaErrors as exc:
        messages: list[str] = []
        seen: set[tuple] = set()
        key: tuple
        for _, case in exc.failure_cases.iterrows():
            row = f"row {int(case['index'])}" if pd.notna(case.get("index")) else "frame"
            if row == "frame":  # schema-level, e.g. a missing or unexpected column
                key = (row, case["check"], str(case["failure_case"]))
                text = f"frame: failed {case['check']} ({case['failure_case']!r})"
            elif case.get("schema_context") == "DataFrameSchema":
                key = (row, case["check"])
                text = f"{row}: {case['check']}"
            else:
                key = (row, case["column"], case["check"])
                text = f"{row}, column {case['column']}: failed {case['check']} (value: {case['failure_case']!r})"
            if key not in seen:
                seen.add(key)
                messages.append(text)
        if len(messages) > max_errors:
            return messages[:max_errors] + [f"... and {len(messages) - max_errors} more"]
        return messages
    return []


def load_raw_training_csv(path) -> pd.DataFrame:
    """Read the Telco CSV the way training does: TotalCharges blanks become NaN."""
    df = pd.read_csv(path)
    df["TotalCharges"] = pd.to_numeric(df["TotalCharges"], errors="coerce")
    return df
