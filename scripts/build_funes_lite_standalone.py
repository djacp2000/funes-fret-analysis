"""Build the ZIP-ready ``FUNES_lite_standalone_v1`` Windows distribution."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NAME = "FUNES_lite_standalone_v1"
DIST_ROOT = ROOT / "dist" / NAME


def main() -> int:
    shutil.rmtree(DIST_ROOT, ignore_errors=True)
    build_root = ROOT / "build" / NAME
    subprocess.run([
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--onedir", "--noconsole",
        "--contents-directory", "funes_files", "--name", NAME,
        "--distpath", str(ROOT / "dist"), "--workpath", str(build_root),
        "--specpath", str(build_root), "--paths", str(ROOT / "src"),
        str(ROOT / "scripts" / "run_funes_lite_standalone.py"),
    ], check=True, cwd=ROOT)
    (DIST_ROOT / "input").mkdir()
    (DIST_ROOT / "output").mkdir()
    (DIST_ROOT / "LEEME.txt").write_text(
        "FUNES — FRET Unified Normalization and Extraction Suite\n"
        "FUNES Lite standalone v1\n\n"
        "1. Copie los TIFF C0/C1 y archivos auxiliares a input.\n"
        "2. Ejecute FUNES_lite_standalone_v1.exe; no requiere Python.\n"
        "3. Los XLS finales se guardan en output\\workbooks.\n"
        "4. Los informes por posición y overlays quedan en output como resultados secundarios.\n\n"
        "Advertencia: análisis automático provisional, no validado científicamente.\n",
        encoding="utf-8",
    )
    print(shutil.make_archive(str(ROOT / "dist" / NAME), "zip", ROOT / "dist", NAME))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
