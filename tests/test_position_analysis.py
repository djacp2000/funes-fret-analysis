import sys
import shutil
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from funes.contracts import Channel, PositionKey
from funes.experiment_roi_review import (
    ExperimentPositionReview,
    ExperimentPositionReviewMode,
    ExperimentRoiReviewOrchestrator,
)
from funes.file_discovery import parse_tiff_filename
from funes.fret_calculation import FretCalculationConfig, FretChannelMapping
from funes.intensity_qc import (
    CameraSaturationProfile,
    FractionThresholds,
    IntensityQcConfig,
)
from funes.position_analysis import (
    PositionAnalysisConfig,
    PositionAnalysisError,
    run_reviewed_position_analysis,
)
from funes.quantitative_background import (
    PercentileQuantitativeBackgroundEstimator,
    QuantitativeBackgroundConfig,
)
from funes.roi_geometry import BorderTouchPolicy, RoiGeometryFilterConfig
from funes.roi_revision import (
    RoiMaskRevision,
    RoiRevisionOperation,
    RoiRevisionSourceIdentity,
    finalize_roi_revision,
)
from funes.roi_revision_chain import (
    RoiRevisionChainEntry,
    RoiRevisionChainResult,
    load_finalized_roi_revision_chain,
)
from funes.roi_revision_persistence import export_roi_revision_artifact
from funes.roi_revision_replay import replay_roi_revision
from funes.segmentation_channel import SegmentationChannelSelectionConfig
from funes.segmentation_preprocessing import IdentitySegmentationPreprocessor
from funes.segmentation_review import SegmentationReviewState
from funes.segmentation_selection import (
    BENCHMARK_BASELINE_PROFILE,
    CapturePositionKey,
    SegmentationConfiguration,
    SegmentationMethodId,
    SegmentationReviewStatus,
    SegmentationSelection,
)
from funes.temporal_intensity import TemporalIntensityExtractionConfig
from funes.tiff_reader import TiffFrameSequence, TiffMetadata, TiffPair


class PositionAnalysisTests(unittest.TestCase):
    def setUp(self) -> None:
        self.a1 = PositionKey("Capture 1", "Position 1", "Experiment A")
        self.a2 = PositionKey("Capture 1", "Position 2", "Experiment A")
        self.selection = SegmentationSelection(
            SegmentationMethodId.CONTROL_P99,
            BENCHMARK_BASELINE_PROFILE,
        )
        self.configuration = SegmentationConfiguration(
            global_selection=self.selection
        )

    def test_runs_reviewed_position_through_modules_5_to_13(self) -> None:
        pair = _pair(self.a1)
        orchestrator = _review_all_orchestrator(
            (self.a1,), self.configuration, inspected=(self.a1,)
        )

        result = run_reviewed_position_analysis(
            pair,
            orchestrator,
            _analysis_config(),
        )

        self.assertIs(result.pair, pair)
        self.assertEqual(
            result.review_decision.status,
            SegmentationReviewStatus.MANUALLY_REVIEWED,
        )
        self.assertEqual(result.channel_selection.selected_channel, Channel.C0)
        self.assertEqual(result.segmentation.roi_count, 1)
        self.assertEqual(result.roi_filtering.accepted_count, 1)
        self.assertIs(result.roi_filtering.source_segmentation, result.segmentation)
        selection = result.segmentation.engine.selection
        self.assertIsNotNone(selection)
        assert selection is not None
        self.assertEqual(selection.review_status, SegmentationReviewStatus.MANUALLY_REVIEWED)
        self.assertTrue(selection.manually_inspected)
        self.assertEqual(len(result.temporal_intensity.records), 4)
        self.assertEqual(len(result.fret.records), 2)
        self.assertEqual(result.fret.parameters["ratio_formula"], "C0/C1")
        self.assertTrue(all(record.ratio == 2.0 for record in result.fret.records))
        self.assertIsNone(result.roi_revision)
        self.assertIs(result.measurement_roi_filtering, result.roi_filtering)
        self.assertEqual(result.mask_source, "automatic")
        self.assertIsNone(result.revision_sha256)

    def test_optional_finalized_revision_is_the_only_downstream_mask(self) -> None:
        pair = _pair(self.a1)
        orchestrator = _review_all_orchestrator(
            (self.a1,), self.configuration, inspected=(self.a1,)
        )
        automatic = run_reviewed_position_analysis(
            pair,
            orchestrator,
            _analysis_config(),
        )
        revision = finalize_roi_revision(
            _revision_for(automatic),
            finalized_at="2026-07-21T18:00:00-04:00",
        )

        revised = run_reviewed_position_analysis(
            pair,
            orchestrator,
            _analysis_config(),
            roi_revision=revision,
        )

        self.assertIsNotNone(revised.roi_revision)
        assert revised.roi_revision is not None
        self.assertIs(
            revised.roi_revision.original_segmentation,
            revised.segmentation,
        )
        self.assertIs(
            revised.roi_revision.original_filtering,
            revised.roi_filtering,
        )
        self.assertIs(
            revised.measurement_roi_filtering,
            revised.roi_revision.geometry_audit,
        )
        self.assertEqual(revised.mask_source, "manual_revision")
        self.assertEqual(revised.revision_sha256, revision.sha256)
        self.assertEqual(
            tuple(np.unique(revised.roi_filtering.filtered_label_image)),
            (0, 1),
        )
        self.assertEqual(
            tuple(np.unique(revised.measurement_roi_filtering.filtered_label_image)),
            (0, 1, 2),
        )
        self.assertEqual(
            {record.roi_label for record in revised.temporal_intensity.records},
            {1, 2},
        )
        self.assertEqual(len(revised.temporal_intensity.records), 8)
        self.assertEqual(len(revised.fret.records), 4)
        self.assertIsNone(orchestrator.experiments[0].review_state.global_approval)

    def test_validated_revision_chain_supplies_only_its_terminal_mask(self) -> None:
        pair = _pair(self.a1)
        orchestrator = _review_all_orchestrator(
            (self.a1,), self.configuration, inspected=(self.a1,)
        )
        automatic = run_reviewed_position_analysis(pair, orchestrator, _analysis_config())
        root = finalize_roi_revision(
            _revision_for(automatic), finalized_at="2026-07-21T19:00:00-04:00"
        )
        root_result = replay_roi_revision(
            root, automatic.segmentation, automatic.roi_filtering, self.a1
        )
        child = finalize_roi_revision(
            RoiMaskRevision(
                source=root.source,
                operations=(
                    RoiRevisionOperation.replace(
                        2, ((5, 6),), reason="Move synthetic revised support."
                    ),
                ),
                editor="synthetic-chain-editor",
                parent_revision_sha256=root.sha256,
            ),
            finalized_at="2026-07-21T19:05:00-04:00",
        )
        child_result = replay_roi_revision(
            child,
            automatic.segmentation,
            automatic.roi_filtering,
            self.a1,
            parent_result=root_result,
        )
        directory = Path(tempfile.mkdtemp(prefix="funes_position_chain_"))
        self.addCleanup(shutil.rmtree, directory)
        root_path = directory / "root.json"
        child_path = directory / "child.json"
        export_roi_revision_artifact(root_result, root_path)
        export_roi_revision_artifact(child_result, child_path)
        chain = load_finalized_roi_revision_chain(
            (root_path, child_path),
            automatic.segmentation,
            automatic.roi_filtering,
            self.a1,
        )

        revised = run_reviewed_position_analysis(
            pair, orchestrator, _analysis_config(), roi_revision_chain=chain
        )

        self.assertIs(revised.roi_revision_chain, chain)
        self.assertIs(revised.roi_revision, chain.terminal_result)
        self.assertIs(
            revised.measurement_roi_filtering,
            chain.terminal_result.geometry_audit,
        )
        self.assertEqual(len(revised.roi_revision_chain.entries), 2)
        self.assertEqual(revised.revision_sha256, child.sha256)
        self.assertEqual(
            tuple(
                tuple(point)
                for point in np.argwhere(
                    revised.measurement_roi_filtering.filtered_label_image == 2
                )
            ),
            ((5, 6),),
        )
        self.assertEqual({record.roi_label for record in revised.temporal_intensity.records}, {1, 2})

    def test_invalid_or_incompatible_chain_fails_before_quantitative_background(self) -> None:
        pair = _pair(self.a1)
        orchestrator = _review_all_orchestrator(
            (self.a1, self.a2), self.configuration, inspected=(self.a1, self.a2)
        )
        automatic = run_reviewed_position_analysis(pair, orchestrator, _analysis_config())
        root = finalize_roi_revision(
            _revision_for(automatic), finalized_at="2026-07-21T19:10:00-04:00"
        )
        root_result = replay_roi_revision(
            root, automatic.segmentation, automatic.roi_filtering, self.a1
        )
        entry = RoiRevisionChainEntry(Path("synthetic-root.json"), "a" * 64, root_result)
        valid_chain = RoiRevisionChainResult((entry,))
        sibling = finalize_roi_revision(
            RoiMaskRevision(
                source=root.source,
                operations=(
                    RoiRevisionOperation.replace(
                        2, ((5, 6),), reason="First synthetic branch."
                    ),
                ),
                editor="synthetic-chain-editor",
                parent_revision_sha256=root.sha256,
            ),
            finalized_at="2026-07-21T19:15:00-04:00",
        )
        sibling_result = replay_roi_revision(
            sibling,
            automatic.segmentation,
            automatic.roi_filtering,
            self.a1,
            parent_result=root_result,
        )
        forked_chain = object.__new__(RoiRevisionChainResult)
        object.__setattr__(
            forked_chain,
            "entries",
            (
                entry,
                RoiRevisionChainEntry(Path("synthetic-child.json"), "b" * 64, sibling_result),
                RoiRevisionChainEntry(Path("synthetic-sibling.json"), "c" * 64, sibling_result),
            ),
        )
        foreign_pair = _pair(self.a2)
        foreign_automatic = run_reviewed_position_analysis(
            foreign_pair, orchestrator, _analysis_config()
        )
        foreign_revision = finalize_roi_revision(
            _revision_for(foreign_automatic), finalized_at="2026-07-21T19:20:00-04:00"
        )
        foreign_result = replay_roi_revision(
            foreign_revision,
            foreign_automatic.segmentation,
            foreign_automatic.roi_filtering,
            self.a2,
        )
        foreign_chain = RoiRevisionChainResult(
            (
                RoiRevisionChainEntry(
                    Path("synthetic-foreign.json"), "d" * 64, foreign_result
                ),
            )
        )
        bomb_config = _analysis_config(background=_BombBackground())

        with self.subTest("mutually exclusive routes"):
            with self.assertRaisesRegex(PositionAnalysisError, "mutually exclusive"):
                run_reviewed_position_analysis(
                    pair,
                    orchestrator,
                    bomb_config,
                    roi_revision=root,
                    roi_revision_chain=valid_chain,
                )
        with self.subTest("bifurcated"):
            with self.assertRaisesRegex(PositionAnalysisError, "does not name the preceding"):
                run_reviewed_position_analysis(
                    pair, orchestrator, bomb_config, roi_revision_chain=forked_chain
                )
        with self.subTest("incompatible"):
            with self.assertRaisesRegex(PositionAnalysisError, "incompatible"):
                run_reviewed_position_analysis(
                    pair, orchestrator, bomb_config, roi_revision_chain=foreign_chain
                )

    def test_invalid_revision_fails_before_quantitative_background(self) -> None:
        pair = _pair(self.a1)
        orchestrator = _review_all_orchestrator(
            (self.a1,), self.configuration, inspected=(self.a1,)
        )
        automatic = run_reviewed_position_analysis(
            pair,
            orchestrator,
            _analysis_config(),
        )
        draft = _revision_for(automatic)
        stale = finalize_roi_revision(
            replace(
                draft,
                source=replace(draft.source, position="Position 99"),
            ),
            finalized_at="2026-07-21T18:05:00-04:00",
        )
        bomb_config = _analysis_config(background=_BombBackground())

        with self.subTest("draft"):
            with self.assertRaisesRegex(
                PositionAnalysisError,
                "only a finalized ROI revision",
            ):
                run_reviewed_position_analysis(
                    pair,
                    orchestrator,
                    bomb_config,
                    roi_revision=draft,
                )
        with self.subTest("stale"):
            with self.assertRaisesRegex(
                PositionAnalysisError,
                "source identity is stale",
            ):
                run_reviewed_position_analysis(
                    pair,
                    orchestrator,
                    bomb_config,
                    roi_revision=stale,
                )

    def test_consumes_existing_experiment_approval_without_creating_one(self) -> None:
        state = SegmentationReviewState(self.configuration).record_inspection(self.a1)
        scoped = ExperimentPositionReview(
            experiment="Experiment A",
            positions=(self.a1, self.a2),
            mode=ExperimentPositionReviewMode.REVIEW_SELECTED,
            selected_positions=(self.a1,),
            review_state=state,
        )
        approved = scoped.approve_remaining("synthetic-approval")
        orchestrator = ExperimentRoiReviewOrchestrator((approved,))

        result = run_reviewed_position_analysis(
            _pair(self.a2), orchestrator, _analysis_config()
        )

        self.assertEqual(
            result.review_decision.status,
            SegmentationReviewStatus.GLOBAL_POLICY_ACCEPTED,
        )
        self.assertFalse(result.review_decision.manually_inspected)
        selection = result.segmentation.engine.selection
        self.assertIsNotNone(selection)
        assert selection is not None
        self.assertEqual(selection.global_approval_id, "synthetic-approval")
        self.assertFalse(selection.manually_inspected)
        self.assertIs(orchestrator.experiments[0], approved)

    def test_unreviewed_position_is_rejected_before_analysis(self) -> None:
        orchestrator = _review_all_orchestrator((self.a1,), self.configuration)
        config = _analysis_config(preprocessor=_BombPreprocessor())

        with self.assertRaisesRegex(PositionAnalysisError, "manual-review target"):
            run_reviewed_position_analysis(_pair(self.a1), orchestrator, config)

    def test_review_all_override_still_requires_its_manual_inspection(self) -> None:
        override_configuration = SegmentationConfiguration(
            global_selection=self.selection,
            field_overrides={
                CapturePositionKey.from_position_key(self.a1): self.selection
            },
        )
        orchestrator = _review_all_orchestrator(
            (self.a1,), override_configuration
        )
        self.assertEqual(
            orchestrator.query(self.a1).status,
            SegmentationReviewStatus.EXPLICIT_OVERRIDE,
        )

        with self.assertRaisesRegex(PositionAnalysisError, "manual-review target"):
            run_reviewed_position_analysis(
                _pair(self.a1), orchestrator, _analysis_config()
            )

    def test_requires_assigned_pair_and_rejects_conflicting_context(self) -> None:
        orchestrator = _review_all_orchestrator(
            (self.a1,), self.configuration, inspected=(self.a1,)
        )
        unassigned = PositionKey("Capture 1", "Position 1")
        with self.assertRaisesRegex(PositionAnalysisError, "experiment-assigned"):
            run_reviewed_position_analysis(
                _pair(unassigned), orchestrator, _analysis_config()
            )
        with self.assertRaisesRegex(ValueError, "conflicts"):
            run_reviewed_position_analysis(
                _pair(self.a1),
                orchestrator,
                _analysis_config(),
                context={"experiment": "Experiment B"},
            )


class _BombPreprocessor:
    name = "bomb_preprocessor"

    def preprocess(self, frame, context=None):
        raise AssertionError("analysis must not start for an uncovered position")


class _BombBackground:
    name = "bomb_background"

    def estimate(self, pair, roi_label_image=None, context=None):
        raise AssertionError("Module 10 must not start for an invalid ROI revision")


def _review_all_orchestrator(
    positions: tuple[PositionKey, ...],
    configuration: SegmentationConfiguration,
    *,
    inspected: tuple[PositionKey, ...] = (),
) -> ExperimentRoiReviewOrchestrator:
    state = SegmentationReviewState(configuration)
    for key in inspected:
        state = state.record_inspection(key)
    return ExperimentRoiReviewOrchestrator(
        (
            ExperimentPositionReview(
                experiment="Experiment A",
                positions=positions,
                mode=ExperimentPositionReviewMode.REVIEW_ALL,
                review_state=state,
            ),
        )
    )


def _analysis_config(
    *,
    preprocessor=IdentitySegmentationPreprocessor(),
    background=None,
) -> PositionAnalysisConfig:
    return PositionAnalysisConfig(
        channel_selection=SegmentationChannelSelectionConfig(
            manual_channel_override=Channel.C0
        ),
        segmentation_preprocessor=preprocessor,
        roi_geometry=RoiGeometryFilterConfig(
            min_area_pixels=1,
            max_area_pixels=10,
            border_policy=BorderTouchPolicy.ACCEPT,
        ),
        quantitative_background=(
            background
            if background is not None
            else PercentileQuantitativeBackgroundEstimator(
                QuantitativeBackgroundConfig(
                    background_percentile=20.0,
                    minimum_background_pixels=1,
                )
            )
        ),
        intensity_qc=IntensityQcConfig(
            camera_profile=CameraSaturationProfile(
                name="synthetic_12_bit",
                saturation_threshold=4095.0,
            ),
            roi_saturation=FractionThresholds(),
            field_saturation=FractionThresholds(),
        ),
        temporal_intensity=TemporalIntensityExtractionConfig(),
        fret=FretCalculationConfig(
            channel_mapping=FretChannelMapping(Channel.C0, Channel.C1),
            baseline_frame_indices=(0,),
        ),
    )


def _revision_for(automatic) -> RoiMaskRevision:
    return RoiMaskRevision(
        source=RoiRevisionSourceIdentity.from_automatic_results(
            automatic.pair.position_key,
            automatic.segmentation,
            automatic.roi_filtering,
        ),
        operations=(
            RoiRevisionOperation.add(
                2,
                ((5, 5),),
                reason="synthetic omitted ROI",
            ),
        ),
        editor="synthetic-test-editor",
    )


def _pair(position_key: PositionKey) -> TiffPair:
    c0 = np.full((2, 10, 10), 10, dtype=np.uint16)
    c1 = np.full((2, 10, 10), 20, dtype=np.uint16)
    c0[:, 4, 4] = (110, 130)
    c1[:, 4, 4] = (70, 80)
    metadata = TiffMetadata(
        page_count=2,
        series_axes="TYX",
        series_shape=tuple(c0.shape),
        imagej_metadata=None,
        ome_metadata=None,
        page_descriptions=(),
        first_page_tags={},
    )
    stem = f"{position_key.capture} - {position_key.position}_XY1_Z0_T00"
    parsed_c0 = parse_tiff_filename(f"{stem}_C0.tif")
    parsed_c1 = parse_tiff_filename(f"{stem}_C1.tif")
    assert parsed_c0 is not None and parsed_c1 is not None
    return TiffPair(
        position_key=position_key,
        c0=TiffFrameSequence(parsed_c0, c0, metadata),
        c1=TiffFrameSequence(parsed_c1, c1, metadata),
    )


if __name__ == "__main__":
    unittest.main()
