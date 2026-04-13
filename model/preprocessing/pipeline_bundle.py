from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import zipfile

from model.preprocessing.preprocessing import build_preprocessing_spec


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(8192), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_pipeline_bundle(
    model_path: Path,
    feature_list_path: Path,
    cat_columns_path: Path,
    output_dir: Path,
    version: str,
) -> Path:
    model_path = model_path.resolve()
    feature_list_path = feature_list_path.resolve()
    cat_columns_path = cat_columns_path.resolve()
    output_dir = output_dir.resolve()

    for required in (model_path, feature_list_path, cat_columns_path):
        if not required.exists():
            raise FileNotFoundError(f"Required artifact is missing: {required}")

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_dir.mkdir(parents=True, exist_ok=True)
    bundle_path = output_dir / f"churn_pipeline_{version}_{timestamp}.zip"

    preprocessing_spec = build_preprocessing_spec()
    preprocessing_spec_bytes = json.dumps(preprocessing_spec, indent=2).encode("utf-8")
    preprocessing_spec_hash = hashlib.sha256(preprocessing_spec_bytes).hexdigest()

    files_manifest = [
        {
            "path": "model/model.cbm",
            "sha256": _sha256_file(model_path),
        },
        {
            "path": "preprocessing/feature_list.json",
            "sha256": _sha256_file(feature_list_path),
        },
        {
            "path": "preprocessing/cat_columns.json",
            "sha256": _sha256_file(cat_columns_path),
        },
        {
            "path": "preprocessing/preprocessing_spec.json",
            "sha256": preprocessing_spec_hash,
        },
    ]

    manifest = {
        "artifact_format": "churn_pipeline_bundle/v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "model_version": version,
        "files": files_manifest,
    }

    with zipfile.ZipFile(bundle_path, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.write(model_path, arcname="model/model.cbm")
        zf.write(feature_list_path, arcname="preprocessing/feature_list.json")
        zf.write(cat_columns_path, arcname="preprocessing/cat_columns.json")
        zf.writestr("preprocessing/preprocessing_spec.json", preprocessing_spec_bytes)
        zf.writestr("manifest.json", json.dumps(manifest, indent=2).encode("utf-8"))

    return bundle_path


def parse_args() -> argparse.Namespace:
    repo_root = Path(__file__).resolve().parents[2]
    default_artifacts = repo_root / "model" / "artifacts"

    parser = argparse.ArgumentParser(
        description="Build a reproducible pipeline bundle containing model + preprocessing artifacts."
    )
    parser.add_argument("--version", required=True, help="Model/pipeline version label (example: v2).")
    parser.add_argument(
        "--model-path",
        type=Path,
        default=default_artifacts / "catboost_churn.cbm",
        help="Path to trained model artifact (.cbm).",
    )
    parser.add_argument(
        "--feature-list-path",
        type=Path,
        default=default_artifacts / "feature_list.json",
        help="Path to feature list JSON.",
    )
    parser.add_argument(
        "--cat-columns-path",
        type=Path,
        default=default_artifacts / "cat_columns.json",
        help="Path to categorical columns JSON.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=default_artifacts / "bundles",
        help="Directory where bundle zip will be written.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    out = build_pipeline_bundle(
        model_path=args.model_path,
        feature_list_path=args.feature_list_path,
        cat_columns_path=args.cat_columns_path,
        output_dir=args.output_dir,
        version=args.version,
    )
    print(f"Pipeline bundle created: {out}")
