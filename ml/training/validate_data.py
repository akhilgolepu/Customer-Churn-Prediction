"""DVC stage `validate_data`: check the raw training CSV against TRAINING_SCHEMA.

Writes reports/data_validation.json and exits non-zero when the data fails,
so `dvc repro` stops before training on bad data.

Usage:
    python ml/training/validate_data.py [--data PATH]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import REPO_ROOT, load_params  # noqa: E402

from ml.data_schema import TRAINING_SCHEMA, load_raw_training_csv, validate_frame  # noqa: E402

OUT_PATH = REPO_ROOT / "reports" / "data_validation.json"


def main(data_path: Path | None) -> int:
    params = load_params()
    path = data_path or (REPO_ROOT / params["data"]["path"])
    df = load_raw_training_csv(path)
    errors = validate_frame(df, TRAINING_SCHEMA)
    target = params["data"]["target"]
    report = {
        "data_path": str(path.relative_to(REPO_ROOT) if path.is_relative_to(REPO_ROOT) else path).replace("\\", "/"),
        "md5": hashlib.md5(path.read_bytes(), usedforsecurity=False).hexdigest(),
        "rows": int(len(df)),
        "columns": int(df.shape[1]),
        "positive_rate": float((df[target] == params["data"]["positive_label"]).mean()) if target in df else None,
        "blank_total_charges": int(df["TotalCharges"].isna().sum()) if "TotalCharges" in df else None,
        "valid": not errors,
        "errors": errors,
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "errors"}, indent=2))
    if errors:
        print("Data validation FAILED:\n  " + "\n  ".join(errors), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=None)
    sys.exit(main(parser.parse_args().data))
