"""Run the focused real-pair integration validation from a source checkout."""

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


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate one real C0/C1 pair through the Module 14 workbook boundary."
    )
    parser.add_argument("input_dir", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--experiment", required=True)
    parser.add_argument("--capture", required=True)
    parser.add_argument("--position", required=True)
    args = parser.parse_args()

    result = run_real_pair_validation(
        args.input_dir,
        args.output_dir,
        RealPairValidationConfig(
            experiment_label=args.experiment,
            capture=args.capture,
            position=args.position,
        ),
    )
    print(f"Selected segmentation channel: {result.selected_channel.selected_channel.value}")
    print(
        "ROIs: "
        f"segmented={result.segmentation.roi_count}, "
        f"retained={result.roi_filtering.accepted_count}, "
        f"rejected={result.roi_filtering.rejected_count}"
    )
    for workbook in result.export.workbook_paths:
        print(f"Workbook: {workbook}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
