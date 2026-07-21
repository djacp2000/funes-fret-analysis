"""Generate an explicit, static Module 7 OFAT visual-review package."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from funes.segmentation_benchmark import (  # noqa: E402
    PARAMETER_BENCHMARK_EXTENSION_VARIANTS,
    PARAMETER_BENCHMARK_VARIANTS,
)
from funes.segmentation_benchmark_review import (  # noqa: E402
    SegmentationBenchmarkReviewPlan,
    export_segmentation_benchmark_review,
    prepare_explicit_benchmark_review_fields,
)
from funes.segmentation_selection import (  # noqa: E402
    CapturePositionKey,
    SegmentationMethodId,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run only explicitly cataloged OFAT variants on explicitly named fields and "
            "write unclassified visual-review artifacts."
        )
    )
    parser.add_argument("input_dir", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--selection-id", required=True)
    parser.add_argument("--selection-note")
    parser.add_argument(
        "--field",
        action="append",
        nargs=2,
        required=True,
        metavar=("CAPTURE", "POSITION"),
        help="Explicit Capture + Position; repeat for each selected field.",
    )
    parser.add_argument(
        "--variant",
        action="append",
        nargs=2,
        required=True,
        metavar=("METHOD", "VARIANT_ID"),
        help="Explicit authorized OFAT method and variant id; repeat for each variant.",
    )
    args = parser.parse_args()

    field_keys = tuple(
        CapturePositionKey(capture, position) for capture, position in args.field
    )
    variants = _resolve_variants(args.variant, parser)
    fields = prepare_explicit_benchmark_review_fields(args.input_dir, field_keys)
    result = export_segmentation_benchmark_review(
        SegmentationBenchmarkReviewPlan(
            selection_id=args.selection_id,
            fields=fields,
            variants=variants,
            selection_note=args.selection_note,
        ),
        args.output_dir,
    )
    print(f"Explicit fields: {len(fields)}")
    print(f"Explicit variants: {len(variants)}")
    print(f"Generated runs: {len(result.artifacts)}")
    print(f"Review index: {result.index_path}")
    print(f"Audit manifest: {result.manifest_path}")
    print("No sample sufficiency, ranking, classification, or profile approval was recorded.")
    return 0


def _resolve_variants(
    requested: list[list[str]],
    parser: argparse.ArgumentParser,
) -> tuple:
    by_key = {
        (variant.method, variant.variant_id): variant
        for variant in (
            *PARAMETER_BENCHMARK_VARIANTS,
            *PARAMETER_BENCHMARK_EXTENSION_VARIANTS,
        )
    }
    selected = []
    for method_text, variant_id in requested:
        try:
            method = SegmentationMethodId(method_text)
        except ValueError:
            parser.error(f"unknown segmentation method: {method_text}")
        variant = by_key.get((method, variant_id))
        if variant is None:
            parser.error(
                f"unknown authorized OFAT variant for method {method.value}: {variant_id}"
            )
        selected.append(variant)
    return tuple(selected)


if __name__ == "__main__":
    raise SystemExit(main())
