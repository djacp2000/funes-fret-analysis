import base64
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from funes.roi_geometry import BorderTouchPolicy, RoiGeometryFilterConfig, filter_labeled_rois
from funes.static_roi_overlay import (
    StaticRoiOverlayConfig,
    export_static_roi_overlay_png,
    export_static_roi_overlay_svg,
)


class StaticRoiOverlayTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp(prefix="funes_roi_overlay_"))

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir)

    def test_exports_numbered_status_contours_with_embedded_grayscale_frame(self) -> None:
        frame = np.arange(36, dtype=np.uint16).reshape(6, 6)
        labels = np.zeros((6, 6), dtype=np.int32)
        labels[1:3, 1:3] = 1
        labels[0, 5] = 2
        filtering = filter_labeled_rois(
            labels,
            RoiGeometryFilterConfig(
                min_area_pixels=2,
                border_policy=BorderTouchPolicy.EXCLUDE,
            ),
        )
        output = self.tmpdir / "overlay.svg"

        result = export_static_roi_overlay_svg(
            frame,
            filtering,
            output,
            title="Synthetic <ROI> overlay",
            subtitle="First frame",
            context={"channel": "C1"},
        )

        self.assertEqual(result.accepted_labels, (1,))
        self.assertEqual(result.flagged_labels, ())
        self.assertEqual(result.rejected_labels, (2,))
        text = output.read_text(encoding="utf-8")
        self.assertIn("Synthetic &lt;ROI&gt; overlay", text)
        self.assertIn('data-roi-label="1" data-status="accepted"', text)
        self.assertIn('data-roi-label="2" data-status="rejected"', text)
        self.assertIn("Accepted: 1", text)
        self.assertIn("Rejected: 1", text)
        encoded = re.search(r"data:image/png;base64,([^\"]+)", text)
        assert encoded is not None
        self.assertTrue(base64.b64decode(encoded.group(1)).startswith(b"\x89PNG\r\n\x1a\n"))

        png_result = export_static_roi_overlay_png(
            frame,
            filtering,
            self.tmpdir / "overlay.png",
        )
        self.assertEqual(png_result.accepted_labels, (1,))
        self.assertTrue(png_result.path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"))

    def test_rejects_invalid_display_config_and_incompatible_inputs(self) -> None:
        with self.assertRaisesRegex(ValueError, "lower_percentile"):
            StaticRoiOverlayConfig(lower_percentile=99, upper_percentile=1)

        labels = np.ones((2, 2), dtype=np.int32)
        filtering = filter_labeled_rois(labels)
        with self.assertRaisesRegex(ValueError, "same shape"):
            export_static_roi_overlay_svg(
                np.ones((3, 3)),
                filtering,
                self.tmpdir / "overlay.svg",
                title="Overlay",
                subtitle="Frame",
            )
        with self.assertRaisesRegex(ValueError, r"\.svg extension"):
            export_static_roi_overlay_svg(
                np.ones((2, 2)),
                filtering,
                self.tmpdir / "overlay.png",
                title="Overlay",
                subtitle="Frame",
            )
        with self.assertRaisesRegex(ValueError, r"\.png extension"):
            export_static_roi_overlay_png(
                np.ones((2, 2)),
                filtering,
                self.tmpdir / "overlay.svg",
            )

    def test_preserves_flagged_status_separately_from_acceptance(self) -> None:
        labels = np.zeros((4, 4), dtype=np.int32)
        labels[0:2, 0:2] = 1
        filtering = filter_labeled_rois(
            labels,
            RoiGeometryFilterConfig(border_policy=BorderTouchPolicy.FLAG),
        )

        result = export_static_roi_overlay_svg(
            np.ones((4, 4)),
            filtering,
            self.tmpdir / "flagged.svg",
            title="Flagged overlay",
            subtitle="First frame",
        )

        self.assertEqual(result.accepted_labels, ())
        self.assertEqual(result.flagged_labels, (1,))
        self.assertEqual(result.rejected_labels, ())
        self.assertIn('data-status="flagged"', result.path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
