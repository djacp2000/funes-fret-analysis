"""Run FUNES's provisional automatic TIFF-to-Excel route."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from funes.simple_analysis import SimpleAnalysisError, run_simple_fret_analysis


def main() -> int:
    parser = argparse.ArgumentParser(description="Run provisional automatic C0/C1 FRET analysis.")
    parser.add_argument("input_dir", type=Path)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    try:
        result = run_simple_fret_analysis(args.input_dir, args.output_dir)
    except (SimpleAnalysisError, ValueError, RuntimeError) as exc:
        parser.error(str(exc))
    for path in result.export.workbook_paths:
        print(f"Workbook: {path}")
    print(f"Summary: {result.summary_path}")
    for position in result.positions:
        key = position.position_export.position_key
        print(f"{key.experiment} / {key.capture} / {key.position}: {position.roi_filtering.accepted_count} ROIs")
    print("WARNING: automatic provisional analysis; not scientifically validated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
