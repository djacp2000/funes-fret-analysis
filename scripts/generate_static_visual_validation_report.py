"""Generate the focused static visual validation report from a source checkout."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from funes.real_data_validation import (  # noqa: E402
    RealPairValidationConfig,
    run_real_pair_validation,
)
from funes.static_validation_report import (  # noqa: E402
    export_static_visual_validation_report,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate a static, non-production visual validation report."
    )
    parser.add_argument("input_dir", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--experiment", default="Static Visual Validation")
    parser.add_argument("--capture", default="Capture 1")
    parser.add_argument("--position", default="Position 1")
    args = parser.parse_args()

    validation = run_real_pair_validation(
        args.input_dir,
        args.output_dir,
        RealPairValidationConfig(
            experiment_label=args.experiment,
            capture=args.capture,
            position=args.position,
        ),
        export_workbook=False,
    )
    report = export_static_visual_validation_report(validation, args.output_dir)
    print(f"Report: {report.report_path}")
    print(f"Manifest: {report.manifest_path}")
    print(
        "Classification: "
        f"segmented={report.segmented_components}, "
        f"geometry_retained={report.geometry_retained_rois}, "
        f"geometry_rejected={report.geometry_rejected_rois}, "
        f"intensity_excluded={report.intensity_excluded_rois}"
    )
    print(f"Ratio range: {report.ratio_minimum:.6f}..{report.ratio_maximum:.6f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
