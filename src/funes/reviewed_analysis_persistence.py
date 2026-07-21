"""Versioned persistence for one completed reviewed Module 20 analysis.

The package stores the complete typed in-memory result, explicit Module 15
configurations, review state, source provenance, issues, and arrays.  Loading
reconstructs those contracts without running discovery, TIFF I/O, analysis,
review mutation, or workbook export.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import tempfile
import zipfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .acquisition_analysis import AcquisitionAnalysisResult
from .contracts import PositionKey
from .position_analysis import PositionAnalysisConfig, PositionAnalysisResult


REVIEWED_ANALYSIS_PACKAGE_SCHEMA = "funes.module21.reviewed_analysis_package.v2"
REVIEWED_ANALYSIS_PACKAGE_SUFFIX = ".funes-analysis.zip"
_MANIFEST_MEMBER = "manifest.json"
_HASH_DOMAIN = b"funes-module21-reviewed-analysis-package-v2\0"


class ReviewedAnalysisPackageError(ValueError):
    """A reviewed analysis package is unsupported, damaged, or incoherent."""


@dataclass(frozen=True, slots=True)
class PositionAnalysisConfigEntry:
    """One exact position identity and its explicit Module 15 configuration."""

    position_key: PositionKey
    config: PositionAnalysisConfig

    def __post_init__(self) -> None:
        if not isinstance(self.position_key, PositionKey):
            raise TypeError("position_key must be a PositionKey")
        if not isinstance(self.config, PositionAnalysisConfig):
            raise TypeError("config must be a PositionAnalysisConfig")


@dataclass(frozen=True, slots=True)
class ReviewedAnalysisPackage:
    """Complete reconstructed evidence for one reviewed acquisition analysis."""

    analysis: AcquisitionAnalysisResult
    position_configs: tuple[PositionAnalysisConfigEntry, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.analysis, AcquisitionAnalysisResult):
            raise TypeError("analysis must be an AcquisitionAnalysisResult")
        entries = tuple(self.position_configs)
        if any(not isinstance(item, PositionAnalysisConfigEntry) for item in entries):
            raise TypeError(
                "position_configs must contain PositionAnalysisConfigEntry values"
            )
        results = tuple(
            position
            for experiment in self.analysis.experiment_results
            for position in experiment.position_results
        )
        expected_keys = tuple(result.pair.position_key for result in results)
        actual_keys = tuple(entry.position_key for entry in entries)
        if actual_keys != expected_keys:
            raise ValueError(
                "position_configs must follow every Module 20 position exactly "
                "in unchanged experiment and position order"
            )
        for entry, result in zip(entries, results):
            _validate_config_provenance(entry.config, result)
        object.__setattr__(self, "position_configs", entries)

    def config_for(self, position_key: PositionKey) -> PositionAnalysisConfig:
        """Return the persisted explicit configuration for one exact position."""

        for entry in self.position_configs:
            if entry.position_key == position_key:
                return entry.config
        raise KeyError(f"no persisted configuration for {position_key!r}")


@dataclass(frozen=True, slots=True)
class ReviewedAnalysisPackageWriteResult:
    """Audit details for one successfully written Module 21 package."""

    path: Path
    sha256: str
    payload_sha256: str
    experiment_count: int
    position_count: int
    array_count: int


def export_reviewed_analysis_package(
    analysis: AcquisitionAnalysisResult,
    configs: Mapping[PositionKey, PositionAnalysisConfig],
    output_path: Path | str,
) -> ReviewedAnalysisPackageWriteResult:
    """Persist completed Module 20 evidence without rerunning any analysis."""

    package = _build_package(analysis, configs)
    destination = _package_path(output_path)
    if destination.exists():
        raise FileExistsError(
            f"reviewed analysis package already exists: {destination}"
        )

    from ._analysis_package_codec import encode_object_graph

    try:
        payload, array_members = encode_object_graph(
            package,
            extra_types=(ReviewedAnalysisPackage, PositionAnalysisConfigEntry),
        )
    except (TypeError, ValueError) as exc:
        raise ReviewedAnalysisPackageError(
            f"cannot encode reviewed analysis package: {exc}"
        ) from exc
    members = [
        {
            "path": name,
            "sha256": hashlib.sha256(content).hexdigest(),
            "size": len(content),
        }
        for name, content in sorted(array_members.items())
    ]
    payload_sha256 = _payload_sha256(payload, members)
    manifest = {
        "schema": REVIEWED_ANALYSIS_PACKAGE_SCHEMA,
        "payload_sha256": payload_sha256,
        "payload": payload,
        "members": members,
    }
    rendered = (
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        handle, temporary_name = tempfile.mkstemp(
            prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
        )
        os.close(handle)
        temporary_path = Path(temporary_name)
        with zipfile.ZipFile(
            temporary_path, "w", compression=zipfile.ZIP_DEFLATED
        ) as archive:
            archive.writestr(_MANIFEST_MEMBER, rendered)
            for name, content in sorted(array_members.items()):
                archive.writestr(name, content)
        # Export refuses an existing destination above; replace is used only to
        # make publication of this newly created path atomic.
        os.replace(temporary_path, destination)
        temporary_path = None
    except OSError as exc:
        raise ReviewedAnalysisPackageError(
            f"cannot write reviewed analysis package {destination}: {exc}"
        ) from exc
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)

    return ReviewedAnalysisPackageWriteResult(
        path=destination,
        sha256=hashlib.sha256(destination.read_bytes()).hexdigest(),
        payload_sha256=payload_sha256,
        experiment_count=len(package.analysis.experiment_results),
        position_count=len(package.position_configs),
        array_count=len(array_members),
    )


def load_reviewed_analysis_package(
    input_path: Path | str,
) -> ReviewedAnalysisPackage:
    """Strictly reconstruct a package without executing any analysis stage."""

    source = _package_path(input_path)
    try:
        with zipfile.ZipFile(source, "r") as archive:
            names = archive.namelist()
            if len(names) != len(set(names)):
                raise ReviewedAnalysisPackageError(
                    "reviewed analysis package contains duplicate ZIP members"
                )
            if _MANIFEST_MEMBER not in names:
                raise ReviewedAnalysisPackageError(
                    "reviewed analysis package has no manifest.json"
                )
            try:
                raw = json.loads(archive.read(_MANIFEST_MEMBER).decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ReviewedAnalysisPackageError(
                    f"invalid reviewed analysis package manifest JSON: {exc}"
                ) from exc
            manifest = _mapping(raw, "manifest")
            _exact_keys(
                manifest,
                {"schema", "payload_sha256", "payload", "members"},
                "manifest",
            )
            schema = _text(manifest["schema"], "manifest.schema")
            if schema != REVIEWED_ANALYSIS_PACKAGE_SCHEMA:
                raise ReviewedAnalysisPackageError(
                    f"unsupported reviewed analysis package schema: {schema!r}"
                )
            checksum = _text(
                manifest["payload_sha256"], "manifest.payload_sha256"
            )
            members = _members(manifest["members"])
            expected_names = {_MANIFEST_MEMBER, *(item["path"] for item in members)}
            if set(names) != expected_names:
                raise ReviewedAnalysisPackageError(
                    "reviewed analysis package ZIP members do not exactly match "
                    "the manifest"
                )
            array_members: dict[str, bytes] = {}
            for item in members:
                content = archive.read(item["path"])
                if len(content) != item["size"] or not hmac.compare_digest(
                    hashlib.sha256(content).hexdigest(), item["sha256"]
                ):
                    raise ReviewedAnalysisPackageError(
                        f"package member integrity check failed: {item['path']!r}"
                    )
                array_members[item["path"]] = content
    except ReviewedAnalysisPackageError:
        raise
    except (OSError, zipfile.BadZipFile, KeyError) as exc:
        raise ReviewedAnalysisPackageError(
            f"cannot read reviewed analysis package {source}: {exc}"
        ) from exc

    expected_payload_sha256 = _payload_sha256(manifest["payload"], list(members))
    if not hmac.compare_digest(checksum, expected_payload_sha256):
        raise ReviewedAnalysisPackageError(
            "reviewed analysis package payload SHA-256 does not match; the "
            "package is incomplete or has changed"
        )

    from ._analysis_package_codec import (
        AnalysisPackageCodecError,
        decode_object_graph,
    )

    try:
        decoded = decode_object_graph(
            manifest["payload"],
            array_members,
            extra_types=(ReviewedAnalysisPackage, PositionAnalysisConfigEntry),
        )
    except AnalysisPackageCodecError as exc:
        raise ReviewedAnalysisPackageError(
            f"incoherent reviewed analysis package {source}: {exc}"
        ) from exc
    if not isinstance(decoded, ReviewedAnalysisPackage):
        raise ReviewedAnalysisPackageError(
            "reviewed analysis package root is not a ReviewedAnalysisPackage"
        )
    return decoded


def _build_package(
    analysis: AcquisitionAnalysisResult,
    configs: Mapping[PositionKey, PositionAnalysisConfig],
) -> ReviewedAnalysisPackage:
    if not isinstance(analysis, AcquisitionAnalysisResult):
        raise TypeError("analysis must be an AcquisitionAnalysisResult")
    if not isinstance(configs, Mapping):
        raise TypeError("configs must be a mapping keyed by PositionKey")
    supplied = dict(configs)
    for key, config in supplied.items():
        if not isinstance(key, PositionKey):
            raise TypeError("configs keys must be PositionKey values")
        if not isinstance(config, PositionAnalysisConfig):
            raise TypeError("configs values must be PositionAnalysisConfig values")
    ordered_keys = tuple(
        result.pair.position_key
        for experiment in analysis.experiment_results
        for result in experiment.position_results
    )
    missing = set(ordered_keys) - set(supplied)
    unexpected = set(supplied) - set(ordered_keys)
    if missing or unexpected:
        details: list[str] = []
        if missing:
            details.append("missing " + ", ".join(sorted(map(str, missing))))
        if unexpected:
            details.append(
                "unexpected " + ", ".join(sorted(map(str, unexpected)))
            )
        raise ReviewedAnalysisPackageError(
            "configs must match every completed Module 20 position exactly: "
            + "; ".join(details)
        )
    return ReviewedAnalysisPackage(
        analysis=analysis,
        position_configs=tuple(
            PositionAnalysisConfigEntry(key, supplied[key]) for key in ordered_keys
        ),
    )


def _validate_config_provenance(
    config: PositionAnalysisConfig,
    result: PositionAnalysisResult,
) -> None:
    """Reject a plainly incompatible caller-supplied configuration record."""

    if config.roi_geometry != result.roi_filtering.config:
        raise ValueError(
            f"persisted ROI geometry config does not match result for "
            f"{result.pair.position_key!r}"
        )
    if config.segmentation_preprocessor.name != result.preprocessing.method:
        raise ValueError(
            "persisted segmentation preprocessor does not match result method"
        )
    if config.quantitative_background.name != result.background.method:
        raise ValueError(
            "persisted quantitative-background strategy does not match result method"
        )
    expected_qc_method = (
        config.intensity_qc_strategy.name
        if config.intensity_qc_strategy is not None
        else "configured_intensity_qc"
    )
    expected_temporal_method = (
        config.temporal_intensity_strategy.name
        if config.temporal_intensity_strategy is not None
        else "fixed_roi_temporal_intensity"
    )
    expected_fret_method = (
        config.fret_strategy.name
        if config.fret_strategy is not None
        else "configured_fret_calculation"
    )
    for name, expected, actual in (
        ("intensity-QC", expected_qc_method, result.intensity_qc.method),
        ("temporal-intensity", expected_temporal_method, result.temporal_intensity.method),
        ("FRET", expected_fret_method, result.fret.method),
    ):
        if expected != actual:
            raise ValueError(
                f"persisted {name} strategy does not match result method"
            )
    metrics = tuple(result.channel_selection.metrics.values())
    if any(
        metric.background_percentile != config.channel_selection.background_percentile
        or metric.signal_percentile != config.channel_selection.signal_percentile
        for metric in metrics
    ):
        raise ValueError(
            "persisted channel-selection config does not match result metrics"
        )
    if (
        config.channel_selection.manual_channel_override is not None
        and (
            result.channel_selection.method != "manual_override"
            or result.channel_selection.selected_channel
            is not config.channel_selection.manual_channel_override
        )
    ):
        raise ValueError(
            "persisted manual channel selection does not match result"
        )


def _package_path(value: Path | str) -> Path:
    path = Path(value)
    if not path.name.casefold().endswith(REVIEWED_ANALYSIS_PACKAGE_SUFFIX):
        raise ValueError(
            "reviewed analysis packages require a "
            f"{REVIEWED_ANALYSIS_PACKAGE_SUFFIX} path"
        )
    return path


def _payload_sha256(payload: object, members: list[Mapping[str, object]]) -> str:
    canonical = json.dumps(
        {
            "schema": REVIEWED_ANALYSIS_PACKAGE_SCHEMA,
            "payload": payload,
            "members": members,
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(_HASH_DOMAIN + canonical).hexdigest()


def _members(value: object) -> tuple[dict[str, Any], ...]:
    if not isinstance(value, list):
        raise ReviewedAnalysisPackageError("manifest.members must be a JSON array")
    members: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(value):
        raw = _mapping(item, f"manifest.members[{index}]")
        _exact_keys(raw, {"path", "sha256", "size"}, f"manifest.members[{index}]")
        path = _text(raw["path"], f"manifest.members[{index}].path")
        checksum = _text(raw["sha256"], f"manifest.members[{index}].sha256")
        size = raw["size"]
        if (
            not path.startswith("arrays/")
            or ".." in Path(path).parts
            or Path(path).is_absolute()
            or not path.endswith(".npy")
        ):
            raise ReviewedAnalysisPackageError(
                f"invalid package array member path: {path!r}"
            )
        if path in seen:
            raise ReviewedAnalysisPackageError(
                f"duplicate package member manifest entry: {path!r}"
            )
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            raise ReviewedAnalysisPackageError(
                f"manifest.members[{index}].size must be non-negative"
            )
        if len(checksum) != 64 or any(
            character not in "0123456789abcdef" for character in checksum
        ):
            raise ReviewedAnalysisPackageError(
                f"manifest.members[{index}].sha256 must be lowercase SHA-256"
            )
        seen.add(path)
        members.append({"path": path, "sha256": checksum, "size": size})
    if tuple(item["path"] for item in members) != tuple(sorted(seen)):
        raise ReviewedAnalysisPackageError(
            "manifest.members must use canonical path order"
        )
    return tuple(members)


def _mapping(value: object, context: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or not all(
        isinstance(key, str) for key in value
    ):
        raise ReviewedAnalysisPackageError(f"{context} must be a JSON object")
    return value


def _text(value: object, context: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ReviewedAnalysisPackageError(f"{context} must be non-empty text")
    return value


def _exact_keys(
    value: Mapping[str, Any], expected: set[str], context: str
) -> None:
    actual = set(value)
    if actual != expected:
        raise ReviewedAnalysisPackageError(
            f"{context} fields must be exactly {sorted(expected)}"
        )
