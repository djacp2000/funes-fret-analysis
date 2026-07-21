"""Strict JSON/NumPy object-graph codec for Module 21 packages.

The codec is intentionally private.  It accepts only the immutable FUNES
contracts that participate in Modules 1-20, plus the Module 24 contracts
already nested in a completed Module 20 result, JSON-like containers, and
NumPy arrays.  It never imports a class named by package data and never uses
pickle.
"""

from __future__ import annotations

import hashlib
import inspect
import io
import math
from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any

import numpy as np

from . import (
    acquisition_analysis,
    acquisition_loading,
    acquisition_review_setup,
    auxiliary_metadata,
    contracts,
    experiment_analysis,
    experiment_assignment,
    experiment_roi_review,
    file_discovery,
    fret_calculation,
    intensity_qc,
    position_analysis,
    quantitative_background,
    roi_geometry,
    roi_revision,
    roi_revision_replay,
    segmentation_channel,
    segmentation_engine,
    segmentation_preprocessing,
    segmentation_review,
    segmentation_selection,
    slidebook_log_metadata,
    temporal_intensity,
    tiff_reader,
)


class AnalysisPackageCodecError(ValueError):
    """The package object graph is unsupported or incoherent."""


_CONTRACT_MODULES = (
    contracts,
    file_discovery,
    auxiliary_metadata,
    slidebook_log_metadata,
    experiment_assignment,
    tiff_reader,
    acquisition_loading,
    segmentation_channel,
    segmentation_preprocessing,
    segmentation_selection,
    segmentation_review,
    experiment_roi_review,
    acquisition_review_setup,
    segmentation_engine,
    roi_geometry,
    roi_revision,
    roi_revision_replay,
    quantitative_background,
    intensity_qc,
    temporal_intensity,
    fret_calculation,
    position_analysis,
    experiment_analysis,
    acquisition_analysis,
)


def encode_object_graph(
    root: object, *, extra_types: tuple[type[Any], ...] = ()
) -> tuple[dict[str, Any], dict[str, bytes]]:
    """Encode one supported object graph and its arrays without pickle."""

    encoder = _Encoder(extra_types)
    encoded = encoder.encode(root, "package")
    if not isinstance(encoded, dict):  # pragma: no cover - root is a dataclass
        raise AnalysisPackageCodecError("package root did not encode as an object")
    return encoded, encoder.array_members


def decode_object_graph(
    payload: object,
    array_members: Mapping[str, bytes],
    *,
    extra_types: tuple[type[Any], ...] = (),
) -> object:
    """Decode after strict type, field, array, and reference validation."""

    dataclasses, enums = _type_registries(extra_types)
    decoder = _Decoder(dataclasses, enums, array_members)
    result = decoder.decode(payload, "package")
    unused = set(array_members) - decoder.used_array_members
    if unused:
        raise AnalysisPackageCodecError(
            "package contains unreferenced array members: " + ", ".join(sorted(unused))
        )
    return result


def type_identifier(value: type[Any]) -> str:
    return f"{value.__module__}.{value.__qualname__}"


class _Encoder:
    def __init__(self, extra_types: tuple[type[Any], ...]) -> None:
        self._memo: dict[int, str] = {}
        self._next_id = 1
        self.array_members: dict[str, bytes] = {}
        self._dataclasses, self._enums = _type_registries(extra_types)

    def encode(self, value: object, context: str) -> Any:
        if isinstance(value, Enum):
            enum_type = type(value)
            if enum_type not in self._enums.values():
                raise AnalysisPackageCodecError(
                    f"{context} uses unsupported enum {type_identifier(enum_type)!r}"
                )
            return {"$enum": type_identifier(enum_type), "value": value.value}
        if value is None or isinstance(value, (str, bool, int)):
            return value
        if isinstance(value, float):
            if math.isfinite(value):
                return value
            return {"$float": _nonfinite_name(value)}
        if isinstance(value, np.bool_):
            return bool(value)
        if isinstance(value, np.integer):
            return int(value)
        if isinstance(value, np.floating):
            return self.encode(float(value), context)
        if isinstance(value, Path):
            return {"$path": str(value)}
        if isinstance(value, np.ndarray):
            return self._encode_array(value, context)
        if is_dataclass(value) and not isinstance(value, type):
            identifier = type_identifier(type(value))
            if self._dataclasses.get(identifier) is not type(value):
                raise AnalysisPackageCodecError(
                    f"{context} uses unsupported contract type {identifier!r}"
                )
            return self._encode_dataclass(value, context)
        if isinstance(value, tuple):
            return {
                "$tuple": [
                    self.encode(item, f"{context}[{index}]")
                    for index, item in enumerate(value)
                ]
            }
        if isinstance(value, list):
            return {
                "$list": [
                    self.encode(item, f"{context}[{index}]")
                    for index, item in enumerate(value)
                ]
            }
        if isinstance(value, Mapping):
            return {
                "$mapping": [
                    [
                        self.encode(key, f"{context}.key[{index}]"),
                        self.encode(item, f"{context}.value[{index}]"),
                    ]
                    for index, (key, item) in enumerate(value.items())
                ]
            }
        if isinstance(value, frozenset):
            return {
                "$frozenset": [
                    self.encode(item, f"{context}[{index}]")
                    for index, item in enumerate(
                        sorted(value, key=lambda item: repr(item))
                    )
                ]
            }
        raise AnalysisPackageCodecError(
            f"{context} uses unsupported value type {type_identifier(type(value))!r}"
        )

    def _encode_dataclass(self, value: object, context: str) -> dict[str, Any]:
        existing = self._memo.get(id(value))
        if existing is not None:
            return {"$ref": existing}
        object_id = self._new_id()
        self._memo[id(value)] = object_id
        return {
            "$id": object_id,
            "$type": type_identifier(type(value)),
            "fields": [
                [
                    field.name,
                    self.encode(
                        getattr(value, field.name), f"{context}.{field.name}"
                    ),
                ]
                for field in fields(value)
            ],
        }

    def _encode_array(
        self, value: np.ndarray[Any, Any], context: str
    ) -> dict[str, Any]:
        existing = self._memo.get(id(value))
        if existing is not None:
            return {"$ref": existing}
        if value.dtype.hasobject:
            raise AnalysisPackageCodecError(
                f"{context} uses an object-dtype array, which cannot be persisted safely"
            )
        object_id = self._new_id()
        self._memo[id(value)] = object_id
        member = f"arrays/{object_id}.npy"
        output = io.BytesIO()
        np.save(output, value, allow_pickle=False)
        content = output.getvalue()
        self.array_members[member] = content
        return {
            "$id": object_id,
            "$array": member,
            "dtype": value.dtype.str,
            "shape": list(value.shape),
            "sha256": hashlib.sha256(content).hexdigest(),
        }

    def _new_id(self) -> str:
        value = f"o{self._next_id:08d}"
        self._next_id += 1
        return value


class _Decoder:
    def __init__(
        self,
        dataclasses: Mapping[str, type[Any]],
        enums: Mapping[str, type[Enum]],
        array_members: Mapping[str, bytes],
    ) -> None:
        self._dataclasses = dataclasses
        self._enums = enums
        self._array_members = dict(array_members)
        self._objects: dict[str, object] = {}
        self.used_array_members: set[str] = set()

    def decode(self, value: object, context: str) -> object:
        if value is None or isinstance(value, (str, bool, int, float)):
            return value
        if not isinstance(value, dict) or not all(
            isinstance(key, str) for key in value
        ):
            raise AnalysisPackageCodecError(
                f"{context} must be a tagged JSON value"
            )
        keys = set(value)
        if keys == {"$float"}:
            return _parse_nonfinite(value["$float"], context)
        if keys == {"$path"}:
            path = value["$path"]
            if not isinstance(path, str):
                raise AnalysisPackageCodecError(f"{context} path must be text")
            return Path(path)
        if keys == {"$enum", "value"}:
            return self._decode_enum(value, context)
        if keys == {"$ref"}:
            reference = _object_id(value["$ref"], f"{context}.$ref")
            try:
                return self._objects[reference]
            except KeyError as exc:
                raise AnalysisPackageCodecError(
                    f"{context} contains a forward or unknown reference {reference!r}"
                ) from exc
        if keys == {"$tuple"}:
            return tuple(
                self.decode(item, f"{context}[{index}]")
                for index, item in enumerate(_json_list(value["$tuple"], context))
            )
        if keys == {"$list"}:
            return [
                self.decode(item, f"{context}[{index}]")
                for index, item in enumerate(_json_list(value["$list"], context))
            ]
        if keys == {"$frozenset"}:
            return frozenset(
                self.decode(item, f"{context}[{index}]")
                for index, item in enumerate(
                    _json_list(value["$frozenset"], context)
                )
            )
        if keys == {"$mapping"}:
            return self._decode_mapping(value["$mapping"], context)
        if keys == {"$id", "$array", "dtype", "shape", "sha256"}:
            return self._decode_array(value, context)
        if keys == {"$id", "$type", "fields"}:
            return self._decode_dataclass(value, context)
        raise AnalysisPackageCodecError(
            f"{context} has unknown or incomplete tagged fields {sorted(keys)}"
        )

    def _decode_enum(self, value: Mapping[str, object], context: str) -> Enum:
        identifier = value["$enum"]
        if not isinstance(identifier, str) or identifier not in self._enums:
            raise AnalysisPackageCodecError(
                f"{context} names unsupported enum {identifier!r}"
            )
        try:
            return self._enums[identifier](value["value"])
        except (TypeError, ValueError) as exc:
            raise AnalysisPackageCodecError(
                f"{context} has invalid enum value {value['value']!r}"
            ) from exc

    def _decode_mapping(self, value: object, context: str) -> dict[object, object]:
        result: dict[object, object] = {}
        for index, item in enumerate(_json_list(value, context)):
            pair = _json_list(item, f"{context}[{index}]")
            if len(pair) != 2:
                raise AnalysisPackageCodecError(
                    f"{context}[{index}] must contain one key and one value"
                )
            key = self.decode(pair[0], f"{context}.key[{index}]")
            try:
                if key in result:
                    raise AnalysisPackageCodecError(
                        f"{context} contains a duplicate mapping key"
                    )
                result[key] = self.decode(pair[1], f"{context}.value[{index}]")
            except TypeError as exc:
                raise AnalysisPackageCodecError(
                    f"{context} contains an unhashable mapping key"
                ) from exc
        return result

    def _decode_array(
        self, value: Mapping[str, object], context: str
    ) -> np.ndarray[Any, Any]:
        object_id = self._start_object(value["$id"], context)
        member = value["$array"]
        dtype = value["dtype"]
        shape = value["shape"]
        checksum = value["sha256"]
        if not all(isinstance(item, str) for item in (member, dtype, checksum)):
            raise AnalysisPackageCodecError(
                f"{context} array metadata must use text values"
            )
        if member not in self._array_members:
            raise AnalysisPackageCodecError(
                f"{context} references missing array member {member!r}"
            )
        content = self._array_members[member]
        if hashlib.sha256(content).hexdigest() != checksum:
            raise AnalysisPackageCodecError(
                f"{context} array SHA-256 does not match for {member!r}"
            )
        try:
            array = np.load(io.BytesIO(content), allow_pickle=False)
        except (OSError, ValueError) as exc:
            raise AnalysisPackageCodecError(
                f"{context} contains an invalid NumPy array: {exc}"
            ) from exc
        expected_shape = _shape(shape, f"{context}.shape")
        if array.dtype.str != dtype or array.shape != expected_shape:
            raise AnalysisPackageCodecError(
                f"{context} array dtype or shape differs from its manifest"
            )
        self._objects[object_id] = array
        self.used_array_members.add(member)
        return array

    def _decode_dataclass(
        self, value: Mapping[str, object], context: str
    ) -> object:
        object_id = self._start_object(value["$id"], context)
        identifier = value["$type"]
        if not isinstance(identifier, str) or identifier not in self._dataclasses:
            raise AnalysisPackageCodecError(
                f"{context} names unsupported contract type {identifier!r}"
            )
        contract = self._dataclasses[identifier]
        entries = _json_list(value["fields"], f"{context}.fields")
        expected_names = tuple(field.name for field in fields(contract))
        actual_names: list[str] = []
        arguments: dict[str, object] = {}
        for index, entry in enumerate(entries):
            pair = _json_list(entry, f"{context}.fields[{index}]")
            if len(pair) != 2 or not isinstance(pair[0], str):
                raise AnalysisPackageCodecError(
                    f"{context}.fields[{index}] must be a named field pair"
                )
            actual_names.append(pair[0])
            arguments[pair[0]] = self.decode(
                pair[1], f"{context}.{pair[0]}"
            )
        if tuple(actual_names) != expected_names:
            raise AnalysisPackageCodecError(
                f"{context} fields do not exactly match {identifier}"
            )
        try:
            result = contract(**arguments)
        except (TypeError, ValueError) as exc:
            raise AnalysisPackageCodecError(
                f"{context} is an incoherent {identifier}: {exc}"
            ) from exc
        self._objects[object_id] = result
        return result

    def _start_object(self, value: object, context: str) -> str:
        object_id = _object_id(value, f"{context}.$id")
        if object_id in self._objects:
            raise AnalysisPackageCodecError(
                f"{context} repeats object definition {object_id!r}"
            )
        return object_id


def _type_registries(
    extra_types: tuple[type[Any], ...],
) -> tuple[dict[str, type[Any]], dict[str, type[Enum]]]:
    dataclass_types: dict[str, type[Any]] = {}
    enum_types: dict[str, type[Enum]] = {}
    for module in _CONTRACT_MODULES:
        for name, candidate in inspect.getmembers(module, inspect.isclass):
            if name.startswith("_") or candidate.__module__ != module.__name__:
                continue
            if is_dataclass(candidate):
                dataclass_types[type_identifier(candidate)] = candidate
            elif issubclass(candidate, Enum):
                enum_types[type_identifier(candidate)] = candidate
    for candidate in extra_types:
        if not is_dataclass(candidate):
            raise TypeError("extra_types must contain dataclass types")
        dataclass_types[type_identifier(candidate)] = candidate
    return dataclass_types, enum_types


def _json_list(value: object, context: str) -> list[Any]:
    if not isinstance(value, list):
        raise AnalysisPackageCodecError(f"{context} must be a JSON array")
    return value


def _object_id(value: object, context: str) -> str:
    if not isinstance(value, str) or not value.startswith("o") or len(value) != 9:
        raise AnalysisPackageCodecError(f"{context} is not a valid object id")
    return value


def _shape(value: object, context: str) -> tuple[int, ...]:
    raw = _json_list(value, context)
    if any(not isinstance(item, int) or isinstance(item, bool) or item < 0 for item in raw):
        raise AnalysisPackageCodecError(
            f"{context} must contain non-negative integer dimensions"
        )
    return tuple(raw)


def _nonfinite_name(value: float) -> str:
    if math.isnan(value):
        return "nan"
    return "positive_infinity" if value > 0 else "negative_infinity"


def _parse_nonfinite(value: object, context: str) -> float:
    values = {
        "nan": float("nan"),
        "positive_infinity": float("inf"),
        "negative_infinity": float("-inf"),
    }
    if not isinstance(value, str) or value not in values:
        raise AnalysisPackageCodecError(
            f"{context} has an invalid non-finite float encoding"
        )
    return values[value]
