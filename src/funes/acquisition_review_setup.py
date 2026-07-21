"""Module 19 setup of experiment-scoped review from one D095 load.

This boundary creates only empty D089 review owners from already assigned,
error-free in-memory TIFF pairs and explicit caller-supplied D088/D044
configuration.  It does not inspect or approve fields, run analysis, persist
state, export artifacts, read acquisition files, or edit ROI masks.
"""

from __future__ import annotations

from dataclasses import dataclass

from .acquisition_loading import (
    AcquisitionLoadResult,
    AcquisitionLoadingError,
)
from .contracts import PositionKey
from .experiment_roi_review import (
    ExperimentPositionReview,
    ExperimentPositionReviewMode,
    ExperimentRoiReviewOrchestrator,
)
from .segmentation_review import SegmentationReviewState
from .segmentation_selection import SegmentationConfiguration
from .tiff_reader import TiffPair


class AcquisitionReviewSetupError(RuntimeError):
    """Raised when a D095 load cannot form a complete fresh D089 scope."""


@dataclass(frozen=True, slots=True)
class AcquisitionReviewExperimentConfig:
    """Explicit D088 coverage and D044 selection for one experiment."""

    experiment: str
    mode: ExperimentPositionReviewMode
    segmentation_configuration: SegmentationConfiguration
    selected_positions: tuple[PositionKey, ...] = ()

    def __post_init__(self) -> None:
        _require_text(self.experiment, "experiment")
        if not isinstance(self.mode, ExperimentPositionReviewMode):
            raise TypeError("mode must be an ExperimentPositionReviewMode")
        if not isinstance(
            self.segmentation_configuration, SegmentationConfiguration
        ):
            raise TypeError(
                "segmentation_configuration must be a SegmentationConfiguration"
            )
        selected = tuple(self.selected_positions)
        if any(not isinstance(key, PositionKey) for key in selected):
            raise TypeError("selected_positions must contain only PositionKey values")
        object.__setattr__(self, "selected_positions", selected)


@dataclass(frozen=True, slots=True)
class AcquisitionReviewSetupResult:
    """Fresh D089 scopes retaining the exact ready D095 inputs."""

    acquisition: AcquisitionLoadResult
    assigned_pairs: tuple[TiffPair, ...]
    experiment_configs: tuple[AcquisitionReviewExperimentConfig, ...]
    review_orchestrator: ExperimentRoiReviewOrchestrator

    def __post_init__(self) -> None:
        if not isinstance(self.acquisition, AcquisitionLoadResult):
            raise TypeError("acquisition must be an AcquisitionLoadResult")
        pairs = tuple(self.assigned_pairs)
        if any(not isinstance(pair, TiffPair) for pair in pairs):
            raise TypeError("assigned_pairs must contain only TiffPair values")
        configs = tuple(self.experiment_configs)
        if any(
            not isinstance(config, AcquisitionReviewExperimentConfig)
            for config in configs
        ):
            raise TypeError(
                "experiment_configs must contain only "
                "AcquisitionReviewExperimentConfig values"
            )
        if not isinstance(
            self.review_orchestrator, ExperimentRoiReviewOrchestrator
        ):
            raise TypeError(
                "review_orchestrator must be an ExperimentRoiReviewOrchestrator"
            )

        try:
            source_pairs = self.acquisition.assigned_pairs
        except AcquisitionLoadingError as exc:
            raise ValueError(
                "acquisition must be a complete, error-free D095 load"
            ) from exc
        if len(pairs) != len(source_pairs) or any(
            supplied is not source for supplied, source in zip(pairs, source_pairs)
        ):
            raise ValueError(
                "assigned_pairs must retain the exact ordered D095 pair objects"
            )

        experiment_order, positions_by_experiment = _group_positions(pairs)
        if tuple(config.experiment for config in configs) != experiment_order:
            raise ValueError(
                "experiment_configs must follow the unchanged D095 experiment order"
            )
        reviews = self.review_orchestrator.experiments
        if tuple(review.experiment for review in reviews) != experiment_order:
            raise ValueError(
                "review_orchestrator must follow the unchanged D095 experiment order"
            )
        for config, review in zip(configs, reviews):
            if review.positions != positions_by_experiment[review.experiment]:
                raise ValueError(
                    "each D089 review must preserve the exact D095 position order"
                )
            if (
                review.mode is not config.mode
                or review.selected_positions != config.selected_positions
                or review.review_state.configuration
                is not config.segmentation_configuration
            ):
                raise ValueError(
                    "each D089 review must retain its exact D088/D044 configuration"
                )
            if review.review_state.inspections or review.review_state.global_approval:
                raise ValueError(
                    "an acquisition review setup must not contain inspections or "
                    "global approval"
                )

        object.__setattr__(self, "assigned_pairs", pairs)
        object.__setattr__(self, "experiment_configs", configs)

    def pairs_for_experiment(self, experiment: str) -> tuple[TiffPair, ...]:
        """Return exact D095 pair objects for one registered experiment."""

        self.review_orchestrator.for_experiment(experiment)
        return tuple(
            pair
            for pair in self.assigned_pairs
            if pair.position_key.experiment == experiment
        )


def initialize_acquisition_review(
    acquisition: AcquisitionLoadResult,
    experiment_configs: tuple[AcquisitionReviewExperimentConfig, ...],
) -> AcquisitionReviewSetupResult:
    """Create fresh, unapproved D089 scopes from one ready D095 acquisition.

    Every experiment present in the assigned load requires exactly one explicit
    configuration.  The function preserves first-seen D095 experiment order and
    pair order within each experiment, while reusing the exact pair and
    segmentation-configuration objects supplied by the caller.
    """

    if not isinstance(acquisition, AcquisitionLoadResult):
        raise TypeError("acquisition must be an AcquisitionLoadResult")
    supplied_configs = tuple(experiment_configs)
    if any(
        not isinstance(config, AcquisitionReviewExperimentConfig)
        for config in supplied_configs
    ):
        raise TypeError(
            "experiment_configs must contain only "
            "AcquisitionReviewExperimentConfig values"
        )

    try:
        pairs = acquisition.assigned_pairs
    except AcquisitionLoadingError as exc:
        raise AcquisitionReviewSetupError(
            "cannot initialize D089 review scopes from an incomplete or "
            "error-bearing D095 acquisition load"
        ) from exc

    experiment_order, positions_by_experiment = _group_positions(pairs)
    config_by_experiment: dict[str, AcquisitionReviewExperimentConfig] = {}
    for config in supplied_configs:
        if config.experiment in config_by_experiment:
            raise AcquisitionReviewSetupError(
                f"duplicate review configuration for experiment "
                f"{config.experiment!r}"
            )
        config_by_experiment[config.experiment] = config
    _require_exact_experiments(config_by_experiment, experiment_order)

    ordered_configs = tuple(config_by_experiment[name] for name in experiment_order)
    reviews: list[ExperimentPositionReview] = []
    for config in ordered_configs:
        try:
            reviews.append(
                ExperimentPositionReview(
                    experiment=config.experiment,
                    positions=positions_by_experiment[config.experiment],
                    mode=config.mode,
                    selected_positions=config.selected_positions,
                    review_state=SegmentationReviewState(
                        configuration=config.segmentation_configuration
                    ),
                )
            )
        except (TypeError, ValueError) as exc:
            raise AcquisitionReviewSetupError(
                f"invalid D088/D044 review configuration for experiment "
                f"{config.experiment!r}: {exc}"
            ) from exc

    return AcquisitionReviewSetupResult(
        acquisition=acquisition,
        assigned_pairs=pairs,
        experiment_configs=ordered_configs,
        review_orchestrator=ExperimentRoiReviewOrchestrator(tuple(reviews)),
    )


def _group_positions(
    pairs: tuple[TiffPair, ...],
) -> tuple[tuple[str, ...], dict[str, tuple[PositionKey, ...]]]:
    experiment_order: list[str] = []
    grouped: dict[str, list[PositionKey]] = {}
    seen: set[PositionKey] = set()
    for pair in pairs:
        experiment = pair.position_key.experiment
        if experiment is None:
            raise AcquisitionReviewSetupError(
                "every D095 pair must have an explicit Module 4 experiment label"
            )
        if pair.position_key in seen:
            raise AcquisitionReviewSetupError(
                "D095 assigned pairs contain a duplicate experiment position: "
                f"{_display_key(pair.position_key)}"
            )
        seen.add(pair.position_key)
        if experiment not in grouped:
            experiment_order.append(experiment)
            grouped[experiment] = []
        grouped[experiment].append(pair.position_key)
    return (
        tuple(experiment_order),
        {experiment: tuple(positions) for experiment, positions in grouped.items()},
    )


def _require_exact_experiments(
    configs: dict[str, AcquisitionReviewExperimentConfig],
    expected_order: tuple[str, ...],
) -> None:
    expected = set(expected_order)
    supplied = set(configs)
    missing = expected - supplied
    unexpected = supplied - expected
    if not missing and not unexpected:
        return
    details: list[str] = []
    if missing:
        details.append("missing " + ", ".join(sorted(missing)))
    if unexpected:
        details.append("unexpected " + ", ".join(sorted(unexpected)))
    raise AcquisitionReviewSetupError(
        "review configurations must match the complete D095 experiment scope "
        "exactly: " + "; ".join(details)
    )


def _display_key(key: PositionKey) -> str:
    return f"{key.experiment} / {key.capture} / {key.position}"


def _require_text(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
