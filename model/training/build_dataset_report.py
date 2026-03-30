from __future__ import annotations

from pathlib import Path

from dataset_registry import DatasetProfiler, DatasetRegistry


def build_report(output_path: Path) -> None:
    registry = DatasetRegistry()
    issues = registry.validate()
    profiler = DatasetProfiler(registry)
    summaries = profiler.summarize_all()

    lines: list[str] = []
    lines.append("# Dataset Expansion Report")
    lines.append("")
    lines.append("This report helps track multi-dataset readiness while preserving the current production model.")
    lines.append("")

    if issues:
        lines.append("## Validation Issues")
        lines.append("")
        for issue in issues:
            lines.append(f"- {issue}")
        lines.append("")
    else:
        lines.append("## Validation")
        lines.append("")
        lines.append("- All active datasets are available on disk.")
        lines.append("")

    lines.append("## Dataset Inventory")
    lines.append("")

    for item in summaries:
        lines.append(f"### {item['name']} ({item['id']})")
        lines.append("")
        lines.append(f"- Status: {item['status']}")
        lines.append(f"- Present: {item['present']}")
        lines.append(f"- Path: {item['path']}")

        if item.get("present"):
            lines.append(f"- Rows: {item.get('rows', 'n/a')}")
            lines.append(f"- Columns: {item.get('columns', 'n/a')}")
            lines.append(f"- Target present: {item.get('target_present')}")
            if item.get("target_present"):
                lines.append(f"- Target column: {item.get('target_column')}")
                lines.append(f"- Positive label: {item.get('positive_label')}")
                lines.append(f"- Churn rate: {item.get('churn_rate')}")
            if item.get("issue"):
                lines.append(f"- Issue: {item.get('issue')}")
        lines.append("")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[2]
    report_path = root / "data" / "dataset_report.md"
    build_report(report_path)
    print(f"Dataset report generated: {report_path}")
