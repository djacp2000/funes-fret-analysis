"""Generate a static numbered ROI overlay from the real-pair validation profile."""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from funes.contracts import Channel  # noqa: E402
from funes.real_data_validation import (  # noqa: E402
    RealPairValidationConfig,
    run_real_pair_validation,
)
from funes.static_roi_overlay import (  # noqa: E402
    export_static_roi_overlay_png,
    export_static_roi_overlay_svg,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate a static numbered ROI overlay for one validation pair."
    )
    parser.add_argument("input_dir", type=Path)
    parser.add_argument("output_svg", type=Path)
    parser.add_argument("--validation-output-dir", type=Path, required=True)
    parser.add_argument("--experiment", required=True)
    parser.add_argument("--capture", required=True)
    parser.add_argument("--position", required=True)
    args = parser.parse_args()

    config = RealPairValidationConfig(
        experiment_label=args.experiment,
        capture=args.capture,
        position=args.position,
    )
    validation = run_real_pair_validation(
        args.input_dir,
        args.validation_output_dir,
        config,
        export_workbook=False,
    )
    pair = validation.position_export.pair
    assert pair is not None
    selected_channel = validation.selected_channel.selected_channel
    frame_stack = pair.c0.frames if selected_channel is Channel.C0 else pair.c1.frames
    overlay = export_static_roi_overlay_svg(
        frame_stack[0],
        validation.roi_filtering,
        args.output_svg,
        title=f"{args.capture} • {args.position} • ROI geometry",
        subtitle=f"First temporal frame • segmentation channel {selected_channel.value}",
        context={
            "profile": "D039 validation only",
            "engine": validation.segmentation.engine.name,
            "threshold_percentile": validation.segmentation.engine.parameters.get(
                "threshold_percentile"
            ),
            "min_area_pixels": validation.roi_filtering.config.min_area_pixels,
            "border_policy": validation.roi_filtering.config.border_policy.value,
        },
    )
    png_overlay = export_static_roi_overlay_png(
        frame_stack[0],
        validation.roi_filtering,
        args.output_svg.with_suffix(".png"),
    )

    reasons = Counter(
        reason
        for record in validation.roi_filtering.records
        if not record.accepted
        for reason in record.reasons
    )
    areas = [
        record.geometry.area_pixels
        for record in validation.roi_filtering.records
        if record.accepted
    ]
    print(f"Overlay: {overlay.path}")
    print(f"PNG preview: {png_overlay.path}")
    print(
        "ROIs: "
        f"accepted={len(overlay.accepted_labels)}, "
        f"flagged={len(overlay.flagged_labels)}, "
        f"rejected={len(overlay.rejected_labels)}"
    )
    print(f"Accepted area range: {min(areas)}..{max(areas)} pixels")
    print("Rejection reasons: " + ", ".join(f"{key}={value}" for key, value in sorted(reasons.items())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
