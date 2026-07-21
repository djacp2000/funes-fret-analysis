import unittest
from pathlib import Path
import sys

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from funes.contracts import Channel, PositionKey, SourceFile
from funes.file_discovery import ParsedTiffFile
from funes.segmentation_channel import (
    SegmentationChannelSelectionConfig,
    calculate_first_frame_signal_metrics,
    select_segmentation_channel,
)
from funes.tiff_reader import TiffFrameSequence, TiffMetadata, TiffPair


class SegmentationChannelSelectionTests(unittest.TestCase):
    def test_selects_c1_when_first_frame_has_stronger_robust_signal(self) -> None:
        c0_frame = np.full((10, 10), 20, dtype=np.uint16)
        c0_frame[2:5, 2:5] = 60
        c1_frame = np.full((10, 10), 20, dtype=np.uint16)
        c1_frame[2:6, 2:6] = 180
        pair = _pair(c0_frame, c1_frame)

        result = select_segmentation_channel(pair)

        self.assertEqual(result.selected_channel, Channel.C1)
        self.assertEqual(result.method, "robust_first_frame_contrast")
        self.assertGreater(result.metrics[Channel.C1].score, result.metrics[Channel.C0].score)
        self.assertEqual(result.issues, ())

    def test_selects_c0_when_c1_only_has_single_extreme_pixel(self) -> None:
        c0_frame = np.full((10, 10), 10, dtype=np.uint16)
        c0_frame[2:7, 2:7] = 120
        c1_frame = np.full((10, 10), 10, dtype=np.uint16)
        c1_frame[0, 0] = 4000
        pair = _pair(c0_frame, c1_frame)

        result = select_segmentation_channel(pair)

        self.assertEqual(result.selected_channel, Channel.C0)
        self.assertEqual(result.metrics[Channel.C1].robust_signal, 10)
        self.assertEqual(result.metrics[Channel.C1].maximum, 4000)

    def test_close_scores_use_configured_tie_breaker_and_warning(self) -> None:
        c0_frame = np.full((10, 10), 10, dtype=np.uint16)
        c0_frame[0:5, 0:5] = 110
        c1_frame = np.full((10, 10), 10, dtype=np.uint16)
        c1_frame[0:5, 0:5] = 113
        pair = _pair(c0_frame, c1_frame)
        config = SegmentationChannelSelectionConfig(tie_breaker=Channel.C1, min_relative_margin=0.05)

        result = select_segmentation_channel(pair, config)

        self.assertEqual(result.selected_channel, Channel.C1)
        self.assertEqual(len(result.issues), 1)
        self.assertEqual(result.issues[0].code, "segmentation_channel_close_scores")

    def test_low_contrast_channels_are_reported(self) -> None:
        pair = _pair(
            np.full((4, 4), 25, dtype=np.uint16),
            np.full((4, 4), 25, dtype=np.uint16),
        )

        result = select_segmentation_channel(pair)

        self.assertEqual(result.selected_channel, Channel.C0)
        self.assertEqual(len(result.issues), 1)
        self.assertEqual(result.issues[0].code, "segmentation_channel_low_contrast")
        self.assertEqual(result.issues[0].context["c0_score"], 0.0)
        self.assertEqual(result.issues[0].context["c1_score"], 0.0)

    def test_manual_override_preserves_metrics_and_method(self) -> None:
        pair = _pair(
            np.full((10, 10), 10, dtype=np.uint16),
            np.full((10, 10), 10, dtype=np.uint16),
        )
        pair.c1.frames[0, 2:7, 2:7] = 200
        config = SegmentationChannelSelectionConfig(manual_channel_override=Channel.C0)

        result = select_segmentation_channel(pair, config)

        self.assertEqual(result.selected_channel, Channel.C0)
        self.assertEqual(result.method, "manual_override")
        self.assertGreater(result.metrics[Channel.C1].score, result.metrics[Channel.C0].score)
        self.assertEqual(result.issues[0].code, "segmentation_channel_manual_override")

    def test_metric_config_rejects_invalid_quantiles(self) -> None:
        with self.assertRaisesRegex(ValueError, "background_percentile"):
            SegmentationChannelSelectionConfig(background_percentile=95, signal_percentile=20)

    def test_first_frame_metrics_reject_empty_arrays(self) -> None:
        with self.assertRaisesRegex(ValueError, "at least one pixel"):
            calculate_first_frame_signal_metrics(np.array([], dtype=np.uint16), Channel.C0)


def _pair(c0_first_frame: np.ndarray, c1_first_frame: np.ndarray) -> TiffPair:
    c0 = _sequence(Channel.C0, c0_first_frame)
    c1 = _sequence(Channel.C1, c1_first_frame)
    return TiffPair(position_key=PositionKey(capture="Capture 1", position="Position 1"), c0=c0, c1=c1)


def _sequence(channel: Channel, first_frame: np.ndarray) -> TiffFrameSequence:
    parsed = ParsedTiffFile(
        source=SourceFile(
            path=Path(f"Capture 1 - Position 1_XY1_Z0_T00_{channel.value}.tif"),
            original_name=f"Capture 1 - Position 1_XY1_Z0_T00_{channel.value}.tif",
        ),
        capture="Capture 1",
        position="Position 1",
        xy="XY1",
        z_token="Z0",
        t_token="T00",
        channel=channel,
    )
    frames = np.asarray(first_frame)[np.newaxis, :, :]
    metadata = TiffMetadata(
        page_count=1,
        series_axes=None,
        series_shape=tuple(frames.shape),
        imagej_metadata=None,
        ome_metadata=None,
        page_descriptions=(),
        first_page_tags={},
    )
    return TiffFrameSequence(parsed_file=parsed, frames=frames, metadata=metadata)


if __name__ == "__main__":
    unittest.main()
