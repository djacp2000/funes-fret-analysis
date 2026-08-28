# F.U.N.E.S. — FRET Unified Normalization and Extraction Suite

**FUNES Lite** es una aplicación portátil de Windows para el análisis automático y **provisional** de series temporales FRET de dos canales exportadas desde SlideBook como TIFF. No requiere instalar Python ni usar una línea de comandos.

Analiza cada adquisición C0/C1 válida que encuentre, segmenta células en el primer frame, mantiene las mismas máscaras para ambos canales y todos los frames, y calcula la razón explícita `C0 / C1`.

> **Importante:** FUNES Lite no está científicamente validado ni es software clínico. Su análisis es automático y provisional; revise los resultados, las máscaras y los informes antes de utilizarlos para conclusiones científicas.

## Qué puede ejecutar un usuario hoy

La distribución `FUNES_lite_standalone_v1` incluye esta estructura:

```text
FUNES_lite_standalone_v1/
├── FUNES_lite_standalone_v1.exe
├── funes_files/
├── input/
├── output/
└── LEEME.txt
```

Ejecute `FUNES_lite_standalone_v1.exe`. La ventana muestra el avance por posición y el progreso total; no solicita parámetros, confirmaciones ni argumentos. La aplicación comienza a procesar automáticamente el contenido de su carpeta vecina `input/`.

Todos los pares válidos se etiquetan como `Experiment 1` en esta edición Lite. La asignación de experimentos, la revisión manual de ROI y los flujos de análisis revisado no forman parte de la interfaz Lite.

## Preparar la entrada

1. Copie los TIFF de una o más adquisiciones a la carpeta `input/`, sin modificar los originales.
2. Para cada posición debe haber un TIFF `C0` y otro `C1` con la misma identidad de adquisición. Se aceptan extensiones `.tif` y `.tiff`.
3. Mantenga el patrón exportado por SlideBook, por ejemplo:

   ```text
   Capture 1 - Position 1_XY1782521382_Z0_T00_C0.tif
   Capture 1 - Position 1_XY1782521382_Z0_T00_C1.tif
   ```

   Los campos `Capture`, `Position`, `XY`, `Z` y `T` se conservan como metadatos. Cada TIFF se interpreta como una secuencia temporal ordenada de frames: `Z` y `T` del nombre no redefinen esa secuencia.

4. Puede incluir archivos auxiliares de SlideBook, como `.log` o `.txt`, junto a los TIFF. Se preservan cuando pueden asociarse de forma inequívoca al par.

La aplicación sólo lee los TIFF y archivos auxiliares de entrada; no los renombra, sobrescribe ni modifica.

## Obtener los resultados

Al terminar, revise la carpeta `output/`:

| Ubicación | Contenido |
| --- | --- |
| `output/workbooks/` | Libro(s) Excel `.xlsx` con los resultados exportados. |
| Hoja `simple_results` | Una fila por experimento, captura, posición, ROI y frame; incluye `C0_mean`, `C1_mean` y `ratio_C0_C1`. Los promedios de esta hoja están corregidos por fondo. |
| Hoja `intensity_long` | Mediciones detalladas, incluidas las intensidades crudas, para trazabilidad. |
| `output/roi_overlays/` | Máscaras de ROI del primer frame en PNG y SVG para revisión visual. |
| `output/position_reports/` | Un informe HTML por posición completada o fallida. |
| `output/simple_analysis_summary.json` | Resumen del lote: libros creados, pares completados, fallos e incidencias de descubrimiento/validación. |

La segmentación selecciona automáticamente el canal C0 o C1 mediante una métrica robusta de señal del primer frame. Cada ROI aceptada queda fija para C0, C1 y todos los frames temporales. La aplicación realiza corrección de fondo y calcula `C0 / C1`; los parámetros de esta ruta Lite son fijos y provisionales.

Un fallo en una posición no impide procesar las demás posiciones válidas. Consulte su informe HTML para el error. El lote se detiene sólo si `input/` no puede leerse, `output/` no puede utilizarse o ningún par válido logra exportarse.

## Ruta Python opcional

Para ejecutar la misma ruta automática desde un clon del repositorio (dirigido a desarrolladores o usuarios técnicos), se necesita Python 3.10 o posterior y las dependencias del proyecto:

```powershell
python -m pip install -e .
python scripts/run_simple_fret_analysis.py input output
```

El primer argumento es la carpeta de entrada y el segundo la carpeta de salida. Esta ruta genera los mismos tipos de resultados provisionales; no convierte el análisis en una validación científica.

Para construir la distribución portátil en Windows:

```powershell
python -m pip install -e ".[standalone]"
python scripts/build_funes_lite_standalone.py
```

El build crea `dist/FUNES_lite_standalone_v1/` y su ZIP. Ambos son artefactos generados e ignorados por Git; no forman parte del código fuente publicado.

Para comprobar los contratos del proyecto con datos sintéticos:

```powershell
python -m unittest discover -s tests
```

## Límites conocidos

- FUNES Lite no corrige automáticamente el drift ni ofrece edición interactiva de ROI.
- Los límites de tamaño de ROI, la segmentación y los criterios de calidad de Lite no sustituyen una configuración o una revisión científica específica del experimento.
- Los resultados deben revisarse con las máscaras y los informes laterales antes de interpretarse.
- La ruta Lite no ejecuta los flujos de revisión, autorización o activación de análisis del proyecto modular.

## Para desarrolladores

FUNES mantiene una arquitectura modular para descubrimiento de archivos, lectura TIFF, metadatos auxiliares, segmentación, control de calidad, extracción temporal, cálculo FRET y exportación auditable. Las especificaciones, decisiones y estado de los módulos están en [docs/PROJECT_SPEC.md](docs/PROJECT_SPEC.md), [docs/MODULE_PLAN.md](docs/MODULE_PLAN.md) y [docs/DECISIONS.md](docs/DECISIONS.md).

## Licencia

MIT. Consulte [LICENSE](LICENSE).
