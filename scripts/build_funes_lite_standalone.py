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
    (DIST_ROOT / "README.txt").write_text(
        "FUNES — FRET Unified Normalization and Extraction Suite\n"
        "FUNES Lite standalone v1\n\n"
        "1. Copy the C0/C1 TIFF files and auxiliary files into input.\n"
        "2. Run FUNES_lite_standalone_v1.exe; Python is not required.\n"
        "3. Final XLS workbooks are saved in output\\workbooks.\n"
        "4. Per-position reports and overlays remain in output as secondary results.\n\n"
        "Warning: automatic provisional analysis, not scientifically validated.\n",
        encoding="utf-8",
    )
    print(shutil.make_archive(str(ROOT / "dist" / NAME), "zip", ROOT / "dist", NAME))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
