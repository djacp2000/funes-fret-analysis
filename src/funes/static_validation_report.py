"""Static, auditable visual report for one focused real-pair validation run.

The report is deliberately diagnostic. It renders existing module outputs and
descriptive sensitivity comparisons without changing pipeline configuration or
making production scientific decisions.
"""

from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from html import escape
from pathlib import Path
from statistics import median
from typing import Any, Iterable, Mapping, Sequence

import numpy as np

from .contracts import Channel
from .intensity_qc import IntensityQcScope, IntensityQcStatus
from .real_data_validation import RealPairValidationResult
from .roi_geometry import (
    BorderTouchPolicy,
    RoiGeometryFilterConfig,
    filter_labeled_rois,
    filter_segmentation_rois,
)
from .static_roi_overlay import (
    StaticRoiOverlayConfig,
    export_static_roi_overlay_png,
    export_static_roi_overlay_svg,
)
from .static_validation_charts import ratio_histogram_svg, ratio_scatter_svg


@dataclass(frozen=True, slots=True)
class StaticVisualValidationReportResult:
    """Paths and key counts from one generated report."""

    report_path: Path
    manifest_path: Path
    roi_audit_path: Path
    roi_measurements_path: Path
    module_io_path: Path
    segmented_components: int
    geometry_retained_rois: int
    geometry_rejected_rois: int
    intensity_excluded_rois: int
    ratio_minimum: float
    ratio_maximum: float


def export_static_visual_validation_report(
    validation: RealPairValidationResult,
    output_dir: Path | str,
) -> StaticVisualValidationReportResult:
    """Write a static HTML report plus machine-readable audit companions."""

    pair = validation.position_export.pair
    if pair is None:
        raise ValueError("static visual validation requires the source TIFF pair")
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)

    selected_channel = validation.selected_channel.selected_channel
    selected_stack = pair.c0.frames if selected_channel is Channel.C0 else pair.c1.frames
    frame_shape = selected_stack[0].shape
    if validation.preprocessing.processed_frame.shape != frame_shape:
        raise ValueError("preprocessed frame shape does not match the selected first frame")

    displays = _export_image_assets(validation, destination)
    scatter_path = destination / "c0_vs_c1_by_roi.svg"
    histogram_path = destination / "ratio_distribution.svg"
    scatter_path.write_text(
        ratio_scatter_svg(validation.position_export.fret.records),
        encoding="utf-8",
        newline="\n",
    )
    histogram_path.write_text(
        ratio_histogram_svg(validation.position_export.fret.records),
        encoding="utf-8",
        newline="\n",
    )

    roi_audit_rows = _source_roi_audit_rows(validation)
    measurement_rows = _accepted_measurement_rows(validation)
    module_rows = _module_io_rows(validation)
    roi_audit_path = destination / "roi_audit.csv"
    measurements_path = destination / "roi_measurements.csv"
    module_io_path = destination / "module_io.csv"
    _write_csv(roi_audit_path, roi_audit_rows)
    _write_csv(measurements_path, measurement_rows)
    _write_csv(module_io_path, module_rows)

    ratios = tuple(
        float(record.ratio)
        for record in validation.position_export.fret.records
        if record.ratio is not None
    )
    if not ratios:
        raise ValueError("static visual validation requires at least one calculated ratio")
    intensity_excluded = _roi_labels_with_intensity_status(validation, IntensityQcStatus.EXCLUDED)
    intensity_flagged = _roi_labels_with_intensity_status(validation, IntensityQcStatus.FLAGGED)
    report_path = destination / "capture1_position1_static_validation.html"
    source_files = _source_file_records(validation)
    report_path.write_text(
        _build_html(
            validation=validation,
            displays=displays,
            source_files=source_files,
            roi_audit_rows=roi_audit_rows,
            measurement_rows=measurement_rows,
            module_rows=module_rows,
            ratios=ratios,
            intensity_excluded=intensity_excluded,
            intensity_flagged=intensity_flagged,
        ),
        encoding="utf-8",
        newline="\n",
    )

    artifact_paths = (
        report_path,
        roi_audit_path,
        measurements_path,
        module_io_path,
        scatter_path,
        histogram_path,
        *tuple(displays["paths"]),
    )
    manifest_path = destination / "audit_manifest.json"
    manifest = {
        "schema_version": 1,
        "scope": "Capture 1 + Position 1 static visual validation",
        "production_ready": False,
        "ratio_formula": "C0/C1",
        "ratio_measurement": "background_corrected_mean",
        "supersedes": {
            "formula": "C1/C0",
            "prior_ratio_range": "2.77-10.86",
            "status": "superseded_by_D042_and_regenerated_module13_output",
        },
        "source_files": source_files,
        "artifacts": [_file_record(path, role="report_artifact") for path in artifact_paths],
        "module_parameters": _module_parameters(validation),
        "classification_counts": {
            "unsegmented_pixels": int(np.count_nonzero(validation.segmentation.label_image == 0)),
            "segmented_components": validation.segmentation.roi_count,
            "geometry_retained_rois": validation.roi_filtering.accepted_count,
            "geometry_rejected_rois": validation.roi_filtering.rejected_count,
            "intensity_flagged_rois": len(intensity_flagged),
            "intensity_excluded_rois": len(intensity_excluded),
        },
        "manifest_note": "The manifest intentionally does not hash itself.",
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False, default=_json_default)
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return StaticVisualValidationReportResult(
        report_path=report_path,
        manifest_path=manifest_path,
        roi_audit_path=roi_audit_path,
        roi_measurements_path=measurements_path,
        module_io_path=module_io_path,
        segmented_components=validation.segmentation.roi_count,
        geometry_retained_rois=validation.roi_filtering.accepted_count,
        geometry_rejected_rois=validation.roi_filtering.rejected_count,
        intensity_excluded_rois=len(intensity_excluded),
        ratio_minimum=min(ratios),
        ratio_maximum=max(ratios),
    )


def _export_image_assets(
    validation: RealPairValidationResult,
    destination: Path,
) -> dict[str, Any]:
    pair = validation.position_export.pair
    assert pair is not None
    empty_filter = filter_labeled_rois(np.zeros(pair.c0.frames[0].shape, dtype=np.int32))
    plain_config = StaticRoiOverlayConfig(lower_percentile=1.0, upper_percentile=99.5)
    c0 = export_static_roi_overlay_png(
        pair.c0.frames[0], empty_filter, destination / "first_frame_c0.png", config=plain_config
    )
    c1 = export_static_roi_overlay_png(
        pair.c1.frames[0], empty_filter, destination / "first_frame_c1.png", config=plain_config
    )
    processed = export_static_roi_overlay_png(
        validation.preprocessing.processed_frame,
        empty_filter,
        destination / "preprocessed_selected_channel.png",
        config=plain_config,
    )
    binary = export_static_roi_overlay_png(
        (validation.segmentation.label_image > 0).astype(np.uint8),
        empty_filter,
        destination / "module7_binary_mask.png",
        config=StaticRoiOverlayConfig(lower_percentile=0.0, upper_percentile=100.0),
    )
    all_components = filter_segmentation_rois(
        validation.segmentation,
        RoiGeometryFilterConfig(border_policy=BorderTouchPolicy.ACCEPT),
    )
    components_svg = export_static_roi_overlay_svg(
        validation.preprocessing.processed_frame,
        all_components,
        destination / "components_before_geometry.svg",
        title="Componentes del módulo 7 antes del filtro geométrico",
        subtitle="Etiquetas originales; todavía no hay aceptación ni rechazo",
        context={"component_count": validation.segmentation.roi_count},
    )
    selected = validation.selected_channel.selected_channel
    selected_frame = pair.c0.frames[0] if selected is Channel.C0 else pair.c1.frames[0]
    geometry_svg = export_static_roi_overlay_svg(
        selected_frame,
        validation.roi_filtering,
        destination / "module8_numbered_overlay.svg",
        title="Overlay numerado después del módulo 8",
        subtitle=f"Primer frame de {selected.value}; razones detalladas en la tabla del informe",
        context={
            "profile": "D039 validation only",
            "min_area_pixels": validation.roi_filtering.config.min_area_pixels,
            "border_policy": validation.roi_filtering.config.border_policy.value,
        },
    )
    geometry_png = export_static_roi_overlay_png(
        selected_frame,
        validation.roi_filtering,
        destination / "module8_numbered_overlay.png",
    )
    paths = (
        c0.path,
        c1.path,
        processed.path,
        binary.path,
        components_svg.path,
        geometry_svg.path,
        geometry_png.path,
    )
    return {
        "c0": c0,
        "c1": c1,
        "processed": processed,
        "binary": binary,
        "components_svg": components_svg,
        "geometry_svg": geometry_svg,
        "paths": paths,
    }


def _source_roi_audit_rows(validation: RealPairValidationResult) -> list[dict[str, Any]]:
    pair = validation.position_export.pair
    assert pair is not None
    backgrounds = {
        (estimate.channel, estimate.frame.frame_index): estimate.value
        for estimate in validation.position_export.background.estimates
    }
    rows: list[dict[str, Any]] = []
    for record in validation.roi_filtering.records:
        label = record.geometry.label
        mask = validation.segmentation.label_image == label
        c0_raw = float(np.mean(pair.c0.frames[0][mask]))
        c1_raw = float(np.mean(pair.c1.frames[0][mask]))
        c0_corrected = _subtract(c0_raw, backgrounds[(Channel.C0, 0)])
        c1_corrected = _subtract(c1_raw, backgrounds[(Channel.C1, 0)])
        ratio = (
            c0_corrected / c1_corrected
            if c0_corrected is not None and c1_corrected is not None and c1_corrected > 0
            else None
        )
        rows.append(
            {
                "roi_label": label,
                "module7_segmented": True,
                "module8_status": record.status.value,
                "module8_reasons": ";".join(record.reasons),
                "area_pixels": record.geometry.area_pixels,
                "touches_border": record.geometry.touches_border,
                "centroid_row": record.geometry.centroid_row,
                "centroid_col": record.geometry.centroid_col,
                "frame0_c0_raw_mean_diagnostic": c0_raw,
                "frame0_c1_raw_mean_diagnostic": c1_raw,
                "frame0_c0_corrected_mean_diagnostic": c0_corrected,
                "frame0_c1_corrected_mean_diagnostic": c1_corrected,
                "frame0_c0_over_c1_diagnostic": ratio,
                "enters_modules_10_to_13": record.accepted,
            }
        )
    return rows


def _accepted_measurement_rows(validation: RealPairValidationResult) -> list[dict[str, Any]]:
    intensity = {
        (record.channel, record.frame.frame_index, record.roi_label): record
        for record in validation.position_export.temporal_intensity.records
    }
    qc = {
        (record.channel, record.frame.frame_index, record.roi_label): record
        for record in validation.position_export.intensity_qc.records
        if record.scope is IntensityQcScope.ROI_FRAME
    }
    geometry = {record.geometry.label: record for record in validation.roi_filtering.records}
    rows: list[dict[str, Any]] = []
    for fret in validation.position_export.fret.records:
        key0 = (Channel.C0, fret.frame.frame_index, fret.roi_label)
        key1 = (Channel.C1, fret.frame.frame_index, fret.roi_label)
        c0_intensity = intensity[key0]
        c1_intensity = intensity[key1]
        c0_qc = qc[key0]
        c1_qc = qc[key1]
        rows.append(
            {
                "roi_label": fret.roi_label,
                "frame_index": fret.frame.frame_index,
                "area_pixels": geometry[fret.roi_label].geometry.area_pixels,
                "donor_channel": fret.donor_channel.value,
                "fret_channel": fret.fret_channel.value,
                "c0_raw_mean": c0_intensity.raw_mean,
                "c0_background": c0_intensity.background_value,
                "c0_background_corrected_mean": c0_intensity.background_corrected_mean,
                "c1_raw_mean": c1_intensity.raw_mean,
                "c1_background": c1_intensity.background_value,
                "c1_background_corrected_mean": c1_intensity.background_corrected_mean,
                "ratio_formula": "C0/C1",
                "ratio_background_corrected_mean": fret.ratio,
                "ratio_status": fret.ratio_status.value,
                "c0_saturated_pixel_count_validation_profile": c0_qc.metrics.get(
                    "saturated_pixel_count"
                ),
                "c1_saturated_pixel_count_validation_profile": c1_qc.metrics.get(
                    "saturated_pixel_count"
                ),
                "c0_qc_status": c0_qc.status.value,
                "c1_qc_status": c1_qc.status.value,
            }
        )
    return rows


def _module_io_rows(validation: RealPairValidationResult) -> list[dict[str, Any]]:
    records = len(validation.position_export.temporal_intensity.records)
    ratios = len(validation.position_export.fret.records)
    estimates = len(validation.position_export.background.estimates)
    qc_records = len(validation.position_export.intensity_qc.records)
    return [
        _module_row("1–4", "TIFF y log; regla explícita de experimento", "Un par C0/C1 validado y log asociado"),
        _module_row("5", "Primer frame C0 y C1", f"Métricas robustas y canal {validation.selected_channel.selected_channel.value}"),
        _module_row("6", "Primer frame del canal elegido", f"Imagen float64; método {validation.preprocessing.method}"),
        _module_row("7", "Imagen preprocesada", f"Máscara etiquetada con {validation.segmentation.roi_count} componentes"),
        _module_row("8", "Máscara etiquetada", f"{validation.roi_filtering.accepted_count} retenidas; {validation.roi_filtering.rejected_count} rechazadas"),
        _module_row("9 (sustituto)", "Frame, etiquetas y estados del módulo 8", "Overlay SVG/PNG estático; ninguna decisión manual"),
        _module_row("10", "Par C0/C1 y máscara geométrica retenida", f"{estimates} estimaciones de fondo canal-frame"),
        _module_row("11", "Frames, ROI, fondo y perfil de cámara provisional", f"{qc_records} registros QC; umbrales de exclusión desactivados"),
        _module_row("12", "ROI fijas, fondos y QC", f"{records} registros de intensidad temporal"),
        _module_row("13", "Medias C0/C1 crudas y corregidas; roles biológicos separados", f"{ratios} ratios C0/C1 corregidos"),
        _module_row("Validación estática", "Salidas anteriores sin recalcular decisiones", "HTML, SVG/PNG, CSV y manifiesto SHA-256"),
    ]


def _module_row(module: str, inputs: str, outputs: str) -> dict[str, Any]:
    return {"module": module, "input": inputs, "output": outputs}


def _build_html(
    *,
    validation: RealPairValidationResult,
    displays: Mapping[str, Any],
    source_files: Sequence[Mapping[str, Any]],
    roi_audit_rows: Sequence[Mapping[str, Any]],
    measurement_rows: Sequence[Mapping[str, Any]],
    module_rows: Sequence[Mapping[str, Any]],
    ratios: Sequence[float],
    intensity_excluded: set[int],
    intensity_flagged: set[int],
) -> str:
    pair = validation.position_export.pair
    assert pair is not None
    segmentation = validation.segmentation
    filtering = validation.roi_filtering
    foreground_pixels = int(np.count_nonzero(segmentation.label_image))
    total_pixels = int(segmentation.label_image.size)
    rejected = [record for record in filtering.records if not record.accepted]
    accepted_areas = [record.geometry.area_pixels for record in filtering.records if record.accepted]
    rejected_areas = [record.geometry.area_pixels for record in rejected]
    threshold = float(segmentation.engine.parameters["threshold_value"])
    percentile = float(segmentation.engine.parameters["threshold_percentile"])
    raw_ratios = [
        row["c0_raw_mean"] / row["c1_raw_mean"]
        for row in measurement_rows
        if row["c1_raw_mean"] > 0
    ]
    fret_records = [record for record in validation.position_export.fret.records if record.ratio is not None]
    extremes = sorted(fret_records, key=lambda record: float(record.ratio))
    example_records = (*extremes[:3], *extremes[-3:])
    sensitivity = _pixel_pool_sensitivity(validation, (90.0, 95.0, 98.0, 99.0))
    log_rows = _slidebook_channel_rows(validation)

    selection_rows = []
    for channel in (Channel.C0, Channel.C1):
        metric = validation.selected_channel.metrics[channel]
        selection_rows.append(
            {
                "canal": channel.value,
                "P20 fondo robusto": metric.robust_background,
                "P95 señal robusta": metric.robust_signal,
                "contraste": metric.robust_contrast,
                "media": metric.mean,
                "mediana": metric.median,
                "mínimo": metric.minimum,
                "máximo": metric.maximum,
                "elegido": "sí" if channel is validation.selected_channel.selected_channel else "no",
            }
        )
    rejection_rows = [
        {
            "ROI": record.geometry.label,
            "área px": record.geometry.area_pixels,
            "borde": "sí" if record.geometry.touches_border else "no",
            "razón": "; ".join(record.reasons),
        }
        for record in rejected
    ]
    background_rows = [
        {
            "canal": estimate.channel.value,
            "frame": estimate.frame.frame_index,
            "P20 fondo": estimate.value,
            "media píxeles fondo": estimate.mean,
            "mediana": estimate.median,
            "desv. estándar": estimate.standard_deviation,
            "n píxeles": estimate.pixel_count,
        }
        for estimate in validation.position_export.background.estimates
    ]
    intensity_rows = _intensity_summary_rows(validation)
    saturation_rows = _saturation_summary_rows(validation)
    extreme_rows = [
        {
            "extremo descriptivo": "bajo" if record in extremes[:3] else "alto",
            "ROI": record.roi_label,
            "frame": record.frame.frame_index,
            "C0 media corregida": record.c0_background_corrected_mean,
            "C1 media corregida": record.c1_background_corrected_mean,
            "fórmula": "C0/C1",
            "ratio corregido": record.ratio,
        }
        for record in example_records
    ]

    return f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Validación estática Capture 1 + Position 1</title>
<style>
body{{font:15px/1.5 system-ui,Segoe UI,sans-serif;color:#1f2937;background:#eef2f6;margin:0}}main{{max-width:1180px;margin:auto;background:white;padding:32px 42px}}h1,h2{{color:#123047}}h2{{border-top:1px solid #d9e2ec;padding-top:26px;margin-top:38px}}.warning{{background:#fff4d6;border-left:6px solid #e9a23b;padding:16px}}.categories{{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}}.card{{border:1px solid #d9e2ec;border-radius:8px;padding:14px;background:#f8fafc}}.images{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px}}img{{max-width:100%;height:auto;border:1px solid #cbd5e1;background:#0b1320}}table{{border-collapse:collapse;width:100%;font-size:13px;margin:12px 0 20px}}th,td{{border:1px solid #cbd5e1;padding:7px;text-align:left;vertical-align:top}}th{{background:#e8f1f7}}code{{background:#edf2f7;padding:2px 4px}}.small{{font-size:12px;color:#52606d}}.good{{color:#116149}}.bad{{color:#9b2c2c}}.mono{{font-family:ui-monospace,Consolas,monospace;word-break:break-all}}@media(max-width:780px){{main{{padding:20px}}.images,.categories{{grid-template-columns:1fr}}}}
</style></head><body><main>
<h1>Validación visual estática y auditable</h1>
<p><strong>Capture 1 + Position 1</strong> · primer frame para segmentación · dos frames para intensidades y ratios.</p>
<div class="warning"><strong>No es un análisis de producción.</strong> Este informe conserva sin cambios el perfil D039: preprocesamiento identidad, segmentación P99 de C1, área mínima 20 px, exclusión de borde, fondo global P20 no-ROI, techo de cámara provisional 65535 y umbrales de intensidad/saturación desactivados. No aprueba ninguno de esos valores.</div>

<h2>Clasificación explícita de regiones</h2>
<div class="categories">
<div class="card"><strong>Nunca segmentadas</strong><br>{total_pixels - foreground_pixels:,} píxeles ({(total_pixels - foreground_pixels) / total_pixels:.2%}) quedaron como etiqueta 0 en el módulo 7. No son ROI y no reciben una razón de rechazo; este conteo no equivale a un número de células.</div>
<div class="card"><strong>Segmentadas y rechazadas geométricamente</strong><br>{filtering.rejected_count} de {segmentation.roi_count} componentes. Se retiraron por tamaño, borde o ambos antes de medir intensidades.</div>
<div class="card"><strong>Excluidas por intensidad o saturación</strong><br>{len(intensity_excluded)} ROI. También hay {len(intensity_flagged)} ROI marcadas. El valor cero significa “no hubo decisiones porque los umbrales están desactivados”, no “calidad científica demostrada”.</div>
</div>

<h2>1. Primer frame original de C0 y C1</h2>
<div class="images"><figure><img src="first_frame_c0.png" alt="Primer frame C0"><figcaption>C0; display P1–P99.5 = {displays['c0'].display_minimum:.1f}–{displays['c0'].display_maximum:.1f}.</figcaption></figure><figure><img src="first_frame_c1.png" alt="Primer frame C1"><figcaption>C1; display P1–P99.5 = {displays['c1'].display_minimum:.1f}–{displays['c1'].display_maximum:.1f}.</figcaption></figure></div>
<p class="small">El estiramiento es exclusivamente visual; no modifica píxeles ni cálculos.</p>

<h2>2. Métricas y canal elegido por el módulo 5</h2>
{_html_table(selection_rows)}
<p>El método <code>{escape(validation.selected_channel.method)}</code> eligió <strong>{validation.selected_channel.selected_channel.value}</strong> porque su contraste robusto fue mayor.</p>

<h2>3. Imagen después del preprocesamiento</h2>
<img src="preprocessed_selected_channel.png" alt="Frame preprocesado">
<p>Método: <code>{escape(validation.preprocessing.method)}</code>. La estrategia identidad convierte a <code>float64</code> y conserva los valores; no sustrae fondo.</p>

<h2>4. Umbral y máscara binaria del módulo 7</h2>
<div class="images"><div><p>Percentil: <strong>{percentile:g}</strong>. Umbral observado: <strong>{threshold:.3f}</strong>. Regla: píxel &gt; umbral.</p><p>Foreground: {foreground_pixels:,} de {total_pixels:,} píxeles ({foreground_pixels / total_pixels:.2%}).</p></div><img src="module7_binary_mask.png" alt="Máscara binaria módulo 7"></div>

<h2>5. Componentes antes del filtro geométrico</h2>
<img src="components_before_geometry.svg" alt="Componentes numerados antes del módulo 8">
<p>El módulo 7 produjo {segmentation.roi_count} componentes conexos con conectividad {segmentation.engine.parameters['connectivity']}; aún no estaban aceptados ni rechazados.</p>

<h2>6. Overlay numerado después del módulo 8</h2>
<img src="module8_numbered_overlay.svg" alt="Overlay numerado después del filtro geométrico">
<p>Cian continuo: aceptadas. Coral discontinuo: rechazadas. Amarillo punteado: marcadas; este perfil no produjo ninguna. Las razones visibles y auditables son:</p>
{_html_table(rejection_rows)}

<h2>7. Áreas, intensidades, fondo y posibles píxeles saturados</h2>
<p>Áreas retenidas: n={len(accepted_areas)}, rango {_range_text(accepted_areas)}, mediana {_median_text(accepted_areas)} px. Áreas rechazadas: n={len(rejected_areas)}, rango {_range_text(rejected_areas)}, mediana {_median_text(rejected_areas)} px.</p>
<h3>Intensidades de ROI retenidas, ambos frames</h3>{_html_table(intensity_rows)}
<h3>Fondo cuantitativo provisional</h3>{_html_table(background_rows)}
<h3>Saturación: evidencia, no decisión</h3>{_html_table(saturation_rows)}
<p>Con el techo provisional 65535 no hay píxeles contados como saturados. La columna ≥4095 es solo una comparación diagnóstica porque 4095 se mencionó como ejemplo posible en la especificación; los TIFF superan ampliamente ese valor y no se puede inferir el techo real desde el dtype. No se excluye ninguna ROI por esta tabla.</p>

<h2>8. C0 frente a C1 por ROI</h2>
<img src="c0_vs_c1_by_roi.svg" alt="C0 frente a C1 por ROI">
<p>Cada punto usa medias corregidas por fondo y conserva la etiqueta original. Los dos paneles separan los frames; no se inventan segundos.</p>

<h2>9. Distribución del ratio C0/C1 y ejemplos descriptivos</h2>
<img src="ratio_distribution.svg" alt="Distribución de ratios">
<p>La fórmula está fijada por D042 como <strong>C0/C1</strong> y usa la media de ROI después de restar el fondo. Los {len(ratios)} ratios regenerados del módulo 13 abarcan <strong>{min(ratios):.4f}–{max(ratios):.4f}</strong>, con mediana {median(ratios):.4f}. La tabla siguiente muestra solo los tres extremos inferiores y superiores para inspección; no define outliers ni límites de producción.</p>
{_html_table(extreme_rows)}
<div class="warning"><strong>Resultados anteriores superseded:</strong> el rango 2.77–10.86 se calculó como C1/C0 y no representa el objetivo manual. Su histograma, ejemplos extremos y explicación causal quedan reemplazados por este informe regenerado.</div>
<p>Las medias crudas se conservan separadamente y su C0/C1 descriptivo abarca {min(raw_ratios):.4f}–{max(raw_ratios):.4f}; no sustituye el ratio principal corregido. La selección P99 continúa siendo solo evidencia diagnóstica y no una segmentación celular aprobada.</p>
<h3>Sensibilidad diagnóstica del pool de píxeles de C1</h3>
{_html_table(sensitivity)}
<p class="small">Comparación descriptiva ajena al pipeline: no crea ROI, no aplica el filtro de área y no cambia P99. Solo calcula C0/C1 a partir de las medias corregidas dentro de pools de píxeles C1 por encima de cada percentil.</p>

<h3>Asignación de canales conservada desde SlideBook</h3>
{_html_table(log_rows)}
<p><strong>Uso provisional:</strong> C0 CFPex/CFPem como donor y C1 CFPex/YFPem como FRET. La correspondencia está respaldada por el texto del log, pero queda pendiente de confirmación científica y de revisar exposición, ganancia, bleed-through, excitación directa y cualquier corrección instrumental necesaria.</p>

<h2>10. Qué entra y qué sale de cada módulo</h2>
{_html_table(module_rows)}

<h2>Auditoría y archivos asociados</h2>
<p><a href="roi_audit.csv">roi_audit.csv</a> conserva los 58 componentes, incluidos los 22 rechazados. <a href="roi_measurements.csv">roi_measurements.csv</a> conserva las 72 observaciones ROI-frame aceptadas geométricamente. <a href="module_io.csv">module_io.csv</a> replica la tabla módulo por módulo. <a href="audit_manifest.json">audit_manifest.json</a> registra parámetros, conteos y SHA-256.</p>
{_html_table(source_files)}
<p class="warning"><strong>Preguntas científicas pendientes:</strong> confirmar roles C0/C1; identificar el techo real de cámara; decidir si los puncta C1 son estructuras biológicas válidas; elegir motor de segmentación, preprocesamiento y fondo de producción; determinar correcciones ópticas; y solo después considerar criterios de intensidad, saturación o ratio.</p>
</main></body></html>"""


def _pixel_pool_sensitivity(
    validation: RealPairValidationResult,
    percentiles: Iterable[float],
) -> list[dict[str, Any]]:
    pair = validation.position_export.pair
    assert pair is not None
    selected = validation.selected_channel.selected_channel
    selected_frame = pair.c0.frames[0] if selected is Channel.C0 else pair.c1.frames[0]
    c0_frame = pair.c0.frames[0].astype(float)
    c1_frame = pair.c1.frames[0].astype(float)
    c0_background = validation.position_export.background.estimate_for(Channel.C0, 0).value
    c1_background = validation.position_export.background.estimate_for(Channel.C1, 0).value
    rows: list[dict[str, Any]] = []
    for percentile in percentiles:
        threshold = float(np.percentile(selected_frame, percentile))
        mask = selected_frame > threshold
        pixel_count = int(np.count_nonzero(mask))
        c0_corrected = (
            _subtract(float(np.mean(c0_frame[mask])), c0_background)
            if pixel_count
            else None
        )
        c1_corrected = (
            _subtract(float(np.mean(c1_frame[mask])), c1_background)
            if pixel_count
            else None
        )
        rows.append(
            {
                "percentil diagnóstico": percentile,
                "canal del pool": selected.value,
                "umbral": threshold,
                "píxeles": pixel_count,
                "fracción": float(np.mean(mask)),
                "C0 corregido medio": c0_corrected,
                "C1 corregido medio": c1_corrected,
                "C0/C1 de medias corregidas": (
                    c0_corrected / c1_corrected
                    if c0_corrected is not None and c1_corrected is not None and c1_corrected > 0
                    else None
                ),
            }
        )
    return rows


def _intensity_summary_rows(validation: RealPairValidationResult) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for channel in (Channel.C0, Channel.C1):
        records = validation.position_export.temporal_intensity.records_for(channel=channel)
        raw = [record.raw_mean for record in records]
        corrected = [record.background_corrected_mean for record in records if record.background_corrected_mean is not None]
        rows.append(
            {
                "canal": channel.value,
                "n ROI-frame": len(records),
                "media cruda mín": min(raw),
                "media cruda mediana": median(raw),
                "media cruda máx": max(raw),
                "media corregida mín": min(corrected),
                "media corregida mediana": median(corrected),
                "media corregida máx": max(corrected),
            }
        )
    return rows


def _saturation_summary_rows(validation: RealPairValidationResult) -> list[dict[str, Any]]:
    pair = validation.position_export.pair
    assert pair is not None
    rows: list[dict[str, Any]] = []
    for channel, frames in ((Channel.C0, pair.c0.frames), (Channel.C1, pair.c1.frames)):
        for frame_index, frame in enumerate(frames):
            qc = validation.position_export.intensity_qc.records_for(
                scope=IntensityQcScope.FIELD_FRAME,
                channel=channel,
                frame_index=frame_index,
            )[0]
            rows.append(
                {
                    "canal": channel.value,
                    "frame": frame_index,
                    "máximo observado": int(np.max(frame)),
                    "≥65535 (perfil validación)": qc.metrics["saturated_pixel_count"],
                    "≥4095 (solo diagnóstico)": int(np.count_nonzero(frame >= 4095)),
                    "estado QC actual": qc.status.value,
                }
            )
    return rows


def _slidebook_channel_rows(validation: RealPairValidationResult) -> list[dict[str, Any]]:
    pair = validation.position_export.pair
    assert pair is not None
    rows: list[dict[str, Any]] = []
    for association in pair.auxiliary_metadata_associations:
        log = association.metadata_file.slidebook_log
        if log is None:
            continue
        for row in log.rows:
            rows.append(
                {
                    "TIFF": row.tiff_filename,
                    "Channel Name en log": row.channel_name,
                    "rol usado en validación": "donor" if "_C0." in row.tiff_filename else "FRET",
                    "estado científico": "pendiente de confirmación",
                }
            )
    return rows


def _roi_labels_with_intensity_status(
    validation: RealPairValidationResult,
    status: IntensityQcStatus,
) -> set[int]:
    return {
        record.roi_label
        for record in validation.position_export.intensity_qc.records
        if record.roi_label is not None
        and record.scope in (IntensityQcScope.ROI_FRAME, IntensityQcScope.ROI)
        and record.status is status
    }


def _module_parameters(validation: RealPairValidationResult) -> dict[str, Any]:
    return {
        "module5": {
            "method": validation.selected_channel.method,
            "selected_channel": validation.selected_channel.selected_channel.value,
        },
        "module6": {
            "method": validation.preprocessing.method,
            "parameters": dict(validation.preprocessing.parameters),
        },
        "module7": {
            "engine": validation.segmentation.engine.name,
            "version": validation.segmentation.engine.version,
            "model": validation.segmentation.engine.model,
            "parameters": dict(validation.segmentation.engine.parameters),
        },
        "module8": {
            "min_area_pixels": validation.roi_filtering.config.min_area_pixels,
            "max_area_pixels": validation.roi_filtering.config.max_area_pixels,
            "border_policy": validation.roi_filtering.config.border_policy.value,
        },
        "module10": dict(validation.position_export.background.parameters),
        "module11": dict(validation.position_export.intensity_qc.parameters),
        "module12": dict(validation.position_export.temporal_intensity.parameters),
        "module13": dict(validation.position_export.fret.parameters),
    }


def _source_file_records(validation: RealPairValidationResult) -> list[dict[str, Any]]:
    pair = validation.position_export.pair
    assert pair is not None
    files = [
        _file_record(pair.c0.parsed_file.source.path, role="C0 TIFF"),
        _file_record(pair.c1.parsed_file.source.path, role="C1 TIFF"),
    ]
    files.extend(
        _file_record(association.metadata_file.source.path, role="SlideBook log")
        for association in pair.auxiliary_metadata_associations
    )
    return files


def _file_record(path: Path, *, role: str) -> dict[str, Any]:
    data = path.read_bytes()
    return {
        "role": role,
        "name": path.name,
        "path": str(path.resolve(strict=False)),
        "size_bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    if not rows:
        raise ValueError(f"cannot write empty audit CSV: {path.name}")
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _html_table(rows: Sequence[Mapping[str, Any]]) -> str:
    if not rows:
        return '<p class="small">Sin registros.</p>'
    headers = list(rows[0])
    head = "".join(f"<th>{escape(str(header))}</th>" for header in headers)
    body = "".join(
        "<tr>"
        + "".join(f"<td>{escape(_format_value(row.get(header)))}</td>" for header in headers)
        + "</tr>"
        for row in rows
    )
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def _format_value(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "sí" if value else "no"
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value)


def _range_text(values: Sequence[int]) -> str:
    return f"{min(values)}–{max(values)} px" if values else "sin valores"


def _median_text(values: Sequence[int]) -> str:
    return f"{median(values):.1f}" if values else "—"


def _subtract(value: float, background: float | None) -> float | None:
    return value - background if background is not None else None


def _json_default(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, tuple):
        return list(value)
    raise TypeError(f"cannot serialize {type(value).__name__}")
